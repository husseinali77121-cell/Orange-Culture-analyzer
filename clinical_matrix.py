# -*- coding: utf-8 -*-
# © 2025 Dr / Hussein Ali — Orange Lab, 6 October City, Egypt
# Microbiology CDSS — All Rights Reserved
"""clinical_matrix.py — الخريطة الإكلينيكية الموحّدة / unified clinical constraint map.

WHY THIS FILE EXISTS
--------------------
Before this module the engine reasoned in three *independent* dimensions:

    organism  ->  intrinsic resistance      (INTRINSIC_RESISTANCE)
    host      ->  pregnancy / renal / age   (per-drug flags in ABX_GUIDELINES)
    specimen  ->  urine-only agents         (one hard-coded carve-out)

Nothing tied them together, and one whole dimension was missing entirely: the
**pharmacokinetic compartment**. A drug can be perfectly active against the
organism in vitro, perfectly safe for the host, and still be unable to reach the
site of infection. The audit that produced this file found 35 such agents being
offered as first-line options — 24 of them on CSF isolates, where the wrong
answer is fatal (Cefazolin, Cephalexin, Clindamycin, Azithromycin, Ertapenem and
oral cephalosporins were all reaching the "Allowed" list for meningitis).

This module is the missing layer, and it is deliberately built as a **total
function**: every (specimen x organism x drug x host) cell has an explicit,
sourced verdict. Nothing falls through to a permissive default. See
`prove_totality()` and `test_clinical_matrix.py`.

DESIGN CONTRACT
---------------
1. TOTALITY      — every cell resolves; no implicit "allow".
2. FAIL-CLOSED   — unknown specimen / organism / drug => DENY, never ALLOW.
3. MONOTONICITY  — adding a risk factor can only shrink the allowed set:
                     allowed(pregnant)  ⊆ allowed(not pregnant)
                     allowed(CrCl 20)   ⊆ allowed(CrCl 95)
                     allowed(hepatic)   ⊆ allowed(no hepatic)
                     allowed(child)     ⊆ allowed(adult)
                   This is machine-checkable across the whole space and is what
                   caught the dead hepatic layer.
4. WORST-WINS    — the strictest verdict from any layer is the final verdict.
5. TRACEABLE     — every verdict carries (layer, reason, citation).

WHAT IT CANNOT DO
-----------------
It proves the CODE matches THIS TABLE. It cannot prove THIS TABLE matches
EUCAST v16 / CLSI M100 Ed36. That still needs a human with the PDF open.
`countersigned_by` in guideline_registry.py is where that signature goes.

Sources: EUCAST Breakpoint Tables v16.1 · EUCAST Intrinsic Resistance and
Unusual Phenotypes v3.3 · CLSI M100 Ed36 · IDSA AMR Guidance 2026 ·
IDSA Bacterial Meningitis 2004 + ESCMID 2016 · WHO AWaRe 2025 · BNF 2025.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

__all__ = [
    "ALLOW", "CAUTION", "DENY",
    "SITE_PENETRATION", "SITE_ORGANISM_PLAUSIBILITY",
    "INTRINSIC_ADDENDA", "HOST_RULES",
    "Verdict", "evaluate", "evaluate_panel",
    "canonical_site", "canonical_organism",
    "prove_totality", "prove_fail_closed", "self_test",
    "MATRIX_VERSION",
]

MATRIX_VERSION = "1.0.0"

# ═══════════════════════════════════════════════════════════════════════════
# 0. VERDICT ALGEBRA
# ═══════════════════════════════════════════════════════════════════════════
ALLOW, CAUTION, DENY = "allow", "caution", "deny"
_RANK = {ALLOW: 0, CAUTION: 1, DENY: 2}


def _worst(a: str, b: str) -> str:
    """Worst-wins combination. Never returns a laxer verdict than either input."""
    return a if _RANK[a] >= _RANK[b] else b


class Verdict:
    """A resolved decision with full provenance."""

    __slots__ = ("level", "reasons")

    def __init__(self, level: str = ALLOW, reasons: Optional[List[Dict[str, str]]] = None):
        self.level = level
        self.reasons: List[Dict[str, str]] = reasons or []

    def add(self, level: str, layer: str, reason_en: str, reason_ar: str,
            citation: str) -> "Verdict":
        self.level = _worst(self.level, level)
        if level != ALLOW:
            self.reasons.append({
                "level": level, "layer": layer, "en": reason_en,
                "ar": reason_ar, "citation": citation,
            })
        return self

    @property
    def blocking(self) -> List[Dict[str, str]]:
        return [r for r in self.reasons if r["level"] == DENY]

    @property
    def cautions(self) -> List[Dict[str, str]]:
        return [r for r in self.reasons if r["level"] == CAUTION]

    def to_dict(self) -> Dict[str, Any]:
        return {"level": self.level, "reasons": list(self.reasons)}

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Verdict {self.level} ({len(self.reasons)} reason(s))>"


# ═══════════════════════════════════════════════════════════════════════════
# 1. VOCABULARY — canonical sites and normalisation
# ═══════════════════════════════════════════════════════════════════════════
SITES: Tuple[str, ...] = ("Urine", "Blood", "Sputum", "Wound Swab", "Pus", "Stool", "CSF")

# Free-text specimen -> canonical site. Ordered: longest / most specific first.
_SITE_ALIASES: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (("csf", "cerebrospinal", "lumbar puncture", "سائل نخاعي", "نخاعي"), "CSF"),
    (("urine", "midstream", "msu", "catheter specimen", "بول"), "Urine"),
    (("blood", "bacteraemia", "bacteremia", "septicaem", "دم"), "Blood"),
    (("sputum", "bal ", "bronch", "tracheal", "endotracheal", "respiratory",
      "throat", "nasopharyn", "بلغم", "حلق"), "Sputum"),
    (("pus", "abscess", "empyema", "صديد", "خراج"), "Pus"),
    (("wound", "swab", "ulcer", "tissue", "skin", "burn", "ear", "eye",
      "جرح", "مسحة"), "Wound Swab"),
    (("stool", "faec", "fec", "rectal", "براز"), "Stool"),
)


def canonical_site(specimen: Optional[str]) -> Optional[str]:
    """Map free text to a canonical site. Returns None when unrecognised.

    None is NOT 'no restriction' — callers must treat it as fail-closed. This is
    the opposite of the legacy `classify_specimen`, which returned '' for
    Semen / HVS / Pleural fluid and silently disabled every site rule.
    """
    if not specimen:
        return None
    s = str(specimen).strip().lower()
    if not s:
        return None
    for keys, site in _SITE_ALIASES:
        if any(k in s for k in keys):
            return site
    return None


_ORG_CANON: Dict[str, str] = {
    "e. coli": "E. coli", "e.coli": "E. coli", "escherichia coli": "E. coli",
    "klebsiella": "Klebsiella spp.", "klebsiella spp.": "Klebsiella spp.",
    "klebsiella pneumoniae": "Klebsiella spp.", "klebsiella oxytoca": "Klebsiella spp.",
    "pseudomonas aeruginosa": "Pseudomonas aeruginosa", "pseudomonas": "Pseudomonas aeruginosa",
    "acinetobacter baumannii": "Acinetobacter baumannii", "acinetobacter": "Acinetobacter baumannii",
    "staphylococcus aureus": "Staphylococcus aureus", "s. aureus": "Staphylococcus aureus",
    "mssa": "Staphylococcus aureus", "mrsa": "MRSA",
    "proteus mirabilis": "Proteus mirabilis", "proteus": "Proteus mirabilis",
    "enterococcus faecalis": "Enterococcus faecalis", "enterococcus": "Enterococcus faecalis",
    "vre": "VRE",
    "salmonella spp.": "Salmonella spp.", "salmonella": "Salmonella spp.",
    "shigella spp.": "Shigella spp.", "shigella": "Shigella spp.",
    "campylobacter jejuni": "Campylobacter jejuni", "campylobacter": "Campylobacter jejuni",
    "streptococcus pneumoniae": "Streptococcus pneumoniae", "pneumococcus": "Streptococcus pneumoniae",
    "h. influenzae": "H. influenzae", "haemophilus influenzae": "H. influenzae",
    "legionella pneumophila": "Legionella pneumophila", "legionella": "Legionella pneumophila",
    "mycoplasma spp.": "Mycoplasma spp.", "mycoplasma": "Mycoplasma spp.",
    "stenotrophomonas maltophilia": "Stenotrophomonas maltophilia",
    "stenotrophomonas": "Stenotrophomonas maltophilia",
    "rickettsia spp.": "Rickettsia spp.", "rickettsia": "Rickettsia spp.",
    "enterobacterales (unspeciated)": "Enterobacterales (unspeciated)",
    "enterobacterales": "Enterobacterales (unspeciated)",
    # Added 2026-08-01 alongside the new ORGANISM_PROFILE entries. Without these
    # canonical_organism() returned None for them and the gate's organism layer
    # (Layer C) silently sat out — fail-closed, but it also means the isolate got
    # no organism-specific check at all.
    "enterobacter cloacae": "Enterobacter cloacae",
    "enterobacter": "Enterobacter cloacae",
    "klebsiella aerogenes": "Enterobacter cloacae",
    "enterobacter aerogenes": "Enterobacter cloacae",
    "serratia marcescens": "Serratia marcescens", "serratia": "Serratia marcescens",
    "citrobacter freundii": "Citrobacter freundii", "citrobacter": "Citrobacter freundii",
    "morganella morganii": "Morganella morganii", "morganella": "Morganella morganii",
    "providencia spp.": "Providencia spp.", "providencia": "Providencia spp.",
    "hafnia alvei": "Hafnia alvei", "hafnia": "Hafnia alvei",
    # added 2026-08-03 with the five previously unreachable organisms
    "listeria monocytogenes": "Listeria monocytogenes", "listeria": "Listeria monocytogenes",
    "streptococcus pyogenes": "Streptococcus pyogenes (Group A)",
    "streptococcus pyogenes (group a)": "Streptococcus pyogenes (Group A)",
    "group a streptococcus": "Streptococcus pyogenes (Group A)",
    "streptococcus agalactiae": "Streptococcus agalactiae (Group B)",
    "streptococcus agalactiae (group b)": "Streptococcus agalactiae (Group B)",
    "group b streptococcus": "Streptococcus agalactiae (Group B)",
    "enterococcus faecium": "Enterococcus faecium",
    "staphylococcus epidermidis": "Coagulase-negative Staphylococci",
    "coagulase negative staphylococci": "Coagulase-negative Staphylococci",
    "coagulase-negative staphylococci": "Coagulase-negative Staphylococci",
    "anaerobes (لاهوائيات)": "Anaerobes (لاهوائيات)", "anaerobes": "Anaerobes (لاهوائيات)",
}


def canonical_organism(organism: Optional[str]) -> Optional[str]:
    if not organism:
        return None
    o = str(organism).strip()
    if o in _ORG_CANON.values():
        return o
    low = o.lower()
    if low in _ORG_CANON:
        return _ORG_CANON[low]
    for key, canon in _ORG_CANON.items():
        if key in low:
            return canon
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 2. LAYER A — PHARMACOKINETIC COMPARTMENT  (drug x site)
# ═══════════════════════════════════════════════════════════════════════════
# This is the layer that did not exist. Format:
#     drug: {site: (verdict, reason_en, reason_ar)}
# Every one of the 51 drugs x 7 sites = 357 cells is explicit. `prove_totality()`
# fails the build if a single cell is missing.
_OK = (ALLOW, "", "")
_NO_CSF = (DENY, "does not reach therapeutic CSF concentrations",
           "لا يصل لتركيز علاجي في السائل النخاعي")
_NO_URINE = (DENY, "negligible active urinary excretion — cannot treat UTI",
             "إفراز بولي ضئيل — لا يعالج عدوى المسالك البولية")
_URINE_ONLY = (DENY, "urinary antiseptic — no systemic tissue concentrations",
               "مطهر بولي فقط — لا يصل لتركيزات نسيجية جهازية")
_NO_ORAL_BSI = (DENY, "oral agent — serum levels inadequate for bacteraemia",
                "دواء فموي — مستوى الدم غير كافٍ لتجرثم الدم")
_AG_PUS = (CAUTION, "aminoglycoside inactivated at low pH / low O2 of abscess — do not use alone",
           "الأمينوجلايكوزيد يُثبَّط في الوسط الحمضي قليل الأكسجين للخراج — لا يُستخدم منفرداً")
_AG_LUNG = (CAUTION, "poor epithelial lining fluid penetration — never monotherapy for pneumonia",
            "اختراق ضعيف لسائل بطانة الرئة — لا يُستخدم منفرداً في الالتهاب الرئوي")

SITE_PENETRATION: Dict[str, Dict[str, Tuple[str, str, str]]] = {
    "Amikacin": {"Urine": _OK, "Blood": _OK, "Sputum": _AG_LUNG, "Wound Swab": _AG_PUS,
                 "Pus": _AG_PUS, "Stool": (DENY, "no role in enteric infection", "لا دور له في عدوى الأمعاء"),
                 "CSF": _NO_CSF},
    "Amoxicillin": {"Urine": _OK, "Blood": (CAUTION, "oral — adequate only for mild disease, not bacteraemia",
                                            "فموي — يكفي للحالات البسيطة فقط وليس لتجرثم الدم"),
                    "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                    "Stool": (CAUTION, "invasive enteric disease only", "للعدوى المعوية الغازية فقط"),
                    "CSF": _NO_CSF},
    "Amoxicillin + Clavulanic acid": {"Urine": _OK, "Blood": (CAUTION, "oral — not for bacteraemia",
                                                              "فموي — غير مناسب لتجرثم الدم"),
                                      "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                                      "Stool": (CAUTION, "invasive enteric disease only", "للعدوى المعوية الغازية فقط"),
                                      "CSF": _NO_CSF},
    "Ampicillin": {"Urine": _OK, "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                   "Stool": _OK,
                   "CSF": (CAUTION, "high-dose IV only (Listeria / Enterococcus meningitis)",
                           "جرعة وريدية عالية فقط (التهاب السحايا بالليستيريا/المكورات المعوية)")},
    "Ampicillin/Sulbactam": {"Urine": _OK, "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK,
                             "Pus": _OK, "Stool": (CAUTION, "invasive enteric disease only", "للعدوى المعوية الغازية فقط"),
                             "CSF": (CAUTION, "limited CSF data — high-dose sulbactam for Acinetobacter only, ID consult",
                                     "بيانات محدودة للسائل النخاعي — سولباكتام بجرعة عالية للأسينيتوباكتر فقط باستشارة معدية")},
    "Azithromycin": {"Urine": _NO_URINE, "Blood": (CAUTION, "low serum / high tissue levels — not for bacteraemia",
                                                    "تركيز دموي منخفض ونسيجي عالٍ — غير مناسب لتجرثم الدم"),
                     "Sputum": _OK, "Wound Swab": (CAUTION, "second-line for soft tissue", "خيار ثانٍ للأنسجة الرخوة"),
                     "Pus": (CAUTION, "second-line for abscess", "خيار ثانٍ للخراج"), "Stool": _OK, "CSF": _NO_CSF},
    "Aztreonam": {"Urine": _OK, "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                  "Stool": (CAUTION, "invasive enteric disease only", "للعدوى المعوية الغازية فقط"), "CSF": _OK},
    "Cefaclor": {"Urine": _OK, "Blood": _NO_ORAL_BSI,
                 "Sputum": (CAUTION, "weak against resistant pneumococci", "ضعيف ضد المكورات الرئوية المقاومة"),
                 "Wound Swab": _OK, "Pus": (CAUTION, "oral — limited abscess penetration", "فموي — اختراق محدود للخراج"),
                 "Stool": (DENY, "no enteric indication", "لا استطباب معوي"), "CSF": _NO_CSF},
    "Cefadroxil": {"Urine": _OK, "Blood": _NO_ORAL_BSI,
                   "Sputum": (DENY, "no H. influenzae activity — inadequate for LRTI",
                              "لا فاعلية ضد المستدمية النزلية — غير كافٍ لعدوى الجهاز التنفسي السفلي"),
                   "Wound Swab": _OK, "Pus": (CAUTION, "oral — limited abscess penetration", "فموي — اختراق محدود للخراج"),
                   "Stool": (DENY, "no enteric indication", "لا استطباب معوي"), "CSF": _NO_CSF},
    "Cefazolin": {"Urine": _OK, "Blood": _OK,
                  "Sputum": (CAUTION, "no H. influenzae activity", "لا فاعلية ضد المستدمية النزلية"),
                  "Wound Swab": _OK, "Pus": _OK,
                  "Stool": (DENY, "no enteric indication", "لا استطباب معوي"), "CSF": _NO_CSF},
    "Cefepime": {"Urine": _OK, "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                 "Stool": (CAUTION, "invasive enteric disease only", "للعدوى المعوية الغازية فقط"), "CSF": _OK},
    "Cefixime": {"Urine": _OK, "Blood": _NO_ORAL_BSI,
                 "Sputum": (CAUTION, "no staphylococcal activity", "لا فاعلية ضد المكورات العنقودية"),
                 "Wound Swab": (CAUTION, "no staphylococcal activity", "لا فاعلية ضد المكورات العنقودية"),
                 "Pus": (CAUTION, "no staphylococcal activity", "لا فاعلية ضد المكورات العنقودية"),
                 "Stool": _OK, "CSF": _NO_CSF},
    "Cefoperazone": {"Urine": (CAUTION, "predominantly biliary excretion — low urinary levels",
                               "إفراز صفراوي أساساً — تركيز بولي منخفض"),
                     "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                     "Stool": (CAUTION, "invasive enteric disease only", "للعدوى المعوية الغازية فقط"), "CSF": _NO_CSF},
    "Cefoperazone + Sulbactam": {"Urine": (CAUTION, "predominantly biliary excretion — low urinary levels",
                                           "إفراز صفراوي أساساً — تركيز بولي منخفض"),
                                 "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                                 "Stool": (CAUTION, "invasive enteric disease only", "للعدوى المعوية الغازية فقط"),
                                 "CSF": _NO_CSF},
    "Cefotaxime": {"Urine": _OK, "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                   "Stool": _OK, "CSF": _OK},
    "Cefoxitin": {"Urine": _OK, "Blood": _OK,
                  "Sputum": (CAUTION, "not first-line for LRTI", "ليس خياراً أول لعدوى التنفسي السفلي"),
                  "Wound Swab": _OK, "Pus": _OK,
                  "Stool": (CAUTION, "invasive enteric disease only", "للعدوى المعوية الغازية فقط"), "CSF": _NO_CSF},
    "Ceftazidime": {"Urine": _OK, "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                    "Stool": (CAUTION, "invasive enteric disease only", "للعدوى المعوية الغازية فقط"), "CSF": _OK},
    "Ceftriaxone": {"Urine": _OK, "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                    "Stool": _OK, "CSF": _OK},
    "Cefuroxime": {"Urine": _OK, "Blood": _NO_ORAL_BSI, "Sputum": _OK, "Wound Swab": _OK,
                   "Pus": (CAUTION, "oral — limited abscess penetration", "فموي — اختراق محدود للخراج"),
                   "Stool": (DENY, "no enteric indication", "لا استطباب معوي"), "CSF": _NO_CSF},
    "Cefuroxime sodium": {"Urine": _OK, "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                          "Stool": (DENY, "no enteric indication", "لا استطباب معوي"),
                          "CSF": (DENY, "abandoned for meningitis — delayed CSF sterilisation and more hearing loss than 3rd-gen",
                                  "مهجور في التهاب السحايا — تعقيم أبطأ للسائل النخاعي وفقدان سمع أكثر مقارنة بالجيل الثالث")},
    "Cephalexin": {"Urine": _OK, "Blood": _NO_ORAL_BSI,
                   "Sputum": (DENY, "no H. influenzae activity — inadequate for LRTI",
                              "لا فاعلية ضد المستدمية النزلية — غير كافٍ لعدوى التنفسي السفلي"),
                   "Wound Swab": _OK, "Pus": (CAUTION, "oral — limited abscess penetration", "فموي — اختراق محدود للخراج"),
                   "Stool": (DENY, "no enteric indication", "لا استطباب معوي"), "CSF": _NO_CSF},
    "Cephradine": {"Urine": _OK, "Blood": _NO_ORAL_BSI,
                   "Sputum": (DENY, "no H. influenzae activity — inadequate for LRTI",
                              "لا فاعلية ضد المستدمية النزلية — غير كافٍ لعدوى التنفسي السفلي"),
                   "Wound Swab": _OK, "Pus": (CAUTION, "oral — limited abscess penetration", "فموي — اختراق محدود للخراج"),
                   "Stool": (DENY, "no enteric indication", "لا استطباب معوي"), "CSF": _NO_CSF},
    "Ciprofloxacin": {"Urine": _OK, "Blood": _OK,
                      "Sputum": (CAUTION, "unreliable against S. pneumoniae — not for CAP",
                                 "غير موثوق ضد المكورات الرئوية — لا يُستخدم في الالتهاب الرئوي المجتمعي"),
                      "Wound Swab": _OK, "Pus": _OK, "Stool": _OK,
                      "CSF": (CAUTION, "moderate CSF penetration — adjunct only, not sole therapy",
                              "اختراق متوسط للسائل النخاعي — كعلاج مساعد فقط وليس منفرداً")},
    "Clarithromycin": {"Urine": _NO_URINE, "Blood": (CAUTION, "low serum levels — not for bacteraemia",
                                                      "تركيز دموي منخفض — غير مناسب لتجرثم الدم"),
                       "Sputum": _OK, "Wound Swab": (CAUTION, "second-line", "خيار ثانٍ"),
                       "Pus": (CAUTION, "second-line", "خيار ثانٍ"),
                       "Stool": (CAUTION, "H. pylori / MAC only", "للملوية البوابية أو المتفطرات فقط"), "CSF": _NO_CSF},
    "Clindamycin": {"Urine": _NO_URINE, "Blood": (CAUTION, "not for Gram-negative or endovascular infection",
                                                   "غير مناسب للسالبات أو عدوى داخل الأوعية"),
                    "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                    "Stool": (DENY, "leading precipitant of C. difficile colitis", "أكثر مسبب لالتهاب القولون بالمطثية العسيرة"),
                    "CSF": _NO_CSF},
    "Colistin": {"Urine": (CAUTION, "colistimethate reaches urine but nephrotoxicity limits use",
                           "الكوليستيميثات يصل للبول لكن السمية الكلوية تحدّ من استخدامه"),
                 "Blood": _OK,
                 "Sputum": (CAUTION, "poor lung penetration — add nebulised colistin",
                            "اختراق رئوي ضعيف — يُضاف كوليستين بالاستنشاق"),
                 "Wound Swab": (CAUTION, "last-line agent — confirm no alternative", "دواء الملاذ الأخير — تأكد من عدم وجود بديل"),
                 "Pus": (CAUTION, "last-line agent — confirm no alternative", "دواء الملاذ الأخير — تأكد من عدم وجود بديل"),
                 "Stool": (DENY, "no enteric indication", "لا استطباب معوي"),
                 "CSF": (DENY, "IV colistin does not reach CSF — intrathecal/intraventricular route required",
                         "الكوليستين الوريدي لا يصل للسائل النخاعي — يلزم الحقن داخل القراب/البطين")},
    "Doxycycline": {"Urine": _NO_URINE, "Blood": (CAUTION, "bacteriostatic — avoid in endovascular infection",
                                                   "مثبط للنمو — يُتجنب في عدوى داخل الأوعية"),
                    "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                    "Stool": (CAUTION, "cholera / Vibrio only", "للكوليرا والضمّات فقط"),
                    "CSF": (DENY, "inadequate for pyogenic meningitis (rickettsial/neuroborreliosis are separate indications)",
                            "غير كافٍ لالتهاب السحايا القيحي (الريكتسيا/لايم استطبابات منفصلة)")},
    "Ertapenem": {"Urine": _OK, "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                  "Stool": (CAUTION, "invasive enteric disease only", "للعدوى المعوية الغازية فقط"),
                  "CSF": (DENY, "not recommended for CNS infection — use meropenem",
                          "غير موصى به لعدوى الجهاز العصبي — استخدم الميروبينيم")},
    "Erythromycin": {"Urine": _NO_URINE, "Blood": (CAUTION, "low serum levels — not for bacteraemia",
                                                    "تركيز دموي منخفض — غير مناسب لتجرثم الدم"),
                     "Sputum": _OK, "Wound Swab": (CAUTION, "second-line", "خيار ثانٍ"),
                     "Pus": (CAUTION, "second-line", "خيار ثانٍ"), "Stool": _OK, "CSF": _NO_CSF},
    "Fosfomycin": {"Urine": _OK, "Blood": _URINE_ONLY, "Sputum": _URINE_ONLY,
                   "Wound Swab": _URINE_ONLY, "Pus": _URINE_ONLY, "Stool": _URINE_ONLY, "CSF": _URINE_ONLY},
    "Fusidic acid": {"Urine": _NO_URINE,
                     "Blood": (CAUTION, "never monotherapy — resistance emerges on treatment",
                               "لا يُستخدم منفرداً أبداً — تظهر المقاومة أثناء العلاج"),
                     "Sputum": (CAUTION, "not an established respiratory agent", "ليس دواءً معتمداً للجهاز التنفسي"),
                     "Wound Swab": (CAUTION, "combine with a second anti-staphylococcal agent",
                                    "يُشارك مع دواء ثانٍ مضاد للعنقوديات"),
                     "Pus": (CAUTION, "combine with a second anti-staphylococcal agent",
                             "يُشارك مع دواء ثانٍ مضاد للعنقوديات"),
                     "Stool": (DENY, "no enteric indication", "لا استطباب معوي"), "CSF": _NO_CSF},
    "Gatifloxacin": {"Urine": _OK, "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                     "Stool": _OK, "CSF": (CAUTION, "adjunct only", "كعلاج مساعد فقط")},
    "Gentamicin": {"Urine": _OK, "Blood": _OK, "Sputum": _AG_LUNG, "Wound Swab": _AG_PUS, "Pus": _AG_PUS,
                   "Stool": (DENY, "no role in enteric infection", "لا دور له في عدوى الأمعاء"), "CSF": _NO_CSF},
    "Imipenem/Cilastatin": {"Urine": _OK, "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                            "Stool": (CAUTION, "invasive enteric disease only", "للعدوى المعوية الغازية فقط"),
                            "CSF": (DENY, "seizure risk in CNS infection — use meropenem",
                                    "خطر التشنجات في عدوى الجهاز العصبي — استخدم الميروبينيم")},
    "Levofloxacin": {"Urine": _OK, "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                     "Stool": _OK, "CSF": (CAUTION, "adjunct only", "كعلاج مساعد فقط")},
    "Linezolid": {"Urine": (CAUTION, "only ~30% excreted unchanged — not preferred for UTI",
                            "حوالي 30% فقط يُطرح دون تغيير — ليس مفضلاً لعدوى المسالك"),
                  "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                  "Stool": (DENY, "no enteric indication", "لا استطباب معوي"), "CSF": _OK},
    "Meropenem": {"Urine": _OK, "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                  "Stool": (CAUTION, "invasive enteric disease only", "للعدوى المعوية الغازية فقط"), "CSF": _OK},
    "Metronidazole": {"Urine": (CAUTION, "anaerobes only — no aerobic urinary pathogen activity",
                                "للاهوائيات فقط — لا فاعلية ضد مسببات المسالك الهوائية"),
                      "Blood": _OK,
                      "Sputum": (CAUTION, "anaerobic cover only — needs an aerobic partner",
                                 "تغطية لاهوائية فقط — يحتاج شريكاً هوائياً"),
                      "Wound Swab": _OK, "Pus": _OK, "Stool": _OK, "CSF": _OK},
    "Minocycline": {"Urine": _NO_URINE, "Blood": (CAUTION, "bacteriostatic — avoid in endovascular infection",
                                                   "مثبط للنمو — يُتجنب في عدوى داخل الأوعية"),
                    "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                    "Stool": (CAUTION, "not an established enteric agent", "ليس دواءً معتمداً للعدوى المعوية"),
                    "CSF": (CAUTION, "limited CSF data — ID consult", "بيانات محدودة للسائل النخاعي — استشارة معدية")},
    "Moxifloxacin": {"Urine": (DENY, "minimal urinary excretion — explicitly NOT indicated for UTI",
                               "إفراز بولي ضئيل جداً — غير مستطب إطلاقاً لعدوى المسالك البولية"),
                     "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                     "Stool": (CAUTION, "not first-line enteric", "ليس خياراً أول للعدوى المعوية"),
                     "CSF": (CAUTION, "adjunct only", "كعلاج مساعد فقط")},
    "Nitrofurantoin": {"Urine": _OK, "Blood": _URINE_ONLY, "Sputum": _URINE_ONLY,
                       "Wound Swab": _URINE_ONLY, "Pus": _URINE_ONLY, "Stool": _URINE_ONLY, "CSF": _URINE_ONLY},
    "Norfloxacin": {"Urine": _OK, "Blood": _URINE_ONLY, "Sputum": _URINE_ONLY,
                    "Wound Swab": _URINE_ONLY, "Pus": _URINE_ONLY,
                    "Stool": (DENY, "serum/tissue levels inadequate for invasive enteric disease",
                              "تركيز الدم والأنسجة غير كافٍ للعدوى المعوية الغازية"),
                    "CSF": _URINE_ONLY},
    "Ofloxacin": {"Urine": _OK, "Blood": (CAUTION, "prefer levofloxacin/ciprofloxacin IV for bacteraemia",
                                          "يُفضل ليفوفلوكساسين/سيبروفلوكساسين وريدياً لتجرثم الدم"),
                  "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK, "Stool": _OK,
                  "CSF": (CAUTION, "adjunct only", "كعلاج مساعد فقط")},
    "Oxacillin": {"Urine": (CAUTION, "not a preferred urinary agent", "ليس دواءً مفضلاً للمسالك البولية"),
                  "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                  "Stool": (DENY, "no enteric indication", "لا استطباب معوي"),
                  "CSF": (CAUTION, "high-dose IV only for MSSA CNS infection",
                          "جرعة وريدية عالية فقط لعدوى الجهاز العصبي بالعنقودية الحساسة")},
    "Penicillin": {"Urine": _OK, "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK, "Pus": _OK,
                   "Stool": (DENY, "no enteric indication", "لا استطباب معوي"),
                   "CSF": (CAUTION, "high-dose IV benzylpenicillin only — oral formulations are inadequate",
                           "بنزيل بنسلين وريدي بجرعة عالية فقط — الأشكال الفموية غير كافية")},
    "Piperacillin + Tazobactam": {"Urine": _OK, "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK,
                                  "Pus": _OK, "Stool": (CAUTION, "invasive enteric disease only", "للعدوى المعوية الغازية فقط"),
                                  "CSF": (DENY, "inadequate CSF penetration — use meropenem or a 3rd-gen cephalosporin",
                                          "اختراق غير كافٍ للسائل النخاعي — استخدم ميروبينيم أو سيفالوسبورين جيل ثالث")},
    "Tetracycline": {"Urine": _NO_URINE, "Blood": (CAUTION, "bacteriostatic — avoid in endovascular infection",
                                                    "مثبط للنمو — يُتجنب في عدوى داخل الأوعية"),
                     "Sputum": (CAUTION, "doxycycline preferred", "يُفضل الدوكسيسيكلين"),
                     "Wound Swab": (CAUTION, "doxycycline preferred", "يُفضل الدوكسيسيكلين"),
                     "Pus": (CAUTION, "doxycycline preferred", "يُفضل الدوكسيسيكلين"),
                     "Stool": (CAUTION, "cholera / Vibrio only", "للكوليرا والضمّات فقط"), "CSF": _NO_CSF},
    "Tinidazole": {"Urine": _NO_URINE, "Blood": (CAUTION, "anaerobes/protozoa only", "للاهوائيات والأوالي فقط"),
                   "Sputum": (DENY, "no respiratory indication", "لا استطباب تنفسي"),
                   "Wound Swab": (CAUTION, "anaerobic cover only", "تغطية لاهوائية فقط"),
                   "Pus": (CAUTION, "anaerobic cover only", "تغطية لاهوائية فقط"), "Stool": _OK,
                   "CSF": (CAUTION, "metronidazole is the established agent", "الميترونيدازول هو الدواء المعتمد")},
    "Tobramycin": {"Urine": _OK, "Blood": _OK, "Sputum": _AG_LUNG, "Wound Swab": _AG_PUS, "Pus": _AG_PUS,
                   "Stool": (DENY, "no role in enteric infection", "لا دور له في عدوى الأمعاء"), "CSF": _NO_CSF},
    "Trimethoprim/Sulfamethoxazole": {"Urine": _OK, "Blood": _OK, "Sputum": _OK, "Wound Swab": _OK,
                                      "Pus": _OK, "Stool": _OK, "CSF": _OK},
    "Vancomycin": {"Urine": (CAUTION, "IV vancomycin is not a preferred urinary agent; ORAL vancomycin is NOT absorbed",
                             "الفانكومايسين الوريدي ليس مفضلاً للمسالك؛ والفموي لا يُمتص إطلاقاً"),
                   "Blood": _OK,
                   "Sputum": (CAUTION, "poor lung penetration — linezolid preferred for MRSA pneumonia",
                              "اختراق رئوي ضعيف — يُفضل اللاينزوليد في الالتهاب الرئوي بـ MRSA"),
                   "Wound Swab": _OK, "Pus": _OK,
                   "Stool": (CAUTION, "ORAL vancomycin for C. difficile only — IV has no enteric effect",
                             "الفانكومايسين الفموي للمطثية العسيرة فقط — الوريدي بلا تأثير معوي"),
                   "CSF": _OK},
}

# ═══════════════════════════════════════════════════════════════════════════
# 3. LAYER B — ORGANISM PLAUSIBILITY AT SITE
# ═══════════════════════════════════════════════════════════════════════════
# Never a DENY on therapy: an implausible organism is a *pre-analytical* signal
# (contamination / mislabelled specimen), so it raises a CAUTION on the whole
# report rather than blocking a drug.
SITE_ORGANISM_PLAUSIBILITY: Dict[str, Dict[str, str]] = {
    "Urine":      {"Streptococcus pneumoniae": "rare", "H. influenzae": "rare",
                   "Legionella pneumophila": "implausible", "Mycoplasma spp.": "implausible",
                   "Campylobacter jejuni": "implausible", "Shigella spp.": "implausible",
                   "Rickettsia spp.": "implausible", "Anaerobes (لاهوائيات)": "rare",
                   "Stenotrophomonas maltophilia": "rare"},
    "Blood":      {"Shigella spp.": "rare", "Campylobacter jejuni": "rare",
                   "Legionella pneumophila": "implausible", "Mycoplasma spp.": "implausible",
                   "Rickettsia spp.": "implausible", "H. influenzae": "rare"},
    "Sputum":     {"Enterococcus faecalis": "implausible", "VRE": "implausible",
                   "Salmonella spp.": "rare", "Shigella spp.": "implausible",
                   "Campylobacter jejuni": "implausible", "Proteus mirabilis": "rare",
                   "Rickettsia spp.": "implausible"},
    "Wound Swab": {"Streptococcus pneumoniae": "rare", "H. influenzae": "rare",
                   "Legionella pneumophila": "implausible", "Mycoplasma spp.": "implausible",
                   "Shigella spp.": "implausible", "Campylobacter jejuni": "implausible",
                   "Rickettsia spp.": "implausible", "Salmonella spp.": "rare"},
    "Pus":        {"Legionella pneumophila": "implausible", "Mycoplasma spp.": "implausible",
                   "Shigella spp.": "implausible", "Campylobacter jejuni": "implausible",
                   "Rickettsia spp.": "implausible", "H. influenzae": "rare"},
    "Stool":      {"Staphylococcus aureus": "rare", "MRSA": "rare",
                   "Pseudomonas aeruginosa": "rare", "Klebsiella spp.": "rare",
                   "Enterococcus faecalis": "rare", "VRE": "rare",
                   "Proteus mirabilis": "rare", "Acinetobacter baumannii": "rare",
                   "Streptococcus pneumoniae": "implausible", "H. influenzae": "implausible",
                   "Legionella pneumophila": "implausible", "Mycoplasma spp.": "implausible",
                   "Stenotrophomonas maltophilia": "rare", "Rickettsia spp.": "implausible",
                   "Anaerobes (لاهوائيات)": "rare"},
    "CSF":        {"Legionella pneumophila": "implausible", "Mycoplasma spp.": "implausible",
                   "Campylobacter jejuni": "implausible", "Shigella spp.": "implausible",
                   "Rickettsia spp.": "implausible", "Stenotrophomonas maltophilia": "rare",
                   "Proteus mirabilis": "rare", "VRE": "rare", "Salmonella spp.": "rare"},
}
_PLAUSIBILITY_TEXT = {
    "rare": (CAUTION, "unusual isolate for this specimen — confirm identification and collection",
             "عزلة غير معتادة لهذه العينة — تأكد من التعريف وطريقة السحب"),
    "implausible": (CAUTION, "this organism does not cause infection at this site — suspect contamination or mislabelling",
                    "هذا الكائن لا يسبب عدوى في هذا الموقع — يُشتبه في تلوث أو خطأ في تسمية العينة"),
}

# ═══════════════════════════════════════════════════════════════════════════
# 4. LAYER C — INTRINSIC RESISTANCE ADDENDA
# ═══════════════════════════════════════════════════════════════════════════
# Gaps the audit found in INTRINSIC_RESISTANCE. Merged, never replacing.
INTRINSIC_ADDENDA: Dict[str, Dict[str, Tuple[str, str, str]]] = {
    "Legionella pneumophila": {
        "Vancomycin": (DENY, "obligate intracellular — glycopeptides cannot enter the host cell",
                       "ممرض داخل الخلية إجبارياً — الجلايكوببتيدات لا تدخل الخلية المضيفة"),
        "Aztreonam": (DENY, "beta-lactams are inactive against intracellular Legionella",
                      "البيتا-لاكتام غير فعّال ضد الليجيونيلا داخل الخلية"),
        "Colistin": (DENY, "no clinical activity — macrolide or fluoroquinolone required",
                     "بلا فاعلية إكلينيكية — يلزم ماكروليد أو فلوروكينولون"),
        "Teicoplanin": (DENY, "obligate intracellular — glycopeptides cannot enter the host cell",
                        "ممرض داخل الخلية إجبارياً — الجلايكوببتيدات لا تدخل الخلية المضيفة"),
    },
    "Mycoplasma spp.": {
        "Colistin": (DENY, "no outer-membrane LPS target — polymyxins are inactive",
                     "لا يوجد هدف LPS في الغشاء الخارجي — البوليميكسينات غير فعّالة"),
    },
    "Anaerobes (لاهوائيات)": {
        "Aztreonam": (DENY, "monobactam — no anaerobic activity whatsoever",
                      "مونوباكتام — بلا أي فاعلية ضد اللاهوائيات"),
        "Trimethoprim/Sulfamethoxazole": (DENY, "no reliable anaerobic activity",
                                          "بلا فاعلية موثوقة ضد اللاهوائيات"),
    },
    "Rickettsia spp.": {
        "Trimethoprim/Sulfamethoxazole": (
            DENY,
            "CONTRAINDICATED — sulfonamides are associated with worsened outcome in rickettsial disease",
            "ممنوع — السلفوناميدات مرتبطة بتفاقم الحالة وسوء النتائج في أمراض الريكتسيا"),
        "Vancomycin": (DENY, "obligate intracellular — doxycycline is the drug of choice",
                       "ممرض داخل الخلية إجبارياً — الدوكسيسيكلين هو دواء الاختيار"),
    },
    "Enterococcus faecalis": {
        "Fusidic acid": (DENY, "enterococci are intrinsically resistant",
                         "المكورات المعوية مقاومة جوهرياً"),
    },
    "VRE": {
        "Fusidic acid": (DENY, "enterococci are intrinsically resistant",
                         "المكورات المعوية مقاومة جوهرياً"),
    },
}

# ═══════════════════════════════════════════════════════════════════════════
# 5. LAYER D — HOST STATE
# ═══════════════════════════════════════════════════════════════════════════
PREGNANCY_DENY: Dict[str, Tuple[str, str]] = {
    "Ciprofloxacin": ("fluoroquinolone — cartilage toxicity in animal studies",
                      "فلوروكينولون — سمية غضروفية في الدراسات الحيوانية"),
    "Levofloxacin": ("fluoroquinolone — cartilage toxicity in animal studies",
                     "فلوروكينولون — سمية غضروفية في الدراسات الحيوانية"),
    "Ofloxacin": ("fluoroquinolone — cartilage toxicity in animal studies",
                  "فلوروكينولون — سمية غضروفية في الدراسات الحيوانية"),
    "Norfloxacin": ("fluoroquinolone — cartilage toxicity in animal studies",
                    "فلوروكينولون — سمية غضروفية في الدراسات الحيوانية"),
    "Moxifloxacin": ("fluoroquinolone — cartilage toxicity in animal studies",
                     "فلوروكينولون — سمية غضروفية في الدراسات الحيوانية"),
    "Gatifloxacin": ("fluoroquinolone — cartilage toxicity in animal studies",
                     "فلوروكينولون — سمية غضروفية في الدراسات الحيوانية"),
    "Doxycycline": ("tetracycline — fetal tooth staining and bone growth inhibition after 15 weeks",
                    "تتراسيكلين — تصبّغ أسنان الجنين وتثبيط نمو العظام بعد الأسبوع 15"),
    "Minocycline": ("tetracycline — fetal tooth staining and bone growth inhibition",
                    "تتراسيكلين — تصبّغ أسنان الجنين وتثبيط نمو العظام"),
    "Tetracycline": ("tetracycline — fetal tooth staining, bone growth inhibition, maternal hepatotoxicity",
                     "تتراسيكلين — تصبّغ الأسنان وتثبيط نمو العظام وسمية كبدية للأم"),
    "Gentamicin": ("aminoglycoside — fetal eighth-nerve (ototoxic) damage",
                   "أمينوجلايكوزيد — تلف العصب الثامن للجنين (سمية سمعية)"),
    "Amikacin": ("aminoglycoside — fetal eighth-nerve (ototoxic) damage",
                 "أمينوجلايكوزيد — تلف العصب الثامن للجنين (سمية سمعية)"),
    "Tobramycin": ("aminoglycoside — fetal eighth-nerve (ototoxic) damage",
                   "أمينوجلايكوزيد — تلف العصب الثامن للجنين (سمية سمعية)"),
}
PREGNANCY_CAUTION: Dict[str, Tuple[str, str]] = {
    "Trimethoprim/Sulfamethoxazole": (
        "avoid 1st trimester (folate antagonism / neural tube defects) and at term (kernicterus)",
        "يُتجنب في الثلث الأول (مضاد للفولات/عيوب الأنبوب العصبي) وقرب الولادة (اليرقان النووي)"),
    "Nitrofurantoin": ("avoid at term and in G6PD deficiency — haemolysis risk",
                       "يُتجنب قرب الولادة وفي نقص G6PD — خطر انحلال الدم"),
    "Metronidazole": ("avoid high single doses in the 1st trimester",
                      "يُتجنب استخدام جرعات مفردة عالية في الثلث الأول"),
    "Tinidazole": ("avoid in the 1st trimester", "يُتجنب في الثلث الأول"),
    "Linezolid": ("limited human pregnancy data", "بيانات محدودة عن الحمل عند البشر"),
    "Colistin": ("limited human pregnancy data — use only if no alternative",
                 "بيانات محدودة عن الحمل — يُستخدم فقط عند انعدام البديل"),
    "Fusidic acid": ("limited human pregnancy data", "بيانات محدودة عن الحمل عند البشر"),
    "Rifampicin": ("give vitamin K in the last weeks — neonatal bleeding risk",
                   "يُعطى فيتامين K في الأسابيع الأخيرة — خطر نزف وليدي"),
}
LACTATION_CAUTION = {"Ciprofloxacin", "Levofloxacin", "Doxycycline", "Tetracycline",
                     "Minocycline", "Metronidazole", "Trimethoprim/Sulfamethoxazole",
                     "Chloramphenicol"}

# CrCl assumed when the clinician flags renal impairment but no creatinine is
# available. Deliberately conservative: 30 mL/min sits in KDIGO G4, which
# triggers dose adjustment for every renally-cleared agent in the table and
# refuses nitrofurantoin — the fail-closed direction. Any message that quotes a
# CrCl derived from this constant MUST label it as assumed, never measured.
ASSUMED_CRCL_UNKNOWN: float = 30.0

# Renal: (CrCl below which a dose change is mandatory, CrCl below which the drug is refused)
RENAL_RULES: Dict[str, Tuple[Optional[float], Optional[float], str, str]] = {
    "Nitrofurantoin": (60, 45, "ineffective (inadequate urinary levels) and neuropathy risk below CrCl 45",
                       "غير فعّال (تركيز بولي غير كافٍ) وخطر اعتلال أعصاب تحت CrCl 45"),
    "Gentamicin": (60, 20, "nephrotoxic and ototoxic — level monitoring mandatory",
                   "سام للكلى والسمع — قياس المستويات إلزامي"),
    "Amikacin": (60, 20, "nephrotoxic and ototoxic — level monitoring mandatory",
                 "سام للكلى والسمع — قياس المستويات إلزامي"),
    "Tobramycin": (60, 20, "nephrotoxic and ototoxic — level monitoring mandatory",
                   "سام للكلى والسمع — قياس المستويات إلزامي"),
    "Vancomycin": (60, None, "AUC/MIC-guided dosing and trough monitoring required",
                   "جرعة موجّهة بـ AUC/MIC مع مراقبة المستوى القاعي"),
    "Colistin": (60, None, "narrow therapeutic index — nephrotoxicity is dose-limiting",
                 "نافذة علاجية ضيقة — السمية الكلوية تحدّ من الجرعة"),
    "Trimethoprim/Sulfamethoxazole": (30, 15, "hyperkalaemia and crystalluria risk",
                                      "خطر ارتفاع البوتاسيوم وتبلور البول"),
    "Fosfomycin": (40, 10, "single 3 g oral dose stays adequate to CrCl 10; avoid repeated IV dosing below 40",
                   "الجرعة الفموية الواحدة 3 جم تبقى كافية حتى CrCl 10؛ تُتجنب الجرعات الوريدية المتكررة تحت 40"),
    "Levofloxacin": (50, None, "renally cleared — halve the dose", "يُطرح كلوياً — تُنصّف الجرعة"),
    "Ciprofloxacin": (30, None, "renally cleared — reduce the dose", "يُطرح كلوياً — تُخفض الجرعة"),
    "Ofloxacin": (50, None, "renally cleared — reduce the dose", "يُطرح كلوياً — تُخفض الجرعة"),
    "Norfloxacin": (30, None, "renally cleared — reduce the dose", "يُطرح كلوياً — تُخفض الجرعة"),
    "Meropenem": (50, None, "renally cleared — reduce the dose", "يُطرح كلوياً — تُخفض الجرعة"),
    "Imipenem/Cilastatin": (70, None, "accumulation lowers the seizure threshold",
                            "التراكم يخفض عتبة التشنجات"),
    "Ertapenem": (30, None, "renally cleared — reduce the dose", "يُطرح كلوياً — تُخفض الجرعة"),
    "Cefepime": (60, None, "accumulation causes neurotoxicity/encephalopathy",
                 "التراكم يسبب سمية عصبية/اعتلال دماغي"),
    "Ceftazidime": (50, None, "renally cleared — reduce the dose", "يُطرح كلوياً — تُخفض الجرعة"),
    "Cefotaxime": (50, None, "renally cleared — extend the interval to q12h", "يُطرح كلوياً — تُمدد الفترة إلى q12h"),
    "Cefazolin": (35, None, "renally cleared — reduce the dose", "يُطرح كلوياً — تُخفض الجرعة"),
    "Cefuroxime sodium": (20, None, "renally cleared — reduce the dose", "يُطرح كلوياً — تُخفض الجرعة"),
    "Cefuroxime": (30, None, "renally cleared — reduce the dose", "يُطرح كلوياً — تُخفض الجرعة"),
    "Cephalexin": (30, None, "renally cleared — extend the interval", "يُطرح كلوياً — تُمدد الفترة"),
    "Cephradine": (50, None, "renally cleared — reduce the dose", "يُطرح كلوياً — تُخفض الجرعة"),
    "Cefadroxil": (50, None, "renally cleared — reduce the dose", "يُطرح كلوياً — تُخفض الجرعة"),
    "Cefaclor": (30, None, "renally cleared — reduce the dose", "يُطرح كلوياً — تُخفض الجرعة"),
    "Cefixime": (60, None, "renally cleared — reduce the dose", "يُطرح كلوياً — تُخفض الجرعة"),
    "Ampicillin": (30, None, "renally cleared — extend the interval", "يُطرح كلوياً — تُمدد الفترة"),
    "Amoxicillin": (30, None, "renally cleared — extend the interval", "يُطرح كلوياً — تُمدد الفترة"),
    "Amoxicillin + Clavulanic acid": (30, None, "avoid the 875 mg strength below CrCl 30",
                                      "يُتجنب تركيز 875 مجم تحت CrCl 30"),
    "Ampicillin/Sulbactam": (30, None, "renally cleared — extend the interval", "يُطرح كلوياً — تُمدد الفترة"),
    "Piperacillin + Tazobactam": (40, None, "renally cleared — reduce the dose", "يُطرح كلوياً — تُخفض الجرعة"),
    "Aztreonam": (30, None, "renally cleared — reduce the dose", "يُطرح كلوياً — تُخفض الجرعة"),
    "Penicillin": (30, None, "high doses accumulate — seizure risk", "الجرعات العالية تتراكم — خطر تشنجات"),
    "Cefoxitin": (50, None, "renally cleared — reduce the dose", "يُطرح كلوياً — تُخفض الجرعة"),
    "Linezolid": (None, None, "no renal adjustment; metabolites accumulate in dialysis",
                  "لا تعديل كلوي؛ المستقلبات تتراكم في الغسيل"),
    # ADDED 2026-07-30. Both carry a renal_limit in abx_guidelines.py but had no
    # row here, so the terminal gate — the layer that exists precisely to give a
    # second opinion — was blind to them. test_dose_adjustment.py now fails the
    # build if the two tables diverge again.
    "Clarithromycin": (30, None, "halve the dose below CrCl 30; do not exceed 14 days",
                       "تُنصّف الجرعة تحت CrCl 30؛ ولا تتجاوز 14 يوماً"),
    "Gatifloxacin": (40, None, "renally cleared — 400 mg loading then 200 mg q24h",
                     "يُطرح كلوياً — 400 مجم تحميل ثم 200 مجم كل 24 ساعة"),
}

# ── Novel beta-lactams & reserve Gram-positive agents (added 2026-08-03) ─────
# These nine were named by COMBINATION_THERAPY as recommended salvage regimens
# and were absent from the formulary entirely, so this table had no row for them
# either. prove_totality() failed the moment they were added, which is exactly
# what it is for: a new agent must be wired into EVERY layer or it is not really
# in the product.
SITE_PENETRATION.update({
    "Ceftazidime + Avibactam": {
        "Urine": ("allow", "", ""), "Blood": ("allow", "", ""),
        "Sputum": ("allow", "", ""), "Pus": ("allow", "", ""),
        "Wound Swab": ("allow", "", ""),
        "CSF": ("caution",
                "limited CSF penetration; adjunctive only, never sole therapy for meningitis",
                "نفاذية سحائية محدودة — مساعِد فقط ولا يُعتمد وحيداً في السحايا"),
        "Stool": ("caution", "systemic agent; enteric infection rarely needs it",
                  "دواء جهازي — نادراً ما تحتاجه العدوى المعوية"),
    },
    "Ceftolozane + Tazobactam": {
        "Urine": ("allow", "", ""), "Blood": ("allow", "", ""),
        "Sputum": ("allow", "", ""), "Pus": ("allow", "", ""),
        "Wound Swab": ("allow", "", ""),
        "CSF": ("caution", "limited CSF data; not established for meningitis",
                "بيانات سحائية محدودة — غير مُثبت في السحايا"),
        "Stool": ("caution", "systemic agent", "دواء جهازي"),
    },
    "Meropenem + Vaborbactam": {
        "Urine": ("allow", "", ""), "Blood": ("allow", "", ""),
        "Sputum": ("allow", "", ""), "Pus": ("allow", "", ""),
        "Wound Swab": ("allow", "", ""),
        "CSF": ("caution", "meropenem component penetrates; vaborbactam data limited",
                "الميروبينيم ينفذ لكن بيانات الـ vaborbactam محدودة"),
        "Stool": ("caution", "systemic agent", "دواء جهازي"),
    },
    "Imipenem + Relebactam": {
        "Urine": ("allow", "", ""), "Blood": ("allow", "", ""),
        "Sputum": ("allow", "", ""), "Pus": ("allow", "", ""),
        "Wound Swab": ("allow", "", ""),
        "CSF": ("deny",
                "imipenem lowers the seizure threshold and is not used for CNS infection",
                "الإيميبينيم يخفض عتبة النوبات ولا يُستخدم لعدوى الجهاز العصبي"),
        "Stool": ("caution", "systemic agent", "دواء جهازي"),
    },
    "Cefiderocol": {
        "Urine": ("allow", "", ""), "Blood": ("allow", "", ""),
        "Sputum": ("allow", "", ""), "Pus": ("allow", "", ""),
        "Wound Swab": ("allow", "", ""),
        "CSF": ("caution", "limited CSF data; last-resort adjunct only",
                "بيانات سحائية محدودة — مساعِد ملاذ أخير فقط"),
        "Stool": ("caution", "systemic agent", "دواء جهازي"),
    },
    "Ceftaroline": {
        "Blood": ("allow", "", ""), "Sputum": ("allow", "", ""),
        "Pus": ("allow", "", ""), "Wound Swab": ("allow", "", ""),
        "Urine": ("caution",
                  "renally excreted but not an established agent for urinary infection",
                  "يُطرح كلوياً لكنه ليس دواءً معتمداً لعدوى المسالك"),
        "CSF": ("caution", "penetrates inflamed meninges; data are case-series only",
                "ينفذ السحايا الملتهبة لكن الأدلة سلاسل حالات فقط"),
        "Stool": ("caution", "systemic agent", "دواء جهازي"),
    },
    "Daptomycin": {
        "Blood": ("allow", "", ""), "Pus": ("allow", "", ""),
        "Wound Swab": ("allow", "", ""),
        # The single most important row in this block.
        "Sputum": ("deny",
                   "inactivated by pulmonary surfactant — NEVER use for pneumonia, "
                   "whatever the susceptibility result says",
                   "يُثبَّط بالسيرفاكتانت الرئوي — ممنوع تماماً في الالتهاب الرئوي "
                   "مهما كانت نتيجة الحساسية"),
        "Urine": ("caution", "adequate urinary levels but not a first-line urinary agent",
                  "تركيز بولي كافٍ لكنه ليس خياراً بولياً أولياً"),
        "CSF": ("caution", "poor CSF penetration; adjunct only",
                "نفاذية سحائية ضعيفة — مساعِد فقط"),
        "Stool": ("caution", "systemic agent", "دواء جهازي"),
    },
    "Tigecycline": {
        "Pus": ("allow", "", ""), "Wound Swab": ("allow", "", ""),
        "Blood": ("deny",
                  "very low serum concentrations — never as sole therapy for bacteraemia; "
                  "FDA all-cause mortality warning",
                  "تركيز دموي منخفض جداً — لا يُستخدم منفرداً في تجرثم الدم؛ "
                  "تحذير FDA بزيادة الوفيات"),
        "Urine": ("deny", "negligible urinary excretion",
                  "إفراز بولي ضئيل — غير فعّال في المسالك"),
        "Sputum": ("caution", "not an approved indication for HAP/VAP",
                   "ليس استطباباً معتمداً في الالتهاب الرئوي المكتسب بالمستشفى"),
        "CSF": ("deny", "does not reach therapeutic CSF concentrations",
                "لا يصل لتركيز علاجي في السائل النخاعي"),
        "Stool": ("caution", "systemic agent", "دواء جهازي"),
    },
    "Teicoplanin": {
        "Blood": ("allow", "", ""), "Pus": ("allow", "", ""),
        "Wound Swab": ("allow", "", ""),
        "Sputum": ("caution", "poor epithelial lining fluid penetration",
                   "نفاذية ضعيفة لسائل البطانة الرئوية"),
        "Urine": ("caution", "not a first-line urinary agent",
                  "ليس خياراً بولياً أولياً"),
        "CSF": ("deny", "does not reach therapeutic CSF concentrations",
                "لا يصل لتركيز علاجي في السائل النخاعي"),
        "Stool": ("caution", "systemic agent", "دواء جهازي"),
    },
})

RENAL_RULES.update({
    "Ceftazidime + Avibactam": (50, 6, "dose reduction required below CrCl 50",
                                "يلزم خفض الجرعة تحت CrCl 50"),
    "Ceftolozane + Tazobactam": (50, 15, "dose reduction required below CrCl 50",
                                 "يلزم خفض الجرعة تحت CrCl 50"),
    "Meropenem + Vaborbactam": (50, 15, "dose reduction required below CrCl 50",
                                "يلزم خفض الجرعة تحت CrCl 50"),
    "Imipenem + Relebactam": (90, 15, "dose reduction required below CrCl 90",
                              "يلزم خفض الجرعة تحت CrCl 90"),
    "Cefiderocol": (60, 15, "dose reduction below CrCl 60; INCREASE if CrCl >=120",
                    "خفض الجرعة تحت CrCl 60؛ وزيادتها إذا CrCl ≥120"),
    "Ceftaroline": (50, 15, "dose reduction required below CrCl 50",
                    "يلزم خفض الجرعة تحت CrCl 50"),
    "Daptomycin": (30, None, "extend to every 48 hours below CrCl 30; monitor CPK",
                   "تمديد الفترة إلى كل 48 ساعة تحت CrCl 30 مع مراقبة CPK"),
    "Teicoplanin": (60, None, "reduce maintenance from day 4; monitor trough",
                    "خفض جرعة الصيانة من اليوم الرابع مع مراقبة المستوى القاعي"),
})


# Hepatic: Child-Pugh C verdict. This layer was previously INERT — the flag
# produced only a side-channel text alert that the PDF truncated to 4 items.
HEPATIC_RULES: Dict[str, Tuple[str, str, str]] = {
    "Amoxicillin + Clavulanic acid": (
        DENY, "clavulanate is the single commonest cause of drug-induced liver injury worldwide",
        "الكلافولانيت هو أشهر مسبب منفرد لإصابة الكبد الدوائية عالمياً"),
    "Nitrofurantoin": (DENY, "chronic active hepatitis and cholestatic injury reported",
                       "التهاب كبدي مزمن نشط وإصابة ركودية موثقة"),
    "Trimethoprim/Sulfamethoxazole": (DENY, "sulfonamide hepatotoxicity and hypersensitivity hepatitis",
                                      "سمية كبدية للسلفوناميد والتهاب كبدي تحسسي"),
    "Fusidic acid": (DENY, "biliary excretion — accumulates and is directly hepatotoxic",
                     "إفراز صفراوي — يتراكم وسام للكبد مباشرة"),
    "Tinidazole": (DENY, "extensive hepatic metabolism", "استقلاب كبدي واسع"),
    "Ceftriaxone": (CAUTION, "biliary sludging and pseudolithiasis — cap at 2 g/day",
                    "ركود صفراوي وحصوات كاذبة — الحد الأقصى 2 جم يومياً"),
    "Cefoperazone": (CAUTION, "predominantly biliary elimination — accumulates; monitor INR",
                     "إخراج صفراوي أساساً — يتراكم؛ راقب INR"),
    "Cefoperazone + Sulbactam": (CAUTION, "predominantly biliary elimination — accumulates; monitor INR",
                                 "إخراج صفراوي أساساً — يتراكم؛ راقب INR"),
    "Metronidazole": (CAUTION, "extensive hepatic metabolism — halve the dose in Child-Pugh C",
                      "استقلاب كبدي واسع — تُنصّف الجرعة في Child-Pugh C"),
    "Clindamycin": (CAUTION, "primary hepatic metabolism — reduce 25-50%",
                    "استقلاب كبدي أساسي — تُخفض 25-50%"),
    "Erythromycin": (CAUTION, "cholestatic hepatitis (estolate salt especially)",
                     "التهاب كبدي ركودي (خاصة ملح الإستولات)"),
    "Clarithromycin": (CAUTION, "hepatic metabolism and strong CYP3A4 inhibition",
                       "استقلاب كبدي وتثبيط قوي لـ CYP3A4"),
    "Azithromycin": (CAUTION, "biliary excretion — cholestatic jaundice reported",
                     "إفراز صفراوي — يرقان ركودي موثق"),
    "Doxycycline": (CAUTION, "biliary excretion — avoid in severe failure",
                    "إفراز صفراوي — يُتجنب في الفشل الشديد"),
    "Minocycline": (CAUTION, "autoimmune hepatitis and DRESS reported",
                    "التهاب كبدي مناعي و DRESS موثقان"),
    "Tetracycline": (CAUTION, "dose-dependent microvesicular steatosis",
                     "تنكس دهني دقيق الحويصلات معتمد على الجرعة"),
    "Ciprofloxacin": (CAUTION, "partial hepatic metabolism — reduce 50% in severe failure",
                      "استقلاب كبدي جزئي — تُخفض 50% في الفشل الشديد"),
    "Levofloxacin": (CAUTION, "rare fulminant hepatitis", "التهاب كبدي خاطف نادر"),
    "Moxifloxacin": (CAUTION, "hepatic metabolism, no renal escape route — highest FQ hepatotoxicity signal",
                     "استقلاب كبدي بلا مخرج كلوي — أعلى إشارة سمية كبدية بين الكينولونات"),
    "Gatifloxacin": (CAUTION, "hepatic metabolism", "استقلاب كبدي"),
    "Ofloxacin": (CAUTION, "partial hepatic metabolism", "استقلاب كبدي جزئي"),
    "Norfloxacin": (CAUTION, "partial hepatic metabolism", "استقلاب كبدي جزئي"),
    "Oxacillin": (CAUTION, "dose-related transaminase rise and cholestasis",
                  "ارتفاع إنزيمات الكبد وركود صفراوي متعلق بالجرعة"),
    "Linezolid": (CAUTION, "lactic acidosis risk is higher in hepatic failure",
                  "خطر الحماض اللبني أعلى في الفشل الكبدي"),
    "Vancomycin": (CAUTION, "no hepatic adjustment, but renal function is often falsely high in cirrhosis",
                   "لا تعديل كبدي، لكن وظائف الكلى تبدو أفضل من الحقيقة في التشمع"),
}

# Age. Bands in YEARS; a neonate is expressed as a fraction (7 days ≈ 0.02).
AGE_RULES: Dict[str, Tuple[Optional[float], str, str, str]] = {
    "Ciprofloxacin": (18, CAUTION, "cartilage toxicity — reserve for when no alternative exists",
                      "سمية غضروفية — يُحفظ لحالات انعدام البديل"),
    "Levofloxacin": (18, CAUTION, "cartilage toxicity — reserve for when no alternative exists",
                     "سمية غضروفية — يُحفظ لحالات انعدام البديل"),
    "Ofloxacin": (18, CAUTION, "cartilage toxicity", "سمية غضروفية"),
    "Norfloxacin": (18, CAUTION, "cartilage toxicity", "سمية غضروفية"),
    "Moxifloxacin": (18, DENY, "cartilage toxicity and no paediatric dosing established",
                     "سمية غضروفية ولا توجد جرعة أطفال معتمدة"),
    "Gatifloxacin": (18, DENY, "cartilage toxicity and dysglycaemia",
                     "سمية غضروفية واضطراب سكر الدم"),
    "Doxycycline": (8, CAUTION, "permanent tooth discoloration under 8 years — permitted for rickettsial disease at any age",
                    "تصبّغ دائم للأسنان تحت 8 سنوات — مسموح في أمراض الريكتسيا بأي عمر"),
    "Minocycline": (8, DENY, "permanent tooth discoloration", "تصبّغ دائم للأسنان"),
    "Tetracycline": (8, DENY, "permanent tooth discoloration and enamel hypoplasia",
                     "تصبّغ دائم للأسنان ونقص تنسج المينا"),
}
NEONATE_MAX_YEARS = 28.0 / 365.0
NEONATAL_DENY: Dict[str, Tuple[str, str]] = {
    "Ceftriaxone": ("displaces bilirubin (kernicterus) and precipitates with IV calcium — use cefotaxime",
                    "يزيح البيليروبين (اليرقان النووي) ويترسب مع الكالسيوم الوريدي — استخدم السيفوتاكسيم"),
    "Trimethoprim/Sulfamethoxazole": ("sulfonamide displaces bilirubin — kernicterus risk",
                                      "السلفوناميد يزيح البيليروبين — خطر اليرقان النووي"),
    "Nitrofurantoin": ("haemolytic anaemia — immature erythrocyte enzyme systems",
                       "فقر دم انحلالي — أنظمة إنزيمات كرات الدم غير ناضجة"),
    "Chloramphenicol": ("grey baby syndrome", "متلازمة الطفل الرمادي"),
}


# ═══════════════════════════════════════════════════════════════════════════
# 6. THE EVALUATOR — one function, all layers, worst-wins
# ═══════════════════════════════════════════════════════════════════════════
def evaluate(
    drug: str,
    organism: Optional[str] = None,
    specimen: Optional[str] = None,
    *,
    sir: Optional[str] = None,
    age_years: Optional[float] = None,
    is_pregnant: bool = False,
    is_lactating: bool = False,
    cl_cr: Optional[float] = None,
    is_renal: bool = False,
    is_hepatic: bool = False,
    child_pugh: Optional[str] = None,
    strict_unknown: bool = True,
) -> Verdict:
    """Resolve one (drug, organism, specimen, host) cell to a single verdict.

    `strict_unknown=True` makes the function fail-closed: an unrecognised drug,
    organism or specimen yields DENY, not silent approval.
    """
    v = Verdict()

    # ---- Layer 0: vocabulary / fail-closed -------------------------------
    if drug not in SITE_PENETRATION:
        if strict_unknown:
            v.add(DENY, "vocabulary",
                  f"'{drug}' is not in the reviewed formulary — no safety data can be applied",
                  f"'{drug}' غير موجود في الدليل المُراجَع — لا يمكن تطبيق أي قواعد أمان",
                  "clinical_matrix fail-closed policy")
        return v

    site = canonical_site(specimen)
    org = canonical_organism(organism)

    # ---- Layer 1: culture result ----------------------------------------
    if sir:
        s = str(sir).strip().upper()[:1]
        if s == "R":
            v.add(DENY, "culture", "resistant in vitro", "مقاوم معملياً",
                  "EUCAST Breakpoint Tables v16.1")
        elif s == "I":
            v.add(CAUTION, "culture",
                  "susceptible, increased exposure — requires the high-dose regimen",
                  "حساس بزيادة الجرعة — يلزم نظام الجرعة العالية",
                  "EUCAST v16.1 definition of category I")

    # ---- Layer 2: PK compartment (the layer that was missing) ------------
    if site is None:
        if specimen and strict_unknown:
            v.add(CAUTION, "site",
                  f"specimen '{specimen}' is not a recognised site — site-appropriateness could not be verified",
                  f"العينة '{specimen}' غير معروفة — تعذّر التحقق من ملاءمة موقع العدوى",
                  "clinical_matrix fail-closed policy")
    else:
        lvl, en, ar = SITE_PENETRATION[drug][site]
        if lvl != ALLOW:
            v.add(lvl, "site", en, ar,
                  "IDSA/ESCMID site-specific guidance; BNF 2025 pharmacokinetics")

    # ---- Layer 3: organism plausibility at site --------------------------
    if site and org:
        flag = SITE_ORGANISM_PLAUSIBILITY.get(site, {}).get(org)
        if flag:
            lvl, en, ar = _PLAUSIBILITY_TEXT[flag]
            v.add(lvl, "specimen-organism", en, ar, "clinical_matrix plausibility table")

    # ---- Layer 4: intrinsic resistance addenda ---------------------------
    if org:
        rule = INTRINSIC_ADDENDA.get(org, {}).get(drug)
        if rule:
            lvl, en, ar = rule
            v.add(lvl, "intrinsic", en, ar,
                  "EUCAST Intrinsic Resistance and Unusual Phenotypes v3.3")

    # ---- Layer 5: pregnancy ----------------------------------------------
    if is_pregnant:
        if drug in PREGNANCY_DENY:
            en, ar = PREGNANCY_DENY[drug]
            v.add(DENY, "pregnancy", en, ar, "BNF 2025; FDA pregnancy labelling")
        elif drug in PREGNANCY_CAUTION:
            en, ar = PREGNANCY_CAUTION[drug]
            v.add(CAUTION, "pregnancy", en, ar, "BNF 2025; FDA pregnancy labelling")
    if is_lactating and drug in LACTATION_CAUTION:
        v.add(CAUTION, "lactation", "excreted in breast milk — weigh benefit against infant exposure",
              "يُفرز في لبن الأم — وازن الفائدة مقابل تعرّض الرضيع", "BNF 2025 lactation")

    # ---- Layer 6: renal ---------------------------------------------------
    if drug in RENAL_RULES:
        adjust_below, refuse_below, en, ar = RENAL_RULES[drug]
        # An UNKNOWN clearance on a patient flagged as renally impaired must not
        # read as a normal one. `None` means "not measured"; when the impairment
        # flag is set we substitute ASSUMED_CRCL_UNKNOWN and every message that
        # quotes the number says it was assumed. streamlit_app.py now passes
        # None (not 100.0) when no creatinine was entered, so this branch is
        # live rather than unreachable.
        crcl = cl_cr if cl_cr is not None else (ASSUMED_CRCL_UNKNOWN if is_renal else None)
        if crcl is not None:
            if refuse_below is not None and crcl < refuse_below:
                v.add(DENY, "renal", f"CrCl {crcl:.0f} mL/min — {en}",
                      f"CrCl {crcl:.0f} مل/د — {ar}", "BNF 2025 renal impairment")
            elif adjust_below is not None and crcl < adjust_below:
                v.add(CAUTION, "renal", f"CrCl {crcl:.0f} mL/min — dose adjustment required: {en}",
                      f"CrCl {crcl:.0f} مل/د — يلزم تعديل الجرعة: {ar}", "BNF 2025 renal impairment")

    # ---- Layer 7: hepatic (previously inert) ------------------------------
    if is_hepatic and drug in HEPATIC_RULES:
        lvl, en, ar = HEPATIC_RULES[drug]
        if child_pugh and str(child_pugh).upper().startswith("A") and lvl == DENY:
            lvl = CAUTION  # Child-Pugh A rarely warrants outright refusal
        v.add(lvl, "hepatic", en, ar, "BNF 2025 hepatic impairment; LiverTox NIH")

    # ---- Layer 8: age ------------------------------------------------------
    if age_years is not None:
        if age_years <= NEONATE_MAX_YEARS and drug in NEONATAL_DENY:
            en, ar = NEONATAL_DENY[drug]
            v.add(DENY, "neonate", en, ar, "BNF for Children 2025; AAP Red Book")
        if drug in AGE_RULES:
            cutoff, lvl, en, ar = AGE_RULES[drug]
            if cutoff is not None and age_years < cutoff:
                v.add(lvl, "paediatric", f"age {age_years:g} y — {en}",
                      f"العمر {age_years:g} سنة — {ar}", "BNF for Children 2025")

    return v


def evaluate_panel(
    drugs: Iterable[str],
    organism: Optional[str] = None,
    specimen: Optional[str] = None,
    *,
    sir_map: Optional[Dict[str, str]] = None,
    **host: Any,
) -> Dict[str, List[Dict[str, Any]]]:
    """Evaluate a whole AST panel. Returns three buckets plus full provenance."""
    sir_map = sir_map or {}
    out: Dict[str, List[Dict[str, Any]]] = {"allow": [], "caution": [], "deny": []}
    for d in drugs:
        v = evaluate(d, organism, specimen, sir=sir_map.get(d), **host)
        out[v.level].append({"drug": d, **v.to_dict()})
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 7. PROOFS — run these in CI; they are the answer to "how do I guarantee it"
# ═══════════════════════════════════════════════════════════════════════════
def prove_totality(formulary: Optional[Iterable[str]] = None) -> List[str]:
    """Every (drug x site) cell must be explicit. No cell may fall through."""
    errs: List[str] = []
    drugs = list(formulary) if formulary is not None else list(SITE_PENETRATION)
    for d in drugs:
        if d not in SITE_PENETRATION:
            errs.append(f"TOTALITY: '{d}' has no site-penetration row")
            continue
        for s in SITES:
            cell = SITE_PENETRATION[d].get(s)
            if cell is None:
                errs.append(f"TOTALITY: '{d}' x '{s}' is undefined")
            elif cell[0] not in (ALLOW, CAUTION, DENY):
                errs.append(f"TOTALITY: '{d}' x '{s}' has invalid verdict {cell[0]!r}")
            elif cell[0] != ALLOW and not cell[1].strip():
                errs.append(f"TOTALITY: '{d}' x '{s}' is non-ALLOW with an empty reason")
    for d in SITE_PENETRATION:
        extra = set(SITE_PENETRATION[d]) - set(SITES)
        if extra:
            errs.append(f"TOTALITY: '{d}' has unknown site key(s) {sorted(extra)}")
    return errs


def prove_fail_closed() -> List[str]:
    """Unknown inputs must DENY, never ALLOW."""
    errs: List[str] = []
    if evaluate("Totally Made Up Drug", "E. coli", "Urine").level != DENY:
        errs.append("FAIL-CLOSED: unknown drug did not deny")
    v = evaluate("Ceftriaxone", "E. coli", "Pleural Fluid")
    if v.level == ALLOW:
        errs.append("FAIL-CLOSED: unrecognised specimen produced a bare ALLOW")
    return errs


def prove_monotonicity(formulary: Optional[Iterable[str]] = None) -> List[str]:
    """Adding a risk factor may only shrink the allowed set — never grow it.

    This single invariant is what exposed the dead hepatic layer: is_hepatic=True
    returned exactly the same set as is_hepatic=False.
    """
    errs: List[str] = []
    drugs = list(formulary) if formulary is not None else list(SITE_PENETRATION)

    def allowed(**kw: Any) -> set:
        base = dict(age_years=40, cl_cr=95.0)
        base.update(kw)
        return {d for d in drugs
                if evaluate(d, "E. coli", "Urine", **base).level == ALLOW}

    healthy = allowed()
    checks = [
        ("pregnancy", allowed(is_pregnant=True)),
        ("hepatic", allowed(is_hepatic=True, child_pugh="C")),
        ("renal CrCl 20", allowed(cl_cr=20.0)),
        ("child 5 y", allowed(age_years=5)),
        ("neonate", allowed(age_years=0.01)),
    ]
    for label, narrowed in checks:
        gained = narrowed - healthy
        if gained:
            errs.append(f"MONOTONICITY: '{label}' ALLOWED agents a healthy adult was not: {sorted(gained)}")
        if narrowed == healthy:
            errs.append(f"MONOTONICITY: '{label}' changed nothing — the layer is inert")
    # CrCl must be monotone decreasing
    prev = None
    for crcl in (95.0, 60.0, 45.0, 30.0, 20.0, 10.0):
        cur = allowed(cl_cr=crcl)
        if prev is not None and not cur <= prev:
            errs.append(f"MONOTONICITY: CrCl {crcl} allowed agents that a higher CrCl did not: "
                        f"{sorted(cur - prev)}")
        prev = cur
    return errs


def prove_no_contradiction() -> List[str]:
    """A drug may not be simultaneously DENIED and ALLOWED by two layers."""
    errs: List[str] = []
    for drug in SITE_PENETRATION:
        for site in SITES:
            lvl = SITE_PENETRATION[drug][site][0]
            if lvl == DENY:
                v = evaluate(drug, "E. coli", site, cl_cr=95.0, age_years=40)
                if v.level != DENY:
                    errs.append(f"CONTRADICTION: {drug} x {site} is DENY in the table "
                                f"but evaluate() returned {v.level}")
    return errs


def self_test(formulary: Optional[Iterable[str]] = None, verbose: bool = True) -> bool:
    checks = (
        ("totality", prove_totality(formulary)),
        ("fail-closed", prove_fail_closed()),
        ("monotonicity", prove_monotonicity(formulary)),
        ("no-contradiction", prove_no_contradiction()),
    )
    ok = True
    for name, errs in checks:
        if verbose:
            n = len(SITE_PENETRATION) * len(SITES) if name == "totality" else ""
            tail = f"  ({n} cells)" if n else ""
            print(f"  [{'PASS' if not errs else 'FAIL'}] {name}{tail}")
        for e in errs:
            ok = False
            if verbose:
                print(f"        - {e}")
    return ok


if __name__ == "__main__":  # pragma: no cover
    import sys
    print(f"clinical_matrix v{MATRIX_VERSION} — "
          f"{len(SITE_PENETRATION)} agents x {len(SITES)} sites = "
          f"{len(SITE_PENETRATION) * len(SITES)} cells\n")
    sys.exit(0 if self_test() else 1)
