import streamlit as st
import pandas as pd
import numpy as np
import cv2
import pytesseract
import re

# ==========================================
# 📋 قاعدة البيانات الطبية الموسعة (Medscape/IDSA 2026)
# ==========================================
# الترتيب: 1 (الأفضل للمسالك)، 4 (الأقوى ويترك للحالات الحرجة)
ABX_GUIDELINES = {
    "Nitrofurantoin": {"priority": 1, "class": "Urinary Antiseptic", "note": "🎯 الخيار الأول للمسالك البولية (Targeted)."},
    "Fosfomycin": {"priority": 1, "class": "Phosphonic Acid", "note": "🎯 خيار مثالي بجرعة واحدة."},
    "Cephalexin": {"priority": 2, "class": "1st Gen Cephalosporin", "note": "✅ آمن وفعال في الحالات البسيطة."},
    "Cefaclor": {"priority": 2, "class": "2nd Gen Cephalosporin", "note": "✅ خيار بديل مستقر."},
    "Augmentin": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ واسع المدى للحالات المتوسطة."},
    "Amoxicillin + Clavulanic acid": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي فعال."},
    "Ceftriaxone": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ واسع المدى جداً؛ يُفضل استخدامه بحذر."},
    "Ceftazidime": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ مضاد قوي، يُستخدم غالباً في المستشفيات."},
    "Gentamicin": {"priority": 3, "class": "Aminoglycoside", "note": "⚠️ حقن قوية؛ يجب مراقبة وظائف الكلى."},
    "Gentamycine": {"priority": 3, "class": "Aminoglycoside", "note": "⚠️ حقن قوية؛ يجب مراقبة وظائف الكلى."},
    "Piperacillin + Tazobactam": {"priority": 4, "class": "Anti-pseudomonal", "note": "🛑 دواء احتياطي قوي جداً للحالات الشديدة."},
    "Cefoperazone + Sulbactam": {"priority": 4, "class": "Combined Beta-lactam", "note": "🛑 مضاد حيوي للمستشفيات (Reserve)."},
    "Imipenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 من أقوى المضادات؛ يُمنع استخدامه إلا في حالات الضرورة القصوى."},
    "Meropenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 دواء للطوارئ والعناية المركزة."}
}

# ==========================================
# 🛠️ معالجة الصورة واستخراج البيانات
# ==========================================
def clean_and_extract_sensitive(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # تحسين النص (Otsu Thresholding)
    processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    
    # تقسيم الصورة للتركيز على عمود Sensitive (أول 45% من العرض)
    h, w = processed.shape
    sensitive_zone = processed[:, :int(w * 0.45)]
    
    # استخراج النصوص
    raw_text = pytesseract.image_to_string(sensitive_zone, config='--psm 6')
    full_text_report = pytesseract.image_to_string(processed) # للبيانات العامة

    detected_drugs = []
    for line in raw_text.split('\n'):
        line_clean = line.strip()
        # فحص وجود الدواء في قاعدة البيانات
        for abx in ABX_GUIDELINES.keys():
            # استخدام البحث عن أجزاء الكلمات لضمان دمج الأسماء المركبة
            if abx.lower() in line_clean.lower() or line_clean.lower() in abx.lower():
                if len(line_clean) > 3:
                    detected_drugs.append(abx)
                    break
    
    # استخراج بيانات المريض (Regex)
    patient = {
        "Age": re.search(r"Age\s*[:/-]?\s*(\d+)", full_text_report, re.I).group(1) if re.search(r"Age", full_text_report) else "25",
        "Sex": "Female" if "female" in full_text_report.lower() else "Male",
        "Organism": re.search(r"Growth\s*[:/-]?\s*([^\n|]+)", full_text_report, re.I).group(1).strip() if re.search(r"Growth", full_text_report) else "E.coli"
    }

    return patient, list(set(detected_drugs))

# ==========================================
# 🖥️ واجهة المستخدم (Streamlit UI)
# ==========================================
st.set_page_config(page_title="Culture AI Expert", layout="wide")
st.title("🧬 محرك تحليل المزارع الذكي (S-Only)")
st.info("هذا النظام يقوم بفلترة الأدوية وترتيبها من الأنسب (Top) إلى الأقوى (Reserve) مع حذف الممنوعات.")

uploaded = st.file_uploader("ارفع صورة المزرعة هنا", type=['jpg', 'png', 'jpeg'])

if uploaded:
    patient, sensitive_list = clean_and_extract_sensitive(uploaded)
    
    col_p, col_r = st.columns([1, 2])
    
    with col_p:
        st.subheader("👤 بيانات المريض")
        p_age = st.number_input("العمر", value=int(patient['Age']))
        p_sex = st.selectbox("الجنس", ["Female", "Male"], index=0 if patient['Sex']=="Female" else 1)
        is_preg = st.checkbox("هل توجد حالة حمل؟") if p_sex == "Female" else False
        st.warning(f"**الميكروب:** {patient['Organism']}")

    with col_r:
        st.subheader("✅ الأدوية المقترحة (مرتبة حسب الأولوية)")
        
        allowed_list = []
        banned_list = []

        for drug in sensitive_list:
            # منطق الحذف بناءً على الـ Guidelines للممنوعات
            is_banned = False
            reason = ""
            
            if is_preg:
                if any(x in drug.lower() for x in ["cipro", "levo", "norf"]):
                    is_banned = True
                    reason = "ممنوع في الحمل (خطر على غضاريف الجنين)."
                elif any(x in drug.lower() for x in ["tetra", "doxy"]):
                    is_banned = True
                    reason = "ممنوع في الحمل (تأثير على عظام وأسنان الجنين)."

            if is_banned:
                banned_list.append({"drug": drug, "reason": reason})
            else:
                # إضافة الأدوية المسموحة مع بياناتها من ABX_GUIDELINES
                data = ABX_GUIDELINES.get(drug, {"priority": 5, "class": "Others", "note": "يستخدم حسب رؤية الطبيب."})
                allowed_list.append({
                    "drug": drug,
                    "priority": data['priority'],
                    "class": data['class'],
                    "note": data['note']
                })

        # الترتيب من الأولوية 1 إلى 4
        allowed_sorted = sorted(allowed_list, key=lambda x: x['priority'])

        if not allowed_sorted:
            st.error("لم يتم العثور على أدوية مناسبة أو المزرعة مقاومة لكل المضادات.")
        else:
            for item in allowed_sorted:
                with st.expander(f"💊 {item['drug']}"):
                    st.write(f"**التصنيف:** {item['class']}")
                    if item['priority'] == 1:
                        st.success(item['note'])
                    elif item['priority'] == 4:
                        st.error(item['note'])
                    else:
                        st.info(item['note'])

        if banned_list:
            st.divider()
            st.subheader("❌ أدوية تم استبعادها (Contraindicated)")
            for b in banned_list:
                st.error(f"**{b['drug']}**: {b['reason']}")

st.sidebar.markdown("""
### 📘 معايير الترتيب:
1. **الخيار الأول:** أدوية متخصصة للمسالك البولية (Targeted).
2. **الخيار الثاني:** أدوية واسعة المدى (Standard).
3. **الأدوية الاحتياطية:** أدوية قوية جداً تُترك للحالات الصعبة (Reserve).
""")
