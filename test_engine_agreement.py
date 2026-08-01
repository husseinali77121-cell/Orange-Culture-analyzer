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
    "_SIR_ALIASES", "normalize_sir_value", "normalize_sir_map",
    "_MED_CANON", "_canon_med",
    "ASSUMED_CRCL_UNKNOWN", "resolve_crcl", "crcl_label", "get_renal_severity",
    "_PREG_ALIASES", "preg_status_of", "_ACQUIRED_NOT_INTRINSIC",
    "MDR_CATEGORIES_STAPH", "MDR_CATEGORIES_ENTEROCOCCUS",
    "MDR_CATEGORIES_STREP", "MDR_NOT_APPLICABLE", "MDR_OUTSIDE_MAGIORAKOS",
    "NEONATAL_RESTRICTIONS",
    "ESBL_PRODUCERS", "AMPC_PRODUCERS", "ESBL_MARKERS", "CARBAPENEMS",
    "_ORG_NON_INFORMATIVE", "_org_matches", "is_esbl_producer", "predict_esbl", "MDR_CATEGORIES",
    "MDR_CATEGORIES_GRAM_NEG", "MDR_CATEGORIES_GRAM_POS",
    "GRAM_POSITIVE_ORGANISMS", "_remove_intrinsic_resistance", "classify_mdr",
    "MDR_INFO", "HEPATIC_DOSING", "analyze_antibiotics", "_hide_urine_only",
    "ORGANISM_OCR_ALIASES",
]

if not os.path.exists(APP):
    print(f"ENVIRONMENT INCOMPLETE — {APP} not found.")
    sys.exit(2)

from abx_guidelines import ABX_GUIDELINES as G                      # noqa: E402
from organism_profile import ORGANISM_PROFILE as OP                 # noqa: E402
from specimen_organism_map import (                                 # noqa: E402
    SPECIMEN_ORDER, get_organisms_for_specimen,
)

_seg, _order, _missing = _extract(APP, _WANT)
NS: dict = {
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
_GRAM_POS_ORGS = {"Staphylococcus aureus", "MRSA", "Enterococcus faecalis",
                  "Enterococcus faecium", "Streptococcus pneumoniae", "VRE"}
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
print("\n" + "=" * 72)
print(f"{len(_PASS)} passed, {len(_FAIL)} failed")
if _FAIL:
    print("\nRESULT: FAILURES — see above")
    sys.exit(1)
print("\nRESULT: ALL GREEN")
print("\nNOTE: this suite guards ENGINE AGREEMENT and TABLE REACHABILITY.")
print("      It does not re-check that the tables match EUCAST v16 — that is")
print("      still the clinician countersignature queue in guideline_registry.")
