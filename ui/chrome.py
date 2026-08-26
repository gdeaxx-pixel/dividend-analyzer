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
import streamlit.components.v1 as components

from ui import heredadas, nav
from ui.tokens import css_variables

_FLAG_CIERRE_POPOVER = "vd_forzar_cierre_popover"


def _pedir_cierre_popover() -> None:
    """Marca que, en el próximo render, hay que forzar el cierre de cualquier popover
    abierto. Streamlit no expone ninguna forma de cerrarlo desde Python en NINGUNA versión
    publicada (verificado contra el código fuente de 1.42.0 y 1.50.0, la última real en
    PyPI — su propio docstring dice que solo un clic FUERA del popover lo cierra). Por eso
    tras elegir una opción se queda flotando en pantalla, sin reposicionarse con el scroll
    (reportado por Daniel 2026-08-11). El cierre real ocurre en `_consumir_cierre_popover`,
    simulando ese clic afuera."""
    st.session_state[_FLAG_CIERRE_POPOVER] = True


def _consumir_cierre_popover() -> None:
    """Si el run anterior pidió cierre, inyecta un componente invisible que simula el clic
    fuera del popover. `components.html` siempre corre en un iframe sandboxed, así que hay
    que cruzar a `window.parent.document` para alcanzar el DOM real de la app — mismo motivo
    que documenta `Dividend — iframes de components.html se auto-dimensionan` en la memoria
    del agente. Se llama al inicio de `render_ruta`, y el flag se consume de inmediato para
    no interferir con popovers que el usuario siga usando en otro rerun cualquiera."""
    if not st.session_state.pop(_FLAG_CIERRE_POPOVER, False):
        return
    components.html(
        """<script>
        try {
          var doc = window.parent.document;
          ["mousedown", "mouseup", "click"].forEach(function (tipo) {
            doc.body.dispatchEvent(new MouseEvent(tipo, {bubbles: true, cancelable: true}));
          });
        } catch (e) {}
        </script>""",
        height=0,
    )

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
    «Largo Plazo» solo trae Cash flow (decisión de Daniel 2026-08-25): Salud NAV y
    Hoja Excel quedan exclusivas de Dividendos."""
    if categoria == "comparacion":
        return dict(nav.CMP_VIEWS)
    if categoria == "metodo":
        return dict(nav.MET_VIEWS)
    if categoria == heredadas.CAT_CLAVE:
        return dict(heredadas.VIEWS)
    if categoria == "largo":
        return {"viaje": nav.SECTIONS["viaje"]}
    return dict(nav.SECTIONS)


def _ancla_metodologia(categoria: str, vista: str) -> str | None:
    """A qué entrada de Metodología corresponde la vista activa — para que «¿Cómo
    funciona?» abra ya iluminando la sección relacionada con lo que se estaba
    consultando, en vez de siempre el índice general (decisión de Daniel 2026-08-10,
    mapeo confirmado en la misma sesión). `None` cuando no hay una entrada 1:1 clara
    (Comparación · Simulación, Detalle heredada): se abre sin resaltar, como antes."""
    if vista == nav.VISTA_CON_ETF and categoria in nav.CATS:
        return "mt-viaje"
    if vista == "salud" and categoria in nav.CATS:
        return "mt-nav"
    if vista == "hoja" and categoria in nav.CATS:
        return "mt-hoja"
    if categoria == "comparacion" and vista == "real":
        return "mt-tr"
    if categoria == "metodo":
        return "mt-metodo"
    return None


def _orden(categoria: str) -> tuple:
    if categoria == "comparacion":
        return nav.CMP_ORDER
    if categoria == "metodo":
        return nav.MET_ORDER
    if categoria == heredadas.CAT_CLAVE:
        return heredadas.VIEW_ORDER
    if categoria == "largo":
        return ("viaje",)
    return tuple(nav.SECTION_ORDER)


def inyectar_estilos(tema: str) -> None:
    """Inyecta los tokens del artifact para el tema activo, más los estilos del chrome
    y de la hoja de carga."""
    from ui.carga import ESTILOS_CARGA
    from ui.heredadas import ESTILOS_HEREDADAS
    from ui.pie import ESTILOS_PIE
    from ui.validacion import ESTILOS_VALIDACION

    st.markdown(
        f"<style>\n        {css_variables(tema)}\n{_ESTILOS}{ESTILOS_CARGA}{ESTILOS_PIE}"
        f"{ESTILOS_HEREDADAS}{ESTILOS_VALIDACION}</style>",
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
                    st.session_state["vd_panel"] = None
                    _pedir_cierre_popover()
                    st.rerun()


def render_ruta(alerta: bool = False, pdf_bytes: bytes | None = None,
                 pdf_filename: str = "") -> Ruta:
    """Ruta horizontal funcional Categoría › Vista › ETF, un popover por segmento.

    Sustituye a `render_crumb` (decorativo) y a la barra lateral: es el único navegador.
    El segmento ETF solo aparece si la vista activa es Cash flow y la categoría tiene ETFs
    (Dividendos · Largo Plazo); Comparación y Método tradicional no lo llevan.

    `alerta`/`pdf_bytes`/`pdf_filename` son datos ya resueltos por quien llama
    (`app.py`, vía `ui.validacion`): este módulo es solo presentación (docstring de
    arriba) y no calcula ni la confiabilidad ni el PDF — solo dibuja el menú de 3 puntos
    con lo que se le entrega.
    """
    _consumir_cierre_popover()

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

    # Categoría con una sola vista (Portafolios, decisión de Daniel 2026-08-26): no se
    # dibuja el segmento de vista — presentar directo, sin sub-menú de un solo elemento.
    unica_vista = len(vistas) <= 1

    kinds = ["cat"]
    if not unica_vista:
        kinds += ["sep", "vista"]
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
                clave_wrap = "vd_ayuda_alerta" if alerta else "vd_ayuda_sin_alerta"
                with st.container(key=clave_wrap):
                    with st.popover(""):
                        if st.button("¿Cómo funciona?", key="vd_menu_metodologia",
                                     use_container_width=True):
                            st.session_state["vd_panel"] = "metodologia"
                            st.session_state["vd_metodologia_anchor"] = (
                                _ancla_metodologia(categoria, vista))
                            _pedir_cierre_popover()
                            st.rerun()
                        marca = " ●" if alerta else ""
                        if st.button(f"Validación datos{marca}", key="vd_menu_validacion",
                                     use_container_width=True):
                            st.session_state["vd_panel"] = "validacion"
                            _pedir_cierre_popover()
                            st.rerun()
                        if pdf_bytes is not None:
                            st.download_button(
                                "Descargar reporte PDF", data=pdf_bytes,
                                file_name=pdf_filename or "auditoria-portafolio.pdf",
                                mime="application/pdf", key="vd_menu_pdf",
                                use_container_width=True)

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
        /* Caret fantasma al hacer clic en contenedores no-editables (reportado 2026-08-25):
           `section.stMain` (el contenedor principal) es focusable (`tabindex=0`) y con
           `user-select: auto`, así que el clic le pasa el foco y el navegador pinta el
           caret de inserción de texto. Se desactiva la selección en los contenedores
           estructurales — inputs, textareas, tablas y [contenteditable] conservan su
           comportamiento normal. */
        section[data-testid="stMain"], [data-testid="stAppViewContainer"],
        [data-testid="stHeader"], .block-container {
          user-select: none; -webkit-user-select: none;
        }
        input, textarea, [contenteditable="true"], [data-testid="stDataFrame"],
        [data-testid="stDataFrame"] *, [data-testid="stCode"], pre, code {
          user-select: text; -webkit-user-select: text;
        }
        html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"] {
          background: var(--ground); color: var(--ink);
          font-family: var(--font-sans); -webkit-font-smoothing: antialiased;
        }
        [data-testid="stHeader"], [data-testid="stToolbar"], footer { visibility: hidden; }
        /* `max-width: 940px` es el del artifact (`cashflow.html:88`). El padding lateral
           también: el `clamp` es literalmente el suyo. Sin esto Streamlit mete 80px por
           lado y deja 780px de contenido, cuando el artifact dibuja con 860px — y el rail
           de 8 pasos no cabe por 10px. */
        .block-container {
          max-width: 940px; padding-top: 2rem; padding-bottom: 4rem;
          padding-left: clamp(16px, 4vw, 40px); padding-right: clamp(16px, 4vw, 40px);
        }

        /* Rail de 8 pasos: barra de progreso + etiqueta, calcado del `.step` del artifact
           (`ui/componentes/cashflow.html:213-224`). Gap 10px y padding del contenedor a
           40px son la geometría del artifact: con ellos cada paso mide 98.8px y la
           etiqueta más larga («Reinv + Efvo», 94px a 9.5px) entra con 4.8px de holgura,
           así que `nowrap` nunca parte ni envuelve. El estado llega por la clave del
           contenedor de cada paso (`…_done` / `…_now` / `…_todo`), porque `st.button`
           solo distingue dos tipos y aquí hacen falta tres. */
        .st-key-vd_paso_wrap [data-testid="stHorizontalBlock"] { gap: 10px; }
        .st-key-vd_paso_wrap .stButton > button {
          background: transparent !important;
          border: none !important;
          border-top: 4px solid var(--hair) !important;
          border-radius: 0 !important;
          box-shadow: none !important;
          min-height: 0 !important;
          padding: 7px 0 0 0 !important;
          font-family: var(--font-mono) !important;
          font-size: 9.5px !important;
          letter-spacing: .03em !important;
          text-transform: uppercase !important;
          line-height: 1.25 !important;
          color: var(--ink-mut) !important;
          white-space: nowrap !important;
          justify-content: center !important;
        }
        .st-key-vd_paso_wrap [class*="_done"] .stButton > button {
          border-top-color: var(--accent) !important; color: var(--ink-2) !important;
        }
        .st-key-vd_paso_wrap [class*="_now"] .stButton > button {
          border-top-color: var(--loss) !important; color: var(--loss) !important;
          font-weight: 700 !important;
        }
        .st-key-vd_paso_wrap .stButton > button:hover { color: var(--accent) !important; }
        .st-key-vd_paso_wrap [class*="_now"] .stButton > button:hover {
          color: var(--loss) !important;
        }
        /* Leyenda del rail móvil (`render_rail` en `ui/componentes/__init__.py`).
           Oculta en desktop: ahí cada paso ya trae su propia etiqueta. */
        .vd-rail-legend { display: none; }

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
           del demo. `flex-wrap: wrap` partía la fila en dos (MSTY caía a una segunda
           línea) en cuanto los tres popovers no cabían de corrido (~500-650px); con
           `nowrap` + `overflow-x: auto` la fila se mantiene en una sola línea y, si no
           entra, se desliza horizontalmente en vez de apilarse. */
        [data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) {
          border: 1px dashed var(--hair); background: var(--ground);
          padding: 13px 16px; flex-wrap: nowrap; overflow-x: auto; align-items: center;
        }
        [data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) > div {
          flex: 0 0 auto; width: auto; min-width: 0; margin-left: 0;
        }
        /* La columna del menú de 3 puntos colapsa a 15px en las rutas sin ETF (3
           columnas: Método tradicional · Comparación · Detalle) — el `width: auto` de
           la regla de arriba dimensiona por contenido, pero los contenedores internos
           de Streamlit traen `flex: 1 1 0%` (base cero), así que el contenido aporta 0 y
           la columna se colapsa; `max-content` no sirve por la misma circularidad. Antes
           este botón era texto («¿CÓMO FUNCIONA? →», 153.4px) y necesitaba 170px de
           min-width; ahora es un `st.popover("")` sin label — solo el chevron nativo de
           Streamlit — así que se deja un mínimo cómodo de click sin heredar ese número,
           que ya no aplica a este contenido.

           Anclaje por clave, no por posición: antes esta regla era `> div:last-child`.
           Medido en el DOM (2026-08-18, Comparación›Simulación de 3 columnas y
           Dividendos›Cash flow›MSTY de 5): la columna de ayuda SÍ es hoy el último hijo
           en las cuatro formas de la ruta, así que `:last-child` "funcionaba" — pero por
           coincidencia posicional, no por identidad. Cualquier columna nueva que se
           agregue al final (o un reordenamiento futuro) se robaría el `margin-left: auto`
           en silencio, sin que nada lo señale hasta que alguien lo note en pantalla. Se
           ancla por la clave estable del contenedor (`st.container(key=…)`,
           líneas 268-269) con el mismo patrón `:has()` que ya usa este archivo. El
           `margin-left: 0` explícito de la regla de arriba evita que alguna columna
           intermedia también reciba espacio libre por herencia. */
        [data-testid="stHorizontalBlock"]:has([data-testid="stPopover"])
          > div:has(:is(.st-key-vd_ayuda_alerta, .st-key-vd_ayuda_sin_alerta)) {
          margin-left: auto; min-width: 48px; text-align: right;
        }
        /* El separador "|" vive en una columna Streamlit completa (mínimo ~130px por el
           min-width interno de los popovers vecinos) y centrado ahí se ve como un hueco
           enorme entre segmentos — notorio desde que «Método tradicional» quedó con solo
           dos vistas (2026-08-24). Su celda abrazará el carácter: min-content. */
        [data-testid="stHorizontalBlock"]:has([data-testid="stPopover"])
          > div:has(.vd-sep) {
          flex: 0 0 auto; width: min-content;
          display: flex; align-items: center; justify-content: center;
        }
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
           `app_old.py` (bg #fcf9f8, radio 12px, sombra suave) — es el propio contenedor de
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

        /* Menú de ayuda: mockup opción A (aprobado por Daniel 2026-08-18). Antes era un
           enlace fantasma como `.crumb-help` del demo — sin caja, `color: var(--ink-mut)`
           (bajo contraste) — y con `margin-left: auto` empujando la columna al borde
           derecho, el chevron quedaba solo en medio del vacío: así es como Daniel lo
           reportó como "desaparecido" (medido en el DOM: `color: rgb(106,123,138)`, sin
           borde, sin fondo — invisible contra el `--ground`). Ahora es un chevron DENTRO
           de una caja de borde fino, mismo trato que los otros segmentos de la ruta
           (borde + `var(--accent)` en hover), para que se lea como parte del mismo menú
           en vez de perderse en el hueco a la derecha. Antes vestía el botón de texto
           «¿Cómo funciona? →»; ahora el botón no lleva label (`st.popover("")`, Daniel
           pidió solo el chevron nativo, sin el «⋮» que se probó primero) — el chevron
           escala en `em`, por eso el tamaño de fuente mayor al resto de la fila.
           Selector por clave (Paso 1), no por posición. */
        [data-testid="stHorizontalBlock"]:has([data-testid="stPopover"])
          :is(.st-key-vd_ayuda_alerta, .st-key-vd_ayuda_sin_alerta) [data-testid="stPopoverButton"] {
          background: none !important; border: 1px solid var(--hair) !important;
          box-shadow: none !important; color: var(--ink) !important;
          padding: 4px 8px !important; font-size: 16px; line-height: 1;
          border-radius: 0 !important;
        }
        [data-testid="stHorizontalBlock"]:has([data-testid="stPopover"])
          :is(.st-key-vd_ayuda_alerta, .st-key-vd_ayuda_sin_alerta) [data-testid="stPopoverButton"]:hover {
          border-color: var(--accent) !important; color: var(--accent) !important;
        }
        /* Punto de aviso del menú (`ui.validacion.hay_alertas`, vía `render_ruta`): solo
           se pinta cuando SÍ hay algo que revisar en Validación datos — decisión de
           Daniel (mockup aprobado 2026-08-10): nada ocupa espacio en la página, pero el
           punto no pasa inadvertido. Contenedor con clave (`st.container(key=...)`,
           mismo patrón que el rail) porque el botón del popover no acepta HTML propio. */
        .st-key-vd_ayuda_alerta [data-testid="stPopoverButton"] {
          position: relative;
        }
        .st-key-vd_ayuda_alerta [data-testid="stPopoverButton"]::after {
          content: ""; position: absolute; top: 4px; right: 2px;
          width: 6px; height: 6px; border-radius: 50%; background: var(--warn);
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
           trae de fábrica el fondo cálido/casi blanco de `app_old.py` con texto casi blanco
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

        /* `.streamlit/config.toml` lleva el tema de app_old.py (superficies cálidas) y lo
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
          /* La fila de la ruta usa `nowrap` + `overflow-x: auto` (línea 385) para no
             reintroducir el bug de #47 (partirse en dos líneas). Pero con
             `margin-left: auto` en la columna de ayuda, una ruta larga que desborda en
             pantalla angosta (`Dividendos | Cash flow | MSTY`, 5 columnas) empuja el
             chevron fuera del área visible: solo aparece deslizando la fila, y el menú
             de ayuda debe estar siempre alcanzable sin scroll. Se anula el
             `margin-left: auto` aquí para que la columna de ayuda quede pegada a los
             segmentos en vez de proyectarse al ancho completo del contenedor. */
          [data-testid="stHorizontalBlock"]:has([data-testid="stPopover"])
            > div:has(:is(.st-key-vd_ayuda_alerta, .st-key-vd_ayuda_sin_alerta)) {
            margin-left: 0 !important;
          }
          /* Rail móvil: mockup aprobado por Daniel (diseñado 2026-08-09, sesión de
             correcciones de forma). Por debajo de 640px Streamlit apila `st.columns(8)`
             de fábrica y el rail pasaba a 8 cajas de ancho completo (~300px de alto) que
             ya no comunican progreso. Se fuerza la fila de vuelta a horizontal — mismos
             8 segmentos de 4px, sin etiqueta por paso (a ~34px de columna no cabe
             ningún texto) — y la leyenda `.vd-rail-legend` de `render_rail` pasa a ser
             la única fuente de "dónde vas". Cada columna sigue siendo tocable
             (~34px de ancho), solo se oculta el texto que ya no cabe.
             `stColumn` trae de fábrica `min-width: calc(100% - 24px)` para apilarse junto
             con el `flex-wrap: wrap` del padre — es lo que lo dispara. Forzar `nowrap` sin
             tocar ese `min-width` no apila, DESBORDA (cada columna insiste en medir ~93%
             del ancho del contenedor, el row termina de 2500px+ con `overflow-x: visible`
             heredado, y solo la primera columna queda dentro del viewport). Hay que anular
             también el `min-width` y devolverle un `flex-basis` igual por columna. */
          .st-key-vd_paso_wrap [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            gap: 4px !important;
          }
          .st-key-vd_paso_wrap [data-testid="stColumn"] {
            min-width: 0 !important;
            width: auto !important;
            flex: 1 1 0 !important;
          }
          .st-key-vd_paso_wrap .stButton > button {
            padding: 7px 0 6px 0 !important;
          }
          .st-key-vd_paso_wrap .stButton > button p { display: none !important; }
          .vd-rail-legend {
            display: block;
            margin-top: 8px;
            text-align: center;
            font-family: var(--font-mono);
            font-size: 11px;
            letter-spacing: .03em;
            text-transform: uppercase;
            color: var(--ink-mut);
          }
        }
"""
