"""Chrome del port: encabezado + ruta funcional Categoría › Vista › ETF.

Toda la taxonomía y todos los colores vienen de `ui/nav.py` y `ui/tokens.py`, que se
GENERAN del demo (`tools/extract_design_system.py`). Aquí no se escribe a mano ni un
nombre de vista ni un color: si algo no coincide con el artifact, se corrige en el demo
y se regenera.

Fase 3b: la barra lateral desaparece. La ruta pasa a ser el único navegador — cada
segmento (Categoría / Vista) es un `st.popover` con botones nativos dentro, y el ETF una
fila de botones directos (`st.segmented_control`); ambos devuelven estado a Python (a diferencia del HTML del artifact). El tema se mueve al
encabezado, arriba a la derecha.

Solo presentación — sin datos ni cálculos.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from ui import estado, heredadas, impuestos, nav, riesgo
from ui.tokens import css_variables

_FLAG_CIERRE_POPOVER = "vd_forzar_cierre_popover"
_CUENTA_CIERRE_POPOVER = "vd_cierre_popover_n"
_CUENTA_SUBIDA = "vd_subida_inicio_n"
_CLAVE_TEMA_AUTO = "vd_tema_auto"
# Huecos de la cabecera que llena `render_ruta`: la cabecera se dibuja antes de calcular los
# resultados (para que ROC «calcule» arriba) y la confiabilidad sale de esos resultados.
HUECO_ESTADO = "_vd_hueco_estado"
HUECO_AYUDA = "_vd_hueco_ayuda"


def _pedir_cierre_popover() -> None:
    """Marca que, en el próximo render, hay que forzar el cierre de cualquier popover
    abierto. Sin esto, tras elegir una opción se queda flotando en pantalla, sin
    reposicionarse con el scroll (reportado por Daniel 2026-08-11). Hasta 1.50 Streamlit no
    tenía forma de cerrarlo desde Python; 1.66 sí (`key` + `on_change="rerun"` y
    `st.session_state[key] = False`), pero reejecuta la app cada vez que se abre o se cierra
    el menú. Por eso el cierre real sigue en `_consumir_cierre_popover`, simulando un clic
    afuera."""
    st.session_state[_FLAG_CIERRE_POPOVER] = True


def _consumir_cierre_popover() -> None:
    """Si el run anterior pidió cierre, inyecta un script invisible que simula el clic
    fuera del popover. `st.html` con `unsafe_allow_javascript` lo corre en el documento de
    la app, sin iframe, así que alcanza el DOM real directamente (antes iba en un
    `components.html` de alto 0 que tenía que cruzar a `window.parent.document`). Se llama
    al inicio de `render_ruta`, y el flag se consume de inmediato para no interferir con
    popovers que el usuario siga usando en otro rerun cualquiera."""
    if not st.session_state.pop(_FLAG_CIERRE_POPOVER, False):
        return
    # Dos condiciones, medidas el 30-oct en el navegador (sin ellas cerraba 11 de 48):
    # - Un cuerpo distinto en cada cierre: un rerun cortado por `st.rerun()` no retira el
    #   script anterior y, si el nuevo llega idéntico, no se vuelve a ejecutar.
    # - `pointerdown` antes del clic: el popover de Streamlit 1.66 decide «clic de fuera»
    #   con el último `pointerdown`, que era el del usuario DENTRO del menú.
    n = st.session_state.get(_CUENTA_CIERRE_POPOVER, 0) + 1
    st.session_state[_CUENTA_CIERRE_POPOVER] = n
    st.html(
        f"<script>/* cierre {n} */</script>" + """<script>
        try {
          ["pointerdown", "mousedown", "pointerup", "mouseup", "click"].forEach(function (tipo) {
            var Evento = tipo.indexOf("pointer") === 0 ? PointerEvent : MouseEvent;
            document.body.dispatchEvent(new Evento(tipo, {bubbles: true, cancelable: true}));
          });
        } catch (e) {}
        </script>""",
        unsafe_allow_javascript=True,
    )


def _subir_al_inicio_si_toca() -> None:
    """Si «Ver resultados →» lo pidió (`ui.estado.pedir_subir_al_inicio`), lleva arriba el
    contenedor que desplaza la app (`stMain`). Mismo mecanismo que `_consumir_cierre_popover`:
    `st.html` con JavaScript corre en el documento de la app, y el cuerpo cambia en cada
    subida porque un script idéntico al anterior no se vuelve a ejecutar."""
    if not estado.consumir_subir_al_inicio():
        return
    n = st.session_state.get(_CUENTA_SUBIDA, 0) + 1
    st.session_state[_CUENTA_SUBIDA] = n
    st.html(
        f"<script>/* subida {n} */</script>" + """<script>
        try {
          var principal = document.querySelector('[data-testid="stMain"]');
          if (principal) principal.scrollTo(0, 0);
          window.scrollTo(0, 0);
        } catch (e) {}
        </script>""",
        unsafe_allow_javascript=True,
    )

# Categorías «Portafolios», «Riesgo» e «Impuestos» compuestas sobre la taxonomía generada:
# `ui/nav.py` es el espejo verificable del artifact (el demo solo tiene 4 categorías) y no
# se edita para meterlas ahí — se componen aquí, en tiempo de import, sin tocar el
# generador (traspaso § Fase 5, y § Fase 2 de la vista fiscal para «Impuestos»).
#
# El ORDEN importa: `CAT_ORDER_TOTAL[0]` es la categoría de aterrizaje por defecto (commit
# `bec1061`, decisión de Daniel) y debe seguir siendo «Portafolios». El resto sigue el orden
# del menú que pidió Daniel (2026-09-28): Largo Plazo antes que Dividendos, «Impuestos» al
# final; y el 2026-10-28 «Riesgo» pasa a ser su propia categoría, en segundo lugar.
# `CAT_LABELS_TOTAL` se construye EN ese orden porque el popover recorre el dict: antes
# se armaba desde `nav.CAT_LABELS` y Portafolios salía quinto aunque fuera el aterrizaje.
CAT_ORDER_TOTAL = (heredadas.CAT_CLAVE, riesgo.CAT_CLAVE, "largo", "dividendos", "comparacion",
                   "metodo", impuestos.CAT_CLAVE)
_LABELS = {**nav.CAT_LABELS, heredadas.CAT_CLAVE: heredadas.CAT_LABEL,
           riesgo.CAT_CLAVE: riesgo.CAT_LABEL, impuestos.CAT_CLAVE: impuestos.CAT_LABEL}
assert set(CAT_ORDER_TOTAL) == set(_LABELS), "CAT_ORDER_TOTAL y las etiquetas divergen"
CAT_LABELS_TOTAL = {clave: _LABELS[clave] for clave in CAT_ORDER_TOTAL}


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
    """Vistas de una categoría. Comparación y Método tienen las suyas; «Largo Plazo» y
    «Dividendos» solo traen Cash flow (decisión de Daniel 2026-09-08): Salud NAV y Hoja
    Excel se retiran de la navegación — se llega directo al ticker desde la categoría."""
    if categoria == "comparacion":
        return dict(nav.CMP_VIEWS)
    if categoria == "metodo":
        return dict(nav.MET_VIEWS)
    if categoria == heredadas.CAT_CLAVE:
        return dict(heredadas.VIEWS)
    if categoria == riesgo.CAT_CLAVE:
        return dict(riesgo.VIEWS)
    if categoria == impuestos.CAT_CLAVE:
        return dict(impuestos.VIEWS)
    if categoria in ("largo", "dividendos"):
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
    # «Impuestos» no tiene todavía una entrada 1:1 en Metodología: se abre sin resaltar.
    return None


# Vistas que muestran el caso de estudio de la clase, no el archivo del cliente (P7,
# 30-oct): `render_comparacion_simulacion` y `render_metodo_tradicional` no leen el CSV.
_VISTAS_DE_EJEMPLO = {("comparacion", "simulacion"), ("metodo", "matriz")}


def _orden(categoria: str) -> tuple:
    if categoria == "comparacion":
        orden = nav.CMP_ORDER
    elif categoria == "metodo":
        orden = nav.MET_ORDER
    elif categoria == heredadas.CAT_CLAVE:
        return heredadas.VIEW_ORDER
    elif categoria == riesgo.CAT_CLAVE:
        return riesgo.VIEW_ORDER
    elif categoria == impuestos.CAT_CLAVE:
        return impuestos.VIEW_ORDER
    elif categoria in ("largo", "dividendos"):
        return ("viaje",)
    else:
        return tuple(nav.SECTION_ORDER)
    # Con archivo, la vista con tus datos va primero y es la que se abre (P7). Sin archivo
    # (Riesgo sin CSV) Real y Matriz 2 no tienen qué dibujar: se queda el orden del demo.
    if riesgo.sin_archivo():
        return tuple(orden)
    return tuple(sorted(orden, key=lambda v: (categoria, v) in _VISTAS_DE_EJEMPLO))


def _origen(categoria: str, vista: str) -> tuple[str, str]:
    """(clase, texto) de la etiqueta que dice de dónde salen las cifras de la vista (P7)."""
    if (categoria, vista) in _VISTAS_DE_EJEMPLO or riesgo.sin_archivo():
        return "ejemplo", "Caso de ejemplo"
    return "tus", "Con tus datos"


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


def _alternar_tema() -> None:
    """`on_click` del botón de tema de la cabecera (P8, 30-oct): antes era un control de dos
    opciones que en el teléfono ocupaba una fila entera."""
    st.session_state["vd_tema"] = "Oscuro" if st.session_state.get("vd_tema") == "Claro" else "Claro"


def _tema_del_sistema_una_vez() -> None:
    """Primera corrida de la visita: si el dispositivo está en modo oscuro, pulsa el botón de
    tema (P8). `.streamlit/config.toml` fija el tema de Streamlit en claro, así que el
    servidor no puede leer esa preferencia: la lee el navegador. Una sola vez por sesión,
    para no pelear con el cliente si después lo cambia a mano."""
    if st.session_state.get(_CLAVE_TEMA_AUTO):
        return
    st.session_state[_CLAVE_TEMA_AUTO] = True
    if st.session_state.get("vd_tema") != "Claro":
        return
    st.html(
        """<script>
        try {
          if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
            var intentos = 0;
            (function pulsar() {
              var boton = document.querySelector(".st-key-vd_tema_btn button");
              if (boton) { boton.click(); return; }
              if (++intentos < 40) setTimeout(pulsar, 50);
            })();
          }
        } catch (e) {}
        </script>""",
        unsafe_allow_javascript=True,
    )


def _con_datos(stats) -> bool:
    return bool(stats) and not stats.get("skipped")


def etfs_habilitados(resultados: dict) -> dict:
    """Por categoría con ETFs, los tickers de `nav.CATS` que el archivo trae con datos —
    el mismo criterio con el que `ui.vistas._stats_o_aviso` dibuja «X no está en tu
    archivo». La ruta solo ofrece estos (decisión de Daniel 2026-09-29): Cash flow solo
    sabe dibujar los tickers de la lista fija, así que no se añade ninguno de fuera."""
    return {cat: tuple(t for t in etfs if _con_datos(resultados.get(t)))
            for cat, etfs in nav.CATS.items()}


def _sync_etf(categoria: str) -> None:
    """`on_change` de los botones de ETF: un segundo clic sobre el activo lo deselecciona y
    llega `None`; ahí se conserva el ETF anterior."""
    seleccion = st.session_state.get(f"vd_etf_w_{categoria}")
    if seleccion is not None:
        st.session_state[f"vd_etf_{categoria}"] = seleccion
        st.session_state["vd_panel"] = None


def _sync_categoria() -> None:
    """`on_change` de la fila de secciones (P1). `required=True` impide deseleccionar."""
    st.session_state["vd_categoria"] = st.session_state["vd_cat_w"]
    st.session_state["vd_panel"] = None


def _sync_vista(categoria: str) -> None:
    """`on_change` de la fila de vistas de Comparación y Método tradicional (P1)."""
    st.session_state["vd_vista"] = st.session_state[f"vd_vista_w_{categoria}"]
    st.session_state["vd_panel"] = None


def render_encabezado(con_datos: bool) -> str:
    """Fila superior en una sola línea (P8, 30-oct): marca con ROC a la izquierda; a la
    derecha, la confiabilidad, «Cambiar datos», «Ayuda» y el botón de tema.

    Con datos, ROC es el ÚNICO búho de la pantalla: aquí solo se reserva su hueco
    (`HUECO_ROC_VISTA`) y lo llena la vista con su estado (`roc_de_vista`) o, si ninguna lo
    hizo, `cerrar_roc_encabezado`. Igual con `HUECO_ESTADO` y `HUECO_AYUDA`: los llena
    `render_ruta`, que es quien recibe la confiabilidad ya calculada. En `con_datos=False`
    la marca no se dibuja aquí: el wordmark de `ui/carga.py` (`<h2>`) ya cumple ese papel.
    Devuelve el tema activo — nunca `None`.
    """
    from ui.componentes import HUECO_ROC_VISTA  # dentro: `ui.chrome` ↔ `ui.componentes` es un ciclo

    st.session_state.setdefault("vd_tema", "Claro")
    # Antes del cálculo de resultados, no después: así la pantalla de espera ya sale arriba.
    _subir_al_inicio_si_toca()
    _tema_del_sistema_una_vez()

    # `horizontal_alignment="right"`: en la carga la cabecera solo lleva el tema, y debe
    # quedar a la derecha (un contenedor vacío como relleno no se dibuja y no empuja nada).
    with st.container(horizontal=True, vertical_alignment="center", gap="small",
                      horizontal_alignment="right", key="vd_cabecera"):
        if con_datos:
            with st.container(horizontal=True, vertical_alignment="center", gap="medium",
                              wrap=False, key="vd_marca"):
                st.markdown('<p class="vd-brand">Invierte &amp; Gana</p>',
                            unsafe_allow_html=True, width="content")
                st.session_state[HUECO_ROC_VISTA] = st.empty()
            st.session_state[HUECO_ESTADO] = st.empty()
            st.session_state[HUECO_AYUDA] = st.empty()
        oscuro = st.session_state["vd_tema"] == "Oscuro"
        st.button("", key="vd_tema_btn", type="tertiary", on_click=_alternar_tema,
                  icon=":material/light_mode:" if oscuro else ":material/dark_mode:",
                  help="Cambiar a tema claro" if oscuro else "Cambiar a tema oscuro")

    return st.session_state["vd_tema"]


def _render_estado(alerta: bool, confiabilidad: str | None) -> None:
    """Confiabilidad visible (P1) y «Cambiar datos» (P2). Antes la confiabilidad era un punto
    de 4px sobre un botón sin nombre, y desde resultados no había forma de volver a la carga:
    Impuestos pedía declarar el país en un paso al que no se llegaba."""
    hueco = st.session_state.pop(HUECO_ESTADO, None) or st.empty()
    with hueco.container(horizontal=True, vertical_alignment="center", gap="small",
                         width="content", key="vd_estado"):
        if alerta:
            texto = f"Confiabilidad {confiabilidad.lower()}" if confiabilidad else "Revisa tus datos"
            if st.button(texto, key="vd_chip_confiabilidad", type="tertiary"):
                st.session_state["vd_panel"] = "validacion"
                st.rerun()
        if not riesgo.sin_archivo():
            if st.button("Cambiar datos", key="vd_cambiar_datos", type="tertiary"):
                # La carga conserva lo ya subido (archivo, posiciones, país): solo se reabre.
                st.session_state["_wizard_listo"] = False
                st.session_state["vd_panel"] = None
                estado.pedir_subir_al_inicio()
                st.rerun()


def _render_ayuda(alerta: bool, categoria: str, vista: str) -> None:
    """«¿Cómo funciona?» y «Validación datos» bajo un menú con nombre (P1): antes era un
    chevron sin texto."""
    hueco = st.session_state.pop(HUECO_AYUDA, None) or st.empty()
    with hueco.container(width="content", key="vd_ayuda"):
        with st.popover("Ayuda", icon=":material/help:"):
            if st.button("¿Cómo funciona?", key="vd_menu_metodologia",
                         use_container_width=True):
                st.session_state["vd_panel"] = "metodologia"
                st.session_state["vd_metodologia_anchor"] = _ancla_metodologia(categoria, vista)
                _pedir_cierre_popover()
                st.rerun()
            marca = " ●" if alerta else ""
            if st.button(f"Validación datos{marca}", key="vd_menu_validacion",
                         use_container_width=True):
                st.session_state["vd_panel"] = "validacion"
                _pedir_cierre_popover()
                st.rerun()


def render_ruta(alerta: bool = False, habilitados: dict | None = None,
                confiabilidad: str | None = None) -> Ruta:
    """Navegación visible (P1, 30-oct): una fila con las secciones siempre a la vista y,
    debajo, las vistas de la sección (Comparación, Método tradicional) o sus fondos
    (Dividendos, Largo plazo), con la etiqueta de dónde salen las cifras (P7). Antes las
    secciones y las vistas vivían en dos popovers y un cliente nuevo solo veía la activa.

    `habilitados` (de `etfs_habilitados`) limita los botones de ETF a los que trae el
    archivo, y una categoría con ETFs que no tiene ninguno se oculta del menú. `None`
    ofrece la lista fija completa.

    `alerta` y `confiabilidad` son datos ya resueltos por quien llama (`app.py`, vía
    `ui.validacion`): este módulo es solo presentación y no calcula la confiabilidad.
    """
    _consumir_cierre_popover()

    if habilitados is None:
        habilitados = dict(nav.CATS)
    categorias = {c: texto for c, texto in CAT_LABELS_TOTAL.items()
                  if c not in nav.CATS or habilitados.get(c)}

    st.session_state.setdefault("vd_categoria", CAT_ORDER_TOTAL[0])
    if st.session_state.vd_categoria not in categorias:
        st.session_state.vd_categoria = CAT_ORDER_TOTAL[0]
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
        etfs = habilitados[categoria]
        if st.session_state.get(clave_etf) not in etfs:
            st.session_state[clave_etf] = etfs[0]
        etf = st.session_state[clave_etf]

    # Categoría con una sola vista (Portafolios, decisión de Daniel 2026-08-26): no se
    # dibuja la fila de vistas — presentar directo, sin sub-menú de un solo elemento.
    unica_vista = len(vistas) <= 1

    _render_estado(alerta, confiabilidad)
    _render_ayuda(alerta, categoria, vista)

    with st.container(key="vd_secciones"):
        st.session_state["vd_cat_w"] = categoria
        st.segmented_control(
            "Sección", tuple(categorias), format_func=categorias.get, key="vd_cat_w",
            on_change=_sync_categoria, label_visibility="collapsed", required=True,
        )

    with st.container(horizontal=True, vertical_alignment="center", gap="small",
                      key="vd_subfila"):
        if not unica_vista:
            st.session_state[f"vd_vista_w_{categoria}"] = vista
            st.segmented_control(
                "Vista", orden, format_func=vistas.get, key=f"vd_vista_w_{categoria}",
                on_change=_sync_vista, args=(categoria,), label_visibility="collapsed",
                required=True,
            )
        if con_etf:
            with st.container(key="vd_etfs"):
                st.session_state[f"vd_etf_w_{categoria}"] = etf
                st.segmented_control(
                    "ETF", habilitados[categoria], key=f"vd_etf_w_{categoria}",
                    on_change=_sync_etf, args=(categoria,), label_visibility="collapsed",
                )
        clase, texto = _origen(categoria, vista)
        st.markdown(f'<span class="vd-origen vd-origen-{clase}">{texto}</span>',
                    unsafe_allow_html=True, width="content")

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
        /* Hueco en blanco tras cambiar de vista (medido 2026-09-28): el auto-alto de los
           componentes (`tools/_auto_alto.py`) fija `flex-basis` INLINE en el contenedor de su
           iframe. React reutiliza ese nodo para el elemento que ocupe la misma posición en la
           vista siguiente y le cambia la clase, pero no toca un estilo que no puso él: un
           párrafo de 51 px heredaba 170 px del iframe anterior. Streamlit fija el alto por
           clase, nunca inline, así que un inline sin iframe dentro solo puede ser ese resto. */
        [data-testid="stElementContainer"][style*="flex-basis"]:not(:has(iframe)) {
          flex-basis: auto !important;
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
           40px son la geometría del artifact: con ellos cada paso mide 98.8px. Desde el
           30-oct (D5) cada paso lleva el mismo nombre que su columna de la cascada, a
           11px y en hasta dos líneas: «Impacto del mercado» no cabe en una. `min-height`
           reserva las dos líneas en todos, así ningún paso es más alto que otro. El estado
           llega por la clave del contenedor de cada paso (`…_done` / `…_now` / `…_todo`),
           porque `st.button` solo distingue dos tipos y aquí hacen falta tres. */
        .st-key-vd_paso_wrap [data-testid="stHorizontalBlock"] { gap: 10px; }
        .st-key-vd_paso_wrap .stButton > button {
          background: transparent !important;
          border: none !important;
          border-top: 4px solid var(--hair) !important;
          border-radius: 0 !important;
          box-shadow: none !important;
          min-height: 38px !important;
          padding: 7px 0 0 0 !important;
          font-family: var(--font-sans) !important;
          font-size: 11px !important;
          letter-spacing: 0 !important;
          line-height: 1.25 !important;
          color: var(--ink-mut) !important;
          white-space: normal !important;
          text-wrap: balance;
          align-items: flex-start !important;
          justify-content: center !important;
        }
        .st-key-vd_paso_wrap .stButton > button p {
          font-size: 11px !important; line-height: 1.25 !important; white-space: normal !important;
        }
        .st-key-vd_paso_wrap [class*="_done"] .stButton > button {
          border-top-color: var(--accent) !important; color: var(--ink-2) !important;
        }
        /* El paso activo va en tinta, no en el rojo de pérdida (D4): el rojo queda solo para
           pérdidas, y el último paso salía rojo también con ganancia. */
        .st-key-vd_paso_wrap [class*="_now"] .stButton > button {
          border-top-color: var(--ink) !important; color: var(--ink) !important;
          font-weight: 700 !important;
        }
        .st-key-vd_paso_wrap .stButton > button:hover { color: var(--accent) !important; }
        .st-key-vd_paso_wrap [class*="_now"] .stButton > button:hover {
          color: var(--ink) !important;
        }
        /* Leyenda del rail móvil (`render_rail` en `ui/componentes/__init__.py`).
           Oculta en desktop: ahí cada paso ya trae su propia etiqueta. */
        .vd-rail-legend { display: none; }

        /* Un solo tamaño de marca en toda la app (carga y resultados). Selector con el
           contenedor para ganarle al `h2`/`p` de Streamlit, que pisaban el tamaño propio. */
        .vd-brand, .vd-wordmark {
          font-family: var(--font-mono); text-transform: uppercase; color: var(--ink);
        }
        .st-key-vd_marca .vd-brand,
        .st-key-vd_marca_carga .vd-wordmark {
          font-size: 16px; font-weight: 700; letter-spacing: .12em;
          line-height: 1.2; margin: 0; padding: 0; max-width: none;
        }
        /* Marca + ROC en una fila: Streamlit le pone `margin-bottom: -1rem` al markdown, y
           el centrado vertical usaba esa caja recortada — el búho quedaba 10px por encima
           del texto (medido 28-sep en la carga). */
        .st-key-vd_marca [data-testid="stMarkdownContainer"],
        .st-key-vd_marca_carga [data-testid="stMarkdownContainer"] { margin-bottom: 0; }
        .st-key-vd_marca, .st-key-vd_marca_carga { gap: 6px; }
        .st-key-vd_marca iframe, .st-key-vd_marca_carga iframe { position: relative; top: -2px; }
        /* El h2 de Streamlit trae un icono de enlace de encabezado que ocupa ~24px a la
           derecha del texto aunque esté oculto: separaba el búho más que en resultados. */
        .st-key-vd_marca_carga [data-testid="stHeaderActionElements"] { display: none; }

        /* ---- Cabecera y navegación (P1 y P8, 30-oct). Cabecera en una sola fila: marca y
           ROC a la izquierda; confiabilidad, «Cambiar datos», «Ayuda» y el tema a la
           derecha. Debajo, las secciones como pestañas siempre visibles (antes un popover que
           solo mostraba la activa) y una fila con las vistas o los fondos de la sección y la
           etiqueta de origen de las cifras (P7). */
        .st-key-vd_cabecera { row-gap: 8px; }
        .st-key-vd_chip_confiabilidad button, .st-key-vd_cambiar_datos button,
        .st-key-vd_ayuda [data-testid="stPopoverButton"], .st-key-vd_tema_btn button {
          min-height: 0 !important; padding: 6px 10px !important; border-radius: 0 !important;
          font-family: var(--font-sans) !important; font-size: 12.5px !important;
          font-weight: 600 !important; letter-spacing: 0 !important; text-transform: none !important;
          line-height: 1.2 !important;
        }
        .st-key-vd_chip_confiabilidad button {
          color: var(--warn) !important; border: none !important;
          background: color-mix(in srgb, var(--warn) 13%, transparent) !important;
        }
        .st-key-vd_chip_confiabilidad button::before {
          content: ""; width: 7px; height: 7px; background: var(--warn); margin-right: 7px;
          flex: none;
        }
        .st-key-vd_cambiar_datos button, .st-key-vd_ayuda [data-testid="stPopoverButton"],
        .st-key-vd_tema_btn button {
          color: var(--ink) !important; background: var(--panel) !important;
          border: 1px solid var(--hair) !important; box-shadow: none !important;
        }
        .st-key-vd_cambiar_datos button:hover, .st-key-vd_ayuda [data-testid="stPopoverButton"]:hover,
        .st-key-vd_tema_btn button:hover {
          border-color: var(--accent) !important; color: var(--accent) !important;
        }
        .st-key-vd_tema_btn button { padding: 6px 8px !important; color: var(--ink-2) !important; }

        /* Pestañas de sección: el `stButtonGroup` de Streamlit vestido como fila de
           pestañas — sin cajas, la activa subrayada en el azul de la marca. Una sola línea:
           si no caben, se desliza de lado (en el teléfono, siempre). */
        .st-key-vd_secciones { margin-top: 4px; }
        /* El grupo mide lo que sus botones; a todo el ancho, la línea de abajo cruza la fila. */
        .st-key-vd_secciones [data-testid="stElementContainer"],
        .st-key-vd_secciones [data-testid="stButtonGroup"] { width: 100% !important; }
        .st-key-vd_secciones [data-testid="stButtonGroup"] {
          flex-wrap: nowrap !important; overflow-x: auto; gap: 0 !important;
          border-bottom: 1px solid var(--hair); scrollbar-width: none;
        }
        .st-key-vd_secciones [data-testid="stButtonGroup"]::-webkit-scrollbar { display: none; }
        /* Los botones viven en un `div` interno del grupo con `flex-wrap: wrap` de fábrica:
           sin esto, en el teléfono las pestañas se partían en dos líneas en vez de deslizarse. */
        .st-key-vd_secciones [data-testid="stButtonGroup"] > div:has(> button) {
          flex-wrap: nowrap !important; width: max-content; min-width: 100%;
        }
        /* `button[aria-checked]` y no solo `button`: la regla general de los grupos de
           botones (más abajo) pinta de --panel la opción no elegida con la misma
           especificidad, y al ir después ganaba — las pestañas salían en un recuadro blanco. */
        .st-key-vd_secciones [data-testid="stButtonGroup"] button[aria-checked] {
          flex: 0 0 auto; white-space: nowrap; margin: 0 0 -1px 0 !important;
          font-family: var(--font-sans) !important; font-size: 13.5px !important;
          font-weight: 600 !important; letter-spacing: 0 !important; text-transform: none !important;
          background: transparent !important; border: none !important;
          border-bottom: 2px solid transparent !important; border-radius: 0 !important;
          color: var(--ink-mut) !important; padding: 10px 12px 9px !important;
          box-shadow: none !important;
        }
        .st-key-vd_secciones [data-testid="stButtonGroup"] button[aria-checked]:hover {
          color: var(--ink) !important; background: transparent !important;
        }
        .st-key-vd_secciones [data-testid="stButtonGroup"] button[aria-checked="true"] {
          color: var(--ink) !important; border-bottom-color: var(--accent) !important;
        }

        /* Fila de vistas y fondos, con la etiqueta de origen al final (P7). */
        .st-key-vd_subfila { row-gap: 6px; margin-top: 2px; }
        .st-key-vd_subfila > div:has(.vd-origen) { margin-left: auto; }
        .st-key-vd_etfs [data-testid="stButtonGroup"] { flex-wrap: wrap; row-gap: 4px; }
        .vd-origen {
          display: inline-flex; align-items: center; gap: 7px; white-space: nowrap;
          font-family: var(--font-mono); font-size: 11px; font-weight: 600;
          letter-spacing: .08em; text-transform: uppercase; color: var(--accent);
        }
        .vd-origen::before { content: ""; width: 7px; height: 7px; background: currentColor; }
        .vd-origen-ejemplo { color: var(--ink-mut); }
        .vd-origen-ejemplo::before {
          background: none; border: 1.5px solid currentColor; box-sizing: border-box;
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

        /* La etiqueta «Ayuda» se oculta en el teléfono (queda el icono): ver @media. */
        /* Control de tema: `stButtonGroup` trae radio redondeado (8px en los extremos) y
           tipografía `system-ui` de fábrica — igual que el popover, es CSS propio de
           Streamlit y solo se ve midiendo el DOM, no con `grep` sobre este archivo. */
        /* Alto reservado para el globo de ROC en la carga («Suéltalo.», «N tickers
           leídos»): sin él, al aparecer el globo el título baja ~10px. */
        [data-testid="stButtonGroup"] button {
          border-radius: 0 !important;
          font-family: var(--font-mono) !important; font-size: 11px !important;
          letter-spacing: .06em; text-transform: uppercase;
        }
        /* La opción NO seleccionada (`kind=segmented_control`, sin el sufijo `Active`)
           trae de fábrica el fondo cálido/casi blanco de `app_old.py` con texto casi blanco
           encima — ilegible en modo oscuro. La seleccionada (`…Active`) ya usa el azul de
           marca de `.streamlit/config.toml` y no se toca. Desde Streamlit 1.66 los botones
           ya no llevan `data-testid`/`kind`: el estado va en `aria-checked`. */
        [data-testid="stButtonGroup"] [data-testid="stBaseButton-segmented_control"],
        [data-testid="stButtonGroup"] button[aria-checked="false"] {
          background: var(--panel) !important; color: var(--ink) !important;
          border-color: var(--hair) !important;
        }
        [data-testid="stButtonGroup"] [data-testid="stBaseButton-segmented_control"]:hover,
        [data-testid="stButtonGroup"] button[aria-checked="false"]:hover {
          background: var(--accent-tint) !important; color: var(--accent) !important;
        }

        /* Etiquetas de widget y su icono de ayuda: Streamlit los pinta #1a1a1a fijo,
           invisibles sobre el fondo del tema oscuro. */
        [data-testid="stWidgetLabel"] p { color: var(--ink-2); }
        [data-testid="stTooltipIcon"] svg { stroke: var(--ink-mut) !important; }

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
        [data-baseweb="input"] > div,
        [data-testid="stNumberInputContainer"] {
          background: var(--panel) !important;
          border: 1px solid var(--hair) !important;
          color: var(--ink) !important;
        }
        /* El campo numérico de Streamlit 1.66 ya no lleva `data-baseweb`: salía claro y
           redondeado también en el tema oscuro. El foco se marca aquí porque el borde de
           arriba pisa el de Streamlit. */
        [data-testid="stNumberInputField"] { color: var(--ink) !important; }
        [data-testid="stNumberInputContainer"]:focus-within { border-color: var(--accent) !important; }
        [data-baseweb="popover"] li { background: var(--panel) !important; color: var(--ink) !important; }
        [data-baseweb="popover"] li:hover { background: var(--panel-tint) !important; }

        /* Sin border-radius en ningún componente: regla de marca IYG. */
        [data-baseweb="select"] > div, [data-baseweb="input"] > div,
        [data-testid="stNumberInputContainer"],
        [data-baseweb="popover"] div, .stButton > button { border-radius: 0 !important; }

        @media (max-width: 640px) {
          .block-container { padding-top: 1.25rem; }
          [data-testid="stHorizontalBlock"]:has([data-testid="stButtonGroup"]) {
            flex-wrap: wrap;
          }
          /* Cabecera (P8): en el teléfono, marca, «Ayuda» y tema en la primera línea; la
             confiabilidad y «Cambiar datos» bajan a una segunda línea entera. */
          .st-key-vd_cabecera { flex-wrap: wrap !important; }
          .st-key-vd_cabecera > div:has(.st-key-vd_estado) { order: 5; flex-basis: 100%; }
          .st-key-vd_ayuda [data-testid="stPopoverButton"] p { display: none; }
          .st-key-vd_etfs [data-testid="stButtonGroup"] { overflow-x: auto; scrollbar-width: none; }
          .st-key-vd_etfs [data-testid="stButtonGroup"] > div:has(> button) {
            flex-wrap: nowrap !important; width: max-content;
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
            min-height: 0 !important;    /* sin etiqueta no hay dos líneas que reservar */
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
