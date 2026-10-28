"""Categoría «Detalle» — secciones del viejo `app_old.py` (tag `archivo/app_old-2026-10`)
que el artifact nunca cubrió.

Fase 5 (traspaso § Fase 5 — Arquitectura): estas 4 vistas agrupan las secciones
heredadas que Daniel decidió que vivan en su propia categoría de la ruta, en vez de
resucitar el scroll infinito de `app_old.py`. A diferencia de `ui/nav.py`, este módulo
**no se genera** — el demo del artifact no tiene una quinta categoría, así que
inventarla ahí rompería el `--check` de `tools/extract_design_system.py` y dejaría
que el port divergiera de su fuente sin que nadie lo note. Aquí sí se escribe a mano,
porque no hay nada que extraer: nunca existió en el artifact.

Regla de método de esta fase (no la de las fases 1-4): se copia la lógica y el texto
literal de `app_old.py`, re-vestido con `ui/tokens.py`. No se redactan de nuevo los
textos ni se reinterpretan las cifras.

Fase 5b — Portafolios e Ingresos:
- Portafolios (filas 8, 9, 15, 16, 35, 36) — `app_old.py:3901-3945` (Tus dos portafolios),
  `app_old.py:3989-4029` (Portafolio dividendos), `app_old.py:4997-5337` (Detalle por
  portafolio + Resumen consolidado), `app_old.py:1869-1895` (`_render_interpretation`,
  filas 35/36).
  Desde el rediseño v4 (2026-09-28) las filas 9, 15, 16, 35 y 36 son «Lo que toca vigilar».
- Ingresos (filas 11, 12, 14) — `app_old.py:4153-4995`, todo detrás de la misma guarda
  `_wizard_income_df is not None` que en `app_old.py` (verificado por indentación: el
  bloque completo — gráfica, cuadrícula ROC y las 3 cuadrículas Schwab-vs-cálculo —
  vive dentro de `if _income_df_s3 is not None and len(_income_df_s3) > 0:`). La
  dona de concentración de ingreso es la excepción: usa `results` directo, sin CSV
  de ingresos, y por eso se muestra siempre que haya ≥2 tickers con ingreso.

Reusa `ui/adapters.py::salud_nav_data` para las tarjetas de salud del NAV (fila 9):
mismo objeto que ya consume la vista Salud NAV — no se recalcula `classify_roc_health`
por segunda vez (espíritu de la Regla 3 del contrato ROC/NRA, aunque esta fila no sea
fiscal).
"""

from __future__ import annotations

import streamlit as st

import logic

CAT_CLAVE = "detalle"
CAT_LABEL = "Portafolios"

VIEWS = {
    "portafolios": "Portafolios",
}

VIEW_ORDER = ("portafolios",)


# ── Fila 8 — Tus dos portafolios ────────────────────────────────────────────────

def _agregados(resultados: dict, tickers: list[str]) -> tuple:
    from ui.adapters import _tiene_datos

    filas = [(t, resultados[t]) for t in tickers if _tiene_datos(resultados.get(t))]
    inv = sum(s["pocket_investment"] for _, s in filas)
    mv = sum(s["market_value"] for _, s in filas)
    # `dividends_collected_cash` no se puede sumar entre tickers: viene BRUTO en Schwab
    # y NETO en IB (misma mezcla de bases que ya resolvió el PR C en `_cuadricula_roc_
    # consolidada` de este archivo y en `report._dividendos_netos`). `dividends_net_total`
    # es el objeto fiscal único (`logic.build_dividend_tax_totals`, corrido dentro de
    # `analyze_portfolio`) y ya resuelve la convención por ticker — sumarlo hace que el
    # "Retorno total" reste la retención NRA también para Schwab. Si no está presente
    # (stats legado sin pasar por `analyze_portfolio`) degrada al campo crudo.
    div = sum(s.get("dividends_net_total") if s.get("dividends_net_total") is not None
              else s.get("dividends_collected_cash", 0)
              for _, s in filas)
    tr = sum(s["net_profit"] for _, s in filas)
    pct = tr / inv * 100 if inv > 0 else 0
    return inv, mv, div, tr, pct


def _tus_dos_portafolios(resultados: dict, classify_map: dict, tema: str) -> tuple[list, list]:
    """Fila 8 — Portafolios v3: el componente `ui/componentes/portafolios.html` (dona
    agrupada + cascada precio → dividendos → total) sustituye a las tarjetas A/B y a la
    dona Altair de `app_old.py:3901-3987` (rediseño «Propuesta v3», sep-2026). Sin título
    ni lede: la ruta ya dice Portafolios (decisión de Daniel). Las cifras las calcula
    `ui.adapters.portafolios_data` en Python; el componente solo dibuja. Devuelve
    `(mode_a, mode_b)` con los tickers que tienen datos, que sigue usando
    `_portafolio_dividendos`."""
    from ui import adapters, componentes

    mode_a = sorted(t for t, m in classify_map.items()
                     if m == "mode_a" and adapters._tiene_datos(resultados.get(t)))
    mode_b = sorted(t for t, m in classify_map.items()
                     if m == "mode_b" and adapters._tiene_datos(resultados.get(t)))
    if not (mode_a or mode_b):
        return mode_a, mode_b

    datos = adapters.portafolios_data(resultados, classify_map)
    if datos is not None:
        componentes.render_portafolios(datos, tema)

    return mode_a, mode_b


# ── Riesgo de la mezcla (dona Dividendos/Crecimiento + caída en dólares) ───────

def _receta_referencia() -> dict | None:
    """La canasta de referencia vive solo en `st.secrets["receta_referencia"]` (el repo es
    público). Sin `secrets.toml` no se toca `st.secrets`: hacerlo pinta un recuadro rojo en
    la página aunque se capture la excepción (ver `ui/carga.py:_clave_gemini`)."""
    try:
        if not st.secrets.load_if_toml_exists():
            return None
        r = st.secrets.get("receta_referencia")
        if r is None:
            return None
        nombre, canasta, pct = r.get("nombre"), r.get("canasta"), r.get("pct_dividendos")
        div, crec = r.get("dividendos"), r.get("crecimiento")
        if not (isinstance(nombre, str) and isinstance(canasta, str)):
            return None
        if isinstance(pct, bool) or not isinstance(pct, int) or not 0 <= pct <= 100:
            return None
        listas = []
        for lista in (div, crec):
            if isinstance(lista, str):
                return None
            lista = list(lista or [])
            if not lista or not all(isinstance(t, str) for t in lista):
                return None
            listas.append(lista)
        return {"nombre": nombre, "canasta": canasta, "pct_dividendos": pct,
                "dividendos": listas[0], "crecimiento": listas[1]}
    except Exception:                                              # noqa: BLE001
        return None


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _historias_riesgo(tickers: tuple[str, ...]) -> tuple[dict, list]:
    """Historia ['Close', 'Dividends'] por ticker vía `price_cache.load_history` (caché →
    en vivo → caché vencido). Vacía o con error → a la lista de sin historia."""
    import price_cache

    historias, sin_historia = {}, []
    for t in tickers:
        try:
            h = price_cache.load_history(t).history
        except Exception:                                          # noqa: BLE001
            h = None
        if h is None or h.empty:
            sin_historia.append(t)
        else:
            historias[t] = h
    return historias, sorted(sin_historia)


def _riesgo_mezcla(resultados: dict, classify_map: dict, tema: str) -> None:
    """Sección «Riesgo de la mezcla», entre Portafolios v3 y Portafolio dividendos. Selector
    «Tus fondos» / canasta de referencia; las cifras salen de `ui.adapters.riesgo_mezcla_data`."""
    from ui import adapters, componentes

    del_usuario = {t for t, m in classify_map.items()
                   if m in ("mode_a", "mode_b") and adapters._tiene_datos(resultados.get(t))
                   and adapters._f(resultados[t].get("market_value")) > 0}
    receta = _receta_referencia()
    tickers = set(del_usuario)
    if receta:
        tickers |= set(receta["dividendos"]) | set(receta["crecimiento"])
    if not tickers:
        return
    historias, sin = _historias_riesgo(tuple(sorted(tickers)))
    sin_historia = [t for t in sin if t in del_usuario]
    datos = adapters.riesgo_mezcla_data(resultados, classify_map, historias, receta, sin_historia)
    if datos is not None:
        componentes.render_riesgo(datos, tema)


# ── Fila 9 — Portafolio dividendos (erosión del NAV, fondo por fondo) ──────────

def _portafolio_dividendos(resultados: dict, mode_a: list[str]) -> None:
    """Fila 9 — «Lo que toca vigilar» (rediseño v4, sep-2026): ROC arriba, luego el
    componente `ui/componentes/vigilar.html` con los puntos a vigilar de cada fondo, y las
    rutas de la calculadora como botones nativos (un clic dentro del iframe no puede
    cambiar la ruta). Sustituye al titular por fondo, sus dos expanders, «El trato
    completo» y el «Detalle por portafolio». `salud_nav_data` corre UNA vez por fondo y
    lo comparten el ROC y el adapter. Diseño:
    `Obsidian/APPs/Dividend-Analyzer/demos/portafolios-v4-detalle.html`."""
    if not mode_a:
        return
    from ui import componentes
    from ui.adapters import roc_cartera_data, salud_nav_data, vigilar_data

    filas = []
    for ticker in mode_a:
        stats = resultados.get(ticker)
        if not isinstance(stats, dict) or "error" in stats:
            continue
        filas.append((ticker, salud_nav_data(ticker, stats)))
    if not filas:
        return

    tema = st.session_state.get("vd_tema", "Claro")
    roc = roc_cartera_data([datos for _, datos in filas])
    componentes.roc_de_vista(roc["estado"], tema, roc["frase"], tam=64)

    datos = vigilar_data(resultados, dict(filas))
    if datos is None:
        return
    componentes.render_vigilar(datos, tema)
    _botones_ruta(datos["rutas"])


def _ir_a_ruta(cat: str, vista: str, etf: str | None) -> None:
    st.session_state.vd_categoria = cat
    st.session_state.vd_vista = vista
    if etf:
        st.session_state[f"vd_etf_{cat}"] = etf


def _botones_ruta(rutas: list[dict]) -> None:
    """«Para entenderlo a fondo»: las vistas de la calculadora donde se estudia cada punto,
    en orden de estudio. Botones nativos: la ruta vive en `st.session_state` y solo un
    callback de Python puede cambiarla."""
    if not rutas:
        return
    st.markdown('<p class="vd-her-subtitulo">Para entenderlo a fondo, en este orden</p>',
                unsafe_allow_html=True)
    for i, r in enumerate(rutas, 1):
        c1, c2 = st.columns([2, 3])
        with c1:
            st.button(f"{i} · {r['etiqueta']} →", key=f"vd_vig_ruta_{r['clave']}",
                      type="tertiary", on_click=_ir_a_ruta,
                      args=(r["cat"], r["vista"], r["etf"]))
        with c2:
            st.caption(r["que"])


def render_portafolios(resultados: dict, tema: str = "Claro") -> None:
    if not resultados:
        st.markdown('<span class="vd-badge">Portafolios</span>', unsafe_allow_html=True)
        st.markdown('<h2 class="vd-title">Portafolios</h2>', unsafe_allow_html=True)
        st.markdown('<p class="vd-lede">Carga tu CSV de transacciones para ver esta vista.</p>',
                    unsafe_allow_html=True)
        return
    classify_map = logic.classify_tickers(list(resultados.keys()))
    mode_a, _mode_b = _tus_dos_portafolios(resultados, classify_map, tema)
    _riesgo_mezcla(resultados, classify_map, tema)
    _portafolio_dividendos(resultados, mode_a)


# ── Despacho ─────────────────────────────────────────────────────────────────

def render_vista(vista: str, ruta) -> None:
    """Despacho de Detalle — solo Portafolios (poda de Ingresos, Proyección y
    Estrategias, decisión de Daniel 2026-08-25)."""
    from ui.vistas import obtener_resultados

    render_portafolios(obtener_resultados(), tema=ruta.tema)


ESTILOS_HEREDADAS = """
        [data-testid="stMarkdownContainer"] p.vd-her-subtitulo {
          font-family: var(--font-mono); font-size: 11px; font-weight: 700;
          letter-spacing: .05em; text-transform: uppercase; color: var(--ink);
          margin: 18px 0 6px;
        }
"""
