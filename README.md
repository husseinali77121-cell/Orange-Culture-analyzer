# Orange Culture Analyzer

نظام دعم قرار سريري (CDSS) لتفسير مزارع الميكروبيولوجي واختبارات الحساسية،
مبني على Streamlit. يقرأ لوحة الحساسية، يستنتج آلية المقاومة، يصنّف
MDR/XDR/PDR، ويُخرج قائمة أدوية مفلترة حسب الكائن والعيّنة وحالة المريض.

> **تنبيه:** أداة مساعدة للقرار. لا تُغني عن حكم أخصائي الميكروبيولوجي أو
> الطبيب المعالج، ولا تُستخدم كمصدر وحيد لقرار علاجي.

## القدرات

| | |
|---|---|
| **المقاومة الجوهرية** | 50 صف، مصدر واحد للحقيقة في `clinical_data.py` |
| **استنتاج الآلية** | ESBL · AmpC · carbapenemase · DTR · MRSA · VRE |
| **التصنيف** | MDR/XDR/PDR بجداول Magiorakos منفصلة لكل مجموعة كائنات |
| **بوابات الأمان** | حمل · أطفال · حديثو ولادة (بالشهور) · كلوي · كبدي (Child-Pugh) |
| **QC اللوحة** | تناقضات · تسلسل · فئات مكافئة · أنماط ظاهرية استثنائية · قابلية التبليغ |
| **التتبّع** | 50 قاعدة مربوطة بمصادر مؤرَّخة في `guideline_registry.py` |

## المصادر

EUCAST Breakpoint Tables v16.1 · EUCAST Intrinsic Resistance v3.3 ·
EUCAST Expert Rules v3.1 · CLSI M100 Ed36 · CLSI M39 ·
IDSA AMR Guidance 2026 · WHO AWaRe 2025 ·
Magiorakos et al., *Clin Microbiol Infect* 2012;18:268-281

## التشغيل

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## الإعداد — `.streamlit/secrets.toml`

```toml
# هوية البائع (تظهر في صفحة الدخول ورسائل التجديد)
vendor_name  = "Orange Lab"
vendor_phone = "+20 ..."
vendor_email = "support@example.com"

# المشتركون: البريد -> تاريخ الانتهاء
subscribers = '{"lab@example.com": "2026-12-31"}'

# كلمات المرور (اختياري لكن موصى به بشدة)
# من غيرها الدخول بالبريد وحده، والتطبيق هيعرض تحذير عند البدء
subscriber_hashes = '{"lab@example.com": "pbkdf2_sha256$240000$...$..."}'
```

توليد الـ hash:

```bash
python -c "import streamlit_app as a; print(a.make_password_hash('كلمة-السر'))"
```

## الاختبارات

```bash
python test_intrinsic_invariant.py   # المقاومة الجوهرية تُحترم دائماً
python test_intrinsic_sync.py        # المحرك العلاجي و QC متفقان
python test_scenarios.py             # 1,344 سيناريو + golden snapshot (1,267 حالة)
python test_comprehensive.py         # فضاء المزارع الكامل
python test_guidelines.py            # تتبّع الاستشهادات
python test_clinical_matrix.py       # خريطة القيود السريرية
python test_safety_invariants.py     # ثوابت بوابات الأمان
```

الـ CI (9 guards) بيشغّل السبعة + `compileall` + **import حقيقي لكل module**.

`test_scenarios.py` بيقارن بـ golden snapshot. أي تغيّر في إجابة سريرية بيكسر
البناء عن قصد — راجع الـ diff، وبعدين:

```bash
python test_scenarios.py --update
```

## البنية

```
streamlit_app.py        الواجهة + المحركات السريرية
clinical_data.py        المقاومة الجوهرية — مصدر الحقيقة الوحيد
abx_guidelines.py       الدستور الدوائي (60 دواء)
organism_profile.py     خطوط العلاج لكل كائن
specimen_organism_map.py أي كائن يُتوقَّع في أي عيّنة
ast_reportability.py    قواعد «هل يجوز تبليغ هذه النتيجة؟»
ast_consistency.py      تناقضات اللوحة + الأنماط الاستثنائية
ast_qa_engine.py        فحوص QA مستوى 1
clinical_matrix.py      خريطة القيود المفصولة
safety_gate.py          بوابة الأمان
guideline_registry.py   ربط كل قاعدة بمصدرها المؤرَّخ
```

> `ui/` و `modules/` و `data/` بقايا إعادة هيكلة سابقة. بتـ import بنجاح لكن
> **مش موصولة بالتطبيق** — إما تُحذف أو تُوصَّل قبل الاعتماد عليها.

---

_الأرقام أعلاه محدَّثة بتاريخ 2026-08-06 مقابل الكود نفسه: **60 دواء · 30 كائن قابل للاختيار · 50 صف مقاومة جوهرية · 50 استشهاد مُوقَّع · 1,267 حالة في الـ snapshot**. `test_clinical_facts.py` بيفشل لو أي رقم منهم اتغيّر من غير تحديث._
