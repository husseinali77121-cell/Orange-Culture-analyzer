import streamlit as st
import pandas as pd
import numpy as np
from PIL import Image
import pytesseract
import cv2
import re

# ==================== الدوال الطبية ====================
def calculate_crcl(age, weight, sex, serum_creatinine):
    if None in (age, weight, serum_creatinine) or weight <= 0 or serum_creatinine <= 0:
        return None
    crcl = ((140 - age) * weight) / (72 * serum_creatinine)
    if sex == "أنثى":
        crcl *= 0.85
    return round(crcl, 1)

def get_renal_alerts(antibiotic, crcl):
    if crcl is None or crcl >= 30:
        return ""
    alerts = {
        "Nitrofurantoin": "⚠️ يُمنع استخدامه إذا CrCl < 30 (يجب استبداله)",
        "Gentamicin": "⚠️ يحتاج تعديل جرعة كبير / تمديد الفاصل بين الجرعات",
        "Amikacin": "⚠️ يحتاج تعديل جرعة كبير / تمديد الفاصل بين الجرعات",
        "Tobramycin": "⚠️ يحتاج تعديل جرعة كبير / تمديد الفاصل بين الجرعات",
        "Vancomycin": "⚠️ مراقبة المستوى وتعديل الجرعة ضروري",
        "Ciprofloxacin": "⚠️ قد تحتاج لتقليل الجرعة إذا CrCl منخفض جداً",
        "Levofloxacin": "⚠️ قد تحتاج لتقليل الجرعة",
        "Trimethoprim/Sulfamethoxazole": "⚠️ تقليل الجرعة أو تجنبه في القصور الشديد"
    }
    return alerts.get(antibiotic, "")

def get_pregnancy_alerts(antibiotic, is_pregnant):
    if not is_pregnant:
        return ""
    unsafe_drugs = [
        "Tetracycline", "Doxycycline", "Minocycline",
        "Ciprofloxacin", "Levofloxacin", "Moxifloxacin",
        "Gentamicin", "Amikacin", "Tobramycin",
        "Trimethoprim/Sulfamethoxazole",
        "Nitrofurantoin"
    ]
    if antibiotic in unsafe_drugs:
        return "🚫 غير آمن في الحمل – يوصى باستبداله"
    return ""

def process_culture_with_alerts(df_culture, crcl, is_pregnant):
    if df_culture.empty:
        return df_culture
    df = df_culture.copy()
    df["Renal Alert"] = df["Antibiotic"].apply(lambda x: get_renal_alerts(x, crcl))
    df["Pregnancy Alert"] = df["Antibiotic"].apply(lambda x: get_pregnancy_alerts(x, is_pregnant))
    return df

# ==================== دالة OCR المُحسَّنة ====================
def extract_antibiogram_from_image(image_file):
    """
    استخراج المضادات الحيوية ونتائج الحساسية من صورة تقرير المزرعة
    (يدعم جداول Sensitive / Intermediate / Resistant)
    """
    # تحويل الصورة إلى صيغة OpenCV
    file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if img is None:
        st.error("تعذر فتح الصورة. تأكد من التنسيق المدعوم (JPG/PNG).")
        return pd.DataFrame()

    # معالجة الصورة لتحسين OCR
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

    # استخدام Tesseract باللغتين العربية والإنجليزية
    custom_config = r'--oem 3 --psm 6'
    text = pytesseract.image_to_string(thresh, lang='eng+ara', config=custom_config)
    lines = text.split('\n')

    # تصفية السطور الفارغة وإزالة المسافات الزائدة
    lines = [re.sub(r'\s+', ' ', line).strip() for line in lines if line.strip()]

    antibiotics = []
    results = []
    current_category = None

    # كلمات دالة على الفئات (بالإنجليزية والعربية)
    sensitive_ids = ['sensitive', 'susceptible', 'حساس', 'حساسة']
    intermediate_ids = ['intermediate', 'متوسط', 'وسيط']
    resistant_ids = ['resistant', 'مقاوم', 'مقاومة']

    for line in lines:
        lower_line = line.lower()

        # اكتشاف عنوان الفئة (حساس / متوسط / مقاوم)
        if any(word in lower_line for word in sensitive_ids):
            current_category = 'S'
            continue
        if any(word in lower_line for word in intermediate_ids):
            current_category = 'I'
            continue
        if any(word in lower_line for word in resistant_ids):
            current_category = 'R'
            continue

        # إذا كنا داخل فئة وكان السطر لا يحتوي على كلمات إضافية غير مرغوب فيها
        if current_category and len(line) > 2:
            # تجاهل سطور مثل "Antibiotic" أو "Description" أو التعليقات
            if any(ignore in lower_line for ignore in ['antibiotic', 'description', 'comment', 'colony', 'culture']):
                continue
            # تنظيف اسم المضاد (إزالة الأرقام والرموز المعلقة)
            drug_name = re.sub(r'[^a-zA-Zا-ي/\s\+\-]', '', line).strip()
            if drug_name:
                antibiotics.append(drug_name)
                results.append(current_category)

    # دمج الأسماء المتشابهة (اختياري)
    df = pd.DataFrame({"Antibiotic": antibiotics, "Result": results})
    # إزالة التكرارات مع الاحتفاظ بأول نتيجة (يمكن تعديلها حسب الحاجة)
    df = df.drop_duplicates(subset="Antibiotic", keep="first").reset_index(drop=True)
    return df

# ==================== واجهة التطبيق ====================
st.set_page_config(page_title="دعم قرار المضادات الحيوية", layout="wide")
st.title("🩺 نظام دعم القرار لاختيار المضاد الحيوي")
st.markdown("ادمج قراءة المزرعة، وظائف الكلى، وحالة الحمل للحصول على توصيات فورية")

# ----- الشريط الجانبي: بيانات المريض -----
with st.sidebar:
    st.header("🧬 بيانات المريض")
    age = st.number_input("العمر (سنوات)", min_value=0, max_value=120, value=49, step=1)
    sex = st.selectbox("الجنس", ["ذكر", "أنثى"])
    weight = st.number_input("الوزن (كجم) - ضروري لحساب CrCl", min_value=30.0, max_value=300.0, value=70.0, step=0.1)
    serum_creatinine = st.number_input("الكرياتينين في الدم (mg/dL)", min_value=0.1, max_value=15.0, value=0.9, step=0.1)

    is_pregnant = False
    if sex == "أنثى":
        is_pregnant = st.checkbox("المريضة حامل؟")

    st.divider()
    calculate_btn = st.button("🔄 حساب CrCl وتقييم النتائج")

# ----- علامات تبويب لطريقة إدخال المزرعة -----
tab1, tab2 = st.tabs(["📸 رفع صورة المزرعة (OCR)", "✍️ إدخال يدوي"])

with tab1:
    uploaded_file = st.file_uploader("اختر صورة لتقرير المزرعة (مثل التقرير المُرفق)", type=["jpg", "jpeg", "png"])
    if uploaded_file is not None:
        with st.spinner("⏳ جارٍ استخراج النتائج من الصورة..."):
            df_culture = extract_antibiogram_from_image(uploaded_file)
            if not df_culture.empty:
                st.success("✅ تم استخراج الجدول بنجاح")
                st.session_state['df_culture'] = df_culture
                st.dataframe(df_culture, use_container_width=True)
            else:
                st.warning("⚠️ لم يتم التعرف على أي نتائج. جرب الإدخال اليدوي أو تأكد من وضوح الصورة/التنسيق.")
                st.session_state['df_culture'] = pd.DataFrame()

with tab2:
    st.markdown("انسخ نتائج المزرعة (كل سطر: اسم المضاد ثم S / I / R)")
    culture_text = st.text_area("الصق التقرير هنا", value="", height=200, placeholder="Piperacillin/Tazobactam S\nCeftazidime I\n...")
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
            df_culture = pd.DataFrame({"Antibiotic": antibiotics, "Result": results})
            st.session_state['df_culture'] = df_culture
            st.success("تم استخراج الجدول بنجاح")
        else:
            st.warning("لم يتم التعرف على بيانات صالحة.")
            st.session_state['df_culture'] = pd.DataFrame()

# ----- عرض التنبيهات عند الضغط على الزر أو وجود بيانات جاهزة -----
if calculate_btn or ('df_culture' in st.session_state and not st.session_state.df_culture.empty):
    crcl = calculate_crcl(age, weight, sex, serum_creatinine)
    if crcl is not None:
        st.sidebar.metric("CrCl (ml/min)", crcl)
        if crcl < 30:
            st.sidebar.error("⚠️ تحذير: قصور كلوي شديد (CrCl < 30)")
    else:
        st.sidebar.warning("الوزن مطلوب لحساب CrCl")

    df_culture = st.session_state.get('df_culture', pd.DataFrame())
    if not df_culture.empty:
        df_with_alerts = process_culture_with_alerts(df_culture, crcl, is_pregnant)
        st.subheader("📊 نتائج المزرعة مع التنبيهات")
        st.dataframe(df_with_alerts, use_container_width=True, hide_index=True)

        for _, row in df_with_alerts.iterrows():
            if row["Renal Alert"]:
                st.warning(f"{row['Antibiotic']} – {row['Renal Alert']}")
            if row["Pregnancy Alert"]:
                st.error(f"{row['Antibiotic']} – {row['Pregnancy Alert']}")
    else:
        st.info("ℹ️ يرجى إدخال نتائج المزرعة أولاً (صورة أو نص).")
