# modules/analyzer.py
# © Dr. Hussein Ali — Orange Lab
# محرك تحليل المضادات الحيوية — AWaRe Ranking + Analyzer + Renal + Syndromes

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from data.antibiotics import (
    ABX_GUIDELINES, ABX_ALIAS_INDEX, normalize_abx_key,
    AWARE_COLORS, get_commercial_name,
)
from data.organisms import ORGANISM_PROFILE, SPECIMEN_ORGANISM_MAP
from data.phenotypes import PHENOTYPE_RULES, detect_resistance_phenotypes

def rank_sensitive_antibiotics(allowed: List[Dict], culture_type: str,
                               organism: str, sir_map: Dict[str, str],
                               phenotypes: List[Dict]) -> List[Dict]:
    ph_names = [p["phenotype"] for p in phenotypes]
    scored = []
    for item in allowed:
        score = 0
        sir = sir_map.get(item.get("name",""))
        score += 4 if sir=="S" else (1 if sir=="I" else 0)
        score += {"Access":3,"Watch":2,"Reserve":1}.get(item.get("aware"),0)
        score += 2 if item.get("high_po") else 1
        score += 2 if (item.get("specimen_notes") or {}).get(culture_type) else 0
        score += max(0, 6 - item.get("priority",5))
        if any(ph in ph_names for ph in ["CRE","CRAB"]):
            if "cephalosporin" in item.get("class","").lower() and sir != "S":
                score -= 3
        scored.append({**item, "_score": score, "_sir": sir or "—"})
    return sorted(scored, key=lambda x: x["_score"], reverse=True)

# =========================================================
# MODULE 4 — Infection Syndrome Module
# =========================================================
INFECTION_SYNDROMES = {
    "Urine":{"syndrome":"Urinary Tract Infection (UTI)",
             "sub":lambda a,p,c:"Complicated UTI" if c or a>65 else "Pregnancy UTI" if p else "Uncomplicated UTI",
             "first":["Nitrofurantoin","Fosfomycin","Trimethoprim/Sulfamethoxazole"],
             "dur":{"Uncomplicated UTI":"3-5 أيام","Complicated UTI":"7-14 يوم","Pregnancy UTI":"7 أيام"},
             "esc":"فشل الخط الأول → Ciprofloxacin أو Cefixime","thr":"≥ 10⁵ CFU/mL"},
    "Blood":{"syndrome":"Bloodstream Infection (BSI)",
             "sub":lambda a,p,c:"CRBSI" if c else "Community/Hospital BSI",
             "first":["Ceftriaxone","Amoxicillin + Clavulanic acid"],
             "dur":{"CRBSI":"14 يوم + إزالة الكاتيتر","Community/Hospital BSI":"14-21 يوم"},
             "esc":"MDR → Meropenem ± Amikacin","thr":"2 sets blood cultures قبل المضاد"},
    "Sputum":{"syndrome":"Respiratory Tract Infection",
              "sub":lambda a,p,c:"HAP/VAP" if c else "CAP",
              "first":["Amoxicillin + Clavulanic acid","Levofloxacin","Azithromycin"],
              "dur":{"CAP":"5-7 أيام","HAP/VAP":"7-14 يوم"},
              "esc":"Pseudomonas/Acinetobacter → anti-pseudomonal إلزامي","thr":"≥ 10⁶ CFU/mL"},
    "Wound Swab":{"syndrome":"Skin & Soft Tissue Infection (SSTI)",
                  "sub":lambda a,p,c:"SSTI",
                  "first":["Cephalexin","Amoxicillin + Clavulanic acid"],
                  "dur":{"SSTI":"5-10 أيام"},"esc":"MRSA اشتباه → TMP/SMX أو Doxycycline",
                  "thr":"عينة من العمق — لا من السطح"},
    "Pus":{"syndrome":"Abscess / Deep Infection",
           "sub":lambda a,p,c:"Abscess",
           "first":["Amoxicillin + Clavulanic acid","Metronidazole"],
           "dur":{"Abscess":"Drainage + 5-7 أيام"},
           "esc":"Intra-abdominal → Metronidazole إلزامي","thr":"Drainage culture — أدق من swab"},
    "Stool":{"syndrome":"Gastrointestinal Infection",
             "sub":lambda a,p,c:"GI Infection",
             "first":["Azithromycin","Ciprofloxacin"],
             "dur":{"GI Infection":"3-5 أيام للحالات الشديدة"},
             "esc":"معظم الحالات لا تحتاج مضاد","thr":"Culture للحالات الشديدة فقط"},
    "CSF":{"syndrome":"CNS Infection (Meningitis)",
           "sub":lambda a,p,c:"Bacterial Meningitis",
           "first":["Ceftriaxone","Meropenem"],
           "dur":{"Bacterial Meningitis":"10-14 يوم"},
           "esc":"ابدأ تجريبياً فوراً. Dexamethasone قبل المضاد",
           "thr":"CSF culture + Gram stain"},
}

def get_infection_syndrome(specimen: str, organism: str, age: int,
                           is_preg: bool, is_cath: bool=False) -> Optional[Dict]:
    data = INFECTION_SYNDROMES.get(specimen)
    if not data:
        return None
    sub_type = data["sub"](age, is_preg, is_cath)
    return {"syndrome":data["syndrome"],"sub_type":sub_type,
            "first_choice":data["first"],"duration":data["dur"].get(sub_type,"حسب الاستجابة"),
            "escalation":data["esc"],"threshold":data["thr"]}


def calc_creatinine_clearance(age: int, weight: float, scr: float, sex: str) -> float:
    if scr <= 0:
        return 0.0
    crcl = ((140 - age) * weight) / (72 * scr)
    if sex == "Female":
        crcl *= 0.85
    return crcl

def get_renal_severity(crcl: float) -> str:
    if crcl >= 60:
        return "Mild"
    if crcl >= 30:
        return "Moderate"
    return "Severe"

def get_route_label(item: Dict[str, Any]) -> str:
    return "🟢 Oral preferred / PO-friendly" if item.get("high_po") else "💉 IV/IM only"

def uniq_keep_order(items: List[str]) -> List[str]:
    seen:   set       = set()
    result: List[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            result.append(x)
    return result

def best_default_index(options: List[str], preferred: Optional[str]) -> int:
    if preferred and preferred in options:
        return options.index(preferred)
    return 0


def is_intrinsically_avoided(organism_type: str, drug_name: str, drug_info: Dict[str, Any]) -> bool:
    organism_avoid = (ORGANISM_PROFILE.get(organism_type) or {}).get("avoid", [])
    d_low   = drug_name.lower()
    d_class = drug_info.get("class", "").lower()
    for avoid_item in organism_avoid:
        av_low = avoid_item.lower().strip()
        if av_low in d_low or d_low in av_low:
            return True
        mapped = ORGANISM_AVOID_CLASS_MAP.get(av_low)
        if mapped and any(cls in d_class for cls in mapped):
            return True
    return False

def build_banned_item(name: str, category: str, reason_short: str, reason_detail: str) -> Dict[str, str]:
    return {"name": name, "category": category,
            "reason_short": reason_short, "reason_detail": reason_detail}

def analyze_antibiotics(
    final_drugs:   List[str],
    organism_type: str,
    culture_type:  str,
    age:           int,
    sex:           str,
    is_renal:      bool,
    cl_cr:         float,
    is_preg:       bool,
    is_hepatic:    bool,
    current_meds:  List[str],
    sir_map:       Dict[str, str],
) -> Tuple[List[Dict], List[Dict], List[Dict], List[Dict], List[str]]:
    allowed:             List[Dict] = []
    warned:              List[Dict] = []
    banned:              List[Dict] = []
    preg_warn_items:     List[Dict] = []
    interactions_alerts: List[str]  = []

    for drug in final_drugs:
        if drug not in ABX_GUIDELINES:
            continue
        info           = ABX_GUIDELINES[drug]
        d_low          = drug.lower()
        cls            = info.get("class", "").lower()
        culture_result = sir_map.get(drug)

        if culture_result == "R":
            banned.append(build_banned_item(
                drug, "resistant", "مقاوم (R) في نتيجة المزرعة.",
                f"المزرعة أثبتت أن {drug} لا يثبط نمو الجرثومة. MIC أعلى من الحد العلاجي.",
            ))
            continue

        for med in current_meds:
            if med in info.get("interacts_with", []):
                interactions_alerts.append(f"⚡ تعارض: {drug} مع {med}")
        if is_hepatic and info.get("hepatic_caution"):
            interactions_alerts.append(f"🏥 تحذير كبدي: {drug} — يحتاج متابعة أو تعديل.")

        if is_intrinsically_avoided(organism_type, drug, info):
            banned.append(build_banned_item(
                drug, "organism",
                f"غير فعال لـ {organism_type} طبيعياً.",
                f"{drug} لديه مقاومة طبيعية أو عدم فعالية ضد {organism_type}.",
            ))
            continue

        if organism_type == "MRSA" and any(x in info.get("class", "") for x in ["Penicillin","Cephalosporin"]):
            banned.append(build_banned_item(
                drug, "organism", "بيتا-لاكتام — لا يعمل على MRSA.",
                "MRSA يحمل mecA / PBP2a مما يجعل البيتا-لاكتام غير فعالة.",
            ))
            continue

        if is_preg and info.get("preg_status") == "Banned":
            preg_note = info.get("preg_note") or "ممنوع في الحمل"
            banned.append(build_banned_item(
                drug, "pregnancy",
                preg_note.splitlines()[0] if preg_note.splitlines() else "ممنوع في الحمل",
                preg_note,
            ))
            continue

        if is_preg and info.get("preg_status") == "Warn":
            preg_warn_items.append({"name": drug, **info})

        if age < 18 and not info.get("child_safe", True):
            if "fluoroquinolone" in cls:
                banned.append(build_banned_item(
                    drug, "child", "غير مناسب < 18 سنة.", CHILD_BAN_REASONS["fluoroquinolone"]
                ))
                continue
            if "tetracycline" in cls and age < 8:
                banned.append(build_banned_item(
                    drug, "child", "غير مناسب < 8 سنوات.", CHILD_BAN_REASONS["tetracycline"]
                ))
                continue
            banned.append(build_banned_item(
                drug, "child", "غير مفضل للأطفال.",
                "يحتاج تقييم متخصص أو لا يُنصح به روتينياً لهذه الفئة العمرية.",
            ))
            continue

        if is_renal and "nitrofurantoin" in d_low and cl_cr < 30:
            banned.append(build_banned_item(
                drug, "renal",
                f"ممنوع — CrCl {cl_cr:.1f} < 30 ml/min",
                f"CrCl = {cl_cr:.1f} مل/د — أقل من الحد المطلوب.",
            ))
            continue

        renal_limit = info.get("renal_limit", 0)
        if is_renal and renal_limit > 0 and cl_cr <= renal_limit:
            warned.append({"name": drug, **info, "warning_reason": "renal_adjustment"})
            continue

        if culture_result == "I":
            warned.append({"name": drug, **info, "warning_reason": "intermediate_culture"})
            continue

        allowed.append({"name": drug, **info})

    allowed         = sorted(allowed,         key=lambda x: x.get("priority", 999))
    warned          = sorted(warned,          key=lambda x: x.get("priority", 999))
    preg_warn_items = sorted(preg_warn_items, key=lambda x: x.get("priority", 999))
    return allowed, warned, banned, preg_warn_items, sorted(set(interactions_alerts))

