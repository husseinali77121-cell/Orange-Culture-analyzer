import streamlit as st

st.set_page_config(page_title="Orange Culture Analyzer",
                   layout="wide", page_icon="🛡️")

# إخفاء GitHub وعناصر Streamlit
st.markdown("""
    <style>
    .stActionButton {display: none !important;}
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    header[data-testid="stHeader"] {display: none !important;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 🔐 نظام الاشتراك — يجب المرور به أولاً
# ==========================================
import json
from datetime import datetime

try:
    raw = st.secrets.get("subscribers_json") or st.secrets.get("subscribers", "{}")
    SUBSCRIBERS = json.loads(raw) if isinstance(raw, str) else dict(raw)
except Exception:
    SUBSCRIBERS = {}

def show_login_page():
    st.markdown("""
    <div style='text-align:center; padding: 3rem 0 1rem 0'>
        <span style='font-size:3rem'>🍊</span>
        <h2 style='margin:0.3rem 0 0.1rem 0'>Orange Culture Analyzer</h2>
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
            "📞 01016872801\n\n"
            "✉️ Hussein.ali77121@gmail.com\n\n"
            "---\n"
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

# ── تدفق تسجيل الدخول ───────────────────────────────────────────────
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
# ✅ ما بعد تسجيل الدخول — يبدأ التطبيق الأساسي هنا
# ══════════════════════════════════════════════════════════════════════

import numpy as np
import cv2
import pytesseract
import re
from difflib import SequenceMatcher

# ==========================================
# 📋 Antibiotics Database – Egyptian Market
# ==========================================
ABX_GUIDELINES = {
    "Amoxicillin + Clavulanic acid": {
        "priority": 1, "class": "Beta-lactamase Inhibitor",
        "note": "✅ خيار قياسي (مثل Augmentin/Curam).",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["augmentin", "curam", "amoxiclav", "co-amoxiclav"],
        "organisms": ["E. coli","Klebsiella spp.","Staphylococcus aureus",
                      "Proteus mirabilis","Streptococcus spp.","H. influenzae"],
        "specimen_notes": {
            "Blood":      "✅ فعال في bacteremia الموجبات والسالبات البسيطة.",
            "Sputum":     "✅ خيار جيد لـ CAP و exacerbation COPD.",
            "Wound Swab": "✅ فعال للعدوى الجلدية المختلطة.",
            "Pus":        "✅ جيد للخراجات والعدوى المختلطة.",
            "Urine":      "✅ خيار أول للمسالك غير المعقدة.",
        },
    },
    "Ampicillin/Sulbactam": {
        "priority": 2, "class": "Penicillin",
        "note": "💉 فعال للموجبات والسالبات. أساس علاج Acinetobacter بجرعات عالية (IDSA AMR).",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["unictam","sigmaclav","unasyn"],
        "organisms": ["E. coli","Klebsiella spp.","Staphylococcus aureus",
                      "Proteus mirabilis","Enterococcus faecalis", "Acinetobacter baumannii"],
        "specimen_notes": {
            "Blood":      "💉 IV فقط — فعال في bacteremia المختلطة.",
            "Sputum":     "💉 فعال في HAP/VAP خصوصاً Acinetobacter.",
            "Wound Swab": "💉 جيد للعدوى الجراحية والمختلطة.",
            "Pus":        "💉 فعال في الخراجات داخل البطن.",
        },
    },
    # ─── جديد ────────────────────────────────────────────────────────────
    "Cefoperazone + Sulbactam": {
        "priority": 4, "class": "3rd Gen Cephalosporin + Beta-lactamase Inhibitor",
        "note": (
            "🛑 (مثل Sulperazone/Bakperazone) مزيج قوي ضد سالبات الجرام الصعبة "
            "بما فيها Acinetobacter baumannii. "
            "يُعتبر بديلاً مهماً لـ Meropenem في بعض بروتوكولات MDR."
        ),
        "renal_limit": 0,
        "renal_note": "🟢 آمن كلوياً — يُطرح أساساً عبر الصفراء (biliary excretion).",
        "hepatic_caution": True,
        "aware": "Watch",
        "high_po": False,
        "preg_status": "Safe",
        "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["sulperazone","bakperazone","cefop-sulbactam","cefoperazone sulbactam"],
        "organisms": [
            "Acinetobacter baumannii",
            "Pseudomonas aeruginosa",
            "Klebsiella spp.",
            "E. coli",
            "Proteus mirabilis",
            "Staphylococcus aureus",
        ],
        "specimen_notes": {
            "Blood":      "🛑 bacteremia بـ MDR Acinetobacter أو Pseudomonas — بديل مهم للكاربابينيم.",
            "Sputum":     "🛑 VAP/HAP بـ MDR Acinetobacter baumannii — بروتوكول مصري شائع.",
            "Wound Swab": "🛑 العدوى الجراحية الشديدة ومضاعفات الحروق.",
            "Pus":        "🛑 الخراجات والعدوى داخل البطن عند فشل الخطوط الأولى.",
            "Urine":      "⚠️ يصل لتركيز كافٍ في البول — بديل عند تعذر الكاربابينيم.",
        },
    },
    # ─────────────────────────────────────────────────────────────────────
    "Piperacillin + Tazobactam": {
        "priority": 4, "class": "Anti-pseudomonal Penicillin",
        "note": "🛑 (مثل Tazocin) مضاد احتياطي واسع الطيف جداً (IDSA AMR).",
        "renal_limit": 20, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["tazocin","pip-tazo","piptaz"],
        "organisms": ["Pseudomonas aeruginosa","E. coli","Klebsiella spp.",
                      "Enterococcus faecalis","Proteus mirabilis", "Acinetobacter baumannii"],
        "specimen_notes": {
            "Blood":      "🛑 خيار قوي في sepsis شديد مع Pseudomonas.",
            "Sputum":     "🛑 VAP/HAP مع اشتباه Pseudomonas.",
            "Wound Swab": "🛑 العدوى الجراحية الشديدة.",
            "Pus":        "🛑 الخراجات داخل البطن الشديدة.",
        },
    },
    "Cephalexin": {
        "priority": 1, "class": "1st Gen Cephalosporin",
        "note": "✅ (مثل Ceporex) آمن للالتهابات البسيطة والجلد.",
        "renal_limit": 40, "renal_note": "⚖️ مباعدة الجرعات مطلوب.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["ceporex","keflex"],
        "organisms": ["Staphylococcus aureus","Streptococcus spp.",
                      "E. coli","Proteus mirabilis"],
        "specimen_notes": {
            "Wound Swab": "✅ خيار ممتاز للعدوى الجلدية البسيطة (cellulitis/impetigo).",
            "Urine":      "✅ مناسب للمسالك البسيطة.",
        },
    },
    "Cefadroxil": {
        "priority": 1, "class": "1st Gen Cephalosporin",
        "note": "✅ (مثل Duricef) فعال لالتهابات الحلق والجلد.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["duricef"],
        "organisms": ["Staphylococcus aureus","Streptococcus spp."],
        "specimen_notes": {
            "Wound Swab": "✅ جيد للعدوى الجلدية والأنسجة الرخوة.",
            "Sputum":     "✅ التهاب الحلق البكتيري (Strep pharyngitis).",
        },
    },
    "Cefaclor": {
        "priority": 2, "class": "2nd Gen Cephalosporin",
        "note": "✅ (مثل Ceclor) فعال للأذن الوسطى والمسالك.",
        "renal_limit": 10, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["ceclor"],
        "organisms": ["E. coli","H. influenzae","Staphylococcus aureus",
                      "Streptococcus spp.","Klebsiella spp."],
        "specimen_notes": {
            "Sputum":     "✅ التهابات الجهاز التنفسي العلوي والأذن الوسطى.",
            "Urine":      "✅ مناسب للمسالك البولية البسيطة.",
        },
    },
    "Cefuroxime": {
        "priority": 2, "class": "2nd Gen Cephalosporin",
        "note": "✅ (مثل Zinnat) واسع المدى للجهاز التنفسي والمسالك.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["zinnat","ceftin"],
        "organisms": ["E. coli","Klebsiella spp.","H. influenzae",
                      "Staphylococcus aureus","Streptococcus spp.","Proteus mirabilis"],
        "specimen_notes": {
            "Sputum":     "✅ CAP وعدوى الجهاز التنفسي.",
            "Wound Swab": "✅ عدوى الأنسجة الرخوة المتوسطة.",
            "Urine":      "✅ مناسب للمسالك.",
            "Blood":      "⚠️ لا يُفضل في bacteremia الشديدة — يُستبدل بـ IV.",
        },
    },
    "Ceftriaxone": {
        "priority": 3, "class": "3rd Gen Cephalosporin",
        "note": "⚠️ (مثل Rocephin) حقن فقط؛ لا يستخدم في الحالات البسيطة.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً (إطراح كبدي أساساً).",
        "hepatic_caution": True, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["rocephin","cefaxone","triaxone"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "Staphylococcus aureus","Streptococcus spp.","H. influenzae",
                      "Salmonella spp.","Shigella spp.","Neisseria gonorrhoeae"],
        "specimen_notes": {
            "Blood":      "💉 خيار ممتاز في bacteremia والـ sepsis.",
            "CSF":        "💉 خيار أول في meningitis البكتيري.",
            "Sputum":     "💉 CAP الشديد الذي يحتاج دخول مستشفى.",
            "Urine":      "⚠️ يُحفظ للـ pyelonephritis الشديد — مش للمسالك البسيطة.",
            "Stool":      "💉 Typhoid fever / الحالات الشديدة من Salmonella و Shigella.",
        },
    },
    "Cefixime": {
        "priority": 2, "class": "3rd Gen Cephalosporin (Oral)",
        "note": "✅ (مثل Suprax) خيار فموي قوي للمسالك.",
        "renal_limit": 20, "renal_note": "⚖️ خفض الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["suprax","oroken"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "H. influenzae","Streptococcus spp.","Salmonella spp."],
        "specimen_notes": {
            "Urine":      "✅ خيار فموي قوي للمسالك والـ pyelonephritis الخفيف.",
            "Sputum":     "✅ مناسب لعدوى الجهاز التنفسي الخفيفة.",
            "Stool":      "✅ Step-down بعد Ceftriaxone في Salmonella.",
        },
    },
    "Cefotaxime": {
        "priority": 3, "class": "3rd Gen Cephalosporin",
        "note": "💉 (مثل Cefotax) يستخدم في العدوى الشديدة.",
        "renal_limit": 20, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["cefotax","claforan"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "Streptococcus spp.","H. influenzae"],
        "specimen_notes": {
            "Blood":  "💉 bacteremia والـ sepsis.",
            "CSF":    "💉 meningitis — بديل Ceftriaxone.",
            "Sputum": "💉 CAP الشديد.",
        },
    },
    "Ceftazidime": {
        "priority": 4, "class": "3rd Gen Cephalosporin (Anti-pseudomonal)",
        "note": "🛑 (مثل Fortum) متخصص في جراثيم Pseudomonas.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة ضروري جداً.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["fortum","ceptaz"],
        "organisms": ["Pseudomonas aeruginosa","E. coli",
                      "Klebsiella spp.","Proteus mirabilis"],
        "specimen_notes": {
            "Blood":  "🛑 Pseudomonas bacteremia.",
            "Sputum": "🛑 VAP/HAP مع Pseudomonas.",
            "Urine":  "🛑 UTI معقد مع Pseudomonas.",
        },
    },
    "Cefoperazone": {
        "priority": 4, "class": "3rd Gen Cephalosporin",
        "note": "💉 (مثل Cefobid) فعال للمسالك والمرارة، يطرح كبدياً.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً؛ يطرح عبر الصفراء.",
        "hepatic_caution": True, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["cefobid"],
        "organisms": ["Pseudomonas aeruginosa","E. coli","Klebsiella spp.",
                      "Proteus mirabilis","Staphylococcus aureus"],
        "specimen_notes": {
            "Blood":  "💉 bacteremia في المرضى الكلويين (يطرح كبدياً).",
            "Pus":    "💉 عدوى البطن والمرارة.",
        },
    },
    "Cefepime": {
        "priority": 5, "class": "4th Gen Cephalosporin",
        "note": "🛑 (مثل Maxipime) مضاد قوي جداً للحالات الحرجة.",
        "renal_limit": 50,
        "renal_note": "⚠️ يتطلب تعديل جرعة دقيق لتجنب السمية العصبية.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["maxipime"],
        "organisms": ["Pseudomonas aeruginosa","E. coli","Klebsiella spp.",
                      "Proteus mirabilis","Staphylococcus aureus","Enterococcus faecalis",
                      "Acinetobacter baumannii"],
        "specimen_notes": {
            "Blood":  "🛑 sepsis شديد مع اشتباه Pseudomonas.",
            "Sputum": "🛑 VAP/HAP الحرجة.",
            "CSF":    "🛑 meningitis المعقد في ICU.",
        },
    },
    "Ciprofloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": "⚠️ (مثل Ciprofar) يفضل ادخاره للمسالك المعقدة.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Ciprofloxacin:\n"
            "  الموقف التقليدي: تجنب (FDA Category C).\n"
            "  الأدلة الحديثة (ACCP Journal 2025): الخطر الحقيقي\n"
            "  أقل مما كان متصوراً، ولم تُثبت تشوهات خلقية واضحة\n"
            "  في الدراسات الكبيرة.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)","Warfarin (مضادات التخثر)"],
        "aliases": ["ciprofar","cipro","ciproflox"],
        "organisms": ["E. coli","Klebsiella spp.","Pseudomonas aeruginosa",
                      "Proteus mirabilis","Staphylococcus aureus",
                      "Salmonella spp.","Shigella spp.","Campylobacter jejuni",
                      "Neisseria gonorrhoeae"],
        "specimen_notes": {
            "Urine":      "⚠️ فعال لكن يُحفظ للمسالك المعقدة (Pseudomonas/pyelonephritis).",
            "Blood":      "⚠️ bacteremia في الحالات المتوسطة.",
            "Sputum":     "⚠️ الفلوروكينولون الوحيد الفعال ضد Pseudomonas في الصدر.",
            "Wound Swab": "⚠️ عدوى الجروح المعقدة.",
            "Stool":      "⚠️ Shigellosis والحالات الشديدة من Campylobacter.",
        },
    },
    "Levofloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": "⚠️ (مثل Tavanic) فعال جداً للصدر والمسالك.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Levofloxacin:\n"
            "  فلوروكينولون — يُستخدم بحذر شديد.\n"
            "  بيانات أقل من Ciprofloxacin في الحمل.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["tavanic","levaquin","levoflox"],
        "organisms": ["E. coli","Klebsiella spp.","Pseudomonas aeruginosa",
                      "Staphylococcus aureus","Streptococcus spp.","H. influenzae",
                      "Streptococcus pneumoniae","Mycoplasma spp.","Legionella pneumophila"],
        "specimen_notes": {
            "Sputum": "⚠️ خيار قوي لـ CAP وعدوى الجهاز التنفسي (respiratory quinolone).",
            "Urine":  "⚠️ فعال لكن يُحفظ للحالات المعقدة.",
            "Blood":  "⚠️ bacteremia في الحالات المتوسطة.",
        },
    },
    "Ofloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": "⚠️ (مثل Tarivid) واسع المدى.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Ofloxacin:\n"
            "  فلوروكينولون — يُستخدم بحذر شديد في الحمل.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["tarivid","oflox"],
        "organisms": ["E. coli","Klebsiella spp.","Staphylococcus aureus",
                      "Proteus mirabilis"],
        "specimen_notes": {
            "Urine":  "⚠️ مناسب للمسالك المتوسطة.",
            "Sputum": "⚠️ عدوى الجهاز التنفسي.",
        },
    },
    "Norfloxacin": {
        "priority": 2, "class": "Fluoroquinolone",
        "note": "⚠️ (مثل Noroxin) متخصص في المسالك البولية فقط — لا يُستخدم خارجها.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب عند CrCl < 30.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Norfloxacin:\n"
            "  فلوروكينولون — يُستخدم بحذر شديد في الحمل.\n"
            "  الأدلة الحديثة (ACCP Journal 2025): الخطر\n"
            "  الحقيقي أقل مما كان متصوراً.\n"
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
    "Nitrofurantoin": {
        "priority": 1, "class": "Urinary Antiseptic",
        "note": "🎯 (مثل Macrofuran) الخيار الأول للمسالك البسيطة فقط.",
        "renal_limit": 30, "renal_note": "🚫 ممنوع إذا كانت التصفية < 30 مل/د.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Nitrofurantoin:\n"
            "  آمن في الـ 1st و 2nd trimester.\n"
            "  ممنوع في الـ 3rd trimester (خطر انحلال الدم\n"
            "  للجنين — hemolytic anemia).\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["macrofuran","macrobid","nitrofur"],
        "organisms": ["E. coli","Staphylococcus aureus",
                      "Enterococcus faecalis","Klebsiella spp."],
        "specimen_notes": {
            "Urine": "🎯 مخصص للمسالك البولية البسيطة فقط — لا يُستخدم خارج البول.",
        },
    },
    "Fosfomycin": {
        "priority": 1, "class": "Phosphonic Acid",
        "note": "🎯 (مثل Monuril) خيار مثالي بجرعة واحدة للمسالك.",
        "renal_limit": 10, "renal_note": "⚠️ حذر في القصور الشديد.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Fosfomycin:\n"
            "  بيانات محدودة في الحمل.\n"
            "  يُعتبر آمناً نسبياً لعلاج UTI في الحمل\n"
            "  بجرعة واحدة عند الضرورة.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": [],
        "aliases": ["monuril","fosfocin"],
        "organisms": ["E. coli","Enterococcus faecalis",
                      "Staphylococcus aureus","Klebsiella spp."],
        "specimen_notes": {
            "Urine": "🎯 جرعة واحدة للـ uncomplicated UTI — مثالي.",
        },
    },
    "Gentamicin": {
        "priority": 4, "class": "Aminoglycoside",
        "note": "💉 (مثل Garamycin) يستخدم بحذر شديد - سام للكلى والأذن.",
        "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى ضرورية.",
        "hepatic_caution": False, "aware": "Access", "high_po": False,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — Gentamicin:\n"
            "  سُمية للأذن الجنينية (ototoxicity) — FDA Category D.\n"
            "  يعبر المشيمة ويتراكم في السائل الأمنيوسي.\n"
            "  خطر فقدان السمع الدائم للجنين."
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
        "priority": 4, "class": "Aminoglycoside",
        "note": "💉 (مثل Amikin) فعال جداً ضد السالبات المقاومة.",
        "renal_limit": 60, "renal_note": "⚖️ مراقبة وظائف الكلى.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — Amikacin:\n"
            "  سُمية للأذن الجنينية (ototoxicity) — FDA Category D.\n"
            "  يعبر المشيمة ويتراكم في السائل الأمنيوسي.\n"
            "  خطر فقدان السمع الدائم للجنين."
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
    "Azithromycin": {
        "priority": 2, "class": "Macrolide",
        "note": "✅ (مثل Zithrokan) فعال للجهاز التنفسي والكلاميديا.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["zithrokan","zithromax","azithro"],
        "organisms": ["Staphylococcus aureus","Streptococcus spp.",
                      "H. influenzae","Chlamydia spp.","Mycoplasma spp.",
                      "Salmonella spp.","Shigella spp.","Campylobacter jejuni",
                      "Streptococcus pneumoniae","Legionella pneumophila"],
        "specimen_notes": {
            "Sputum":     "✅ خيار ممتاز لـ CAP والـ atypicals (Mycoplasma/Chlamydia).",
            "Wound Swab": "✅ عدوى الجلد الخفيفة بالموجبات.",
            "Urine":      "⚠️ فعال فقط في Chlamydia urethritis — مش UTI عادي.",
            "Stool":      "✅ الخيار الأول في Campylobacter وبعض حالات Shigella.",
        },
    },
    "Clarithromycin": {
        "priority": 2, "class": "Macrolide",
        "note": "✅ (مثل Klacid) فعال لجرثومة المعدة والصدر.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — Clarithromycin:\n"
            "  ارتبط بتشوهات خلقية في الدراسات الحيوانية\n"
            "  والبشرية — FDA Category C.\n"
            "  البديل الآمن: Azithromycin."
        ),
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["klacid","biaxin"],
        "organisms": ["Staphylococcus aureus","Streptococcus spp.",
                      "H. pylori","H. influenzae","Mycoplasma spp.",
                      "Streptococcus pneumoniae","Legionella pneumophila"],
        "specimen_notes": {
            "Sputum": "✅ CAP والـ atypical pneumonia.",
            "Stool":  "✅ H. pylori eradication therapy (جزء من Triple Therapy).",
        },
    },
    "Trimethoprim/Sulfamethoxazole": {
        "priority": 2, "class": "Sulfonamide",
        "note": "✅ (مثل Septra/Sutrim) فعال للمسالك والجهاز التنفسي.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Access", "high_po": True,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — TMP/SMX (Sutrim/Bactrim):\n"
            "  يثبط حمض الفوليك — خطر Neural Tube Defects\n"
            "  في الـ 1st trimester.\n"
            "  يسبب kernicterus للجنين في الـ 3rd trimester."
        ),
        "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["septra","sutrim","bactrim","co-trimoxazole","tmp-smx"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "Staphylococcus aureus","Streptococcus spp.","Acinetobacter baumannii",
                      "Stenotrophomonas maltophilia"],
        "specimen_notes": {
            "Urine":      "✅ فعال للمسالك البسيطة عند تأكيد الحساسية.",
            "Sputum":     "✅ الجهاز التنفسي والـ PCP prophylaxis — خيار أول لـ Stenotrophomonas.",
            "Wound Swab": "✅ MRSA skin infections (SSTI).",
        },
    },
    "Metronidazole": {
        "priority": 1, "class": "Nitroimidazole",
        "note": "✅ (مثل Flagyl) الخيار الأول للأنيروبيك والطفيليات.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True, "aware": "Access", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Metronidazole:\n"
            "  تجنب في الـ 1st trimester (مخاوف تاريخية).\n"
            "  مقبول ومُستخدم في الـ 2nd و 3rd trimester\n"
            "  بإشراف طبي.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["flagyl","metro","metrogyl"],
        "organisms": ["Anaerobes (لاهوائيات)","Trichomonas vaginalis",
                      "H. pylori","C. difficile","Bacteroides spp.","Giardia lamblia"],
        "specimen_notes": {
            "Pus":        "✅ الخراجات والعدوى المختلطة (anaerobic coverage).",
            "Wound Swab": "✅ العدوى الجراحية التي تشمل اللاهوائيات.",
            "Stool":      "✅ الخيار الأول لـ C. difficile وبعض الطفيليات (Giardia).",
            "Blood":      "✅ sepsis البطن مع اشتباه anaerobic.",
        },
    },
    "Tinidazole": {
        "priority": 2, "class": "Nitroimidazole",
        "note": "✅ (مثل Fasigyn) بديل Metronidazole بجرعة أقل تكراراً.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": True, "aware": "Access", "high_po": True,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — Tinidazole:\n"
            "  ممنوع في الـ 1st trimester.\n"
            "  بيانات أقل من Metronidazole — يُفضل تجنبه\n"
            "  طوال الحمل والاستعاضة بـ Metronidazole."
        ),
        "child_safe": False,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["fasigyn","tini"],
        "organisms": ["Anaerobes (لاهوائيات)","Trichomonas vaginalis",
                      "H. pylori","Giardia lamblia"],
        "specimen_notes": {
            "Stool":      "✅ Giardia و H. pylori.",
            "Wound Swab": "✅ عدوى اللاهوائيات الخفيفة.",
        },
    },
    "Doxycycline": {
        "priority": 2, "class": "Tetracycline",
        "note": "✅ (مثل Vibramycin) فعال للكلاميديا والمايكوبلازما.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً نسبياً.",
        "hepatic_caution": True, "aware": "Watch", "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Doxycycline:\n"
            "  الموقف التقليدي: ممنوع (FDA Category D).\n"
            "  الأدلة الحديثة (ACCP Journal 2025): الخطر\n"
            "  الحقيقي أقل مما كان متصوراً في الاستخدام\n"
            "  القصير المدى — لم تُثبت تشوهات عظمية واضحة\n"
            "  في الدراسات الحديثة الكبيرة.\n"
            "  مع ذلك: لا تزال البيانات غير كافية للتأكيد.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["vibramycin","doxy"],
        "organisms": ["Chlamydia spp.","Mycoplasma spp.",
                      "Staphylococcus aureus","H. influenzae","Rickettsia spp.",
                      "Acinetobacter baumannii","Stenotrophomonas maltophilia",
                      "Legionella pneumophila"],
        "specimen_notes": {
            "Sputum":     "✅ atypical pneumonia (Mycoplasma/Chlamydia/Legionella).",
            "Wound Swab": "✅ MRSA SSTI و Rickettsia.",
            "Blood":      "✅ Rickettsia bacteremia.",
        },
    },
    "Cefuroxime sodium": {
        "priority": 2, "class": "2nd Gen Cephalosporin (IV)",
        "note": "💉 (مثل Zinacef) نفس Cefuroxime لكن IV فقط — للحالات التي تحتاج حقن.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["zinacef","cefuroxime iv","cefuroxime sodium"],
        "organisms": ["E. coli","Klebsiella spp.","H. influenzae",
                      "Staphylococcus aureus","Streptococcus spp.","Proteus mirabilis"],
        "specimen_notes": {
            "Blood":      "💉 bacteremia المتوسطة الشدة.",
            "Sputum":     "💉 CAP الذي يحتاج دخول مستشفى.",
            "Wound Swab": "💉 العدوى الجراحية المتوسطة.",
            "Urine":      "💉 pyelonephritis يحتاج IV.",
        },
    },
    "Ertapenem": {
        "priority": 5, "class": "Carbapenem (non-anti-pseudomonal)",
        "note": "🛑 (مثل Invanz) كاربابينيم بجرعة يومية واحدة — لا يغطي Pseudomonas.",
        "renal_limit": 30, "renal_note": "⚖️ تعديل الجرعة مطلوب عند CrCl < 30.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["invanz","ertapenem"],
        "organisms": ["E. coli","Klebsiella spp.","Proteus mirabilis",
                      "Staphylococcus aureus","Enterococcus faecalis",
                      "Anaerobes (لاهوائيات)"],
        "specimen_notes": {
            "Blood":  "🛑 ESBL bacteremia — يفضل على Meropenem للحفاظ على الكاربابينيم.",
            "Urine":  "🛑 ESBL-producing UTI المعقد فقط.",
            "Pus":    "🛑 عدوى البطن المعقدة بـ ESBL.",
        },
    },
    "Meropenem": {
        "priority": 5, "class": "Carbapenem",
        "note": "🛑 (مثل Meronem) مضاد الملاذ الأخير للمقاومة.",
        "renal_limit": 50, "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False, "aware": "Watch", "high_po": False,
        "preg_status": "Safe", "preg_note": "",
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["meronem","merrem"],
        "organisms": ["Pseudomonas aeruginosa","Klebsiella spp.","E. coli",
                      "Enterococcus faecalis","Staphylococcus aureus","MRSA",
                      "Acinetobacter baumannii"],
        "specimen_notes": {
            "Blood":  "🛑 sepsis شديد — MDR organisms — ICU.",
            "CSF":    "🛑 meningitis المعقد — MDR organisms.",
            "Sputum": "🛑 VAP/HAP بـ MDR organisms.",
            "Urine":  "🛑 UTI المعقد جداً بـ CRE.",
        },
    },
    "Vancomycin": {
        "priority": 5, "class": "Glycopeptide",
        "note": "🛑 خاص بـ MRSA والحالات الحرجة - مراقبة الـ Trough.",
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
                      "Streptococcus spp.","C. difficile","Streptococcus pneumoniae"],
        "specimen_notes": {
            "Blood":      "🛑 MRSA bacteremia.",
            "CSF":        "🛑 MRSA meningitis.",
            "Sputum":     "🛑 MRSA pneumonia في ICU.",
            "Wound Swab": "🛑 MRSA wound infection.",
            "Stool":      "🛑 C. difficile الشديد (Oral Vancomycin فقط).",
        },
    },
    "Linezolid": {
        "priority": 5, "class": "Oxazolidinone",
        "note": "🛑 (مثل Averozolid) للموجبات المقاومة (MRSA/VRE) فقط.",
        "renal_limit": 0, "renal_note": "🟢 آمن كلوياً.",
        "hepatic_caution": False, "aware": "Reserve", "high_po": True,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — Linezolid:\n"
            "  بيانات غير كافية في الحمل البشري.\n"
            "  أثبت سُمية جنينية في الحيوانات.\n"
            "  يُستخدم فقط عند انعدام البدائل الأخرى."
        ),
        "child_safe": True,
        "interacts_with": ["SSRI (أدوية الاكتئاب)"],
        "aliases": ["averozolid","zyvox"],
        "organisms": ["MRSA","Staphylococcus aureus","Enterococcus faecalis",
                      "VRE","Streptococcus spp."],
        "specimen_notes": {
            "Blood":      "🛑 VRE/MRSA bacteremia.",
            "Sputum":     "🛑 MRSA pneumonia — تركيز رئوي ممتاز.",
            "Wound Swab": "🛑 MRSA/VRE wound infection.",
            "CSF":        "🛑 اختراق ممتاز للـ CNS.",
        },
    },
    "Colistin": {
        "priority": 6, "class": "Polymyxin",
        "note": "🔴 الملاذ الأخير (Reserve) للبكتيريا سالبة الجرام شديدة المقاومة (MDR).",
        "renal_limit": 80, "renal_note": "⚖️ سام جداً للكلى، تعديل الجرعة والمراقبة حتمية.",
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
    # ─── مضافة جديدة ─────────────────────────────────────────────────────
    "Fidaxomicin": {
        "priority": 3, "class": "Macrocyclic Antibiotic",
        "note": (
            "🎯 (مثل Dificlir) خاص بـ C. difficile — معدل انتكاس أقل من Vancomycin. "
            "يُستخدم في الحالات المتكررة أو الشديدة."
        ),
        "renal_limit": 0,
        "renal_note": "🟢 آمن كلوياً — امتصاص فموي ضعيف جداً (تأثير محلي).",
        "hepatic_caution": False,
        "aware": "Watch",
        "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Fidaxomicin:\n"
            "  بيانات محدودة في الحمل — يُفضل Oral Vancomycin كبديل.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": [],
        "aliases": ["dificlir","fidaxo"],
        "organisms": ["C. difficile"],
        "specimen_notes": {
            "Stool": "🎯 الخيار المفضل للـ C. difficile المتكرر أو الشديد (IDSA/ESCMID 2021).",
        },
    },
    "Rifaximin": {
        "priority": 2, "class": "Rifamycin (Non-absorbable)",
        "note": (
            "🎯 (مثل Normix/Xifaxan) مضاد فموي غير ممتص — "
            "خاص بالأمعاء. يُستخدم للوقاية من traveler's diarrhea وعلاج IBS-D."
        ),
        "renal_limit": 0,
        "renal_note": "🟢 آمن كلوياً — امتصاص جهازي أقل من 0.4%.",
        "hepatic_caution": False,
        "aware": "Watch",
        "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Rifaximin:\n"
            "  بيانات محدودة في الحمل — يُفضل تجنبه.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": [],
        "aliases": ["normix","xifaxan","rifaximin"],
        "organisms": ["E. coli","Salmonella spp.","Shigella spp."],
        "specimen_notes": {
            "Stool": "🎯 Traveler's diarrhea — عدوى الأمعاء البسيطة والوقاية.",
        },
    },
    "TMP/SMX (High-dose)": {
        "priority": 2, "class": "Sulfonamide",
        "note": (
            "🎯 TMP/SMX بجرعة عالية — الخيار الأول لـ Stenotrophomonas maltophilia. "
            "نفس الدواء (Sutrim/Bactrim) لكن بجرعة مختلفة."
        ),
        "renal_limit": 30,
        "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": False,
        "aware": "Watch",
        "high_po": True,
        "preg_status": "Banned",
        "preg_note": (
            "ممنوع في الحمل — TMP/SMX:\n"
            "  يثبط حمض الفوليك — خطر Neural Tube Defects.\n"
            "  يسبب kernicterus في الـ 3rd trimester."
        ),
        "child_safe": True,
        "interacts_with": ["Warfarin (مضادات التخثر)"],
        "aliases": ["tmp-smx high dose","bactrim ds","co-trimoxazole hd"],
        "organisms": ["Stenotrophomonas maltophilia"],
        "specimen_notes": {
            "Sputum": "🎯 الخيار الأول لـ Stenotrophomonas — VAP/HAP.",
            "Blood":  "🎯 Stenotrophomonas bacteremia.",
        },
    },
    "Levofloxacin (High-dose)": {
        "priority": 3, "class": "Fluoroquinolone",
        "note": (
            "⚠️ Levofloxacin بجرعة 750mg — بديل TMP/SMX "
            "لـ Stenotrophomonas maltophilia عند وجود حساسية أو تعذر الاستخدام."
        ),
        "renal_limit": 50,
        "renal_note": "⚖️ تعديل الجرعة مطلوب.",
        "hepatic_caution": True,
        "aware": "Watch",
        "high_po": True,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Levofloxacin:\n"
            "  فلوروكينولون — يُستخدم بحذر شديد.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": False,
        "interacts_with": ["Antacids (مضادات الحموضة)"],
        "aliases": ["levaquin hd","levoflox 750"],
        "organisms": ["Stenotrophomonas maltophilia"],
        "specimen_notes": {
            "Sputum": "⚠️ بديل TMP/SMX لـ Stenotrophomonas.",
            "Blood":  "⚠️ Stenotrophomonas bacteremia عند تعذر TMP/SMX.",
        },
    },
    "Ceftazidime-Avibactam": {
        "priority": 6, "class": "5th Gen Cephalosporin + Beta-lactamase Inhibitor",
        "note": (
            "🔴 (مثل Avycaz) خيار متخصص لـ KPC وOXA-48 "
            "وبعض NDM. ملاذ أخير لـ CRE وXDR Pseudomonas."
        ),
        "renal_limit": 50,
        "renal_note": "⚖️ تعديل الجرعة حتمي — يُطرح كلياً.",
        "hepatic_caution": False,
        "aware": "Reserve",
        "high_po": False,
        "preg_status": "Warn",
        "preg_note": (
            "تحذير حمل — Ceftazidime-Avibactam:\n"
            "  بيانات غير كافية في الحمل البشري.\n"
            "  يُستخدم فقط عند الضرورة القصوى.\n"
            "  >>> القرار النهائي للطبيب المعالج حصراً. <<<"
        ),
        "child_safe": True,
        "interacts_with": [],
        "aliases": ["avycaz","caz-avi","ceftazidime avibactam"],
        "organisms": ["Klebsiella spp.","Pseudomonas aeruginosa","E. coli"],
        "specimen_notes": {
            "Blood":  "🔴 CRE/KPC bacteremia — ملاذ أخير.",
            "Sputum": "🔴 XDR Pseudomonas في ICU.",
            "Urine":  "🔴 UTI بـ CRE عند فشل كل البدائل.",
        },
    },
}

# ==========================================
# 🦠 Organism → First-line / Avoid mapping
# ==========================================
ORGANISM_PROFILE = {
    "E. coli": {
        "first_line": [
            "Nitrofurantoin",
            "Fosfomycin",
            "Trimethoprim/Sulfamethoxazole",
            "Amoxicillin + Clavulanic acid",
        ],
        "second_line": [
            "Cefuroxime",
            "Cefuroxime sodium",
            "Cefixime",
            "Norfloxacin",
            "Ciprofloxacin",
        ],
        "third_line": [
            "Ertapenem",
            "Meropenem",
        ],
        "avoid": [],
        "urine_note": (
            "Norfloxacin: مخصص للمسالك البولية فقط (لا يصل لتركيز علاجي خارج البول).\n"
            "Ertapenem: يُحفظ للـ ESBL-producing E. coli فقط — لا يُستخدم روتينياً."
        ),
        "specimen_context": {
            "Blood":      "🔬 الأكثر شيوعاً في bacteremia الجهاز البولي والبطن.",
            "Sputum":     "⚠️ E. coli في البلغم — نادر، يشير لـ aspiration أو HAP.",
            "Wound Swab": "🔬 شائع في عدوى الجروح الجراحية والحروق.",
            "Pus":        "🔬 شائع في خراجات البطن وعدوى البطن.",
            "Stool":      "🔬 ETEC و EPEC — أسباب إسهال المسافرين.",
        },
        "note": "🔬 الأكثر شيوعاً في مزارع البول.",
    },
    "Klebsiella spp.": {
        "first_line": [
            "Amoxicillin + Clavulanic acid",
            "Cefuroxime",
            "Cefixime",
        ],
        "second_line": [
            "Cefuroxime sodium",
            "Norfloxacin",
            "Ciprofloxacin",
            "Piperacillin + Tazobactam",
            "Ceftriaxone",
        ],
        "third_line": [
            "Ertapenem",
            "Meropenem",
        ],
        "avoid": ["Ampicillin"],
        "urine_note": (
            "Ertapenem: الخيار الأول لـ ESBL-producing Klebsiella\n"
            "  وفق IDSA 2023 — يفضل على Meropenem للحفاظ على الكاربابينيم.\n"
            "Norfloxacin: مخصص للمسالك فقط — لا يُستخدم في الحالات الشديدة."
        ),
        "specimen_context": {
            "Blood":      "🔬 Klebsiella bacteremia — خطر حقيقي خصوصاً في الكبد.",
            "Sputum":     "🔬 HAP وعدوى الجهاز التنفسي في المستشفى.",
            "Wound Swab": "🔬 عدوى الجروح الجراحية.",
            "Pus":        "🔬 خراجات الكبد والبطن.",
            "Urine":      "🔬 الثاني الأكثر شيوعاً في مزارع البول.",
        },
        "note": "🔬 مقاومة لبعض البيتا-لاكتام بطبيعتها — تحقق من ESBL.",
    },
    "Pseudomonas aeruginosa": {
        "first_line": [
            "Piperacillin + Tazobactam",
            "Ceftazidime",
            "Ciprofloxacin",
        ],
        "second_line": [
            "Cefepime",
            "Cefoperazone + Sulbactam",
            "Meropenem",
            "Amikacin",
        ],
        "third_line": ["Colistin","Ceftazidime-Avibactam"],
        "avoid": [
            "Nitrofurantoin",
            "Fosfomycin",
            "Trimethoprim/Sulfamethoxazole",
            "Cephalexin","Cefadroxil","Cefaclor",
            "Norfloxacin",
            "Cefuroxime sodium",
            "Ertapenem",
        ],
        "urine_note": (
            "Ertapenem: ممنوع لـ Pseudomonas — لا نشاط (EUCAST/EAU).\n"
            "Norfloxacin: تركيز غير كافٍ ضد Pseudomonas.\n"
            "Ciprofloxacin هو الفلوروكينولون الوحيد الفعال ضد Pseudomonas."
        ),
        "specimen_context": {
            "Blood":      "🔴 Pseudomonas bacteremia — mortality عالية — ICU غالباً.",
            "Sputum":     "🔴 VAP/HAP الأكثر خطورة — يحتاج anti-pseudomonal.",
            "Wound Swab": "🔴 شائع في حروق والجروح المزمنة.",
            "Urine":      "🔴 UTI المعقد — كاتيتر أو مضادات حيوية سابقة.",
        },
        "note": "🔬 جرثومة انتهازية — تحتاج مضادات anti-pseudomonal متخصصة.",
    },
    "Acinetobacter baumannii": {
        "first_line": [
            "Ampicillin/Sulbactam",
            "Cefoperazone + Sulbactam",
        ],
        "second_line": ["Meropenem","Amikacin","Trimethoprim/Sulfamethoxazole","Doxycycline"],
        "third_line": ["Colistin"],
        "avoid": [
            "Ertapenem",
            "Cephalexin", "Cefuroxime", "Ceftriaxone",
            "Azithromycin", "Clarithromycin",
            "Nitrofurantoin", "Fosfomycin",
        ],
        "specimen_context": {
            "Blood":      "🔴 Acinetobacter bacteremia — ICU — MDR غالباً.",
            "Sputum":     "🔴 VAP الأكثر شيوعاً في ICU — خطر جداً.",
            "Wound Swab": "🔴 عدوى الحروق والجروح الجراحية الكبيرة.",
        },
        "note": "🔴 بكتيريا رعاية حرجة شديدة المقاومة (MDR). Ampicillin/Sulbactam أو Cefoperazone/Sulbactam بجرعات عالية هو الأساس (IDSA AMR Guidance).",
    },
    "Staphylococcus aureus": {
        "first_line": [
            "Cephalexin",
            "Cefadroxil",
            "Amoxicillin + Clavulanic acid",
        ],
        "second_line": [
            "Cefuroxime sodium",
            "Azithromycin",
            "Doxycycline",
        ],
        "third_line": [],
        "avoid": [],
        "urine_note": (
            "Norfloxacin: نشاط ضعيف ضد S. aureus في مزارع البول — ليس خياراً مثالياً.\n"
            "تحقق من MRSA — إذا MRSA: Vancomycin أو Linezolid فقط."
        ),
        "specimen_context": {
            "Blood":      "🔬 تحقق من MRSA فوراً — endocarditis خطر حقيقي.",
            "Sputum":     "🔬 pneumonia بعد الإنفلونزا أو في ICU.",
            "Wound Swab": "🔬 الأكثر شيوعاً في عدوى الجروح والجلد.",
            "Pus":        "🔬 خراجات الجلد والأنسجة الرخوة.",
            "Urine":      "⚠️ S. aureus في البول — احتمال hematogenous seeding — راجع Blood culture.",
        },
        "note": "🔬 تحقق من MRSA — قد يحتاج Vancomycin.",
    },
    "MRSA": {
        "first_line": ["Vancomycin","Linezolid"],
        "second_line": ["Trimethoprim/Sulfamethoxazole","Doxycycline"],
        "third_line": [],
        "avoid": [
            "Cephalexin","Cefadroxil","Cefaclor",
            "Cefuroxime","Cefuroxime sodium","Ceftriaxone",
            "Amoxicillin + Clavulanic acid","Ampicillin/Sulbactam",
            "Piperacillin + Tazobactam",
            "Ertapenem",
        ],
        "urine_note": (
            "جميع البيتا-لاكتام بما فيها Cefuroxime sodium وErtapenem\n"
            "  لا تعمل على MRSA (mecA gene — PBP2a resistance)."
        ),
        "specimen_context": {
            "Blood":      "🔴 MRSA bacteremia — emergency — ابدأ Vancomycin فوراً.",
            "Sputum":     "🔴 MRSA pneumonia — خطر عالي في ICU.",
            "Wound Swab": "🔴 MRSA SSTI — شائع في المجتمع (CA-MRSA).",
            "Pus":        "🔴 MRSA abscess — drainage + Vancomycin.",
            "CSF":        "🔴 MRSA meningitis — نادر لكن خطر جداً.",
        },
        "note": "🔴 مقاوم لجميع البيتا-لاكتام! — Vancomycin أو Linezolid فقط.",
    },
    "Proteus mirabilis": {
        "first_line": [
            "Amoxicillin + Clavulanic acid",
            "Cefuroxime",
            "Cefixime",
        ],
        "second_line": [
            "Cefuroxime sodium",
            "Norfloxacin",
            "Ciprofloxacin",
            "Trimethoprim/Sulfamethoxazole",
        ],
        "third_line": [
            "Ertapenem",
        ],
        "avoid": [
            "Nitrofurantoin",
            "Tetracyclines",
            "Colistin",
        ],
        "urine_note": (
            "Nitrofurantoin: مقاوم طبيعياً لـ Proteus (intrinsic) — EUCAST.\n"
            "Norfloxacin: فعال في UTI فقط — لا يُستخدم في bacteremia أو pyelonephritis."
        ),
        "specimen_context": {
            "Urine":      "🔬 شائع في UTI — يرفع الـ pH (urease-producing).",
            "Wound Swab": "🔬 عدوى الجروح المزمنة والقدم السكري.",
            "Blood":      "⚠️ Proteus bacteremia — غالباً مصدره الجهاز البولي.",
        },
        "note": "🔬 مقاوم طبيعياً لـ Nitrofurantoin — لا تستخدمه أبداً.",
    },
    "Enterococcus faecalis": {
        "first_line": [
            "Amoxicillin + Clavulanic acid",
            "Fosfomycin",
            "Nitrofurantoin",
        ],
        "second_line": [
            "Ampicillin/Sulbactam",
            "Vancomycin",
            "Linezolid",
        ],
        "third_line": [],
        "avoid": [
            "Cephalosporins (كل الجيل)",
            "Trimethoprim/Sulfamethoxazole",
            "Cefuroxime sodium",
            "Ertapenem",
            "Norfloxacin",
        ],
        "urine_note": (
            "Ertapenem وCefuroxime sodium: لا نشاط ضد Enterococcus (EUCAST).\n"
            "Norfloxacin: نشاط متغير وغير موثوق — تجنب.\n"
            "جميع السيفالوسبورين مقاومة طبيعياً لـ Enterococcus."
        ),
        "specimen_context": {
            "Urine":      "🔬 شائع في UTI خصوصاً الكاتيتر.",
            "Blood":      "⚠️ Enterococcus bacteremia — خطر endocarditis.",
            "Wound Swab": "⚠️ عدوى البطن والجروح الجراحية المختلطة.",
        },
        "note": "🔬 مقاوم طبيعياً للسيفالوسبورين وErtapenem — Amoxicillin هو الأساس.",
    },
    # ─── بكتيريا الـ Stool ─────────────────────────────────────────────
    "Salmonella spp.": {
        "first_line": [
            "Ceftriaxone",
            "Azithromycin",
            "Ciprofloxacin",
        ],
        "second_line": [
            "Trimethoprim/Sulfamethoxazole",
            "Cefixime",
        ],
        "third_line": [],
        "avoid": [
            "Nitrofurantoin",
            "Fosfomycin",
            "Cephalexin",
            "Cefadroxil",
            "Cefaclor",
            "Cefuroxime",
            "Metronidazole",
            "Doxycycline",
        ],
        "urine_note": "",
        "specimen_context": {
            "Stool":  "🔬 Salmonella gastroenteritis — العلاج فقط للحالات الشديدة أو المعرضين للخطر.",
            "Blood":  "🔬 Typhoid fever / enteric fever — Ceftriaxone أو Azithromycin.",
        },
        "note": "🔬 العلاج بالمضادات الحيوية مخصص للحالات الشديدة أو الحمى التيفودية فقط.",
    },
    "Shigella spp.": {
        "first_line": [
            "Azithromycin",
            "Ciprofloxacin",
            "Ceftriaxone",
        ],
        "second_line": [
            "Trimethoprim/Sulfamethoxazole",
        ],
        "third_line": [],
        "avoid": [
            "Nitrofurantoin",
            "Fosfomycin",
            "Amoxicillin + Clavulanic acid",
            "Metronidazole",
        ],
        "urine_note": "",
        "specimen_context": {
            "Stool":  "🔬 Shigellosis — العلاج بالمضادات الحيوية يقلل الأعراض ويمنع انتشار المرض.",
            "Blood":  "🔬 نادراً ما يصل للدم إلا في الحالات الشديدة.",
        },
        "note": "🔬 تعالج فقط الحالات الوخيمة أو أثناء الأوبئة؛ مقاومة عالية لـ TMP/SMX في بعض المناطق.",
    },
    "Campylobacter jejuni": {
        "first_line": [
            "Azithromycin",
        ],
        "second_line": [
            "Ciprofloxacin",
        ],
        "third_line": [],
        "avoid": [
            "Trimethoprim/Sulfamethoxazole",
            "Penicillins",
            "Cephalosporins",
            "Nitrofurantoin",
            "Fosfomycin",
        ],
        "urine_note": "",
        "specimen_context": {
            "Stool":  "🔬 أشهر أسباب الإسهال البكتيري — غالباً محدود ذاتياً.",
            "Blood":  "🔬 Bacteremia نادر الحدوث في نقص المناعة.",
        },
        "note": "🔬 معظم الحالات لا تحتاج مضادات حيوية؛ Azithromycin هو الخيار الأول عند الحاجة.",
    },
    "H. pylori": {
        "first_line": [
            "Clarithromycin",
            "Metronidazole",
            "Amoxicillin + Clavulanic acid",
        ],
        "second_line": [
            "Tinidazole",
            "Levofloxacin",
            "Tetracycline",
        ],
        "third_line": ["Rifaximin"],
        "avoid": [
            "Nitrofurantoin",
            "Fosfomycin",
            "Cephalosporins",
        ],
        "urine_note": "",
        "specimen_context": {
            "Stool":       "🔬 H. pylori Stool Antigen Test — يؤكد الإصابة والشفاء بعد العلاج.",
            "Blood":       "⚠️ H. pylori لا يُعزل من الدم — الاختبار هنا serological.",
        },
        "note": "🔬 يحتاج Triple أو Quadruple therapy — لا يُعطى مضاد واحد أبداً.",
    },
    "C. difficile": {
        "first_line": [
            "Vancomycin",
            "Fidaxomicin",
        ],
        "second_line": [
            "Metronidazole",
        ],
        "third_line": [],
        "avoid": [
            "Cephalosporins",
            "Fluoroquinolones",
            "Clindamycin",
            "Trimethoprim/Sulfamethoxazole",
        ],
        "urine_note": "",
        "specimen_context": {
            "Stool": "🔬 C. difficile — أهم سبب للإسهال المرتبط بالمضادات الحيوية. GDH+Toxin أو PCR.",
        },
        "note": "🔬 Oral Vancomycin أو Fidaxomicin هو الخيار الأول (IDSA 2021). Metronidazole بديل للحالات الخفيفة فقط.",
    },
    "Giardia lamblia": {
        "first_line": [
            "Metronidazole",
            "Tinidazole",
        ],
        "second_line": [],
        "third_line": [],
        "avoid": [
            "Cephalosporins",
            "Fluoroquinolones",
            "Aminoglycosides",
        ],
        "urine_note": "",
        "specimen_context": {
            "Stool": "🔬 Giardiasis — إسهال مزمن دهني + انتفاخ. يُشخص بـ Stool Antigen أو Microscopy.",
        },
        "note": "🔬 Metronidazole أو Tinidazole (جرعة واحدة) — الأكثر فاعلية والأرخص.",
    },
    # ─── بكتيريا جهاز تنفسي مهمة ──────────────────────────────────────
    "Streptococcus pneumoniae": {
        "first_line": [
            "Amoxicillin + Clavulanic acid",
            "Ceftriaxone",
            "Levofloxacin",
        ],
        "second_line": [
            "Azithromycin",
            "Clarithromycin",
            "Cefuroxime",
        ],
        "third_line": ["Vancomycin", "Linezolid"],
        "avoid": [],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔬 السبب الأول لـ CAP — تحقق من مقاومة Penicillin.",
            "Blood":  "🔬 Pneumococcal bacteremia — خطر حقيقي في المسنين والمناعة.",
            "CSF":    "🔬 السبب الأول لـ bacterial meningitis في البالغين.",
        },
        "note": "🔬 السبب الأول لـ CAP والـ meningitis البالغين. تحقق من MIC للـ Penicillin.",
    },
    "H. influenzae": {
        "first_line": [
            "Amoxicillin + Clavulanic acid",
            "Cefuroxime",
            "Ceftriaxone",
        ],
        "second_line": [
            "Azithromycin",
            "Levofloxacin",
            "Trimethoprim/Sulfamethoxazole",
        ],
        "third_line": [],
        "avoid": ["Ampicillin (alone — beta-lactamase common)"],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔬 شائع في COPD exacerbation و CAP وعدوى الأذن الوسطى.",
            "Blood":  "⚠️ H. influenzae bacteremia — نادر بعد التطعيم.",
            "CSF":    "⚠️ H. influenzae meningitis — نادر جداً الآن (تطعيم Hib).",
        },
        "note": "🔬 شائع في التهاب القصبات والـ COPD. 30% ينتجون beta-lactamase — Amoxicillin/Clavulanate مفضل.",
    },
    "Legionella pneumophila": {
        "first_line": [
            "Levofloxacin",
            "Azithromycin",
        ],
        "second_line": [
            "Doxycycline",
            "Clarithromycin",
        ],
        "third_line": [],
        "avoid": [
            "Beta-lactams (alone)",
            "Aminoglycosides",
            "Cephalosporins (alone)",
        ],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔬 Legionella — CAP الشديد، خاصةً في الفنادق أو مكيفات الهواء.",
            "Blood":  "⚠️ Bacteremia نادر — التشخيص بـ Urine Antigen أو PCR.",
        },
        "note": "🔬 Legionellosis — Levofloxacin هو الخيار الأول. لا يُعزل بالزراعة العادية — يحتاج وسط BCYE.",
    },
    "Mycoplasma spp.": {
        "first_line": [
            "Azithromycin",
            "Doxycycline",
        ],
        "second_line": [
            "Levofloxacin",
            "Clarithromycin",
        ],
        "third_line": [],
        "avoid": [
            "Beta-lactams",
            "Cephalosporins",
            "Vancomycin",
            "Aminoglycosides",
        ],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔬 Atypical pneumonia — Walking pneumonia — خاصةً في الشباب.",
        },
        "note": "🔬 لا جدار خلوي — كل البيتا-لاكتام غير فعالة. يُشخص بـ PCR أو Serology.",
    },
    "Chlamydia spp.": {
        "first_line": [
            "Doxycycline",
            "Azithromycin",
        ],
        "second_line": [
            "Levofloxacin",
        ],
        "third_line": [],
        "avoid": [
            "Beta-lactams",
            "Aminoglycosides",
            "Cephalosporins",
        ],
        "urine_note": "Azithromycin: جرعة واحدة 1g لـ Chlamydia urethritis.",
        "specimen_context": {
            "Sputum": "🔬 C. pneumoniae — سبب لـ atypical CAP.",
            "Urine":  "🔬 C. trachomatis — STI شائع، يُشخص بـ NAAT.",
        },
        "note": "🔬 لا جدار خلوي — البيتا-لاكتام غير فعالة. Doxycycline 7 أيام أو Azithromycin جرعة واحدة.",
    },
    # ─── بكتيريا MDR مهمة ──────────────────────────────────────────────
    "Stenotrophomonas maltophilia": {
        "first_line": [
            "Trimethoprim/Sulfamethoxazole",
            "TMP/SMX (High-dose)",
        ],
        "second_line": [
            "Levofloxacin",
            "Levofloxacin (High-dose)",
            "Doxycycline",
        ],
        "third_line": ["Ceftazidime-Avibactam"],
        "avoid": [
            "Carbapenems",
            "Ertapenem",
            "Meropenem",
            "Aminoglycosides",
            "Ceftriaxone",
            "Cefepime",
        ],
        "urine_note": "",
        "specimen_context": {
            "Sputum": "🔴 شائع في VAP/HAP في ICU — خاصةً بعد علاج طويل بالكاربابينيم.",
            "Blood":  "🔴 Stenotrophomonas bacteremia — نادر لكن خطر في المناعة الضعيفة.",
        },
        "note": "🔴 مقاومة طبيعية للكاربابينيم! TMP/SMX هو الخيار الأول. كثيراً ما ينتقى بعد علاج Meropenem.",
    },
    "Neisseria gonorrhoeae": {
        "first_line": [
            "Ceftriaxone",
        ],
        "second_line": [
            "Azithromycin",
            "Ciprofloxacin",
        ],
        "third_line": [],
        "avoid": [
            "Penicillin (alone — high resistance)",
            "Tetracyclines (alone)",
        ],
        "urine_note": "Ceftriaxone IM جرعة واحدة 500mg هو الخيار الأول (CDC/ECDC 2021).",
        "specimen_context": {
            "Urine":      "🔬 يُشخص بـ NAAT — Ceftriaxone IM جرعة واحدة.",
            "Wound Swab": "🔬 عدوى المفاصل (septic arthritis) — نادر.",
            "Blood":      "⚠️ Gonococcal bacteremia — نادر جداً.",
        },
        "note": "🔬 Ceftriaxone IM جرعة واحدة هو المعيار الذهبي. مقاومة عالية لكثير من المضادات.",
    },
    "Anaerobes (لاهوائيات)": {
        "first_line": [
            "Metronidazole",
            "Amoxicillin + Clavulanic acid",
        ],
        "second_line": [
            "Piperacillin + Tazobactam",
            "Meropenem",
            "Ampicillin/Sulbactam",
        ],
        "third_line": [],
        "avoid": [
            "Aminoglycosides",
            "Fluoroquinolones (ضعيف للاهوائيات)",
            "Nitrofurantoin",
        ],
        "urine_note": "",
        "specimen_context": {
            "Pus":        "🔬 الخراجات داخل البطن وتحت الحجاب — Metronidazole ضروري.",
            "Wound Swab": "🔬 العدوى الجراحية بعد عمليات الأمعاء — Metronidazole دائماً.",
            "Blood":      "🔬 Bacteremia اللاهوائيات — مصدره البطن غالباً.",
        },
        "note": "🔬 Metronidazole هو الخيار الأول لكل اللاهوائيات. يُضاف عادةً للتغطية المختلطة.",
    },
}

# ─── خريطة العينات والبكتيريا المرتبطة بها ──────────────────────────
SPECIMEN_ORGANISM_MAP = {
    "Urine":      [
        "E. coli","Klebsiella spp.","Proteus mirabilis",
        "Enterococcus faecalis","Staphylococcus aureus","MRSA",
        "Pseudomonas aeruginosa","Acinetobacter baumannii",
        "Neisseria gonorrhoeae","Chlamydia spp.",
    ],
    "Blood":      [
        "E. coli","Klebsiella spp.","Staphylococcus aureus","MRSA",
        "Pseudomonas aeruginosa","Acinetobacter baumannii",
        "Streptococcus pneumoniae","Enterococcus faecalis",
        "Salmonella spp.","Proteus mirabilis","Anaerobes (لاهوائيات)",
        "Stenotrophomonas maltophilia",
    ],
    "Sputum":     [
        "Streptococcus pneumoniae","H. influenzae","Klebsiella spp.",
        "Pseudomonas aeruginosa","Acinetobacter baumannii","MRSA",
        "Staphylococcus aureus","E. coli","Legionella pneumophila",
        "Mycoplasma spp.","Chlamydia spp.","Stenotrophomonas maltophilia",
    ],
    "Wound Swab": [
        "Staphylococcus aureus","MRSA","E. coli","Klebsiella spp.",
        "Pseudomonas aeruginosa","Proteus mirabilis","Acinetobacter baumannii",
        "Enterococcus faecalis","Anaerobes (لاهوائيات)","Streptococcus spp.",
    ],
    "Pus":        [
        "Staphylococcus aureus","MRSA","E. coli","Klebsiella spp.",
        "Pseudomonas aeruginosa","Acinetobacter baumannii",
        "Anaerobes (لاهوائيات)","Enterococcus faecalis","Proteus mirabilis",
    ],
    "Stool":      [
        "Salmonella spp.","Shigella spp.","Campylobacter jejuni",
        "H. pylori","C. difficile","Giardia lamblia","E. coli",
    ],
    "CSF":        [
        "Streptococcus pneumoniae","H. influenzae","MRSA",
        "Staphylococcus aureus","E. coli","Klebsiella spp.",
        "Listeria monocytogenes",
    ],
}

# قائمة كل البكتيريا (للـ OCR وللعرض العام)
BACTERIA_TYPES = list(ORGANISM_PROFILE.keys())

SPECIMEN_TYPES = ["Urine","Blood","Sputum","Wound Swab","Pus","Stool","CSF"]
COMMON_MEDS    = ["Antacids (مضادات الحموضة)","Warfarin (مضادات التخثر)",
                  "NSAIDs (مسكنات الألم)","SSRI (أدوية الاكتئاب)"]
AWARE_COLORS   = {"Access":"🟢 Access","Watch":"🟡 Watch","Reserve":"🔴 Reserve"}

# ==========================================
# 🔍 OCR + Fuzzy Matching
# ==========================================
def fuzzy_match(word, target):
    w, t = word.lower(), target.lower()
    if t in w or w in t:
        return 100
    ratio = SequenceMatcher(None, w, t).ratio() * 100
    return ratio

def extract_all_data(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img        = cv2.imdecode(file_bytes, 1)
    gray       = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh  = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    full_text  = pytesseract.image_to_string(thresh, config='--psm 6')
    text_lower = full_text.lower()

    age_match      = re.search(r"(\d+)\s*[Yy]ears?", full_text)
    detected_age   = age_match.group(1) if age_match else "25"
    detected_sex   = "Female" if "female" in text_lower else "Male"

    detected_specimen = "Urine"
    for s in SPECIMEN_TYPES:
        if s.lower() in text_lower:
            detected_specimen = s; break

    detected_organism = "E. coli"
    organism_counts = {}
    for b in BACTERIA_TYPES:
        count = text_lower.count(b.lower())
        if count > 0:
            organism_counts[b] = count
    if organism_counts:
        detected_organism = max(organism_counts, key=organism_counts.get)

    sir_map = {}
    for line in full_text.splitlines():
        ll = line.lower().strip()
        result = None
        if re.search(r'\b(s|sensitive|sens)\b', ll):    result = "S"
        elif re.search(r'\b(r|resistant|resist)\b', ll): result = "R"
        elif re.search(r'\b(i|intermediate|inter)\b', ll): result = "I"
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
        if matched:
            detected_drugs.append(abx_name)

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
        "  - لا يصل لتركيز علاجي كافٍ في البول → لا يقتل الجرثومة.\n"
        "  - يتراكم في الدم → خطر سُمية رئوية وعصبية.\n"
        "  السبب الطبي: الدواء يُطرح كلياً عبر الترشيح الكبيبي."
    ),
}

CHILD_BAN_REASONS = {
    "fluoroquinolone": (
        "الفلوروكينولونات (Cipro/Levo/Oflox/Norflox) تؤثر على غضاريف\n"
        "  النمو (cartilage) في الأطفال والمراهقين < 18 سنة.\n"
        "  أثبتت الدراسات الحيوانية تلف مفصلي دائم.\n"
        "  تُستخدم فقط عند انعدام البدائل الأخرى تماماً."
    ),
    "tetracycline": (
        "Doxycycline والتتراسيكلينات تترسب في العظام والأسنان\n"
        "  النامية → تلوين دائم للأسنان وتثبيط نمو العظام.\n"
        "  ممنوعة < 8 سنوات بشكل مطلق (AAP)، وتُتجنب حتى 18 سنة."
    ),
}

def generate_report(age, sex, weight, cl_cr, is_renal, is_preg, is_hepatic,
                    allowed, warned, banned, preg_warn_items,
                    organism, specimen, interactions, sir_map):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
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
        if spec_ctx:
            r.append(f"  Specimen Context: {spec_ctx}")
        r.append(f"  First-line (guidelines): {', '.join(op['first_line'])}")
        if op["avoid"]:
            r.append(f"  Avoid (intrinsic resistance): {', '.join(op['avoid'])}")

    if sir_map:
        r.append(f"\nSENSITIVITY RESULTS (extracted from image):")
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
            r.append(f"  Route     : {'Oral (PO)' if item['high_po'] else 'IV only'}")
            spec_note = item.get("specimen_notes", {}).get(specimen, "")
            if spec_note:
                r.append(f"  Note      : {item['note']}  |  [{specimen}]: {spec_note}")
            else:
                r.append(f"  Note      : {item['note']}")
            if is_renal:
                r.append(f"  Renal     : {item['renal_note']}")
            if is_preg and item["preg_status"] == "Warn":
                r.append(f"  Pregnancy : {item['preg_note'].splitlines()[0]}")
    else:
        r.append("  No recommended options after applying all restrictions.")

    if warned:
        r.append(f"\n{SEP}")
        r.append("  DOSE ADJUSTMENT REQUIRED")
        r.append(f"  (Antibiotic is still effective but needs modified dosing)")
        r.append(SEP)
        r.append(f"\n  WHY dose adjustment is needed in renal impairment:")
        r.append(f"  Most antibiotics are eliminated by the kidneys.")
        r.append(f"  When kidney function is reduced (low CrCl), the drug")
        r.append(f"  accumulates in the blood → risk of toxicity.")
        r.append(f"  Reducing the dose or extending the interval maintains")
        r.append(f"  efficacy while avoiding toxic accumulation.")
        r.append(f"  Patient CrCl = {cl_cr:.1f} ml/min\n")
        for item in warned:
            sir_tag = f"  [Culture: {sir_map.get(item['name'],'?')}]" if sir_map else ""
            r.append(f"  {item['name']}{sir_tag}")
            r.append(f"  {SEP2}")
            r.append(f"  WHO AWaRe : {item['aware']}")
            r.append(f"  Class     : {item['class']}")
            r.append(f"  Renal note: {item['renal_note']}")
            r.append(f"  Limit CrCl: Dose adjustment required when CrCl <= {item['renal_limit']} ml/min")
            r.append("")

    if is_preg and preg_warn_items:
        r.append(f"\n{SEP}")
        r.append("  PREGNANCY — USE WITH CAUTION")
        r.append(f"  (Final decision belongs to the treating physician)")
        r.append(SEP)
        r.append("  These antibiotics are NOT automatically banned.")
        r.append("  They require careful medical evaluation.")
        r.append("  Some have been re-evaluated in recent literature")
        r.append("  (ACCP Journal 2025 and others).")
        r.append("  The detailed reason for caution is listed below.\n")
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
            r.append(f"  Reason: The laboratory confirmed this antibiotic")
            r.append(f"  does NOT inhibit the organism's growth (MIC too high).")
            r.append(f"  Using it will lead to treatment failure.\n")
            for b in cat_resist:
                r.append(f"    x {b['name']}")
                r.append(f"      {b['reason_detail']}\n")

        if cat_renal:
            r.append(f"\n  [B] CONTRAINDICATED IN RENAL IMPAIRMENT:")
            r.append(f"  Patient CrCl = {cl_cr:.1f} ml/min\n")
            for b in cat_renal:
                r.append(f"    x {b['name']}")
                r.append(f"      Short reason : {b['reason_short']}")
                detail_key = b["name"].lower().replace(" ","")
                for k, v in RENAL_BAN_REASONS.items():
                    if k in detail_key:
                        r.append(f"      Detail       :")
                        for ln in v.splitlines():
                            r.append(f"        {ln}")
                        break
                else:
                    r.append(f"      Detail       : {b['reason_detail']}")
                r.append("")

        if cat_preg:
            r.append(f"\n  [C] CONTRAINDICATED IN PREGNANCY:")
            r.append(f"  The following are banned due to confirmed fetal risk.\n")
            for b in cat_preg:
                r.append(f"    x {b['name']}")
                r.append(f"      Short reason : {b['reason_short']}")
                r.append(f"      Full detail  :")
                for ln in b["reason_detail"].splitlines():
                    r.append(f"        {ln}")
                r.append("")

        if cat_child:
            r.append(f"\n  [D] NOT SUITABLE FOR PATIENTS < 18 YEARS:")
            r.append(f"  Patient age = {age} years\n")
            for b in cat_child:
                r.append(f"    x {b['name']}")
                r.append(f"      Short reason : {b['reason_short']}")
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
            r.append(f"\n  [E] INEFFECTIVE FOR THIS ORGANISM ({organism}):")
            r.append(f"  These antibiotics have intrinsic (natural) resistance")
            r.append(f"  to this organism regardless of culture sensitivity.\n")
            for b in cat_organism:
                r.append(f"    x {b['name']}")
                r.append(f"      {b['reason_detail']}\n")

        if cat_other:
            r.append(f"\n  [F] OTHER CONTRAINDICATIONS:")
            for b in cat_other:
                r.append(f"    x {b['name']}")
                r.append(f"      {b['reason_detail']}\n")

    r.append(SEP)
    r.append("  DISCLAIMER:")
    r.append("  هذا التقرير مساعد للقرار الطبي وليس بديلاً عنه.")
    r.append("  القرار النهائي في الوصف يعود للطبيب المعالج.")
    r.append(SEP)
    r.append("  Guidelines : EUCAST 2026 | CLSI M100 2026 | IDSA AMR 2025 | Egypt National")
    r.append("  WHO AWaRe  : 🟢 Access = First choice | 🟡 Watch = Caution | 🔴 Reserve = Last resort")
    r.append(SEP)
    r.append("  Developed by: Dr. Hussein Ali | Orange Lab")
    r.append(SEP)
    return "\n".join(r)

# ==========================================
# 🖥️ Streamlit UI
# ==========================================
st.title("🛡️ Orange Culture Analyzer")
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

        # ─── فلترة البكتيريا حسب نوع العينة ─────────────────────────────
        filtered_organisms = SPECIMEN_ORGANISM_MAP.get(culture_type, BACTERIA_TYPES)
        # نضمن أن البكتيريا المقترحة موجودة في ORGANISM_PROFILE فعلاً
        filtered_organisms = [o for o in filtered_organisms if o in ORGANISM_PROFILE]

        # إذا كانت البكتيريا المكتشفة بالـ OCR موجودة في القائمة استخدمها، وإلا خذ الأول
        ocr_organism = patient["Organism"]
        if ocr_organism in filtered_organisms:
            default_org_idx = filtered_organisms.index(ocr_organism)
        else:
            default_org_idx = 0

        organism_type = st.selectbox(
            "🦠 Organism",
            filtered_organisms,
            index=default_org_idx,
            help=f"يعرض البكتيريا الأكثر شيوعاً في عينة {culture_type}",
        )

        if organism_type in ORGANISM_PROFILE:
            op = ORGANISM_PROFILE[organism_type]
            with st.expander("📌 Organism Guidance", expanded=True):
                st.info(op["note"])
                spec_ctx = op.get("specimen_context", {}).get(culture_type, "")
                if spec_ctx:
                    st.warning(f"**{culture_type} Context:** {spec_ctx}")
                st.write("**First-line:**", ", ".join(op["first_line"]))
                st.write("**Second-line:**", ", ".join(op["second_line"]))
                if op.get("third_line"):
                    st.write("**Third-line:**", ", ".join(op["third_line"]))
                if op["avoid"]:
                    st.error("**Avoid:** " + ", ".join(op["avoid"]))
                if culture_type == "Urine" and op.get("urine_note"):
                    st.info(f"📌 Urine-specific notes:\n{op['urine_note']}")

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
                                    min_value=0.1, max_value=20.0,
                                    value=1.0, step=0.1)
            cl_cr = ((140 - age) * weight) / (72 * s_cr)
            if sex == "Female": cl_cr *= 0.85
            st.metric("CrCl (Cockcroft-Gault)", f"{cl_cr:.1f} ml/min",
                      delta="Mild" if cl_cr>=60 else
                            ("Moderate" if cl_cr>=30 else "Severe"),
                      delta_color="normal" if cl_cr>=60 else
                                  ("off" if cl_cr>=30 else "inverse"))

        is_hepatic = st.checkbox("🚩 Hepatic Impairment")

        is_preg = False
        if sex == "Female" and 12 <= age <= 55:
            is_preg = st.checkbox("🤰 Patient is Pregnant")

        current_meds = st.multiselect("💊 Current Medications", COMMON_MEDS)

    with col2:
        st.subheader("💊 Antibiotic Analysis")

        if sir_map:
            st.info("📊 S/I/R detected from image: " +
                    " | ".join(f"{k}: **{v}**" for k,v in sir_map.items()))

        final_drugs = st.multiselect(
            "✅ Confirm/Edit Sensitive Antibiotics:",
            options=sorted(ABX_GUIDELINES.keys()),
            default=[d for d in drugs_from_ocr if d in ABX_GUIDELINES],
        )

        allowed, warned, banned = [], [], []
        preg_warn_items          = []
        interactions_alerts      = []
        organism_avoid           = ORGANISM_PROFILE.get(organism_type,{}).get("avoid",[])

        for d in final_drugs:
            info  = ABX_GUIDELINES[d]
            d_low = d.lower()

            if sir_map.get(d) == "R":
                banned.append({
                    "name": d, "category": "resistant",
                    "reason_short": "مقاوم (R) في نتيجة المزرعة.",
                    "reason_detail": (
                        f"المزرعة أثبتت أن {d} لا يثبط نمو الجرثومة.\n"
                        f"        الـ MIC أعلى من الحد العلاجي.\n"
                        f"        الاستخدام سيؤدي لفشل علاجي مؤكد."
                    ),
                })
                continue

            for med in current_meds:
                if med in info["interacts_with"]:
                    interactions_alerts.append(f"⚡ تعارض: {d} مع {med}")

            if is_hepatic and info["hepatic_caution"]:
                interactions_alerts.append(
                    f"🏥 تحذير كبدي: {d} — يحتاج متابعة وظائف الكبد.")

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
                        f"{d} لديه مقاومة طبيعية (intrinsic resistance)\n"
                        f"        لجرثومة {organism_type} بغض النظر عن نتيجة المزرعة.\n"
                        f"        الاستخدام سيؤدي لفشل علاجي."
                    ),
                })
                continue

            if organism_type == "MRSA":
                bl_classes = ["Penicillin","Cephalosporin"]
                if any(c in info["class"] for c in bl_classes):
                    banned.append({
                        "name": d, "category": "organism",
                        "reason_short": "بيتا-لاكتام — لا يعمل على MRSA.",
                        "reason_detail": (
                            f"MRSA يحمل جين mecA الذي يُنتج بروتين PBP2a.\n"
                            f"        هذا البروتين لا يرتبط بأي بيتا-لاكتام.\n"
                            f"        → جميع البنسيلين والسيفالوسبورين غير فعالة."
                        ),
                    })
                    continue

            if is_preg and info["preg_status"] == "Banned":
                banned.append({
                    "name": d, "category": "pregnancy",
                    "reason_short": info["preg_note"].splitlines()[0],
                    "reason_detail": info["preg_note"],
                })
                continue

            if is_preg and info["preg_status"] == "Warn":
                preg_warn_items.append({"name": d, **info})

            cls = info["class"].lower()
            if age < 18 and not info.get("child_safe", True):
                if "fluoroquinolone" in cls:
                    banned.append({
                        "name": d, "category": "child",
                        "reason_short": "غير مناسب لمن هم دون 18 سنة.",
                        "reason_detail": CHILD_BAN_REASONS["fluoroquinolone"],
                    })
                    continue
                elif "tetracycline" in cls and age < 8:
                    banned.append({
                        "name": d, "category": "child",
                        "reason_short": "غير مناسب لمن هم دون 8 سنوات.",
                        "reason_detail": CHILD_BAN_REASONS["tetracycline"],
                    })
                    continue
                else:
                    banned.append({
                        "name": d, "category": "child",
                        "reason_short": f"غير مرخص للأطفال.",
                        "reason_detail": f"الشركة الصانعة لا توصي به لمن هم دون 18 سنة.",
                    })
                    continue

            if is_renal and "nitrofurantoin" in d_low and cl_cr < 30:
                banned.append({
                    "name": d, "category": "renal",
                    "reason_short": f"ممنوع — CrCl {cl_cr:.1f} < 30 مل/د.",
                    "reason_detail": (
                        f"CrCl المريض = {cl_cr:.1f} مل/د (أقل من الحد المطلوب 30).\n"
                        f"        Nitrofurantoin لا يصل لتركيز علاجي في البول\n"
                        f"        عند ضعف الكلى، ويتراكم في الدم مسبباً سُمية."
                    ),
                })
                continue

            if is_renal and info["renal_limit"] > 0 and cl_cr <= info["renal_limit"]:
                warned.append({"name": d, **info})
                continue

            allowed.append({"name": d, **info})

        non_preg_alerts = [a for a in interactions_alerts if "🤰" not in a]
        if non_preg_alerts:
            st.warning("⚡ Interactions / Hepatic Warnings")
            for a in sorted(set(non_preg_alerts)):
                st.write(a)

        if is_preg and preg_warn_items:
            st.markdown("---")
            st.markdown("### 🤰 Pregnancy — Use With Caution")
            st.info(
                "الأدوية التالية **ليست محظورة تلقائياً** لكنها تحتاج تقييم طبي دقيق.\n\n"
                "بعضها أُعيد تقييمه في الأدبيات الحديثة (ACCP 2025).\n\n"
                "**القرار النهائي للطبيب المعالج حصراً.**"
            )
            for item in preg_warn_items:
                with st.expander(f"⚠️ {item['name']} — تفاصيل التحذير"):
                    for line in item["preg_note"].splitlines():
                        st.write(line)

        if banned:
            with st.expander("🚫 Contraindicated / Ineffective", expanded=True):
                for b in banned:
                    cat_label = {
                        "resistant": "مقاوم في المزرعة",
                        "renal":     "قصور كلوي",
                        "pregnancy": "ممنوع في الحمل",
                        "child":     "غير مناسب < 18 سنة",
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
                sir_badge  = f" [{sir_map.get(item['name'],'?')}]" if sir_map else ""
                preg_flag  = " 🤰" if (is_preg and item["preg_status"]=="Warn") else ""
                with st.expander(
                    f"{item['name']}{sir_badge}{preg_flag} — {AWARE_COLORS[item['aware']]}"
                ):
                    c1, c2 = st.columns(2)
                    c1.write(f"**Class:** {item['class']}")
                    c2.write(f"**Route:** {'🟢 PO' if item['high_po'] else '💉 IV only'}")
                    st.write(f"**Note:** {item['note']}")
                    spec_note = item.get("specimen_notes", {}).get(culture_type, "")
                    if spec_note:
                        st.info(f"**{culture_type} Note:** {spec_note}")
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
  Compliant with: EUCAST 2026 | CLSI M100 2026 | IDSA AMR 2025 | Egypt National Guidelines
</div>
""", unsafe_allow_html=True)
