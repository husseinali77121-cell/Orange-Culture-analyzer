import streamlit as st
import numpy as np
import cv2
import pytesseract
import re

# ==========================================
# 📋 قاعدة بيانات شاملة وموسعة للتعرف الذكي
# ==========================================
ABX_GUIDELINES = {
    "Nitrofurantoin": {"priority": 1, "class": "Urinary Antiseptic", "note": "🎯 الخيار الأول للمسالك البولية."},
    "Fosfomycin": {"priority": 1, "class": "Phosphonic Acid", "note": "🎯 خيار مثالي بجرعة واحدة."},
    "Amoxicillin + Clavulanic acid": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي فعال."},
    "Augmentin": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي فعال."},
    "Cephalexin": {"priority": 2, "class": "1st Gen Cephalosporin", "note": "✅ آمن وفعال للحالات البسيطة."},
    "Cefaclor": {"priority": 2, "class": "2nd Gen Cephalosporin", "note": "✅ خيار بديل مستقر."},
    "Doxycycline": {"priority": 2, "class": "Tetracycline", "note": "✅ فعال ولكن يراعى تجنبه في الحمل والأطفال."},
    "Levofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ واسع المدى؛ يستخدم عند الضرورة."},
    "Ofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ واسع المدى؛ يستخدم عند الضرورة."},
    "Ceftriaxone": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ واسع المدى؛ يُفضل استخدامه بحذر."},
    "Ceftazidime": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ مضاد قوي للمستشفيات."},
    "Cefepime": {"priority": 3, "class": "4th Gen Cephalosporin", "note": "⚠️ قوي جداً وواسع المدى."},
    "Gentamicin": {"priority": 3, "class": "Aminoglycoside", "note": "⚠️ حقن قوية؛ يجب مراقبة وظائف الكلى."},
    "Gentamycine": {"priority": 3, "class": "Aminoglycoside", "note": "⚠️ حقن قوية؛ يجب مراقبة وظائف الكلى."},
    "Ertapenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 دواء احتياطي قوي جداً."},
    "Imipenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 من أقوى المضادات؛ للحالات الحرجة فقط."},
    "Meropenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 دواء للطوارئ والعناية المركزة."},
    "Piperacillin + Tazobactam": {"priority": 4, "class": "Anti-pseudomonal", "note": "🛑 مضاد حيوي للمستشفيات (Reserve)."},
    "Cefoperazone + Sulbactam": {"priority": 4, "class": "Combined Beta-lactam", "note": "🛑 مضاد احتياطي قوي."},
    "Cefoperazone": {"priority": 4, "class": "3rd Gen Cephalosporin", "note": "🛑 يُستخدم غالباً في حالات معينة بالمستشفى."}
}

# ==========================================
# 🛠️ دالة معالجة الصورة المتقدمة
# ==========================================
def extract_all_data(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    
    # 1. تحسين جودة الصورة (إزالة النويز وزيادة التباين)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

    # 2. استخراج النص بالكامل مع إعدادات تدعم القوائم (--psm 6)
    full_text = pytesseract.image_to_string(thresh, config='--psm 6')
    
    detected_drugs = []
    
    # 3. منطق المطابقة الذكي: فحص كل كلمة مستخرجة مقابل قاعدة البيانات
    lines = full_text.split('\n')
    for line in lines:
        clean_line = line.strip().lower()
        if not clean_line: continue
        
        for abx_name in ABX_GUIDELINES.keys():
            # البحث عن اسم المضاد داخل السطر بأكمله لضمان التقاطه حتى لو وجد رقم بجانبه
            if abx_name.lower() in clean_line:
                detected_drugs.append(abx_name)
    
    # إزالة التكرار
    unique_drugs = list(set(detected_drugs))
    
    # 4. استخراج بيانات المريض الأساسية
    patient_data = {
        "Age": re.search(r"Age\s*[:/-]?\s*(\d+)", full_text, re.I).group(1) if re.search(r"Age", full_text) else "25",
        "Sex": "Female" if "female" in full_text.lower() else "Male",
        "Organism": re.search(r"Growth\s*[:/-]?\s*([^\n|]+)", full_text, re.I).group(1).strip() if re.search(r"Growth", full_text) else "Klebsiella spp."
    }

    return patient_data, unique_drugs

# ==========================================
# 🖥️ واجهة التطبيق (Streamlit)
# ==========================================
st.set_page_config(page_title="Comprehensive Culture Analyzer", layout="wide")
st.title("🛡️ محرك تحليل المزارع الشامل (S-Only)")

uploaded = st.file_uploader("ارفع صورة المزرعة (تأكد من وضوح قائمة Sensitive)", type=['jpg', 'png', 'jpeg'])

if uploaded:
    patient, drugs = extract_all_data(uploaded)
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("👤 بيانات المريض")
        age = st.number_input("العمر", value=int(patient['Age']))
        sex = st.selectbox("الجنس", ["Female", "Male"], index=0 if patient['Sex']=="Female" else 1)
        is_preg = st.checkbox("حالة حمل؟") if sex == "Female" else False
        st.info(f"**الميكروب المكتشف:** {patient['Organism']}")

    with col2:
        st.subheader(f"✅ المضادات الحيوية المكتشفة ({len(drugs)})")
        
        allowed, banned = [], []
        
        for d in drugs:
            # فلترة الممنوعات للحامل
            if is_preg and any(x in d.lower() for x in ["cipro", "levo", "norf", "oflox", "tetra", "doxy"]):
                banned.append(d)
            else:
                info = ABX_GUIDELINES.get(d, {"priority": 5, "class": "Others", "note": "يستخدم حسب تعليمات الطبيب."})
                allowed.append({"name": d, **info})

        # ترتيب النتائج حسب الأولوية الطبيّة
        allowed_sorted = sorted(allowed, key=lambda x: x['priority'])

        for item in allowed_sorted:
            with st.expander(f"💊 {item['name']}"):
                st.write(f"**الفئة:** {item['class']}")
                if item['priority'] == 1:
                    st.success(item['note'])
                elif item['priority'] == 4:
                    st.error(item['note'])
                else:
                    st.info(item['note'])

        if banned:
            st.divider()
            st.subheader("❌ أدوية مستبعدة (ممنوعة للحمل)")
            for b in banned:
                st.error(f"**{b}**: يشكل خطراً على الجنين.")
