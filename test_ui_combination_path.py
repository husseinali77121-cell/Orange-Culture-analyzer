#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_ui_combination_path.py — the combination-therapy panel, walked the way
the UI and the PDF actually call it, not the way run_analysis() calls it.

WHY THIS FILE EXISTS
This is not a hypothetical. On 2026-08-21 a second-opinion audit of the
delivered zip found that streamlit_app.py's live Combination Therapy expander
(around "## Combination Therapy") and the PDF-export button both called

    get_combination_therapy(phenotypes, is_pregnant=..., age_years=..., ...)

without `organism=`, even though run_analysis() -- the function every other
test suite in this repo calls -- passes it correctly. get_combination_therapy()
has an entire block (`if organism and results:`) that annotates any option
naming a drug the organism is INTRINSICALLY resistant to (the exact
Colistin-vs-Proteus/Providencia/Morganella/Serratia defect fixed on
2026-08-06, per that function's own docstring). Omitting `organism=` at a
call site does not raise an error -- it just silently skips that block. Every
existing suite stayed green throughout, because every existing suite calls
the function directly with correct arguments and none of them walks the two
specific lines inside streamlit_app.py that render what a clinician actually
sees. Both call sites were fixed the same day this test was added.

WHAT THIS FILE PROVES, TWO WAYS (either one alone would have caught this)
  1. STATIC  -- every `get_combination_therapy(` call site in streamlit_app.py,
                other than the function's own def, passes `organism=`. This
                is the guard that survives a future refactor: if someone adds
                a THIRD call site and forgets the argument, this fails without
                needing to guess which clinical scenario would expose it.
  2. DYNAMIC -- the actual Proteus mirabilis / CRE / Colistin scenario, run
                through get_combination_therapy() exactly as the UI now
                calls it, produces the intrinsic-resistance annotation; the
                same call WITHOUT organism (the pre-fix pattern) does not --
                proving the static check above is guarding something real,
                not a stylistic preference.

Run:  python test_ui_combination_path.py [--verbose]
"""
from __future__ import annotations

import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
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
print("Orange Lab CDSS — combination-therapy panel, walked the UI/PDF way")
print("=" * 72)


# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] STATIC — every real call site passes organism=")
# ═══════════════════════════════════════════════════════════════════════════
import ast as _ast  # noqa: E402

_src = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
_tree = _ast.parse(_src, filename="streamlit_app.py")

_call_sites = []      # (lineno, has_organism, is_def)
for _node in _ast.walk(_tree):
    if isinstance(_node, _ast.FunctionDef) and _node.name == "get_combination_therapy":
        _call_sites.append((_node.lineno, True, True))
    elif isinstance(_node, _ast.Call):
        _f = _node.func
        if isinstance(_f, _ast.Name) and _f.id == "get_combination_therapy":
            _has_org = any(kw.arg == "organism" for kw in _node.keywords)
            _call_sites.append((_node.lineno, _has_org, False))

_real_calls = [(ln, has_org) for ln, has_org, is_def in _call_sites if not is_def]
check("at least the two known call sites (UI panel + PDF export) were found",
      len(_real_calls) >= 2, f"found {len(_real_calls)}")

_missing_organism = [ln for ln, has_org in _real_calls if not has_org]
check("every get_combination_therapy(...) call site passes organism=",
      not _missing_organism,
      f"call site(s) at line(s) {_missing_organism} do not pass organism= — "
      f"this is exactly the defect class fixed 2026-08-21")

for ln, has_org in _real_calls:
    check(f"call site at line {ln} passes organism=", has_org)


# ═══════════════════════════════════════════════════════════════════════════
print("\n[2] DYNAMIC — the actual Proteus/CRE/Colistin scenario")
# ═══════════════════════════════════════════════════════════════════════════
class _Mock:
    def __call__(self, *a, **k): return _Mock()
    def __iter__(self): return iter([_Mock() for _ in range(6)])
    def __getitem__(self, i): return _Mock()
    def __getattr__(self, n): return _Mock()
    def __enter__(self): return _Mock()
    def __exit__(self, *a): return False
    def __bool__(self): return False


class _SessionState(dict):
    def __getattr__(self, n): return self.get(n)
    def __setattr__(self, n, v): self[n] = v


class _Stub(types.ModuleType):
    def __getattr__(self, n):
        # See test_clinical_matrix.py's 2026-08-22 note for why columns/tabs
        # and cache_data/cache_resource/fragment/dialog need real handling
        # here, not a generic Mock -- a pytest-collection cross-file bug a
        # second-opinion audit found.
        if n in ("cache_data", "cache_resource"):
            return lambda f=None, **k: (f if f else (lambda g: g))
        if n in ("fragment", "dialog"):
            return lambda *a, **k: (lambda f: f)
        if n == "columns":
            return lambda spec, **k: [_Mock() for _ in range(spec if isinstance(spec, int) else len(spec))]
        if n == "tabs":
            return lambda names, **k: [_Mock() for _ in names]
        return _Mock()


_stub = _Stub("streamlit")
_stub.session_state = _SessionState()
_stub.secrets = {}
sys.modules.setdefault("streamlit", _stub)

_APP: dict = {"__name__": "app_core"}
try:
    _marker = 'if not st.session_state.authenticated:'
    exec(compile(_src[:_src.index(_marker)], "streamlit_app.py", "exec"), _APP)
    _LOADED = True
except Exception as _e:
    _LOADED = False
    print(f"  SKIP  could not load streamlit_app.py core ({_e})")

if _LOADED:
    get_combo = _APP["get_combination_therapy"]
    phenotypes = [{"phenotype": "CRE"}]

    # (a) the pre-fix pattern: no organism at all -- documents the exact
    #     blind spot, so a future reader sees the contrast, not just a pass.
    _no_org = get_combo(phenotypes, is_pregnant=False, age_years=45,
                         age_months=None, is_renal=False, cl_cr=None,
                         is_hepatic=False)
    _cre_panel_no_org = next((p for p in _no_org if p["phenotype"] == "CRE"), None)
    check("sanity: CRE panel is produced even without organism",
          _cre_panel_no_org is not None)
    _colistin_opt_no_org = next(
        (o for o in _cre_panel_no_org["data"]["options"] if "Colistin" in o["combo"]),
        None) if _cre_panel_no_org else None
    check("without organism=, the Colistin option is NOT annotated "
          "(this is the exact blind spot the fix closes -- not a good "
          "thing, just the documented baseline)",
          _colistin_opt_no_org is not None
          and not _colistin_opt_no_org.get("host_flagged"))

    # (b) the fixed pattern: organism="Proteus mirabilis" (intrinsically
    #     colistin-resistant, per clinical_data.INTRINSIC_RESISTANCE) -- the
    #     exact call shape both UI call sites now use.
    for _organism in ("Proteus mirabilis", "Providencia spp.",
                       "Morganella morganii", "Serratia marcescens"):
        _with_org = get_combo(phenotypes, is_pregnant=False, age_years=45,
                               age_months=None, is_renal=False, cl_cr=None,
                               is_hepatic=False, organism=_organism)
        _cre_panel = next((p for p in _with_org if p["phenotype"] == "CRE"), None)
        _colistin_opt = next(
            (o for o in _cre_panel["data"]["options"] if "Colistin" in o["combo"]),
            None) if _cre_panel else None
        check(f"with organism={_organism!r}, the Colistin option IS "
              f"flagged as intrinsically inactive",
              _colistin_opt is not None and _colistin_opt.get("host_flagged") is True,
              _colistin_opt)

    # (c) a genuinely colistin-susceptible organism must NOT be flagged --
    #     proves this isn't a blanket "always flag Colistin" shortcut.
    _pa = get_combo([{"phenotype": "CRPA"}], is_pregnant=False, age_years=45,
                     age_months=None, is_renal=False, cl_cr=None,
                     is_hepatic=False, organism="Pseudomonas aeruginosa")
    _crpa_panel = next((p for p in _pa if p["phenotype"] == "CRPA"), None)
    if _crpa_panel:
        _colistin_pa = next(
            (o for o in _crpa_panel["data"]["options"] if "Colistin" in o["combo"]),
            None)
        if _colistin_pa is not None:
            check("Colistin is NOT flagged for Pseudomonas aeruginosa "
                  "(not intrinsically resistant -- this must stay a real option)",
                  not _colistin_pa.get("host_flagged"))


print("\n" + "=" * 72)
print(f"{len(_PASS)} passed, {len(_FAIL)} failed")
if _FAIL:
    print("\nRESULT: FAILURES — see above")
    if __name__ == "__main__":
        sys.exit(1)
else:
    print("\nRESULT: ALL GREEN")
    print("\nNOTE: this suite guards the UI/PDF CALL PATH specifically. It does")
    print("      not re-prove get_combination_therapy()'s own clinical content")
    print("      -- that is test_engine_agreement.py and test_scenarios.py.")
    if __name__ == "__main__":
        sys.exit(0)
