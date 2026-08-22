#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_safety_invariants.py — regression proofs for the July-2026 safety audit.

Every check in this file corresponds to a defect that was FOUND IN PRODUCTION
CODE and fixed. The point of the file is not to prove the engine is correct in
general — nothing can do that — but to guarantee that these specific failures
can never come back silently.

Each test states the defect it guards, so a future reader who trips one knows
what was at stake rather than just seeing a red line.

Run:  python test_safety_invariants.py            (quiet)
      python test_safety_invariants.py --verbose  (list every case)

Files needed alongside: streamlit_app.py, abx_guidelines.py, organism_profile.py,
specimen_organism_map.py, clinical_data.py, clinical_matrix.py, safety_gate.py
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
            for line in str(detail).splitlines()[:8]:
                print(f"          {line}")
    elif VERBOSE:
        print(f"  PASS  {name}")


# ═══════════════════════════════════════════════════════════════════════════
# Load the monolith's pure decision logic without a Streamlit runtime
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
    # Shared helpers the engines now call. They must be extracted BEFORE the
    # functions that use them, or the re-exec'd copy raises NameError.
    
    "_MED_CANON", "_canon_med",
    # Added 2026-07-30 with the unknown-CrCl fix. analyze_antibiotics now calls
    # resolve_crcl() on entry, so omitting these from the extraction list makes
    # the whole suite die on NameError rather than fail a check.
    "ASSUMED_CRCL_UNKNOWN", "resolve_crcl", "crcl_label", "get_renal_severity",
    "_PREG_ALIASES", "preg_status_of", "_ACQUIRED_NOT_INTRINSIC",
    "MDR_CATEGORIES_STAPH", "MDR_CATEGORIES_ENTEROCOCCUS",
    "MDR_CATEGORIES_STREP", "MDR_NOT_APPLICABLE", "MDR_OUTSIDE_MAGIORAKOS",
    "NEONATAL_RESTRICTIONS",
    "ESBL_PRODUCERS", "AMPC_PRODUCERS", "ESBL_MARKERS", "CARBAPENEMS",
    "_re_ws_collapse", "_ORG_NON_INFORMATIVE", "_org_matches", "is_esbl_producer", "predict_esbl", "MDR_CATEGORIES",
    "MDR_CATEGORIES_GRAM_NEG", "MDR_CATEGORIES_GRAM_POS",
    "GRAM_POSITIVE_ORGANISMS", "_remove_intrinsic_resistance", "classify_mdr",
    "MDR_INFO", "HEPATIC_DOSING", "analyze_antibiotics", "_hide_urine_only",
]

if not os.path.exists(APP):
    print(f"ENVIRONMENT INCOMPLETE — {APP} not found.")
    if __name__ == "__main__":
        sys.exit(2)

from abx_guidelines import ABX_GUIDELINES as G                     # noqa: E402
from organism_profile import ORGANISM_PROFILE as OP                # noqa: E402
from specimen_organism_map import (                                # noqa: E402
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
import re as _re                                                    # noqa: E402
NS["re"] = _re
try:
    from clinical_data import INTRINSIC_RESISTANCE
    NS["INTRINSIC_RESISTANCE"] = INTRINSIC_RESISTANCE
except Exception:
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
classify_specimen = NS["classify_specimen"]
HEPATIC_DOSING = NS["HEPATIC_DOSING"]
SPECS = list(SPECIMEN_ORDER)
ORGS = list(OP)


def buckets(drugs, org, spec, *, age=40, sex="Male", renal=False, crcl=100.0,
            preg=False, hep=False, cp="A", sir=None):
    sir = sir or {d: "S" for d in drugs}
    a, w, b, p, _i = analyze(drugs, org, spec, age, sex, renal, crcl, preg, hep,
                             [], sir, cp)
    nm = lambda L: {x.get("name") for x in L}
    return nm(a), nm(w), nm(b), nm(p)


def cls_of(d):
    return (G[d].get("class") or "").lower()


PREG_ABSOLUTE = [
    d for d in G
    if G[d].get("preg_status") == "Banned"
    or "tetracycline" in cls_of(d)
    or "aminoglycoside" in cls_of(d)
    or "clarithromycin" in d.lower()
]
CHILD_UNSAFE = [d for d in G if not G[d].get("child_safe", True)]

print("=" * 72)
print("Orange Lab CDSS — safety invariants (July 2026 audit regression suite)")
print(f"  {len(G)} agents · {len(ORGS)} organisms · {len(SPECS)} specimens")
print("=" * 72)
if _missing:
    print(f"\n  WARNING: could not extract {_missing} from streamlit_app.py")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] DEFECT: a renal 'continue' short-circuited pregnancy screening")
print("    Pregnant + CrCl<=renal_limit showed aminoglycosides as 'use with")
print("    caution' instead of BANNED. 560 leaking cells across the space.")
# ═══════════════════════════════════════════════════════════════════════════
leaks = []
for spec in SPECS:
    for org in ORGS:
        for crcl in (10, 20, 25, 30, 35, 40, 45, 50, 55, 59, 60, 70, 95):
            for renal in (True, False):
                A, W, B, P = buckets(PREG_ABSOLUTE, org, spec, age=30, sex="Female",
                                     renal=renal, crcl=float(crcl), preg=True)
                bad = (A | W | P) & set(PREG_ABSOLUTE)
                if bad:
                    leaks.append(f"{spec}/{org} renal={renal} CrCl={crcl}: {sorted(bad)}")
check("pregnancy-absolute agents never reach allowed/caution at any CrCl",
      not leaks, "\n".join(leaks[:5]))

# the specific historical case, named so it can never be lost in aggregate
_, W, B, P = buckets(["Gentamicin", "Amikacin", "Tobramycin"], "E. coli", "Urine",
                     age=28, sex="Female", renal=True, crcl=55.0, preg=True)
check("regression: pregnant + CrCl 55 bans Gentamicin/Amikacin/Tobramycin",
      {"Gentamicin", "Amikacin", "Tobramycin"} <= B,
      f"warned={sorted(W)} banned={sorted(B)}")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[2] DEFECT: hepatic 'Avoid' verdicts were annotated but never enforced")
# ═══════════════════════════════════════════════════════════════════════════
HEP_AVOID_C = [k for k, v in HEPATIC_DOSING.items()
               if isinstance(v.get("C"), tuple)
               and "avoid" in str(v["C"][0]).lower() and k in G]
hep_leaks = []
for spec in SPECS:
    for org in ORGS[:8]:
        A, W, B, P = buckets(HEP_AVOID_C, org, spec, age=45, hep=True, cp="C")
        bad = (A | W | P) & set(HEP_AVOID_C)
        if bad:
            hep_leaks.append(f"{spec}/{org}: {sorted(bad)}")
check("Child-Pugh C 'Avoid' agents are removed, not merely annotated",
      not hep_leaks, "\n".join(hep_leaks[:5]))

A, _, B, _ = buckets(["Amoxicillin + Clavulanic acid", "Doxycycline", "Nitrofurantoin"],
                     "E. coli", "Urine", hep=True, cp="C")
check("regression: Child-Pugh C bans Amox-Clav / Doxycycline / Nitrofurantoin",
      not A and len(B) == 3, f"allowed={sorted(A)}")

# Child-Pugh A must NOT be over-restricted — monotonicity in the safe direction
A_a, _, _, _ = buckets(["Amoxicillin + Clavulanic acid"], "E. coli", "Urine",
                       hep=True, cp="A")
check("Child-Pugh A does not over-restrict (Amox-Clav still offered)",
      "Amoxicillin + Clavulanic acid" in A_a)

check("every hepatic_caution agent has a hepatic dosing row",
      not [k for k, v in G.items() if v.get("hepatic_caution") and k not in HEPATIC_DOSING],
      str([k for k, v in G.items() if v.get("hepatic_caution") and k not in HEPATIC_DOSING]))

check("analyze_antibiotics accepts a child_pugh argument",
      "child_pugh" in _seg["analyze_antibiotics"].split(")")[0])


# ═══════════════════════════════════════════════════════════════════════════
print("\n[3] DEFECT: three different 'is this urine?' tests disagreed")
print("    MSU / Midstream / Catheter specimen were treated as non-urine by the")
print("    urine-only filter, banning Nitrofurantoin off a real urine sample.")
# ═══════════════════════════════════════════════════════════════════════════
URINE_SYNONYMS = ["Urine", "Mid-stream urine", "MSU", "Midstream",
                  "Catheter specimen", "urine (CSU)"]
mismatch = []
for s in URINE_SYNONYMS:
    A, W, B, P = buckets(["Nitrofurantoin", "Fosfomycin"], "E. coli", s)
    if {"Nitrofurantoin", "Fosfomycin"} & B:
        mismatch.append(f"{s}: banned={sorted(B)}")
check("urine-only agents survive on every urine synonym", not mismatch,
      "\n".join(mismatch))

wrong = [s for s in URINE_SYNONYMS if classify_specimen(s) != "urine"]
check("classify_specimen() recognises every urine synonym", not wrong, str(wrong))

# and they must still be banned off-urine
off = []
for s in ["Blood", "CSF", "Sputum", "Wound Swab", "Pus"]:
    A, W, B, P = buckets(["Nitrofurantoin", "Fosfomycin"], "E. coli", s)
    if (A | W | P) & {"Nitrofurantoin", "Fosfomycin"}:
        off.append(f"{s}: {sorted((A | W | P))}")
check("urine-only agents remain banned on systemic sites", not off, "\n".join(off))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[4] DEFECT: cephalosporins warned but BLI combos banned on the same")
print("    unconfirmed-carbapenemase isolate — the asymmetry was backwards.")
# ═══════════════════════════════════════════════════════════════════════════
sir_oxa = {"Ceftriaxone": "S", "Cefotaxime": "S", "Piperacillin + Tazobactam": "S",
           "Ertapenem": "R", "Meropenem": "S"}
A, W, B, P = buckets(list(sir_oxa), "Klebsiella pneumoniae", "Blood", sir=sir_oxa)
ceph_warned = {"Ceftriaxone", "Cefotaxime"} <= W
bli_warned = "Piperacillin + Tazobactam" in W
check("possible-carbapenemase treats cephalosporins and BLI combos alike",
      ceph_warned == bli_warned,
      f"cephs warned={ceph_warned} BLI warned={bli_warned} | W={sorted(W)} B={sorted(B)}")
check("neither class is silently promoted to 'recommended' on a systemic site",
      not ({"Ceftriaxone", "Piperacillin + Tazobactam"} & A), f"allowed={sorted(A)}")

# confirmed ESBL on blood must still ban BLI combos (MERINO 2018)
sir_esbl = {"Ceftriaxone": "R", "Cefotaxime": "R", "Ceftazidime": "R",
            "Piperacillin + Tazobactam": "S", "Meropenem": "S"}
A2, W2, B2, _ = buckets(list(sir_esbl), "E. coli", "Blood", sir=sir_esbl)
check("confirmed ESBL bacteraemia still bans BLI combos (MERINO 2018)",
      "Piperacillin + Tazobactam" in B2,
      f"allowed={sorted(A2)} warned={sorted(W2)}")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[5] DEFECT: tetracyclines at age 8-17 fell through to a reasonless ban")
# ═══════════════════════════════════════════════════════════════════════════
_, _, _, _ = buckets(["Doxycycline"], "E. coli", "Urine", age=12)
a, w, b, p, _i = analyze(["Doxycycline"], "E. coli", "Urine", 12, "Male",
                         False, 100.0, False, False, [], {"Doxycycline": "S"}, "A")
row = next((x for x in b if x["name"] == "Doxycycline"), None)
check("age 12 tetracycline ban carries a real clinical reason",
      row is not None and "تقييم متخصص" not in row["reason_detail"]
      and len(row["reason_detail"]) > 80,
      (row or {}).get("reason_detail", "MISSING")[:120])

a, w, b, p, _i = analyze(["Doxycycline"], "E. coli", "Urine", 5, "Male",
                         False, 100.0, False, False, [], {"Doxycycline": "S"}, "A")
row5 = next((x for x in b if x["name"] == "Doxycycline"), None)
check("age 5 tetracycline keeps the dental/bone rationale",
      row5 is not None and "8" in row5["reason_short"])

kid_leaks = []
for spec in SPECS:
    for age in (1, 5, 9, 14, 17):
        for renal, crcl in ((False, 100.0), (True, 30.0), (True, 55.0)):
            A, W, B, P = buckets(CHILD_UNSAFE, "E. coli", spec, age=age,
                                 renal=renal, crcl=crcl)
            bad = (A | W | P) & set(CHILD_UNSAFE)
            if bad:
                kid_leaks.append(f"{spec} age={age} CrCl={crcl}: {sorted(bad)}")
check("paediatric-unsafe agents never reach allowed/caution", not kid_leaks,
      "\n".join(kid_leaks[:5]))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[6] DEFECT: clinical_matrix + safety_gate existed but were never imported")
# ═══════════════════════════════════════════════════════════════════════════
app_src = open(APP, encoding="utf-8").read()
app_tree = ast.parse(app_src)
imported = set()
for n in ast.walk(app_tree):
    if isinstance(n, ast.ImportFrom) and n.module:
        imported.add(n.module)
    elif isinstance(n, ast.Import):
        for al in n.names:
            imported.add(al.name)
check("streamlit_app.py imports safety_gate", "safety_gate" in imported)
check("streamlit_app.py imports clinical_matrix", "clinical_matrix" in imported)
check("apply_safety_gate is actually called, not merely imported",
      "apply_safety_gate(" in app_src.split("from safety_gate import")[-1])
check("the gate is declared CRITICAL in _MODULE_HEALTH",
      "SAFETY_GATE_AVAILABLE, True" in app_src)

try:
    from safety_gate import apply_safety_gate
    from clinical_matrix import evaluate  # noqa: F401
    GATE_OK = True
except Exception as exc:                                   # pragma: no cover
    GATE_OK = False
    print(f"        (gate import failed: {exc})")
check("safety_gate imports cleanly", GATE_OK)

if GATE_OK:
    # demote-only property: the gate may tighten, never loosen
    promoted = []
    for spec in SPECS:
        for org in ORGS[:8]:
            drugs = list(G)[:30]
            sir = {d: "S" for d in drugs}
            a, w, b, p, _i = analyze(drugs, org, spec, 40, "Male", False, 100.0,
                                     False, False, [], sir, "A")
            A0 = {x["name"] for x in a}
            B0 = {x["name"] for x in b}
            A1, W1, B1, rep = apply_safety_gate(
                a, w, b, organism=org, specimen=spec, sir_map=sir,
                age_years=40, cl_cr=100.0)
            n1 = {x.get("name") for x in A1}
            nb = {x.get("name") for x in B1}
            if n1 - A0:
                promoted.append(f"{spec}/{org}: gained allowed {sorted(n1 - A0)}")
            if B0 - nb:
                promoted.append(f"{spec}/{org}: lost bans {sorted(B0 - nb)}")
    check("safety gate is demote-only (never promotes, never un-bans)",
          not promoted, "\n".join(promoted[:5]))

    # the defect the matrix was built for: CNS penetration
    NO_CNS = ["Cefazolin", "Cephalexin", "Clindamycin", "Azithromycin", "Ertapenem"]
    sir = {d: "S" for d in NO_CNS + ["Ceftriaxone", "Meropenem"]}
    a, w, b, p, _i = analyze(list(sir), "Streptococcus pneumoniae", "CSF", 30,
                             "Male", False, 100.0, False, False, [], sir, "A")
    A1, W1, B1, rep = apply_safety_gate(a, w, b, organism="Streptococcus pneumoniae",
                                        specimen="CSF", sir_map=sir,
                                        age_years=30, cl_cr=100.0)
    still = {x.get("name") for x in A1} & set(NO_CNS)
    check("agents that cannot cross the BBB are not recommended for CSF",
          not still, f"still recommended for meningitis: {sorted(still)}")
    check("agents that DO cross the BBB survive the CSF gate",
          {"Ceftriaxone", "Meropenem"} <= {x.get("name") for x in A1},
          f"allowed={sorted(x.get('name') for x in A1)}")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[7] STRUCTURAL: defects that hide from review rather than from tests")
# ═══════════════════════════════════════════════════════════════════════════
import pathlib                                                     # noqa: E402
dups = []
for p in pathlib.Path(HERE).rglob("*.py"):
    if "__pycache__" in str(p):
        continue
    try:
        t = ast.parse(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    for node in ast.walk(t):
        if isinstance(node, ast.Dict):
            seen = {}
            for k in node.keys:
                if k is None:
                    continue
                try:
                    v = ast.literal_eval(k)
                except Exception:
                    continue
                if not isinstance(v, (str, int, float, bool, tuple)):
                    continue
                if v in seen:
                    dups.append(f"{p.name}:{node.lineno} duplicate key {v!r}")
                seen[v] = 1
check("no duplicate dict keys anywhere in the repo", not dups, "\n".join(dups[:8]))

bad_avoid = []
for o, v in OP.items():
    cm = NS["ORGANISM_AVOID_CLASS_MAP"]
    for a_ in (v.get("avoid") or []):
        if a_ in G:
            continue
        al = a_.lower().strip()
        if al in cm:
            continue
        if any(al in d.lower() or d.lower() in al for d in G):
            continue
        bad_avoid.append(f"{o} -> {a_!r}")
check("every ORGANISM_PROFILE 'avoid' entry resolves to something real",
      not bad_avoid, "\n".join(bad_avoid[:8]))

for f in ("clinical_matrix.py", "safety_gate.py"):
    check(f"{f} is present", os.path.exists(os.path.join(HERE, f)))


# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
print("\n[AGE] The gate must read MONTHS, not the integer year field.")
print("    DEFECT 2026-08-03: apply_safety_gate() took age_years only, and the")
print("    caller passes the UI's integer year field — 0 for every infant from")
print("    birth to eleven months. clinical_matrix.NEONATE_MAX_YEARS is")
print("    correctly 28/365, but 0 <= 0.0767, so a six-month-old was evaluated")
print("    as a neonate and NEONATAL_DENY banned Ceftriaxone in blood, urine")
print("    AND CSF — the first-line agent for infant bacteraemia and infant")
print("    meningitis beyond the neonatal period.")
# ═══════════════════════════════════════════════════════════════════════════
try:
    from safety_gate import apply_safety_gate as _gate
    import inspect as _insp
    _sig = _insp.signature(_gate)
    check("apply_safety_gate accepts age_months", "age_months" in _sig.parameters,
          f"params = {list(_sig.parameters)}")

    _sir = {"Ceftriaxone": "S", "Cefotaxime": "S", "Meropenem": "S",
            "Trimethoprim/Sulfamethoxazole": "S"}

    def _state(drug, months, spec="CSF"):
        a, w, b, p, _i = analyze(list(_sir), "E. coli", spec, 0, "Male", False,
                                 None, False, False, [], _sir, "A", months)
        a, w, b, _r = _gate(a, w, b, organism="E. coli", specimen=spec,
                            sir_map=_sir, age_years=0, age_months=months,
                            child_pugh="A")
        if drug in {x.get("name") for x in a}: return "allowed"
        if drug in {x.get("name") for x in w}: return "warned"
        return "banned"

    _age_bad = []
    # Neonate: ceftriaxone out (bilirubin displacement), cefotaxime in.
    if _state("Ceftriaxone", 0) != "banned":
        _age_bad.append("0 mo: Ceftriaxone not banned — kernicterus risk")
    if _state("Cefotaxime", 0) == "banned":
        _age_bad.append("0 mo: Cefotaxime banned — it is the neonatal alternative")
    # Beyond the neonatal period it must come back, at every site.
    for _mo in (1, 2, 6, 11):
        for _sp in ("CSF", "Blood", "Urine"):
            if _state("Ceftriaxone", _mo, _sp) == "banned":
                _age_bad.append(f"{_mo} mo / {_sp}: Ceftriaxone still banned "
                                f"past the 28-day neonatal window")
    # TMP-SMX: banned under 2 months, available after.
    if _state("Trimethoprim/Sulfamethoxazole", 1) != "banned":
        _age_bad.append("1 mo: TMP-SMX not banned")
    if _state("Trimethoprim/Sulfamethoxazole", 6) == "banned":
        _age_bad.append("6 mo: TMP-SMX still banned past its 2-month window")
    check("neonatal bans lift at the correct month, at every site",
          not _age_bad, "\n".join(_age_bad[:10]))

    # A months value outside 0-11 is a data error. The gate falls back to
    # age_years, which is 0 here, so the isolate is treated as a neonate and
    # ceftriaxone stays banned. That is the correct direction: with the age
    # unknown and the year field reading 0, the patient MIGHT be a neonate, and
    # the engine simultaneously raises "عمر غير محدد بالشهور" asking for the
    # month. Fail closed, prompt for the missing datum — do not guess older.
    check("an unusable months value fails CLOSED rather than widening the window",
          all(_state("Ceftriaxone", _bad) == "banned" for _bad in (99, -3, None)),
          f"99 -> {_state('Ceftriaxone', 99)}, "
          f"-3 -> {_state('Ceftriaxone', -3)}, "
          f"None -> {_state('Ceftriaxone', None)}")
except Exception as _e:
    check("age-months gate checks ran", False, repr(_e))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[PRETERM] The neonatal ceftriaxone contraindication is TWO-PART.")
print("    Web-verified 2026-08-03: contraindicated in PREMATURE infants up to")
print("    41 weeks POSTMENSTRUAL age — roughly three chronological months for")
print("    a 28-weeker — and in TERM neonates (<=28 days) who are")
print("    hyperbilirubinaemic or receiving IV calcium. A single postnatal")
print("    cutoff cannot express the first half, and this engine holds no")
print("    gestational-age field, so months 1-2 carry a caution asking the")
print("    prescriber to check rather than silently clearing the drug.")
# ═══════════════════════════════════════════════════════════════════════════
try:
    _NR = NS.get("NEONATAL_RESTRICTIONS", {})
    _cro = _NR.get("Ceftriaxone", {})
    check("the ceftriaxone rule records a preterm caution window",
          _cro.get("preterm_caution_months") == 3 and _cro.get("preterm_reason"),
          f"preterm_caution_months={_cro.get('preterm_caution_months')}")

    def _cro_state(months):
        a, w, b, p, _i = analyze(["Ceftriaxone", "Cefotaxime", "Meropenem"],
                                 "E. coli", "Blood", 0, "Male", False, None,
                                 False, False, [],
                                 {"Ceftriaxone": "S", "Cefotaxime": "S",
                                  "Meropenem": "S"}, "A", months)
        if "Ceftriaxone" in {x.get("name") for x in a}: return "allowed"
        if "Ceftriaxone" in {x.get("name") for x in w}: return "warned"
        return "banned"

    _pt = []
    if _cro_state(0) != "banned":
        _pt.append("0 mo: term neonate must be BANNED")
    for _m in (1, 2):
        if _cro_state(_m) != "warned":
            _pt.append(f"{_m} mo: expected a preterm caution, got {_cro_state(_m)}")
    for _m in (3, 6, 11):
        if _cro_state(_m) != "allowed":
            _pt.append(f"{_m} mo: past the preterm window, expected allowed, "
                       f"got {_cro_state(_m)}")
    check("ceftriaxone: banned at term-neonate, cautioned 1-2 mo, clear from 3 mo",
          not _pt, "\n".join(_pt))
except Exception as _e:
    check("preterm ceftriaxone checks ran", False, repr(_e))

# ═══════════════════════════════════════════════════════════════════════════
print("\n[SIGNED] Clinical data that carries a countersignature must keep it.")
# ═══════════════════════════════════════════════════════════════════════════
try:
    from abx_guidelines import ABX_GUIDELINES as _AG
    _signed = [d for d, i in _AG.items() if i.get("dose_countersigned")]
    _pending = [d for d, i in _AG.items() if i.get("dose_review")]
    _both = [d for d, i in _AG.items()
             if i.get("dose_review") and i.get("dose_countersigned")]

    # A row must never hold BOTH: that is a signature and a pending flag on the
    # same milligrams, and whichever a reader believes, the other is a lie.
    check("no dose band is both signed and pending", not _both, f"{_both}")

    # HARD: a signature must never disappear. Sixteen bands were countersigned
    # on 2026-08-03; if that count drops, someone deleted a signature rather
    # than earning one, and that is a regression the build must refuse.
    check("no previously countersigned dose band has lost its signature",
          len(_signed) >= 16,
          f"signed = {len(_signed)}, expected at least 16")

    # SOFT: newly added agents legitimately arrive unsigned. This is REPORTED
    # loudly and does not fail the build, on purpose. Failing it would push a
    # developer to delete the `dose_review` key to get green — which converts a
    # visible gap into an invisible one. The queue is the governance artefact;
    # `python test_dose_adjustment.py --queue` lists it, and a release must not
    # ship while it is non-empty.
    if _pending:
        print(f"\n  ⚠ {len(_pending)} dose band(s) AWAIT a clinician's signature")
        print(f"    {', '.join(sorted(_pending))}")
        print("    These are NOT a build failure — they are newly added agents.")
        print("    They ARE a release blocker. Run --queue and get them signed.")
    import guideline_registry as _GRg
    _unsigned = [k for k, v in _GRg.RULES.items()
                 if not str(v.get("countersigned_by", "")).strip()]
    check("every guideline rule carries a clinician countersignature",
          not _unsigned, f"unsigned: {_unsigned[:6]}")
except Exception as _e:
    check("countersignature checks ran", False, repr(_e))

print("\n" + "=" * 72)
print(f"{len(_PASS)} passed, {len(_FAIL)} failed")
if _FAIL:
    print("\nFAILED:")
    for f in _FAIL:
        print(f"  - {f}")
    print("\nRESULT: attention required")
    if __name__ == "__main__":
        sys.exit(1)
print("\nRESULT: ALL GREEN")
print("\nNOTE: this proves the CODE matches the TABLES. It does NOT prove the")
print("      TABLES match EUCAST v16 / CLSI M100 Ed36 — see guideline_registry.py,")
print("      where guideline_registry.py's own 'awaiting human' count (see")
print("      test_guidelines.py) tracks who still needs a clinician's countersignature.")
if __name__ == "__main__":
    sys.exit(0)
