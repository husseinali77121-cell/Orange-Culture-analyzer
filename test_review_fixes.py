#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_review_fixes.py — regression suite for the 2026-11-10 guideline review.

Every check below is a finding from the line-by-line review against CLSI M100
Ed33-Ed36, EUCAST v16, IDSA AMR Guidance 2026, IDSA cUTI 2025, ATS/IDSA HAP/VAP
2016, IDSA bacterial meningitis, ACOG and AAP. Each was first REPRODUCED as a
failing probe against the unmodified code, then fixed; the expected value here
is the guideline answer, not the old behaviour.

Grouped as in the review: C = critical, H = high, M = medium/text.

Run:  python test_review_fixes.py [--verbose]
"""
from __future__ import annotations

import os
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
    if __name__ == "__main__":
        sys.exit(2)

from clinical_utils import Patient                                 # noqa: E402
import ast_qa_engine as QA                                        # noqa: E402
import ast_reportability as RP                                    # noqa: E402
import ast_consistency as CO                                      # noqa: E402
import pathogenicity as PA                                        # noqa: E402
from abx_guidelines import ABX_GUIDELINES as G                    # noqa: E402
from organism_profile import ORGANISM_PROFILE as OP               # noqa: E402
import clinical_matrix as CM                                      # noqa: E402

ADULT = Patient(age_years=45, sex="Male")
WOMAN = Patient(age_years=30, sex="Female")


def run(org, spec, sir, patient=ADULT, **kw):
    return A.run_analysis(patient, org, spec, sir, **kw)


def where(res, drug):
    for b in ("allowed", "warned", "banned", "preg_warn"):
        for x in res[b]:
            if (x.get("name") if isinstance(x, dict) else x) == drug:
                return b, x
    return None, None


def phen(res):
    return {p.get("phenotype") for p in res["phenotypes"]}


print("=" * 72)
print("Orange Lab CDSS — 2026-11-10 guideline-review regression suite")
print("=" * 72)

# ═══════════════════════════════════════════════════════════════════════════
print("\n[C1] Novel agents on a confirmed carbapenemase are judged by enzyme class")
# ═══════════════════════════════════════════════════════════════════════════
CRE = {"Meropenem": "R", "Imipenem/Cilastatin": "R", "Ertapenem": "R",
       "Ceftriaxone": "R", "Ceftazidime": "R", "Cefepime": "R",
       "Piperacillin + Tazobactam": "R",
       "Ceftazidime + Avibactam": "S", "Meropenem + Vaborbactam": "S",
       "Imipenem + Relebactam": "S", "Cefiderocol": "S", "Aztreonam + Avibactam": "S"}
for ct, ok_drugs, bad_drugs in (
        ("KPC", {"Ceftazidime + Avibactam", "Meropenem + Vaborbactam", "Imipenem + Relebactam"}, set()),
        ("OXA-48-like", {"Ceftazidime + Avibactam"}, {"Meropenem + Vaborbactam", "Imipenem + Relebactam"}),
        ("NDM / VIM / IMP (MBL)", {"Aztreonam + Avibactam", "Cefiderocol"},
         {"Meropenem + Vaborbactam", "Imipenem + Relebactam"})):
    r = run("Klebsiella spp.", "Blood", CRE, carbapenemase_type=A.normalize_carbapenemase_type(ct))
    got_ok = {d for d in ok_drugs if where(r, d)[0] == "allowed"}
    got_bad = {d for d in bad_drugs if where(r, d)[0] == "banned"}
    check(f"{ct}: preferred agents recommended", got_ok == ok_drugs,
          f"recommended={sorted(got_ok)} expected={sorted(ok_drugs)}")
    check(f"{ct}: inactive agents avoided", got_bad == bad_drugs,
          f"banned={sorted(got_bad)} expected={sorted(bad_drugs)}")
r = run("Klebsiella spp.", "Blood", CRE)
_nov = [where(r, d) for d in ("Ceftazidime + Avibactam", "Meropenem + Vaborbactam",
                              "Imipenem + Relebactam", "Cefiderocol")]
check("unknown enzyme: no novel agent is banned; each warns with the type explanation",
      all(b == "warned" and x.get("warning_reason") == "novel_agent" and x.get("clinical_note")
          for b, x in _nov), str([(b, (x or {}).get("warning_reason")) for b, x in _nov]))
check("MBL: ceftazidime-avibactam alone is not recommended",
      where(run("Klebsiella spp.", "Blood", CRE, carbapenemase_type="MBL"),
            "Ceftazidime + Avibactam")[0] in ("warned", "banned"))
_cre_combo = run("Klebsiella spp.", "Blood", CRE, carbapenemase_type="MBL")["combinations"]
_cre_opts = [o["combo"] for c in _cre_combo if c["phenotype"] == "CRE" for o in c["data"]["options"]]
check("MBL combination panel shows aztreonam-avibactam and hides KPC-only agents",
      any("Aztreonam-Avibactam" in o for o in _cre_opts)
      and not any("Vaborbactam" in o for o in _cre_opts), str(_cre_opts))

# ═══════════════════════════════════════════════════════════════════════════
print("\n[C2] AmpC is not ESBL — cefepime S is the suggested agent")
# ═══════════════════════════════════════════════════════════════════════════
AMPC = {"Ceftriaxone": "R", "Ceftazidime": "R", "Cefotaxime": "R", "Cefoxitin": "R",
        "Cefepime": "S", "Meropenem": "S", "Ciprofloxacin": "S"}
r = run("Enterobacter cloacae", "Blood", AMPC)
check("Enterobacter + derepressed AmpC: mechanism is AmpC", r["mechanism"]["probability"] == "ampc",
      r["mechanism"])
check("cefepime S on AmpC blood isolate is recommended", where(r, "Cefepime")[0] == "allowed",
      where(r, "Cefepime"))
check("AMPC phenotype emitted with its panel", "AMPC" in phen(r)
      and any(c["phenotype"] == "AMPC" for c in r["combinations"]), phen(r))

# ═══════════════════════════════════════════════════════════════════════════
print("\n[C3] Proteeae imipenem R alone is not CRE")
# ═══════════════════════════════════════════════════════════════════════════
for org in ("Proteus mirabilis", "Morganella morganii", "Providencia spp.", "Proteus vulgaris"):
    sir = {"Imipenem/Cilastatin": "R", "Meropenem": "S", "Ertapenem": "S", "Ceftriaxone": "S"}
    r = run(org, "Urine", sir, WOMAN)
    check(f"{org}: no CRE phenotype, no carbapenemase", "CRE" not in phen(r)
          and r["mechanism"]["probability"] not in ("carbapenemase", "possible_carbapenemase"),
          f"{phen(r)} {r['mechanism'].get('probability')}")
    _qa = [i.message for i in QA.run_ast_qa_engine(org, "Urine", sir)
           if getattr(i, "severity", "") in ("HIGH", "CRITICAL")]
    check(f"{org}: QA engine raises no HIGH carbapenem alarm", not any("Imipenem" in m for m in _qa), _qa)
sir = {"Imipenem/Cilastatin": "R", "Meropenem": "R", "Ertapenem": "R", "Ceftriaxone": "R"}
check("Proteus with meropenem R still flags CRE", "CRE" in phen(run("Proteus mirabilis", "Blood", sir)))
_qa = [i.message for i in QA.run_ast_qa_engine("Pseudomonas aeruginosa", "Blood",
                                               {"Ertapenem": "R", "Imipenem/Cilastatin": "S"})]
check("Pseudomonas ertapenem R + imipenem S: no 'early CRE' alarm", not any("Ertapenem=R" in m for m in _qa), _qa)

# ═══════════════════════════════════════════════════════════════════════════
print("\n[C4] Dose texts match the product labels")
# ═══════════════════════════════════════════════════════════════════════════
check("cefepime CrCl 11-29 is once daily", "CrCl 11-29: 500mg-2g q24h" in G["Cefepime"]["renal_note_en"])
check("levofloxacin 750 mg -> q48h at CrCl 20-49", "750 mg q48h" in G["Levofloxacin"]["renal_note_en"])
check("cefoperazone-sulbactam has a renal limit (sulbactam is renally cleared)",
      G["Cefoperazone + Sulbactam"]["renal_limit"] == 30
      and "Cefoperazone + Sulbactam" in CM.RENAL_RULES)
check("cefazolin renal bands halve the dose", "half the usual dose" in G["Cefazolin"]["renal_note_en"])
check("cefuroxime sodium 10-20 band is 750 mg, signature withdrawn",
      "CrCl 10-20: 750mg q12h" in G["Cefuroxime sodium"]["renal_note_en"]
      and not G["Cefuroxime sodium"].get("dose_countersigned"))
check("imipenem follows the current label (adjust below CrCl 90)",
      G["Imipenem/Cilastatin"]["renal_limit"] == 89)
check("tigecycline Child-Pugh C maintenance is 25 mg q12h",
      "25mg q12h" in str(A.HEPATIC_DOSING["Tigecycline"]["C"]))
_unsigned_edits = [d for d in ("Cefepime", "Levofloxacin", "Cefoperazone + Sulbactam", "Cefazolin",
                               "Cefuroxime sodium", "Imipenem/Cilastatin")
                   if G[d].get("dose_countersigned") or not G[d].get("dose_review")]
check("every rewritten dose band is queued for countersignature, none carries a stale signature",
      not _unsigned_edits, _unsigned_edits)

# ═══════════════════════════════════════════════════════════════════════════
print("\n[C5] Aminoglycosides for P. aeruginosa (CLSI M100 Ed33)")
# ═══════════════════════════════════════════════════════════════════════════
r = run("Pseudomonas aeruginosa", "Blood", {"Gentamicin": "S", "Tobramycin": "S", "Amikacin": "S",
                                            "Ceftazidime": "S"})
check("gentamicin is avoided for P. aeruginosa", where(r, "Gentamicin")[0] == "banned")
check("amikacin outside urine is a caution", where(r, "Amikacin")[0] in ("warned", "banned"))
check("reportability suppresses gentamicin for P. aeruginosa",
      any(i["id"].startswith("nobp_gentamicin_pseudomonas")
          for i in RP.check_reportability("Pseudomonas aeruginosa", {"Gentamicin": "S"})))
check("gentamicin formulary row no longer lists P. aeruginosa",
      "Pseudomonas aeruginosa" not in G["Gentamicin"]["organisms"])

# ═══════════════════════════════════════════════════════════════════════════
print("\n[H6/H7] Therapy panels follow IDSA AMR Guidance 2026")
# ═══════════════════════════════════════════════════════════════════════════
CT = A.COMBINATION_THERAPY
check("CRAB panel leads with sulbactam-durlobactam + carbapenem",
      CT["CRAB"]["options"][0]["combo"].startswith("Sulbactam-Durlobactam"))
check("CRAB panel cites AIDA for what AIDA tested (colistin +/- meropenem)",
      any("AIDA" in o["ref"] and "Meropenem" in o["combo"] for o in CT["CRAB"]["options"]))
check("STENO panel leads with cefiderocol", CT["STENO"]["options"][0]["combo"].startswith("Cefiderocol"))
check("MRSA/VRE panels no longer cite the Gram-negative IDSA guidance",
      not any("IDSA AMR" in o["ref"] for k in ("MRSA", "VRE") for o in CT[k]["options"]))
check("new formulary rows exist with renal rules and Reserve status",
      all(d in G and G[d]["aware"] == "Reserve" and d in CM.RENAL_RULES and d in CM.SITE_PENETRATION
          for d in ("Aztreonam + Avibactam", "Sulbactam + Durlobactam")))
r = run("Stenotrophomonas maltophilia", "Blood", {"Cefiderocol": "S", "Aztreonam + Avibactam": "S",
                                                   "Trimethoprim/Sulfamethoxazole": "S"})
check("Steno: cefiderocol recommended", where(r, "Cefiderocol")[0] == "allowed", where(r, "Cefiderocol"))
check("Steno: aztreonam-avibactam not banned", where(r, "Aztreonam + Avibactam")[0] in ("allowed", "warned"))
check("Steno panel shown", any(c["phenotype"] == "STENO" for c in r["combinations"]))
r = run("Acinetobacter baumannii", "Sputum", {"Meropenem": "R", "Imipenem/Cilastatin": "R",
                                               "Sulbactam + Durlobactam": "S"})
check("CRAB: sulbactam-durlobactam recommended", where(r, "Sulbactam + Durlobactam")[0] == "allowed")
check("sul-dur is avoided outside Acinetobacter",
      where(run("E. coli", "Blood", {"Sulbactam + Durlobactam": "S"}), "Sulbactam + Durlobactam")[0] == "banned")

# ═══════════════════════════════════════════════════════════════════════════
print("\n[H8] No false intrinsic bans")
# ═══════════════════════════════════════════════════════════════════════════
check("H. influenzae ampicillin S is offered",
      where(run("H. influenzae", "Sputum", {"Ampicillin": "S"}), "Ampicillin")[0] == "allowed")
check("VRE ampicillin S is offered",
      where(run("VRE", "Urine", {"Ampicillin": "S", "Vancomycin": "R"}, WOMAN), "Ampicillin")[0] == "allowed")
check("Serratia (low-risk AmpC) ceftriaxone S is offered",
      where(run("Serratia marcescens", "Blood", {"Ceftriaxone": "S"}), "Ceftriaxone")[0] == "allowed")
b, x = where(run("Enterobacter cloacae", "Blood", {"Ceftriaxone": "S", "Cefepime": "S"}), "Ceftriaxone")
check("Enterobacter ceftriaxone S is a caution with the IDSA note, not an intrinsic ban",
      b == "warned" and x.get("warning_reason") == "organism_caution", (b, (x or {}).get("warning_reason")))
check("MRSA: ceftaroline is offered", where(run("MRSA", "Blood", {"Ceftaroline": "S", "Oxacillin": "R"}),
                                            "Ceftaroline")[0] == "allowed")

# ═══════════════════════════════════════════════════════════════════════════
print("\n[H9] Upper UTI excludes bladder-only agents")
# ═══════════════════════════════════════════════════════════════════════════
U = {"Nitrofurantoin": "S", "Fosfomycin": "S", "Norfloxacin": "S", "Ciprofloxacin": "S"}
r = run("E. coli", "Urine", U, WOMAN, uti_syndrome="upper")
check("pyelonephritis: nitrofurantoin / fosfomycin / norfloxacin avoided",
      all(where(r, d)[0] == "banned" for d in ("Nitrofurantoin", "Fosfomycin", "Norfloxacin")),
      [where(r, d)[0] for d in U])
check("pyelonephritis: ciprofloxacin still offered", where(r, "Ciprofloxacin")[0] == "allowed")
check("cystitis keeps nitrofurantoin",
      where(run("E. coli", "Urine", U, WOMAN, uti_syndrome="lower"), "Nitrofurantoin")[0] == "allowed")
check("auto mode reads fever as upper UTI",
      A.resolve_uti_syndrome(A.UTI_SYNDROME_OPTIONS[0], ["Fever (> 38°C)"]) == "upper")

# ═══════════════════════════════════════════════════════════════════════════
print("\n[H10] Durations")
# ═══════════════════════════════════════════════════════════════════════════
D = A.TREATMENT_DURATION_DB
check("GNB bacteraemia standard 7 days with oral step-down", D["Bacteremia_GNB"]["standard"] == 7
      and D["Bacteremia_GNB"]["po_days"] > 0)
check("cUTI 7 days", D["UTI_complicated"]["standard"] == 7)
check("HAP/VAP 7 days", D["HAP_VAP"]["standard"] == 7)
for org, key in (("Neisseria meningitidis", "Meningitis_meningococcal"),
                 ("H. influenzae", "Meningitis_haemophilus"),
                 ("Listeria monocytogenes", "Meningitis_listeria"),
                 ("Streptococcus agalactiae (Group B)", "Meningitis_GBS"),
                 ("E. coli", "Meningitis_GNB")):
    d = A.get_treatment_duration("CSF", org, "", 30, "Male", False, [], "severe")
    check(f"meningitis duration by organism: {org}", d["label"] == D[key]["label"], d["label"])
for org, key in (("Coagulase-negative Staphylococci", "Bacteremia_CoNS"),
                 ("Enterococcus faecalis", "Bacteremia_Enterococcus"),
                 ("Streptococcus pneumoniae", "Bacteremia_Strep"),
                 ("Staphylococcus lugdunensis", "Bacteremia_MSSA")):
    d = A.get_treatment_duration("Blood", org, "", 50, "Male", False, [], "moderate")
    check(f"bacteraemia duration by organism: {org}", d["label"] == D[key]["label"], d["label"])
check("bacteraemia no longer forces IV-only", "bacteremia" not in A.ALWAYS_IV_SYNDROMES)

# ═══════════════════════════════════════════════════════════════════════════
print("\n[H11/H12] QA engine and colistin")
# ═══════════════════════════════════════════════════════════════════════════
_qa = [i.message for i in QA.run_ast_qa_engine("Staphylococcus aureus", "Urine", {"Nitrofurantoin": "S"})]
check("S. aureus nitrofurantoin S is not 'implausible'", not any("Nitrofurantoin" in m for m in _qa), _qa)
_qa = [(i.severity, i.detail) for i in QA.run_ast_qa_engine(
    "Pseudomonas aeruginosa", "Blood", {"Levofloxacin": "R", "Ciprofloxacin": "S"})
    if "Levofloxacin=R" in i.message]
check("levo R / cipro S is a MEDIUM prompt without the wrong potency claim",
      _qa and _qa[0][0] == "MEDIUM" and "higher intrinsic activity" not in _qa[0][1], _qa)
check("colistin disc rule fires on an S result",
      any(i["id"].startswith("rare_colistin_disc")
          for i in CO.check_consistency("Klebsiella spp.", {"Colistin": "S"})))
b, x = where(run("Klebsiella spp.", "Blood", {"Colistin": "S"}), "Colistin")
check("colistin S is a caution with the CLSI/BMD note", b == "warned" and x.get("clinical_note"))

# ═══════════════════════════════════════════════════════════════════════════
print("\n[H13] Pregnancy")
# ═══════════════════════════════════════════════════════════════════════════
PREG = Patient(age_years=28, sex="Female", is_pregnant=True)
r = run("Listeria monocytogenes", "Blood", {"Ampicillin": "S", "Gentamicin": "S",
                                            "Trimethoprim/Sulfamethoxazole": "S"}, PREG)
check("gentamicin in pregnancy is a physician decision, not a ban", where(r, "Gentamicin")[0] == "preg_warn")
check("TMP-SMX in pregnancy is trimester-dependent caution",
      where(r, "Trimethoprim/Sulfamethoxazole")[0] == "preg_warn")
check("matrix: clarithromycin denied in pregnancy, FQ / aminoglycosides cautioned",
      "Clarithromycin" in CM.PREGNANCY_DENY and "Ciprofloxacin" in CM.PREGNANCY_CAUTION
      and "Gentamicin" in CM.PREGNANCY_CAUTION and "Gentamicin" not in CM.PREGNANCY_DENY)

# ═══════════════════════════════════════════════════════════════════════════
print("\n[H14] New organisms and OCR boundaries")
# ═══════════════════════════════════════════════════════════════════════════
for o in ("Citrobacter koseri", "Proteus vulgaris", "Staphylococcus saprophyticus",
          "Staphylococcus lugdunensis"):
    check(f"{o}: profile + canonical + panel map", o in OP and CM.canonical_organism(o) == o)
check("OCR: 'gastric' is not Group A Strep",
      A.detect_organism("gastric aspirate culture: no growth") is None)
check("OCR: 'consistent with' is not CoNS",
      A.detect_organism("findings consistent with contamination") is None)
check("OCR: S. saprophyticus maps to its own profile",
      A.detect_organism("isolated staphylococcus saprophyticus 10^5")
      == "Staphylococcus saprophyticus")

# ═══════════════════════════════════════════════════════════════════════════
print("\n[M] Medium-severity and text fixes")
# ═══════════════════════════════════════════════════════════════════════════
b, _ = where(run("Klebsiella spp.", "Urine", {"Fosfomycin": "S"}, WOMAN), "Fosfomycin")
check("fosfomycin outside E. coli is a caution (no breakpoint)", b == "warned")
check("MDR Gram-negative set no longer counts nitrofurans",
      "Nitrofurans" not in A.MDR_CATEGORIES_GRAM_NEG and "Glycylcyclines" in A.MDR_CATEGORIES_GRAM_NEG)
check("staph MDR set counts daptomycin / ceftaroline / teicoplanin",
      {"Lipopeptides", "Anti-MRSA Cephalosporins"} <= A.MDR_CATEGORIES_STAPH
      and "Teicoplanin" in A.MDR_CATEGORIES["Glycopeptides"])
p = PA.assess_pathogenicity("Urine", "E. coli", "2x10^4", "Pure", [], "", "", "", 0, "Male", [])
check("infant urine 2x10^4 with nothing else is not 'treat'", "TREAT" not in str(p.get("verdict", "")).upper()
      or p["score"] < 60, (p["score"], p.get("verdict")))
check("BAL threshold 10^4", any("BAL ≥ 10⁴" in str(v.get("culture_threshold", ""))
                                for v in A.INFECTION_SYNDROMES.values()))
check("GBS note distinguishes intrapartum prophylaxis from antepartum treatment",
      "10⁵" in OP["Streptococcus agalactiae (Group B)"]["urine_note"])
b, _ = where(run("Streptococcus pyogenes (Group A)", "Sputum", {"Trimethoprim/Sulfamethoxazole": "S"}),
             "Trimethoprim/Sulfamethoxazole")
check("GAS TMP-SMX outside skin infection is avoided (CLSI Ed36)", b == "banned")
b, _ = where(run("Streptococcus pyogenes (Group A)", "Wound Swab", {"Trimethoprim/Sulfamethoxazole": "S"}),
             "Trimethoprim/Sulfamethoxazole")
check("GAS TMP-SMX for skin infection is allowed with the CLSI note", b in ("allowed", "warned"))
b, x = where(run("Staphylococcus aureus", "Blood", {"Penicillin": "S"}), "Penicillin")
check("penicillin S staph needs a negative penicillinase test", b == "warned", b)
b, x = where(run("Klebsiella spp.", "Blood", {"Ceftriaxone": "S"},
                 Patient(age_years=40, sex="Male", allergies=["Cephalosporin"])), "Ceftriaxone")
check("documented cephalosporin allergy bans the class", b == "banned" and x.get("category") == "allergy")
b, x = where(run("Klebsiella spp.", "Blood", {"Meropenem": "S"},
                 Patient(age_years=40, sex="Male", allergies=["Penicillin — severe / anaphylaxis"])),
             "Meropenem")
check("penicillin allergy -> carbapenem cross-reactivity caution, not a ban", b == "warned", b)
check("doxycycline child note follows AAP Red Book 2024", G["Doxycycline"]["child_safe"] is True)
check("amox-clav is no longer 'first choice for uncomplicated UTI'",
      "خيار أول" not in G["Amoxicillin + Clavulanic acid"]["specimen_notes"]["Urine"])
check("cipro is no longer 'the only anti-pseudomonal FQ'",
      "الوحيد" not in G["Ciprofloxacin"]["specimen_notes"]["Sputum"])

print()
print("=" * 72)
print(f"{len(_PASS)} passed, {len(_FAIL)} failed")
if _FAIL:
    print("\nRESULT: FAILURES — see above")
    sys.exit(1)
print("\nRESULT: ALL GREEN")
