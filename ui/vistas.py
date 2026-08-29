"""Despacho de vistas: qué se dibuja para cada punto de la ruta.

Las vistas ya portadas se renderizan; el resto muestra una superficie honesta hasta que
llegue su fase. Aquí no hay cálculo: se pide a `logic.py` y se pasa por `ui.adapters`.
"""

from __future__ import annotations

import streamlit as st

import logic
from ui import estado, heredadas, impuestos, nav
from ui.adapters import (DatosIncompletos, cashflow_data, comparacion_data, hoja_data,
                         metodo_data, metodo_real_data, metodo_serie_data, salud_nav_data,
                         trg_real_data, verificar_identidades)
from ui.chrome import Ruta, render_placeholder
from ui.componentes import (render_cashflow, render_comparacion, render_comparacion_real,
                            render_hoja, render_metodo, render_metodo_real,
                            render_metodologia, render_rail)
from ui.validacion import render_validacion_datos


def obtener_resultados() -> dict:
    """Acceso público al cache de `_resultados()`, para el pie (`ui/pie.py`) — que no
    puede importar este módulo por el ciclo que crearía con `ui.componentes`."""
    return _resultados()


def _resultados() -> dict:
    """`analyze_portfolio` cacheado en la sesión.

    Baja precios de mercado, así que recalcularlo en cada rerun —y el rail provoca uno
    por paso— haría la vista inusable. Se invalida al editar la carga, porque esos
    handlers borran `_wizard_df_clean`.
    """
    if st.session_state.get("_vd_resultados") is None:
        df = st.session_state.get("_wizard_df_clean")
        if df is None:
            return {}
        with st.spinner("Leyendo tu portafolio y consultando el mercado…"):
            st.session_state["_vd_resultados"] = logic.analyze_portfolio(df)
    return st.session_state["_vd_resultados"] or {}


def _stats_o_aviso(ruta: Ruta) -> dict | None:
    """Stats del ETF de contexto, o `None` tras dibujar el aviso «sin datos».

    Compartido por Cash flow, Salud NAV y Hoja Excel: las tres secciones dependen del
    mismo ETF de la ruta (`ui/chrome.py` lo resuelve aunque el breadcrumb solo lo
    muestre en Cash flow — mapa-datos.md § 3).
    """
    stats = _resultados().get(ruta.etf)
    if not stats or stats.get("skipped"):
        st.markdown('<span class="vd-badge">Sin datos</span>', unsafe_allow_html=True)
        st.markdown(f'<h2 class="vd-title">{ruta.etf} no está en tu archivo</h2>',
                    unsafe_allow_html=True)
        st.markdown(
            '<p class="vd-lede">Elige otro ETF en la ruta de arriba, o vuelve a la carga '
            'si falta un archivo.</p>', unsafe_allow_html=True)
        return None
    return stats


def _tax_summary(ticker: str) -> dict | None:
    """Objeto fiscal del ticker re-derivado por la residencia declarada (capa 2, Regla 3).

    `analyze_portfolio` cachea la capa 1 SIN DECLARAR porque está bajo `@st.cache_data` y no
    puede ver `session_state`. Aquí sí: se re-deriva una vez por render con el perfil vigente
    y se le entrega a la vista, que solo lo RENDERIZA. Sin país declarado devuelve el mismo
    objeto sin devolución estimada — no una versión con 30% asumido.
    """
    resultados = _resultados()
    if not resultados:
        return None
    tasa, pais = estado.tasa_y_pais()
    return logic.build_tax_summaries(resultados, base_rate_pct=tasa, country=pais).get(ticker)


def render_aviso_retencion(stats: dict, ticker: str) -> None:
    """Contrasta la tasa que le APLICARON contra la que le corresponde por su país.

    El país da el derecho; los números dicen qué pasó. Que no coincidan es la señal de que
    el W-8BEN no está presentado o venció — y eso es dinero que no vuelve solo, a diferencia
    de la sobre-retención por ROC. Por eso los dos buckets se muestran SEPARADOS: tienen
    causas, tiempos y acciones distintas, y sumarlos sería repetir el bug de las dos verdades
    del mismo dólar.
    """
    tasa, pais = estado.tasa_y_pais()
    diag = logic.build_withholding_diagnosis(
        stats, ticker, entitled_pct=None if tasa == logic.RATE_UNDECLARED else tasa,
        country=pais)

    if diag["verdict"] == "tratado_no_aplicado":
        st.warning(f"**Revisa tu W-8BEN.** {diag['label']}")
        if diag["gap_w8ben"] > 0.01 or diag["refund_roc"] > 0.01:
            c1, c2 = st.columns(2)
            c1.metric("Vuelve solo (ROC)", f"${diag['refund_roc']:,.2f}",
                      help="Se reclasifica en el cierre anual del bróker: IB devuelve entre "
                           "enero y marzo, Schwab entre junio y septiembre.")
            c2.metric("No vuelve solo (W-8BEN)", f"${diag['gap_w8ben']:,.2f}",
                      help="Retención por encima de tu tratado. Hay que presentar el "
                           "W-8BEN y reclamar lo cobrado de más con el 1040-NR.")
    elif diag["verdict"] == "menor_de_lo_esperado":
        st.info(diag["label"])


def render_cash_flow(ruta: Ruta) -> None:
    """El recorrido del dinero para el ETF seleccionado."""
    stats = _stats_o_aviso(ruta)
    if stats is None:
        return

    render_aviso_retencion(stats, ruta.etf)

    try:
        datos = cashflow_data(stats, ruta.etf, tax_summary=_tax_summary(ruta.etf))
    except DatosIncompletos as error:
        st.warning(str(error))
        return

    # Las identidades del waterfall se comprueban ANTES de dibujar: si no cuadran, las
    # barras mienten aunque cada cifra suelta sea correcta. Se avisa en vez de callar.
    # Se pasa `stats` para que el guard reconcilie contra una relectura independiente del
    # CSV, no solo contra las identidades definitorias de `cashflow_data`.
    fallos = verificar_identidades(datos, stats)
    if fallos:
        st.error("Las cifras de este recorrido no cuadran entre sí — no se dibuja para no "
                 "mostrar un gráfico que miente.")
        with st.expander("Detalle"):
            for fallo in fallos:
                st.write(f"· {fallo}")
        return

    paso = render_rail(datos["STEP_LABELS"], activo=len(datos["STEP_LABELS"]) - 1)
    render_cashflow(datos, paso, ruta.tema)


def render_hoja_excel(ruta: Ruta) -> None:
    """La hoja de cálculo de toda la vida, con y sin el error de doble conteo."""
    stats = _stats_o_aviso(ruta)
    if stats is None:
        return

    df = st.session_state.get("_wizard_df_clean")
    try:
        datos = hoja_data(stats, ruta.etf, df, tax_summary=_tax_summary(ruta.etf))
    except DatosIncompletos as error:
        st.warning(str(error))
        return

    fallos = verificar_identidades(datos, stats)
    if fallos:
        st.error("Las cifras de esta hoja no cuadran entre sí — no se dibuja para no "
                 "mostrar una tabla que miente.")
        with st.expander("Detalle"):
            for fallo in fallos:
                st.write(f"· {fallo}")
        return

    render_hoja(datos, ruta.tema)


def render_salud_nav(ruta: Ruta) -> None:
    """Veredicto de salud del NAV: destrucción de capital o solo caída del subyacente.

    Sin diseño del artifact que portar (`panel-salud` es un placeholder — mapa-datos.md
    § 3): se dibuja con widgets nativos y el mismo lenguaje visual (`vd-badge`/`vd-title`/
    `vd-lede`) que el resto de la ruta.
    """
    stats = _stats_o_aviso(ruta)
    if stats is None:
        return

    datos = salud_nav_data(ruta.etf, stats)

    st.markdown('<span class="vd-badge">Salud del NAV</span>', unsafe_allow_html=True)
    st.markdown(
        f'<h2 class="vd-title" style="color:{datos["color"]}">{datos["headline"]}</h2>',
        unsafe_allow_html=True)
    st.markdown(f'<p class="vd-lede">{datos["plain"]}</p>', unsafe_allow_html=True)

    nums = []
    if datos["nav_cagr"] is not None:
        nums.append(f"NAV {datos['nav_cagr']:+.0f}%/año")
    if datos["roc_pct"] is not None:
        nums.append(f"ROC {datos['roc_pct']:.0f}%")
    if datos["total_return_pct"] is not None:
        nums.append(f"retorno total {datos['total_return_pct']:+.0f}%")
    with st.expander("Ver detalle técnico"):
        if nums:
            st.caption(" · ".join(nums))
        st.write(datos["reason"])

    info = logic.load_instruments().get(str(ruta.etf).upper(), {}) or {}
    why = []
    if info.get("nav_erosion"):
        why.append(f"**Erosión del NAV:** {info['nav_erosion']}")
    if info.get("sustainability"):
        why.append(f"**Sostenibilidad de la distribución:** {info['sustainability']}")
    if why:
        with st.expander(f"¿Por qué pasa esto en {ruta.etf}?"):
            for parrafo in why:
                st.markdown(parrafo)


def render_comparacion_simulacion(ruta: Ruta) -> None:
    """«Comparación · Simulación» (Total Return Graph, Fase 3.3a). No depende del
    portafolio del usuario — vive fuera del wizard —, así que a diferencia de
    `render_trg_real` no hay `_resultados()` que esperar. `comparacion_data` sí baja
    historia (del caché de precio, casi nunca de red — ver `ui.adapters.comparacion_data`),
    así que se cachea en la sesión con el mismo criterio que `_resultados()`: recalcularlo
    en cada rerun del rail sería lento sin motivo, sobre datos que no cambian por sesión.
    """
    if st.session_state.get("_vd_comparacion_data") is None:
        st.session_state["_vd_comparacion_data"] = comparacion_data()
    datos = st.session_state["_vd_comparacion_data"]
    if datos is None:
        st.warning("No se pudo cargar la historia de precios (ni caché ni yfinance en "
                  "vivo) — inténtalo de nuevo en unos minutos.")
        return
    render_comparacion(datos, ruta.tema)


def render_metodo_tradicional(ruta: Ruta) -> None:
    """«Método tradicional» (las 5 sub-vistas de `nav.MET_ORDER`). Como
    `render_comparacion_simulacion`, no depende del portafolio del usuario — es el caso
    de estudio fijo de la clase de Greco — así que `metodo_data()` (que sí baja historia,
    del caché casi siempre) se cachea en la sesión con el mismo criterio que
    `_vd_comparacion_data`.
    """
    if st.session_state.get("_vd_metodo_data") is None:
        st.session_state["_vd_metodo_data"] = metodo_data()
    datos = st.session_state["_vd_metodo_data"]
    if datos is None:
        st.warning("No se pudo cargar la historia de precios del caso de estudio (ni "
                  "caché ni yfinance en vivo) — inténtalo de nuevo en unos minutos.")
        return
    # La serie mensual de los 6 escenarios (3ª matriz) se cachea aparte y con la misma
    # regla: mismo caso de estudio fijo, así que una vez por sesión basta. Clave propia y
    # no dentro de `_vd_metodo_data` porque son dos metodologías distintas (ver
    # `ui.adapters.metodo_serie_data`) y conviene que se vea que no comparten objeto.
    if st.session_state.get("_vd_metodo_serie") is None:
        st.session_state["_vd_metodo_serie"] = metodo_serie_data()
    render_metodo(ruta.vista, ruta.tema, datos, st.session_state["_vd_metodo_serie"])


def render_matriz2(ruta: Ruta) -> None:
    """«Matriz 2» — las cuatro lecciones de «La matriz» sobre el portafolio real del
    CSV cargado (traspaso 2026-08-17). Nombrada distinto a `ui.componentes.
    render_metodo_real` a propósito, mismo motivo que `render_trg_real`/
    `render_comparacion_real`: dos módulos no pueden compartir nombre de función sin
    que el import de uno choque con la definición del otro.

    Sin CSV cargado, la vista no se dibuja (Decisión 5 del traspaso) — mismo patrón que
    `render_trg_real`.
    """
    resultados = _resultados()
    if not resultados:
        st.info("Carga tu CSV para ver esta sección con datos reales.")
        return

    df = st.session_state.get("_wizard_df_clean")
    tasa_pct, pais = estado.tasa_y_pais()
    datos = metodo_real_data(resultados, df, tasa_pct, pais)
    if datos is None:
        st.warning("Ninguna posición de tu portafolio tiene datos suficientes para "
                  "esta matriz todavía.")
        return

    render_metodo_real(datos, ruta.tema)


def render_trg_real(ruta: Ruta) -> None:
    """Total Return Graph con datos reales — el mismo componente del artifact que
    Comparación · Simulación (`ui/componentes/comparacion_real.html`, derivado de
    `comparacion.html` por `tools/extract_comparacion_real.py`), alimentado con el
    índice real que calcula `ui.adapters.trg_real_data` sobre `price_cache` +
    `backtest.run_backtest` (mapa-datos.md § 5; hasta el 2026-08-21 era
    `logic.build_drip_comparison_series`, retirada). Sin badge/título/lede propios: el panel del componente ya trae los suyos
    (mismo patrón que Comparación · Simulación) — duplicarlos aquí dejaría dos
    encabezados.

    El componente no calcula nada: `ui.adapters.trg_real_data` entrega el índice
    crudo de los 8 tickers × 3 modos fiscales sobre la ventana completa, y `series()`
    (JS) renormaliza al fondo base que el usuario elija dentro del iframe, sin rerun
    de Streamlit — decisión 3 del traspaso 2026-08-10.
    """
    resultados = _resultados()
    if not resultados:
        st.info("Carga tu CSV para ver esta gráfica con datos reales.")
        return

    # Antes: `st.session_state.get("proj_country")` — una clave que ningún widget vivo
    # escribía (el selector usaba `vd_her_proj_country`), así que `pais` siempre salía None
    # y esta vista corría a 30% para todo el mundo. El perfil ahora tiene un dueño único.
    perfil = estado.perfil_fiscal()
    pais = perfil["country"]
    tasa_pct = perfil["rate_pct"] if perfil["rate_declared"] else logic.NRA_DEFAULT_RATE

    datos = trg_real_data(resultados, tasa_pct, pais)
    if datos is None:
        st.warning("No se pudo descargar la serie de precios del fondo base — "
                  "inténtalo de nuevo en unos minutos.")
        return

    render_comparacion_real(datos, ruta.tema)


def render_vista(ruta: Ruta) -> None:
    """Punto único de entrada: decide qué vista toca según la ruta.

    Metodología y Validación datos se activan desde el menú de 3
    puntos de la ruta (`vd_panel` en `st.session_state`, valores
    `"metodologia"`/`"validacion"`/`None`). «Otras calculadoras» vive ahora como §12 de
    Metodología (2026-08-24) — su panel propio y su botón en el menú se retiraron. Se sale
    de cualquiera de los dos paneles con el botón nativo «← Volver al análisis» o con
    cualquier otra selección
    de la ruta (`ui/chrome.py` limpia `vd_panel` al elegir) — solo un panel a la vez,
    mismo patrón que Metodología antes de que existiera el menú.
    """
    panel = st.session_state.get("vd_panel")
    if panel in ("metodologia", "validacion"):
        if st.button("← Volver al análisis", key="vd_panel_volver"):
            st.session_state["vd_panel"] = None
            st.rerun()
        if panel == "metodologia":
            # Mismo caché de sesión que `render_metodo_tradicional` (`_vd_metodo_data`):
            # § 9 «Anualizar bien» cita el mismo caso de estudio que «Método tradicional»,
            # así que reutiliza la corrida en vez de bajar la historia dos veces. `None`
            # (sin caché ni yfinance en vivo) degrada con gracia dentro del componente —
            # no hay banner aquí porque Metodología no depende de que esto cargue.
            if st.session_state.get("_vd_metodo_data") is None:
                st.session_state["_vd_metodo_data"] = metodo_data()
            render_metodologia(ruta.tema, anchor=st.session_state.get("vd_metodologia_anchor"),
                                datos=st.session_state["_vd_metodo_data"])
        elif panel == "validacion":
            render_validacion_datos(_resultados())
        return
    if ruta.categoria in nav.CATS and ruta.etf:
        if ruta.vista == nav.VISTA_CON_ETF:
            render_cash_flow(ruta)
            return
        if ruta.vista == "hoja":
            render_hoja_excel(ruta)
            return
        if ruta.vista == "salud":
            render_salud_nav(ruta)
            return
    if ruta.categoria == "comparacion":
        if ruta.vista == "simulacion":
            render_comparacion_simulacion(ruta)
            return
        if ruta.vista == "real":
            render_trg_real(ruta)
            return
    if ruta.categoria == "metodo" and ruta.vista == "matriz2":
        render_matriz2(ruta)
        return
    if ruta.categoria == "metodo" and ruta.vista in nav.MET_ORDER:
        render_metodo_tradicional(ruta)
        return
    if ruta.categoria == heredadas.CAT_CLAVE:
        heredadas.render_vista(ruta.vista, ruta)
        return
    if ruta.categoria == impuestos.CAT_CLAVE:
        impuestos.render_vista(ruta.vista, ruta)
        return
    render_placeholder(ruta)
