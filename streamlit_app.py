# streamlit_app.py
# © 2025 Dr. Hussein Ali — Orange Lab, 6 October City, Egypt
# Orange Culture Tool — Microbiology CDSS
# All Rights Reserved. Unauthorized copying or distribution is prohibited.

import streamlit as st

# =========================================================
# إعداد الصفحة
# =========================================================
st.set_page_config(
    page_title="Microbiology CDSS",
    layout="wide",
    page_icon="🔬"
)

st.markdown("""
<style>
    .stActionButton {display: none !important;}
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    header[data-testid="stHeader"] {display: none !important;}
    .app-card {
        padding: 1rem 1.2rem;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
        background: rgba(255,255,255,0.02);
        margin-bottom: 1rem;
    }
    .muted-text { color: #9aa0a6; font-size: 0.92rem; }
    .orange-badge {
        display:inline-block; background:#ff8c00; color:white;
        padding:0.25rem 0.7rem; border-radius:999px;
        font-size:0.8rem; font-weight:600;
    }
</style>
""", unsafe_allow_html=True)

# =========================================================

# ── Entry point ──────────────────────────────────────────────────────────────
from ui.dashboard import init_session_state, run_dashboard

init_session_state()

from modules.auth import (check_subscription, show_login_page,
                           handle_session_timeout, render_top_bar)
from modules.qc   import get_startup_validation_issues

if not st.session_state.get("authenticated", False):
    email_input = show_login_page()
    if email_input:
        if check_subscription(email_input):
            import time
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

run_dashboard()
