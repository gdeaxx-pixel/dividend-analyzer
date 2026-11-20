"""CAP-1 y PROM-1: ningún texto libre viaja en la copia; promote_case valida sus argumentos."""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(__file__))
import logic
import promote_case

BASE = os.path.dirname(__file__)


def _generico():
    return pd.DataFrame({
        'Date': ['2025-01-15', '2025-02-10', '2025-03-03', '2025-03-04', '2025-04-01'],
        'Action': ['Compra', 'JUAN PEREZ RETIRO CTA 12345678', 'Dividendo',
                   'Transferencia a MARIA GOMEZ', 'Compra'],
        'Ticker': ['XYZQ', 'XYZQ', 'XYZQ', 'JUAN PEREZ', 'ABCD'],
        'Quantity': [10.0, 0, 0, 0, 5.0],
        'Price': [25.01, 0, 0, 0, 30.5],
        'Amount': [-253.17, -1500.0, 12.34, -980.11, -152.5],
    })


def test_cap1_ningun_texto_libre_en_el_csv():
    csv = logic.anonymize_to_min_rows(_generico()).to_csv(index=False)
    for needle in ('JUAN', 'PEREZ', 'MARIA', 'GOMEZ', '12345678'):
        assert needle not in csv


def test_cap1_en_el_bundle_completo():
    b = logic.build_capture_bundle(_generico(), 'generic', {}, {})
    assert 'JUAN' not in b['transactions_min_csv'] and '12345678' not in b['transactions_min_csv']


def test_cap1_action_y_ticker_cerrados():
    mn = logic.anonymize_to_min_rows(_generico())
    assert list(mn['Action']) == ['Buy', 'OTRO', 'Dividend', 'Journal', 'Buy']
    assert list(mn['Ticker']) == ['XYZQ', 'XYZQ', 'XYZQ', 'OTRO', 'ABCD']


def test_cap1_acciones_del_broker_se_conservan():
    conocidas = ['Buy', 'Sell', 'NRA Tax Adj', 'Reinvest Shares', 'Dividend - Foreign Tax Withholding',
                 'Qualified Dividend', 'MoneyLink Transfer', 'Cash In Lieu']
    df = pd.DataFrame({'Date': ['2025-01-01'] * len(conocidas), 'Action': conocidas,
                       'Ticker': ['A'] * len(conocidas), 'Quantity': [1.0] * len(conocidas),
                       'Price': [1.0] * len(conocidas), 'Amount': [1.0] * len(conocidas)})
    assert list(logic.anonymize_to_min_rows(df)['Action']) == conocidas


def test_cap1_ticker_vacio_sigue_vacio():
    df = _generico()
    df.loc[0, 'Ticker'] = None
    assert logic.anonymize_to_min_rows(df)['Ticker'].iloc[0] == ''


def test_cap1_fidelidad_mismas_cifras_original_y_copia():
    df = pd.DataFrame({
        'Date': ['2025-01-15', '2025-02-10', '2025-03-03', '2025-03-04', '2025-03-04', '2025-05-01'],
        'Action': ['Compra de acciones', 'Venta parcial', 'Dividendo en efectivo',
                   'Retención de impuesto NRA', 'Reinversión de dividendos', 'Depósito de fondos'],
        'Ticker': ['XYZQ'] * 6,
        'Quantity': [10.0, -2.0, 0, 0, 0.3, 0],
        'Price': [25.0, 27.0, 0, 0, 25.0, 0],
        'Amount': [-250.0, 54.0, 20.0, -6.0, -7.5, 500.0],
    })
    copia = logic.anonymize_to_min_rows(df)
    copia['Date'] = pd.to_datetime(copia['Date'])
    assert logic.build_dividend_tax_totals(copia) == logic.build_dividend_tax_totals(df)
    assert logic.withheld_tax_total(copia) == logic.withheld_tax_total(df)
    for orig, cop in zip(df['Action'], copia['Action']):
        assert logic._is_tax_row_action(orig) == logic._is_tax_row_action(cop)
        o, c = orig.lower(), cop.lower()
        for kw in ('buy|compra', 'sell|venta', 'reinvest|reinversión', 'dividend|dividendo'):
            assert any(k in o for k in kw.split('|')) == any(k in c for k in kw.split('|')), (orig, cop)


SCHWAB_FUERA_DE_LA_LISTA = ['Bond Interest', 'Internal Transfer', 'MoneyLink Deposit', 'MoneyLink Adj',
                            'Pr Yr Div Reinvest']


def _filas(acciones, importes=None):
    n = len(acciones)
    return pd.DataFrame({'Date': ['2025-01-15'] * n, 'Action': acciones, 'Ticker': ['XYZQ'] * n,
                         'Quantity': [0.0] * n, 'Price': [0.0] * n,
                         'Amount': importes or [1.0] * n})


@pytest.mark.parametrize('broker', ['schwab', 'ibkr'])
def test_cap1_el_action_propio_del_broker_no_se_reescribe(broker):
    mn = logic.anonymize_to_min_rows(_filas(SCHWAB_FUERA_DE_LA_LISTA), broker)
    assert list(mn['Action']) == SCHWAB_FUERA_DE_LA_LISTA


@pytest.mark.parametrize('broker', [None, 'generic', 'normalized', 'otro'])
def test_cap1_sin_broker_conocido_el_vocabulario_es_cerrado(broker):
    mn = logic.anonymize_to_min_rows(_filas(['JUAN PEREZ RETIRO', 'Bond Interest', 'Buy']), broker)
    assert list(mn['Action']) == ['OTRO', 'Credit Interest', 'Buy']


def test_cap1_ni_con_broker_conocido_viaja_un_numero_largo():
    mn = logic.anonymize_to_min_rows(_filas(['RETIRO CTA 12345678', 'Buy', 'Bond Interest']), 'schwab')
    assert list(mn['Action']) == ['OTRO', 'Buy', 'Bond Interest']


def test_cap1_el_bundle_le_pasa_el_broker_a_la_copia():
    df = _filas(['Bond Interest', 'JUAN PEREZ RETIRO'])
    assert 'Bond Interest' in logic.build_capture_bundle(df, 'schwab', {}, {})['transactions_min_csv']
    generico = logic.build_capture_bundle(df, 'generic', {}, {})['transactions_min_csv']
    assert 'Bond Interest' not in generico and 'JUAN' not in generico


def test_cap1_un_interes_no_se_vuelve_dividendo():
    df = _filas(['Dividendo en efectivo', 'Interest on cash', 'Retención de impuesto NRA'], [20.0, 5.0, -6.0])
    copia = logic.anonymize_to_min_rows(df)
    assert list(copia['Action']) == ['Dividend', 'Credit Interest', 'NRA Tax Adj']
    copia['Date'] = pd.to_datetime(copia['Date'])
    assert logic.build_dividend_tax_totals(copia) == logic.build_dividend_tax_totals(df)


@pytest.mark.parametrize('malo', ['..', '../x', 'a/b', '', 'a b', 'a\\b', '.'])
def test_prom1_rechaza_argumentos_invalidos(monkeypatch, malo):
    llamadas = []
    monkeypatch.setattr(promote_case.storage, 'fetch_case', lambda *a: llamadas.append(a) or {})
    with pytest.raises(ValueError):
        promote_case.promote(malo, 'abc123')
    with pytest.raises(ValueError):
        promote_case.promote('schwab', malo)
    with pytest.raises(ValueError):
        promote_case.show(malo, 'abc123')
    assert llamadas == []


def test_prom1_acepta_argumentos_validos(monkeypatch):
    monkeypatch.setattr(promote_case.storage, 'fetch_case', lambda *a: None)
    assert promote_case.show('schwab', 'ab12_CD-3') is None
