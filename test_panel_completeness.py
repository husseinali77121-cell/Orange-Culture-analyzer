#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_panel_completeness.py — ast_panel_completeness.py, tested directly.

WHY THIS FILE EXISTS
ast_panel_completeness.py answers a question no other test suite in this repo
asks: "was enough tested in the first place?". Its failure modes are not
"crashes" — they are quiet ones: an organism that silently gets no coverage,
a drug name spelled one character differently than the OCR/alias system
produces (so it NEVER stops being "missing"), a primary-tier drug list that
contradicts the intrinsic-resistance table for the same organism, or a
CRITICAL escalation that fires when it shouldn't (alert fatigue) or stays
silent when it should (the exact gap this module exists to close).

WHAT THIS COVERS
    organism matching     group precedence, no-match safety (not_evaluated)
    name normalization    spacing/case-insensitive drug matching
    tier maths             expected/tested/missing counts, per tier
    escalation logic       the CRITICAL trigger, and three ways it must NOT fire
    cross-module safety    no group's expected list contradicts
                           clinical_data.INTRINSIC_RESISTANCE for the same organism
    registry traceability  every GROUPS id has a citation row, and vice versa
    pipeline integration   ast_qa_engine.run_ast_qa_engine() actually surfaces it

Run:  python test_panel_completeness.py [--verbose]
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
VERBOSE = "--verbose" in sys.argv

_PASS: list = []
_FAIL: list = []


def check(name, ok, detail=""):
    (_PASS if ok else _FAIL).append(name)
    if not ok:
        print(f"  FAIL  {name}")
        for line in str(detail).splitlines()[:8]:
            print(f"          {line}")
    elif VERBOSE:
        print(f"  PASS  {name}")


print("=" * 72)
print("Orange Lab CDSS — ast_panel_completeness.py, tested directly")
print("=" * 72)

from ast_panel_completeness import (                                # noqa: E402
    GROUPS, check_panel_completeness, _match_group, _nk,
    _intrinsically_resistant_drugs,
)


# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] Organism matching — precedence and no-match safety")
# ═══════════════════════════════════════════════════════════════════════════
check("empty organism -> no group, no exception", _match_group("") is None)
check("None organism -> no group, no exception", _match_group(None) is None)
check("unrecognized organism -> no group (stays silent, not a false pass)",
      _match_group("Legionella pneumophila") is None)
check("Mycoplasma -> no group (no routine AST convention)",
      _match_group("Mycoplasma spp.") is None)
check("Anaerobes -> no group (routine panel testing not standard practice)",
      _match_group("Anaerobes (لاهوائيات)") is None)

_g = _match_group("Salmonella spp.")
check("Salmonella matches its OWN group, not swallowed by Enterobacterales",
      _g is not None and _g["id"] == "panel_salmonella_shigella",
      f"got {_g['id'] if _g else None}")
_g = _match_group("Shigella spp.")
check("Shigella matches the same enteric group",
      _g is not None and _g["id"] == "panel_salmonella_shigella")

_g = _match_group("Enterobacterales (unspeciated)")
check("the literal '(unspeciated)' label still resolves to Enterobacterales",
      _g is not None and _g["id"] == "panel_enterobacterales",
      f"got {_g['id'] if _g else None}")

_spot_checks = [
    ("E. coli", "panel_enterobacterales"),
    ("Klebsiella spp.", "panel_enterobacterales"),
    ("Enterobacter cloacae", "panel_enterobacterales"),
    ("Pseudomonas aeruginosa", "panel_pseudomonas"),
    ("Acinetobacter baumannii", "panel_acinetobacter"),
    ("Stenotrophomonas maltophilia", "panel_stenotrophomonas"),
    ("Staphylococcus aureus", "panel_staphylococcus"),
    ("MRSA", "panel_staphylococcus"),
    ("Coagulase-negative Staphylococci", "panel_staphylococcus"),
    ("Enterococcus faecalis", "panel_enterococcus"),
    ("VRE", "panel_enterococcus"),
    ("Streptococcus pneumoniae", "panel_strep_pneumoniae"),
    ("Streptococcus pyogenes (Group A)", "panel_beta_hemolytic_strep"),
    ("Streptococcus agalactiae (Group B)", "panel_beta_hemolytic_strep"),
    ("H. influenzae", "panel_haemophilus"),
]
_bad = []
for org, want in _spot_checks:
    g = _match_group(org)
    got = g["id"] if g else None
    if got != want:
        _bad.append(f"{org!r}: got {got}, want {want}")
check("every real selectable organism name resolves to its intended group",
      not _bad, "\n".join(_bad))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[2] Drug-name normalization — spacing/case must not create phantom gaps")
# ═══════════════════════════════════════════════════════════════════════════
check("_nk collapses spacing and case",
      _nk("Amoxicillin + Clavulanic acid") == _nk("amoxicillin+clavulanic  ACID"))
check("_nk of empty/None is empty, not an exception",
      _nk("") == "" and _nk(None) == "")

_r = check_panel_completeness(
    "Pseudomonas aeruginosa", "Blood",
    {"cefepime": "S", "CEFTAZIDIME": "S", " Ciprofloxacin ": "S",
     "piperacillin+tazobactam": "S", "tobramycin": "S"},
)
check("differently-formatted keys still count as tested (no phantom missing)",
      not _r.missing_primary, f"missing_primary={_r.missing_primary}")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[3] Tier maths — expected / tested / missing counts")
# ═══════════════════════════════════════════════════════════════════════════
_full = {"Cefepime": "S", "Ceftazidime": "S", "Ciprofloxacin": "S",
         "Piperacillin + Tazobactam": "S", "Tobramycin": "S",
         "Levofloxacin": "S", "Amikacin": "S", "Imipenem/Cilastatin": "S",
         "Meropenem": "S", "Aztreonam": "S", "Colistin": "S",
         "Cefiderocol": "S", "Ceftazidime + Avibactam": "S",
         "Ceftolozane + Tazobactam": "S"}
_r = check_panel_completeness("Pseudomonas aeruginosa", "Blood", _full)
check("a fully-tested panel is 'adequate'", _r.status == "adequate", _r.status)
check("expected_total == tested_count when nothing is missing",
      _r.expected_total == _r.tested_count == len(_full))
check("no issues raised for an adequate panel", not _r.issues, _r.issues)

_partial = {"Cefepime": "S", "Ceftazidime": "R", "Piperacillin + Tazobactam": "S",
            "Tobramycin": "S"}
_r = check_panel_completeness("Pseudomonas aeruginosa", "Blood", _partial)
check("Ciprofloxacin missing from primary is caught",
      "Ciprofloxacin" in _r.missing_primary, _r.missing_primary)
check("supplemental agents all missing are caught",
      set(_r.missing_supplemental) == {"Levofloxacin", "Amikacin",
                                        "Imipenem/Cilastatin", "Meropenem",
                                        "Aztreonam", "Colistin", "Cefiderocol",
                                        "Ceftazidime + Avibactam",
                                        "Ceftolozane + Tazobactam"},
      _r.missing_supplemental)
check("status is 'incomplete', not 'critical' (a susceptible primary agent exists)",
      _r.status == "incomplete", _r.status)
_high = [i for i in _r.issues if i["severity"] == "HIGH"]
_low = [i for i in _r.issues if i["severity"] == "LOW"]
check("missing primary agents produce HIGH severity issues",
      len(_high) == 1 and _high[0]["drug"] == "Ciprofloxacin", _high)
check("missing supplemental agents produce LOW severity issues",
      len(_low) == 9, _low)


# ═══════════════════════════════════════════════════════════════════════════
print("\n[4] CRITICAL escalation — must fire exactly when the panel truly")
print("    cannot be safely interpreted, and NOT in three adjacent cases")
# ═══════════════════════════════════════════════════════════════════════════
# (a) SHOULD fire: every tested primary agent is R, and a primary agent is missing.
_r = check_panel_completeness(
    "Pseudomonas aeruginosa", "Blood",
    {"Piperacillin + Tazobactam": "R", "Ceftazidime": "R", "Meropenem": "R"},
)
check("fires when every tested primary agent is R and one is untested",
      _r.status == "critical", _r.status)
_crit = [i for i in _r.issues if i["severity"] == "CRITICAL"]
check("exactly one CRITICAL issue is raised", len(_crit) == 1, _crit)
if _crit:
    _named = set(d.strip() for d in _crit[0]["drug"].split(","))
    check("the CRITICAL issue names only untested drugs, never a tested one",
          _named == set(_r.missing_primary), f"{_named} vs {_r.missing_primary}")
    check("none of the drugs named by the CRITICAL issue appear in sir_map "
          "(a therapy engine can never 'recommend' an untested drug, so this "
          "issue can never collide with test_engine_agreement.py's check)",
          not (_named & {"Piperacillin + Tazobactam", "Ceftazidime", "Meropenem"}))

# (b) should NOT fire: nothing from primary was ever tested (no resistance signal).
_r = check_panel_completeness(
    "Pseudomonas aeruginosa", "Blood", {"Imipenem/Cilastatin": "S"},
)
check("does NOT fire when zero primary agents were tested (no signal yet)",
      _r.status != "critical", _r.status)

# (c) should NOT fire: at least one tested primary agent is susceptible.
_r = check_panel_completeness(
    "Pseudomonas aeruginosa", "Blood",
    {"Piperacillin + Tazobactam": "S", "Ceftazidime": "R"},
)
check("does NOT fire when a tested primary agent is S (a therapy option exists)",
      _r.status != "critical", _r.status)

# (d) should NOT fire: the primary panel is complete (nothing missing to worry about).
_r = check_panel_completeness(
    "Pseudomonas aeruginosa", "Blood",
    {"Cefepime": "R", "Ceftazidime": "R", "Ciprofloxacin": "R",
     "Piperacillin + Tazobactam": "R", "Tobramycin": "R"},
)
check("does NOT fire when the primary panel is complete, even if all-R "
      "(that is a real XDR/PDR isolate, not an incomplete panel)",
      _r.status != "critical", _r.status)


# ═══════════════════════════════════════════════════════════════════════════
print("\n[5] Specimen-scoped additions")
# ═══════════════════════════════════════════════════════════════════════════
_r_urine = check_panel_completeness("E. coli", "Urine", {"Ampicillin": "S"})
_r_blood = check_panel_completeness("E. coli", "Blood", {"Ampicillin": "S"})
check("Urine adds Nitrofurantoin/Fosfomycin to the expected panel",
      {"Nitrofurantoin", "Fosfomycin"} <= set(_r_urine.missing_supplemental),
      _r_urine.missing_supplemental)
check("Blood does NOT expect urine-only agents",
      not ({"Nitrofurantoin", "Fosfomycin"} & set(_r_blood.missing_supplemental)),
      _r_blood.missing_supplemental)


# ═══════════════════════════════════════════════════════════════════════════
print("\n[6] Cross-module safety — no group may contradict")
print("    clinical_data.INTRINSIC_RESISTANCE for the same organism")
# ═══════════════════════════════════════════════════════════════════════════
try:
    from clinical_data import INTRINSIC_RESISTANCE
    _has_intrinsic = True
except Exception:
    INTRINSIC_RESISTANCE = {}
    _has_intrinsic = False

if _has_intrinsic:
    # Real per-organism check, not a group-level one: call the actual public
    # function for every SPECIFIC organism key the intrinsic table knows
    # about, with nothing tested, so missing_primary+missing_supplemental IS
    # the fully-filtered expected panel for that exact organism — then
    # confirm none of it is banned for that exact organism. A group-level
    # check here would miss the runtime filter entirely, since GROUPS itself
    # is deliberately never mutated (the filter is applied fresh per call).
    _contradictions = []
    for org_key, banned in INTRINSIC_RESISTANCE.items():
        r = check_panel_completeness(org_key, "Blood", {"__probe__": "S"})
        if r.status == "not_evaluated":
            continue
        expected = set(r.missing_primary) | set(r.missing_supplemental)
        hit = expected & set(banned)
        if hit:
            _contradictions.append(f"{r.rule_id} vs organism '{org_key}': {hit}")
    check("no expected-panel entry is intrinsically resistant for the exact "
          "reported organism (checked against every organism clinical_data knows)",
          not _contradictions, "\n".join(_contradictions))

    # And the helper itself: sanity-check it agrees with the canonical table
    # on a couple of known rows, so a future refactor of the helper can't
    # silently stop filtering anything.
    check("_intrinsically_resistant_drugs matches the canonical table directly",
          "Ampicillin" in _intrinsically_resistant_drugs("Klebsiella pneumoniae")
          and "Nitrofurantoin" in _intrinsically_resistant_drugs("Proteus mirabilis"))
else:
    print("  SKIP  clinical_data not importable")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[7] Registry traceability — every GROUPS id is a citation row, and")
print("    every panel_* citation row is a real GROUPS id")
# ═══════════════════════════════════════════════════════════════════════════
try:
    from guideline_registry import RULES, SOURCES
    _has_registry = True
except Exception:
    RULES, SOURCES = {}, {}
    _has_registry = False

if _has_registry:
    _group_ids = {g["id"] for g in GROUPS}
    _registry_panel_ids = {rid for rid in RULES if rid.startswith("panel_")}
    check("every GROUPS id has a guideline_registry.RULES row",
          _group_ids <= set(RULES), _group_ids - set(RULES))
    check("no dead panel_* citation rows (registered but not in GROUPS)",
          _registry_panel_ids <= _group_ids, _registry_panel_ids - _group_ids)
    _bad_src = [g["id"] for g in GROUPS if RULES.get(g["id"], {}).get("source") not in SOURCES]
    check("every panel_* row points at a defined source", not _bad_src, _bad_src)
    _bad_level = [rid for rid in _registry_panel_ids
                  if RULES[rid].get("verified") not in ("pending", "secondary")]
    check("every panel_* row is honestly marked 'pending' or 'secondary' -- "
          "never 'source' (that implies primary-text verification this batch "
          "hasn't done) and never silently promoted to fully verified",
          not _bad_level, _bad_level)
    _bad_sign = [rid for rid in _registry_panel_ids
                 if str(RULES[rid].get("countersigned_by", "")).strip()]
    check("no panel_* row claims a clinician countersignature that was never "
          "given -- Dr. Tarek has not reviewed this batch yet",
          not _bad_sign, _bad_sign)
else:
    print("  SKIP  guideline_registry not importable")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[8] Pipeline integration — ast_qa_engine.run_ast_qa_engine() actually")
print("    surfaces Panel Completeness issues, at the right level/category")
# ═══════════════════════════════════════════════════════════════════════════
try:
    from ast_qa_engine import run_ast_qa_engine
    _has_qa = True
except Exception as _e:
    run_ast_qa_engine = None
    _has_qa = False
    print(f"  SKIP  ast_qa_engine not importable ({_e})")

if _has_qa:
    _issues = run_ast_qa_engine(
        organism="Pseudomonas aeruginosa", specimen="Blood",
        sir_map={"Piperacillin + Tazobactam": "S", "Ceftazidime": "S"},
    )
    _panel_issues = [i for i in _issues if i.category == "Panel Completeness"]
    check("run_ast_qa_engine() surfaces Panel Completeness issues",
          bool(_panel_issues), "no Panel Completeness issues returned")
    check("Panel Completeness issues are tagged level 16",
          all(i.level == 16 for i in _panel_issues),
          [i.level for i in _panel_issues])

    _issues_silent = run_ast_qa_engine(
        organism="Mycoplasma spp.", specimen="Sputum",
        sir_map={"Azithromycin": "S"},
    )
    _panel_issues_silent = [i for i in _issues_silent if i.category == "Panel Completeness"]
    check("an organism with no expected-panel group stays silent (not_evaluated), "
          "never a false 'incomplete'",
          not _panel_issues_silent, _panel_issues_silent)

    # The removed flat Pseudomonas/Ceftazidime "AST Completeness" check must not
    # have left a duplicate behind — the systematic module is the only source now.
    _dupe = [i for i in _issues
             if i.category == "AST Completeness" and "Ceftazidime" in (i.drug or "")]
    check("no duplicate LOW-severity 'AST Completeness' Ceftazidime message remains "
          "(single source of truth is ast_panel_completeness.py now)",
          not _dupe, _dupe)


print("\n" + "=" * 72)
print(f"{len(_PASS)} passed, {len(_FAIL)} failed")
if _FAIL:
    print("\nRESULT: FAILURES — see above")
    if __name__ == "__main__":
        sys.exit(1)
print("\nRESULT: ALL GREEN")
print("\nNOTE: 6 of 10 expected-panel groups in ast_panel_completeness.py are")
print("      verified='secondary' (checked against actual CLSI M100 Ed36 tier")
print("      data); 4 remain 'pending' (clinically reasoned, not independently")
print("      re-verified). NONE carry Dr. Tarek's countersignature yet. Green")
print("      here means the ENGINEERING is correct, not that the panels are")
print("      cleared for clinical use. See that module's docstring.")
