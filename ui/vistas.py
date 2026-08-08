"""Despacho de vistas: qué se dibuja para cada punto de la ruta.

Las vistas ya portadas se renderizan; el resto muestra una superficie honesta hasta que
llegue su fase. Aquí no hay cálculo: se pide a `logic.py` y se pasa por `ui.adapters`.
"""

from __future__ import annotations

import streamlit as st

import logic
from ui import heredadas, nav
from ui.adapters import (DatosIncompletos, cashflow_data, hoja_data, salud_nav_data,
                         verificar_identidades)
from ui.chrome import Ruta, render_placeholder
from ui.componentes import (render_cashflow, render_comparacion, render_hoja,
                            render_metodo, render_metodologia, render_rail)

# Paleta de los 8 tickers del universo de comparación — literal del demo
# (`viaje-dinero-waterfall.html:2837`), reusada aquí para que TRG Real use los mismos
# colores por ticker que TRG Simulación en vez de inventar una paleta nueva.
_TRG_YM = ("NVDY", "TSLY", "CONY", "MSTY", "CHPY")
_TRG_GROWTH = ("SCHB", "XLK", "SMH")
_TRG_COLORES = {"NVDY": "#1f86c4", "TSLY": "#d1662f", "CONY": "#b95cae", "MSTY": "#a8b020",
                "CHPY": "#17a89a", "SCHB": "#b06a3d", "XLK": "#8f76d4", "SMH": "#c99a26"}


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


_V1042S_ESTILO = {
    "match":            ("--cash", "Coincide"),
    "portfolio_higher":  ("--warn", "Tu análisis reporta más"),
    "form_higher":       ("--warn", "El 1042-S reporta más"),
    "no_overlap":        ("--ink-mut", "Sin año en común"),
}


def render_1042s_card() -> None:
    """Banner persistente bajo el encabezado: cruza el 1042-S leído en el Bloque 3
    contra el bruto de dividendos que `analyze_portfolio` calculó. Solo aparece si hay
    un 1042-S en sesión — es la tercera fuente, opcional, no gatea nada."""
    wizard_1042s = st.session_state.get("_wizard_1042s")
    if not wizard_1042s:
        return
    validacion = logic.build_1042s_validation(_resultados(), wizard_1042s)
    if not validacion:
        return
    accent_var, etiqueta = _V1042S_ESTILO.get(validacion["status"], _V1042S_ESTILO["no_overlap"])
    st.markdown(
        f'<div class="vd-1042s-card" style="border-left-color: var({accent_var});">'
        f'<p class="vd-1042s-titulo">Validación 1042-S · <span style="color: var({accent_var});">'
        f'{etiqueta}</span></p>'
        f'<p class="vd-1042s-detalle">Dividendo bruto {validacion["tax_year"]} — Tu análisis: '
        f'<b>${validacion["bruto_portafolio"]:,.2f}</b> · 1042-S: <b>${validacion["bruto_1042s"]:,.2f}</b> · '
        f'Retenido: <b>${validacion["retenido_1042s"]:,.2f}</b> · ROC: '
        f'<b>${validacion["roc_1042s"]:,.2f}</b> ({validacion["roc_pct"]:.1f}%)</p>'
        f'<p class="vd-1042s-nota">{validacion["note"]}</p>'
        '</div>', unsafe_allow_html=True)


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
    render_cashflow(datos, paso)


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

    render_hoja(datos)


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
    """Total Return Graph con datos reales — la misma comparación que la Simulación,
    pero calculada sobre precios/dividendos reales vía `logic.build_drip_comparison_series`
    (mapa-datos.md § 5). Sin diseño del artifact (`cmp-panel-real` es un placeholder «En
    diseño»): widgets nativos, mismo criterio que Salud NAV.

    Sin ETF de contexto en la ruta (Comparación no lleva breadcrumb de ETF): el fondo
    base se elige aquí, igual que en `app.py:5931-5936` (referencia probada en
    producción, misma lógica de controles y transformación de datos).
    """
    import altair as alt

    st.markdown('<span class="vd-badge">Comparación · Real</span>', unsafe_allow_html=True)
    st.markdown('<h2 class="vd-title">Total Return Graph · datos reales</h2>',
                unsafe_allow_html=True)
    st.markdown(
        '<p class="vd-lede">La misma comparación que la simulación, pero con tu '
        'reinversión y tu retención efectiva, calculada desde precios y dividendos '
        'reales.</p>', unsafe_allow_html=True)

    resultados = _resultados()
    if not resultados:
        st.info("Carga tu CSV para ver esta gráfica con datos reales.")
        return

    classify_map = logic.classify_tickers(list(resultados.keys()))
    poseidos_a = [t for t, m in classify_map.items() if m == "mode_a" and t in _TRG_YM]
    base_defecto = (max(poseidos_a, key=lambda t: (resultados.get(t) or {}).get("market_value") or 0)
                    if poseidos_a else _TRG_YM[0])

    col_base, col_modo = st.columns([1, 2])
    with col_base:
        base = st.selectbox("Fondo base (YieldMax)", _TRG_YM,
                            index=_TRG_YM.index(base_defecto), key="vd_trg_base")
    with col_modo:
        pais = st.session_state.get("proj_country")
        pais = pais if pais in logic.NRA_COUNTRY_RATES else None
        tasa_pct = logic.NRA_COUNTRY_RATES[pais][0] if pais else logic.NRA_DEFAULT_RATE
        modo_lbl = st.radio(
            "Supuesto de reinversión",
            ["DRIP bruto (0%)", "Neto estimado (ROC 19a)", f"Peor caso ({tasa_pct:.0f}% plano)"],
            horizontal=True, key="vd_trg_modo")
    modo = ("bruto" if modo_lbl.startswith("DRIP") else
           "roc" if "ROC" in modo_lbl else "plano")

    col_g, col_y = st.columns(2)
    with col_g:
        crecimiento = st.pills("Crecimiento", _TRG_GROWTH, default=list(_TRG_GROWTH),
                               selection_mode="multi", key="vd_trg_crecimiento")
    with col_y:
        otros_ym = [t for t in _TRG_YM if t != base]
        ym_extra = st.pills("Otros YieldMax", otros_ym, default=[],
                            selection_mode="multi", key=f"vd_trg_ym_{base}")
    comparar = tuple((crecimiento or []) + (ym_extra or []))

    df, meta = logic.build_drip_comparison_series(base, comparar, mode=modo, base_rate=tasa_pct / 100.0)
    if df.empty or base not in meta:
        st.warning(f"No se pudo descargar la serie de precios de {base} — inténtalo de nuevo "
                   "en unos minutos.")
        return

    df = df.copy()
    df["Pct"] = df["Valor"] - 100.0
    mostrados = [t for t in _TRG_COLORES if t in set(df["Ticker"])]
    escala = alt.Scale(domain=mostrados, range=[_TRG_COLORES[t] for t in mostrados])
    tardios = {t for t, m in meta.items() if m.get("late")}
    df["Etiqueta"] = df["Ticker"] + df["Ticker"].map(lambda t: "*" if t in tardios else "")

    lineas = alt.Chart(df).mark_line().encode(
        x=alt.X("Fecha:T", title=None),
        y=alt.Y("Pct:Q", title="Rendimiento total (%)"),
        color=alt.Color("Ticker:N", scale=escala, legend=alt.Legend(orient="bottom", title=None)),
        strokeWidth=alt.condition(alt.datum.Ticker == base, alt.value(3.2), alt.value(2)),
        tooltip=[alt.Tooltip("Fecha:T", title="Fecha", format="%d %b %Y"),
                alt.Tooltip("Ticker:N", title="Activo"),
                alt.Tooltip("Pct:Q", title="Rendimiento total", format="+.1f")],
    ).properties(height=420)
    st.altair_chart(lineas, use_container_width=True)

    if tardios:
        st.caption("* incepción posterior al fondo base — arranca en 0% en su propia fecha; "
                  "su cifra final no cubre el mismo horizonte.")


def render_vista(ruta: Ruta) -> None:
    """Punto único de entrada: decide qué vista toca según la ruta.

    Metodología se activa desde el botón «¿Cómo funciona? →» de la ruta (`vd_metodologia`
    en `st.session_state`) y se sale de ella con el botón nativo «← Volver al análisis» o
    con cualquier otra selección de la ruta (`ui/chrome.py` limpia la bandera al elegir).
    """
    if st.session_state.get("vd_metodologia"):
        if st.button("← Volver al análisis", key="vd_metodologia_volver"):
            st.session_state["vd_metodologia"] = False
            st.rerun()
        render_metodologia()
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
            render_comparacion()
            return
        if ruta.vista == "real":
            render_trg_real(ruta)
            return
    if ruta.categoria == "metodo" and ruta.vista in nav.MET_ORDER:
        render_metodo(ruta.vista)
        return
    if ruta.categoria == heredadas.CAT_CLAVE:
        heredadas.render_vista(ruta.vista, ruta)
        return
    render_placeholder(ruta)
