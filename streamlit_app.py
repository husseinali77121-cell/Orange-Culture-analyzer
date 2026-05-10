import streamlit as st
import numpy as np
import cv2
import pytesseract
import re

# ==========================================
# 📋 Comprehensive Antibiotics Database (Expanded)
# ==========================================
ABX_GUIDELINES = {
    # --- Urinary Antiseptics ---
    "Nitrofurantoin": {"priority": 1, "class": "Urinary Antiseptic", "note": "🎯 الخيار الأول للمسالك البسيطة.", "renal_limit": 30, "renal_note": "🚫 ممنوع إذا كانت التصفية < 30 مل/د."},
    "Fosfomycin": {"priority": 1, "class": "Phosphonic Acid", "note": "🎯 خيار مثالي بجرعة واحدة.", "renal_limit": 10, "renal_note": "⚠️ حذر في القصور الشديد."},
    
    # --- Penicillins & Beta-lactamase Inhibitors ---
    "Amoxicillin": {"priority": 3, "class": "Penicillin", "note": "✅ فعال لبعض السلالات، مقاومة عالية غالباً.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب."},
    "Ampicillin": {"priority": 3, "class": "Penicillin", "note": "✅ يستخدم غالباً للـ Enterococcus.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب."},
    "Amoxicillin + Clavulanic acid": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي (Augmentin).", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب."},
    "Augmentin": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي فعال.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب."},
    "Piperacillin + Tazobactam": {"priority": 4, "class": "Anti-pseudomonal", "note": "🛑 مضاد احتياطي واسع الطيف للحالات الشديدة.", "renal_limit": 40, "renal_note": "⚖️ تعديل الجرعة مطلوب."},
    
    # --- Cephalosporins (1st - 5th Gen) ---
    "Cephalexin": {"priority": 2, "class": "1st Gen Cephalosporin", "note": "✅ آمن وفعال للالتهابات البسيطة.", "renal_limit": 40, "renal_note": "⚖️ مباعدة الجرعات مطلوب."},
    "Cefazolin": {"priority": 2, "class": "1st Gen Cephalosporin", "note": "💉 يعطى حقناً، فعال للعمليات الجراحية.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب."},
    "Cefuroxime": {"priority": 2, "class": "2nd Gen Cephalosporin", "note": "✅ فعال للجراثيم الموجبة والسالبة.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب."},
    "Ceftriaxone": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ حقن وريدي؛ يفضل تجنبه في الحالات البسيطة.", "renal_limit": 10, "renal_note": "🟢 آمن كلوياً بشكل عام."},
    "Cefotaxime": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ مشابه للسيفتركسون؛ يستخدم بالمستشفى.", "renal_limit": 20, "renal_note": "⚖️ تعديل الجرعة مطلوب."},
    "Ceftazidime": {"priority": 4, "class": "3rd Gen Cephalosporin", "note": "🛑 فعال جداً ضد Pseudomonas.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب."},
    "Cefixime": {"priority": 2, "class": "3rd Gen Cephalosporin (Oral)", "note": "✅ خيار فموي جيد للمسالك.", "renal_limit": 20, "renal_note": "⚖️ خفض الجرعة."},
    "Cefepime": {"priority": 4, "class": "4th Gen Cephalosporin", "note": "⚠️ قوي جداً للحالات الحرجة والمقاومة.", "renal_limit": 50, "renal_note": "🛑 خطر سمية عصبية إذا لم تعدل الجرعة."},
    
    # --- Carbapenems (Big Guns) ---
    "Imipenem": {"priority": 5, "class": "Carbapenem", "note": "🛑 خيار الملاذ الأخير (ESBL/MDR).", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة لمنع التشنجات."},
    "Meropenem": {"priority": 5, "class": "Carbapenem", "note": "🛑 خيار الملاذ الأخير؛ آمن عصبياً أكثر من إيميبينيم.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب."},
    "Ertapenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 جرعة واحدة يومياً؛ لا يغطي Pseudomonas.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب."},

    # --- Fluoroquinolones ---
    "Ciprofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ يستخدم بحذر في الحالات المعقدة؛ يفضل ادخاره.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب."},
    "Levofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ واسع المدى؛ يغطي الرئة والمسالك.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب."},
    "Norfloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "✅ مخصص لالتهابات المسالك فقط.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب."},
    
    # --- Aminoglycosides ---
    "Amikacin": {"priority": 4, "class": "Aminoglycoside", "note": "💉 حقن؛ فعال جداً ضد السلبيات المقاومة.", "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى ضرورية جداً."},
    "Gentamicin": {"priority": 4, "class": "Aminoglycoside", "note": "💉 حقن؛ يستخدم غالباً كعلاج مضاف.", "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى ضرورية جداً."},
    "Tobramycin": {"priority": 4, "class": "Aminoglycoside", "note": "💉 حقن؛ فعالية قوية ضد Pseudomonas.", "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى."},

    # --- Others ---
    "Sulfamethoxazole + Trimethoprim": {"priority": 2, "class": "Sulfonamide (Bactrim)", "note": "✅ فعال للمسالك والبروستاتا.", "renal_limit": 30, "renal_note": "⚖️ خفض الجرعة للنصف."},
    "Vancomycin": {"priority": 5, "class": "Glycopeptide", "note": "🛑 خاص بـ MRSA والموجبات المقاومة فقط.", "renal_limit": 50, "renal_note": "⚖️ مراقبة المستوى في الدم."},
    "Linezolid": {"priority": 5, "class": "Oxazolidinone", "note": "🛑 للموجبات المقاومة؛ يستخدم بحذر.", "renal_limit": 0, "renal_note": "🟢 لا يحتاج تعديل كلوي."},
    "Clindamycin": {"priority": 3, "class": "Lincosamide", "note": "✅ فعال للالتهابات اللاهوائية والموجبات.", "renal_limit": 0, "renal_note": "🟢 لا يحتاج تعديل كلوي."},
    "Doxycycline": {"priority": 3, "class": "Tetracycline", "note": "✅ فعال لبعض المسببات غير النمطية.", "renal_limit": 0, "renal_note": "🟢 آمن كلوياً."},
    "Colistin": {"priority": 5, "class": "Polymyxin", "note": "🛑 الملاذ الأخير للبكتيريا المقاومة لكل شيء.", "renal_limit": 50, "renal_note": "🛑 سمية كلوية عالية جداً."}
}

# قوائم التعرف الآلي
SPECIMEN_TYPES = ["Urine", "Blood", "Sputum", "Wound Swab", "Pus", "Stool", "CSF", "Ear Swab", "Throat Swab"]
BACTERIA_TYPES = [
    "E. coli", "Klebsiella spp.", "Pseudomonas aeruginosa", 
    "Staphylococcus aureus", "MRSA", "Proteus mirabilis", 
    "Enterococcus faecalis", "Acinetobacter baumannii", "Streptococcus", "Enterobacter"
]

def extract_all_data(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    full_text = pytesseract.image_to_string(thresh, config='--psm 6')
    
    text_lower = full_text.lower()
    
    # 1. التعرف على نوع المزرعة
    detected_specimen = "Urine" # الافتراضي
    for s in SPECIMEN_TYPES:
        if s.lower() in text_lower:
            detected_specimen = s
            break

    # 2. التعرف على نوع البكتيريا
    detected_organism = "E. coli" # الافتراضي
    for b in BACTERIA_TYPES:
        if b.lower() in text_lower:
            detected_organism = b
            break

    # 3. استخراج الأدوية الحساسة
    start_pos = text_lower.find("highly")
    if start_pos == -1: start_pos = text_lower.find("sensitive")
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
        
        # القائمة المنسدلة الآن تحتوي على كل شيء في ABX_GUIDELINES
        manual_add = st.multiselect(
            "➕ Manually add Sensitive Antibiotics (Search here):",
            options=sorted(list(ABX_GUIDELINES.keys()))
        )
        
        total_drugs = list(set(drugs + manual_add))
        
        allowed, banned, warnings = [], [], []
        
        for d in total_drugs:
            info = ABX_GUIDELINES.get(d, {"priority": 5, "class": "Others", "note": "يستخدم حسب التعليمات السريرية.", "renal_limit": 0, "renal_note": ""})
            
            d_low = d.lower()
            # --- Logic Checks ---
            # 1. Pregnancy Contraindications
            preg_banned = ["cipro", "levo", "norflox", "tetra", "doxy", "genta", "amikacin", "tobra", "imipenem", "meropenem"]
            # 2. Pediatric Contraindications
            peds_banned = ["tetra", "doxy", "cipro", "levo"]

            if is_preg and any(x in d_low for x in preg_banned):
                banned.append(f"💊 {d}: غير آمن أثناء الحمل.")
            elif is_pediatric and age < 15 and any(x in d_low for x in ["cipro", "levo"]):
                 banned.append(f"💊 {d}: يفضل تجنبه للأطفال (تأثير على الغضاريف).")
            elif is_pediatric and age < 8 and any(x in d_low for x in ["tetra", "doxy"]):
                banned.append(f"💊 {d}: ممنوع للأطفال (تأثير على الأسنان).")
            elif is_renal and "nitrofurantoin" in d_low and cl_cr < 30:
                banned.append(f"💊 {d}: يفقد فعاليته ويزيد السمية في القصور الكلوي الشديد.")
            elif is_renal and info['renal_limit'] > 0 and cl_cr <= info['renal_limit']:
                warnings.append({"name": d, **info})
            else:
                allowed.append({"name": d, **info})

        # --- Display Results ---
        if banned:
            st.error("🚫 Contraindicated (موانع استخدام)")
            for b in banned: st.write(b)
            
        if warnings:
            st.warning("⚖️ Requires Dose Adjustment (يتطلب تعديل جرعة)")
            for item in warnings:
                with st.expander(f"⚠️ {item['name']}"):
                    st.write(f"**السبب:** {item['renal_note']}")
                    st.info(f"الحد الكلوى: {item['renal_limit']} ml/min")

        if allowed:
            st.success("🟢 Generally Safe / Recommended (خيارات آمنة أو مفضلة)")
            # Sort by priority
            for item in sorted(allowed, key=lambda x: x['priority']):
                with st.expander(f"💊 {item['name']} ({item['class']})"):
                    st.write(item['note'])
                    if is_renal and item['renal_limit'] > 0:
                        st.caption(f"ملاحظة: هذا الدواء يحتاج مراقبة إذا نزلت التصفية عن {item['renal_limit']}")

st.divider()
st.markdown("""
<div style="text-align: center; color: gray; font-size: 0.8em;">
    Developed by: Dr Hussein Ali , Orange Lab <br>
    Note: Clinical judgment should always supersede AI suggestions.
</div>
""", unsafe_allow_html=True)
