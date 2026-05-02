import streamlit as st
import pandas as pd
import numpy as np
from PIL import Image
import easyocr
import re

# ========== الدوال الطبية (المنطق) ==========

def calculate_crcl(age, weight, sex, serum_creatinine):
    """
    حساب معدل تصفية الكرياتينين (CrCl) بمعادلة Cockcroft-Gault.
    يُرجع القيمة ml/min أو None إن لم تتوفر المدخلات.
    """
    if None in (age, weight, serum_creatinine) or weight <= 0 or serum_creatinine <= 0:
        return None
    crcl = ((140 - age) * weight) / (72 * serum_creatinine)
    if sex == "أنثى":
        crcl *= 0.85
    return round(crcl, 1)


def extract_culture_results(uploaded_image):
    """
    استخراج نتائج المزرعة من صورة باستخدام EasyOCR.
    يُرجع DataFrame بالأعمدة: Antibiotic, Result
    """
    # حفظ الصورة مؤقتاً
    with open("temp_culture.jpg", "wb") as f:
        f.write(uploaded_image.getbuffer())
    
    # تهيئة EasyOCR (يدعم الإنجليزية والعربية)
    reader = easyocr.Reader(['en', 'ar'], gpu=False)
    results = reader.readtext("temp_culture.jpg", detail=0)
    
    # تنظيف النص المستخرج – نحاول التعرف على سطور الجدول
    cleaned_lines = []
    for line in results:
        # إزالة التشويش والمسافات الزائدة
        line = re.sub(r'\s+', ' ', line).strip()
        if line:
            cleaned_lines.append(line)
    
    # محاولة بناء DataFrame من النص:
    # نفترض أن كل سطر يتكون من اسم المضاد ثم النتيجة S / I / R
    antibiotics = []
    sensitivity = []
    for line in cleaned_lines:
        # نبحث عن أحد الرموز S, I, R في آخر السطر
        match = re.search(r'\b([SIR])\b\s*$', line.upper())
        if match:
            result_code = match.group(1)
            # اسم المضاد هو كل ما قبل النتيجة
            ab_name = line[:match.start()].strip().rstrip(':-* ')
            antibiotics.append(ab_name)
            sensitivity.append(result_code)
    
    df = pd.DataFrame({
        "Antibiotic": antibiotics,
        "Result": sensitivity
    })
    return df


def get_renal_alerts(antibiotic, crcl):
    """
    تحقق من حاجة المضاد لتعديل الجرعة بناءً على CrCl.
    يُرجع رسالة التنبيه أو سلسلة فارغة.
    """
    if crcl is None:
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
    if crcl < 30:
        return alerts.get(antibiotic, "")
    return ""


def get_pregnancy_alerts(antibiotic, is_pregnant):
    """
    يُرجع تنبيهاً إذا كان المضاد غير آمن في الحمل.
    (مبنية على أحدث الدلائل الإرشادية – فئة D/X أو ما ينصح بتجنبه)
    """
    unsafe_drugs = [
        "Tetracycline", "Doxycycline", "Minocycline",       # تيتراسيكلينات
        "Ciprofloxacin", "Levofloxacin", "Moxifloxacin",    # فلوروكينولونات
        "Gentamicin", "Amikacin", "Tobramycin",             # أمينوغليكوزيدات
        "Trimethoprim/Sulfamethoxazole",                    # في الثلث الأول والأخير
        "Nitrofurantoin"                                    # في الثلث الثالث
    ]
    if is_pregnant and antibiotic in unsafe_drugs:
        return "🚫 غير آمن في الحمل – يوصى باستبداله"
    return ""


def process_culture_with_alerts(df_culture, crcl, is_pregnant):
    """
    دمج نتائج المزرعة مع التنبيهات السريرية (كلوي / حمل).
    """
    if df_culture.empty:
        return df_culture
    
    df = df_culture.copy()
    df["Renal Alert"] = df["Antibiotic"].apply(lambda x: get_renal_alerts(x, crcl))
    df["Pregnancy Alert"] = df["Antibiotic"].apply(lambda x: get_pregnancy_alerts(x, is_pregnant))
    return df


# ========== واجهة المستخدم (Streamlit) ==========

st.set_page_config(page_title="دعم قرار المضادات الحيوية", layout="wide")
st.title("🩺 نظام دعم القرار لاختيار المضاد الحيوي")
st.markdown("**ادمج قراءة المزرعة، وظائف الكلى، وحالة الحمل للحصول على توصيات فورية**")

# ----- الشريط الجانبي: بيانات المريض -----
with st.sidebar:
    st.header("بيانات المريض")
    age = st.number_input("العمر (سنوات)", min_value=0, max_value=120, value=50, step=1)
    sex = st.selectbox("الجنس", ["ذكر", "أنثى"])
    weight = st.number_input("الوزن (كجم) - اختياري", min_value=0.0, max_value=300.0, value=70.0, step=0.1)
    serum_creatinine = st.number_input("الكرياتينين في الدم (mg/dL)", min_value=0.1, max_value=20.0, value=1.0, step=0.1)
    
    is_pregnant = False
    if sex == "أنثى":
        is_pregnant = st.checkbox("المريضة حامل حالياً؟")
    
    st.divider()
    calculate_btn = st.button("🔄 حساب CrCl وإعادة التقييم")

# ----- المنطقة الرئيسية: رفع صورة المزرعة -----
st.header("📤 رفع تقرير المزرعة")
uploaded_file = st.file_uploader("اختر صورة لتقرير المزرعة (JPG/PNG)", type=["jpg", "jpeg", "png"])

# ----- معالجة الصورة واستخراج النتائج -----
if uploaded_file is not None:
    with st.spinner("⏳ جارٍ استخراج النتائج من الصورة... (قد يستغرق عدة ثوانٍ)"):
        try:
            df_culture = extract_culture_results(uploaded_file)
            if not df_culture.empty:
                st.success("✅ تم استخراج الجدول بنجاح")
                st.subheader("نتائج المزرعة المُستخرجة")
                st.dataframe(df_culture, use_container_width=True)
            else:
                st.warning("⚠️ لم يتم التعرف على أي نتائج بصيغة (مضاد حيوي + S/I/R). تأكد من وضوح الصورة.")
                df_culture = pd.DataFrame()
        except Exception as e:
            st.error(f"فشل استخراج النص: {e}")
            df_culture = pd.DataFrame()
else:
    st.info("ℹ️ ارفع صورة المزرعة أولاً")
    df_culture = pd.DataFrame()

# ----- حساب CrCl والتنبيهات (إذا دخل المستخدم زر الحساب أو تلقائياً) -----
if calculate_btn or (uploaded_file is not None and not df_culture.empty):
    crcl = calculate_crcl(age, weight, sex, serum_creatinine)
    
    if crcl is not None:
        st.sidebar.metric("تصفية الكرياتينين (CrCl)", f"{crcl} ml/min")
        if crcl < 30:
            st.sidebar.error("⚠️ تحذير: قصور كلوي شديد (CrCl < 30). معظم الأدوية تحتاج تعديل جرعة أو تغيير.")
    else:
        st.sidebar.info("ℹ️ أدخل الوزن لحساب CrCl")
        crcl = None
    
    # تطبيق التنبيهات على جدول المزرعة
    if not df_culture.empty:
        df_with_alerts = process_culture_with_alerts(df_culture, crcl, is_pregnant)
        st.subheader("🔔 المضادات مع التنبيهات السريرية")
        
        # تلوين الصفوف حسب وجود تحذير
        def highlight_rows(row):
            if row["Renal Alert"] or row["Pregnancy Alert"]:
                return ['background-color: #fff3cd'] * len(row)
            return [''] * len(row)
        
        styled_df = df_with_alerts.style.apply(highlight_rows, axis=1)
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
        
        # عرض تفصيلي للتنبيهات
        for idx, row in df_with_alerts.iterrows():
            if row["Renal Alert"]:
                st.warning(f"{row['Antibiotic']} – {row['Renal Alert']}")
            if row["Pregnancy Alert"]:
                st.error(f"{row['Antibiotic']} – {row['Pregnancy Alert']}")
