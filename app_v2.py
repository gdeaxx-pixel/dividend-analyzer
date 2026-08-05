"""Punto de entrada del port de «Viaje del dinero» a Streamlit.

Estado y controles en widgets nativos; el HTML del artifact es render visual. Ver el
traspaso § Arquitectura: `st.components.v1.html()` no puede devolver interacciones a
`st.session_state`, así que todo lo que cambia estado vive en Python.
"""

import streamlit as st

from ui.carga import render_carga
from ui.chrome import inyectar_estilos, render_crumb, render_ruta
from ui.vistas import render_vista

st.set_page_config(
    page_title="Viaje del dinero · Invierte & Gana",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Sin posiciones confirmadas no hay recorrido que enseñar: la hoja de carga ocupa toda la
# superficie y la navegación se reduce al tema.
con_datos = bool(st.session_state.get("_wizard_pos_confirmed"))

ruta = render_ruta(con_datos=con_datos)
inyectar_estilos(ruta.tema)

if con_datos:
    render_crumb(ruta)
    render_vista(ruta)
else:
    render_carga()
