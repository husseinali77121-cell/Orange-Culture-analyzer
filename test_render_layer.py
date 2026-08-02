"""Orange Lab CDSS — render layer guard.

WHY THIS SUITE EXISTS
---------------------
The other nine suites all prove the same shape of thing: that the ENGINE
reaches the right conclusion. Not one of them looks at what the SCREEN
prints. The 2026-08-02 audit found five defects and every single one lived
in that gap — the engine decided correctly and the renderer dropped the
sentence. Measured across the full scenario matrix, before the fix:

    100.0%  of safety-gate reclassifications rendered a BLANK reason
     15.3%  of banned drugs rendered "💊 Cefazolin []" with no category
     48.6%  of warnings rendered a note belonging to a DIFFERENT organ
            a neonate's kernicterus warning rendered as an empty line

None of that moved the golden snapshot, because the snapshot records the
engine's decision and not the words shown to the clinician.

THE RULE THIS SUITE ENFORCES
----------------------------
    A decision the clinician cannot read is a decision the system did not
    make. Every ban must carry a label and a reason; every warning must
    carry a note; every gate move must carry a cause.

A ban with no visible reason is worse than no ban: it reads as arbitrary,
and arbitrary bans get overridden.

Usage
-----
    python test_render_layer.py
    python test_render_layer.py --verbose
"""
from __future__ import annotations

import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
VERBOSE = "--verbose" in sys.argv


# ── Load the monolith's logic without starting Streamlit ─────────────────────
class _Mock:
    def __call__(self, *a, **k): return _Mock()
    def __getattr__(self, n): return _Mock()
    def __enter__(self): return _Mock()
    def __exit__(self, *a): return False
    def __bool__(self): return False


class _SessionState(dict):
    def __getattr__(self, n): return self.get(n)
    def __setattr__(self, n, v): self[n] = v


class _StreamlitStub(types.ModuleType):
    def __getattr__(self, n): return _Mock()


_stub = _StreamlitStub("streamlit")
_stub.session_state = _SessionState()
_stub.secrets = {}
sys.modules["streamlit"] = _stub

_src = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
# Built by concatenation on purpose: writing this marker as one literal would
# make THIS FILE's own text the first textual match if the file were ever
# scanned, and it is the exact trap that truncated the module during the audit.
_MARK = "if not st.session_state." + "authenticated:"
_cut = _src.index(_MARK)
APP: dict = {"__name__": "app_core"}
exec(compile(_src[:_cut], "streamlit_app.py", "exec"), APP)

analyze_antibiotics = APP["analyze_antibiotics"]
warned_note_for = APP["warned_note_for"]
banned_category_label = APP["banned_category_label"]
BANNED_CATEGORY_LABELS = APP["BANNED_CATEGORY_LABELS"]
build_banned_item = APP["build_banned_item"]
is_intrinsically_avoided = APP["is_intrinsically_avoided"]

from safety_gate import apply_safety_gate                      # noqa: E402
from scenario_matrix import build_matrix                       # noqa: E402
from self_check import run_self_check, BLOCK                   # noqa: E402

passed: list[str] = []
failed: list[str] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    (passed if ok else failed).append(name if ok else f"{name}\n        {detail}")
    if VERBOSE or not ok:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        if not ok and detail:
            print(f"          {detail}")


HOSTS = [
    ("adult", dict(age=45, sex="Male", is_renal=False, cl_cr=95.0,
                   is_preg=False, is_hepatic=False, current_meds=[])),
    ("pregnant", dict(age=28, sex="Female", is_renal=False, cl_cr=95.0,
                      is_preg=True, is_hepatic=False, current_meds=[])),
    ("neonate-0m", dict(age=0, sex="Male", age_months=0, is_renal=False,
                        cl_cr=95.0, is_preg=False, is_hepatic=False, current_meds=[])),
    ("neonate-months-unknown", dict(age=0, sex="Male", age_months=None,
                                    is_renal=False, cl_cr=95.0, is_preg=False,
                                    is_hepatic=False, current_meds=[])),
    ("neonate-bad-months", dict(age=0, sex="Male", age_months=99, is_renal=False,
                                cl_cr=95.0, is_preg=False, is_hepatic=False,
                                current_meds=[])),
    ("renal-CrCl22", dict(age=70, sex="Male", is_renal=True, cl_cr=22.0,
                          is_preg=False, is_hepatic=False, current_meds=[])),
    ("hepatic-CP-C", dict(age=55, sex="Male", is_renal=False, cl_cr=95.0,
                          is_preg=False, is_hepatic=True, child_pugh="C",
                          current_meds=[])),
]

print("=" * 72)
print("Orange Lab CDSS — render layer")
print("  every ban labelled · every warning explained · every gate move caused")
print("=" * 72)
print()


# ═════════════════════════════════════════════════════════════════════════
print("[1] STATIC — the label map covers every category the engine emits")
# ═════════════════════════════════════════════════════════════════════════
# Scraped from the source rather than from a hand-kept list: a category added
# in a future edit shows up here without anyone remembering to update a test.
import re                                                       # noqa: E402

_emitted = set(re.findall(r'build_banned_item\(\s*[^,]+,\s*"([a-z_]+)"', _src))
_emitted |= set(re.findall(r'"category":\s*"([a-z_]+)"', _src))
_emitted |= set(re.findall(r'"category":\s*"([a-z_]+)"',
                           (ROOT / "safety_gate.py").read_text(encoding="utf-8")))
_missing = sorted(c for c in _emitted if c not in BANNED_CATEGORY_LABELS)
check(not _missing,
      "every banned category has a display label",
      f"unlabelled: {_missing}")

check(banned_category_label("a_category_invented_tomorrow").strip() != "",
      "an unknown category still renders a non-empty label")
check(banned_category_label(None).strip() != "",
      "a missing category still renders a non-empty label")
print()


# ═════════════════════════════════════════════════════════════════════════
print("[2] STATIC — the warned-note resolver never returns an empty string")
# ═════════════════════════════════════════════════════════════════════════
_reasons = sorted(set(re.findall(r'"warning_reason":\s*"([a-z_]+)"', _src))
                  | {"safety_gate", ""})
_blank = [r for r in _reasons if not warned_note_for({"name": "X", "warning_reason": r}).strip()]
check(not _blank,
      "every warning_reason resolves to a non-empty note",
      f"blank for: {_blank}")
check(warned_note_for({}).strip() != "",
      "an item with no reason at all still resolves to a note")

# The defect verbatim: a hepatic warning must not be explained with a
# kidney instruction just because renal_note happens to be present.
_hep = {"name": "Ceftriaxone", "warning_reason": "hepatic_adjustment",
        "hepatic_level": "Caution", "hepatic_rec": "خفض الجرعة",
        "renal_note": "🟢 آمن كلوياً — يُطرح كبدياً أساساً."}
check(_hep["renal_note"] not in warned_note_for(_hep),
      "a hepatic warning is NOT explained with the renal note",
      f"got: {warned_note_for(_hep)!r}")

_neo = {"name": "Ceftriaxone", "warning_reason": "neonate_age_unknown",
        "neonate_note": "⚠️ تحذير حديثي الولادة"}
check("حديثي الولادة" in warned_note_for(_neo),
      "a neonatal warning shows the neonatal note")
print()


# ═════════════════════════════════════════════════════════════════════════
print("[3] STATIC — every gate move carries a machine-readable reason")
# ═════════════════════════════════════════════════════════════════════════
_a, _w, _b, _rep = apply_safety_gate(
    [{"name": "Cefazolin"}], [], [],
    organism="Streptococcus pneumoniae", specimen="CSF", age_years=45)
_mv = _rep.get("moves") or []
check(bool(_mv), "the gate still demotes Cefazolin on a CSF isolate")
check(all(m.get("reason_ar") for m in _mv),
      "every gate move carries reason_ar (the UI renders Arabic)")
check(all(m.get("reason_en") for m in _mv),
      "every gate move carries reason_en")
print()


# ═════════════════════════════════════════════════════════════════════════
print("[4] MATRIX — nothing renders blank across the whole scenario space")
# ═════════════════════════════════════════════════════════════════════════
blank_bans: list[str] = []
blank_warns: list[str] = []
blank_moves: list[str] = []
no_reason_short: list[str] = []
cases = 0

for case in build_matrix():
    for hname, host in HOSTS:
        cases += 1
        sir = dict(case["sir_map"])
        allowed, warned, banned, preg, inter = analyze_antibiotics(
            final_drugs=list(sir), organism_type=case["organism"],
            culture_type=case["specimen"], sir_map=sir, **host)
        allowed, warned, banned, rep = apply_safety_gate(
            allowed, warned, banned,
            organism=case["organism"], specimen=case["specimen"], sir_map={},
            age_years=host["age"], is_pregnant=host["is_preg"],
            cl_cr=host["cl_cr"], is_renal=host["is_renal"],
            is_hepatic=host["is_hepatic"], child_pugh=host.get("child_pugh"))
        cid = f"{case['id']}/{hname}"

        for it in banned:
            if not banned_category_label(it.get("category")).strip():
                blank_bans.append(f"{cid}: {it.get('name')} cat={it.get('category')}")
            if not (it.get("reason_short") or "").strip():
                no_reason_short.append(f"{cid}: {it.get('name')}")
        for it in warned:
            if not warned_note_for(it).strip():
                blank_warns.append(f"{cid}: {it.get('name')} "
                                   f"wr={it.get('warning_reason')}")
        for m in rep.get("moves", []):
            if not (m.get("reason_ar") or m.get("reason_en") or m.get("why")):
                blank_moves.append(f"{cid}: {m.get('drug')}")

check(not blank_bans, f"no banned drug renders an empty category label "
                      f"({cases} cases)", f"{len(blank_bans)} e.g. {blank_bans[:3]}")
check(not no_reason_short, "every banned drug carries reason_short",
      f"{len(no_reason_short)} e.g. {no_reason_short[:3]}")
check(not blank_warns, "no warning renders an empty note",
      f"{len(blank_warns)} e.g. {blank_warns[:3]}")
check(not blank_moves, "no gate move renders an empty reason",
      f"{len(blank_moves)} e.g. {blank_moves[:3]}")
print()


# ═════════════════════════════════════════════════════════════════════════
print("[5] SELF-CHECK — it must FAIL on the defects it was built to catch")
# ═════════════════════════════════════════════════════════════════════════
# A verification module that cannot be made to fail is not a verification
# module. These feed it the pre-fix renderers and demand a BLOCK.
_old_labels = {"resistant": "..", "renal": "..", "pregnancy": "..",
               "child": "..", "organism": "..", "other": ".."}


def _old_label(c):
    return _old_labels.get(c, "")


def _old_note(it):
    if it.get("warning_reason") in ("esbl_bli_uti_only", "possible_carbapenemase"):
        return it.get("esbl_note", "")
    return it.get("renal_note", "")


_r = run_self_check(
    allowed=[], warned=[], banned=[{"name": "Doxycycline", "category": "hepatic",
                                    "reason_short": "x"}],
    sir_map={}, organism="", specimen="Blood", age=40,
    gate_report={"moves": [], "specimen_recognised": True,
                 "organism_recognised": True},
    warned_note_for=_old_note, banned_category_label=_old_label)
check(_r["state"] == BLOCK,
      "self-check BLOCKS an unlabelled banned category (regression of bug 2)")

_r = run_self_check(
    allowed=[], warned=[{"name": "Ceftriaxone", "category": "neonate",
                         "reason_short": "x"}], banned=[],
    sir_map={}, organism="", specimen="Blood", age=40,
    gate_report={"moves": [], "specimen_recognised": True,
                 "organism_recognised": True},
    warned_note_for=_old_note, banned_category_label=banned_category_label)
check(_r["state"] == BLOCK,
      "self-check BLOCKS a warning with no text (regression of bug 4)")

_r = run_self_check(
    allowed=[], warned=[], banned=[{"name": "Cefazolin", "category": "safety_gate",
                                    "reason_short": "x"}],
    sir_map={}, organism="", specimen="Blood", age=40,
    gate_report={"moves": [{"drug": "Cefazolin", "from": "allowed",
                            "to": "banned", "layers": ["site"]}],
                 "specimen_recognised": True, "organism_recognised": True},
    warned_note_for=warned_note_for, banned_category_label=banned_category_label)
check(_r["state"] == BLOCK,
      "self-check BLOCKS a gate move with no reason (regression of bug 1)")

# And it must NOT block a clean report — a check that always fails is as
# useless as one that always passes.
_r = run_self_check(
    allowed=[{"name": "Meropenem"}], warned=[], banned=[],
    sir_map={"Meropenem": "S"}, organism="Escherichia coli", specimen="Blood",
    age=40, cl_cr=95.0,
    gate_report={"moves": [], "specimen_recognised": True,
                 "organism_recognised": True},
    warned_note_for=warned_note_for, banned_category_label=banned_category_label,
    intrinsic_checker=is_intrinsically_avoided)
check(_r["state"] != BLOCK, "self-check does NOT block a clean report",
      f"findings: {[f['code'] for f in _r['findings']]}")

# It must catch a contradiction the engine could never report about itself.
_r = run_self_check(
    allowed=[{"name": "Ampicillin"}], warned=[], banned=[],
    sir_map={"Ampicillin": "R"}, organism="Escherichia coli", specimen="Blood",
    age=40, cl_cr=95.0,
    gate_report={"moves": [], "specimen_recognised": True,
                 "organism_recognised": True},
    warned_note_for=warned_note_for, banned_category_label=banned_category_label)
check(_r["state"] == BLOCK,
      "self-check BLOCKS a drug reported R that reached the Allowed list")
print()

print("=" * 72)
print(f"{len(passed)} passed, {len(failed)} failed   ({cases} matrix cases)")
if failed:
    print("\nRESULT: FAILURES")
    for f in failed:
        print(f"  - {f}")
    sys.exit(1)
print("\nRESULT: ALL GREEN")
print("\nNOTE: this proves every decision is READABLE. It does not prove the")
print("      decision is clinically right — see guideline_registry.py.")
