import streamlit as st
import numpy as np
import cv2
import pytesseract
import re
from datetime import datetime

# ==========================================
# 📋 Comprehensive Antibiotics Database (Egyptian Market Focus)
# ==========================================
ABX_GUIDELINES = {
    # --- Penicillins ---
    "Amoxicillin + Clavulanic acid": {"priority": 1, "class": "Beta-lactamase Inhibitor", "note": "✅ خيار قياسي (مثل Augmentin/Curam).", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Access", "high_po": True, "interacts_with": []},
    "Ampicillin/Sulbactam": {"priority": 2, "class": "Penicillin", "note": "💉 (مثل Unictam/Sigmaclav) فعال للموجبات والسالبات.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": False, "interacts_with": []},
    "Piperacillin + Tazobactam": {"priority": 4, "class": "Anti-pseudomonal", "note": "🛑 (مثل Tazocin) مضاد احتياطي واسع الطيف جداً.", "renal_limit": 20, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": False, "interacts_with": []},

    # --- Cephalosporins ---
    "Cephalexin": {"priority": 1, "class": "1st Gen Cephalosporin", "note": "✅ (مثل Ceporex) آمن للالتهابات البسيطة والجلد.", "renal_limit": 40, "renal_note": "⚖️ مباعدة الجرعات مطلوب.", "aware": "Access", "high_po": True, "interacts_with": []},
    "Cefadroxil": {"priority": 1, "class": "1st Gen Cephalosporin", "note": "✅ (مثل Duricef) فعال لالتهابات الحلق والجلد.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Access", "high_po": True, "interacts_with": []},
    "Cefaclor": {"priority": 2, "class": "2nd Gen Cephalosporin", "note": "✅ (مثل Ceclor) فعال للأذن الوسطى والمسالك.", "renal_limit": 10, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": True, "interacts_with": ["Antacids (مضادات الحموضة)"]},
    "Cefuroxime": {"priority": 2, "class": "2nd Gen Cephalosporin", "note": "✅ (مثل Zinnat) واسع المدى للجهاز التنفسي والمسالك.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": True, "interacts_with": ["Antacids (مضادات الحموضة)"]},
    "Ceftriaxone": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "⚠️ (مثل Rocephin) حقن فقط؛ لا يستخدم في الحالات البسيطة.", "renal_limit": 0, "renal_note": "🟢 آمن كلوياً (إطراح كبدي أساساً).", "aware": "Watch", "high_po": False, "interacts_with": []},
    "Cefixime": {"priority": 2, "class": "3rd Gen Cephalosporin (Oral)", "note": "✅ (مثل Suprax) خيار فموي قوي للمسالك.", "renal_limit": 20, "renal_note": "⚖️ خفض الجرعة مطلوب.", "aware": "Watch", "high_po": True, "interacts_with": []},
    "Cefotaxime": {"priority": 3, "class": "3rd Gen Cephalosporin", "note": "💉 (مثل Cefotax) يستخدم في العدوى الشديدة.", "renal_limit": 20, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": False, "interacts_with": []},
    "Ceftazidime": {"priority": 4, "class": "3rd Gen Cephalosporin", "note": "🛑 (مثل Fortum) متخصص في جراثيم Pseudomonas.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري جداً.", "aware": "Watch", "high_po": False, "interacts_with": []},
    "Cefoperazone": {"priority": 4, "class": "3rd Gen Cephalosporin", "note": "💉 (مثل Cefobid) فعال للمسالك والمرارة.", "renal_limit": 0, "renal_note": "🟢 آمن كلوياً؛ يطرح عبر الصفراء.", "aware": "Watch", "high_po": False, "interacts_with": ["Warfarin (مضادات التخثر)"]},
    "Cefepime": {"priority": 5, "class": "4th Gen Cephalosporin", "note": "🛑 (مثل Maxipime) مضاد قوي جداً للحالات الحرجة.", "renal_limit": 50, "renal_note": "⚠️ يتطلب تعديل جرعة دقيق لتجنب السمية العصبية.", "aware": "Watch", "high_po": False, "interacts_with": []},

    # --- Fluoroquinolones ---
    "Ciprofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ (مثل Ciprofar) يفضل ادخاره للمسالك المعقدة.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": True, "interacts_with": ["Antacids (مضادات الحموضة)", "Warfarin (مضادات التخثر)"]},
    "Levofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ (مثل Tavanic) فعال جداً للصدر والمسالك.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": True, "interacts_with": ["Antacids (مضادات الحموضة)"]},
    "Ofloxacin": {"priority": 2, "class": "Fluoroquinolone", "note": "⚠️ (مثل Tarivid) واسع المدى.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": True, "interacts_with": ["Antacids (مضادات الحموضة)"]},

    # --- Urinary Antiseptics ---
    "Nitrofurantoin": {"priority": 1, "class": "Urinary Antiseptic", "note": "🎯 (مثل Macrofuran) الخيار الأول للمسالك البسيطة.", "renal_limit": 30, "renal_note": "🚫 ممنوع إذا كانت التصفية < 30 مل/د.", "aware": "Access", "high_po": True, "interacts_with": ["Antacids (مضادات الحموضة)"]},
    "Fosfomycin": {"priority": 1, "class": "Phosphonic Acid", "note": "🎯 (مثل Monuril) خيار مثالي بجرعة واحدة.", "renal_limit": 10, "renal_note": "⚠️ حذر في القصور الشديد.", "aware": "Access", "high_po": True, "interacts_with": []},

    # --- Aminoglycosides ---
    "Gentamicin": {"priority": 4, "class": "Aminoglycoside", "note": "💉 (مثل Garamycin) يستخدم بحذر شديد.", "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى ضرورية.", "aware": "Access", "high_po": False, "interacts_with": ["NSAIDs (مسكنات الألم)"]},
    "Amikacin": {"priority": 4, "class": "Aminoglycoside", "note": "💉 (مثل Amikin) فعال جداً ضد السالبات المقاومة.", "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى.", "aware": "Watch", "high_po": False, "interacts_with": ["NSAIDs (مسكنات الألم)"]},

    # --- Others ---
    "Azithromycin": {"priority": 2, "class": "Macrolide", "note": "✅ (مثل Zithrokan) فعال للجهاز التنفسي.", "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.", "aware": "Watch", "high_po": True, "interacts_with": ["Antacids (مضادات الحموضة)"]},
    "Clarithromycin": {"priority": 2, "class": "Macrolide", "note": "✅ (مثل Klacid) فعال لجرثومة المعدة والصدر.", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": True, "interacts_with": []},
    "Trimethoprim/Sulfamethoxazole": {"priority": 2, "class": "Sulfa", "note": "✅ (مثل Septra/Sutrim).", "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Access", "high_po": True, "interacts_with": ["Warfarin (مضادات التخثر)"]},
    "Vancomycin": {"priority": 5, "class": "Glycopeptide", "note": "🛑 خاص بـ MRSA والحالات الحرجة.", "renal_limit": 50, "renal_note": "⚖️ مراقبة مستوى الدواء في الدم.", "aware": "Watch", "high_po": False, "interacts_with": ["NSAIDs (مسكنات الألم)"]},
    "Meropenem": {"priority": 5, "class": "Carbapenem", "note": "🛑 (مثل Meronem) مضاد الملاذ الأخير.", "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.", "aware": "Watch", "high_po": False, "interacts_with": []},
    "Linezolid": {"priority": 5, "class": "Oxazolidinone", "note": "🛑 (مثل Averozolid) للموجبات المقاومة (MRSA/VRE).", "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.", "aware": "Reserve", "high_po": True, "interacts_with": ["SSRI (أدوية الاكتئاب)"]},
}

SPECIMEN_TYPES = ["Urine", "Blood", "Sputum", "Wound Swab", "Pus", "Stool", "CSF"]
BACTERIA_TYPES = ["E. coli", "Klebsiella spp.", "Pseudomonas aeruginosa", "Staphylococcus aureus", "MRSA", "Proteus mirabilis", "Enterococcus faecalis"]
COMMON_MEDS = ["Antacids (مضادات الحموضة)", "Warfarin (مضادات التخثر)", "NSAIDs (مسكنات الألم)", "SSRI (أدوية الاكتئاب)"]
AWARE_COLORS = {"Access": "🟢 (Access)", "Watch": "🟡 (Watch)", "Reserve": "🔴 (Reserve)"}

# ==========================================
# 🔍 OCR Function
# ==========================================
def extract_all_data(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    full_text = pytesseract.image_to_string(thresh, config='--psm 6')
    text_lower = full_text.lower()

    age_match = re.search(r"(\d+)\s*Years", full_text, re.I)
    detected_age = age_match.group(1) if age_match else "25"

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

    return {"Age": detected_age, "Sex": "Female" if "female" in text_lower else "Male", 
            "Specimen": detected_specimen, "Organism": detected_organism}, list(set(detected_drugs))

# ==========================================
# 📄 Report Generator
# ==========================================
def generate_report(age, sex, weight, cl_cr, is_renal, is_preg, allowed_drugs, banned_drugs, warnings, organism, specimen, interactions):
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    report = f"==========================================\n"
    report += f" 🛡️ ORANGE LAB - CLINICAL DECISION REPORT\n"
    report += f"==========================================\n"
    report += f"Date: {date_str}\n\n"
    report += f"👤 PATIENT DETAILS:\n"
    report += f"- Age: {age} Years | Gender: {sex} | Weight: {weight} kg\n"
    report += f"- Renal Function: {'🚩 ACTIVE' if is_renal else '🟢 NORMAL'}\n"
    if is_renal: report += f" > Calculated CrCl: {cl_cr:.1f} ml/min\n"
    if sex == "Female": report += f"- Pregnancy: {'🤰 PREGNANT' if is_preg else '🟢 NOT PREGNANT'}\n"
    
    report += f"\n🧫 CULTURE DETAILS:\n"
    report += f"- Specimen: {specimen} | Organism: {organism}\n\n"

    if interactions:
        report += f"⚠️ INTERACTIONS:\n"
        for i in interactions: report += f"- {i}\n"
        report += "\n"

    report += f"🟢 RECOMMENDED ANTIBIOTICS:\n"
    for item in allowed_drugs: report += f"- {item['name']} ({item['aware']})\n"

    if warnings:
        report += f"\n🟡 RENAL DOSAGE ADJUSTMENTS:\n"
        for item in warnings: report += f"- {item['name']}: {item['renal_note']}\n"

    if banned_drugs:
        report += f"\n🔴 CONTRAINDICATED:\n"
        for b in banned_drugs: report += f"- {b}\n"

    report += f"\n==========================================\n"
    report += f"Developed by: Dr. Hussein Ali | Orange Lab\n"
    return report

# ==========================================
# 🖥️ Interface
# ==========================================
st.set_page_config(page_title="Orange Culture Analyzer", layout="wide")
st.title("🛡️ Orange Culture Analyzer")

uploaded = st.file_uploader("Upload Culture Report Image", type=['jpg', 'png', 'jpeg'])

if uploaded:
    if 'ocr_data' not in st.session_state:
        patient_init, drugs_init = extract_all_data(uploaded)
        st.session_state.ocr_data = (patient_init, drugs_init)

    patient, drugs_from_ocr = st.session_state.ocr_data
    col1, col2 = st.columns([1, 1.5])

    with col1:
        st.subheader("👤 Patient Details")
        culture_type = st.selectbox("🧫 Specimen Type", SPECIMEN_TYPES, index=SPECIMEN_TYPES.index(patient['Specimen']) if patient['Specimen'] in SPECIMEN_TYPES else 0)
        organism_type = st.selectbox("🦠 Bacteria", BACTERIA_TYPES, index=BACTERIA_TYPES.index(patient['Organism']) if patient['Organism'] in BACTERIA_TYPES else 0)
        st.divider()
        age = st.number_input("Age (Years)", value=int(patient['Age']), min_value=0)
        sex = st.selectbox("Gender", ["Female", "Male"], index=0 if patient['Sex']=="Female" else 1)
        weight = st.number_input("Weight (kg)", min_value=5, value=70)
        
        is_renal = st.checkbox("🚩 Evaluate Renal Function")
        cl_cr = 100
        if is_renal:
            s_creat = st.number_input("Serum Creatinine (mg/dL)", min_value=0.1, value=1.0, step=0.1)
            cl_cr = ((140 - age) * weight) / (72 * s_creat)
            if sex == "Female": cl_cr *= 0.85
            st.metric("Estimated CrCl", f"{cl_cr:.1f} ml/min")

        is_preg = st.checkbox("🤰 Is Patient Pregnant?") if sex == "Female" and age >= 12 else False
        current_meds = st.multiselect("💊 Current Medications:", COMMON_MEDS)

    with col2:
        st.subheader("💊 Antibiotics Analysis")
        final_drugs = st.multiselect("Verify Antibiotics:", options=sorted(list(ABX_GUIDELINES.keys())), 
                                    default=[d for d in drugs_from_ocr if d in ABX_GUIDELINES])

        allowed, banned, warnings, interactions_alerts = [], [], [], []

        for d in final_drugs:
            info = ABX_GUIDELINES[d]
            d_low = d.lower()
            for med in current_meds:
                if med in info['interacts_with']: interactions_alerts.append(f"⚡ تعارض: {d} مع {med}")

            # Pregnancy/Age/Renal Logic
            preg_banned = ["cipro", "levo", "oflox", "norflox", "genta", "vancomycin", "amikacin", "clarithro"]
            if is_preg and any(x in d_low for x in preg_banned):
                banned.append(f"💊 {d}: غير آمن للحمل.")
            elif age < 18 and any(x in d_low for x in ["cipro", "levo", "oflox"]):
                banned.append(f"💊 {d}: يفضل تجنبه للأطفال.")
            elif is_renal and "nitrofurantoin" in d_low and cl_cr < 30:
                banned.append(f"💊 {d}: ممنوع في قصور الكلى الشديد.")
            elif is_renal and info['renal_limit'] > 0 and cl_cr <= info['renal_limit']:
                warnings.append({"name": d, **info})
            else:
                allowed.append({"name": d, **info})

        if interactions_alerts:
            st.warning("Interactions Detected")
            for a in set(interactions_alerts): st.write(a)
        if banned:
            st.error("🚫 Contraindicated")
            for b in banned: st.write(b)
        if allowed:
            st.success("🟢 Recommended Options (Safe)")
            for item in sorted(allowed, key=lambda x: x['priority']):
                with st.expander(f"{item['name']} {AWARE_COLORS[item['aware']]}"):
                    st.write(f"**Class:** {item['class']}")
                    st.write(f"**Note:** {item['note']}")

        if final_drugs:
            st.divider()
            full_report = generate_report(age, sex, weight, cl_cr, is_renal, is_preg, allowed, banned, warnings, organism_type, culture_type, interactions_alerts)
            st.download_button("📄 Download Final Report", full_report, f"Orange_Report_{datetime.now().strftime('%H%M%S')}.txt", use_container_width=True)

st.divider()

# --- الجزء الذي تم تعديله ليتطابق مع الصورة تماماً ---
st.markdown("""
<div style="text-align: center;">
    <strong>Developed by: Dr Hussein Ali, Orange Lab</strong><br><br>
    WHO AWaRe Classification: 🟢<br>
    Access (First choice) | 🟡 Watch<br>
    (Use with caution) | 🔴 Reserve<br>
    (Last resort)
</div>
""", unsafe_allow_html=True)
