import streamlit as st
import numpy as np
import cv2
import pytesseract
import re

# ==========================================
# 📋 Comprehensive Antibiotics Database (From Your Images)
# ==========================================
ABX_GUIDELINES = {
    "Nitrofurantoin": {"priority": 1, "class": "Urinary Antiseptic", "note": "🎯 الخيار الأول للمسالك.", "renal_limit": 30, "renal_note": "🚫 ممنوع إذا كانت التصفية < 30."},
    "Fosfomycin": {"priority": 1, "class": "Phosphonic Acid", "note": "🎯 خيار مثالي بجرعة واحدة.", "renal_limit": 10, "renal_note": "⚠️ حذر في القصور الشديد."},
    "Amoxicillin + Clavulanic acid": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي واسع المدى.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة إذا كانت التصفية < 30."},
    "Augmentin": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة إذا كانت التصفية < 30."},
    "Cephalexin": {"priority": 2, "class": "1st Gen Cephalosporin", "note": "✅ آمن وفعال للالتهابات البسيطة.", "renal_limit": 40, "renal_note": "⚖️ مباعدة الجرعات في القصور المتوسط."},
    "Cefaclor": {"priority": 2, "class": "2nd Gen Cephalosporin", "note": "✅ خيار بديل مستقر.", "renal_limit": 10, "renal_note": "⚠️ تقليل الجرعة في الفشل النهائي."},
    "Doxycycline": {"priority": 2, "class": "Tetracycline", "note": "✅ آمن كلوياً بشكل عام.", "renal_limit": 0, "renal_note": "🟢 آمن لمرضى الكلى."},
    "Sulfamethoxazole + Trimethoprim": {"priority": 2, "class": "Sulfonamide", "note": "✅ فعال للمسالك والبروستاتا.", "renal_limit": 30, "renal_note": "⚖️ خفض الجرعة للنصف (CrCl 15-30)."},
    "Levofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ واسع المدى؛ يفضل ادخاره للحالات المعقدة.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة (تصفية < 50)."},
    "Ofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ واسع المدى.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة (تصفية < 50)."},
    "Ciprofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ خيار قوي؛ تجنبه في الحالات البسيطة.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة (تصفية < 50)."},
    "Ceftriaxone": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ حقن؛ آمن كلوياً (إطراح مزدوج).", "renal_limit": 0, "renal_note": "🟢 لا يحتاج تعديل جرعة."},
    "Ceftazidime": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ مضاد للمستشفيات (Pseudomonas).", "renal_limit": 50, "renal_note": "⚖️ تعديل دقيق حسب التصفية."},
    "Cefepime": {"priority": 3, "class": "4th Gen Cephalosporin", "note": "⚠️ قوي جداً للحالات الشديدة.", "renal_limit": 50, "renal_note": "🛑 خطر سمية عصبية (تصفية < 50)."},
    "Gentamicin": {"priority": 3, "class": "Aminoglycoside", "note": "⚠️ سمية كلوية عالية؛ يتطلب مراقبة.", "renal_limit": 70, "renal_note": "🚫 حذر شديد؛ تجنبه في القصور الكلوي."},
    "Amikacin": {"priority": 3, "class": "Aminoglycoside", "note": "⚠️ سمية كلوية عالية.", "renal_limit": 50, "renal_note": "🚫 خطر سمية كلوية عالية."},
    "Imipenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 للحالات الحرجة والطوارئ.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة لتجنب التشنجات."},
    "Meropenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 مضاد احتياطي للحالات المعقدة.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري (تصفية < 50)."},
    "Ertapenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 يستخدم مرة واحدة يومياً.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة (CrCl < 30)."},
    "Piperacillin + Tazobactam": {"priority": 4, "class": "Anti-pseudomonal", "note": "🛑 مضاد احتياطي واسع المدى جداً.", "renal_limit": 40, "renal_note": "⚖️ تعديل الجرعة ضروري."},
}

def extract_all_data(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    
    # استخدام PSM 3 للمسح الشامل وضمان التقاط الكلمات المتناثرة
    full_text = pytesseract.image_to_string(thresh, config='--psm 3')
    
    # البحث عن الأدوية في كامل النص كحل وقائي
    detected_drugs = []
    for abx_name in ABX_GUIDELINES.keys():
        if re.search(r'\b' + re.escape(abx_name.lower()) + r'\b', full_text.lower()):
            detected_drugs.append(abx_name)
    
    age_match = re.search(r"Age\s*[:/-]?\s*(\d+)", full_text, re.I)
    sex = "Female" if "female" in full_text.lower() else "Male"
    
    patient_data = {
        "Age": age_match.group(1) if age_match else "35",
        "Sex": sex
    }
    return patient_data, list(set(detected_drugs))

# ==========================================
# 🖥️ Interface: ORANGE LAB CULTURE ANALYZER
# ==========================================
st.set_page_config(page_title="Orange Lab Culture Pro", layout="wide")
st.title("🛡️ ORANGE LAB | Culture & Sensitivity Analyzer")

uploaded = st.file_uploader("Upload Culture Report Image", type=['jpg', 'png', 'jpeg'])

if uploaded:
    patient, drugs = extract_all_data(uploaded)
    col1, col2 = st.columns([1, 1.5])
    
    with col1:
        st.subheader("👤 Patient Information")
        age = st.number_input("Age", value=int(patient['Age']))
        sex = st.radio("Gender", ["Male", "Female"], index=1 if patient['Sex']=="Female" else 0)
        
        # سؤال الحمل يظهر للإناث فقط
        is_preg = False
        if sex == "Female":
            is_preg = st.checkbox("🤰 Is Pregnant?")
        
        st.divider()
        is_renal = st.checkbox("🚩 Renal Function (CrCl Calculation)")
        cl_cr = 100
        if is_renal:
            weight = st.number_input("Weight (kg)", min_value=10, value=75)
            s_creat = st.number_input("Serum Creatinine", min_value=0.1, value=1.0, step=0.1)
            cl_cr = ((140 - age) * weight) / (72 * s_creat)
            if sex == "Female": cl_cr *= 0.85
            st.metric("Creatinine Clearance", f"{cl_cr:.1f} ml/min")

    with col2:
        st.subheader("💊 Sensitive Antibiotics (Detected)")
        
        # ميزة التعديل اليدوي على الأدوية المكتشفة
        final_list = st.multiselect(
            "📝 Review & Add Missing Antibiotics:",
            options=sorted(list(ABX_GUIDELINES.keys())),
            default=drugs,
            help="Select antibiotics marked as 'Sensitive' in the report."
        )
        
        st.divider()
        
        allowed, banned, warnings = [], [], []
        
        for d in final_list:
            info = ABX_GUIDELINES.get(d)
            if info:
                # 1. فحص موانع الحمل
                if is_preg and any(x in d.lower() for x in ["cipro", "levo", "oflox", "tetra", "doxy", "genta", "amikacin"]):
                    banned.append(f"❌ {d}: Teratogenic risk / Contraindicated.")
                # 2. فحص كفاءة الكلى (Nitrofurantoin حالة خاصة)
                elif is_renal and d == "Nitrofurantoin" and cl_cr < 30:
                    banned.append(f"❌ {d}: Ineffective/Contraindicated when CrCl < 30.")
                # 3. فحص الحاجة لتعديل الجرعة
                elif is_renal and info['renal_limit'] > 0 and cl_cr <= info['renal_limit']:
                    warnings.append({"name": d, **info})
                # 4. خيار متاح
                else:
                    allowed.append({"name": d, **info})

        # --- عرض النتائج ---
        if banned:
            st.error("🚫 Contraindicated / Not Recommended")
            for b in banned: st.write(b)
            
        if warnings:
            st.warning("⚖️ Dose Adjustment Required")
            for item in warnings:
                with st.expander(f"⚠️ {item['name']} - {item['renal_note']}"):
                    st.write(item['note'])

        if allowed:
            st.success("🟢 Recommended Options (Safe/Standard Dose)")
            for item in sorted(allowed, key=lambda x: x['priority']):
                with st.expander(f"💊 {item['name']}"):
                    st.write(f"**Class:** {item['class']}")
                    st.info(item['note'])

st.divider()
# إمضاء المطور بالإنجليزية كما طلبت
st.markdown("""
<div style="text-align: center; color: gray; font-size: 0.8em;">
    Developed by: Dr. Hussein Ali | Orange Lab - October Branch
</div>
""", unsafe_allow_html=True)
