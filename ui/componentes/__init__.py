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

# Alto del iframe. `components.html` no se adapta al contenido, así que hay que fijarlo:
# medido sobre el componente real con los 8 pasos (el waterfall reserva 300px de trazado
# + ~88px de rótulos, y el mosaico añade su bloque). Si se queda corto, el remate del
# mosaico se corta sin avisar.
ALTO_CASHFLOW = 1180


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
