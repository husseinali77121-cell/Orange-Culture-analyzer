import streamlit as st
import pandas as pd
import numpy as np
import cv2
import pytesseract
import re
from sklearn.cluster import KMeans

st.set_page_config(page_title="Antibiotic Decision PRO", layout="wide")
st.title("🧬 نظام دعم القرار للمضادات الحيوية (نسخة احترافية)")

# =========================
# 🖼️ تحسين الصورة
# =========================
def preprocess(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, 30, 7, 21)

    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11, 2
    )

    # deskew
    coords = np.column_stack(np.where(thresh > 0))
    angle = cv2.minAreaRect(coords)[-1]
    angle = -(90 + angle) if angle < -45 else -angle

    (h, w) = thresh.shape
    M = cv2.getRotationMatrix2D((w//2, h//2), angle, 1.0)
    thresh = cv2.warpAffine(thresh, M, (w, h),
                            flags=cv2.INTER_CUBIC,
                            borderMode=cv2.BORDER_REPLICATE)

    return thresh


# =========================
# 🔍 استخراج الجدول الحقيقي
# =========================
def extract_structured_antibiogram(file):
    file_bytes = np.asarray(bytearray(file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

    if img is None:
        return pd.DataFrame(), ""

    processed = preprocess(img)

    data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)
    full_text = pytesseract.image_to_string(processed)

    words = []
    for i in range(len(data['text'])):
        txt = data['text'][i].strip()
        if txt:
            words.append({
                "text": txt,
                "x": data['left'][i],
                "y": data['top'][i]
            })

    if len(words) < 10:
        return pd.DataFrame(), full_text

    # =========================
    # 📊 تقسيم الأعمدة
    # =========================
    x_vals = np.array([w['x'] for w in words]).reshape(-1,1)
    kmeans = KMeans(n_clusters=3, random_state=0).fit(x_vals)

    for i, w in enumerate(words):
        w['col'] = kmeans.labels_[i]

    # ترتيب الأعمدة
    col_centers = {}
    for c in range(3):
        xs = [w['x'] for w in words if w['col']==c]
        col_centers[c] = np.mean(xs)

    sorted_cols = sorted(col_centers, key=lambda c: col_centers[c])

    col_map = {
        sorted_cols[0]: 'S',
        sorted_cols[1]: 'I',
        sorted_cols[2]: 'R'
    }

    # =========================
    # 🧪 تجميع الأسطر (حل مشكلة multi-line)
    # =========================
    rows = {}

    for w in words:
        col = col_map[w['col']]
        y_key = round(w['y']/12)*12

        if y_key not in rows:
            rows[y_key] = {"S":[], "I":[], "R":[]}

        rows[y_key][col].append(w['text'])

    antibiotics = []
    results = []

    for y in sorted(rows.keys()):
        for col in ['S','I','R']:
            txt = " ".join(rows[y][col]).strip()

            # تنظيف
            txt = re.sub(r'[^a-zA-Z/\+\- ]', '', txt)

            if len(txt) > 4 and txt.lower() not in ['sensitive','intermediate','resistant']:
                antibiotics.append(txt)
                results.append(col)

    df = pd.DataFrame({"Antibiotic": antibiotics, "Result": results})

    # تنظيف junk
    df = df[df['Antibiotic'].str.len() > 4]
    df = df.drop_duplicates()

    return df, full_text


# =========================
# 🦠 استخراج البكتيريا
# =========================
def extract_organism(text):
    match = re.search(r'(Klebsiella|Escherichia coli|Pseudomonas|Staphylococcus)', text, re.I)
    return match.group(1) if match else "Unknown"


# =========================
# 💊 حساب الكلى
# =========================
def calc_crcl(age, weight, cr, sex):
    crcl = ((140-age)*weight)/(72*cr)
    if sex == "أنثى":
        crcl *= 0.85
    return round(crcl,1)


# =========================
# 🧠 Clinical Engine
# =========================
def clinical_engine(df, organism, crcl):

    sensitive = df[df['Result']=='S']['Antibiotic'].tolist()
    intermediate = df[df['Result']=='I']['Antibiotic'].tolist()
    resistant = df[df['Result']=='R']['Antibiotic'].tolist()

    report = []

    report.append(f"### 🦠 Organism: {organism}")
    report.append(f"### 📊 S:{len(sensitive)} | I:{len(intermediate)} | R:{len(resistant)}")

    # Klebsiella logic
    if 'klebsiella' in organism.lower():
        report.append("🧠 Klebsiella infection detected")

        if any('imipenem' in s.lower() for s in sensitive):
            best = "Imipenem"
            report.append("✅ First-line: Carbapenem (Imipenem)")

        elif any('piperacillin' in s.lower() for s in sensitive):
            best = "Piperacillin/Tazobactam"
            report.append("✅ Alternative: Piperacillin/Tazobactam")

        else:
            best = sensitive[0] if sensitive else None

        if any('cipro' in i.lower() for i in intermediate):
            report.append("⚠️ Fluoroquinolones not reliable (Intermediate)")

        if len(resistant) > len(sensitive):
            report.append("🚨 MDR suspected")

        if any('amox' in r.lower() for r in resistant):
            report.append("⚠️ Possible ESBL producer")

    else:
        best = sensitive[0] if sensitive else None

    # الجرعة
    dose = ""
    if best:
        if 'imipenem' in best.lower():
            dose = "500 mg IV every 6 hours"
        elif 'piperacillin' in best.lower():
            dose = "4.5 g IV every 6-8 hours"

    report.append(f"### 💊 Recommended: {best}")
    report.append(f"Dose: {dose}")

    report.append(f"### 🧪 CrCl: {crcl} ml/min")

    return "\n".join(report)


# =========================
# UI
# =========================
uploaded = st.file_uploader("📸 ارفع صورة المزرعة")

age = st.number_input("Age", 1, 100, 40)
sex = st.selectbox("Sex", ["ذكر","أنثى"])
weight = st.number_input("Weight", 30.0, 150.0, 70.0)
cr = st.number_input("Creatinine", 0.1, 10.0, 1.0)

if uploaded:
    df, text = extract_structured_antibiogram(uploaded)

    if not df.empty:
        st.success("✅ تم استخراج الجدول بدقة حقيقية")
        st.dataframe(df)

        organism = extract_organism(text)
        crcl = calc_crcl(age, weight, cr, sex)

        report = clinical_engine(df, organism, crcl)

        st.markdown("---")
        st.markdown(report)

    else:
        st.error("❌ فشل استخراج البيانات")
