# modules/mdr.py
# © Dr. Hussein Ali — Orange Lab
# MDR/XDR/PDR Classification + ESBL Prediction
# المرجع: CLSI M100 2026, EUCAST 2026, WHO 2022

from __future__ import annotations
from typing import Any, Dict
from data.antibiotics import ABX_GUIDELINES, normalize_abx_key

def classify_mdr(organism: str, sir_map: Dict[str, str]) -> Dict[str, Any]:
    if not sir_map:
        return {"level": None, "resistant_categories": [], "total_tested": 0}
    resistant_cats   = []
    susceptible_cats = []
    for cat, drugs in MDR_CATEGORIES.items():
        tested = [d for d in drugs if d in sir_map]
        if not tested:
            continue
        if any(sir_map.get(d) == "R" for d in tested):
            resistant_cats.append(cat)
        else:
            susceptible_cats.append(cat)
    total_cats = len(resistant_cats) + len(susceptible_cats)
    r_count    = len(resistant_cats)
    if total_cats == 0:
        return {"level": None, "resistant_categories": [], "total_tested": 0}
    if r_count >= total_cats:
        level = "PDR"
    elif total_cats - r_count <= 2 and r_count > 0:
        level = "XDR"
    elif r_count >= 3:
        level = "MDR"
    else:
        level = None
    return {
        "level":                  level,
        "resistant_categories":   resistant_cats,
        "susceptible_categories": susceptible_cats,
        "total_tested":           total_cats,
        "resistant_count":        r_count,
    }

# =========================================================
# ESBL Predictor
# =========================================================
ESBL_PRODUCERS = [
    "Klebsiella spp.","E. coli","Proteus mirabilis",
    "Klebsiella pneumoniae","Enterobacter cloacae",
]
ESBL_MARKERS = {
    "high":   ["Ceftriaxone","Cefotaxime","Ceftazidime","Cefepime"],
    "medium": ["Cefuroxime","Cefixime","Cefaclor","Cephalexin"],
}

def predict_esbl(organism: str, sir_map: Dict[str, str]) -> Dict[str, Any]:
    if not sir_map:
        return {"probability": None}
    is_producer = any(p.lower() in organism.lower() for p in ESBL_PRODUCERS)
    if not is_producer:
        return {"probability": None}
    high_R = [d for d in ESBL_MARKERS["high"]   if sir_map.get(d) == "R"]
    med_R  = [d for d in ESBL_MARKERS["medium"] if sir_map.get(d) == "R"]
    carb_R = any(sir_map.get(d) == "R"
                 for d in ["Imipenem/Cilastatin","Meropenem","Ertapenem"])
    if carb_R and len(high_R) >= 2:
        return {
            "probability": "carbapenemase",
            "markers_R":   high_R,
            "detail":      "نمط يُشير لإنزيم Carbapenemase (KPC/MBL/OXA). تحقق فوراً.",
            "action":      "أرسل للمختبر المرجعي. ارفع بروتوكول العزل.",
        }
    elif len(high_R) >= 2:
        return {
            "probability": "high",
            "markers_R":   high_R,
            "detail":      f"مقاومة لـ {', '.join(high_R)} — احتمال ESBL مرتفع.",
            "action":      "استخدم Carbapenems للعدوى الشديدة. تجنب Cephalosporins.",
        }
    elif len(high_R) == 1 or len(med_R) >= 2:
        return {
            "probability": "moderate",
            "markers_R":   high_R + med_R,
            "detail":      "نمط مقاومة يستدعي إجراء تأكيد ESBL.",
            "action":      "أجرِ Double Disk Synergy Test أو PCR للتأكيد.",
        }
    return {"probability": "low"}

