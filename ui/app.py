import _bootstrap  # noqa: F401  # deve vir antes de qualquer import de jobapplier
import streamlit as st

from jobapplier.config.manager import ConfigManager

st.set_page_config(
    page_title="AI Job Applier",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="collapsed",
)

config = ConfigManager()

if not config.is_setup_complete():
    st.switch_page("pages/1_Setup.py")
else:
    st.switch_page("pages/2_Dashboard.py")
