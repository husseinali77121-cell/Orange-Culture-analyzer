# -*- coding: utf-8 -*-
"""Round-4 suite — final logic review, 2026-11-11.

Every check below pins a defect that was REPRODUCED on the release before it
was fixed (see CHANGELOG_2026-11-10.md, "الجولة الرابعة"). None of the
twenty earlier suites caught these: most live where two correct layers meet —
the pregnancy bucket and the safety gate, the OCR header and the age field, the
sidebar and the next patient.

Run: python test_round4.py
"""
import os, re, sys, random, collections, types, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
FAILS = []


def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok:
        FAILS.append(name)
        if detail != "":
            print("          ", str(detail)[:700])


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
    if __name__ == "__main__":
        sys.exit(2)

from clinical_utils import Patient                                 # noqa: E402
import clinical_matrix as CM                                       # noqa: E402
import final_checklist as FC                                       # noqa: E402
import ocr_parsing as OCR                                          # noqa: E402
import report_service as RS                                        # noqa: E402

G = A.ABX_GUIDELINES
SRC = open(os.path.join(HERE, "streamlit_app.py"), encoding="utf-8").read()


def names(items):
    return [i["name"] for i in items]


def buckets(r):
    return {b: names(r[b]) for b in ("allowed", "warned", "banned", "preg_warn")}


# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] Pregnancy-caution drugs still meet the hepatic, renal, I and gate checks")
# ═══════════════════════════════════════════════════════════════════════════
P_CP_C = Patient(age_years=28, sex="Female", is_pregnant=True, is_hepatic=True, child_pugh="C")
r = A.run_analysis(P_CP_C, "E. coli", "Urine",
                   {"Trimethoprim/Sulfamethoxazole": "S", "Nitrofurantoin": "S", "Cephalexin": "S"})
b = buckets(r)
check("pregnant + Child-Pugh C: TMP-SMX and nitrofurantoin are BANNED (hepatic), "
      "not offered as pregnancy cautions",
      {"Trimethoprim/Sulfamethoxazole", "Nitrofurantoin"} <= set(b["banned"])
      and not ({"Trimethoprim/Sulfamethoxazole", "Nitrofurantoin"} & set(b["preg_warn"])), b)

r = A.run_analysis(Patient(age_years=28, sex="Female", is_pregnant=True), "E. coli", "CSF",
                   {"Gentamicin": "S", "Amikacin": "S", "Ceftriaxone": "S", "Meropenem": "S"})
b = buckets(r)
check("pregnant + meningitis: gentamicin / amikacin go to Avoid via the gate (no CSF penetration)",
      {"Gentamicin", "Amikacin"} <= set(b["banned"]) and not ({"Gentamicin", "Amikacin"} & set(b["preg_warn"])), b)
check("the pregnancy-bucket gate move is recorded in gate_report",
      any(m.get("from") == "preg_warn" and m.get("to") == "banned"
          for m in r["gate_report"].get("moves", [])), r["gate_report"].get("moves"))

r = A.run_analysis(Patient(age_years=28, sex="Female", is_pregnant=True, is_renal=True, cl_cr=20),
                   "E. coli", "Urine", {"Gentamicin": "S", "Ciprofloxacin": "I", "Meropenem": "S"})
_pw = {i["name"]: i for i in r["preg_warn"]}
check("pregnant + CrCl 20: the renal adjustment travels with the pregnancy item",
      "Gentamicin" in _pw and "Renal" in _pw["Gentamicin"].get("preg_note", "")
      and _pw["Gentamicin"].get("renal_adjustment"), _pw.get("Gentamicin", {}).get("preg_note"))
check("pregnant + Ciprofloxacin I: the Intermediate result is stated on the pregnancy item",
      "Ciprofloxacin" in _pw and "Culture result I" in _pw["Ciprofloxacin"].get("preg_note", ""))

print("    fuzz: 2,500 random cases — no pregnancy-bucket item the matrix would refuse")
rnd = random.Random(20261111)
ORGS = list(A.ORGANISM_PROFILE); SPECS = list(A.SPECIMEN_TYPES); DR = list(G)
bad = collections.Counter(); ex = {}
for _ in range(2500):
    org, sp = rnd.choice(ORGS), rnd.choice(SPECS)
    sir = {d: rnd.choice("SSSIR") for d in rnd.sample(DR, rnd.randint(3, 14))}
    preg = rnd.random() < 0.5
    ren = rnd.random() < 0.3
    hep = rnd.random() < 0.3
    p = Patient(age_years=rnd.choice([20, 30, 40]), sex="Female", is_pregnant=preg,
                is_renal=ren, cl_cr=rnd.choice([None, 10, 25, 40, 70]) if ren else None,
                is_hepatic=hep, child_pugh=rnd.choice("ABC"))
    rr = A.run_analysis(p, org, sp, sir, uti_syndrome=rnd.choice([None, "upper", "lower"]))
    allnames = collections.Counter(x for v in buckets(rr).values() for x in v)
    if any(c > 1 for c in allnames.values()):
        bad["dup"] += 1; ex.setdefault("dup", (org, sp))
    if [d for d in sir if d in G and d not in allnames]:
        bad["missing"] += 1; ex.setdefault("missing", (org, sp))
    for it in rr["preg_warn"]:
        v = CM.evaluate(it["name"], org, sp, strict_unknown=False, age_years=p.effective_age_years,
                        is_pregnant=True, cl_cr=p.cl_cr, is_renal=ren, is_hepatic=hep,
                        child_pugh=p.child_pugh)
        if v.level == CM.DENY:
            bad["preg_deny"] += 1; ex.setdefault("preg_deny", (org, sp, it["name"]))
        if sir.get(it["name"]) == "R":
            bad["preg_R"] += 1; ex.setdefault("preg_R", (org, sp, it["name"]))
check("no drug sits in two buckets", not bad["dup"], ex.get("dup"))
check("no tested formulary drug disappears", not bad["missing"], ex.get("missing"))
check("no pregnancy-bucket item is one the matrix DENIES", not bad["preg_deny"], ex.get("preg_deny"))
check("no R result reaches the pregnancy bucket", not bad["preg_R"], ex.get("preg_R"))

# ═══════════════════════════════════════════════════════════════════════════
print("\n[2] OCR: the age comes from the age field, not from any 'N days' in the report")
# ═══════════════════════════════════════════════════════════════════════════
_REP = ("Patient: A  Age: 45 Y  Sex: Male\nSpecimen: Urine\n"
        "Growth of E. coli after 2 days incubation\nRepeat in 7 days if symptomatic\n")
_cases = [
    (_REP, (45, None)),
    ("Age: 6/12\n", (0, 6)),
    ("Age: 18 months\n", (1, None)),
    ("Age: 20 days\n", (0, 0)),
    ("Age: 3 weeks\n", (0, 0)),
    ("العمر: 3 شهور\n", (0, 3)),
    ("Age/Sex: 45/M\n", (45, None)),
    ("Name: B\nAge: 32 years\nReport valid for 3 months\n", (32, None)),
    ("Baby of Mona, 10 days old\n", (0, 0)),
    ("Page 2 of 3\nNo age printed\n", (None, None)),
    ("Patient 67 years\n", (67, None)),
]
_bad = [(t, OCR.parse_patient_age(t), want) for t, want in _cases if OCR.parse_patient_age(t) != want]
check("parse_patient_age reads every header form correctly", not _bad, _bad)
_spec_cases = {
    "Specimen: CSF\nRBCs: 50 (red blood cells)\nPus cells: 200": "CSF",
    "Stool culture\nOccult blood: positive\nPus cells: 10-12": "Stool",
    "Urine culture\nPus cells: 20-25\nRBCs: 2-4 (red blood cells)": "Urine",
    "Specimen: Wound swab\nPus cells: many": "Wound Swab",
    "Blood culture: aerobic bottle positive at 18 h": "Blood",
    "Sputum culture\nPus cells >25/LPF": "Sputum",
}
_bad = {t[:24]: A.detect_specimen(t.lower()) for t, w in _spec_cases.items()
        if A.detect_specimen(t.lower()) != w}
check("specimen: a CSF or stool report that mentions 'blood' as an analyte is not read as Blood",
      not _bad, _bad)
check("detect_age: an adult whose report says 'after 2 days incubation' is 45, not 0",
      A.detect_age(_REP) == 45 and A.detect_age_months(_REP) is None,
      (A.detect_age(_REP), A.detect_age_months(_REP)))

# ═══════════════════════════════════════════════════════════════════════════
print("\n[3] A new report starts a new patient")
# ═══════════════════════════════════════════════════════════════════════════
_ss = st.session_state
_ss.update({"patho_result": {"verdict": "OLD"}, "pus_cells_text": "20-25", "colony_count": "10^3",
            "patient_name_final": "Old Patient", "child_pugh_class": "A",
            "pus_cells_input": "20-25", "patho_symp_urine": ["Fever (> 38°C)"],
            "severity_manual_Urine_E. coli": True})
A.reset_patient_state()
check("reset_patient_state clears the previous pathogenicity verdict, microscopy and name",
      _ss.get("patho_result") is None and _ss.get("pus_cells_text") == ""
      and _ss.get("patient_name_final") == "" and "pus_cells_input" not in _ss
      and "patho_symp_urine" not in _ss and "severity_manual_Urine_E. coli" not in _ss,
      {k: _ss.get(k) for k in ("patho_result", "pus_cells_text", "patient_name_final")})
check("Child-Pugh falls back to the fail-closed grade C for the next patient",
      _ss.get("child_pugh_class") == "C")
_i_up = SRC.find("old_hash and old_hash != file_hash")
check("the upload handler calls reset_patient_state() when the file changes",
      _i_up > 0 and "reset_patient_state()" in SRC[_i_up:_i_up + 600])
for _lbl, _k in (("renal flag", 'key=f"renal_flag_{_fh}"'), ("creatinine", 'key=f"scr_{_fh}"'),
                 ("hepatic flag", 'key=f"hepatic_{_fh}"'), ("pregnancy", 'key=f"preg_{_fh}"'),
                 ("current meds", 'key=f"meds_{_fh}"'), ("allergies", 'key=f"allergies_input_{_fh}"'),
                 ("carbapenemase class", 'key=f"carb_type_input_{_fh}"'),
                 ("UTI syndrome", 'key=f"uti_syndrome_input_{_fh}"')):
    check(f"the {_lbl} widget is keyed per uploaded file", _k in SRC)

# ═══════════════════════════════════════════════════════════════════════════
print("\n[4] Paediatric renal function: bedside Schwartz, never Cockcroft-Gault")
# ═══════════════════════════════════════════════════════════════════════════
check("Schwartz: 5-year-old, 110 cm, SCr 0.4 -> ~113.6",
      abs((A.calc_paediatric_egfr(110, 0.4, 5) or 0) - 113.6) < 0.2, A.calc_paediatric_egfr(110, 0.4, 5))
check("term neonate (k 0.45): 50 cm, SCr 0.5 -> 45",
      A.calc_paediatric_egfr(50, 0.5, 0, 0) == 45.0, A.calc_paediatric_egfr(50, 0.5, 0, 0))
check("no height -> no paediatric eGFR (never a guessed number)",
      A.calc_paediatric_egfr(0, 0.5, 5) is None and A.calc_paediatric_egfr(None, 0.5, 5) is None)
check("the UI uses Cockcroft-Gault only from 18 years",
      "if s_cr > 0 and age >= 18:" in SRC and "calc_paediatric_egfr(_height, s_cr, age, age_months)" in SRC)
check("under 2 years a low GFR does not switch adult renal dosing on by itself",
      "if cl_cr is not None and age < 2 and not _renal_flag:" in SRC)

# ═══════════════════════════════════════════════════════════════════════════
print("\n[5] Pus cells / RBCs are read only from their own line")
# ═══════════════════════════════════════════════════════════════════════════
check("colony count '>100,000' is not read as pus cells",
      A.detect_pus_cells("Urine culture\nColony count: >100,000 CFU/mL\n") == "")
check("'Moderate growth' is not read as pus cells",
      A.detect_pus_cells("Urine culture\nModerate growth of Klebsiella\n") == "")
check("a labelled pus line still parses", A.detect_pus_cells("Pus cells: 20-25 /HPF\nRBCs: 2-4") == "20-25")
check("a labelled verbal reading still parses", A.detect_pus_cells("Pus cells: many\n") == ">30")
check("'WBC: TNTC' is not an RBC value", A.detect_rbcs("WBC: TNTC\nRBCs: \n") != "TNTC")
check("'RBCs: TNTC' is", A.detect_rbcs("Pus cells: 2-4\nRBCs TNTC /HPF\n") == "TNTC")

# ═══════════════════════════════════════════════════════════════════════════
print("\n[6] Treatment duration names the right syndrome")
# ═══════════════════════════════════════════════════════════════════════════
def _lbl(sp, org):
    return A.get_treatment_duration(sp, org, "", 40, "Male", False, [], "moderate")["label"]
_exp = [("CSF", "Staphylococcus aureus", "Staphylococcal"), ("CSF", "MRSA", "Staphylococcal"),
        ("CSF", "Coagulase-negative Staphylococci", "Staphylococcal"),
        ("CSF", "Enterococcus spp.", "other"), ("CSF", "Gram-positive cocci (unidentified)", "other"),
        ("CSF", "E. coli", "Gram-Negative"), ("CSF", "Streptococcus pneumoniae", "Pneumococcal"),
        ("Blood", "Staphylococcus spp.", "MSSA"), ("Blood", "Gram-positive cocci (unidentified)", "Gram-positive cocci"),
        ("Blood", "Listeria monocytogenes", "Listeria"), ("Blood", "Anaerobes (لاهوائيات)", "Anaerobic"),
        ("Blood", "Coagulase-negative Staphylococci", "Coagulase-negative"), ("Blood", "E. coli", "GNB")]
_bad = [(sp, o, _lbl(sp, o)) for sp, o, w in _exp if w not in _lbl(sp, o)]
check("no Gram-positive isolate is labelled Gram-negative; Staphylococcus spp. is not a contaminant course",
      not _bad, _bad)
check("upper UTI -> the duration engine is asked for pyelonephritis (one helper for UI, PDF, pipeline)",
      A.duration_syndrome_key({"syndrome": "Urinary Tract Infection (UTI)"}, "upper", "Urine") == "pyelonephritis"
      and A.duration_syndrome_key({"syndrome": "Urinary Tract Infection (UTI)"}, None, "Urine")
      == "Urinary Tract Infection (UTI)"
      and SRC.count("duration_syndrome_key(syndrome_info, _uti_syn_now, culture_type)") == 2)
_d = A.run_analysis(Patient(age_years=30, sex="Female"), "E. coli", "Urine", {"Ciprofloxacin": "S"},
                    uti_syndrome="upper")["duration"]
check("run_analysis: pyelonephritis duration for an upper UTI", "Pyelonephritis" in _d["label"], _d["label"])

# ═══════════════════════════════════════════════════════════════════════════
print("\n[7] Classification and mechanism")
# ═══════════════════════════════════════════════════════════════════════════
_m = A.classify_mdr("Gram-positive cocci (unidentified)", {"Vancomycin": "R", "Ciprofloxacin": "R"})
check("unidentified Gram-positive cocci are NOT classified with the Gram-negative categories",
      _m.get("gram") == "positive" and "Magiorakos 2012, Tables 3-5" not in str(_m.get("basis")), _m)
for _org in ("Salmonella spp.", "Shigella spp."):
    _r = A.run_analysis(Patient(age_years=30), _org, "Blood",
                        {"Ceftriaxone": "R", "Cefotaxime": "R", "Piperacillin + Tazobactam": "S",
                         "Cefepime": "S", "Meropenem": "S"})
    check(f"{_org} with an ESBL pattern: pip-tazo and cefepime are not recommended",
          _r["mechanism"].get("probability") == "high"
          and not ({"Piperacillin + Tazobactam", "Cefepime"} & set(names(_r["allowed"]))),
          (_r["mechanism"].get("probability"), names(_r["allowed"])))

# ═══════════════════════════════════════════════════════════════════════════
print("\n[8] What reaches the screen and the report")
# ═══════════════════════════════════════════════════════════════════════════
check("the Resistance Classification panel renders possible_carbapenemase",
      'elif prob == "possible_carbapenemase":' in SRC)
check("the sidebar Resistance Profile renders possible_carbapenemase, plasmid AmpC and CR-PA",
      'elif _prob == "possible_carbapenemase":' in SRC and 'elif _prob == "crpa":' in SRC
      and 'elif _prob in ("ampc", "ampc_plasmid"):' in SRC)
_sir = {"Ertapenem": "R", "Meropenem": "S", "Ceftriaxone": "S", "Ciprofloxacin": "S"}
_ra = A.run_analysis(Patient(age_years=40), "E. coli", "Urine", _sir)
_txt = A.generate_report(patient_name="T", age=40, sex="Male", weight=70, cl_cr=None,
                         is_renal=False, is_preg=False, is_hepatic=False,
                         allowed=_ra["allowed"], warned=_ra["warned"], banned=_ra["banned"],
                         preg_warn_items=_ra["preg_warn"], organism="E. coli", specimen="Urine",
                         interactions=_ra["interactions"], sir_map=_sir)
check("the text report prints the possible-carbapenemase tier", "POSSIBLE" in _txt.upper()
      and "CARBAPENEMASE" in _txt.upper() and "mCIM" in _txt)
check("the report cache key hashes bucket CONTENTS and the inputs it used to miss",
      all(t in SRC for t in ("_bsig(allowed)", "_bsig(preg_warn_items)", "sorted(interactions_alerts",
                             "_child_pugh_now}", "sorted(allergies", "_carb_type_now}", "_uti_syn_now}")))
check("the summary image no longer heads CR-PA / possible carbapenemase as 'ESBL ALERT'",
      "CR-P. aeruginosa ALERT" in open(os.path.join(HERE, "report_service.py"), encoding="utf-8").read())
_lab = re.search(r"cat_labels = \{(.*?)\}", SRC, re.S).group(1)
_cats = set(re.findall(r'build_banned_item\(\s*(?:name=)?[^,]+,\s*(?:category=)?"([a-z_]+)"', SRC, re.S))
_cats |= {"safety_gate"}
_missing = sorted(c for c in _cats if f'"{c}"' not in _lab)
check("every Avoid category the engine emits has an on-screen label", not _missing, _missing)

# ═══════════════════════════════════════════════════════════════════════════
print("\n[9] Severity, syndrome, pathogenicity in pregnancy, disk codes, checklist")
# ═══════════════════════════════════════════════════════════════════════════
_sv = A.run_analysis(Patient(age_years=30, sex="Female", is_renal=True, cl_cr=None), "E. coli", "Urine",
                     {"Ciprofloxacin": "S"})["severity"]
check("renal flag with an UNKNOWN clearance makes a UTI complicated (was read as CrCl 95)",
      _sv["suggested"] == "moderate" and any("Renal" in x for x in _sv["reasons"]), _sv)
check("a man's UTI is a complicated UTI on the syndrome panel",
      A.get_infection_syndrome("Urine", "E. coli", 40, False, sex="Male")["sub_type"] == "Complicated UTI")
check("age > 65 alone is no longer labelled 'Severe CAP'",
      "Severe" not in A.get_infection_syndrome("Sputum", "Streptococcus pneumoniae", 70, False)["sub_type"])
check("the sidebar pregnancy flag reaches the pathogenicity engine",
      'if is_preg and "Pregnant" not in patho_host:' in SRC)
_disk = {"CIP5   R": ["Ciprofloxacin"], "AK30 S": ["Amikacin"], "CN10 R": ["Gentamicin"],
         "CN30 S": ["Cephalexin"], "PIT S": ["Piperacillin + Tazobactam"]}
_bad = {k: OCR._scan_line_for_disk_codes(k) for k, v in _disk.items() if OCR._scan_line_for_disk_codes(k) != v}
check("disk codes fused with their potency are read (exact code still wins)", not _bad, _bad)
_ck = FC.build_final_checklist("E. coli", "Urine", {"Gentamicin": "S"}, allowed=[], warned=[],
                               banned=[], preg_warn=[{"name": "Gentamicin"}])
_opt = [c for c in _ck if c["key"] == "options"][0]
check("final checklist: a pregnancy-caution option is an option (warn, not 'no option')",
      _opt["status"] == FC.WARN, _opt)
check("Patient(is_hepatic=True) without a grade fails CLOSED to Child-Pugh C",
      Patient(is_hepatic=True).child_pugh == "C")
_sw = A.evaluate_iv_po_switch("Linezolid", "Bloodstream Infection (BSI) / Bacteremia", True, True, True, 5,
                              organism="Staphylococcus aureus")
check("IV->PO: S. aureus bacteraemia is a blocker (the rule could never fire before)",
      not _sw["can_switch"] and any("aureus" in b for b in _sw["blockers"]), _sw["blockers"])
check("IV->PO: Ofloxacin is matched as Ofloxacin, not inside 'Ciprofloxacin'",
      A.evaluate_iv_po_switch("Ofloxacin", "", True, True, True, 3)["matched_drug"] == "Ofloxacin")
_de = A.evaluate_deescalation([{"name": "Meropenem", "aware": "Watch"}], [], 72, True, mdr_level="XDR")
check("de-escalation: an XDR isolate is a reserve organism (MDR level now reaches the advisor)",
      _de["is_reserve_organism"] and not _de["can_deescalate"], _de)
_de = A.evaluate_deescalation([], [{"phenotype": "DTR_PA"}], 72, True)
check("de-escalation: DTR-P. aeruginosa is a reserve organism", _de["is_reserve_organism"])

print("\n" + "=" * 72)
if FAILS:
    print(f"RESULT: {len(FAILS)} round-4 check(s) FAILED")
    sys.exit(1)
print("RESULT: all round-4 checks passed")
