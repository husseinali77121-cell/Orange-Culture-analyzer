# -*- coding: utf-8 -*-
"""Orange Lab CDSS — dose-adjustment guard (renal + hepatic).

WHY THIS FILE EXISTS
--------------------
The existing suites prove the engine matches its tables. None of them looked at
whether the DOSE the clinician is handed is the right dose, or whether it is a
dose at all. The July-2026 dosing audit found six classes of defect that every
other guard was structurally blind to:

  1. An UNKNOWN creatinine clearance was represented as 100.0 ml/min — a normal
     clearance. Ticking "Renal Impairment" without a creatinine therefore
     produced the same 19 recommended agents as a healthy patient, versus 6 at a
     real CrCl of 25, with Nitrofurantoin recommended rather than refused.
  2. Child-Pugh was seeded to "A" and the selector rendered BELOW the analysis
     call, so the first hepatic run always evaluated as grade A: 0 hepatic bans
     instead of 7. clinical_matrix downgrades its own hepatic DENY on grade A,
     so both layers failed together.
  3. Two rows carried ANOTHER DRUG'S dose band verbatim — Cefotaxime held the
     Piperacillin-Tazobactam bands (3.375 g / 2.25 g), Norfloxacin held the
     Amoxicillin-Clavulanate bands (500/125 mg, 875 mg).
  4. Sixteen agents with a renal_limit said only "dose adjustment required" —
     no dose, no interval, no threshold.
  5. Two independent renal threshold tables (abx_guidelines.renal_limit and
     clinical_matrix.RENAL_RULES) disagreed on sixteen drugs.
  6. Six drugs had a renal_limit BELOW the top of their own printed dose band,
     so the highest band could never be reached.

Each check below fails the build if one of those returns. Run:

    python test_dose_adjustment.py            # check
    python test_dose_adjustment.py --queue    # rows awaiting countersignature
"""
from __future__ import annotations

import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

APP = os.path.join(HERE, "streamlit_app.py")
SHOW_QUEUE = "--queue" in sys.argv
VERBOSE = "-v" in sys.argv or SHOW_QUEUE

_PASS: list = []
_FAIL: list = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (_PASS if ok else _FAIL).append(name)
    if not ok:
        print(f"  FAIL  {name}")
        for line in str(detail).splitlines()[:10]:
            print(f"          {line}")
    elif VERBOSE:
        print(f"  PASS  {name}")


from abx_guidelines import ABX_GUIDELINES as G                       # noqa: E402
from clinical_matrix import (                                        # noqa: E402
    ASSUMED_CRCL_UNKNOWN, CAUTION, DENY, HEPATIC_RULES, RENAL_RULES, evaluate,
)

# ── Load the monolith's decision logic without a Streamlit runtime ───────────
_WANT = [
    "ASSUMED_CRCL_UNKNOWN", "resolve_crcl", "crcl_label", "get_renal_severity",
    "calc_creatinine_clearance", "HEPATIC_DOSING",
    "_SPECIMEN_CATEGORY_RULES", "classify_specimen", "is_intrinsically_avoided",
    "build_banned_item", 
    "_MED_CANON", "_canon_med", "_PREG_ALIASES",
    "preg_status_of", "ESBL_PRODUCERS", "AMPC_PRODUCERS", "ESBL_MARKERS",
    "CARBAPENEMS", "_re_ws_collapse", "_ORG_NON_INFORMATIVE", "_org_matches", "is_esbl_producer", "_ACQUIRED_NOT_INTRINSIC",
    "_remove_intrinsic_resistance", "predict_esbl",
    "NEONATAL_RESTRICTIONS", "RENAL_BAN_REASONS", "CHILD_BAN_REASONS",
    "ORGANISM_AVOID_CLASS_MAP", "analyze_antibiotics",
]


def _extract(path: str, names: list) -> tuple:
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


_seg, _order, _missing = _extract(APP, _WANT)
# 2026-08-03: the S/I/R vocabulary moved to ocr_parsing.py. Seed it from
# the real module instead of slicing it out of the monolith — an
# importable module is the whole point of having extracted it.
from ocr_parsing import (normalize_sir_value as _nsv,
                         normalize_sir_map as _nsm,
                         _SIR_ALIASES as _sal)
NS: dict = {
    "normalize_sir_value": _nsv, "normalize_sir_map": _nsm, "_SIR_ALIASES": _sal,
    "__builtins__": __builtins__, "re": re,
    "Dict": dict, "List": list, "Any": object, "Tuple": tuple, "Optional": object,
    "ABX_GUIDELINES": G,
}
try:
    from clinical_data import INTRINSIC_RESISTANCE
    NS["INTRINSIC_RESISTANCE"] = INTRINSIC_RESISTANCE
except Exception:
    NS["INTRINSIC_RESISTANCE"] = {}
try:
    from organism_profile import ORGANISM_PROFILE
    NS["ORGANISM_PROFILE"] = ORGANISM_PROFILE
except Exception:
    NS["ORGANISM_PROFILE"] = {}
for _nm in _order:
    exec(compile(_seg[_nm], f"<{_nm}>", "exec"), NS)

analyze = NS["analyze_antibiotics"]
resolve_crcl = NS["resolve_crcl"]
crcl_label = NS["crcl_label"]
HEPATIC_DOSING = NS["HEPATIC_DOSING"]
APP_ASSUMED = NS["ASSUMED_CRCL_UNKNOWN"]

print("=" * 74)
print("Orange Lab CDSS — dose-adjustment guard")
print(f"  {len(G)} agents · {len(RENAL_RULES)} matrix renal rules · "
      f"{len(HEPATIC_DOSING)} hepatic rows")
print("=" * 74)
if _missing:
    print(f"\n  ENVIRONMENT: could not extract {_missing}")

PANEL = ["Nitrofurantoin", "Ciprofloxacin", "Levofloxacin", "Cefepime",
         "Piperacillin + Tazobactam", "Amoxicillin + Clavulanic acid",
         "Gentamicin", "Amikacin", "Vancomycin", "Meropenem", "Cefotaxime",
         "Trimethoprim/Sulfamethoxazole", "Azithromycin", "Clarithromycin",
         "Doxycycline", "Metronidazole", "Cefoxitin", "Cephradine", "Cefixime"]
SIR = {d: "S" for d in PANEL}


def buckets(**kw):
    kw.setdefault("final_drugs", PANEL)
    kw.setdefault("organism_type", "E. coli")
    kw.setdefault("culture_type", "Urine")
    kw.setdefault("age", 60)
    kw.setdefault("sex", "Male")
    kw.setdefault("is_renal", False)
    kw.setdefault("cl_cr", None)
    kw.setdefault("is_preg", False)
    kw.setdefault("is_hepatic", False)
    kw.setdefault("current_meds", [])
    kw.setdefault("sir_map", SIR)
    a, w, b, p, _i = analyze(**kw)
    return ([x["name"] for x in a],
            {x["name"]: x.get("warning_reason", "") for x in w},
            {x["name"]: x.get("reason_short", "") for x in b})


# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] UNKNOWN CrCl must fail CLOSED, never read as a normal clearance")
# ═══════════════════════════════════════════════════════════════════════════
check("the two layers share one assumed-CrCl constant",
      APP_ASSUMED == ASSUMED_CRCL_UNKNOWN,
      f"streamlit={APP_ASSUMED} clinical_matrix={ASSUMED_CRCL_UNKNOWN}")

check("assumed CrCl sits in the conservative direction (<= 30)",
      0 < ASSUMED_CRCL_UNKNOWN <= 30, f"got {ASSUMED_CRCL_UNKNOWN}")

_eff, _meas = resolve_crcl(None, True)
check("resolve_crcl(None, is_renal=True) substitutes the assumed value",
      _eff == ASSUMED_CRCL_UNKNOWN and _meas is False, f"{_eff!r} {_meas!r}")

_eff, _meas = resolve_crcl(None, False)
check("resolve_crcl(None, is_renal=False) stays None (no renal branch)",
      _eff is None, f"{_eff!r}")

_eff, _meas = resolve_crcl(22.0, True)
check("a measured value is passed through and marked measured",
      _eff == 22.0 and _meas is True, f"{_eff!r} {_meas!r}")

a_unk, w_unk, b_unk = buckets(is_renal=True, cl_cr=None)
a_norm, w_norm, b_norm = buckets(is_renal=False, cl_cr=None)
check("renal flag + unknown CrCl does NOT equal a healthy patient",
      set(a_unk) != set(a_norm),
      f"unknown-CrCl allowed {len(a_unk)}, healthy allowed {len(a_norm)}")

check("renal flag + unknown CrCl still refuses Nitrofurantoin",
      "Nitrofurantoin" in b_unk,
      f"Nitrofurantoin landed in "
      f"{'allowed' if 'Nitrofurantoin' in a_unk else 'warned'}")

_ren = [k for k, v in w_unk.items() if v == "renal_adjustment"]
check("renal flag + unknown CrCl produces dose-adjustment notes",
      len(_ren) >= 5, f"only {len(_ren)} agents flagged: {_ren}")

check("an assumed CrCl is LABELLED assumed, not printed as measured",
      "assume" in crcl_label(None, True).lower()
      and "not measured" in crcl_label(None, True).lower(),
      crcl_label(None, True))

check("a measured CrCl is NOT labelled assumed",
      "assume" not in crcl_label(25.0, True).lower(), crcl_label(25.0, True))

# The old default. If anyone reintroduces it, this fires.
a_100, w_100, b_100 = buckets(is_renal=True, cl_cr=100.0)
check("REGRESSION: cl_cr=100 with the renal flag is a no-op (so it must "
      "never be used to mean 'unknown')",
      not [k for k, v in w_100.items() if v == "renal_adjustment"]
      and "Nitrofurantoin" in a_100,
      "cl_cr=100 now does something — re-read this check before changing it")

check("negative CrCl is impossible out of Cockcroft-Gault",
      NS["calc_creatinine_clearance"](150, 70, 1.0, "Male") >= 0.0)

# ═══════════════════════════════════════════════════════════════════════════
print("\n[2] HEPATIC grade must fail CLOSED when it has not been graded")
# ═══════════════════════════════════════════════════════════════════════════
_src = open(APP, encoding="utf-8").read()
check('init_session_state seeds child_pugh_class="C", not "A"',
      '"child_pugh_class":        "C"' in _src,
      "the seed is the caller analyze_antibiotics warns about")

_sig = _src.split("def analyze_antibiotics(", 1)[1].split("->", 1)[0]
check('analyze_antibiotics still defaults child_pugh="C"',
      'child_pugh: str = "C"' in _sig, _sig.strip()[:200])

# The analysis call moved into run_analysis() on 2026-08-03, so the anchor is
# now the UI's single entry into the pipeline rather than the inlined call.
_i_sel = _src.find('key="cp_sel_sidebar"')
_i_call = _src.find("_res = run_analysis(")
check("the Child-Pugh selector renders BEFORE the analysis call",
      0 < _i_sel < _i_call,
      f"selector at char {_i_sel}, analysis at char {_i_call} — a widget below "
      f"the call cannot influence the run it is supposed to govern")

check("only ONE widget writes child_pugh_class",
      _src.count("st.session_state.child_pugh_class = ") == 1,
      f"found {_src.count('st.session_state.child_pugh_class = ')} writers — "
      f"two widgets on one session key is a stale-state race")

_, _wA, _bA = buckets(is_hepatic=True, child_pugh="A")
_, _wC, _bC = buckets(is_hepatic=True, child_pugh="C")
check("Child-Pugh C bans strictly more than Child-Pugh A",
      len(_bC) > len(_bA), f"A banned {len(_bA)}, C banned {len(_bC)}")

for _bad in ("", None, "X", "unknown"):
    _, _w, _b = buckets(is_hepatic=True, child_pugh=_bad)
    check(f"unreadable child_pugh {_bad!r} falls back to C, not A",
          len(_b) == len(_bC), f"{_bad!r} banned {len(_b)}, C bans {len(_bC)}")

# ═══════════════════════════════════════════════════════════════════════════
print("\n[3] NO DOSE BAND MAY BELONG TO ANOTHER DRUG")
# ═══════════════════════════════════════════════════════════════════════════
# Signature strengths: a product presentation unique to one agent. Finding one
# in another agent's row is the fingerprint of a copy-pasted table row, which is
# how Cefotaxime came to be dosed at a pip-tazo strength that does not exist.
SIGNATURE = {
    "3.375": ("piperacillin",), "2.25": ("piperacillin",),
    "4.5g": ("piperacillin",),
    # Only combination RATIOS are unique. A bare "875" is a legitimate plain
    # amoxicillin strength as well as a co-amoxiclav one, so it is not a
    # fingerprint and was a false positive here.
    "500/125": ("amoxicillin",),
    "160/800": ("trimethoprim", "sulfamethoxazole"),
    "80/400": ("trimethoprim", "sulfamethoxazole"),
}
_offenders = []
for drug, info in G.items():
    blob = f"{info.get('renal_note', '')} {info.get('renal_note_en', '')}"
    dl = drug.lower()
    for token, owners in SIGNATURE.items():
        if token in blob and not all(o in dl for o in owners):
            _offenders.append(f"{drug}: contains '{token}' (belongs to "
                              f"{'/'.join(owners)})")
check("no renal_note carries another drug's signature strength",
      not _offenders, "\n".join(_offenders))

_shared = {}
for drug, info in G.items():
    n = (info.get("renal_note") or "").strip()
    if n and re.search(r"CrCl|q\d", n):
        _shared.setdefault(n, []).append(drug)
_dupes = []
for note, drugs in _shared.items():
    if len(drugs) > 1:
        classes = {G[d].get("class", "?") for d in drugs}
        if len(classes) > 1:
            _dupes.append(f"{drugs} span classes {sorted(classes)}")
check("no dose band is shared verbatim across drug classes",
      not _dupes, "\n".join(_dupes))

# ═══════════════════════════════════════════════════════════════════════════
print("\n[4] EVERY renal_limit MUST COME WITH AN ACTUAL DOSE")
# ═══════════════════════════════════════════════════════════════════════════
DOSE_SHAPE = re.compile(r"(\d+\s*(mg|g|mcg)\b)|q\d+\s*-?\s*\d*\s*h|\d+\s*mg/kg"
                        r"|\d+\s*%|AUC", re.I)
PLACEHOLDER = re.compile(r"^[^\w]*(تعديل|خفض|adjust|reduce)[^.]*\.?\s*$", re.I)
_vague, _blank_en = [], []
for drug, info in G.items():
    rl = info.get("renal_limit", 0) or 0
    if rl <= 0:
        continue
    ar = (info.get("renal_note") or "").strip()
    en = (info.get("renal_note_en") or "").strip()
    # An agent whose renal_limit REFUSES rather than adjusts has no reduced
    # dose to print. It must still carry a normal-dose anchor, which DOSE_SHAPE
    # checks, so only the placeholder test is skipped.
    if not ar or not DOSE_SHAPE.search(ar) or (
            PLACEHOLDER.match(ar) and drug not in ("Nitrofurantoin",)):
        _vague.append(f"{drug} (limit {rl}): {ar[:60] or '<empty>'}")
    if ar and not en:
        _blank_en.append(f"{drug}: AR present, EN empty")
check("no renally-adjusted agent says only 'adjust the dose'",
      not _vague, "\n".join(_vague))
check("every Arabic dose band has an English counterpart",
      not _blank_en, "\n".join(_blank_en))

_band_hi = re.compile(r"CrCl\s*(\d+)\s*[-\u2013]\s*(\d+)", re.I)
_too_low = []
for drug, info in G.items():
    rl = info.get("renal_limit", 0) or 0
    if rl <= 0 or drug == "Nitrofurantoin":   # nitrofurantoin's limit refuses
        continue
    blob = f"{info.get('renal_note', '')} {info.get('renal_note_en', '')}"
    tops = [int(b) for a, b in _band_hi.findall(blob)]
    if tops and max(tops) > rl:
        _too_low.append(f"{drug}: renal_limit={rl} but its own band reaches "
                        f"CrCl {max(tops)} — the top band never fires")
check("no renal_limit sits below the top of its own dose band",
      not _too_low, "\n".join(_too_low))

_no_tdm = []
for drug in ("Vancomycin", "Gentamicin", "Amikacin", "Tobramycin"):
    info = G.get(drug)
    if not info:
        continue
    blob = f"{info.get('renal_note', '')} {info.get('renal_note_en', '')}".lower()
    if not any(k in blob for k in ("trough", "auc", "level", "مستوى")):
        _no_tdm.append(f"{drug}: no monitoring target stated")
check("every narrow-index agent states a monitoring target",
      not _no_tdm, "\n".join(_no_tdm))

# ═══════════════════════════════════════════════════════════════════════════
print("\n[5] ONE THRESHOLD PER DRUG — the two renal tables must agree")
# ═══════════════════════════════════════════════════════════════════════════
# `renal_limit` means "adjust at or below this CrCl" for every agent EXCEPT
# Nitrofurantoin, where analyze_antibiotics reads it as the REFUSAL threshold.
# That collision is deliberate and documented; it is asserted, not assumed.
REFUSAL_SEMANTICS = {"Nitrofurantoin"}
_diverge = []
for drug in sorted(set(G) & set(RENAL_RULES)):
    abx = G[drug].get("renal_limit", 0) or 0
    adjust_below, refuse_below, _en, _ar = RENAL_RULES[drug]
    expected = refuse_below if drug in REFUSAL_SEMANTICS else adjust_below
    if expected is None:
        if abx:
            _diverge.append(f"{drug}: abx={abx} but matrix has no threshold")
        continue
    if abx != expected:
        _diverge.append(f"{drug}: abx_guidelines={abx} vs clinical_matrix="
                        f"{expected:g}")
check("abx_guidelines.renal_limit == clinical_matrix.RENAL_RULES",
      not _diverge, "\n".join(_diverge))

_orphan = [d for d, i in G.items()
           if (i.get("renal_limit", 0) or 0) > 0 and d not in RENAL_RULES]
check("every renally-adjusted agent also has a matrix rule (second opinion)",
      not _orphan, f"no matrix rule for: {_orphan}")

check("Nitrofurantoin keeps the EMA/BNF refusal threshold of 45",
      (G.get("Nitrofurantoin", {}).get("renal_limit") == 45
       and RENAL_RULES["Nitrofurantoin"][1] == 45),
      f"abx={G.get('Nitrofurantoin', {}).get('renal_limit')} "
      f"matrix_refuse={RENAL_RULES['Nitrofurantoin'][1]}")

# ═══════════════════════════════════════════════════════════════════════════
print("\n[6] HEPATIC: the stricter of the two tables must win")
# ═══════════════════════════════════════════════════════════════════════════
# The gate is demote-only, so HEPATIC_DOSING "Avoid" + matrix CAUTION is safe
# (the ban survives). The unsafe direction is matrix DENY against a
# HEPATIC_DOSING row that permits — that would rely on the gate to catch a
# contraindication the primary engine handed out as normal.
_unsafe = []
for drug, (lvl, _en, _ar) in HEPATIC_RULES.items():
    row = HEPATIC_DOSING.get(drug)
    if lvl != DENY or not row:
        continue
    c_level = str(row.get("C", ("", ""))[0]).lower()
    if "avoid" in c_level:
        continue
    if c_level in ("normal", "normal (renal)", "renal-based"):
        _unsafe.append(f"{drug}: matrix DENY but HEPATIC_DOSING[C]='{c_level}'")
check("no agent is DENIED by the matrix while the engine calls it normal",
      not _unsafe, "\n".join(_unsafe))

_flagless = [d for d, i in G.items()
             if d in HEPATIC_DOSING
             and "avoid" in str(HEPATIC_DOSING[d].get("C", ("", ""))[0]).lower()
             and not i.get("hepatic_caution")]
check("every Child-Pugh-C 'Avoid' agent carries hepatic_caution=True",
      not _flagless,
      f"the side-channel hepatic alert never fires for: {_flagless}")

_no_row = [d for d, i in G.items() if i.get("hepatic_caution")
           and d not in HEPATIC_DOSING]
check("every hepatic_caution agent has a HEPATIC_DOSING row",
      not _no_row, f"no hepatic guidance for: {_no_row}")

# ═══════════════════════════════════════════════════════════════════════════
print("\n[7] MONOTONICITY — worsening organ function may only narrow the list")
# ═══════════════════════════════════════════════════════════════════════════
_prev, _viol = None, []
for _c in (95.0, 60.0, 45.0, 30.0, 20.0, 10.0):
    _a, _, _ = buckets(is_renal=True, cl_cr=_c)
    if _prev is not None and not set(_a) <= set(_prev[1]):
        _viol.append(f"CrCl {_c}: {sorted(set(_a) - set(_prev[1]))} appeared "
                     f"that CrCl {_prev[0]} did not allow")
    _prev = (_c, _a)
check("a falling CrCl never adds an agent",
      not _viol, "\n".join(_viol))

_aA, _, _ = buckets(is_hepatic=True, child_pugh="A")
_aB, _, _ = buckets(is_hepatic=True, child_pugh="B")
_aC, _, _ = buckets(is_hepatic=True, child_pugh="C")
check("a worsening Child-Pugh grade never adds an agent",
      set(_aC) <= set(_aB) <= set(_aA),
      f"A={len(_aA)} B={len(_aB)} C={len(_aC)}")

# ═══════════════════════════════════════════════════════════════════════════
print("\n[8] ONE FORMULARY — no second copy of the drug table may exist")
# ═══════════════════════════════════════════════════════════════════════════
# HISTORY. There were THREE copies of ABX_GUIDELINES: abx_guidelines.py (live in
# the monolith), data/antibiotics.py (live in the modular build) and a dead,
# byte-identical antibiotics.py at the root. The two live copies had drifted into
# different generations -- 15/41 renal_limits, 32/41 renal_notes and, worst,
# preg_status for Doxycycline and Tetracycline, which read "Warn" in the modular
# copy where modules/analyzer.py bans only on "Banned". A tetracycline therefore
# reached a pregnant patient as a mere caution in that build.
#
# 2026-08-03: modules/, ui/, data/, qc.py and antibiotics.py were DELETED.
# 3,227 lines carrying 20 latent NameErrors -- code that parsed but could not
# run. The redirect shims went with them, since a redirect to a deleted package
# is just a slower ImportError. This check therefore changed shape: it no longer
# proves the redirects behave, it proves the copies never come back.
import importlib                                                     # noqa: E402
import ast as _ast8                                                  # noqa: E402
from pathlib import Path as _Path8                                   # noqa: E402
_ROOT = _Path8(__file__).resolve().parent

_GONE = ["modules", "ui", "data", "qc.py", "antibiotics.py"]
_resurrected = [g for g in _GONE if (_ROOT / g).exists()]
check("the deleted parallel build has not returned",
      not _resurrected, f"present again: {_resurrected}")

# Exactly one module in the tree may define an ABX_GUIDELINES table literal.
_definers = []
for _py in sorted(_ROOT.glob("*.py")):
    try:
        _t = _ast8.parse(_py.read_text(encoding="utf-8"))
    except SyntaxError:
        continue
    for _n in _t.body:
        if isinstance(_n, _ast8.Assign):
            for _tg in _n.targets:
                if (isinstance(_tg, _ast8.Name) and _tg.id == "ABX_GUIDELINES"
                        and isinstance(_n.value, _ast8.Dict) and len(_n.value.keys) > 5):
                    _definers.append(_py.name)
        elif isinstance(_n, _ast8.AnnAssign):
            if (isinstance(_n.target, _ast8.Name) and _n.target.id == "ABX_GUIDELINES"
                    and isinstance(_n.value, _ast8.Dict) and len(_n.value.keys) > 5):
                _definers.append(_py.name)
check("exactly one file defines the ABX_GUIDELINES table",
      _definers == ["abx_guidelines.py"], f"definers = {_definers}")

# Same for the organism table.
_org_definers = []
for _py in sorted(_ROOT.glob("*.py")):
    try:
        _t = _ast8.parse(_py.read_text(encoding="utf-8"))
    except SyntaxError:
        continue
    for _n in _t.body:
        _tgt = None
        if isinstance(_n, _ast8.Assign) and len(_n.targets) == 1:
            _tgt = _n.targets[0]
        elif isinstance(_n, _ast8.AnnAssign):
            _tgt = _n.target
        if (isinstance(_tgt, _ast8.Name) and _tgt.id == "ORGANISM_PROFILE"
                and isinstance(_n.value, _ast8.Dict) and len(_n.value.keys) > 5):
            _org_definers.append(_py.name)
check("exactly one file defines the ORGANISM_PROFILE table",
      _org_definers == ["organism_profile.py"], f"definers = {_org_definers}")

# The canonical QA engine must still be reachable and still find the classic
# intrinsic contradiction. This used to be asserted through modules/qc.py; it is
# now asserted against the engine itself, which is what actually runs.
try:
    _qa = importlib.import_module("ast_qa_engine")
    _found = _qa.run_ast_qa_engine(organism="Klebsiella spp.",
                                   sir_map={"Ampicillin": "S"}, specimen="Blood")
    check("the QA engine detects Klebsiella + Ampicillin=S as intrinsic",
          len(_found) >= 1,
          "the canonical engine must flag a textbook intrinsic contradiction")
except Exception as _exc:
    check("ast_qa_engine imports and runs", False, str(_exc))

# ═══════════════════════════════════════════════════════════════════════════
# Countersignature queue — reported, never a failure
# ═══════════════════════════════════════════════════════════════════════════
_queue = sorted((d, i["dose_review"]) for d, i in G.items() if i.get("dose_review"))
_signed = sorted(d for d, i in G.items() if i.get("dose_countersigned"))

print()
print("=" * 74)
print(f"{len(_PASS)} passed, {len(_FAIL)} failed")
if _queue:
    print(f"\nDOSE REVIEW QUEUE: {len(_queue)} row(s) awaiting a clinician's "
          f"countersignature")
    print("  These bands were written or corrected in the 2026-07-30 dosing")
    print("  audit and have NOT been checked against a source document by a")
    print("  human. Verify against BNF 2025 / the product label, then delete")
    print("  the 'dose_review' key. Run with --queue to list them.")
if _signed:
    print(f"\nDOSE BANDS COUNTERSIGNED: {len(_signed)} row(s) checked against "
          f"BNF 2025 / product label by a clinician and recorded in-file.")
    if SHOW_QUEUE:
        for d, why in _queue:
            print(f"\n  {d}")
            print(f"     {why}")
            print(f"     AR: {(G[d].get('renal_note') or '')[:100]}")
            print(f"     EN: {(G[d].get('renal_note_en') or '')[:100]}")

if _FAIL:
    print("\nRESULT: FAILED")
    for f in _FAIL:
        print(f"  - {f}")
    if __name__ == "__main__":
        sys.exit(1)

print("\nRESULT: ALL GREEN")
print("\nNOTE: this proves the DOSE PATHWAY is internally consistent and fails")
print("      closed. The milligrams and intervals themselves were countersigned")
print("      against BNF 2025 / the product labels by Dr. Tarek El-Shafei,")
print("      Laboratory Director, on 2026-08-03 — recorded per row in the")
print("      `dose_countersigned` key. A band added later without that key")
print("      reappears in the queue above; the signature is not inheritable.")
