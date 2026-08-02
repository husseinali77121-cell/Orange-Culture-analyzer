# -*- coding: utf-8 -*-
# © 2025 Dr / Hussein Ali — Orange Lab, 6 October City, Egypt
# Microbiology CDSS — All Rights Reserved
"""self_check.py — فحص ما قبل التبليغ / pre-release verification.

WHAT THIS IS FOR, AND WHAT IT IS NOT FOR
----------------------------------------
The nine test suites in this repo all prove the same kind of thing: that the
ENGINE reaches the right conclusion. None of them looks at what the SCREEN
prints. Every defect found in the 2026-08-02 audit lived in that gap — the
engine decided correctly and the renderer dropped the sentence:

    · 100% of safety-gate reclassifications displayed a blank reason
    · 15.3% of banned drugs displayed "💊 Cefazolin []" with no category
    · 48.6% of warnings displayed a note belonging to a different organ
    · a neonate's kernicterus warning rendered as an empty line

So this module deliberately checks the things the engine CANNOT check about
itself. A verification that only asks "is the engine self-consistent?" would
have returned green on all four of those.

THREE STATES, NOT TWO
---------------------
    OK        — nothing found. Safe to report.
    ATTENTION — something needs a human's eye before this goes out.
    BLOCK     — do not report this as it stands.

Two states would make the check a rubber stamp: anything not provably broken
becomes "approved". The middle state is the whole point — most real findings
are "a human has to look at this", not "the software is wrong".

WHAT A GREEN RESULT DOES NOT MEAN
---------------------------------
It does not mean the advice is clinically correct. It means the report is
internally consistent, fully explained, and complete enough to be read. The
clinical judgement is still the microbiologist's, and `guideline_registry.py`
still lists rules awaiting a clinician's countersignature.

USAGE
-----
    from self_check import run_self_check, OK, ATTENTION, BLOCK

    result = run_self_check(
        allowed=allowed, warned=warned, banned=banned,
        preg_warn_items=preg_warn_items,
        sir_map=sir_map, organism=organism_type, specimen=culture_type,
        age=age, age_months=age_months, is_renal=is_renal, cl_cr=cl_cr,
        is_preg=is_preg, is_hepatic=is_hepatic, child_pugh=child_pugh,
        gate_report=_gate_report, qc_issues=qc_issues,
        warned_note_for=warned_note_for,
        banned_category_label=banned_category_label,
        intrinsic_checker=is_intrinsically_avoided,
    )
    result["state"]    -> "ok" | "attention" | "block"
    result["findings"] -> [{level, code, title_ar, detail_ar, drug}]
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

__all__ = ["run_self_check", "OK", "ATTENTION", "BLOCK", "SELF_CHECK_VERSION",
           "state_badge"]

SELF_CHECK_VERSION = "1.0.0"

OK, ATTENTION, BLOCK = "ok", "attention", "block"
_RANK = {OK: 0, ATTENTION: 1, BLOCK: 2}


def _name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name") or item.get("drug") or "").strip()
    return str(item).strip()


class _Findings:
    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []

    def add(self, level: str, code: str, title: str, detail: str = "",
            drug: str = "") -> None:
        self.rows.append({"level": level, "code": code, "title_ar": title,
                          "detail_ar": detail, "drug": drug})

    def worst(self) -> str:
        return max((r["level"] for r in self.rows), key=lambda s: _RANK[s],
                   default=OK)


def run_self_check(
    *,
    allowed: List[Dict],
    warned: List[Dict],
    banned: List[Dict],
    preg_warn_items: Optional[List[Dict]] = None,
    sir_map: Optional[Dict[str, str]] = None,
    organism: str = "",
    specimen: str = "",
    age: Optional[float] = None,
    age_months: Optional[int] = None,
    is_renal: bool = False,
    cl_cr: Optional[float] = None,
    is_preg: bool = False,
    is_hepatic: bool = False,
    child_pugh: Optional[str] = None,
    gate_report: Optional[Dict[str, Any]] = None,
    qc_issues: Optional[List[Dict[str, Any]]] = None,
    warned_note_for: Optional[Callable[[Dict], str]] = None,
    banned_category_label: Optional[Callable[[Optional[str]], str]] = None,
    intrinsic_checker: Optional[Callable[[str, str], bool]] = None,
) -> Dict[str, Any]:
    """Verify a finished report before it is read. Never raises."""
    F = _Findings()
    sir_map = sir_map or {}
    preg_warn_items = preg_warn_items or []
    qc_issues = qc_issues or []

    a_names = [_name(d) for d in allowed]
    w_names = [_name(d) for d in warned]
    b_names = [_name(d) for d in banned]

    # ── A. BUCKET INTEGRITY ─────────────────────────────────────────────
    for pair, lbl in ((set(a_names) & set(w_names), "موصى به + تحذير"),
                      (set(a_names) & set(b_names), "موصى به + ممنوع"),
                      (set(w_names) & set(b_names), "تحذير + ممنوع")):
        for d in sorted(pair):
            F.add(BLOCK, "BUCKET_COLLISION",
                  f"{d} ظاهر في خانتين متناقضتين ({lbl}).",
                  "الدواء الواحد لا يمكن أن يكون موصى به وممنوعاً في نفس التقرير.", d)

    for bucket, lbl in ((allowed, "موصى به"), (warned, "تحذير"), (banned, "ممنوع")):
        for it in bucket:
            if not _name(it):
                F.add(BLOCK, "NAMELESS_DRUG",
                      f"عنصر بلا اسم في خانة «{lbl}».",
                      "لا يمكن تبليغ توصية بدواء غير مُسمّى.")

    # ── B. EXPLAINABILITY — the class of defect this module exists for ──
    # A ban with no stated reason is read as an arbitrary ban, and an
    # arbitrary ban is overridden. The reason IS the safety feature.
    for it in banned:
        d = _name(it)
        if banned_category_label is not None:
            lbl = (banned_category_label(it.get("category")) or "").strip()
            if not lbl:
                F.add(BLOCK, "BAN_NO_LABEL",
                      f"{d}: ممنوع بفئة «{it.get('category')}» ليس لها مسمّى معروض.",
                      "سيظهر للطبيب بأقواس فارغة بدون سبب.", d)
        if not (it.get("reason_short") or "").strip():
            F.add(BLOCK, "BAN_NO_REASON",
                  f"{d}: ممنوع بدون سبب مكتوب.",
                  "منع بلا سبب معروض = منع سيتم تجاهله.", d)

    if warned_note_for is not None:
        for it in warned:
            d = _name(it)
            try:
                note = (warned_note_for(it) or "").strip()
            except Exception as exc:                    # a renderer must not crash
                F.add(BLOCK, "WARN_RENDER_ERROR",
                      f"{d}: فشل توليد نص التحذير.", str(exc), d)
                continue
            if not note:
                F.add(BLOCK, "WARN_NO_NOTE",
                      f"{d}: تحذير بدون نص.",
                      "سيظهر سطر تحذير فارغ — أسوأ من عدم عرضه.", d)
            wr = it.get("warning_reason")
            if not wr:
                F.add(ATTENTION, "WARN_NO_REASON_CODE",
                      f"{d}: تحذير بلا سبب مصنَّف (warning_reason).",
                      "النص ظهر عبر المسار الاحتياطي؛ راجع مصدر التحذير.", d)
            # The defect that started this: a hepatic warning must not be
            # explained with a kidney instruction.
            if wr == "hepatic_adjustment" and not (it.get("hepatic_rec") or "").strip():
                F.add(ATTENTION, "HEPATIC_NO_BAND",
                      f"{d}: تحذير كبدي بلا شريحة جرعة مسجَّلة.",
                      "راجع BNF 2025 / LiverTox قبل التبليغ.", d)

    for m in (gate_report or {}).get("moves", []) or []:
        if not (m.get("reason_ar") or m.get("reason_en") or m.get("why")):
            F.add(BLOCK, "GATE_MOVE_NO_REASON",
                  f"{m.get('drug')}: بوابة الأمان نقلته "
                  f"({m.get('from')} → {m.get('to')}) بدون سبب معروض.",
                  "إعادة تصنيف بلا تفسير لا يمكن مراجعتها.", str(m.get("drug") or ""))

    # ── C. CLINICAL INVARIANTS, RE-DERIVED INDEPENDENTLY ────────────────
    # Deliberately recomputed from sir_map rather than trusting the engine:
    # a check that asks the engine to confirm itself proves nothing.
    for d in a_names:
        r = str(sir_map.get(d, "")).strip().upper()
        if r == "R":
            F.add(BLOCK, "RESISTANT_IN_ALLOWED",
                  f"{d}: مقاوم (R) في اللوحة ومع ذلك ظاهر في الموصى به.",
                  "تناقض مباشر مع نتيجة المزرعة.", d)
    for d in w_names:
        if str(sir_map.get(d, "")).strip().upper() == "R":
            F.add(BLOCK, "RESISTANT_IN_WARNED",
                  f"{d}: مقاوم (R) في اللوحة ومع ذلك ظاهر في خانة التحذير.",
                  "المقاوم يُنقل للممنوع، لا للتحذير.", d)

    if intrinsic_checker is not None and organism:
        for d in a_names + w_names:
            try:
                if intrinsic_checker(organism, d):
                    F.add(BLOCK, "INTRINSIC_OFFERED",
                          f"{d}: مقاومة جوهرية لـ {organism} ومع ذلك معروض للاستخدام.",
                          "المقاومة الجوهرية لا تُتجاوز مهما كانت نتيجة القرص.", d)
            except Exception:
                pass

    # ── D. DATA COMPLETENESS — the gates that must fail closed ──────────
    if age is not None and age < 1 and age_months is None:
        F.add(ATTENTION, "MISSING_AGE_MONTHS",
              "العمر أقل من سنة والعمر بالشهور غير مُدخل.",
              "الحدود العمرية لحديثي الولادة لم تُطبَّق بدقة. "
              "أدخل العمر بالشهور في خانة «أقل من سنة».")
    if is_renal and cl_cr is None:
        F.add(ATTENTION, "MISSING_CRCL",
              "قصور كلوي مُعلَّم وقيمة CrCl غير متاحة.",
              "تعديل الجرعة الكلوي محسوب على تقدير وليس على قياس.")
    if is_hepatic and not (child_pugh or "").strip():
        F.add(ATTENTION, "MISSING_CHILD_PUGH",
              "قصور كبدي مُعلَّم بدون تصنيف Child-Pugh.",
              "النظام يفترض الدرجة C (الأشد) عند غياب التصنيف — تحقق.")
    if is_preg and (age is None or age <= 0):
        F.add(ATTENTION, "PREG_NO_AGE",
              "حمل مُعلَّم بدون عمر صالح.", "راجع بيانات المريضة.")

    gr = gate_report or {}
    if gr and not gr.get("specimen_recognised", True):
        F.add(ATTENTION, "SPECIMEN_UNKNOWN",
              f"نوع العينة «{specimen}» غير معروف لبوابة الأمان.",
              "لم يتم التحقق من ملاءمة موقع العدوى — راجع التوصيات يدوياً.")
    if gr and not gr.get("organism_recognised", True):
        F.add(ATTENTION, "ORGANISM_UNKNOWN",
              f"الكائن «{organism}» غير معروف لبوابة الأمان.",
              "طبقات الأمان الخاصة بالكائن لم تُطبَّق.")
    if not gr:
        F.add(ATTENTION, "GATE_DID_NOT_RUN",
              "بوابة الأمان لم تعمل على هذا التقرير.",
              "طبقة نفاذية الموقع والحمل والكبد والكلى غير مُطبَّقة.")

    # ── E. COVERAGE & QC SURFACING ──────────────────────────────────────
    if not allowed:
        F.add(ATTENTION, "NO_OPTION",
              "لا يوجد أي خيار موصى به بعد تطبيق كل القيود.",
              "استشر الميكروبيولوجي — قد يلزم علاج توليفي أو دواء إنقاذي.")
    if not (allowed or warned or banned):
        F.add(BLOCK, "EMPTY_REPORT",
              "التقرير فارغ تماماً.", "لم يُصنَّف أي مضاد — لا شيء للتبليغ.")

    for q in qc_issues:
        sev = str(q.get("severity") or q.get("level") or "").lower()
        if "critical" in sev:
            F.add(BLOCK, "QC_CRITICAL",
                  f"QC حرج: {q.get('message') or q.get('title') or q.get('id') or '—'}",
                  "لوحة الحساسية بها تناقض حرج — لا تُبلَّغ قبل الإعادة.")
        elif "major" in sev or "warn" in sev or "high" in sev:
            F.add(ATTENTION, "QC_MAJOR",
                  f"QC: {q.get('message') or q.get('title') or q.get('id') or '—'}")

    if is_preg and preg_warn_items:
        F.add(ATTENTION, "PREG_REVIEW",
              f"{len(preg_warn_items)} دواء يحتاج قرار طبيب في الحمل.",
              "هذه الأدوية غير محظورة تلقائياً — القرار النهائي للطبيب المعالج.")

    state = F.worst()
    counts = {lvl: sum(1 for r in F.rows if r["level"] == lvl)
              for lvl in (BLOCK, ATTENTION)}
    return {
        "version": SELF_CHECK_VERSION,
        "state": state,
        "findings": F.rows,
        "counts": counts,
        "checked": {"allowed": len(allowed), "warned": len(warned),
                    "banned": len(banned), "gate_moves": len(gr.get("moves") or [])},
    }


def state_badge(state: str, lang: str = "ar") -> str:
    """One line the clinician can read without opening anything."""
    if lang == "en":
        return {OK: "✅ Checks passed — report is complete and internally consistent.",
                ATTENTION: "⚠️ Needs review before reporting.",
                BLOCK: "🚫 Do not report as it stands."}.get(state, state)
    return {OK: "✅ الفحص سليم — التقرير مكتمل ومتّسق داخلياً.",
            ATTENTION: "⚠️ يحتاج مراجعة قبل التبليغ.",
            BLOCK: "🚫 لا تُبلّغ التقرير بحالته الراهنة."}.get(state, state)
