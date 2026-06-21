# data/phenotypes.py
# © Dr. Hussein Ali — Orange Lab
# قواعد الفينوتايبات المقاومة: MRSA, VRE, CRE, CRAB, CRPA, ESBL

from __future__ import annotations
from typing import Dict, List, Any

PHENOTYPE_RULES = {
    "MRSA": {
        "organisms": ["Staphylococcus aureus","MRSA"],
        "markers":   [("Cefoxitin","R"),("Oxacillin","R")],
        "require_any": 1,
        "icon": "🔴", "label": "MRSA — Methicillin-Resistant S. aureus",
        "detail": "مقاوم للـ Methicillin (mecA gene). جميع البيتا-لاكتام غير فعالة.",
        "action": "Vancomycin أو Linezolid. بروتوكول عزل إلزامي.",
        "isolation": True,
    },
    "VRE": {
        "organisms": ["Enterococcus faecalis","Enterococcus faecium","VRE"],
        "markers":   [("Vancomycin","R")],
        "require_any": 1,
        "icon": "🔴", "label": "VRE — Vancomycin-Resistant Enterococcus",
        "detail": "مقاوم للـ Vancomycin (vanA/vanB gene).",
        "action": "Linezolid. عزل فوري. إبلاغ مكافحة العدوى.",
        "isolation": True,
    },
    "CRE": {
        "organisms": ["Klebsiella spp.","E. coli","Proteus mirabilis","Enterobacter cloacae"],
        "markers":   [("Imipenem/Cilastatin","R"),("Meropenem","R"),("Ertapenem","R")],
        "require_any": 1,
        "icon": "🚨", "label": "CRE — Carbapenem-Resistant Enterobacteriaceae",
        "detail": "مقاوم للكاربابينيم — أخطر أنماط المقاومة.",
        "action": "Colistin + Fosfomycin. أرسل للمختبر المرجعي فوراً.",
        "isolation": True,
    },
    "CRAB": {
        "organisms": ["Acinetobacter baumannii"],
        "markers":   [("Imipenem/Cilastatin","R"),("Meropenem","R")],
        "require_any": 1,
        "icon": "🚨", "label": "CRAB — Carbapenem-Resistant Acinetobacter baumannii",
        "detail": "XDR/PDR Acinetobacter — أصعب الكائنات علاجاً في ICU.",
        "action": "Colistin ± Rifampicin. استشارة معدية.",
        "isolation": True,
    },
    "CRPA": {
        "organisms": ["Pseudomonas aeruginosa"],
        "markers":   [("Imipenem/Cilastatin","R"),("Meropenem","R"),
                      ("Piperacillin + Tazobactam","R"),("Ceftazidime","R")],
        "require_any": 2,
        "icon": "🔴", "label": "CRPA — Carbapenem-Resistant Pseudomonas aeruginosa",
        "detail": "مقاوم للكاربابينيم مع مقاومة متعددة.",
        "action": "Colistin أو Ceftolozane-Tazobactam. Combination therapy.",
        "isolation": True,
    },
}

def detect_resistance_phenotypes(organism: str, sir_map: Dict[str, str]) -> List[Dict[str, Any]]:
    if not sir_map:
        return []
    detected = []
    org_lower = organism.lower()
    for ph_name, rule in PHENOTYPE_RULES.items():
        if not any(o.lower() in org_lower or org_lower in o.lower() for o in rule["organisms"]):
            continue
        req_any = rule.get("require_any", len(rule["markers"]))
        matched = sum(1 for drug, exp in rule["markers"] if sir_map.get(drug) == exp)
        if matched >= req_any and matched > 0:
            detected.append({"phenotype": ph_name, "icon": rule["icon"],
                "label": rule["label"], "detail": rule["detail"],
                "action": rule["action"], "isolation": rule.get("isolation", False),
                "matched_markers": [d for d, e in rule["markers"] if sir_map.get(d) == e],})
    if "staphylococcus aureus" in org_lower and "MRSA" not in [d["phenotype"] for d in detected]:
        beta_r = any(sir_map.get(d) == "R" for d in
                     ["Amoxicillin + Clavulanic acid","Cephalexin","Cefazolin","Ampicillin"])
        if beta_r and sir_map.get("Vancomycin") == "S":
            detected.append({"phenotype": "Possible MRSA", "icon": "⚠️",
                "label": "Possible MRSA — تأكيد مطلوب",
                "detail": "نمط مقاومة beta-lactam مع حساسية Vancomycin يشير لـ MRSA.",
                "action": "أجرِ Cefoxitin disk diffusion أو PCR (mecA) للتأكيد.",
                "isolation": False, "matched_markers": [],})
    return detected

