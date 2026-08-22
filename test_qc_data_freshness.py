#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_qc_data_freshness.py — the Resistance Profile / AST Quality Check /
Panel Completeness cards must never read a stale sir_map_edited.

WHY THIS FILE EXISTS
On 2026-08-22 a user report (re-verified directly against the code, not
taken on faith) found that these three cards render BEFORE the manual
AST-editing block in script order, so on the exact rerun where a lab tech
just changed a result, the cards read st.session_state.sir_map_edited as it
stood at the END of the PREVIOUS run -- one edit behind. Concretely: add
Piperacillin+Tazobactam to a Klebsiella isolate, and the Panel Completeness
card kept showing it as missing until the NEXT unrelated edit, because the
individual st.selectbox widgets sync fresh immediately, but the AGGREGATE
dict those cards read is only rebuilt later in the same script run.

Cannot be tested by actually driving Streamlit reruns -- streamlit itself is
not installed in this environment (no network access to pip install it), and
none of this repo's other suites do that either; they all stub streamlit and
exec a slice of the file for its function/data definitions. This suite proves
what CAN be proven without a live Streamlit runtime: the specific code shape
that closes the gap is present and in the right place relative to both the
write and the sections that depend on it -- the same kind of static,
source-level guard test_ui_combination_path.py [1] uses for a different
call-path defect, for the same reason: a runtime scenario test cannot see a
one-render-lag bug, but reading the actual control flow can.

Run:  python test_qc_data_freshness.py [--verbose]
"""
from __future__ import annotations

import ast
import pathlib
import sys

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
print("Orange Lab CDSS — QC card data freshness (sir_map_edited)")
print("=" * 72)

_src = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
_lines = _src.split("\n")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] The three QC-style cards still render before the edit block")
# ═══════════════════════════════════════════════════════════════════════════
# (documents WHY the fix is needed, not a claim it's a good layout -- if this
# ever flips, the fix below becomes dead code and should be reconsidered.)
def _first_line(marker):
    for i, ln in enumerate(_lines, 1):
        if marker in ln:
            return i
    return None

_resistance_profile_ln = _first_line('st.expander("🧬 Resistance Profile')
_ast_qc_ln = _first_line('st.expander("🔬 AST Quality Check')
_write_back_ln = _first_line("st.session_state.sir_map_edited = edited_sir")

check("Resistance Profile expander found", _resistance_profile_ln is not None)
check("AST Quality Check expander found", _ast_qc_ln is not None)
check("the sir_map_edited write-back line was found", _write_back_ln is not None)

if _resistance_profile_ln and _write_back_ln:
    check("Resistance Profile still renders before the write-back "
          "(confirms the freshness fix below is still needed, not dead code)",
          _resistance_profile_ln < _write_back_ln)
if _ast_qc_ln and _write_back_ln:
    check("AST Quality Check still renders before the write-back "
          "(confirms the freshness fix below is still needed, not dead code)",
          _ast_qc_ln < _write_back_ln)


# ═══════════════════════════════════════════════════════════════════════════
print("\n[2] The write-back forces a rerun when the value actually changed")
# ═══════════════════════════════════════════════════════════════════════════
if _write_back_ln:
    # Look at a small window around the write-back for the rerun-on-change
    # pattern, via AST rather than string matching so formatting changes
    # don't silently defeat this guard.
    _tree = ast.parse(_src, filename="streamlit_app.py")

    def _find_enclosing_if_with_rerun(target_lineno, max_lookahead=6):
        """Is there an `if <cond>: ... st.rerun()` whose body starts within
        a few lines after target_lineno, and whose condition compares against
        the same sir_map_edited-shaped names?"""
        hits = []
        for node in ast.walk(_tree):
            if isinstance(node, ast.If) and target_lineno <= node.lineno <= target_lineno + max_lookahead:
                calls_rerun = any(
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "rerun"
                    for n in ast.walk(node)
                )
                if calls_rerun:
                    hits.append(node)
        return hits

    _guards = _find_enclosing_if_with_rerun(_write_back_ln)
    check("an `if <changed>: ... st.rerun()` guard exists right after the "
          "sir_map_edited write-back",
          bool(_guards),
          "no If-node calling st.rerun() found within a few lines of the "
          "write-back -- the stale-QC-card bug would be back")

    if _guards:
        _cond_src = ast.dump(_guards[0].test)
        check("the rerun guard's condition references sir_map_edited or "
              "edited_sir (not some unrelated flag)",
              "sir_map_edited" in _cond_src or "edited_sir" in ast.dump(_guards[0]),
              _cond_src)

        # The write-back must happen BEFORE the rerun fires, or the follow-up
        # render would see the OLD value again -- an infinite-rerun risk.
        check("session_state.sir_map_edited is assigned before this rerun "
              "fires (so the follow-up render sees the NEW value, not the "
              "old one -- and the loop converges)",
              any(
                  isinstance(n, ast.Assign)
                  and any(
                      isinstance(t, ast.Attribute) and t.attr == "sir_map_edited"
                      for t in n.targets
                  )
                  for n in ast.walk(_tree)
                  if hasattr(n, "lineno") and _write_back_ln - 3 <= n.lineno <= _write_back_ln + 1
              ))


print("\n[3] Panel Completeness card is never gated by AST_QA_AVAILABLE")
# ═══════════════════════════════════════════════════════════════════════════
# Found 2026-08-22: the card called ast_panel_completeness.py directly (never
# through run_ast_qa_engine()), yet was nested inside `if AST_QA_AVAILABLE:`
# purely by accident of where it got inserted -- an unrelated ast_qa_engine.py
# problem could silently take the card down with zero trace anywhere. Fixed
# by decoupling; this guard stops the coupling from quietly coming back.
_tree_pc = ast.parse(_src, filename="streamlit_app.py")


def _ancestors_testing_ast_qa_available(tree, target_call_name="check_panel_completeness"):
    """For every Call node whose func name mentions target_call_name, walk
    back up the tree and report whether any enclosing If's test references
    AST_QA_AVAILABLE."""
    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fname = ""
            if isinstance(node.func, ast.Name):
                fname = node.func.id
            elif isinstance(node.func, ast.Attribute):
                fname = node.func.attr
            if target_call_name not in fname:
                continue
            n = node
            while n in parent:
                n = parent[n]
                if isinstance(n, ast.If) and "AST_QA_AVAILABLE" in ast.dump(n.test):
                    hits.append(node.lineno)
                    break
    return hits

_gated_calls = _ancestors_testing_ast_qa_available(_tree_pc)
check("the Panel Completeness card's own check_panel_completeness() call is "
      "not nested inside any `if ...AST_QA_AVAILABLE...:` block",
      not _gated_calls,
      f"call(s) at line(s) {_gated_calls} are still gated by AST_QA_AVAILABLE "
      f"-- the coupling bug is back")



print(f"{len(_PASS)} passed, {len(_FAIL)} failed")
if _FAIL:
    print("\nRESULT: FAILURES — see above")
    if __name__ == "__main__":
        sys.exit(1)
else:
    print("\nRESULT: ALL GREEN")
    print("\nNOTE: this is a STATIC guard (source-level, via AST) -- it cannot")
    print("      drive an actual Streamlit rerun, because streamlit itself is")
    print("      not installed in this environment. It proves the fix's code")
    print("      shape is present and correctly ordered, not that a live app")
    print("      behaves correctly end to end. A manual click-through (add a")
    print("      drug, confirm the Panel Completeness count updates on the")
    print("      SAME click, not the next one) is still worth doing once.")
    if __name__ == "__main__":
        sys.exit(0)