"""Chrome compartido: encabezado y navegación del port de Viaje del dinero."""

from __future__ import annotations

import streamlit as st

NAV_ITEMS = (
    "Inicio",
    "Flujo de dinero",
    "Salud NAV",
    "Comparación",
    "Método tradicional",
    "Metodología",
)


def render_navigation() -> str:
    """Renderiza la navegación inicial y devuelve la vista seleccionada."""
    st.sidebar.markdown('<p class="vd-brand">Invierte &amp; Gana</p>', unsafe_allow_html=True)
    st.sidebar.markdown(
        '<p class="vd-brand-subtitle">Viaje del dinero<br>Lectura forense de dividendos</p>',
        unsafe_allow_html=True,
    )
    if "vd_page" not in st.session_state:
        st.session_state.vd_page = NAV_ITEMS[0]
    return st.sidebar.radio(
        "Navegación principal",
        NAV_ITEMS,
        key="vd_page",
        label_visibility="collapsed",
    )


def render_header(page: str) -> None:
    """Muestra el encabezado consistente de la vista seleccionada."""
    if page == "Inicio":
        eyebrow = "Port de Streamlit · Fase 1"
        title = "El viaje de tu dinero"
        lede = (
            "Una nueva lectura visual para seguir el capital aportado, los dividendos, "
            "la retención y el valor actual sin alterar los cálculos fiscales existentes."
        )
    else:
        eyebrow = "Viaje del dinero"
        title = page
        lede = "Esta sección queda preparada en la navegación para las fases posteriores del port."

    st.markdown(f'<p class="vd-eyebrow">{eyebrow}</p>', unsafe_allow_html=True)
    st.markdown(f'<h1 class="vd-title">{title}</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="vd-lede">{lede}</p>', unsafe_allow_html=True)


def render_stage(page: str) -> None:
    """Mantiene una superficie honesta mientras las vistas aún no se portan."""
    if page == "Inicio":
        heading = "Comienza con el recorrido"
        detail = (
            "Usa la navegación lateral para conocer las áreas que compondrán el artifact. "
            "La carga de datos y las visualizaciones se incorporarán en fases posteriores."
        )
    else:
        heading = f"{page}: estructura inicial"
        detail = (
            "La navegación y el sistema visual ya están activos. "
            "El contenido funcional de esta vista no forma parte de la Fase 1."
        )

    st.markdown("<hr class=\"vd-divider\">", unsafe_allow_html=True)
    st.markdown(
        f'<section class="vd-stage"><h2>{heading}</h2><p>{detail}</p></section>',
        unsafe_allow_html=True,
    )
