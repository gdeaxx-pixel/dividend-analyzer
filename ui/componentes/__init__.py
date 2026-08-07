"""Montaje de los componentes HTML extraídos del artifact.

Cada componente es un `.html` **generado** (ver `tools/extract_*.py`) con huecos que se
rellenan en cada rerun. El estado no vive aquí: `components.html()` devuelve `None` y no
puede retornar interacciones a Python, así que los controles son widgets nativos y el
componente solo dibuja lo que recibe.
"""

from __future__ import annotations

import json
import os

import streamlit as st
import streamlit.components.v1 as components

_AQUI = os.path.dirname(os.path.abspath(__file__))

# Alto del iframe. `components.html` no se adapta al contenido, así que hay que fijarlo.
# NO estimar: medido en el navegador sobre el componente real en el paso 8 (el más alto),
# `document.body.scrollHeight` = 2095px, con el mosaico terminando en 1642px. La primera
# estimación fue 1180 y habría cortado el mosaico por la mitad — que es el remate
# narrativo de la vista— sin ningún aviso.
ALTO_CASHFLOW = 2150

# Pendiente de medir en el navegador (mismo criterio que ALTO_CASHFLOW: nunca estimar
# a ojo). Placeholders generosos mientras se corrigen en la verificación de la Fase 4.
ALTO_HOJA = 1400
ALTO_COMPARACION = 900
ALTO_METODO = 1800
ALTO_METODOLOGIA = 2600


def _plantilla(nombre: str) -> str:
    ruta = os.path.join(_AQUI, nombre)
    if not os.path.exists(ruta):
        raise FileNotFoundError(
            f"Falta {nombre}. Genéralo con `python tools/extract_cashflow.py`."
        )
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def render_cashflow(datos: dict, paso: int, alto: int = ALTO_CASHFLOW) -> None:
    """Dibuja el recorrido del dinero en el paso indicado.

    `datos` viene de `ui.adapters.cashflow_data`; `paso` es 0-7 y lo controla el rail
    nativo. El JSON se serializa con `json.dumps`, que ya escapa lo necesario para vivir
    dentro de un `<script>`.
    """
    html = _plantilla("cashflow.html")
    html = html.replace("{{DATA_JSON}}", json.dumps(datos, ensure_ascii=False))
    html = html.replace("{{PASO}}", str(int(paso)))
    components.html(html, height=alto, scrolling=False)


def render_hoja(datos: dict, alto: int = ALTO_HOJA) -> None:
    """Dibuja la Hoja Excel: las dos lecturas de la posición y el interruptor
    «Corregir la hoja». `datos` viene de `ui.adapters.hoja_data`.
    """
    html = _plantilla("hoja.html")
    html = html.replace("{{DATA_JSON}}", json.dumps(datos, ensure_ascii=False))
    components.html(html, height=alto, scrolling=False)


def render_comparacion(alto: int = ALTO_COMPARACION) -> None:
    """Dibuja «Comparación · Simulación» (Total Return Graph). Sin datos: es un modelo
    paramétrico que se porta tal cual (mapa-datos.md § 4), así que no hay `{{DATA_JSON}}`
    que rellenar — el componente trae sus propias cifras, igual que en el demo.
    """
    html = _plantilla("comparacion.html")
    components.html(html, height=alto, scrolling=False)


def render_metodo(vista_activa: str, alto: int = ALTO_METODO) -> None:
    """Dibuja «Método tradicional». `vista_activa` es una de matriz/rendimiento/payback/
    tasa/otras (`ui.nav.MET_ORDER`). El componente trae sus 5 sub-vistas ya calculadas
    (initMetodo las llena de una pasada, igual que en el demo) y solo oculta las que no
    tocan — sin datos de Python: la cartera que audita es ajena (mapa-datos.md § 6).
    """
    html = _plantilla("metodo.html")
    html = html.replace("{{VISTA_ACTIVA}}", vista_activa)
    components.html(html, height=alto, scrolling=False)


def render_metodologia(alto: int = ALTO_METODOLOGIA) -> None:
    """Dibuja Metodología: 11 entradas, formulario y bibliografía. HTML estático
    completo — sin datos de Python (mapa-datos.md § 7).
    """
    html = _plantilla("metodologia.html")
    components.html(html, height=alto, scrolling=False)


def render_rail(labels: list, activo: int, key: str = "vd_paso") -> int:
    """Rail de 8 pasos en botones nativos.

    En el demo el rail es HTML y cambia sin recargar; aquí cada clic es un rerun de
    Streamlit. Es el precio de tener el estado en Python, y está aprobado en el traspaso.
    """
    st.session_state.setdefault(key, activo)
    columnas = st.columns(len(labels))
    for indice, (columna, etiqueta) in enumerate(zip(columnas, labels)):
        with columna:
            estado = "primary" if indice == st.session_state[key] else "secondary"
            if st.button(etiqueta, key=f"{key}_{indice}", type=estado,
                         use_container_width=True):
                st.session_state[key] = indice
                st.rerun()
    return st.session_state[key]
