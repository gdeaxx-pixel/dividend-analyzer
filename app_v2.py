"""Punto de entrada del port de Viaje del dinero a Streamlit (Fase 1)."""

import streamlit as st

from ui.chrome import render_header, render_navigation, render_stage
from ui.tokens import base_css


st.set_page_config(
    page_title="Viaje del dinero · Invierte & Gana",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

selection = render_navigation()
st.markdown(base_css(selection.theme), unsafe_allow_html=True)
render_header(selection)
render_stage(selection)
