# -*- coding: utf-8 -*-
# © Dr. Hussein Ali — Orange Lab, 6 October City, Egypt
# Microbiology CDSS — All Rights Reserved
"""report_service.py — the three renderers: PDF, decision-tree image, text report.

WHY THIS FILE EXISTS
1,852 lines — a fifth of streamlit_app.py — spent on turning a finished analysis
into something a clinician can hold. It is presentation code with no clinical
decisions in it, and it was sitting in the same file as the decision engine,
which is how the render-layer defects of 2026-08-03 survived so long: every
safety-gate move printing a BLANK reason, and every hepatic or neonatal warning
printing RENAL dosing text instead of its own.

WHY IT IS WIRED RATHER THAN IMPORTED
These renderers need thirty-seven names from the monolith — classify_mdr,
predict_esbl, rank_sensitive_antibiotics, the AWaRe tables, the PIL and
WeasyPrint availability flags, the Arabic reshaper. A plain
`from streamlit_app import ...` would be circular: streamlit_app imports this
module, so this module cannot import it at load time.

The alternative was to rewrite 1,852 lines to reference an accessor object, and
rewriting that much working presentation code to achieve a tidier import graph
is a bad trade — the last time a bulk text edit ran across this codebase it put
a keyword argument on a function that did not accept it and no suite noticed.

So the dependency is INJECTED once, explicitly, by bind() below. The moved code
is byte-for-byte what it was. If a name is missing, bind() raises immediately at
import time with the name in the message, rather than failing later inside a PDF
render where the traceback would be forty frames deep.

WHAT LIVES HERE
    generate_pdf_html_report()      the full clinical PDF (WeasyPrint)
    generate_decision_tree_image()  the decision-tree PNG (Pillow)
    generate_report()               the plain-text report

None of them decides anything. They receive `allowed`, `warned`, `banned` and
the rest already computed by run_analysis(), and they must never re-derive a
clinical verdict — if a renderer disagrees with the engine, the renderer is
wrong by construction.
"""
from __future__ import annotations

import datetime as _datetime_mod
import io
import logging
import os as _os
import re
import re as _re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Injected by bind(). Declared here so the module reads honestly: these are
#    the monolith's, not this file's, and nothing works until bind() has run.
ABX_GUIDELINES: Dict = {}
ORGANISM_PROFILE: Dict = {}
MDR_INFO: Dict = {}
INFECTION_SYNDROMES: Dict = {}
RENAL_BAN_REASONS: Dict = {}
ARABIC_SUPPORT = False
PIL_AVAILABLE = False
WEASYPRINT_AVAILABLE = False
_arabic_reshaper_mod = None
_wp = None
Image = ImageDraw = ImageFont = None
classify_mdr = predict_esbl = rank_sensitive_antibiotics = None
crcl_label = resolve_crcl = preg_status_of = get_renal_severity = None
_drop_intrinsic = _hide_urine_only = _esc = _score_color = None
annotate_regimen_note = get_commercial_name = pdf_glyph_guard = None
normalize_abx_key = warned_note_for = None

# AST Panel Completeness -- a standalone module (like ast_reportability.py),
# not part of the monolith, so it is imported directly rather than through
# bind() below. Optional: absence must never break report generation, only
# silently drop this one section.
try:
    from ast_panel_completeness import check_panel_completeness as _check_panel_completeness_ext
    _PANEL_COMPLETENESS_AVAILABLE = True
except Exception:
    _check_panel_completeness_ext = None
    _PANEL_COMPLETENESS_AVAILABLE = False

_REQUIRED = (
    "ABX_GUIDELINES", "ORGANISM_PROFILE", "MDR_INFO", "INFECTION_SYNDROMES",
    "RENAL_BAN_REASONS", "ARABIC_SUPPORT", "PIL_AVAILABLE",
    "WEASYPRINT_AVAILABLE", "_arabic_reshaper_mod", "_wp",
    "Image", "ImageDraw", "ImageFont",
    "classify_mdr", "predict_esbl", "rank_sensitive_antibiotics",
    "crcl_label", "resolve_crcl", "preg_status_of", "get_renal_severity",
    "_drop_intrinsic", "_hide_urine_only", "_esc", "_score_color",
    "annotate_regimen_note", "get_commercial_name", "pdf_glyph_guard",
    "normalize_abx_key", "warned_note_for",
)


def bind(**names: Any) -> None:
    """Inject the monolith's names into this module's globals.

    Called ONCE from streamlit_app.py immediately after the renderers are
    imported. Raises on a missing name so the failure lands at import time with
    the name in the message, instead of forty frames deep inside a PDF render.
    """
    missing = [n for n in _REQUIRED if n not in names]
    if missing:
        raise RuntimeError(
            f"report_service.bind() is missing {missing}. Every renderer here "
            f"needs the monolith's tables and helpers; binding a partial set "
            f"would fail later, inside a render, where the traceback says "
            f"nothing useful."
        )
    globals().update(names)


def generate_pdf_html_report(
    patient_name: str, age: int, sex: str, weight: float,
    cl_cr: float, is_renal: bool, is_preg: bool, is_hepatic: bool,
    allowed: List[Dict], warned: List[Dict], banned: List[Dict],
    preg_warn_items: List[Dict], organism: str, specimen: str,
    sir_map: Dict[str, str], interactions: List[str],
    mdr_result: Dict, esbl_result: Dict, phenotypes: List[Dict],
    colony_count: str = "", date_in: str = "", pus_cells: str = "",
    rbcs: str = "", lab_name: str = "Your Lab Name", lab_city: str = "",
    patho_assessment: dict = None, duration_data: dict = None,
    combo_suggestions: list = None, show_commercial_names: bool = False,
    child_pugh: str = "", hepatic_recs: list = None,
    lang: str = "ar",
    return_html: bool = False,
) -> Optional[bytes]:
    # `return_html` exists so this document can be INSPECTED without WeasyPrint.
    # Added 2026-08-03: the function returns rendered bytes, so in any
    # environment without the renderer it returned None and the entire PDF
    # layer — 1,000 lines of it — was untestable. That is how the wrong-note
    # defect survived here after being fixed on screen the same day: no test
    # could read what the PDF actually said.
    if return_html:
        WEASYPRINT_REQUIRED = False
    elif not WEASYPRINT_AVAILABLE:
        return None

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── Language helpers ─────────────────────────────────────────────────
    _EN = lang == "en"

    # All bilingual strings used in this PDF
    _T = {
        # Section headers
        "recommended":   "Recommended Therapy -- Ranked"       if _EN else "Recommended Therapy -- Ranked",
        "avoid":         "Avoid / Contraindicated"            if _EN else "⊘ Avoid / Contraindicated",
        "dose_adj":      "⚠ Dose Adjustment / Use with Caution",
        "interactions":  "⊕ Drug Interactions",
        "pregnancy":     "⚠ Pregnancy -- Use with Caution",
        "preg_sub":      "(Physician decision required for all items below)",
        "treatment":     "Treatment Duration",
        "pathogenicity": "Pathogenicity Assessment",
        # Pregnancy inline notes
        "preg_extra":    "Additional options require caution in pregnancy -- see Pregnancy section below."
                         if _EN else "⚠ خيارات إضافية بحذر في الحمل -- راجع قسم Pregnancy بالأسفل.",
        "preg_only":     "All sensitive agents require caution in pregnancy -- see Pregnancy -- Use with Caution below."
                         if _EN else "⚠ جميع الخيارات الحساسة تتطلب حذراً في الحمل -- راجع قسم Pregnancy -- Use with Caution بالأسفل لاتخاذ القرار.",
        # Renal
        "renal_label":   "Patient CrCl" if _EN else "Patient CrCl",
        "renal_thresh":  "Threshold: CrCl ≤",
        "renal_adj":     "⚠ Renal dose adjustment required  |  Threshold: CrCl ≤",
        "intermediate":  "⚠ Intermediate (I) in culture result -- use only if no better option",
        # Patho
        "supporting":    "Supporting:",
        "against":       "Against:",
        "recs":          "Recommendations:",
        # Duration
        "protocol":      "Protocol",
        "standard":      "Standard",
        "range":         "Range",
        "iv_po":         "IV/PO Split",
        "follow_up":     "▣ Follow-up culture recommended after treatment",
        # Footer
        "disclaimer":    "Disclaimer: Clinical decision support only. Treatment decisions are the sole responsibility of the treating physician.",
        "references":    "References",
    }

    def _xlate_preg_note(note: str) -> str:
        """Translate Arabic preg_note to English for EN mode."""
        if not _EN or not note:
            return note
        import re as _re
        _arabic_re = _re.compile(r'[؀-ۿ]+')
        if not _arabic_re.search(note):
            return note   # already English

        # Known translations map
        _AR_EN = {
            "ممنوع في الحمل":                   "Contraindicated in pregnancy",
            "تحذير حمل":                         "Pregnancy caution",
            "مقبول في الحمل":                    "Acceptable in pregnancy",
            "آمن في الـ":                        "Safe in",
            "تجنّب في الـ":                      "Avoid in",
            "تجنّب":                             "Avoid",
            "يترسّب في عظام وأسنان الجنين":      "chelates into fetal bone and teeth",
            "تصبغ دائم للأسنان":                "permanent tooth discoloration",
            "تثبيط نمو العظام":                 "inhibited bone growth",
            "محظورة في كل مراحل الحمل":          "contraindicated throughout all trimesters",
            "خاصة بعد الأسبوع":                 "especially after week",
            "البديل":                           "Alternative",
            "بيانات بشرية محدودة":              "limited human data",
            "يعبر المشيمة":                     "crosses placenta",
            "سُمية للأذن الجنينية":             "fetal ototoxicity",
            "فقدان سمع دائم":                   "permanent hearing loss",
            "مضاد حمض الفوليك":                 "folate antagonist",
            "عيوب أنبوب عصبي":                  "neural tube defects",
            "يُفضل تجنبه":                      "prefer to avoid",
            "إن وُجد بديل آمن":                 "if a safer alternative exists",
            "مقبول في كل":                      "acceptable throughout all",
            "عند الضرورة":                      "when medically necessary",
            "القرار النهائي للطبيب المعالج":     "Final decision: treating physician",
            "حصراً":                            "exclusively",
            "خطر":                              "risk of",
            "خطر hemolytic anemia في الجنين":   "risk of fetal hemolytic anemia (G6PD)",
            "نيونيتل hemolysis عند الوليد":     "neonatal hemolysis",
            "البديل في 3rd trim":               "Alternative in 3rd trim",
            "جرعة واحدة":                       "(single dose)",
            "الأدلة الحديثة":                   "Recent evidence",
            "دحضت مخاوف":                       "refuted concerns about",
            "التشوهات القديمة":                 "historical malformation risk",
            "يُفضل تجنبه في الـ 1st trimester": "prefer to avoid in 1st trimester",
            "ارتبط بتشوهات خلقية":              "associated with congenital malformations",
            "الدراسات الحيوانية والبشرية":       "in animal and human studies",
            "أثبت سُمية جنينية في الحيوانات":   "demonstrated fetal toxicity in animal studies",
            "يُستخدم فقط عند انعدام البدائل":    "use only when no alternatives available",
            "يُستخدم عند الضرورة القصوى":        "use only when critically necessary",
            "مراقبة وظائف الكلى":               "monitor renal function",
            "السمع للأم والجنين":                "and fetal/maternal hearing",
            "Category C":                        "Category C",
            "Category B":                        "Category B",
            "عند الحاجة لكاربابينيم":           "when a carbapenem is needed",
            "يُفضل Meropenem":                  "Meropenem preferred",
            "عند تعذّر Meropenem":              "if Meropenem is unavailable",
            "nephrotoxicity":                    "nephrotoxicity",
            "يُستخدم فقط لإنقاذ الحياة":        "life-saving use only",
            "في XDR gram-negatives":            "for XDR gram-negative infections",
            "غياب أي بديل":                     "when no alternative exists",
            "تجنّب ما أمكن":                    "avoid whenever possible",
            "تجنّب في الـ 3rd trimester":        "avoid in 3rd trimester",
            "≥36 أسبوع":                        "≥36 weeks gestation",
            "ممنوع في الـ 1st trimester":        "contraindicated in 1st trimester",
            "ممنوع في كل الحمل":                "contraindicated throughout pregnancy",
            "لا يُعتبر خطاً أول":               "not a first-line agent",
            "أبداً في الحمل":                    "at any point in pregnancy",
            "خطر التشوهات أقل مما كان يُعتقد":  "teratogenicity risk lower than previously thought",
            "لا يُستخدم كخط أول":               "do not use as first-line",
            "فقط عند غياب البديل الأكثر أمانًا": "only when no safer alternative exists",
            "مقبول بجرعة واحدة":                "acceptable as single dose",
            "لـ uncomplicated UTI في الحمل":    "for uncomplicated UTI in pregnancy",
            "خيار مفضل على Nitrofurantoin":     "preferred over Nitrofurantoin",
            "1st trim":                          "1st trimester",
            "2nd trim":                          "2nd trimester",
            "3rd trim":                          "3rd trimester",
            "trimester":                         "trimester",
        }

        result = note
        for ar, en in _AR_EN.items():
            result = result.replace(ar, en)
        return result

    def _xlate_patho(text: str) -> str:
        """Translate Arabic pathogenicity text to English."""
        if not _EN or not text:
            return text
        import re as _re
        if not _re.compile(r'[؀-ۿ]').search(text):
            return text
        _PATHO_EN = {
            # Organism name carrying an Arabic parenthetical (EN report → Latin only)
            "Anaerobes (لاهوائيات)": "Anaerobes",
            "(لاهوائيات)": "",
            # Contaminant-tier interpretations / recommendations (were leaking Arabic)
            "يُنصح بإعادة أخذ العينة بتقنية صحيحة قبل البدء بالعلاج.":
                "Repeat specimen collection with proper technique before starting treatment.",
            "أعِد أخذ العينة مع تحسين التقنية.":
                "Repeat specimen collection with improved technique.",
            "لا تبدأ العلاج بناءً على هذه النتيجة وحدها.":
                "Do NOT start treatment based on this result alone.",
            "إذا تكرر العزل، فكّر في مصدر بديل (Hematogenous / Device).":
                "If the isolate recurs, consider an alternative source (Hematogenous / Device).",
            "المؤشرات تدعم التلوث أو الاستعمار بشكل كبير. العلاج غير مبرر في الغالب. تابع المريض كلينيكياً.":
                "Indicators strongly support contamination or colonization. Treatment is usually not justified. Follow up the patient clinically.",
            "لا تعطِ مضادات حيوية بناءً على هذه النتيجة.":
                "Do NOT give antibiotics based on this result.",
            "التزم بمبادئ Antibiotic Stewardship.":
                "Adhere to Antibiotic Stewardship principles.",
            "المؤشرات تدعم بقوة وجود عدوى حقيقية. يُنصح بالعلاج الموجَّه بنتيجة الحساسية مع مراعاة السياق الكلينيكي.":
                "Strong indicators of TRUE INFECTION. Culture-directed therapy is recommended, considering the clinical context.",
            "المؤشرات تدعم بقوة وجود عدوى حقيقية":
                "Strong indicators of true infection",
            "يُنصح بالعلاج الموجَّه بنتيجة الحساسية مع مراعاة السياق الكلينيكي":
                "Culture-directed therapy recommended based on clinical context",
            "ابدأ العلاج بناءً على نتيجة الـ AST.":
                "Initiate therapy based on AST results.",
            "ابدأ العلاج بناءً على نتيجة الـ AST":
                "Initiate therapy based on AST results",
            "راعِ شدة الأعراض وعوامل الخطر.":
                "Consider symptom severity and risk factors.",
            "راعِ شدة الأعراض وعوامل الخطر":
                "Consider severity and risk factors",
            "راجع الجرعة حسب الوظيفة الكلوية.":
                "Review dosing based on renal function.",
            "راجع الجرعة حسب الوظيفة الكلوية":
                "Review dosing based on renal function",
            "De-escalate بعد 48–72 ساعة إذا تحسّن المريض.":
                "De-escalate after 48–72 hours if patient improves.",
            "النتيجة حدودية. يُنصح بالتقييم الكلينيكي الكامل قبل البدء بالعلاج.":
                "Borderline result. Full clinical assessment recommended before initiating treatment.",
            "قد تحتاج فحوصات إضافية أو إعادة المزرعة.":
                "Additional workup or repeat culture may be needed.",
            "لا يُنصح بالعلاج إلا في الحامل أو قبل تدخل جراحي بولي.":
                "Treatment not recommended unless patient is pregnant or pre-urological procedure.",
            "المؤشرات تميل نحو التلوث أو الاستعمار.":
                "Indicators suggest contamination or colonization.",
            "ABU في سياق يستوجب العلاج (حمل / تدخل جراحي بولي).":
                "Asymptomatic Bacteriuria requiring treatment (pregnancy / pre-op).",
            "اختر مضاداً حيوياً مناسباً للحمل حسب نتيجة الحساسية.":
                "Select a pregnancy-appropriate antibiotic per sensitivity results.",
            "مدة العلاج 5–7 أيام عادةً.":
                "Treatment duration typically 5–7 days.",
            "أعِد المزرعة بعد الانتهاء من الدورة للتأكد من الشفاء.":
                "Repeat culture post-treatment to confirm clearance.",
            "العينة غير مناسبة":
                "Specimen inadequate",
            "ارفض العينة وأعِد طلب البلغم بتقنية صحيحة.":
                "Reject specimen and request repeat sputum with proper technique.",
            "قيّم المريض كلينيكياً قبل إعطاء المضادات الحيوية.":
                "Assess the patient clinically before giving antibiotics.",
            "فكّر في إعادة المزرعة إذا كان الوضع غير واضح.":
                "Consider repeating the culture if the situation is unclear.",
            "راجع نتيجة الـ Urinalysis / CRP / CBC إذا لم تكن متاحة.":
                "Review Urinalysis / CRP / CBC results if not available.",
            "النتيجة حدودية. يُنصح بالتقييم الكلينيكي الكامل قبل البدء بالعلاج. قد تحتاج فحوصات إضافية أو إعادة المزرعة.":
                "Borderline result. Full clinical assessment is recommended before starting treatment. Additional tests or repeat culture may be needed.",
            "أعِد تقييم المريض إذا استمرت الأعراض أو تطورت.":
                "Re-evaluate the patient if symptoms persist or progress.",
            "ابدأ العلاج التجريبي فوراً ريثما تظهر نتيجة الحساسية.":
                "Start empiric therapy immediately pending sensitivity results.",
            "احتجز المريض ومراقبته بشكل مكثف.":
                "Admit the patient for intensive monitoring.",
            "استثناءات: حمل -- قبيل جراحة بولية (Urology pre-op).":
                "Exceptions: pregnancy / pre-urological surgery.",
            "استشر طبيب الأمراض المعدية.":
                "Consult an infectious disease specialist.",
            "العينة من موقع معقم (CSF) -- أي نمو يُعدّ مرضياً بغض النظر عن العوامل الأخرى.":
                "Specimen from a sterile site (CSF) -- any growth is pathogenic regardless of other factors.",
            "تابع المريض وأعِد التقييم إذا ظهرت أعراض.":
                "Follow up and reassess if symptoms appear.",
            "تشير المعطيات إلى Asymptomatic Bacteriuria. وفقاً لـ IDSA 2019: لا يُنصح بالعلاج إلا في الحامل أو قبل تدخل جراحي بولي.":
                "Findings indicate Asymptomatic Bacteriuria. Per IDSA 2019: treatment not recommended except in pregnancy or before a urological procedure.",
            "لا تعطِ مضادات حيوية (Antibiotic Stewardship -- IDSA 2019).":
                "Do NOT give antibiotics (Antibiotic Stewardship -- IDSA 2019).",
        }
        result = text
        for ar, en in _PATHO_EN.items():
            result = result.replace(ar, en)

        # Word-level fallback for any remaining Arabic fragments
        # NOTE: a word-level Arabic->English dictionary (_WORD_EN) used to sit
        # here but was never wired in -- the regex strip below always ran instead.
        # It has been deleted rather than connected, because partial word
        # substitution produced half-translated "franco" text that is harder to
        # read than clean removal. What IS unsafe is deleting a clinical
        # recommendation with no trace, so the strip now logs what it dropped.
        # Safety net: strip any residual Arabic so the English report is
        # guaranteed to contain ZERO Arabic (and never franco-garbage from
        # partial word substitution). Complete phrases above are fully
        # translated; this only catches anything not yet mapped.
        if re.compile(r'[؀-ۿ]').search(result):
            _dropped = re.findall(r'[؀-ۿ\uFB50-\uFEFF]+(?:\s+[؀-ۿ\uFB50-\uFEFF]+)*', result)
            if _dropped:
                logger.warning(
                    "EN report: %d Arabic fragment(s) had no translation and were "
                    "removed -- add them to _PATHO_EN: %s",
                    len(_dropped), " | ".join(f[:60] for f in _dropped[:5]))
            result = re.sub(r'[؀-ۿ\uFB50-\uFEFF]+', '', result)
            result = re.sub(r'\(\s*\)', '', result)            # drop empty parens
            result = re.sub(r'\s+([.,;:،])', r'\1', result)     # tidy space before punct
            result = re.sub(r'\s{2,}', ' ', result).strip()
        return result

    # ── AWaRe helpers ────────────────────────────────────────────────────
    AWARE_CLR  = {"Access": "#1e8449", "Watch": "#b7770d", "Reserve": "#922b21"}
    AWARE_PILL = {"Access": "background:#1e8449;color:#fff",
                  "Watch":  "background:#b7770d;color:#fff",
                  "Reserve":"background:#922b21;color:#fff"}
    AWARE_CARD = {"Access": "background:#eafaf1;border:0.8pt solid #1e8449",
                  "Watch":  "background:#fef9e7;border:0.8pt solid #b7770d",
                  "Reserve":"background:#fdf2f2;border:0.8pt solid #922b21"}
    # NOTE: AWaRe class is NOT used as the therapy "line" anymore (see ranked loop
    # below) — Access!=first-line for a given site. Line labels come from the syndrome.

    # المصدر الموحّد للترتيب — نفس منطق الشاشة والصورة (الحساسية أولاً ثم
    # العينة ثم AWaRe ثم الطريق)، بدلاً من ترتيب AWaRe منفصل كان يعطي ترتيباً
    # مختلفاً عن الشاشة.
    ranked   = rank_sensitive_antibiotics(allowed, specimen, organism, sir_map, phenotypes)
    mdr_class = mdr_result.get("level","") if mdr_result else ""
    ph_labels = [p.get("phenotype","") for p in phenotypes]
    esbl_prob = esbl_result.get("probability","low")
    esbl_conf = esbl_result.get("confidence", 0) if esbl_result else 0
    # Header pills must reflect only confirmed/high-confidence findings —
    # weak/fallback inferences (e.g. "Possible MRSA" without Oxacillin/Cefoxitin
    # confirmation) stay in the body detail, not the prominent header badge.
    _WEAK_HEADER_PHENOTYPES = {"Possible MRSA"}
    _hdr_ph_labels = [p for p in ph_labels if p not in _WEAK_HEADER_PHENOTYPES]
    # Flags for Avoid-reason tagging (derived from passed-in results)
    _is_esbl_like     = esbl_prob in ("high", "ampc", "ampc_plasmid")
    _is_carbapenemase = esbl_prob in ("carbapenemase", "possible_carbapenemase")
    _is_mrsa          = any("MRSA" in str(p).upper() for p in ph_labels) \
                        or "mrsa" in str(organism).lower()

    def pill(txt, style):
        return f'<span style="padding:0.35mm 2.6mm;border-radius:2mm;font-size:8.5pt;font-weight:bold;{style}">{_esc(txt)}</span>'

    def _rnote(d):
        """Renal note in the report's language.

        EN reports must never fall back to the Arabic renal_note: the
        downstream Arabic strip would delete words like "تجنّب" (avoid) and
        "بعد" (after) mid-sentence, turning "(avoid 875mg)" into "(875mg)"
        and "+ dose after dialysis" into "+ dose dialysis".

        The two entries this used to hold back (Cefotaxime, Norfloxacin) held
        another drug's dose band and had renal_note_en blanked as a stopgap.
        That protected the English report only -- the ARABIC report, which is
        the one this lab issues, kept printing pip-tazo doses under Cefotaxime
        and co-amoxiclav doses under Norfloxacin. Both bands are now corrected
        at source, so the hold below is dormant. It stays as a net: any future
        entry with a deliberately blank renal_note_en shows an explicit hold
        rather than a silent gap or the wrong drug's dosing.
        """
        # ── Dose detail is withheld unless the patient is FLAGGED RENAL ─────
        # Requested 2026-08-03. A PDF is an issued document: it leaves the lab,
        # gets photographed, forwarded, and read weeks later by someone who
        # never saw the patient. Specific milligrams and intervals printed on a
        # report for a patient with NORMAL renal function are an invitation to
        # apply them to a different patient, or to the same patient after their
        # function has changed.
        #
        # What is withheld is the NUMBERS, not the fact. The reader is still
        # told the agent carries a renal threshold and what that threshold is,
        # so nobody concludes from a short line that no adjustment exists — the
        # dangerous reading. They are told where to get the figures.
        #
        # When is_renal is set, the full band prints: that is the patient the
        # numbers were computed for.
        _lim = d.get("renal_limit")
        if not is_renal:
            if isinstance(_lim, (int, float)) and _lim:
                if _EN:
                    return (f"Renally adjusted below CrCl {int(_lim)}. Specific "
                            f"doses are not printed for a patient not flagged "
                            f"as renally impaired — recheck if renal function "
                            f"changes and consult BNF 2025.")
                return (f"يحتاج تعديل الجرعة تحت CrCl {int(_lim)}. الجرعات "
                        f"التفصيلية لا تُطبع لمريض غير مُسجَّل بقصور كلوي — "
                        f"أعِد التقييم إذا تغيّرت الوظيفة الكلوية، وراجع BNF 2025.")
            return d.get("renal_note_en" if _EN else "renal_note", "") or ""

        if not _EN:
            return d.get("renal_note", "") or ""
        en = (d.get("renal_note_en") or "").strip()
        if en:
            return en
        if "renal_note_en" in d:
            return ("Renal dosing withheld -- entry flagged for clinical "
                    "verification. Consult BNF 2025.")
        return d.get("renal_note", "") or ""

    def _join_more(items, n):
        """Join first n items, then say how many were withheld."""
        items = [str(i) for i in (items or [])]
        head = ", ".join(items[:n])
        rest = len(items) - n
        return head + (f"  (+{rest} more)" if rest > 0 else "")

    def _clip(text, limit):
        """Word-boundary-safe truncation with a visible ellipsis.

        The previous code sliced clinical strings at a raw character index,
        which cut dose bands mid-number ('CrCl 40-6') and gave the reader no
        signal that anything had been dropped. This never splits a token and
        always marks the cut.
        """
        s = str(text or '')
        if len(s) <= limit:
            return s
        cut = s[:limit]
        sp = cut.rfind(' ')
        if sp > limit * 0.55:
            cut = cut[:sp]
        return cut.rstrip(' ,;.-') + '\u2026'
    # ── Compact CSS ──────────────────────────────────────────────────────
    CSS = """
@page {
    size: A4;
    margin: 6mm 10mm 8mm 10mm;
    @bottom-center {
        content: "Page " counter(page) " of " counter(pages) " | Microbiology CDSS | @@LABFOOT@@";
        font-size: 7.5pt; color: #7b8794;
        font-family: 'Noto Sans','Liberation Sans','DejaVu Sans', sans-serif;
    }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
/* ══ TYPE SYSTEM ═══════════════════════════════════════════════════════
   Serif sets prose, headings and the masthead (clinical/journal register).
   Sans sets numeric and tabular data (digit clarity in dense dose strings).
   Amiri is listed last in every stack and every Latin family ahead of it has
   zero Arabic coverage, so Arabic resolves to Amiri and nothing else does.
   Geometric symbols (✓ ✗ ⊘ ◆ ● ▣ ▲ ↻ ⊕) fall through to DejaVu Sans.        */
body { font-family: 'Noto Serif','Liberation Serif','Amiri','DejaVu Sans',serif;
       font-size: 9.3pt; line-height: 1.42; color: #1a1a2e; direction: ltr;
       background: #fff; -weasy-hyphens: none; }

/* Data faces — tabular figures so dose columns align and digits stay distinct */
.ast, .compact-tbl, .info4, .dose-grid, .ranked-row, .tier-sep,
.hdr-right, .hdr-lbl, .score-lbl {
    font-family: 'Noto Sans','Liberation Sans','Amiri','DejaVu Sans',sans-serif;
    font-variant-numeric: tabular-nums;
    -weasy-font-variant-numeric: tabular-nums;
}
/* Binomial names stay serif italic — scientific convention */
.hdr-org, i.sci { font-family:'Noto Serif','Liberation Serif',serif; font-style:italic; }
/* Arabic runs */
.rtl, .ar, .hdr-pt { font-family:'Amiri','Noto Naskh Arabic',serif; }
.ltr { direction: ltr; unicode-bidi: embed; display: inline; }
.rtl { direction: rtl; unicode-bidi: embed; }
/* Header — compact */
.hdr { background:#0d3b66; color:#fff; padding:2mm 8mm 1.5mm; display:flex;
       justify-content:space-between; align-items:center; }
.hdr-lab  { font-size:15.5pt; font-weight:bold; letter-spacing:0.35pt; }
.hdr-pt   { font-size:9pt; }
.hdr-org  { font-size:9.2pt; }
.hdr-sub  { font-size:8.6pt; color:#c3d3e4; margin-top:0.4mm; }
.hdr-pills { margin-top:0.7mm; }
.hdr-right { font-size:8.6pt; color:#edf3f9; text-align:right; direction:ltr; }
.hdr-lbl  { font-size:8pt; color:#9fb8d2; letter-spacing:0.5pt; }
.accent   { height:1mm; background:#ff8c00; }
.content  { padding: 0.5mm 0; }
/* Micro info grid */
.info4 { display: table; width: 100%; border-collapse: collapse; font-size:9pt; margin:1mm 0; }
.info4 tr td { padding: 1mm 2.5mm; border: 0.3pt solid #d5d8dc; }
.lbl4 { background:#f4f6f8; font-weight:bold; color:#0d3b66; width:14%; }
.val4 { width:22%; }
/* Section titles — tighter */
.sec-ttl { font-size:9.2pt; font-weight:bold; color:#0d3b66; text-transform:uppercase;
            letter-spacing:0.9pt; border-bottom:0.7pt solid #0d3b66;
            padding-bottom:0.4mm; margin:1.6mm 0 0.8mm;
            direction:ltr; text-align:left; }
/* AST table */
.ast { width:100%; border-collapse:collapse; font-size:8.8pt; direction:ltr; }
.ast th { background:#0d3b66; color:#fff; padding:1mm 2.5mm; text-align:left; font-size:8pt; }
.ast td { padding:1mm 2.5mm; border:0.3pt solid #d5d8dc; text-align:left; }
.ast tr:nth-child(even) td { background:#f8f9fa; }
.sir-s { color:#1e8449; font-weight:bold; }
.sir-i { color:#b7770d; font-weight:bold; }
.sir-r { color:#922b21; font-weight:bold; }
/* Two-column grid */
.pb { page-break-after: always; }
.grid2 { display:table; width:100%; border-spacing:1mm; border-collapse:separate; direction:ltr; }
.g2l { display:table-cell; width:49%; vertical-align:top; direction:ltr; text-align:left; }
.g2r { display:table-cell; width:49%; vertical-align:top; direction:ltr; text-align:left; }
/* Ranked rows — tighter */
.ranked-row { padding:1mm 2.5mm; margin:0.4mm 0; border-radius:1.5mm; direction:ltr; text-align:left;
              display:flex; justify-content:space-between; align-items:center; page-break-inside:avoid; }
.tier-sep { font-size:8.2pt; font-weight:bold; text-transform:uppercase; letter-spacing:0.3pt;
            direction:ltr; text-align:left;
            padding:0.2mm 0; margin-top:0.8mm; border-top:0.8pt solid; }
/* Alerts — tighter */
.alert { padding:1.1mm 2.8mm; border-radius:1.5mm; margin:0.5mm 0; font-size:9.2pt; direction:ltr; text-align:left; }
.al-warn   { background:#fef9e7; border:0.4pt solid #b7770d; color:#7d6608; }
.al-danger { background:#fdedec; border:0.4pt solid #922b21; color:#78281f; }
.al-info   { background:#eaf4fb; border:0.4pt solid #2980b9; color:#1a5276; }
.score-bar { background:#e5e7eb; border-radius:1.5mm; height:3mm; width:100%; }
.score-fill{ height:3mm; border-radius:1.5mm; }
.compact-tbl { width:100%; border-collapse:collapse; font-size:9.2pt; direction:ltr; }
.compact-tbl td { padding:0.8mm 2.5mm; border:0.3pt solid #d5d8dc; text-align:left; }
.compact-tbl .lbl { background:#f4f6f8; font-weight:bold; color:#0d3b66; width:40%; }
.warn-val  { color:#b7770d; font-weight:bold; }
.danger-val{ color:#922b21; font-weight:bold; }
.no-break  { page-break-inside: avoid; }
hr.dv { border:none; border-top:0.4pt solid #d5d8dc; margin:0.6mm 0; }
/* Safety net: long, unbreakable drug names must never overflow the A4 margin */
.content, .alert, .g2l, .g2r, .ranked-row > div { overflow-wrap:anywhere; }
.ranked-row > div { min-width:0; }
"""

    # ── Specimen short label for header (lab-report convention) ───────────
    SPECIMEN_SHORT = {
        "Urine":       "Urine C/S",
        "Blood":       "Blood C/S",
        "Sputum":      "Sputum C/S",
        "Wound Swab":  "Wound C/S",
        "Pus":         "Pus C/S",
        "Stool":       "Stool C/S",
        "CSF":         "CSF C/S",
    }
    specimen_short = SPECIMEN_SHORT.get(specimen, f"{specimen} C/S" if specimen else "")

    def hdr_html(page_lbl: str) -> str:
        mdr_pills = ""
        # MDR/XDR/PDR — deterministic category count (Magiorakos 2012), always shown
        if mdr_class: mdr_pills += pill(mdr_class, "background:#922b21;color:#fff")+" "
        # Resistance phenotypes (MRSA/VRE/CRE/CRAB/CRPA) — confirmed via direct AST
        # markers, always shown. Weak/fallback inferences already excluded upstream.
        for ph in _hdr_ph_labels[:3]: mdr_pills += pill(ph, "background:#6e2fa0;color:#fff")+" "
        # ESBL/AmpC/Carbapenemase — genuinely PREDICTED mechanisms (predict_esbl()).
        # Only surface in header when confidence is high; lower-confidence calls
        # remain available in the body detail, not as a prominent badge.
        if esbl_conf >= 70:
            if esbl_prob == "crpa":
                mdr_pills += pill("DTR-P.aeruginosa" if (esbl_result or {}).get("dtr") else "CR-P.aeruginosa",
                                  "background:#922b21;color:#fff" if (esbl_result or {}).get("dtr")
                                  else "background:#b7770d;color:#fff")
            elif esbl_prob in ("carbapenemase", "possible_carbapenemase"): mdr_pills += pill("CARBAPENEMASE","background:#922b21;color:#fff")
            elif esbl_prob in ("ampc", "ampc_plasmid"):        mdr_pills += pill("AmpC","background:#b7770d;color:#fff")
            elif esbl_prob in ("high","moderate"): mdr_pills += pill("ESBL+","background:#b7770d;color:#fff")
        _pills_html = ("<div class='hdr-pills'>" + mdr_pills + "</div>") if mdr_pills else ""
        return f"""<div class="hdr">
  <div>
    <div class="hdr-lab">{_esc(lab_name)}</div>
    <div class="hdr-sub">{_esc(lab_city)} &nbsp;|&nbsp; Microbiology CDSS</div>
    {_pills_html}
  </div>
  <div class="hdr-right">
    <b style="font-size:11pt">{_esc(specimen_short)}</b><br>
    <span class="hdr-lbl">{page_lbl}</span><br>
    {_esc(date_in or now_str[:10])}<br>
    <b class="hdr-pt">&#x2067;@@PTNAME@@&#x2069;</b><br>
    <span class="hdr-org">&#x2066;{_esc(organism)}&#x2069;</span>
  </div>
</div><div class="accent"></div><div class="content">"""

    # Resolve the footer lab-name token (see P1) -- quotes stripped so the
    # value cannot break out of the CSS content string.
    CSS = CSS.replace(
        "@@LABFOOT@@",
        (lab_name or "").replace('"', "").replace("\\", "")
    )

    H = []
    _doc_title = (
        f"{specimen_short or 'Culture'} Clinical Advisory"
        f" -- {organism or 'isolate'} -- {lab_name or 'Lab'}"
    )
    H.append(f"<!DOCTYPE html><html lang='en' dir='ltr'><head><meta charset='UTF-8'>"
             f"<title>{_esc(_doc_title)}</title>"
             f"<style>{CSS}</style></head><body>")

    # ════════════════════════════════════════════════════════════════
    # SINGLE PAGE: Clinical Decision Support
    # (Page 1 Patient/Culture/AST removed -- CDS only)
    # ════════════════════════════════════════════════════════════════
    H.append(hdr_html("CLINICAL ADVISORY"))
    H.append('<div class="content">')

    # ── RECOMMENDED THERAPY — RANKED (Page 1 — compact like orange_lab) ──────
    if ranked:
        H.append(f'<div class="sec-ttl">{_T["recommended"]}</div>')
        # ── Line-of-therapy label is SITE-SPECIFIC, not AWaRe ────────────────
        # AWaRe (Access/Watch/Reserve) is a stewardship/conservation class, NOT a
        # clinical preference rank for this infection. Using it as the "line" made an
        # Access aminoglycoside (Gentamicin) show as "First-line" for a Sputum case,
        # sitting *below* the actually-preferred Watch agents — clinically misleading.
        # The first-line set now comes from the syndrome table (curated per specimen,
        # e.g. Sputum -> Amox/Clav, Levofloxacin, Azithromycin). AWaRe stays only as
        # the row tint + pill on the right.
        # First-line set is ORGANISM-aware first (curated per organism), then falls
        # back to the specimen syndrome. This stops e.g. Azithromycin being labelled
        # "FIRST-LINE" for an Enterobacterales (macrolides aren't first-line for GNB),
        # even though the CAP syndrome lists it as an empiric first choice.
        _prof_fl = _drop_intrinsic(
            (ORGANISM_PROFILE.get(organism) or {}).get("first_line") or [], organism)
        _syn_fl  = INFECTION_SYNDROMES.get((specimen, None), {})
        _fl_src  = _prof_fl or (_syn_fl.get("first_choice") or [])
        _fl_norm = {normalize_abx_key(n) for n in _fl_src}
        prev_tier = ""
        # If AST + safety filtering left NO curated first-line agent standing,
        # labelling every surviving row "ALTERNATIVE" leaves the document with
        # no primary recommendation. Detect that and promote the top row.
        _fl_survives = any(
            normalize_abx_key(_r.get("name","")) in _fl_norm for _r in ranked
        ) if _fl_norm else False
        for i, _rd in enumerate(ranked, 1):
            _raw  = _rd.get("aware","")
            _nm_norm = normalize_abx_key(_rd.get("name",""))
            if _fl_norm and _fl_survives:
                _tlbl = "FIRST-LINE" if _nm_norm in _fl_norm else "ALTERNATIVE"
            else:                                   # no curated syndrome list -> rank by position
                _tlbl = "PRIMARY" if i == 1 else "ALTERNATIVE"
            _clr  = AWARE_CLR.get(_raw,"#444")      # drug name + pill colour = AWaRe (stewardship)
            _hclr = "#1e8449" if _tlbl in ("FIRST-LINE", "PRIMARY") else "#0d3b66"  # header colour = line
            _ccss = AWARE_CARD.get(_raw,"")
            _sirv = sir_map.get(_rd.get("name",""),"S")
            _rte  = "PO" if _rd.get("high_po") else "IV/IM"
            _rnl  = _esc(_rnote(_rd)) if is_renal else ""
            if _tlbl != prev_tier:
                H.append(f'<div class="tier-sep" style="color:{_hclr};border-color:{_hclr}">{_tlbl}</div>')
                prev_tier = _tlbl
            H.append(
                f'<div class="ranked-row" style="{_ccss};border-radius:1.5mm;padding:1mm 2.5mm;margin:0.3mm 0">'
                '<div style="flex:1;min-width:0;overflow-wrap:anywhere">'
                f'<b style="font-size:10.5pt;color:{_clr}">{i}. {_esc(_rd.get("name",""))}</b>'
                f'&ensp;<span class="ltr" style="background:#fff;border:0.4pt solid {_clr};color:{_clr};'
                f'font-size:8.5pt;padding:0.3mm 2.5mm;border-radius:1mm">{_sirv}</span>'
                f'&ensp;<span style="font-size:8.5pt;color:#555">{_rte}</span>'
                + (f'&ensp;<small style="color:#b7770d">⚠ {_rnl}</small>' if _rnl else "")
                + '</div>'
                f'<div>{pill(_raw, AWARE_PILL.get(_raw,""))}</div>'
                '</div>'
            )
        if is_preg and preg_warn_items:
            H.append('<div style="font-size:8.2pt;color:#6c3483;margin-top:0.5mm">'
                     f'{_T["preg_extra"]}</div>')
    else:
        H.append(f'<div class="sec-ttl">{_T["recommended"]}</div>')
        if is_preg and preg_warn_items:
            H.append(f'<div class="alert al-info" style="font-size:8.4pt">{_T["preg_only"]}</div>')
        else:
            H.append('<div class="alert al-info" style="font-size:8.4pt">'
                     'No clear first-line options — see Caution / Pregnancy sections below.</div>')

    # ── AVOID -- each drug with its specific reason ────────────────────────
    if banned:
        def _ban_reason(bd):
            cat = bd.get("category", "")
            nm  = bd.get("name", "")
            _sir = sir_map.get(nm, "")
            _info_lookup = ABX_GUIDELINES.get(nm, {})
            _cls = (_info_lookup.get("class", "") or "").lower()
            # 1. Resistant in culture (explicit R)
            if cat == "resistant" or _sir == "R":
                return ('✗ (R)', '#922b21')
            # 2. Pregnancy contraindication
            if cat == "pregnancy":
                return ('⊘ Pregnancy', '#7d3c98')
            # 3. Pediatric / child
            if cat in ("child", "pediatric"):
                return ('⊘ Pediatric', '#7d3c98')
            # 4. Renal
            if cat == "renal":
                return ('⚠ Renal', '#b7770d')
            # 5. Organism-based (MRSA / ESBL / AmpC / Carbapenemase / intrinsic)
            if cat == "organism":
                _is_betalactam = any(k in _cls for k in
                                     ("penicillin", "cephalosporin", "carbapenem"))
                # MRSA: detected + beta-lactam
                if _is_mrsa and _is_betalactam:
                    return ('⚠ MRSA -- β-lactam', '#922b21')
                # Carbapenemase
                if _is_carbapenemase and _is_betalactam:
                    return ('⚠ Carbapenemase', '#922b21')
                # ESBL/AmpC suppression of penicillins+cephalosporins
                if _is_esbl_like and _is_betalactam:
                    return ('⚠ ESBL Concern', '#b7770d')
                # Otherwise intrinsic resistance
                return ('⚠ Intrinsic R', '#922b21')
            return ('✗ Avoid', '#922b21')

        H.append(
            '<div class="sec-ttl" style="margin-top:1mm;color:#922b21;border-bottom-color:#922b21">'
            f'{_T["avoid"]}</div>'
        )
        _avoid_rows = []
        for _bd in banned:
            _nm   = _esc(_bd.get("name",""))
            _tag, _clr = _ban_reason(_bd)
            _avoid_rows.append(
                f'<span style="display:inline-block;margin:0.3mm 1mm 0.3mm 0;'
                f'padding:0.2mm 2mm;background:#fff;border:0.4pt solid {_clr};'
                f'border-radius:1.5mm;font-size:8pt;max-width:90mm;overflow-wrap:anywhere;vertical-align:top">'
                f'<b style="color:#1a1a2e">{_nm}</b> '
                f'<span style="color:{_clr};font-size:8.2pt">{_tag}</span></span>'
            )
        H.append(
            f'<div class="alert al-danger" style="font-size:8.5pt;line-height:1.6">'
            f'{"".join(_avoid_rows)}</div>'
        )
        # Pregnancy-banned — separate line for clarity
        _preg_banned = [_bd for _bd in banned if _bd.get("category") == "pregnancy"]
        if _preg_banned and is_preg:
            _pb_names = ", ".join(_esc(_bd["name"]) for _bd in _preg_banned)
            H.append(
                '<div class="alert al-danger" style="font-size:8.5pt;margin-top:1mm">'
                f'⊘ <b>Pregnancy Contraindicated:</b> {_pb_names}</div>'
            )

    # ── DOSE ADJUSTMENT / USE WITH CAUTION -- compact chip grid ──────────
    if warned:
        H.append('<div class="sec-ttl" style="margin-top:0.6mm;color:#b7770d;border-bottom-color:#b7770d">'
                 f'{_T["dose_adj"]}</div>')
        # Shared notes (renal / intermediate) stated ONCE here instead of
        # repeating under every single drug below.
        _sub_notes = []
        if is_renal:
            _sub_notes.append(f'Patient CrCl = {crcl_label(cl_cr, is_renal)}')
        if any(_wd.get("warning_reason") == "intermediate_culture" for _wd in warned):
            _sub_notes.append('⚠ Intermediate (I) in culture -- use only if no better option')
        if _sub_notes:
            H.append('<div style="font-size:8.2pt;color:#7d6608;margin-bottom:1mm">'
                     + ' &nbsp;·&nbsp; '.join(_sub_notes) + '</div>')

        H.append('<div class="dose-grid" style="display:flex;flex-wrap:wrap;gap:1mm;align-items:stretch">')
        for _wd in warned:
            _wname = _esc(_wd.get("name",""))
            _waw   = _esc(_wd.get("aware",""))
            _wreason = _wd.get("warning_reason","")
            _waw_style = {
                "Access":  "background:#1e8449;color:#fff",
                "Watch":   "background:#b7770d;color:#fff",
                "Reserve": "background:#922b21;color:#fff",
            }.get(_wd.get("aware",""), "background:#888;color:#fff")

            # Reason-specific detail -- "intermediate_culture" is skipped here
            # since it's already covered once by the shared note above.
            _detail = ""
            if _wreason == "renal_adjustment":
                _rl = _wd.get("renal_limit","-")
                _rn = _esc(_rnote(_wd))
                _detail = f'Renal dose adjustment required | Threshold: CrCl \u2264 {_rl} ml/min' + (f' -- {_rn}' if _rn else '')
            elif _wreason in ("esbl_bli_uti_only", "possible_carbapenemase"):
                _esbl_txt = (_wd.get("esbl_note_en") if _EN and _wd.get("esbl_note_en")
                             else _wd.get("esbl_note","ESBL organism -- BLI combo for uncomplicated UTI only"))
                _detail = _esc(_esbl_txt)
            elif _wreason == "intermediate_culture":
                # Never leave the card body empty -- a blank card next to cards
                # carrying a renal caveat reads as "nothing to adjust here".
                _detail = ('Intermediate (I) on AST \u2014 use only if no better '
                           'option; maximise dose/exposure.')
                _rn_i = _esc(_rnote(_wd))
                if _rn_i:
                    _detail += f' Renal: {_rn_i}'
            else:
                # FIX 2026-08-03. This branch used to fall through to _rnote(),
                # i.e. the RENAL note, for every warning reason it did not name
                # explicitly — hepatic, safety-gate, neonatal, possible-MRSA.
                # It is the identical defect that was found and fixed in the
                # on-screen renderer the same day, and it survived here because
                # the two renderers each had their own if/else instead of one
                # resolver. A Child-Pugh C caution printed renal dosing; a CSF
                # gate refusal printed "no renal adjustment required" — a
                # reassuring sentence under a refusal.
                #
                # warned_note_for() is now the SINGLE resolver for both, injected
                # through bind(). If a reason has no branch there it returns ""
                # rather than substituting an unrelated note, and the card below
                # says so explicitly instead of printing something false.
                _detail = _esc(warned_note_for(_wd, "en" if _EN else "ar"))
                if not _detail:
                    _detail = _esc(_wd.get("note", "")) or (
                        "Caution recorded with no explanation attached — "
                        "review manually." if _EN else
                        "تحذير بلا تفسير مسجَّل — راجِع النتيجة يدوياً.")

            H.append(
                # flex:1 1 42mm -> chips grow to fill each row evenly (fixes poor
                # distribution when few drugs); min-width forces a clean wrap; max-width
                # keeps a lone chip from spanning the whole page; overflow:hidden +
                # word wrapping on the name stop long drug names spilling past the
                # right margin.
                '<div style="flex:1 1 42mm;min-width:40mm;max-width:92mm;padding:0.5mm 2mm;'
                'border-radius:1.5mm;background:#fef9e7;border:0.5pt solid #b7770d;'
                'overflow:hidden;page-break-inside:avoid">'
                '<div style="display:flex;justify-content:space-between;align-items:center;gap:1.5mm;min-width:0">'
                f'<b style="font-size:9pt;color:#6b5806;min-width:0;overflow-wrap:anywhere;word-break:break-word">{_wname}</b>'
                '<span style="padding:0.2mm 1.8mm;border-radius:1.5mm;font-size:7pt;flex:0 0 auto;'
                f'font-weight:bold;white-space:nowrap;{_waw_style}">{_waw}</span>'
                '</div>'
                + (f'<div style="font-size:8pt;color:#4a4a4a;margin-top:0.4mm;line-height:1.35;overflow-wrap:anywhere">{_detail}</div>'
                   if _detail else '')
                + '</div>'
            )
        H.append('</div>')

    # ── Interactions (compact) ─────────────────────────────────────────
    # SILENT-TRUNCATION FIX: this used to print `interactions[:4]`, so on a
    # hepatic patient with several flagged agents the 5th warning onwards simply
    # never appeared in the document the physician actually reads -- and nothing
    # told anyone it had been dropped. All items are now printed; if the list is
    # long the overflow is condensed onto one line rather than discarded.
    if interactions:
        _ia_all = list(interactions)
        _ia_head, _ia_tail = _ia_all[:6], _ia_all[6:]
        _rows = [f'<span style="font-size:9pt">{_esc(ia)}</span>' for ia in _ia_head]
        if _ia_tail:
            _rows.append('<span style="font-size:8pt">+ '
                         + _esc(" · ".join(_ia_tail)) + '</span>')
        H.append(f'<div class="sec-ttl" style="margin-top:0.6mm">{_T["interactions"]}</div>'
                 '<div class="alert al-warn">' + '<br>'.join(_rows) + '</div>')

    # 2-column equal — Treatment Duration LEFT, Pathogenicity RIGHT
    H.append('<div class="grid2" style="margin-top:0.6mm">')

    # ── Treatment Duration (now left column) ──────────────────────────────
    H.append('<div class="g2l">')
    if duration_data:
        d = duration_data
        H.append('<div class="sec-ttl">Treatment Duration</div>')
        std = d.get("standard_days", d.get("standard","?"))
        H.append('<table class="compact-tbl">'
                 f'<tr><td class="lbl">Protocol</td><td>{_esc(d.get("label",""))}</td></tr>'
                 f'<tr><td class="lbl">Standard</td><td><b style="font-size:12pt">{std} days</b></td></tr>'
                 f'<tr><td class="lbl">Range</td><td>{d.get("min_days","?")}–{d.get("max_days","?")} days</td></tr>'
                 f'<tr><td class="lbl">IV/PO Split</td><td class="ltr">IV:{d.get("iv_days",0)}d · PO:{d.get("po_days",0)}d</td></tr>'
                 '</table>')
        if d.get("notes"):
            _note = annotate_regimen_note(d["notes"], sir_map, lang=lang)
            H.append(f'<div class="alert al-info" style="font-size:8pt;margin-top:0.5mm">▣ {_esc(_clip(_note, 400))}</div>')
        if d.get("follow_up_culture"):
            H.append('<div class="alert al-warn" style="font-size:8.5pt">↻ Follow-up culture recommended after treatment</div>')
        H.append(f'<div style="font-size:8.4pt;color:#7b8794;margin-top:1.2mm">§ {_esc(d.get("ref",""))}</div>')
    else:
        H.append('<div class="sec-ttl">Treatment Duration</div>')
        H.append('<div class="alert al-info" style="font-size:9pt">Select severity level to see treatment duration</div>')
    H.append('</div>')

    # ── Pathogenicity (now right column, expanded) ────────────────────────
    H.append('<div class="g2r">')
    if patho_assessment:
        sc     = patho_assessment.get("score",0)
        verd   = _esc(patho_assessment.get("verdict",""))
        interp = _esc(_xlate_patho(patho_assessment.get("interpretation","")))
        flags  = patho_assessment.get("special_flags",[])
        recs   = [_esc(_xlate_patho(r)) for r in patho_assessment.get("recommendations",[])]
        fpos   = patho_assessment.get("factors_pos",[])
        fneg   = patho_assessment.get("factors_neg",[])
        clr2   = _score_color(sc)

        H.append('<div class="sec-ttl">Pathogenicity Assessment</div>')
        # Score bar
        H.append(f'<div class="score-bar"><div class="score-fill" '
                 f'style="width:{sc}%;background:{clr2}"></div></div>')
        H.append(f'<div style="font-size:10pt;margin:0.5mm 0;font-weight:bold;color:{clr2}">{sc}% — {verd}</div>')
        # Interpretation
        if interp:
            H.append(f'<div style="font-size:9pt;color:#444;margin-bottom:0.5mm">{_clip(interp, 240)}</div>')
        # Flags
        flag_msgs = {
            "ABU_NO_TREAT":  ("al-warn",   "ABU -- Do NOT Treat (IDSA 2019)"),
            "ABU_TREAT":     ("al-danger", "ABU -- TREAT (High-risk)"),
            "MW_REJECT":     ("al-danger", "Specimen REJECTED -- Repeat"),
            "MW_ADEQUATE":   ("al-info",   "Murray-Washington: Adequate"),
            "SIRS_HIGH":     ("al-danger", "SIRS ≥3 -- Sepsis Probable"),
            "PEDIATRIC_UTI": ("al-info",   "Pediatric threshold applied"),
            # Added 2026-08-01: an unread colony count used to contribute a
            # silent zero. It now contributes nothing AND says so, because a
            # verdict built on a field nobody filled in should not look the
            # same as one built on a real reading.
            "CFU_NOT_REPORTED": ("al-warn",
                                 "Colony count not reported / unreadable -- "
                                 "excluded from the score"),
        }
        for fl, (cls, msg) in flag_msgs.items():
            if fl in flags:
                H.append(f'<div class="alert {cls}" style="font-size:8.5pt;margin:0.3mm 0">{msg}</div>')
        # Supporting factors (compact)
        if fpos:
            H.append(f'<div style="font-size:8.5pt;color:#1e8449;margin-top:1mm"><b>{_T["supporting"]}</b></div>')
            for f in fpos[:3]:
                H.append(f'<div style="font-size:8.5pt;color:#1e8449">{_esc(_clip(_xlate_patho(f), 120))}</div>')
        # Against factors
        if fneg:
            H.append(f'<div style="font-size:8.5pt;color:#b7770d;margin-top:0.5mm"><b>{_T["against"]}</b></div>')
            for f in fneg[:3]:
                H.append(f'<div style="font-size:8.5pt;color:#b7770d">{_esc(_clip(f, 120))}</div>')
        # Recommendations
        if recs:
            H.append(f'<div style="font-size:8.5pt;font-weight:bold;margin-top:0.5mm">{_T["recs"]}</div>')
            for r in recs[:3]:
                H.append(f'<div style="font-size:8.5pt">• {_clip(r, 150)}</div>')
    else:
        # Non-urine: show ESBL / MDR / resistance summary instead of pathogenicity
        _is_urine_pdf = "urine" in (specimen or "").lower()
        if _is_urine_pdf:
            H.append('<div class="sec-ttl">Pathogenicity Assessment</div>')
            H.append('<div class="alert al-info" style="font-size:9pt">Run Pathogenicity Assessment in the app to see score</div>')
        else:
            H.append('<div class="sec-ttl">Organism Resistance Profile</div>')
            # ESBL / Mechanism
            if esbl_result and esbl_result.get("probability") not in ("low", None):
                _ep3 = esbl_result.get("probability")
                _em3 = _esc(esbl_result.get("mechanism", ""))
                _ec3 = esbl_result.get("confidence", 0)
                _ed3 = _esc(esbl_result.get("detail",""))
                if _ep3 == "carbapenemase":
                    H.append(f'<div class="alert al-danger" style="font-size:8.5pt"><b>▲ {_em3}</b> ({_ec3}%)</div>')
                    H.append(f'<div style="font-size:8pt;color:#922b21">{_clip(_ed3, 200)}</div>')
                elif _ep3 in ("high","ampc"):
                    _l3 = "AmpC β-Lactamase" if _ep3 == "ampc" else "ESBL Producer"
                    H.append(f'<div class="alert al-danger" style="font-size:8.5pt"><b>⚠ {_l3}</b> ({_ec3}%) — {_em3}</div>')
                    H.append(f'<div style="font-size:8pt;color:#555">{_clip(_ed3, 200)}</div>')
                elif _ep3 == "moderate":
                    H.append(f'<div class="alert al-warn" style="font-size:8.5pt"><b>◆ ESBL Suspected</b> ({_ec3}%)</div>')
                    H.append(f'<div style="font-size:8pt;color:#555">{_clip(_ed3, 200)}</div>')
            # MDR level
            if mdr_result and mdr_result.get("level"):
                _ml3 = mdr_result["level"]
                _mi3 = MDR_INFO.get(_ml3, {})
                _clr3 = "#922b21" if _ml3 in ("XDR","PDR") else "#b7770d"
                H.append(f'<div style="font-size:9pt;font-weight:bold;color:{_clr3};margin-top:1mm">'
                         f'{_mi3.get("icon","")} {_mi3.get("label","")}</div>')
                H.append(f'<div style="font-size:8pt;color:#555">'
                         f'Resistant {mdr_result["resistant_count"]}/{mdr_result["total_tested"]} categories: '
                         f'{_esc(_join_more(mdr_result.get("resistant_categories",[]), 6))}</div>')
            # Phenotypes
            if phenotypes:
                for _ph3 in phenotypes[:3]:
                    _phn3 = _esc(_ph3.get("phenotype",""))
                    H.append(f'<div style="font-size:8.5pt;color:#6e2fa0;margin-top:0.5mm">◆ {_phn3}</div>')
            # No resistance info → show full Susceptibility Summary
            if (not esbl_result or esbl_result.get("probability") in ("low", None)) \
               and not (mdr_result and mdr_result.get("level")) \
               and not phenotypes:
                H.append('<div class="sec-ttl">Susceptibility Summary</div>')
                # ── AST stats ──────────────────────────────────────────────────
                _s_n = sum(1 for v in sir_map.values() if v == "S")
                _i_n = sum(1 for v in sir_map.values() if v == "I")
                _r_n = sum(1 for v in sir_map.values() if v == "R")
                _tot = len(sir_map)
                _gram_txt = ("Gram-positive organism"
                             if (mdr_result or {}).get("gram") == "positive"
                             else "Gram-negative organism"
                             if (mdr_result or {}).get("gram") == "negative"
                             else "")
                _access_n = sum(1 for d in allowed if d.get("aware") == "Access")
                _watch_n  = sum(1 for d in allowed if d.get("aware") == "Watch")
                _res_n    = sum(1 for d in allowed if d.get("aware") == "Reserve")
                _aware_str = (
                    (f"{_access_n} Access" if _access_n else "")
                    + (" · " if _access_n and (_watch_n or _res_n) else "")
                    + (f"{_watch_n} Watch" if _watch_n else "")
                    + (" · " if _watch_n and _res_n else "")
                    + (f"{_res_n} Reserve" if _res_n else "")
                )
                # Score bar colour: green if >60% sensitive
                _pct_s = int(_s_n / _tot * 100) if _tot else 0
                _bar_clr = "#1e8449" if _pct_s >= 60 else "#b7770d" if _pct_s >= 40 else "#922b21"
                H.append(
                    f'<div class="score-bar" style="margin:1mm 0">'
                    f'<div class="score-fill" style="width:{_pct_s}%;background:{_bar_clr}"></div></div>'
                )
                H.append(
                    '<table style="width:100%;border-collapse:collapse;font-size:9pt;margin-top:0.5mm">'
                    f'<tr><td style="padding:0.5mm 1mm;color:#1e8449">✓ Sensitive</td>'
                    f'<td style="padding:0.5mm 1mm;font-weight:bold;color:#1e8449">{_s_n} agents</td>'
                    f'<td style="padding:0.5mm 1mm;font-size:8pt;color:#888">{_pct_s}%</td></tr>'
                    + (f'<tr><td style="padding:0.5mm 1mm;color:#b7770d">● Intermediate</td>'
                       f'<td style="padding:0.5mm 1mm;font-weight:bold;color:#b7770d">{_i_n} agent{"s" if _i_n!=1 else ""}</td>'
                       f'<td></td></tr>' if _i_n else "")
                    + f'<tr><td style="padding:0.5mm 1mm;color:#922b21">✗ Resistant</td>'
                      f'<td style="padding:0.5mm 1mm;font-weight:bold;color:#922b21">{_r_n} agent{"s" if _r_n!=1 else ""}</td>'
                      f'<td></td></tr>'
                    '</table>'
                )
                H.append('<hr class="dv" style="margin:0.8mm 0">')
                if _gram_txt:
                    H.append(f'<div style="font-size:9pt;color:#1a1a2e;margin:0.3mm 0">'
                             f'● {_gram_txt}</div>')
                H.append(f'<div style="font-size:9pt;color:#0d3b66;margin:0.3mm 0">'
                         f'Pattern: <b>Non-MDR / Susceptible</b></div>')
                if _aware_str:
                    H.append(f'<div style="font-size:9pt;color:#555;margin:0.3mm 0">'
                             f'AWaRe: {_aware_str}</div>')
                H.append('<hr class="dv" style="margin:0.8mm 0">')
                H.append(
                    '<div class="alert al-info" style="font-size:8.5pt">'
                    '▣ No ESBL / AmpC / Carbapenemase markers detected.<br>'
                    '<span style="font-size:8pt">Standard culture-directed therapy applicable. '
                    'Follow recommended regimen above.</span></div>'
                )
    H.append('</div></div>')

    # ── PREGNANCY -- USE WITH CAUTION  (dedicated section) ─────────────────
    if is_preg and preg_warn_items:
        H.append('<hr class="dv">')
        H.append(
            '<div class="sec-ttl" style="color:#7d3c98;border-bottom-color:#7d3c98">'
            f'{_T["pregnancy"]} &nbsp;'
            '<span style="font-size:8pt;font-weight:normal;color:#888">'
            f'{_T["preg_sub"]}</span></div>'
        )
        for _pw in preg_warn_items:
            _pname = _esc(_pw.get("name", ""))
            _paw   = _esc(_pw.get("aware", ""))
            _pnote = (_pw.get("preg_note") or "").strip()
            # Use English note if lang=en
            if _EN and _pw.get("preg_note_en"):
                _pnote = _pw.get("preg_note_en").strip()
            H.append(
                f'<div style="margin:0.3mm 0;padding:0.8mm 2.5mm;border-radius:2mm;'
                f'border:1pt solid #c39bd3;background:#f5eef8;page-break-inside:avoid">'
                f'<div style="display:flex;justify-content:space-between;align-items:center">'
                f'<b style="font-size:9pt;color:#6c3483">{_pname}</b>'
                f'<span style="padding:0.3mm 2.5mm;border-radius:2mm;font-size:8pt;'
                f'font-weight:bold;background:#7d3c98;color:#fff">{_paw}</span>'
                f'</div>'
            )
            if _pnote:
                for _line in _pnote.splitlines():
                    _line = _line.strip()
                    if not _line:
                        continue
                    if _line.startswith("⊘"):
                        _lcolor = "#922b21"; _lbg = "#fdf2f2"
                    elif _line.startswith("✓"):
                        _lcolor = "#1e8449"; _lbg = "#eafaf1"
                    elif _line.startswith("⚠"):
                        _lcolor = "#b7770d"; _lbg = "#fef9e7"
                    elif _line.startswith(">>>"):
                        _lcolor = "#444";   _lbg = "#f0f0f0"
                    else:
                        _lcolor = "#444";   _lbg = "transparent"
                    H.append(
                        f'<div style="font-size:9pt;color:{_lcolor};'
                        f'background:{_lbg};padding:0.3mm 2mm;margin-top:0.5mm;'
                        f'border-radius:1mm">{_esc(_xlate_preg_note(_line))}</div>'
                    )
            H.append('</div>')

    # Combination + Hepatic (compact)
    if combo_suggestions:
        H.append('<hr class="dv" style="margin:0.5mm 0"><div class="sec-ttl">Combination Therapy — MDR</div>')
        for cs in combo_suggestions[:2]:
            data = cs["data"]
            H.append(f'<div class="alert al-danger" style="font-size:8.5pt">'
                     f'<b>{_esc(data["urgency"])} — {_esc(data["title"])}</b></div>')
            for opt in data["options"][:3]:
                avoid = "AVOID" in opt.get("evidence","") or "AVOID" in opt["combo"].upper()
                H.append(f'<div style="font-size:8.5pt;margin:0.3mm 0;color:{"#922b21" if avoid else "#1a1a2e"}">'
                         f'{"⊘ " if avoid else "• "}<b>{_esc(opt["combo"])}</b>'
                         f' <span style="color:#888">({_esc(opt["evidence"])})</span></div>')

    if is_hepatic and hepatic_recs:
        action_recs = [r for r in hepatic_recs if r.get("requires_action")][:3]
        if action_recs:
            H.append(f'<hr class="dv" style="margin:0.5mm 0"><div class="sec-ttl">Hepatic Dosing — CP-{_esc(child_pugh)}</div>')
            for r in action_recs:
                cls4 = "danger-val" if "Avoid" in r["level"] else "warn-val"
                H.append(f'<div style="font-size:9pt;margin:0.3mm 0">'
                         f'<b class="{cls4}">{_esc(r["name"])}</b>: {_esc(r["recommendation"])}</div>')

    # Footer
    H.append("""<hr class="dv" style="margin-top:1mm">
<div class="grid2">
  <div class="g2l" style="font-size:8pt;color:#666">
    <b>References:</b> CLSI 2026 | EUCAST Breakpoint Tables v16.1 | IDSA AMR Guidance 2026 | WHO AWaRe 2025 | Sanford 2025 | BNF 2025 | Egypt Nat. Guidelines
  </div>
  <div class="g2r" style="font-size:8pt;color:#666">
    <b>Disclaimer:</b> Clinical decision support only. Treatment decisions are the sole responsibility of the treating physician.
  </div>
</div>

</div></body></html>"""
)

    _full_html = "".join(H)
    if _EN:
        # Final safety net: guarantee a pure-English report by removing any Arabic
        # that escaped phrase-translation (e.g. an organism's Arabic parenthetical
        # like "Anaerobes (لاهوائيات)"), then tidy the artifacts left behind. HTML
        # tags/attributes are ASCII, so only visible text is affected.
        # Arabic ranges, deliberately excluding U+FE00-FE0F: those are emoji
        # variation selectors, not Arabic, and a range like FB50-FEFF swallows
        # them.
        _AR = r'\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF'
        # 1. Parenthetical glosses -- purely Arabic inside brackets. Safe to
        #    drop; this is the case the original net was written for.
        _full_html = re.sub(r'\s*\(\s*[' + _AR + r'\s\u060C\u061B\u061F.,\-]+\s*\)',
                            '', _full_html)
        # 2. Anything still Arabic is running clinical text. Leave it visible
        #    rather than amputating words from a dose instruction. Record it so
        #    QA can see the leak instead of the patient inheriting it.
        _ar_leaks = re.findall(r'[' + _AR + r']+(?:[\s\u060C][' + _AR + r']+)*',
                               _full_html)
        if _ar_leaks:
            try:
                _uniq = sorted(set(t.strip() for t in _ar_leaks if t.strip()))
                logging.warning(
                    "EN report: %d Arabic fragment(s) reached render; "
                    "add an _en field for these: %s",
                    len(_uniq), " | ".join(_uniq[:12])
                )
            except Exception:
                pass
        _full_html = re.sub(r'\(\s*\)', '', _full_html)      # empty () left by stripping
        _full_html = re.sub(r'[ \t]{2,}', ' ', _full_html)   # collapse doubled spaces
    # Restore the patient name AFTER the Arabic strip: the name is a patient
    # identifier, not clinical prose, so the pure-English rule must not apply to
    # it -- a report with no name is a misidentification hazard, which is worse
    # than an Arabic word on an English page. The placeholder is ASCII, so it
    # survives the strip above unharmed.
    _full_html = _full_html.replace("@@PTNAME@@", _esc(patient_name or "—"))
    try:
        if return_html:
            return pdf_glyph_guard(_full_html)
        return _wp.HTML(string=pdf_glyph_guard(_full_html)).write_pdf()
    except Exception:
        return None



def generate_decision_tree_image(
    patient_name:    str,
    age:             int,
    sex:             str,
    weight:          float,
    cl_cr:           float,
    is_renal:        bool,
    is_preg:         bool,
    organism:        str,
    specimen:        str,
    first_line:      List[str],
    preferred:       List[str],
    use_caution:     List[str],
    contraindicated: List[str],
    reserve:         List[str],
    notes:           List[str],
    colony_count:    str = "",
    date_in:         str = "",
    pus_cells:       str = "",
    rbcs:            str = "",
    lab_name:        str = "Your Lab Name",
    lab_city:        str = "",
    mdr_result:          Optional[Dict] = None,
    esbl_result:         Optional[Dict] = None,
    phenotypes:          Optional[List] = None,
    referring_physician: str = "",
    culture_condition:   str = "Aerobic",
    microbiologist:      str = "",
    age_months:          Optional[int] = None,
) -> bytes:
    if not PIL_AVAILABLE:
        raise RuntimeError("Pillow غير متاح -- أضف Pillow لـ requirements.txt")

    # ── Scale & Canvas ────────────────────────────────────────────────────────
    # A4 landscape = 297mm × 210mm  @ 200 DPI = 2339 × 1654 px
    # نطرح 10mm من كل جهة -> 277mm × 190mm = 2181 × 1496 px
    # أصغر من A4 بـ ~20mm -> يُطبع بدون قص
    S  = 2                       # 2× scale -> جودة طباعة جيدة
    W  = 2181                    # 277mm @ 200 DPI  (أصغر من A4 بـ 20mm)
    H  = 1496                    # 190mm @ 200 DPI  (أصغر من A4 بـ 20mm)
    P  = 14   * S                # padding
    G  = 8    * S                # gap

    # ── Color Palette (identical to reference) ────────────────────────────────
    BG         = (248, 250, 252)
    WHITE      = (255, 255, 255)
    DARK       = (28,  32,  40)
    GRAY       = (95, 100, 112)
    LIGHT_GRAY = (190, 195, 205)

    NAVY       = (4,   26,  63)
    PURPLE_BD  = (120, 75, 178);  PURPLE_BG  = (247, 243, 254)
    GREEN_BD   = (45, 138,  68);  GREEN_BG   = (236, 252, 240);  GREEN_TXT  = (20,  95,  40)
    AMBER_BD   = (195,140,  30);  AMBER_BG   = (255, 250, 228);  AMBER_TXT  = (120,  80,   0)
    RED_BD     = (183, 52,  52);  RED_BG     = (255, 237, 234);  RED_TXT    = (148,  30,  30)
    BLUE_BD    = (35,  90, 172);  BLUE_BG    = (234, 244, 255);  BLUE_TXT   = (15,   55, 145)
    ALERT_BD   = (205,115,  50);  ALERT_BG   = (255, 248, 232);  ALERT_TXT  = (130,  60,   5)
    SPEC_BD    = (35,  90, 172);  SPEC_BG    = (234, 244, 255)
    MICRO_BD   = (30, 130,  65);  MICRO_BG   = (234, 252, 238)
    FL_BD      = (190,138,  28);  FL_BG      = (255, 250, 225)
    FOOT_BD    = (185,192,200);   FOOT_BG    = (247, 249, 251)

    # ── Fonts (all scaled) ────────────────────────────────────────────────────
    def gf(size: int, bold: bool = False):
        """
        Robust font loader with comprehensive fallbacks.
        Priority: Liberation Sans -> DejaVu -> NotoSans -> Amiri -> auto-discover
        Liberation/DejaVu give the clean sans-serif look of the old images.
        NotoSans/Amiri are fallbacks for Streamlit Cloud if Liberation not found.
        """
        import os as _os
        _b = "Bold" if bold else "Regular"
        paths = [
            # ── DejaVu Sans FIRST -- supports Arabic Unicode (fonts-dejavu-core) ─
            f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
            f"/usr/share/fonts/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
            f"/usr/share/fonts/truetype/dejavu-sans/DejaVuSans{'-Bold' if bold else ''}.ttf",
            # ── Liberation Sans (fonts-liberation in packages.txt) ──────────────
            f"/usr/share/fonts/truetype/liberation/LiberationSans-{_b}.ttf",
            f"/usr/share/fonts/truetype/liberation2/LiberationSans-{_b}.ttf",
            f"/usr/share/fonts/liberation/LiberationSans-{_b}.ttf",
            # ── Noto Sans (fonts-noto-core in packages.txt) -- clean sans-serif ──
            f"/usr/share/fonts/truetype/noto/NotoSans-{_b}.ttf",
            f"/usr/share/fonts/truetype/noto/NotoSans{'Bold' if bold else 'Regular'}.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/noto/NotoSans-Regular.ttf",
            # ── Amiri (fonts-hosny-amiri in packages.txt) -- Arabic+Latin ────────
            f"/usr/share/fonts/opentype/fonts-hosny-amiri/Amiri-{_b}.ttf",
            f"/usr/share/fonts/opentype/fonts-hosny-amiri/amiri-{'bold' if bold else 'regular'}.ttf",
            f"/usr/share/fonts/truetype/amiri/Amiri-{_b}.ttf",
            # ── Other common fonts ───────────────────────────────────────────────
            f"/usr/share/fonts/truetype/freefont/FreeSans{'Bold' if bold else ''}.ttf",
            f"/usr/share/fonts/truetype/ubuntu/Ubuntu-{'B' if bold else 'R'}.ttf",
        ]
        for p in paths:
            if _os.path.isfile(p):
                try:
                    return ImageFont.truetype(p, size * S)
                except Exception:
                    continue
        # Auto-discover: search for ANY usable sans-serif font
        for _fdir in ["/usr/share/fonts/truetype", "/usr/share/fonts/opentype",
                      "/usr/share/fonts"]:
            if not _os.path.isdir(_fdir):
                continue
            try:
                for _root, _, _files in _os.walk(_fdir):
                    for _f in sorted(_files):   # sorted = deterministic order
                        if not _f.lower().endswith((".ttf", ".otf")):
                            continue
                        _fl = _f.lower()
                        if any(k in _fl for k in
                               ("liberation", "dejavu", "notosans", "noto-sans",
                                "ubuntu", "freesans", "amiri", "arial", "sans")):
                            try:
                                return ImageFont.truetype(
                                    _os.path.join(_root, _f), size * S)
                            except Exception:
                                continue
            except Exception:
                continue
        return ImageFont.load_default()

    F_HEADER  = gf(20, True)
    F_TITLE   = gf(15, True)
    F_SUBTITL = gf(12, True)
    F_TEXT    = gf(12)
    F_SMALL   = gf(10)
    F_ORG     = gf(26, True)
    F_SUMNUM  = gf(20, True)
    F_BADGE   = gf(9,  True)

    def fh(f) -> int:
        return f.size if hasattr(f, "size") else 14 * S

    def tw(draw, text, font) -> float:
        try:
            return draw.textlength(text, font=font)
        except Exception:
            return len(text) * fh(font) * 0.6

    # ── Arabic text helper ────────────────────────────────────────────────────
    def _fix_arabic(text: str) -> str:
        """
        Reshape Arabic text for Pillow.
        reshape() connects letters correctly.
        get_display() reverses word order -- NOT used here to avoid reversal.
        """
        if not text:
            return ""
        if not ARABIC_SUPPORT:
            return str(text)
        try:
            return _arabic_reshaper_mod.reshape(str(text))
        except Exception:
            return str(text)

    def rbox(draw, box, bg, bd, radius=14, width=3):
        draw.rounded_rectangle(
            [box[0], box[1], box[2], box[3]],
            radius=radius * S, fill=bg, outline=bd, width=width * S
        )

    def text_wrap(draw, x, y, text, font, fill, max_w, gap=4, max_y=None, min_size=7):
        """
        Word-wraps text within max_w. If max_y is given and the wrapped
        text would cross that boundary at the current font size, the font
        is progressively shrunk (down to min_size) so the text always
        stays inside its box; if it still doesn't fit at min_size, the
        last visible line is truncated with "…" instead of overflowing
        past the border.
        """
        text = _fix_arabic(text)   # reshape Arabic before wrapping

        def _wrap(f):
            words = text.split()
            lines, cur = [], ""
            for w in words:
                trial = (cur + " " + w).strip()
                if tw(draw, trial, f) <= max_w:
                    cur = trial
                else:
                    if cur: lines.append(cur)
                    cur = w
            if cur: lines.append(cur)
            return lines

        f = font
        lines = _wrap(f)
        lh = fh(f) + gap * S

        if max_y is not None and (y + lh * len(lines)) > max_y:
            nominal = max(min_size, int(fh(font) / S) - 1)
            for step in range(nominal, min_size - 1, -1):
                f2 = gf(step)
                lines2 = _wrap(f2)
                lh2 = fh(f2) + gap * S
                if (y + lh2 * len(lines2)) <= max_y:
                    f, lines, lh = f2, lines2, lh2
                    break
            else:
                f = gf(min_size)
                lines = _wrap(f)
                lh = fh(f) + gap * S
                max_lines = max(1, int((max_y - y) // lh))
                if len(lines) > max_lines:
                    lines = lines[:max_lines]
                    lines[-1] = lines[-1].rstrip() + "…"

        for line in lines:
            draw.text((x, y), line, fill=fill, font=f)
            y += lh
        return y

    # AWaRe colors -- Access أخضر، Watch برتقالي
    AWARE_NAME_COLORS = {
        "[A]": (20, 138, 68),    # أخضر -- Access
        "[W]": (180, 100,  0),   # برتقالي -- Watch
    }

    def section_box(draw, box, title, title_color, subtitle, items, bg, bd,
                    ft, fs, fi):
        x1, y1, x2, y2 = box
        rbox(draw, box, bg, bd, radius=16, width=3)
        draw.text((x1 + 14*S, y1 + 12*S), _fix_arabic(title), fill=title_color, font=ft)
        cy = y1 + 12*S + fh(ft) + 6*S
        if subtitle:
            draw.text((x1 + 14*S, cy), _fix_arabic(subtitle), fill=(110,115,125), font=fs)
            cy += fh(fs) + 4*S
        draw.line([(x1 + 10*S, cy), (x2 - 10*S, cy)], fill=bd, width=1*S)
        cy += 8*S
        for item in items:
            if cy + fh(fi) + 7*S > y2 - 8*S:
                draw.text((x1 + 14*S, cy), "…", fill=LIGHT_GRAY, font=fi)
                break
            # استخراج badge [A] أو [W]
            badge = ""
            display_name = item
            for b in ["[A]", "[W]"]:
                if item.endswith(b):
                    badge = b
                    display_name = item[:-len(b)].rstrip()
                    break
            # لون الاسم حسب AWaRe
            name_color = AWARE_NAME_COLORS.get(badge, DARK)
            cy = text_wrap(draw, x1 + 14*S, cy, f"• {display_name}",
                           fi, name_color, x2 - x1 - 26*S, gap=5, max_y=y2-8*S)

    # ── Build Image ───────────────────────────────────────────────────────────
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # ── 1. HEADER ─────────────────────────────────────────────────────────────
    rbox(draw, (P, 6*S, W-P, 62*S), NAVY, NAVY, radius=12, width=1)
    htxt = f"🔬  {lab_name.upper()} – MICROBIOLOGY DEPARTMENT"
    hw   = tw(draw, htxt, F_HEADER)
    draw.text(((W - hw)//2, 16*S), _fix_arabic(htxt), fill=WHITE, font=F_HEADER)

    # ── 2. CULTURE BOX (center) ───────────────────────────────────────────────
    CB = (368*S, 72*S, 870*S, 198*S)
    rbox(draw, CB, WHITE, NAVY, radius=14, width=2)

    ctype = "Culture/ Growth"
    ctw_  = tw(draw, ctype, F_SUBTITL)
    draw.text(((CB[0]+CB[2]-ctw_)//2, CB[1]+12*S), _fix_arabic(ctype), fill=DARK, font=F_SUBTITL)

    ow = tw(draw, organism, F_ORG)
    draw.text(((CB[0]+CB[2]-ow)//2, CB[1]+38*S), _fix_arabic(organism), fill=NAVY, font=F_ORG)

    # Colony count under organism -- Date In inline
    cc_parts = []
    if colony_count:
        cc_parts.append(f"Colony Count: {colony_count}")
    if date_in:
        cc_parts.append(f"Date In: {date_in}")
    if cc_parts:
        cc_txt = "   |   ".join(cc_parts)
        cctw   = tw(draw, cc_txt, F_TEXT)
        draw.text(((CB[0]+CB[2]-cctw)//2, CB[1]+38*S+fh(F_ORG)+6*S),
                  cc_txt, fill=(90, 90, 140), font=F_TEXT)

    # ── 3. PATIENT BOX (left) ─────────────────────────────────────────────────
    PB = (P, 72*S, 358*S, 198*S)
    rbox(draw, PB, PURPLE_BG, PURPLE_BD, radius=14, width=3)
    # No "PATIENT DETAILS" header -- direct fields
    p_lines = []
    if patient_name:
        p_lines.append(f"Patient Name:  {patient_name}")
    _age_lbl = f"{age_months} months" if age_months is not None else f"{age} yrs"
    p_lines.append(f"Sex / Age:     {'Male' if sex == 'Male' else 'Female'}, {_age_lbl}")
    if referring_physician:
        p_lines.append(f"Referred by:   Dr/ {referring_physician}")
    if is_renal:
        _eff, _meas = resolve_crcl(cl_cr, is_renal)
        p_lines.append(
            f"Renal:         IMPAIRED  CrCl:{_eff:.0f}"
            f"{'' if _meas else ' (assumed)'}" if _eff is not None
            else "Renal:         IMPAIRED  CrCl:not measured")
    else:
        p_lines.append("Renal:         Normal")
    p_lines.append("Hepatic:       Normal")
    if sex == "Female" and 12 <= age <= 55:
        p_lines.append(f"Pregnancy:     {'Yes' if is_preg else 'No'}")

    py = 78*S
    for ln in p_lines[:7]:
        draw.text((P+14*S, py), _fix_arabic(f"• {ln}"), fill=DARK, font=F_TEXT)
        py += fh(F_TEXT) + 5*S

    # ── 4. ALERT BOX (right) -- يشمل MDR/ESBL/Phenotype ──────────────────────
    AB = (885*S, 72*S, W-P, 198*S)

    # لون المربع حسب خطورة الـ phenotype
    _ph_names   = [p.get("phenotype","") for p in (phenotypes or [])]
    _has_cre    = any(p in _ph_names for p in ["CRE","CRAB","CRPA"])
    _has_mdr    = (mdr_result or {}).get("level") in ("XDR","PDR")
    _esbl_prob  = (esbl_result or {}).get("probability")
    _has_esbl   = _esbl_prob in ("high", "carbapenemase", "ampc",
                                 "ampc_plasmid", "possible_carbapenemase",
                                 "crpa")

    if _has_cre or _has_mdr:
        AB_BG = (255, 237, 234);  AB_BD = (183, 52, 52);   AB_TXT = (148, 30, 30)
    elif _has_esbl:
        AB_BG = (255, 248, 232);  AB_BD = (205,115, 50);   AB_TXT = (130, 60,  5)
    else:
        AB_BG = ALERT_BG;         AB_BD = ALERT_BD;         AB_TXT = ALERT_TXT

    rbox(draw, AB, AB_BG, AB_BD, radius=14, width=3)

    # عنوان ديناميكي
    if _has_cre:
        alert_title = "🚨 CRE / XDR ALERT"
    elif _has_mdr:
        alert_title = "🔴 MDR/XDR ALERT"
    elif _esbl_prob in ("ampc", "ampc_plasmid"):
        alert_title = "⚠  AmpC ALERT"
    elif _has_esbl:
        alert_title = "⚠  ESBL ALERT"
    else:
        alert_title = "⚠  IMPORTANT ALERT"

    draw.text((AB[0]+12*S, 72*S+12*S), _fix_arabic(alert_title), fill=AB_TXT, font=F_SUBTITL)
    alerts: List[str] = []

    # ── MDR/XDR/PDR ──────────────────────────────────────────────────────────
    mdr_lvl = (mdr_result or {}).get("level")
    if mdr_lvl:
        mdr_cats = (mdr_result or {}).get("resistant_categories", [])
        rc = (mdr_result or {}).get("resistant_count", 0)
        rt = (mdr_result or {}).get("total_tested", 0)
        alerts.append(f"{mdr_lvl}: Resistant {rc}/{rt} categories")
        if mdr_cats:
            alerts.append(f"R-cats: {', '.join(mdr_cats[:3])}")

    # ── ESBL / AmpC / Carbapenemase ────────────────────────────────────────────
    _esbl_mech = (esbl_result or {}).get("mechanism", "")
    if _esbl_prob in ("carbapenemase", "possible_carbapenemase"):
        if "OXA-48" in _esbl_mech:
            alerts.append("Possible OXA-48 carbapenemase")
        else:
            alerts.append("Carbapenemase (KPC/MBL/OXA) possible!")
        alerts.append("Send to reference lab immediately.")
    elif _esbl_prob in ("ampc", "ampc_plasmid"):
        alerts.append("Possible AmpC β-lactamase")
        alerts.append("Avoid 3rd-gen cephalosporins; use Cefepime/Carbapenem")
    elif _esbl_prob == "high":
        alerts.append("High probability ESBL Producer")
        alerts.append("Use Carbapenems for severe cases")
    elif _esbl_prob == "moderate":
        alerts.append("ESBL confirmation recommended")
        alerts.append("Double Disk Synergy Test")
    elif _esbl_prob == "crpa":
        if (esbl_result or {}).get("dtr"):
            alerts.append("DTR P. aeruginosa - all first-line agents non-susceptible")
            alerts.append("Ceftolozane-Tazo / Ceftazidime-Avi / Imipenem-Rel / Cefiderocol")
        else:
            alerts.append("Carbapenem-resistant P. aeruginosa - mechanism not determined")
            _abl = (esbl_result or {}).get("active_betalactams") or []
            alerts.append(f"Still susceptible: {', '.join(_abl)} - high-dose extended infusion"
                          if _abl else "Check Ceftazidime / Cefepime / Pip-Tazo before escalating")

    # ── Phenotypes ────────────────────────────────────────────────────────────
    for ph in (phenotypes or [])[:2]:
        ph_name = ph.get("phenotype","")
        if ph_name not in ("Possible MRSA",):
            alerts.append(f"Phenotype: {ph_name}")

    # ── Organism-specific baseline alerts ────────────────────────────────────
    org_l = organism.lower()
    if not alerts:  # فقط لو مفيش MDR/ESBL
        if "klebsiella" in org_l:
            alerts += ["Consider ESBL screening",
                       "Natural resistance: Ampicillin"]
        elif "e. coli" in org_l or "coli" in org_l:
            alerts += ["Most common UTI pathogen",
                       "Verify with culture sensitivity"]
        elif "pseudomonas" in org_l:
            alerts += ["High intrinsic resistance",
                       "Anti-pseudomonal agent required"]
        elif "mrsa" in org_l or "staphylococcus" in org_l:
            alerts += ["Check MRSA status",
                       "Vancomycin/Linezolid if MRSA"]
        elif "acinetobacter" in org_l:
            alerts += ["MDR risk -- check Carbapenem S/I/R"]
        else:
            alerts = ["Verify sensitivity results."]

    if is_renal:
        _eff, _meas = resolve_crcl(cl_cr, is_renal)
        alerts.append(f"Renal adj. (CrCl {_eff:.0f} ml/min"
                      f"{'' if _meas else ', assumed'})" if _eff is not None
                      else "Renal adj. (CrCl not measured)")
    if is_preg and age >= 18:
        alerts.append("Pregnancy: verify fetal safety")

    ay = 72*S + 12*S + fh(F_SUBTITL) + 8*S
    alert_max_w = AB[2] - AB[0] - 22*S
    for al in alerts[:6]:
        if ay + fh(F_SMALL) + 4*S > AB[3] - 6*S:
            break
        ay = text_wrap(draw, AB[0]+12*S, ay, f"• {al}",
                       F_SMALL, AB_TXT, alert_max_w, gap=4, max_y=AB[3]-6*S)
        ay += 2*S

    # ── 5. ROW 2: Specimen | Microscopic Exam | First-Line ────────────────────
    R2_Y1 = 210*S
    R2_Y2 = 310*S
    r2w   = (W - 2*P - 2*G) // 3

    # Specimen box -- no title, direct fields
    # Specimen label -- add collection method for Urine
    _spec_label = specimen
    if "urine" in specimen.lower():
        _spec_label = f"{specimen} / Mid-Stream"
    spec_items = [
        f"Specimen:      {_spec_label}",
        "Method:        Culture & Sensitivity",
        f"Condition:     {culture_condition}",
    ]
    if microbiologist:
        spec_items.append(f"Microbiologist: Dr/ {microbiologist}")
    micro_items = [
        f"Pus Cells: {pus_cells if pus_cells else chr(8212)} /HPF",
        f"RBCs:      {rbcs if rbcs else chr(8212)} /HPF",
    ]
    fl_items = first_line[:4] or ["--"]

    r2_data = [
    ("",                   spec_items,  SPEC_BD,  SPEC_BG,  ""),
    ("MICROSCOPIC EXAM",   micro_items, MICRO_BD, MICRO_BG, "🔬"),
    ("CLINICAL STRATEGY",  fl_items,    FL_BD,    FL_BG,    "📋"),
    ]
    for i, (title, items, bd, bg, icon) in enumerate(r2_data):
        bx1 = P + i*(r2w+G)
        bx2 = bx1 + r2w
        rbox(draw, (bx1, R2_Y1, bx2, R2_Y2), bg, bd, radius=12, width=2)
        if title:
            draw.text((bx1+12*S, R2_Y1+9*S), _fix_arabic(f"{icon} {title}"), fill=bd, font=F_SUBTITL)
            iy = R2_Y1 + 32*S
        else:
            iy = R2_Y1 + 11*S  # start higher when no title
        for it in items[:5]:
            iy = text_wrap(draw, bx1+14*S, iy, f"• {it}",
                           F_SMALL, DARK, bx2-bx1-24*S, gap=4, max_y=R2_Y2-6*S)

    # ── 6. FOUR MAIN COLUMNS ──────────────────────────────────────────────────
    COL_Y1 = 323*S
    COL_Y2 = H - 115*S
    cw     = (W - 2*P - 3*G) // 4

    # Dynamic column titles based on pregnancy
    avoid_title    = "🚫 AVOID IN PREGNANCY" if is_preg else "🚫 AVOID / CONTRAINDICT."
    avoid_subtitle = "Contraindicated / Not recommended" if is_preg else "Due to other factors"

    columns = [
        ("✅ PREFERRED (SAFE)",  "Preferred oral options",  preferred,       GREEN_BD, GREEN_BG, GREEN_TXT),
        ("⚠️  USE WITH CAUTION", "Use with caution",         use_caution,     AMBER_BD, AMBER_BG, AMBER_TXT),
        (avoid_title,            avoid_subtitle,             contraindicated,  RED_BD,   RED_BG,   RED_TXT),
        ("🛡️  RESERVE (WHO)",     "Last-resort agents (MDR/XDR)", reserve,      BLUE_BD,  BLUE_BG,  BLUE_TXT),
    ]
    for i, (title, subtitle, items, bd, bg, tc) in enumerate(columns):
        bx1 = P + i*(cw+G)
        bx2 = bx1 + cw
        section_box(draw, (bx1, COL_Y1, bx2, COL_Y2),
                    title, tc, subtitle, items or ["--"],
                    bg, bd, F_TITLE, F_SMALL, F_TEXT)

    # ── 7. FOOTER -- 4 مربعات متساوية ─────────────────────────────────────────
    FY1 = H - 116*S
    FY2 = H - 8*S
    fw4 = (W - 2*P - 3*G) // 4

    # ① WHO AWaRe
    fx1 = P;  fx2 = fx1 + fw4
    rbox(draw, (fx1, FY1, fx2, FY2), FOOT_BG, FOOT_BD, radius=12, width=2)
    draw.text((fx1+10*S, FY1+10*S), "WHO AWaRe", fill=DARK, font=F_SUBTITL)
    bx = fx1 + 10*S
    by = FY1 + 30*S
    for label, color in [("ACCESS", GREEN_TXT), ("WATCH", AMBER_TXT), ("RESERVE", RED_TXT)]:
        lw      = tw(draw, label, F_BADGE)
        badge_w = int(lw) + 10*S
        rbox(draw, (bx-2*S, by-2*S, bx+badge_w, by+fh(F_BADGE)+4*S),
             color, color, radius=5, width=1)
        draw.text((bx+3*S, by), label, fill=WHITE, font=F_BADGE)
        bx += badge_w + 5*S
    draw.text((fx1+10*S, by+fh(F_BADGE)+7*S),
              "1st/2nd | Caution | Last resort", fill=GRAY, font=F_SMALL)

    # ② SUMMARY
    fx1 = P + fw4 + G;  fx2 = fx1 + fw4
    rbox(draw, (fx1, FY1, fx2, FY2), FOOT_BG, FOOT_BD, radius=12, width=2)
    draw.text((fx1+10*S, FY1+10*S), "SUMMARY", fill=DARK, font=F_SUBTITL)
    sum_items = [
        (f"~{len(preferred)}",       "Recommended", GREEN_TXT),
        (f"~{len(use_caution)}",     "Caution",     AMBER_TXT),
        (f"~{len(contraindicated)}", "Avoided",     RED_TXT),
        (f"~{len(reserve)}",         "Reserve",     BLUE_TXT),
    ]
    sw = (fx2 - fx1 - 16*S) // 4
    for j, (num, lbl, clr) in enumerate(sum_items):
        sx = fx1 + 10*S + j * sw
        draw.text((sx, FY1+28*S), num, fill=clr,  font=F_SUMNUM)
        draw.text((sx, FY1+62*S), lbl, fill=GRAY, font=F_SMALL)

    # ③ NOTES
    fx1 = P + 2*(fw4+G);  fx2 = fx1 + fw4
    rbox(draw, (fx1, FY1, fx2, FY2), FOOT_BG, FOOT_BD, radius=12, width=2)
    draw.text((fx1+10*S, FY1+10*S), "NOTES", fill=DARK, font=F_SUBTITL)
    ny = FY1 + 30*S
    for note in (notes or [])[:5]:
        if ny + fh(F_SMALL) + 3*S > FY2 - 6*S:
            break
        ny = text_wrap(draw, fx1+10*S, ny, f"• {note}",
                       F_SMALL, DARK, fx2-fx1-18*S, gap=3, max_y=FY2-6*S)

    # ④ REFERENCES
    fx1 = P + 3*(fw4+G);  fx2 = W - P
    rbox(draw, (fx1, FY1, fx2, FY2), FOOT_BG, FOOT_BD, radius=12, width=2)
    draw.text((fx1+10*S, FY1+10*S), "REFERENCES", fill=DARK, font=F_SUBTITL)
    refs = ["EUCAST Breakpoint Tables v16.1", "CLSI M100 Ed36", "IDSA AMR Guidance 2026",
            "WHO AWaRe 2025", "Egypt Nat. Guidelines", "BNF 2025 | FDA Labels"]
    ry = FY1 + 30*S
    for ref in refs:
        if ry + fh(F_SMALL) + 3*S > FY2 - 6*S:
            break
        ry = text_wrap(draw, fx1+10*S, ry, f"• {ref}",
                       F_SMALL, DARK, fx2-fx1-18*S, gap=3, max_y=FY2-6*S)
    # ── Export Ultra HD ───────────────────────────────────────────────────────
    buf = io.BytesIO()
    img.save(buf, "PNG", dpi=(200, 200), optimize=False)
    return buf.getvalue()


def generate_report(
    patient_name:    str,
    age:             int,
    sex:             str,
    weight:          float,
    cl_cr:           float,
    is_renal:        bool,
    is_preg:         bool,
    is_hepatic:      bool,
    allowed:         List[Dict],
    warned:          List[Dict],
    banned:          List[Dict],
    preg_warn_items: List[Dict],
    organism:        str,
    specimen:        str,
    interactions:    List[str],
    sir_map:         Dict[str, str],
    colony_count:    str = "",
    date_in:         str = "",
    pus_cells:       str = "",
    rbcs:            str = "",
    lab_name:              str = "Your Lab Name",
    lab_city:              str = "",
    patho_assessment:      dict = None,
    show_commercial_names: bool = False,
    age_months:            Optional[int] = None,
) -> str:
    now  = datetime.now().strftime("%Y-%m-%d %H:%M")
    sep  = "=" * 60
    sep2 = "-" * 60
    L:   List[str] = []

    lab_hdr = lab_name.upper() if lab_name else "ORANGE LAB"
    L += [sep, f"{lab_hdr} -- CLINICAL DECISION REPORT", sep, f"Date     : {now}"]
    if patient_name:
        L.append(f"Patient  : {patient_name}")
    L.append(sep)

    L += ["\nPATIENT DETAILS", sep2,
          (f"Age      : {age_months} months" if age_months is not None
         else f"Age      : {age} years"),
          f"Gender   : {sex}",
          f"Weight   : {weight} kg",
          f"Renal    : {'IMPAIRED' if is_renal else 'Normal'}"]
    if is_renal:
        _eff, _ = resolve_crcl(cl_cr, is_renal)
        L.append(f"CrCl     : {crcl_label(cl_cr, is_renal)} "
                 f"({get_renal_severity(_eff)})")
    L.append(f"Hepatic  : {'IMPAIRED' if is_hepatic else 'Normal'}")
    if sex == "Female" and age >= 18:
        L.append(f"Pregnant : {'Yes' if is_preg else 'No'}")

    L += ["\nCULTURE & MICROSCOPY", sep2,
          f"Specimen : {specimen}"]
    if date_in:
        L.append(f"Date In  : {date_in}")
    L.append(f"Organism : {organism}")
    if colony_count:
        L.append(f"Colony   : {colony_count}")
    if pus_cells:
        L.append(f"Pus Cells: {pus_cells} /HPF")
    if rbcs:
        L.append(f"RBCs     : {rbcs} /HPF")

    if organism in ORGANISM_PROFILE:
        op = ORGANISM_PROFILE[organism]
        if op.get("note"):
            L.append(f"Note       : {op['note']}")
        spec_ctx = (op.get("specimen_context") or {}).get(specimen, "")
        if spec_ctx:
            L.append(f"Context    : {spec_ctx}")
        _fl_disp = _hide_urine_only(op.get("first_line"), specimen)
        if _fl_disp:
            L.append(f"First-line : {', '.join(_fl_disp)}")
        if op.get("avoid"):
            L.append(f"Avoid      : {', '.join(op['avoid'])}")

    if sir_map:
        L += ["\nSENSITIVITY RESULTS", sep2]
        for drug, result in sorted(sir_map.items()):
            label = {"S": "Sensitive", "R": "Resistant", "I": "Intermediate"}.get(result, result)
            L.append(f"{drug:<40} {label}")

    # AST PANEL COMPLETENESS -- added 2026-08-22, request: this belongs in
    # the internal report, not just the interactive Streamlit page. Same
    # question as the UI card: was enough tested at all, not just "was what
    # WAS tested interpreted correctly". Silently absent (not an empty
    # section header) when the module isn't available or the organism has
    # no expected-panel group -- see ast_panel_completeness.py for why
    # staying silent beats guessing for an organism this module doesn't
    # cover confidently.
    if sir_map and _PANEL_COMPLETENESS_AVAILABLE and _check_panel_completeness_ext:
        _pc_report = _check_panel_completeness_ext(organism, specimen, sir_map)
        if _pc_report.status != "not_evaluated":
            L += ["\nAST PANEL COMPLETENESS", sep2,
                  f"Organism : {_pc_report.organism_group}",
                  f"Expected : {_pc_report.expected_total}    "
                  f"Tested: {_pc_report.tested_count}    "
                  f"Missing: {len(_pc_report.missing_primary) + len(_pc_report.missing_supplemental)}"]
            if not (_pc_report.missing_primary or _pc_report.missing_supplemental):
                L.append("Panel adequate -- all expected agents for this organism were tested.")
            else:
                if _pc_report.status == "critical":
                    L.append("!! CRITICAL: every primary agent tested came back Resistant, "
                             "and expected primary agent(s) were never tested. A therapeutic "
                             "option may exist among the untested agents -- this panel cannot "
                             "rule that out. Do not report 'no susceptible options' from an "
                             "incomplete panel.")
                if _pc_report.missing_primary:
                    L.append("Missing (primary)     : " + ", ".join(_pc_report.missing_primary))
                if _pc_report.missing_supplemental:
                    L.append("Missing (supplemental): " + ", ".join(_pc_report.missing_supplemental))
            if _pc_report.rule_id:
                try:
                    from guideline_registry import citation_line as _pc_report_cite
                    _pc_report_ref = _pc_report_cite(_pc_report.rule_id)
                    if _pc_report_ref:
                        L.append(f"Reference: {_pc_report_ref} -- see guideline_registry.py "
                                 f"for verification status")
                except Exception:
                    pass

    if interactions:
        L += ["\nINTERACTIONS / WARNINGS", sep2]
        for item in sorted(set(interactions)):
            L.append(f"- {item}")

    # MDR/XDR/PDR + ESBL في التقرير
    if sir_map:
        mdr_r = classify_mdr(organism, sir_map)
        if mdr_r["level"]:
            info = MDR_INFO[mdr_r["level"]]
            L += [f"\n{info['icon']} RESISTANCE CLASSIFICATION: {info['label']}", sep2,
                  info["detail"],
                  f"Resistant ({mdr_r['resistant_count']}/{mdr_r['total_tested']}): "
                  + ", ".join(mdr_r['resistant_categories']),
                  f"Action: {info['action']}", ""]
        esbl_r = predict_esbl(organism, sir_map)
        prob   = esbl_r.get("probability")
        if prob == "carbapenemase":
            L += [f"\n🚨 {esbl_r.get('mechanism','POSSIBLE CARBAPENEMASE PRODUCER').upper()}", sep2,
                  esbl_r["detail"], f"Action: {esbl_r['action']}", ""]
        elif prob in ("ampc", "ampc_plasmid"):
            L += ["\n⚠️  POSSIBLE AmpC β-LACTAMASE PRODUCER", sep2,
                  esbl_r["detail"], f"Action: {esbl_r['action']}", ""]
        elif prob == "high":
            L += ["\n⚠️  HIGH PROBABILITY ESBL PRODUCER", sep2,
                  esbl_r["detail"], f"Action: {esbl_r['action']}", ""]
        elif prob == "crpa":
            L += [f"\n{'🚨' if esbl_r.get('dtr') else '⚠️ '} "
                  f"{esbl_r.get('mechanism','CARBAPENEM-RESISTANT P. AERUGINOSA').upper()}", sep2,
                  esbl_r["detail"], f"Action: {esbl_r['action']}", ""]
        elif prob == "moderate":
            L += ["\n🔶 ESBL CONFIRMATION RECOMMENDED", sep2,
                  esbl_r["detail"], f"Action: {esbl_r['action']}", ""]

    L += ["\nRECOMMENDED ANTIBIOTICS", sep]
    if allowed:
        for item in allowed:
            sir_tag  = f" [Culture: {sir_map[item['name']]}]" if sir_map and item['name'] in sir_map else ""
            preg_tag = " [Pregnancy: caution]" if (is_preg and preg_status_of(item) == "Warn") else ""
            L += [f"\n{item['name']}{sir_tag}{preg_tag}", sep2,
                  f"WHO AWaRe : {item.get('aware','-')}",
                  f"Class     : {item.get('class','-')}",
                  f"Route     : {'Oral/PO-friendly' if item.get('high_po') else 'IV/IM only'}"]
            spec_note = (item.get("specimen_notes") or {}).get(specimen, "")
            if spec_note:
                L += [f"Note      : {item.get('note','')}", f"{specimen}   : {spec_note}"]
            else:
                L.append(f"Note      : {item.get('note','')}")
            if is_renal:
                L.append(f"Renal     : {item.get('renal_note','-')}")
            if is_preg and preg_status_of(item) == "Warn":
                pn = (item.get("preg_note") or "").splitlines()
                if pn:
                    L.append(f"Pregnancy : {pn[0]}")
            if show_commercial_names:
                _brands = get_commercial_name(item["name"])
                if _brands:
                    L.append(f"Brands    : {_brands}")
    else:
        L.append("No recommended options after applying all restrictions.")

    if warned:
        L += ["\nDOSE ADJUSTMENT / USE WITH CAUTION", sep]
        if is_renal:
            L.append(f"Patient CrCl = {crcl_label(cl_cr, is_renal)}\n")
        for item in warned:
            sir_tag = f" [Culture: {sir_map[item['name']]}]" if sir_map and item['name'] in sir_map else ""
            L += [f"{item['name']}{sir_tag}", sep2, f"WHO AWaRe : {item.get('aware','-')}"]
            # Printed BEFORE the reason branch, not inside it: an Intermediate
            # agent that also needs a renal or hepatic adjustment carries the
            # other reason in warning_reason, and the I used to disappear from
            # this report entirely.
            if (item.get("culture_intermediate")
                    and item.get("warning_reason") != "intermediate_culture"):
                L.append("!! CONFLICT : culture is INTERMEDIATE (EUCAST: susceptible at "
                         "INCREASED exposure) while the host requires a REDUCED dose. "
                         "Prefer a fully susceptible agent; if unavoidable, dose with TDM.")
            if item.get("warning_reason") == "intermediate_culture":
                L.append("Reason    : Intermediate (I) on culture result")
            elif item.get("esbl_note") or item.get("esbl_note_en"):
                # Mechanism warnings (ESBL BLI-in-UTI, suspected carbapenemase)
                # carry their reason in esbl_note; without this branch they fell
                # through to renal_note and printed an empty reason.
                L.append("Reason    : " + (item.get("esbl_note_en")
                                           or item.get("esbl_note", "-")))
            else:
                L += [f"Renal note: {item.get('renal_note','-')}",
                      f"Limit CrCl: <= {item.get('renal_limit','-')} ml/min"]
            if show_commercial_names:
                _brands = get_commercial_name(item["name"])
                if _brands:
                    L.append(f"Brands    : {_brands}")
            L.append("")

    if is_preg and preg_warn_items:
        L += ["\nPREGNANCY -- USE WITH CAUTION", sep]
        for item in preg_warn_items:
            L += [item['name'], sep2]
            L.extend((item.get("preg_note") or "").splitlines())
            L.append("")

    if banned:
        L += ["\nCONTRAINDICATED / INEFFECTIVE", sep]
        grouped: Dict[str, list] = {
            "resistant": [], "renal": [], "pregnancy": [],
            "child": [], "organism": [], "specimen": [], "other": [],
        }
        for item in banned:
            grouped.setdefault(item["category"], []).append(item)
        labels = [
            ("resistant", "[A] RESISTANT IN CULTURE"),
            ("renal",     "[B] CONTRAINDICATED -- RENAL IMPAIRMENT"),
            ("pregnancy", "[C] CONTRAINDICATED -- PREGNANCY"),
            ("child",     "[D] NOT SUITABLE FOR AGE"),
            ("organism",  f"[E] INEFFECTIVE FOR {organism}"),
            ("specimen",  f"[F] INAPPROPRIATE FOR {specimen.upper()} SPECIMEN"),
            ("other",     "[G] OTHER CONTRAINDICATIONS"),
        ]
        _rendered_cats = set()
        for cat, heading in labels:
            if grouped.get(cat):
                _rendered_cats.add(cat)
                L += [f"\n{heading}", sep2]
                for b in grouped[cat]:
                    L.append(f"- {b['name']} -- {b.get('reason_short', '')}")
                    if cat == "renal":
                        dk       = b["name"].lower().replace(" ", "")
                        rendered = False
                        for k, v in RENAL_BAN_REASONS.items():
                            if k in dk:
                                L.extend([f"  {ln}" for ln in v.splitlines()])
                                rendered = True
                                break
                        if not rendered:
                            L.extend([f"  {ln}" for ln in (b.get("reason_detail") or "").splitlines()])
                    else:
                        L.extend([f"  {ln}" for ln in (b.get("reason_detail") or "").splitlines()])
                    L.append("")
        # Safety net -- never silently drop a banned drug whose category is not
        # listed above (e.g. a future/unknown category).
        for cat, items in grouped.items():
            if cat in _rendered_cats or not items:
                continue
            L += [f"\n[+] OTHER -- {cat.upper()}", sep2]
            for b in items:
                L.append(f"- {b['name']} -- {b.get('reason_short', '')}")
                L.extend([f"  {ln}" for ln in (b.get("reason_detail") or "").splitlines()])
                L.append("")

    # ── Pathogenicity Assessment ──────────────────────────────────────
    if patho_assessment:
        sc    = patho_assessment.get("score", 0)
        verd  = patho_assessment.get("verdict", "")
        interp = patho_assessment.get("interpretation", "")
        recs  = patho_assessment.get("recommendations", [])
        flags = patho_assessment.get("special_flags", [])
        L += ["", "PATHOGENICITY ASSESSMENT", sep2,
              f"Score    : {sc}% -- {verd}"]
        if "ABU_DETECTED" in flags:
            L.append("FLAG     : Asymptomatic Bacteriuria (ABU) Detected")
        if "MW_REJECT" in flags:
            L.append("FLAG     : Murray-Washington -- Specimen REJECTED")
        elif "MW_ADEQUATE" in flags:
            L.append("FLAG     : Murray-Washington -- Adequate Sputum Quality")
        if "SIRS_HIGH" in flags:
            L.append("FLAG     : SIRS >=3 criteria -- Sepsis Probable")
        if interp:
            L.append(f"Interp   : {interp}")
        if recs:
            L.append("Recs     :")
            for r in recs:
                L.append(f"  • {r}")

    L += ["\nDISCLAIMER", sep,
          "هذا التقرير أداة مساعدة للقرار الطبي وليس بديلاً عن التقييم السريري.",
          "القرار النهائي للوصف العلاجي يعود للطبيب المعالج.", sep,
          "Guidelines: EUCAST Breakpoint Tables v16.1 | CLSI M100 Ed36 | IDSA AMR Guidance 2026 | Egypt National",
          "Route info: BNF 2025 | FDA Labels | WHO AWaRe 2025",
          "WHO AWaRe : Access | Watch | Reserve", sep,
          f"Developed by Dr / Hussein Ali | {lab_name}{(' | ' + lab_city) if lab_city else ''}", sep]
    return "\n".join(L)
