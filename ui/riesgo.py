"""Categoría «Riesgo» — qué le pasaría a tu mezcla Dividendos/Crecimiento en una caída, en
dólares, contra una canasta de referencia.

**Este módulo NO se genera y NO calcula nada de riesgo.** Igual que `ui/impuestos.py`, la
categoría no existe en el demo del artifact, así que inventarla en `ui/nav.py` rompería el
`--check` de `tools/extract_design_system.py`. Se compone a mano en `ui/chrome.py` en tiempo
de import. Hasta #227 la sección vivía dentro de Portafolios (`ui/heredadas.py`); Daniel la
sacó a su propia categoría, segunda en el menú.

Las cifras salen de `riesgo_mezcla.py` vía `ui.adapters.riesgo_mezcla_data`; aquí solo se
arma la entrada (historias, secreto de la canasta) y se RENDERIZA en
`ui/componentes/riesgo.html`.
"""

from __future__ import annotations

import functools
import os

import pandas as pd
import streamlit as st

import estres_2022
import logic

CAT_CLAVE = "riesgo"
CAT_LABEL = "Riesgo"

VIEWS = {
    "riesgo": "Riesgo",
}

# Una sola vista: con una vista el breadcrumb nativo no dibuja el segmento de vista
# (`ui/chrome.py:unica_vista`), mismo patrón que `impuestos.VIEW_ORDER`.
VIEW_ORDER = ("riesgo",)


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


_DIR_ESTRES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge", "estres_2022")


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _historias_estres(tickers: tuple[str, ...]) -> dict:
    """Historia ['Close', 'Dividends'] de 2022 por ticker, solo del snapshot congelado
    (`knowledge/estres_2022/`, lo escribe `fetch_estres_2022.py` para todo fondo que la app
    reconoce). Nada en vivo: no se llama a yfinance desde la UI. Sin archivo, el ticker no entra
    y la simulación lo deja fuera con nota."""
    historias = {}
    for t in tickers:
        ruta = os.path.join(_DIR_ESTRES, f"{t}.parquet")
        try:
            h = pd.read_parquet(ruta) if os.path.exists(ruta) else None
        except Exception:                                          # noqa: BLE001
            h = None
        if h is not None and not h.empty and "Close" in h and not h["Close"].isna().any():
            historias[t] = h[["Close", "Dividends"]]
    return historias


def _estres_para(tickers: set[str], receta: dict | None):
    """(función `datos_estres` ya armada, filas del modal) para los fondos dados, o (None, None)
    si no hay parámetros. La función recibe `(pesos_dividendos, pesos_crecimiento)`."""
    try:
        parametros = estres_2022.cargar_parametros()
        sub = estres_2022.subyacentes_yieldmax(logic.load_instruments())
        v = parametros["ventana"]
        # Un YieldMax con subyacente se simula con su acción; del resto se pide su propia
        # historia (si no existía en 2022, no hay archivo).
        pedir = sorted({sub[t] for t in tickers if t in sub} | {t for t in tickers if t not in sub})
        historias = _historias_estres(tuple(pedir))
    except Exception:                                              # noqa: BLE001
        return None, None
    fn = functools.partial(_datos_estres, historias=historias, parametros=parametros, subyacentes=sub)
    return fn, estres_2022.filas_modal(parametros)


def _datos_estres(pesos_div: dict, pesos_crec: dict, *, historias, parametros, subyacentes):
    try:
        return estres_2022.datos_estres(pesos_div, pesos_crec, historias, parametros, subyacentes)
    except Exception:                                              # noqa: BLE001
        return None


def _riesgo_mezcla(resultados: dict, classify_map: dict, tema: str) -> None:
    """Sección «Riesgo de la mezcla». Selector
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
    estres, estres_modal = _estres_para(tickers, receta)
    datos = adapters.riesgo_mezcla_data(resultados, classify_map, historias, receta, sin_historia,
                                        estres, estres_modal)
    if datos is not None:
        componentes.render_riesgo(datos, tema)


def hay_receta() -> bool:
    return _receta_referencia() is not None


def abrir_sin_archivo() -> None:
    """Entrada desde la hoja de carga: pasa a la ruta con la categoría Riesgo, sin archivo.
    La ruta solo se dibuja con `_wizard_listo`, y sin CSV `_resultados()` devuelve `{}`."""
    st.session_state["_wizard_listo"] = True
    st.session_state["vd_categoria"] = CAT_CLAVE
    st.session_state["vd_vista"] = VIEW_ORDER[0]


def volver_a_cargar() -> None:
    """Regreso a la hoja de carga. Olvida la categoría para que, al subir el archivo, se
    aterrice en Portafolios (`CAT_ORDER_TOTAL[0]`) y no en la última vista sin datos."""
    st.session_state["_wizard_listo"] = False
    st.session_state.pop("vd_categoria", None)
    st.session_state.pop("vd_vista", None)


def sin_archivo() -> bool:
    """En la ruta sin CSV: solo se llega así por `abrir_sin_archivo` (el demo trae el suyo)."""
    return (st.session_state.get("_wizard_df_clean") is None
            and not st.session_state.get("_vd_resultados"))


def boton_subir_archivo() -> None:
    st.button("Subir mi archivo →", key="_vd_riesgo_subir_archivo", type="tertiary",
              on_click=volver_a_cargar)


def render_vista(vista: str, ruta) -> None:
    """Despacho de Riesgo — UNA vista. Con archivo se dibuja la mezcla del usuario (y la
    canasta de referencia si hay receta); sin archivo y con receta, solo la canasta, con una
    línea que invita a subirlo; sin ninguno de los dos, el estado vacío de Impuestos."""
    from ui.vistas import obtener_resultados

    resultados = obtener_resultados() or {}
    if resultados:
        classify_map = logic.classify_tickers(list(resultados))
        _riesgo_mezcla(resultados, classify_map, ruta.tema)
        return
    if _receta_referencia():
        st.caption("Sube tu archivo de transacciones para comparar con tus fondos.")
        boton_subir_archivo()
        _riesgo_mezcla({}, {}, ruta.tema)
        return
    st.markdown('<span class="vd-badge">Riesgo</span>', unsafe_allow_html=True)
    st.markdown('<h2 class="vd-title">Riesgo</h2>', unsafe_allow_html=True)
    st.markdown(
        '<p class="vd-lede">Carga tu CSV de transacciones para ver qué le pasaría a tu mezcla '
        'de Dividendos y Crecimiento en una caída.</p>', unsafe_allow_html=True)
