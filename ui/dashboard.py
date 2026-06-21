# ui/dashboard.py
# © Dr. Hussein Ali — Orange Lab
# الواجهة الرئيسية — Main Dashboard UI

from __future__ import annotations
import io, re, time
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import streamlit.components.v1 as stc_components

try:
    import cv2, numpy as np, pytesseract
except Exception:
    cv2 = np = pytesseract = None

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from data.antibiotics  import (ABX_GUIDELINES, ABX_ALIAS_INDEX, normalize_abx_key,
                                COMMERCIAL_NAMES, get_commercial_name, COMMON_MEDS, AWARE_COLORS)
from data.organisms    import ORGANISM_PROFILE, SPECIMEN_ORGANISM_MAP
from data.phenotypes   import detect_resistance_phenotypes
from modules.analyzer  import (analyze_antibiotics, rank_sensitive_antibiotics,
                                get_infection_syndrome, calc_creatinine_clearance,
                                get_renal_severity, get_route_label,
                                uniq_keep_order, best_default_index)
from modules.ocr       import (extract_all_data_cached, make_file_hash, safe_int,
                                fuzzy_match, normalize_ocr_text, OCR_AVAILABLE)
from modules.mdr       import classify_mdr, predict_esbl
from modules.qc        import run_ast_qc, get_startup_validation_issues
from modules.pathogenicity import assess_pathogenicity
from modules.reports   import generate_decision_tree_image, generate_report, PIL_AVAILABLE
from modules.auth      import (load_subscribers, get_subscription_days_left,
                                show_login_page, check_subscription,
                                logout, handle_session_timeout, render_top_bar)

def init_session_state() -> None:
    defaults = {
        "authenticated":      False,
        "email":              "",
        "days_left":          None,
        "last_activity":      None,
        "logout_reason":      "",
        "ocr_data":           None,
        "last_file_hash":     "",
        "sir_map_edited":     {},
        "patient_name_final": "",
        "colony_count":       "≥ 10^5 CFU/mL",
        "date_in":            date.today(),
        "pus_cells_text":     "",
        "rbcs_text":          "",
        "lab_name":           "Orange Lab",
        "lab_city":           "6 October City, Egypt",
        # ─── Commercial Names ─────────────────────────────────────────────
        "show_commercial_names": False,
        # ─── Pathogenicity Assessment ─────────────────────────────────────
        "patho_culture_purity":   "Pure growth",
        "patho_symptoms":         [],
        "patho_urinalysis":       "مش معروف / مش مذكور",
        "patho_gram_stain":       "مش متعملة",
        "patho_host_factors":     [],
        "patho_sputum_pus":       "",
        "patho_sputum_epi":       "",
        "patho_sirs":             [],
        "patho_blood_source":     "",
        "patho_wound_type":       "",
        "patho_result":           None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def run_dashboard() -> None:
    init_session_state()


    if not st.session_state.authenticated:
        email_input = show_login_page()
        if email_input:
            if check_subscription(email_input):
                st.session_state.authenticated = True
                st.session_state.last_activity = time.time()
                st.rerun()
        st.stop()

    handle_session_timeout()
    render_top_bar()

    startup_issues = get_startup_validation_issues()
    if startup_issues:
        with st.expander("🧪 Data validation at startup", expanded=False):
            st.warning(f"Found {len(startup_issues)} data issue(s).")
            for issue in startup_issues:
                st.write(f"- {issue}")

    st.title("🔬 Microbiology Clinical Decision Support System (CDSS)")
    st.caption("AI-Assisted Antibiotic & Resistance Decision Support — Egyptian Market Edition")

    # ── إعدادات المعمل ───────────────────────────────────────────────────
    with st.expander("🏥 إعدادات المعمل", expanded=False):
        lc1, lc2 = st.columns(2)
        with lc1:
            lab_name_input = st.text_input(
                "اسم المعمل / المستشفى",
                value=st.session_state.get("lab_name", "Orange Lab"),
                placeholder="مثال: Bustan Lab",
                key="lab_name_widget"
            )
            if lab_name_input.strip():
                st.session_state.lab_name = lab_name_input.strip()
        with lc2:
            lab_city_input = st.text_input(
                "المدينة / الجهة (اختياري)",
                value=st.session_state.get("lab_city", ""),
                placeholder="مثال: Cairo",
                key="lab_city_widget"
            )
            st.session_state.lab_city = lab_city_input.strip()
        preview_txt = f"🔬  {st.session_state.lab_name}"
        if st.session_state.lab_city:
            preview_txt += f"  |  {st.session_state.lab_city}"
        st.caption(f"معاينة الترويسة: **{preview_txt}**")

    uploaded = st.file_uploader("📷 Upload Culture Report Image", type=["jpg","jpeg","png"])

    if uploaded:
        file_bytes = uploaded.getvalue()
        file_hash  = make_file_hash(file_bytes)
        is_new     = (st.session_state.ocr_data is None or
                      st.session_state.last_file_hash != file_hash)

        if is_new:
            with st.spinner("🔍 جاري تحليل صورة التقرير..."):
                try:
                    payload = extract_all_data_cached(file_bytes)
                    st.session_state.ocr_data       = payload
                    st.session_state.last_file_hash = file_hash
                    st.session_state.sir_map_edited = dict(payload["sir_map"])
                except Exception as e:
                    st.error(f"تعذر تحليل الصورة: {e}")
                    st.stop()

        payload        = st.session_state.ocr_data
        patient        = payload["patient"]
        drugs_from_ocr = payload["drugs"]
        raw_text       = payload["raw_text"]

        if not st.session_state.sir_map_edited and payload["sir_map"]:
            st.session_state.sir_map_edited = dict(payload["sir_map"])

        st.image(file_bytes, caption="Preview", use_container_width=True)

        with st.expander("📝 النص المستخرج من التقرير (OCR)", expanded=False):
            st.text_area("Extracted Text", raw_text, height=220, label_visibility="collapsed")

        col1, col2 = st.columns([1.05, 1.55], gap="large")

        # ─── العمود الأيسر ───────────────────────────────────────────────
        with col1:
            st.subheader("👤 Patient & Culture")

            patient_name = st.text_input(
                "👤 اسم المريض / Patient Name",
                value=st.session_state.get("patient_name_final", ""),
                placeholder="أدخل اسم المريض",
                key=f"pname_{file_hash[:8]}"
            )
            st.session_state.patient_name_final = patient_name.strip()

            culture_type = st.selectbox(
                "🧫 Specimen",
                SPECIMEN_TYPES,
                index=best_default_index(SPECIMEN_TYPES, patient.get("Specimen"))
            )

            filtered_organisms = [
                org for org in SPECIMEN_ORGANISM_MAP.get(culture_type, BACTERIA_TYPES)
                if org in ORGANISM_PROFILE
            ]
            if not filtered_organisms:
                filtered_organisms = BACTERIA_TYPES

            organism_type = st.selectbox(
                "🦠 Organism",
                filtered_organisms,
                index=best_default_index(filtered_organisms, patient.get("Organism")),
                help=f"بكتيريا شائعة في عينة {culture_type}",
            )

            st.divider()
            st.subheader("🔬 Culture & Microscopic Details")

            colony_count = st.text_input(
                "Colony Count (CFU/mL)",
                value=st.session_state.colony_count,
                placeholder="≥ 10^5 CFU/mL",
                key="colony_count_input"
            )
            st.session_state.colony_count = colony_count

            date_in = st.date_input(
                "📅 Date In (تاريخ استلام العينة)",
                value=st.session_state.date_in,
                key="date_in_input"
            )
            st.session_state.date_in = date_in

            c_pus, c_rbc = st.columns(2)
            with c_pus:
                pus_cells_text = st.text_input(
                    "Pus Cells (/HPF)",
                    value=st.session_state.pus_cells_text,
                    placeholder="مثال: 4 - 6",
                    key="pus_cells_input"
                )
                st.session_state.pus_cells_text = pus_cells_text
            with c_rbc:
                rbcs_text = st.text_input(
                    "RBC Cells (/HPF)",
                    value=st.session_state.rbcs_text,
                    placeholder="مثال: 2 - 4",
                    key="rbcs_input"
                )
                st.session_state.rbcs_text = rbcs_text

            if organism_type in ORGANISM_PROFILE:
                op = ORGANISM_PROFILE[organism_type]
                with st.expander("📌 Organism Guidance", expanded=True):
                    st.info(op.get("note", ""))
                    spec_ctx = (op.get("specimen_context") or {}).get(culture_type, "")
                    if spec_ctx:
                        st.warning(f"**{culture_type} Context:** {spec_ctx}")
                    if op.get("first_line"):
                        st.write("**First-line:**", ", ".join(op["first_line"]))
                    if op.get("second_line"):
                        st.write("**Second-line:**", ", ".join(op["second_line"]))
                    if op.get("third_line"):
                        st.write("**Third-line:**", ", ".join(op["third_line"]))
                    if op.get("avoid"):
                        st.error("**Avoid:** " + ", ".join(op["avoid"]))
                    if culture_type == "Urine" and op.get("urine_note"):
                        st.info(f"📌 Urine notes:\n{op['urine_note']}")

            st.divider()
            age    = st.number_input("Age (years)", min_value=0, max_value=120,
                                      value=safe_int(patient.get("Age"), 25))
            default_sex = patient.get("Sex") if patient.get("Sex") in ["Female","Male"] else "Male"
            sex    = st.selectbox("Gender", ["Female","Male"],
                                  index=0 if default_sex == "Female" else 1)
            weight = st.number_input("Weight (kg)", min_value=5, max_value=300, value=70)

            st.divider()
            is_renal = st.checkbox("🚩 Renal Impairment")
            cl_cr    = 100.0
            if is_renal:
                s_cr  = st.number_input("Serum Creatinine (mg/dL)",
                                        min_value=0.1, max_value=20.0, value=1.0, step=0.1)
                cl_cr = calc_creatinine_clearance(age, weight, s_cr, sex)
                st.metric("CrCl (Cockcroft-Gault)", f"{cl_cr:.1f} ml/min",
                          delta=get_renal_severity(cl_cr),
                          delta_color="normal" if cl_cr >= 60 else ("off" if cl_cr >= 30 else "inverse"))

            is_hepatic = st.checkbox("🚩 Hepatic Impairment")
            is_preg    = False
            if sex == "Female" and 18 <= age <= 55:
                is_preg = st.checkbox("🤰 Patient is Pregnant")

            current_meds = st.multiselect("💊 Current Medications", COMMON_MEDS)

            # ── Pathogenicity Assessment Module v2 ───────────────────────────────
            st.divider()
            with st.expander("🧫 Pathogenicity Assessment", expanded=False):
                st.caption("هل العينة تمثل عدوى حقيقية أم تلوث؟ — يدعم Urine · Sputum · Blood · Wound · CSF")

                pa_col1, pa_col2 = st.columns(2)
                with pa_col1:
                    patho_purity = st.selectbox(
                        "نقاء المزرعة",
                        ["Pure growth", "Mixed growth"],
                        index=0 if st.session_state.patho_culture_purity == "Pure growth" else 1,
                        key="patho_purity_sel"
                    )
                    st.session_state.patho_culture_purity = patho_purity

                    patho_gram = st.selectbox(
                        "Gram Stain",
                        ["مش متعملة",
                         "WBCs + Gram Positive Cocci",
                         "WBCs + Gram Negative Rods",
                         "Organisms بدون WBCs",
                         "طبيعية (No organisms seen)"],
                        key="patho_gram_sel"
                    )
                    st.session_state.patho_gram_stain = patho_gram

                with pa_col2:
                    patho_urinalysis = st.selectbox(
                        "نتيجة Urinalysis (للبول فقط)",
                        ["مش معروف / مش مذكور", "Urinalysis طبيعي",
                         "Pyuria (WBCs > 5/HPF)", "Nitrites Positive", "Hematuria"],
                        key="patho_ua_sel"
                    )
                    st.session_state.patho_urinalysis = patho_urinalysis

                # ── Specimen-specific fields ──────────────────────────────────────
                spec_lower_ui = culture_type.lower()

                # Urine symptoms
                if "urine" in spec_lower_ui:
                    patho_symptoms = st.multiselect(
                        "الأعراض الكلينيكية",
                        ["Dysuria / Frequency / Urgency", "Fever (> 38°C)",
                         "Flank pain / Loin pain", "Nocturnal enuresis",
                         "Abdominal pain", "Nausea / Vomiting", "Asymptomatic"],
                        default=st.session_state.patho_symptoms,
                        key="patho_symp_urine"
                    )

                # Sputum — Murray-Washington fields
                elif "sputum" in spec_lower_ui or "respiratory" in spec_lower_ui:
                    st.markdown("**Murray-Washington Criteria**")
                    mw_c1, mw_c2 = st.columns(2)
                    with mw_c1:
                        patho_sputum_pus = st.text_input(
                            "WBC/LPF (Pus cells per low-power field)",
                            value=st.session_state.patho_sputum_pus,
                            placeholder="مثال: 30",
                            key="patho_mw_pus"
                        )
                        st.session_state.patho_sputum_pus = patho_sputum_pus
                    with mw_c2:
                        patho_sputum_epi = st.text_input(
                            "Epithelial cells/LPF",
                            value=st.session_state.patho_sputum_epi,
                            placeholder="مثال: 5",
                            key="patho_mw_epi"
                        )
                        st.session_state.patho_sputum_epi = patho_sputum_epi
                    st.caption("✅ Adequate: WBC ≥25 & Epi <10 | ❌ Reject: Epi ≥25")
                    patho_symptoms = st.multiselect(
                        "الأعراض التنفسية",
                        ["Productive cough / Purulent sputum", "Fever (> 38°C)",
                         "Dyspnea", "Pleuritic chest pain", "Asymptomatic"],
                        default=st.session_state.patho_symptoms,
                        key="patho_symp_sputum"
                    )

                # Blood — SIRS criteria
                elif "blood" in spec_lower_ui:
                    st.markdown("**SIRS Criteria** (اختر كل المعايير الموجودة)")
                    patho_sirs = st.multiselect(
                        "SIRS Criteria",
                        ["Fever > 38°C or Temp < 36°C",
                         "HR > 90 bpm",
                         "RR > 20 or PaCO₂ < 32",
                         "WBC > 12,000 or < 4,000 or >10% bands"],
                        default=st.session_state.patho_sirs,
                        key="patho_sirs_sel"
                    )
                    st.session_state.patho_sirs = patho_sirs
                    patho_blood_source = st.selectbox(
                        "Bottles / Source",
                        ["غير محدد", "Single bottle positive",
                         "Multiple bottles positive", "Source identified (CVC/wound)"],
                        key="patho_blood_src"
                    )
                    st.session_state.patho_blood_source = patho_blood_source
                    patho_symptoms = st.session_state.patho_symptoms

                # Wound / Swab
                elif any(w in spec_lower_ui for w in ["wound", "pus", "swab", "abscess"]):
                    patho_wound_type = st.selectbox(
                        "نوع الجرح",
                        ["غير محدد", "Surgical / Post-op wound",
                         "Chronic / Diabetic wound", "Traumatic wound",
                         "Superficial wound", "Deep tissue / Abscess"],
                        key="patho_wound_type_sel"
                    )
                    st.session_state.patho_wound_type = patho_wound_type
                    patho_symptoms = st.multiselect(
                        "علامات العدوى",
                        ["Erythema / Warmth / Swelling", "Purulent discharge",
                         "Fever (> 38°C)", "Pain / Tenderness", "Asymptomatic"],
                        default=st.session_state.patho_symptoms,
                        key="patho_symp_wound"
                    )
                else:
                    patho_symptoms = st.multiselect(
                        "الأعراض الكلينيكية",
                        ["Fever (> 38°C)", "Localized pain", "Asymptomatic"],
                        default=st.session_state.patho_symptoms,
                        key="patho_symp_other"
                    )

                st.session_state.patho_symptoms = patho_symptoms

                # Host factors (universal)
                patho_host = st.multiselect(
                    "عوامل المضيف",
                    ["Immunosuppressants / Steroids",
                     "Urinary catheter", "Central line / PICC",
                     "تاريخ UTIs متكررة", "Recurrent infections",
                     "Diabetes",
                     "Renal abnormality / Vesicoureteral reflux",
                     "Pregnant", "Pre-surgical"],
                    default=st.session_state.patho_host_factors,
                    key="patho_host_sel"
                )
                st.session_state.patho_host_factors = patho_host

                if st.button("🔬 احسب Pathogenicity Score", use_container_width=True, key="patho_calc_btn"):
                    # Build kwargs based on specimen
                    patho_kwargs = dict(
                        specimen=culture_type,
                        organism=organism_type,
                        colony_count_text=colony_count,
                        culture_purity=patho_purity,
                        symptoms=patho_symptoms,
                        pus_cells_text=pus_cells_text,
                        urinalysis_result=patho_urinalysis,
                        gram_stain=patho_gram,
                        age=age,
                        sex=sex,
                        host_factors=patho_host,
                    )
                    if "sputum" in spec_lower_ui or "respiratory" in spec_lower_ui:
                        patho_kwargs["sputum_pus_cells"]  = st.session_state.patho_sputum_pus
                        patho_kwargs["sputum_epithelial"] = st.session_state.patho_sputum_epi
                    if "blood" in spec_lower_ui:
                        patho_kwargs["sirs_criteria"]  = st.session_state.patho_sirs
                        patho_kwargs["blood_source"]   = st.session_state.patho_blood_source
                    if any(w in spec_lower_ui for w in ["wound","pus","swab","abscess"]):
                        patho_kwargs["wound_type"] = st.session_state.patho_wound_type

                    patho_result = assess_pathogenicity(**patho_kwargs)
                    st.session_state.patho_result = patho_result

                # ── Display Result (persists after button) ────────────────────
                patho_result = st.session_state.get("patho_result")
                if patho_result:
                    sc    = patho_result["score"]
                    color = patho_result["color"]
                    flags = patho_result.get("special_flags", [])

                    st.markdown(f"### Pathogenicity Score: **{sc}%**")
                    st.progress(sc / 100)

                    if color == "error":
                        st.error(patho_result["verdict"])
                    elif color == "warning":
                        st.warning(patho_result["verdict"])
                    else:
                        st.success(patho_result["verdict"])

                    # ABU badge
                    if patho_result.get("abu_detected"):
                        st.info("🔵 **Asymptomatic Bacteriuria (ABU) Detected** — راجع IDSA 2019")

                    # Murray-Washington badge
                    if "MW_REJECT" in flags:
                        st.error("🧫 **Murray-Washington: Specimen REJECTED** — إعادة أخذ العينة ضرورية")
                    elif "MW_ADEQUATE" in flags:
                        st.success("🧫 **Murray-Washington: Adequate Sputum** ✅")
                    elif "MW_MIXED" in flags:
                        st.warning("🧫 **Murray-Washington: Mixed Quality** — تحليل بتحفظ")

                    # SIRS badge
                    if "SIRS_HIGH" in flags:
                        st.error("🩸 **SIRS ≥3 criteria** — Sepsis Probable")
                    elif "SIRS_MET" in flags:
                        st.warning("🩸 **SIRS 2 criteria** — Bacteremia Possible")

                    # Pediatric badge
                    if "PEDIATRIC_UTI" in flags:
                        st.info("👶 **Pediatric threshold applied** (Age < 2 yrs — any growth significant)")

                    st.info(patho_result["interpretation"])

                    col_pos, col_neg = st.columns(2)
                    with col_pos:
                        if patho_result["factors_pos"]:
                            st.markdown("**✅ Supporting Factors**")
                            for f in patho_result["factors_pos"]:
                                st.write(f)
                    with col_neg:
                        if patho_result["factors_neg"]:
                            st.markdown("**⚠️ Against Infection**")
                            for f in patho_result["factors_neg"]:
                                st.write(f)

                    st.markdown("**📋 التوصيات:**")
                    for rec in patho_result["recommendations"]:
                        st.write(f"• {rec}")


        # ─── العمود الأيمن ───────────────────────────────────────────────
        with col2:
            st.subheader("💊 Antibiotic Analysis")

            # ══════════════════════════════════════════════════════
            # AST Input Panel — OCR + Manual موحّد
            # ══════════════════════════════════════════════════════
            ocr_sir_map  = payload["sir_map"]
            sir_options  = ["S", "I", "R"]
            label_icons  = {"S":"🟢","I":"🟡","R":"🔴"}

            st.markdown("**📊 نتائج المزرعة — S / I / R**")
            st.caption("✅ من OCR تلقائياً — عدّل أي قيمة أو أضف مضاد فاته الـ OCR")

            ocr_drugs    = list(ocr_sir_map.keys())
            manual_prev  = [d for d in st.session_state.sir_map_edited.keys()
                            if d not in ocr_drugs]
            manual_extra = st.multiselect(
                "➕ أضف مضادات فاتها OCR",
                options=[d for d in sorted(ABX_GUIDELINES.keys()) if d not in ocr_drugs],
                default=manual_prev,
                key=f"manual_drugs_{file_hash[:8]}",
            )
            edited_sir: Dict[str, str] = {}

            if ocr_drugs:
                st.markdown("<small style='color:#555'>🔍 من OCR:</small>", unsafe_allow_html=True)
                for i in range(0, len(ocr_drugs), 3):
                    row_drugs = ocr_drugs[i: i+3]
                    cols = st.columns(3)
                    for col_w, drug in zip(cols, row_drugs):
                        cur = st.session_state.sir_map_edited.get(drug, ocr_sir_map[drug])
                        if cur not in sir_options: cur = "S"
                        val = col_w.selectbox(
                            f"{label_icons.get(cur,'')} {drug}",
                            options=sir_options, index=sir_options.index(cur),
                            key=f"sir_{drug}_{file_hash[:8]}"
                        )
                        edited_sir[drug] = val

            manual_new = [d for d in manual_extra if d not in ocr_drugs]
            if manual_new:
                st.markdown("<small style='color:#1a6b3a'>➕ مُضافة يدوياً:</small>", unsafe_allow_html=True)
                for i in range(0, len(manual_new), 3):
                    row_drugs = manual_new[i: i+3]
                    cols = st.columns(3)
                    for col_w, drug in zip(cols, row_drugs):
                        cur = st.session_state.sir_map_edited.get(drug, "S")
                        if cur not in sir_options: cur = "S"
                        val = col_w.selectbox(
                            f"{label_icons.get(cur,'')} {drug}",
                            options=sir_options, index=sir_options.index(cur),
                            key=f"sir_m_{drug}_{file_hash[:8]}"
                        )
                        edited_sir[drug] = val

            st.session_state.sir_map_edited = edited_sir
            sir_map     = dict(edited_sir)
            final_drugs = list(sir_map.keys())

            if sir_map:
                s_n = sum(1 for v in sir_map.values() if v=="S")
                i_n = sum(1 for v in sir_map.values() if v=="I")
                r_n = sum(1 for v in sir_map.values() if v=="R")
                st.caption(f"📊 {len(sir_map)} مضاد | 🟢 S:{s_n} | 🟡 I:{i_n} | 🔴 R:{r_n}")

            allowed, warned, banned, preg_warn_items, interactions_alerts = analyze_antibiotics(
                final_drugs=final_drugs,
                organism_type=organism_type,
                culture_type=culture_type,
                age=age, sex=sex,
                is_renal=is_renal, cl_cr=cl_cr,
                is_preg=is_preg, is_hepatic=is_hepatic,
                current_meds=current_meds,
                sir_map=sir_map,
            )

            if interactions_alerts:
                st.warning("⚡ Interactions / Hepatic Warnings")
                for alert in interactions_alerts:
                    st.write(alert)

            mdr_result  = classify_mdr(organism_type, sir_map)
            esbl_result = predict_esbl(organism_type, sir_map)
            phenotypes  = detect_resistance_phenotypes(organism_type, sir_map)

            # ── Resistance Classification (MDR/XDR/PDR + ESBL) ───────────────
            if mdr_result["level"] or (esbl_result.get("probability") and
                                        esbl_result["probability"] not in ("low", None)):
                with st.expander("🧬 Resistance Classification", expanded=True):
                    if mdr_result["level"]:
                        info = MDR_INFO[mdr_result["level"]]
                        _rc   = mdr_result["resistant_count"]
                        _rt   = mdr_result["total_tested"]
                        _cats = ", ".join(mdr_result["resistant_categories"])
                        _msg  = (f"{info['icon']} **{info['label']}**  \n"
                                 f"{info['detail']}  \n"
                                 f"Resistant categories ({_rc}/{_rt}): {_cats}  \n"
                                 f"🔹 {info['action']}")
                        if mdr_result["level"] == "MDR":
                            st.warning(_msg)
                        else:
                            st.error(_msg)

                    prob = esbl_result.get("probability")
                    if prob == "carbapenemase":
                        st.error(
                            "**🚨 Possible Carbapenemase (KPC/MBL/OXA)**\n" +
                            esbl_result["detail"] + "  \n🔹 " + esbl_result["action"]
                        )
                    elif prob == "high":
                        st.error(
                            "**⚠️ High Probability ESBL Producer**\n" +
                            esbl_result["detail"] + "  \n🔹 " + esbl_result["action"]
                        )
                    elif prob == "moderate":
                        st.warning(
                            "**🔶 ESBL Confirmation Recommended**\n" +
                            esbl_result["detail"] + "  \n🔹 " + esbl_result["action"]
                        )

            # ── Resistance Phenotype Engine ───────────────────────────────────
            if phenotypes:
                with st.expander("🦠 Resistance Phenotypes Detected", expanded=True):
                    for ph in phenotypes:
                        iso = "  🚨 **عزل فوري مطلوب**" if ph["isolation"] else ""
                        msg = (f"{ph['icon']} **{ph['label']}**{iso}\n"
                               f"{ph['detail']}\n🔹 {ph['action']}")
                        (st.error if ph["isolation"] else st.warning)(msg)
                        if ph.get("matched_markers"):
                            st.caption(f"Evidence: {', '.join(ph['matched_markers'])}")

            # ── AST Quality Control ───────────────────────────────────────────
            if sir_map:
                qc_issues = run_ast_qc(organism_type, sir_map)
                if qc_issues:
                    with st.expander(f"🔬 AST Quality Control — {len(qc_issues)} Issue(s)", expanded=True):
                        st.caption("تحقق تلقائي من منطقية نتائج المزرعة — EUCAST Expert Rules")
                        for iss in qc_issues:
                            fn = st.error if iss["severity"] == "error" else st.warning
                            icon = "❌" if iss["severity"] == "error" else "⚠️"
                            fn(f"{icon} **[{iss['id']}]** {iss['message']}\n✏️ {iss['fix']}")

            # ── Smart Antibiotic Ranking ──────────────────────────────────────
            if allowed:
                ranked = rank_sensitive_antibiotics(
                    allowed, culture_type, organism_type, sir_map, phenotypes
                )
                with st.expander("🏆 Smart Antibiotic Ranking", expanded=False):
                    st.caption("مرتب حسب: نتيجة المزرعة + WHO AWaRe + Route + ملاءمة العينة")
                    for i, item in enumerate(ranked[:8], 1):
                        sir_b  = item.get("_sir", "—")
                        aware  = item.get("aware", "")
                        route  = "💊 Oral" if item.get("high_po") else "💉 IV/IM"
                        score  = item.get("_score", 0)
                        a_icon = {"Access": "🟢", "Watch": "🟡", "Reserve": "🔴"}.get(aware, "⚪")
                        st.markdown(
                            f"**{i}.** {item['name']} &nbsp; `{sir_b}` &nbsp; "
                            f"{a_icon} {aware} &nbsp; {route} &nbsp;"
                            f"<small style='color:gray'>score:{score}</small>",
                            unsafe_allow_html=True
                        )

            # ── Infection Syndrome Module ─────────────────────────────────────
            syn = get_infection_syndrome(culture_type, organism_type, age, is_preg)
            if syn:
                with st.expander(f"🏥 Infection Syndrome: {syn['syndrome']}", expanded=False):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"**النوع:** {syn['sub_type']}")
                        st.markdown(f"**مدة العلاج:** {syn['duration']}")
                        st.markdown(f"**الخط الأول:** {', '.join(syn['first_choice'])}")
                    with c2:
                        st.info(f"**Escalation:** {syn['escalation']}")
                        st.caption(f"📌 Culture threshold: {syn['threshold']}")

            if is_preg and preg_warn_items:
                st.markdown("---")
                st.markdown("### 🤰 Pregnancy — Use With Caution")
                st.info(
                    "الأدوية التالية **ليست محظورة تلقائيًا** لكنها تحتاج تقييمًا طبيًا دقيقًا.\n\n"
                    "**القرار النهائي للطبيب المعالج حصراً.**"
                )
                for item in preg_warn_items:
                    with st.expander(f"⚠️ {item['name']} — تفاصيل التحذير"):
                        for line in (item.get("preg_note") or "").splitlines():
                            st.write(line)

            if banned:
                with st.expander("🚫 Contraindicated / Ineffective", expanded=True):
                    cat_labels = {
                        "resistant": "مقاوم في المزرعة",
                        "renal":     "قصور كلوي",
                        "pregnancy": "ممنوع في الحمل",
                        "child":     "غير مناسب للعمر",
                        "organism":  "غير فعال للجرثومة",
                        "other":     "موانع أخرى",
                    }
                    for item in banned:
                        st.error(
                            f"💊 {item['name']}  [{cat_labels.get(item['category'],'')}]\n"
                            f"{item['reason_short']}"
                        )

            if warned:
                with st.expander("🟡 Warnings / Dose Adjustment Required", expanded=True):
                    for item in warned:
                        sir_tag = (f" [{sir_map[item['name']]}]"
                                   if sir_map and item['name'] in sir_map else "")
                        if item.get("warning_reason") == "intermediate_culture":
                            st.warning(
                                f"**{item['name']}{sir_tag}** — Intermediate (I) on culture, "
                                "use only after clinical review."
                            )
                        else:
                            st.warning(f"**{item['name']}{sir_tag}** — {item.get('renal_note','')}")

            if allowed:
                st.success(f"🟢 {len(allowed)} Recommended Option(s)")
                for item in allowed:
                    sir_badge = (f" [{sir_map[item['name']]}]"
                                 if sir_map and item['name'] in sir_map else "")
                    preg_flag = " 🤰" if (is_preg and item.get("preg_status") == "Warn") else ""
                    aware_val = item.get("aware", "Unknown")
                    color_val = AWARE_COLORS.get(aware_val, aware_val)
                    with st.expander(
                        f"{item['name']}{sir_badge}{preg_flag} — {color_val}", expanded=False
                    ):
                        c1, c2 = st.columns(2)
                        c1.write(f"**Class:** {item.get('class','-')}")
                        c2.write(f"**Route:** {get_route_label(item)}")
                        st.write(f"**Note:** {item.get('note','-')}")
                        spec_note = (item.get("specimen_notes") or {}).get(culture_type, "")
                        if spec_note:
                            st.info(f"**{culture_type} Note:** {spec_note}")
                        if is_renal:
                            st.caption(f"Renal: {item.get('renal_note','-')}")
                        if is_preg and item.get("preg_status") == "Warn":
                            pn = (item.get("preg_note") or "").splitlines()
                            if pn:
                                st.caption(f"🤰 {pn[0]}")
            elif not banned and not warned:
                st.info("اختر المضادات الحساسة أو المناسبة من القائمة أعلاه.")

            # ── التقارير والصورة ─────────────────────────────────────────
            if final_drugs:
                st.divider()

                _lab  = st.session_state.get("lab_name", "Orange Lab")
                _city = st.session_state.get("lab_city", "")
                _pt   = patient_name.strip() or "غير محدد"

                reserve_names = uniq_keep_order([
                    item['name'] for item in (allowed + warned)
                    if item.get("aware") == "Reserve"
                ])
                AWARE_ORDER = {"Access": 0, "Watch": 1, "Reserve": 2, None: 3}
                preferred_sorted = sorted(
                    [item for item in allowed if item.get("aware") != "Reserve"],
                    key=lambda x: AWARE_ORDER.get(x.get("aware"), 3)
                )
                # بدون badge — اللون بيتحدد داخل section_box عن طريق [A]/[W]
                preferred_with_badge = [
                    (f"{item['name']} [A]" if item.get("aware")=="Access" else
                     f"{item['name']} [W]" if item.get("aware")=="Watch" else
                     item['name'])
                    for item in preferred_sorted
                ]
                preg_caution_names = [item['name'] for item in preg_warn_items]
                use_caution_names  = uniq_keep_order(
                    [item['name'] for item in warned if item['name'] not in reserve_names]
                    + preg_caution_names
                )
                banned_names   = uniq_keep_order([item['name'] for item in banned])
                org_profile    = ORGANISM_PROFILE.get(organism_type, {})
                first_line_l   = org_profile.get("first_line", [])

                notes: List[str] = []
                if is_renal:
                    notes.append(f"Renal impairment: CrCl {cl_cr:.1f} ml/min — dose adjustment required.")
                if is_preg:
                    notes.append("Pregnancy: use with caution; consult specialist.")
                if age < 18:
                    notes.append("Pediatric age: verify age-specific suitability.")
                if banned:
                    notes.append(f"{len(banned)} contraindicated / ineffective antibiotics.")
                if warned:
                    notes.append(f"{len(warned)} antibiotics need caution or dose adjustment.")
                notes.append("Treatment guided by severity and local resistance patterns.")
                notes.append("De-escalate based on culture & sensitivity.")

                # ── مفتاح تجديد شامل يتغير مع أي معطى ──────────────────
                import hashlib as _hl
                _refresh_key = _hl.md5(
                    f"{organism_type}|{culture_type}|{age}|{sex}|{weight}|"
                    f"{is_renal}|{cl_cr:.1f}|{is_preg}|{is_hepatic}|"
                    f"{sorted(sir_map.items())}|{sorted(final_drugs)}|"
                    f"{_pt}|{colony_count}|{str(date_in)}|{pus_cells_text}|{rbcs_text}|"
                    f"{_lab}|{_city}".encode()
                ).hexdigest()[:12]

                # ── Commercial Names Toggle ────────────────────────────────
                show_commercial = st.checkbox(
                    "📋 إضافة الأسماء التجارية (Commercial Names) في التقرير؟",
                    value=st.session_state.get("show_commercial_names", False),
                    key="show_commercial_chk",
                    help="يضيف أسماء العلامات التجارية بجانب كل مضاد حيوي في ملف TXT فقط"
                )
                st.session_state.show_commercial_names = show_commercial
                if show_commercial and not COMMERCIAL_NAMES:
                    st.warning("⚠️ ملف `commercial_names.txt` غير موجود في مجلد البرنامج.")
                elif show_commercial:
                    st.caption(f"✅ {len(COMMERCIAL_NAMES)} دواء مسجّل في قاموس الأسماء التجارية")

                # ── التقرير النصي ─────────────────────────────────────────
                st.markdown("### 📋 التقرير السريري")
                auto_report = generate_report(
                    patient_name=_pt,
                    age=age, sex=sex, weight=weight,
                    cl_cr=cl_cr, is_renal=is_renal,
                    is_preg=is_preg, is_hepatic=is_hepatic,
                    allowed=allowed, warned=warned, banned=banned,
                    preg_warn_items=preg_warn_items,
                    organism=organism_type, specimen=culture_type,
                    interactions=interactions_alerts, sir_map=sir_map,
                    colony_count=colony_count,
                    date_in=str(date_in),
                    pus_cells=pus_cells_text,
                    rbcs=rbcs_text,
                    lab_name=_lab,
                    lab_city=_city,
                    patho_assessment=st.session_state.get("patho_result"),
                    show_commercial_names=show_commercial,
                )
                st.text_area(
                    "نص التقرير",
                    value=auto_report,
                    height=380,
                    disabled=True,
                    label_visibility="collapsed",
                    key=f"rpt_{_refresh_key}"
                )
                st.download_button(
                    "📥 تنزيل التقرير (TXT)",
                    data=auto_report,
                    file_name=(f"Orange_{organism_type.replace(' ','_')}_"
                               f"{_pt.replace(' ','_')[:15]}_"
                               f"{datetime.now().strftime('%Y%m%d_%H%M')}.txt"),
                    mime="text/plain",
                    use_container_width=True,
                    type="primary",
                    key=f"dl_txt_{_refresh_key}",
                )

                # ── صورة الملخص ───────────────────────────────────────────
                st.divider()
                st.markdown(
                    f"### 🖼️ صورة ملخص الحالة — "
                    f"**{_lab}**{'  |  ' + _city if _city else ''}"
                )
                if PIL_AVAILABLE:
                    try:
                        img_bytes = generate_decision_tree_image(
                            patient_name=_pt,
                            age=age, sex=sex, weight=weight,
                            cl_cr=cl_cr, is_renal=is_renal, is_preg=is_preg,
                            organism=organism_type, specimen=culture_type,
                            first_line=first_line_l,
                            preferred=preferred_with_badge,
                            use_caution=use_caution_names,
                            contraindicated=banned_names,
                            reserve=reserve_names,
                            notes=notes,
                            colony_count=colony_count,
                            date_in=str(date_in),
                            pus_cells=pus_cells_text,
                            rbcs=rbcs_text,
                            lab_name=_lab,
                            lab_city=_city,
                            mdr_result=mdr_result,
                            esbl_result=esbl_result,
                            phenotypes=phenotypes if "phenotypes" in dir() else [],
                        )
                        st.image(
                            img_bytes,
                            caption=(f"{_lab}{' | ' + _city if _city else ''}"
                                     f"  —  {_pt}  |  {str(date_in)}"),
                            use_container_width=True,
                        )
                        dl_img, pr_img = st.columns(2)
                        with dl_img:
                            st.download_button(
                                "📥 تنزيل الصورة (PNG)",
                                data=img_bytes,
                                file_name=(f"Orange_{organism_type.replace(' ','_')}_"
                                           f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"),
                                mime="image/png",
                                use_container_width=True,
                                key=f"dl_img_{_refresh_key}",
                            )
                        with pr_img:
                            # تنزيل نسخة عالية الجودة للطباعة
                            st.download_button(
                                "🖨️ تنزيل للطباعة (HD)",
                                data=img_bytes,
                                file_name=(f"Orange_Print_{organism_type.replace(' ','_')}_"
                                           f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"),
                                mime="image/png",
                                use_container_width=True,
                                key=f"dl_print_{_refresh_key}",
                            )
                            st.caption("افتح الصورة بعد التنزيل → Ctrl+P للطباعة")
                    except Exception as e:
                        st.error(f"فشل توليد الصورة: {e}")
                else:
                    st.warning("⚠️ أضف `Pillow` لـ requirements.txt لتفعيل صورة الملخص.")

    st.divider()
    st.markdown("""
    <div style="text-align:center;color:gray;font-size:0.9rem;">
      <strong>Developed by Dr / Hussein Ali | Orange Lab — Microbiology CDSS</strong><br>
      EUCAST 2026 | CLSI M100 2026 | IDSA AMR 2025 | BNF 2025 | Egypt National Guidelines
    </div>
    """, unsafe_allow_html=True)
