# data/antibiotics.py
# © Dr. Hussein Ali — Orange Lab
# قاعدة بيانات المضادات الحيوية + الأسماء التجارية

from __future__ import annotations
import os as _os
import re          # FIX: _normalize_key() calls re.sub() -- was NameError on import
from typing import Dict, Any, List

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


AWARE_COLORS: Dict[str, str] = {
    "Access":  "🟢 Access",
    "Watch":   "🟡 Watch",
    "Reserve": "🔴 Reserve",
}
