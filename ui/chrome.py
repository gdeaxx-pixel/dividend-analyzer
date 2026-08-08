"""Chrome del port: encabezado + ruta funcional Categoría › Vista › ETF.

Toda la taxonomía y todos los colores vienen de `ui/nav.py` y `ui/tokens.py`, que se
GENERAN del demo (`tools/extract_design_system.py`). Aquí no se escribe a mano ni un
nombre de vista ni un color: si algo no coincide con el artifact, se corrige en el demo
y se regenera.

Fase 3b: la barra lateral desaparece. La ruta pasa a ser el único navegador — cada
segmento (Categoría / Vista / ETF) es un `st.popover` con botones nativos dentro, que sí
devuelven estado a Python (a diferencia del HTML del artifact). El tema se mueve al
encabezado, arriba a la derecha.

Solo presentación — sin datos ni cálculos.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from ui import heredadas, nav
from ui.tokens import css_variables

# Categoría «Detalle» compuesta sobre la taxonomía generada: `ui/nav.py` es el espejo
# verificable del artifact (el demo solo tiene 4 categorías) y no se edita para meterla
# ahí — se compone aquí, en tiempo de import, sin tocar el generador (traspaso § Fase 5).
CAT_ORDER_TOTAL = nav.CAT_ORDER + (heredadas.CAT_CLAVE,)
CAT_LABELS_TOTAL = {**nav.CAT_LABELS, heredadas.CAT_CLAVE: heredadas.CAT_LABEL}


@dataclass(frozen=True)
class Ruta:
    """Posición actual en la jerarquía del artifact."""

    categoria: str          # clave: dividendos · largo · comparacion · metodo
    vista: str              # clave dentro de la categoría
    etf: str | None         # solo en Cash flow
    tema: str               # "Claro" | "Oscuro"

    @property
    def categoria_label(self) -> str:
        return CAT_LABELS_TOTAL[self.categoria]

    @property
    def vista_label(self) -> str:
        return _vistas(self.categoria)[self.vista]


def _vistas(categoria: str) -> dict:
    """Vistas de una categoría. Comparación y Método tienen las suyas; las categorías
    con ETF comparten las tres secciones (Cash flow · Salud NAV · Hoja Excel); Detalle
    (heredada, fuera del artifact) trae las suyas propias."""
    if categoria == "comparacion":
        return dict(nav.CMP_VIEWS)
    if categoria == "metodo":
        return dict(nav.MET_VIEWS)
    if categoria == heredadas.CAT_CLAVE:
        return dict(heredadas.VIEWS)
    return dict(nav.SECTIONS)


def _orden(categoria: str) -> tuple:
    if categoria == "comparacion":
        return nav.CMP_ORDER
    if categoria == "metodo":
        return nav.MET_ORDER
    if categoria == heredadas.CAT_CLAVE:
        return heredadas.VIEW_ORDER
    return tuple(nav.SECTION_ORDER)


def inyectar_estilos(tema: str) -> None:
    """Inyecta los tokens del artifact para el tema activo, más los estilos del chrome
    y de la hoja de carga."""
    from ui.carga import ESTILOS_CARGA
    from ui.pie import ESTILOS_PIE

    st.markdown(
        f"<style>\n        {css_variables(tema)}\n{_ESTILOS}{ESTILOS_CARGA}{ESTILOS_PIE}</style>",
        unsafe_allow_html=True)


def _sync_tema() -> None:
    """`on_change` del control de tema: corre ANTES de que el script vuelva a dibujar el
    widget, así que aquí sí se puede tocar `st.session_state["vd_tema_w"]` (a diferencia de
    hacerlo en el cuerpo del script, donde Streamlit lo rechaza por ya estar instanciado —
    ese fue el bug que tumbaba la app al deseleccionar el pill activo).

    `st.segmented_control` en modo `single` deja deseleccionar la opción activa con un
    segundo clic, y entonces `vd_tema_w` llega en `None`. Ese caso reafirma el valor
    anterior tanto en el espejo (`vd_tema`, lo que lee el resto de la app) como en el
    propio widget (para que el pill se vea seleccionado en el siguiente render)."""
    seleccion = st.session_state.get("vd_tema_w")
    if seleccion is None:
        st.session_state["vd_tema_w"] = st.session_state["vd_tema"]
    else:
        st.session_state["vd_tema"] = seleccion


def render_encabezado(con_datos: bool) -> str:
    """Fila superior: marca a la izquierda, tema a la derecha.

    En `con_datos=False` la marca no se dibuja aquí: el wordmark de `ui/carga.py` (`<h2>`)
    ya cumple ese papel como título de pantalla — mostrar ambos era redundante, así que la
    columna izquierda queda vacía durante la carga. Devuelve el tema activo — nunca `None`.
    """
    st.session_state.setdefault("vd_tema", "Claro")
    st.session_state.setdefault("vd_tema_w", st.session_state["vd_tema"])

    col_izq, col_der = st.columns([4, 2])
    with col_izq:
        if con_datos:
            st.markdown('<p class="vd-brand">Invierte &amp; Gana</p>', unsafe_allow_html=True)
    with col_der:
        st.segmented_control(
            "Tema", ("Claro", "Oscuro"), key="vd_tema_w", on_change=_sync_tema,
            label_visibility="collapsed",
        )

    return st.session_state["vd_tema"]


def _popover_segmento(columna, etiqueta_actual: str, opciones: dict, clave_actual: str,
                       prefijo: str, on_select) -> None:
    """Un segmento de la ruta: botón que muestra la selección activa y abre un popover
    con las alternativas. Es lo más cercano al `crumb-btn` del demo que devuelve estado
    a Python — a diferencia del HTML, que no puede.

    Sin flecha en el label: Streamlit ya dibuja su propio chevron en `st.popover`, y el
    `▾` del demo (que es texto, no un ícono nativo) duplicaba el símbolo."""
    with columna:
        with st.popover(etiqueta_actual, use_container_width=True):
            for clave, texto in opciones.items():
                marca = " ●" if clave == clave_actual else ""
                if st.button(f"{texto}{marca}", key=f"{prefijo}_{clave}",
                             use_container_width=True):
                    on_select(clave)
                    st.session_state["vd_metodologia"] = False
                    st.rerun()


def render_ruta() -> Ruta:
    """Ruta horizontal funcional Categoría › Vista › ETF, un popover por segmento.

    Sustituye a `render_crumb` (decorativo) y a la barra lateral: es el único navegador.
    El segmento ETF solo aparece si la vista activa es Cash flow y la categoría tiene ETFs
    (Dividendos · Largo Plazo); Comparación y Método tradicional no lo llevan.
    """
    st.session_state.setdefault("vd_categoria", CAT_ORDER_TOTAL[0])
    categoria = st.session_state.vd_categoria

    orden = _orden(categoria)
    if st.session_state.get("vd_vista") not in orden:
        st.session_state.vd_vista = orden[0]
    vista = st.session_state.vd_vista
    vistas = _vistas(categoria)

    # El ETF activo se resuelve para TODA categoría con ETFs, no solo Cash flow: Salud
    # NAV y Hoja Excel siguen necesitando saber de qué ticker hablan, aunque el demo
    # oculte el tercer segmento del breadcrumb en esas dos vistas (`showTab`: `var
    # conEtf = (name === "viaje")`). `con_etf` gobierna solo si se DIBUJA el popover;
    # `tiene_etf` gobierna si existe un ETF de contexto que resolver.
    tiene_etf = categoria in nav.CATS
    con_etf = vista == nav.VISTA_CON_ETF and tiene_etf
    etf = None
    clave_etf = f"vd_etf_{categoria}"
    if tiene_etf:
        etfs = nav.CATS[categoria]
        if st.session_state.get(clave_etf) not in etfs:
            st.session_state[clave_etf] = etfs[0]
        etf = st.session_state[clave_etf]

    kinds = ["cat", "sep", "vista"]
    if con_etf:
        kinds += ["sep", "etf"]
    kinds += ["ayuda"]
    columnas = st.columns(len(kinds))

    for columna, kind in zip(columnas, kinds):
        if kind == "sep":
            with columna:
                st.markdown('<span class="vd-sep">|</span>', unsafe_allow_html=True)
        elif kind == "cat":
            def _elegir_categoria(clave):
                st.session_state.vd_categoria = clave
            _popover_segmento(columna, CAT_LABELS_TOTAL[categoria], CAT_LABELS_TOTAL,
                              categoria, "vd_pop_cat", _elegir_categoria)
        elif kind == "vista":
            def _elegir_vista(clave):
                st.session_state.vd_vista = clave
            _popover_segmento(columna, vistas[vista], vistas, vista,
                              f"vd_pop_vis_{categoria}", _elegir_vista)
        elif kind == "etf":
            def _elegir_etf(clave, _clave_etf=clave_etf):
                st.session_state[_clave_etf] = clave
            _popover_segmento(columna, etf, {e: e for e in nav.CATS[categoria]}, etf,
                              f"vd_pop_etf_{categoria}", _elegir_etf)
        elif kind == "ayuda":
            with columna:
                if st.button("¿CÓMO FUNCIONA? →", key="vd_ayuda"):
                    st.session_state["vd_metodologia"] = True
                    st.rerun()

    return Ruta(categoria=categoria, vista=vista, etf=etf,
                tema=st.session_state.get("vd_tema", "Claro"))


def render_placeholder(ruta: "Ruta | None" = None, titulo: str | None = None) -> None:
    """Superficie honesta mientras la vista no se porta (Fases 3-5), o para Metodología
    (fuera de alcance en esta entrega: título fijo, sin depender de una Ruta válida)."""
    st.markdown('<span class="vd-badge">En construcción</span>', unsafe_allow_html=True)
    titulo = titulo if titulo is not None else (ruta.vista_label if ruta else "")
    st.markdown(f'<h2 class="vd-title">{titulo}</h2>', unsafe_allow_html=True)
    st.markdown(
        '<p class="vd-lede">La navegación y el sistema visual del artifact ya están '
        'activos. El contenido de esta vista llega en fases posteriores del port.</p>',
        unsafe_allow_html=True,
    )


_ESTILOS = """
        * { box-sizing: border-box; }
        html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"] {
          background: var(--ground); color: var(--ink);
          font-family: var(--font-sans); -webkit-font-smoothing: antialiased;
        }
        [data-testid="stHeader"], [data-testid="stToolbar"], footer { visibility: hidden; }
        .block-container { max-width: 940px; padding-top: 2rem; padding-bottom: 4rem; }

        .vd-brand {
          font-family: var(--font-mono); font-size: 13px; font-weight: 700;
          letter-spacing: .12em; text-transform: uppercase; color: var(--ink); margin: 0;
        }
        .vd-wordmark {
          text-transform: uppercase; letter-spacing: .10em;
          font-size: clamp(20px, 3vw, 27px);
        }

        .vd-sep { color: var(--ink-mut); opacity: .6; font-size: 13px; margin: 0 6px; }

        /* ---- Ruta funcional: un st.popover por segmento. La fila de columnas es la
           misma superficie que la página — fondo --ground exacto, borde dashed — y las
           columnas abrazan su contenido en vez de repartirse el ancho, como el .crumb
           del demo. ---- */
        [data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) {
          border: 1px dashed var(--hair); background: var(--ground);
          padding: 13px 16px; flex-wrap: wrap; align-items: center;
        }
        [data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) > div {
          flex: 0 0 auto; width: auto; min-width: 0;
        }
        [data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) > div:last-child {
          margin-left: auto;
        }
        /* El botón «¿Cómo funciona? →» es un st.button sin popover: por defecto
           Streamlit envuelve su texto, y con la columna a flex-basis:auto eso colapsa
           el ancho al carácter más angosto (una letra por línea). nowrap le da al
           flex-basis su medida real. */
        [data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) button {
          white-space: nowrap;
        }

        [data-testid="stPopoverButton"] {
          font-family: var(--font-mono); font-size: 12px; letter-spacing: .06em;
          text-transform: uppercase; background: none; border: 1px solid transparent;
          border-radius: 0; color: var(--ink);
        }
        [data-testid="stPopoverButton"]:hover { border-color: var(--accent); }
        /* Streamlit 1.42.0 no expone aria-expanded en este botón (verificado en el
           bundle): el estado "abierto" solo se distingue por el hover, no hay forma de
           engancharlo por CSS puro sin JS. */

        /* La superficie del menú: `stPopoverBody` trae de fábrica la paleta cálida de
           `app.py` (bg #fcf9f8, radio 12px, sombra suave) — es el propio contenedor de
           Streamlit, no algo que este archivo escribiera, así que `[data-baseweb="popover"]
           div` no lo alcanzaba. Aquí se sobreescribe con el `.crumb-menu` del demo:
           `background: var(--ground); border: 1px dashed var(--hair); border-radius: 0`.

           Un solo contenedor, sin marco anidado: `stPopoverBody` envuelve un `div` propio
           de BaseWeb (sin `data-testid`, medido en el navegador) que trae su fondo cálido
           de fábrica — ese es el "segundo marco" que se veía. Se sobreescribe con `> div`
           en vez de perseguir su clase generada (`st-be st-c9…`, cambia entre builds). Sin
           esto, el hueco de 16px entre botones (`stVerticalBlock` gap) deja ver ese fondo
           claro como una barra sólida entre cada fila — el defecto en modo oscuro. */
        [data-testid="stPopoverBody"] {
          background: var(--ground) !important;
          border: 1px dashed var(--hair) !important;
          border-radius: 0 !important;
          box-shadow: 0 4px 20px rgba(0, 0, 0, .25) !important;
          padding: 4px !important;
        }
        [data-testid="stPopoverBody"] > div {
          background: var(--ground) !important;
        }
        /* El gap por defecto entre botones (16px, de `stVerticalBlock`) es lo que hacía
           ver cada opción como una fila alta y separada — se reduce a un solo trazo fino,
           sin bordes individuales por botón (interacción sutil en vez de recuadros). */
        [data-testid="stPopoverBody"] [data-testid="stVerticalBlock"] {
          gap: 1px !important;
        }
        [data-testid="stPopoverBody"] button {
          font-family: var(--font-mono); font-size: 12px; letter-spacing: .05em;
          text-transform: uppercase; text-align: left; justify-content: flex-start;
          border: none; border-radius: 0; background: var(--panel); color: var(--ink);
          min-height: 0; height: auto; padding: 9px 12px; line-height: 1.3;
        }
        /* Estado sutil: solo cambia texto/fondo, sin borde grueso alrededor de la opción. */
        [data-testid="stPopoverBody"] button:hover {
          background: var(--accent-tint); color: var(--accent);
        }

        [data-testid="stPopover"] button, [data-testid="stPopover"] div {
          border-radius: 0 !important;
        }

        /* «¿Cómo funciona? →»: enlace fantasma como `.crumb-help` en el demo — sin caja,
           solo colorea en hover. Es la última columna de la fila de la ruta (no lleva
           popover), así que se distingue por posición: `div:last-child` en esa fila. */
        [data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) > div:last-child button {
          background: none !important; border: none !important; box-shadow: none !important;
          color: var(--ink-mut) !important; padding: 6px 2px !important;
          font-family: var(--font-mono); font-size: 11px; font-weight: 600;
          letter-spacing: .04em; text-transform: uppercase;
        }
        [data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) > div:last-child button:hover {
          color: var(--accent) !important; text-decoration: underline;
        }

        /* Control de tema: `stButtonGroup` trae radio redondeado (8px en los extremos) y
           tipografía `system-ui` de fábrica — igual que el popover, es CSS propio de
           Streamlit y solo se ve midiendo el DOM, no con `grep` sobre este archivo. */
        [data-testid="stButtonGroup"] button {
          border-radius: 0 !important;
          font-family: var(--font-mono) !important; font-size: 11px !important;
          letter-spacing: .06em; text-transform: uppercase;
        }
        /* La opción NO seleccionada (`kind=segmented_control`, sin el sufijo `Active`)
           trae de fábrica el fondo cálido/casi blanco de `app.py` con texto casi blanco
           encima — ilegible en modo oscuro. La seleccionada (`…Active`) ya usa el azul de
           marca de `.streamlit/config.toml` y no se toca. */
        [data-testid="stButtonGroup"] [data-testid="stBaseButton-segmented_control"] {
          background: var(--panel) !important; color: var(--ink) !important;
          border-color: var(--hair) !important;
        }
        [data-testid="stButtonGroup"] [data-testid="stBaseButton-segmented_control"]:hover {
          background: var(--accent-tint) !important; color: var(--accent) !important;
        }

        .vd-badge {
          display: inline-block; font-family: var(--font-mono); font-size: 10.5px;
          font-weight: 700; letter-spacing: .1em; text-transform: uppercase;
          color: var(--accent); border: 1px solid var(--accent);
          padding: 4px 10px; margin-bottom: 18px;
        }
        .vd-title {
          font-family: var(--font-mono); font-size: clamp(20px, 3vw, 27px);
          font-weight: 700; letter-spacing: -.01em; line-height: 1.15;
          margin: 0 0 12px; color: var(--ink); max-width: 22ch;
        }
        .vd-lede {
          font-size: 15px; line-height: 1.55; color: var(--ink-2);
          max-width: 56ch; margin: 0;
        }

        /* Streamlit pinta h1-h6 con su propia fuente y gana por especificidad; hay que
           reafirmar la mono del artifact sobre el elemento, no solo sobre la clase. */
        h1.vd-title, h2.vd-title, .block-container h2.vd-title {
          font-family: var(--font-mono) !important;
        }

        /* `.streamlit/config.toml` lleva el tema de app.py (superficies cálidas) y lo
           comparte con producción, así que no se toca: se sobreescribe aquí. Sin esto los
           selectores salen rosados sobre el azul frío del artifact. */
        [data-baseweb="select"] > div,
        [data-baseweb="input"] > div {
          background: var(--panel) !important;
          border: 1px solid var(--hair) !important;
          color: var(--ink) !important;
        }
        [data-baseweb="popover"] li { background: var(--panel) !important; color: var(--ink) !important; }
        [data-baseweb="popover"] li:hover { background: var(--panel-tint) !important; }

        /* Sin border-radius en ningún componente: regla de marca IYG. */
        [data-baseweb="select"] > div, [data-baseweb="input"] > div,
        [data-baseweb="popover"] div, .stButton > button { border-radius: 0 !important; }

        @media (max-width: 640px) {
          .block-container { padding-top: 1.25rem; }
          [data-testid="stHorizontalBlock"]:has([data-testid="stButtonGroup"]) {
            flex-wrap: wrap;
          }
          [data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) {
            padding: 10px 12px;
          }
        }
"""
