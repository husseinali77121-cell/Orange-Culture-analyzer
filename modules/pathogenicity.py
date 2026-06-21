# modules/pathogenicity.py
# © Dr. Hussein Ali — Orange Lab
# Pathogenicity Assessment Module v2
# Murray-Washington | SIRS | ABU | Pediatric thresholds

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional

def assess_pathogenicity(
    specimen: str,
    organism: str,
    colony_count_text: str,
    culture_purity: str,
    symptoms: list,
    pus_cells_text: str,
    urinalysis_result: str,
    gram_stain: str,
    age: int,
    sex: str,
    host_factors: list,
    # Sputum-specific
    sputum_pus_cells: str = "",
    sputum_epithelial: str = "",
    # Blood-specific (SIRS)
    sirs_criteria: list = None,
    blood_source: str = "",
    # Wound-specific
    wound_type: str = "",
) -> dict:
    """
    Pathogenicity Score Engine v2
    Returns: {score, verdict, color, interpretation, recommendations,
              factors_pos, factors_neg, abu_detected, special_flags}
    """
    if sirs_criteria is None:
        sirs_criteria = []

    score        = 0
    factors_pos  = []
    factors_neg  = []
    special_flags = []
    abu_detected  = False

    # ── Organism Lists ────────────────────────────────────────────────
    TYPICAL_UROPATHOGENS = [
        "Escherichia coli", "Klebsiella pneumoniae", "Klebsiella spp.",
        "Proteus mirabilis", "Proteus spp.", "Enterococcus faecalis",
        "Enterococcus spp.", "Staphylococcus saprophyticus",
        "Pseudomonas aeruginosa", "Enterobacter spp.", "Enterobacter cloacae",
        "Citrobacter spp.", "Morganella morganii", "Serratia marcescens",
    ]
    ATYPICAL_UROPATHOGENS = [
        "Staphylococcus aureus", "Staphylococcus epidermidis",
        "Streptococcus viridans", "Corynebacterium spp.",
        "Candida albicans", "Candida spp.",
    ]
    NORMAL_SKIN_FLORA = [
        "Staphylococcus epidermidis", "Corynebacterium spp.",
        "Streptococcus viridans",
    ]
    RESPIRATORY_PATHOGENS = [
        "Streptococcus pneumoniae", "Haemophilus influenzae",
        "Klebsiella pneumoniae", "Pseudomonas aeruginosa",
        "Staphylococcus aureus", "Moraxella catarrhalis",
        "Acinetobacter baumannii", "Enterobacter spp.",
        "Escherichia coli", "Serratia marcescens",
    ]
    URT_CONTAMINANTS_SPUTUM = [
        "Streptococcus viridans", "Neisseria spp.", "Candida spp.",
        "Candida albicans", "Staphylococcus epidermidis",
        "Corynebacterium spp.",
    ]
    TRUE_BLOOD_PATHOGENS = [
        "Staphylococcus aureus", "Streptococcus pneumoniae",
        "Escherichia coli", "Klebsiella pneumoniae", "Pseudomonas aeruginosa",
        "Acinetobacter baumannii", "Enterococcus faecalis", "Enterococcus spp.",
        "Candida albicans", "Candida spp.", "Salmonella spp.",
        "Neisseria meningitidis", "Listeria monocytogenes",
    ]
    BLOOD_CONTAMINANTS = [
        "Staphylococcus epidermidis", "Corynebacterium spp.",
        "Bacillus spp.", "Propionibacterium spp.", "Micrococcus spp.",
    ]

    spec_lower = specimen.lower()

    # ══════════════════════════════════════════════════════════════════
    # URINE
    # ══════════════════════════════════════════════════════════════════
    if "urine" in spec_lower:

        # Pediatric threshold: < 2 years → any growth significant
        if age < 2:
            score += 20
            factors_pos.append(f"✅ Infant < 2 yrs — any colony count clinically significant")
            special_flags.append("PEDIATRIC_UTI")

        # Organism context
        if organism in TYPICAL_UROPATHOGENS:
            score += 20
            factors_pos.append(f"✅ {organism} — typical uropathogen")
        elif organism in ATYPICAL_UROPATHOGENS:
            score -= 20
            factors_neg.append(f"⚠️ {organism} — atypical uropathogen; consider contamination or hematogenous seeding")
        else:
            score += 5
            factors_pos.append(f"➕ {organism} — occasional uropathogen")

        # Colony count
        cfu_val = _parse_cfu(colony_count_text)
        if age < 2:
            # Pediatric: ≥ 10⁴ = significant
            if cfu_val >= 10000:
                score += 20
                factors_pos.append(f"✅ Colony count ≥ 10⁴ CFU/mL (significant for age < 2)")
            elif cfu_val > 0:
                score += 5
                factors_pos.append(f"➕ Colony count {cfu_val:,} — borderline (pediatric)")
        elif sex == "Female" and age >= 12:
            # IDSA: ≥ 10³ symptomatic, ≥ 10⁵ asymptomatic
            if cfu_val >= 100000:
                score += 25
                factors_pos.append("✅ Colony count ≥ 10⁵ CFU/mL — significant bacteriuria")
            elif cfu_val >= 1000:
                score += 12
                factors_pos.append("➕ Colony count 10³–10⁵ — significant if symptomatic (female)")
            elif cfu_val > 0:
                score -= 10
                factors_neg.append(f"⚠️ Colony count {cfu_val:,} < 10³ — likely insignificant")
        else:
            # Male / general
            if cfu_val >= 100000:
                score += 25
                factors_pos.append("✅ Colony count ≥ 10⁵ CFU/mL — significant bacteriuria")
            elif cfu_val >= 10000:
                score += 10
                factors_pos.append("➕ Colony count 10⁴–10⁵ CFU/mL — borderline")
            elif cfu_val > 0:
                score -= 15
                factors_neg.append(f"⚠️ Colony count {cfu_val:,} < 10⁴ — likely insignificant")

        # Pyuria / Urinalysis
        pus_val = _parse_pus(pus_cells_text)
        if pus_val is not None:
            if pus_val > 10:
                score += 20
                factors_pos.append(f"✅ Significant pyuria ({pus_val} WBC/HPF)")
            elif pus_val >= 5:
                score += 10
                factors_pos.append(f"➕ Mild pyuria ({pus_val} WBC/HPF)")
            else:
                score -= 15
                factors_neg.append(f"⚠️ No/minimal pyuria ({pus_val} WBC/HPF) — argues against UTI")
        elif "طبيعي" in urinalysis_result or "normal" in urinalysis_result.lower():
            score -= 25
            factors_neg.append("❌ Normal urinalysis — strongly suggests contamination")
        elif "pyuria" in urinalysis_result.lower() or "wbc" in urinalysis_result.lower():
            score += 15
            factors_pos.append("✅ Pyuria noted on urinalysis")
        elif "nitrit" in urinalysis_result.lower():
            score += 10
            factors_pos.append("➕ Nitrites positive — bacterial activity")

        # ABU Detection
        classic_symp = [s for s in symptoms if s in [
            "Dysuria / Frequency / Urgency", "Fever (> 38°C)", "Flank pain / Loin pain"
        ]]
        if not classic_symp and cfu_val >= 100000 and pus_val is not None and pus_val >= 5:
            abu_detected = True
            special_flags.append("ABU_DETECTED")
            # ABU: treat only if pregnant or pre-surgery
            if "Pregnant" in host_factors or "Pre-surgical" in host_factors:
                score += 20
                factors_pos.append("✅ ABU in high-risk context (pregnancy/pre-op) — TREAT")
                special_flags.append("ABU_TREAT")
            else:
                score -= 20
                factors_neg.append("⚠️ Asymptomatic Bacteriuria (ABU) — Do NOT treat (IDSA 2019)")
                special_flags.append("ABU_NO_TREAT")

        # Sex & Age context
        if sex == "Female":
            score += 10
            factors_pos.append("➕ Female — higher UTI prevalence")
        if sex == "Male" and 15 <= age <= 50:
            score -= 5
            factors_neg.append("⚠️ Male (non-pediatric/non-elderly) — UTI uncommon")
        if sex == "Male" and age > 50:
            score += 10
            factors_pos.append("➕ Male > 50 — prostatic age, any UTI is significant")
        if age < 1:
            score += 15
            factors_pos.append("✅ Infant < 1 yr — all UTIs require treatment")

    # ══════════════════════════════════════════════════════════════════
    # SPUTUM — Murray-Washington criteria
    # ══════════════════════════════════════════════════════════════════
    elif "sputum" in spec_lower or "respiratory" in spec_lower or "bal" in spec_lower:

        # Murray-Washington score from WBCs & epithelial cells
        mw_pus   = _parse_pus(sputum_pus_cells)   # WBC/LPF
        mw_epith = _parse_pus(sputum_epithelial)   # Epithelial cells/LPF

        if mw_pus is not None and mw_epith is not None:
            if mw_pus >= 25 and mw_epith < 10:
                score += 30
                factors_pos.append(f"✅ Murray-Washington Grade ≥4: WBC≥25, Epi<10/LPF — Adequate sputum")
                special_flags.append("MW_ADEQUATE")
            elif mw_pus >= 25 and mw_epith >= 10:
                score += 10
                factors_pos.append(f"➕ Murray-Washington: WBC≥25 but Epi≥10 — mixed quality")
                special_flags.append("MW_MIXED")
            elif mw_epith >= 25:
                score -= 20
                factors_neg.append(f"❌ Murray-Washington: Epi≥25/LPF — heavily contaminated, reject specimen")
                special_flags.append("MW_REJECT")
            else:
                score += 5
        elif mw_epith is not None and mw_epith >= 25:
            score -= 20
            factors_neg.append("❌ Epithelial cells ≥25/LPF — specimen inadequate (saliva)")
            special_flags.append("MW_REJECT")

        # Organism context
        if organism in RESPIRATORY_PATHOGENS:
            score += 20
            factors_pos.append(f"✅ {organism} — recognized respiratory pathogen")
        elif organism in URT_CONTAMINANTS_SPUTUM:
            score -= 20
            factors_neg.append(f"⚠️ {organism} — likely URT/oropharyngeal contaminant")
        else:
            score += 5

        # Symptoms
        resp_symp = [s for s in symptoms if s in [
            "Productive cough / Purulent sputum",
            "Fever (> 38°C)", "Dyspnea", "Pleuritic chest pain"
        ]]
        if len(resp_symp) >= 2:
            score += 20
            factors_pos.append(f"✅ {len(resp_symp)} respiratory symptoms present")
        elif len(resp_symp) == 1:
            score += 10
            factors_pos.append("➕ 1 respiratory symptom present")

    # ══════════════════════════════════════════════════════════════════
    # BLOOD CULTURE — SIRS criteria
    # ══════════════════════════════════════════════════════════════════
    elif "blood" in spec_lower:

        # SIRS criteria (≥2 = SIRS, ≥3 = high probability sepsis)
        sirs_count = len(sirs_criteria)
        if sirs_count >= 3:
            score += 35
            factors_pos.append(f"✅ {sirs_count}/4 SIRS criteria met — high sepsis probability")
            special_flags.append("SIRS_HIGH")
        elif sirs_count == 2:
            score += 20
            factors_pos.append(f"➕ 2/4 SIRS criteria met — bacteremia possible")
            special_flags.append("SIRS_MET")
        elif sirs_count == 1:
            score += 10
            factors_pos.append("➕ 1 SIRS criterion — low probability bacteremia")
        else:
            score += 5
            factors_neg.append("⚠️ No SIRS criteria — consider contaminant especially for CoNS")

        # Organism type
        if organism in TRUE_BLOOD_PATHOGENS:
            score += 25
            factors_pos.append(f"✅ {organism} — true bloodstream pathogen; single positive = significant")
        elif organism in BLOOD_CONTAMINANTS:
            score -= 20
            factors_neg.append(f"⚠️ {organism} — common blood culture contaminant (CoNS/Coryne); requires ≥2 bottles")
            special_flags.append("BLOOD_CONTAMINANT_RISK")
        else:
            score += 15
            factors_pos.append(f"➕ {organism} — possible bloodstream pathogen")

        # Number of positive bottles
        if "Multiple bottles positive" in blood_source:
            score += 15
            factors_pos.append("✅ Multiple blood culture bottles positive — true bacteremia")
        elif "Single bottle" in blood_source and organism in BLOOD_CONTAMINANTS:
            score -= 15
            factors_neg.append("⚠️ Single bottle + contaminant organism — likely contamination")

        # Source identified
        if blood_source and "source" in blood_source.lower():
            score += 10
            factors_pos.append(f"➕ Source identified: {blood_source}")

    # ══════════════════════════════════════════════════════════════════
    # CSF
    # ══════════════════════════════════════════════════════════════════
    elif "csf" in spec_lower or "cerebrospinal" in spec_lower:
        score += 40
        factors_pos.append("✅ CSF — any growth is always clinically significant (sterile site)")
        special_flags.append("CSF_ALWAYS_SIGNIFICANT")

    # ══════════════════════════════════════════════════════════════════
    # WOUND / PUS
    # ══════════════════════════════════════════════════════════════════
    elif any(w in spec_lower for w in ["wound", "pus", "abscess", "swab"]):
        wound_lower = wound_type.lower() if wound_type else ""

        if organism in NORMAL_SKIN_FLORA and not wound_lower:
            score += 10
            factors_pos.append(f"➕ {organism} — possible wound pathogen, assess clinical context")
        else:
            score += 25
            factors_pos.append(f"✅ {organism} — likely wound pathogen")

        # Wound type context
        if "surgical" in wound_lower or "post-op" in wound_lower:
            score += 15
            factors_pos.append("✅ Post-surgical wound — any growth is significant")
        elif "chronic" in wound_lower or "diabetic" in wound_lower:
            score += 10
            factors_pos.append("➕ Chronic/diabetic wound — higher clinical significance")
        elif "superficial" in wound_lower:
            score -= 5
            factors_neg.append("➕ Superficial wound — assess depth and clinical signs")

        # Symptoms
        wound_symp = [s for s in symptoms if s in [
            "Erythema / Warmth / Swelling",
            "Purulent discharge",
            "Fever (> 38°C)",
            "Pain / Tenderness",
        ]]
        if len(wound_symp) >= 2:
            score += 20
            factors_pos.append(f"✅ {len(wound_symp)} local infection signs present")
        elif len(wound_symp) == 1:
            score += 10

    # ══════════════════════════════════════════════════════════════════
    # Shared factors (all specimens)
    # ══════════════════════════════════════════════════════════════════

    # Culture purity
    if culture_purity == "Pure growth":
        score += 15
        factors_pos.append("✅ Pure culture — supports true infection")
    elif culture_purity == "Mixed growth":
        score -= 15
        factors_neg.append("⚠️ Mixed growth — suggests contamination")

    # Gram stain
    if "WBCs + Gram" in gram_stain:
        score += 15
        factors_pos.append("✅ Gram stain: organisms + WBCs — supports infection")
    elif "Organisms" in gram_stain and "بدون" not in gram_stain and "without" not in gram_stain.lower():
        score += 5
        factors_pos.append("➕ Organisms seen on Gram stain")
    elif "طبيعية" in gram_stain or "No organisms" in gram_stain:
        score -= 10
        factors_neg.append("⚠️ Normal Gram stain — no organisms seen")

    # Host factors
    if "Immunosuppressants / Steroids" in host_factors:
        score += 10
        factors_pos.append("➕ Immunocompromised — lower threshold for clinical significance")
    if "Diabetes" in host_factors:
        score += 5
        factors_pos.append("➕ Diabetes — increased infection susceptibility")
    if "تاريخ UTIs متكررة" in host_factors or "Recurrent infections" in host_factors:
        score += 5
        factors_pos.append("➕ Recurrent infection history")
    if "Urinary catheter" in host_factors or "Central line / PICC" in host_factors or "Catheter" in host_factors:
        score += 10
        factors_pos.append("➕ Indwelling device — lower threshold for significance")
    if "Renal abnormality / Vesicoureteral reflux" in host_factors:
        score += 10
        factors_pos.append("➕ Structural abnormality — increased susceptibility")
    if "Pregnant" in host_factors:
        score += 10
        factors_pos.append("✅ Pregnancy — any bacteriuria requires treatment")
    if not host_factors:
        score -= 5
        factors_neg.append("➕ No host risk factors identified")

    # Pediatric global flag
    if age < 3 and "PEDIATRIC_UTI" not in special_flags and "csf" not in spec_lower:
        score += 5
        factors_pos.append("➕ Young child — higher clinical vigilance warranted")

    # ── Clamp ────────────────────────────────────────────────────────
    score = max(0, min(100, score))

    # ── Verdict ──────────────────────────────────────────────────────
    if "CSF_ALWAYS_SIGNIFICANT" in special_flags:
        verdict = "🔴 ALWAYS SIGNIFICANT — Treat Immediately"
        color   = "error"
        interpretation = "العينة من موقع معقم (CSF) — أي نمو يُعدّ مرضياً بغض النظر عن العوامل الأخرى."
        recommendations = [
            "ابدأ العلاج التجريبي فوراً ريثما تظهر نتيجة الحساسية.",
            "استشر طبيب الأمراض المعدية.",
            "احتجز المريض ومراقبته بشكل مكثف.",
        ]
    elif "MW_REJECT" in special_flags:
        verdict = "🟢 SPECIMEN INADEQUATE — Reject & Repeat"
        color   = "success"
        interpretation = "العينة غير مناسبة (خلايا طلائية ≥25/LPF). النتيجة تعكس تلوثاً من تجويف الفم لا عدوى حقيقية."
        recommendations = [
            "ارفض العينة وأعِد طلب البلغم بتقنية صحيحة.",
            "يُفضَّل التجميع الصباحي الباكر (Early morning sputum).",
            "فكّر في BAL إذا تعذّر الحصول على عينة مناسبة.",
        ]
    elif "ABU_NO_TREAT" in special_flags:
        verdict = "🟡 ASYMPTOMATIC BACTERIURIA (ABU) — Do NOT Treat"
        color   = "warning"
        interpretation = (
            "تشير المعطيات إلى Asymptomatic Bacteriuria. وفقاً لـ IDSA 2019: "
            "لا يُنصح بالعلاج إلا في الحامل أو قبل تدخل جراحي بولي."
        )
        recommendations = [
            "لا تعطِ مضادات حيوية (Antibiotic Stewardship — IDSA 2019).",
            "تابع المريض وأعِد التقييم إذا ظهرت أعراض.",
            "استثناءات: حمل — قبيل جراحة بولية (Urology pre-op).",
        ]
    elif "ABU_TREAT" in special_flags:
        verdict = "🔴 ABU IN HIGH-RISK CONTEXT — Treat"
        color   = "error"
        interpretation = "ABU في سياق يستوجب العلاج (حمل / تدخل جراحي بولي)."
        recommendations = [
            "اختر مضاداً حيوياً مناسباً للحمل حسب نتيجة الحساسية.",
            "مدة العلاج 5–7 أيام عادةً.",
            "أعِد المزرعة بعد الانتهاء من الدورة للتأكد من الشفاء.",
        ]
    elif score >= 75:
        verdict = "🔴 Likely TRUE INFECTION — Treat"
        color   = "error"
        interpretation = (
            "المؤشرات تدعم بقوة وجود عدوى حقيقية. يُنصح بالعلاج "
            "الموجَّه بنتيجة الحساسية مع مراعاة السياق الكلينيكي."
        )
        recommendations = [
            "ابدأ العلاج بناءً على نتيجة الـ AST.",
            "راعِ شدة الأعراض وعوامل الخطر.",
            "راجع الجرعة حسب الوظيفة الكلوية.",
            "De-escalate بعد 48–72 ساعة إذا تحسّن المريض.",
        ]
    elif score >= 50:
        verdict = "🟡 POSSIBLE INFECTION — Clinical Correlation Required"
        color   = "warning"
        interpretation = (
            "النتيجة حدودية. يُنصح بالتقييم الكلينيكي الكامل قبل البدء بالعلاج. "
            "قد تحتاج فحوصات إضافية أو إعادة المزرعة."
        )
        recommendations = [
            "قيّم المريض كلينيكياً قبل إعطاء المضادات الحيوية.",
            "فكّر في إعادة المزرعة إذا كان الوضع غير واضح.",
            "راجع نتيجة الـ Urinalysis / CRP / CBC إذا لم تكن متاحة.",
        ]
    elif score >= 30:
        verdict = "🟠 LIKELY CONTAMINANT — Repeat Recommended"
        color   = "warning"
        interpretation = (
            "المؤشرات تميل نحو التلوث أو الاستعمار. "
            "يُنصح بإعادة أخذ العينة بتقنية صحيحة قبل البدء بالعلاج."
        )
        recommendations = [
            "أعِد أخذ العينة مع تحسين التقنية.",
            "لا تبدأ العلاج بناءً على هذه النتيجة وحدها.",
            "إذا تكرر العزل، فكّر في مصدر بديل (Hematogenous / Device).",
        ]
    else:
        verdict = "🟢 LIKELY CONTAMINANT / COLONIZER — Do Not Treat"
        color   = "success"
        interpretation = (
            "المؤشرات تدعم التلوث أو الاستعمار بشكل كبير. "
            "العلاج غير مبرر في الغالب. تابع المريض كلينيكياً."
        )
        recommendations = [
            "لا تعطِ مضادات حيوية بناءً على هذه النتيجة.",
            "أعِد تقييم المريض إذا استمرت الأعراض أو تطورت.",
            "التزم بمبادئ Antibiotic Stewardship.",
        ]

    return {
        "score":           score,
        "verdict":         verdict,
        "color":           color,
        "interpretation":  interpretation,
        "recommendations": recommendations,
        "factors_pos":     factors_pos,
        "factors_neg":     factors_neg,
        "abu_detected":    abu_detected,
        "special_flags":   special_flags,
    }


def _parse_cfu(text: str) -> int:
    """استخرج قيمة CFU رقمية من النص"""
    if not text:
        return 0
    t = text.lower().strip()
    if any(x in t for x in ["≥", ">=", ">10^5", ">100000", "10^5", "≥10", ">=10"]):
        if "10^5" in t or "100000" in t or "≥10^5" in t:
            return 100000
        if "10^4" in t or "10000" in t:
            return 10000
    nums = re.findall(r'[\d]+', text.replace(",", ""))
    if not nums:
        return 0
    val = int(nums[-1])
    # إذا كان الرقم صغير جداً (مثل "10" تعني 10^5 أحياناً)
    if val <= 9 and "^" in text:
        exp_match = re.findall(r'\^(\d+)', text)
        if exp_match:
            val = 10 ** int(exp_match[0])
    return val


def _parse_pus(text: str):
    """استخرج أقصى قيمة WBC/HPF من النص، أو None إذا لم يوجد"""
    if not text:
        return None
    nums = re.findall(r'[\d]+', text)
    if not nums:
        return None
    return max(int(n) for n in nums)


