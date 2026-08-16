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
    "detect_age_months", "ORGANISM_OCR_ALIASES", "ABX_DISK_CODES",
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

def detect_age_months(text: str) -> Optional[int]:
    """Age in MONTHS for an under-one patient, or None.

    Feeds the NEONATAL_RESTRICTIONS gate, which cannot distinguish a two-week-old
    from an eleven-month-old without it and therefore warns instead of deciding.
    """
    t = str(text or "")
    m = re.search(r"(\d+)\s*(?:day|days|d\b|يوم|أيام)", t, re.I)
    if m:
        return min(11, int(m.group(1)) // 30)
    m = re.search(r"(\d+)\s*(?:week|weeks|wk|w\b|أسبوع|اسبوع)", t, re.I)
    if m:
        return min(11, int(m.group(1)) // 4)
    m = re.search(r"(\d+)\s*(?:month|months|mo\b|mos|شهر|شهور|أشهر)", t, re.I)
    if m and 0 <= int(m.group(1)) <= 11:
        return int(m.group(1))
    m = re.search(r"(?:age|العمر|السن)\s*[:\-]?\s*(\d{1,2})\s*/\s*12\b", t, re.I)
    if m and 0 <= int(m.group(1)) <= 11:
        return int(m.group(1))
    return None

ORGANISM_OCR_ALIASES: Dict[str, str] = {
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
    "staphylococcus saprophyticus": "Coagulase-negative Staphylococci",
    "staphylococcus lugdunensis": "Coagulase-negative Staphylococci",
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
}

_DISK_CODE_TOKEN = re.compile(r"[A-Za-z]{1,4}\d{0,3}")

def _scan_line_for_disk_codes(line: str) -> List[str]:
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
    if not any(normalize_sir_value(t) is not None for t in tokens):
        return []
    found: List[str] = []
    for tok in tokens:
        # A verdict token is never also a drug code (S / I / R would otherwise
        # collide with nothing here, but NS and RES would).
        if normalize_sir_value(tok) is not None:
            continue
        if not _DISK_CODE_TOKEN.fullmatch(tok):
            continue
        name = ABX_DISK_CODES.get(tok.upper())
        if name and name in ABX_GUIDELINES and name not in found:
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
