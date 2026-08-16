#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_render_layer.py — proofs about what actually reaches the screen.

WHY THIS FILE EXISTS
Every other suite in this repository tests the ENGINE: which bucket a drug lands
in, whether a table row is reachable, whether two engines agree. None of them
tested the RENDER LAYER, and on 2026-08-01 that gap held two live defects:

  1. Safety-gate moves rendered with an EMPTY reason. safety_gate.py emitted the
     key "why"; the renderer read `reason_ar or reason or ''`. Neither key
     existed, so 33 of 33 moves printed "Drug: allowed → banned — ".

  2. Warned items rendered the WRONG note. The renderer was two branches — ESBL
     notes, else `renal_note` — and every warned item carries `**info` spread
     from ABX_GUIDELINES, so `renal_note` was always populated. The else branch
     therefore never printed nothing; it printed something fluent and false:

         Child-Pugh C warning  -> "CrCl <30: خفض الجرعة 50%…"
         CSF gate demotion     -> "🟢 لا تعديل كلوي مطلوب"

     The second one is the dangerous shape. The gate had just refused oxacillin
     for not crossing the blood-brain barrier in meningitis, and the line under
     it read "no renal adjustment required" — reassurance in place of a refusal.

  3. Neonatal warnings were built without `**info` and without a
     `warning_reason`, so the renderer had nothing to switch on at all.

An engine that reaches the right verdict and then prints someone else's
explanation next to it is not safer than an engine that gets it wrong — the
clinician acts on the sentence, not on the bucket.

Run:  python test_render_layer.py
      python test_render_layer.py --verbose
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VERBOSE = "--verbose" in sys.argv
if HERE not in sys.path:
    sys.path.insert(0, HERE)

_PASS: list[str] = []
_FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (_PASS if ok else _FAIL).append(name)
    if not ok:
        print(f"  FAIL  {name}")
        for line in str(detail).splitlines()[:12]:
            print(f"          {line}")
    elif VERBOSE:
        print(f"  PASS  {name}")


# ═══════════════════════════════════════════════════════════════════════════
# Load the app without a Streamlit runtime, reusing the house AST-extraction
# pattern. Only the decision + resolver layer is needed here.
# ═══════════════════════════════════════════════════════════════════════════
import ast  # noqa: E402

APP = os.path.join(HERE, "streamlit_app.py")
if not os.path.exists(APP):
    print(f"ENVIRONMENT INCOMPLETE — {APP} not found.")
    sys.exit(2)


def _extract(path: str, names: list[str]):
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
    "_re_ws_collapse", "_ORG_NON_INFORMATIVE", "_org_matches", "is_esbl_producer", "predict_esbl",
    "MDR_CATEGORIES", "MDR_CATEGORIES_GRAM_NEG", "MDR_CATEGORIES_GRAM_POS",
    "GRAM_POSITIVE_ORGANISMS", "_remove_intrinsic_resistance", "classify_mdr",
    "MDR_INFO", "HEPATIC_DOSING", "warned_note_for", "analyze_antibiotics",
    "COMBINATION_THERAPY", "_COMBO_HOST_FLAGS", "get_combination_therapy",
    "_hide_urine_only",
]

from abx_guidelines import ABX_GUIDELINES as G                      # noqa: E402
from organism_profile import ORGANISM_PROFILE as OP                 # noqa: E402
from specimen_organism_map import (                                 # noqa: E402
    SPECIMEN_ORDER, get_organisms_for_specimen,
)
import re as _re                                                     # noqa: E402

_seg, _order, _missing = _extract(APP, _WANT)
# 2026-08-03: the S/I/R vocabulary moved to ocr_parsing.py. Seed it from
# the real module instead of slicing it out of the monolith — an
# importable module is the whole point of having extracted it.
from ocr_parsing import (normalize_sir_value as _nsv,
                         normalize_sir_map as _nsm,
                         _SIR_ALIASES as _sal)
NS: dict = {
    "normalize_sir_value": _nsv, "normalize_sir_map": _nsm, "_SIR_ALIASES": _sal,
    "__builtins__": __builtins__, "re": _re,
    "Dict": dict, "List": list, "Any": object, "Tuple": tuple, "Optional": object,
    "ABX_GUIDELINES": G, "ORGANISM_PROFILE": OP,
    "SPECIMEN_ORDER": SPECIMEN_ORDER,
    "get_organisms_for_specimen": get_organisms_for_specimen,
}
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
note_for = NS["warned_note_for"]
ORGS = list(OP)
SPECS = list(SPECIMEN_ORDER)

try:
    from safety_gate import apply_safety_gate
    GATE = True
except Exception:
    GATE = False


def pipeline(org, spec, sir, *, age=45, sex="Male", renal=False, crcl=None,
             preg=False, hep=False, cp="A", am=None):
    a, w, b, p, i = analyze(list(sir), org, spec, age, sex, renal, crcl, preg,
                            hep, [], sir, cp, am)
    rep = {}
    if GATE:
        a, w, b, rep = apply_safety_gate(
            a, w, b, organism=org, specimen=spec, sir_map=sir, age_years=age,
            is_pregnant=preg, cl_cr=crcl, is_renal=renal, is_hepatic=hep,
            child_pugh=cp)
    return a, w, b, p, rep


ALL_S = {d: "S" for d in G}

print("=" * 72)
print("Orange Lab CDSS — render layer")
print(f"  {len(G)} agents · {len(ORGS)} organisms · {len(SPECS)} specimens")
print("=" * 72)
if _missing:
    print(f"\n  WARNING: could not extract {_missing}")
if not GATE:
    print("  WARNING: safety_gate.py did not import — gate checks degraded")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] Every warned item renders a NON-EMPTY explanation.")
# ═══════════════════════════════════════════════════════════════════════════
_HOSTS = [
    ("healthy adult",   dict()),
    ("renal CrCl 25",   dict(renal=True, crcl=25)),
    ("renal CrCl 8",    dict(renal=True, crcl=8)),
    ("Child-Pugh C",    dict(hep=True, cp="C")),
    ("Child-Pugh B",    dict(hep=True, cp="B")),
    ("pregnant",        dict(preg=True, sex="Female", age=28)),
    ("neonate 0 m",     dict(age=0, am=0)),
    ("neonate unknown", dict(age=0, am=None)),
    ("child 5",         dict(age=5)),
    ("elderly 88",      dict(age=88)),
]
_ESBL = {"Ceftriaxone": "R", "Cefotaxime": "R", "Ceftazidime": "R"}

_empty, _reasons_seen = [], set()
for org in ORGS:
    for spec in SPECS:
        for label, kw in _HOSTS:
            sir = dict(ALL_S)
            if org in ("E. coli", "Klebsiella spp."):
                sir.update(_ESBL)
            _a, w, _b, _p, _rep = pipeline(org, spec, sir, **kw)
            for item in w:
                r = item.get("warning_reason")
                _reasons_seen.add(r)
                if r == "intermediate_culture":
                    continue          # rendered by its own dedicated banner
                if not note_for(item, "ar").strip():
                    _empty.append(f"{org}/{spec}/{label}: {item.get('name')} "
                                  f"[reason={r!r}] renders nothing")
check("no warned item renders an empty explanation", not _empty,
      "\n".join(_empty[:10]))
if VERBOSE:
    print(f"        warning_reason values exercised: {sorted(map(str, _reasons_seen))}")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[2] The explanation must belong to THIS warning — not to a neighbour.")
print("    The old renderer fell through to renal_note for every reason it did")
print("    not name, and renal_note is always populated, so a hepatic warning")
print("    printed renal dosing and a meningitis gate refusal printed")
print("    '🟢 no renal adjustment required'.")
# ═══════════════════════════════════════════════════════════════════════════
# A keyword scan is the wrong instrument here: the gate's own note for
# Colistin in urine legitimately discusses nephrotoxicity, and would trip any
# "mentions kidneys" filter. The precise question is whether the rendered text
# IS the renal_note field — that is the substitution, and it is exact.
_wrong_domain = []
for org in ("E. coli", "Staphylococcus aureus", "Streptococcus pneumoniae"):
    if org not in OP:
        continue
    for spec in ("Blood", "CSF", "Urine"):
        for label, kw in (("Child-Pugh C", dict(hep=True, cp="C")),
                          ("neonate unknown", dict(age=0, am=None)),
                          ("healthy", dict())):
            _a, w, _b, _p, _rep = pipeline(org, spec, dict(ALL_S), **kw)
            for item in w:
                r = item.get("warning_reason")
                if r in ("renal_adjustment", "intermediate_culture"):
                    continue
                shown = note_for(item, "ar").strip()
                renal = str(item.get("renal_note") or "").strip()
                if shown and renal and shown == renal:
                    _wrong_domain.append(
                        f"{org}/{spec}/{label}: {item.get('name')} [{r}] "
                        f"rendered the renal_note field verbatim -> {shown[:55]!r}")
check("a non-renal warning never renders the renal_note field", not _wrong_domain,
      "\n".join(_wrong_domain[:10]))

# The specific regression: the reassuring line under a meningitis refusal.
_reassure = []
_a, w, _b, _p, _rep = pipeline("Streptococcus pneumoniae", "CSF", dict(ALL_S))
for item in w:
    txt = note_for(item, "ar")
    if "لا تعديل كلوي مطلوب" in txt or "no renal adjustment" in txt.lower():
        _reassure.append(f"{item.get('name')} [{item.get('warning_reason')}]: {txt[:70]}")
check("a CSF safety-gate demotion never renders a reassuring renal note",
      not _reassure, "\n".join(_reassure[:6]))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[3] Safety-gate moves must render the reason the gate recorded.")
# ═══════════════════════════════════════════════════════════════════════════
if GATE:
    _blank_moves, _total = [], 0
    for org in ORGS:
        for spec in SPECS:
            for label, kw in (("healthy", dict()),
                              ("pregnant", dict(preg=True, sex="Female", age=28)),
                              ("CrCl 8", dict(renal=True, crcl=8)),
                              ("neonate", dict(age=0, am=0))):
                _a, _w, _b, _p, rep = pipeline(org, spec, dict(ALL_S), **kw)
                for m in (rep.get("moves") or []):
                    _total += 1
                    # exactly the expression the render layer evaluates
                    shown = (m.get("reason_ar") or m.get("why")
                             or m.get("reason_en") or "")
                    if not str(shown).strip():
                        _blank_moves.append(
                            f"{org}/{spec}/{label}: {m.get('drug')} "
                            f"{m.get('from')}→{m.get('to')} keys={sorted(m)}")
    check(f"no safety-gate move renders a blank reason ({_total} moves checked)",
          not _blank_moves, "\n".join(_blank_moves[:10]))

    # Producer/consumer contract, stated once so a rename on either side fails
    # here rather than silently blanking the panel.
    _a, _w, _b, _p, rep = pipeline("Streptococcus pneumoniae", "CSF", dict(ALL_S))
    _keys = set().union(*[set(m) for m in rep.get("moves", [{}])]) if rep.get("moves") else set()
    check("gate moves carry reason_ar / reason_en alongside why",
          {"why", "reason_ar", "reason_en"} <= _keys,
          f"move keys = {sorted(_keys)}")
else:
    print("  SKIP  safety_gate.py not importable")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[4] Every warned item carries a warning_reason at all.")
print("    Neonatal items were appended without `**info` and without a")
print("    warning_reason, so the renderer had nothing to switch on.")
# ═══════════════════════════════════════════════════════════════════════════
_no_reason = []
for org in ORGS:
    for spec in SPECS:
        for label, kw in _HOSTS:
            _a, w, _b, _p, _rep = pipeline(org, spec, dict(ALL_S), **kw)
            for item in w:
                if not item.get("warning_reason"):
                    _no_reason.append(f"{org}/{spec}/{label}: {item.get('name')} "
                                      f"category={item.get('category')!r}")
check("every warned item has a warning_reason", not _no_reason,
      "\n".join(_no_reason[:10]))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[5] Every banned item renders a reason and a detail.")
# ═══════════════════════════════════════════════════════════════════════════
_bad_ban = []
for org in ORGS:
    for spec in SPECS:
        for label, kw in _HOSTS:
            sir = dict(ALL_S)
            sir.update({"Ceftriaxone": "R", "Ciprofloxacin": "R"})
            _a, _w, b, _p, _rep = pipeline(org, spec, sir, **kw)
            for item in b:
                short = str(item.get("reason_short") or "").strip()
                if not short:
                    _bad_ban.append(f"{org}/{spec}/{label}: {item.get('name')} "
                                    f"[{item.get('category')}] has no reason_short")
check("no banned item renders without a reason", not _bad_ban,
      "\n".join(_bad_ban[:10]))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[6] warned_note_for handles every reason the engine can emit, and")
print("    never falls back to renal_note for an unknown one — that silent")
print("    substitution is the whole defect this resolver replaced.")
# ═══════════════════════════════════════════════════════════════════════════
_KNOWN = {"renal_adjustment", "hepatic_adjustment", "safety_gate", "neonate",
          "intermediate_culture", "esbl_bli_uti_only", "possible_carbapenemase",
          "interaction", "pregnancy"}
_unhandled = sorted(str(r) for r in _reasons_seen if r and r not in _KNOWN)
check("every warning_reason the engine emits has a resolver branch",
      not _unhandled, f"unhandled: {_unhandled}")

_probe = {"name": "X", "warning_reason": "some_future_reason",
          "renal_note": "CrCl <30: reduce by 50%"}
check("an unknown reason does NOT silently render renal_note",
      note_for(_probe, "ar") == "",
      f"rendered {note_for(_probe, 'ar')!r}")

_probe2 = {"name": "X", "warning_reason": "hepatic_adjustment",
           "hepatic_level": "Reduce 50%", "hepatic_rec": "halve the dose",
           "renal_note": "CrCl <30: reduce by 50%"}
_out = note_for(_probe2, "ar")
check("a hepatic warning renders hepatic text, not renal text",
      "halve the dose" in _out and "CrCl" not in _out, f"rendered {_out!r}")



# ═══════════════════════════════════════════════════════════════════════════
print("\n[7] STATIC — every keyword argument at a call site must exist in the")
print("    callee's signature. DEFECT 2026-08-03: a global rename that added")
print("    `age_months=` to the safety-gate calls also matched two")
print("    get_combination_therapy() calls, which take no such parameter. That")
print("    is a TypeError on the combination panel and on PDF export — and no")
print("    suite caught it, because every suite calls these functions directly")
print("    with correct arguments and never through the Streamlit UI path.")
print("    A signature check is cheap and covers the whole file.")
# ═══════════════════════════════════════════════════════════════════════════
import ast as _ast

_src = open(APP, encoding="utf-8").read()
_tree = _ast.parse(_src)

# Signatures of every function defined in this module.
_sig_of = {}
for _n in _ast.walk(_tree):
    if isinstance(_n, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
        _a = _n.args
        _names = {p.arg for p in _a.posonlyargs + _a.args + _a.kwonlyargs}
        _sig_of[_n.name] = (_names, _a.kwarg is not None)

# Signatures of the modules the app imports from and calls by bare name.
try:
    import safety_gate as _sg
    import inspect as _insp
    for _fn in ("apply_safety_gate",):
        _f = getattr(_sg, _fn, None)
        if _f:
            _p = _insp.signature(_f).parameters
            _sig_of[_fn] = ({k for k in _p},
                            any(v.kind == v.VAR_KEYWORD for v in _p.values()))
except Exception:
    pass

_badkw = []
for _n in _ast.walk(_tree):
    if not isinstance(_n, _ast.Call) or not isinstance(_n.func, _ast.Name):
        continue
    _target = _n.func.id
    if _target not in _sig_of:
        continue
    _accepted, _has_kwargs = _sig_of[_target]
    if _has_kwargs:
        continue
    for _kw in _n.keywords:
        if _kw.arg and _kw.arg not in _accepted:
            _badkw.append(f"line {_n.lineno}: {_target}({_kw.arg}=...) — "
                          f"not a parameter of {_target}")
check("no call site passes a keyword the callee does not accept",
      not _badkw, "\n".join(_badkw[:12]))

# The specific pair that broke, asserted by behaviour rather than by parse.
try:
    _gct = NS.get("get_combination_therapy")
    if _gct:
        _gct([], is_pregnant=False, age_years=30, age_months=None,
             is_renal=False, cl_cr=None, is_hepatic=False)
        _ok = True
    else:
        _ok = True
except TypeError as _e:
    _ok = False
    _detail = str(_e)
check("get_combination_therapy accepts the host context the UI passes it",
      _ok, locals().get("_detail", ""))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[9] The PDF and the screen must resolve a warning the SAME way.")
print("    DEFECT 2026-08-03: warned_note_for() fixed the screen; the PDF kept")
print("    its own if/else that fell through to the RENAL note for every reason")
print("    it did not name — hepatic, safety-gate, neonatal, possible-MRSA. One")
print("    defect, two renderers, one fixed. Both now use the one resolver.")
# ═══════════════════════════════════════════════════════════════════════════
_src9 = open(os.path.join(HERE, "report_service.py"), encoding="utf-8").read()
check("the PDF routes its fall-through branch through warned_note_for",
      "warned_note_for(_wd" in _src9,
      "the PDF still has its own fall-through — it will drift from the screen")
check("warned_note_for is wired into report_service via bind()",
      '"warned_note_for"' in _src9)


# ═══════════════════════════════════════════════════════════════════════════
print("\n[10] STATIC — the UI layer. 1,351 of this file's lines are Streamlit")
print("    calls that no test can execute without a browser, so they are")
print("    checked by reading rather than by running.")
print("    DEFECT 2026-08-03: st.session_state.get('patient_name') was read on")
print("    every internal QA report, and NOTHING in the file writes that key —")
print("    the name lives under patient_name_final. Every QA document since the")
print("    field was added carried a blank patient reference, and a QA document")
print("    that cannot be tied to its isolate is the one thing it exists for.")
print("    Third instance of the same shape: safety_gate emitted 'why' while")
print("    the renderer read 'reason_ar'; report_service needed warned_note_for")
print("    and had its own copy. A producer and a consumer naming one fact")
print("    differently is this codebase's most repeated defect.")
# ═══════════════════════════════════════════════════════════════════════════
import ast as _ast10

_t10 = _ast10.parse(open(APP, encoding="utf-8").read())
_written, _read = set(), set()
for _n in _ast10.walk(_t10):
    if (isinstance(_n, _ast10.Subscript) and isinstance(_n.value, _ast10.Attribute)
            and _n.value.attr == "session_state"
            and isinstance(_n.slice, _ast10.Constant)):
        (_written if isinstance(_n.ctx, _ast10.Store) else _read).add(_n.slice.value)
    if (isinstance(_n, _ast10.Call) and isinstance(_n.func, _ast10.Attribute)
            and _n.func.attr in ("get", "setdefault")
            and isinstance(_n.func.value, _ast10.Attribute)
            and _n.func.value.attr == "session_state" and _n.args
            and isinstance(_n.args[0], _ast10.Constant)):
        _read.add(_n.args[0].value)
    if (isinstance(_n, _ast10.Attribute) and isinstance(_n.value, _ast10.Attribute)
            and _n.value.attr == "session_state"):
        (_written if isinstance(_n.ctx, _ast10.Store) else _read).add(_n.attr)
# A literal in any dict counts as a write: the defaults table seeds the state.
for _n in _ast10.walk(_t10):
    if isinstance(_n, _ast10.Dict):
        for _k in _n.keys:
            if isinstance(_k, _ast10.Constant) and _k.value in _read:
                _written.add(_k.value)

_METHODS = {"get", "pop", "clear", "keys", "items", "values", "update", "setdefault"}
_ghost = sorted(_read - _written - _METHODS)
check("every session_state key that is READ is written somewhere",
      not _ghost,
      f"read but never written: {_ghost}\n"
      "Each of these silently returns its default forever.")

# Duplicate widget keys raise DuplicateWidgetID at runtime, in front of a user,
# on a page that cannot be tested here.
_wkeys = {}
_STATEFUL = {"text_input", "number_input", "selectbox", "multiselect", "radio",
             "checkbox", "slider", "text_area", "file_uploader", "date_input",
             "button", "form_submit_button", "download_button", "data_editor"}
for _n in _ast10.walk(_t10):
    if (isinstance(_n, _ast10.Call) and isinstance(_n.func, _ast10.Attribute)
            and _n.func.attr in _STATEFUL):
        for _kw in _n.keywords:
            if _kw.arg == "key" and isinstance(_kw.value, _ast10.Constant):
                _wkeys.setdefault(_kw.value.value, []).append(_n.lineno)
_dup = {k: v for k, v in _wkeys.items() if len(v) > 1}
check("no two widgets share a literal key",
      not _dup, f"{ {k: v for k, v in list(_dup.items())[:5]} }")

print("\n" + "=" * 72)
print(f"{len(_PASS)} passed, {len(_FAIL)} failed")
if _FAIL:
    print("\nRESULT: FAILURES — see above")
    sys.exit(1)
print("\nRESULT: ALL GREEN")
print("\nNOTE: this suite proves the right SENTENCE reaches the screen. It says")
print("      nothing about whether the verdict behind it is clinically correct")
print("      — that is test_engine_agreement.py and test_scenarios.py.")
