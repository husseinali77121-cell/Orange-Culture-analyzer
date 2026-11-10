# © 2025 Dr / Hussein Ali — Orange Lab, 6 October City, Egypt
# Orange Culture Tool — All Rights Reserved
# Unauthorized copying or distribution is prohibited.

"""Organism profile dataset for Orange Culture Tool.

Enhancements in this revision:
- added helper lookup/validation utilities
- added clinically relevant missing profiles (VRE)
  [Rickettsia spp. added here, then removed 2026-08-01 as unreachable — see below]
- exported normalization helpers for cross-module consistency checks
"""

import re
from typing import Any, Dict, Iterable, Optional

ORGANISM_PROFILE = {
    "E. coli": {
        # 2026-11-10: amox-clav moved to second line -- IDSA cystitis guidance
        # ranks beta-lactams below nitrofurantoin / TMP-SMX / fosfomycin.
        "first_line": ["Nitrofurantoin","Fosfomycin",
                       "Trimethoprim/Sulfamethoxazole"],
        "second_line": ["Amoxicillin + Clavulanic acid","Cefuroxime","Cefuroxime sodium",
                        "Cefixime","Ceftriaxone","Ciprofloxacin","Norfloxacin"],
        "third_line":  ["Ertapenem","Meropenem"],
        "avoid": [],
        "urine_note": (
            "Norfloxacin: مخصص للمسالك فقط — لا تركيز علاجي خارج البول.\n"
            "Ertapenem: يُحفظ للـ ESBL-producing E. coli فقط.\n"
            "Nitrofurantoin / Fosfomycin الفموي: لالتهاب المثانة فقط — لا تصل لنسيج الكلى."
        ),
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
        "first_line": ["Trimethoprim/Sulfamethoxazole","Amoxicillin + Clavulanic acid",
                       "Cefuroxime"],
        "second_line": ["Cefixime","Cefuroxime sodium","Ceftriaxone","Ciprofloxacin",
                        "Norfloxacin","Piperacillin + Tazobactam"],
        "third_line":  ["Ertapenem","Meropenem"],
        "avoid": ["Ampicillin (alone)"],
        "urine_note": (
            "ESBL Klebsiella (IDSA AMR 2026): التهاب المثانة ← TMP-SMX أو Nitrofurantoin إذا حساسة؛ "
            "التهاب الحويضة ← TMP-SMX أو Ciprofloxacin/Levofloxacin؛ العدوى الغازية ← Carbapenem.\n"
            "Fosfomycin الفموي: لا breakpoints لـ Klebsiella (fosA كروموسومي).\n"
            "Norfloxacin: للمسالك فقط."
        ),
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
        # 2026-11-10: Cefoperazone-sulbactam removed (no breakpoints for the
        # combination); Tobramycin replaces gentamicin-era aminoglycoside use
        # (CLSI 2023); novel agents listed for DTR (IDSA AMR 2026).
        "first_line": ["Piperacillin + Tazobactam","Ceftazidime","Cefepime","Ciprofloxacin"],
        "second_line": ["Levofloxacin","Meropenem","Imipenem/Cilastatin","Aztreonam",
                        "Tobramycin","Amikacin"],
        "third_line":  ["Ceftolozane + Tazobactam","Ceftazidime + Avibactam",
                        "Imipenem + Relebactam","Cefiderocol","Colistin"],
        "avoid": ["Nitrofurantoin","Fosfomycin","Trimethoprim/Sulfamethoxazole",
                  "Cephalexin","Cefadroxil","Cefaclor","Norfloxacin",
                  "Cefuroxime sodium","Ertapenem"],
        "urine_note": (
            "Ertapenem: ممنوع لـ Pseudomonas — لا نشاط (EUCAST).\n"
            "Ciprofloxacin و Levofloxacin (750mg) فعّالان ضد Pseudomonas؛ Norfloxacin لا يُستخدم.\n"
            "Gentamicin: ألغته CLSI 2023 لـ P. aeruginosa — Tobramycin هو البديل؛ Amikacin للبول فقط.\n"
            "الأمينوجليكوزيد منفرداً لعدوى البول فقط (CLSI 2023)."
        ),
        "specimen_context": {
            "Blood":      "🔴 Pseudomonas bacteremia — mortality عالية — ICU.",
            "Sputum":     "🔴 VAP/HAP الأكثر خطورة — anti-pseudomonal إلزامي.",
            "Wound Swab": "🔴 شائع في حروق والجروح المزمنة.",
            "Urine":      "🔴 UTI المعقد — كاتيتر أو مضادات سابقة.",
        },
        "note": "🔬 جرثومة انتهازية — تحتاج anti-pseudomonal متخصص.",
    },
    "Acinetobacter baumannii": {
        # 2026-11-10: Cefoperazone-sulbactam removed from first line -- not
        # in IDSA guidance, no breakpoint, and its sulbactam dose (<=4 g/day)
        # is below the 6-9 g/day IDSA uses for CRAB.
        "first_line": ["Ampicillin/Sulbactam"],
        # Doxycycline was listed here even after clinical_data.py was corrected to
        # mark it intrinsically resistant -- EUCAST Intrinsic Resistance v3.3,
        # Table 2 fn.2: Acinetobacter is intrinsically resistant to tetracycline
        # and doxycycline but NOT to minocycline and tigecycline. The engine
        # banned it while this list still displayed it as second-line, so one
        # screen contradicted the other. Replaced by the agent that actually
        # works.
        "second_line": ["Meropenem","Imipenem/Cilastatin","Amikacin",
                        "Trimethoprim/Sulfamethoxazole","Minocycline"],
        "third_line":  ["Sulbactam + Durlobactam","Cefiderocol","Tigecycline","Colistin"],
        "avoid": ["Ertapenem","Cephalexin","Cefuroxime","Ceftriaxone",
                  "Azithromycin","Clarithromycin","Nitrofurantoin","Fosfomycin"],
        # Attached to the drug when it is offered; never demotes it.
        "agent_notes": {
            "Ampicillin/Sulbactam": ("Acinetobacter: جرعة عالية — 9 g sulbactam يومياً "
                                     "(مثلاً 9 g Ampicillin/Sulbactam q8h بتسريب 4 ساعات) — "
                                     "وفي CRAB مع دواء ثانٍ فعّال (IDSA 2026)."),
            "Minocycline": "Acinetobacter: 200 mg q12h؛ في CRAB كجزء من توليفة (IDSA 2026).",
        },
        "specimen_context": {
            "Blood":      "🔴 Acinetobacter bacteremia — ICU — MDR غالباً.",
            "Sputum":     "🔴 VAP الأكثر شيوعاً في ICU — خطر جداً.",
            "Wound Swab": "🔴 عدوى الحروق والجروح الكبيرة.",
        },
        "note": (
            "🔴 MDR غالباً. CRAB (IDSA AMR Guidance 2026): Sulbactam-durlobactam + "
            "Meropenem أو Imipenem هو المفضّل؛ وإلا Ampicillin-sulbactam جرعة عالية "
            "(9 g sulbactam/يوم) + دواء ثانٍ (Polymyxin B / Minocycline / Tigecycline / "
            "Cefiderocol). لا Rifampicin ولا Colistin منفرداً. Cefoperazone-sulbactam: "
            "جرعة السولباكتام فيه غير كافية ولا breakpoints له."
        ),
    },
    "Staphylococcus aureus": {
        "first_line": ["Oxacillin","Cefazolin","Cephalexin","Cefadroxil"],
        "second_line": ["Amoxicillin + Clavulanic acid","Clindamycin","Cefuroxime sodium",
                         "Trimethoprim/Sulfamethoxazole","Doxycycline","Erythromycin"],
        "third_line":  ["Fusidic acid","Penicillin"],
        "avoid": [],
        "urine_note": (
            "Oxacillin: إذا S → MSSA — استخدم Cefazolin أو Oxacillin.\n"
            "Oxacillin: إذا R → MRSA — ابدأ Vancomycin أو Linezolid فوراً.\n"
            "Clindamycin: D-test مطلوب إذا Erythromycin=R.\n"
            "Penicillin: يُستخدم فقط عند تأكيد Beta-lactamase سالب.\n"
            "Fusidic acid: يُستخدم في combination فقط — لا monotherapy.\n"
            "S. aureus في البول → تحقق من Blood culture (hematogenous seeding)."
        ),
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
        "first_line": ["Vancomycin","Linezolid","Daptomycin"],
        "second_line": ["Trimethoprim/Sulfamethoxazole","Doxycycline","Clindamycin",
                        "Ceftaroline","Teicoplanin"],
        "third_line":  ["Fusidic acid"],
        # Ceftaroline binds PBP2a -- the class-wide "Cephalosporins" avoid
        # below must not catch it (2026-11-10).
        "avoid_exempt": ["Ceftaroline"],
        "avoid": ["Oxacillin","Penicillin","Cephalexin","Cefadroxil","Cefaclor",
                  "Cefuroxime","Cefuroxime sodium","Ceftriaxone",
                  "Amoxicillin + Clavulanic acid","Ampicillin/Sulbactam",
                  "Piperacillin + Tazobactam","Ertapenem",
                  "Cephalosporins","Carbapenems"],   # class-wide: also catches Cefixime/Cefepime/Ceftazidime/Cefazolin/Meropenem/Imipenem (PBP2a -> all beta-lactams fail, bar anti-MRSA ceph)
        "urine_note": (
            "جميع البيتا-لاكتام لا تعمل على MRSA (mecA gene — PBP2a) **عدا Ceftaroline**.\n"
            "Clindamycin: D-test مطلوب إذا Erythromycin=R — لا تستخدم بدون تأكيد.\n"
            "Fusidic acid: يُستخدم في combination فقط (مع Rifampicin أو Vancomycin) — لا monotherapy."
        ),
        "specimen_context": {
            "Blood":      "🔴 MRSA bacteremia — ابدأ Vancomycin فوراً.",
            "Sputum":     "🔴 MRSA pneumonia — خطر في ICU.",
            "Wound Swab": "🔴 MRSA SSTI — شائع في المجتمع (CA-MRSA).",
            "Pus":        "🔴 MRSA abscess — drainage + Vancomycin.",
            "CSF":        "🔴 MRSA meningitis — نادر لكن خطر.",
        },
        "note": ("🔴 مقاوم لجميع البيتا-لاكتام عدا Ceftaroline. تجرثم الدم: Vancomycin "
                 "(AUC-guided) أو Daptomycin؛ الالتهاب الرئوي: Vancomycin أو Linezolid "
                 "(Daptomycin لا يُستخدم في الرئة). IDSA MRSA."),
    },
    "Proteus mirabilis": {
        "first_line": ["Trimethoprim/Sulfamethoxazole","Amoxicillin + Clavulanic acid",
                       "Cefuroxime","Cefixime"],
        "second_line": ["Cefuroxime sodium","Ceftriaxone","Ciprofloxacin","Norfloxacin"],
        "third_line":  ["Ertapenem","Meropenem"],
        "avoid": ["Nitrofurantoin","Tetracyclines","Colistin"],
        "caution": {"Imipenem/Cilastatin": (
            "Proteeae: نشاط Imipenem منخفض جوهرياً (MICs أعلى) — Meropenem أو Ertapenem "
            "هو الكاربابينيم المفضّل، و Imipenem R وحده ليس علامة CRE (CDC).")},
        "urine_note": (
            "Nitrofurantoin: مقاوم طبيعياً لـ Proteus (intrinsic) — EUCAST.\n"
            "Norfloxacin: فعال في UTI فقط."
        ),
        "specimen_context": {
            "Urine":      "🔬 شائع في UTI — يرفع الـ pH (urease).",
            "Wound Swab": "🔬 عدوى الجروح المزمنة والقدم السكري.",
            "Blood":      "⚠️ Proteus bacteremia — مصدره البولي غالباً.",
        },
        "note": "🔬 مقاوم طبيعياً لـ Nitrofurantoin — لا تستخدمه أبداً.",
    },
    "Enterococcus faecalis": {
        # 2026-11-10: Ampicillin/Amoxicillin are THE agents for E. faecalis
        # (IDSA / ESC 2023); amox-clav adds nothing over amoxicillin here.
        "first_line": ["Ampicillin","Amoxicillin","Nitrofurantoin","Fosfomycin"],
        "second_line": ["Penicillin","Amoxicillin + Clavulanic acid",
                        "Ampicillin/Sulbactam","Vancomycin"],
        "third_line":  ["Linezolid","Daptomycin","Teicoplanin"],
        "avoid": ["Cephalosporins (كل الجيل)","Trimethoprim/Sulfamethoxazole",
                  "Cefuroxime sodium","Ertapenem","Norfloxacin"],
        "urine_note": (
            "Ertapenem وCefuroxime sodium: لا نشاط ضد Enterococcus (EUCAST).\n"
            "جميع السيفالوسبورين مقاومة طبيعياً لـ Enterococcus."
        ),
        "specimen_context": {
            "Urine":      "🔬 شائع في UTI خصوصاً الكاتيتر.",
            "Blood":      "⚠️ Enterococcus bacteremia — خطر endocarditis.",
            "Wound Swab": "⚠️ عدوى البطن والجروح الجراحية.",
        },
        "note": ("🔬 مقاوم طبيعياً للسيفالوسبورين — Ampicillin/Amoxicillin هو الأساس.\n"
                 "🫀 التهاب الشغاف: Ampicillin + Ceftriaxone (تآزر — ESC 2023) أو Ampicillin + "
                 "Gentamicin **فقط إذا HLAR سالب** (Gentamicin 120 µg / Streptomycin 300 µg). "
                 "قرص الجنتاميسين العادي لا يُفسَّر للمكورات المعوية."),
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
        "avoid": ["Nitrofurantoin","Fosfomycin","Amoxicillin + Clavulanic acid",
                  "Metronidazole"],
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
        "first_line": ["Penicillin","Amoxicillin + Clavulanic acid",
                        "Ceftriaxone","Levofloxacin"],
        "second_line": ["Azithromycin","Erythromycin","Clarithromycin",
                         "Clindamycin","Cefuroxime"],
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
        "second_line": ["Azithromycin","Levofloxacin",
                         "Trimethoprim/Sulfamethoxazole"],
        "third_line":  [],
        # 2026-11-10: Ampicillin removed from "avoid" -- a beta-lactamase-
        # NEGATIVE isolate is ampicillin-S and ampicillin/amoxicillin is then
        # the agent of choice (CLSI M100: BL-positive -> report ampicillin R).
        "avoid": [],
        "agent_notes": {
            "Ampicillin": ("H. influenzae: Ampicillin S يعني بيتا-لاكتاماز سالب — Ampicillin/"
                           "Amoxicillin هو الخيار المفضّل حينها (BLNAR نادر؛ راجع النتيجة)."),
        },
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
        "second_line": ["Erythromycin","Doxycycline","Clarithromycin"],
        "third_line":  [],
               "avoid": ["Beta-lactams (alone)","Aminoglycosides","Cephalosporins"],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔬 Legionella — CAP الشديد، خاصةً في الفنادق أو مكيفات الهواء.",
            "Blood":  "⚠️ Bacteremia نادر — التشخيص بـ Urine Antigen أو PCR.",
        },
        "note": "🔬 Levofloxacin هو الخيار الأول. لا يُعزل بالزراعة العادية — يحتاج وسط BCYE.",
    },
    "Mycoplasma spp.": {
        "first_line": ["Azithromycin","Doxycycline"],
        "second_line": ["Erythromycin","Levofloxacin","Clarithromycin"],
        "third_line":  [],
        "avoid": ["Beta-lactams","Cephalosporins","Vancomycin","Aminoglycosides"],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔬 Atypical pneumonia — Walking pneumonia — خاصةً في الشباب.",
        },
        "note": ("🔬 لا جدار خلوي — كل البيتا-لاكتام غير فعالة. يُشخص بـ PCR أو Serology.\n"
                 "M. pneumoniae: ماكروليد أولاً، و Doxycycline أو Levofloxacin عند فشله "
                 "(مقاومة الماكروليد شائعة في شرق آسيا).\n"
                 "⚠️ M. hominis مقاوم جوهرياً للماكروليدات (Erythromycin/Azithromycin/"
                 "Clarithromycin) ← Doxycycline أو Clindamycin. Ureaplasma مقاوم جوهرياً "
                 "للـ Clindamycin ← Doxycycline أو Azithromycin."),
    },
    "Anaerobes (لاهوائيات)": {
        "first_line": ["Metronidazole","Clindamycin","Amoxicillin + Clavulanic acid"],
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
        # 2026-11-10 (IDSA AMR Guidance 2026): cefiderocol monotherapy is the
        # preferred agent for invasive infection; aztreonam-avibactam is an
        # alternative. Doxycycline removed -- CLSI breakpoints exist for
        # minocycline, not doxycycline.
        "first_line": ["Cefiderocol","Trimethoprim/Sulfamethoxazole"],
        "second_line": ["Minocycline", "Levofloxacin"],
        "third_line":  ["Aztreonam + Avibactam"],
        "avoid": ["Carbapenems","Ertapenem","Meropenem","Imipenem/Cilastatin",
                  "Aminoglycosides","Ceftriaxone","Cefepime"],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔴 شائع في VAP/HAP في ICU — خاصةً بعد علاج طويل بالكاربابينيم.",
            "Blood":  "🔴 Stenotrophomonas bacteremia — نادر لكن خطر في المناعة الضعيفة.",
        },
        "note": ("🔴 مقاومة طبيعية للكاربابينيم (L1 metallo-β-lactamase) — ينتقى بعد Meropenem.\n"
                 "العدوى الغازية (IDSA AMR 2026): Cefiderocol منفرداً هو المفضّل؛ البديل "
                 "Aztreonam-avibactam (أو Ceftazidime-avibactam + Aztreonam) ويُفضَّل مع دواء ثانٍ. "
                 "TMP-SMX أو Minocycline أو Levofloxacin للعدوى الخفيفة أو كتنزيل، ويُفضَّل "
                 "توليفة دوائين منها في العدوى الشديدة إن لم يتوفر Cefiderocol.\n"
                 "لا تُفسَّر نتيجة Ceftazidime (أُلغيت breakpoints في CLSI 2024)."),
    },
}
# Additional clinically relevant profiles referenced by the antibiotic module.
ORGANISM_PROFILE.update({
       "VRE": {
        # 2026-11-10: amox-clav and amp-sulbactam removed from "avoid" --
        # VRE E. faecalis is usually ampicillin-S and an aminopenicillin is then
        # the drug of choice; the inhibitor neither helps nor makes it inactive.
        "first_line": ["Linezolid","Daptomycin"],
        "second_line": ["Ampicillin","Amoxicillin","Nitrofurantoin","Fosfomycin"],
        "third_line": ["Tigecycline"],
        "avoid": [
            "Vancomycin",
            "Cephalosporins (كل الجيل)",
            "Carbapenems",
            "Ertapenem",
        ],
        "urine_note": "VRE = Vancomycin-resistant Enterococcus؛ لذلك لا يُستخدم Vancomycin. راجع الحساسية المحلية، وLinezolid خيار مهم في العدوى الجهازية.",
        "specimen_context": {
            "Blood": "🔴 VRE bacteremia — يحتاج علاج موجّه ومتابعة متخصصة.",
            "Urine": "⚠️ VRE قد يظهر في UTI المعقد أو المرضى المنومين لفترات طويلة.",
            "Wound Swab": "⚠️ قد يظهر في الجروح المزمنة والمستشفيات.",
        },
        "note": ("🔴 VRE يعني مقاومة للفانكومايسين. إذا كان Ampicillin = S (غالباً E. faecalis) "
                 "فهو الخيار الأول؛ وإلا Linezolid أو Daptomycin بجرعة عالية (8-12 mg/kg) "
                 "لتجرثم الدم. البول: Nitrofurantoin أو Fosfomycin حسب الحساسية."),
    },

    # REMOVED 2026-08-01. "Rickettsia spp." carried a full profile here and
    # appeared in NO specimen list in specimen_organism_map.py, so
    # get_organisms_for_specimen() never offered it and not one of its
    # first_line / avoid / note fields could ever reach a user. Its own note
    # conceded the point -- "ليست جرثومة مزرعية روتينية" -- which is correct:
    # rickettsial disease is diagnosed by serology or PCR, never by the
    # culture-and-sensitivity workflow this tool exists to support. A profile
    # that cannot be selected is not "data consistency", it is a table entry
    # that has to be maintained and audited forever and can never fire.
    # The clinical_matrix.py DENY rules (sulfonamides worsen outcome,
    # vancomycin cannot reach an obligate intracellular organism) are kept:
    # they cost nothing and would apply immediately if the organism is ever
    # added back to a specimen list.

    # Generic fallback for reports that read "Gram Negative Bacilli" with no
    # species identification (very common locally). Lets the Enterobacterales
    # logic (ESBL predictor, ceph/carbapenem QC) run WITHOUT forcing a specific
    # species. Name must stay exactly "Enterobacterales (unspeciated)" so its
    # lowercase contains the "enterobacterales" substring matched in
    # streamlit_app.py (ESBL_PRODUCERS + QC004). Deliberately NO genus-specific
    # intrinsic resistance and NO assumed AmpC — the genus is unknown.
    "Enterobacterales (unspeciated)": {
        "first_line":  ["Amoxicillin + Clavulanic acid", "Cefuroxime", "Ciprofloxacin"],
        "second_line": ["Ceftriaxone", "Piperacillin + Tazobactam", "Amikacin"],
        "third_line":  ["Ertapenem", "Meropenem"],
        "avoid": [],   # unspeciated -> do NOT assume intrinsic R (e.g. Klebsiella's Ampicillin)
        "urine_note": (
            "كائن Enterobacterales غير محدد النوع — العلاج يُوجَّه بنتيجة الحساسية.\n"
            "لا تُفترض مقاومة intrinsic جينس-محددة (مثل Ampicillin في Klebsiella) قبل الـ ID."
        ),
        "specimen_context": {
            "Sputum":     "⚠️ GNB غير معرّف في البلغم — قيّم جودة العينة (احتمال colonization) واطلب ID.",
            "Urine":      "🔬 افصل ABU عن UTI بالأعراض + العدّ؛ اطلب ID عند الحاجة.",
            "Blood":      "🔴 Enterobacterales bacteremia — اطلب ID + MIC عاجل.",
            "Pus":        "🔬 خراجات البطن — Enterobacterales شائعة؛ ID مهم.",
            "Wound Swab": "🔬 عدوى جروح — افصل colonization عن infection.",
        },
        "note": (
            "🔬 Enterobacterales غير محدد النوع (GNB). الجينس غير معروف — لا AmpC ولا "
            "مقاومة intrinsic جينس-محددة مفترضة. يُنصح بـ ID + MIC. الـ ESBL predictor "
            "يعمل من نمط السيفالوسبورين في الـ AST."
        ),
    },
})

# ════════════════════════════════════════════════════════════════════════════
#  CHROMOSOMAL-AmpC GENERA — added 2026-08-01
#  --------------------------------------------------------------------------
#  DEFECT THIS FIXES
#  streamlit_app.AMPC_PRODUCERS listed eleven genera. Ten of them were NOT in
#  this file, so the organism dropdown could never reach them and the inducible-
#  AmpC pathway was dead code from the user's side; only P. aeruginosa remained
#  reachable. (The plasmid-AmpC pathway for E. coli / Klebsiella / Proteus was
#  working and is untouched.)
#
#  Worse, streamlit_app.ORGANISM_OCR_ALIASES already mapped "serratia",
#  "s. marcescens", "enterobacter" and "enterobacter cloacae" to profile keys
#  that did not exist here. best_default_index() falls back to index 0 when the
#  detected name is not in the list, so an OCR'd Serratia marcescens blood
#  report silently became E. coli -- and E. coli carries no derepression rule,
#  so Ceftriaxone-S came back RECOMMENDED for the one group of organisms where
#  a susceptible 3rd-generation cephalosporin is the classic trap.
#
#  clinical_data.INTRINSIC_RESISTANCE already held complete, correct rows for
#  all of these; nothing could reach them. This block adds the reachability.
#
#  CLINICAL BASIS (revised 2026-11-10 against IDSA AMR Guidance 2026):
#  the risk of clinically significant AmpC derepression on a 3rd-generation
#  cephalosporin is NOT uniform across this group.
#    * moderate-to-high risk: Enterobacter cloacae complex, Klebsiella
#      aerogenes, Citrobacter freundii (and Hafnia alvei). Ceftriaxone is not
#      suggested to START therapy for invasive infection; it is reasonable for
#      uncomplicated cystitis, and continuing it is reasonable in a non-severe
#      infection that is already responding. Cefepime is preferred.
#    * low risk: Serratia marcescens, Morganella morganii, Providencia spp.
#      -- treat according to the AST result (a 3rd-gen S is usable).
#  The previous revision put all six on one hard "avoid" list, which BANNED
#  an S ceftriaxone even for Serratia cystitis, and labelled the ban
#  "intrinsic resistance" on screen. It is now a `caution` (demote + note)
#  for the higher-risk genera and nothing at all for the low-risk ones.
# ════════════════════════════════════════════════════════════════════════════
_AMPC_DEREPRESSION_NOTE = (
    "⚠️ **AmpC كروموسومي قابل للتحفيز — خطر متوسط/مرتفع** (IDSA AMR 2026).\n"
    "السيفالوسبورينات من الجيل الثالث قد تظهر **حسّاسة** ثم تفشل: العلاج بها قد ينتقي "
    "طفرات مُفرِطة الإنتاج (stable derepression).\n"
    "**العدوى الغازية:** ابدأ بـ Cefepime (ثابت أمام AmpC، إذا MIC ≤ 2)؛ Carbapenem إذا "
    "كان Cefepime SDD/I. Ceftriaxone مقبول لالتهاب المثانة، ويُعقل الاستمرار فيه في عدوى "
    "غير شديدة تستجيب بالفعل.\n"
    "**التنزيل الفموي:** TMP-SMX أو Fluoroquinolone حسب الحساسية.\n"
    "المصدر: IDSA AMR Guidance 2026 · EUCAST Expert Rules v3.1."
)
_AMPC_LOW_RISK_NOTE = (
    "ℹ️ **AmpC كروموسومي منخفض الخطر** (IDSA AMR 2026): احتمال الانتقاء أثناء العلاج "
    "منخفض — اختر حسب نتيجة الحساسية؛ الجيل الثالث الحسّاس قابل للاستخدام."
)
_AMPC_3GC_CAUTION_TEXT = (
    "IDSA AMR 2026 — AmpC متوسط/مرتفع الخطر: لا يُبدأ بالجيل الثالث لعدوى غازية حتى لو S "
    "(خطر انتقاء AmpC مُفرط الإنتاج) — Cefepime هو المفضّل. مقبول لالتهاب المثانة، ويُعقل "
    "الاستمرار فيه إذا تحسّن المريض في عدوى غير شديدة."
)
# "Cefoperazone + Sulbactam" listed explicitly: caution keys are exact names,
# and sulbactam does not protect cefoperazone from AmpC (the old substring
# avoid caught it; the exact-key caution must name it).
_AMPC_3GC_CAUTION = {d: _AMPC_3GC_CAUTION_TEXT for d in
                     ("Ceftriaxone", "Cefotaxime", "Ceftazidime", "Cefixime", "Cefoperazone",
                      "Cefoperazone + Sulbactam")}
_AMPC_PIPTAZO_CAUTION = {"Piperacillin + Tazobactam": (
    "IDSA AMR 2026 — AmpC متوسط/مرتفع الخطر: Pip-Tazo غير مقترح للعدوى الغازية "
    "(MERINO-2 تجريبية فقط) — Cefepime أو Carbapenem. مقبول لالتهاب المثانة.")}
_PROTEEAE_IMIPENEM_CAUTION = {"Imipenem/Cilastatin": (
    "Proteeae: نشاط Imipenem منخفض جوهرياً (MICs أعلى) — Meropenem أو Ertapenem هو "
    "الكاربابينيم المفضّل، و Imipenem R وحده ليس علامة CRE (CDC).")}
_AMPC_SPECIMEN_CONTEXT = {
    "Blood":      "🔴 تجرثم دم بكائن AmpC متوسط/مرتفع الخطر — ابدأ بـ Cefepime (إذا S) أو Carbapenem، لا بالجيل الثالث.",
    "Urine":      "🔬 في التهاب المثانة البسيط الجيل الثالث الحسّاس مقبول؛ في pyelonephritis عامله كعدوى غازية.",
    "Sputum":     "⚠️ شائع كـ colonizer على أنابيب التنفس — افصل الاستعمار عن العدوى قبل العلاج.",
    "Pus":        "🔬 خراج — الصرف الجراحي أهم من اختيار الدواء؛ Cefepime مفضّل على الجيل الثالث.",
    "Wound Swab": "🔬 عدوى جروح/حروق — شائع في وحدات الحروق؛ Cefepime مفضّل على الجيل الثالث.",
}
_AMPC_LOW_SPECIMEN_CONTEXT = {
    "Blood":      "🔴 تجرثم دم — اختر حسب الحساسية؛ الجيل الثالث الحسّاس مقبول (AmpC منخفض الخطر).",
    "Urine":      "🔬 شائع مع القسطرة — افصل الاستعمار عن العدوى.",
    "Sputum":     "⚠️ شائع كـ colonizer على أنابيب التنفس — افصل الاستعمار عن العدوى قبل العلاج.",
    "Pus":        "🔬 خراج — الصرف الجراحي أهم من اختيار الدواء.",
    "Wound Swab": "🔬 عدوى جروح/حروق — فسّر مع الصورة السريرية.",
}

ORGANISM_PROFILE.update({
    "Enterobacter cloacae": {
        "first_line":  ["Cefepime", "Trimethoprim/Sulfamethoxazole", "Ciprofloxacin"],
        "second_line": ["Piperacillin + Tazobactam", "Amikacin", "Levofloxacin"],
        "third_line":  ["Meropenem", "Imipenem/Cilastatin"],
        # Ampicillin / amox-clav / 1st-2nd gen cephalosporins are handled by
        # clinical_data.INTRINSIC_RESISTANCE["enterobacter cloacae"]. Listed
        # here are the agents that are NOT intrinsic but must still be avoided:
        # a susceptible 3rd-gen result that will not hold under therapy.
        "avoid": [],
        "caution": {**_AMPC_3GC_CAUTION, **_AMPC_PIPTAZO_CAUTION},
        "urine_note": ("Enterobacter في البول: في التهاب مثانة غير معقّد يمكن "
                       "الاعتماد على Nitrofurantoin/Fosfomycin حسب الحساسية؛ "
                       "في pyelonephritis عامله كعدوى غازية."),
        "specimen_context": dict(_AMPC_SPECIMEN_CONTEXT),
        "note": "🦠 **Enterobacter cloacae complex.**\n" + _AMPC_DEREPRESSION_NOTE,
    },
    "Serratia marcescens": {
        "first_line":  ["Ceftriaxone", "Cefepime", "Ciprofloxacin",
                        "Trimethoprim/Sulfamethoxazole"],
        "second_line": ["Piperacillin + Tazobactam", "Amikacin", "Levofloxacin"],
        "third_line":  ["Meropenem", "Imipenem/Cilastatin"],
        "avoid": [],
        "urine_note": ("⚠️ Serratia مقاومة جوهرياً لـ Nitrofurantoin و Colistin "
                       "و Tetracycline/Doxycycline — لا تُطرح كخيار بولي. "
                       "(Minocycline و Tigecycline تعملان — عكس Proteae.)"),
        "specimen_context": dict(_AMPC_LOW_SPECIMEN_CONTEXT),
        "note": ("🦠 **Serratia marcescens.**\n" + _AMPC_LOW_RISK_NOTE +
                 "\n\n📋 مقاومة جوهرية إضافية: Colistin · Nitrofurantoin · "
                 "Tetracycline · Doxycycline. لكن **Minocycline و Tigecycline "
                 "فعّالتان** — وهو ما يميّزها عن Proteus/Morganella/Providencia "
                 "(EUCAST v3.3 Table 2, fn.5)."),
    },
    "Citrobacter freundii": {
        "first_line":  ["Cefepime", "Ciprofloxacin", "Trimethoprim/Sulfamethoxazole"],
        "second_line": ["Piperacillin + Tazobactam", "Amikacin", "Levofloxacin"],
        "third_line":  ["Meropenem", "Imipenem/Cilastatin"],
        "avoid": [],
        "caution": {**_AMPC_3GC_CAUTION, **_AMPC_PIPTAZO_CAUTION},
        "urine_note": ("Citrobacter freundii في البول: وجّه العلاج بالحساسية "
                       "وتجنّب الجيل الثالث في العدوى الغازية."),
        "specimen_context": dict(_AMPC_SPECIMEN_CONTEXT),
        "note": ("🦠 **Citrobacter freundii.**\n" + _AMPC_DEREPRESSION_NOTE +
                 "\n\n📋 ملاحظة: *C. koseri* كائن مختلف — لا يحمل AmpC قابلاً "
                 "للتحفيز، ومقاومته الجوهرية تقتصر على الأمينوبنسلينات."),
    },
    # ── Proteae (Morganella / Providencia) ──────────────────────────────────
    # Also chromosomal-AmpC and also absent from this file until 2026-08-01.
    # Both are ordinary catheter-associated urinary isolates, and both carry a
    # distinctive intrinsic profile that clinical_data already held and nothing
    # could reach: tetracyclines AND tigecycline AND colistin AND nitrofurantoin
    # are all out — the exact opposite of Serratia, where minocycline and
    # tigecycline work. Offering "Nitrofurantoin, S" for a Morganella UTI is the
    # error this prevents.
    "Morganella morganii": {
        "first_line":  ["Ceftriaxone", "Cefepime", "Ciprofloxacin",
                        "Trimethoprim/Sulfamethoxazole"],
        "second_line": ["Piperacillin + Tazobactam", "Amikacin", "Levofloxacin"],
        "third_line":  ["Meropenem", "Imipenem/Cilastatin"],
        "avoid": [],
        "caution": dict(_PROTEEAE_IMIPENEM_CAUTION),
        "urine_note": ("⚠️ Morganella مقاومة جوهرياً لـ Nitrofurantoin و Colistin "
                       "وكل التتراسيكلينات (بما فيها Tigecycline) — لا تُطرح "
                       "كخيارات بولية مهما كانت نتيجة القرص."),
        "specimen_context": dict(_AMPC_LOW_SPECIMEN_CONTEXT),
        "note": ("🦠 **Morganella morganii** (مجموعة Proteae).\n"
                 + _AMPC_LOW_RISK_NOTE +
                 "\n\n📋 مقاومة جوهرية إضافية: Colistin · Nitrofurantoin · "
                 "Tetracycline · Doxycycline · Minocycline · Tigecycline "
                 "(EUCAST v3.3 Table 2, fn.3). شائعة في التهابات المسالك "
                 "المرتبطة بالقسطرة."),
    },
    "Providencia spp.": {
        "first_line":  ["Ceftriaxone", "Cefepime", "Ciprofloxacin",
                        "Trimethoprim/Sulfamethoxazole"],
        "second_line": ["Piperacillin + Tazobactam", "Amikacin", "Levofloxacin"],
        "third_line":  ["Meropenem", "Imipenem/Cilastatin"],
        "avoid": [],
        "caution": dict(_PROTEEAE_IMIPENEM_CAUTION),
        "urine_note": ("⚠️ Providencia مقاومة جوهرياً لـ Nitrofurantoin و Colistin "
                       "وكل التتراسيكلينات، **و كذلك Gentamicin و Tobramycin** — "
                       "الأميكاسين هو الأمينوجليكوزيد الوحيد الذي قد يعمل."),
        "specimen_context": dict(_AMPC_LOW_SPECIMEN_CONTEXT),
        "note": ("🦠 **Providencia spp.** (مجموعة Proteae).\n"
                 + _AMPC_LOW_RISK_NOTE +
                 "\n\n📋 مقاومة جوهرية إضافية: Gentamicin · Tobramycin · "
                 "Colistin · Nitrofurantoin · كل التتراسيكلينات و Tigecycline "
                 "(EUCAST v3.3 Table 2). **Amikacin مستثنى** — قد يبقى فعّالاً."),
    },
    "Hafnia alvei": {
        "first_line":  ["Cefepime", "Ciprofloxacin", "Trimethoprim/Sulfamethoxazole"],
        "second_line": ["Piperacillin + Tazobactam", "Amikacin"],
        "third_line":  ["Meropenem", "Imipenem/Cilastatin"],
        "avoid": [],
        "caution": {**_AMPC_3GC_CAUTION, **_AMPC_PIPTAZO_CAUTION},
        "urine_note": "Hafnia alvei نادرة — أكِّد التعريف قبل بناء قرار علاجي عليها.",
        "specimen_context": dict(_AMPC_SPECIMEN_CONTEXT),
        "note": ("🦠 **Hafnia alvei** — عزلة نادرة، غالباً استعمار أو تلوث. "
                 "أكِّد التعريف أولاً.\n" + _AMPC_DEREPRESSION_NOTE),
    },
})


# ════════════════════════════════════════════════════════════════════════════
#  ORGANISMS THAT HAD RULES BUT NO WAY IN — added 2026-08-03
#  --------------------------------------------------------------------------
#  clinical_data.INTRINSIC_RESISTANCE carried complete, correct rows for
#  Listeria, both pyogenic streptococci, E. faecium and the coagulase-negative
#  staphylococci — and none of them appeared in this file, so the dropdown never
#  offered them and not one of those rules could ever fire.
#
#  Listeria is the one that matters most: it is intrinsically resistant to EVERY
#  cephalosporin, and it causes meningitis in exactly the three groups a
#  ceftriaxone-first protocol is written for — neonates, pregnant women and the
#  elderly. A lab that reports Listeria to a tool that cannot represent it gets
#  no warning that the empirical cephalosporin will fail.
#
#  CoNS is the opposite problem: the commonest blood-culture isolate in any lab,
#  and usually a skin contaminant. The clinical question is not "which
#  antibiotic" but "is this real at all", so its profile leads with that.
# ════════════════════════════════════════════════════════════════════════════
ORGANISM_PROFILE.update({
    "Listeria monocytogenes": {
        "first_line":  ["Ampicillin", "Amoxicillin", "Penicillin"],
        "second_line": ["Trimethoprim/Sulfamethoxazole", "Meropenem"],
        "third_line":  ["Linezolid", "Vancomycin"],
        # Every cephalosporin. This is the entire point of the entry.
        "avoid": ["Ceftriaxone", "Cefotaxime", "Ceftazidime", "Cefepime",
                  "Cefuroxime", "Cefazolin", "Cephalexin", "Cefixime",
                  "Cefoxitin", "Cefaclor", "Cefadroxil", "Cephradine",
                  "Cefoperazone", "Ceftaroline", "Cefiderocol"],
        "urine_note": "Listeria نادرة جداً في البول — أكِّد التعريف قبل أي قرار.",
        "specimen_context": {
            "CSF": ("🔴 **التهاب سحايا بالليستيريا.** السيفالوسبورينات **كلها** تفشل — "
                    "لهذا يُضاف Ampicillin تجريبياً للوليد والحامل ومن تجاوز 50 سنة. "
                    "أضِف Gentamicin للتآزر في الحالات الشديدة."),
            "Blood": ("🔴 تجرثم دم بالليستيريا — شائع في الحمل (قد يكون العرض الوحيد) "
                      "وفي نقص المناعة. Ampicillin ± Gentamicin."),
            "Pus": "🔬 نادرة — أكِّد التعريف.",
        },
        "note": ("🦠 **Listeria monocytogenes** — عصيّة موجبة الجرام داخل خلوية.\n"
                 "⛔ **مقاومة جوهرية لكل السيفالوسبورينات** (PBP3 منخفضة الألفة) — "
                 "أي نتيجة حساسية لسيفالوسبورين هنا غير قابلة للتفسير ويجب "
                 "عدم الاعتماد عليها.\n"
                 "🤰 الفئات المعرّضة: الحوامل · حديثو الولادة · فوق 50 سنة · "
                 "نقص المناعة. المصدر الغذائي: الأجبان الطرية والألبان غير المبسترة.\n"
                 "📋 العلاج: Ampicillin جرعة عالية ± Gentamicin للتآزر. "
                 "بديل الحساسية للبنسلين: TMP-SMX. (IDSA Meningitis · EUCAST v16.1)"),
    },
    "Streptococcus pyogenes (Group A)": {
        "first_line":  ["Penicillin", "Amoxicillin", "Ampicillin"],
        "second_line": ["Cefazolin", "Cephalexin", "Clindamycin"],
        "third_line":  ["Azithromycin", "Clarithromycin", "Vancomycin"],
        # TMP-SMX: handled by the engine (CLSI M100 Ed36 -- breakpoints for
        # skin/soft-tissue infection only), not a blanket avoid (2026-11-10).
        "avoid": [],
        "urine_note": "GAS في البول غير معتاد — استبعد التلوّث.",
        "specimen_context": {
            "Wound Swab": ("🔴 التهاب نسيج خلوي / حمرة / التهاب لفافة نخري. "
                           "أضِف **Clindamycin** في الحالات الغازية لتثبيط "
                           "إنتاج الذيفان (تأثير Eagle)."),
            "Pus": "🔴 خراج — الصرف الجراحي أساسي مع البنسلين.",
            "Blood": "🔴 متلازمة الصدمة السمّية العقدية — Penicillin + Clindamycin + IVIG.",
        },
        "note": ("🦠 **Streptococcus pyogenes** (المجموعة A).\n"
                 "✅ **لم تُوثَّق مقاومة للبنسلين إطلاقاً على مستوى العالم** — "
                 "أي نتيجة تقول Penicillin = R تعني خطأ في التعريف أو الاختبار "
                 "ويجب إعادتهما قبل أي قرار.\n"
                 "⚠️ مقاومة الماكروليدات موجودة وتتفاوت محلياً — لا تُستخدم إلا "
                 "بنتيجة حساسية.\n"
                 "📋 في العدوى الغازية أضِف Clindamycin: يوقف تصنيع الذيفان "
                 "الخارجي ولا يتأثر بكثافة الجراثيم. (CLSI M100 Ed36)"),
    },
    "Streptococcus agalactiae (Group B)": {
        "first_line":  ["Penicillin", "Ampicillin", "Amoxicillin"],
        "second_line": ["Cefazolin", "Ceftriaxone"],
        "third_line":  ["Vancomycin", "Clindamycin"],
        "avoid": [],
        # FIX 2026-11-10: the note said GBS bacteriuria at ANY count needs
        # antepartum treatment. ACOG CO 797: any count -> intrapartum
        # prophylaxis; antepartum treatment only at >=10^5 CFU/mL or if
        # symptomatic.
        "urine_note": ("🤰 **GBS في بول الحامل بأي عدد** = استعمار ثقيل ← وقاية بالبنسلين "
                       "أثناء المخاض (ولا حاجة لمسحة الأسبوع 36-37). **العلاج أثناء الحمل** "
                       "فقط إذا العدد ≥ 10⁵ CFU/mL أو وُجدت أعراض. (ACOG CO 797)"),
            "specimen_context": {
            "Blood": "🔴 إنتان وليدي مبكر أو متأخر — Ampicillin + Gentamicin.",
            "CSF": "🔴 سحايا وليدية — Ampicillin جرعة عالية ± Gentamicin.",
            "Urine": "🤰 راجع ملاحظة البول — له دلالة خاصة في الحمل.",
            "Wound Swab": "🔬 عدوى جلد ونسيج رخو، خاصة في السكري.",
        },
        "note": ("🦠 **Streptococcus agalactiae** (المجموعة B).\n"
                 "🤰 **السبب الأول للإنتان الوليدي المبكر.** يُفحص للحوامل في "
                 "الأسبوع 36–37، والإيجابيات تأخذ وقاية بالبنسلين أثناء المخاض.\n"
                 "⚠️ عند حساسية البنسلين: **اطلب D-test** — مقاومة الكليندامايسين "
                 "المُحرَّضة شائعة في GBS، و Erythromycin=R مع Clindamycin=S "
                 "يعني احتمال فشل الكليندامايسين.\n"
                 "✅ البنسلين يظل فعّالاً دائماً. (CDC GBS Guidelines · CLSI M100 Ed36)"),
    },
    "Enterococcus faecium": {
        "first_line":  ["Vancomycin", "Linezolid"],
        "second_line": ["Teicoplanin", "Daptomycin"],
        "third_line":  ["Tigecycline"],
        "avoid": ["Ceftriaxone", "Cefotaxime", "Ceftazidime", "Cefepime",
                  "Cefuroxime", "Cefazolin", "Cephalexin", "Cefoxitin",
                  "Trimethoprim/Sulfamethoxazole", "Clindamycin"],
        "urine_note": ("في التهاب المثانة البسيط: Nitrofurantoin أو Fosfomycin "
                       "حسب الحساسية — تجنّب الأدوية الواسعة."),
        "specimen_context": {
            "Blood": ("🔴 تجرثم دم بـ E. faecium — **مقاومة الأمبيسيلين هي القاعدة** "
                      "(>90% عالمياً)، بعكس E. faecalis. تحقّق من الفانكومايسين."),
            "Urine": "🔬 شائع في القسطرة — افصل الاستعمار عن العدوى.",
            "Pus": "🔬 عدوى داخل بطنية — غالباً ضمن فلورا مختلطة.",
        },
        "note": ("🦠 **Enterococcus faecium** — يختلف عن *E. faecalis* اختلافاً "
                 "علاجياً جوهرياً.\n"
                 "⚠️ **مقاومة الأمبيسيلين هي القاعدة** في *faecium* (>90%) "
                 "والاستثناء في *faecalis* — لا تعامِلهما ككائن واحد.\n"
                 "⚠️ معظم عزلات VRE هي *faecium*. VanA = مقاوم للفانكومايسين "
                 "والتيكوبلانين؛ **VanB = مقاوم للفانكومايسين وحسّاس للتيكوبلانين**.\n"
                 "⛔ مقاومة جوهرية: كل السيفالوسبورينات · الكليندامايسين · "
                 "TMP-SMX (فعّال معملياً وفاشل سريرياً) · البوليميكسينات."),
    },
    "Coagulase-negative Staphylococci": {
        "first_line":  ["Vancomycin"],
        "second_line": ["Teicoplanin", "Linezolid"],
        "third_line":  ["Daptomycin", "Trimethoprim/Sulfamethoxazole", "Doxycycline"],
        "avoid": [],
        "urine_note": ("CoNS في البول: **S. saprophyticus** ممرض حقيقي في الفتيات "
                       "الشابات؛ باقي الأنواع غالباً تلوّث إلا مع قسطرة أو "
                       "جسم غريب."),
        "specimen_context": {
            "Blood": ("⚠️ **سؤال التلوّث قبل سؤال الدواء.** CoNS أشهر عزلة في مزارع "
                      "الدم وأغلبها تلوّث جلدي. مؤشرات العدوى الحقيقية: نمو في "
                      "**زجاجتين منفصلتين أو أكثر** · وجود جهاز داخل وعائي أو "
                      "صمّام صناعي · نمو خلال أقل من 24 ساعة · صورة سريرية موافقة. "
                      "زجاجة واحدة من مجموعة واحدة = تلوّث حتى يثبت العكس."),
            "Wound Swab": "🔬 غالباً فلورا جلدية — فسّر مع الصورة السريرية.",
            "Pus": "🔬 له وزن حقيقي مع الأجسام الصناعية (مفاصل · شرائح).",
            "CSF": "⚠️ له وزن حقيقي مع تحويلة بطينية صفاقية؛ وإلا فتلوّث.",
        },
        "note": ("🦠 **عنقوديات سالبة التخثّر** (S. epidermidis · S. haemolyticus · "
                 "S. hominis · S. saprophyticus).\n"
                 "⚠️ **أشهر عزلة في مزارع الدم، وأغلبها تلوّث.** لا تبدأ علاجاً "
                 "قبل الإجابة على سؤال الأهمية.\n"
                 "📋 حين تكون حقيقية: **>70–80% مقاومة للميثيسيلين** — الفانكومايسين "
                 "هو الخيار التجريبي، وينزل إلى Oxacillin/Cefazolin فقط إذا ثبتت "
                 "الحساسية.\n"
                 "🔧 مرتبطة بالأجهزة والأجسام الصناعية عبر الأغشية الحيوية "
                 "(biofilm) — **نزع الجهاز غالباً شرط للشفاء**، وأضِف Rifampicin "
                 "للأجسام الصناعية مع دواء فعّال آخر.\n"
                 "⚠️ **S. lugdunensis استثناء**: يسلك سلوك *S. aureus* في الشراسة "
                 "ويجب التعامل معه كممرض حقيقي دائماً — اختره بالاسم من القائمة. "
                 "وكذلك **S. saprophyticus** في البول."),
    },
})

# ════════════════════════════════════════════════════════════════════════════
#  ORGANISMS ADDED 2026-11-10 (review H14)
#  Common laboratory identifications the dropdown could not represent, so OCR
#  mapped them to a neighbour with a DIFFERENT intrinsic profile:
#    * Citrobacter koseri  -> was read as C. freundii (koseri has no inducible
#      AmpC; amox-clav and 1st/2nd-gen cephalosporins can work).
#    * Proteus vulgaris    -> was read as P. mirabilis (vulgaris is
#      intrinsically resistant to ampicillin and cefuroxime; mirabilis is not).
#    * S. saprophyticus    -> was read as CoNS (it is a true urinary pathogen
#      in young women and is intrinsically resistant to fosfomycin).
#    * S. lugdunensis      -> was read as CoNS (behaves like S. aureus and must
#      never be dismissed as a contaminant).
# ════════════════════════════════════════════════════════════════════════════
ORGANISM_PROFILE.update({
    "Citrobacter koseri": {
        "first_line":  ["Trimethoprim/Sulfamethoxazole", "Amoxicillin + Clavulanic acid",
                        "Cefuroxime", "Ceftriaxone"],
        "second_line": ["Ciprofloxacin", "Cefepime", "Piperacillin + Tazobactam"],
        "third_line":  ["Ertapenem", "Meropenem"],
        "avoid": [],
        "urine_note": ("C. koseri: Nitrofurantoin يعمل عادةً حسب الحساسية. لا يحمل AmpC قابلاً "
                       "للتحفيز — بعكس C. freundii."),
        "specimen_context": {
            "Urine": "🔬 شائع في UTI المرتبط بالقسطرة.",
            "CSF":   "🔴 C. koseri سبب معروف لالتهاب السحايا وخراج الدماغ عند حديثي الولادة.",
            "Blood": "🔬 تجرثم دم — غالباً من مصدر بولي.",
        },
        "note": ("🦠 **Citrobacter koseri** — مقاومته الجوهرية تقتصر على الأمينوبنسلينات "
                 "(β-lactamase من الصنف A). لا AmpC قابل للتحفيز. ⚠️ يسبب خراجات دماغية "
                 "عند حديثي الولادة."),
    },
    "Proteus vulgaris": {
        "first_line":  ["Trimethoprim/Sulfamethoxazole", "Ceftriaxone", "Ciprofloxacin"],
        "second_line": ["Cefepime", "Piperacillin + Tazobactam", "Amikacin", "Levofloxacin"],
        "third_line":  ["Ertapenem", "Meropenem"],
        "avoid": [],
        "caution": {"Imipenem/Cilastatin": (
            "Proteeae: نشاط Imipenem منخفض جوهرياً (MICs أعلى) — Meropenem أو Ertapenem هو "
            "الكاربابينيم المفضّل، و Imipenem R وحده ليس علامة CRE (CDC).")},
        "urine_note": ("⚠️ P. vulgaris مقاوم جوهرياً لـ Nitrofurantoin و Colistin وكل "
                       "التتراسيكلينات و Tigecycline، وكذلك Ampicillin و Cefuroxime و "
                       "الجيل الأول — بعكس P. mirabilis."),
        "specimen_context": {
            "Urine": "🔬 UTI معقّد / قسطرة — منتج لليورياز (حصوات).",
            "Wound Swab": "🔬 عدوى جروح مزمنة.",
        },
        "note": ("🦠 **Proteus vulgaris** (مجموعة Proteae) — cefuroximase كروموسومي (صنف A "
                 "قابل للتحفيز): مقاوم جوهرياً لـ Ampicillin و Amoxicillin والجيل الأول و "
                 "Cefuroxime (EUCAST). الجيل الثالث والرابع فعّالان عادةً."),
    },
    "Staphylococcus saprophyticus": {
        "first_line":  ["Nitrofurantoin", "Trimethoprim/Sulfamethoxazole"],
        "second_line": ["Cephalexin", "Amoxicillin + Clavulanic acid", "Ciprofloxacin"],
        "third_line":  [],
        "avoid": [],
        "urine_note": ("S. saprophyticus ممرض بولي حقيقي في النساء الشابات (حتى بأعداد ≥10³–10⁴). "
                       "⛔ مقاوم جوهرياً لـ Fosfomycin و Fusidic acid و Novobiocin (EUCAST). "
                       "CLSI: اختبار الحساسية الروتيني غير ضروري لعزلات البول — يستجيب عادةً "
                       "للأدوية المعتادة للمسالك."),
        "specimen_context": {
            "Urine": "🔬 ثاني أشيع سبب لالتهاب المثانة في النساء الشابات.",
        },
        "note": ("🦠 **Staphylococcus saprophyticus** — عنقودي سالب التخثّر لكنه ممرض بولي "
                 "حقيقي، لا يُعامل كتلوّث. مقاوم جوهرياً لـ Fosfomycin و Novobiocin."),
    },
    "Staphylococcus lugdunensis": {
        "first_line":  ["Oxacillin", "Cefazolin", "Cephalexin"],
        "second_line": ["Vancomycin", "Clindamycin", "Trimethoprim/Sulfamethoxazole",
                        "Doxycycline"],
        "third_line":  ["Linezolid", "Daptomycin"],
        "avoid": [],
        "urine_note": "",
        "specimen_context": {
            "Blood": ("🔴 **لا يُعامل كتلوّث أبداً** — زجاجة واحدة تستحق التقييم. يسبب التهاب "
                      "شغاف شرساً كـ S. aureus؛ اطلب Echo."),
            "Wound Swab": "🔬 عدوى جلد ونسيج رخو وخراجات.",
            "Pus": "🔬 خراجات وعدوى المفاصل الصناعية.",
        },
        "note": ("🦠 **Staphylococcus lugdunensis** — سالب التخثّر لكنه يسلك سلوك S. aureus. "
                 "CLSI يفسّر Oxacillin/Cefoxitin له بـ breakpoints الـ S. aureus. غالباً حسّاس "
                 "للبنسلين — لكن لا يُعتمد عليه دون نفي البنسليناز."),
    },
})

# Guarantee a complete schema across all organism records.
for _payload in ORGANISM_PROFILE.values():
    _payload.setdefault("first_line", [])
    _payload.setdefault("second_line", [])
    _payload.setdefault("third_line", [])
    _payload.setdefault("avoid", [])
    _payload.setdefault("urine_note", "")
    _payload.setdefault("specimen_context", {})
    _payload.setdefault("note", "")

# Updated set to include legacy antibiotic names not present in ABX_GUIDELINES,
# preventing false "avoid item not found" errors during validation.
GENERIC_DRUG_CLASS_TERMS = {
    "cephalosporins (كل الجيل)",
    "cephalosporins",
    "cephalosporins (alone)",      # Added for Legionella pneumophila
    "beta-lactams",
    "beta-lactams (alone)",
    "aminoglycosides",
    "carbapenems",
    "tetracyclines",
    "ampicillin",                  # Added for Klebsiella spp.
    "ampicillin (alone)",          # Added for H. influenzae
}


def normalize_organism_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def get_organism_profile(name: str) -> Optional[Dict[str, Any]]:
    direct = ORGANISM_PROFILE.get(name)
    if direct:
        return direct
    normalized = normalize_organism_key(name)
    for organism_name, payload in ORGANISM_PROFILE.items():
        if normalize_organism_key(organism_name) == normalized:
            return payload
    return None


def validate_organism_profile(known_antibiotics: Optional[Iterable[str]] = None) -> list[str]:
    issues: list[str] = []
    known_abx = set(known_antibiotics or [])

    for organism_name, payload in ORGANISM_PROFILE.items():
        required = {"first_line", "second_line", "third_line", "avoid", "urine_note", "specimen_context", "note"}
        missing = sorted(required - set(payload.keys()))
        if missing:
            issues.append(f"{organism_name}: missing keys -> {', '.join(missing)}")

        if known_abx:
            for bucket_name in ("first_line", "second_line", "third_line"):
                for abx_name in payload.get(bucket_name, []):
                    if abx_name not in known_abx:
                        issues.append(f"{organism_name}: {bucket_name} antibiotic missing in ABX_GUIDELINES -> {abx_name}")
            for avoid_name in payload.get("avoid", []):
                low = avoid_name.lower().strip()
                if avoid_name not in known_abx and low not in GENERIC_DRUG_CLASS_TERMS:
                    issues.append(f"{organism_name}: avoid item not found in ABX_GUIDELINES -> {avoid_name}")

    return issues


__all__ = [
    "GENERIC_DRUG_CLASS_TERMS",
    "ORGANISM_PROFILE",
    "get_organism_profile",
    "normalize_organism_key",
    "validate_organism_profile",
]


# ════════════════════════════════════════════════════════════════════════════
#  ROUND-2 CORRECTIONS — 2026-11-10
#  --------------------------------------------------------------------------
#  Applied as explicit, commented amendments so each change is readable on its
#  own and the reason sits next to it.
# ════════════════════════════════════════════════════════════════════════════
def _r2_extend(name, key, items):
    row = ORGANISM_PROFILE[name]
    cur = list(row.get(key) or [])
    row[key] = cur + [i for i in items if i not in cur]


def _r2_notes(name, key, mapping):
    row = ORGANISM_PROFILE[name]
    merged = dict(row.get(key) or {})
    merged.update(mapping)
    row[key] = merged


# S. pneumoniae -- amoxicillin is the first-line oral agent (ATS/IDSA CAP 2019);
# amox-clav and the respiratory quinolone are second line. Ceftazidime, cefixime
# and ciprofloxacin test "S" on some panels but have NO pneumococcal breakpoints
# (CLSI/EUCAST) and poor activity -- they were being offered.
ORGANISM_PROFILE["Streptococcus pneumoniae"]["first_line"] = ["Amoxicillin", "Penicillin", "Ceftriaxone"]
ORGANISM_PROFILE["Streptococcus pneumoniae"]["second_line"] = [
    "Amoxicillin + Clavulanic acid", "Levofloxacin", "Cefuroxime", "Doxycycline",
    "Azithromycin", "Erythromycin", "Clarithromycin", "Clindamycin"]
_r2_extend("Streptococcus pneumoniae", "avoid", [
    # NOTE: "Ofloxacin" is deliberately absent -- the avoid matcher is a
    # substring test and "ofloxacin" sits inside "levOFLOXACIN" and
    # "moxifloxacin" is safe only by spelling. Caught by the snapshot review.
    "Ceftazidime", "Cefixime", "Ciprofloxacin", "Norfloxacin",
    "Cephalexin", "Cefadroxil", "Cephradine", "Cefoxitin", "Cefoperazone",
    "Cefoperazone + Sulbactam", "Ceftazidime + Avibactam", "Ceftolozane + Tazobactam",
    "Nitrofurantoin", "Fosfomycin"])

# Staphylococci -- EUCAST: ceftazidime, cefixime, ceftazidime-avibactam and
# ceftolozane-tazobactam have no breakpoints and "should not be used for
# staphylococcal infections", whatever the oxacillin result.
for _n in ("Staphylococcus aureus", "Coagulase-negative Staphylococci",
           "Staphylococcus saprophyticus", "Staphylococcus lugdunensis"):
    _r2_extend(_n, "avoid", ["Ceftazidime", "Cefixime", "Ceftazidime + Avibactam",
                             "Ceftolozane + Tazobactam"])

# Legionella -- intracellular: clindamycin has no useful activity.
_r2_extend("Legionella pneumophila", "avoid", ["Clindamycin"])
_r2_notes("Legionella pneumophila", "caution", {
    "Trimethoprim/Sulfamethoxazole": ("Legionella: بديل ضعيف وبلا دليل سريري كافٍ — الخيار "
                                      "Levofloxacin أو Azithromycin (ATS/IDSA CAP 2019).")})

# Anaerobes -- clindamycin is no longer first line: B. fragilis group resistance
# is commonly >= 30% (IDSA intra-abdominal guidance removed it).
ORGANISM_PROFILE["Anaerobes (لاهوائيات)"]["first_line"] = ["Metronidazole", "Amoxicillin + Clavulanic acid"]
ORGANISM_PROFILE["Anaerobes (لاهوائيات)"]["second_line"] = [
    "Piperacillin + Tazobactam", "Meropenem", "Imipenem/Cilastatin",
    "Ampicillin/Sulbactam", "Clindamycin"]
_r2_notes("Anaerobes (لاهوائيات)", "agent_notes", {
    "Clindamycin": ("اللاهوائيات: مقاومة Bacteroides fragilis للكليندامايسين شائعة (≥ 30%) — لا يُعتمد "
                    "عليه تجريبياً في عدوى البطن (IDSA IAI)؛ مقبول فوق الحجاب الحاجز مع ثبوت الحساسية.")})

# H. influenzae -- a beta-lactamase-negative isolate (Ampicillin S) is treated
# with amoxicillin; it was missing from the lines altogether.
ORGANISM_PROFILE["H. influenzae"]["first_line"] = ["Amoxicillin", "Amoxicillin + Clavulanic acid", "Ceftriaxone"]
ORGANISM_PROFILE["H. influenzae"]["second_line"] = [
    "Cefuroxime", "Azithromycin", "Levofloxacin", "Trimethoprim/Sulfamethoxazole"]
_r2_notes("H. influenzae", "agent_notes", {
    "Amoxicillin": ("H. influenzae: Amoxicillin للعزلة سالبة البيتا-لاكتاماز (Ampicillin S). "
                    "في السحايا/العدوى الغازية: Ceftriaxone.")})

# Stenotrophomonas -- CLSI M100 Ed34+ carries the comment that levofloxacin and
# trimethoprim-sulfamethoxazole "should not be used alone"; IDSA 2026 prefers
# cefiderocol monotherapy for invasive infection.
_r2_notes("Stenotrophomonas maltophilia", "caution", {
    "Trimethoprim/Sulfamethoxazole": ("Stenotrophomonas: CLSI M100 Ed34+ — لا يُستخدم منفرداً في العدوى "
                                      "الغازية؛ ضمن توليفة (مع Minocycline أو Levofloxacin) أو "
                                      "Cefiderocol منفرداً (IDSA AMR Guidance 2026)."),
    "Levofloxacin": ("Stenotrophomonas: CLSI M100 Ed34+ — لا يُستخدم منفرداً (مقاومة تظهر أثناء "
                     "العلاج)؛ ضمن توليفة فقط."),
})

# Morganella / Providencia -- ampicillin-sulbactam and cefoxitin left the
# INTRINSIC table (they are in neither CLSI Appendix B nor EUCAST Table 1), but
# chromosomal AmpC makes both unreliable, so they stay "not recommended".
for _n in ("Morganella morganii", "Providencia spp."):
    _r2_extend(_n, "avoid", ["Ampicillin/Sulbactam", "Cefoxitin"])

# Enterococci -- the anti-staphylococcal penicillins have no useful activity
# (no CLSI/EUCAST breakpoints); "Oxacillin S" on a panel is not a treatment
# option. Not an intrinsic-resistance claim, so it lives here.
for _n in ("Enterococcus faecalis", "Enterococcus faecium", "VRE"):
    _r2_extend(_n, "avoid", ["Oxacillin"])


# ════════════════════════════════════════════════════════════════════════════
#  ORGANISMS NOT IDENTIFIED TO SPECIES LEVEL — added 2026-11-10
#  --------------------------------------------------------------------------
#  Local reports often stop at the genus ("Acinetobacter spp.") or at the Gram
#  stain ("Gram negative bacilli"). Until now the only choices were to force a
#  species the lab never named, or to fall back on "Enterobacterales
#  (unspeciated)" for an organism that may be a non-fermenter.
#
#  RULE USED: each genus-level entry inherits the lines of the species that is
#  both the commonest and the most resistant in that genus (`unspeciated_as`),
#  so nothing is ever more permissive than the worst case, and it adds the
#  cautions that only matter because the species is unknown. The Gram-level
#  entries assume nothing genus-specific at all.
# ════════════════════════════════════════════════════════════════════════════
import copy as _copy

UNSPECIATED_AS = {
    "Acinetobacter spp.":  "Acinetobacter baumannii",
    "Pseudomonas spp.":    "Pseudomonas aeruginosa",
    "Enterobacter spp.":   "Enterobacter cloacae",
    "Citrobacter spp.":    "Citrobacter freundii",
    "Proteus spp.":        "Proteus mirabilis",
    "Serratia spp.":       "Serratia marcescens",
    "Enterococcus spp.":   "Enterococcus faecalis",
    "Staphylococcus spp.": "Staphylococcus aureus",
}

_UNSPECIATED_NOTES = {
    "Acinetobacter spp.": (
        "🔬 **Acinetobacter غير محدد النوع** — يُعامل كـ *A. baumannii-calcoaceticus complex* "
        "(الأشيع والأكثر مقاومة) إلى أن يُحدَّد النوع. الأنواع خارج المركّب (A. lwoffii، "
        "A. junii، A. haemolyticus) أقل مقاومة وكثيراً ما تكون استعماراً أو تلوثاً. "
        "Sulbactam-durlobactam معتمد لمركّب baumannii-calcoaceticus فقط."),
    "Pseudomonas spp.": (
        "🔬 **Pseudomonas غير محدد النوع** — يُعامل كـ *P. aeruginosa* احتياطاً. الأنواع الأخرى "
        "(P. putida، P. fluorescens، P. stutzeri) لها breakpoints مختلفة في CLSI (Other "
        "Non-Enterobacterales) وأقل شراسة — اطلب التعريف قبل الحكم على DTR/CRPA."),
    "Enterobacter spp.": (
        "🔬 **Enterobacter غير محدد النوع** — يُعامل كـ *E. cloacae complex*: AmpC كروموسومي "
        "مُحدَث (خطر متوسط — IDSA). Cefepime مفضّل في العدوى الغازية."),
    "Citrobacter spp.": (
        "🔬 **Citrobacter غير محدد النوع** — يُعامل كـ *C. freundii* (AmpC) احتياطاً. "
        "*C. koseri* لا يحمل AmpC مُحدَثاً ويمكن علاجه بالجيل الثالث — التعريف يغيّر الاختيار."),
    "Proteus spp.": (
        "🔬 **Proteus غير محدد النوع** — الخطوط كـ *P. mirabilis*، لكن الأنواع موجبة الإندول "
        "(P. vulgaris / P. penneri) مقاومة جوهرياً لـ Ampicillin والجيل الأول و Cefuroxime. "
        "اختبار الإندول يحسمها."),
    "Serratia spp.": (
        "🔬 **Serratia غير محدد النوع** — يُعامل كـ *S. marcescens* (AmpC منخفض الخطر، مقاومة "
        "جوهرية لـ Colistin و Nitrofurantoin والجيل الأول)."),
    "Enterococcus spp.": (
        "🔬 **Enterococcus غير محدد النوع** — نتيجة Ampicillin هي المفتاح: الحساس غالباً "
        "*E. faecalis*، والمقاوم غالباً *E. faecium* (وعندها Vancomycin أو Linezolid). "
        "السيفالوسبورينات و Clindamycin و TMP-SMX بلا فاعلية أياً كان النوع."),
    "Staphylococcus spp.": (
        "🔬 **Staphylococcus غير محدد النوع (اختبار التخثّر غير مذكور)** — يُعامل كـ "
        "*S. aureus* احتياطاً: في الدم والمواقع المعقمة لا يُعتبر ملوِّثاً قبل نفي S. aureus. "
        "نتيجة Oxacillin/Cefoxitin تحدد MRSA. السالب للتخثّر (CoNS) ملوِّث شائع ويُفسَّر بعدد "
        "الزجاجات ووجود أجهزة مزروعة."),
}

for _new, _ref in UNSPECIATED_AS.items():
    _row = _copy.deepcopy(ORGANISM_PROFILE[_ref])
    _row["unspeciated_as"] = _ref
    _row["note"] = _UNSPECIATED_NOTES[_new]
    ORGANISM_PROFILE[_new] = _row

# Proteus spp.: agents that are fine for P. mirabilis but intrinsically inactive
# against the indole-positive species.
_r2_notes("Proteus spp.", "caution", {
    _d: ("Proteus غير محدد النوع: لو كان موجب الإندول (P. vulgaris / P. penneri) فهذا الدواء "
         "مقاوم جوهرياً — أكّد النوع قبل الاعتماد عليه.")
    for _d in ("Ampicillin", "Amoxicillin", "Cephalexin", "Cefadroxil", "Cephradine",
               "Cefazolin", "Cefaclor", "Cefuroxime", "Cefuroxime sodium")})
# Citrobacter spp.: the 3rd-gen caution already comes with the C. freundii copy.
# Enterococcus spp.: ampicillin decides the species in practice.
_r2_notes("Enterococcus spp.", "agent_notes", {
    "Ampicillin": ("Enterococcus غير محدد النوع: Ampicillin S ← غالباً E. faecalis وهو الخيار "
                   "الأول؛ Ampicillin R ← غالباً E. faecium."),
})

ORGANISM_PROFILE.update({
    "Streptococcus spp.": {
        "first_line":  ["Penicillin", "Ampicillin", "Amoxicillin", "Ceftriaxone"],
        "second_line": ["Vancomycin", "Clindamycin", "Levofloxacin", "Linezolid"],
        "third_line":  [],
        "avoid": ["Aminoglycosides", "Ciprofloxacin", "Ceftazidime", "Cefixime",
                  "Nitrofurantoin", "Fosfomycin"],
        "urine_note": ("Streptococcus غير محدد النوع في البول: غالباً فلورا مهبلية/إحليلية. "
                       "في الحامل استبعد Group B (S. agalactiae)."),
        "specimen_context": {
            "Blood":      "🔴 Streptococcus في الدم — عرّف النوع: pneumococcus / beta-haemolytic / "
                          "viridans (endocarditis) / anginosus (خراج).",
            "Sputum":     "🔬 قد يكون S. pneumoniae أو فلورا فموية — optochin / bile solubility.",
            "CSF":        "🔴 عامِل كـ S. pneumoniae حتى التعريف (breakpoints التهاب السحايا).",
            "Wound Swab": "🔬 beta-haemolytic ممرض؛ viridans غالباً فلورا.",
            "Pus":        "🔬 مجموعة anginosus تسبب الخراجات — غالباً حساسة للبنسلين.",
            "Urine":      "🔬 غالباً تلوث — استبعد GBS في الحامل.",
        },
        "note": ("🔬 **Streptococcus غير محدد النوع** (يشمل مجموعة viridans). البنسلين/"
                 "Ceftriaxone أساس العلاج، لكن مقاومة البنسلين موجودة في viridans و "
                 "S. pneumoniae — اعتمد على الـ MIC في العدوى الغازية. الأمينوجليكوزيد منفرداً "
                 "غير فعّال (يُضاف للتآزر فقط في endocarditis)."),
    },
    "Gram-negative bacilli (unidentified)": {
        "first_line":  ["Ceftriaxone", "Piperacillin + Tazobactam", "Ciprofloxacin"],
        "second_line": ["Cefepime", "Amikacin", "Meropenem"],
        "third_line":  [],
        "avoid": [],
        "urine_note": ("عصيات سالبة الجرام غير معرّفة: قد تكون Enterobacterales أو non-fermenter "
                       "(Pseudomonas / Acinetobacter). لا تُفترض مقاومة جوهرية ولا تُستنتج آلية "
                       "(ESBL/AmpC) قبل التعريف."),
        "specimen_context": {
            "Blood":      "🔴 GNB في الدم = ممرض حقيقي دائماً — اطلب ID + MIC عاجل.",
            "Urine":      "🔬 افصل ABU عن UTI بالأعراض + العدّ.",
            "Sputum":     "⚠️ قيّم جودة العينة — استعمار مجرى الهواء شائع.",
            "CSF":        "🔴 التهاب سحايا بـ GNB — Meropenem أو Ceftriaxone/Ceftazidime حتى التعريف.",
            "Wound Swab": "🔬 افصل الاستعمار عن العدوى بالعلامات السريرية.",
            "Pus":        "🔬 شائع في خراجات البطن — غالباً مع لاهوائيات.",
        },
        "note": ("🔬 **عصيات سالبة الجرام غير معرّفة**. لا جنس معروف ← لا مقاومة جوهرية مفترضة "
                 "ولا استنتاج ESBL/AmpC/Carbapenemase من اللوحة. العلاج بنتيجة الحساسية، والتعريف "
                 "(oxidase + lactose كحد أدنى) يغيّر التفسير: oxidase موجب = non-fermenter."),
    },
    "Non-fermenting Gram-negative bacilli (unspeciated)": {
        "first_line":  ["Ceftazidime", "Cefepime", "Piperacillin + Tazobactam"],
        "second_line": ["Meropenem", "Ciprofloxacin", "Levofloxacin", "Amikacin",
                        "Trimethoprim/Sulfamethoxazole"],
        "third_line":  ["Colistin"],
        "avoid": ["Ertapenem", "Nitrofurantoin", "Cephalexin", "Cefuroxime", "Ceftriaxone"],
        "urine_note": ("Non-fermenter غير محدد النوع: غالباً مكتسب من المستشفى أو مع قسطرة — "
                       "الاستعمار شائع، عالِج فقط مع أعراض."),
        "specimen_context": {
            "Blood":      "🔴 Non-fermenter في الدم — ابحث عن قسطرة مركزية كمصدر؛ ID عاجل.",
            "Sputum":     "⚠️ استعمار شائع في مرضى التنفس الصناعي — VAP يُشخَّص سريرياً وبالأشعة.",
            "Urine":      "🔬 غالباً مع قسطرة — افصل الاستعمار عن العدوى.",
            "Wound Swab": "🔬 مستعمِر شائع للحروق والجروح المزمنة.",
            "Pus":        "🔬 قيّم مع الصورة السريرية.",
        },
        "note": ("🔬 **Non-fermenter غير محدد النوع** (Pseudomonas / Acinetobacter / "
                 "Stenotrophomonas / Burkholderia). الفروق بينها كبيرة: Stenotrophomonas مقاوم "
                 "جوهرياً للكاربابينيم، و Acinetobacter لـ Aztreonam، و Pseudomonas لـ TMP-SMX — "
                 "لذلك لا يُعتمد على نتيجة S لهذه الأدوية قبل التعريف."),
        "caution": {
            "Meropenem": "Non-fermenter غير معرّف: Stenotrophomonas مقاوم جوهرياً للكاربابينيم — أكّد النوع.",
            "Imipenem/Cilastatin": "Non-fermenter غير معرّف: Stenotrophomonas مقاوم جوهرياً للكاربابينيم — أكّد النوع.",
            "Trimethoprim/Sulfamethoxazole": "Non-fermenter غير معرّف: Pseudomonas مقاوم جوهرياً لـ TMP-SMX — أكّد النوع.",
            "Aztreonam": "Non-fermenter غير معرّف: Acinetobacter و Stenotrophomonas مقاومان جوهرياً لـ Aztreonam — أكّد النوع.",
        },
    },
    "Gram-positive cocci (unidentified)": {
        "first_line":  ["Vancomycin"],
        "second_line": ["Linezolid", "Daptomycin", "Teicoplanin"],
        "third_line":  [],
        "avoid": [],
        "urine_note": ("مكورات موجبة الجرام غير معرّفة في البول: Enterococcus أو "
                       "S. saprophyticus أو تلوث بفلورا الجلد — التعريف مطلوب."),
        "specimen_context": {
            "Blood":      "🔴 قبل التعريف عامِلها كـ S. aureus محتملة في المريض غير المستقر "
                          "(clusters = staph، chains = strep/enterococcus).",
            "CSF":        "🔴 Vancomycin + Ceftriaxone حتى التعريف.",
            "Urine":      "🔬 Enterococcus / S. saprophyticus / تلوث.",
            "Wound Swab": "🔬 S. aureus و beta-haemolytic strep ممرضان؛ CoNS غالباً استعمار.",
            "Pus":        "🔬 غالباً S. aureus — الصرف أساس العلاج.",
            "Sputum":     "🔬 pneumococcus أو S. aureus أو فلورا فموية.",
        },
        "note": ("🔬 **مكورات موجبة الجرام غير معرّفة**. Vancomycin يغطي المكورات العنقودية "
                 "(ومنها MRSA) والعقدية والمعوية الحساسة إلى أن يظهر التعريف؛ بعده انزل لأضيق "
                 "دواء (Cefazolin/Oxacillin لـ MSSA، Penicillin للعقديات، Ampicillin لـ "
                 "E. faecalis)."),
    },
})
for _n in ("Streptococcus spp.", "Gram-negative bacilli (unidentified)",
           "Non-fermenting Gram-negative bacilli (unspeciated)",
           "Gram-positive cocci (unidentified)"):
    ORGANISM_PROFILE[_n]["unspeciated_as"] = None
