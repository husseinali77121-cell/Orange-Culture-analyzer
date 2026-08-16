# -*- coding: utf-8 -*-
# © 2025 Dr / Hussein Ali — Orange Lab, 6 October City, Egypt
# Microbiology CDSS — All Rights Reserved
"""safety_gate.py — بوابة الأمان النهائية / terminal safety gate.

WHY A GATE AND NOT A REWRITE
----------------------------
`analyze_antibiotics` is ~520 lines of interleaved rules inside a 7,800-line
file. Re-plumbing it to consult a new layer touches every branch and risks
breaking the 803-scenario snapshot that currently passes. A terminal gate is
the safer shape: the existing engine keeps producing its three buckets, and the
gate re-examines each bucket against `clinical_matrix` before anything reaches
the physician.

The gate obeys one rule, deliberately asymmetric:

    IT MAY ONLY DEMOTE. Allowed -> Caution -> Avoid.
    IT MAY NEVER PROMOTE.

So the gate can add safety but can never undo a ban the engine already applied.
That property is machine-checked in `test_clinical_matrix.py::test_gate_never_promotes`
and it is what makes the gate safe to deploy on a live system: the worst thing
a bug in this file can do is make the CDSS more conservative.

USAGE — three lines in streamlit_app.py
---------------------------------------
    from safety_gate import apply_safety_gate

    allowed, warned, banned, preg, inter = analyze_antibiotics(...)
    allowed, warned, banned, gate_report = apply_safety_gate(
        allowed, warned, banned,
        organism=organism_type, specimen=culture_type, sir_map=sir_map,
        age_years=age, age_months=age_months, is_pregnant=is_preg, cl_cr=cl_cr,
        is_renal=is_renal, is_hepatic=is_hepatic)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from clinical_matrix import (
    ALLOW, CAUTION, DENY, MATRIX_VERSION, Verdict, canonical_organism,
    canonical_site, evaluate,
)

logger = logging.getLogger("orange_cdss.safety_gate")

__all__ = ["apply_safety_gate", "gate_summary_lines", "GATE_VERSION"]

GATE_VERSION = "1.0.0"



def _name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name") or item.get("drug") or "")
    return str(item)


def _reason_block(v: Verdict, lang: str = "ar") -> str:
    """Render the blocking/cautioning reasons as one readable string."""
    parts: List[str] = []
    for r in v.reasons:
        txt = r.get(lang) or r.get("en") or ""
        if not txt:
            continue
        tag = {"site": "الموقع", "intrinsic": "مقاومة جوهرية", "pregnancy": "حمل",
               "renal": "كلوي", "hepatic": "كبدي", "paediatric": "أطفال",
               "neonate": "حديثي الولادة", "culture": "المزرعة",
               "specimen-organism": "العينة/الكائن", "lactation": "رضاعة",
               "vocabulary": "خارج الدليل"}.get(r["layer"], r["layer"]) if lang == "ar" else r["layer"]
        parts.append(f"[{tag}] {txt}")
    return " · ".join(parts)


def apply_safety_gate(
    allowed: List[Any],
    warned: List[Any],
    banned: List[Any],
    *,
    organism: Optional[str] = None,
    specimen: Optional[str] = None,
    sir_map: Optional[Dict[str, str]] = None,
    age_years: Optional[float] = None,
    age_months: Optional[float] = None,
    is_pregnant: bool = False,
    is_lactating: bool = False,
    cl_cr: Optional[float] = None,
    is_renal: bool = False,
    is_hepatic: bool = False,
    child_pugh: Optional[str] = None,
    enabled: bool = True,
) -> Tuple[List[Any], List[Any], List[Any], Dict[str, Any]]:
    """Re-examine three buckets through the clinical matrix. Demote-only.

    Returns (allowed, warned, banned, report). `report` records every movement
    so the change is auditable rather than invisible.
    """
    report: Dict[str, Any] = {
        "gate_version": GATE_VERSION, "matrix_version": MATRIX_VERSION,
        "enabled": enabled, "moves": [], "site": canonical_site(specimen),
        "organism": canonical_organism(organism), "specimen_recognised": bool(canonical_site(specimen)),
        "organism_recognised": bool(canonical_organism(organism)),
    }
    if not enabled:
        return allowed, warned, banned, report

    sir_map = sir_map or {}

    # ── Age resolution ────────────────────────────────────────────────────────
    # DEFECT 2026-08-03: this gate received `age_years` only, and the caller
    # passes the UI's INTEGER year field — which is 0 for every infant from
    # birth to eleven months. clinical_matrix.NEONATE_MAX_YEARS is correctly
    # 28/365, but `0 <= 0.0767` is True, so a six-month-old was evaluated as a
    # NEONATE and NEONATAL_DENY banned Ceftriaxone at every site — in blood, in
    # urine, and in CSF. Ceftriaxone is the first-line agent for infant
    # bacteraemia and for infant bacterial meningitis beyond the neonatal
    # period (AAP Red Book / IDSA), so the gate was removing the drug of choice
    # from the patients who need it most.
    #
    # analyze_antibiotics() had this right all along: NEONATAL_RESTRICTIONS is
    # expressed in MONTHS and bans ceftriaxone below one month only. The gate
    # simply had no parameter through which months could reach it.
    #
    # Months win when supplied — they are the more precise measurement, and
    # carrying them here is the entire purpose of the "أقل من سنة" field.
    # Resolution lives in clinical_utils.resolve_age_years — the same helper
    # get_combination_therapy uses, so the two cannot grow different ideas of
    # what "six months old" means. Each had its own copy before 2026-08-03.
    from clinical_utils import resolve_age_years as _resolve_age
    _eff_age = _resolve_age(age_years, age_months)
    report["age_years_effective"] = _eff_age

    host = dict(age_years=_eff_age, is_pregnant=is_pregnant, is_lactating=is_lactating,
                cl_cr=cl_cr, is_renal=is_renal, is_hepatic=is_hepatic,
                child_pugh=child_pugh)

    new_allowed: List[Any] = []
    new_warned: List[Any] = list(warned)
    new_banned: List[Any] = list(banned)

    # ---- pass 1: Allowed may fall to Warned or Banned --------------------
    for item in allowed:
        drug = _name(item)
        if not drug:
            new_allowed.append(item)
            continue
        try:
            # `sir` is intentionally NOT passed here: the engine has already
            # applied the culture result, and re-applying it would let the gate
            # re-derive a ban the engine deliberately handled (e.g. the ESBL
            # report-as-tested carve-out). The gate adds only the layers the
            # engine lacks.
            v = evaluate(drug, organism, specimen, strict_unknown=False, **host)
        except Exception as exc:                      # never break the report
            logger.warning("safety_gate failed on %s: %s", drug, exc, exc_info=True)
            new_allowed.append(item)
            continue

        if v.level == DENY:
            enriched = dict(item) if isinstance(item, dict) else {"name": drug}
            enriched.update({
                "gate_blocked": True,
                "reason_short": "غير مناسب لموقع العدوى أو لحالة المريض.",
                "reason_detail": _reason_block(v, "ar"),
                "reason_detail_en": _reason_block(v, "en"),
                "gate_layers": sorted({r["layer"] for r in v.blocking}),
                "category": "safety_gate",
            })
            new_banned.append(enriched)
            report["moves"].append({"drug": drug, "from": "allowed", "to": "banned",
                                    "layers": enriched["gate_layers"],
                                    "why": _reason_block(v, "en"),
                                    # FIX 2026-08-01: the consumer in
                                    # streamlit_app.py reads reason_ar /
                                    # reason and fell through to '' on
                                    # every single move, because the only
                                    # key emitted here was "why". Emit all
                                    # three: "why" stays for any existing
                                    # caller, reason_ar/_en are what the UI
                                    # asks for and what a bilingual report
                                    # needs.
                                    "reason_ar": _reason_block(v, "ar"),
                                    "reason_en": _reason_block(v, "en")})
        elif v.level == CAUTION:
            enriched = dict(item) if isinstance(item, dict) else {"name": drug}
            enriched.update({
                "gate_caution": True,
                "warning_reason": "safety_gate",
                "gate_note": _reason_block(v, "ar"),
                "gate_note_en": _reason_block(v, "en"),
                "gate_layers": sorted({r["layer"] for r in v.cautions}),
            })
            new_warned.append(enriched)
            report["moves"].append({"drug": drug, "from": "allowed", "to": "warned",
                                    "layers": enriched["gate_layers"],
                                    "why": _reason_block(v, "en"),
                                    # FIX 2026-08-01: the consumer in
                                    # streamlit_app.py reads reason_ar /
                                    # reason and fell through to '' on
                                    # every single move, because the only
                                    # key emitted here was "why". Emit all
                                    # three: "why" stays for any existing
                                    # caller, reason_ar/_en are what the UI
                                    # asks for and what a bilingual report
                                    # needs.
                                    "reason_ar": _reason_block(v, "ar"),
                                    "reason_en": _reason_block(v, "en")})
        else:
            new_allowed.append(item)

    # ---- pass 2: Warned may fall to Banned (never rise) ------------------
    promoted_out: List[Any] = []
    for item in list(new_warned):
        drug = _name(item)
        if not drug or any(_name(b) == drug for b in new_banned):
            continue
        try:
            v = evaluate(drug, organism, specimen, strict_unknown=False, **host)
        except Exception:
            continue
        if v.level == DENY:
            enriched = dict(item) if isinstance(item, dict) else {"name": drug}
            enriched.update({
                "gate_blocked": True,
                "reason_short": "غير مناسب لموقع العدوى أو لحالة المريض.",
                "reason_detail": _reason_block(v, "ar"),
                "reason_detail_en": _reason_block(v, "en"),
                "gate_layers": sorted({r["layer"] for r in v.blocking}),
                "category": "safety_gate",
            })
            new_banned.append(enriched)
            promoted_out.append(item)
            report["moves"].append({"drug": drug, "from": "warned", "to": "banned",
                                    "layers": enriched["gate_layers"],
                                    "why": _reason_block(v, "en"),
                                    # FIX 2026-08-01: the consumer in
                                    # streamlit_app.py reads reason_ar /
                                    # reason and fell through to '' on
                                    # every single move, because the only
                                    # key emitted here was "why". Emit all
                                    # three: "why" stays for any existing
                                    # caller, reason_ar/_en are what the UI
                                    # asks for and what a bilingual report
                                    # needs.
                                    "reason_ar": _reason_block(v, "ar"),
                                    "reason_en": _reason_block(v, "en")})
    for it in promoted_out:
        try:
            new_warned.remove(it)
        except ValueError:
            pass

    # ---- de-duplicate: a drug must live in exactly one bucket ------------
    banned_names = {_name(b) for b in new_banned}
    new_warned = [w for w in new_warned if _name(w) not in banned_names]
    warned_names = {_name(w) for w in new_warned}
    new_allowed = [a for a in new_allowed
                   if _name(a) not in banned_names and _name(a) not in warned_names]

    report["counts"] = {"allowed": len(new_allowed), "warned": len(new_warned),
                        "banned": len(new_banned), "moved": len(report["moves"])}
    return new_allowed, new_warned, new_banned, report


def gate_summary_lines(report: Dict[str, Any], lang: str = "ar") -> List[str]:
    """Human-readable summary for the UI / PDF. Empty when the gate changed nothing."""
    moves = report.get("moves") or []
    lines: List[str] = []
    if not report.get("specimen_recognised"):
        lines.append("⚠️ نوع العينة غير معروف للنظام — لم يتم التحقق من ملاءمة موقع العدوى."
                     if lang == "ar" else
                     "⚠️ Specimen type not recognised — site-appropriateness was NOT verified.")
    for m in moves:
        arrow = "🚫" if m["to"] == "banned" else "⚠️"
        lines.append(f"{arrow} {m['drug']} — {m['why']}")
    return lines
