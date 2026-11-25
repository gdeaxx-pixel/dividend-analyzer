"""Riesgo acota solo los días en que el archivo mueve algo (auditoría S11, M9).

Un día sin operación ni pago rinde lo que rindió el precio y no se recorta: una caída de
mercado es el dato. Los días con operación, traspaso, pago o split siguen acotados al rango
[1 %, 99 %] de la serie, porque ahí un salto puede ser contabilidad y no rendimiento.
Todo sintético; los esperados se calculan aparte con numpy, no con la función vigilada.
"""
import numpy as np
import pandas as pd
import pytest

import logic
import metricas
from test_serie_diaria_coherencia import COMPRA, POSICIONES, _analizar, _analizar_fixture


def _ruido(n, semilla=7, media=0.0004, desv=0.008):
    return np.random.default_rng(semilla).normal(media, desv, n)


def _con_caida(n=249):
    r = _ruido(n)
    r[100], r[101], r[102] = -0.12, -0.10, -0.08
    return r


def _caida_maxima(r):
    w = np.r_[1.0, np.cumprod(1.0 + np.asarray(r, dtype=float))]
    return float((w / np.maximum.accumulate(w) - 1.0).min() * 100.0)


def _historia(r, eventos=(), voo=None, sin_columna=False):
    idx = pd.bdate_range('2023-01-02', periods=len(r) + 1)
    twr = (np.cumprod(np.r_[1.0, 1.0 + np.asarray(r, dtype=float)]) - 1.0) * 100.0
    h = pd.DataFrame({'User Return %': twr, 'VOO Price': 100.0, 'VOO Div': 0.0,
                      'SPY Profit': 0.0}, index=idx)
    if voo is not None:
        h['VOO Price'] = 100.0 * np.cumprod(np.r_[1.0, 1.0 + np.asarray(voo, dtype=float)])
    if not sin_columna:
        marca = pd.Series(False, index=idx)
        marca.iloc[[i + 1 for i in eventos]] = True
        h['Dia Con Evento'] = marca
    return h


# ── 1. `_winsorize_returns(solo=…)` ─────────────────────────────────────────────────────

def test_sin_dias_marcados_no_se_recorta_nada():
    r = pd.Series(_con_caida())
    salida = metricas._winsorize_returns(r, solo=pd.Series(False, index=r.index))
    assert salida.tolist() == r.tolist()


def test_solo_se_acota_el_dia_marcado_y_con_los_limites_de_toda_la_serie():
    crudo = _con_caida()
    crudo[50] = 68.43
    crudo[60] = -0.95
    r = pd.Series(crudo)
    marca = pd.Series(False, index=r.index)
    marca.iloc[[50, 60]] = True
    salida = metricas._winsorize_returns(r, solo=marca)
    lo, hi = np.quantile(crudo, 0.01), np.quantile(crudo, 0.99)
    assert salida.iloc[50] == pytest.approx(hi, abs=1e-12)
    assert salida.iloc[60] == pytest.approx(lo, abs=1e-12)
    assert salida.iloc[[100, 101, 102]].tolist() == [-0.12, -0.10, -0.08]
    resto = [i for i in range(len(r)) if i not in (50, 60)]
    assert salida.iloc[resto].tolist() == r.iloc[resto].tolist()


def test_un_dia_marcado_dentro_del_rango_no_cambia():
    r = pd.Series(_con_caida())
    marca = pd.Series(False, index=r.index)
    marca.iloc[10] = True
    assert metricas._winsorize_returns(r, solo=marca).tolist() == r.tolist()


def test_la_marca_que_no_cubre_un_dia_cuenta_como_sin_marcar():
    crudo = _con_caida()
    crudo[50] = 68.43
    r = pd.Series(crudo)
    marca = pd.Series([True], index=[60])
    assert metricas._winsorize_returns(r, solo=marca).iloc[50] == 68.43


def test_una_serie_corta_no_se_acota_aunque_tenga_dia_marcado():
    r = pd.Series([0.01, -0.02, 0.03, 68.0])
    marca = pd.Series([False, False, False, True])
    assert metricas._winsorize_returns(r, solo=marca).tolist() == r.tolist()


def test_sin_marca_se_acota_la_serie_entera_como_antes():
    crudo = _con_caida()
    r = pd.Series(crudo)
    salida = metricas._winsorize_returns(r)
    assert salida.min() == pytest.approx(np.quantile(crudo, 0.01), abs=1e-12)
    assert salida.iloc[100] > -0.12


# ── 2. `_metricas_riesgo` ───────────────────────────────────────────────────────────────

def test_la_caida_de_tres_dias_sin_operaciones_sale_entera():
    r = _con_caida()
    vol, _sh, _so, caida, _cal, _b, _a = logic._metricas_riesgo(_historia(r))
    assert _caida_maxima(r) == pytest.approx(-40.49, abs=0.01)
    assert caida == pytest.approx(_caida_maxima(r), abs=1e-6)
    assert vol == pytest.approx(float(np.std(r, ddof=1) * np.sqrt(252) * 100), abs=1e-6)


def test_la_serie_de_caida_que_se_dibuja_llega_al_mismo_minimo():
    r = _con_caida()
    h = _historia(r)
    logic._metricas_riesgo(h)
    assert float(h['Drawdown %'].min()) == pytest.approx(_caida_maxima(r), abs=1e-6)


def test_calmar_usa_el_retorno_sin_recortar():
    r = _con_caida()
    _v, _sh, _so, caida, calmar, _b, _a = logic._metricas_riesgo(_historia(r))
    cagr = (float(np.prod(1.0 + r)) ** (252 / len(r)) - 1.0) * 100.0
    assert calmar == pytest.approx(cagr / abs(_caida_maxima(r)), abs=1e-6)


def test_un_salto_en_dia_con_evento_sigue_acotado():
    r = _con_caida()
    r[50] = 68.43
    vol, *_ = logic._metricas_riesgo(_historia(r, eventos=[50]))
    acotado = r.copy()
    acotado[50] = np.quantile(r, 0.99)
    assert vol == pytest.approx(float(np.std(acotado, ddof=1) * np.sqrt(252) * 100), abs=1e-6)
    assert vol < 30


def test_el_mismo_salto_en_dia_sin_evento_no_se_toca():
    r = _con_caida()
    r[50] = 0.26
    vol, *_ = logic._metricas_riesgo(_historia(r))
    assert vol == pytest.approx(float(np.std(r, ddof=1) * np.sqrt(252) * 100), abs=1e-6)


def test_el_indice_por_precio_no_se_acota():
    voo = _con_caida()
    _v, _sh, _so, _dd, _cal, beta, _a = logic._metricas_riesgo(_historia(2.0 * voo, voo=voo))
    assert beta == pytest.approx(2.0, abs=1e-9)


def test_el_respaldo_del_indice_se_sigue_acotando_entero():
    r = _con_caida()
    h = _historia(r).drop(columns=['VOO Price', 'VOO Div'])
    ref = _ruido(len(r), semilla=11)
    ref[40] = 49.0
    h['SPY Profit'] = 1000.0 * np.cumprod(np.r_[1.0, 1.0 + ref])
    _v, _sh, _so, _dd, _cal, beta, _a = logic._metricas_riesgo(h)
    acotado = np.clip(ref, np.quantile(ref, 0.01), np.quantile(ref, 0.99))
    esperado = float(np.cov(r, acotado, ddof=1)[0, 1] / np.var(acotado, ddof=1))
    assert beta == pytest.approx(esperado, abs=1e-9)


def test_una_serie_sin_la_marca_se_acota_entera_como_antes():
    r = _con_caida()
    lo, hi = np.quantile(r, 0.01), np.quantile(r, 0.99)
    acotada = _caida_maxima(np.clip(r, lo, hi))
    _vol, _sh, _so, caida, _cal, _b, _a = logic._metricas_riesgo(_historia(r, sin_columna=True))
    assert caida == pytest.approx(acotada, abs=1e-6)
    assert acotada > _caida_maxima(r) + 5


# ── 3. Qué días marca la serie ──────────────────────────────────────────────────────────

def _serie(acciones, flujo=None, pago=None):
    idx = pd.bdate_range('2024-01-02', periods=len(acciones))
    cero = [0.0] * len(acciones)
    return pd.DataFrame({'Shares Held': acciones, 'Flujo Efectivo': flujo or cero,
                         'Daily Cash Div': pago or cero}, index=idx)


def _marcados(h, splits=None, reinicios=()):
    s = pd.Series(0.0, index=h.index)
    for i, factor in (splits or {}).items():
        s.iloc[i] = factor
    reinicios = {h.index[i]: (0.0, 0.0) for i in reinicios}
    return [i for i, v in enumerate(logic._dias_con_evento(h, s, reinicios)) if v]


def test_un_dia_quieto_no_se_marca():
    assert _marcados(_serie([10.0] * 6, flujo=[1000.0] + [0.0] * 5)) == [0]


def test_el_dia_que_cambian_las_acciones_se_marca():
    assert _marcados(_serie([10.0, 10.0, 12.5, 12.5, 4.0, 4.0])) == [2, 4]


def test_el_dia_que_entra_o_sale_dinero_se_marca():
    assert _marcados(_serie([10.0] * 5, flujo=[0.0, 0.0, 300.0, 0.0, -50.0])) == [2, 4]


def test_el_dia_que_se_cobra_un_pago_se_marca():
    assert _marcados(_serie([10.0] * 5, pago=[0.0, 0.0, 0.0, -7.5, 0.0])) == [3]


def test_la_sesion_del_split_se_marca():
    assert _marcados(_serie([10.0] * 6), splits={3: 0.2}) == [3]


def test_de_la_fila_de_split_al_split_del_mercado_se_marca_todo():
    assert _marcados(_serie([10.0] * 9), splits={5: 0.2}, reinicios=[2]) == [2, 3, 4, 5]


def test_fila_de_split_sin_split_cercano_en_el_mercado_marca_solo_su_dia():
    assert _marcados(_serie([10.0] * 12), splits={10: 0.2}, reinicios=[2]) == [2, 10]


def test_el_tramo_llega_hasta_un_split_a_cinco_sesiones_y_no_a_seis():
    assert _marcados(_serie([10.0] * 12), splits={7: 0.2}, reinicios=[2]) == [2, 3, 4, 5, 6, 7]
    assert _marcados(_serie([10.0] * 12), splits={8: 0.2}, reinicios=[2]) == [2, 8]


def test_fila_de_split_y_split_la_misma_sesion_marcan_un_solo_dia():
    assert _marcados(_serie([10.0] * 8), splits={2: 0.2}, reinicios=[2]) == [2]


# ── 4. La cadena completa ───────────────────────────────────────────────────────────────

def _cierres_con_caida(n=120):
    r = _ruido(n - 1, semilla=3)
    r[60], r[61], r[62] = -0.12, -0.10, -0.08
    return list(100.0 * np.cumprod(np.r_[1.0, 1.0 + r])), r


def test_cadena_la_caida_del_precio_llega_entera_a_riesgo(monkeypatch):
    cierres, r = _cierres_con_caida()
    res = _analizar(monkeypatch, [COMPRA], cierres)
    assert res['max_drawdown'] == pytest.approx(_caida_maxima(r), abs=1e-6)
    assert res['volatilidad_anualizada'] == pytest.approx(
        float(np.std(r, ddof=1) * np.sqrt(252) * 100), abs=1e-6)
    assert float(res['daily_trend']['Drawdown %'].min()) == pytest.approx(_caida_maxima(r), abs=1e-6)


def test_cadena_acciones_que_entran_sin_dinero_no_disparan_la_volatilidad(monkeypatch):
    cierres, r = _cierres_con_caida()
    filas = [dict(Date='2024-01-02', Action='Buy', Quantity=1, Amount=-100.0),
             dict(Date='2024-02-01', Action='Reinvest Shares', Quantity=40, Amount=0.0)]
    res = _analizar(monkeypatch, filas, cierres)
    dia = pd.bdate_range('2024-01-02', periods=len(cierres)).get_loc(pd.Timestamp('2024-02-01'))
    crudo = r.copy()
    crudo[dia - 1] = 41.0 * cierres[dia] / cierres[dia - 1] - 1.0
    acotado = crudo.copy()
    acotado[dia - 1] = np.quantile(crudo, 0.99)
    assert crudo[dia - 1] > 30
    assert res['volatilidad_anualizada'] == pytest.approx(
        float(np.std(acotado, ddof=1) * np.sqrt(252) * 100), abs=1e-6)
    assert res['max_drawdown'] == pytest.approx(_caida_maxima(acotado), abs=1e-6)


def test_cadena_un_traspaso_de_acciones_marca_su_dia(monkeypatch):
    vistas = []
    real = logic._metricas_riesgo
    monkeypatch.setattr(logic, '_metricas_riesgo', lambda h: (vistas.append(h.copy()), real(h))[1])
    filas = [COMPRA, dict(Date='2024-02-01', Action='Internal Transfer', Quantity=20, Amount=0.0),
             dict(Date='2024-03-01', Action='Cash Dividend', Quantity=0, Amount=12.0)]
    _analizar(monkeypatch, filas, [100.0] * 60)
    marca = vistas[0]['Dia Con Evento']
    assert [d.strftime('%Y-%m-%d') for d in marca.index[marca]] == [
        '2024-01-02', '2024-02-01', '2024-03-01']


@pytest.mark.parametrize('fixture', sorted(POSICIONES))
def test_en_un_dia_sin_evento_el_retorno_es_el_del_precio(monkeypatch, fixture):
    vistas = []
    real = logic._metricas_riesgo
    monkeypatch.setattr(logic, '_metricas_riesgo', lambda h: (vistas.append(h.copy()), real(h))[1])
    _analizar_fixture(monkeypatch, fixture)
    assert len(vistas) == len(POSICIONES[fixture])
    comparados = 0
    for h in vistas:
        factor = (1 + h['User Return %'] / 100).replace(0, np.nan)
        r = factor.ffill().pct_change(fill_method=None)
        precio = h['Price'].pct_change(fill_method=None)
        con_posicion = h['Market Value'].shift(1) > 0.0001
        quieto = ~h['Dia Con Evento'] & r.notna() & con_posicion
        assert h['Dia Con Evento'].any()
        assert float((r - precio)[quieto].abs().max()) < 1e-9
        assert float(r[~h['Dia Con Evento'] & r.notna() & ~con_posicion].abs().sum()) == 0.0
        comparados += int(quieto.sum())
    assert comparados > 100
