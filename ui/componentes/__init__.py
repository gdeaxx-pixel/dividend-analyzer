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

# Alto INICIAL del iframe y respaldo si el script auto-dimensionante no corre. El
# componente se mide y corrige su propio alto desde dentro (ver el segundo <script> de
# `tools/extract_cashflow.py`), así que este número ya no manda — pero tiene que ser
# seguro por sí solo: si Streamlit Cloud sirviera el componente cross-origin,
# `window.frameElement` no sería alcanzable y este valor sería el definitivo.
# Medido en el navegador sobre los 8 pasos × 3 fixtures: 1053px (desktop) a 1485px
# (320px de ancho). Se fija por encima del peor caso — NO bajarlo a la medida de
# desktop: con `scrolling=False` lo que no cabe es inalcanzable, no solo invisible.
ALTO_CASHFLOW = 1520

# Respaldo si el script auto-dimensionante no corre (ver `tools/_auto_alto.py`).
# Medido en el navegador sobre el componente real (fixture `schwab_synth_1`, MSTY):
# `document.body.scrollHeight` = 658px, igual con el interruptor «Corregir la hoja»
# encendido o apagado (la fila que agrega ya tenía su espacio reservado). Se detectó
# y corrigió antes de esta medición un bug de extracción que dejaba el iframe en
# negro (`hidden` heredado del panel de pestañas del demo — ver `extract_hoja.py`).
ALTO_HOJA = 700

# Respaldo si el script auto-dimensionante no corre (ver `tools/_auto_alto.py`).
# La medición vieja (901px) era solo a ancho de escritorio; a 320-375px los chips
# envuelven en más filas y el panel crece. Re-medido en la auditoría del 2026-08-10 a
# 375px: `body.scrollHeight` = 1025px. Se fija por encima de ESE caso, no del de
# escritorio: con `scrolling=False` lo que no cabe es inalcanzable, no solo invisible.
ALTO_COMPARACION = 1200

# Respaldo si el script auto-dimensionante no corre (ver `tools/_auto_alto.py`).
# Mismo panel que ALTO_COMPARACION, pero el lede declara la fecha de corte y la nota
# de cifras reales es más larga, así que crece un poco más. Medido en el navegador con
# datos reales (`?demo=schwab2`, base MSTY · DRIP bruto): 974px a 1280 de ancho y
# **1086px a 375px**. El auto-alto converge en esos valores sin oscilar.
ALTO_COMPARACION_REAL = 1150

# Respaldo si el script auto-dimensionante no corre (ver `tools/_auto_alto.py`).
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
ALTO_METODO = 2500

# Respaldo si el script auto-dimensionante no corre (ver `tools/_auto_alto.py`); el
# componente corrige su propio alto en cuanto carga. El alto depende del ANCHO (el texto
# envuelve distinto): no hay un único "valor real" — a 860px (escritorio) converge en
# 4537px, a 337px (contenedor real a 375px de viewport) en 6483px. Ambas mediciones
# tomadas al ancho FINAL del iframe, no al 300px por defecto que Streamlit usa antes de
# estirarlo (medir ahí da 6826px, un artefacto del ancho equivocado, no del contenido —
# ver `feedback_resize-observer-suspendido`). 7000 cubre ambos casos con margen y sigue
# siendo el respaldo seguro; no hace falta subirlo.
ALTO_METODOLOGIA = 7000

# Respaldo si el script auto-dimensionante no corre (ver `tools/_auto_alto.py`); el
# componente corrige su propio alto en cuanto carga. «Matriz 2» apila las 4 secciones
# en un solo panel (a diferencia de `metodo.html`, que reparte 5 sub-vistas): matriz +
# escalera + payback + tasa. Estimado inicial sobre el orden de magnitud de «El
# rendimiento»/«Payback»/«Rendimiento vs tasa» combinados en `ALTO_METODO` — pendiente
# de medición en vivo con un portafolio real (`?demo=ib`/`schwab`/`schwab2`).
ALTO_METODO_REAL = 2600


def _plantilla(nombre: str) -> str:
    ruta = os.path.join(_AQUI, nombre)
    if not os.path.exists(ruta):
        raise FileNotFoundError(
            f"Falta {nombre}. Genéralo con `python tools/extract_cashflow.py`."
        )
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def _con_tema(html: str, tema: str) -> str:
    """Inserta el atributo de tema ANTES del primer `<style>` (y por tanto antes del
    `<script>` del componente), para que `draw()` — los colores dependientes de custom
    properties — lea los tokens correctos en su primera pasada.

    H1 (traspaso 2026-08-10): los 5 componentes viven en iframes `srcdoc` con su propia
    copia del CSS del artifact. `ui/chrome.py:inyectar_estilos` escribe los tokens en el
    documento PRINCIPAL; dentro del iframe nadie escribía `data-theme`, así que el CSS
    caía a `@media (prefers-color-scheme: dark)` — el tema del SISTEMA OPERATIVO, no el
    de la app (medido: con la app en Claro y el Mac en oscuro, todos los componentes
    salían oscuros y el botón Claro no hacía nada dentro de ellos). El CSS del artifact
    ya trae `:root[data-theme="light"]`/`[data-theme="dark"]` después del `@media`, así
    que el selector con atributo gana por especificidad — no hace falta tocar CSS ni
    extractores, solo escribir el atributo antes de que el componente calcule colores.
    """
    atributo = "dark" if tema == "Oscuro" else "light"
    script = (f'<script>document.documentElement.setAttribute('
              f'"data-theme", "{atributo}");</script>\n')
    i = html.find("<style>")
    if i < 0:
        raise ValueError("No encontré <style> en el componente — ¿cambió el extractor?")
    return html[:i] + script + html[i:]


def _con_anchor(html: str, anchor: str | None) -> str:
    """Inserta `window.__vdAnchor` antes del primer `<style>` (mismo punto que
    `_con_tema`), para que `buildMethIndex()` (`ui/componentes/metodologia.html`) la lea
    al construirse y abra ya iluminada la entrada correspondiente a la vista de origen —
    ver `ui/chrome.py:_ANCLA_METODOLOGIA`. Sin `anchor`, no se inserta nada: el
    componente se comporta como hoy (índice sin resaltar)."""
    if not anchor:
        return html
    script = f'<script>window.__vdAnchor = {json.dumps(anchor)};</script>\n'
    i = html.find("<style>")
    if i < 0:
        raise ValueError("No encontré <style> en el componente — ¿cambió el extractor?")
    return html[:i] + script + html[i:]


def render_cashflow(datos: dict, paso: int, tema: str, alto: int = ALTO_CASHFLOW) -> None:
    """Dibuja el recorrido del dinero en el paso indicado.

    `datos` viene de `ui.adapters.cashflow_data`; `paso` es 0-7 y lo controla el rail
    nativo. El JSON se serializa con `json.dumps`, que ya escapa lo necesario para vivir
    dentro de un `<script>`. `tema` es "Claro"/"Oscuro" (`st.session_state["vd_tema"]`).
    """
    html = _plantilla("cashflow.html")
    html = _con_tema(html, tema)
    html = html.replace("{{DATA_JSON}}", json.dumps(datos, ensure_ascii=False))
    html = html.replace("{{PASO}}", str(int(paso)))
    components.html(html, height=alto, scrolling=False)


def render_hoja(datos: dict, tema: str, alto: int = ALTO_HOJA) -> None:
    """Dibuja la Hoja Excel: las dos lecturas de la posición y el interruptor
    «Corregir la hoja». `datos` viene de `ui.adapters.hoja_data`.
    """
    html = _plantilla("hoja.html")
    html = _con_tema(html, tema)
    html = html.replace("{{DATA_JSON}}", json.dumps(datos, ensure_ascii=False))
    components.html(html, height=alto, scrolling=False)


def render_comparacion(datos: dict, tema: str, alto: int = ALTO_COMPARACION) -> None:
    """Dibuja «Comparación · Simulación» (Total Return Graph). `datos` viene de
    `ui.adapters.comparacion_data`: índice mensual real (caché de precio/dividendo +
    `backtest.run_backtest`, Fase 3.3a del plan de remediación) para los 8 tickers de
    `TRG_UNIVERSO`, sin depender del portafolio del usuario — mismo patrón
    `{{DATA_JSON}}` que `render_hoja`/`render_comparacion_real`, ya no el modelo
    paramétrico (`F`/`shapeOf`) que tenía antes.
    """
    html = _plantilla("comparacion.html")
    html = _con_tema(html, tema)
    html = html.replace("{{DATA_JSON}}", json.dumps(datos, ensure_ascii=False))
    components.html(html, height=alto, scrolling=False)


def render_comparacion_real(datos: dict, tema: str, alto: int = ALTO_COMPARACION_REAL) -> None:
    """Dibuja «Comparación · Real» (Total Return Graph con datos reales). Mismo
    componente/CSS/controles que la Simulación (`ui/componentes/comparacion_real.html`,
    derivado por `tools/extract_comparacion_real.py`), pero leyendo `{{DATA_JSON}}` —
    el índice TRI crudo de los 8 tickers × 3 modos que arma
    `ui.adapters.trg_real_data` — en vez del modelo paramétrico. El componente no
    calcula: series()/draw() en JS hacen la renormalización al fondo base elegido, sin
    rerun de Streamlit (mapa-datos.md § 5, decisión 3 del traspaso 2026-08-10).

    Nombrado distinto a `ui.vistas.render_trg_real` (el despachador que llama a esta
    función) a propósito — mismo patrón que `render_cashflow`/`render_cash_flow` y
    `render_hoja`/`render_hoja_excel`: dos módulos con responsabilidades distintas no
    pueden compartir nombre de función sin que el import de uno choque con la
    definición del otro.
    """
    html = _plantilla("comparacion_real.html")
    html = _con_tema(html, tema)
    html = html.replace("{{DATA_JSON}}", json.dumps(datos, ensure_ascii=False))
    html = html.replace("{{ASOF}}", str(datos.get("asof", "")))
    components.html(html, height=alto, scrolling=False)


def render_metodo(vista_activa: str, tema: str, datos: dict, alto: int = ALTO_METODO) -> None:
    """Dibuja «Método tradicional». `vista_activa` es una de matriz/rendimiento/payback/
    tasa/otras (`ui.nav.MET_ORDER`). El componente trae sus 5 sub-vistas ya calculadas
    (initMetodo las llena de una pasada, igual que en el demo); de las cinco, hoy solo
    «La matriz» recibe `{{DATA_JSON}}` (Fase 3.3b, `ui.adapters.metodo_data`) — el resto
    sigue con cifras propias sin datos de Python, ajenas al portafolio del usuario
    (mapa-datos.md § 6).
    """
    html = _plantilla("metodo.html")
    html = _con_tema(html, tema)
    html = html.replace("{{VISTA_ACTIVA}}", vista_activa)
    html = html.replace("{{DATA_JSON}}", json.dumps(datos, ensure_ascii=False))
    components.html(html, height=alto, scrolling=False)


def render_metodo_real(datos: dict, tema: str, alto: int = ALTO_METODO_REAL) -> None:
    """Dibuja «Matriz 2» (Método tradicional · las cuatro lecciones de «La matriz»
    sobre el portafolio real del CSV cargado). Componente propio, no una sexta
    sub-vista de `metodo.html` (Duda 1 del traspaso 2026-08-17: ese componente pesa
    170 KB y ya dibuja sus 5 sub-vistas de una pasada con un ciclo de vida cacheado
    por sesión; esta vista se invalida cada vez que se reedita la carga del CSV, un
    ciclo de vida distinto). `datos` viene de `ui.adapters.metodo_real_data` — `None`
    lo maneja quien llama (mismo patrón que `render_comparacion_real`/`render_trg_real`).
    """
    html = _plantilla("metodo_real.html")
    html = _con_tema(html, tema)
    html = html.replace("{{DATA_JSON}}", json.dumps(datos, ensure_ascii=False))
    components.html(html, height=alto, scrolling=False)


def render_metodologia(tema: str, alto: int = ALTO_METODOLOGIA, anchor: str | None = None,
                        datos: dict | None = None) -> None:
    """Dibuja Metodología: 11 entradas, formulario y bibliografía. HTML mayormente
    estático — sin datos de Python salvo, opcionalmente, `anchor` (mapa-datos.md § 7):
    la entrada a iluminar al abrir, cuando se llega desde una vista concreta en vez del
    índice general (ver `ui/chrome.py:_ANCLA_METODOLOGIA`).

    `datos` (Fase 4, Clase E) es el mismo `ui.adapters.metodo_data()` que ya consume
    `render_metodo` — se reutiliza (mismo caché de sesión, no una segunda descarga). § 9
    «Anualizar bien» LEE de ahí `escalera` (retorno total, ventana media ponderada, ÷N
    ingenuo y TIR exacta) en vez de rehacer la cuenta en JS: es el mismo objeto que
    dibuja la escalera de «Método tradicional» § 10, y por eso las dos vistas no pueden
    divergir. Sin `datos` (o si `metodo_data()` no pudo bajar historia), el componente
    muestra el aviso en vez de una cifra que ya no puede verificar."""
    html = _plantilla("metodologia.html")
    html = _con_tema(html, tema)
    html = _con_anchor(html, anchor)
    html = html.replace("{{DATA_JSON}}", json.dumps(datos, ensure_ascii=False) if datos else "null")
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
        # Leyenda «Paso N de 8 · Etiqueta», solo visible en móvil (ver @media en
        # `ui/chrome.py`): en desktop el texto por paso ya cumple ese rol; a 375px
        # Streamlit apila las 8 columnas y el texto por botón se oculta, así que esta
        # línea es lo único que sigue comunicando dónde va el usuario.
        st.markdown(
            f'<div class="vd-rail-legend">Paso {actual + 1} de {len(labels)} · '
            f'{labels[actual]}</div>',
            unsafe_allow_html=True,
        )
    return st.session_state[key]
