import streamlit as st
import numpy as np
import cv2
import pytesseract
import re

# ==========================================
# 📋 قاعدة بيانات المضادات (مرتبة حسب الأولوية والاحتياج الكلوي)
# ==========================================
ABX_GUIDELINES = {
    "Nitrofurantoin": {"priority": 1, "class": "Urinary Antiseptic", "note": "🎯 الخيار الأول للمسالك.", "renal_limit": 30, "renal_note": "🚫 ممنوع إذا كانت التصفية < 30."},
    "Fosfomycin": {"priority": 1, "class": "Phosphonic Acid", "note": "🎯 خيار مثالي بجرعة واحدة.", "renal_limit": 10, "renal_note": "⚠️ حذر في القصور الشديد."},
    "Amoxicillin + Clavulanic acid": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة إذا كانت التصفية < 30."},
    "Augmentin": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة إذا كانت التصفية < 30."},
    "Cephalexin": {"priority": 2, "class": "1st Gen Cephalosporin", "note": "✅ آمن وفعال.", "renal_limit": 40, "renal_note": "⚖️ مباعدة الجرعات في القصور المتوسط/الشديد."},
    "Cefaclor": {"priority": 2, "class": "2nd Gen Cephalosporin", "note": "✅ خيار بديل مستقر.", "renal_limit": 10, "renal_note": "⚠️ تقليل الجرعة في الفشل النهائي."},
    "Doxycycline": {"priority": 2, "class": "Tetracycline", "note": "✅ آمن كلوياً.", "renal_limit": 0, "renal_note": "🟢 آمن لمرضى الكلى."},
    "Levofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ واسع المدى.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة (تصفية < 50)."},
    "Ofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ واسع المدى.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة (تصفية < 50)."},
    "Ceftriaxone": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ يفضل استخدامه بحذر.", "renal_limit": 10, "renal_note": "🟢 آمن كلوياً (إطراح مزدوج)."},
    "Ceftazidime": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ مضاد للمستشفيات.", "renal_limit": 50, "renal_note": "⚖️ تعديل دقيق حسب التصفية."},
    "Cefepime": {"priority": 3, "class": "4th Gen Cephalosporin", "note": "⚠️ قوي جداً.", "renal_limit": 50, "renal_note": "🛑 خطر سمية عصبية (تصفية < 50)."},
    "Gentamicin": {"priority": 3, "class": "Aminoglycoside", "note": "⚠️ حقن قوية.", "renal_limit": 70, "renal_note": "🚫 سمية كلوية عالية؛ تجنبه قدر الإمكان."},
    "Gentamycin": {"priority": 3, "class": "Aminoglycoside", "note": "⚠️ حقن قوية.", "renal_limit": 70, "renal_note": "🚫 سمية كلوية عالية."},
    "Imipenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 للحالات الحرجة.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة لتجنب التشنجات."},
    "Meropenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 للطوارئ.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري (تصفية < 50)."},
    "Piperacillin + Tazobactam": {"priority": 4, "class": "Anti-pseudomonal", "note": "🛑 مضاد احتياطي.", "renal_limit": 40, "renal_note": "⚖️ تعديل الجرعة (تصفية < 40)."}
}

def extract_all_data(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    full_text = pytesseract.image_to_string(thresh, config='--psm 6')
    
    # محاولة حصر النص في قسم الـ Sensitive
    text_lower = full_text.lower()
    start_pos = text_lower.find("highly")
    end_pos = text_lower.find("resistant")
    
    search_area = full_text[start_pos:end_pos] if (start_pos != -1 and end_pos != -1) else full_text

    detected_drugs = []
    for abx_name in ABX_GUIDELINES.keys():
        if re.search(r'\b' + re.escape(abx_name.lower()) + r'\b', search_area.lower()):
            detected_drugs.append(abx_name)
    
    age_match = re.search(r"Age\s*[:/-]?\s*(\d+)", full_text, re.I)
    patient_data = {
        "Age": age_match.group(1) if age_match else "49",
        "Sex": "Female" if "female" in full_text.lower() else "Male",
        "Organism": "Klebsiella spp." if "klebsiella" in full_text.lower() else "E. coli"
    }
    return patient_data, list(set(detected_drugs))

# ==========================================
# 🖥️ واجهة التطبيق
# ==========================================
st.set_page_config(page_title="Lab Culture Pro", layout="wide")
st.title("🛡️ محلل المزارع الذكي (المسح الضوئي + الإدخال اليدوي)")

uploaded = st.file_uploader("ارفع صورة المزرعة", type=['jpg', 'png', 'jpeg'])

if uploaded:
    patient, drugs = extract_all_data(uploaded)
    col1, col2 = st.columns([1, 1.5])
    
    with col1:
        st.subheader("👤 بيانات المريض")
        age = st.number_input("العمر", value=int(patient['Age']))
        sex = st.selectbox("الجنس", ["Female", "Male"], index=0 if patient['Sex']=="Female" else 1)
        weight = st.number_input("الوزن (kg)", min_value=10, value=70)
        
        st.divider()
        is_renal = st.checkbox("🚩 فحص وظائف الكلى (CrCl)")
        cl_cr = 100
        if is_renal:
            s_creat = st.number_input("الكرياتينين (Serum Creatinine)", min_value=0.1, value=1.0)
            cl_cr = ((140 - age) * weight) / (72 * s_creat)
            if sex == "Female": cl_cr *= 0.85
            st.metric("تصفية الكرياتينين", f"{cl_cr:.1f} ml/min")
        
        is_preg = st.checkbox("حالة حمل؟") if sex == "Female" else False

    with col2:
        st.subheader("💊 المضادات الحيوية (Sensitive)")
        
        # خانة الإضافة اليدوية للأدوية التي لم يكتشفها الـ OCR
        manual_add = st.multiselect(
            "➕ أضف يدوياً المضادات الحساسة التي لم تظهر في المسح:",
            options=[k for k in ABX_GUIDELINES.keys() if k not in drugs],
            help="إذا كان هناك دواء في التقرير ولم يقرأه البرنامج، اختره من هنا."
        )
        
        # دمج الأدوية (المكتشفة + اليدوية)
        total_drugs = list(set(drugs + manual_add))
        
        st.info(f"إجمالي الأدوية الخاضعة للتحليل: {len(total_drugs)}")
        
        allowed, banned, warnings = [], [], []
        
        for d in total_drugs:
            info = ABX_GUIDELINES.get(d, {"priority": 5, "class": "Others", "note": "حسب الحساسية.", "renal_limit": 0, "renal_note": ""})
            
            if is_preg and any(x in d.lower() for x in ["cipro", "levo", "oflox", "tetra", "doxy"]):
                banned.append(f"💊 {d}: خطر على الجنين.")
            elif is_renal and d == "Nitrofurantoin" and cl_cr < 30:
                banned.append(f"💊 {d}: غير فعال/ممنوع (CrCl < 30).")
            elif is_renal and info['renal_limit'] > 0 and cl_cr <= info['renal_limit']:
                warnings.append({"name": d, **info})
            else:
                allowed.append({"name": d, **info})

        # عرض النتائج النهائية
        if banned:
            st.error("🚫 أدوية ممنوعة للحالة")
            for b in banned: st.write(b)
            
        if warnings:
            st.warning("⚖️ أدوية تتطلب تعديل جرعة")
            for item in warnings:
                with st.expander(f"⚠️ {item['name']} - {item['renal_note']}"):
                    st.write(item['note'])

        if allowed:
            st.success("🟢 خيارات آمنة أو مناسبة")
            for item in sorted(allowed, key=lambda x: x['priority']):
                with st.expander(f"💊 {item['name']}"):
                    st.write(f"**الفئة:** {item['class']}")
                    st.info(item['note'])

st.caption("دكتور حسين، يمكنك الآن اختيار أي دواء ناقص من القائمة المنسدلة وسيقوم النظام فوراً بمعاملته كدواء حساس (Sensitive).")
