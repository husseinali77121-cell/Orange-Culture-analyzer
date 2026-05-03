import streamlit as st
import pandas as pd
import numpy as np
import cv2
import pytesseract
import re

# --- إعدادات الصفحة ---
st.set_page_config(layout="wide", page_title="Clinical Culture Analyzer PRO")

# --- دالة معالجة الصورة لزيادة دقة النص ---
def preprocess_image(img):
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # استخدام العتبة المتكيفة لتحسين تباين الكلمات السوداء على خلفية بيضاء
        processed = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        return processed
    except Exception:
        return None

# --- دالة استخراج البيانات بأمان ---
def extract_all_data(uploaded_file):
    try:
        file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, 1)
        processed = preprocess_image(img)
        
        if processed is None:
            return None, None

        # استخراج البيانات الخام وإحداثيات الكلمات
        ocr_data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)
        full_text = pytesseract.image_to_string(processed)

        # 1. استخراج بيانات المريض (Safe Regex)
        def safe_extract(pattern, text, default="Not Found"):
            match = re.search(pattern, text, re.I)
            return match.group(1).strip() if match else default

        patient = {
            "Name": safe_extract(r"(?:Name|الاسم)\s*[:/-]?\s*([^\n|]+)", full_text),
            "Age": safe_extract(r"(?:Age|العمر)\s*[:/-]?\s*(\d+)", full_text),
            "Sex": "Female" if any(x in full_text.lower() for x in ["female", "أنثى", " f "]) else "Male",
            "Organism": safe_extract(r"(?:Culture|Result)\s*[:/-]?\s*(.*?)(?:\n|$)", full_text, "Unknown Organism")
        }
        
        # تحسين استخراج اسم البكتيريا إذا كان بين أقواس كما في صورك
        org_between_brackets = re.search(r"\((.*?)\)", full_text)
        if org_between_brackets:
            patient["Organism"] = org_between_brackets.group(1).strip()

        # 2. استخراج جدول المضادات الحيوية بناءً على الأعمدة
        words = ocr_data['text']
        lefts = ocr_data['left']
        tops = ocr_data['top']
        
        # تحديد موقع أعمدة Sensitive و Resistant ديناميكياً
        s_x, r_x = 0, 1000
        for i, word in enumerate(words):
            if "Sensitive" in word: s_x = lefts[i]
            if "Resistant" in word: r_x = lefts[i]

        antibiogram = []
        lines = {}
        for i in range(len(words)):
            txt = words[i].strip()
            if len(txt) > 1:
                # تجميع الكلمات التي تقع على نفس الارتفاع تقريباً في سطر واحد
                y_key = tops[i] // 14 * 14 
                if y_key not in lines: lines[y_key] = []
                lines[y_key].append({"text": txt, "x": lefts[i]})

        for y in sorted(lines.keys()):
            line_parts = sorted(lines[y], key=lambda x: x['x'])
            line_str = " ".join([w['text'] for w in line_parts])
            
            # تخطي أسطر العناوين
            if any(x in line_str for x in ["Sensitive", "Resistant", "ANTIBIOGRAM", "Name", "Date"]):
                continue
            
            first_x = line_parts[0]['x']
            result = "I" # الافتراضي Intermediate
            if first_x < (s_x + 50): result = "S"
            elif first_x > (r_x - 50): result = "R"
            
            # تنظيف اسم الدواء
            clean_name = re.sub(r'[^a-zA-Z\s\+/]', '', line_str).strip()
            if len(clean_name) > 4:
                antibiogram.append({"Antibiotic": clean_name, "Result": result})

        return patient, pd.DataFrame(antibiogram)
    except Exception as e:
        st.error(f"Error during extraction: {e}")
        return None, None

# --- دالة القواعد الطبية (Clinical Decision Support) ---
def get_clinical_advice(drug, age, sex, is_pregnant):
    d = drug.lower()
    alerts = []
    
    if is_pregnant:
        if any(x in d for x in ["tetra", "doxy"]):
            alerts.append("❌ Contraindicated: Fetal bone/tooth toxicity.")
        if any(x in d for x in ["cipro", "levo", "norf", "oflox"]):
            alerts.append("⚠️ Avoid: Potential fetal cartilage damage.")
        if "nitrofurantoin" in d:
            alerts.append("✅ Safe choice (Avoid only in the last month of pregnancy).")
        if "trimethoprim" in d:
            alerts.append("❌ Avoid in 1st trimester (Folate antagonist).")

    if age != "Not Found":
        try:
            if int(age) < 18:
                if any(x in d for x in ["cipro", "levo"]):
                    alerts.append("⚠️ Caution: Quinolones in pediatrics (Tendon risk).")
        except: pass
        
    return alerts

# --- واجهة المستخدم (Streamlit UI) ---
st.title("🧬 Smart Urine Culture Interpreter")
st.markdown("---")

uploaded = st.file_uploader("Upload Culture Report Image", type=['jpg', 'jpeg', 'png'])

if uploaded:
    with st.spinner('Processing Image...'):
        patient_data, df = extract_all_data(uploaded)
        
    if patient_data:
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("👤 Patient Info")
            # تمكين التعديل اليدوي لضمان الدقة
            u_name = st.text_input("Patient Name", value=patient_data['Name'])
            u_age = st.text_input("Age", value=patient_data['Age'])
            u_sex = st.selectbox("Sex", ["Male", "Female"], index=1 if patient_data['Sex']=="Female" else 0)
            
            is_pregnant = False
            if u_sex == "Female":
                is_pregnant = st.checkbox("Is the patient pregnant? 🤰")
            
            st.info(f"**Detected Organism:** {patient_data['Organism']}")

        with col2:
            st.subheader("🧪 Antibiogram Results")
            if df is not None and not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("No antibiotics detected. Please check image quality.")

        st.markdown("---")
        st.subheader("📋 Clinical Guidance Report")
        
        if df is not None and not df.empty:
            sensitive_drugs = df[df['Result'] == 'S']
            
            if sensitive_drugs.empty:
                st.error("🚨 All antibiotics are Resistant or Intermediate.")
            else:
                for _, row in sensitive_drugs.iterrows():
                    drug = row['Antibiotic']
                    advices = get_clinical_advice(drug, u_age, u_sex, is_pregnant)
                    
                    # عرض النتائج بشكل منظم
                    status_icon = "✅" if not advices else "⚠️"
                    with st.expander(f"{status_icon} {drug}"):
                        if advices:
                            for msg in advices:
                                if "❌" in msg: st.error(msg)
                                else: st.warning(msg)
                        else:
                            st.success(f"{drug} is suitable based on age and gender.")
    
    st.caption("Disclaimer: This tool is for educational purposes only. Clinical decisions must be made by a licensed physician.")
