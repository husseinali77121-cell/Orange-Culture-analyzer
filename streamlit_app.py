import streamlit as st
import numpy as np
import cv2
import pytesseract
import re
from datetime import datetime

# ==========================================
# 📋 Antibiotics Database - Egyptian Market
# preg_status: "Safe" | "Warn" | "Banned"
# preg_note  : سبب التحذير أو الحظر
# ==========================================
ABX_GUIDELINES = {

    # ── Penicillins ────────────────────────────────────────────
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
                      "Proteus mirabilis","Streptococcus spp.","H. influenzae"],
    },
    "Ampicillin/Sulbactam": {
        "priority": 2, "class": "Penicillin",
        "note": "💉 (مثل Unictam/Sigmaclav) فعال للموجبات والسالبات.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["unictam","sigmaclav","unasyn"],
        "organisms": ["E. coli","Klebsiella spp.","Staphylococcus aureus",
                      "Proteus mirabilis","Enterococcus faecalis"],
    },
    "Piperacillin + Tazobactam": {
        "priority": 4, "class": "Anti-pseudomonal Penicillin",
        "note": "🛑 (مثل Tazocin) مضاد احتياطي واسع الطيف جداً.",
        "renal_limit": 20, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["tazocin","pip-tazo","piptaz"],
        "organisms": ["Pseudomonas aeruginosa","E. coli","Klebsiella spp.",
                      "Enterococcus faecalis","Proteus mirabilis"],
    },

    # ── Cephalosporins ─────────────────────────────────────────
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
                      "Streptococcus spp.","Klebsiella spp."],
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
                      "Staphylococcus aureus","Streptococcus spp.","Proteus mirabilis"],
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
                      "Staphylococcus aureus","Streptococcus spp.","H. influenzae"],
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
                      "Streptococcus spp.","H. influenzae"],
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
                      "Proteus mirabilis","Staphylococcus aureus","Enterococcus faecalis"],
    },

    # ── Fluoroquinolones ───────────────────────────────────────
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
                      "Staphylococcus aureus","Streptococcus spp.","H. influenzae"],
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
        "aliases": ["noroxin","norflox","norfloxacin"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "Staphylococcus aureus","Enterococcus faecalis"],
    },

    # ── Urinary Antiseptics ────────────────────────────────────
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
                      "Enterococcus faecalis","Klebsiella spp."],
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
    },

    # ── Aminoglycosides ────────────────────────────────────────
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
                      "Proteus mirabilis","Staphylococcus aureus"],
    },

    # ── Macrolides ─────────────────────────────────────────────
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
                      "H. influenzae","Chlamydia spp.","Mycoplasma spp."],
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
                      "H. pylori","H. influenzae","Mycoplasma spp."],
    },

    # ── Sulfonamides ───────────────────────────────────────────
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
                      "Staphylococcus aureus","Streptococcus spp."],
    },

    # ── Nitroimidazoles ────────────────────────────────────────
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
                      "H. pylori","C. difficile","Bacteroides spp."],
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
    },

    # ── Tetracyclines ──────────────────────────────────────────
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
                      "Staphylococcus aureus","H. influenzae","Rickettsia spp."],
    },

    # ── Cefuroxime Sodium (IV form) ───────────────────────────
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
    },

    # ── Carbapenems ────────────────────────────────────────────
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
    },

    # ── Last Resort ────────────────────────────────────────────
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
                      "Streptococcus spp.","C. difficile"],
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
                      "Enterococcus faecalis","Staphylococcus aureus","MRSA"],
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
                      "VRE","Streptococcus spp."],
    },
}

# ==========================================
# 🦠 Organism → First-line / Avoid mapping
# ==========================================
ORGANISM_PROFILE = {
    "E. coli": {
        "first_line": ["Nitrofurantoin","Fosfomycin",
                       "Trimethoprim/Sulfamethoxazole","Amoxicillin + Clavulanic acid"],
        "second_line": ["Cefuroxime","Cefixime","Ciprofloxacin"],
        "avoid": [],
        "note": "🔬 الأكثر شيوعاً في مزارع البول.",
    },
    "Klebsiella spp.": {
        "first_line": ["Amoxicillin + Clavulanic acid","Cefuroxime","Cefixime","Cefuroxime sodium"],
        "second_line": ["Piperacillin + Tazobactam","Ceftriaxone","Meropenem","Norfloxacin","Ertapenem"],
        "avoid": ["Ampicillin"],
        "note": "🔬 مقاومة لبعض البيتا-لاكتام بطبيعتها.",
    },
    "Pseudomonas aeruginosa": {
        "first_line": ["Piperacillin + Tazobactam","Ceftazidime","Ciprofloxacin"],
        "second_line": ["Cefepime","Meropenem","Amikacin"],
        "avoid": ["Nitrofurantoin","Fosfomycin","Trimethoprim/Sulfamethoxazole",
                  "Cephalexin","Cefadroxil","Cefaclor"],
        "note": "🔬 جرثومة انتهازية تحتاج مضادات متخصصة.",
    },
    "Staphylococcus aureus": {
        "first_line": ["Cephalexin","Cefadroxil","Amoxicillin + Clavulanic acid"],
        "second_line": ["Azithromycin","Clarithromycin","Doxycycline"],
        "avoid": [],
        "note": "🔬 تحقق من MRSA - قد يحتاج Vancomycin.",
    },
    "MRSA": {
        "first_line": ["Vancomycin","Linezolid"],
        "second_line": ["Trimethoprim/Sulfamethoxazole","Doxycycline"],
        "avoid": ["Cephalexin","Cefadroxil","Cefaclor","Cefuroxime","Ceftriaxone",
                  "Amoxicillin + Clavulanic acid","Ampicillin/Sulbactam",
                  "Piperacillin + Tazobactam"],
        "note": "🔴 مقاوم لجميع البيتا-لاكتام!",
    },
    "Proteus mirabilis": {
        "first_line": ["Amoxicillin + Clavulanic acid","Cefuroxime","Cefixime"],
        "second_line": ["Ciprofloxacin","Trimethoprim/Sulfamethoxazole"],
        "avoid": ["Nitrofurantoin","Tetracyclines"],
        "note": "🔬 مقاوم طبيعياً لـ Nitrofurantoin.",
    },
    "Enterococcus faecalis": {
        "first_line": ["Amoxicillin + Clavulanic acid","Fosfomycin","Nitrofurantoin"],
        "second_line": ["Ampicillin/Sulbactam","Vancomycin","Linezolid"],
        "avoid": ["Cephalosporins (كل الجيل)","Trimethoprim/Sulfamethoxazole"],
        "note": "🔬 مقاوم طبيعياً لجميع السيفالوسبورين.",
    },
}

SPECIMEN_TYPES = ["Urine","Blood","Sputum","Wound Swab","Pus","Stool","CSF"]
BACTERIA_TYPES = list(ORGANISM_PROFILE.keys())
COMMON_MEDS    = ["Antacids (مضادات الحموضة)","Warfarin (مضادات التخثر)",
                  "NSAIDs (مسكنات الألم)","SSRI (أدوية الاكتئاب)"]
AWARE_COLORS   = {"Access":"🟢 Access","Watch":"🟡 Watch","Reserve":"🔴 Reserve"}

# ==========================================
# 🔍 OCR + Fuzzy Matching
# ==========================================
def fuzzy_match(word, target):
    w, t = word.lower(), target.lower()
    if t in w or w in t:
        return 100
    matches = sum(c in t for c in w)
    return (matches / max(len(w), len(t))) * 100


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
    for b in BACTERIA_TYPES:
        if b.lower() in text_lower:
            detected_organism = b; break

    # S/I/R per line
    sir_map = {}
    for line in full_text.splitlines():
        ll = line.lower().strip()
        result = None
        if re.search(r'\b(s|sensitive|sens)\b', ll):   result = "S"
        elif re.search(r'\b(r|resistant|resist)\b', ll): result = "R"
        elif re.search(r'\b(i|intermediate|inter)\b', ll): result = "I"
        if result:
            for abx_name, info in ABX_GUIDELINES.items():
                for name in [abx_name] + info["aliases"]:
                    if fuzzy_match(name, ll) >= 75:
                        sir_map[abx_name] = result; break

    # Sensitive block drugs
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
# 📄 Report Generator — full detail
# banned is now a list of dicts:
#   {"name", "reason_short", "reason_detail", "category"}
# category: "resistant"|"renal"|"hepatic"|"pregnancy"|"child"|"organism"|"other"
# ==========================================
WHO_AWARE_EXPLANATION = """
WHO AWaRe CLASSIFICATION — EXPLANATION:
  Access  (🟢) — First-choice antibiotics for common infections.
                  Low resistance potential. Should be widely available
                  and affordable. Use these FIRST whenever possible.
                  Examples: Amoxicillin, Nitrofurantoin, TMP/SMX.

  Watch   (🟡) — Higher resistance potential. Use only when Access
                  antibiotics are not suitable (allergy, resistance,
                  culture result, severity). Require closer monitoring.
                  Examples: Ciprofloxacin, Ceftriaxone, Levofloxacin.

  Reserve (🔴) — Last-resort antibiotics. Use ONLY for confirmed or
                  suspected infections with multi-drug resistant (MDR)
                  organisms when all other options have failed.
                  Overuse threatens their effectiveness globally.
                  Examples: Linezolid, Colistin, Tigecycline.

  Key rule: Always prefer the lowest AWaRe category that is effective
  for the specific culture & patient to minimise resistance development.
"""

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
        "الفلوروكينولونات (Cipro/Levo/Oflox/Norflox) تؤثر على غضاريف\n"
        "  النمو (cartilage) في الأطفال والمراهقين < 18 سنة.\n"
        "  أثبتت الدراسات الحيوانية تلف مفصلي دائم.\n"
        "  تُستخدم فقط عند انعدام البدائل الأخرى تماماً."
    ),
    "tetracycline": (
        "Doxycycline والتتراسيكلينات تترسب في العظام والأسنان\n"
        "  النامية → تلوين دائم للأسنان وتثبيط نمو العظام.\n"
        "  ممنوعة < 8 سنوات بشكل مطلق، وتُتجنب حتى 18 سنة."
    ),
}


def generate_report(age, sex, weight, cl_cr, is_renal, is_preg, is_hepatic,
                    allowed, warned, banned, preg_warn_items,
                    organism, specimen, interactions, sir_map):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    SEP  = "=" * 50
    SEP2 = "-" * 50
    r    = []

    # ── Header ───────────────────────────────────────
    r.append(SEP)
    r.append("   ORANGE LAB — CLINICAL DECISION REPORT")
    r.append(SEP)
    r.append(f"  Date: {now}")
    r.append(f"  Developed by: Dr. Hussein Ali | Orange Lab")
    r.append(SEP)

    # ── Patient ───────────────────────────────────────
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

    # ── Culture ───────────────────────────────────────
    r.append(f"\nCULTURE:")
    r.append(f"  Specimen : {specimen}")
    r.append(f"  Organism : {organism}")
    if organism in ORGANISM_PROFILE:
        op = ORGANISM_PROFILE[organism]
        r.append(f"  Note     : {op['note']}")
        r.append(f"  First-line (guidelines): {', '.join(op['first_line'])}")
        if op["avoid"]:
            r.append(f"  Avoid (intrinsic resistance): {', '.join(op['avoid'])}")

    # ── S/I/R ─────────────────────────────────────────
    if sir_map:
        r.append(f"\nSENSITIVITY RESULTS (extracted from image):")
        r.append(f"  {'Antibiotic':<35} Result")
        r.append(f"  {'-'*35} ------")
        for drug, res in sir_map.items():
            icon = "Sensitive (S)" if res=="S" else ("Resistant (R)" if res=="R" else "Intermediate (I)")
            r.append(f"  {drug:<35} {icon}")

    # ── Interactions ──────────────────────────────────
    non_preg = [i for i in interactions if "🤰" not in i]
    if non_preg:
        r.append(f"\nDRUG INTERACTIONS / WARNINGS:")
        for i in sorted(set(non_preg)):
            r.append(f"  ! {i}")

    # ══════════════════════════════════════════════════
    # ── RECOMMENDED ───────────────────────────────────
    # ══════════════════════════════════════════════════
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
            r.append(f"  Note      : {item['note']}")
            r.append(f"  Renal     : {item['renal_note']}")
            if is_preg and item["preg_status"] == "Warn":
                r.append(f"  Pregnancy : {item['preg_note'].splitlines()[0]}")
    else:
        r.append("  No recommended options after applying all restrictions.")

    # ══════════════════════════════════════════════════
    # ── DOSE ADJUSTMENT (Renal) ───────────────────────
    # ══════════════════════════════════════════════════
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

    # ══════════════════════════════════════════════════
    # ── PREGNANCY WARN ────────────────────────────────
    # ══════════════════════════════════════════════════
    if is_preg and preg_warn_items:
        r.append(f"\n{SEP}")
        r.append("  PREGNANCY — USE WITH CAUTION")
        r.append(f"  (Final decision belongs to the treating physician)")
        r.append(SEP)
        r.append("  These antibiotics are NOT automatically banned.")
        r.append("  They require careful medical evaluation.")
        r.append("  Some have been re-evaluated in recent literature")
        r.append("  (ACCP Journal 2025 and others).")
        r.append("  The detailed reason for caution is listed below.\n")
        for item in preg_warn_items:
            r.append(f"  {item['name']}")
            r.append(f"  {SEP2}")
            for line in item["preg_note"].splitlines():
                r.append(f"  {line}")
            r.append("")

    # ══════════════════════════════════════════════════
    # ── CONTRAINDICATED ───────────────────────────────
    # ══════════════════════════════════════════════════
    if banned:
        r.append(f"\n{SEP}")
        r.append("  CONTRAINDICATED / INEFFECTIVE")
        r.append(SEP)

        # Group by category
        cat_resist   = [b for b in banned if b["category"] == "resistant"]
        cat_renal    = [b for b in banned if b["category"] == "renal"]
        cat_preg     = [b for b in banned if b["category"] == "pregnancy"]
        cat_child    = [b for b in banned if b["category"] == "child"]
        cat_organism = [b for b in banned if b["category"] == "organism"]
        cat_other    = [b for b in banned if b["category"] == "other"]

        if cat_resist:
            r.append(f"\n  [A] RESISTANT IN CULTURE:")
            r.append(f"  Reason: The laboratory confirmed this antibiotic")
            r.append(f"  does NOT inhibit the organism's growth (MIC too high).")
            r.append(f"  Using it will lead to treatment failure.\n")
            for b in cat_resist:
                r.append(f"    x {b['name']}")
                r.append(f"      {b['reason_detail']}\n")

        if cat_renal:
            r.append(f"\n  [B] CONTRAINDICATED IN RENAL IMPAIRMENT:")
            r.append(f"  Patient CrCl = {cl_cr:.1f} ml/min\n")
            for b in cat_renal:
                r.append(f"    x {b['name']}")
                r.append(f"      Short reason : {b['reason_short']}")
                # Detailed reason from RENAL_BAN_REASONS if available
                detail_key = b["name"].lower().replace(" ","")
                for k, v in RENAL_BAN_REASONS.items():
                    if k in detail_key:
                        r.append(f"      Detail       :")
                        for ln in v.splitlines():
                            r.append(f"        {ln}")
                        break
                else:
                    r.append(f"      Detail       : {b['reason_detail']}")
                r.append("")

        if cat_preg:
            r.append(f"\n  [C] CONTRAINDICATED IN PREGNANCY:")
            r.append(f"  The following are banned due to confirmed fetal risk.\n")
            for b in cat_preg:
                r.append(f"    x {b['name']}")
                r.append(f"      Short reason : {b['reason_short']}")
                r.append(f"      Full detail  :")
                for ln in b["reason_detail"].splitlines():
                    r.append(f"        {ln}")
                r.append("")

        if cat_child:
            r.append(f"\n  [D] NOT SUITABLE FOR PATIENTS < 18 YEARS:")
            r.append(f"  Patient age = {age} years\n")
            for b in cat_child:
                r.append(f"    x {b['name']}")
                r.append(f"      Short reason : {b['reason_short']}")
                # Detailed reason from CHILD_BAN_REASONS
                cls = ABX_GUIDELINES.get(b["name"],{}).get("class","").lower()
                if "fluoroquinolone" in cls:
                    for ln in CHILD_BAN_REASONS["fluoroquinolone"].splitlines():
                        r.append(f"        {ln}")
                elif "tetracycline" in cls:
                    for ln in CHILD_BAN_REASONS["tetracycline"].splitlines():
                        r.append(f"        {ln}")
                else:
                    r.append(f"        {b['reason_detail']}")
                r.append("")

        if cat_organism:
            r.append(f"\n  [E] INEFFECTIVE FOR THIS ORGANISM ({organism}):")
            r.append(f"  These antibiotics have intrinsic (natural) resistance")
            r.append(f"  to this organism regardless of culture sensitivity.\n")
            for b in cat_organism:
                r.append(f"    x {b['name']}")
                r.append(f"      {b['reason_detail']}\n")

        if cat_other:
            r.append(f"\n  [F] OTHER CONTRAINDICATIONS:")
            for b in cat_other:
                r.append(f"    x {b['name']}")
                r.append(f"      {b['reason_detail']}\n")

    # ══════════════════════════════════════════════════
    # ── WHO AWaRe EXPLANATION ─────────────────────────
    # ══════════════════════════════════════════════════
    r.append(f"\n{SEP}")
    r.append("  WHO AWaRe CLASSIFICATION — REFERENCE GUIDE")
    r.append(SEP)
    r.append(WHO_AWARE_EXPLANATION)

    # ── Footer ────────────────────────────────────────
    r.append(SEP)
    r.append("  DISCLAIMER:")
    r.append("  هذا التقرير مساعد للقرار الطبي وليس بديلاً عنه.")
    r.append("  القرار النهائي في الوصف يعود للطبيب المعالج.")
    r.append(SEP)
    r.append("  WHO AWaRe Note: 🟢 Access = First choice | 🟡 Watch = Caution | 🔴 Reserve = Last resort")
    r.append(SEP)
    r.append("  Developed by: Dr. Hussein Ali | Orange Lab")
    r.append(SEP)
    return "\n".join(r)


# ==========================================
# 🖥️ Streamlit UI
# ==========================================
st.set_page_config(page_title="Orange Culture Analyzer",
                   layout="wide", page_icon="🛡️")
st.markdown("<style>.block-container{padding-top:1rem;}h1{color:#e87722;}</style>",
            unsafe_allow_html=True)

st.title("🛡️ Orange Culture Analyzer")
st.caption("AI-Assisted Antibiotic Decision Support — Egyptian Market Edition")

uploaded = st.file_uploader("📷 Upload Culture Report Image",
                             type=["jpg","png","jpeg"])

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

    # ── LEFT COLUMN ──────────────────────────────────────────
    with col1:
        st.subheader("👤 Patient & Culture")

        culture_type = st.selectbox(
            "🧫 Specimen", SPECIMEN_TYPES,
            index=SPECIMEN_TYPES.index(patient["Specimen"])
                  if patient["Specimen"] in SPECIMEN_TYPES else 0)

        organism_type = st.selectbox(
            "🦠 Organism", BACTERIA_TYPES,
            index=BACTERIA_TYPES.index(patient["Organism"])
                  if patient["Organism"] in BACTERIA_TYPES else 0)

        if organism_type in ORGANISM_PROFILE:
            op = ORGANISM_PROFILE[organism_type]
            with st.expander("📌 Organism Guidance", expanded=True):
                st.info(op["note"])
                st.write("**First-line:**", ", ".join(op["first_line"]))
                st.write("**Second-line:**", ", ".join(op["second_line"]))
                if op["avoid"]:
                    st.error("**Avoid:** " + ", ".join(op["avoid"]))

        st.divider()
        age    = st.number_input("Age (years)", value=int(patient["Age"]),
                                 min_value=0, max_value=120)
        sex    = st.selectbox("Gender", ["Female","Male"],
                              index=0 if patient["Sex"]=="Female" else 1)
        weight = st.number_input("Weight (kg)", min_value=5, max_value=300, value=70)

        st.divider()
        is_renal = st.checkbox("🚩 Renal Impairment")
        cl_cr    = 100.0
        if is_renal:
            s_cr  = st.number_input("Serum Creatinine (mg/dL)",
                                    min_value=0.1, max_value=20.0,
                                    value=1.0, step=0.1)
            cl_cr = ((140 - age) * weight) / (72 * s_cr)
            if sex == "Female": cl_cr *= 0.85
            st.metric("CrCl (Cockcroft-Gault)", f"{cl_cr:.1f} ml/min",
                      delta="Mild" if cl_cr>=60 else
                            ("Moderate" if cl_cr>=30 else "Severe"),
                      delta_color="normal" if cl_cr>=60 else
                                  ("off" if cl_cr>=30 else "inverse"))

        is_hepatic = st.checkbox("🚩 Hepatic Impairment")

        is_preg = False
        if sex == "Female" and 12 <= age <= 55:
            is_preg = st.checkbox("🤰 Patient is Pregnant")

        current_meds = st.multiselect("💊 Current Medications", COMMON_MEDS)

    # ── RIGHT COLUMN ─────────────────────────────────────────
    with col2:
        st.subheader("💊 Antibiotic Analysis")

        if sir_map:
            st.info("📊 S/I/R detected from image: " +
                    " | ".join(f"{k}: **{v}**" for k,v in sir_map.items()))

        final_drugs = st.multiselect(
            "✅ Confirm/Edit Sensitive Antibiotics:",
            options=sorted(ABX_GUIDELINES.keys()),
            default=[d for d in drugs_from_ocr if d in ABX_GUIDELINES],
        )

        allowed, warned, banned = [], [], []
        preg_warn_items          = []   # Warn-level pregnancy drugs
        interactions_alerts      = []
        organism_avoid           = ORGANISM_PROFILE.get(organism_type,{}).get("avoid",[])

        for d in final_drugs:
            info  = ABX_GUIDELINES[d]
            d_low = d.lower()

            # ① Resistant in culture
            if sir_map.get(d) == "R":
                banned.append({
                    "name": d, "category": "resistant",
                    "reason_short": "مقاوم (R) في نتيجة المزرعة.",
                    "reason_detail": (
                        f"المزرعة أثبتت أن {d} لا يثبط نمو الجرثومة.\n"
                        f"        الـ MIC أعلى من الحد العلاجي.\n"
                        f"        الاستخدام سيؤدي لفشل علاجي مؤكد."
                    ),
                })
                continue

            # ② Drug interactions
            for med in current_meds:
                if med in info["interacts_with"]:
                    interactions_alerts.append(f"⚡ تعارض: {d} مع {med}")

            # ③ Hepatic
            if is_hepatic and info["hepatic_caution"]:
                interactions_alerts.append(
                    f"🏥 تحذير كبدي: {d} — يحتاج متابعة وظائف الكبد.")

            # ④ Organism-specific avoid
            if any(av.lower() in d_low or d_low in av.lower()
                   for av in organism_avoid):
                banned.append({
                    "name": d, "category": "organism",
                    "reason_short": f"غير فعال لـ {organism_type} طبيعياً.",
                    "reason_detail": (
                        f"{d} لديه مقاومة طبيعية (intrinsic resistance)\n"
                        f"        لجرثومة {organism_type} بغض النظر عن نتيجة المزرعة.\n"
                        f"        الاستخدام سيؤدي لفشل علاجي."
                    ),
                })
                continue

            # ⑤ MRSA beta-lactam rule
            if organism_type == "MRSA":
                bl_classes = ["Penicillin","Cephalosporin"]
                if any(c in info["class"] for c in bl_classes):
                    banned.append({
                        "name": d, "category": "organism",
                        "reason_short": "بيتا-لاكتام — لا يعمل على MRSA.",
                        "reason_detail": (
                            f"MRSA يحمل جين mecA الذي يُنتج بروتين PBP2a.\n"
                            f"        هذا البروتين لا يرتبط بأي بيتا-لاكتام.\n"
                            f"        → جميع البنسيلين والسيفالوسبورين غير فعالة."
                        ),
                    })
                    continue

            # ⑥ Pregnancy — BANNED
            if is_preg and info["preg_status"] == "Banned":
                banned.append({
                    "name": d, "category": "pregnancy",
                    "reason_short": info["preg_note"].splitlines()[0],
                    "reason_detail": info["preg_note"],
                })
                continue

            # ⑦ Pregnancy — WARN (stays in allowed but flagged)
            if is_preg and info["preg_status"] == "Warn":
                preg_warn_items.append({"name": d, **info})

            # ⑧ Child < 18
            if age < 18 and not info["child_safe"]:
                cls = info["class"].lower()
                if "fluoroquinolone" in cls:
                    detail = "فلوروكينولون — خطر تلف غضاريف النمو < 18 سنة."
                elif "tetracycline" in cls:
                    detail = "تتراسيكلين — يتراسب في العظام والأسنان النامية."
                else:
                    detail = f"غير مرخص للاستخدام في الأطفال < 18 سنة."
                banned.append({
                    "name": d, "category": "child",
                    "reason_short": f"غير مناسب لمن هم دون 18 سنة.",
                    "reason_detail": detail,
                })
                continue

            # ⑨ Nitrofurantoin hard cutoff
            if is_renal and "nitrofurantoin" in d_low and cl_cr < 30:
                banned.append({
                    "name": d, "category": "renal",
                    "reason_short": f"ممنوع — CrCl {cl_cr:.1f} < 30 مل/د.",
                    "reason_detail": (
                        f"CrCl المريض = {cl_cr:.1f} مل/د (أقل من الحد المطلوب 30).\n"
                        f"        Nitrofurantoin لا يصل لتركيز علاجي في البول\n"
                        f"        عند ضعف الكلى، ويتراكم في الدم مسبباً سُمية."
                    ),
                })
                continue

            # ⑩ Renal dose adjustment
            if is_renal and info["renal_limit"] > 0 and cl_cr <= info["renal_limit"]:
                warned.append({"name": d, **info})
                continue

            allowed.append({"name": d, **info})

        # ── Display: Interactions ──────────────────────────
        non_preg_alerts = [a for a in interactions_alerts if "🤰" not in a]
        if non_preg_alerts:
            st.warning("⚡ Interactions / Hepatic Warnings")
            for a in sorted(set(non_preg_alerts)):
                st.write(a)

        # ── Display: Pregnancy WARN section ───────────────
        if is_preg and preg_warn_items:
            st.markdown("---")
            st.markdown("### 🤰 Pregnancy — Use With Caution")
            st.info(
                "الأدوية التالية **ليست محظورة تلقائياً** لكنها تحتاج تقييم طبي دقيق.\n\n"
                "بعضها أُعيد تقييمه في الأدبيات الحديثة (ACCP 2025).\n\n"
                "**القرار النهائي للطبيب المعالج حصراً.**"
            )
            for item in preg_warn_items:
                with st.expander(f"⚠️ {item['name']} — تفاصيل التحذير"):
                    for line in item["preg_note"].splitlines():
                        st.write(line)

        # ── Display: Banned ────────────────────────────────
        if banned:
            with st.expander("🚫 Contraindicated / Ineffective", expanded=True):
                for b in banned:
                    cat_label = {
                        "resistant": "مقاوم في المزرعة",
                        "renal":     "قصور كلوي",
                        "pregnancy": "ممنوع في الحمل",
                        "child":     "غير مناسب < 18 سنة",
                        "organism":  "غير فعال للجرثومة",
                        "other":     "موانع أخرى",
                    }.get(b["category"], "")
                    st.error(f"💊 {b['name']}  [{cat_label}]\n{b['reason_short']}")

        # ── Display: Dose Adjustment ───────────────────────
        if warned:
            with st.expander("🟡 Dose Adjustment Required", expanded=True):
                for item in warned:
                    sir_tag = f" [{sir_map.get(item['name'],'')}]" if sir_map else ""
                    st.warning(f"**{item['name']}{sir_tag}** — {item['renal_note']}")

        # ── Display: Recommended ───────────────────────────
        if allowed:
            st.success(f"🟢 {len(allowed)} Recommended Option(s)")
            for item in sorted(allowed, key=lambda x: x["priority"]):
                sir_badge = f" [{sir_map.get(item['name'],'?')}]" if sir_map else ""
                preg_flag = " 🤰" if (is_preg and item["preg_status"]=="Warn") else ""
                with st.expander(
                    f"{item['name']}{sir_badge}{preg_flag} — {AWARE_COLORS[item['aware']]}"
                ):
                    c1, c2 = st.columns(2)
                    c1.write(f"**Class:** {item['class']}")
                    c2.write(f"**Route:** {'🟢 PO' if item['high_po'] else '💉 IV only'}")
                    st.write(f"**Note:** {item['note']}")
                    if is_preg and item["preg_status"] == "Warn":
                        st.caption("🤰 " + item["preg_note"].splitlines()[0])
        elif not banned and not warned:
            st.info("اختر المضادات الحساسة من القائمة أعلاه.")

        # ── Download ───────────────────────────────────────
        if final_drugs:
            st.divider()
            report_txt = generate_report(
                age, sex, weight, cl_cr, is_renal, is_preg, is_hepatic,
                allowed, warned, banned, preg_warn_items,
                organism_type, culture_type,
                interactions_alerts, sir_map,
            )
            st.download_button(
                "📄 Download Clinical Report",
                report_txt,
                file_name=f"Orange_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True,
            )

st.divider()
st.markdown("""
<div style="text-align:center;color:gray;font-size:0.85rem;">
  <strong>Developed by: Dr. Hussein Ali | Orange Lab</strong><br>
  WHO AWaRe: 🟢 <b>Access</b> (First choice) |
  🟡 <b>Watch</b> (Use with caution) |
  🔴 <b>Reserve</b> (Last resort)
</div>
""", unsafe_allow_html=True)
