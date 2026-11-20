"""La serie diaria (`daily_trend`) y la cifra escalar (`net_profit`) cuentan el mismo dinero.

Cada caso pasa por `analyze_portfolio` entero con el mercado inyectado. Los esperados son
literales calculados a mano: compra de 10 acciones a 100 (−1000) con el precio plano en 100,
salvo donde el caso diga otra cosa.
"""
import io
import os

import numpy as np
import pandas as pd
import pytest

import logic

BASE = os.path.dirname(os.path.abspath(__file__))
COMPRA = dict(Date='2024-01-02', Action='Buy', Quantity=10, Amount=-1000.0)


def _mercado(cierres, inicio='2024-01-02'):
    idx = pd.bdate_range(inicio, periods=len(cierres))
    return pd.DataFrame({'Close': cierres, 'Dividends': 0.0, 'Stock Splits': 0.0}, index=idx)


def _sin_cache():
    return getattr(logic.analyze_portfolio, '__wrapped__', logic.analyze_portfolio)


def _analizar(monkeypatch, filas, cierres=None, inicio='2024-01-02'):
    md = _mercado([100.0] * 60 if cierres is None else cierres, inicio)
    bench = _mercado([100.0] * len(md), inicio)
    df = pd.DataFrame(filas)
    df['Ticker'] = 'VTI'
    df['Date'] = pd.to_datetime(df['Date'])
    for col in ('Quantity', 'Amount', 'Price'):
        if col not in df:
            df[col] = 0.0
        df[col] = df[col].fillna(0.0)
    monkeypatch.setattr(logic, 'fetch_market_data', lambda t, s: (md.copy(), None))
    monkeypatch.setattr(logic, '_descargar_benchmark', lambda d, ticker='VOO': bench.copy())
    return _sin_cache()(df)['VTI']


def _ganancia(r):
    return r['daily_trend']['User Profit']


def _retorno(r):
    return r['daily_trend']['User Return %']


# ── M2 + M3: el efectivo diario es neto y con signo ─────────────────────────────────────

def test_schwab_retencion_en_fila_aparte_el_mismo_dia(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA,
        dict(Date='2024-02-01', Action='Cash Dividend', Amount=100.0),
        dict(Date='2024-02-01', Action='NRA Tax Adj', Amount=-30.0),
    ])
    assert r['net_profit'] == pytest.approx(70.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(70.0, abs=0.01)
    assert _retorno(r).iloc[-1] == pytest.approx(7.0, abs=1e-6)


def test_ibkr_retencion_plegada_en_la_fila_de_dividendo(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA,
        dict(Date='2024-02-01', Action='Dividend', Amount=100.0),
        dict(Date='2024-02-01', Action='Dividend - Foreign Tax Withholding', Amount=-30.0),
    ])
    assert r['net_profit'] == pytest.approx(70.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(70.0, abs=0.01)
    assert _retorno(r).iloc[-1] == pytest.approx(7.0, abs=1e-6)


def test_reversa_de_dividendo_en_dia_propio_resta(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA,
        dict(Date='2024-02-01', Action='Cash Dividend', Amount=100.0),
        dict(Date='2024-02-15', Action='Dividend Reversal', Amount=-100.0),
    ])
    assert r['net_profit'] == pytest.approx(0.0, abs=0.01)
    assert _ganancia(r).loc['2024-02-14'] == pytest.approx(100.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(0.0, abs=0.01)
    assert _retorno(r).iloc[-1] == pytest.approx(-1.0, abs=1e-6)


def test_schwab_reinversion_no_resta_la_retencion_dos_veces(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA,
        dict(Date='2024-02-01', Action='Reinvest Dividend', Amount=100.0),
        dict(Date='2024-02-01', Action='NRA Tax Adj', Amount=-30.0),
        dict(Date='2024-02-01', Action='Reinvest Shares', Quantity=0.7, Amount=-70.0),
    ])
    assert r['net_profit'] == pytest.approx(70.0, abs=0.01)
    assert r['daily_trend']['Market Value'].iloc[-1] == pytest.approx(1070.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(70.0, abs=0.01)
    assert _retorno(r).iloc[-1] == pytest.approx(7.0, abs=1e-6)


def test_schwab_retencion_fechada_dos_dias_despues(monkeypatch):
    r = _analizar(monkeypatch, [
        dict(Date='2023-01-03', Action='Buy', Quantity=10, Amount=-1000.0),
        dict(Date='2023-02-01', Action='Cash Dividend', Amount=100.0),
        dict(Date='2023-02-03', Action='NRA Tax Adj', Amount=-30.0),
    ], inicio='2023-01-03')
    assert r['net_profit'] == pytest.approx(70.0, abs=0.01)
    assert _ganancia(r).loc['2023-02-01'] == pytest.approx(100.0, abs=0.01)
    assert _ganancia(r).loc['2023-02-02'] == pytest.approx(100.0, abs=0.01)
    assert _ganancia(r).loc['2023-02-03'] == pytest.approx(70.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(70.0, abs=0.01)
    assert _retorno(r).iloc[-1] == pytest.approx(6.7, abs=1e-6)


def test_schwab_devolucion_de_la_retencion_dias_despues(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA,
        dict(Date='2024-02-01', Action='Cash Dividend', Amount=100.0),
        dict(Date='2024-02-01', Action='NRA Tax Adj', Amount=-30.0),
        dict(Date='2024-02-15', Action='NRA Tax Adj', Amount=30.0),
    ])
    assert r['net_profit'] == pytest.approx(100.0, abs=0.01)
    assert _ganancia(r).loc['2024-02-14'] == pytest.approx(70.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(100.0, abs=0.01)
    assert _retorno(r).iloc[-1] == pytest.approx(10.21, abs=1e-6)


def test_devolucion_sin_retencion_previa_sigue_a_la_escalar(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA,
        dict(Date='2024-02-01', Action='Cash Dividend', Amount=100.0),
        dict(Date='2024-02-15', Action='NRA Tax Adj', Amount=30.0),
    ])
    assert r['net_profit'] == pytest.approx(100.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(100.0, abs=0.01)
    assert _retorno(r).iloc[-1] == pytest.approx(10.0, abs=1e-6)


# ── Dos vistas del mismo número: la serie contra la cifra escalar, por la cadena real ───

class _Archivo:
    def __init__(self, crudo, nombre):
        self._buf = io.BytesIO(crudo)
        self.name = nombre

    def read(self):
        return self._buf.read()

    def seek(self, n):
        self._buf.seek(n)


def _mercado_determinista(desde, hasta):
    idx = pd.bdate_range(pd.Timestamp(desde) - pd.Timedelta(days=10),
                         pd.Timestamp(hasta) + pd.Timedelta(days=10))
    i = np.arange(len(idx))
    return pd.DataFrame({'Close': 40.0 + 10.0 * np.sin(i / 9.0) + 0.02 * i,
                         'Dividends': 0.0, 'Stock Splits': 0.0}, index=idx)


def _analizar_fixture(monkeypatch, fixture):
    ruta = os.path.join(BASE, 'fixtures', fixture, 'synthetic_transactions.csv')
    with open(ruta, 'rb') as fh:
        crudo, _broker = logic.load_and_detect_csv(_Archivo(fh.read(), f'{fixture}.csv'))
    df = logic.normalize_csv(crudo)
    hasta = pd.to_datetime(df['Date']).max()
    monkeypatch.setattr(logic, 'fetch_market_data',
                        lambda t, s: (_mercado_determinista(s, hasta), None))
    monkeypatch.setattr(logic, '_descargar_benchmark',
                        lambda d, ticker='VOO': _mercado_determinista(
                            pd.to_datetime(d['Date']).min(), hasta))
    return _sin_cache()(df)


POSICIONES = {
    'schwab_synth_1': {'MSTY', 'SCHB', 'TSLY'},
    'schwab_synth_2': {'MSTY', 'SCHB'},
    'ib_synth_1': {'NVDY', 'SMH', 'CONY'},
    'schwab_tda_synth': {'SCHB', 'XLK', 'VTI'},
}

# `User Profit` final − `net_profit` de las posiciones que no cuadran por una causa que no es
# de esta tanda. Cada cifra sale de las filas del CSV de la fixture, no del motor.
DESCUADRE_FUERA_DE_ALCANCE = {
    # Caja miscelánea: `Cash In Lieu` de $0.37 (02-may-2025). Entra en `net_profit` y no en
    # la serie; sumarla sin soltar la fracción de acción que paga la contaría dos veces.
    ('schwab_synth_1', 'TSLY'): -0.37,
    # M4: `Cash Dividend` de $5.00 y su `Reinvest Shares` el mismo día (25-mar-2024). La
    # escalar lo cuenta como efectivo y como acciones; la serie, solo como acciones.
    ('schwab_tda_synth', 'VTI'): -5.00,
}


@pytest.mark.parametrize('fixture', sorted(POSICIONES))
def test_ultimo_dia_de_la_serie_cuadra_con_net_profit(monkeypatch, fixture):
    resultados = _analizar_fixture(monkeypatch, fixture)
    analizados = {t for t, r in resultados.items() if 'daily_trend' in r}
    assert analizados == POSICIONES[fixture]
    for ticker in sorted(analizados):
        r = resultados[ticker]
        descuadre = float(r['daily_trend']['User Profit'].iloc[-1]) - r['net_profit']
        assert descuadre == pytest.approx(
            DESCUADRE_FUERA_DE_ALCANCE.get((fixture, ticker), 0.0), abs=0.01), (fixture, ticker)


def test_el_descuadre_de_tsly_es_exactamente_su_caja_miscelanea(monkeypatch):
    r = _analizar_fixture(monkeypatch, 'schwab_synth_1')['TSLY']
    assert r['misc_cash_total'] == pytest.approx(0.37, abs=0.001)
    ultimo = r['daily_trend'].iloc[-1]
    assert ultimo['Market Value'] == pytest.approx(r['market_value'], abs=0.01)
    assert ultimo['Invested Capital'] == pytest.approx(r['pocket_investment'], abs=0.01)
    assert ultimo['User Profit'] + r['misc_cash_total'] == pytest.approx(r['net_profit'], abs=0.01)


# ── M7: un día sin precio no envenena la serie ──────────────────────────────────────────

SERIE = ['Market Value', 'User Profit', 'User Return %']


def test_cierre_ausente_a_mitad_de_serie_se_valora_al_ultimo_valido(monkeypatch):
    r = _analizar(monkeypatch, [COMPRA], [100.0] * 30 + [float('nan')] + [110.0] * 29)
    dt = r['daily_trend']
    assert int(dt[SERIE].isna().sum().sum()) == 0
    assert dt['Market Value'].iloc[30] == pytest.approx(1000.0, abs=0.01)
    assert dt['User Profit'].iloc[-1] == pytest.approx(100.0, abs=0.01)
    assert dt['User Return %'].iloc[-1] == pytest.approx(10.0, abs=1e-6)
    assert r['volatilidad_anualizada'] > 0


@pytest.mark.parametrize('invalido', [0.0, -5.0])
def test_cierre_cero_o_negativo_un_dia_no_hunde_el_retorno(monkeypatch, invalido):
    r = _analizar(monkeypatch, [COMPRA], [100.0] * 30 + [invalido] + [100.0] * 29)
    dt = r['daily_trend']
    assert dt['Market Value'].iloc[30] == pytest.approx(1000.0, abs=0.01)
    assert dt['User Return %'].min() == pytest.approx(0.0, abs=1e-6)
    assert dt['User Return %'].iloc[-1] == pytest.approx(0.0, abs=1e-6)


def test_cierre_ausente_en_la_ultima_barra_vale_el_ultimo_cierre_valido(monkeypatch):
    r = _analizar(monkeypatch, [COMPRA], [100.0] * 58 + [105.0, float('nan')])
    ultimo = r['daily_trend'].iloc[-1]
    assert r['net_profit'] == pytest.approx(50.0, abs=0.01)
    assert ultimo['Market Value'] == pytest.approx(1050.0, abs=0.01)
    assert ultimo['User Profit'] == pytest.approx(50.0, abs=0.01)
    assert ultimo['User Return %'] == pytest.approx(5.0, abs=1e-6)


def test_cierre_ausente_el_dia_de_la_compra_se_valora_al_primero_posterior(monkeypatch):
    r = _analizar(monkeypatch, [COMPRA], [float('nan')] + [100.0] * 58 + [120.0])
    dt = r['daily_trend']
    assert int(dt[SERIE].isna().sum().sum()) == 0
    assert dt['Market Value'].iloc[0] == pytest.approx(1000.0, abs=0.01)
    assert dt['User Profit'].iloc[-1] == pytest.approx(200.0, abs=0.01)
    assert dt['User Return %'].iloc[-1] == pytest.approx(20.0, abs=1e-6)


# ── M11: la fila fuente de la reinversión no suma acciones ──────────────────────────────

def test_fila_fuente_de_reinversion_con_cantidad_no_suma_acciones(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA,
        dict(Date='2024-01-10', Action='Reinvest Dividend', Quantity=2, Amount=200.0),
        dict(Date='2024-01-10', Action='Reinvest Shares', Quantity=2, Amount=-200.0),
    ])
    ultimo = r['daily_trend'].iloc[-1]
    assert r['shares_owned'] == pytest.approx(12.0, abs=1e-9)
    assert ultimo['Market Value'] == pytest.approx(1200.0, abs=0.01)
    assert ultimo['User Profit'] == pytest.approx(200.0, abs=0.01)
    assert ultimo['User Return %'] == pytest.approx(20.0, abs=1e-6)


def test_reinversion_de_rotulo_ambiguo_sigue_sumando_acciones(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA,
        dict(Date='2024-01-10', Action='Reinvestment', Quantity=2, Amount=-200.0),
    ])
    assert r['shares_owned'] == pytest.approx(12.0, abs=1e-9)
    assert r['daily_trend']['Market Value'].iloc[-1] == pytest.approx(1200.0, abs=0.01)
