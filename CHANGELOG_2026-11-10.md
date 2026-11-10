# سجل التغييرات — مراجعة الإرشادات 2026-11-10

مراجعة سطر بسطر مقابل: CLSI M100 Ed33–Ed36 · EUCAST v16.1 · IDSA AMR Guidance 2026
(doi:10.1093/cid/ciag481) · IDSA cUTI 2025 · BALANCE (NEJM 2025) · ATS/IDSA HAP/VAP 2016 ·
IDSA Bacterial Meningitis · ACOG CO 717 / 797 · AAP Red Book 2024 · WHO AWaRe 2025 ·
Magiorakos 2012.

كل خطأ هنا **اتأكّد الأول** بسيناريو فشل على الكود الأصلي، وبعدين اتصلّح، وبعدين اتثبّت
باختبار في الملف الجديد `test_review_fixes.py` (94 فحص).

> ⚠️ **تحديث الجولة التانية:** صفوف الجرعات والقواعد اللي كانت مستنية توقيع اتراجعت
> مقابل النشرة/المصدر واتعتمدت **بتعليمات مالك المعمل** (`dose_owner_approved` /
> `owner_approved`). ده **مش** توقيع د. طارق ولا أي طبيب، ومكتوب كده جوه كل صف.

---

## 🔴 الأخطاء الحرجة (5)

| # | الخطأ | التصحيح |
|---|---|---|
| C1 | مع carbapenemase مؤكد، المحرك كان **يحظر** Ceftazidime-avibactam (كـ BLI/MERINO) و Meropenem-vaborbactam و Imipenem-relebactam (ككاربابينيم) و Cefiderocol (كسيفالوسبورين) — يعني الأدوية اللي اتعملت للعزلة دي بالذات | العوامل الحديثة بتتقيّم بنشاطها الفعلي حسب نوع الإنزيم: KPC ← CZA/MEV/IMR · OXA-48 ← CZA · MBL ← ATM-AVI / CZA+ATM / Cefiderocol. نوع غير معروف ← تحذير مع شرح (NDM و OXA-48 الأشيع في مصر). ملف جديد `therapy_rules.py` + اختيار نوع الإنزيم في الـ sidebar |
| C2 | AmpC كان بيعدّي على فرع ESBL، فـ Cefepime S على Enterobacter في الدم كان يتحذّر بنص ESBL | Cefepime S ← موصى به لـ AmpC (IDSA 2026)؛ SDD/I ← تحذير "احتمال ESBL مرافق — كاربابينيم" |
| C3 | Imipenem R لوحده في Proteus/Morganella/Providencia كان يطلّع CRE + عزل + "اشتباه carbapenemase" | مستبعد في `predict_esbl` و PHENOTYPE_RULES و QA level 5 و QC004 (اتقسمت QC004/QC004b) — تعريف CDC |
| C4 | نصوص جرعات غلط: Cefepime (CrCl 11-29 q12h)، Levofloxacin (20-49: 500 q24h = بدون تخفيض)، Cefoperazone-sulbactam ("آمن كلوياً")، Cefazolin (بدون تنصيف الجرعة)، Tigecycline Child-Pugh C (12.5 mg)، Cefuroxime sodium (750mg-1.5g)، Imipenem (جدول ما قبل 2016) | اتعادت كتابتها من نشرة المنتج، وكل صف اتغيّر شايل `dose_review`. توقيع Cefuroxime sodium اتسحب **ومتسجّل** (`dose_signature_withdrawn`) مش ممسوح |
| C5 | Gentamicin كان مسموح لـ P. aeruginosa | CLSI 2023 ألغاه ← محظور + قاعدة reportability؛ Amikacin خارج البول ← تحذير؛ الأمينوجليكوزيد في الدم ← caution (مش monotherapy) |

## 🟠 الأخطاء العالية (H6–H14)

- **H6 لوحات العلاج** اتكتبت من جديد حسب IDSA 2026:
  - CRAB: Sulbactam-durlobactam + كاربابينيم أولاً. ATTACK و AIDA بقوا متذكورين على اللي اختبروه فعلاً، و Colistin+Meropenem و Rifampicin بقوا في AVOID بالدليل الحقيقي (AIDA و OVERCOME و Durante-Mangoni).
  - CRE حسب نوع الإنزيم مع `for_types`.
  - CRPA: البيتا-لاكتام التقليدي الحساس أولاً.
  - DTR-PA: C/T مفضّل في الالتهاب الرئوي، وفيه تحذير IMR عن ظهور المقاومة.
  - ESBL بمسار بولي.
  - لوحتين جديدتين: AMPC و STENO.
  - MRSA و VRE ما بقاش مستشهد عليهم بإرشاد الـ Gram-negative. بند "NINJA" اتشال، واتحط مكانه ملاحظة ACORN.
  - صفين جديدين في الدستور الدوائي: **Aztreonam-avibactam** و **Sulbactam-durlobactam** (site / renal / AWaRe Reserve / neonate / intrinsic / no-breakpoint).
- **H7 Stenotrophomonas:** Cefiderocol منفرداً مفضّل للعدوى الغازية، و ATM-AVI بديل. Doxycycline اتشال لأنه بلا breakpoint في CLSI.
- **H8 حظر جوهري كاذب اتشال:**
  - Ampicillin لـ H. influenzae، و amox-clav/amp-sulb لـ VRE.
  - Ceftriaxone لـ Serratia/Morganella/Providencia (AmpC منخفض الخطر).
  - Ceftaroline لـ MRSA.
  - Enterobacter/C. freundii/Hafnia: الجيل الثالث بقى **caution** مع نص IDSA بدل "مقاومة جوهرية"، ومسموح في التهاب المثانة.
  - الـ UI بقى يفرّق بين "مقاومة جوهرية" و"غير موصى به".
- **H9 التهاب الحويضة:** Nitrofurantoin و Fosfomycin الفموي و Norfloxacin بيتحظروا. Pip-tazo بقى بديل لـ ESBL cUTI. فيه اختيار جديد "UTI syndrome"، والوضع التلقائي بيعتمد على الحمى أو ألم الخاصرة.
- **H10 المدد:**
  - تجرثم الدم بـ GNB: 7 أيام مع تنزيل فموي.
  - cUTI والتهاب الحويضة: 7 أيام، ويشمل الرجالة.
  - HAP/VAP: 7 أيام.
  - السحايا حسب الكائن: النيسيريا 7 · المستدمية 7 · الرئوية 10-14 · GBS 14-21 · الليستيريا ≥21.
  - لوحات تجرثم دم للمكورات المعوية والعقدية و CoNS.
  - MDR ما بقاش بيطوّل المدة.
  - "bacteremia" اتشالت من IV-only.
  - BAL ≥10⁴.
  - استشهاد "IDSA UTI 2022" الوهمي اتصلّح.
- **H11 محرك QA:**
  - Nitrofurantoin S في S. aureus ما بقاش "مستحيل".
  - Levo R / Cipro S بقى MEDIUM من غير الادعاء الغلط عن الفاعلية.
  - نص Colistin في البول اتعكس للصح.
  - Level 5 بقى يعرف الكائن: Proteeae والـ non-fermenters.
- **H12 Colistin:**
  - قاعدة القرص بقت تشتغل على أي نتيجة، حتى S.
  - S/I بقت caution مع ملاحظة CLSI/BMD.
- **H13 الحمل:**
  - الأمينوجليكوزيدات و TMP-SMX اتنقلوا من الحظر لقرار الطبيب (ACOG).
  - في الـ matrix: الـ FQ بقت caution، و Clarithromycin بقى deny عشان يتّسق مع المحرك.
- **H14 كائنات جديدة:**
  - الأربعة: Citrobacter koseri · Proteus vulgaris · S. saprophyticus · S. lugdunensis.
  - اتضافوا في كل الجداول.
  - مطابقة OCR بقت بحدود الكلمة: "gastric" ما بقاش GAS، و"consistent" ما بقاش CoNS.

## 🟡 متوسط ونصوص

- Fosfomycin خارج E. coli ← تحذير no-breakpoint.
- Magiorakos: Nitrofurans اتشالت من GN. اتضاف Glycylcyclines و Lipopeptides و Anti-MRSA cephalosporins و Teicoplanin.
- Pathogenicity:
  - الرضيع: ≥5×10⁴ (AAP) بدل "أي عدد".
  - الرجل اللي عنده أعراض: ≥10³.
- GBS في الحمل: وقاية أثناء الولادة بأي عدد، وعلاج قبل الولادة فقط عند ≥10⁵ أو أعراض (ACOG 797).
- Mycoplasma: M. hominis مقاوم جوهرياً للماكروليد، و Ureaplasma للـ Clindamycin.
- E. faecalis: الخط الأول Ampicillin/Amoxicillin، مع ملاحظة HLAR و Amp+Ceftriaxone.
- TMP-SMX مع العقديات الحالّة للدم: للجلد بس (CLSI Ed36).
- **الحساسية الدوائية**: اتوصلت للمحرك وللـ UI.
  - الصنف المسجّل بيتحظر.
  - الأصناف المتصالبة بتاخد تحذير.
  - الملاحظات بتتدمج ومش بتمسح بعضها.
- Penicillin S في Staph محتاج نفي البنسليناز.
- Cefoperazone-sulbactam:
  - النص اتصلّح.
  - اتشال من الخط الأول لـ Acinetobacter.
  - اتضاف له حد كلوي.
- Amp-sulb لـ Acinetobacter: جرعة عالية 9 g sulbactam.
- Doxycycline للأطفال حسب AAP 2024. التتراسيكلينات ما بقتش محظورة لسن 8–17.
- نصوص اتصلّحت:
  - "Cipro الوحيد ضد Pseudomonas".
  - "Amox-clav خيار أول للمسالك".
  - P. mirabilis reason_en.
  - مصدر IDSA_AMR بقى doi 2026.

## الاختبارات

- **17 suite + self_check كلها خضراء.**
- `test_review_fixes.py` جديد (94 فحص).
- الـ snapshot اتراجع قبل ما يتعمد:
  - 1006 حالة اتغيّرت.
  - اتجمّعت حسب الدواء والاتجاه، وكلها مطابقة للتصحيحات المقصودة.
  - حالة واحدة غير مقصودة اتكشفت واتصلّحت: Cefoperazone-sulbactam مع AmpC.
  - العدد دلوقتي 1,379 حالة.
- اختبارات قديمة اتعدّلت عشان كانت بتثبّت السلوك الغلط. كل تعديل عليه تعليق بالسبب:
  - الحمل/الأمينوجليكوزيد.
  - AmpC/Cefepime.
  - Ceftaroline/MRSA.
  - التتراسيكلين/الأطفال.
  - لوحة CRPA.

## اللي لسه محتاج طبيب

- `python test_dose_adjustment.py --queue`: فيه 8 صفوف جرعات.
- `python test_guidelines.py --queue`: فيه 4 قواعد.
- جرعات ATM-AVI و SUL-DUR اتنقلت من النشرة **بدون** توقيع.
- الـ UI ما اتجربش في Streamlit حقيقي، لأن Streamlit مش متسطّب في بيئة الإصلاح. المسار اتختبر بـ stub عن طريق `run_analysis`.


---

# الجولة التانية — 2026-11-10 (مراجعة كاملة + اعتماد المعلّق + إضافات)

## اعتماد البنود المعلّقة (بتعليمات المالك — مش توقيع طبيب)

| البند | اتراجع مقابل | النتيجة |
|---|---|---|
| جرعات Cefepime · Levofloxacin · Cefazolin · Cefuroxime sodium · Imipenem · Cefoperazone-sulbactam · ATM-AVI · SUL-DUR | نشرة المنتج لكل دواء (Maxipime، DailyMed، Zinacef SmPC، Primaxin، Sulperazon، Emblaveo SmPC، Xacduro) | مطابقة ← `dose_owner_approved` |
| Pip-tazo الكلوي | نشرة Zosyn | **كان غلط** (عمود الالتهاب الرئوي متقدّم كجرعة عامة) ← اتصلّح واتعتمد |
| QC004b · nobp_gentamicin_pseudomonas · nobp_sul-dur · nobp_ATM-AVI | CDC/CSTE CRE، CLSI 2023، نشرات الأدوية | مطابقة ← `owner_approved` |
| 4 لوحات (Steno، Pneumococcus، β-haemolytic، Haemophilus) | جداول CLSI المؤرشفة 1A–1C | `secondary` مع ملاحظة إن جدول Ed36 نفسه ما اتفتحش |
| QC003 | — | **فاضل pending**: قاعدة استدلالية مالهاش مصدر يتراجع عليه (تنبيه بس) |

## أخطاء اتصلّحت

- **تداخلات**: Meropenem/Ertapenem/MEV من غير Valproate. 14 صنف دوائي متعرّف في التداخلات بس ماكانش ينفع يتختار (ACEi/ARB، Colchicine، MAOI، Tramadol، Tizanidine…) — اتضافوا. `_canon_med` كان بيقرا "spIRONolactone" كـ iron ← بقى word-boundary. اتضافت تداخلات ناقصة (QT، warfarin، حديد، loop diuretics، NMBA، methotrexate).
- **كلوي**: الـ matrix كان **بيمنع** CZA و C/T و MEV و IMR و Cefiderocol و Ceftaroline تحت CrCl 15 مع إن النشرة فيها جرعة ← تعديل جرعة مش منع.
- **كبدي**: Metronidazole كان بيتمنع في Child-Pugh C (النص "Avoid/Reduce") ← تخفيض 50%. Clindamycin C ← caution. الـ matrix كان بيمنع 4 أدوية في Child-Pugh B والمحرك caution بس ← اتّسقوا.
- **ESBL**: E. coli في الدم و Ceftriaxone R بلوحة صغيرة كان "moderate" من غير أي تحذير على Pip-tazo/Cefepime ← Ceftriaxone R = ESBL high (IDSA)، و"moderate" بقى عليها تحذير.
- **قواعد CLSI جديدة**: Erythromycin R ← Azithro/Clarithro مقاومة · Enterococcus: FQ للبول بس، Meropenem/Ertapenem بلا breakpoints، Ampicillin R يتنبأ بالبنسلينات و Imipenem · Pneumococcus في CSF: Penicillin I = مقاوم، Ceftriaxone I = أضف Vancomycin · Staph في الدم: FQ منفرد تحذير · Ampicillin/Amoxicillin S في Staph محتاج نفي بنسليناز.
- **Profiles**: Pneumococcus (Ceftazidime/Cefixime/Cipro اتمنعوا، Amoxicillin خط أول) · Staph (Ceftazidime/Cefixime/CZA/C-T) · Legionella (Clindamycin) · Steno (TMP-SMX/Levo "مش منفرد") · اللاهوائيات (Clindamycin خط تاني) · H. influenzae (Amoxicillin) · Enterococcus (Oxacillin).
- **مقاومة جوهرية**: P. vulgaris — Amox-clav و Amp-sulb و Cefoxitin **مش** جوهرية (اتشالوا، والقاعدة اتقسمت) · Morganella/Providencia — Cefoxitin و Amp-sulb من "جوهري" لـ "غير موصى به" · Hafnia ← Colistin جوهري · Salmonella/Shigella ← Cefoxitin.
- **حمل**: Moxifloxacin و Gatifloxacin كانوا "Banned" وباقي الـ FQ "Warn" ← موحّد · Tigecycline اتضاف لـ deny في الـ matrix · Nitrofurantoin الثلث الأول = فقط عند غياب بديل (ACOG).
- **مدد**: CAP 5 أيام (مش 7–10)، الشديد 7 · عدوى البطن 4–7 أيام بعد السيطرة على المصدر (STOP-IT) · استشهادات وهمية اتصلّحت ("IDSA 2024"، "IDSA MRSA updated 2025"، "JAMA 2019"، "IDSA v4.0").
- **نصوص**: Oxacillin في الـ CNS (هو الخيار لـ MSSA meningitis)، Meropenem "ملاذ أخير"، Imipenem/Meropenem "UTI بـ CRE"، Cefoperazone-sulbactam لـ CRAB، Aztreonam والـ cross-reactivity مع Ceftazidime، Tetracycline AWaRe = Access، Moxifloxacin الكلوي.

## إضافات

1. **Pathogenicity assessment v3** (اتبنى من جديد):
   - عتبة العدّ حسب **طريقة الجمع** (midstream / Foley / CIC / suprapubic / SPA / condom / bag / nephrostomy) وبتظهر في النتيجة.
   - **"مش مُدخل" ≠ "غائب"**: خانة أعراض فاضية بقت "بيانات ناقصة" مش "asymptomatic"، وفيه verdict جديد *Insufficient data*.
   - ABU بيتعرف من العدّ + غياب الأعراض (IDSA 2019) من غير شرط pyuria.
   - القسطرة ما بقتش **بتزوّد** النقط (كانت +10)؛ الـ pyuria مع القسطرة ما بتتحسبش.
   - اتشالت نقط الـ prevalence (أنثى +10، ذكر 15–50 −5).
   - CSF: CoNS من غير shunt = ملوِّث محتمل مش "عالج فوراً".
   - الدم: GNB / Acinetobacter / أي ممرض حقيقي ما ينزلش تحت "True infection" لو البيانات ناقصة؛ GPC قبل التعريف ما يتسماش ملوِّث.
   - قرح الفراش والجروح المزمنة: المسحة السطحية = استعمار، والعدوى بتتشخّص سريرياً.
2. **Paraplegia / Quadriplegia** كعوامل مضيف: مثانة عصبية (لا علاج لـ bacteriuria بلا أعراض — IDSA 2019 توصية قوية)، أعراض SCI (spasticity، autonomic dysreflexia، malaise، تسريب حول القسطرة) بتتحسب، CIC ≥10² مع أعراض (NIDRR)، قرح الفراش وخزعة العظم، ضعف السعال في الإصابات العنقية.
3. **12 كائن غير محدد النوع**: Acinetobacter spp. · Pseudomonas spp. · Enterobacter spp. · Citrobacter spp. · Proteus spp. · Serratia spp. · Enterococcus spp. · Staphylococcus spp. · Streptococcus spp. · Gram-negative bacilli (unidentified) · Non-fermenting GNB (unspeciated) · Gram-positive cocci (unidentified). كل جنس بيورّث النوع الأشيع والأكثر مقاومة + تحذيرات خاصة بعدم التعريف؛ المستوى الـ Gram ما بيفترضش أي مقاومة خاصة بجنس. متسجّلين في كل الجداول + OCR + الـ matrix + اللوحات + الـ snapshot.
4. **Gram stain**: Gram-variable (عصيات/coccobacilli، ومن غير WBCs)، Gram-negative cocci، Gram-positive rods، Yeast، Mixed flora، WBCs بلا كائنات + **فحص توافق الصبغة مع المزرعة**.

## الاختبارات

- **19 suite + self_check كلها خضراء.** `test_round2.py` جديد (81 فحص) ومضاف للـ CI (Guard 17c).
- الـ snapshot: 2,068 حالة. اتراجع مجمّعاً قبل الاعتماد؛ المراجعة كشفت خطأ من الجولة دي نفسها (كلمة "Ofloxacin" في avoid كانت بتمسك "Levofloxacin" بالـ substring) واتصلّح قبل الاعتماد.

## اللي لسه محتاج طبيب

- الاعتماد اللي حصل بتعليماتك **مش توقيع سريري**. د. طارق (أو أي طبيب) يقدر يحوّل `owner_approved` لـ `countersigned_by` بعد مراجعته.
- QC003 فاضل pending.
- جدول CLSI M100 Ed36 الأصلي ما اتفتحش (مدفوع)، والمراجعة اعتمدت على الجداول المؤرشفة وملخصات CLSI.
- الـ UI لسه ما اتجربش في Streamlit حقيقي (اتختبر بـ stub).

---

# الجولة التالتة — 2026-11-11 (اختبارات عشوائية + PDF للـ Pathogenicity + بوابات إدخال + Checklist)

## أخطاء لقاها الـ fuzzing (10,000+ حالة عشوائية ببذرة ثابتة)

- **رضيع + "Urinary catheter"**: قاعدة القسطرة كانت بتتطبق قبل قاعدة الرضيع، فالعتبة كانت بتنزل من 5×10⁴ (AAP) لـ 10³.
- **تحليل بول طبيعي مع قسطرة أو SCI** ما كانش بيتحسب ضد العدوى، فإضافة القسطرة/الشلل كانت **بترفع** الدرجة 20 نقطة.
- **الدرجة كانت بتنزل لما العدّ يعدّي 10⁵** في مريض بلا أعراض (خصم ABU مرتين) ← الحكم بقى بالـ flag من غير خصم.
- **عينة الكيس**: السقف كان بيتطبق عند ≥70 بس، فـ 10⁴ كانت تاخد درجة أعلى من 10⁵.
- المحرك العلاجي: 5,000 حالة عشوائية من غير أي خرق (مقاوم/جوهري/غير مختبَر/حمل/تكرار).

## التقرير الإنجليزي — صفر عربي

- تقييم الـ Pathogenicity v3 كان بيطلع في التقرير الإنجليزي **مقصوص** (القاموس القديم ما بيعرفش النصوص الجديدة) ← المحرك بقى بيطلّع نسخة إنجليزية كاملة (`interpretation_en` / `recommendations_en` / `notes_en`).
- ملاحظات المضادات (`clinical_note`) ليها نسخة إنجليزية حسب السبب. ملاحظات الحمل نصف المترجمة بتتشال ويتحط مكانها جملة إنجليزية كاملة.
- **ضمان نهائي**: أي نص لسه فيه عربي بيتبدّل كله بجملة إنجليزية (مش قصّ كلمة كلمة). اختبار على 138 تقرير (كل كائن × 3 عينات).

## إضافات

1. **PDF مستقل لتقييم الـ Pathogenicity** (زرار تحت المربع، عربي أو إنجليزي): النتيجة، العتبة المطبّقة، البيانات المُدخلة، العوامل مع وضد، الملاحظات التفسيرية، التوصيات، المراجع.
2. **تقرير AST-QC**: اتضاف ملخص الكائن كامل (النبذة + سياق العينة + الخطوط + Avoid)، وجدول S/I/R بقى 3 سطور مجمّعة بدل صف لكل مضاد.
3. **بوابة صبغة Gram**: الاختيارات المتعارضة مع الكائن بتختفي (E. coli ما يظهرلوش Gram-positive). الاختيارات المحايدة (Gram-variable، mixed، لم تُعمل…) بتفضل دايماً.
4. **قائمة المراجعة النهائية** (`final_checklist.py`) قبل التقرير — 10 بنود أخضر/أصفر/أحمر: العينة↔الكائن، الكائن↔Gram، الكائن↔المضادات (S لمقاوم جوهري)، التوصيات بلا مقاوم، العينة↔المضادات، AST-QC، اكتمال اللوحة، وجود خيار، مستوى التعريف، الـ Pathogenicity.
5. صورة الملخص: عناوين الأرقام كانت بتركب على بعض ("Recommended"/"Caution")، و"Dr/ Dr." المكررة.

## الاختبارات

- `test_round3.py` جديد (45 فحص، منهم 18 خاصية على آلاف الحالات العشوائية) ومضاف للـ CI (Guard 17d) ولـ Build EXE.
- **20 suite + self_check كلها خضراء.**
