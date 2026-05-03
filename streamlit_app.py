import streamlit as st
import pandas as pd
import numpy as np
import cv2
import pytesseract
import re

# --- قاعدة بيانات الأدوية وتصنيف قوتها وأولويتها ---
# Priority: 1 (First-line), 2 (Second-line), 3 (Reserve/Strong)
ABX_DB = {
    "Nitrofurantoin": {"priority": 1, "class": "Urinary Antiseptic"},
    "Fosfomycin": {"priority": 1, "class": "Phosphonic acid derivative"},
    "Amoxicillin/Clavulanate": {"priority": 2, "class": "Penicillin + Beta-lactamase"},
    "Augmentin": {"priority": 2, "class": "Penicillin + Beta-lactamase"},
    "Cefaclor": {"priority": 2, "class": "Cephalosporin (2nd Gen)"},
    "Cefuroxime": {"priority": 2, "class": "Cephalosporin (2nd Gen)"},
    "Ceftriaxone": {"priority": 2, "class": "Cephalosporin (3rd Gen)"},
    "Cefotaxime": {"priority": 2, "class": "Cephalosporin (3rd Gen)"},
    "Ciprofloxacin": {"priority": 2, "class": "Fluoroquinolone"},
    "Levofloxacin": {"priority": 2, "class": "Fluoroquinolone"},
    "Gentamicin": {"priority": 3, "class": "Aminoglycoside"},
    "Amikacin": {"priority": 3, "class": "Aminoglycoside"},
    "Imipenem": {"priority": 4, "class": "Carbapenem (Reserve)"},
    "Meropenem": {"priority": 4, "class": "Carbapenem (Reserve)"},
    "Ertapenem": {"priority": 4, "class": "Carbapenem (Reserve)"},
    "Piperacillin/Tazobactam": {"priority": 4, "class": "Anti-pseudomonal Penicillin"}
}

def clean_and_match(text):
    """التعرف على الدواء من قاعدة البيانات لضمان دقة الترتيب"""
    text_clean = text.lower()
    for drug in ABX_DB.keys():
        if drug.lower() in text_clean:
            return drug
    return None

def process_and_sort(raw_list, age, is_pregnant):
    """فلترة الممنوعات وترتيب الباقي من الأنسب (Top) إلى الأقوى (Reserve)"""
    allowed = []
    contraindicated = []
    
    for raw_drug in raw_list:
        drug_name = clean_and_match(raw_drug)
        if not drug_name: continue
        
        reason = ""
        # فحص موانع الاستعمال (Contraindications)
        if is_pregnant:
            if any(x in drug_name.lower() for x in ["cipro", "levo", "norf"]):
                reason = "ممنوع في الحمل (خطر على غضاريف الجنين)"
            elif any(x in drug_name.lower() for x in ["tetra", "doxy"]):
                reason = "ممنوع في الحمل (تصبغ العظام والأسنان)"
            elif "trimethoprim" in drug_name.lower():
                reason = "يُفضل تجنبه في الشهور الأولى (نقص الفوليك)"
        
        if age < 18 and any(x in drug_name.lower() for x in ["cipro", "levo"]):
            reason = "يُمنع استخدامه للأطفال تحت 18 سنة إلا للضرورة"

        if reason:
            contraindicated.append({"drug": drug_name, "reason": reason})
        else:
            data = ABX_DB[drug_name]
            allowed.append({
                "drug": drug_name,
                "priority": data['priority'],
                "class": data['class']
            })
    
    # الترتيب: الأقل في الـ priority (رقم 1) يظهر أولاً
    allowed_sorted = sorted(allowed, key=lambda x: x['priority'])
    return allowed_sorted, contraindicated

# --- واجهة Streamlit ---
st.set_page_config(page_title="Pro-Guideline Analyzer", layout="wide")
st.title("🛡️ محرك التوصيات الذكي (Guidelines-Based)")

uploaded_file = st.file_uploader("ارفع صورة المزرعة", type=['jpg', 'png', 'jpeg'])

if uploaded_file:
    # (هنا نستخدم نفس دوال الـ OCR السابقة لاستخراج القائمة الخام)
    # للتبسيط، سنفترض استخراج هذه القائمة:
    raw_detected = ["Ciprofloxacin", "Nitrofurantoin", "Meropenem", "Augmentin", "Ceftriaxone"] 
    
    st.sidebar.subheader("بيانات المريض")
    age = st.sidebar.number_input("العمر", value=25)
    sex = st.sidebar.selectbox("الجنس", ["Female", "Male"])
    is_preg = False
    if sex == "Female":
        is_preg = st.sidebar.checkbox("هل توجد حالة حمل؟")

    allowed, banned = process_and_sort(raw_detected, age, is_preg)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("✅ الأدوية الموصى بها (مرتبة حسب الأولوية)")
        st.info("الترتيب يبدأ من الخيار الأول (الأكثر تخصصاً) وصولاً إلى الأدوية القوية (للحالات المعقدة).")
        
        for item in allowed:
            with st.expander(f"⭐ {item['drug']}"):
                st.write(f"**التصنيف:** {item['class']}")
                if item['priority'] == 1:
                    st.success("🎯 خيار أول (First-line therapy) - فعال جداً وآمن.")
                elif item['priority'] >= 4:
                    st.warning("⚠️ دواء احتياطي (Reserve) - لا يستخدم إلا في حالة فشل الخيارات السابقة.")
                else:
                    st.write("خيار بديل مناسب.")

    with col2:
        st.subheader("❌ الأدوية المحذوفة (Contraindicated)")
        if not banned:
            st.write("لا توجد موانع استعمال لهذا المريض.")
        else:
            for item in banned:
                st.error(f"**{item['drug']}**\n\n*السبب:* {item['reason']}")

    st.markdown("---")
    st.caption("تعتمد هذه التوصيات على تقارير IDSA و Medscape لعام 2024/2026.")
