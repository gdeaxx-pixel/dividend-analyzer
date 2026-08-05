"""Punto de entrada del port de «Viaje del dinero» a Streamlit.

Estado y controles en widgets nativos; el HTML del artifact es render visual. Ver el
traspaso § Arquitectura: `st.components.v1.html()` no puede devolver interacciones a
`st.session_state`, así que todo lo que cambia estado vive en Python.
"""

import streamlit as st

from ui.chrome import inyectar_estilos, render_crumb, render_placeholder, render_ruta

st.set_page_config(
    page_title="Viaje del dinero · Invierte & Gana",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

ruta = render_ruta()
inyectar_estilos(ruta.tema)
render_crumb(ruta)
render_placeholder(ruta)
