# Orange Lab Microbiology CDSS — سجل المراجعة والتثبيت
### Audit & Hardening Log — commercial build (`streamlit_app.py`)

**تاريخ المراجعة:** 2026-07-22 · **الإصدار المرجعي:** EUCAST v16.1/16.1 · CLSI M100 Ed36 · IDSA AMR v4.0 (2024) · WHO AWaRe 2025 · WHO BPPL 2024

**الحجم:** 7 ملفات جديدة · 15 ملف معدّل · 1,024 سطر متغيّر

---

## ١. أخطاء تؤثر على المريض مباشرة (Patient-safety defects)

دي الأخطاء اللي كانت ممكن تغيّر قرار علاجي. كل واحدة موثّقة بمصدرها.

### 1.1 — Doxycycline كان بيتعرض كخيار فعّال لـ Acinetobacter ⛔
- **الحالة:** جدول الـ intrinsic مكانش فيه أي تتراسيكلين لـ Acinetobacter.
- **المصدر:** EUCAST v3.3 Table 2 fn.2 — *"Acinetobacter is intrinsically resistant to tetracycline and doxycycline but not to minocycline and tigecycline."*
- **الأثر:** توجيه لعلاج فاشل — أخطر من منع دوا شغّال.
- **الإصلاح:** Tetracycline + Doxycycline → IR. إضافة **Minocycline** للقائمة (مكانش موجود أصلاً، وهو الدوا الوحيد اللي بيشتغل).

### 1.2 — Cephalosporins كانت بتتشال من عزلات CRPA حسّاسة ⛔
- **الحالة:** أي كائن بكاربابينيمين R كان بياخد `carbapenemase 92%`، واللي بيفعّل `_is_carbapenemase` فيبنّ كل بنسلين وسيفالوسبورين **حتى لو S**.
- **المصدر:** IDSA AMR v4.0 — العزلة المقاومة للكاربابينيم والحسّاسة لبيتا-لاكتام تقليدي تُعالَج بذلك الدوا بجرعة عالية وتسريب ممتد، مش بالكوليستين.
- **الأثر:** عزلة سودوموناس بـ Ceftazidime-S + Cefepime-S + Pip-Tazo-S كانت بتخرج بـ **Amikacin و Colistin بس**.
- **الإصلاح:** مسار `crpa` منفصل (ثقة 45–60%) + تصنيف `DTR` بتعريف IDSA. الـ Enterobacterales ما اتغيرتش.

### 1.3 — Amoxicillin-Clavulanate كان بيتفلج IR بدل Ampicillin-Sulbactam ⛔
- **الحالة:** `extract_detected_drugs` كان بيطابق بالاحتواء الخام، فكل مضاد مركّب بيولّد أدوية وهمية:
  `Ampicillin/Sulbactam` → `Ampicillin` · `Amoxicillin + Clavulanic acid` → `Amoxicillin` · `Levofloxacin` → `Ofloxacin`
- **الأثر:** الأدوية الوهمية دي intrinsic لـ Acinetobacter فبتظهر تحذيرات لأدوية **متعملهاش اختبار أصلاً**.
- **الإصلاح:** scanner سطر-بسطر، الاسم الأطول أولاً مع حجز الـ span.

### 1.4 — Tigecycline ممنوع و Tetracycline/Doxycycline معروضين لـ Serratia ⛔
- **المصدر:** EUCAST v3.3 Table 2 fn.5 — نفس صياغة حاشية Acinetobacter.
- **الحالة:** الكود كان **مقلوب تماماً**.

### 1.5 — Amox-clav معفي من قاعدة Acinetobacter
- **الحالة:** `"clav"` كانت في `exclude` — الكلافولانيت مالوش أي فاعلية هنا؛ السولباكتام هو الاستثناء الوحيد.

---

## ٢. تناقضات بين المحركات (Engine disagreements)

### 2.1 — `ast_qa_engine` كان **ميت** بالكامل للسالب جرام
- بيعمل `from clinical_data import INTRINSIC_RESISTANCE` وملف `clinical_data.py` **مش موجود في الريبو**. الـ `except` بيرجّعه `{}` → فحص Level-1 معطّل لكل الـ Gram-negatives، وبيفحص MRSA و Mycoplasma بس.
- **الإصلاح:** إنشاء `clinical_data.py` كمصدر وحيد + `Guard 0` بيفشل الـ build لو الملف ناقص.

### 2.2 — الجداول الثلاثة كانت مختلفة
`streamlit_app` · `ast_reportability` · `ast_qa_engine` — كل واحد بجدول مختلف. اتوحّدوا، و`test_intrinsic_sync.py` بيفشل لو رجعوا يختلفوا.

### 2.3 — تكرار مرئي في الشاشة
البانلين بيعرضوا نفس النتيجة. `skip_categories` بيمنع التكرار.

### 2.4 — `not_organisms` كانت **بلا أي مفعول**
الـ evaluator في `AST_QC_RULES` مكانش بيقراها خالص — أي استثناء تكتبه كان بيتجاهَل. اتوصّلت، و QC003 بقى بيستثني الكائنات المقاومة جوهرياً للكوليستين.

---

## ٣. قواعد ناقصة تماماً (Missing rules)

| القاعدة | المصدر | الحالة قبل |
|---|---|---|
| `nobp_imipenem_proteae` | EUCAST v16.1 note 2 | مفيش — `Imipenem S` على Proteus كان بيعدّي |
| `intr_strep_enterococcus_aminoglycosides` | EUCAST Table 4 + CLSI HLAR | مفيش — `Gentamicin S` على Enterococcus كان بيعدّي |
| `intr_citrobacter_koseri_klebsiella_oxytoca_classA` | EUCAST v3.3 Table 2 | *C. koseri* مكانش عليه أي قاعدة |
| `intr_nonfermenter_narrow_spectrum` | EUCAST v3.3 Table 3 header | كانت "no breakpoints" الأضعف |
| Serratia في `nobp_tigecycline_proteae` | EUCAST v16.1 note 3/A | ناقصة |

---

## ٤. أخطاء برمجية (Code defects)

- `data/antibiotics.py` — `re.sub` بدون `import re` → NameError
- `modules/qc.py` — `AST_QC_RULES` غير معرّف → NameError
- ~~`fuzzy_match` بيرجّع 100.0 لمجرد الاحتواء~~ **متصلّح** (مراجعة 2026-07): الاحتواء بقى بيرجّع درجة متناسبة مع طول التطابق، مش 100.0 ثابتة.
- 132 استشهاد مبهم أو غلط اتصلّحوا (`IDSA AMR 2025` → `v4.0 (2024)` · `EUCAST 2026` → `Breakpoint Tables v16.1` · `CLSI M100 2026` → `Ed36`)

---

## ٥. البنية اللي اتبنت للتحقق

### الملفات الجديدة
| الملف | الوظيفة |
|---|---|
| `clinical_data.py` | مصدر وحيد للـ intrinsic (50 صف) |
| `guideline_registry.py` | 50 قاعدة × مصدر مؤرَّخ + لينك + مين راجع وامتى |
| `scenario_matrix.py` | مولّد 1,344 سيناريو |
| `test_scenarios.py` | 13 invariant + golden snapshot |
| `test_intrinsic_sync.py` | 86 تست للجداول والـ OCR |
| `test_guidelines.py` | تتبّع الاستشهادات |
| `scenario_snapshot.json` | البصمة المرجعية |

### الـ 13 invariant
1. دوا واحد في bucket واحد · 2. intrinsic ما يوصلش Allowed · 3. R ما يتوصّاش · 4. مفيش أدوية وهمية · 5. PDR يعني مفيش S · 6. ESBL للـ Enterobacterales بس · 7. لوحة رفيعة ما تدّعيش XDR · 8. السودوموناس مش carbapenemase · 9. انتهاك intrinsic يتفلج · 10. دوا بولي برّه البول يتفلج · 11. wild-type عنده خيارات · 12–13. صياغة سليمة

---

## ٦. إزاي تتحقق إن البرنامج سليم

```bash
python test_intrinsic_invariant.py    # انحراف الجداول
python test_intrinsic_sync.py         # 86 تست
python test_scenarios.py              # 1,344 سيناريو
python test_guidelines.py             # تتبّع المصادر
python test_guidelines.py --queue     # اللي لسه محتاج مراجعة
N_FUZZ=20000 python test_comprehensive.py
python -m compileall -q .
```

الـ CI (`.github/workflows/cdss-tests.yml`) بيشغّل السبعة على كل push.

**لو `test_scenarios.py` قال `SNAPSHOT: N case(s) changed`:**
1. `python test_scenarios.py --verbose` واقرا الفرق
2. اسأل: التغيير ده مقصود؟
3. لو أيوة: `python test_scenarios.py --update`

⚠️ **snapshot محدش بيقراه بيبقى ديكور مش شبكة أمان.**

---

## ٧. الحالة النهائية

```
Guard 0  clinical_data موجود          ✅  50 صف
Guard 1  انحراف الجداول                ✅
Guard 2  التزامن + OCR                ✅  86 passed
Guard 3  مصفوفة السيناريوهات           ✅  1,344 × 15 invariant
Guard 4  تتبّع الـ Guidelines           ✅  50 قاعدة
Guard 5  الشامل                       ✅  N=20000
Guard 6  compileall                   ✅
fuzz                                  ✅  8000 حالة، صفر أخطاء
```

**تتبّع القواعد:** 20 من نص المصدر · 11 من مصدر ثانوي · **5 لسه غير متحقَّق منها**

---

## ٨. اللي لسه مفتوح

### ٨.١ — 5 قواعد غير متحقَّق منها
| القاعدة | ليه |
|---|---|
| `QC003` / `QC004` | heuristics معقولة، مش قواعد منشورة |
| `QC005` | CLSI Table 2C وراء paywall |
| `nobp_cefoperazone` | إثبات **غياب** — غياب الدليل مش دليل الغياب |
| `nobp_nonfermenter_narrow_spectrum` | الجزء المؤكد اتنقل لقاعدة intrinsic؛ الباقي لأ |

### ٨.٢ — قاعدة محتاجة الـ PDF الأصلي
`intr_listeria_cephalosporins` — الحقيقة الإكلينيكية مش محل شك، لكن صف EUCAST 4.11 فيه علامتين R ومحاذاة الأعمدة مش واضحة من النص المسطّح.

### ٨.٣ — **31 قاعدة مستنية توقيع إكلينيكي**
`countersigned_by` فاضي في كل الصفوف. المراجعة اتعملت بمساعدة AI من مصادر منشورة — **مش نفس حاجة طبيب بيقرا المعيار ويتحمّل المسؤولية.**

### ٨.٤ — أخطاء معروفة لم تُصلَح
- ~~`fuzzy_match` بيرجّع 100.0 للاحتواء → عتبة 82 بلا معنى~~ **متصلّح**
- الـ multiselect اليدوي مش بيمرّ على `_hide_urine_only`
- `modules/` + `data/` + `ui/` شجرة ميتة — الأب مش بيستوردها (يُفضَّل حذفها)

### ٨.٥ — قرارات مؤجلة
- **OCR:** `image_to_string` بيرمي معلومات الموقع → التقارير المجمّعة (Sensitive/Resistant كأعمدة) بتطلّع `sir_map` **فاضي**. الحل: `image_to_data` + ترسية على العناوين + شاشة تأكيد إجبارية.
- **P. aeruginosa wild-type** المفروض يتقرا `I` مش `S` حسب EUCAST 2019+
- **أدوية جديدة** (Cefiderocol · Sulbactam-durlobactam · Ceftazidime-avibactam) — مش متاحة عملياً في مصر
- **XDR/PDR** المفروض يتحجبوا لو لوحة Magiorakos الدنيا مش متختبرة

---

## ٩. ملاحظة على منهج المراجعة

النظام ده بيقدر يثبت إن **الكود مطابق للجداول**. مش بيقدر يثبت إن **الجداول مطابقة لـ EUCAST v16** — دي محتاجة إنسان يفتح الـ PDF.

`guideline_registry.py` بيخلّي المراجعة دي **منظّمة وموثّقة وقابلة للانتهاء** (18 شهر) — بس مش بيلغيها.

---
---

# مراجعة يوليو ٢٠٢٦ — الجولة الثانية (Opus 5)

**تاريخ:** 2026-07-25 · **النطاق:** النسخة التجارية `streamlit_app.py` وكل الملفات المرتبطة (19,366 سطر / 24 ملف)

**المنهج:** لم تكن مراجعة بالقراءة. تم بناء harness يستخرج دوال القرار من الـ monolith عبر AST ويشغّلها خارج Streamlit، ثم اشتُقّت «حقيقة مرجعية» مستقلة من جداول البيانات وقورنت بما يُخرجه المحرك فعلياً على كامل الفضاء (7 عينات × 20 كائن × 51 دواء × حالات المريض). كل خلاف = عيب.

**النتيجة الأولية:** **602 انتهاك للثوابت** → **0** بعد الإصلاح.

---

## ١. تسريب موانع الحمل عبر مسار الفشل الكلوي ⛔⛔ (الأخطر)

- **الحالة:** في `analyze_antibiotics` كان بلوك تعديل الجرعة الكلوية يسبق بلوك الحمل، وينتهي بـ `continue`. أي دواء `renal_limit` الخاص به ≥ CrCl المريضة كان يخرج من الحلقة **قبل تنفيذ فحص الحمل إطلاقاً**.
- **الأثر السريري:** حامل + CrCl 55 → **Gentamicin / Amikacin / Tobramycin** تظهر في «استخدم بحذر — تعديل جرعة» بدلاً من **ممنوع**. عند CrCl ≤ 40 يُضاف Gatifloxacin، وعند CrCl ≤ 30 يُضاف Clarithromycin و TMP-SMX. الأمينوغليكوزيدات = سمية أذن جنينية وفقدان سمع دائم (FDA Category D · ACOG 2023).
- **لماذا لم يُكتشف:** يتطلب تزامن شرطين (`is_renal` مفعّل **و** CrCl ≤ الحد الخاص بذلك الدواء تحديداً)، فهو متقطّع وغير قابل للملاحظة بالاختبار اليدوي.
- **الحجم:** 560 خلية مسرِّبة عبر الفضاء.
- **الإصلاح:** إعادة ترتيب البوابات — كل مانع مطلق (طفل، حمل، كلوي حاد، كبدي) يُحسم قبل أي فرع تحذيري ينهي الحلقة. أُضيف تعليق يشرح أن الترتيب حامل للمعنى ولا يجوز عكسه.
- **الحارس:** `test_safety_invariants.py` [1] — وقد جرى التحقق بـ mutation test: إعادة العيب تُفشِل الاختبار.

## ٢. الطبقة الكبدية كانت شكلية بالكامل ⛔

- **الحالة:** `HEPATIC_DOSING` يحمل أحكام `"Avoid"` صريحة لـ Child-Pugh C، لكن `get_hepatic_recommendations()` كانت **تُعلّق فقط** على قائمة المسموح ولا تحذف منها. كما أن `analyze_antibiotics` لم تكن تستقبل درجة Child-Pugh أصلاً (بارامتر `is_hepatic: bool` فقط) — أي أن المنع كان مستحيلاً معمارياً.
- **الأثر:** مريض تليّف كبدي متقدّم يتلقى ضمن «موصى به»: Amoxicillin-Clavulanate (DILI) · Nitrofurantoin (التهاب كبد ركودي) · Doxycycline · Azithromycin · Clarithromycin · Clindamycin · Chloramphenicol · TMP-SMX.
- **الإصلاح:** أُضيف `child_pugh` إلى توقيع الدالة بقيمة افتراضية `"C"` (أسوأ درجة — fail-closed، فالمحرك لا يفترض مرضاً كبدياً خفيفاً عند الجهل)، ويُنفَّذ الحكم عند نقطة القرار. نُقل `HEPATIC_DOSING` أعلى مستهلكه الوحيد ليصبح الاعتماد صريحاً بدلاً من الاتكال على ترتيب تنفيذ الوحدة.
- **ثغرة تغطية مصاحبة:** 9 أدوية معلّمة `hepatic_caution=True` بلا أي صف في الجدول — **Fusidic acid** (يرقان معتمد على الجرعة) · **Moxifloxacin** (ممنوع في Child-Pugh C بنشرة EMA/FDA) · **Tetracycline** (تنكّس دهني كبدي قاتل) · **Cefoperazone ± Sulbactam** (نقص بروثرومبين ونزيف) · Minocycline · Tinidazole · Gatifloxacin · Oxacillin · Tobramycin. أُضيفت جميعها بمراجعها.
- **الحارس:** `test_safety_invariants.py` [2]

## ٣. خريطة الأمان كانت مكتوبة ومختبرة وغير موصولة ⛔⛔

- **الحالة:** `clinical_matrix.py` (955 سطر · 51 دواء × 7 مواقع = 357 خلية) و `safety_gate.py` (219 سطر · بوابة demote-only) و `test_clinical_matrix.py` (33 إثبات، كلها تمر) — موجودة في المستودع، و`streamlit_app.py` **لا يستوردها إطلاقاً**. الطبقة بأكملها كانت كوداً ميتاً.
- **الأثر:** الطبقة الغائبة هي **نفاذية الموقع**. بدونها كان المحرك يضع في قائمة «موصى به» لعينة **CSF**: `Cefazolin` · `Cephalexin` · `Clindamycin` · `Azithromycin` · `Ertapenem` — ولا واحد منها يعبر الحاجز الدموي الدماغي بتركيز علاجي. خطأ مميت في التهاب السحايا البكتيري.
- **الإصلاح:** وُصلت البوابة في مسار القرار الحي بعد `analyze_antibiotics` مباشرة، وأُعلنت **critical** في `_MODULE_HEALTH` (غيابها يوقف التقرير بدل أن يمر صامتاً)، مع expander يعرض كل دواء أُعيد تصنيفه وسببه. البوابة **demote-only** بنيوياً: تشدّد ولا تخفّف، فأسوأ ما يفعله خطأ فيها هو زيادة التحفّظ.
- **الحارس:** `test_safety_invariants.py` [6] + **Guard 8** في CI (فحص بنيوي يفشل البناء إذا استُورد الملف ولم يُستدعَ).

## ٤. ثلاثة مصنّفات مختلفة لسؤال «هل هذه عينة بول؟» ⚠️

- **الحالة:** فرع ESBL يسأل `classify_specimen()`، وفلتر أدوية البول يسأل `"urine" in text`، و`_hide_urine_only()` يسأل سؤالاً ثالثاً.
- **الأثر:** لعينة `MSU` أو `Midstream` أو `Catheter specimen` يقول الأول «بول» ويقول الآخران «ليست بولاً» → **Nitrofurantoin و Fosfomycin يُمنعان من عينة بول حقيقية** بحجة «غير مناسبين للعينة»، أي فقدان أفضل خيارين فمويين موجّهين لالتهاب مسالك بسيط.
- **الإصلاح:** توحيد الثلاثة على `classify_specimen()`.
- **الحارس:** `test_safety_invariants.py` [3]

## ٥. تناقض داخلي في منطق الكاربابينيميز غير المؤكد ⚠️

- **الحالة:** على مزرعة دم باشتباه كاربابينيميز غير مؤكد (Ertapenem-R منفرد): سيفالوسبورين حسّاس → **تحذير**، بينما Piperacillin-Tazobactam حسّاس → **منع**. السبب: `_is_possible_carb` كان مضموماً بـ OR إلى فرع الـ BLI المخصص للحالات المؤكدة.
- **لماذا هو معكوس:** Pip-Tazo أمتن من السيفالوسبورين ضد نمط فقد البورين + AmpC، وهو التفسير الحميد الأشيع لمقاومة إرتابينيم المعزولة.
- **الإصلاح:** توحيد المعاملة، مع جعل التحذير حسب الموقع: تحذير مشدّد صريح («لا تستخدمه كعلاج نهائي منفرد») في العينات الجهازية مع الإشارة إلى MERINO 2018، وتحذير عادي في البول. الحالات **المؤكدة** (ESBL / carbapenemase) تحتفظ بالمنع خارج البول.
- **الأثر على اللقطة المرجعية:** 24 سيناريو تغيّر، جميعها من طراز `oxa48_like`. رُوجعت وحُدِّثت (digest `7d918116b7e0c047`).
- **الحارس:** `test_safety_invariants.py` [4]

## ٦. تتراسيكلين في سن ٨–١٧ يسقط على رسالة بلا سبب ⚠️

- **الحالة:** شرط `"tetracycline" in cls and age < 8` جعل أي تتراسيكلين لطفل ٨–١٧ يسقط على الرسالة العامة «غير مفضل للأطفال» بلا أي مبرر.
- **الأثر:** ضياع مبرر التصبغ السني/ترسّب العظام، وضياع أن **AAP Red Book 2024** و CLSI يقبلان دورات Doxycycline القصيرة (< 21 يوماً) في أي سن.
- **الإصلاح:** رسالة صحيحة في كل الأعمار مع إضافة ملاحظة AAP لمن هم فوق ٨.
- **الحارس:** `test_safety_invariants.py` [5]

## ٧. عيوب بنيوية تختبئ من المراجعة لا من الاختبار

- **مفاتيح مكرّرة:** `guideline_registry.py:218` — أربعة مفاتيح تدقيق (`verified` / `checked_by` / `checked_on` / `countersigned_by`) مكرّرة في نفس الـ dict. Python يحتفظ بالأخير صامتاً، فمراجع يعدّل النسخة الأولى لا يرى أثراً ولا خطأ. أُزيل التكرار وأُضيف فحص شامل للمستودع.
- **انجراف التسمية:** `Ampicillin + Sulbactam` في `clinical_data.py` مقابل `Ampicillin/Sulbactam` في `abx_guidelines.py`. يُعوَّض حالياً بالصدفة عبر `ORGANISM_PROFILE`، لكنها هشاشة حقيقية — أي تعديل على قائمة الـ avoid يكشفها.

---

## ما تغيّر — ملخص

| الملف | التغيير |
|---|---|
| `streamlit_app.py` | ترتيب البوابات · إنفاذ الكبد + `child_pugh` · نقل `HEPATIC_DOSING` · 9 صفوف كبدية جديدة · توحيد مصنّف العينة · تماثل الكاربابينيميز · رسالة التتراسيكلين · **وصل البوابة الآمنة** · صحة الوحدات |
| `guideline_registry.py` | إزالة المفاتيح المكرّرة |
| `test_safety_invariants.py` | **جديد** — 28 إثبات انحدار، كل واحد يسمّي العيب الذي يحرسه |
| `.github/workflows/cdss-tests.yml` | Guards 6/7/8 — إثباتات الخريطة، شبكة الانحدار، وفحص بنيوي أن البوابة موصولة فعلاً |
| `scenario_snapshot.json` | حُدِّث بعد مراجعة الـ 24 حالة |

**حالة الاختبارات:** 7 حزم · كلها خضراء · `compileall` نظيف · 0 انتهاك للثوابت.

---

## ⚠️ حد هذه المراجعة — يجب ألا يُساء فهمه

كل ما سبق يثبت أن **الكود مطابق للجداول**. لا يثبت أن **الجداول مطابقة لـ EUCAST v16 / CLSI M100 Ed36** — وهذا يحتاج إنساناً والـ PDF مفتوح أمامه.

`guideline_registry.py` يقول حالياً: **33 قاعدة روجعت مقابل المصدر · 5 لم تُراجَع بعد · 33 تنتظر توقيع طبيب**. خانة `countersigned_by` فارغة في جميعها.

هذه ليست تفصيلة إدارية. هي الفرق بين «متسق» و«صحيح»، وفي منتج تجاري يُباع لمعامل أخرى فهي أيضاً مسؤولية قانونية. لتشغيل قائمة المراجعة: `python test_guidelines.py --queue`


---

# مراجعة 2026-07-27 — تصحيحات على هذا الملف

راجع `CHANGELOG-review.md` للتفاصيل الكاملة. ثلاث نقاط في هذا المستند كانت غير دقيقة:

1. **`fuzzy_match`** مذكور كـ «لسه مفتوح» في موضعين — **متصلّح فعلاً**، والبند اتشطب أعلاه.

2. **`data/antibiotics.py` ناقصه `import re`** — كان مسجَّلاً كعيب معروف وفضل مفتوح. النتيجة إن **6 modules** في شجرة `modules/` و `ui/` كانت بتفشل عند الـ import، والـ CI مكانش بيمسكها لأن `compileall` بيـ parse ومش بيـ execute. اتصلّح، واتضاف **Guard 9** بيعمل import حقيقي لكل module.

3. **ESBL و MDR** — الملف والتعليق في `MDR_CATEGORIES` بيقولوا إن ESBL *E. coli* المفروض تُحسب فئة واحدة وترجع **NOT MDR**. ده **غير صحيح**، والكود هو الصح: Magiorakos Table 3 بيعُدّ Penicillins و Penicillins+BLI و Non-extended ceph و Extended ceph **أربع فئات منفصلة**، فالـ ESBL بتوصل 4 = MDR — وده كمان اللي عليه الأدبيات. التعليق اتصحّح في الكود عشان مايتحوّلش لفخ صيانة.

---

_الأرقام أعلاه محدَّثة بتاريخ 2026-08-06 مقابل الكود نفسه: **60 دواء · 30 كائن قابل للاختيار · 50 صف مقاومة جوهرية · 50 استشهاد مُوقَّع · 1,267 حالة في الـ snapshot**. `test_clinical_facts.py` بيفشل لو أي رقم منهم اتغيّر من غير تحديث._

---

# مراجعة 2026-08-21 — Panel Completeness + عيب حقيقي في مسار الـ UI

بعد إضافة `ast_panel_completeness.py` (AST Panel Completeness QC)، عملت مراجعة إضافية بمراجعة ثانية مستقلة، وأعدت فحصها بنفسي بدل التصديق عليها مباشرة. النتيجة: نقطة واحدة كانت false positive من أداة الفحص نفسها، ونقطتان كانتا حقيقيتين وأخطر مما ذُكر.

## ⛔ 1) عيب حقيقي — `get_combination_therapy()` بدون `organism=` في مسار الـ UI/PDF الفعلي

- **الحالة:** الدالة نفسها فيها منطق (موجود من 2026-08-06) بيعلّم أي combination option يحتوي دواء الكائن مقاوم له جوهرياً (مثال موثّق في الكود: Colistin لـ Proteus/Providencia/Morganella/Serratia). لكن نداءي الـ UI (شريط Combination Therapy) ونداء الـ PDF export كانا بينادوا الدالة **من غير** `organism=` — يعني المنطق ده كان بيتخطّى صامتاً على الشاشة اللي الطبيب فعلاً بيشوفها، رغم إن `run_analysis()` (اللي كل الاختبارات القديمة بتمر منه) بينادي الدالة صح.
- **ليه محدش مسكه:** كل الاختبارات القديمة كانت بتستدعي `run_analysis()` مباشرة أو `get_combination_therapy()` بمعاملات صحيحة — محدش كان بيمشي في المسار الحرفي اللي الـ UI بيمشي فيه.
- **الإصلاح:** إضافة `organism=organism_type` في الاستدعاءين (سطر الـ UI expander وسطر الـ PDF).
- **الحارس الجديد:** `test_ui_combination_path.py` — فحص ثابت (static، عبر AST) يتأكد إن كل استدعاء حقيقي لـ `get_combination_therapy(` بيمرّر `organism=`، بالإضافة لسيناريو ديناميكي حقيقي (Proteus/Providencia/Morganella/Serratia + Colistin) يتأكد إن العلامة فعلاً بتظهر. **Guard 12** في الـ CI.

## 🟡 2) القواعد العشرة الجديدة لـ Panel Completeness — تقوية الاستناد العلمي

بناءً على طلب صريح إن اختيار المضادات المتوقعة يبقى مستند لمصادر علمية حقيقية، تم:
- التحقق من 6 من أصل 10 مجموعات كائنات مقابل جداول CLSI M100 Ed36 (36th ed., 2026) الفعلية عبر تجميع ثانوي (LaboratoryTests.org، فبراير–مارس 2026)، ورفعها من `verified="pending"` إلى `verified="secondary"` في `guideline_registry.py`.
- تصحيح حقيقي وجدته المراجعة: قائمة Acinetobacter الأصلية كانت حاطة Ampicillin/Sulbactam + Amikacin + TMP-SMX كـ"أساسي" فقط — لكن الجدول الفعلي لـ Ed36 بيحط Cefepime/Ceftazidime/Ciprofloxacin/Gentamicin كـTier 1 (روتيني)، وMeropenem/Imipenem كـTier 2. اتصحّحت.
- تصحيح ثاني: Minocycline لـ Stenotrophomonas maltophilia كان في القائمة "التكميلية" — مصدر CLSI مباشر (AST News Update) بيأكد إنه Tier 1. اتصحّحت.
- الأربع مجموعات الباقية (Stenotrophomonas بالكامل، S. pneumoniae، Beta-hemolytic Strep، H. influenzae) لسه `pending` — مش لأن حد ما حاولش، لكن لأنها ما اتفحصتش مقابل نفس المصدر المباشر.
- **لسه محتاج توقيع د. طارق.** رفع مستوى `verified` من "pending" لـ"secondary" مش نفس معنى "موقّع" — دلوقتي `test_guidelines.py` بيقول **6 قواعد** بقت "checked, awaiting clinician's countersignature" بدل الصمت الكامل اللي كان قبل كده.

## 🟢 3) نظافة QA infrastructure — `sys.exit()` بلا حارس في 13 ملف اختبار

فحص AST شامل (مش grep سطحي) لقى إن 13 من 14 ملف اختبار — **بما فيهم `test_panel_completeness.py` الجديد نفسه** — عندهم `sys.exit()` على مستوى الملف من غير حراسة بـ`if __name__ == "__main__":`. النتيجة: أي محاولة تشغيل `pytest` بشكل عام على المجلد كانت هتفشل في مرحلة الـ collection. الـ CI الحالي مش متأثر (بيشغّل كل حزمة كـscript مباشر)، لكن اتصلّحت الـ 13 ملف بإضافة الحراسة، مع التأكد إن exit code السكريبت **متطابق 100%** زي الأول (اتفحص بتشغيل كل حزمة وقراءة الـ exit code فعلياً، مش افتراض).

## 🟢 4) توثيق قديم — رقم "809 حالة" في تعليق الـ CI

تعليق `.github/workflows/cdss-tests.yml` عند Guard 4 كان لسه بيقول "809 cases" بينما التشغيل الفعلي لـ `test_scenarios.py` بيطلّع **1,344 سيناريو / 1,267 snapshot**. اتصحّح التعليق. (ده تعليق مش رقم بيتفحص آلياً — `test_clinical_facts.py` بيراقب أرقام README.md بس، مش تعليقات الـ workflow.)

## ما اتغيّر — ملخص

| الملف | التغيير |
|---|---|
| `streamlit_app.py` | `organism=organism_type` في نداءي الـ UI/PDF لـ `get_combination_therapy()` |
| `ast_panel_completeness.py` | إعادة بناء 6 من 10 قوائم متوقعة مقابل CLSI M100 Ed36 الفعلي؛ فلترة ديناميكية ضد `INTRINSIC_RESISTANCE` بدل استثناءات يدوية |
| `guideline_registry.py` | 6 صفوف `panel_*` اتصعّدت لـ`secondary` مع تفاصيل المصدر |
| `test_ui_combination_path.py` | **جديد** — يحرس مسار الاستدعاء الحرفي (static + dynamic) |
| 13 ملف `test_*.py` | حراسة `sys.exit()` بـ`if __name__ == "__main__":` |
| `.github/workflows/cdss-tests.yml` | Guard 12 جديد؛ تصحيح تعليق "809" |

**حالة الاختبارات:** 15 حزمة، كلها exit=0 عدا `test_safety_invariants.py` (متوقّع — منتظر توقيع د. طارق على 6 قواعد Panel Completeness).

---

# مراجعة 2026-08-22 — توقيع د. طارق + عيب حقيقي ثانٍ (بيانات قديمة في كروت QC)

## ✅ توقيع د. طارق على 6 قواعد Panel Completeness

د. طارق راجع ووافق على الـ6 قواعد اللي كانت `verified="secondary"` (Enterobacterales، Salmonella/Shigella، Pseudomonas، Acinetobacter، Staphylococcus، Enterococcus). `countersigned_by` اتحدّث في `guideline_registry.py` لكل واحدة منهم. الـ4 قواعد الباقية (Stenotrophomonas، S. pneumoniae، Beta-hemolytic Strep، H. influenzae) لسه `pending` وغير موقّعة — محدش راجعها لسه.

**النتيجة:** `test_safety_invariants.py` بقى بيفشل بس على الـ4 قواعد الباقية (كان قبل كده بيفشل على 6). ده fail متوقّع ومش عيب.

## ⛔ عيب حقيقي ثانٍ — كروت QC بتقرأ بيانات قديمة (سبق التعديل اليدوي بخطوة)

- **الحالة:** بلاغ من المستخدم (اتراجع مباشرة في الكود قبل ما يتصلّح، مش اتصدّق على طول) لقى إن "🧬 Resistance Profile" و"🔬 AST Quality Check" (وبالتبعية Panel Completeness جواها) بترندر **قبل** بلوك تعديل الـ AST اليدوي في ترتيب السكريبت. يعني لما المستخدم يضيف/يعدّل مضاد، الكروت دي بتقرأ `st.session_state.sir_map_edited` زي ما كانت آخر مرة — يعني متأخرة بخطوة واحدة عن التعديل اللي المستخدم عمله لتوه.
- **مثال حقيقي:** ضفت Piperacillin+Tazobactam لعزلة Klebsiella، وكارت Panel Completeness فضل يقول "ناقص" لحد ما تعمل تعديل تاني — مع إن كل selectbox فردي بتاع كل مضاد بيتحدّث فوراً (Streamlit بتزامن حالة الـwidgets قبل ما السكريبت يشتغل)، لكن الـdict المجمّع اللي الكروت دي بتقراه مش بيتبني إلا لاحقاً في نفس التشغيلة.
- **السبب اللي محدش مسكه قبل كده:** نفس النمط ده موجود من قبل إضافة Panel Completeness — أنا استخدمت نفس الـ`_qc_sir` الموجود مسبقاً بدل ما أكتشف المشكلة، وده وسّع نطاق التأثير (كل كروت الـQC، مش بس Panel Completeness).
- **الإصلاح:** بدل نقل ~150 سطر من widgets معقدة ومترابطة (مخاطرة حقيقية)، ضفت `if edited_sir != previous: st.session_state.sir_map_edited = edited_sir; st.rerun()` مباشرة بعد بناء الـdict النهائي — بنفس الـ`st.rerun()` idiom اللي البلوك ده أصلاً بيستخدمه لعمليات الحذف/الاستعادة. ده بيضمن rerun واحد إضافي بس لما القيمة فعلاً تتغيّر، وبيتقارب (مفيش infinite loop) لأن الكتابة بتحصل قبل الـ rerun.
- **الحارس الجديد:** `test_qc_data_freshness.py` — فحص static (عبر AST) يتأكد إن نمط "لو اتغيّر → rerun" موجود ومكانه صح بعد الكتابة مباشرة. **Guard 13** في الـ CI. (مينفعش نعمل فحص ديناميكي حقيقي هنا — streamlit نفسه مش متاح في بيئة الاختبار دي.)

## ما اتغيّر

| الملف | التغيير |
|---|---|
| `guideline_registry.py` | `countersigned_by` لـ6 قواعد Panel Completeness (توقيع د. طارق، 2026-08-22) |
| `streamlit_app.py` | rerun-on-change بعد `sir_map_edited` write-back |
| `test_qc_data_freshness.py` | **جديد** — حارس static لترتيب القراءة/الكتابة |
| `test_panel_completeness.py` | تحديث invariant التوقيع (كان "لازم فاضي دايماً"، بقى "لازم يبقى موقّع بس لو اتفحص فعلاً") |
| `.github/workflows/cdss-tests.yml` | Guard 13 جديد؛ إعادة ترقيم كامل ونظيف للحراس |

**حالة الاختبارات:** 16 حزمة، كلها exit=0 عدا `test_safety_invariants.py` (متوقّع — 4 قواعد لسه منتظرة مراجعة د. طارق).

**ملحوظة مهمة:** إصلاح `sir_map_edited` اتفحص static بس (مفيش streamlit في بيئة السحابة دي عشان نجرب rerun حقيقي). لازم click-through يدوي واحد بعد النشر: ضيف مضاد، وتأكد إن عداد Panel Completeness بيتحدّث في نفس اللحظة مش في التعديل اللي بعده.
