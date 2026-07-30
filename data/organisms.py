# -*- coding: utf-8 -*-
# © Dr. Hussein Ali — Orange Lab, 6 October City, Egypt
# Microbiology CDSS — All Rights Reserved
"""data/organisms.py — adapter over the single organism tables.

This file used to be a second copy of ORGANISM_PROFILE and
SPECIMEN_ORGANISM_MAP. Measured 2026-07-30 it had fallen behind the canonical
tables in `organism_profile.py` and `specimen_organism_map.py`:

  * 17 organisms here against 20 there. MISSING: "Enterobacterales
    (unspeciated)" (the fall-back key the OCR path lands on when the report
    names no species), "Rickettsia spp." and "VRE".
  * 11 of the 17 shared organisms had a different profile — different
    first/second/third-line agents and different avoid lists.

A missing "VRE" key means the modular build had no vancomycin-resistant
enterococcus guidance at all, and a missing unspeciated-Enterobacterales key
means an unnamed Gram-negative fell through organism lookup entirely.

Same conclusion as data/antibiotics.py: two files holding one set of clinical
facts drift by construction. The copy is removed; this re-exports the canonical
tables. test_dose_adjustment.py fails the build if a second copy reappears.
"""
from __future__ import annotations

from organism_profile import (  # noqa: F401  (re-exported for the modular build)
    GENERIC_DRUG_CLASS_TERMS,
    ORGANISM_PROFILE,
    get_organism_profile,
    normalize_organism_key,
    validate_organism_profile,
)
from specimen_organism_map import (  # noqa: F401
    SPECIMEN_ORDER,
    SPECIMEN_ORGANISM_MAP,
    get_organisms_for_specimen,
    validate_specimen_organism_map,
)

__all__ = [
    "ORGANISM_PROFILE", "SPECIMEN_ORGANISM_MAP", "SPECIMEN_ORDER",
    "BACTERIA_TYPES", "SPECIMEN_TYPES",
    "GENERIC_DRUG_CLASS_TERMS", "normalize_organism_key",
    "get_organism_profile", "validate_organism_profile",
    "get_organisms_for_specimen", "validate_specimen_organism_map",
]

# Derived, not restated. SPECIMEN_TYPES was a hardcoded list here while the
# canonical order lived in specimen_organism_map.SPECIMEN_ORDER, so adding a
# specimen in one place left the other behind.
BACTERIA_TYPES = list(ORGANISM_PROFILE.keys())
SPECIMEN_TYPES = list(SPECIMEN_ORDER)
