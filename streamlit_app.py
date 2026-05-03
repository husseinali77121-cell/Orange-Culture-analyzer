import streamlit as st
import pandas as pd
import numpy as np
import cv2
import pytesseract
import re

st.set_page_config(page_title="Clinical Review Engine", layout="wide")
st.title("🧬 نظام مراجعة تقارير المزارع (OCR + Clinical Engine)")

# =========================
# 🖼️ Image Preprocessing
# =========================
def preprocess(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, 30, 7, 21)

    th = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11, 2
    )

    # deskew
    coords = np.column_stack(np.where(th > 0))
    if len(coords) > 0:
        angle = cv2.minAreaRect(coords)[-1]
        angle = -(90 + angle) if angle < -45 else -angle
        (h, w) = th.shape
        M = cv2.getRotationMatrix2D((w//2, h//2), angle, 1.0)
        th = cv2.warpAffine(th, M, (w, h),
                            flags=cv2.INTER_CUBIC,
                            borderMode=cv2.BORDER_REPLICATE)
    return th

# =========================
# 🧾 Demographics Extraction
# =========================
def extract_demographics(text):
    data = {
        "name": None,
        "age": None,
        "sex": None,
        "pregnant": None,
        "creatinine": None
    }

    # Name (Arabic/English after Name:)
    m = re.search(r'Name\s*:\s*(.+)', text, re.I)
    if m:
        data["name"] = m.group(1).strip()

    # Age
    m = re.search(r'Age\s*:\s*(\d+)', text, re.I)
    if m:
        data["age"] = int(m.group(1))

    # Sex
    m = re.search(r'Sex\s*:\s*(Male|Female|ذكر|أنثى)', text, re.I)
    if m:
        val = m.group(1).lower()
        data["sex"] = "أنثى" if ("female" in val or "أنثى" in val) else "ذكر"

    # Creatinine (لو مذكورة)
    m = re.search(r'Creatinine\s*[:\-]?\s*([\d\.]+)', text, re.I)
    if m:
        data["creatinine"] = float(m.group(1))

    # Pregnancy (من checkbox في UI لاحقًا غالبًا)
    return data

# =========================
# 🦠 Organism + Specimen
# =========================
def extract_micro(text):
    m = re.search(r'(Klebsiella|Escherichia coli|E\.?\s*coli|Pseudomonas|Staphylococcus|Enterococcus)', text, re.I)
    org = m.group(1) if m else "Unknown"

    spec = "Other"
    if re.search(r'Urine', text, re.I): spec = "Urine"
    elif re.search(r'Blood', text, re.I): spec = "Blood"
    elif re.search(r'Sputum', text, re.I): spec = "Sputum"

    return org, spec

# =========================
# 💊 Drug Normalization
# =========================
DRUG_MAP = {
    "amoxycillin clavulanate": "Amoxicillin/Clavulanate",
    "amoxicillin clavulanate": "Amoxicillin/Clavulanate",
    "cefoperazone sulbactam": "Cefoperazone/Sulbactam",
    "tazobactam": "Piperacillin/Tazobactam",
    "piptazo": "Piperacillin/Tazobactam",
    "tmp smx": "Trimethoprim/Sulfamethoxazole",
    "co trimoxazole": "Trimethoprim/Sulfamethoxazole",
}

def normalize_drug(name):
    n = name.lower().strip()
    n = re.sub(r'[^a-z/\+\- ]', '', n)
    for k,v in DRUG_MAP.items():
        if k in n:
            return v
    return name.strip()

# =========================
# 🔍 Extract Antibiogram (3 columns rule-based)
# =========================
def extract_antibiogram(file):
    file_bytes = np.asarray(bytearray(file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if img is None:
        return pd.DataFrame(), ""

    th = preprocess(img)
    data = pytesseract.image_to_data(th, output_type=pytesseract.Output.DICT)
    text = pytesseract.image_to_string(th)

    words = []
    for i in range(len(data['text'])):
        t = data['text'][i].strip()
        if t:
            words.append({
                "text": t,
                "x": data['left'][i],
                "y": data['top'][i]
            })

    if len(words) < 10:
        return pd.DataFrame(), text

    width = th.shape[1]

    # assign columns by x (no sklearn)
    for w in words:
        if w['x'] < width*0.33:
            w['col'] = 'S'
        elif w['x'] < width*0.66:
            w['col'] = 'I'
        else:
            w['col'] = 'R'

    # group rows
    rows = {}
    for w in words:
        yk = round(w['y']/12)*12
        if yk not in rows:
            rows[yk] = {"S":[], "I":[], "R":[]}
        rows[yk][w['col']].append(w['text'])

    abx, res = [], []

    for y in sorted(rows.keys()):
        for c in ['S','I','R']:
            txt = " ".join(rows[y][c]).strip()
            txt = normalize_drug(txt)

            if len(txt) > 4 and txt.lower() not in ['sensitive','intermediate','resistant']:
                abx.append(txt)
                res.append(c)

    df = pd.DataFrame({"Antibiotic": abx, "Result": res})
    df = df.drop_duplicates()
    return df, text

# =========================
# 🧪 Renal Function
# =========================
def calc_crcl(age, weight, cr, sex):
    if not age or not weight or not cr:
        return None
    val = ((140-age)*weight)/(72*cr)
    if sex == "أنثى":
        val *= 0.85
    return round(val,1)

# =========================
# ⚠️ Contraindications
# =========================
def check_contra(ab, pregnant, age, crcl):
    alerts = []
    ab = ab.lower()

    if pregnant:
        if any(x in ab for x in ["tetracycline","doxycycline"]):
            alerts.append("❌ contraindicated in pregnancy")
        if "fluoro" in ab or "cipro" in ab:
            alerts.append("⚠️ avoid in pregnancy")

    if age and age < 18:
        if "cipro" in ab:
            alerts.append("⚠️ avoid in pediatrics")

    if crcl and crcl < 30:
        if "nitrofurantoin" in ab:
            alerts.append("❌ avoid (renal)")

    return alerts

# =========================
# 🧠 Clinical Engine
# =========================
def clinical_decision(df, org, spec, pregnant, age, crcl):

    S = df[df.Result=="S"]["Antibiotic"].tolist()
    I = df[df.Result=="I"]["Antibiotic"].tolist()
    R = df[df.Result=="R"]["Antibiotic"].tolist()

    report = []
    report.append(f"### 🦠 Organism: {org}")
    report.append(f"### 🧫 Specimen: {spec}")
    report.append(f"S:{len(S)} | I:{len(I)} | R:{len(R)}")

    safe = []
    for d in S:
        alerts = check_contra(d, pregnant, age, crcl)
        if not any("❌" in a for a in alerts):
            safe.append((d, alerts))

    # selection logic
    best = None

    if "urine" in spec.lower():
        for pref in ["Nitrofurantoin","Fosfomycin","Cephalexin"]:
            for d,_ in safe:
                if pref.lower() in d.lower():
                    best = d
                    break
            if best: break

    if not best and safe:
        best = safe[0][0]

    # flags
    if len(R) > len(S):
        report.append("🚨 MDR suspected")

    if any("clavulanate" in r.lower() for r in R):
        report.append("⚠️ possible ESBL")

    report.append("### 💊 Recommendation")
    if best:
        report.append(f"Use: {best}")
    else:
        report.append("No safe antibiotic found")

    return "\n".join(report)

# =========================
# UI
# =========================
uploaded = st.file_uploader("📸 ارفع التقرير")

age = st.number_input("Age", 1, 100, 40)
sex = st.selectbox("Sex", ["ذكر","أنثى"])
weight = st.number_input("Weight", 30.0, 150.0, 70.0)
cr = st.number_input("Creatinine", 0.1, 10.0, 1.0)
preg = st.checkbox("Pregnant") if sex=="أنثى" else False

if uploaded:
    df, text = extract_antibiogram(uploaded)

    demo = extract_demographics(text)
    org, spec = extract_micro(text)
    crcl = calc_crcl(age, weight, cr, sex)

    if not df.empty:
        st.dataframe(df)

        report = clinical_decision(df, org, spec, preg, age, crcl)

        st.markdown("---")
        st.markdown(report)
    else:
        st.error("فشل استخراج البيانات")
