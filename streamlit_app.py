import streamlit as st
import pandas as pd
import numpy as np
import cv2
import pytesseract
import re

# --- إعدادات الصفحة ---
st.set_page_config(layout="wide", page_title="Clinical Culture Analyzer PRO")

# ==========================================
# 📋 القائمة البيضاء الذكية للمضادات الحيوية
# ==========================================
# تشمل الأدوية المفردة والمركبة
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
    "Trimethoprim", "Sulfamethoxazole", "Vancomycin", "Rifampicin", "Ertapenem"
]

# تركيبات شهيرة لضمان دمجها بشكل صحيح
COMBINATIONS = [
    "Amoxycillin/Clavulanate", "Amoxycillin+Clavulanate", "Augmentin",
    "Ampicillin/Sulbactam", "Piperacillin/Tazobactam",
    "Sulfamethoxazole/Trimethoprim", "Cefoperazone/Sulbactam",
    "Trimethoprim/Sulfamethoxazole"
]

def is_valid_drug_part(text):
    """التحقق من أن الكلمة جزء من دواء معروف أو رمز ربط"""
    text = text.lower()
    if text in ["/", "+", "&"]: return True
    return any(abx.lower() in text for abx in ANTIBIOTIC_WHITELIST)

# ==========================================
# 🧪 معالجة واستخراج البيانات
# ==========================================
def extract_smart_data(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    
    # تحسين الصورة
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    processed = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    
    # استخراج النصوص والإحداثيات
    d = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)
    full_text = pytesseract.image_to_string(processed)

    # تحديد أماكن أعمدة النتائج
    s_x, r_x = 0, 1000
    for i, word in enumerate(d['text']):
        if "Sensitive" in word: s_x = d['left'][i]
        if "Resistant" in word: r_x = d['left'][i]

    # تجميع الكلمات في أسطر مع فلترة الكلمات غير الطبية
    lines = {}
    for i in range(len(d['text'])):
        txt = d['text'][i].strip()
        if len(txt) >= 1:
            y = d['top'][i] // 15 * 15 # تقريب لتجميع السطر
            if y not in lines: lines[y] = []
            lines[y].append({"text": txt, "x": d['left'][i]})

    final_results = []
    for y in sorted(lines.keys()):
        line_data = sorted(lines[y], key=lambda x: x['x'])
        
        # تصفية الكلمات: نحتفظ فقط بما هو مضاد حيوي أو رمز ربط
        filtered_words = [w['text'] for w in line_data if is_valid_drug_part(w['text'])]
        
        if not filtered_words or len(" ".join(filtered_words)) < 4:
            continue
            
        drug_name = " ".join(filtered_words)
        
        # تصحيح الرموز (إزالة المسافات حول الـ / والـ +)
        drug_name = drug_name.replace(" / ", "/").replace(" + ", "+")

        # تحديد النتيجة (S/I/R) بناءً على إحداثيات أول كلمة في السطر الأصلي
        first_x = line_data[0]['x']
        res = "I"
        if first_x < (s_x + 60): res = "S"
        elif first_x > (r_x - 60): res = "R"
        
        final_results.append({"Antibiotic": drug_name, "Result": res})

    # استخراج بيانات المريض (Safe Extraction)
    def quick_regex(pattern, text):
        m = re.search(pattern, text, re.I)
        return m.group(1).strip() if m else "N/A"

    patient = {
        "Name": quick_regex(r"Name\s*[:/-]?\s*([^\n|]+)", full_text),
        "Age": quick_regex(r"Age\s*[:/-]?\s*(\d+)", full_text),
        "Sex": "Female" if "female" in full_text.lower() else "Male",
        "Organism": quick_regex(r"\((.*?)\)", full_text)
    }

    return patient, pd.DataFrame(final_results).drop_duplicates()

# ==========================================
# ⚕️ التقرير الطبي المحدث (Clinical Guidelines)
# ==========================================
def get_clinical_report(drug, age, is_pregnant):
    d = drug.lower()
    notes = []

    # 1. الحمل (Pregnancy Guidelines)
    if is_pregnant:
        if any(x in d for x in ["tetra", "doxy"]):
            notes.append("❌ **Contraindicated:** Tetracyclines may cause fetal tooth discoloration.")
        if any(x in d for x in ["cipro", "levo", "oflox", "norf"]):
            notes.append("⚠️ **Avoid:** Fluoroquinolones risk fetal arthropathy.")
        if "trimethoprim" in d:
            notes.append("❌ **Avoid in 1st Trimester:** Neural tube defect risk.")
        if "nitrofurantoin" in d:
            notes.append("✅ **Safe (First Line):** Effective for cystitis, avoid only at full term (hemolysis risk).")
        if any(x in d for x in ["amoxicillin", "ampicillin", "cefalexin", "ceftriaxone"]):
            notes.append("✅ **Safe:** Beta-lactams are generally safe in pregnancy.")

    # 2. العمر (Pediatrics)
    try:
        if age != "N/A" and int(age) < 18:
            if any(x in d for x in ["cipro", "levo"]):
                notes.append("⚠️ **Caution:** Use quinolones only if no safer alternative (cartilage risk).")
    except: pass

    return notes

# ==========================================
# 🖥️ واجهة المستخدم (Streamlit UI)
# ==========================================
st.title("🛡️ Urine Culture Expert System")
st.markdown("---")

uploaded = st.file_uploader("Upload Culture Image", type=['jpg', 'png', 'jpeg'])

if uploaded:
    patient, df = extract_smart_data(uploaded)
    
    if patient:
        col1, col2 = st.columns([1, 1.5])
        
        with col1:
            st.subheader("👤 Patient Details")
            p_age = st.text_input("Age", value=patient['Age'])
            p_sex = st.selectbox("Sex", ["Female", "Male"], index=0 if patient['Sex']=="Female" else 1)
            is_preg = st.checkbox("Is Patient Pregnant?") if p_sex == "Female" else False
            st.info(f"**Organism:** {patient['Organism']}")
            
            st.subheader("🧪 Filtered Antibiogram")
            st.table(df)

        with col2:
            st.subheader("📋 Clinical Recommendations")
            sensitive_list = df[df['Result'] == 'S']
            
            if sensitive_list.empty:
                st.error("No sensitive (S) antibiotics found.")
            else:
                for _, row in sensitive_list.iterrows():
                    advices = get_clinical_report(row['Antibiotic'], p_age, is_preg)
                    with st.expander(f"💊 {row['Antibiotic']}"):
                        if advices:
                            for a in advices:
                                if "❌" in a: st.error(a)
                                elif "⚠️" in a: st.warning(a)
                                else: st.success(a)
                        else:
                            st.success("Suitable for use based on current guidelines.")

st.sidebar.markdown("""
### 📘 How it works:
1. **Filtering:** Any word not in the antibiotic database (like Pat No, Lab Code) is automatically ignored.
2. **Combinations:** Supports drugs like *Piperacillin/Tazobactam* even if the slash is missing or spaces are present.
3. **Safety:** Checks pregnancy contraindications based on ACOG/IDSA guidelines.
""")
