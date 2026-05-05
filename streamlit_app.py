import streamlit as st
import numpy as np
import cv2
import pytesseract
import re

# ==========================================
# 📋 قاعدة بيانات شاملة للتعرف الذكي وبروتوكول الكلى
# ==========================================
ABX_GUIDELINES = {
    "Nitrofurantoin": {"priority": 1, "class": "Urinary Antiseptic", "note": "🎯 الخيار الأول للمسالك البولية.", "renal_limit": 30, "renal_note": "🚫 ممنوع إذا كانت التصفية < 30 مل/د (فقدان الفعالية وخطر السمية)."},
    "Fosfomycin": {"priority": 1, "class": "Phosphonic Acid", "note": "🎯 خيار مثالي بجرعة واحدة.", "renal_limit": 10, "renal_note": "⚠️ يستخدم بحذر في القصور الشديد."},
    "Amoxicillin + Clavulanic acid": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي فعال.", "renal_limit": 30, "renal_note": "⚖️ يتطلب تعديل الجرعة (تقليل التكرار) إذا كانت التصفية < 30."},
    "Augmentin": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي فعال.", "renal_limit": 30, "renal_note": "⚖️ يتطلب تعديل الجرعة إذا كانت التصفية < 30."},
    "Cephalexin": {"priority": 2, "class": "1st Gen Cephalosporin", "note": "✅ آمن وفعال.", "renal_limit": 40, "renal_note": "⚖️ يحتاج مباعدة الجرعات في القصور المتوسط والشديد."},
    "Cefaclor": {"priority": 2, "class": "2nd Gen Cephalosporin", "note": "✅ خيار بديل مستقر.", "renal_limit": 10, "renal_note": "⚠️ تقليل الجرعة في الفشل الكلوي النهائي."},
    "Doxycycline": {"priority": 2, "class": "Tetracycline", "note": "✅ آمن كلوياً؛ لا يتطلب تعديل جرعة.", "renal_limit": 0, "renal_note": "🟢 آمن لمرضى الكلى."},
    "Levofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ واسع المدى.", "renal_limit": 50, "renal_note": "⚖️ ضرورة تعديل الجرعة (تصفية < 50)."},
    "Ofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ واسع المدى.", "renal_limit": 50, "renal_note": "⚖️ ضرورة تعديل الجرعة (تصفية < 50)."},
    "Ceftriaxone": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ يفضل استخدامه بحذر.", "renal_limit": 10, "renal_note": "🟢 آمن كلوياً (إطراح مزدوج)؛ لا يتجاوز 2 جم يومياً في القصور الشديد."},
    "Ceftazidime": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ مضاد للمستشفيات.", "renal_limit": 50, "renal_note": "⚖️ يتطلب تعديلاً دقيقاً حسب مستوى التصفية."},
    "Cefepime": {"priority": 3, "class": "4th Gen Cephalosporin", "note": "⚠️ قوي جداً.", "renal_limit": 50, "renal_note": "🛑 خطر سمية عصبية إذا لم تُعدل الجرعة (تصفية < 50)."},
    "Gentamicin": {"priority": 3, "class": "Aminoglycoside", "note": "⚠️ حقن قوية.", "renal_limit": 70, "renal_note": "🚫 سمية كلوية عالية؛ تجنبه أو استخدم جرعة واحدة فقط مع مراقبة المستويات."},
    "Gentamycine": {"priority": 3, "class": "Aminoglycoside", "note": "⚠️ حقن قوية.", "renal_limit": 70, "renal_note": "🚫 سمية كلوية عالية؛ تجنبه أو استخدم جرعة واحدة فقط."},
    "Ertapenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 دواء احتياطي.", "renal_limit": 30, "renal_note": "⚖️ خفض الجرعة إلى 500 ملجم إذا كانت التصفية < 30."},
    "Imipenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 للحالات الحرجة.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري لتجنب التشنجات."},
    "Meropenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 للطوارئ.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري (تصفية < 50)."},
    "Piperacillin + Tazobactam": {"priority": 4, "class": "Anti-pseudomonal", "note": "🛑 مضاد احتياطي.", "renal_limit": 40, "renal_note": "⚖️ تعديل الجرعة مطلوب إذا كانت التصفية < 40."},
    "Cefoperazone + Sulbactam": {"priority": 4, "class": "Combined Beta-lactam", "note": "🛑 مضاد احتياطي قوي.", "renal_limit": 30, "renal_note": "⚠️ سلفاكتام يتطلب تعديلاً إذا كانت التصفية < 30."}
}

def extract_all_data(uploaded_file):
    # معالجة الصورة
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    
    # تحويل الصورة لنص
    full_text = pytesseract.image_to_string(thresh, config='--psm 6')
    
    # استخراج المضادات المكتشفة
    detected_drugs = []
    lines = full_text.split('\n')
    for line in lines:
        clean_line = line.strip().lower()
        if not clean_line: continue
        for abx_name in ABX_GUIDELINES.keys():
            if abx_name.lower() in clean_line:
                detected_drugs.append(abx_name)
    
    unique_drugs = list(set(detected_drugs))
    
    # استخراج بيانات المريض
    age_match = re.search(r"Age\s*[:/-]?\s*(\d+)", full_text, re.I)
    org_match = re.search(r"Growth\s*[:/-]?\s*([^\n|]+)", full_text, re.I)
    
    patient_data = {
        "Age": age_match.group(1) if age_match else "25",
        "Sex": "Female" if "female" in full_text.lower() else "Male",
        "Organism": org_match.group(1).strip() if org_match else "Klebsiella spp."
    }
    return patient_data, unique_drugs

# ==========================================
# 🖥️ واجهة التطبيق
# ==========================================
st.set_page_config(page_title="Renal-Aware Culture Analyzer", layout="wide")
st.title("🛡️ محرك تحليل المزارع الذكي (بروتوكول الكلى المدمج)")

uploaded = st.file_uploader("ارفع صورة المزرعة", type=['jpg', 'png', 'jpeg'])

if uploaded:
    patient, drugs = extract_all_data(uploaded)
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("👤 بيانات المريض")
        age = st.number_input("العمر", value=int(patient['Age']))
        sex = st.selectbox("الجنس", ["Female", "Male"], index=0 if patient['Sex']=="Female" else 1)
        
        st.divider()
        is_renal = st.checkbox("🚩 هل المريض يعاني من قصور كلوي؟")
        cl_cr = 100
        if is_renal:
            cl_cr = st.number_input("تصفية الكرياتينين (CrCl ml/min)", min_value=5, max_value=150, value=30)
            st.caption("يُنصح باستخدام معادلة Cockcroft-Gault لحساب التصفية.")
        
        is_preg = st.checkbox("حالة حمل؟") if sex == "Female" else False
        st.info(f"**الميكروب المكتشف:** {patient['Organism']}")

    with col2:
        st.subheader(f"✅ تحليل المضادات الحيوية المكتشفة ({len(drugs)})")
        allowed, banned, warning_renal = [], [], []
        
        for d in drugs:
            drug_info = ABX_GUIDELINES.get(d, {"priority": 5, "class": "Others", "note": "يستخدم حسب التعليمات.", "renal_limit": 0, "renal_note": ""})
            
            # 1. فلترة الحمل (الأدوية الممنوعة للحامل)
            if is_preg and any(x in d.lower() for x in ["cipro", "levo", "norf", "oflox", "tetra", "doxy"]):
                banned.append(f"💊 {d}: خطر على الجنين.")
            
            # 2. فلترة الكلى (الموانع القطعية)
            elif is_renal and d == "Nitrofurantoin" and cl_cr < 30:
                banned.append(f"💊 {d}: ممنوع في القصور الكلوي الشديد (فقدان الفعالية).")
            
            # 3. تحذيرات التعديل والسمية
            else:
                if is_renal and drug_info['renal_limit'] > 0 and cl_cr <= drug_info['renal_limit']:
                    warning_renal.append({"name": d, **drug_info})
                else:
                    allowed.append({"name": d, **drug_info})

        # عرض النتائج
        if banned:
            st.error("🚫 أدوية ممنوعة للحالة (حمل أو قصور كلوي حاد)")
            for b in banned: st.write(b)

        if warning_renal:
            st.warning("⚖️ أدوية تتطلب تعديل جرعة أو حذر شديد")
            for item in warning_renal:
                with st.expander(f"⚠️ {item['name']} - {item['renal_note']}"):
                    st.write(f"**الفئة:** {item['class']}")
                    st.write(f"**ملاحظة طبية:** {item['note']}")

        if allowed:
            st.success("🟢 أدوية آمنة أو مناسبة (مع مراعاة الجرعات القياسية)")
            allowed_sorted = sorted(allowed, key=lambda x: x['priority'])
            for item in allowed_sorted:
                with st.expander(f"💊 {item['name']}"):
                    st.write(f"**الفئة:** {item['class']}")
                    st.info(item['note'])

st.caption("ملاحظة: هذا النظام أداة مساعدة للطبيب ولا يغني عن الاستشارة السريرية المباشرة.")
