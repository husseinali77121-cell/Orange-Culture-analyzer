# © 2025 Dr / Hussein Ali -- Orange Lab, 6 October City, Egypt
# Microbiology CDSS -- All Rights Reserved
# Unauthorized copying or distribution is prohibited.

import base64
import hmac
import io
import json
import os
import re
import time
import hashlib
import logging
from datetime import datetime, date
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

logger = logging.getLogger("orange_cdss")

try:
    import cv2
    import numpy as np
    import pytesseract
    OCR_AVAILABLE = True
    OCR_IMPORT_ERROR = ""
except Exception as exc:
    cv2 = None
    np = None
    pytesseract = None
    OCR_AVAILABLE = False
    OCR_IMPORT_ERROR = str(exc)

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = ImageDraw = ImageFont = None

try:
    import weasyprint as _wp
    WEASYPRINT_AVAILABLE = True
except Exception:
    # Broad except deliberately, not ImportError: weasyprint's native
    # dependency (GTK3/Pango/Cairo, via cffi) raises OSError -- not
    # ImportError -- when the Python package is installed but the native
    # library is missing or broken (e.g. "cannot load library
    # 'libgobject-2.0-0'"). An ImportError-only except let that OSError
    # propagate and crash app startup entirely instead of degrading to "no
    # PDF generation", on ANY machine with a partial GTK3 install -- found
    # 2026-08-22 when the Windows EXE build's own test step hit exactly
    # this before GTK3 had been staged yet.
    WEASYPRINT_AVAILABLE = False
    _wp = None

try:
    import arabic_reshaper as _arabic_reshaper_mod
    from bidi.algorithm import get_display as _bidi_display
    ARABIC_SUPPORT = True
except ImportError:
    ARABIC_SUPPORT = False
    _arabic_reshaper_mod = None
    _bidi_display = None


from abx_guidelines import (
    ABX_ALIAS_INDEX,
    ABX_GUIDELINES,
    DEFAULT_SPECIMENS,
    normalize_abx_key,
    validate_abx_guidelines,
)
from organism_profile import ORGANISM_PROFILE, validate_organism_profile
from specimen_organism_map import (
    SPECIMEN_ORDER,
    SPECIMEN_ORGANISM_MAP,
    get_organisms_for_specimen,
    validate_specimen_organism_map,
)

# AST Quality-Check engine (validates susceptibility-result internal consistency)
try:
    from ast_qa_engine import run_ast_qa_engine
    AST_QA_AVAILABLE = True
except Exception:
    run_ast_qa_engine = None
    AST_QA_AVAILABLE = False

# AST reportability + internal-consistency rule modules (shared with the Orange
# Lab version -- single source of truth across both products). Optional: if the
# files are absent the QC report simply falls back to the inline phenotype rules.
try:
    from ast_reportability import (
        check_reportability as _check_reportability_ext,
        format_issue as _fmt_reportability,
    )
    from ast_consistency import (
        check_consistency as _check_consistency_ext,
        format_issue as _fmt_consistency,
    )
    AST_RULES_MODULES_AVAILABLE = True
    AST_RULES_IMPORT_ERROR = ""
except Exception as _ast_rules_exc:
    # A bare `except: pass` here is how the whole reportability + consistency QC
    # layer can switch itself off in production with nothing on screen. One
    # NameError in a rule table (a helper referenced before it is defined is
    # enough) silently downgrades the product from ~60 traceable rules to the
    # small inline fallback set. Record the reason and surface it in
    # get_startup_validation_issues() so it can never be invisible again.
    _check_reportability_ext = None
    _check_consistency_ext = None
    _fmt_reportability = None
    _fmt_consistency = None
    AST_RULES_MODULES_AVAILABLE = False
    AST_RULES_IMPORT_ERROR = f"{type(_ast_rules_exc).__name__}: {_ast_rules_exc}"
    logger.error("ast_reportability/ast_consistency unavailable -- AST QC is "
                 "running on the inline fallback rules only: %s", _ast_rules_exc)

# AST Panel Completeness -- "was enough tested at all", not "was what was
# tested interpreted correctly" (that's the block above). Same optional-import
# pattern: absence of this file must never crash the report -- but unlike the
# block above, this one used to swallow the exception completely with no
# captured message, no log line, and no entry in _MODULE_HEALTH below. That
# meant an import failure here was PERMANENTLY INVISIBLE: no card, no error,
# no clue anywhere in the app about why. Found 2026-08-22 when the card
# simply never appeared and there was nothing to look at to find out why.
try:
    from ast_panel_completeness import check_panel_completeness as _check_panel_completeness_ext
    PANEL_COMPLETENESS_AVAILABLE = True
    PANEL_COMPLETENESS_IMPORT_ERROR = ""
except Exception as _panel_completeness_exc:
    _check_panel_completeness_ext = None
    PANEL_COMPLETENESS_AVAILABLE = False
    PANEL_COMPLETENESS_IMPORT_ERROR = (
        f"{type(_panel_completeness_exc).__name__}: {_panel_completeness_exc}"
    )
    logger.error("ast_panel_completeness unavailable -- the Panel Completeness "
                 "card and its QC findings will not appear anywhere in the "
                 "report: %s", _panel_completeness_exc)

# Terminal safety gate + unified clinical constraint map. This is the layer that
# adds site penetration (can the drug physically reach the infection?) on top of
# the organism/host reasoning the main engine already does. Treated as CRITICAL
# in _MODULE_HEALTH: without it the app silently loses meningeal-penetration
# checking and the hepatic layer, and nothing on screen would say so.
try:
    from safety_gate import apply_safety_gate, GATE_VERSION
    from clinical_matrix import MATRIX_VERSION
    SAFETY_GATE_AVAILABLE = True
except Exception as _sg_exc:
    apply_safety_gate = None
    GATE_VERSION = MATRIX_VERSION = "unavailable"
    SAFETY_GATE_AVAILABLE = False
    logger.error("safety_gate/clinical_matrix unavailable: %s", _sg_exc)

# =========================================================
# ملاحظة: Ampicillin, Amoxicillin, Tetracycline, Cephradine
# منقولة بالكامل إلى abx_guidelines.py
# لا توجد بيانات مضادات حيوية في هذا الملف -- كل البيانات في abx_guidelines.py
# =========================================================

# =========================================================
# إعداد الصفحة
# =========================================================
st.set_page_config(
    page_title="Microbiology CDSS",
    layout="wide",
    page_icon="🔬"
)

st.markdown("""
<style>
    .stActionButton {display: none !important;}
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    header[data-testid="stHeader"] {display: none !important;}
    .app-card {
        padding: 1rem 1.2rem;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
        background: rgba(255,255,255,0.02);
        margin-bottom: 1rem;
    }
    .muted-text { color: #9aa0a6; font-size: 0.92rem; }
    .orange-badge {
        display:inline-block; background:#ff8c00; color:white;
        padding:0.25rem 0.7rem; border-radius:999px;
        font-size:0.8rem; font-weight:600;
    }
</style>
""", unsafe_allow_html=True)

# =========================================================
# الثوابت
# =========================================================
SESSION_TIMEOUT = 30 * 60
BACTERIA_TYPES  = list(ORGANISM_PROFILE.keys())
SPECIMEN_TYPES  = list(SPECIMEN_ORDER or DEFAULT_SPECIMENS)

AWARE_COLORS = {
    "Access":  "🟢 Access",
    "Watch":   "🟡 Watch",
    "Reserve": "🔴 Reserve",
}

# ── Commercial Names Loader ───────────────────────────────────────────
def load_commercial_names(filepath: str = "commercial_names.txt") -> Dict[str, str]:
    """Loads commercial names -- multi-path search for Streamlit Cloud compatibility."""
    import os as _os
    result: Dict[str, str] = {}
    # __file__ may be undefined in some exec contexts -> guard it
    try:
        _base = _os.path.dirname(_os.path.abspath(__file__))
    except NameError:
        _base = _os.getcwd()
    for _p in [filepath,
                _os.path.join(_base, filepath),
                _os.path.join(_os.getcwd(), filepath)]:
        try:
            with open(_p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        g, _, b = line.partition("=")
                        g, b = g.strip(), b.strip()
                        if g and b:
                            result[g.lower()] = b
            if result:
                break
        except FileNotFoundError:
            continue
        except Exception:
            continue
    return result

COMMERCIAL_NAMES: Dict[str, str] = load_commercial_names()

# The brand file and ABX_GUIDELINES spell combination drugs differently
# ("Amoxicillin-Clavulanate" vs "Amoxicillin + Clavulanic acid",
# "Ampicillin-Sulbactam" vs "Ampicillin/Sulbactam"). An exact lowercase lookup
# therefore returned NOTHING for 11 of 51 agents -- including Augmentin, Unasyn,
# Tazocin, Tienam and Septrin, the brands an Egyptian clinician is most likely to
# want. Resolve through the same normalisation and alias index the OCR uses, so
# either spelling finds the entry.
_COMMERCIAL_BY_KEY: Dict[str, str] = {}
for _g, _b in COMMERCIAL_NAMES.items():
    _COMMERCIAL_BY_KEY[normalize_abx_key(_g)] = _b
    _canon = ABX_ALIAS_INDEX.get(normalize_abx_key(_g))
    if _canon:
        _COMMERCIAL_BY_KEY.setdefault(normalize_abx_key(_canon), _b)

def get_commercial_name(generic: str) -> str:
    if not generic:
        return ""
    direct = COMMERCIAL_NAMES.get(generic.lower(), "")
    if direct:
        return direct
    key = normalize_abx_key(generic)
    if key in _COMMERCIAL_BY_KEY:
        return _COMMERCIAL_BY_KEY[key]
    # Last resort: the drug's own declared aliases (e.g. "augmentin").
    for _alias in (ABX_GUIDELINES.get(generic, {}) or {}).get("aliases", []):
        hit = _COMMERCIAL_BY_KEY.get(normalize_abx_key(_alias))
        if hit:
            return hit
    return ""

COMMON_MEDS = [
    "Antacids (مضادات الحموضة)",
    "Warfarin (مضادات التخثر)",
    "NSAIDs (مسكنات الألم)",
    "SSRI (أدوية الاكتئاب)",
    "Valproic acid (مضادات الصرع)",
    # Added on re-review. abx_guidelines.py declares interactions against these
    # classes, but none of them could be SELECTED, so the entries were dead: the
    # rhabdomyolysis warning on fusidic acid + statin, the QT warning on
    # moxifloxacin, the ototoxicity warning on tobramycin + loop diuretic and the
    # methotrexate warning on penicillin could never once have fired in the app.
    "Statins (أدوية الكوليسترول)",
    "QT-prolonging drugs (أدوية تطيل QT)",
    "Methotrexate (ميثوتريكسات)",
    "Iron supplements (مكملات الحديد)",
    "Loop diuretics (Furosemide)",
    "Theophylline (ثيوفيلين)",
    "Neuromuscular blocking agents (مرخيات العضلات)",
    # Added 2026-11-10 (round 2). The same defect as above, found again: these
    # classes are declared in abx_guidelines.py but could not be selected, so
    # TMP-SMX + ACE inhibitor (hyperkalaemia), clarithromycin + colchicine
    # (fatal toxicity), linezolid + MAOI / tramadol (serotonin syndrome) and
    # ciprofloxacin + tizanidine (contraindicated) could never fire.
    "ACE inhibitors (مثبطات ACE)",
    "ARBs (حاصرات الأنجيوتنسين)",
    "Spironolactone (مدر حافظ للبوتاسيوم)",
    "Phenytoin (فينيتوين)",
    "Sulfonylureas (خافضات السكر)",
    "Azathioprine (آزاثيوبرين)",
    "Colchicine (كولشيسين)",
    "Digoxin (ديجوكسين)",
    "Calcium channel blockers (حاصرات الكالسيوم)",
    "Ergot alkaloids (إرجوتامين)",
    "MAOI (مثبطات MAO)",
    "Tramadol / Pethidine (أفيونات سيروتونينية)",
    "Sympathomimetics (سودوإيفيدرين / دوبامين)",
    "Tizanidine (تيزانيدين)",
    "Nephrotoxic drugs (Amphotericin / Cyclosporine / Tacrolimus)",
]

# ── Interaction matching ────────────────────────────────────────────────────
# Matching was exact string equality, and the formulary spells the same class
# two ways -- "Warfarin" on gatifloxacin/moxifloxacin but
# "Warfarin (مضادات التخثر)" on TMP-SMX, metronidazole and ciprofloxacin. Only
# one spelling could ever match the dropdown, so selecting warfarin silently
# missed whichever half of the formulary used the other form. Eleven declared
# interactions were unreachable in total. Compare on a canonical key instead.
_MED_CANON = {
    "antacid": "antacids", "antacids": "antacids",
    "warfarin": "warfarin", "anticoagulant": "warfarin",
    "nsaid": "nsaids", "nsaids": "nsaids",
    "ssri": "ssri", "snri": "ssri", "antidepressant": "ssri",
    "valproic acid": "valproate", "valproate": "valproate",
    "statin": "statins", "statins": "statins",
    "qt-prolonging drugs": "qt", "qt prolonging drugs": "qt",
    "methotrexate": "methotrexate",
    "iron supplements": "iron", "iron": "iron",
    "loop diuretics": "loop_diuretic", "furosemide": "loop_diuretic",
    "theophylline": "theophylline",
    "neuromuscular blocking agents": "nmba",
    "vancomycin": "vancomycin",
    # ── Added 2026-08-01 with the interaction-table fix ───────────────────────
    # A class label in interacts_with only ever fires if the medication the
    # clinician actually typed canonicalises to the same key. "ACE inhibitors"
    # was declared on TMP-SMX and matched nothing, because nobody types "ACE
    # inhibitors" -- they type Lisinopril. The individual generics are what
    # reaches this function, so the class has to be reachable from them.
    "ace inhibitor": "acei", "ace inhibitors": "acei",
    "lisinopril": "acei", "enalapril": "acei", "ramipril": "acei",
    "captopril": "acei", "perindopril": "acei", "quinapril": "acei",
    "arb": "arb", "arbs": "arb",
    "losartan": "arb", "valsartan": "arb", "candesartan": "arb",
    "irbesartan": "arb", "telmisartan": "arb", "olmesartan": "arb",
    "spironolactone": "k_sparing", "eplerenone": "k_sparing",
    "amiloride": "k_sparing", "potassium": "k_sparing",
    "colchicine": "colchicine",
    "digoxin": "digoxin",
    "phenytoin": "phenytoin",
    "azathioprine": "azathioprine", "6-mercaptopurine": "azathioprine",
    "sulfonylurea": "sulfonylurea", "sulfonylureas": "sulfonylurea",
    "glibenclamide": "sulfonylurea", "gliclazide": "sulfonylurea",
    "glimepiride": "sulfonylurea", "glipizide": "sulfonylurea",
    "maoi": "maoi", "monoamine oxidase": "maoi",
    "selegiline": "maoi", "rasagiline": "maoi", "linezolid": "maoi",
    "pethidine": "serotonergic_opioid", "meperidine": "serotonergic_opioid",
    "tramadol": "serotonergic_opioid", "fentanyl": "serotonergic_opioid",
    "sympathomimetics": "sympathomimetic", "pseudoephedrine": "sympathomimetic",
    "dopamine": "sympathomimetic", "adrenaline": "sympathomimetic",
    "epinephrine": "sympathomimetic",
    "tyramine-rich foods": "tyramine", "tyramine": "tyramine",
    "ergot alkaloids": "ergot", "ergotamine": "ergot",
    "calcium channel blockers": "ccb", "amlodipine": "ccb",
    "verapamil": "ccb", "diltiazem": "ccb", "nifedipine": "ccb",
    "atorvastatin": "statins", "simvastatin": "statins",
    "rosuvastatin": "statins", "lovastatin": "statins",
    # ── Added 2026-11-10 (round 2) ────────────────────────────────────────────
    "tizanidine": "tizanidine",
    "nephrotoxic drugs": "nephrotoxic", "nephrotoxic": "nephrotoxic",
    "amphotericin": "nephrotoxic", "cyclosporine": "nephrotoxic",
    "ciclosporin": "nephrotoxic", "tacrolimus": "nephrotoxic",
    "cisplatin": "nephrotoxic",
}


def _canon_med(name: str) -> str:
    """Canonical key for one medication / drug-class label.

    Strips any parenthetical gloss (Arabic or English) and matches the leading
    class name, so "Warfarin" and "Warfarin (مضادات التخثر)" collapse together.
    """
    base = re.split(r"[(\uFF08]", str(name or ""), 1)[0].strip().lower()
    if base in _MED_CANON:
        return _MED_CANON[base]
    # FIX 2026-11-10 (round 2): this was a bare substring test in dict order, so
    # "iron" fired inside "spIRONolactone" and "arb" inside "cARBamazepine" --
    # a potassium-sparing diuretic was matched as an iron supplement. Whole
    # words only, longest key first (an optional plural "s" is tolerated).
    for key in sorted(_MED_CANON, key=len, reverse=True):
        if re.search(r"(?<![a-z0-9])" + re.escape(key) + r"s?(?![a-z0-9])", base):
            return _MED_CANON[key]
    return base

RENAL_BAN_REASONS = {
    # The threshold in this text said 30 while the engine enforced 45 (EMA/BNF
    # 2025), so the explanation shown to the clinician contradicted the ban that
    # had just fired. Corrected 2026-07-30.
    "nitrofurantoin": (
        "Nitrofurantoin يحتاج وظيفة كلى سليمة ليتركز في البول.\n"
        "عند CrCl < 45 مل/د (EMA/BNF 2025):\n"
        "- لا يصل لتركيز علاجي في البول -> لا يقتل الجرثومة.\n"
        "- يتراكم في الدم -> خطر سُمية رئوية وعصبية.\n"
        "السبب: الدواء يُطرح كلياً عبر الترشيح الكبيبي."
    ),
}

CHILD_BAN_REASONS = {
    "fluoroquinolone": (
        "الفلوروكينولونات قد تؤثر على غضاريف النمو في الأطفال < 18 سنة.\n"
        "تُستخدم فقط عند انعدام البدائل وبقرار متخصص."
    ),
    "tetracycline": (
        "Doxycycline والتتراسيكلينات قد تترسب في العظام والأسنان النامية.\n"
        "قد تسبب تلوينًا دائمًا للأسنان وتأثيرًا على نمو العظام.\n"
        "ممنوعة غالباً تحت 8 سنوات."
    ),
}

ORGANISM_AVOID_CLASS_MAP = {
    "cephalosporins (كل الجيل)": ["cephalosporin"],
    "cephalosporins":            ["cephalosporin"],
    "tetracyclines":             ["tetracycline"],
    "aminoglycosides":           ["aminoglycoside"],
    "carbapenems":               ["carbapenem"],
    "beta-lactams (alone)":      ["penicillin", "cephalosporin", "carbapenem"],
    "beta-lactams":              ["penicillin", "cephalosporin", "carbapenem"],
}


def _drop_intrinsic(names, organism):
    """Remove agents this organism is intrinsically resistant to.

    The Organism Guidance panel printed first/second/third-line straight from
    ORGANISM_PROFILE with only the urine-only filter applied. Nothing checked
    the intrinsic table, so a single stale row in the profile put a drug the
    engine BANS on the same screen as a recommendation. This closes the display
    against the same source of truth the engine uses, so the two cannot drift
    apart again even if a profile row is edited carelessly.
    """
    out = []
    for n in (names or []):
        info = ABX_GUIDELINES.get(n, {})
        if is_intrinsically_avoided(organism, n, info):
            continue
        out.append(n)
    return out


def _hide_urine_only(names, specimen):
    """Drop urine-only agents from organism first/second/third-line *guidance display*
    on non-urine sites (they reach therapeutic levels only in urine). The ranking side
    already strips these from `allowed`; this keeps the reference list honest too.
    Norfloxacin keeps an enteric (GI) role, so it is retained for Stool."""
    # Uses the canonical classifier so that this display filter cannot drift away
    # from the therapeutic filter in analyze_antibiotics -- they must agree on
    # what counts as urine, or the reference list contradicts the recommendation.
    cat = classify_specimen(specimen)
    if cat == "urine":
        return list(names or [])
    drop = {"nitrofurantoin", "fosfomycin"}
    if cat != "stool":
        drop = drop | {"norfloxacin"}
    return [n for n in (names or []) if n.lower().strip() not in drop]

# =========================================================
# تحميل المشتركين
# =========================================================
def load_subscribers() -> Dict[str, str]:
    try:
        raw  = st.secrets.get("subscribers_json") or st.secrets.get("subscribers", "{}")
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
        return {str(k).strip().lower(): str(v).strip() for k, v in data.items()}
    except Exception:
        return {}

# ── Vendor identity — configurable for resale ───────────────────────────────
# Support phone and e-mail were hard-coded in four places. Every lab that buys
# this build shipped with the original developer's personal mobile number and
# private Gmail address on the login page, the renewal banner and the expiry
# logout message. Override per deployment in .streamlit/secrets.toml:
#
#   vendor_name  = "Orange Lab"
#   vendor_phone = "+20 …"
#   vendor_email = "support@…"
def _vendor(key: str, default: str) -> str:
    try:
        return str(st.secrets.get(key, default) or default)
    except Exception:
        return default


VENDOR_PHONE = _vendor("vendor_phone", "01016872801")
VENDOR_EMAIL = _vendor("vendor_email", "Hussein.ali77121@gmail.com")


SUBSCRIBERS = load_subscribers()


# ═══════════════════════════════════════════════════════════════════════
# PASSWORD VERIFICATION
# ----------------------------------------------------------------------
# The commercial build authenticated on an EMAIL ADDRESS ALONE. Anyone who knew
# or guessed a subscriber's address had full access to a paid product, and there
# was no way for a customer to revoke a leaked login short of deleting the
# account. Email is an identifier, not a secret.
#
# Rollout is deliberately backward-compatible so no existing customer is locked
# out on deploy:
#   * secrets["subscriber_hashes"] = {"<email>": "pbkdf2_sha256$<iters>$<salt>$<hash>"}
#   * an email WITH a hash must supply the matching password
#   * an email WITHOUT a hash still logs in as before, but the account is listed
#     in get_startup_validation_issues() so the gap is visible rather than silent
#
# Generate a hash with:  python -c "import streamlit_app as a; \
#                                   print(a.make_password_hash('the-password'))"
# ═══════════════════════════════════════════════════════════════════════
_PBKDF2_ITERATIONS = 240_000
# Login throttle — see auth_service.py. Persisted per ACCOUNT, not per session.
import auth_service as _AUTH                                        # noqa: E402
# The two aliases that used to live here (_LOGIN_MAX_ATTEMPTS,
# _LOGIN_LOCKOUT_SECONDS) were kept for backward compatibility when the throttle
# moved to auth_service.py, and nothing ever read them. Read
# _AUTH.MAX_ATTEMPTS / _AUTH.LOCKOUT_SECONDS directly — one name per fact.


# ── Administrator utility — intentionally not called from anywhere ──────────
# make_password_hash() is run BY HAND, from a Python shell, to generate the
# value that goes into the `subscriber_hashes` secret:
#
#     python -c "import streamlit_app as s; print(s.make_password_hash('...'))"
#
# A dead-code scan flags it every time because nothing in the app invokes it.
# It stays: an operator needs it to onboard a subscriber, and the alternative
# is a password-hashing routine pasted into a shell from memory, which is how
# salts get omitted. Deleting it would remove the only correct way to produce
# the value this app refuses to start without.
def make_password_hash(password: str, iterations: int = _PBKDF2_ITERATIONS) -> str:
    """Encode a password as pbkdf2_sha256$iterations$salt$hash (base64 parts)."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(dk).decode("ascii"),
    )


def load_subscriber_hashes() -> Dict[str, str]:
    try:
        raw = st.secrets.get("subscriber_hashes", "{}")
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
        return {str(k).strip().lower(): str(v).strip() for k, v in data.items()}
    except Exception:
        return {}


SUBSCRIBER_HASHES = load_subscriber_hashes()


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time check of a password against a stored pbkdf2 record."""
    try:
        algo, iters, salt_b64, hash_b64 = str(encoded).split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", (password or "").encode("utf-8"),
            base64.b64decode(salt_b64), int(iters),
        )
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except Exception:
        return False

# =========================================================
# Session State
# =========================================================
def init_session_state() -> None:
    defaults = {
        "authenticated":      False,
        "email":              "",
        "days_left":          None,
        "last_activity":      None,
        "logout_reason":      "",
        "ocr_data":           None,
        "last_file_hash":     "",
        "sir_map_edited":     {},
        "patient_name_ocr":   "",
        "patient_name_final": "",
        # ─── حقول المزرعة الجديدة ─────────────────────────────────────────
        "colony_count":       "≥ 10^5 CFU/mL",
        "date_in":            date.today(),
        "pus_cells_text":     "",
        "rbcs_text":          "",
        # اسم المعمل -- قابل للتعديل من الـ sidebar
        "lab_name":           "Your Lab Name",
        "lab_city":           "",
        # ─── Commercial Names ─────────────────────────────────────────────
        "show_commercial_names": False,
        # ─── Pathogenicity Assessment ─────────────────────────────────────
        "patho_culture_purity":   "Pure growth",
        "patho_symptoms":         [],
        "patho_urinalysis":       "مش معروف / مش مذكور",
        "patho_gram_stain":       "مش متعملة",
        "patho_host_factors":     [],
        "patho_sputum_pus":       "",
        "patho_sputum_epi":       "",
        "patho_sirs":             [],
        "patho_blood_source":     "",
        "patho_wound_type":       "",
        "patho_result":           None,
        # ─── Clinical Engines v4 ──────────────────────────────────────────
        "severity_level":          "moderate",  # overwritten by auto-suggest
        "last_patho_specimen":     "",   # tracks specimen that generated patho_result
        # Seeded to "C", not "A". analyze_antibiotics() documents that it
        # fail-closes to the worst grade when the caller does not know it, but
        # this seed was the caller, and it asserted the mildest grade. Because
        # the Child-Pugh selectbox renders BELOW the analysis call in script
        # order, the first run after ticking "Hepatic Impairment" always
        # evaluated as Child-Pugh A -- which is 0 hepatic bans instead of 7
        # (Amox-Clav/DILI, Azithromycin, Clarithromycin, Metronidazole, TMP-SMX,
        # Nitrofurantoin, Doxycycline). clinical_matrix also downgrades its
        # hepatic DENY to CAUTION on grade A, so both layers failed together and
        # there was no independent backstop. The grade is now asked for in the
        # sidebar, next to the flag, before anything is evaluated.
        "child_pugh_class":        "C",
        "days_on_iv":              3,
        "clinical_improving_48h":  True,
        "tolerating_oral":         True,
        "bacteremia_resolved":     True,
        "hours_on_treatment":      72,
        "de_clinical_improving":   True,
        # ─── PDF Report Options ───────────────────────────────────────────
        "pdf_include_combo":       True,
        "pdf_include_duration":    True,
        "pdf_include_patho":       True,
        # ─── New image/report fields ──────────────────────────────────────
        "referring_physician":     "",
        "culture_condition":       "Aerobic",
        "microbiologist":          "",
        # ─── Cached Computations (prevent regeneration on every widget) ────
        "_img_bytes":              None,
        "_img_hash":               "",
        "_img_error":              False,
        "_rpt_text":               "",
        "_rpt_hash":               "",
        "_pdf_bytes":              None,
        "_pdf_hash":               "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()


# ── A new report is a new patient ───────────────────────────────────────────
# FIX 2026-11-11 (round 4). Uploading the next report reset only the S/I/R
# panel. Everything else the clinician had entered for the PREVIOUS patient
# stayed live and flowed into the new patient's analysis and report: the
# pregnancy, renal and hepatic flags, the creatinine, current medications,
# drug allergies, the carbapenemase class, the UTI syndrome, the colony count,
# pus cells and RBCs (whose OCR auto-fill then refused to overwrite them), the
# patient's name, and -- when the specimen type matched -- the previous
# pathogenicity verdict, printed in the new report. Widgets that hold patient
# facts are either keyed per file (and so recreated) or listed here and reset.
_PATIENT_WIDGET_KEYS = (
    "colony_count_input", "date_in_input", "pus_cells_input", "rbcs_input",
    "ref_phys_input", "culture_cond_sel",
    "patho_purity_sel", "patho_gram_sel", "patho_ua_sel", "patho_coll_sel",
    "patho_symp_urine", "patho_host_sel",
    "np_purity_sel", "np_gram_sel", "np_sirs_ms", "np_bsrc_sel", "np_spwbc",
    "np_spepi", "np_symp_gi", "np_wtype_sel", "np_symp_wound", "np_symp_resp",
    "np_host_sel",
    "sev_sel_ui", "sw_drug_sel", "sw_days_num", "sw_i_chk", "sw_o_chk", "sw_b_chk",
    "de_h_num", "de_i_chk",
)
_PATIENT_STATE_KEYS = (
    "patient_name_ocr", "patient_name_final", "colony_count", "date_in",
    "pus_cells_text", "rbcs_text", "referring_physician", "culture_condition",
    "patho_culture_purity", "patho_symptoms", "patho_urinalysis", "patho_gram_stain",
    "patho_host_factors", "patho_sputum_pus", "patho_sputum_epi", "patho_sirs",
    "patho_blood_source", "patho_wound_type", "patho_result", "patho_pdf_ctx",
    "last_patho_specimen", "severity_level", "child_pugh_class", "carb_type_now",
    "days_on_iv", "clinical_improving_48h", "tolerating_oral", "bacteremia_resolved",
    "hours_on_treatment", "de_clinical_improving",
    "_img_bytes", "_img_hash", "_img_error", "_rpt_text", "_rpt_hash",
    "_pdf_bytes", "_pdf_hash", "_pdf_lang_used",
)


def reset_patient_state() -> None:
    """Forget every patient-specific input before a different report is read."""
    for _k in _PATIENT_WIDGET_KEYS + _PATIENT_STATE_KEYS:
        st.session_state.pop(_k, None)
    for _k in [k for k in list(st.session_state.keys())
               if str(k).startswith("severity_manual_")]:
        st.session_state.pop(_k, None)
    init_session_state()          # re-seed the data keys with their defaults

# =========================================================
# أدوات مساعدة
# =========================================================
# ── OCR / parsing moved to ocr_parsing.py (2026-08-03) ──────────────────────
# 329 lines that were spread across FOURTEEN fragments between line 586 and
# line 1898 of this file: the fuzzy matcher, the organism alias table, the disk
# codes, the drug scanner and the S/I/R vocabulary. Three of this audit's
# defects lived in that scatter — the phantom "Ampicillin" from a substring
# match, the disk-code panel that parsed to nothing, and an S/I/R vocabulary a
# thousand lines from the table it validated. Re-exported so existing callers
# and the AST-extraction harnesses still find them by name.
from ocr_parsing import (                                            # noqa: E402,F401
    fuzzy_match, normalize_ocr_text, clean_patient_name, detect_age_months,
    ORGANISM_OCR_ALIASES, ABX_DISK_CODES,
    _scan_line_for_disk_codes, _scan_line_for_drugs, extract_detected_drugs,
    _SIR_ALIASES, normalize_sir_value, normalize_sir_map,
    match_antibiotic_from_text, parse_result_line, age_reading_is_ambiguous,
)



def make_file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()

def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default

def calc_creatinine_clearance(age: int, weight: float, scr: float, sex: str) -> float:
    if scr <= 0:
        return 0.0
    crcl = ((140 - age) * weight) / (72 * scr)
    if sex == "Female":
        crcl *= 0.85
    # Cockcroft-Gault goes negative past age 140. The widget caps age at 120 so
    # this cannot fire today, but a negative clearance would satisfy every
    # `cl_cr <= renal_limit` test at once and print "CrCl -14 ml/min" in the
    # report, so clamp at the source rather than trusting the caller.
    return max(0.0, crcl)


def calc_paediatric_egfr(height_cm: Optional[float], scr: Optional[float],
                         age_years: Optional[float],
                         age_months: Optional[int] = None) -> Optional[float]:
    """Paediatric eGFR (ml/min/1.73 m²) -- bedside Schwartz, or None.

    Added 2026-11-11 (round 4). Cockcroft-Gault is an ADULT equation; in a
    child it is driven by body weight and badly underestimates clearance (a
    healthy 3.5 kg neonate with SCr 0.5 came out at ~14 ml/min).
      * 1-17 years: bedside Schwartz (CKiD, Schwartz et al. JASN 2009),
        eGFR = 0.413 x height(cm) / SCr(mg/dL)
      * under 1 year: the original Schwartz constant for TERM infants, 0.45
        (0.33 applies to pre-term infants, which this form cannot tell apart).
    Returns None without a height -- the equation cannot be applied.
    """
    try:
        h = float(height_cm or 0)
        s = float(scr or 0)
    except (TypeError, ValueError):
        return None
    if h <= 0 or s <= 0:
        return None
    infant = (age_months is not None) or (age_years is not None and age_years < 1)
    k = 0.45 if infant else 0.413
    return round(k * h / s, 1)


# ── UNKNOWN vs NORMAL CLEARANCE ──────────────────────────────────────────────
# The defect this replaces: the sidebar set `cl_cr = 100.0` whenever serum
# creatinine was left at 0, and 100 ml/min is not "unknown", it is a normal
# clearance. So a clinician who TICKED "Renal Impairment" but did not have the
# creatinine to hand got:
#   * no renal dose-adjustment note on any agent (no renal_limit reaches 100),
#   * Nitrofurantoin RECOMMENDED rather than refused,
#   * and a report line reading "Renal: IMPAIRED  CrCl: 100" — an asserted
#     normal number, which is worse than printing nothing.
# Measured against a real CrCl of 25 the same panel went from 19 recommended
# agents to 6. The flag did nothing at all except add a reassuring caption.
#
# `None` now means "not measured". When the impairment flag is set we substitute
# ASSUMED_CRCL_UNKNOWN, which is the same 30 ml/min convention clinical_matrix
# already used, so the two layers agree instead of one assuming 30 and the other
# 100. Every string that quotes a substituted number says it was ASSUMED.
ASSUMED_CRCL_UNKNOWN: float = 30.0


def resolve_crcl(cl_cr: Optional[float], is_renal: bool) -> Tuple[Optional[float], bool]:
    """(effective CrCl, was_measured). None means no renal branch applies."""
    if cl_cr is not None:
        return float(cl_cr), True
    return (ASSUMED_CRCL_UNKNOWN, False) if is_renal else (None, False)


def crcl_label(cl_cr: Optional[float], is_renal: bool = False,
               lang: str = "en") -> str:
    """CrCl for display. Never presents an assumed value as a measured one."""
    eff, measured = resolve_crcl(cl_cr, is_renal)
    if eff is None:
        return "غير مطلوب" if lang == "ar" else "not applicable"
    if measured:
        return f"{eff:.1f} ml/min"
    if lang == "ar":
        return (f"غير مقيسة (لم يُدخل الكرياتينين) — الجرعات محسوبة على "
                f"افتراض CrCl ≈ {eff:.0f} مل/د")
    return (f"not measured (no creatinine entered) — dosing assumes "
            f"CrCl ≈ {eff:.0f} ml/min")


def get_renal_severity(crcl: Optional[float]) -> str:
    # KDIGO G-stages rather than three home-made bands. The old table called
    # CrCl 200 "Mild" and lumped G4 (15-29) together with dialysis-dependent G5,
    # which are not the same dosing problem.
    if crcl is None:
        return "Unknown"
    if crcl >= 90:
        return "Normal (G1)"
    if crcl >= 60:
        return "Mild (G2)"
    if crcl >= 30:
        return "Moderate (G3)"
    if crcl >= 15:
        return "Severe (G4)"
    return "Kidney failure (G5)"

def get_route_label(item: Dict[str, Any]) -> str:
    return "🟢 Oral preferred / PO-friendly" if item.get("high_po") else "💉 IV/IM only"

def uniq_keep_order(items: List[str]) -> List[str]:
    seen:   set       = set()
    result: List[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            result.append(x)
    return result

def ensure_ocr_dependencies() -> None:
    if OCR_AVAILABLE:
        return
    st.error(
        "تعذر تحميل مكتبات OCR المطلوبة لتشغيل قراءة الصور.\n\n"
        f"Runtime import error: {OCR_IMPORT_ERROR}"
    )
    st.stop()

@st.cache_data(show_spinner=False)
def get_startup_validation_issues() -> List[str]:
    issues: List[str] = []
    issues.extend(validate_abx_guidelines(
        known_organisms=list(ORGANISM_PROFILE.keys()),
        known_specimens=SPECIMEN_TYPES
    ))
    issues.extend(validate_organism_profile(known_antibiotics=list(ABX_GUIDELINES.keys())))
    issues.extend(validate_specimen_organism_map(known_organisms=list(ORGANISM_PROFILE.keys())))
    if not SUBSCRIBER_HASHES:
        issues.append(
            "[SECURITY] No subscriber_hashes secret is configured -- login is by "
            "email address alone, so anyone who knows a customer's address has "
            "full access. Add a secrets entry: subscriber_hashes = "
            '{"user@lab.com": "pbkdf2_sha256$..."} (generate with '
            "make_password_hash())."
        )
    else:
        _open = sorted(e for e in SUBSCRIBERS if e not in SUBSCRIBER_HASHES)
        if _open:
            issues.append(
                f"[SECURITY] {len(_open)} subscriber account(s) still have no "
                f"password set: {', '.join(_open[:5])}"
                + (" ..." if len(_open) > 5 else "")
            )
    _bad_preg = sorted(
        f"{d} = {i.get('preg_status')!r}" for d, i in ABX_GUIDELINES.items()
        if str(i.get("preg_status") or "").strip().upper() not in _PREG_ALIASES
    )
    if _bad_preg:
        issues.append(
            "[WARNING] preg_status values outside the Safe/Warn/Banned enum -- "
            "they are being treated as 'Warn' (fail-closed) but should be "
            f"corrected in abx_guidelines.py: {', '.join(_bad_preg)}"
        )
    if not AST_RULES_MODULES_AVAILABLE:
        issues.append(
            "[CRITICAL] ast_reportability / ast_consistency failed to load -- the "
            "AST QC report is running on the small inline fallback rule set. "
            "Intrinsic-resistance and panel-discrepancy findings will be MISSING "
            f"from every report. Reason: {AST_RULES_IMPORT_ERROR or 'unknown'}"
        )
    if not AST_QA_AVAILABLE:
        issues.append(
            "[CRITICAL] ast_qa_engine failed to load -- Level-1 AST QA checks are "
            "disabled."
        )
    if not PANEL_COMPLETENESS_AVAILABLE:
        issues.append(
            "[WARNING] ast_panel_completeness failed to load -- the '🧫 AST "
            "Panel Completeness' card will not appear anywhere in the report "
            f"and no 'missing expected agent' findings will be generated. "
            f"Reason: {PANEL_COMPLETENESS_IMPORT_ERROR or 'unknown'}"
        )
    if not INTRINSIC_TABLE_OK:
        issues.append(
            "[CRITICAL] clinical_data.py not found -- INTRINSIC_RESISTANCE is empty. "
            "Intrinsically inactive agents will NOT be routed to Avoid and will NOT be "
            "stripped before MDR counting. Upload clinical_data.py next to streamlit_app.py."
        )
    deduped: List[str] = []
    seen:    set        = set()
    for issue in issues:
        if issue not in seen:
            deduped.append(issue)
            seen.add(issue)
    return deduped


def best_default_index(options: List[str], preferred: Optional[str]) -> int:
    if preferred and preferred in options:
        return options.index(preferred)
    return 0

# =========================================================
# اكتشاف اسم المريض من OCR
# =========================================================

def get_subscription_days_left(email: str) -> Optional[int]:
    email = (email or "").strip().lower()
    if email not in SUBSCRIBERS:
        return None
    expiry_str = SUBSCRIBERS[email]
    try:
        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        today       = datetime.now().date()
        return (expiry_date - today).days
    except Exception:
        return None

def show_login_page():
    if st.session_state.get("logout_reason"):
        st.warning(st.session_state.pop("logout_reason"))
    st.markdown("""
    <div style='text-align:center; padding: 3rem 0 1rem 0'>
        <span style='font-size:3rem'>🍊</span>
        <h2 style='margin:0.3rem 0 0.1rem 0'>Microbiology CDSS</h2>
        <p style='color:gray; margin:0'>AI-Assisted Antibiotic Decision Support -- Egyptian Market</p>
    </div>
    """, unsafe_allow_html=True)
    _, col2, _ = st.columns([1, 2, 1])
    with col2:
        st.markdown("#### 🔐 تسجيل الدخول")
        email    = st.text_input("📧 البريد الإلكتروني", placeholder="example@hospital.com",
                                 label_visibility="collapsed")
        password = st.text_input("🔑 كلمة المرور", type="password",
                                 placeholder="كلمة المرور",
                                 label_visibility="collapsed")
        login_btn = st.button("دخول", use_container_width=True, type="primary")
        if login_btn:
            return email.strip().lower(), password
        st.markdown("---")
        st.markdown(f"""
        <div style='text-align:center; border:1px solid #E8A33D; border-radius:10px;
                    padding:14px 12px; background:rgba(232,163,61,0.07)'>
          <div style='font-size:1.02rem; font-weight:700; color:#C2410C;
                      margin-bottom:6px'>
            ⏳ الفترة التجريبية المجانية تقترب من نهايتها
          </div>
          <div style='font-size:0.9rem; line-height:1.85'>
            برجاء سرعة التواصل معنا لتسجيل اشتراكك قبل انتهاء المدة، حفاظًا على
            استمرار عملك دون انقطاع والاحتفاظ ببياناتك وإعداداتك.<br>
            <span style='color:#B45309; font-weight:600'>
              بعد انتهاء الفترة التجريبية يتوقف الدخول إلى النظام تلقائيًا.
            </span>
          </div>
          <div style='margin:12px 0 8px; font-size:1.05rem; font-weight:700'>
            📞 <a href='tel:{VENDOR_PHONE}' style='text-decoration:none'>{VENDOR_PHONE}</a>
            &nbsp;·&nbsp;
            ✉️ <a href='mailto:{VENDOR_EMAIL}' style='text-decoration:none'>{VENDOR_EMAIL}</a>
          </div>
          <div style='font-size:0.88rem; color:#555; line-height:1.8'>
            🔹 تجريبي مجاني: <b>15 يوم</b><br>
            🔹 شهري: <b>200 جنيه</b><br>
            🔹 سنوي: <b>2000 جنيه</b>
            <span style='color:#15803D; font-weight:600'>(توفير 400 جنيه)</span>
          </div>
        </div>
        """, unsafe_allow_html=True)
    return None

def check_subscription(email: str, password: str = "") -> bool:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        st.warning("⚠️ أدخل بريدًا إلكترونيًا صحيحًا")
        return False
    # ── Throttle ─────────────────────────────────────────────────────────────
    # 2026-08-01 this counter lived in st.session_state, which is per BROWSER
    # SESSION: an attacker clearing cookies, opening a private window, or
    # driving the app from a script got a fresh five attempts every time. It
    # stopped a naive loop and nothing else.
    #
    # 2026-08-03 it moved to auth_service.py, keyed by ACCOUNT and persisted on
    # disk, so the limit follows the e-mail rather than the browser. Storage
    # failures FAIL OPEN and are logged loudly — a laboratory locked out of its
    # own CDSS because a disk filled up is a worse outcome than a slower brute
    # force, and the attempt is recorded either way.
    #
    # Still NOT a distributed rate limiter: one JSON file under one process. If
    # this is ever scaled horizontally the store must move to Redis, and the
    # interface in auth_service is deliberately the shape that migration keeps.
    _locked, _wait, _prior_fails = _AUTH.check_lockout(email)
    if _locked:
        st.error(f"⛔ محاولات كثيرة خاطئة على هذا الحساب. "
                 f"حاول بعد {_wait // 60}:{_wait % 60:02d} دقيقة.")
        return False
    if email not in SUBSCRIBERS:
        st.error("❌ هذا البريد غير مسجل في النظام")
        st.info(
            "**للحصول على نسخة تجريبية مجانية (15 يوم) أو اشتراك:**\n\n"
            f"📞 {VENDOR_PHONE}\n\n✉️ {VENDOR_EMAIL}\n\n---\n"
            "🔹 تجريبي: **مجاناً - 15 يوم**\n"
            "🔹 شهري: **200 جنيه**\n"
            "🔹 سنوي: **2000 جنيه** *(توفير 400 ج)*"
        )
        return False
    _stored = SUBSCRIBER_HASHES.get(email)
    if _stored:
        if not verify_password(password, _stored):
            _now_locked, _wait2, _left = _AUTH.record_failure(email, "bad password")
            if _now_locked:
                st.error(f"⛔ تم قفل المحاولات {_wait2 // 60} دقائق "
                         f"بعد {_AUTH.MAX_ATTEMPTS} محاولات خاطئة.")
            else:
                st.error(f"❌ كلمة المرور غير صحيحة ({_left} محاولة متبقية)")
            return False
    elif SUBSCRIBER_HASHES:
        # FIX 2026-08-01: this branch printed a warning and then FELL THROUGH,
        # returning True. The comment beneath it said "do not silently accept a
        # bare email while the rest of the estate is protected" -- which is
        # exactly what the code then did, minus the silence. Any account added
        # to `subscribers` without a matching entry in `subscriber_hashes` was a
        # password-free door into a paid product, and adding a subscriber
        # without a hash is the easy mistake to make.
        # Fail closed: once ANY account is protected, an unprotected one cannot
        # log in at all.
        st.error(
            "⛔ هذا الحساب غير مفعّل بكلمة مرور، والنظام يعمل بوضع "
            "الحماية الكاملة.\n\n"
            f"تواصل مع الدعم لتفعيله: 📞 {VENDOR_PHONE} | ✉️ {VENDOR_EMAIL}"
        )
        logger.error("login refused: %s exists in `subscribers` but has no "
                     "entry in `subscriber_hashes` while %d other account(s) "
                     "do. Add a hash for it with make_password_hash().",
                     email, len(SUBSCRIBER_HASHES))
        return False

    days_left = get_subscription_days_left(email)
    if days_left is None:
        st.error("خطأ في بيانات الاشتراك، تواصل مع الدعم")
        return False
    st.session_state.email     = email
    st.session_state.days_left = days_left
    # Credentials accepted: clear the account's counter and record the sign-in.
    _AUTH.record_success(email)
    if days_left < 0:
        st.error(f"⏳ انتهى اشتراكك منذ {abs(days_left)} يوم")
        st.info(f"📞 للتجديد: {VENDOR_PHONE} | ✉️ {VENDOR_EMAIL}")
        return False
    if days_left <= 3:
        st.warning(f"⚠️ اشتراكك ينتهي خلال **{days_left} يوم فقط**")
    elif days_left <= 7:
        st.info(f"ℹ️ متبقي **{days_left} أيام** على انتهاء الاشتراك")
    else:
        st.success(f"✅ أهلاً بك! الاشتراك ساري -- متبقي {days_left} يومًا")
    return True

def logout(reason: str = "تم تسجيل الخروج.") -> None:
    st.session_state.clear()
    st.session_state["logout_reason"] = reason
    st.rerun()

def handle_session_timeout() -> None:
    last_activity = st.session_state.get("last_activity")
    if last_activity:
        elapsed = time.time() - last_activity
        if elapsed > SESSION_TIMEOUT:
            logout("انتهت صلاحية الجلسة بسبب عدم النشاط. الرجاء تسجيل الدخول مرة أخرى.")
    st.session_state.last_activity = time.time()

def render_top_bar() -> None:
    left, right = st.columns([6, 1])
    with left:
        days = get_subscription_days_left(st.session_state.get("email", ""))
        st.session_state.days_left = days
        if days is None:
            # The account disappeared from the subscriber table mid-session
            # (revoked, refunded, typo-fixed). Access must stop immediately.
            logout("تم إنهاء الجلسة: الحساب لم يعد مسجلاً.")
        elif days < 0:
            # check_subscription() only runs at LOGIN. Without this branch an
            # expired subscription kept full access until the 30-minute idle
            # timeout happened to fire.
            logout(f"⏳ انتهى اشتراكك منذ {abs(days)} يوم. للتجديد: {VENDOR_PHONE}")
        if days is not None:
            if days <= 3:
                st.warning(
                    f"⚠️ اشتراك **{st.session_state.email}** سينتهي خلال **{days} يوم(أيام)** -- يُرجى التجديد قريبًا."
                )
            else:
                st.info(f"✅ اشتراك **{st.session_state.email}** سارٍ -- متبقي **{days}** يومًا.")
    with right:
        if st.button("تسجيل خروج", use_container_width=True):
            logout("تم تسجيل الخروج بنجاح.")

# =========================================================
# OCR
# =========================================================
def preprocess_image(file_bytes: bytes) -> Tuple[Any, Any]:
    ensure_ocr_dependencies()
    arr  = np.frombuffer(file_bytes, np.uint8)
    img  = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("تعذر قراءة الصورة. تأكد أن الملف صورة سليمة.")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=1.7, fy=1.7, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    gray = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11,
    )
    kernel = np.ones((1, 1), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
    return img, thresh

def run_ocr(thresh: Any) -> str:
    ensure_ocr_dependencies()
    configs = ["--psm 6", "--psm 11", "--psm 4"]
    outputs = []
    for cfg in configs:
        for lang in ["ara+eng", "eng"]:
            try:
                txt = pytesseract.image_to_string(thresh, lang=lang, config=cfg)
                txt = normalize_ocr_text(txt)
                if txt:
                    outputs.append(txt)
            except Exception:
                continue
    if not outputs:
        raise RuntimeError("OCR failed: no text extracted")
    return max(outputs, key=lambda x: len(re.sub(r"\s+", "", x)))

def detect_age(text: str) -> Optional[int]:
    r"""Age in YEARS from a report header. Returns 0 for anyone under one year.

    The previous version matched `Age[:\s]+(\d+)` before considering the unit,
    so every sub-year notation in common use was read as a number of YEARS:

        "Age: 6/12"        -> 6      (means 6 MONTHS in Egyptian, Indian and
                                      UK paediatric notation)
        "Age: 3 months"    -> None
        "Age: 20 days"     -> None

    Reading a six-month-old as a six-year-old bypasses every infant and neonatal
    gate in the engine at once -- ceftriaxone, TMP-SMX and nitrofurantoin all
    become ALLOWED for a patient with hard contraindications to all three. Units
    are therefore matched BEFORE the bare number, and `detect_age_months`
    supplies the precision the neonatal table needs.
    """
    # FIX 2026-11-11 (round 4): the unit patterns ran over the WHOLE report
    # first, so "growth after 2 days incubation" made a 45-year-old age 0. The
    # age is now read from the age field itself -- see
    # ocr_parsing.parse_patient_age for the rules and the history.
    from ocr_parsing import parse_patient_age
    return parse_patient_age(text)[0]



def detect_sex(text_lower: str) -> Optional[str]:
    """Robust sex detection — regex with word boundaries, Female checked first.
    Handles: 'sex: male/female', 'sex: m/f', 'sex=male', 'gender: ...', Arabic."""
    # Female first (avoids 'male' substring inside 'female')
    if (re.search(r'(?:sex|gender)\s*[:=]?\s*(?:female|f\b)', text_lower)
            or re.search(r'\bfemale\b', text_lower)
            or "أنثى" in text_lower or "انثى" in text_lower):
        return "Female"
    # Male: word boundary on 'male' so it won't fire on 'female'
    if (re.search(r'(?:sex|gender)\s*[:=]?\s*(?:male|m\b)', text_lower)
            or re.search(r'\bmale\b', text_lower)
            or "ذكر" in text_lower):
        return "Male"
    return None

# ─────────────────────────────────────────────────────────────────────────
# Canonical specimen classifier — SINGLE SOURCE OF TRUTH for all routing.
# Prevents the same specimen being bucketed differently by different engines
# (pathogenicity / severity / syndrome / treatment-duration).
# Keyword order encodes clinical priority — e.g. a "Rectal Swab" is GI (rectal)
# before it is a wound (swab); a "Tracheal aspirate" is respiratory (tracheal)
# before anything else.
# ─────────────────────────────────────────────────────────────────────────
_SPECIMEN_CATEGORY_RULES = [
    # (category, [keywords])  — checked top-to-bottom; FIRST HIT WINS, so the
    # order below is load-bearing: the generic "swab" keyword sits in the LAST
    # rule precisely so that "throat swab" and "nasopharyngeal swab" are claimed
    # by the respiratory rule above it. Before this fix "throat swab" fell into
    # 'wound', which routed an upper-respiratory isolate through soft-tissue
    # logic. Anything genuinely unrecognised still returns '' and every caller
    # must treat '' as fail-closed, never as "no restriction".
    ("blood",   ["blood culture", "blood", "bacteraem", "bacterem", "septicaem"]),
    ("csf",     ["csf", "cerebrospinal", "lumbar puncture", "نخاعي"]),
    ("urine",   ["urine", "mid-stream", "midstream", "msu", "catheter specimen", "بول"]),
    ("sputum",  ["sputum", "respiratory", "tracheal", "endotracheal", "bronch", "bal",
                 "throat", "pharyn", "nasopharyn", "tonsil", "بلغم", "حلق"]),
    ("stool",   ["stool", "fecal", "faecal", "feces", "faeces", "rectal", "براز"]),
    ("abdomen", ["abdomen", "abdominal", "periton", "ascit", "bile", "biliary"]),
    ("pus",     ["pus", "abscess", "empyema", "صديد", "خراج"]),
    ("wound",   ["wound", "tissue", "swab", "ulcer", "burn", "skin", "جرح", "مسحة"]),
]

def classify_specimen(specimen: str) -> str:
    """Return the canonical specimen category for any specimen string.

    One of: 'urine','sputum','blood','csf','stool','abdomen','pus','wound', or ''.
    Every routing engine dispatches on this so a given specimen is always
    bucketed identically.
    """
    s = (specimen or "").lower()
    for category, keywords in _SPECIMEN_CATEGORY_RULES:
        if any(k in s for k in keywords):
            return category
    return ""

_SPEC_CAT_TO_TYPE = {"urine": "Urine", "blood": "Blood", "sputum": "Sputum",
                     "wound": "Wound Swab", "pus": "Pus", "stool": "Stool", "csf": "CSF",
                     "abdomen": "Pus"}


def detect_specimen(text_lower: str) -> Optional[str]:
    """Specimen type from the OCR text.

    FIX 2026-11-11 (round 4): this returned the FIRST specimen name found
    anywhere in the text, in list order (Urine, Blood, Sputum, ...). Analyte
    lines name other specimens: a CSF report prints "RBCs (red blood cells)"
    and a stool report "occult blood", so both came back as BLOOD -- which
    then filtered the organism list and pre-selected a bloodstream workflow.
    Now: the labelled specimen field first, then "<x> culture", then the most
    specific words, with the analyte words ("blood", "pus") last.
    """
    t = str(text_lower or "").lower()

    def _typ(cat: str) -> Optional[str]:
        name = _SPEC_CAT_TO_TYPE.get(cat)
        return name if name in SPECIMEN_TYPES else None

    for m in re.finditer(r"(?:specimen|sample|type of specimen|نوع العينة|العينة)"
                         r"\s*(?:type)?\s*[:\-]\s*([^\n|]{2,40})", t):
        cat = classify_specimen(m.group(1))
        if cat and _typ(cat):
            return _typ(cat)
    m = re.search(r"(?<![a-z])(urine|blood|sputum|stool|csf|wound|pus|throat|tracheal|bal)"
                  r"\s*(?:culture|c\s*/\s*s|c\s*&\s*s)", t)
    if m:
        cat = classify_specimen(m.group(1))
        if cat and _typ(cat):
            return _typ(cat)
    for name, keys in (("CSF", ("csf", "cerebrospinal", "نخاعي")),
                       ("Stool", ("stool", "faec", "fecal", "براز")),
                       ("Sputum", ("sputum", "bronch", "tracheal", "بلغم")),
                       ("Urine", ("urine", "بول")),
                       ("Wound Swab", ("wound", "swab", "جرح", "مسحة")),
                       ("Blood", ("blood culture", "bacteraem", "bacterem", "bottle")),
                       ("Pus", ("abscess", "pus ", "صديد", "خراج")),
                       ("Blood", ("blood",))):
        if name in SPECIMEN_TYPES and any(k in t for k in keys):
            return name
    return None

# Spellings a laboratory actually prints, mapped to the profile key. Detection
# was plain containment of the PROFILE NAME, so a report saying "Escherichia
# coli" -- the full binomial, which is what most laboratories write -- matched
# nothing and the organism field came back empty. Since almost every downstream
# decision keys on the organism, an empty field silently disables intrinsic
# resistance, mechanism inference and MDR classification all at once.


def detect_organism(text_lower: str) -> Optional[str]:
    """Best-matching organism from OCR text, profile names AND lab spellings.

    Longest alias wins, so "escherichia coli" is not decided by the shorter
    "e. coli" fragment and "enterococcus faecium" is not swallowed by
    "enterococcus".
    """
    t = str(text_lower or "").lower()

    # FIX 2026-11-10: plain substring matching read "gas" inside "gastric" /
    # "gastroenteritis" as Group A Streptococcus and "cons" inside
    # "consistent" / "consultant" as CoNS. Every alias is now matched on
    # letter boundaries (digits and punctuation still count as a boundary).
    def _hits(needle: str) -> int:
        n = needle.lower()
        if not n:
            return 0
        return len(re.findall(r"(?<![a-z])" + re.escape(n) + r"(?![a-z])", t))

    counts: Dict[str, int] = {}
    for organism in BACTERIA_TYPES:
        c = _hits(organism)
        if c > 0:
            counts[organism] = counts.get(organism, 0) + c
    if not counts:
        for alias in sorted(ORGANISM_OCR_ALIASES, key=len, reverse=True):
            if _hits(alias):
                mapped = ORGANISM_OCR_ALIASES[alias]
                if mapped in ORGANISM_PROFILE:
                    return mapped
        return None
    return max(counts, key=counts.get)

def classify_sir_from_line(line: str) -> Optional[str]:
    """S/I/R from one printed AST line.

    Routed through normalize_sir_value() so the OCR reader and the engine cannot
    disagree about what a result means. Before this, the engine accepted SDD and
    NS while the OCR classifier returned None for both, and neither side
    understood the Arabic حساس / مقاوم / متوسط that bilingual reports print --
    so a resistant drug read from an Arabic report simply had no result at all.
    """
    ll = str(line or "").lower().strip()
    # Longest-first so "non-susceptible" is not read as "susceptible".
    for pat, token in (
        (r"(?:non[\s\-]?susceptible|not\s+susceptible)", "NS"),
        (r"(?:susceptible[\s\-]*dose[\s\-]*dependent|\bsdd\b)", "SDD"),
        (r"\b(?:sensitive|susceptible|sens)\b", "S"),
        (r"\b(?:resistant|resist)\b", "R"),
        (r"\b(?:intermediate|inter)\b", "I"),
        (r"\bns\b", "NS"),
        (r"(?:حسّاس|حساس)", "S"),
        (r"(?:مقاوم)", "R"),
        (r"(?:متوسط|متوسطة)", "I"),
    ):
        if re.search(pat, ll):
            return normalize_sir_value(token)
    tail = re.search(r"\b([sir])\b\s*$", ll)
    if tail:
        return tail.group(1).upper()
    return None

# ── Drug-name scanning: SPAN-CLAIMING, LONGEST-WINS ──────────────────────────
#  BUG FIXED (Acinetobacter / Sputum report): the old scanner tested plain
#  containment of every drug name in the raw OCR text. Because every combination
#  agent CONTAINS its own partner drug, one printed line manufactured several
#  phantom panel entries that were never tested:
#
#      "Ampicillin/Sulbactam"          -> also produced "Ampicillin"
#      "Amoxicillin + Clavulanic acid" -> also produced "Amoxicillin"
#      "Cefoperazone + Sulbactam"      -> also produced "Cefoperazone"
#      "Cefuroxime sodium"             -> also produced "Cefuroxime"
#      "Levofloxacin"                  -> also produced "Ofloxacin"  (!)
#
#  Those phantoms then hit INTRINSIC_RESISTANCE: for A. baumannii bare
#  Ampicillin / Amoxicillin ARE intrinsically resistant while the tested
#  Ampicillin/Sulbactam is NOT, so the report showed an intrinsic-resistance
#  alert for a drug that was never on the panel.
#
#  The fix scans the NORMALIZED text (same normalisation as the alias index, so
#  "+", "/", spaces and case never matter), longest alias first, and CLAIMS the
#  character span each match occupies. A shorter name that falls entirely inside
#  an already-claimed span is a fragment of the longer name, not a second drug.

# ═══════════════════════════════════════════════════════════════════════════
# CLSI / EUCAST DISK CODES  (added 2026-08-01)
# ---------------------------------------------------------------------------
# DEFECT THIS FIXES
# ABX_ALIAS_INDEX held 176 aliases, rich in Egyptian brand names (Augmentin,
# Curam, Unictam, Sigmaclav, Unasyn, Tazocin) and containing ZERO disk codes.
# VITEK, Phoenix and hand-read disk plates all label by code, so a report
# printed as "AMC  R / CIP  R / SXT  R / MEM  R" produced an EMPTY panel and
# nothing said so. Measured on a Pseudomonas isolate the same AST went from
# MDR (4/5 categories) to level=None -- the MDR alert disappeared entirely
# because half the panel was never parsed.
#
# WHY THIS IS NOT JUST MORE ALIASES
# Several codes are one or two letters: P (benzylpenicillin), E (erythromycin),
# DO (doxycycline), CN (gentamicin), TE (tetracycline), VA (vancomycin), AK
# (amikacin). Dropping those into ABX_ALIAS_INDEX would make them match inside
# ordinary words -- normalize_abx_key strips punctuation, so "Patient" contains
# "p" and "Date" contains "te". Every one of them would fire on the report
# header.
#
# So a code is honoured ONLY when it stands alone as a whole token AND the line
# also carries an S/I/R verdict. That is the shape of a result row and nothing
# else. A code appearing in prose has no verdict beside it and is ignored.
# ═══════════════════════════════════════════════════════════════════════════

# A result row must carry a verdict. Reuse the same vocabulary the value parser
# accepts so the two cannot drift.







@st.cache_data(show_spinner=False)
def detect_pus_cells(text: str) -> str:
    """
    Extract Pus cells / WBCs from OCR text.
    Handles: 6-8, 10-15, >10, Over 100, >100/HPF, TNTC, كثيرة
    """
    import re
    text_l = text.lower()

    # FIX (#O1): scope the generic qualifiers (>N / over N / TNTC / +++) to the
    # pus/WBC line when one is present, so a '>N' belonging to RBCs or the colony
    # count elsewhere in the report is not misread as the pus-cell value.
    _pus_line = ""
    for _ln in text_l.splitlines():
        # Round 5: "Leukocyte esterase: +++" is a dipstick line, not a cell
        # count -- it used to win over the real "Pus cells: 2-4" line below it
        # and came back as ">100". "Pus: 50-60" (no "cells") is accepted.
        if "esterase" in _ln:
            continue
        if re.search(r"pus\s*cells?|(?<![a-z])pus\s*[:=]|w\.?b\.?c|leu[ck]ocyt|صديد", _ln):
            _pus_line = _ln
            break
    # FIX 2026-11-11 (round 4): this used to fall back to the WHOLE report when
    # no pus/WBC line existed, and the generic qualifiers below then read the
    # culture section as microscopy -- "Colony count: >100,000 CFU/mL" became
    # pus cells ">100" and "Moderate growth of Klebsiella" became "10-20",
    # both fed to the pathogenicity score as pyuria the report never stated.
    # Without a labelled line there is no pus-cell value to qualify; only the
    # bare N/HPF fallback at the end (which has its own guards) may still run.
    if not _pus_line:
        if not re.search(r"r\.?\s*b\.?\s*c|red\s*b|erythro|cast|epithel|crystal|"
                         r"yeast|bacteri|حمراء|بلورات", text_l):
            for pat in (r"(\d+\s*[-–]\s*\d+)\s*/\s*hpf", r"(\d+)\s*/\s*hpf"):
                m = re.search(pat, text_l, re.IGNORECASE)
                if m:
                    return m.group(1).strip()
        return ""
    scope = _pus_line

    # Round 5: a NUMBER printed right after the label is the value. The verbal
    # qualifiers below used to be tried first over the whole line, so
    # "Pus cells 15-20 /HPF, many bacteria" came back as ">30" -- the word
    # belongs to the bacteria.
    _after = re.split(r"pus\s*cells?|(?<![a-z])pus(?=\s*[:=])|w\.?\s*b\.?\s*c\.?s?|"
                      r"leu[ck]ocytes?|صديد", scope, maxsplit=1)[-1]
    _m_num = re.match(r"(?:[\s:=\-–/().]|h\.?p\.?f\.?)*(\d+\s*[-–]\s*\d+|\d+)(?![\d,.]*\d)",
                      _after)
    if _m_num:
        return _m_num.group(1).strip()

    # ── Text qualifiers (check first, within scope) ──────────────────────────
    # ADDED 2026-08-03. This extractor and pathogenicity._parse_pus disagreed
    # about the same words: the SCORER resolved "full field", "loaded",
    # "plenty", "many", "occasional" to numbers, and this EXTRACTOR returned ""
    # for all of them — so the verbal readings never reached the scorer that
    # knew what to do with them. A microscopist writing "pus cells: full field",
    # the strongest pyuria on the form, produced no value at all.
    #
    # The vocabularies are now the same one, resolved to the same words, so a
    # change to _PUS_VERBAL cannot silently leave this function behind.
    if re.search(r"tntc|too\s+numerous|innumerable|uncountable"
                 r"|full\s*field|packed|loaded|مليء|حقل\s*كامل", scope):
        return "TNTC"
    if re.search(r"plenty|numerous|كثير", scope):
        return ">50"
    if re.search(r"\bmany\b|عديد", scope):
        return ">30"
    if re.search(r"\bmoderate\b|متوسط", scope):
        return "10-20"
    if re.search(r"occasional|\bfew\b|scanty|قليل", scope):
        return "1-3"
    if re.search(r"\bnil\b|\bnone\b|not\s*seen|absent|لا\s*يوجد", scope):
        return "0"
    m_over = re.search(r"over\s*(\d+)", scope)
    if m_over:
        return f"Over {m_over.group(1)}"
    m_gt = re.search(r">\s*(\d+)", scope)
    if m_gt:
        return f">{m_gt.group(1)}"
    if re.search(r"\+{3,}|كثير", scope):
        return ">100"

    # ── Numeric patterns (anchored to pus/wbc first) ─────────────────────────
    patterns = [
        r"pus(?:\s*cells?)?\s*[:\-]?\s*(\d+\s*[-–]\s*\d+|\d+)",
        r"wbcs?\s*[:\-]?\s*(\d+\s*[-–]\s*\d+|\d+)",
        r"(\d+\s*[-–]\s*\d+)\s*/\s*hpf",
        r"(\d+)\s*/\s*hpf",
    ]
    # Anchored patterns (1-2) may search the whole text: they carry their own
    # "pus cells" / "wbc" label. The bare /HPF patterns (3-4) MUST stay inside the
    # pus line, otherwise they pick up whichever analyte happens to be printed
    # first -- RBCs, casts, epithelial cells.
    for pat in patterns[:2]:
        m = re.search(pat, text_l, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    if _pus_line:
        for pat in patterns[2:]:
            m = re.search(pat, _pus_line, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        # "Pus cells / HPF    2-4" puts the unit before the value, so the
        # number-then-/HPF patterns miss it. Strip the label and the unit off the
        # pus line and take whatever number is left -- still confined to that line.
        _rest = re.sub(r"pus\s*cells?|w\.?\s*b\.?\s*c\.?s?|leu[ck]ocytes?|صديد",
                       " ", _pus_line, flags=re.IGNORECASE)
        _rest = re.sub(r"/?\s*h\.?p\.?f\.?|per\s+field|[:\-–]\s*$", " ", _rest,
                       flags=re.IGNORECASE)
        m = re.search(r"(\d+\s*[-–]\s*\d+|\d+)", _rest)
        if m:
            return m.group(1).strip()
        return ""

    # No pus/WBC label anywhere. Fall back to a bare "N/HPF" ONLY when the report
    # names no competing analyte -- otherwise the first /HPF figure in the report
    # belongs to something else and must not be reported as a pus-cell count.
    if not re.search(r"r\.?\s*b\.?\s*c|red\s*b|erythro|cast|epithel|crystal|"
                     r"yeast|bacteri|حمراء|بلورات", text_l):
        for pat in patterns[2:]:
            m = re.search(pat, text_l, re.IGNORECASE)
            if m:
                return m.group(1).strip()
    return ""

def detect_rbcs(text: str) -> str:
    """استخرج قيمة RBCs من نص OCR."""
    import re
    patterns = [
        r"rbcs?\s*[:\-]?\s*(\d+\s*[-–]\s*\d+|\d+)",
        r"red\s*blood\s*cells?\s*[:\-]?\s*(\d+\s*[-–]\s*\d+|\d+)",
        r"كريات\s*حمراء\s*[:\-]?\s*(\d+\s*[-–]\s*\d+|\d+)",
        r"erythrocytes?\s*[:\-]?\s*(\d+\s*[-–]\s*\d+|\d+)",
    ]
    text_l = text.lower()
    for pat in patterns:
        m = re.search(pat, text_l, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    # Handle text qualifiers for RBCs -- ONLY on a line that names red cells.
    # FIX 2026-11-11 (round 4): the old test ("TNTC somewhere, and the word
    # 'pus' not before it") turned "WBC: TNTC" / "Leucocytes: TNTC" into an RBC
    # value, and fired on any TNTC in a report with no pus label at all.
    for _ln in text_l.splitlines():
        if (re.search(r"tntc|too\s+numerous|full\s*field", _ln)
                and re.search(r"r\.?\s*b\.?\s*c|red\s*b|erythro|كريات\s*حمراء", _ln)
                and not re.search(r"pus|w\.?\s*b\.?\s*c|leu[ck]|صديد", _ln)):
            return "TNTC"
    # Fallback: find the /HPF line that actually NAMES red cells. Never guess by
    # position -- the old "second /HPF line" rule returned the pus-cell count as
    # RBCs whenever the RBC label was dotted (R.B.Cs), and fabricated a value from
    # the casts line on reports that had no RBC row at all.
    _RBC_LABEL = re.compile(r"r\.?\s*b\.?\s*c|red\s*b|erythro|كريات\s*حمراء|حمراء")
    _NOT_RBC   = re.compile(r"pus|w\.?\s*b\.?\s*c|leu[ck]|صديد|cast|epithel|crystal|"
                            r"bacteri|yeast|mucus|املاح|بلورات")
    hpf_lines = [l for l in text_l.splitlines() if "hpf" in l]
    _cands = [l for l in hpf_lines if _RBC_LABEL.search(l) and not _NOT_RBC.search(l)]
    if _cands:
        _rbc_l = _cands[0]
        m_ov = re.search(r"over\s*(\d+)|>\s*(\d+)", _rbc_l)
        if m_ov:
            n = m_ov.group(1) or m_ov.group(2)
            return f"Over {n}" if "over" in _rbc_l else f">{n}"
        m2 = re.search(r"(\d+\s*[-–]\s*\d+|\d+)", _rbc_l)
        if m2:
            return m2.group(1).strip()
    return ""


def detect_culture_condition(text: str) -> str:
    """استخرج نوع ظروف المزرعة: Aerobic / Anaerobic / Both."""
    import re
    text_l = text.lower()
    if re.search(r"both|aerobic\s*[&+]\s*anaerobic|anaerobic\s*[&+]\s*aerobic", text_l):
        return "Both (Aerobic + Anaerobic)"
    if re.search(r"anaerob", text_l):
        return "Anaerobic"
    if re.search(r"aerob", text_l):
        return "Aerobic"
    return ""


def extract_all_data_cached(file_bytes: bytes) -> Dict[str, Any]:
    _, thresh  = preprocess_image(file_bytes)
    full_text  = run_ocr(thresh)
    text_lower = full_text.lower()
    sir_map: Dict[str, str] = {}
    for line in full_text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Round 5 (2026-11-12): a line may carry more than one result (two
        # columns, "Sensitive to: a, b"). One verdict + the longest drug name
        # per line read "Amikacin Sensitive  Ciprofloxacin Resistant" as
        # Ciprofloxacin = S. See ocr_parsing.parse_result_line.
        for matched_abx, result in parse_result_line(line, classify_sir_from_line):
            # The same drug printed twice with different results is not
            # readable: keep the more resistant reading, never the S.
            _old = sir_map.get(matched_abx)
            if _old and _old != result:
                result = max(_old, result, key="SIR".index)
            sir_map[matched_abx] = result
    return {
        "patient": {
            "Name":     None,  # الاسم يُدخل يدوياً فقط
            "Age":      detect_age(full_text),
            # Months are extracted alongside years so an infant report can
            # pre-tick the under-one box instead of relying on the operator to
            # notice. Without it the OCR could read "Age: 6/12" correctly as
            # under one year and the form would still open on the adult branch.
            "AgeMonths": detect_age_months(full_text),
            "AgeAmbiguous": age_reading_is_ambiguous(full_text),
            "Sex":      detect_sex(text_lower),
            "Specimen": detect_specimen(text_lower),
            "Organism": detect_organism(text_lower),
        },
        "drugs":     extract_detected_drugs(full_text),
        "sir_map":   sir_map,
        "raw_text":  full_text,
        # ── New: Microscopy + Condition ──────────────────────────────────
        "pus_cells": detect_pus_cells(full_text),
        "rbcs":      detect_rbcs(full_text),
        "condition": detect_culture_condition(full_text),
    }

# =========================================================
# التحليل السريري
# =========================================================
def is_intrinsically_avoided(organism_type: str, drug_name: str, drug_info: Dict[str, Any],
                             return_source: bool = False):
    """True if the drug is on the organism's avoid list.

    With return_source=True: 'intrinsic' | 'profile' | None -- WHY it is avoided.

    2026-11-10: split out so the UI can say "intrinsic resistance" only when it
    is true. The ORGANISM_PROFILE avoid lists also hold "not recommended"
    entries (poor clinical efficacy despite in-vitro activity), and every one
    of them used to be shown to the physician as intrinsic resistance.
    """
    # ── FIX: authoritative EUCAST intrinsic-resistance table first ────────────
    # The per-organism ORGANISM_PROFILE["avoid"] list was incomplete for
    # P. aeruginosa (missing Doxycycline and the intrinsically-inactive
    # cephalosporins), so drugs like Doxycycline (reported I) leaked into
    # "Use with caution" and Cephalexin was mis-tagged via the beta-lactamase path
    # instead of being flagged as intrinsic. Checking INTRINSIC_RESISTANCE here
    # guarantees a name-level intrinsic hit routes straight to Avoid, and keeps
    # a single source of truth shared with MDR-stripping and mechanism inference.
    _org_l = (organism_type or "").lower().strip()
    for _org_key, _drug_list in INTRINSIC_RESISTANCE.items():
        # Same length guard as _remove_intrinsic_resistance -- without it an
        # unreadable organism name banned every drug that is intrinsic to ANY
        # organism in the table.
        if not _org_key:
            continue
        if (_org_key in _org_l or (len(_org_l) >= 4 and _org_l in _org_key)) \
                and drug_name in _drug_list:
            return "intrinsic" if return_source else True

    _prof = ORGANISM_PROFILE.get(organism_type) or {}
    # 2026-11-10: a class-wide avoid ("Cephalosporins" for MRSA) must not
    # catch the deliberate exception (Ceftaroline binds PBP2a).
    if drug_name in (_prof.get("avoid_exempt") or []):
        return None if return_source else False
    organism_avoid = _prof.get("avoid", [])
    d_low   = drug_name.lower()
    d_class = (drug_info or {}).get("class", "").lower()
    for avoid_item in organism_avoid:
        av_low = avoid_item.lower().strip()
        if av_low in d_low or d_low in av_low:
            return "profile" if return_source else True
        mapped = ORGANISM_AVOID_CLASS_MAP.get(av_low)
        if mapped and any(cls in d_class for cls in mapped):
            return "profile" if return_source else True
    return None if return_source else False

def build_banned_item(name: str, category: str, reason_short: str, reason_detail: str) -> Dict[str, str]:
    return {"name": name, "category": category,
            "reason_short": reason_short, "reason_detail": reason_detail}
# ═══════════════════════════════════════════════════════════════════════
# HEPATIC DOSING TABLE — defined here (not further down the file) because
# analyze_antibiotics() now ENFORCES it rather than merely annotating it.
# Keeping a table below its only consumer works by accident of module
# execution order; declaring it first makes the dependency explicit.
# ═══════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════
# NEONATAL / YOUNG-INFANT CONTRAINDICATIONS
# ----------------------------------------------------------------------
# `child_safe` in abx_guidelines.py is a single boolean covering the whole
# 0-17 range, so three agents with hard NEONATAL contraindications were
# returned as ALLOWED, with no flag at all, for a patient entered as age 0:
#
#   Ceftriaxone   -> bilirubin displacement (kernicterus) and fatal
#                    ceftriaxone-calcium precipitates in neonates
#   TMP-SMX       -> sulfonamide bilirubin displacement, <2 months
#   Nitrofurantoin-> haemolytic anaemia, immature erythrocyte enzymes
#
# The dashboard ALREADY collects `age_months` for under-1s and then throws it
# away (it only seeded the weight default). Threading it through makes the
# thresholds exact instead of banning the whole first year.
#
# Each entry: drug -> (limit_in_months, ban_or_warn, alternative, reason)
# ═══════════════════════════════════════════════════════════════════════
NEONATAL_RESTRICTIONS: Dict[str, Dict[str, Any]] = {
    "Ceftriaxone": {
        # WEB-VERIFIED 2026-08-03. The contraindication is TWO-PART, not one
        # age cutoff:
        #   (a) PREMATURE infants — contraindicated up to 41 weeks POSTMENSTRUAL
        #       age (gestational + chronological), which for a 28-week baby runs
        #       to roughly THREE months of chronological age;
        #   (b) TERM neonates (<= 28 days) who are hyperbilirubinaemic or who
        #       receive / are expected to receive IV calcium-containing fluids.
        # Mechanism: bilirubin displacement from albumin (kernicterus) and fatal
        # ceftriaxone-calcium precipitation.
        #
        # This engine holds chronological age only — there is no gestational-age
        # field — so a single postnatal rule cannot express (a). The month ban
        # covers the term neonate exactly; the preterm case is surfaced as a
        # caution through 3 months rather than silently missed, because a
        # 6-week-old ex-28-weeker is still within the contraindication and the
        # engine has no way to know it. Adding a gestational-age input would let
        # this become a hard rule.
        "months": 1, "action": "ban", "alt": "Cefotaxime",
        "preterm_caution_months": 3,
        "reason": ("🚫 يُمنع في حديثي الولادة (≤ 28 يوم): يزيح البيليروبين عن "
                   "الألبومين → خطر kernicterus، ويكوّن راسب قاتل مع محاليل "
                   "الكالسيوم الوريدية. البديل المباشر: Cefotaxime بنفس الطيف. "
                   "(FDA label / BNFc / AAP Red Book 33rd ed.)"),
        "preterm_reason": ("⚠️ **إن كان الرضيع خديجاً**: المنع يمتد حتى عمر ما بعد "
                           "الطمث 41 أسبوعاً (الحملي + الزمني) — أي قد يصل إلى ~3 "
                           "شهور زمنية لمولود 28 أسبوعاً. البرنامج لا يعرف عمر "
                           "الحمل، فتحقّق يدوياً قبل الوصف. وتجنّبه مطلقاً مع أي "
                           "محلول كالسيوم وريدي أو فرط بيليروبين. "
                           "(FDA label / AAP Red Book 33rd ed.)"),
    },
    "Trimethoprim/Sulfamethoxazole": {
        "months": 2, "action": "ban", "alt": "بيتا-لاكتام حسب الحساسية",
        "reason": ("🚫 يُمنع تحت شهرين: السلفوناميد يزيح البيليروبين عن "
                   "الألبومين → kernicterus. (BNFc / AAP Red Book)"),
    },
    "Nitrofurantoin": {
        "months": 3, "action": "ban", "alt": "Cephalexin أو Amoxicillin",
        "reason": ("🚫 يُمنع تحت 3 شهور: أنظمة إنزيمات كرات الدم الحمراء غير "
                   "ناضجة → أنيميا انحلالية. (BNFc / EMA)"),
    },
    "Ciprofloxacin": {
        "months": 1, "action": "warn", "alt": "",
        "reason": ("⚠️ في حديثي الولادة يُستخدم فقط لدواعٍ مهدِّدة للحياة "
                   "وبقرار استشاري."),
    },
}


# ═══════════════════════════════════════════════════════════════════════
# ENGINE 3 -- Hepatic Dosing (Child-Pugh A/B/C)
# BNF 2025 | Lexicomp 2025 | UpToDate 2025
# ═══════════════════════════════════════════════════════════════════════
HEPATIC_DOSING: Dict[str, Dict] = {
    # ── Keys match abx_guidelines.py drug names exactly for lookup to work ──
    # Drugs marked [MDR/REF only] not in active formulary -- kept for reference display.
    "Metronidazole":                 {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment (label) -- monitor for adverse effects"), "C": ("Reduce 50%","Child-Pugh C: reduce the dose by 50% (label)"), "note": "Extensive hepatic metabolism. FIX 2026-11-10: the level string 'Avoid/Reduce' contained 'avoid' and BANNED metronidazole in Child-Pugh C; the label halves the dose"},
    "Clindamycin":                   {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Caution","No fixed reduction -- half-life is prolonged in severe liver disease; monitor liver enzymes (label)"), "note": "Primary hepatic metabolism. FIX 2026-11-10: was 'Avoid' in Child-Pugh C; the label asks for monitoring, not avoidance"},
    "Rifampicin":                    {"A": ("Normal (no jaundice)","Normal if no jaundice"), "B": ("Max 8mg/kg/d","Max 8mg/kg/day; weekly LFTs"), "C": ("Avoid","Avoid -- hepatotoxic + CYP inducer"), "note": "Hepatotoxic + strong CYP inducer [MDR/REF only]"},
    "Erythromycin":                  {"A": ("Normal","No adjustment"), "B": ("Reduce 25%","Reduce dose by 25%"), "C": ("Reduce 50%","Reduce 50% or avoid"), "note": "Cholestatic hepatitis risk [MDR/REF only]"},
    "Ceftriaxone":                   {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment; max 2g/day"), "C": ("Max 2g/day","2g/day maximum -- biliary sludge risk"), "note": "Dual hepatic/renal elimination"},
    "Linezolid":                     {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Normal","No adjustment -- primarily renal"), "note": "No hepatic dose adjustment required"},
    "Vancomycin":                    {"A": ("Renal-based","AUC/MIC monitoring"), "B": ("Renal-based","AUC/MIC monitoring"), "C": ("Renal-based","AUC/MIC monitoring"), "note": "Primarily renal -- no hepatic adjustment"},
    "Ciprofloxacin":                 {"A": ("Normal","No adjustment"), "B": ("Caution","Use with caution"), "C": ("Caution","No dose adjustment established -- use with caution in severe impairment (label)"), "note": "Partial hepatic metabolism"},
    "Doxycycline":                   {"A": ("Normal","No adjustment"), "B": ("Caution","Use with caution"), "C": ("Avoid","Avoid in severe hepatic failure"), "note": "Biliary excretion pathway"},
    "Amoxicillin + Clavulanic acid": {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Avoid","Avoid -- Clavulanate-associated DILI risk"), "note": "Clavulanate linked to drug-induced liver injury"},
    "Piperacillin + Tazobactam":     {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Normal (renal)","No hepatic adjustment -- monitor renal"), "note": "Primarily renal elimination"},
    "Tigecycline":                   {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Reduce","100mg loading then 25mg q12h in Child-Pugh C (label; FIX 2026-11-10 — was 12.5mg)"), "note": "Biliary excretion -- adjust in severe impairment [MDR/REF only]"},
    "Colistin":                      {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Renal-based","Based on CrCl -- primarily renal"), "note": "Primarily renal elimination"},
    "Nitrofurantoin":                {"A": ("Normal","No adjustment"), "B": ("Caution","Use with caution"), "C": ("Avoid","Avoid in hepatic failure"), "note": "Cholestatic hepatitis risk"},
    "Chloramphenicol":               {"A": ("Caution","Use with caution"), "B": ("Avoid","Avoid"), "C": ("Avoid","Avoid -- gray syndrome risk"), "note": "Hepatic glucuronidation -- accumulates [MDR/REF only]"},
    "Trimethoprim/Sulfamethoxazole": {"A": ("Normal","No adjustment"), "B": ("Caution","Use with caution"), "C": ("Avoid","Avoid in severe hepatic failure"), "note": "Hepatic acetylation -- accumulates"},
    "Azithromycin":                  {"A": ("Normal","No adjustment"), "B": ("Caution","Monitor LFTs"), "C": ("Avoid","Avoid in severe hepatic failure"), "note": "Biliary excretion -- hepatic impairment increases exposure"},
    "Clarithromycin":                {"A": ("Normal","No adjustment"), "B": ("Caution","Use with caution"), "C": ("Avoid","Avoid -- accumulation + QT risk"), "note": "Hepatic CYP3A4 metabolism"},
    "Meropenem":                     {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Caution","No formal adjustment -- monitor clinically"), "note": "Minimal hepatic metabolism"},
    "Imipenem/Cilastatin":           {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Caution","No formal adjustment -- monitor seizure risk"), "note": "Minimal hepatic metabolism"},
    "Levofloxacin":                  {"A": ("Normal","No adjustment"), "B": ("Caution","Monitor LFTs"), "C": ("Caution","No formal adjustment -- primarily renal; monitor"), "note": "Partial hepatic metabolism -- primarily renal"},
    "Ofloxacin":                     {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Normal","No hepatic adjustment -- primarily renal"), "note": "Primarily renal elimination"},
    "Norfloxacin":                   {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Normal","No hepatic adjustment -- primarily renal"), "note": "Primarily renal elimination"},
    "Ertapenem":                     {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Normal","No hepatic adjustment required"), "note": "Primarily renal elimination"},
    "Ampicillin/Sulbactam":          {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Normal","No hepatic adjustment -- primarily renal"), "note": "Primarily renal elimination"},
    "Fosfomycin":                    {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Normal","No hepatic adjustment"), "note": "Primarily renal elimination"},
    "Cephalexin":                    {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Normal","No hepatic adjustment"), "note": "Primarily renal elimination"},
    "Gentamicin":                    {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Normal (renal)","Primarily renal -- no hepatic adjustment; monitor nephrotoxicity"), "note": "Primarily renal -- ototoxic + nephrotoxic"},
    "Amikacin":                      {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Normal (renal)","Primarily renal -- no hepatic adjustment; monitor nephrotoxicity"), "note": "Primarily renal -- ototoxic + nephrotoxic"},
    # ── COVERAGE GAP CLOSED ────────────────────────────────────────────────
    # These nine agents all carry hepatic_caution=True in abx_guidelines.py yet
    # had NO row here, so get_hepatic_recommendations() returned nothing for
    # them and a cirrhotic patient received no hepatic guidance at all on the
    # very drugs the formulary had already flagged as hepatically risky.
    "Tobramycin":                    {"A": ("Normal","No adjustment"), "B": ("Normal","No adjustment"), "C": ("Normal (renal)","Primarily renal -- no hepatic adjustment; monitor nephrotoxicity"), "note": "Primarily renal -- ototoxic + nephrotoxic"},
    "Moxifloxacin":                  {"A": ("Normal","No adjustment"), "B": ("Caution","Monitor LFTs; withdraw if transaminases rise"), "C": ("Avoid","CONTRAINDICATED in Child-Pugh C (EMA/FDA label) and if ALT/AST >5x ULN"), "note": "Hepatic metabolism with no renal escape route; highest fulminant-hepatitis signal of the fluoroquinolones"},
    "Gatifloxacin":                  {"A": ("Normal","No adjustment"), "B": ("Caution","Monitor LFTs and glucose"), "C": ("Avoid","Avoid -- hepatic metabolism plus dysglycaemia risk"), "note": "Hepatic metabolism; withdrawn in several markets for dysglycaemia"},
    "Tetracycline":                  {"A": ("Caution","Use with caution"), "B": ("Avoid","Avoid"), "C": ("Avoid","Avoid -- dose-related hepatotoxicity, microvesicular steatosis"), "note": "Fatal fatty liver reported with high/IV doses; the most hepatotoxic tetracycline"},
    "Minocycline":                   {"A": ("Normal","No adjustment"), "B": ("Caution","Monitor LFTs"), "C": ("Avoid","Avoid -- autoimmune hepatitis and DRESS reported"), "note": "Hepatic metabolism; idiosyncratic autoimmune hepatitis on prolonged use"},
    "Tinidazole":                    {"A": ("Normal","No adjustment"), "B": ("Reduce 50%","Reduce dose by 50%"), "C": ("Avoid","Avoid -- extensive CYP3A4 metabolism, accumulation"), "note": "Extensive hepatic metabolism (mirrors Metronidazole but longer half-life)"},
    "Oxacillin":                     {"A": ("Normal","No adjustment"), "B": ("Caution","Monitor LFTs; consider Cefazolin instead"), "C": ("Avoid","Avoid -- prefer Cefazolin (less hepatotoxic, equal MSSA efficacy)"), "note": "Dose-related cholestatic hepatitis, especially >8 g/day"},
    "Fusidic acid":                  {"A": ("Caution","Monitor LFTs"), "B": ("Avoid","Avoid"), "C": ("Avoid","Avoid -- biliary excretion, dose-dependent jaundice"), "note": "Biliary excretion; hyperbilirubinaemia and cholestasis are common, worse with statin co-administration"},
    "Cefoperazone":                  {"A": ("Normal","No adjustment"), "B": ("Caution","Max 4 g/day; monitor INR, give vitamin K"), "C": ("Avoid","Avoid -- max 2 g/day if unavoidable; biliary obstruction abolishes the main clearance route"), "note": "~70% biliary excretion; NMTT side chain causes hypoprothrombinaemia and bleeding"},
    "Cefoperazone + Sulbactam":      {"A": ("Normal","No adjustment"), "B": ("Caution","Max 4 g/day cefoperazone component; monitor INR, give vitamin K"), "C": ("Avoid","Avoid -- max 2 g/day if unavoidable"), "note": "~70% biliary excretion; NMTT side chain causes hypoprothrombinaemia and bleeding"},
}



# ═══════════════════════════════════════════════════════════════════════
# SIR NORMALISATION — the single entry point for every S/I/R value
# ----------------------------------------------------------------------
# Every engine in this file compares with `== "R"` / `in ("R","I")`. Nothing
# validated the values, and the interactive editor coerced anything it did not
# recognise straight to "S":
#
#     if cur not in sir_options: cur = "S"        <-- fail-OPEN
#
# so a lowercase "r", a trailing space, or the word "Resistant" arriving from
# OCR, a pasted table or a future JSON import made a RESISTANT drug come back
# ALLOWED. The Streamlit selectbox happens to constrain the values today, which
# is the only reason this has not fired in production; it is one import feature
# away from doing so.
#
# SDD (Susceptible-Dose Dependent) is a real CLSI M100 category -- cefepime vs
# Enterobacterales is the everyday example -- and was silently read as plain S,
# i.e. standard dosing for a result that explicitly requires a high-dose
# regimen. It maps to "I" so the existing increased-exposure warning fires.
#
# NS (non-susceptible) maps to R: it is the conservative direction and the only
# one that cannot cost a patient a failed therapy.
# ═══════════════════════════════════════════════════════════════════════






# ── Pregnancy status: canonicalise the enum ─────────────────────────────────
# abx_guidelines.py declares four distinct values -- Safe / Warn / Banned and,
# on Aztreonam alone, "Caution". Every consumer tested only for "Banned" and
# "Warn", so "Caution" fell through every branch and the drug reached a pregnant
# patient with no flag at all -- indistinguishable from Safe. An undocumented
# fourth value silently meaning "Safe" is exactly the drift a clinical table
# must not tolerate.
_PREG_ALIASES = {
    "SAFE": "Safe", "": "Safe", "NONE": "Safe",
    "WARN": "Warn", "CAUTION": "Warn", "WARNING": "Warn", "MONITOR": "Warn",
    "BANNED": "Banned", "CONTRAINDICATED": "Banned", "AVOID": "Banned",
}


# ═══════════════════════════════════════════════════════════════════════
# 2026-11-10 REVIEW FIXES live in therapy_rules.py (importable, so the
# AST-extraction harnesses can reach them -- see that module's docstring).
# ═══════════════════════════════════════════════════════════════════════
from therapy_rules import (                                      # noqa: E402
    CLINICAL_NOTE_REASONS, NOVEL_BL_AGENTS, CARBAPENEMASE_TYPE_OPTIONS,
    UTI_SYNDROME_OPTIONS, normalize_carbapenemase_type, resolve_uti_syndrome,
)


def validate_patient_context(age: int, sex: str, is_preg: bool,
                             cl_cr: float, age_months: Optional[int] = None
                             ) -> List[str]:
    """Contradictions in the patient inputs themselves.

    Nothing checked these. A pregnancy flag on a male patient, a negative age or
    an impossible creatinine clearance all ran to completion and silently
    reshaped the entire recommendation list -- the pregnancy flag alone bans
    thirteen agents. A clinical tool should say when its inputs cannot all be
    true at once.
    """
    problems: List[str] = []
    if is_preg and str(sex).strip().lower() in ("male", "ذكر", "m"):
        problems.append("⚠️ عُلِّم الحمل مع جنس «ذكر» — راجع بيانات المريض "
                        "(علامة الحمل وحدها تحظر 13 دواءً).")
    if is_preg and age is not None and 0 <= age < 10:
        problems.append(f"⚠️ عُلِّم الحمل مع عمر {age} سنة — راجع بيانات المريض.")
    if age is not None and age < 0:
        problems.append(f"⚠️ العمر المُدخَل سالب ({age}).")
    if age is not None and age > 120:
        problems.append(f"⚠️ العمر المُدخَل غير معقول ({age} سنة).")
    if age_months is not None and not (0 <= age_months <= 11):
        problems.append(f"⚠️ العمر بالشهور خارج النطاق 0–11 ({age_months}).")
    if cl_cr is not None and cl_cr < 0:
        problems.append(f"⚠️ تصفية الكرياتينين سالبة ({cl_cr:.0f}).")
    if cl_cr is not None and cl_cr > 250:
        problems.append(f"⚠️ تصفية الكرياتينين غير معقولة ({cl_cr:.0f} mL/min) — "
                        "راجع الوزن والكرياتينين المُدخَلين.")
    return problems


def preg_status_of(info: Dict[str, Any]) -> str:
    """Canonical Safe | Warn | Banned for one formulary entry.

    Unknown values fail CLOSED to "Warn": an unrecognised label must raise a
    flag, never suppress one.
    """
    raw = str(info.get("preg_status") or "").strip().upper()
    return _PREG_ALIASES.get(raw, "Warn")


# ═══════════════════════════════════════════════════════════════════════════
#  run_analysis() — THE PIPELINE AS ONE CALLABLE FUNCTION
# ═══════════════════════════════════════════════════════════════════════════
#  WHY THIS EXISTS
#  Until 2026-08-03 the whole decision pipeline lived INSIDE the Streamlit UI
#  block, and that block sits behind an OCR file upload. Line-tracing a full UI
#  run reached 12.8% of this file and touched NONE of analyze_antibiotics,
#  apply_safety_gate, detect_resistance_phenotypes or generate_report: without a
#  file there is no drug list, so the analysis never starts.
#
#  The consequence was not theoretical. A text replacement added `age_months=`
#  to two get_combination_therapy() calls that take no such parameter — a
#  TypeError on the combination panel and on PDF export — and all ten suites
#  stayed green, because every suite calls these functions DIRECTLY with correct
#  arguments and none of them walks the path the user walks.
#
#  This function is that path, minus Streamlit. It takes a Patient, an organism,
#  a specimen and an S/I/R map, and returns everything the UI renders. The UI
#  now calls it instead of inlining it, so a test can walk the same code the
#  clinician does — which is the only way the class of bug above gets caught.
#
#  It is deliberately PURE: no session_state, no widgets, no I/O. Everything it
#  needs arrives as arguments and everything it produces is returned.
# ═══════════════════════════════════════════════════════════════════════════
def run_analysis(
    patient: "Patient",
    organism: str,
    specimen: str,
    sir_map: Dict[str, str],
    drugs: Optional[List[str]] = None,
    *,
    apply_gate: bool = True,
    carbapenemase_type: Optional[str] = None,
    uti_syndrome: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full clinical pipeline and return every panel the UI shows.

    Returns a dict with: allowed / warned / banned / preg_warn / interactions,
    gate_report, phenotypes, mdr, mechanism, ranked, combinations, syndrome,
    duration, severity, patient_warnings.

    `carbapenemase_type` (KPC / OXA-48 / MBL, from NG-Test CARBA-5, Xpert or
    PCR) and `uti_syndrome` (cystitis / upper / None) were added 2026-11-10:
    without the first the engine cannot choose between the novel agents, and
    without the second it cannot tell a cystitis from a pyelonephritis.
    """
    drugs = list(drugs if drugs is not None else sir_map.keys())
    k = patient.as_kwargs()

    allowed, warned, banned, preg_warn, interactions = analyze_antibiotics(
        drugs, organism, specimen, k["age"], k["sex"], k["is_renal"],
        k["cl_cr"], k["is_preg"], k["is_hepatic"], k["current_meds"], sir_map,
        k["child_pugh"], k["age_months"],
        carbapenemase_type=carbapenemase_type, uti_syndrome=uti_syndrome,
        allergies=list(getattr(patient, "allergies", None) or []),
    )

    gate_report: Dict[str, Any] = {}
    if apply_gate and SAFETY_GATE_AVAILABLE:
        allowed, warned, banned, gate_report = apply_safety_gate(
            allowed, warned, banned,
            organism=organism, specimen=specimen, sir_map=sir_map,
            age_years=k["age"], age_months=k["age_months"],
            is_pregnant=k["is_preg"], cl_cr=k["cl_cr"], is_renal=k["is_renal"],
            is_hepatic=k["is_hepatic"], child_pugh=k["child_pugh"],
        )
        # 2026-11-11 (round 4): the pregnancy-caution bucket passes the same
        # terminal check -- it used to be the one list the gate never saw.
        if preg_warn:
            from safety_gate import gate_pregnancy_bucket
            preg_warn, banned, _pmoves = gate_pregnancy_bucket(
                preg_warn, banned,
                organism=organism, specimen=specimen,
                age_years=k["age"], age_months=k["age_months"],
                is_pregnant=k["is_preg"], cl_cr=k["cl_cr"], is_renal=k["is_renal"],
                is_hepatic=k["is_hepatic"], child_pugh=k["child_pugh"],
            )
            if _pmoves:
                gate_report.setdefault("moves", []).extend(_pmoves)
                _c = gate_report.setdefault("counts", {})
                _c["banned"] = len(banned)
                _c["preg_warn"] = len(preg_warn)
                _c["moved"] = len(gate_report["moves"])

    phenotypes = detect_resistance_phenotypes(organism, sir_map)
    mechanism = predict_esbl(organism, sir_map)
    mdr = classify_mdr(organism, sir_map)
    ranked = rank_sensitive_antibiotics(allowed, specimen, organism, sir_map, phenotypes)
    combinations = get_combination_therapy(
        phenotypes,
        is_pregnant=k["is_preg"], age_years=k["age"], age_months=k["age_months"],
        is_renal=k["is_renal"], cl_cr=k["cl_cr"], is_hepatic=k["is_hepatic"],
        organism=organism, carbapenemase_type=carbapenemase_type,
    )

    # FIX 2026-11-11 (round 4): this passed `cl_cr or 95`, so an UNKNOWN
    # clearance on a patient flagged renal -- and a measured clearance of 0 --
    # was read as a normal 95 ml/min and never made a UTI "complicated".
    # suggest_severity() resolves None itself (resolve_crcl), like every other
    # layer.
    severity = suggest_severity(specimen, k["age"], k["sex"], k["is_preg"],
                                k["is_renal"], k["cl_cr"])
    syndrome = get_infection_syndrome(specimen, organism, k["age"], k["is_preg"],
                                      sex=k["sex"])
    _syn_key = duration_syndrome_key(syndrome, uti_syndrome, specimen)
    duration = get_treatment_duration(
        specimen, organism, _syn_key, k["age"], k["sex"], k["is_renal"],
        phenotypes, severity.get("suggested", "moderate"),
    )

    # ── Which safety layers actually ran ────────────────────────────────────
    # ADDED 2026-08-05 after an import-failure injection: with safety_gate or
    # clinical_matrix unimportable, this function returned a full, confident
    # result set with gate_report={} and said nothing. The UI does raise a
    # "DEGRADED CLINICAL MODE" banner, but run_analysis() is the PUBLIC entry
    # point now — anything calling it programmatically, this project's own test
    # suites included, received un-gated recommendations that were
    # indistinguishable from gated ones.
    #
    # A result that skipped the terminal safety check must SAY SO in the result,
    # not only on a page the caller may never render. Callers can then refuse to
    # report, and a test can assert the gate ran.
    degraded = []
    if not SAFETY_GATE_AVAILABLE:
        degraded.append("safety_gate + clinical_matrix — no site-penetration "
                        "check and no host-state demotion were applied")
    elif apply_gate and not gate_report:
        degraded.append("safety_gate returned no report — the terminal check "
                        "may not have run")
    if not INTRINSIC_TABLE_OK:
        degraded.append("clinical_data — intrinsically inactive agents were NOT "
                        "filtered out and are NOT excluded from MDR counting")

    return {
        "allowed": allowed, "warned": warned, "banned": banned,
        "preg_warn": preg_warn, "interactions": interactions,
        "gate_report": gate_report, "phenotypes": phenotypes,
        "mechanism": mechanism, "mdr": mdr, "ranked": ranked,
        "combinations": combinations, "severity": severity,
        "syndrome": syndrome, "duration": duration,
        "patient_warnings": patient.validate(),
        # Empty on a healthy run. Non-empty means a safety layer did not run and
        # the result must not be reported as if it had.
        "degraded": degraded,
        "gate_applied": bool(apply_gate and SAFETY_GATE_AVAILABLE),
    }


def duration_syndrome_key(syndrome: Any, uti_syndrome: Optional[str], specimen: str) -> str:
    """The syndrome string the duration engine dispatches on.

    ONE place for it (2026-11-11, round 4). run_analysis() turned an "upper"
    UTI into "pyelonephritis" before asking for a duration, but the on-screen
    Treatment Duration panel and the PDF each asked again with the bare
    syndrome label ("Urinary Tract Infection (UTI)"). A clinician who picked
    "pyelonephritis / cUTI" in the sidebar therefore saw nitrofurantoin and
    fosfomycin removed by the engine and, in the panel below, the 5-day
    uncomplicated-cystitis course (nitrofurantoin 5 d | fosfomycin single dose).
    """
    key = syndrome.get("syndrome", "") if isinstance(syndrome, dict) else str(syndrome or "")
    if (str(uti_syndrome or "").lower() in ("upper", "pyelonephritis", "urosepsis")
            and classify_specimen(specimen) == "urine"):
        return "pyelonephritis"
    return key


def warned_note_for(item: Dict[str, Any], lang: str = "ar") -> str:
    """The explanation that belongs to THIS warning, in the caller's language.

    DEFECT THIS FIXES (2026-08-01, fourth pass)
    The warned-item renderer was two branches:

        if warning_reason in ("esbl_bli_uti_only", "possible_carbapenemase"):
            show item["esbl_note"]
        else:
            show item["renal_note"]          # <- everything else landed here

    Every warned item carries `**info` spread from ABX_GUIDELINES, and every
    ABX_GUIDELINES row has a `renal_note`. So the else branch never printed an
    empty string -- it printed a CONFIDENT, WELL-FORMATTED, WRONG note:

      * Child-Pugh C warning on Ciprofloxacin rendered
        "CrCl <30: خفض الجرعة 50%…" -- renal dosing for a patient whose
        kidneys are fine and whose liver is failing.
      * A safety-gate demotion of Oxacillin in MENINGITIS rendered
        "🟢 لا تعديل كلوي مطلوب" -- actively reassuring, at the moment the gate
        had just refused the drug for not crossing the blood-brain barrier.
      * Neonatal warnings rendered adult renal dosing.

    Wrong text is worse than no text: a blank line invites the reader to look
    further, a fluent irrelevant sentence does not.

    The real explanation was present the whole time under a per-reason key --
    gate_note, hepatic_level/hepatic_rec, reason_short/reason_detail -- and
    nothing read it. This resolver is the single place that knows which key
    belongs to which reason.

    Returns "" only when the item genuinely carries no explanation, which the
    render layer surfaces explicitly rather than printing a blank bullet.
    """
    # 2026-11-10: an item can carry a second, independent fact (a novel-agent
    # note, an organism caution, a CLSI breakpoint restriction) under
    # `clinical_note` while its primary warning_reason is something else --
    # renal dosing, say. It is appended so neither fact hides the other.
    def _primary() -> str:
        if not isinstance(item, dict):
            return ""
        ar = (lang or "ar").lower().startswith("ar")

        def pick(*keys) -> str:
            for k in keys:
                v = item.get(k)
                if v and str(v).strip():
                    return str(v).strip()
            return ""

        reason = item.get("warning_reason") or ""
        category = item.get("category") or ""

        if reason in ("esbl_bli_uti_only", "possible_carbapenemase"):
            return pick("esbl_note", "esbl_note_en") if ar else pick("esbl_note_en", "esbl_note")

        if reason == "hepatic_adjustment":
            lvl, rec = item.get("hepatic_level"), item.get("hepatic_rec")
            if lvl or rec:
                head = f"🫀 Child-Pugh: {lvl}" if lvl else "🫀 قصور كبدي"
                body = f" — {rec}" if rec else ""
                extra = pick("hepatic_note", "hepatic_note_en")
                return f"{head}{body}" + (f"  \n{extra}" if extra else "")
            return pick("hepatic_note", "hepatic_note_en")

        if reason == "renal_adjustment":
            return pick("renal_note", "renal_note_en") if ar else pick("renal_note_en", "renal_note")

        if reason == "possible_mrsa":
            return pick("possible_mrsa_note")

        if reason == "safety_gate":
            return pick("gate_note", "gate_note_en") if ar else pick("gate_note_en", "gate_note")

        if reason == "neonate" or category == "neonate":
            short, detail = pick("reason_short"), pick("reason_detail")
            return f"{short}  \n{detail}" if short and detail else (short or detail)

        if reason == "intermediate_culture":
            if not ar:
                return ("Result is Intermediate (I) - EUCAST: susceptible, increased exposure. "
                        "Use only at the higher dose / extended infusion and after excluding a "
                        "susceptible (S) alternative.")
            return ("النتيجة Intermediate (I) — حسب EUCAST تعني حساسية عند تعرّض أعلى: "
                    "لا تُستخدم إلا بجرعة أعلى/تسريب ممتد وبعد استبعاد بديل حسّاس (S).")

        if reason == "interaction" or category == "interaction":
            return pick("interaction_note", "reason_detail", "reason_short")

        if reason == "pregnancy" or category == "pregnancy":
            return pick("preg_note", "preg_note_en", "reason_detail", "reason_short")

        # Warnings added by the 2026-11-10 review fixes carry their explanation
        # under ONE key, `clinical_note` (literal set: this function is lifted
        # by name into bare test namespaces, so it must not depend on a global).
        if reason in ("novel_agent", "organism_caution", "allergy", "uti_upper",
                      "aminoglycoside_pseudomonas", "colistin", "penicillinase_unconfirmed",
                      "no_breakpoint", "ampc_sdd", "ampc_cefepime"):
            if not ar:
                return (pick("clinical_note_en")
                        or "Clinical caution applies to this agent for this organism / site - review before use.")
            return pick("clinical_note", "reason_detail", "reason_short")

        # Unknown reason: try every explanation slot that exists before giving up,
        # and NEVER fall back to renal_note -- that silent substitution is the whole
        # defect this function replaces.
        return pick("reason_short", "reason_detail", "gate_note", "esbl_note",
                    "hepatic_rec", "note")

    base = _primary()
    _en_mode = not (lang or "ar").lower().startswith("ar")
    extra = str(item.get("clinical_note_en" if _en_mode else "clinical_note") or "").strip() \
        if isinstance(item, dict) else ""
    if extra and extra not in base:
        return f"{base}  \n{extra}" if base else extra
    return base


def analyze_antibiotics(
    final_drugs: List[str],
    organism_type: str,
    culture_type: str,
    age: int,
    sex: str,
    is_renal: bool,
    cl_cr: Optional[float],
    is_preg: bool,
    is_hepatic: bool,
    current_meds: List[str],
    sir_map: Dict[str, str],
    child_pugh: str = "C",
    age_months: Optional[int] = None,
    *,
    carbapenemase_type: Optional[str] = None,
    uti_syndrome: Optional[str] = None,
    allergies: Optional[List[str]] = None,
) -> Tuple[List[Dict], List[Dict], List[Dict], List[Dict], List[str]]:
    # child_pugh defaults to the WORST grade on purpose. If the caller knows the
    # grade it passes it; if it does not, the engine must not silently assume the
    # mildest liver disease and hand back agents that are contraindicated in
    # decompensated cirrhosis. Fail-closed, never fail-permissive.
    #
    # cl_cr is Optional. None means "no creatinine was measured", NOT "normal".
    # resolve_crcl() substitutes ASSUMED_CRCL_UNKNOWN (30 ml/min) when the renal
    # flag is set, and every message below that quotes the number says whether it
    # was measured or assumed. Passing 100.0 for "unknown" — which is what the
    # sidebar used to do — silently disabled the entire renal pathway.
    # 2026-11-10 review rules -- imported here, not at module level, so the
    # AST-extraction harnesses that exec this function in a bare namespace
    # still resolve them (see therapy_rules.py).
    from therapy_rules import (NOVEL_BL_AGENTS, novel_agent_verdict as _novel_agent_verdict,
                               normalize_carbapenemase_type, allergy_profile as _allergy_profile,
                               carb_tx_text as _carb_tx_text)
    _crcl, _crcl_measured = resolve_crcl(cl_cr, is_renal)
    _crcl_src = ("" if _crcl_measured else
                 " (CrCl مفترضة — لم يُقَس الكرياتينين؛ أدخِله لضبط الجرعة)")
    # Drugs that WERE on the panel but whose result could not be read. They must
    # not fall through to the untested-drug path, which would present them as
    # ordinary options.
    _unreadable = {str(d or "").strip() for d, v in (sir_map or {}).items()
                   if normalize_sir_value(v) is None and str(d or "").strip()}
    sir_map = normalize_sir_map(sir_map)
    # final_drugs is built from the RAW panel keys upstream, so it carries the
    # same OCR padding the map does. Trim here as well, or a drug whose name
    # arrived as " Ciprofloxacin " matches no formulary entry and disappears from
    # the report entirely -- neither recommended nor banned.
    current_meds = list(current_meds or [])
    _seen = set()
    final_drugs = [d for d in (str(x or "").strip() for x in (final_drugs or []))
                   if d and not (d in _seen or _seen.add(d))]
    allowed:            List[Dict] = []
    warned:             List[Dict] = []
    banned:             List[Dict] = []
    preg_warn_items:    List[Dict] = []
    interactions_alerts: List[str] = []

    # ── Detect resistance mechanism ONCE (drives beta-lactam suppression) ──────
    # ESBL -> resistant to ALL penicillins + cephalosporins (+ aztreonam),
    #        even if AST reports S (inoculum effect; EUCAST/CLSI report-as-tested
    #        but clinically carbapenem is required for serious infection).
    # Carbapenemase -> also resistant to carbapenems.
    _mech = predict_esbl(organism_type, sir_map) if sir_map else {}
    _mech = _mech or {}
    _mech_prob = _mech.get("probability")
    _is_esbl_like   = _mech_prob in ("high", "ampc", "ampc_plasmid")
    # CONFIRMED only (>=2 carbapenems R). A single carbapenem R or Meropenem I is
    # "possible_carbapenemase": it still raises the alert and asks for mCIM/PCR,
    # but it must NOT ban agents the AST reports as active -- that turned a 55%
    # suspicion into a full beta-lactam lockdown.
    _is_carbapenemase = _mech_prob == "carbapenemase"
    _is_possible_carb = _mech_prob == "possible_carbapenemase"
    _carb_type = normalize_carbapenemase_type(carbapenemase_type)
    _mech_label = ("Carbapenemase" if _is_carbapenemase
                   else "AmpC" if _mech_prob in ("ampc", "ampc_plasmid") else "ESBL")
    _allergy = _allergy_profile(allergies)
    # (level, note, reason) applied AFTER the loop, so a note never pre-empts a
    # hard ban that a later branch (pregnancy, renal, hepatic) would apply.
    _post_notes: Dict[str, Tuple[str, str, str]] = {}

    def _add_note(_d: str, _lvl: str, _txt: str, _rsn: str) -> None:
        """Merge, never overwrite: an allergy caution must survive a later
        novel-agent note on the same drug. 'warn' beats 'allow'; the reason of
        the first WARNING is kept as the primary one; texts are joined."""
        if _d not in _post_notes:
            _post_notes[_d] = (_lvl, _txt, _rsn)
            return
        _ol, _ot, _or = _post_notes[_d]
        _nl = "warn" if "warn" in (_ol, _lvl) else "allow"
        _nr = _or if (_ol == "warn" or _lvl != "warn") else _rsn
        _post_notes[_d] = (_nl, _ot if _txt in _ot else f"{_ot}  \n{_txt}", _nr)
    _spec_cat_aa = classify_specimen(culture_type)
    _uti_upper = (_spec_cat_aa == "urine" and str(uti_syndrome or "").lower()
                  in ("upper", "pyelonephritis", "urosepsis"))

    # ── Detect MRSA from AST markers (Oxacillin/Cefoxitin R), not just name ────
    # A S. aureus with Oxacillin-R or Cefoxitin-R IS MRSA -> ALL beta-lactams fail
    # (except anti-MRSA cephalosporins like Ceftaroline, not in this formulary).
    _org_l_aa = (organism_type or "").lower()
    _is_staph = ("staphylococcus" in _org_l_aa or "staph" in _org_l_aa
                 or _org_l_aa == "mrsa" or _org_l_aa == "mssa")
    # MRSA detection: AST markers + organism name + free-text report markers
    _mrsa_text_markers = (
        "mrsa screen positive" in _org_l_aa
        or "pbp2a positive" in _org_l_aa
        or "pbp2a" in _org_l_aa
        or "methicillin resistant" in _org_l_aa
        or "methicillin-resistant" in _org_l_aa
    )
    _mrsa_marker_R = (sir_map.get("Oxacillin") == "R"
                      or sir_map.get("Cefoxitin") == "R"
                      or _org_l_aa == "mrsa"
                      or _mrsa_text_markers)
    _is_mrsa = _is_staph and _mrsa_marker_R

    # ── "Possible MRSA": the panel carries no oxacillin and no cefoxitin ──────
    # DEFECT 2026-08-03. detect_resistance_phenotypes() already raised
    # "Possible MRSA -- تأكيد مطلوب" for exactly this pattern (S. aureus, a
    # beta-lactam R, vancomycin or linezolid S) — and this engine knew nothing
    # about it, because _is_mrsa requires an oxacillin or cefoxitin R that the
    # panel never carried. So on a S. aureus BACTERAEMIA the phenotype panel
    # said "possible MRSA, confirm with cefoxitin/mecA" while the column beside
    # it recommended Ceftriaxone and Meropenem.
    #
    # The response is deliberately CAUTION, not a ban. "Possible" is not
    # "confirmed": a heuristic inference must not fabricate a diagnosis and
    # strip every beta-lactam from a patient who may have plain MSSA. But a
    # beta-lactam must not sit in the green column either while the screen
    # says the isolate may be methicillin-resistant. Demote and say why.
    _possible_mrsa = False
    if _is_staph and not _is_mrsa:
        _vanco_s = sir_map.get("Vancomycin") == "S"
        _linez_s = sir_map.get("Linezolid") == "S"
        _bl_r = any(sir_map.get(d) == "R" for d in
                    ("Amoxicillin + Clavulanic acid", "Cephalexin", "Cefuroxime"))
        _possible_mrsa = _bl_r and (_vanco_s or _linez_s)

    def _cls_and_name(info_dict: Dict, drug_name: str = "") -> str:
        """Class text PLUS drug name, lower-cased, for robust matching.

        Matching on the class string alone silently mis-sorted any drug whose
        class was phrased differently from the token being searched for.
        """
        c = (info_dict.get("class") or "").lower()
        n = (drug_name or info_dict.get("name") or "")
        return f"{c} | {str(n).lower()}"

    _BLI_TOKENS = ("bli", "tazobactam", "sulbactam", "clavulan", "avibactam",
                   "relebactam", "vaborbactam", "inhibitor")

    def _is_penicillin_or_ceph(info_dict: Dict, drug_name: str = "") -> bool:
        """True for the beta-lactams an ESBL / AmpC hydrolyses.

        FIX 2026-08-01: the token list was penicillin / cephalosporin / cillin /
        cef / ceph. Aztreonam's class string is "Monobactam (IV)" and its name
        contains none of those substrings, so it matched NOTHING -- while the
        docstring of this very function's caller states that an ESBL is
        "resistant to ALL penicillins + cephalosporins (+ aztreonam)". A
        confirmed-ESBL Klebsiella bacteraemia therefore came back with
        Aztreonam in the RECOMMENDED bucket, and the terminal safety gate did
        not catch it either. Aztreonam is an oxyimino beta-lactam -- it is the
        classic ESBL substrate and CLSI uses it as an ESBL screening agent.
        """
        t = _cls_and_name(info_dict, drug_name)
        if "carbapenem" in t or "penem" in t:
            return False
        if any(k in t for k in _BLI_TOKENS):
            return False   # BLI combos handled separately (UTI-only caution)
        return any(k in t for k in ("penicillin", "cephalosporin", "cephalosporins",
                                    "cillin", "cef", "ceph",
                                    "monobactam", "aztreonam"))

    def _is_bli_combo(info_dict: Dict, drug_name: str = "") -> bool:
        t = _cls_and_name(info_dict, drug_name)
        if "carbapenem" in t or "relebactam" in t or "vaborbactam" in t:
            return False          # carbapenem/BLI pairs handled by _is_carbapenem
        return any(k in t for k in _BLI_TOKENS)

    def _is_carbapenem(info_dict: Dict) -> bool:
        return "carbapenem" in info_dict.get("class", "").lower()

    for drug in final_drugs:
        if drug not in ABX_GUIDELINES:
            continue
        if drug in _unreadable:
            banned.append(build_banned_item(
                drug, "unreadable",
                "نتيجة الحساسية غير مقروءة.",
                f"{drug}: القيمة المسجّلة في اللوحة ليست S أو I أو R. لا يمكن "
                "تفسيرها، ولا يجوز افتراض أنها حساسة. أعد إدخال النتيجة يدوياً.",
            ))
            continue
        info           = ABX_GUIDELINES[drug]
        d_low          = drug.lower()
        cls            = info.get("class", "").lower()
        culture_result = sir_map.get(drug)

        if culture_result == "R":
            banned.append(build_banned_item(
                drug, "resistant", "مقاوم (R) في نتيجة المزرعة.",
                f"المزرعة أثبتت أن {drug} لا يثبط نمو الجرثومة. MIC أعلى من الحد العلاجي -> خطر فشل علاجي.",
            ))
            continue

        _declared = {_canon_med(x) for x in (info.get("interacts_with") or [])}
        for med in current_meds:
            if _canon_med(med) in _declared:
                interactions_alerts.append(f"⚡ تعارض: {drug} مع {med}")
        if is_hepatic and info.get("hepatic_caution"):
            interactions_alerts.append(f"🏥 تحذير كبدي: {drug} — يحتاج متابعة أو تعديل حسب الحالة.")

        # ── Drug allergy (2026-11-10). Patient.allergies existed and nothing
        # read it. A documented allergy is a hard stop for the class itself;
        # cross-reactive classes are cautions with the real numbers.
        _cn = _cls_and_name(info, drug)
        # Sulbactam-durlobactam is a beta-lactam but not an aminopenicillin:
        # it gets the cross-reactivity caution, not the class ban.
        _is_pen = (any(k in _cn for k in ("penicillin", "cillin")) or "sulbactam" in _cn) \
            and "cephalosporin" not in _cn and "cef" not in d_low \
            and "durlobactam" not in d_low
        _is_ceph = "cephalosporin" in _cn or d_low.startswith("cef") or d_low.startswith("ceph")
        _is_carb = "carbapenem" in _cn or "penem" in d_low
        _allergy_ban = None
        if _allergy["penicillin"] and _is_pen:
            _allergy_ban = "حساسية مسجّلة للبنسلين."
        elif _allergy["cephalosporin"] and _is_ceph:
            _allergy_ban = "حساسية مسجّلة للسيفالوسبورينات."
        elif _allergy["sulfa"] and ("sulfamethox" in d_low or "sulfonamide" in cls):
            _allergy_ban = "حساسية مسجّلة للسلفوناميد."
        elif _allergy["fluoroquinolone"] and "fluoroquinolone" in cls:
            _allergy_ban = "حساسية مسجّلة للفلوروكينولونات."
        elif _allergy["macrolide"] and "macrolide" in cls:
            _allergy_ban = "حساسية مسجّلة للماكروليدات."
        if _allergy_ban:
            banned.append(build_banned_item(
                drug, "allergy", _allergy_ban,
                f"{drug}: {_allergy_ban} لا يُعطى نفس الصنف. راجع نوع التفاعل السابق "
                "(تأقي فوري أم طفح متأخر) قبل اختيار البديل."))
            continue
        if _allergy["penicillin"] and (_is_ceph or _is_carb or "durlobactam" in d_low):
            _add_note(drug, "warn", (
                "حساسية بنسلين: التفاعل المتصالب مع الكاربابينيم < 1%، ومع "
                "السيفالوسبورينات ذات السلاسل الجانبية المختلفة منخفض. "
                + ("الحساسية مسجّلة كشديدة/فورية — يُعطى تحت مراقبة أو بعد استشارة حساسية."
                   if _allergy["penicillin_severe"] else
                   "مع تاريخ طفح خفيف غير فوري يُعطى عادة بأمان.")), "allergy")
        elif _allergy["cephalosporin"] and (_is_pen or _is_carb):
            _add_note(drug, "warn", "حساسية سيفالوسبورين: تفاعل متصالب منخفض — راجع السلسلة الجانبية للدواء المسبب.", "allergy")
        elif _allergy["ceftazidime"] and "aztreonam" in d_low:
            _add_note(drug, "warn", "Aztreonam يشارك Ceftazidime نفس السلسلة الجانبية — تفاعل متصالب ممكن.", "allergy")

        _avoid_src = is_intrinsically_avoided(organism_type, drug, info, return_source=True)
        if _avoid_src == "intrinsic":
            banned.append(build_banned_item(
                drug, "organism",
                f"غير فعال لـ {organism_type} طبيعياً.",
                f"{drug} لديه مقاومة طبيعية أو عدم فعالية ضد {organism_type}.",
            ))
            continue
        if _avoid_src == "profile":
            # FIX 2026-11-10: a profile "avoid" is a CLINICAL recommendation,
            # not intrinsic resistance, and must not be worded as one.
            banned.append(build_banned_item(
                drug, "organism",
                f"غير موصى به لـ {organism_type}.",
                f"{drug}: مدرج في قائمة التجنّب السريرية لهذا الكائن (ملف الكائن). "
                "ليس مقاومة جوهرية — راجع الملاحظة الخاصة بالكائن.",
            ))
            continue

        # ── MRSA: ALL beta-lactams (penicillins + cephalosporins) fail ────────
        # Detected from AST (Oxacillin/Cefoxitin R) OR organism name = MRSA.
        # Exception: carbapenems also fail for MRSA but are caught here too.
        #
        # FIX 2026-08-01: the filter read ONLY the class string, for the tokens
        # penicillin / cephalosporin / carbapenem. Amoxicillin + Clavulanic acid
        # is classed "Beta-lactamase Inhibitor Combination" -- none of the three
        # -- so it escaped and reached the CAUTION bucket, while every other BLI
        # combo (Amp-Sulbactam, Pip-Tazo, Cefoperazone-Sulbactam) was caught
        # only because its class text happens to spell out "Penicillin" or
        # "Cephalosporin". Worse, the same isolate typed as "MRSA" rather than
        # "Staphylococcus aureus + Oxacillin-R" got Amox-Clav BANNED by the
        # intrinsic table -- two different verdicts for one organism, decided by
        # how the technologist spelled the name.
        # mecA/PBP2a is an ALTERED TARGET, not a beta-lactamase: no inhibitor
        # rescues any beta-lactam. Match on class AND name, and include the
        # inhibitor tokens.
        # FIX 2026-11-10: Ceftaroline binds PBP2a and is THE anti-MRSA
        # cephalosporin; the "cef" token banned it on every MRSA.
        if _is_mrsa and drug != "Ceftaroline" and any(k in _cls_and_name(info, drug)
                            for k in ("penicillin", "cephalosporin", "carbapenem",
                                      "cillin", "cef", "ceph", "penem",
                                      "monobactam", "aztreonam", *_BLI_TOKENS)):
            banned.append(build_banned_item(
                drug, "organism", "بيتا-لاكتام -- لا يعمل على MRSA.",
                "MRSA يحمل جين mecA (PBP2a) -> مقاوم لكل البيتا-لاكتام (البنسلينات، "
                "السيفالوسبورينات التقليدية، والكاربابينيمات) حتى لو أظهرت المزرعة حساسية. "
                "العلاج: Vancomycin / Linezolid / Daptomycin (حسب الموقع والحساسية).",
            ))
            continue

        # Unconfirmed MRSA: caution, never silent approval. See _possible_mrsa.
        if _possible_mrsa and drug != "Ceftaroline" and any(k in _cls_and_name(info, drug)
                                  for k in ("penicillin", "cephalosporin",
                                            "carbapenem", "cillin", "cef",
                                            "ceph", "penem", *_BLI_TOKENS)):
            _w = {"name": drug, **info,
                  "warning_reason": "possible_mrsa",
                  "possible_mrsa_note": (
                      "⚠️ **اشتباه MRSA غير مؤكَّد.** اللوحة لا تحتوي Oxacillin "
                      "ولا Cefoxitin، والنمط (بيتا-لاكتام مقاوم + Vancomycin/"
                      "Linezolid حسّاس) يوحي بمقاومة الميثيسيلين. لو كانت MRSA "
                      "فكل البيتا-لاكتام سيفشل بغض النظر عن نتيجة القرص "
                      "(mecA/PBP2a هدف مُعدَّل وليس إنزيماً).\n"
                      "**قبل استخدام أي بيتا-لاكتام:** اطلب Cefoxitin disk أو "
                      "PCR (mecA). في تجرثم الدم ابدأ بـ Vancomycin تجريبياً "
                      "حتى يظهر التأكيد.")}
            warned.append(_w)
            continue

        # ── Novel beta-lactams / BLIs (2026-11-10) ─────────────────────────────
        # Judged on their OWN activity, never by the old-beta-lactam mechanism
        # bans below (see _novel_agent_verdict for the defect this closes).
        _skip_mech = False
        if drug in NOVEL_BL_AGENTS:
            _nv, _nn = _novel_agent_verdict(drug, organism_type, _mech, _carb_type, sir_map)
            if _nv == "ban":
                banned.append(build_banned_item(drug, "organism", _nn[:170], _nn))
                continue
            _add_note(drug, _nv, _nn, "novel_agent")
            _skip_mech = True

        # ── P. aeruginosa + aminoglycosides (CLSI M100 Ed33, 2023) ────────────
        # CLSI eliminated gentamicin as a treatment option for P. aeruginosa
        # (suppress or report R) and limited amikacin to urinary isolates.
        if "pseudomonas" in _org_l_aa and drug == "Gentamicin":
            banned.append(build_banned_item(
                drug, "no_breakpoint",
                "CLSI 2023: Gentamicin لم يعد خياراً ضد P. aeruginosa.",
                "CLSI M100 Ed33 (2023) ألغى Gentamicin كخيار علاجي لـ P. aeruginosa "
                "(أقصى MIC يحقق التثبيط 0.5 µg/mL، أقل بكثير من الـ ECV). "
                "يُحجب من التقرير أو يُبلَّغ R. البديل من نفس الصنف: Tobramycin."))
            continue
        if ("pseudomonas" in _org_l_aa and drug == "Amikacin"
                and _spec_cat_aa != "urine"):
            _add_note(drug, "warn", (
                "CLSI M100 Ed33: breakpoints الأميكاسين لـ P. aeruginosa على عزلات البول فقط. "
                "خارج البول لا يُستخدم الأمينوجليكوزيد إلا في توليفة مع بيتا-لاكتام فعّال."),
                "aminoglycoside_pseudomonas")

        # ── Organism-specific clinical cautions (2026-11-10) ──────────────────
        # Not intrinsic resistance: an agent that tests S and works, but whose
        # use depends on the infection (e.g. a 3rd-gen cephalosporin against a
        # moderate-risk AmpC organism, IDSA AMR Guidance 2026).
        # The mechanism blocks below still run: an ESBL/carbapenemase verdict
        # is stronger than an organism caution and must not be skipped.
        _prof_aa = ORGANISM_PROFILE.get(organism_type) or {}
        _pcaut = _prof_aa.get("caution") or {}
        if drug in _pcaut and culture_result in ("S", "I"):
            # IDSA 2026: for AmpC organisms the 3rd-gen caution is about
            # INVASIVE infection -- in uncomplicated cystitis the S agent is
            # reasonable, so it stays recommended with the note attached.
            _cyst = (_spec_cat_aa == "urine" and not _uti_upper
                     and "AmpC" in str(_pcaut[drug]))
            _add_note(drug, "allow" if _cyst else "warn", _pcaut[drug], "organism_caution")
        _pnote = (_prof_aa.get("agent_notes") or {}).get(drug)
        if _pnote and culture_result in ("S", "I", None):
            _add_note(drug, "allow", _pnote, "organism_note")

        # ── Colistin: no S category, BMD only (CLSI M100 / EUCAST) ───────────
        if drug == "Colistin" and culture_result in ("S", "I"):
            _add_note(drug, "warn", (
                "Colistin: لا توجد فئة S في CLSI (I ≤ 2 / R ≥ 4 µg/mL) والاختبار بـ broth "
                "microdilution فقط — نتيجة القرص أو الشريط غير صالحة. دواء Reserve يُستخدم في "
                "توليفة مع مراقبة الكلى، و IDSA لا تفضّله لـ CRE أو DTR-PA عند توفر بديل حديث."),
                "colistin")

        # ── Oral fosfomycin outside E. coli (CLSI / EUCAST) ───────────────────
        if (drug == "Fosfomycin" and culture_result in ("S", "I")
                and not any(k in _org_l_aa for k in ("e. coli", "escherichia", "e.coli",
                                                     "enterococcus faecalis"))):
            _add_note(drug, "warn", (
                "Fosfomycin الفموي: breakpoints في CLSI و EUCAST لـ E. coli (و E. faecalis في "
                "CLSI) فقط. Klebsiella تحمل fosA كروموسومياً — النتيجة هنا غير مُعايَرة."),
                "no_breakpoint")

        # ── Penicillin-S S. aureus needs a negative penicillinase test ────────
        if (drug in ("Penicillin", "Ampicillin", "Amoxicillin") and culture_result == "S"
                and ("staph" in _org_l_aa or "mssa" in _org_l_aa)):
            _bz = str(sir_map.get("Penicillinase") or sir_map.get("Beta-lactamase")
                      or sir_map.get("blaZ") or "").strip().upper()
            if _bz != "NEGATIVE":
                _add_note(drug, "warn", (
                    "Penicillin = S في Staphylococcus يحتاج تأكيد سلبية البنسليناز (zone-edge "
                    "أو nitrocefin أو blaZ PCR) قبل الاعتماد عليه — CLSI M100."),
                    "penicillinase_unconfirmed")

        # ── Beta-haemolytic streptococci + TMP-SMX (CLSI M100 Ed36) ───────────
        if (("trimethoprim" in d_low or "sulfamethox" in d_low)
                and any(k in _org_l_aa for k in ("streptococcus pyogenes",
                                                 "streptococcus agalactiae"))):
            if _spec_cat_aa not in ("wound", "pus"):
                banned.append(build_banned_item(
                    drug, "no_breakpoint",
                    "CLSI 2026: breakpoints لعدوى الجلد فقط.",
                    "CLSI M100 Ed36 أضاف breakpoints لـ TMP-SMX مع المكورات الحالّة بيتا "
                    "لعدوى الجلد والأنسجة الرخوة فقط — لا تُبلَّغ في البلعوم أو البول أو الدم."))
                continue
            _add_note(drug, "warn", "CLSI M100 Ed36: مقبول لعدوى الجلد والأنسجة الرخوة فقط.",
                                 "no_breakpoint")

        # ══════════════════════════════════════════════════════════════════
        # ROUND-2 RULES (2026-11-10) -- results that test S but must not be
        # reported as a treatment option, each from a CLSI M100 comment.
        # ══════════════════════════════════════════════════════════════════
        _is_staph_r2 = any(k in _org_l_aa for k in ("staph", "mrsa", "mssa"))
        _is_strep_r2 = "strep" in _org_l_aa or "pneumoc" in _org_l_aa
        _is_entero_r2 = "enterococc" in _org_l_aa or _org_l_aa.strip() == "vre"
        _is_pneumo_r2 = "pneumoniae" in _org_l_aa and "strep" in _org_l_aa

        # ── Macrolides: erythromycin predicts azithromycin / clarithromycin ──
        # CLSI M100 Table 1 footnote: "susceptibility and resistance to
        # azithromycin and clarithromycin can be predicted by testing
        # erythromycin" (staphylococci, streptococci). erm / mef are shared.
        if (drug in ("Azithromycin", "Clarithromycin") and culture_result in ("S", "I")
                and sir_map.get("Erythromycin") == "R"
                and (_is_staph_r2 or _is_strep_r2)):
            banned.append(build_banned_item(
                drug, "cross_resistance",
                "Erythromycin R ← مقاومة متصالبة لكل الماكروليدات.",
                f"{drug} ظهر حساساً بينما Erythromycin = R. في المكورات العنقودية والعقدية "
                "نتيجة Erythromycin تتنبأ بـ Azithromycin و Clarithromycin (CLSI M100، "
                "آلية erm/mef مشتركة) — النتيجة تُعامل كمقاومة ويُراجَع الاختبار."))
            continue

        # ── Enterococci ───────────────────────────────────────────────────────
        if _is_entero_r2 and culture_result in ("S", "I"):
            # Fluoroquinolones: CLSI lists them for URINARY isolates only.
            if "fluoroquinolone" in cls and _spec_cat_aa != "urine":
                banned.append(build_banned_item(
                    drug, "no_breakpoint",
                    "CLSI: الفلوروكينولون مع Enterococcus للبول فقط.",
                    "CLSI M100 يدرج Ciprofloxacin/Levofloxacin مع المكورات المعوية لعزلات "
                    "البول فقط (Group U) — لا تُبلَّغ ولا تُستخدم في الدم أو الجروح أو غيرها. "
                    "البديل: Ampicillin إن كان حساساً، وإلا Vancomycin / Linezolid / Daptomycin."))
                continue
            # Meropenem / ertapenem: no enterococcal breakpoints, unreliable.
            if drug in ("Meropenem", "Ertapenem", "Meropenem + Vaborbactam"):
                banned.append(build_banned_item(
                    drug, "no_breakpoint",
                    "لا breakpoints لهذا الكاربابينيم مع Enterococcus.",
                    f"{drug}: لا توجد breakpoints في CLSI أو EUCAST مع المكورات المعوية ونشاطه "
                    "غير موثوق (Ertapenem بلا نشاط). Imipenem فقط يُتنبأ به من Ampicillin "
                    "في E. faecalis."))
                continue
            # Ampicillin R predicts the other penicillins and imipenem.
            if (sir_map.get("Ampicillin") == "R"
                    and drug in ("Penicillin", "Amoxicillin", "Amoxicillin + Clavulanic acid",
                                 "Ampicillin/Sulbactam", "Piperacillin + Tazobactam",
                                 "Imipenem/Cilastatin", "Imipenem + Relebactam")):
                banned.append(build_banned_item(
                    drug, "cross_resistance",
                    "Ampicillin R ← مقاومة متوقعة لهذا البيتا-لاكتام.",
                    f"{drug} ظهر حساساً بينما Ampicillin = R. في Enterococcus نتيجة Ampicillin "
                    "تتنبأ بـ Amoxicillin و Amoxicillin-clavulanate و Ampicillin-sulbactam و "
                    "Piperacillin-tazobactam و Imipenem (CLSI M100) — تُعامل كمقاومة."))
                continue

        # ── S. pneumoniae in CSF: meningitis breakpoints have no "I" ─────────
        if _is_pneumo_r2 and _spec_cat_aa == "csf" and culture_result == "I":
            if drug in ("Penicillin", "Ampicillin", "Amoxicillin"):
                banned.append(build_banned_item(
                    drug, "no_breakpoint",
                    "التهاب السحايا: Penicillin غير الحساس = مقاوم.",
                    "breakpoints التهاب السحايا لـ S. pneumoniae (CLSI M100): S ≤ 0.06 و "
                    "R ≥ 0.12 µg/mL — لا توجد فئة Intermediate. النتيجة I تُعامل كمقاومة: "
                    "Ceftriaxone/Cefotaxime بجرعة عالية + Vancomycin حتى ظهور الـ MIC."))
                continue
            if drug in ("Ceftriaxone", "Cefotaxime"):
                _add_note(drug, "warn", (
                    "التهاب السحايا بـ S. pneumoniae مع Ceftriaxone/Cefotaxime = I "
                    "(MIC 1 µg/mL): لا يكفي منفرداً — أضف Vancomycin (IDSA Bacterial "
                    "Meningitis)."), "organism_caution")

        # ── S. aureus bacteraemia / CNS: no fluoroquinolone monotherapy ──────
        if (_is_staph_r2 and "fluoroquinolone" in cls and culture_result in ("S", "I")
                and _spec_cat_aa in ("blood", "csf")):
            _add_note(drug, "warn", (
                "Staphylococcus في الدم/CSF: الفلوروكينولون منفرداً غير موصى به (مقاومة تظهر "
                "أثناء العلاج) — الخيار: Cefazolin أو Oxacillin (MSSA) / Vancomycin أو "
                "Daptomycin (MRSA)."), "organism_caution")

        # ── ESBL "moderate" = not excluded: say so on the beta-lactams ───────
        if (_mech_prob == "moderate" and culture_result in ("S", "I")
                and not (_spec_cat_aa == "urine" and not _uti_upper)
                and drug not in NOVEL_BL_AGENTS and "carbapenem" not in cls
                and ("cephalosporin" in cls
                     or drug in ("Piperacillin + Tazobactam", "Aztreonam",
                                 "Amoxicillin + Clavulanic acid", "Ampicillin/Sulbactam"))):
            _add_note(drug, "warn", (
                "ESBL غير مستبعد (مقاومة سيفالوسبورين بلوحة محدودة): في العدوى الغازية لا "
                "يُعتمد على هذا البيتا-لاكتام قبل نفي ESBL (اختبر Ceftriaxone/Ceftazidime أو "
                "DDST) — الكاربابينيم أضمن (IDSA AMR Guidance 2026)."), "organism_caution")

        # ── AmpC + Cefepime (IDSA AMR Guidance 2024 / 2026) ───────────────────
        # FIX 2026-11-10: AmpC was routed through the ESBL branch below and
        # cefepime was demoted with an "ESBL ... avoid in bacteraemia" note.
        # IDSA suggests cefepime for moderate/high-risk AmpC organisms when the
        # isolate is susceptible; an SDD/I result raises the possibility of a
        # co-produced ESBL, and then a carbapenem is preferred.
        if (not _skip_mech and _mech_prob in ("ampc", "ampc_plasmid")
                and drug == "Cefepime" and culture_result in ("S", "I")):
            if culture_result == "S":
                _add_note(drug, "allow", (
                    "AmpC: Cefepime ثابت أمام AmpC وهو الخيار المقترح للعدوى الغازية "
                    "(IDSA 2026) طالما النتيجة S (MIC ≤ 2)."), "ampc_cefepime")
            else:
                _add_note(drug, "warn", (
                    "AmpC مع Cefepime SDD/I: احتمال ESBL مرافق — فضّل الكاربابينيم في "
                    "العدوى الغازية (IDSA 2026)."), "ampc_sdd")
            _skip_mech = True

        # ── Mechanism-driven beta-lactam handling (rewritten 2026-11-10) ──────
        # R is already handled above; here the drug is S / I / untested.
        # EUCAST v16 / CLSI: report AS TESTED -- an S result is never edited to R.
        # What changes with the mechanism is the TREATMENT recommendation, and
        # that depends on the mechanism and on the site:
        #   ESBL  : IDSA 2026 -- carbapenem for invasive infection; TMP-SMX / FQ
        #           preferred for pyelonephritis/cUTI, pip-tazo an alternative
        #           for cUTI; a beta-lactam that tests S is acceptable for cystitis.
        #           MERINO (2018) is ESBL bacteraemia evidence only.
        #   AmpC  : cefepime (S) is the suggested agent -- handled above; 3rd-gen
        #           cephalosporins and pip-tazo are not suggested for invasive
        #           infection (selection of derepressed mutants).
        #   Carbapenemase (confirmed): every old beta-lactam is avoided; the
        #           definitive agent depends on the enzyme class.
        # The previous text cited MERINO and recommended a carbapenem for AmpC,
        # and recommended "Colistin / Ceftazidime-Avibactam" for every
        # carbapenemase -- wrong for MBL, and colistin is not preferred.
        _urine_lower = (_spec_cat_aa == "urine" and not _uti_upper)
        if _mech_prob in ("ampc", "ampc_plasmid"):
            _invasive_tx = ("Cefepime إذا كانت النتيجة S (MIC ≤ 2)، وإلا Carbapenem "
                            "(IDSA 2026 — AmpC)")
            _invasive_why = ("AmpC: الـ 3rd-gen cephalosporins و Pip-Tazo غير مقترحة للعدوى الغازية "
                             "لخطر انتقاء طفرات مُفرِطة الإنتاج أثناء العلاج")
        else:
            _invasive_tx = "Carbapenem (Meropenem / Ertapenem)"
            _invasive_why = ("ESBL: البيتا-لاكتام الحساس معملياً أقل موثوقية في العدوى الغازية "
                             "(inoculum effect؛ MERINO 2018 لتجرثم الدم)")

        # Cefepime + ESBL (IDSA AMR 2024/2026): not suggested for pyelonephritis,
        # cUTI or bloodstream infection even when S; acceptable for cystitis.
        # FIX 2026-11-10: was WARNED on blood while S pip-tazo on the same blood
        # culture was BANNED -- the weaker agent got the softer verdict.
        if (not _skip_mech and _is_esbl_like and not _is_carbapenemase
                and _mech_prob not in ("ampc", "ampc_plasmid")
                and drug == "Cefepime" and culture_result in ("S", "I")):
            if _urine_lower:
                _wc = dict(info)
                _wc["warning_reason"] = "esbl_bli_uti_only"
                _wc["esbl_note"] = (
                    "كائن ESBL: Cefepime حسّاس معملياً ويُبلَّغ كما هو. مقبول لالتهاب المثانة البسيط "
                    "فقط. غير مقترح لالتهاب الحويضة أو cUTI أو تجرثم الدم (IDSA 2026).")
                _wc["esbl_note_en"] = (
                    "ESBL organism: cefepime is susceptible and reported as tested. Acceptable "
                    "for uncomplicated cystitis only; not suggested for pyelonephritis, cUTI "
                    "or bacteraemia (IDSA AMR Guidance 2026).")
                warned.append({"name": drug, **_wc})
                continue
            banned.append(build_banned_item(
                drug, "organism", "ESBL: Cefepime غير مقترح لهذه العدوى (IDSA 2026).",
                "كائن منتج لـ ESBL: Cefepime غير مقترح لالتهاب الحويضة أو cUTI أو تجرثم الدم "
                "حتى مع الحساسية المعملية (IDSA AMR Guidance 2026). تُبلَّغ النتيجة كما هي. "
                + ("البديل في البول العلوي: TMP-SMX أو Ciprofloxacin/Levofloxacin إذا كانت حساسة، وإلا Carbapenem."
                   if _spec_cat_aa == "urine" else f"البديل: {_invasive_tx}.")))
            continue

        if (not _skip_mech and _is_possible_carb and _is_penicillin_or_ceph(info, drug)
                and culture_result in ("S", "I")):
            _w = dict(info)
            _w["warning_reason"] = "possible_carbapenemase"
            _w["esbl_note"] = (
                "⚠️ يوجد اشتباه في كاربابينيميز (كاربابينيم واحد فقط R أو "
                "Meropenem I) — والاشتباه **ليس** تأكيداً؛ النمط قد يكون فقد "
                "بورين مع ESBL/AmpC. هذا الدواء حسّاس معملياً ويُبلَّغ كما هو "
                "(EUCAST v16). أكّد بـ mCIM أو PCR قبل التصعيد، وفي العدوى "
                "الشديدة فضّل الكاربابينيم أو استشر الأمراض المعدية."
            )
            _w["esbl_note_en"] = (
                "Carbapenemase is SUSPECTED (a single carbapenem R, or meropenem I) - a "
                "suspicion, not a confirmation; porin loss with ESBL/AmpC gives the same "
                "pattern. This agent tests susceptible and is reported as such (EUCAST v16). "
                "Confirm with mCIM or PCR before escalating; in severe infection prefer a "
                "carbapenem or seek infectious-diseases advice."
            )
            warned.append({"name": drug, **_w})
            continue

        if (not _skip_mech and (_is_esbl_like or _is_carbapenemase)
                and _is_penicillin_or_ceph(info, drug)):
            if (not _is_carbapenemase and culture_result in ("S", "I") and _urine_lower):
                _w = dict(info)
                _w["warning_reason"] = "esbl_bli_uti_only"
                _w["esbl_note"] = (
                    f"كائن {_mech_label}: هذا البيتا-لاكتام حسّاس معملياً -- يُبلَّغ **كما هو** "
                    "(EUCAST v16؛ لا تُحوّل الحساس إلى R). خيار ممكن لالتهاب المثانة البسيط فقط "
                    "(المفضّل: Nitrofurantoin أو TMP-SMX؛ Fosfomycin لـ E. coli). تجنّبه في "
                    f"التهاب الحويضة وتجرثم الدم -- {_invasive_tx}."
                )
                _w["esbl_note_en"] = (
                    f"{_mech_label} organism: this beta-lactam is susceptible in vitro -- report "
                    "it AS TESTED (EUCAST v16). An option for uncomplicated cystitis only "
                    "(preferred: nitrofurantoin or TMP-SMX; fosfomycin for E. coli). Avoid in "
                    "pyelonephritis and bacteraemia (IDSA AMR Guidance 2026)."
                )
                warned.append({"name": drug, **_w})
                continue
            if _is_carbapenemase:
                banned.append(build_banned_item(
                    drug, "organism", "غير مُوصى به -- كائن منتج لـ Carbapenemase.",
                    "الكائن منتج لـ Carbapenemase: لا يُعتمد على البنسلينات أو السيفالوسبورينات "
                    "التقليدية حتى لو ظهرت حساسة. العلاج النهائي: " + _carb_tx_text(_carb_type) + "."))
            else:
                banned.append(build_banned_item(
                    drug, "organism", f"غير مُوصى به -- كائن منتج لـ {_mech_label}.",
                    f"الكائن منتج لـ {_mech_label}. الحساسية المعملية تُبلَّغ كما هي، لكن "
                    f"{_invasive_why}. الخيار العلاجي: {_invasive_tx}."))
            continue

        # ── Carbapenemase: also suppress carbapenems ──────────────────────────
        if not _skip_mech and _is_carbapenemase and _is_carbapenem(info):
            banned.append(build_banned_item(
                drug, "organism",
                "غير فعّال -- كائن منتج لـ Carbapenemase.",
                "الكائن منتج لإنزيم Carbapenemase: لا يُعتمد على الكاربابينيم منفرداً. "
                "العلاج النهائي: " + _carb_tx_text(_carb_type) + ".",
            ))
            continue

        # ── BLI combinations (Amox-Clav, Amp-Sulb, Pip-Tazo, Cefop-Sulb) ──────
        # A *suspicion* of carbapenemase: warn and ask for confirmation, never
        # ban (pip-tazo is the more robust agent against the porin-loss/AmpC
        # phenotype that most often explains an isolated ertapenem R).
        if (not _skip_mech and _is_possible_carb
                and not (_is_esbl_like or _is_carbapenemase)
                and _is_bli_combo(info, drug) and culture_result in ("S", "I")):
            _w = dict(info)
            _w["warning_reason"] = "possible_carbapenemase"
            if not _urine_lower:
                _w["esbl_note"] = (
                    "⛔ لا تستخدمه كعلاج نهائي منفرد في هذه العينة. اشتباه كاربابينيميز "
                    "غير مؤكد (كاربابينيم واحد R أو Meropenem I). "
                    "التوليفة حسّاسة معملياً وتُبلَّغ كما هي (EUCAST v16). "
                    "ابدأ بالكاربابينيم وأكّد بـ mCIM أو PCR، ولا تنزل لهذه التوليفة إلا "
                    "بعد نفي الإنزيم واستشارة الأمراض المعدية."
                )
                _w["esbl_note_en"] = (
                    "DO NOT use as definitive monotherapy for this specimen. Unconfirmed "
                    "carbapenemase suspicion. Susceptible in vitro and reported as tested "
                    "(EUCAST v16). Start a carbapenem, confirm with mCIM/PCR, and de-escalate "
                    "only once the enzyme is excluded and ID has been consulted."
                )
            else:
                _w["esbl_note"] = (
                    "⚠️ اشتباه كاربابينيميز غير مؤكد (كاربابينيم واحد R أو Meropenem I). "
                    "هذه التوليفة حسّاسة معملياً وتُبلَّغ كما هي (EUCAST v16). خيار مقبول "
                    "لالتهاب المثانة البسيط عند ثبوت الحساسية؛ أكّد بـ mCIM أو PCR."
                )
                _w["esbl_note_en"] = (
                    "Unconfirmed carbapenemase suspicion. Susceptible in vitro and reported "
                    "as tested (EUCAST v16). Acceptable for uncomplicated cystitis when proven "
                    "S; confirm with mCIM or PCR."
                )
            warned.append({"name": drug, **_w})
            continue

        if (not _skip_mech and (_is_esbl_like or _is_carbapenemase)
                and _is_bli_combo(info, drug)):
            _is_pt = "piperacillin" in d_low
            if _is_carbapenemase:
                banned.append({**info, **build_banned_item(
                    name=drug, category="organism",
                    reason_short="Carbapenemase -- المثبط التقليدي غير كافٍ.",
                    reason_detail=("Tazobactam و Sulbactam و Clavulanate لا تثبّط الكاربابينيميز. "
                                   "العلاج النهائي: " + _carb_tx_text(_carb_type) + "."))})
                continue
            # cUTI / pyelonephritis: IDSA AMR Guidance 2026 lists pip-tazo as an
            # ALTERNATIVE for ESBL-E cUTI (TMP-SMX / FQ preferred); not amox-clav.
            if (_spec_cat_aa == "urine" and _uti_upper and _is_pt
                    and culture_result in ("S", "I")):
                _w = dict(info)
                _w["warning_reason"] = "esbl_bli_uti_only"
                _w["esbl_note"] = (
                    (f"كائن {_mech_label} + التهاب حويضة / cUTI: Pip-Tazo بديل مقبول (IDSA 2026) "
                     "بجرعة 4.5 g q6h وتسريب ممتد، والمفضّل TMP-SMX أو Ciprofloxacin/Levofloxacin إذا كانت "
                     "حساسة. في حالة الصدمة أو تجرثم الدم: Carbapenem.")
                    if _mech_label == "ESBL" else
                    ("AmpC + التهاب حويضة: Cefepime (إذا S) مقدَّم على Pip-Tazo (IDSA 2026)."))
                warned.append({"name": drug, **_w})
                continue
            if not _urine_lower:
                banned.append({**info, **build_banned_item(
                    name=drug, category="organism",
                    reason_short=(f"{_mech_label} + عدوى غازية/علوية -- BLI غير مقترح."),
                    reason_detail=(
                        (f"كائن منتج لـ ESBL في {'التهاب حويضة / cUTI' if _spec_cat_aa == 'urine' else 'عينة غير بولية'}: "
                         + ("Amoxicillin-clavulanate / Ampicillin-sulbactam لالتهاب المثانة فقط (IDSA 2026). "
                            if not _is_pt else
                            "Pip-Tazo أظهر وفيات أعلى من Meropenem في تجرثم الدم (MERINO 2018: 12.3% مقابل 3.7%). ")
                         + f"البديل: {_invasive_tx}.")
                        if _mech_label == "ESBL" else
                        (f"{_invasive_why}. البديل: {_invasive_tx}.")),
                )})
                continue
            _w = dict(info)
            _w["warning_reason"] = "esbl_bli_uti_only"
            _w["esbl_note"] = (f"كائن {_mech_label}: هذه التوليفة مقبولة لالتهاب المثانة البسيط عند "
                               "ثبوت الحساسية (IDSA 2026). لا تُستخدم في تجرثم الدم أو العدوى الشديدة "
                               f"-- {_invasive_tx}.")
            _w["esbl_note_en"] = (f"{_mech_label} organism: this BLI combination is acceptable for "
                                  "uncomplicated cystitis when proven susceptible (IDSA 2026). Not "
                                  "for bacteraemia or serious infection.")
            warned.append({"name": drug, **_w})
            continue

        # ══════════════════════════════════════════════════════════════════
        # ABSOLUTE CONTRAINDICATIONS -- checked BEFORE pregnancy caution
        # (child age + renal threshold are hard bans; pregnancy is discretionary)
        # ══════════════════════════════════════════════════════════════════
        if age < 18 and not info.get("child_safe", True):
            if "fluoroquinolone" in cls:
                banned.append(build_banned_item(
                    drug, "child", "غير مناسب < 18 سنة.", CHILD_BAN_REASONS["fluoroquinolone"]
                ))
                continue
            if "tetracycline" in cls:
                # The age<8 guard used to sit on this branch, so a tetracycline
                # given to an 8-17 year old fell through to the generic message
                # below and the clinician was told "not preferred for children"
                # with no reason -- losing the dental-staining/bone-deposition
                # rationale that is the whole point of the restriction, and
                # losing the fact that AAP Red Book 2024 and CLSI now accept
                # short courses of doxycycline (<21 days) at any age.
                # FIX 2026-11-10: the tooth-staining restriction is an UNDER-8
                # rule. An 8-17 year old was banned from every tetracycline
                # ("needs a physician decision"), which no guideline says --
                # from 8 years they are ordinary agents. Doxycycline itself is
                # child_safe now (AAP Red Book 2024) and never reaches here.
                if age < 8:
                    banned.append(build_banned_item(
                        drug, "child", "غير مناسب < 8 سنوات.",
                        CHILD_BAN_REASONS["tetracycline"]
                        + "\n\nملاحظة (AAP Red Book 2024): Doxycycline لدورة قصيرة (≤ 21 يوم) "
                          "مقبول في أي عمر — هو البديل من نفس الصنف."))
                    continue
                # age 8-17: no paediatric ban -- fall through to the remaining checks
            else:
                banned.append(build_banned_item(
                    drug, "child", "غير مفضل للأطفال.",
                    f"{drug}: يحتاج تقييم متخصص أو لا يُنصح به روتينياً في عمر {age} سنة. "
                    f"{info.get('child_note', '')}".strip(),
                ))
                continue

        # ── NEONATAL / YOUNG-INFANT gate ──────────────────────────────────────
        # Runs only when the patient is inside the first year, and only when we
        # actually know the age in months. If the clinician entered age=0 years
        # WITHOUT the months field, we cannot tell a 3-week-old from an
        # 11-month-old -- so we warn rather than silently allowing, which is the
        # behaviour that shipped.
        if age < 1 and drug in NEONATAL_RESTRICTIONS:
            _neo = NEONATAL_RESTRICTIONS[drug]
            _alt = f" البديل: {_neo['alt']}." if _neo.get("alt") else ""
            # A months value outside 0-11 is not a patient, it is a data error.
            # Treating 99 as "older than the threshold" silently switched the
            # whole neonatal gate off; treat it as UNKNOWN instead, which warns.
            _m = age_months
            if _m is not None and not (0 <= _m <= 11):
                _m = None
            if _m is None:
                warned.append({
                    # FIX 2026-08-01: `**info` and `warning_reason` were both
                    # missing here, so the render layer had no reason to switch
                    # on and no ABX metadata to fall back to -- the item printed
                    # as a bare drug name with an empty explanation.
                    "name": drug, **info,
                    "category": "neonate", "warning_reason": "neonate",
                    "reason_short": f"عمر غير محدد بالشهور — تحقق من حد الـ {_neo['months']} شهور.",
                    "reason_detail": (f"{_neo['reason']}{_alt}\n\n"
                                      "أدخل العمر بالشهور (خانة «أقل من سنة») "
                                      "ليطبّق النظام الحد العمري بدقة."),
                })
                continue
            if _m < _neo["months"]:
                if _neo["action"] == "ban":
                    banned.append(build_banned_item(
                        drug, "neonate",
                        f"يُمنع تحت {_neo['months']} شهر (العمر {_m} شهر).",
                        f"{_neo['reason']}{_alt}",
                    ))
                else:
                    warned.append({
                        "name": drug, **info,
                        "category": "neonate", "warning_reason": "neonate",
                        "reason_short": f"حذر شديد تحت {_neo['months']} شهر.",
                        "reason_detail": f"{_neo['reason']}{_alt}",
                    })
                continue

        # Preterm window: the chronological ban has lifted, but for an
        # ex-premature infant the contraindication runs to 41 weeks POSTMENSTRUAL
        # age — roughly three chronological months for a 28-weeker. The engine
        # holds no gestational-age field, so it asks rather than assumes.
        if age < 1 and age_months is not None and drug in NEONATAL_RESTRICTIONS:
            _neo2 = NEONATAL_RESTRICTIONS[drug]
            _pcm = _neo2.get("preterm_caution_months")
            if _pcm and _neo2.get("months", 0) <= age_months < _pcm:
                warned.append({
                    "name": drug, **info,
                    "category": "neonate", "warning_reason": "neonate",
                    "reason_short": f"خديج؟ تحقّق قبل الوصف (العمر {age_months} شهر).",
                    "reason_detail": _neo2.get("preterm_reason", ""),
                })
                continue

        # Nitrofurantoin: contraindicated below its renal threshold (EMA/BNF 2025 = 45)
        # ── D-test: Inducible Clindamycin Resistance (CLSI M100 Ed36) ──────────
        if "clindamycin" in d_low and culture_result == "S":
            erythro_r = sir_map.get("Erythromycin") == "R"
            if erythro_r:
                d_test_val = (sir_map.get("D-test") or
                              sir_map.get("D test") or "").strip().upper()
                if d_test_val == "NEGATIVE":
                    pass  # Confirmed D-test negative → safe to use
                else:
                    label = "D-test Positive" if d_test_val == "POSITIVE" else "D-test Not Confirmed"
                    banned.append(build_banned_item(
                        drug, "d_test_inducible",
                        f"مقاومة Clindamycin المستحثة — {label}",
                        f"Erythromycin=R + Clindamycin=S → MLSB inducible resistance محتملة. "
                        f"لا تُستخدم Clindamycin إلا بعد تأكيد D-test سالب. CLSI M100 Ed36 · EUCAST Breakpoint Tables v16.1.",
                    ))
                    continue

        # ── Fusidic acid: لا monotherapy في العدوى الجهازية ─────────────────────
        if "fusidic" in d_low and info.get("no_monotherapy_systemic"):
            # Substring match rather than equality: culture_type comes from the
            # selectbox today, but an exact-match test fails silently the moment a
            # label gains a suffix ("Sputum Culture"), and losing a "never use as
            # monotherapy" warning is not a failure that should happen quietly.
            _ct = (culture_type or "").lower()
            if any(k in _ct for k in ("blood", "csf", "sputum")):
                interactions_alerts.append(
                    "⚠️ Fusidic acid: never as monotherapy in systemic infection — resistance "
                    "emerges rapidly; combination is mandatory (+ Rifampicin or + Vancomycin)."
                )

        # ── Penicillin: Penicillinase في المكورات العنقودية ─────────────────────
        if ("penicillin" in d_low and "oxacillin" not in d_low
                and info.get("penicillinase_sensitive")):
            org_l = (organism_type or "").lower()
            is_staph = ("staphylococcus aureus" in org_l or "mrsa" in org_l
                        or "mssa" in org_l or "staph" in org_l)
            if is_staph and culture_result != "S":
                banned.append(build_banned_item(
                    drug, "penicillinase_producer",
                    "إنتاج Beta-lactamase (Penicillinase)",
                    "90%+ من S. aureus تنتج Penicillinase → Penicillin غير فعال. "
                    "استخدم Cefazolin أو Oxacillin (MSSA) أو Vancomycin (MRSA).",
                ))
                continue

        # ── Oxacillin: MSSA alert للـ bacteremia ─────────────────────────────────
        if "oxacillin" in d_low and culture_result == "S" and culture_type == "Blood":
            interactions_alerts.append(
                "ℹ️ Oxacillin=S (MSSA confirmed). In bacteraemia cefazolin is non-inferior to (flu)cloxacillin "
                "with less kidney injury — CloCeBa (Lancet 2025) / SNAP (NEJM 2026)."
            )

        # ── Enterococcus + TMP-SMX: in-vitro S but clinically unreliable ─────────
        # Enterococci use exogenous folate/thymidine in vivo, bypassing folate
        # inhibition, so TMP-SMX may test S yet fail clinically. CLSI/EUCAST warn
        # against reporting/using it for enterococcal infections.
        if (("trimethoprim" in d_low or "sulfamethoxazole" in d_low or "smx" in d_low)
                and "enterococc" in (organism_type or "").lower()):
            banned.append(build_banned_item(
                drug, "organism",
                "غير موثوق سريرياً ضد Enterococcus (رغم حساسية المختبر).",
                "المكورات المعوية تستخدم الفولات/الثيميدين الخارجي داخل الجسم فتتجاوز "
                "تثبيط الفولات؛ لذلك قد يظهر TMP-SMX حساساً في المختبر لكنه يفشل سريرياً. "
                "لا يُعتمد عليه لعلاج عدوى Enterococcus (CLSI/EUCAST). استخدم "
                "Ampicillin/Amoxicillin (أو Vancomycin/Linezolid حسب الحساسية).",
            ))
            continue

        _nf_limit = info.get("renal_limit", 45)
        if is_renal and "nitrofurantoin" in d_low and _crcl is not None and _crcl < _nf_limit:
            banned.append(build_banned_item(
                drug, "renal",
                f"ممنوع -- CrCl {_crcl:.1f} < {_nf_limit} ml/min",
                f"CrCl = {_crcl:.1f} مل/د -- أقل من الحد المطلوب ({_nf_limit} مل/د). "
                f"خطر عدم كفاءة علاجية + تراكم سمي (EMA/BNF 2025).{_crcl_src}",
            ))
            continue

        # ══════════════════════════════════════════════════════════════════
        # PREGNANCY SAFETY BLOCK
        # Updated per: ACOG 2023, BNF 2025, EMA 2025, ENTIS 2024,
        #              IDSA AMR Guidance 2026, WHO AWaRe 2025, BMJ Teratology 2023
        #
        # ORDERING IS LOAD-BEARING -- DO NOT MOVE THE RENAL BLOCK BACK ABOVE THIS.
        # The renal-adjustment branch below ends in `continue`. While it sat
        # BEFORE this block, any drug whose renal_limit happened to exceed the
        # patient's CrCl skipped pregnancy screening entirely: a pregnant woman
        # with CrCl 55 was shown Gentamicin, Amikacin and Tobramycin (fetal
        # ototoxicity, FDA category D) as "Use with caution -- needs renal
        # adjustment" instead of BANNED, and at CrCl <=30 Clarithromycin,
        # TMP-SMX and Gatifloxacin leaked the same way. The leak was invisible
        # in testing because it only fires when BOTH is_renal is ticked AND
        # cl_cr <= that particular drug's renal_limit. A sweep over
        # 7 specimens x 20 organisms x 7 CrCl values found 560 leaking cells.
        # Absolute teratogenic contraindications must be resolved before any
        # branch that can exit the loop early.
        # ══════════════════════════════════════════════════════════════════
        #
        # FIX 2026-11-11 (round 4): every pregnancy CAUTION used to end in
        # `continue`, straight into preg_warn_items. Nothing after this block
        # ran for those drugs -- not the hepatic contraindication, not the renal
        # adjustment, not the Intermediate flag -- and run_analysis() never
        # passed the pregnancy bucket through the terminal safety gate either.
        # So a pregnant woman in Child-Pugh C was shown TMP-SMX and
        # Nitrofurantoin (hepatic AVOID) as "use with caution", and a pregnant
        # woman with meningitis was shown Gentamicin/Amikacin (no CSF
        # penetration) as options: 322 of 6,000 random cases. A pregnancy
        # caution is now RECORDED here and the drug keeps walking through the
        # remaining hard checks; it is bucketed at the end of the loop.
        _preg_item: Optional[Dict[str, Any]] = None
        _preg_extra: List[str] = []
        if is_preg:

            # ── 1. Tetracyclines: ALWAYS BANNED (class-based override) ────────
            if "tetracycline" in cls:
                banned.append(build_banned_item(
                    drug, "pregnancy",
                    "⛔ ممنوع في الحمل -- Tetracyclines.",
                    "Tetracyclines (Doxycycline / Tetracycline / Minocycline / Tigecycline):\n"
                    "تترسّب في عظام وأسنان الجنين -> تصبغ دائم للأسنان وتثبيط نمو العظام.\n"
                    "محظورة في كل مراحل الحمل (خاصة بعد الأسبوع 15).\n"
                    "ACOG 2023 / BNF 2025: contraindication مطلقة.\n"
                    "البديل: Azithromycin (atypicals) | Amoxicillin-Clavulanate | Cephalosporin.",
                ))
                continue

            # ── 2. Aminoglycosides: USE WITH CAUTION (2026-11-10) ─────────────
            # FIX: was an absolute ban. Gentamicin is standard obstetric therapy
            # (ampicillin + gentamicin for chorioamnionitis / intra-amniotic
            # infection, ACOG; severe pyelonephritis and sepsis in pregnancy).
            # Documented fetal eighth-nerve toxicity is with streptomycin and
            # kanamycin; gentamicin/tobramycin/amikacin carry a theoretical risk
            # managed by once-daily dosing, levels and short courses.
            if "aminoglycoside" in cls:
                _preg_item = {
                    "name": drug, **info,
                    "preg_note": (
                        f"⚠️ Use with Caution — {drug} في الحمل:\n"
                        "يعبر المشيمة. خطر السمية السمعية الجنينية موثّق أساساً مع Streptomycin و "
                        "Kanamycin؛ مع Gentamicin نظري ونادر.\n"
                        "مقبول عند الحاجة (التهاب المشيمة: Ampicillin + Gentamicin؛ التهاب حويضة "
                        "شديد أو إنتان) بجرعة يومية واحدة ومراقبة المستوى ولأقصر مدة.\n"
                        ">>> القرار النهائي للطبيب المعالج حصراً. <<<"),
                }

            # ── 3. TMP-SMX: USE WITH CAUTION, trimester-dependent (2026-11-10) ─
            # FIX: was an absolute ban. ACOG Committee Opinion 717 (reaffirmed):
            # sulfonamides remain appropriate in the 1st trimester when no
            # suitable alternative exists; avoid near term (kernicterus). It is
            # also the alternative for Listeria in penicillin allergy.
            elif ("sulfonamide" in cls or "trimethoprim" in d_low
                    or "sulfamethox" in d_low):
                _preg_item = {
                    "name": drug, **info,
                    "preg_note": (
                        "⚠️ TMP-SMX — Use with Caution في الحمل:\n"
                        "الثلث الأول: مضاد للفولات — يُستخدم فقط عند غياب بديل مناسب (ACOG CO 717) "
                        "مع حمض الفوليك.\n"
                        "قرب الولادة (≥ 32-36 أسبوع): تجنّب — خطر kernicterus.\n"
                        "الثلث الثاني: مقبول.\n"
                        ">>> القرار النهائي للطبيب المعالج حسب الـ trimester. <<<"),
                }

            # ── 4. Clarithromycin: BANNED ─────────────────────────────────────
            elif "clarithromycin" in d_low:
                preg_note = info.get("preg_note") or (
                    "⛔ ممنوع في الحمل -- Clarithromycin.\n"
                    "ارتبط بزيادة الإجهاض (Andersen, PLoS One 2013) وإشارة لتشوهات في الثلث "
                    "الأول مع الماكروليدات (Fan, BMJ 2020).\n"
                    "BNF 2025: تجنّب في الحمل.\n"
                    "البديل الآمن: Azithromycin."
                )
                banned.append(build_banned_item(
                    drug, "pregnancy",
                    preg_note.splitlines()[0],
                    preg_note,
                ))
                continue

            # ── 5. Any remaining preg_status="Banned": BANNED ─────────────────
            elif preg_status_of(info) == "Banned":
                preg_note = info.get("preg_note") or "⛔ ممنوع في الحمل."
                banned.append(build_banned_item(
                    drug, "pregnancy",
                    preg_note.splitlines()[0],
                    preg_note,
                ))
                continue

            # ── 6. Fluoroquinolones: USE WITH CAUTION ────────────────────────
            elif "fluoroquinolone" in cls:
                _preg_item = {
                    "name": drug, **info,
                    "preg_note": info.get("preg_note") or (
                        "⚠️ Use with Caution -- Fluoroquinolone في الحمل:\n"
                        "الأدلة الحديثة (ENTIS 2024): خطر التشوهات أقل مما كان يُعتقد.\n"
                        "لا يُستخدم كخط أول -- فقط عند غياب البديل الأكثر أمانًا.\n"
                        ">>> القرار النهائي للطبيب المعالج حصراً. <<<"
                    ),
                }

            # ── 7. Nitrofurantoin: CAUTION (trimester-dependent) ─────────────
            elif "nitrofurantoin" in d_low:
                _preg_item = {
                    "name": drug, **info,
                    "preg_note": info.get("preg_note") or (
                        "⚠️ Nitrofurantoin -- Use with Caution في الحمل:\n"
                        "الثلث الأول: فقط عند غياب بديل مناسب (ACOG CO 717).\n"
                        "✅ الثلث الثاني وبداية الثالث: مقبول لالتهاب المثانة.\n"
                        "⛔ تجنّب في الـ 3rd trimester وعند الـ term (≥36 أسبوع):\n"
                        "   خطر hemolytic anemia جنينية (G6PD) ونيونيتل hemolysis.\n"
                        "البديل في 3rd trim: Fosfomycin جرعة واحدة أو Cephalexin.\n"
                        ">>> القرار النهائي للطبيب المعالج حسب الـ trimester. <<<"
                    ),
                }

            # ── 8. Metronidazole / Nitroimidazoles: CAUTION ───────────────────
            elif "nitroimidazole" in cls or "metronidazole" in d_low:
                _preg_item = {
                    "name": drug, **info,
                    "preg_note": info.get("preg_note") or (
                        "⚠️ Metronidazole -- Use with Caution:\n"
                        "ACOG 2021: مقبول في كل trimesters عند الضرورة.\n"
                        "يُفضل تجنبه في الـ 1st trimester إن وُجد بديل آمن.\n"
                        ">>> القرار النهائي للطبيب المعالج حصراً. <<<"
                    ),
                }

            # ── 9. Carbapenems / Vancomycin / Colistin (Warn): physician ──────
            elif preg_status_of(info) == "Warn":
                _preg_item = {"name": drug, **info}

        # ══════════════════════════════════════════════════════════════════
        # HEPATIC CONTRAINDICATIONS -- enforced, not merely annotated
        # ------------------------------------------------------------------
        # HEPATIC_DOSING already recorded "Avoid" verdicts for Child-Pugh C, but
        # nothing consumed them: get_hepatic_recommendations() only ANNOTATED the
        # allowed list, so ten agents carrying an explicit Avoid -- including
        # Amoxicillin-Clavulanate (DILI), Chloramphenicol, Nitrofurantoin
        # (cholestatic hepatitis), Doxycycline, Azithromycin and Clarithromycin --
        # stayed in the recommended bucket for a decompensated cirrhotic. The
        # verdict is now applied here, at the point of decision.
        # BNF 2025 hepatic impairment | LiverTox (NIH) | Lexicomp 2025
        # ══════════════════════════════════════════════════════════════════
        if is_hepatic:
            _hep_row = HEPATIC_DOSING.get(drug)
            if _hep_row:
                _grade = (child_pugh or "C").strip().upper()[:1] or "C"
                if _grade not in ("A", "B", "C"):
                    _grade = "C"
                _lvl, _rec = _hep_row.get(_grade, ("Normal", "No adjustment"))
                if "avoid" in str(_lvl).lower():
                    banned.append(build_banned_item(
                        drug, "hepatic",
                        f"ممنوع في القصور الكبدي (Child-Pugh {_grade}).",
                        f"{drug}: {_rec}. {_hep_row.get('note', '')} "
                        f"المرجع: BNF 2025 (hepatic impairment) / LiverTox NIH.",
                    ))
                    continue
                if str(_lvl).lower() not in ("normal", "renal-based", "auc/mic monitoring",
                                             "normal (renal)"):
                    if _preg_item is not None:
                        # Stays in the pregnancy bucket, but the hepatic fact
                        # travels with it instead of being dropped.
                        _preg_item.update(hepatic_level=_lvl, hepatic_rec=_rec)
                        _preg_extra.append(f"🫀 Hepatic (Child-Pugh {_grade}): {_lvl} — {_rec}")
                    else:
                        warned.append({"name": drug, **info,
                                       "warning_reason": "hepatic_adjustment",
                                       "hepatic_level": _lvl, "hepatic_rec": _rec})
                        continue

        # ── Renal dose adjustment (a CAUTION, so it must run last) ────────────
        # Kept below every absolute contraindication on purpose: this branch
        # exits the loop, and anything that exits the loop must not be able to
        # pre-empt a hard ban. See the ordering note in the pregnancy block.
        renal_limit = info.get("renal_limit", 0)
        if (is_renal and renal_limit > 0 and _crcl is not None
                and _crcl <= renal_limit):
            if _preg_item is not None:
                _preg_item.update(renal_adjustment=True, crcl_used=_crcl,
                                  crcl_measured=_crcl_measured)
                _rn = str(info.get("renal_note_en") or info.get("renal_note") or "").strip()
                _preg_extra.append(
                    f"🫘 Renal: CrCl {_crcl:.0f} ml/min"
                    + ("" if _crcl_measured else " (assumed — no creatinine entered)")
                    + f" ≤ {renal_limit} — dose adjustment required"
                    + (f": {_rn}" if _rn else "."))
            else:
                warned.append({"name": drug, **info,
                               "warning_reason": "renal_adjustment",
                               # Carried on the item so the renderers do not each
                               # have to re-derive them. The PDF, the text report and
                               # the on-screen panel previously printed three
                               # different amounts of renal detail.
                               "crcl_used": _crcl,
                               "crcl_measured": _crcl_measured})
                continue

        if culture_result == "I":
            if _preg_item is not None:
                _preg_extra.append("🟡 Culture result I (susceptible, increased exposure) — "
                                   "only at the high-dose regimen, and only if no S alternative exists.")
            else:
                warned.append({"name": drug, **info, "warning_reason": "intermediate_culture"})
                continue

        if _preg_item is not None:
            if _preg_extra:
                _preg_item["preg_note"] = ((_preg_item.get("preg_note") or "").rstrip()
                                           + "\n" + "\n".join(_preg_extra)).strip()
            preg_warn_items.append(_preg_item)
            continue

        allowed.append({"name": drug, **info})

    # ── Host checks for cautions that left the loop EARLY (round 5, 2026-11-12) ─
    # Same defect family as the round-4 pregnancy fix. The ESBL-cystitis
    # carve-out, the possible-carbapenemase caution, the possible-MRSA caution
    # and the neonatal "months unknown" caution all end in `continue` ABOVE the
    # hepatic and renal blocks, so those drugs never met either:
    #   * Cefepime / Pip-Tazo on an ESBL cystitis with CrCl 15 were printed as
    #     "caution" with the ESBL note only -- no renal dose adjustment, while
    #     Meropenem beside them carried one (cefepime accumulation =
    #     encephalopathy);
    #   * Cefoperazone and Cefoperazone-Sulbactam (hepatic AVOID in Child-Pugh
    #     C) stayed a caution: 21 of 12,000 random cases.
    # The checks run here, after the loop, so no early exit can skip them: a
    # hepatic AVOID bans; a hepatic or renal adjustment is recorded on the item
    # and written into the note every renderer already prints for that reason.
    _EARLY_NOTE_KEYS = {
        "esbl_bli_uti_only":      ("esbl_note", "esbl_note_en"),
        "possible_carbapenemase": ("esbl_note", "esbl_note_en"),
        "possible_mrsa":          ("possible_mrsa_note",),
        "neonate":                ("reason_detail",),
        # The hepatic CAUTION branch also ends in `continue`, above the renal
        # block: Cefoperazone-Sulbactam in Child-Pugh B with CrCl 15 was a
        # hepatic caution with no renal adjustment. Renal part only here.
        "hepatic_adjustment":     ("hepatic_note",),
    }
    _kept_warned: List[Dict] = []
    for _it in warned:
        _nkeys = _EARLY_NOTE_KEYS.get(_it.get("warning_reason") or "")
        if not _nkeys:
            _kept_warned.append(_it)
            continue
        _nm = _it.get("name")
        _inf = ABX_GUIDELINES.get(_nm) or {}
        _extra: List[str] = []
        if (is_hepatic and HEPATIC_DOSING.get(_nm)
                and _it.get("warning_reason") != "hepatic_adjustment"):
            _hrow = HEPATIC_DOSING[_nm]
            _g = (child_pugh or "C").strip().upper()[:1] or "C"
            if _g not in ("A", "B", "C"):
                _g = "C"
            _hl, _hr = _hrow.get(_g, ("Normal", "No adjustment"))
            if "avoid" in str(_hl).lower():
                banned.append(build_banned_item(
                    _nm, "hepatic",
                    f"ممنوع في القصور الكبدي (Child-Pugh {_g}).",
                    f"{_nm}: {_hr}. {_hrow.get('note', '')} "
                    f"المرجع: BNF 2025 (hepatic impairment) / LiverTox NIH.",
                ))
                continue
            if str(_hl).lower() not in ("normal", "renal-based", "auc/mic monitoring",
                                        "normal (renal)"):
                _it.update(hepatic_level=_hl, hepatic_rec=_hr)
                _extra.append(f"🫀 Hepatic (Child-Pugh {_g}): {_hl} — {_hr}")
        _rl = _inf.get("renal_limit", 0) or 0
        if is_renal and _rl > 0 and _crcl is not None and _crcl <= _rl:
            _it.update(renal_adjustment=True, crcl_used=_crcl,
                       crcl_measured=_crcl_measured)
            _rn = str(_inf.get("renal_note_en") or _inf.get("renal_note") or "").strip()
            _extra.append(
                f"🫘 Renal: CrCl {_crcl:.0f} ml/min"
                + ("" if _crcl_measured else " (assumed — no creatinine entered)")
                + f" ≤ {_rl} — dose adjustment required"
                + (f": {_rn}" if _rn else "."))
        if _extra:
            _add = "\n".join(_extra)
            _present = [k for k in _nkeys if str(_it.get(k) or "").strip()] or [_nkeys[0]]
            for _k in _present:
                _it[_k] = (str(_it.get(_k) or "").rstrip() + "\n" + _add).strip()
        _kept_warned.append(_it)
    warned = _kept_warned

    # ── Upper UTI / pyelonephritis: lower-tract-only agents (2026-11-10) ──────
    # Nitrofurantoin, oral fosfomycin and norfloxacin do not reach renal tissue
    # or serum; IDSA cUTI 2025 and the IDSA AMR guidance restrict them to
    # cystitis. They used to be offered for pyelonephritis because the engine
    # only knew "urine", not which part of the urinary tract was infected.
    if _uti_upper:
        _lower_only = {"Nitrofurantoin", "Fosfomycin", "Norfloxacin"}
        _hit = ({d["name"] for d in allowed if d.get("name") in _lower_only}
                | {d["name"] for d in warned if d.get("name") in _lower_only}
                | {d["name"] for d in preg_warn_items if d.get("name") in _lower_only})
        allowed = [d for d in allowed if d.get("name") not in _lower_only]
        warned = [d for d in warned if d.get("name") not in _lower_only]
        preg_warn_items = [d for d in preg_warn_items if d.get("name") not in _lower_only]
        for _nm in sorted(_hit):
            banned.append(build_banned_item(
                _nm, "uti_upper",
                "التهاب حويضة / cUTI -- عامل للمثانة فقط.",
                f"{_nm}: لا يحقق تركيزاً علاجياً في نسيج الكلى أو الدم، فلا يُستخدم لالتهاب "
                "الحويضة أو cUTI أو الإنتان البولي (IDSA cUTI 2025). الخيارات: TMP-SMX أو "
                "Ciprofloxacin/Levofloxacin إذا كانت حساسة، أو بيتا-لاكتام وريدي حسب المزرعة."))

    # ── Post-loop clinical notes (2026-11-10) ─────────────────────────────────
    # Applied after every hard ban has had its chance: a note never rescues a
    # drug from `banned`, and a "warn" note only DEMOTES allowed -> warned.
    if _post_notes:
        from therapy_rules import CLINICAL_NOTE_EN as _NOTE_EN
        _banned_names = {b.get("name") for b in banned if isinstance(b, dict)}
        _new_allowed = []
        for _it in allowed:
            _nm = _it.get("name")
            if _nm in _post_notes and _nm not in _banned_names:
                _lvl, _note, _rsn = _post_notes[_nm]
                _it = dict(_it)
                _it["clinical_note"] = _note
                _it["clinical_note_en"] = _NOTE_EN.get(_rsn, _NOTE_EN["organism_caution"])
                if _lvl == "warn":
                    _it["warning_reason"] = _rsn
                    warned.append(_it)
                    continue
            _new_allowed.append(_it)
        allowed = _new_allowed
        for _bucket in (warned, preg_warn_items):
            for _it in _bucket:
                _nm = _it.get("name")
                if _nm in _post_notes and not _it.get("clinical_note"):
                    _it["clinical_note"] = _post_notes[_nm][1]
                    _it["clinical_note_en"] = _NOTE_EN.get(_post_notes[_nm][2],
                                                           _NOTE_EN["organism_caution"])

    # ── The Intermediate fact is INDEPENDENT of warning_reason ───────────────
    # DEFECT 2026-08-01: `warning_reason` is a single slot and the branches above
    # are ordered hard-ban -> hepatic -> renal -> intermediate, each ending in
    # `continue`. So for a patient with renal impairment an Intermediate result
    # was relabelled "renal_adjustment" and the I vanished from the report: the
    # dedicated "⚠ Intermediate (I) on culture — use only if no better option"
    # banner filters on warning_reason == "intermediate_culture" and no longer
    # matched.
    #
    # The two facts are not merely both true, they pull OPPOSITE WAYS. EUCAST
    # redefined I as "Susceptible, Increased exposure" — the agent works only at
    # a HIGHER dose or longer infusion — while the renal note instructs the
    # clinician to REDUCE the dose. Showing one and hiding the other is the
    # worst of the three possible outputs.
    #
    # Reordering the branches was rejected: the ordering is load-bearing (see
    # the pregnancy block) and moving it risks letting a caution pre-empt a hard
    # ban. A separate key costs nothing and cannot be overwritten.
    for _item in warned:
        _item["culture_intermediate"] = (sir_map.get(_item.get("name")) == "I")
    for _item in allowed:
        _item["culture_intermediate"] = False   # an I never reaches allowed

    allowed         = sorted(allowed,         key=lambda x: x.get("priority", 999))
    warned          = sorted(warned,          key=lambda x: x.get("priority", 999))
    preg_warn_items = sorted(preg_warn_items, key=lambda x: x.get("priority", 999))

    # ── Specimen-appropriateness filter ───────────────────────────────────────
    # Urine-only agents achieve therapeutic concentrations ONLY in urine:
    #   • Nitrofurantoin / Fosfomycin (oral): negligible serum & tissue levels
    #     -> useless for bacteremia, pneumonia, wound, meningitis.
    #   • Norfloxacin: poor serum levels -> urinary (and some GI) use only.
    # They are BANNED (with a reason) for every non-urine systemic specimen.
    # For stool/GI, Norfloxacin retains an enteric role so only Nitro/Fosfo go.
    # Canonical classifier, not a raw substring test. Three different "is this
    # urine?" tests used to coexist in this file and they disagreed: the ESBL
    # branch asked classify_specimen(), this filter asked `"urine" in text`, and
    # _hide_urine_only() asked a third. For "MSU", "Midstream" or "Catheter
    # specimen" the first said urine and the other two said not-urine, so
    # Nitrofurantoin and Fosfomycin were banned off a genuine urine sample as
    # "specimen-inappropriate" -- removing the two best-targeted oral agents for
    # an uncomplicated UTI. One classifier, one answer.
    _spec_cat_final = classify_specimen(culture_type)
    _spec_l     = (culture_type or "").lower()
    is_urine    = _spec_cat_final == "urine"
    is_stool_gi = _spec_cat_final == "stool"

    if not is_urine:
        if is_stool_gi:
            _urine_only = {"Nitrofurantoin", "Fosfomycin"}   # Norfloxacin has GI use
            _reason = ("عامل بولي فقط -- لا يصل لتركيز علاجي داخل الأمعاء؛ "
                       "غير مناسب لعدوى الجهاز الهضمي.")
        else:
            _urine_only = {"Nitrofurantoin", "Fosfomycin", "Norfloxacin"}
            _reason = ("عامل بولي فقط -- لا يحقق تركيزاً علاجياً في الدم أو الأنسجة؛ "
                       "غير مناسب للعدوى الجهازية (دم / رئة / جرح / سائل نخاعي). "
                       "(ملاحظة: Fosfomycin الوريدي استثناء غير متوفر في هذه القائمة.)")
        _moved = ({d["name"] for d in allowed if d.get("name") in _urine_only} |
                  {d["name"] for d in warned  if d.get("name") in _urine_only} |
                  {d["name"] for d in preg_warn_items if d.get("name") in _urine_only})
        allowed = [d for d in allowed if d.get("name") not in _urine_only]
        warned  = [d for d in warned  if d.get("name") not in _urine_only]
        # Also purge urine-only agents from the pregnancy-warning list: for a
        # non-urine specimen they are specimen-inappropriate regardless of
        # pregnancy status, so they belong in 'banned' (below), not as a
        # standalone pregnancy note that would otherwise leave them unflagged.
        preg_warn_items = [d for d in preg_warn_items if d.get("name") not in _urine_only]
        for _nm in sorted(_moved):
            banned.append(build_banned_item(
                _nm, "specimen",
                "عامل بولي فقط -- غير مناسب لهذه العينة.", _reason,
            ))

    return allowed, warned, banned, preg_warn_items, sorted(set(interactions_alerts))

# =========================================================
# MDR / XDR / PDR Classification -- CDC & ECDC 2017
# =========================================================
# تعريف الفئات حسب Magiorakos et al. 2012 (ECDC/CDC)
MDR_CATEGORIES = {
    "Aminoglycosides":         ["Gentamicin","Amikacin","Tobramycin","Netilmicin"],
    "Antipseudomonal Penics":  ["Piperacillin + Tazobactam"],
    # Magiorakos Table 1 counts 3rd AND 4th generation as ONE category. Splitting
    # them across three entries double-counted ONE cephalosporin mechanism.
    #
    # CORRECTION (2026-07): an earlier revision of this comment claimed a plain
    # ESBL should score 1 category and come back NOT MDR. That is wrong, and the
    # code below is right. Magiorakos Table 3 lists Penicillins, Penicillins +
    # BLI, Non-extended-spectrum cephalosporins and Extended-spectrum
    # cephalosporins as FOUR SEPARATE categories, so an ESBL E. coli that is
    # non-susceptible to ampicillin, amoxicillin-clavulanate, cefuroxime and
    # ceftriaxone is non-susceptible in four -- MDR, which is also how ESBL-E are
    # reported throughout the literature. Do not "fix" the code to match the old
    # comment; merging 3rd and 4th generation agents into one entry is the whole
    # of the intended change.
    "Extended-Sp Cephalosporins": ["Ceftriaxone","Cefotaxime","Cefixime",
                                   "Ceftazidime","Cefoperazone",
                                   "Cefoperazone + Sulbactam","Cefepime"],
    # 1st/2nd generation: a distinct Magiorakos category that had no entry, so
    # resistance to it counted for nothing. Cefuroxime is 2nd gen and moves here.
    "Non-Extended-Sp Cephalosporins": ["Cephalexin","Cefadroxil","Cephradine",
                                       "Cefazolin","Cefaclor","Cefuroxime",
                                       "Cefuroxime sodium"],
    "Cephamycins":             ["Cefoxitin"],
    "Monobactams":             ["Aztreonam"],
    # Penicillin (benzylpenicillin) had no category at all, so a penicillin-R
    # pneumococcus scored zero for the one class that defines PRSP.
    "Penicillins":             ["Ampicillin","Amoxicillin","Penicillin"],
    "Carbapenems":             ["Imipenem/Cilastatin","Meropenem","Ertapenem"],
    # Moxifloxacin and Gatifloxacin were in the formulary but in NO category, so
    # resistance to them counted for nothing. Magiorakos lists moxifloxacin under
    # Fluoroquinolones for S. aureus, Enterococcus and Enterobacteriaceae alike.
    "Fluoroquinolones":        ["Ciprofloxacin","Levofloxacin","Ofloxacin","Norfloxacin",
                                "Moxifloxacin","Gatifloxacin"],
    "Folate PI":               ["Trimethoprim/Sulfamethoxazole"],
    "Penicillins+BLI":         ["Amoxicillin + Clavulanic acid","Ampicillin/Sulbactam"],
    "Polymyxins":              ["Colistin"],
    # Teicoplanin added 2026-11-10 (Magiorakos Tables 1-2 list it).
    "Glycopeptides":           ["Vancomycin", "Teicoplanin"],
    "Oxazolidinones":          ["Linezolid"],
    # Kept for any external caller; no organism set counts it any more --
    # nitrofurantoin appears in NO Magiorakos table (2026-11-10).
    "Nitrofurans":             ["Nitrofurantoin"],
    # Categories added 2026-11-10 -- in the Magiorakos tables and now stocked:
    "Glycylcyclines":          ["Tigecycline"],
    "Lipopeptides":            ["Daptomycin"],
    "Anti-MRSA Cephalosporins": ["Ceftaroline"],
    "Fosfomycins":             ["Fosfomycin"],
    "Tetracyclines":           ["Doxycycline", "Tetracycline", "Minocycline"],
    "Macrolides":              ["Azithromycin", "Clarithromycin", "Erythromycin"],
    "Lincosamides":            ["Clindamycin"],
    "Rifamycins":              ["Rifampicin"],
    # ── Categories that had NO entry at all before ────────────────────────────
    # Magiorakos Table 1 (S. aureus): "Anti-staphylococcal beta-lactams (or
    # cephamycins)" with oxacillin OR cefoxitin as the marker agent. Neither
    # Oxacillin nor Penicillin belonged to any category, and Cephamycins was
    # excluded from the Gram-positive set -- so a textbook MRSA (oxacillin R,
    # cefoxitin R, penicillin R, erythromycin R, ciprofloxacin R) scored only
    # 2 categories and came back level=None. This category is used ONLY in the
    # staphylococcal set, so Cefoxitin is never double-counted against the
    # Gram-negative "Cephamycins" entry.
    "Anti-staphylococcal Beta-lactams": ["Oxacillin", "Cefoxitin"],
    # Magiorakos Table 1: "Fucidanes". Fusidic acid was in the formulary with no
    # category, so fusidic-acid resistance in S. aureus counted for nothing.
    "Fusidanes":               ["Fusidic acid"],
    # Pneumococci are OUTSIDE the Magiorakos scope (the paper covers S. aureus,
    # Enterococcus, Enterobacteriaceae, P. aeruginosa and Acinetobacter only).
    # This single "Cephalosporins" bucket follows the conventional MDRSP
    # definition and deliberately merges 2nd/3rd-generation agents, so one
    # PBP-mediated mechanism cannot be counted twice.
    "Cephalosporins (pneumococcal)": ["Cefuroxime", "Cefuroxime sodium",
                                      "Ceftriaxone", "Cefotaxime", "Cefixime"],
}

# Categories meaningful for Gram-negative organisms (Enterobacterales / non-fermenters)
# FIX 2026-11-10: "Nitrofurans" removed (in no Magiorakos table -- it padded
# the denominator and could push an isolate away from an XDR call);
# "Glycylcyclines" (tigecycline, Magiorakos Table 3) added.
MDR_CATEGORIES_GRAM_NEG = frozenset([
    "Aminoglycosides", "Antipseudomonal Penics", "Extended-Sp Cephalosporins",
    "Carbapenems", "Fluoroquinolones", "Folate PI", "Penicillins+BLI",
    "Polymyxins", "Non-Extended-Sp Cephalosporins", "Cephamycins",
    "Monobactams", "Penicillins", "Glycylcyclines",
    "Fosfomycins", "Tetracyclines",
])
# ── Gram-positive category sets — ONE SET PER ORGANISM GROUP ────────────────
# A single flat "Gram-positive" set cannot be correct, because Magiorakos builds
# a DIFFERENT category list for each organism. The old flat set contained
# neither Penicillins nor any anti-staphylococcal beta-lactam entry, so the two
# resistances that define MRSA and ampicillin-resistant E. faecium were both
# invisible to the classifier, while Nitrofurans (a urinary agent that appears
# in no Magiorakos table) padded the denominator and pushed isolates away from
# an XDR call.
#
# Magiorakos et al., Clin Microbiol Infect 2012;18:268-281.

# Table 1 — Staphylococcus aureus.
# Categories present in this formulary; those with no agent stocked here
# (anti-MRSA cephalosporins, glycylcyclines, lipopeptides, phenicols,
# streptogramins, ansamycins) simply never contribute.
MDR_CATEGORIES_STAPH = frozenset([
    "Anti-staphylococcal Beta-lactams", "Aminoglycosides", "Fluoroquinolones",
    "Folate PI", "Fusidanes", "Glycopeptides", "Lincosamides", "Macrolides",
    "Oxazolidinones", "Tetracyclines", "Rifamycins", "Fosfomycins",
    # 2026-11-10: Magiorakos Table 1 categories now stocked in the formulary.
    "Anti-MRSA Cephalosporins", "Lipopeptides", "Glycylcyclines",
])

# Table 2 — Enterococcus spp.
# Note what is ABSENT and must stay absent: cephalosporins and folate-pathway
# inhibitors (intrinsic / no in-vivo activity) and nitrofurantoin (not a
# Magiorakos category). Penicillins here means AMPICILLIN — the single most
# important marker for E. faecium, previously uncounted.
MDR_CATEGORIES_ENTEROCOCCUS = frozenset([
    "Penicillins", "Aminoglycosides", "Carbapenems", "Fluoroquinolones",
    "Glycopeptides", "Oxazolidinones", "Tetracyclines",
    # 2026-11-10: Magiorakos Table 2 categories now stocked.
    "Lipopeptides", "Glycylcyclines",
])

# Streptococci (incl. S. pneumoniae) — NOT a Magiorakos organism.
# Follows the conventional MDRSP definition: non-susceptibility to >=3 of
# penicillin, cephalosporins, macrolides, lincosamides, tetracyclines,
# folate-pathway inhibitors, fluoroquinolones, glycopeptides, oxazolidinones.
# Flagged as a non-Magiorakos basis in the returned `basis` field.
MDR_CATEGORIES_STREP = frozenset([
    "Penicillins", "Cephalosporins (pneumococcal)", "Macrolides",
    "Lincosamides", "Tetracyclines", "Folate PI", "Fluoroquinolones",
    "Glycopeptides", "Oxazolidinones",
])

# Retained for backward compatibility with any external caller / older test that
# still imports the flat name. It is the union of the three sets above and is
# NOT used by classify_mdr any more.
MDR_CATEGORIES_GRAM_POS = frozenset([
    "Anti-staphylococcal Beta-lactams", "Cephalosporins (pneumococcal)",
    "Penicillins", "Aminoglycosides", "Carbapenems", "Fluoroquinolones",
    "Folate PI", "Fusidanes", "Glycopeptides", "Lincosamides", "Macrolides",
    "Oxazolidinones", "Tetracyclines", "Rifamycins", "Fosfomycins",
    "Anti-MRSA Cephalosporins", "Lipopeptides", "Glycylcyclines",
])

GRAM_POSITIVE_ORGANISMS = frozenset([
    "staphylococcus aureus", "mrsa", "mssa",
    "staphylococcus epidermidis", "staphylococcus saprophyticus",
    "staphylococcus lugdunensis", "coagulase-negative staphylococci",
    "enterococcus faecalis", "enterococcus faecium", "enterococcus spp.", "vre",
    "streptococcus pneumoniae", "streptococcus pyogenes",
    "streptococcus agalactiae", "streptococcus viridans",
    "listeria monocytogenes", "corynebacterium",
])

# ── Organisms for which the MDR/XDR/PDR framework does not apply at all ──────
# Returning "XDR" for an anaerobe or a Legionella is not a conservative error --
# it is a fabricated alarm that drives escalation to reserve agents. Before this
# guard, `Anaerobes` and `Legionella pneumophila` were routed into the
# GRAM-NEGATIVE category set (they match no Gram-positive key) and, having no
# intrinsic-resistance row to strip their EXPECTED beta-lactam and
# aminoglycoside resistance, both came back XDR on 9 of 11 categories.
#
#  * no cell wall            -> every beta-lactam/glycopeptide result is expected
#  * obligate intracellular  -> AST is not performed and has no breakpoints
#  * anaerobes               -> intrinsically resistant to aminoglycosides;
#                               Magiorakos builds no category table for them
MDR_NOT_APPLICABLE = (
    "mycoplasma", "ureaplasma", "chlamydia", "chlamydophila",
    "legionella", "rickettsia", "coxiella", "bartonella", "brucella",
    "treponema", "borrelia", "leptospira",
    "anaerobe", "لاهوائي", "bacteroides", "clostrid", "fusobacterium",
    "peptostreptococcus", "prevotella", "veillonella", "actinomyces",
    "mycobacter",
    # Fungi. Found on re-review: "Candida albicans" matched no Gram-positive key,
    # fell through to the GRAM-NEGATIVE branch and was returned as MDR with the
    # basis "Magiorakos 2012, Tables 3-5" -- a bacterial framework applied to a
    # yeast, citing a paper that never mentions it. Antifungal susceptibility has
    # its own categories (CLSI M27/M60, EUCAST antifungal tables) and no
    # MDR/XDR/PDR definition at all.
    "candida", "aspergillus", "cryptococc", "fungus", "fungal", "yeast",
    "mucor", "rhizopus", "fusarium", "trichosporon", "malassezia",
    "histoplasma", "blastomyces", "coccidioides", "pneumocystis",
    "فطر", "خميرة",
)

# Aerobic organisms that ARE routinely classified in the literature but sit
# outside the five species Magiorakos actually tabulated. They keep a level, but
# the read-out says which authority it rests on so nobody quotes "Magiorakos
# XDR" for a Stenotrophomonas.
MDR_OUTSIDE_MAGIORAKOS = (
    "stenotrophomonas", "burkholderia", "salmonella", "shigella",
    "campylobacter", "haemophilus", "influenzae", "aeromonas",
    "moraxella", "neisseria", "vibrio", "yersinia", "listeria",
    "corynebacterium", "streptococc",
)

# ============================================================================
#  INTRINSIC_RESISTANCE — moved to clinical_data.py (SINGLE SOURCE OF TRUTH)
# ----------------------------------------------------------------------------
#  It used to be defined inline here, while ast_qa_engine.py imported it from a
#  `clinical_data` module that did not exist in this repository. That import
#  silently fell back to {}, so the QA engine's intrinsic-resistance level was
#  dead for every Gram-negative while THIS copy was driving the Avoid list — the
#  two halves of the product disagreed with nobody noticing. The table now lives
#  in clinical_data.py and both halves import the same rows.
#
#  Matching is EXACT drug-name (see _remove_intrinsic_resistance /
#  is_intrinsically_avoided), so every spelling variant used anywhere in the app
#  must appear verbatim in the list. Extra variants that match no real drug are
#  harmless. ONLY intrinsically-INACTIVE agents are listed — anti-pseudomonal
#  beta-lactams (Ceftazidime/Cefepime/Cefoperazone/Pip-Tazo/Aztreonam/carbapenems)
#  are deliberately EXCLUDED and judged on their own AST result.
# ============================================================================
try:
    from clinical_data import INTRINSIC_RESISTANCE
    INTRINSIC_TABLE_OK = True
except Exception as _intrinsic_exc:          # pragma: no cover - deployment fault
    logger.error("clinical_data.py is missing or unreadable (%s) -- the "
                 "intrinsic-resistance table is EMPTY; Avoid-routing and MDR "
                 "stripping are degraded.", _intrinsic_exc)
    INTRINSIC_RESISTANCE: Dict[str, List[str]] = {}
    INTRINSIC_TABLE_OK = False


# mecA (MRSA) and vanA/vanB (VRE) are ACQUIRED mechanisms, not intrinsic ones.
# They live in INTRINSIC_RESISTANCE under the pseudo-species keys "mrsa"/"vre"
# because that table also drives the therapeutic Avoid list, where banning every
# beta-lactam on an MRSA is exactly right. But Magiorakos strips only INTRINSIC
# categories before counting, and counts acquired resistance. Leaving these rows
# in place for the MDR pass deleted the very categories that define the
# phenotype: an isolate reported as "VRE" lost its Glycopeptides category and
# came back level=None, while the SAME isolate reported as "Enterococcus
# faecium" came back MDR. One isolate must not get two answers because of how
# the lab typed its name.
_ACQUIRED_NOT_INTRINSIC = {
    "mrsa": {"Oxacillin", "Penicillin", "Cefoxitin", "Ampicillin", "Amoxicillin",
             "Amoxicillin + Clavulanic acid", "Ampicillin/Sulbactam",
             "Piperacillin + Tazobactam", "Cephalexin", "Cefadroxil", "Cephradine",
             "Cefazolin", "Cefaclor", "Cefuroxime", "Cefuroxime sodium",
             "Ceftriaxone", "Cefotaxime", "Cefixime", "Ceftazidime", "Cefepime",
             "Cefoperazone", "Cefoperazone + Sulbactam",
             "Imipenem/Cilastatin", "Meropenem", "Ertapenem"},
    "vre":  {"Vancomycin", "Teicoplanin"},
}


def _remove_intrinsic_resistance(organism: str, sir_map: Dict[str, str],
                                 keep_acquired: bool = False) -> Dict[str, str]:
    """Drop drugs the organism is intrinsically resistant to (not acquired).

    keep_acquired=True (used by classify_mdr) additionally keeps the agents whose
    resistance on that row is an ACQUIRED mechanism, so the MDR/XDR count sees
    them. Everything else -- the Avoid list, mechanism inference -- keeps the
    default and still strips the whole row.
    """
    org_l = (organism or "").lower().strip()
    drugs_to_drop = set()
    for org_key, drug_list in INTRINSIC_RESISTANCE.items():
        if not org_key:
            continue
        # Reverse containment (`org_l in org_key`) exists so that "proteus"
        # picks up "proteus mirabilis". Ungated, it also makes EVERY key match a
        # blank or 1-2 character name: `"" in "escherichia coli"` is True, so an
        # organism the OCR failed to read stripped the ENTIRE panel and
        # classify_mdr came back level=None with total_tested=0 -- a silent
        # false-negative on the MDR alert. A genus fragment is never shorter
        # than four characters.
        if org_key in org_l or (len(org_l) >= 4 and org_l in org_key):
            _row = set(drug_list)
            if keep_acquired:
                _row -= _ACQUIRED_NOT_INTRINSIC.get(org_key, set())
            drugs_to_drop.update(_row)
    if not drugs_to_drop:
        return dict(sir_map)
    return {d: v for d, v in sir_map.items() if d not in drugs_to_drop}

def classify_mdr(organism: str, sir_map: Dict[str, str]) -> Dict[str, Any]:
    """
    MDR/XDR/PDR classification -- Magiorakos et al. 2012 (ECDC/CDC).
    Key principles implemented:
    • Non-susceptible = R + I (not R alone)
    • Intrinsic resistance excluded before counting
    • Gram-pos / Gram-neg category sets applied per organism
    • Category counts as non-susceptible if non-susceptible to ≥1 agent in it
      (a category is "susceptible" only when EVERY tested agent in it is S)
    • PDR = non-susceptible to ALL agents in ALL categories (no S anywhere)
    • XDR/PDR held to MDR on thin panels (<6 categories or <3 multi-agent cats)
    • Reliability warning when too few categories testable
    • Also returns `conservative_resistant_categories` (the stricter "all agents
      lost" view) as METADATA only — never used to set the level.
    """
    sir_map = normalize_sir_map(sir_map)
    if not sir_map:
        return {"level": None, "resistant_categories": [], "total_tested": 0}

    org_l = (organism or "").lower().strip()

    # 0. Organisms the framework was never built for -> refuse, do not guess.
    if any(k in org_l for k in MDR_NOT_APPLICABLE):
        return {
            "level": None, "resistant_categories": [], "total_tested": 0,
            "not_applicable": True,
            "basis": "not applicable",
            "warnings": [
                "ℹ️ تصنيف MDR/XDR/PDR غير منطبق على هذا الكائن — المقاومة "
                "الظاهرة هنا متوقعة جوهرياً (لا جدار خلوي / لاهوائي / داخل "
                "خلوي إجباري) وليست مقاومة مكتسبة. Magiorakos 2012 لا يضع "
                "جدول فئات لهذه المجموعة."
            ],
        }

    # 1. Strip intrinsic resistance (Magiorakos: an intrinsically-resistant
    #    category is removed BEFORE the criteria are applied) -- but keep the
    #    ACQUIRED mecA / van resistances, which the same criteria count.
    clean_map = _remove_intrinsic_resistance(organism, sir_map, keep_acquired=True)

    # 2. Choose the category set for THIS organism group, not one flat
    #    Gram-positive list. Order matters: enterococci and streptococci must be
    #    tested before the generic staphylococcal branch.
    if any(k in org_l for k in ("enterococc", "vre")):
        applicable, _group, _basis = (MDR_CATEGORIES_ENTEROCOCCUS, "enterococcus",
                                      "Magiorakos 2012, Table 2")
    elif "streptococc" in org_l or "pneumococc" in org_l:
        applicable, _group, _basis = (MDR_CATEGORIES_STREP, "streptococcus",
                                      "MDRSP convention — outside Magiorakos scope")
    elif any(k in org_l for k in ("staphylococc", "staph", "mrsa", "mssa")):
        # Magiorakos Table 1 is S. AUREUS. Coagulase-negative staphylococci
        # (epidermidis, saprophyticus, haemolyticus, "CoNS") are not in the paper
        # at all, so labelling their result "Magiorakos 2012, Table 1" overstates
        # the authority behind it. The category set is the closest reasonable fit
        # and is kept; only the citation is corrected.
        _is_aureus = ("aureus" in org_l or org_l in ("mrsa", "mssa")
                      or "mrsa" in org_l or "mssa" in org_l)
        applicable, _group, _basis = (
            MDR_CATEGORIES_STAPH, "staphylococcus",
            "Magiorakos 2012, Table 1" if _is_aureus
            else "S. aureus categories applied to CoNS — outside Magiorakos scope")
    elif (any(g in org_l for g in GRAM_POSITIVE_ORGANISMS)
          or "gram-positive" in org_l or "gram positive" in org_l):
        # "Gram-positive cocci (unidentified)" (added 2026-11-10) matched no
        # key here and fell through to the GRAM-NEGATIVE set, reported as
        # "Magiorakos 2012, Tables 3-5" -- a Gram-negative framework applied to
        # a Gram-positive isolate (FIX 2026-11-11, round 4).
        applicable, _group, _basis = (MDR_CATEGORIES_GRAM_POS, "gram-positive (other)",
                                      "outside Magiorakos scope")
    else:
        applicable, _group, _basis = (MDR_CATEGORIES_GRAM_NEG, "gram-negative",
                                      "Magiorakos 2012, Tables 3-5")
    # An isolate identified only by its Gram stain is not one of the organisms
    # Magiorakos tabulated; say so rather than quote the paper for it.
    if (("unidentified" in org_l or "unspeciated" in org_l or "non-fermenting" in org_l)
            and "enterobacterales" not in org_l and "Magiorakos" in _basis):
        _basis = "organism not identified — provisional, outside Magiorakos scope"
    if any(k in org_l for k in MDR_OUTSIDE_MAGIORAKOS) and "Magiorakos" in _basis:
        _basis = "outside Magiorakos scope — literature convention"
    is_gram_pos = _group != "gram-negative"

    resistant_cats     = []
    susceptible_cats   = []
    single_drug_cats   = []   # categories judged on only 1 tested agent
    conservative_resistant_cats = []  # "therapeutic loss" view — metadata only

    for cat, drugs in MDR_CATEGORIES.items():
        if cat not in applicable:
            continue
        tested = [d for d in drugs if d in clean_map]
        if not tested:
            continue
        if len(tested) == 1:
            single_drug_cats.append(cat)
        # Magiorakos et al. 2012 (the international definition): a category counts
        # as NON-SUSCEPTIBLE — i.e. it contributes toward MDR/XDR — when the
        # isolate is non-susceptible (R or I) to AT LEAST ONE tested agent in it.
        # A category is "susceptible" only when EVERY tested agent in it is S.
        # (Requiring ALL agents to be non-S before counting the category is
        # stricter than Magiorakos and systematically UNDER-counts MDR/XDR — that
        # was the previous bug.)
        if any(clean_map.get(d) in ("R", "I") for d in tested):
            resistant_cats.append(cat)
        else:
            susceptible_cats.append(cat)
        # Supplementary conservative "Orange" view: a category is fully lost only
        # when NO tested agent is S. Kept purely as metadata for the therapeutic
        # read-out and for the PDR test below — it must NEVER drive the MDR/XDR
        # level, or the tool drifts below world references again.
        if not any(clean_map.get(d) == "S" for d in tested):
            conservative_resistant_cats.append(cat)

    total_cats = len(resistant_cats) + len(susceptible_cats)
    r_count    = len(resistant_cats)

    if total_cats == 0:
        return {"level": None, "resistant_categories": [], "total_tested": 0}

    # XDR/PDR require enough categories tested to be meaningful (Magiorakos:
    # XDR = susceptible to ≤2 categories out of the full applicable panel).
    # Without a broad panel we cannot reliably call XDR/PDR -> cap at MDR.
    _enough_for_xdr = total_cats >= 6

    # A category judged on a SINGLE tested agent is weak evidence: one disc can
    # be an error/outlier. XDR/PDR is a severe call, so it must rest on
    # categories confirmed by ≥2 agents. Count how many RESISTANT categories are
    # multi-agent; if fewer than 3, we do not make a categorical XDR/PDR call.
    _single = set(single_drug_cats)
    _multidrug_resistant = [c for c in resistant_cats if c not in _single]
    _enough_multidrug = len(_multidrug_resistant) >= 3

    # PDR (Magiorakos): non-susceptibility to ALL agents in ALL categories — i.e.
    # not susceptible to a single tested agent anywhere. Under the corrected
    # category counting, "every category is non-susceptible" (r_count == total)
    # is NOT the same as PDR, because a category can be non-susceptible while
    # still holding one S agent. PDR requires the conservative count (no S in any
    # category) to cover every evaluable category.
    # NOTE on "I". Magiorakos counts non-susceptible = I or R, and this engine
    # follows it. The paper predates the 2019 EUCAST redefinition of I as
    # "susceptible, increased exposure" -- a USABLE result at a higher dose, not
    # a failing one. Consequence: a panel reported entirely as I is classified
    # MDR here. That is faithful to the published criteria and errs toward
    # flagging, but it is a real divergence from current EUCAST language and is
    # recorded so nobody mistakes it for an oversight.
    _no_susceptible_anywhere = (len(conservative_resistant_cats) == total_cats)

    # Magiorakos Table 1, criterion (i): "an MRSA is always considered MDR by
    # virtue of being an MRSA" -- because oxacillin/cefoxitin resistance predicts
    # non-susceptibility to every beta-lactam category in the document except the
    # anti-MRSA cephalosporins. Detected from the AST MARKERS, not from the
    # organism name, so it fires on an isolate the lab reported as plain
    # "Staphylococcus aureus" with Oxacillin R -- which is how most labs report.
    _is_staph_grp = _group == "staphylococcus"
    _mrsa_by_marker = clean_map.get("Oxacillin") in ("R", "I") or \
                      clean_map.get("Cefoxitin") in ("R", "I")
    _mrsa_by_name = org_l == "mrsa" or "methicillin-resistant" in org_l \
                    or "methicillin resistant" in org_l
    _is_mrsa_mdr = _is_staph_grp and (_mrsa_by_marker or _mrsa_by_name)

    if _no_susceptible_anywhere and _enough_for_xdr and _enough_multidrug:
        level = "PDR"
    elif (total_cats - r_count) <= 2 and r_count >= 3 and _enough_for_xdr and _enough_multidrug:
        level = "XDR"
    elif r_count >= 3:
        level = "MDR"
    elif _is_mrsa_mdr:
        level = "MDR"
    else:
        level = None

    # If pattern looks like XDR/PDR but the panel is too thin (few categories,
    # or resistant categories rest mostly on single agents), flag it but hold at
    # MDR rather than over-calling XDR/PDR.
    _capped = False
    if r_count >= 3 and (total_cats - r_count) <= 2 and not (_enough_for_xdr and _enough_multidrug):
        _capped = True

    # Reliability flag
    reliable = total_cats >= 4
    warnings = []
    if not reliable:
        warnings.append(f"⚠️ Only {total_cats} categories testable -- MDR classification may be unreliable.")
    if single_drug_cats:
        warnings.append(f"⚠️ Categories judged on a single agent: {', '.join(single_drug_cats)}")
    if _is_mrsa_mdr and level == "MDR" and r_count < 3:
        warnings.append("ℹ️ MDR بحكم التعريف: كل MRSA يُصنَّف MDR — مقاومة "
                        "Oxacillin/Cefoxitin تتنبأ بعدم الحساسية لكل فئات "
                        "البيتا-لاكتام (Magiorakos 2012, Table 1, criterion i).")
    if "outside" in _basis or "MDRSP" in _basis:
        warnings.append(f"ℹ️ أساس التصنيف: {_basis}. Magiorakos 2012 يغطي "
                        "S. aureus · Enterococcus · Enterobacteriaceae · "
                        "P. aeruginosa · Acinetobacter فقط.")
    if _capped:
        warnings.append("⚠️ Resistance pattern suggests XDR/PDR, but the evidence is too thin "
                        "(few categories, or resistant categories rest on a single agent each) -- "
                        "reported as MDR. Expand the panel with ≥2 agents per category to confirm.")

    return {
        "level":                  level,
        "resistant_categories":   resistant_cats,
        "susceptible_categories": susceptible_cats,
        "total_tested":           total_cats,
        "total_categories_evaluable": total_cats,
        "resistant_count":        r_count,
        "single_drug_categories": single_drug_cats,
        "conservative_resistant_categories": conservative_resistant_cats,
        "reliable":               reliable,
        "warnings":               warnings,
        "gram":                   "positive" if is_gram_pos else "negative",
        "group":                  _group,
        "basis":                  _basis,
        "mrsa_rule_applied":      bool(_is_mrsa_mdr),
        "not_applicable":         False,
    }

MDR_INFO = {
    "MDR": {
        "label":  "MDR -- Multi-Drug Resistant",
        "color":  "warning",
        "icon":   "⚠️",
        "detail": "مقاوم لعامل واحد على الأقل في 3 فئات دوائية أو أكثر.",
        "action": "تجنب الأدوية المقاومة. استشر الصيدلي السريري.",
    },
    "XDR": {
        "label":  "XDR -- Extensively Drug Resistant",
        "color":  "error",
        "icon":   "🔴",
        "detail": "مقاوم لمعظم الفئات الدوائية -- حساس لفئتين أو أقل فقط.",
        "action": "يستلزم استشارة متخصص. الخيارات محدودة جداً.",
    },
    "PDR": {
        "label":  "PDR -- Pan-Drug Resistant",
        "color":  "error",
        "icon":   "🚨",
        "detail": "مقاوم لجميع الفئات الدوائية المتاحة.",
        "action": "حالة طارئة -- استشارة معدية فورية. لا خيارات قياسية.",
    },
}

# ── Mechanism producer sets — CANONICAL (kept identical across modules) ──────
# Enterobacterales capable of ESBL production. "enterobacterales" (generic,
# unspeciated) is included so an ID without genus is still treated as ESBL-capable.
ESBL_PRODUCERS = frozenset([
    "escherichia coli", "e. coli", "e.coli",
    "klebsiella pneumoniae", "klebsiella spp.", "klebsiella oxytoca",
    "proteus mirabilis", "proteus spp.", "proteus vulgaris",
    "enterobacter cloacae", "enterobacter spp.", "enterobacter aerogenes",
    "citrobacter freundii", "citrobacter koseri", "citrobacter spp.",
    "serratia marcescens", "serratia spp.",
    "morganella morganii", "providencia spp.",
    "enterobacterales", "hafnia alvei",
    # 2026-11-11 (round 4): Salmonella and Shigella are Enterobacterales and
    # CTX-M ESBLs are well documented in both (Egypt included); the AmpC note
    # further down names Salmonella explicitly. Missing here, a Salmonella
    # bacteraemia with ceftriaxone AND cefotaxime R came back with no mechanism
    # at all -- piperacillin-tazobactam and cefepime RECOMMENDED -- while the
    # identical E. coli panel had both refused (IDSA AMR Guidance 2026).
    "salmonella spp.", "salmonella", "shigella spp.", "shigella",
])

# ── Organism matching now lives in clinical_utils.py ────────────────────────
# These were three separate implementations of the same idea, and the guards
# were added to two of them and forgotten on the third — twice. They are now
# thin aliases over ONE implementation so they cannot drift again.
from clinical_utils import (                                    # noqa: E402
    org_matches as _cu_org_matches,
    NON_INFORMATIVE_ORGANISM_TOKENS as _ORG_NON_INFORMATIVE,
    NEONATE_MAX_YEARS, resolve_age_years, Patient,
)


def _re_ws_collapse(text) -> str:
    """lower + strip + collapse internal whitespace. Thin alias over
    clinical_utils.collapse_ws, defined as a real function rather than an
    import alias because the AST-extraction harnesses lift it out by name."""
    from clinical_utils import collapse_ws
    return collapse_ws(text)


def _org_matches(org_l, keys) -> bool:
    """Alias over clinical_utils.org_matches — see that module for the history.

    Kept as a module-level name because the AST-extraction test harnesses slice
    functions out of this file by name and exec them in a bare namespace. The
    import is INSIDE the function for the same reason: a module-level alias
    would resolve to nothing once the function is lifted out of the file, and
    the harnesses would fail with a NameError that says nothing about the real
    dependency. Importing here makes the extracted function self-sufficient.
    """
    from clinical_utils import org_matches as _m
    return _m(org_l, keys)


def is_esbl_producer(organism: str) -> bool:
    """True only for organisms KNOWN to produce ESBL (Enterobacterales).
    ESBL is a mechanism defined for Enterobacterales — this is the single gate
    that keeps the ESBL prediction/alert off non-Enterobacterales (P. aeruginosa,
    Acinetobacter, Stenotrophomonas, Gram-positives)."""
    return _org_matches((organism or "").lower().strip(), ESBL_PRODUCERS)

# Chromosomal inducible AmpC ("SPICE/SPACE") + P. aeruginosa + Hafnia.
AMPC_PRODUCERS = frozenset([
    "enterobacter cloacae", "enterobacter spp.", "enterobacter aerogenes",
    "citrobacter freundii", "citrobacter spp.",
    "serratia marcescens", "serratia spp.",
    "morganella morganii", "providencia spp.",
    "pseudomonas aeruginosa", "hafnia alvei",
    "pseudomonas spp.",          # unspeciated: treated as P. aeruginosa (2026-11-10)
])

ESBL_MARKERS = {
    # Primary 3rd-gen oxyimino-cephalosporins -- best ESBL indicators
    "primary":   ["Ceftriaxone", "Cefotaxime", "Ceftazidime", "Cefpodoxime"],
    # Cefepime is 4th-gen -- may stay S in ESBL -> secondary only
    "secondary": ["Cefepime"],
    # Lower-gen cephalosporins
    "medium":    ["Cefuroxime", "Cefixime", "Cefaclor", "Cephalexin"],
}
CARBAPENEMS = ["Imipenem/Cilastatin", "Meropenem", "Ertapenem"]


def predict_esbl(organism: str, sir_map: Dict[str, str]) -> Dict[str, Any]:
    """
    Predict ESBL / AmpC / Carbapenemase from the resistance phenotype.
    Returns probability + confidence (0-100) + mechanism + markers.

    Logic (EUCAST/CLSI):
    • ESBL  : R to ≥1 primary 3rd-gen cephalosporin (Ceftriaxone/Cefotaxime/Ceftazidime)
    • AmpC  : 3rd-gen R + Cefoxitin R (in AmpC-prone organism)
    • Carbapenemase tiers:
        - OXA-48 suspicion : Ertapenem R, Meropenem S/I
        - high             : ≥2 carbapenems R
        - moderate         : 1 carbapenem R (or Meropenem I)
    """
    sir_map = normalize_sir_map(sir_map)
    if not sir_map:
        return {"probability": None, "confidence": 0}

    # `(organism or "")`: every other entry point in this file coerces None, this
    # one did not and raised AttributeError instead of failing closed.
    org_l = (organism or "").lower().strip()
    is_producer = is_esbl_producer(organism)   # ESBL prediction/alert: producers only
    is_ampc_prone = _org_matches(org_l, AMPC_PRODUCERS)
    if not is_producer and not is_ampc_prone:
        return {"probability": None, "confidence": 0}

    # ── FIX: never infer a mechanism from INTRINSIC resistance ────────────────
    # A drug the organism is intrinsically resistant to carries ZERO information
    # about ESBL/AmpC/carbapenemase. P. aeruginosa is intrinsically R to
    # Ceftriaxone/Cefotaxime/Cephalexin/Cefuroxime/Cefoxitin, so leaving them in
    # made the panel below read those (expected) results as ESBL markers and
    # fire a false "ESBL — high" call. Strip intrinsic-R drugs first, then infer
    # only from ACQUIRED resistance. (Local reassignment; caller's map untouched.)
    sir_map = _remove_intrinsic_resistance(organism, sir_map)

    def _ns(drug):  # non-susceptible = R or I
        return sir_map.get(drug) in ("R", "I")
    def _r(drug):
        return sir_map.get(drug) == "R"

    primary_R = [d for d in ESBL_MARKERS["primary"] if _r(d)]
    second_R  = [d for d in ESBL_MARKERS["secondary"] if _r(d)]
    med_R     = [d for d in ESBL_MARKERS["medium"] if _r(d)]
    cefoxitin_R = _r("Cefoxitin")
    # كم marker أساسي (3rd-gen cephalosporin) تم اختباره فعلاً على اللوحة؟
    # الثقة في تفسير ESBL تعتمد على اتساع اللوحة: R لدواء واحد بينما البقية غير
    # مُختبَرة أضعف بكثير من R لدواء مع اختبار البقية.
    primary_tested = [d for d in ESBL_MARKERS["primary"] if d in sir_map]
    _thin_panel = len(primary_tested) < 2

    # FIX 2026-11-10: Proteeae imipenem R is expected, not a carbapenemase marker.
    from therapy_rules import is_proteeae
    _proteeae = is_proteeae(organism)
    carb_R_list = [d for d in CARBAPENEMS if _r(d)
                   and not (_proteeae and d == "Imipenem/Cilastatin")]
    erta_R   = _r("Ertapenem")
    mero_R   = _r("Meropenem")
    mero_I   = sir_map.get("Meropenem") == "I"

    # ── 0. P. aeruginosa carbapenem resistance is NOT a carbapenemase call ────
    #
    #  Evidence for splitting this out of the generic carbapenemase tiers below:
    #
    #  * MECHANISM. In P. aeruginosa carbapenem resistance is predominantly
    #    chromosomal -- loss/down-regulation of the OprD porin, MexAB-OprM efflux
    #    up-regulation, and derepressed AmpC (PDC) -- not an acquired
    #    carbapenemase. The PorinPredict validation set found OprD loss in 454 of
    #    522 (87%) meropenem-non-susceptible CARBAPENEMASE-NEGATIVE genomes, and
    #    US CDC Emerging Infections Program surveillance describes carbapenem
    #    resistance in this species as "due primarily to chromosomal mutations
    #    that alter porins, modify efflux pump activity, and derepress intrinsic
    #    beta-lactamases". Carbapenemase-producing CRPA exists and is rising
    #    (MBLs are common in the Middle East, so an Egyptian lab must not exclude
    #    it) -- but it is the minority mechanism, not the default one.
    #
    #  * NO VALIDATED PHENOTYPIC RULE. EUCAST publishes screening / confirmation
    #    algorithms for carbapenemases in Enterobacterales. It has published none
    #    for P. aeruginosa, because the classic beta-lactam pattern cannot
    #    separate carbapenemase-producing from porin/efflux/AmpC CRPA. A "92%
    #    confidence carbapenemase" call from a disk panel therefore has no
    #    standard behind it.
    #
    #  * THE PATIENT-SAFETY BUG. The generic branch returned
    #    probability="carbapenemase", which analyze_antibiotics turns into
    #    `_is_carbapenemase` -- and that BANS every penicillin and cephalosporin
    #    even when the AST reports them Susceptible. So a P. aeruginosa with
    #    Meropenem R but Ceftazidime S had ceftazidime removed from the report.
    #    IDSA AMR guidance (v4.0, Tamma et al., CID 2024;ciae403) says the
    #    opposite: when a carbapenem-resistant isolate remains susceptible to a
    #    traditional beta-lactam, treat with that agent at high dose by extended
    #    infusion. Returning "crpa" keeps `_is_esbl_like` and `_is_carbapenemase`
    #    both False, so each agent is judged on its own AST result.
    #
    #  DTR (difficult-to-treat resistance) per IDSA = non-susceptible to ALL of:
    #  piperacillin-tazobactam, ceftazidime, cefepime, aztreonam, meropenem,
    #  imipenem-cilastatin, ciprofloxacin, levofloxacin.
    _is_pseudomonas = "pseudomonas" in org_l
    if _is_pseudomonas and (len(carb_R_list) >= 1 or mero_I):
        _DTR_AGENTS = ["Piperacillin + Tazobactam", "Ceftazidime", "Cefepime",
                       "Aztreonam", "Meropenem", "Imipenem/Cilastatin",
                       "Ciprofloxacin", "Levofloxacin"]
        _dtr_tested = [d for d in _DTR_AGENTS if d in sir_map]
        _dtr_ns     = [d for d in _dtr_tested if sir_map.get(d) in ("R", "I")]
        # DTR requires the whole first-line set to be non-susceptible. A panel
        # that tested only two of them cannot establish it, so demand >=5.
        _is_dtr = bool(_dtr_tested) and len(_dtr_ns) == len(_dtr_tested) and len(_dtr_tested) >= 5
        # Traditional anti-pseudomonal beta-lactams still reported Susceptible.
        _active_bl = [d for d in ["Piperacillin + Tazobactam", "Ceftazidime",
                                  "Cefepime", "Cefoperazone", "Cefoperazone + Sulbactam",
                                  "Aztreonam"]
                      if sir_map.get(d) == "S"]
        if _is_dtr:
            return {
                "probability": "crpa", "dtr": True, "confidence": 80,
                "active_betalactams": [],
                "mechanism": "DTR P. aeruginosa — difficult-to-treat resistance (mechanism not determined)",
                "markers_R": _dtr_ns,
                "detail": (
                    "غير حسّاس لكل الخط الأول (بيتا-لاكتام + فلوروكينولون): "
                    f"{', '.join(_dtr_ns)} — تعريف DTR في إرشادات IDSA. "
                    "الآلية غير محددة من اللوحة: قد تكون فقد بورين OprD + مضخات "
                    "الطرد + AmpC مُحدَث، أو إنزيم كاربابينيميز مكتسب (MBL شائع في "
                    "الشرق الأوسط). الاثنان يبدوان متطابقين على أقراص البيتا-لاكتام."
                ),
                "action": (
                    "الخيارات المفضّلة (IDSA AMR Guidance 2026): Ceftolozane-Tazobactam · "
                    "Ceftazidime-Avibactam · Imipenem-Relebactam · Cefiderocol — "
                    "اطلب حساسية لها تحديداً. لا تعتمد على Colistin كخط أول. "
                    "أكّد وجود كاربابينيميز (mCIM / PCR للـ MBL) فقط إذا كان "
                    "سيغيّر الاختيار — MBL يُفشل الثلاثة الأولى ويترك Cefiderocol "
                    "أو Aztreonam-Avibactam. عزل + إبلاغ مكافحة العدوى."
                ),
            }
        return {
            "probability": "crpa", "dtr": False,
            "confidence": 60 if len(carb_R_list) >= 2 else 45,
            "active_betalactams": _active_bl,
            "mechanism": "Carbapenem-resistant P. aeruginosa — mechanism not determined",
            "markers_R": carb_R_list or ["Meropenem (I)"],
            "detail": (
                f"مقاومة كاربابينيم ({', '.join(carb_R_list) or 'Meropenem I'}) في "
                "P. aeruginosa. الآلية الأشيع فقد/تقليل بورين OprD ± مضخات طرد "
                "± AmpC مُحدَث — وليست إنزيم كاربابينيميز. لا يوجد في EUCAST "
                "خوارزمية معتمدة تفرّق بينهما من أقراص البيتا-لاكتام."
                + (f"  \nلا يزال حسّاساً لـ: {', '.join(_active_bl)}."
                   if _active_bl else "")
            ),
            "action": (
                (f"ابدأ بـ {_active_bl[0]} بجرعة عالية وتسريب ممتد (extended infusion) "
                 "— IDSA: العزلة المقاومة للكاربابينيم والحسّاسة لبيتا-لاكتام تقليدي "
                 "تُعالَج بذلك البيتا-لاكتام، لا بـ Colistin. "
                 if _active_bl else
                 "راجع Ceftazidime / Cefepime / Piperacillin-Tazobactam / Aztreonam "
                 "في نفس اللوحة قبل التصعيد. ")
                + "أكّد الكاربابينيميز (mCIM / PCR) فقط إذا كان سيغيّر العلاج."
            ),
        }

    # ── 1. Carbapenemase tiers (highest priority) ─────────────────────────
    if len(carb_R_list) >= 2:
        return {
            "probability": "carbapenemase",
            "confidence": 92,
            "mechanism": "Carbapenemase (KPC / MBL / OXA-48-like) — Predicted",
            "markers_R": carb_R_list + primary_R,
            "detail": f"مقاومة لـ ≥2 كاربابينيم ({', '.join(carb_R_list)}) -- نمط Carbapenemase صريح.",
            "action": ("أرسل للمختبر المرجعي فوراً وحدّد نوع الإنزيم (NG-Test CARBA-5 أو PCR). عزل صارم. "
                       "KPC: Ceftazidime-avibactam أو Meropenem-vaborbactam أو Imipenem-relebactam؛ "
                       "OXA-48: Ceftazidime-avibactam؛ NDM/VIM/IMP: Aztreonam-avibactam أو "
                       "Ceftazidime-avibactam + Aztreonam أو Cefiderocol (IDSA 2026). "
                       "Colistin ليس خياراً مفضّلاً."),
        }
    if erta_R and (sir_map.get("Meropenem") in ("S", "I")) and not mero_R:
        # Ertapenem-R with Meropenem-S/I. Suggestive of OXA-48 (common in Egypt /
        # Middle East, which lifts the prior) -- but the SAME pattern arises from
        # porin loss + ESBL/AmpC with no true carbapenemase, and Ertapenem is the
        # carbapenem most affected by non-carbapenemase mechanisms. Confirm-first
        # signal, not a high-confidence call: keep confidence moderate and name
        # the alternative mechanism in the read-out.
        return {
            "probability": "possible_carbapenemase",
            "confidence": 62,
            "mechanism": "Possible OXA-48-like carbapenemase OR porin loss + ESBL/AmpC — Predicted",
            "markers_R": ["Ertapenem"] + primary_R,
            "detail": ("Ertapenem R مع Meropenem S/I -- نمط قد يوحي بـ OXA-48 (شائع في "
                       "مصر/الشرق الأوسط) أو بفقدان بورين + ESBL/AmpC بدون إنزيم "
                       "كاربابينيميز حقيقي."),
            "action": "أكد بـ mCIM / PCR (OXA-48) قبل اعتماد التشخيص. راقب بحذر؛ قد تكون الكاربابينيمات أقل فعالية.",
        }
    if len(carb_R_list) == 1 or mero_I:
        return {
            "probability": "possible_carbapenemase",
            "confidence": 55,
            "mechanism": "Possible carbapenemase (low-level) — Predicted",
            "markers_R": carb_R_list or ["Meropenem (I)"],
            "detail": "مقاومة/توسط لكاربابينيم واحد -- يستلزم اختبار تأكيدي.",
            "action": "أجرِ mCIM/CarbaNP. قد يكون فقدان بورين + ESBL/AmpC وليس carbapenemase حقيقياً.",
        }

    # ── 2. AmpC — Enterobacterales AmpC organisms only ────────────────────
    # AmpC (SPICE/SPACE) attribution requires an ENTEROBACTERALE (is_producer);
    # this keeps AmpC/ESBL mechanism calls scoped to Enterobacterales and lets a
    # non-Enterobacterale (P. aeruginosa/Hafnia) fall through to the producer
    # gate below. Cefoxitin is NOT required: it is intrinsically resistant in
    # these organisms and is stripped before marker computation, so its absence
    # here is expected — 3rd-gen cephalosporin R in an AmpC-prone Enterobacterale
    # is itself the derepression signal.
    if is_ampc_prone and is_producer and primary_R:
        return {
            "probability": "ampc",
            "confidence": 75,
            "mechanism": "Possible AmpC β-lactamase (Predicted)",
            "markers_R": primary_R,
            "detail": "مقاومة لـ 3rd-gen cephalosporin في كائن Enterobacterale منتج لـ AmpC مزمن -- نمط AmpC وليس ESBL.",
            "action": "تجنب 3rd-gen cephalosporins حتى لو S. استخدم Cefepime أو Carbapenem. لا يُكتشف بـ DDST.",
        }

    # ── 2b. Plasmid-mediated AmpC in a NON-AmpC-prone Enterobacterale ─────
    #  Cefoxitin is the classic phenotypic discriminator: ESBLs do not hydrolyse
    #  cephamycins, so a true ESBL is normally cefoxitin-SUSCEPTIBLE, whereas AmpC
    #  (chromosomal or plasmid-borne) IS cefoxitin-resistant. In organisms with no
    #  chromosomal AmpC (E. coli, Klebsiella, Proteus mirabilis, Salmonella) a
    #  cefoxitin-R + 3rd-gen-R phenotype therefore points at acquired pAmpC or at
    #  porin loss -- not at a plain ESBL.
    #
    #  This is a QUALIFIER, not a re-diagnosis: cefoxitin resistance can also arise
    #  from porin loss in a genuine ESBL producer, so the report names both
    #  possibilities and tells the lab what the confirmatory test will do.
    if (is_producer and not is_ampc_prone and primary_R and cefoxitin_R
            and not _thin_panel):
        return {
            "probability": "ampc_plasmid",
            "confidence": 70,
            "mechanism": "Possible plasmid-mediated AmpC (pAmpC) or porin loss — not a plain ESBL",
            "markers_R": primary_R + ["Cefoxitin"],
            "detail": (
                "مقاومة للجيل الثالث **مع** مقاومة للـ Cefoxitin في كائن لا يحمل "
                "AmpC كروموسومي. الـ ESBL الكلاسيكي لا يحلّل السيفاميسينات، فيكون "
                "عادةً حسّاساً للـ Cefoxitin — والنمط ده يرجّح AmpC مكتسب "
                "(CMY-2 وأشباهه) أو فقد بورين، وليس ESBL بسيط."
            ),
            "action": (
                "⚠️ اختبار التأكيد (DDST / combination disk) قد يخرج **سالباً** — "
                "الكلافولانيت لا يثبّط AmpC. لا تعتمد على Amoxicillin-Clavulanate. "
                "الـ Cefepime غالباً يظل فعّالاً في AmpC (راجع نتيجته على اللوحة)، "
                "والكاربابينيم هو الخيار الآمن في العدوى الشديدة. "
                "التمييز النهائي يحتاج PCR."
            ),
        }

    # ── 3. ESBL (Enterobacterales ONLY) ───────────────────────────────────
    # ESBL is a mechanism DEFINED for Enterobacterales. A non-Enterobacterale
    # that is AmpC-prone (e.g. P. aeruginosa) must NEVER be labelled "ESBL":
    # any 3rd-gen cephalosporin R that survives intrinsic-stripping (i.e. an
    # ACQUIRED Ceftazidime-R) reflects derepressed chromosomal AmpC / efflux
    # (MexAB-OprM) / porin loss — not an ESBL.
    # A non-Enterobacterale (e.g. P. aeruginosa) is NEVER an ESBL producer.
    # After intrinsic-stripping, any residual 3rd-gen cephalosporin R is judged
    # on the drug's own AST result (an R drug is banned as R regardless); we do
    # NOT emit an ESBL/AmpC mechanism call here, which prevents both the false
    # "ESBL ALERT" and any "(ESBL)" label bleed onto this organism's β-lactams.
    if not is_producer:
        return {"probability": "low", "confidence": 10}

    if len(primary_R) >= 2:
        return {
            "probability": "high",
            "confidence": 88,
            "mechanism": "ESBL (Extended-Spectrum β-Lactamase) — Predicted",
            "markers_R": primary_R + second_R,
            "detail": f"مقاومة لـ {', '.join(primary_R)} -- احتمال ESBL مرتفع.",
            "action": "استخدم Carbapenem للعدوى الشديدة (MERINO 2018). تجنب جميع cephalosporins.",
        }
    if len(primary_R) == 1:
        # Classic single-marker ESBL pattern (e.g., Ceftriaxone R, Meropenem S)
        carbS = any(sir_map.get(d) == "S" for d in CARBAPENEMS)
        _base_conf = 72 if carbS else 60
        # لوحة رفيعة (marker أساسي واحد مُختبَر فقط) -> خفّض الثقة، فلا يُبنى حكم
        # ESBL قوي على اختبار سيفالوسبورين واحد بينما لم تُختبر بقية الـ 3rd-gen.
        if _thin_panel:
            _base_conf = min(_base_conf, 45)
        _detail = f"مقاومة لـ {primary_R[0]}" + (
            " مع كاربابينيم حساس -- نمط ESBL كلاسيكي." if carbS else ".")
        if _thin_panel:
            _detail += (" ⚠️ لوحة محدودة: تم اختبار سيفالوسبورين أساسي واحد فقط "
                        "-- التفسير أقل موثوقية؛ وسّع اللوحة (Ceftazidime/Cefotaxime).")
        return {
            # FIX 2026-11-10 (round 2): a thin panel forced "moderate", and at
            # "moderate" the engine applied NO ESBL handling at all -- E. coli in
            # blood with Ceftriaxone R as the only 3rd-gen tested had
            # piperacillin-tazobactam and cefepime recommended without a word.
            # IDSA AMR Guidance: ceftriaxone non-susceptibility is the accepted
            # proxy for ESBL production in E. coli / Klebsiella / P. mirabilis.
            "probability": ("high" if (primary_R[0] in ("Ceftriaxone", "Cefotaxime")
                                       or (carbS and not _thin_panel)) else "moderate"),
            "confidence": (max(_base_conf, 70)
                           if primary_R[0] in ("Ceftriaxone", "Cefotaxime") else _base_conf),
            "mechanism": "Probable ESBL — Predicted",
            "markers_R": primary_R + med_R,
            "detail": _detail,
            "action": "أكد بـ Double-Disk Synergy Test (DDST) أو PCR. عامل كـ ESBL حتى التأكيد.",
        }
    if len(med_R) >= 2:
        return {
            "probability": "moderate",
            "confidence": 50,
            "mechanism": "Possible ESBL (lower-gen cephalosporin resistance) — Predicted",
            "markers_R": med_R,
            "detail": "مقاومة لـ ≥2 من الجيل الأقل -- يستدعي تأكيد ESBL.",
            "action": "أجرِ DDST. قد يكون ESBL مبكر أو آلية أخرى.",
        }

    return {"probability": "low", "confidence": 10}

# =========================================================
# Pathogenicity Assessment Module -- v2
# Covers: Urine, Sputum (Murray-Washington), Blood (SIRS),
#         Wound/Pus, CSF, Swab
# Includes: Pediatric thresholds, ABU detection
# =========================================================
# Organism-name canonicalization for pathogenicity membership tests
# =========================================================
# The app passes ORGANISM_PROFILE short names ("E. coli", "MRSA", "Klebsiella
# spp."), but the pathogenicity lists historically used full binomials. Direct
# `organism in LIST` tests silently failed -> mis-scored non-urine organisms.
# Canonicalize BOTH sides so membership is spelling-independent.
# ── Pathogenicity scoring moved to pathogenicity.py (2026-08-03) ────────────
# 904 lines: the colony-count parser, the verbal-report tables, the three-state
# report classifier and assess_pathogenicity() itself. They were pure functions
# over their own tables the whole time, sitting in the middle of a 10,400-line
# file between the UI and the PDF writer. Re-exported here so every existing
# caller and every AST-extraction test harness still finds them by name.
from pathogenicity import (                                          # noqa: E402,F401
    assess_pathogenicity,
    _ORG_CANON_MAP, _canon_org, _org_in,
    _CFU_SUPERSCRIPTS, _CFU_VERBAL, _PUS_VERBAL,
    _parse_cfu, _cfu_report_state, _score_colony_count, _parse_pus,
    # v3 option lists -- the UI and the engine read the same strings
    PATHO_ENGINE_VERSION, GRAM_STAIN_OPTIONS, URINE_COLLECTION_METHODS,
    URINE_SYMPTOMS, HOST_FACTORS_URINE, HOST_FACTORS_OTHER,
    WOUND_TYPES, WOUND_SIGNS, RESPIRATORY_SIGNS, gram_options_for,
)
from final_checklist import build_final_checklist, summarize as summarize_checklist, ICON as CHECK_ICON  # noqa: E402




# ═══════════════════════════════════════════════════════════════════════
# CLINICAL DECISION ENGINES -- v4.0
# ① Treatment Duration  ② IV->PO Switch  ③ Hepatic Dosing (Child-Pugh)
# ④ Combination Therapy  ⑤ De-escalation Advisor
# References: IDSA AMR Guidance 2026 | Sanford 2025 | WHO AWaRe 2025
#             MERINO 2018 | NINJA 2020 | ATTACK 2023 | STOP-IT 2015
# ═══════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════
# ENGINE 1 -- Treatment Duration Engine
# IDSA AMR Guidance 2026 | Sanford Guide 2025 | ATS/IDSA CAP 2019
# IDSA cUTI 2025 | IDSA SSTI 2014 | STOP-IT trial 2015
# ═══════════════════════════════════════════════════════════════════════
# Durations re-read 2026-11-10 against IDSA cUTI 2025, BALANCE (NEJM 2025),
# ATS/IDSA HAP/VAP 2016 and IDSA bacterial meningitis. Defects fixed: cUTI and
# pyelonephritis were 10-14 days (14 for men), GNB bacteraemia was a flat 14
# days IV with no oral step-down, HAP/VAP sent non-fermenters to 14 days, and
# every CSF isolate that was not a pneumococcus got the 21-day GNB course --
# including N. meningitidis and H. influenzae (7 days). "IDSA UTI 2022" was
# not a real citation.
TREATMENT_DURATION_DB: Dict[str, Any] = {
    "UTI_uncomplicated_female": {
        "label": "Uncomplicated cystitis (Female)",
        "days": (1, 7), "standard": 5, "iv_days": 0, "po_days": 5,
        "notes": "Agent-dependent: Nitrofurantoin 5d | TMP-SMX 3d | Fosfomycin 3 g single dose | "
                 "beta-lactam 3-7d.",
        "follow_up_culture": False, "ref": "IDSA/ESCMID uncomplicated cystitis 2011",
    },
    "UTI_complicated": {
        "label": "Complicated UTI (incl. men, catheter-associated)",
        "days": (5, 14), "standard": 7, "iv_days": 0, "po_days": 7,
        "notes": "7d if prompt response (FQ 5-7d) -- men included. 10-14d only for delayed "
                 "response or an unresolved urological source. Oral step-down once improving.",
        "follow_up_culture": False, "ref": "IDSA cUTI Guideline 2025",
    },
    "Pyelonephritis_outpatient": {
        "label": "Pyelonephritis (Outpatient)",
        "days": (5, 7), "standard": 7, "iv_days": 0, "po_days": 7,
        "notes": "FQ 5-7d | TMP-SMX or beta-lactam 7d. Verify sensitivities.",
        "follow_up_culture": False, "ref": "IDSA cUTI Guideline 2025",
    },
    "Pyelonephritis_inpatient": {
        "label": "Pyelonephritis / cUTI (Inpatient)",
        "days": (7, 14), "standard": 7, "iv_days": 2, "po_days": 5,
        "notes": "7d total if prompt response (incl. urinary-source bacteraemia); IV until "
                 "afebrile 24-48h -> high-bioavailability oral step-down.",
        "follow_up_culture": False, "ref": "IDSA cUTI Guideline 2025",
    },
    "CAP_mild": {
        "label": "CAP -- Mild (Outpatient)",
        "days": (5, 7), "standard": 5, "iv_days": 0, "po_days": 5,
        "notes": "5 days adequate for mild CAP. No CURB-65 risk factors.",
        "follow_up_culture": False, "ref": "IDSA/ATS CAP Guidelines 2019",
    },
    "CAP_moderate": {
        "label": "CAP -- Moderate (Inpatient)",
        # FIX 2026-11-10 (round 2): was 7-10 d. ATS/IDSA 2019: treat until
        # clinically stable and for no less than 5 days; ATS 2025 suggests even
        # shorter courses for stable non-severe CAP.
        "days": (5, 7), "standard": 5, "iv_days": 2, "po_days": 3,
        "notes": "5d minimum and until clinically stable (afebrile 48-72h, <=1 instability "
                 "sign); ATS 2025: 3-5d is enough for non-severe CAP that stabilises early. "
                 "IV -> oral step-down at stability. 7d for MRSA / P. aeruginosa.",
        "follow_up_culture": False, "ref": "ATS/IDSA CAP 2019 | ATS CAP 2025",
    },
    "CAP_severe": {
        "label": "CAP -- Severe (ICU)",
        # FIX 2026-11-10 (round 2): was 10-14 d. Severity alone does not
        # lengthen CAP therapy; complications and specific pathogens do.
        "days": (5, 10), "standard": 7, "iv_days": 4, "po_days": 3,
        "notes": ">=5d and until clinically stable; 7d for MRSA / P. aeruginosa (ATS/IDSA 2019). "
                 "Longer only for empyema, abscess, S. aureus bacteraemia, Legionella with slow "
                 "response. PCT can support stopping.",
        "follow_up_culture": True, "ref": "ATS/IDSA CAP 2019 | ATS CAP 2025",
    },
    "HAP_VAP": {
        "label": "HAP / VAP",
        "days": (7, 14), "standard": 7, "iv_days": 7, "po_days": 0,
        "notes": "7d for HAP and VAP, non-fermenters included (ATS/IDSA 2016). Longer only for "
                 "slow response, abscess, empyema or immunosuppression.",
        "follow_up_culture": False, "ref": "ATS/IDSA HAP/VAP 2016",
    },
    "Bacteremia_GNB": {
        "label": "GNB Bacteremia",
        "days": (7, 14), "standard": 7, "iv_days": 3, "po_days": 4,
        "notes": "7d if the source is controlled and the patient is improving (BALANCE, NEJM 2025); "
                 "14d for uncontrolled source, severe immunosuppression or slow response. Oral "
                 "step-down (FQ / TMP-SMX / high-bioavailability beta-lactam) once stable.",
        "follow_up_culture": False, "ref": "BALANCE 2025 | IDSA cUTI 2025",
    },
    "Bacteremia_Enterococcus": {
        "label": "Enterococcal Bacteremia",
        "days": (7, 14), "standard": 7, "iv_days": 7, "po_days": 0,
        "notes": "7-14d if uncomplicated and the source is removed. E. faecalis: assess for "
                 "endocarditis (DENOVA score / echo) -- endocarditis needs 4-6 weeks.",
        "follow_up_culture": True, "ref": "Expert consensus | ESC Endocarditis 2023",
    },
    "Bacteremia_Strep": {
        "label": "Streptococcal Bacteremia",
        "days": (10, 14), "standard": 10, "iv_days": 5, "po_days": 5,
        "notes": "10-14d (oral step-down possible once stable). Exclude endocarditis if persistent "
                 "or viridans group.",
        "follow_up_culture": False, "ref": "Expert consensus",
    },
    "Bacteremia_CoNS": {
        "label": "Coagulase-negative Staphylococcal Bacteremia",
        "days": (5, 14), "standard": 7, "iv_days": 7, "po_days": 0,
        "notes": "Treat only if TRUE infection (>=2 sets / device). 5-7d after catheter removal; "
                 "10-14d with catheter retention + lock therapy. Single positive bottle = "
                 "contaminant until proven otherwise.",
        "follow_up_culture": True, "ref": "IDSA CRBSI 2009",
    },
    "Bacteremia_MSSA": {
        "label": "MSSA Bacteremia",
        "days": (14, 42), "standard": 14, "iv_days": 14, "po_days": 0,
        "notes": "Min 14d from first negative culture (uncomplicated) | 28-42d (complicated/"
                 "endovascular). Echo + repeat blood cultures mandatory. ID consult.",
        "follow_up_culture": True, "ref": "IDSA MRSA 2011 (SAB principles) | expert consensus",
    },
    "Bacteremia_MRSA": {
        "label": "MRSA Bacteremia",
        "days": (14, 42), "standard": 14, "iv_days": 14, "po_days": 0,
        "notes": "Vancomycin AUC/MIC target 400-600. Min 14d (uncomplicated) | 42d (endocarditis).",
        "follow_up_culture": True, "ref": "IDSA MRSA Guidelines 2011 | ASHP/IDSA/PIDS/SIDP vancomycin consensus 2020",
    },
    "Meningitis_pneumococcal": {
        "label": "Pneumococcal Meningitis",
        "days": (10, 14), "standard": 14, "iv_days": 14, "po_days": 0,
        "notes": "Dexamethasone 0.15 mg/kg q6h x 2-4d, started before or with the first "
                 "antibiotic dose. IV throughout.",
        "follow_up_culture": True, "ref": "IDSA Bacterial Meningitis 2004",
    },
    "Meningitis_meningococcal": {
        "label": "Meningococcal Meningitis",
        "days": (7, 7), "standard": 7, "iv_days": 7, "po_days": 0,
        "notes": "7d IV. Chemoprophylaxis for close contacts.",
        "follow_up_culture": False, "ref": "IDSA Bacterial Meningitis 2004",
    },
    "Meningitis_haemophilus": {
        "label": "H. influenzae Meningitis",
        "days": (7, 7), "standard": 7, "iv_days": 7, "po_days": 0,
        "notes": "7d IV. Dexamethasone in children (before/with first dose).",
        "follow_up_culture": False, "ref": "IDSA Bacterial Meningitis 2004",
    },
    "Meningitis_listeria": {
        "label": "Listeria Meningitis",
        "days": (21, 42), "standard": 21, "iv_days": 21, "po_days": 0,
        "notes": ">=21d IV (longer for rhombencephalitis/abscess). Ampicillin +/- gentamicin.",
        "follow_up_culture": True, "ref": "IDSA Bacterial Meningitis 2004",
    },
    "Meningitis_GBS": {
        "label": "Group B Streptococcal Meningitis",
        "days": (14, 21), "standard": 14, "iv_days": 14, "po_days": 0,
        "notes": "14-21d IV.", "follow_up_culture": True, "ref": "IDSA Bacterial Meningitis 2004",
    },
    "Meningitis_GNB": {
        "label": "Gram-Negative Meningitis",
        "days": (21, 21), "standard": 21, "iv_days": 21, "po_days": 0,
        "notes": "21d IV for aerobic Gram-negative bacillary meningitis. Verify CSF sterilization.",
        "follow_up_culture": True, "ref": "IDSA Bacterial Meningitis 2004",
    },
    # ── Added 2026-11-11 (round 4) ─────────────────────────────────────────
    # Every CSF isolate that was not pneumococcus / meningococcus /
    # H. influenzae / Listeria / GBS fell to "Gram-Negative Meningitis, 21 d" --
    # S. aureus, MRSA, CoNS, enterococci and unidentified Gram-positive cocci
    # included.
    "Meningitis_staph": {
        "label": "Staphylococcal Meningitis / Ventriculitis",
        "days": (10, 14), "standard": 14, "iv_days": 14, "po_days": 0,
        "notes": "Usually shunt / EVD / post-neurosurgical: remove or externalise the device. "
                 "S. aureus 10-14d; CoNS 10d with minimal CSF abnormality, 10-14d with "
                 "pleocytosis / low glucose -- counted from the first sterile CSF culture. "
                 "Repeat CSF cultures until sterile.",
        "follow_up_culture": True,
        "ref": "IDSA Healthcare-Associated Ventriculitis and Meningitis 2017",
    },
    "Meningitis_other": {
        "label": "Bacterial Meningitis (other / not fully identified)",
        "days": (10, 21), "standard": 14, "iv_days": 14, "po_days": 0,
        "notes": "No organism-specific duration: set it on the FINAL identification and the CSF "
                 "response (pneumococcus 10-14d, GBS 14-21d, staphylococci 10-14d, enterococci / "
                 "viridans streptococci >=14d). Identify the organism; ID consultation.",
        "follow_up_culture": True,
        "ref": "IDSA Bacterial Meningitis 2004 | IDSA 2017",
    },
    "Bacteremia_GPC_unidentified": {
        "label": "Gram-positive cocci bacteremia (not yet identified)",
        "days": (5, 14), "standard": 14, "iv_days": 14, "po_days": 0,
        "notes": "Treat as S. aureus until identified (clusters on Gram stain): repeat blood "
                 "cultures, no oral step-down, echo if S. aureus. Re-set the duration on the "
                 "identification -- CoNS 5-7d after line removal, streptococci 10-14d, "
                 "enterococci 7-14d.",
        "follow_up_culture": True, "ref": "IDSA MRSA 2011 (SAB principles) | IDSA CRBSI 2009",
    },
    "Bacteremia_Listeria": {
        "label": "Listeria Bacteremia",
        "days": (14, 21), "standard": 14, "iv_days": 14, "po_days": 0,
        "notes": "Ampicillin +/- gentamicin, 2 weeks IV for bacteraemia without CNS involvement; "
                 "LP / brain imaging if any neurological sign (>=21d for CNS infection). "
                 "Cephalosporins are inactive.",
        "follow_up_culture": True, "ref": "Expert consensus | IDSA Bacterial Meningitis 2004",
    },
    "Bacteremia_anaerobe": {
        "label": "Anaerobic Bacteremia",
        "days": (7, 14), "standard": 10, "iv_days": 3, "po_days": 7,
        "notes": "Duration follows the source (intra-abdominal, pelvic, abscess) and its control; "
                 "drain collections. Metronidazole is ~100% bioavailable -- oral step-down once "
                 "stable.",
        "follow_up_culture": False, "ref": "Expert consensus | IDSA IAI 2010",
    },
    "SSTI_mild": {
        "label": "SSTI -- Mild (Cellulitis)",
        "days": (5, 7), "standard": 5, "iv_days": 0, "po_days": 5,
        "notes": "5d oral adequate for uncomplicated cellulitis without systemic signs.",
        "follow_up_culture": False, "ref": "IDSA SSTI Guidelines 2014",
    },
    "SSTI_moderate": {
        "label": "SSTI -- Moderate",
        "days": (7, 14), "standard": 7, "iv_days": 2, "po_days": 5,
        "notes": "IV until afebrile + local improvement -> step-down oral.",
        "follow_up_culture": False, "ref": "IDSA SSTI 2014",
    },
    "SSTI_severe": {
        "label": "SSTI -- Severe / Necrotizing",
        "days": (10, 21), "standard": 14, "iv_days": 14, "po_days": 0,
        "notes": "IV + surgical source control. ID consult mandatory.",
        "follow_up_culture": True, "ref": "IDSA SSTI 2014",
    },
    "Osteomyelitis": {
        "label": "Osteomyelitis",
        "days": (42, 84), "standard": 42, "iv_days": 14, "po_days": 28,
        "notes": "IV 2 weeks -> high-bioavailability oral 4+ weeks. Total ≥6 weeks.",
        "follow_up_culture": True, "ref": "IDSA Vertebral Osteomyelitis 2015 | OVIVA (NEJM 2019)",
    },
    "Intraabdominal_mild": {
        "label": "Intraabdominal Infection (Source Controlled)",
        "days": (4, 7), "standard": 4, "iv_days": 2, "po_days": 2,
        "notes": "4d if source controlled (STOP-IT trial 2015). Extend only for ongoing sepsis.",
        "follow_up_culture": False, "ref": "IDSA IAI 2010 | STOP-IT 2015",
    },
    "Intraabdominal_severe": {
        "label": "Intraabdominal Infection (Severe)",
        # FIX 2026-11-10 (round 2): was 7-14 d. With adequate source control
        # ~4 days is as good as longer (STOP-IT, NEJM 2015; SIS 2017).
        "days": (4, 7), "standard": 5, "iv_days": 4, "po_days": 1,
        "notes": "4-7d AFTER adequate source control (STOP-IT). Persisting signs beyond day 7 "
                 "mean failed source control -> re-image, do not just extend antibiotics.",
        "follow_up_culture": True, "ref": "STOP-IT (NEJM 2015) | SIS 2017 | IDSA IAI 2010",
    },
    "GI_mild": {
        "label": "GI Infection -- Mild/Moderate (Supportive Care)",
        "days": (0, 5), "standard": 0, "iv_days": 0, "po_days": 0,
        "notes": "Most GI infections: supportive care (fluids, electrolytes). "
                 "Antibiotics ONLY for: bloody diarrhea, immunocompromised, "
                 "severe dehydration, Salmonella typhi, Shigella, C. diff.",
        "follow_up_culture": False, "ref": "IDSA Foodborne GI 2017 | WHO 2025",
    },
    "GI_severe": {
        "label": "Severe GI Infection / Immunocompromised",
        "days": (3, 7), "standard": 5, "iv_days": 2, "po_days": 3,
        "notes": "Azithromycin or Ciprofloxacin 3-5d. C. diff -> Fidaxomicin or Vancomycin 10d (IDSA/SHEA 2021). "
                 "Salmonella typhi -> 7-14d. Reassess daily.",
        "follow_up_culture": True, "ref": "IDSA 2017 | Sanford 2025",
    },
}

def suggest_severity(
    specimen: str, age: int, sex: str,
    is_preg: bool, is_renal: bool, cl_cr: float,
    host_factors: Optional[List] = None,
    symptoms: Optional[List] = None,
) -> Dict[str, Any]:
    """
    Auto-suggest infection severity based on patient risk factors.
    Clinical basis: IDSA cUTI 2025 | IDSA CAP 2019 | Sanford 2025 |
                    AHA Infective Endocarditis 2015 | SCCM Sepsis-3 2016.

    Returns:
        suggested: "mild" | "moderate" | "severe"
        reasons:   list of clinical reasons
        override:  True (user can still change it)
    """
    _cat   = classify_specimen(specimen)
    hf     = [h.lower() for h in (host_factors or [])]
    syms   = [s.lower() for s in (symptoms or [])]

    reasons_severe   = []
    reasons_moderate = []
    reasons_mild     = []

    # ── Universal red flags -> SEVERE ─────────────────────────────────────
    if any(k in " ".join(syms) for k in
           ["septic shock", "hypotension", "icu", "bacteremia",
            "altered consciousness", "confusion", "rigors"]):
        reasons_severe.append("Systemic sepsis signs / shock")

    if "central line" in " ".join(hf) or "immunocompromised" in " ".join(hf):
        reasons_severe.append("Immunocompromised / central line")

    # ── Specimen-specific logic ────────────────────────────────────────────
    if _cat == "urine":
        # IDSA: complicated UTI = male, pregnant, elderly, renal, catheter
        if sex == "Male":
            reasons_moderate.append("Male UTI -> complicated (IDSA cUTI 2025)")
        if is_preg:
            reasons_moderate.append("Pregnancy -> complicated UTI")
        if age >= 65:
            reasons_moderate.append("Age ≥ 65 -> complicated UTI")
        _eff, _meas = resolve_crcl(cl_cr, is_renal)
        if is_renal and _eff is not None and _eff < 60:
            reasons_moderate.append(
                f"Renal impairment (CrCl {_eff:.0f}"
                f"{'' if _meas else ', assumed'}) -> complicated")
        if any(k in " ".join(hf) for k in ["catheter", "urologic", "diabetes"]):
            reasons_moderate.append("Host risk factor (DM / catheter / urologic anomaly)")
        if any(k in " ".join(syms) for k in ["fever", "flank pain", "costovertebral"]):
            reasons_moderate.append("Upper UTI symptoms -> pyelonephritis")
        if not reasons_moderate and not reasons_severe:
            if sex == "Female" and age < 65 and not is_preg and not is_renal:
                reasons_mild.append("Young healthy female -> uncomplicated cystitis (IDSA/ESCMID 2011)")

    elif _cat == "sputum":
        # CURB-65 proxy: Age ≥65, renal, altered mentation
        curb = 0
        if age >= 65:         curb += 1; reasons_moderate.append("Age ≥ 65 (CURB-65)")
        if is_renal:          curb += 1; reasons_moderate.append("Renal impairment (CURB-65)")
        if any(k in " ".join(syms) for k in ["confusion", "altered"]):
            curb += 1; reasons_severe.append("Altered mentation (CURB-65 ≥3)")
        if curb == 0:
            reasons_mild.append("No CURB-65 risk factors -> mild CAP")

    elif _cat == "blood":
        # Bacteremia is always at least moderate
        reasons_moderate.append("Bloodstream infection -> minimum moderate")
        if age >= 65 or is_renal:
            reasons_severe.append("Bacteremia + age ≥65 / renal impairment -> severe")

    elif _cat == "csf":
        # CNS = always severe
        reasons_severe.append("CNS infection -> always severe")

    elif _cat in ("wound", "pus"):
        if any(k in " ".join(hf) for k in ["diabetes", "immunocompromised"]):
            reasons_moderate.append("Wound infection + DM/immunocompromised")
        elif not reasons_moderate and not reasons_severe:
            reasons_mild.append("Simple SSTI without systemic features")

    elif _cat in ("stool", "abdomen"):
        if age >= 65 or is_renal or is_preg:
            reasons_moderate.append("GI infection + high-risk host")
        if any(k in " ".join(syms) for k in ["bloody", "fever", "dehydration"]):
            reasons_moderate.append("Febrile / bloody diarrhea -> moderate+")
        else:
            reasons_mild.append("GI infection without systemic features -> supportive")

    # ── Final decision ────────────────────────────────────────────────────
    if reasons_severe:
        return {"suggested": "severe",   "reasons": reasons_severe,   "override": True}
    elif reasons_moderate:
        return {"suggested": "moderate", "reasons": reasons_moderate, "override": True}
    else:
        return {"suggested": "mild",     "reasons": reasons_mild or ["No risk factors identified"],
                "override": True}


def _sir_lookup(drug: str, sir_map: Dict[str, str]) -> Optional[str]:
    """Return S/I/R for `drug` from sir_map, matching keys tolerantly."""
    if not sir_map:
        return None
    try:
        from abx_guidelines import normalize_abx_key
        target = normalize_abx_key(drug)
        for k, v in sir_map.items():
            if normalize_abx_key(k) == target:
                return ((v or "").strip().upper()[:1]) or None
    except Exception:
        low = {k.lower(): v for k, v in sir_map.items()}
        val = low.get(drug.lower())
        return ((val or "").strip().upper()[:1]) or None
    return None


_REGIMEN_TOKENS = [
    ("TMP-SMX",        ["Trimethoprim/Sulfamethoxazole"]),
    ("Nitrofurantoin", ["Nitrofurantoin"]),
    ("Fosfomycin",     ["Fosfomycin"]),
    ("FQ",             ["Ciprofloxacin", "Ofloxacin", "Norfloxacin",
                        "Levofloxacin", "Gatifloxacin", "Moxifloxacin"]),
]


def _regimen_token_status(drug_names, sir_map) -> str:
    seen = [s for s in (_sir_lookup(d, sir_map) for d in drug_names) if s]
    if not seen:
        return "NT"
    if "S" in seen:
        return "S"
    if "I" in seen:
        return "I"
    return "R"


def annotate_regimen_note(note: str, sir_map: Dict[str, str], lang: str = "ar") -> str:
    """Flag each guideline agent quoted in a duration note with its real AST
    status, so the note can never contradict the antibiogram. Sensitive agents
    stay unflagged; R / I / not-tested agents are marked."""
    if not note or not sir_map:
        return note
    flags = {
        "R":  " ⚠️[R -- مقاوم في هذه المزرعة]" if lang == "ar" else " ⚠️[R -- resistant here]",
        "I":  " [I]",
        "NT": " [غير مُختبر]" if lang == "ar" else " [not tested]",
    }
    out = note
    for token, drugs in _REGIMEN_TOKENS:
        if token not in out:
            continue
        flag = flags.get(_regimen_token_status(drugs, sir_map), "")
        if not flag:
            continue
        out = re.sub(r"(?<![\w-])" + re.escape(token) + r"(?![\w-])",
                     lambda m: m.group(0) + flag, out, count=1)
    return out


def get_treatment_duration(
    specimen: str, organism: str, syndrome: str,
    age: int, sex: str, is_renal: bool,
    phenotypes: List[Dict], severity: str = "moderate",
) -> Dict[str, Any]:
    """Treatment Duration Engine -- IDSA AMR Guidance 2026 | Sanford Guide 2025"""
    org  = organism.lower()
    synd = (syndrome or "").lower()
    _cat = classify_specimen(specimen)
    ph   = [p.get("phenotype", "") for p in phenotypes]
    has_mrsa = "MRSA" in ph
    has_mdr  = any(x in ph for x in ["MDR", "XDR", "PDR", "CRE", "CRPA", "CRAB"])

    key = None
    if _cat == "urine":
        if any(k in synd for k in ["pyelonephritis", "upper", "kidney", "pyelo"]):
            # Syndrome explicitly says pyelonephritis
            key = "Pyelonephritis_inpatient" if severity == "severe" else "Pyelonephritis_outpatient"
        elif severity == "severe":
            # Severe UTI without explicit syndrome -> treat as pyelonephritis/inpatient
            key = "Pyelonephritis_inpatient"
        elif severity == "moderate" or sex == "Male" or age >= 65 or is_renal or has_mdr:
            # Complicated: male, elderly, renal impaired, MDR, or moderate severity
            key = "UTI_complicated"
        else:
            # Mild + female + young + no complicating factors -> uncomplicated
            key = "UTI_uncomplicated_female"
    elif _cat == "sputum":
        if any(k in synd for k in ["hap", "vap", "hospital", "ventil"]):
            key = "HAP_VAP"
        elif severity == "mild":   key = "CAP_mild"
        elif severity == "severe": key = "CAP_severe"
        else:                      key = "CAP_moderate"
    elif _cat == "blood":
        # 2026-11-10: every non-S. aureus isolate used to get the GNB course
        # (CoNS, enterococci and streptococci included).
        # 2026-11-11 (round 4): "Staphylococcus spp." inherits S. aureus
        # everywhere else in the engine, but here it fell to the CoNS course
        # ("single bottle = contaminant"); unidentified Gram-positive cocci,
        # Listeria and anaerobes fell to "GNB Bacteremia".
        if has_mrsa or "mrsa" in org:           key = "Bacteremia_MRSA"
        elif ("staphylococcus aureus" in org or "lugdunensis" in org
              or org.strip().startswith("staphylococcus spp")):
            key = "Bacteremia_MSSA"            # S. lugdunensis behaves like S. aureus
        elif "coagulase" in org or "staphylococc" in org:
            key = "Bacteremia_CoNS"
        elif "enterococc" in org or org.strip() == "vre":
            key = "Bacteremia_Enterococcus"
        elif "streptococc" in org:               key = "Bacteremia_Strep"
        elif "gram-positive" in org or "gram positive" in org:
            key = "Bacteremia_GPC_unidentified"
        elif "listeria" in org:                  key = "Bacteremia_Listeria"
        elif "anaerob" in org or "لاهوائ" in org or "bacteroides" in org:
            key = "Bacteremia_anaerobe"
        else:                                    key = "Bacteremia_GNB"
    elif _cat == "csf":
        # Match pneumococcus explicitly so Klebsiella *pneumoniae* (a GNB) is not
        # mis-routed to the pneumococcal-meningitis protocol.
        _is_pneumococcus = ("streptococcus pneumoniae" in org
                            or "s. pneumoniae" in org or "pneumococc" in org)
        if _is_pneumococcus:                     key = "Meningitis_pneumococcal"
        elif "meningitidis" in org or "meningococc" in org:
            key = "Meningitis_meningococcal"
        elif "influenzae" in org or "haemophilus" in org:
            key = "Meningitis_haemophilus"
        elif "listeria" in org:                  key = "Meningitis_listeria"
        elif "agalactiae" in org or "group b" in org:
            key = "Meningitis_GBS"
        elif has_mrsa or any(k in org for k in ("staphylococc", "mrsa", "mssa", "coagulase")):
            key = "Meningitis_staph"
        elif any(k in org for k in ("enterococc", "streptococc", "gram-positive",
                                    "gram positive")) or org.strip() == "vre":
            key = "Meningitis_other"
        else:                                    key = "Meningitis_GNB"
    elif _cat in ("wound", "pus"):
        if any(k in synd for k in ["necrotiz", "fasciitis", "gangrene"]): key = "SSTI_severe"
        elif "osteomyelitis" in synd or "bone" in synd:                    key = "Osteomyelitis"
        elif severity == "mild":   key = "SSTI_mild"
        elif severity == "severe": key = "SSTI_severe"
        else:                      key = "SSTI_moderate"
    elif _cat == "stool":
        # GI infections: most need NO antibiotic; treat only severe/immunocompromised
        key = "GI_severe" if severity == "severe" else "GI_mild"
    elif _cat == "abdomen":
        key = "Intraabdominal_severe" if severity == "severe" else "Intraabdominal_mild"

    if not key:
        return {"label": "Not matched", "min_days": 7, "max_days": 14, "standard_days": 10,
                "iv_days": 3, "po_days": 7, "notes": "Individualize based on clinical response.",
                "follow_up_culture": True, "ref": "Clinical judgment"}

    d = TREATMENT_DURATION_DB[key].copy()
    mn, mx = d["days"]
    notes_extra = []
    if has_mdr:
        # 2026-11-10: was `mx = max(mx, 14)`. Once an ACTIVE agent is given,
        # duration does not differ for resistant organisms (IDSA AMR 2026).
        notes_extra.append("MDR organism: same duration as for a susceptible isolate once on an "
                           "active agent (IDSA AMR 2026); the clock starts at active therapy.")
    if is_renal: notes_extra.append("Renal impairment: monitor drug levels closely.")
    if age > 65:  notes_extra.append("Elderly: monitor for toxicity; shorter courses if responding.")
    if notes_extra:
        _base = d.get("notes") or ""
        d["notes"] = (_base + " | " if _base else "") + " | ".join(notes_extra)
    d.update({"min_days": mn, "max_days": mx, "standard_days": d["standard"]})
    return d


# ═══════════════════════════════════════════════════════════════════════
# ENGINE 2 -- IV->PO Switch Engine
# IDSA OPAT 2019 | BNF 2025 | BSAC 2023
# ═══════════════════════════════════════════════════════════════════════
HIGH_BIOAVAILABILITY: Dict[str, int] = {
    # Keys match abx_guidelines.py drug names exactly for cross-module consistency
    "Ciprofloxacin": 95, "Levofloxacin": 99, "Moxifloxacin": 90,
    "Ofloxacin": 95, "Norfloxacin": 30,
    "Metronidazole": 99, "Linezolid": 100,
    "Trimethoprim/Sulfamethoxazole": 90, "Doxycycline": 93,
    "Minocycline": 95, "Clindamycin": 87, "Fluconazole": 90,
    "Rifampicin": 95, "Amoxicillin": 90,
    "Amoxicillin + Clavulanic acid": 65,             # fixed: was "Amoxicillin-Clavulanate"
    "Cephalexin": 90, "Cephradine": 90, "Cefuroxime": 52, "Cefixime": 50,
    "Nitrofurantoin": 85, "Fosfomycin": 36, "Azithromycin": 37,
    "Clarithromycin": 52, "Erythromycin": 35, "Trimethoprim": 90,
}
# "bacteremia" removed 2026-11-10: oral step-down is standard for
# uncomplicated Gram-negative and streptococcal bacteraemia once the patient
# is stable (BALANCE 2025; IDSA cUTI 2025). S. aureus bacteraemia and
# endocarditis keep IV-only through their own entries.
ALWAYS_IV_SYNDROMES = frozenset([
    "endocarditis", "meningitis", "septic shock", "staphylococcus aureus bacteremia",
    "necrotizing fasciitis", "osteomyelitis (acute)", "vap",
])

def evaluate_iv_po_switch(
    drug_name: str, syndrome: str,
    clinical_improving: bool, tolerating_oral: bool,
    bacteremia_resolved: bool, days_on_iv: int,
    organism: str = "",
) -> Dict[str, Any]:
    """OPAT IV->PO Evaluation -- IDSA 2019 | BNF 2025

    `organism` added 2026-11-11 (round 4): ALWAYS_IV_SYNDROMES names
    "staphylococcus aureus bacteremia", but the syndrome passed in is the
    specimen-level label ("Bloodstream Infection (BSI) / Bacteremia"), which
    never carries the organism -- so the rule could not fire and S. aureus
    bacteraemia was cleared for oral switch like any Gram-negative one.
    """
    bioavail, matched = 0, ""
    # Exact name first (2026-11-11, round 4): with one substring pass in dict
    # order, "Ofloxacin" matched inside "Ciprofloxacin" and the panel quoted
    # the wrong drug's bioavailability.
    _dl = (drug_name or "").lower()
    for k, v in HIGH_BIOAVAILABILITY.items():
        if k.lower() == _dl:
            bioavail, matched = v, k
            break
    else:
        for k, v in HIGH_BIOAVAILABILITY.items():
            if _dl and _dl in k.lower():
                bioavail, matched = v, k
                break

    blockers, supporters = [], []
    if not clinical_improving: blockers.append("No clinical improvement in 48-72h")
    else:                      supporters.append("Clinical improvement documented")
    if not tolerating_oral:    blockers.append("Not tolerating oral intake")
    else:                      supporters.append("Tolerating oral medications")
    if not bacteremia_resolved: blockers.append("Active bacteremia / endovascular infection")
    else:                       supporters.append("No active bloodstream infection")

    if bioavail >= 80:     supporters.append(f"{matched}: Oral bioavailability {bioavail}% -- excellent for switch")
    elif bioavail >= 50:   blockers.append(f"{matched}: Moderate bioavailability ({bioavail}%) -- consider IV continuation")
    elif bioavail > 0:     blockers.append(f"{matched}: Low bioavailability ({bioavail}%) -- IV preferred")
    else:                  blockers.append(f"{drug_name}: No established oral equivalent")

    synd_lower = (syndrome or "").lower()
    if any(s in synd_lower for s in ALWAYS_IV_SYNDROMES):
        blockers.append(f"{syndrome} -- requires prolonged IV therapy")
    _org_l = (organism or "").lower()
    if (("aureus" in _org_l or "mrsa" in _org_l or "mssa" in _org_l or "lugdunensis" in _org_l)
            and any(k in synd_lower for k in ("bacteremia", "bacteraemia", "bloodstream", "bsi"))
            and "staphylococcus aureus bacteremia" not in synd_lower):
        blockers.append("S. aureus bacteraemia -- IV therapy (>= 14 d from the first negative "
                        "culture); early oral step-down only for low-risk SAB after ID review "
                        "(SABATO, Lancet Infect Dis 2024)")
    if days_on_iv < 2:    blockers.append(f"Less than 48h on IV ({days_on_iv}d) -- complete initial IV course")
    else:                  supporters.append(f"{days_on_iv} days on IV -- appropriate reassessment window")

    can_switch = len(blockers) == 0
    return {
        "can_switch": can_switch, "bioavail": bioavail, "matched_drug": matched,
        "blockers": blockers, "supporters": supporters,
        "verdict": (f"Switch acceptable. Oral bioavailability: {bioavail}%." if can_switch
                    else "IV->PO switch NOT recommended at this time."),
        "ref": "IDSA OPAT 2019 | BNF 2025 | BSAC 2023",
    }

def get_hepatic_recommendations(allowed_drugs: List[Dict], child_pugh: str) -> List[Dict[str, str]]:
    """Hepatic dosing recommendations -- BNF 2025 | Lexicomp 2025"""
    results = []
    for drug in allowed_drugs:
        name = drug.get("name", "")
        if name in HEPATIC_DOSING:
            level, rec = HEPATIC_DOSING[name].get(child_pugh, ("Normal", "No adjustment"))
            note = HEPATIC_DOSING[name].get("note", "")
            results.append({
                "name": name, "level": level,
                "recommendation": rec, "note": note,
                "requires_action": level not in ("Normal", "Renal-based", "AUC/MIC monitoring"),
            })
    results.sort(key=lambda x: (0 if x["requires_action"] else 1, x["name"]))
    return results


# ═══════════════════════════════════════════════════════════════════════
# ENGINE 4 -- Combination Therapy Suggester
# IDSA AMR Guidance 2026 | WHO Priority Pathogens | ESCAPE organisms
# ═══════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════
# COMBINATION / DEFINITIVE-THERAPY PANELS — rewritten 2026-11-10
# ----------------------------------------------------------------------
# Re-read against IDSA AMR Guidance 2026 (Gram-negatives) and the primary
# trials. Defects in the previous table:
#   * CRAB led with "Ampicillin-Sulbactam + Colistin" citing ATTACK. ATTACK
#     (Kaye, Lancet Infect Dis 2023) tested SULBACTAM-DURLOBACTAM vs colistin;
#     sulbactam-durlobactam + a carbapenem is now IDSA's priority regimen and
#     was absent. "Colistin + Rifampicin + Meropenem" cited AIDA, which tested
#     colistin +/- meropenem and found no benefit (as did OVERCOME 2023);
#     rifampicin added nothing in Durante-Mangoni (CID 2013). Both are now
#     listed as AVOID with their real evidence.
#   * CRE listed agents without the enzyme class that decides between them
#     (KPC / OXA-48 / MBL), cited RECAPTURE (a cUTI trial, not CRE) and had no
#     aztreonam-avibactam. Options now carry `for_types`.
#   * CRPA led with "Ceftolozane-Tazobactam + Amikacin". IDSA: a carbapenem-R
#     isolate still S to a traditional beta-lactam is treated with that agent
#     (high dose, extended infusion); routine aminoglycoside combination is not
#     suggested once susceptibility is known.
#   * ESBL called ertapenem "carbapenem-sparing" (it is a carbapenem) and had
#     no urinary pathway (TMP-SMX / FQ preferred for pyelonephritis/cUTI).
#   * MRSA / VRE options cited "IDSA AMR Guidance 2026", which covers
#     Gram-negatives only; "AVOID: Vancomycin + Pip-Tazo" cited a "NINJA trial"
#     -- the evidence is observational, and the ACORN RCT (JAMA 2023) found no
#     AKI difference between pip-tazo and cefepime. Now a monitoring note.
#   * No AmpC or S. maltophilia panel existed.
# ═══════════════════════════════════════════════════════════════════════
COMBINATION_THERAPY: Dict[str, Dict] = {
    "CRAB": {
        "title": "Carbapenem-Resistant A. baumannii (CRAB)",
        "urgency": "CRITICAL",
        "options": [
            {"combo": "Sulbactam-Durlobactam + Meropenem or Imipenem", "evidence": "★★★",
             "indication": "Preferred regimen for CRAB (durlobactam protects sulbactam from OXA-23/24/58)",
             "caution": "Not active against MBL-producing Acinetobacter. If resistant: two "
                        "non-sulbactam agents, or sulbactam-durlobactam + cefiderocol (IDSA 2026)",
             "ref": "ATTACK (Kaye, Lancet Infect Dis 2023) | IDSA AMR Guidance 2026"},
            {"combo": "High-dose Ampicillin-Sulbactam (9 g sulbactam/day) + second active agent "
                      "(Polymyxin B, Minocycline, Tigecycline or Cefiderocol)", "evidence": "★★",
             "indication": "When sulbactam-durlobactam is unavailable -- at least two active agents",
             "caution": "Polymyxin B preferred over colistin outside the urinary tract",
             "ref": "IDSA AMR Guidance 2026"},
            {"combo": "Cefiderocol as part of a combination", "evidence": "★",
             "indication": "Intolerance or resistance to the regimens above",
             "caution": "CREDIBLE-CR: excess mortality in the Acinetobacter subgroup -- never as monotherapy",
             "ref": "CREDIBLE-CR (Bassetti, Lancet Infect Dis 2021) | IDSA AMR Guidance 2026"},
            {"combo": "AVOID: Colistin + Meropenem as the backbone", "evidence": "AVOID",
             "indication": "",
             "caution": "AIDA (Paul, Lancet Infect Dis 2018) and OVERCOME (Kaye, NEJM Evid 2023): "
                        "adding meropenem to colistin did not improve outcome",
             "ref": "AIDA 2018 | OVERCOME 2023"},
            {"combo": "AVOID: Rifampicin added to a polymyxin", "evidence": "AVOID",
             "indication": "",
             "caution": "No mortality benefit (Durante-Mangoni, Clin Infect Dis 2013)",
             "ref": "Durante-Mangoni 2013"},
        ]
    },
    "CRPA": {
        "title": "Carbapenem-Resistant Pseudomonas aeruginosa (CRPA, not DTR)",
        "urgency": "HIGH",
        "options": [
            {"combo": "Traditional beta-lactam that tests S (Pip-Tazo, Ceftazidime, Cefepime or "
                      "Aztreonam) -- high dose, extended infusion", "evidence": "★★★",
             "indication": "Carbapenem-R but still S to a traditional agent -- treat with that agent",
             "caution": "Repeat AST if the isolate is from a relapse",
             "ref": "IDSA AMR Guidance 2026"},
            {"combo": "Ceftolozane-Tazobactam / Ceftazidime-Avibactam / Imipenem-Relebactam",
             "evidence": "★★",
             "indication": "Only if no traditional beta-lactam tests S (then the isolate is usually DTR)",
             "caution": "Reserve agents -- see the DTR-PA panel",
             "ref": "IDSA AMR Guidance 2026"},
        ]
    },
    "DTR_PA": {
        "title": "Difficult-to-Treat Resistance -- P. aeruginosa (DTR-PA)",
        "urgency": "CRITICAL",
        "options": [
            {"combo": "Ceftolozane-Tazobactam", "evidence": "★★★",
             "indication": "Preferred; favoured over ceftazidime-avibactam for pneumonia",
             "caution": "", "ref": "IDSA AMR Guidance 2026"},
            {"combo": "Ceftazidime-Avibactam", "evidence": "★★★",
             "indication": "Preferred alternative (not active if the isolate produces an MBL)",
             "caution": "", "ref": "IDSA AMR Guidance 2026"},
            {"combo": "Imipenem-Relebactam", "evidence": "★★★",
             "indication": "Preferred alternative (not active against MBL producers)",
             "caution": "High risk of resistance emerging on therapy, as with ceftazidime-avibactam (IDSA 2026)",
             "ref": "IDSA AMR Guidance 2026"},
            {"combo": "Cefiderocol", "evidence": "★★",
             "indication": "Preferred when an MBL (VIM/NDM) is detected; otherwise when the above are inactive",
             "caution": "", "ref": "IDSA AMR Guidance 2026"},
            {"combo": "AVOID: Colistin-based combination as first choice",
             "evidence": "AVOID",
             "indication": "",
             "caution": "IDSA prefers the novel beta-lactams over polymyxins for DTR-PA -- lower "
                        "nephrotoxicity and better outcomes. Reserve polymyxins for when none is active.",
             "ref": "IDSA AMR Guidance 2026"},
        ]
    },
    "CRE": {
        "title": "Carbapenem-Resistant Enterobacterales (CRE)",
        "urgency": "CRITICAL",
        "options": [
            {"combo": "Identify the carbapenemase class (NG-Test CARBA-5 / PCR)", "evidence": "★★★",
             "indication": "The enzyme class decides the agent -- NDM and OXA-48 are the commonest in Egypt",
             "caution": "", "ref": "IDSA AMR Guidance 2026", "for_types": ["UNKNOWN"]},
            {"combo": "Ceftazidime-Avibactam", "evidence": "★★★",
             "indication": "KPC or OXA-48 producers -- preferred",
             "caution": "Inactive alone against MBL (NDM/VIM/IMP)", "ref": "IDSA AMR Guidance 2026",
             "for_types": ["KPC", "OXA-48", "UNKNOWN"]},
            {"combo": "Meropenem-Vaborbactam", "evidence": "★★★",
             "indication": "KPC producers -- preferred",
             "caution": "Inactive against OXA-48 and MBL", "ref": "TANGO-II 2018 | IDSA AMR Guidance 2026",
             "for_types": ["KPC", "UNKNOWN"]},
            {"combo": "Imipenem-Relebactam", "evidence": "★★★",
             "indication": "KPC producers -- preferred",
             "caution": "Inactive against OXA-48 and MBL", "ref": "RESTORE-IMI 1 2020 | IDSA AMR Guidance 2026",
             "for_types": ["KPC", "UNKNOWN"]},
            {"combo": "Aztreonam-Avibactam", "evidence": "★★★",
             "indication": "NDM / VIM / IMP (MBL) producers -- preferred",
             "caution": "Breakpoints for Enterobacterales (CLSI M100 Ed36)",
             "ref": "ASSEMBLE / REVISIT | IDSA AMR Guidance 2026", "for_types": ["MBL", "UNKNOWN"]},
            {"combo": "Ceftazidime-Avibactam + Aztreonam (given together)", "evidence": "★★★",
             "indication": "MBL producers -- preferred alternative where aztreonam-avibactam is unavailable",
             "caution": "Synergy test (e.g. disk-stacking) advisable",
             "ref": "Falcone, Clin Infect Dis 2021 | IDSA AMR Guidance 2026", "for_types": ["MBL", "UNKNOWN"]},
            {"combo": "Cefiderocol", "evidence": "★★",
             "indication": "MBL producers (alternative); KPC / OXA-48 when the preferred agents are inactive",
             "caution": "", "ref": "IDSA AMR Guidance 2026", "for_types": ["MBL", "KPC", "OXA-48", "UNKNOWN"]},
            {"combo": "Polymyxin B or Colistin-based combination", "evidence": "★",
             "indication": "Only when no novel agent is active",
             "caution": "Nephrotoxicity; not for intrinsically polymyxin-R genera (Proteeae, Serratia)",
             "ref": "IDSA AMR Guidance 2026"},
        ]
    },
    "ESBL": {
        "title": "ESBL-Producing Enterobacterales",
        "urgency": "MODERATE",
        "options": [
            {"combo": "Cystitis: Nitrofurantoin or TMP-SMX", "evidence": "★★★",
             "indication": "Preferred for uncomplicated cystitis if S (fosfomycin oral for E. coli only)",
             "caution": "Not for pyelonephritis or bacteraemia", "ref": "IDSA AMR Guidance 2026"},
            {"combo": "Pyelonephritis / cUTI: TMP-SMX, Ciprofloxacin or Levofloxacin", "evidence": "★★★",
             "indication": "Preferred if S; carbapenem if resistant. Pip-Tazo an alternative for cUTI",
             "caution": "", "ref": "IDSA AMR Guidance 2026"},
            {"combo": "Outside the urinary tract: Meropenem, Imipenem or Ertapenem", "evidence": "★★★",
             "indication": "Preferred for bacteraemia and serious infection; oral TMP-SMX/FQ step-down once stable",
             "caution": "Ertapenem: avoid in hypoalbuminaemia (<2.5 g/dL) and critical illness",
             "ref": "MERINO 2018 | IDSA AMR Guidance 2026"},
            {"combo": "AVOID: Piperacillin-Tazobactam for bacteremia", "evidence": "AVOID",
             "indication": "Inferior to meropenem for ESBL bloodstream infection",
             "caution": "MERINO (Harris, JAMA 2018): 30-day mortality 12.3% vs 3.7%", "ref": "MERINO 2018"},
            {"combo": "AVOID: Cefepime for pyelonephritis, cUTI or bacteraemia", "evidence": "AVOID",
             "indication": "Even when cefepime tests S", "caution": "", "ref": "IDSA AMR Guidance 2026"},
        ]
    },
    "AMPC": {
        "title": "AmpC-producing Enterobacterales (derepressed / plasmid)",
        "urgency": "MODERATE",
        "options": [
            {"combo": "Cefepime (if MIC <= 2 / S)", "evidence": "★★★",
             "indication": "Preferred for invasive infection -- stable to AmpC",
             "caution": "If cefepime is SDD/I, suspect ESBL co-production -- use a carbapenem",
             "ref": "IDSA AMR Guidance 2026"},
            {"combo": "Carbapenem (Meropenem / Ertapenem)", "evidence": "★★★",
             "indication": "Cefepime SDD/I or R, or critical illness", "caution": "",
             "ref": "IDSA AMR Guidance 2026"},
            {"combo": "Oral step-down: TMP-SMX or a fluoroquinolone", "evidence": "★★",
             "indication": "After clinical response, if S", "caution": "", "ref": "IDSA AMR Guidance 2026"},
            {"combo": "AVOID: Ceftriaxone or Pip-Tazo to START invasive therapy (E. cloacae, "
                      "K. aerogenes, C. freundii)", "evidence": "AVOID",
             "indication": "Selection of derepressed mutants on therapy",
             "caution": "Acceptable for cystitis; continuing ceftriaxone is reasonable in a non-severe "
                        "infection that is already responding (IDSA 2026)",
             "ref": "IDSA AMR Guidance 2026"},
        ]
    },
    "STENO": {
        "title": "Stenotrophomonas maltophilia (invasive)",
        "urgency": "HIGH",
        "options": [
            {"combo": "Cefiderocol monotherapy", "evidence": "★★★",
             "indication": "Preferred for invasive infection", "caution": "",
             "ref": "IDSA AMR Guidance 2026"},
            {"combo": "Aztreonam-Avibactam (or Ceftazidime-Avibactam + Aztreonam) + second agent",
             "evidence": "★★",
             "indication": "Alternative -- no CLSI breakpoint for this organism",
             "caution": "", "ref": "IDSA AMR Guidance 2026"},
            {"combo": "TMP-SMX + Minocycline or Levofloxacin", "evidence": "★★",
             "indication": "When cefiderocol is unavailable; monotherapy acceptable only for mild infection or step-down",
             "caution": "TMP-SMX: high dose (8-12 mg/kg/day TMP); monitor potassium",
             "ref": "IDSA AMR Guidance 2026"},
            {"combo": "AVOID: Ceftazidime", "evidence": "AVOID",
             "indication": "CLSI removed the ceftazidime breakpoints for S. maltophilia (2024)",
             "caution": "L1/L2 beta-lactamases", "ref": "CLSI M100 Ed34"},
        ]
    },
    "MRSA": {
        "title": "Methicillin-Resistant S. aureus (MRSA)",
        "urgency": "HIGH",
        "options": [
            {"combo": "Vancomycin -- AUC/MIC target 400-600", "evidence": "★★★",
             "indication": "MRSA bacteremia | endocarditis | pneumonia -- first-line",
             "caution": "AUC-guided TDM (not trough-only)",
             "ref": "IDSA MRSA 2011 | ASHP/IDSA/PIDS/SIDP vancomycin TDM 2020"},
            {"combo": "Daptomycin (8-10 mg/kg)", "evidence": "★★★",
             "indication": "MRSA bacteremia / right-sided endocarditis -- alternative to vancomycin",
             "caution": "Daptomycin INEFFECTIVE for pneumonia (inactivated by surfactant); weekly CK",
             "ref": "Fowler, NEJM 2006 | IDSA MRSA 2011"},
            {"combo": "Linezolid 600mg q12h", "evidence": "★★★",
             "indication": "MRSA pneumonia -- equivalent alternative to vancomycin",
             "caution": "ZEPHyR showed higher clinical cure but no mortality difference; avoid >2 weeks, "
                        "weekly CBC, serotonin syndrome risk",
             "ref": "ZEPHyR (Wunderink, CID 2012) | IDSA MRSA 2011"},
            {"combo": "Daptomycin + Ceftaroline", "evidence": "★★",
             "indication": "Persistent MRSA bacteremia (salvage)",
             "caution": "Small RCT / observational evidence", "ref": "Geriak, AAC 2019 | expert consensus"},
            {"combo": "Vancomycin + Rifampicin", "evidence": "★★",
             "indication": "Retained prosthetic material only (prosthetic joint, valve, CIED) -- after bacteraemia clears",
             "caution": "Not for uncomplicated S. aureus bacteraemia (ARREST, Lancet 2018: no benefit); "
                        "never rifampicin monotherapy",
             "ref": "IDSA PJI 2013 | ARREST 2018"},
            {"combo": "Vancomycin + Piperacillin-Tazobactam -- monitor creatinine", "evidence": "★",
             "indication": "Not contraindicated",
             "caution": "Observational AKI signal; the ACORN RCT (JAMA 2023) found no AKI difference "
                        "between pip-tazo and cefepime. Daily creatinine; use AUC dosing",
             "ref": "ACORN (Qian, JAMA 2023)"},
        ]
    },
    "VRE": {
        "title": "Vancomycin-Resistant Enterococcus (VRE)",
        "urgency": "HIGH",
        "options": [
            {"combo": "Ampicillin (if the isolate tests S -- usually E. faecalis)", "evidence": "★★★",
             "indication": "Drug of choice whenever ampicillin is S", "caution": "",
             "ref": "AHA 2015 / ESC 2023 endocarditis guidance"},
            {"combo": "Linezolid 600mg q12h", "evidence": "★★★",
             "indication": "VRE -- serious infections when ampicillin is R",
             "caution": "Weekly CBC monitoring; myelosuppression risk",
             "ref": "Expert consensus (no IDSA guideline)"},
            {"combo": "Daptomycin high-dose (>=10 mg/kg)", "evidence": "★★",
             "indication": "VRE bacteremia", "caution": "Monitor CK weekly",
             "ref": "Britt, Clin Infect Dis 2017 (cohort)"},
            {"combo": "Daptomycin + Ampicillin (or Ceftaroline)", "evidence": "★",
             "indication": "Persistent VRE bacteremia / endocarditis -- beta-lactam potentiates daptomycin",
             "caution": "In-vitro / observational evidence", "ref": "Synergy studies"},
        ]
    },
}

# Agents inside COMBINATION_THERAPY option strings that carry a host-state
# contraindication. Matched as case-insensitive substrings of the combo text,
# because the strings are prose ("Ampicillin-Sulbactam (high-dose 9g q8h) +
# Colistin"), not formulary keys.
_COMBO_HOST_FLAGS: List[Tuple[str, List[str], str, str]] = [
    ("pregnancy", ["amikacin", "gentamicin", "tobramycin", "plazomicin"],
     "⚠️ حمل: أمينوجليكوزيد — سمية أذنية جنينية نظرية (موثّقة مع Streptomycin). "
     "يُستخدم عند الحاجة بجرعة يومية واحدة ومراقبة المستوى ولأقصر مدة (ACOG).",
     "PREGNANCY: aminoglycoside — theoretical fetal ototoxicity (documented with "
     "streptomycin). Use when needed: once-daily dosing, levels, shortest course (ACOG)."),
    ("pregnancy", ["tigecycline", "minocycline", "doxycycline", "eravacycline"],
     "⛔ حمل: تتراسيكلين — مضاد استطباب مطلق (تلوّن الأسنان، تثبيط نمو العظم).",
     "PREGNANCY: tetracycline — absolute contraindication."),
    ("pregnancy", ["ciprofloxacin", "levofloxacin", "moxifloxacin",
                   "fluoroquinolone"],
     "⚠️ حمل: فلوروكينولون — يُتجنّب (سمّية غضروفية في الدراسات الحيوانية).",
     "PREGNANCY: fluoroquinolone — avoid (animal arthropathy)."),
    ("pregnancy", ["rifampicin", "rifampin"],
     "⚠️ حمل: ريفامبيسين — خطر نزف وليدي، أعطِ فيتامين K للأم والوليد.",
     "PREGNANCY: rifampicin — neonatal haemorrhage risk; give vitamin K."),
    ("neonate", ["ceftriaxone"],
     "⛔ وليد: سيفترياكسون — يزيح البيليروبين ويترسّب مع الكالسيوم. استخدم "
     "cefotaxime بدلاً منه.",
     "NEONATE: ceftriaxone — bilirubin displacement / calcium precipitation. "
     "Use cefotaxime."),
    ("neonate", ["tigecycline", "minocycline", "doxycycline",
                 "ciprofloxacin", "levofloxacin", "moxifloxacin"],
     "⛔ وليد/طفل: غير مناسب لهذه الفئة العمرية إلا باستثناء مبرَّر.",
     "NEONATE/CHILD: not appropriate for this age band without justification."),
    # Added 2026-08-03. A mutation that widened this panel's neonate window to
    # every infant survived every suite — and writing the test that kills it
    # showed the window was not the only gap: NONE of the salvage agents this
    # panel actually recommends was in the neonate list. A neonate with XDR
    # Pseudomonas got Cefiderocol and Imipenem-Relebactam with no age caution
    # at all, because the list named only ceftriaxone and the tetracyclines.
    #
    # Amikacin and colistin are deliberately NOT here: amikacin is standard
    # neonatal sepsis therapy and colistin has real neonatal experience. Adding
    # them would flag the two agents a neonatologist is most likely to need.
    ("neonate", ["cefiderocol", "relebactam", "vaborbactam", "avibactam",
                 "ceftolozane", "ceftaroline", "daptomycin", "durlobactam"],
     "⚠️ وليد: بيانات السلامة والجرعة في حديثي الولادة محدودة أو غير متوفرة "
     "لهذا الدواء. لا يُستخدم إلا بعد استشارة حديثي الولادة والأمراض المعدية، "
     "وبتوثيق سبب غياب البديل.",
     "NEONATE: neonatal safety and dosing data for this agent are limited or "
     "absent. Use only after neonatology and infectious-diseases consultation, "
     "documenting why no alternative exists."),
    ("renal", ["colistin", "polymyxin", "amikacin", "gentamicin", "tobramycin",
               "vancomycin"],
     "⚠️ قصور كلوي: يحتاج تعديل جرعة ومتابعة CrCl/TDM — الجرعات المكتوبة هنا "
     "للوظيفة الكلوية الطبيعية.",
     "RENAL IMPAIRMENT: dose adjustment plus CrCl/TDM monitoring required — the "
     "doses quoted here assume normal renal function."),
    ("hepatic", ["tigecycline", "rifampicin", "rifampin"],
     "⚠️ قصور كبدي: يحتاج تعديل جرعة ومتابعة إنزيمات الكبد.",
     "HEPATIC IMPAIRMENT: dose adjustment and LFT monitoring required."),
]


def get_combination_therapy(
    phenotypes: List[Dict],
    *,
    is_pregnant: bool = False,
    age_years: Optional[float] = None,
    age_months: Optional[float] = None,
    is_renal: bool = False,
    cl_cr: Optional[float] = None,
    is_hepatic: bool = False,
    organism: str = "",
    carbapenemase_type: Optional[str] = None,
) -> List[Dict]:
    """Combination therapy suggestions -- IDSA AMR Guidance 2026.

    FIX 2026-08-01 (second pass): this took `phenotypes` and nothing else. It
    was the ONLY panel in the app that proposed agents without passing through
    analyze_antibiotics() or apply_safety_gate(), and it renders in an expander
    that is open by default under a CRITICAL header. A pregnant patient with
    CRPA was shown "Ceftolozane-Tazobactam + Amikacin" with an empty caution
    field, while the main engine was refusing amikacin for that same patient
    three panels above.

    These are XDR salvage regimens from the literature, so they are NOT removed
    -- withholding the only option for a pan-resistant isolate is its own harm.
    The host contraindication is attached to the option instead, in the
    `caution` slot the renderer already displays.
    """
    results: List[Dict] = []
    ph_names = [p.get("phenotype", "") for p in phenotypes]

    states = set()
    if is_pregnant:
        states.add("pregnancy")
    # Months win over years. `age_years` is the UI's INTEGER field, which reads
    # 0 for every infant from birth to eleven months — the same trap that made
    # apply_safety_gate() treat a six-month-old as a neonate (fixed 2026-08-03).
    # Resolve here too rather than inheriting it.
    from clinical_utils import resolve_age_years as _ray, NEONATE_MAX_YEARS as _NMY
    _eff_age = _ray(age_years, age_months)
    if _eff_age is not None and _eff_age <= _NMY:
        states.add("neonate")
    if is_renal or (cl_cr is not None and cl_cr < 60):
        states.add("renal")
    if is_hepatic:
        states.add("hepatic")

    # DTR_PA before CRPA: when both fire, the narrower finding carries the
    # more specific therapeutic instruction and should read first. (The CRPA
    # panel now says "use the traditional beta-lactam that tests S", which is
    # moot for a DTR isolate, so it is not shown alongside DTR_PA.)
    if "DTR_PA" in ph_names:
        ph_names = [p for p in ph_names if p != "CRPA"]
    # CRE options are filtered by enzyme class when it is known (2026-11-10):
    # showing meropenem-vaborbactam for an NDM producer is a wrong answer, not
    # a neutral one.
    from therapy_rules import normalize_carbapenemase_type as _nct
    _ctype = _nct(carbapenemase_type) or "UNKNOWN"
    for ph in ["CRAB", "DTR_PA", "CRPA", "CRE", "STENO", "AMPC", "ESBL", "MRSA", "VRE", "MDR"]:
        if ph not in ph_names or ph not in COMBINATION_THERAPY:
            continue
        data = COMBINATION_THERAPY[ph]
        if ph == "CRE":
            _kept = [o for o in data["options"]
                     if not o.get("for_types") or _ctype in o["for_types"]]
            _title = data["title"] + ("" if _ctype == "UNKNOWN" else f" — {_ctype}")
            data = {**data, "title": _title, "options": _kept}
        if not states:
            results.append({"phenotype": ph, "data": data})
            continue
        # Copy before annotating: COMBINATION_THERAPY is module-level and
        # Streamlit reruns this on every interaction, so mutating it in place
        # would accumulate host warnings from previous patients.
        opts = []
        for opt in data["options"]:
            combo_low = opt["combo"].lower()
            extra = [ar for state, drugs, ar, _en in _COMBO_HOST_FLAGS
                     if state in states and any(d in combo_low for d in drugs)]
            if extra:
                new_opt = dict(opt)
                new_opt["caution"] = "  ".join(
                    x for x in [opt.get("caution", ""), *extra] if x)
                new_opt["host_flagged"] = True
                opts.append(new_opt)
            else:
                opts.append(opt)
        results.append({"phenotype": ph, "data": {**data, "options": opts}})
    # ── The organism's OWN intrinsic resistance ─────────────────────────────
    # DEFECT 2026-08-06, raised by a third-party review and confirmed over 1,500
    # randomised cases: the CRE panel offered "Colistin + Meropenem high-dose"
    # for Proteus, Providencia, Morganella and Serratia — all four INTRINSICALLY
    # colistin-resistant. They are Enterobacterales, so CRE fires correctly; the
    # panel then recommended a polymyxin that cannot work against them, 50 times
    # in 1,500 cases.
    #
    # This is NOT the same as offering an agent the AST reported R. A salvage
    # regimen naming an AST-resistant drug is the POINT of high-dose extended
    # infusion — the strategy exists for isolates where the standard dose
    # failed. An INTRINSIC mechanism is different in kind: no dose, no infusion
    # time and no partner overcomes a missing target or a constitutive efflux
    # pump. It is a dead option printed in the panel a clinician reaches for
    # when nothing else is left.
    #
    # Options are ANNOTATED, not deleted: the reader should see that the
    # regimen exists and why it does not apply here, rather than wonder whether
    # the panel simply forgot it.
    #
    # Matching claims whole agent names longest-first — the same span-claiming
    # the OCR scanner uses. Without it "Ampicillin-Sulbactam", a genuine and
    # recommended CRAB agent, would match Acinetobacter's intrinsic "Ampicillin"
    # and be wrongly condemned.
    if organism and results:
        try:
            from clinical_data import INTRINSIC_RESISTANCE as _IR_C
            from clinical_utils import org_matches as _om_c
        except Exception:
            _IR_C, _om_c = {}, None
        _intr = set()
        if _om_c:
            for _k, _v in _IR_C.items():
                if _om_c(organism, [_k]):
                    _intr |= set(_v)
        if _intr:
            _agents = sorted(ABX_GUIDELINES, key=len, reverse=True)
            for _panel in results:
                _opts = []
                for _opt in _panel["data"]["options"]:
                    _txt = str(_opt.get("combo", ""))
                    if _txt.upper().startswith("AVOID"):
                        _opts.append(_opt)
                        continue
                    _norm = _txt.lower().replace("+", "-").replace("/", "-").replace(" ", "")
                    _claimed = []
                    for _ag in _agents:
                        _a = _ag.lower().replace("+", "-").replace("/", "-").replace(" ", "")
                        if _a and _a in _norm:
                            _claimed.append(_ag)
                            _norm = _norm.replace(_a, "\x00" * len(_a))
                    _dead = [d for d in _claimed if d in _intr]
                    if _dead:
                        _opt = dict(_opt)
                        _opt["host_flagged"] = True
                        _opt["intrinsically_inactive"] = _dead
                        _opt["caution"] = (
                            f"⛔ **{organism} مقاوم جوهرياً لـ "
                            f"{'، '.join(_dead)}** — لا جرعة ولا تسريب ممتد ولا "
                            f"شريك دوائي يتغلب على مقاومة جوهرية. هذا الخيار غير "
                            f"صالح لهذه العزلة. " + str(_opt.get("caution", ""))
                        ).strip()
                    _opts.append(_opt)
                _panel["data"] = dict(_panel["data"])
                _panel["data"]["options"] = _opts

    return results


# ═══════════════════════════════════════════════════════════════════════
# ENGINE 5 -- De-escalation Advisor
# WHO AWaRe 2025 | IDSA Stewardship 2025
# ═══════════════════════════════════════════════════════════════════════
def evaluate_deescalation(
    allowed: List[Dict], phenotypes: List[Dict],
    hours_on_treatment: int, clinical_improving: bool,
    mdr_level: Optional[str] = None,
) -> Dict[str, Any]:
    """De-escalation advisor -- WHO AWaRe 2025 | IDSA Stewardship 2025

    FIX 2026-11-11 (round 4): "MDR" / "XDR" / "PDR" were looked for among the
    PHENOTYPE names, where no detector ever emits them (the level comes from
    classify_mdr), and DTR-P. aeruginosa was missing -- so an XDR or DTR
    isolate got "de-escalation recommended" with no ID caution. The MDR level
    is now passed in.
    """
    ph_names    = [p.get("phenotype", "") for p in phenotypes]
    is_reserve  = (any(p in ph_names for p in ["MDR", "XDR", "PDR", "CRE", "CRPA", "CRAB", "DTR_PA"])
                   or str(mdr_level or "").upper() in ("MDR", "XDR", "PDR"))
    access_drugs = [d for d in allowed if d.get("aware") == "Access"]
    watch_drugs  = [d for d in allowed if d.get("aware") == "Watch"]
    recs, can_de = [], False

    if hours_on_treatment < 48:
        recs.append(f"INFO: Still in early treatment phase ({hours_on_treatment}h). Complete 48-72h before reassessment.")
    elif not clinical_improving:
        recs.extend(["WARNING: No clinical improvement at 48-72h:",
                     "  - Repeat culture to confirm sensitivity",
                     "  - Assess source control (drainage, catheter removal)",
                     "  - Consider TDM (vancomycin AUC, aminoglycosides)",
                     "  - Consult Infectious Disease"])
    else:
        can_de = True
        recs.append("RECOMMENDED: Clinical improvement documented -- consider spectrum narrowing:")
        if access_drugs:
            names = [d["name"] for d in access_drugs[:4]]
            recs.append(f"  Access-group options: {' | '.join(names)}")
        elif watch_drugs:
            names = [d["name"] for d in watch_drugs[:3]]
            recs.append(f"  Watch-group options: {' | '.join(names)}")
        if is_reserve:
            recs.append("  CAUTION: MDR/XDR organism -- ID consult before de-escalating Reserve agents")
            can_de = False

    recs.append("PRINCIPLE: Narrowest effective spectrum + shortest safe duration (WHO AWaRe 2025)")
    return {
        "can_deescalate": can_de,
        "access_options": [d["name"] for d in access_drugs],
        "watch_options":  [d["name"] for d in watch_drugs],
        "recommendations": recs,
        "is_reserve_organism": is_reserve,
        "ref": "WHO AWaRe 2025 | IDSA Stewardship 2025",
    }




# =========================================================
# MODULE 1 -- Resistance Phenotype Engine
# يحدد: ESBL / CRE / MRSA / VRE / MDR / XDR / PDR
# المرجع: EUCAST Breakpoint Tables v16.1, CLSI M100 Ed36, CDC/ECDC 2017
# =========================================================
PHENOTYPE_RULES = {
    # ── DERIVED phenotypes (2026-11-10) ──────────────────────────────────────
    # Not marker rules: emitted from predict_esbl() / the organism itself at
    # the end of detect_resistance_phenotypes(). Registered here so every
    # name a detector emits is a real key (and the marker loop skips them).
    "ESBL": {
        "derived": True, "organisms": [], "markers": [],
        "icon": "🟠", "label": "ESBL -- Extended-Spectrum β-Lactamase (predicted)",
        "detail": "مقاومة للجيل الثالث في Enterobacterale — نمط ESBL متوقع.",
        "action": ("المثانة: Nitrofurantoin/TMP-SMX؛ الحويضة: TMP-SMX/FQ؛ تجرثم الدم: "
                   "Carbapenem (IDSA 2026). أكّد بـ DDST حسب سياسة المعمل."),
        "isolation": False,
    },
    "AMPC": {
        "derived": True, "organisms": [], "markers": [],
        "icon": "🟠", "label": "AmpC β-lactamase (predicted)",
        "detail": "مقاومة للجيل الثالث مع نمط AmpC (كروموسومي مُفرط أو بلازميدي).",
        "action": ("Cefepime إذا S (MIC ≤ 2)؛ Carbapenem إذا SDD/I أو حالة حرجة "
                   "(IDSA 2026). لا Ceftriaxone ولا Pip-Tazo للعدوى الغازية."),
        "isolation": False,
    },
    "STENO": {
        "derived": True, "organisms": ["Stenotrophomonas maltophilia"], "markers": [],
        "icon": "🟠", "label": "S. maltophilia -- intrinsically carbapenem-resistant",
        "detail": "L1 metallo-β-lactamase + L2 — مقاومة جوهرية لكل الكاربابينيمات.",
        "action": "العدوى الغازية: Cefiderocol منفرداً (IDSA 2026) — راجع لوحة العلاج.",
        "isolation": False,
    },
    "MRSA": {
        "organisms": ["Staphylococcus aureus","MRSA","Staphylococcus spp."],
        "markers":   [("Oxacillin","R"), ("Cefoxitin","R")],
        "require_any": 1,  # CLSI M100: أي surrogate لوحده (Oxacillin أو Cefoxitin) R يؤكد MRSA
        "fallback":  [("Vancomycin","S"), ("Linezolid","S")],  # حساس لهم -> likely MRSA
        "icon":  "🔴",
        "label": "MRSA -- Methicillin-Resistant S. aureus",
        "detail": "مقاوم للـ Methicillin (mecA gene). جميع البيتا-لاكتام غير فعالة.",
        "action": "Vancomycin أو Linezolid حسب الشدة. بروتوكول عزل إلزامي.",
        "isolation": True,
    },
    "VRE": {
        "organisms": ["Enterococcus faecalis","Enterococcus faecium","VRE","Enterococcus spp."],
        "markers":   [("Vancomycin","R")],
        "icon":  "🔴",
        "label": "VRE -- Vancomycin-Resistant Enterococcus",
        "detail": "مقاوم للـ Vancomycin (vanA/vanB gene). خطر انتشار في المستشفى.",
        "action": "Linezolid أو Daptomycin. عزل فوري. إبلاغ مكافحة العدوى.",
        "isolation": True,
    },
    "CRE": {
        # FIX 2026-08-01 (second pass). This list is a FOURTH organism table,
        # independent of clinical_data.INTRINSIC_RESISTANCE, ORGANISM_PROFILE
        # and clinical_matrix._ORG_CANON — and it was not updated when the
        # AmpC genera were added, nor did it ever cover Salmonella, Shigella or
        # the unspeciated fallback.
        #
        # The failure was silent and severe: predict_esbl() returned
        # "carbapenemase" and the red banner appeared, but because no phenotype
        # was detected the isolate got NO "🚨 عزل فوري مطلوب" isolation alert,
        # NO combination-therapy panel (so Ceftazidime-Avibactam and
        # Meropenem-Vaborbactam were never suggested), and evaluate_deescalation
        # did not treat it as a Reserve organism. A carbapenem-resistant isolate
        # that nobody is told to isolate is the one that spreads through a ward.
        #
        # "Citrobacter freundii" is spelled out because the entry here was
        # "Citrobacter spp." and neither string is a substring of the other, so
        # the species profile added earlier that day matched nothing.
        "organisms": ["Klebsiella spp.", "E. coli", "Escherichia coli",
                      "Enterobacter cloacae", "Enterobacter spp.",
                      "Proteus mirabilis", "Proteus vulgaris", "Proteus spp.",
                      "Klebsiella pneumoniae", "Klebsiella oxytoca",
                      "Serratia marcescens", "Serratia spp.", "Citrobacter spp.",
                      "Citrobacter freundii", "Citrobacter koseri",
                      "Morganella morganii", "Providencia spp.",
                      "Hafnia alvei", "Salmonella spp.", "Shigella spp.",
                      "Enterobacterales (unspeciated)", "Enterobacterales"],
        "markers":   [("Imipenem/Cilastatin","R"),("Meropenem","R"),("Ertapenem","R")],
        "require_any": 1,  # واحد كافٍ
        "icon":  "🚨",
        # Proteeae: imipenem R alone does not qualify (CDC CRE definition).
        "exclude_markers_for": {("proteus", "morganella", "providencia"): ["Imipenem/Cilastatin"]},
        "label": "CRE -- Carbapenem-Resistant Enterobacterales",
        "detail": "مقاوم للكاربابينيم -- أخطر أنماط المقاومة في العالم.",
        # FIX 2026-11-10: was "Colistin + Fosfomycin أو Ceftazidime-Avibactam"
        # for every CRE. The choice depends on the enzyme class (IDSA 2026),
        # and polymyxin combinations are not preferred.
        "action": ("حدّد نوع الكاربابينيميز (NG-Test CARBA-5 أو PCR) — العلاج يتوقف عليه: "
                   "KPC ← Ceftazidime-avibactam / Meropenem-vaborbactam / Imipenem-relebactam؛ "
                   "OXA-48 ← Ceftazidime-avibactam؛ NDM/VIM/IMP ← Aztreonam-avibactam أو "
                   "Ceftazidime-avibactam + Aztreonam أو Cefiderocol (IDSA 2026). "
                   "Colistin ليس خياراً مفضّلاً. أرسل للمختبر المرجعي."),
        "isolation": True,
    },
    "CRAB": {
        "organisms": ["Acinetobacter baumannii", "Acinetobacter spp."],
        "markers":   [("Imipenem/Cilastatin","R"),("Meropenem","R")],
        "require_any": 1,
        "icon":  "🚨",
        "label": "CRAB -- Carbapenem-Resistant Acinetobacter baumannii",
        "detail": "XDR/PDR Acinetobacter -- أصعب الكائنات علاجاً في ICU.",
        # FIX 2026-11-10: was "Colistin ± Rifampicin". IDSA 2026 prioritises
        # sulbactam-durlobactam + a carbapenem; rifampicin adds nothing (AIDA).
        "action": ("IDSA 2026: Sulbactam-durlobactam + Meropenem أو Imipenem هو المفضّل. "
                   "إن لم يتوفر: Ampicillin-sulbactam جرعة عالية (9 g sulbactam يومياً) + دواء "
                   "ثانٍ فعّال (Polymyxin B أو Minocycline أو Tigecycline أو Cefiderocol). "
                   "لا Rifampicin. استشارة الأمراض المعدية."),
        "isolation": True,
    },
    "CRPA": {
        # FIX 2026-08-03. The rule was:
        #     markers = Imipenem R, Meropenem R, Pip-Tazo R, Ceftazidime R
        #     require_any = 2
        # Pip-Tazo and Ceftazidime are NOT carbapenems, and putting them in a
        # definition literally named "Carbapenem-Resistant" broke it BOTH ways:
        #
        #   MISSED   Meropenem R alone  -> no CRPA, no isolation alert, no
        #            combination panel. Egyptian panels routinely carry
        #            meropenem as the only carbapenem, so a genuine CRPA
        #            bacteraemia produced no alert at all.
        #   OVER-CALLED  Ceftazidime R + Pip-Tazo R with BOTH carbapenems S
        #            -> "CRPA", 🚨 immediate isolation and an XDR salvage panel,
        #            for a carbapenem-SUSCEPTIBLE isolate. predict_esbl() said
        #            "low" for the same isolate on the same screen.
        #
        # CDC / IDSA / EUCAST all define CRPA as resistance to AT LEAST ONE
        # carbapenem. Ceftazidime and Pip-Tazo belong to DTR (difficult-to-treat
        # resistance), a separate concept with its own therapeutic implication —
        # see the DTR_PA rule below. Note the sibling rules were already correct:
        # CRAB requires 1 of 2 carbapenems, CRE requires 1 of 3. CRPA was the
        # only outlier, with no comment explaining why.
        #
        # Ertapenem is deliberately absent: P. aeruginosa is INTRINSICALLY
        # resistant to it, so an ertapenem-R result carries no information here.
        "organisms": ["Pseudomonas aeruginosa", "Pseudomonas spp."],
        # Doripenem belongs in this definition clinically but is NOT in this
        # formulary's 51 agents, so a marker naming it can never match and is
        # exactly the dead-rule pattern this audit keeps removing. Add it back
        # here the day the agent is added to abx_guidelines.py.
        "markers":   [("Imipenem/Cilastatin", "R"), ("Meropenem", "R")],
        "require_any": 1,
        "icon":  "🔴",
        "label": "CRPA -- Carbapenem-Resistant Pseudomonas aeruginosa",
        "detail": "مقاوم لواحد على الأقل من الكاربابينيمات. خيارات علاجية محدودة.",
        "action": "Ceftolozane-Tazobactam أو Ceftazidime-Avibactam حسب الحساسية. "
                  "Colistin كخيار إنقاذ. راجع لوحة العلاج التوليفي.",
        "isolation": True,
    },
    "DTR_PA": {
        # Difficult-to-Treat Resistance (Kadri et al., Clin Infect Dis 2018;
        # adopted by IDSA AMR Guidance v4.0). DEFINED as non-susceptibility to
        # ALL of: piperacillin-tazobactam, ceftazidime, cefepime, aztreonam,
        # meropenem, imipenem, ciprofloxacin and levofloxacin — i.e. every
        # first-line agent has failed, which is a different and narrower thing
        # than carbapenem resistance and points at the novel beta-lactams rather
        # than at colistin.
        #
        # This is where Ceftazidime and Pip-Tazo actually belong. They were
        # previously sitting inside the CRPA marker list, which is what made a
        # carbapenem-susceptible isolate register as carbapenem-resistant.
        #
        # DEFINITION FIX 2026-08-03 (web-verified against Kadri et al. 2018 and
        # IDSA): DTR is non-susceptibility to ALL EIGHT agents, not a majority.
        # A 6-of-8 threshold over-calls it — an isolate still susceptible to
        # cefepime and levofloxacin is not difficult-to-treat, and labelling it
        # so pushes a clinician toward the novel beta-lactams when a first-line
        # agent still works.
        #
        # But requiring all eight to be PRESENT on the panel would make the rule
        # unreachable: no Egyptian panel carries aztreonam plus all three
        # anti-pseudomonal beta-lactams plus both fluoroquinolones. The engine
        # therefore requires every one of the eight that WAS TESTED to be R,
        # with a floor of 5 tested agents so a two-drug panel cannot qualify.
        # That is the faithful reading of "non-susceptible to all" under partial
        # testing, and it is handled by `require_all_tested` below rather than
        # by require_any.
        "organisms": ["Pseudomonas aeruginosa", "Pseudomonas spp."],
        "markers":   [("Piperacillin + Tazobactam", "R"), ("Ceftazidime", "R"),
                      ("Cefepime", "R"), ("Aztreonam", "R"),
                      ("Meropenem", "R"), ("Imipenem/Cilastatin", "R"),
                      ("Ciprofloxacin", "R"), ("Levofloxacin", "R")],
        "require_any": 5,          # floor: at least 5 of the 8 must be on the panel
        "require_all_tested": True, # and every tested one must be R
        "icon":  "🔴",
        "label": "DTR-P. aeruginosa -- Difficult-to-Treat Resistance",
        "detail": "مقاومة لكل الخطوط الأولى (بيتا-لاكتام + فلوروكينولون). "
                  "المفهوم أضيق من CRPA ويوجّه نحو البيتا-لاكتامات الحديثة.",
        "action": "Ceftolozane-Tazobactam أو Ceftazidime-Avibactam أو Cefiderocol "
                  "حسب الحساسية — يُفضَّل على Colistin (سمّية أقل، نتائج أفضل). "
                  "استشارة الأمراض المعدية مطلوبة.",
        "isolation": True,
    },
}

def detect_resistance_phenotypes(
    organism: str, sir_map: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    يكتشف الـ phenotypes المقاومة من نمط S/I/R.
    يعيد قائمة بكل الـ phenotypes المكتشفة.
    """
    if not sir_map:
        return []
    detected = []
    # `(organism or "")`: predict_esbl carried the same bare .lower() until
    # 2026-08-01 and raised AttributeError on None while every other entry point
    # in this file coerced. Same fix, same reason — fail closed, do not raise.
    org_lower = _re_ws_collapse(organism)

    for ph_name, rule in PHENOTYPE_RULES.items():
        if rule.get("derived"):
            continue          # emitted below, not by markers
        # Is this organism a candidate for this phenotype?
        # FIX 2026-08-03: this was an unguarded two-way substring test, the same
        # trap already fixed in is_esbl_producer(). `"" in "klebsiella spp."` is
        # True, so a blank or one-character organism matched EVERY rule and came
        # back claiming MRSA + VRE + CRE + CRAB simultaneously — four
        # immediate-isolation banners and four salvage-therapy panels for an
        # isolate with no name. _org_matches() carries the length floor and the
        # non-informative-token list, so the guard now lives in one place
        # instead of being re-derived per call site.
        if not _org_matches(org_lower, [o.lower() for o in rule["organisms"]]):
            continue

        markers   = rule.get("markers", [])
        for _toks, _excl in (rule.get("exclude_markers_for") or {}).items():
            if any(t in org_lower for t in _toks):
                markers = [(d, e) for d, e in markers if d not in _excl]
        req_any   = rule.get("require_any", len(markers))  # default: كل الـ markers

        # عدد الـ markers المطابقة
        matched = sum(1 for drug, expected in markers
                      if sir_map.get(drug) == expected)

        # `require_all_tested` (added 2026-08-03 for DTR-P. aeruginosa): the
        # definition is non-susceptibility to ALL of a named set, but a real
        # panel rarely carries every agent in it. Requiring all EIGHT to be
        # present makes the rule unreachable; requiring a mere majority
        # over-calls it. So: every listed agent that WAS tested must match, and
        # `require_any` becomes a floor on how many had to be tested at all.
        if rule.get("require_all_tested"):
            tested = [(d, e) for d, e in markers if sir_map.get(d) is not None]
            if len(tested) < req_any:
                continue
            if any(sir_map.get(d) != e for d, e in tested):
                continue
            matched = len(tested)

        if matched >= req_any and matched > 0:
            detected.append({
                "phenotype": ph_name,
                "icon":      rule["icon"],
                "label":     rule["label"],
                "detail":    rule["detail"],
                "action":    rule["action"],
                "isolation": rule.get("isolation", False),
                "matched_markers": [
                    drug for drug, exp in markers if sir_map.get(drug) == exp
                ],
            })

    # ── Mechanism phenotypes from the predictor (added 2026-11-10) ──────────
    # The ESBL therapy panel existed but no detector ever emitted "ESBL", so
    # it could never be shown; AmpC and S. maltophilia had no panel at all.
    # Isolation is False: these change THERAPY, not the isolation protocol
    # (local IPC policy decides contact precautions for ESBL).
    _have = {d["phenotype"] for d in detected}

    def _derived(_name: str) -> Dict[str, Any]:
        _r = PHENOTYPE_RULES[_name]
        return {"phenotype": _name, "icon": _r["icon"], "label": _r["label"],
                "detail": _r["detail"], "action": _r["action"],
                "isolation": _r["isolation"], "matched_markers": []}

    if not ({"CRE", "CRAB", "CRPA", "DTR_PA"} & _have):
        try:
            _pm = (predict_esbl(organism, sir_map) or {}).get("probability")
        except Exception:          # harnesses that lift this function alone
            _pm = None
        if _pm == "high":
            detected.append(_derived("ESBL"))
        elif _pm in ("ampc", "ampc_plasmid"):
            detected.append(_derived("AMPC"))
    if "stenotrophomonas" in org_lower:
        detected.append(_derived("STENO"))

    # MRSA fallback: لو S. aureus + Vancomycin S + Linezolid S -> اشتباه MRSA
    if (("staphylococcus aureus" in org_lower or "staphylococcus spp" in org_lower)
            and "MRSA" not in [d["phenotype"] for d in detected]):
        vanco_s   = sir_map.get("Vancomycin") == "S"
        linezo_s  = sir_map.get("Linezolid")  == "S"
        beta_r    = any(sir_map.get(d) == "R" for d in
                        ["Amoxicillin + Clavulanic acid","Cephalexin","Cefuroxime"])
        if beta_r and (vanco_s or linezo_s):
            detected.append({
                "phenotype": "Possible MRSA",
                "icon":      "⚠️",
                "label":     "Possible MRSA -- تأكيد مطلوب",
                "detail":    "نمط مقاومة beta-lactam مع حساسية للـ Vancomycin/Linezolid يشير لـ MRSA.",
                "action":    "أجرِ Cefoxitin disk diffusion أو PCR (mecA) للتأكيد.",
                "isolation": False,
                "matched_markers": [],
            })

    return detected


# =========================================================
# MODULE 2 -- AST Internal Consistency & Reportability Checker
# INTERNAL QC ONLY. Feeds the AST-QA report and the QC expander. It NEVER
# changes the antibiotic recommendations (allowed / warned / banned): it only
# flags results that should be reviewed before sign-out, so no treatment
# decision is ever derived from it.
#
# Four passes, run in order (see run_ast_qc):
#   1) reportability  -- "should this agent be on this organism's panel?"
#                        (intrinsic resistance / no breakpoints / in-vivo failure)
#   2) consistency    -- "do these results contradict each other?"
#                        (equivalence + hierarchy, with CTX-M / OXA-48 guards)
#   3) specimen fit   -- urinary-only agents reported for a non-urine isolate
#   4) phenotype      -- ESBL / carbapenemase pattern notes
#
# Passes 1-2 are provided by the shared ast_reportability / ast_consistency
# modules (single source of truth with the Orange Lab build). Passes 3-4 are
# inline. Output is English (complete sentences) on purpose: the internal PDF
# renders right-to-left Arabic incorrectly.
#
# References: EUCAST Intrinsic Resistance v3.3 | EUCAST Breakpoint Tables v16.1 |
#             CLSI M100 Ed36 | EUCAST Expert Rules.
# =========================================================

def _sir_val(sir_map: Dict[str, str], drug: str) -> str:
    return (sir_map.get(drug) or "").strip().upper()

def _org_any(org_lower: str, names) -> bool:
    return any(n in org_lower for n in names)

# Urinary-only agents: therapeutic levels are reached in urine only, so a result
# for a non-urine (systemic) isolate is not clinically actionable.
_URINARY_ONLY = {
    "Nitrofurantoin": "Nitrofurantoin reaches therapeutic concentrations only in urine.",
    "Fosfomycin":     "Oral fosfomycin is a urinary agent (IV fosfomycin is the systemic exception).",
    "Norfloxacin":    "Norfloxacin reaches adequate concentrations only in the urinary and GI tracts.",
}
# Non-Enterobacterales Gram-negatives NOT covered by the intrinsic-Enterobacterales
# reportability rule -- add a Gram-positive-only-agent guard for them here.
_NON_ENTERO_GN = ["pseudomonas", "acinetobacter", "stenotrophomonas",
                  "burkholderia", "moraxella"]
_GRAM_POS_ONLY = ["Vancomycin", "Teicoplanin", "Linezolid", "Daptomycin"]


def _pass_specimen_fit(specimen: str, sir_map: Dict[str, str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if classify_specimen(specimen) in ("urine", ""):   # urinary agents belong in urine
        return out
    for drug, why in _URINARY_ONLY.items():
        if _sir_val(sir_map, drug) in ("S", "I", "R"):
            out.append({
                "id": f"SPEC-URN:{drug}",
                "severity": "warning",
                "message": (f"⚠️ **Specimen appropriateness** — **{drug} [{_sir_val(sir_map, drug)}]** — "
                            f"tested on a {specimen} isolate. {why} It is not clinically actionable "
                            f"for a non-urinary (systemic) infection."),
                "fix": (f"Suppress {drug} from the {specimen} report; it is a urinary-tract agent only.  \n"
                        f"📖 EUCAST Breakpoint Tables v16.1 — agent site-of-infection notes"),
            })
    return out


def _pass_non_entero_gram_pos(org_lower: str, sir_map: Dict[str, str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not _org_any(org_lower, _NON_ENTERO_GN):
        return out
    for drug in _GRAM_POS_ONLY:
        v = _sir_val(sir_map, drug)
        if v in ("S", "I", "R"):
            out.append({
                "id": f"REP-GPO-GN:{drug}",
                "severity": "error",
                "message": (f"🚫 **Intrinsic resistance** — **{drug} [{v}]** — reported for a "
                            f"Gram-negative organism, but {drug} has no activity and no breakpoint "
                            f"against Gram-negative bacteria."),
                "fix": (f"Remove {drug}; it must never be tested or reported for a Gram-negative isolate.  \n"
                        f"📖 EUCAST Intrinsic Resistance v3.3"),
            })
    return out


# ── Phenotype-level rules (ESBL / carbapenemase). Intrinsic-resistance and
#    equivalence checks that used to live here are now handled by the
#    reportability / consistency modules, so only the phenotype notes remain.
#    QC006 is corrected to the EUCAST v16.1 "report as tested" stance. ──
AST_QC_RULES = [
    {
        "id": "QC003",
        # Excluded: the Morganellaceae (Proteus / Providencia / Morganella) and
        # Serratia are INTRINSICALLY colistin-resistant, so "Colistin R" is the
        # expected result for them and flagging it as atypical sent the lab
        # chasing a correct identification. EUCAST v3.3 Table 1.
        "organisms": [],
        "not_organisms": ["proteus", "providencia", "morganella", "serratia",
                          "hafnia", "edwardsiella", "burkholderia"],
        "condition": lambda s: (
            any(s.get(d) == "S" for d in ["Imipenem/Cilastatin", "Meropenem"]) and
            s.get("Colistin") == "R" and
            sum(1 for v in s.values() if v == "R") >= 6
        ),
        "severity": "warning",
        "message": "⚠️ A carbapenem is Susceptible while Colistin is Resistant amid broad resistance. "
                   "This unusual pattern warrants confirmation of the organism identification.",
        "fix": "Verify the isolate identification; this susceptibility pattern is atypical.  \n"
               "📖 EUCAST Expert Rules",
    },
    {
        "id": "QC004",
        "organisms": ["E. coli", "Escherichia", "Klebsiella", "Proteus", "Enterobacter",
                      "Citrobacter", "Serratia", "Enterobacterales"],
        # FIX 2026-11-10: split by marker. Imipenem R is EXPECTED in Proteeae
        # (intrinsically elevated MICs), so it cannot trigger the carbapenemase
        # prompt for Proteus / Morganella / Providencia. Meropenem/Ertapenem R
        # still does (QC004 below); imipenem R does for the rest (QC004b).
        "condition": lambda s: (
            any(s.get(d) == "S" for d in ["Ceftriaxone", "Cefotaxime", "Cefepime"]) and
            any(s.get(d) == "R" for d in ["Meropenem", "Ertapenem"])
        ),
        "severity": "warning",
        "message": "⚠️ A carbapenem is Resistant while a cephalosporin is Susceptible. This pattern is "
                   "uncommon (it may reflect an OXA-48-like carbapenemase or porin loss) and should be confirmed.",
        "fix": "Confirm with a carbapenemase assay (e.g., mCIM / PCR) before reporting.  \n"
               "📖 EUCAST Guidance on detection of resistance mechanisms",
    },
    {
        "id": "QC004b",
        "organisms": ["E. coli", "Escherichia", "Klebsiella", "Enterobacter",
                      "Citrobacter", "Serratia", "Enterobacterales"],
        "not_organisms": ["proteus", "morganella", "providencia"],
        "condition": lambda s: (
            any(s.get(d) == "S" for d in ["Ceftriaxone", "Cefotaxime", "Cefepime"]) and
            s.get("Imipenem/Cilastatin") == "R"
            and s.get("Meropenem") != "R" and s.get("Ertapenem") != "R"
        ),
        "severity": "warning",
        "message": "⚠️ Imipenem is Resistant while a cephalosporin is Susceptible. This pattern is "
                   "uncommon (it may reflect a carbapenemase or porin loss) and should be confirmed.",
        "fix": "Confirm with a carbapenemase assay (e.g., mCIM / PCR) before reporting.  \n"
               "📖 EUCAST Guidance on detection of resistance mechanisms",
    },
    {
        "id": "QC005",
        "organisms": ["Staphylococcus aureus", "MRSA"],
        "condition": lambda s: s.get("Linezolid") == "R",
        "severity": "warning",
        "message": "⚠️ Linezolid Resistance in Staphylococcus aureus is very rare and should be confirmed.",
        "fix": "Repeat by a reference method (Etest or broth microdilution) before reporting.  \n"
               "📖 CLSI M100 Ed36",
    },
    {
        "id": "QC006",
        "organisms": ["E. coli", "Escherichia", "Klebsiella", "Proteus"],
        "condition": lambda s: (
            any(s.get(d) == "R" for d in ["Ceftriaxone", "Cefotaxime"]) and
            any(s.get(d) == "S" for d in [
                "Cefuroxime", "Cephalexin", "Cefaclor", "Cefixime",
                "Cefoperazone", "Cefoperazone + Sulbactam"])
        ),
        "trigger_fn": lambda s: [
            d for d in ["Cefuroxime", "Cephalexin", "Cefaclor", "Cefixime",
                        "Cefoperazone", "Cefoperazone + Sulbactam"] if s.get(d) == "S"],
        "trigger_r_fn": lambda s: [d for d in ["Ceftriaxone", "Cefotaxime"] if s.get(d) == "R"],
        "severity": "warning",
        "message": "⚠️ **Pattern worth noting** — {r_drug} = R with a lower-generation cephalosporin "
                   "({drugs}) = S, a pattern often seen with ESBL production. First check for a "
                   "third-generation cephalosporin discrepancy (see any panel-discrepancy alerts above).",
        "fix": "LABORATORY REPORTING: report susceptibilities exactly as tested. Per EUCAST Breakpoint "
               "Tables v16.1, the current cephalosporin breakpoints already detect the clinically "
               "important mechanisms, and the presence or absence of an ESBL does not by itself change "
               "the category -- do NOT edit a Susceptible cephalosporin to Resistant (that pre-2017 "
               "practice was withdrawn). ESBL detection is for infection control and surveillance only.  \n"
               "TREATMENT (separate, physician-level decision): a carbapenem is preferred over "
               "cephalosporins / piperacillin-tazobactam for ESBL bacteraemia even when they test "
               "Susceptible (IDSA AMR guidance; MERINO trial, JAMA 2018).  \n"
               "📖 EUCAST Breakpoint Tables v16.1 -- Enterobacterales, note on cephalosporin breakpoints and ESBL",
    },
]


def run_ast_qc(organism: str, sir_map: Dict[str, str], specimen: str = "") -> List[Dict[str, Any]]:
    """Internal AST consistency / reportability audit (English, informational only).

    INFORMATIONAL ONLY -- never consulted when building the antibiotic
    recommendations, so it can flag freely without affecting any decision.
    Returns a de-duplicated list of {id, severity, message, fix}.
    """
    sir_map = normalize_sir_map(sir_map)
    if not sir_map:
        return []
    org_lower = (organism or "").lower()
    issues: List[Dict[str, Any]] = []

    # ── Pass 1: reportability (shared module) ────────────────────────────────
    if AST_RULES_MODULES_AVAILABLE and _check_reportability_ext:
        try:
            for _iss in _check_reportability_ext(organism, sir_map):
                _r = _fmt_reportability(_iss, lang="en")
                issues.append({
                    "id": _iss.get("id", "REP"),
                    "severity": _iss.get("severity", "warning"),
                    "message": _r["message"],
                    "fix": _r["fix"],
                })
        except Exception as _e:
            logger.warning("reportability pass failed: %s", _e, exc_info=True)

    # ── Pass 2: internal consistency (shared module) ─────────────────────────
    if AST_RULES_MODULES_AVAILABLE and _check_consistency_ext:
        try:
            for _iss in _check_consistency_ext(organism, sir_map):
                _r = _fmt_consistency(_iss, lang="en")
                issues.append({
                    "id": _iss.get("id", "CON"),
                    "severity": _iss.get("severity", "error"),
                    "message": _r["message"],
                    "fix": _r["fix"],
                })
        except Exception as _e:
            logger.warning("consistency pass failed: %s", _e, exc_info=True)

    # ── Pass 3: specimen appropriateness + non-Enterobacterales GN guard ─────
    issues.extend(_pass_specimen_fit(specimen, sir_map))
    # The shared ast_reportability module now flags wrong-spectrum agents for ALL
    # Gram-negatives (a superset of this inline guard). Run the inline guard ONLY
    # as a fallback when that module is absent, so the two never double-report.
    if not AST_RULES_MODULES_AVAILABLE:
        issues.extend(_pass_non_entero_gram_pos(org_lower, sir_map))

    # ── Pass 4: phenotype rules ──────────────────────────────────────────────
    for rule in AST_QC_RULES:
        if rule["organisms"]:
            if not any(o.lower() in org_lower or org_lower in o.lower()
                       for o in rule["organisms"]):
                continue
        # Negative gating. Without this the "not_organisms" key on a rule would be
        # silently inert -- the rule would still fire on the very species it names
        # as exclusions. ast_reportability already supports this; AST_QC_RULES did
        # not, so the two rule engines disagreed on how a rule is scoped.
        if rule.get("not_organisms"):
            if any(o.lower() in org_lower for o in rule["not_organisms"]):
                continue
        try:
            if rule["condition"](sir_map):
                _msg = rule["message"]
                if "trigger_r_fn" in rule and "{r_drug}" in _msg:
                    _rt = rule["trigger_r_fn"](sir_map)
                    _msg = _msg.replace("{r_drug}", " / ".join(_rt) if _rt else "Cephalosporin")
                if "trigger_fn" in rule and "{drugs}" in _msg:
                    _tt = rule["trigger_fn"](sir_map)
                    _msg = _msg.replace("{drugs}", " / ".join(_tt) if _tt else "Cephalosporin")
                issues.append({
                    "id": rule["id"], "severity": rule["severity"],
                    "message": _msg, "fix": rule["fix"],
                })
        except Exception as _exc:
            logger.warning("AST QC rule %s failed and was skipped: %s",
                           rule.get("id", "?"), _exc, exc_info=True)
            continue

    # De-duplicate identical findings
    _seen = set()
    _uniq: List[Dict[str, Any]] = []
    for it in issues:
        _k = (it["id"], it["message"])
        if _k not in _seen:
            _seen.add(_k)
            _uniq.append(it)
    return _uniq


def compute_qa_confidence(
    qc_issues: List[Dict[str, Any]],
    sir_map: Dict[str, str],
    organism: str,
) -> Dict[str, Any]:
    """
    Confidence Score للتوصية العلاجية — بناءً على:
      1. عدد وشدة الـ QA issues (errors تخفض أكتر من warnings)
      2. اكتمال الـ AST panel (عدد المضادات المختبرة)
    يرجع: {level, score, icon, color, reasons}
    """
    score   = 100
    reasons = []

    n_errors   = sum(1 for i in qc_issues if i.get("severity") == "error")
    n_warnings = sum(1 for i in qc_issues if i.get("severity") == "warning")

    if n_errors:
        score -= n_errors * 30
        reasons.append(f"{n_errors} تناقض حرج (error) في نتائج الـ AST")
    if n_warnings:
        score -= n_warnings * 12
        reasons.append(f"{n_warnings} ملاحظة (warning) تستدعي المراجعة")

    n_tested = len(sir_map) if sir_map else 0
    if n_tested == 0:
        score -= 50
        reasons.append("لا توجد نتائج AST مدخلة")
    elif n_tested <= 2:
        score -= 35
        reasons.append(f"عدد المضادات المختبرة قليل جداً ({n_tested}) -- لا يكفي لتوصية موثوقة")
    elif n_tested < 5:
        score -= 20
        reasons.append(f"عدد المضادات المختبرة قليل ({n_tested}) -- قد لا يغطي كل الخيارات العلاجية")
    elif n_tested < 8:
        score -= 8
        reasons.append(f"عدد المضادات المختبرة محدود ({n_tested})")

    score = max(0, min(100, score))

    if score >= 80:
        level, icon, color = "High Confidence",     "🟢", "#1e8449"
    elif score >= 50:
        level, icon, color = "Moderate Confidence", "🟡", "#b7770d"
    else:
        level, icon, color = "Low Confidence",      "🔴", "#922b21"

    if not reasons:
        reasons.append("لا توجد مشاكل مكتشفة -- تقرير AST مكتمل ومتسق")

    return {
        "level":      level,  "icon":  icon,  "color": color,
        "score":      score,  "reasons": reasons,
        "n_errors":   n_errors, "n_warnings": n_warnings, "n_tested": n_tested,
    }


def generate_qa_report_pdf(
    organism: str,
    specimen: str,
    sir_map: Dict[str, str],
    qc_issues: List[Dict[str, Any]],
    confidence: Dict[str, Any],
    microbiologist: str = "",
    lab_id: str = "",
    patient_ref: str = "",
) -> Optional[bytes]:
    """
    تقرير AST-QA PDF منفصل تماماً عن تقرير الطبيب.
    للأرشفة الداخلية ومراجعة الجودة من قِبل الميكروبيولوجي فقط.
    لا يُعرض ولا يُرسل للطبيب المعالج.
    """
    if not WEASYPRINT_AVAILABLE or _wp is None:
        return None

    _now = datetime.now().strftime("%Y-%m-%d  %H:%M")

    H: List[str] = []
    H.append("""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@page { size:A4; margin:12mm 14mm; }
body { font-family:'Segoe UI',Tahoma,Arial,sans-serif; color:#1a1a2e; font-size:10pt; }
.hdr { border-bottom:2px solid #6e2fa0; padding-bottom:3mm; margin-bottom:4mm; }
.hdr-title { font-size:16pt; font-weight:bold; color:#6e2fa0; }
.hdr-sub   { font-size:9pt; color:#888; margin-top:1mm; }
.meta-row  { display:flex; justify-content:space-between; font-size:9pt; margin-bottom:3mm;
             background:#f7f5fb; padding:2.5mm 3mm; border-radius:2mm; }
.sec-ttl   { font-size:11pt; font-weight:bold; color:#6e2fa0;
             border-bottom:1px solid #ddd; padding-bottom:1mm; margin:4mm 0 2mm 0; }
.conf-box  { padding:3mm; border-radius:2mm; margin-bottom:4mm; }
.issue     { padding:2mm 3mm; margin:1.5mm 0; border-radius:1.5mm; font-size:9pt; line-height:1.5; }
.err       { background:#fdf2f2; border-left:3px solid #922b21; }
.warn      { background:#fef9e7; border-left:3px solid #b7770d; }
.ast-tbl   { width:100%; border-collapse:collapse; font-size:8.5pt; margin-top:2mm; }
.ast-tbl th{ background:#6e2fa0; color:#fff; padding:1.5mm 2mm; text-align:left; }
.ast-tbl td{ padding:1.2mm 2mm; border-bottom:1px solid #eee; }
.sir-S     { color:#1e8449; font-weight:bold; }
.sir-I     { color:#b7770d; font-weight:bold; }
.sir-R     { color:#922b21; font-weight:bold; }
.footer    { margin-top:6mm; padding-top:2mm; border-top:1px solid #ddd;
             font-size:7.5pt; color:#888; }
.org-box   { background:#f7f5fb; border-left:3px solid #6e2fa0; padding:2mm 3mm;
             border-radius:1.5mm; font-size:8.8pt; line-height:1.45; }
.org-box .ar { direction:rtl; text-align:right; unicode-bidi:isolate; margin-bottom:1mm;
               font-family:'Amiri','Noto Naskh Arabic','Segoe UI',Tahoma,Arial,sans-serif; }
.org-box .ln { direction:ltr; margin-top:0.6mm; }
.sir-line  { font-size:8.8pt; line-height:1.5; margin:0.8mm 0; }
.confidential { background:#fdf2f2; color:#922b21; font-weight:bold;
                text-align:center; padding:1.5mm; border-radius:1.5mm;
                font-size:8.5pt; margin-bottom:3mm; }
</style></head><body>""")

    H.append(
        '<div class="confidential">'
        '🔒 INTERNAL LABORATORY USE ONLY &nbsp;—&nbsp; '
        'NOT FOR PHYSICIAN OR PATIENT DISTRIBUTION'
        '</div>'
    )

    H.append(
        '<div class="hdr">'
        '<div class="hdr-title">🔬 AST Quality Assurance Report</div>'
        '<div class="hdr-sub">Laboratory Consistency &amp; Confidence Audit — Internal QA Archive</div>'
        '</div>'
    )

    H.append(
        '<div class="meta-row">'
        f'<div><b>Organism:</b>&nbsp;{_esc(organism or "—")}</div>'
        f'<div><b>Specimen:</b>&nbsp;{_esc(specimen or "—")}</div>'
        f'<div><b>Generated:</b>&nbsp;{_esc(_now)}</div>'
        '</div>'
    )
    H.append(
        '<div class="meta-row">'
        f'<div><b>Microbiologist:</b>&nbsp;{_esc(microbiologist or "—")}</div>'
        f'<div><b>Patient Ref:</b>&nbsp;{_esc(patient_ref or "—")}</div>'
        f'<div><b>Lab ID:</b>&nbsp;{_esc(lab_id or "—")}</div>'
        '</div>'
    )

    # ── Organism summary (2026-11-11) ──────────────────────────────────────
    # The same guidance card the screen shows under the specimen data, in full,
    # so the archived QA sheet says what the organism IS, not only its name.
    _op_qa = ORGANISM_PROFILE.get(organism) or {}
    if _op_qa:
        H.append('<div class="sec-ttl">📌 Organism Summary</div>')
        H.append('<div class="org-box">')
        if _op_qa.get("note"):
            H.append(f'<div class="ar">{_md_inline(_op_qa["note"])}</div>')
        _ctx_qa = (_op_qa.get("specimen_context") or {}).get(specimen, "")
        if _ctx_qa:
            H.append(f'<div class="ar"><b>{_esc(specimen)}:</b> {_md_inline(_ctx_qa)}</div>')
        for _lbl, _key in (("First-line", "first_line"), ("Second-line", "second_line"),
                           ("Third-line", "third_line"), ("Avoid", "avoid")):
            if _op_qa.get(_key):
                H.append(f'<div class="ln"><b>{_lbl}:</b> {_esc(", ".join(_op_qa[_key]))}</div>')
        if "urine" in str(specimen).lower() and _op_qa.get("urine_note"):
            H.append(f'<div class="ar">{_md_inline(_op_qa["urine_note"])}</div>')
        H.append('</div>')

    # ── Confidence Score ──────────────────────────────────────────────
    H.append('<div class="sec-ttl">📊 Recommendation Confidence Score</div>')
    H.append(
        f'<div class="conf-box" style="background:{confidence["color"]}18;'
        f'border:1.5px solid {confidence["color"]}">'
        f'<div style="font-size:13pt;font-weight:bold;color:{confidence["color"]}">'
        f'{confidence["icon"]} {_esc(confidence["level"])} — {confidence["score"]}/100</div>'
        '<ul style="margin:2mm 0 0 4mm;padding:0;font-size:9pt">'
        + "".join(f'<li>{_esc(r)}</li>' for r in confidence["reasons"])
        + '</ul></div>'
    )
    H.append(
        f'<div style="font-size:8pt;color:#888;margin-bottom:3mm">'
        f'Errors: <b>{confidence["n_errors"]}</b> &nbsp;|&nbsp; '
        f'Warnings: <b>{confidence["n_warnings"]}</b> &nbsp;|&nbsp; '
        f'Antibiotics tested: <b>{confidence["n_tested"]}</b>'
        '</div>'
    )

    # ── QC Issues ────────────────────────────────────────────────────
    H.append(f'<div class="sec-ttl">🔍 AST-QA Findings ({len(qc_issues)})</div>')
    if not qc_issues:
        H.append(
            '<div style="font-size:9.5pt;color:#1e8449">'
            '✅ All AST consistency checks passed. No issues detected.'
            '</div>'
        )
    else:
        for issue in qc_issues:
            cls  = "err" if issue["severity"] == "error" else "warn"
            icon = "❌"  if issue["severity"] == "error" else "⚠️"
            H.append(
                f'<div class="issue {cls}">'
                f'<b>{icon} {_esc(issue["severity"].upper())}</b><br>'
                f'{_md_inline(issue["message"])}<br>'
                f'<span style="color:#555">✏️ {_md_inline(issue["fix"])}</span>'
                '</div>'
            )

    # ── AST Panel Completeness ──────────────────────────────────────────
    # Added 2026-08-22: this is THE internal QA PDF (confirmed against a
    # live screenshot -- "تقرير الجودة الداخلي للميكروبيولوجي فقط" is
    # this document's own header text) -- Panel Completeness had been added
    # to generate_report()/generate_pdf_html_report() (the CLINICIAN-facing
    # report) instead, which was the wrong document for an "internal AST
    # report" request. Kept in both now; this is the one that actually
    # matters for "was enough tested" as a QA question, not a treatment one.
    if PANEL_COMPLETENESS_AVAILABLE and _check_panel_completeness_ext and sir_map:
        _pc_pdf = _check_panel_completeness_ext(organism, specimen, sir_map)
        if _pc_pdf.status != "not_evaluated":
            _pc_pdf_missing = _pc_pdf.missing_primary + _pc_pdf.missing_supplemental
            H.append('<div class="sec-ttl">🧫 AST Panel Completeness</div>')
            H.append(
                f'<div style="font-size:9pt;color:#555;margin-bottom:2mm">'
                f'Organism group: <b>{_esc(_pc_pdf.organism_group)}</b> &nbsp;|&nbsp; '
                f'Expected: <b>{_pc_pdf.expected_total}</b> &nbsp;|&nbsp; '
                f'Tested: <b>{_pc_pdf.tested_count}</b> &nbsp;|&nbsp; '
                f'Missing: <b>{len(_pc_pdf_missing)}</b>'
                '</div>'
            )
            if not _pc_pdf_missing:
                H.append(
                    '<div style="font-size:9.5pt;color:#1e8449">'
                    '✅ Panel adequate -- all expected agents for this organism were tested.'
                    '</div>'
                )
            else:
                if _pc_pdf.status == "critical":
                    H.append(
                        '<div class="issue err">'
                        '<b>❌ CRITICAL</b><br>'
                        'Every primary agent tested came back Resistant, and expected '
                        'primary agent(s) were never tested. A therapeutic option may '
                        'exist among the untested agents -- this panel cannot rule that '
                        'out. Do not report &ldquo;no susceptible options&rdquo; from an '
                        'incomplete panel.'
                        '</div>'
                    )
                if _pc_pdf.missing_primary:
                    H.append(
                        f'<div class="issue warn"><b>⚠️ Missing (primary)</b><br>'
                        f'{_esc(", ".join(_pc_pdf.missing_primary))}</div>'
                    )
                if _pc_pdf.missing_supplemental:
                    H.append(
                        f'<div style="font-size:8.5pt;color:#555;margin:1mm 0">'
                        f'🔵 Missing (supplemental): {_esc(", ".join(_pc_pdf.missing_supplemental))}'
                        '</div>'
                    )
            if _pc_pdf.rule_id:
                _pc_pdf_ref = citation_line(_pc_pdf.rule_id) if 'citation_line' in dir() else ""
                try:
                    from guideline_registry import citation_line as _pc_pdf_cite_fn
                    _pc_pdf_ref = _pc_pdf_cite_fn(_pc_pdf.rule_id)
                except Exception:
                    _pc_pdf_ref = ""
                if _pc_pdf_ref:
                    H.append(
                        f'<div style="font-size:7.5pt;color:#888">📖 {_esc(_pc_pdf_ref)}</div>'
                    )

    # ── Full AST Panel ────────────────────────────────────────────────
    # Compact since 2026-11-11: one row per drug pushed the sheet onto a
    # second page for any normal panel. Grouped by result it is three lines,
    # and nothing is lost -- every tested agent is still named.
    H.append('<div class="sec-ttl">🧪 Full AST Panel as Entered</div>')
    if sir_map:
        for _res, _lbl in (("S", "Susceptible"), ("I", "Intermediate / SDD"), ("R", "Resistant")):
            _grp = sorted(d for d, r in sir_map.items() if r == _res)
            if _grp:
                H.append(f'<div class="sir-line"><span class="sir-{_res}">{_res} — {_lbl} '
                         f'({len(_grp)}):</span> {_esc(", ".join(_grp))}</div>')
        _oth = sorted(f"{d} ({r})" for d, r in sir_map.items() if r not in ("S", "I", "R"))
        if _oth:
            H.append(f'<div class="sir-line"><b>Other:</b> {_esc(", ".join(_oth))}</div>')
    else:
        H.append('<div style="font-size:9pt;color:#888">No AST data recorded.</div>')

    H.append(
        '<div class="footer">'
        'Generated by Orange Lab AST-QA Engine&nbsp;|&nbsp;'
        'EUCAST Expert Rules v3.1 (2016) / CLSI M100 Ed36<br>'
        'This document is for internal laboratory quality control and audit only. '
        'It must not be shared with referring physicians or included in the patient report.'
        '</div>'
    )
    H.append('</body></html>')

    try:
        return _wp.HTML(string=pdf_glyph_guard("".join(H))).write_pdf()
    except Exception:
        return None


def generate_patho_report_pdf(
    patho_result: Dict[str, Any],
    organism: str,
    specimen: str,
    inputs: Optional[Dict[str, Any]] = None,
    patient_ref: str = "",
    lang: str = "ar",
    return_html: bool = False,
):
    """Stand-alone PDF of the Pathogenicity Assessment (added 2026-11-11).

    Everything the panel shows -- score, verdict, threshold, supporting and
    opposing factors, interpretive notes, recommendations, references -- on
    one sheet, so the Arabic recommendations can be printed and filed.
    lang="ar" prints the Arabic interpretation; lang="en" prints the English
    forms and carries no Arabic. `return_html` allows inspection without
    WeasyPrint.
    """
    if not patho_result:
        return None
    if not return_html and (not WEASYPRINT_AVAILABLE or _wp is None):
        return None
    en = not str(lang or "ar").lower().startswith("ar")
    pr = patho_result
    sc = int(pr.get("score", 0))
    col = {"error": "#922b21", "warning": "#b7770d"}.get(pr.get("color"), "#1e8449")
    interp = pr.get("interpretation_en") if en else pr.get("interpretation")
    recs = pr.get("recommendations_en") if en else pr.get("recommendations")
    notes = pr.get("notes_en") if en else pr.get("notes")
    tcls = "ltr" if en else "ar"
    _conf = {"high": ("High", "عالية"), "moderate": ("Moderate", "متوسطة"),
             "low": ("Low", "منخفضة")}.get(pr.get("confidence"), ("-", "-"))

    def T(e, a):
        return e if en else a

    H: List[str] = []
    H.append("""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@page { size:A4; margin:12mm 14mm; }
body { font-family:'Noto Sans','Segoe UI',Tahoma,Arial,'DejaVu Sans',sans-serif; color:#1a1a2e; font-size:10pt; }
.hdr { border-bottom:2px solid #0b6e6e; padding-bottom:3mm; margin-bottom:4mm; }
.hdr-title { font-size:16pt; font-weight:bold; color:#0b6e6e; }
.hdr-sub { font-size:9pt; color:#888; margin-top:1mm; }
.meta { display:flex; justify-content:space-between; font-size:9pt; margin-bottom:2mm;
        background:#f2f8f8; padding:2.5mm 3mm; border-radius:2mm; }
.sec { font-size:11pt; font-weight:bold; color:#0b6e6e; border-bottom:1px solid #ddd;
       padding-bottom:1mm; margin:4mm 0 2mm 0; }
.bar { height:4mm; background:#e6e6e6; border-radius:2mm; overflow:hidden; }
.fill { height:4mm; }
.verdict { font-size:13pt; font-weight:bold; margin:2mm 0; }
.ar { direction:rtl; text-align:right; unicode-bidi:isolate; line-height:1.6;
      font-family:'Amiri','Noto Naskh Arabic','Segoe UI',Tahoma,Arial,sans-serif; }
.ltr { direction:ltr; text-align:left; line-height:1.5; }
.row { font-size:9.3pt; margin:1.2mm 0; }
.pos { color:#1e8449; } .neg { color:#b7770d; }
.box { background:#f7f7f9; border-left:3px solid #0b6e6e; padding:2mm 3mm; border-radius:1.5mm; }
.in-tbl { width:100%; border-collapse:collapse; font-size:8.8pt; }
.in-tbl td { padding:1mm 2mm; border-bottom:1px solid #eee; vertical-align:top; }
.in-tbl td.k { width:34%; color:#555; }
.footer { margin-top:6mm; padding-top:2mm; border-top:1px solid #ddd; font-size:7.5pt; color:#888; }
</style></head><body>""")
    H.append('<div class="hdr"><div class="hdr-title">Pathogenicity Assessment Report</div>'
             '<div class="hdr-sub">Infection vs colonisation vs contamination — '
             f'engine v{_esc(str(pr.get("engine_version", "")))}</div></div>')
    H.append('<div class="meta">'
             f'<div><b>Organism:</b>&nbsp;{_esc(organism or "—")}</div>'
             f'<div><b>Specimen:</b>&nbsp;{_esc(specimen or "—")}</div>'
             f'<div><b>Generated:</b>&nbsp;{_esc(datetime.now().strftime("%Y-%m-%d  %H:%M"))}</div></div>')
    if patient_ref:
        H.append(f'<div class="meta"><div><b>Patient Ref:</b>&nbsp;%%PATIENT%%</div></div>')

    H.append(f'<div class="sec">{T("Result", "النتيجة")}</div>')
    H.append(f'<div class="bar"><div class="fill" style="width:{sc}%;background:{col}"></div></div>')
    H.append(f'<div class="verdict" style="color:{col}">{sc}% — {_esc(str(pr.get("verdict", "")))}</div>')
    H.append(f'<div class="row">{T("Assessment confidence", "ثقة التقييم")}: '
             f'<b>{_conf[0] if en else _conf[1]}</b></div>')
    if pr.get("threshold"):
        H.append(f'<div class="row ltr"><b>Threshold applied:</b> {_esc(pr["threshold"])}</div>')
    if pr.get("missing_inputs"):
        H.append(f'<div class="row ltr neg"><b>Not entered (not counted against infection):</b> '
                 f'{_esc(", ".join(pr["missing_inputs"]))}</div>')
    if interp:
        H.append(f'<div class="box {tcls}">{_esc(interp)}</div>')

    if inputs:
        _rows = [(k, v) for k, v in inputs.items() if v not in (None, "", [], "مش محدد", "مش متعملة")]
        if _rows:
            H.append(f'<div class="sec">{T("Data entered", "البيانات المُدخلة")}</div>')
            H.append('<table class="in-tbl">')
            for k, v in _rows:
                v = ", ".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v)
                H.append(f'<tr><td class="k">{_esc(k)}</td><td>{_esc(v)}</td></tr>')
            H.append('</table>')

    if pr.get("factors_pos"):
        H.append(f'<div class="sec">{T("Supporting infection", "عوامل تدعم العدوى")}</div>')
        for f in pr["factors_pos"]:
            H.append(f'<div class="row pos" style="unicode-bidi:plaintext">{_esc(f)}</div>')
    if pr.get("factors_neg"):
        H.append(f'<div class="sec">{T("Against infection", "عوامل ضد العدوى")}</div>')
        for f in pr["factors_neg"]:
            H.append(f'<div class="row neg" style="unicode-bidi:plaintext">{_esc(f)}</div>')
    if notes:
        H.append(f'<div class="sec">{T("Interpretive notes", "ملاحظات تفسيرية")}</div>')
        for n_ in notes:
            H.append(f'<div class="row {tcls}">{_esc(n_)}</div>')
    if recs:
        H.append(f'<div class="sec">{T("Recommendations", "التوصيات")}</div>')
        for r_ in recs:
            H.append(f'<div class="row {tcls}">• {_esc(r_)}</div>')
    if pr.get("references"):
        H.append('<div class="sec">References</div>')
        H.append(f'<div class="row ltr" style="font-size:8.5pt;color:#555">'
                 f'{_esc(" · ".join(pr["references"]))}</div>')
    H.append('<div class="footer">Generated by Orange Lab Pathogenicity Engine. Decision support only: '
             'the significance of a culture is a clinical judgement that remains with the treating '
             'physician and the microbiologist.</div></body></html>')
    html = "".join(H)
    if en:
        # UI option labels that carry Arabic words: say them in English first,
        # so the strip below cannot turn "Organisms بدون WBCs" into "Organisms WBCs".
        for _a, _e in (("بدون", "without"), ("مش متعملة", "Not done"), ("مش محدد", "Not specified"),
                       ("طبيعية", "Normal"), ("تاريخ UTIs متكررة", "Recurrent UTIs"),
                       ("(لاهوائيات)", "")):
            html = html.replace(_a, _e)
        # the factor lines are English already; this is the guarantee, not the mechanism
        html = re.sub(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]+", "", html)
        html = re.sub(r"\(\s*\)", "", html)
    html = html.replace("%%PATIENT%%", _esc(patient_ref or ""))
    if return_html:
        return html
    try:
        return _wp.HTML(string=pdf_glyph_guard(html)).write_pdf()
    except Exception:
        return None


# =========================================================
# MODULE 3 -- Smart Antibiotic Ranking
# يرتب الأدوية الـ Sensitive حسب الأولوية السريرية
# =========================================================
RANKING_WEIGHTS = {
    "aware_score":     {"Access": 3, "Watch": 2, "Reserve": 1, None: 0},
    "route_score":     {"oral": 2, "iv": 1},
    "specimen_match":  2,   # bonus لو الدواء له specimen_note للعينة دي
    "priority_bonus":  lambda p: max(0, 6 - p),  # priority 1 -> +5, priority 5 -> +1
}

def rank_sensitive_antibiotics(
    allowed:      List[Dict],
    culture_type: str,
    organism:     str,
    sir_map:      Dict[str, str],
    phenotypes:   List[Dict],
) -> List[Dict]:
    """
    يرتب الأدوية المسموحة بترتيب هرمي صارم (lexicographic) — كل معيار يكسر
    التعادل في المعيار الأهم منه فقط، فلا يتغلب معيار أدنى على أعلى:

      1. نتيجة المزرعة   : S قبل I  (بوابة صارمة — لا يتخطى I دواءً S أبداً)
      2. ملاءمة العينة   : دواء له specimen_note للعينة الحالية أولاً
      3. WHO AWaRe       : Access > Watch > Reserve
      4. طريق الإعطاء     : Oral قبل IV/IM (لو المريض مؤهل)
      5. Priority        : أولوية الـ guidelines (أقل = أفضل)
      6. الاسم           : لضمان ترتيب ثابت (deterministic)

    ملاحظة تصميمية: السبب في استخدام الترتيب الهرمي بدل جمع النقاط أن جمع
    النقاط كان يسمح لدواء Intermediate ذي AWaRe/route جيد أن يتفوق على دواء
    Sensitive — وهذا خطأ إكلينيكي (الفعالية المخبرية تسبق كل شيء).
    يُحتفظ بـ _score كقيمة عرض تقريبية فقط، لا للترتيب.
    """
    ph_names = [p.get("phenotype", "") for p in phenotypes]
    _sir_rank   = {"S": 0, "I": 1}          # الأصغر = أفضل
    _aware_rank = {"Access": 0, "Watch": 1, "Reserve": 2}

    def sort_key(item):
        name = item.get("name", "")
        sir  = sir_map.get(name)
        # 1) Susceptibility gate (S=0, I=1, unknown=2 -> آخر القائمة)
        k_sir = _sir_rank.get(sir, 2)
        # 2) Specimen appropriateness (match=0 يسبق no-match=1)
        k_spec = 0 if (item.get("specimen_notes") or {}).get(culture_type) else 1
        # 3) AWaRe (Access first). لكن CRE/CRAB/CRPA تُنزّل السيفالوسبورين غير الـ S
        aware = item.get("aware")
        k_aware = _aware_rank.get(aware, 3)
        if any(ph in ph_names for ph in ["CRE", "CRAB", "CRPA"]):
            cls = item.get("class", "").lower()
            if "cephalosporin" in cls and sir != "S":
                k_aware += 5          # ادفعه لأسفل ضمن نفس مستوى الحساسية
        # 4) Route (oral first)
        k_route = 0 if item.get("high_po") else 1
        # 5) Priority (أقل أفضل)
        k_priority = item.get("priority", 99)
        return (k_sir, k_spec, k_aware, k_route, k_priority, name)

    # _score للعرض فقط (تقريبي) — لا يُستخدم في الترتيب
    def _display_score(item):
        name = item.get("name", "")
        sir  = sir_map.get(name)
        s = 0
        if sir == "S": s += 4
        elif sir == "I": s += 1
        s += RANKING_WEIGHTS["aware_score"].get(item.get("aware"), 0)
        s += RANKING_WEIGHTS["route_score"]["oral" if item.get("high_po") else "iv"]
        if (item.get("specimen_notes") or {}).get(culture_type):
            s += RANKING_WEIGHTS["specimen_match"]
        s += RANKING_WEIGHTS["priority_bonus"](item.get("priority", 5))
        return s

    scored = [
        {**item, "_score": _display_score(item), "_sir": (sir_map.get(item.get("name", "")) or "--")}
        for item in allowed
    ]
    return sorted(scored, key=sort_key)


# =========================================================
# MODULE 4 -- Infection Syndrome Module
# يربط Specimen + Organism + Phenotype بـ clinical syndrome
# =========================================================
INFECTION_SYNDROMES = {
    ("Urine", None): {
        "syndrome":  "Urinary Tract Infection (UTI)",
        "classify":  lambda age, is_preg, is_cath: (
            "Complicated UTI" if (is_cath or age > 65) else
            "Pregnancy-associated UTI" if is_preg else
            "Uncomplicated UTI"
        ),
        "first_choice": ["Nitrofurantoin","Fosfomycin","Trimethoprim/Sulfamethoxazole"],
        # 2026-11-10: cUTI 7 days (IDSA cUTI 2025); the culture threshold read
        # "10^3 symptomatic / 10^5 asymptomatic" for every patient -- the
        # 10^3 figure applies to symptomatic women and men specifically.
        "duration": {"Uncomplicated UTI": "1-7 أيام حسب الدواء (Nitrofurantoin 5 · TMP-SMX 3 · Fosfomycin جرعة)",
                     "Complicated UTI": "7 أيام عند الاستجابة السريعة (FQ 5-7) — 10-14 للاستجابة البطيئة",
                     "Pregnancy-associated UTI": "5-7 أيام"},
        "escalation": "لو فشل الخط الأول أو CrCl < 45 (Nitrofurantoin) -> حسب الحساسية: Cefixime / Ciprofloxacin",
        "culture_threshold": ("≥ 10³ CFU/mL مع أعراض (نساء ورجال)؛ ≥ 10⁵ للبيلة اللاعرضية "
                              "(تُعالج فقط في الحمل وقبل إجراء بولي جراحي)"),
    },
    ("Blood", None): {
        "syndrome":  "Bloodstream Infection (BSI) / Bacteremia",
        "classify":  lambda age, is_preg, is_cath: (
            "Catheter-Related BSI (CRBSI)" if is_cath else "Community/Hospital BSI"
        ),
        "first_choice": ["Ceftriaxone","Piperacillin-Tazobactam","Meropenem (MDR/severe)"],
        "duration": {"Community/Hospital BSI": ("GNB: 7 أيام مع السيطرة على المصدر (BALANCE 2025) · "
                                                 "S. aureus: ≥14 يوم · حسب الكائن والمصدر"),
                     "Catheter-Related BSI (CRBSI)": ("إزالة الكاتيتر + GNB 7-14 · CoNS 5-7 · "
                                                      "S. aureus ≥14 يوم")},
        "escalation": "MDR/XDR -> Meropenem ± Amikacin. Endocarditis اشتباه -> اتشاور",
        "culture_threshold": "2 sets blood cultures قبل المضاد",
    },
    ("Sputum", None): {
        "syndrome":  "Respiratory Tract Infection",
        # FIX 2026-11-11 (round 4): age > 65 alone was labelled "Severe CAP".
        # Age is ONE CURB-65 point; severity needs the score (or ATS/IDSA
        # major/minor criteria), and suggest_severity() already rates an
        # otherwise-well 70-year-old as moderate. The label now says what is
        # actually known.
        "classify":  lambda age, is_preg, is_cath: (
            "HAP/VAP" if is_cath else ("CAP (age > 65 — assess CURB-65 / PSI)" if age > 65 else "CAP")
        ),
        "first_choice": ["Amoxicillin + Clavulanic acid","Levofloxacin","Azithromycin"],
        "duration": {"CAP": "5 أيام كحد أدنى حتى الاستقرار",
                     "CAP (age > 65 — assess CURB-65 / PSI)": (
                         "5 أيام كحد أدنى حتى الاستقرار — 7 أيام للحالات الشديدة أو MRSA/Pseudomonas"),
                     "Severe CAP": "5-7 أيام (أطول لـ MRSA/Pseudomonas)",
                     "HAP/VAP": "7 أيام (ATS/IDSA 2016)"},
        "escalation": "Pseudomonas/Acinetobacter -> anti-pseudomonal mandatory",
        # FIX 2026-11-10: BAL threshold is 10^4 CFU/mL (10^3 for PSB, 10^5-10^6
        # for endotracheal aspirate) -- the line read BAL 10^5.
        "culture_threshold": "BAL ≥ 10⁴ CFU/mL · PSB ≥ 10³ · شفط رغامي ≥ 10⁵–10⁶ (ATS/IDSA 2016)",
    },
    ("Wound Swab", None): {
        "syndrome":  "Skin & Soft Tissue Infection (SSTI)",
        "classify":  lambda age, is_preg, is_cath: "SSTI",
        "first_choice": ["Cephalexin","Amoxicillin + Clavulanic acid"],
        "duration": {"SSTI": "5-10 أيام حسب الشدة"},
        "escalation": "MRSA اشتباه -> TMP/SMX أو Doxycycline. Diabetic foot -> broader coverage",
        "culture_threshold": "أخذ عينة من العمق -- لا من السطح",
    },
    ("Pus", None): {
        "syndrome":  "Abscess / Deep Infection",
        "classify":  lambda age, is_preg, is_cath: "Abscess",
        "first_choice": ["Amoxicillin + Clavulanic acid","Metronidazole"],
        "duration": {"Abscess": "Drainage + 5-7 أيام"},
        "escalation": "Intra-abdominal -> Metronidazole إلزامي. Carbapenem لو ESBL",
        "culture_threshold": "Drainage culture -- أدق من swab",
    },
    ("Stool", None): {
        "syndrome":  "Gastrointestinal Infection",
        "classify":  lambda age, is_preg, is_cath: (
            "Severe GI / Immunocompromised" if (age < 2 or age > 65 or is_preg) else "Mild-Moderate GI Infection"
        ),
        "first_choice": ["Azithromycin", "Ciprofloxacin (if susceptible)"],
        "duration": {
            "Mild-Moderate GI Infection": "Supportive care -- antibiotics usually NOT needed",
            "Severe GI / Immunocompromised": "3-5 days (Azithromycin/Cipro)",
        },
        "escalation": "C. diff -> Vancomycin PO / Fidaxomicin. Salmonella typhi -> 7-14d Ceftriaxone.",
        "culture_threshold": "Stool culture for severe/immunocompromised cases only",
    },
    ("Stool Culture", None): {
        "syndrome":  "Gastrointestinal Infection",
        "classify":  lambda age, is_preg, is_cath: (
            "Severe GI / Immunocompromised" if (age < 2 or age > 65 or is_preg) else "Mild-Moderate GI Infection"
        ),
        "first_choice": ["Azithromycin", "Ciprofloxacin (if susceptible)"],
        "duration": {"GI Infection": "Supportive care preferred -- antibiotics for severe cases only"},
        "escalation": "C. diff -> Vancomycin/Fidaxomicin | Salmonella typhi -> 7-14d",
        "culture_threshold": "Culture for severe/immunocompromised only",
    },
    ("CSF", None): {
        "syndrome":  "Central Nervous System Infection (Meningitis)",
        "classify":  lambda age, is_preg, is_cath: "Bacterial Meningitis",
        "first_choice": ["Ceftriaxone","Meropenem"],
        "duration": {"Bacterial Meningitis": ("N. meningitidis 7 · H. influenzae 7 · S. pneumoniae 10-14 · "
                                              "GBS 14-21 · Listeria ≥21 · GNB 21 يوم")},
        "escalation": "ابدأ تجريبياً فوراً ولا تنتظر culture. Dexamethasone قبل المضاد أو معه",
        "culture_threshold": "CSF culture + Gram stain + Ag testing",
    },
}

def get_infection_syndrome(
    specimen:  str,
    organism:  str,
    age:       int,
    is_preg:   bool,
    is_cath:   bool = False,
    sex:       str = "",
) -> Optional[Dict[str, Any]]:
    """
    يعيد السياق السريري للعدوى -- يدعم مطابقة مرنة لأسماء العينات.

    `sex` added 2026-11-11 (round 4): a urinary infection in a man is a
    complicated UTI (IDSA cUTI 2025) -- suggest_severity() and the duration
    engine already said so, while this panel, which never knew the sex, called
    it "Uncomplicated UTI" with the 1-7 day cystitis course on the same screen.
    """
    # Try exact match first
    syndrome_data = INFECTION_SYNDROMES.get((specimen, None))
    # Fuzzy fallback: match substring
    if not syndrome_data:
        spec_l = specimen.lower()
        for (key_spec, _), data in INFECTION_SYNDROMES.items():
            kl = key_spec.lower()
            if kl in spec_l or spec_l in kl:
                syndrome_data = data
                break
    # Canonical-category fallback (single source of truth -- classify_specimen)
    if not syndrome_data:
        _cat_to_key = {
            "urine": "Urine", "blood": "Blood", "sputum": "Sputum",
            "csf":   "CSF",   "stool": "Stool", "wound":  "Wound Swab",
            "pus":   "Pus",   "abdomen": "Pus",
        }
        _target = _cat_to_key.get(classify_specimen(specimen))
        if _target:
            syndrome_data = INFECTION_SYNDROMES.get((_target, None))

    if not syndrome_data:
        return None

    sub_type = syndrome_data["classify"](age, is_preg, is_cath)
    if (sub_type == "Uncomplicated UTI"
            and str(sex or "").strip().lower() in ("male", "m", "ذكر")):
        sub_type = "Complicated UTI"
    duration  = syndrome_data["duration"].get(sub_type, "حسب الاستجابة السريرية")

    return {
        "syndrome":       syndrome_data["syndrome"],
        "sub_type":       sub_type,
        "first_choice":   syndrome_data["first_choice"],
        "duration":       duration,
        "escalation":     syndrome_data["escalation"],
        "threshold":      syndrome_data["culture_threshold"],
    }



# =========================================================
# عرض نتيجة الـ Pathogenicity (مشترك بين البول وغير البول)
# =========================================================
def _render_patho_result(patho_result: dict) -> None:
    """Render a pathogenicity assessment result (score, verdict, factors, recs).
    Shared by the urine and non-urine pathogenicity panels (engine v3)."""
    sc    = patho_result["score"]
    color = patho_result["color"]
    flags = patho_result.get("special_flags", [])

    st.markdown(f"### Pathogenicity Score: **{sc}%**")
    st.progress(sc / 100)

    if color == "error":
        st.error(patho_result["verdict"])
    elif color == "warning":
        st.warning(patho_result["verdict"])
    else:
        st.success(patho_result["verdict"])

    _conf = patho_result.get("confidence")
    if _conf:
        _conf_ar = {"high": "عالية", "moderate": "متوسطة", "low": "منخفضة"}.get(_conf, _conf)
        st.caption(f"ثقة التقييم: **{_conf_ar}** · Engine v{patho_result.get('engine_version', '')}")
    if patho_result.get("threshold"):
        st.caption(f"📏 العتبة المطبّقة: {patho_result['threshold']}")
    if patho_result.get("missing_inputs"):
        st.warning("بيانات غير مُدخلة (لم تُحتسب ضد العدوى): "
                   + "، ".join(patho_result["missing_inputs"]))

    # Special-flag badges (specimen-specific)
    if patho_result.get("abu_detected"):
        st.info("🔵 **Asymptomatic Bacteriuria (ABU) Detected** -- راجع IDSA 2019")
    if "PEDIATRIC_UTI" in flags:
        st.info("👶 **Pediatric threshold applied** (Age < 2 yrs -- AAP: pyuria + ≥ 5×10⁴ CFU/mL; "
                "any count only for suprapubic aspirate)")
    if "SCI" in flags:
        st.info("♿ **Spinal cord injury context applied** -- neurogenic bladder / pressure ulcer / "
                "impaired cough rules")
    if "UNSPECIATED_ORGANISM" in flags:
        st.info("🔬 **Organism not identified to species level** -- التقييم على مستوى الجنس/الصبغة")
    if "GRAM_VARIABLE" in flags:
        st.info("🔬 **Gram-variable stain** -- راجع الملاحظة أسفل")
    if "GRAM_DISCORDANT" in flags:
        st.warning("🔬 **Gram stain / culture discordance** -- الصبغة لا تطابق العزلة")
    if "MW_REJECT" in flags:
        st.warning("🧪 **Specimen quality: REJECT** -- Murray-Washington (saliva contamination). أعِد العينة.")
    if "MW_ADEQUATE" in flags:
        st.success("🧪 **Specimen quality: Adequate** -- Murray-Washington (WBC≥25, Epi<10/LPF).")
    if "SIRS_HIGH" in flags:
        st.error("🌡️ **SIRS ≥3 criteria -- Sepsis probable**")
    if "CSF_ALWAYS_SIGNIFICANT" in flags:
        st.error("🧠 **Sterile site (CSF) -- growth of this organism is clinically significant**")
    if "CSF_SKIN_FLORA" in flags:
        st.warning("🧠 **CSF skin flora without a device** -- possible contaminant; correlate with CSF cells")
    if "GI_TRUE_PATHOGEN" in flags:
        st.error("🦠 **Enteric pathogen -- always significant**")
    if "BLOOD_CONTAMINANT_RISK" in flags and "MULTI_SET_SKIN_FLORA" not in flags:
        st.warning("🩸 **Possible blood-culture contaminant (CoNS / skin flora)** -- يتطلب نفس الكائن في ≥2 sets.")
    if "BLOOD_PENDING_ID" in flags:
        st.warning("🩸 **Identification pending** -- لا تعتبره ملوِّثاً قبل نفي S. aureus.")

    st.info(patho_result["interpretation"])

    col_pos, col_neg = st.columns(2)
    with col_pos:
        if patho_result["factors_pos"]:
            st.markdown("**✅ Supporting Factors**")
            for f in patho_result["factors_pos"]:
                st.write(f)
    with col_neg:
        if patho_result["factors_neg"]:
            st.markdown("**⚠️ Against Infection**")
            for f in patho_result["factors_neg"]:
                st.write(f)

    if patho_result.get("notes"):
        st.markdown("**🧭 ملاحظات تفسيرية:**")
        for _n in patho_result["notes"]:
            st.write(_n)

    st.markdown("**📋 التوصيات:**")
    for rec in patho_result["recommendations"]:
        st.write(f"• {rec}")

    if patho_result.get("references"):
        st.caption("المراجع: " + " · ".join(patho_result["references"]))

    # ── PDF of this assessment only (2026-11-11) ───────────────────────────
    st.divider()
    _ctx = st.session_state.get("patho_pdf_ctx") or {}
    _pl = st.radio("لغة ملف الـ PDF", ["العربية", "English"], horizontal=True,
                   key=f"patho_pdf_lang_{_ctx.get('panel', 'x')}")
    if WEASYPRINT_AVAILABLE:
        _pp = generate_patho_report_pdf(
            patho_result, _ctx.get("organism", ""), _ctx.get("specimen", ""),
            inputs=_ctx.get("inputs"),
            patient_ref=(st.session_state.get("patient_name_final", "")
                         or st.session_state.get("patient_name_ocr", "") or ""),
            lang="en" if _pl == "English" else "ar")
        if _pp:
            st.download_button(
                "⬇️ Download Pathogenicity Assessment (PDF)", data=_pp,
                file_name=f"Pathogenicity-{datetime.now().strftime('%Y%m%d-%H%M')}.pdf",
                mime="application/pdf", key=f"patho_pdf_dl_{_ctx.get('panel', 'x')}")
        else:
            st.caption("⚠️ تعذر إنشاء PDF لتقييم الـ Pathogenicity.")
    else:
        st.caption("⚠️ WeasyPrint غير متاح في هذه البيئة — لا يمكن إنشاء PDF.")


# =========================================================
# أدوات رسم الصورة
# =========================================================
def _score_color(score: int) -> str:
    if score >= 75: return "#922b21"
    if score >= 50: return "#b7770d"
    if score >= 30: return "#e67e22"
    return "#1e8449"


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))

def _md_inline(text: str) -> str:
    """Escape HTML, then render the tiny markdown subset the QC messages use:
    **bold** -> <b>, markdown line breaks -> <br>. Used for AST-QA issues whose
    text comes from the reportability / consistency modules."""
    import re as _re
    out = _esc(text)
    out = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = out.replace("  \n", "<br>").replace("\n", "<br>")
    return out


# ══════════════════════════════════════════════════════════════════════════
# PDF GLYPH GUARD
# ══════════════════════════════════════════════════════════════════════════
# The deployment image (see packages.txt) ships Liberation Sans, Amiri and
# DejaVu Sans. None of them carry emoji. Any emoji reaching WeasyPrint is
# therefore drawn as a .notdef tofu box -- which is what produced the
# "[] Orange Lab" / "[] E. coli" / "[] (R)" boxes in the shipped advisory.
#
# Every replacement below was verified present in DejaVu Sans, so it renders
# as real vector outline: crisp at any zoom, unlike a bitmap emoji font.
_PDF_GLYPH_MAP = {
    # --- status / verdict ------------------------------------------------
    "\u2705":     "\u2713",   # white heavy check   -> check mark
    "\u274C":     "\u2717",   # cross mark          -> ballot X
    "\u2795":     "+",        # heavy plus          -> plus
    "\u2796":     "\u2212",   # heavy minus         -> minus sign
    "\u2757":     "\u26A0",   # exclamation         -> warning sign
    "\u2696":     "\u25C6",   # balance scale       -> black diamond
    "\u2753":     "?",        # question            -> question mark
    # --- prohibition ----------------------------------------------------
    "\U0001F6AB": "\u2298",   # no entry sign       -> circled slash
    "\u26D4":     "\u2298",   # no entry            -> circled slash
    "\U0001F6D1": "\u2298",   # stop sign           -> circled slash
    # --- lab / clinical -------------------------------------------------
    "\U0001F52C": "\u25C6",   # microscope          -> black diamond
    "\U0001F9A0": "\u25CF",   # microbe             -> black circle
    "\U0001F9EB": "\u25C6",   # petri dish          -> black diamond
    "\U0001F48A": "\u2295",   # pill                -> circled plus
    "\U0001F930": "\u26A0",   # pregnant woman      -> warning sign
    "\U0001F489": "",         # syringe             -> drop (decorative)
    "\U0001F3E5": "",         # hospital            -> drop
    "\U0001F3AF": "",         # dart                -> drop
    # --- documents ------------------------------------------------------
    "\U0001F4CB": "\u25A3",   # clipboard           -> framed square
    "\U0001F4DA": "\u00A7",   # books               -> section sign
    "\U0001F4D6": "\u00A7",   # open book           -> section sign
    "\U0001F4C4": "\u25A3",   # page                -> framed square
    # --- alerts ---------------------------------------------------------
    "\U0001F6A8": "\u25B2",   # siren               -> black up triangle
    "\U0001F504": "\u21BB",   # cycle arrows        -> clockwise arrow
    # --- colour-coded status dots ---------------------------------------
    # NOTE: colour is LOST here. These should be CSS-coloured spans at
    # source, not emoji -- see PDF_RENDER_AUDIT.md, finding F9.
    "\U0001F534": "\u25CF",   # red circle
    "\U0001F7E2": "\u25CF",   # green circle
    "\U0001F7E1": "\u25CF",   # yellow circle
    "\U0001F7E0": "\u25CF",   # orange circle
    "\U0001F535": "\u25CF",   # blue circle
    "\U0001F536": "\u25C6",   # large orange diamond
    "\U0001F539": "\u25C6",   # small blue diamond
    "\U0001F7E3": "\u25CF",   # purple circle
}

# Symbols confirmed present in DejaVu Sans -- must survive the sweep below.
_PDF_SAFE_SYMBOLS = frozenset(
    "\u2713\u2717\u2298\u25C6\u25CF\u25CB\u25A3\u25AA\u25B2\u21BB"
    "\u26A0\u2295\u00A7\u2022\u2192\u2264\u2265\u2261\u00B7\u2014\u2013"
)


def pdf_glyph_guard(html: str) -> str:
    """Make `html` renderable by the fonts actually installed.

    1. Maps known emoji to DejaVu-backed vector equivalents.
    2. Drops anything still in an emoji range -- no installed font can draw
       it, so leaving it in guarantees a tofu box. Dropping is strictly
       better than shipping a box into a clinical document.
    3. Strips VS-15/VS-16 selectors, which tofu on their own.
    """
    out = []
    for ch in html:
        if ch in _PDF_SAFE_SYMBOLS:
            out.append(ch)
            continue
        mapped = _PDF_GLYPH_MAP.get(ch)
        if mapped is not None:
            out.append(mapped)
            continue
        o = ord(ch)
        if (0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF
                or 0x2B00 <= o <= 0x2BFF or o in (0xFE0E, 0xFE0F)
                or 0x1F1E6 <= o <= 0x1F1FF):
            continue
        out.append(ch)
    return "".join(out)


# ── Report rendering moved to report_service.py (2026-08-03) ───────────────
# 1,852 lines of presentation — the PDF, the decision-tree PNG and the text
# report — extracted from this file. They decide nothing; they render what
# run_analysis() already decided. The dependency is injected by bind() rather
# than imported, because these renderers need thirty-seven names from here and
# a plain import would be circular. Re-exported so every existing caller and
# every AST-extraction harness still finds them by name.
import report_service as _RS                                        # noqa: E402
_RS.bind(
    ABX_GUIDELINES=ABX_GUIDELINES, ORGANISM_PROFILE=ORGANISM_PROFILE,
    MDR_INFO=MDR_INFO, INFECTION_SYNDROMES=INFECTION_SYNDROMES,
    RENAL_BAN_REASONS=RENAL_BAN_REASONS, ARABIC_SUPPORT=ARABIC_SUPPORT,
    PIL_AVAILABLE=PIL_AVAILABLE, WEASYPRINT_AVAILABLE=WEASYPRINT_AVAILABLE,
    _arabic_reshaper_mod=_arabic_reshaper_mod, _wp=_wp,
    Image=Image, ImageDraw=ImageDraw, ImageFont=ImageFont,
    classify_mdr=classify_mdr, predict_esbl=predict_esbl,
    rank_sensitive_antibiotics=rank_sensitive_antibiotics,
    crcl_label=crcl_label, resolve_crcl=resolve_crcl,
    preg_status_of=preg_status_of, get_renal_severity=get_renal_severity,
    _drop_intrinsic=_drop_intrinsic, _hide_urine_only=_hide_urine_only,
    _esc=_esc, _score_color=_score_color,
    annotate_regimen_note=annotate_regimen_note,
    get_commercial_name=get_commercial_name, pdf_glyph_guard=pdf_glyph_guard,
    normalize_abx_key=normalize_abx_key, warned_note_for=warned_note_for,
)
generate_pdf_html_report     = _RS.generate_pdf_html_report
generate_decision_tree_image = _RS.generate_decision_tree_image
generate_report              = _RS.generate_report







# =========================================================
# واجهة التطبيق الرئيسية
# =========================================================
if not st.session_state.authenticated:
    _login = show_login_page()
    if _login:
        email_input, password_input = _login
        if check_subscription(email_input, password_input):
            st.session_state.authenticated = True
            st.session_state.last_activity = time.time()
            st.rerun()
    st.stop()

handle_session_timeout()
render_top_bar()

# ── Module health, shown before anything else ────────────────────────────────
#  A missing clinical_data.py silently disables intrinsic-resistance filtering:
#  inactive agents stop being routed to Avoid and stop being stripped before MDR
#  counting. That is a degraded clinical mode, and it used to be reported only
#  inside a COLLAPSED expander among ordinary data notes -- so the app could run
#  for months giving weaker advice with nobody noticing. Anything that changes
#  what the engine is capable of is now surfaced at the top, unmissable.
_MODULE_HEALTH = [
    ("clinical_data.py  (intrinsic resistance table)", INTRINSIC_TABLE_OK, True),
    (f"safety_gate + clinical_matrix  (site/host safety map v{MATRIX_VERSION})",
     SAFETY_GATE_AVAILABLE, True),
    ("ast_reportability + ast_consistency  (QC panel)", AST_RULES_MODULES_AVAILABLE, False),
    ("ast_qa_engine.py  (AST quality check)", AST_QA_AVAILABLE, False),
    ("ast_panel_completeness.py  (Panel Completeness card)", PANEL_COMPLETENESS_AVAILABLE, False),
    ("Arabic shaping  (arabic-reshaper + python-bidi)", ARABIC_SUPPORT, False),
]
_degraded = [(n, crit) for n, ok, crit in _MODULE_HEALTH if not ok]
if any(crit for _, crit in _degraded):
    st.error(
        "🛑 **DEGRADED CLINICAL MODE — do not use for reporting.**  \n"
        + "  \n".join(f"❌ `{n}` is missing." for n, crit in _degraded if crit)
        + "  \n\nIntrinsically inactive antibiotics will NOT be filtered out of the "
          "recommendations and will NOT be excluded from MDR counting. "
          "Upload the missing file next to `streamlit_app.py` and restart."
    )
elif _degraded:
    st.warning("⚠️ Optional modules unavailable: "
               + ", ".join(f"`{n}`" for n, _ in _degraded)
               + ". Core recommendations are unaffected.")

startup_issues = get_startup_validation_issues()
if startup_issues:
    with st.expander(f"🧪 Data validation at startup ({len(startup_issues)})",
                     expanded=False):
        for issue in startup_issues:
            st.write(f"- {issue}")

with st.expander("🧩 Module health", expanded=False):
    for _n, _ok, _crit in _MODULE_HEALTH:
        st.write(f"{'✅' if _ok else ('❌' if _crit else '⚠️')} {_n}")

st.title("🔬 Microbiology CDSS")
st.caption("AI-Assisted Antibiotic Decision Support -- Egyptian Market Edition")

if os.environ.get("ORANGE_CDSS_OFFLINE_MODE") == "1":
    # Set by launcher.py only when actually running as the frozen desktop
    # exe (never in the cloud-deployed version) -- reassurance that this
    # build works with no internet connection, not a claim about what the
    # cloud-deployed version does.
    st.caption(
        "🟢 **Offline** — Clinical Engine: Local · AST QC: Local · "
        "OCR: Local · Guidelines: Local copy — no internet connection required"
    )

# ── إعدادات المعمل -- قابلة للتغيير (النسخة التجارية) ─────────────────────
# الأولوية: secrets (للنشر) -> session_state (تغيير مباشر) -> default
#
# 2026-08-22: hasattr(st, "secrets") only proves the ATTRIBUTE exists -- it
# is always True, since `secrets` is a normal attribute of the streamlit
# module regardless of whether a secrets.toml file is present anywhere.
# Accessing it (even via .get()) is what can fail: if NO secrets.toml exists
# at all (not even an empty one -- exactly the case in CI, where none is
# ever committed), Streamlit raises StreamlitSecretNotFoundError. That is
# not a KeyError, so .get()'s own internal exception handling does not catch
# it -- every OTHER st.secrets call site in this file already wraps the
# access in `try/except Exception`; this was the one bare call left, and it
# crashed app startup the moment real streamlit (installed for the Windows
# EXE build's test step) actually tried to import this file with no
# secrets.toml deployed.
try:
    _lab_from_secrets = bool(st.secrets.get("lab_name", ""))
except Exception:
    _lab_from_secrets = False

if _lab_from_secrets:
    # Deployed lab: name fixed via Streamlit secrets (no UI override needed)
    st.session_state.lab_name = st.secrets.get("lab_name", "Your Lab Name")
    st.session_state.lab_city = st.secrets.get("lab_city", "")
else:
    # Commercial / demo mode: allow UI-based name change
    with st.expander("🏥 إعدادات المعمل", expanded=False):
        _c1, _c2 = st.columns([3, 2])
        with _c1:
            _lab_input = st.text_input(
                "اسم المعمل",
                value=st.session_state.get("lab_name", "Your Lab Name"),
                placeholder="مثال: Nile Diagnostic Center",
                key="lab_name_input_commercial",
            )
            if _lab_input.strip():
                st.session_state.lab_name = _lab_input.strip()
        with _c2:
            _city_input = st.text_input(
                "المدينة / العنوان (اختياري)",
                value=st.session_state.get("lab_city", ""),
                placeholder="مثال: Cairo",
                key="lab_city_input_commercial",
            )
            st.session_state.lab_city = _city_input.strip()
        # Live preview
        _prev = st.session_state.lab_name
        if st.session_state.lab_city:
            _prev += f"  |  {st.session_state.lab_city}"
        st.caption(f"🔬 **معاينة الترويسة:** {_prev}")
        st.caption("ℹ️ هذا الاسم سيظهر في الصورة وتقرير PDF والتقرير النصي تلقائياً.")



uploaded = st.file_uploader(
    "📷 Upload Culture Report Image",
    type=["jpg", "jpeg", "png"]
)

if uploaded:
    file_bytes = uploaded.getvalue()
    file_hash  = make_file_hash(file_bytes)
    is_new     = (st.session_state.ocr_data is None or
                  st.session_state.last_file_hash != file_hash)

    if is_new:
        # Clean up old session keys when loading a new image
        old_hash = st.session_state.get("last_file_hash", "")
        if old_hash and old_hash != file_hash:
            keys_to_delete = [k for k in st.session_state if old_hash[:8] in str(k)]
            for key in keys_to_delete:
                del st.session_state[key]
            # A different report = a different patient (round 4, 2026-11-11).
            reset_patient_state()

        with st.spinner("🔍 جاري تحليل صورة التقرير..."):
            try:
                payload = extract_all_data_cached(file_bytes)
                st.session_state.ocr_data           = payload
                st.session_state.last_file_hash     = file_hash
                st.session_state.sir_map_edited     = dict(payload["sir_map"])
                # الاسم يُدخل يدوياً -- لا نغير ما أدخله المستخدم عند تحميل صورة جديدة
                st.session_state.patient_name_ocr   = ""
                # patient_name_final محفوظ من الجلسة السابقة (لا نمسحه)
            except Exception as e:
                st.error(f"تعذر تحليل الصورة: {e}")
                st.stop()

    payload        = st.session_state.ocr_data
    patient        = payload["patient"]
    drugs_from_ocr = payload["drugs"]
    raw_text       = payload["raw_text"]

    if not st.session_state.sir_map_edited and payload["sir_map"]:
        st.session_state.sir_map_edited = dict(payload["sir_map"])

    st.image(file_bytes, caption="Preview", use_container_width=True)

    with st.expander("📝 النص المستخرج من التقرير (OCR)", expanded=False):
        st.text_area("Extracted Text", raw_text, height=220, label_visibility="collapsed")

    col1, col2 = st.columns([1.05, 1.55], gap="large")

    # ─── العمود الأيسر ────────────────────────────────────────────────────────
    with col1:
        st.subheader("👤 Patient & Culture")

        # اسم المريض -- إدخال يدوي فقط
        patient_name = st.text_input(
            "👤 اسم المريض / Patient Name",
            value=st.session_state.get("patient_name_final", ""),
            placeholder="أدخل اسم المريض",
            help="يظهر في التقرير وصورة الملخص.",
            key=f"pname_{file_hash[:8]}"
        )
        st.session_state.patient_name_final = patient_name.strip()

        # Round 5 (2026-11-12): specimen, organism, age, months, sex and weight
        # had NO key, so Streamlit identified them by their parameters. When
        # the next report's OCR produced the same default (e.g. age unread ->
        # 25 both times, or the same organism), the widget was "the same
        # widget" and kept the PREVIOUS patient's manually entered value --
        # a child analysed at the last adult's age. Keyed per file like the
        # round-4 widgets, so a new report always starts from its own OCR.
        _fh = file_hash[:8]
        culture_type = st.selectbox(
            "🧫 Specimen",
            SPECIMEN_TYPES,
            index=best_default_index(SPECIMEN_TYPES, patient.get("Specimen")),
            key=f"specimen_sel_{_fh}",
        )

        filtered_organisms = [
            org for org in get_organisms_for_specimen(culture_type)
            if org in ORGANISM_PROFILE
        ]
        if not filtered_organisms:
            filtered_organisms = BACTERIA_TYPES

        organism_type = st.selectbox(
            "🦠 Organism",
            filtered_organisms,
            index=best_default_index(filtered_organisms, patient.get("Organism")),
            help=f"بكتيريا شائعة في عينة {culture_type}",
            key=f"organism_sel_{_fh}_{culture_type}",
        )

        # ── Atypical organisms: NOT recovered on routine culture, NO disc AST ──
        # Legionella / Mycoplasma / Rickettsia are diagnosed by PCR / serology /
        # urine antigen — any S/I/R entered for them is not meaningful. Surface
        # empiric therapy from the profile and tell the user to ignore the AST panel.
        _ATYPICAL_NO_AST = {"Legionella pneumophila", "Mycoplasma spp."}
        if organism_type in _ATYPICAL_NO_AST:
            _emp = _drop_intrinsic(
                (ORGANISM_PROFILE.get(organism_type) or {}).get("first_line", []),
                organism_type)
            _emp_txt = "، ".join(_emp) if _emp else "—"
            st.warning(
                f"⚠️ **{organism_type}** لا يُزرع بالمزرعة الروتينية ولا يوجد له اختبار "
                f"حساسية (AST) بالأقراص — يُشخَّص بـ PCR / Serology / Urine Antigen.\n\n"
                f"**العلاج تجريبي (Empiric):** {_emp_txt}.\n\n"
                f"تجاهل أي نتائج S/I/R بالأسفل — غير ذات دلالة لهذا الكائن."
            )

        # ── حقول المزرعة والمجهر ──────────────────────────────────────────────
        st.divider()
        st.subheader("🔬 Culture & Microscopic Details")

        # Colony count is a urine-only concept — showing/carrying it into a
        # blood/sputum/CSF report is clinically wrong. Only render it for urine;
        # for other specimens send nothing downstream (stored value is preserved
        # so switching back to Urine restores it).
        if "urine" in (culture_type or "").lower():
            colony_count = st.text_input(
                "Colony Count (CFU/mL)",
                value=st.session_state.colony_count,
                placeholder="≥ 10^5 CFU/mL",
                key="colony_count_input"
            )
            st.session_state.colony_count = colony_count
        else:
            colony_count = ""

        date_in = st.date_input(
            "📅 Date In (تاريخ استلام العينة)",
            value=st.session_state.date_in,
            key="date_in_input"
        )
        st.session_state.date_in = date_in

        # ── Auto-populate Pus/RBCs/Condition from OCR -- only ONCE per file ────
        _ocr_done_key = f"_ocr_filled_{file_hash[:12]}"
        if payload and not st.session_state.get(_ocr_done_key, False):
            _ocr_pus = payload.get("pus_cells", "")
            _ocr_rbc = payload.get("rbcs", "")
            _ocr_cnd = payload.get("condition", "")
            _filled  = []
            if _ocr_pus and not st.session_state.get("pus_cells_text",""):
                st.session_state.pus_cells_text = _ocr_pus
                _filled.append(f"Pus: {_ocr_pus}/HPF")
            if _ocr_rbc and not st.session_state.get("rbcs_text",""):
                st.session_state.rbcs_text = _ocr_rbc
                _filled.append(f"RBCs: {_ocr_rbc}/HPF")
            if _ocr_cnd and st.session_state.get("culture_condition","Aerobic") == "Aerobic":
                st.session_state.culture_condition = _ocr_cnd
                _filled.append(f"Condition: {_ocr_cnd}")
            if _filled:
                st.toast("🔍 OCR auto-filled: " + " | ".join(_filled), icon="🔬")
            st.session_state[_ocr_done_key] = True  # never fire again for this file

        c_pus, c_rbc = st.columns(2)
        with c_pus:
            pus_cells_text = st.text_input(
                "Pus Cells (/HPF)",
                value=st.session_state.pus_cells_text,
                placeholder="مثال: 4 - 6",
                key="pus_cells_input"
            )
            st.session_state.pus_cells_text = pus_cells_text
        with c_rbc:
            rbcs_text = st.text_input(
                "RBC Cells (/HPF)",
                value=st.session_state.rbcs_text,
                placeholder="مثال: 2 - 4",
                key="rbcs_input"
            )
            st.session_state.rbcs_text = rbcs_text

        # Organism guidance
        if organism_type in ORGANISM_PROFILE:
            op = ORGANISM_PROFILE[organism_type]
            with st.expander("📌 Organism Guidance", expanded=True):
                st.info(op.get("note", ""))
                spec_ctx = (op.get("specimen_context") or {}).get(culture_type, "")
                if spec_ctx:
                    st.warning(f"**{culture_type} Context:** {spec_ctx}")
                _t_first_line = _drop_intrinsic(
                    _hide_urine_only(op.get("first_line"), culture_type), organism_type)
                if _t_first_line:
                    st.write("**First-line:**", ", ".join(_t_first_line))
                _t_second_line = _drop_intrinsic(
                    _hide_urine_only(op.get("second_line"), culture_type), organism_type)
                if _t_second_line:
                    st.write("**Second-line:**", ", ".join(_t_second_line))
                _t_third_line = _drop_intrinsic(
                    _hide_urine_only(op.get("third_line"), culture_type), organism_type)
                if _t_third_line:
                    st.write("**Third-line:**", ", ".join(_t_third_line))
                if op.get("avoid"):
                    st.error("**Avoid:** " + ", ".join(op["avoid"]))
                if culture_type == "Urine" and op.get("urine_note"):
                    st.info(f"📌 Urine notes:\n{op['urine_note']}")

        st.divider()

        # Infants are common in every culture type, and a plain "Age (years)"
        # field forces them to 0 -- which reads as "0 yrs" on the report and
        # seeds a wrong weight. Offer months instead; the clinical engines still
        # receive age=0 (years), so all existing pediatric logic is unchanged.
        _ocr_months = patient.get("AgeMonths")
        _ocr_under_1 = (_ocr_months is not None
                        or safe_int(patient.get("Age"), 25) == 0)
        # Round 5: an age the OCR could not read used to become "25 years"
        # with nothing on screen saying it was a guess, and "Age: 3 M" (three
        # months, or 3 years / Male?) was read as years. Both now ask.
        if patient.get("Age") is None:
            st.warning("⚠️ العمر لم يُقرأ من التقرير — القيمة 25 سنة افتراضية وليست عمر "
                       "المريض. أدخل العمر الصحيح: حظر أدوية الأطفال والرضّع يعتمد عليه.")
        elif patient.get("AgeAmbiguous"):
            st.warning(f"⚠️ العمر مكتوب «{patient.get('Age')} M» — قد يعني شهوراً أو "
                       "(سنوات + Male). قُرئ كسنوات؛ لو المريض رضيع علّم «أقل من سنة» "
                       "وأدخل الشهور.")
        _under_1 = st.checkbox("👶 أقل من سنة (< 1 year)", value=bool(_ocr_under_1),
                               key=f"under1_{_fh}")
        if _under_1:
            age_months = st.number_input(
                "Age (months)", min_value=0, max_value=11,
                value=safe_int(_ocr_months, 6), step=1, key=f"age_months_{_fh}")
            age = 0
            st.caption(f"👶 رضيع {age_months} شهر -- يُقيَّم إكلينيكياً كعمر 0 "
                       f"(Infant < 1 yr: أي عدد مستعمرات ذو دلالة).")
        else:
            age_months = None
            age = st.number_input("Age (years)", min_value=0, max_value=120,
                                   value=safe_int(patient.get("Age"), 25),
                                   key=f"age_years_{_fh}")
        default_sex = patient.get("Sex") if patient.get("Sex") in ["Female", "Male"] else "Male"
        sex    = st.selectbox("Gender", ["Female", "Male"],
                              index=0 if default_sex == "Female" else 1,
                              key=f"sex_sel_{_fh}")
        # Age-appropriate default (APLS estimate) so pediatric CrCl/dosing isn't
        # seeded with an adult 70 kg. Still fully editable.
        # Infants use the WHO/APLS infant rule: kg ≈ (months + 9) / 2.
        _wt_default = (
            max(1, round((age_months + 9) / 2)) if age_months is not None
            else 8 if age < 1
            else int(2 * (age + 4)) if age <= 5
            else int(3 * age + 7) if age <= 12
            else 70
        )
        # A neonate is ~3.5 kg, so the adult-oriented 5 kg floor has to drop for
        # infants or the correct weight simply cannot be entered.
        _wt_min = 1 if age_months is not None else 5
        # The key carries the age so the age-appropriate default is re-seeded
        # when the age changes (a keyed widget keeps its value otherwise).
        weight = st.number_input("Weight (kg)", min_value=_wt_min, max_value=300,
                                 value=_wt_default,
                                 key=f"weight_{_fh}_{age}_{age_months}")

        st.divider()

        # Patient-fact widgets are keyed PER FILE (round 4, 2026-11-11): a new
        # report recreates them empty instead of inheriting the last patient's
        # flags. The old keys carry the old hash and are deleted on upload.
        # (_fh is defined above, with the specimen widget.)
        _renal_flag = st.checkbox("🚩 Renal Impairment", key=f"renal_flag_{_fh}")
        # Always offered, not hidden behind the checkbox: a reduced clearance that
        # nobody thought to flag is exactly the case that needs catching.
        s_cr = st.number_input(
            "Serum Creatinine (mg/dL) — leave 0 if not available",
            min_value=0.0, max_value=20.0, value=0.0, step=0.1,
            key=f"scr_{_fh}",
            help="If entered, CrCl is calculated (Cockcroft-Gault for adults, "
                 "bedside Schwartz for under-18s) and a value below 60 ml/min "
                 "engages renal dosing on its own.")
        # Children: Cockcroft-Gault is validated in adults only. Fed an infant's
        # weight and creatinine it reports a healthy neonate (3.5 kg, SCr 0.5)
        # as ~14 ml/min -- kidney failure -- which refused gentamicin (the
        # standard neonatal sepsis partner) and cut the dose of everything
        # renally cleared. Under 18 the bedside Schwartz equation is used, and
        # it needs the height (round 4, 2026-11-11).
        _height = 0.0
        if age < 18 and s_cr > 0:
            _height = st.number_input(
                "Height (cm) — needed for paediatric eGFR (Schwartz)",
                min_value=0.0, max_value=200.0, value=0.0, step=1.0,
                key=f"height_{_fh}")
        # cl_cr is None when nothing was measured. It used to be set to 100.0,
        # which is a NORMAL clearance, so ticking the impairment box without a
        # creatinine produced exactly the same recommendations as a patient with
        # healthy kidneys: no dose-adjustment note on any agent (no renal_limit
        # reaches 100) and Nitrofurantoin recommended rather than refused.
        cl_cr = None
        if s_cr > 0 and age >= 18:
            cl_cr = calc_creatinine_clearance(age, weight, s_cr, sex)
            st.metric("CrCl (Cockcroft-Gault)", f"{cl_cr:.1f} ml/min",
                      delta=get_renal_severity(cl_cr),
                      delta_color="normal" if cl_cr >= 60 else ("off" if cl_cr >= 30 else "inverse"))
        elif s_cr > 0:
            cl_cr = calc_paediatric_egfr(_height, s_cr, age, age_months)
            if cl_cr is None:
                st.warning("⚠️ Cockcroft-Gault غير صالح تحت 18 سنة — أدخل الطول لحساب "
                           "eGFR بمعادلة Schwartz. لم تُحسب وظيفة الكلى من الكرياتينين.")
            else:
                st.metric("eGFR (bedside Schwartz)", f"{cl_cr:.1f} ml/min/1.73m²",
                          delta=get_renal_severity(cl_cr),
                          delta_color="normal" if cl_cr >= 60 else ("off" if cl_cr >= 30 else "inverse"))
        # Under two years a GFR below 60 is physiological (it matures over the
        # first two years), so it must not switch adult renal dosing on by
        # itself; the value is used only if the clinician flags impairment.
        if cl_cr is not None and age < 2 and not _renal_flag:
            st.caption("ℹ️ GFR الطبيعي أقل من البالغين في أول سنتين — لم يُفعَّل تعديل الجرعة "
                       "الكلوي تلقائياً. علّم Renal Impairment إن كان هناك قصور فعلي.")
            cl_cr = None
        # Engage renal handling if EITHER the clinician flagged it OR the measured
        # clearance is impaired.
        is_renal = bool(_renal_flag) or (cl_cr is not None and cl_cr < 60)
        if is_renal and cl_cr is None:
            st.warning(
                f"⚠️ Renal impairment flagged with no creatinine. Dosing will "
                f"assume **CrCl ≈ {ASSUMED_CRCL_UNKNOWN:.0f} ml/min** (the "
                f"conservative direction) and every renal note will say so. "
                f"Enter the creatinine for patient-specific doses.")
        elif is_renal and not _renal_flag:
            st.warning(f"⚠️ CrCl {cl_cr:.0f} ml/min — renal dose adjustment applied "
                       "automatically (the impairment box was not ticked).")

        is_hepatic = st.checkbox("🚩 Hepatic Impairment", key=f"hepatic_{_fh}")
        # ── Child-Pugh is captured HERE, next to the flag that needs it ────────
        # It used to be asked for inside an expander further down the page, which
        # in Streamlit's top-to-bottom execution runs AFTER analyze_antibiotics().
        # So on the run where the clinician ticked hepatic impairment the engine
        # was still evaluating the seeded grade, and the hepatic contraindications
        # never fired on the screen that mattered. Asking here removes the
        # ordering dependency permanently rather than papering over it.
        if is_hepatic:
            child_pugh_class = st.selectbox(
                "Child-Pugh Class", ["C", "B", "A"],
                index=["C", "B", "A"].index(
                    st.session_state.get("child_pugh_class", "C")),
                format_func=lambda x: {"A": "A — Mild (5-6 pts)",
                                       "B": "B — Moderate (7-9 pts)",
                                       "C": "C — Severe (10-15 pts)"}[x],
                key=f"cp_sel_sidebar_{_fh}",
                help="Starts at C (most conservative) until graded. Grade the "
                     "patient — C refuses agents that are acceptable in A.")
            st.session_state.child_pugh_class = child_pugh_class
            if child_pugh_class == "C":
                st.caption("⚠️ Assuming Child-Pugh C until graded.")
        is_preg    = False
        if sex == "Female":
            is_preg = st.checkbox(
                "🤰 Patient is Pregnant", key=f"preg_{_fh}",
                help="Shown for every female patient. The age window used to hide "
                     "this control entirely, which made the pregnancy safety rules "
                     "unreachable outside 15-55 rather than merely unticked.")

        current_meds = st.multiselect("💊 Current Medications", COMMON_MEDS, key=f"meds_{_fh}")

        # ─── Added 2026-11-10 (guideline review) ─────────────────────────────
        # Three facts the engine could not know, and which change the answer:
        # the allergy (Patient.allergies existed and nothing filled it), the
        # carbapenemase CLASS (decides between the novel agents, IDSA 2026),
        # and whether a urine isolate is cystitis or pyelonephritis.
        allergies = st.multiselect(
            "🚫 Drug allergies",
            ["Penicillin — mild / delayed rash", "Penicillin — severe / anaphylaxis",
             "Cephalosporin", "Ceftazidime", "Sulfonamide (sulfa)",
             "Fluoroquinolone", "Macrolide"],
            key=f"allergies_input_{_fh}",
            help="الحساسية المسجّلة تحظر الصنف نفسه، وتضيف تحذير تفاعل متصالب للأصناف القريبة.")
        carbapenemase_choice = st.selectbox(
            "🧬 Carbapenemase type (if tested)", list(CARBAPENEMASE_TYPE_OPTIONS),
            key=f"carb_type_input_{_fh}",
            help="من NG-Test CARBA-5 أو Xpert Carba-R أو PCR. يحدد أي عامل حديث يعمل "
                 "(KPC / OXA-48 / MBL) — IDSA AMR Guidance 2026.")
        uti_syndrome_choice = st.selectbox(
            "🫘 UTI syndrome (urine only)", list(UTI_SYNDROME_OPTIONS),
            key=f"uti_syndrome_input_{_fh}",
            help="تلقائي: حمى أو ألم الخاصرة ← التهاب حويضة/cUTI. Nitrofurantoin و Fosfomycin "
                 "الفموي و Norfloxacin لا تصلح للحويضة.")

        # ─── New clinical/lab fields ──────────────────────────────────────────
        with st.expander("🏥 Lab Report Fields", expanded=False):
            _ref_phys = st.text_input(
                "Referred by (Physician Name)",
                value=st.session_state.get("referring_physician",""),
                placeholder="Dr. Ahmed Mohamed",
                key="ref_phys_input"
            )
            st.session_state.referring_physician = _ref_phys

            _culture_cond = st.selectbox(
                "Culture Condition",
                ["Aerobic", "Anaerobic", "Both (Aerobic + Anaerobic)"],
                index=["Aerobic","Anaerobic","Both (Aerobic + Anaerobic)"].index(
                    st.session_state.get("culture_condition","Aerobic")
                ),
                key="culture_cond_sel"
            )
            st.session_state.culture_condition = _culture_cond

            _micro_name = st.text_input(
                "Microbiologist Name",
                value=st.session_state.get("microbiologist",""),
                placeholder="Dr. Aya Gamal",
                key="micro_name_input"
            )
            st.session_state.microbiologist = _micro_name

        # ── Pathogenicity Assessment Module v2 ───────────────────────────────
        # ⚠️ التعديل: Pathogenicity Assessment يظهر للبول فقط.
        #    لباقي المزارع يظهر بدلاً منه: Resistance Profile (ESBL / MDR / XDR / PDR).
        _is_urine_specimen = "urine" in culture_type.lower()

        # Clear stale patho_result when specimen changes
        if st.session_state.get("last_patho_specimen","") != culture_type:
            st.session_state.patho_result = None
            st.session_state.last_patho_specimen = culture_type
            # Reset specimen-specific symptoms to avoid stale defaults
            st.session_state.patho_symptoms = []
            st.session_state.patho_sirs = []
            st.session_state.patho_blood_source = ""
            st.session_state.patho_wound_type = ""

        st.divider()

        # ═══════════════════════════════════════════════════════════════════════
        # الفرع (أ): Pathogenicity Assessment -- للبول فقط
        # ═══════════════════════════════════════════════════════════════════════
        if _is_urine_specimen:
            with st.expander("🧫 Pathogenicity Assessment", expanded=False):
                st.caption("هل العينة تمثل عدوى حقيقية أم تلوث؟ -- خاص بمزارع البول")

                pa_col1, pa_col2 = st.columns(2)
                with pa_col1:
                    patho_purity = st.selectbox(
                        "نقاء المزرعة",
                        ["Pure growth", "Mixed growth"],
                        index=0 if st.session_state.patho_culture_purity == "Pure growth" else 1,
                        key="patho_purity_sel"
                    )
                    st.session_state.patho_culture_purity = patho_purity

                    patho_gram = st.selectbox(
                        "Gram Stain",
                        gram_options_for(organism_type),
                        key="patho_gram_sel",
                        help="Gram-variable = نتيجة صبغة وليست نوع بكتيريا: Acinetobacter، "
                             "Gardnerella، مزارع قديمة، أو خطأ إزالة اللون."
                    )
                    st.session_state.patho_gram_stain = patho_gram

                with pa_col2:
                    patho_urinalysis = st.selectbox(
                        "نتيجة Urinalysis",
                        ["مش معروف / مش مذكور", "Urinalysis طبيعي",
                         "Pyuria (WBCs > 5/HPF)", "Nitrites Positive", "Hematuria"],
                        key="patho_ua_sel"
                    )
                    st.session_state.patho_urinalysis = patho_urinalysis

                    patho_collection = st.selectbox(
                        "طريقة جمع العينة",
                        URINE_COLLECTION_METHODS,
                        key="patho_coll_sel",
                        help="عتبة عدّ المستعمرات تختلف حسب طريقة الجمع: midstream / قسطرة "
                             "(≥10³ مع أعراض) / SPA (أي نمو) — IDSA 2009 و AAP."
                    )

                # ── Urine symptoms ─────────────────────────────────────────
                patho_symptoms = st.multiselect(
                    "الأعراض الكلينيكية",
                    URINE_SYMPTOMS,
                    default=[x for x in st.session_state.patho_symptoms if x in URINE_SYMPTOMS],
                    key="patho_symp_urine",
                    help="اختر Asymptomatic صراحةً لو المريض بلا أعراض — ترك الخانة فاضية معناه "
                         "«غير مُدخل» ولا يُحتسب ضد العدوى. أعراض (SCI) تُحتسب مع إصابة النخاع "
                         "الشوكي أو القسطرة فقط."
                )
                st.session_state.patho_symptoms = patho_symptoms

                # Host factors
                patho_host = st.multiselect(
                    "عوامل المضيف",
                    HOST_FACTORS_URINE,
                    default=[x for x in st.session_state.patho_host_factors
                             if x in HOST_FACTORS_URINE],
                    key="patho_host_sel",
                    help="Paraplegia / Quadriplegia = مثانة عصبية: الـ bacteriuria شبه دائمة ولا "
                         "تُعالَج بلا أعراض، والأعراض غير نمطية (spasticity / dysreflexia)."
                )
                st.session_state.patho_host_factors = patho_host

                if st.button("🔬 احسب Pathogenicity Score", use_container_width=True, key="patho_calc_btn"):
                    # FIX 2026-11-11 (round 4): the engine read pregnancy only
                    # from this multiselect, never from the sidebar flag, so a
                    # pregnant patient's asymptomatic bacteriuria >= 10^5 came
                    # back "do NOT treat" -- IDSA 2019 says treat it -- unless
                    # "Pregnant" was ticked a second time here.
                    if is_preg and "Pregnant" not in patho_host:
                        patho_host = list(patho_host) + ["Pregnant"]
                    patho_kwargs = dict(
                        specimen=culture_type,
                        organism=organism_type,
                        colony_count_text=colony_count,
                        culture_purity=patho_purity,
                        symptoms=patho_symptoms,
                        pus_cells_text=pus_cells_text,
                        urinalysis_result=patho_urinalysis,
                        gram_stain=patho_gram,
                        age=age,
                        sex=sex,
                        host_factors=patho_host,
                        collection_method=patho_collection,
                    )
                    patho_result = assess_pathogenicity(**patho_kwargs)
                    st.session_state.patho_result = patho_result
                    st.session_state.patho_pdf_ctx = {
                        "panel": "urine", "organism": organism_type, "specimen": culture_type,
                        "inputs": {
                            "Colony count": patho_kwargs.get("colony_count_text"),
                            "Collection method": patho_kwargs.get("collection_method"),
                            "Culture purity": patho_kwargs.get("culture_purity"),
                            "Pus cells / HPF": patho_kwargs.get("pus_cells_text"),
                            "Urinalysis": patho_kwargs.get("urinalysis_result"),
                            "Gram stain": patho_kwargs.get("gram_stain"),
                            "Symptoms": patho_kwargs.get("symptoms"),
                            "Host factors": patho_kwargs.get("host_factors"),
                            "Age / Sex": f"{patho_kwargs.get('age')} / {patho_kwargs.get('sex')}",
                        }}

                # ── Display Result (persists after button) ────────────────────
                patho_result = st.session_state.get("patho_result")
                if patho_result:
                    _render_patho_result(patho_result)

        # ═══════════════════════════════════════════════════════════════════════
        # الفرع (ب): Resistance Profile -- لكل المزارع غير البول
        #    يعرض: MDR/XDR/PDR + ESBL/AmpC/Carbapenemase + Phenotypes
        # ═══════════════════════════════════════════════════════════════════════
        else:
            # ═══════════════════════════════════════════════════════════════
            # الفرع (ب-1): Pathogenicity Assessment للعينات غير البول
            #   Blood (SIRS) · Sputum (Murray-Washington) · Stool (GI flora) ·
            #   Wound/Pus (SSTI) · CSF (sterile site)
            # ═══════════════════════════════════════════════════════════════
            _pcat = classify_specimen(culture_type)
            if _pcat in ("blood", "sputum", "stool", "wound", "pus", "csf"):
                _pcap = {
                    "blood":  "هل عدوى مجرى دم حقيقية أم تلوث؟ -- SIRS + نوع الكائن",
                    "sputum": "هل عينة بلغم كافية أم لعاب؟ -- Murray-Washington",
                    "stool":  "هل ممرض معوي حقيقي أم flora طبيعي؟",
                    "wound":  "هل ممرض جرح حقيقي؟ -- نوع الجرح + العلامات الموضعية",
                    "pus":    "هل ممرض حقيقي؟ -- نوع الجرح + العلامات الموضعية",
                    "csf":    "عينة من موقع معقم -- أي نمو مرضي بالضرورة",
                }[_pcat]
                with st.expander("🧫 Pathogenicity Assessment", expanded=False):
                    st.caption(_pcap)

                    # ── Common inputs ──────────────────────────────────────
                    np_c1, np_c2 = st.columns(2)
                    with np_c1:
                        np_purity = st.selectbox(
                            "نقاء المزرعة",
                            ["Pure growth", "Mixed growth"],
                            key="np_purity_sel")
                    with np_c2:
                        np_gram = st.selectbox(
                            "Gram Stain",
                            gram_options_for(organism_type),
                            key="np_gram_sel",
                            help="Gram-variable = نتيجة صبغة وليست نوع بكتيريا: Acinetobacter، "
                                 "Gardnerella، مزارع قديمة، أو خطأ إزالة اللون.")

                    # ── Category-specific inputs ───────────────────────────
                    np_sirs = []; np_blood_source = ""
                    np_sputum_wbc = ""; np_sputum_epi = ""
                    np_wound_type = ""; np_symptoms = []

                    if _pcat == "blood":
                        np_sirs = st.multiselect(
                            "SIRS Criteria (≥2 = SIRS · ≥3 = sepsis probable)",
                            ["Temp > 38°C or < 36°C",
                             "Heart rate > 90 / min",
                             "Resp rate > 20 / min (or PaCO₂ < 32)",
                             "WBC > 12k or < 4k (or > 10% bands)"],
                            key="np_sirs_ms")
                        np_blood_source = st.selectbox(
                            "عدد الزجاجات الإيجابية",
                            ["مش محدد", "Single bottle positive",
                             "Multiple bottles positive"],
                            key="np_bsrc_sel")

                    elif _pcat == "sputum":
                        sp_c1, sp_c2 = st.columns(2)
                        with sp_c1:
                            np_sputum_wbc = st.text_input(
                                "WBCs / LPF", placeholder="مثال: 25",
                                key="np_spwbc")
                        with sp_c2:
                            np_sputum_epi = st.text_input(
                                "Epithelial cells / LPF", placeholder="مثال: 5",
                                key="np_spepi")
                        np_symptoms = st.multiselect(
                            "الأعراض التنفسية",
                            RESPIRATORY_SIGNS,
                            key="np_symp_resp")

                    elif _pcat == "stool":
                        np_symptoms = st.multiselect(
                            "الأعراض المعوية",
                            ["Fever (> 38°C)", "Bloody diarrhea",
                             "Watery diarrhea", "Vomiting", "Abdominal cramps"],
                            key="np_symp_gi")

                    elif _pcat in ("wound", "pus"):
                        np_wound_type = st.selectbox(
                            "نوع الجرح",
                            WOUND_TYPES,
                            key="np_wtype_sel")
                        np_symptoms = st.multiselect(
                            "علامات العدوى الموضعية",
                            WOUND_SIGNS,
                            key="np_symp_wound")

                    elif _pcat == "csf":
                        st.info("🧠 CSF موقع معقم. فلورا الجلد (CoNS وغيرها) بدون shunt/EVD أو "
                                "جراحة أعصاب حديثة قد تكون تلوثاً — سجّل الجهاز في عوامل المضيف.")

                    # ── Host factors (shared) ──────────────────────────────
                    np_host = st.multiselect(
                        "عوامل المضيف",
                        HOST_FACTORS_OTHER,
                        key="np_host_sel",
                        help="Paraplegia / Quadriplegia: قرح الفراش (مسحة سطحية = استعمار) وضعف "
                             "السعال في الإصابات العنقية يغيّران تفسير المزرعة.")

                    if st.button("🔬 احسب Pathogenicity Score",
                                 use_container_width=True, key="np_calc_btn"):
                        st.session_state.patho_result = assess_pathogenicity(
                            specimen=culture_type,
                            organism=organism_type,
                            colony_count_text=colony_count,
                            culture_purity=np_purity,
                            symptoms=np_symptoms,
                            pus_cells_text="",
                            urinalysis_result="",
                            gram_stain=np_gram,
                            age=age, sex=sex,
                            host_factors=np_host,
                            sputum_pus_cells=np_sputum_wbc,
                            sputum_epithelial=np_sputum_epi,
                            sirs_criteria=np_sirs,
                            blood_source=np_blood_source,
                            wound_type=np_wound_type,
                        )
                        st.session_state.patho_pdf_ctx = {
                            "panel": "other", "organism": organism_type, "specimen": culture_type,
                            "inputs": {
                                "Colony count": colony_count, "Culture purity": np_purity,
                                "Gram stain": np_gram, "Signs / symptoms": np_symptoms,
                                "SIRS criteria": np_sirs, "Positive bottles": np_blood_source,
                                "Sputum WBC / LPF": np_sputum_wbc,
                                "Sputum epithelial / LPF": np_sputum_epi,
                                "Wound type": np_wound_type, "Host factors": np_host,
                                "Age / Sex": f"{age} / {sex}",
                            }}

                    _npr = st.session_state.get("patho_result")
                    if _npr:
                        _render_patho_result(_npr)

            with st.expander("🧬 Resistance Profile (ESBL / MDR / Mechanisms)", expanded=True):
                st.caption(
                    f"تحليل مقاومة الكائن **{organism_type}** في عينة **{culture_type}** -- "
                    "تصنيف MDR/XDR/PDR + آليات المقاومة (ESBL / AmpC / Carbapenemase)"
                )

                # sir_map may not be defined yet at this render point — read from session_state
                _sir_map_now = st.session_state.get("sir_map_edited") or {}
                _mdr_r  = classify_mdr(organism_type, _sir_map_now) if _sir_map_now else {"level": None}
                _esbl_r = predict_esbl(organism_type, _sir_map_now) if _sir_map_now else {"probability": None}
                _ph_r   = detect_resistance_phenotypes(organism_type, _sir_map_now) if _sir_map_now else []

                # ── MDR / XDR / PDR ────────────────────────────────────────────
                if _mdr_r.get("level"):
                    _mi = MDR_INFO[_mdr_r["level"]]
                    _rc = _mdr_r["resistant_count"]
                    _rt = _mdr_r["total_tested"]
                    _cats = ", ".join(_mdr_r["resistant_categories"])
                    _gram = _mdr_r.get("gram", "")
                    _msg = (f"{_mi['icon']} **{_mi['label']}**  \n"
                            f"{_mi['detail']}  \n"
                            f"Resistant categories ({_rc}/{_rt}, Gram-{_gram}): {_cats}  \n"
                            f"🔹 {_mi['action']}")
                    if _mdr_r["level"] == "MDR":
                        st.warning(_msg)
                    else:
                        st.error(_msg)
                    for _w in _mdr_r.get("warnings", []):
                        st.caption(_w)
                else:
                    if _sir_map_now:
                        st.success("✅ لا يوجد تصنيف MDR/XDR/PDR -- الكائن حساس لمعظم الفئات.")
                    else:
                        st.info("ℹ️ أدخل نتائج المزرعة (S/I/R) لتحليل المقاومة.")

                # ── ESBL / AmpC / Carbapenemase ───────────────────────────────
                _prob = _esbl_r.get("probability")
                _conf = _esbl_r.get("confidence", 0)
                _mech = _esbl_r.get("mechanism", "")
                if _prob == "carbapenemase":
                    st.error(
                        f"🚨 **{_mech or 'Possible Carbapenemase (KPC/MBL/OXA)'}** "
                        f"(confidence {_conf}%)  \n"
                        f"{_esbl_r.get('detail','')}  \n🔹 {_esbl_r.get('action','')}"
                    )
                elif _prob == "possible_carbapenemase":
                    # Round 4 (2026-11-11): this tier, plasmid AmpC and CR-PA
                    # were not rendered in this panel at all.
                    st.warning(
                        f"⚠️ **{_mech or 'Possible carbapenemase'}** (confidence {_conf}%)  \n"
                        f"{_esbl_r.get('detail','')}  \n🔹 {_esbl_r.get('action','')}"
                    )
                elif _prob in ("ampc", "ampc_plasmid"):
                    st.error(
                        f"⚠️ **{_mech if _prob == 'ampc_plasmid' else 'Possible AmpC β-Lactamase'}** "
                        f"(confidence {_conf}%)  \n"
                        f"{_esbl_r.get('detail','')}  \n🔹 {_esbl_r.get('action','')}"
                    )
                elif _prob == "crpa":
                    (st.error if _esbl_r.get("dtr") else st.warning)(
                        f"{'🚨' if _esbl_r.get('dtr') else '⚠️'} **{_mech}** (confidence {_conf}%)  \n"
                        f"{_esbl_r.get('detail','')}  \n🔹 {_esbl_r.get('action','')}"
                    )
                elif _prob == "high":
                    st.error(
                        f"⚠️ **High Probability ESBL Producer** (confidence {_conf}%)  \n"
                        f"{_esbl_r.get('detail','')}  \n🔹 {_esbl_r.get('action','')}"
                    )
                elif _prob == "moderate":
                    st.warning(
                        f"🔶 **ESBL Confirmation Recommended** (confidence {_conf}%)  \n"
                        f"{_esbl_r.get('detail','')}  \n🔹 {_esbl_r.get('action','')}"
                    )

                # ── Resistance Phenotypes ─────────────────────────────────────
                if _ph_r:
                    st.markdown("**🦠 Resistance Phenotypes Detected:**")
                    for _ph in _ph_r:
                        _iso = "  🚨 **عزل فوري مطلوب**" if _ph["isolation"] else ""
                        _pmsg = (f"{_ph['icon']} **{_ph['label']}**{_iso}  \n"
                                 f"{_ph['detail']}  \n"
                                 f"🔹 {_ph['action']}")
                        if _ph["isolation"]:
                            st.error(_pmsg)
                        else:
                            st.warning(_pmsg)
                        if _ph.get("matched_markers"):
                            st.caption(f"Evidence: {', '.join(_ph['matched_markers'])}")

                # ── Summary stats ──────────────────────────────────────────────
                if _sir_map_now:
                    _s = sum(1 for v in _sir_map_now.values() if v == "S")
                    _i = sum(1 for v in _sir_map_now.values() if v == "I")
                    _r = sum(1 for v in _sir_map_now.values() if v == "R")
                    _sc1, _sc2, _sc3, _sc4 = st.columns(4)
                    _sc1.metric("Total Tested", len(_sir_map_now))
                    _sc2.metric("Sensitive", _s)
                    _sc3.metric("Intermediate", _i)
                    _sc4.metric("Resistant", _r)

            # ── AST Quality Check (QC Engine) ────────────────────────────
            with st.expander("🔬 AST Quality Check -- فحص جودة نتائج الحساسية", expanded=True):
                st.caption(
                    "فحص آلي لاتساق نتائج الـ AST: intrinsic resistance · phenotype "
                    "consistency · cross-resistance · biological plausibility · QC rules"
                )
                _qc_sir = st.session_state.get("sir_map_edited") or {}
                if not _qc_sir:
                    st.info("أدخل نتائج S/I/R أولاً لتشغيل فحص الجودة.")
                else:
                    # ── AST Quality Check (QC Engine) -- needs ast_qa_engine.py ──
                    if not AST_QA_AVAILABLE:
                        st.caption("⚠️ الملف `ast_qa_engine.py` غير موجود -- ارفعه بجانب "
                                   "`streamlit_app.py` لتفعيل فحص الجودة.")
                    else:
                        _qc_mdr  = classify_mdr(organism_type, _qc_sir)
                        _qc_esbl = predict_esbl(organism_type, _qc_sir)
                        # De-duplication: the AST Quality CONTROL panel below runs
                        # ast_reportability (intrinsic resistance / no-breakpoints)
                        # and the specimen-appropriateness pass. Asking the QA
                        # engine for the same two categories printed every one of
                        # those findings twice on the same screen, so they are
                        # suppressed here whenever the shared modules are loaded.
                        _qa_skip = ({"Intrinsic Resistance", "Clinical Context"}
                                    if AST_RULES_MODULES_AVAILABLE else set())
                        # Already shown as its own card below (with
                        # expected/tested/missing counts) -- don't also list
                        # each missing drug a second time in this mixed
                        # findings list.
                        if PANEL_COMPLETENESS_AVAILABLE:
                            _qa_skip = _qa_skip | {"Panel Completeness"}
                        _qc_issues = run_ast_qa_engine(
                            organism=organism_type, specimen=culture_type,
                            sir_map=_qc_sir, esbl_result=_qc_esbl, mdr_result=_qc_mdr,
                            skip_categories=_qa_skip,
                        )
                        if not _qc_issues:
                            st.success("✅ لا توجد تعارضات -- النتائج متسقة داخلياً "
                                       "(لم يُكتشف خطأ منطقي في ملف الحساسية).")
                        else:
                            _sev_counts: Dict[str, int] = {}
                            for _iss in _qc_issues:
                                _sev_counts[_iss.severity] = _sev_counts.get(_iss.severity, 0) + 1
                            _order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
                            _summ = " · ".join(f"{k}: {_sev_counts[k]}"
                                               for k in _order if k in _sev_counts)
                            st.markdown(f"**تم اكتشاف {len(_qc_issues)} ملاحظة** -- {_summ}")
                            _sev_render = {"CRITICAL": st.error, "HIGH": st.warning,
                                           "MEDIUM": st.warning, "LOW": st.info}
                            _sev_icon = {"CRITICAL": "🔴", "HIGH": "🟠",
                                         "MEDIUM": "🟡", "LOW": "🔵"}
                            for _iss in _qc_issues:
                                _render = _sev_render.get(_iss.severity, st.info)
                                _msg = (f"{_sev_icon.get(_iss.severity, '•')} "
                                        f"**[{_iss.severity}] {_iss.category}**  \n{_iss.message}")
                                if _iss.drug:
                                    _msg += f"  \n🧪 {_iss.drug}"
                                _render(_msg)
                                if _iss.detail:
                                    st.caption(_iss.detail)
                                if _iss.reference:
                                    st.caption(f"📖 {_iss.reference}")

                    # ── AST Panel Completeness -- renders AFTER AST QA, ──
                    # ── per request 2026-08-22 ───────────────────────────
                    # Answers a different question from everything above:
                    # "ينقص هذه المزرعة إيه من المضادات؟" -- what is this
                    # specific culture's panel missing. Shown as its own
                    # card, separate from the mixed findings list above (see
                    # _qa_skip there): the same missing drug listed twice,
                    # once here and once buried in that mixed list, is
                    # noise, not thoroughness.
                    #
                    # Independent of AST_QA_AVAILABLE on purpose: this card
                    # calls ast_panel_completeness.py directly, never through
                    # run_ast_qa_engine(), so it has zero real dependency on
                    # that module. It used to sit inside
                    # `if AST_QA_AVAILABLE: ...` purely by accident of where
                    # it got inserted -- an unrelated ast_qa_engine.py
                    # problem could take it down with zero trace anywhere.
                    # Visibility now depends on nothing but its OWN import
                    # (PANEL_COMPLETENESS_AVAILABLE, tracked in Module Health
                    # above) and having sir data -- checked independently of
                    # whether the AST QA block above even ran.
                    if PANEL_COMPLETENESS_AVAILABLE:
                        _pc = _check_panel_completeness_ext(
                            organism_type, culture_type, _qc_sir
                        )
                        if _pc.status != "not_evaluated":
                            _pc_missing = _pc.missing_primary + _pc.missing_supplemental
                            st.divider()
                            st.markdown("**🧫 AST Panel Completeness**")
                            st.caption(f"الكائن: {_pc.organism_group}")
                            _c1, _c2, _c3 = st.columns(3)
                            _c1.metric("Expected", _pc.expected_total)
                            _c2.metric("Tested", _pc.tested_count)
                            _c3.metric("Missing", len(_pc_missing))
                            if not _pc_missing:
                                st.success("✅ Panel adequate -- كل المضادات "
                                           "المتوقعة لهذا الكائن تم اختبارها.")
                            else:
                                if _pc.status == "critical":
                                    st.error(
                                        "🔴 كل المضادات الأساسية اللي اتعملت كانت "
                                        "Resistant، ومضادات أساسية متوقعة لسه معملتش "
                                        "-- ممكن يكون فيه خيار علاجي في اللي ناقص. "
                                        "متقولش 'مفيش خيارات' من لوحة ناقصة."
                                    )
                                else:
                                    st.warning(
                                        f"⚠️ Panel incomplete -- "
                                        f"{len(_pc_missing)} مضاد متوقع غير مُختبَر"
                                    )
                                if _pc.missing_primary:
                                    st.markdown(
                                        "**ناقص (أساسي):** " +
                                        " · ".join(f"⚠️ {d}" for d in _pc.missing_primary)
                                    )
                                if _pc.missing_supplemental:
                                    st.markdown(
                                        "**ناقص (تكميلي/اختياري):** " +
                                        " · ".join(f"🔵 {d}" for d in _pc.missing_supplemental)
                                    )
                                if _pc.rule_id:
                                    from guideline_registry import citation_line as _pc_cite
                                    _pc_ref = _pc_cite(_pc.rule_id)
                                    if _pc_ref:
                                        st.caption(f"📖 {_pc_ref} -- قيد مراجعة د. طارق")


    # ─── العمود الأيمن ────────────────────────────────────────────────────────
    with col2:
        st.subheader("💊 Antibiotic Analysis")

        # ══════════════════════════════════════════════════════
        # AST Input Panel -- OCR + Manual Entry موحّد
        # ══════════════════════════════════════════════════════
        ocr_sir_map = payload["sir_map"]
        sir_options = ["S", "I", "R"]

        st.markdown("**📊 نتائج المزرعة -- S / I / R**")
        st.caption("✅ من OCR تلقائياً -- عدّل أي قيمة خطأ أو أضف مضاد فاته الـ OCR")

        # ── Drugs detected by OCR WITH S/I/R ─────────────────────────
        all_known   = sorted(ABX_GUIDELINES.keys())
        ocr_drugs   = list(ocr_sir_map.keys())

        # Drugs OCR found by NAME but couldn't determine S/I/R for
        ocr_detected_no_sir = [d for d in drugs_from_ocr
                                if d not in ocr_sir_map and d]

        if ocr_detected_no_sir:
            st.markdown(
                f"**🔍 OCR اكتشف {len(ocr_detected_no_sir)} مضاد بدون نتيجة S/I/R واضحة:**",
                help="OCR وجد أسماء هذه الأدوية في الورقة لكن لم يتعرف على النتيجة -- حدد النتيجة يدوياً"
            )
            no_sir_cols = st.columns(min(len(ocr_detected_no_sir), 3))
            for idx_d, drug_no_sir in enumerate(ocr_detected_no_sir):
                col_d = no_sir_cols[idx_d % 3]
                assign = col_d.selectbox(
                    f"⚠️ {drug_no_sir}",
                    ["--", "S", "I", "R"],
                    key=f"no_sir_{drug_no_sir}_{file_hash[:8]}",
                    help=f"OCR وجد '{drug_no_sir}' في النص -- حدد النتيجة أو اتركها"
                )
                if assign != "--":
                    if drug_no_sir not in ocr_drugs:
                        ocr_drugs.append(drug_no_sir)
                    ocr_sir_map[drug_no_sir] = assign
            st.divider()

        # ── الأدوية المضافة يدوياً (فاتها OCR كلياً) ─────────────────
        manual_prev = [d for d in st.session_state.sir_map_edited.keys()
                       if d not in ocr_drugs]

        # ── إضافة سريعة: دواء + نتيجته مرة واحدة ──────────────────────
        # Requested 2026-08-22: adding a missing drug through the multiselect
        # below always lands it at "S" first (that selectbox's own default),
        # then needs a SEPARATE edit afterward to set the real result --
        # exactly the two-step flow that made the freshness bug upstream
        # confusing to reason about (which state was "saved"?). This widget
        # puts the drug picker and its S/I/R result side by side so one
        # click adds the drug WITH its actual result already correct --
        # nothing to go back and fix.
        _quick_add_pool = [d for d in all_known
                           if d not in ocr_drugs and d not in ocr_detected_no_sir
                           and d not in manual_prev]
        if _quick_add_pool:
            st.markdown("<small style='color:#1a6b3a'>⚡ إضافة سريعة -- دواء ونتيجته "
                        "مرة واحدة:</small>", unsafe_allow_html=True)
            _qa_c1, _qa_c2, _qa_c3 = st.columns([5, 2, 2])
            _quick_drug = _qa_c1.selectbox(
                "المضاد الناقص", options=[""] + sorted(_quick_add_pool),
                key=f"quick_add_drug_{file_hash[:8]}", label_visibility="collapsed",
                format_func=lambda d: "اختر المضاد الناقص..." if d == "" else d,
            )
            _quick_sir = _qa_c2.selectbox(
                "النتيجة", options=sir_options,
                key=f"quick_add_sir_{file_hash[:8]}", label_visibility="collapsed",
            )
            if _qa_c3.button("➕ إضافة", key=f"quick_add_btn_{file_hash[:8]}",
                             disabled=not _quick_drug, use_container_width=True):
                _mkey = f"manual_drugs_{file_hash[:8]}"
                _current_manual = list(st.session_state.get(_mkey, manual_prev))
                if _quick_drug not in _current_manual:
                    _current_manual.append(_quick_drug)
                st.session_state[_mkey] = _current_manual
                # Set BOTH the aggregate map (what Panel Completeness/QC read)
                # and this specific drug's own selectbox key (so it renders
                # showing the chosen result, not "S", the instant it appears
                # below) -- same reasoning as the sir_map_edited freshness fix:
                # write before the rerun, not after, so the very next render
                # is already correct.
                _sir_now = dict(st.session_state.sir_map_edited)
                _sir_now[_quick_drug] = _quick_sir
                st.session_state.sir_map_edited = _sir_now
                st.session_state[f"sir_manual_{_quick_drug}_{file_hash[:8]}"] = _quick_sir
                st.rerun()

        manual_extra = st.multiselect(
            "➕ أو أضف عدة مضادات دفعة واحدة (كلها هتتحط S مبدئياً وتقدر تعدّلها تحت)",
            options=[d for d in all_known if d not in ocr_drugs and d not in ocr_detected_no_sir],
            default=manual_prev,
            key=f"manual_drugs_{file_hash[:8]}",
            help="اختر الأدوية التي ظهرت في التقرير لكن OCR لم يكتشفها على الإطلاق",
        )

        # ── بناء القائمة الكاملة: OCR + Manual ───────────────────────
        all_drugs_to_show = ocr_drugs + [d for d in manual_extra if d not in ocr_drugs]

        # ── عرض SIR dropdown لكل دواء ─────────────────────────────────
        edited_sir: Dict[str, str] = {}

        # ── Deleted drugs list (persisted in session) ─────────────────
        _del_key = f"deleted_drugs_{file_hash[:8]}"
        if _del_key not in st.session_state:
            st.session_state[_del_key] = set()

        if all_drugs_to_show:
            # OCR drugs أولاً
            if ocr_drugs:
                st.markdown("<small style='color:#555'>🔍 من OCR -- يمكنك حذف أي مضاد بالضغط على ❌:</small>",
                            unsafe_allow_html=True)
                for i in range(0, len(ocr_drugs), 3):
                    row_drugs = ocr_drugs[i: i + 3]
                    row_cols  = st.columns([3,3,3])
                    for col, drug in zip(row_cols, row_drugs):
                        if drug in st.session_state[_del_key]:
                            # Show restore button
                            if col.button(f"↩️ {drug}", key=f"restore_{drug}_{file_hash[:8]}",
                                          help="استعادة المضاد"):
                                st.session_state[_del_key].discard(drug)
                                st.rerun()
                            continue
                        cur = st.session_state.sir_map_edited.get(drug, ocr_sir_map[drug])
                        if cur not in sir_options:
                            cur = "S"
                        label_icons = {"S": "🟢", "I": "🟡", "R": "🔴"}
                        # 4-column: icon+name | selectbox | delete btn
                        _c1, _c2, _c3 = col.columns([4, 3, 1])
                        _c1.markdown(f"<small>{label_icons.get(cur,'')} **{drug}**</small>",
                                     unsafe_allow_html=True)
                        new_val = _c2.selectbox(
                            "##",
                            options=sir_options,
                            index=sir_options.index(cur),
                            key=f"sir_{drug}_{file_hash[:8]}",
                            label_visibility="collapsed"
                        )
                        if _c3.button("❌", key=f"del_{drug}_{file_hash[:8]}",
                                      help=f"حذف {drug}"):
                            st.session_state[_del_key].add(drug)
                            st.rerun()
                        edited_sir[drug] = new_val

            # Manual drugs
            manual_new = [d for d in manual_extra if d not in ocr_drugs]
            if manual_new:
                st.markdown("<small style='color:#1a6b3a'>➕ مُضافة يدوياً:</small>",
                            unsafe_allow_html=True)
                for i in range(0, len(manual_new), 3):
                    row_drugs = manual_new[i: i + 3]
                    row_cols  = st.columns(3)
                    for col, drug in zip(row_cols, row_drugs):
                        if drug in st.session_state[_del_key]:
                            if col.button(f"↩️ {drug}", key=f"restore_m_{drug}_{file_hash[:8]}"):
                                st.session_state[_del_key].discard(drug)
                                st.rerun()
                            continue
                        cur = st.session_state.sir_map_edited.get(drug, "S")
                        if cur not in sir_options:
                            cur = "S"
                        label_icons = {"S": "🟢", "I": "🟡", "R": "🔴"}
                        _c1, _c2, _c3 = col.columns([4, 3, 1])
                        _c1.markdown(f"<small>{label_icons.get(cur,'')} **{drug}**</small>",
                                     unsafe_allow_html=True)
                        new_val = _c2.selectbox(
                            "##",
                            options=sir_options,
                            index=sir_options.index(cur),
                            key=f"sir_manual_{drug}_{file_hash[:8]}",
                            label_visibility="collapsed"
                        )
                        if _c3.button("❌", key=f"del_m_{drug}_{file_hash[:8]}",
                                      help=f"حذف {drug}"):
                            st.session_state[_del_key].add(drug)
                            st.rerun()
                        edited_sir[drug] = new_val

        # ── Apply deletions to sir_map ────────────────────────────────
        _deleted = st.session_state.get(_del_key, set())
        edited_sir = {d: v for d, v in edited_sir.items() if d not in _deleted}

        # 2026-08-22: Resistance Profile / AST Quality Check / Panel
        # Completeness (above, ~line 6267/6355) render BEFORE this block in
        # script order, so on the run where the user just changed a result
        # they were reading st.session_state.sir_map_edited as it stood at
        # the END of the PREVIOUS run -- one edit behind. Each individual
        # st.selectbox's own session_state[key] is already fresh at this
        # point (Streamlit syncs those before the script starts), but the
        # AGGREGATE dict those QC sections actually read is only assembled
        # here. Rather than relocating ~150 lines of interdependent widget
        # code above this point (real risk of breaking the column/key/rerun
        # interactions elsewhere on this page), force one extra rerun exactly
        # when the aggregate changed -- the same st.rerun() idiom this block
        # already uses for delete/restore, just keyed off a value change
        # instead of a button click. sir_map_edited is written BEFORE the
        # rerun fires, so the follow-up run reads current data and converges
        # (no loop): a real Piperacillin+Tazobactam entry no longer shows as
        # missing the moment it's saved, not one edit later.
        _prev_sir_map_edited = st.session_state.get("sir_map_edited")
        st.session_state.sir_map_edited = edited_sir
        if edited_sir != _prev_sir_map_edited:
            st.rerun()

        # sir_map = كل الأدوية (OCR + manual) مع نتائجها -- بعد الحذف
        sir_map = dict(edited_sir)

        # final_drugs = كل الأدوية التي أُدخلت نتائجها
        final_drugs = list(sir_map.keys())

        # ── ملخص سريع ─────────────────────────────────────────────────
        if sir_map:
            s_count = sum(1 for v in sir_map.values() if v == "S")
            i_count = sum(1 for v in sir_map.values() if v == "I")
            r_count = sum(1 for v in sir_map.values() if v == "R")
            st.caption(
                f"📊 إجمالي: {len(sir_map)} مضاد &nbsp;|&nbsp; "
                f"🟢 Sensitive: {s_count} &nbsp;|&nbsp; "
                f"🟡 Intermediate: {i_count} &nbsp;|&nbsp; "
                f"🔴 Resistant: {r_count}"
            )

        # ── تحليل المضادات ────────────────────────────────────────────────────
        # النقطة ٤: analyze_antibiotics يُستدعى مباشرة بقيم اللحظة
        # فأي تغيير في أي widget يُعيد تشغيل Streamlit -> تحديث فوري
        # The grade now comes from the sidebar widget, which runs BEFORE this
        # point, so it reflects what the clinician actually selected on this run.
        # The default is "C" in both places: an ungraded liver must not be read as
        # the mildest one.
        _child_pugh_now = st.session_state.get("child_pugh_class", "C") if is_hepatic else "A"

        for _pp in validate_patient_context(age, sex, is_preg, cl_cr, age_months):
            st.warning(_pp)
        # ONE call instead of two inlined ones. run_analysis() is this same
        # pipeline exposed as a pure function, so a test can walk exactly the
        # path the clinician walks — see its docstring for why that matters.
        _patient = Patient(
            age_years=age, age_months=age_months, sex=sex,
            is_pregnant=is_preg, is_renal=is_renal, cl_cr=cl_cr,
            is_hepatic=is_hepatic, child_pugh=_child_pugh_now,
            current_meds=list(current_meds or []),
            allergies=list(allergies or []),
        )
        _carb_type_now = normalize_carbapenemase_type(carbapenemase_choice)
        _uti_syn_now = resolve_uti_syndrome(uti_syndrome_choice,
                                            st.session_state.get("patho_symptoms") or [])
        st.session_state["carb_type_now"] = _carb_type_now
        _res = run_analysis(_patient, organism_type, culture_type, sir_map,
                            drugs=final_drugs, carbapenemase_type=_carb_type_now,
                            uti_syndrome=_uti_syn_now)
        if _uti_syn_now == "upper" and classify_specimen(culture_type) == "urine":
            st.info("🫘 التهاب حويضة / cUTI — Nitrofurantoin و Fosfomycin الفموي و Norfloxacin "
                    "مُستبعدة (لا تصل لنسيج الكلى).")
        allowed              = _res["allowed"]
        warned               = _res["warned"]
        banned               = _res["banned"]
        preg_warn_items      = _res["preg_warn"]
        interactions_alerts  = _res["interactions"]
        for _pw in _res["patient_warnings"]:
            st.warning(_pw)

        # ══════════════════════════════════════════════════════════════════════
        # TERMINAL SAFETY GATE — second, independent opinion before display
        # ----------------------------------------------------------------------
        # clinical_matrix.py + safety_gate.py were written, tested (33 proofs)
        # and then never imported by this file, so the whole layer was inert.
        # It supplies what analyze_antibiotics structurally cannot: the
        # pharmacokinetic compartment. Without it this app was placing
        # Cefazolin, Cephalexin, Clindamycin, Azithromycin and Ertapenem in the
        # RECOMMENDED bucket for a CSF isolate — none of them reliably cross the
        # blood-brain barrier at meningeal doses.
        #
        # The gate is DEMOTE-ONLY (allowed -> caution -> avoid, never the
        # reverse), which is what makes it safe to run in front of a live
        # engine: the worst a bug in it can do is make the advice stricter.
        # ══════════════════════════════════════════════════════════════════════
        if SAFETY_GATE_AVAILABLE:
            _gate_report = _res["gate_report"]
            _moves = _gate_report.get("moves") or []
            if _moves:
                with st.expander(
                    f"🛡️ Safety gate — {len(_moves)} agent(s) reclassified",
                    expanded=any(m.get("to") == "banned" for m in _moves),
                ):
                    st.caption(
                        "طبقة أمان مستقلة راجعت المخرجات (نفاذية الموقع، الحمل، الكبد، "
                        "الكلى، العمر). لا يمكنها ترقية أي دواء — فقط تشديد التصنيف."
                    )
                    for _m in _moves:
                        st.write(
                            f"- **{_m.get('drug')}**: `{_m.get('from')}` → "
                            f"`{_m.get('to')}` — "
                            # `why` is what safety_gate has always emitted;
                            # reason_ar/_en were added 2026-08-01. Neither of
                            # the two keys this line used to read existed, so
                            # 33/33 moves rendered with a blank reason.
                            f"{_m.get('reason_ar') or _m.get('why') or _m.get('reason_en') or ''}"
                        )
            if not _gate_report.get("specimen_recognised", True):
                st.warning(
                    f"⚠️ الطبقة الآمنة لم تتعرف على نوع العينة «{culture_type}» — "
                    "تم تطبيق سياسة fail-closed. راجع التوصيات يدوياً."
                )

        if interactions_alerts:
            st.warning("⚡ Interactions / Hepatic Warnings")
            for alert in interactions_alerts:
                st.write(alert)

        # ── MDR / XDR / PDR Classification ───────────────────────────────────
        mdr_result  = classify_mdr(organism_type, sir_map)
        esbl_result = predict_esbl(organism_type, sir_map)

        if mdr_result["level"] or (esbl_result.get("probability") and esbl_result["probability"] not in ("low", None)):
            with st.expander("🧬 Resistance Classification", expanded=True):

                # MDR/XDR/PDR
                if mdr_result["level"]:
                    info = MDR_INFO[mdr_result["level"]]
                    _rc  = mdr_result["resistant_count"]
                    _rt  = mdr_result["total_tested"]
                    _cats = ", ".join(mdr_result["resistant_categories"])
                    _gram = mdr_result.get("gram", "")
                    _msg = (f"{info['icon']} **{info['label']}**  \n"
                            f"{info['detail']}  \n"
                            f"Resistant categories ({_rc}/{_rt}, Gram-{_gram}): {_cats}  \n"
                            f"🔹 {info['action']}")
                    if mdr_result["level"] == "MDR":
                        st.warning(_msg)
                    else:
                        st.error(_msg)
                    # Reliability warnings
                    for _w in mdr_result.get("warnings", []):
                        st.caption(_w)

                # ESBL Predictor
                prob = esbl_result.get("probability")
                _conf = esbl_result.get("confidence", 0)
                _mech = esbl_result.get("mechanism", "")
                if prob == "carbapenemase":
                    _em = (f"[!!] {_mech or 'Possible Carbapenemase (KPC/MBL/OXA)'} "
                           f"(confidence {_conf}%)\n"
                           + esbl_result["detail"] + "  \n🔹 " + esbl_result["action"])
                    st.error(_em)
                elif prob == "possible_carbapenemase":
                    # FIX 2026-11-11 (round 4): this tier (one carbapenem R, an
                    # isolated ertapenem R, or meropenem I) opened this expander
                    # and then printed nothing -- its mCIM / PCR instruction
                    # never reached the screen.
                    _em = (f"[!] {_mech or 'Possible carbapenemase'} (confidence {_conf}%)\n"
                           + esbl_result.get("detail", "") + "  \n🔹 " + esbl_result.get("action", ""))
                    st.warning(_em)
                elif prob in ("ampc", "ampc_plasmid"):
                    _em = (f"[!] Possible AmpC β-Lactamase (confidence {_conf}%)\n"
                           + esbl_result["detail"] + "  \n🔹 " + esbl_result["action"])
                    st.error(_em)
                elif prob == "high":
                    _em = (f"[!] High Probability ESBL Producer (confidence {_conf}%)\n"
                           + esbl_result["detail"] + "  \n🔹 " + esbl_result["action"])
                    st.error(_em)
                elif prob == "crpa":
                    _em = (f"[{'!!' if esbl_result.get('dtr') else '!'}] "
                           f"{_mech} (confidence {_conf}%)\n"
                           + esbl_result["detail"] + "  \n🔹 " + esbl_result["action"])
                    if esbl_result.get("dtr"):
                        st.error(_em)
                    else:
                        st.warning(_em)
                elif prob == "moderate":
                    _em = (f"[~] ESBL Confirmation Recommended (confidence {_conf}%)\n"
                           + esbl_result["detail"] + "  \n🔹 " + esbl_result["action"])
                    st.warning(_em)

        # ── Resistance Phenotype Engine ──────────────────────────────────
        phenotypes = detect_resistance_phenotypes(organism_type, sir_map)
        if phenotypes:
            with st.expander("🦠 Resistance Phenotypes Detected", expanded=True):
                for ph in phenotypes:
                    isolation_tag = "  🚨 **عزل فوري مطلوب**" if ph["isolation"] else ""
                    msg = (f"{ph['icon']} **{ph['label']}**{isolation_tag}  \n"
                           f"{ph['detail']}  \n"
                           f"🔹 {ph['action']}")
                    if ph["isolation"]:
                        st.error(msg)
                    else:
                        st.warning(msg)
                    if ph.get("matched_markers"):
                        st.caption(f"Evidence: {', '.join(ph['matched_markers'])}")

        # ── AST Quality Control Checker ───────────────────────────────────
        if sir_map:
            qc_issues    = run_ast_qc(organism_type, sir_map, specimen=culture_type)
            qa_confidence = compute_qa_confidence(qc_issues, sir_map, organism_type)

            with st.expander(
                f"{qa_confidence['icon']} AST Quality Control -- "
                f"{qa_confidence['level']} ({qa_confidence['score']}/100)"
                + (f" -- {len(qc_issues)} Issue(s)" if qc_issues else ""),
                expanded=bool(qc_issues)
            ):
                st.caption("تحقق تلقائي من منطقية نتائج المزرعة وفق EUCAST Expert Rules")

                # Confidence score box
                st.markdown(
                    f"<div style='padding:2mm 3mm;border-radius:2mm;"
                    f"background:{qa_confidence['color']}15;"
                    f"border:1px solid {qa_confidence['color']};margin-bottom:4px'>"
                    f"<b style='color:{qa_confidence['color']}'>"
                    f"{qa_confidence['icon']} {qa_confidence['level']} — {qa_confidence['score']}/100</b>"
                    f"<ul style='margin:4px 0 0 16px;padding:0;font-size:0.85em'>"
                    + "".join(f"<li>{r}</li>" for r in qa_confidence["reasons"])
                    + "</ul></div>",
                    unsafe_allow_html=True,
                )

                if qc_issues:
                    for issue in qc_issues:
                        icon = "❌" if issue["severity"] == "error" else "⚠️"
                        if issue["severity"] == "error":
                            st.error(f"{issue['message']}  \n✏️ {issue['fix']}")
                        else:
                            st.warning(f"{issue['message']}  \n✏️ {issue['fix']}")
                else:
                    st.success("✅ All AST consistency checks passed. No issues detected.")

                # ── AST Panel Completeness ──────────────────────────────
                # Added HERE 2026-08-22: this is the "AST Quality Control"
                # expander (run_ast_qc(), EUCAST-based) -- a completely
                # separate, independent rendering pipeline from the
                # ast_qa_engine.py-based "🔬 AST Quality Check" expander
                # elsewhere on this page. Panel Completeness had only been
                # wired into the LATTER, which meant it never appeared here
                # at all, no matter how correctly it worked on its own --
                # this repo has carried two parallel QC systems since before
                # this feature existed (flagged, not caused, by this work).
                # Independent of qc_issues/AST_QA_AVAILABLE on purpose, same
                # reasoning as the other integration point: this card calls
                # ast_panel_completeness.py directly and has no dependency on
                # run_ast_qc() succeeding or failing.
                if PANEL_COMPLETENESS_AVAILABLE:
                    _pc2 = _check_panel_completeness_ext(
                        organism_type, culture_type, sir_map
                    )
                    if _pc2.status != "not_evaluated":
                        _pc2_missing = _pc2.missing_primary + _pc2.missing_supplemental
                        st.divider()
                        st.markdown("**🧫 AST Panel Completeness**")
                        st.caption(f"الكائن: {_pc2.organism_group}")
                        _pc2c1, _pc2c2, _pc2c3 = st.columns(3)
                        _pc2c1.metric("Expected", _pc2.expected_total)
                        _pc2c2.metric("Tested", _pc2.tested_count)
                        _pc2c3.metric("Missing", len(_pc2_missing))
                        if not _pc2_missing:
                            st.success("✅ Panel adequate -- كل المضادات "
                                       "المتوقعة لهذا الكائن تم اختبارها.")
                        else:
                            if _pc2.status == "critical":
                                st.error(
                                    "🔴 كل المضادات الأساسية اللي اتعملت كانت "
                                    "Resistant، ومضادات أساسية متوقعة لسه معملتش "
                                    "-- ممكن يكون فيه خيار علاجي في اللي ناقص. "
                                    "متقولش 'مفيش خيارات' من لوحة ناقصة."
                                )
                            else:
                                st.warning(
                                    f"⚠️ Panel incomplete -- "
                                    f"{len(_pc2_missing)} مضاد متوقع غير مُختبَر"
                                )
                            if _pc2.missing_primary:
                                st.markdown(
                                    "**ناقص (أساسي):** " +
                                    " · ".join(f"⚠️ {d}" for d in _pc2.missing_primary)
                                )
                            if _pc2.missing_supplemental:
                                st.markdown(
                                    "**ناقص (تكميلي/اختياري):** " +
                                    " · ".join(f"🔵 {d}" for d in _pc2.missing_supplemental)
                                )
                            if _pc2.rule_id:
                                from guideline_registry import citation_line as _pc2_cite
                                _pc2_ref = _pc2_cite(_pc2.rule_id)
                                if _pc2_ref:
                                    st.caption(f"📖 {_pc2_ref}")

                # QA Report PDF — for microbiologist internal archive only
                st.divider()
                st.caption("📄 تقرير الجودة الداخلي (للميكروبيولوجي فقط — لا يُرسل للطبيب)")
                if WEASYPRINT_AVAILABLE:
                    _qa_pdf = generate_qa_report_pdf(
                        organism=organism_type,
                        specimen=culture_type,
                        sir_map=sir_map,
                        qc_issues=qc_issues,
                        confidence=qa_confidence,
                        microbiologist=st.session_state.get("microbiologist", ""),
                        # FIX 2026-08-03. This read "patient_name", a key NOTHING
                        # in this file ever writes — the name is stored under
                        # patient_name_final (the confirmed value) and
                        # patient_name_ocr (what the scan read). So the patient
                        # reference on every internal QA report has been blank
                        # since the field was added, and a QA document with no
                        # patient reference cannot be tied back to the isolate
                        # it audits, which is the only thing it is for.
                        #
                        # Found by a static session_state audit: 4 keys were
                        # READ that are never WRITTEN, and this was the one that
                        # mattered. Same shape as the safety-gate "why" versus
                        # "reason_ar" mismatch — a producer and a consumer
                        # naming the same fact differently.
                        patient_ref=(st.session_state.get("patient_name_final", "")
                                     or st.session_state.get("patient_name_ocr", "")
                                     or ""),
                    )
                    if _qa_pdf:
                        st.download_button(
                            "⬇️ Download AST-QA Report (PDF)",
                            data=_qa_pdf,
                            file_name=f"AST-QA-Report-{datetime.now().strftime('%Y%m%d-%H%M')}.pdf",
                            mime="application/pdf",
                            key="qa_report_pdf_dl",
                        )
                    else:
                        st.caption("⚠️ تعذر إنشاء PDF لتقرير الجودة.")
                else:
                    st.caption("⚠️ WeasyPrint غير متاح في هذه البيئة.")

        # ── Smart Antibiotic Ranking ──────────────────────────────────────
        if allowed:
            ranked = rank_sensitive_antibiotics(
                allowed, culture_type, organism_type, sir_map, phenotypes
            )
            with st.expander("🏆 Smart Antibiotic Ranking", expanded=False):
                st.caption("مرتب حسب: نتيجة المزرعة + WHO AWaRe + طريق الإعطاء + ملاءمة العينة")
                _aic = {"Access": "🟢", "Watch": "🟡", "Reserve": "🔴"}
                for i, item in enumerate(ranked[:8], 1):
                    sir_badge  = item.get("_sir", "--")
                    aware      = item.get("aware", "")
                    route      = "💊 Oral" if item.get("high_po") else "💉 IV/IM"
                    score      = item.get("_score", 0)
                    aware_icon = _aic.get(aware, "⚪")
                    st.markdown(
                        f"**{i}.** {item['name']} &nbsp; "
                        f"`{sir_badge}` &nbsp; {aware_icon} {aware} &nbsp; {route} &nbsp;"
                        f"<small style='color:gray'>score:{score}</small>",
                        unsafe_allow_html=True)

        # ── Infection Syndrome Module ─────────────────────────────────────
        syndrome_info = get_infection_syndrome(
            specimen=culture_type,
            organism=organism_type,
            age=age,
            is_preg=is_preg,
            is_cath=False,
            sex=sex,
        )
        if syndrome_info:
            with st.expander(f"🏥 Infection Syndrome: {syndrome_info['syndrome']}", expanded=False):
                s1, s2 = st.columns(2)
                with s1:
                    st.markdown(f"**النوع:** {syndrome_info['sub_type']}")
                    st.markdown(f"**مدة العلاج:** {syndrome_info['duration']}")
                    st.markdown(f"**الخط الأول (guidelines):** {', '.join(syndrome_info['first_choice'])}")
                with s2:
                    st.info(f"**Escalation:** {syndrome_info['escalation']}")
                    st.caption(f"📌 Culture threshold: {syndrome_info['threshold']}")

        if is_preg and preg_warn_items:
            st.markdown("---")
            st.markdown("### 🤰 Pregnancy -- Use With Caution")
            st.info(
                "الأدوية التالية **ليست محظورة تلقائيًا** لكنها تحتاج تقييمًا طبيًا دقيقًا.\n\n"
                "**القرار النهائي للطبيب المعالج حصراً.**"
            )
            for item in preg_warn_items:
                with st.expander(f"⚠️ {item['name']} -- تفاصيل التحذير"):
                    for line in (item.get("preg_note") or "").splitlines():
                        st.write(line)

        if banned:
            with st.expander("🚫 Contraindicated / Ineffective", expanded=True):
                # Every category the engine and the gate emit (2026-11-11, round
                # 4): ten of them had no label and printed an empty "[]".
                cat_labels = {
                    "resistant": "مقاوم في المزرعة",
                    "renal":     "قصور كلوي",
                    "pregnancy": "ممنوع في الحمل",
                    "child":     "غير مناسب للعمر",
                    "neonate":   "حديثو الولادة / الرضع",
                    "hepatic":   "قصور كبدي",
                    "allergy":   "حساسية دوائية",
                    "organism":  "غير فعال للجرثومة",
                    "cross_resistance": "مقاومة متصالبة",
                    "no_breakpoint": "لا breakpoint / غير مُبلَّغ",
                    "d_test_inducible": "مقاومة مستحثة (D-test)",
                    "penicillinase_producer": "Penicillinase",
                    "specimen":  "غير مناسب للعينة",
                    "uti_upper": "لا يصلح للحويضة / cUTI",
                    "safety_gate": "بوابة الأمان (الموقع / حالة المريض)",
                    "unreadable": "نتيجة غير مقروءة",
                    "other":     "موانع أخرى",
                }
                for item in banned:
                    _cat = item.get("category", "")
                    st.error(
                        f"💊 {item['name']}  [{cat_labels.get(_cat, _cat)}]\n"
                        f"{item.get('reason_short', '')}"
                    )

        if warned:
            with st.expander("🟡 Warnings / Dose Adjustment Required", expanded=True):
                # `culture_intermediate` rather than warning_reason: an I that
                # also needs a renal or hepatic adjustment carries the OTHER
                # reason in that slot, and used to drop out of this banner
                # entirely. Both facts are now shown for the same agent.
                _interm = [w for w in warned
                           if w.get("warning_reason") == "intermediate_culture"
                           or w.get("culture_intermediate")]
                _others = [w for w in warned if w.get("warning_reason") != "intermediate_culture"]
                if _interm:
                    _names = ", ".join(
                        w['name'] + (f" [{sir_map[w['name']]}]" if sir_map and w['name'] in sir_map else "")
                        for w in _interm
                    )
                    st.warning(
                        f"⚠ Intermediate (I) on culture -- use only if no better option: **{_names}**"
                    )
                for item in _others:
                    sir_tag = (f" [{sir_map[item['name']]}]"
                               if sir_map and item['name'] in sir_map else "")
                    # One resolver, not an if/else that fell through to
                    # renal_note for every reason it did not name explicitly.
                    _note = warned_note_for(item, "ar")
                    if _note:
                        st.warning(f"**{item['name']}{sir_tag}** -- {_note}")
                    else:
                        # An item with no explanation is a data defect, not a
                        # blank bullet: say so rather than rendering a bare name.
                        st.warning(
                            f"**{item['name']}{sir_tag}** -- ⚠️ تحذير بلا تفسير "
                            f"مسجَّل (reason={item.get('warning_reason') or '—'}). "
                            "راجِع النتيجة يدوياً وأبلغ عن العطل."
                        )
                    # An I result that also needs a dose adjustment gives the
                    # clinician two instructions pointing opposite ways. Say so
                    # explicitly rather than printing only the one that happened
                    # to win the warning_reason slot.
                    if (item.get("culture_intermediate")
                            and item.get("warning_reason") in ("renal_adjustment",
                                                               "hepatic_adjustment")):
                        st.error(
                            f"⚠️ **{item['name']}: تعارض في اتجاه الجرعة.** "
                            "النتيجة **I** — وتعريف EUCAST لها *Susceptible, "
                            "Increased exposure*: الدواء يعمل فقط بجرعة أعلى أو "
                            "تسريب ممتد. لكن حالة المريض تفرض **خفض** الجرعة. "
                            "لا تُعدّل الجرعة بناءً على أحد العاملين وحده — "
                            "اختر بديلاً حسّاساً (S) إن وُجد، أو استشر "
                            "الصيدلة الإكلينيكية لضبط الجرعة بمتابعة TDM."
                        )

        if allowed:
            st.success(f"🟢 {len(allowed)} Recommended Option(s)")
            for item in allowed:
                sir_badge = (f" [{sir_map[item['name']]}]"
                             if sir_map and item['name'] in sir_map else "")
                preg_flag = " 🤰" if (is_preg and preg_status_of(item) == "Warn") else ""
                aware_val = item.get("aware", "Unknown")
                color_val = AWARE_COLORS.get(aware_val, aware_val)
                with st.expander(
                    f"{item['name']}{sir_badge}{preg_flag} -- {color_val}", expanded=False
                ):
                    c1, c2 = st.columns(2)
                    c1.write(f"**Class:** {item.get('class','-')}")
                    c2.write(f"**Route:** {get_route_label(item)}")
                    st.write(f"**Note:** {item.get('note','-')}")
                    if item.get("clinical_note"):
                        st.info(f"🧭 {item['clinical_note']}")
                    spec_note = (item.get("specimen_notes") or {}).get(culture_type, "")
                    if spec_note:
                        st.info(f"**{culture_type} Note:** {spec_note}")
                    if is_renal:
                        st.caption(f"Renal: {item.get('renal_note','-')}")
                    if is_preg and preg_status_of(item) == "Warn":
                        pn = (item.get("preg_note") or "").splitlines()
                        if pn:
                            st.caption(f"🤰 {pn[0]}")
        elif not banned and not warned:
            st.info("اختر المضادات الحساسة أو المناسبة من القائمة أعلاه.")

        # ── التقرير والصورة ──────────────────────────────────────────────────
        if final_drugs:
            st.divider()

            # مصدر الترتيب الموحّد — يُحسب هنا لضمان توفره بغضّ النظر عن أي
            # حساب سابق مشروط (كان يُعرّف داخل expander منفصل → NameError محتمل).
            ranked = rank_sensitive_antibiotics(
                allowed, culture_type, organism_type, sir_map, phenotypes
            )

            # بناء قوائم الصورة
            reserve_names = uniq_keep_order([
                item['name'] for item in (allowed + warned)
                if item.get("aware") == "Reserve"
            ])
            # مصدر ترتيب واحد موحّد: نفس ترتيب rank_sensitive_antibiotics
            # (الحساسية أولاً ثم العينة ثم AWaRe ثم الطريق) — نستبعد الـ Reserve
            # من قائمة الـ PREFERRED فقط (تظهر منفصلة كـ Reserve).
            preferred_sorted = [
                item for item in ranked if item.get("aware") != "Reserve"
            ]
            preferred_names = [item['name'] for item in preferred_sorted]
            # للصورة: نضيف badge [A] أو [W] بجانب الاسم
            preferred_with_badge = [
                (f"{item['name']} [A]" if item.get('aware') == 'Access'
                 else f"{item['name']} [W]" if item.get('aware') == 'Watch'
                 else item['name'])
                for item in preferred_sorted
            ]
            # النقطة ٣: use_caution يشمل warned + preg_warn
            preg_caution_names = [item['name'] for item in preg_warn_items]
            use_caution_names  = uniq_keep_order(
                [item['name'] for item in warned if item['name'] not in reserve_names]
                + preg_caution_names
            )
            # Build banned names WITH reason tag for the image (same logic as PDF)
            _esbl_prob_img    = esbl_result.get("probability","low") if esbl_result else "low"
            _img_esbl_like    = _esbl_prob_img in ("high","ampc")
            _img_carbapenemase= _esbl_prob_img == "carbapenemase"
            _img_mrsa         = any("MRSA" in str(p.get("phenotype","")).upper() for p in (phenotypes or [])) \
                                or "mrsa" in organism_type.lower()
            def _img_ban_tag(bd):
                cat = bd.get("category",""); nm = bd.get("name","")
                _s = sir_map.get(nm,"")
                _cl = (ABX_GUIDELINES.get(nm,{}).get("class","") or "").lower()
                if cat == "resistant" or _s == "R":         return "(R)"
                if cat == "pregnancy":                       return "(Pregnancy)"
                if cat in ("child","pediatric"):             return "(Pediatric)"
                if cat == "renal":                           return "(Renal)"
                if cat == "organism":
                    _bl = any(k in _cl for k in ("penicillin","cephalosporin","carbapenem"))
                    if _img_mrsa and _bl:          return "(MRSA)"
                    if _img_carbapenemase and _bl: return "(Carbapenemase)"
                    if _img_esbl_like and _bl:     return "(ESBL)"
                    return "(Intrinsic R)"
                return "(Avoid)"
            _seen_ban = set()
            banned_names = []
            for item in banned:
                nm = item.get("name","")
                if nm and nm not in _seen_ban:
                    _seen_ban.add(nm)
                    banned_names.append(f"{nm} {_img_ban_tag(item)}")
            org_profile    = ORGANISM_PROFILE.get(organism_type, {})
            # الـ first-line في ORGANISM_PROFILE قائمة عامة للميكروب وغير مفلترة
            # بنتيجة المزرعة — قد تحتوي دواءً مقاوماً في هذه العينة. نُبقي فقط
            # الأدوية التي اجتازت فلتر الحساسية فعلاً (موجودة في allowed غير الـ R)،
            # وبنفس ترتيب rank_sensitive_antibiotics. إن لم يتبقَّ شيء نترك القائمة
            # فارغة (لا نعرض first-line مقاوماً).
            _profile_fl    = org_profile.get("first_line", []) or []
            _allowed_names = {it.get("name", "") for it in allowed}
            _ranked_names  = [it.get("name", "") for it in ranked]
            first_line_l   = [
                d for d in _ranked_names
                if d in _profile_fl and d in _allowed_names
            ]

            notes: List[str] = []
            if is_renal:
                notes.append(f"Renal impairment: CrCl {crcl_label(cl_cr, is_renal)} "
                             f"-- dose adjustment required.")
            if is_preg:
                notes.append("Pregnancy: use with caution; consult specialist.")
            if age < 18:
                notes.append("Pediatric age: verify age-specific suitability.")
            if banned:
                notes.append(f"{len(banned)} contraindicated / ineffective antibiotics.")
            if warned:
                notes.append(f"{len(warned)} antibiotics need caution or dose adjustment.")
            notes.append("Treatment guided by severity and local resistance patterns.")
            notes.append("De-escalate based on culture & sensitivity.")

            # Use syndrome_info directly
            # syndrome_info is already defined

            # ════════════════════════════════════════════════════════════
            # CLINICAL ENGINES UI -- v4.0
            # ════════════════════════════════════════════════════════════
            st.divider()

            # ── ① Treatment Duration ─────────────────────────────────
            with st.expander("⏱️ Treatment Duration", expanded=False):
                st.caption("Evidence-based duration -- IDSA AMR Guidance 2026 | Sanford 2025")

                # ── Auto-suggest severity from patient factors ─────────────
                _auto = suggest_severity(
                    specimen=culture_type, age=age, sex=sex,
                    is_preg=is_preg, is_renal=is_renal, cl_cr=cl_cr,
                    host_factors=st.session_state.get("patho_host_factors", []),
                    symptoms=st.session_state.get("patho_symptoms", []),
                )
                _suggested   = _auto["suggested"]
                _auto_reasons = _auto["reasons"]

                # Only auto-set on first load or when user hasn't overridden
                _sev_key = f"severity_manual_{culture_type}_{organism_type}"
                if not st.session_state.get(_sev_key):
                    st.session_state.severity_level = _suggested

                # Show auto-suggestion chip
                _chip_color = {"mild": "#f39c12", "moderate": "#e67e22",
                               "severe": "#c0392b"}[_suggested]
                st.markdown(
                    f"**🤖 Auto-suggested:** "
                    f"<span style='background:{_chip_color};color:white;"
                    f"padding:1px 8px;border-radius:8px;font-size:0.85em'>"
                    f"{_suggested.upper()}</span> "
                    f"<small style='color:gray'>-- {_auto_reasons[0] if _auto_reasons else ''}</small>",
                    unsafe_allow_html=True,
                )

                _sev = st.selectbox(
                    "Case Severity (يمكنك التعديل يدوياً)",
                    ["mild", "moderate", "severe"],
                    index=["mild","moderate","severe"].index(
                        st.session_state.get("severity_level","moderate")),
                    format_func=lambda x:{"mild":"🟡 Mild","moderate":"🟠 Moderate","severe":"🔴 Severe"}[x],
                    key="sev_sel_ui")

                # Mark as manually overridden if changed
                if _sev != _suggested:
                    st.session_state[_sev_key] = True
                    if _sev != st.session_state.get("severity_level"):
                        st.caption(f"ℹ️ تم تعديل الشدة يدوياً من {_suggested} -> {_sev}")
                else:
                    st.session_state[_sev_key] = False

                st.session_state.severity_level = _sev
                _syn_lbl = duration_syndrome_key(syndrome_info, _uti_syn_now, culture_type)
                _dur = get_treatment_duration(
                    specimen=culture_type, organism=organism_type,
                    syndrome=_syn_lbl, age=age, sex=sex,
                    is_renal=is_renal, phenotypes=phenotypes, severity=_sev)
                _d1, _d2, _d3 = st.columns(3)
                _d1.metric("Standard", f"{_dur.get('standard_days',_dur.get('standard','?'))}d")
                _d2.metric("Range", f"{_dur.get('min_days','?')}–{_dur.get('max_days','?')}d")
                _d3.metric("IV / PO", f"IV:{_dur.get('iv_days',0)}d · PO:{_dur.get('po_days',0)}d")
                _dur_note = annotate_regimen_note(_dur.get('notes', ''), sir_map, lang="ar")
                if _dur_note:
                    st.info(f"📋 {_dur_note}")
                if _dur.get("follow_up_culture"):
                    st.warning("🔄 Follow-up culture recommended after treatment completion")
                st.caption(f"📚 {_dur.get('ref','')}")

            # ── ② Combination Therapy (auto if MDR phenotype) ────────
            # organism= restored 2026-08-21: without it, get_combination_therapy()'s
            # own intrinsic-resistance annotation block (`if organism and results:`)
            # never runs on THIS call site, even though run_analysis() passes it
            # correctly. Same defect class as the 2026-08-06 fix documented inside
            # that function -- a Colistin+Meropenem option could render for
            # Proteus/Providencia/Morganella/Serratia (intrinsically colistin-
            # resistant) with no annotation, on the exact screen a clinician reads.
            # test_pipeline.py never caught it because it exercises run_analysis()
            # directly, not this inline UI call -- see test_ui_combination_path.py.
            _combos = get_combination_therapy(
                phenotypes,
                is_pregnant=is_preg, age_years=age, age_months=age_months,
                is_renal=is_renal, cl_cr=cl_cr, is_hepatic=is_hepatic,
                organism=organism_type,
                carbapenemase_type=st.session_state.get("carb_type_now"),
            )
            if _combos:
                with st.expander(f"🔬 Combination Therapy ({len(_combos)} phenotype)", expanded=True):
                    st.caption("MDR/XDR combination therapy -- IDSA AMR Guidance 2026")
                    for _cs in _combos:
                        _pd = _cs["data"]
                        _urg = _pd["urgency"]
                        (st.error if _urg=="CRITICAL" else st.warning)(f"**{_urg}** -- {_pd['title']}")
                        for _op in _pd["options"]:
                            _avoid = "AVOID" in _op.get("evidence","") or "AVOID" in _op["combo"].upper()
                            if _avoid:
                                st.error(f"🚫 **{_op['combo']}** | {_op.get('caution','')}")
                            else:
                                with st.container(border=True):
                                    _ca, _cb = st.columns([3,1])
                                    with _ca:
                                        _hf = "  ⚠️" if _op.get("host_flagged") else ""
                                        st.markdown(f"**{_op['combo']}** -- {_op['evidence']}{_hf}")
                                        st.caption(_op["indication"])
                                        # A host contraindication is an error,
                                        # not a caption: these are the only
                                        # agents in the app that reach the
                                        # screen without passing the safety
                                        # gate, so the warning has to carry the
                                        # weight the gate would have.
                                        if _op.get("host_flagged"):
                                            st.error(_op.get("caution",""))
                                        elif _op.get("caution"):
                                            st.warning(_op["caution"])
                                    with _cb:
                                        st.caption(_op["ref"])

            # ── ③ IV -> PO Switch ──────────────────────────────────────
            with st.expander("💊 IV -> PO Switch Evaluation", expanded=False):
                st.caption("OPAT switch criteria -- IDSA 2019 | BNF 2025")
                _sw1, _sw2 = st.columns(2)
                with _sw1:
                    _sw_drug = st.selectbox("Current IV drug",
                        [""] + [d["name"] for d in allowed], key="sw_drug_sel")
                    _sw_days = st.number_input("Days on IV", min_value=0, max_value=30,
                        value=st.session_state.get("days_on_iv",3), key="sw_days_num")
                    st.session_state.days_on_iv = _sw_days
                with _sw2:
                    _sw_i = st.checkbox("Clinical improvement documented",
                        value=st.session_state.get("clinical_improving_48h",True), key="sw_i_chk")
                    _sw_o = st.checkbox("Tolerating oral medications",
                        value=st.session_state.get("tolerating_oral",True), key="sw_o_chk")
                    _sw_b = st.checkbox("No active bacteremia",
                        value=st.session_state.get("bacteremia_resolved",True), key="sw_b_chk")
                    st.session_state.clinical_improving_48h = _sw_i
                    st.session_state.tolerating_oral        = _sw_o
                    st.session_state.bacteremia_resolved    = _sw_b
                if _sw_drug:
                    _swr = evaluate_iv_po_switch(
                        drug_name=_sw_drug,
                        syndrome=syndrome_info["syndrome"] if syndrome_info else "",
                        clinical_improving=_sw_i, tolerating_oral=_sw_o,
                        bacteremia_resolved=_sw_b, days_on_iv=_sw_days,
                        organism=organism_type)
                    (st.success if _swr["can_switch"] else st.warning)(_swr["verdict"])
                    _sc1, _sc2 = st.columns(2)
                    with _sc1:
                        st.markdown("**✅ Supporting factors:**")
                        for _s in _swr["supporters"]: st.write(f"• {_s}")
                    with _sc2:
                        st.markdown("**⚠️ Blocking factors:**")
                        for _b in _swr["blockers"]: st.write(f"• {_b}")
                    st.caption(f"📚 {_swr['ref']}")
                else:
                    st.info("Select the current IV drug to evaluate switch criteria")

            # ── ④ Hepatic Dosing -- Child-Pugh ─────────────────────────
            if is_hepatic:
                with st.expander("🟡 Hepatic Dosing -- Child-Pugh", expanded=True):
                    st.caption("Dose adjustments in hepatic impairment -- BNF 2025 | Lexicomp 2025")
                    # The grade is read, not asked for again. A second selectbox
                    # writing the same session key from below the analysis call is
                    # the stale-state race that made this panel and the engine
                    # disagree on the same screen: the panel showed grade A advice
                    # while the engine had already banned on grade C, or the
                    # reverse. One widget, in the sidebar, before the analysis.
                    _cp = st.session_state.get("child_pugh_class", "C")
                    st.info(f"Evaluated as **Child-Pugh {_cp}** — change it in the "
                            f"sidebar, next to the Hepatic Impairment flag.")
                    _hr = get_hepatic_recommendations(allowed, _cp)
                    _act = [r for r in _hr if r["requires_action"]]
                    _nrm = [r for r in _hr if not r["requires_action"]]
                    if _act:
                        st.markdown("**⚠️ Adjustments required:**")
                        for _r in _act:
                            (st.error if "Avoid" in _r["level"] else st.warning)(
                                f"{'❌' if 'Avoid' in _r['level'] else '⚠️'} "
                                f"**{_r['name']}**: {_r['recommendation']} -- _{_r['note']}_")
                    if _nrm:
                        with st.expander(f"✅ {len(_nrm)} drugs: no hepatic adjustment needed"):
                            for _r in _nrm: st.caption(f"✅ {_r['name']}: {_r['recommendation']}")
                    if not _hr:
                        st.success("✅ No hepatic dose adjustments needed for current recommendations")
                    st.caption("📚 BNF 2025 | Lexicomp 2025 | UpToDate 2025")

            # ── ⑤ De-escalation Advisor ───────────────────────────────
            with st.expander("📉 De-escalation Advisor", expanded=False):
                st.caption("Antibiotic stewardship -- WHO AWaRe 2025 | IDSA Stewardship 2025")
                _de1, _de2 = st.columns(2)
                with _de1:
                    _de_h = st.number_input("Hours on current therapy",
                        min_value=0, max_value=336, step=12,
                        value=st.session_state.get("hours_on_treatment",72), key="de_h_num")
                    st.session_state.hours_on_treatment = _de_h
                with _de2:
                    _de_i = st.checkbox("Clinical improvement documented",
                        value=st.session_state.get("de_clinical_improving",True), key="de_i_chk")
                    st.session_state.de_clinical_improving = _de_i
                _der = evaluate_deescalation(
                    allowed=allowed, phenotypes=phenotypes,
                    hours_on_treatment=_de_h, clinical_improving=_de_i,
                    mdr_level=(mdr_result or {}).get("level"))
                if _der["can_deescalate"]: st.success("✅ De-escalation recommended")
                elif _de_h < 48: st.info("ℹ️ Complete 48h course before reassessment")
                else: st.warning("⚠️ Review required before de-escalation")
                for _rec in _der["recommendations"]: st.write(_rec)
                st.caption(f"📚 {_der['ref']}")

            st.divider()

            # ── Final verification checklist (2026-11-11) ───────────────────
            # One line per question a reviewer asks before release. Nothing
            # here decides anything new -- it re-checks what the engine did.
            st.markdown("### ✅ قائمة المراجعة النهائية")
            _is_urine_ck = classify_specimen(culture_type) == "urine"
            _gram_ck = st.session_state.get("patho_gram_sel" if _is_urine_ck else "np_gram_sel", "")
            _panel_ck = None
            if PANEL_COMPLETENESS_AVAILABLE and _check_panel_completeness_ext and sir_map:
                try:
                    _panel_ck = _check_panel_completeness_ext(organism_type, culture_type, sir_map)
                except Exception:
                    _panel_ck = None
            _ck_items = build_final_checklist(
                organism_type, culture_type, sir_map,
                allowed=allowed, warned=warned, banned=banned,
                qc_issues=(run_ast_qc(organism_type, sir_map, specimen=culture_type)
                           if sir_map else []),
                gram_stain=_gram_ck,
                patho_result=st.session_state.get("patho_result"),
                panel_result=_panel_ck,
                preg_warn=preg_warn_items,
            )
            _ck_sum = summarize_checklist(_ck_items)
            for _ck in _ck_items:
                _line = f"{CHECK_ICON[_ck['status']]} **{_ck['title']}** — {_ck['detail']}"
                if _ck["status"] == "fail":
                    st.error(_line)
                elif _ck["status"] == "warn":
                    st.warning(_line)
                elif _ck["status"] == "pass":
                    st.success(_line)
                else:
                    st.caption(_line)
            if _ck_sum["overall"] == "fail":
                st.error(f"❌ {_ck_sum['counts']['fail']} بند يحتاج مراجعة قبل إصدار التقرير.")
            elif _ck_sum["overall"] == "warn":
                st.warning(f"⚠️ لا أخطاء — {_ck_sum['counts']['warn']} بند يحتاج انتباه.")
            else:
                st.success("✅ كل بنود المراجعة سليمة.")
            st.divider()

            # ── Commercial Names Toggle ────────────────────────────────────────
            show_commercial = st.checkbox(
                "📋 إضافة الأسماء التجارية (Commercial Names) في التقرير؟",
                value=st.session_state.get("show_commercial_names", False),
                key="show_commercial_chk",
                help="يضيف أسماء العلامات التجارية بجانب كل مضاد حيوي في ملف TXT فقط"
            )
            st.session_state.show_commercial_names = show_commercial
            if show_commercial and not COMMERCIAL_NAMES:
                st.warning("⚠️ ملف `commercial_names.txt` غير موجود في مجلد البرنامج.")
            elif show_commercial:
                st.caption(f"✅ {len(COMMERCIAL_NAMES)} دواء مسجّل في قاموس الأسماء التجارية")

            # ── التقرير النصي -- cached to prevent lag on every keystroke ──────
            st.markdown("### 📋 التقرير السريري")

            _lab  = st.session_state.get("lab_name", "Your Lab Name")
            _city = st.session_state.get("lab_city", "")
            _pt   = patient_name.strip() or "غير محدد"

            # Hash all inputs that affect the report.
            # patho_result is serialized IN FULL (not just its score): its verdict,
            # factors_pos/neg and recommendations depend on UI inputs (culture
            # purity, symptoms, urinalysis, gram stain, host factors) that are NOT
            # otherwise present in this hash — so a score-only key leaves the report
            # stale whenever those change while the numeric score stays the same.
            _patho_sig = json.dumps(
                st.session_state.get("patho_result") or {},
                sort_keys=True, default=str, ensure_ascii=False,
            )
            # FIX 2026-11-11 (round 4): the buckets were hashed by their LENGTH.
            # Two different verdicts of equal size (a drug swapping between
            # caution and avoid after a Child-Pugh change, a novel agent's note
            # after a carbapenemase class was entered) kept the old report, and
            # current medications / interactions, allergies, Child-Pugh, the
            # carbapenemase class and the UTI syndrome were not hashed at all --
            # so adding warfarin left the interaction out of the report.
            def _bsig(items):
                return ";".join(
                    f"{i.get('name')}:{i.get('warning_reason') or i.get('category') or ''}"
                    f":{len(str(i.get('clinical_note') or i.get('preg_note') or ''))}"
                    for i in (items or []))
            _rpt_input_hash = hashlib.md5(
                f"{_pt}|{age}|{age_months}|{sex}|{weight}|{cl_cr}|{is_renal}|{is_preg}|{is_hepatic}"
                f"|{_child_pugh_now}|{sorted(current_meds or [])}|{sorted(allergies or [])}"
                f"|{_carb_type_now}|{_uti_syn_now}"
                f"|{organism_type}|{culture_type}|{colony_count}|{date_in}"
                f"|{pus_cells_text}|{rbcs_text}|{str(sorted(sir_map.items()))}"
                f"|{_bsig(allowed)}|{_bsig(warned)}|{_bsig(banned)}|{_bsig(preg_warn_items)}"
                f"|{sorted(interactions_alerts or [])}"
                f"|{show_commercial}|{_lab}|{_city}|{_patho_sig}".encode()
            ).hexdigest()[:16]

            if st.session_state.get("_rpt_hash") != _rpt_input_hash:
                _new_report = generate_report(
                    patient_name=_pt,
                    age=age, age_months=age_months, sex=sex, weight=weight,
                    cl_cr=cl_cr, is_renal=is_renal,
                    is_preg=is_preg, is_hepatic=is_hepatic,
                    allowed=allowed, warned=warned, banned=banned,
                    preg_warn_items=preg_warn_items,
                    organism=organism_type, specimen=culture_type,
                    interactions=interactions_alerts, sir_map=sir_map,
                    colony_count=colony_count,
                    date_in=str(date_in),
                    pus_cells=pus_cells_text,
                    rbcs=rbcs_text,
                    lab_name=_lab,
                    lab_city=_city,
                    patho_assessment=st.session_state.get("patho_result"),
                    show_commercial_names=show_commercial,
                )
                st.session_state._rpt_text = _new_report
                st.session_state._rpt_hash = _rpt_input_hash

            auto_report = st.session_state.get("_rpt_text", "")

            # معاينة للقراءة فقط
            if auto_report:
                st.text_area(
                    "نص التقرير",
                    value=auto_report,
                    height=300,
                    disabled=True,
                    label_visibility="collapsed",
                    key=f"rpt_{_rpt_input_hash}"
                )
                st.download_button(
                    "📥 تنزيل التقرير (TXT)",
                    data=auto_report,
                    file_name=(f"CDSS_{organism_type.replace(' ','_')}_"
                               f"{_pt.replace(' ','_')[:12]}_"
                               f"{datetime.now().strftime('%Y%m%d_%H%M')}.txt"),
                    mime="text/plain",
                    use_container_width=True,
                    type="primary",
                )

            # ── PDF Report ────────────────────────────────────────────
            st.markdown("---")
            st.markdown("#### 📄 PDF Clinical Report")

            _pdf_lang_col, _popt1, _popt2, _popt3 = st.columns([2,1,1,1])
            _pdf_lang  = _pdf_lang_col.radio(
                "Report Language",
                options=["ar", "en"],
                format_func=lambda x: "🌐 Arabic + English (Bilingual)" if x == "ar"
                                      else "🇬🇧 English Only",
                index=["ar","en"].index(st.session_state.get("pdf_lang","ar")),
                horizontal=True,
                key="pdf_lang_radio",
            )
            st.session_state.pdf_lang = _pdf_lang
            _pdf_combo = _popt1.checkbox("Combination",
                value=st.session_state.get("pdf_include_combo",True), key="pdf_cb_combo")
            _pdf_dur   = _popt2.checkbox("Duration",
                value=st.session_state.get("pdf_include_duration",True), key="pdf_cb_dur")
            _pdf_patho = _popt3.checkbox("Pathogenicity",
                value=st.session_state.get("pdf_include_patho",True), key="pdf_cb_patho")
            st.session_state.pdf_include_combo    = _pdf_combo
            st.session_state.pdf_include_duration = _pdf_dur
            st.session_state.pdf_include_patho    = _pdf_patho

            if WEASYPRINT_AVAILABLE:
                _cp_pdf  = st.session_state.get("child_pugh_class", "A")
                _sev_pdf = st.session_state.get("severity_level", "moderate")
                _lang_lbl = "English Only" if _pdf_lang == "en" else "Arabic + English"

                # FIX (#R2): input signature for the PDF so a stale PDF is never
                # offered for download after inputs change. Reuses the report hash
                # (identical clinical inputs) + PDF-specific toggles/options. The
                # '_pdf_hash' session slot existed but was never wired -> a PDF
                # generated for one patient/organism could be downloaded after the
                # inputs (and thus the filename) had already changed.
                _pdf_sig = (f"{_rpt_input_hash}|{_pdf_lang}|{_pdf_combo}|{_pdf_dur}"
                            f"|{_pdf_patho}|{_cp_pdf}|{_sev_pdf}")

                if st.button(f"🔄 Generate PDF ({_lang_lbl})", key="gen_pdf_btn",
                             use_container_width=True,
                             help="Click to generate report -- takes a few seconds"):
                    _dur_for_pdf = get_treatment_duration(
                        specimen=culture_type, organism=organism_type,
                        syndrome=duration_syndrome_key(syndrome_info, _uti_syn_now, culture_type),
                        age=age, sex=sex, is_renal=is_renal,
                        phenotypes=phenotypes, severity=_sev_pdf,
                    ) if _pdf_dur else None
                    # organism= restored 2026-08-21 -- see the matching note on
                    # the UI call site above. Same missing-organism defect, same
                    # consequence (Colistin/Proteus-class intrinsic annotation
                    # silently skipped), on the PDF a clinician downloads and keeps.
                    _combo_for_pdf = get_combination_therapy(
                        phenotypes,
                        is_pregnant=is_preg, age_years=age, age_months=age_months,
                        is_renal=is_renal, cl_cr=cl_cr, is_hepatic=is_hepatic,
                        organism=organism_type,
                        carbapenemase_type=st.session_state.get("carb_type_now"),
                    ) if _pdf_combo else None
                    _hep_for_pdf   = (get_hepatic_recommendations(allowed, _cp_pdf)
                                      if is_hepatic else None)
                    with st.spinner("جاري توليد التقرير PDF..."):
                        try:
                            _new_pdf = generate_pdf_html_report(
                                patient_name         = _pt,
                                age=age, sex=sex, weight=weight,
                                cl_cr=cl_cr, is_renal=is_renal,
                                is_preg=is_preg, is_hepatic=is_hepatic,
                                allowed=allowed, warned=warned, banned=banned,
                                preg_warn_items=preg_warn_items,
                                organism=organism_type, specimen=culture_type,
                                sir_map=sir_map,
                                interactions=interactions_alerts,
                                mdr_result=mdr_result,
                                esbl_result=esbl_result,
                                phenotypes=phenotypes,
                                colony_count=colony_count,
                                date_in=str(date_in),
                                pus_cells=pus_cells_text,
                                rbcs=rbcs_text,
                                lab_name=_lab,
                                lab_city=_city,
                                patho_assessment=(st.session_state.get("patho_result")
                                                  if _pdf_patho else None),
                                duration_data=_dur_for_pdf,
                                combo_suggestions=_combo_for_pdf,
                                show_commercial_names=show_commercial,
                                child_pugh=_cp_pdf,
                                hepatic_recs=_hep_for_pdf,
                                lang=_pdf_lang,
                            )
                            if _new_pdf:
                                st.session_state._pdf_bytes = _new_pdf
                                st.session_state._pdf_lang_used = _pdf_lang
                                st.session_state._pdf_hash = _pdf_sig
                                st.success("✅ PDF ready -- click download below")
                            else:
                                st.error("فشل توليد PDF -- تحقق من تثبيت weasyprint")
                        except Exception as _pdf_err:
                            st.error(f"خطأ في توليد PDF: {_pdf_err}")

                # Download button -- only when the cached PDF matches current inputs
                if (st.session_state.get("_pdf_bytes")
                        and st.session_state.get("_pdf_hash") == _pdf_sig):
                    _lang_suffix = "EN" if st.session_state.get("_pdf_lang_used") == "en" else "AR_EN"
                    st.download_button(
                        f"📄 Download PDF ({_lang_suffix})",
                        data=st.session_state._pdf_bytes,
                        file_name=(f"CDSS_{organism_type.replace(' ','_')}_"
                                   f"{_pt.replace(' ','_')[:12]}_"
                                   f"{_lang_suffix}_"
                                   f"{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"),
                        mime="application/pdf",
                        use_container_width=True,
                        type="secondary",
                    )
                elif st.session_state.get("_pdf_bytes"):
                    st.info("🔄 تغيّرت البيانات بعد آخر توليد للـ PDF — اضغط "
                            "**Generate PDF** لإصدار نسخة محدّثة مطابقة للبيانات الحالية.")
            else:
                st.info("أضف `weasyprint` إلى requirements.txt لتفعيل تصدير PDF")

            # ── صورة الملخص ──────────────────────────────────────────────────
            st.divider()
            st.markdown("### 🖼️ صورة ملخص الحالة")
            st.caption("تتحدث فوراً عند أي تغيير في البيانات")

            if PIL_AVAILABLE:
                # Hash-based cache: only regenerate when the DRAWN content changes.
                # Signatures below use actual content, not counts / wrong keys:
                #   • mdr_result -> 'level' (classify_mdr never returns
                #     'classification', so the old key was always empty),
                #   • phenotypes & esbl -> by content, not len,
                #   • the drug lists -> by content, not len (two different lists of
                #     equal length must produce different hashes),
                #   • referring physician / culture condition / microbiologist are
                #     drawn on the image but were previously absent from the hash.
                # weight is intentionally NOT hashed: it is passed to the drawing
                # function but never rendered, so hashing it would regenerate the
                # image on every weight keystroke for zero visual change.
                _ph_sig    = "/".join(sorted(p.get("phenotype", "") for p in (phenotypes or [])))
                _esbl_sig  = (f"{(esbl_result or {}).get('probability','')}"
                              f":{(esbl_result or {}).get('mechanism','')}")
                _lists_sig = "|".join([
                    ",".join(first_line_l),
                    ",".join(preferred_with_badge),
                    ",".join(use_caution_names),
                    ",".join(banned_names),
                    ",".join(reserve_names),
                    ",".join(notes),
                ])
                _img_input_hash = hashlib.md5(
                    f"{patient_name}|{age}|{age_months}|{sex}|{weight}|{cl_cr}|{is_renal}|{is_preg}"
                    f"|{organism_type}|{culture_type}|{colony_count}|{date_in}"
                    f"|{pus_cells_text}|{rbcs_text}|{str(sorted(sir_map.items()))}"
                    f"|{_lists_sig}"
                    f"|{mdr_result.get('level','')}|{_ph_sig}|{_esbl_sig}"
                    f"|{st.session_state.get('lab_name','')}|{st.session_state.get('lab_city','')}"
                    f"|{st.session_state.get('referring_physician','')}"
                    f"|{st.session_state.get('culture_condition','Aerobic')}"
                    f"|{st.session_state.get('microbiologist','')}"
                    .encode()
                ).hexdigest()[:16]

                if (st.session_state.get("_img_hash") != _img_input_hash
                        or not st.session_state.get("_img_bytes")
                        or st.session_state.get("_img_error")):
                    try:
                        _new_img = generate_decision_tree_image(
                            patient_name=patient_name.strip() or "غير محدد",
                            age=age, age_months=age_months, sex=sex, weight=weight,
                            cl_cr=cl_cr, is_renal=is_renal, is_preg=is_preg,
                            organism=organism_type, specimen=culture_type,
                            first_line=first_line_l,
                            preferred=preferred_with_badge,
                            use_caution=use_caution_names,
                            contraindicated=banned_names,
                            reserve=reserve_names,
                            notes=notes,
                            colony_count=colony_count,
                            date_in=str(date_in),
                            pus_cells=pus_cells_text,
                            rbcs=rbcs_text,
                            lab_name=st.session_state.get("lab_name", "Your Lab Name"),
                            lab_city=st.session_state.get("lab_city", ""),
                            mdr_result=mdr_result,
                            esbl_result=esbl_result,
                            phenotypes=phenotypes,
                            referring_physician=st.session_state.get("referring_physician",""),
                            culture_condition=st.session_state.get("culture_condition","Aerobic"),
                            microbiologist=st.session_state.get("microbiologist",""),
                        )
                        st.session_state._img_bytes = _new_img
                        st.session_state._img_hash  = _img_input_hash
                        st.session_state._img_error = False
                    except Exception as _img_err:
                        st.error(f"خطأ في توليد الصورة: {_img_err}")
                        st.session_state._img_error = True

                img_bytes = st.session_state.get("_img_bytes")
                if img_bytes:
                    st.image(img_bytes,
                             caption=f"Microbiology CDSS | {patient_name.strip() or organism_type} | {str(date_in)}",
                             use_container_width=True)

                    # أزرار التنزيل والطباعة
                    dl_col, pr_col = st.columns(2)
                    with dl_col:
                        st.download_button(
                            "📥 تنزيل الصورة (PNG -- Ultra HD)",
                            data=img_bytes,
                            file_name=f"Orange_ClinicalTree_{organism_type.replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
                            mime="image/png",
                            use_container_width=True,
                        )
                    with pr_col:
                        # زر الطباعة: يفتح الصورة في tab جديد -> Ctrl+P للطباعة
                        import base64 as _b64
                        b64 = _b64.b64encode(img_bytes).decode()
                        # نستخدم <a> بدل button لأن Streamlit يحجب onclick
                        print_html = f'<a href="data:image/png;base64,{b64}" target="_blank" style="display:block;text-align:center;padding:0.45rem 1rem;background:#1B4F9E;color:white;border-radius:8px;font-size:0.95rem;font-weight:600;text-decoration:none;line-height:2;">🖨️ فتح للطباعة (Ctrl+P)</a>' 
                        st.markdown(print_html, unsafe_allow_html=True)
                        st.caption("افتح الرابط ← Ctrl+P أو ⌘+P للطباعة")

            else:
                st.warning("⚠️ أضف `Pillow` لـ requirements.txt لتفعيل صورة الملخص.")

st.divider()
st.markdown("""
<div style="text-align:center;color:gray;font-size:0.9rem;">
  <strong>Developed by Dr / Hussein Ali | Orange Lab</strong><br>
  EUCAST Breakpoint Tables v16.1 | CLSI M100 Ed36 | IDSA AMR Guidance 2026 | BNF 2025 | Egypt National Guidelines
</div>
""", unsafe_allow_html=True)
