import streamlit as st
import pandas as pd
import numpy as np
import cv2
import pytesseract
import re
from sklearn.cluster import KMeans

st.set_page_config(page_title="Antibiotic Decision Support PRO", layout="wide")
st.title("🧬 Antibiotic Decision Support System (Enhanced)")

# =========================
# 🧠 تحسين الصورة قبل OCR
# =========================
def preprocess_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Denoise
    gray = cv2.fastNlMeansDenoising(gray, None, 30, 7, 21)

    # Adaptive threshold
    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11, 2
    )

    # Deskew
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
# 🔍 OCR Hybrid Extraction
# =========================
def extract_antibiogram(image_file):
    file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

    if img is None:
        return pd.DataFrame(), ""

    processed = preprocess_image(img)

    full_text = pytesseract.image_to_string(processed, config='--psm 6')

    antibiotics, results = [], []

    # 🔥 Regex (الأقوى)
    pattern = r'([A-Za-z/\-\+ ]+)\s+(S|I|R)\b'
    matches = re.findall(pattern, full_text)

    for ab, res in matches:
        ab = ab.strip()
        if len(ab) > 2:
            antibiotics.append(ab)
            results.append(res)

    # fallback لو regex فشل
    if len(antibiotics) < 3:
        data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)

        words = []
        for i in range(len(data['text'])):
            txt = data['text'][i].strip()
            if txt:
                words.append((txt, data['left'][i]))

        if len(words) > 5:
            x_vals = np.array([w[1] for w in words]).reshape(-1,1)
            kmeans = KMeans(n_clusters=3, random_state=0).fit(x_vals)

            for i, (txt, _) in enumerate(words):
                if txt.upper() in ['S','I','R'] and i > 0:
                    antibiotics.append(words[i-1][0])
                    results.append(txt.upper())

    df = pd.DataFrame({"Antibiotic": antibiotics, "Result": results})
    df = df.drop_duplicates()

    return df, full_text


# =========================
# 🧫 استخراج الكائن
# =========================
def extract_organism(text):
    match = re.search(r'(Escherichia coli|Klebsiella|Pseudomonas|Staphylococcus)', text, re.I)
    return match.group(1) if match else "Unknown"


# =========================
# 🧠 Clinical Engine
# =========================
def get_priority_list(org):
    org = org.lower()

    if 'coli' in org:
        return ['Nitrofurantoin','Fosfomycin','TMP-SMX','Cephalexin']
    elif 'pseudomonas' in org:
        return ['Piperacillin/Tazobactam','Cefepime','Meropenem']
    elif 'staphylococcus' in org:
        return ['Oxacillin','Vancomycin','Linezolid']
    return []


def adjust_dose(ab, crcl):
    ab = ab.lower()

    if 'ciprofloxacin' in ab:
        return "500 mg q12h" if crcl > 30 else "500 mg q24h"
    if 'vancomycin' in ab:
        return "TDM required"
    if 'nitrofurantoin' in ab:
        return "Avoid if CrCl <30"
    return "Standard dosing"


def generate_report(df, organism, crcl):
    sensitive = df[df['Result']=='S']['Antibiotic'].tolist()
    resistant = df[df['Result']=='R']['Antibiotic'].tolist()

    priority = get_priority_list(organism)

    best = None
    for p in priority:
        for s in sensitive:
            if p.lower() in s.lower():
                best = s
                break
        if best:
            break

    if not best and sensitive:
        best = sensitive[0]

    report = []
    report.append(f"### 🦠 Organism: {organism}")
    report.append(f"### 📊 Sensitive: {len(sensitive)} | Resistant: {len(resistant)}")

    if crcl:
        report.append(f"### 🧪 CrCl: {crcl} ml/min")

    if best:
        dose = adjust_dose(best, crcl)
        report.append(f"## ✅ Recommended: {best}")
        report.append(f"💊 Dose: {dose}")

    if len(resistant) > len(sensitive):
        report.append("🚨 Possible MDR organism")

    if 'pseudomonas' in organism.lower() and best and 'ceftriaxone' in best.lower():
        report.append("⚠️ Ceftriaxone not reliable vs Pseudomonas")

    return "\n".join(report)


# =========================
# UI
# =========================
uploaded = st.file_uploader("Upload Culture Image")

age = st.number_input("Age", 1, 100, 40)
weight = st.number_input("Weight", 30.0, 150.0, 70.0)
cr = st.number_input("Creatinine", 0.1, 10.0, 1.0)

def calc_crcl(age, weight, cr):
    return ((140-age)*weight)/(72*cr)

if uploaded:
    df, text = extract_antibiogram(uploaded)

    if not df.empty:
        st.success("Extracted successfully")
        st.dataframe(df)

        organism = extract_organism(text)
        crcl = calc_crcl(age, weight, cr)

        report = generate_report(df, organism, crcl)

        st.markdown("---")
        st.markdown(report)

    else:
        st.error("Extraction failed")
