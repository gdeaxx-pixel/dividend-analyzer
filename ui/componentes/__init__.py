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

# Medido en el navegador sobre el componente real (fixture `schwab_synth_1`, MSTY):
# `document.body.scrollHeight` = 658px, igual con el interruptor «Corregir la hoja»
# encendido o apagado (la fila que agrega ya tenía su espacio reservado). Se detectó
# y corrigió antes de esta medición un bug de extracción que dejaba el iframe en
# negro (`hidden` heredado del panel de pestañas del demo — ver `extract_hoja.py`).
ALTO_HOJA = 700

# Medido en el navegador (fixture NVDY, paso 1 · DRIP bruto): `scrollHeight` = 901px,
# ya casi exacto contra el placeholder de 900 — solo se sube el margen de seguridad.
ALTO_COMPARACION = 920

# Medido en el navegador sobre las 5 sub-vistas (fixture `schwab_synth_1`, precios en
# vivo vía `analyze_portfolio`): matriz 1847px, rendimiento 1128px, payback 902px,
# rendimiento vs tasa la más alta — 2541px —, otras calculadoras 563px. Dos bugs de
# extracción corregidos antes de esta medición: (1) el iframe en negro por `hidden`
# heredado de `view-metodo`, el envoltorio de nivel superior (ver `extract_metodo.py`);
# (2) la medición inicial daba números inconsistentes entre cargas (1612–2541 para
# "tasa") porque `ajustarBaseFiscal()` — que reserva el alto máximo entre los 3 modos
# fiscales (bruto/ROC/plano) — solo se disparaba por azar vía `resize`, nunca al
# entrar a la sub-vista «matriz» como hace `showMetTab` en el demo; se cableó ese
# llamado en el extractor. Con eso el alto es determinista, pero sigue habiendo margen
# extra: los precios en vivo pueden variar el número de filas visibles entre cargas.
ALTO_METODO = 2650

# Medido en el navegador: `scrollHeight` = 6826px, estable (una primera medición con
# el iframe todavía a 2600 dio 5882 — algo dentro del componente solo terminaba de
# expandirse con más alto disponible; se volvió a medir tras subir el alto hasta que
# el número dejó de moverse). El placeholder de 2600 dejaba más de la mitad del texto
# invisible sin aviso — `scrolling=False` no deja ni hacer scroll para alcanzarlo. Se
# detectó y corrigió antes de esta medición un bug de extracción que dejaba el iframe
# en negro (`hidden` heredado de `view-metodologia` — ver `extract_metodologia.py`).
ALTO_METODOLOGIA = 7000


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
    """Rail de 8 pasos: barra de progreso + etiqueta, como el `.step` del artifact.

    En el demo el rail es HTML y cambia sin recargar; aquí cada clic es un rerun de
    Streamlit. Es el precio de tener el estado en Python, y está aprobado en el traspaso.

    Cada paso va envuelto en su propio `st.container(key=...)` cuya clave termina en
    `_done` / `_now` / `_todo`: Streamlit convierte esa clave en la clase `st-key-…` y
    `inyectar_estilos` la usa para colorear la barra. Es el único modo de tener TRES
    estados — `st.button` solo distingue dos (`primary`/`secondary`).
    """
    st.session_state.setdefault(key, activo)
    actual = st.session_state[key]
    with st.container(key=f"{key}_wrap"):
        columnas = st.columns(len(labels))
        for indice, (columna, etiqueta) in enumerate(zip(columnas, labels)):
            estado = "now" if indice == actual else ("done" if indice < actual else "todo")
            with columna:
                with st.container(key=f"{key}_p{indice}_{estado}"):
                    if st.button(etiqueta, key=f"{key}_{indice}",
                                 use_container_width=True):
                        st.session_state[key] = indice
                        st.rerun()
    return st.session_state[key]
