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

ENGINE v3 (2026-11-10) rebuilt the scoring: thresholds by collection method,
"not entered" kept apart from "absent", spinal-cord-injury and device context,
unspeciated organisms, Gram-variable and stain/culture concordance. See the
block comment above PATHO_ENGINE_VERSION.

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
    # v3 (2026-11-10)
    "PATHO_ENGINE_VERSION", "_urine_threshold", "_gram_type", "_stain_type",
    "HOST_SCI_PARA", "HOST_SCI_QUAD", "HOST_FACTORS_URINE", "HOST_FACTORS_OTHER",
    "URINE_COLLECTION_METHODS", "URINE_SYMPTOMS", "GRAM_STAIN_OPTIONS",
    "WOUND_TYPES", "WOUND_SIGNS", "RESPIRATORY_SIGNS",
]


_ORG_CANON_MAP = {
    "e. coli": "escherichia coli", "e.coli": "escherichia coli",
    "escherichia coli": "escherichia coli",
    "enterohemorrhagic e. coli": "escherichia coli o157",
    "escherichia coli o157:h7": "escherichia coli o157",
    "klebsiella spp.": "klebsiella", "klebsiella pneumoniae": "klebsiella",
    "klebsiella oxytoca": "klebsiella", "klebsiella": "klebsiella",
    "proteus mirabilis": "proteus", "proteus spp.": "proteus", "proteus": "proteus",
    "proteus vulgaris": "proteus",
    "citrobacter spp.": "citrobacter", "citrobacter freundii": "citrobacter",
    "citrobacter koseri": "citrobacter", "citrobacter": "citrobacter",
    "enterococcus faecalis": "enterococcus", "enterococcus spp.": "enterococcus",
    "enterococcus faecium": "enterococcus", "enterococcus": "enterococcus",
    "vre": "vre",
    "h. influenzae": "haemophilus influenzae",
    "haemophilus influenzae": "haemophilus influenzae",
    "staphylococcus aureus": "staphylococcus aureus", "mssa": "staphylococcus aureus",
    "mrsa": "mrsa",
    "staphylococcus epidermidis": "cons",
    "staphylococcus saprophyticus": "staphylococcus saprophyticus",
    # S. lugdunensis keeps its own identity: it must never be scored as a
    # skin contaminant like the other CoNS (2026-11-10).
    "staphylococcus lugdunensis": "staphylococcus lugdunensis",
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


# ════════════════════════════════════════════════════════════════════════════
#  PATHOGENICITY ENGINE v3 — rebuilt 2026-11-10
#  --------------------------------------------------------------------------
#  WHAT CHANGED AND WHY
#  v2 added points for anything that sounded like risk. Several of those were
#  not evidence that THIS growth is an infection, and a few ran the wrong way:
#
#    * A urinary catheter earned +10 ("lower threshold for significance").
#      Catheter bacteriuria is near-universal; a catheter makes a positive
#      culture LESS specific, not more. IDSA 2009 (CA-UTI): >= 10^3 CFU/mL PLUS
#      compatible symptoms, and pyuria does not separate CA-UTI from CA-ASB.
#    * Asymptomatic bacteriuria was only recognised when pyuria was present.
#      IDSA 2019 defines it on the count and the absence of symptoms alone.
#    * An EMPTY symptom list was scored as "asymptomatic". Not entered and
#      explicitly absent are different facts — the same conflation the colony
#      count had before _cfu_report_state() split it into three states.
#    * "Female +10", "male 15-50 -5", "no host factors -5": prevalence, not
#      evidence about this specimen. Removed.
#    * "Organisms بدون WBCs" matched no branch at all (the test for the word
#      "Organisms" excluded any string containing "بدون"), so it scored nothing.
#    * CSF: every isolate was "always significant — treat immediately",
#      including a coagulase-negative staphylococcus from a patient with no
#      shunt — the commonest CSF contaminant there is.
#    * A chronic or diabetic wound earned +10. Chronic wounds are always
#      colonised; IWGDF/IDSA diagnose infection CLINICALLY (>= 2 local signs).
#
#  NEW IN v3
#    * Thresholds chosen by collection method, age, sex and symptoms, and
#      REPORTED (`threshold`) so the reader sees which rule was applied.
#    * Spinal cord injury (paraplegia / quadriplegia): neurogenic bladder,
#      SCI-specific UTI symptoms, no treatment of bacteriuria without them,
#      pressure-ulcer swabs, impaired cough in cervical injury.
#    * Unspeciated organisms ("Acinetobacter spp.", "Gram-negative bacilli
#      (unidentified)", ...) are placed by genus / Gram reaction.
#    * Gram stain: Gram-variable, more morphotypes, and a stain-vs-culture
#      concordance check.
#    * "Insufficient data" is a verdict. Missing inputs are listed.
#
#  CONTRACT (unchanged): same positional arguments, same keys in the result.
#  New keys: engine_version, category, threshold, notes, missing_inputs,
#  confidence, references, evidence.
# ════════════════════════════════════════════════════════════════════════════
PATHO_ENGINE_VERSION = "3.0 (2026-11-10)"

# ── Option lists (single source for the UI) ─────────────────────────────────
HOST_SCI_PARA = "Paraplegia (spinal cord injury)"
HOST_SCI_QUAD = "Quadriplegia / Tetraplegia (cervical cord injury)"

HOST_FACTORS_URINE = [
    "Immunosuppressants / Steroids", "Neutropenia", "Renal transplant",
    "Diabetes", "Urinary catheter",
    HOST_SCI_PARA, HOST_SCI_QUAD, "Neurogenic bladder (non-SCI)",
    "تاريخ UTIs متكررة", "Renal abnormality / Vesicoureteral reflux",
    "Urinary obstruction / Stone / Stent",
    "Pregnant", "Urologic procedure planned (mucosal trauma)",
]
HOST_FACTORS_OTHER = [
    "Immunosuppressants / Steroids", "Neutropenia", "Diabetes",
    "Central line / PICC", "Catheter",
    "Prosthetic valve / Pacemaker / Vascular graft",
    "CSF shunt / EVD / Recent neurosurgery",
    "Tracheostomy / Mechanical ventilation",
    HOST_SCI_PARA, HOST_SCI_QUAD,
    "Recurrent infections",
]
URINE_COLLECTION_METHODS = [
    "مش محدد",
    "Midstream clean-catch",
    "Indwelling catheter (Foley)",
    "Intermittent catheterisation (in-out / CIC)",
    "Suprapubic catheter",
    "Suprapubic aspirate (SPA)",
    "Condom catheter",
    "Bag specimen (infant)",
    "Nephrostomy / Ileal conduit",
]
URINE_SYMPTOMS = [
    "Dysuria / Frequency / Urgency", "Suprapubic pain / tenderness",
    "Fever (> 38°C)", "Flank pain / Loin pain", "Rigors / Hypotension (sepsis)",
    "Acute haematuria",
    "Increased spasticity (SCI)", "Autonomic dysreflexia (SCI)",
    "Malaise / Lethargy / Sense of unease (SCI)",
    "New incontinence / Leaking around catheter",
    "Cloudy / Foul-smelling urine only",
    "Confusion / Delirium only (no urinary symptoms)",
    "Nocturnal enuresis", "Abdominal pain", "Nausea / Vomiting",
    "Asymptomatic",
]
GRAM_STAIN_OPTIONS = [
    "مش متعملة",
    "WBCs + Gram Positive Cocci",
    "WBCs + Gram Negative Rods",
    "WBCs + Gram Negative Cocci / Diplococci",
    "WBCs + Gram Positive Rods",
    "WBCs + Gram Variable Rods / Coccobacilli",
    "WBCs + Mixed flora (Polymicrobial)",
    "WBCs + Yeast cells",
    "Organisms بدون WBCs",
    "Gram Variable organisms بدون WBCs",
    "WBCs بدون Organisms",
    "طبيعية (No organisms seen)",
]
WOUND_TYPES = [
    "مش محدد", "Surgical / Post-op", "Abscess (aspirated pus)",
    "Chronic / Diabetic", "Pressure ulcer / Bed sore", "Burn",
    "Bite wound", "Superficial",
]
WOUND_SIGNS = [
    "Erythema / Warmth / Swelling", "Purulent discharge", "Fever (> 38°C)",
    "Pain / Tenderness", "No local signs of infection",
]
RESPIRATORY_SIGNS = [
    "Productive cough / Purulent sputum", "Fever (> 38°C)", "Dyspnea",
    "Pleuritic chest pain", "New infiltrate on chest imaging",
    "Worsening oxygenation / ventilator settings",
]

# ── Organism placement by genus / Gram reaction (lower-case substrings) ─────
_TK_ENTEROBACTERALES = (
    "e. coli", "e.coli", "escherichia", "klebsiella", "proteus", "enterobacter",
    "citrobacter", "serratia", "morganella", "providencia", "hafnia",
    "salmonella", "shigella", "enterobacterales", "pantoea", "raoultella", "yersinia")
_TK_NONFERMENTERS = ("pseudomonas", "acinetobacter", "stenotrophomonas",
                     "burkholderia", "non-ferment")
_TK_SAUREUS = ("staphylococcus aureus", "s. aureus", "mrsa", "mssa", "lugdunensis")
_TK_SKIN_FLORA = ("coagulase-negative", "coagulase negative", "epidermidis",
                  "haemolyticus", "hominis", "corynebacterium", "diphtheroid",
                  "cutibacterium", "propionibacterium", "bacillus spp", "micrococcus",
                  "saprophyticus")
_TK_VIRIDANS = ("viridans", "streptococcus mitis", "streptococcus oralis",
                "streptococcus sanguinis", "streptococcus salivarius")
_TK_ENTEROCOCCI = ("enterococc",)
_TK_STREP_PATHOGEN = ("pneumoniae", "pneumococc", "pyogenes", "agalactiae",
                      "group a", "group b")
_TK_CANDIDA = ("candida", "yeast")
_TK_GI_PATHOGEN = ("salmonella", "shigella", "campylobacter", "difficile",
                   "yersinia", "vibrio", "o157", "enterohemorrhagic",
                   "entamoeba", "listeria")
_TK_NEVER_CONTAMINANT_BLOOD = (
    "staphylococcus aureus", "s. aureus", "mrsa", "mssa", "lugdunensis",
    "pneumoniae", "pneumococc", "pyogenes", "agalactiae", "neisseria meningitidis",
    "haemophilus", "h. influenzae", "listeria", "salmonella", "candida",
    "brucella", "gonorrhoeae")
_TK_MENINGITIS = ("pneumoniae", "pneumococc", "meningitidis", "haemophilus",
                  "h. influenzae", "listeria", "agalactiae", "group b",
                  "cryptococc")
# Organisms that genuinely stain Gram-variable.
_TK_GRAM_VARIABLE = ("acinetobacter", "gardnerella", "bacillus", "clostridi",
                     "corynebacterium", "lactobacill", "mobiluncus", "actinomyces")


def _has(text: str, tokens) -> bool:
    low = (text or "").lower()
    return any(t in low for t in tokens)


def _is_cons(org_l: str) -> bool:
    return _has(org_l, _TK_SKIN_FLORA) or bool(re.search(r"(?<![a-z])cons(?![a-z])", org_l))


def _hf(host_factors, *tokens) -> bool:
    """Host-factor test that survives relabelling (substring, case-insensitive)."""
    for h in host_factors or []:
        hl = str(h).lower()
        if any(t in hl for t in tokens):
            return True
    return False


def _gram_type(org_l: str) -> Optional[str]:
    """Expected Gram morphology of the ISOLATE, or None when it has none to
    compare (mixed anaerobes, cell-wall-less organisms)."""
    if _has(org_l, ("mycoplasma", "ureaplasma", "anaerobes", "لاهوائ")):
        return None
    if "gram-variable" in org_l or "gram variable" in org_l:
        return "variable"
    if _has(org_l, ("acinetobacter", "haemophilus", "h. influenzae")):
        return "neg_coccobacilli"
    if _has(org_l, ("neisseria", "moraxella")):
        return "neg_cocci"
    if _has(org_l, _TK_ENTEROBACTERALES + _TK_NONFERMENTERS + (
            "legionella", "campylobacter", "vibrio", "gram-negative bacilli",
            "gram negative bacilli")):
        return "neg_rods"
    if _has(org_l, _TK_CANDIDA):
        return "yeast"
    if _has(org_l, ("staph", "strep", "enterococc", "mrsa", "mssa", "vre", "pneumococc",
                    "gram-positive cocci", "gram positive cocci", "micrococcus")) or _is_cons(org_l):
        return "pos_cocci"
    if _has(org_l, ("listeria", "corynebacterium", "bacillus", "clostridi",
                    "lactobacill", "diphtheroid", "cutibacterium", "propionibacterium",
                    "gardnerella", "actinomyces")):
        return "pos_rods"
    return None


def _stain_type(gram_stain: str) -> Optional[str]:
    g = (gram_stain or "").lower()
    if "variable" in g:
        return "variable"
    if "mixed" in g or "polymicrobial" in g:
        return "mixed"
    if "yeast" in g:
        return "yeast"
    if "positive cocci" in g:
        return "pos_cocci"
    if "negative rods" in g or "negative bacilli" in g:
        return "neg_rods"
    if "negative cocci" in g or "diplococci" in g:
        return "neg_cocci"
    if "positive rods" in g or "positive bacilli" in g:
        return "pos_rods"
    return None


_GRAM_LABEL = {"pos_cocci": "Gram-positive cocci", "neg_rods": "Gram-negative rods",
               "neg_cocci": "Gram-negative cocci", "pos_rods": "Gram-positive rods",
               "neg_coccobacilli": "Gram-negative coccobacilli", "yeast": "yeast",
               "variable": "Gram-variable", "mixed": "mixed flora"}
_GRAM_COMPATIBLE = {
    "pos_cocci": {"pos_cocci"},
    "neg_rods": {"neg_rods", "neg_coccobacilli"},
    "neg_coccobacilli": {"neg_rods", "neg_cocci", "neg_coccobacilli"},
    "neg_cocci": {"neg_cocci", "neg_coccobacilli"},
    "pos_rods": {"pos_rods"},
    "yeast": {"yeast"},
}


def _urine_threshold(collection: str, age, sex: str, symptomatic: bool, sci: bool,
                     catheterised: bool) -> Tuple[int, str]:
    """(CFU/mL threshold, the rule it comes from) for a urine culture."""
    c = (collection or "").lower()
    if "aspirate" in c or "spa" in c:
        return 100, "Suprapubic aspirate: any growth is significant (sterile sampling)"
    if "bag" in c:
        return 100000, ("Bag specimen: high contamination rate — a positive result must be "
                        "confirmed by catheter or SPA before treating (AAP)")
    if "condom" in c:
        return ((10000, "Condom catheter in spinal cord injury: >= 10^4 CFU/mL (NIDRR consensus)")
                if sci else (100000, "Condom catheter: >= 10^5 CFU/mL (IDSA CA-UTI 2009)"))
    if catheterised or "nephrostomy" in c or "conduit" in c:
        if symptomatic:
            return 1000, ("Catheter specimen with compatible symptoms: >= 10^3 CFU/mL "
                          "(IDSA CA-UTI 2009)")
        return 100000, ("Catheter specimen WITHOUT symptoms: >= 10^5 CFU/mL defines "
                        "catheter-associated asymptomatic bacteriuria — not an infection "
                        "(IDSA CA-UTI 2009)")
    if isinstance(age, (int, float)) and age < 2:
        return 50000, ("Infant < 2 yr (catheter/SPA): >= 5×10^4 CFU/mL of one uropathogen "
                       "WITH pyuria (AAP 2011, reaffirmed 2016)")
    if symptomatic:
        return 1000, ("Symptomatic patient, midstream urine: >= 10^3 CFU/mL of a uropathogen "
                      "(IDSA / EAU)")
    return 100000, ("No urinary symptoms: >= 10^5 CFU/mL defines asymptomatic bacteriuria "
                    "(IDSA ASB 2019)")


def _score_colony_count(state: str, cfu_val: int, age: int, sex: str,
                        symptomatic: bool = False, collection: str = "",
                        sci: bool = False, catheterised: bool = False):
    """(delta, positive_factor, negative_factor) for the colony-count field.

    v3: one threshold chosen by _urine_threshold(), then four outcomes —
    meets / borderline (within one log below) / below / no growth — so the
    score can only rise with the count ("no growth" always scores lowest).
    """
    if state == "unreported":
        return 0, None, ("ℹ️ Colony count not reported / unreadable — this field "
                         "contributed nothing to the score. Enter it for a "
                         "reliable assessment.")
    if state == "none":
        return -35, None, ("❌ No growth reported — strong evidence against "
                           "infection. If an organism was isolated, the colony "
                           "count and the culture result disagree; re-check the "
                           "report before treating.")
    thr, rule = _urine_threshold(collection, age, sex, symptomatic, sci, catheterised)
    if cfu_val >= thr:
        return 30, f"✅ Colony count {cfu_val:,} CFU/mL meets the threshold — {rule}", None
    if cfu_val * 10 >= thr:
        extra = ""
        if sci and "intermittent" in (collection or "").lower() and cfu_val >= 100:
            extra = (" In spinal cord injury on intermittent catheterisation >= 10^2 "
                     "CFU/mL counts when symptomatic (NIDRR consensus).")
        return 12, (f"➕ Colony count {cfu_val:,} CFU/mL is borderline (within one log of the "
                    f"threshold) — {rule}.{extra}"), None
    return -15, None, f"⚠️ Colony count {cfu_val:,} CFU/mL is below the threshold — {rule}"


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
    # v3
    collection_method: str = "",
) -> dict:
    """Pathogenicity engine v3 — is this isolate an infection, colonisation or
    contamination?

    Returns: {score, verdict, color, interpretation, recommendations,
              factors_pos, factors_neg, abu_detected, special_flags,
              engine_version, category, threshold, notes, missing_inputs,
              confidence, references, evidence}
    """
    specimen = specimen or ""
    organism = organism or ""
    symptoms = list(symptoms or [])
    host_factors = list(host_factors or [])
    sirs_criteria = list(sirs_criteria or [])
    culture_purity = culture_purity or ""
    urinalysis_result = urinalysis_result or ""
    gram_stain = gram_stain or ""
    blood_source = blood_source or ""
    wound_type = wound_type or ""
    collection_method = collection_method or ""
    # "مش محدد" (not specified) is the UI's empty choice, not a value.
    if "مش محدد" in blood_source:
        blood_source = ""
    if not isinstance(age, (int, float)):
        age = 40
    spec_lower = specimen.lower()
    org_l = re.sub(r"\s+", " ", organism.strip().lower())

    score = 0
    factors_pos: List[str] = []
    factors_neg: List[str] = []
    special_flags: List[str] = []
    notes: List[str] = []
    missing: List[str] = []
    references: List[str] = []
    evidence: List[Dict[str, Any]] = []
    threshold_text = ""
    abu_detected = False

    def add(domain: str, pts: int, text: Optional[str]) -> None:
        nonlocal score
        score += pts
        if text:
            (factors_pos if pts >= 0 else factors_neg).append(text)
        evidence.append({"domain": domain, "points": pts, "text": text or ""})

    # ── Host context shared by every specimen ────────────────────────────────
    sci_quad = _hf(host_factors, "quadripleg", "tetrapleg", "cervical cord")
    sci = sci_quad or _hf(host_factors, "parapleg", "spinal cord")
    neurogenic = sci or _hf(host_factors, "neurogenic")
    immuno = _hf(host_factors, "immunosupp", "steroid", "neutropen", "transplant")
    neutropenic = _hf(host_factors, "neutropen")
    pregnant = _hf(host_factors, "pregnan")
    uro_procedure = _hf(host_factors, "pre-surgical", "urologic procedure")
    has_line = _hf(host_factors, "central line", "picc")
    has_prosthesis = _hf(host_factors, "prosthetic", "pacemaker", "graft")
    has_cns_device = _hf(host_factors, "shunt", "evd", "neurosurg")
    ventilated = _hf(host_factors, "tracheostomy", "ventilat")
    if sci:
        special_flags.append("SCI")

    is_enterobacterales = _has(org_l, _TK_ENTEROBACTERALES)
    is_nonfermenter = _has(org_l, _TK_NONFERMENTERS)
    is_saureus = _has(org_l, _TK_SAUREUS)
    is_cons = _is_cons(org_l) and not is_saureus
    is_staph_unspeciated = ("staphylococcus spp" in org_l
                            or "gram-positive cocci" in org_l or "gram positive cocci" in org_l)
    is_viridans = _has(org_l, _TK_VIRIDANS)
    # Unspeciated streptococci are NOT assumed to be viridans flora: the same
    # label covers S. pneumoniae, S. pyogenes and the anginosus group.
    is_strep_unspeciated = org_l.startswith("streptococcus spp")
    is_enterococcus = _has(org_l, _TK_ENTEROCOCCI) or org_l == "vre"
    is_candida = _has(org_l, _TK_CANDIDA)
    is_gnb_unidentified = "gram-negative bacilli" in org_l or "gram negative bacilli" in org_l
    # "Klebsiella spp." / "Salmonella spp." are this app's ordinary labels for
    # those genera, not a statement that identification is incomplete.
    _standard_spp = ("klebsiella spp", "salmonella spp", "shigella spp",
                     "providencia spp", "mycoplasma spp")
    unspeciated = (("spp" in org_l and not _has(org_l, _standard_spp))
                   or "unspeciated" in org_l or "unidentified" in org_l)
    if unspeciated:
        special_flags.append("UNSPECIATED_ORGANISM")
        notes.append("🔬 الكائن غير محدد النوع — التقييم مبني على الجنس/صبغة Gram فقط. "
                     "تحديد النوع (ID) يغيّر التفسير في بعض الحالات (مثل Staphylococcus: "
                     "S. aureus ممرض دائماً، والسالب للتخثّر ملوِّث شائع).")

    # ══════════════════════════════════════════════════════════════════
    # URINE
    # ══════════════════════════════════════════════════════════════════
    if "urine" in spec_lower:
        references += ["IDSA Asymptomatic Bacteriuria 2019", "IDSA CA-UTI 2009",
                       "IDSA cUTI 2025", "AAP UTI 2011 (reaffirmed 2016)"]
        coll_l = collection_method.lower()
        catheterised = (any(k in coll_l for k in ("indwelling", "foley", "intermittent",
                                                  "suprapubic catheter", "nephrostomy", "conduit"))
                        or _hf(host_factors, "urinary catheter"))
        infant = age < 2
        if infant:
            special_flags.append("PEDIATRIC_UTI")

        # ── Symptoms: specific / SCI-specific / non-specific / not stated ────
        _specific = {"Dysuria / Frequency / Urgency", "Suprapubic pain / tenderness",
                     "Acute haematuria"}
        _upper = {"Fever (> 38°C)", "Flank pain / Loin pain", "Rigors / Hypotension (sepsis)"}
        _sci_sym = {"Increased spasticity (SCI)", "Autonomic dysreflexia (SCI)",
                    "Malaise / Lethargy / Sense of unease (SCI)",
                    "New incontinence / Leaking around catheter"}
        sym = set(symptoms)
        has_upper = bool(sym & _upper)
        has_specific = bool(sym & _specific)
        has_sci_sym = bool(sym & _sci_sym) and (neurogenic or catheterised)
        infant_nonspecific = infant and bool(sym & {"Nausea / Vomiting", "Abdominal pain"})
        symptomatic = has_upper or has_specific or has_sci_sym or infant_nonspecific
        explicit_asym = ("Asymptomatic" in sym) and not symptomatic
        only_nonspecific = bool(sym) and not symptomatic and not explicit_asym
        symptoms_stated = bool(sym)

        if has_upper:
            add("symptoms", 30, "✅ Fever / flank pain / sepsis — upper-tract or systemic infection")
            special_flags.append("UPPER_UTI_FEATURES")
        elif has_specific:
            add("symptoms", 25, "✅ Urinary symptoms present (dysuria / frequency / urgency / suprapubic pain)")
        elif has_sci_sym:
            add("symptoms", 22, "✅ Symptoms compatible with UTI in neurogenic bladder / catheter "
                                "(spasticity, autonomic dysreflexia, malaise, new leakage) — IDSA 2009")
        elif infant_nonspecific:
            add("symptoms", 15, "➕ Non-specific symptoms in an infant — UTI presents this way under 2 yr")
        elif explicit_asym:
            add("symptoms", -20, "⚠️ Asymptomatic — bacteriuria without symptoms is not a UTI")
        elif only_nonspecific:
            add("symptoms", -10, "⚠️ Only non-specific findings (cloudy/smelly urine, confusion, "
                                 "abdominal pain) — none is an indication to treat bacteriuria")
        else:
            missing.append("Symptoms")
            special_flags.append("SYMPTOMS_NOT_STATED")
        if "Cloudy / Foul-smelling urine only" in sym:
            notes.append("ℹ️ البول العكر أو كريه الرائحة وحده ليس دليلاً على عدوى ولا داعياً للمزرعة "
                         "أو العلاج (IDSA CA-UTI 2009).")
        if "Confusion / Delirium only (no urinary symptoms)" in sym and not symptomatic:
            notes.append("ℹ️ تشوش/هذيان بلا أعراض بولية ولا حمى في مريض مسن: ابحث عن سبب آخر "
                         "وراقب بدل علاج الـ bacteriuria (IDSA ASB 2019).")

        # ── Organism ─────────────────────────────────────────────────────────
        if (is_enterobacterales or "pseudomonas" in org_l or is_enterococcus
                or "saprophyticus" in org_l or is_gnb_unidentified):
            add("organism", 15, f"✅ {organism} -- recognised uropathogen")
        elif is_saureus:
            add("organism", -5, f"⚠️ {organism} in urine is unusual without a catheter or urological "
                                "procedure — consider haematogenous seeding")
            special_flags.append("SAUREUS_BACTERIURIA")
            notes.append("🔴 S. aureus في البول بلا قسطرة أو تدخل بولي: قد يكون انعكاساً لـ bacteremia "
                         "— اسحب مزارع دم قبل اعتباره تلوثاً.")
        elif "agalactiae" in org_l or "group b" in org_l:
            add("organism", 5, f"➕ {organism} -- occasional uropathogen")
            if pregnant:
                special_flags.append("GBS_BACTERIURIA_PREGNANCY")
                notes.append("🤰 GBS في بول الحامل بأي عدد = استعمار كثيف: وقاية أثناء الولادة (ACOG 797)؛ "
                             "العلاج قبل الولادة فقط عند ≥ 10⁵ أو أعراض.")
        elif is_strep_unspeciated:
            add("organism", -5, f"⚠️ {organism} -- streptococci are uncommon uropathogens (Group B "
                                "excepted); speciate before interpreting")
        elif is_candida:
            add("organism", -10, f"⚠️ {organism} -- candiduria is usually colonisation; treat only "
                                 "if symptomatic, neutropenic or before a urological procedure (IDSA 2016)")
        elif is_cons or is_viridans or _has(org_l, ("lactobacill", "gardnerella")):
            add("organism", -5 if catheterised else -20,
                f"⚠️ {organism} -- skin / urethral / vaginal flora; usually contamination"
                + (" (can be significant with a catheter or stent)" if catheterised else ""))
        elif is_nonfermenter:
            add("organism", 8 if (catheterised or neurogenic) else 0,
                f"➕ {organism} -- healthcare-associated uropathogen (catheter, neurogenic bladder, "
                "recent antibiotics); colonisation is common")
        else:
            add("organism", 5, f"➕ {organism} -- occasional uropathogen")

        # ── Colony count against the threshold that applies ──────────────────
        cfu_val = _parse_cfu(colony_count_text)
        cfu_state = _cfu_report_state(colony_count_text)
        _thr, threshold_text = _urine_threshold(collection_method, age, sex, symptomatic,
                                                sci, catheterised)
        if not symptoms_stated:
            threshold_text = "Symptoms not entered — threshold shown assumes none. " + threshold_text
        _d, _pos, _neg = _score_colony_count(cfu_state, cfu_val, age, sex,
                                             symptomatic=symptomatic,
                                             collection=collection_method,
                                             sci=sci, catheterised=catheterised)
        add("colony_count", _d, _pos or _neg)
        if cfu_state == "unreported":
            special_flags.append("CFU_NOT_REPORTED")
            missing.append("Colony count")
        if "bag" in coll_l:
            special_flags.append("BAG_SPECIMEN")
            notes.append("👶 عينة الكيس: نسبة تلوث عالية جداً — النتيجة السلبية تنفي العدوى، والإيجابية "
                         "لازم تتأكد بقسطرة أو SPA قبل العلاج (AAP).")
        if not collection_method or "مش محدد" in collection_method:
            if catheterised or neurogenic or infant:
                missing.append("Urine collection method")

        # ── Pyuria ───────────────────────────────────────────────────────────
        pus_val = _parse_pus(pus_cells_text)
        ua_l = urinalysis_result.lower()
        if catheterised or neurogenic:
            # IDSA 2009: pyuria does not separate CA-UTI from CA-ASB; its
            # ABSENCE points away from UTI.
            if pus_val is not None and pus_val < 5 and not neutropenic:
                add("pyuria", -15, f"⚠️ No pyuria ({pus_val} WBC/HPF) — in a catheterised / "
                                   "neurogenic bladder this suggests a diagnosis other than UTI")
            elif pus_val is not None:
                add("pyuria", 0, None)
                notes.append("ℹ️ الـ pyuria مع القسطرة أو المثانة العصبية شائعة بلا عدوى — لا تُحتسب "
                             "دليلاً على UTI ولا داعياً للعلاج (IDSA CA-UTI 2009).")
        elif pus_val is not None:
            if pus_val > 10:
                add("pyuria", 15, f"✅ Significant pyuria ({pus_val} WBC/HPF)")
            elif pus_val >= 5:
                add("pyuria", 8, f"➕ Mild pyuria ({pus_val} WBC/HPF)")
            elif neutropenic:
                add("pyuria", 0, None)
                notes.append("ℹ️ غياب الـ pyuria لا ينفي العدوى في مريض neutropenic.")
            else:
                add("pyuria", -15, f"⚠️ No/minimal pyuria ({pus_val} WBC/HPF) -- argues against UTI")
        elif "طبيعي" in urinalysis_result or "normal" in ua_l:
            add("pyuria", -20, "❌ Normal urinalysis -- strongly suggests contamination")
        elif "pyuria" in ua_l or "wbc" in ua_l:
            add("pyuria", 10, "✅ Pyuria noted on urinalysis")
        elif "nitrit" in ua_l:
            add("pyuria", 8, "➕ Nitrites positive -- Enterobacterales bacteriuria")
        else:
            missing.append("Pyuria / urinalysis")

        # ── Asymptomatic bacteriuria (IDSA 2019: count + no symptoms) ────────
        # "No urinary-specific symptom" covers the explicit "Asymptomatic" and
        # the findings IDSA says must not be treated as UTI on their own
        # (cloudy / smelly urine, delirium without urinary symptoms).
        _sig_count = cfu_state == "counted" and cfu_val >= 100000
        if (explicit_asym or only_nonspecific) and _sig_count:
            abu_detected = True
            special_flags.append("ABU_DETECTED")
            if catheterised:
                special_flags.append("CA_ASB")
            if sex == "Female" and not catheterised:
                notes.append("ℹ️ تعريف ABU في النساء يتطلب عينتين متتاليتين بنفس الكائن ≥ 10⁵ "
                             "(IDSA 2019)؛ عينة واحدة تكفي في الرجال.")
            if pregnant or uro_procedure:
                add("abu", 20, "✅ Asymptomatic bacteriuria in pregnancy / before a urological "
                               "procedure with mucosal trauma -- TREAT (IDSA 2019)")
                special_flags.append("ABU_TREAT")
            else:
                add("abu", -20, "⚠️ Asymptomatic bacteriuria -- do NOT treat (IDSA 2019)")
                special_flags.append("ABU_NO_TREAT")
        elif pregnant and _sig_count and not symptomatic:
            notes.append("🤰 حامل + bacteriuria ≥ 10⁵: إن كانت بلا أعراض فهي ABU تُعالَج في الحمل "
                         "(IDSA 2019) — حدّد الأعراض.")

        # ── Spinal cord injury / neurogenic bladder ──────────────────────────
        if neurogenic:
            notes.append(
                "♿ إصابة النخاع الشوكي / المثانة العصبية: الـ bacteriuria والـ pyuria شبه دائمة — "
                "لا تُفحص ولا تُعالَج بلا أعراض (IDSA ASB 2019، توصية قوية). الأعراض هنا غير "
                "نمطية: حمى، زيادة التشنج (spasticity)، autonomic dysreflexia، إحساس بالتوعك، "
                "تسريب جديد حول القسطرة — وليست الحرقان.")
            notes.append(
                "♿ عند العلاج: غيّر القسطرة إذا مرّ عليها ≥ أسبوعين وخذ المزرعة من الجديدة؛ "
                "المدة 7 أيام مع استجابة سريعة و10–14 يوم مع استجابة متأخرة (IDSA CA-UTI 2009). "
                "احتمال الكائنات المقاومة أعلى (مضادات متكررة) — اعتمد على الحساسية.")
            if not symptoms_stated:
                notes.append("♿ الأعراض غير مُدخلة: في إصابة النخاع الشوكي لا يمكن تفسير المزرعة بدونها.")

        if infant:
            notes.append("👶 رضيع < سنتين: UTI = pyuria + ≥ 5×10⁴ CFU/mL لكائن واحد من قسطرة أو SPA "
                         "(AAP). أي UTI مؤكد يُعالَج.")
        if sex == "Male" and symptomatic and age >= 15:
            notes.append("♂ UTI في الذكور: فكّر في البروستاتا (مدة أطول واختيار دواء يخترقها) عند "
                         "الحمى أو التكرار.")

    # ══════════════════════════════════════════════════════════════════
    # SPUTUM / RESPIRATORY
    # ══════════════════════════════════════════════════════════════════
    elif any(k in spec_lower for k in ("sputum", "respiratory", "bal", "tracheal", "eta")):
        references += ["ATS/IDSA HAP/VAP 2016", "ATS/IDSA CAP 2019",
                       "Murray & Washington 1975 (sputum quality)"]
        mw_pus = _parse_pus(sputum_pus_cells)
        mw_epith = _parse_pus(sputum_epithelial)
        invasive = any(k in spec_lower for k in ("bal", "tracheal", "eta", "psb"))

        if not invasive:
            if mw_pus is not None and mw_epith is not None:
                if mw_pus >= 25 and mw_epith < 10:
                    add("quality", 25, "✅ Murray-Washington: WBC ≥ 25, epithelial < 10 /LPF -- adequate sputum")
                    special_flags.append("MW_ADEQUATE")
                elif mw_pus >= 25 and mw_epith >= 10:
                    add("quality", 8, "➕ Murray-Washington: WBC ≥ 25 but epithelial ≥ 10 -- mixed quality")
                    special_flags.append("MW_MIXED")
                elif mw_epith >= 25:
                    add("quality", -20, "❌ Murray-Washington: epithelial ≥ 25 /LPF -- saliva, reject specimen")
                    special_flags.append("MW_REJECT")
                else:
                    add("quality", 0, None)
            elif mw_epith is not None and mw_epith >= 25:
                add("quality", -20, "❌ Epithelial cells ≥ 25 /LPF -- specimen inadequate (saliva)")
                special_flags.append("MW_REJECT")
            else:
                missing.append("Sputum quality (WBC / epithelial cells per LPF)")
        else:
            cfu_val = _parse_cfu(colony_count_text)
            if _cfu_report_state(colony_count_text) == "counted":
                thr = 10000 if "bal" in spec_lower else 1000 if "psb" in spec_lower else 100000
                threshold_text = (f"Quantitative lower-respiratory culture: >= {thr:,} CFU/mL "
                                  "(BAL 10^4 · PSB 10^3 · endotracheal aspirate 10^5; ATS/IDSA 2016)")
                if cfu_val >= thr:
                    add("colony_count", 20, f"✅ {cfu_val:,} CFU/mL meets the quantitative threshold")
                else:
                    add("colony_count", -15, f"⚠️ {cfu_val:,} CFU/mL is below the quantitative "
                                             "threshold -- colonisation more likely")
            else:
                missing.append("Quantitative count (BAL / ETA)")

        if _has(org_l, ("pneumoniae", "pneumococc", "haemophilus", "h. influenzae",
                        "moraxella", "legionella", "mycoplasma")) or is_saureus:
            add("organism", 20, f"✅ {organism} -- recognised respiratory pathogen")
        elif is_strep_unspeciated:
            add("organism", 0, f"➕ {organism} -- could be S. pneumoniae or oral streptococci; "
                               "optochin / bile solubility decides")
        elif is_enterobacterales or is_nonfermenter or is_gnb_unidentified:
            add("organism", 10, f"➕ {organism} -- respiratory pathogen in hospital / ventilated / "
                                "structural lung disease; frequent airway coloniser otherwise")
        elif is_candida:
            add("organism", -25, f"⚠️ {organism} -- Candida in respiratory specimens is colonisation; "
                                 "Candida pneumonia is exceptionally rare -- do not treat")
            special_flags.append("RESPIRATORY_CANDIDA")
        elif is_cons or is_viridans or is_enterococcus or _has(org_l, ("neisseria spp", "corynebacterium")):
            add("organism", -20, f"⚠️ {organism} -- oropharyngeal flora; not a cause of pneumonia")
        else:
            add("organism", 5, f"➕ {organism} -- uncommon respiratory isolate; correlate")

        resp = [s for s in symptoms if s in ("Productive cough / Purulent sputum", "Fever (> 38°C)",
                                             "Dyspnea", "Pleuritic chest pain",
                                             "Worsening oxygenation / ventilator settings")]
        if "New infiltrate on chest imaging" in symptoms:
            add("imaging", 20, "✅ New infiltrate on chest imaging -- pneumonia requires this")
        elif symptoms:
            notes.append("🩻 تشخيص الالتهاب الرئوي يحتاج ارتشاحاً جديداً في الأشعة — المزرعة وحدها "
                         "لا تكفي (ATS/IDSA).")
        if len(resp) >= 2:
            add("symptoms", 20, f"✅ {len(resp)} respiratory signs/symptoms present")
        elif len(resp) == 1:
            add("symptoms", 10, "➕ 1 respiratory sign/symptom present")
        elif not symptoms:
            missing.append("Respiratory signs / imaging")
        if ventilated:
            notes.append("🫁 مريض على tracheostomy/جهاز تنفس: استعمار مجرى الهواء شبه دائم — "
                         "VAP يُشخَّص بارتشاح جديد + علامتين سريريتين + مزرعة كمية، لا بالمزرعة وحدها "
                         "(ATS/IDSA 2016).")
        if sci_quad:
            notes.append("♿ Quadriplegia: ضعف السعال وعضلات التنفس ← احتباس إفرازات وشفط متكرر؛ "
                         "الالتهاب الرئوي من أهم أسباب الوفاة في الإصابات العنقية — عتبة الاشتباه "
                         "منخفضة عند وجود حمى أو تغيّر الإفرازات أو الأكسجة، لكن الاستعمار "
                         "(خاصة مع tracheostomy) شائع ولا يُعالَج وحده.")
        elif sci:
            notes.append("♿ Paraplegia: الإصابات الصدرية العليا تُضعف السعال — قيّم سريرياً وبالأشعة.")

    # ══════════════════════════════════════════════════════════════════
    # BLOOD
    # ══════════════════════════════════════════════════════════════════
    elif "blood" in spec_lower:
        references += ["CLSI M47 (blood cultures)", "IDSA CLABSI 2009",
                       "Weinstein 1997 / Doern 2019 (contaminant criteria)"]
        multiple = "multiple" in blood_source.lower()
        single = "single" in blood_source.lower()
        contaminant_org = is_cons or is_viridans or _has(org_l, ("micrococcus", "bacillus spp",
                                                                 "cutibacterium", "propionibacterium"))

        if _has(org_l, _TK_NEVER_CONTAMINANT_BLOOD):
            add("organism", 45, f"🔴 {organism} في الدم لا يُعد ملوِّثاً أبداً — عزلة واحدة كافية. "
                                "ابدأ العلاج فوراً ولا تنتظر إعادة المزرعة.")
            special_flags.append("NEVER_CONTAMINANT")
        elif is_enterobacterales or is_nonfermenter or is_enterococcus or is_gnb_unidentified \
                or _has(org_l, ("anaerobes", "bacteroides", "لاهوائ")):
            add("organism", 70, f"✅ {organism} -- true bloodstream pathogen; a single positive "
                                "bottle is significant")
            special_flags.append("BLOOD_TRUE_PATHOGEN")
        elif contaminant_org:
            add("organism", -15, f"⚠️ {organism} -- common blood-culture contaminant; significance "
                                 "needs the same organism in ≥ 2 separately drawn sets")
            special_flags.append("BLOOD_CONTAMINANT_RISK")
        elif is_strep_unspeciated:
            add("organism", 55, f"✅ {organism} -- streptococci in blood are usually significant "
                                "(pneumococcus, beta-haemolytic, anginosus group, endocarditis); a "
                                "single bottle of viridans streptococci can be contamination -- speciate")
        elif is_staph_unspeciated:
            # Never "contaminant" before identification: this label includes
            # S. aureus. The floor below keeps the verdict at "possible".
            add("organism", 45, f"➕ {organism} -- cannot be interpreted until speciated: clusters = "
                                "staphylococci (coagulase decides), chains/pairs = streptococci/enterococci")
            special_flags.append("BLOOD_PENDING_ID")
            notes.append("🔬 Gram-positive cocci في الدم قبل التعريف: عامِلها كـ S. aureus محتملة "
                         "(تغطية MRSA) لحين ظهور الـ coagulase/ID إذا كان المريض غير مستقر.")
        else:
            add("organism", 45, f"➕ {organism} -- possible bloodstream pathogen")

        if multiple:
            # For skin flora this is THE criterion: it outweighs the organism
            # penalty above (same organism in >= 2 separately drawn sets).
            add("bottles", 65 if contaminant_org else 15,
                "✅ Same organism in multiple sets -- true bacteraemia")
            if contaminant_org:
                special_flags.append("MULTI_SET_SKIN_FLORA")
        elif single and contaminant_org:
            add("bottles", -20, "⚠️ Single positive bottle + skin-flora organism -- contamination likely")
        elif not blood_source:
            if contaminant_org:
                missing.append("Number of positive sets / bottles")
        if blood_source and "source" in blood_source.lower():
            add("source", 10, f"➕ Source identified: {blood_source}")

        sirs_count = len(sirs_criteria)
        if sirs_count >= 3:
            add("sirs", 20, f"✅ {sirs_count}/4 SIRS criteria met -- sepsis probable")
            special_flags.append("SIRS_HIGH")
        elif sirs_count == 2:
            add("sirs", 15, "➕ 2/4 SIRS criteria met")
            special_flags.append("SIRS_MET")
        elif sirs_count == 1:
            add("sirs", 5, "➕ 1 SIRS criterion")
        elif contaminant_org:
            missing.append("SIRS criteria")
        if contaminant_org and (has_line or has_prosthesis or has_cns_device):
            add("device", 15, "➕ Intravascular / prosthetic device -- coagulase-negative staphylococci "
                              "are the leading cause of line and prosthetic-valve infection")
            notes.append("🩸 CoNS مع قسطرة مركزية أو صمام صناعي: اسحب مجموعتين (واحدة طرفية) قبل الحكم؛ "
                         "نفس الكائن في المجموعتين = CLABSI محتمل (IDSA 2009).")
        if contaminant_org and age < 1:
            add("neonate", 10, "➕ Infant < 1 yr -- CoNS is a true pathogen in neonates with lines")
        if is_saureus:
            notes.append("🔴 S. aureus bacteremia: مزارع دم متكررة كل 24–48 ساعة حتى السلبية، echo، "
                         "بحث عن المصدر وإزالته، وعلاج وريدي ≥ 14 يوم (غير المعقدة) — استشارة ID تقلل الوفيات.")
        if sci:
            notes.append("♿ إصابة النخاع الشوكي مع bacteremia: المصادر الأشيع المسالك البولية، قرح "
                         "الفراش/التهاب العظم تحتها، والالتهاب الرئوي — الحمى قد تكون العلامة الوحيدة.")

    # ══════════════════════════════════════════════════════════════════
    # CSF
    # ══════════════════════════════════════════════════════════════════
    elif "csf" in spec_lower or "cerebrospinal" in spec_lower:
        references += ["IDSA Bacterial Meningitis 2004",
                       "IDSA Healthcare-Associated Ventriculitis and Meningitis 2017"]
        skin_flora = is_cons or is_viridans or _has(org_l, ("cutibacterium", "propionibacterium",
                                                            "bacillus spp", "micrococcus"))
        if skin_flora and not has_cns_device:
            add("organism", 35, f"⚠️ {organism} in CSF without a shunt, drain or recent neurosurgery -- "
                                "the commonest CSF contaminant")
            special_flags.append("CSF_SKIN_FLORA")
        elif skin_flora and has_cns_device:
            add("organism", 75, f"🔴 {organism} with a CSF shunt / drain / recent neurosurgery -- "
                                "device-associated ventriculitis until proven otherwise")
            special_flags += ["CSF_ALWAYS_SIGNIFICANT", "CSF_DEVICE"]
        else:
            add("organism", 80, "✅ CSF -- growth of this organism from a sterile site is "
                                "clinically significant")
            special_flags.append("CSF_ALWAYS_SIGNIFICANT")

    # ══════════════════════════════════════════════════════════════════
    # STOOL / GI
    # ══════════════════════════════════════════════════════════════════
    elif "stool" in spec_lower or "fecal" in spec_lower or "rectal" in spec_lower:
        references += ["IDSA Infectious Diarrhea 2017", "IDSA/SHEA C. difficile 2021"]
        if _has(org_l, _TK_GI_PATHOGEN):
            add("organism", 45, f"✅ {organism} -- enteric pathogen; always clinically significant")
            special_flags.append("GI_TRUE_PATHOGEN")
        elif is_enterobacterales or is_enterococcus or is_candida or is_nonfermenter:
            add("organism", -15, f"⚠️ {organism} -- normal or transient bowel flora; not a cause of diarrhoea")
        else:
            add("organism", 10, f"➕ {organism} -- potential GI pathogen; correlate clinically")
        gi = [s for s in symptoms if s in ("Fever (> 38°C)", "Bloody diarrhea", "Watery diarrhea",
                                           "Vomiting", "Abdominal cramps")]
        if len(gi) >= 2:
            add("symptoms", 25, f"✅ {len(gi)} GI symptoms -- supports true infection")
        elif len(gi) == 1:
            add("symptoms", 10, "➕ 1 GI symptom")
        elif not symptoms:
            missing.append("GI symptoms")
        notes.append("ℹ️ أغلب عدوى الأمعاء: علاج داعم (سوائل وأملاح). المضاد الحيوي فقط عند: إسهال "
                     "دموي مع حمى، نقص مناعة، رضيع < 3 شهور، Shigella، التيفود، C. difficile، أو حالة شديدة.")
        if "salmonella" in org_l and (immuno or age < 1 or age >= 50):
            notes.append("⚠️ Salmonella غير التيفية: يُعالَج عند نقص المناعة، الرضع < 3 شهور، و > 50 سنة "
                         "مع مرض وعائي/صمامات (خطر bacteremia وعدوى وعائية).")

    # ══════════════════════════════════════════════════════════════════
    # WOUND / PUS
    # ══════════════════════════════════════════════════════════════════
    elif any(w in spec_lower for w in ("wound", "pus", "abscess", "swab", "tissue")):
        references += ["IDSA SSTI 2014", "IWGDF/IDSA Diabetic Foot Infection 2023",
                       "NPIAP/EPUAP Pressure Injury Guideline 2019"]
        wl = wound_type.lower()
        aspirate = ("pus" in spec_lower or "abscess" in spec_lower or "tissue" in spec_lower
                    or "abscess" in wl)
        chronic = "chronic" in wl or "diabetic" in wl
        pressure = "pressure" in wl or "bed sore" in wl
        signs = [s for s in symptoms if s in ("Erythema / Warmth / Swelling", "Purulent discharge",
                                              "Fever (> 38°C)", "Pain / Tenderness")]
        skin_flora = is_cons or is_viridans or _has(org_l, ("micrococcus",))

        if skin_flora:
            add("organism", -15, f"⚠️ {organism} -- skin flora; usually colonisation of the wound surface")
        elif is_saureus or _has(org_l, ("pyogenes", "group a", "agalactiae", "group b",
                                        "anaerobes", "لاهوائ", "pasteurella")):
            add("organism", 25, f"✅ {organism} -- recognised wound / soft-tissue pathogen")
        elif is_enterobacterales or is_nonfermenter or is_enterococcus or is_gnb_unidentified:
            add("organism", 12, f"➕ {organism} -- pathogen in surgical, burn and deep wounds; "
                                "frequent coloniser of chronic wound surfaces")
        elif is_candida:
            add("organism", -10, f"⚠️ {organism} -- usually colonisation of a wound surface")
        else:
            add("organism", 10, f"➕ {organism} -- possible wound pathogen")

        if aspirate:
            add("specimen", 15, "✅ Pus / aspirate / tissue -- reflects the infected compartment, "
                                "not the surface")
        elif chronic or pressure:
            add("specimen", -10, "⚠️ Surface swab of a chronic wound / pressure ulcer -- grows the "
                                 "colonising flora; deep tissue after debridement is the valid specimen")
            special_flags.append("CHRONIC_WOUND_SWAB")
        if "surgical" in wl or "post-op" in wl:
            add("wound_type", 10, "➕ Surgical site -- growth with local signs = surgical site infection")
        elif "burn" in wl:
            add("wound_type", 5, "➕ Burn wound -- colonisation is universal; quantitative biopsy or "
                                 "clinical invasion defines infection")
        elif "bite" in wl:
            add("wound_type", 10, "➕ Bite wound -- polymicrobial oral flora, treat on clinical grounds")
        elif "superficial" in wl:
            add("wound_type", -5, "⚠️ Superficial wound -- assess depth and clinical signs")
        no_signs = "No local signs of infection" in symptoms and not signs
        if len(signs) >= 2:
            add("signs", 25, f"✅ {len(signs)} local/systemic signs of infection (≥ 2 = clinical infection)")
        elif len(signs) == 1:
            add("signs", 10, "➕ 1 sign of infection")
        elif no_signs:
            add("signs", -15, "⚠️ No local signs of infection -- growth without inflammation is colonisation")
        else:
            missing.append("Local signs of infection")
        # Only when the signs were actually assessed: "not entered" is not "absent".
        if (chronic or pressure) and (no_signs or len(signs) == 1):
            special_flags.append("WOUND_COLONISATION_LIKELY")
        if pressure or (sci and (chronic or not wl or "مش محدد" in wl)):
            notes.append("♿ قرح الفراش (شائعة مع Paraplegia/Quadriplegia): المسحة السطحية تعكس الاستعمار "
                         "فقط — العدوى تُشخَّص سريرياً (احمرار منتشر، صديد، رائحة، حمى، عدم التئام). "
                         "العينة الصحيحة نسيج عميق بعد التنضيف، وعند انكشاف العظم أو جرح لا يلتئم: "
                         "خزعة عظم لتشخيص التهاب العظم (osteomyelitis).")
        if chronic:
            notes.append("🦶 الجروح المزمنة/القدم السكري: لا تُزرع ولا تُعالَج قرحة بلا علامات عدوى "
                         "سريرية (≥ 2 علامة موضعية) — IWGDF/IDSA 2023.")

    else:
        missing.append("Specimen type not recognised")

    # ══════════════════════════════════════════════════════════════════
    # Shared: purity, Gram stain, host
    # ══════════════════════════════════════════════════════════════════
    _polymicrobial_ok = ("urine" in spec_lower and (_hf(host_factors, "urinary catheter")
                                                    or "catheter" in collection_method.lower()))
    if culture_purity == "Pure growth":
        add("purity", 10, "✅ Pure culture -- supports true infection")
    elif culture_purity == "Mixed growth":
        if _polymicrobial_ok:
            add("purity", -5, "⚠️ Mixed growth -- common with long-term catheters; interpret each "
                              "organism against symptoms")
        elif any(w in spec_lower for w in ("wound", "pus", "abscess", "swab")):
            add("purity", -5, "⚠️ Mixed growth -- expected in chronic wounds and abscesses below "
                              "the diaphragm; less so in a clean surgical site")
        else:
            add("purity", -15, "⚠️ Mixed growth -- suggests contamination")

    g_l = gram_stain.lower()
    stain_done = bool(gram_stain) and "مش متعملة" not in gram_stain
    st_type = _stain_type(gram_stain)
    iso_type = _gram_type(org_l)
    wbc_seen = "wbcs +" in g_l or g_l.startswith("wbcs")
    no_org = "no organisms" in g_l or "طبيعية" in gram_stain or "wbcs بدون organisms" in g_l
    if stain_done:
        if "wbcs بدون organisms" in g_l:
            add("gram_stain", 0, None)
            notes.append("🔬 خلايا صديدية بلا كائنات في الصبغة: مضاد حيوي سابق، حمل بكتيري قليل، أو "
                         "كائن لا يُصبغ (Mycoplasma / Legionella / Mycobacteria).")
        elif no_org:
            add("gram_stain", -8, "⚠️ Gram stain: no organisms seen")
        elif wbc_seen:
            add("gram_stain", 12, "✅ Gram stain: organisms WITH inflammatory cells -- supports infection")
        elif "بدون wbcs" in g_l or "without" in g_l:
            if immuno:
                add("gram_stain", 3, "➕ Organisms without WBCs -- expected when neutropenic / "
                                     "immunosuppressed")
            else:
                add("gram_stain", -5, "⚠️ Organisms WITHOUT inflammatory cells -- colonisation or "
                                      "contamination more likely")
        if st_type == "variable":
            special_flags.append("GRAM_VARIABLE")
            if _has(org_l, _TK_GRAM_VARIABLE):
                notes.append(f"🔬 Gram-variable متوافق مع {organism}: "
                             + ("Acinetobacter يقاوم إزالة اللون ويظهر coccobacilli موجبة/متغيرة "
                                "وقد يُخلط بالمكورات الموجبة أو Neisseria."
                                if "acinetobacter" in org_l else
                                "هذا الجنس معروف بالتلوّن المتغير، خاصة في المزارع القديمة."))
            else:
                notes.append("🔬 Gram-variable: ليس نوعاً من البكتيريا بل نتيجة صبغة. الأسباب: "
                             "كائنات متغيرة التلوّن فعلاً (Acinetobacter، Gardnerella، Bacillus/"
                             "Clostridium في المزارع القديمة، Corynebacterium، Actinomyces)، مزرعة "
                             "عمرها > 24 ساعة، مضاد حيوي سابق يُتلف الجدار، أو خطأ في إزالة اللون. "
                             "أعِد الصبغة من مزرعة عمرها 18–24 ساعة مع شريحة ضابطة، واعتمد على التعريف "
                             "(ID) لا على الصبغة.")
        elif st_type == "mixed":
            notes.append("🔬 فلورا مختلطة في الصبغة: تلوث بفلورا الموقع أو عدوى متعددة الميكروبات "
                         "(بطن، قدم سكري، شفط) — الكائن المعزول قد لا يكون الوحيد.")
        elif st_type and iso_type and iso_type != "variable" \
                and st_type not in _GRAM_COMPATIBLE.get(iso_type, {iso_type}):
            add("gram_stain", -10, f"⚠️ Gram stain shows {_GRAM_LABEL.get(st_type, st_type)} but the "
                                   f"culture grew {organism} ({_GRAM_LABEL.get(iso_type, iso_type)}) -- "
                                   "stain/culture discordance")
            special_flags.append("GRAM_DISCORDANT")
            notes.append("🔬 عدم توافق الصبغة مع المزرعة: عدوى مختلطة لم ينمُ أحد كائناتها (لاهوائي/"
                         "متطلب)، ملوِّث طغى في المزرعة، مضاد حيوي سابق، أو خطأ صبغ — راجع الشريحة "
                         "والأطباق قبل اعتماد العزلة كمسبب.")
        elif st_type and iso_type and iso_type != "variable":
            add("gram_stain", 5, "✅ Gram stain morphology matches the isolate")

    if immuno:
        add("host", 5, "➕ Immunocompromised -- lower threshold to act; inflammatory signs may be blunted")
    if _hf(host_factors, "diabetes") and "urine" not in spec_lower:
        notes.append("ℹ️ السكري يزيد شدة العدوى ومضاعفاتها، لكنه ليس دليلاً على أن هذه العزلة ممرضة.")

    # ── Clamp, floors, completeness ─────────────────────────────────────────
    score = max(0, min(100, score))
    if "NEVER_CONTAMINANT" in special_flags and score < 75:
        score = 75
    if "BLOOD_PENDING_ID" in special_flags and score < 45:
        score = 45
    if "BLOOD_TRUE_PATHOGEN" in special_flags and score < 70:
        score = 70            # missing metadata must not turn a GNB bacteraemia into "repeat"
    if "BAG_SPECIMEN" in special_flags and score >= 70:
        score = 65            # AAP: a bag-specimen positive is never diagnostic on its own
    _core_missing = [m for m in missing if m in ("Symptoms", "Colony count",
                                                 "Respiratory signs / imaging",
                                                 "Local signs of infection",
                                                 "Number of positive sets / bottles")]
    confidence = "high" if not missing else "moderate" if len(_core_missing) <= 1 else "low"
    insufficient = (("urine" in spec_lower and "Symptoms" in missing and "Colony count" in missing)
                    or "Specimen type not recognised" in missing)
    if insufficient:
        special_flags.append("INSUFFICIENT_DATA")

    # ── Verdict ─────────────────────────────────────────────────────────────
    T_TRUE, T_POSSIBLE, T_LIKELY_CONTAM = 70, 45, 25
    if "CSF_ALWAYS_SIGNIFICANT" in special_flags:
        category = "STERILE_SITE_SIGNIFICANT"
        verdict = "🔴 ALWAYS SIGNIFICANT -- Treat Immediately"
        color = "error"
        interpretation = ("العينة من موقع معقم (CSF) والكائن ممرض معروف فيه"
                          + (" مع وجود shunt/drain أو جراحة أعصاب حديثة" if "CSF_DEVICE" in special_flags else "")
                          + " — أي نمو يُعدّ مرضياً.")
        recommendations = [
            "ابدأ العلاج فوراً بجرعات التهاب السحايا ريثما تظهر الحساسية.",
            "استشر الأمراض المعدية" + (" وجراحة الأعصاب لإزالة/تغيير الـ shunt أو الـ drain."
                                       if "CSF_DEVICE" in special_flags else "."),
            "راجع خلايا وسكر وبروتين الـ CSF وكرر البزل عند عدم التحسن خلال 48 ساعة.",
        ]
    elif "CSF_SKIN_FLORA" in special_flags:
        category = "POSSIBLE_CONTAMINANT_STERILE_SITE"
        verdict = "🟡 POSSIBLE CONTAMINANT (CSF skin flora) -- Correlate before treating"
        color = "warning"
        interpretation = ("كائن من فلورا الجلد في CSF بدون shunt أو drain أو جراحة أعصاب حديثة: "
                          "أشيع ملوِّث لمزارع الـ CSF (خاصة لو النمو في المرق فقط).")
        recommendations = [
            "قارن بخلايا وسكر وبروتين الـ CSF وصبغة Gram: طبيعية = تلوث غالباً.",
            "كرّر البزل القطني إذا كان الاشتباه السريري قائماً — لا تتجاهل النتيجة ولا تعالج عليها وحدها.",
            "لو المريض عنده shunt/EVD أو جراحة أعصاب حديثة: سجّلها في عوامل المضيف — التفسير يتغير.",
        ]
    elif "MW_REJECT" in special_flags:
        category = "SPECIMEN_REJECT"
        verdict = "🟢 SPECIMEN INADEQUATE -- Reject & Repeat"
        color = "success"
        interpretation = ("العينة غير مناسبة (خلايا طلائية ≥ 25/LPF). النتيجة تعكس فلورا الفم "
                          "لا الجهاز التنفسي السفلي.")
        recommendations = [
            "ارفض العينة وأعِد طلب البلغم بتقنية صحيحة (صباحي باكر بعد المضمضة).",
            "فكّر في induced sputum أو BAL/ETA إذا تعذّرت عينة مناسبة.",
        ]
    elif insufficient:
        category = "INSUFFICIENT_DATA"
        verdict = "⚪ INSUFFICIENT DATA -- Cannot assess significance"
        color = "warning"
        interpretation = ("البيانات الأساسية غير مُدخلة (" + "، ".join(missing) + "). الحكم على "
                          "الـ pathogenicity بدونها تخمين — لم يُحتسب غياب البيانات كدليل ضد العدوى.")
        recommendations = [
            "أدخل الأعراض (أو اختر Asymptomatic صراحةً) وعدّ المستعمرات.",
            "للبول: حدّد طريقة الجمع — العتبة تختلف (midstream / قسطرة / SPA).",
        ]
    elif "ABU_NO_TREAT" in special_flags:
        category = "ASB_NO_TREAT"
        verdict = "🟡 ASYMPTOMATIC BACTERIURIA (ABU) -- Do NOT Treat"
        color = "warning"
        interpretation = ("bacteriuria بعدد معنوي بلا أعراض = Asymptomatic Bacteriuria"
                          + (" مرتبطة بالقسطرة (CA-ASB)" if "CA_ASB" in special_flags else "")
                          + ". IDSA 2019: لا فحص ولا علاج — يشمل كبار السن، السكري، القسطرة، "
                          "إصابة النخاع الشوكي، وزرع الكلى بعد الشهر الأول.")
        recommendations = [
            "لا تعطِ مضادات حيوية (IDSA 2019) — العلاج لا يمنع العدوى ويزيد المقاومة و C. difficile.",
            "أعِد التقييم فقط إذا ظهرت أعراض.",
            "الاستثناءان: الحمل، وقبل إجراء بولي فيه جرح للغشاء المخاطي.",
        ]
    elif "ABU_TREAT" in special_flags:
        category = "ASB_TREAT"
        verdict = "🔴 ABU IN HIGH-RISK CONTEXT -- Treat"
        color = "error"
        interpretation = "ABU في سياق يستوجب العلاج (حمل / إجراء بولي فيه جرح للغشاء المخاطي)."
        recommendations = [
            "الحمل: دواء آمن حسب الحساسية لمدة 4–7 أيام، ثم مزرعة متابعة.",
            "قبل الإجراء البولي: جرعة أو جرعتان تبدأ 30–60 دقيقة قبل الإجراء (IDSA 2019).",
        ]
    elif "WOUND_COLONISATION_LIKELY" in special_flags and score < T_TRUE:
        category = "COLONISATION"
        verdict = "🟢 LIKELY COLONISATION (chronic wound) -- Do Not Treat on culture alone"
        color = "success"
        interpretation = ("جرح مزمن/قرحة فراش بدون علامتين سريريتين للعدوى: النمو يمثل استعمار "
                          "سطح الجرح.")
        recommendations = [
            "لا مضاد حيوي جهازي — العناية بالجرح والتنضيف ورفع الضغط.",
            "أعِد التقييم عند ظهور علامات عدوى، وخذ نسيجاً عميقاً لا مسحة سطحية.",
        ]
    elif score >= T_TRUE:
        category = "TRUE_INFECTION"
        verdict = "🔴 Likely TRUE INFECTION -- Treat"
        color = "error"
        interpretation = ("المؤشرات تدعم بقوة وجود عدوى حقيقية. يُنصح بالعلاج الموجَّه بنتيجة "
                          "الحساسية مع مراعاة السياق الكلينيكي.")
        recommendations = [
            "ابدأ العلاج بناءً على نتيجة الـ AST.",
            "راجع الجرعة حسب الوظيفة الكلوية، وأقصر مدة فعّالة.",
            "De-escalate بعد 48–72 ساعة إذا تحسّن المريض.",
        ]
    elif score >= T_POSSIBLE:
        category = "POSSIBLE_INFECTION"
        verdict = "🟡 POSSIBLE INFECTION -- Clinical Correlation Required"
        color = "warning"
        interpretation = ("النتيجة حدودية. يُنصح بالتقييم الكلينيكي الكامل قبل البدء بالعلاج. "
                          "قد تحتاج فحوصات إضافية أو إعادة المزرعة.")
        recommendations = [
            "قيّم المريض كلينيكياً قبل إعطاء المضادات الحيوية.",
            "أكمل البيانات الناقصة أو أعِد المزرعة إذا كان الوضع غير واضح.",
        ]
    elif score >= T_LIKELY_CONTAM:
        category = "LIKELY_CONTAMINANT"
        verdict = "🟠 LIKELY CONTAMINANT -- Repeat Recommended"
        color = "warning"
        interpretation = ("المؤشرات تميل نحو التلوث أو الاستعمار. يُنصح بإعادة أخذ العينة "
                          "بتقنية صحيحة قبل البدء بالعلاج.")
        recommendations = [
            "أعِد أخذ العينة مع تحسين التقنية.",
            "لا تبدأ العلاج بناءً على هذه النتيجة وحدها.",
        ]
    else:
        category = "CONTAMINANT_OR_COLONISER"
        verdict = "🟢 LIKELY CONTAMINANT / COLONIZER -- Do Not Treat"
        color = "success"
        interpretation = ("المؤشرات تدعم التلوث أو الاستعمار بشكل كبير. العلاج غير مبرر في "
                          "الغالب. تابع المريض كلينيكياً.")
        recommendations = [
            "لا تعطِ مضادات حيوية بناءً على هذه النتيجة.",
            "أعِد تقييم المريض إذا استمرت الأعراض أو تطورت.",
        ]
    if "BLOOD_CONTAMINANT_RISK" in special_flags and category != "TRUE_INFECTION":
        recommendations.append("اسحب مجموعتين جديدتين من موضعين مختلفين قبل الحكم على CoNS / فلورا الجلد.")
    if "BAG_SPECIMEN" in special_flags:
        recommendations.append("عينة كيس: أكّد بعينة قسطرة أو SPA قبل اعتماد التشخيص — ولا تؤخر العلاج "
                               "في رضيع محموم يبدو مريضاً (خذ العينة الصحيحة ثم ابدأ).")
    if "SAUREUS_BACTERIURIA" in special_flags:
        recommendations.append("اسحب مزارع دم: S. aureus في البول قد يدل على bacteremia.")
    if missing and not insufficient:
        recommendations.append("بيانات ناقصة تُضعف الثقة في التقييم: " + "، ".join(missing) + ".")

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
        # v3
        "engine_version":  PATHO_ENGINE_VERSION,
        "category":        category,
        "threshold":       threshold_text,
        "notes":           notes,
        "missing_inputs":  missing,
        "confidence":      confidence,
        "references":      references,
        "evidence":        evidence,
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
