# سجل التغييرات — مراجعة الإرشادات 2026-11-10

مراجعة سطر بسطر مقابل: CLSI M100 Ed33–Ed36 · EUCAST v16.1 · IDSA AMR Guidance 2026
(doi:10.1093/cid/ciag481) · IDSA cUTI 2025 · BALANCE (NEJM 2025) · ATS/IDSA HAP/VAP 2016 ·
IDSA Bacterial Meningitis · ACOG CO 717 / 797 · AAP Red Book 2024 · WHO AWaRe 2025 ·
Magiorakos 2012.

كل خطأ هنا **اتأكّد الأول** بسيناريو فشل على الكود الأصلي، وبعدين اتصلّح، وبعدين اتثبّت
باختبار في الملف الجديد `test_review_fixes.py` (94 فحص).

> ⚠️ **ده مش توقيع سريري.** 8 صفوف جرعات و4 قواعد جديدة عليها علامة
> `dose_review` / `awaiting_countersignature` وبتظهر في الاختبارات كـ *release blocker*
> لحد ما طبيب يراجعها ويوقّع.

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
