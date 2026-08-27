#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_clinical_facts.py — the DATA, asserted by value.

WHY THIS FILE EXISTS
On 2026-08-05 the clinical data tables were mutation-tested for the first time.
Eight single-value edits were made — the kind a careless afternoon produces —
and FIVE of them passed every one of the twelve suites:

    Doxycycline  preg_status  "Banned" -> "Caution"   a teratogen, downgraded
    Gentamicin   preg_status  "Banned" -> "Caution"   fetal ototoxicity
    Vancomycin   child_safe   True     -> False       unusable in children
    Listeria     avoid        ceftriaxone removed     the exact defect fixed
                                                      three days earlier
    Daptomycin   Sputum       "deny"   -> "allow"     surfactant inactivation

Every suite stayed green. The reason is simple and was invisible until someone
mutated data rather than code: the suites test what the ENGINE DOES WITH the
tables — buckets stay exclusive, resistant agents are not recommended, the gate
only demotes — and none of them asserts what the tables SAY. Feed the same
correct logic a wrong fact and it produces a wrong answer, correctly.

The invariants that would have caught these did exist. They lived in the
throwaway sweep scripts written during the audit — 5,000-case runs with twenty
live assertions — and a throwaway script protects nothing after the session
that wrote it ends.

This file is those assertions, written down.

WHAT BELONGS HERE
Facts about the DATA that are true independently of any code path, and whose
violation is a clinical error rather than a bug:

    * a teratogen is banned in pregnancy, not cautioned
    * an organism intrinsically resistant to a class does not list that class
      as a treatment option
    * a drug inactivated at a site is denied at that site
    * a renal threshold matches the regulator's figure

WHAT DOES NOT BELONG HERE
Behaviour. Whether analyze_antibiotics() honours preg_status is
test_engine_agreement.py's question. This file only asks whether preg_status
says the right thing.

Every entry carries its source. A fact with no source is an opinion, and an
opinion has no business failing someone's build.

Run:  python test_clinical_facts.py [--verbose]
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


from abx_guidelines import ABX_GUIDELINES as G                      # noqa: E402
from organism_profile import ORGANISM_PROFILE as OP                 # noqa: E402
from clinical_data import INTRINSIC_RESISTANCE as IR                # noqa: E402
import clinical_matrix as CM                                        # noqa: E402

print("=" * 72)
print("Orange Lab CDSS — clinical facts, asserted by value")
print(f"  {len(G)} agents · {len(OP)} organisms · {len(IR)} intrinsic rows")
print("=" * 72)


# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] PREGNANCY — a teratogen is BANNED, never merely cautioned.")
print("    Doxycycline and Gentamicin were both silently downgradable to")
print("    'Caution' with no suite objecting.")
# ═══════════════════════════════════════════════════════════════════════════
# FDA labelling + ACOG. Tetracyclines: fetal tooth staining and bone growth
# inhibition. Aminoglycosides: irreversible fetal ototoxicity (eighth nerve).
# Fluoroquinolones: cartilage toxicity in immature animals.
# The vocabulary has FOUR tiers — Banned, Warn, Caution, Safe — and the
# distinction is deliberate, not sloppy. `Banned` is absolute; `Warn` keeps an
# agent out of the recommended column and flags it, which is the right handling
# for a drug that is avoided in pregnancy but still reached for when nothing
# else works. Asserting the wrong tier would have forced a real clinical
# distinction out of the data to make a test pass.
#
# ABSOLUTE: no obstetric situation justifies these.
PREG_ABSOLUTE = [
    ("Doxycycline", "tetracycline — fetal teeth and bone"),
    ("Tetracycline", "tetracycline — fetal teeth and bone"),
    ("Minocycline", "tetracycline — fetal teeth and bone"),
    ("Tigecycline", "glycylcycline — tetracycline class effect"),
    ("Gentamicin", "aminoglycoside — irreversible fetal ototoxicity"),
    ("Amikacin", "aminoglycoside — irreversible fetal ototoxicity"),
    ("Tobramycin", "aminoglycoside — irreversible fetal ototoxicity"),
    ("Chloramphenicol", "grey baby syndrome"),
]
_bad = [f"{d}: preg_status={G[d].get('preg_status')!r}, must be 'Banned' — {why}"
        for d, why in PREG_ABSOLUTE
        if d in G and G[d].get("preg_status") != "Banned"]
check("every absolutely contraindicated agent is preg_status='Banned'",
      not _bad, "\n".join(_bad))

# AVOIDED: fluoroquinolones. ACOG advises against them in pregnancy, but they
# are used in multidrug-resistant pyelonephritis when no alternative exists —
# which tetracyclines never are. `Warn` is correct and `Banned` would be
# clinically wrong. What must NEVER happen is a drop to Caution or Safe.
PREG_AVOID = ["Ciprofloxacin", "Levofloxacin", "Moxifloxacin", "Ofloxacin",
              "Norfloxacin"]
_soft = [f"{d}: preg_status={G[d].get('preg_status')!r} — must be 'Banned' or "
         f"'Warn', never Caution/Safe"
         for d in PREG_AVOID
         if d in G and G[d].get("preg_status") not in ("Banned", "Warn")]
check("fluoroquinolones are at least 'Warn' in pregnancy, never merely Caution",
      not _soft, "\n".join(_soft))

# The reverse: agents that are safe must not be banned, or a pregnant woman
# with a UTI is left with nothing.
PREG_SAFE = ["Amoxicillin", "Ampicillin", "Amoxicillin + Clavulanic acid",
             "Cefazolin", "Cephalexin", "Ceftriaxone", "Cefuroxime",
             "Cefotaxime", "Azithromycin", "Erythromycin", "Nitrofurantoin",
             "Fosfomycin", "Meropenem", "Penicillin", "Clindamycin"]
_over = [f"{d}: preg_status={G[d].get('preg_status')!r}"
         for d in PREG_SAFE if d in G and G[d].get("preg_status") == "Banned"]
check("no pregnancy-safe first-line agent is banned in pregnancy",
      not _over, "\n".join(_over))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[2] PAEDIATRICS — child_safe must match the actual restriction.")
# ═══════════════════════════════════════════════════════════════════════════
# Vancomycin was silently flippable to child_safe=False, which would remove the
# only reliable agent for paediatric MRSA.
CHILD_SAFE = ["Vancomycin", "Meropenem", "Ceftriaxone", "Cefotaxime",
              "Ampicillin", "Amoxicillin", "Azithromycin", "Clindamycin",
              "Gentamicin", "Amikacin", "Penicillin"]
_cs = [f"{d}: child_safe={G[d].get('child_safe')!r}, must be True"
       for d in CHILD_SAFE if d in G and G[d].get("child_safe") is not True]
check("agents used routinely in children are marked child_safe",
      not _cs, "\n".join(_cs))

CHILD_UNSAFE = ["Doxycycline", "Tetracycline", "Minocycline", "Tigecycline",
                "Ciprofloxacin", "Levofloxacin", "Moxifloxacin"]
_cu = [f"{d}: child_safe={G[d].get('child_safe')!r}, must be False"
       for d in CHILD_UNSAFE if d in G and G[d].get("child_safe") is not False]
check("age-restricted agents are NOT marked child_safe",
      not _cu, "\n".join(_cu))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[3] SITE — an agent inactivated at a site must be DENIED there.")
print("    'Daptomycin / Sputum: deny -> allow' passed all twelve suites.")
# ═══════════════════════════════════════════════════════════════════════════
# Daptomycin is bound and inactivated by pulmonary surfactant: it fails in
# pneumonia whatever the MIC says. Tigecycline reaches negligible serum and
# urinary concentrations. Neither is a dosing problem; both are absolute.
SITE_DENY = [
    ("Daptomycin", "Sputum", "inactivated by pulmonary surfactant"),
    ("Tigecycline", "Blood", "serum concentrations too low for bacteraemia"),
    ("Tigecycline", "Urine", "negligible urinary excretion"),
    ("Tigecycline", "CSF", "does not reach therapeutic CSF levels"),
    ("Teicoplanin", "CSF", "does not reach therapeutic CSF levels"),
    ("Nitrofurantoin", "Blood", "urinary agent, no systemic levels"),
    ("Fosfomycin", "Blood", "urinary agent at the oral dose"),
]
_sd = []
for _d, _sp, _why in SITE_DENY:
    _row = CM.SITE_PENETRATION.get(_d, {}).get(_sp)
    if not _row or _row[0] != "deny":
        _sd.append(f"{_d} / {_sp}: {_row[0] if _row else 'NO ROW'!r}, must be "
                   f"'deny' — {_why}")
check("agents inactivated or absent at a site are denied there",
      not _sd, "\n".join(_sd))

# And the reverse: a first-line agent must not be denied at its own site.
SITE_ALLOW = [("Ceftriaxone", "CSF"), ("Meropenem", "CSF"), ("Vancomycin", "CSF"),
              ("Nitrofurantoin", "Urine"), ("Fosfomycin", "Urine"),
              ("Daptomycin", "Blood"), ("Metronidazole", "Pus")]
_sa = []
for _d, _sp in SITE_ALLOW:
    _row = CM.SITE_PENETRATION.get(_d, {}).get(_sp)
    if _row and _row[0] == "deny":
        _sa.append(f"{_d} / {_sp} is denied at the site where it is first-line")
check("no first-line agent is denied at its own site",
      not _sa, "\n".join(_sa))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[4] ORGANISM PROFILES — an intrinsically resistant class is not")
print("    offered as treatment. 'Ceftriaxone removed from Listeria avoid'")
print("    passed every suite — the exact defect fixed three days earlier.")
# ═══════════════════════════════════════════════════════════════════════════
# Listeria: PBP3 has low affinity for ALL cephalosporins. It causes meningitis
# in neonates, pregnant women and the elderly — the three groups a
# ceftriaxone-first protocol is written for.
MUST_AVOID = [
    ("Listeria monocytogenes",
     ["Ceftriaxone", "Cefotaxime", "Ceftazidime", "Cefepime", "Cefuroxime",
      "Cefazolin", "Cephalexin"],
     "PBP3 has low affinity for every cephalosporin"),
    ("Enterococcus faecium",
     ["Ceftriaxone", "Cefotaxime", "Ceftazidime", "Cefepime"],
     "enterococci are intrinsically cephalosporin-resistant (PBP5)"),
    # MRSA is deliberately NOT listed here. Its beta-lactam ban is enforced by
    # CLASS in analyze_antibiotics() — every penicillin, cephalosporin,
    # carbapenem and BLI combination, whether or not the profile happens to
    # name it — because PBP2a defeats the whole class rather than specific
    # members. Requiring the profile to enumerate them would duplicate a
    # class-wide rule as a list that could fall behind the formulary, which is
    # how five of this audit's defects happened. The behaviour is asserted in
    # test_engine_agreement.py, where it belongs.
]
_ma = []
for _org, _drugs, _why in MUST_AVOID:
    if _org not in OP:
        continue
    _av = {d.lower() for d in (OP[_org].get("avoid") or [])}
    for _d in _drugs:
        if _d in G and _d.lower() not in _av:
            _ma.append(f"{_org}: {_d} missing from `avoid` — {_why}")
check("no profile omits a class its organism is intrinsically resistant to",
      not _ma, "\n".join(_ma))

# Every profile's first-line list must be treatable: present in the formulary
# AND not intrinsically inactive against that organism.
_fl = []
for _org, _prof in OP.items():
    _row = set()
    for _k, _v in IR.items():
        if _k in _org.lower() or _org.lower() in _k:
            _row |= set(_v)
    for _d in (_prof.get("first_line") or []):
        if _d not in G:
            _fl.append(f"{_org}: first-line {_d!r} is not in the formulary")
        elif _d in _row:
            _fl.append(f"{_org}: first-line {_d!r} is on its own intrinsic list")
check("every first-line recommendation is real and not intrinsically inactive",
      not _fl, "\n".join(_fl))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[5] THRESHOLDS — the regulator's figure, by value.")
# ═══════════════════════════════════════════════════════════════════════════
# MHRA Drug Safety Update, February 2015: nitrofurantoin is contraindicated
# below eGFR 45, not 60. A loosening to 15 was caught; a tightening to 60 must
# fail too, because it withdraws the first-line agent for uncomplicated UTI.
THRESHOLDS = [
    ("Nitrofurantoin", 45, "MHRA DSU Feb 2015 / BNF 2025"),
    ("Meropenem", 50, "product label"),
    ("Ertapenem", 30, "product label"),
    ("Ciprofloxacin", 30, "product label"),
    ("Cefiderocol", 60, "Fetroja label — and INCREASED above CrCl 120"),
    ("Daptomycin", 30, "Cubicin label — interval extends to 48h below this"),
]
_th = [f"{d}: renal_limit={G[d].get('renal_limit')!r}, must be {v} ({src})"
       for d, v, src in THRESHOLDS if d in G and G[d].get("renal_limit") != v]
check("renal thresholds match the regulator's published figure",
      not _th, "\n".join(_th))

# WHO AWaRe 2025 (B09489). These drive the stewardship ranking, so a
# reclassification changes which agent a clinician is steered toward.
AWARE = {"Aztreonam": "Reserve", "Fosfomycin": "Watch",
         "Ampicillin/Sulbactam": "Access", "Tobramycin": "Watch",
         "Gentamicin": "Access", "Amikacin": "Access", "Vancomycin": "Watch",
         "Teicoplanin": "Watch", "Linezolid": "Reserve", "Colistin": "Reserve",
         "Tigecycline": "Reserve", "Daptomycin": "Reserve",
         "Cefiderocol": "Reserve", "Ceftaroline": "Reserve",
         "Meropenem": "Watch", "Ertapenem": "Watch", "Cefazolin": "Access",
         "Cephalexin": "Access", "Clindamycin": "Access",
         "Doxycycline": "Access", "Nitrofurantoin": "Access"}
_aw = [f"{d}: aware={G[d].get('aware')!r}, WHO 2025 says {e!r}"
       for d, e in AWARE.items() if d in G and G[d].get("aware") != e]
check("AWaRe categories match the WHO 2025 list (B09489)",
      not _aw, "\n".join(_aw))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[6] INTRINSIC RESISTANCE — the entries that must exist, and the")
print("    entries that must NOT (a wrong ban withdraws a working drug).")
# ═══════════════════════════════════════════════════════════════════════════
# EUCAST Intrinsic Resistance and Unusual Phenotypes v3.3.
INTRINSIC_MUST = [
    ("escherichia coli", "Vancomycin"), ("escherichia coli", "Linezolid"),
    ("klebsiella pneumoniae", "Ampicillin"),
    ("proteus mirabilis", "Nitrofurantoin"), ("proteus mirabilis", "Colistin"),
    ("proteus mirabilis", "Tigecycline"),
    ("morganella morganii", "Tigecycline"),
    ("providencia spp.", "Gentamicin"),
    ("enterococcus faecalis", "Colistin"),
    ("enterococcus faecalis", "Trimethoprim/Sulfamethoxazole"),
    ("listeria monocytogenes", "Ceftriaxone"),
    ("coagulase-negative staphylococci", "Aztreonam"),
    ("acinetobacter baumannii", "Ertapenem"),
    ("stenotrophomonas maltophilia", "Meropenem"),
    ("anaerobes", "Gentamicin"), ("anaerobes", "Colistin"),
    ("h. influenzae", "Vancomycin"),
    ("campylobacter jejuni", "Trimethoprim"),
]
_im = [f"{k} / {d} is missing from the intrinsic table"
       for k, d in INTRINSIC_MUST if d not in set(IR.get(k, []))]
check("every required intrinsic-resistance entry is present",
      not _im, "\n".join(_im))

# Wrong bans are just as harmful: they remove a drug that works.
INTRINSIC_MUST_NOT = [
    ("serratia marcescens", "Tigecycline", "active against Serratia — EUCAST fn.5"),
    ("serratia marcescens", "Minocycline", "active against Serratia — EUCAST fn.5"),
    ("proteus mirabilis", "Ampicillin", "P. mirabilis IS ampicillin-susceptible"),
    ("klebsiella pneumoniae", "Cephalexin", "not on the EUCAST intrinsic list"),
    ("acinetobacter baumannii", "Minocycline", "minocycline is active"),
    ("stenotrophomonas maltophilia", "Trimethoprim/Sulfamethoxazole",
     "TMP-SMX is the drug of CHOICE"),
    ("stenotrophomonas maltophilia", "Levofloxacin", "recognised active option"),
    ("providencia spp.", "Amikacin", "amikacin is spared"),
    ("h. influenzae", "Azithromycin", "macrolides are indicated"),
]
_in = [f"{k} / {d} must NOT be intrinsic — {why}"
       for k, d, why in INTRINSIC_MUST_NOT if d in set(IR.get(k, []))]
check("no working agent is wrongly listed as intrinsically resistant",
      not _in, "\n".join(_in))



# ═══════════════════════════════════════════════════════════════════════════
print("\n[7] NAMING — a rule that only matches by accident is not a rule.")
print("    Ten intrinsic rows named 'Ampicillin + Sulbactam' while the")
print("    formulary key is 'Ampicillin/Sulbactam'. The engine excluded the")
print("    drug anyway because the matcher bridges '+' and '/', so no test")
print("    failed — but the rules worked BY ACCIDENT, and tightening the")
print("    matcher for any reason would silence ten of them at once.")
# ═══════════════════════════════════════════════════════════════════════════
# Agents this formulary does not stock. Their rules are kept deliberately: they
# are EUCAST facts, and the day one is added the rule must already be present
# rather than remembered. Anything NOT on this list must match a formulary key
# exactly.
_NOT_STOCKED = {
    "Nalidixic acid", "Polymyxin B", "Rifampicin", "Ticarcillin",
    "Trimethoprim", "Chloramphenicol", "Cefpodoxime", "Ceftibuten",
    "Cefuroxime axetil", "Piperacillin",
}
_mismatch = []
for _k, _row in IR.items():
    for _d in _row:
        if _d in G or _d in _NOT_STOCKED:
            continue
        # near-miss on punctuation or spacing is the dangerous case: it works
        # today and stops working the moment matching tightens.
        _norm = _d.lower().replace("+", "/").replace(" ", "")
        _near = [g for g in G if g.lower().replace("+", "/").replace(" ", "") == _norm]
        _mismatch.append(f"{_k} / {_d!r}" +
                         (f" — the formulary key is {_near[0]!r}" if _near
                          else " — not in the formulary and not declared unstocked"))
check("every intrinsic entry names a formulary key exactly, or is declared unstocked",
      not _mismatch, "\n".join(sorted(set(_mismatch))[:10]))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[8] CROSS-TABLE CONTRACTS — every table that names a drug, an organism")
print("    or a specimen must name one the other tables recognise.")
print("    This is the check that found 'Ampicillin + Sulbactam' vs")
print("    'Ampicillin/Sulbactam' across ten intrinsic rows on 2026-08-05: the")
print("    behaviour was right, but only because the matcher happened to bridge")
print("    '+' and '/'. Tighten matching for any reason and ten rules go silent")
print("    with no behavioural test failing. A rule that works by accident is")
print("    not a rule.")
# ═══════════════════════════════════════════════════════════════════════════
import importlib as _il8                                            # noqa: E402
import clinical_matrix as _CM8                                      # noqa: E402
import ast_reportability as _RP8                                    # noqa: E402
from specimen_organism_map import SPECIMEN_ORGANISM_MAP as _SOM8    # noqa: E402

try:
    _sa8 = _il8.import_module("streamlit_app")
except Exception:
    _sa8 = None

_DRUGS8 = set(G)
# Agents this formulary does not stock. Their rules stay: they are EUCAST facts
# and must already exist the day the agent is added, not be remembered then.
_UNSTOCKED8 = {"Nalidixic acid", "Polymyxin B", "Rifampicin", "Ticarcillin",
               "Trimethoprim", "Chloramphenicol", "Cefpodoxime", "Ceftibuten",
               "Cefuroxime axetil", "Piperacillin", "Netilmicin", "Kanamycin",
               "Streptomycin"}


def _near_miss(name):
    """A name that differs from a real key only by punctuation or spacing.

    This is the ONLY failure mode this check treats as an error. A name that is
    simply absent is usually a deliberate unstocked agent or a class label; a
    NEAR-MISS is a rule silently depending on a lenient matcher.
    """
    n = str(name).lower().replace("+", "/").replace(" ", "")
    return [g for g in _DRUGS8
            if g.lower().replace("+", "/").replace(" ", "") == n and g != name]


_tables = [
    ("INTRINSIC_RESISTANCE", [d for r in IR.values() for d in r]),
    ("SITE_PENETRATION", list(_CM8.SITE_PENETRATION)),
    ("RENAL_RULES", list(_CM8.RENAL_RULES)),
    ("ast_reportability.INTRINSIC_RULES",
     [d for r in _RP8.INTRINSIC_RULES for d in (r.get("drugs") or [])]),
]
if _sa8:
    _tables += [
        ("HEPATIC_DOSING", list(getattr(_sa8, "HEPATIC_DOSING", {}))),
        ("NEONATAL_RESTRICTIONS", list(_sa8.NEONATAL_RESTRICTIONS)),
        ("PHENOTYPE_RULES.markers",
         [d for r in _sa8.PHENOTYPE_RULES.values() for d, _ in r["markers"]]),
        ("MDR_CATEGORIES", [d for v in _sa8.MDR_CATEGORIES.values() for d in v]),
    ]

# ast_reportability stores drug names lower-cased on purpose and matches
# case-insensitively; that is a documented convention, not a near-miss.
_CASE_INSENSITIVE = {"ast_reportability.INTRINSIC_RULES"}

_nm = []
for _tbl, _names in _tables:
    for _d in _names:
        if _d in _DRUGS8 or _d in _UNSTOCKED8:
            continue
        if _tbl in _CASE_INSENSITIVE and _d.title() in _DRUGS8:
            continue
        if _tbl in _CASE_INSENSITIVE and any(g.lower() == str(_d).lower() for g in _DRUGS8):
            continue
        _hit = _near_miss(_d)
        if _hit:
            _nm.append(f"{_tbl}: {_d!r} is a near-miss for {_hit[0]!r} — "
                       f"it only matches while the matcher stays lenient")
check("no table names a drug by a near-miss of the real formulary key",
      not _nm, "\n".join(sorted(set(_nm))[:10]))

# Specimens are a closed vocabulary: a typo here silently drops a whole note.
if _sa8:
    _SPECS8 = set(_sa8.SPECIMEN_TYPES)
    _sp = []
    for _tbl, _names in (
            ("ORGANISM_PROFILE.specimen_context",
             {s for p in OP.values() for s in (p.get("specimen_context") or {})}),
            ("ABX_GUIDELINES.specimen_notes",
             {s for v in G.values() for s in (v.get("specimen_notes") or {})}),
            ("SITE_PENETRATION",
             {s for r in _CM8.SITE_PENETRATION.values() for s in r}),
            ("SPECIMEN_ORGANISM_MAP", set(_SOM8))):
        _sp += [f"{_tbl}: {s!r}" for s in _names if s not in _SPECS8]
    check("every specimen named anywhere is a selectable specimen",
          not _sp, "\n".join(sorted(set(_sp))[:8]))

    # A phenotype must fire for every selectable organism it is meant to cover.
    # The rule lists MORE names than the dropdown offers on purpose — an OCR'd
    # report may say "Escherichia coli" or "Klebsiella pneumoniae" where the
    # dropdown says "E. coli" or "Klebsiella spp." — so the check is
    # behavioural: does the phenotype fire, not does the name match a key.
    _CRE_ORGS = ["E. coli", "Klebsiella spp.", "Enterobacter cloacae",
                 "Citrobacter freundii", "Serratia marcescens",
                 "Morganella morganii", "Providencia spp.", "Hafnia alvei",
                 "Enterobacterales (unspeciated)"]
    _cre_miss = [o for o in _CRE_ORGS if o in OP and "CRE" not in
                 {p["phenotype"] for p in _sa8.detect_resistance_phenotypes(
                     o, {"Meropenem": "R", "Ertapenem": "R"})}]
    check("CRE fires for every selectable Enterobacterales it should cover",
          not _cre_miss, f"no CRE for: {_cre_miss}")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[8] CROSS-TABLE CONTRACTS — every table that NAMES a drug, organism")
print("    or specimen must name something the defining table actually has.")
print("    This is the check that found 'Ampicillin + Sulbactam' vs")
print("    'Ampicillin/Sulbactam' across ten intrinsic rows: behaviour was")
print("    correct, but only because the matcher happened to bridge '+' and")
print("    '/'. Tighten matching for any reason and ten rules go silent with")
print("    nothing failing.")
# ═══════════════════════════════════════════════════════════════════════════
# This suite runs WITHOUT a Streamlit runtime — that is the point of it, and
# importing streamlit_app here would defeat it. The tables that live in the
# monolith are therefore lifted out by AST, the same way the other harnesses
# do it, rather than imported.
import ast as _ast8                                                        # noqa: E402
from specimen_organism_map import SPECIMEN_ORGANISM_MAP as _SOM            # noqa: E402
import clinical_matrix as _CM8                                            # noqa: E402
import ast_reportability as _RP8                                          # noqa: E402
from ocr_parsing import ORGANISM_OCR_ALIASES as _OCR_ALIASES               # noqa: E402
from clinical_utils import collapse_ws                                     # noqa: E402
try:
    from clinical_matrix import _ORG_CANON_MAP as _CANON8
except ImportError:
    _CANON8 = {}

_APP8 = os.path.join(HERE, "streamlit_app.py")
_src8 = open(_APP8, encoding="utf-8").read()
_tree8 = _ast8.parse(_src8)
_lines8 = _src8.splitlines(keepends=True)
_NS8 = {"__builtins__": __builtins__}
for _n8 in _tree8.body:
    _nm8 = None
    if isinstance(_n8, (_ast8.Assign, _ast8.AnnAssign)):
        _tg8 = _n8.targets if isinstance(_n8, _ast8.Assign) else [_n8.target]
        if len(_tg8) == 1 and isinstance(_tg8[0], _ast8.Name):
            _nm8 = _tg8[0].id
    if _nm8 in ("SPECIMEN_TYPES", "PHENOTYPE_RULES", "MDR_CATEGORIES",
                "COMBINATION_THERAPY",
                "HEPATIC_DOSING", "NEONATAL_RESTRICTIONS",
                "ORGANISM_OCR_ALIASES") and _nm8 not in _NS8:
        try:
            exec(compile("".join(_lines8[_n8.lineno - 1:_n8.end_lineno]),
                         f"<{_nm8}>", "exec"), _NS8)
        except Exception:
            pass


class _App8:
    def __getattr__(self, k):
        try:
            return _NS8[k]
        except KeyError:
            raise AttributeError(k)


_sa8 = _App8()
_DRUGS8, _ORGS8 = set(G), set(OP)
# SPECIMEN_TYPES in the monolith is `list(SPECIMEN_ORDER or DEFAULT_SPECIMENS)`
# — derived, not a literal, so AST extraction yields nothing. Read the source
# it derives from.
from specimen_organism_map import SPECIMEN_ORDER as _SPEC_ORDER8           # noqa: E402
_SPECS8 = set(_SPEC_ORDER8)

# Deliberate exceptions, each for a DIFFERENT reason. Listing them here is the
# point: an exception nobody wrote down is indistinguishable from a defect.
_UNSTOCKED = {          # EUCAST facts about agents this formulary does not carry.
    "Nalidixic acid", "Polymyxin B", "Rifampicin", "Ticarcillin", "Trimethoprim",
    "Chloramphenicol", "Cefpodoxime", "Ceftibuten", "Cefuroxime axetil",
    "Piperacillin", "Netilmicin",
}
_CLASS_TOKENS = {       # CLASS-level entries in organism profiles. A profile may
    "Aminoglycosides", "Beta-lactams", "Beta-lactams (alone)", "Carbapenems",
    "Cephalosporins", "Cephalosporins (كل الجيل)", "Tetracyclines",
    "Ampicillin (alone)",   # "alone" = without a synergistic aminoglycoside
}                       # name a whole class; the engine matches by class too.

_bad8 = []


def _names_drugs(where, names, extra=frozenset()):
    for _d in names:
        if _d in _DRUGS8:
            continue
        # A NEAR-MISS is checked BEFORE the exemption lists, not after. Order
        # matters: "Ampicillin + Sulbactam" is a punctuation variant of the
        # stocked "Ampicillin/Sulbactam", and an exemption list that happens to
        # contain a similar string would wave it through — which is exactly
        # what happened when this guard was first written and a mutation
        # reintroducing the variant survived. A name that differs from a
        # stocked key only by "+" versus "/" or by spacing is never a
        # deliberate reference to something else.
        _n = str(_d).lower().replace("+", "/").replace(" ", "")
        _near = [g for g in _DRUGS8
                 if g.lower().replace("+", "/").replace(" ", "") == _n]
        if _near:
            _bad8.append(f"{where}: {_d!r} — NEAR-MISS for {_near[0]!r}; it "
                         f"works only because the matcher is fuzzy")
            continue
        if _d in _UNSTOCKED or _d in extra:
            continue
        _bad8.append(f"{where}: {_d!r} — absent from the formulary and not "
                     f"declared unstocked")


_names_drugs("ORGANISM_PROFILE", [d for p in OP.values()
                                  for k in ("first_line", "second_line", "third_line",
                                            "alternatives", "avoid")
                                  for d in (p.get(k) or [])], _CLASS_TOKENS)
_names_drugs("INTRINSIC_RESISTANCE", [d for r in IR.values() for d in r])
_names_drugs("SITE_PENETRATION", list(_CM8.SITE_PENETRATION))
_names_drugs("RENAL_RULES", list(_CM8.RENAL_RULES))
_names_drugs("HEPATIC_DOSING", list(_sa8.HEPATIC_DOSING))
_names_drugs("NEONATAL_RESTRICTIONS", list(_sa8.NEONATAL_RESTRICTIONS))
_names_drugs("PHENOTYPE_RULES.markers",
             [d for r in _sa8.PHENOTYPE_RULES.values() for d, _ in r["markers"]])
_names_drugs("MDR_CATEGORIES",
             [d for v in _sa8.MDR_CATEGORIES.values()
              if isinstance(v, (list, tuple, set, frozenset)) for d in v])
check("no table names a drug by a near-miss spelling",
      not _bad8, "\n".join(sorted(set(_bad8))[:8]))

# A repeated entry in a resistance row is harmless to behaviour — a set
# membership test does not care — but it is the fingerprint of a bulk rename
# that landed twice, and the next such rename may not be harmless. One was left
# behind by the 2026-08-05 "Ampicillin + Sulbactam" correction.
_dupes = []
for _k, _row in IR.items():
    _seen = set()
    for _d in _row:
        if _d in _seen:
            _dupes.append(f"{_k}: {_d!r} listed twice")
        _seen.add(_d)
for _o, _p in OP.items():
    for _key in ("first_line", "second_line", "third_line", "avoid"):
        _lst = _p.get(_key) or []
        if len(_lst) != len(set(_lst)):
            _dupes.append(f"{_o}/{_key}: repeated entries")
check("no clinical list repeats an entry",
      not _dupes, "\n".join(sorted(set(_dupes))[:8]))

# ast_reportability deliberately stores lower-case tokens and matches
# case-insensitively — a different convention, not a mismatch. What must hold
# is that every token resolves to SOMETHING once case is folded, or is an agent
# this formulary does not stock.
_low = {g.lower() for g in _DRUGS8} | {u.lower() for u in _UNSTOCKED}
_EXTRA_RP = {"benzylpenicillin", "carbenicillin", "cephalothin", "cloxacillin",
             "co-trimoxazole", "cotrimoxazole", "dalbavancin", "fusidic",
             "imipenem", "kanamycin", "lincomycin", "mecillinam", "netilmicin",
             "oritavancin", "penicillin", "quinupristin", "streptomycin",
             "sulfonamides", "telavancin", "temocillin", "tetracyclines",
             "ticarcillin", "trimethoprim", "aminoglycosides", "carbapenems",
             "cephalosporins", "glycopeptides", "macrolides", "polymyxins",
             # Synonyms and older names EUCAST still uses in its own tables:
             # methicillin names the phenotype rather than a stocked drug,
             # rifampin is the US spelling of rifampicin, penicillin G is
             # benzylpenicillin, and sulfamethoxazole appears alone because
             # EUCAST lists the sulphonamide component separately from the
             # co-trimoxazole combination. Keeping the source's own vocabulary
             # is right: rewriting it to match this formulary would make the
             # rules harder to check against the published document.
             "methicillin", "neomycin", "penicillin g", "polymyxin",
             "rifampin", "sulfamethoxazole", "sulphamethoxazol"}
_rp_bad = [f"{t!r}" for t in {d for r in _RP8.INTRINSIC_RULES
                              for d in (r.get("drugs") or [])}
           if t.lower() not in _low and t.lower() not in _EXTRA_RP]
check("every reportability token resolves case-insensitively or is declared",
      not _rp_bad, "\n".join(sorted(_rp_bad)[:8]))

# Organism and specimen names, same question.
# PHENOTYPE_RULES is deliberately EXCLUDED from the name check below and
# asserted behaviourally instead. Its organism lists are matched by the ENGINE
# with a two-way substring test against the PATIENT's organism, so the tokens
# there are intentionally broader than the dropdown: "Citrobacter spp." exists
# to cover C. freundii, "Escherichia coli" is the full binomial for the profile
# keyed "E. coli". Asserting those names against the profile keys tests the
# wrong direction and would push someone to narrow rules that work.
#
# What matters is that each rule REACHES an organism. That is checked here by
# firing it, which is the only form of the question that cannot be satisfied by
# renaming something.
_ph_bad = []
for _ph, _rule in _sa8.PHENOTYPE_RULES.items():
    _marks = _rule.get("markers") or []
    if not _marks:
        _ph_bad.append(f"{_ph}: no markers — the rule can never fire")
        continue
    # Every marker must name a real agent, or the rule is inert.
    for _d, _v in _marks:
        if _d not in _DRUGS8:
            _ph_bad.append(f"{_ph}: marker {_d!r} is not in the formulary")
        if _v not in ("S", "I", "R"):
            _ph_bad.append(f"{_ph}: marker verdict {_v!r} is not S/I/R")
    # Its organism list must not be empty, and its threshold must be reachable.
    if not (_rule.get("organisms") or []):
        _ph_bad.append(f"{_ph}: no organisms — the rule can never fire")
    _req = _rule.get("require_any", len(_marks))
    if _req > len(_marks):
        _ph_bad.append(f"{_ph}: require_any={_req} exceeds its {len(_marks)} "
                       f"markers — unreachable by construction")
    # An isolation banner with no therapy panel tells the ward to isolate and
    # the clinician nothing.
    if _rule.get("isolation") and _ph not in _NS8.get("COMBINATION_THERAPY", {_ph: 1}):
        _ph_bad.append(f"{_ph}: raises an isolation alert with no therapy panel")
check("every phenotype rule is reachable: real markers, real organisms, "
      "a threshold it can meet",
      not _ph_bad, "\n".join(sorted(set(_ph_bad))[:8]))

_org_bad = []
for _where, _names in (("SPECIMEN_ORGANISM_MAP",
                        {o for v in _SOM.values() for o in v}),
                       ("ABX_GUIDELINES.organisms",
                        {o for v in G.values() for o in (v.get("organisms") or [])}),
                       # ORGANISM_OCR_ALIASES moved to ocr_parsing.py in the
                       # 2026-08-03 extraction; it is imported from its real
                       # home rather than lifted out of the monolith.
                       ("ORGANISM_OCR_ALIASES targets",
                        set(_OCR_ALIASES.values()))):
    for _o in _names:
        if _o in _ORGS8:
            continue
        # A genus-level token that a selectable species matches is intentional:
        # "Citrobacter spp." covers C. freundii, "Enterobacter spp." covers
        # E. cloacae, and "Escherichia coli" is the full binomial for the
        # profile keyed "E. coli". Resolve through the app's OWN canonical map
        # — the same one the engine matches with — rather than a bare substring
        # test, so this check agrees with runtime behaviour by construction.
        _c = _CANON8.get(collapse_ws(_o), collapse_ws(_o))
        if any(_c == collapse_ws(x) for x in _ORGS8):
            continue
        if any(_c in collapse_ws(x) or collapse_ws(x) in _c for x in _ORGS8):
            continue
        _org_bad.append(f"{_where}: {_o!r} matches no selectable organism")
check("every organism named anywhere is selectable or a covering genus token",
      not _org_bad, "\n".join(sorted(set(_org_bad))[:8]))

_spec_bad = []
for _where, _names in (("ORGANISM_PROFILE.specimen_context",
                        {s for p in OP.values() for s in (p.get("specimen_context") or {})}),
                       ("ABX_GUIDELINES.specimen_notes",
                        {s for v in G.values() for s in (v.get("specimen_notes") or {})}),
                       ("SITE_PENETRATION",
                        {s for r in _CM8.SITE_PENETRATION.values() for s in r}),
                       ("SPECIMEN_ORGANISM_MAP keys", set(_SOM))):
    _spec_bad += [f"{_where}: {s!r}" for s in _names if s not in _SPECS8]
check("every specimen named anywhere is selectable",
      not _spec_bad, "\n".join(sorted(set(_spec_bad))[:8]))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[9] DOCUMENTATION must match the code. An external review on")
print("    2026-08-06 found README claiming 34 organisms, 803 scenarios and 51")
print("    drugs while the code had 30, 1,344 and 60 — and AUDIT.md quoting")
print("    791 scenarios and 36 rules. None of it changes a clinical answer,")
print("    but a project whose own documents disagree with it invites a reader")
print("    to trust the wrong number, and a reviewer to doubt the right one.")
# ═══════════════════════════════════════════════════════════════════════════
import re as _re9
import json as _json9

try:
    _snap9 = _json9.load(open(os.path.join(HERE, "scenario_snapshot.json"),
                              encoding="utf-8"))
    _SNAP9 = len(_snap9.get("cases", _snap9)) if isinstance(_snap9, dict) else len(_snap9)
except Exception:
    _SNAP9 = None

_REAL9 = {"agents": len(G), "organisms": len(OP), "rows": len(IR)}
try:
    import guideline_registry as _GR9
    _REAL9["citations"] = len(_GR9.RULES)
except Exception:
    pass
if _SNAP9:
    _REAL9["snapshot"] = _SNAP9

# AUDIT.md is a CHANGE LOG. Numbers inside it describe the state at the time of
# an entry — "31 rules awaiting signature", "20 organisms", "51 drugs" were all
# true when written and rewriting them would falsify the record. Only the
# CURRENT-STATE document is checked, and only its summary tables.
_stale9 = []
for _doc in ("README.md",):
    _path = os.path.join(HERE, _doc)
    if not os.path.exists(_path):
        continue
    _t9 = open(_path, encoding="utf-8").read()
    # Numbers this project has actually had at some point. If one of these
    # appears next to a counting word, it is almost certainly a stale figure
    # rather than a coincidence.
    for _m9 in _re9.finditer(r"(\d[\d,]{1,6})\s*(كائن|سيناريو|دواء|قاعدة|صف)", _t9):
        _n9 = int(_m9.group(1).replace(",", ""))
        _w9 = _m9.group(2)
        _exp = {"كائن": _REAL9["organisms"], "دواء": _REAL9["agents"],
                "قاعدة": _REAL9.get("citations"), "صف": _REAL9["rows"]}.get(_w9)
        if _w9 == "سيناريو":
            continue                     # scenario counts are generated, not fixed
        if _exp and _n9 != _exp:
            _stale9.append(f"{_doc}: {_m9.group(0)!r} — the code has {_exp}")
check("README quotes the counts the code actually has",
      not _stale9, "\n".join(sorted(set(_stale9))[:8]))

# AUDIT.md is exempt from the count check but must carry a dated stamp, so a
# reader can tell a historical figure from a current one at a glance.
_audit9 = os.path.join(HERE, "AUDIT.md")
if os.path.exists(_audit9):
    _at9 = open(_audit9, encoding="utf-8").read()
    check("AUDIT.md states which figures are current and when they were checked",
          "الأرقام أعلاه محدَّثة" in _at9,
          "a change log without a dated current-state stamp reads as if every "
          "number in it is still true")

# Version pins must agree between the docs and the registry.
_pins9 = []
try:
    _reg9 = " ".join(str(v) for v in _GR9.SOURCES.values())
    for _doc in ("README.md",):
        _path = os.path.join(HERE, _doc)
        if not os.path.exists(_path):
            continue
        _t9 = open(_path, encoding="utf-8").read()
        for _pin, _label in (("v16.1", "EUCAST breakpoints"),
                             ("Ed36", "CLSI M100"),
                             ("2025", "WHO AWaRe")):
            if _pin in _t9 and _pin not in _reg9:
                _pins9.append(f"{_doc} cites {_label} {_pin}, the registry does not")
except Exception:
    pass
check("the version pins in README match the registry",
      not _pins9, "\n".join(_pins9))


# ═══════════════════════════════════════════════════════════════════════════
print("\n[X] ABX_GUIDELINES['organisms'] never contradicts INTRINSIC_RESISTANCE")
# ═══════════════════════════════════════════════════════════════════════════
# 2026-08-22: found by systematic cross-check, not by symptom. A drug's own
# "organisms" list (which organisms it's presented as treating) is
# independent, hand-maintained content from clinical_data.INTRINSIC_RESISTANCE
# (the authoritative table the rest of the engine defers to) -- nothing
# enforced they agree. Found two real contradictions this way:
#   - Cefepime listed Enterococcus faecalis (cephalosporins have no reliable
#     Enterococcus activity as a class -- well-established, unambiguous)
#   - Doxycycline listed Acinetobacter baumannii (EUCAST Intrinsic Resistance
#     and Unusual Phenotypes v3.3: "Acinetobacter is intrinsically resistant
#     to tetracycline and doxycycline but not to minocycline and tigecycline"
#     -- the same authoritative source this registry already cites elsewhere).
# Both fixed by removing the organism from the drug's list, not by touching
# INTRINSIC_RESISTANCE (which was independently confirmed correct against
# EUCAST's own table before either change was made).
_contradictions = []
for _drug, _v in G.items():
    for _org in _v.get("organisms", []):
        _ok = _org.lower().strip()
        for _k, _lst in IR.items():
            if _k and (_k in _ok or (len(_ok) >= 4 and _ok in _k)):
                if _drug in _lst:
                    _contradictions.append(f"{_drug} lists '{_org}' as treatable but "
                                           f"is intrinsically resistant per IR['{_k}']")
check("no drug's organisms[] list includes an organism it's intrinsically "
      "resistant against", not _contradictions, "\n".join(_contradictions))

check("Cefepime no longer lists Enterococcus faecalis",
      "Enterococcus faecalis" not in G["Cefepime"]["organisms"])
check("Doxycycline no longer lists Acinetobacter baumannii",
      "Acinetobacter baumannii" not in G["Doxycycline"]["organisms"])
# Minocycline/Tigecycline correctly keep Acinetobacter -- EUCAST's own
# sentence names them as the exception, not the rule, within this class.
if "Minocycline" in G:
    check("Minocycline still correctly lists Acinetobacter baumannii "
          "(EUCAST's stated exception within the tetracycline class)",
          "Acinetobacter baumannii" in G["Minocycline"].get("organisms", []))

print("\n" + "=" * 72)
print(f"{len(_PASS)} passed, {len(_FAIL)} failed")
if _FAIL:
    print("\nRESULT: FAILURES — see above")
    if __name__ == "__main__":
        sys.exit(1)
print("\nRESULT: ALL GREEN")
print("\nNOTE: this suite asserts what the TABLES SAY. Whether the engine")
print("      honours them is test_engine_agreement.py; whether the tables match")
print("      the published guideline is a clinician's signature, recorded in")
print("      guideline_registry.py.")
