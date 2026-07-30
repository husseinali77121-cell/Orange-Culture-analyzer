# -*- coding: utf-8 -*-
# © Dr. Hussein Ali — Orange Lab, 6 October City, Egypt
# Microbiology CDSS — All Rights Reserved
"""antibiotics.py — legacy import path. Contains no data of its own.

This file used to hold a complete 893-line copy of ABX_GUIDELINES, byte-identical
to data/antibiotics.py apart from where `import re` sat. That made THREE copies of
the formulary in one repository, and the two that were actually imported had
drifted into different generations of the same table — 15 of 41 shared agents had
a different renal_limit, and preg_status for Doxycycline and Tetracycline said
"Warn" in one and "Banned" in the other. Tetracyclines are an absolute
contraindication in pregnancy, so that divergence had a patient on the wrong side
of it.

Deleting the file outright is still the tidiest end state. It is kept as a
redirect because a zip cannot express a deletion and this repository is deployed
by extracting archives, so a file that must be removed by hand tends to survive.
A redirect cannot drift: there is nothing here to drift.

Everything below re-exports from data/antibiotics.py, which in turn re-exports the
one formulary in abx_guidelines.py. If you ever want this file gone, confirm
nothing imports it and delete it — no code in this repository does:

    grep -rn "import antibiotics" --include=*.py .   # expect no hits
    git rm antibiotics.py
"""
from __future__ import annotations

from data.antibiotics import (  # noqa: F401
    ABX_ALIAS_INDEX,
    ABX_GUIDELINES,
    AWARE_COLORS,
    CHILD_BAN_REASONS,
    COMMERCIAL_NAMES,
    COMMON_MEDS,
    DEFAULT_SPECIMENS,
    ORGANISM_AVOID_CLASS_MAP,
    RENAL_BAN_REASONS,
    get_commercial_name,
    load_commercial_names,
    normalize_abx_key,
    validate_abx_guidelines,
)

__all__ = [
    "ABX_GUIDELINES", "ABX_ALIAS_INDEX", "normalize_abx_key",
    "DEFAULT_SPECIMENS", "validate_abx_guidelines",
    "AWARE_COLORS", "COMMERCIAL_NAMES", "COMMON_MEDS",
    "load_commercial_names", "get_commercial_name",
    "ORGANISM_AVOID_CLASS_MAP", "RENAL_BAN_REASONS", "CHILD_BAN_REASONS",
]
