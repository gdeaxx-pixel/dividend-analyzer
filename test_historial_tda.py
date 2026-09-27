"""Tests de §5 (spec T1): historial migrado de TD Ameritrade en los CSV de Schwab.

Las filas `TDA TRAN - …` llegan con `Symbol` vacío, el ticker solo en la descripción y el
DRIP partido en un triplete (`Cash Dividend` / `Journaled Shares` «W-8 WITHHOLDING» /
`Reinvest Shares`). `_resolver_filas_tda` las devuelve al vocabulario nativo de Schwab.

Las cifras de este archivo son LITERALES de la spec (medidas por Opus), nunca calculadas
con la función auditada.
"""
import os

import pandas as pd
import pytest

import logic
from test_logic import FakeFile
from test_vista_impuestos import _MKT_MOCK
from ui.adapters import cashflow_data, verificar_identidades

BASE = os.path.dirname(os.path.abspath(__file__))


def _leer(fixture_dir: str, nombre: str = None) -> pd.DataFrame:
    ruta = os.path.join(BASE, "fixtures", fixture_dir, "synthetic_transactions.csv")
    with open(ruta, "rb") as f:
        df, _broker = logic.load_and_detect_csv(
            FakeFile(f.read(), nombre or f"{fixture_dir}.csv"))
    return df


def _cargar_tda() -> pd.DataFrame:
    return logic.normalize_csv(_leer("schwab_tda_synth"))


# ── T1 · por ticker: bruto, retención, huérfanas y acciones ─────────────────────────

_CASOS = {
    # SCHB: dos tripletes TDA (03/27 y 06/26) + un triplete NATIVO (12/18).
    "SCHB": {
        "gross": 9.00, "withheld": 2.70,
        "drip": {'compras': 3, 'fuentes': 3, 'huerfanas': 0, 'importe': 0.0},
        "acciones": ['Buy', 'NRA Tax Adj', 'Reinvest Dividend', 'Reinvest Shares'],
    },
    # XLK: `Qual Div Reinvest` TDA con compra el mismo día → Reinvest Dividend.
    "XLK": {
        "gross": 1.00, "withheld": 0.30,
        "drip": {'compras': 1, 'fuentes': 1, 'huerfanas': 0, 'importe': 0.0},
        "acciones": ['Buy', 'NRA Tax Adj', 'Reinvest Dividend', 'Reinvest Shares'],
    },
    # ES: `Qual Div Reinvest` TDA SIN compra (cobrado en efectivo) → Qualified Dividend,
    # más una «MANDATORY REORGANIZATION FEE» que NO es retención (sigue Journaled Shares).
    "ES": {
        "gross": 4.00, "withheld": 1.20,
        "drip": {'compras': 0, 'fuentes': 0, 'huerfanas': 0, 'importe': 0.0},
        "acciones": ['Buy', 'Journaled Shares', 'NRA Tax Adj', 'Qualified Dividend'],
    },
    # VTI: dividendo NATIVO el mismo día que una compra, que NO se toca (mismo criterio
    # que test_adapters.py::test_un_dividendo_en_efectivo_no_respalda_una_compra_del_drip).
    "VTI": {
        "gross": 5.00, "withheld": 0.00,
        "drip": {'compras': 1, 'fuentes': 0, 'huerfanas': 1, 'importe': 5.0},
        "acciones": ['Buy', 'Cash Dividend', 'Reinvest Shares'],
    },
}


@pytest.mark.parametrize("tk", ["SCHB", "XLK", "ES", "VTI"])
def test_tda_por_ticker(tk):
    """Bruto, retención, DRIP huérfano y vocabulario de acciones por ticker (ver _CASOS)."""
    caso = _CASOS[tk]
    dfc = _cargar_tda()
    t = dfc[dfc["Ticker"] == tk]
    assert not t.empty
    tot = logic.build_dividend_tax_totals(t)
    assert tot["gross"] == pytest.approx(caso["gross"], abs=0.005)
    assert tot["withheld"] == pytest.approx(caso["withheld"], abs=0.005)
    assert logic.drip_huerfanas(t) == caso["drip"]
    assert sorted(t["Action"].unique()) == caso["acciones"]


# ── T2 · W-8 sin ticker: no se atribuye a ninguna posición ──────────────────────────

def test_tda_w8_sin_ticker_no_se_atribuye():
    """Una retención W-8 sin ticker en la descripción no tiene posición a la que ir."""
    dfc = _cargar_tda()
    t = dfc[~dfc["Ticker"].isin(list(_CASOS))]
    assert list(zip(t["Action"], t["Amount"])) == [("Journaled Shares", -5.0)]


# ── T3 · el guard de identidades se desbloquea (el test que paga la spec) ───────────

def test_tda_desbloquea_el_guard_de_identidades(monkeypatch):
    """El caso de la captura de Daniel en miniatura: antes SCHB daba 2.80 ≠ 6.30 y XLK
    0.00 ≠ 0.70; con las filas TDA resueltas, el guard pasa. VTI sigue fallando porque su
    dividendo es NATIVO y una compra del mismo día no lo respalda (§8, fuera de alcance)."""
    dfc = _cargar_tda()
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    res = logic.analyze_portfolio(dfc, version="T1_TDA")
    tx = logic.build_tax_summaries(res, base_rate_pct=30.0, country=None)

    def fallos(tk):
        return verificar_identidades(
            cashflow_data(res[tk], tk, tax_summary=tx.get(tk) or {}), res[tk])

    assert fallos("SCHB") == []
    assert fallos("XLK") == []
    fvti = fallos("VTI")
    assert fvti
    assert "neto = reinvertido + efectivo: 5.00 ≠ 10.00" in fvti[0]


# ── T4 · los CSV nativos salen intactos ─────────────────────────────────────────────

@pytest.mark.parametrize("fixture", ["schwab_synth_1", "schwab_synth_2"])
def test_tda_no_toca_los_csv_nativos(fixture, monkeypatch):
    """Un CSV sin filas TDA sale idéntico con y sin el resolver."""
    a = logic.normalize_csv(_leer(fixture))
    monkeypatch.setattr(logic, "_resolver_filas_tda", lambda df: df)
    b = logic.normalize_csv(_leer(fixture))
    pd.testing.assert_frame_equal(a, b)
