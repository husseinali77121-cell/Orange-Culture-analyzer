# -*- coding: utf-8 -*-
# © Dr. Hussein Ali — Orange Lab, 6 October City, Egypt
# Microbiology CDSS — All Rights Reserved
"""ocr_parsing.py — turning a photographed lab report into structured data.

WHY THIS FILE EXISTS
Everything here reads TEXT and produces FACTS: which antibiotics a report names,
what S/I/R each carries, which organism was isolated, how old the patient is.
It is the layer where a misread character becomes a clinical error, and it was
scattered through streamlit_app.py in fourteen fragments between line 586 and
line 1898 — a matcher here, an alias table six hundred lines later, the S/I/R
vocabulary eight hundred lines after that.

Three of this audit's defects lived in exactly that scatter:

  * extract_detected_drugs() matched by plain containment, so
    "Ampicillin/Sulbactam" also produced a phantom "Ampicillin" entry and the
    engine raised intrinsic-resistance alerts for a drug nobody tested.
  * ABX_ALIAS_INDEX held 176 aliases rich in Egyptian brand names and ZERO
    CLSI disk codes, so a VITEK printout reading "AMC / CIP / SXT / MEM"
    produced an EMPTY panel — and the same Pseudomonas isolate went from MDR to
    no classification at all, with nothing on screen saying the panel had been
    truncated by the parser.
  * normalize_sir_value() and the alias table sat a thousand lines apart, so
    the question "what does this parser accept" had no single answer.

CONTRACTS WORTH KNOWING
  * normalize_sir_value() FAILS CLOSED: an unrecognised verdict returns None
    and the drug drops out of the panel rather than being guessed at. A wrong
    S is worse than a missing row.
  * _scan_line_for_drugs() claims character SPANS, longest name first, so a
    shorter name inside a longer one cannot also match.
  * Disk codes are honoured ONLY as a whole standalone token on a line that
    also carries an S/I/R verdict. Several are one or two letters — P, E, DO,
    CN, TE — and a naive alias would fire on the report header.
"""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from abx_guidelines import ABX_ALIAS_INDEX, ABX_GUIDELINES, normalize_abx_key

logger = logging.getLogger(__name__)

__all__ = [
    "fuzzy_match", "normalize_ocr_text", "clean_patient_name",
    "detect_age_months", "parse_patient_age", "age_reading_is_ambiguous",
    "parse_result_line", "ORGANISM_OCR_ALIASES", "ABX_DISK_CODES",
    "_scan_line_for_disk_codes", "_scan_line_for_drugs",
    "extract_detected_drugs", "_SIR_ALIASES", "normalize_sir_value",
    "normalize_sir_map", "match_antibiotic_from_text",
]


def fuzzy_match(a: str, b: str) -> float:
    """Similarity 0-100 between two drug-name strings.

    BUG FIXED: the old body returned a flat 100.0 whenever either string was a
    substring of the other. That made the caller's `>= 82` threshold completely
    inert -- a single OCR character was enough to bind a garbage token to a real
    antibiotic ('a' vs 'Amikacin' scored 100.0). Containment is now scored by
    how much of the LONGER string the match actually covers, and a floor is
    applied so a fragment can never outscore a genuine near-miss.
    """
    a = (a or "").lower().strip()
    b = (b or "").lower().strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 100.0
    ratio = SequenceMatcher(None, a, b).ratio() * 100
    if a in b or b in a:
        short, long = (a, b) if len(a) <= len(b) else (b, a)
        # A containment is only as strong as its coverage of the longer name,
        # and fragments under 4 characters carry no evidential weight at all.
        if len(short) < 4:
            return ratio
        coverage = (len(short) / len(long)) * 100
        return max(ratio, coverage)
    return ratio

def normalize_ocr_text(text: str) -> str:
    cleaned = text or ""
    for old, new in {"\u2013": "-", "\u2014": "-", "\u00a0": " ", "|": " "}.items():
        cleaned = cleaned.replace(old, new)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()

def clean_patient_name(name: str) -> str:
    """Strip form labels and stray glyphs out of an OCR'd patient-name field.

    NOT CURRENTLY CALLED. Kept deliberately: the OCR pipeline populates the name
    field via extract_all_data(), and whether that path routes through here has
    changed more than once. Deleting it would mean rewriting the blacklist the
    next time the OCR field mapping moves, and the blacklist is the part that
    took the tuning. If it is still uncalled at the next review, delete it then
    -- but check `extract_all_data` first.
    """
    if not name:
        return ""
    name = normalize_ocr_text(name)
    blacklist = [
        "name", "patient", "patient name", "specimen", "organism", "age", "sex",
        "male", "female", "urine", "culture", "report", "lab", "result",
        "اسم", "المريض", "اسم المريض", "العمر", "النوع", "الجنس",
        "العينة", "المزرعة", "نتيجة", "تقرير", "معمل", "مختبر"
    ]
    low = name.lower()
    for token in blacklist:
        low = low.replace(token.lower(), " ")
    name = low
    name = re.sub(r"[^A-Za-z\u0600-\u06FF\s]", " ", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    if len(name) < 3:
        return ""
    return name.title() if re.search(r"[A-Za-z]", name) else name

# ── Patient age ──────────────────────────────────────────────────────────────
# FIX 2026-11-11 (round 4). The unit patterns used to be searched over the
# WHOLE report, before the "Age:" field was even looked at. A culture report
# always carries some "N days" -- "growth after 2 days incubation", "valid for
# 3 months", "repeat in 7 days" -- so a 45-year-old came back as age 0, months
# 0: a neonate. That pre-ticks the under-one box and switches on every neonatal
# ban (ceftriaxone, TMP-SMX, nitrofurantoin) and the paediatric FQ ban for an
# adult. "Age: 18 months" was the opposite error: 0 years and NO months, so the
# engine could not apply a single month-based rule.
#
# The age is now read from the AGE FIELD first, with its own unit; a bare
# "N <unit> old" is the only unlabelled form accepted for days/weeks/months,
# and an unlabelled number with a year unit is the last resort.
_AGE_UNIT = (r"(?P<unit>years?|yrs?|y(?![a-z])|سنة|سنه|سنوات|سنين|عام|"
             r"months?|mons?|mths?|mo(?![a-z])|mos(?![a-z])|شهر|شهور|أشهر|اشهر|"
             r"weeks?|wks?|wk(?![a-z])|w(?![a-z])|أسبوع|اسبوع|أسابيع|اسابيع|"
             r"days?|d(?![a-z])(?!\.\s*o)|يوم|أيام|ايام)")
# FIX 2026-11-12 (round 5). Between the label and the number the old pattern
# allowed ANY 15 non-digit characters, so an empty age field read the next
# field instead: "Age:    Date: 12/11/2026" -> 12 years. Only separators, a
# "/Sex" label and a "(years)" hint may sit there now, and a number that
# continues as a date ("12/11", "12-11") is not an age. "السن" no longer
# matches inside "السنة", and "45 D.O.B" is not 45 days.
_AGE_GAP = (r"(?:\s*/\s*(?:sex|gender))?(?:\s+in\s+years)?"
            r"\s*(?:\(\s*(?:years?|yrs?|y)\s*\))?[\s:;=\-._|]{0,8}")
_AGE_LABELLED = re.compile(
    r"(?:(?<![a-z])age(?![a-z])|العمر|السن(?![\u0600-\u06FF]))" + _AGE_GAP +
    r"(?P<n>\d{1,3})(?!\d)(?:[.,]\d)?"
    r"(?:\s*/\s*(?P<den>12|52)(?!\d))?(?!\s*[/\-]\s*\d)\s*" + _AGE_UNIT + r"?", re.I)
# "0 Y 6 M" / "0 years, 6 months": the month part of a compound age.
_AGE_MONTH_PART = re.compile(
    r"\s*[,&+]?\s*(?P<m>\d{1,2})\s*(?:months?|mons?|mths?|mos?|m|شهور|شهر|أشهر|اشهر)(?![a-z])", re.I)
_AGE_BARE_M = re.compile(r"\s+m(?![a-z/])", re.I)
_AGE_OLD = re.compile(r"(?P<n>\d{1,3})\s*-?\s*" + _AGE_UNIT + r"[\s\-]*old(?![a-z])", re.I)
_AGE_YEARS_FREE = re.compile(
    r"(?P<n>\d{1,3})\s*(?:years?|yrs?)(?![a-z])|(?P<n2>\d{1,3})\s*(?:سنة|سنه|سنوات)", re.I)


def _age_from_parts(n: str, den: Optional[str], unit: Optional[str]
                    ) -> Tuple[Optional[int], Optional[int]]:
    """(years, months-if-under-one) from one parsed age expression."""
    try:
        v = int(n)
    except (TypeError, ValueError):
        return None, None
    u = (unit or "").lower()
    days: Optional[int] = None
    months_total: Optional[int] = None
    if den == "12":
        months_total = v
    elif den == "52":
        days = v * 7
    elif u.startswith(("mo", "mth", "شهر", "شهو", "أشه", "اشه")):
        months_total = v
    elif u.startswith(("w", "أسب", "اسب", "أساب", "اساب")):
        days = v * 7
    elif u.startswith(("d", "يوم", "أيام", "ايام")):
        days = v
    else:                                   # years, or no unit at all
        return (v, None) if 0 <= v <= 120 else (None, None)
    if days is not None:
        if days < 365:
            return 0, min(11, days // 30)
        return days // 365, None
    if months_total is not None:
        if months_total <= 11:
            return 0, months_total
        yrs = months_total // 12
        return (yrs, None) if yrs <= 120 else (None, None)
    return None, None


def parse_patient_age(text: str) -> Tuple[Optional[int], Optional[int]]:
    """(age in years, age in months when under one year) from a report header.

    Years is 0 for any patient under one; months is None from one year up or
    when nothing usable was printed.
    """
    t = str(text or "")
    # Every candidate is tried (round 5): one unusable match -- "Age: 2026" --
    # used to end the search and hide a good "Age: 45 Y" further down.
    for rx in (_AGE_LABELLED, _AGE_OLD):
        for m in rx.finditer(t):
            unit = m.group("unit")
            yrs, mons = _age_from_parts(m.group("n"), m.groupdict().get("den"), unit)
            if yrs is None:
                continue
            # "Age: 0 Y 6 M" -> six months, not "0 years, months unknown".
            if yrs == 0 and mons is None and (unit or "").lower()[:1] in ("y", "س", "ع"):
                mp = _AGE_MONTH_PART.match(t, m.end())
                if mp and 0 <= int(mp.group("m")) <= 11:
                    mons = int(mp.group("m"))
            return yrs, mons
    m = _AGE_YEARS_FREE.search(t)
    if m:
        v = int(m.group("n") or m.group("n2"))
        if 0 <= v <= 120:
            return v, None
    return None, None


def age_reading_is_ambiguous(text: str) -> bool:
    """True when the age field reads "N M" with no unit -- months, or Male?

    Added 2026-11-12 (round 5). "Age: 3 M" is how many laboratories print a
    three-MONTH-old, and it is also how they print "3 years, Male". The parser
    cannot know, and reads years. A three-month-old read as a three-year-old
    loses every infant restriction, so the UI asks the operator to confirm
    instead of trusting either reading silently.
    """
    t = str(text or "")
    for m in _AGE_LABELLED.finditer(t):
        if m.group("unit") or m.groupdict().get("den"):
            return False
        try:
            n = int(m.group("n"))
        except (TypeError, ValueError):
            continue
        return bool(n <= 36 and _AGE_BARE_M.match(t, m.end("n")))
    return False


def detect_age_months(text: str) -> Optional[int]:
    """Age in MONTHS for an under-one patient, or None.

    Feeds the NEONATAL_RESTRICTIONS gate, which cannot distinguish a two-week-old
    from an eleven-month-old without it and therefore warns instead of deciding.
    """
    return parse_patient_age(text)[1]

ORGANISM_OCR_ALIASES: Dict[str, str] = {
    # ── Not identified to species level (2026-11-10) ─────────────────────────
    # Longest alias wins in detect_organism(), so "acinetobacter spp" is read
    # as the genus-level entry and is no longer forced onto A. baumannii.
    "acinetobacter spp": "Acinetobacter spp.", "acinetobacter species": "Acinetobacter spp.",
    "acinetobacter sp": "Acinetobacter spp.",
    "pseudomonas spp": "Pseudomonas spp.", "pseudomonas species": "Pseudomonas spp.",
    "pseudomonas sp": "Pseudomonas spp.",
    "enterobacter spp": "Enterobacter spp.", "enterobacter species": "Enterobacter spp.",
    "citrobacter spp": "Citrobacter spp.", "citrobacter species": "Citrobacter spp.",
    "proteus spp": "Proteus spp.", "proteus species": "Proteus spp.",
    "serratia spp": "Serratia spp.", "serratia species": "Serratia spp.",
    "enterococcus spp": "Enterococcus spp.", "enterococcus species": "Enterococcus spp.",
    "enterococci": "Enterococcus spp.",
    "staphylococcus spp": "Staphylococcus spp.", "staphylococcus species": "Staphylococcus spp.",
    "streptococcus spp": "Streptococcus spp.", "streptococcus species": "Streptococcus spp.",
    "viridans streptococci": "Streptococcus spp.", "streptococcus viridans": "Streptococcus spp.",
    "gram negative bacilli": "Gram-negative bacilli (unidentified)",
    "gram-negative bacilli": "Gram-negative bacilli (unidentified)",
    "gram negative rods": "Gram-negative bacilli (unidentified)",
    "gram-negative rods": "Gram-negative bacilli (unidentified)",
    "non fermenting gram negative bacilli": "Non-fermenting Gram-negative bacilli (unspeciated)",
    "non-fermenting gram-negative bacilli": "Non-fermenting Gram-negative bacilli (unspeciated)",
    "non fermenter": "Non-fermenting Gram-negative bacilli (unspeciated)",
    "non-fermenter": "Non-fermenting Gram-negative bacilli (unspeciated)",
    "gram positive cocci": "Gram-positive cocci (unidentified)",
    "gram-positive cocci": "Gram-positive cocci (unidentified)",
    "escherichia coli": "E. coli", "e.coli": "E. coli", "e. coli": "E. coli",
    "esch coli": "E. coli", "e coli": "E. coli",
    "klebsiella pneumoniae": "Klebsiella spp.", "klebsiella oxytoca": "Klebsiella spp.",
    "k. pneumoniae": "Klebsiella spp.", "k.pneumoniae": "Klebsiella spp.",
    "klebsiella": "Klebsiella spp.",
    "staph aureus": "Staphylococcus aureus", "s. aureus": "Staphylococcus aureus",
    "s.aureus": "Staphylococcus aureus",
    "methicillin resistant staphylococcus aureus": "MRSA",
    "methicillin-resistant staphylococcus aureus": "MRSA",
    "pseudomonas": "Pseudomonas aeruginosa", "p. aeruginosa": "Pseudomonas aeruginosa",
    "ps. aeruginosa": "Pseudomonas aeruginosa",
    "acinetobacter": "Acinetobacter baumannii", "a. baumannii": "Acinetobacter baumannii",
    "proteus vulgaris": "Proteus vulgaris", "p. vulgaris": "Proteus vulgaris",
    "proteus": "Proteus mirabilis", "p. mirabilis": "Proteus mirabilis",
    # 2026-08-01 these two pointed at "Enterococcus faecium", which was not a
    # profile key, so they were redirected to E. faecalis as the nearest
    # selectable match. 2026-08-03: E. faecium now HAS its own profile — the
    # species difference is not cosmetic (ampicillin resistance is the rule in
    # faecium and the exception in faecalis), so the redirect is removed and the
    # canonical mappings live further down with the other new organisms.
    "e. faecalis": "Enterococcus faecalis", "enterococcus": "Enterococcus faecalis",
    "vancomycin resistant enterococcus": "VRE",
    "vancomycin-resistant enterococcus": "VRE",
    "strep pneumoniae": "Streptococcus pneumoniae",
    "s. pneumoniae": "Streptococcus pneumoniae", "pneumococcus": "Streptococcus pneumoniae",
    "stenotrophomonas": "Stenotrophomonas maltophilia",
    "s. maltophilia": "Stenotrophomonas maltophilia",
    # These three targets did not exist in ORGANISM_PROFILE until 2026-08-01, so
    # an OCR'd Serratia or Enterobacter report fell through to index 0 -- E. coli
    # on Urine and Blood -- losing the whole chromosomal-AmpC derepression rule
    # on the organisms it matters most for. The profiles now exist.
    "enterobacter cloacae": "Enterobacter cloacae", "enterobacter": "Enterobacter cloacae",
    "e. cloacae": "Enterobacter cloacae",
    "klebsiella aerogenes": "Enterobacter cloacae",     # renamed from E. aerogenes
    "enterobacter aerogenes": "Enterobacter cloacae",
    "serratia": "Serratia marcescens", "s. marcescens": "Serratia marcescens",
    "serratia marcescens": "Serratia marcescens",
    "citrobacter freundii": "Citrobacter freundii", "c. freundii": "Citrobacter freundii",
    "citrobacter koseri": "Citrobacter koseri", "c. koseri": "Citrobacter koseri",
    "citrobacter diversus": "Citrobacter koseri",
    "citrobacter": "Citrobacter freundii",
    "morganella morganii": "Morganella morganii", "morganella": "Morganella morganii",
    "m. morganii": "Morganella morganii",
    "providencia": "Providencia spp.", "providencia stuartii": "Providencia spp.",
    "providencia rettgeri": "Providencia spp.",
    "hafnia alvei": "Hafnia alvei", "hafnia": "Hafnia alvei",
    # Added 2026-08-03. Each of these had a complete intrinsic-resistance row
    # and no selectable profile, so an OCR'd report naming one resolved to
    # nothing and best_default_index() fell back to index 0 — the silent
    # misidentification this audit already fixed once for Serratia.
    "listeria monocytogenes": "Listeria monocytogenes",
    "listeria": "Listeria monocytogenes", "l. monocytogenes": "Listeria monocytogenes",
    "streptococcus pyogenes": "Streptococcus pyogenes (Group A)",
    "s. pyogenes": "Streptococcus pyogenes (Group A)",
    "group a streptococcus": "Streptococcus pyogenes (Group A)",
    "gas": "Streptococcus pyogenes (Group A)",
    "beta haemolytic streptococcus group a": "Streptococcus pyogenes (Group A)",
    "streptococcus agalactiae": "Streptococcus agalactiae (Group B)",
    "s. agalactiae": "Streptococcus agalactiae (Group B)",
    "group b streptococcus": "Streptococcus agalactiae (Group B)",
    "gbs": "Streptococcus agalactiae (Group B)",
    "beta haemolytic streptococcus group b": "Streptococcus agalactiae (Group B)",
    "enterococcus faecium": "Enterococcus faecium",
    "e. faecium": "Enterococcus faecium",
    "staphylococcus epidermidis": "Coagulase-negative Staphylococci",
    "s. epidermidis": "Coagulase-negative Staphylococci",
    "staphylococcus haemolyticus": "Coagulase-negative Staphylococci",
    "staphylococcus hominis": "Coagulase-negative Staphylococci",
    # 2026-11-10: own profiles now (saprophyticus = urinary pathogen with
    # intrinsic fosfomycin R; lugdunensis = behaves like S. aureus).
    "staphylococcus saprophyticus": "Staphylococcus saprophyticus",
    "s. saprophyticus": "Staphylococcus saprophyticus",
    "staphylococcus lugdunensis": "Staphylococcus lugdunensis",
    "s. lugdunensis": "Staphylococcus lugdunensis",
    "coagulase negative staphylococci": "Coagulase-negative Staphylococci",
    "coagulase-negative staphylococci": "Coagulase-negative Staphylococci",
    "cons": "Coagulase-negative Staphylococci",
    "coagulase negative staph": "Coagulase-negative Staphylococci",
    "salmonella": "Salmonella spp.", "shigella": "Shigella spp.",
    "haemophilus influenzae": "H. influenzae", "h. influenzae": "H. influenzae",
    "campylobacter": "Campylobacter jejuni",
    "legionella": "Legionella pneumophila",
    "mycoplasma": "Mycoplasma spp.",
    # "rickettsia" alias removed 2026-08-01 with the profile: it resolved to
    # a key that no longer exists, and best_default_index() falls back to
    # index 0 for an unknown name -- the silent-misidentification bug this
    # audit already fixed for Serratia and Enterobacter.
}

_ABX_ALIAS_SORTED = sorted(
    ((k, v) for k, v in ABX_ALIAS_INDEX.items() if len(k) >= 5),
    key=lambda item: len(item[0]), reverse=True,
)

ABX_DISK_CODES: Dict[str, str] = {
    # Penicillins & BLI combinations
    "P": "Penicillin", "PEN": "Penicillin",
    "AMP": "Ampicillin", "AM": "Ampicillin",
    "AMX": "Amoxicillin", "AML": "Amoxicillin",
    "AMC": "Amoxicillin + Clavulanic acid",
    "SAM": "Ampicillin/Sulbactam", "AMS": "Ampicillin/Sulbactam",
    "TZP": "Piperacillin + Tazobactam", "PTZ": "Piperacillin + Tazobactam",
    "OX": "Oxacillin", "OXA": "Oxacillin",
    # Cephalosporins
    "CZ": "Cefazolin", "KZ": "Cefazolin", "CFZ": "Cefazolin",
    "CL": "Cephalexin", "LEX": "Cephalexin", "CN30": "Cephalexin",
    "CXM": "Cefuroxime", "CRM": "Cefuroxime",
    "FOX": "Cefoxitin", "CX": "Cefoxitin",
    "CRO": "Ceftriaxone", "CTR": "Ceftriaxone",
    "CTX": "Cefotaxime",
    "CAZ": "Ceftazidime",
    "FEP": "Cefepime", "CPM": "Cefepime",
    "CFM": "Cefixime", "CE": "Cefixime",
    "CFP": "Cefoperazone", "CES": "Cefoperazone + Sulbactam",
    # Carbapenems & monobactam
    "IPM": "Imipenem/Cilastatin", "IMP": "Imipenem/Cilastatin",
    "MEM": "Meropenem", "MRP": "Meropenem",
    "ETP": "Ertapenem", "ERT": "Ertapenem",
    "ATM": "Aztreonam", "AZT": "Aztreonam",
    # Aminoglycosides  (CN = gentamicin in the EUCAST/Oxoid convention)
    "CN": "Gentamicin", "GEN": "Gentamicin", "GM": "Gentamicin",
    "AK": "Amikacin", "AN": "Amikacin", "AMK": "Amikacin",
    "TOB": "Tobramycin", "TM": "Tobramycin", "NN": "Tobramycin",
    # Quinolones
    "CIP": "Ciprofloxacin",
    "LEV": "Levofloxacin", "LVX": "Levofloxacin",
    "MXF": "Moxifloxacin", "MFX": "Moxifloxacin",
    "OFX": "Ofloxacin", "OF": "Ofloxacin",
    "NOR": "Norfloxacin", "NX": "Norfloxacin",
    # Others
    "SXT": "Trimethoprim/Sulfamethoxazole", "TS": "Trimethoprim/Sulfamethoxazole",
    "COT": "Trimethoprim/Sulfamethoxazole",
    "TE": "Tetracycline", "TET": "Tetracycline",
    "DO": "Doxycycline", "DOX": "Doxycycline",
    "MH": "Minocycline", "MI": "Minocycline", "MIN": "Minocycline",
    "VA": "Vancomycin", "VAN": "Vancomycin",
    "LZD": "Linezolid", "LNZ": "Linezolid",
    "DA": "Clindamycin", "CD": "Clindamycin", "CLI": "Clindamycin",
    "E": "Erythromycin", "ERY": "Erythromycin",
    "AZM": "Azithromycin", "AZI": "Azithromycin",
    "CLR": "Clarithromycin",
    "FD": "Fusidic acid", "FA": "Fusidic acid",
    "F": "Nitrofurantoin", "NIT": "Nitrofurantoin", "FT": "Nitrofurantoin",
    "FOS": "Fosfomycin", "FOT": "Fosfomycin",
    "CT": "Colistin", "CST": "Colistin", "COL": "Colistin",
    "MTZ": "Metronidazole", "MET": "Metronidazole",
    "RD": "Rifampicin", "RA": "Rifampicin",
    # HiMedia labels (2026-11-11), the other disk brand common in Egypt.
    "PIT": "Piperacillin + Tazobactam", "LE": "Levofloxacin", "LZ": "Linezolid",
    "TEI": "Teicoplanin", "CPZ": "Cefoperazone", "CFS": "Cefoperazone + Sulbactam",
}

_DISK_CODE_TOKEN = re.compile(r"[A-Za-z]{1,4}\d{0,3}")
# Words that may sit on a disk-code row without being a code (round 5).
_DISK_ROW_FILLER = frozenset({"MM", "MCG", "UG", "MG", "IU", "U", "MIC", "ZONE",
                              "DISK", "DISC", "CODE", "DIAMETER"})


def _disk_code_name(tok: str) -> Optional[str]:
    name = ABX_DISK_CODES.get(tok.upper())
    if not name:
        name = ABX_DISK_CODES.get(re.sub(r"\d+$", "", tok.upper()))
    return name if name in ABX_GUIDELINES else None


def _is_pure_disk_row(tokens: List[str]) -> bool:
    """True when every word on the line is a disk code, a verdict or a unit.

    FIX 2026-11-12 (round 5). Many codes are ordinary letters and words -- F
    (nitrofurantoin), P, E, OF (ofloxacin), DO, AM, AN, TE -- and the only
    guard was "the line carries a verdict somewhere". A header or a comment
    passes that easily:
        "Sex: F   Age: 30 Y   Ref: Dr. S"   -> Nitrofurantoin = S
        "Heavy growth of Klebsiella, resistant strain" -> Ofloxacin = R
    Both put a drug nobody tested on the panel, one of them as susceptible. A
    genuine code row ("AMC 30 S", "CIP5 R / MEM S") holds nothing but codes,
    numbers, verdicts and units, so that is now required.
    """
    for tok in tokens:
        if normalize_sir_value(tok) is not None:
            continue
        core = tok.strip(".+")
        if not core or not re.search(r"[A-Za-z\u0600-\u06FF]", core):
            continue                                  # a number / symbol
        if core.upper() in _DISK_ROW_FILLER:
            continue
        if _DISK_CODE_TOKEN.fullmatch(core) and _disk_code_name(core):
            continue
        return False
    return True


def _scan_line_for_disk_codes(line: str, require_verdict: bool = True,
                              check_row: bool = True) -> List[str]:
    """Antibiotics named by CLSI/EUCAST disk code on ONE result row.

    Returns [] unless the line also carries an S/I/R verdict — a bare code in
    prose is not a result and must not create a panel entry.
    """
    if not line:
        return []
    # FIX 2026-08-03: this reused the full-name splitter, which KEEPS "/" and
    # "-" because real drug names contain them (Ampicillin/Sulbactam,
    # Imipenem-Relebactam). For disk codes that is wrong: "AMC S/CIP R/MEM S"
    # tokenised as ["AMC", "S/CIP", "R/MEM", "S"] and only the first code
    # survived — a THREE-drug panel parsed as one, silently, which is the exact
    # truncation the disk codes were added to prevent. "AMC-S CIP-R" parsed as
    # nothing at all.
    #
    # Splitting on them here is safe: _scan_line_for_drugs() runs FIRST and
    # claims every full name, so this path only ever sees a line that named no
    # drug in full. No disk code contains a slash or a hyphen.
    tokens = re.split(r"[^\w.+]+", line.strip())
    tokens = [t for t in tokens if t]
    if not tokens:
        return []
    # Does this line look like a result row at all?
    if require_verdict and not any(normalize_sir_value(t) is not None for t in tokens):
        return []
    if check_row and not _is_pure_disk_row(tokens):
        return []
    found: List[str] = []
    for tok in tokens:
        # A verdict token is never also a drug code (S / I / R would otherwise
        # collide with nothing here, but NS and RES would).
        if normalize_sir_value(tok) is not None:
            continue
        if not _DISK_CODE_TOKEN.fullmatch(tok):
            continue
        # FIX 2026-11-11 (round 4): disks are printed with their potency and
        # OCR often fuses the two ("CIP5", "AK30", "CN10", "AMC30"). Only the
        # exact token was looked up, so a fused code named no drug and the row
        # vanished from the panel. The exact token still wins -- "CN30" is
        # HiMedia's cephalexin, not gentamicin -- then the potency is dropped.
        name = _disk_code_name(tok)
        if name and name not in found:
            found.append(name)
    return found

def _scan_line_for_drugs(line: str) -> List[str]:
    """Every distinct antibiotic named in ONE line, longest-name-wins."""
    norm = normalize_abx_key(line)
    if not norm:
        return []
    claimed: List[Tuple[int, int]] = []
    found:   List[str] = []
    for alias_norm, abx_name in _ABX_ALIAS_SORTED:
        start = 0
        while True:
            i = norm.find(alias_norm, start)
            if i < 0:
                break
            j = i + len(alias_norm)
            # Skip if this hit is entirely inside a longer name already matched.
            if not any(s <= i and j <= e for s, e in claimed):
                claimed.append((i, j))
                if abx_name not in found:
                    found.append(abx_name)
            start = i + 1
    # Full names win. Only when the line named nothing spelled out do we fall
    # back to disk codes, so "Ciprofloxacin  CIP  R" cannot double-count and a
    # stray two-letter token on a named row cannot invent a second agent.
    if not found:
        found = _scan_line_for_disk_codes(line)
    return found

def extract_detected_drugs(full_text: str) -> List[str]:
    """
    Every antibiotic named anywhere in the OCR text -- with or without S/I/R.

    Scanning is done PER LINE (an AST sheet prints one agent per row) so a name
    can never be assembled across a line break, and each line uses the
    span-claiming longest-wins matcher above so combination agents do not spawn
    phantom entries for their own components.
    """
    detected: List[str] = []
    for line in (full_text or "").splitlines():
        line = line.strip()
        if len(line) < 3:
            continue
        for name in _scan_line_for_drugs(line):
            if name not in detected:
                detected.append(name)
    return sorted(detected)

_SIR_ALIASES = {
    "S": "S", "SUSCEPTIBLE": "S", "SENSITIVE": "S", "SENS": "S", "حساس": "S",
    "I": "I", "INTERMEDIATE": "I", "INTER": "I", "INT": "I", "متوسط": "I",
    "SDD": "I", "SUSCEPTIBLE-DOSE DEPENDENT": "I", "SUSCEPTIBLE DOSE DEPENDENT": "I",
    "R": "R", "RESISTANT": "R", "RESIST": "R", "RES": "R", "مقاوم": "R",
    "NS": "R", "NON-SUSCEPTIBLE": "R", "NONSUSCEPTIBLE": "R",
}

def normalize_sir_value(value: Any) -> Optional[str]:
    """One S/I/R value -> canonical 'S' | 'I' | 'R', or None if unreadable.

    Returning None (rather than defaulting to 'S') is deliberate: an
    uninterpretable result must drop out of the panel, never be presented to a
    clinician as a susceptible agent.
    """
    if value is None:
        return None
    v = str(value).strip().upper().replace("_", " ")
    return _SIR_ALIASES.get(v)

def normalize_sir_map(sir_map: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Canonicalise a whole panel, dropping entries that cannot be read."""
    out: Dict[str, str] = {}
    for drug, value in (sir_map or {}).items():
        # Keys are trimmed too. OCR routinely emits " Ciprofloxacin " with
        # padding; the padded key matched no formulary entry, so the drug was
        # dropped from the report in complete silence -- neither recommended nor
        # banned, simply gone.
        key = str(drug or "").strip()
        if not key:
            continue
        v = normalize_sir_value(value)
        if v is not None:
            out[key] = v
        elif value not in (None, ""):
            logger.warning("unreadable AST value %r for %r -- dropped from the "
                           "panel rather than assumed susceptible", value, drug)
    return out


# ── One printed line -> every (drug, result) pair on it ─────────────────────
# FIX 2026-11-12 (round 5). The reader took ONE verdict and ONE drug per line:
# the first verdict word by a fixed priority (sensitive before resistant) and
# the LONGEST drug name. Two-column reports and "Sensitive to: a, b, c" lists
# are common, and on those it produced a WRONG S:
#     "Amikacin Sensitive    Ciprofloxacin Resistant"  -> Ciprofloxacin = S
#     "Gentamicin R    Piperacillin/Tazobactam S"      -> fine by luck only
# and silently dropped every other drug on the line. A line is now cut at each
# verdict and a verdict belongs to the drug printed just before it.
_VERDICT_RX = re.compile(
    r"(?P<ns>non[\s\-]?susceptible|not\s+susceptible)"
    r"|(?P<sdd>susceptible[\s\-]*dose[\s\-]*dependent|\bsdd\b)"
    r"|(?P<s>\b(?:sensitive|susceptible|sens)\b|حسّاس|حساس)"
    r"|(?P<r>\b(?:resistant|resist)\b|مقاوم)"
    r"|(?P<i>\b(?:intermediate|inter)\b|متوسطة|متوسط)"
    r"|(?P<ns2>\bns\b)"
    r"|(?P<letter>(?<![A-Za-z0-9.+/])[SIR](?![A-Za-z0-9+])(?!\.\s*[A-Za-z]))", re.I)
_VERDICT_VALUE = {"ns": "R", "ns2": "R", "sdd": "I", "s": "S", "r": "R", "i": "I"}
_LIST_SEP = re.compile(r"[,،;&]|\band\b|\bو\b", re.I)


def _verdict_of(m: "re.Match") -> str:
    g = m.lastgroup or ""
    return m.group(0).upper() if g == "letter" else _VERDICT_VALUE[g]


def _segment_drugs(seg: str) -> List[str]:
    """Drugs named in a piece of a result line (names first, then codes)."""
    norm = normalize_abx_key(seg)
    if not norm:
        return []
    claimed: List[Tuple[int, int]] = []
    hits: List[Tuple[int, str]] = []
    for alias_norm, abx_name in _ABX_ALIAS_SORTED:
        start = 0
        while True:
            i = norm.find(alias_norm, start)
            if i < 0:
                break
            j = i + len(alias_norm)
            if not any(s <= i and j <= e for s, e in claimed):
                claimed.append((i, j))
                hits.append((i, abx_name))
            start = i + 1
    if hits:
        out: List[str] = []
        for _, n in sorted(hits):                      # in printed order
            if n not in out:
                out.append(n)
        return out
    return _scan_line_for_disk_codes(seg, require_verdict=False, check_row=False)


def parse_result_line(line: str, classify=None) -> List[Tuple[str, str]]:
    """Every (antibiotic, 'S'|'I'|'R') pair printed on ONE line.

    `classify` is the caller's one-line classifier (the app passes its own, so
    the two cannot drift); it is used for the ordinary one-drug row.
    """
    line = str(line or "").strip()
    if not line:
        return []
    drugs = _scan_line_for_drugs(line)
    verdicts = list(_VERDICT_RX.finditer(line))

    if len(drugs) <= 1:
        v = classify(line) if classify else None
        if v is None:
            words = [m for m in verdicts if m.lastgroup != "letter"]
            letters = [m for m in verdicts if m.lastgroup == "letter"]
            if words:
                v = _verdict_of(words[0])
            elif drugs and len(letters) == 1:
                # "Nitrofurantoin   S   32": the zone / MIC is printed AFTER
                # the verdict, so the end-of-line rule missed it and the row
                # lost its result.
                v = _verdict_of(letters[0])
        if not v:
            return []
        d = match_antibiotic_from_text(line)
        return [(d, v)] if d else []

    if not verdicts:
        return []
    out: List[Tuple[str, str]] = []
    seen = set()
    prev = 0
    for m in verdicts:
        seg = line[prev:m.start()]
        ds = _segment_drugs(seg)
        if ds:
            # Several drugs before one verdict: a list ("a, b: Sensitive")
            # shares it; otherwise only the drug NEXT to the verdict owns it --
            # the earlier one lost its own result to the OCR and must not
            # inherit its neighbour's.
            owners = ds if (len(ds) == 1 or _LIST_SEP.search(seg)) else ds[-1:]
            for d in owners:
                if d not in seen:
                    seen.add(d)
                    out.append((d, _verdict_of(m)))
            prev = m.end()
        elif m.lastgroup != "letter":
            prev = m.end()
    tail = _segment_drugs(line[prev:])
    if tail and not out and len(verdicts) == 1 and verdicts[0].lastgroup != "letter":
        # "Resistant to: Ciprofloxacin, Ceftriaxone, Cefepime"
        out = [(d, _verdict_of(verdicts[0])) for d in tail]
    return out


def match_antibiotic_from_text(snippet: str) -> Optional[str]:
    """The single antibiotic a result line refers to (longest name wins)."""
    hits = _scan_line_for_drugs(snippet)
    if hits:
        # Prefer the longest official name among the hits: on a line reading
        # "Ampicillin/Sulbactam  S" the combination -- not the partner -- is
        # the drug that was tested.
        return max(hits, key=lambda n: len(normalize_abx_key(n)))
    best_match = None
    best_score = 0.0
    for abx_name, info in ABX_GUIDELINES.items():
        for variant in [abx_name, *info.get("aliases", [])]:
            score = fuzzy_match(variant, snippet)
            if score > best_score:
                best_score = score
                best_match = abx_name
    return best_match if best_score >= 82 else None
