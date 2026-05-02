# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import cv2
import pytesseract
import re

# ==================== الإعدادات العامة والإرشادات ====================
PAGE_TITLE = "نظام دعم القرار لاختيار المضاد الحيوي - إرشادات 2025"

# ==================== دوال طبية مُحدَّثة بناءً على إرشادات 2025 ====================
def calculate_crcl(age, weight, sex, serum_creatinine):
    """حساب CrCl باستخدام معادلة Cockcroft-Gault"""
    if None in (age, weight, serum_creatinine) or weight <= 0 or serum_creatinine <= 0:
        return None
    crcl = ((140 - age) * weight) / (72 * serum_creatinine)
    if sex == "أنثى":
        crcl *= 0.85
    return round(crcl, 1)

def get_clinical_alerts(antibiotic, crcl, is_pregnant, specimen_type="Urine"):
    """
    تجميع التنبيهات السريرية بناءً على إرشادات 2025.
    تُرجع (renal_alert, pregnancy_alert)
    """
    renal_alert = ""
    pregnancy_alert = ""
    
    # --- التنبيهات الكلوية (مبنية على Sanford Guide 2025 وجداول الجمعية الأمريكية) ---
    if crcl is not None:
        antibiotic_lower = antibiotic.lower()
        
        # Nitrofurantoin: تجنب إذا CrCl < 30 (أو < 60 حسب بعض المصادر)
        if 'nitrofurantoin' in antibiotic_lower:
            if crcl < 30:
                renal_alert = "⚠️ **تجنب الاستخدام:** يمنع إذا CrCl < 30 (عدم وصول تركيز كافٍ للبول وزيادة السمية)."
            elif crcl < 60:
                renal_alert = "⚠️ **حذر:** بيانات محدودة لـ CrCl < 60. يفضل بديل."
        
        # Aminoglycosides (مثل: Gentamicin, Amikacin, Tobramycin)
        elif any(drug in antibiotic_lower for drug in ['gentamicin', 'amikacin', 'tobramycin']):
            if crcl < 30:
                renal_alert = "⚠️ **تجنب أو تعديل كبير:** مراقبة المستوى (TDM) ضرورية. خطر سمية كلوية وأذنية."
            elif crcl < 70:
                renal_alert = "⚠️ **حذر:** يفضل مراقبة المستوى وتعديل الجرعة حسب وظائف الكلى."

        # Vancomycin
        elif 'vancomycin' in antibiotic_lower:
            if crcl < 50:
                renal_alert = "⚠️ **مراقبة المستوى وتعديل الجرعة:** خطر سمية كلوية. مراقبة المستوى ضرورية."

        # Fluoroquinolones (Ciprofloxacin, Levofloxacin, Ofloxacin)
        elif any(drug in antibiotic_lower for drug in ['ciprofloxacin', 'levofloxacin', 'ofloxacin']):
            if crcl < 30:
                renal_alert = "⚠️ **خفض الجرعة:** يحتاج لتقليل الجرعة بشكل كبير."
            elif crcl < 60:
                renal_alert = "⚠️ **حذر:** قد يحتاج لتقليل الجرعة إذا CrCl منخفض جداً."

        # Trimethoprim/Sulfamethoxazole
        elif 'trimethoprim' in antibiotic_lower or 'sulfamethoxazole' in antibiotic_lower:
            if crcl < 30:
                renal_alert = "⚠️ **تقليل الجرعة أو تجنبه:** خطر تفاقم وظائف الكلى وفرط بوتاسيوم الدم."
        
        # Piperacillin/Tazobactam
        elif 'piperacillin' in antibiotic_lower:
            if crcl < 40:
                renal_alert = "⚠️ **تعديل الجرعة:** يحتاج لتقليل الجرعة إذا CrCl ≤ 40."

    # --- تنبيهات الحمل (مبنية على إرشادات 2025) ---
    if is_pregnant:
        antibiotic_lower = antibiotic.lower()
        # أدوية غير آمنة في الحمل
        unsafe_drugs = {
            'tetracycline': '❌ **خطر على الجنين:** يمنع استخدام التتراسيكلينات في الحمل.',
            'doxycycline': '❌ **خطر على الجنين:** يمنع استخدام التتراسيكلينات في الحمل.',
            'minocycline': '❌ **خطر على الجنين:** يمنع استخدام التتراسيكلينات في الحمل.',
            'ciprofloxacin': '🚫 **غير آمن:** يفضل تجنب الفلوروكينولونات في الحمل.',
            'levofloxacin': '🚫 **غير آمن:** يفضل تجنب الفلوروكينولونات في الحمل.',
            'moxifloxacin': '🚫 **غير آمن:** يفضل تجنب الفلوروكينولونات في الحمل.',
            'gentamicin': '⚠️ **خطر:** يمكن استخدامه فقط إذا كانت الفوائد تفوق المخاطر (خطر سمية أذنية للجنين).',
            'amikacin': '⚠️ **خطر:** يمكن استخدامه فقط إذا كانت الفوائد تفوق المخاطر.',
            'tobramycin': '⚠️ **خطر:** يمكن استخدامه فقط إذا كانت الفوائد تفوق المخاطر.',
            'trimethoprim': '❌ **يمنع:** يمنع في الثلث الأول (خطر تشوهات الأنبوب العصبي).',
            'sulfamethoxazole': '❌ **يمنع:** يمنع قرب الولادة (خطر اليرقان النووي).',
            'nitrofurantoin': '⚠️ **تجنب:** تجنب في الثلث الثالث (خطر فقر الدم الانحلالي).'
        }
        
        for drug_key, alert_msg in unsafe_drugs.items():
            if drug_key in antibiotic_lower:
                pregnancy_alert = alert_msg
                break

    return renal_alert, pregnancy_alert

def generate_recommendation(row_data, crcl, is_pregnant, specimen_type):
    """
    يولد التوصية النهائية لكل مضاد حيوي بناءً على نتيجة الحساسية، إرشادات الكلى والحمل، ونوع العينة.
    """
    antibiotic = row_data['Antibiotic']
    result = row_data['Result']
    
    if result == 'R':
        return "❌ مقاوم – لا يُستخدم"
    
    if result == 'I':
        base = "🟡 حساسية متوسطة – يمكن استخدامه بحذر إذا لزم الأمر"
    else: # S
        base = "✅ موصى به"

    # إضافة تحذيرات
    renal_alert, pregnancy_alert = get_clinical_alerts(antibiotic, crcl, is_pregnant, specimen_type)
    
    alerts = []
    if renal_alert:
        alerts.append(renal_alert)
    if pregnancy_alert:
        alerts.append(pregnancy_alert)
    
    if alerts:
        return base + " | " + " | ".join(alerts)
    return base

# ==================== دوال OCR محسَّنة ====================
@st.cache_data
def extract_patient_data(full_text):
    """استخراج العمر والجنس من نص التقرير."""
    age = None
    sex = None
    # محاولة استخراج العمر: Age : 49 Y أو Age:49Y
    age_match = re.search(r'Age\s*:\s*(\d+)\s*Y', full_text, re.IGNORECASE)
    if age_match:
        age = int(age_match.group(1))
    else:
        age_match = re.search(r'Age\s*:\s*(\d+)', full_text, re.IGNORECASE)
        if age_match:
            age = int(age_match.group(1))
    
    # محاولة استخراج الجنس: Sex : Male أو Sex: Male
    sex_match = re.search(r'Sex\s*:\s*(\w+)', full_text, re.IGNORECASE)
    if sex_match:
        sex_value = sex_match.group(1).lower()
        if 'female' in sex_value or 'أنثى' in sex_value:
            sex = 'أنثى'
        elif 'male' in sex_value or 'ذكر' in sex_value:
            sex = 'ذكر'
    return age, sex

@st.cache_data
def extract_antibiogram_advanced(image_file):
    """استخراج نتائج المزرعة من الصورة باستخدام تحليل مكاني دقيق."""
    # تحميل الصورة
    file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if img is None:
        return pd.DataFrame(), ""

    # معالجة الصورة
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

    # 1. استخراج النص الكامل للبيانات الديموغرافية
    full_text = pytesseract.image_to_string(thresh, lang='eng+ara', config='--psm 6')

    # 2. استخراج البيانات المنظمة باستخدام image_to_data
    data = pytesseract.image_to_data(thresh, lang='eng+ara', output_type=pytesseract.Output.DICT, config='--psm 6')

    # إعادة بناء السطور
    lines = {}
    n_boxes = len(data['text'])
    for i in range(n_boxes):
        text = data['text'][i].strip()
        if not text:
            continue
        x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
        # تجميع الكلمات القريبة جداً أفقياً (لمنع دمج الأعمدة)
        line_key = round(y / 15) * 15  # زيادة الدقة
        if line_key not in lines:
            lines[line_key] = []
        lines[line_key].append((x, text))

    # ترتيب السطور y وإعادة بناء النص لكل سطر
    sorted_line_keys = sorted(lines.keys())
    reconstructed_lines = []
    for key in sorted_line_keys:
        # ترتيب الكلمات أفقياً داخل السطر
        sorted_words = sorted(lines[key], key=lambda item: item[0])
        line_text = ' '.join([word for _, word in sorted_words])
        reconstructed_lines.append(line_text)

    # كلمات مفتاحية للفئات (حساس / متوسط / مقاوم)
    sensitive_kw = ['sensitive', 'susceptible', 'حساس']
    intermediate_kw = ['intermediate', 'متوسط', 'وسيط']
    resistant_kw = ['resistant', 'مقاوم', 'مقاومة']
    
    antibiotics = []
    results = []
    current_category = None

    for line in reconstructed_lines:
        clean_line = line.strip()
        lower_line = clean_line.lower()
        
        # تجاهل الأسطر الفارغة أو العناوين العامة
        if not clean_line or any(ignore in lower_line for ignore in ['antibiotic', 'description', 'colony', 'comment', 'مزرعة', 'antibacterial', 'reporting']):
            continue

        # تحديث الفئة الحالية
        if any(kw in lower_line for kw in sensitive_kw):
            current_category = 'S'
            # إذا كان هناك اسم دواء بجانب "Sensitive"، نضيفه
            for kw in sensitive_kw:
                clean_line = re.sub(r'(?i)' + kw + r'[\s:]*', '', clean_line).strip()
            if clean_line:
                antibiotics.append(clean_line)
                results.append('S')
            continue
        elif any(kw in lower_line for kw in intermediate_kw):
            current_category = 'I'
            for kw in intermediate_kw:
                clean_line = re.sub(r'(?i)' + kw + r'[\s:]*', '', clean_line).strip()
            if clean_line:
                antibiotics.append(clean_line)
                results.append('I')
            continue
        elif any(kw in lower_line for kw in resistant_kw):
            current_category = 'R'
            for kw in resistant_kw:
                clean_line = re.sub(r'(?i)' + kw + r'[\s:]*', '', clean_line).strip()
            if clean_line:
                antibiotics.append(clean_line)
                results.append('R')
            continue

        # إذا لم تكن فئة، فهو اسم مضاد حيوي
        if current_category and clean_line:
            # تنظيف الاسم
            drug_name = re.sub(r'[^a-zA-Zأ-ي/\s\+\-]', '', clean_line).strip()
            if drug_name:
                antibiotics.append(drug_name)
                results.append(current_category)

    # بناء DataFrame
    df = pd.DataFrame({"Antibiotic": antibiotics, "Result": results})
    # تنظيف نهائي: إزالة أسطر قد لا تزال تحتوي على كلمات مفتاحية، وإزالة التكرارات المتجاورة
    if not df.empty:
        # إزالة أي صفوف يكون اسم المضاد فيها فارغاً أو لا يزال يحتوي على كلمة مفتاحية
        df = df[~df['Antibiotic'].str.lower().str.contains('|'.join(sensitive_kw + intermediate_kw + resistant_kw))]
        df = df[df['Antibiotic'].str.strip() != '']
        df = df.drop_duplicates(subset="Antibiotic", keep="first").reset_index(drop=True)
    
    return df, full_text

# ==================== واجهة التطبيق ====================
st.set_page_config(page_title=PAGE_TITLE, layout="wide")
st.title("🩺 نظام دعم القرار لاختيار المضاد الحيوي")
st.markdown("**ادمج قراءة المزرعة، وظائف الكلى، وحالة الحمل للحصول على توصيات فورية تستند على إرشادات 2025**")

# --- الحالة الافتراضية ---
if 'df_culture' not in st.session_state:
    st.session_state.df_culture = pd.DataFrame()
if 'auto_age' not in st.session_state:
    st.session_state.auto_age = None
if 'auto_sex' not in st.session_state:
    st.session_state.auto_sex = None
if 'specimen_type' not in st.session_state:
    st.session_state.specimen_type = "Urine"

# ---------- الشريط الجانبي: المدخلات السريرية ----------
with st.sidebar:
    st.header("🧬 مدخلات المريض")
    st.markdown("---")
    
    default_age = st.session_state.auto_age if st.session_state.auto_age else 40
    default_sex = st.session_state.auto_sex if st.session_state.auto_sex else "ذكر"
    
    age = st.number_input("العمر (سنوات)", min_value=0, max_value=120, value=default_age, step=1)
    sex = st.selectbox("الجنس", ["ذكر", "أنثى"], index=0 if default_sex == "ذكر" else 1)
    weight = st.number_input("الوزن (كجم)", min_value=30.0, max_value=300.0, value=70.0, step=0.1, help="ضروري لحساب تصفية الكرياتينين.")
    serum_creatinine = st.number_input("الكرياتينين في الدم (mg/dL)", min_value=0.1, max_value=15.0, value=0.9, step=0.1)

    st.markdown("---")
    st.subheader("⚕️ اعتبارات سريرية")
    col1, col2 = st.columns(2)
    with col1:
        is_pregnant = st.checkbox("🤰 حمل")
        if is_pregnant and sex != "أنثى":
            st.warning("لا يمكن تحديد الحمل إذا لم تكن أنثى.")
            is_pregnant = False
    with col2:
        is_renal_patient = st.checkbox("🧪 مرض كلوي")
        if is_renal_patient:
            st.info("سيتم تفعيل التنبيهات الكلوية تلقائياً إذا كان CrCl منخفضاً.")

    st.session_state.specimen_type = st.selectbox(
        "نوع العينة",
        ["Urine", "Blood", "Sputum", "Wound", "Other"],
        index=0,
        help="يؤثر على خيارات المضادات الحيوية."
    )

    st.markdown("---")
    calculate_btn = st.button("🔬 حساب CrCl وتقييم النتائج", type="primary", use_container_width=True)

# ---------- علامات تبويب إدخال المزرعة ----------
tab1, tab2 = st.tabs(["📸 رفع صورة المزرعة (OCR)", "✍️ إدخال يدوي"])

with tab1:
    uploaded_file = st.file_uploader("اختر صورة لتقرير المزرعة (مثل Urine C/S)", type=["jpg", "jpeg", "png"])
    if uploaded_file is not None:
        with st.spinner("⏳ جارٍ استخراج النتائج وبيانات المريض..."):
            df_culture, full_ocr_text = extract_antibiogram_advanced(uploaded_file)
            
            # استخراج البيانات الديموغرافية
            auto_age, auto_sex = extract_patient_data(full_ocr_text)
            if auto_age: st.session_state.auto_age = auto_age
            if auto_sex: st.session_state.auto_sex = auto_sex
            
            if not df_culture.empty:
                st.success("✅ تم استخراج الجدول وبيانات المريض")
                st.session_state.df_culture = df_culture
                st.dataframe(df_culture, use_container_width=True, hide_index=True)
                if auto_age or auto_sex:
                    st.info(f"تم استخراج: العمر={auto_age}، الجنس={auto_sex} (سيتم تعبئته تلقائياً في الشريط الجانبي)")
                # عرض النص المستخرج للمراجعة
                with st.expander("🔍 عرض النص المستخرج بالكامل للمراجعة"):
                    st.text(full_ocr_text)
            else:
                st.error("❌ لم يتم التعرف على أي نتائج. تأكد من وضوح الصورة أو استخدم الإدخال اليدوي.")

with tab2:
    st.markdown("انسخ نتائج المزرعة (كل سطر: اسم المضاد ثم S / I / R)")
    culture_text = st.text_area("الصق التقرير هنا", value="", height=200, 
                                placeholder="Piperacillin/Tazobactam S\nCeftazidime I\n...")
    if st.button("تحليل النص المدخل"):
        lines = culture_text.strip().split('\n')
        antibiotics = []
        results = []
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[-1].upper() in ('S', 'I', 'R'):
                ab = ' '.join(parts[:-1])
                res = parts[-1].upper()
                antibiotics.append(ab)
                results.append(res)
        if antibiotics:
            st.session_state.df_culture = pd.DataFrame({"Antibiotic": antibiotics, "Result": results})
            st.success("تم استخراج الجدول")
        else:
            st.warning("لم يتم التعرف على بيانات صالحة.")

# ---------- عرض النتائج مع التوصيات ----------
if calculate_btn or not st.session_state.df_culture.empty:
    crcl = calculate_crcl(age, weight, sex, serum_creatinine)
    
    # عرض CrCl في الشريط الجانبي
    with st.sidebar:
        if crcl is not None:
            st.metric("CrCl (ml/min)", crcl)
            if crcl < 30:
                st.error("🚨 قصور كلوي شديد (CrCl < 30). التنبيهات الكلوية مفعَّلة.")
            elif crcl < 60:
                st.warning("⚠️ قصور كلوي معتدل (CrCl < 60).")
        else:
            st.warning("الوزن مطلوب لحساب CrCl")

    df = st.session_state.df_culture.copy()
    if not df.empty:
        # إضافة أعمدة التوصيات والتنبيهات
        renal_alerts = []
        preg_alerts = []
        final_recs = []
        
        for _, row in df.iterrows():
            renal, preg = get_clinical_alerts(row['Antibiotic'], crcl, is_pregnant)
            renal_alerts.append(renal)
            preg_alerts.append(preg)
            final_recs.append(generate_recommendation(row, crcl, is_pregnant, st.session_state.specimen_type))
        
        df['Renal Alert'] = renal_alerts
        df['Pregnancy Alert'] = preg_alerts
        df['التوصية النهائية'] = final_recs

        st.subheader("📊 جدول المزرعة مع التوصيات النهائية")
        st.dataframe(
            df[['Antibiotic', 'Result', 'Renal Alert', 'Pregnancy Alert', 'التوصية النهائية']],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Antibiotic": "المضاد الحيوي",
                "Result": "النتيجة",
                "Renal Alert": "تنبيه كلوي",
                "Pregnancy Alert": "تنبيه حمل",
                "التوصية النهائية": "التوصية"
            }
        )

        # --- ملخص التوصيات بناءً على إرشادات 2025 ---
        st.markdown("---")
        st.subheader("🎯 ملخص التحليل السريري (IDSA 2025)")
        
        recommended_drugs = df[df['Result'] == 'S']
        intermediate_drugs = df[df['Result'] == 'I']
        resistant_drugs = df[df['Result'] == 'R']
        
        col1, col2, col3 = st.columns(3)
        col1.metric("✅ موصى به", len(recommended_drugs), delta="اختيار أول")
        col2.metric("🟡 حساسية متوسطة", len(intermediate_drugs), delta="بديل محتمل")
        col3.metric("❌ مقاوم", len(resistant_drugs), delta="لا يُستخدم", delta_color="off")
        
        # نصيحة للمستخدم
        st.info("""
        **ملاحظة هامة (إرشادات IDSA 2025):**
        - العدوى المعقدة (cUTI): إذا كان هناك ارتفاع في درجة الحرارة أو علامات جهازية، يوصى بالاختيار من السيفالوسبورينات من الجيل الثالث/الرابع أو بيبراسيلين-تازوباكتام.
        - العدوى البسيطة (uUTI): يمكن استخدام نطاق أضيق مثل نيتروفورانتوين (إذا كان CrCl > 60 ولا يوجد حمل في الثلث الثالث) أو سيفاليكسين.
        - مدة العلاج: 5-7 أيام للفلوروكينولونات، 7 أيام لغيرها.
        """)
    else:
        st.info("ℹ️ يرجى إدخال نتائج المزرعة أولاً.")
