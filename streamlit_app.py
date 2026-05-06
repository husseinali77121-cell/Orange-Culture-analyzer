import streamlit as st
import numpy as np
import cv2
import pytesseract
import re

# ==========================================
# 📋 Comprehensive Antibiotics Database (Expanded)
# ==========================================
ABX_GUIDELINES = {
    # Urinary Antiseptics
    "Nitrofurantoin": {"priority": 1, "class": "Urinary Antiseptic", "note": "🎯 الخيار الأول للمسالك.", "renal_limit": 30, "renal_note": "🚫 ممنوع إذا كانت التصفية < 30 مل/د (فقدان الفعالية)."},
    "Fosfomycin": {"priority": 1, "class": "Phosphonic Acid", "note": "🎯 خيار مثالي بجرعة واحدة.", "renal_limit": 10, "renal_note": "⚠️ يستخدم بحذر في القصور الشديد."},
    
    # Beta-lactams & Combinations
    "Amoxicillin + Clavulanic acid": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي فعال.", "renal_limit": 30, "renal_note": "⚖️ يتطلب تعديل الجرعة (تقليل التكرار) إذا التصفية < 30."},
    "Augmentin": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي فعال.", "renal_limit": 30, "renal_note": "⚖️ يتطلب تعديل الجرعة إذا التصفية < 30."},
    "Piperacillin + Tazobactam": {"priority": 4, "class": "Anti-pseudomonal", "note": "🛑 مضاد احتياطي واسع الطيف.", "renal_limit": 40, "renal_note": "⚖️ يتطلب تعديلاً دقيقاً للجرعة حسب مستوى التصفية."},
    "Cefoperazone + Sulbactam": {"priority": 3, "class": "Combined Beta-lactam", "note": "⚠️ مضاد واسع للمستشفيات.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة (بسبب Sulbactam) مطلوب في القصور الشديد."},

    # Cephalosporins
    "Cephalexin": {"priority": 2, "class": "1st Gen Cephalosporin", "note": "✅ آمن وفعال للالتهابات البسيطة.", "renal_limit": 40, "renal_note": "⚖️ يحتاج مباعدة الجرعات في القصور المتوسط والشديد."},
    "Cefaclor": {"priority": 2, "class": "2nd Gen Cephalosporin", "note": "✅ خيار بديل مستقر.", "renal_limit": 10, "renal_note": "⚠️ تقليل الجرعة في الفشل الكلوي النهائي."},
    "Ceftriaxone": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ يفضل استخدامه بحذر; حقن.", "renal_limit": 10, "renal_note": "🟢 آمن كلوياً (إطراح مزدوج)؛ لا يتجاوز 2جم يومياً في القصور الشديد."},
    "Ceftazidime": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ مضاد للمستشفيات (Pseudomonas).", "renal_limit": 50, "renal_note": "⚖️ يتطلب تعديلاً دقيقاً حسب مستوى التصفية."},
    "Cefepime": {"priority": 3, "class": "4th Gen Cephalosporin", "note": "⚠️ قوي جداً للحالات الحرجة.", "renal_limit": 50, "renal_note": "🛑 خطر سمية عصبية (Toxicity) إذا لم تعدل الجرعة (تصفية < 50)."},
    
    # Tetracyclines
    "Doxycycline": {"priority": 2, "class": "Tetracycline", "note": "✅ آمن كلوياً؛ لا يتطلب تعديل جرعة.", "renal_limit": 0, "renal_note": "🟢 آمن لمرضى الكلى."},
    "Tetracycline": {"priority": 2, "class": "Tetracycline", "note": "✅ فعال ولكن تجنبه في الحمل والأطفال.", "renal_limit": 10, "renal_note": "⚖️ يتطلب تعديلاً في الفشل النهائي."},

    # Fluoroquinolones
    "Levofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ واسع المدى؛ يفضل ادخاره.", "renal_limit": 50, "renal_note": "⚖️ ضرورة تعديل الجرعة (CrCl < 50)."},
    "Ofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ واسع المدى.", "renal_limit": 50, "renal_note": "⚖️ ضرورة تعديل الجرعة (CrCl < 50)."},
    "Ciprofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ يستخدم بحذر في التهابات المسالك المعقدة.", "renal_limit": 50, "renal_note": "⚖️ يتطلب تعديل الجرعة إذا التصفية < 50 مل/د."},

    # Aminoglycosides
    "Gentamicin": {"priority": 3, "class": "Aminoglycoside", "note": "⚠️ حقن قوية وريدية/عضلية.", "renal_limit": 70, "renal_note": "🚫 سمية كلوية (Nephrotoxicity) عالية؛ تجنبه قدر الإمكان في القصور الكلوي."},
    "Amikacin": {"priority": 3, "class": "Aminoglycoside", "note": "⚠️ حقن قوية؛ يتطلب مراقبة دقيقة.", "renal_limit": 50, "renal_note": "⚖️ يتطلب تعديلاً دقيقاً للجرعة ومراقبة المستوى بالدم."},

    # Carbapenems
    "Imipenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 مضاد احتياطي للحالات الحرجة.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري لتجنب خطر التشنجات (Seizures)."},
    "Meropenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 للطوارئ والالتهابات المعقدة.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري (CrCl < 50)."},
    "Ertapenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 يستخدم مرة واحدة يومياً.", "renal_limit": 30, "renal_note": "⚖️ يجب خفض الجرعة إلى 500 ملجم يومياً إذا كانت التصفية < 30."},
    
    # Others
    "Sulfamethoxazole + Trimethoprim": {"priority": 2, "class": "Sulfonamide", "note": "✅ فعال للمسالك والبروستاتا.", "renal_limit": 30, "renal_note": "⚖️ يتطلب تعديل الجرعة (خفض الجرعة للنصف) إذا التصفية < 30."}
}

def extract_all_data(uploaded_file):
    # OCR Logic kept exactly as requested
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    full_text = pytesseract.image_to_string(thresh, config='--psm 6')
    
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
# 🖥️ Interface
# ==========================================
st.set_page_config(page_title="Universal Culture & Sensitivity Analyzer", layout="wide")
st.title("🛡️ Universal Culture & Sensitivity Analyzer (OCR + Manual)")

uploaded = st.file_uploader("Upload Culture Report Image", type=['jpg', 'png', 'jpeg'])

if uploaded:
    patient, drugs = extract_all_data(uploaded)
    col1, col2 = st.columns([1, 1.5])
    
    with col1:
        st.subheader("👤 Patient Details")
        age = st.number_input("Age (Years)", value=int(patient['Age']))
        sex = st.selectbox("Gender", ["Female", "Male"], index=0 if patient['Sex']=="Female" else 1)
        
        # Pediatric Notification
        is_pediatric = age < 18
        if is_pediatric:
            st.info("👶 **تفعيل تلقائي:** بروتوكول الأطفال نشط.")

        weight = st.number_input("Weight (kg)", min_value=10, value=70 if not is_pediatric else 30)
        
        st.divider()
        is_renal = st.checkbox("🚩 Evaluate Renal Function (CrCl)")
        cl_cr = 100
        if is_renal:
            s_creat = st.number_input("Serum Creatinine (mg/dL)", min_value=0.1, value=1.0, step=0.1)
            # Cockcroft-Gault Equation
            cl_cr = ((140 - age) * weight) / (72 * s_creat)
            if sex == "Female": cl_cr *= 0.85
            st.metric("Creatinine Clearance (CrCl)", f"{cl_cr:.1f} ml/min")
        
        # Pregnancy logic (hidden if child under 12)
        is_preg = False
        if sex == "Female" and age >= 12:
            is_preg = st.checkbox("🤰 Is Pregnant?")

    with col2:
        st.subheader("💊 Sensitive Antibiotics (Analysis)")
        
        manual_add = st.multiselect(
            "➕ Manually add Sensitive Antibiotics (if OCR missed any):",
            options=[k for k in ABX_GUIDELINES.keys() if k not in drugs],
            help="Select antibiotics marked as 'Sensitive' on the report that were not detected automatically."
        )
        
        total_drugs = list(set(drugs + manual_add))
        st.info(f"Total Antibiotics under Analysis: {len(total_drugs)}")
        
        allowed, banned, warnings = [], [], []
        
        for d in total_drugs:
            info = ABX_GUIDELINES.get(d, {"priority": 5, "class": "Others", "note": "يستخدم حسب التعليمات السريرية.", "renal_limit": 0, "renal_note": ""})
            
            # --- 1. Pregnancy Protocol ---
            if is_preg and any(x in d.lower() for x in ["cipro", "levo", "oflox", "tetra", "doxy", "genta", "amikacin"]):
                banned.append(f"💊 {d}: خطر على الجنين (Teratogenic/Toxicity).")
            
            # --- 2. Pediatric Protocol ---
            elif is_pediatric and age < 8 and any(x in d.lower() for x in ["tetra", "doxy"]):
                banned.append(f"💊 {d}: ممنوع للأطفال < 8 سنوات (تصبغ دائم للأسنان وتأثير على العظام).")
            elif is_pediatric and any(x in d.lower() for x in ["cipro", "levo", "oflox"]):
                banned.append(f"💊 {d}: لا ينصح به للأطفال < 18 سنة (خطر على نمو الغضاريف) إلا للضرورة القصوى.")
            
            # --- 3. Renal Protocol (Absolute contraindications) ---
            elif is_renal and "nitrofurantoin" in d.lower() and cl_cr < 30:
                banned.append(f"💊 {d}: ممنوع في القصور الكلوي الشديد (CrCl < 30) لفقدان الفعالية.")
            
            # --- 4. Warnings (Dose adjustments or minor age limits) ---
            elif is_pediatric and age < 12 and "fosfomycin" in d.lower():
                warnings.append({"name": d, **info, "note": "⚠️ غير معتمد عادة للأطفال أقل من 12 سنة.", "renal_note": "Pediatric Alert"})
            elif is_renal and info['renal_limit'] > 0 and cl_cr <= info['renal_limit']:
                warnings.append({"name": d, **info})
            
            # --- 5. Allowed ---
            else:
                allowed.append({"name": d, **info})

        # --- Display Results ---
        if banned:
            st.error("🚫 Contraindicated / Forbidden for this Case")
            for b in banned: st.write(b)
            
        if warnings:
            st.warning("⚖️ Requires Dose Adjustment or Extreme Caution")
            for item in warnings:
                with st.expander(f"⚠️ {item['name']} - {item.get('renal_note', '')}"):
                    st.write(item['note'])

        if allowed:
            st.success("🟢 Generally Safe / Recommended Options")
            for item in sorted(allowed, key=lambda x: x['priority']):
                with st.expander(f"💊 {item['name']}"):
                    st.write(f"**Class:** {item['class']}")
                    st.info(item['note'])

st.divider()
# Developer Imprint
st.markdown("""
<div style="text-align: center; color: gray; font-size: 0.8em;">
    Developed by Dr. Hussein Ali | Universal Solutions Branch
</div>
""", unsafe_allow_html=True)
