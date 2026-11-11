# -*- coding: utf-8 -*-
"""final_checklist.py — the last screen before a report leaves the lab.

Added 2026-11-11. Every check below is already enforced somewhere inside the
engine; this module does not decide anything new. It re-asks the questions a
reviewer would ask — does the specimen fit the organism, does the organism fit
the Gram stain and the antibiotic panel, is anything recommended that should
not be — and answers each with one line: pass (green), attention (amber) or
fail (red). A red line means "do not release until someone has looked".

Pure functions, no Streamlit: build_final_checklist() can be tested directly.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

PASS, WARN, FAIL, NA = "pass", "warn", "fail", "na"
ICON = {PASS: "✅", WARN: "⚠️", FAIL: "❌", NA: "➖"}


def _name(x: Any) -> str:
    return x.get("name", "") if isinstance(x, dict) else str(x)


def _intrinsic_row(organism: str) -> List[str]:
    """Same lookup rule as the therapy engine (substring either way)."""
    from clinical_data import INTRINSIC_RESISTANCE
    o = " ".join(str(organism or "").lower().split())
    if len(o) < 4:
        return []
    out: List[str] = []
    for key, drugs in INTRINSIC_RESISTANCE.items():
        if key in o or o in key:
            out.extend(drugs)
    return out


def build_final_checklist(
    organism: str,
    specimen: str,
    sir_map: Optional[Dict[str, str]],
    allowed: Optional[List[Any]] = None,
    warned: Optional[List[Any]] = None,
    banned: Optional[List[Any]] = None,
    qc_issues: Optional[List[Dict[str, Any]]] = None,
    gram_stain: str = "",
    patho_result: Optional[Dict[str, Any]] = None,
    panel_result: Any = None,
    preg_warn: Optional[List[Any]] = None,
) -> List[Dict[str, str]]:
    """Return [{key, title, status, detail}] in the order a reviewer reads.

    `preg_warn` (2026-11-11, round 4): the pregnancy-caution bucket is a list
    of options the clinician may still use. Without it a pregnant patient whose
    only usable agents were "use with caution in pregnancy" got a red "no
    treatment option" line, and checks 4 and 5 never looked at those agents.
    """
    sir_map = dict(sir_map or {})
    allowed, warned, banned = list(allowed or []), list(warned or []), list(banned or [])
    preg_warn = list(preg_warn or [])
    out: List[Dict[str, str]] = []

    def add(key, title, status, detail):
        out.append({"key": key, "title": title, "status": status, "detail": detail})

    # 1 ── specimen ↔ organism ────────────────────────────────────────────────
    try:
        import clinical_matrix as CM
        site, org = CM.canonical_site(specimen), CM.canonical_organism(organism)
        flag = CM.SITE_ORGANISM_PLAUSIBILITY.get(site, {}).get(org) if site and org else None
    except Exception:
        site, org, flag = None, None, None
    if not organism or not specimen:
        add("specimen_organism", "نوع العينة ↔ نوع البكتيريا", FAIL,
            "نوع العينة أو البكتيريا غير مُدخل.")
    elif flag == "implausible":
        add("specimen_organism", "نوع العينة ↔ نوع البكتيريا", FAIL,
            f"{organism} في عينة {specimen} غير متوقع إطلاقاً — راجع التعريف أو نوع العينة.")
    elif flag == "rare":
        add("specimen_organism", "نوع العينة ↔ نوع البكتيريا", WARN,
            f"{organism} نادر في عينة {specimen} — أكّد التعريف واستبعد التلوث.")
    elif site is None:
        add("specimen_organism", "نوع العينة ↔ نوع البكتيريا", WARN,
            f"نوع العينة «{specimen}» غير معروف للبرنامج — لم يُتحقق من الملاءمة.")
    else:
        add("specimen_organism", "نوع العينة ↔ نوع البكتيريا", PASS,
            f"{organism} متوافق مع عينة {specimen}.")

    # 2 ── organism ↔ Gram stain ──────────────────────────────────────────────
    try:
        from pathogenicity import _gram_type, _stain_type, _GRAM_COMPATIBLE, _GRAM_LABEL
        iso = _gram_type(" ".join(str(organism or "").lower().split()))
        st_ = _stain_type(gram_stain)
    except Exception:
        iso = st_ = None
        _GRAM_COMPATIBLE, _GRAM_LABEL = {}, {}
    if not gram_stain or "مش متعملة" in gram_stain:
        add("organism_gram", "نوع البكتيريا ↔ صبغة Gram", NA, "صبغة Gram غير مُدخلة.")
    elif st_ == "variable":
        add("organism_gram", "نوع البكتيريا ↔ صبغة Gram", WARN,
            "Gram-variable — نتيجة صبغة غير حاسمة؛ الاعتماد على التعريف (ID).")
    elif st_ is None or iso is None or st_ == "mixed":
        add("organism_gram", "نوع البكتيريا ↔ صبغة Gram", PASS,
            "لا تعارض بين الصبغة والعزلة.")
    elif st_ in _GRAM_COMPATIBLE.get(iso, {iso}):
        add("organism_gram", "نوع البكتيريا ↔ صبغة Gram", PASS,
            f"الصبغة ({_GRAM_LABEL.get(st_, st_)}) مطابقة لـ {organism}.")
    else:
        add("organism_gram", "نوع البكتيريا ↔ صبغة Gram", FAIL,
            f"الصبغة ({_GRAM_LABEL.get(st_, st_)}) لا تطابق {organism} "
            f"({_GRAM_LABEL.get(iso, iso)}) — راجع الشريحة أو التعريف.")

    # 3 ── organism ↔ antibiotics (intrinsic resistance reported S / I) ───────
    intrinsic = set(_intrinsic_row(organism))
    bad = sorted(d for d, r in sir_map.items() if d in intrinsic and r in ("S", "I"))
    if not sir_map:
        add("organism_antibiotics", "نوع البكتيريا ↔ المضادات المختبَرة", FAIL,
            "لا توجد نتائج حساسية مُدخلة.")
    elif bad:
        add("organism_antibiotics", "نوع البكتيريا ↔ المضادات المختبَرة", FAIL,
            "نتيجة S/I لمضاد مقاوم جوهرياً لهذا الكائن: " + "، ".join(bad)
            + " — خطأ تعريف أو خطأ اختبار. (البرنامج لم يوصِ بها.)")
    else:
        add("organism_antibiotics", "نوع البكتيريا ↔ المضادات المختبَرة", PASS,
            f"{len(sir_map)} مضاد مختبَر — لا نتيجة تتعارض مع المقاومة الجوهرية.")

    # 4 ── nothing resistant / intrinsic is recommended (self-check) ──────────
    rec = [_name(x) for x in allowed + warned + preg_warn]
    leak = sorted(d for d in rec if sir_map.get(d) == "R" or d in intrinsic)
    if leak:
        add("recommendation_safety", "التوصيات لا تحتوي مضاداً مقاوماً", FAIL,
            "خطأ داخلي — مضاد مقاوم أو مقاوم جوهرياً ضمن التوصيات: " + "، ".join(leak))
    else:
        add("recommendation_safety", "التوصيات لا تحتوي مضاداً مقاوماً", PASS,
            f"{len(rec)} مضاد في التوصيات — كلها S/I وغير مقاومة جوهرياً.")

    # 5 ── specimen ↔ antibiotics (site penetration) ──────────────────────────
    try:
        import clinical_matrix as CM
        site_bad = []
        for d in [_name(x) for x in allowed + preg_warn]:
            row = CM.SITE_PENETRATION.get(d, {})
            lvl = (row.get(site) or (CM.ALLOW,))[0] if site else CM.ALLOW
            if lvl == CM.DENY:
                site_bad.append(d)
        n_site = sum(1 for b in banned if isinstance(b, dict)
                     and str(b.get("category", "")) in ("specimen", "safety_gate", "uti_upper"))
        if site_bad:
            add("specimen_antibiotics", "نوع العينة ↔ المضادات الموصى بها", FAIL,
                "مضاد لا يصل لموقع العدوى ضمن المسموح: " + "، ".join(sorted(site_bad)))
        else:
            add("specimen_antibiotics", "نوع العينة ↔ المضادات الموصى بها", PASS,
                f"كل المضادات المسموحة مناسبة لموقع العدوى ({n_site} استُبعد لعدم الملاءمة).")
    except Exception:
        add("specimen_antibiotics", "نوع العينة ↔ المضادات الموصى بها", WARN,
            "تعذّر التحقق من ملاءمة الموقع.")

    # 6 ── AST quality control ────────────────────────────────────────────────
    errs = [i for i in (qc_issues or []) if i.get("severity") == "error"]
    wrns = [i for i in (qc_issues or []) if i.get("severity") != "error"]
    if errs:
        add("ast_qc", "مراجعة جودة نتائج الحساسية (AST-QC)", FAIL,
            f"{len(errs)} خطأ و{len(wrns)} تحذير — راجع قسم AST Quality Control قبل الإصدار.")
    elif wrns:
        add("ast_qc", "مراجعة جودة نتائج الحساسية (AST-QC)", WARN,
            f"{len(wrns)} تحذير — راجع قسم AST Quality Control.")
    else:
        add("ast_qc", "مراجعة جودة نتائج الحساسية (AST-QC)", PASS, "لا أخطاء ولا تحذيرات.")

    # 7 ── panel completeness ─────────────────────────────────────────────────
    st_pc = getattr(panel_result, "status", None)
    miss = list(getattr(panel_result, "missing_primary", []) or [])
    if st_pc in (None, "not_evaluated"):
        add("panel", "اكتمال لوحة المضادات", NA, "لا توجد لوحة معيارية لهذا الكائن.")
    elif st_pc == "critical":
        add("panel", "اكتمال لوحة المضادات", FAIL,
            "كل المضادات الأساسية المختبَرة مقاومة، وفيه أساسي لم يُختبر: " + "، ".join(miss))
    elif miss:
        add("panel", "اكتمال لوحة المضادات", WARN, "مضادات أساسية لم تُختبر: " + "، ".join(miss))
    else:
        add("panel", "اكتمال لوحة المضادات", PASS, "كل المضادات الأساسية المتوقعة مختبَرة.")

    # 8 ── at least one option exists ─────────────────────────────────────────
    if allowed:
        add("options", "وجود خيار علاجي", PASS,
            f"{len(allowed)} خيار مسموح و{len(warned) + len(preg_warn)} بحذر.")
    elif warned or preg_warn:
        add("options", "وجود خيار علاجي", WARN,
            f"لا يوجد خيار بلا تحفظ — {len(warned) + len(preg_warn)} خيار بحذر فقط"
            + (" (منها حمل)." if preg_warn else "."))
    else:
        add("options", "وجود خيار علاجي", FAIL,
            "لا يوجد أي خيار علاجي من اللوحة المختبَرة — استشارة أمراض معدية واختبار مضادات إضافية.")

    # 9 ── identification level ───────────────────────────────────────────────
    ol = str(organism or "").lower()
    if "unidentified" in ol or "unspeciated" in ol:
        add("identification", "مستوى تعريف البكتيريا", WARN,
            "الكائن معرّف بصبغة Gram أو المجموعة فقط — التوصيات مبدئية حتى التعريف.")
    elif "spp" in ol and not any(k in ol for k in ("klebsiella", "salmonella", "shigella",
                                                   "providencia", "mycoplasma")):
        add("identification", "مستوى تعريف البكتيريا", WARN,
            "الكائن معرّف على مستوى الجنس فقط — عومل كأكثر الأنواع مقاومة.")
    else:
        add("identification", "مستوى تعريف البكتيريا", PASS, "الكائن معرّف.")

    # 10 ── pathogenicity assessment ──────────────────────────────────────────
    if not patho_result:
        add("pathogenicity", "تقييم الـ Pathogenicity", NA,
            "لم يُحسب — العلاج يفترض أن العزلة ممرضة.")
    else:
        cat = patho_result.get("category", "")
        flags = patho_result.get("special_flags", [])
        verdict = str(patho_result.get("verdict", ""))
        if cat == "INSUFFICIENT_DATA":
            add("pathogenicity", "تقييم الـ Pathogenicity", WARN, "بيانات غير كافية للتقييم.")
        elif "GRAM_DISCORDANT" in flags:
            add("pathogenicity", "تقييم الـ Pathogenicity", WARN, verdict + " — مع تعارض صبغة/مزرعة.")
        elif cat in ("ASB_NO_TREAT", "COLONISATION", "CONTAMINANT_OR_COLONISER",
                     "LIKELY_CONTAMINANT", "SPECIMEN_REJECT",
                     "POSSIBLE_CONTAMINANT_STERILE_SITE"):
            add("pathogenicity", "تقييم الـ Pathogenicity", WARN,
                verdict + " — التقييم لا يدعم العلاج؛ قائمة المضادات للعلم فقط.")
        else:
            add("pathogenicity", "تقييم الـ Pathogenicity", PASS, verdict)
    return out


def summarize(items: List[Dict[str, str]]) -> Dict[str, Any]:
    n = {s: sum(1 for i in items if i["status"] == s) for s in (PASS, WARN, FAIL, NA)}
    overall = FAIL if n[FAIL] else WARN if n[WARN] else PASS
    return {"counts": n, "overall": overall}
