"""Punto de entrada del port de «Viaje del dinero» a Streamlit.

Estado y controles en widgets nativos; el HTML del artifact es render visual. Ver el
traspaso § Arquitectura: `st.components.v1.html()` no puede devolver interacciones a
`st.session_state`, así que todo lo que cambia estado vive en Python.
"""

import streamlit as st

from ui.carga import render_carga
from ui.chrome import inyectar_estilos, render_encabezado, render_ruta
from ui.vistas import render_vista

st.set_page_config(
    page_title="Viaje del dinero · Invierte & Gana",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Hasta que el usuario pulsa «Ver resultados →» (al final del Bloque 3, opcional) no hay
# recorrido que enseñar: la hoja de carga ocupa toda la superficie y la ruta no se dibuja —
# solo el tema, en el encabezado. Confirmar posiciones (Bloque 2) NO basta por sí solo:
# saltar directo a resultados en ese punto dejaba el Bloque 3 (ingresos) inalcanzable.
con_datos = bool(st.session_state.get("_wizard_listo"))

# Los estilos se inyectan ANTES de dibujar el encabezado: si `render_encabezado` corriera
# primero, el primer pintado de esta corrida saldría sin tokens.
st.session_state.setdefault("vd_tema", "Claro")
inyectar_estilos(st.session_state["vd_tema"])

render_encabezado(con_datos)

if con_datos:
    ruta = render_ruta()
    render_vista(ruta)
else:
    render_carga()
