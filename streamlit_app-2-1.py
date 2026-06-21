# © 2025 Dr / Hussein Ali — Orange Lab, 6 October City, Egypt
# Orange Culture Tool — All Rights Reserved
# Unauthorized copying or distribution is prohibited.

import io
import json
import re
import time
import hashlib
from datetime import datetime, date
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import streamlit.components.v1 as stc_components

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
# قاعدة بيانات المضادات الحيوية
# =========================================================
ABX_GUIDELINES = {
    "Amoxicillin + Clavulanic acid": {
        "priority": 1, "class": "Beta-lactamase Inhibitor Combination",
        "note": "✅ خيار قياسي للعدوى البسيطة والمتوسطة (مثل Augmentin/Curam). Bioavailability فموي ~90%.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب عند CrCl < 30.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["augmentin","curam","amoxiclav","co-amoxiclav"],
        "organisms": ["E. coli","Klebsiella spp.","Staphylococcus aureus",
                      "Proteus mirabilis","Streptococcus pneumoniae","H. influenzae"],
        "specimen_notes": {
            "Blood":      "✅ فعال في bacteremia الموجبات والسالبات البسيطة.",
            "Sputum":     "✅ خيار أول لـ CAP وexacerbation COPD.",
            "Wound Swab": "✅ فعال للعدوى الجلدية المختلطة.",
            "Pus":        "✅ جيد للخراجات والعدوى المختلطة.",
            "Urine":      "✅ خيار أول للمسالك غير المعقدة.",
        },
    },
    "Ampicillin/Sulbactam": {
        "priority": 2, "class": "Penicillin + Beta-lactamase Inhibitor (IV)",
        "note": "💉 IV فقط. فعال للموجبات والسالبات. أساس علاج Acinetobacter بجرعات عالية (IDSA AMR 2025).",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["unictam","sigmaclav","unasyn"],
        "organisms": ["E. coli","Klebsiella spp.","Staphylococcus aureus",
                      "Proteus mirabilis","Enterococcus faecalis","Acinetobacter baumannii"],
        "specimen_notes": {
            "Blood":      "💉 فعال في bacteremia المختلطة.",
            "Sputum":     "💉 HAP/VAP خصوصاً Acinetobacter بجرعات عالية.",
            "Wound Swab": "💉 العدوى الجراحية والمختلطة.",
            "Pus":        "💉 الخراجات داخل البطن.",
        },
    },
    "Piperacillin + Tazobactam": {
        "priority": 4, "class": "Anti-pseudomonal Penicillin + Inhibitor (IV)",
        "note": "🛑 (مثل Tazocin) IV فقط. واسع الطيف جداً — يُحفظ للحالات الشديدة (IDSA AMR 2025).",
        "renal_limit": 20, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["tazocin","pip-tazo","piptaz"],
        "organisms": ["Pseudomonas aeruginosa","E. coli","Klebsiella spp.",
                      "Enterococcus faecalis","Proteus mirabilis","Acinetobacter baumannii"],
        "specimen_notes": {
            "Blood":      "🛑 sepsis شديد مع اشتباه Pseudomonas.",
            "Sputum":     "🛑 VAP/HAP مع اشتباه Pseudomonas.",
            "Wound Swab": "🛑 العدوى الجراحية الشديدة.",
            "Pus":        "🛑 الخراجات داخل البطن الشديدة.",
        },
    },
    "Cephalexin": {
        "priority": 1, "class": "1st Gen Cephalosporin (Oral)",
        "note": "✅ (مثل Ceporex) Oral. Bioavailability ~90%. آمن للالتهابات البسيطة والجلد.",
        "renal_limit": 40, "renal_note": "⚖️ مباعدة الجرعات مطلوب.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["ceporex","keflex"],
        "organisms": ["Staphylococcus aureus","Streptococcus pneumoniae","E. coli","Proteus mirabilis"],
        "specimen_notes": {
            "Wound Swab": "✅ خيار ممتاز للعدوى الجلدية البسيطة (cellulitis/impetigo).",
            "Urine":      "✅ مناسب للمسالك البسيطة.",
        },
    },
    "Cefadroxil": {
        "priority": 1, "class": "1st Gen Cephalosporin (Oral)",
        "note": "✅ (مثل Duricef) Oral. Bioavailability ~90%. فعال لالتهابات الحلق والجلد.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["duricef"],
        "organisms": ["Staphylococcus aureus","Streptococcus pneumoniae"],
        "specimen_notes": {
            "Wound Swab": "✅ جيد للعدوى الجلدية والأنسجة الرخوة.",
            "Sputum":     "✅ التهاب الحلق البكتيري (Strep pharyngitis).",
        },
    },
    "Cefaclor": {
        "priority": 2, "class": "2nd Gen Cephalosporin (Oral)",
        "note": "✅ (مثل Ceclor) Oral. Bioavailability ~95%. فعال للأذن الوسطى والمسالك.",
        "renal_limit": 10, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["ceclor"],
        "organisms": ["E. coli","H. influenzae","Staphylococcus aureus",
                      "Streptococcus pneumoniae","Klebsiella spp."],
        "specimen_notes": {
            "Sputum": "✅ التهابات الجهاز التنفسي العلوي والأذن الوسطى.",
            "Urine":  "✅ مناسب للمسالك البولية البسيطة.",
        },
    },
    "Cefuroxime": {
        "priority": 2, "class": "2nd Gen Cephalosporin (Oral)",
        "note": "✅ (مثل Zinnat) Oral. Bioavailability ~52%. واسع المدى للجهاز التنفسي والمسالك.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["zinnat","ceftin"],
        "organisms": ["E. coli","Klebsiella spp.","H. influenzae",
                      "Staphylococcus aureus","Streptococcus pneumoniae","Proteus mirabilis"],
        "specimen_notes": {
            "Sputum":     "✅ CAP وعدوى الجهاز التنفسي.",
            "Wound Swab": "✅ عدوى الأنسجة الرخوة المتوسطة.",
            "Urine":      "✅ مناسب للمسالك.",
            "Blood":      "⚠️ لا يُفضل في bacteremia الشديدة — استبدل بـ Zinacef IV.",
        },
    },
    "Cefuroxime sodium": {
        "priority": 2, "class": "2nd Gen Cephalosporin (IV)",
        "note": "💉 (مثل Zinacef) IV فقط — نفس Cefuroxime لكن للحالات التي تحتاج حقن.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["zinacef","cefuroxime iv","cefuroxime sodium"],
        "organisms": ["E. coli","Klebsiella spp.","H. influenzae",
                      "Staphylococcus aureus","Streptococcus pneumoniae","Proteus mirabilis"],
        "specimen_notes": {
            "Blood":      "💉 bacteremia المتوسطة الشدة.",
            "Sputum":     "💉 CAP الذي يحتاج دخول مستشفى.",
            "Wound Swab": "💉 العدوى الجراحية المتوسطة.",
            "Urine":      "💉 pyelonephritis يحتاج IV.",
        },
    },
    "Ceftriaxone": {
        "priority": 3, "class": "3rd Gen Cephalosporin (IV/IM)",
        "note": "⚠️ (مثل Rocephin) IV/IM فقط — bioavailability فموي = صفر. لا يُستخدم في الحالات البسيطة.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً — يُطرح كبدياً أساساً.",
        "hepatic_caution": True, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["rocephin","cefaxone","triaxone"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis","Staphylococcus aureus",
                      "Streptococcus pneumoniae","H. influenzae",
                      "Salmonella spp.","Shigella spp."],
        "specimen_notes": {
            "Blood":  "💉 خيار ممتاز في bacteremia والـ sepsis.",
            "CSF":    "💉 خيار أول في meningitis البكتيري.",
            "Sputum": "💉 CAP الشديد الذي يحتاج دخول مستشفى.",
            "Urine":  "⚠️ يُحفظ للـ pyelonephritis الشديد فقط.",
            "Stool":  "💉 Typhoid fever والحالات الشديدة من Salmonella/Shigella.",
        },
    },
    "Cefixime": {
        "priority": 2, "class": "3rd Gen Cephalosporin (Oral)",
        "note": "✅ (مثل Suprax) Oral. Bioavailability ~40-50%. خيار فموي قوي للمسالك.",
        "renal_limit": 20, "renal_note": "⚖️ خفض الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["suprax","oroken"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "H. influenzae","Streptococcus pneumoniae","Salmonella spp."],
        "specimen_notes": {
            "Urine":  "✅ خيار فموي قوي للمسالك والـ pyelonephritis الخفيف.",
            "Sputum": "✅ عدوى الجهاز التنفسي الخفيفة.",
            "Stool":  "✅ Step-down بعد Ceftriaxone في Salmonella.",
        },
    },
    "Cefotaxime": {
        "priority": 3, "class": "3rd Gen Cephalosporin (IV)",
        "note": "💉 (مثل Cefotax) IV فقط — bioavailability فموي = صفر.",
        "renal_limit": 20, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["cefotax","claforan"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "Streptococcus pneumoniae","H. influenzae"],
        "specimen_notes": {
            "Blood":  "💉 bacteremia والـ sepsis.",
            "CSF":    "💉 meningitis — بديل Ceftriaxone.",
            "Sputum": "💉 CAP الشديد.",
        },
    },
    "Ceftazidime": {
        "priority": 4, "class": "3rd Gen Cephalosporin Anti-pseudomonal (IV)",
        "note": "🛑 (مثل Fortum) IV فقط — متخصص في Pseudomonas.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري جداً.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["fortum","ceptaz"],
        "organisms": ["Pseudomonas aeruginosa","E. coli","Klebsiella spp.","Proteus mirabilis"],
        "specimen_notes": {
            "Blood":  "🛑 Pseudomonas bacteremia.",
            "Sputum": "🛑 VAP/HAP مع Pseudomonas.",
            "Urine":  "🛑 UTI معقد مع Pseudomonas.",
        },
    },
    "Cefoperazone": {
        "priority": 4, "class": "3rd Gen Cephalosporin (IV)",
        "note": "💉 (مثل Cefobid) IV فقط — يُطرح صفراوياً. آمن في القصور الكلوي.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً — يُطرح عبر الصفراء بالكامل.",
        "hepatic_caution": True, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["cefobid"],
        "organisms": ["Pseudomonas aeruginosa","E. coli","Klebsiella spp.",
                      "Proteus mirabilis","Staphylococcus aureus"],
        "specimen_notes": {
            "Blood": "💉 bacteremia في مرضى القصور الكلوي.",
            "Pus":   "💉 عدوى البطن والمرارة.",
        },
    },
    "Cefoperazone + Sulbactam": {
        "priority": 4, "class": "3rd Gen Cephalosporin + Beta-lactamase Inhibitor (IV)",
        "note": "🛑 (مثل Sulperazone/Bakperazone) IV فقط. مزيج قوي ضد MDR gram-negatives بما فيها Acinetobacter baumannii.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً — يُطرح صفراوياً أساساً.",
        "hepatic_caution": True, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["sulperazone","bakperazone","cefop-sulbactam","cefoperazone sulbactam"],
        "organisms": ["Acinetobacter baumannii","Pseudomonas aeruginosa","Klebsiella spp.",
                      "E. coli","Proteus mirabilis","Staphylococcus aureus"],
        "specimen_notes": {
            "Blood":      "🛑 MDR Acinetobacter/Pseudomonas bacteremia.",
            "Sputum":     "🛑 VAP/HAP بـ MDR Acinetobacter — بروتوكول ICU مصري شائع.",
            "Wound Swab": "🛑 العدوى الجراحية الشديدة ومضاعفات الحروق.",
            "Pus":        "🛑 الخراجات والعدوى داخل البطن عند فشل الخطوط الأولى.",
            "Urine":      "⚠️ بديل عند تعذر الكاربابينيم في MDR UTI.",
        },
    },
    "Cefepime": {
        "priority": 5, "class": "4th Gen Cephalosporin (IV)",
        "note": "🛑 (مثل Maxipime) IV فقط — للحالات الحرجة.",
        "renal_limit": 50, "renal_note": "⚠️ تعديل جرعة دقيق لتجنب السمية العصبية.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["maxipime"],
        "organisms": ["Pseudomonas aeruginosa","E. coli","Klebsiella spp.",
                      "Proteus mirabilis","Staphylococcus aureus",
                      "Enterococcus faecalis","Acinetobacter baumannii"],
        "specimen_notes": {
            "Blood":  "🛑 sepsis شديد مع اشتباه Pseudomonas.",
            "Sputum": "🛑 VAP/HAP الحرجة.",
            "CSF":    "🛑 meningitis المعقد في ICU.",
        },
    },
    "Ciprofloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": "⚠️ (مثل Ciprofar) Oral وIV. Bioavailability فموي ~70-80%. يُفضل ادخاره للمسالك المعقدة.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": ("تحذير حمل — Ciprofloxacin:\n"
                      "  الموقف التقليدي: تجنب (FDA Category C).\n"
                      "  الأدلة الحديثة (ACCP Journal 2025): الخطر الحقيقي أقل مما كان متصوراً.\n"
                      "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)","Warfarin (مضادات التخثر)"],
        "aliases": ["ciprofar","cipro","ciproflox"],
        "organisms": ["E. coli","Klebsiella spp.","Pseudomonas aeruginosa",
                      "Proteus mirabilis","Staphylococcus aureus",
                      "Salmonella spp.","Shigella spp.","Campylobacter jejuni"],
        "specimen_notes": {
            "Urine":      "⚠️ فعال لكن يُحفظ للمسالك المعقدة.",
            "Blood":      "⚠️ bacteremia في الحالات المتوسطة.",
            "Sputum":     "⚠️ الفلوروكينولون الوحيد الفعال ضد Pseudomonas في الصدر.",
            "Wound Swab": "⚠️ عدوى الجروح المعقدة.",
            "Stool":      "⚠️ Shigellosis والحالات الشديدة من Campylobacter.",
        },
    },
    "Levofloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": "⚠️ (مثل Tavanic) Oral وIV. Bioavailability فموي ~99%. أفضل respiratory quinolone متاح.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": ("تحذير حمل — Levofloxacin:\n"
                      "  فلوروكينولون — يُستخدم بحذر شديد.\n"
                      "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["tavanic","levaquin","levoflox"],
        "organisms": ["E. coli","Klebsiella spp.","Pseudomonas aeruginosa",
                      "Staphylococcus aureus","Streptococcus pneumoniae","H. influenzae",
                      "Mycoplasma spp.","Legionella pneumophila"],
        "specimen_notes": {
            "Sputum": "⚠️ خيار قوي لـ CAP (respiratory quinolone) — Mycoplasma وLegionella.",
            "Urine":  "⚠️ فعال لكن يُحفظ للحالات المعقدة.",
            "Blood":  "⚠️ bacteremia في الحالات المتوسطة.",
        },
    },
    "Ofloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": "⚠️ (مثل Tarivid) Oral وIV. Bioavailability فموي ~98%.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": ("تحذير حمل — Ofloxacin:\n"
                      "  فلوروكينولون — يُستخدم بحذر شديد.\n"
                      "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["tarivid","oflox"],
        "organisms": ["E. coli","Klebsiella spp.","Staphylococcus aureus","Proteus mirabilis"],
        "specimen_notes": {
            "Urine":  "⚠️ مناسب للمسالك المتوسطة.",
            "Sputum": "⚠️ عدوى الجهاز التنفسي.",
        },
    },
    "Norfloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": "⚠️ (مثل Noroxin) Oral فقط — متخصص في المسالك البولية. Bioavailability ~35% لكن يتركز في البول.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب عند CrCl < 30.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": ("تحذير حمل — Norfloxacin:\n"
                      "  فلوروكينولون — يُستخدم بحذر شديد.\n"
                      "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["noroxin","norflox"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "Staphylococcus aureus","Enterococcus faecalis"],
        "specimen_notes": {
            "Urine": "⚠️ مخصص للمسالك البولية فقط — لا تركيز علاجي خارج البول.",
        },
    },
    "Nitrofurantoin": {
        "priority": 1, "class": "Urinary Antiseptic (Oral)",
        "note": "🎯 (مثل Macrofuran) Oral فقط — الخيار الأول للمسالك البسيطة. Bioavailability ~90% لكن يتركز في البول فقط.",
        "renal_limit": 30, "renal_note": "🚫 ممنوع إذا CrCl < 30 مل/د.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Warn",
        "preg_note": ("تحذير حمل — Nitrofurantoin:\n"
                      "  آمن في الـ 1st و 2nd trimester.\n"
                      "  ممنوع في الـ 3rd trimester (خطر hemolytic anemia للجنين).\n"
                      "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"),
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["macrofuran","macrobid","nitrofur"],
        "organisms": ["E. coli","Staphylococcus aureus","Enterococcus faecalis","Klebsiella spp."],
        "specimen_notes": {
            "Urine": "🎯 مخصص للمسالك البولية البسيطة فقط — لا يُستخدم خارج البول أبداً.",
        },
    },
    "Fosfomycin": {
        "priority": 1, "class": "Phosphonic Acid (Oral)",
        "note": "🎯 (مثل Monuril) Oral — جرعة واحدة للمسالك. Bioavailability ~34-58% لكن تركيزه في البول عالٍ جداً.",
        "renal_limit": 10, "renal_note": "⚠️ حذر في القصور الشديد.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Warn",
        "preg_note": ("تحذير حمل — Fosfomycin:\n"
                      "  بيانات محدودة — يُعتبر آمناً نسبياً بجرعة واحدة عند الضرورة.\n"
                      "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"),
        "child_safe": False, "interacts_with": [],
        "aliases": ["monuril","fosfocin"],
        "organisms": ["E. coli","Enterococcus faecalis","Staphylococcus aureus","Klebsiella spp."],
        "specimen_notes": {
            "Urine": "🎯 جرعة واحدة للـ uncomplicated UTI — مثالي.",
        },
    },
    "Gentamicin": {
        "priority": 4, "class": "Aminoglycoside (IV/IM)",
        "note": "💉 (مثل Garamycin) IV/IM فقط — لا bioavailability فموي. سام للكلى والأذن.",
        "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى ضرورية.",
        "hepatic_caution": False, "aware": "Access", "high_po": False,
        "preg_status": "Banned",
        "preg_note": ("ممنوع في الحمل — Gentamicin:\n"
                      "  سُمية للأذن الجنينية (ototoxicity) — FDA Category D.\n"
                      "  يعبر المشيمة — خطر فقدان السمع الدائم للجنين."),
        "child_safe": True,
        "interacts_with": ["NSAIDs (مسكنات الألم)"],
        "aliases": ["garamycin","genta"],
        "organisms": ["E. coli","Klebsiella spp.","Pseudomonas aeruginosa",
                      "Proteus mirabilis","Staphylococcus aureus"],
        "specimen_notes": {
            "Blood":      "💉 synergy مع beta-lactam في bacteremia الشديدة.",
            "Wound Swab": "💉 العدوى الجراحية الشديدة.",
            "Urine":      "💉 pyelonephritis المعقد عند عدم توفر بدائل.",
        },
    },
    "Amikacin": {
        "priority": 4, "class": "Aminoglycoside (IV/IM)",
        "note": "💉 (مثل Amikin) IV/IM فقط — لا bioavailability فموي. فعال ضد السالبات المقاومة.",
        "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Banned",
        "preg_note": ("ممنوع في الحمل — Amikacin:\n"
                      "  سُمية للأذن الجنينية (ototoxicity) — FDA Category D.\n"
                      "  يعبر المشيمة — خطر فقدان السمع الدائم للجنين."),
        "child_safe": True,
        "interacts_with": ["NSAIDs (مسكنات الألم)"],
        "aliases": ["amikin","amikacin"],
        "organisms": ["E. coli","Klebsiella spp.","Pseudomonas aeruginosa",
                      "Proteus mirabilis","Staphylococcus aureus","Acinetobacter baumannii"],
        "specimen_notes": {
            "Blood":  "💉 MDR gram-negatives bacteremia.",
            "Sputum": "💉 HAP/VAP مع MDR organisms.",
            "Urine":  "💉 UTI المعقد مع MDR organisms.",
        },
    },
    "Azithromycin": {
        "priority": 2, "class": "Macrolide (Oral/IV)",
        "note": "✅ (مثل Zithrokan) Oral وIV. Bioavailability فموي ~37% لكن تركيزه النسيجي عالٍ جداً.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["zithrokan","zithromax","azithro"],
        "organisms": ["Staphylococcus aureus","Streptococcus pneumoniae","H. influenzae",
                      "Mycoplasma spp.","Salmonella spp.","Shigella spp.",
                      "Campylobacter jejuni","Legionella pneumophila"],
        "specimen_notes": {
            "Sputum":     "✅ خيار ممتاز لـ CAP والـ atypicals (Mycoplasma/Legionella).",
            "Wound Swab": "✅ عدوى الجلد الخفيفة.",
            "Stool":      "✅ الخيار الأول في Campylobacter وبعض حالات Shigella.",
        },
    },
    "Clarithromycin": {
        "priority": 2, "class": "Macrolide (Oral/IV)",
        "note": "✅ (مثل Klacid) Oral وIV. Bioavailability فموي ~55%. فعال للصدر.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Banned",
        "preg_note": ("ممنوع في الحمل — Clarithromycin:\n"
                      "  ارتبط بتشوهات خلقية في الدراسات الحيوانية والبشرية.\n"
                      "  البديل الآمن: Azithromycin."),
        "child_safe": True, "interacts_with": [],
        "aliases": ["klacid","biaxin"],
        "organisms": ["Staphylococcus aureus","Streptococcus pneumoniae",
                      "H. influenzae","Mycoplasma spp.","Legionella pneumophila"],
        "specimen_notes": {
            "Sputum": "✅ CAP والـ atypical pneumonia.",
        },
    },
    "Trimethoprim/Sulfamethoxazole": {
        "priority": 2, "class": "Sulfonamide (Oral/IV)",
        "note": "✅ (مثل Sutrim/Bactrim) Oral وIV. Bioavailability فموي ~100%. ممتاز للمسالك والجهاز التنفسي.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Banned",
        "preg_note": ("ممنوع في الحمل — TMP/SMX:\n"
                      "  يثبط حمض الفوليك — خطر Neural Tube Defects في الـ 1st trimester.\n"
                      "  يسبب kernicterus للجنين في الـ 3rd trimester."),
        "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["septra","sutrim","bactrim","co-trimoxazole","tmp-smx"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis","Staphylococcus aureus",
                      "Stenotrophomonas maltophilia","Shigella spp.","Salmonella spp."],
        "specimen_notes": {
            "Urine":      "✅ فعال للمسالك البسيطة عند تأكيد الحساسية.",
            "Sputum":     "✅ الجهاز التنفسي — خيار أول لـ Stenotrophomonas.",
            "Wound Swab": "✅ MRSA skin infections (SSTI).",
        },
    },
    "Metronidazole": {
        "priority": 1, "class": "Nitroimidazole (Oral/IV)",
        "note": "✅ (مثل Flagyl) Oral وIV. Bioavailability فموي ~100%. الخيار الأول للأنيروبيك.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True, "aware": "Access", "high_po": True,
        "preg_status": "Warn",
        "preg_note": ("تحذير حمل — Metronidazole:\n"
                      "  تجنب في الـ 1st trimester (مخاوف تاريخية).\n"
                      "  مقبول في الـ 2nd و 3rd trimester بإشراف طبي.\n"
                      "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"),
        "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["flagyl","metro","metrogyl"],
        "organisms": ["Anaerobes (لاهوائيات)"],
        "specimen_notes": {
            "Pus":        "✅ الخراجات والعدوى المختلطة (anaerobic coverage).",
            "Wound Swab": "✅ العدوى الجراحية التي تشمل اللاهوائيات.",
            "Stool":      "✅ بعض الطفيليات والعدوى اللاهوائية.",
            "Blood":      "✅ sepsis البطن مع اشتباه anaerobic.",
        },
    },
    "Tinidazole": {
        "priority": 2, "class": "Nitroimidazole (Oral)",
        "note": "✅ (مثل Fasigyn) Oral فقط. Bioavailability ~100%. بديل Metronidazole.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True, "aware": "Access", "high_po": True,
        "preg_status": "Banned",
        "preg_note": ("ممنوع في الحمل — Tinidazole:\n"
                      "  ممنوع في الـ 1st trimester.\n"
                      "  يُفضل تجنبه طوال الحمل — استبدل بـ Metronidazole."),
        "child_safe": False,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["fasigyn","tini"],
        "organisms": ["Anaerobes (لاهوائيات)"],
        "specimen_notes": {
            "Wound Swab": "✅ عدوى اللاهوائيات الخفيفة.",
        },
    },
    "Doxycycline": {
        "priority": 2, "class": "Tetracycline (Oral/IV)",
        "note": "✅ (مثل Vibramycin) Oral وIV. Bioavailability فموي ~93%. فعال للكلاميديا والمايكوبلازما.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً نسبياً.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": ("تحذير حمل — Doxycycline:\n"
                      "  الموقف التقليدي: ممنوع (FDA Category D).\n"
                      "  الأدلة الحديثة (ACCP 2025): خطر أقل في الاستخدام القصير.\n"
                      "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["vibramycin","doxy"],
        "organisms": ["Mycoplasma spp.","Staphylococcus aureus","H. influenzae",
                      "Rickettsia spp.","Acinetobacter baumannii",
                      "Stenotrophomonas maltophilia","Legionella pneumophila"],
        "specimen_notes": {
            "Sputum":     "✅ atypical pneumonia (Mycoplasma/Legionella).",
            "Wound Swab": "✅ MRSA SSTI و Rickettsia.",
            "Blood":      "✅ Rickettsia bacteremia.",
        },
    },
    "Imipenem/Cilastatin": {
        "priority": 5, "class": "Carbapenem (IV)",
        "note": ("🛑 (مثل Tienam) IV فقط. أوسع كاربابينيم طيفاً. "
                 "⚠️ خطر نوبات صرع عند الجرعات العالية أو القصور الكلوي."),
        "renal_limit": 50,
        "renal_note": "⚠️ تعديل جرعة حتمي — يتراكم في القصور الكلوي ويزيد خطر نوبات الصرع.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Warn",
        "preg_note": ("تحذير حمل — Imipenem/Cilastatin:\n"
                      "  بيانات محدودة في الحمل البشري.\n"
                      "  يُستخدم عند الضرورة القصوى فقط.\n"
                      "  يُفضل Meropenem عند الحاجة لكاربابينيم في الحمل.\n"
                      "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"),
        "child_safe": True,
        "interacts_with": ["Valproic acid (مضادات الصرع)"],
        "aliases": ["tienam","primaxin","imipenem","imipenem cilastatin"],
        "organisms": ["Pseudomonas aeruginosa","Klebsiella spp.","E. coli",
                      "Acinetobacter baumannii","Enterococcus faecalis",
                      "Staphylococcus aureus","Proteus mirabilis",
                      "Anaerobes (لاهوائيات)"],
        "specimen_notes": {
            "Blood":  "🛑 sepsis شديد — MDR organisms.",
            "Sputum": "🛑 VAP/HAP بـ MDR organisms — بديل Meropenem.",
            "Urine":  "🛑 UTI المعقد بـ CRE عند تعذر خيارات أخرى.",
            "Pus":    "🛑 عدوى البطن الشديدة المختلطة.",
            "CSF":    "⚠️ لا يُفضل في meningitis — خطر نوبات صرع. استخدم Meropenem.",
        },
    },
    "Ertapenem": {
        "priority": 5, "class": "Carbapenem non-anti-pseudomonal (IV/IM)",
        "note": "🛑 (مثل Invanz) IV/IM — جرعة يومية واحدة. لا يغطي Pseudomonas ولا Acinetobacter.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب عند CrCl < 30.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["invanz","ertapenem"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "Staphylococcus aureus","Enterococcus faecalis",
                      "Anaerobes (لاهوائيات)"],
        "specimen_notes": {
            "Blood": "🛑 ESBL bacteremia — يفضل على Meropenem للحفاظ على الكاربابينيم.",
            "Urine": "🛑 ESBL-producing UTI المعقد فقط.",
            "Pus":   "🛑 عدوى البطن المعقدة بـ ESBL.",
        },
    },
    "Meropenem": {
        "priority": 5, "class": "Carbapenem (IV)",
        "note": "🛑 (مثل Meronem) IV فقط — الملاذ الأخير للمقاومة. أقل خطراً للصرع من Imipenem.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["meronem","merrem"],
        "organisms": ["Pseudomonas aeruginosa","Klebsiella spp.","E. coli",
                      "Enterococcus faecalis","Staphylococcus aureus","MRSA",
                      "Acinetobacter baumannii"],
        "specimen_notes": {
            "Blood":  "🛑 sepsis شديد — MDR organisms — ICU.",
            "CSF":    "🛑 meningitis المعقد — MDR — أفضل من Imipenem للـ CNS.",
            "Sputum": "🛑 VAP/HAP بـ MDR organisms.",
            "Urine":  "🛑 UTI المعقد جداً بـ CRE.",
        },
    },
    "Vancomycin": {
        "priority": 5, "class": "Glycopeptide (IV)",
        "note": "🛑 IV فقط — خاص بـ MRSA والحالات الحرجة. مراقبة الـ Trough أو AUC/MIC حتمية.",
        "renal_limit": 50, "renal_note": "⚖️ مراقبة مستوى الدواء في الدم.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Warn",
        "preg_note": ("تحذير حمل — Vancomycin:\n"
                      "  يُستخدم عند الضرورة القصوى (MRSA في الحمل).\n"
                      "  مراقبة وظائف الكلى والسمع للأم والجنين.\n"
                      "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"),
        "child_safe": True,
        "interacts_with": ["NSAIDs (مسكنات الألم)"],
        "aliases": ["vancocin","vanco"],
        "organisms": ["MRSA","Staphylococcus aureus","Enterococcus faecalis",
                      "Streptococcus pneumoniae"],
        "specimen_notes": {
            "Blood":      "🛑 MRSA bacteremia.",
            "CSF":        "🛑 MRSA meningitis.",
            "Sputum":     "🛑 MRSA pneumonia في ICU.",
            "Wound Swab": "🛑 MRSA wound infection.",
        },
    },
    "Linezolid": {
        "priority": 5, "class": "Oxazolidinone (Oral/IV)",
        "note": "🛑 (مثل Averozolid) Oral وIV. Bioavailability فموي ~100%. للموجبات المقاومة (MRSA/VRE) فقط.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": False, "aware": "Reserve", "high_po": True,
        "preg_status": "Banned",
        "preg_note": ("ممنوع في الحمل — Linezolid:\n"
                      "  أثبت سُمية جنينية في الحيوانات.\n"
                      "  يُستخدم فقط عند انعدام البدائل."),
        "child_safe": True,
        "interacts_with": ["SSRI (أدوية الاكتئاب)"],
        "aliases": ["averozolid","zyvox"],
        "organisms": ["MRSA","Staphylococcus aureus","Enterococcus faecalis",
                      "VRE","Streptococcus pneumoniae"],
        "specimen_notes": {
            "Blood":      "🛑 VRE/MRSA bacteremia.",
            "Sputum":     "🛑 MRSA pneumonia — تركيز رئوي ممتاز.",
            "Wound Swab": "🛑 MRSA/VRE wound infection.",
            "CSF":        "🛑 اختراق ممتاز للـ CNS.",
        },
    },
    "Colistin": {
        "priority": 6, "class": "Polymyxin (IV)",
        "note": "🔴 IV فقط — الملاذ الأخير للـ MDR gram-negatives. Bioavailability فموي = صفر.",
        "renal_limit": 80, "renal_note": "⚖️ سام جداً للكلى — مراقبة حتمية.",
        "hepatic_caution": False, "aware": "Reserve", "high_po": False,
        "preg_status": "Warn",
        "preg_note": "يُستخدم فقط لإنقاذ الحياة عند غياب البدائل.",
        "child_safe": True,
        "interacts_with": ["NSAIDs (مسكنات الألم)"],
        "aliases": ["colistin","polymyxin e"],
        "organisms": ["Pseudomonas aeruginosa","Acinetobacter baumannii","Klebsiella spp."],
        "specimen_notes": {
            "Blood":  "🔴 MDR/XDR bacteremia — ملاذ أخير.",
            "Sputum": "🔴 VAP بـ XDR Acinetobacter/Pseudomonas.",
        },
    },
    "Cefazolin": {
        "priority": 1, "class": "1st Gen Cephalosporin (IV/IM)",
        "note": "💉 (مثل Cefazol/Kefzol) IV/IM فقط. أكثر سيفالوسبورين استخداماً في الجراحة الوقائية.",
        "renal_limit": 35, "renal_note": "⚖️ تعديل الجرعة مطلوب عند CrCl < 35.",
        "hepatic_caution": False, "aware": "Access", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["cefazol","kefzol","cefazolin","cephazolin"],
        "organisms": ["Staphylococcus aureus","Streptococcus pneumoniae","E. coli","Proteus mirabilis"],
        "specimen_notes": {
            "Blood":      "💉 bacteremia الموجبات والسالبات البسيطة.",
            "Wound Swab": "💉 الوقاية الجراحية والعدوى البسيطة.",
            "Urine":      "💉 pyelonephritis يحتاج IV عند تأكيد الحساسية.",
        },
    },
    "Furadantin": {
        "priority": 1, "class": "Urinary Antiseptic (Oral)",
        "note": "🎯 (Nitrofurantoin — Furadantin/Macrobid) Oral فقط. مخصص للمسالك البسيطة.",
        "renal_limit": 30, "renal_note": "🚫 ممنوع إذا CrCl < 30 مل/د.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Warn",
        "preg_note": ("تحذير حمل — Furadantin:\n"
                      "  آمن في الـ 1st و 2nd trimester.\n"
                      "  ممنوع في الـ 3rd trimester.\n"
                      "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"),
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["furadantin","furadantine","macrobid","nitrofurantoin macrocrystal"],
        "organisms": ["E. coli","Staphylococcus aureus","Enterococcus faecalis","Klebsiella spp."],
        "specimen_notes": {
            "Urine": "🎯 مخصص للمسالك البولية البسيطة فقط.",
        },
    },
    "Cefoxitin": {
        "priority": 2, "class": "2nd Gen Cephalosporin / Cephamycin (IV)",
        "note": "💉 (مثل Mefoxin) IV فقط. يغطي اللاهوائيات. يُستخدم لـ MRSA screening (disk diffusion).",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["mefoxin","cefoxitin","cefox"],
        "organisms": ["Staphylococcus aureus","E. coli","Klebsiella spp.",
                      "Proteus mirabilis","Anaerobes (لاهوائيات)"],
        "specimen_notes": {
            "Wound Swab": "💉 عدوى الجروح الجراحية — يغطي اللاهوائيات.",
            "Pus":        "💉 الخراجات المختلطة — anaerobic coverage.",
            "Blood":      "⚠️ MRSA screening marker — Cefoxitin-R = MRSA.",
        },
    },
    "Ampicillin": {
        "priority": 2, "class": "Penicillin (IV/Oral)",
        "note": "⚠️ مقاومة عالية (>80%) بدون مثبط. يُستخدم مع Sulbactam (Ampicillin/Sulbactam).",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["ampicillin","ampicil","ampicilli","penbritin"],
        "organisms": ["Enterococcus faecalis","Streptococcus pneumoniae"],
        "specimen_notes": {
            "Urine": "⚠️ مقاومة عالية — تحقق من نتيجة المزرعة.",
            "Blood": "⚠️ يُستخدم مع Sulbactam للحالات المتوسطة.",
        },
    },
    "Amoxicillin": {
        "priority": 1, "class": "Penicillin (Oral)",
        "note": "✅ (مثل Amoxil) Oral. Bioavailability ~90%. بدون مثبط — مقاومة عالية لكثير من الكائنات.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["amoxil","amoxicillin","amoxycillin","amoxy","flemoxin"],
        "organisms": ["Streptococcus pneumoniae","Enterococcus faecalis","H. influenzae"],
        "specimen_notes": {
            "Urine":  "⚠️ مقاومة عالية — يُفضل Amoxicillin + Clavulanic acid.",
            "Sputum": "✅ CAP بسيط عند تأكيد الحساسية.",
        },
    },
    "Tetracycline": {
        "priority": 3, "class": "Tetracycline (Oral)",
        "note": "⚠️ (مثل Achromycin) Oral. Bioavailability ~77%. أقل تفضيلاً من Doxycycline.",
        "renal_limit": 0, "renal_note": "⚠️ تجنب في القصور الكلوي الشديد.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": ("تحذير حمل — Tetracycline:\n"
                      "  ممنوع في الـ 2nd و 3rd trimester.\n"
                      "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["achromycin","tetracycline","tetracyclin","tetracycl"],
        "organisms": ["Staphylococcus aureus","Mycoplasma spp.","H. influenzae"],
        "specimen_notes": {
            "Sputum":     "⚠️ atypical pneumonia — يُفضل Doxycycline.",
            "Wound Swab": "⚠️ SSTI — يُفضل Doxycycline.",
        },
    },
}

# ── Alias index للبحث السريع ──────────────────────────────────────────

# ── Cephradine (inject if not already in ABX_GUIDELINES) ──────────────────
def _inject_cephradine():
    if "Cephradine" not in ABX_GUIDELINES:
        ABX_GUIDELINES["Cephradine"] = {
            "class":           "Cephalosporins",
            "aware":           "Access",
            "route":           "oral",
            "high_po":         True,
            "priority":        3,
            "note":            "1st-gen cephalosporin; active vs Gram+ (staph/strep). "
                               "Oral equivalent of Cefazolin. Use for skin/soft tissue, "
                               "UTI, upper respiratory tract infections.",
            "renal_note":      "CrCl 20-50: 250mg q8h | CrCl <20: 250mg q12h",
            "renal_limit":     30,
            "preg_status":     "Safe",
            "preg_note":       "Generally considered safe in pregnancy (Category B).",
            "child_safe":      True,
            "child_note":      "Approved for children > 9 months. Dose 25-50 mg/kg/day.",
            "hepatic_caution": False,
            "hepatic_note":    "",
            "interacts_with":  [],
            "aliases":         ["Velosef", "Sefril", "Eskacef"],
            "organisms": [
                "Staphylococcus aureus", "Staphylococcus epidermidis",
                "Streptococcus pyogenes", "Streptococcus agalactiae",
                "Escherichia coli", "Klebsiella spp.", "Proteus mirabilis",
            ],
            "specimen_notes": {
                "Urine":       "Adequate for lower UTI (uncomplicated cystitis).",
                "Wound Swab":  "Good Gram+ coverage for mild-moderate wound infections.",
                "Wound/Pus":   "Good Gram+ coverage for mild-moderate wound infections.",
                "Wound / Pus": "Good Gram+ coverage for mild-moderate wound infections.",
                "Wound":       "Good Gram+ coverage for mild-moderate wound infections.",
                "Pus":         "Good Gram+ coverage for mild-moderate wound infections.",
                "Sputum":      "Limited Gram- coverage; not first choice for pneumonia.",
            },
        }

_inject_cephradine()

def _build_alias_index() -> Dict[str, str]:
    idx: Dict[str, str] = {}
    for name, info in ABX_GUIDELINES.items():
        idx[_normalize_key(name)] = name
        for alias in info.get("aliases", []):
            k = _normalize_key(alias)
            if k:
                idx[k] = name
    return idx

def _normalize_key(text: str) -> str:
    if not text:
        return ""
    t = text.lower().strip()
    t = re.sub(r"[^a-z0-9]", "", t)
    return t

ABX_ALIAS_INDEX = _build_alias_index()

def normalize_abx_key(text: str) -> str:
    return _normalize_key(text)

# =========================================================
# ملفات الكائنات الدقيقة
# =========================================================
ORGANISM_PROFILE = {
    "E. coli": {
        "first_line": ["Nitrofurantoin","Fosfomycin",
                       "Trimethoprim/Sulfamethoxazole","Amoxicillin + Clavulanic acid"],
        "second_line": ["Cefuroxime","Cefuroxime sodium","Cefixime",
                        "Norfloxacin","Ciprofloxacin"],
        "third_line":  ["Ertapenem","Meropenem"],
        "avoid": [],
        "urine_note": ("Norfloxacin: مخصص للمسالك فقط — لا تركيز علاجي خارج البول.\n"
                       "Ertapenem: يُحفظ للـ ESBL-producing E. coli فقط."),
        "specimen_context": {
            "Blood":      "🔬 الأكثر شيوعاً في bacteremia الجهاز البولي والبطن.",
            "Sputum":     "⚠️ E. coli في البلغم — نادر، يشير لـ aspiration أو HAP.",
            "Wound Swab": "🔬 شائع في عدوى الجروح الجراحية والحروق.",
            "Pus":        "🔬 شائع في خراجات البطن.",
            "Stool":      "🔬 ETEC/EPEC — إسهال المسافرين.",
        },
        "note": "🔬 الأكثر شيوعاً في مزارع البول.",
    },
    "Klebsiella spp.": {
        "first_line": ["Amoxicillin + Clavulanic acid","Cefuroxime","Cefixime"],
        "second_line": ["Cefuroxime sodium","Norfloxacin","Ciprofloxacin",
                        "Piperacillin + Tazobactam","Ceftriaxone"],
        "third_line":  ["Ertapenem","Meropenem"],
        "avoid": ["Ampicillin"],
        "urine_note": ("Ertapenem: الخيار الأول لـ ESBL-producing Klebsiella (IDSA 2023).\n"
                       "Norfloxacin: للمسالك فقط."),
        "specimen_context": {
            "Blood":      "🔬 Klebsiella bacteremia — خطر خصوصاً في الكبد.",
            "Sputum":     "🔬 HAP وعدوى الجهاز التنفسي في المستشفى.",
            "Wound Swab": "🔬 عدوى الجروح الجراحية.",
            "Pus":        "🔬 خراجات الكبد والبطن.",
            "Urine":      "🔬 الثاني الأكثر شيوعاً في مزارع البول.",
        },
        "note": "🔬 تحقق من ESBL — مقاومة طبيعية لبعض البيتا-لاكتام.",
    },
    "Pseudomonas aeruginosa": {
        "first_line": ["Piperacillin + Tazobactam","Ceftazidime","Ciprofloxacin"],
        "second_line": ["Cefepime","Cefoperazone + Sulbactam",
                        "Meropenem","Imipenem/Cilastatin","Amikacin"],
        "third_line":  ["Colistin"],
        "avoid": ["Nitrofurantoin","Fosfomycin","Trimethoprim/Sulfamethoxazole",
                  "Cephalexin","Cefadroxil","Cefaclor","Norfloxacin",
                  "Cefuroxime sodium","Ertapenem"],
        "urine_note": ("Ertapenem: ممنوع لـ Pseudomonas — لا نشاط (EUCAST).\n"
                       "Ciprofloxacin هو الفلوروكينولون الوحيد الفعال ضد Pseudomonas."),
        "specimen_context": {
            "Blood":      "🔴 Pseudomonas bacteremia — mortality عالية — ICU.",
            "Sputum":     "🔴 VAP/HAP الأكثر خطورة — anti-pseudomonal إلزامي.",
            "Wound Swab": "🔴 شائع في حروق والجروح المزمنة.",
            "Urine":      "🔴 UTI المعقد — كاتيتر أو مضادات سابقة.",
        },
        "note": "🔬 جرثومة انتهازية — تحتاج anti-pseudomonal متخصص.",
    },
    "Acinetobacter baumannii": {
        "first_line": ["Ampicillin/Sulbactam","Cefoperazone + Sulbactam"],
        "second_line": ["Meropenem","Imipenem/Cilastatin","Amikacin",
                        "Trimethoprim/Sulfamethoxazole","Doxycycline"],
        "third_line":  ["Colistin"],
        "avoid": ["Ertapenem","Cephalexin","Cefuroxime","Ceftriaxone",
                  "Azithromycin","Clarithromycin","Nitrofurantoin","Fosfomycin"],
        "specimen_context": {
            "Blood":      "🔴 Acinetobacter bacteremia — ICU — MDR غالباً.",
            "Sputum":     "🔴 VAP الأكثر شيوعاً في ICU — خطر جداً.",
            "Wound Swab": "🔴 عدوى الحروق والجروح الكبيرة.",
        },
        "note": ("🔴 MDR — Ampicillin/Sulbactam أو Cefoperazone/Sulbactam "
                 "بجرعات عالية هو الأساس (IDSA AMR 2025)."),
    },
    "Staphylococcus aureus": {
        "first_line": ["Cephalexin","Cefadroxil","Amoxicillin + Clavulanic acid"],
        "second_line": ["Cefuroxime sodium","Azithromycin","Doxycycline"],
        "third_line":  [],
        "avoid": [],
        "urine_note": ("تحقق من MRSA — إذا MRSA: Vancomycin أو Linezolid فقط.\n"
                       "S. aureus في البول → تحقق من Blood culture (hematogenous seeding)."),
        "specimen_context": {
            "Blood":      "🔬 تحقق من MRSA فوراً — خطر endocarditis.",
            "Sputum":     "🔬 pneumonia بعد الإنفلونزا أو في ICU.",
            "Wound Swab": "🔬 الأكثر شيوعاً في عدوى الجروح.",
            "Pus":        "🔬 خراجات الجلد والأنسجة الرخوة.",
            "Urine":      "⚠️ S. aureus في البول — احتمال hematogenous seeding.",
        },
        "note": "🔬 تحقق من MRSA — قد يحتاج Vancomycin.",
    },
    "MRSA": {
        "first_line": ["Vancomycin","Linezolid"],
        "second_line": ["Trimethoprim/Sulfamethoxazole","Doxycycline"],
        "third_line":  [],
        "avoid": ["Cephalexin","Cefadroxil","Cefaclor","Cefuroxime","Cefuroxime sodium",
                  "Ceftriaxone","Amoxicillin + Clavulanic acid","Ampicillin/Sulbactam",
                  "Piperacillin + Tazobactam","Ertapenem"],
        "urine_note": "جميع البيتا-لاكتام لا تعمل على MRSA (mecA gene — PBP2a resistance).",
        "specimen_context": {
            "Blood":      "🔴 MRSA bacteremia — ابدأ Vancomycin فوراً.",
            "Sputum":     "🔴 MRSA pneumonia — خطر في ICU.",
            "Wound Swab": "🔴 MRSA SSTI — شائع في المجتمع (CA-MRSA).",
            "Pus":        "🔴 MRSA abscess — drainage + Vancomycin.",
            "CSF":        "🔴 MRSA meningitis — نادر لكن خطر.",
        },
        "note": "🔴 مقاوم لجميع البيتا-لاكتام — Vancomycin أو Linezolid فقط.",
    },
    "Proteus mirabilis": {
        "first_line": ["Amoxicillin + Clavulanic acid","Cefuroxime","Cefixime"],
        "second_line": ["Cefuroxime sodium","Norfloxacin","Ciprofloxacin",
                        "Trimethoprim/Sulfamethoxazole"],
        "third_line":  ["Ertapenem"],
        "avoid": ["Nitrofurantoin","Tetracyclines","Colistin"],
        "urine_note": ("Nitrofurantoin: مقاوم طبيعياً لـ Proteus (intrinsic) — EUCAST.\n"
                       "Norfloxacin: فعال في UTI فقط."),
        "specimen_context": {
            "Urine":      "🔬 شائع في UTI — يرفع الـ pH (urease).",
            "Wound Swab": "🔬 عدوى الجروح المزمنة والقدم السكري.",
            "Blood":      "⚠️ Proteus bacteremia — مصدره البولي غالباً.",
        },
        "note": "🔬 مقاوم طبيعياً لـ Nitrofurantoin — لا تستخدمه أبداً.",
    },
    "Enterococcus faecalis": {
        "first_line": ["Amoxicillin + Clavulanic acid","Fosfomycin","Nitrofurantoin"],
        "second_line": ["Ampicillin/Sulbactam","Vancomycin","Linezolid"],
        "third_line":  [],
        "avoid": ["Cephalosporins (كل الجيل)","Trimethoprim/Sulfamethoxazole",
                  "Cefuroxime sodium","Ertapenem","Norfloxacin"],
        "urine_note": ("Ertapenem وCefuroxime sodium: لا نشاط ضد Enterococcus (EUCAST).\n"
                       "جميع السيفالوسبورين مقاومة طبيعياً لـ Enterococcus."),
        "specimen_context": {
            "Urine":      "🔬 شائع في UTI خصوصاً الكاتيتر.",
            "Blood":      "⚠️ Enterococcus bacteremia — خطر endocarditis.",
            "Wound Swab": "⚠️ عدوى البطن والجروح الجراحية.",
        },
        "note": "🔬 مقاوم طبيعياً للسيفالوسبورين — Amoxicillin هو الأساس.",
    },
    "Salmonella spp.": {
        "first_line": ["Ceftriaxone","Azithromycin","Ciprofloxacin"],
        "second_line": ["Trimethoprim/Sulfamethoxazole","Cefixime"],
        "third_line":  [],
        "avoid": ["Nitrofurantoin","Fosfomycin","Cephalexin","Cefadroxil",
                  "Cefaclor","Cefuroxime","Metronidazole","Doxycycline"],
        "urine_note": "",
        "specimen_context": {
            "Stool": "🔬 Salmonella gastroenteritis — العلاج للحالات الشديدة فقط.",
            "Blood": "🔬 Typhoid fever — Ceftriaxone أو Azithromycin.",
        },
        "note": "🔬 العلاج مخصص للحالات الشديدة أو الحمى التيفودية فقط.",
    },
    "Shigella spp.": {
        "first_line": ["Azithromycin","Ciprofloxacin","Ceftriaxone"],
        "second_line": ["Trimethoprim/Sulfamethoxazole"],
        "third_line":  [],
        "avoid": ["Nitrofurantoin","Fosfomycin","Amoxicillin + Clavulanic acid","Metronidazole"],
        "urine_note": "",
        "specimen_context": {
            "Stool": "🔬 Shigellosis — العلاج يقلل الأعراض ويمنع الانتشار.",
            "Blood": "🔬 نادراً ما يصل للدم إلا في الحالات الشديدة.",
        },
        "note": "🔬 تعالج الحالات الوخيمة — مقاومة عالية لـ TMP/SMX في مصر.",
    },
    "Campylobacter jejuni": {
        "first_line": ["Azithromycin"],
        "second_line": ["Ciprofloxacin"],
        "third_line":  [],
        "avoid": ["Trimethoprim/Sulfamethoxazole","Nitrofurantoin","Fosfomycin"],
        "urine_note": "",
        "specimen_context": {
            "Stool": "🔬 أشهر أسباب الإسهال البكتيري — غالباً محدود ذاتياً.",
            "Blood": "🔬 Bacteremia نادر في نقص المناعة.",
        },
        "note": "🔬 معظم الحالات لا تحتاج مضادات — Azithromycin عند الحاجة.",
    },
    "Streptococcus pneumoniae": {
        "first_line": ["Amoxicillin + Clavulanic acid","Ceftriaxone","Levofloxacin"],
        "second_line": ["Azithromycin","Clarithromycin","Cefuroxime"],
        "third_line":  ["Vancomycin","Linezolid"],
        "avoid": [],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔬 السبب الأول لـ CAP — تحقق من مقاومة Penicillin.",
            "Blood":  "🔬 Pneumococcal bacteremia — خطر في المسنين.",
            "CSF":    "🔬 السبب الأول لـ bacterial meningitis في البالغين.",
        },
        "note": "🔬 السبب الأول لـ CAP والـ meningitis. تحقق من MIC للـ Penicillin.",
    },
    "H. influenzae": {
        "first_line": ["Amoxicillin + Clavulanic acid","Cefuroxime","Ceftriaxone"],
        "second_line": ["Azithromycin","Levofloxacin","Trimethoprim/Sulfamethoxazole"],
        "third_line":  [],
        "avoid": ["Ampicillin (alone)"],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔬 شائع في COPD exacerbation و CAP.",
            "Blood":  "⚠️ H. influenzae bacteremia — نادر بعد التطعيم.",
            "CSF":    "⚠️ H. influenzae meningitis — نادر جداً الآن.",
        },
        "note": "🔬 30% ينتجون beta-lactamase — Amoxicillin/Clavulanate مفضل.",
    },
    "Legionella pneumophila": {
        "first_line": ["Levofloxacin","Azithromycin"],
        "second_line": ["Doxycycline","Clarithromycin"],
        "third_line":  [],
        "avoid": ["Beta-lactams (alone)","Aminoglycosides","Cephalosporins (alone)"],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔬 Legionella — CAP الشديد، خاصةً في الفنادق أو مكيفات الهواء.",
            "Blood":  "⚠️ Bacteremia نادر — التشخيص بـ Urine Antigen أو PCR.",
        },
        "note": "🔬 Levofloxacin هو الخيار الأول. لا يُعزل بالزراعة العادية — يحتاج وسط BCYE.",
    },
    "Mycoplasma spp.": {
        "first_line": ["Azithromycin","Doxycycline"],
        "second_line": ["Levofloxacin","Clarithromycin"],
        "third_line":  [],
        "avoid": ["Beta-lactams","Cephalosporins","Vancomycin","Aminoglycosides"],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔬 Atypical pneumonia — Walking pneumonia — خاصةً في الشباب.",
        },
        "note": "🔬 لا جدار خلوي — كل البيتا-لاكتام غير فعالة. يُشخص بـ PCR أو Serology.",
    },
    "Anaerobes (لاهوائيات)": {
        "first_line": ["Metronidazole","Amoxicillin + Clavulanic acid"],
        "second_line": ["Piperacillin + Tazobactam","Meropenem",
                        "Imipenem/Cilastatin","Ampicillin/Sulbactam"],
        "third_line":  [],
        "avoid": ["Aminoglycosides","Nitrofurantoin"],
        "urine_note": "",
        "specimen_context": {
            "Pus":        "🔬 الخراجات داخل البطن — Metronidazole ضروري.",
            "Wound Swab": "🔬 العدوى الجراحية بعد عمليات الأمعاء.",
            "Blood":      "🔬 Bacteremia اللاهوائيات — مصدره البطن غالباً.",
        },
        "note": "🔬 Metronidazole هو الخيار الأول لكل اللاهوائيات.",
    },
    "Stenotrophomonas maltophilia": {
        "first_line": ["Trimethoprim/Sulfamethoxazole"],
        "second_line": ["Levofloxacin","Doxycycline"],
        "third_line":  [],
        "avoid": ["Carbapenems","Ertapenem","Meropenem","Imipenem/Cilastatin",
                  "Aminoglycosides","Ceftriaxone","Cefepime"],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔴 شائع في VAP/HAP في ICU — خاصةً بعد علاج طويل بالكاربابينيم.",
            "Blood":  "🔴 Stenotrophomonas bacteremia — نادر لكن خطر في المناعة الضعيفة.",
        },
        "note": "🔴 مقاومة طبيعية للكاربابينيم! TMP/SMX هو الخيار الأول. ينتقى بعد Meropenem.",
    },
}

# ─── خريطة العينات → البكتيريا ───────────────────────────────────────
SPECIMEN_ORGANISM_MAP = {
    "Urine": ["E. coli","Klebsiella spp.","Proteus mirabilis",
              "Enterococcus faecalis","Staphylococcus aureus","MRSA",
              "Pseudomonas aeruginosa","Acinetobacter baumannii"],
    "Blood": ["E. coli","Klebsiella spp.","Staphylococcus aureus","MRSA",
              "Pseudomonas aeruginosa","Acinetobacter baumannii",
              "Streptococcus pneumoniae","Enterococcus faecalis",
              "Salmonella spp.","Proteus mirabilis",
              "Anaerobes (لاهوائيات)","Stenotrophomonas maltophilia"],
    "Sputum": ["Streptococcus pneumoniae","H. influenzae","Klebsiella spp.",
               "Pseudomonas aeruginosa","Acinetobacter baumannii","MRSA",
               "Staphylococcus aureus","E. coli","Legionella pneumophila",
               "Mycoplasma spp.","Stenotrophomonas maltophilia"],
    "Wound Swab": ["Staphylococcus aureus","MRSA","E. coli","Klebsiella spp.",
                   "Pseudomonas aeruginosa","Proteus mirabilis","Acinetobacter baumannii",
                   "Enterococcus faecalis","Anaerobes (لاهوائيات)"],
    "Pus": ["Staphylococcus aureus","MRSA","E. coli","Klebsiella spp.",
            "Pseudomonas aeruginosa","Acinetobacter baumannii",
            "Anaerobes (لاهوائيات)","Enterococcus faecalis","Proteus mirabilis"],
    "Stool": ["Salmonella spp.","Shigella spp.","Campylobacter jejuni","E. coli"],
    "CSF": ["Streptococcus pneumoniae","H. influenzae","MRSA",
            "Staphylococcus aureus","E. coli","Klebsiella spp."],
}

BACTERIA_TYPES = list(ORGANISM_PROFILE.keys())
SPECIMEN_TYPES = ["Urine","Blood","Sputum","Wound Swab","Pus","Stool","CSF"]

# =========================================================
# الثوابت
# =========================================================
SESSION_TIMEOUT = 30 * 60
SIR_LABELS      = {"S": "Sensitive", "I": "Intermediate", "R": "Resistant"}
AWARE_COLORS    = {"Access": "🟢 Access", "Watch": "🟡 Watch", "Reserve": "🔴 Reserve"}

# ── Commercial Names Loader ───────────────────────────────────────────
def load_commercial_names(filepath: str = "commercial_names.txt") -> Dict[str, str]:
    result: Dict[str, str] = {}
    import os as _os
    # حاول المسارات المحتملة بالترتيب
    candidates = [
        filepath,
        _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), filepath),
        _os.path.join(_os.getcwd(), filepath),
    ]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        generic, _, brands = line.partition("=")
                        generic = generic.strip()
                        brands  = brands.strip()
                        if generic and brands:
                            result[generic.lower()] = brands
            if result:
                break
        except FileNotFoundError:
            continue
        except Exception:
            continue
    return result

COMMERCIAL_NAMES: Dict[str, str] = load_commercial_names()

def get_commercial_name(generic: str) -> str:
    return COMMERCIAL_NAMES.get(generic.lower(), "")
COMMON_MEDS     = [
    "Antacids (مضادات الحموضة)",
    "Warfarin (مضادات التخثر)",
    "NSAIDs (مسكنات الألم)",
    "SSRI (أدوية الاكتئاب)",
    "Valproic acid (مضادات الصرع)",
]

ORGANISM_AVOID_CLASS_MAP = {
    "cephalosporins (كل الجيل)": ["cephalosporin"],
    "cephalosporins":            ["cephalosporin"],
    "tetracyclines":             ["tetracycline"],
    "aminoglycosides":           ["aminoglycoside"],
    "carbapenems":               ["carbapenem"],
    "beta-lactams (alone)":      ["penicillin","cephalosporin","carbapenem"],
    "beta-lactams":              ["penicillin","cephalosporin","carbapenem"],
}

RENAL_BAN_REASONS = {
    "nitrofurantoin": (
        "Nitrofurantoin يحتاج وظيفة كلى سليمة ليتركز في البول.\n"
        "عند CrCl < 30 مل/د:\n"
        "- لا يصل لتركيز علاجي في البول → لا يقتل الجرثومة.\n"
        "- يتراكم في الدم → خطر سُمية رئوية وعصبية.\n"
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

# =========================================================
# MDR / XDR / PDR Classification
# =========================================================
MDR_CATEGORIES = {
    "Aminoglycosides":                ["Gentamicin","Amikacin"],
    "Antipseudomonal Penics":         ["Piperacillin + Tazobactam"],
    "Extended-Sp Cephalosporins":     ["Ceftriaxone","Cefotaxime","Cefixime","Cefuroxime"],
    "Carbapenems":                    ["Imipenem/Cilastatin","Meropenem","Ertapenem"],
    "Fluoroquinolones":               ["Ciprofloxacin","Levofloxacin","Ofloxacin","Norfloxacin"],
    "Folate PI":                      ["Trimethoprim/Sulfamethoxazole"],
    "Penicillins+BLI":                ["Amoxicillin + Clavulanic acid","Ampicillin/Sulbactam"],
    "Polymyxins":                     ["Colistin"],
    "Cephalosporins-4th":             ["Cefepime"],
    "Cephalosporins-3rd-AP":          ["Ceftazidime","Cefoperazone","Cefoperazone + Sulbactam"],
    "Glycopeptides":                  ["Vancomycin"],
    "Oxazolidinones":                 ["Linezolid"],
    "Nitrofurans":                    ["Nitrofurantoin"],
    "Fosfomycins":                    ["Fosfomycin"],
}

MDR_INFO = {
    "MDR": {
        "label":  "MDR — Multi-Drug Resistant",
        "color":  "warning",
        "icon":   "⚠️",
        "detail": "مقاوم لعامل واحد على الأقل في 3 فئات دوائية أو أكثر.",
        "action": "تجنب الأدوية المقاومة. استشر الصيدلي السريري.",
    },
    "XDR": {
        "label":  "XDR — Extensively Drug Resistant",
        "color":  "error",
        "icon":   "🔴",
        "detail": "مقاوم لمعظم الفئات الدوائية — حساس لفئتين أو أقل فقط.",
        "action": "يستلزم استشارة متخصص. الخيارات محدودة جداً.",
    },
    "PDR": {
        "label":  "PDR — Pan-Drug Resistant",
        "color":  "error",
        "icon":   "🚨",
        "detail": "مقاوم لجميع الفئات الدوائية المتاحة.",
        "action": "حالة طارئة — استشارة معدية فورية. لا خيارات قياسية.",
    },
}

def classify_mdr(organism: str, sir_map: Dict[str, str]) -> Dict[str, Any]:
    if not sir_map:
        return {"level": None, "resistant_categories": [], "total_tested": 0}
    resistant_cats   = []
    susceptible_cats = []
    for cat, drugs in MDR_CATEGORIES.items():
        tested = [d for d in drugs if d in sir_map]
        if not tested:
            continue
        if any(sir_map.get(d) == "R" for d in tested):
            resistant_cats.append(cat)
        else:
            susceptible_cats.append(cat)
    total_cats = len(resistant_cats) + len(susceptible_cats)
    r_count    = len(resistant_cats)
    if total_cats == 0:
        return {"level": None, "resistant_categories": [], "total_tested": 0}
    if r_count >= total_cats:
        level = "PDR"
    elif total_cats - r_count <= 2 and r_count > 0:
        level = "XDR"
    elif r_count >= 3:
        level = "MDR"
    else:
        level = None
    return {
        "level":                  level,
        "resistant_categories":   resistant_cats,
        "susceptible_categories": susceptible_cats,
        "total_tested":           total_cats,
        "resistant_count":        r_count,
    }

# =========================================================
# ESBL Predictor
# =========================================================
ESBL_PRODUCERS = [
    "Klebsiella spp.","E. coli","Proteus mirabilis",
    "Klebsiella pneumoniae","Enterobacter cloacae",
]
ESBL_MARKERS = {
    "high":   ["Ceftriaxone","Cefotaxime","Ceftazidime","Cefepime"],
    "medium": ["Cefuroxime","Cefixime","Cefaclor","Cephalexin"],
}

def predict_esbl(organism: str, sir_map: Dict[str, str]) -> Dict[str, Any]:
    if not sir_map:
        return {"probability": None}
    is_producer = any(p.lower() in organism.lower() for p in ESBL_PRODUCERS)
    if not is_producer:
        return {"probability": None}
    high_R = [d for d in ESBL_MARKERS["high"]   if sir_map.get(d) == "R"]
    med_R  = [d for d in ESBL_MARKERS["medium"] if sir_map.get(d) == "R"]
    carb_R = any(sir_map.get(d) == "R"
                 for d in ["Imipenem/Cilastatin","Meropenem","Ertapenem"])
    if carb_R and len(high_R) >= 2:
        return {
            "probability": "carbapenemase",
            "markers_R":   high_R,
            "detail":      "نمط يُشير لإنزيم Carbapenemase (KPC/MBL/OXA). تحقق فوراً.",
            "action":      "أرسل للمختبر المرجعي. ارفع بروتوكول العزل.",
        }
    elif len(high_R) >= 2:
        return {
            "probability": "high",
            "markers_R":   high_R,
            "detail":      f"مقاومة لـ {', '.join(high_R)} — احتمال ESBL مرتفع.",
            "action":      "استخدم Carbapenems للعدوى الشديدة. تجنب Cephalosporins.",
        }
    elif len(high_R) == 1 or len(med_R) >= 2:
        return {
            "probability": "moderate",
            "markers_R":   high_R + med_R,
            "detail":      "نمط مقاومة يستدعي إجراء تأكيد ESBL.",
            "action":      "أجرِ Double Disk Synergy Test أو PCR للتأكيد.",
        }
    return {"probability": "low"}

# =========================================================
# Pathogenicity Assessment Module — v2
# =========================================================
# =========================================================
# Pathogenicity Assessment Module — v2
# Covers: Urine, Sputum (Murray-Washington), Blood (SIRS),
#         Wound/Pus, CSF, Swab
# Includes: Pediatric thresholds, ABU detection
# =========================================================
def assess_pathogenicity(
    specimen: str,
    organism: str,
    colony_count_text: str,
    culture_purity: str,
    symptoms: list,
    pus_cells_text: str,
    urinalysis_result: str,
    gram_stain: str,
    age: int,
    sex: str,
    host_factors: list,
    # Sputum-specific
    sputum_pus_cells: str = "",
    sputum_epithelial: str = "",
    # Blood-specific (SIRS)
    sirs_criteria: list = None,
    blood_source: str = "",
    # Wound-specific
    wound_type: str = "",
) -> dict:
    """
    Pathogenicity Score Engine v2
    Returns: {score, verdict, color, interpretation, recommendations,
              factors_pos, factors_neg, abu_detected, special_flags}
    """
    if sirs_criteria is None:
        sirs_criteria = []

    score        = 0
    factors_pos  = []
    factors_neg  = []
    special_flags = []
    abu_detected  = False

    # ── Organism Lists ────────────────────────────────────────────────
    TYPICAL_UROPATHOGENS = [
        "Escherichia coli", "Klebsiella pneumoniae", "Klebsiella spp.",
        "Proteus mirabilis", "Proteus spp.", "Enterococcus faecalis",
        "Enterococcus spp.", "Staphylococcus saprophyticus",
        "Pseudomonas aeruginosa", "Enterobacter spp.", "Enterobacter cloacae",
        "Citrobacter spp.", "Morganella morganii", "Serratia marcescens",
    ]
    ATYPICAL_UROPATHOGENS = [
        "Staphylococcus aureus", "Staphylococcus epidermidis",
        "Streptococcus viridans", "Corynebacterium spp.",
        "Candida albicans", "Candida spp.",
    ]
    NORMAL_SKIN_FLORA = [
        "Staphylococcus epidermidis", "Corynebacterium spp.",
        "Streptococcus viridans",
    ]
    RESPIRATORY_PATHOGENS = [
        "Streptococcus pneumoniae", "Haemophilus influenzae",
        "Klebsiella pneumoniae", "Pseudomonas aeruginosa",
        "Staphylococcus aureus", "Moraxella catarrhalis",
        "Acinetobacter baumannii", "Enterobacter spp.",
        "Escherichia coli", "Serratia marcescens",
    ]
    URT_CONTAMINANTS_SPUTUM = [
        "Streptococcus viridans", "Neisseria spp.", "Candida spp.",
        "Candida albicans", "Staphylococcus epidermidis",
        "Corynebacterium spp.",
    ]
    TRUE_BLOOD_PATHOGENS = [
        "Staphylococcus aureus", "Streptococcus pneumoniae",
        "Escherichia coli", "Klebsiella pneumoniae", "Pseudomonas aeruginosa",
        "Acinetobacter baumannii", "Enterococcus faecalis", "Enterococcus spp.",
        "Candida albicans", "Candida spp.", "Salmonella spp.",
        "Neisseria meningitidis", "Listeria monocytogenes",
    ]
    BLOOD_CONTAMINANTS = [
        "Staphylococcus epidermidis", "Corynebacterium spp.",
        "Bacillus spp.", "Propionibacterium spp.", "Micrococcus spp.",
    ]

    spec_lower = specimen.lower()

    # ══════════════════════════════════════════════════════════════════
    # URINE
    # ══════════════════════════════════════════════════════════════════
    if "urine" in spec_lower:

        # Pediatric threshold: < 2 years → any growth significant
        if age < 2:
            score += 20
            factors_pos.append(f"✅ Infant < 2 yrs — any colony count clinically significant")
            special_flags.append("PEDIATRIC_UTI")

        # Organism context
        if organism in TYPICAL_UROPATHOGENS:
            score += 20
            factors_pos.append(f"✅ {organism} — typical uropathogen")
        elif organism in ATYPICAL_UROPATHOGENS:
            score -= 20
            factors_neg.append(f"⚠️ {organism} — atypical uropathogen; consider contamination or hematogenous seeding")
        else:
            score += 5
            factors_pos.append(f"➕ {organism} — occasional uropathogen")

        # Colony count
        cfu_val = _parse_cfu(colony_count_text)
        if age < 2:
            # Pediatric: ≥ 10⁴ = significant
            if cfu_val >= 10000:
                score += 20
                factors_pos.append(f"✅ Colony count ≥ 10⁴ CFU/mL (significant for age < 2)")
            elif cfu_val > 0:
                score += 5
                factors_pos.append(f"➕ Colony count {cfu_val:,} — borderline (pediatric)")
        elif sex == "Female" and age >= 12:
            # IDSA: ≥ 10³ symptomatic, ≥ 10⁵ asymptomatic
            if cfu_val >= 100000:
                score += 25
                factors_pos.append("✅ Colony count ≥ 10⁵ CFU/mL — significant bacteriuria")
            elif cfu_val >= 1000:
                score += 12
                factors_pos.append("➕ Colony count 10³–10⁵ — significant if symptomatic (female)")
            elif cfu_val > 0:
                score -= 10
                factors_neg.append(f"⚠️ Colony count {cfu_val:,} < 10³ — likely insignificant")
        else:
            # Male / general
            if cfu_val >= 100000:
                score += 25
                factors_pos.append("✅ Colony count ≥ 10⁵ CFU/mL — significant bacteriuria")
            elif cfu_val >= 10000:
                score += 10
                factors_pos.append("➕ Colony count 10⁴–10⁵ CFU/mL — borderline")
            elif cfu_val > 0:
                score -= 15
                factors_neg.append(f"⚠️ Colony count {cfu_val:,} < 10⁴ — likely insignificant")

        # Pyuria / Urinalysis
        pus_val = _parse_pus(pus_cells_text)
        if pus_val is not None:
            if pus_val > 10:
                score += 20
                factors_pos.append(f"✅ Significant pyuria ({pus_val} WBC/HPF)")
            elif pus_val >= 5:
                score += 10
                factors_pos.append(f"➕ Mild pyuria ({pus_val} WBC/HPF)")
            else:
                score -= 15
                factors_neg.append(f"⚠️ No/minimal pyuria ({pus_val} WBC/HPF) — argues against UTI")
        elif "طبيعي" in urinalysis_result or "normal" in urinalysis_result.lower():
            score -= 25
            factors_neg.append("❌ Normal urinalysis — strongly suggests contamination")
        elif "pyuria" in urinalysis_result.lower() or "wbc" in urinalysis_result.lower():
            score += 15
            factors_pos.append("✅ Pyuria noted on urinalysis")
        elif "nitrit" in urinalysis_result.lower():
            score += 10
            factors_pos.append("➕ Nitrites positive — bacterial activity")

        # ABU Detection
        classic_symp = [s for s in symptoms if s in [
            "Dysuria / Frequency / Urgency", "Fever (> 38°C)", "Flank pain / Loin pain"
        ]]
        if not classic_symp and cfu_val >= 100000 and pus_val is not None and pus_val >= 5:
            abu_detected = True
            special_flags.append("ABU_DETECTED")
            # ABU: treat only if pregnant or pre-surgery
            if "Pregnant" in host_factors or "Pre-surgical" in host_factors:
                score += 20
                factors_pos.append("✅ ABU in high-risk context (pregnancy/pre-op) — TREAT")
                special_flags.append("ABU_TREAT")
            else:
                score -= 20
                factors_neg.append("⚠️ Asymptomatic Bacteriuria (ABU) — Do NOT treat (IDSA 2019)")
                special_flags.append("ABU_NO_TREAT")

        # Sex & Age context
        if sex == "Female":
            score += 10
            factors_pos.append("➕ Female — higher UTI prevalence")
        if sex == "Male" and 15 <= age <= 50:
            score -= 5
            factors_neg.append("⚠️ Male (non-pediatric/non-elderly) — UTI uncommon")
        if sex == "Male" and age > 50:
            score += 10
            factors_pos.append("➕ Male > 50 — prostatic age, any UTI is significant")
        if age < 1:
            score += 15
            factors_pos.append("✅ Infant < 1 yr — all UTIs require treatment")

    # ══════════════════════════════════════════════════════════════════
    # SPUTUM — Murray-Washington criteria
    # ══════════════════════════════════════════════════════════════════
    elif "sputum" in spec_lower or "respiratory" in spec_lower or "bal" in spec_lower:

        # Murray-Washington score from WBCs & epithelial cells
        mw_pus   = _parse_pus(sputum_pus_cells)   # WBC/LPF
        mw_epith = _parse_pus(sputum_epithelial)   # Epithelial cells/LPF

        if mw_pus is not None and mw_epith is not None:
            if mw_pus >= 25 and mw_epith < 10:
                score += 30
                factors_pos.append(f"✅ Murray-Washington Grade ≥4: WBC≥25, Epi<10/LPF — Adequate sputum")
                special_flags.append("MW_ADEQUATE")
            elif mw_pus >= 25 and mw_epith >= 10:
                score += 10
                factors_pos.append(f"➕ Murray-Washington: WBC≥25 but Epi≥10 — mixed quality")
                special_flags.append("MW_MIXED")
            elif mw_epith >= 25:
                score -= 20
                factors_neg.append(f"❌ Murray-Washington: Epi≥25/LPF — heavily contaminated, reject specimen")
                special_flags.append("MW_REJECT")
            else:
                score += 5
        elif mw_epith is not None and mw_epith >= 25:
            score -= 20
            factors_neg.append("❌ Epithelial cells ≥25/LPF — specimen inadequate (saliva)")
            special_flags.append("MW_REJECT")

        # Organism context
        if organism in RESPIRATORY_PATHOGENS:
            score += 20
            factors_pos.append(f"✅ {organism} — recognized respiratory pathogen")
        elif organism in URT_CONTAMINANTS_SPUTUM:
            score -= 20
            factors_neg.append(f"⚠️ {organism} — likely URT/oropharyngeal contaminant")
        else:
            score += 5

        # Symptoms
        resp_symp = [s for s in symptoms if s in [
            "Productive cough / Purulent sputum",
            "Fever (> 38°C)", "Dyspnea", "Pleuritic chest pain"
        ]]
        if len(resp_symp) >= 2:
            score += 20
            factors_pos.append(f"✅ {len(resp_symp)} respiratory symptoms present")
        elif len(resp_symp) == 1:
            score += 10
            factors_pos.append("➕ 1 respiratory symptom present")

    # ══════════════════════════════════════════════════════════════════
    # BLOOD CULTURE — SIRS criteria
    # ══════════════════════════════════════════════════════════════════
    elif "blood" in spec_lower:

        # SIRS criteria (≥2 = SIRS, ≥3 = high probability sepsis)
        sirs_count = len(sirs_criteria)
        if sirs_count >= 3:
            score += 35
            factors_pos.append(f"✅ {sirs_count}/4 SIRS criteria met — high sepsis probability")
            special_flags.append("SIRS_HIGH")
        elif sirs_count == 2:
            score += 20
            factors_pos.append(f"➕ 2/4 SIRS criteria met — bacteremia possible")
            special_flags.append("SIRS_MET")
        elif sirs_count == 1:
            score += 10
            factors_pos.append("➕ 1 SIRS criterion — low probability bacteremia")
        else:
            score += 5
            factors_neg.append("⚠️ No SIRS criteria — consider contaminant especially for CoNS")

        # Organism type
        if organism in TRUE_BLOOD_PATHOGENS:
            score += 25
            factors_pos.append(f"✅ {organism} — true bloodstream pathogen; single positive = significant")
        elif organism in BLOOD_CONTAMINANTS:
            score -= 20
            factors_neg.append(f"⚠️ {organism} — common blood culture contaminant (CoNS/Coryne); requires ≥2 bottles")
            special_flags.append("BLOOD_CONTAMINANT_RISK")
        else:
            score += 15
            factors_pos.append(f"➕ {organism} — possible bloodstream pathogen")

        # Number of positive bottles
        if "Multiple bottles positive" in blood_source:
            score += 15
            factors_pos.append("✅ Multiple blood culture bottles positive — true bacteremia")
        elif "Single bottle" in blood_source and organism in BLOOD_CONTAMINANTS:
            score -= 15
            factors_neg.append("⚠️ Single bottle + contaminant organism — likely contamination")

        # Source identified
        if blood_source and "source" in blood_source.lower():
            score += 10
            factors_pos.append(f"➕ Source identified: {blood_source}")

    # ══════════════════════════════════════════════════════════════════
    # CSF
    # ══════════════════════════════════════════════════════════════════
    elif "csf" in spec_lower or "cerebrospinal" in spec_lower:
        score += 40
        factors_pos.append("✅ CSF — any growth is always clinically significant (sterile site)")
        special_flags.append("CSF_ALWAYS_SIGNIFICANT")

    # ══════════════════════════════════════════════════════════════════
    # WOUND / PUS
    # ══════════════════════════════════════════════════════════════════
    elif any(w in spec_lower for w in ["wound", "pus", "abscess", "swab"]):
        wound_lower = wound_type.lower() if wound_type else ""

        if organism in NORMAL_SKIN_FLORA and not wound_lower:
            score += 10
            factors_pos.append(f"➕ {organism} — possible wound pathogen, assess clinical context")
        else:
            score += 25
            factors_pos.append(f"✅ {organism} — likely wound pathogen")

        # Wound type context
        if "surgical" in wound_lower or "post-op" in wound_lower:
            score += 15
            factors_pos.append("✅ Post-surgical wound — any growth is significant")
        elif "chronic" in wound_lower or "diabetic" in wound_lower:
            score += 10
            factors_pos.append("➕ Chronic/diabetic wound — higher clinical significance")
        elif "superficial" in wound_lower:
            score -= 5
            factors_neg.append("➕ Superficial wound — assess depth and clinical signs")

        # Symptoms
        wound_symp = [s for s in symptoms if s in [
            "Erythema / Warmth / Swelling",
            "Purulent discharge",
            "Fever (> 38°C)",
            "Pain / Tenderness",
        ]]
        if len(wound_symp) >= 2:
            score += 20
            factors_pos.append(f"✅ {len(wound_symp)} local infection signs present")
        elif len(wound_symp) == 1:
            score += 10

    # ══════════════════════════════════════════════════════════════════
    # Shared factors (all specimens)
    # ══════════════════════════════════════════════════════════════════

    # Culture purity
    if culture_purity == "Pure growth":
        score += 15
        factors_pos.append("✅ Pure culture — supports true infection")
    elif culture_purity == "Mixed growth":
        score -= 15
        factors_neg.append("⚠️ Mixed growth — suggests contamination")

    # Gram stain
    if "WBCs + Gram" in gram_stain:
        score += 15
        factors_pos.append("✅ Gram stain: organisms + WBCs — supports infection")
    elif "Organisms" in gram_stain and "بدون" not in gram_stain and "without" not in gram_stain.lower():
        score += 5
        factors_pos.append("➕ Organisms seen on Gram stain")
    elif "طبيعية" in gram_stain or "No organisms" in gram_stain:
        score -= 10
        factors_neg.append("⚠️ Normal Gram stain — no organisms seen")

    # Host factors
    if "Immunosuppressants / Steroids" in host_factors:
        score += 10
        factors_pos.append("➕ Immunocompromised — lower threshold for clinical significance")
    if "Diabetes" in host_factors:
        score += 5
        factors_pos.append("➕ Diabetes — increased infection susceptibility")
    if "تاريخ UTIs متكررة" in host_factors or "Recurrent infections" in host_factors:
        score += 5
        factors_pos.append("➕ Recurrent infection history")
    if "Urinary catheter" in host_factors or "Central line / PICC" in host_factors or "Catheter" in host_factors:
        score += 10
        factors_pos.append("➕ Indwelling device — lower threshold for significance")
    if "Renal abnormality / Vesicoureteral reflux" in host_factors:
        score += 10
        factors_pos.append("➕ Structural abnormality — increased susceptibility")
    if "Pregnant" in host_factors:
        score += 10
        factors_pos.append("✅ Pregnancy — any bacteriuria requires treatment")
    if not host_factors:
        score -= 5
        factors_neg.append("➕ No host risk factors identified")

    # Pediatric global flag
    if age < 3 and "PEDIATRIC_UTI" not in special_flags and "csf" not in spec_lower:
        score += 5
        factors_pos.append("➕ Young child — higher clinical vigilance warranted")

    # ── Clamp ────────────────────────────────────────────────────────
    score = max(0, min(100, score))

    # ── Verdict ──────────────────────────────────────────────────────
    if "CSF_ALWAYS_SIGNIFICANT" in special_flags:
        verdict = "🔴 ALWAYS SIGNIFICANT — Treat Immediately"
        color   = "error"
        interpretation = "العينة من موقع معقم (CSF) — أي نمو يُعدّ مرضياً بغض النظر عن العوامل الأخرى."
        recommendations = [
            "ابدأ العلاج التجريبي فوراً ريثما تظهر نتيجة الحساسية.",
            "استشر طبيب الأمراض المعدية.",
            "احتجز المريض ومراقبته بشكل مكثف.",
        ]
    elif "MW_REJECT" in special_flags:
        verdict = "🟢 SPECIMEN INADEQUATE — Reject & Repeat"
        color   = "success"
        interpretation = "العينة غير مناسبة (خلايا طلائية ≥25/LPF). النتيجة تعكس تلوثاً من تجويف الفم لا عدوى حقيقية."
        recommendations = [
            "ارفض العينة وأعِد طلب البلغم بتقنية صحيحة.",
            "يُفضَّل التجميع الصباحي الباكر (Early morning sputum).",
            "فكّر في BAL إذا تعذّر الحصول على عينة مناسبة.",
        ]
    elif "ABU_NO_TREAT" in special_flags:
        verdict = "🟡 ASYMPTOMATIC BACTERIURIA (ABU) — Do NOT Treat"
        color   = "warning"
        interpretation = (
            "تشير المعطيات إلى Asymptomatic Bacteriuria. وفقاً لـ IDSA 2019: "
            "لا يُنصح بالعلاج إلا في الحامل أو قبل تدخل جراحي بولي."
        )
        recommendations = [
            "لا تعطِ مضادات حيوية (Antibiotic Stewardship — IDSA 2019).",
            "تابع المريض وأعِد التقييم إذا ظهرت أعراض.",
            "استثناءات: حمل — قبيل جراحة بولية (Urology pre-op).",
        ]
    elif "ABU_TREAT" in special_flags:
        verdict = "🔴 ABU IN HIGH-RISK CONTEXT — Treat"
        color   = "error"
        interpretation = "ABU في سياق يستوجب العلاج (حمل / تدخل جراحي بولي)."
        recommendations = [
            "اختر مضاداً حيوياً مناسباً للحمل حسب نتيجة الحساسية.",
            "مدة العلاج 5–7 أيام عادةً.",
            "أعِد المزرعة بعد الانتهاء من الدورة للتأكد من الشفاء.",
        ]
    elif score >= 75:
        verdict = "🔴 Likely TRUE INFECTION — Treat"
        color   = "error"
        interpretation = (
            "المؤشرات تدعم بقوة وجود عدوى حقيقية. يُنصح بالعلاج "
            "الموجَّه بنتيجة الحساسية مع مراعاة السياق الكلينيكي."
        )
        recommendations = [
            "ابدأ العلاج بناءً على نتيجة الـ AST.",
            "راعِ شدة الأعراض وعوامل الخطر.",
            "راجع الجرعة حسب الوظيفة الكلوية.",
            "De-escalate بعد 48–72 ساعة إذا تحسّن المريض.",
        ]
    elif score >= 50:
        verdict = "🟡 POSSIBLE INFECTION — Clinical Correlation Required"
        color   = "warning"
        interpretation = (
            "النتيجة حدودية. يُنصح بالتقييم الكلينيكي الكامل قبل البدء بالعلاج. "
            "قد تحتاج فحوصات إضافية أو إعادة المزرعة."
        )
        recommendations = [
            "قيّم المريض كلينيكياً قبل إعطاء المضادات الحيوية.",
            "فكّر في إعادة المزرعة إذا كان الوضع غير واضح.",
            "راجع نتيجة الـ Urinalysis / CRP / CBC إذا لم تكن متاحة.",
        ]
    elif score >= 30:
        verdict = "🟠 LIKELY CONTAMINANT — Repeat Recommended"
        color   = "warning"
        interpretation = (
            "المؤشرات تميل نحو التلوث أو الاستعمار. "
            "يُنصح بإعادة أخذ العينة بتقنية صحيحة قبل البدء بالعلاج."
        )
        recommendations = [
            "أعِد أخذ العينة مع تحسين التقنية.",
            "لا تبدأ العلاج بناءً على هذه النتيجة وحدها.",
            "إذا تكرر العزل، فكّر في مصدر بديل (Hematogenous / Device).",
        ]
    else:
        verdict = "🟢 LIKELY CONTAMINANT / COLONIZER — Do Not Treat"
        color   = "success"
        interpretation = (
            "المؤشرات تدعم التلوث أو الاستعمار بشكل كبير. "
            "العلاج غير مبرر في الغالب. تابع المريض كلينيكياً."
        )
        recommendations = [
            "لا تعطِ مضادات حيوية بناءً على هذه النتيجة.",
            "أعِد تقييم المريض إذا استمرت الأعراض أو تطورت.",
            "التزم بمبادئ Antibiotic Stewardship.",
        ]

    return {
        "score":           score,
        "verdict":         verdict,
        "color":           color,
        "interpretation":  interpretation,
        "recommendations": recommendations,
        "factors_pos":     factors_pos,
        "factors_neg":     factors_neg,
        "abu_detected":    abu_detected,
        "special_flags":   special_flags,
    }


def _parse_cfu(text: str) -> int:
    """استخرج قيمة CFU رقمية من النص"""
    if not text:
        return 0
    t = text.lower().strip()
    if any(x in t for x in ["≥", ">=", ">10^5", ">100000", "10^5", "≥10", ">=10"]):
        if "10^5" in t or "100000" in t or "≥10^5" in t:
            return 100000
        if "10^4" in t or "10000" in t:
            return 10000
    nums = re.findall(r'[\d]+', text.replace(",", ""))
    if not nums:
        return 0
    val = int(nums[-1])
    # إذا كان الرقم صغير جداً (مثل "10" تعني 10^5 أحياناً)
    if val <= 9 and "^" in text:
        exp_match = re.findall(r'\^(\d+)', text)
        if exp_match:
            val = 10 ** int(exp_match[0])
    return val


def _parse_pus(text: str):
    """استخرج أقصى قيمة WBC/HPF من النص، أو None إذا لم يوجد"""
    if not text:
        return None
    nums = re.findall(r'[\d]+', text)
    if not nums:
        return None
    return max(int(n) for n in nums)



# =========================================================
# MODULE 1 — Resistance Phenotype Engine
# =========================================================
PHENOTYPE_RULES = {
    "MRSA": {
        "organisms": ["Staphylococcus aureus","MRSA"],
        "markers":   [("Cefoxitin","R"),("Oxacillin","R")],
        "require_any": 1,
        "icon": "🔴", "label": "MRSA — Methicillin-Resistant S. aureus",
        "detail": "مقاوم للـ Methicillin (mecA gene). جميع البيتا-لاكتام غير فعالة.",
        "action": "Vancomycin أو Linezolid. بروتوكول عزل إلزامي.",
        "isolation": True,
    },
    "VRE": {
        "organisms": ["Enterococcus faecalis","Enterococcus faecium","VRE"],
        "markers":   [("Vancomycin","R")],
        "require_any": 1,
        "icon": "🔴", "label": "VRE — Vancomycin-Resistant Enterococcus",
        "detail": "مقاوم للـ Vancomycin (vanA/vanB gene).",
        "action": "Linezolid. عزل فوري. إبلاغ مكافحة العدوى.",
        "isolation": True,
    },
    "CRE": {
        "organisms": ["Klebsiella spp.","E. coli","Proteus mirabilis","Enterobacter cloacae"],
        "markers":   [("Imipenem/Cilastatin","R"),("Meropenem","R"),("Ertapenem","R")],
        "require_any": 1,
        "icon": "🚨", "label": "CRE — Carbapenem-Resistant Enterobacteriaceae",
        "detail": "مقاوم للكاربابينيم — أخطر أنماط المقاومة.",
        "action": "Colistin + Fosfomycin. أرسل للمختبر المرجعي فوراً.",
        "isolation": True,
    },
    "CRAB": {
        "organisms": ["Acinetobacter baumannii"],
        "markers":   [("Imipenem/Cilastatin","R"),("Meropenem","R")],
        "require_any": 1,
        "icon": "🚨", "label": "CRAB — Carbapenem-Resistant Acinetobacter baumannii",
        "detail": "XDR/PDR Acinetobacter — أصعب الكائنات علاجاً في ICU.",
        "action": "Colistin ± Rifampicin. استشارة معدية.",
        "isolation": True,
    },
    "CRPA": {
        "organisms": ["Pseudomonas aeruginosa"],
        "markers":   [("Imipenem/Cilastatin","R"),("Meropenem","R"),
                      ("Piperacillin + Tazobactam","R"),("Ceftazidime","R")],
        "require_any": 2,
        "icon": "🔴", "label": "CRPA — Carbapenem-Resistant Pseudomonas aeruginosa",
        "detail": "مقاوم للكاربابينيم مع مقاومة متعددة.",
        "action": "Colistin أو Ceftolozane-Tazobactam. Combination therapy.",
        "isolation": True,
    },
}

def detect_resistance_phenotypes(organism: str, sir_map: Dict[str, str]) -> List[Dict[str, Any]]:
    if not sir_map:
        return []
    detected = []
    org_lower = organism.lower()
    for ph_name, rule in PHENOTYPE_RULES.items():
        if not any(o.lower() in org_lower or org_lower in o.lower() for o in rule["organisms"]):
            continue
        req_any = rule.get("require_any", len(rule["markers"]))
        matched = sum(1 for drug, exp in rule["markers"] if sir_map.get(drug) == exp)
        if matched >= req_any and matched > 0:
            detected.append({"phenotype": ph_name, "icon": rule["icon"],
                "label": rule["label"], "detail": rule["detail"],
                "action": rule["action"], "isolation": rule.get("isolation", False),
                "matched_markers": [d for d, e in rule["markers"] if sir_map.get(d) == e],})
    if "staphylococcus aureus" in org_lower and "MRSA" not in [d["phenotype"] for d in detected]:
        beta_r = any(sir_map.get(d) == "R" for d in
                     ["Amoxicillin + Clavulanic acid","Cephalexin","Cefazolin","Ampicillin"])
        if beta_r and sir_map.get("Vancomycin") == "S":
            detected.append({"phenotype": "Possible MRSA", "icon": "⚠️",
                "label": "Possible MRSA — تأكيد مطلوب",
                "detail": "نمط مقاومة beta-lactam مع حساسية Vancomycin يشير لـ MRSA.",
                "action": "أجرِ Cefoxitin disk diffusion أو PCR (mecA) للتأكيد.",
                "isolation": False, "matched_markers": [],})
    return detected

# =========================================================
# MODULE 2 — AST Quality Control Checker
# =========================================================
AST_QC_RULES = [
    {"id":"QC001","severity":"error",
     "organisms":["E. coli","Klebsiella spp.","Pseudomonas aeruginosa","Acinetobacter baumannii","Proteus mirabilis"],
     "condition": lambda s: s.get("Vancomycin")=="S",
     "message":"Vancomycin-S في غرام سالب — مستحيل (intrinsic resistance).",
     "fix":"احذف نتيجة Vancomycin — لا تُختبر على الغرام سالبات."},
    {"id":"QC002","severity":"error",
     "organisms":["Proteus mirabilis"],
     "condition": lambda s: s.get("Nitrofurantoin")=="S" or s.get("Furadantin")=="S",
     "message":"Nitrofurantoin-S في Proteus — مقاومة طبيعية (EUCAST).",
     "fix":"نتيجة خاطئة — يجب أن تكون R."},
    {"id":"QC003","severity":"error",
     "organisms":["Proteus mirabilis"],
     "condition": lambda s: s.get("Colistin")=="S",
     "message":"Colistin-S في Proteus — مقاومة طبيعية (EUCAST).",
     "fix":"نتيجة خاطئة — يجب أن تكون R."},
    {"id":"QC004","severity":"warning",
     "organisms":["E. coli","Klebsiella spp.","Proteus mirabilis"],
     "condition": lambda s: (any(s.get(d)=="R" for d in ["Ceftriaxone","Cefotaxime"]) and
                             any(s.get(d)=="S" for d in ["Cefuroxime","Cephalexin","Cefazolin"])),
     "message":"Ceftriaxone-R مع Cefuroxime-S — نمط ESBL غير متوقع.",
     "fix":"ESBL تسبب مقاومة لكل السيفالوسبورين — راجع النتائج."},
    {"id":"QC005","severity":"warning",
     "organisms":["Staphylococcus aureus","MRSA"],
     "condition": lambda s: s.get("Linezolid")=="R",
     "message":"Linezolid-R في S. aureus — نادر جداً.",
     "fix":"أعد الاختبار بـ Etest."},
    {"id":"QC006","severity":"warning",
     "organisms":[],
     "condition": lambda s: (any(s.get(d)=="S" for d in ["Imipenem/Cilastatin","Meropenem"]) and
                             s.get("Colistin")=="R" and
                             sum(1 for v in s.values() if v=="R")>=6),
     "message":"Carbapenem-S مع Colistin-R ومقاومة واسعة — تحقق من الهوية.",
     "fix":"تأكد من صحة التعريف."},
    {"id":"QC007","severity":"warning",
     "organisms":["Staphylococcus aureus"],
     "condition": lambda s: (s.get("Cefoxitin")=="R" and
                             any(s.get(d)=="S" for d in ["Amoxicillin + Clavulanic acid","Cephalexin","Cefazolin"])),
     "message":"Cefoxitin-R مع Beta-lactam-S — يشير لـ MRSA، Beta-lactam خاطئ.",
     "fix":"MRSA مقاوم لكل البيتا-لاكتام — غيّر النتائج لـ R."},
]

def run_ast_qc(organism: str, sir_map: Dict[str, str]) -> List[Dict[str, Any]]:
    if not sir_map:
        return []
    issues = []
    org_lower = organism.lower()
    for rule in AST_QC_RULES:
        if rule["organisms"]:
            if not any(o.lower() in org_lower or org_lower in o.lower() for o in rule["organisms"]):
                continue
        try:
            if rule["condition"](sir_map):
                issues.append({"id":rule["id"],"severity":rule["severity"],
                               "message":rule["message"],"fix":rule["fix"]})
        except Exception:
            continue
    return issues

# =========================================================
# MODULE 3 — Smart Antibiotic Ranking
# =========================================================
def rank_sensitive_antibiotics(allowed: List[Dict], culture_type: str,
                               organism: str, sir_map: Dict[str, str],
                               phenotypes: List[Dict]) -> List[Dict]:
    ph_names = [p["phenotype"] for p in phenotypes]
    scored = []
    for item in allowed:
        score = 0
        sir = sir_map.get(item.get("name",""))
        score += 4 if sir=="S" else (1 if sir=="I" else 0)
        score += {"Access":3,"Watch":2,"Reserve":1}.get(item.get("aware"),0)
        score += 2 if item.get("high_po") else 1
        score += 2 if (item.get("specimen_notes") or {}).get(culture_type) else 0
        score += max(0, 6 - item.get("priority",5))
        if any(ph in ph_names for ph in ["CRE","CRAB"]):
            if "cephalosporin" in item.get("class","").lower() and sir != "S":
                score -= 3
        scored.append({**item, "_score": score, "_sir": sir or "—"})
    return sorted(scored, key=lambda x: x["_score"], reverse=True)

# =========================================================
# MODULE 4 — Infection Syndrome Module
# =========================================================
INFECTION_SYNDROMES = {
    "Urine":{"syndrome":"Urinary Tract Infection (UTI)",
             "sub":lambda a,p,c:"Complicated UTI" if c or a>65 else "Pregnancy UTI" if p else "Uncomplicated UTI",
             "first":["Nitrofurantoin","Fosfomycin","Trimethoprim/Sulfamethoxazole"],
             "dur":{"Uncomplicated UTI":"3-5 أيام","Complicated UTI":"7-14 يوم","Pregnancy UTI":"7 أيام"},
             "esc":"فشل الخط الأول → Ciprofloxacin أو Cefixime","thr":"≥ 10⁵ CFU/mL"},
    "Blood":{"syndrome":"Bloodstream Infection (BSI)",
             "sub":lambda a,p,c:"CRBSI" if c else "Community/Hospital BSI",
             "first":["Ceftriaxone","Amoxicillin + Clavulanic acid"],
             "dur":{"CRBSI":"14 يوم + إزالة الكاتيتر","Community/Hospital BSI":"14-21 يوم"},
             "esc":"MDR → Meropenem ± Amikacin","thr":"2 sets blood cultures قبل المضاد"},
    "Sputum":{"syndrome":"Respiratory Tract Infection",
              "sub":lambda a,p,c:"HAP/VAP" if c else "CAP",
              "first":["Amoxicillin + Clavulanic acid","Levofloxacin","Azithromycin"],
              "dur":{"CAP":"5-7 أيام","HAP/VAP":"7-14 يوم"},
              "esc":"Pseudomonas/Acinetobacter → anti-pseudomonal إلزامي","thr":"≥ 10⁶ CFU/mL"},
    "Wound Swab":{"syndrome":"Skin & Soft Tissue Infection (SSTI)",
                  "sub":lambda a,p,c:"SSTI",
                  "first":["Cephalexin","Amoxicillin + Clavulanic acid"],
                  "dur":{"SSTI":"5-10 أيام"},"esc":"MRSA اشتباه → TMP/SMX أو Doxycycline",
                  "thr":"عينة من العمق — لا من السطح"},
    "Pus":{"syndrome":"Abscess / Deep Infection",
           "sub":lambda a,p,c:"Abscess",
           "first":["Amoxicillin + Clavulanic acid","Metronidazole"],
           "dur":{"Abscess":"Drainage + 5-7 أيام"},
           "esc":"Intra-abdominal → Metronidazole إلزامي","thr":"Drainage culture — أدق من swab"},
    "Stool":{"syndrome":"Gastrointestinal Infection",
             "sub":lambda a,p,c:"GI Infection",
             "first":["Azithromycin","Ciprofloxacin"],
             "dur":{"GI Infection":"3-5 أيام للحالات الشديدة"},
             "esc":"معظم الحالات لا تحتاج مضاد","thr":"Culture للحالات الشديدة فقط"},
    "CSF":{"syndrome":"CNS Infection (Meningitis)",
           "sub":lambda a,p,c:"Bacterial Meningitis",
           "first":["Ceftriaxone","Meropenem"],
           "dur":{"Bacterial Meningitis":"10-14 يوم"},
           "esc":"ابدأ تجريبياً فوراً. Dexamethasone قبل المضاد",
           "thr":"CSF culture + Gram stain"},
}

def get_infection_syndrome(specimen: str, organism: str, age: int,
                           is_preg: bool, is_cath: bool=False) -> Optional[Dict]:
    data = INFECTION_SYNDROMES.get(specimen)
    if not data:
        return None
    sub_type = data["sub"](age, is_preg, is_cath)
    return {"syndrome":data["syndrome"],"sub_type":sub_type,
            "first_choice":data["first"],"duration":data["dur"].get(sub_type,"حسب الاستجابة"),
            "escalation":data["esc"],"threshold":data["thr"]}

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

SUBSCRIBERS = load_subscribers()

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
        "patient_name_final": "",
        "colony_count":       "≥ 10^5 CFU/mL",
        "date_in":            date.today(),
        "pus_cells_text":     "",
        "rbcs_text":          "",
        "lab_name":           "Orange Lab",
        "lab_city":           "6 October City, Egypt",
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
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# =========================================================
# أدوات مساعدة
# =========================================================
def fuzzy_match(a: str, b: str) -> float:
    a = (a or "").lower().strip()
    b = (b or "").lower().strip()
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 100.0
    return SequenceMatcher(None, a, b).ratio() * 100

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
    return crcl

def get_renal_severity(crcl: float) -> str:
    if crcl >= 60:
        return "Mild"
    if crcl >= 30:
        return "Moderate"
    return "Severe"

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

def best_default_index(options: List[str], preferred: Optional[str]) -> int:
    if preferred and preferred in options:
        return options.index(preferred)
    return 0

def normalize_ocr_text(text: str) -> str:
    cleaned = text or ""
    for old, new in {"\u2013": "-", "\u2014": "-", "\u00a0": " ", "|": " "}.items():
        cleaned = cleaned.replace(old, new)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()

# =========================================================
# OCR — معالجة الصور
# =========================================================
def ensure_ocr_dependencies() -> None:
    if OCR_AVAILABLE:
        return
    st.error(
        "تعذر تحميل مكتبات OCR المطلوبة لتشغيل قراءة الصور.\n\n"
        f"Runtime import error: {OCR_IMPORT_ERROR}"
    )
    st.stop()

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

def classify_sir_from_line(line: str) -> Optional[str]:
    ll   = line.lower().strip()
    tail = re.search(r"\b([sir])\b\s*$", ll)
    if tail:
        return tail.group(1).upper()
    if re.search(r"\b(sensitive|susceptible|sens)\b", ll):
        return "S"
    if re.search(r"\b(resistant|resist)\b", ll):
        return "R"
    if re.search(r"\b(intermediate|inter)\b", ll):
        return "I"
    return None

def match_antibiotic_from_text(snippet: str) -> Optional[str]:
    snippet_norm = normalize_abx_key(snippet)
    if not snippet_norm:
        return None
    alias_items = sorted(ABX_ALIAS_INDEX.items(), key=lambda item: len(item[0]), reverse=True)
    for alias_norm, abx_name in alias_items:
        if alias_norm and alias_norm in snippet_norm:
            return abx_name
    best_match = None
    best_score = 0.0
    for abx_name, info in ABX_GUIDELINES.items():
        for variant in [abx_name, *info.get("aliases", [])]:
            score = fuzzy_match(variant, snippet)
            if score > best_score:
                best_score = score
                best_match = abx_name
    return best_match if best_score >= 82 else None

def extract_detected_drugs(full_text: str) -> List[str]:
    detected: set = set()
    for line in full_text.splitlines():
        line = line.strip()
        if not line:
            continue
        matched = match_antibiotic_from_text(line)
        if matched:
            detected.add(matched)
    return sorted(detected)

def detect_age(text: str) -> Optional[int]:
    for pattern in [r"(\d+)\s*[Yy]ears?", r"Age[:\s]+(\d+)", r"(\d+)\s*[Yy]\b", r"العمر[:\s]+(\d+)"]:
        match = re.search(pattern, text)
        if match:
            value = safe_int(match.group(1), -1)
            if 0 <= value <= 120:
                return value
    return None

def detect_sex(text_lower: str) -> Optional[str]:
    if any(t in text_lower for t in ["female", "sex: f", "gender: female", "أنثى", "انثى"]):
        return "Female"
    if any(t in text_lower for t in ["male", "sex: m", "gender: male", "ذكر"]):
        return "Male"
    return None

def detect_specimen(text_lower: str) -> Optional[str]:
    for specimen in SPECIMEN_TYPES:
        if specimen.lower() in text_lower:
            return specimen
    return None

def detect_organism(text_lower: str) -> Optional[str]:
    counts: Dict[str, int] = {}
    for organism in BACTERIA_TYPES:
        c = text_lower.count(organism.lower())
        if c > 0:
            counts[organism] = c
    return max(counts, key=counts.get) if counts else None

@st.cache_data(show_spinner=False)
def extract_all_data_cached(file_bytes: bytes) -> Dict[str, Any]:
    _, thresh  = preprocess_image(file_bytes)
    full_text  = run_ocr(thresh)
    text_lower = full_text.lower()
    sir_map: Dict[str, str] = {}
    for line in full_text.splitlines():
        line = line.strip()
        if not line:
            continue
        result = classify_sir_from_line(line)
        if not result:
            continue
        matched_abx = match_antibiotic_from_text(line)
        if matched_abx:
            sir_map[matched_abx] = result
    return {
        "patient": {
            "Name":     None,
            "Age":      detect_age(full_text),
            "Sex":      detect_sex(text_lower),
            "Specimen": detect_specimen(text_lower),
            "Organism": detect_organism(text_lower),
        },
        "drugs":    extract_detected_drugs(full_text),
        "sir_map":  sir_map,
        "raw_text": full_text,
    }

# =========================================================
# التحليل السريري
# =========================================================
def is_intrinsically_avoided(organism_type: str, drug_name: str, drug_info: Dict[str, Any]) -> bool:
    organism_avoid = (ORGANISM_PROFILE.get(organism_type) or {}).get("avoid", [])
    d_low   = drug_name.lower()
    d_class = drug_info.get("class", "").lower()
    for avoid_item in organism_avoid:
        av_low = avoid_item.lower().strip()
        if av_low in d_low or d_low in av_low:
            return True
        mapped = ORGANISM_AVOID_CLASS_MAP.get(av_low)
        if mapped and any(cls in d_class for cls in mapped):
            return True
    return False

def build_banned_item(name: str, category: str, reason_short: str, reason_detail: str) -> Dict[str, str]:
    return {"name": name, "category": category,
            "reason_short": reason_short, "reason_detail": reason_detail}

def analyze_antibiotics(
    final_drugs:   List[str],
    organism_type: str,
    culture_type:  str,
    age:           int,
    sex:           str,
    is_renal:      bool,
    cl_cr:         float,
    is_preg:       bool,
    is_hepatic:    bool,
    current_meds:  List[str],
    sir_map:       Dict[str, str],
) -> Tuple[List[Dict], List[Dict], List[Dict], List[Dict], List[str]]:
    allowed:             List[Dict] = []
    warned:              List[Dict] = []
    banned:              List[Dict] = []
    preg_warn_items:     List[Dict] = []
    interactions_alerts: List[str]  = []

    for drug in final_drugs:
        if drug not in ABX_GUIDELINES:
            continue
        info           = ABX_GUIDELINES[drug]
        d_low          = drug.lower()
        cls            = info.get("class", "").lower()
        culture_result = sir_map.get(drug)

        if culture_result == "R":
            banned.append(build_banned_item(
                drug, "resistant", "مقاوم (R) في نتيجة المزرعة.",
                f"المزرعة أثبتت أن {drug} لا يثبط نمو الجرثومة. MIC أعلى من الحد العلاجي.",
            ))
            continue

        for med in current_meds:
            if med in info.get("interacts_with", []):
                interactions_alerts.append(f"⚡ تعارض: {drug} مع {med}")
        if is_hepatic and info.get("hepatic_caution"):
            interactions_alerts.append(f"🏥 تحذير كبدي: {drug} — يحتاج متابعة أو تعديل.")

        if is_intrinsically_avoided(organism_type, drug, info):
            banned.append(build_banned_item(
                drug, "organism",
                f"غير فعال لـ {organism_type} طبيعياً.",
                f"{drug} لديه مقاومة طبيعية أو عدم فعالية ضد {organism_type}.",
            ))
            continue

        if organism_type == "MRSA" and any(x in info.get("class", "") for x in ["Penicillin","Cephalosporin"]):
            banned.append(build_banned_item(
                drug, "organism", "بيتا-لاكتام — لا يعمل على MRSA.",
                "MRSA يحمل mecA / PBP2a مما يجعل البيتا-لاكتام غير فعالة.",
            ))
            continue

        if is_preg and info.get("preg_status") == "Banned":
            preg_note = info.get("preg_note") or "ممنوع في الحمل"
            banned.append(build_banned_item(
                drug, "pregnancy",
                preg_note.splitlines()[0] if preg_note.splitlines() else "ممنوع في الحمل",
                preg_note,
            ))
            continue

        if is_preg and info.get("preg_status") == "Warn":
            preg_warn_items.append({"name": drug, **info})

        if age < 18 and not info.get("child_safe", True):
            if "fluoroquinolone" in cls:
                banned.append(build_banned_item(
                    drug, "child", "غير مناسب < 18 سنة.", CHILD_BAN_REASONS["fluoroquinolone"]
                ))
                continue
            if "tetracycline" in cls and age < 8:
                banned.append(build_banned_item(
                    drug, "child", "غير مناسب < 8 سنوات.", CHILD_BAN_REASONS["tetracycline"]
                ))
                continue
            banned.append(build_banned_item(
                drug, "child", "غير مفضل للأطفال.",
                "يحتاج تقييم متخصص أو لا يُنصح به روتينياً لهذه الفئة العمرية.",
            ))
            continue

        if is_renal and "nitrofurantoin" in d_low and cl_cr < 30:
            banned.append(build_banned_item(
                drug, "renal",
                f"ممنوع — CrCl {cl_cr:.1f} < 30 ml/min",
                f"CrCl = {cl_cr:.1f} مل/د — أقل من الحد المطلوب.",
            ))
            continue

        renal_limit = info.get("renal_limit", 0)
        if is_renal and renal_limit > 0 and cl_cr <= renal_limit:
            warned.append({"name": drug, **info, "warning_reason": "renal_adjustment"})
            continue

        if culture_result == "I":
            warned.append({"name": drug, **info, "warning_reason": "intermediate_culture"})
            continue

        allowed.append({"name": drug, **info})

    allowed         = sorted(allowed,         key=lambda x: x.get("priority", 999))
    warned          = sorted(warned,          key=lambda x: x.get("priority", 999))
    preg_warn_items = sorted(preg_warn_items, key=lambda x: x.get("priority", 999))
    return allowed, warned, banned, preg_warn_items, sorted(set(interactions_alerts))

# =========================================================
# توليد صورة Decision Tree
# =========================================================
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
    lab_name:        str = "Orange Lab",
    lab_city:        str = "",
    mdr_result:      Optional[Dict] = None,
    esbl_result:     Optional[Dict] = None,
    phenotypes:      Optional[List] = None,
) -> bytes:
    if not PIL_AVAILABLE:
        raise RuntimeError("Pillow غير متاح — أضف Pillow لـ requirements.txt")

    S  = 2
    W  = 2181
    H  = 1496
    P  = 14 * S
    G  = 8  * S

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

    def gf(size: int, bold: bool = False):
        paths = [
            f"/usr/share/fonts/truetype/liberation/LiberationSans-{'Bold' if bold else 'Regular'}.ttf",
            f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        ]
        for p in paths:
            try:
                return ImageFont.truetype(p, size * S)
            except Exception:
                pass
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

    def rbox(draw, box, bg, bd, radius=14, width=3):
        draw.rounded_rectangle(
            [box[0], box[1], box[2], box[3]],
            radius=radius * S, fill=bg, outline=bd, width=width * S
        )

    def text_wrap(draw, x, y, text, font, fill, max_w, gap=4):
        words = text.split()
        lines, cur = [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if tw(draw, trial, font) <= max_w:
                cur = trial
            else:
                if cur: lines.append(cur)
                cur = w
        if cur: lines.append(cur)
        lh = fh(font) + gap * S
        for line in lines:
            draw.text((x, y), line, fill=fill, font=font)
            y += lh
        return y

    BADGE_COLORS = {"[A]": (20, 138, 68), "[W]": (195, 140, 30)}

    # ألوان AWaRe للنص
    AWARE_TXT_COLORS = {
        "[A]": (20, 138, 68),   # أخضر — Access
        "[W]": (160, 100, 0),   # برتقالي — Watch
    }

    def section_box(draw, box, title, title_color, subtitle, items, bg, bd, ft, fs, fi):
        x1, y1, x2, y2 = box
        rbox(draw, box, bg, bd, radius=16, width=3)
        draw.text((x1 + 14*S, y1 + 12*S), title, fill=title_color, font=ft)
        cy = y1 + 12*S + fh(ft) + 6*S
        if subtitle:
            draw.text((x1 + 14*S, cy), subtitle, fill=(110,115,125), font=fs)
            cy += fh(fs) + 4*S
        draw.line([(x1 + 10*S, cy), (x2 - 10*S, cy)], fill=bd, width=1*S)
        cy += 8*S
        for item in items:
            if cy + fh(fi) + 6*S > y2 - 8*S:
                draw.text((x1 + 14*S, cy), "...", fill=LIGHT_GRAY, font=fi)
                break
            # استخراج الـ badge وتلوين الاسم
            badge = ""
            display_name = item
            for b in ["[A]", "[W]"]:
                if item.endswith(b):
                    badge = b
                    display_name = item[:-len(b)].rstrip()
                    break
            # لون النص حسب AWaRe
            txt_color = AWARE_TXT_COLORS.get(badge, DARK)
            cy = text_wrap(draw, x1 + 14*S, cy, f"• {display_name}",
                           fi, txt_color, x2 - x1 - 26*S, gap=6)

    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Header — اسم المعمل متغير بالكامل بدون أي نص ثابت
    rbox(draw, (P, 6*S, W-P, 62*S), NAVY, NAVY, radius=12, width=1)
    htxt = f"{lab_name.upper()}  —  MICROBIOLOGY CDSS"
    if lab_city:
        htxt += f"  |  {lab_city}"
    hw = tw(draw, htxt, F_HEADER)
    draw.text(((W - hw)//2, 16*S), htxt, fill=WHITE, font=F_HEADER)

    # Culture box
    CB = (368*S, 72*S, 870*S, 198*S)
    rbox(draw, CB, WHITE, NAVY, radius=14, width=2)
    ctype = "URINE CULTURE RESULT" if "urine" in specimen.lower() else f"{specimen.upper()} CULTURE RESULT"
    ctw_  = tw(draw, ctype, F_SUBTITL)
    draw.text(((CB[0]+CB[2]-ctw_)//2, CB[1]+12*S), ctype, fill=DARK, font=F_SUBTITL)
    ow = tw(draw, organism, F_ORG)
    draw.text(((CB[0]+CB[2]-ow)//2, CB[1]+38*S), organism, fill=NAVY, font=F_ORG)
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

    # Alert box — ديناميكي حسب MDR/ESBL/Phenotype
    _ph_names  = [p.get("phenotype","") for p in (phenotypes or [])]
    _has_cre   = any(p in _ph_names for p in ["CRE","CRAB","CRPA"])
    _mdr_lvl   = (mdr_result or {}).get("level")
    _esbl_prob = (esbl_result or {}).get("probability")
    _has_xdr   = _mdr_lvl in ("XDR","PDR")
    _has_esbl  = _esbl_prob in ("high","carbapenemase")

    if _has_cre or _has_xdr:
        AB_BG=(255,237,234); AB_BD=(183,52,52);  AB_TXT=(148,30,30)
        _alert_title = "🚨 CRE / XDR ALERT"
    elif _has_esbl or _mdr_lvl == "MDR":
        AB_BG=(255,248,232); AB_BD=(205,115,50); AB_TXT=(130,60,5)
        _alert_title = "⚠  ESBL / MDR ALERT"
    else:
        AB_BG=ALERT_BG; AB_BD=ALERT_BD; AB_TXT=ALERT_TXT
        _alert_title = "⚠  IMPORTANT ALERT"

    AB = (885*S, 72*S, W-P, 198*S)
    rbox(draw, AB, AB_BG, AB_BD, radius=14, width=3)
    draw.text((AB[0]+12*S, 72*S+12*S), _alert_title, fill=AB_TXT, font=F_SUBTITL)
    alerts: List[str] = []

    if _mdr_lvl:
        rc   = (mdr_result or {}).get("resistant_count",0)
        rt   = (mdr_result or {}).get("total_tested",0)
        cats = (mdr_result or {}).get("resistant_categories",[])
        alerts.append(f"{_mdr_lvl}: R {rc}/{rt} categories")
        if cats:
            alerts.append(f"R: {', '.join(cats[:3])}")

    if _esbl_prob == "carbapenemase":
        alerts += ["Carbapenemase (KPC/MBL/OXA)!","Send to reference lab NOW."]
    elif _esbl_prob == "high":
        alerts += ["High probability ESBL Producer","Use Carbapenems for severe cases"]
    elif _esbl_prob == "moderate":
        alerts += ["ESBL confirmation needed","Double Disk Synergy Test"]

    for ph in (phenotypes or [])[:2]:
        if ph.get("phenotype") not in ("Possible MRSA",):
            alerts.append(f"Phenotype: {ph.get('phenotype','')}")

    org_l = organism.lower()
    if not alerts:
        if "klebsiella" in org_l:
            alerts += ["Consider ESBL screening","Natural R: Ampicillin"]
        elif "e. coli" in org_l or "coli" in org_l:
            alerts += ["Most common UTI pathogen","Verify culture sensitivity"]
        elif "pseudomonas" in org_l:
            alerts += ["High intrinsic resistance","Anti-pseudomonal required"]
        elif "mrsa" in org_l or "staphylococcus" in org_l:
            alerts += ["Check MRSA status","Vancomycin/Linezolid if MRSA"]
        elif "acinetobacter" in org_l:
            alerts += ["MDR risk — check Carbapenem S/I/R"]
        else:
            alerts = ["Verify sensitivity results."]

    if is_renal:
        alerts.append(f"Renal adj. (CrCl {cl_cr:.0f} ml/min)")
    if is_preg and age >= 18:
        alerts.append("Pregnancy: verify fetal safety")

    ay = 72*S + 12*S + fh(F_SUBTITL) + 8*S
    for al in alerts[:6]:
        if ay + fh(F_SMALL) + 4*S > AB[3] - 6*S:
            break
        ay = text_wrap(draw, AB[0]+12*S, ay, f"• {al}",
                       F_SMALL, AB_TXT, AB[2]-AB[0]-22*S, gap=4)
        ay += 2*S

    # Patient box
    PB = (P, 72*S, 358*S, 198*S)
    rbox(draw, PB, PURPLE_BG, PURPLE_BD, radius=14, width=3)
    draw.text((P+14*S, 84*S), "PATIENT DETAILS", fill=PURPLE_BD, font=F_TITLE)
    p_lines = []
    if patient_name:
        p_lines.append(f"Name: {patient_name}")
    p_lines.append(f"{'Male' if sex == 'Male' else 'Female'}, {age} years")
    if is_renal:
        p_lines.append(f"Weight: {weight} kg")
        p_lines.append(f"Renal: IMPAIRED")
        p_lines.append(f"CrCl: {cl_cr:.1f} ml/min ({get_renal_severity(cl_cr)})")
    else:
        p_lines.append("Renal: Normal")
    if sex == "Female" and age >= 18:
        p_lines.append(f"Pregnancy: {'Yes' if is_preg else 'No'}")
    if age < 18:
        p_lines.append("Verify age-specific suitability.")
    py = 106*S
    for ln in p_lines[:7]:
        draw.text((P+14*S, py), f"• {ln}", fill=DARK, font=F_TEXT)
        py += fh(F_TEXT) + 5*S

    # Row 2: Specimen | Microscopic | First-line
    R2_Y1 = 210*S
    R2_Y2 = 310*S
    r2w   = (W - 2*P - 2*G) // 3
    spec_items  = [f"Type: {specimen}", "Method: Culture & Sensitivity"]
    micro_items = [
        f"Pus Cells: {pus_cells if pus_cells else '-'} /HPF",
        f"RBCs:      {rbcs if rbcs else '-'} /HPF",
    ]
    fl_items = first_line[:4] or ["-"]
    r2_data = [
        ("SPECIMEN",           spec_items,  SPEC_BD,  SPEC_BG,  "Specimen"),
        ("MICROSCOPIC EXAM",   micro_items, MICRO_BD, MICRO_BG, "Microscopy"),
        ("FIRST-LINE OPTIONS", fl_items,    FL_BD,    FL_BG,    "First-Line"),
    ]
    for i, (title, items, bd, bg, _) in enumerate(r2_data):
        bx1 = P + i*(r2w+G)
        bx2 = bx1 + r2w
        rbox(draw, (bx1, R2_Y1, bx2, R2_Y2), bg, bd, radius=12, width=2)
        draw.text((bx1+12*S, R2_Y1+9*S), title, fill=bd, font=F_SUBTITL)
        iy = R2_Y1 + 32*S
        for it in items[:4]:
            iy = text_wrap(draw, bx1+14*S, iy, f"• {it}", F_SMALL, DARK, bx2-bx1-24*S, gap=4)

    # 4 main columns
    COL_Y1 = 323*S
    COL_Y2 = H - 115*S
    cw     = (W - 2*P - 3*G) // 4
    avoid_title = "AVOID IN PREGNANCY" if is_preg else "AVOID / CONTRAINDICT."
    avoid_sub   = "Contraindicated / Pregnancy" if is_preg else "Due to other factors"
    columns = [
        ("PREFERRED (SAFE)",  "Preferred oral options",  preferred,       GREEN_BD, GREEN_BG, GREEN_TXT),
        ("USE WITH CAUTION",  "Use with caution",         use_caution,     AMBER_BD, AMBER_BG, AMBER_TXT),
        (avoid_title,         avoid_sub,                  contraindicated, RED_BD,   RED_BG,   RED_TXT),
        ("RESERVE (SEVERE)",  "ESBL / Severe cases only", reserve,         BLUE_BD,  BLUE_BG,  BLUE_TXT),
    ]
    for i, (title, subtitle, items, bd, bg, tc) in enumerate(columns):
        bx1 = P + i*(cw+G)
        bx2 = bx1 + cw
        section_box(draw, (bx1, COL_Y1, bx2, COL_Y2),
                    title, tc, subtitle, items or ["-"],
                    bg, bd, F_TITLE, F_SMALL, F_TEXT)

    # Footer — 4 boxes
    FY1 = H - 116*S
    FY2 = H - 8*S
    fw4 = (W - 2*P - 3*G) // 4

    # WHO AWaRe
    fx1 = P; fx2 = fx1 + fw4
    rbox(draw, (fx1, FY1, fx2, FY2), FOOT_BG, FOOT_BD, radius=12, width=2)
    draw.text((fx1+10*S, FY1+10*S), "WHO AWaRe", fill=DARK, font=F_SUBTITL)
    bx = fx1 + 10*S
    by = FY1 + 30*S
    for label, color in [("ACCESS", GREEN_TXT), ("WATCH", AMBER_TXT), ("RESERVE", RED_TXT)]:
        lw      = tw(draw, label, F_BADGE)
        badge_w = int(lw) + 10*S
        rbox(draw, (bx-2*S, by-2*S, bx+badge_w, by+fh(F_BADGE)+4*S), color, color, radius=5, width=1)
        draw.text((bx+3*S, by), label, fill=WHITE, font=F_BADGE)
        bx += badge_w + 5*S
    draw.text((fx1+10*S, by+fh(F_BADGE)+7*S), "1st/2nd | Caution | Last resort", fill=GRAY, font=F_SMALL)

    # Summary
    fx1 = P + fw4 + G; fx2 = fx1 + fw4
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

    # Notes
    fx1 = P + 2*(fw4+G); fx2 = fx1 + fw4
    rbox(draw, (fx1, FY1, fx2, FY2), FOOT_BG, FOOT_BD, radius=12, width=2)
    draw.text((fx1+10*S, FY1+10*S), "NOTES", fill=DARK, font=F_SUBTITL)
    ny = FY1 + 30*S
    for note in (notes or [])[:5]:
        if ny + fh(F_SMALL) + 3*S > FY2 - 6*S:
            break
        ny = text_wrap(draw, fx1+10*S, ny, f"• {note}", F_SMALL, DARK, fx2-fx1-18*S, gap=3)

    # References
    fx1 = P + 3*(fw4+G); fx2 = W - P
    rbox(draw, (fx1, FY1, fx2, FY2), FOOT_BG, FOOT_BD, radius=12, width=2)
    draw.text((fx1+10*S, FY1+10*S), "REFERENCES", fill=DARK, font=F_SUBTITL)
    refs = ["EUCAST 2026","CLSI M100 2026","IDSA AMR 2025",
            "WHO AWaRe 2025","Egypt Nat. Guidelines","BNF 2025 | FDA Labels"]
    ry = FY1 + 30*S
    for ref in refs:
        if ry + fh(F_SMALL) + 3*S > FY2 - 6*S:
            break
        ry = text_wrap(draw, fx1+10*S, ry, f"• {ref}", F_SMALL, DARK, fx2-fx1-18*S, gap=3)

    buf = io.BytesIO()
    img.save(buf, "PNG", dpi=(200, 200), optimize=False)
    return buf.getvalue()

# =========================================================
# توليد التقرير النصي
# =========================================================
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
    lab_name:              str = "Orange Lab",
    lab_city:              str = "",
    patho_assessment:      dict = None,
    show_commercial_names: bool = False,
) -> str:
    now  = datetime.now().strftime("%Y-%m-%d %H:%M")
    sep  = "=" * 60
    sep2 = "-" * 60
    L:   List[str] = []

    lab_hdr = lab_name.upper() if lab_name else "ORANGE LAB"
    L += [sep, f"{lab_hdr} — CLINICAL DECISION REPORT", sep, f"Date     : {now}"]
    if patient_name:
        L.append(f"Patient  : {patient_name}")
    L.append(sep)

    L += ["\nPATIENT DETAILS", sep2,
          f"Age      : {age} years",
          f"Gender   : {sex}",
          f"Weight   : {weight} kg",
          f"Renal    : {'IMPAIRED' if is_renal else 'Normal'}"]
    if is_renal:
        L.append(f"CrCl     : {cl_cr:.1f} ml/min ({get_renal_severity(cl_cr)})")
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
        if op.get("first_line"):
            L.append(f"First-line : {', '.join(op['first_line'])}")
        if op.get("avoid"):
            L.append(f"Avoid      : {', '.join(op['avoid'])}")

    if sir_map:
        L += ["\nSENSITIVITY RESULTS", sep2]
        for drug, result in sorted(sir_map.items()):
            label = {"S": "Sensitive", "R": "Resistant", "I": "Intermediate"}.get(result, result)
            L.append(f"{drug:<40} {label}")

    if interactions:
        L += ["\nINTERACTIONS / WARNINGS", sep2]
        for item in sorted(set(interactions)):
            L.append(f"- {item}")

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
            L += ["\nPOSSIBLE CARBAPENEMASE PRODUCER", sep2,
                  esbl_r["detail"], f"Action: {esbl_r['action']}", ""]
        elif prob == "high":
            L += ["\nHIGH PROBABILITY ESBL PRODUCER", sep2,
                  esbl_r["detail"], f"Action: {esbl_r['action']}", ""]
        elif prob == "moderate":
            L += ["\nESBL CONFIRMATION RECOMMENDED", sep2,
                  esbl_r["detail"], f"Action: {esbl_r['action']}", ""]

    L += ["\nRECOMMENDED ANTIBIOTICS", sep]
    if allowed:
        for item in allowed:
            sir_tag  = f" [Culture: {sir_map[item['name']]}]" if sir_map and item['name'] in sir_map else ""
            preg_tag = " [Pregnancy: caution]" if (is_preg and item.get("preg_status") == "Warn") else ""
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
            if is_preg and item.get("preg_status") == "Warn":
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
            L.append(f"Patient CrCl = {cl_cr:.1f} ml/min\n")
        for item in warned:
            sir_tag = f" [Culture: {sir_map[item['name']]}]" if sir_map and item['name'] in sir_map else ""
            L += [f"{item['name']}{sir_tag}", sep2, f"WHO AWaRe : {item.get('aware','-')}"]
            if item.get("warning_reason") == "intermediate_culture":
                L.append("Reason    : Intermediate (I) on culture result")
            else:
                L += [f"Renal note: {item.get('renal_note','-')}",
                      f"Limit CrCl: <= {item.get('renal_limit','-')} ml/min"]
            if show_commercial_names:
                _brands = get_commercial_name(item["name"])
                if _brands:
                    L.append(f"Brands    : {_brands}")
            L.append("")

    if is_preg and preg_warn_items:
        L += ["\nPREGNANCY — USE WITH CAUTION", sep]
        for item in preg_warn_items:
            L += [item['name'], sep2]
            L.extend((item.get("preg_note") or "").splitlines())
            L.append("")

    if banned:
        L += ["\nCONTRAINDICATED / INEFFECTIVE", sep]
        grouped: Dict[str, list] = {
            "resistant": [], "renal": [], "pregnancy": [],
            "child": [], "organism": [], "other": [],
        }
        for item in banned:
            grouped.setdefault(item["category"], []).append(item)
        labels = [
            ("resistant", "[A] RESISTANT IN CULTURE"),
            ("renal",     "[B] CONTRAINDICATED — RENAL IMPAIRMENT"),
            ("pregnancy", "[C] CONTRAINDICATED — PREGNANCY"),
            ("child",     "[D] NOT SUITABLE FOR AGE"),
            ("organism",  f"[E] INEFFECTIVE FOR {organism}"),
            ("other",     "[F] OTHER CONTRAINDICATIONS"),
        ]
        for cat, heading in labels:
            if grouped.get(cat):
                L += [f"\n{heading}", sep2]
                for b in grouped[cat]:
                    L.append(f"- {b['name']} — {b['reason_short']}")
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

    # ── Pathogenicity Assessment ──────────────────────────────────────
    if patho_assessment:
        sc     = patho_assessment.get("score", 0)
        verd   = patho_assessment.get("verdict", "")
        interp = patho_assessment.get("interpretation", "")
        recs   = patho_assessment.get("recommendations", [])
        flags  = patho_assessment.get("special_flags", [])
        L += ["", "PATHOGENICITY ASSESSMENT", sep2,
              f"Score    : {sc}% — {verd}"]
        if "ABU_DETECTED" in flags:
            L.append("FLAG     : Asymptomatic Bacteriuria (ABU) Detected")
        if "MW_REJECT" in flags:
            L.append("FLAG     : Murray-Washington — Specimen REJECTED")
        elif "MW_ADEQUATE" in flags:
            L.append("FLAG     : Murray-Washington — Adequate Sputum")
        if "SIRS_HIGH" in flags:
            L.append("FLAG     : SIRS >=3 criteria — Sepsis Probable")
        if interp:
            L.append(f"Interp   : {interp}")
        if recs:
            L.append("Recs     :")
            for r in recs:
                L.append(f"  • {r}")

    L += ["\nDISCLAIMER", sep,
          "هذا التقرير أداة مساعدة للقرار الطبي وليس بديلاً عن التقييم السريري.",
          "القرار النهائي للوصف العلاجي يعود للطبيب المعالج.", sep,
          "Guidelines: EUCAST 2026 | CLSI M100 2026 | IDSA AMR 2025 | Egypt National",
          "Route info: BNF 2025 | FDA Labels | WHO AWaRe 2025",
          "WHO AWaRe : Access | Watch | Reserve", sep,
          f"Developed by Dr / Hussein Ali | {lab_name}{(' | ' + lab_city) if lab_city else ''}", sep]
    return "\n".join(L)


# =========================================================
# Auth — تسجيل الدخول والاشتراك
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
        <p style='color:gray; margin:0'>Microbiology Clinical Decision Support System — Egyptian Market</p>
    </div>
    """, unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("#### 🔐 تسجيل الدخول")
        email    = st.text_input("📧 البريد الإلكتروني", placeholder="example@hospital.com",
                                 label_visibility="collapsed")
        login_btn = st.button("دخول", use_container_width=True, type="primary")
        if login_btn:
            return email.strip().lower()
        st.markdown("---")
        st.markdown("""
        <div style='text-align:center; font-size:0.9rem; color:gray'>
        للحصول على نسخة تجريبية أو اشتراك:<br>
        📞 01016872801 &nbsp;|&nbsp; ✉️ Hussein.ali77121@gmail.com<br><br>
        🔹 تجريبي مجاني: <b>15 يوم</b><br>
        🔹 شهري: <b>200 جنيه</b><br>
        🔹 سنوي: <b>2000 جنيه</b> <span style='color:green'>(توفير 400 ج)</span>
        </div>
        """, unsafe_allow_html=True)
    return None

def check_subscription(email: str) -> bool:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        st.warning("⚠️ أدخل بريدًا إلكترونيًا صحيحًا")
        return False
    if email not in SUBSCRIBERS:
        st.error("❌ هذا البريد غير مسجل في النظام")
        st.info(
            "**للحصول على نسخة تجريبية مجانية (15 يوم) أو اشتراك:**\n\n"
            "📞 01016872801\n\n✉️ Hussein.ali77121@gmail.com\n\n---\n"
            "🔹 تجريبي: **مجاناً - 15 يوم**\n"
            "🔹 شهري: **200 جنيه**\n"
            "🔹 سنوي: **2000 جنيه** *(توفير 400 ج)*"
        )
        return False
    days_left = get_subscription_days_left(email)
    if days_left is None:
        st.error("خطأ في بيانات الاشتراك، تواصل مع الدعم")
        return False
    st.session_state.email     = email
    st.session_state.days_left = days_left
    if days_left < 0:
        st.error(f"⏳ انتهى اشتراكك منذ {abs(days_left)} يوم")
        st.info("📞 للتجديد: 01016872801 | ✉️ Hussein.ali77121@gmail.com")
        return False
    if days_left <= 3:
        st.warning(f"⚠️ اشتراكك ينتهي خلال **{days_left} يوم فقط**")
    elif days_left <= 7:
        st.info(f"ℹ️ متبقي **{days_left} أيام** على انتهاء الاشتراك")
    else:
        st.success(f"✅ أهلاً بك! الاشتراك ساري — متبقي {days_left} يومًا")
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
        if days is not None:
            if days <= 3:
                st.warning(
                    f"⚠️ اشتراك **{st.session_state.email}** سينتهي خلال **{days} يوم(أيام)** — يُرجى التجديد قريبًا."
                )
            else:
                st.info(f"✅ اشتراك **{st.session_state.email}** سارٍ — متبقي **{days}** يومًا.")
    with right:
        if st.button("تسجيل خروج", use_container_width=True):
            logout("تم تسجيل الخروج بنجاح.")

# =========================================================
# التحقق من البيانات عند التشغيل
# =========================================================
@st.cache_data(show_spinner=False)
def get_startup_validation_issues() -> List[str]:
    issues: List[str] = []
    known_organisms = list(ORGANISM_PROFILE.keys())
    known_abx       = list(ABX_GUIDELINES.keys())
    # تحقق أن first_line/second_line/third_line في ABX_GUIDELINES
    for org, profile in ORGANISM_PROFILE.items():
        for tier in ["first_line","second_line","third_line"]:
            for drug in profile.get(tier, []):
                if drug not in ABX_GUIDELINES:
                    issues.append(f"[organism_profile] {org} → {tier} → '{drug}' not in ABX_GUIDELINES")
    # إزالة المكررات
    return list(dict.fromkeys(issues))

# =========================================================
# الواجهة الرئيسية
# =========================================================
if not st.session_state.authenticated:
    email_input = show_login_page()
    if email_input:
        if check_subscription(email_input):
            st.session_state.authenticated = True
            st.session_state.last_activity = time.time()
            st.rerun()
    st.stop()

handle_session_timeout()
render_top_bar()

startup_issues = get_startup_validation_issues()
if startup_issues:
    with st.expander("🧪 Data validation at startup", expanded=False):
        st.warning(f"Found {len(startup_issues)} data issue(s).")
        for issue in startup_issues:
            st.write(f"- {issue}")

st.title("🔬 Microbiology Clinical Decision Support System (CDSS)")
st.caption("AI-Assisted Antibiotic & Resistance Decision Support — Egyptian Market Edition")

# ── إعدادات المعمل ───────────────────────────────────────────────────
with st.expander("🏥 إعدادات المعمل", expanded=False):
    lc1, lc2 = st.columns(2)
    with lc1:
        lab_name_input = st.text_input(
            "اسم المعمل / المستشفى",
            value=st.session_state.get("lab_name", "Orange Lab"),
            placeholder="مثال: Bustan Lab",
            key="lab_name_widget"
        )
        if lab_name_input.strip():
            st.session_state.lab_name = lab_name_input.strip()
    with lc2:
        lab_city_input = st.text_input(
            "المدينة / الجهة (اختياري)",
            value=st.session_state.get("lab_city", ""),
            placeholder="مثال: Cairo",
            key="lab_city_widget"
        )
        st.session_state.lab_city = lab_city_input.strip()
    preview_txt = f"🔬  {st.session_state.lab_name}"
    if st.session_state.lab_city:
        preview_txt += f"  |  {st.session_state.lab_city}"
    st.caption(f"معاينة الترويسة: **{preview_txt}**")

uploaded = st.file_uploader("📷 Upload Culture Report Image", type=["jpg","jpeg","png"])

if uploaded:
    file_bytes = uploaded.getvalue()
    file_hash  = make_file_hash(file_bytes)
    is_new     = (st.session_state.ocr_data is None or
                  st.session_state.last_file_hash != file_hash)

    if is_new:
        with st.spinner("🔍 جاري تحليل صورة التقرير..."):
            try:
                payload = extract_all_data_cached(file_bytes)
                st.session_state.ocr_data       = payload
                st.session_state.last_file_hash = file_hash
                st.session_state.sir_map_edited = dict(payload["sir_map"])
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

    # ─── العمود الأيسر ───────────────────────────────────────────────
    with col1:
        st.subheader("👤 Patient & Culture")

        patient_name = st.text_input(
            "👤 اسم المريض / Patient Name",
            value=st.session_state.get("patient_name_final", ""),
            placeholder="أدخل اسم المريض",
            key=f"pname_{file_hash[:8]}"
        )
        st.session_state.patient_name_final = patient_name.strip()

        culture_type = st.selectbox(
            "🧫 Specimen",
            SPECIMEN_TYPES,
            index=best_default_index(SPECIMEN_TYPES, patient.get("Specimen"))
        )

        filtered_organisms = [
            org for org in SPECIMEN_ORGANISM_MAP.get(culture_type, BACTERIA_TYPES)
            if org in ORGANISM_PROFILE
        ]
        if not filtered_organisms:
            filtered_organisms = BACTERIA_TYPES

        organism_type = st.selectbox(
            "🦠 Organism",
            filtered_organisms,
            index=best_default_index(filtered_organisms, patient.get("Organism")),
            help=f"بكتيريا شائعة في عينة {culture_type}",
        )

        st.divider()
        st.subheader("🔬 Culture & Microscopic Details")

        colony_count = st.text_input(
            "Colony Count (CFU/mL)",
            value=st.session_state.colony_count,
            placeholder="≥ 10^5 CFU/mL",
            key="colony_count_input"
        )
        st.session_state.colony_count = colony_count

        date_in = st.date_input(
            "📅 Date In (تاريخ استلام العينة)",
            value=st.session_state.date_in,
            key="date_in_input"
        )
        st.session_state.date_in = date_in

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

        if organism_type in ORGANISM_PROFILE:
            op = ORGANISM_PROFILE[organism_type]
            with st.expander("📌 Organism Guidance", expanded=True):
                st.info(op.get("note", ""))
                spec_ctx = (op.get("specimen_context") or {}).get(culture_type, "")
                if spec_ctx:
                    st.warning(f"**{culture_type} Context:** {spec_ctx}")
                if op.get("first_line"):
                    st.write("**First-line:**", ", ".join(op["first_line"]))
                if op.get("second_line"):
                    st.write("**Second-line:**", ", ".join(op["second_line"]))
                if op.get("third_line"):
                    st.write("**Third-line:**", ", ".join(op["third_line"]))
                if op.get("avoid"):
                    st.error("**Avoid:** " + ", ".join(op["avoid"]))
                if culture_type == "Urine" and op.get("urine_note"):
                    st.info(f"📌 Urine notes:\n{op['urine_note']}")

        st.divider()
        age    = st.number_input("Age (years)", min_value=0, max_value=120,
                                  value=safe_int(patient.get("Age"), 25))
        default_sex = patient.get("Sex") if patient.get("Sex") in ["Female","Male"] else "Male"
        sex    = st.selectbox("Gender", ["Female","Male"],
                              index=0 if default_sex == "Female" else 1)
        weight = st.number_input("Weight (kg)", min_value=5, max_value=300, value=70)

        st.divider()
        is_renal = st.checkbox("🚩 Renal Impairment")
        cl_cr    = 100.0
        if is_renal:
            s_cr  = st.number_input("Serum Creatinine (mg/dL)",
                                    min_value=0.1, max_value=20.0, value=1.0, step=0.1)
            cl_cr = calc_creatinine_clearance(age, weight, s_cr, sex)
            st.metric("CrCl (Cockcroft-Gault)", f"{cl_cr:.1f} ml/min",
                      delta=get_renal_severity(cl_cr),
                      delta_color="normal" if cl_cr >= 60 else ("off" if cl_cr >= 30 else "inverse"))

        is_hepatic = st.checkbox("🚩 Hepatic Impairment")
        is_preg    = False
        if sex == "Female" and 18 <= age <= 55:
            is_preg = st.checkbox("🤰 Patient is Pregnant")

        current_meds = st.multiselect("💊 Current Medications", COMMON_MEDS)

        # ── Pathogenicity Assessment Module v2 ───────────────────────────────
        st.divider()
        with st.expander("🧫 Pathogenicity Assessment", expanded=False):
            st.caption("هل العينة تمثل عدوى حقيقية أم تلوث؟ — يدعم Urine · Sputum · Blood · Wound · CSF")

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
                    ["مش متعملة",
                     "WBCs + Gram Positive Cocci",
                     "WBCs + Gram Negative Rods",
                     "Organisms بدون WBCs",
                     "طبيعية (No organisms seen)"],
                    key="patho_gram_sel"
                )
                st.session_state.patho_gram_stain = patho_gram

            with pa_col2:
                patho_urinalysis = st.selectbox(
                    "نتيجة Urinalysis (للبول فقط)",
                    ["مش معروف / مش مذكور", "Urinalysis طبيعي",
                     "Pyuria (WBCs > 5/HPF)", "Nitrites Positive", "Hematuria"],
                    key="patho_ua_sel"
                )
                st.session_state.patho_urinalysis = patho_urinalysis

            # ── Specimen-specific fields ──────────────────────────────────────
            spec_lower_ui = culture_type.lower()

            # Urine symptoms
            if "urine" in spec_lower_ui:
                patho_symptoms = st.multiselect(
                    "الأعراض الكلينيكية",
                    ["Dysuria / Frequency / Urgency", "Fever (> 38°C)",
                     "Flank pain / Loin pain", "Nocturnal enuresis",
                     "Abdominal pain", "Nausea / Vomiting", "Asymptomatic"],
                    default=st.session_state.patho_symptoms,
                    key="patho_symp_urine"
                )

            # Sputum — Murray-Washington fields
            elif "sputum" in spec_lower_ui or "respiratory" in spec_lower_ui:
                st.markdown("**Murray-Washington Criteria**")
                mw_c1, mw_c2 = st.columns(2)
                with mw_c1:
                    patho_sputum_pus = st.text_input(
                        "WBC/LPF (Pus cells per low-power field)",
                        value=st.session_state.patho_sputum_pus,
                        placeholder="مثال: 30",
                        key="patho_mw_pus"
                    )
                    st.session_state.patho_sputum_pus = patho_sputum_pus
                with mw_c2:
                    patho_sputum_epi = st.text_input(
                        "Epithelial cells/LPF",
                        value=st.session_state.patho_sputum_epi,
                        placeholder="مثال: 5",
                        key="patho_mw_epi"
                    )
                    st.session_state.patho_sputum_epi = patho_sputum_epi
                st.caption("✅ Adequate: WBC ≥25 & Epi <10 | ❌ Reject: Epi ≥25")
                patho_symptoms = st.multiselect(
                    "الأعراض التنفسية",
                    ["Productive cough / Purulent sputum", "Fever (> 38°C)",
                     "Dyspnea", "Pleuritic chest pain", "Asymptomatic"],
                    default=st.session_state.patho_symptoms,
                    key="patho_symp_sputum"
                )

            # Blood — SIRS criteria
            elif "blood" in spec_lower_ui:
                st.markdown("**SIRS Criteria** (اختر كل المعايير الموجودة)")
                patho_sirs = st.multiselect(
                    "SIRS Criteria",
                    ["Fever > 38°C or Temp < 36°C",
                     "HR > 90 bpm",
                     "RR > 20 or PaCO₂ < 32",
                     "WBC > 12,000 or < 4,000 or >10% bands"],
                    default=st.session_state.patho_sirs,
                    key="patho_sirs_sel"
                )
                st.session_state.patho_sirs = patho_sirs
                patho_blood_source = st.selectbox(
                    "Bottles / Source",
                    ["غير محدد", "Single bottle positive",
                     "Multiple bottles positive", "Source identified (CVC/wound)"],
                    key="patho_blood_src"
                )
                st.session_state.patho_blood_source = patho_blood_source
                patho_symptoms = st.session_state.patho_symptoms

            # Wound / Swab
            elif any(w in spec_lower_ui for w in ["wound", "pus", "swab", "abscess"]):
                patho_wound_type = st.selectbox(
                    "نوع الجرح",
                    ["غير محدد", "Surgical / Post-op wound",
                     "Chronic / Diabetic wound", "Traumatic wound",
                     "Superficial wound", "Deep tissue / Abscess"],
                    key="patho_wound_type_sel"
                )
                st.session_state.patho_wound_type = patho_wound_type
                patho_symptoms = st.multiselect(
                    "علامات العدوى",
                    ["Erythema / Warmth / Swelling", "Purulent discharge",
                     "Fever (> 38°C)", "Pain / Tenderness", "Asymptomatic"],
                    default=st.session_state.patho_symptoms,
                    key="patho_symp_wound"
                )
            else:
                patho_symptoms = st.multiselect(
                    "الأعراض الكلينيكية",
                    ["Fever (> 38°C)", "Localized pain", "Asymptomatic"],
                    default=st.session_state.patho_symptoms,
                    key="patho_symp_other"
                )

            st.session_state.patho_symptoms = patho_symptoms

            # Host factors (universal)
            patho_host = st.multiselect(
                "عوامل المضيف",
                ["Immunosuppressants / Steroids",
                 "Urinary catheter", "Central line / PICC",
                 "تاريخ UTIs متكررة", "Recurrent infections",
                 "Diabetes",
                 "Renal abnormality / Vesicoureteral reflux",
                 "Pregnant", "Pre-surgical"],
                default=st.session_state.patho_host_factors,
                key="patho_host_sel"
            )
            st.session_state.patho_host_factors = patho_host

            if st.button("🔬 احسب Pathogenicity Score", use_container_width=True, key="patho_calc_btn"):
                # Build kwargs based on specimen
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
                )
                if "sputum" in spec_lower_ui or "respiratory" in spec_lower_ui:
                    patho_kwargs["sputum_pus_cells"]  = st.session_state.patho_sputum_pus
                    patho_kwargs["sputum_epithelial"] = st.session_state.patho_sputum_epi
                if "blood" in spec_lower_ui:
                    patho_kwargs["sirs_criteria"]  = st.session_state.patho_sirs
                    patho_kwargs["blood_source"]   = st.session_state.patho_blood_source
                if any(w in spec_lower_ui for w in ["wound","pus","swab","abscess"]):
                    patho_kwargs["wound_type"] = st.session_state.patho_wound_type

                patho_result = assess_pathogenicity(**patho_kwargs)
                st.session_state.patho_result = patho_result

            # ── Display Result (persists after button) ────────────────────
            patho_result = st.session_state.get("patho_result")
            if patho_result:
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

                # ABU badge
                if patho_result.get("abu_detected"):
                    st.info("🔵 **Asymptomatic Bacteriuria (ABU) Detected** — راجع IDSA 2019")

                # Murray-Washington badge
                if "MW_REJECT" in flags:
                    st.error("🧫 **Murray-Washington: Specimen REJECTED** — إعادة أخذ العينة ضرورية")
                elif "MW_ADEQUATE" in flags:
                    st.success("🧫 **Murray-Washington: Adequate Sputum** ✅")
                elif "MW_MIXED" in flags:
                    st.warning("🧫 **Murray-Washington: Mixed Quality** — تحليل بتحفظ")

                # SIRS badge
                if "SIRS_HIGH" in flags:
                    st.error("🩸 **SIRS ≥3 criteria** — Sepsis Probable")
                elif "SIRS_MET" in flags:
                    st.warning("🩸 **SIRS 2 criteria** — Bacteremia Possible")

                # Pediatric badge
                if "PEDIATRIC_UTI" in flags:
                    st.info("👶 **Pediatric threshold applied** (Age < 2 yrs — any growth significant)")

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

                st.markdown("**📋 التوصيات:**")
                for rec in patho_result["recommendations"]:
                    st.write(f"• {rec}")


    # ─── العمود الأيمن ───────────────────────────────────────────────
    with col2:
        st.subheader("💊 Antibiotic Analysis")

        # ══════════════════════════════════════════════════════
        # AST Input Panel — OCR + Manual موحّد
        # ══════════════════════════════════════════════════════
        ocr_sir_map  = payload["sir_map"]
        sir_options  = ["S", "I", "R"]
        label_icons  = {"S":"🟢","I":"🟡","R":"🔴"}

        st.markdown("**📊 نتائج المزرعة — S / I / R**")
        st.caption("✅ من OCR تلقائياً — عدّل أي قيمة أو أضف مضاد فاته الـ OCR")

        ocr_drugs    = list(ocr_sir_map.keys())
        manual_prev  = [d for d in st.session_state.sir_map_edited.keys()
                        if d not in ocr_drugs]
        manual_extra = st.multiselect(
            "➕ أضف مضادات فاتها OCR",
            options=[d for d in sorted(ABX_GUIDELINES.keys()) if d not in ocr_drugs],
            default=manual_prev,
            key=f"manual_drugs_{file_hash[:8]}",
        )
        edited_sir: Dict[str, str] = {}

        if ocr_drugs:
            st.markdown("<small style='color:#555'>🔍 من OCR:</small>", unsafe_allow_html=True)
            for i in range(0, len(ocr_drugs), 3):
                row_drugs = ocr_drugs[i: i+3]
                cols = st.columns(3)
                for col_w, drug in zip(cols, row_drugs):
                    cur = st.session_state.sir_map_edited.get(drug, ocr_sir_map[drug])
                    if cur not in sir_options: cur = "S"
                    val = col_w.selectbox(
                        f"{label_icons.get(cur,'')} {drug}",
                        options=sir_options, index=sir_options.index(cur),
                        key=f"sir_{drug}_{file_hash[:8]}"
                    )
                    edited_sir[drug] = val

        manual_new = [d for d in manual_extra if d not in ocr_drugs]
        if manual_new:
            st.markdown("<small style='color:#1a6b3a'>➕ مُضافة يدوياً:</small>", unsafe_allow_html=True)
            for i in range(0, len(manual_new), 3):
                row_drugs = manual_new[i: i+3]
                cols = st.columns(3)
                for col_w, drug in zip(cols, row_drugs):
                    cur = st.session_state.sir_map_edited.get(drug, "S")
                    if cur not in sir_options: cur = "S"
                    val = col_w.selectbox(
                        f"{label_icons.get(cur,'')} {drug}",
                        options=sir_options, index=sir_options.index(cur),
                        key=f"sir_m_{drug}_{file_hash[:8]}"
                    )
                    edited_sir[drug] = val

        st.session_state.sir_map_edited = edited_sir
        sir_map     = dict(edited_sir)
        final_drugs = list(sir_map.keys())

        if sir_map:
            s_n = sum(1 for v in sir_map.values() if v=="S")
            i_n = sum(1 for v in sir_map.values() if v=="I")
            r_n = sum(1 for v in sir_map.values() if v=="R")
            st.caption(f"📊 {len(sir_map)} مضاد | 🟢 S:{s_n} | 🟡 I:{i_n} | 🔴 R:{r_n}")

        allowed, warned, banned, preg_warn_items, interactions_alerts = analyze_antibiotics(
            final_drugs=final_drugs,
            organism_type=organism_type,
            culture_type=culture_type,
            age=age, sex=sex,
            is_renal=is_renal, cl_cr=cl_cr,
            is_preg=is_preg, is_hepatic=is_hepatic,
            current_meds=current_meds,
            sir_map=sir_map,
        )

        if interactions_alerts:
            st.warning("⚡ Interactions / Hepatic Warnings")
            for alert in interactions_alerts:
                st.write(alert)

        mdr_result  = classify_mdr(organism_type, sir_map)
        esbl_result = predict_esbl(organism_type, sir_map)
        phenotypes  = detect_resistance_phenotypes(organism_type, sir_map)

        # ── Resistance Classification (MDR/XDR/PDR + ESBL) ───────────────
        if mdr_result["level"] or (esbl_result.get("probability") and
                                    esbl_result["probability"] not in ("low", None)):
            with st.expander("🧬 Resistance Classification", expanded=True):
                if mdr_result["level"]:
                    info = MDR_INFO[mdr_result["level"]]
                    _rc   = mdr_result["resistant_count"]
                    _rt   = mdr_result["total_tested"]
                    _cats = ", ".join(mdr_result["resistant_categories"])
                    _msg  = (f"{info['icon']} **{info['label']}**  \n"
                             f"{info['detail']}  \n"
                             f"Resistant categories ({_rc}/{_rt}): {_cats}  \n"
                             f"🔹 {info['action']}")
                    if mdr_result["level"] == "MDR":
                        st.warning(_msg)
                    else:
                        st.error(_msg)

                prob = esbl_result.get("probability")
                if prob == "carbapenemase":
                    st.error(
                        "**🚨 Possible Carbapenemase (KPC/MBL/OXA)**\n" +
                        esbl_result["detail"] + "  \n🔹 " + esbl_result["action"]
                    )
                elif prob == "high":
                    st.error(
                        "**⚠️ High Probability ESBL Producer**\n" +
                        esbl_result["detail"] + "  \n🔹 " + esbl_result["action"]
                    )
                elif prob == "moderate":
                    st.warning(
                        "**🔶 ESBL Confirmation Recommended**\n" +
                        esbl_result["detail"] + "  \n🔹 " + esbl_result["action"]
                    )

        # ── Resistance Phenotype Engine ───────────────────────────────────
        if phenotypes:
            with st.expander("🦠 Resistance Phenotypes Detected", expanded=True):
                for ph in phenotypes:
                    iso = "  🚨 **عزل فوري مطلوب**" if ph["isolation"] else ""
                    msg = (f"{ph['icon']} **{ph['label']}**{iso}\n"
                           f"{ph['detail']}\n🔹 {ph['action']}")
                    (st.error if ph["isolation"] else st.warning)(msg)
                    if ph.get("matched_markers"):
                        st.caption(f"Evidence: {', '.join(ph['matched_markers'])}")

        # ── AST Quality Control ───────────────────────────────────────────
        if sir_map:
            qc_issues = run_ast_qc(organism_type, sir_map)
            if qc_issues:
                with st.expander(f"🔬 AST Quality Control — {len(qc_issues)} Issue(s)", expanded=True):
                    st.caption("تحقق تلقائي من منطقية نتائج المزرعة — EUCAST Expert Rules")
                    for iss in qc_issues:
                        fn = st.error if iss["severity"] == "error" else st.warning
                        icon = "❌" if iss["severity"] == "error" else "⚠️"
                        fn(f"{icon} **[{iss['id']}]** {iss['message']}\n✏️ {iss['fix']}")

        # ── Smart Antibiotic Ranking ──────────────────────────────────────
        if allowed:
            ranked = rank_sensitive_antibiotics(
                allowed, culture_type, organism_type, sir_map, phenotypes
            )
            with st.expander("🏆 Smart Antibiotic Ranking", expanded=False):
                st.caption("مرتب حسب: نتيجة المزرعة + WHO AWaRe + Route + ملاءمة العينة")
                for i, item in enumerate(ranked[:8], 1):
                    sir_b  = item.get("_sir", "—")
                    aware  = item.get("aware", "")
                    route  = "💊 Oral" if item.get("high_po") else "💉 IV/IM"
                    score  = item.get("_score", 0)
                    a_icon = {"Access": "🟢", "Watch": "🟡", "Reserve": "🔴"}.get(aware, "⚪")
                    st.markdown(
                        f"**{i}.** {item['name']} &nbsp; `{sir_b}` &nbsp; "
                        f"{a_icon} {aware} &nbsp; {route} &nbsp;"
                        f"<small style='color:gray'>score:{score}</small>",
                        unsafe_allow_html=True
                    )

        # ── Infection Syndrome Module ─────────────────────────────────────
        syn = get_infection_syndrome(culture_type, organism_type, age, is_preg)
        if syn:
            with st.expander(f"🏥 Infection Syndrome: {syn['syndrome']}", expanded=False):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**النوع:** {syn['sub_type']}")
                    st.markdown(f"**مدة العلاج:** {syn['duration']}")
                    st.markdown(f"**الخط الأول:** {', '.join(syn['first_choice'])}")
                with c2:
                    st.info(f"**Escalation:** {syn['escalation']}")
                    st.caption(f"📌 Culture threshold: {syn['threshold']}")

        if is_preg and preg_warn_items:
            st.markdown("---")
            st.markdown("### 🤰 Pregnancy — Use With Caution")
            st.info(
                "الأدوية التالية **ليست محظورة تلقائيًا** لكنها تحتاج تقييمًا طبيًا دقيقًا.\n\n"
                "**القرار النهائي للطبيب المعالج حصراً.**"
            )
            for item in preg_warn_items:
                with st.expander(f"⚠️ {item['name']} — تفاصيل التحذير"):
                    for line in (item.get("preg_note") or "").splitlines():
                        st.write(line)

        if banned:
            with st.expander("🚫 Contraindicated / Ineffective", expanded=True):
                cat_labels = {
                    "resistant": "مقاوم في المزرعة",
                    "renal":     "قصور كلوي",
                    "pregnancy": "ممنوع في الحمل",
                    "child":     "غير مناسب للعمر",
                    "organism":  "غير فعال للجرثومة",
                    "other":     "موانع أخرى",
                }
                for item in banned:
                    st.error(
                        f"💊 {item['name']}  [{cat_labels.get(item['category'],'')}]\n"
                        f"{item['reason_short']}"
                    )

        if warned:
            with st.expander("🟡 Warnings / Dose Adjustment Required", expanded=True):
                for item in warned:
                    sir_tag = (f" [{sir_map[item['name']]}]"
                               if sir_map and item['name'] in sir_map else "")
                    if item.get("warning_reason") == "intermediate_culture":
                        st.warning(
                            f"**{item['name']}{sir_tag}** — Intermediate (I) on culture, "
                            "use only after clinical review."
                        )
                    else:
                        st.warning(f"**{item['name']}{sir_tag}** — {item.get('renal_note','')}")

        if allowed:
            st.success(f"🟢 {len(allowed)} Recommended Option(s)")
            for item in allowed:
                sir_badge = (f" [{sir_map[item['name']]}]"
                             if sir_map and item['name'] in sir_map else "")
                preg_flag = " 🤰" if (is_preg and item.get("preg_status") == "Warn") else ""
                aware_val = item.get("aware", "Unknown")
                color_val = AWARE_COLORS.get(aware_val, aware_val)
                with st.expander(
                    f"{item['name']}{sir_badge}{preg_flag} — {color_val}", expanded=False
                ):
                    c1, c2 = st.columns(2)
                    c1.write(f"**Class:** {item.get('class','-')}")
                    c2.write(f"**Route:** {get_route_label(item)}")
                    st.write(f"**Note:** {item.get('note','-')}")
                    spec_note = (item.get("specimen_notes") or {}).get(culture_type, "")
                    if spec_note:
                        st.info(f"**{culture_type} Note:** {spec_note}")
                    if is_renal:
                        st.caption(f"Renal: {item.get('renal_note','-')}")
                    if is_preg and item.get("preg_status") == "Warn":
                        pn = (item.get("preg_note") or "").splitlines()
                        if pn:
                            st.caption(f"🤰 {pn[0]}")
        elif not banned and not warned:
            st.info("اختر المضادات الحساسة أو المناسبة من القائمة أعلاه.")

        # ── التقارير والصورة ─────────────────────────────────────────
        if final_drugs:
            st.divider()

            _lab  = st.session_state.get("lab_name", "Orange Lab")
            _city = st.session_state.get("lab_city", "")
            _pt   = patient_name.strip() or "غير محدد"

            reserve_names = uniq_keep_order([
                item['name'] for item in (allowed + warned)
                if item.get("aware") == "Reserve"
            ])
            AWARE_ORDER = {"Access": 0, "Watch": 1, "Reserve": 2, None: 3}
            preferred_sorted = sorted(
                [item for item in allowed if item.get("aware") != "Reserve"],
                key=lambda x: AWARE_ORDER.get(x.get("aware"), 3)
            )
            # بدون badge — اللون بيتحدد داخل section_box عن طريق [A]/[W]
            preferred_with_badge = [
                (f"{item['name']} [A]" if item.get("aware")=="Access" else
                 f"{item['name']} [W]" if item.get("aware")=="Watch" else
                 item['name'])
                for item in preferred_sorted
            ]
            preg_caution_names = [item['name'] for item in preg_warn_items]
            use_caution_names  = uniq_keep_order(
                [item['name'] for item in warned if item['name'] not in reserve_names]
                + preg_caution_names
            )
            banned_names   = uniq_keep_order([item['name'] for item in banned])
            org_profile    = ORGANISM_PROFILE.get(organism_type, {})
            first_line_l   = org_profile.get("first_line", [])

            notes: List[str] = []
            if is_renal:
                notes.append(f"Renal impairment: CrCl {cl_cr:.1f} ml/min — dose adjustment required.")
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

            # ── مفتاح تجديد شامل يتغير مع أي معطى ──────────────────
            import hashlib as _hl
            _refresh_key = _hl.md5(
                f"{organism_type}|{culture_type}|{age}|{sex}|{weight}|"
                f"{is_renal}|{cl_cr:.1f}|{is_preg}|{is_hepatic}|"
                f"{sorted(sir_map.items())}|{sorted(final_drugs)}|"
                f"{_pt}|{colony_count}|{str(date_in)}|{pus_cells_text}|{rbcs_text}|"
                f"{_lab}|{_city}".encode()
            ).hexdigest()[:12]

            # ── Commercial Names Toggle ────────────────────────────────
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

            # ── التقرير النصي ─────────────────────────────────────────
            st.markdown("### 📋 التقرير السريري")
            auto_report = generate_report(
                patient_name=_pt,
                age=age, sex=sex, weight=weight,
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
                show_commercial_names=st.session_state.get("show_commercial_names", False),
            )
            st.text_area(
                "نص التقرير",
                value=auto_report,
                height=380,
                disabled=True,
                label_visibility="collapsed",
                key=f"rpt_{_refresh_key}"
            )
            st.download_button(
                "📥 تنزيل التقرير (TXT)",
                data=auto_report,
                file_name=(f"Orange_{organism_type.replace(' ','_')}_"
                           f"{_pt.replace(' ','_')[:15]}_"
                           f"{datetime.now().strftime('%Y%m%d_%H%M')}.txt"),
                mime="text/plain",
                use_container_width=True,
                type="primary",
                key=f"dl_txt_{_refresh_key}",
            )

            # ── صورة الملخص ───────────────────────────────────────────
            st.divider()
            st.markdown(
                f"### 🖼️ صورة ملخص الحالة — "
                f"**{_lab}**{'  |  ' + _city if _city else ''}"
            )
            if PIL_AVAILABLE:
                try:
                    img_bytes = generate_decision_tree_image(
                        patient_name=_pt,
                        age=age, sex=sex, weight=weight,
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
                        lab_name=_lab,
                        lab_city=_city,
                        mdr_result=mdr_result,
                        esbl_result=esbl_result,
                        phenotypes=phenotypes if "phenotypes" in dir() else [],
                    )
                    st.image(
                        img_bytes,
                        caption=(f"{_lab}{' | ' + _city if _city else ''}"
                                 f"  —  {_pt}  |  {str(date_in)}"),
                        use_container_width=True,
                    )
                    dl_img, pr_img = st.columns(2)
                    with dl_img:
                        st.download_button(
                            "📥 تنزيل الصورة (PNG)",
                            data=img_bytes,
                            file_name=(f"Orange_{organism_type.replace(' ','_')}_"
                                       f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"),
                            mime="image/png",
                            use_container_width=True,
                            key=f"dl_img_{_refresh_key}",
                        )
                    with pr_img:
                        # تنزيل نسخة عالية الجودة للطباعة
                        st.download_button(
                            "🖨️ تنزيل للطباعة (HD)",
                            data=img_bytes,
                            file_name=(f"Orange_Print_{organism_type.replace(' ','_')}_"
                                       f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"),
                            mime="image/png",
                            use_container_width=True,
                            key=f"dl_print_{_refresh_key}",
                        )
                        st.caption("افتح الصورة بعد التنزيل → Ctrl+P للطباعة")
                except Exception as e:
                    st.error(f"فشل توليد الصورة: {e}")
            else:
                st.warning("⚠️ أضف `Pillow` لـ requirements.txt لتفعيل صورة الملخص.")

st.divider()
st.markdown("""
<div style="text-align:center;color:gray;font-size:0.9rem;">
  <strong>Developed by Dr / Hussein Ali | Orange Lab — Microbiology CDSS</strong><br>
  EUCAST 2026 | CLSI M100 2026 | IDSA AMR 2025 | BNF 2025 | Egypt National Guidelines
</div>
""", unsafe_allow_html=True)
