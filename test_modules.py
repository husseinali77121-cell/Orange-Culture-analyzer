#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_modules.py — the extracted modules, tested directly.

WHY THIS FILE EXISTS
Between 2026-08-01 and 2026-08-03 roughly 3,300 lines came out of
streamlit_app.py into five modules: clinical_utils, pathogenicity, ocr_parsing,
auth_service and report_service. Every one of them is now importable without a
Streamlit runtime — and every one of them was still only being tested
INDIRECTLY, through the pipeline that happens to call it.

That is the same gap that let the render layer ship two live defects: code with
no suite of its own is code whose contracts nobody has written down. Extracting
a module and not testing it directly buys the import graph and none of the
safety.

WHAT THIS COVERS
Each module's own contract — the promises its callers rely on and that are not
visible from the pipeline:

    clinical_utils   the matching guards, and Patient's derived properties
    pathogenicity    the three-state colony report, and score monotonicity
    ocr_parsing      span-claiming, disk codes, and failing CLOSED on junk
    auth_service     persistence across sessions, and failing OPEN on storage
    report_service   bind() refusing a partial wiring

Run:  python test_modules.py [--verbose]
"""
from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
VERBOSE = "--verbose" in sys.argv

# auth_service writes to disk. Point it at a throwaway directory BEFORE it is
# imported anywhere, so a test run never touches a real deployment's store.
os.environ["ORANGE_AUTH_STORE"] = os.path.join(
    tempfile.mkdtemp(prefix="orange-test-"), "auth.json")

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
print("Orange Lab CDSS — the extracted modules, tested directly")
print("=" * 72)


# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] clinical_utils — the matching guards that were missing three times")
# ═══════════════════════════════════════════════════════════════════════════
from clinical_utils import (                                        # noqa: E402
    collapse_ws, canon_org, org_matches, org_in, resolve_age_years,
    Patient, NEONATE_MAX_YEARS, NON_INFORMATIVE_ORGANISM_TOKENS,
)

check("collapse_ws lowers, strips AND collapses internal runs",
      collapse_ws("  Escherichia   COLI  ") == "escherichia coli",
      repr(collapse_ws("  Escherichia   COLI  ")))
check("collapse_ws survives None and non-strings",
      collapse_ws(None) == "" and collapse_ws(123) == "123")

# Zero-width and directional marks. `\s` does not match these, so before
# 2026-08-03 an organism carrying one matched NO intrinsic row, no producer
# list and no phenotype rule — and the OCR alias lookup then fell through to
# index 0, the silent misidentification already fixed once for Serratia. They
# arrive from OCR of bidirectional documents, from PDF copy-paste, and from
# Word autocorrect.
_ZW = [("Klebsiella\u200bpneumoniae", "klebsiella pneumoniae"),   # ZW space
       ("Klebsiella\u00adpneumoniae", "klebsiella pneumoniae"),   # soft hyphen
       ("E\u200c. coli", "e. coli"),                              # ZW non-joiner
       ("\ufeffE. coli", "e. coli"),                              # BOM
       ("  Escherichia\u00a0coli ", "escherichia coli"),          # NBSP
       ("E. coli", "e. coli")]
_zwbad = [f"{s!r} -> {collapse_ws(s)!r}, want {w!r}"
          for s, w in _ZW if collapse_ws(s) != w]
check("zero-width and directional marks resolve to the real name",
      not _zwbad, "\n".join(_zwbad))
check("a zero-width mark is treated as a separator, not deleted",
      collapse_ws("Klebsiella\u200bpneumoniae") == "klebsiella pneumoniae",
      "deleting it joins the words and matches nothing")
check("hostile control characters still match nothing",
      not any(org_matches(x, ["escherichia coli"])
              for x in ("", "\u200f", "\u202e", "\u0000", "\ufeff", "×" * 50)))

_KEYS = ["escherichia coli", "klebsiella pneumoniae", "staphylococcus aureus"]
# The empty-string trap: `"" in "escherichia coli"` is True, and that one fact
# produced three separate clinical defects before the floor existed.
_junk = [j for j in ("", " ", "   ", "e", "a", ".", "sp") if org_matches(j, _KEYS)]
check("no fragment shorter than the floor matches anything", not _junk, f"{_junk}")
_tok = [t for t in NON_INFORMATIVE_ORGANISM_TOKENS if org_matches(t, _KEYS)]
check("no non-informative token matches", not _tok, f"{_tok}")
check("org_matches(None, ...) is False, not an exception",
      org_matches(None, _KEYS) is False)
check("a real organism still matches, spaced or not",
      org_matches("Escherichia coli", _KEYS)
      and org_matches("  Escherichia   coli ", _KEYS)
      and org_matches("E. COLI", ["e. coli"]))
check("org_in is exact membership, never substring",
      org_in("E. coli", ["E. coli"]) and not org_in("coli", ["E. coli"]))

# resolve_age_years is the fix for the ceftriaxone defect, and its whole value
# is in what it does with a months value it cannot use.
check("months win over years when usable",
      abs(resolve_age_years(0, 6) - 0.5) < 1e-9)
check("months of 0 still resolve (0 is a real neonate, not 'missing')",
      resolve_age_years(0, 0) == 0.0)
_bad_months = [m for m in (12, 99, -3, "x", None)
               if resolve_age_years(5, m) != 5]
check("an unusable months value falls back to years, never guesses older",
      not _bad_months, f"{_bad_months}")

_p = Patient(age_years=0, age_months=6)
check("Patient derives an effective age from months",
      abs(_p.effective_age_years - 0.5) < 1e-9)
check("a six-month-old is an infant but NOT a neonate",
      _p.is_infant and not _p.is_neonate)
check("a three-day-old IS a neonate",
      Patient(age_years=0, age_months=0).is_neonate)
check("the neonate boundary is 28 days, not one year",
      abs(NEONATE_MAX_YEARS - 28 / 365) < 1e-9)
check("validate() reports impossible records without raising",
      any("ذكر" in w for w in Patient(age_years=40, sex="Male",
                                      is_pregnant=True).validate()))
check("validate() is silent on a valid record",
      Patient(age_years=40, sex="Male", cl_cr=90).validate() == [])
check("validate() never raises on a nonsense record",
      isinstance(Patient(age_years=None, sex="", cl_cr=None).validate(), list))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[2] pathogenicity — three states, and a score that only goes up")
# ═══════════════════════════════════════════════════════════════════════════
import pathogenicity as PG                                          # noqa: E402

_EXPECT = [("10^5", 100000), ("10*5", 100000), ("10**5", 100000),
           ("10E5", 100000), ("10e5", 100000), ("10 5", 100000),
           ("5x10^4", 50000), ("2 x 10^5", 200000),
           ("100000", 100000), (">100,000", 100000),
           ("No growth", 0), ("", 0)]
_bad = [f"{t!r}->{PG._parse_cfu(t)} want {e}" for t, e in _EXPECT
        if PG._parse_cfu(t) != e]
check("_parse_cfu reads every exponent notation a machine prints",
      not _bad, "\n".join(_bad))

# The three states exist because 0 cannot carry both "nothing grew" and
# "nobody filled the field in".
_states = {"": "unreported", "  ": "unreported", "???": "unreported",
           "No growth": "none", "No significant growth": "none",
           "لا يوجد نمو": "none", "10^5": "counted", "heavy growth": "counted"}
_bad = [f"{t!r}->{PG._cfu_report_state(t)!r} want {e!r}"
        for t, e in _states.items() if PG._cfu_report_state(t) != e]
check("'no growth', 'not reported' and a real count are three distinct states",
      not _bad, "\n".join(_bad))

_bands = [("heavy growth", 100000, None), ("TNTC", 100000, None),
          ("+++", 100000, None), ("moderate growth", 10000, 100000),
          ("++", 10000, 100000), ("scanty growth", 1000, 10000)]
_bad = []
for t, lo, hi in _bands:
    v = PG._parse_cfu(t)
    if v < lo or (hi and v >= hi):
        _bad.append(f"{t!r} -> {v}, expected {lo}..{hi or '∞'}")
check("verbal reports land in the right significance band, not on a threshold",
      not _bad, "\n".join(_bad))

check("verbal pyuria is not silently dropped",
      all(PG._parse_pus(t) is not None
          for t in ("full field", "loaded", "TNTC", "plenty", "many")))
check("_parse_pus still returns None when nothing is stated",
      PG._parse_pus("") is None and PG._parse_pus("not done") is None)

# EXTRACTOR and SCORER must share one vocabulary. Until 2026-08-03 they did
# not: _parse_pus resolved "full field", "loaded", "plenty", "many" and
# "occasional" to numbers, while detect_pus_cells returned "" for every one of
# them — so the verbal readings never reached the function that knew what to do
# with them, and the strongest pyuria a microscopist can report produced no
# value at all. Found by executing detect_pus_cells directly after a coverage
# sweep showed 41 of its 72 lines had never run.
try:
    import importlib as _il2
    _sa = _il2.import_module("streamlit_app")
    _chain = [("Pus cells: full field", 50), ("Pus cells numerous", 30),
              ("Pus cells many", 20), ("Pus cells: 20-25", 20),
              ("Pus cells: TNTC", 50), ("صديد كثير", 30)]
    _gap = []
    for _txt, _min in _chain:
        _e = _sa.detect_pus_cells(_txt)
        _v = PG._parse_pus(_e) if _e else None
        if _v is None or _v < _min:
            _gap.append(f"{_txt!r} -> extracted {_e!r} -> scored {_v}, expected >= {_min}")
    check("a verbal pyuria reading survives extractor AND scorer",
          not _gap, "\n".join(_gap))
    check("an absent reading still yields nothing at both stages",
          _sa.detect_pus_cells("") == "" and PG._parse_pus("") is None)
except ImportError:
    print("  SKIP  streamlit_app not importable here")

# Monotonicity: sterile urine must score BELOW any real count. It did not, for
# a long time, because every branch penalised `cfu > 0` and 0 hit no branch.
_SYM = ["Dysuria / Frequency / Urgency"]


def _score(colony, age=35, sex="Male"):
    return PG.assess_pathogenicity("Urine", "E. coli", colony, "Pure growth",
                                   _SYM, "20-25", "", "", age, sex, [])


_mono = []
for _lab, _age, _sex in (("male 35", 35, "Male"), ("female 30", 30, "Female"),
                         ("infant", 0, "Male")):
    _none = _score("No growth", _age, _sex)["score"]
    _low = _score("10^2", _age, _sex)["score"]
    if _none >= _low:
        _mono.append(f"{_lab}: 'No growth'={_none} >= '10^2'={_low}")
    _prev = None
    for _c in ("10^2", "10^3", "10^4", "10^5", "heavy growth"):
        _s = _score(_c, _age, _sex)["score"]
        if _prev is not None and _s < _prev:
            _mono.append(f"{_lab}: score fell {_prev}->{_s} at {_c!r}")
        _prev = _s
check("the score rises with colony count and never runs backwards",
      not _mono, "\n".join(_mono))

check("an unreadable colony count is flagged, not scored silently",
      "CFU_NOT_REPORTED" in (_score("")["special_flags"] or []),
      f"flags = {_score('')['special_flags']}")
check("assess_pathogenicity returns its reasoning, not just a number",
      all(k in _score("10^5") for k in ("score", "verdict", "factors_pos",
                                        "factors_neg")))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[3] ocr_parsing — span claiming, disk codes, and failing CLOSED")
# ═══════════════════════════════════════════════════════════════════════════
import ocr_parsing as OP                                            # noqa: E402

# A shorter name inside a longer one must not also match: this produced a
# phantom "Ampicillin" that raised intrinsic alerts for an untested drug.
_phantom = []
for _line, _want, _not in (
        ("Ampicillin/Sulbactam            S", "Ampicillin/Sulbactam", "Ampicillin"),
        ("Amoxicillin + Clavulanic acid   R", "Amoxicillin + Clavulanic acid", "Amoxicillin"),
        ("Piperacillin + Tazobactam       S", "Piperacillin + Tazobactam", "Piperacillin"),
        ("Trimethoprim/Sulfamethoxazole   S", "Trimethoprim/Sulfamethoxazole", "Trimethoprim")):
    _got = OP.extract_detected_drugs(_line)
    if _want not in _got:
        _phantom.append(f"{_line[:34]!r} lost {_want}")
    if _not in _got:
        _phantom.append(f"{_line[:34]!r} invented {_not}")
check("a shorter drug name inside a longer one never also matches",
      not _phantom, "\n".join(_phantom))

check("brand names and misspellings resolve",
      OP.extract_detected_drugs("Augmentin S") == ["Amoxicillin + Clavulanic acid"]
      and OP.extract_detected_drugs("Amoxycillin S") == ["Amoxicillin"])

# Disk codes: honoured only as a standalone token on a line carrying a verdict.
# Every separator a report might use between code and verdict. A panel that
# parses PARTIALLY is worse than one that fails outright: on a Pseudomonas
# isolate a truncated panel took the same AST from MDR to no classification at
# all, with nothing on screen saying the parser had dropped half of it.
_seps = {
    "newline":      "AMC S\nCIP R\nSXT S\nMEM S",
    "spaced slash": "AMC S / CIP R / SXT S / MEM S",
    "bare slash":   "AMC S/CIP R/SXT S/MEM S",
    "hyphen":       "AMC-S CIP-R SXT-S MEM-S",
    "colon":        "AMC:S CIP:R SXT:S MEM:S",
    "pipe":         "AMC S| CIP R| SXT S| MEM S",
    "tab":          "AMC\tS\tCIP\tR\tSXT\tS\tMEM\tS",
}
_part = [f"{k}: {len(OP.extract_detected_drugs(v))}/4"
         for k, v in _seps.items() if len(OP.extract_detected_drugs(v)) != 4]
check("a disk-code panel parses fully whatever separates code from verdict",
      not _part, "\n".join(_part))

# The separator widening must not have broken the full names that legitimately
# contain a slash or a hyphen.
_names = [("Ampicillin/Sulbactam S", "Ampicillin/Sulbactam"),
          ("Trimethoprim/Sulfamethoxazole R", "Trimethoprim/Sulfamethoxazole"),
          ("Imipenem/Cilastatin S", "Imipenem/Cilastatin")]
_broken = [f"{t!r} -> {OP.extract_detected_drugs(t)}"
           for t, w in _names if OP.extract_detected_drugs(t) != [w]]
check("drug names containing / are still matched whole",
      not _broken, "\n".join(_broken))
_noise = ["Orange Lab  -  Culture & Sensitivity Report",
          "Name: Mohamed Ali        Age: 45 Y        Sex: M",
          "Specimen: Urine      Date: 01/08/2026",
          "Dr. Tarek El Shafie   -   Lab Director",
          "The AMC result was discussed with the team"]
_fp = [(l, OP.extract_detected_drugs(l)) for l in _noise
       if OP.extract_detected_drugs(l)]
check("disk codes never fire on report boilerplate", not _fp,
      "\n".join(f"{l[:40]!r} -> {g}" for l, g in _fp))
check("a named drug and its code on one row count once",
      OP.extract_detected_drugs("Ciprofloxacin  CIP  R") == ["Ciprofloxacin"])

# The S/I/R vocabulary fails CLOSED: a wrong S is worse than a missing row.
check("recognised verdicts normalise",
      [OP.normalize_sir_value(v) for v in ("S", "sensitive", "R", "Resistant",
                                           "I", "SDD")] == ["S", "S", "R", "R", "I", "I"])
_open = [v for v in ("???", "5", "sensetive", "", None, "Ø", "MODERATE")
         if OP.normalize_sir_value(v) is not None]
check("an unrecognised verdict returns None rather than a guess",
      not _open, f"guessed at: {_open}")
check("normalize_sir_map drops the unreadable rows and keeps the rest",
      OP.normalize_sir_map({"Meropenem": "S", "X": "???"}) == {"Meropenem": "S"})


# ═══════════════════════════════════════════════════════════════════════════
print("\n[4] auth_service — the throttle follows the ACCOUNT, not the browser")
# ═══════════════════════════════════════════════════════════════════════════
import importlib                                                    # noqa: E402
import auth_service as AU                                           # noqa: E402

_EM = "test-user@orange.lab"
AU.record_success(_EM)                       # start from a clean counter
check("a clean account is not locked", AU.check_lockout(_EM) == (False, 0, 0))

# ABSOLUTE bounds, not relative to the constant. Everything below counts up to
# AU.MAX_ATTEMPTS, so a mutation raising it to 500 makes the loop longer and
# every assertion still passes — the throttle is disabled and the suite is
# green. A limit is only a limit if its VALUE is asserted.
check("MAX_ATTEMPTS is a usable limit, not a number that disables the throttle",
      3 <= AU.MAX_ATTEMPTS <= 10, f"MAX_ATTEMPTS = {AU.MAX_ATTEMPTS}")
check("the lockout is long enough to matter and short enough to recover from",
      60 <= AU.LOCKOUT_SECONDS <= 3600, f"LOCKOUT_SECONDS = {AU.LOCKOUT_SECONDS}")
check("the attempt window is bounded",
      60 <= AU.ATTEMPT_WINDOW_SECONDS <= 86400,
      f"ATTEMPT_WINDOW_SECONDS = {AU.ATTEMPT_WINDOW_SECONDS}")

_seq = [AU.record_failure(_EM) for _ in range(AU.MAX_ATTEMPTS)]
check("the counter counts down to the limit",
      [s[2] for s in _seq] == list(range(AU.MAX_ATTEMPTS - 1, -1, -1)),
      f"attempts left: {[s[2] for s in _seq]}")
check("the account locks at exactly MAX_ATTEMPTS",
      _seq[-1][0] is True and not any(s[0] for s in _seq[:-1]))

# THE point of this module: the previous throttle lived in st.session_state, so
# clearing cookies reset it. Reloading the module simulates a brand-new process
# with no in-memory state at all.
importlib.reload(AU)
check("the lockout survives a process with no memory of it",
      AU.check_lockout(_EM)[0] is True,
      "the throttle is back to being session-scoped")

AU.record_success(_EM)
check("a successful sign-in clears the counter",
      AU.check_lockout(_EM) == (False, 0, 0))
_kinds = [e["kind"] for e in AU.recent_events(10)]
check("every decision is recorded in the audit trail",
      "success" in _kinds and "lockout" in _kinds, f"{_kinds[:6]}")
check("the store is not world-readable",
      oct(os.stat(AU.store_path()).st_mode)[-3:] == "600",
      oct(os.stat(AU.store_path()).st_mode)[-3:])
# The store must never accumulate credentials. It holds e-mails, counters and
# a CLOSED vocabulary of reason codes — a caller cannot smuggle user input into
# the audit file by passing it as `reason`.
AU.record_failure(_EM, "hunter2-the-actual-password")
_written = open(AU.store_path(), encoding="utf-8").read()
check("a reason outside the closed vocabulary is not written verbatim",
      "hunter2" not in _written,
      "free text reached the audit file")
check("it is recorded as 'other' rather than dropped silently",
      any(e.get("detail") == "other" for e in AU.recent_events(5)),
      f"{[e.get('detail') for e in AU.recent_events(5)]}")
check("the audit reason vocabulary is closed, not free text",
      hasattr(AU, "REASON_CODES") and "other" in AU.REASON_CODES
      and len(AU.REASON_CODES) < 20,
      "an open vocabulary lets a caller write user input into the audit file")

check("the store holds no password hashes",
      not any(k in _written.lower() for k in ("pbkdf2", "sha256$", "bcrypt", "argon")))
AU.record_success(_EM)

# Fail OPEN on storage failure: a lab locked out of its own CDSS by a full disk
# is a worse outcome than a slower brute force.
_real = os.environ["ORANGE_AUTH_STORE"]
os.environ["ORANGE_AUTH_STORE"] = "/proc/does-not-exist/auth.json"
try:
    check("an unwritable store fails OPEN, not closed",
          AU.check_lockout("x@y.z") == (False, 0, 0)
          and AU.record_failure("x@y.z")[0] is False)
finally:
    os.environ["ORANGE_AUTH_STORE"] = _real


# ═══════════════════════════════════════════════════════════════════════════
print("\n[5] report_service — bind() must refuse a partial wiring")
# ═══════════════════════════════════════════════════════════════════════════
import report_service as RS                                         # noqa: E402

check("the three renderers are exported",
      all(callable(getattr(RS, n, None)) for n in
          ("generate_pdf_html_report", "generate_decision_tree_image",
           "generate_report")))
try:
    RS.bind(ABX_GUIDELINES={})           # deliberately incomplete
    _refused = False
    _msg = ""
except RuntimeError as _e:
    _refused = True
    _msg = str(_e)
check("bind() refuses a partial wiring instead of failing later in a render",
      _refused, "bind() accepted an incomplete set")
check("the refusal names what is missing",
      "missing" in _msg.lower() and "classify_mdr" in _msg, _msg[:120])


# ═══════════════════════════════════════════════════════════════════════════
print("\n[6] Every extracted module imports WITHOUT a Streamlit runtime.")
print("    That is the whole point of having extracted them — a module you can")
print("    import is a module you can test without a harness standing in for")
print("    an import statement.")
# ═══════════════════════════════════════════════════════════════════════════
# 2026-08-22: the runtime check that used to live here
# (`"streamlit" not in sys.modules`) was removed -- it was testing the wrong
# thing. By this point in the file, "streamlit" legitimately CAN be in
# sys.modules for reasons that have nothing to do with whether the four
# extracted modules import it: this file's own import_module("streamlit_app")
# a few sections up (testing something unrelated, and allowed to pull in
# real streamlit), or -- under `pytest -q` collecting multiple test files in
# one process -- another file's Streamlit stub, already installed before this
# file even runs. The static check right below already verifies the actual
# intent (do these four files' SOURCE contain an import streamlit statement)
# precisely, without depending on what else has happened in this process.
_leak = []
for _m in ("clinical_utils", "pathogenicity", "ocr_parsing", "auth_service"):
    _src = open(os.path.join(HERE, f"{_m}.py"), encoding="utf-8").read()
    if "import streamlit" in _src or "from streamlit" in _src:
        _leak.append(_m)
check("no extracted module imports streamlit", not _leak, f"{_leak}")


print("\n" + "=" * 72)
print(f"{len(_PASS)} passed, {len(_FAIL)} failed")
if _FAIL:
    print("\nRESULT: FAILURES — see above")
    if __name__ == "__main__":
        sys.exit(1)
print("\nRESULT: ALL GREEN")
print("\nNOTE: this suite tests each module's OWN contract. Whether the modules")
print("      compose into a correct clinical answer is test_pipeline.py, and")
print("      whether that answer matches the guidelines is")
print("      test_engine_agreement.py and test_scenarios.py.")
