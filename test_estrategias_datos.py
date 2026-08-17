"""Vista «Estrategias» (`ui/heredadas._serie_temporal_estrategias`) — red anti-regresion.

Contexto: esa vista era la ULTIMA de la app que bajaba de yfinance en cada render
(`yf.download(..., auto_adjust=True)`), saltandose `price_cache`. Al migrarla aparecio una
trampa: `auto_adjust=True` mete el dividendo DENTRO del precio, asi que la serie vieja medía
retorno total; el cache guarda `auto_adjust=False` a proposito (`Close` crudo + `Dividends`
aparte, para que el DRIP no se cuente dos veces). Cambiar solo la FUENTE, sin reinvertir las
distribuciones, convierte el benchmark en solo-precio — en YMAX eso borra ~58% del resultado
y hace que el portafolio real se vea artificialmente bien en la unica vista cuyo proposito es
esa comparacion.

Tier 1 (estructural, sin red ni cache): la vista no vuelve a llamar yfinance directo.
Tier 2 (sobre el cache versionado, sin red): reinvertir sigue importando — el motor no
puede degradar a solo-precio sin que esto falle.
"""
import os
import re
import sys

import pandas as pd
import pytest

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

_HEREDADAS = os.path.join(BASE, "ui", "heredadas.py")


def _fuente() -> str:
    with open(_HEREDADAS, encoding="utf-8") as f:
        return f.read()


# ── Tier 1 — estructural ─────────────────────────────────────────────────────


def test_heredadas_no_llama_yfinance_directo():
    """`ui/heredadas.py` no puede volver a bajar datos en runtime: todo pasa por
    `price_cache.load_history`, que resuelve cache-primero y declara el fallback.

    Se analiza el AST y no el texto: un grep marca tambien las menciones en prosa (este
    mismo modulo cita `yf.download(...)` en su docstring para explicar de que se migro), y
    un guard que grita por su propia documentacion se termina ignorando."""
    import ast

    arbol = ast.parse(_fuente(), filename=_HEREDADAS)

    importa_yf = [
        n for n in ast.walk(arbol)
        if (isinstance(n, ast.Import) and any(a.name == "yfinance" for a in n.names))
        or (isinstance(n, ast.ImportFrom) and n.module == "yfinance")
    ]
    assert not importa_yf, (
        f"reaparecio `import yfinance` en ui/heredadas.py (linea "
        f"{importa_yf[0].lineno}) — la vista Estrategias debe leer de price_cache")

    llamadas = [
        n for n in ast.walk(arbol)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id in ("yf", "yfinance")
    ]
    assert not llamadas, (
        f"`ui/heredadas.py` volvio a llamar yfinance directo en la linea "
        f"{llamadas[0].lineno} — debe pasar por price_cache.load_history")


def test_estrategias_usa_price_cache_y_el_motor():
    """La serie del ETF alternativo se arma con el motor event-driven ya reconciliado,
    no con una formula propia de `acciones x precio`."""
    src = _fuente()
    assert "price_cache.load_history(" in src
    assert "backtest.run_backtest(" in src
    assert re.search(r"drip\s*=\s*True", src)
    assert "history=hist" in src, "el motor debe recibir la historia inyectada del cache"


def test_ymax_esta_en_el_universo_del_cache():
    """Sin YMAX en `fetch_price_cache.TICKERS` la vista seguiria saliendo a la red por el."""
    import fetch_price_cache

    faltan = [t for t in ("SCHB", "XLK", "YMAX", "SMH") if t not in fetch_price_cache.TICKERS]
    assert not faltan, f"tickers de _ESTR_ETF_MAP fuera del cache: {faltan}"


def test_los_4_etf_de_la_comparacion_tienen_parquet():
    import price_cache

    from ui.heredadas import _ESTR_ETF_MAP

    meta = price_cache._load_yaml(price_cache.META_PATH)
    faltan = [t for t in _ESTR_ETF_MAP if t not in meta]
    assert not faltan, f"sin entrada en _meta.yaml del cache: {faltan}"


# ── Tier 2 — el DRIP no puede desaparecer en silencio ────────────────────────

_FLOWS = [(pd.Timestamp("2024-03-01"), 5000.0),
          (pd.Timestamp("2025-01-15"), 5000.0),
          (pd.Timestamp("2025-09-01"), 5000.0)]
_END = pd.Timestamp("2026-08-14")


def _valor_final_motor(ticker: str, hist: pd.DataFrame) -> float:
    """Réplica exacta de lo que hace la vista: un tranche por compra, sumados."""
    import backtest

    total = None
    for bd, amt in _FLOWS:
        if bd > hist.index.max():
            continue
        r = backtest.run_backtest(ticker, start_date=bd, initial_capital=amt,
                                  drip=True, nra_rate=0.0, end_date=_END, history=hist)
        s = r.daily["total_value"]
        total = s if total is None else total.add(s, fill_value=0.0)
    v = total[total > 0]
    return float(v.iloc[-1])


def _valor_final_solo_precio(hist: pd.DataFrame) -> float:
    """El bug que este test previene: mismo cálculo sobre el `Close` crudo del cache,
    sin reinvertir las distribuciones."""
    prices = hist["Close"].dropna()
    port = pd.Series(0.0, index=prices.index)
    for bd, amt in _FLOWS:
        fut = prices[prices.index >= bd]
        if fut.empty:
            continue
        buy_p = float(fut.iloc[0])
        if buy_p <= 0:
            continue
        port[prices.index >= bd] += (amt / buy_p) * prices[prices.index >= bd]
    v = port[port > 0]
    return float(v.iloc[-1])


@pytest.mark.parametrize("ticker,min_ventaja_pct", [
    ("YMAX", 50.0),   # fondo de distribucion alta: casi todo el retorno va por el dividendo
    ("SCHB", 1.0),
])
def test_reinvertir_cambia_el_resultado(ticker, min_ventaja_pct):
    """Si alguien degrada la vista a solo-precio, el valor final cae — y en un fondo de
    distribucion alta cae muchisimo. Este test fija esa distancia: no puede desaparecer."""
    import price_cache

    hr = price_cache.load_history(ticker, start=_FLOWS[0][0] - pd.Timedelta(days=10), end=_END)
    if hr.history is None or hr.history.empty:
        pytest.skip(f"sin cache para {ticker}")

    con_drip = _valor_final_motor(ticker, hr.history)
    solo_precio = _valor_final_solo_precio(hr.history)

    ventaja = (con_drip / solo_precio - 1.0) * 100.0
    assert ventaja >= min_ventaja_pct, (
        f"{ticker}: reinvertir solo aporta {ventaja:.1f}% sobre el precio pelado "
        f"(esperado >={min_ventaja_pct}%). O el motor dejo de reinvertir, o la vista "
        f"volvio a medir solo precio.")


def test_la_serie_del_etf_es_creciente_en_indice_y_positiva():
    """Higiene de la serie que se grafica: indice ordenado y valores > 0."""
    import price_cache

    hr = price_cache.load_history("SCHB", start=_FLOWS[0][0] - pd.Timedelta(days=10), end=_END)
    if hr.history is None or hr.history.empty:
        pytest.skip("sin cache para SCHB")

    import backtest

    r = backtest.run_backtest("SCHB", start_date=_FLOWS[0][0], initial_capital=5000.0,
                              drip=True, nra_rate=0.0, end_date=_END, history=hr.history)
    s = r.daily["total_value"]
    assert s.index.is_monotonic_increasing
    assert (s > 0).all()
    assert s.index.min().normalize() >= _FLOWS[0][0].normalize()
