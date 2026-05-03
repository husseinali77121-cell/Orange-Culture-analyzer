import streamlit as st
import pandas as pd
import numpy as np
import cv2
import pytesseract
import re

# قائمة المضادات الحيوية (للفلترة ومنع الكلمات العشوائية)
ANTIBIOTIC_WHITELIST = [
    "Amikacin", "Amoxicillin", "Ampicillin", "Augmentin", "Azithromycin",
    "Cefaclor", "Cefadroxil", "Cefazolin", "Cefepime", "Cefixime",
    "Cefoperazone", "Cefotaxime", "Cefoxitin", "Cefpirome", "Cefpodoxime",
    "Ceftazidime", "Ceftriaxone", "Cefuroxime", "Cephalexin", "Cephradine",
    "Ciprofloxacin", "Clarithromycin", "Clindamycin", "Colistin",
    "Doxycycline", "Ertapenem", "Erythromycin", "Fosfomycin", "Fusidic acid",
    "Gentamicin", "Imipenem", "Levofloxacin", "Linezolid", "Meropenem",
    "Minocycline", "Moxifloxacin", "Nalidixic acid", "Nitrofurantoin",
    "Norfloxacin", "Ofloxacin", "Oxacillin", "Penicillin", "Piperacillin",
    "Sulbactam", "Tazobactam", "Tetracycline", "Ticarcillin", "Tobramycin",
    "Trimethoprim", "Sulfamethoxazole", "Vancomycin", "Rifampicin"
]

def is_valid_drug(text):
    text = text.lower()
    return any(abx.lower() in text for abx in ANTIBIOTIC_WHITELIST)

def extract_section_data(img_section, result_type):
    """استخراج الأدوية من جزء معين من الصورة"""
    text = pytesseract.image_to_string(img_section, config='--psm 6')
    found = []
    # تنظيف النص وتقسيمه لأسطر
    for line in text.split('\n'):
        clean_line = re.sub(r'[^a-zA-Z\s\+/]', '', line).strip()
        if len(clean_line) > 3 and is_valid_drug(clean_line):
            found.append({"Antibiotic": clean_name(clean_line), "Result": result_type})
    return found

def clean_name(name):
    """تنظيف اسم الدواء من أي زوائد غير طبية"""
    parts = name.split()
    valid_parts = [p for p in parts if is_valid_drug(p) or p in ["/", "+"]]
    return " ".join(valid_parts).replace(" / ", "/").replace(" + ", "+")

def process_culture_report(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    h, w, _ = img.shape

    # 1. تحديد منطقة الجدول (تقريباً تبدأ بعد ترويسة البيانات)
    # سنقسم الصورة عرضياً إلى 3 مناطق بناءً على عرض الصورة الكلي
    # المنطقة الحساسة (يسار)، المتوسطة (وسط)، المقاومة (يمين)
    
    # تحسين جودة الصورة قبل التقسيم
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

    # تقسيم الصورة لثلاث أعمدة
    col_width = w // 3
    sensitive_zone = processed[:, :col_width + 50]
    intermediate_zone = processed[:, col_width: (col_width * 2) - 20]
    resistant_zone = processed[:, (col_width * 2) - 20:]

    all_results = []
    all_results.extend(extract_section_data(sensitive_zone, "S"))
    all_results.extend(extract_section_data(intermediate_zone, "I"))
    all_results.extend(extract_section_data(resistant_zone, "R"))

    # استخراج البيانات العامة (Name, Age, Organism) من النص الكامل
    full_text = pytesseract.image_to_string(processed)
    
    def get_val(pattern, text):
        match = re.search(pattern, text, re.I)
        return match.group(1).strip() if match else "N/A"

    patient = {
        "Name": get_val(r"Name\s*[:/-]?\s*([^\n|]+)", full_text),
        "Age": get_val(r"Age\s*[:/-]?\s*(\d+)", full_text),
        "Sex": "Female" if "female" in full_text.lower() else "Male",
        "Organism": get_val(r"\((.*?)\)", full_text)
    }

    return patient, pd.DataFrame(all_results).drop_duplicates(subset=['Antibiotic'])

# --- Streamlit UI ---
st.title("🔬 Clinical Culture Expert (Column-Based)")
file = st.file_uploader("Upload Lab Report", type=['jpg', 'png', 'jpeg'])

if file:
    patient, df = process_culture_report(file)
    
    c1, c2 = st.columns([1, 2])
    with c1:
        st.subheader("Patient Info")
        age = st.text_input("Age", value=patient['Age'])
        sex = st.selectbox("Sex", ["Female", "Male"], index=0 if patient['Sex']=="Female" else 1)
        is_preg = st.checkbox("Is Pregnant?") if sex == "Female" else False
        st.write(f"**Organism:** {patient['Organism']}")
    
    with c2:
        st.subheader("Antibiogram Results")
        st.dataframe(df, use_container_width=True)

    st.divider()
    st.subheader("📋 Guidelines-Based Recommendations")
    
    sensitive_drugs = df[df['Result'] == 'S']
    for _, row in sensitive_drugs.iterrows():
        drug = row['Antibiotic']
        advice = []
        
        # منطق التوصيات (Medscape/IDSA)
        if is_preg:
            if any(x in drug.lower() for x in ["tetra", "doxy"]): advice.append("❌ Contraindicated in pregnancy.")
            if any(x in drug.lower() for x in ["cipro", "levo"]): advice.append("⚠️ Avoid if possible (Cartilage risk).")
            if "nitrofurantoin" in drug.lower(): advice.append("✅ Safe (First-line for Cystitis).")
        
        with st.expander(f"💊 {drug}"):
            if advice:
                for a in advice: st.write(a)
            else:
                st.success("Safe to use based on provided data.")
