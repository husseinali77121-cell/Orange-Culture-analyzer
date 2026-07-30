# -*- coding: utf-8 -*-
# © Dr. Hussein Ali — Orange Lab, 6 October City, Egypt
# Microbiology CDSS — All Rights Reserved
"""data/antibiotics.py — adapter over the single formulary.

WHAT THIS FILE USED TO BE
-------------------------
A second, complete 903-line copy of ABX_GUIDELINES. There was also a third,
byte-identical copy at the repository root (`antibiotics.py`) that nothing
imported. Both are gone; this file now re-exports the one table in
`abx_guidelines.py` and adds only the helpers the modular build needs on top.

WHY IT HAD TO GO
----------------
The two live copies had drifted into different generations of the same table,
and the modular build was running the older one. Measured 2026-07-30 across the
41 agents the two tables shared:

    renal_limit          15 / 41 disagreed
    renal_note           32 / 41 disagreed
    hepatic_caution       3 / 41 disagreed
    preg_status           3 / 41 disagreed
    child_safe            1 / 41 disagreed

The divergences were not cosmetic:

  * preg_status for Doxycycline and Tetracycline was "Warn" here and "Banned"
    in abx_guidelines. modules/analyzer.py bans on preg_status == "Banned" and
    has no class-based tetracycline override, so a tetracycline reached a
    pregnant patient as a CAUTION in this build. Tetracyclines are an absolute
    contraindication (fetal bone deposition and permanent dental staining,
    ACOG 2023 / BNF 2025).
  * hepatic_caution was False here for Amoxicillin-Clavulanate (the commonest
    single cause of drug-induced liver injury worldwide), Nitrofurantoin and
    TMP-SMX.
  * child_safe was False here for Fosfomycin, which is used in children.
  * 32 of 33 renally-adjusted agents carried no dose at all — only
    "تعديل الجرعة مطلوب" — and this table had ZERO renal_note_en keys, so the
    modular build had no English renal dosing whatsoever.

Every one of those was already correct in abx_guidelines.py. Porting field by
field would have fixed today's divergence and guaranteed tomorrow's; two files
holding the same clinical facts drift by construction, not by accident. So the
duplication is removed instead. test_dose_adjustment.py now fails the build if a
second ABX_GUIDELINES literal reappears anywhere in the repository.

WHAT CHANGES FOR THE MODULAR BUILD
----------------------------------
It gains the 10 agents this table lacked (Aztreonam, Clindamycin, Erythromycin,
Fusidic acid, Gatifloxacin, Minocycline, Moxifloxacin, Oxacillin, Penicillin,
Tobramycin), the corrected renal thresholds, and bilingual dose bands.

It loses the standalone "Furadantin" entry, which was a nitrofurantoin brand
masquerading as a separate drug — two formulary rows for one molecule meant an
AST panel could carry both and have the same agent counted twice.
"furadantin" and "furantoin" are now aliases on Nitrofurantoin in
abx_guidelines.py, so OCR still resolves the brand; it simply resolves it to the
right agent.

The local `_inject_cephradine()` shim is also gone: Cephradine is a first-class
entry in abx_guidelines.py, with a renal band that names a starting dose.
"""
from __future__ import annotations

import os
from typing import Dict

# ── THE formulary. One table, one place. ─────────────────────────────────────
from abx_guidelines import (  # noqa: F401  (re-exported for the modular build)
    ABX_ALIAS_INDEX,
    ABX_GUIDELINES,
    DEFAULT_SPECIMENS,
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


# ── Commercial (brand) names ─────────────────────────────────────────────────
def load_commercial_names(filepath: str = "commercial_names.txt") -> Dict[str, str]:
    """Map generic -> brand names from commercial_names.txt.

    Tries the path as given, then next to this file, then the repo root, then
    the working directory, because the modular build is launched from both the
    repo root and the ui/ directory depending on how Streamlit is invoked.
    """
    result: Dict[str, str] = {}
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        filepath,
        os.path.join(here, filepath),
        os.path.join(os.path.dirname(here), filepath),   # repo root
        os.path.join(os.getcwd(), filepath),
    ]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        generic, _, brands = line.partition("=")
                        generic, brands = generic.strip(), brands.strip()
                        if generic and brands:
                            result[generic.lower()] = brands
            if result:
                break
        except FileNotFoundError:
            continue
        except Exception:
            continue
    return result


COMMERCIAL_NAMES: Dict[str, str] = load_commercial_names()


def get_commercial_name(generic: str) -> str:
    return COMMERCIAL_NAMES.get(str(generic or "").lower(), "")


# ── Presentation + reason tables used only by the modular build ──────────────
AWARE_COLORS: Dict[str, str] = {
    "Access":  "🟢 Access",
    "Watch":   "🟡 Watch",
    "Reserve": "🔴 Reserve",
}

COMMON_MEDS = [
    "Antacids (مضادات الحموضة)",
    "Warfarin (مضادات التخثر)",
    "NSAIDs (مسكنات الألم)",
    "SSRI (أدوية الاكتئاب)",
    "Valproic acid (مضادات الصرع)",
]

ORGANISM_AVOID_CLASS_MAP = {
    "cephalosporins (كل الجيل)": ["cephalosporin"],
    "cephalosporins":            ["cephalosporin"],
    "tetracyclines":             ["tetracycline"],
    "aminoglycosides":           ["aminoglycoside"],
    "carbapenems":               ["carbapenem"],
    "beta-lactams (alone)":      ["penicillin", "cephalosporin", "carbapenem"],
    "beta-lactams":              ["penicillin", "cephalosporin", "carbapenem"],
}

RENAL_BAN_REASONS = {
    # The threshold in this text said 30 while the engine enforced 45
    # (EMA/BNF 2025), so the explanation shown to the clinician contradicted the
    # ban that had just fired. Corrected 2026-07-30, in step with
    # streamlit_app.py's copy of the same table.
    "nitrofurantoin": (
        "Nitrofurantoin يحتاج وظيفة كلى سليمة ليتركز في البول.\n"
        "عند CrCl < 45 مل/د (EMA/BNF 2025):\n"
        "- لا يصل لتركيز علاجي في البول → لا يقتل الجرثومة.\n"
        "- يتراكم في الدم → خطر سُمية رئوية وعصبية.\n"
        "السبب: الدواء يُطرح كلياً عبر الترشيح الكبيبي."
    ),
}

CHILD_BAN_REASONS = {
    "fluoroquinolone": (
        "الفلوروكينولونات قد تؤثر على غضاريف النمو في الأطفال < 18 سنة.\n"
        "تُستخدم فقط عند انعدام البدائل وبقرار متخصص."
    ),
    "tetracycline": (
        "Doxycycline والتتراسيكلينات قد تترسب في العظام والأسنان النامية.\n"
        "قد تسبب تلوينًا دائمًا للأسنان وتأثيرًا على نمو العظام.\n"
        "ممنوعة غالباً تحت 8 سنوات."
    ),
}
