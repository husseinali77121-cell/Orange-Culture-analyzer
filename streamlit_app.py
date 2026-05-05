import streamlit as st
import numpy as np
import cv2
import pytesseract
import re

# ==========================================
# 📋 قاعدة بيانات المضادات الحيوية والبروتوكول الكلوي
# ==========================================
ABX_GUIDELINES = {
    "Sulfamethoxazole + Trimethoprim": {"priority": 2, "class": "Sulfonamide", "note": "✅ فعال لالتهابات المسالك والبروستاتا.", "renal_limit": 30, "renal_note": "⚖️ خفض الجرعة للنصف (CrCl 15-30)."},
    "Nitrofurantoin": {"priority": 1, "class": "Urinary Antiseptic", "note": "🎯 الخيار الأول للمسالك فقط (لا يصل للدم).", "renal_limit": 30, "renal_note": "🚫 ممنوع إذا كانت التصفية < 30."},
    "Amoxicillin + Clavulanic acid": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي واسع المدى.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب (CrCl < 30)."},
    "Augmentin": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب."},
    "Ciprofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ خيار قوي؛ يفضل تجنبه في الحالات البسيطة.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري (CrCl < 50)."},
    "Levofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ يستخدم بحذر؛ واسع المدى جداً.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري (CrCl < 50)."},
    "Ceftriaxone": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "🟢 آمن كلوياً (إطراح مزدوج).", "renal_limit": 0, "renal_note": ""},
    "Cefepime": {"priority": 3, "class": "4th Gen Cephalosporin", "note": "🛑 مضاد قوي للمستشفيات.", "renal_limit": 50, "renal_note": "🛑 خطر سمية عصبية إذا لم تعدل الجرعة."},
    "Amikacin": {"priority": 3, "class": "Aminoglycoside", "note": "⚠️ مراقبة وظائف الكلى ضرورية جداً.", "renal_limit": 50, "renal_note": "🚫 خطر سمية كلوية عالية."},
    "Meropenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 دواء احتياطي للحالات المعقدة.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري (CrCl < 50)."},
}

def process_image(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    text = pytesseract.image_to_string(thresh, config='--psm 6').lower()
    
    # محاولة استخراج منطقة الـ Sensitive فقط
    start = max(text.find("highly"), text.find("sensitive"), 0)
    end = text.find("resistant") if "resistant" in text else len(text)
    roi = text[start:end]

    detected = [abx for abx in ABX_GUIDELINES.keys() if re.search(r'\b' + re.escape(abx.lower()) + r'\b', roi)]
    
    age_match = re.search(r"age\s*[:/-]?\s*(\d+)", text)
    sex = "Female" if "female" in text else "Male"
    return (age_match.group(1) if age_match else "35"), sex, list(set(detected))

# ==========================================
# 🖥️ واجهة التطبيق المستحدثة
# ==========================================
st.set_page_config(page_title="Orange Lab Analyzer", layout="wide")
st.title("🛡️ محلل المزارع الذكي الشامل")

file = st.file_uploader("ارفع صورة المزرعة", type=['jpg', 'png', 'jpeg'])

if file:
    age_str, sex_detected, drugs = process_image(file)
    
    col1, col2 = st.columns([1, 1.3])
    
    with col1:
        st.subheader("👤 بيانات المريض")
        age = st.number_input("العمر", value=int(age_str))
        weight = st.number_input("الوزن (kg)", value=75)
        sex = st.radio("الجنس", ["Male", "Female"], index=0 if sex_detected=="Male" else 1)
        
        st.divider()
        st.write("🧪 **وظائف الكلى**")
        s_creat = st.number_input("الكرياتينين (Serum Creatinine)", value=1.0, step=0.1)
        
        # حساب التصفية آلياً
        crcl = ((140 - age) * weight) / (72 * s_creat)
        if sex == "Female": crcl *= 0.85
        
        color = "green" if crcl > 60 else "orange" if crcl > 30 else "red"
        st.markdown(f"تصفية الكرياتينين: <b style='color:{color}'>{crcl:.1f} ml/min</b>", unsafe_allow_html=True)

    with col2:
        st.subheader("💊 الأدوية الحساسة (Sensitive)")
        
        # الإضافة اليدوية لأي نقص
        manual = st.multiselect("➕ أضف/عدل المضادات الحساسة المكتشفة:", 
                               options=sorted(list(ABX_GUIDELINES.keys())), 
                               default=drugs)
        
        # إضافة دواء غير موجود نهائياً في القائمة
        custom = st.text_input("📝 دواء غير مدرج في القائمة؟ اكتبه هنا:")
        
        final_list = list(set(manual + ([custom] if custom else [])))
        
        st.divider()
        
        if not final_list:
            st.info("لم يتم اكتشاف أدوية تلقائياً. يرجى الاختيار يدوياً.")
        
        for d in final_list:
            info = ABX_GUIDELINES.get(d)
            if info:
                if crcl <= info['renal_limit'] and info['renal_limit'] > 0:
                    with st.expander(f"⚠️ {d} - يحتاج تعديل"):
                        st.error(info['renal_note'])
                        st.caption(info['note'])
                else:
                    with st.expander(f"✅ {d} - خيار متاح"):
                        st.success(info['note'])
            else:
                st.warning(f"🔹 {d}: دواء مضاف يدوياً؛ يرجى مراجعة بروتوكول الجرعة للقصور الكلوي.")

st.divider()
st.caption("تطوير : دكتور حسين علي / معمل اورانج لاب اكتوبر / Orange lab")
