import streamlit as st
import numpy as np
import cv2
import pytesseract
import re

# ==========================================
# 📋 قاعدة بيانات المضادات الحيوية
# ==========================================
ABX_GUIDELINES = {
    "Nitrofurantoin": {"priority": 1, "class": "Urinary Antiseptic", "note": "🎯 الخيار الأول للمسالك البولية.", "renal_limit": 30, "renal_note": "🚫 ممنوع إذا كانت التصفية < 30."},
    "Fosfomycin": {"priority": 1, "class": "Phosphonic Acid", "note": "🎯 خيار مثالي بجرعة واحدة.", "renal_limit": 10, "renal_note": "⚠️ يستخدم بحذر في القصور الشديد."},
    "Amoxicillin + Clavulanic acid": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي فعال.", "renal_limit": 30, "renal_note": "⚖️ يتطلب تعديل الجرعة إذا كانت التصفية < 30."},
    "Augmentin": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي فعال.", "renal_limit": 30, "renal_note": "⚖️ يتطلب تعديل الجرعة إذا كانت التصفية < 30."},
    "Cephalexin": {"priority": 2, "class": "1st Gen Cephalosporin", "note": "✅ آمن وفعال.", "renal_limit": 40, "renal_note": "⚖️ يحتاج مباعدة الجرعات في القصور المتوسط والشديد."},
    "Doxycycline": {"priority": 2, "class": "Tetracycline", "note": "✅ آمن كلوياً؛ لا يتطلب تعديل جرعة.", "renal_limit": 0, "renal_note": "🟢 آمن لمرضى الكلى."},
    "Levofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ واسع المدى.", "renal_limit": 50, "renal_note": "⚖️ ضرورة تعديل الجرعة (تصفية < 50)."},
    "Ofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ واسع المدى.", "renal_limit": 50, "renal_note": "⚖️ ضرورة تعديل الجرعة (تصفية < 50)."},
    "Ceftriaxone": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ يفضل استخدامه بحذر.", "renal_limit": 10, "renal_note": "🟢 آمن كلوياً (إطراح مزدوج)."},
    "Gentamicin": {"priority": 3, "class": "Aminoglycoside", "note": "⚠️ حقن قوية.", "renal_limit": 70, "renal_note": "🚫 سمية كلوية عالية؛ تجنبه أو راقب المستويات بدقة."},
    "Meropenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 للطوارئ.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري (تصفية < 50)."},
    "Imipenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 للحالات الحرجة.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري لتجنب التشنجات."}
}

def extract_all_data(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    
    full_text = pytesseract.image_to_string(thresh, config='--psm 6')
    
    # تحسين الاستخراج: البحث فقط في منطقة الحساسية (Sensitive)
    sensitive_section = ""
    text_lower = full_text.lower()
    start_keywords = ["highly", "sensitive", "susceptible"]
    end_keywords = ["resistant", "intermediate"]
    
    start_pos = -1
    for k in start_keywords:
        if text_lower.find(k) != -1:
            start_pos = text_lower.find(k)
            break
            
    end_pos = len(text_lower)
    for k in end_keywords:
        pos = text_lower.find(k, start_pos if start_pos != -1 else 0)
        if pos != -1:
            end_pos = pos
            break
            
    if start_pos != -1:
        sensitive_section = full_text[start_pos:end_pos]
    else:
        sensitive_section = full_text # fallback if headers not found

    detected_drugs = []
    for abx_name in ABX_GUIDELINES.keys():
        if re.search(r'\b' + re.escape(abx_name.lower()) + r'\b', sensitive_section.lower()):
            detected_drugs.append(abx_name)
    
    patient_data = {
        "Age": re.search(r"Age\s*[:/-]?\s*(\d+)", full_text, re.I).group(1) if re.search(r"Age", full_text) else "35",
        "Sex": "Female" if "female" in full_text.lower() else "Male",
        "Organism": re.search(r"Growth\s*[:/-]?\s*([^\n|]+)", full_text, re.I).group(1).strip() if re.search(r"Growth", full_text) else "E. coli"
    }
    return patient_data, list(set(detected_drugs))

# ==========================================
# 🖥️ واجهة التطبيق المحدثة
# ==========================================
st.set_page_config(page_title="Culture Analyzer Pro", layout="wide")
st.title("🛡️ محلل المزارع الذكي (إصدار حساب التصفية التلقائي)")

uploaded = st.file_uploader("ارفع صورة المزرعة", type=['jpg', 'png', 'jpeg'])

if uploaded:
    patient, drugs = extract_all_data(uploaded)
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("👤 بيانات المريض")
        age = st.number_input("العمر", value=int(patient['Age']))
        sex = st.selectbox("الجنس", ["Female", "Male"], index=0 if patient['Sex']=="Female" else 1)
        weight = st.number_input("الوزن (kg)", min_value=10, max_value=200, value=75)
        
        st.divider()
        is_renal = st.checkbox("🚩 تفعيل فحص وظائف الكلى")
        cl_cr = 100
        if is_renal:
            s_creat = st.number_input("مستوى الكرياتينين في الدم (mg/dL)", min_value=0.1, max_value=15.0, value=1.2, step=0.1)
            # معادلة Cockcroft-Gault
            cl_cr = ((140 - age) * weight) / (72 * s_creat)
            if sex == "Female": cl_cr *= 0.85
            
            st.metric("تصفية الكرياتينين المحسوبة (CrCl)", f"{cl_cr:.1f} ml/min")
            if cl_cr < 60: st.warning("هناك انخفاض في كفاءة الكلى.")
        
        is_preg = st.checkbox("حالة حمل؟") if sex == "Female" else False
        st.info(f"**الميكروب المكتشف:** {patient['Organism']}")

    with col2:
        st.subheader(f"✅ المضادات الحساسة المكتشفة ({len(drugs)})")
        allowed, banned, warning_renal = [], [], []
        
        for d in drugs:
            drug_info = ABX_GUIDELINES.get(d, {"priority": 5, "class": "Others", "note": "حسب الحساسية.", "renal_limit": 0, "renal_note": ""})
            
            if is_preg and any(x in d.lower() for x in ["cipro", "levo", "oflox", "tetra", "doxy"]):
                banned.append(f"💊 {d}: خطر على الجنين.")
            elif is_renal and d == "Nitrofurantoin" and cl_cr < 30:
                banned.append(f"💊 {d}: ممنوع في القصور الشديد.")
            elif is_renal and drug_info['renal_limit'] > 0 and cl_cr <= drug_info['renal_limit']:
                warning_renal.append({"name": d, **drug_info})
            else:
                allowed.append({"name": d, **drug_info})

        if banned:
            st.error("🚫 أدوية ممنوعة (حمل/قصور حاد)")
            for b in banned: st.write(b)
        if warning_renal:
            st.warning("⚖️ أدوية تتطلب تعديل جرعة")
            for item in warning_renal:
                with st.expander(f"⚠️ {item['name']} - {item['renal_note']}"):
                    st.write(f"**الملاحظة:** {item['note']}")
        if allowed:
            st.success("🟢 خيارات آمنة/مناسبة")
            for item in sorted(allowed, key=lambda x: x['priority']):
                with st.expander(f"💊 {item['name']}"):
                    st.info(item['note'])

st.caption("ملاحظة برمجية: تم تحسين دقة الاستخراج عبر حصر النص بين قسمي الحساسية والمقاومة.")
