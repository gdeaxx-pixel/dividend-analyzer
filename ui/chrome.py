"""Chrome del port: ruta Categoría › Vista › ETF y superficie visual del artifact.

Toda la taxonomía y todos los colores vienen de `ui/nav.py` y `ui/tokens.py`, que se
GENERAN del demo (`tools/extract_design_system.py`). Aquí no se escribe a mano ni un
nombre de vista ni un color: si algo no coincide con el artifact, se corrige en el demo
y se regenera.

Solo presentación — sin datos ni cálculos.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from ui import nav
from ui.tokens import css_variables


@dataclass(frozen=True)
class Ruta:
    """Posición actual en la jerarquía del artifact."""

    categoria: str          # clave: dividendos · largo · comparacion · metodo
    vista: str              # clave dentro de la categoría
    etf: str | None         # solo en Cash flow
    tema: str               # "Claro" | "Oscuro"

    @property
    def categoria_label(self) -> str:
        return nav.CAT_LABELS[self.categoria]

    @property
    def vista_label(self) -> str:
        return _vistas(self.categoria)[self.vista]


def _vistas(categoria: str) -> dict:
    """Vistas de una categoría. Comparación y Método tienen las suyas; las categorías
    con ETF comparten las tres secciones (Cash flow · Salud NAV · Hoja Excel)."""
    if categoria == "comparacion":
        return dict(nav.CMP_VIEWS)
    if categoria == "metodo":
        return dict(nav.MET_VIEWS)
    return dict(nav.SECTIONS)


def _orden(categoria: str) -> tuple:
    if categoria == "comparacion":
        return nav.CMP_ORDER
    if categoria == "metodo":
        return nav.MET_ORDER
    return tuple(nav.SECTION_ORDER)


def inyectar_estilos(tema: str) -> None:
    """Inyecta los tokens del artifact para el tema activo."""
    st.markdown(f"<style>\n        {css_variables(tema)}\n{_ESTILOS}</style>",
                unsafe_allow_html=True)


def render_ruta() -> Ruta:
    """Dibuja la navegación de tres niveles y devuelve la posición actual."""
    st.session_state.setdefault("vd_tema", "Claro")
    st.session_state.setdefault("vd_categoria", nav.CAT_ORDER[0])

    if st.session_state.get("vd_vista") not in _orden(st.session_state.vd_categoria):
        st.session_state.vd_vista = _orden(st.session_state.vd_categoria)[0]

    with st.sidebar:
        st.markdown('<p class="vd-brand">Invierte &amp; Gana</p>', unsafe_allow_html=True)
        st.markdown('<p class="vd-brand-sub">Viaje del dinero</p>', unsafe_allow_html=True)

        st.markdown('<p class="vd-lab">Categoría</p>', unsafe_allow_html=True)
        categoria = st.selectbox(
            "Categoría", nav.CAT_ORDER, key="vd_categoria",
            format_func=lambda c: nav.CAT_LABELS[c], label_visibility="collapsed",
        )

        orden = _orden(categoria)
        if st.session_state.get("vd_vista") not in orden:
            st.session_state.vd_vista = orden[0]
        vistas = _vistas(categoria)

        st.markdown('<p class="vd-lab">Vista</p>', unsafe_allow_html=True)
        vista = st.radio(
            "Vista", orden, key="vd_vista",
            format_func=lambda v: vistas[v], label_visibility="collapsed",
        )

        # El ETF es el ÚLTIMO segmento y solo existe en Cash flow: Salud NAV y Hoja Excel
        # van a una vista consolidada, sin ETF que elegir (igual que `showTab` en el demo).
        etf = None
        if vista == nav.VISTA_CON_ETF and categoria in nav.CATS:
            st.markdown('<p class="vd-lab">ETF</p>', unsafe_allow_html=True)
            etf = st.selectbox(
                "ETF", nav.CATS[categoria], key=f"vd_etf_{categoria}",
                label_visibility="collapsed",
            )

        st.markdown('<p class="vd-lab">Tema</p>', unsafe_allow_html=True)
        tema = st.radio("Tema", ("Claro", "Oscuro"), key="vd_tema",
                        label_visibility="collapsed", horizontal=True)

    return Ruta(categoria=categoria, vista=vista, etf=etf, tema=tema)


def render_crumb(ruta: Ruta) -> None:
    """La ruta superior: misma superficie que la página, borde dashed y mono en
    mayúsculas como único acento — el tratamiento del demo."""
    segmentos = [ruta.categoria_label, ruta.vista_label]
    if ruta.etf:
        segmentos.append(ruta.etf)
    partes = '<span class="vd-sep">|</span>'.join(
        f'<span class="vd-seg">{s}</span>' for s in segmentos)
    st.markdown(f'<nav class="vd-crumb" aria-label="Ubicación">{partes}'
                f'<span class="vd-help">¿Cómo funciona? →</span></nav>',
                unsafe_allow_html=True)


def render_placeholder(ruta: Ruta) -> None:
    """Superficie honesta mientras la vista no se porta (Fases 3-5)."""
    st.markdown('<span class="vd-badge">En construcción</span>', unsafe_allow_html=True)
    st.markdown(f'<h2 class="vd-title">{ruta.vista_label}</h2>', unsafe_allow_html=True)
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
        section[data-testid="stSidebar"] {
          background: var(--ground); border-right: 1px dashed var(--hair);
        }
        section[data-testid="stSidebar"] * { color: var(--ink); }

        .vd-brand {
          font-family: var(--font-mono); font-size: 12px; font-weight: 700;
          letter-spacing: .12em; text-transform: uppercase; color: var(--ink); margin: 0;
        }
        .vd-brand-sub { font-size: 11.5px; color: var(--ink-mut); margin: 2px 0 1.5rem; }
        .vd-lab {
          font-family: var(--font-mono); font-size: 10.5px; font-weight: 700;
          letter-spacing: .1em; text-transform: uppercase; color: var(--ink-mut);
          margin: 1.1rem 0 .3rem;
        }

        /* La ruta es la misma superficie que la página, no una caja aparte:
           fondo --ground exacto, borde dashed, mono en mayúsculas. */
        .vd-crumb {
          display: flex; align-items: center; gap: 0; margin: 0 0 26px;
          padding: 13px 16px; background: var(--ground);
          border: 1px dashed var(--hair); flex-wrap: wrap;
        }
        .vd-seg {
          font-family: var(--font-mono); font-size: 12px; font-weight: 700;
          letter-spacing: .06em; text-transform: uppercase; color: var(--ink);
          padding: 6px 10px;
        }
        .vd-sep { color: var(--ink-mut); opacity: .6; font-size: 13px; margin: 0 6px; }
        .vd-help {
          margin-left: auto; font-family: var(--font-mono); font-size: 11px;
          font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
          color: var(--ink-mut);
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
        [data-baseweb="input"] > div,
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
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
          .vd-crumb { padding: 10px 12px; }
          .vd-seg { font-size: 11px; padding: 4px 6px; }
          .vd-help { margin-left: 0; width: 100%; padding-top: 6px; }
        }
"""
