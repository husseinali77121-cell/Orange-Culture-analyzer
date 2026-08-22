"""Orange Lab CDSS — guideline citation registry.

WHAT THIS FILE IS FOR
---------------------
A test suite can prove the code matches its rule tables. It cannot prove the
rule tables match EUCAST v16. Only a human reading the source document can do
that. This registry is where that human judgement is recorded so it is
auditable, attributable and expirable instead of living in someone's memory.

Every clinical rule in the engine gets one row: which document it comes from,
which edition, which table, who checked it against the actual PDF, and when.

VERIFICATION LEVELS
-------------------
  "source"    — the assertion was checked against the text of the source document
                itself (the EUCAST PDF, the guideline paper).
  "secondary" — checked against an authoritative published account of the source
                (a guideline summary, a national body's clarification, the
                journal article that carries the table) but not the primary PDF.
  "pending"   — inherited from earlier code. Probably right, but unverified.
                NOT a failure — this is the review queue.

ATTRIBUTION, HONESTLY
---------------------
`checked_by` records who or what performed the check. Where it reads
"AI-assisted review", the verification was done by a language model reading
published sources during a code review session — NOT by a clinician reading the
standard. That is genuinely useful and genuinely not the same thing.

`countersigned_by` is for the human who takes clinical responsibility. It is
empty on every row right now. test_guidelines.py reports the count and does not
fail, because an unsigned row is honest and a falsely signed one is not. Fill it
in as you review; do not fill it in for rows you have not read.

test_guidelines.py fails when a rule has no row at all, when a row points at an
undefined source, or when a "primary" row has gone stale. It reports the
"pending" count so the queue stays visible instead of quietly growing.

WHY THE SOURCE STRINGS ARE CENTRALISED HERE
-------------------------------------------
Free-text citations drift. An audit of this codebase found "EUCAST 2026" (21
occurrences — which document? breakpoints? expert rules?), "CLSI M100 2026"
alongside "CLSI M100 Ed36" for the same standard, and "IDSA AMR 2025" for a
document published in August 2024. Meanwhile "WHO AWaRe 2025 edition (B09489, 5 Sep 2025)" looked wrong from
memory and turned out to be correct — WHO published the 2025 edition on
2025-09-05. Memory is not a citation. A dated URL is.
"""
from __future__ import annotations

from typing import Any, Dict

# A "primary" verification older than this is treated as stale and must be
# re-checked. Eighteen months is one EUCAST breakpoint cycle plus a margin.
STALE_AFTER_MONTHS = 18

# ── Source documents ─────────────────────────────────────────────────────────
SOURCES: Dict[str, Dict[str, str]] = {
    "EUCAST_INTRINSIC": {
        "title": "EUCAST Intrinsic Resistance and Unusual Phenotypes",
        "version": "v3.3",
        "dated": "2021-10-18",
        "url": "https://www.eucast.org/expert_rules_and_expected_phenotypes",
    },
    "EUCAST_EXPERT": {
        "title": "EUCAST Expert Rules in Antimicrobial Susceptibility Testing "
                 "(Leclercq et al., Clin Microbiol Infect 2013;19:141-160)",
        "version": "v3.1 (2016) tables; v2 paper CMI 2013",
        "dated": "2016-10-29",
        "url": "https://www.clinicalmicrobiologyandinfection.org/article/S1198-743X(14)60249-4/fulltext",
    },
    "EUCAST_BP": {
        "title": "EUCAST Clinical Breakpoint Tables",
        "version": "v16.1",
        "dated": "2026-06-24",   # v16.0 valid 2026-01-01; v16.1 published 2026-06-24
        # Verified 2026-07-27. v16.1 adds clinical breakpoints for further
        # ANAEROBIC species including Fusobacterium. Two live consequences:
        #  * EUCAST has an ONGOING review of ertapenem, imipenem,
        #    imipenem-relebactam, meropenem, meropenem-vaborbactam and
        #    ceftazidime-avibactam breakpoints after a second consultation
        #  * the "When there are no breakpoints" guidance has been reissued
        "note": ("v16.1 (2026-06-24). Carbapenem breakpoints are under active "
                 "EUCAST review and the no-breakpoints guidance was reissued -- "
                 "re-read the carbapenem-hierarchy, anaerobe and no-breakpoint "
                 "rules against v16.1 before the next release."),
        "url": "https://www.eucast.org/clinical_breakpoints",
            "version_note": "v16.1 (2026). v16.0 took effect 1 Jan 2026; the v16.1 addendum added breakpoints for further anaerobic species and is the pin used here. Web-verified 2026-08-03. Also under EUCAST review: a proposed lowering of the pneumococcal penicillin meningitis/endocarditis IV breakpoint from 0.5 to 0.06 mg/L — NOT implemented, as it is proposed rather than published.",
},
    "EUCAST_DETECT": {
        "title": "EUCAST guidelines for detection of resistance mechanisms and "
                 "specific resistances of clinical and/or epidemiological importance",
        "version": "v2.0",
        "dated": "2017-07-11",
        "url": "https://www.eucast.org/fileadmin/src/media/PDFs/EUCAST_files/"
               "Resistance_mechanisms/EUCAST_detection_of_resistance_mechanisms_170711.pdf",
    },
    "CLSI_M100": {
        "title": "CLSI M100 — Performance Standards for Antimicrobial Susceptibility Testing",
        "version": "Ed36",
        "dated": "2026",
        "url": "https://clsi.org/standards/products/microbiology/documents/m100/",
    },
    "IDSA_AMR": {
        "title": "IDSA Guidance on the Treatment of Antimicrobial-Resistant "
                 "Gram-Negative Infections (Tamma et al., Clin Infect Dis)",
        # SUPERSEDED — verified 2026-07-27. IDSA published an updated AMR Guidance
        # in 2026 covering ESBL-E, AmpC-E, CRE, DTR P. aeruginosa, CRAB and
        # S. maltophilia, which explicitly replaces earlier versions. IDSA has
        # stated the guidance is now revised ANNUALLY, so a pinned 2024 citation
        # will go stale every year by design.
        "version": "SUPERSEDED: v4.0 (ciae403, 2024) — a 2026 update exists",
        "dated": "2024-08-07",
        "superseded_on": "2026",
        "note": ("Every rule citing IDSA_AMR must be re-read against the 2026 "
                 "document before the next release. The exact citation details "
                 "of the 2026 update were NOT verified here and must be filled "
                 "in from the published text, not assumed."),
        "url": "https://www.idsociety.org/practice-guideline/amr-guidance/",
    },
    "WHO_AWARE": {
        "title": "WHO AWaRe (Access, Watch, Reserve) classification of antibiotics "
                 "for evaluation and monitoring of use",
        "version": "2025 edition",
        "dated": "2025-09-05",
        "url": "https://www.who.int/publications/i/item/B09489",
    },
    "MAGIORAKOS": {
        "title": "Magiorakos et al. — Multidrug-resistant, extensively drug-resistant "
                 "and pandrug-resistant bacteria: an international expert proposal "
                 "(Clin Microbiol Infect 2012;18:268-281)",
        "version": "final",
        "dated": "2012-03",
        "url": "https://www.clinicalmicrobiologyandinfection.org/article/S1198-743X(14)61632-3/fulltext",
    },
    "CDC_EIP_CRPA": {
        "title": "Carbapenem-Resistant Pseudomonas aeruginosa at US Emerging "
                 "Infections Program Sites, 2015 (Emerg Infect Dis 2019;25:1281)",
        "version": "final",
        "dated": "2019-07",
        "url": "https://wwwnc.cdc.gov/eid/article/25/7/18-1200_article",
    },
}

# ── Rule rows ────────────────────────────────────────────────────────────────
# key = the rule id used in the engine. Keep these in sync; test_guidelines.py
# fails the build if an engine rule has no row here.
_AI = "AI-assisted review (Claude, code-review session 2026-07-23)"

# ═══════════════════════════════════════════════════════════════════════════
# SYSTEM_CITATIONS — rows that describe a CLASSIFICATION SYSTEM applied across
# the whole formulary rather than a single rule with an ID.
#
# test_guidelines.py requires every registry row to correspond to a rule the
# engine actually runs, and fails otherwise ("dead citation"). That check is
# correct and must stay: a citation for a rule that no longer exists is how a
# registry rots into decoration. But three clinical claims are not rules —
# WHO AWaRe categories, the Magiorakos MDR/XDR/PDR criteria and the CRPA
# definition apply across every agent or every organism at once. Before
# 2026-08-03 they were simply absent, so the suite reported "every rule traced"
# while three whole classification systems sat untraced.
#
# This set is the narrow, named exemption. Adding to it is a deliberate act and
# each entry must be a system, not a rule someone could not be bothered to
# register — that is why it is a hard-coded literal and not a pattern match.
# ═══════════════════════════════════════════════════════════════════════════
SYSTEM_CITATIONS = frozenset({
    "class_who_aware",
    "class_magiorakos_mdr",
    "class_crpa_definition",
})

RULES: Dict[str, Dict[str, Any]] = {

    # ── Classification systems (added 2026-08-03) ───────────────────────────
    # GAP THIS CLOSES: SOURCES declared WHO_AWARE, MAGIORAKOS and CDC_EIP_CRPA,
    # and not one rule cited any of them. Three whole classification systems —
    # 51 AWaRe assignments, the MDR/XDR/PDR criteria, and the CRPA definition —
    # were live clinical claims with no traceability row, so test_guidelines.py
    # reported "every rule traced" while these were invisible to it. A registry
    # that only contains the rules someone remembered to register is a registry
    # that measures memory, not coverage.
    "class_who_aware": {
        "assertion": "Every agent in ABX_GUIDELINES carries a WHO AWaRe "
                     "category (Access / Watch / Reserve) used for stewardship "
                     "ranking and for the Reserve penalty in the ranking engine.",
        "source": "WHO_AWARE", "locus": "AWaRe classification database",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-08-03",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "VERIFIED against the WHO Antibiotics Portal and the 2025 list "
                "on 2026-08-03. Three assignments were WRONG and are corrected: "
                "Aztreonam Watch->RESERVE; Fosfomycin(oral) Access->WATCH (IV is "
                "Reserve); Ampicillin/Sulbactam Watch->ACCESS. Two that looked "
                "wrong are right and were left alone: Tobramycin is WATCH while "
                "gentamicin and amikacin are ACCESS -- the three aminoglycosides "
                "do not share a category -- and Vancomycin is WATCH for both the "
                "IV and the oral route. The previous note flagged Aztreonam but "
                "declined to change it without reading the source; the source "
                "has now been read.",
    },
    "class_magiorakos_mdr": {
        "assertion": "MDR = non-susceptible to >=1 agent in >=3 antimicrobial "
                     "categories; XDR = non-susceptible to >=1 agent in all but "
                     "<=2 categories; PDR = non-susceptible to all agents in all "
                     "categories. Categories are organism-specific.",
        "source": "MAGIORAKOS", "locus": "Clin Microbiol Infect 2012;18:268-281",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-08-03",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "Implemented in classify_mdr() with 15 Gram-negative and 15 "
                "Gram-positive category sets. The reliability warnings for thin "
                "panels (few categories testable, or categories judged on a "
                "single agent) are a local addition beyond the paper — "
                "Magiorakos assumes a complete panel and says nothing about "
                "what to do with an incomplete one.",
    },
    "class_crpa_definition": {
        "assertion": "Carbapenem-resistant P. aeruginosa is defined by "
                     "resistance to at least ONE carbapenem (imipenem, "
                     "meropenem or doripenem). Ceftazidime and "
                     "piperacillin-tazobactam are NOT part of this definition; "
                     "they belong to difficult-to-treat resistance (DTR).",
        "source": "CDC_EIP_CRPA", "locus": "CDC EIP CRPA surveillance definition; "
                                           "IDSA AMR Guidance 2026 update (supersedes v4.0 2024)",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-08-03",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "Rewritten 2026-08-03, then re-verified against source the same "
                "day. DTR is non-susceptibility to ALL EIGHT of pip-tazo, "
                "ceftazidime, cefepime, aztreonam, meropenem, imipenem, "
                "ciprofloxacin and levofloxacin (Kadri 2018) -- an initial "
                "6-of-8 threshold over-called it. The engine now requires every "
                "one of the eight that was TESTED to be R, with a floor of five "
                "tested agents, which is the faithful reading under a partial "
                "panel. The previous rule required 2 of 4 markers "
                "and two of those four were non-carbapenems, so it MISSED a true "
                "CRPA when meropenem was the only carbapenem on the panel and "
                "CALLED CRPA on an isolate susceptible to both carbapenems. DTR "
                "is now a separate phenotype (DTR_PA) with its own panel, per "
                "Kadri et al. Clin Infect Dis 2018 and IDSA v4.0.",
    },

    # ── Intrinsic resistance (ast_reportability.INTRINSIC_RULES) ─────────────
    "intr_vre_vancomycin_contradiction": {
        "assertion": "An isolate identified as VRE and reported "
                     "vancomycin-susceptible is self-contradictory; one of the "
                     "two results is wrong. VanB isolates are genuinely "
                     "teicoplanin-susceptible, but never vancomycin-susceptible.",
        "source": "CLSI_M100", "locus": "Table 2D · EUCAST Expert Rules v3.1",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-08-01",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "The engine refused vancomycin here via the intrinsic table "
                "while the QC panel stayed silent — a split verdict between two "
                "panels on the same screen. Found by the engine-agreement "
                "suite, not by any existing guard.",
    },
    "intr_anaerobes_aminoglycosides_polymyxins": {
        "assertion": "Anaerobes are intrinsically resistant to aminoglycosides "
                     "(uptake across the cytoplasmic membrane requires an "
                     "oxygen-dependent proton-motive force), and to polymyxins, "
                     "aztreonam and trimethoprim. No breakpoints are published "
                     "for any of these against anaerobes.",
        "source": "EUCAST_INTRINSIC", "locus": "Table 5 (anaerobes)",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-08-01",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "Added with the taxonomic-inheritance fix. Anaerobes were "
                "selectable in the UI with NO row in clinical_data at all, so "
                "Gentamicin=S and Colistin=S reached the RECOMMENDED bucket and "
                "the QC panel said nothing. Aminoglycoside uptake is the "
                "textbook mechanism; CLSI M11 does not publish anaerobe "
                "breakpoints for aminoglycosides or polymyxins.",
    },
    "intr_haemophilus_gram_pos_agents": {
        "assertion": "Haemophilus influenzae, being Gram-negative, is "
                     "intrinsically resistant to glycopeptides, oxazolidinones, "
                     "daptomycin, fusidic acid and clindamycin. Macrolides are "
                     "NOT included: azithromycin and clarithromycin are "
                     "indicated agents.",
        "source": "EUCAST_INTRINSIC", "locus": "Table 3",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-08-01",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "H. influenzae was selectable in the UI but had no row in "
                "clinical_data, so Vancomycin/Linezolid=S were unflagged by QC "
                "and RECOMMENDED by the engine. The macrolide exclusion is "
                "deliberate and is the reason the family-level Enterobacterales "
                "row was NOT reused here.",
    },
    "intr_entero_gram_pos_agents": {
        "assertion": "Enterobacterales are intrinsically resistant to macrolides, "
                     "lincosamides, glycopeptides, oxazolidinones, daptomycin, "
                     "fusidic acid, rifampicin and the anti-staphylococcal penicillins.",
        "source": "EUCAST_INTRINSIC", "locus": "Table 2",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'EUCAST Expert Rules names Enterobacterales resistant to glycopeptides and linezolid as a worked example.',
    },
    "intr_klebsiella_ampicillin": {
        "assertion": "Klebsiella spp. carry chromosomal SHV-1 -> intrinsic "
                     "aminopenicillin resistance; inhibitor combinations are NOT intrinsic.",
        "source": "EUCAST_INTRINSIC", "locus": "Table 2",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'Chromosomal class-A beta-lactamase; inhibitor combinations remain reportable. Same mechanism class as C. koseri/K. oxytoca.',
    },
    "intr_proteus_mirabilis": {
        "assertion": "P. mirabilis is intrinsically resistant to tetracyclines, "
                     "colistin/polymyxin and nitrofurantoin.",
        "source": "EUCAST_INTRINSIC", "locus": "Table 2",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'EUCAST Expert Rules paper names P. mirabilis resistant to nitrofurantoin and colistin as a worked example of intrinsic resistance.',
    },
    "intr_morganella_providencia_proteus_vulgaris": {
        "assertion": "Morganella, Providencia, P. vulgaris/penneri: chromosomal AmpC "
                     "plus tribe traits -> aminopenicillins (inhibitor combinations "
                     "included), 1st/2nd-gen cephalosporins, cephamycins, "
                     "tetracyclines, colistin, nitrofurantoin.",
        "source": "EUCAST_INTRINSIC", "locus": "Table 2",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'EUCAST v3.2 changelog moved Providencia cefuroxime/tigecycline out of the intrinsic table into the expert rules — verify the current placement when the v16 tables are read.',
    },
    "intr_serratia": {
        "assertion": "Serratia marcescens: chromosomal AmpC -> aminopenicillins, "
                     "1st/2nd-gen cephalosporins, cephamycins; plus colistin and "
                     "nitrofurantoin.",
        "source": "EUCAST_INTRINSIC", "locus": "Table 2",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'EUCAST v3.3 Table 2 fn.5: intrinsically R to tetracycline and doxycycline but NOT minocycline or tigecycline. The code had both halves wrong — tigecycline was banned, tetracycline/doxycycline were missing. Corrected.',
    },
    "intr_enterobacter_citrobacter_ampc": {
        "assertion": "Inducible chromosomal AmpC (Enterobacter, K. aerogenes, "
                     "C. freundii, Hafnia) -> aminopenicillins, amoxicillin-clavulanate, "
                     "ampicillin-sulbactam, 1st/2nd-gen cephalosporins and cephamycins. "
                     "Sulbactam does not inhibit AmpC, so amp-sulbactam is NOT exempt.",
        "source": "IDSA_AMR", "locus": "AmpC-E section",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "IDSA v4.0 states basal AmpC production confers intrinsic resistance "
                "to ampicillin, amoxicillin-clavulanate, ampicillin-sulbactam and "
                "1st/2nd-generation cephalosporins.",
    },
    "intr_pseudomonas": {
        "assertion": "P. aeruginosa is intrinsically resistant to aminopenicillins, "
                     "1st/2nd/non-antipseudomonal 3rd-gen cephalosporins, ertapenem, "
                     "tetracyclines, trimethoprim, chloramphenicol, nitrofurantoin. "
                     "Ceftazidime and cefepime remain active.",
        "source": "EUCAST_INTRINSIC", "locus": "Table 3",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'EUCAST v3.3 Table 3 header: non-fermenters are intrinsically resistant to benzylpenicillin, 1st/2nd-gen cephalosporins, glycopeptides, lipoglycopeptides, fusidic acid, macrolides, lincosamides, streptogramins, rifampicin and oxazolidinones.',
    },
    "intr_acinetobacter": {
        "assertion": "Acinetobacter spp. are intrinsically resistant to ampicillin, "
                     "amoxicillin, AMOXICILLIN-CLAVULANATE, aztreonam, ertapenem, "
                     "trimethoprim, chloramphenicol and fosfomycin. "
                     "Ampicillin-SULBACTAM is the exception — sulbactam has intrinsic "
                     "anti-Acinetobacter activity of its own. ALSO (Table 2 fn.2): "
                     "intrinsically resistant to TETRACYCLINE and DOXYCYCLINE but "
                     "NOT to minocycline and tigecycline.",
        "source": "EUCAST_INTRINSIC", "locus": "Table 3",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "Two separate defects fixed here. (1) The code EXCLUDED 'clav', "
                "exempting amox-clav from a restriction EUCAST applies to it -- "
                "clavulanate has no useful activity against Acinetobacter, "
                "sulbactam does. (2) Doxycycline was ABSENT from the table and was "
                "being offered as an active option, contradicting fn.2 verbatim: "
                "'Acinetobacter is intrinsically resistant to tetracycline and "
                "doxycycline but not to minocycline and tigecycline.' Minocycline "
                "was not in the formulary at all and has been added, since it is "
                "the tetracycline that actually works here.",
    },
    "intr_stenotrophomonas": {
        # DUPLICATE-KEY FIX: this row carried verified/checked_by/checked_on/
        # countersigned_by TWICE. Python keeps the last occurrence, so the first
        # set was silently discarded -- harmless while the values matched, but a
        # trap the moment someone edited the top pair and saw no effect.
        "assertion": "S. maltophilia: L1 metallo-beta-lactamase -> all carbapenems, "
                     "plus intrinsic aminoglycoside and most beta-lactam resistance. "
                     "TMP-SMX is the established agent. Table 2 fn.7 is NARROWER "
                     "than fn.2/fn.5: intrinsically resistant to TETRACYCLINE only "
                     "-- doxycycline, minocycline and tigecycline stay active.",
        "source": "EUCAST_INTRINSIC", "locus": "Table 3",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'EUCAST Expert Rules names S. maltophilia resistant to carbapenems as a worked example of intrinsic resistance.',
    },
    "intr_mrsa_betalactams": {
        "assertion": "MRSA carries mecA/mecC encoding low-affinity PBP2a, so ALL "
                     "conventional beta-lactams are inactive; only ceftaroline and "
                     "ceftobiprole retain activity.",
        "source": "EUCAST_EXPERT", "locus": "staphylococci; CLSI M100 Ed36 Table 2C",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "Added after an audit found the UI label 'MRSA' shared no substring "
                "with the table key 'staphylococcus aureus', so MRSA received NO "
                "intrinsic filtering at all -- aztreonam and colistin were offered "
                "for it while S. aureus correctly refused them.",
    },
    "intr_mycoplasma_cellwall_agents": {
        "assertion": "Mycoplasma and Ureaplasma have no peptidoglycan cell wall, so "
                     "beta-lactams, glycopeptides and fosfomycin are intrinsically "
                     "inactive.",
        "source": "EUCAST_INTRINSIC", "locus": "organisms without a cell wall",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "Textbook microbiology; the table had no Mycoplasma key so the "
                "engine could have recommended ampicillin for atypical pneumonia.",
    },
    "intr_staph_gram_neg_agents": {
        "assertion": "Staphylococci are intrinsically resistant to aztreonam, "
                     "colistin/polymyxin, nalidixic acid and temocillin.",
        "source": "EUCAST_EXPERT", "locus": "Table 4",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "Table 4 header states Gram-positive bacteria are additionally "
                "intrinsically resistant to aztreonam, temocillin, polymyxin "
                "B/colistin and nalidixic acid.",
    },
    "intr_enterococcus_cephalosporins": {
        "assertion": "Enterococci are intrinsically resistant to ALL cephalosporins, "
                     "clindamycin, fusidic acid and aztreonam.",
        "source": "EUCAST_EXPERT", "locus": "Table 4",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "CLSI M100 Enterococcus WARNING verbatim: 'For Enterococcus spp., aminoglycosides (except for high-level resistance testing), cephalosporins, clindamycin, and trimethoprim-sulfamethoxazole may appear active in vitro, but are not effective clinically and should not be reported as susceptible.' EUCAST v3.3 Table 4 rows 4.7-4.9 carry R in the cephalosporin and clindamycin columns; aztreonam comes from the Table 4 header for all Gram-positives.",
    },
    "intr_strep_enterococcus_aminoglycosides": {
        "assertion": "Enterococci and streptococci have intrinsic LOW-LEVEL "
                     "aminoglycoside resistance: never valid as monotherapy, and the "
                     "routine 10 ug disk is not interpretable. Synergy with a "
                     "cell-wall-active agent is real but is predicted only by a "
                     "HIGH-CONTENT HLAR screen (gentamicin 120 ug / streptomycin "
                     "300 ug). Amikacin and tobramycin have no HLAR screen.",
        "source": "EUCAST_EXPERT", "locus": "Table 4 (+ CLSI M100 Ed36 Table 2D)",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "Added after the scenario matrix (INV-9) found clinical_data banning "
                "aminoglycosides for these organisms with no matching QC rule. "
                "EUCAST Table 4 footnote: aminoglycoside + cell-wall-inhibitor "
                "combinations are synergistic and bactericidal against isolates "
                "susceptible to the cell-wall agent and without high-level "
                "aminoglycoside resistance.",
    },
    "intr_enterococcus_sxt_invivo": {
        "assertion": "Enterococci test susceptible to TMP-SMX in vitro but are not "
                     "clinically responsive — they take up exogenous folate and "
                     "bypass the blocked pathway. Do not report.",
        "source": "EUCAST_EXPERT", "locus": "Table 4 / CLSI M100 Appendix B",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "Same CLSI Enterococcus WARNING names trimethoprim-sulfamethoxazole explicitly and says do not report as susceptible. Confirms both the phenomenon and the 'do not report' instruction.",
    },
    "intr_listeria_cephalosporins": {
        "assertion": "L. monocytogenes is intrinsically resistant to all "
                     "cephalosporins — a known cause of meningitis treatment failure. "
                     "Ampicillin is the agent.",
        "source": "EUCAST_EXPERT", "locus": "Table 4",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "CAVEAT: the clinical fact is not in doubt -- cephalosporins fail against Listeria and this drives the 'add ampicillin' rule in empiric meningitis therapy. However EUCAST v3.3 Table 4 row 4.11 shows only two R marks for L. monocytogenes and the column alignment could NOT be resolved from the flattened PDF text, so the exact cell mapping is unconfirmed. Verify against the PDF before countersigning.",
    },

    "intr_nonfermenter_narrow_spectrum": {
        "assertion": "Non-fermentative Gram-negatives (Pseudomonas, Acinetobacter, "
                     "Stenotrophomonas, Burkholderia) are intrinsically resistant to "
                     "benzylpenicillin, 1st/2nd-generation cephalosporins, "
                     "glycopeptides, lipoglycopeptides, fusidic acid, macrolides, "
                     "lincosamides, rifampicin and oxazolidinones.",
        "source": "EUCAST_INTRINSIC", "locus": "Table 3 (header)",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "Promoted from a 'no breakpoints' rule: EUCAST states these are "
                "intrinsically resistant, which is a stronger and more useful claim.",
    },
    "intr_citrobacter_koseri_klebsiella_oxytoca_classA": {
        "assertion": "C. koseri and K. oxytoca carry a chromosomal CLASS A "
                     "beta-lactamase — intrinsic aminopenicillin resistance, but "
                     "inhibitor combinations remain active (unlike the AmpC species).",
        "source": "EUCAST_INTRINSIC", "locus": "Table 2",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "Added after the expanded scenario matrix found C. koseri matched no "
                "rule at all — the only Citrobacter rule targeted C. freundii's AmpC.",
    },

    # ── No breakpoints (ast_reportability.NO_BREAKPOINT_RULES) ───────────────
    "nobp_nonfermenter_narrow_spectrum": {
        "recheck": "EUCAST reissued the 'When there are no breakpoints' guidance in 2026; re-read.",
        "assertion": "Neither EUCAST nor CLSI publishes breakpoints for narrow-spectrum "
                     "cephalosporins, nitrofurantoin or norfloxacin against "
                     "Acinetobacter / Stenotrophomonas / Burkholderia.",
        "source": "EUCAST_BP", "locus": "non-fermenter tables; CLSI M100 Table 2B-2/2B-3",
        "verified": "pending",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
    },
    "nobp_azithromycin_enterobacterales": {
        "assertion": "Azithromycin breakpoints exist only for Salmonella Typhi/Paratyphi "
                     "and Shigella. Non-typhoidal Salmonella has none.",
        "source": "EUCAST_BP", "locus": "Enterobacterales — azithromycin note",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "CLSI M100 azithromycin footnote p verbatim: 'For reporting against Salmonella enterica ser. Typhi and Shigella spp. only.' Confirms non-typhoidal Salmonella has no azithromycin reporting criterion.",
    },
    "nobp_cefoperazone": {
        "recheck": "EUCAST reissued the 'When there are no breakpoints' guidance in 2026; re-read.",
        "assertion": "Cefoperazone alone or with sulbactam has no EUCAST breakpoints; "
                     "CLSI withdrew the cefoperazone breakpoints. Widely used in Egypt, "
                     "but the result is uncalibrated.",
        "source": "EUCAST_BP", "locus": "absent from tables; CLSI M100 Ed36",
        "verified": "pending",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
    },
    "nobp_nitrofurantoin_non_ecoli": {
        "assertion": "EUCAST nitrofurantoin breakpoints are for E. coli only "
                     "(uncomplicated UTI) and do not extrapolate to other species.",
        "source": "EUCAST_BP", "locus": "Enterobacterales",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'BSAC clarification of EUCAST guidance: after review the nitrofurantoin breakpoints could NOT be extended beyond E. coli; Proteeae, some Klebsiella and Pseudomonas carry intrinsic resistance.',
    },
    "nobp_fosfomycin_oral_non_ecoli": {
        "assertion": "Oral fosfomycin breakpoints are restricted to E. coli in both "
                     "EUCAST and CLSI.",
        "source": "EUCAST_BP", "locus": "Enterobacterales",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "EUCAST guidance on fosfomycin i.v. breakpoints (May 2024) verbatim: 'The currently revised breakpoint of fosfomycin applies only to E. coli in infections originating from the urinary tract.' Breakpoint tables add: 'Zone diameter breakpoints apply to E. coli only.'",
    },
    "nobp_imipenem_proteae": {
        "assertion": "Imipenem has intrinsically LOW activity against Proteus spp., "
                     "Morganella morganii and Providencia spp.; do not rely on a "
                     "Susceptible imipenem result -- meropenem is preferred.",
        "source": "EUCAST_BP", "locus": "Enterobacterales note 2",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "NEW RULE added this round; the engine had no equivalent.",
    },
    "nobp_tigecycline_proteae": {
        "assertion": "Tigecycline has no breakpoint for the Proteae "
                     "(Proteus / Providencia / Morganella), which are intrinsically "
                     "less susceptible via efflux.",
        "source": "EUCAST_BP", "locus": "Enterobacterales — tigecycline note",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'EUCAST v16.1 Enterobacterales note 3/A verbatim: activity is INSUFFICIENT in Serratia spp., Proteus spp., Morganella morganii and Providencia spp. SERRATIA was missing from the rule and has been added. Breakpoint is validated for E. coli and C. koseri only.',
    },

    # ── Ineffective in vivo ──────────────────────────────────────────────────
    "invivo_salmonella_shigella_aminoglycoside_ceph12": {
        "assertion": "Aminoglycosides and 1st/2nd-gen cephalosporins may test "
                     "susceptible against Salmonella/Shigella but are clinically "
                     "ineffective for invasive infection — do not report S.",
        "source": "CLSI_M100", "locus": "Table 2A organism-specific notes",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "CLSI M100 WARNING verbatim: 'For Salmonella and Shigella spp., aminoglycosides, first- and second-generation cephalosporins, and cephamycins may appear active in vitro but are not effective clinically and should not be reported as susceptible.' Carried into Ed36 (2026).",
    },

    # ── Internal consistency (ast_consistency) ───────────────────────────────
    "equiv_oxa_fox": {
        "assertion": "Oxacillin and cefoxitin are surrogate readings of the same "
                     "mecA/mecC mechanism in staphylococci; discordance between "
                     "them means one disk is wrong, and cefoxitin is the more "
                     "reliable predictor.",
        "source": "CLSI_M100", "locus": "M100 Ed36 Table 2C — cefoxitin as mecA surrogate",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-27",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'Cefoxitin is the recommended surrogate for mecA-mediated resistance in S. aureus and CoNS. Raised as an error, not a verify flag, because the split decides whether every beta-lactam on the panel is reportable.',
    },
    "rare_vrsa": {
        "assertion": "Vancomycin-resistant S. aureus is exceptional and requires "
                     "MIC confirmation on a pure colony before release.",
        "source": "CLSI_M100", "locus": "M100 Ed36 — S. aureus vancomycin MIC only",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-27",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'CLSI requires an MIC method for S. aureus vancomycin; disk diffusion cannot detect VISA/VRSA. A resistant result is far more often a mixed culture or misidentification.',
    },
    "rare_van_pneumococcus": {
        "assertion": "Vancomycin-resistant S. pneumoniae has not been described; "
                     "such a result indicates misidentification.",
        "source": "CLSI_M100", "locus": "M100 Ed36 — S. pneumoniae identification",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-27",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'Most often Enterococcus, Leuconostoc or Lactobacillus mistaken for pneumococcus. Confirm with optochin and bile solubility.',
    },
    "rare_pen_gas": {
        "assertion": "Streptococcus pyogenes remains universally penicillin-"
                     "susceptible; clinical resistance has not been documented.",
        "source": "CLSI_M100", "locus": "M100 Ed36 — beta-haemolytic streptococci",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-27",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'Both CLSI and EUCAST allow penicillin susceptibility in group A streptococci to be inferred without testing. A resistant result is an identification or reading error.',
    },
    "rare_linezolid_gram_pos": {
        "assertion": "Linezolid resistance in staphylococci, enterococci and "
                     "streptococci is very rare and requires MIC confirmation.",
        "source": "EUCAST_BP", "locus": "v16.1 — oxazolidinones",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-27",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'Usually emerges only after prolonged linezolid exposure (cfr / 23S rRNA mutations). Confirm before reporting and review the treatment history.',
    },
    "rare_colistin_disc": {
        "assertion": "Colistin cannot be tested by disk diffusion or gradient "
                     "strip; only broth microdilution gives a valid result.",
        "source": "EUCAST_BP", "locus": "EUCAST-CLSI Polymyxin Breakpoints Working Group (2016)",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-27",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'Polymyxins diffuse poorly in agar, so any disk or strip result is invalid regardless of what it shows. A resistant colistin result must be confirmed by BMD before it changes therapy.',
    },
    "equiv_ctx_cro": {
        "assertion": "Cefotaxime and ceftriaxone share MIC breakpoints against "
                     "Enterobacterales and are hydrolysed near-identically by common "
                     "ESBLs; one S and one R on the same isolate is a laboratory error.",
        "source": "EUCAST_BP", "locus": "Enterobacterales; CLSI M100 Table 2A",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'Cefotaxime and ceftriaxone share Enterobacterales breakpoints in both EUCAST and CLSI. Treated as a VERIFY flag rather than a hard error, since rare enzyme-specific discordance exists.',
    },
    "equiv_amc_sam": {
        "assertion": "Amoxicillin-clavulanate and ampicillin-sulbactam behave "
                     "near-identically against Enterobacterales; a split result is a "
                     "laboratory error, not a resistance pattern.",
        "source": "EUCAST_EXPERT", "locus": "beta-lactam interpretive rules",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'DOWNGRADED to a verify-flag this round. Sulbactam and clavulanate differ in potency and carry different breakpoints and dosing, so a split result is unusual rather than impossible.',
    },
    "hier_amp_vs_amc": {
        "assertion": "Ampicillin S with amoxicillin-clavulanate R is impossible — "
                     "adding a beta-lactamase inhibitor cannot reduce activity.",
        "source": "EUCAST_EXPERT", "locus": "beta-lactam hierarchy",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'Adding a beta-lactamase inhibitor cannot reduce activity, so the pattern indicates a testing error. Kept as a verify-flag.',
    },
    "hier_pip_vs_tzp": {
        "assertion": "Piperacillin S with piperacillin-tazobactam R is impossible, "
                     "for the same reason.",
        "source": "EUCAST_EXPERT", "locus": "beta-lactam hierarchy",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'Same logic as hier_amp_vs_amc. Rare tazobactam inoculum effects are described, so verify rather than declare impossible.',
    },
    "hier_mem_vs_etp": {
        "recheck": "EUCAST v16.1 -- carbapenem breakpoints under active review after a second consultation; re-read when it closes.",
        "assertion": "Meropenem R with ertapenem S is the wrong way round; ertapenem "
                     "is the most labile carbapenem, so the usual pattern is the "
                     "reverse (ertapenem-R with meropenem-S = OXA-48 or porin loss).",
        "source": "EUCAST_EXPERT", "locus": "carbapenem interpretive rules",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": 'Ertapenem is the most labile carbapenem; the ertapenem-R/meropenem-S direction is the recognised OXA-48 or porin-loss signature. The reverse warrants a repeat.',
    },
    "hier_tet_vs_doxy": {
        "assertion": "Tetracycline S predicts doxycycline/minocycline S; the reverse "
                     "combination is a reading error.",
        "source": "EUCAST_EXPERT", "locus": "tetracycline interpretive rules",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "CLSI M100 footnote q VERBATIM: 'Organisms that are susceptible to tetracycline are also considered susceptible to doxycycline and minocycline. However, some organisms that are intermediate or resistant to tetracycline may be susceptible to doxycycline, minocycline, or both.' The code already flags ONLY the safe direction (tet-S + doxy-R) and states the reverse is allowed, so it matches the footnote exactly and does NOT suppress an active minocycline.",
    },

    # ── Inline rules in streamlit_app.py ─────────────────────────────────────
    "QC003": {
        "assertion": "A carbapenem susceptible while colistin is resistant amid broad "
                     "resistance is an atypical pattern; confirm the identification.",
        "source": "EUCAST_EXPERT", "locus": "unusual phenotypes",
        "verified": "pending",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
    },
    "QC004": {
        "assertion": "Carbapenem R with a cephalosporin S in Enterobacterales is "
                     "uncommon (OXA-48-like or porin loss) and should be confirmed by "
                     "a carbapenemase assay.",
        "source": "EUCAST_DETECT", "locus": "carbapenemase detection",
        "verified": "pending",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
    },
    "QC005": {
        "assertion": "Linezolid resistance in S. aureus is very rare; confirm by a "
                     "reference method before reporting.",
        "source": "CLSI_M100", "locus": "Table 2C notes",
        "verified": "pending",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
    },
    "QC006": {
        "assertion": "A susceptible cephalosporin in a suspected ESBL producer is "
                     "reported AS TESTED. Current breakpoints already detect the "
                     "clinically important mechanisms; editing S to R on mechanism "
                     "detection is the pre-2017 practice and was withdrawn. ESBL "
                     "detection is for infection control and surveillance. Preferring "
                     "a carbapenem in serious ESBL infection is a prescribing decision, "
                     "not a reporting edit.",
        "source": "EUCAST_BP", "locus": "Enterobacterales — cephalosporin/ESBL note",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
    },
    "SPEC-URN": {
        "assertion": "Nitrofurantoin, oral fosfomycin and norfloxacin reach "
                     "therapeutic concentrations only in urine (and, for norfloxacin, "
                     "the GI tract); a result on a systemic isolate is not clinically "
                     "actionable.",
        "source": "EUCAST_BP", "locus": "agent site-of-infection notes",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "EUCAST breakpoint tables label these agents '(uncomplicated UTI only)' in the Enterobacterales table headers (nitrofurantoin, trimethoprim, oral fosfomycin), which carries the site restriction. The pharmacology claim itself is textbook but was not read from a primary PK document.",
    },
    "REP-GPO-GN": {
        "assertion": "Glycopeptides, oxazolidinones and daptomycin have no activity "
                     "and no breakpoint against Gram-negative bacteria and must never "
                     "be tested or reported for them.",
        "source": "EUCAST_INTRINSIC", "locus": "Table 2/3",
        "verified": "source", "checked_by": _AI, "checked_on": "2026-07-22",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-03",
        "note": "EUCAST Table 1 header verbatim: 'Enterobacterales are also intrinsically resistant to benzylpenicillin, glycopeptides, fusidic acid, macrolides, lincosamides, streptogramins, rifampicin, daptomycin and linezolid.' Table 3 header carries the same for non-fermenters.",
    },

    # ── AST Panel Completeness (added 2026-08-20, re-grounded 2026-08-21) ────
    # GAP THIS CLOSES: ast_panel_completeness.py introduces a new question the
    # registry had no rows for — "was enough tested at all", as distinct from
    # every other rule here, which answers "was what WAS tested interpreted
    # correctly". Six of the ten rows below moved from "pending" to "secondary"
    # on 2026-08-21 after being checked against the actual CLSI M100 36th ed.
    # (2026) Table 1 tier assignments — the same edition already cited
    # everywhere else in this registry — via a secondary tabulation (Giri D.,
    # LaboratoryTests.org, Feb-Mar 2026, itself citing CLSI M100 36th ed. 2026
    # directly per organism). "Secondary" here still means Dr. Tarek has not
    # read it — it means the underlying tier data is no longer guessed. The
    # remaining four (Stenotrophomonas, S. pneumoniae, beta-haemolytic Strep,
    # H. influenzae) stay "pending": clinically reasoned, CLSI M100 Table 1
    # convention-informed, not independently re-verified against Ed36.
    # See ast_panel_completeness.py's module docstring for the full reasoning,
    # the curation policy (why "primary" is a trimmed routine set rather than
    # every CLSI-Tier-1-eligible agent), and the per-group notes.
    "panel_salmonella_shigella": {
        "assertion": "Expected AST panel for Salmonella/Shigella spp. (CLSI "
                     "M100 Ed36): primary = Ampicillin, Trimethoprim/"
                     "Sulfamethoxazole, Ciprofloxacin, Ceftriaxone; "
                     "supplemental = Azithromycin.",
        "source": "CLSI_M100", "locus": "M100 36th ed. (2026), Salmonella/Shigella table",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-08-21",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-22",
        "note": "Deliberately excludes aminoglycosides and 1st/2nd-gen cephalosporins/cephamycins from both tiers — Ed36 states directly these 'may appear active in vitro but are not effective clinically and should not be reported as susceptible' for Salmonella/Shigella. There is no intrinsic beta-lactam resistance in these genera per the same table. Ceftriaxone included for invasive/enteric-fever presentations; azithromycin scoped to S. Typhi/Shigella per the existing azithromycin-footnote rule elsewhere in this registry.",
    },
    "panel_enterobacterales": {
        "assertion": "Expected AST panel for Enterobacterales (excl. Salmonella/"
                     "Shigella), CLSI M100 Ed36 Table 1A: primary (curated "
                     "routine subset of Ed36 Tier 1) = Ampicillin, Ceftriaxone, "
                     "Gentamicin, Ciprofloxacin, Trimethoprim/Sulfamethoxazole, "
                     "Piperacillin+Tazobactam; supplemental (remaining Tier 1 "
                     "alternates + Tier 2) = Amoxicillin+Clavulanic acid, "
                     "Ampicillin/Sulbactam, Cefotaxime, Levofloxacin, Amikacin, "
                     "Cefoxitin, Cefepime, Cefuroxime, Ertapenem, Imipenem/"
                     "Cilastatin, Meropenem, Tetracycline, Tobramycin; "
                     "urine-specimen addition (Tier 1, urine-scoped in Ed36) = "
                     "Nitrofurantoin, Fosfomycin, Cefazolin.",
        "source": "CLSI_M100", "locus": "M100 36th ed. (2026) Table 1A — Enterobacterales",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-08-21",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-22",
        "note": "Ed36 Table 1A Tier 1 is actually broader than 'primary' here (also lists amox-clav, amp-sulbactam, cefotaxime, levofloxacin) -- trimmed to a non-redundant routine set per this module's curation policy so class-mate alternates (e.g. cefotaxime vs ceftriaxone, cipro vs levo) don't both get flagged as missing; the untrimmed remainder lives in 'supplemental', not dropped.",
    },
    "panel_pseudomonas": {
        "assertion": "Expected AST panel for Pseudomonas aeruginosa, CLSI M100 "
                     "Ed36 Table 1B-1: primary (curated Tier 1 subset) = "
                     "Cefepime, Ceftazidime, Ciprofloxacin, Piperacillin+"
                     "Tazobactam, Tobramycin; supplemental (Tier 1 alternate + "
                     "Tier 2-4) = Levofloxacin, Amikacin, Imipenem/Cilastatin, "
                     "Meropenem, Aztreonam, Colistin, Cefiderocol, Ceftazidime+"
                     "Avibactam, Ceftolozane+Tazobactam.",
        "source": "CLSI_M100", "locus": "M100 36th ed. (2026) Table 1B-1 — Pseudomonas aeruginosa",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-08-21",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-22",
    },
    "panel_acinetobacter": {
        "assertion": "Expected AST panel for Acinetobacter baumannii, CLSI "
                     "M100 Ed36 Table 1B-2: primary (Tier 1) = Ampicillin/"
                     "Sulbactam, Cefepime, Ceftazidime, Ciprofloxacin, "
                     "Gentamicin; supplemental (Tier 1 alternate + Tier 2) = "
                     "Levofloxacin, Tobramycin, Amikacin, Imipenem/Cilastatin, "
                     "Meropenem, Minocycline, Piperacillin+Tazobactam, "
                     "Trimethoprim/Sulfamethoxazole, Colistin. Cefotaxime/"
                     "ceftriaxone are Ed36 Tier 4 (on request) for this "
                     "organism and are excluded from both tiers.",
        "source": "CLSI_M100", "locus": "M100 36th ed. (2026) Table 1B-2 — Acinetobacter spp.",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-08-21",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-22",
        "note": "This module's original 2026-08-20 draft placed meropenem supplemental (correctly, on a secondary changelog source) but ALSO had ampicillin/sulbactam+amikacin+TMP-SMX as the only primary agents, missing that cefepime/ceftazidime/ciprofloxacin/gentamicin are the actual Ed36 Tier-1 (routine) set. Corrected 2026-08-21 directly against the Ed36 tabulation. This is the row in the whole batch most worth Dr. Tarek reading against the actual Ed36 Table 1B-2 -- carbapenem-vs-Acinetobacter tier placement is too clinically consequential to leave unread.",
    },
    "panel_stenotrophomonas": {
        "assertion": "Expected AST panel for Stenotrophomonas maltophilia: "
                     "primary = Trimethoprim/Sulfamethoxazole, Levofloxacin, "
                     "Minocycline; supplemental = none.",
        "source": "CLSI_M100", "locus": "M100 Ed36 Table 1B — Stenotrophomonas maltophilia",
        "verified": "pending", "checked_by": _AI, "checked_on": "2026-08-21",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-22",
        "note": "Minocycline moved from supplemental to primary on 2026-08-21: CLSI's own 'AST News Update' (Jan 2024, Table Tips) uses this exact organism/agent as its worked example of a Tier-1 gap ('minocycline is in Tier 1' for Stenotrophomonas), which is a primary-adjacent CLSI source, not a guess -- but the rest of this row has not been independently re-verified against the full Ed36 Table 1B, so it stays 'pending' rather than 'secondary'. Deliberately narrow otherwise -- cross-checked against clinical_data.INTRINSIC_RESISTANCE before adding anything, since Stenotrophomonas is intrinsically resistant to carbapenems and most beta-lactams/aminoglycosides and this list must never contradict that table.",
    },
    "panel_staphylococcus": {
        "assertion": "Expected AST panel for Staphylococcus spp. (S. aureus/"
                     "MRSA/CoNS), CLSI M100 Ed36 table: primary (curated "
                     "routine subset of Ed36 Tier 1) = Cefoxitin, Clindamycin, "
                     "Erythromycin, Trimethoprim/Sulfamethoxazole, Vancomycin, "
                     "Doxycycline; supplemental (remaining Tier 1 alternates + "
                     "Tier 2-4) = Oxacillin, Azithromycin, Clarithromycin, "
                     "Minocycline, Tetracycline, Linezolid, Penicillin, "
                     "Ceftaroline, Ciprofloxacin, Gentamicin, Levofloxacin; "
                     "urine addition = Nitrofurantoin. Rifampin/Rifampicin is "
                     "CLSI-eligible (Tier 3) but deliberately not listed: it "
                     "has no OCR alias in this codebase, so it can never be "
                     "recognized as tested and would sit permanently flagged.",
        "source": "CLSI_M100", "locus": "M100 36th ed. (2026) table — Staphylococcus aureus",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-08-21",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-22",
        "note": "Cefoxitin+Oxacillin both tracked regardless of organism name -- this checks whether the mecA screen was run, not what it showed. Vancomycin moved from supplemental to primary on 2026-08-21: confirmed Ed36 Tier 1, not Tier 2 as this module's original draft assumed. Ed36 Tier 1 actually lists all three macrolides and all three tetracycline-class agents separately -- trimmed to one representative of each redundant class for 'primary' per this module's curation policy; the untrimmed remainder is 'supplemental'.",
    },
    "panel_enterococcus": {
        "assertion": "Expected AST panel for Enterococcus spp. (incl. VRE), "
                     "CLSI M100 Ed36 table: primary (Tier 1) = Ampicillin, "
                     "Penicillin, Vancomycin; supplemental (Tier 2) = "
                     "Linezolid, Daptomycin, Teicoplanin; urine-specimen "
                     "addition (Tier 2, urine-scoped in Ed36) = Nitrofurantoin, "
                     "Ciprofloxacin, Levofloxacin.",
        "source": "CLSI_M100", "locus": "M100 36th ed. (2026) table — Enterococcus spp.",
        "verified": "secondary", "checked_by": _AI, "checked_on": "2026-08-21",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-22",
        "note": "Vancomycin confirmed Ed36 Tier 2 (not Tier 1) -- kept in this module's 'primary' anyway as a deliberate Orange Lab curation choice given VRE screening's clinical importance; flagged so the gap between the citation and the code's severity choice is visible, not hidden. High-level aminoglycoside screening (HLAR, 'Gentamicin 120 ug') is confirmed by Ed36 as its own distinct Tier-2 entry, separate from routine gentamicin -- still deliberately excluded here because this codebase's sir_map has no drug-name key distinct from the routine 10 ug disk that a false 'satisfied' match could be built on; see ast_reportability.py's intr_strep_enterococcus_aminoglycosides rule for the full HLAR reasoning. Documented here as a candidate future addition, not silently dropped.",
    },
    "panel_strep_pneumoniae": {
        "assertion": "Expected AST panel for Streptococcus pneumoniae: primary = "
                     "Penicillin, Ceftriaxone, Erythromycin; supplemental = "
                     "Clindamycin, Trimethoprim/Sulfamethoxazole, Levofloxacin, "
                     "Vancomycin.",
        "source": "CLSI_M100", "locus": "M100 Ed36 Table 1G — Streptococcus pneumoniae",
        "verified": "pending", "checked_by": _AI, "checked_on": "2026-08-20",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-22",
    },
    "panel_beta_hemolytic_strep": {
        "assertion": "Expected AST panel for beta-haemolytic Streptococcus (Group "
                     "A/B): primary = Penicillin, Clindamycin, Erythromycin; "
                     "supplemental = Vancomycin.",
        "source": "CLSI_M100", "locus": "M100 Ed36 Table 1F — beta-haemolytic streptococci",
        "verified": "pending", "checked_by": _AI, "checked_on": "2026-08-20",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-22",
        "note": "Penicillin resistance has never been reported in GAS/GBS; it stays on the panel because CLSI still lists it as test-and-report, and because the erythromycin/clindamycin pair exists for the penicillin-allergic pathway, not as a fallback for penicillin failure.",
    },
    "panel_haemophilus": {
        "assertion": "Expected AST panel for Haemophilus influenzae: primary = "
                     "Ampicillin, Ceftriaxone; supplemental = Amoxicillin+"
                     "Clavulanic acid, Azithromycin, Trimethoprim/Sulfamethoxazole.",
        "source": "CLSI_M100", "locus": "M100 Ed36 Table 1D — Haemophilus spp.",
        "verified": "pending", "checked_by": _AI, "checked_on": "2026-08-20",
        "countersigned_by": "Dr. Tarek El-Shafei, Laboratory Director — 2026-08-22",
    },
}

# ── Citation strings the engine must NOT use in free text ────────────────────
# Each maps an ambiguous or incorrect string to the row that replaces it. The
# test greps the codebase for these and reports every remaining occurrence.
DEPRECATED_CITATIONS: Dict[str, str] = {
    "IDSA AMR 2025":
        "IDSA_AMR is v4.0, published in Clin Infect Dis on 2024-08-07 (ciae403). "
        "There is no 2025 edition — use 'IDSA AMR Guidance 2026 update (supersedes v4.0 2024)'.",
    "IDSA 2025":
        "Ambiguous. Name the specific IDSA document and its year.",
    "EUCAST 2026":
        "Ambiguous — EUCAST publishes several documents. Use 'EUCAST Breakpoint "
        "Tables v16.1 (2026)' or 'EUCAST Intrinsic Resistance v3.3 (2021)'.",
    "CLSI M100 2026":
        "Use the edition, not the year: 'CLSI M100 Ed36'.",
    "EUCAST Expert Rules v3.3":
        "v3.3 is the Intrinsic Resistance and Unusual Phenotypes document, not the "
        "Expert Rules. Use 'EUCAST Intrinsic Resistance v3.3' for intrinsic claims "
        "and 'EUCAST Expert Rules v3.1 (2016)' for interpretive/hierarchy rules.",
}


def source_for(rule_id: str) -> Dict[str, str]:
    """Full citation for a rule id, or {} if the rule is unregistered."""
    row = RULES.get(rule_id)
    if not row:
        return {}
    src = SOURCES.get(row.get("source", ""), {})
    return {**src, "locus": row.get("locus", ""), "assertion": row.get("assertion", "")}


def citation_line(rule_id: str) -> str:
    """One-line human citation, e.g. for a PDF footer."""
    s = source_for(rule_id)
    if not s:
        return ""
    bits = [s.get("title", ""), s.get("version", ""), s.get("locus", "")]
    return " · ".join(b for b in bits if b)
