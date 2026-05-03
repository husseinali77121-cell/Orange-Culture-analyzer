import streamlit as st
import pandas as pd
import numpy as np
import cv2
import pytesseract
import re

# إعداد الصفحة وتنسيقها
st.set_page_config(layout="wide", page_title="Clinical Analyzer PRO")

def preprocess_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # تقنية لتحسين النصوص الباهتة في التقارير
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    return gray

def extract_all_data(uploaded_file):
    # تحويل الصورة
    img = cv2.imdecode(np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8), 1)
    processed = preprocess_image(img)
    
    # استخراج البيانات مع الإحداثيات (بمنتهى الدقة)
    ocr_data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)
    full_text = pytesseract.image_to_string(processed)

    # 1. استخراج بيانات المريض
    patient = {
        "Name": re.search(r"Name\s*:\s*([^\n|]+)", full_text, re.I).group(1).strip() if re.search(r"Name", full_text) else "N/A",
        "Age": re.search(r"Age\s*:\s*(\d+)", full_text, re.I).group(1) if re.search(r"Age", full_text) else "N/A",
        "Sex": "Female" if "female" in full_text.lower() else "Male",
        "Organism": re.search(r"\((.*?)\)", full_text).group(1).strip() if re.search(r"Culture", full_text) else "Unknown"
    }

    # 2. استخراج جدول المضادات الحيوية (خوارزمية الإحداثيات السطرية)
    # نحدد أماكن الكلمات المفتاحية (S, I, R) في الصورة
    words = ocr_data['text']
    lefts = ocr_data['left']
    tops = ocr_data['top']
    
    sensitive_x = 0
    resistant_x = 1000
    
    for i, word in enumerate(words):
        if "Sensitive" in word: sensitive_x = lefts[i]
        if "Resistant" in word: resistant_x = lefts[i]

    antibiogram = []
    
    # تجميع النص بناءً على الارتفاع (Y-axis) لضمان عدم اختلاط السطور
    lines = {}
    for i in range(len(words)):
        if words[i].strip():
            y = tops[i] // 10 * 10 # تقريب الإحداثي لجمع الكلمات على نفس السطر
            if y not in lines: lines[y] = []
            lines[y].append({"text": words[i], "x": lefts[i]})

    for y in sorted(lines.keys()):
        line_text = " ".join([w['text'] for w in sorted(lines[y], key=lambda x: x['x'])])
        
        # استبعاد سطور الترويسة
        if any(x in line_text for x in ["ANTIBIOGRAM", "Sensitive", "Culture", "Name"]): continue
        
        # تحديد النتيجة بناءً على مكان أول كلمة في السطر بالنسبة للأعمدة
        first_word_x = lines[y][0]['x']
        
        result = "I" # الافتراضي
        if first_word_x < (sensitive_x + 50): result = "S"
        elif first_word_x > (resistant_x - 50): result = "R"
        
        # تنظيف اسم المضاد من أي شوائب
        drug_name = re.sub(r'[^a-zA-Z\s\+]', '', line_text).strip()
        if len(drug_name) > 3:
            antibiogram.append({"Antibiotic": drug_name, "Result": result})

    return patient, pd.DataFrame(antibiogram)

def clinical_guidelines(drug, age, is_pregnant):
    d = drug.lower()
    notes = []
    
    # قوانين صارمة بناءً على Guidelines
    if is_pregnant:
        if any(x in d for x in ["tetracycline", "doxycyclin"]):
            notes.append("❌ ممنوع تماماً في الحمل (يؤثر على عظام وأسنان الجنين)")
        if any(x in d for x in ["ciprofloxacin", "norfloxacin", "levofloxacin", "ofloxacin"]):
            notes.append("⚠️ يفضل تجنبه في الحمل (خطر على المفاصل)")
        if "nitrofurantoin" in d:
            notes.append("✅ خيار أول آمن (ما عدا في الشهر التاسع)")
        if "trimethoprim" in d:
            notes.append("❌ ممنوع في الشهور الثلاثة الأولى")

    if age and int(age) < 18:
        if any(x in d for x in ["cipro", "levo", "oflox"]):
            notes.append("⚠️ يراعى الحذر تحت سن 18 (تأثير على الغضاريف)")

    return notes

# واجهة البرنامج
st.title("🛡️ نظام تحليل المزارع الذكي")
uploaded = st.file_uploader("ارفع صورة المزرعة هنا", type=['jpg', 'png', 'jpeg'])

if uploaded:
    patient, df = extract_all_data(uploaded)
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📋 بيانات المريض المستخرجة")
        st.write(f"**الاسم:** {patient['Name']}")
        st.write(f"**العمر:** {patient['Age']}")
        st.write(f"**الجنس:** {patient['Sex']}")
        st.info(f"**الميكروب:** {patient['Organism']}")
        
        is_pregnant = False
        if patient['Sex'] == "Female":
            is_pregnant = st.checkbox("هل المريضة حامل؟")

    with col2:
        st.subheader("🧬 نتائج الحساسية")
        st.dataframe(df)

    st.divider()
    st.subheader("📝 التقرير الطبي المقترح")
    
    for index, row in df.iterrows():
        if row['Result'] == 'S':
            alerts = clinical_guidelines(row['Antibiotic'], patient['Age'], is_pregnant)
            color = "green" if not alerts else "orange"
            icon = "✅" if not alerts else "⚠️"
            
            with st.expander(f"{icon} {row['Antibiotic']}"):
                if alerts:
                    for a in alerts: st.error(a)
                else:
                    st.success("مناسب للحالة من حيث العمر والجنس.")

