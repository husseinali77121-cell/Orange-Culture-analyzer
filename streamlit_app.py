import streamlit as st
import numpy as np
import cv2
import pytesseract
import re

# ==========================================
# 📋 قاعدة بيانات المضادات الحيوية والبروتوكول
# ==========================================
ABX_GUIDELINES = {
    "Sulfamethoxazole + Trimethoprim": {"priority": 2, "class": "Sulfonamide", "note": "✅ فعال لالتهابات المسالك والبروستاتا.", "renal_limit": 30, "renal_note": "⚖️ خفض الجرعة للنصف (CrCl 15-30)."},
    "Nitrofurantoin": {"priority": 1, "class": "Urinary Antiseptic", "note": "🎯 الخيار الأول للمسالك فقط (لا يصل للدم).", "renal_limit": 30, "renal_note": "🚫 ممنوع إذا كانت التصفية < 30."},
    "Amoxicillin + Clavulanic acid": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي واسع المدى.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب (CrCl < 30)."},
    "Augmentin": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب."},
    "Ciprofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ خيار قوي؛ يفضل تجنبه في الحالات البسيطة.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري (CrCl < 50)."},
    "Levofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ يستخدم بحذر؛ واسع المدى جداً.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري (CrCl < 50)."},
    "Ofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ واسع المدى.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة (CrCl < 50)."},
    "Ceftriaxone": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "🟢 آمن كلوياً (إطراح مزدوج).", "renal_limit": 0, "renal_note": ""},
    "Cefepime": {"priority": 3, "class": "4th Gen Cephalosporin", "note": "🛑 مضاد قوي للمستشفيات.", "renal_limit": 50, "renal_note": "🛑 خطر سمية عصبية إذا لم تعدل الجرعة."},
    "Amikacin": {"priority": 3, "class": "Aminoglycoside", "note": "⚠️ مراقبة وظائف الكلى ضرورية جداً.", "renal_limit": 50, "renal_note": "🚫 خطر سمية كلوية عالية."},
    "Gentamicin": {"priority": 3, "class": "Aminoglycoside", "note": "⚠️ سمية كلوية عالية.", "renal_limit": 70, "renal_note": "🚫 حذر شديد (CrCl < 70)."},
    "Meropenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 دواء احتياطي للحالات المعقدة.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري (CrCl < 50)."},
    "Imipenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 مضاد للطوارئ.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب."},
    "Doxycycline": {"priority": 2, "class": "Tetracycline", "note": "✅ آمن كلوياً بشكل عام.", "renal_limit": 0, "renal_note": "🟢 لا يحتاج تعديل جرعة."},
}

def process_image(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    
    text = pytesseract.image_to_string(thresh, config='--psm 3').lower()
    
    # استخراج البيانات
    age_match = re.search(r"age\s*[:/-]?\s*(\d+)", text)
    sex = "Female" if "female" in text else "Male"
    
    # البحث الشامل لتقليل أخطاء الـ OCR
    detected = [abx for abx in ABX_GUIDELINES.keys() if re.search(r'\b' + re.escape(abx.lower()) + r'\b', text)]
    
    return (age_match.group(1) if age_match else "35"), sex, list(set(detected))

# ==========================================
# 🖥️ واجهة التطبيق - Orange Lab
# ==========================================
st.set_page_config(page_title="Orange Lab Analyzer", layout="wide")
st.title("🛡️ محلل المزارع الذكي - Orange Lab")

file = st.file_uploader("ارفع صورة المزرعة", type=['jpg', 'png', 'jpeg'])

if file:
    age_str, sex_detected, drugs_found = process_image(file)
    
    col1, col2 = st.columns([1, 1.3])
    
    with col1:
        st.subheader("👤 بيانات المريض")
        age = st.number_input("العمر", value=int(age_str))
        sex = st.radio("الجنس", ["Male", "Female"], index=1 if sex_detected=="Female" else 0)
        
        # التصحيح: يظهر للإناث فقط
        is_preg = False
        if sex == "Female":
            is_preg = st.checkbox("🤰 حالة حمل؟")
        
        st.divider()
        is_renal_patient = st.checkbox("🚩 مريض كلى؟ (لحساب الجرعة)")
        
        crcl = 100
        if is_renal_patient:
            weight = st.number_input("الوزن (kg)", value=75)
            s_creat = st.number_input("الكرياتينين (Serum Creatinine)", value=1.2, step=0.1)
            crcl = ((140 - age) * weight) / (72 * s_creat)
            if sex == "Female": crcl *= 0.85
            st.warning(f"تصفية الكرياتينين: {crcl:.1f} ml/min")

    with col2:
        st.subheader("💊 الأدوية الحساسة (Sensitive)")
        
        # دمج المكتشف مع إمكانية التعديل
        manual_list = st.multiselect("➕ المضادات المكتشفة (أضف الناقص):", 
                                   options=sorted(list(ABX_GUIDELINES.keys())), 
                                   default=drugs_found)
        
        custom_input = st.text_input("📝 دواء غير مدرج بالقائمة؟")
        final_list = list(set(manual_list + ([custom_input] if custom_input else [])))
        
        st.divider()
        for d in final_list:
            info = ABX_GUIDELINES.get(d)
            if info:
                # فحص الحمل أولاً
                if is_preg and any(x in d.lower() for x in ["cipro", "levo", "oflox", "tetra", "doxy"]):
                    with st.expander(f"❌ {d} - ممنوع للحامل"):
                        st.error("🚫 خطر على الجنين.")
                # فحص الكلى ثانياً
                elif is_renal_patient and info['renal_limit'] > 0 and crcl <= info['renal_limit']:
                    with st.expander(f"⚠️ {d} - تعديل جرعة"):
                        st.warning(info['renal_note'])
                else:
                    with st.expander(f"✅ {d} - متاح"):
                        st.success(info['note'])
            else:
                st.info(f"🔹 {d}: يرجى مراجعة الجرعة يدوياً.")

st.divider()
st.caption("تطوير : دكتور حسين علي / معمل اورانج لاب اكتوبر / Orange lab")
