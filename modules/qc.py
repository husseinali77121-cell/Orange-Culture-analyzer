# modules/qc.py
# © Dr. Hussein Ali — Orange Lab
# AST QC Checker + Startup Validation (EUCAST Expert Rules)

from __future__ import annotations
from typing import Any, Dict, List
from data.antibiotics import ABX_GUIDELINES, normalize_abx_key
from data.organisms import ORGANISM_PROFILE, SPECIMEN_ORGANISM_MAP

def run_ast_qc(organism: str, sir_map: Dict[str, str]) -> List[Dict[str, Any]]:
    if not sir_map:
        return []
    issues = []
    org_lower = organism.lower()
    for rule in AST_QC_RULES:
        if rule["organisms"]:
            if not any(o.lower() in org_lower or org_lower in o.lower() for o in rule["organisms"]):
                continue
        try:
            if rule["condition"](sir_map):
                issues.append({"id":rule["id"],"severity":rule["severity"],
                               "message":rule["message"],"fix":rule["fix"]})
        except Exception:
            continue
    return issues


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
