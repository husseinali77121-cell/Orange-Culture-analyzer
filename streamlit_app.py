import streamlit as st
import numpy as np
import cv2
import pytesseract
import re
from datetime import datetime

# ==========================================
# 📋 Antibiotics Database - Egyptian Market
# ==========================================
ABX_GUIDELINES = {
    # --- Penicillins ---
    "Amoxicillin + Clavulanic acid": {
        "priority": 1, "class": "Beta-lactamase Inhibitor",
        "note": "✅ خيار قياسي (مثل Augmentin/Curam).",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False,
        "aware": "Access", "high_po": True,
        "preg_safe": True, "child_safe": True,
        "interacts_with": [],
        "aliases": ["augmentin", "curam", "amoxiclav", "co-amoxiclav"],
        "organisms": ["E. coli", "Klebsiella spp.", "Staphylococcus aureus",
                      "Proteus mirabilis", "Streptococcus spp.", "H. influenzae"],
    },
    "Ampicillin/Sulbactam": {
        "priority": 2, "class": "Penicillin",
        "note": "💉 (مثل Unictam/Sigmaclav) فعال للموجبات والسالبات.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False,
        "aware": "Watch", "high_po": False,
        "preg_safe": True, "child_safe": True,
        "interacts_with": [],
        "aliases": ["unictam", "sigmaclav", "unasyn"],
        "organisms": ["E. coli", "Klebsiella spp.", "Staphylococcus aureus",
                      "Proteus mirabilis", "Enterococcus faecalis"],
    },
    "Piperacillin + Tazobactam": {
        "priority": 4, "class": "Anti-pseudomonal Penicillin",
        "note": "🛑 (مثل Tazocin) مضاد احتياطي واسع الطيف جداً.",
        "renal_limit": 20, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False,
        "aware": "Watch", "high_po": False,
        "preg_safe": True, "child_safe": True,
        "interacts_with": [],
        "aliases": ["tazocin", "pip-tazo", "piptaz"],
        "organisms": ["Pseudomonas aeruginosa", "E. coli", "Klebsiella spp.",
                      "Enterococcus faecalis", "Proteus mirabilis"],
    },

    # --- Cephalosporins ---
    "Cephalexin": {
        "priority": 1, "class": "1st Gen Cephalosporin",
        "note": "✅ (مثل Ceporex) آمن للالتهابات البسيطة والجلد.",
        "renal_limit": 40, "renal_note": "⚖️ مباعدة الجرعات مطلوب.",
        "hepatic_caution": False,
        "aware": "Access", "high_po": True,
        "preg_safe": True, "child_safe": True,
        "interacts_with": [],
        "aliases": ["ceporex", "keflex"],
        "organisms": ["Staphylococcus aureus", "Streptococcus spp.", "E. coli",
                      "Proteus mirabilis"],
    },
    "Cefadroxil": {
        "priority": 1, "class": "1st Gen Cephalosporin",
        "note": "✅ (مثل Duricef) فعال لالتهابات الحلق والجلد.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False,
        "aware": "Access", "high_po": True,
        "preg_safe": True, "child_safe": True,
        "interacts_with": [],
        "aliases": ["duricef"],
        "organisms": ["Staphylococcus aureus", "Streptococcus spp."],
    },
    "Cefaclor": {
        "priority": 2, "class": "2nd Gen Cephalosporin",
        "note": "✅ (مثل Ceclor) فعال للأذن الوسطى والمسالك.",
        "renal_limit": 10, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False,
        "aware": "Watch", "high_po": True,
        "preg_safe": True, "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["ceclor"],
        "organisms": ["E. coli", "H. influenzae", "Staphylococcus aureus",
                      "Streptococcus spp.", "Klebsiella spp."],
    },
    "Cefuroxime": {
        "priority": 2, "class": "2nd Gen Cephalosporin",
        "note": "✅ (مثل Zinnat) واسع المدى للجهاز التنفسي والمسالك.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False,
        "aware": "Watch", "high_po": True,
        "preg_safe": True, "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["zinnat", "ceftin"],
        "organisms": ["E. coli", "Klebsiella spp.", "H. influenzae",
                      "Staphylococcus aureus", "Streptococcus spp.", "Proteus mirabilis"],
    },
    "Ceftriaxone": {
        "priority": 3, "class": "3rd Gen Cephalosporin",
        "note": "⚠️ (مثل Rocephin) حقن فقط؛ لا يستخدم في الحالات البسيطة.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً (إطراح كبدي أساساً).",
        "hepatic_caution": True,
        "aware": "Watch", "high_po": False,
        "preg_safe": True, "child_safe": True,
        "interacts_with": [],
        "aliases": ["rocephin", "cefaxone", "triaxone"],
        "organisms": ["E. coli", "Klebsiella spp.", "Proteus mirabilis",
                      "Staphylococcus aureus", "Streptococcus spp.", "H. influenzae",
                      "Enterococcus faecalis"],
    },
    "Cefixime": {
        "priority": 2, "class": "3rd Gen Cephalosporin (Oral)",
        "note": "✅ (مثل Suprax) خيار فموي قوي للمسالك.",
        "renal_limit": 20, "renal_note": "⚖️ خفض الجرعة مطلوب.",
        "hepatic_caution": False,
        "aware": "Watch", "high_po": True,
        "preg_safe": True, "child_safe": True,
        "interacts_with": [],
        "aliases": ["suprax", "oroken"],
        "organisms": ["E. coli", "Klebsiella spp.", "Proteus mirabilis",
                      "H. influenzae", "Streptococcus spp."],
    },
    "Cefotaxime": {
        "priority": 3, "class": "3rd Gen Cephalosporin",
        "note": "💉 (مثل Cefotax) يستخدم في العدوى الشديدة.",
        "renal_limit": 20, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False,
        "aware": "Watch", "high_po": False,
        "preg_safe": True, "child_safe": True,
        "interacts_with": [],
        "aliases": ["cefotax", "claforan"],
        "organisms": ["E. coli", "Klebsiella spp.", "Proteus mirabilis",
                      "Streptococcus spp.", "H. influenzae"],
    },
    "Ceftazidime": {
        "priority": 4, "class": "3rd Gen Cephalosporin (Anti-pseudomonal)",
        "note": "🛑 (مثل Fortum) متخصص في جراثيم Pseudomonas.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري جداً.",
        "hepatic_caution": False,
        "aware": "Watch", "high_po": False,
        "preg_safe": True, "child_safe": True,
        "interacts_with": [],
        "aliases": ["fortum", "ceptaz"],
        "organisms": ["Pseudomonas aeruginosa", "E. coli", "Klebsiella spp.",
                      "Proteus mirabilis"],
    },
    "Cefoperazone": {
        "priority": 4, "class": "3rd Gen Cephalosporin",
        "note": "💉 (مثل Cefobid) فعال للمسالك والمرارة، يطرح كبدياً.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً؛ يطرح عبر الصفراء.",
        "hepatic_caution": True,
        "aware": "Watch", "high_po": False,
        "preg_safe": True, "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["cefobid"],
        "organisms": ["Pseudomonas aeruginosa", "E. coli", "Klebsiella spp.",
                      "Proteus mirabilis", "Staphylococcus aureus"],
    },
    "Cefepime": {
        "priority": 5, "class": "4th Gen Cephalosporin",
        "note": "🛑 (مثل Maxipime) مضاد قوي جداً للحالات الحرجة.",
        "renal_limit": 50, "renal_note": "⚠️ يتطلب تعديل جرعة دقيق لتجنب السمية العصبية.",
        "hepatic_caution": False,
        "aware": "Watch", "high_po": False,
        "preg_safe": True, "child_safe": True,
        "interacts_with": [],
        "aliases": ["maxipime"],
        "organisms": ["Pseudomonas aeruginosa", "E. coli", "Klebsiella spp.",
                      "Proteus mirabilis", "Staphylococcus aureus", "Enterococcus faecalis"],
    },

    # --- Fluoroquinolones ---
    "Ciprofloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": "⚠️ (مثل Ciprofar) يفضل ادخاره للمسالك المعقدة.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True,
        "aware": "Watch", "high_po": True,
        "preg_safe": False, "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)", "Warfarin (مضادات التخثر)"],
        "aliases": ["ciprofar", "cipro", "ciproflox"],
        "organisms": ["E. coli", "Klebsiella spp.", "Pseudomonas aeruginosa",
                      "Proteus mirabilis", "Staphylococcus aureus"],
    },
    "Levofloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": "⚠️ (مثل Tavanic) فعال جداً للصدر والمسالك.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True,
        "aware": "Watch", "high_po": True,
        "preg_safe": False, "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["tavanic", "levaquin", "levoflox"],
        "organisms": ["E. coli", "Klebsiella spp.", "Pseudomonas aeruginosa",
                      "Staphylococcus aureus", "Streptococcus spp.", "H. influenzae"],
    },
    "Ofloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": "⚠️ (مثل Tarivid) واسع المدى.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True,
        "aware": "Watch", "high_po": True,
        "preg_safe": False, "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["tarivid", "oflox"],
        "organisms": ["E. coli", "Klebsiella spp.", "Staphylococcus aureus",
                      "Proteus mirabilis"],
    },

    # --- Urinary Antiseptics ---
    "Nitrofurantoin": {
        "priority": 1, "class": "Urinary Antiseptic",
        "note": "🎯 (مثل Macrofuran) الخيار الأول للمسالك البسيطة فقط.",
        "renal_limit": 30, "renal_note": "🚫 ممنوع إذا كانت التصفية < 30 مل/د.",
        "hepatic_caution": False,
        "aware": "Access", "high_po": True,
        "preg_safe": False, "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["macrofuran", "macrobid", "nitrofur"],
        "organisms": ["E. coli", "Staphylococcus aureus", "Enterococcus faecalis",
                      "Klebsiella spp."],
    },
    "Fosfomycin": {
        "priority": 1, "class": "Phosphonic Acid",
        "note": "🎯 (مثل Monuril) خيار مثالي بجرعة واحدة للمسالك.",
        "renal_limit": 10, "renal_note": "⚠️ حذر في القصور الشديد.",
        "hepatic_caution": False,
        "aware": "Access", "high_po": True,
        "preg_safe": False, "child_safe": False,
        "interacts_with": [],
        "aliases": ["monuril", "fosfocin"],
        "organisms": ["E. coli", "Enterococcus faecalis", "Staphylococcus aureus",
                      "Klebsiella spp."],
    },

    # --- Aminoglycosides ---
    "Gentamicin": {
        "priority": 4, "class": "Aminoglycoside",
        "note": "💉 (مثل Garamycin) يستخدم بحذر شديد - سام للكلى والأذن.",
        "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى ضرورية.",
        "hepatic_caution": False,
        "aware": "Access", "high_po": False,
        "preg_safe": False, "child_safe": True,
        "interacts_with": ["NSAIDs (مسكنات الألم)"],
        "aliases": ["garamycin", "genta"],
        "organisms": ["E. coli", "Klebsiella spp.", "Pseudomonas aeruginosa",
                      "Proteus mirabilis", "Staphylococcus aureus"],
    },
    "Amikacin": {
        "priority": 4, "class": "Aminoglycoside",
        "note": "💉 (مثل Amikin) فعال جداً ضد السالبات المقاومة.",
        "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى.",
        "hepatic_caution": False,
        "aware": "Watch", "high_po": False,
        "preg_safe": False, "child_safe": True,
        "interacts_with": ["NSAIDs (مسكنات الألم)"],
        "aliases": ["amikin", "amikacin"],
        "organisms": ["E. coli", "Klebsiella spp.", "Pseudomonas aeruginosa",
                      "Proteus mirabilis", "Staphylococcus aureus"],
    },

    # --- Macrolides ---
    "Azithromycin": {
        "priority": 2, "class": "Macrolide",
        "note": "✅ (مثل Zithrokan) فعال للجهاز التنفسي والكلاميديا.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True,
        "aware": "Watch", "high_po": True,
        "preg_safe": True, "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["zithrokan", "zithromax", "azithro"],
        "organisms": ["Staphylococcus aureus", "Streptococcus spp.", "H. influenzae",
                      "Chlamydia spp.", "Mycoplasma spp."],
    },
    "Clarithromycin": {
        "priority": 2, "class": "Macrolide",
        "note": "✅ (مثل Klacid) فعال لجرثومة المعدة والصدر.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True,
        "aware": "Watch", "high_po": True,
        "preg_safe": False, "child_safe": True,
        "interacts_with": [],
        "aliases": ["klacid", "biaxin"],
        "organisms": ["Staphylococcus aureus", "Streptococcus spp.",
                      "H. pylori", "H. influenzae", "Mycoplasma spp."],
    },

    # --- Sulfonamides ---
    "Trimethoprim/Sulfamethoxazole": {
        "priority": 2, "class": "Sulfonamide",
        "note": "✅ (مثل Septra/Sutrim) فعال للمسالك والجهاز التنفسي.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False,
        "aware": "Access", "high_po": True,
        "preg_safe": False, "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["septra", "sutrim", "bactrim", "co-trimoxazole", "tmp-smx"],
        "organisms": ["E. coli", "Klebsiella spp.", "Proteus mirabilis",
                      "Staphylococcus aureus", "Streptococcus spp."],
    },

    # --- Nitroimidazoles ---
    "Metronidazole": {
        "priority": 1, "class": "Nitroimidazole",
        "note": "✅ (مثل Flagyl) الخيار الأول للأنيروبيك والطفيليات.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True,
        "aware": "Access", "high_po": True,
        "preg_safe": False, "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["flagyl", "metro", "metrogyl"],
        "organisms": ["Anaerobes (لاهوائيات)", "Trichomonas vaginalis",
                      "H. pylori", "C. difficile", "Bacteroides spp."],
    },
    "Tinidazole": {
        "priority": 2, "class": "Nitroimidazole",
        "note": "✅ (مثل Fasigyn) بديل Metronidazole بجرعة أقل تكراراً.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True,
        "aware": "Access", "high_po": True,
        "preg_safe": False, "child_safe": False,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["fasigyn", "tini"],
        "organisms": ["Anaerobes (لاهوائيات)", "Trichomonas vaginalis",
                      "H. pylori", "Giardia lamblia"],
    },

    # --- Tetracyclines ---
    "Doxycycline": {
        "priority": 2, "class": "Tetracycline",
        "note": "✅ (مثل Vibramycin) فعال للكلاميديا والمايكوبلازما.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً نسبياً.",
        "hepatic_caution": True,
        "aware": "Watch", "high_po": True,
        "preg_safe": False, "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["vibramycin", "doxy"],
        "organisms": ["Chlamydia spp.", "Mycoplasma spp.", "Staphylococcus aureus",
                      "H. influenzae", "Rickettsia spp."],
    },

    # --- Last Resort ---
    "Vancomycin": {
        "priority": 5, "class": "Glycopeptide",
        "note": "🛑 خاص بـ MRSA والحالات الحرجة - مراقبة الـ Trough.",
        "renal_limit": 50, "renal_note": "⚖️ مراقبة مستوى الدواء في الدم.",
        "hepatic_caution": False,
        "aware": "Watch", "high_po": False,
        "preg_safe": False, "child_safe": True,
        "interacts_with": ["NSAIDs (مسكنات الألم)"],
        "aliases": ["vancocin", "vanco"],
        "organisms": ["MRSA", "Staphylococcus aureus", "Enterococcus faecalis",
                      "Streptococcus spp.", "C. difficile"],
    },
    "Meropenem": {
        "priority": 5, "class": "Carbapenem",
        "note": "🛑 (مثل Meronem) مضاد الملاذ الأخير للمقاومة.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False,
        "aware": "Watch", "high_po": False,
        "preg_safe": True, "child_safe": True,
        "interacts_with": [],
        "aliases": ["meronem", "merrem"],
        "organisms": ["Pseudomonas aeruginosa", "Klebsiella spp.", "E. coli",
                      "Enterococcus faecalis", "Staphylococcus aureus", "MRSA"],
    },
    "Linezolid": {
        "priority": 5, "class": "Oxazolidinone",
        "note": "🛑 (مثل Averozolid) للموجبات المقاومة (MRSA/VRE) فقط.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": False,
        "aware": "Reserve", "high_po": True,
        "preg_safe": False, "child_safe": True,
        "interacts_with": ["SSRI (أدوية الاكتئاب)"],
        "aliases": ["averozolid", "zyvox"],
        "organisms": ["MRSA", "Staphylococcus aureus", "Enterococcus faecalis",
                      "VRE", "Streptococcus spp."],
    },
}

# ==========================================
# 🦠 Organism → First-line & Avoid mapping
# ==========================================
ORGANISM_PROFILE = {
    "E. coli": {
        "first_line": ["Nitrofurantoin", "Fosfomycin", "Trimethoprim/Sulfamethoxazole",
                       "Amoxicillin + Clavulanic acid"],
        "second_line": ["Cefuroxime", "Cefixime", "Ciprofloxacin"],
        "avoid": [],
        "note": "🔬 الأكثر شيوعاً في مزارع البول.",
    },
    "Klebsiella spp.": {
        "first_line": ["Amoxicillin + Clavulanic acid", "Cefuroxime", "Cefixime"],
        "second_line": ["Piperacillin + Tazobactam", "Ceftriaxone", "Meropenem"],
        "avoid": ["Ampicillin"],
        "note": "🔬 مقاومة لبعض البيتا-لاكتام بطبيعتها.",
    },
    "Pseudomonas aeruginosa": {
        "first_line": ["Piperacillin + Tazobactam", "Ceftazidime", "Ciprofloxacin"],
        "second_line": ["Cefepime", "Meropenem", "Amikacin"],
        "avoid": ["Nitrofurantoin", "Fosfomycin", "Trimethoprim/Sulfamethoxazole",
                  "Cephalexin", "Cefadroxil", "Cefaclor"],
        "note": "🔬 جرثومة انتهازية تحتاج مضادات متخصصة.",
    },
    "Staphylococcus aureus": {
        "first_line": ["Cephalexin", "Cefadroxil", "Amoxicillin + Clavulanic acid"],
        "second_line": ["Azithromycin", "Clarithromycin", "Doxycycline"],
        "avoid": [],
        "note": "🔬 تحقق من MRSA - قد يحتاج Vancomycin.",
    },
    "MRSA": {
        "first_line": ["Vancomycin", "Linezolid"],
        "second_line": ["Trimethoprim/Sulfamethoxazole", "Doxycycline"],
        "avoid": ["Cephalexin", "Cefadroxil", "Cefaclor", "Cefuroxime", "Ceftriaxone",
                  "Amoxicillin + Clavulanic acid", "Ampicillin/Sulbactam",
                  "Piperacillin + Tazobactam"],
        "note": "🔴 مقاوم لجميع البيتا-لاكتام!",
    },
    "Proteus mirabilis": {
        "first_line": ["Amoxicillin + Clavulanic acid", "Cefuroxime", "Cefixime"],
        "second_line": ["Ciprofloxacin", "Trimethoprim/Sulfamethoxazole"],
        "avoid": ["Nitrofurantoin", "Tetracyclines"],
        "note": "🔬 مقاوم طبيعياً لـ Nitrofurantoin.",
    },
    "Enterococcus faecalis": {
        "first_line": ["Amoxicillin + Clavulanic acid", "Fosfomycin", "Nitrofurantoin"],
        "second_line": ["Ampicillin/Sulbactam", "Vancomycin", "Linezolid"],
        "avoid": ["Cephalosporins (كل الجيل)", "Trimethoprim/Sulfamethoxazole"],
        "note": "🔬 مقاوم طبيعياً لجميع السيفالوسبورين.",
    },
}

SPECIMEN_TYPES = ["Urine", "Blood", "Sputum", "Wound Swab", "Pus", "Stool", "CSF"]
BACTERIA_TYPES = list(ORGANISM_PROFILE.keys())
COMMON_MEDS = ["Antacids (مضادات الحموضة)", "Warfarin (مضادات التخثر)",
               "NSAIDs (مسكنات الألم)", "SSRI (أدوية الاكتئاب)"]
AWARE_COLORS = {"Access": "🟢 Access", "Watch": "🟡 Watch", "Reserve": "🔴 Reserve"}

# ==========================================
# 🔍 OCR with Fuzzy-like Matching
# ==========================================
def fuzzy_match(word, target, threshold=80):
    """Simple character overlap scoring (no external lib needed)."""
    w, t = word.lower(), target.lower()
    if t in w or w in t:
        return 100
    matches = sum(c in t for c in w)
    score = (matches / max(len(w), len(t))) * 100
    return score


def extract_all_data(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    full_text = pytesseract.image_to_string(thresh, config='--psm 6')
    text_lower = full_text.lower()

    # --- Age ---
    age_match = re.search(r"(\d+)\s*[Yy]ears?", full_text)
    detected_age = age_match.group(1) if age_match else "25"

    # --- Sex ---
    detected_sex = "Female" if "female" in text_lower else "Male"

    # --- Specimen ---
    detected_specimen = "Urine"
    for s in SPECIMEN_TYPES:
        if s.lower() in text_lower:
            detected_specimen = s
            break

    # --- Organism ---
    detected_organism = "E. coli"
    for b in BACTERIA_TYPES:
        if b.lower() in text_lower:
            detected_organism = b
            break

    # --- S/I/R Extraction ---
    sir_map = {}
    # Look for patterns like "Ciprofloxacin ... S" or "S Ciprofloxacin"
    lines = full_text.splitlines()
    for line in lines:
        line_lower = line.lower().strip()
        result = None
        if re.search(r'\b(s|sensitive|sens)\b', line_lower):
            result = "S"
        elif re.search(r'\b(r|resistant|resist)\b', line_lower):
            result = "R"
        elif re.search(r'\b(i|intermediate|inter)\b', line_lower):
            result = "I"

        if result:
            for abx_name, info in ABX_GUIDELINES.items():
                all_names = [abx_name] + info["aliases"]
                for name in all_names:
                    if fuzzy_match(name, line_lower) >= 75:
                        sir_map[abx_name] = result
                        break

    # --- Sensitive Drugs Detection ---
    start_pos = text_lower.find("highly")
    if start_pos == -1:
        start_pos = text_lower.find("sensitive")
    end_pos = text_lower.find("resistant")
    search_area = full_text[start_pos:end_pos] if (start_pos != -1 and end_pos != -1) else full_text
    words_in_area = search_area.lower().split()

    detected_drugs = []
    for abx_name, info in ABX_GUIDELINES.items():
        all_names = [abx_name] + info["aliases"]
        matched = False
        for name in all_names:
            name_words = name.lower().split()
            for word in words_in_area:
                if any(fuzzy_match(word, nw) >= 82 for nw in name_words):
                    matched = True
                    break
            if matched:
                break
        if matched:
            detected_drugs.append(abx_name)

    return (
        {"Age": detected_age, "Sex": detected_sex,
         "Specimen": detected_specimen, "Organism": detected_organism},
        list(set(detected_drugs)),
        sir_map,
    )


# ==========================================
# 📄 Report Generator
# ==========================================
def generate_report(age, sex, weight, cl_cr, is_renal, is_preg, is_hepatic,
                    allowed_drugs, warned_drugs, banned_drugs,
                    organism, specimen, interactions, sir_map, organism_notes):
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    r = []
    r.append("==========================================")
    r.append(" 🛡️ ORANGE LAB - CLINICAL DECISION REPORT")
    r.append("==========================================")
    r.append(f"Date: {date_str}\n")

    r.append("👤 PATIENT DETAILS:")
    r.append(f"- Age: {age} yrs | Gender: {sex} | Weight: {weight} kg")
    r.append(f"- Renal: {'🚩 IMPAIRED (CrCl ' + f'{cl_cr:.1f} ml/min)' if is_renal else '🟢 Normal'}")
    r.append(f"- Hepatic: {'🚩 IMPAIRED' if is_hepatic else '🟢 Normal'}")
    if sex == "Female":
        r.append(f"- Pregnancy: {'🤰 PREGNANT' if is_preg else '🟢 Not pregnant'}")

    r.append(f"\n🧫 CULTURE:")
    r.append(f"- Specimen: {specimen} | Organism: {organism}")
    if organism in ORGANISM_PROFILE:
        r.append(f"- Note: {ORGANISM_PROFILE[organism]['note']}")

    if sir_map:
        r.append("\n📊 SENSITIVITY:")
        for drug, res in sir_map.items():
            r.append(f"  {drug}: {res}")

    if interactions:
        r.append("\n⚡ INTERACTIONS:")
        for i in interactions:
            r.append(f"  {i}")

    r.append("\n🟢 RECOMMENDED:")
    for item in allowed_drugs:
        sir_label = f" [{sir_map.get(item['name'], '?')}]" if sir_map else ""
        r.append(f"  - {item['name']}{sir_label} ({AWARE_COLORS[item['aware']]})")
        r.append(f"    {item['note']}")

    if warned_drugs:
        r.append("\n🟡 DOSE ADJUSTMENT REQUIRED:")
        for item in warned_drugs:
            r.append(f"  - {item['name']}: {item['renal_note']}")

    if banned_drugs:
        r.append("\n🔴 CONTRAINDICATED:")
        for b in banned_drugs:
            r.append(f"  - {b}")

    r.append("\n==========================================")
    r.append("Developed by: Dr. Hussein Ali | Orange Lab")
    return "\n".join(r)


# ==========================================
# 🖥️ Streamlit Interface
# ==========================================
st.set_page_config(page_title="Orange Culture Analyzer", layout="wide",
                   page_icon="🛡️")

st.markdown("""
    <style>
    .block-container {padding-top: 1rem;}
    h1 {color: #e87722;}
    </style>
""", unsafe_allow_html=True)

st.title("🛡️ Orange Culture Analyzer")
st.caption("AI-Assisted Antibiotic Decision Support — Egyptian Market Edition")

uploaded = st.file_uploader("📷 Upload Culture Report Image", type=["jpg", "png", "jpeg"])

if uploaded:
    if "ocr_data" not in st.session_state or st.session_state.get("last_file") != uploaded.name:
        with st.spinner("🔍 Analyzing report image..."):
            patient_init, drugs_init, sir_init = extract_all_data(uploaded)
            st.session_state.ocr_data = (patient_init, drugs_init, sir_init)
            st.session_state.last_file = uploaded.name

    patient, drugs_from_ocr, sir_map = st.session_state.ocr_data

    col1, col2 = st.columns([1, 1.6])

    # ──────────────────────────────────────────────────────
    with col1:
        st.subheader("👤 Patient & Culture Details")

        culture_type = st.selectbox(
            "🧫 Specimen", SPECIMEN_TYPES,
            index=SPECIMEN_TYPES.index(patient["Specimen"])
            if patient["Specimen"] in SPECIMEN_TYPES else 0,
        )
        organism_type = st.selectbox(
            "🦠 Organism", BACTERIA_TYPES,
            index=BACTERIA_TYPES.index(patient["Organism"])
            if patient["Organism"] in BACTERIA_TYPES else 0,
        )

        # Organism guidance card
        if organism_type in ORGANISM_PROFILE:
            op = ORGANISM_PROFILE[organism_type]
            with st.expander("📌 Organism Guidance", expanded=True):
                st.info(op["note"])
                st.write("**First-line:**", ", ".join(op["first_line"]))
                st.write("**Second-line:**", ", ".join(op["second_line"]))
                if op["avoid"]:
                    st.error("**Avoid:** " + ", ".join(op["avoid"]))

        st.divider()
        age = st.number_input("Age (years)", value=int(patient["Age"]), min_value=0, max_value=120)
        sex = st.selectbox("Gender", ["Female", "Male"],
                           index=0 if patient["Sex"] == "Female" else 1)
        weight = st.number_input("Weight (kg)", min_value=5, max_value=300, value=70)

        st.divider()
        is_renal = st.checkbox("🚩 Renal Impairment")
        cl_cr = 100.0
        if is_renal:
            s_creat = st.number_input("Serum Creatinine (mg/dL)",
                                      min_value=0.1, max_value=20.0, value=1.0, step=0.1)
            cl_cr = ((140 - age) * weight) / (72 * s_creat)
            if sex == "Female":
                cl_cr *= 0.85
            color = "normal" if cl_cr >= 60 else ("off" if cl_cr >= 30 else "inverse")
            st.metric("Estimated CrCl (Cockcroft-Gault)", f"{cl_cr:.1f} ml/min",
                      delta=("Mild" if cl_cr >= 60 else ("Moderate" if cl_cr >= 30 else "Severe")),
                      delta_color=color)

        is_hepatic = st.checkbox("🚩 Hepatic Impairment")

        is_preg = False
        if sex == "Female" and 12 <= age <= 55:
            is_preg = st.checkbox("🤰 Patient is Pregnant")

        current_meds = st.multiselect("💊 Current Medications", COMMON_MEDS)

    # ──────────────────────────────────────────────────────
    with col2:
        st.subheader("💊 Antibiotic Analysis")

        if sir_map:
            st.info(f"📊 S/I/R detected from image: "
                    + " | ".join(f"{k}: **{v}**" for k, v in sir_map.items()))

        default_drugs = [d for d in drugs_from_ocr if d in ABX_GUIDELINES]
        final_drugs = st.multiselect(
            "✅ Confirm/Edit Sensitive Antibiotics:",
            options=sorted(list(ABX_GUIDELINES.keys())),
            default=default_drugs,
        )

        allowed, warned, banned, interactions_alerts = [], [], [], []
        organism_avoid = ORGANISM_PROFILE.get(organism_type, {}).get("avoid", [])

        for d in final_drugs:
            info = ABX_GUIDELINES[d]
            d_low = d.lower()

            # S/I/R filter — skip Resistant
            if sir_map.get(d) == "R":
                banned.append(f"💊 {d}: مقاوم (R) في نتيجة المزرعة.")
                continue

            # Interaction check
            for med in current_meds:
                if med in info["interacts_with"]:
                    interactions_alerts.append(f"⚡ تعارض: {d} مع {med}")

            # Organism-specific avoid list
            if any(avoid_term.lower() in d_low or d_low in avoid_term.lower()
                   for avoid_term in organism_avoid):
                banned.append(f"💊 {d}: غير فعال لـ {organism_type} طبيعياً.")
                continue

            # MRSA / Pseudomonas hard rules
            if organism_type == "MRSA":
                beta_lactam_classes = ["Penicillin", "Cephalosporin", "Carbapenem"]
                if any(c in info["class"] for c in beta_lactam_classes) \
                        and d not in ["Meropenem"]:
                    banned.append(f"💊 {d}: بيتا-لاكتام - لا يعمل على MRSA.")
                    continue

            # Pregnancy
            if is_preg and not info["preg_safe"]:
                banned.append(f"💊 {d}: غير آمن أثناء الحمل.")
                continue

            # Child (<18) — Fluoroquinolones & Tetracyclines
            if age < 18 and not info["child_safe"]:
                banned.append(f"💊 {d}: غير مناسب لمن هم دون 18 سنة.")
                continue

            # Renal — Nitrofurantoin hard cutoff
            if is_renal and "nitrofurantoin" in d_low and cl_cr < 30:
                banned.append(f"💊 {d}: ممنوع — CrCl < 30 مل/د.")
                continue

            # Renal — dose adjustment needed
            if is_renal and info["renal_limit"] > 0 and cl_cr <= info["renal_limit"]:
                warned.append({"name": d, **info})
                continue

            # Hepatic
            if is_hepatic and info["hepatic_caution"]:
                interactions_alerts.append(f"🏥 تحذير كبدي: {d} — يحتاج متابعة وظائف الكبد.")

            allowed.append({"name": d, **info})

        # ---- Display Results ----
        if interactions_alerts:
            st.warning("⚡ Interactions / Warnings Detected")
            for a in sorted(set(interactions_alerts)):
                st.write(a)

        if banned:
            with st.expander("🚫 Contraindicated / Ineffective", expanded=True):
                for b in banned:
                    st.error(b)

        if warned:
            with st.expander("🟡 Dose Adjustment Required", expanded=True):
                for item in warned:
                    sir_label = f" [{sir_map.get(item['name'], '')}]" if sir_map else ""
                    st.warning(f"**{item['name']}{sir_label}** — {item['renal_note']}")

        if allowed:
            st.success(f"🟢 {len(allowed)} Recommended Option(s)")
            for item in sorted(allowed, key=lambda x: x["priority"]):
                sir_badge = f" 🔬 [{sir_map.get(item['name'], '?')}]" if sir_map else ""
                with st.expander(
                    f"{item['name']}{sir_badge} — {AWARE_COLORS[item['aware']]}"
                ):
                    cols = st.columns(2)
                    cols[0].write(f"**Class:** {item['class']}")
                    cols[1].write(f"**Route:** {'🟢 PO (فموي)' if item['high_po'] else '💉 IV فقط'}")
                    st.write(f"**Note:** {item['note']}")
                    if item["renal_note"] != "🟢 آمن كلوياً.":
                        st.caption(f"🫘 Renal: {item['renal_note']}")
        elif not banned and not warned:
            st.info("اختر المضادات الحساسة من القائمة أعلاه.")

        # ---- Download ----
        if final_drugs:
            st.divider()
            full_report = generate_report(
                age, sex, weight, cl_cr, is_renal, is_preg, is_hepatic,
                allowed, warned, banned, organism_type, culture_type,
                interactions_alerts, sir_map,
                ORGANISM_PROFILE.get(organism_type, {}),
            )
            st.download_button(
                "📄 Download Clinical Report",
                full_report,
                file_name=f"Orange_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True,
            )

st.divider()
st.markdown("""
<div style="text-align:center; color:gray; font-size:0.85rem;">
    <strong>Developed by: Dr. Hussein Ali | Orange Lab</strong><br>
    WHO AWaRe Classification:&nbsp;
    🟢 <b>Access</b> (First choice) |
    🟡 <b>Watch</b> (Use with caution) |
    🔴 <b>Reserve</b> (Last resort)
</div>
""", unsafe_allow_html=True)
