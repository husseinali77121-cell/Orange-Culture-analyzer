import streamlit as st

st.set_page_config(page_title="Orange Culture Analyzer",
                   layout="wide", page_icon="🛡️")

# إخفاء GitHub وعناصر Streamlit
st.markdown("""
    <style>
    .stActionButton {display: none !important;}
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    header[data-testid="stHeader"] {display: none !important;}
    </style>
""", unsafe_allow_html=True)

import numpy as np
import cv2
import pytesseract
import re
from datetime import datetime
from difflib import SequenceMatcher

# ==========================================
# 📋 Antibiotics Database – Egyptian Market
# ==========================================
ABX_GUIDELINES = {
    # المجموعة الأساسية (لم تحذف)
    "Amoxicillin + Clavulanic acid": {
        "priority": 1, "class": "Beta-lactamase Inhibitor",
        "note": "✅ خيار قياسي (مثل Augmentin/Curam).",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["augmentin", "curam", "amoxiclav", "co-amoxiclav"],
        "organisms": ["E. coli","Klebsiella spp.","Staphylococcus aureus",
                      "Proteus mirabilis","Streptococcus spp.","H. influenzae",
                      "Streptococcus pneumoniae","Moraxella catarrhalis"],
        "specimen_notes": {
            "Blood":      "✅ فعال في bacteremia الموجبات والسالبات البسيطة.",
            "Sputum":     "✅ خيار جيد لـ CAP و exacerbation COPD.",
            "Wound Swab": "✅ فعال للعدوى الجلدية المختلطة.",
            "Pus":        "✅ جيد للخراجات والعدوى المختلطة.",
            "Urine":      "✅ خيار أول للمسالك غير المعقدة.",
            "Throat Swab":"✅ خيار لالتهاب الحلق بالعقديات.",
            "Nasal Swab": "✅ مناسب لحالات الجيوب الأنفية.",
        },
    },
    "Ampicillin/Sulbactam": {
        "priority": 2, "class": "Penicillin",
        "note": "💉 فعال للموجبات والسالبات. أساس علاج Acinetobacter بجرعات عالية (IDSA AMR).",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["unictam","sigmaclav","unasyn"],
        "organisms": ["E. coli","Klebsiella spp.","Staphylococcus aureus",
                      "Proteus mirabilis","Enterococcus faecalis", "Acinetobacter baumannii"],
        "specimen_notes": {
            "Blood":      "💉 IV فقط — فعال في bacteremia المختلطة.",
            "Sputum":     "💉 فعال في HAP/VAP خصوصاً Acinetobacter.",
            "Wound Swab": "💉 جيد للعدوى الجراحية والمختلطة.",
            "Pus":        "💉 فعال في الخراجات داخل البطن.",
        },
    },
    "Piperacillin + Tazobactam": {
        "priority": 4, "class": "Anti-pseudomonal Penicillin",
        "note": "🛑 (مثل Tazocin) مضاد احتياطي واسع الطيف جداً (IDSA AMR).",
        "renal_limit": 20, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["tazocin","pip-tazo","piptaz"],
        "organisms": ["Pseudomonas aeruginosa","E. coli","Klebsiella spp.",
                      "Enterococcus faecalis","Proteus mirabilis", "Acinetobacter baumannii",
                      "Bacteroides fragilis"],
        "specimen_notes": {
            "Blood":      "🛑 خيار قوي في sepsis شديد مع Pseudomonas.",
            "Sputum":     "🛑 VAP/HAP مع اشتباه Pseudomonas.",
            "Wound Swab": "🛑 العدوى الجراحية الشديدة.",
            "Pus":        "🛑 الخراجات داخل البطن الشديدة.",
        },
    },
    "Cephalexin": {
        "priority": 1, "class": "1st Gen Cephalosporin",
        "note": "✅ (مثل Ceporex) آمن للالتهابات البسيطة والجلد.",
        "renal_limit": 40, "renal_note": "⚖️ مباعدة الجرعات مطلوب.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["ceporex","keflex"],
        "organisms": ["Staphylococcus aureus","Streptococcus spp.",
                      "E. coli","Proteus mirabilis"],
        "specimen_notes": {
            "Wound Swab": "✅ خيار ممتاز للعدوى الجلدية البسيطة (cellulitis/impetigo).",
            "Urine":      "✅ مناسب للمسالك البسيطة.",
        },
    },
    "Cefadroxil": {
        "priority": 1, "class": "1st Gen Cephalosporin",
        "note": "✅ (مثل Duricef) فعال لالتهابات الحلق والجلد.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["duricef"],
        "organisms": ["Staphylococcus aureus","Streptococcus spp."],
        "specimen_notes": {
            "Wound Swab": "✅ جيد للعدوى الجلدية والأنسجة الرخوة.",
            "Sputum":     "✅ التهاب الحلق البكتيري (Strep pharyngitis).",
        },
    },
    "Cefaclor": {
        "priority": 2, "class": "2nd Gen Cephalosporin",
        "note": "✅ (مثل Ceclor) فعال للأذن الوسطى والمسالك.",
        "renal_limit": 10, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["ceclor"],
        "organisms": ["E. coli","H. influenzae","Staphylococcus aureus",
                      "Streptococcus spp.","Klebsiella spp.","Moraxella catarrhalis"],
        "specimen_notes": {
            "Sputum":     "✅ التهابات الجهاز التنفسي العلوي والأذن الوسطى.",
            "Urine":      "✅ مناسب للمسالك البولية البسيطة.",
        },
    },
    "Cefuroxime": {
        "priority": 2, "class": "2nd Gen Cephalosporin",
        "note": "✅ (مثل Zinnat) واسع المدى للجهاز التنفسي والمسالك.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["zinnat","ceftin"],
        "organisms": ["E. coli","Klebsiella spp.","H. influenzae",
                      "Staphylococcus aureus","Streptococcus spp.","Proteus mirabilis",
                      "Streptococcus pneumoniae","Moraxella catarrhalis"],
        "specimen_notes": {
            "Sputum":     "✅ CAP وعدوى الجهاز التنفسي.",
            "Wound Swab": "✅ عدوى الأنسجة الرخوة المتوسطة.",
            "Urine":      "✅ مناسب للمسالك.",
            "Blood":      "⚠️ لا يُفضل في bacteremia الشديدة — يُستبدل بـ IV.",
            "Throat Swab":"✅ خيار بديل لالتهاب الحلق.",
        },
    },
    "Ceftriaxone": {
        "priority": 3, "class": "3rd Gen Cephalosporin",
        "note": "⚠️ (مثل Rocephin) حقن فقط؛ لا يستخدم في الحالات البسيطة.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً (إطراح كبدي أساساً).",
        "hepatic_caution": True, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["rocephin","cefaxone","triaxone"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "Staphylococcus aureus","Streptococcus spp.","H. influenzae",
                      "Neisseria meningitidis","Streptococcus pneumoniae","Salmonella spp."],
        "specimen_notes": {
            "Blood":      "💉 خيار ممتاز في bacteremia والـ sepsis.",
            "CSF":        "💉 خيار أول في meningitis البكتيري.",
            "Sputum":     "💉 CAP الشديد الذي يحتاج دخول مستشفى.",
            "Urine":      "⚠️ يُحفظ للـ pyelonephritis الشديد — مش للمسالك البسيطة.",
        },
    },
    "Cefixime": {
        "priority": 2, "class": "3rd Gen Cephalosporin (Oral)",
        "note": "✅ (مثل Suprax) خيار فموي قوي للمسالك.",
        "renal_limit": 20, "renal_note": "⚖️ خفض الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["suprax","oroken"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "H. influenzae","Streptococcus spp."],
        "specimen_notes": {
            "Urine":      "✅ خيار فموي قوي للمسالك والـ pyelonephritis الخفيف.",
            "Sputum":     "✅ مناسب لعدوى الجهاز التنفسي الخفيفة.",
        },
    },
    "Cefotaxime": {
        "priority": 3, "class": "3rd Gen Cephalosporin",
        "note": "💉 (مثل Cefotax) يستخدم في العدوى الشديدة.",
        "renal_limit": 20, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["cefotax","claforan"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "Streptococcus spp.","H. influenzae","Neisseria meningitidis"],
        "specimen_notes": {
            "Blood":  "💉 bacteremia والـ sepsis.",
            "CSF":    "💉 meningitis — بديل Ceftriaxone.",
            "Sputum": "💉 CAP الشديد.",
        },
    },
    "Ceftazidime": {
        "priority": 4, "class": "3rd Gen Cephalosporin (Anti-pseudomonal)",
        "note": "🛑 (مثل Fortum) متخصص في جراثيم Pseudomonas.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري جداً.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["fortum","ceptaz"],
        "organisms": ["Pseudomonas aeruginosa","E. coli",
                      "Klebsiella spp.","Proteus mirabilis"],
        "specimen_notes": {
            "Blood":  "🛑 Pseudomonas bacteremia.",
            "Sputum": "🛑 VAP/HAP مع Pseudomonas.",
            "Urine":  "🛑 UTI معقد مع Pseudomonas.",
        },
    },
    "Cefoperazone": {
        "priority": 4, "class": "3rd Gen Cephalosporin",
        "note": "💉 (مثل Cefobid) فعال للمسالك والمرارة، يطرح كبدياً.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً؛ يطرح عبر الصفراء.",
        "hepatic_caution": True, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["cefobid"],
        "organisms": ["Pseudomonas aeruginosa","E. coli","Klebsiella spp.",
                      "Proteus mirabilis","Staphylococcus aureus"],
        "specimen_notes": {
            "Blood":  "💉 bacteremia في المرضى الكلويين (يطرح كبدياً).",
            "Pus":    "💉 عدوى البطن والمرارة.",
        },
    },
    "Cefepime": {
        "priority": 5, "class": "4th Gen Cephalosporin",
        "note": "🛑 (مثل Maxipime) مضاد قوي جداً للحالات الحرجة.",
        "renal_limit": 50,
        "renal_note": "⚠️ يتطلب تعديل جرعة دقيق لتجنب السمية العصبية.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["maxipime"],
        "organisms": ["Pseudomonas aeruginosa","E. coli","Klebsiella spp.",
                      "Proteus mirabilis","Staphylococcus aureus","Enterococcus faecalis",
                      "Acinetobacter baumannii"],
        "specimen_notes": {
            "Blood":  "🛑 sepsis شديد مع اشتباه Pseudomonas.",
            "Sputum": "🛑 VAP/HAP الحرجة.",
            "CSF":    "🛑 meningitis المعقد في ICU.",
        },
    },
    "Ciprofloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": "⚠️ (مثل Ciprofar) يفضل ادخاره للمسالك المعقدة.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Ciprofloxacin:\n"
            "  الموقف التقليدي: تجنب (FDA Category C).\n"
            "  الأدلة الحديثة (ACCP Journal 2025): الخطر الحقيقي\n"
            "  أقل مما كان متصوراً، ولم تُثبت تشوهات خلقية واضحة\n"
            "  في الدراسات الكبيرة.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)","Warfarin (مضادات التخثر)"],
        "aliases": ["ciprofar","cipro","ciproflox"],
        "organisms": ["E. coli","Klebsiella spp.","Pseudomonas aeruginosa",
                      "Proteus mirabilis","Staphylococcus aureus"],
        "specimen_notes": {
            "Urine":      "⚠️ فعال لكن يُحفظ للمسالك المعقدة (Pseudomonas/pyelonephritis).",
            "Blood":      "⚠️ bacteremia في الحالات المتوسطة.",
            "Sputum":     "⚠️ الفلوروكينولون الوحيد الفعال ضد Pseudomonas في الصدر.",
            "Wound Swab": "⚠️ عدوى الجروح المعقدة.",
        },
    },
    "Levofloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": "⚠️ (مثل Tavanic) فعال جداً للصدر والمسالك.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Levofloxacin:\n"
            "  فلوروكينولون — يُستخدم بحذر شديد.\n"
            "  بيانات أقل من Ciprofloxacin في الحمل.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["tavanic","levaquin","levoflox"],
        "organisms": ["E. coli","Klebsiella spp.","Pseudomonas aeruginosa",
                      "Staphylococcus aureus","Streptococcus spp.","H. influenzae",
                      "Streptococcus pneumoniae","Moraxella catarrhalis"],
        "specimen_notes": {
            "Sputum": "⚠️ خيار قوي لـ CAP وعدوى الجهاز التنفسي (respiratory quinolone).",
            "Urine":  "⚠️ فعال لكن يُحفظ للحالات المعقدة.",
            "Blood":  "⚠️ bacteremia في الحالات المتوسطة.",
        },
    },
    "Ofloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": "⚠️ (مثل Tarivid) واسع المدى.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Ofloxacin:\n"
            "  فلوروكينولون — يُستخدم بحذر شديد في الحمل.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["tarivid","oflox"],
        "organisms": ["E. coli","Klebsiella spp.","Staphylococcus aureus",
                      "Proteus mirabilis"],
        "specimen_notes": {
            "Urine":  "⚠️ مناسب للمسالك المتوسطة.",
            "Sputum": "⚠️ عدوى الجهاز التنفسي.",
        },
    },
    "Norfloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": "⚠️ (مثل Noroxin) متخصص في المسالك البولية فقط — لا يُستخدم خارجها.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب عند CrCl < 30.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Norfloxacin:\n"
            "  فلوروكينولون — يُستخدم بحذر شديد في الحمل.\n"
            "  الأدلة الحديثة (ACCP Journal 2025): الخطر\n"
            "  الحقيقي أقل مما كان متصوراً.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
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
        "priority": 1, "class": "Urinary Antiseptic",
        "note": "🎯 (مثل Macrofuran) الخيار الأول للمسالك البسيطة فقط.",
        "renal_limit": 30, "renal_note": "🚫 ممنوع إذا كانت التصفية < 30 مل/د.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Nitrofurantoin:\n"
            "  آمن في الـ 1st و 2nd trimester.\n"
            "  ممنوع في الـ 3rd trimester (خطر انحلال الدم\n"
            "  للجنين — hemolytic anemia).\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["macrofuran","macrobid","nitrofur"],
        "organisms": ["E. coli","Staphylococcus aureus",
                      "Enterococcus faecalis","Klebsiella spp.","Staphylococcus saprophyticus"],
        "specimen_notes": {
            "Urine": "🎯 مخصص للمسالك البولية البسيطة فقط — لا يُستخدم خارج البول.",
        },
    },
    "Fosfomycin": {
        "priority": 1, "class": "Phosphonic Acid",
        "note": "🎯 (مثل Monuril) خيار مثالي بجرعة واحدة للمسالك.",
        "renal_limit": 10, "renal_note": "⚠️ حذر في القصور الشديد.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Fosfomycin:\n"
            "  بيانات محدودة في الحمل.\n"
            "  يُعتبر آمناً نسبياً لعلاج UTI في الحمل\n"
            "  بجرعة واحدة عند الضرورة.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": [],
        "aliases": ["monuril","fosfocin"],
        "organisms": ["E. coli","Enterococcus faecalis",
                      "Staphylococcus aureus","Klebsiella spp."],
        "specimen_notes": {
            "Urine": "🎯 جرعة واحدة للـ uncomplicated UTI — مثالي.",
        },
    },
    "Gentamicin": {
        "priority": 4, "class": "Aminoglycoside",
        "note": "💉 (مثل Garamycin) يستخدم بحذر شديد - سام للكلى والأذن.",
        "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى ضرورية.",
        "hepatic_caution": False, "aware": "Access", "high_po": False,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — Gentamicin:\n"
            "  سُمية للأذن الجنينية (ototoxicity) — FDA Category D.\n"
            "  يعبر المشيمة ويتراكم في السائل الأمنيوسي.\n"
            "  خطر فقدان السمع الدائم للجنين."
        ),
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
        "priority": 4, "class": "Aminoglycoside",
        "note": "💉 (مثل Amikin) فعال جداً ضد السالبات المقاومة.",
        "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — Amikacin:\n"
            "  سُمية للأذن الجنينية (ototoxicity) — FDA Category D.\n"
            "  يعبر المشيمة ويتراكم في السائل الأمنيوسي.\n"
            "  خطر فقدان السمع الدائم للجنين."
        ),
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
        "priority": 2, "class": "Macrolide",
        "note": "✅ (مثل Zithrokan) فعال للجهاز التنفسي والكلاميديا.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["zithrokan","zithromax","azithro"],
        "organisms": ["Staphylococcus aureus","Streptococcus spp.",
                      "H. influenzae","Chlamydia spp.","Mycoplasma spp.",
                      "Streptococcus pneumoniae","Moraxella catarrhalis",
                      "Campylobacter jejuni","Salmonella spp."],
        "specimen_notes": {
            "Sputum":     "✅ خيار ممتاز لـ CAP والـ atypicals (Mycoplasma/Chlamydia).",
            "Wound Swab": "✅ عدوى الجلد الخفيفة بالموجبات.",
            "Urine":      "⚠️ فعال فقط في Chlamydia urethritis — مش UTI عادي.",
            "Stool":      "✅ علاج Salmonella و Campylobacter (الحالات الخفيفة).",
        },
    },
    "Clarithromycin": {
        "priority": 2, "class": "Macrolide",
        "note": "✅ (مثل Klacid) فعال لجرثومة المعدة والصدر.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — Clarithromycin:\n"
            "  ارتبط بتشوهات خلقية في الدراسات الحيوانية\n"
            "  والبشرية — FDA Category C.\n"
            "  البديل الآمن: Azithromycin."
        ),
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["klacid","biaxin"],
        "organisms": ["Staphylococcus aureus","Streptococcus spp.",
                      "H. pylori","H. influenzae","Mycoplasma spp.",
                      "Streptococcus pneumoniae"],
        "specimen_notes": {
            "Sputum": "✅ CAP والـ atypical pneumonia.",
            "Stool":  "✅ H. pylori eradication therapy.",
        },
    },
    "Trimethoprim/Sulfamethoxazole": {
        "priority": 2, "class": "Sulfonamide",
        "note": "✅ (مثل Septra/Sutrim) فعال للمسالك والجهاز التنفسي.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — TMP/SMX (Sutrim/Bactrim):\n"
            "  يثبط حمض الفوليك — خطر Neural Tube Defects\n"
            "  في الـ 1st trimester.\n"
            "  يسبب kernicterus للجنين في الـ 3rd trimester."
        ),
        "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["septra","sutrim","bactrim","co-trimoxazole","tmp-smx"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "Staphylococcus aureus","Streptococcus spp.","Acinetobacter baumannii"],
        "specimen_notes": {
            "Urine":      "✅ فعال للمسالك البسيطة عند تأكيد الحساسية.",
            "Sputum":     "✅ الجهاز التنفسي والـ PCP prophylaxis.",
            "Wound Swab": "✅ MRSA skin infections (SSTI).",
        },
    },
    "Metronidazole": {
        "priority": 1, "class": "Nitroimidazole",
        "note": "✅ (مثل Flagyl) الخيار الأول للأنيروبيك والطفيليات.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True, "aware": "Access", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Metronidazole:\n"
            "  تجنب في الـ 1st trimester (مخاوف تاريخية).\n"
            "  مقبول ومُستخدم في الـ 2nd و 3rd trimester\n"
            "  بإشراف طبي.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["flagyl","metro","metrogyl"],
        "organisms": ["Anaerobes (لاهوائيات)","Trichomonas vaginalis",
                      "H. pylori","C. difficile","Bacteroides spp.",
                      "Bacteroides fragilis"],
        "specimen_notes": {
            "Pus":        "✅ الخراجات والعدوى المختلطة (anaerobic coverage).",
            "Wound Swab": "✅ العدوى الجراحية التي تشمل اللاهوائيات.",
            "Stool":      "✅ الخيار الأول لـ C. difficile وبعض الطفيليات.",
            "Blood":      "✅ sepsis البطن مع اشتباه anaerobic.",
        },
    },
    "Tinidazole": {
        "priority": 2, "class": "Nitroimidazole",
        "note": "✅ (مثل Fasigyn) بديل Metronidazole بجرعة أقل تكراراً.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True, "aware": "Access", "high_po": True,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — Tinidazole:\n"
            "  ممنوع في الـ 1st trimester.\n"
            "  بيانات أقل من Metronidazole — يُفضل تجنبه\n"
            "  طوال الحمل والاستعاضة بـ Metronidazole."
        ),
        "child_safe": False,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["fasigyn","tini"],
        "organisms": ["Anaerobes (لاهوائيات)","Trichomonas vaginalis",
                      "H. pylori","Giardia lamblia"],
        "specimen_notes": {
            "Stool":      "✅ Giardia و H. pylori.",
            "Wound Swab": "✅ عدوى اللاهوائيات الخفيفة.",
        },
    },
    "Doxycycline": {
        "priority": 2, "class": "Tetracycline",
        "note": "✅ (مثل Vibramycin) فعال للكلاميديا والمايكوبلازما.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً نسبياً.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Doxycycline:\n"
            "  الموقف التقليدي: ممنوع (FDA Category D).\n"
            "  الأدلة الحديثة (ACCP Journal 2025): الخطر\n"
            "  الحقيقي أقل مما كان متصوراً في الاستخدام\n"
            "  القصير المدى — لم تُثبت تشوهات عظمية واضحة\n"
            "  في الدراسات الحديثة الكبيرة.\n"
            "  مع ذلك: لا تزال البيانات غير كافية للتأكيد.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["vibramycin","doxy"],
        "organisms": ["Chlamydia spp.","Mycoplasma spp.",
                      "Staphylococcus aureus","H. influenzae","Rickettsia spp.",
                      "Acinetobacter baumannii"],
        "specimen_notes": {
            "Sputum":     "✅ atypical pneumonia (Mycoplasma/Chlamydia).",
            "Wound Swab": "✅ MRSA SSTI و Rickettsia.",
            "Blood":      "✅ Rickettsia bacteremia.",
        },
    },
    "Cefuroxime sodium": {
        "priority": 2, "class": "2nd Gen Cephalosporin (IV)",
        "note": "💉 (مثل Zinacef) نفس Cefuroxime لكن IV فقط — للحالات التي تحتاج حقن.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["zinacef","cefuroxime iv","cefuroxime sodium"],
        "organisms": ["E. coli","Klebsiella spp.","H. influenzae",
                      "Staphylococcus aureus","Streptococcus spp.","Proteus mirabilis"],
        "specimen_notes": {
            "Blood":      "💉 bacteremia المتوسطة الشدة.",
            "Sputum":     "💉 CAP الذي يحتاج دخول مستشفى.",
            "Wound Swab": "💉 العدوى الجراحية المتوسطة.",
            "Urine":      "💉 pyelonephritis يحتاج IV.",
        },
    },
    "Ertapenem": {
        "priority": 5, "class": "Carbapenem (non-anti-pseudomonal)",
        "note": "🛑 (مثل Invanz) كاربابينيم بجرعة يومية واحدة — لا يغطي Pseudomonas.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب عند CrCl < 30.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["invanz","ertapenem"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "Staphylococcus aureus","Enterococcus faecalis",
                      "Anaerobes (لاهوائيات)"],
        "specimen_notes": {
            "Blood":  "🛑 ESBL bacteremia — يفضل على Meropenem للحفاظ على الكاربابينيم.",
            "Urine":  "🛑 ESBL-producing UTI المعقد فقط.",
            "Pus":    "🛑 عدوى البطن المعقدة بـ ESBL.",
        },
    },
    "Meropenem": {
        "priority": 5, "class": "Carbapenem",
        "note": "🛑 (مثل Meronem) مضاد الملاذ الأخير للمقاومة.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["meronem","merrem"],
        "organisms": ["Pseudomonas aeruginosa","Klebsiella spp.","E. coli",
                      "Enterococcus faecalis","Staphylococcus aureus","MRSA",
                      "Acinetobacter baumannii","Listeria monocytogenes"],
        "specimen_notes": {
            "Blood":  "🛑 sepsis شديد — MDR organisms — ICU.",
            "CSF":    "🛑 meningitis المعقد — MDR organisms.",
            "Sputum": "🛑 VAP/HAP بـ MDR organisms.",
            "Urine":  "🛑 UTI المعقد جداً بـ CRE.",
        },
    },
    "Vancomycin": {
        "priority": 5, "class": "Glycopeptide",
        "note": "🛑 خاص بـ MRSA والحالات الحرجة - مراقبة الـ Trough.",
        "renal_limit": 50, "renal_note": "⚖️ مراقبة مستوى الدواء في الدم.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Vancomycin:\n"
            "  يُستخدم عند الضرورة القصوى (MRSA في الحمل).\n"
            "  مراقبة وظائف الكلى والسمع للأم والجنين.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": True,
        "interacts_with": ["NSAIDs (مسكنات الألم)"],
        "aliases": ["vancocin","vanco"],
        "organisms": ["MRSA","Staphylococcus aureus","Enterococcus faecalis",
                      "Streptococcus spp.","C. difficile","Streptococcus pneumoniae"],
        "specimen_notes": {
            "Blood":  "🛑 MRSA bacteremia.",
            "CSF":    "🛑 MRSA meningitis.",
            "Sputum": "🛑 MRSA pneumonia في ICU.",
            "Wound Swab": "🛑 MRSA wound infection.",
        },
    },
    "Linezolid": {
        "priority": 5, "class": "Oxazolidinone",
        "note": "🛑 (مثل Averozolid) للموجبات المقاومة (MRSA/VRE) فقط.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": False, "aware": "Reserve", "high_po": True,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — Linezolid:\n"
            "  بيانات غير كافية في الحمل البشري.\n"
            "  أثبت سُمية جنينية في الحيوانات.\n"
            "  يُستخدم فقط عند انعدام البدائل الأخرى."
        ),
        "child_safe": True,
        "interacts_with": ["SSRI (أدوية الاكتئاب)"],
        "aliases": ["averozolid","zyvox"],
        "organisms": ["MRSA","Staphylococcus aureus","Enterococcus faecalis",
                      "VRE","Streptococcus spp.","Streptococcus pneumoniae"],
        "specimen_notes": {
            "Blood":      "🛑 VRE/MRSA bacteremia.",
            "Sputum":     "🛑 MRSA pneumonia — تركيز رئوي ممتاز.",
            "Wound Swab": "🛑 MRSA/VRE wound infection.",
            "CSF":        "🛑 اختراق ممتاز للـ CNS.",
        },
    },
    "Colistin": {
        "priority": 6, "class": "Polymyxin",
        "note": "🔴 الملاذ الأخير (Reserve) للبكتيريا سالبة الجرام شديدة المقاومة (MDR).",
        "renal_limit": 80, "renal_note": "⚖️ سام جداً للكلى، تعديل الجرعة والمراقبة حتمية.",
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
    # المضادات الجديدة
    "Clindamycin": {
        "priority": 2, "class": "Lincosamide",
        "note": "✅ (مثل Dalacin C) فعال للموجبات واللاهوائيات، بديل في حساسية البنسيلين.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True, "aware": "Access", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["dalacin c","clinacin","clinda"],
        "organisms": ["Staphylococcus aureus","Streptococcus spp.",
                      "Anaerobes (لاهوائيات)","Bacteroides fragilis"],
        "specimen_notes": {
            "Wound Swab": "✅ عدوى الجلد والأنسجة الرخوة (بديل في حساسية البنسيلين).",
            "Pus":        "✅ خراجات الرئة والبطن (مع تغطية لاهوائية).",
            "Blood":      "⚠️ bacteremia؟ ليس الخيار الأول لكنه مفيد للحالات المختلطة.",
        },
    },
    "Moxifloxacin": {
        "priority": 2, "class": "Fluoroquinolone (Respiratory)",
        "note": "⚠️ (مثل Avelox) فلوروكينولون تنفسي قوي جداً مع غطاء لاهوائي.",
        "renal_limit": 0, "renal_note": "🟢 لا يحتاج تعديل كلوي.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Moxifloxacin:\n"
            "  تجنب في الحمل إلا للضرورة القصوى.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["avelox","moxiflox"],
        "organisms": ["Streptococcus pneumoniae","H. influenzae",
                      "Moraxella catarrhalis","Anaerobes (لاهوائيات)"],
        "specimen_notes": {
            "Sputum":     "✅ CAP وحالات الجهاز التنفسي المعقدة.",
            "Wound Swab": "✅ عدوى الجلد المختلطة.",
        },
    },
    "Cefpodoxime": {
        "priority": 2, "class": "3rd Gen Cephalosporin (Oral)",
        "note": "✅ (مثل Orelox) بديل فموي لـ Ceftriaxone في الحالات الخفيفة.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة.",
        "hepatic_caution": False, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["orelox","cefpodoxime"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "Streptococcus pneumoniae","H. influenzae"],
        "specimen_notes": {
            "Sputum": "✅ CAP الخفيف للتبديل الفموي.",
            "Urine":  "✅ بديل Cefixime في UTI.",
        },
    },
    "Imipenem/Cilastatin": {
        "priority": 5, "class": "Carbapenem",
        "note": "🛑 (مثل Tienam) أوسع الكاربابينيمات، ينفع لـ MDR و Pseudomonas.",
        "renal_limit": 60, "renal_note": "⚖️ تعديل الجرعة بدقة.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["tienam","imipenem"],
        "organisms": ["Pseudomonas aeruginosa","Acinetobacter baumannii",
                      "E. coli","Klebsiella spp.","Bacteroides fragilis"],
        "specimen_notes": {
            "Blood": "🛑 MDR bacteremia خيار قوي.",
            "CSF":   "⚠️ قد يسبب اختلاجات — تجنب في meningitis إلا للضرورة.",
        },
    },
    "Rifaximin": {
        "priority": 2, "class": "Rifamycin",
        "note": "🎯 (مثل Xifaxan) غير ممتص، للإسهال البكتيري والاعتلال الدماغي الكبدي.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": "بيانات محدودة — يُستخدم بحذر.",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["xifaxan","rifaximin"],
        "organisms": ["E. coli","Salmonella spp.","Shigella spp.","Campylobacter jejuni"],
        "specimen_notes": {
            "Stool": "✅ إسهال المسافرين وبعض حالات القولون العصبي.",
        },
    },
    "Teicoplanin": {
        "priority": 5, "class": "Glycopeptide",
        "note": "🛑 (مثل Targocid) بديل Vancomycin أقل سمية كلوية.",
        "renal_limit": 60, "renal_note": "⚖️ مراقبة المستويات.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Warn",
        "preg_note": "يُستخدم عند الضرورة فقط.",
        "child_safe": True,
        "interacts_with": ["NSAIDs (مسكنات الألم)"],
        "aliases": ["targocid","teicoplanin"],
        "organisms": ["MRSA","Staphylococcus aureus","Enterococcus faecalis"],
        "specimen_notes": {
            "Blood": "🛑 MRSA bacteremia — بديل Vancomycin.",
            "Wound Swab": "🛑 عدوى الجلد بالمكورات المقاومة.",
        },
    },
}

# ==========================================
# 🦠 Organism → First-line / Avoid mapping
# ==========================================
ORGANISM_PROFILE = {
    "E. coli": {
        "first_line": ["Nitrofurantoin","Fosfomycin","Trimethoprim/Sulfamethoxazole","Amoxicillin + Clavulanic acid"],
        "second_line": ["Cefuroxime","Cefuroxime sodium","Cefixime","Norfloxacin","Ciprofloxacin"],
        "third_line": ["Ertapenem","Meropenem"],
        "avoid": [],
        "urine_note": "Norfloxacin: مخصص للمسالك فقط.\nErtapenem: يُحفظ لـ ESBL.",
        "specimen_context": {"Blood":"🔬 bacteremia البول/البطن.","Stool":"🔬 ETEC/EPEC."},
        "note": "🔬 الأكثر شيوعاً في مزارع البول.",
    },
    "Klebsiella spp.": {
        "first_line": ["Amoxicillin + Clavulanic acid","Cefuroxime","Cefixime"],
        "second_line": ["Cefuroxime sodium","Norfloxacin","Ciprofloxacin","Piperacillin + Tazobactam","Ceftriaxone"],
        "third_line": ["Ertapenem","Meropenem"],
        "avoid": ["Ampicillin"],
        "urine_note": "Ertapenem: لـ ESBL فقط.",
        "specimen_context": {"Blood":"🔬 bacteremia الكبد.","Sputum":"🔬 HAP."},
        "note": "🔬 تحقق من ESBL.",
    },
    "Pseudomonas aeruginosa": {
        "first_line": ["Piperacillin + Tazobactam","Ceftazidime","Ciprofloxacin"],
        "second_line": ["Cefepime","Meropenem","Amikacin"],
        "third_line": ["Colistin"],
        "avoid": ["Nitrofurantoin","Fosfomycin","TMP/SMX","Cephalexin","Cefadroxil","Cefaclor","Norfloxacin","Cefuroxime sodium","Ertapenem"],
        "urine_note": "Ertapenem: لا نشاط.",
        "specimen_context": {"Blood":"🔴 bacteremia عالية الخطورة.","Sputum":"🔴 VAP."},
        "note": "🔬 تحتاج مضادات anti-pseudomonal.",
    },
    "Acinetobacter baumannii": {
        "first_line": ["Ampicillin/Sulbactam"],
        "second_line": ["Meropenem","Amikacin","Trimethoprim/Sulfamethoxazole","Doxycycline"],
        "third_line": ["Colistin"],
        "avoid": ["Ertapenem","Cephalexin","Cefuroxime","Ceftriaxone","Azithromycin","Clarithromycin","Nitrofurantoin","Fosfomycin"],
        "specimen_context": {"Blood":"🔴 ICU.","Sputum":"🔴 VAP."},
        "note": "🔴 MDR. Ampicillin/Sulbactam بجرعات عالية.",
    },
    "Staphylococcus aureus": {
        "first_line": ["Cephalexin","Cefadroxil","Amoxicillin + Clavulanic acid"],
        "second_line": ["Cefuroxime sodium","Azithromycin","Doxycycline"],
        "third_line": [],
        "avoid": [],
        "urine_note": "Norfloxacin: نشاط ضعيف. تحقق من MRSA.",
        "specimen_context": {"Blood":"🔬 endocarditis خطر.","Wound Swab":"🔬 الأكثر شيوعاً."},
        "note": "🔬 تحقق من MRSA.",
    },
    "MRSA": {
        "first_line": ["Vancomycin","Linezolid"],
        "second_line": ["Trimethoprim/Sulfamethoxazole","Doxycycline"],
        "third_line": [],
        "avoid": ["Cephalexin","Cefadroxil","Cefaclor","Cefuroxime","Cefuroxime sodium","Ceftriaxone","Amoxicillin + Clavulanic acid","Ampicillin/Sulbactam","Piperacillin + Tazobactam","Ertapenem"],
        "specimen_context": {"Blood":"🔴 emergency.","Wound Swab":"🔴 CA-MRSA."},
        "note": "🔴 مقاوم لجميع البيتا-لاكتام!",
    },
    "Proteus mirabilis": {
        "first_line": ["Amoxicillin + Clavulanic acid","Cefuroxime","Cefixime"],
        "second_line": ["Cefuroxime sodium","Norfloxacin","Ciprofloxacin","Trimethoprim/Sulfamethoxazole"],
        "third_line": ["Ertapenem"],
        "avoid": ["Nitrofurantoin","Tetracyclines","Colistin"],
        "urine_note": "Nitrofurantoin: مقاوم طبيعي.",
        "specimen_context": {"Urine":"🔬 urease-positive."},
        "note": "🔬 مقاوم طبيعي لـ Nitrofurantoin.",
    },
    "Enterococcus faecalis": {
        "first_line": ["Amoxicillin + Clavulanic acid","Fosfomycin","Nitrofurantoin"],
        "second_line": ["Ampicillin/Sulbactam","Vancomycin","Linezolid"],
        "third_line": [],
        "avoid": ["Cephalosporins (كل الجيل)","Trimethoprim/Sulfamethoxazole","Cefuroxime sodium","Ertapenem","Norfloxacin"],
        "specimen_context": {"Urine":"🔬 كاتيتر.","Blood":"⚠️ endocarditis."},
        "note": "🔬 مقاوم للسيفالوسبورين وErtapenem.",
    },
    "Salmonella spp.": {
        "first_line": ["Ceftriaxone","Azithromycin","Ciprofloxacin"],
        "second_line": ["Trimethoprim/Sulfamethoxazole","Cefixime"],
        "third_line": [],
        "avoid": ["Nitrofurantoin","Fosfomycin","Cephalexin","Cefadroxil","Cefaclor","Cefuroxime","Metronidazole","Doxycycline"],
        "specimen_context": {"Stool":"🔬 الحالات الشديدة فقط.","Blood":"🔬 التيفود."},
        "note": "🔬 العلاج للحالات الشديدة فقط.",
    },
    "Shigella spp.": {
        "first_line": ["Azithromycin","Ciprofloxacin","Ceftriaxone"],
        "second_line": ["Trimethoprim/Sulfamethoxazole"],
        "third_line": [],
        "avoid": ["Nitrofurantoin","Fosfomycin","Amoxicillin + Clavulanic acid","Metronidazole"],
        "specimen_context": {"Stool":"🔬 مضاد حيوي ضروري.","Blood":"🔬 نادر."},
        "note": "🔬 مقاومة TMP-SMX شائعة.",
    },
    "Campylobacter jejuni": {
        "first_line": ["Azithromycin"],
        "second_line": ["Ciprofloxacin"],
        "third_line": [],
        "avoid": ["Trimethoprim/Sulfamethoxazole","Penicillins","Cephalosporins","Nitrofurantoin","Fosfomycin"],
        "specimen_context": {"Stool":"🔬 غالباً ذاتي الشفاء.","Blood":"🔬 نقص المناعة."},
        "note": "🔬 Azithromycin هو الخيار الأول.",
    },
    # ========= الكائنات الجديدة =========
    "Streptococcus pneumoniae": {
        "first_line": ["Amoxicillin + Clavulanic acid","Cefuroxime","Ceftriaxone"],
        "second_line": ["Levofloxacin","Moxifloxacin","Vancomycin"],
        "third_line": [],
        "avoid": ["Nitrofurantoin","Fosfomycin","Metronidazole"],
        "specimen_context": {
            "Sputum":"🔬 CAP الأكثر شيوعاً.","CSF":"🔬 أشهر مسبب للسحايا.","Blood":"🔬 bacteremia خطيرة.",
            "Nasal Swab":"🔬 قد يكون حالة حمل.",
        },
        "note": "🔬 تحقق من حساسية البنسلين (MIC).",
    },
    "Streptococcus pyogenes (Group A)": {
        "first_line": ["Amoxicillin + Clavulanic acid","Cephalexin","Cefadroxil"],
        "second_line": ["Azithromycin","Clindamycin"],
        "third_line": [],
        "avoid": ["Nitrofurantoin","Fosfomycin","Trimethoprim/Sulfamethoxazole"],
        "specimen_context": {
            "Throat Swab":"🔬 التهاب الحلق العقدي.","Wound Swab":"🔬 cellulitis/impetigo.","Blood":"🔬 sepsis نادر لكن خطير.",
        },
        "note": "🔬 حساس جداً للبنسلين.",
    },
    "Haemophilus influenzae": {
        "first_line": ["Amoxicillin + Clavulanic acid","Cefuroxime","Ceftriaxone"],
        "second_line": ["Azithromycin","Levofloxacin","Moxifloxacin"],
        "third_line": [],
        "avoid": ["Nitrofurantoin","Fosfomycin"],
        "specimen_context": {
            "Sputum":"🔬 CAP و exacerbation COPD.","CSF":"🔬 سحايا الأطفال.","Blood":"🔬 bacteremia.",
        },
        "note": "🔬 بعض السلالات منتجة للبيتا-لاكتاماز.",
    },
    "Moraxella catarrhalis": {
        "first_line": ["Amoxicillin + Clavulanic acid","Cefuroxime","Cefaclor"],
        "second_line": ["Azithromycin","Levofloxacin","Moxifloxacin"],
        "third_line": [],
        "avoid": ["Nitrofurantoin","Fosfomycin","Trimethoprim/Sulfamethoxazole"],
        "specimen_context": {
            "Sputum":"🔬 COPD exacerbation.","Nasal Swab":"🔬 التهاب الجيوب.",
        },
        "note": "🔬 معظم السلالات منتجة للبيتا-لاكتاماز.",
    },
    "Neisseria meningitidis": {
        "first_line": ["Ceftriaxone","Cefotaxime"],
        "second_line": ["Meropenem","Ampicillin/Sulbactam"],
        "third_line": [],
        "avoid": ["Vancomycin (لا يخترق BBB)","Colistin"],
        "specimen_context": {
            "CSF":"🔴 سحايا حادة.","Blood":"🔴 meningococcemia.",
        },
        "note": "🔴 حالة طوارئ؛ Ceftriaxone هو الخط الأول.",
    },
    "Listeria monocytogenes": {
        "first_line": ["Ampicillin/Sulbactam","Amoxicillin + Clavulanic acid"],
        "second_line": ["Meropenem","Trimethoprim/Sulfamethoxazole"],
        "third_line": [],
        "avoid": ["Cephalosporins (كل الأجيال)","Vancomycin","Colistin"],
        "specimen_context": {
            "CSF":"🔴 سحايا حديثي الولادة/كبار السن/الحوامل.","Blood":"🔴 bacteremia.",
        },
        "note": "🔬 مقاوم طبيعي للسيفالوسبورين.",
    },
    "Streptococcus agalactiae (Group B)": {
        "first_line": ["Ampicillin/Sulbactam","Amoxicillin + Clavulanic acid"],
        "second_line": ["Cefazolin (غير موجود)","Vancomycin","Clindamycin"],
        "third_line": [],
        "avoid": ["Trimethoprim/Sulfamethoxazole","Nitrofurantoin"],
        "specimen_context": {
            "CSF":"🔴 حديثي الولادة.","Blood":"🔴 bacteremia.","Urine":"⚠️ حمل.",
        },
        "note": "🔬 حساس للبنسلين.",
    },
    "Staphylococcus saprophyticus": {
        "first_line": ["Nitrofurantoin","Fosfomycin","Trimethoprim/Sulfamethoxazole"],
        "second_line": ["Cephalexin","Amoxicillin + Clavulanic acid"],
        "third_line": [],
        "avoid": ["Metronidazole","Colistin"],
        "urine_note": "سبب شائع لـ UTI في النساء الشابات.",
        "specimen_context": {"Urine":"🔬 UTI بسيطة."},
        "note": "🔬 دائماً مقاوم لـ Novobiocin (لا يستخدم في مصر).",
    },
    "Bacteroides fragilis": {
        "first_line": ["Metronidazole"],
        "second_line": ["Clindamycin","Piperacillin + Tazobactam","Imipenem/Cilastatin"],
        "third_line": [],
        "avoid": ["Cephalosporins","Fluoroquinolones","Aminoglycosides"],
        "specimen_context": {
            "Blood":"🔴 bacteremia البطن.","Pus":"🔴 خراجات البطن.","Wound Swab":"🔴 الجروح الجراحية.",
        },
        "note": "🔬 لاهوائي إجباري — Metronidazole هو الخيار.",
    },
    "Clostridioides difficile": {
        "first_line": ["Metronidazole","Vancomycin (فموي)"],
        "second_line": ["Fidaxomicin (غير متوفر)","Teicoplanin (فموي)"],
        "third_line": [],
        "avoid": ["Clindamycin","Cephalosporins","Fluoroquinolones"],
        "specimen_context": {"Stool":"🔴 إسهال المستشفيات.","Blood":"نادر."},
        "note": "🔴 أوقف المضاد الحيوي المسبب إن أمكن.",
    },
}

BACTERIA_TYPES = list(ORGANISM_PROFILE.keys())

SPECIMEN_TYPES = ["Urine","Blood","Sputum","Wound Swab","Pus","Stool","CSF","Throat Swab","Nasal Swab"]
COMMON_MEDS    = ["Antacids (مضادات الحموضة)","Warfarin (مضادات التخثر)",
                  "NSAIDs (مسكنات الألم)","SSRI (أدوية الاكتئاب)"]
AWARE_COLORS   = {"Access":"🟢 Access","Watch":"🟡 Watch","Reserve":"🔴 Reserve"}

# ==========================================
# 🔍 OCR + Fuzzy Matching (بدون تغيير)
# ==========================================
def fuzzy_match(word, target):
    w, t = word.lower(), target.lower()
    if t in w or w in t:
        return 100
    ratio = SequenceMatcher(None, w, t).ratio() * 100
    return ratio

def extract_all_data(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img        = cv2.imdecode(file_bytes, 1)
    gray       = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh  = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    full_text  = pytesseract.image_to_string(thresh, config='--psm 6')
    text_lower = full_text.lower()

    age_match      = re.search(r"(\d+)\s*[Yy]ears?", full_text)
    detected_age   = age_match.group(1) if age_match else "25"
    detected_sex   = "Female" if "female" in text_lower else "Male"

    detected_specimen = "Urine"
    for s in SPECIMEN_TYPES:
        if s.lower() in text_lower:
            detected_specimen = s; break

    detected_organism = "E. coli"
    organism_counts = {}
    for b in BACTERIA_TYPES:
        count = text_lower.count(b.lower())
        if count > 0:
            organism_counts[b] = count
    if organism_counts:
        detected_organism = max(organism_counts, key=organism_counts.get)

    sir_map = {}
    for line in full_text.splitlines():
        ll = line.lower().strip()
        result = None
        if re.search(r'\b(s|sensitive|sens)\b', ll):    result = "S"
        elif re.search(r'\b(r|resistant|resist)\b', ll): result = "R"
        elif re.search(r'\b(i|intermediate|inter)\b', ll): result = "I"
        if result:
            for abx_name, info in ABX_GUIDELINES.items():
                for name in [abx_name] + info["aliases"]:
                    if fuzzy_match(name, ll) >= 75:
                        sir_map[abx_name] = result; break

    start = text_lower.find("highly")
    if start == -1: start = text_lower.find("sensitive")
    end   = text_lower.find("resistant")
    area  = full_text[start:end] if (start != -1 and end != -1) else full_text
    words = area.lower().split()

    detected_drugs = []
    for abx_name, info in ABX_GUIDELINES.items():
        matched = False
        for name in [abx_name] + info["aliases"]:
            for w in words:
                if any(fuzzy_match(w, nw) >= 82 for nw in name.lower().split()):
                    matched = True; break
            if matched: break
        if matched:
            detected_drugs.append(abx_name)

    return (
        {"Age": detected_age, "Sex": detected_sex,
         "Specimen": detected_specimen, "Organism": detected_organism},
        list(set(detected_drugs)),
        sir_map,
    )

# ==========================================
# 📄 Report Generator (بدون تغيير جوهري)
# ==========================================
RENAL_BAN_REASONS = {
    "nitrofurantoin": (
        "Nitrofurantoin يحتاج وظيفة كلى سليمة ليتركز في البول.\n"
        "  عند CrCl < 30 مل/د:\n"
        "  - لا يصل لتركيز علاجي كافٍ في البول → لا يقتل الجرثومة.\n"
        "  - يتراكم في الدم → خطر سُمية رئوية وعصبية.\n"
        "  السبب الطبي: الدواء يُطرح كلياً عبر الترشيح الكبيبي."
    ),
}
CHILD_BAN_REASONS = {
    "fluoroquinolone": (
        "الفلوروكينولونات تؤثر على غضاريف النمو في الأطفال < 18 سنة.\n"
        "  أثبتت الدراسات الحيوانية تلف مفصلي دائم.\n"
        "  تُستخدم فقط عند انعدام البدائل الأخرى تماماً."
    ),
    "tetracycline": (
        "Doxycycline والتتراسيكلينات تترسب في العظام والأسنان النامية\n"
        "  → تلوين دائم للأسنان وتثبيط نمو العظام.\n"
        "  ممنوعة < 8 سنوات بشكل مطلق (AAP)، وتُتجنب حتى 18 سنة."
    ),
}

def generate_report(age, sex, weight, cl_cr, is_renal, is_preg, is_hepatic,
                    allowed, warned, banned, preg_warn_items,
                    organism, specimen, interactions, sir_map):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    SEP  = "=" * 50
    SEP2 = "-" * 50
    r    = []

    r.append(SEP)
    r.append("   ORANGE LAB — CLINICAL DECISION REPORT")
    r.append(SEP)
    r.append(f"  Date      : {now}")
    r.append(SEP)

    r.append("\nPATIENT DETAILS:")
    r.append(f"  Age     : {age} years")
    r.append(f"  Gender  : {sex}")
    r.append(f"  Weight  : {weight} kg")
    renal_str = (f"IMPAIRED  |  CrCl = {cl_cr:.1f} ml/min  "
                 f"({'Mild' if cl_cr>=60 else 'Moderate' if cl_cr>=30 else 'Severe'})")
    r.append(f"  Renal   : {renal_str if is_renal else 'Normal'}")
    r.append(f"  Hepatic : {'IMPAIRED' if is_hepatic else 'Normal'}")
    if sex == "Female":
        r.append(f"  Pregnancy: {'PREGNANT' if is_preg else 'Not pregnant'}")

    r.append(f"\nCULTURE:")
    r.append(f"  Specimen : {specimen}")
    r.append(f"  Organism : {organism}")
    if organism in ORGANISM_PROFILE:
        op = ORGANISM_PROFILE[organism]
        r.append(f"  Note     : {op['note']}")
        spec_ctx = op.get("specimen_context", {}).get(specimen, "")
        if spec_ctx:
            r.append(f"  Specimen Context: {spec_ctx}")
        r.append(f"  First-line (guidelines): {', '.join(op['first_line'])}")
        if op["avoid"]:
            r.append(f"  Avoid (intrinsic resistance): {', '.join(op['avoid'])}")

    if sir_map:
        r.append(f"\nSENSITIVITY RESULTS (extracted from image):")
        r.append(f"  {'Antibiotic':<35} Result")
        r.append(f"  {'-'*35} ------")
        for drug, res in sir_map.items():
            icon = "Sensitive (S)" if res=="S" else ("Resistant (R)" if res=="R" else "Intermediate (I)")
            r.append(f"  {drug:<35} {icon}")

    non_preg = [i for i in interactions if "🤰" not in i]
    if non_preg:
        r.append(f"\nDRUG INTERACTIONS / WARNINGS:")
        for i in sorted(set(non_preg)):
            r.append(f"  ! {i}")

    r.append(f"\n{SEP}")
    r.append("  RECOMMENDED ANTIBIOTICS")
    r.append(SEP)
    if allowed:
        for item in sorted(allowed, key=lambda x: x["priority"]):
            sir_tag  = f"  [Culture: {sir_map.get(item['name'],'?')}]" if sir_map else ""
            preg_tag = "  [Pregnancy: Use with caution]" if (is_preg and item["preg_status"]=="Warn") else ""
            r.append(f"\n  {item['name']}{sir_tag}{preg_tag}")
            r.append(f"  {SEP2}")
            r.append(f"  WHO AWaRe : {item['aware']}")
            r.append(f"  Class     : {item['class']}")
            r.append(f"  Route     : {'Oral (PO)' if item['high_po'] else 'IV only'}")
            spec_note = item.get("specimen_notes", {}).get(specimen, "")
            if spec_note:
                r.append(f"  Note      : {item['note']}  |  [{specimen}]: {spec_note}")
            else:
                r.append(f"  Note      : {item['note']}")
            if is_renal:
                r.append(f"  Renal     : {item['renal_note']}")
            if is_preg and item["preg_status"] == "Warn":
                r.append(f"  Pregnancy : {item['preg_note'].splitlines()[0]}")
    else:
        r.append("  No recommended options after applying all restrictions.")

    if warned:
        r.append(f"\n{SEP}")
        r.append("  DOSE ADJUSTMENT REQUIRED")
        r.append(f"  (Antibiotic is still effective but needs modified dosing)")
        r.append(SEP)
        r.append(f"\n  WHY dose adjustment is needed in renal impairment:")
        r.append(f"  Most antibiotics are eliminated by the kidneys.")
        r.append(f"  When kidney function is reduced (low CrCl), the drug")
        r.append(f"  accumulates in the blood → risk of toxicity.")
        r.append(f"  Reducing the dose or extending the interval maintains")
        r.append(f"  efficacy while avoiding toxic accumulation.")
        r.append(f"  Patient CrCl = {cl_cr:.1f} ml/min\n")
        for item in warned:
            sir_tag = f"  [Culture: {sir_map.get(item['name'],'?')}]" if sir_map else ""
            r.append(f"  {item['name']}{sir_tag}")
            r.append(f"  {SEP2}")
            r.append(f"  WHO AWaRe : {item['aware']}")
            r.append(f"  Class     : {item['class']}")
            r.append(f"  Renal note: {item['renal_note']}")
            r.append(f"  Limit CrCl: Dose adjustment required when CrCl <= {item['renal_limit']} ml/min")
            r.append("")

    if is_preg and preg_warn_items:
        r.append(f"\n{SEP}")
        r.append("  PREGNANCY — USE WITH CAUTION")
        r.append(f"  (Final decision belongs to the treating physician)")
        r.append(SEP)
        for item in preg_warn_items:
            r.append(f"  {item['name']}")
            r.append(f"  {SEP2}")
            for line in item["preg_note"].splitlines():
                r.append(f"  {line}")
            r.append("")

    if banned:
        r.append(f"\n{SEP}")
        r.append("  CONTRAINDICATED / INEFFECTIVE")
        r.append(SEP)
        cat_resist   = [b for b in banned if b["category"] == "resistant"]
        cat_renal    = [b for b in banned if b["category"] == "renal"]
        cat_preg     = [b for b in banned if b["category"] == "pregnancy"]
        cat_child    = [b for b in banned if b["category"] == "child"]
        cat_organism = [b for b in banned if b["category"] == "organism"]
        cat_other    = [b for b in banned if b["category"] == "other"]

        if cat_resist:
            r.append("\n  [A] RESISTANT IN CULTURE:")
            for b in cat_resist: r.append(f"    x {b['name']} — {b['reason_detail']}")
        if cat_renal:
            r.append("\n  [B] CONTRAINDICATED IN RENAL IMPAIRMENT:")
            for b in cat_renal: r.append(f"    x {b['name']} — {b['reason_short']}")
        if cat_preg:
            r.append("\n  [C] CONTRAINDICATED IN PREGNANCY:")
            for b in cat_preg: r.append(f"    x {b['name']} — {b['reason_detail']}")
        if cat_child:
            r.append("\n  [D] NOT SUITABLE FOR CHILDREN:")
            for b in cat_child: r.append(f"    x {b['name']} — {b['reason_short']}")
        if cat_organism:
            r.append(f"\n  [E] INEFFECTIVE FOR {organism}:")
            for b in cat_organism: r.append(f"    x {b['name']} — {b['reason_detail']}")
        if cat_other:
            r.append("\n  [F] OTHER:")
            for b in cat_other: r.append(f"    x {b['name']}")

    r.append(SEP)
    r.append("  DISCLAIMER: هذا التقرير مساعد للقرار الطبي وليس بديلاً عنه.")
    r.append("  Guidelines : EUCAST 2026 | CLSI M100 2026 | IDSA AMR 2025 | Egypt National")
    r.append("  Developed by: Dr. Hussein Ali | Orange Lab")
    return "\n".join(r)

# ==========================================
# 🖥️ Streamlit UI (معدل لاستيعاب العينات الجديدة)
# ==========================================
st.title("🛡️ Orange Culture Analyzer")
st.caption("AI-Assisted Antibiotic Decision Support — Egyptian Market Edition")

uploaded = st.file_uploader("📷 Upload Culture Report Image", type=["jpg","png","jpeg"])

if uploaded:
    cache_key = uploaded.name
    if "ocr_data" not in st.session_state or \
       st.session_state.get("last_file") != cache_key:
        with st.spinner("🔍 Analyzing report image..."):
            p, drugs, sir = extract_all_data(uploaded)
            st.session_state.ocr_data  = (p, drugs, sir)
            st.session_state.last_file = cache_key

    patient, drugs_from_ocr, sir_map = st.session_state.ocr_data

    col1, col2 = st.columns([1, 1.6])

    with col1:
        st.subheader("👤 Patient & Culture")
        culture_type = st.selectbox("🧫 Specimen", SPECIMEN_TYPES,
            index=SPECIMEN_TYPES.index(patient["Specimen"]) if patient["Specimen"] in SPECIMEN_TYPES else 0)
        organism_type = st.selectbox("🦠 Organism", BACTERIA_TYPES,
            index=BACTERIA_TYPES.index(patient["Organism"]) if patient["Organism"] in BACTERIA_TYPES else 0)

        if organism_type in ORGANISM_PROFILE:
            op = ORGANISM_PROFILE[organism_type]
            with st.expander("📌 Organism Guidance", expanded=True):
                st.info(op["note"])
                spec_ctx = op.get("specimen_context", {}).get(culture_type, "")
                if spec_ctx: st.warning(f"**{culture_type} Context:** {spec_ctx}")
                st.write("**First-line:**", ", ".join(op["first_line"]))
                st.write("**Second-line:**", ", ".join(op["second_line"]))
                if op.get("third_line"): st.write("**Third-line:**", ", ".join(op["third_line"]))
                if op["avoid"]: st.error("**Avoid:** " + ", ".join(op["avoid"]))
                if culture_type == "Urine" and op.get("urine_note"): st.info(op["urine_note"])

        st.divider()
        age = st.number_input("Age (years)", value=int(patient["Age"]), min_value=0, max_value=120)
        sex = st.selectbox("Gender", ["Female","Male"], index=0 if patient["Sex"]=="Female" else 1)
        weight = st.number_input("Weight (kg)", min_value=5, max_value=300, value=70)

        st.divider()
        is_renal = st.checkbox("🚩 Renal Impairment")
        cl_cr = 100.0
        if is_renal:
            s_cr = st.number_input("Serum Creatinine (mg/dL)", min_value=0.1, max_value=20.0, value=1.0, step=0.1)
            cl_cr = ((140 - age) * weight) / (72 * s_cr)
            if sex == "Female": cl_cr *= 0.85
            st.metric("CrCl (Cockcroft-Gault)", f"{cl_cr:.1f} ml/min",
                      delta="Mild" if cl_cr>=60 else ("Moderate" if cl_cr>=30 else "Severe"),
                      delta_color="normal" if cl_cr>=60 else ("off" if cl_cr>=30 else "inverse"))

        is_hepatic = st.checkbox("🚩 Hepatic Impairment")
        is_preg = False
        if sex == "Female" and 12 <= age <= 55:
            is_preg = st.checkbox("🤰 Patient is Pregnant")

        current_meds = st.multiselect("💊 Current Medications", COMMON_MEDS)

    with col2:
        st.subheader("💊 Antibiotic Analysis")
        if sir_map:
            st.info("📊 S/I/R: " + " | ".join(f"{k}: **{v}**" for k,v in sir_map.items()))

        final_drugs = st.multiselect("✅ Confirm/Edit Sensitive Antibiotics:",
            options=sorted(ABX_GUIDELINES.keys()),
            default=[d for d in drugs_from_ocr if d in ABX_GUIDELINES])

        allowed, warned, banned = [], [], []
        preg_warn_items = []
        interactions_alerts = []
        organism_avoid = ORGANISM_PROFILE.get(organism_type,{}).get("avoid",[])

        for d in final_drugs:
            info = ABX_GUIDELINES[d]
            d_low = d.lower()

            if sir_map.get(d) == "R":
                banned.append({"name": d, "category": "resistant", "reason_detail": "مقاوم في المزرعة."})
                continue

            for med in current_meds:
                if med in info["interacts_with"]:
                    interactions_alerts.append(f"⚡ تعارض: {d} مع {med}")

            if is_hepatic and info["hepatic_caution"]:
                interactions_alerts.append(f"🏥 تحذير كبدي: {d}")

            # Organism avoid
            d_class = info.get("class","").lower()
            organism_avoided = False
            for av in organism_avoid:
                av_low = av.lower()
                if av_low in d_low or d_low in av_low:
                    organism_avoided = True; break
                if av_low in d_class or any(av_low in cls.lower() for cls in ["cephalosporin","penicillin","macrolide","tetracycline"] if av_low in cls):
                    organism_avoided = True; break
            if organism_avoided:
                banned.append({"name": d, "category": "organism", "reason_detail": f"غير فعال لـ {organism_type}."})
                continue

            if organism_type == "MRSA" and any(c in info["class"] for c in ["Penicillin","Cephalosporin"]):
                banned.append({"name": d, "category": "organism", "reason_detail": "MRSA مقاوم للبيتا-لاكتام."})
                continue

            if is_preg and info["preg_status"] == "Banned":
                banned.append({"name": d, "category": "pregnancy", "reason_short": info["preg_note"]})
                continue
            if is_preg and info["preg_status"] == "Warn":
                preg_warn_items.append({"name": d, **info})

            # Children
            cls = info["class"].lower()
            if age < 18 and not info.get("child_safe", True):
                if "fluoroquinolone" in cls:
                    banned.append({"name": d, "category": "child", "reason_short": "فلوروكينولون < 18 سنة."})
                    continue
                elif "tetracycline" in cls and age < 8:
                    banned.append({"name": d, "category": "child", "reason_short": "تتراسيكلين < 8 سنوات."})
                    continue
                else:
                    banned.append({"name": d, "category": "child", "reason_short": "غير مناسب للأطفال."})
                    continue

            if is_renal and "nitrofurantoin" in d_low and cl_cr < 30:
                banned.append({"name": d, "category": "renal", "reason_short": f"CrCl {cl_cr:.1f} < 30."})
                continue

            if is_renal and info["renal_limit"] > 0 and cl_cr <= info["renal_limit"]:
                warned.append({"name": d, **info})
                continue

            allowed.append({"name": d, **info})

        # واجهة العرض
        non_preg_alerts = [a for a in interactions_alerts if "🤰" not in a]
        if non_preg_alerts:
            st.warning("⚡ Interactions / Warnings")
            for a in sorted(set(non_preg_alerts)): st.write(a)

        if is_preg and preg_warn_items:
            st.markdown("### 🤰 Pregnancy — Use With Caution")
            st.info("الأدوية التالية تحتاج تقييم طبي.")
            for item in preg_warn_items:
                with st.expander(f"⚠️ {item['name']}"):
                    for line in item["preg_note"].splitlines(): st.write(line)

        if banned:
            with st.expander("🚫 Contraindicated / Ineffective", expanded=True):
                for b in banned:
                    cat_label = {"resistant":"مقاوم","renal":"كلوي","pregnancy":"حمل","child":"أطفال","organism":"غير فعال"}.get(b["category"], "")
                    st.error(f"💊 {b['name']} [{cat_label}]")

        if warned:
            with st.expander("🟡 Dose Adjustment Required", expanded=True):
                for item in warned:
                    st.warning(f"**{item['name']}** — {item['renal_note']}")

        if allowed:
            st.success(f"🟢 {len(allowed)} Recommended Option(s)")
            for item in sorted(allowed, key=lambda x: x["priority"]):
                sir_badge = f" [{sir_map.get(item['name'],'?')}]" if sir_map else ""
                with st.expander(f"{item['name']}{sir_badge} — {AWARE_COLORS[item['aware']]}"):
                    col_a, col_b = st.columns(2)
                    col_a.write(f"**Class:** {item['class']}")
                    col_b.write(f"**Route:** {'🟢 PO' if item['high_po'] else '💉 IV'}")
                    st.write(f"**Note:** {item['note']}")
                    spec_note = item.get("specimen_notes", {}).get(culture_type, "")
                    if spec_note: st.info(f"**{culture_type} Note:** {spec_note}")
                    if is_preg and item["preg_status"]=="Warn": st.caption("🤰 " + item["preg_note"].splitlines()[0])
        elif not banned and not warned:
            st.info("اختر المضادات الحساسة من القائمة.")

        if final_drugs:
            st.divider()
            report_txt = generate_report(age, sex, weight, cl_cr, is_renal, is_preg, is_hepatic,
                                         allowed, warned, banned, preg_warn_items,
                                         organism_type, culture_type,
                                         interactions_alerts, sir_map)
            st.download_button("📄 Download Clinical Report", report_txt,
                               file_name=f"Orange_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                               mime="text/plain", use_container_width=True)

st.divider()
st.markdown("""
<div style="text-align:center;color:gray;font-size:0.85rem;">
  <strong>Developed by: Dr. Hussein Ali | Orange Lab</strong><br>
  Compliant with: EUCAST 2026 | CLSI M100 2026 | IDSA AMR 2025 | Egypt National Guidelines
</div>
""", unsafe_allow_html=True)
