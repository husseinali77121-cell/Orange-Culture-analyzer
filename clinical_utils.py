# -*- coding: utf-8 -*-
# © Dr. Hussein Ali — Orange Lab, 6 October City, Egypt
# Microbiology CDSS — All Rights Reserved
"""clinical_utils.py — the shared primitives every clinical layer needs.

WHY THIS FILE EXISTS
The August-2026 audit found nineteen defects. The clinical *content* was rarely
at fault; what failed, over and over, was one of two things:

  1. THE SAME RULE WRITTEN TWICE AND UPDATED ONCE.
     Organism-name matching lived in seven places with slightly different
     spellings of the same idea. `is_esbl_producer` had no length floor while
     the two intrinsic matchers did, so a blank organism matched the first key
     in the table and came back "Possible AmpC, confidence 75". Phenotype
     detection had the identical hole and claimed MRSA + VRE + CRE + CRAB at
     once for an isolate with no name.

  2. A FACT THAT EXISTED BUT COULD NOT REACH THE LAYER THAT NEEDED IT.
     `age_months` was known to the engine and absent from the safety gate's
     signature, so every infant arrived as `age_years=0`, tripped
     `0 <= 28/365`, and had ceftriaxone banned as a neonate — in blood, in
     urine and in CSF, through eleven months of life. The gate could not see
     the month because there was no parameter to put it in.

This module answers both. `_org_matches` and `canon_org` are the ONE matcher.
`Patient` is the ONE host record: assemble it once, pass it whole, and a new
consumer cannot silently miss a field the way a twelfth positional argument can.

IMPORT DIRECTION IS ONE-WAY: clinical_utils imports nothing from the app. Every
other module imports from here. That is what keeps it a single source rather
than a fourth copy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, Optional

__all__ = [
    "NEONATE_MAX_YEARS", "NON_INFORMATIVE_ORGANISM_TOKENS",
    "collapse_ws", "canon_org", "org_matches", "org_in",
    "resolve_age_years", "Patient",
]

# 28 days. EUCAST/AAP treat the neonatal window in DAYS, so a years-based
# comparison must carry the fraction, never `age < 1`.
NEONATE_MAX_YEARS: float = 28.0 / 365.0

# Tokens that clear a four-character floor but name no organism. "spp." is a
# substring of "klebsiella spp." and matched every key that carried it.
NON_INFORMATIVE_ORGANISM_TOKENS = frozenset({
    "spp.", "spp", "sp.", "species", "gram", "n/a", "na", "none", "nil",
    "unknown", "unspeciated", "isolate", "organism", "culture", "growth",
})

_WS = re.compile(r"\s+")

# Zero-width and directional marks. `\s` does NOT match these, so an organism
# name carrying one matched NO intrinsic row, no producer list and no phenotype
# rule — and the OCR alias lookup then fell through to index 0, which is the
# silent misidentification this audit already fixed once for Serratia.
#
# They arrive from OCR of bidirectional documents, from copy-paste out of a
# PDF, and from Word autocorrect.
#
# They are replaced with a SPACE, not deleted. Deleting them joins the words —
# "Klebsiella" + ZWSP + "pneumoniae" became "klebsiellapneumoniae" and matched
# nothing. A zero-width character between two words is almost always where a
# space or a line break used to be. The punctuation repair below then undoes
# the one case that over-splits: "E" + ZWNJ + ". coli" would otherwise become
# "e . coli".
_ZERO_WIDTH = re.compile(
    "["
    "\u200b"   # zero-width space
    "\u200c"   # zero-width non-joiner
    "\u200d"   # zero-width joiner
    "\u200e"   # left-to-right mark
    "\u200f"   # right-to-left mark
    "\u202a-\u202e"  # directional embedding / override
    "\u2066-\u2069"  # directional isolates
    "\ufeff"   # BOM / zero-width no-break space
    "\u00ad"   # soft hyphen
    "]"
)
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,])")


def collapse_ws(text: Any) -> str:
    """lower + strip + collapse internal whitespace runs to one space.

    `.strip()` cleans the ends and leaves the middle, so an OCR'd
    "Escherichia  coli" with a doubled space matched no intrinsic row and no
    producer list. Every matcher below normalises through here so they cannot
    disagree about what counts as the same name.
    """
    t = _ZERO_WIDTH.sub(" ", str(text or ""))
    t = _WS.sub(" ", t).strip().lower()
    # "e . coli" -> "e. coli": a space introduced immediately before a full stop
    # or comma is an artefact of the substitution above, never real spelling.
    return _SPACE_BEFORE_PUNCT.sub(r"\1", t)


def canon_org(name: Any, alias_map: Optional[Dict[str, str]] = None) -> str:
    """Normalised organism name, optionally mapped through a synonym table."""
    n = collapse_ws(name)
    return (alias_map or {}).get(n, n)


def org_matches(org: Any, keys: Iterable[str], *, min_len: int = 4) -> bool:
    """Two-way substring match with the guards that were missing in three places.

    Rejects the empty string, whitespace, and non-informative tokens outright,
    and only allows the REVERSE direction (`org in key`) once the name is at
    least `min_len` characters — because `"" in "escherichia coli"` is True and
    that one fact produced three separate clinical defects.
    """
    o = collapse_ws(org)
    if not o or o in NON_INFORMATIVE_ORGANISM_TOKENS:
        return False
    for k in keys:
        kk = collapse_ws(k)
        if not kk:
            continue
        if kk in o or (len(o) >= min_len and o in kk):
            return True
    return False


def org_in(name: Any, group: Iterable[str]) -> bool:
    """Exact, spelling-independent membership (no substring behaviour)."""
    t = canon_org(name)
    return any(canon_org(g) == t for g in group)


def resolve_age_years(age_years: Optional[float],
                      age_months: Optional[float] = None) -> Optional[float]:
    """Effective age in years, with MONTHS winning when it is usable.

    This is the fix for the ceftriaxone defect, hoisted out of the two places
    that had each grown their own copy of it (apply_safety_gate and
    get_combination_therapy). A months value outside 0-11 is a data error, not
    a patient: fall back to years rather than trusting it, so an unusable entry
    fails CLOSED instead of quietly widening a paediatric window.
    """
    if age_months is not None:
        try:
            m = float(age_months)
            if 0 <= m <= 11:
                return m / 12.0
        except (TypeError, ValueError):
            pass
    return age_years


@dataclass
class Patient:
    """Every host fact the clinical engines need, carried as ONE object.

    Before this existed the pipeline threaded twelve positional and keyword
    arguments through four layers, and each layer took a different subset:
    analyze_antibiotics knew `age_months`, apply_safety_gate did not,
    get_treatment_duration knew neither `is_pregnant` nor `is_hepatic`,
    generate_report took `age_months` but not `child_pugh` while
    generate_pdf_html_report took the reverse. Adding a field meant editing
    every signature and every call site, and the one time that was done with a
    text replacement it landed on a function that did not accept it and raised
    TypeError on the PDF path.

    Passing the record whole removes that whole class of error: a consumer that
    wants a new field reads it off the object, and no call site changes.

    NOT a validator. `validate()` reports problems; it does not refuse to build.
    A CDSS that will not construct a patient because the creatinine is odd is
    a CDSS that gets bypassed.
    """
    age_years: Optional[float] = None
    age_months: Optional[int] = None
    sex: str = "Male"
    weight_kg: Optional[float] = None

    is_pregnant: bool = False
    is_lactating: bool = False

    is_renal: bool = False
    cl_cr: Optional[float] = None

    is_hepatic: bool = False
    child_pugh: str = "A"

    current_meds: list = field(default_factory=list)
    host_factors: list = field(default_factory=list)
    allergies: list = field(default_factory=list)

    # ── derived ────────────────────────────────────────────────────────────
    @property
    def effective_age_years(self) -> Optional[float]:
        return resolve_age_years(self.age_years, self.age_months)

    @property
    def is_neonate(self) -> bool:
        a = self.effective_age_years
        return a is not None and a <= NEONATE_MAX_YEARS

    @property
    def is_infant(self) -> bool:
        a = self.effective_age_years
        return a is not None and a < 1.0

    @property
    def is_child(self) -> bool:
        a = self.effective_age_years
        return a is not None and a < 18.0

    def validate(self) -> list:
        """Problems worth showing the user. Never raises, never blocks."""
        out = []
        a = self.age_years
        if a is not None and not (0 <= a <= 120):
            out.append(f"العمر خارج النطاق المعقول (0–120): {a}")
        if self.age_months is not None and not (0 <= self.age_months <= 11):
            out.append(f"العمر بالشهور خارج النطاق 0–11 ({self.age_months}) — "
                       f"سيُتجاهل ويُعتمد العمر بالسنوات.")
        if self.is_pregnant and str(self.sex).lower().startswith("m"):
            out.append("حمل مُسجَّل لمريض ذكر — راجع بيانات المريض.")
        if self.is_pregnant and a is not None and not (10 <= a <= 60):
            out.append(f"حمل مُسجَّل خارج سن الإنجاب المعتاد ({a} سنة).")
        if self.cl_cr is not None and self.cl_cr < 0:
            out.append(f"CrCl سالب ({self.cl_cr}).")
        if self.is_hepatic and self.child_pugh not in ("A", "B", "C"):
            out.append(f"تصنيف Child-Pugh غير صالح: {self.child_pugh!r}")
        return out

    def as_kwargs(self) -> Dict[str, Any]:
        """Keyword form for the legacy signatures that still take loose args.

        The pipeline is being migrated to take `Patient` directly; until every
        layer has been converted this keeps ONE place that knows how the object
        maps onto the old parameter names, instead of that knowledge living at
        each call site.
        """
        return {
            "age": int(self.age_years or 0),
            "age_months": self.age_months,
            "sex": self.sex,
            "is_renal": self.is_renal,
            "cl_cr": self.cl_cr,
            "is_preg": self.is_pregnant,
            "is_hepatic": self.is_hepatic,
            "child_pugh": self.child_pugh,
            "current_meds": list(self.current_meds),
        }

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["effective_age_years"] = self.effective_age_years
        d["is_neonate"] = self.is_neonate
        return d
