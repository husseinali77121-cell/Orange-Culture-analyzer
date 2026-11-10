# -*- coding: utf-8 -*-
"""Round-3 suite — 2026-11-11.

Two kinds of check:
  * FUZZ / PROPERTY tests. Thousands of random cases (fixed seeds, so a failure
    reproduces) run against invariants that must hold for ANY input: nothing
    resistant or intrinsically resistant is recommended, no drug sits in two
    buckets, the pathogenicity score never falls as the count rises, a host
    factor that is not evidence never raises it, the English report carries no
    Arabic. These found three real defects on the day they were written.
  * The features added with them: the stand-alone Pathogenicity PDF, the
    compact AST-QA sheet, the Gram-stain entry gate and the final checklist.
Run: python test_round3.py
"""
import sys, os, re, io, random, contextlib, collections, inspect
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



import abx_guidelines as AG, clinical_data as CD, organism_profile as OPm
import pathogenicity as PG, final_checklist as FC
from clinical_utils import Patient as PT

G = AG.ABX_GUIDELINES
ORGS = list(OPm.ORGANISM_PROFILE)
DRUGS = list(G)
AR = re.compile(r"[\u0600-\u06FF]")


def text_of(html):
    return re.sub(r"<[^>]+>", "\n", re.sub(r"<style.*?</style>", "", html, flags=re.S))


def intrinsic(o):
    ol = " ".join(o.lower().split()); out = set()
    for k, v in CD.INTRINSIC_RESISTANCE.items():
        if k in ol or ol in k:
            out |= set(v)
    return out


print("\n[1] Therapy engine — 1,500 random cases, fixed seed")
rnd = random.Random(20261111)
bad = collections.Counter(); ex = {}; recs_seen = 0
_fields = set(inspect.signature(PT).parameters)
for _ in range(1500):
    o = rnd.choice(ORGS); s = rnd.choice(["Urine", "Blood", "Sputum", "Wound Swab", "Pus", "CSF", "Stool"])
    sir = {d: rnd.choice("SSSIRR") for d in rnd.sample(DRUGS, rnd.randint(1, 22))}
    kw = dict(age_years=rnd.choice([0, 1, 5, 12, 30, 45, 70, 88]), sex=rnd.choice(["Male", "Female"]))
    preg = kw["sex"] == "Female" and 15 <= kw["age_years"] <= 45 and rnd.random() < .4
    kw.update(is_pregnant=preg, is_hepatic=rnd.random() < .2, child_pugh=rnd.choice("ABC"),
              is_renal=rnd.random() < .3, cl_cr=rnd.choice([8, 20, 40, 70, 110]),
              weight_kg=rnd.choice([4, 20, 60, 90]))
    kw = {k: v for k, v in kw.items() if k in _fields}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            r = A.run_analysis(PT(**kw), o, s, sir,
                               carbapenemase_type=rnd.choice([None, None, "KPC", "MBL", "OXA-48"]),
                               uti_syndrome=rnd.choice([None, "lower", "upper"]))
    except Exception as e:                                   # noqa: BLE001
        bad["exception"] += 1; ex.setdefault("exception", (repr(e)[:120], o, s)); continue
    names = {b: [x.get("name") for x in r[b]] for b in ("allowed", "warned", "banned", "preg_warn")}
    rec = names["allowed"] + names["warned"] + names["preg_warn"]; recs_seen += len(rec)
    intr = intrinsic(o)
    for d in rec:
        if sir.get(d) == "R": bad["resistant"] += 1; ex.setdefault("resistant", (o, s, d))
        if d in intr: bad["intrinsic"] += 1; ex.setdefault("intrinsic", (o, s, d))
        if d not in sir: bad["untested"] += 1; ex.setdefault("untested", (o, s, d))
        if preg and G[d].get("preg_status") == "Banned" and d not in names["preg_warn"]:
            bad["pregnancy"] += 1; ex.setdefault("pregnancy", (o, s, d))
    allb = sum(names.values(), [])
    if len(allb) != len(set(allb)): bad["two_buckets"] += 1; ex.setdefault("two_buckets", (o, s))
    if [d for d in sir if d not in allb and d not in intr]:
        bad["vanished"] += 1; ex.setdefault("vanished", (o, s))
check("the fuzz actually exercised recommendations", recs_seen > 2000, recs_seen)
for key, label in (("exception", "no input makes the engine raise"),
                   ("resistant", "a drug reported R is never recommended"),
                   ("intrinsic", "an intrinsically resistant drug is never recommended"),
                   ("untested", "a drug that was not tested is never recommended"),
                   ("pregnancy", "a pregnancy-banned drug is never recommended to a pregnant patient"),
                   ("two_buckets", "no drug appears in two result buckets"),
                   ("vanished", "every tested, non-intrinsic drug is accounted for")):
    check(label, not bad[key], ex.get(key))

print("\n[2] Pathogenicity engine — 4,000 random cases, fixed seed")
rnd = random.Random(31); P = PG.assess_pathogenicity
PORGS = ORGS + ["Candida albicans", "Unknown bug", ""]
SPECS = ["Urine", "Blood", "Sputum", "BAL", "Wound Swab", "Pus", "CSF", "Stool", "Throat swab", ""]
SYM = PG.URINE_SYMPTOMS + PG.WOUND_SIGNS + PG.RESPIRATORY_SIGNS + ["Bloody diarrhea", "Vomiting", "Watery diarrhea"]
HOSTS = PG.HOST_FACTORS_URINE + PG.HOST_FACTORS_OTHER
SCI_SYM = {"Increased spasticity (SCI)", "Autonomic dysreflexia (SCI)",
           "Malaise / Lethargy / Sense of unease (SCI)", "New incontinence / Leaking around catheter"}
bad = collections.Counter(); ex = {}
for _ in range(4000):
    k = dict(specimen=rnd.choice(SPECS), organism=rnd.choice(PORGS),
             colony_count_text=rnd.choice(["", "No growth", "10^2", "10^3", "10^4", "5x10^4", "10^5", ">10^5", "heavy growth", "garbage"]),
             culture_purity=rnd.choice(["Pure growth", "Mixed growth", ""]),
             symptoms=rnd.sample(SYM, rnd.randint(0, 4)),
             pus_cells_text=rnd.choice(["", "0-2", "5-8", "20-25", "over 100", "x"]),
             urinalysis_result=rnd.choice(["", "Normal", "Pyuria", "Nitrite positive"]),
             gram_stain=rnd.choice(PG.GRAM_STAIN_OPTIONS + [""]), age=rnd.choice([0, 1, 5, 30, 70, None]),
             sex=rnd.choice(["Male", "Female"]), host_factors=rnd.sample(HOSTS, rnd.randint(0, 3)),
             sputum_pus_cells=rnd.choice(["", "30", "5"]), sputum_epithelial=rnd.choice(["", "5", "30"]),
             sirs_criteria=rnd.sample(["a", "b", "c", "d"], rnd.randint(0, 4)),
             blood_source=rnd.choice(["", "مش محدد", "Single bottle positive", "Multiple bottles positive"]),
             wound_type=rnd.choice(PG.WOUND_TYPES + [""]),
             collection_method=rnd.choice(PG.URINE_COLLECTION_METHODS + [""]))
    try:
        r = P(**k)
    except Exception as e:                                   # noqa: BLE001
        bad["exception"] += 1; ex.setdefault("exception", (repr(e)[:100], k)); continue
    if not 0 <= r["score"] <= 100: bad["range"] += 1
    if r["category"] not in PG._CATEGORY_EN: bad["category"] += 1; ex.setdefault("category", r["category"])
    if len(r["notes_en"]) != len(r["notes"]):
        bad["note_en"] += 1; ex.setdefault("note_en", [n[:50] for n in r["notes"] if not PG._note_en(n)])
    if not r["interpretation_en"] or not r["recommendations_en"]: bad["en_missing"] += 1
    if AR.search(" ".join([r["interpretation_en"]] + r["recommendations_en"] + r["notes_en"])): bad["en_arabic"] += 1
    sp = k["specimen"].lower(); ol = k["organism"].lower()
    typical = any(t in ol for t in ("e. coli", "klebsiella", "proteus", "enterobacter"))
    if "urine" in sp:
        if k["symptoms"] == ["Asymptomatic"] and r["category"] == "TRUE_INFECTION":
            bad["asym_true"] += 1; ex.setdefault("asym_true", k)
        sc = [P(**dict(k, colony_count_text=c))["score"] for c in ("No growth", "10^2", "10^3", "10^4", "10^5")]
        if sc != sorted(sc): bad["monotonic"] += 1; ex.setdefault("monotonic", (sc, k))
        if (typical and "Urinary catheter" not in k["host_factors"] and k["culture_purity"] != "Mixed growth"
                and "catheter" not in k["collection_method"].lower()):
            if P(**dict(k, host_factors=k["host_factors"] + ["Urinary catheter"]))["score"] > r["score"] \
                    and not set(k["symptoms"]) & SCI_SYM:
                bad["catheter"] += 1; ex.setdefault("catheter", k)
    if "blood" in sp and any(t in ol for t in ("aureus", "mrsa", "e. coli", "klebsiella", "pseudomonas")) \
            and r["category"] != "TRUE_INFECTION":
        bad["blood"] += 1; ex.setdefault("blood", (r["category"], k))
    if (typical and not any("pleg" in h for h in k["host_factors"]) and not set(k["symptoms"]) & SCI_SYM
            and "Condom" not in k["collection_method"] and "Intermittent" not in k["collection_method"]):
        if P(**dict(k, host_factors=k["host_factors"] + [PG.HOST_SCI_PARA]))["score"] > r["score"]:
            bad["sci"] += 1; ex.setdefault("sci", k)
for key, label in (("exception", "no input makes the pathogenicity engine raise"),
                   ("range", "the score stays within 0-100"),
                   ("category", "every result has a known category"),
                   ("note_en", "every interpretive note has an English form"),
                   ("en_missing", "every result has an English interpretation and recommendations"),
                   ("en_arabic", "the English forms contain no Arabic"),
                   ("asym_true", "explicitly asymptomatic urine is never 'true infection'"),
                   ("monotonic", "the urine score never falls as the colony count rises"),
                   ("catheter", "a urinary catheter never raises the score for a typical uropathogen"),
                   ("blood", "a true bloodstream pathogen is always significant, whatever is missing"),
                   ("sci", "paraplegia by itself never raises the score")):
    check(label, not bad[key], ex.get(key))
x = P("Urine", "E. coli", "10^5", "Pure growth", ["Fever (> 38°C)"], "", "", "", 0, "Male", ["Urinary catheter"])
check("infant: the AAP 5x10^4 threshold is not replaced by the catheter rule", "5×10^4" in x["threshold"], x["threshold"])
a_ = P("Urine", "E. coli", "10^5", "Pure growth", ["Dysuria / Frequency / Urgency"], "", "Normal", "", 40, "Male", [])["score"]
b_ = P("Urine", "E. coli", "10^5", "Pure growth", ["Dysuria / Frequency / Urgency"], "", "Normal", "", 40, "Male", [PG.HOST_SCI_PARA])["score"]
check("a normal urinalysis still counts against UTI in spinal cord injury", b_ <= a_, (a_, b_))

print("\n[3] English clinical report carries no Arabic")
rnd = random.Random(5); leaks = collections.Counter(); n = 0
for o in ORGS:
    for s in ("Urine", "Blood", "CSF"):
        sir = {d: rnd.choice("SSIR") for d in rnd.sample(DRUGS, 18)}
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            r = A.run_analysis(Patient(age_years=30, sex="Female", is_pregnant=(n % 2 == 0)), o, s, sir)
            pa = PG.assess_pathogenicity(s, o, "10^5", "Pure growth", rnd.sample(SYM, 2), "20", "",
                                         rnd.choice(PG.GRAM_STAIN_OPTIONS), 30, "Female",
                                         rnd.sample(HOSTS, 2), wound_type="Pressure ulcer / Bed sore",
                                         collection_method="Indwelling catheter (Foley)")
            import logging; logging.disable(logging.CRITICAL)
            h = A.generate_pdf_html_report("Test", 30, "Female", 60, 90, False, n % 2 == 0, False,
                                           r["allowed"], r["warned"], r["banned"], r["preg_warn"], o, s, sir,
                                           r.get("interactions", []), r.get("mdr") or {}, r.get("mechanism") or {},
                                           r["phenotypes"], patho_assessment=pa, lang="en", return_html=True) or ""
            logging.disable(logging.NOTSET)
        n += 1
        for m in re.findall(r"[^\n]*[\u0600-\u06FF][^\n]*", text_of(h)):
            leaks[m.strip()[:90]] += 1
check(f"no Arabic text in {n} English reports (every organism x 3 specimens)", not leaks, leaks.most_common(4))

print("\n[4] Stand-alone Pathogenicity PDF")
pa = P("Urine", "E. coli", "10^5", "Pure growth", ["Fever (> 38°C)"], "20", "", "Organisms بدون WBCs", 40, "Male",
       [PG.HOST_SCI_PARA], collection_method="Indwelling catheter (Foley)")
INP = {"Gram stain": "Organisms بدون WBCs", "Host factors": [PG.HOST_SCI_PARA]}
har = A.generate_patho_report_pdf(pa, "E. coli", "Urine", inputs=INP, lang="ar", return_html=True)
hen = A.generate_patho_report_pdf(pa, "E. coli", "Urine", inputs=INP, lang="en", return_html=True)
check("Arabic PDF prints every recommendation and every note",
      all(A._esc(t) in har for t in pa["recommendations"] + pa["notes"]))
check("Arabic PDF prints the factors, threshold and references",
      all(A._esc(t) in har for t in pa["factors_pos"] + pa["factors_neg"]) and A._esc(pa["threshold"]) in har
      and "IDSA" in har)
check("English PDF carries no Arabic at all", not AR.search(text_of(hen)), AR.findall(text_of(hen))[:5])
check("English PDF prints the English recommendations and notes",
      all(A._esc(t) in hen for t in pa["recommendations_en"] + pa["notes_en"]))
check("an Arabic option label is translated, not amputated", "Organisms without WBCs" in hen)
check("no result -> no document", A.generate_patho_report_pdf(None, "E. coli", "Urine", return_html=True) is None)

print("\n[5] AST-QA sheet")
src = inspect.getsource(A.generate_qa_report_pdf)
check("the QA sheet prints the organism summary", "Organism Summary" in src and '_op_qa["note"]' in src)
check("the AST panel is grouped by result, not one row per drug",
      "sir-line" in src and "<tr><td>{_esc(drug)}" not in src)

print("\n[6] Gram-stain entry gate")
ec = PG.gram_options_for("E. coli"); sa = PG.gram_options_for("Staphylococcus aureus")
check("E. coli: Gram-positive choices are not offered", not [o_ for o_ in ec if "Positive" in o_], ec)
check("E. coli: Gram-negative rods, Gram-variable and the neutral choices are offered",
      "WBCs + Gram Negative Rods" in ec and any("Variable" in o_ for o_ in ec) and "مش متعملة" in ec)
check("S. aureus: Gram-negative choices are not offered", not [o_ for o_ in sa if "Negative" in o_], sa)
check("Acinetobacter: rods, cocci and Gram-variable all remain (coccobacillus)",
      {"WBCs + Gram Negative Rods", "WBCs + Gram Negative Cocci / Diplococci"} <= set(PG.gram_options_for("Acinetobacter spp.")))
check("anaerobes / unknown names keep the full list",
      len(PG.gram_options_for("Anaerobes (لاهوائيات)")) == len(PG.GRAM_STAIN_OPTIONS)
      and len(PG.gram_options_for("Something new")) == len(PG.GRAM_STAIN_OPTIONS))
check("every organism always has the neutral choices",
      all({"مش متعملة", "طبيعية (No organisms seen)"} <= set(PG.gram_options_for(o_)) for o_ in ORGS))

print("\n[7] Final checklist")


def ck(org, spec, sir, gram="", patho=None):
    with contextlib.redirect_stdout(io.StringIO()):
        r = A.run_analysis(Patient(age_years=45, sex="Male"), org, spec, sir)
    items = FC.build_final_checklist(org, spec, sir, r["allowed"], r["warned"], r["banned"],
                                     A.run_ast_qc(org, sir, specimen=spec), gram, patho)
    return {i["key"]: i["status"] for i in items}, items


st, items = ck("E. coli", "Urine", {"Ceftriaxone": "S", "Nitrofurantoin": "S", "Ciprofloxacin": "R"},
               "WBCs + Gram Negative Rods")
check("a clean case is all green / not-applicable", set(st.values()) <= {"pass", "na"}, st)
check("the checklist covers specimen-organism, organism-Gram, organism-antibiotics and specimen-antibiotics",
      {"specimen_organism", "organism_gram", "organism_antibiotics", "specimen_antibiotics"} <= set(st))
st, _ = ck("E. coli", "Urine", {"Ceftriaxone": "S"}, "WBCs + Gram Positive Cocci")
check("Gram stain that contradicts the organism is red", st["organism_gram"] == "fail")
st, _ = ck("E. coli", "Urine", {"Ceftriaxone": "S", "Vancomycin": "S"})
check("an 'S' for an intrinsically resistant drug is red", st["organism_antibiotics"] == "fail")
st, _ = ck("Legionella pneumophila", "Urine", {"Levofloxacin": "S"})
check("an implausible specimen-organism pair is red", st["specimen_organism"] == "fail", st)
st, _ = ck("E. coli", "Blood", {"Ceftriaxone": "R", "Ciprofloxacin": "R"})
check("no therapeutic option at all is red", st["options"] == "fail")
st, _ = ck("Acinetobacter spp.", "Sputum", {"Meropenem": "S"})
check("a genus-level organism is amber", st["identification"] == "warn")
check("the summary is red as soon as one line is red",
      FC.summarize([{"status": "pass"}, {"status": "fail"}])["overall"] == "fail"
      and FC.summarize([{"status": "pass"}, {"status": "na"}])["overall"] == "pass")
rnd = random.Random(9); crashed = []
for _ in range(400):
    o = rnd.choice(ORGS + ["", "weird"]); s = rnd.choice(["Urine", "Blood", "Sputum", "CSF", "", "Odd site"])
    sir = {d: rnd.choice("SIR") for d in rnd.sample(DRUGS, rnd.randint(0, 12))}
    try:
        FC.build_final_checklist(o, s, sir, gram_stain=rnd.choice(PG.GRAM_STAIN_OPTIONS + [""]))
    except Exception as e:                                   # noqa: BLE001
        crashed.append((o, s, repr(e)[:80]))
check("the checklist never raises, whatever it is given", not crashed, crashed[:2])

print("\n" + "=" * 72)
if FAILS:
    print(f"RESULT: {len(FAILS)} FAILED")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("RESULT: all round-3 checks passed")
