#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_pipeline.py — walks the path the clinician walks.

WHY THIS FILE EXISTS
Every other suite calls the decision functions DIRECTLY, with correct arguments,
one at a time. None of them walked the composed pipeline, because until
2026-08-03 the pipeline lived inside the Streamlit UI block and that block sits
behind an OCR file upload. Line-tracing a full UI run reached 12.8% of
streamlit_app.py and touched analyze_antibiotics zero times.

That gap was not theoretical. A text replacement added `age_months=` to two
get_combination_therapy() calls that accept no such parameter — a TypeError on
the combination panel and on PDF export — and all ten suites stayed green.

run_analysis() is that pipeline extracted as a pure function, and this suite is
what now walks it. It imports through clinical_utils.Patient, exactly as the UI
does, so a parameter that fails to reach a layer fails HERE rather than in front
of a clinician.

Run:  python test_pipeline.py [--verbose]
"""
from __future__ import annotations

import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
VERBOSE = "--verbose" in sys.argv

_PASS: list = []
_FAIL: list = []


def check(name, ok, detail=""):
    (_PASS if ok else _FAIL).append(name)
    if not ok:
        print(f"  FAIL  {name}")
        for line in str(detail).splitlines()[:10]:
            print(f"          {line}")
    elif VERBOSE:
        print(f"  PASS  {name}")


# ── Load the app the way the UI does, minus the Streamlit runtime ───────────
class _Ctx:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __getattr__(self, n): return lambda *a, **k: _Ctx()
    def __iter__(self): return iter([_Ctx() for _ in range(6)])
    def __getitem__(self, i): return _Ctx()


class _Stop(Exception):
    pass


def _mk_stub():
    import types
    m = types.ModuleType("streamlit")

    class _S(dict):
        def __getattr__(self, k):
            try: return self[k]
            except KeyError: raise AttributeError(k)
        def __setattr__(self, k, v): self[k] = v
    m.session_state = _S()
    m.secrets = _S()
    m._Stop = _Stop
    def _noop(*a, **k): return _Ctx()
    for n in ("markdown", "write", "error", "warning", "info", "success", "caption",
              "text", "header", "subheader", "title", "divider", "image", "toast",
              "metric", "dataframe", "table", "json", "code", "rerun", "set_page_config",
              "download_button", "file_uploader", "date_input", "progress"):
        setattr(m, n, _noop)
    m.expander = m.container = m.form = m.spinner = m.empty = m.status = m.popover = _noop
    m.sidebar = _Ctx()
    m.stop = lambda *a, **k: (_ for _ in ()).throw(_Stop())
    m.cache_data = m.cache_resource = lambda f=None, **k: (f if f else (lambda g: g))
    m.columns = lambda spec, **k: [_Ctx() for _ in range(spec if isinstance(spec, int) else len(spec))]
    m.tabs = lambda names, **k: [_Ctx() for _ in names]
    m.button = m.form_submit_button = lambda *a, **k: False
    m.checkbox = lambda *a, **k: k.get("value", False)
    m.selectbox = m.radio = lambda label=None, options=None, *a, **k: (
        list(options)[k.get("index", 0) or 0] if options else None)
    m.multiselect = lambda *a, **k: list(k.get("default") or [])
    m.text_input = m.text_area = lambda *a, **k: k.get("value", "") or ""
    m.number_input = m.slider = lambda *a, **k: k.get("value", 0) or 0
    m.dialog = m.fragment = lambda *a, **k: (lambda f: f)
    m.__getattr__ = lambda n: _noop
    comp = types.ModuleType("streamlit.components")
    comp.v1 = types.SimpleNamespace(html=_noop, iframe=_noop)
    sys.modules["streamlit.components"] = comp
    sys.modules["streamlit.components.v1"] = comp.v1
    return m


sys.modules.setdefault("streamlit", _mk_stub())
import streamlit as st                                            # noqa: E402
import importlib.util                                             # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "streamlit_app", os.path.join(HERE, "streamlit_app.py"))
A = importlib.util.module_from_spec(_spec)
sys.modules["streamlit_app"] = A
try:
    _spec.loader.exec_module(A)
except _Stop:
    pass
except Exception as exc:                                          # pragma: no cover
    print(f"ENVIRONMENT INCOMPLETE — streamlit_app.py did not load: {exc!r}")
    sys.exit(2)

from clinical_utils import Patient, NEONATE_MAX_YEARS             # noqa: E402

G = A.ABX_GUIDELINES
ORGS = list(A.ORGANISM_PROFILE)
SPECS = list(A.SPECIMEN_TYPES)
DRUGS = list(G)

print("=" * 72)
print("Orange Lab CDSS — composed pipeline (the path the user walks)")
print(f"  {len(G)} agents · {len(ORGS)} organisms · {len(SPECS)} specimens")
print("=" * 72)


# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] run_analysis() returns every panel the UI renders.")
# ═══════════════════════════════════════════════════════════════════════════
_EXPECTED_KEYS = {"allowed", "warned", "banned", "preg_warn", "interactions",
                  "gate_report", "phenotypes", "mechanism", "mdr", "ranked",
                  "combinations", "severity", "syndrome", "duration",
                  "patient_warnings"}
_r = A.run_analysis(Patient(age_years=45, sex="Male"), "E. coli", "Blood",
                    {"Meropenem": "S", "Amikacin": "S", "Ceftriaxone": "R"})
_missing = _EXPECTED_KEYS - set(_r)
check("the pipeline returns the full result set", not _missing,
      f"missing keys: {sorted(_missing)}")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[2] Every host field on Patient actually reaches the engine that")
print("    needs it. This is the check that would have caught the ceftriaxone")
print("    defect: age_months was known upstream and had no parameter to")
print("    travel through, so every infant arrived as age_years=0.")
# ═══════════════════════════════════════════════════════════════════════════
_sir_cro = {"Ceftriaxone": "S", "Cefotaxime": "S", "Meropenem": "S"}


def _state(res, drug):
    if drug in {x["name"] for x in res["allowed"]}: return "allowed"
    if drug in {x["name"] for x in res["warned"]}: return "warned"
    return "banned"


_age = []
for _mo, _want in ((0, "banned"), (1, "warned"), (2, "warned"),
                   (3, "allowed"), (6, "allowed"), (11, "allowed")):
    _res = A.run_analysis(Patient(age_years=0, age_months=_mo), "E. coli",
                          "CSF", _sir_cro)
    if _state(_res, "Ceftriaxone") != _want:
        _age.append(f"{_mo} mo: got {_state(_res, 'Ceftriaxone')}, want {_want}")
check("age_months reaches the gate through the composed pipeline",
      not _age, "\n".join(_age))

# Pregnancy must reach the engine through the object, not a positional slot.
_preg = A.run_analysis(Patient(age_years=28, sex="Female", is_pregnant=True),
                       "E. coli", "Urine",
                       {d: "S" for d in ("Ciprofloxacin", "Doxycycline",
                                         "Gentamicin", "Nitrofurantoin")})
_leak = {x["name"] for x in _preg["allowed"]} & {"Ciprofloxacin", "Doxycycline", "Gentamicin"}
check("is_pregnant reaches the engine", not _leak, f"offered: {sorted(_leak)}")

# Renal and hepatic likewise.
_ren = A.run_analysis(Patient(age_years=50, is_renal=True, cl_cr=10),
                      "E. coli", "Urine", {"Nitrofurantoin": "S", "Meropenem": "S"})
check("cl_cr reaches the engine",
      "Nitrofurantoin" not in {x["name"] for x in _ren["allowed"]},
      "nitrofurantoin still recommended at CrCl 10")

_hep = A.run_analysis(Patient(age_years=50, is_hepatic=True, child_pugh="C"),
                      "E. coli", "Blood", {d: "S" for d in DRUGS})
check("child_pugh reaches the engine",
      any(x.get("warning_reason") == "hepatic_adjustment" for x in _hep["warned"]),
      "no hepatic warning raised at Child-Pugh C")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[3] Every downstream panel is built with the SAME host context.")
print("    The combination panel is the one that reaches the screen without")
print("    passing the safety gate, so it must at least see the same patient.")
# ═══════════════════════════════════════════════════════════════════════════
_xdr = {d: "R" for d in ("Meropenem", "Imipenem/Cilastatin", "Ceftazidime",
                         "Cefepime", "Ciprofloxacin", "Levofloxacin",
                         "Piperacillin + Tazobactam", "Aztreonam")}
_xdr.update({"Amikacin": "S", "Colistin": "S"})
_res = A.run_analysis(Patient(age_years=28, sex="Female", is_pregnant=True),
                      "Pseudomonas aeruginosa", "Blood", _xdr)
_flagged = [o for c in _res["combinations"] for o in c["data"]["options"]
            if o.get("host_flagged")]
check("a pregnant patient's combination panel carries pregnancy warnings",
      bool(_flagged),
      "no option flagged despite aminoglycoside-containing regimens")

check("phenotypes, MDR and mechanism are all produced in one pass",
      _res["phenotypes"] and _res["mdr"] and _res["mechanism"],
      f"phenotypes={bool(_res['phenotypes'])} mdr={bool(_res['mdr'])} "
      f"mechanism={bool(_res['mechanism'])}")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[4] Patient.validate() surfaces impossible host records without")
print("    refusing to build one — a CDSS that will not construct a patient is")
print("    a CDSS that gets bypassed.")
# ═══════════════════════════════════════════════════════════════════════════
check("pregnancy recorded on a male patient is reported",
      any("ذكر" in w for w in Patient(age_years=40, sex="Male",
                                      is_pregnant=True).validate()))
check("an out-of-range month is reported",
      any("0–11" in w for w in Patient(age_years=0, age_months=99).validate()))
check("a negative CrCl is reported",
      any("CrCl" in w for w in Patient(age_years=40, cl_cr=-5).validate()))
check("a valid patient reports nothing",
      Patient(age_years=40, sex="Male", cl_cr=90).validate() == [])
check("validate() never raises on a nonsense record",
      isinstance(Patient(age_years=None, sex="", cl_cr=None).validate(), list))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[5] The composed pipeline holds the same invariants the direct calls")
print("    do — across 400 randomised patients.")
# ═══════════════════════════════════════════════════════════════════════════
random.seed(20260803)
_bad = []
for _ in range(400):
    org = random.choice(ORGS); spec = random.choice(SPECS)
    sir = {d: random.choice("SIR") for d in random.sample(DRUGS, random.randint(3, 22))}
    mo = random.choice([None, 0, 1, 3, 6, 11])
    yr = 0 if mo is not None else random.choice([2, 9, 30, 66, 95])
    sex = random.choice(["Male", "Female"])
    p = Patient(age_years=yr, age_months=mo, sex=sex,
                is_pregnant=(sex == "Female" and yr > 12 and random.random() < .4),
                is_renal=random.random() < .5,
                cl_cr=random.choice([None, 5, 25, 55, 95]),
                is_hepatic=random.random() < .4,
                child_pugh=random.choice("ABC"))
    try:
        r = A.run_analysis(p, org, spec, sir)
        nA = {x["name"] for x in r["allowed"]}
        nW = {x["name"] for x in r["warned"]}
        nB = {x["name"] for x in r["banned"]}
        nP = {x["name"] for x in r["preg_warn"]}
        assert not (nA & nB) and not (nA & nW) and not (nW & nB), "bucket overlap"
        assert not any(sir.get(d) == "R" for d in nA), "resistant agent recommended"
        assert set(sir) <= (nA | nW | nB | nP), "an agent vanished"
        assert all(A.warned_note_for(x, "ar").strip()
                   or x.get("warning_reason") == "intermediate_culture"
                   for x in r["warned"]), "warning with no explanation"
        assert all(str(x.get("reason_short") or "").strip()
                   for x in r["banned"]), "ban with no reason"
        for m in (r["gate_report"].get("moves") or []):
            assert (m.get("reason_ar") or m.get("why") or "").strip(), "gate move with no reason"
    except Exception as exc:
        _bad.append(f"{org}/{spec}/age{yr}/mo{mo}: {type(exc).__name__}: {exc}")
check(f"400 randomised patients through the composed pipeline",
      not _bad, "\n".join(_bad[:8]))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[6] run_analysis() is PURE — no Streamlit state, no mutation of the")
print("    caller's inputs, no mutation of the clinical tables.")
# ═══════════════════════════════════════════════════════════════════════════
import copy                                                        # noqa: E402
_sir = {d: "S" for d in DRUGS}
_snap_sir = copy.deepcopy(_sir)
_snap_g = copy.deepcopy(G)
_snap_ph = copy.deepcopy(A.PHENOTYPE_RULES)
_snap_ct = copy.deepcopy(A.COMBINATION_THERAPY)
_p = Patient(age_years=30, sex="Female", is_pregnant=True)
for _ in range(20):
    A.run_analysis(_p, "Klebsiella spp.", "Blood", _sir)
check("the caller's sir_map is not mutated", _sir == _snap_sir)
check("ABX_GUIDELINES is not mutated", G == _snap_g)
check("PHENOTYPE_RULES is not mutated", A.PHENOTYPE_RULES == _snap_ph)
check("COMBINATION_THERAPY is not mutated", A.COMBINATION_THERAPY == _snap_ct)

_a = A.run_analysis(_p, "Klebsiella spp.", "Blood", _sir)
_b = A.run_analysis(_p, "Klebsiella spp.", "Blood", _sir)
check("the same input yields the same output",
      {x["name"] for x in _a["allowed"]} == {x["name"] for x in _b["allowed"]})


# ═══════════════════════════════════════════════════════════════════════════
print("\n[7] The parallel build stays deleted.")
# ═══════════════════════════════════════════════════════════════════════════
_gone = [g for g in ("modules", "ui", "data", "qc.py", "antibiotics.py")
         if os.path.exists(os.path.join(HERE, g))]
check("modules/ ui/ data/ qc.py antibiotics.py remain deleted",
      not _gone, f"present again: {_gone}")



# ═══════════════════════════════════════════════════════════════════════════
print("\n[8] The PDF withholds specific doses unless the patient is flagged")
print("    RENAL. Requested 2026-08-03: a PDF is an ISSUED document — it leaves")
print("    the lab, gets photographed and forwarded, and is read weeks later by")
print("    someone who never saw the patient. Milligrams printed for a patient")
print("    with NORMAL renal function invite being applied to a different one,")
print("    or to the same one after their function has changed.")
print("    What is withheld is the NUMBERS, not the fact: the threshold is still")
print("    stated, so a short line is never read as 'nothing to adjust here'.")
# ═══════════════════════════════════════════════════════════════════════════
import re as _re8                                                    # noqa: E402

_DOSE = _re8.compile(r"q\d+h|\d+\s*mg/kg|\d+(?:\.\d+)?\s*g\s+q|\d{3,4}\s*mg\s+q")
_sir8 = {d: "S" for d in ("Meropenem", "Ciprofloxacin", "Amikacin", "Vancomycin")
         if d in G}


def _pdf_html(**kw):
    """The PDF document as text. `return_html` exists precisely so this layer
    can be inspected in an environment without WeasyPrint — before it existed,
    1,000 lines of PDF code were untestable and a defect fixed on screen the
    same day survived here unnoticed."""
    p = Patient(age_years=55, sex="Male", **kw)
    r = A.run_analysis(p, "Klebsiella spp.", "Blood", _sir8)
    return A.generate_pdf_html_report(
        patient_name="T", age=55, sex="Male", weight=70,
        cl_cr=kw.get("cl_cr", 95), is_renal=kw.get("is_renal", False),
        is_preg=False, is_hepatic=kw.get("is_hepatic", False),
        allowed=r["allowed"], warned=r["warned"], banned=r["banned"],
        preg_warn_items=r["preg_warn"], organism="Klebsiella spp.",
        specimen="Blood", interactions=r["interactions"], sir_map=_sir8,
        mdr_result=r["mdr"], esbl_result=r["mechanism"],
        phenotypes=r["phenotypes"], return_html=True) or ""


# The rule is applied PER ORGAN, not globally. A renal dose is printed only for
# a patient flagged renal; a HEPATIC dose is printed only for a patient flagged
# hepatic. Gating hepatic dosing on the renal flag would withhold the
# adjustment from the Child-Pugh C patient who is the only one who needs it —
# which is the opposite of the point.
_leaks = []
for _lab, _kw in (("healthy adult", {}),
                  ("elderly 88", {}),
                  ("CrCl 95 recorded", {"cl_cr": 95})):
    _found = sorted({m.group(0).strip() for m in _DOSE.finditer(_pdf_html(**_kw))})
    if _found:
        _leaks.append(f"{_lab}: {_found[:6]}")
check("no dose of any kind reaches the PDF for a patient with no organ flag",
      not _leaks, "\n".join(_leaks))

# A hepatic patient with NORMAL kidneys gets the hepatic band and no renal one.
_hep = _pdf_html(is_hepatic=True, child_pugh="C")
check("a hepatic patient receives hepatic dosing",
      "Child-Pugh" in _hep,
      "the hepatic band was withheld from the patient who needs it")
check("a hepatic patient with normal kidneys receives NO renal dosing",
      "Renal dose adjustment required" not in _hep,
      "renal dosing printed for a patient not flagged renal")

_renal_html = _pdf_html(is_renal=True, cl_cr=25)
check("the full dose band DOES print for a renally impaired patient",
      bool(_DOSE.search(_renal_html)),
      "renal patient received no dosing at all — the gate over-corrected")

# A healthy patient's report carries no renal section at all, and that is
# correct — there is nothing to adjust and nothing to withhold. The guarantee
# that matters is narrower: WHERE renal text does appear without the numbers,
# it must still name the threshold, so the short line is never read as "no
# adjustment exists". Assert the withheld form directly rather than inferring
# it from a document that legitimately omits the section.
from report_service import _REQUIRED as _RS_REQ                      # noqa: E402,F401
_src8 = open(os.path.join(HERE, "report_service.py"), encoding="utf-8").read()
check("the withheld form names the CrCl threshold in both languages",
      "Renally adjusted below CrCl {int(_lim)}" in _src8
      and "يحتاج تعديل الجرعة تحت CrCl {int(_lim)}" in _src8,
      "the withheld note must state the threshold it is withholding for")
check("withholding is gated on is_renal, not on the drug",
      "if not is_renal:" in _src8,
      "the gate must key on the PATIENT, not on which agent is being printed")

_plain = _pdf_html()

check("the PDF is inspectable without WeasyPrint installed",
      len(_plain) > 1000, f"return_html produced {len(_plain)} chars")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[9] THREE-WAY RENDERER AGREEMENT — screen, PDF and text report must")
print("    say the same thing about the same isolate. Three of this audit's")
print("    defects were renderers disagreeing: gate moves printing a blank")
print("    reason on screen, the PDF printing renal dosing under a hepatic")
print("    warning, and the text report losing the Intermediate flag. Each was")
print("    found separately because nothing compared the three outputs.")
# ═══════════════════════════════════════════════════════════════════════════
import re as _re9                                                    # noqa: E402

_DOSE9 = _re9.compile(r"q\d+h|\d+\s*mg/kg|\d+(?:\.\d+)?\s*g\s+q|\d{3,4}\s*mg\s+q")


def _strip9(h):
    return " ".join(_re9.sub(r"<[^>]+>", " ", h or "").split())


random.seed(31337)
_dis = []
for _ in range(120):
    _org = random.choice(ORGS); _spec = random.choice(SPECS)
    _sir = {d: random.choice("SIR") for d in random.sample(DRUGS, random.randint(4, 20))}
    _renal = random.random() < .5
    _crcl = random.choice([10, 25, 45]) if _renal else random.choice([None, 90])
    _hep = random.random() < .4
    _mo = random.choice([None, 0, 3, 9])
    _yr = 0 if _mo is not None else random.choice([6, 40, 75])
    _p = Patient(age_years=_yr, age_months=_mo, sex="Male", is_renal=_renal,
                 cl_cr=_crcl, is_hepatic=_hep, child_pugh="C")
    _r = A.run_analysis(_p, _org, _spec, _sir)
    _nA = {x["name"] for x in _r["allowed"]}

    _txt = A.generate_report(
        patient_name="T", age=_yr, age_months=_mo, sex="Male", weight=70,
        cl_cr=_crcl or 95, is_renal=_renal, is_preg=False, is_hepatic=_hep,
        allowed=_r["allowed"], warned=_r["warned"], banned=_r["banned"],
        preg_warn_items=_r["preg_warn"], organism=_org, specimen=_spec,
        interactions=_r["interactions"], sir_map=_sir)
    _txt = _txt if isinstance(_txt, str) else str(_txt)
    _pdf = _strip9(A.generate_pdf_html_report(
        patient_name="T", age=_yr, sex="Male", weight=70, cl_cr=_crcl or 95,
        is_renal=_renal, is_preg=False, is_hepatic=_hep, allowed=_r["allowed"],
        warned=_r["warned"], banned=_r["banned"], preg_warn_items=_r["preg_warn"],
        organism=_org, specimen=_spec, interactions=_r["interactions"],
        sir_map=_sir, mdr_result=_r["mdr"], esbl_result=_r["mechanism"],
        phenotypes=_r["phenotypes"], return_html=True))

    for _d in _nA:
        if _d not in _txt:
            _dis.append(f"{_org}/{_spec}: {_d} recommended but absent from the text report")
        if _d not in _pdf:
            _dis.append(f"{_org}/{_spec}: {_d} recommended but absent from the PDF")
    for _w in _r["warned"]:
        if _w["name"] not in _pdf:
            _dis.append(f"{_org}/{_spec}: {_w['name']} cautioned but absent from the PDF")
    # Per-organ dose gating must hold in the PDF, for both organs.
    if not _renal and "Renal dose adjustment required" in _pdf and _DOSE9.search(_pdf):
        _dis.append(f"{_org}/{_spec}: renal dose printed for a non-renal patient")
    if not _hep and "Child-Pugh" in _pdf and _DOSE9.search(_pdf):
        _dis.append(f"{_org}/{_spec}: hepatic dose printed for a non-hepatic patient")

check("screen, PDF and text report agree across 120 randomised isolates",
      not _dis, "\n".join(_dis[:8]))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[10] The combination panel's own age resolution. It carries a SECOND")
print("    copy of the neonate test — get_combination_therapy decides whether to")
print("    attach neonatal cautions independently of the safety gate — and a")
print("    mutation widening it to every infant under one year survived every")
print("    suite. The gate's copy was tested; this one was not.")
# ═══════════════════════════════════════════════════════════════════════════
_xdr10 = {d: "R" for d in ("Meropenem", "Imipenem/Cilastatin", "Ceftazidime",
                           "Cefepime", "Ciprofloxacin", "Levofloxacin",
                           "Piperacillin + Tazobactam", "Aztreonam") if d in G}
_xdr10.update({d: "S" for d in ("Amikacin", "Colistin") if d in G})
_ph10 = A.detect_resistance_phenotypes("Pseudomonas aeruginosa", _xdr10)


def _neo_flagged_agents(age_years, age_months):
    """WHICH salvage agents carry a neonatal caution at this age.

    Returns the set, not a boolean. A boolean passes as long as ANY option is
    flagged, so removing four of the seven agents from the caution list left
    the check green — which is how a mutation deleting most of the neonatal
    cautions survived. Naming the agents is the difference between "something
    was flagged" and "the right things were flagged".
    """
    combos = A.get_combination_therapy(
        _ph10, is_pregnant=False, age_years=age_years, age_months=age_months,
        is_renal=False, cl_cr=None, is_hepatic=False)
    out = set()
    for c in combos:
        for o in c["data"]["options"]:
            if o.get("host_flagged") and ("وليد" in str(o.get("caution", ""))
                                          or "NEONATE" in str(o.get("caution", "")).upper()):
                out.add(o["combo"])
    return out


def _neo_flagged(age_years, age_months):
    return bool(_neo_flagged_agents(age_years, age_months))


_age_bad = []
# A true neonate must be flagged; an older infant must NOT be.
if not _neo_flagged(0, 0):
    _age_bad.append("0 months: a neonate was not flagged")
for _mo in (3, 6, 11):
    if _neo_flagged(0, _mo):
        _age_bad.append(f"{_mo} months: flagged as a neonate — the window widened "
                        f"to every infant, which is the gate defect all over again")
for _yr in (1, 5, 40):
    if _neo_flagged(_yr, None):
        _age_bad.append(f"{_yr} years: flagged as a neonate")
check("the combination panel flags neonates only, not every infant",
      not _age_bad, "\n".join(_age_bad))

# Every salvage agent WITHOUT neonatal data must carry the caution. Amikacin
# and colistin are deliberately excluded: amikacin is standard neonatal sepsis
# therapy and colistin has real neonatal experience, so flagging them would
# warn against the two agents a neonatologist is most likely to reach for.
_NEO_MUST = {"cefiderocol", "relebactam", "vaborbactam", "avibactam",
             "ceftolozane", "ceftaroline", "daptomycin"}
_flagged_txt = " ".join(_neo_flagged_agents(0, 0)).lower()
_unflagged = sorted(a for a in _NEO_MUST
                    if any(a in o["combo"].lower()
                           for c in A.get_combination_therapy(_ph10)
                           for o in c["data"]["options"])
                    and a not in _flagged_txt)
check("every salvage agent lacking neonatal data carries the caution",
      not _unflagged,
      f"no neonatal caution on: {_unflagged}\n"
      f"flagged were: {sorted(_neo_flagged_agents(0, 0))}")

# It must use the SHARED resolver, not a third private copy of the arithmetic.
_src10 = open(os.path.join(HERE, "streamlit_app.py"), encoding="utf-8").read()
check("the combination panel resolves age through clinical_utils, not its own copy",
      "resolve_age_years as _ray" in _src10 or "resolve_age_years(" in _src10,
      "a private age calculation here is a fourth place for the same defect")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[11] The app's OWN startup validator must be clean.")
print("    get_startup_validation_issues() has existed all along and NOTHING")
print("    ran it. A coverage sweep on 2026-08-03 called it once and it")
print("    reported four real defects introduced by this audit: three organism")
print("    profiles naming 'Benzathine Penicillin' as first-line when the")
print("    formulary key is 'Penicillin' — so Group A Strep silently lost its")
print("    drug of choice — and a Doxycycline reference to the Rickettsia")
print("    profile that had been deleted. A validator nobody runs is not a")
print("    validator; it is a comment that happens to be executable.")
# ═══════════════════════════════════════════════════════════════════════════
_startup = [i for i in A.get_startup_validation_issues() if "[SECURITY]" not in i]
check("the startup validator reports no table inconsistency",
      not _startup, "\n".join(_startup[:8]))

# The security line is environmental — it fires whenever no subscriber_hashes
# secret is configured, which is correct in a test environment and correct as a
# warning in production. It is asserted to EXIST rather than to be absent.
_sec = [i for i in A.get_startup_validation_issues() if "[SECURITY]" in i]
check("the validator still warns when no password hashes are configured",
      bool(_sec), "the security check disappeared")

# Every drug named anywhere in a profile must exist in the formulary. This is
# the specific class the validator caught, asserted directly so the failure
# names the drug rather than appearing as a generic validator message.
_ghost = []
for _o, _prof in A.ORGANISM_PROFILE.items():
    for _key in ("first_line", "second_line", "third_line", "alternatives"):
        for _d in (_prof.get(_key) or []):
            if _d not in G:
                _ghost.append(f"{_o}/{_key}: {_d!r} is not in the formulary")
check("no organism profile recommends a drug the formulary does not have",
      not _ghost, "\n".join(_ghost[:8]))

# And the reverse: no formulary entry may name an organism that was deleted.
_dangling = []
for _d, _info in G.items():
    for _o in (_info.get("organisms") or []):
        if _o not in A.ORGANISM_PROFILE:
            _dangling.append(f"{_d} names {_o!r}, which is not a selectable organism")
check("no formulary entry names a deleted organism",
      not _dangling, "\n".join(_dangling[:8]))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[12] A result that skipped a safety layer must SAY SO.")
print("    Found 2026-08-05 by import-failure injection: with safety_gate")
print("    unimportable, run_analysis() returned a full, confident result set")
print("    with gate_report={} and no other signal. The UI does raise a")
print("    'DEGRADED CLINICAL MODE' banner — but run_analysis() is the public")
print("    entry point now, and anything calling it programmatically received")
print("    un-gated recommendations indistinguishable from gated ones.")
# ═══════════════════════════════════════════════════════════════════════════
_r12 = A.run_analysis(Patient(age_years=45, sex="Male"), "Klebsiella spp.",
                      "Blood", {"Meropenem": "S", "Vancomycin": "S"})
check("a healthy run reports no degradation",
      _r12.get("degraded") == [], f"{_r12.get('degraded')}")

# An empty list on a healthy run proves nothing: a field hardcoded to [] passes
# it forever. A mutation doing exactly that survived on 2026-08-05. The field is
# only a signal if it goes NON-empty when a layer is actually missing, so force
# that state and check it is reported.
_saved_gate = A.SAFETY_GATE_AVAILABLE
try:
    A.SAFETY_GATE_AVAILABLE = False
    _rdeg = A.run_analysis(Patient(age_years=45, sex="Male"), "Klebsiella spp.",
                           "Blood", {"Meropenem": "S", "Vancomycin": "S"})
    check("a missing safety gate is REPORTED in the result, not just absent",
          bool(_rdeg.get("degraded")),
          "degraded stayed empty with SAFETY_GATE_AVAILABLE=False — the field "
          "cannot distinguish a healthy run from an ungated one")
    check("the degradation message names the layer that did not run",
          any("safety_gate" in str(x) for x in (_rdeg.get("degraded") or [])),
          f"{_rdeg.get('degraded')}")
    check("gate_applied is False when the gate could not run",
          _rdeg.get("gate_applied") is False)
finally:
    A.SAFETY_GATE_AVAILABLE = _saved_gate
check("a healthy run records that the gate was applied",
      _r12.get("gate_applied") is True)

_r12b = A.run_analysis(Patient(age_years=45, sex="Male"), "Klebsiella spp.",
                       "Blood", {"Meropenem": "S"}, apply_gate=False)
check("deliberately skipping the gate is recorded, not hidden",
      _r12b.get("gate_applied") is False)

# The field must exist on EVERY result, or a caller cannot rely on checking it.
_missing12 = []
for _o in list(ORGS)[:6]:
    for _s in list(SPECS)[:4]:
        _rr = A.run_analysis(Patient(age_years=40), _o, _s, {"Meropenem": "S"})
        if "degraded" not in _rr or "gate_applied" not in _rr:
            _missing12.append(f"{_o}/{_s}")
check("every result carries the degradation fields",
      not _missing12, f"{_missing12[:5]}")

# And the UI must still refuse to report when a critical module is missing.
_src12 = open(os.path.join(HERE, "streamlit_app.py"), encoding="utf-8").read()
check("a missing critical module still raises the DEGRADED banner",
      "DEGRADED CLINICAL MODE" in _src12 and "_MODULE_HEALTH" in _src12)
check("safety_gate is registered as CRITICAL in module health, not optional",
      "SAFETY_GATE_AVAILABLE, True)" in _src12,
      "safety_gate must be flagged critical — without it there is no terminal check")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[13] The combination panel must not offer an agent the organism is")
print("    INTRINSICALLY resistant to. Raised by external review 2026-08-06 and")
print("    confirmed at 50 occurrences in 1,500 randomised cases: the CRE panel")
print("    offered 'Colistin + Meropenem high-dose' for Proteus, Providencia,")
print("    Morganella and Serratia — all four intrinsically colistin-resistant.")
print("    They are Enterobacterales, so CRE fires correctly; the panel then")
print("    named a polymyxin that cannot work against them.")
print("    This is NOT the same as naming an AST-resistant drug — high-dose")
print("    extended infusion exists precisely for those. An intrinsic mechanism")
print("    is different in kind: no dose overcomes a missing target.")
# ═══════════════════════════════════════════════════════════════════════════
from clinical_data import INTRINSIC_RESISTANCE as _IR13                    # noqa: E402
from clinical_utils import org_matches as _om13                            # noqa: E402

_sir13 = {"Meropenem": "R", "Ertapenem": "R", "Colistin": "S",
          "Amikacin": "S", "Tigecycline": "S"}
_leak13 = []
for _org13 in ORGS:
    _intr13 = set()
    for _k13, _v13 in _IR13.items():
        if _om13(_org13, [_k13]):
            _intr13 |= set(_v13)
    if not _intr13:
        continue
    _r13 = A.run_analysis(Patient(age_years=50, sex="Male"), _org13, "Blood", _sir13)
    for _c13 in _r13["combinations"]:
        for _o13 in _c13["data"]["options"]:
            if str(_o13.get("combo", "")).upper().startswith("AVOID"):
                continue
            if _o13.get("intrinsically_inactive"):
                continue          # correctly annotated
            _norm13 = str(_o13["combo"]).lower().replace("+", "-").replace("/", "-").replace(" ", "")
            for _ag13 in sorted(G, key=len, reverse=True):
                _a13 = _ag13.lower().replace("+", "-").replace("/", "-").replace(" ", "")
                if _a13 and _a13 in _norm13:
                    _norm13 = _norm13.replace(_a13, "\x00" * len(_a13))
                    if _ag13 in _intr13:
                        _leak13.append(f"{_org13} ({_c13['phenotype']}): "
                                       f"intrinsically resistant to {_ag13}, panel "
                                       f"offers {_o13['combo'][:40]!r} unflagged")
check("no combination option offers an intrinsically inactive agent unflagged",
      not _leak13, "\n".join(sorted(set(_leak13))[:8]))

# The annotation must land on the RIGHT options only. Ampicillin-Sulbactam is a
# recommended CRAB agent; matching Acinetobacter's intrinsic "Ampicillin" inside
# it would wrongly condemn the drug of choice.
_over13 = []
_r_ab = A.run_analysis(Patient(age_years=50, sex="Male"),
                       "Acinetobacter baumannii", "Blood",
                       {"Meropenem": "R", "Imipenem/Cilastatin": "R",
                        "Ampicillin/Sulbactam": "S", "Colistin": "S"})
for _c13 in _r_ab["combinations"]:
    for _o13 in _c13["data"]["options"]:
        if "sulbactam" in str(_o13.get("combo", "")).lower() and _o13.get("intrinsically_inactive"):
            _over13.append(f"ampicillin-sulbactam wrongly condemned for CRAB: "
                           f"{_o13['intrinsically_inactive']}")
check("a combination product is not condemned for its lone component",
      not _over13, "\n".join(_over13))

print("\n" + "=" * 72)
print(f"{len(_PASS)} passed, {len(_FAIL)} failed")
if _FAIL:
    print("\nRESULT: FAILURES — see above")
    sys.exit(1)
print("\nRESULT: ALL GREEN")
print("\nNOTE: this suite walks the COMPOSED pipeline. It proves the parts are")
print("      wired to each other correctly; whether each part is clinically")
print("      right is test_engine_agreement.py and test_scenarios.py.")
