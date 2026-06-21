# ui/settings.py
# © Dr. Hussein Ali — Orange Lab
# Sidebar settings panel (lab name, city, theme)

from __future__ import annotations
import streamlit as st

def render_settings_sidebar() -> tuple[str, str]:
    """يرجع (lab_name, lab_city) من الـ sidebar"""
    with st.sidebar:
        st.markdown("### ⚙️ إعدادات المعمل")
        lab_name = st.text_input(
            "اسم المعمل",
            value=st.session_state.get("lab_name", "Orange Lab"),
            key="lab_name_input"
        )
        lab_city = st.text_input(
            "المدينة",
            value=st.session_state.get("lab_city", "6 October City, Egypt"),
            key="lab_city_input"
        )
        st.session_state.lab_name = lab_name
        st.session_state.lab_city = lab_city
        return lab_name, lab_city
