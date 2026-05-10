import streamlit as st
import numpy as np
import cv2
import pytesseract
import re
from datetime import datetime

# ==========================================
# 📋 Comprehensive Antibiotics Database (Upgraded)
# ==========================================
# تمت إضافة: aware (تصنيف WHO), high_po (قابلية التحويل لفموي), interacts_with (التفاعلات الدوائية)
ABX_GUIDELINES = {
    # --- Urinary Antiseptics ---
    "Nitrofurantoin": {"priority": 1, "class": "Urinary Antiseptic", "note": "🎯 الخيار الأول للمسالك البسيطة.", "renal_limit": 30, "renal_note": "🚫 ممنوع إذا كانت التصفية < 30 مل/د.", "aware": "Access", "high_po": True, "interacts_with": ["Antacids (مضادات الحموضة)"]},
    "Fosfomycin": {"priority": 1, "class": "Phosphonic Acid", "note": "🎯 خيار مثالي بجرعة واحدة.", "renal_limit": 10, "renal_note": "⚠️ حذر في القصور الشديد.", "aware": "Access", "high_po": True, "interacts_with": []},
    
    # --- Penicillins & Beta-lactamase Inhibitors ---
    "Amoxicillin": {"priority": 3, "class": "Penicillin", "note": "✅ فعال لبعض السلالات، مقاومة عالية غالباً.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Access", "high_po": True, "interacts_with": []},
    "Ampicillin": {"priority": 3, "class": "Penicillin", "note": "✅ يستخدم غالباً للـ Enterococcus.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Access", "high_po": False, "interacts_with": []},
    "Amoxicillin + Clavulanic acid": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي (Augmentin).", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Access", "high_po": True, "interacts_with": []},
    "Augmentin": {"priority": 2, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي فعال.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Access", "high_po": True, "interacts_with": []},
    "Piperacillin + Tazobactam": {"priority": 4, "class": "Anti-pseudomonal", "note": "🛑 مضاد احتياطي واسع الطيف.", "renal_limit": 40, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": False, "interacts_with": []},
    
    # --- Cephalosporins (1st - 5th Gen) ---
    "Cephalexin": {"priority": 2, "class": "1st Gen Cephalosporin", "note": "✅ آمن وفعال للالتهابات البسيطة.", "renal_limit": 40, "renal_note": "⚖️ مباعدة الجرعات مطلوب.", "aware": "Access", "high_po": True, "interacts_with": []},
    "Cefazolin": {"priority": 2, "class": "1st Gen Cephalosporin", "note": "💉 يعطى حقناً، فعال للعمليات الجراحية.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Access", "high_po": False, "interacts_with": []},
    "Cefuroxime": {"priority": 2, "class": "2nd Gen Cephalosporin", "note": "✅ فعال للجراثيم الموجبة والسالبة.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": True, "interacts_with": ["Antacids (مضادات الحموضة)"]},
    "Ceftriaxone": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ حقن وريدي؛ يفضل تجنبه في الحالات البسيطة.", "renal_limit": 10, "renal_note": "🟢 آمن كلوياً بشكل عام.", "aware": "Watch", "high_po": False, "interacts_with": []},
    "Cefotaxime": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ مشابه للسيفتركسون؛ يستخدم بالمستشفى.", "renal_limit": 20, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": False, "interacts_with": []},
    "Ceftazidime": {"priority": 4, "class": "3rd Gen Cephalosporin", "note": "🛑 فعال جداً ضد Pseudomonas.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": False, "interacts_with": []},
    "Cefixime": {"priority": 2, "class": "3rd Gen Cephalosporin (Oral)", "note": "✅ خيار فموي جيد للمسالك.", "renal_limit": 20, "renal_note": "⚖️ خفض الجرعة.", "aware": "Watch", "high_po": True, "interacts_with": []},
    "Cefepime": {"priority": 4, "class": "4th Gen Cephalosporin", "note": "⚠️ قوي جداً للحالات الحرجة والمقاومة.", "renal_limit": 50, "renal_note": "🛑 خطر سمية عصبية.", "aware": "Watch", "high_po": False, "interacts_with": []},
    
    # --- Carbapenems (Big Guns) ---
    "Imipenem": {"priority": 5, "class": "Carbapenem", "note": "🛑 خيار الملاذ الأخير (ESBL/MDR).", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة لمنع التشنجات.", "aware": "Watch", "high_po": False, "interacts_with": []},
    "Meropenem": {"priority": 5, "class": "Carbapenem", "note": "🛑 خيار الملاذ الأخير؛ آمن عصبياً.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": False, "interacts_with": []},
    "Ertapenem": {"priority": 4, "class": "Carbapenem", "note": "🛑 لا يغطي Pseudomonas.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": False, "interacts_with": []},

    # --- Fluoroquinolones ---
    "Ciprofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ يستخدم بحذر؛ يفضل ادخاره.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": True, "interacts_with": ["Antacids (مضادات الحموضة)", "Warfarin (مضادات التخثر)", "NSAIDs (مسكنات الألم)"]},
    "Levofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ يغطي الرئة والمسالك.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": True, "interacts_with": ["Antacids (مضادات الحموضة)", "Warfarin (مضادات التخثر)", "NSAIDs (مسكنات الألم)"]},
    "Norfloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "✅ مخصص لالتهابات المسالك فقط.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": True, "interacts_with": ["Antacids (مضادات الحموضة)"]},
    
    # --- Aminoglycosides ---
    "Amikacin": {"priority": 4, "class": "Aminoglycoside", "note": "💉 فعال ضد السلبيات المقاومة.", "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى.", "aware": "Access", "high_po": False, "interacts_with": ["NSAIDs (مسكنات الألم)"]},
    "Gentamicin": {"priority": 4, "class": "Aminoglycoside", "note": "💉 يستخدم غالباً كعلاج مضاف.", "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى.", "aware": "Access", "high_po": False, "interacts_with": ["NSAIDs (مسكنات الألم)"]},
    "Tobramycin": {"priority": 4, "class": "Aminoglycoside", "note": "💉 فعالية قوية ضد Pseudomonas.", "renal_limit": 60, "renal_note": "⚖️ مراقبة الكلى.", "aware": "Access", "high_po": False, "interacts_with": ["NSAIDs (مسكنات الألم)"]},

    # --- Others ---
    "Sulfamethoxazole + Trimethoprim": {"priority": 2, "class": "Sulfonamide", "note": "✅ فعال للمسالك والبروستاتا.", "renal_limit": 30, "renal_note": "⚖️ خفض الجرعة للنصف.", "aware": "Access", "high_po": True, "interacts_with": ["Warfarin (مضادات التخثر)"]},
    "Vancomycin": {"priority": 5, "class": "Glycopeptide", "note": "🛑 خاص بـ MRSA.", "renal_limit": 50, "renal_note": "⚖️ مراقبة المستوى في الدم.", "aware": "Watch", "high_po": False, "interacts_with": []},
    "Linezolid": {"priority": 5, "class": "Oxazolidinone", "note": "🛑 للموجبات المقاومة.", "renal_limit": 0, "renal_note": "🟢 لا يحتاج تعديل.", "aware": "Reserve", "high_po": True, "interacts_with": ["SSRI (أدوية الاكتئاب)"]},
    "Clindamycin": {"priority": 3, "class": "Lincosamide", "note": "✅ للالتهابات اللاهوائية والموجبات.", "renal_limit": 0, "renal_note": "🟢 لا يحتاج تعديل.", "aware": "Access", "high_po": True, "interacts_with": []},
    "Doxycycline": {"priority": 3, "class": "Tetracycline", "note": "✅ فعال للمسببات غير النمطية.", "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.", "aware": "Access", "high_po": True, "interacts_with": ["Antacids (مضادات الحموضة)"]},
    "Colistin": {"priority": 5, "class": "Polymyxin", "note": "🛑 الملاذ الأخير.", "renal_limit": 50, "renal_note": "🛑 سمية كلوية عالية.", "aware": "Reserve", "high_po": False, "interacts_with": []}
}

# قوائم التعرف
SPECIMEN_TYPES = ["Urine", "Blood", "Sputum", "Wound Swab", "Pus", "Stool", "CSF", "Ear Swab", "Throat Swab"]
BACTERIA_TYPES = ["E. coli", "Klebsiella spp.", "Pseudomonas aeruginosa", "Staphylococcus aureus", "MRSA", "Proteus mirabilis", "Enterococcus faecalis", "Acinetobacter baumannii", "Streptococcus", "Enterobacter"]
COMMON_MEDS = ["Antacids (مضادات الحموضة)", "Warfarin (مضادات التخثر)", "NSAIDs (مسكنات الألم)", "SSRI (أدوية الاكتئاب)", "Statins (أدوية الكوليسترول)"]

# ألوان تصنيف AWaRe
AWARE_COLORS = {"Access": "🟢 (Access)", "Watch": "🟡 (Watch)", "Reserve": "🔴 (Reserve)"}

def extract_all_data(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    full_text = pytesseract.image_to_string(thresh, config='--psm 6')
    text_lower = full_text.lower()
    
    detected_specimen = "Urine"
    for s in SPECIMEN_TYPES:
        if s.lower() in text_lower:
            detected_specimen = s
            break

    detected_organism = "E. coli"
    for b in BACTERIA_TYPES:
        if b.lower() in text_lower:
            detected_organism = b
            break

    start_pos = text_lower.find("highly")
    if start_pos == -1: start_pos = text_lower.find("sensitive")
    end_pos = text_lower.find("resistant")
    search_area = full_text[start_pos:end_pos] if (start_pos != -1 and end_pos != -1) else full_text

    detected_drugs = []
    for abx_name in ABX_GUIDELINES.keys():
        if re.search(r'\b' + re.escape(abx_name.lower()) + r'\b', search_area.lower()):
            detected_drugs.append(abx_name)
    
    age_match = re.search(r"Age\s*[:/-]?\s*(\d+)", full_text, re.I)
    patient_data = {
        "Age": age_match.group(1) if age_match else "45",
        "Sex": "Female" if "female" in text_lower else "Male",
        "Specimen": detected_specimen,
        "Organism": detected_organism
    }
    return patient_data, list(set(detected_drugs))

def generate_report(patient_info, allowed_drugs, banned_drugs, warnings, organism, specimen, interactions_found):
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = f"==========================================\n"
    report += f"   🛡️ ORANGE LAB - CLINICAL DECISION REPORT\n"
    report += f"==========================================\n"
    report += f"Date: {date_str}\n\n"
    report += f"👤 PATIENT DETAILS:\n"
    report += f"- Age: {patient_info['Age']} | Gender: {patient_info['Sex']} | Weight: {patient_info['Weight']} kg\n"
    if patient_info.get('CrCl'):
         report += f"- Estimated CrCl: {patient_info['CrCl']:.1f} ml/min\n"
    
    report += f"\n🧫 CULTURE DETAILS:\n"
    report += f"- Specimen: {specimen}\n"
    report += f"- Identified Organism: {organism}\n\n"
    
    if interactions_found:
        report += f"⚠️ IDENTIFIED DRUG INTERACTIONS:\n"
        for i in interactions_found: report += f"- {i}\n"
        report += "\n"

    report += f"🟢 RECOMMENDED / SAFE ANTIBIOTICS:\n"
    for item in allowed_drugs:
        report += f"- {item['name']} ({item['aware']}) | Class: {item['class']}\n"
        if item.get('high_po_msg'): report += f"  > 💊 IV to PO: {item['high_po_msg']}\n"
    
    if warnings:
        report += f"\n🟡 REQUIRES DOSE ADJUSTMENT (Renal):\n"
        for item in warnings:
            report += f"- {item['name']}: {item['renal_note']}\n"
            
    if banned_drugs:
        report += f"\n🔴 CONTRAINDICATED:\n"
        for b in banned_drugs: report += f"- {b}\n"
        
    report += f"\n==========================================\n"
    report += f"Developed by: Dr. Hussein Ali | Orange Lab\n"
    report += f"Note: Clinical judgment should always supersede AI suggestions.\n"
    return report

# ==========================================
# 🖥️ Interface
# ==========================================
st.set_page_config(page_title="Orange Culture Analyzer", layout="wide")
st.title("🛡️ Orange Culture Analyzer")

uploaded = st.file_uploader("Upload Culture Report Image", type=['jpg', 'png', 'jpeg'])

if uploaded:
    patient, drugs = extract_all_data(uploaded)
    col1, col2 = st.columns([1, 1.5])
    
    with col1:
        st.subheader("👤 Patient & Report Details")
        
        culture_type = st.selectbox("🧫 Specimen Type", SPECIMEN_TYPES, index=SPECIMEN_TYPES.index(patient['Specimen']) if patient['Specimen'] in SPECIMEN_TYPES else 0)
        organism_type = st.selectbox("🦠 Identified Bacteria", BACTERIA_TYPES, index=BACTERIA_TYPES.index(patient['Organism']) if patient['Organism'] in BACTERIA_TYPES else 0)
        
        st.divider()
        age = st.number_input("Age (Years)", value=int(patient['Age']))
        sex = st.selectbox("Gender", ["Female", "Male"], index=0 if patient['Sex']=="Female" else 1)
        weight = st.number_input("Weight (kg)", min_value=10, value=70 if age >= 18 else 30)
        patient['Weight'] = weight
        is_pediatric = age < 18
        
        st.divider()
        is_renal = st.checkbox("🚩 Evaluate Renal Function (CrCl)")
        cl_cr = 100
        if is_renal:
            s_creat = st.number_input("Serum Creatinine (mg/dL)", min_value=0.1, value=1.0, step=0.1)
            cl_cr = ((140 - age) * weight) / (72 * s_creat)
            if sex == "Female": cl_cr *= 0.85
            st.metric("Creatinine Clearance (CrCl)", f"{cl_cr:.1f} ml/min")
            patient['CrCl'] = cl_cr
        
        is_preg = False
        if sex == "Female" and age >= 12:
            is_preg = st.checkbox("🤰 Is Pregnant?")
            
        st.divider()
        st.write("💊 **Current Medications (التفاعلات الدوائية)**")
        current_meds = st.multiselect("اختر الأدوية التي يتناولها المريض حالياً:", COMMON_MEDS)

    with col2:
        st.subheader("💊 Analysis & Clinical Decision")
        st.caption(f"Analysis for: **{organism_type}** in **{culture_type}**")
        
        manual_add = st.multiselect("➕ Manually add Antibiotics (Search here):", options=sorted(list(ABX_GUIDELINES.keys())))
        total_drugs = list(set(drugs + manual_add))
        
        allowed, banned, warnings, interactions_alerts = [], [], [], []
        
        for d in total_drugs:
            info = ABX_GUIDELINES.get(d, {"priority": 5, "class": "Others", "note": "", "renal_limit": 0, "renal_note": "", "aware": "Access", "high_po": False, "interacts_with": []})
            d_low = d.lower()
            
            # --- 1. Drug Interactions Check ---
            has_interaction = False
            for med in current_meds:
                if med in info['interacts_with']:
                    interactions_alerts.append(f"⚡ تعارض محتمل: **{d}** مع **{med}**")
                    has_interaction = True

            # --- 2. Logic Checks ---
            preg_banned = ["cipro", "levo", "norflox", "tetra", "doxy", "genta", "amikacin", "tobra", "imipenem", "meropenem"]
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
                allowed_item = {"name": d, **info}
                if info['high_po']:
                    allowed_item['high_po_msg'] = "التوافر الحيوي ممتاز فموياً. فكر في التحويل (IV to PO Switch) إذا كانت حالة المريض مستقرة."
                allowed.append(allowed_item)

        # --- Display Results ---
        if interactions_alerts:
            st.warning("⚡ **Drug Interactions (تداخلات دوائية محتملة)**")
            for alert in set(interactions_alerts): st.write(alert)

        if banned:
            st.error("🚫 Contraindicated (موانع استخدام)")
            for b in banned: st.write(b)
            
        if warnings:
            st.warning("⚖️ Requires Dose Adjustment (يتطلب تعديل جرعة بناءً على الكلى)")
            for item in warnings:
                with st.expander(f"⚠️ {item['name']} - {AWARE_COLORS[item['aware']]}"):
                    st.write(f"**السبب:** {item['renal_note']}")

        if allowed:
            st.success("🟢 Generally Safe / Recommended (خيارات آمنة)")
            for item in sorted(allowed, key=lambda x: x['priority']):
                with st.expander(f"💊 {item['name']} | WHO Class: {AWARE_COLORS[item['aware']]}"):
                    st.write(f"**العائلة:** {item['class']}")
                    st.write(f"**ملاحظة السريرية:** {item['note']}")
                    if item.get('high_po_msg'):
                        st.info(f"🔄 **IV to PO:** {item['high_po_msg']}")
        
        # --- PDF/Text Report Export ---
        if total_drugs:
            st.divider()
            report_text = generate_report(patient, allowed, banned, warnings, organism_type, culture_type, interactions_alerts)
            st.download_button(
                label="📄 Download Clinical Report (.txt)",
                data=report_text,
                file_name=f"OrangeLab_Report_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain",
                use_container_width=True
            )

st.divider()
st.markdown("""
<div style="text-align: center; color: gray; font-size: 0.8em;">
    Developed by: Dr Hussein Ali , Orange Lab <br>
    WHO AWaRe Classification: 🟢 Access (First choice) | 🟡 Watch (Use with caution) | 🔴 Reserve (Last resort)
</div>
""", unsafe_allow_html=True)
