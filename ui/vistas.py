"""Despacho de vistas: qué se dibuja para cada punto de la ruta.

Las vistas ya portadas se renderizan; el resto muestra una superficie honesta hasta que
llegue su fase. Aquí no hay cálculo: se pide a `logic.py` y se pasa por `ui.adapters`.
"""

from __future__ import annotations

import streamlit as st

import logic
from ui import nav
from ui.adapters import DatosIncompletos, cashflow_data, verificar_identidades
from ui.chrome import Ruta, render_placeholder
from ui.componentes import render_cashflow, render_rail


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


def render_cash_flow(ruta: Ruta) -> None:
    """El recorrido del dinero para el ETF seleccionado."""
    resultados = _resultados()
    stats = resultados.get(ruta.etf)

    if not stats or stats.get("skipped"):
        st.markdown('<span class="vd-badge">Sin datos</span>', unsafe_allow_html=True)
        st.markdown(f'<h2 class="vd-title">{ruta.etf} no está en tu archivo</h2>',
                    unsafe_allow_html=True)
        st.markdown(
            '<p class="vd-lede">Elige otro ETF en la barra lateral, o vuelve a la carga '
            'si falta un archivo.</p>', unsafe_allow_html=True)
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


def render_vista(ruta: Ruta) -> None:
    """Punto único de entrada: decide qué vista toca según la ruta.

    Metodología (fuera de alcance en esta entrega) se activa desde el botón «¿Cómo
    funciona? →» de la ruta y se sale de ella con cualquier otra selección — mismo
    criterio que `showCat()` en el demo (línea 2643).
    """
    if st.session_state.get("vd_metodologia"):
        render_placeholder(titulo="Metodología")
        return
    if ruta.categoria in nav.CATS and ruta.vista == nav.VISTA_CON_ETF and ruta.etf:
        render_cash_flow(ruta)
        return
    render_placeholder(ruta)
