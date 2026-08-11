"""PRODUCCIÓN. Punto de entrada de la app desplegada en Streamlit Cloud.

Es el port de «Viaje del dinero» del artifact; sustituyó al `app.py` anterior el
2026-08-09 por renombre (el anterior se conserva como `app_old.py`, no se ejecuta).
La interfaz vive en `ui/`; `logic.py` es la capa de cálculo compartida.

Estado y controles en widgets nativos; el HTML del artifact es render visual:
`st.components.v1.html()` no puede devolver interacciones a `st.session_state`, así que
todo lo que cambia estado vive en Python.
"""

import streamlit as st

import stale_guard

# Los módulos se importan como tales antes de sacarles nombres sueltos: así el guardián
# los ve todos ya cargados y puede recargarlos si el disco cambió bajo el proceso
# (despliegue sin reinicio en Streamlit Cloud). Estos cuatro arrastran el resto de `ui/`.
import logic  # noqa: F401  — lo vigila el guardián
from ui import carga, chrome, pie, vistas  # noqa: F401  — ídem

# Anotar en la 1ª corrida y comparar en las siguientes tiene que pasar DESPUÉS de los
# imports: si tomara la foto antes, una corrida posterior al despliegue registraría las
# fechas nuevas como si fueran las suyas y el código viejo pasaría desapercibido.
stale_guard.asegurar_frescura()

from ui.carga import notificar_progreso, render_carga  # noqa: E402  — tras el guardián
from ui.chrome import inyectar_estilos, render_encabezado, render_ruta
from ui.pie import render_pie
from ui.validacion import hay_alertas, preparar_pdf
from ui.vistas import obtener_resultados, render_vista

st.set_page_config(
    page_title="Viaje del dinero · Invierte & Gana",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# `?clear` — limpia el cache de `analyze_portfolio` (copiado literal de `app_old.py:61`).
if st.query_params.get("clear"):
    st.cache_data.clear()
    st.query_params.clear()
    st.rerun()

# Modo demo local (`?demo=ib|schwab|schwab2`): carga un caso de `real_examples/` directo
# a resultados, sin wizard. Copiado literal de `app_old.py:67-79`; en producción y en este
# worktree no hay `real_examples/` → inerte por diseño (fixtures/ es lo único versionado).
# Único puente necesario con el resto del port: el bundle trae las claves de sesión de
# `app_old.py` (`_results`, `_wizard_step`…), que este port no lee — su contrato es
# `_wizard_df_clean` + `_wizard_listo` (Fase 2/3b). Fijar `_wizard_listo` es lo que hace
# que el demo "salte a resultados sin subir CSV"; no es una reinterpretación de lógica de
# negocio, es la única bandera de navegación que cambió de nombre entre `app_old.py` y el port.
_demo_param = st.query_params.get("demo")
if _demo_param and st.session_state.get("_demo_case") != _demo_param:
    import demo_mode
    _demo_bundle = demo_mode.load_demo_case(_demo_param)
    if _demo_bundle:
        for _dk, _dv in _demo_bundle.items():
            st.session_state[_dk] = _dv
        st.session_state["_wizard_listo"] = True
        st.session_state["_demo_case"] = _demo_param
    elif demo_mode.demo_available():
        st.caption(f"demo '{_demo_param}' no disponible · casos: {', '.join(demo_mode.demo_keys())}")

# Hasta que el usuario pulsa «Ver resultados →» (al final del Bloque 3, opcional) no hay
# recorrido que enseñar: la hoja de carga ocupa toda la superficie y la ruta no se dibuja —
# solo el tema, en el encabezado. Confirmar posiciones (Bloque 2) NO basta por sí solo:
# saltar directo a resultados en ese punto dejaba el Bloque 3 (ingresos) inalcanzable.
con_datos = bool(st.session_state.get("_wizard_listo"))
notificar_progreso(con_datos)

# Los estilos se inyectan ANTES de dibujar el encabezado: si `render_encabezado` corriera
# primero, el primer pintado de esta corrida saldría sin tokens.
st.session_state.setdefault("vd_tema", "Claro")
inyectar_estilos(st.session_state["vd_tema"])

render_encabezado(con_datos)

if con_datos:
    resultados = obtener_resultados()
    pdf_bytes, pdf_filename = preparar_pdf(resultados)
    ruta = render_ruta(hay_alertas(resultados), pdf_bytes, pdf_filename)
    render_vista(ruta)
    render_pie(resultados)
else:
    render_carga()
