# -*- coding: utf-8 -*-
"""test_clinical_matrix.py — proofs for the clinical map and the safety gate.

Run:  python test_clinical_matrix.py [--verbose]

This file answers the question "how do I guarantee the program never makes a
mistake?" as precisely as it is possible to answer it. It proves FOUR things
mechanically, and is explicit about the fifth thing it cannot prove:

  1. TOTALITY       every (drug x site) cell has an explicit verdict
  2. FAIL-CLOSED    unknown drug / specimen / organism never yields a bare ALLOW
  3. MONOTONICITY   adding a risk factor only ever shrinks the allowed set
  4. DEMOTE-ONLY    the gate can never promote a drug the engine restricted
  5. (NOT PROVABLE) that the table itself matches EUCAST v16 — a human must
                    open the PDF. guideline_registry.countersigned_by is where
                    that signature lives.
"""
from __future__ import annotations

import itertools
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import clinical_matrix as CM                                       # noqa: E402
from safety_gate import apply_safety_gate                          # noqa: E402

VERBOSE = "--verbose" in sys.argv
failures: list[str] = []
passed = 0


def check(cond: bool, label: str, detail: str = "") -> None:
    global passed
    if cond:
        passed += 1
        if VERBOSE:
            print(f"  PASS  {label}")
    else:
        failures.append(f"{label}" + (f" — {detail}" if detail else ""))
        print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))


# ── load the monolith's engine without starting Streamlit ────────────────────
class _Mock:
    def __call__(self, *a, **k): return _Mock()
    def __getattr__(self, n): return _Mock()
    def __enter__(self): return _Mock()
    def __exit__(self, *a): return False
    def __bool__(self): return False


class _SessionState(dict):
    def __getattr__(self, n): return self.get(n)
    def __setattr__(self, n, v): self[n] = v


class _Stub(types.ModuleType):
    def __getattr__(self, n): return _Mock()


_stub = _Stub("streamlit"); _stub.session_state = _SessionState(); _stub.secrets = {}
sys.modules.setdefault("streamlit", _stub)

_src = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
APP: dict = {"__name__": "app_core"}
exec(compile(_src[:_src.index("if not st.session_state.authenticated:")],
             "streamlit_app.py", "exec"), APP)

ABX = APP["ABX_GUIDELINES"]
analyze = APP["analyze_antibiotics"]
FORMULARY = sorted(ABX)

print("=" * 72)
print("Orange Lab CDSS — clinical map & safety gate proofs")
print(f"  {len(FORMULARY)} agents · {len(CM.SITES)} sites · "
      f"{len(FORMULARY) * len(CM.SITES)} PK cells")
print("=" * 72)

# ═════════════════════════════════════════════════════════════════════════
print("\n[1] TOTALITY — every cell is explicit")
errs = CM.prove_totality(FORMULARY)
check(not errs, "every (drug x site) cell resolves", "; ".join(errs[:4]))

# ═════════════════════════════════════════════════════════════════════════
print("\n[2] FAIL-CLOSED — unknown input never silently allows")
for errs in (CM.prove_fail_closed(),):
    check(not errs, "unknown drug / specimen fail closed", "; ".join(errs[:4]))
check(CM.canonical_site("Pleural Fluid") is None
      or CM.evaluate("Nitrofurantoin", "E. coli", "Pleural Fluid").level != CM.ALLOW,
      "an unrecognised specimen does not silently allow a urine-only agent")
check(CM.evaluate("NotARealDrug", "E. coli", "Urine").level == CM.DENY,
      "an agent outside the reviewed formulary is refused")

# ═════════════════════════════════════════════════════════════════════════
print("\n[3] MONOTONICITY — a risk factor may only shrink the allowed set")
errs = CM.prove_monotonicity(FORMULARY)
check(not errs, "every host layer strictly narrows and none is inert",
      "; ".join(errs[:4]))

# ═════════════════════════════════════════════════════════════════════════
print("\n[4] NO CONTRADICTION between the table and the evaluator")
errs = CM.prove_no_contradiction()
check(not errs, "table DENY always survives evaluate()", "; ".join(errs[:4]))

# ═════════════════════════════════════════════════════════════════════════
print("\n[5] SITE APPROPRIATENESS — the defect this map was built to fix")
PT = dict(age=45, sex="Male", is_renal=False, cl_cr=95.0, is_preg=False,
          is_hepatic=False, current_meds=[])
CANNOT_TREAT = {
    "CSF": ["Cefazolin", "Cephalexin", "Clindamycin", "Azithromycin", "Ertapenem",
            "Cefuroxime", "Cefixime", "Erythromycin", "Doxycycline",
            "Piperacillin + Tazobactam", "Gentamicin", "Colistin"],
    "Urine": ["Moxifloxacin", "Azithromycin", "Clindamycin", "Doxycycline",
              "Erythromycin", "Minocycline", "Fusidic acid"],
    "Blood": ["Cephalexin", "Cefixime", "Cefaclor", "Nitrofurantoin", "Fosfomycin"],
    "Sputum": ["Nitrofurantoin", "Fosfomycin", "Norfloxacin"],
    "Pus": ["Nitrofurantoin", "Fosfomycin", "Norfloxacin"],
    "Stool": ["Norfloxacin", "Clindamycin"],
}
ORG_FOR = {"CSF": "Streptococcus pneumoniae", "Urine": "E. coli",
           "Blood": "Staphylococcus aureus", "Sputum": "Klebsiella spp.",
           "Pus": "Staphylococcus aureus", "Stool": "Salmonella spp."}
for site, drugs in CANNOT_TREAT.items():
    org = ORG_FOR[site]
    sir = {d: "S" for d in FORMULARY}
    a, w, b, p, i = analyze(final_drugs=list(sir), organism_type=org,
                            culture_type=site, sir_map=sir, **PT)
    A, W, B, rep = apply_safety_gate(a, w, b, organism=org, specimen=site,
                                     sir_map=sir, age_years=45, cl_cr=95.0)
    still = sorted({d for d in drugs if d in {x["name"] for x in A}})
    check(not still, f"{site}: no PK-inappropriate agent reaches Allowed", str(still))

# ═════════════════════════════════════════════════════════════════════════
print("\n[6] GATE IS DEMOTE-ONLY — it can never loosen the engine")
RANK = {"banned": 2, "warned": 1, "allowed": 0}
violations: list[str] = []
combos = itertools.product(
    ["CSF", "Urine", "Blood", "Sputum", "Stool"],
    ["E. coli", "Staphylococcus aureus", "MRSA", "Pseudomonas aeruginosa",
     "Enterococcus faecalis", "Streptococcus pneumoniae", "Salmonella spp."],
    [dict(is_preg=False, is_hepatic=False, cl_cr=95.0, age=45),
     dict(is_preg=True, is_hepatic=False, cl_cr=95.0, age=28),
     dict(is_preg=False, is_hepatic=True, cl_cr=95.0, age=60),
     dict(is_preg=False, is_hepatic=False, cl_cr=18.0, age=70),
     dict(is_preg=False, is_hepatic=False, cl_cr=95.0, age=5)],
)
n_cases = 0
for site, org, host in combos:
    n_cases += 1
    sir = {d: "S" for d in FORMULARY}
    pt = dict(PT); pt.update({k: v for k, v in host.items()})
    pt["is_renal"] = host["cl_cr"] < 60
    a, w, b, p, i = analyze(final_drugs=list(sir), organism_type=org,
                            culture_type=site, sir_map=sir, **pt)
    before = {}
    for bucket, items in (("allowed", a), ("warned", w), ("banned", b)):
        for it in items:
            before[it["name"]] = bucket
    A, W, B, rep = apply_safety_gate(
        a, w, b, organism=org, specimen=site, sir_map=sir,
        age_years=host["age"], is_pregnant=host["is_preg"],
        cl_cr=host["cl_cr"], is_renal=pt["is_renal"], is_hepatic=host["is_hepatic"])
    after = {}
    for bucket, items in (("allowed", A), ("warned", W), ("banned", B)):
        for it in items:
            after[it["name"]] = bucket
    for drug, was in before.items():
        now = after.get(drug)
        if now and RANK[now] < RANK[was]:
            violations.append(f"{site}/{org}: {drug} {was}->{now}")
    # a drug must never vanish and never be duplicated
    if set(before) != set(after):
        violations.append(f"{site}/{org}: drug set changed "
                          f"(lost {sorted(set(before) - set(after))[:3]})")
    counts = [len(A), len(W), len(B)]
    if sum(counts) != len({*(x['name'] for x in A), *(x['name'] for x in W),
                           *(x['name'] for x in B)}):
        violations.append(f"{site}/{org}: a drug appears in more than one bucket")
check(not violations, f"gate never promotes across {n_cases} engine x host cases",
      "; ".join(violations[:4]))

# ═════════════════════════════════════════════════════════════════════════
print("\n[7] KNOWN CLINICAL FACTS — spot checks that must never regress")
FACTS = [
    # (drug, organism, specimen, host kwargs, must_not_be)
    ("Cefazolin", "Streptococcus pneumoniae", "CSF", {}, CM.ALLOW),
    ("Ertapenem", "E. coli", "CSF", {}, CM.ALLOW),
    ("Moxifloxacin", "E. coli", "Urine", {}, CM.ALLOW),
    ("Nitrofurantoin", "E. coli", "Blood", {}, CM.ALLOW),
    ("Trimethoprim/Sulfamethoxazole", "Rickettsia spp.", "Blood", {}, CM.ALLOW),
    ("Vancomycin", "Legionella pneumophila", "Sputum", {}, CM.ALLOW),
    ("Aztreonam", "Anaerobes (لاهوائيات)", "Pus", {}, CM.ALLOW),
    ("Colistin", "Mycoplasma spp.", "Sputum", {}, CM.ALLOW),
    ("Ceftriaxone", "E. coli", "Blood", {"age_years": 0.01}, CM.ALLOW),
    ("Amoxicillin + Clavulanic acid", "E. coli", "Urine",
     {"is_hepatic": True, "child_pugh": "C"}, CM.ALLOW),
    ("Doxycycline", "E. coli", "Urine", {"is_pregnant": True}, CM.ALLOW),
    ("Nitrofurantoin", "E. coli", "Urine", {"cl_cr": 20.0}, CM.ALLOW),
]
for drug, org, spec, host, forbidden in FACTS:
    v = CM.evaluate(drug, org, spec, **host)
    ctx = f"{drug} / {org} / {spec}" + (f" / {host}" if host else "")
    check(v.level != forbidden, f"NOT {forbidden}: {ctx}", f"got {v.level}")

# these must remain available — over-blocking is also a defect
MUST_STAY = [
    ("Ceftriaxone", "Streptococcus pneumoniae", "CSF", {}),
    ("Meropenem", "Klebsiella spp.", "CSF", {}),
    ("Vancomycin", "MRSA", "CSF", {}),
    ("Nitrofurantoin", "E. coli", "Urine", {}),
    ("Fosfomycin", "E. coli", "Urine", {}),
    ("Trimethoprim/Sulfamethoxazole", "Stenotrophomonas maltophilia", "Sputum", {}),
    ("Amoxicillin + Clavulanic acid", "E. coli", "Urine", {"is_pregnant": True}),
    ("Cefuroxime", "H. influenzae", "Sputum", {}),
]
for drug, org, spec, host in MUST_STAY:
    v = CM.evaluate(drug, org, spec, **host)
    check(v.level == CM.ALLOW, f"still ALLOWED: {drug} / {org} / {spec}",
          f"got {v.level}: {[r['en'] for r in v.reasons][:2]}")

# ═════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 72)
if failures:
    print(f"RESULT: {passed} passed, {len(failures)} FAILED")
    for f in failures:
        print("   ✗", f)
    if __name__ == "__main__":
        sys.exit(1)
print(f"RESULT: ALL GREEN — {passed} checks passed")
print("\nNOTE: these proofs show the CODE matches THIS TABLE.")
print("      They do NOT show the TABLE matches EUCAST v16 — that needs a human.")
if __name__ == "__main__":
    sys.exit(0)
