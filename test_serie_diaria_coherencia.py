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


def _analizar(monkeypatch, filas, cierres=None, inicio='2024-01-02', splits=None):
    md = _mercado([100.0] * 60 if cierres is None else cierres, inicio)
    for fecha, factor in (splits or {}).items():
        md.loc[pd.Timestamp(fecha), 'Stock Splits'] = factor
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


def test_la_caja_miscelanea_de_tsly_entra_en_la_serie_el_dia_que_se_paga(monkeypatch):
    r = _analizar_fixture(monkeypatch, 'schwab_synth_1')['TSLY']
    assert r['misc_cash_total'] == pytest.approx(0.37, abs=0.001)
    dt = r['daily_trend']
    salto = (dt['User Profit'] - dt['Market Value'] + dt['Invested Capital']).diff()
    assert salto.loc['2025-05-02'] == pytest.approx(0.37, abs=0.001)
    assert dt['Market Value'].iloc[-1] == pytest.approx(r['market_value'], abs=0.01)
    assert dt['User Profit'].iloc[-1] == pytest.approx(r['net_profit'], abs=0.01)


# ── Split inverso: la fila del bróker reinicia las acciones y la fracción se cobra ──────
# Compra 15 acciones a $10. Split inverso 1 por 10 el 1-feb: el bróker deja 1 acción entera
# y paga la media acción sobrante en efectivo ($50) al día siguiente. Cierra a $120.

COMPRA_15 = dict(Date='2024-01-02', Action='Buy', Quantity=15, Amount=-150.0)
CIERRES_SPLIT = [10.0] * 22 + [100.0] * 28 + [120.0] * 10
SPLIT_YAHOO = {'2024-02-01': 0.1}


def _acciones(r):
    valor = r['daily_trend']['Market Value']
    return valor / pd.Series(CIERRES_SPLIT, index=valor.index)


def test_split_inverso_con_fila_y_fraccion_pagada_en_efectivo(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA_15,
        dict(Date='2024-02-01', Action='Reverse Split', Quantity=1),
        dict(Date='2024-02-02', Action='Cash In Lieu', Amount=50.0),
    ], CIERRES_SPLIT, splits=SPLIT_YAHOO)
    assert r['shares_owned'] == pytest.approx(1.0, abs=1e-9)
    assert r['net_profit'] == pytest.approx(20.0, abs=0.01)
    assert _acciones(r).loc['2024-01-31'] == pytest.approx(15.0, abs=1e-9)
    assert _acciones(r).loc['2024-02-01'] == pytest.approx(1.0, abs=1e-9)
    assert _ganancia(r).loc['2024-01-31'] == pytest.approx(0.0, abs=0.01)
    assert _ganancia(r).loc['2024-02-01'] == pytest.approx(-50.0, abs=0.01)
    assert _ganancia(r).loc['2024-02-02'] == pytest.approx(0.0, abs=0.01)
    ultimo = r['daily_trend'].iloc[-1]
    assert ultimo['Market Value'] == pytest.approx(120.0, abs=0.01)
    assert ultimo['User Profit'] == pytest.approx(20.0, abs=0.01)


def test_fila_de_split_un_dia_antes_que_el_split_del_mercado_no_multiplica_dos_veces(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA_15,
        dict(Date='2024-01-31', Action='Reverse Split', Quantity=1),
        dict(Date='2024-02-02', Action='Cash In Lieu', Amount=50.0),
    ], CIERRES_SPLIT, splits=SPLIT_YAHOO)
    assert r['shares_owned'] == pytest.approx(1.0, abs=1e-9)
    assert _acciones(r).loc['2024-01-31'] == pytest.approx(15.0, abs=1e-9)
    assert _acciones(r).loc['2024-02-01'] == pytest.approx(1.0, abs=1e-9)
    assert _ganancia(r).loc['2024-01-31'] == pytest.approx(0.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(20.0, abs=0.01)


def test_fila_de_split_sin_split_en_el_mercado_reinicia_en_la_fecha_de_la_fila(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA_15,
        dict(Date='2024-02-01', Action='Reverse Split', Quantity=1),
        dict(Date='2024-02-02', Action='Cash In Lieu', Amount=50.0),
    ], CIERRES_SPLIT)
    assert r['shares_owned'] == pytest.approx(1.0, abs=1e-9)
    assert r['net_profit'] == pytest.approx(20.0, abs=0.01)
    assert _acciones(r).loc['2024-01-31'] == pytest.approx(15.0, abs=1e-9)
    assert _acciones(r).loc['2024-02-01'] == pytest.approx(1.0, abs=1e-9)
    assert _ganancia(r).iloc[-1] == pytest.approx(20.0, abs=0.01)


def test_compra_el_mismo_dia_despues_de_la_fila_de_split_se_suma(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA_15,
        dict(Date='2024-02-01', Action='Reverse Split', Quantity=1),
        dict(Date='2024-02-01', Action='Buy', Quantity=2, Amount=-200.0),
    ], CIERRES_SPLIT, splits=SPLIT_YAHOO)
    assert r['shares_owned'] == pytest.approx(3.0, abs=1e-9)
    assert _acciones(r).loc['2024-02-01'] == pytest.approx(3.0, abs=1e-9)
    assert r['net_profit'] == pytest.approx(10.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(10.0, abs=0.01)


def test_compra_el_mismo_dia_antes_de_la_fila_de_split_queda_dentro_del_reinicio(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA_15,
        dict(Date='2024-02-01', Action='Buy', Quantity=5, Amount=-50.0),
        dict(Date='2024-02-01', Action='Reverse Split', Quantity=2),
    ], CIERRES_SPLIT, splits=SPLIT_YAHOO)
    assert r['shares_owned'] == pytest.approx(2.0, abs=1e-9)
    assert _acciones(r).loc['2024-02-01'] == pytest.approx(2.0, abs=1e-9)
    assert r['net_profit'] == pytest.approx(40.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(40.0, abs=0.01)


def test_compra_entre_la_fila_de_split_y_el_split_del_mercado_se_convierte(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA_15,
        dict(Date='2024-01-30', Action='Reverse Split', Quantity=1),
        dict(Date='2024-01-31', Action='Buy', Quantity=10, Amount=-100.0),
    ], CIERRES_SPLIT, splits=SPLIT_YAHOO)
    assert r['shares_owned'] == pytest.approx(2.0, abs=1e-9)
    assert _acciones(r).loc['2024-01-31'] == pytest.approx(25.0, abs=1e-9)
    assert _acciones(r).loc['2024-02-01'] == pytest.approx(2.0, abs=1e-9)
    assert r['net_profit'] == pytest.approx(-10.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(-10.0, abs=0.01)


def test_fila_de_split_sin_cantidad_no_reinicia(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA_15,
        dict(Date='2024-02-01', Action='Reverse Split', Quantity=0),
    ], CIERRES_SPLIT, splits=SPLIT_YAHOO)
    assert r['shares_owned'] == pytest.approx(1.5, abs=1e-9)
    assert _acciones(r).loc['2024-02-01'] == pytest.approx(1.5, abs=1e-9)
    assert r['net_profit'] == pytest.approx(30.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(30.0, abs=0.01)


def test_fraccion_pagada_en_efectivo_sin_fila_de_split_sigue_a_la_escalar(monkeypatch):
    r = _analizar(monkeypatch, [COMPRA, dict(Date='2024-02-01', Action='Cash In Lieu', Amount=0.37)])
    assert r['net_profit'] == pytest.approx(0.37, abs=0.001)
    assert _ganancia(r).loc['2024-01-31'] == pytest.approx(0.0, abs=0.001)
    assert _ganancia(r).iloc[-1] == pytest.approx(0.37, abs=0.001)


def test_cargo_de_custodia_resta_en_la_serie(monkeypatch):
    r = _analizar(monkeypatch, [COMPRA, dict(Date='2024-02-01', Action='ADR Mgmt Fee', Amount=-3.0)])
    assert r['net_profit'] == pytest.approx(-3.0, abs=0.01)
    assert _ganancia(r).loc['2024-01-31'] == pytest.approx(0.0, abs=0.01)
    assert _ganancia(r).loc['2024-02-01'] == pytest.approx(-3.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(-3.0, abs=0.01)


# ── Fracción pagada en efectivo por un split que el CSV no declara ───────────────────────
# Compra 10,5 acciones a $30. Split 3 por 1 el 1-feb: serían 31,5, el bróker deja 31 y paga
# la media acción ($5 a $10) el día antes. Cierra a $12. Con el precio ya ajustado por el
# split (como lo da Yahoo) y sin ajustar.

COMPRA_10_5 = dict(Date='2024-01-02', Action='Buy', Quantity=10.5, Amount=-315.0)
PAGO_FRACCION = dict(Date='2024-01-31', Action='Cash In Lieu', Amount=5.0)
CIERRES_AJUSTADOS = [10.0] * 50 + [12.0] * 10
CIERRES_SIN_AJUSTAR = [30.0] * 22 + [10.0] * 28 + [12.0] * 10
SPLIT_3X1 = {'2024-02-01': 3.0}


@pytest.mark.parametrize('cierres', [CIERRES_AJUSTADOS, CIERRES_SIN_AJUSTAR])
def test_fraccion_pagada_antes_de_un_split_sin_fila_sale_de_las_acciones(monkeypatch, cierres):
    r = _analizar(monkeypatch, [COMPRA_10_5, PAGO_FRACCION], cierres, splits=SPLIT_3X1)
    assert r['shares_owned'] == pytest.approx(31.0, abs=1e-9)
    assert r['shares_owned_pocket'] == pytest.approx(31.0, abs=1e-9)
    assert r['market_value'] == pytest.approx(372.0, abs=0.01)
    assert r['net_profit'] == pytest.approx(62.0, abs=0.01)
    valor = r['daily_trend']['Market Value']
    assert valor.loc['2024-01-30'] == pytest.approx(315.0, abs=0.01)
    assert valor.loc['2024-01-31'] == pytest.approx(310.0, abs=0.01)
    assert valor.loc['2024-02-01'] == pytest.approx(310.0, abs=0.01)
    assert _ganancia(r).loc['2024-01-31'] == pytest.approx(0.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(62.0, abs=0.01)
    no_realizada = r['capital_gains']['unrealized']
    assert no_realizada['shares'] == pytest.approx(31.0, abs=1e-9)
    assert no_realizada['basis'] == pytest.approx(315.0, abs=0.01)


def test_fraccion_pagada_tras_un_split_inverso_sin_fila_sale_de_las_acciones(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA_15, dict(Date='2024-02-02', Action='Cash In Lieu', Amount=50.0),
    ], CIERRES_SPLIT, splits=SPLIT_YAHOO)
    assert r['shares_owned'] == pytest.approx(1.0, abs=1e-9)
    assert r['net_profit'] == pytest.approx(20.0, abs=0.01)
    assert _acciones(r).loc['2024-02-01'] == pytest.approx(1.5, abs=1e-9)
    assert _acciones(r).loc['2024-02-02'] == pytest.approx(1.0, abs=1e-9)
    assert _ganancia(r).iloc[-1] == pytest.approx(20.0, abs=0.01)
    assert r['capital_gains']['unrealized']['shares'] == pytest.approx(1.0, abs=1e-9)


def test_la_fraccion_sale_en_proporcion_de_lo_comprado_y_lo_reinvertido(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA_10_5,
        dict(Date='2024-01-10', Action='Reinvest Dividend', Amount=105.0),
        dict(Date='2024-01-10', Action='Reinvest Shares', Quantity=3.5, Amount=-105.0),
        dict(Date='2024-01-31', Action='Cash In Lieu', Amount=10.0),
    ], CIERRES_SIN_AJUSTAR, splits=SPLIT_3X1)
    assert r['shares_owned'] == pytest.approx(41.0, abs=1e-9)
    assert r['shares_owned_pocket'] == pytest.approx(30.75, abs=1e-9)
    assert r['shares_owned_drip'] == pytest.approx(10.25, abs=1e-9)
    assert r['net_profit'] == pytest.approx(41 * 12.0 + 10.0 - 315.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(187.0, abs=0.01)


def test_pago_de_fraccion_lejos_de_cualquier_split_no_toca_las_acciones(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA_10_5, dict(Date='2024-01-18', Action='Cash In Lieu', Amount=5.0),
    ], CIERRES_AJUSTADOS, splits=SPLIT_3X1)
    assert r['shares_owned'] == pytest.approx(31.5, abs=1e-9)
    assert r['net_profit'] == pytest.approx(31.5 * 12.0 + 5.0 - 315.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(68.0, abs=0.01)


def test_pago_de_fraccion_a_diez_dias_del_split_si_cuenta(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA_10_5, dict(Date='2024-01-22', Action='Cash In Lieu', Amount=5.0),
    ], CIERRES_AJUSTADOS, splits=SPLIT_3X1)
    assert r['shares_owned'] == pytest.approx(31.0, abs=1e-9)


def test_cargo_rotulado_como_fraccion_no_suma_acciones(monkeypatch):
    r = _analizar(monkeypatch, [
        COMPRA_10_5, dict(Date='2024-01-31', Action='Cash In Lieu', Amount=-5.0),
    ], CIERRES_AJUSTADOS, splits=SPLIT_3X1)
    assert r['shares_owned'] == pytest.approx(31.5, abs=1e-9)
    assert r['net_profit'] == pytest.approx(31.5 * 12.0 - 5.0 - 315.0, abs=0.01)


def test_pago_de_fraccion_mayor_que_la_posicion_la_deja_en_cero(monkeypatch):
    r = _analizar(monkeypatch, [
        dict(Date='2024-01-02', Action='Buy', Quantity=0.1, Amount=-3.0),
        dict(Date='2024-01-31', Action='Cash In Lieu', Amount=5.0),
    ], CIERRES_AJUSTADOS, splits=SPLIT_3X1)
    assert r['shares_owned'] == pytest.approx(0.0, abs=1e-9)
    assert r['net_profit'] == pytest.approx(2.0, abs=0.01)
    assert _ganancia(r).iloc[-1] == pytest.approx(2.0, abs=0.01)


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
