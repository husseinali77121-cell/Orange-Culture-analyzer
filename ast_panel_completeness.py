# © 2025 Dr. Hussein Ali — Orange Lab, 6 October City, Egypt
# AST Panel Completeness QC — Independent Module
# Unauthorized copying or distribution is prohibited.
"""Orange Lab — AST Panel Completeness QC.

Every check in ast_qa_engine.py and ast_reportability.py answers some version
of "was what got tested interpreted correctly?". None of them can answer a
different, earlier question:

    "Was enough tested at all?"

A panel that skipped an expected agent doesn't look wrong — it looks clean,
because there is nothing on it to contradict. That is exactly why it needs its
own pass rather than another rule bolted onto the contradiction checks: a
missing drug produces silence everywhere else in the pipeline.

WHAT THIS MODULE DOES NOT DO
Two things stay explicitly out of scope, on purpose:

  1. It does not decide treatment. "Panel adequate" and "what should this
     patient receive" are different questions with different owners
     (organism_profile.py / the Clinical Decision Engine answers the second).
     Mixing them means an incomplete panel gets silently reinterpreted by the
     recommendation engine as "no options" instead of "we don't know yet".

  2. It does not guess. Where this module has no organism-group entry, it
     returns status="not_evaluated" — not a clean bill of health, not a
     flagged panel. Every organism handled here is chosen because a routine
     panel for it is genuinely well established (CLSI M100 Table 1 series);
     atypicals with no standard AST convention (Legionella, Mycoplasma),
     organisms where routine panel testing is not standard laboratory
     practice (anaerobes, Campylobacter), and any organism string this module
     cannot confidently place in a group, are left silent rather than forced
     into a guess. ast_reportability.py states the same rule for the same
     reason: a false "this panel is incomplete" alert costs a QA engine
     credibility it cannot afford to spend.

THREE TIERS, NOT A FLAT MISSING LIST
  HIGH           A routine agent for this organism group is absent from the
                 panel entirely — the kind of agent a general lab tests and
                 reports on every isolate of this kind.
  INFORMATIONAL  A supplemental/selective agent is absent — useful, often
                 reflex-tested on resistance or by specimen site, but not
                 expected on every isolate.
  CRITICAL       Not a property of one drug — computed AFTER the HIGH/
                 INFORMATIONAL comparison. If every HIGH-tier agent that WAS
                 tested came back non-susceptible, and a HIGH-tier agent that
                 might have resolved therapy was never tested, the panel
                 cannot be safely read as "no options" — it can only be read
                 as "incomplete". That is a therapeutic-safety fact, not a
                 completeness footnote, so it gets its own severity rather
                 than sharing HIGH with an ordinary gap.

GUIDELINE STATUS — READ BEFORE TRUSTING THIS FILE
Six of the ten groups below (Enterobacterales, Salmonella/Shigella, Pseudomonas,
Acinetobacter, Staphylococcus, Enterococcus) are grounded in the actual CLSI
M100 36th-edition (2026) Table 1 tier assignments — the same edition this
codebase already cites everywhere else — via a secondary tabulation (Giri D.,
LaboratoryTests.org, Feb-Mar 2026, itself citing CLSI M100 36th ed. 2026
directly per organism). Each such row is marked verified="secondary" in
guideline_registry.py, and Dr. Tarek countersigned all six on 2026-08-22
(see countersigned_by on each row). The remaining four (Stenotrophomonas,
S. pneumoniae, beta-haemolytic Streptococcus, H. influenzae) are still a
clinically-reasoned DRAFT, informed by CLSI M100 Table 1 conventions but not
independently re-verified against Ed36 or reviewed by him yet — marked
verified="pending", unsigned.

"Grounded" does not mean "every CLSI-eligible agent is listed as primary".
CLSI's Tier 1 lists what is APPROPRIATE for routine testing and reporting —
it is not a mandate that every lab test every Tier-1 agent for every isolate,
and several Tier-1 agents are class-mates a lab picks ONE of (e.g. CLSI lists
both ciprofloxacin and levofloxacin as Tier 1 for several organisms; a lab
reasonably tests one fluoroquinolone, not both). Treating the full Tier-1 list
as "expected, flag if absent" would manufacture exactly the alert fatigue this
module exists to avoid. So: "primary" below is a curated, clinically-standard
ROUTINE panel drawn only from agents CLSI recognizes as Tier-1/routine-
appropriate for that organism; "supplemental" carries the rest of what CLSI
recognizes as appropriate (remaining Tier-1 alternates plus Tier 2+) so
nothing eligible is left unaddressed, just not flagged at HIGH severity for
an ordinary lab's ordinary panel. This curation choice was Orange Lab's own,
same as organism_profile.py's treatment-line lists — Dr. Tarek's sign-off on
the six countersigned rows covers this curation choice too, not just the
underlying CLSI tier data.

Two concrete, dated facts drove earlier design choices and are worth stating
plainly rather than re-deriving from memory each time:
  * CLSI M100 replaced its Group A/B/C/U reporting scheme with a Tier 1-4
    scheme starting with the 33rd edition (2023) — this file's "primary"/
    "supplemental" are Orange Lab's own labels, not a claim about which
    numbered CLSI tier an agent sits in (see each group's citation for that).
  * Tier placement has MOVED between editions for specific agents — e.g.
    meropenem in Acinetobacter was Category-A as of the 2022 tables and is
    Tier-2 (not Tier-1/routine) as of Ed36 — confirmed directly against the
    Ed36 tabulation, not assumed from an older edition's convention.
Every group is registered in guideline_registry.RULES. See its module
docstring for what "secondary" vs "pending" verified status means. The four
still-pending rows raise the exact same "worth a look, not an accusation"
caveat as before — they just haven't reached him yet.

Architecture:
  OCR → AST parsing → AST-QA (contradictions) → [PANEL COMPLETENESS]
    → Clinical Decision Engine → Safety Gate → Final Recommendation
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_NORM = re.compile(r"[^a-z0-9]")


def _nk(s: str) -> str:
    """Normalize a drug name for matching: lowercase, alphanumerics only.

    Same normalization ast_reportability.py uses internally, kept local
    rather than imported so this module has zero dependency on the private
    surface of another module — only ENTEROBACTERALES (a plain public
    constant) is imported from it, below.
    """
    return _NORM.sub("", (s or "").lower())


# ── Organism family reused from ast_reportability.py ────────────────────────
# Genus tokens only — Salmonella/Shigella are matched by their OWN group
# first (see GROUPS ordering) because CLSI restricts what gets reported for
# them (ampicillin-only beta-lactam reporting; azithromycin scoped to
# S. Typhi/Shigella) in a way the general Enterobacterales panel does not.
try:
    from ast_reportability import ENTEROBACTERALES as _ENTERO_GENERA
except Exception:                            # standalone use without the module
    _ENTERO_GENERA = [
        "escherichia", "e. coli", "e.coli", "klebsiella", "enterobacter",
        "citrobacter", "serratia", "proteus", "morganella", "providencia",
        "hafnia", "pantoea", "raoultella", "yersinia", "cronobacter",
        "edwardsiella", "kluyvera", "leclercia",
    ]

# ── Intrinsic-resistance guard ───────────────────────────────────────────────
# A flat, one-size-fits-all "Enterobacterales panel" is wrong in a specific,
# testable way: intrinsic resistance varies BY GENUS within that order (e.g.
# Klebsiella is chromosomally ampicillin-resistant genus-wide; Proteus
# mirabilis/vulgaris and Morganella are intrinsically resistant to
# nitrofurantoin; Providencia additionally to gentamicin). Hand-listing every
# genus exception here would duplicate a table this codebase already
# maintains as the single source of truth and — per this repo's own history —
# duplicated tables are exactly how the two halves of a system end up
# disagreeing. So: filter the expected panel against the SAME canonical table
# ast_qa_engine.py's intrinsic-resistance check already uses, at check time,
# for whichever specific organism string was actually reported. This is what
# test_panel_completeness.py's cross-module safety check enforces.
try:
    from clinical_data import INTRINSIC_RESISTANCE as _CANONICAL_INTRINSIC
except Exception:
    _CANONICAL_INTRINSIC = {}


def _intrinsically_resistant_drugs(organism: str) -> set:
    """Same substring-match convention as ast_qa_engine._check_intrinsic_resistance."""
    org_l = (organism or "").lower().strip()
    if not org_l:
        return set()
    out: set = set()
    for k, lst in _CANONICAL_INTRINSIC.items():
        if k and (k in org_l or org_l in k):
            out.update(lst)
    return out


# ── Expected-panel groups ────────────────────────────────────────────────────
# Order matters: the FIRST group whose `match` tokens hit the (lowercased)
# organism string wins. Put the more specific group before the general one it
# would otherwise be swallowed by (Salmonella/Shigella before Enterobacterales).
GROUPS: List[Dict[str, Any]] = [
    {
        # GROUNDED — CLSI M100 Ed36 (2026), Salmonella/Shigella table, verified
        # secondary (LaboratoryTests.org tabulation of the Ed36 table, Mar 2026).
        "id": "panel_salmonella_shigella",
        "label": "Salmonella / Shigella spp.",
        "match": ["salmonella", "shigella"],
        "primary": ["Ampicillin", "Trimethoprim/Sulfamethoxazole",
                    "Ciprofloxacin", "Ceftriaxone"],
        "supplemental": ["Azithromycin"],
        # Deliberately excludes 1st/2nd-gen cephalosporins and cephamycins:
        # Ed36 explicitly notes these "may appear active in vitro but are not
        # effective clinically and should not be reported as susceptible" for
        # Salmonella/Shigella specifically.
        "reference": ("CLSI M100 36th ed. (2026), Salmonella/Shigella table "
                      "(Orange Lab curation, verified against Ed36 tier data)"),
    },
    {
        # GROUNDED — CLSI M100 Ed36 (2026) Table 1A, verified secondary.
        # Tier 1 for this table is actually much broader than "primary" below
        # (it also lists amoxicillin-clavulanate, ampicillin-sulbactam,
        # cefotaxime, levofloxacin as Tier 1) — trimmed to a non-redundant
        # routine set per the module docstring's curation policy; the rest
        # live in "supplemental" below, not dropped.
        "id": "panel_enterobacterales",
        "label": "Enterobacterales",
        "match": list(_ENTERO_GENERA) + ["enterobacterales"],
        "primary": ["Ampicillin", "Ceftriaxone", "Gentamicin",
                    "Ciprofloxacin", "Trimethoprim/Sulfamethoxazole",
                    "Piperacillin + Tazobactam"],
        "supplemental": ["Amoxicillin + Clavulanic acid", "Ampicillin/Sulbactam",
                          "Cefotaxime", "Levofloxacin", "Amikacin", "Cefoxitin",
                          "Cefepime", "Cefuroxime", "Ertapenem",
                          "Imipenem/Cilastatin", "Meropenem", "Tetracycline",
                          "Tobramycin"],
        # Cefazolin and Nitrofurantoin are Tier 1 in Ed36 but explicitly scoped
        # "Urine only" in the table itself — kept out of the general list.
        "specimen_supplemental": {"Urine": ["Nitrofurantoin", "Fosfomycin",
                                             "Cefazolin"]},
        "reference": ("CLSI M100 36th ed. (2026) Table 1A — Enterobacterales "
                       "(Orange Lab curation, verified against Ed36 tier data)"),
    },
    {
        # GROUNDED — CLSI M100 Ed36 (2026) Table 1B-1, verified secondary.
        "id": "panel_pseudomonas",
        "label": "Pseudomonas aeruginosa",
        "match": ["pseudomonas"],
        "primary": ["Cefepime", "Ceftazidime", "Ciprofloxacin",
                    "Piperacillin + Tazobactam", "Tobramycin"],
        "supplemental": ["Levofloxacin", "Amikacin", "Imipenem/Cilastatin",
                          "Meropenem", "Aztreonam", "Colistin", "Cefiderocol",
                          "Ceftazidime + Avibactam", "Ceftolozane + Tazobactam"],
        "reference": ("CLSI M100 36th ed. (2026) Table 1B-1 — Pseudomonas "
                       "aeruginosa (Orange Lab curation, verified against "
                       "Ed36 tier data)"),
    },
    {
        # GROUNDED — CLSI M100 Ed36 (2026) Table 1B-2, verified secondary.
        # Confirms, against the actual Ed36 tabulation rather than an older
        # edition's convention: cefepime/ceftazidime/ciprofloxacin/gentamicin
        # are Tier 1 (routine) for Acinetobacter, while meropenem, imipenem,
        # and piperacillin-tazobactam are Tier 2 — a real change from the
        # pre-2023 Category-A/B scheme this module's first draft assumed.
        # Cefotaxime/ceftriaxone are Tier 4 (on request) for this organism —
        # confirms they were correctly excluded from both tiers here.
        "id": "panel_acinetobacter",
        "label": "Acinetobacter baumannii",
        "match": ["acinetobacter"],
        "primary": ["Ampicillin/Sulbactam", "Cefepime", "Ceftazidime",
                    "Ciprofloxacin", "Gentamicin"],
        "supplemental": ["Levofloxacin", "Tobramycin", "Amikacin",
                          "Imipenem/Cilastatin", "Meropenem", "Minocycline",
                          "Piperacillin + Tazobactam",
                          "Trimethoprim/Sulfamethoxazole", "Colistin"],
        "reference": ("CLSI M100 36th ed. (2026) Table 1B-2 — Acinetobacter "
                       "spp. (Orange Lab curation, verified against Ed36 tier "
                       "data — corrects this module's original draft, which "
                       "had assumed a pre-2023 Category-A/B convention)"),
    },
    {
        "id": "panel_stenotrophomonas",
        "label": "Stenotrophomonas maltophilia",
        "match": ["stenotrophomonas"],
        # Minocycline confirmed Tier 1 (not supplemental) directly from CLSI's
        # own published "AST News Update" worked example: "Your panel for
        # Stenotrophomonas maltophilia does not include minocycline, but
        # minocycline is in Tier 1" — this module's original draft had it
        # supplemental; corrected here on a primary-source citation.
        # List stays narrow on purpose: Stenotrophomonas is intrinsically
        # resistant to carbapenems and most beta-lactams/aminoglycosides (see
        # clinical_data.INTRINSIC_RESISTANCE) — nothing here may be added to
        # without checking that table first.
        "primary": ["Trimethoprim/Sulfamethoxazole", "Levofloxacin",
                    "Minocycline"],
        "supplemental": [],
        "reference": ("CLSI M100 Ed36 Table 1B — Stenotrophomonas maltophilia "
                       "(Orange Lab draft; minocycline tier corrected via "
                       "CLSI's own 2024 AST News Update worked example — "
                       "still pending full Ed36 re-verification)"),
    },
    {
        # GROUNDED — CLSI M100 Ed36 (2026) table, verified secondary.
        # Tier 1 for this table lists eleven agents including all three
        # macrolides (azithromycin/clarithromycin/erythromycin) and both
        # tetracyclines (doxycycline/minocycline/tetracycline) as separately
        # eligible — trimmed to one representative per redundant class for
        # "primary" per the module docstring's curation policy; the rest are
        # "supplemental", still CLSI-Tier-1-eligible, not lower quality.
        # Vancomycin confirmed Tier 1 here — this module's original draft had
        # it supplemental; corrected.
        "id": "panel_staphylococcus",
        "label": "Staphylococcus spp.",
        "match": ["staphylococcus", "staph", "mrsa", "mrse"],
        # Cefoxitin/Oxacillin both kept regardless of organism name — this
        # checks whether the mecA screen was RUN, not what it showed. An
        # MRSA-named isolate is still expected to carry the pair that
        # established the call.
        "primary": ["Cefoxitin", "Clindamycin", "Erythromycin",
                    "Trimethoprim/Sulfamethoxazole", "Vancomycin",
                    "Doxycycline"],
        "supplemental": ["Oxacillin", "Azithromycin", "Clarithromycin",
                          "Minocycline", "Tetracycline", "Linezolid",
                          "Penicillin", "Ceftaroline", "Ciprofloxacin",
                          "Gentamicin", "Levofloxacin"],
        # "Rifampicin" deliberately excluded even though it's a real CLSI-
        # eligible agent for this organism: it is absent from
        # ocr_parsing.ABX_ALIAS_INDEX (no full-name alias) and its disk-code
        # fallback ("RD"/"RA") only fires when a line names no drug in full —
        # a report that spells "Rifampicin" out would never be recognized as
        # tested. Adding it here would create a permanent false "missing"
        # flag no matter what the lab actually did. Caught by this module's
        # own audit; documented rather than silently worked around.
        "specimen_supplemental": {"Urine": ["Nitrofurantoin"]},
        "reference": ("CLSI M100 36th ed. (2026) Table — Staphylococcus "
                       "aureus (Orange Lab curation, verified against Ed36 "
                       "tier data)"),
    },
    {
        # GROUNDED — CLSI M100 Ed36 (2026) table, verified secondary.
        # High-level aminoglycoside screening (HLAR, "Gentamicin 120 ug") is
        # confirmed by Ed36 as its own distinct Tier-2 entry, separate from
        # routine Gentamicin susceptibility — this module still does NOT add
        # it, because this codebase's sir_map has no drug-name key distinct
        # from the routine 10 ug disk that a false "satisfied" match could be
        # built on. Flagging this as a documented future addition rather than
        # guessing a key name is the same discipline ast_reportability.py's
        # intr_strep_enterococcus_aminoglycosides rule already applies.
        "id": "panel_enterococcus",
        "label": "Enterococcus spp.",
        "match": ["enterococc", "vre"],
        "primary": ["Ampicillin", "Penicillin", "Vancomycin"],
        "supplemental": ["Linezolid", "Daptomycin", "Teicoplanin"],
        # Ciprofloxacin/Levofloxacin are Ed36 Tier 2 for Enterococcus but
        # explicitly scoped "Urine only" in the table.
        "specimen_supplemental": {"Urine": ["Nitrofurantoin", "Ciprofloxacin",
                                             "Levofloxacin"]},
        "reference": ("CLSI M100 36th ed. (2026) Table — Enterococcus spp. "
                       "(Orange Lab curation, verified against Ed36 tier "
                       "data)"),
    },
    {
        "id": "panel_strep_pneumoniae",
        "label": "Streptococcus pneumoniae",
        "match": ["streptococcus pneumoniae", "s. pneumoniae", "pneumococc"],
        "primary": ["Penicillin", "Ceftriaxone", "Erythromycin"],
        "supplemental": ["Clindamycin", "Trimethoprim/Sulfamethoxazole",
                          "Levofloxacin", "Vancomycin"],
        "reference": ("CLSI M100 Ed36 Table 1G — Streptococcus pneumoniae "
                       "(Orange Lab draft, pending review)"),
    },
    {
        "id": "panel_beta_hemolytic_strep",
        "label": "Beta-haemolytic Streptococcus (Group A/B)",
        "match": ["streptococcus pyogenes", "streptococcus agalactiae"],
        # Penicillin resistance has never been reported in GAS/GBS, but CLSI
        # still lists it as the agent to test and report — the erythromycin/
        # clindamycin pair exists specifically for penicillin-allergic
        # patients, not as an alternative because penicillin might fail.
        "primary": ["Penicillin", "Clindamycin", "Erythromycin"],
        "supplemental": ["Vancomycin"],
        "reference": ("CLSI M100 Ed36 Table 1F — beta-haemolytic streptococci "
                       "(Orange Lab draft, pending review)"),
    },
    {
        "id": "panel_haemophilus",
        "label": "Haemophilus influenzae",
        "match": ["haemophilus", "h. influenzae"],
        "primary": ["Ampicillin", "Ceftriaxone"],
        "supplemental": ["Amoxicillin + Clavulanic acid", "Azithromycin",
                          "Trimethoprim/Sulfamethoxazole"],
        "reference": ("CLSI M100 Ed36 Table 1D — Haemophilus spp. "
                       "(Orange Lab draft, pending review)"),
    },
]

_GROUPS_BY_ID: Dict[str, Dict[str, Any]] = {g["id"]: g for g in GROUPS}

# ── Explicit per-organism mapping ────────────────────────────────────────────
# Every organism string actually selectable in this app's dropdown
# (organism_profile.ORGANISM_PROFILE, 30 entries as of 2026-08-22), each named
# explicitly rather than left to substring "family" matching alone. Requested
# 2026-08-22 for auditability: Dr. Tarek (or anyone) can read this list and
# see exactly which panel every real organism resolves to, without having to
# trace genus-token substring logic to convince themselves a given name
# actually matches. The five organisms mapped to None are DELIBERATE, not
# omissions -- see each GROUPS entry's docstring on why routine AST panel
# testing does not have an established convention for them (Anaerobes,
# Campylobacter, Legionella, Listeria, Mycoplasma): silence over a guess.
#
# The underlying panel DATA (primary/supplemental drug lists, citations,
# Dr. Tarek's countersignatures) is unchanged by this -- this is a naming
# layer on top of the same six Ed36-grounded + four pending groups, not a
# second copy of the clinical content. A future organism added to
# organism_profile.py without a matching line here still falls through to
# the substring fallback below (see test_panel_completeness.py's coverage
# check), so nothing silently goes unevaluated by omission from this table.
ORGANISM_NAMES: Dict[str, Optional[str]] = {
    "Acinetobacter baumannii": "panel_acinetobacter",
    "Anaerobes (لاهوائيات)": None,
    "Campylobacter jejuni": None,
    "Citrobacter freundii": "panel_enterobacterales",
    "Coagulase-negative Staphylococci": "panel_staphylococcus",
    "E. coli": "panel_enterobacterales",
    "Enterobacter cloacae": "panel_enterobacterales",
    "Enterobacterales (unspeciated)": "panel_enterobacterales",
    "Enterococcus faecalis": "panel_enterococcus",
    "Enterococcus faecium": "panel_enterococcus",
    "H. influenzae": "panel_haemophilus",
    "Hafnia alvei": "panel_enterobacterales",
    "Klebsiella spp.": "panel_enterobacterales",
    "Legionella pneumophila": None,
    "Listeria monocytogenes": None,
    "MRSA": "panel_staphylococcus",
    "Morganella morganii": "panel_enterobacterales",
    "Mycoplasma spp.": None,
    "Proteus mirabilis": "panel_enterobacterales",
    "Providencia spp.": "panel_enterobacterales",
    "Pseudomonas aeruginosa": "panel_pseudomonas",
    "Salmonella spp.": "panel_salmonella_shigella",
    "Serratia marcescens": "panel_enterobacterales",
    "Shigella spp.": "panel_salmonella_shigella",
    "Staphylococcus aureus": "panel_staphylococcus",
    "Stenotrophomonas maltophilia": "panel_stenotrophomonas",
    "Streptococcus agalactiae (Group B)": "panel_beta_hemolytic_strep",
    "Streptococcus pneumoniae": "panel_strep_pneumoniae",
    "Streptococcus pyogenes (Group A)": "panel_beta_hemolytic_strep",
    "VRE": "panel_enterococcus",
}


def _match_group(organism: str) -> Optional[Dict[str, Any]]:
    org_raw = (organism or "").strip()
    if not org_raw:
        return None

    # Primary path: exact name, as it would appear from the organism
    # dropdown. Covers every organism this app can actually select.
    if org_raw in ORGANISM_NAMES:
        gid = ORGANISM_NAMES[org_raw]
        return _GROUPS_BY_ID[gid] if gid else None

    # Fallback: substring "family" matching, for organism text that never
    # went through the dropdown (free-text OCR extraction, or a name added
    # to organism_profile.py that hasn't been added to ORGANISM_NAMES above
    # yet). Kept deliberately narrow -- see each GROUPS entry's own `match`
    # tokens -- rather than removed, so a real but unlisted organism name
    # still gets evaluated instead of silently falling through.
    org_l = org_raw.lower()
    for g in GROUPS:
        if any(tok in org_l for tok in g["match"]):
            return g
    return None


# ── Result container ─────────────────────────────────────────────────────────
@dataclass
class PanelCompletenessResult:
    status: str                                    # not_evaluated | adequate | incomplete | critical
    organism_group: str = ""
    rule_id: str = ""
    expected_total: int = 0
    tested_count: int = 0
    missing_primary: List[str] = field(default_factory=list)
    missing_supplemental: List[str] = field(default_factory=list)
    issues: List[Dict[str, Any]] = field(default_factory=list)  # ready for QAIssue conversion


def check_panel_completeness(
    organism: str, specimen: str, sir_map: Dict[str, str]
) -> PanelCompletenessResult:
    """Compare the tested panel against the expected panel for this organism.

    Returns status="not_evaluated" (never "adequate") for any organism this
    module has no group for — see the module docstring on why that distinction
    matters. Missing-agent status is based on whether the drug is a KEY in
    sir_map at all, not its S/I/R value: an untested drug and a drug tested R
    are different facts, and only the first one is this module's concern.
    """
    if not sir_map:
        return PanelCompletenessResult(status="not_evaluated")

    group = _match_group(organism)
    if group is None:
        return PanelCompletenessResult(status="not_evaluated")

    tested_norm: Dict[str, tuple] = {_nk(k): (k, v) for k, v in (sir_map or {}).items()}

    # Drop anything intrinsically resistant for THIS specific reported
    # organism before it can ever be called "expected" — see the guard's
    # docstring above for why this is a lookup against the shared table
    # rather than a hand-maintained per-genus exception list.
    _banned = _intrinsically_resistant_drugs(organism)

    primary = [d for d in group.get("primary", []) if d not in _banned]
    supplemental = [d for d in group.get("supplemental", []) if d not in _banned]
    supplemental += [d for d in group.get("specimen_supplemental", {}).get(specimen, [])
                      if d not in _banned]
    # de-dup, preserve order (a specimen addition might repeat a base entry)
    _seen: set = set()
    supplemental = [d for d in supplemental if not (d in _seen or _seen.add(d))]

    missing_primary = [d for d in primary if _nk(d) not in tested_norm]
    missing_supplemental = [d for d in supplemental if _nk(d) not in tested_norm]

    expected_total = len(primary) + len(supplemental)
    tested_count = expected_total - len(missing_primary) - len(missing_supplemental)

    ref = group.get("reference", "")
    issues: List[Dict[str, Any]] = []

    for d in missing_primary:
        issues.append({
            "severity": "HIGH",
            "drug": d,
            "message": f"Expected AST agent missing: {d}",
            "detail": (
                f"{d} is on the routine expected panel for {group['label']} but was "
                f"not tested on this isolate. Review panel completeness before final "
                f"validation."
            ),
            "reference": ref,
        })
    for d in missing_supplemental:
        issues.append({
            "severity": "LOW",
            "drug": d,
            "message": f"Supplemental AST agent not tested: {d}",
            "detail": (
                f"{d} is a supplemental/selective agent for {group['label']} — useful "
                f"in specific scenarios (resistance to a primary agent, specimen site, "
                f"stewardship review) but not expected on every isolate."
            ),
            "reference": ref,
        })

    status = "adequate" if not (missing_primary or missing_supplemental) else "incomplete"

    # ── Escalation: can the primary tier even be safely read? ───────────────
    # Only fires when at least one primary agent WAS tested (so there is an
    # actual resistance signal, not just an empty panel) AND every primary
    # agent that was tested is non-susceptible AND at least one primary agent
    # was never tested (so an option may exist that this panel cannot see).
    tested_primary = [(d, tested_norm[_nk(d)][1]) for d in primary if _nk(d) in tested_norm]
    if tested_primary and missing_primary and all(v == "R" for _, v in tested_primary):
        status = "critical"
        issues.append({
            "severity": "CRITICAL",
            "drug": ", ".join(missing_primary),
            "message": "Incomplete AST panel blocks reliable therapeutic interpretation",
            "detail": (
                f"Every primary agent tested for {group['label']} on this isolate came "
                f"back Resistant, and {len(missing_primary)} expected primary agent(s) "
                f"were never tested ({', '.join(missing_primary)}). A therapeutic option "
                f"may exist among the untested agents — this panel cannot rule that out. "
                f"Do not report 'no susceptible options' from an incomplete panel; "
                f"request add-on testing first."
            ),
            "reference": ref,
        })

    return PanelCompletenessResult(
        status=status,
        organism_group=group["label"],
        rule_id=group["id"],
        expected_total=expected_total,
        tested_count=tested_count,
        missing_primary=missing_primary,
        missing_supplemental=missing_supplemental,
        issues=issues,
    )


__all__ = ["GROUPS", "ORGANISM_NAMES", "PanelCompletenessResult", "check_panel_completeness"]
