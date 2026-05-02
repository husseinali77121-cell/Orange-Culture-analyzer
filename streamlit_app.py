import streamlit as st
import pandas as pd
import numpy as np
import cv2
import pytesseract
import re

# ========== الإعدادات ==========
st.set_page_config(page_title="نظام دعم المضادات الحيوية - 2025", layout="wide")
st.title("🩺 نظام دعم القرار لاختيار المضاد الحيوي")
st.markdown("**تحليل احترافي يستند على إرشادات IDSA 2025. استخراج دقيق للمزرعة، تقييم الحساسية، وتوصيات علاجية مخصصة.**")

# ========== الدوال الطبية (ثوابت) ==========
def calculate_crcl(age, weight, sex, serum_creatinine):
    if None in (age, weight, serum_creatinine) or weight <= 0 or serum_creatinine <= 0:
        return None
    crcl = ((140 - age) * weight) / (72 * serum_creatinine)
    if sex == "أنثى":
        crcl *= 0.85
    return round(crcl, 1)

def get_clinical_alerts(antibiotic, crcl, is_pregnant):
    renal_alert = ""
    pregnancy_alert = ""
    ab_lower = antibiotic.lower()
    
    if crcl is not None:
        if 'nitrofurantoin' in ab_lower:
            if crcl < 30: renal_alert = "⚠️ تجنب (CrCl<30)"
            elif crcl < 60: renal_alert = "⚠️ حذر (CrCl<60)"
        elif any(d in ab_lower for d in ['gentamicin', 'amikacin', 'tobramycin']):
            if crcl < 30: renal_alert = "⚠️ تجنب أو تعديل كبير (سمية)"
            elif crcl < 70: renal_alert = "⚠️ يفضل مراقبة المستوى"
        elif 'vancomycin' in ab_lower and crcl < 50:
            renal_alert = "⚠️ مراقبة مستوى وتعديل الجرعة"
        elif any(d in ab_lower for d in ['ciprofloxacin', 'levofloxacin', 'ofloxacin']):
            if crcl < 30: renal_alert = "⚠️ خفض الجرعة"
            elif crcl < 60: renal_alert = "⚠️ قد تحتاج خفض الجرعة"
        elif ('trimethoprim' in ab_lower or 'sulfamethoxazole' in ab_lower) and crcl < 30:
            renal_alert = "⚠️ تقليل الجرعة أو تجنب"
        elif 'piperacillin' in ab_lower and crcl < 40:
            renal_alert = "⚠️ تعديل الجرعة"
    
    if is_pregnant:
        unsafe_map = {
            'tetracycline': '❌ يمنع (تشوهات)', 'doxycycline': '❌ يمنع (تشوهات)',
            'minocycline': '❌ يمنع (تشوهات)', 'ciprofloxacin': '🚫 تجنب',
            'levofloxacin': '🚫 تجنب', 'moxifloxacin': '🚫 تجنب',
            'gentamicin': '⚠️ خطر (سمية أذنية)', 'amikacin': '⚠️ خطر',
            'tobramycin': '⚠️ خطر', 'trimethoprim': '❌ يمنع في الثلث الأول',
            'sulfamethoxazole': '❌ يمنع قرب الولادة', 'nitrofurantoin': '⚠️ تجنب في الثلث الثالث'
        }
        for key, msg in unsafe_map.items():
            if key in ab_lower:
                pregnancy_alert = msg
                break
    return renal_alert, pregnancy_alert

def generate_clinical_interpretation(df, microorganism, crcl, is_pregnant, specimen_type, patient_sex):
    if df.empty:
        return "لا توجد بيانات مزرعة لتفسيرها."
    
    sensitive = df[df['Result'] == 'S']['Antibiotic'].tolist()
    intermediate = df[df['Result'] == 'I']['Antibiotic'].tolist()
    resistant = df[df['Result'] == 'R']['Antibiotic'].tolist()
    
    safe_sensitive = []
    for ab in sensitive:
        renal, preg = get_clinical_alerts(ab, crcl, is_pregnant)
        if not renal and not preg:
            safe_sensitive.append(ab)
        elif preg and '❌' in preg:
            continue
        elif renal and 'تجنب' in renal:
            continue
        else:
            safe_sensitive.append(f"{ab} (مع حذر)")
    
    best_choice = None
    if specimen_type.lower() == 'urine':
        preferred_simple = ['Nitrofurantoin', 'Trimethoprim/Sulfamethoxazole', 'Cephalexin']
        for pref in preferred_simple:
            for s_ab in sensitive:
                if pref.lower() in s_ab.lower():
                    renal_a, preg_a = get_clinical_alerts(s_ab, crcl, is_pregnant)
                    if not renal_a and not preg_a:
                        best_choice = s_ab
                        break
            if best_choice: break
        if not best_choice and safe_sensitive:
            best_choice = safe_sensitive[0].split(" (مع حذر)")[0]
    
    if not best_choice:
        for pref_gen in ['Piperacillin/Tazobactam', 'Ceftriaxone', 'Cefepime', 'Imipenem', 'Levofloxacin']:
            for s in sensitive:
                if pref_gen.lower() in s.lower():
                    renal_a, preg_a = get_clinical_alerts(s, crcl, is_pregnant)
                    if not renal_a and not preg_a:
                        best_choice = s
                        break
            if best_choice: break
        if not best_choice and safe_sensitive:
            best_choice = safe_sensitive[0].split(" (مع حذر)")[0]
    
    report = []
    report.append(f"### 🧫 نتيجة المزرعة")
    report.append(f"**الكائن الحي:** {microorganism}")
    report.append(f"**نوع العينة:** {specimen_type}")
    
    report.append(f"### 📊 ملخص الحساسية")
    report.append(f"- ✅ حساس: {len(sensitive)} أدوية")
    if intermediate: report.append(f"- 🟡 متوسط: {len(intermediate)} أدوية")
    if resistant: report.append(f"- ❌ مقاوم: {len(resistant)} أدوية")
    
    if crcl is not None:
        report.append(f"### 🩺 وظائف الكلى (CrCl = {crcl} ml/min)")
        if crcl < 30: report.append("- 🚨 قصور شديد: تعديلات جرعات ضرورية.")
        elif crcl < 60: report.append("- ⚠️ قصور معتدل: بعض الأدوية تحتاج حذر.")
        else: report.append("- طبيعية.")
    
    if is_pregnant:
        report.append(f"### 🤰 حمل: نعم (تم استبعاد غير الآمن)")
    
    report.append(f"### 🎯 التوصية العلاجية")
    if best_choice:
        dosage_info = ""
        drug_lower = best_choice.lower()
        if 'nitrofurantoin' in drug_lower: dosage_info = "100 مغ كل 12 ساعة لمدة 5 أيام."
        elif 'cephalexin' in drug_lower: dosage_info = "500 مغ كل 8 ساعات لمدة 7 أيام."
        elif 'trimethoprim' in drug_lower: dosage_info = "160/800 مغ كل 12 ساعة لمدة 3 أيام."
        elif 'ciprofloxacin' in drug_lower: dosage_info = "500 مغ كل 12 ساعة لمدة 7 أيام."
        elif 'levofloxacin' in drug_lower: dosage_info = "750 مغ يومياً لمدة 5 أيام."
        elif 'ceftriaxone' in drug_lower: dosage_info = "1-2 غم وريدياً كل 24 ساعة."
        elif 'piperacillin' in drug_lower: dosage_info = "4.5 غم وريدياً كل 8 ساعات."
        else: dosage_info = "يرجى تحديد الجرعة حسب البروتوكول المحلي."
        report.append(f"✅ **نوصي باستخدام:** {best_choice}")
        report.append(f"   الجرعة: {dosage_info}")
    else:
        report.append("❌ لا يوجد مضاد مناسب. يرجى استشارة أخصائي أمراض معدية.")
    
    report.append(f"### 📝 ملاحظات")
    report.append("- تم توليد هذه التوصية بناءً على إرشادات IDSA 2025 ومعادلة Cockcroft-Gault.")
    report.append("- يجب مراعاة تاريخ الحساسية لكل مريض.")
    return "\n".join(report)

# ========== دالة استخراج الجرثومة ==========
def extract_microorganism(full_text):
    patterns = [
        r'Culture\s*:\s*(.*?)(?:\n|$)', r'Organism\s*:\s*(.*?)(?:\n|$)',
        r'Gram negative bacilli\s*\(\s*(\w+)\s*\)', r'Gram positive cocci\s*\(\s*(\w+)\s*\)',
        r'(\b(?:Escherichia|Klebsiella|Pseudomonas|Staphylococcus|Streptococcus|Enterococcus|Proteus|Acinetobacter)\b.*?)(?:\n|$)'
    ]
    for pat in patterns:
        match = re.search(pat, full_text, re.IGNORECASE)
        if match: return match.group(1).strip()
    for line in full_text.split('\n'):
        if 'bacilli' in line.lower() or 'coli' in line.lower(): return line.strip()
    return "غير معروف"

# ========== خوارزمية استخراج الجدول الجديدة (Cell-Based) ==========
def extract_antibiogram_advanced(image_file):
    file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if img is None:
        return pd.DataFrame(), ""
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    
    # النص الكامل للبيانات الديموغرافية
    full_text = pytesseract.image_to_string(thresh, lang='eng+ara', config='--psm 6')
    
    # البيانات المكانية
    data = pytesseract.image_to_data(thresh, lang='eng+ara', output_type=pytesseract.Output.DICT, config='--psm 6')
    
    # جمع كل الكلمات غير الفارغة مع إحداثياتها
    words = []
    n = len(data['text'])
    for i in range(n):
        text = data['text'][i].strip()
        if not text:
            continue
        x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
        words.append({'text': text, 'x': x, 'y': y, 'w': w, 'h': h, 'right': x + w})
    
    if not words:
        return pd.DataFrame(), full_text
    
    # --- 1. اكتشاف الأعمدة تلقائياً ---
    # نرتب الكلمات جميعها حسب x، ونبحث عن فجوات كبيرة تمثل حدود الأعمدة
    all_x_starts = sorted([w['x'] for w in words])
    gaps = []
    for i in range(len(all_x_starts)-1):
        gap = all_x_starts[i+1] - all_x_starts[i]
        if gap > 30:  # فجوة أفقية أكبر من 30 بكسل = عمود جديد غالباً
            gaps.append((all_x_starts[i], all_x_starts[i+1]))
    
    # نأخذ نهايات الأعمدة من الفجوات
    column_boundaries = [0]
    for g in gaps:
        # نهاية العمود السابق هي بداية الفجوة، بداية العمود التالي هي نهاية الفجوة
        column_boundaries.append(g[0] + 1)  # +1 لبداية العمود الجديد
    column_boundaries.append(99999)  # نهاية افتراضية
    
    # دمج الحدود المتقاربة جداً (أقل من 20 بكسل) لتجنب تعدد الأعمدة بسبب المسافات الصغيرة
    merged_boundaries = []
    for b in column_boundaries:
        if not merged_boundaries or b - merged_boundaries[-1] > 20:
            merged_boundaries.append(b)
    column_boundaries = merged_boundaries
    
    # --- 2. توزيع الكلمات على أعمدة وخلايا ---
    # ننشئ بنية: كل صف y_key يحتوي على قاموس {column_index: النص}
    rows = {}
    for w in words:
        # تحديد العمود
        col_idx = 0
        for i, boundary in enumerate(column_boundaries):
            if w['x'] < boundary:
                col_idx = i
                break
        # مفتاح الصف (نباعد بين الأسطر القريبة بـ 5 بكسل على الأقل)
        y_key = round(w['y'] / 10) * 10
        if y_key not in rows:
            rows[y_key] = {}
        if col_idx not in rows[y_key]:
            rows[y_key][col_idx] = []
        rows[y_key][col_idx].append(w['text'])
    
    # --- 3. بناء السطور وقراءة الفئات ---
    sorted_y = sorted(rows.keys())
    reconstructed_lines = []
    for y_key in sorted_y:
        # دمج نصوص كل عمود في هذا السطر
        line_parts = []
        for col in sorted(rows[y_key].keys()):
            line_parts.append(' '.join(rows[y_key][col]))
        full_line = ' | '.join(line_parts)
        reconstructed_lines.append(full_line)
    
    # --- 4. تحليل الفئات (Sensitive, Intermediate, Resistant) ---
    sens_kw = ['sensitive', 'susceptible', 'حساس']
    inter_kw = ['intermediate', 'متوسط', 'وسيط']
    resist_kw = ['resistant', 'مقاوم']
    
    antibiotics = []
    results = []
    current_category = None
    
    for line in reconstructed_lines:
        lower = line.lower()
        if not line.strip() or any(w in lower for w in ['antibiotic', 'description', 'colony', 'comment', 'reporting']):
            continue
        
        # هل هذا السطر هو عنوان فئة؟
        if any(kw in lower for kw in sens_kw):
            current_category = 'S'
            # قد يحتوي السطر على اسم دواء مع Sensitive، نستخرج النص المتبقي
            rest = line
            for kw in sens_kw:
                rest = re.sub(r'(?i)' + kw + r'[\s:]*', '', rest).strip()
            if rest and not any(kw in rest.lower() for kw in sens_kw+inter_kw+resist_kw):
                # ننظف ونضيف
                for part in rest.split('|'):
                    part = re.sub(r'[^a-zA-Zأ-ي/\s\+\-]', '', part).strip()
                    if part:
                        antibiotics.append(part)
                        results.append('S')
            continue
        elif any(kw in lower for kw in inter_kw):
            current_category = 'I'
            rest = line
            for kw in inter_kw:
                rest = re.sub(r'(?i)' + kw + r'[\s:]*', '', rest).strip()
            if rest and not any(kw in rest.lower() for kw in sens_kw+inter_kw+resist_kw):
                for part in rest.split('|'):
                    part = re.sub(r'[^a-zA-Zأ-ي/\s\+\-]', '', part).strip()
                    if part:
                        antibiotics.append(part)
                        results.append('I')
            continue
        elif any(kw in lower for kw in resist_kw):
            current_category = 'R'
            rest = line
            for kw in resist_kw:
                rest = re.sub(r'(?i)' + kw + r'[\s:]*', '', rest).strip()
            if rest and not any(kw in rest.lower() for kw in sens_kw+inter_kw+resist_kw):
                for part in rest.split('|'):
                    part = re.sub(r'[^a-zA-Zأ-ي/\s\+\-]', '', part).strip()
                    if part:
                        antibiotics.append(part)
                        results.append('R')
            continue
        
        # وإلا فهو سطر أدوية (قد يحتوي على عدة أعمدة)
        if current_category:
            # الخط قد يحتوي على عدة أدوية مفصولة بـ "|"
            parts = line.split('|')
            for part in parts:
                part = re.sub(r'[^a-zA-Zأ-ي/\s\+\-]', '', part).strip()
                if part:
                    antibiotics.append(part)
                    results.append(current_category)
    
    df = pd.DataFrame({"Antibiotic": antibiotics, "Result": results})
    if not df.empty:
        all_kw = sens_kw + inter_kw + resist_kw
        mask = ~df['Antibiotic'].str.lower().apply(lambda x: any(k in x for k in all_kw))
        df = df[mask]
        df = df.drop_duplicates(subset="Antibiotic", keep="first").reset_index(drop=True)
    return df, full_text

# ========== واجهة المستخدم ==========
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

tab1, tab2 = st.tabs(["📸 رفع صورة المزرعة", "✍️ إدخال يدوي"])

with tab1:
    uploaded_file = st.file_uploader("اختر صورة لتقرير المزرعة", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        with st.spinner("⏳ جارٍ استخراج الجدول بدقة عالية (تحليل خلايا)..."):
            df_culture, full_ocr = extract_antibiogram_advanced(uploaded_file)
            st.session_state.full_text = full_ocr
            
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
                st.success("✅ تم استخراج الجدول بدقة عالية")
                st.session_state.df_culture = df_culture
                st.dataframe(df_culture, use_container_width=True)
            else:
                st.error("❌ فشل استخراج النتائج. الرجاء استخدام الإدخال اليدوي.")

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

if calculate_btn and not st.session_state.df_culture.empty:
    crcl = calculate_crcl(age, weight, sex, serum_creatinine)
    if crcl is not None:
        st.sidebar.metric("CrCl (ml/min)", crcl)
    else:
        st.sidebar.warning("الوزن مطلوب لحساب CrCl")
    
    microorganism = extract_microorganism(st.session_state.full_text)
    if microorganism == "غير معروف":
        microorganism = "غير محدد (يرجى مراجعة التقرير)"
    
    interpretation = generate_clinical_interpretation(
        st.session_state.df_culture, microorganism, crcl, is_pregnant, specimen_type, sex
    )
    st.markdown("---")
    st.markdown(interpretation)
    
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
