"""Orange Lab CDSS — regression guard for the three intrinsic-resistance tables
and for the OCR drug-name scanner.

Run:  python test_intrinsic_sync.py        (no pytest, no network, no Streamlit)

Each of these tests exists because the corresponding bug shipped:

  1. clinical_data.py did not exist, so ast_qa_engine's canonical import fell
     back to {} and its intrinsic check was dead for every Gram-negative while
     streamlit_app.py was banning drugs from its own private copy.
  2. ast_reportability's Acinetobacter rule excluded "clav", exempting
     amoxicillin-clavulanate from a rule EUCAST applies to it — so the QC panel
     stayed silent on a drug the recommendation panel refused.
  3. extract_detected_drugs() matched drug names by plain containment, so
     "Ampicillin/Sulbactam" manufactured a phantom "Ampicillin" row that then
     tripped the intrinsic-resistance alert for an untested agent.
"""
from __future__ import annotations

import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []
PASSES = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASSES
    if ok:
        PASSES += 1
        print(f"  PASS  {label}")
    else:
        FAILURES.append(f"{label}{(' — ' + detail) if detail else ''}")
        print(f"  FAIL  {label}{(' — ' + detail) if detail else ''}")


# ── Load the data layer without importing Streamlit ──────────────────────────
from clinical_data import INTRINSIC_RESISTANCE as CANON       # noqa: E402
from abx_guidelines import ABX_GUIDELINES, ABX_ALIAS_INDEX, normalize_abx_key  # noqa: E402
import ast_reportability as RP                                # noqa: E402
import ast_qa_engine as QA                                    # noqa: E402

DRUGS = sorted(ABX_GUIDELINES)


def canon_for(org: str) -> set:
    ol = org.lower().strip()
    hit: set = set()
    for k, v in CANON.items():
        if k and (k in ol or ol in k):
            hit |= set(v)
    return {d for d in DRUGS if d in hit}


def qa_for(org: str) -> set:
    ol = org.lower().strip()
    hit: set = set()
    for k, v in QA._INTRINSIC_RESISTANCE.items():
        if k and (k in ol or ol in k):
            hit |= set(v)
    return {d for d in DRUGS if d in hit}


def rp_for(org: str) -> set:
    hit: set = set()
    for r in RP.INTRINSIC_RULES:
        if RP._org_matches(org, r["organisms"]):
            hit |= {d for d in DRUGS if RP._drug_matches(d, r["drugs"], r["exclude"])}
    return hit


ORGANISMS = [
    "Escherichia coli", "Klebsiella pneumoniae", "Proteus mirabilis",
    "Proteus vulgaris", "Morganella morganii", "Providencia spp.",
    "Serratia marcescens", "Enterobacter cloacae", "Citrobacter freundii",
    "Salmonella spp.", "Shigella spp.", "Pseudomonas aeruginosa",
    "Acinetobacter baumannii", "Stenotrophomonas maltophilia",
    "Staphylococcus aureus", "Enterococcus faecalis", "Listeria monocytogenes",
]

print("\n[1] canonical table is live in both engines")
check("clinical_data.INTRINSIC_RESISTANCE is populated", len(CANON) >= 30, f"{len(CANON)} keys")
check("ast_qa_engine loaded the canonical table", QA.CANONICAL_INTRINSIC_LOADED)
for org in ORGANISMS:
    check(f"clinical_data == ast_qa_engine for {org}",
          canon_for(org) == qa_for(org),
          f"symmetric difference: {sorted(canon_for(org) ^ qa_for(org))}")

print("\n[2] Acinetobacter — the reported bug")
acine = canon_for("Acinetobacter baumannii")
acine_rp = rp_for("Acinetobacter baumannii")
check("amox-clav IS intrinsic in clinical_data", "Amoxicillin + Clavulanic acid" in acine)
check("amox-clav IS intrinsic in ast_reportability", "Amoxicillin + Clavulanic acid" in acine_rp)
check("amp-sulbactam is NOT intrinsic in clinical_data", "Ampicillin/Sulbactam" not in acine)
check("amp-sulbactam is NOT intrinsic in ast_reportability", "Ampicillin/Sulbactam" not in acine_rp)
check("cefoperazone-sulbactam is NOT intrinsic (active option)",
      "Cefoperazone + Sulbactam" not in acine and "Cefoperazone + Sulbactam" not in acine_rp)
check("doxycycline is NOT intrinsic (can be active)", "Doxycycline" not in acine)

print("\n[3] no intrinsic rule ever contradicts the other table")
for org in ORGANISMS:
    overlap_conflict = rp_for(org) & {d for d in DRUGS if d not in canon_for(org)}
    # reportability may flag wrong-spectrum Gram-positive agents the clinical
    # table leaves to its own wrong-spectrum pass; only β-lactams must agree.
    betalactam = {d for d in overlap_conflict
                  if re.search(r"cef|ceph|cillin|penem|bactam", d, re.I)}
    check(f"no beta-lactam disagreement for {org}", not betalactam, f"{sorted(betalactam)}")

print("\n[4] OCR scanner produces no phantom drugs")
try:
    _src = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    _start = _src.index("_ABX_ALIAS_SORTED = sorted(")
    _end = _src.index("def extract_detected_drugs(")
    _end = _src.index("\n\n", _src.index("return sorted(detected)", _end))
    _ns: dict = {
        "ABX_ALIAS_INDEX": ABX_ALIAS_INDEX, "ABX_GUIDELINES": ABX_GUIDELINES,
        "normalize_abx_key": normalize_abx_key, "List": list, "Tuple": tuple,
        "Optional": type(None), "fuzzy_match": lambda a, b: 0.0,
    }
    exec(compile(_src[_start:_end], "scanner", "exec"), _ns)
    scan = _ns["extract_detected_drugs"]
    match_one = _ns["match_antibiotic_from_text"]
except Exception as exc:                                   # pragma: no cover
    scan = match_one = None
    check("scanner block is extractable from streamlit_app.py", False, repr(exc))

if scan:
    PHANTOM_CASES = [
        ("Ampicillin/Sulbactam            S", "Ampicillin/Sulbactam", "Ampicillin"),
        ("Amoxicillin + Clavulanic acid   R", "Amoxicillin + Clavulanic acid", "Amoxicillin"),
        ("Cefoperazone + Sulbactam        S", "Cefoperazone + Sulbactam", "Cefoperazone"),
        ("Cefuroxime sodium               R", "Cefuroxime sodium", "Cefuroxime"),
        ("Levofloxacin                    R", "Levofloxacin", "Ofloxacin"),
        ("Piperacillin + Tazobactam       R", "Piperacillin + Tazobactam", "Piperacillin"),
    ]
    for line, want, phantom in PHANTOM_CASES:
        found = scan(line)
        check(f"{want!r:34s} does not spawn {phantom!r}", phantom not in found, f"got {found}")
        check(f"{want!r:34s} is itself detected", want in found, f"got {found}")
        check(f"{want!r:34s} resolves as the tested agent", match_one(line) == want,
              f"got {match_one(line)!r}")

    # Real agents that ARE on the panel in their own right must still be found.
    for line, want in [("Ampicillin      R", "Ampicillin"),
                       ("Amoxicillin     S", "Amoxicillin"),
                       ("Ofloxacin       S", "Ofloxacin"),
                       ("Cefuroxime      S", "Cefuroxime"),
                       ("Unasyn          S", "Ampicillin/Sulbactam"),
                       ("Augmentin       R", "Amoxicillin + Clavulanic acid")]:
        check(f"standalone {want!r} still detected", match_one(line) == want,
              f"got {match_one(line)!r}")

print("\n" + "=" * 68)
print(f"{PASSES} passed, {len(FAILURES)} failed")
for f in FAILURES:
    print("  ✗", f)
sys.exit(1 if FAILURES else 0)
