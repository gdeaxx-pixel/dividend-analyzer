"""Chrome compartido: navegación y jerarquía del port de Viaje del dinero.

La Fase 1 solo define el cascarón de interfaz. No carga datos ni contiene cálculos.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


NAVIGATION: dict[str, tuple[str, ...]] = {
    "Dividendos": ("Cash flow", "Salud NAV", "Hoja Excel"),
    "Largo Plazo": ("Proyección",),
    "Comparación": ("Real", "Simulación"),
    "Método tradicional": (
        "La hoja",
        "Reinversión",
        "Escalera de honestidad",
        "Yield anunciado",
        "Total return",
    ),
    "Metodología": ("Cómo funciona",),
}


@dataclass(frozen=True)
class NavigationState:
    """Selección de navegación de Fase 1, sin estado financiero asociado."""

    category: str
    view: str
    etf: str | None
    theme: str


def _reset_view_if_needed(category: str) -> None:
    """Mantiene la vista seleccionada dentro de la categoría activa."""
    available_views = NAVIGATION[category]
    if st.session_state.get("vd_view") not in available_views:
        st.session_state.vd_view = available_views[0]


def render_navigation() -> NavigationState:
    """Renderiza navegación nativa Categoría › Vista › ETF y tema persistente."""
    if "vd_theme" not in st.session_state:
        st.session_state.vd_theme = "Claro"
    if "vd_category" not in st.session_state:
        st.session_state.vd_category = "Dividendos"
    _reset_view_if_needed(st.session_state.vd_category)

    with st.sidebar:
        st.markdown('<p class="vd-brand">Invierte &amp; Gana</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="vd-brand-subtitle">Viaje del dinero<br>Lectura forense de dividendos</p>',
            unsafe_allow_html=True,
        )
        st.markdown('<p class="vd-nav-label">Categoría</p>', unsafe_allow_html=True)
        category = st.selectbox(
            "Categoría",
            tuple(NAVIGATION),
            key="vd_category",
            label_visibility="collapsed",
        )
        _reset_view_if_needed(category)
        st.markdown('<p class="vd-nav-label">Vista</p>', unsafe_allow_html=True)
        view = st.radio(
            "Vista",
            NAVIGATION[category],
            key="vd_view",
            label_visibility="collapsed",
        )

        etf: str | None = None
        if view == "Cash flow":
            st.markdown('<p class="vd-nav-label">ETF</p>', unsafe_allow_html=True)
            etf = st.selectbox(
                "ETF",
                ("MSTY",),
                key="vd_etf",
                label_visibility="collapsed",
            )

        st.divider()
        st.markdown('<p class="vd-nav-label">Tema</p>', unsafe_allow_html=True)
        theme = st.radio(
            "Tema",
            ("Claro", "Oscuro"),
            key="vd_theme",
            label_visibility="collapsed",
            horizontal=True,
        )

    return NavigationState(category=category, view=view, etf=etf, theme=theme)


def render_header(selection: NavigationState) -> None:
    """Muestra breadcrumb y jerarquía visual de la vista seleccionada."""
    trail = [selection.category, selection.view]
    if selection.etf:
        trail.append(selection.etf)
    breadcrumb = "<span class=\"vd-home\">Viaje del dinero</span>" + "".join(
        f'<span class="vd-crumb-separator">›</span><span>{item}</span>' for item in trail
    )
    st.markdown(f'<nav class="vd-breadcrumb" aria-label="Ruta">{breadcrumb}</nav>', unsafe_allow_html=True)
    st.markdown(f'<p class="vd-eyebrow">{selection.category}</p>', unsafe_allow_html=True)
    st.markdown(f'<h1 class="vd-title">{selection.view}</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="vd-lede">Navegación y sistema visual listos para el port de Streamlit.</p>',
        unsafe_allow_html=True,
    )


def render_stage(selection: NavigationState) -> None:
    """Renderiza un esqueleto explícito de Fase 1, sin datos ni lógica de negocio."""
    context = f" · {selection.etf}" if selection.etf else ""
    st.markdown("<hr class=\"vd-divider\">", unsafe_allow_html=True)
    st.markdown(
        f'<section class="vd-stage"><p class="vd-stage-kicker">Fase 1{context}</p>'
        f'<h2>{selection.category} › {selection.view}</h2>'
        '<p>Esta superficie conserva la ruta, el tema y la jerarquía de la interfaz. '
        'Los datos, cálculos y visualizaciones se incorporarán en fases posteriores.</p></section>',
        unsafe_allow_html=True,
    )
