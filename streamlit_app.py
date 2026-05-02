import streamlit as st
import pandas as pd
import numpy as np
import cv2
import pytesseract
import re
from PIL import Image

# ==================== دوال طبية ====================
def calculate_crcl(age, weight, sex, serum_creatinine):
    if None in (age, weight, serum_creatinine) or weight <= 0 or serum_creatinine <= 0:
        return None
    crcl = ((140 - age) * weight) / (72 * serum_creatinine)
    if sex == "أنثى":
        crcl *= 0.85
    return round(crcl, 1)

def get_renal_alert(antibiotic, crcl):
    if crcl is None or crcl >= 30:
        return ""
    alerts = {
        "Nitrofurantoin": "⚠️ يمنع (CrCl<30)",
        "Gentamicin": "⚠️ يحتاج تعديل جرعة (CrCl<30)",
        "Amikacin": "⚠️ يحتاج تعديل جرعة (CrCl<30)",
        "Tobramycin": "⚠️ يحتاج تعديل جرعة (CrCl<30)",
        "Vancomycin": "⚠️ مراقبة مستوى وتعديل جرعة (CrCl<30)",
        "Ciprofloxacin": "⚠️ خفض الجرعة (CrCl<30)",
        "Levofloxacin": "⚠️ خفض الجرعة (CrCl<30)",
        "Trimethoprim/Sulfamethoxazole": "⚠️ تقليل الجرعة أو تجنبه (CrCl<30)"
    }
    return alerts.get(antibiotic, "")

def get_pregnancy_alert(antibiotic, is_pregnant):
    if not is_pregnant:
        return ""
    unsafe = [
        "Tetracycline", "Doxycycline", "Minocycline",
        "Ciprofloxacin", "Levofloxacin", "Moxifloxacin",
        "Gentamicin", "Amikacin", "Tobramycin",
        "Trimethoprim/Sulfamethoxazole",
        "Nitrofurantoin"
    ]
    if antibiotic in unsafe:
        return "🚫 غير آمن في الحمل"
    return ""

def generate_recommendation(row_data, crcl, is_pregnant):
    """
    يولد التوصية النهائية لكل مضاد حيوي.
    """
    antibiotic = row_data['Antibiotic']
    result = row_data['Result']
    if result == 'R':
        return "مقاوم – لا يُستخدم"
    if result == 'I':
        base = "حساسية متوسطة – يمكن استخدامه بحذر"
    else:  # S
        base = "✅ موصى به"

    # إضافة تحذيرات إن وجدت
    warnings = []
    renal = get_renal_alert(antibiotic, crcl)
    preg = get_pregnancy_alert(antibiotic, is_pregnant)
    if renal:
        warnings.append(renal)
    if preg:
        warnings.append(preg)
    if warnings:
        return base + " مع تحذير: " + " | ".join(warnings)
    return base

# ==================== دالة OCR المتطورة ====================
def extract_patient_info(ocr_text):
    """استخراج العمر والجنس من نص OCR (يدعم العربية والإنجليزية)."""
    age = None
    sex = None
    # البحث عن Age: XX Y أو العمر: XX سنة
    age_match = re.search(r'Age\s*:\s*(\d+)\s*Y', ocr_text, re.IGNORECASE)
    if not age_match:
        age_match = re.search(r'العمر\s*:\s*(\d+)', ocr_text)
    if age_match:
        age = int(age_match.group(1))
    
    # البحث عن Sex: Male/Female أو الجنس: ذكر/أنثى
    sex_match = re.search(r'Sex\s*:\s*(\w+)', ocr_text, re.IGNORECASE)
    if sex_match:
        if 'female' in sex_match.group(1).lower() or 'أنثى' in sex_match.group(1):
            sex = 'أنثى'
        else:
            sex = 'ذكر'
    return age, sex

def extract_antibiogram_advanced(image_file):
    """
    استخراج المضادات الحيوية ونتائج الحساسية (S/I/R) من صورة تقرير المزرعة.
    تستخدم image_to_data لإعادة بناء الصفوف بدقة.
    """
    # تحميل الصورة
    file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if img is None:
        return pd.DataFrame(), ""
    # معالجة مبدئية
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

    # استخراج النص الكامل (لاستخراج البيانات الديموغرافية)
    full_text = pytesseract.image_to_string(thresh, lang='eng+ara', config='--psm 6')
    
    # استخراج البيانات المنظمة بالجدول باستخدام image_to_data
    data = pytesseract.image_to_data(thresh, lang='eng+ara', output_type=pytesseract.Output.DICT, config='--psm 6')
    
    # إعادة بناء السطور بناءً على الإحداثيات (y) ومنع دمج الأعمدة المتجاورة
    lines = {}
    for i in range(len(data['text'])):
        text = data['text'][i].strip()
        if not text:
            continue
        y = data['top'][i]
        x = data['left'][i]
        # تجميع الكلمات التي تبدأ في نفس السطر (بفارق بسيط في y)
        line_key = round(y / 10) * 10  # تقريب لأقرب 10 بكسل لدمج السطور المتقاربة
        if line_key not in lines:
            lines[line_key] = {'words': [], 'min_x': x}
        lines[line_key]['words'].append(text)
        lines[line_key]['min_x'] = min(lines[line_key]['min_x'], x)
    
    # ترتيب السطور حسب الإحداثي y
    sorted_lines = sorted(lines.items(), key=lambda kv: kv[0])
    
    # كلمات دالة على الفئات
    sensitive_kw = ['sensitive', 'susceptible', 'حساس', 'حساسة']
    intermediate_kw = ['intermediate', 'متوسط', 'وسيط']
    resistant_kw = ['resistant', 'مقاوم', 'مقاومة']
    
    antibiotics = []
    results = []
    current_category = None
    
    for _, line_data in sorted_lines:
        words = line_data['words']
        line_text = ' '.join(words).strip()
        # تجاهل سطور العناوين
        if any(w.lower() in ['antibiotic', 'description', 'colony', 'comment', 'مضاد', 'المضاد'] for w in words):
            continue
        
        # التحقق مما إذا كان السطر يحتوي على فئة
        if any(kw in line_text.lower() for kw in sensitive_kw):
            current_category = 'S'
            # قد يكون مع الكلمة اسم مضاد مثل "Sensitive Piperacillin/Tazobactam"
            # نحاول استخراج اسم الدواء إذا وجد بعد الفئة
            rest = re.sub(r'(?i)(sensitive|susceptible|حساس|حساسة)[\s:]*', '', line_text).strip()
            if rest:
                antibiotics.append(rest)
                results.append('S')
            continue
        elif any(kw in line_text.lower() for kw in intermediate_kw):
            current_category = 'I'
            rest = re.sub(r'(?i)(intermediate|متوسط|وسيط)[\s:]*', '', line_text).strip()
            if rest:
                antibiotics.append(rest)
                results.append('I')
            continue
        elif any(kw in line_text.lower() for kw in resistant_kw):
            current_category = 'R'
            rest = re.sub(r'(?i)(resistant|مقاوم|مقاومة)[\s:]*', '', line_text).strip()
            if rest:
                antibiotics.append(rest)
                results.append('R')
            continue
        
        # إذا كان السطر لا يحتوي على فئة، فهو اسم مضاد ضمن الفئة الحالية
        if current_category and line_text:
            # تنظيف الاسم من الأرقام والرموز العالقة
            drug = re.sub(r'[^a-zA-Zأ-ي/\s\+\-]', '', line_text).strip()
            if drug:
                antibiotics.append(drug)
                results.append(current_category)
    
    df = pd.DataFrame({"Antibiotic": antibiotics, "Result": results})
    # إزالة التكرارات (بنفس الاسم) – قد تظهر مكررة بسبب بقايا OCR
    df = df.drop_duplicates(subset="Antibiotic", keep="first").reset_index(drop=True)
    return df, full_text

# ==================== واجهة التطبيق ====================
st.set_page_config(page_title="دعم قرار المضادات الحيوية", layout="wide")
st.title("🩺 نظام دعم القرار لاختيار المضاد الحيوي")
st.markdown("ادمج قراءة المزرعة، وظائف الكلى، وحالة الحمل للحصول على توصيات فورية")

# تحميل البيانات المخزنة في الجلسة
if 'df_culture' not in st.session_state:
    st.session_state.df_culture = pd.DataFrame()
if 'auto_age' not in st.session_state:
    st.session_state.auto_age = None
if 'auto_sex' not in st.session_state:
    st.session_state.auto_sex = None

# ----- الشريط الجانبي: بيانات المريض -----
with st.sidebar:
    st.header("🧬 بيانات المريض")
    # استخدام القيم المستخرجة تلقائياً كقيم افتراضية إن وجدت
    default_age = st.session_state.auto_age if st.session_state.auto_age else 40
    default_sex = st.session_state.auto_sex if st.session_state.auto_sex else "ذكر"
    
    age = st.number_input("العمر (سنوات)", min_value=0, max_value=120, value=default_age, step=1)
    sex = st.selectbox("الجنس", ["ذكر", "أنثى"], 
                       index=0 if default_sex == "ذكر" else 1)
    weight = st.number_input("الوزن (كجم) - ضروري لحساب CrCl", min_value=30.0, max_value=300.0, value=70.0, step=0.1)
    serum_creatinine = st.number_input("الكرياتينين في الدم (mg/dL)", min_value=0.1, max_value=15.0, value=0.9, step=0.1)

    is_pregnant = False
    if sex == "أنثى":
        is_pregnant = st.checkbox("المريضة حامل؟")

    st.divider()
    calculate_btn = st.button("🔄 حساب CrCl وتقييم النتائج")

# ----- علامات التبويب -----
tab1, tab2 = st.tabs(["📸 رفع صورة المزرعة (OCR)", "✍️ إدخال يدوي"])

with tab1:
    uploaded_file = st.file_uploader("اختر صورة لتقرير المزرعة", type=["jpg", "jpeg", "png"])
    if uploaded_file is not None:
        with st.spinner("⏳ جارٍ استخراج النتائج وبيانات المريض من الصورة..."):
            df_culture, full_ocr_text = extract_antibiogram_advanced(uploaded_file)
            
            # استخراج البيانات الديموغرافية
            auto_age, auto_sex = extract_patient_info(full_ocr_text)
            if auto_age:
                st.session_state.auto_age = auto_age
            if auto_sex:
                st.session_state.auto_sex = auto_sex
            
            if not df_culture.empty:
                st.success("✅ تم استخراج الجدول وبيانات المريض")
                st.session_state.df_culture = df_culture
                st.subheader("نتائج المزرعة المستخرجة")
                st.dataframe(df_culture, use_container_width=True)
                if auto_age or auto_sex:
                    st.info(f"تم استخراج: العمر={auto_age}، الجنس={auto_sex} (سيتم تعبئته تلقائياً في الشريط الجانبي)")
            else:
                st.warning("⚠️ لم يتم التعرف على أي نتائج. تأكد من وضوح الصورة أو استخدم الإدخال اليدوي.")
                st.session_state.df_culture = pd.DataFrame()

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

# ----- عرض النتائج مع التوصيات -----
if calculate_btn or not st.session_state.df_culture.empty:
    crcl = calculate_crcl(age, weight, sex, serum_creatinine)
    if crcl is not None:
        st.sidebar.metric("CrCl (ml/min)", crcl)
        if crcl < 30:
            st.sidebar.error("⚠️ تحذير: قصور كلوي شديد (CrCl < 30)")
    else:
        st.sidebar.warning("الوزن مطلوب لحساب CrCl")

    df = st.session_state.df_culture.copy()
    if not df.empty:
        # إضافة عمود التوصية النهائية
        df['توصية شاملة'] = df.apply(
            lambda row: generate_recommendation(row, crcl, is_pregnant), axis=1
        )
        # إضافة عمود التنبيهات المنفصلة للوضوح
        df['Renal Alert'] = df['Antibiotic'].apply(lambda x: get_renal_alert(x, crcl))
        df['Pregnancy Alert'] = df['Antibiotic'].apply(lambda x: get_pregnancy_alert(x, is_pregnant))
        
        st.subheader("📊 جدول المزرعة مع التوصيات النهائية")
        st.dataframe(df, use_container_width=True, hide_index=True)

        # عرض ملخص سريع
        st.markdown("### 🎯 ملخص التوصيات")
        rec_counts = df['توصية شاملة'].value_counts()
        for rec, count in rec_counts.items():
            st.write(f"- {rec}: **{count}** أدوية")
    else:
        st.info("ℹ️ يرجى إدخال نتائج المزرعة أولاً.")
