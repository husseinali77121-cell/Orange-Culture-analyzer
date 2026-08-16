# -*- coding: utf-8 -*-
# © Dr. Hussein Ali — Orange Lab, 6 October City, Egypt
# Microbiology CDSS — All Rights Reserved
"""pathogenicity.py — is this isolate a pathogen, or is it contamination?

WHY THIS FILE EXISTS
This is the question a microbiology report answers BEFORE the antibiotic
question, and until 2026-08-03 its 900 lines sat in the middle of
streamlit_app.py, wedged between the UI and the PDF writer. That file was
10,400 lines doing UI, clinical logic, OCR, PDF and session state at once, and
every defect this audit found in the scoring engine — the colony-count parser
reading "10*5" as 10, verbal reports scoring as "no growth", the score running
BACKWARDS at the bottom of the range — sat in code nobody could open on its own.

Extracted here it is what it always was: a pure scoring function over a handful
of tables, importable and testable without a Streamlit runtime.

WHAT IT DOES
assess_pathogenicity() weighs colony count, purity, pyuria, symptoms, host
factors, Gram stain and specimen quality into a score and a verdict, with the
factors that produced it returned alongside so the reader can disagree with the
arithmetic rather than being handed a number.

CONTRACTS WORTH KNOWING
  * _cfu_report_state() returns THREE states, not two. "no growth" and "field
    not filled in" are different facts and 0 cannot carry both — conflating
    them is what made an unread field score as a real result.
  * _parse_pus() returns None for "not stated" and that None is meaningful:
    the caller skips the whole pyuria block on it. Verbal readings ("full
    field", "loaded") resolve to numbers precisely so they do NOT fall into it.
  * Nothing here touches Streamlit, session state, or any global table.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "assess_pathogenicity",
    "_ORG_CANON_MAP", "_canon_org", "_org_in",
    "_CFU_SUPERSCRIPTS", "_CFU_VERBAL", "_PUS_VERBAL",
    "_parse_cfu", "_cfu_report_state", "_score_colony_count", "_parse_pus",
]


_ORG_CANON_MAP = {
    "e. coli": "escherichia coli", "e.coli": "escherichia coli",
    "escherichia coli": "escherichia coli",
    "enterohemorrhagic e. coli": "escherichia coli o157",
    "escherichia coli o157:h7": "escherichia coli o157",
    "klebsiella spp.": "klebsiella", "klebsiella pneumoniae": "klebsiella",
    "klebsiella oxytoca": "klebsiella", "klebsiella": "klebsiella",
    "proteus mirabilis": "proteus", "proteus spp.": "proteus", "proteus": "proteus",
    "enterococcus faecalis": "enterococcus", "enterococcus spp.": "enterococcus",
    "enterococcus faecium": "enterococcus", "enterococcus": "enterococcus",
    "vre": "vre",
    "h. influenzae": "haemophilus influenzae",
    "haemophilus influenzae": "haemophilus influenzae",
    "staphylococcus aureus": "staphylococcus aureus", "mssa": "staphylococcus aureus",
    "mrsa": "mrsa",
    "staphylococcus epidermidis": "cons",
    "staphylococcus saprophyticus": "staphylococcus saprophyticus",
    "coagulase negative staphylococcus": "cons",
    "coagulase-negative staphylococci": "cons", "cons": "cons",
    "streptococcus viridans": "viridans streptococci",
    "viridans streptococci": "viridans streptococci",
    "corynebacterium spp.": "corynebacterium", "corynebacterium": "corynebacterium",
    "campylobacter jejuni": "campylobacter", "campylobacter spp.": "campylobacter",
    "campylobacter": "campylobacter",
    "salmonella spp.": "salmonella", "salmonella": "salmonella",
    "shigella spp.": "shigella", "shigella": "shigella",
    "streptococcus pneumoniae": "streptococcus pneumoniae",
    "s. pneumoniae": "streptococcus pneumoniae",
    "pseudomonas aeruginosa": "pseudomonas aeruginosa",
    "acinetobacter baumannii": "acinetobacter baumannii",
    "stenotrophomonas maltophilia": "stenotrophomonas maltophilia",
    "legionella pneumophila": "legionella", "legionella": "legionella",
    "mycoplasma spp.": "mycoplasma", "mycoplasma pneumoniae": "mycoplasma",
    "moraxella catarrhalis": "moraxella catarrhalis",
    "neisseria meningitidis": "neisseria meningitidis",
    "neisseria spp.": "neisseria",
    "listeria monocytogenes": "listeria monocytogenes",
    "streptococcus agalactiae": "streptococcus agalactiae",
    "gbs": "streptococcus agalactiae",
    "anaerobes (لاهوائيات)": "anaerobes", "anaerobes": "anaerobes",
    "clostridioides difficile": "c. difficile", "clostridium difficile": "c. difficile",
    "candida albicans": "candida", "candida spp.": "candida", "candida": "candida",
}


def _canon_org(name: str) -> str:
    n = re.sub(r"\s+", " ", (name or "").strip().lower())
    return _ORG_CANON_MAP.get(n, n)


def _org_in(name: str, group) -> bool:
    """Spelling-independent membership test for organism names."""
    target = _canon_org(name)
    return any(_canon_org(g) == target for g in group)


# =========================================================
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
        "Candida albicans", "Candida spp.", "MRSA",
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
        "MRSA", "Legionella pneumophila", "Mycoplasma spp.",
        "Stenotrophomonas maltophilia",
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
        "MRSA", "H. influenzae", "VRE", "Anaerobes (لاهوائيات)",
        "Stenotrophomonas maltophilia", "Proteus mirabilis",
    ]
    # ══════════════════════════════════════════════════════════════════
    # ORGANISMS THAT ARE NEVER A CONTAMINANT IN BLOOD
    # ------------------------------------------------------------------
    # Found on re-review. A Staphylococcus aureus blood culture with fever
    # scored 35 and was reported as "🟠 LIKELY CONTAMINANT -- Repeat
    # Recommended". S. aureus is in TRUE_BLOOD_PATHOGENS and did earn its +25,
    # but the missing-SIRS and single-bottle deductions pulled the total back
    # under the threshold -- so an additive score alone could never protect it.
    #
    # S. aureus bacteraemia carries roughly 20-30% mortality. It mandates
    # echocardiography, source control and 2-6 weeks of intravenous therapy.
    # Telling a clinician to repeat the sample instead is the most dangerous
    # single output this engine can produce, and no combination of missing
    # metadata should be able to generate it.
    #
    # This list is deliberately NARROWER than TRUE_BLOOD_PATHOGENS: E. coli or
    # Enterococcus in one bottle can occasionally be contamination, so they keep
    # the ordinary scoring. The organisms below cannot.
    NEVER_CONTAMINANT_IN_BLOOD = [
        "Staphylococcus aureus", "MRSA", "MSSA",
        "Streptococcus pneumoniae", "Streptococcus pyogenes",
        "Neisseria meningitidis", "Haemophilus influenzae", "H. influenzae",
        "Listeria monocytogenes", "Salmonella spp.", "Salmonella typhi",
        "Candida albicans", "Candida spp.", "Streptococcus agalactiae",
        "Brucella spp.", "Neisseria gonorrhoeae",
    ]

    BLOOD_CONTAMINANTS = [
        "Staphylococcus epidermidis", "Corynebacterium spp.",
        "Bacillus spp.", "Propionibacterium spp.", "Micrococcus spp.",
    ]

    # Re-review found four hard crashes on None: symptoms, specimen, age and
    # host_factors. They arrive from widgets today, but a cleared number_input or
    # a restored session can deliver None, and a traceback in place of a
    # pathogenicity verdict is not an acceptable failure mode.
    specimen      = specimen or ""
    organism      = organism or ""
    symptoms      = list(symptoms or [])
    host_factors  = list(host_factors or [])
    if not isinstance(age, (int, float)):
        age = 40
    spec_lower = specimen.lower()

    # ══════════════════════════════════════════════════════════════════
    # URINE
    # ══════════════════════════════════════════════════════════════════
    if "urine" in spec_lower:

        # Pediatric threshold: < 2 years -> any growth significant
        if age < 2:
            score += 20
            factors_pos.append(f"✅ Infant < 2 yrs -- any colony count clinically significant")
            special_flags.append("PEDIATRIC_UTI")

        # Organism context
        if _org_in(organism, TYPICAL_UROPATHOGENS):
            score += 20
            factors_pos.append(f"✅ {organism} -- typical uropathogen")
        elif _org_in(organism, ATYPICAL_UROPATHOGENS):
            score -= 20
            factors_neg.append(f"⚠️ {organism} -- atypical uropathogen; consider contamination or hematogenous seeding")
        else:
            score += 5
            factors_pos.append(f"➕ {organism} -- occasional uropathogen")

        # Colony count
        # FIX 2026-08-01 (third pass): the three branches below used to be
        # written out inline, and all three ended at `elif cfu_val > 0`, so a
        # zero -- whether "no growth" or an unread field -- fell through with no
        # adjustment and scored HIGHER than a genuine low count. See
        # _cfu_report_state() for the measurements.
        cfu_val   = _parse_cfu(colony_count_text)
        cfu_state = _cfu_report_state(colony_count_text)
        _d, _pos, _neg = _score_colony_count(cfu_state, cfu_val, age, sex)
        score += _d
        if _pos:
            factors_pos.append(_pos)
        if _neg:
            factors_neg.append(_neg)
        if cfu_state == "unreported":
            special_flags.append("CFU_NOT_REPORTED")

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
                factors_neg.append(f"⚠️ No/minimal pyuria ({pus_val} WBC/HPF) -- argues against UTI")
        elif "طبيعي" in urinalysis_result or "normal" in urinalysis_result.lower():
            score -= 25
            factors_neg.append("❌ Normal urinalysis -- strongly suggests contamination")
        elif "pyuria" in urinalysis_result.lower() or "wbc" in urinalysis_result.lower():
            score += 15
            factors_pos.append("✅ Pyuria noted on urinalysis")
        elif "nitrit" in urinalysis_result.lower():
            score += 10
            factors_pos.append("➕ Nitrites positive -- bacterial activity")

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
                factors_pos.append("✅ ABU in high-risk context (pregnancy/pre-op) -- TREAT")
                special_flags.append("ABU_TREAT")
            else:
                score -= 20
                factors_neg.append("⚠️ Asymptomatic Bacteriuria (ABU) -- Do NOT treat (IDSA 2019)")
                special_flags.append("ABU_NO_TREAT")

        # Sex & Age context
        if sex == "Female":
            score += 10
            factors_pos.append("➕ Female -- higher UTI prevalence")
        if sex == "Male" and 15 <= age <= 50:
            score -= 5
            factors_neg.append("⚠️ Male (non-pediatric/non-elderly) -- UTI uncommon")
        if sex == "Male" and age > 50:
            score += 10
            factors_pos.append("➕ Male > 50 -- prostatic age, any UTI is significant")
        if age < 1:
            score += 15
            factors_pos.append("✅ Infant < 1 yr -- all UTIs require treatment")

    # ══════════════════════════════════════════════════════════════════
    # SPUTUM -- Murray-Washington criteria
    # ══════════════════════════════════════════════════════════════════
    elif "sputum" in spec_lower or "respiratory" in spec_lower or "bal" in spec_lower:

        # Murray-Washington score from WBCs & epithelial cells
        mw_pus   = _parse_pus(sputum_pus_cells)   # WBC/LPF
        mw_epith = _parse_pus(sputum_epithelial)   # Epithelial cells/LPF

        if mw_pus is not None and mw_epith is not None:
            if mw_pus >= 25 and mw_epith < 10:
                score += 30
                factors_pos.append(f"✅ Murray-Washington Grade ≥4: WBC≥25, Epi<10/LPF -- Adequate sputum")
                special_flags.append("MW_ADEQUATE")
            elif mw_pus >= 25 and mw_epith >= 10:
                score += 10
                factors_pos.append(f"➕ Murray-Washington: WBC≥25 but Epi≥10 -- mixed quality")
                special_flags.append("MW_MIXED")
            elif mw_epith >= 25:
                score -= 20
                factors_neg.append(f"❌ Murray-Washington: Epi≥25/LPF -- heavily contaminated, reject specimen")
                special_flags.append("MW_REJECT")
            else:
                score += 5
        elif mw_epith is not None and mw_epith >= 25:
            score -= 20
            factors_neg.append("❌ Epithelial cells ≥25/LPF -- specimen inadequate (saliva)")
            special_flags.append("MW_REJECT")

        # Organism context
        if _org_in(organism, RESPIRATORY_PATHOGENS):
            score += 20
            factors_pos.append(f"✅ {organism} -- recognized respiratory pathogen")
        elif _org_in(organism, URT_CONTAMINANTS_SPUTUM):
            score -= 20
            factors_neg.append(f"⚠️ {organism} -- likely URT/oropharyngeal contaminant")
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
    # BLOOD CULTURE -- SIRS criteria
    # ══════════════════════════════════════════════════════════════════
    elif "blood" in spec_lower:

        # SIRS criteria (≥2 = SIRS, ≥3 = high probability sepsis)
        sirs_count = len(sirs_criteria)
        if sirs_count >= 3:
            score += 35
            factors_pos.append(f"✅ {sirs_count}/4 SIRS criteria met -- high sepsis probability")
            special_flags.append("SIRS_HIGH")
        elif sirs_count == 2:
            score += 20
            factors_pos.append(f"➕ 2/4 SIRS criteria met -- bacteremia possible")
            special_flags.append("SIRS_MET")
        elif sirs_count == 1:
            score += 10
            factors_pos.append("➕ 1 SIRS criterion -- low probability bacteremia")
        else:
            # No SIRS: neutral — let organism type drive (true pathogen vs CoNS contaminant).
            # (was +5, which contradicted the contaminant warning printed below.)
            score += 0
            factors_neg.append("⚠️ No SIRS criteria -- consider contaminant especially for CoNS")

        # Organism type
        if _org_in(organism, NEVER_CONTAMINANT_IN_BLOOD):
            score += 25
            special_flags.append("NEVER_CONTAMINANT")
            factors_pos.append(
                f"🔴 {organism} في الدم لا يُعد ملوِّثاً أبداً — عزلة واحدة كافية. "
                "ابدأ العلاج فوراً ولا تنتظر إعادة المزرعة.")
        elif _org_in(organism, TRUE_BLOOD_PATHOGENS):
            score += 25
            factors_pos.append(f"✅ {organism} -- true bloodstream pathogen; single positive = significant")
        elif _org_in(organism, BLOOD_CONTAMINANTS):
            score -= 20
            factors_neg.append(f"⚠️ {organism} -- common blood culture contaminant (CoNS/Coryne); requires ≥2 bottles")
            special_flags.append("BLOOD_CONTAMINANT_RISK")
        else:
            score += 15
            factors_pos.append(f"➕ {organism} -- possible bloodstream pathogen")

        # Number of positive bottles
        if "Multiple bottles positive" in blood_source:
            score += 15
            factors_pos.append("✅ Multiple blood culture bottles positive -- true bacteremia")
        elif "Single bottle" in blood_source and _org_in(organism, BLOOD_CONTAMINANTS):
            score -= 15
            factors_neg.append("⚠️ Single bottle + contaminant organism -- likely contamination")

        # Source identified
        if blood_source and "source" in blood_source.lower():
            score += 10
            factors_pos.append(f"➕ Source identified: {blood_source}")

    # ══════════════════════════════════════════════════════════════════
    # CSF
    # ══════════════════════════════════════════════════════════════════
    elif "csf" in spec_lower or "cerebrospinal" in spec_lower:
        score += 40
        factors_pos.append("✅ CSF -- any growth is always clinically significant (sterile site)")
        special_flags.append("CSF_ALWAYS_SIGNIFICANT")

    # ══════════════════════════════════════════════════════════════════
    # STOOL / GI
    # ══════════════════════════════════════════════════════════════════
    elif "stool" in spec_lower or "fecal" in spec_lower or "rectal" in spec_lower:

        # GI-specific pathogens always significant
        GI_TRUE_PATHOGENS = [
            "Salmonella spp.", "Shigella spp.", "Campylobacter spp.",
            "Clostridioides difficile", "Clostridium difficile",
            "Yersinia enterocolitica", "Vibrio cholerae", "Listeria monocytogenes",
            "Enterohemorrhagic E. coli", "Escherichia coli O157:H7",
            "Entamoeba histolytica",
        ]
        GI_NORMAL_FLORA = [
            "Escherichia coli", "Klebsiella spp.", "Klebsiella pneumoniae",
            "Enterococcus faecalis", "Enterococcus spp.",
            "Proteus mirabilis", "Proteus spp.",
        ]

        if _org_in(organism, GI_TRUE_PATHOGENS):
            score += 40
            factors_pos.append(f"✅ {organism} -- obligate GI pathogen; always clinically significant")
            special_flags.append("GI_TRUE_PATHOGEN")
        elif _org_in(organism, GI_NORMAL_FLORA):
            score -= 10
            factors_neg.append(f"⚠️ {organism} -- normal GI flora; significance depends on clinical context")
        else:
            score += 15
            factors_pos.append(f"➕ {organism} -- potential GI pathogen; correlate clinically")

        # GI Symptoms
        gi_symp = [s for s in symptoms if s in [
            "Fever (> 38°C)", "Bloody diarrhea", "Watery diarrhea",
            "Vomiting", "Abdominal cramps",
        ]]
        if len(gi_symp) >= 2:
            score += 25
            factors_pos.append(f"✅ {len(gi_symp)} GI symptoms -- supports true infection")
        elif len(gi_symp) == 1:
            score += 10
        else:
            score -= 10
            factors_neg.append("⚠️ No GI symptoms -- most stool cultures positive without symptoms = colonization")

        # Most GI infections: antibiotics often NOT indicated
        factors_neg.append("⚠️ Most GI infections: supportive care preferred; antibiotics only for severe/immunocompromised")

    # ══════════════════════════════════════════════════════════════════
    # WOUND / PUS
    # ══════════════════════════════════════════════════════════════════
    elif any(w in spec_lower for w in ["wound", "pus", "abscess", "swab"]):
        wound_lower = wound_type.lower() if wound_type else ""

        if _org_in(organism, NORMAL_SKIN_FLORA) and not wound_lower:
            score += 10
            factors_pos.append(f"➕ {organism} -- possible wound pathogen, assess clinical context")
        else:
            score += 25
            factors_pos.append(f"✅ {organism} -- likely wound pathogen")

        # Wound type context
        if "surgical" in wound_lower or "post-op" in wound_lower:
            score += 15
            factors_pos.append("✅ Post-surgical wound -- any growth is significant")
        elif "chronic" in wound_lower or "diabetic" in wound_lower:
            score += 10
            factors_pos.append("➕ Chronic/diabetic wound -- higher clinical significance")
        elif "superficial" in wound_lower:
            score -= 5
            factors_neg.append("➕ Superficial wound -- assess depth and clinical signs")

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
        factors_pos.append("✅ Pure culture -- supports true infection")
    elif culture_purity == "Mixed growth":
        score -= 15
        factors_neg.append("⚠️ Mixed growth -- suggests contamination")

    # Gram stain
    if "WBCs + Gram" in gram_stain:
        score += 15
        factors_pos.append("✅ Gram stain: organisms + WBCs -- supports infection")
    elif "Organisms" in gram_stain and "بدون" not in gram_stain and "without" not in gram_stain.lower():
        score += 5
        factors_pos.append("➕ Organisms seen on Gram stain")
    elif "طبيعية" in gram_stain or "No organisms" in gram_stain:
        score -= 10
        factors_neg.append("⚠️ Normal Gram stain -- no organisms seen")

    # Host factors
    if "Immunosuppressants / Steroids" in host_factors:
        score += 10
        factors_pos.append("➕ Immunocompromised -- lower threshold for clinical significance")
    if "Diabetes" in host_factors:
        score += 5
        factors_pos.append("➕ Diabetes -- increased infection susceptibility")
    if "تاريخ UTIs متكررة" in host_factors or "Recurrent infections" in host_factors:
        score += 5
        factors_pos.append("➕ Recurrent infection history")
    if "Urinary catheter" in host_factors or "Central line / PICC" in host_factors or "Catheter" in host_factors:
        score += 10
        factors_pos.append("➕ Indwelling device -- lower threshold for significance")
    if "Renal abnormality / Vesicoureteral reflux" in host_factors:
        score += 10
        factors_pos.append("➕ Structural abnormality -- increased susceptibility")
    if "Pregnant" in host_factors:
        score += 10
        factors_pos.append("✅ Pregnancy -- any bacteriuria requires treatment")
    if not host_factors:
        score -= 5
        factors_neg.append("➕ No host risk factors identified")

    # Pediatric global flag
    if age < 3 and "PEDIATRIC_UTI" not in special_flags and "csf" not in spec_lower:
        score += 5
        factors_pos.append("➕ Young child -- higher clinical vigilance warranted")

    # ── Clamp ────────────────────────────────────────────────────────
    score = max(0, min(100, score))

    # ── Verdict ──────────────────────────────────────────────────────
    # HARD FLOOR: a never-contaminant sterile-site isolate cannot be downgraded
    # to "contaminant" by missing metadata, whatever the additive score says.
    if "NEVER_CONTAMINANT" in special_flags and score < 75:
        score = 75

    if "CSF_ALWAYS_SIGNIFICANT" in special_flags:
        verdict = "🔴 ALWAYS SIGNIFICANT -- Treat Immediately"
        color   = "error"
        interpretation = "العينة من موقع معقم (CSF) -- أي نمو يُعدّ مرضياً بغض النظر عن العوامل الأخرى."
        recommendations = [
            "ابدأ العلاج التجريبي فوراً ريثما تظهر نتيجة الحساسية.",
            "استشر طبيب الأمراض المعدية.",
            "احتجز المريض ومراقبته بشكل مكثف.",
        ]
    elif "MW_REJECT" in special_flags:
        verdict = "🟢 SPECIMEN INADEQUATE -- Reject & Repeat"
        color   = "success"
        interpretation = "العينة غير مناسبة (خلايا طلائية ≥25/LPF). النتيجة تعكس تلوثاً من تجويف الفم لا عدوى حقيقية."
        recommendations = [
            "ارفض العينة وأعِد طلب البلغم بتقنية صحيحة.",
            "يُفضَّل التجميع الصباحي الباكر (Early morning sputum).",
            "فكّر في BAL إذا تعذّر الحصول على عينة مناسبة.",
        ]
    elif "ABU_NO_TREAT" in special_flags:
        verdict = "🟡 ASYMPTOMATIC BACTERIURIA (ABU) -- Do NOT Treat"
        color   = "warning"
        interpretation = (
            "تشير المعطيات إلى Asymptomatic Bacteriuria. وفقاً لـ IDSA 2019: "
            "لا يُنصح بالعلاج إلا في الحامل أو قبل تدخل جراحي بولي."
        )
        recommendations = [
            "لا تعطِ مضادات حيوية (Antibiotic Stewardship -- IDSA 2019).",
            "تابع المريض وأعِد التقييم إذا ظهرت أعراض.",
            "استثناءات: حمل -- قبيل جراحة بولية (Urology pre-op).",
        ]
    elif "ABU_TREAT" in special_flags:
        verdict = "🔴 ABU IN HIGH-RISK CONTEXT -- Treat"
        color   = "error"
        interpretation = "ABU في سياق يستوجب العلاج (حمل / تدخل جراحي بولي)."
        recommendations = [
            "اختر مضاداً حيوياً مناسباً للحمل حسب نتيجة الحساسية.",
            "مدة العلاج 5–7 أيام عادةً.",
            "أعِد المزرعة بعد الانتهاء من الدورة للتأكد من الشفاء.",
        ]
    elif score >= 75:
        verdict = "🔴 Likely TRUE INFECTION -- Treat"
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
        verdict = "🟡 POSSIBLE INFECTION -- Clinical Correlation Required"
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
        verdict = "🟠 LIKELY CONTAMINANT -- Repeat Recommended"
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
        verdict = "🟢 LIKELY CONTAMINANT / COLONIZER -- Do Not Treat"
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


_CFU_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")

# Semi-quantitative and verbal colony reports, mapped to a representative count.
# ORDER MATTERS: scanned top-down and the first hit wins, so the more specific
# phrase must precede the substring it contains ("no significant growth" before
# "significant growth", "scanty" before "growth").
#
# Values sit in the MIDDLE of the band each phrase denotes, never on a
# threshold, so a rounding argument can never flip the score:
#   heavy / TNTC / confluent  -> 10^5 band  (significant at every age and sex)
#   moderate                  -> 10^4 band  (borderline for males, significant <2y)
#   scanty / few / light      -> 10^3 band  (significant only if symptomatic)
_CFU_VERBAL: List[Tuple[str, int]] = [
    ("no significant growth", 0),
    ("insignificant growth", 0),
    ("no bacterial growth", 0),
    ("لا يوجد نمو", 0),
    ("نمو غير معنوي", 0),
    ("too numerous to count", 300000),
    ("tntc", 300000),
    ("confluent growth", 300000),
    ("innumerable", 300000),
    ("heavy growth", 300000),
    ("heavy mixed growth", 300000),
    ("profuse growth", 300000),
    ("+++", 300000),
    ("نمو كثيف", 300000),
    ("نمو غزير", 300000),
    ("significant growth", 300000),
    ("moderate growth", 30000),
    ("moderate mixed growth", 30000),
    ("++", 30000),
    ("نمو متوسط", 30000),
    ("scanty growth", 3000),
    ("scant growth", 3000),
    ("light growth", 3000),
    ("few colonies", 3000),
    ("occasional colonies", 3000),
    ("نمو ضئيل", 3000),
    ("نمو قليل", 3000),
]

# Verbal pyuria estimates. _parse_pus() returns None for "not stated", and the
# caller skips the whole pyuria block on None -- so "full field", the strongest
# reading on the form, used to contribute nothing at all.
_PUS_VERBAL: List[Tuple[str, int]] = [
    ("full field", 100),
    ("packed", 100),
    ("loaded", 100),
    ("innumerable", 100),
    ("too numerous", 100),
    ("tntc", 100),
    ("plenty", 50),
    ("numerous", 50),
    ("many", 30),
    ("moderate", 15),
    ("مليء", 100),
    ("كثير", 30),
    ("متوسط", 15),
    ("few", 3),
    ("occasional", 3),
    ("rare", 1),
    ("قليل", 3),
    ("نادر", 1),
]


def _parse_cfu(text: str) -> int:
    """Numeric CFU/mL from a free-text colony-count field.

    REWRITTEN. The previous body ended with `val = int(nums[-1])` -- the LAST
    number anywhere in the string. Any trailing digit hijacked the result:

        "Colony count 100000 CFU/mL (specimen 2)"  ->  2
        "10 5 CFU/mL"   (OCR lost the superscript) ->  5
        "Growth < 10^4 CFU/mL"                     ->  10000  (direction dropped)

    The first two turn a significant count into an insignificant one, which is
    the direction that costs a patient a treated infection. The third does the
    opposite and manufactures significance out of an explicitly sub-threshold
    report.

    Strategy: normalise, then read the count that is ACTUALLY tied to a CFU /
    count keyword or to power-of-ten notation, and honour the comparison
    operator that precedes it.
    """
    if not text:
        return 0
    t = str(text)

    # Unicode superscripts after "10" -> caret form ("10⁵" -> "10^5").
    t = re.sub(r"10\s*([\u2070\u00b9\u00b2\u00b3\u2074-\u2079]+)",
               lambda m: "10^" + m.group(1).translate(_CFU_SUPERSCRIPTS), t)
    # OCR frequently renders "10⁵" as "10 5" / "10-5" once the superscript is
    # lost. A bare "10" followed by a single digit 2-9 is a lost exponent, never
    # a real count of "5 CFU/mL".
    t = re.sub(r"\b10\s*[\-\u2013 ]\s*([2-9])\b", r"10^\1", t)
    # FIX 2026-08-01 (second pass): the caret was the ONLY exponent form this
    # function understood. Analysers and technologists routinely type the ASCII
    # alternatives, and every one of them collapsed to the mantissa:
    #     "10*5" -> 10   "10**5" -> 10   "10E5" -> 10   "10e5" -> 10
    # For an adult male urine that turns +25 "significant bacteriuria" into
    # -15 "likely insignificant" -- a 40-point swing in the direction that
    # dismisses a real infection. Normalise them all to the caret form first.
    t = re.sub(r"\b10\s*(?:\*\*|\*|[eE]|\^)\s*(\d+)", r"10^\1", t)
    # A coefficient in front of a power of ten was silently dropped:
    # "5x10^4" returned 10 000, not 50 000. Fold it in before the scan.
    t = re.sub(
        r"(\d+(?:\.\d+)?)\s*[x\u00d7\u2715*]\s*10\s*\^\s*(\d+)",
        lambda m: str(int(float(m.group(1)) * (10 ** int(m.group(2))))), t)
    t = t.replace("\u2009", " ")

    low = t.lower()
    if any(k in low for k in ("no growth", "sterile", "no organism", "لا يوجد نمو")):
        return 0

    # ── Semi-quantitative and verbal reports ─────────────────────────────────
    # FIX 2026-08-01 (second pass): "heavy growth", "TNTC" and "significant
    # growth" all returned 0 -- the SAME value as "no growth". Callers cannot
    # distinguish "nothing grew" from "the parser gave up", and 0 is scored as
    # absence of infection, so the strongest possible signal on the form was
    # read as the weakest. These phrasings are what Egyptian lab report forms
    # actually print. Mapped to the midpoint of the band each phrase denotes,
    # so the existing thresholds (10^3 / 10^4 / 10^5) keep working unchanged.
    for _kw, _val in _CFU_VERBAL:
        if _kw in low:
            return _val

    # Candidate counts. The number pattern is deliberately STRICT:
    #   10^n            power-of-ten notation
    #   1,234,567       thousands-separated
    #   12345           a plain run of digits
    # An earlier draft of this rewrite used `\d[\d, ]{2,}`, which greedily ate
    # across a clause boundary: "pus cells 20-25, 100000 CFU/mL" matched
    # "25, 100000" and returned 25,100,000. A comma or space may only appear
    # INSIDE a thousands group, never as a separator between two readings.
    pat = re.compile(
        r"(?:10\s*\^\s*(?P<exp>\d+))"
        r"|(?P<grp>\d{1,3}(?:,\d{3})+)"
        r"|(?P<num>\d+)"
    )

    cands = []
    for m in pat.finditer(t):
        if m.group("exp"):
            val = 10 ** int(m.group("exp"))
        elif m.group("grp"):
            val = int(m.group("grp").replace(",", ""))
        else:
            val = int(m.group("num"))
        cands.append((m.start(), m.end(), val))
    if not cands:
        return 0

    # Prefer a candidate sitting next to a CFU / count keyword. Report suffixes
    # ("sample #3", "(specimen 2)") and unrelated clauses ("pus cells 20-25")
    # carry no such keyword, so they drop out.
    anchored = [(a, b, v) for a, b, v in cands
                if re.search(r"cfu|colon|count|/ml|/cc|بكتير|مستعمر",
                             low[max(0, a - 24): b + 26])]
    pool = anchored or cands
    start, end, value = max(pool, key=lambda c: c[2])

    # "<" applies only when it sits IMMEDIATELY BEFORE the count we chose. The
    # first draft searched the whole string, so a "pus cells < 5" clause silently
    # decremented an unrelated colony count.
    prefix = low[max(0, start - 14): start]
    if re.search(r"[<\u2264]\s*(?:10\s*\^\s*)?$|less than\s*$|below\s*$|أقل من\s*$",
                 prefix) and value > 0:
        value -= 1
    return value


def _cfu_report_state(text: str) -> str:
    """Classify WHAT the colony-count field says, not just its numeric value.

    _parse_cfu() returns an int, and 0 is overloaded: it means both "the lab
    reported no growth" and "the field is blank or the parser could not read
    it". assess_pathogenicity() consumed only that int, and every one of its
    three age/sex branches was written as

        if   cfu_val >= HIGH: score += ...
        elif cfu_val >= MID:  score += ...
        elif cfu_val > 0:     score -= PENALTY      # small count is penalised
        #    cfu_val == 0  ->  no branch at all     # zero is NOT

    so zero escaped the penalty a small count pays, and the score went
    BACKWARDS at the bottom of the range:

        male 35, dysuria, pyuria 20-25
            "No growth"  -> 45      "10^3 CFU/mL" -> 30
        infant, field left blank
            -> 85  ->  "Likely TRUE INFECTION -- Treat"

    Sterile urine scoring higher than scanty growth is the wrong direction, and
    an unread field scoring at all is worse: it is an opinion manufactured from
    an absence of data.

    Returns one of:
        "none"       -- the lab explicitly reported no growth. Strong evidence
                        AGAINST infection; must outweigh a low-but-real count.
        "unreported" -- blank, or present but unparseable. Contributes NOTHING
                        to the score and is surfaced to the user instead.
        "counted"    -- a real reading; use _parse_cfu()'s value.
    """
    raw = (text or "").strip()
    if not raw:
        return "unreported"
    low = raw.lower()
    if any(k in low for k in ("no growth", "sterile", "no organism",
                              "no significant growth", "insignificant growth",
                              "no bacterial growth", "لا يوجد نمو",
                              "نمو غير معنوي")):
        return "none"
    # A reading the parser could not resolve to a number is NOT a zero count.
    # _parse_cfu returns 0 for both, which is exactly the conflation above.
    return "counted" if _parse_cfu(raw) > 0 else "unreported"


def _score_colony_count(state: str, cfu_val: int, age: int, sex: str):
    """(delta, positive_factor, negative_factor) for the colony-count field.

    Split out of assess_pathogenicity so the three age/sex branches share one
    treatment of the "none" and "unreported" states — the original had the
    thresholds written out three times and the zero case missing from all three.
    """
    if state == "unreported":
        return 0, None, ("ℹ️ Colony count not reported / unreadable — this field "
                         "contributed nothing to the score. Enter it for a "
                         "reliable assessment.")
    if state == "none":
        # Must be a HARDER penalty than any low-count penalty below, otherwise
        # sterile urine outranks scanty growth. Explicit no-growth with an
        # organism named on the form is itself a contradiction worth flagging.
        return -30, None, ("❌ No growth reported — strong evidence against "
                           "infection. If an organism was isolated, the colony "
                           "count and the culture result disagree; re-check the "
                           "report before treating.")

    if age < 2:
        if cfu_val >= 10000:
            return 20, "✅ Colony count ≥ 10⁴ CFU/mL (significant for age < 2)", None
        return 5, f"➕ Colony count {cfu_val:,} -- borderline (pediatric)", None
    if sex == "Female" and age >= 12:
        if cfu_val >= 100000:
            return 25, "✅ Colony count ≥ 10⁵ CFU/mL -- significant bacteriuria", None
        if cfu_val >= 1000:
            return 12, "➕ Colony count 10³–10⁵ -- significant if symptomatic (female)", None
        return -10, None, f"⚠️ Colony count {cfu_val:,} < 10³ -- likely insignificant"
    if cfu_val >= 100000:
        return 25, "✅ Colony count ≥ 10⁵ CFU/mL -- significant bacteriuria", None
    if cfu_val >= 10000:
        return 10, "➕ Colony count 10⁴–10⁵ CFU/mL -- borderline", None
    return -15, None, f"⚠️ Colony count {cfu_val:,} < 10⁴ -- likely insignificant"


def _parse_pus(text: str):
    """Highest WBC/HPF reading in the text, or None when none is stated.

    Returning None is meaningful: assess_pathogenicity() skips its entire pyuria
    block on None. That is correct for "not done", and was WRONG for "full
    field" / "loaded" / "TNTC" -- the strongest pyuria a microscopist can report
    -- which contributed nothing because the string holds no digit. The verbal
    forms are resolved first so a stray digit elsewhere in the field cannot
    outrank them.
    """
    if not text:
        return None
    low = str(text).lower()
    for _kw, _val in _PUS_VERBAL:
        if _kw in low:
            return _val
    nums = re.findall(r'[\d]+', text)
    if not nums:
        return None
    return max(int(n) for n in nums)
