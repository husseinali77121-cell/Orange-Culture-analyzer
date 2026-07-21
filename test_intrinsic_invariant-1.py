#!/usr/bin/env python3
"""
Orange Lab CDSS (COMMERCIAL / streamlit_app.py) — drift & invariant guard.
Reads tables straight from source via AST — needs NO heavy imports and does NOT
run the Streamlit app. Files required next to it:  streamlit_app.py, ast_qa_engine.py
Run:  python test_intrinsic_invariant.py     (exit 0 = OK, 1 = violation)
"""
import ast, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP  = os.path.join(HERE, "streamlit_app.py")     # commercial monolith (inline tables)
QA   = os.path.join(HERE, "ast_qa_engine.py")     # QA engine (embedded fallback table)
ESBL_MARKER_DRUGS = {"Ceftriaxone","Cefotaxime","Ceftazidime","Cefpodoxime","Cefepime"}

def _eval(node):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in ("frozenset","set","list","tuple") and node.args:
        return set(ast.literal_eval(node.args[0]))
    return ast.literal_eval(node)

def _module_literal(path, name):
    for n in ast.parse(open(path, encoding="utf-8").read()).body:
        if isinstance(n, ast.Assign) and any(getattr(t,"id",None)==name for t in n.targets):
            return _eval(n.value)
    raise AssertionError(f"{name} not found in {os.path.basename(path)}")

def _qa_fallback(path):
    """The _CANONICAL_INTRINSIC dict embedded in ast_qa_engine's except block."""
    for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
        if isinstance(node, ast.Try):
            for h in node.handlers:
                for stmt in h.body:
                    if isinstance(stmt, ast.Assign) and any(
                        getattr(t,"id",None)=="_CANONICAL_INTRINSIC" for t in stmt.targets
                    ) and isinstance(stmt.value, ast.Dict):
                        return ast.literal_eval(stmt.value)
    return None

def _norm(t): return {k:set(v) for k,v in t.items()}
fails=[]
def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  — {detail}" if detail and not ok else ""))
    if not ok: fails.append(label)

print("Commercial CDSS — intrinsic / ESBL-gating invariants\n")
ir_app = _module_literal(APP, "INTRINSIC_RESISTANCE")
qa_fb  = _qa_fallback(QA)
check("streamlit_app INTRINSIC_RESISTANCE == ast_qa_engine embedded fallback",
      qa_fb is not None and _norm(ir_app)==_norm(qa_fb), "drift between the two inline copies")

producers = _module_literal(APP, "ESBL_PRODUCERS")
forbidden = {"pseudomonas","acinetobacter","stenotrophomonas","enterococcus","staphylococcus","streptococcus"}
leaked = {p for p in producers if any(f in p for f in forbidden)}
check("ESBL_PRODUCERS contains NO non-Enterobacterale", not leaked, f"leaked={leaked}")

bad = {o:(set(v)&ESBL_MARKER_DRUGS) for o,v in ir_app.items()
       if any(p in o or o in p for p in producers) and set(v)&ESBL_MARKER_DRUGS}
check("no ESBL-marker drug is intrinsic for any producer organism", not bad, f"{bad}")

ampc = _module_literal(APP, "AMPC_PRODUCERS")
np_ampc = [o for o in ampc if not any(p in o or o in p for p in producers)]
uncov = [o for o in np_ampc if not any(k in o or o in k for k in ir_app)]
check("every AmpC-prone non-producer has an intrinsic entry", not uncov, f"uncovered={uncov}")

print()
if fails:
    print(f"RESULT: {len(fails)} invariant(s) violated — DRIFT DETECTED."); sys.exit(1)
print(f"RESULT: all invariants hold — {len(ir_app)} organisms, tables unified, ESBL gating intact.")
sys.exit(0)
