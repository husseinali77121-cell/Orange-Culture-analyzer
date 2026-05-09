import streamlit as st
import numpy as np
import cv2
import pytesseract
import re

# ==========================================
# 📋 Comprehensive Antibiotics Database
# ==========================================
ABX_GUIDELINES = {
    # Urinary Antiseptics
    "Nitrofurantoin": {"priority": 1, "class": "Urinary Antiseptic", "note": "🎯 الخيار الأول للمسالك.", "renal_limit": 30, "renal_note": "🚫 ممنوع إذا كانت التصفية < 30 مل/د (فقدان الفعالية)."},
    "Fosfomycin": {"priority": 1, "class": "Phosphonic Acid", "note": "🎯 خيار مثالي بجرعة واحدة.", "renal_limit": 10, "renal_note": "⚠️ يستخدم بحذر في القصور الشديد."},
    
    # Beta-lactams & Combinations
    "Amoxicillin + Clavulanic acid": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي فعال.", "renal_limit": 30, "renal_note": "⚖️ يتطلب تعديل الجرعة إذا التصفية < 30."},
    "Augmentin": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي فعال.", "renal_limit": 30, "renal_note": "⚖️ يتطلب تعديل الجرعة إذا التصفية < 30."},
    "Piperacillin + Tazobactam": {"priority": 4, "class": "Anti-pseudomonal", "note": "🛑 مضاد احتياطي واسع الطيف.", "renal_limit": 40, "renal_note": "⚖️ يتطلب تعديلاً دقيقاً للجرعة."},
    
    # Cephalosporins
    "Cephalexin": {"priority": 2, "class": "1st Gen Cephalosporin", "note": "✅ آمن وفعال للالتهابات البسيطة.", "renal_limit": 40, "renal_note": "⚖️ يحتاج مباعدة الجرعات في القصور المتوسط."},
    "Ceftriaxone": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ يفضل استخدامه بحذر; حقن.", "renal_limit": 10, "renal_note": "🟢 آمن كلوياً (إطراح مزدوج)."},
    "Cefepime": {"priority": 3, "class": "4th Gen Cephalosporin", "note": "⚠️ قوي جداً للحالات الحرجة.", "renal_limit": 50, "renal_note": "🛑 خطر سمية عصبية إذا لم تعدل الجرعة."},
    
    # Fluoroquinolones
    "Levofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ واسع المدى؛ يفضل ادخاره.", "renal_limit": 50, "renal_note": "⚖️ ضرورة تعديل الجرعة (CrCl < 50)."},
    "Ciprofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ يستخدم بحذر في التهابات المسالك المعقدة.", "renal_limit": 50, "renal_note": "⚖️ يتطلب تعديل الجرعة إذا التصفية < 50."},

    # Others
    "Sulfamethoxazole + Trimethoprim": {"priority": 2, "class": "Sulfonamide", "note": "✅ فعال للمسالك والبروستاتا.", "renal_limit": 30, "renal_note": "⚖️ خفض الجرعة للنصف إذا التصفية < 30."}
}

# قوائم التعرف الآلي
SPECIMEN_TYPES = ["Urine", "Blood", "Sputum", "Wound Swab", "Pus", "Stool", "CSF", "Ear Swab", "Throat Swab"]
BACTERIA_TYPES = [
    "E. coli", "Klebsiella spp.", "Pseudomonas aeruginosa", 
    "Staphylococcus aureus", "MRSA", "Proteus mirabilis", 
    "Enterococcus faecalis", "Acinetobacter baumannii", "Streptococcus"
]

def extract_all_data(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    full_text = pytesseract.image_to_string(thresh, config='--psm 6')
    
    text_lower = full_text.lower()
    
    # 1. التعرف على نوع المزرعة (Specimen)
    detected_specimen = "Urine" # الافتراضي
    for s in SPECIMEN_TYPES:
        if s.lower() in text_lower:
            detected_specimen = s
            break

    # 2. التعرف على نوع البكتيريا (Organism)
    detected_organism = "E. coli" # الافتراضي
    for b in BACTERIA_TYPES:
        if b.lower() in text_lower:
            detected_organism = b
            break

    # 3. استخراج الأدوية الحساسة
    start_pos = text_lower.find("highly")
    end_pos = text_lower.find("resistant")
    search_area = full_text[start_pos:end_pos] if (start_pos != -1 and end_pos != -1) else full_text

    detected_drugs = []
    for abx_name in ABX_GUIDELINES.keys():
        if re.search(r'\b' + re.escape(abx_name.lower()) + r'\b', search_area.lower()):
            detected_drugs.append(abx_name)
    
    # 4. بيانات المريض
    age_match = re.search(r"Age\s*[:/-]?\s*(\d+)", full_text, re.I)
    patient_data = {
        "Age": age_match.group(1) if age_match else "45",
        "Sex": "Female" if "female" in text_lower else "Male",
        "Specimen": detected_specimen,
        "Organism": detected_organism
    }
    return patient_data, list(set(detected_drugs))

# ==========================================
# 🖥️ Interface
# ==========================================
st.set_page_config(page_title="Orange culture analyzer", layout="wide")
st.title("🛡️ Orange Culture Analyzer")

uploaded = st.file_uploader("Upload Culture Report Image", type=['jpg', 'png', 'jpeg'])

if uploaded:
    patient, drugs = extract_all_data(uploaded)
    col1, col2 = st.columns([1, 1.5])
    
    with col1:
        st.subheader("👤 Patient & Report Details")
        
        # عرض وتعديل نوع المزرعة والبكتيريا
        culture_type = st.selectbox("🧫 Specimen Type (نوع المزرعة)", SPECIMEN_TYPES, 
                                     index=SPECIMEN_TYPES.index(patient['Specimen']) if patient['Specimen'] in SPECIMEN_TYPES else 0)
        
        organism_type = st.selectbox("🦠 Identified Bacteria (نوع البكتيريا)", BACTERIA_TYPES,
                                      index=BACTERIA_TYPES.index(patient['Organism']) if patient['Organism'] in BACTERIA_TYPES else 0)
        
        st.divider()
        
        age = st.number_input("Age (Years)", value=int(patient['Age']))
        sex = st.selectbox("Gender", ["Female", "Male"], index=0 if patient['Sex']=="Female" else 1)
        
        is_pediatric = age < 18
        if is_pediatric:
            st.info("👶 **تفعيل تلقائي:** بروتوكول الأطفال نشط.")

        weight = st.number_input("Weight (kg)", min_value=10, value=70 if not is_pediatric else 30)
        
        st.divider()
        is_renal = st.checkbox("🚩 Evaluate Renal Function (CrCl)")
        cl_cr = 100
        if is_renal:
            s_creat = st.number_input("Serum Creatinine (mg/dL)", min_value=0.1, value=1.0, step=0.1)
            cl_cr = ((140 - age) * weight) / (72 * s_creat)
            if sex == "Female": cl_cr *= 0.85
            st.metric("Creatinine Clearance (CrCl)", f"{cl_cr:.1f} ml/min")
        
        is_preg = False
        if sex == "Female" and age >= 12:
            is_preg = st.checkbox("🤰 Is Pregnant?")

    with col2:
        st.subheader("💊 Sensitive Antibiotics (Analysis)")
        st.caption(f"Analysis for: **{organism_type}** found in **{culture_type}**")
        
        manual_add = st.multiselect(
            "➕ Manually add Sensitive Antibiotics:",
            options=[k for k in ABX_GUIDELINES.keys() if k not in drugs]
        )
        
        total_drugs = list(set(drugs + manual_add))
        
        allowed, banned, warnings = [], [], []
        
        for d in total_drugs:
            info = ABX_GUIDELINES.get(d, {"priority": 5, "class": "Others", "note": "يستخدم حسب التعليمات السريرية.", "renal_limit": 0, "renal_note": ""})
            
            # --- Logic Checks ---
            if is_preg and any(x in d.lower() for x in ["cipro", "levo", "oflox", "tetra", "doxy", "genta", "amikacin"]):
                banned.append(f"💊 {d}: خطر على الجنين.")
            elif is_pediatric and age < 8 and any(x in d.lower() for x in ["tetra", "doxy"]):
                banned.append(f"💊 {d}: ممنوع للأطفال (تأثير على العظام/الأسنان).")
            elif is_renal and "nitrofurantoin" in d.lower() and cl_cr < 30:
                banned.append(f"💊 {d}: ممنوع في القصور الكلوي الشديد.")
            elif is_renal and info['renal_limit'] > 0 and cl_cr <= info['renal_limit']:
                warnings.append({"name": d, **info})
            else:
                allowed.append({"name": d, **info})

        # --- Display Results ---
        if banned:
            st.error("🚫 Contraindicated")
            for b in banned: st.write(b)
            
        if warnings:
            st.warning("⚖️ Requires Dose Adjustment")
            for item in warnings:
                with st.expander(f"⚠️ {item['name']}"):
                    st.write(item['note'])
                    st.info(f"Renal Adjustment Limit: {item['renal_limit']} ml/min")

        if allowed:
            st.success("🟢 Generally Safe / Recommended")
            for item in sorted(allowed, key=lambda x: x['priority']):
                with st.expander(f"💊 {item['name']}"):
                    st.write(f"**Class:** {item['class']}")
                    st.info(item['note'])

st.divider()
st.markdown("""
<div style="text-align: center; color: gray; font-size: 0.8em;">
    Developed by: Dr Hussein Ali , Orange Lab
</div>
""", unsafe_allow_html=True)
