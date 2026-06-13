# © 2025 Dr. Hussein Ali — Orange Lab, 6 October City, Egypt
# Orange Culture Tool — All Rights Reserved
# Unauthorized copying or distribution is prohibited.
import streamlit as st

st.set_page_config(page_title="Orange Culture Tool",
                   layout="wide", page_icon="🛡️")

st.markdown("""
    <style>
    .stActionButton {display: none !important;}
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    header[data-testid="stHeader"] {display: none !important;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 🔐 نظام الاشتراك
# ==========================================
import json
from datetime import datetime
import time  # for session timeout

try:
    raw = st.secrets.get("subscribers_json") or st.secrets.get("subscribers", "{}")
    SUBSCRIBERS = json.loads(raw) if isinstance(raw, str) else dict(raw)
except Exception:
    SUBSCRIBERS = {}

# Session timeout in seconds (30 minutes)
SESSION_TIMEOUT = 30 * 60

def show_login_page():
    # Check if we came from a session timeout
    if st.session_state.get("logout_reason"):
        st.warning(st.session_state.pop("logout_reason"))
    st.markdown("""
    <div style='text-align:center; padding: 3rem 0 1rem 0'>
        <span style='font-size:3rem'>🍊</span>
        <h2 style='margin:0.3rem 0 0.1rem 0'>Orange Culture Tool</h2>
        <p style='color:gray; margin:0'>AI-Assisted Antibiotic Decision Support — Egyptian Market</p>
    </div>
    """, unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("#### 🔐 تسجيل الدخول")
        email = st.text_input("📧 البريد الإلكتروني", placeholder="example@hospital.com",
                              label_visibility="collapsed")
        login_btn = st.button("دخول", use_container_width=True, type="primary")
        if login_btn:
            return email.strip().lower()
        st.markdown("---")
        st.markdown("""
        <div style='text-align:center; font-size:0.85rem; color:gray'>
        للحصول على نسخة تجريبية أو اشتراك:<br>
        📞 01016872801 &nbsp;|&nbsp; ✉️ Hussein.ali77121@gmail.com<br><br>
        🔹 تجريبي مجاني: <b>15 يوم</b><br>
        🔹 شهري: <b>200 جنيه</b><br>
        🔹 سنوي: <b>2000 جنيه</b> <span style='color:green'>(توفير 400 ج)</span>
        </div>
        """, unsafe_allow_html=True)
    return None

def check_subscription(email):
    if not email or "@" not in email:
        st.warning("⚠️ أدخل بريداً إلكترونياً صحيحاً")
        return False
    if email not in SUBSCRIBERS:
        st.error("❌ هذا البريد غير مسجل في النظام")
        st.info(
            "**للحصول على نسخة تجريبية مجانية (15 يوم) أو اشتراك:**\n\n"
            "📞 01016872801\n\n✉️ Hussein.ali77121@gmail.com\n\n---\n"
            "🔹 تجريبي: **مجاناً - 15 يوم**  \n"
            "🔹 شهري: **200 جنيه**  \n"
            "🔹 سنوي: **2000 جنيه** *(توفير 400 ج)*"
        )
        return False
    expiry_str = SUBSCRIBERS[email]
    try:
        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    except ValueError:
        st.error("خطأ في بيانات الاشتراك، تواصل مع الدعم")
        return False
    today = datetime.now().date()
    days_left = (expiry_date - today).days
    # Store email and days in session for later banner use
    st.session_state.email = email
    st.session_state.days_left = days_left

    if days_left < 0:
        st.error(f"⏳ انتهى اشتراكك منذ {abs(days_left)} يوم")
        st.info("📞 للتجديد: 01016872801 | ✉️ Hussein.ali77121@gmail.com")
        return False
    if days_left <= 3:
        st.warning(f"⚠️ اشتراكك ينتهي خلال **{days_left} يوم فقط!** تواصل للتجديد.")
    elif days_left <= 7:
        st.info(f"ℹ️ متبقي **{days_left} أيام** على انتهاء اشتراكك.")
    else:
        st.success(f"✅ أهلاً بك! الاشتراك ساري — متبقي {days_left} يوماً")
    return True

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    email_input = show_login_page()
    if email_input:
        if check_subscription(email_input):
            st.session_state.authenticated = True
            st.rerun()
    st.stop()

# ══════════════════════════════════════════════════════════════════════
# ✅ Session timeout check & subscription banner (top of main app)
# ══════════════════════════════════════════════════════════════════════

# Check inactivity timeout
if "last_activity" in st.session_state:
    elapsed = time.time() - st.session_state.last_activity
    if elapsed > SESSION_TIMEOUT:
        # Logout due to inactivity
        st.session_state.clear()
        st.session_state.logout_reason = "انتهت صلاحية الجلسة بسبب عدم النشاط. الرجاء تسجيل الدخول مرة أخرى."
        st.rerun()
# Update last activity timestamp
st.session_state.last_activity = time.time()

# Display subscription status banner
days = st.session_state.get("days_left", None)
email = st.session_state.get("email", "")
if days is not None:
    if days <= 3:
        st.warning(f"⚠️ اشتراك **{email}** سينتهي خلال **{days} يوم(أيام)** — يُرجى التجديد قريباً.")
    else:
        st.info(f"✅ اشتراك **{email}** سارٍ — متبقي **{days}** يوماً.")

# ══════════════════════════════════════════════════════════════════════
# ✅ التطبيق الأساسي
# ══════════════════════════════════════════════════════════════════════
import numpy as np
import cv2
import pytesseract
import re
from difflib import SequenceMatcher

# ==========================================
# 📋 Antibiotics Database – Egyptian Market
# ==========================================
# (Database content remains unchanged)
ABX_GUIDELINES = {
    # ── Beta-lactam / Penicillins ──────────────────────────────────────
    "Amoxicillin + Clavulanic acid": {
        "priority": 1, "class": "Beta-lactamase Inhibitor Combination",
        "note": "✅ خيار قياسي للعدوى البسيطة والمتوسطة (مثل Augmentin/Curam). Bioavailability فموي ~90%.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب عند CrCl < 30.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["augmentin","curam","amoxiclav","co-amoxiclav"],
        "organisms": ["E. coli","Klebsiella spp.","Staphylococcus aureus",
                      "Proteus mirabilis","Streptococcus pneumoniae","H. influenzae"],
        "specimen_notes": {
            "Blood":      "✅ فعال في bacteremia الموجبات والسالبات البسيطة.",
            "Sputum":     "✅ خيار أول لـ CAP وexacerbation COPD.",
            "Wound Swab": "✅ فعال للعدوى الجلدية المختلطة.",
            "Pus":        "✅ جيد للخراجات والعدوى المختلطة.",
            "Urine":      "✅ خيار أول للمسالك غير المعقدة.",
        },
    },
    "Ampicillin/Sulbactam": {
        "priority": 2, "class": "Penicillin + Beta-lactamase Inhibitor (IV)",
        "note": "💉 IV فقط. فعال للموجبات والسالبات. أساس علاج Acinetobacter بجرعات عالية (IDSA AMR 2025).",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["unictam","sigmaclav","unasyn"],
        "organisms": ["E. coli","Klebsiella spp.","Staphylococcus aureus",
                      "Proteus mirabilis","Enterococcus faecalis","Acinetobacter baumannii"],
        "specimen_notes": {
            "Blood":      "💉 فعال في bacteremia المختلطة.",
            "Sputum":     "💉 HAP/VAP خصوصاً Acinetobacter بجرعات عالية.",
            "Wound Swab": "💉 العدوى الجراحية والمختلطة.",
            "Pus":        "💉 الخراجات داخل البطن.",
        },
    },
    "Piperacillin + Tazobactam": {
        "priority": 4, "class": "Anti-pseudomonal Penicillin + Inhibitor (IV)",
        "note": "🛑 (مثل Tazocin) IV فقط. واسع الطيف جداً — يُحفظ للحالات الشديدة (IDSA AMR 2025).",
        "renal_limit": 20, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["tazocin","pip-tazo","piptaz"],
        "organisms": ["Pseudomonas aeruginosa","E. coli","Klebsiella spp.",
                      "Enterococcus faecalis","Proteus mirabilis","Acinetobacter baumannii"],
        "specimen_notes": {
            "Blood":      "🛑 sepsis شديد مع اشتباه Pseudomonas.",
            "Sputum":     "🛑 VAP/HAP مع اشتباه Pseudomonas.",
            "Wound Swab": "🛑 العدوى الجراحية الشديدة.",
            "Pus":        "🛑 الخراجات داخل البطن الشديدة.",
        },
    },
    # ── Cephalosporins ─────────────────────────────────────────────────
    "Cephalexin": {
        "priority": 1, "class": "1st Gen Cephalosporin (Oral)",
        "note": "✅ (مثل Ceporex) Oral. Bioavailability ~90%. آمن للالتهابات البسيطة والجلد.",
        "renal_limit": 40, "renal_note": "⚖️ مباعدة الجرعات مطلوب.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["ceporex","keflex"],
        "organisms": ["Staphylococcus aureus","Streptococcus pneumoniae","E. coli","Proteus mirabilis"],
        "specimen_notes": {
            "Wound Swab": "✅ خيار ممتاز للعدوى الجلدية البسيطة (cellulitis/impetigo).",
            "Urine":      "✅ مناسب للمسالك البسيطة.",
        },
    },
    "Cefadroxil": {
        "priority": 1, "class": "1st Gen Cephalosporin (Oral)",
        "note": "✅ (مثل Duricef) Oral. Bioavailability ~90%. فعال لالتهابات الحلق والجلد.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["duricef"],
        "organisms": ["Staphylococcus aureus","Streptococcus pneumoniae"],
        "specimen_notes": {
            "Wound Swab": "✅ جيد للعدوى الجلدية والأنسجة الرخوة.",
            "Sputum":     "✅ التهاب الحلق البكتيري (Strep pharyngitis).",
        },
    },
    "Cefaclor": {
        "priority": 2, "class": "2nd Gen Cephalosporin (Oral)",
        "note": "✅ (مثل Ceclor) Oral. Bioavailability ~95%. فعال للأذن الوسطى والمسالك.",
        "renal_limit": 10, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["ceclor"],
        "organisms": ["E. coli","H. influenzae","Staphylococcus aureus",
                      "Streptococcus pneumoniae","Klebsiella spp."],
        "specimen_notes": {
            "Sputum": "✅ التهابات الجهاز التنفسي العلوي والأذن الوسطى.",
            "Urine":  "✅ مناسب للمسالك البولية البسيطة.",
        },
    },
    "Cefuroxime": {
        "priority": 2, "class": "2nd Gen Cephalosporin (Oral)",
        "note": "✅ (مثل Zinnat) Oral. Bioavailability ~52%. واسع المدى للجهاز التنفسي والمسالك.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["zinnat","ceftin"],
        "organisms": ["E. coli","Klebsiella spp.","H. influenzae",
                      "Staphylococcus aureus","Streptococcus pneumoniae","Proteus mirabilis"],
        "specimen_notes": {
            "Sputum":     "✅ CAP وعدوى الجهاز التنفسي.",
            "Wound Swab": "✅ عدوى الأنسجة الرخوة المتوسطة.",
            "Urine":      "✅ مناسب للمسالك.",
            "Blood":      "⚠️ لا يُفضل في bacteremia الشديدة — استبدل بـ Zinacef IV.",
        },
    },
    "Cefuroxime sodium": {
        "priority": 2, "class": "2nd Gen Cephalosporin (IV)",
        "note": "💉 (مثل Zinacef) IV فقط — نفس Cefuroxime لكن للحالات التي تحتاج حقن.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["zinacef","cefuroxime iv","cefuroxime sodium"],
        "organisms": ["E. coli","Klebsiella spp.","H. influenzae",
                      "Staphylococcus aureus","Streptococcus pneumoniae","Proteus mirabilis"],
        "specimen_notes": {
            "Blood":      "💉 bacteremia المتوسطة الشدة.",
            "Sputum":     "💉 CAP الذي يحتاج دخول مستشفى.",
            "Wound Swab": "💉 العدوى الجراحية المتوسطة.",
            "Urine":      "💉 pyelonephritis يحتاج IV.",
        },
    },
    "Ceftriaxone": {
        "priority": 3, "class": "3rd Gen Cephalosporin (IV/IM)",
        "note": "⚠️ (مثل Rocephin) IV/IM فقط — bioavailability فموي = صفر. لا يُستخدم في الحالات البسيطة.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً — يُطرح كبدياً أساساً.",
        "hepatic_caution": True, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["rocephin","cefaxone","triaxone"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis","Staphylococcus aureus",
                      "Streptococcus pneumoniae","H. influenzae",
                      "Salmonella spp.","Shigella spp."],
        "specimen_notes": {
            "Blood":      "💉 خيار ممتاز في bacteremia والـ sepsis.",
            "CSF":        "💉 خيار أول في meningitis البكتيري.",
            "Sputum":     "💉 CAP الشديد الذي يحتاج دخول مستشفى.",
            "Urine":      "⚠️ يُحفظ للـ pyelonephritis الشديد فقط.",
            "Stool":      "💉 Typhoid fever والحالات الشديدة من Salmonella/Shigella.",
        },
    },
    "Cefixime": {
        "priority": 2, "class": "3rd Gen Cephalosporin (Oral)",
        "note": "✅ (مثل Suprax) Oral. Bioavailability ~40-50%. خيار فموي قوي للمسالك.",
        "renal_limit": 20, "renal_note": "⚖️ خفض الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["suprax","oroken"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "H. influenzae","Streptococcus pneumoniae","Salmonella spp."],
        "specimen_notes": {
            "Urine":  "✅ خيار فموي قوي للمسالك والـ pyelonephritis الخفيف.",
            "Sputum": "✅ عدوى الجهاز التنفسي الخفيفة.",
            "Stool":  "✅ Step-down بعد Ceftriaxone في Salmonella.",
        },
    },
    "Cefotaxime": {
        "priority": 3, "class": "3rd Gen Cephalosporin (IV)",
        "note": "💉 (مثل Cefotax) IV فقط — bioavailability فموي = صفر. يستخدم في العدوى الشديدة.",
        "renal_limit": 20, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["cefotax","claforan"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "Streptococcus pneumoniae","H. influenzae"],
        "specimen_notes": {
            "Blood":  "💉 bacteremia والـ sepsis.",
            "CSF":    "💉 meningitis — بديل Ceftriaxone.",
            "Sputum": "💉 CAP الشديد.",
        },
    },
    "Ceftazidime": {
        "priority": 4, "class": "3rd Gen Cephalosporin Anti-pseudomonal (IV)",
        "note": "🛑 (مثل Fortum) IV فقط — متخصص في Pseudomonas. Bioavailability فموي = صفر.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري جداً.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["fortum","ceptaz"],
        "organisms": ["Pseudomonas aeruginosa","E. coli","Klebsiella spp.","Proteus mirabilis"],
        "specimen_notes": {
            "Blood":  "🛑 Pseudomonas bacteremia.",
            "Sputum": "🛑 VAP/HAP مع Pseudomonas.",
            "Urine":  "🛑 UTI معقد مع Pseudomonas.",
        },
    },
    "Cefoperazone": {
        "priority": 4, "class": "3rd Gen Cephalosporin (IV)",
        "note": "💉 (مثل Cefobid) IV فقط — يُطرح صفراوياً. آمن في القصور الكلوي.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً — يُطرح عبر الصفراء بالكامل.",
        "hepatic_caution": True, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["cefobid"],
        "organisms": ["Pseudomonas aeruginosa","E. coli","Klebsiella spp.",
                      "Proteus mirabilis","Staphylococcus aureus"],
        "specimen_notes": {
            "Blood": "💉 bacteremia في مرضى القصور الكلوي (يُطرح كبدياً).",
            "Pus":   "💉 عدوى البطن والمرارة.",
        },
    },
    "Cefoperazone + Sulbactam": {
        "priority": 4, "class": "3rd Gen Cephalosporin + Beta-lactamase Inhibitor (IV)",
        "note": (
            "🛑 (مثل Sulperazone/Bakperazone) IV فقط. مزيج قوي ضد MDR gram-negatives "
            "بما فيها Acinetobacter baumannii. بديل مهم لـ Meropenem في بروتوكولات MDR المصرية."
        ),
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً — يُطرح صفراوياً أساساً.",
        "hepatic_caution": True, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["sulperazone","bakperazone","cefop-sulbactam","cefoperazone sulbactam"],
        "organisms": ["Acinetobacter baumannii","Pseudomonas aeruginosa","Klebsiella spp.",
                      "E. coli","Proteus mirabilis","Staphylococcus aureus"],
        "specimen_notes": {
            "Blood":      "🛑 MDR Acinetobacter/Pseudomonas bacteremia.",
            "Sputum":     "🛑 VAP/HAP بـ MDR Acinetobacter — بروتوكول ICU مصري شائع.",
            "Wound Swab": "🛑 العدوى الجراحية الشديدة ومضاعفات الحروق.",
            "Pus":        "🛑 الخراجات والعدوى داخل البطن عند فشل الخطوط الأولى.",
            "Urine":      "⚠️ بديل عند تعذر الكاربابينيم في MDR UTI.",
        },
    },
    "Cefepime": {
        "priority": 5, "class": "4th Gen Cephalosporin (IV)",
        "note": "🛑 (مثل Maxipime) IV فقط — للحالات الحرجة. Bioavailability فموي = صفر.",
        "renal_limit": 50, "renal_note": "⚠️ تعديل جرعة دقيق لتجنب السمية العصبية.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["maxipime"],
        "organisms": ["Pseudomonas aeruginosa","E. coli","Klebsiella spp.",
                      "Proteus mirabilis","Staphylococcus aureus",
                      "Enterococcus faecalis","Acinetobacter baumannii"],
        "specimen_notes": {
            "Blood":  "🛑 sepsis شديد مع اشتباه Pseudomonas.",
            "Sputum": "🛑 VAP/HAP الحرجة.",
            "CSF":    "🛑 meningitis المعقد في ICU.",
        },
    },
    # ── Fluoroquinolones ───────────────────────────────────────────────
    "Ciprofloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": (
            "⚠️ (مثل Ciprofar) Oral وIV. Bioavailability فموي ~70-80%. "
            "يُفضل ادخاره للمسالك المعقدة."
        ),
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Ciprofloxacin:\n"
            "  الموقف التقليدي: تجنب (FDA Category C).\n"
            "  الأدلة الحديثة (ACCP Journal 2025): الخطر الحقيقي\n"
            "  أقل مما كان متصوراً.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)","Warfarin (مضادات التخثر)"],
        "aliases": ["ciprofar","cipro","ciproflox"],
        "organisms": ["E. coli","Klebsiella spp.","Pseudomonas aeruginosa",
                      "Proteus mirabilis","Staphylococcus aureus",
                      "Salmonella spp.","Shigella spp.","Campylobacter jejuni"],
        "specimen_notes": {
            "Urine":      "⚠️ فعال لكن يُحفظ للمسالك المعقدة.",
            "Blood":      "⚠️ bacteremia في الحالات المتوسطة.",
            "Sputum":     "⚠️ الفلوروكينولون الوحيد الفعال ضد Pseudomonas في الصدر.",
            "Wound Swab": "⚠️ عدوى الجروح المعقدة.",
            "Stool":      "⚠️ Shigellosis والحالات الشديدة من Campylobacter.",
        },
    },
    "Levofloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": (
            "⚠️ (مثل Tavanic) Oral وIV. Bioavailability فموي ~99%. "
            "أفضل respiratory quinolone متاح."
        ),
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Levofloxacin:\n"
            "  فلوروكينولون — يُستخدم بحذر شديد.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["tavanic","levaquin","levoflox"],
        "organisms": ["E. coli","Klebsiella spp.","Pseudomonas aeruginosa",
                      "Staphylococcus aureus","Streptococcus pneumoniae","H. influenzae",
                      "Mycoplasma spp.","Legionella pneumophila"],
        "specimen_notes": {
            "Sputum": "⚠️ خيار قوي لـ CAP (respiratory quinolone) — Mycoplasma وLegionella.",
            "Urine":  "⚠️ فعال لكن يُحفظ للحالات المعقدة.",
            "Blood":  "⚠️ bacteremia في الحالات المتوسطة.",
        },
    },
    "Ofloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": "⚠️ (مثل Tarivid) Oral وIV. Bioavailability فموي ~98%.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Ofloxacin:\n"
            "  فلوروكينولون — يُستخدم بحذر شديد.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["tarivid","oflox"],
        "organisms": ["E. coli","Klebsiella spp.","Staphylococcus aureus","Proteus mirabilis"],
        "specimen_notes": {
            "Urine":  "⚠️ مناسب للمسالك المتوسطة.",
            "Sputum": "⚠️ عدوى الجهاز التنفسي.",
        },
    },
    "Norfloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": (
            "⚠️ (مثل Noroxin) Oral فقط — متخصص في المسالك البولية. "
            "Bioavailability ~35% لكن يتركز في البول."
        ),
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب عند CrCl < 30.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Norfloxacin:\n"
            "  فلوروكينولون — يُستخدم بحذر شديد.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["noroxin","norflox"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "Staphylococcus aureus","Enterococcus faecalis"],
        "specimen_notes": {
            "Urine": "⚠️ مخصص للمسالك البولية فقط — لا تركيز علاجي خارج البول.",
        },
    },
    # ── Urinary Antiseptics ────────────────────────────────────────────
    "Nitrofurantoin": {
        "priority": 1, "class": "Urinary Antiseptic (Oral)",
        "note": (
            "🎯 (مثل Macrofuran) Oral فقط — الخيار الأول للمسالك البسيطة. "
            "Bioavailability ~90% لكن يتركز في البول فقط."
        ),
        "renal_limit": 30, "renal_note": "🚫 ممنوع إذا CrCl < 30 مل/د.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Nitrofurantoin:\n"
            "  آمن في الـ 1st و 2nd trimester.\n"
            "  ممنوع في الـ 3rd trimester (خطر hemolytic anemia للجنين).\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["macrofuran","macrobid","nitrofur"],
        "organisms": ["E. coli","Staphylococcus aureus","Enterococcus faecalis","Klebsiella spp."],
        "specimen_notes": {
            "Urine": "🎯 مخصص للمسالك البولية البسيطة فقط — لا يُستخدم خارج البول أبداً.",
        },
    },
    "Fosfomycin": {
        "priority": 1, "class": "Phosphonic Acid (Oral)",
        "note": (
            "🎯 (مثل Monuril) Oral — جرعة واحدة للمسالك. "
            "Bioavailability ~34-58% لكن تركيزه في البول عالٍ جداً."
        ),
        "renal_limit": 10, "renal_note": "⚠️ حذر في القصور الشديد.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Fosfomycin:\n"
            "  بيانات محدودة — يُعتبر آمناً نسبياً بجرعة واحدة عند الضرورة.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False, "interacts_with": [],
        "aliases": ["monuril","fosfocin"],
        "organisms": ["E. coli","Enterococcus faecalis","Staphylococcus aureus","Klebsiella spp."],
        "specimen_notes": {
            "Urine": "🎯 جرعة واحدة للـ uncomplicated UTI — مثالي.",
        },
    },
    # ── Aminoglycosides ────────────────────────────────────────────────
    "Gentamicin": {
        "priority": 4, "class": "Aminoglycoside (IV/IM)",
        "note": "💉 (مثل Garamycin) IV/IM فقط — لا bioavailability فموي. سام للكلى والأذن.",
        "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى ضرورية.",
        "hepatic_caution": False, "aware": "Access", "high_po": False,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — Gentamicin:\n"
            "  سُمية للأذن الجنينية (ototoxicity) — FDA Category D.\n"
            "  يعبر المشيمة — خطر فقدان السمع الدائم للجنين."
        ),
        "child_safe": True,
        "interacts_with": ["NSAIDs (مسكنات الألم)"],
        "aliases": ["garamycin","genta"],
        "organisms": ["E. coli","Klebsiella spp.","Pseudomonas aeruginosa",
                      "Proteus mirabilis","Staphylococcus aureus"],
        "specimen_notes": {
            "Blood":      "💉 synergy مع beta-lactam في bacteremia الشديدة.",
            "Wound Swab": "💉 العدوى الجراحية الشديدة.",
            "Urine":      "💉 pyelonephritis المعقد عند عدم توفر بدائل.",
        },
    },
    "Amikacin": {
        "priority": 4, "class": "Aminoglycoside (IV/IM)",
        "note": "💉 (مثل Amikin) IV/IM فقط — لا bioavailability فموي. فعال ضد السالبات المقاومة.",
        "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — Amikacin:\n"
            "  سُمية للأذن الجنينية (ototoxicity) — FDA Category D.\n"
            "  يعبر المشيمة — خطر فقدان السمع الدائم للجنين."
        ),
        "child_safe": True,
        "interacts_with": ["NSAIDs (مسكنات الألم)"],
        "aliases": ["amikin","amikacin"],
        "organisms": ["E. coli","Klebsiella spp.","Pseudomonas aeruginosa",
                      "Proteus mirabilis","Staphylococcus aureus","Acinetobacter baumannii"],
        "specimen_notes": {
            "Blood":  "💉 MDR gram-negatives bacteremia.",
            "Sputum": "💉 HAP/VAP مع MDR organisms.",
            "Urine":  "💉 UTI المعقد مع MDR organisms.",
        },
    },
    # ── Macrolides ─────────────────────────────────────────────────────
    "Azithromycin": {
        "priority": 2, "class": "Macrolide (Oral/IV)",
        "note": (
            "✅ (مثل Zithrokan) Oral وIV. Bioavailability فموي ~37% "
            "لكن تركيزه النسيجي عالٍ جداً — فعال للجهاز التنفسي."
        ),
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["zithrokan","zithromax","azithro"],
        "organisms": ["Staphylococcus aureus","Streptococcus pneumoniae","H. influenzae",
                      "Mycoplasma spp.","Salmonella spp.","Shigella spp.",
                      "Campylobacter jejuni","Legionella pneumophila"],
        "specimen_notes": {
            "Sputum":     "✅ خيار ممتاز لـ CAP والـ atypicals (Mycoplasma/Legionella).",
            "Wound Swab": "✅ عدوى الجلد الخفيفة.",
            "Stool":      "✅ الخيار الأول في Campylobacter وبعض حالات Shigella.",
        },
    },
    "Clarithromycin": {
        "priority": 2, "class": "Macrolide (Oral/IV)",
        "note": "✅ (مثل Klacid) Oral وIV. Bioavailability فموي ~55%. فعال للصدر.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — Clarithromycin:\n"
            "  ارتبط بتشوهات خلقية في الدراسات الحيوانية والبشرية.\n"
            "  البديل الآمن: Azithromycin."
        ),
        "child_safe": True, "interacts_with": [],
        "aliases": ["klacid","biaxin"],
        "organisms": ["Staphylococcus aureus","Streptococcus pneumoniae",
                      "H. influenzae","Mycoplasma spp.","Legionella pneumophila"],
        "specimen_notes": {
            "Sputum": "✅ CAP والـ atypical pneumonia.",
        },
    },
    # ── Sulfonamides ───────────────────────────────────────────────────
    "Trimethoprim/Sulfamethoxazole": {
        "priority": 2, "class": "Sulfonamide (Oral/IV)",
        "note": (
            "✅ (مثل Sutrim/Bactrim) Oral وIV. Bioavailability فموي ~100%. "
            "ممتاز للمسالك والجهاز التنفسي."
        ),
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — TMP/SMX:\n"
            "  يثبط حمض الفوليك — خطر Neural Tube Defects في الـ 1st trimester.\n"
            "  يسبب kernicterus للجنين في الـ 3rd trimester."
        ),
        "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["septra","sutrim","bactrim","co-trimoxazole","tmp-smx"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis","Staphylococcus aureus",
                      "Stenotrophomonas maltophilia","Shigella spp.","Salmonella spp."],
        "specimen_notes": {
            "Urine":      "✅ فعال للمسالك البسيطة عند تأكيد الحساسية.",
            "Sputum":     "✅ الجهاز التنفسي — خيار أول لـ Stenotrophomonas.",
            "Wound Swab": "✅ MRSA skin infections (SSTI).",
        },
    },
    # ── Nitroimidazoles ────────────────────────────────────────────────
    "Metronidazole": {
        "priority": 1, "class": "Nitroimidazole (Oral/IV)",
        "note": (
            "✅ (مثل Flagyl) Oral وIV. Bioavailability فموي ~100%. "
            "الخيار الأول للأنيروبيك."
        ),
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True, "aware": "Access", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Metronidazole:\n"
            "  تجنب في الـ 1st trimester (مخاوف تاريخية).\n"
            "  مقبول في الـ 2nd و 3rd trimester بإشراف طبي.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["flagyl","metro","metrogyl"],
        "organisms": ["Anaerobes (لاهوائيات)"],
        "specimen_notes": {
            "Pus":        "✅ الخراجات والعدوى المختلطة (anaerobic coverage).",
            "Wound Swab": "✅ العدوى الجراحية التي تشمل اللاهوائيات.",
            "Stool":      "✅ بعض الطفيليات والعدوى اللاهوائية.",
            "Blood":      "✅ sepsis البطن مع اشتباه anaerobic.",
        },
    },
    "Tinidazole": {
        "priority": 2, "class": "Nitroimidazole (Oral)",
        "note": "✅ (مثل Fasigyn) Oral فقط. Bioavailability ~100%. بديل Metronidazole.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True, "aware": "Access", "high_po": True,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — Tinidazole:\n"
            "  ممنوع في الـ 1st trimester.\n"
            "  يُفضل تجنبه طوال الحمل — استبدل بـ Metronidazole."
        ),
        "child_safe": False,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["fasigyn","tini"],
        "organisms": ["Anaerobes (لاهوائيات)"],
        "specimen_notes": {
            "Wound Swab": "✅ عدوى اللاهوائيات الخفيفة.",
        },
    },
    # ── Tetracyclines ──────────────────────────────────────────────────
    "Doxycycline": {
        "priority": 2, "class": "Tetracycline (Oral/IV)",
        "note": (
            "✅ (مثل Vibramycin) Oral وIV. Bioavailability فموي ~93%. "
            "فعال للكلاميديا والمايكوبلازما."
        ),
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً نسبياً.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Doxycycline:\n"
            "  الموقف التقليدي: ممنوع (FDA Category D).\n"
            "  الأدلة الحديثة (ACCP 2025): خطر أقل في الاستخدام القصير.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["vibramycin","doxy"],
        "organisms": ["Mycoplasma spp.","Staphylococcus aureus","H. influenzae",
                      "Rickettsia spp.","Acinetobacter baumannii",
                      "Stenotrophomonas maltophilia","Legionella pneumophila"],
        "specimen_notes": {
            "Sputum":     "✅ atypical pneumonia (Mycoplasma/Legionella).",
            "Wound Swab": "✅ MRSA SSTI و Rickettsia.",
            "Blood":      "✅ Rickettsia bacteremia.",
        },
    },
    # ── Carbapenems ────────────────────────────────────────────────────
    "Imipenem/Cilastatin": {
        "priority": 5, "class": "Carbapenem (IV)",
        "note": (
            "🛑 (مثل Tienam) IV فقط — bioavailability فموي = صفر. "
            "أوسع كاربابينيم طيفاً — يغطي Pseudomonas والموجبات والسالبات واللاهوائيات. "
            "⚠️ خطر نوبات صرع عند الجرعات العالية أو القصور الكلوي. "
            "Cilastatin يمنع تكسره كلوياً."
        ),
        "renal_limit": 50,
        "renal_note": (
            "⚠️ تعديل جرعة حتمي — يتراكم في القصور الكلوي "
            "ويزيد خطر نوبات الصرع بشكل مباشر."
        ),
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Imipenem/Cilastatin:\n"
            "  بيانات محدودة في الحمل البشري.\n"
            "  يُستخدم عند الضرورة القصوى فقط.\n"
            "  يُفضل Meropenem عند الحاجة لكاربابينيم في الحمل.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": True,
        "interacts_with": ["Valproic acid (مضادات الصرع)"],
        "aliases": ["tienam","primaxin","imipenem","imipenem cilastatin"],
        "organisms": ["Pseudomonas aeruginosa","Klebsiella spp.","E. coli",
                      "Acinetobacter baumannii","Enterococcus faecalis",
                      "Staphylococcus aureus","Proteus mirabilis",
                      "Anaerobes (لاهوائيات)"],
        "specimen_notes": {
            "Blood":  "🛑 sepsis شديد — MDR organisms — يغطي طيفاً أوسع من Meropenem.",
            "Sputum": "🛑 VAP/HAP بـ MDR organisms — بديل Meropenem.",
            "Urine":  "🛑 UTI المعقد بـ CRE عند تعذر خيارات أخرى.",
            "Pus":    "🛑 عدوى البطن الشديدة المختلطة — يغطي اللاهوائيات أيضاً.",
            "CSF":    "⚠️ لا يُفضل في meningitis — خطر نوبات صرع. استخدم Meropenem.",
        },
    },
    "Ertapenem": {
        "priority": 5, "class": "Carbapenem non-anti-pseudomonal (IV/IM)",
        "note": (
            "🛑 (مثل Invanz) IV/IM — جرعة يومية واحدة. "
            "لا يغطي Pseudomonas ولا Acinetobacter. Bioavailability فموي = صفر."
        ),
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب عند CrCl < 30.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["invanz","ertapenem"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "Staphylococcus aureus","Enterococcus faecalis",
                      "Anaerobes (لاهوائيات)"],
        "specimen_notes": {
            "Blood": "🛑 ESBL bacteremia — يفضل على Meropenem للحفاظ على الكاربابينيم.",
            "Urine": "🛑 ESBL-producing UTI المعقد فقط.",
            "Pus":   "🛑 عدوى البطن المعقدة بـ ESBL.",
        },
    },
    "Meropenem": {
        "priority": 5, "class": "Carbapenem (IV)",
        "note": (
            "🛑 (مثل Meronem) IV فقط — الملاذ الأخير للمقاومة. "
            "Bioavailability فموي = صفر. أقل خطراً للصرع من Imipenem."
        ),
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True, "interacts_with": [],
        "aliases": ["meronem","merrem"],
        "organisms": ["Pseudomonas aeruginosa","Klebsiella spp.","E. coli",
                      "Enterococcus faecalis","Staphylococcus aureus","MRSA",
                      "Acinetobacter baumannii"],
        "specimen_notes": {
            "Blood":  "🛑 sepsis شديد — MDR organisms — ICU.",
            "CSF":    "🛑 meningitis المعقد — MDR — أفضل من Imipenem للـ CNS.",
            "Sputum": "🛑 VAP/HAP بـ MDR organisms.",
            "Urine":  "🛑 UTI المعقد جداً بـ CRE.",
        },
    },
    # ── Glycopeptides / Oxazolidinones ─────────────────────────────────
    "Vancomycin": {
        "priority": 5, "class": "Glycopeptide (IV)",
        "note": (
            "🛑 IV فقط — خاص بـ MRSA والحالات الحرجة. "
            "Bioavailability فموي < 5% جهازياً — IV فقط للعدوى الجهازية. "
            "مراقبة الـ Trough أو AUC/MIC حتمية."
        ),
        "renal_limit": 50, "renal_note": "⚖️ مراقبة مستوى الدواء في الدم.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Vancomycin:\n"
            "  يُستخدم عند الضرورة القصوى (MRSA في الحمل).\n"
            "  مراقبة وظائف الكلى والسمع للأم والجنين.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": True,
        "interacts_with": ["NSAIDs (مسكنات الألم)"],
        "aliases": ["vancocin","vanco"],
        "organisms": ["MRSA","Staphylococcus aureus","Enterococcus faecalis",
                      "Streptococcus pneumoniae"],
        "specimen_notes": {
            "Blood":      "🛑 MRSA bacteremia.",
            "CSF":        "🛑 MRSA meningitis.",
            "Sputum":     "🛑 MRSA pneumonia في ICU.",
            "Wound Swab": "🛑 MRSA wound infection.",
        },
    },
    "Linezolid": {
        "priority": 5, "class": "Oxazolidinone (Oral/IV)",
        "note": (
            "🛑 (مثل Averozolid) Oral وIV. Bioavailability فموي ~100%. "
            "للموجبات المقاومة (MRSA/VRE) فقط."
        ),
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": False, "aware": "Reserve", "high_po": True,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — Linezolid:\n"
            "  أثبت سُمية جنينية في الحيوانات.\n"
            "  يُستخدم فقط عند انعدام البدائل."
        ),
        "child_safe": True,
        "interacts_with": ["SSRI (أدوية الاكتئاب)"],
        "aliases": ["averozolid","zyvox"],
        "organisms": ["MRSA","Staphylococcus aureus","Enterococcus faecalis",
                      "VRE","Streptococcus pneumoniae"],
        "specimen_notes": {
            "Blood":      "🛑 VRE/MRSA bacteremia.",
            "Sputum":     "🛑 MRSA pneumonia — تركيز رئوي ممتاز.",
            "Wound Swab": "🛑 MRSA/VRE wound infection.",
            "CSF":        "🛑 اختراق ممتاز للـ CNS.",
        },
    },
    # ── Polymyxins ─────────────────────────────────────────────────────
    "Colistin": {
        "priority": 6, "class": "Polymyxin (IV)",
        "note": (
            "🔴 IV فقط — الملاذ الأخير للـ MDR gram-negatives. "
            "Bioavailability فموي = صفر."
        ),
        "renal_limit": 80, "renal_note": "⚖️ سام جداً للكلى — مراقبة حتمية.",
        "hepatic_caution": False, "aware": "Reserve", "high_po": False,
        "preg_status": "Warn",
        "preg_note": "يُستخدم فقط لإنقاذ الحياة عند غياب البدائل.",
        "child_safe": True,
        "interacts_with": ["NSAIDs (مسكنات الألم)"],
        "aliases": ["colistin","polymyxin e"],
        "organisms": ["Pseudomonas aeruginosa","Acinetobacter baumannii","Klebsiella spp."],
        "specimen_notes": {
            "Blood":  "🔴 MDR/XDR bacteremia — ملاذ أخير.",
            "Sputum": "🔴 VAP بـ XDR Acinetobacter/Pseudomonas.",
        },
    },
}

# ==========================================
# 🦠 Organism Profiles
# ==========================================
ORGANISM_PROFILE = {
    "E. coli": {
        "first_line": ["Nitrofurantoin","Fosfomycin",
                       "Trimethoprim/Sulfamethoxazole","Amoxicillin + Clavulanic acid"],
        "second_line": ["Cefuroxime","Cefuroxime sodium","Cefixime",
                        "Norfloxacin","Ciprofloxacin"],
        "third_line":  ["Ertapenem","Meropenem"],
        "avoid": [],
        "urine_note": (
            "Norfloxacin: مخصص للمسالك فقط — لا تركيز علاجي خارج البول.\n"
            "Ertapenem: يُحفظ للـ ESBL-producing E. coli فقط."
        ),
        "specimen_context": {
            "Blood":      "🔬 الأكثر شيوعاً في bacteremia الجهاز البولي والبطن.",
            "Sputum":     "⚠️ E. coli في البلغم — نادر، يشير لـ aspiration أو HAP.",
            "Wound Swab": "🔬 شائع في عدوى الجروح الجراحية والحروق.",
            "Pus":        "🔬 شائع في خراجات البطن.",
            "Stool":      "🔬 ETEC/EPEC — إسهال المسافرين.",
        },
        "note": "🔬 الأكثر شيوعاً في مزارع البول.",
    },
    "Klebsiella spp.": {
        "first_line": ["Amoxicillin + Clavulanic acid","Cefuroxime","Cefixime"],
        "second_line": ["Cefuroxime sodium","Norfloxacin","Ciprofloxacin",
                        "Piperacillin + Tazobactam","Ceftriaxone"],
        "third_line":  ["Ertapenem","Meropenem"],
        "avoid": ["Ampicillin"],
        "urine_note": (
            "Ertapenem: الخيار الأول لـ ESBL-producing Klebsiella (IDSA 2023).\n"
            "Norfloxacin: للمسالك فقط."
        ),
        "specimen_context": {
            "Blood":      "🔬 Klebsiella bacteremia — خطر خصوصاً في الكبد.",
            "Sputum":     "🔬 HAP وعدوى الجهاز التنفسي في المستشفى.",
            "Wound Swab": "🔬 عدوى الجروح الجراحية.",
            "Pus":        "🔬 خراجات الكبد والبطن.",
            "Urine":      "🔬 الثاني الأكثر شيوعاً في مزارع البول.",
        },
        "note": "🔬 تحقق من ESBL — مقاومة طبيعية لبعض البيتا-لاكتام.",
    },
    "Pseudomonas aeruginosa": {
        "first_line": ["Piperacillin + Tazobactam","Ceftazidime","Ciprofloxacin"],
        "second_line": ["Cefepime","Cefoperazone + Sulbactam",
                        "Meropenem","Imipenem/Cilastatin","Amikacin"],
        "third_line":  ["Colistin"],
        "avoid": ["Nitrofurantoin","Fosfomycin","Trimethoprim/Sulfamethoxazole",
                  "Cephalexin","Cefadroxil","Cefaclor","Norfloxacin",
                  "Cefuroxime sodium","Ertapenem"],
        "urine_note": (
            "Ertapenem: ممنوع لـ Pseudomonas — لا نشاط (EUCAST).\n"
            "Ciprofloxacin هو الفلوروكينولون الوحيد الفعال ضد Pseudomonas."
        ),
        "specimen_context": {
            "Blood":      "🔴 Pseudomonas bacteremia — mortality عالية — ICU.",
            "Sputum":     "🔴 VAP/HAP الأكثر خطورة — anti-pseudomonal إلزامي.",
            "Wound Swab": "🔴 شائع في حروق والجروح المزمنة.",
            "Urine":      "🔴 UTI المعقد — كاتيتر أو مضادات سابقة.",
        },
        "note": "🔬 جرثومة انتهازية — تحتاج anti-pseudomonal متخصص.",
    },
    "Acinetobacter baumannii": {
        "first_line": ["Ampicillin/Sulbactam","Cefoperazone + Sulbactam"],
        "second_line": ["Meropenem","Imipenem/Cilastatin","Amikacin",
                        "Trimethoprim/Sulfamethoxazole","Doxycycline"],
        "third_line":  ["Colistin"],
        "avoid": ["Ertapenem","Cephalexin","Cefuroxime","Ceftriaxone",
                  "Azithromycin","Clarithromycin","Nitrofurantoin","Fosfomycin"],
        "specimen_context": {
            "Blood":      "🔴 Acinetobacter bacteremia — ICU — MDR غالباً.",
            "Sputum":     "🔴 VAP الأكثر شيوعاً في ICU — خطر جداً.",
            "Wound Swab": "🔴 عدوى الحروق والجروح الكبيرة.",
        },
        "note": (
            "🔴 MDR — Ampicillin/Sulbactam أو Cefoperazone/Sulbactam "
            "بجرعات عالية هو الأساس (IDSA AMR 2025)."
        ),
    },
    "Staphylococcus aureus": {
        "first_line": ["Cephalexin","Cefadroxil","Amoxicillin + Clavulanic acid"],
        "second_line": ["Cefuroxime sodium","Azithromycin","Doxycycline"],
        "third_line":  [],
        "avoid": [],
        "urine_note": (
            "تحقق من MRSA — إذا MRSA: Vancomycin أو Linezolid فقط.\n"
            "S. aureus في البول → تحقق من Blood culture (hematogenous seeding)."
        ),
        "specimen_context": {
            "Blood":      "🔬 تحقق من MRSA فوراً — خطر endocarditis.",
            "Sputum":     "🔬 pneumonia بعد الإنفلونزا أو في ICU.",
            "Wound Swab": "🔬 الأكثر شيوعاً في عدوى الجروح.",
            "Pus":        "🔬 خراجات الجلد والأنسجة الرخوة.",
            "Urine":      "⚠️ S. aureus في البول — احتمال hematogenous seeding.",
        },
        "note": "🔬 تحقق من MRSA — قد يحتاج Vancomycin.",
    },
    "MRSA": {
        "first_line": ["Vancomycin","Linezolid"],
        "second_line": ["Trimethoprim/Sulfamethoxazole","Doxycycline"],
        "third_line":  [],
        "avoid": ["Cephalexin","Cefadroxil","Cefaclor","Cefuroxime","Cefuroxime sodium",
                  "Ceftriaxone","Amoxicillin + Clavulanic acid","Ampicillin/Sulbactam",
                  "Piperacillin + Tazobactam","Ertapenem"],
        "urine_note": "جميع البيتا-لاكتام لا تعمل على MRSA (mecA gene — PBP2a resistance).",
        "specimen_context": {
            "Blood":      "🔴 MRSA bacteremia — ابدأ Vancomycin فوراً.",
            "Sputum":     "🔴 MRSA pneumonia — خطر في ICU.",
            "Wound Swab": "🔴 MRSA SSTI — شائع في المجتمع (CA-MRSA).",
            "Pus":        "🔴 MRSA abscess — drainage + Vancomycin.",
            "CSF":        "🔴 MRSA meningitis — نادر لكن خطر.",
        },
        "note": "🔴 مقاوم لجميع البيتا-لاكتام — Vancomycin أو Linezolid فقط.",
    },
    "Proteus mirabilis": {
        "first_line": ["Amoxicillin + Clavulanic acid","Cefuroxime","Cefixime"],
        "second_line": ["Cefuroxime sodium","Norfloxacin","Ciprofloxacin",
                        "Trimethoprim/Sulfamethoxazole"],
        "third_line":  ["Ertapenem"],
        "avoid": ["Nitrofurantoin","Tetracyclines","Colistin"],
        "urine_note": (
            "Nitrofurantoin: مقاوم طبيعياً لـ Proteus (intrinsic) — EUCAST.\n"
            "Norfloxacin: فعال في UTI فقط."
        ),
        "specimen_context": {
            "Urine":      "🔬 شائع في UTI — يرفع الـ pH (urease).",
            "Wound Swab": "🔬 عدوى الجروح المزمنة والقدم السكري.",
            "Blood":      "⚠️ Proteus bacteremia — مصدره البولي غالباً.",
        },
        "note": "🔬 مقاوم طبيعياً لـ Nitrofurantoin — لا تستخدمه أبداً.",
    },
    "Enterococcus faecalis": {
        "first_line": ["Amoxicillin + Clavulanic acid","Fosfomycin","Nitrofurantoin"],
        "second_line": ["Ampicillin/Sulbactam","Vancomycin","Linezolid"],
        "third_line":  [],
        "avoid": ["Cephalosporins (كل الجيل)","Trimethoprim/Sulfamethoxazole",
                  "Cefuroxime sodium","Ertapenem","Norfloxacin"],
        "urine_note": (
            "Ertapenem وCefuroxime sodium: لا نشاط ضد Enterococcus (EUCAST).\n"
            "جميع السيفالوسبورين مقاومة طبيعياً لـ Enterococcus."
        ),
        "specimen_context": {
            "Urine":      "🔬 شائع في UTI خصوصاً الكاتيتر.",
            "Blood":      "⚠️ Enterococcus bacteremia — خطر endocarditis.",
            "Wound Swab": "⚠️ عدوى البطن والجروح الجراحية.",
        },
        "note": "🔬 مقاوم طبيعياً للسيفالوسبورين — Amoxicillin هو الأساس.",
    },
    "Salmonella spp.": {
        "first_line": ["Ceftriaxone","Azithromycin","Ciprofloxacin"],
        "second_line": ["Trimethoprim/Sulfamethoxazole","Cefixime"],
        "third_line":  [],
        "avoid": ["Nitrofurantoin","Fosfomycin","Cephalexin","Cefadroxil",
                  "Cefaclor","Cefuroxime","Metronidazole","Doxycycline"],
        "urine_note": "",
        "specimen_context": {
            "Stool": "🔬 Salmonella gastroenteritis — العلاج للحالات الشديدة فقط.",
            "Blood": "🔬 Typhoid fever — Ceftriaxone أو Azithromycin.",
        },
        "note": "🔬 العلاج مخصص للحالات الشديدة أو الحمى التيفودية فقط.",
    },
    "Shigella spp.": {
        "first_line": ["Azithromycin","Ciprofloxacin","Ceftriaxone"],
        "second_line": ["Trimethoprim/Sulfamethoxazole"],
        "third_line":  [],
        "avoid": ["Nitrofurantoin","Fosfomycin","Amoxicillin + Clavulanic acid",
                  "Metronidazole"],
        "urine_note": "",
        "specimen_context": {
            "Stool": "🔬 Shigellosis — العلاج يقلل الأعراض ويمنع الانتشار.",
            "Blood": "🔬 نادراً ما يصل للدم إلا في الحالات الشديدة.",
        },
        "note": "🔬 تعالج الحالات الوخيمة — مقاومة عالية لـ TMP/SMX في مصر.",
    },
    "Campylobacter jejuni": {
        "first_line": ["Azithromycin"],
        "second_line": ["Ciprofloxacin"],
        "third_line":  [],
        "avoid": ["Trimethoprim/Sulfamethoxazole","Nitrofurantoin","Fosfomycin"],
        "urine_note": "",
        "specimen_context": {
            "Stool": "🔬 أشهر أسباب الإسهال البكتيري — غالباً محدود ذاتياً.",
            "Blood": "🔬 Bacteremia نادر في نقص المناعة.",
        },
        "note": "🔬 معظم الحالات لا تحتاج مضادات — Azithromycin عند الحاجة.",
    },
    "Streptococcus pneumoniae": {
        "first_line": ["Amoxicillin + Clavulanic acid","Ceftriaxone","Levofloxacin"],
        "second_line": ["Azithromycin","Clarithromycin","Cefuroxime"],
        "third_line":  ["Vancomycin","Linezolid"],
        "avoid": [],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔬 السبب الأول لـ CAP — تحقق من مقاومة Penicillin.",
            "Blood":  "🔬 Pneumococcal bacteremia — خطر في المسنين.",
            "CSF":    "🔬 السبب الأول لـ bacterial meningitis في البالغين.",
        },
        "note": "🔬 السبب الأول لـ CAP والـ meningitis. تحقق من MIC للـ Penicillin.",
    },
    "H. influenzae": {
        "first_line": ["Amoxicillin + Clavulanic acid","Cefuroxime","Ceftriaxone"],
        "second_line": ["Azithromycin","Levofloxacin","Trimethoprim/Sulfamethoxazole"],
        "third_line":  [],
        "avoid": ["Ampicillin (alone)"],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔬 شائع في COPD exacerbation و CAP.",
            "Blood":  "⚠️ H. influenzae bacteremia — نادر بعد التطعيم.",
            "CSF":    "⚠️ H. influenzae meningitis — نادر جداً الآن.",
        },
        "note": "🔬 30% ينتجون beta-lactamase — Amoxicillin/Clavulanate مفضل.",
    },
    "Legionella pneumophila": {
        "first_line": ["Levofloxacin","Azithromycin"],
        "second_line": ["Doxycycline","Clarithromycin"],
        "third_line":  [],
        "avoid": ["Beta-lactams (alone)","Aminoglycosides","Cephalosporins (alone)"],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔬 Legionella — CAP الشديد، خاصةً في الفنادق أو مكيفات الهواء.",
            "Blood":  "⚠️ Bacteremia نادر — التشخيص بـ Urine Antigen أو PCR.",
        },
        "note": "🔬 Levofloxacin هو الخيار الأول. لا يُعزل بالزراعة العادية — يحتاج وسط BCYE.",
    },
    "Mycoplasma spp.": {
        "first_line": ["Azithromycin","Doxycycline"],
        "second_line": ["Levofloxacin","Clarithromycin"],
        "third_line":  [],
        "avoid": ["Beta-lactams","Cephalosporins","Vancomycin","Aminoglycosides"],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔬 Atypical pneumonia — Walking pneumonia — خاصةً في الشباب.",
        },
        "note": "🔬 لا جدار خلوي — كل البيتا-لاكتام غير فعالة. يُشخص بـ PCR أو Serology.",
    },
    "Anaerobes (لاهوائيات)": {
        "first_line": ["Metronidazole","Amoxicillin + Clavulanic acid"],
        "second_line": ["Piperacillin + Tazobactam","Meropenem",
                        "Imipenem/Cilastatin","Ampicillin/Sulbactam"],
        "third_line":  [],
        "avoid": ["Aminoglycosides","Nitrofurantoin"],
        "urine_note": "",
        "specimen_context": {
            "Pus":        "🔬 الخراجات داخل البطن — Metronidazole ضروري.",
            "Wound Swab": "🔬 العدوى الجراحية بعد عمليات الأمعاء.",
            "Blood":      "🔬 Bacteremia اللاهوائيات — مصدره البطن غالباً.",
        },
        "note": "🔬 Metronidazole هو الخيار الأول لكل اللاهوائيات.",
    },
    "Stenotrophomonas maltophilia": {
        "first_line": ["Trimethoprim/Sulfamethoxazole"],
        "second_line": ["Levofloxacin","Doxycycline"],
        "third_line":  [],
        "avoid": ["Carbapenems","Ertapenem","Meropenem","Imipenem/Cilastatin",
                  "Aminoglycosides","Ceftriaxone","Cefepime"],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔴 شائع في VAP/HAP في ICU — خاصةً بعد علاج طويل بالكاربابينيم.",
            "Blood":  "🔴 Stenotrophomonas bacteremia — نادر لكن خطر في المناعة الضعيفة.",
        },
        "note": "🔴 مقاومة طبيعية للكاربابينيم! TMP/SMX هو الخيار الأول. ينتقى بعد Meropenem.",
    },
}

# ─── خريطة العينات → البكتيريا المرتبطة ─────────────────────────────
SPECIMEN_ORGANISM_MAP = {
    "Urine": [
        "E. coli","Klebsiella spp.","Proteus mirabilis",
        "Enterococcus faecalis","Staphylococcus aureus","MRSA",
        "Pseudomonas aeruginosa","Acinetobacter baumannii",
    ],
    "Blood": [
        "E. coli","Klebsiella spp.","Staphylococcus aureus","MRSA",
        "Pseudomonas aeruginosa","Acinetobacter baumannii",
        "Streptococcus pneumoniae","Enterococcus faecalis",
        "Salmonella spp.","Proteus mirabilis",
        "Anaerobes (لاهوائيات)","Stenotrophomonas maltophilia",
    ],
    "Sputum": [
        "Streptococcus pneumoniae","H. influenzae","Klebsiella spp.",
        "Pseudomonas aeruginosa","Acinetobacter baumannii","MRSA",
        "Staphylococcus aureus","E. coli","Legionella pneumophila",
        "Mycoplasma spp.","Stenotrophomonas maltophilia",
    ],
    "Wound Swab": [
        "Staphylococcus aureus","MRSA","E. coli","Klebsiella spp.",
        "Pseudomonas aeruginosa","Proteus mirabilis","Acinetobacter baumannii",
        "Enterococcus faecalis","Anaerobes (لاهوائيات)",
    ],
    "Pus": [
        "Staphylococcus aureus","MRSA","E. coli","Klebsiella spp.",
        "Pseudomonas aeruginosa","Acinetobacter baumannii",
        "Anaerobes (لاهوائيات)","Enterococcus faecalis","Proteus mirabilis",
    ],
    "Stool": [
        "Salmonella spp.","Shigella spp.","Campylobacter jejuni","E. coli",
    ],
    "CSF": [
        "Streptococcus pneumoniae","H. influenzae","MRSA",
        "Staphylococcus aureus","E. coli","Klebsiella spp.",
    ],
}

BACTERIA_TYPES  = list(ORGANISM_PROFILE.keys())
SPECIMEN_TYPES  = ["Urine","Blood","Sputum","Wound Swab","Pus","Stool","CSF"]
COMMON_MEDS     = ["Antacids (مضادات الحموضة)","Warfarin (مضادات التخثر)",
                   "NSAIDs (مسكنات الألم)","SSRI (أدوية الاكتئاب)",
                   "Valproic acid (مضادات الصرع)"]
AWARE_COLORS    = {"Access":"🟢 Access","Watch":"🟡 Watch","Reserve":"🔴 Reserve"}

# ==========================================
# 🔍 OCR + Fuzzy Matching
# ==========================================
def fuzzy_match(word, target):
    w, t = word.lower(), target.lower()
    if t in w or w in t: return 100
    return SequenceMatcher(None, w, t).ratio() * 100

def extract_all_data(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img        = cv2.imdecode(file_bytes, 1)
    gray       = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh  = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    full_text  = pytesseract.image_to_string(thresh, config='--psm 6')
    text_lower = full_text.lower()

    age_match    = re.search(r"(\d+)\s*[Yy]ears?", full_text)
    detected_age = age_match.group(1) if age_match else "25"
    detected_sex = "Female" if "female" in text_lower else "Male"

    detected_specimen = "Urine"
    for s in SPECIMEN_TYPES:
        if s.lower() in text_lower:
            detected_specimen = s; break

    detected_organism = "E. coli"
    organism_counts = {}
    for b in BACTERIA_TYPES:
        c = text_lower.count(b.lower())
        if c > 0: organism_counts[b] = c
    if organism_counts:
        detected_organism = max(organism_counts, key=organism_counts.get)

    sir_map = {}
    for line in full_text.splitlines():
        ll = line.lower().strip()
        result = None
        if   re.search(r'\b(s|sensitive|sens)\b', ll):     result = "S"
        elif re.search(r'\b(r|resistant|resist)\b', ll):    result = "R"
        elif re.search(r'\b(i|intermediate|inter)\b', ll):  result = "I"
        if result:
            for abx_name, info in ABX_GUIDELINES.items():
                for name in [abx_name] + info["aliases"]:
                    if fuzzy_match(name, ll) >= 75:
                        sir_map[abx_name] = result; break

    start = text_lower.find("highly")
    if start == -1: start = text_lower.find("sensitive")
    end   = text_lower.find("resistant")
    area  = full_text[start:end] if (start != -1 and end != -1) else full_text
    words = area.lower().split()

    detected_drugs = []
    for abx_name, info in ABX_GUIDELINES.items():
        matched = False
        for name in [abx_name] + info["aliases"]:
            for w in words:
                if any(fuzzy_match(w, nw) >= 82 for nw in name.lower().split()):
                    matched = True; break
            if matched: break
        if matched: detected_drugs.append(abx_name)

    return (
        {"Age": detected_age, "Sex": detected_sex,
         "Specimen": detected_specimen, "Organism": detected_organism},
        list(set(detected_drugs)),
        sir_map,
    )

# ==========================================
# 📄 Report Generator
# ==========================================
RENAL_BAN_REASONS = {
    "nitrofurantoin": (
        "Nitrofurantoin يحتاج وظيفة كلى سليمة ليتركز في البول.\n"
        "  عند CrCl < 30 مل/د:\n"
        "  - لا يصل لتركيز علاجي في البول → لا يقتل الجرثومة.\n"
        "  - يتراكم في الدم → خطر سُمية رئوية وعصبية.\n"
        "  السبب: الدواء يُطرح كلياً عبر الترشيح الكبيبي."
    ),
}

CHILD_BAN_REASONS = {
    "fluoroquinolone": (
        "الفلوروكينولونات تؤثر على غضاريف النمو في الأطفال < 18 سنة.\n"
        "  أثبتت الدراسات الحيوانية تلف مفصلي دائم.\n"
        "  تُستخدم فقط عند انعدام البدائل."
    ),
    "tetracycline": (
        "Doxycycline والتتراسيكلينات تترسب في العظام والأسنان النامية.\n"
        "  تلوين دائم للأسنان وتثبيط نمو العظام.\n"
        "  ممنوعة < 8 سنوات بشكل مطلق (AAP)."
    ),
}

def generate_report(age, sex, weight, cl_cr, is_renal, is_preg, is_hepatic,
                    allowed, warned, banned, preg_warn_items,
                    organism, specimen, interactions, sir_map):
    now  = datetime.now().strftime("%Y-%m-%d %H:%M")
    SEP  = "=" * 50
    SEP2 = "-" * 50
    r    = []

    r.append(SEP)
    r.append("   ORANGE LAB — CLINICAL DECISION REPORT")
    r.append(SEP)
    r.append(f"  Date      : {now}")
    r.append(SEP)
    r.append("\nPATIENT DETAILS:")
    r.append(f"  Age     : {age} years")
    r.append(f"  Gender  : {sex}")
    r.append(f"  Weight  : {weight} kg")
    renal_str = (f"IMPAIRED  |  CrCl = {cl_cr:.1f} ml/min  "
                 f"({'Mild' if cl_cr>=60 else 'Moderate' if cl_cr>=30 else 'Severe'})")
    r.append(f"  Renal   : {renal_str if is_renal else 'Normal'}")
    r.append(f"  Hepatic : {'IMPAIRED' if is_hepatic else 'Normal'}")
    if sex == "Female":
        r.append(f"  Pregnancy: {'PREGNANT' if is_preg else 'Not pregnant'}")

    r.append(f"\nCULTURE:")
    r.append(f"  Specimen : {specimen}")
    r.append(f"  Organism : {organism}")
    if organism in ORGANISM_PROFILE:
        op = ORGANISM_PROFILE[organism]
        r.append(f"  Note     : {op['note']}")
        spec_ctx = op.get("specimen_context", {}).get(specimen, "")
        if spec_ctx: r.append(f"  Specimen Context: {spec_ctx}")
        r.append(f"  First-line (guidelines): {', '.join(op['first_line'])}")
        if op["avoid"]: r.append(f"  Avoid (intrinsic resistance): {', '.join(op['avoid'])}")

    if sir_map:
        r.append(f"\nSENSITIVITY RESULTS:")
        r.append(f"  {'Antibiotic':<35} Result")
        r.append(f"  {'-'*35} ------")
        for drug, res in sir_map.items():
            icon = "Sensitive (S)" if res=="S" else ("Resistant (R)" if res=="R" else "Intermediate (I)")
            r.append(f"  {drug:<35} {icon}")

    non_preg = [i for i in interactions if "🤰" not in i]
    if non_preg:
        r.append(f"\nDRUG INTERACTIONS / WARNINGS:")
        for i in sorted(set(non_preg)):
            r.append(f"  ! {i}")

    r.append(f"\n{SEP}")
    r.append("  RECOMMENDED ANTIBIOTICS")
    r.append(SEP)
    if allowed:
        for item in sorted(allowed, key=lambda x: x["priority"]):
            sir_tag  = f"  [Culture: {sir_map.get(item['name'],'?')}]" if sir_map else ""
            preg_tag = "  [Pregnancy: Use with caution]" if (is_preg and item["preg_status"]=="Warn") else ""
            r.append(f"\n  {item['name']}{sir_tag}{preg_tag}")
            r.append(f"  {SEP2}")
            r.append(f"  WHO AWaRe : {item['aware']}")
            r.append(f"  Class     : {item['class']}")
            r.append(f"  Route     : {'Oral (PO) / IV' if item['high_po'] else 'IV/IM only'}")
            spec_note = item.get("specimen_notes", {}).get(specimen, "")
            if spec_note:
                r.append(f"  Note      : {item['note']}  |  [{specimen}]: {spec_note}")
            else:
                r.append(f"  Note      : {item['note']}")
            if is_renal: r.append(f"  Renal     : {item['renal_note']}")
            if is_preg and item["preg_status"] == "Warn":
                r.append(f"  Pregnancy : {item['preg_note'].splitlines()[0]}")
    else:
        r.append("  No recommended options after applying all restrictions.")

    if warned:
        r.append(f"\n{SEP}")
        r.append("  DOSE ADJUSTMENT REQUIRED")
        r.append(SEP)
        r.append(f"\n  Patient CrCl = {cl_cr:.1f} ml/min\n")
        for item in warned:
            sir_tag = f"  [Culture: {sir_map.get(item['name'],'')}]" if sir_map else ""
            r.append(f"  {item['name']}{sir_tag}")
            r.append(f"  {SEP2}")
            r.append(f"  WHO AWaRe : {item['aware']}")
            r.append(f"  Renal note: {item['renal_note']}")
            r.append(f"  Limit CrCl: <= {item['renal_limit']} ml/min")
            r.append("")

    if is_preg and preg_warn_items:
        r.append(f"\n{SEP}")
        r.append("  PREGNANCY — USE WITH CAUTION")
        r.append(SEP)
        for item in preg_warn_items:
            r.append(f"  {item['name']}")
            r.append(f"  {SEP2}")
            for line in item["preg_note"].splitlines():
                r.append(f"  {line}")
            r.append("")

    if banned:
        r.append(f"\n{SEP}")
        r.append("  CONTRAINDICATED / INEFFECTIVE")
        r.append(SEP)
        cat_resist   = [b for b in banned if b["category"] == "resistant"]
        cat_renal    = [b for b in banned if b["category"] == "renal"]
        cat_preg     = [b for b in banned if b["category"] == "pregnancy"]
        cat_child    = [b for b in banned if b["category"] == "child"]
        cat_organism = [b for b in banned if b["category"] == "organism"]
        cat_other    = [b for b in banned if b["category"] == "other"]

        if cat_resist:
            r.append(f"\n  [A] RESISTANT IN CULTURE:")
            for b in cat_resist:
                r.append(f"    x {b['name']}  — {b['reason_detail']}\n")

        if cat_renal:
            r.append(f"\n  [B] CONTRAINDICATED — RENAL IMPAIRMENT (CrCl={cl_cr:.1f}):")
            for b in cat_renal:
                r.append(f"    x {b['name']}  — {b['reason_short']}")
                detail_key = b["name"].lower().replace(" ","")
                for k, v in RENAL_BAN_REASONS.items():
                    if k in detail_key:
                        for ln in v.splitlines(): r.append(f"        {ln}")
                        break
                else:
                    r.append(f"        {b['reason_detail']}")
                r.append("")

        if cat_preg:
            r.append(f"\n  [C] CONTRAINDICATED — PREGNANCY:")
            for b in cat_preg:
                r.append(f"    x {b['name']}  — {b['reason_short']}")
                for ln in b["reason_detail"].splitlines(): r.append(f"        {ln}")
                r.append("")

        if cat_child:
            r.append(f"\n  [D] NOT SUITABLE — PATIENT < 18 YEARS (Age={age}):")
            for b in cat_child:
                r.append(f"    x {b['name']}  — {b['reason_short']}")
                cls = ABX_GUIDELINES.get(b["name"],{}).get("class","").lower()
                if "fluoroquinolone" in cls:
                    for ln in CHILD_BAN_REASONS["fluoroquinolone"].splitlines():
                        r.append(f"        {ln}")
                elif "tetracycline" in cls:
                    for ln in CHILD_BAN_REASONS["tetracycline"].splitlines():
                        r.append(f"        {ln}")
                else:
                    r.append(f"        {b['reason_detail']}")
                r.append("")

        if cat_organism:
            r.append(f"\n  [E] INEFFECTIVE FOR {organism} (intrinsic resistance):")
            for b in cat_organism:
                r.append(f"    x {b['name']}  — {b['reason_detail']}\n")

        if cat_other:
            r.append(f"\n  [F] OTHER CONTRAINDICATIONS:")
            for b in cat_other:
                r.append(f"    x {b['name']}  — {b['reason_detail']}\n")

    r.append(SEP)
    r.append("  DISCLAIMER:")
    r.append("  هذا التقرير مساعد للقرار الطبي وليس بديلاً عنه.")
    r.append("  القرار النهائي في الوصف يعود للطبيب المعالج.")
    r.append(SEP)
    r.append("  Guidelines : EUCAST 2026 | CLSI M100 2026 | IDSA AMR 2025 | Egypt National")
    r.append("  Route info : BNF 2025 | FDA Labels | WHO AWaRe 2025")
    r.append("  WHO AWaRe  : 🟢 Access = First choice | 🟡 Watch = Caution | 🔴 Reserve = Last resort")
    r.append(SEP)
    r.append("  Developed by: Dr. Hussein Ali | Orange Lab")
    r.append(SEP)
    return "\n".join(r)

# ==========================================
# 🖥️ Streamlit UI
# ==========================================
st.title("🛡️ Orange Culture Tool")
st.caption("AI-Assisted Antibiotic Decision Support — Egyptian Market Edition")

uploaded = st.file_uploader("📷 Upload Culture Report Image", type=["jpg","png","jpeg"])

if uploaded:
    cache_key = uploaded.name
    if "ocr_data" not in st.session_state or \
       st.session_state.get("last_file") != cache_key:
        with st.spinner("🔍 Analyzing report image..."):
            p, drugs, sir = extract_all_data(uploaded)
            st.session_state.ocr_data  = (p, drugs, sir)
            st.session_state.last_file = cache_key

    patient, drugs_from_ocr, sir_map = st.session_state.ocr_data

    col1, col2 = st.columns([1, 1.6])

    with col1:
        st.subheader("👤 Patient & Culture")

        culture_type = st.selectbox(
            "🧫 Specimen", SPECIMEN_TYPES,
            index=SPECIMEN_TYPES.index(patient["Specimen"])
                  if patient["Specimen"] in SPECIMEN_TYPES else 0)

        # ─── فلترة البكتيريا حسب العينة ─────────────────────────────
        filtered_organisms = [o for o in SPECIMEN_ORGANISM_MAP.get(culture_type, BACTERIA_TYPES)
                               if o in ORGANISM_PROFILE]
        ocr_org = patient["Organism"]
        default_idx = filtered_organisms.index(ocr_org) if ocr_org in filtered_organisms else 0

        organism_type = st.selectbox(
            "🦠 Organism", filtered_organisms, index=default_idx,
            help=f"بكتيريا شائعة في عينة {culture_type}")

        if organism_type in ORGANISM_PROFILE:
            op = ORGANISM_PROFILE[organism_type]
            with st.expander("📌 Organism Guidance", expanded=True):
                st.info(op["note"])
                spec_ctx = op.get("specimen_context", {}).get(culture_type, "")
                if spec_ctx: st.warning(f"**{culture_type} Context:** {spec_ctx}")
                st.write("**First-line:**", ", ".join(op["first_line"]))
                st.write("**Second-line:**", ", ".join(op["second_line"]))
                if op.get("third_line"):
                    st.write("**Third-line:**", ", ".join(op["third_line"]))
                if op["avoid"]:
                    st.error("**Avoid:** " + ", ".join(op["avoid"]))
                if culture_type == "Urine" and op.get("urine_note"):
                    st.info(f"📌 Urine notes:\n{op['urine_note']}")

        st.divider()
        age    = st.number_input("Age (years)", value=int(patient["Age"]),
                                 min_value=0, max_value=120)
        sex    = st.selectbox("Gender", ["Female","Male"],
                              index=0 if patient["Sex"]=="Female" else 1)
        weight = st.number_input("Weight (kg)", min_value=5, max_value=300, value=70)

        st.divider()
        is_renal = st.checkbox("🚩 Renal Impairment")
        cl_cr    = 100.0
        if is_renal:
            s_cr  = st.number_input("Serum Creatinine (mg/dL)",
                                    min_value=0.1, max_value=20.0, value=1.0, step=0.1)
            cl_cr = ((140 - age) * weight) / (72 * s_cr)
            if sex == "Female": cl_cr *= 0.85
            st.metric("CrCl (Cockcroft-Gault)", f"{cl_cr:.1f} ml/min",
                      delta="Mild" if cl_cr>=60 else ("Moderate" if cl_cr>=30 else "Severe"),
                      delta_color="normal" if cl_cr>=60 else ("off" if cl_cr>=30 else "inverse"))

        is_hepatic = st.checkbox("🚩 Hepatic Impairment")

        is_preg = False
        if sex == "Female" and 12 <= age <= 55:
            is_preg = st.checkbox("🤰 Patient is Pregnant")

        current_meds = st.multiselect("💊 Current Medications", COMMON_MEDS)

    with col2:
        st.subheader("💊 Antibiotic Analysis")

        if sir_map:
            st.info("📊 S/I/R detected: " +
                    " | ".join(f"{k}: **{v}**" for k,v in sir_map.items()))

        final_drugs = st.multiselect(
            "✅ Confirm/Edit Sensitive Antibiotics:",
            options=sorted(ABX_GUIDELINES.keys()),
            default=[d for d in drugs_from_ocr if d in ABX_GUIDELINES],
        )

        allowed, warned, banned = [], [], []
        preg_warn_items     = []
        interactions_alerts = []
        organism_avoid      = ORGANISM_PROFILE.get(organism_type,{}).get("avoid",[])

        for d in final_drugs:
            info  = ABX_GUIDELINES[d]
            d_low = d.lower()

            # ── مقاوم في المزرعة ───────────────────────────────────────
            if sir_map.get(d) == "R":
                banned.append({
                    "name": d, "category": "resistant",
                    "reason_short": "مقاوم (R) في نتيجة المزرعة.",
                    "reason_detail": (
                        f"المزرعة أثبتت أن {d} لا يثبط نمو الجرثومة.\n"
                        f"        MIC أعلى من الحد العلاجي — فشل علاجي مؤكد."
                    ),
                })
                continue

            # ── تعارض أدوية / تحذير كبدي ─────────────────────────────
            for med in current_meds:
                if med in info["interacts_with"]:
                    interactions_alerts.append(f"⚡ تعارض: {d} مع {med}")
            if is_hepatic and info["hepatic_caution"]:
                interactions_alerts.append(f"🏥 تحذير كبدي: {d} — يحتاج متابعة.")

            # ── مقاومة طبيعية للجرثومة ────────────────────────────────
            d_class = info.get("class","").lower()
            organism_avoided = False
            for av in organism_avoid:
                av_low = av.lower()
                if av_low in d_low or d_low in av_low:
                    organism_avoided = True; break
                if av_low in d_class or any(
                    av_low in cls.lower()
                    for cls in ["cephalosporin","penicillin","macrolide","tetracycline"]
                    if av_low in cls
                ):
                    organism_avoided = True; break

            if organism_avoided:
                banned.append({
                    "name": d, "category": "organism",
                    "reason_short": f"غير فعال لـ {organism_type} طبيعياً.",
                    "reason_detail": (
                        f"{d} — مقاومة طبيعية (intrinsic) لـ {organism_type}.\n"
                        f"        الاستخدام سيؤدي لفشل علاجي."
                    ),
                })
                continue

            # ── MRSA ────────────────────────────────────────────────────
            if organism_type == "MRSA":
                bl_classes = ["Penicillin","Cephalosporin"]
                if any(c in info["class"] for c in bl_classes):
                    banned.append({
                        "name": d, "category": "organism",
                        "reason_short": "بيتا-لاكتام — لا يعمل على MRSA.",
                        "reason_detail": (
                            "MRSA يحمل جين mecA — بروتين PBP2a.\n"
                            "        لا يرتبط بأي بيتا-لاكتام → جميعها غير فعالة."
                        ),
                    })
                    continue

            # ── ممنوع في الحمل ─────────────────────────────────────────
            if is_preg and info["preg_status"] == "Banned":
                banned.append({
                    "name": d, "category": "pregnancy",
                    "reason_short": info["preg_note"].splitlines()[0],
                    "reason_detail": info["preg_note"],
                })
                continue

            if is_preg and info["preg_status"] == "Warn":
                preg_warn_items.append({"name": d, **info})

            # ── الأطفال ────────────────────────────────────────────────
            cls = info["class"].lower()
            if age < 18 and not info.get("child_safe", True):
                if "fluoroquinolone" in cls:
                    banned.append({
                        "name": d, "category": "child",
                        "reason_short": "غير مناسب < 18 سنة.",
                        "reason_detail": CHILD_BAN_REASONS["fluoroquinolone"],
                    }); continue
                elif "tetracycline" in cls and age < 8:
                    banned.append({
                        "name": d, "category": "child",
                        "reason_short": "غير مناسب < 8 سنوات.",
                        "reason_detail": CHILD_BAN_REASONS["tetracycline"],
                    }); continue
                else:
                    banned.append({
                        "name": d, "category": "child",
                        "reason_short": "غير مرخص للأطفال.",
                        "reason_detail": "الشركة الصانعة لا توصي به < 18 سنة.",
                    }); continue

            # ── قصور كلوي حاد — Nitrofurantoin ────────────────────────
            if is_renal and "nitrofurantoin" in d_low and cl_cr < 30:
                banned.append({
                    "name": d, "category": "renal",
                    "reason_short": f"ممنوع — CrCl {cl_cr:.1f} < 30 مل/د.",
                    "reason_detail": (
                        f"CrCl = {cl_cr:.1f} مل/د — أقل من الحد المطلوب (30).\n"
                        f"        لا يتركز في البول ويتراكم في الدم مسبباً سُمية."
                    ),
                }); continue

            # ── تعديل جرعة ────────────────────────────────────────────
            if is_renal and info["renal_limit"] > 0 and cl_cr <= info["renal_limit"]:
                warned.append({"name": d, **info}); continue

            allowed.append({"name": d, **info})

        # ── عرض النتائج ────────────────────────────────────────────────
        non_preg_alerts = [a for a in interactions_alerts if "🤰" not in a]
        if non_preg_alerts:
            st.warning("⚡ Interactions / Hepatic Warnings")
            for a in sorted(set(non_preg_alerts)): st.write(a)

        if is_preg and preg_warn_items:
            st.markdown("---")
            st.markdown("### 🤰 Pregnancy — Use With Caution")
            st.info(
                "الأدوية التالية **ليست محظورة تلقائياً** لكنها تحتاج تقييم طبي دقيق.\n\n"
                "**القرار النهائي للطبيب المعالج حصراً.**"
            )
            for item in preg_warn_items:
                with st.expander(f"⚠️ {item['name']} — تفاصيل التحذير"):
                    for line in item["preg_note"].splitlines(): st.write(line)

        if banned:
            with st.expander("🚫 Contraindicated / Ineffective", expanded=True):
                for b in banned:
                    cat_label = {
                        "resistant": "مقاوم في المزرعة",
                        "renal":     "قصور كلوي",
                        "pregnancy": "ممنوع في الحمل",
                        "child":     "غير مناسب للعمر",
                        "organism":  "غير فعال للجرثومة",
                        "other":     "موانع أخرى",
                    }.get(b["category"], "")
                    st.error(f"💊 {b['name']}  [{cat_label}]\n{b['reason_short']}")

        if warned:
            with st.expander("🟡 Dose Adjustment Required", expanded=True):
                for item in warned:
                    sir_tag = f" [{sir_map.get(item['name'],'')}]" if sir_map else ""
                    st.warning(f"**{item['name']}{sir_tag}** — {item['renal_note']}")

        if allowed:
            st.success(f"🟢 {len(allowed)} Recommended Option(s)")
            for item in sorted(allowed, key=lambda x: x["priority"]):
                sir_badge = f" [{sir_map.get(item['name'],'?')}]" if sir_map else ""
                preg_flag = " 🤰" if (is_preg and item["preg_status"]=="Warn") else ""
                with st.expander(
                    f"{item['name']}{sir_badge}{preg_flag} — {AWARE_COLORS[item['aware']]}"
                ):
                    c1, c2 = st.columns(2)
                    c1.write(f"**Class:** {item['class']}")
                    c2.write(f"**Route:** {'🟢 Oral/IV' if item['high_po'] else '💉 IV/IM only'}")
                    st.write(f"**Note:** {item['note']}")
                    spec_note = item.get("specimen_notes", {}).get(culture_type, "")
                    if spec_note: st.info(f"**{culture_type} Note:** {spec_note}")
                    if is_preg and item["preg_status"] == "Warn":
                        st.caption("🤰 " + item["preg_note"].splitlines()[0])
        elif not banned and not warned:
            st.info("اختر المضادات الحساسة من القائمة أعلاه.")

        if final_drugs:
            st.divider()
            report_txt = generate_report(
                age, sex, weight, cl_cr, is_renal, is_preg, is_hepatic,
                allowed, warned, banned, preg_warn_items,
                organism_type, culture_type,
                interactions_alerts, sir_map,
            )
            st.download_button(
                "📄 Download Clinical Report",
                report_txt,
                file_name=f"Orange_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True,
            )

st.divider()
st.markdown("""
<div style="text-align:center;color:gray;font-size:0.85rem;">
  <strong>Developed by: Dr. Hussein Ali | Orange Lab</strong><br>
  EUCAST 2026 | CLSI M100 2026 | IDSA AMR 2025 | BNF 2025 | Egypt National Guidelines
</div>
""", unsafe_allow_html=True)
