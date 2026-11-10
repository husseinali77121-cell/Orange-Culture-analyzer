# -*- coding: utf-8 -*-
# © 2025 Dr / Hussein Ali — Orange Lab, 6 October City, Egypt
# Microbiology CDSS — All Rights Reserved
"""therapy_rules.py — treatment rules added by the 2026-11-10 guideline review.

WHY A SEPARATE MODULE
---------------------
analyze_antibiotics() and predict_esbl() are lifted out of streamlit_app.py by
name and exec'd in a bare namespace by the AST-extraction test harnesses. A
helper defined at module level in the monolith is invisible there, so every
helper these functions need is imported INSIDE them from this module -- the
same pattern clinical_utils.py already uses.

WHAT IS HERE
------------
* Novel beta-lactam / BLI agents judged by their OWN activity against the
  organism and, for Enterobacterales, against the carbapenemase CLASS.
  DEFECT this closes: on a confirmed carbapenemase the engine banned
  ceftazidime-avibactam (as a "BLI combination, MERINO"), meropenem-
  vaborbactam and imipenem-relebactam (as "carbapenems") and cefiderocol (as
  a "cephalosporin") -- the four agents that exist FOR that isolate.
  Source: IDSA AMR Guidance 2026 (Tamma et al., Clin Infect Dis 2026).
* Carbapenemase-type normalisation (KPC / OXA-48 / MBL).
* Allergy profile.
* Proteeae imipenem rule (CDC CRE definition; EUCAST expected phenotypes).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "CLINICAL_NOTE_REASONS", "NOVEL_BL_AGENTS", "CARBAPENEMASE_TYPE_OPTIONS",
    "normalize_carbapenemase_type", "NOVEL_ACTIVITY", "RESERVE_NOTE",
    "novel_agent_verdict", "carb_tx_text", "allergy_profile",
    "PROTEEAE_TOKENS", "is_proteeae", "UTI_SYNDROME_OPTIONS", "resolve_uti_syndrome",
]

# Proteeae (Proteus, Morganella, Providencia) have intrinsically elevated
# imipenem MICs (EUCAST Expected Resistant Phenotypes; CDC CRE definition:
# for these genera resistance to a carbapenem OTHER THAN imipenem is
# required). An imipenem R alone is therefore not a CRE/carbapenemase marker.
PROTEEAE_TOKENS = ("proteus", "morganella", "providencia")


def is_proteeae(organism: Optional[str]) -> bool:
    o = (organism or "").lower()
    return any(t in o for t in PROTEEAE_TOKENS)


UTI_SYNDROME_OPTIONS = ("تلقائي (من الأعراض)", "التهاب مثانة (سفلي)",
                        "التهاب حويضة / cUTI / إنتان بولي")


def resolve_uti_syndrome(choice: Optional[str], symptoms: Optional[List[str]] = None) -> Optional[str]:
    """'upper' | 'lower' | None from the UI choice and the symptom checklist.

    Auto mode infers 'upper' from fever or flank/loin pain (IDSA cUTI 2025
    defines cUTI/pyelonephritis by systemic or upper-tract signs).
    """
    c = str(choice or "")
    if "حويضة" in c or "upper" in c.lower() or "cuti" in c.lower():
        return "upper"
    if "مثانة" in c or "lower" in c.lower() or "cystitis" in c.lower():
        return "lower"
    sym = " | ".join(str(x).lower() for x in (symptoms or []))
    if any(k in sym for k in ("fever", "flank", "loin", "حمى", "خاصرة", "rigors")):
        return "upper"
    return None


CLINICAL_NOTE_REASONS = frozenset({
    "novel_agent", "organism_caution", "allergy", "uti_upper",
    "aminoglycoside_pseudomonas", "colistin", "penicillinase_unconfirmed",
    "no_breakpoint", "ampc_sdd", "ampc_cefepime",
})

NOVEL_BL_AGENTS = frozenset({
    "Ceftazidime + Avibactam", "Meropenem + Vaborbactam",
    "Imipenem + Relebactam", "Cefiderocol", "Ceftolozane + Tazobactam",
    "Aztreonam + Avibactam", "Sulbactam + Durlobactam",
})

CARBAPENEMASE_TYPE_OPTIONS = ("غير معروف / لم يُختبر", "KPC", "OXA-48-like",
                              "NDM / VIM / IMP (MBL)")


def normalize_carbapenemase_type(value: Any) -> Optional[str]:
    """KPC | OXA-48 | MBL | None. Anything unrecognised is None (unknown)."""
    t = str(value or "").strip().lower()
    if not t:
        return None
    if any(k in t for k in ("ndm", "vim", "mbl", "metallo")) or re.search(r"\bimp\b", t):
        return "MBL"
    if "oxa" in t:
        return "OXA-48"
    if "kpc" in t:
        return "KPC"
    return None


# Activity of each novel agent against each carbapenemase class in
# Enterobacterales. (level, note). IDSA AMR Guidance 2026.
NOVEL_ACTIVITY: Dict[str, Dict[str, Tuple[str, str]]] = {
    "KPC": {
        "Ceftazidime + Avibactam": ("allow", "KPC: خيار مفضّل (IDSA 2026)."),
        "Meropenem + Vaborbactam": ("allow", "KPC: خيار مفضّل (IDSA 2026)."),
        "Imipenem + Relebactam": ("allow", "KPC: خيار مفضّل (IDSA 2026)."),
        "Cefiderocol": ("warn", "KPC: بديل عند تعذّر الخيارات المفضّلة (IDSA 2026)."),
        "Aztreonam + Avibactam": ("warn", "KPC: فعّال، لكن يُحتفظ به لمنتجات MBL."),
    },
    "OXA-48": {
        "Ceftazidime + Avibactam": ("allow", "OXA-48: الخيار المفضّل (IDSA 2026)."),
        "Meropenem + Vaborbactam": ("ban", "Vaborbactam لا يثبّط OXA-48 — غير فعّال مهما كانت النتيجة."),
        "Imipenem + Relebactam": ("ban", "Relebactam لا يثبّط OXA-48 — غير فعّال مهما كانت النتيجة."),
        "Cefiderocol": ("warn", "OXA-48: بديل (IDSA 2026)."),
        "Aztreonam + Avibactam": ("warn", "OXA-48: فعّال، لكن يُحتفظ به لمنتجات MBL."),
    },
    "MBL": {
        "Ceftazidime + Avibactam": ("warn", "MBL يحلّل Ceftazidime-avibactam: منفرداً غير فعّال — "
                                            "يُستخدم فقط مع Aztreonam (CZA + ATM)."),
        "Meropenem + Vaborbactam": ("ban", "Vaborbactam لا يثبّط MBL (NDM/VIM/IMP) — غير فعّال."),
        "Imipenem + Relebactam": ("ban", "Relebactam لا يثبّط MBL (NDM/VIM/IMP) — غير فعّال."),
        "Cefiderocol": ("allow", "MBL: خيار مفضّل/بديل (IDSA 2026)."),
        "Aztreonam + Avibactam": ("allow", "NDM/MBL: الخيار المفضّل قليلاً على CZA + Aztreonam (IDSA 2026)."),
    },
}

RESERVE_NOTE = ("🛡️ دواء Reserve (WHO AWaRe) — يُحتفظ به للـ CRE / DTR. "
                 "لا يُستخدم إلا عند غياب خيار Access أو Watch فعّال على نفس اللوحة.")


def novel_agent_verdict(drug: str, organism: str, mech: Optional[Dict[str, Any]],
                         carb_type: Optional[str],
                         sir_map: Dict[str, str]) -> Tuple[str, str]:
    """('allow' | 'warn' | 'ban', note) for one novel agent on one isolate."""
    o = (organism or "").lower()
    prob = (mech or {}).get("probability")
    dtr = bool((mech or {}).get("dtr"))
    carb_r = any((sir_map or {}).get(d) in ("R", "I")
                 for d in ("Meropenem", "Imipenem/Cilastatin"))
    gp = any(k in o for k in ("staphylococc", "streptococc", "enterococc",
                              "listeria", "mrsa", "vre", "coagulase"))
    if gp or "anaerob" in o or "لاهوائ" in o:
        return "ban", f"{drug}: لا دور له ضد هذا الكائن ولا breakpoints."
    if "acinetobacter" in o:
        if drug == "Sulbactam + Durlobactam":
            if carb_r:
                return "allow", ("IDSA 2026: Sulbactam-durlobactam + Meropenem أو Imipenem هو "
                                 "الأولوية للعدوى الغازية بـ CRAB.")
            return "warn", RESERVE_NOTE + " (العزلة ليست CRAB)."
        if drug == "Cefiderocol":
            return "warn", ("IDSA 2026: Cefiderocol لـ CRAB عند مقاومة Sulbactam-durlobactam فقط، "
                            "ومع دواء ثانٍ. زيادة وفيات في CREDIBLE-CR.")
        return "ban", f"{drug}: لا نشاط موثوق ولا breakpoints ضد Acinetobacter."
    if "stenotrophomonas" in o:
        if drug == "Cefiderocol":
            return "allow", "IDSA 2026: Cefiderocol منفرداً هو المفضّل للعدوى الغازية بـ S. maltophilia."
        if drug == "Aztreonam + Avibactam":
            return "warn", ("IDSA 2026: بديل للعدوى الغازية، يُفضَّل مع دواء ثانٍ. لا breakpoints "
                            "CLSI لهذا الكائن.")
        return "ban", f"{drug}: غير فعّال ضد S. maltophilia (L1 metallo-β-lactamase)."
    if "pseudomonas" in o:
        if drug == "Sulbactam + Durlobactam":
            return "ban", "لا نشاط ضد P. aeruginosa."
        if drug == "Aztreonam + Avibactam":
            return "warn", ("لا breakpoints لـ P. aeruginosa (CLSI لـ Enterobacterales فقط) — "
                            "Avibactam لا يضيف كثيراً على Aztreonam ضد الزائفة.")
        if drug == "Meropenem + Vaborbactam":
            return "warn", "Vaborbactam لا يضيف نشاطاً على Meropenem ضد P. aeruginosa — احكم بنتيجة Meropenem."
        if dtr:
            if drug == "Ceftolozane + Tazobactam":
                return "allow", ("IDSA 2026: خيار مفضّل لـ DTR-P. aeruginosa، ومُقدَّم على "
                                 "Ceftazidime-avibactam في الالتهاب الرئوي.")
            if drug in ("Ceftazidime + Avibactam", "Imipenem + Relebactam"):
                return "allow", "IDSA 2026: خيار مفضّل لـ DTR-P. aeruginosa (لا يُعتمد عليه إن كان المنتج MBL)."
            if drug == "Cefiderocol":
                return "warn", "IDSA 2026: بديل لـ DTR-P. aeruginosa، ومفضّل إذا كان المنتج MBL."
        return "warn", (RESERVE_NOTE + " IDSA: إذا ظل بيتا-لاكتام تقليدي حسّاساً فهو المفضّل "
                        "بجرعة عالية وتسريب ممتد.")
    # Enterobacterales and the remaining Gram-negatives
    if drug == "Sulbactam + Durlobactam":
        return "ban", "معتمد ومُعايَر ضد Acinetobacter فقط — لا breakpoints لهذا الكائن."
    if prob in ("carbapenemase", "possible_carbapenemase") or carb_type:
        confirmed = prob == "carbapenemase" or bool(carb_type)
        if drug == "Ceftolozane + Tazobactam":
            if confirmed:
                return "ban", ("Ceftolozane-tazobactam لا يغطي Enterobacterales المنتجة للكاربابينيميز "
                               "(KPC / OXA-48 / MBL).")
            return "warn", ("اشتباه كاربابينيميز: Ceftolozane-tazobactam يفشل لو ثبت الإنزيم — "
                            "أكّد بـ mCIM / PCR أولاً.")
        if not carb_type:
            return "warn", ("نوع الكاربابينيميز غير محدد، والاختيار يتوقف عليه: "
                            "KPC ← Ceftazidime-avibactam أو Meropenem-vaborbactam أو Imipenem-relebactam؛ "
                            "OXA-48 ← Ceftazidime-avibactam؛ NDM/VIM/IMP ← Aztreonam-avibactam أو "
                            "Ceftazidime-avibactam + Aztreonam أو Cefiderocol. NDM و OXA-48 الأشيع في "
                            "مصر — اطلب NG-Test CARBA-5 أو PCR وحدّد النوع.")
        lvl, note = NOVEL_ACTIVITY.get(carb_type, {}).get(drug, ("warn", RESERVE_NOTE))
        return lvl, note
    return "warn", RESERVE_NOTE


def carb_tx_text(carb_type: Optional[str]) -> str:
    """Definitive-therapy pointer for a confirmed carbapenemase (IDSA AMR 2026)."""
    if carb_type == "KPC":
        return ("Ceftazidime-avibactam أو Meropenem-vaborbactam أو Imipenem-relebactam "
                "حسب الحساسية (IDSA 2026)")
    if carb_type == "OXA-48":
        return "Ceftazidime-avibactam (IDSA 2026)؛ Cefiderocol بديل"
    if carb_type == "MBL":
        return ("Aztreonam-avibactam، أو Ceftazidime-avibactam + Aztreonam، أو Cefiderocol "
                "(IDSA 2026)")
    return ("حدّد نوع الإنزيم أولاً (NG-Test CARBA-5 أو PCR) — العلاج يختلف بين KPC و OXA-48 "
            "و MBL. Colistin ليس خياراً مفضّلاً عند توفر عامل حديث فعّال (IDSA 2026)")


def allergy_profile(allergies: Optional[List[str]]) -> Dict[str, bool]:
    a = " | ".join(str(x).lower() for x in (allergies or []))
    pen = "penicillin" in a or "بنسلين" in a
    return {
        "penicillin": pen,
        "penicillin_severe": pen and any(k in a for k in ("severe", "anaphyl", "immediate",
                                                            "شديد", "تأق")),
        "cephalosporin": "cephalosporin" in a or "سيفالوسبورين" in a,
        "ceftazidime": "ceftazidime" in a,
        "sulfa": "sulfa" in a or "sulfonamide" in a or "سلفا" in a,
        "fluoroquinolone": "quinolone" in a or "كينولون" in a,
        "macrolide": "macrolide" in a or "ماكروليد" in a,
    }


