# © 2025 Dr / Hussein Ali — Orange Lab, 6 October City, Egypt
# Orange Culture Tool — All Rights Reserved
# Unauthorized copying or distribution is prohibited.

"""Specimen-to-organism mapping for Orange Culture Tool.

Enhancements in this revision:
- added helper accessors and validators
- expanded VRE coverage in high-yield specimens
"""

from typing import Iterable, Optional

SPECIMEN_ORGANISM_MAP = {
    "Urine": [
        "E. coli", "Klebsiella spp.", "Proteus mirabilis",
        "Enterococcus faecalis", "Staphylococcus aureus", "MRSA",
        "Pseudomonas aeruginosa", "Acinetobacter baumannii",
        "Enterobacterales (unspeciated)",
    ],
    "Blood": [
        "E. coli", "Klebsiella spp.", "Staphylococcus aureus", "MRSA",
        "Pseudomonas aeruginosa", "Acinetobacter baumannii",
        "Streptococcus pneumoniae", "Enterococcus faecalis",
        "Salmonella spp.", "Proteus mirabilis",
        "Anaerobes (لاهوائيات)", "Stenotrophomonas maltophilia",
        "Enterobacterales (unspeciated)",
    ],
    "Sputum": [
        "Streptococcus pneumoniae", "H. influenzae", "Klebsiella spp.",
        "Pseudomonas aeruginosa", "Acinetobacter baumannii", "MRSA",
        "Staphylococcus aureus", "E. coli", "Legionella pneumophila",
        "Mycoplasma spp.", "Stenotrophomonas maltophilia",
        "Enterobacterales (unspeciated)",
    ],
    "Wound Swab": [
        "Staphylococcus aureus", "MRSA", "E. coli", "Klebsiella spp.",
        "Pseudomonas aeruginosa", "Proteus mirabilis", "Acinetobacter baumannii",
        "Enterococcus faecalis", "Anaerobes (لاهوائيات)",
        "Enterobacterales (unspeciated)",
    ],
    "Pus": [
        "Staphylococcus aureus", "MRSA", "E. coli", "Klebsiella spp.",
        "Pseudomonas aeruginosa", "Acinetobacter baumannii",
        "Anaerobes (لاهوائيات)", "Enterococcus faecalis", "Proteus mirabilis",
        "Enterobacterales (unspeciated)",
    ],
    "Stool": [
        "Salmonella spp.", "Shigella spp.", "Campylobacter jejuni", "E. coli",
    ],
    "CSF": [
        "Streptococcus pneumoniae", "H. influenzae", "MRSA",
        "Staphylococcus aureus", "E. coli", "Klebsiella spp.",
        "Enterobacterales (unspeciated)",
    ],
}

for specimen_name in ("Urine", "Blood", "Wound Swab", "Pus"):
    if "VRE" not in SPECIMEN_ORGANISM_MAP.get(specimen_name, []):
        SPECIMEN_ORGANISM_MAP.setdefault(specimen_name, []).append("VRE")

# ── Chromosomal-AmpC genera (added 2026-08-01) ──────────────────────────────
# These were absent from every specimen list, so ORGANISM_PROFILE could not
# surface them in the dropdown and the OCR aliases for "serratia" /
# "enterobacter" resolved to a name the widget did not offer -- silently
# defaulting the isolate to index 0 (E. coli on Urine and Blood). They are
# ordinary nosocomial isolates at every one of these sites.
# NOT added to Stool: they are not enteric pathogens.
_AMPC_GENERA = ("Enterobacter cloacae", "Serratia marcescens",
                "Citrobacter freundii", "Morganella morganii",
                "Providencia spp.", "Hafnia alvei")
for specimen_name in ("Urine", "Blood", "Sputum", "Wound Swab", "Pus", "CSF"):
    for _org in _AMPC_GENERA:
        if _org not in SPECIMEN_ORGANISM_MAP.get(specimen_name, []):
            SPECIMEN_ORGANISM_MAP.setdefault(specimen_name, []).append(_org)

SPECIMEN_ORDER = ("Urine", "Blood", "Sputum", "Wound Swab", "Pus", "Stool", "CSF")


def get_organisms_for_specimen(specimen_name: str) -> list[str]:
    return list(SPECIMEN_ORGANISM_MAP.get(specimen_name, []))


def validate_specimen_organism_map(known_organisms: Optional[Iterable[str]] = None) -> list[str]:
    issues: list[str] = []
    organism_set = set(known_organisms or [])
    should_validate_organisms = bool(organism_set)

    for specimen_name, organisms in SPECIMEN_ORGANISM_MAP.items():
        if specimen_name not in SPECIMEN_ORDER:
            issues.append(f"Unknown specimen key -> {specimen_name}")
        if not organisms:
            issues.append(f"{specimen_name}: organism list is empty")
        for organism_name in organisms:
            if should_validate_organisms and organism_name not in organism_set:
                issues.append(f"{specimen_name}: organism not found in profile -> {organism_name}")
    return issues



__all__ = [
    "SPECIMEN_ORGANISM_MAP",
    "SPECIMEN_ORDER",
    "get_organisms_for_specimen",
    "validate_specimen_organism_map",
]
