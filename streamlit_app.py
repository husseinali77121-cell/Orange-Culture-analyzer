import streamlit as st
import pandas as pd
import numpy as np
import cv2
import pytesseract
import re

st.set_page_config(layout="wide")
st.title("🧬 Clinical Culture Analyzer PRO")

# =========================
# 🖼️ Image Processing
# =========================
def preprocess(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, 30, 7, 21)

    th = cv2.adaptiveThreshold(
        gray,255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,11,2
    )
    return th

# =========================
# 🧾 Patient Extraction
# =========================
def extract_patient(text):

    def safe_search(pattern):
        m = re.search(pattern, text, re.I)
        return m.group(1).strip() if m else None

    name = safe_search(r'Name\s*:\s*(.+)')
    age = safe_search(r'Age\s*:\s*(\d+)')
    sex = safe_search(r'Sex\s*:\s*(Male|Female|ذكر|أنثى)')

    if sex:
        sex = "أنثى" if "female" in sex.lower() or "أنثى" in sex else "ذكر"

    return {
        "name": name,
        "age": int(age) if age else None,
        "sex": sex
    }

# =========================
# 🦠 Organism
# =========================
def extract_organism(text):
    pattern = r'(Klebsiella|E\.?\s*coli|Escherichia coli|Pseudomonas|Staphylococcus)'
    m = re.search(pattern, text, re.I)
    return m.group(1) if m else "Unknown"

# =========================
# 💊 Drug Normalization
# =========================
DRUG_FIX = {
    "amoxycillin clavulanate": "Amoxicillin/Clavulanate",
    "cefoperazone sulbactam": "Cefoperazone/Sulbactam",
    "tazobactam": "Piperacillin/Tazobactam",
}

def normalize_drug(txt):
    txt = txt.lower()
    txt = re.sub(r'[^a-z/\+\- ]', '', txt)

    for k,v in DRUG_FIX.items():
        if k in txt:
            return v

    return txt.title()

# =========================
# 🔍 Antibiogram Extraction
# =========================
def extract_antibiogram(file):

    img = cv2.imdecode(np.asarray(bytearray(file.read()), dtype=np.uint8), 1)
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

    width = th.shape[1]

    # column split
    for w in words:
        if w['x'] < width*0.33:
            w['col'] = 'S'
        elif w['x'] < width*0.66:
            w['col'] = 'I'
        else:
            w['col'] = 'R'

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

    df = pd.DataFrame({"Antibiotic":abx,"Result":res})
    df = df.drop_duplicates()

    return df, text

# =========================
# ⚠️ Contraindications
# =========================
def check_contra(drug, age, pregnant):

    d = drug.lower()
    issues = []

    if pregnant:
        if any(x in d for x in ["doxycycline","tetracycline"]):
            issues.append("❌ contraindicated in pregnancy")
        if "cipro" in d:
            issues.append("⚠️ avoid in pregnancy")

    if age and age < 18:
        if "cipro" in d:
            issues.append("⚠️ avoid in children")

    return issues

# =========================
# 🧠 Decision Engine
# =========================
def clinical_engine(df, organism, age, pregnant):

    S = df[df.Result=="S"]["Antibiotic"].tolist()
    I = df[df.Result=="I"]["Antibiotic"].tolist()
    R = df[df.Result=="R"]["Antibiotic"].tolist()

    report = []

    report.append(f"### 🦠 Organism: {organism}")
    report.append(f"S:{len(S)} | I:{len(I)} | R:{len(R)}")

    safe = []

    for d in S:
        alerts = check_contra(d, age, pregnant)

        if not any("❌" in a for a in alerts):
            safe.append((d, alerts))

    best = None

    # organism-based
    if "klebsiella" in organism.lower():
        for d,_ in safe:
            if "imipenem" in d.lower():
                best = d
                break

    if not best and safe:
        best = safe[0][0]

    if len(R) > len(S):
        report.append("🚨 MDR suspected")

    report.append("### 💊 Recommendation")
    report.append(best if best else "No suitable antibiotic")

    report.append("### ⚠️ Notes")
    for d,a in safe:
        if a:
            report.append(f"{d}: {a}")

    return "\n".join(report)

# =========================
# UI
# =========================
uploaded = st.file_uploader("📸 Upload report")

if uploaded:
    df, text = extract_antibiogram(uploaded)
    patient = extract_patient(text)
    organism = extract_organism(text)

    preg = False
    if patient["sex"] == "أنثى":
        preg = st.checkbox("Pregnant")

    st.subheader("📋 Patient")
    st.write(patient)

    st.subheader("🧫 Antibiogram")
    st.dataframe(df)

    report = clinical_engine(df, organism, patient["age"], preg)

    st.markdown("---")
    st.markdown(report)
