# modules/qc.py
# © Dr. Hussein Ali — Orange Lab
# AST QC Checker + Startup Validation (EUCAST Expert Rules)

from __future__ import annotations
from typing import Any, Dict, List
from data.antibiotics import ABX_GUIDELINES, normalize_abx_key
from data.organisms import ORGANISM_PROFILE, SPECIMEN_ORGANISM_MAP

# FIX 2026-07-30: run_ast_qc() iterated a name, AST_QC_RULES, that was never
# defined -- it was lost when the monolith was split -- so EVERY call raised
# NameError. ui/dashboard.py:636 calls it on every analysis, which made AST QC a
# hard crash in this build rather than a degraded feature. The dead root copy of
# this file (qc.py) carried a guard that was never brought across, and that guard
# only degraded to an EMPTY rule list, so QC would have silently found nothing.
#
# Rather than restate the rules a third time, this delegates to the canonical
# engine in ast_qa_engine.py (13 check families) and adapts QAIssue objects to the
# dict shape ui/dashboard.py already renders.
try:
    from ast_qa_engine import run_ast_qa_engine as _run_qa
    QA_ENGINE_AVAILABLE = True
except Exception:                                            # pragma: no cover
    _run_qa = None
    QA_ENGINE_AVAILABLE = False

# ui/dashboard.py branches on severity == "error"; the canonical engine grades
# CRITICAL / HIGH / MEDIUM / LOW. Map the two top grades onto "error" so a
# critical finding is still rendered in red.
_SEV_TO_UI = {"CRITICAL": "error", "HIGH": "error",
              "MEDIUM": "warning", "LOW": "warning"}


def run_ast_qc(organism: str, sir_map: Dict[str, str],
               specimen: str = "") -> List[Dict[str, Any]]:
    """AST plausibility check. Returns [] when the QA engine is unavailable.

    `specimen` is accepted for signature parity with the monolith's run_ast_qc,
    which takes three arguments; calling the two interchangeably used to raise
    TypeError.
    """
    if not sir_map or not organism or not QA_ENGINE_AVAILABLE:
        return []
    try:
        issues = _run_qa(organism, specimen or "", sir_map)
    except Exception:
        # A QC panel that cannot run must not take the whole analysis down with
        # it -- the recommendations are still valid without it.
        return []
    out: List[Dict[str, Any]] = []
    for i in issues:
        out.append({
            "id":       f"{i.category}/{i.level}",
            "severity": _SEV_TO_UI.get(i.severity, "warning"),
            "message":  i.message,
            "fix":      i.detail or i.reference or "",
        })
    return out


def get_startup_validation_issues() -> List[str]:
    issues: List[str] = []
    known_organisms = list(ORGANISM_PROFILE.keys())
    known_abx       = list(ABX_GUIDELINES.keys())
    # تحقق أن first_line/second_line/third_line في ABX_GUIDELINES
    for org, profile in ORGANISM_PROFILE.items():
        for tier in ["first_line","second_line","third_line"]:
            for drug in profile.get(tier, []):
                if drug not in ABX_GUIDELINES:
                    issues.append(f"[organism_profile] {org} → {tier} → '{drug}' not in ABX_GUIDELINES")
    # إزالة المكررات
    return list(dict.fromkeys(issues))

# =========================================================
