"""Compra y venta el mismo día, y el tramo de 2 años cuando hay compras a ambos lados.

Un CSV con fecha sin hora no dice qué pasó primero: se cuenta siempre la compra primero, venga
en el orden que venga. Y el tramo sale del día promedio de la posición, así que con compras de
antes y de después del corte la venta cae entera en un tramo: se marca como aproximada.
"""
import copy

import pandas as pd
import pytest

import logic
from ui import adapters


def _df(filas):
    return pd.DataFrame(filas, columns=['Date', 'Action', 'Symbol', 'Quantity', 'Price', 'Amount'])


PREVIA = ('2024-01-10', 'Buy', 'AAA', 100, 10.00, -1000.00)
COMPRA = ('2024-06-03', 'Buy', 'AAA', 100, 20.00, -2000.00)


def _venta(cantidad, importe, fecha='2024-06-03'):
    return (fecha, 'Sell', 'AAA', cantidad, importe / cantidad, importe)


@pytest.mark.parametrize('orden', ['venta_antes', 'venta_despues', 'archivo_al_reves'])
def test_la_compra_del_mismo_dia_cuenta_antes_que_la_venta(orden):
    """100 a $10 y, el mismo día de la venta, 100 a $20: promedio $15. Vender 50 se lleva
    $750 de base en cualquier orden de filas; con la venta primero saldrían $500."""
    venta = _venta(50, 900.00)
    filas = {'venta_antes': [PREVIA, venta, COMPRA],
             'venta_despues': [PREVIA, COMPRA, venta],
             'archivo_al_reves': [venta, COMPRA, PREVIA]}[orden]
    df = _df(filas)
    if orden == 'archivo_al_reves':
        df = df.sort_values('Date', kind='stable')
    cg = logic.build_capital_gains(df, 'AAA')
    assert cg['estado'] == 'ok', cg['motivo']
    r = cg['realized'][0]
    assert r['basis'] == pytest.approx(750.00, abs=0.005)
    assert r['gain'] == pytest.approx(150.00, abs=0.005)
    assert cg['unrealized']['shares'] == pytest.approx(150.0)
    assert cg['unrealized']['basis'] == pytest.approx(2250.00, abs=0.005)


def test_vender_mas_de_lo_que_habia_antes_de_la_compra_del_dia_no_queda_indeterminado():
    df = _df([PREVIA, _venta(150, 1800.00), COMPRA])
    cg = logic.build_capital_gains(df, 'AAA')
    assert cg['estado'] == 'ok', cg['motivo']
    assert cg['realized'][0]['basis'] == pytest.approx(2250.00, abs=0.005)
    assert cg['realized'][0]['gain'] == pytest.approx(-450.00, abs=0.005)


def test_con_hora_en_la_fecha_se_respeta_el_orden_real():
    """Si el archivo dice que la venta fue a las 10 y la compra a las 15, no se reordena."""
    df = _df([
        (pd.Timestamp('2024-01-10 10:00'), 'Buy', 'AAA', 100, 10.00, -1000.00),
        (pd.Timestamp('2024-06-03 10:00'), 'Sell', 'AAA', 50, 18.00, 900.00),
        (pd.Timestamp('2024-06-03 15:00'), 'Buy', 'AAA', 100, 20.00, -2000.00),
    ])
    cg = logic.build_capital_gains(df, 'AAA')
    assert cg['realized'][0]['basis'] == pytest.approx(500.00, abs=0.005)


def test_solo_se_mueven_las_ventas_y_solo_dentro_de_su_fecha():
    df = _df([
        ('2024-06-03', 'Sell', 'AAA', 1, 1.0, 1.0),
        ('2024-06-03', 'Qualified Dividend', 'AAA', 0, 0.0, 5.0),
        ('2024-06-03', 'Buy', 'AAA', 1, 1.0, -1.0),
        ('2024-06-04', 'Sell', 'AAA', 1, 1.0, 1.0),
        ('2024-06-04', 'Reinvest Shares', 'AAA', 1, 1.0, -1.0),
        ('2024-06-05', 'Buy', 'AAA', 1, 1.0, -1.0),
    ])
    df.index = [40, 30, 20, 10, 5, 1]
    fuera = logic._compras_antes_que_ventas(df)
    assert list(fuera.index) == [30, 20, 40, 5, 10, 1]
    assert fuera.loc[40].equals(df.loc[40])
    ya_ordenado = df.loc[[30, 20, 40, 5, 10, 1]]
    assert logic._compras_antes_que_ventas(ya_ordenado) is ya_ordenado


@pytest.mark.parametrize('accion', [
    'Sell', 'Sold', 'Venta', 'Buy', 'Bought', 'Compra', 'Reinvest Shares', 'Reinvest Dividend',
    'Journaled Shares', 'Internal Transfer', 'Deposit', 'Qualified Dividend', 'Sell to Cover',
    'Transfer Sold Shares', 'NRA Tax Adj', 'Stock Split',
])
def test_lo_que_se_manda_al_final_es_lo_que_el_recorrido_trata_como_venta(accion):
    """El ordenador y el recorrido deciden «venta» por separado: aquí se comparan. Una fila es
    venta para el recorrido si deja una entrada en `realized`."""
    df = _df([PREVIA, ('2024-06-03', accion, 'AAA', 10, 12.00, 120.00)])
    cg = logic.build_capital_gains(df, 'AAA')
    assert logic._es_venta_de_capital(accion) == (len(cg['realized']) == 1), accion


# ── Tramo aproximado ─────────────────────────────────────────────────────────────────

VIEJA = ('2022-01-10', 'Buy', 'AAA', 100, 10.00, -1000.00)


@pytest.mark.parametrize('fecha_nueva,fecha_venta,tramo,aproximado', [
    ('2025-06-02', '2025-07-01', 'lt_2y', True),    # 1268 y 29 días: a los dos lados
    ('2022-03-01', '2025-07-01', 'ge_2y', False),   # las dos compras pasan el corte
    ('2025-06-02', '2025-06-20', 'lt_2y', True),
    ('2022-01-12', '2024-01-11', 'ge_2y', True),    # 731 y 729 días: a un día de cada lado
    ('2022-01-11', '2024-01-11', 'ge_2y', False),   # 731 y 730: las dos ya pasaron
    ('2022-01-12', '2024-01-09', 'lt_2y', False),   # 729 y 727: ninguna ha pasado
])
def test_la_venta_con_compras_a_ambos_lados_del_corte_va_marcada(fecha_nueva, fecha_venta,
                                                                 tramo, aproximado):
    df = _df([VIEJA, (fecha_nueva, 'Buy', 'AAA', 100, 10.00, -1000.00),
              (fecha_venta, 'Sell', 'AAA', 50, 12.00, 600.00)])
    r = logic.build_capital_gains(df, 'AAA')['realized'][0]
    assert r['tramo'] == tramo
    assert r['tramo_aproximado'] is aproximado


def test_el_tramo_no_cambia_de_metodo_solo_se_marca():
    """Sigue siendo el día promedio: 100 de 1268 días y 100 de 29 dan 648, por debajo."""
    df = _df([VIEJA, ('2025-06-02', 'Buy', 'AAA', 100, 10.00, -1000.00),
              ('2025-07-01', 'Sell', 'AAA', 50, 12.00, 600.00)])
    r = logic.build_capital_gains(df, 'AAA')['realized'][0]
    assert r['holding_days'] == 648 and r['tramo'] == 'lt_2y'


def test_una_posicion_que_se_cerro_no_arrastra_su_antiguedad():
    df = _df([VIEJA, ('2025-01-10', 'Sell', 'AAA', 100, 12.00, 1200.00),
              ('2025-06-02', 'Buy', 'AAA', 100, 10.00, -1000.00),
              ('2025-07-01', 'Sell', 'AAA', 50, 12.00, 600.00)])
    ventas = logic.build_capital_gains(df, 'AAA')['realized']
    assert [v['tramo_aproximado'] for v in ventas] == [False, False]


@pytest.mark.parametrize('hoy,aproximado', [('2025-07-01', True), ('2027-07-01', False)])
def test_lo_no_vendido_lleva_la_misma_marca(hoy, aproximado):
    df = _df([VIEJA, ('2025-06-02', 'Buy', 'AAA', 100, 10.00, -1000.00)])
    u = logic.build_capital_gains(df, 'AAA', market_price=12.0, today=hoy)['unrealized']
    assert u['tramo_aproximado'] is aproximado


def test_la_reinversion_tambien_cuenta_como_compra_reciente():
    df = _df([VIEJA, ('2025-06-02', 'Reinvest Shares', 'AAA', 5, 10.00, -50.00),
              ('2025-07-01', 'Sell', 'AAA', 50, 12.00, 600.00)])
    r = logic.build_capital_gains(df, 'AAA')['realized'][0]
    assert r['tramo'] == 'ge_2y' and r['tramo_aproximado'] is True


# ── La pantalla lo cuenta ────────────────────────────────────────────────────────────

def _stats(realized):
    return {"capital_gains": {"estado": "ok", "realized": realized, "unrealized": None},
            "history": pd.DataFrame({"Action": ["Buy"]}), "shares_owned": 1.0,
            "market_value": 1.0, "pocket_investment": 1.0}


def test_el_adaptador_cuenta_las_ventas_de_reparto_aproximado(monkeypatch):
    monkeypatch.setattr(adapters, "_tiene_datos", lambda st: True)
    ventas = [{"gain": 10.0, "tramo": "ge_2y", "tramo_aproximado": True},
              {"gain": 5.0, "tramo": "lt_2y", "tramo_aproximado": False},
              {"gain": 1.0, "tramo": "lt_2y"}]
    peld = {"gravable": {"monto": 100.0}, "retenido": {"monto": 30.0}}
    L = adapters._impuesto_local_cartera(peld, None, {"AAA": _stats(ventas)})
    assert L["ventas_tramo_aproximado"] == 1
    assert sum(t["n_ventas"] for t in L["realizado_por_tramo"].values()) == 3


def test_la_pantalla_avisa_del_reparto_aproximado_y_calla_si_no_lo_hay():
    import test_vista_impuestos_render as tv
    if not tv.shutil.which("node"):
        pytest.skip("node ausente")
    for n, esperado in ((0, None), (1, "en 1 venta tenías"), (3, "en 3 ventas tenías")):
        d = copy.deepcopy(tv._D)
        d["impuesto_local"]["realizado_por_tramo"]["ge_2y"]["n_ventas"] = 4
        d["impuesto_local"]["ventas_tramo_aproximado"] = n
        salida = tv._ejecutar(d=d)
        texto = " ".join(tv._texto(salida, f) for f in salida if f.startswith("fase"))
        assert "por debajo de ese corte" in texto
        if esperado is None:
            assert "Reparto aproximado" not in texto
        else:
            assert "Reparto aproximado:</b> " + esperado in texto, texto[-600:]
