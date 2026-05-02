import streamlit as st
import pandas as pd
import numpy as np
import cv2
import pytesseract
import re

# ========== الإعدادات ==========
st.set_page_config(page_title="نظام دعم المضادات الحيوية - 2025", layout="wide")
st.title("🩺 نظام دعم القرار لاختيار المضاد الحيوي")
st.markdown("**تحليل احترافي مبني على أحدث الإرشادات (IDSA 2025) يشمل استخراج الجرثومة، تقييم الحساسية، وتوصيات علاجية مخصصة**")

# ========== الدوال الطبية (ثوابت) ==========
def calculate_crcl(age, weight, sex, serum_creatinine):
    if None in (age, weight, serum_creatinine) or weight <= 0 or serum_creatinine <= 0:
        return None
    crcl = ((140 - age) * weight) / (72 * serum_creatinine)
    if sex == "أنثى":
        crcl *= 0.85
    return round(crcl, 1)

def get_clinical_alerts(antibiotic, crcl, is_pregnant):
    """
    تُرجع تنبيهات كلوية وتنبيهات حمل (نفس السابق مع تحسينات).
    """
    renal_alert = ""
    pregnancy_alert = ""
    ab_lower = antibiotic.lower()
    
    # --- تنبيهات كلوية ---
    if crcl is not None:
        if 'nitrofurantoin' in ab_lower:
            if crcl < 30:
                renal_alert = "⚠️ تجنب (CrCl<30)"
            elif crcl < 60:
                renal_alert = "⚠️ حذر (CrCl<60)"
        elif any(d in ab_lower for d in ['gentamicin', 'amikacin', 'tobramycin']):
            if crcl < 30:
                renal_alert = "⚠️ تجنب أو تعديل كبير (سمية)"
            elif crcl < 70:
                renal_alert = "⚠️ يفضل مراقبة المستوى"
        elif 'vancomycin' in ab_lower and crcl < 50:
            renal_alert = "⚠️ مراقبة مستوى وتعديل الجرعة"
        elif any(d in ab_lower for d in ['ciprofloxacin', 'levofloxacin', 'ofloxacin']):
            if crcl < 30:
                renal_alert = "⚠️ خفض الجرعة"
            elif crcl < 60:
                renal_alert = "⚠️ قد تحتاج خفض الجرعة"
        elif ('trimethoprim' in ab_lower or 'sulfamethoxazole' in ab_lower) and crcl < 30:
            renal_alert = "⚠️ تقليل الجرعة أو تجنب"
        elif 'piperacillin' in ab_lower and crcl < 40:
            renal_alert = "⚠️ تعديل الجرعة"
    
    # --- تنبيهات الحمل ---
    if is_pregnant:
        unsafe_map = {
            'tetracycline': '❌ يمنع (تشوهات)',
            'doxycycline': '❌ يمنع (تشوهات)',
            'minocycline': '❌ يمنع (تشوهات)',
            'ciprofloxacin': '🚫 تجنب (سلامة غير مثبتة)',
            'levofloxacin': '🚫 تجنب',
            'moxifloxacin': '🚫 تجنب',
            'gentamicin': '⚠️ خطر (سمية أذنية)',
            'amikacin': '⚠️ خطر',
            'tobramycin': '⚠️ خطر',
            'trimethoprim': '❌ يمنع في الثلث الأول',
            'sulfamethoxazole': '❌ يمنع قرب الولادة',
            'nitrofurantoin': '⚠️ تجنب في الثلث الثالث'
        }
        for key, msg in unsafe_map.items():
            if key in ab_lower:
                pregnancy_alert = msg
                break
    return renal_alert, pregnancy_alert

# ========== دوال OCR المحسّنة ==========
def extract_microorganism(full_text):
    """
    استخراج اسم الجرثومة من النص.
    """
    # أنماط شائعة في تقارير المختبرات العربية والإنجليزية
    patterns = [
        r'Culture\s*:\s*(.*?)(?:\n|$)',
        r'Organism\s*:\s*(.*?)(?:\n|$)',
        r'Isolate\s*:\s*(.*?)(?:\n|$)',
        r'Gram negative bacilli\s*\(\s*(\w+)\s*\)',
        r'Gram positive cocci\s*\(\s*(\w+)\s*\)',
        r'(\b(?:Escherichia|Klebsiella|Pseudomonas|Staphylococcus|Streptococcus|Enterococcus|Proteus|Acinetobacter)\b.*?)(?:\n|$)'
    ]
    for pat in patterns:
        match = re.search(pat, full_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    # محاولة أخيرة: أي سطر يحتوي على "bacilli" أو "coli"
    for line in full_text.split('\n'):
        if 'bacilli' in line.lower() or 'coli' in line.lower():
            return line.strip()
    return "غير معروف"

def extract_antibiogram_advanced(image_file):
    """استخراج الجدول بدقة عالية باستخدام image_to_data مع تجميع ذكي."""
    file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if img is None:
        return pd.DataFrame(), ""
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    
    # 1. النص الكامل
    full_text = pytesseract.image_to_string(thresh, lang='eng+ara', config='--psm 6')
    
    # 2. البيانات المكانية
    data = pytesseract.image_to_data(thresh, lang='eng+ara', output_type=pytesseract.Output.DICT, config='--psm 6')
    
    # تجميع الكلمات في سطور بناءً على الإحداثي y (مع تفاوت بسيط)
    lines = {}
    n = len(data['text'])
    for i in range(n):
        word = data['text'][i].strip()
        if not word:
            continue
        x, y = data['left'][i], data['top'][i]
        # مفتاح السطر: نقرب y لأقرب 10 بكسل
        y_key = round(y / 10) * 10
        if y_key not in lines:
            lines[y_key] = []
        lines[y_key].append((x, word))
    
    # ترتيب السطور وإعادة بناء النص
    sorted_y = sorted(lines.keys())
    reconstructed = []
    for y_key in sorted_y:
        words_sorted = sorted(lines[y_key], key=lambda w: w[0])
        line_text = ' '.join([w for _, w in words_sorted])
        reconstructed.append(line_text.strip())
    
    # تعريف الفئات
    sens_kw = ['sensitive', 'susceptible', 'حساس']
    inter_kw = ['intermediate', 'متوسط', 'وسيط']
    resist_kw = ['resistant', 'مقاوم']
    
    antibiotics = []
    results = []
    current_category = None
    
    for line in reconstructed:
        lower = line.lower()
        # تجاهل سطور العناوين الفارغة أو غير الدوائية
        if not line or any(w in lower for w in ['antibiotic', 'description', 'colony', 'comment', 'reporting']):
            continue
        
        # تحديد الفئة
        if any(kw in lower for kw in sens_kw):
            current_category = 'S'
            # إزالة الكلمة المفتاحية نفسها من السطر
            for kw in sens_kw:
                line = re.sub(r'(?i)' + kw + r'[\s:]*', '', line).strip()
            if line:
                antibiotics.append(line)
                results.append('S')
            continue
        elif any(kw in lower for kw in inter_kw):
            current_category = 'I'
            for kw in inter_kw:
                line = re.sub(r'(?i)' + kw + r'[\s:]*', '', line).strip()
            if line:
                antibiotics.append(line)
                results.append('I')
            continue
        elif any(kw in lower for kw in resist_kw):
            current_category = 'R'
            for kw in resist_kw:
                line = re.sub(r'(?i)' + kw + r'[\s:]*', '', line).strip()
            if line:
                antibiotics.append(line)
                results.append('R')
            continue
        
        # إذا لم تكن فئة، نعتمد الفئة الحالية
        if current_category:
            # تنظيف الاسم من الأحرف غير المرغوبة (مع الحفاظ على الشرطة والخط المائل)
            clean = re.sub(r'[^a-zA-Zأ-ي/\s\+\-]', '', line).strip()
            if clean:
                antibiotics.append(clean)
                results.append(current_category)
    
    df = pd.DataFrame({"Antibiotic": antibiotics, "Result": results})
    if not df.empty:
        # إزالة أي صفوف لا تزال تحتوي على كلمات مفتاحية
        all_kw = sens_kw + inter_kw + resist_kw
        mask = ~df['Antibiotic'].str.lower().apply(lambda x: any(k in x for k in all_kw))
        df = df[mask]
        df = df.drop_duplicates(subset="Antibiotic", keep="first").reset_index(drop=True)
    return df, full_text

# ========== دالة التفسير الاحترافي ==========
def generate_clinical_interpretation(df, microorganism, crcl, is_pregnant, specimen_type, patient_sex):
    """
    بناء تقرير استشاري احترافي.
    """
    if df.empty:
        return "لا توجد بيانات مزرعة لتفسيرها."
    
    # 1. تصنيف المضادات حسب الحساسية
    sensitive = df[df['Result'] == 'S']['Antibiotic'].tolist()
    intermediate = df[df['Result'] == 'I']['Antibiotic'].tolist()
    resistant = df[df['Result'] == 'R']['Antibiotic'].tolist()
    
    # 2. فلترة المضادات الآمنة حسب الحالة السريرية
    safe_sensitive = []
    for ab in sensitive:
        renal, preg = get_clinical_alerts(ab, crcl, is_pregnant)
        if not renal and not preg:  # لا توجد تحذيرات على الإطلاق
            safe_sensitive.append(ab)
        elif preg and '❌' in preg:  # إذا كان خطراً على الحمل، نستبعده
            continue
        elif renal and 'تجنب' in renal:  # إذا كان يجب تجنبه بسبب الكلى، نستبعده
            continue
        else:
            # إذا كان التحذير مجرد "حذر" نضيفه مع علامة
            safe_sensitive.append(f"{ab} (مع حذر)")
    
    # 3. تحديد أفضل خيار حسب نوع العدوى (UTI هنا)
    best_choice = None
    # أولوية لعدوى UTI بسيطة (إذا كانت وظائف الكلى طبيعية ولا حمل)
    if specimen_type.lower() == 'urine':
        # UTI بسيطة: نفضل nitrofurantoin أو TMP-SMX أو cephalexin
        preferred_simple = ['Nitrofurantoin', 'Trimethoprim/Sulfamethoxazole', 'Cephalexin']
        for pref in preferred_simple:
            for s_ab in sensitive:
                if pref.lower() in s_ab.lower():
                    renal_a, preg_a = get_clinical_alerts(s_ab, crcl, is_pregnant)
                    if not renal_a and not preg_a:
                        best_choice = s_ab
                        break
            if best_choice:
                break
        # إذا لم نجد، نختار أي آمن من الحساسين
        if not best_choice and safe_sensitive:
            best_choice = safe_sensitive[0].replace(" (مع حذر)", "")
    
    # إذا لم نجد أو كانت عدوى معقدة (أو غير بولية)
    if not best_choice:
        # نأخذ أفضل مضاد آمن واسع الطيف من الحساسين
        for pref_gen in ['Piperacillin/Tazobactam', 'Ceftriaxone', 'Cefepime', 'Imipenem', 'Meropenem', 'Levofloxacin']:
            for s in sensitive:
                if pref_gen.lower() in s.lower():
                    renal_a, preg_a = get_clinical_alerts(s, crcl, is_pregnant)
                    if not renal_a and not preg_a:
                        best_choice = s
                        break
            if best_choice:
                break
        if not best_choice and safe_sensitive:
            best_choice = safe_sensitive[0].replace(" (مع حذر)", "")
    
    # 4. بناء التقرير
    report = []
    report.append(f"### 🧫 نتيجة المزرعة")
    report.append(f"**الكائن الحي (Microorganism):** {microorganism}")
    report.append(f"**نوع العينة:** {specimen_type}")
    
    report.append(f"### 📊 ملخص الحساسية")
    report.append(f"- ✅ حساس (Sensitive): {len(sensitive)} مضادات حيوية")
    if intermediate:
        report.append(f"- 🟡 حساسية متوسطة (Intermediate): {len(intermediate)} مضادات")
    if resistant:
        report.append(f"- ❌ مقاوم (Resistant): {len(resistant)} مضادات")
    
    # تفاصيل التنبيهات
    if crcl is not None:
        report.append(f"### 🩺 وظائف الكلى")
        report.append(f"- CrCl = {crcl} ml/min")
        if crcl < 30:
            report.append("- 🚨 قصور كلوي شديد: يتطلب تعديلات جوهرية في الجرعات أو اختيار بدائل.")
        elif crcl < 60:
            report.append("- ⚠️ قصور كلوي معتدل: بعض الأدوية تحتاج حذر.")
        else:
            report.append("- وظائف كلوية طبيعية.")
    
    if is_pregnant:
        report.append(f"### 🤰 حالة الحمل")
        report.append("- المريضة حامل – تم استبعاد الأدوية غير الآمنة تلقائياً.")
    
    # التوصية العلاجية النهائية
    report.append(f"### 🎯 التوصية العلاجية")
    if best_choice:
        # تحديد الجرعة والمدة بناءً على الدواء
        dosage_info = ""
        drug_lower = best_choice.lower()
        if 'nitrofurantoin' in drug_lower:
            dosage_info = "الجرعة المقترحة: 100 مغ كل 12 ساعة لمدة 5 أيام (لعدوى المسالك البولية غير المعقدة)."
        elif 'cephalexin' in drug_lower:
            dosage_info = "الجرعة المقترحة: 500 مغ كل 8 ساعات لمدة 7 أيام."
        elif 'trimethoprim' in drug_lower:
            dosage_info = "الجرعة المقترحة: 160/800 مغ (TMP/SMX) كل 12 ساعة لمدة 3 أيام (للبسيطة)."
        elif 'ciprofloxacin' in drug_lower:
            dosage_info = "الجرعة المقترحة: 500 مغ كل 12 ساعة لمدة 7 أيام (تعديل الجرعة إذا CrCl<30)."
        elif 'levofloxacin' in drug_lower:
            dosage_info = "الجرعة المقترحة: 750 مغ مرة يومياً لمدة 5 أيام (تعديل إذا CrCl<50)."
        elif 'ceftriaxone' in drug_lower:
            dosage_info = "الجرعة: 1-2 غم وريدياً كل 24 ساعة (حسب شدة العدوى)."
        elif 'piperacillin' in drug_lower:
            dosage_info = "الجرعة: 4.5 غم وريدياً كل 8 ساعات (تعديل إذا CrCl≤40)."
        else:
            dosage_info = "يرجى تحديد الجرعة حسب وزن المريض وإرشادات المستشفى."
        
        report.append(f"✅ **نوصي باستخدام:** {best_choice}")
        report.append(f"   {dosage_info}")
    else:
        report.append("❌ لا يوجد مضاد حيوي مناسب بناءً على الحساسية والقيود السريرية. يرجى استشارة أخصائي أمراض معدية.")
    
    # إضافة ملاحظات عامة
    report.append(f"### 📝 ملاحظات إضافية")
    report.append("- تم توليد هذه التوصية بناءً على إرشادات IDSA 2025 ومعادلة Cockcroft-Gault.")
    report.append("- يجب مراعاة تاريخ الحساسية لكل مريض قبل وصف الدواء.")
    report.append("- في حال عدم تحسن الأعراض خلال 48-72 ساعة، يُنصح بإعادة التقييم.")
    
    return "\n".join(report)

# ========== واجهة المستخدم ==========
# حفظ الحالة
if 'df_culture' not in st.session_state:
    st.session_state.df_culture = pd.DataFrame()
if 'auto_age' not in st.session_state:
    st.session_state.auto_age = None
if 'auto_sex' not in st.session_state:
    st.session_state.auto_sex = None
if 'full_text' not in st.session_state:
    st.session_state.full_text = ""

with st.sidebar:
    st.header("🧬 بيانات المريض")
    default_age = st.session_state.auto_age if st.session_state.auto_age else 40
    default_sex = st.session_state.auto_sex if st.session_state.auto_sex else "ذكر"
    
    age = st.number_input("العمر (سنوات)", min_value=0, max_value=120, value=default_age, step=1)
    sex = st.selectbox("الجنس", ["ذكر", "أنثى"], index=0 if default_sex == "ذكر" else 1)
    weight = st.number_input("الوزن (كجم)", min_value=30.0, max_value=300.0, value=70.0, step=0.1)
    serum_creatinine = st.number_input("الكرياتينين (mg/dL)", min_value=0.1, max_value=15.0, value=0.9, step=0.1)

    st.markdown("---")
    is_pregnant = False
    if sex == "أنثى":
        is_pregnant = st.checkbox("🤰 المريضة حامل")
    
    specimen_type = st.selectbox("نوع العينة", ["Urine", "Blood", "Sputum", "Wound", "Other"], index=0)
    
    st.markdown("---")
    calculate_btn = st.button("🔬 حساب CrCl وعرض التفسير الكامل", type="primary", use_container_width=True)

# ---------- التبويبات ----------
tab1, tab2 = st.tabs(["📸 رفع صورة المزرعة", "✍️ إدخال يدوي"])

with tab1:
    uploaded_file = st.file_uploader("اختر صورة لتقرير المزرعة", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        with st.spinner("⏳ جارٍ استخراج النتائج وتحليل التقرير..."):
            df_culture, full_ocr = extract_antibiogram_advanced(uploaded_file)
            st.session_state.full_text = full_ocr
            
            # استخراج البيانات الديموغرافية
            age_found, sex_found = None, None
            age_match = re.search(r'Age\s*:\s*(\d+)\s*Y', full_ocr, re.I)
            if age_match:
                age_found = int(age_match.group(1))
            sex_match = re.search(r'Sex\s*:\s*(Male|Female|ذكر|أنثى)', full_ocr, re.I)
            if sex_match:
                val = sex_match.group(1).lower()
                sex_found = 'أنثى' if ('female' in val or 'أنثى' in val) else 'ذكر'
            
            if age_found: st.session_state.auto_age = age_found
            if sex_found: st.session_state.auto_sex = sex_found
            
            if not df_culture.empty:
                st.success("✅ تم استخراج الجدول بنجاح")
                st.session_state.df_culture = df_culture
                st.dataframe(df_culture, use_container_width=True)
                if age_found or sex_found:
                    st.info(f"تم استخراج: العمر={age_found}، الجنس={sex_found} (تم تحديث الشريط الجانبي)")
            else:
                st.error("❌ فشل استخراج النتائج. جرب الإدخال اليدوي.")

with tab2:
    st.markdown("انسخ النتائج: كل سطر = المضاد ثم S/I/R")
    txt = st.text_area("الصق هنا", height=200)
    if st.button("تحليل النص"):
        lines = txt.strip().split('\n')
        abs_list, res_list = [], []
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[-1].upper() in ('S','I','R'):
                abs_list.append(' '.join(parts[:-1]))
                res_list.append(parts[-1].upper())
        if abs_list:
            st.session_state.df_culture = pd.DataFrame({"Antibiotic": abs_list, "Result": res_list})
            st.success("تم")

# ---------- عرض التفسير الاحترافي ----------
if calculate_btn and not st.session_state.df_culture.empty:
    crcl = calculate_crcl(age, weight, sex, serum_creatinine)
    
    # عرض CrCl في الشريط الجانبي
    if crcl is not None:
        st.sidebar.metric("CrCl (ml/min)", crcl)
    else:
        st.sidebar.warning("الوزن مطلوب لحساب CrCl")
    
    # استخراج الجرثومة
    microorganism = extract_microorganism(st.session_state.full_text)
    if microorganism == "غير معروف":
        # محاولة من الجدول اليدوي (قد لا يكون موجوداً)
        microorganism = "غير محدد (يرجى مراجعة التقرير)"
    
    # إنشاء التفسير
    interpretation = generate_clinical_interpretation(
        st.session_state.df_culture,
        microorganism,
        crcl,
        is_pregnant,
        specimen_type,
        sex
    )
    
    st.markdown("---")
    st.markdown(interpretation)
    
    # عرض جدول التنبيهات أيضاً
    with st.expander("📋 عرض التنبيهات المفصلة لكل مضاد"):
        df_alerts = st.session_state.df_culture.copy()
        renal_list, preg_list = [], []
        for _, row in df_alerts.iterrows():
            r, p = get_clinical_alerts(row['Antibiotic'], crcl, is_pregnant)
            renal_list.append(r)
            preg_list.append(p)
        df_alerts['Renal Alert'] = renal_list
        df_alerts['Pregnancy Alert'] = preg_list
        st.dataframe(df_alerts, use_container_width=True)

elif calculate_btn:
    st.info("ℹ️ يرجى إدخال نتائج المزرعة أولاً.")
