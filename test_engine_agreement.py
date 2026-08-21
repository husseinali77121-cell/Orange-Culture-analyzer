#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_engine_agreement.py — regression proofs for the August-2026 audit.

Every existing suite proves the CODE matches its TABLES. None of them asks
whether two engines looking at the same isolate reach the same verdict, or
whether a table row that exists is actually REACHABLE. This file guards that
second question, which is where every defect in the August 2026 audit lived:

  * a rule written in one matcher and forgotten in the sibling matcher
  * a taxonomy row that exists but is inherited by nobody
  * a QC engine that says "biologically impossible" while the recommendation
    engine on the same screen says "recommended"
  * a fact (Intermediate) overwritten by a later, unrelated warning

Run:  python test_engine_agreement.py
      python test_engine_agreement.py --verbose

Files needed alongside: streamlit_app.py, abx_guidelines.py, organism_profile.py,
specimen_organism_map.py, clinical_data.py, clinical_matrix.py, safety_gate.py,
ast_qa_engine.py
"""
from __future__ import annotations

import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "streamlit_app.py")
VERBOSE = "--verbose" in sys.argv

if HERE not in sys.path:
    sys.path.insert(0, HERE)

_PASS: list[str] = []
_FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (_PASS if ok else _FAIL).append(name)
    if not ok:
        print(f"  FAIL  {name}")
        if detail:
            for line in str(detail).splitlines()[:10]:
                print(f"          {line}")
    elif VERBOSE:
        print(f"  PASS  {name}")


# ═══════════════════════════════════════════════════════════════════════════
# Load the monolith's decision logic without a Streamlit runtime
# ═══════════════════════════════════════════════════════════════════════════
def _extract(path: str, names: list[str]) -> tuple[dict, list, list]:
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    seg, order = {}, []
    for n in tree.body:
        nm = getattr(n, "name", None)
        if nm is None and isinstance(n, (ast.Assign, ast.AnnAssign)):
            tg = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in tg:
                if isinstance(t, ast.Name):
                    nm = t.id
        if nm in names and nm not in seg:
            seg[nm] = "".join(lines[n.lineno - 1:n.end_lineno])
            order.append(nm)
    return seg, order, [w for w in names if w not in seg]


_WANT = [
    "SPECIMEN_TYPES", "BACTERIA_TYPES", "ORGANISM_AVOID_CLASS_MAP",
    "RENAL_BAN_REASONS", "CHILD_BAN_REASONS", "_SPECIMEN_CATEGORY_RULES",
    "classify_specimen", "is_intrinsically_avoided", "build_banned_item",
    
    "_MED_CANON", "_canon_med",
    "ASSUMED_CRCL_UNKNOWN", "resolve_crcl", "crcl_label", "get_renal_severity",
    "_PREG_ALIASES", "preg_status_of", "_ACQUIRED_NOT_INTRINSIC",
    "MDR_CATEGORIES_STAPH", "MDR_CATEGORIES_ENTEROCOCCUS",
    "MDR_CATEGORIES_STREP", "MDR_NOT_APPLICABLE", "MDR_OUTSIDE_MAGIORAKOS",
    "NEONATAL_RESTRICTIONS",
    "ESBL_PRODUCERS", "AMPC_PRODUCERS", "ESBL_MARKERS", "CARBAPENEMS",
    "_ORG_NON_INFORMATIVE", "_org_matches", "is_esbl_producer", "predict_esbl",
    "MDR_CATEGORIES",
    "MDR_CATEGORIES_GRAM_NEG", "MDR_CATEGORIES_GRAM_POS",
    "GRAM_POSITIVE_ORGANISMS", "_remove_intrinsic_resistance", "classify_mdr",
    "MDR_INFO", "HEPATIC_DOSING", "analyze_antibiotics", "_hide_urine_only",
    "ORGANISM_OCR_ALIASES",
    "_re_ws_collapse", "PHENOTYPE_RULES", "detect_resistance_phenotypes",
    "COMBINATION_THERAPY", "_COMBO_HOST_FLAGS", "get_combination_therapy",
]

if not os.path.exists(APP):
    print(f"ENVIRONMENT INCOMPLETE — {APP} not found.")
    if __name__ == "__main__":
        sys.exit(2)

from abx_guidelines import ABX_GUIDELINES as G                      # noqa: E402
from organism_profile import ORGANISM_PROFILE as OP                 # noqa: E402
from specimen_organism_map import (                                 # noqa: E402
    SPECIMEN_ORDER, get_organisms_for_specimen,
)

_seg, _order, _missing = _extract(APP, _WANT)
# 2026-08-03: the S/I/R vocabulary moved to ocr_parsing.py. Seed it from
# the real module instead of slicing it out of the monolith — an
# importable module is the whole point of having extracted it.
from ocr_parsing import (normalize_sir_value as _nsv,
                         normalize_sir_map as _nsm,
                         _SIR_ALIASES as _sal)
NS: dict = {
    "normalize_sir_value": _nsv, "normalize_sir_map": _nsm, "_SIR_ALIASES": _sal,
    "__builtins__": __builtins__,
    "Dict": dict, "List": list, "Any": object, "Tuple": tuple, "Optional": object,
    "ABX_GUIDELINES": G, "ORGANISM_PROFILE": OP,
    "SPECIMEN_ORDER": SPECIMEN_ORDER,
    "get_organisms_for_specimen": get_organisms_for_specimen,
}
import re as _re                                                     # noqa: E402
NS["re"] = _re
try:
    from clinical_data import INTRINSIC_RESISTANCE
    NS["INTRINSIC_RESISTANCE"] = INTRINSIC_RESISTANCE
except Exception:
    INTRINSIC_RESISTANCE = {}
    NS["INTRINSIC_RESISTANCE"] = {}
try:
    from abx_guidelines import ABX_ALIAS_INDEX, normalize_abx_key
    NS["ABX_ALIAS_INDEX"] = ABX_ALIAS_INDEX
    NS["normalize_abx_key"] = normalize_abx_key
except Exception:
    pass

for _nm in _order:
    exec(compile(_seg[_nm], f"<{_nm}>", "exec"), NS)

analyze = NS["analyze_antibiotics"]
predict_esbl = NS["predict_esbl"]
is_esbl_producer = NS["is_esbl_producer"]
OCR_ALIASES = NS.get("ORGANISM_OCR_ALIASES", {})
detect_phenotypes = NS["detect_resistance_phenotypes"]
ORGS = list(OP)
SPECS = list(SPECIMEN_ORDER)

try:
    from safety_gate import apply_safety_gate
    GATE = True
except Exception:
    GATE = False

try:
    from ast_qa_engine import run_ast_qa_engine
    QA = True
except Exception:
    QA = False


def buckets(org, spec, sir, *, age=40, sex="Male", renal=False, crcl=None,
            preg=False, hep=False, cp="A", gate=True):
    """Run the FULL production pipeline: engine + terminal safety gate."""
    drugs = list(sir)
    a, w, b, p, _i = analyze(drugs, org, spec, age, sex, renal, crcl, preg, hep,
                             [], sir, cp)
    if gate and GATE:
        a, w, b, _r = apply_safety_gate(
            a, w, b, organism=org, specimen=spec, sir_map=sir, age_years=age,
            is_pregnant=preg, cl_cr=crcl, is_renal=renal, is_hepatic=hep,
            child_pugh=cp)
    nm = lambda L: {x.get("name") for x in L}
    return nm(a), nm(w), nm(b)


print("=" * 72)
print("Orange Lab CDSS — engine agreement & table reachability")
print(f"  {len(G)} agents · {len(ORGS)} organisms · {len(SPECS)} specimens")
print("=" * 72)
if _missing:
    print(f"\n  WARNING: could not extract {_missing} from streamlit_app.py")
if not GATE:
    print("  WARNING: safety_gate.py did not import — gate checks are degraded")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] ESBL lockdown must cover EVERY oxyimino beta-lactam")
print("    DEFECT: _is_penicillin_or_ceph() matched on the tokens penicillin/")
print("    cephalosporin/cillin/cef/ceph. Aztreonam's class is 'Monobactam',")
print("    so it matched none of them and a confirmed-ESBL Klebsiella")
print("    bacteraemia listed Aztreonam as RECOMMENDED — the one agent the")
print("    function's own docstring names as needing suppression.")
# ═══════════════════════════════════════════════════════════════════════════
_OXYIMINO = {"Ceftriaxone", "Cefotaxime", "Ceftazidime", "Cefepime", "Aztreonam",
             "Cefixime", "Cefoperazone", "Cefpodoxime"}
_esbl_leaks = []
for org in [o for o in ORGS if is_esbl_producer(o)]:
    for spec in ("Blood", "CSF", "Sputum"):
        sir = {"Ceftriaxone": "R", "Cefotaxime": "R", "Ceftazidime": "R",
               "Meropenem": "S", "Amikacin": "S"}
        sir.update({d: "S" for d in _OXYIMINO
                    if d in G and d not in sir})
        A, W, B = buckets(org, spec, sir)
        leak = (A & _OXYIMINO)
        if leak:
            _esbl_leaks.append(f"{org}/{spec}: RECOMMENDED {sorted(leak)}")
check("no oxyimino beta-lactam is RECOMMENDED on a confirmed-ESBL isolate",
      not _esbl_leaks, "\n".join(_esbl_leaks[:8]))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[2] Taxonomy inheritance — a genus-level intrinsic row must reach")
print("    its species. DEFECT: INTRINSIC_RESISTANCE['enterobacterales'] lists")
print("    Vancomycin/Linezolid/Clindamycin/macrolides, but the matcher is")
print("    literal substring, so only the string 'Enterobacterales")
print("    (unspeciated)' inherited it. Vancomycin and Linezolid reported S")
print("    were RECOMMENDED for E. coli, Klebsiella, Proteus and Salmonella.")
# ═══════════════════════════════════════════════════════════════════════════
_GP_ONLY = {"Vancomycin", "Linezolid", "Teicoplanin", "Daptomycin", "Fusidic acid"}
_GN_ONLY = {"Colistin", "Polymyxin B", "Aztreonam"}

# Explicit, not a substring heuristic. "Enterobacterales" and "Enterobacter"
# both contain "entero", so a name-fragment test classified two Gram-negative
# genera as enterococci. Organisms that are neither classical Gram-positive nor
# classical Gram-negative -- the atypicals, and "Anaerobes" which is a mixed
# bag containing both -- are excluded from this check entirely rather than
# forced into one side of a dichotomy they do not belong to.
# EXHAUSTIVE, not a sample. Every Gram-positive organism the dropdown offers
# must appear here, because the check below is the one that catches "organism
# added to ORGANISM_PROFILE, forgotten in clinical_data" — which happened five
# times in this audit, most recently when Coagulase-negative Staphylococci
# matched NO intrinsic row (the staph keys are singular, "staphylococcus", and
# "coagulase-negative staphylococcI" is plural) and AZTREONAM came back
# recommended for a Gram-positive isolate.
_GRAM_POS_ORGS = {"Staphylococcus aureus", "MRSA", "Enterococcus faecalis",
                  "Enterococcus faecium", "Streptococcus pneumoniae", "VRE",
                  "Streptococcus pyogenes (Group A)",
                  "Streptococcus agalactiae (Group B)",
                  "Listeria monocytogenes",
                  "Coagulase-negative Staphylococci"}
# Same requirement in the other direction.
_GRAM_NEG_ORGS = {"E. coli", "Klebsiella spp.", "Pseudomonas aeruginosa",
                  "Acinetobacter baumannii", "Proteus mirabilis",
                  "Salmonella spp.", "Shigella spp.", "Campylobacter jejuni",
                  "Stenotrophomonas maltophilia", "H. influenzae",
                  "Enterobacterales (unspeciated)", "Enterobacter cloacae",
                  "Serratia marcescens", "Citrobacter freundii",
                  "Morganella morganii", "Providencia spp.", "Hafnia alvei"}

_gram_leaks = []
for org in ORGS:
    if org in _GRAM_NEG_ORGS:
        banned_set = _GP_ONLY
    elif org in _GRAM_POS_ORGS:
        banned_set = _GN_ONLY
    else:
        continue          # atypical / mixed — not a Gram dichotomy
    avail = {d: "S" for d in banned_set if d in G}
    if not avail:
        continue
    avail["Meropenem"] = "S"
    A, W, B = buckets(org, "Blood", avail)
    leak = (A | W) & banned_set
    if leak:
        _gram_leaks.append(f"{org}: {sorted(leak)} reached allowed/caution")
check("an agent with no activity against this Gram class is never offered",
      not _gram_leaks, "\n".join(_gram_leaks[:12]))

# The two sets above are only a guard if they stay complete. Anything the
# dropdown offers that is in NEITHER set escapes the spectrum check entirely —
# which is exactly how a new organism slips through.
_ATYPICAL = {"Anaerobes (لاهوائيات)", "Mycoplasma spp.", "Legionella pneumophila",
             "Enterobacterales (unspeciated)"}
_unclassified = [o for o in ORGS
                 if o not in _GRAM_POS_ORGS and o not in _GRAM_NEG_ORGS
                 and o not in _ATYPICAL]
check("every selectable organism is classified for the spectrum check",
      not _unclassified,
      f"unclassified: {_unclassified}\n"
      "Add each to _GRAM_POS_ORGS, _GRAM_NEG_ORGS or _ATYPICAL — an organism in "
      "none of them is never spectrum-checked.")



# ═══════════════════════════════════════════════════════════════════════════
print("\n[3] Engine agreement — the QC engine and the therapy engine must not")
print("    contradict each other. DEFECT: run_ast_qa_engine() printed")
print("    '[CRITICAL] biologically impossible … Do not use for clinical")
print("    decisions' while the neighbouring column listed the same agent")
print("    under RECOMMENDED. QC output was display-only.")
# ═══════════════════════════════════════════════════════════════════════════
if QA:
    _disagree = []
    _probe = [
        ("E. coli", {"Vancomycin": "S", "Linezolid": "S", "Meropenem": "S"}),
        ("Klebsiella spp.", {"Vancomycin": "S", "Meropenem": "S"}),
        ("Proteus mirabilis", {"Vancomycin": "S", "Meropenem": "S"}),
        ("Enterococcus faecalis", {"Colistin": "S", "Linezolid": "S"}),
        ("Stenotrophomonas maltophilia", {"Vancomycin": "S",
                                          "Trimethoprim/Sulfamethoxazole": "S"}),
    ]
    for org, sir in _probe:
        if org not in OP:
            continue
        A, W, B = buckets(org, "Blood", sir)
        issues = run_ast_qa_engine(organism=org, specimen="Blood", sir_map=sir)
        impossible = {i.drug for i in issues
                      if getattr(i, "severity", "") == "CRITICAL" and i.drug}
        both = impossible & (A | W)
        if both:
            _disagree.append(f"{org}: QC says impossible, engine offers {sorted(both)}")
    check("no agent is CRITICAL-impossible in QC and offered by the engine",
          not _disagree, "\n".join(_disagree[:8]))
else:
    print("  SKIP  ast_qa_engine.py not importable")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[4] MRSA — the verdict must not depend on how the name was typed, and")
print("    every beta-lactam must fail. DEFECT: the MRSA branch filtered on")
print("    class tokens penicillin/cephalosporin/carbapenem. Amox-Clav's class")
print("    is 'Beta-lactamase Inhibitor Combination' and matched none, so a")
print("    Staph aureus + Oxacillin-R isolate got Amox-Clav as CAUTION while")
print("    the same isolate typed as 'MRSA' got it BANNED. mecA/PBP2a is not a")
print("    beta-lactamase — an inhibitor cannot rescue any of them.")
# ═══════════════════════════════════════════════════════════════════════════
_BETA_LACTAM = {d for d in G
                if any(k in (G[d].get("class", "") + " " + d).lower()
                       for k in ("penicillin", "cephalosporin", "carbapenem",
                                 "cillin", "cef", "monobactam", "penem"))}
_sir_mrsa = {d: "S" for d in _BETA_LACTAM}
_sir_mrsa.update({"Oxacillin": "R", "Cefoxitin": "R", "Vancomycin": "S"})

A1, W1, B1 = buckets("Staphylococcus aureus", "Blood", _sir_mrsa)
A2, W2, B2 = buckets("MRSA", "Blood", _sir_mrsa)
_bl_offered = (A1 | W1) & (_BETA_LACTAM - {"Oxacillin", "Cefoxitin"})
check("no beta-lactam is offered on a phenotypically MRSA isolate",
      not _bl_offered, f"offered: {sorted(_bl_offered)}")
check("the MRSA verdict is identical whether the name reads "
      "'Staphylococcus aureus + Oxacillin-R' or 'MRSA'",
      A1 == A2 and W1 == W2,
      f"allowed diff={sorted(A1 ^ A2)}  caution diff={sorted(W1 ^ W2)}")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[5] A nameless isolate must not produce a mechanism call. DEFECT:")
print("    is_esbl_producer('') returned True — `'' in 'escherichia coli'` is")
print("    True and the predicate had no length guard, though the two sibling")
print("    matchers (_remove_intrinsic_resistance, is_intrinsically_avoided)")
print("    both carry one and document exactly this risk. A blank organism")
print("    came back 'Possible AmpC β-lactamase (Predicted)', confidence 75.")
# ═══════════════════════════════════════════════════════════════════════════
_panel = {"Ceftriaxone": "R", "Ceftazidime": "R", "Cefoxitin": "R",
          "Cefepime": "S", "Meropenem": "S"}
# Phenotype detection had the identical unguarded substring test until
# 2026-08-03: a blank organism matched every rule and came back claiming
# MRSA + VRE + CRE + CRAB at once — four isolation banners and four salvage
# panels for an isolate with no name.
_ph_junk = []
for _j in (None, "", " ", "e", "a", "???", "spp."):
    _got = {p.get("phenotype") for p in detect_phenotypes(
        _j, {"Meropenem": "R", "Oxacillin": "R", "Vancomycin": "R"})}
    if _got:
        _ph_junk.append(f"detect_resistance_phenotypes({_j!r}) -> {sorted(_got)}")
check("an unnamed isolate produces no resistance phenotype at all",
      not _ph_junk, "\n".join(_ph_junk))

# Every phenotype name a detector can emit must be a real key, or a consumer
# keying on it silently finds nothing. "Possible MRSA" was emitted by a fallback
# branch and existed in no table: get_combination_therapy returned [] for it,
# and the therapy engine — whose _is_mrsa flag needs an oxacillin or cefoxitin
# the panel did not carry — recommended Ceftriaxone and Meropenem for a
# S. aureus BACTERAEMIA the screen had just labelled "possible MRSA".
_ADVISORY = {"Possible MRSA"}
_unregistered, _leaks = [], []
_probe_sir = {"Amoxicillin + Clavulanic acid": "R", "Cephalexin": "R",
              "Vancomycin": "S", "Linezolid": "S", "Meropenem": "S",
              "Ceftriaxone": "S"}
for _o in ORGS:
    for _p in detect_phenotypes(_o, _probe_sir):
        _n = _p.get("phenotype")
        if _n not in NS.get("PHENOTYPE_RULES", {}) and _n not in _ADVISORY:
            _unregistered.append(f"{_o}: emitted {_n!r}, in no table")
check("every phenotype name a detector emits is registered somewhere",
      not _unregistered, "\n".join(_unregistered[:8]))

_A, _W, _B = buckets("Staphylococcus aureus", "Blood", _probe_sir)
_ph = {p.get("phenotype") for p in detect_phenotypes("Staphylococcus aureus", _probe_sir)}
if "Possible MRSA" in _ph:
    _bl_green = _A & {"Ceftriaxone", "Meropenem", "Cefepime", "Cefuroxime",
                      "Amoxicillin", "Ampicillin", "Imipenem/Cilastatin"}
    if _bl_green:
        _leaks.append(f"phenotype says Possible MRSA, engine RECOMMENDS {sorted(_bl_green)}")
check("a 'Possible MRSA' isolate has no beta-lactam in the recommended column",
      not _leaks, "\n".join(_leaks))

_blank_hits = []
for junk in ("", " ", "  ", "e", "S", "a", ".", "spp.", "sp"):
    if is_esbl_producer(junk):
        _blank_hits.append(f"is_esbl_producer({junk!r}) -> True")
    verdict = predict_esbl(junk, _panel).get("probability")
    if verdict not in (None, "low"):
        _blank_hits.append(f"predict_esbl({junk!r}) -> {verdict!r}")
check("an unreadable / fragmentary organism name yields no mechanism call",
      not _blank_hits, "\n".join(_blank_hits[:8]))

_crashed = ""
try:
    predict_esbl(None, _panel)
except Exception as e:
    _crashed = f"{type(e).__name__}: {e}"
check("predict_esbl(None, panel) fails closed instead of raising",
      not _crashed, _crashed)


# ═══════════════════════════════════════════════════════════════════════════
print("\n[6] An Intermediate result must survive into the warning it carries.")
print("    DEFECT: the renal and hepatic branches both `continue` BEFORE the")
print("    `culture_result == 'I'` branch, so in a renally impaired patient an")
print("    I result was relabelled 'renal_adjustment'. The two instructions")
print("    point opposite ways — EUCAST 'I' means susceptible at INCREASED")
print("    exposure, the renal note says REDUCE the dose — and only one of")
print("    them was displayed.")
# ═══════════════════════════════════════════════════════════════════════════
_i_panel = {d: "I" for d in ("Ciprofloxacin", "Levofloxacin", "Meropenem",
                             "Amikacin", "Vancomycin") if d in G}
_lost = []
for org in ("E. coli", "Staphylococcus aureus"):
    if org not in OP:
        continue
    for label, kw in (("renal CrCl 25", dict(renal=True, crcl=25.0)),
                      ("Child-Pugh C", dict(hep=True, cp="C"))):
        a, w, b, p, _i = analyze(list(_i_panel), org, "Blood", 40, "Male",
                                 kw.get("renal", False), kw.get("crcl"),
                                 False, kw.get("hep", False), [], _i_panel,
                                 kw.get("cp", "A"))
        for item in w:
            if (_i_panel.get(item.get("name")) == "I"
                    and item.get("warning_reason") != "intermediate_culture"
                    and not item.get("culture_intermediate")):
                _lost.append(f"{org}/{label}: {item['name']} -> "
                             f"{item.get('warning_reason')} (I fact dropped)")
check("an Intermediate result is never overwritten by a later warning reason",
      not _lost, "\n".join(_lost[:8]))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[7] Every OCR organism alias must resolve to a selectable organism.")
print("    DEFECT: 'serratia', 's. marcescens', 'enterobacter', 'enterobacter")
print("    cloacae' and 'enterococcus faecium' mapped to profile keys that do")
print("    not exist, and best_default_index() falls back to index 0. An OCR'd")
print("    Serratia marcescens blood report silently became E. coli — losing")
print("    the entire chromosomal-AmpC derepression rule.")
# ═══════════════════════════════════════════════════════════════════════════
_dangling = [f"{k!r} -> {v!r}" for k, v in OCR_ALIASES.items() if v not in OP]
check("every ORGANISM_OCR_ALIASES target exists in ORGANISM_PROFILE",
      not _dangling, "\n".join(_dangling[:10]))

_OP_GENERA = {o.split()[0].lower().rstrip(".,") for o in OP}
_unreachable = sorted(
    {k.split()[0] for k in NS.get("AMPC_PRODUCERS", ())} - _OP_GENERA)
check("every chromosomal-AmpC genus is reachable from the organism list",
      not _unreachable,
      f"unreachable genera: {_unreachable}\n"
      "Each is a real nosocomial isolate whose AmpC derepression rule the user "
      "cannot reach, because the dropdown never offers the organism.")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[8] STRUCTURAL — every test suite in the repo runs in CI.")
print("    DEFECT: test_safety_invariants.py (28 proofs), test_clinical_matrix")
print("    .py (33 proofs) and test_guidelines.py were never added to the")
print("    workflow, so the newest and most safety-critical layer — the")
print("    terminal safety gate — shipped unguarded on every push.")
# ═══════════════════════════════════════════════════════════════════════════
_wf = os.path.join(HERE, ".github", "workflows", "cdss-tests.yml")
if os.path.exists(_wf):
    _yml = open(_wf, encoding="utf-8").read()
    _suites = sorted(f for f in os.listdir(HERE)
                     if f.startswith("test_") and f.endswith(".py"))
    _absent = [f for f in _suites if f not in _yml]
    check("no test suite is missing from .github/workflows/cdss-tests.yml",
          not _absent, f"not run in CI: {_absent}")
else:
    print("  SKIP  workflow file not found")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[9] STRUCTURAL — ast_reportability.INTRINSIC_RULES is a hand-written")
print("    list, not a projection of clinical_data.INTRINSIC_RESISTANCE. Every")
print("    row added to the table needs a matching rule added here by hand, and")
print("    three separate comments in ast_reportability record this being")
print("    forgotten (lines 125, 418, 499). Until the two are unified, this")
print("    check names the organisms where the therapy engine refuses an agent")
print("    while the QC panel stays silent about it.")
# ═══════════════════════════════════════════════════════════════════════════
try:
    from ast_reportability import check_reportability
    _RP = True
except Exception:
    _RP = False

if _RP and INTRINSIC_RESISTANCE:
    _silent = []
    # Only the unambiguous wrong-spectrum agents: these are never a matter of
    # "no breakpoint published", they are biologically inactive, so a QC panel
    # that says nothing about them is a straightforward gap.
    _WRONG_SPECTRUM = {"Vancomycin", "Teicoplanin", "Linezolid", "Daptomycin",
                       "Colistin", "Polymyxin B", "Aztreonam"}
    for org in ORGS:
        ol = org.lower().strip()
        banned_here = set()
        for key, drugs in INTRINSIC_RESISTANCE.items():
            if key and (key in ol or (len(ol) >= 4 and ol in key)):
                banned_here |= set(drugs)
        probe = {d: "S" for d in (banned_here & _WRONG_SPECTRUM) if d in G}
        if not probe:
            continue
        try:
            issues = check_reportability(org, probe)
        except Exception as exc:
            _silent.append(f"{org}: check_reportability raised {exc!r}")
            continue
        # NOTE: the two QC modules return DIFFERENT shapes. ast_qa_engine yields
        # a QAIssue dataclass with .message / .drug (singular); ast_reportability
        # yields dicts with "drugs" (plural) / "reason_en". Reading the wrong one
        # returns an empty string and every check silently passes, so both are
        # handled explicitly here rather than with a permissive .get().
        flagged: set = set()
        for i in issues or []:
            if not isinstance(i, dict):
                continue
            flagged |= set(i.get("drugs") or ([i["drug"]] if i.get("drug") else []))
        quiet = sorted(d for d in probe if d not in flagged)
        if quiet:
            _silent.append(f"{org}: engine refuses {quiet}, QC panel silent")
    check("no organism where the engine refuses a wrong-spectrum agent while "
          "ast_reportability says nothing", not _silent, "\n".join(_silent[:10]))
else:
    print("  SKIP  ast_reportability.py not importable")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[10] predict_esbl() and detect_resistance_phenotypes() must agree.")
print("    DEFECT: PHENOTYPE_RULES is a FOURTH organism table, independent of")
print("    clinical_data, ORGANISM_PROFILE and clinical_matrix._ORG_CANON. Its")
print("    CRE list omitted Citrobacter freundii, Morganella, Providencia,")
print("    Hafnia, Salmonella, Shigella and the unspeciated fallback — so on a")
print("    carbapenem-resistant isolate predict_esbl raised the red banner")
print("    while the phenotype list stayed empty, which means NO isolation")
print("    alert and NO combination-therapy panel for a CRE bacteraemia. Four")
print("    of the seven were introduced by the very audit that was fixing this")
print("    class of bug: a row added in one table, forgotten in a sibling.")
# ═══════════════════════════════════════════════════════════════════════════
get_combos = NS["get_combination_therapy"]

_CARBAPENEMASE_PH = {"CRE", "CRPA", "CRAB"}
_mismatch = []
_sir_carba = {"Meropenem": "R", "Imipenem/Cilastatin": "R", "Ertapenem": "R",
              "Ceftriaxone": "R", "Amikacin": "S", "Colistin": "S"}
for org in ORGS:
    verdict = predict_esbl(org, _sir_carba).get("probability")
    if verdict not in ("carbapenemase", "crpa"):
        continue
    phen = detect_phenotypes(org, _sir_carba)
    names = {p.get("phenotype") for p in phen}
    if not (names & _CARBAPENEMASE_PH):
        _mismatch.append(
            f"{org}: predict_esbl={verdict!r} but phenotypes={sorted(names) or 'NONE'} "
            f"-> no isolation alert, no combination panel")
check("a carbapenemase verdict always produces a matching phenotype",
      not _mismatch, "\n".join(_mismatch[:10]))

_iso = []
for org in ORGS:
    if predict_esbl(org, _sir_carba).get("probability") not in ("carbapenemase", "crpa"):
        continue
    phen = detect_phenotypes(org, _sir_carba)
    if not any(p.get("isolation") for p in phen):
        _iso.append(f"{org}: carbapenem-resistant, no isolation flag")
    if not get_combos(phen):
        _iso.append(f"{org}: carbapenem-resistant, empty combination panel")
check("a carbapenem-resistant isolate always triggers isolation + a combination panel",
      not _iso, "\n".join(_iso[:10]))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[11] The combination-therapy panel is the only place in the app that")
print("    proposes agents WITHOUT passing through analyze_antibiotics() or")
print("    apply_safety_gate(). DEFECT: get_combination_therapy() took only")
print("    `phenotypes` — no pregnancy, no age, no CrCl — and renders in an")
print("    expander that is open by default under a CRITICAL header. A pregnant")
print("    CRPA patient was shown 'Ceftolozane-Tazobactam + Amikacin' with an")
print("    empty caution field while the main engine refused amikacin for that")
print("    same patient three panels above.")
# ═══════════════════════════════════════════════════════════════════════════
_HOST_RISK_DRUGS = {
    "pregnancy": ["amikacin", "gentamicin", "tobramycin", "tigecycline",
                  "minocycline", "doxycycline", "ciprofloxacin", "levofloxacin"],
}
_unflagged = []
_sir_crpa = {"Meropenem": "R", "Imipenem/Cilastatin": "R", "Ceftazidime": "R",
             "Ciprofloxacin": "R", "Amikacin": "S", "Colistin": "S"}
for org in ("Pseudomonas aeruginosa", "Acinetobacter baumannii", "E. coli"):
    if org not in OP:
        continue
    phen = detect_phenotypes(org, _sir_crpa)
    for combo in get_combos(phen, is_pregnant=True, age_years=28):
        for opt in combo["data"]["options"]:
            low = opt["combo"].lower()
            risky = [d for d in _HOST_RISK_DRUGS["pregnancy"] if d in low]
            if risky and not opt.get("host_flagged"):
                _unflagged.append(
                    f"{org} pregnant: '{opt['combo'][:44]}' contains {risky} "
                    f"— caution={opt.get('caution','')[:30]!r}")
check("a combination option contraindicated in pregnancy is flagged as such",
      not _unflagged, "\n".join(_unflagged[:8]))

# The table is module-level and Streamlit reruns on every interaction; if
# get_combination_therapy annotated in place, one pregnant patient would leave
# pregnancy warnings on the next patient's screen.
_before = [o.get("caution", "") for o in NS["COMBINATION_THERAPY"]["CRPA"]["options"]]
get_combos(detect_phenotypes("Pseudomonas aeruginosa", _sir_crpa),
           is_pregnant=True, age_years=28, is_renal=True, cl_cr=15)
_after = [o.get("caution", "") for o in NS["COMBINATION_THERAPY"]["CRPA"]["options"]]
check("annotating host warnings does not mutate COMBINATION_THERAPY",
      _before == _after, f"before={_before}\nafter ={_after}")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[12] Colony-count and pyuria parsers. DEFECT: _parse_cfu understood")
print("    only the caret form. '10*5', '10**5', '10E5' and '10e5' all")
print("    collapsed to 10 — for an adult male urine that turns +25")
print("    'significant bacteriuria' into -15 'likely insignificant', a")
print("    40-point swing in the direction that dismisses a real infection.")
print("    Separately, every verbal report ('heavy growth', 'TNTC', 'full")
print("    field') returned 0 or None — the same value as 'no growth' — so the")
print("    strongest reading on the form scored as the weakest.")
# ═══════════════════════════════════════════════════════════════════════════
# Imported, not sliced — see the note at the pathogenicity checks below.
from pathogenicity import _parse_cfu as parse_cfu, _parse_pus as parse_pus

_EXPECT_CFU = [
    ("10^5", 100000), ("10*5", 100000), ("10**5", 100000),
    ("10E5", 100000), ("10e5", 100000), ("10 5", 100000),
    ("5x10^4", 50000), ("2 x 10^5", 200000),
    ("100000", 100000), (">100,000", 100000),
    ("No growth", 0), ("No significant growth", 0), ("", 0),
]
_bad = [f"{t!r} -> {parse_cfu(t)}, expected {e}"
        for t, e in _EXPECT_CFU if parse_cfu(t) != e]
check("_parse_cfu reads every common exponent notation", not _bad, "\n".join(_bad))

# Verbal reports must be distinguishable from "no growth" and must land in the
# right significance band, not on a threshold.
_bad = []
for t in ("heavy growth", "TNTC", "too numerous to count", "confluent growth", "+++"):
    if parse_cfu(t) < 100000:
        _bad.append(f"{t!r} -> {parse_cfu(t)}, should reach the 10^5 band")
for t in ("moderate growth", "++"):
    if not 10000 <= parse_cfu(t) < 100000:
        _bad.append(f"{t!r} -> {parse_cfu(t)}, should sit in the 10^4 band")
for t in ("scanty growth", "few colonies"):
    if not 1000 <= parse_cfu(t) < 10000:
        _bad.append(f"{t!r} -> {parse_cfu(t)}, should sit in the 10^3 band")
check("a verbal colony report is never scored as 'no growth'", not _bad,
      "\n".join(_bad))

_bad = [f"{t!r} -> {parse_pus(t)}" for t in
        ("full field", "loaded", "TNTC", "plenty", "many")
        if parse_pus(t) is None]
check("a verbal pyuria report is not silently dropped", not _bad, "\n".join(_bad))
check("_parse_pus still returns None when nothing is stated",
      parse_pus("") is None and parse_pus("not done") is None,
      f"'' -> {parse_pus('')}, 'not done' -> {parse_pus('not done')}")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[13] Every organism in ORGANISM_PROFILE must be selectable somewhere.")
print("    DEFECT: 'Rickettsia spp.' carried a full profile — first_line, avoid,")
print("    specimen_context, note — and appeared in NO specimen list, so")
print("    get_organisms_for_specimen() never offered it and not one of those")
print("    fields could ever reach a user. A profile that cannot be selected")
print("    still has to be maintained and audited forever, and can never fire.")
# ═══════════════════════════════════════════════════════════════════════════
_orphan = [o for o in ORGS
           if not any(o in get_organisms_for_specimen(s) for s in SPECS)]
check("no ORGANISM_PROFILE entry is unreachable from every specimen",
      not _orphan, f"unreachable: {_orphan}")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[14] The pathogenicity score must not run BACKWARDS at the bottom of")
print("    the colony-count range. DEFECT: all three age/sex branches ended at")
print("    `elif cfu_val > 0: score -= PENALTY`, so a zero — which meant both")
print("    'no growth' AND 'field blank / unparseable' — hit no branch at all")
print("    and escaped the penalty a real low count pays:")
print("        male 35, dysuria, pyuria 20-25:")
print("            'No growth' -> 45   but   '10^3 CFU/mL' -> 30")
print("        infant, colony-count field left blank:")
print("            -> 85 -> 'Likely TRUE INFECTION -- Treat'")
print("    Sterile urine outranking scanty growth is the wrong direction; a")
print("    verdict built from an unread field is worse — an opinion assembled")
print("    out of missing data.")
# ═══════════════════════════════════════════════════════════════════════════
# 2026-08-03: the pathogenicity engine moved into pathogenicity.py, so these
# are IMPORTED rather than sliced out of streamlit_app.py. That is the point of
# extracting them — a module you can import is a module you can test without a
# 900-line AST harness standing in for an import statement.
try:
    from pathogenicity import (assess_pathogenicity as assess,
                               _cfu_report_state as cfu_state)
except ImportError:
    assess = cfu_state = None
if assess is None or cfu_state is None:
    print("  SKIP  assess_pathogenicity / _cfu_report_state not extracted")
else:
    _SYM = ["Dysuria / Frequency / Urgency"]

    def _score(colony, age, sex):
        return assess("Urine", "E. coli", colony, "Pure growth", _SYM,
                      "20-25", "", "", age, sex, [])

    _LADDER = ["10^2", "10^3", "10^4", "10^5", "heavy growth"]
    _mono = []
    for label, age, sex in (("male 35", 35, "Male"),
                            ("female 30", 30, "Female"),
                            ("infant", 0, "Male")):
        none_score = _score("No growth", age, sex)["score"]
        prev = None
        for c in _LADDER:
            s = _score(c, age, sex)["score"]
            if prev is not None and s < prev:
                _mono.append(f"{label}: score fell from {prev} to {s} going up "
                             f"the colony ladder at {c!r}")
            prev = s
        lowest_counted = _score("10^2", age, sex)["score"]
        if none_score >= lowest_counted:
            _mono.append(f"{label}: 'No growth' scores {none_score}, "
                         f"'10^2' scores {lowest_counted} — sterile urine must "
                         f"score BELOW any real count")
    check("the pathogenicity score rises monotonically with colony count",
          not _mono, "\n".join(_mono[:8]))

    # An unread field must contribute nothing AND say so.
    _states = {t: cfu_state(t) for t in
               ("", "   ", "???", "No growth", "لا يوجد نمو",
                "No significant growth", "10^5", "heavy growth")}
    _want = {"": "unreported", "   ": "unreported", "???": "unreported",
             "No growth": "none", "لا يوجد نمو": "none",
             "No significant growth": "none",
             "10^5": "counted", "heavy growth": "counted"}
    _wrong = [f"{t!r} -> {_states[t]!r}, expected {_want[t]!r}"
              for t in _want if _states[t] != _want[t]]
    check("'no growth', 'not reported' and a real count are three distinct states",
          not _wrong, "\n".join(_wrong))

    _blank = _score("", 35, "Male")
    _flagged = "CFU_NOT_REPORTED" in (_blank.get("special_flags") or [])
    check("an unreadable colony count is flagged to the user, not scored silently",
          _flagged, f"special_flags={_blank.get('special_flags')}")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[15] A phenotype named 'Carbapenem-Resistant' must be defined on")
print("    CARBAPENEMS. DEFECT: PHENOTYPE_RULES['CRPA'] required 2 of four")
print("    markers, and two of the four — Pip-Tazo and Ceftazidime — are not")
print("    carbapenems. It broke both ways:")
print("      MISSED  Meropenem-R alone -> no CRPA, no isolation alert, no")
print("              combination panel. Egyptian panels routinely carry")
print("              meropenem as the only carbapenem.")
print("      CALLED  Ceftazidime-R + Pip-Tazo-R with BOTH carbapenems S ->")
print("              'CRPA', immediate-isolation banner and an XDR salvage")
print("              panel, for a carbapenem-SUSCEPTIBLE isolate — while")
print("              predict_esbl said 'low' on the same screen.")
print("    CRAB required 1 of 2 and CRE 1 of 3; CRPA was the lone outlier.")
# ═══════════════════════════════════════════════════════════════════════════
_RULES = NS.get("PHENOTYPE_RULES", {})
_CARBAPENEMS = {"imipenem", "meropenem", "ertapenem", "doripenem", "biapenem"}

_bad_def = []
for _ph in ("CRE", "CRPA", "CRAB"):
    _rule = _RULES.get(_ph)
    if not _rule:
        _bad_def.append(f"{_ph}: rule missing entirely")
        continue
    _marks = [m[0] for m in _rule.get("markers", [])]
    _noncarb = [d for d in _marks
                if not any(c in d.lower() for c in _CARBAPENEMS)]
    if _noncarb:
        _bad_def.append(f"{_ph}: non-carbapenem markers {_noncarb} in a "
                        f"carbapenem-resistance definition")
    if _rule.get("require_any", 99) != 1:
        _bad_def.append(f"{_ph}: require_any={_rule.get('require_any')}; "
                        f"CDC/IDSA/EUCAST define these as resistance to AT "
                        f"LEAST ONE carbapenem")
check("carbapenem-resistance phenotypes use carbapenem markers, threshold 1",
      not _bad_def, "\n".join(_bad_def))

# Behavioural proof, in both directions.
_dir = []
_ONE_CARB = [("Meropenem R only", {"Meropenem": "R", "Amikacin": "S"}),
             ("Imipenem R only", {"Imipenem/Cilastatin": "R", "Amikacin": "S"})]
for _label, _sir in _ONE_CARB:
    _got = {p.get("phenotype") for p in detect_phenotypes("Pseudomonas aeruginosa", _sir)}
    if "CRPA" not in _got:
        _dir.append(f"MISS — {_label}: phenotypes={sorted(_got) or 'NONE'}")
_carb_susceptible = {"Ceftazidime": "R", "Piperacillin + Tazobactam": "R",
                     "Meropenem": "S", "Imipenem/Cilastatin": "S"}
_got = {p.get("phenotype") for p in detect_phenotypes("Pseudomonas aeruginosa",
                                                      _carb_susceptible)}
if "CRPA" in _got:
    _dir.append("OVER-CALL — both carbapenems S but CRPA fired")
check("CRPA fires on one carbapenem and never on a carbapenem-susceptible isolate",
      not _dir, "\n".join(_dir))

# Ertapenem must not appear: P. aeruginosa is intrinsically resistant to it, so
# an ertapenem-R result carries no information about acquired resistance.
_crpa_marks = [m[0].lower() for m in _RULES.get("CRPA", {}).get("markers", [])]
# A marker naming an agent outside the formulary can never match: it reads as a
# rule but is inert. Doripenem sat in the CRPA list this way until 2026-08-03.
_ghost = []
for _ph, _r in _RULES.items():
    for _d, _ in _r.get("markers", []):
        if _d not in G:
            _ghost.append(f"{_ph}: marker {_d!r} is not in the formulary")
check("no phenotype marker names an agent outside the formulary",
      not _ghost, "\n".join(_ghost))

check("CRPA does not read ertapenem (P. aeruginosa is intrinsically resistant)",
      not any("ertapenem" in m for m in _crpa_marks),
      f"CRPA markers = {_crpa_marks}")

# Every phenotype that raises an isolation banner must have a therapy panel,
# or the alert tells the ward to isolate and the clinician nothing to give.
_orphan_ph = []
for _name, _rule in _RULES.items():
    if not _rule.get("isolation"):
        continue
    if _name not in NS.get("COMBINATION_THERAPY", {}):
        _orphan_ph.append(f"{_name}: isolation=True but no COMBINATION_THERAPY entry")
check("every isolation-triggering phenotype has a treatment panel",
      not _orphan_ph, "\n".join(_orphan_ph))


# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
print("\n[16] GUIDELINE PINS — web-verified 2026-08-03. Three assignments were")
print("    wrong against WHO AWaRe 2025 (B09489, 5 Sep 2025): Aztreonam was")
print("    Watch and is Reserve; oral Fosfomycin was Access and is Watch;")
print("    Ampicillin/Sulbactam was Watch and is Access. Two that looked wrong")
print("    are right: Tobramycin is Watch while gentamicin and amikacin are")
print("    Access, and Vancomycin is Watch by both routes.")
# ═══════════════════════════════════════════════════════════════════════════
_WHO_2025 = {
    "Aztreonam": "Reserve", "Fosfomycin": "Watch", "Ampicillin/Sulbactam": "Access",
    "Tobramycin": "Watch", "Gentamicin": "Access", "Amikacin": "Access",
    "Vancomycin": "Watch", "Teicoplanin": "Watch", "Linezolid": "Reserve",
    "Colistin": "Reserve", "Clindamycin": "Access", "Minocycline": "Watch",
    "Amoxicillin + Clavulanic acid": "Access", "Piperacillin + Tazobactam": "Watch",
    "Cefazolin": "Access", "Cephalexin": "Access", "Ceftriaxone": "Watch",
    "Meropenem": "Watch", "Ertapenem": "Watch", "Ciprofloxacin": "Watch",
    "Nitrofurantoin": "Access", "Trimethoprim/Sulfamethoxazole": "Access",
    "Doxycycline": "Access", "Metronidazole": "Access", "Rifampicin": "Watch",
}
_aw = [f"{d}: code={G[d].get('aware')!r} WHO={e!r}"
       for d, e in _WHO_2025.items() if d in G and G[d].get("aware") != e]
check("AWaRe categories match the WHO 2025 list", not _aw, "\n".join(_aw))

# Nitrofurantoin: MHRA/BNF contraindication is eGFR < 45, not < 60.
check("nitrofurantoin renal threshold is 45 (MHRA DSU Feb 2015 / BNF)",
      G.get("Nitrofurantoin", {}).get("renal_limit") == 45,
      f"renal_limit = {G.get('Nitrofurantoin', {}).get('renal_limit')}")

# DTR is non-susceptibility to ALL EIGHT (Kadri 2018 / IDSA), not a majority.
_dtr = _RULES.get("DTR_PA", {})
_dtr_marks = {d for d, _ in _dtr.get("markers", [])}
_EXPECTED_DTR = {"Piperacillin + Tazobactam", "Ceftazidime", "Cefepime", "Aztreonam",
                 "Meropenem", "Imipenem/Cilastatin", "Ciprofloxacin", "Levofloxacin"}
check("DTR-PA names exactly the eight Kadri agents",
      _dtr_marks == _EXPECTED_DTR,
      f"missing={sorted(_EXPECTED_DTR - _dtr_marks)} extra={sorted(_dtr_marks - _EXPECTED_DTR)}")
check("DTR-PA requires every TESTED agent to be resistant, not a majority",
      _dtr.get("require_all_tested") is True,
      f"require_all_tested={_dtr.get('require_all_tested')} require_any={_dtr.get('require_any')}")

_over = []
_full = {d: "R" for d in _EXPECTED_DTR}
for _spare in ("Cefepime", "Levofloxacin", "Meropenem"):
    _sir = dict(_full); _sir[_spare] = "S"
    if "DTR_PA" in {p.get("phenotype") for p in detect_phenotypes("Pseudomonas aeruginosa", _sir)}:
        _over.append(f"{_spare} susceptible but DTR still called")
check("DTR-PA is not called when any of the eight is still susceptible",
      not _over, "\n".join(_over))


print("\n" + "=" * 72)
print(f"{len(_PASS)} passed, {len(_FAIL)} failed")
if _FAIL:
    print("\nRESULT: FAILURES — see above")
    if __name__ == "__main__":
        sys.exit(1)
print("\nRESULT: ALL GREEN")
print("\nNOTE: this suite guards ENGINE AGREEMENT and TABLE REACHABILITY.")
print("      It does not re-check that the tables match EUCAST v16 — that is")
print("      still the clinician countersignature queue in guideline_registry.")
