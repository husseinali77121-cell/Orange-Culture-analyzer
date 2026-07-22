# clinical_data.py
# © 2025 Dr / Hussein Ali -- Orange Lab, 6 October City, Egypt
# Microbiology CDSS -- All Rights Reserved
#
# SINGLE SOURCE OF TRUTH for intrinsic resistance.
#
# Why this file exists
# --------------------
# The table below used to live inside streamlit_app.py, while ast_qa_engine.py
# tried to `from clinical_data import INTRINSIC_RESISTANCE` -- a module that did
# not exist in this repository. The import silently fell back to {} , so the QA
# engine's Level-1 intrinsic-resistance check was DEAD for every Gram-negative
# and only MRSA / Mycoplasma were ever evaluated. Extracting the table here makes
# that import resolve, so the clinical engine and the QA engine now read the same
# rows and can no longer drift apart.
#
# Consumers:
#   * streamlit_app.py   -> Avoid-routing + intrinsic stripping before MDR counting
#   * ast_qa_engine.py   -> Level 1 "this S contradicts intrinsic resistance"
#   * test_intrinsic_invariant.py -> guards the two against divergence
#
# Editing rule: this file holds DATA ONLY. No imports, no Streamlit, no logic --
# so it stays importable from a bare test runner with no dependencies.
#
# References: EUCAST Intrinsic Resistance and Unusual Phenotypes v3.3 (2021-10-18)
#             EUCAST Clinical Breakpoint Tables v16.0 (valid from 2026-01-01)
#             CLSI M100 Ed36 (2026) Appendix B

from __future__ import annotations

from typing import Dict, List

# ============================================================================
#  INTRINSIC_RESISTANCE — CANONICAL SINGLE SOURCE OF TRUTH
#  EUCAST Intrinsic Resistance & Unusual Phenotypes Tables v3.3
#  Keys are substring-matched (org_key in org_l OR org_l in org_key), so both
#  binomial and abbreviated organism forms are covered. Drug strings include
#  common formulary VARIANTS (e.g. "Cefuroxime" AND "Cefuroxime sodium") so
#  exact-string matching in _remove_intrinsic_resistance / is_intrinsically_
#  avoided never silently misses. Extra variants that match no real drug are
#  harmless. ONLY intrinsically-INACTIVE agents are listed — anti-pseudomonal
#  β-lactams (Ceftazidime/Cefepime/Cefoperazone/Pip-Tazo/Aztreonam/carbapenems)
#  are deliberately EXCLUDED and judged on their own AST result.
# ============================================================================
INTRINSIC_RESISTANCE = {
    # ── Enterobacterales — wild-type susceptible ────────────────────────────
    "escherichia coli": ["Oxacillin", "Penicillin"],
    "e. coli":          ["Oxacillin", "Penicillin"],

    # Klebsiella: chromosomal penicillinase (SHV/LEN/OKP) → aminopenicillins.
    # Amox-clav / cephalosporins remain active (NOT intrinsic).
    "klebsiella pneumoniae": ["Ampicillin", "Amoxicillin", "Ticarcillin", "Oxacillin", "Penicillin"],
    "klebsiella oxytoca":    ["Ampicillin", "Amoxicillin", "Ticarcillin", "Oxacillin", "Penicillin"],
    "klebsiella spp.":       ["Ampicillin", "Amoxicillin", "Ticarcillin", "Oxacillin", "Penicillin"],

    # Proteus/Providencia/Morganella tribe → tetracyclines, nitrofurantoin,
    # polymyxins are ALL intrinsically inactive.
    "proteus mirabilis": ["Tetracycline", "Doxycycline", "Minocycline", "Tigecycline",
                          "Nitrofurantoin", "Colistin", "Polymyxin B", "Oxacillin", "Penicillin"],
    "proteus spp.":      ["Tetracycline", "Doxycycline", "Minocycline", "Tigecycline",
                          "Nitrofurantoin", "Colistin", "Polymyxin B", "Oxacillin", "Penicillin"],
    # P. vulgaris/penneri add inducible β-lactamase → aminopenicillins + 1st/2nd ceph
    "proteus vulgaris":  ["Tetracycline", "Doxycycline", "Minocycline", "Tigecycline",
                          "Nitrofurantoin", "Colistin", "Polymyxin B",
                          "Ampicillin", "Amoxicillin",
                          "Amoxicillin + Clavulanic acid",
                          "Ampicillin/Sulbactam", "Ampicillin + Sulbactam",
                          "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin",
                          "Cefaclor", "Cefuroxime", "Cefuroxime sodium",
                          "Cefoxitin", "Oxacillin", "Penicillin"],

    # Morganella: chromosomal AmpC + tribe intrinsics
    "morganella morganii": ["Ampicillin", "Amoxicillin", "Amoxicillin + Clavulanic acid",
                            "Ampicillin/Sulbactam", "Ampicillin + Sulbactam",
                            "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin",
                            "Cefuroxime", "Cefuroxime sodium", "Cefaclor", "Cefoxitin",
                            "Tetracycline", "Doxycycline", "Minocycline", "Tigecycline",
                            "Nitrofurantoin", "Colistin", "Polymyxin B", "Oxacillin", "Penicillin"],

    # Providencia: AmpC + tribe + intrinsic aminoglycoside (gentamicin/tobramycin)
    "providencia spp.": ["Ampicillin", "Amoxicillin", "Amoxicillin + Clavulanic acid",
                         "Ampicillin/Sulbactam", "Ampicillin + Sulbactam",
                         "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin",
                         "Cefuroxime", "Cefuroxime sodium", "Cefaclor", "Cefoxitin",
                         "Tetracycline", "Doxycycline", "Minocycline", "Tigecycline",
                         "Nitrofurantoin", "Colistin", "Polymyxin B",
                         "Gentamicin", "Tobramycin", "Oxacillin", "Penicillin"],

    # Serratia: chromosomal AmpC + intrinsic polymyxin/nitrofurantoin
    # EUCAST v3.3 Table 2 fn.5 -- "S. marcescens is intrinsically resistant to
    # tetracycline and doxycycline but not to minocycline or tigecycline."
    # Tigecycline was previously listed here (wrongly banning an active agent for
    # MDR Serratia) while tetracycline and doxycycline were absent entirely.
    "serratia marcescens": ["Tetracycline", "Doxycycline",
                            "Ampicillin", "Amoxicillin", "Amoxicillin + Clavulanic acid",
                            "Ampicillin/Sulbactam", "Ampicillin + Sulbactam",
                            "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin",
                            "Cefuroxime", "Cefuroxime sodium", "Cefaclor", "Cefoxitin",
                            "Colistin", "Polymyxin B", "Nitrofurantoin", "Oxacillin", "Penicillin"],
    "serratia spp.":       ["Tetracycline", "Doxycycline",
                            "Ampicillin", "Amoxicillin", "Amoxicillin + Clavulanic acid",
                            "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin",
                          "Cefuroxime", "Cefuroxime sodium",
                            "Cefoxitin", "Colistin", "Polymyxin B", "Nitrofurantoin", "Oxacillin", "Penicillin"],

    # Enterobacter / Hafnia: chromosomal inducible AmpC
    "enterobacter cloacae":  ["Ampicillin", "Amoxicillin", "Amoxicillin + Clavulanic acid",
                             "Ampicillin/Sulbactam", "Ampicillin + Sulbactam",
                             "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin",
                             "Cefuroxime", "Cefuroxime sodium", "Cefaclor", "Cefoxitin", "Oxacillin", "Penicillin"],
    "enterobacter aerogenes":["Ampicillin", "Amoxicillin", "Amoxicillin + Clavulanic acid",
                             "Ampicillin/Sulbactam", "Ampicillin + Sulbactam",
                             "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin",
                             "Cefuroxime", "Cefuroxime sodium", "Cefaclor", "Cefoxitin", "Oxacillin", "Penicillin"],
    "enterobacter spp.":     ["Ampicillin", "Amoxicillin", "Amoxicillin + Clavulanic acid",
                             "Ampicillin/Sulbactam", "Ampicillin + Sulbactam",
                             "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin",
                             "Cefuroxime", "Cefuroxime sodium", "Cefaclor", "Cefoxitin", "Oxacillin", "Penicillin"],
    "hafnia alvei":          ["Ampicillin", "Amoxicillin", "Amoxicillin + Clavulanic acid",
                             "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin",
                          "Cefuroxime", "Cefuroxime sodium",
                             "Cefoxitin", "Oxacillin", "Penicillin"],

    # Citrobacter freundii = AmpC; C. koseri = penicillinase only
    "citrobacter freundii":  ["Ampicillin", "Amoxicillin", "Amoxicillin + Clavulanic acid",
                             "Ampicillin/Sulbactam", "Ampicillin + Sulbactam",
                             "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin",
                             "Cefuroxime", "Cefuroxime sodium", "Cefaclor", "Cefoxitin", "Oxacillin", "Penicillin"],
    "citrobacter koseri":    ["Ampicillin", "Amoxicillin", "Ticarcillin", "Oxacillin", "Penicillin"],
    "citrobacter spp.":      ["Ampicillin", "Amoxicillin", "Amoxicillin + Clavulanic acid", "Oxacillin", "Penicillin"],

    # Salmonella / Shigella: 1st/2nd-gen cephalosporins & aminoglycosides may
    # test S in vitro but are CLINICALLY INEFFECTIVE for invasive infection
    # (EUCAST/CLSI "do not report S"). Routed to Avoid here.
    "salmonella": ["Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin", "Cefaclor",
                   "Cefuroxime", "Cefuroxime sodium",
                   "Gentamicin", "Amikacin", "Tobramycin", "Nitrofurantoin", "Oxacillin", "Penicillin"],
    "shigella":   ["Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin", "Cefaclor",
                   "Cefuroxime", "Cefuroxime sodium",
                   "Gentamicin", "Amikacin", "Tobramycin", "Nitrofurantoin", "Oxacillin", "Penicillin"],

    # ── Non-fermenters ──────────────────────────────────────────────────────
    # Pseudomonas aeruginosa — ONLY Ceftazidime/Cefepime/Cefoperazone/Pip-Tazo/
    # Aztreonam/anti-pseudomonal carbapenems/FQs/aminoglycosides/colistin work.
    "pseudomonas aeruginosa": [
        "Ampicillin", "Amoxicillin", "Amoxicillin + Clavulanic acid",
        "Ampicillin/Sulbactam", "Ampicillin + Sulbactam",
        "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin", "Cefaclor",
        "Cefuroxime", "Cefuroxime sodium", "Cefuroxime axetil", "Cefoxitin",
        "Cefotaxime", "Ceftriaxone", "Cefixime", "Cefpodoxime", "Ceftibuten",
        "Ertapenem",
        "Tetracycline", "Doxycycline", "Minocycline", "Tigecycline",
        "Chloramphenicol", "Trimethoprim", "Trimethoprim/Sulfamethoxazole",
        "Nitrofurantoin",
        "Azithromycin", "Erythromycin", "Clarithromycin", "Oxacillin", "Penicillin",
    ],

    # Acinetobacter baumannii — NOTE: Ampicillin/Sulbactam is ACTIVE (excluded);
    # tetracyclines (doxy/minocycline) can be active (excluded).
    "acinetobacter baumannii": [
        "Ampicillin", "Amoxicillin", "Amoxicillin + Clavulanic acid",
        "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin", "Cefaclor",
        "Cefuroxime", "Cefuroxime sodium", "Cefoxitin",
        "Cefotaxime", "Ceftriaxone", "Ertapenem", "Aztreonam",
        "Trimethoprim", "Fosfomycin", "Nitrofurantoin", "Chloramphenicol", "Oxacillin", "Penicillin",
    ],

    # Stenotrophomonas maltophilia — L1 MBL (all carbapenems) + aminoglycosides.
    # Active (excluded): TMP-SMX, Levofloxacin, Minocycline, Tigecycline.
    "stenotrophomonas maltophilia": [
        "Imipenem/Cilastatin", "Meropenem", "Ertapenem",
        "Gentamicin", "Amikacin", "Tobramycin",
        "Ampicillin", "Amoxicillin", "Amoxicillin + Clavulanic acid",
        "Ampicillin/Sulbactam", "Ampicillin + Sulbactam",
        "Piperacillin", "Piperacillin + Tazobactam",
        "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin", "Cefuroxime", "Cefoxitin", "Cefuroxime sodium",
        "Cefaclor", "Cefotaxime", "Ceftriaxone", "Ceftazidime", "Cefepime",
        "Cefoperazone", "Aztreonam",
        "Ciprofloxacin", "Norfloxacin", "Ofloxacin",
        "Fosfomycin", "Nitrofurantoin", "Oxacillin", "Penicillin",
    ],

    # ── Gram-positives ──────────────────────────────────────────────────────
    # Enterococcus — ALL cephalosporins + low-level aminoglycoside (mono) +
    # clindamycin + TMP-SMX (in-vivo ineffective) + aztreonam. E. faecalis is
    # ampicillin-SUSCEPTIBLE (ampicillin deliberately excluded).
    "enterococcus faecalis": [
        "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin", "Cefuroxime", "Cefuroxime sodium",
        "Cefaclor", "Cefixime", "Ceftriaxone", "Cefotaxime", "Ceftazidime",
        "Cefepime", "Cefoperazone", "Cefoperazone + Sulbactam", "Cefoxitin",
        "Gentamicin", "Amikacin", "Tobramycin",
        "Clindamycin", "Trimethoprim/Sulfamethoxazole", "Aztreonam",
    ],
    "enterococcus faecium": [
        "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin", "Cefuroxime", "Cefuroxime sodium",
        "Cefaclor", "Cefixime", "Ceftriaxone", "Cefotaxime", "Ceftazidime",
        "Cefepime", "Cefoperazone", "Cefoperazone + Sulbactam", "Cefoxitin",
        "Gentamicin", "Amikacin", "Tobramycin",
        "Clindamycin", "Trimethoprim/Sulfamethoxazole", "Aztreonam",
    ],
    "enterococcus spp.": [
        "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin", "Cefuroxime", "Cefuroxime sodium",
        "Cefaclor", "Cefixime", "Ceftriaxone", "Cefotaxime", "Ceftazidime",
        "Cefepime", "Cefoperazone", "Cefoperazone + Sulbactam", "Cefoxitin",
        "Gentamicin", "Amikacin", "Tobramycin",
        "Clindamycin", "Trimethoprim/Sulfamethoxazole", "Aztreonam",
    ],
    "vre": [
        "Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin", "Cefuroxime", "Cefuroxime sodium",
        "Cefaclor", "Cefixime", "Ceftriaxone", "Cefotaxime", "Ceftazidime",
        "Cefepime", "Cefoperazone", "Cefoperazone + Sulbactam", "Cefoxitin",
        "Gentamicin", "Amikacin", "Tobramycin",
        "Clindamycin", "Trimethoprim/Sulfamethoxazole", "Aztreonam",
        "Vancomycin",
    ],

    # Staphylococcus — Aztreonam + polymyxins intrinsic. (MRSA β-lactam failure
    # is handled by the mecA/Oxacillin-Cefoxitin logic, NOT this table.)
    "staphylococcus aureus": ["Aztreonam", "Colistin", "Polymyxin B"],
    "staphylococcus":        ["Aztreonam", "Colistin", "Polymyxin B"],

    # Streptococcus — low-level aminoglycoside (mono, synergy-only) + aztreonam
    # + polymyxins + fusidic acid.
    "streptococcus pneumoniae": ["Gentamicin", "Amikacin", "Tobramycin",
                                 "Aztreonam", "Colistin", "Polymyxin B", "Fusidic acid"],
    "streptococcus pyogenes":   ["Gentamicin", "Amikacin", "Tobramycin",
                                 "Aztreonam", "Colistin", "Polymyxin B", "Fusidic acid"],
    "streptococcus agalactiae": ["Gentamicin", "Amikacin", "Tobramycin",
                                 "Aztreonam", "Colistin", "Polymyxin B", "Fusidic acid"],

    # Listeria monocytogenes — ALL cephalosporins intrinsically inactive.
    "listeria monocytogenes": ["Cephalexin", "Cefadroxil", "Cephradine", "Cefazolin",
                               "Cefuroxime", "Cefuroxime sodium", "Cefaclor",
                               "Cefotaxime", "Ceftriaxone", "Ceftazidime", "Cefepime",
                               "Cefoperazone", "Cefoperazone + Sulbactam",
                               "Cefoxitin", "Aztreonam", "Fosfomycin"],
}
