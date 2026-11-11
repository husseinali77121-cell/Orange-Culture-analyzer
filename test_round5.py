# -*- coding: utf-8 -*-
"""Round-5 suite — independent review of v4, 2026-11-12.

Every check pins a defect that was REPRODUCED on v4 (all 21 suites green)
before it was fixed. See CHANGELOG_2026-11-10.md, "الجولة الخامسة".

Run: python test_round5.py
"""
import contextlib, io, os, random, collections, sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Load the app exactly as test_round4 does (its Streamlit stub), silently.
with contextlib.redirect_stdout(io.StringIO()):
    import test_round4 as _R4
A = _R4.A
from clinical_utils import Patient                                  # noqa: E402
import ocr_parsing as OCR                                           # noqa: E402

G = A.ABX_GUIDELINES
SRC = open(os.path.join(HERE, "streamlit_app.py"), encoding="utf-8").read()
FAILS = []


def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok:
        FAILS.append(name)
        if detail != "":
            print("          ", str(detail)[:700])


def panel(text):
    """The S/I/R map the OCR loop builds from report text."""
    out = {}
    for line in text.splitlines():
        for d, v in OCR.parse_result_line(line.strip(), A.classify_sir_from_line):
            old = out.get(d)
            out[d] = max(old, v, key="SIR".index) if old and old != v else v
    return out


def bucket_of(r, drug):
    for b in ("allowed", "warned", "banned", "preg_warn"):
        for it in r[b]:
            if it["name"] == drug:
                return b, it
    return None, {}


# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] OCR: a line with two results gives each drug ITS OWN result")
# ═══════════════════════════════════════════════════════════════════════════
_cases = [
    ("Amikacin Sensitive   Ciprofloxacin Resistant", {"Amikacin": "S", "Ciprofloxacin": "R"}),
    ("Ciprofloxacin Resistant   Amikacin Sensitive", {"Amikacin": "S", "Ciprofloxacin": "R"}),
    ("Amikacin S    Ciprofloxacin R", {"Amikacin": "S", "Ciprofloxacin": "R"}),
    ("Gentamicin  R   Piperacillin/Tazobactam  S",
     {"Gentamicin": "R", "Piperacillin + Tazobactam": "S"}),
    ("AK S  CIP R", {"Amikacin": "S", "Ciprofloxacin": "R"}),
    ("Sensitive to: Amikacin, Meropenem", {"Amikacin": "S", "Meropenem": "S"}),
    ("Resistant to: Ciprofloxacin, Ceftriaxone, Cefepime",
     {"Ciprofloxacin": "R", "Ceftriaxone": "R", "Cefepime": "R"}),
    ("Amikacin, Gentamicin: Sensitive", {"Amikacin": "S", "Gentamicin": "S"}),
    # the first column lost its verdict: it must NOT inherit its neighbour's
    ("Amikacin      Ciprofloxacin S", {"Ciprofloxacin": "S"}),
    # one drug per line is unchanged
    ("Vancomycin   Sensitive", {"Vancomycin": "S"}),
    ("Ciprofloxacin  >=4  R", {"Ciprofloxacin": "R"}),
    ("Amoxicillin/Clavulanic acid R", {"Amoxicillin + Clavulanic acid": "R"}),
    ("Meropenem (MEM) 10 S", {"Meropenem": "S"}),
    ("Cefotaxime 5 I", {"Cefotaxime": "I"}),
    ("Trimethoprim-Sulfamethoxazole  S", {"Trimethoprim/Sulfamethoxazole": "S"}),
    # zone / MIC printed after the verdict
    ("Nitrofurantoin   S   32", {"Nitrofurantoin": "S"}),
    ("AMC S/CIP R/MEM S", {"Amoxicillin + Clavulanic acid": "S", "Ciprofloxacin": "R",
                           "Meropenem": "S"}),
]
_bad = [(t, panel(t), w) for t, w in _cases if panel(t) != w]
check("every (drug, result) pair on a line is read; no drug takes another drug's result",
      not _bad, _bad)
check("no RESISTANT drug is read as S on a two-column line",
      panel("Amikacin Sensitive   Ciprofloxacin Resistant").get("Ciprofloxacin") == "R")
check("the same drug printed twice with different results keeps the more resistant one",
      panel("Ciprofloxacin S\nCiprofloxacin R") == {"Ciprofloxacin": "R"})
check("the OCR loop uses parse_result_line", "parse_result_line(line, classify_sir_from_line)" in SRC)

# ═══════════════════════════════════════════════════════════════════════════
print("\n[2] OCR: a header or comment line is never a disk-code result row")
# ═══════════════════════════════════════════════════════════════════════════
_hdr = ["Sex: F   Age: 30 Y  Ref: Dr. S", "Ward: I   Sex: F", "Group: P  Result: R",
        "Heavy growth of Klebsiella, resistant strain",
        "Gram stain: gram negative bacilli  E coli  R", "Date of report: 12/11  R"]
_bad = {h: (OCR._scan_line_for_drugs(h), panel(h)) for h in _hdr
        if OCR._scan_line_for_drugs(h) or panel(h)}
check("header / prose lines put no antibiotic on the panel", not _bad, _bad)
_rows = {"AMC 30 S": ["Amoxicillin + Clavulanic acid"], "CIP5   R": ["Ciprofloxacin"],
         "F 300 mcg S": ["Nitrofurantoin"], "P 10 U R": ["Penicillin"],
         "CN10 R": ["Gentamicin"], "AK30 S": ["Amikacin"], "PIT S": ["Piperacillin + Tazobactam"]}
_bad = {k: OCR._scan_line_for_disk_codes(k) for k, v in _rows.items()
        if OCR._scan_line_for_disk_codes(k) != v}
check("genuine disk-code rows (code, potency, unit, verdict) still parse", not _bad, _bad)

# ═══════════════════════════════════════════════════════════════════════════
print("\n[3] OCR: age field")
# ═══════════════════════════════════════════════════════════════════════════
_age = [("Age: 0 Y 6 M", (0, 6)), ("Age: 2 Y 6 M", (2, None)),
        ("Age: 45 D.O.B: 1/1/1981", (45, None)),
        ("Age :   Date: 12/11/2026", (None, None)),
        ("السنة 2026\nAge: 45 Y", (45, None)),
        ("Age: 2026\nAge: 45 Y", (45, None)),
        ("Age: 5 D", (0, 0)), ("Age: 6 mo", (0, 6)), ("Age/Sex: 45/M", (45, None)),
        ("AGE/SEX : 25 Y / F", (25, None)), ("Age (years): 62", (62, None)),
        ("Patient age 62", (62, None)), ("Age: Adult", (None, None)),
        ("العمر: 3 شهور", (0, 3)), ("السن: 3 سنوات", (3, None))]
_bad = [(t, OCR.parse_patient_age(t), w) for t, w in _age if OCR.parse_patient_age(t) != w]
check("compound ages, an empty age field and 'D.O.B' are read correctly", not _bad, _bad)
check("'Age: 3 M' (months, or 3 years / Male?) is flagged as ambiguous",
      OCR.age_reading_is_ambiguous("Age: 3 M") and not OCR.age_reading_is_ambiguous("Age: 3 months")
      and not OCR.age_reading_is_ambiguous("Age/Sex: 45/M")
      and not OCR.age_reading_is_ambiguous("Age: 45 Y  Sex: M"))
check("the UI warns when the age was not read (default 25) or is ambiguous",
      'if patient.get("Age") is None:' in SRC and 'patient.get("AgeAmbiguous")' in SRC)

# ═══════════════════════════════════════════════════════════════════════════
print("\n[4] OCR: pus cells")
# ═══════════════════════════════════════════════════════════════════════════
_pus = [("Pus cells 15 - 20 /HPF many bacteria", "15 - 20"),
        ("Leukocyte esterase: +++\nPus cells: 2-4", "2-4"),
        ("Pus: 50-60", "50-60"), ("Pus cells: many", ">30"), ("Pus cells: >100", ">100"),
        ("Pus cells : over 100", "Over 100"), ("Pus cells / HPF    2-4", "2-4"),
        ("Pus cells: 20-25 /HPF\nRBCs: 2-4", "20-25"),
        ("Urine culture\nColony count: >100,000 CFU/mL\n", "")]
_bad = [(t, A.detect_pus_cells(t), w) for t, w in _pus if A.detect_pus_cells(t) != w]
check("the number after the label wins; a dipstick line is not a cell count", not _bad, _bad)

# ═══════════════════════════════════════════════════════════════════════════
print("\n[5] Cautions that left the loop early still meet the renal and hepatic checks")
# ═══════════════════════════════════════════════════════════════════════════
_esbl = {"Ceftriaxone": "R", "Ceftazidime": "R", "Cefepime": "S",
         "Piperacillin + Tazobactam": "S", "Meropenem": "S",
         "Cefoperazone": "S", "Cefoperazone + Sulbactam": "S"}
r = A.run_analysis(Patient(age_years=70, sex="Female", is_renal=True, cl_cr=15),
                   "E. coli", "Urine", _esbl)
for _d in ("Cefepime", "Piperacillin + Tazobactam"):
    _b, _it = bucket_of(r, _d)
    check(f"ESBL cystitis + CrCl 15: {_d} carries the renal dose adjustment",
          _b == "warned" and _it.get("renal_adjustment") and _it.get("crcl_used") == 15
          and "Renal: CrCl 15" in A.warned_note_for(_it, "en")
          and "Renal: CrCl 15" in A.warned_note_for(_it, "ar"),
          (_b, A.warned_note_for(_it, "en")[-200:]))
_txt = A.generate_report(patient_name="T", age=70, sex="Female", weight=60, cl_cr=15,
                         is_renal=True, is_preg=False, is_hepatic=False,
                         allowed=r["allowed"], warned=r["warned"], banned=r["banned"],
                         preg_warn_items=r["preg_warn"], organism="E. coli", specimen="Urine",
                         interactions=r["interactions"], sir_map=_esbl)
_i = _txt.find("Cefepime [Culture: S]")
check("the text report prints that adjustment under Cefepime",
      _i > 0 and "Renal: CrCl 15" in _txt[_i:_i + 600], _txt[_i:_i + 400])

_PC = Patient(age_years=50, is_hepatic=True, child_pugh="C")
r = A.run_analysis(_PC, "E. coli", "Urine", _esbl)
for _d in ("Cefoperazone", "Cefoperazone + Sulbactam"):
    _b, _it = bucket_of(r, _d)
    check(f"ESBL cystitis + Child-Pugh C: {_d} is BANNED (hepatic), not a caution",
          _b == "banned" and _it.get("category") == "hepatic", (_b, _it.get("category")))
r = A.run_analysis(_PC, "E. coli", "Urine",
                   {"Ertapenem": "R", "Meropenem": "S", "Cefoperazone": "S"})
check("possible carbapenemase + Child-Pugh C: Cefoperazone is banned",
      bucket_of(r, "Cefoperazone")[0] == "banned", bucket_of(r, "Cefoperazone")[0])
r = A.run_analysis(_PC, "Staphylococcus aureus", "Wound Swab",
                   {"Cephalexin": "R", "Vancomycin": "S", "Cefoperazone": "S"})
check("possible MRSA + Child-Pugh C: Cefoperazone is banned",
      bucket_of(r, "Cefoperazone")[0] == "banned", bucket_of(r, "Cefoperazone")[0])
r = A.run_analysis(Patient(age_years=50, is_hepatic=True, child_pugh="B"), "E. coli", "Urine", _esbl)
_b, _it = bucket_of(r, "Cefoperazone")
check("Child-Pugh B: the hepatic caution travels with the ESBL caution",
      _b == "warned" and "Hepatic (Child-Pugh B)" in A.warned_note_for(_it, "en"),
      (_b, A.warned_note_for(_it, "en")[-160:]))
r = A.run_analysis(Patient(age_years=40), "E. coli", "Urine", _esbl)
_b, _it = bucket_of(r, "Cefepime")
check("no renal / hepatic flag: the ESBL caution is unchanged",
      _b == "warned" and "Renal:" not in A.warned_note_for(_it, "en")
      and not _it.get("renal_adjustment"))

print("    fuzz: 4,000 random cases — hepatic AVOID never survives, renal adjustment never lost")
rnd = random.Random(20261112)
ORGS = list(A.ORGANISM_PROFILE); SPECS = list(A.SPECIMEN_TYPES); DR = list(G)
bad = collections.Counter(); ex = {}
for _ in range(4000):
    org, sp = rnd.choice(ORGS), rnd.choice(SPECS)
    sir = {d: rnd.choice("SSSIR") for d in rnd.sample(DR, rnd.randint(3, 16))}
    ren = rnd.random() < 0.5; hep = rnd.random() < 0.5
    cp = rnd.choice("ABC")
    clcr = rnd.choice([None, 5, 15, 25, 40, 55, 70]) if ren else None
    p = Patient(age_years=rnd.choice([0, 5, 30, 75]), age_months=None, sex=rnd.choice(["Female", "Male"]),
                is_renal=ren, cl_cr=clcr, is_hepatic=hep, child_pugh=cp)
    rr = A.run_analysis(p, org, sp, sir, uti_syndrome=rnd.choice([None, "upper", "lower"]))
    eff = A.resolve_crcl(clcr, ren)[0]
    for b in ("allowed", "warned", "preg_warn"):
        for it in rr[b]:
            d = it["name"]
            row = A.HEPATIC_DOSING.get(d)
            if hep and row and "avoid" in str(row.get(cp, ("", ""))[0]).lower():
                bad["hep"] += 1; ex.setdefault("hep", (org, sp, d, cp, b))
            lim = G[d].get("renal_limit", 0) or 0
            if ren and lim > 0 and eff is not None and eff <= lim:
                said = (it.get("warning_reason") == "renal_adjustment" or it.get("renal_adjustment")
                        or "renal" in [str(x).lower() for x in (it.get("gate_layers") or [])])
                if b == "allowed" or not said:
                    bad["renal"] += 1; ex.setdefault("renal", (org, sp, d, eff, b, it.get("warning_reason")))
check("no hepatic-AVOID agent is left in allowed / caution", not bad["hep"], ex.get("hep"))
check("every agent at or below its renal threshold says so", not bad["renal"], ex.get("renal"))

# ═══════════════════════════════════════════════════════════════════════════
print("\n[6] A new report starts a new patient — the remaining widgets")
# ═══════════════════════════════════════════════════════════════════════════
for _lbl, _k in (("specimen", 'key=f"specimen_sel_{_fh}"'),
                 ("organism", 'key=f"organism_sel_{_fh}_{culture_type}"'),
                 ("under-one-year box", 'key=f"under1_{_fh}"'),
                 ("age in months", 'key=f"age_months_{_fh}"'),
                 ("age in years", 'key=f"age_years_{_fh}"'),
                 ("sex", 'key=f"sex_sel_{_fh}"'),
                 ("weight", 'key=f"weight_{_fh}_{age}_{age_months}"')):
    check(f"the {_lbl} widget is keyed per uploaded file", _k in SRC)
check("_fh is defined before the first widget that uses it",
      0 < SRC.find("_fh = file_hash[:8]") < SRC.find('key=f"specimen_sel_{_fh}"'))
check("the summary image is regenerated when the weight changes",
      "{patient_name}|{age}|{age_months}|{sex}|{weight}|{cl_cr}" in SRC)

print("\n" + "=" * 72)
if FAILS:
    print(f"RESULT: {len(FAILS)} round-5 check(s) FAILED")
    sys.exit(1)
print("RESULT: all round-5 checks passed")
