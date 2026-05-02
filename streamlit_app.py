import streamlit as st
import pandas as pd

# ========== الدوال الطبية (ثابتة كما هي) ==========
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

# ========== واجهة المستخدم ==========
st.set_page_config(page_title="دعم قرار المضادات الحيوية", layout="wide")
st.title("🩺 نظام دعم القرار لاختيار المضاد الحيوي")
st.markdown("**أدخل نتائج المزرعة وبيانات المريض لتحصل على توصيات فورية (بدون OCR معقد)**")

# ----- الشريط الجانبي: بيانات المريض -----
with st.sidebar:
    st.header("🧬 بيانات المريض")
    age = st.number_input("العمر (سنوات)", min_value=0, max_value=120, value=40, step=1)
    sex = st.selectbox("الجنس", ["ذكر", "أنثى"])
    weight = st.number_input("الوزن (كجم) - مطلوب لحساب CrCl", min_value=30.0, max_value=300.0, value=70.0, step=0.1)
    serum_creatinine = st.number_input("الكرياتينين في الدم (mg/dL)", min_value=0.1, max_value=15.0, value=0.9, step=0.1)

    is_pregnant = False
    if sex == "أنثى":
        is_pregnant = st.checkbox("المريضة حامل؟")

    st.divider()
    calculate_btn = st.button("🔄 حساب CrCl وتقييم النتائج")

# ----- المنطقة الرئيسية: إدخال نتائج المزرعة -----
st.header("🔬 نتائج المزرعة (حساسية المضادات الحيوية)")

tab1, tab2 = st.tabs(["✍️ إدخال نصي", "📋 جدول تفاعلي"])

with tab1:
    st.markdown("انسخ نتائج المزرعة كما تظهر في التقرير (كل سطر: اسم المضاد ثم S / I / R)")
    default_text = """Amoxicillin S
Ciprofloxacin R
Gentamicin S
Nitrofurantoin S
Trimethoprim/Sulfamethoxazole S"""
    culture_text = st.text_area("الصق التقرير هنا", value=default_text, height=200)
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
            st.warning("لم يتم التعرف على بيانات صالحة. تأكد من كتابة النتيجة (S/I/R) في نهاية كل سطر.")
            st.session_state['df_culture'] = pd.DataFrame()

with tab2:
    st.markdown("قم بملء الجدول مباشرة:")
    # جدول افتراضي قابل للتعديل
    if 'editable_df' not in st.session_state:
        st.session_state.editable_df = pd.DataFrame([
            {"Antibiotic": "Amoxicillin", "Result": "S"},
            {"Antibiotic": "Ciprofloxacin", "Result": "R"},
            {"Antibiotic": "Gentamicin", "Result": "S"}
        ])
    edited_df = st.data_editor(
        st.session_state.editable_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Result": st.column_config.SelectboxColumn(
                "النتيجة",
                options=["S", "I", "R"],
                required=True
            )
        }
    )
    if st.button("اعتماد الجدول التفاعلي"):
        st.session_state['df_culture'] = edited_df
        st.success("تم اعتماد الجدول.")

# عرض النتائج عند الطلب
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

        # تنبيهات منفصلة
        for _, row in df_with_alerts.iterrows():
            if row["Renal Alert"]:
                st.warning(f"{row['Antibiotic']} – {row['Renal Alert']}")
            if row["Pregnancy Alert"]:
                st.error(f"{row['Antibiotic']} – {row['Pregnancy Alert']}")
    else:
        st.info("يرجى إدخال نتائج المزرعة أولاً (تبويب الإدخال النصي أو الجدول).")
