"""Despacho de vistas: qué se dibuja para cada punto de la ruta.

Las vistas ya portadas se renderizan; el resto muestra una superficie honesta hasta que
llegue su fase. Aquí no hay cálculo: se pide a `logic.py` y se pasa por `ui.adapters`.
"""

from __future__ import annotations

import streamlit as st

import logic
from ui import heredadas, nav
from ui.adapters import (DatosIncompletos, cashflow_data, hoja_data, salud_nav_data,
                         trg_real_data, verificar_identidades)
from ui.chrome import Ruta, render_placeholder
from ui.componentes import (render_cashflow, render_comparacion, render_comparacion_real,
                            render_hoja, render_metodo, render_metodologia, render_rail)
from ui.pie import render_calculadoras
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


def render_cash_flow(ruta: Ruta) -> None:
    """El recorrido del dinero para el ETF seleccionado."""
    stats = _stats_o_aviso(ruta)
    if stats is None:
        return

    try:
        datos = cashflow_data(stats, ruta.etf)
    except DatosIncompletos as error:
        st.warning(str(error))
        return

    # Las identidades del waterfall se comprueban ANTES de dibujar: si no cuadran, las
    # barras mienten aunque cada cifra suelta sea correcta. Se avisa en vez de callar.
    fallos = verificar_identidades(datos)
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
        datos = hoja_data(stats, ruta.etf, df)
    except DatosIncompletos as error:
        st.warning(str(error))
        return

    fallos = verificar_identidades(datos)
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


def render_trg_real(ruta: Ruta) -> None:
    """Total Return Graph con datos reales — el mismo componente del artifact que
    Comparación · Simulación (`ui/componentes/comparacion_real.html`, derivado de
    `comparacion.html` por `tools/extract_comparacion_real.py`), alimentado con el
    índice TRI real que calcula `logic.build_drip_comparison_series` (mapa-datos.md
    § 5). Sin badge/título/lede propios: el panel del componente ya trae los suyos
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

    pais = st.session_state.get("proj_country")
    pais = pais if pais in logic.NRA_COUNTRY_RATES else None
    tasa_pct = logic.NRA_COUNTRY_RATES[pais][0] if pais else logic.NRA_DEFAULT_RATE

    datos = trg_real_data(resultados, tasa_pct, pais)
    if datos is None:
        st.warning("No se pudo descargar la serie de precios del fondo base — "
                  "inténtalo de nuevo en unos minutos.")
        return

    render_comparacion_real(datos, ruta.tema)


def render_vista(ruta: Ruta) -> None:
    """Punto único de entrada: decide qué vista toca según la ruta.

    Metodología, Validación datos y Otras calculadoras se activan desde el menú de 3
    puntos de la ruta (`vd_panel` en `st.session_state`, valores
    `"metodologia"`/`"validacion"`/`"calculadoras"`/`None`) y se sale de cualquiera de
    las tres con el botón nativo «← Volver al análisis» o con cualquier otra selección
    de la ruta (`ui/chrome.py` limpia `vd_panel` al elegir) — solo un panel a la vez,
    mismo patrón que Metodología antes de que existiera el menú.
    """
    panel = st.session_state.get("vd_panel")
    if panel in ("metodologia", "validacion", "calculadoras"):
        if st.button("← Volver al análisis", key="vd_panel_volver"):
            st.session_state["vd_panel"] = None
            st.rerun()
        if panel == "metodologia":
            render_metodologia(ruta.tema, anchor=st.session_state.get("vd_metodologia_anchor"))
        elif panel == "validacion":
            render_validacion_datos(_resultados())
        else:
            render_calculadoras()
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
            render_comparacion(ruta.tema)
            return
        if ruta.vista == "real":
            render_trg_real(ruta)
            return
    if ruta.categoria == "metodo" and ruta.vista in nav.MET_ORDER:
        render_metodo(ruta.vista, ruta.tema)
        return
    if ruta.categoria == heredadas.CAT_CLAVE:
        heredadas.render_vista(ruta.vista, ruta)
        return
    render_placeholder(ruta)
