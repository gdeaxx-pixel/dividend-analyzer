"""Huecos de la referencia congelada de `analyze_portfolio` (R3, C6, PD).

Cada test lleva su mutante: rojo con él, verde con `logic.py` intacto. Los esperados están
escritos a mano a partir de datos sintéticos; ninguno repite el umbral que vigila.
"""
import numpy as np
import pandas as pd
import pytest

import logic


def _historial_riesgo(n_filas):
    retornos_voo = [0.010, -0.005, 0.008, -0.012, 0.006, 0.004, -0.007, 0.009, -0.003, 0.002]
    retornos_voo = (retornos_voo * 2)[:n_filas - 1]
    voo = [100.0]
    twr = [0.0]
    for r in retornos_voo:
        voo.append(voo[-1] * (1 + r))
        twr.append(((1 + twr[-1] / 100) * (1 + 1.4 * r) - 1) * 100)
    idx = pd.date_range('2024-03-04', periods=n_filas, freq='B')
    return pd.DataFrame({
        'User Return %': twr,
        'VOO Price': voo,
        'VOO Div': 0.0,
        'SPY Profit': 0.0,
    }, index=idx)


def test_r3_beta_y_alpha_existen_con_diez_retornos_alineados():
    """11 filas -> 10 retornos alineados: justo en el borde, beta y alpha se calculan."""
    out = logic._metricas_riesgo(_historial_riesgo(11))
    beta, alpha = out[5], out[6]
    assert beta is not None and np.isfinite(beta)
    assert alpha is not None and np.isfinite(alpha)


def test_r3_beta_y_alpha_son_none_con_nueve_retornos_alineados():
    """10 filas -> 9 retornos alineados: por debajo del borde no hay beta ni alpha."""
    out = logic._metricas_riesgo(_historial_riesgo(10))
    assert out[5] is None
    assert out[6] is None


def test_twr_invalido_a_mitad_de_serie_cuenta_como_dia_sin_movimiento():
    """Un día con TWR de -100 % (factor 0 -> NaN) toma el valor del día anterior: retorno 0 ese
    día, y el siguiente se mide contra el último válido. Con todos los demás días en +1 %, eso
    da una volatilidad de ~6 %. Sin el relleno (lo que hace pandas 3 por defecto) se pierden
    esos dos retornos, quedan solo días de +1 % y la volatilidad cae a ~0.
    Mutante: `twr_factor.pct_change(fill_method=None)` sin el `ffill()`."""
    twr = [0.0]
    for _ in range(11):
        twr.append(((1 + twr[-1] / 100) * 1.01 - 1) * 100)
    twr[6] = -100.0
    idx = pd.date_range('2024-03-04', periods=len(twr), freq='B')
    historial = pd.DataFrame({
        'User Return %': twr,
        'VOO Price': 100.0,
        'VOO Div': 0.0,
        'SPY Profit': 0.0,
    }, index=idx)
    volatilidad = logic._metricas_riesgo(historial)[0]
    assert volatilidad is not None and volatilidad > 1.0


def _filas_impuesto():
    return pd.DataFrame([{
        'Date': pd.Timestamp('2024-09-10'),
        'Action': 'NRA Tax Adj',
        'Ticker': 'MSTY',
        'Quantity': 0,
        'Amount': -30.0,
    }])


def test_c6_el_predicado_de_impuesto_se_resuelve_en_cada_llamada(monkeypatch):
    """Una fila 'NRA Tax Adj' hoy entra al cronograma de IRR como flujo de impuesto. Si el
    predicado se desactiva por el nombre del módulo, el flujo desaparece: eso solo ocurre si
    `_recorrer_transacciones` lo busca en `logic` en cada llamada y no lo captura al definirse."""
    intacto = logic._recorrer_transacciones(_filas_impuesto().copy(), pd.Series(dtype=float))
    assert intacto['irr_flows_dated'] == [(pd.Timestamp('2024-09-10'), -30.0)]

    monkeypatch.setattr(logic, '_is_tax_row_action', lambda action: False)
    parcheado = logic._recorrer_transacciones(_filas_impuesto().copy(), pd.Series(dtype=float))
    assert parcheado['irr_flows_dated'] == []


def _mercado_pd(t, d):
    idx = pd.to_datetime(['2024-09-02', '2024-09-03', '2024-09-04', '2024-10-15'])
    return pd.DataFrame({'Close': [17.0, 18.2, 25.0, 20.0],
                         'Dividends': 0.0, 'Stock Splits': 0.0}, index=idx), None


def _compras_pd():
    return pd.DataFrame([
        {'Date': pd.Timestamp(d), 'Action': 'Buy', 'Ticker': 'MSTY', 'Quantity': q, 'Amount': a}
        for d, q, a in [('2024-09-02', 100, -2000.0),
                        ('2024-09-03', 10, -200.0),
                        ('2024-09-04', 10, -200.0)]])


def test_pd_discrepancias_de_precio_csv_vs_yfinance(monkeypatch):
    """Tres compras a $20 del CSV contra cierres de 17.0 (ratio ~1.18, sobre el umbral),
    18.2 (ratio ~1.10, dentro de tolerancia) y 25.0 (ratio 0.80, bajo el umbral inferior)."""
    monkeypatch.setattr(logic, 'fetch_market_data', _mercado_pd)
    monkeypatch.setattr(logic, '_descargar_benchmark', lambda df, *a, **k: pd.DataFrame())
    res = logic.analyze_portfolio(_compras_pd(), version='TEST_PD_HUECO')
    assert res['MSTY']['price_discrepancies'] == [
        {'date': '2024-09-02', 'csv_price': 20.0, 'yf_price': 17.0, 'ratio': 1.18},
        {'date': '2024-09-04', 'csv_price': 20.0, 'yf_price': 25.0, 'ratio': 0.8},
    ]
