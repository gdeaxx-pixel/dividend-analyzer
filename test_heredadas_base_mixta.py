"""Tarea 1 (2026-08-23) — test cruzado de base mixta en `ui/heredadas.py`.

Regla 3b del contrato (`specs/roc-nra-invariants.md`): todo eje con más de una vista
necesita un test que compare DOS VISTAS DEL MISMO NÚMERO entre sí. Las vistas aquí son:

  1. `_resumen_consolidado` («Dividendos cobrados» y el ROI del TOTAL)
  2. `_cuadricula_roc_consolidada` («Div. pagados (neto)» / «En efectivo»)
  3. `logic.build_dividend_tax_totals` (el objeto fiscal único, re-derivado directo del CSV)

El fixture es MIXTO Schwab+IB: un portafolio de un solo bróker NO vale — así nació el
test mentiroso del A1 (verde meses con el defecto vivo porque su fixture era solo-Schwab).
Se construye uniendo las transacciones normalizadas de `fixtures/schwab_synth_2`
(Schwab: retención en fila aparte, Action 'NRA Tax Adj', sin la palabra dividend) con las
de `fixtures/ib_synth_1` (IB: retención PLEGADA en la fila
'Dividend - Foreign Tax Withholding'), sin solapamiento de tickers.

Criterio de aceptación exacto (en los DOS brókers):

    neto − (drip + efectivo) == 0

Hoy (con el bug) da == −withheld en Schwab.

Las vistas 1 y 2 se retiraron con el rediseño v4 (2026-09-28); su invariante (neto, no
bruto; `net_profit`, no la fórmula vieja) lo vigila ahora `test_vigilar_data.py`.
"""

import os

import pandas as pd
import pytest

import logic
from ui.heredadas import _agregados


class FakeFile:
    def __init__(self, content: bytes, name: str = "test.csv"):
        import io
        self._buf = io.BytesIO(content)
        self.name = name

    def read(self):
        return self._buf.read()

    def seek(self, n):
        self._buf.seek(n)


_MKT_MOCK = lambda t, d: (pd.DataFrame({"Close": [20.0], "Dividends": [0.0], "Stock Splits": [0.0]},
                                       index=[pd.Timestamp("2024-10-15")]), None)


def _df_broker(fixture_dir, csv_name):
    raw = open(os.path.join(os.path.dirname(__file__), "fixtures", fixture_dir,
                            csv_name), "rb").read()
    df, broker = logic.load_and_detect_csv(FakeFile(raw, f"{fixture_dir}.csv"))
    return logic.normalize_csv(df), broker


def _resultados_mixtos(monkeypatch):
    """analyze_portfolio sobre Schwab synth_2 + IB synth_1 concatenados (tickers disjuntos)."""
    df_s, broker_s = _df_broker("schwab_synth_2", "synthetic_transactions.csv")
    assert broker_s == "schwab"
    df_i, broker_i = _df_broker("ib_synth_1", "synthetic_transactions.csv")
    assert broker_i == "ibkr"

    # columnas comunes, para no inventar nada: intersección preservando orden de schwab
    cols = [c for c in df_s.columns if c in df_i.columns]
    mixto = pd.concat([df_s[cols], df_i[cols]], ignore_index=True)

    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    results = logic.analyze_portfolio(mixto, version="TEST_BASE_MIXTA")
    return results, mixto


def test_e1_retorno_total_de_cartera_es_la_suma_de_net_profit(monkeypatch):
    """C·1/E1: el titular de cartera (`_agregados`) ya no cuenta el DRIP dos veces —
    el total es la suma de `net_profit` del motor, no `mv + neto - inv`. El fixture
    mixto no trae DRIP real, así que se fuerza un `net_profit` distinto de
    `mv + div - pk` en una posición (simula lo que hace el DRIP: mv ya incluye las
    acciones reinvertidas) para probar que el código LEE net_profit y no recalcula."""
    results, _mixto = _resultados_mixtos(monkeypatch)
    todos = ["MSTY", "SCHB", "NVDY", "CONY", "SMH"]
    results["MSTY"]["net_profit"] = results["MSTY"]["net_profit"] + 500.0  # divergencia forzada

    inv, mv, div, tr, pct = _agregados(results, todos)

    esperado = sum(results[t]["net_profit"] for t in todos)
    formula_vieja = mv + div - inv
    assert tr == pytest.approx(esperado, abs=0.01)
    assert tr != pytest.approx(formula_vieja, abs=0.01), (
        "el total sigue siendo mv + div - inv, no net_profit")
    assert pct == pytest.approx(esperado / inv * 100, abs=0.01)
