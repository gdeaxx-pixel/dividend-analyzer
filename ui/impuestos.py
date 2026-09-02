"""Categoría «Impuestos» — la escalera de lo que te repartieron, lo que era renta,
lo que te toca y lo que te retuvieron.

**Este módulo NO se genera y NO calcula fiscalidad.** Igual que `ui/heredadas.py`, la
categoría no existe en el demo del artifact (el demo solo tiene 4 categorías), así que
inventarla en `ui/nav.py` rompería el `--check` de `tools/extract_design_system.py`. Se
compone a mano en `ui/chrome.py` en tiempo de import, exactamente como «Portafolios».

La vista es de CARTERA, no de ETF: todo el mensaje es de concentración —la retención de
Daniel en 2025 salió casi entera de un solo fondo— y eso solo se ve sumando la cartera.
El desglose por fondo va como tabla dentro del componente.

Toda cifra en dólares sale de un objeto fiscal que ya existe (`build_tax_summaries`,
`build_withholding_diagnosis`, `diagnose_broker_refund_from_forms`); aquí solo se
RENDERIZA (Regla 3 de `specs/roc-nra-invariants.md`). El armado del JSON vive en
`ui/adapters.py::impuestos_data`. La residencia fiscal se lee por `ui/estado.py`, nunca
directo de `st.session_state` (Regla del `test_perfil_fiscal.py`).
"""

from __future__ import annotations

import streamlit as st

from ui import estado

CAT_CLAVE = "impuestos"
CAT_LABEL = "Impuestos"

VIEWS = {
    "escalera": "La escalera",
}

VIEW_ORDER = ("escalera",)


def render_vista(vista: str, ruta) -> None:
    """Despacho de Impuestos — una sola vista (la escalera)."""
    from ui import adapters, componentes
    from ui.vistas import obtener_resultados

    resultados = obtener_resultados()
    if not resultados:
        st.markdown('<span class="vd-badge">Impuestos</span>', unsafe_allow_html=True)
        st.markdown('<h2 class="vd-title">La escalera de tus impuestos</h2>',
                    unsafe_allow_html=True)
        st.markdown(
            '<p class="vd-lede">Carga tu CSV de transacciones para ver cuánto te repartió '
            'el fondo, cuánto era renta de verdad, cuánto te corresponde pagar y cuánto te '
            'retuvieron.</p>', unsafe_allow_html=True)
        return

    perfil = estado.perfil_fiscal()
    _w1042s = st.session_state.get("_wizard_1042s") or {}
    forms_1042s = _w1042s.get("forms") or []
    # Casilla 13b: solo para que los CTA ofrezcan la segunda vía de declarar el país. No
    # declara residencia — eso sigue pidiendo el clic del cliente en el Paso 2.
    codigo_pais_1042s = _w1042s.get("recipient_country_code")

    datos = adapters.impuestos_data(resultados, perfil, forms_1042s, codigo_pais_1042s)
    if datos is None or not datos.get("fondos"):
        st.markdown('<span class="vd-badge">Impuestos</span>', unsafe_allow_html=True)
        st.markdown('<h2 class="vd-title">Sin dividendos que declarar</h2>',
                    unsafe_allow_html=True)
        st.markdown(
            '<p class="vd-lede">Ninguna posición de tu portafolio repartió dividendos ni '
            'tuvo retención de impuestos en la ventana analizada.</p>',
            unsafe_allow_html=True)
        return

    componentes.render_impuestos(datos, ruta.tema)
