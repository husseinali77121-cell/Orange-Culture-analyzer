# -*- coding: utf-8 -*-
"""Round-2 review regression suite — 2026-11-10.

One check per defect found in the second line-by-line review, plus the three
features added with it: pathogenicity engine v3 (incl. spinal cord injury),
organisms not identified to species level, and Gram-variable stains.
Run: python test_round2.py
"""
import sys, types, contextlib, io

import os
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

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



import abx_guidelines as AG, clinical_data as CD, clinical_matrix as CM
import organism_profile as OP, guideline_registry as GR, pathogenicity as PG
import ast_reportability as AR

G = AG.ABX_GUIDELINES
FAILS = []


def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok:
        FAILS.append(name)
        if detail != "":
            print("          ", detail)


def run(org, spec, sir):
    with contextlib.redirect_stdout(io.StringIO()):
        return A.run_analysis(Patient(age_years=45, sex="Male"), org, spec, sir)


def where(r, drug):
    for b in ("allowed", "warned", "banned", "preg_warn"):
        for x in r.get(b, []):
            if (x.get("name") if isinstance(x, dict) else x) == drug:
                return b
    return None


def canon(lst):
    return {A._canon_med(x) for x in lst}


print("\n[1] Drug interactions")
for d in ("Meropenem", "Ertapenem", "Imipenem/Cilastatin", "Meropenem + Vaborbactam",
          "Imipenem + Relebactam"):
    check(f"{d} declares the valproate interaction",
          "valproate" in canon(G[d].get("interacts_with", [])))
_sel = canon(A.COMMON_MEDS)
_dead = sorted({f"{d}: {i}" for d, row in G.items() for i in row.get("interacts_with", [])
                if A._canon_med(i) not in _sel and "tyramine" not in i.lower()})
check("every declared interaction can be selected in the UI (no dead entries)", not _dead, _dead)
check("'spironolactone ...' is not read as an iron supplement",
      A._canon_med("Spironolactone / K-sparing diuretics") == "k_sparing")
check("'carbamazepine' is not read as an ARB", A._canon_med("carbamazepine") != "arb")
check("ciprofloxacin + tizanidine is declared",
      "tizanidine" in canon(G["Ciprofloxacin"]["interacts_with"]))

print("\n[2] Renal / hepatic")
for d in ("Ceftazidime + Avibactam", "Ceftolozane + Tazobactam", "Meropenem + Vaborbactam",
          "Imipenem + Relebactam", "Cefiderocol", "Ceftaroline"):
    check(f"{d}: the gate adjusts, never refuses, on renal function alone",
          CM.RENAL_RULES[d][1] is None)
_h = A.HEPATIC_DOSING
check("metronidazole in Child-Pugh C is a 50% reduction, not a ban",
      "avoid" not in _h["Metronidazole"]["C"][0].lower())
check("clindamycin in Child-Pugh C is caution, not avoid",
      "avoid" not in _h["Clindamycin"]["C"][0].lower())
_v = CM.evaluate("Trimethoprim/Sulfamethoxazole", "E. coli", "Urine", sir="S",
                 is_hepatic=True, child_pugh="B")
check("matrix no longer denies TMP-SMX at Child-Pugh B (engine only cautions there)",
      getattr(_v, "level", None) != CM.DENY, getattr(_v, "level", None))
_pt = G["Piperacillin + Tazobactam"]["renal_note_en"]
check("pip-tazo states both label columns (general 2.25 g q6h at CrCl 20-40)",
      "CrCl 20-40: 2.25 g q6h" in _pt and "Nosocomial pneumonia" in _pt and "0.75 g" in _pt)

print("\n[3] Pregnancy / class consistency")
check("all fluoroquinolones share one pregnancy status",
      len({G[d]["preg_status"] for d in G if "fluoroquinolone" in G[d]["class"].lower()}) == 1)
check("tigecycline is a pregnancy deny in the matrix too", "Tigecycline" in CM.PREGNANCY_DENY)
check("tetracycline is AWaRe Access", G["Tetracycline"]["aware"] == "Access")

print("\n[4] Intrinsic resistance")
IR = CD.INTRINSIC_RESISTANCE
check("P. vulgaris: amox-clav, amp-sulb and cefoxitin are not intrinsic",
      not {"Amoxicillin + Clavulanic acid", "Ampicillin/Sulbactam", "Cefoxitin"} & set(IR["proteus vulgaris"]))
check("P. vulgaris: ampicillin and cefuroxime remain intrinsic",
      {"Ampicillin", "Cefuroxime"} <= set(IR["proteus vulgaris"]))
check("Morganella: cefoxitin is not intrinsic but stays not-recommended via the profile",
      "Cefoxitin" not in IR["morganella morganii"]
      and "Cefoxitin" in OP.ORGANISM_PROFILE["Morganella morganii"]["avoid"])
check("Hafnia alvei is intrinsically colistin-resistant", "Colistin" in IR["hafnia alvei"])
check("Salmonella and Shigella list cefoxitin (CLSI cephamycin warning)",
      "Cefoxitin" in IR["salmonella"] and "Cefoxitin" in IR["shigella"])
_ids = {r["id"] for r in AR.REPORTABILITY_RULES} if hasattr(AR, "REPORTABILITY_RULES") else set()
check("the split Proteus rule and the Hafnia rule are registered",
      {"intr_proteus_vulgaris_penneri", "intr_hafnia_colistin"} <= set(GR.RULES))

print("\n[5] Engine: results that test S but must not be offered")
r = run("Streptococcus pneumoniae", "Sputum", {"Erythromycin": "R", "Azithromycin": "S", "Clarithromycin": "S"})
check("erythromycin R bans azithromycin and clarithromycin (CLSI)",
      where(r, "Azithromycin") == "banned" and where(r, "Clarithromycin") == "banned")
r = run("Enterococcus faecalis", "Blood", {"Ampicillin": "S", "Ciprofloxacin": "S", "Levofloxacin": "S", "Meropenem": "S"})
check("enterococcus in blood: fluoroquinolones and meropenem are not offered",
      where(r, "Ciprofloxacin") == "banned" and where(r, "Levofloxacin") == "banned"
      and where(r, "Meropenem") == "banned", {d: where(r, d) for d in ("Ciprofloxacin", "Levofloxacin", "Meropenem")})
r = run("Enterococcus faecalis", "Urine", {"Ampicillin": "S", "Ciprofloxacin": "S"})
check("enterococcus in urine: ciprofloxacin is still available", where(r, "Ciprofloxacin") != "banned")
r = run("Enterococcus faecium", "Blood", {"Ampicillin": "R", "Penicillin": "S", "Imipenem/Cilastatin": "S", "Vancomycin": "S"})
check("enterococcus: ampicillin R predicts penicillin and imipenem",
      where(r, "Penicillin") == "banned" and where(r, "Imipenem/Cilastatin") == "banned")
r = run("Streptococcus pneumoniae", "CSF", {"Penicillin": "I", "Ceftriaxone": "I", "Vancomycin": "S"})
check("pneumococcal meningitis: penicillin I is treated as resistant", where(r, "Penicillin") == "banned")
check("pneumococcal meningitis: ceftriaxone I is a warning (add vancomycin)", where(r, "Ceftriaxone") == "warned")
r = run("Streptococcus pneumoniae", "Blood", {"Levofloxacin": "S", "Ciprofloxacin": "S", "Ceftazidime": "S", "Moxifloxacin": "S"})
check("pneumococcus: ciprofloxacin and ceftazidime are not offered; levofloxacin and moxifloxacin are",
      where(r, "Ciprofloxacin") == "banned" and where(r, "Ceftazidime") == "banned"
      and where(r, "Levofloxacin") in ("allowed", "warned") and where(r, "Moxifloxacin") in ("allowed", "warned"),
      {d: where(r, d) for d in ("Ciprofloxacin", "Ceftazidime", "Levofloxacin", "Moxifloxacin")})
r = run("Staphylococcus aureus", "Blood", {"Oxacillin": "S", "Ceftazidime": "S", "Ciprofloxacin": "S", "Ampicillin": "S"})
check("S. aureus: ceftazidime not offered; ciprofloxacin in blood and ampicillin S are cautions",
      where(r, "Ceftazidime") == "banned" and where(r, "Ciprofloxacin") == "warned"
      and where(r, "Ampicillin") == "warned", {d: where(r, d) for d in ("Ceftazidime", "Ciprofloxacin", "Ampicillin")})
r = run("E. coli", "Blood", {"Ceftriaxone": "R", "Piperacillin + Tazobactam": "S", "Cefepime": "S", "Meropenem": "S"})
check("E. coli blood, ceftriaxone R on a thin panel = ESBL high (IDSA proxy)",
      (r.get("mechanism") or {}).get("probability") == "high", (r.get("mechanism") or {}).get("probability"))
check("... so pip-tazo and cefepime are not plainly recommended",
      where(r, "Piperacillin + Tazobactam") != "allowed" and where(r, "Cefepime") != "allowed")
r = run("Stenotrophomonas maltophilia", "Blood", {"Trimethoprim/Sulfamethoxazole": "S", "Levofloxacin": "S"})
check("Stenotrophomonas: TMP-SMX and levofloxacin carry the CLSI 'not alone' caution",
      where(r, "Trimethoprim/Sulfamethoxazole") == "warned" and where(r, "Levofloxacin") == "warned")

print("\n[6] Durations")
D = A.TREATMENT_DURATION_DB
check("CAP (moderate) standard course is 5 days", D["CAP_moderate"]["standard"] == 5)
check("CAP (severe) standard course is 7 days", D["CAP_severe"]["standard"] == 7)
check("complicated intra-abdominal infection is 4-7 days after source control",
      D["Intraabdominal_severe"]["days"] == (4, 7))
check("no reference to a non-existent 'IDSA MRSA 2025 update'",
      "updated 2025" not in str(D["Bacteremia_MRSA"]["ref"]))

print("\n[7] Governance")
check("no dose row is left in the countersignature queue", not [d for d in G if G[d].get("dose_review")])
check("owner-approved dose rows never carry a clinician signature",
      not [d for d in G if G[d].get("dose_owner_approved") and G[d].get("dose_countersigned")])
_pend = sorted(k for k, v in GR.RULES.items() if v.get("verified") == "pending")
check("only QC003 (a heuristic with no primary locus) remains source-pending", _pend == ["QC003"], _pend)
check("no rule claims Dr. Tarek's signature for a row added on 2026-11-10",
      not [k for k, v in GR.RULES.items() if v.get("owner_approved") and v.get("countersigned_by")])

print("\n[8] Pathogenicity engine v3")
P = PG.assess_pathogenicity
S = ["Dysuria / Frequency / Urgency"]
x = P("Urine", "E. coli", "10^5", "Pure growth", S, "20-25", "", "WBCs + Gram Negative Rods", 30, "Female", [],
      collection_method="Midstream clean-catch")
check("classic cystitis is a true infection", x["category"] == "TRUE_INFECTION", x["score"])
x = P("Urine", "E. coli", "", "Pure", [], "", "", "", 40, "Male", [])
check("no symptoms entered + no count = INSUFFICIENT DATA, not 'contaminant'",
      x["category"] == "INSUFFICIENT_DATA" and "Symptoms" in x["missing_inputs"])
x = P("Urine", "E. coli", "10^5", "Pure growth", ["Asymptomatic"], "", "", "", 78, "Female", ["Diabetes"])
check("asymptomatic bacteriuria is recognised WITHOUT pyuria and is not treated",
      x["abu_detected"] and "ABU_NO_TREAT" in x["special_flags"])
x = P("Urine", "E. coli", "10^5", "Pure growth", ["Asymptomatic"], "15", "", "", 28, "Female", ["Pregnant"])
check("ABU in pregnancy is treated", "ABU_TREAT" in x["special_flags"])
a = P("Urine", "E. coli", "10^5", "Pure growth", ["Cloudy / Foul-smelling urine only"], "50", "", "", 80, "Male",
      [], collection_method="Midstream clean-catch")["score"]
b = P("Urine", "E. coli", "10^5", "Pure growth", ["Cloudy / Foul-smelling urine only"], "50", "", "", 80, "Male",
      ["Urinary catheter"], collection_method="Indwelling catheter (Foley)")["score"]
check("a urinary catheter never RAISES the score", b <= a, (a, b))
x = P("Urine", "Klebsiella spp.", "10^5", "Pure growth", ["Asymptomatic"], "30", "", "", 40, "Male",
      [PG.HOST_SCI_PARA], collection_method="Intermittent catheterisation (in-out / CIC)")
check("paraplegia + asymptomatic bacteriuria = do not treat, with the SCI notes",
      "ABU_NO_TREAT" in x["special_flags"] and "SCI" in x["special_flags"]
      and any("النخاع" in n for n in x["notes"]))
x = P("Urine", "Pseudomonas aeruginosa", "10^3", "Pure growth",
      ["Increased spasticity (SCI)", "Fever (> 38°C)"], "30", "", "", 40, "Male",
      [PG.HOST_SCI_QUAD], collection_method="Intermittent catheterisation (in-out / CIC)")
check("quadriplegia + fever/spasticity at 10^3 from a catheter specimen = infection",
      x["category"] == "TRUE_INFECTION" and "10^3" in x["threshold"], (x["score"], x["threshold"]))
y = P("Urine", "Pseudomonas aeruginosa", "10^3", "Pure growth", ["Increased spasticity (SCI)"], "30", "", "",
      40, "Male", [], collection_method="Midstream clean-catch")
check("SCI symptoms only count when SCI or a catheter is present",
      y["score"] < x["score"] and "SCI" not in y["special_flags"])
x = P("Urine", "E. coli", "10^5", "Pure growth", ["Fever (> 38°C)"], "20", "", "", 0, "Male", [],
      collection_method="Bag specimen (infant)")
check("an infant bag specimen is never diagnostic on its own", x["category"] != "TRUE_INFECTION")
x = P("Blood", "Coagulase-negative Staphylococci", "", "", [], "", "", "", 50, "Male", [], blood_source="Single bottle positive")
check("CoNS in a single bottle = contaminant", x["score"] < 25)
x = P("Blood", "Coagulase-negative Staphylococci", "", "Pure growth", [], "", "", "", 50, "Male",
      ["Central line / PICC"], sirs_criteria=["a", "b"], blood_source="Multiple bottles positive")
check("CoNS in multiple sets with a line and SIRS = true infection", x["category"] == "TRUE_INFECTION", x["score"])
for org in ("E. coli", "Acinetobacter spp.", "Gram-negative bacilli (unidentified)"):
    x = P("Blood", org, "", "", [], "", "", "", 50, "Male", [])
    check(f"{org} in blood with no other data is still significant", x["category"] == "TRUE_INFECTION", x["score"])
for org in ("Gram-positive cocci (unidentified)", "Staphylococcus spp."):
    x = P("Blood", org, "", "", [], "", "", "", 50, "Male", [])
    check(f"{org} in blood is never called a contaminant before identification",
          x["score"] >= 45 and "BLOOD_PENDING_ID" in x["special_flags"], x["score"])
x = P("CSF", "Coagulase-negative Staphylococci", "", "Pure growth", [], "", "", "", 50, "Male", [])
check("CoNS in CSF without a device = possible contaminant, not 'treat immediately'",
      "CSF_SKIN_FLORA" in x["special_flags"] and "Treat Immediately" not in x["verdict"])
x = P("CSF", "Coagulase-negative Staphylococci", "", "Pure growth", [], "", "", "", 50, "Male",
      ["CSF shunt / EVD / Recent neurosurgery"])
check("CoNS in CSF with a shunt = significant", "CSF_ALWAYS_SIGNIFICANT" in x["special_flags"])
x = P("Wound Swab", "Pseudomonas aeruginosa", "", "Mixed growth", ["No local signs of infection"], "", "", "",
      45, "Male", [PG.HOST_SCI_PARA], wound_type="Pressure ulcer / Bed sore")
check("pressure-ulcer swab without signs = colonisation, with the bone-biopsy note",
      x["category"] == "COLONISATION" and any("osteomyelitis" in n for n in x["notes"]))
x = P("Wound Swab", "Pseudomonas aeruginosa", "", "Mixed growth", [], "", "", "", 45, "Male", [],
      wound_type="Chronic / Diabetic")
check("signs not entered is not the same as signs absent", "Local signs of infection" in x["missing_inputs"]
      and x["category"] != "COLONISATION")
x = P("Sputum", "Candida albicans", "", "Pure growth", ["Fever (> 38°C)"], "", "", "", 45, "Male", [],
      sputum_pus_cells="30", sputum_epithelial="5")
check("Candida in sputum is colonisation", "RESPIRATORY_CANDIDA" in x["special_flags"] and x["score"] < 45)

print("\n[9] Gram stain")
check("Gram-variable options are offered",
      sum("Variable" in o for o in PG.GRAM_STAIN_OPTIONS) >= 2)
x = P("Urine", "Acinetobacter spp.", "10^5", "Pure growth", S, "20", "", "WBCs + Gram Variable Rods / Coccobacilli",
      60, "Male", [])
check("Gram-variable + Acinetobacter is reported as consistent, not discordant",
      "GRAM_VARIABLE" in x["special_flags"] and "GRAM_DISCORDANT" not in x["special_flags"]
      and any("Acinetobacter" in n for n in x["notes"]))
x = P("Urine", "E. coli", "10^5", "Pure growth", S, "20", "", "WBCs + Gram Positive Cocci", 30, "Female", [])
check("stain/culture discordance is flagged", "GRAM_DISCORDANT" in x["special_flags"])
a = P("Wound Swab", "Staphylococcus aureus", "", "", [], "", "", "Organisms بدون WBCs", 40, "Male", [])["score"]
b = P("Wound Swab", "Staphylococcus aureus", "", "", [], "", "", "مش متعملة", 40, "Male", [])["score"]
check("'organisms without WBCs' is now scored (it matched no branch before)", a != b, (a, b))

print("\n[10] Organisms not identified to species level")
NEW = [k for k, v in OP.ORGANISM_PROFILE.items() if "unspeciated_as" in v]
check("12 genus- / Gram-level organisms are selectable", len(NEW) == 12, NEW)
check("every one of them survives the matrix canonicaliser under its own name",
      all(CM.canonical_organism(o) == o for o in NEW))
check("every one of them is detected from report text",
      all(A.detect_organism(f"Organism isolated: {o}") == o for o in NEW),
      [(o, A.detect_organism(f"Organism isolated: {o}")) for o in NEW if A.detect_organism(f"Organism isolated: {o}") != o])
CRAB = {"Meropenem": "R", "Imipenem/Cilastatin": "R", "Ceftazidime": "R", "Ciprofloxacin": "R", "Colistin": "S",
        "Trimethoprim/Sulfamethoxazole": "S", "Amikacin": "R", "Piperacillin + Tazobactam": "R"}
r = run("Acinetobacter spp.", "Sputum", CRAB)
check("Acinetobacter spp. with carbapenem R is flagged CRAB",
      "CRAB" in [p.get("phenotype") for p in (r.get("phenotypes") or [])])
r = run("Pseudomonas spp.", "Urine", {"Trimethoprim/Sulfamethoxazole": "S", "Ceftazidime": "S"})
check("Pseudomonas spp. inherits intrinsic TMP-SMX resistance", where(r, "Trimethoprim/Sulfamethoxazole") != "allowed")
r = run("Staphylococcus spp.", "Blood", {"Oxacillin": "R", "Vancomycin": "S", "Cefazolin": "S"})
check("Staphylococcus spp. with oxacillin R is handled as MRSA",
      "MRSA" in [p.get("phenotype") for p in (r.get("phenotypes") or [])] and where(r, "Cefazolin") == "banned")
r = run("Gram-negative bacilli (unidentified)", "Blood", {"Ceftriaxone": "R", "Meropenem": "S", "Vancomycin": "S"})
check("an unidentified GNB gets no ESBL inference and no Gram-positive agent",
      not (r.get("mechanism") or {}).get("probability") and where(r, "Vancomycin") != "allowed")
r = run("Proteus spp.", "Urine", {"Ampicillin": "S", "Ceftriaxone": "S"})
check("Proteus spp.: ampicillin S carries the indole-positive caution", where(r, "Ampicillin") == "warned")
check("the plain 'Acinetobacter baumannii' report still maps to the species",
      A.detect_organism("Organism: Acinetobacter baumannii") == "Acinetobacter baumannii")

print("\n" + "=" * 72)
if FAILS:
    print(f"RESULT: {len(FAILS)} FAILED")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("RESULT: all round-2 checks passed")
