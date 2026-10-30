"""Módulo 1 de `analyze_portfolio`: solo se piden datos del subyacente cuando es un ticker.

YMAX, ULTY y LFGY siguen una cartera ('Multi') e YMAG a las siete grandes ('Mag-7'). Antes se
pedían a Yahoo como si fueran tickers y volvían vacíos tras 2 a 6 s por fondo (medido
2026-10-29). Mutantes medidos con `/auditoria-m4` el mismo día, sobre la suite completa:
- el Módulo 1 con la exclusión vieja (`str(u).upper() not in ('N/A', 'NA', '')`) pone
  rojo al primero;
- la frase de exposición con esa misma exclusión, al segundo;
- la regla con tickers de 1 a 4 letras (GOOY pierde GOOGL), al tercero;
- la regla que pasa el valor a mayúsculas antes de mirarlo ('Multi' -> 'MULTI'), a los tres.
"""
import pandas as pd

import estres_2022
import logic

_FICHAS = {'YMAX': 'Multi', 'YMAG': 'Mag-7', 'ULTY': 'Multi', 'LFGY': 'Multi', 'TSLY': 'TSLA'}


def _compras():
    return pd.DataFrame([
        {'Date': pd.Timestamp('2025-01-02'), 'Action': 'Buy', 'Ticker': t, 'Quantity': 10,
         'Amount': -200.0}
        for t in _FICHAS])


def test_m1_no_pide_a_yahoo_un_subyacente_que_no_es_ticker(monkeypatch):
    fichas = logic.load_instruments()
    assert {t: fichas[t]['underlying'] for t in _FICHAS} == _FICHAS

    pedidos = []
    idx = pd.bdate_range('2024-12-20', '2026-10-23')
    conocidos = {*_FICHAS, 'TSLA'}

    def _mercado(ticker, start_date):
        """Como Yahoo: serie para los tickers que existen, vacío con motivo para el resto."""
        pedidos.append(ticker)
        if ticker not in conocidos:
            return pd.DataFrame(), f'{ticker}: sin datos'
        return pd.DataFrame({'Close': 20.0, 'Dividends': 0.0, 'Stock Splits': 0.0},
                            index=idx), None

    monkeypatch.setattr(logic, 'fetch_market_data', _mercado)
    monkeypatch.setattr(logic, '_descargar_benchmark', lambda df, *a, **k: pd.DataFrame())
    res = logic.analyze_portfolio(_compras(), version='TEST_M1_SUBYACENTE_TICKER')

    assert 'MULTI' not in pedidos and 'MAG-7' not in pedidos, pedidos
    assert sorted(pedidos) == sorted([*_FICHAS, 'TSLA'])
    for fondo in ('YMAX', 'YMAG', 'ULTY', 'LFGY'):
        assert res[fondo]['underlying_ticker'] is None
    assert res['TSLY']['underlying_ticker'] == 'TSLA'
    assert res['TSLY']['underlying_hold_value'] is not None


def test_la_exposicion_al_subyacente_calla_si_no_es_un_ticker():
    """Con la regla vieja, YMAX decía «YMAX sigue a MULTI» y «vende opciones sobre MULTI»."""
    for fondo in ('YMAX', 'YMAG', 'ULTY', 'LFGY'):
        assert logic.build_underlying_exposure({fondo: {}}, fondo)['lines'] == []
    lineas = logic.build_underlying_exposure({'TSLY': {}}, 'TSLY')['lines']
    assert lineas[0].startswith('TSLY sigue a TSLA')


def test_m1_y_riesgo_coinciden_en_que_fondos_tienen_un_ticker_de_subyacente():
    """Las dos reglas son independientes (una vive en `logic`, la otra en `estres_2022`)
    y tienen que dar el mismo conjunto sobre las fichas reales."""
    fichas = logic.load_instruments()
    m1 = {t: logic._subyacente_ticker(p.get('underlying')) for t, p in fichas.items()
          if p.get('type') == 'yieldmax'}
    assert {t: u for t, u in m1.items() if u} == estres_2022.subyacentes_yieldmax(fichas)
