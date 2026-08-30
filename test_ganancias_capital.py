"""Ganancia de capital por costo promedio ponderado — `logic.build_capital_gains`.

Eje NUEVO: antes de la Fase 3 no había ninguna ganancia de capital en el repo. Las dos cifras
que más se le parecen no sirven de base fiscal — `pocket_investment` es flujo de caja neto (las
ventas restan el importe recibido) y `net_profit` incluye dividendos sin separar realizado de
no realizado.

Los tests van por las tres trampas que el motor tiene que blindar (splits, DRIP, historia
incompleta) más la identidad cruzada que exige la Regla 3b del contrato fiscal.
"""
import pandas as pd
import pytest

import logic


def _df(filas):
    """Construye el DataFrame con las columnas que el motor lee."""
    return pd.DataFrame(filas, columns=['Date', 'Action', 'Symbol', 'Quantity', 'Price', 'Amount'])


def _splits(pares):
    """Serie de splits {fecha -> ratio}, la misma forma que `market_data['Stock Splits']`."""
    if not pares:
        return pd.Series(dtype=float)
    idx = pd.to_datetime([f for f, _ in pares])
    return pd.Series([r for _, r in pares], index=idx)


# ── Trampa 1: splits ────────────────────────────────────────────────────────────────

def test_split_no_convierte_una_ganancia_en_perdida():
    """Compra 100 @ $10, split 2:1, venta de las 200 @ $6 → +$200, NO −$400.

    Leer `Quantity` en crudo daría base 100×$10 = $1000 contra $1200 de ingreso... pero
    vendiendo 200 acciones contra 100 registradas dispararía 'indeterminado'. El ajuste por
    split es lo que hace que las dos patas hablen de la misma cantidad.
    """
    df = _df([
        ('2024-01-15', 'Buy',  'XLK', 100, 10.00, -1000.00),
        ('2024-07-01', 'Sell', 'XLK', 200,  6.00,  1200.00),
    ])
    cg = logic.build_capital_gains(df, 'XLK', splits=_splits([('2024-03-01', 2.0)]))

    assert cg['estado'] == 'ok', cg['motivo']
    assert len(cg['realized']) == 1
    assert cg['realized'][0]['gain'] == pytest.approx(200.00, abs=0.01)
    assert cg['realized_total'] == pytest.approx(200.00, abs=0.01)


def test_sin_ajuste_de_split_el_mismo_caso_saldria_mal():
    """Contraprueba: el mismo CSV sin la serie de splits NO puede dar +$200.

    Sin esto, el test de arriba pasaría igual con un motor que ignore los splits por completo
    y el guard no probaría nada.
    """
    df = _df([
        ('2024-01-15', 'Buy',  'XLK', 100, 10.00, -1000.00),
        ('2024-07-01', 'Sell', 'XLK', 200,  6.00,  1200.00),
    ])
    cg = logic.build_capital_gains(df, 'XLK', splits=None)

    assert cg['estado'] == 'indeterminado'
    assert cg['motivo'] == 'ventas_sin_compras_registradas'


# ── Costo promedio ponderado ────────────────────────────────────────────────────────

def test_promedio_ponderado_en_venta_parcial():
    """Dos compras a precios distintos + venta parcial: la base sale del PROMEDIO, y lo que
    queda vivo conserva el resto de la base.

    100 @ $10 + 100 @ $20 = $3000 / 200 acciones = $15 promedio.
    Vende 50 @ $25 → base $750, ingreso $1250, ganancia +$500.
    Quedan 150 acciones con base $2250.
    """
    df = _df([
        ('2024-01-10', 'Buy',  'AAA', 100, 10.00, -1000.00),
        ('2024-02-10', 'Buy',  'AAA', 100, 20.00, -2000.00),
        ('2024-06-10', 'Sell', 'AAA',  50, 25.00,  1250.00),
    ])
    cg = logic.build_capital_gains(df, 'AAA', market_price=30.00, today='2024-06-10')

    assert cg['estado'] == 'ok'
    r = cg['realized'][0]
    assert r['basis'] == pytest.approx(750.00, abs=0.01)
    assert r['gain'] == pytest.approx(500.00, abs=0.01)

    u = cg['unrealized']
    assert u['shares'] == pytest.approx(150.0)
    assert u['basis'] == pytest.approx(2250.00, abs=0.01)
    assert u['market_value'] == pytest.approx(4500.00, abs=0.01)
    assert u['gain'] == pytest.approx(2250.00, abs=0.01)


def test_el_metodo_va_declarado_en_el_objeto():
    """La Fase 4 se apoya en que el método sea promedio ponderado; no puede deducirlo."""
    df = _df([('2024-01-10', 'Buy', 'AAA', 10, 10.00, -100.00)])
    cg = logic.build_capital_gains(df, 'AAA')
    assert cg['method'] == 'costo_promedio_ponderado'
    assert cg['basis'] == 'costo_promedio'


# ── El corte de 2 años ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize('fecha_venta,tramo_esperado,dias', [
    ('2026-01-08', 'lt_2y', 729),   # un día antes del corte
    ('2026-01-09', 'ge_2y', 730),   # justo en el corte
])
# OJO con las fechas: 2024 es BISIESTO, así que los 730 días desde el 2024-01-10 caen el
# 2026-01-09, no el 2026-01-10. Escribir «dos años exactos» a ojo se equivoca por un día, y
# un día es justo lo que este test mide.
def test_corte_de_dos_anios_por_un_dia_a_cada_lado(fecha_venta, tramo_esperado, dias):
    df = _df([
        ('2024-01-10', 'Buy',  'AAA', 100, 10.00, -1000.00),
        (fecha_venta,  'Sell', 'AAA', 100, 12.00,  1200.00),
    ])
    cg = logic.build_capital_gains(df, 'AAA')
    r = cg['realized'][0]
    assert r['holding_days'] == dias
    assert r['tramo'] == tramo_esperado


# ── Trampa 2: DRIP sube la base ─────────────────────────────────────────────────────

def test_drip_sube_la_base_TOTAL_que_es_lo_estructural():
    """Lo que el DRIP hace SIEMPRE: añade acciones y añade su costo a la base total.

    Regla 5 del contrato: distinguir lo estructural de un hecho de mercado. Esto se cumple por
    construcción — las acciones reinvertidas costaron dinero y no son gratis — así que se
    assertá como invariante.
    """
    sin_drip = _df([('2024-01-10', 'Buy', 'MSTY', 100, 10.00, -1000.00)])
    con_drip = _df([
        ('2024-01-10', 'Buy',              'MSTY', 100, 10.00, -1000.00),
        ('2024-03-01', 'Reinvest Shares',  'MSTY',  10,  8.00,   -80.00),
        ('2024-03-01', 'Reinvest Dividend','MSTY',   0,  0.00,    80.00),
    ])
    a = logic.build_capital_gains(sin_drip, 'MSTY', market_price=15.0)
    b = logic.build_capital_gains(con_drip, 'MSTY', market_price=15.0)

    assert b['unrealized']['basis'] > a['unrealized']['basis']
    assert b['unrealized']['basis'] == pytest.approx(1080.00, abs=0.01)
    assert b['unrealized']['shares'] > a['unrealized']['shares']


@pytest.mark.parametrize('precio_reinversion,importe,promedio,esperado,por_que', [
    # 10 acciones reinvertidas. Promedio = (1000 + importe) / 110. Ganancia = 750 − 50×promedio.
    (8.00,   80.00,  9.8181, 259.09, "reinvertir por DEBAJO del promedio lo BAJA -> ganancia MAYOR"),
    (20.00, 200.00, 10.9090, 204.55, "reinvertir por ENCIMA del promedio lo SUBE  -> ganancia MENOR"),
])
def test_el_drip_mueve_la_ganancia_en_LAS_DOS_direcciones(
        precio_reinversion, importe, promedio, esperado, por_que):
    """«Con DRIP la ganancia realizada es menor» es FALSO como invariante — depende del precio
    al que se reinvirtió, que es un hecho de mercado.

    El spec de la Fase 3 lo pedía como aserción estructural («el mismo portafolio con y sin
    filas de reinversión da ganancia menor con DRIP») y **no se sostiene**: vendiendo un número
    FIJO de acciones, lo que decide la ganancia es el costo PROMEDIO por acción, no la base
    total. Reinvertir a $8 con un promedio de $10 lo baja a $9.82 y la ganancia SUBE.

    Es exactamente el patrón de la Regla 5, el mismo que ya mordió a este repo con «más
    impuesto ⇒ peor resultado» y con «NAV cayendo ⇒ el efectivo gana»: la intuición monótona
    falla porque el DRIP cambia el CAMINO, no solo el destino.
    """
    df = _df([
        ('2024-01-10', 'Buy',              'MSTY', 100, 10.00,             -1000.00),
        ('2024-03-01', 'Reinvest Shares',  'MSTY',  10, precio_reinversion, -importe),
        ('2024-03-01', 'Reinvest Dividend','MSTY',   0,  0.00,               importe),
        ('2024-09-01', 'Sell',             'MSTY',  50, 15.00,               750.00),
    ])
    cg = logic.build_capital_gains(df, 'MSTY')
    assert cg['estado'] == 'ok'
    assert cg['realized'][0]['basis'] / 50 == pytest.approx(promedio, abs=0.001)
    assert cg['realized_total'] == pytest.approx(esperado, abs=0.01), por_que


def test_reinvest_dividend_no_se_cuenta_como_compra():
    """La fila de ingreso ('Reinvest Dividend') no mueve acciones ni base — la compra es
    'Reinvest Shares'. Contarlas las dos duplica la reinversión."""
    con_fila_ingreso = _df([
        ('2024-01-10', 'Buy',              'MSTY', 100, 10.00, -1000.00),
        ('2024-03-01', 'Reinvest Shares',  'MSTY',  10,  8.00,   -80.00),
        ('2024-03-01', 'Reinvest Dividend','MSTY',   0,  0.00,    80.00),
    ])
    sin_fila_ingreso = _df([
        ('2024-01-10', 'Buy',             'MSTY', 100, 10.00, -1000.00),
        ('2024-03-01', 'Reinvest Shares', 'MSTY',  10,  8.00,   -80.00),
    ])
    a = logic.build_capital_gains(con_fila_ingreso, 'MSTY', market_price=12.0)
    b = logic.build_capital_gains(sin_fila_ingreso, 'MSTY', market_price=12.0)

    assert a['unrealized']['shares'] == pytest.approx(b['unrealized']['shares'])
    assert a['unrealized']['basis'] == pytest.approx(b['unrealized']['basis'])
    assert a['unrealized']['basis'] == pytest.approx(1080.00, abs=0.01)


# ── Trampa 3: historia incompleta = base DESCONOCIDA, no base cero ──────────────────

def test_venta_sin_compras_da_indeterminado_no_una_ganancia_igual_al_importe():
    """La aserción que importa no es «da indeterminado»: es que NO devuelve $2000."""
    df = _df([('2024-06-01', 'Sell', 'AAA', 100, 20.00, 2000.00)])
    cg = logic.build_capital_gains(df, 'AAA')

    assert cg['estado'] == 'indeterminado'
    assert cg['motivo'] == 'ventas_sin_compras_registradas'
    assert cg['realized_total'] is None
    assert cg['realized'] == []
    assert cg['unrealized'] is None


def test_venta_mayor_que_lo_comprado_tambien_es_indeterminado():
    df = _df([
        ('2024-01-10', 'Buy',  'AAA',  10, 10.00, -100.00),
        ('2024-06-01', 'Sell', 'AAA', 100, 20.00, 2000.00),
    ])
    cg = logic.build_capital_gains(df, 'AAA')
    assert cg['estado'] == 'indeterminado'
    assert cg['realized_total'] is None


def test_history_incomplete_entrante_manda_aunque_el_csv_parezca_sano():
    """`analyze_portfolio` ya detecta historial truncado por su cuenta. Si lo declara, este
    motor no puede contradecirlo con cifras que parecen buenas."""
    df = _df([
        ('2024-01-10', 'Buy',  'AAA', 100, 10.00, -1000.00),
        ('2024-06-01', 'Sell', 'AAA',  50, 20.00,  1000.00),
    ])
    sano = logic.build_capital_gains(df, 'AAA')
    assert sano['estado'] == 'ok'

    truncado = logic.build_capital_gains(df, 'AAA', history_incomplete=True)
    assert truncado['estado'] == 'indeterminado'
    assert truncado['motivo'] == 'history_incomplete'
    assert truncado['realized_total'] is None


def test_acciones_sin_costo_registrado_es_indeterminado():
    """Acciones vivas con base $0: un depósito sin importe deja la posición sin costo."""
    df = _df([('2024-01-10', 'Transfer', 'AAA', 100, 0.0, 0.0)])
    cg = logic.build_capital_gains(df, 'AAA', market_price=20.0)
    assert cg['estado'] == 'indeterminado'
    assert cg['motivo'] == 'acciones_sin_costo_registrado'
    assert cg['unrealized'] is None


def test_traspaso_sin_importe_ENTRE_compras_reales_tambien_es_indeterminado():
    """El caso PARCIAL, que es el traicionero: la mayoría de la posición sí tiene costo.

    Un guard de «base total ≤ 0» no lo ve, porque la base no queda en cero — queda DILUIDA,
    y la ganancia sale inflada por el valor entero de las acciones que llegaron gratis.

    Defecto real de la primera versión de este motor, cazado cruzando contra `pocket_investment`
    sobre los demos: XLK de `?demo=schwab` trae un `Internal Transfer` de 8.2230 acciones con
    Amount $0.00 (37% de la posición). La base salía $904.22 contra los $1,991.22 que el resto
    de la app reconoce — **$1,087.00 de ganancia fantasma**.
    """
    df = _df([
        ('2024-01-10', 'Buy',               'XLK',  3, 284.55, -853.65),
        ('2024-05-13', 'Internal Transfer', 'XLK',  8,   0.00,    0.00),
    ])
    cg = logic.build_capital_gains(df, 'XLK', market_price=300.0)

    assert cg['estado'] == 'indeterminado'
    assert cg['motivo'] == 'acciones_sin_costo_registrado'
    assert cg['unrealized'] is None, (
        "con acciones de costo desconocido no se puede publicar una ganancia latente")


def test_split_declarado_en_el_csv_reinicia_el_balance():
    """Una fila de split dentro del CSV anuncia el saldo POST-split y manda sobre lo
    acumulado — el mismo reinicio de balance que hace `analyze_portfolio`.

    Sin esto, el factor de mercado y la fila del CSV se aplican los dos y las acciones
    divergen. Medido antes del arreglo: MSTY salía 9.6443 contra las 9.1508 de
    `stats['shares_owned']` en `?demo=schwab2` — 5.39%.

    La base en DÓLARES no se toca: un split reparte el mismo costo entre otro número de
    acciones, no crea ni destruye costo.
    """
    df = _df([
        ('2024-01-10', 'Buy',           'MSTY', 100, 10.00, -1000.00),
        ('2025-12-01', 'Reverse Split', 'MSTY',  20,  0.00,     0.00),
    ])
    cg = logic.build_capital_gains(df, 'MSTY', market_price=50.00)

    assert cg['estado'] == 'ok', cg['motivo']
    assert cg['unrealized']['shares'] == pytest.approx(20.0), "el saldo lo fija la fila del CSV"
    assert cg['unrealized']['basis'] == pytest.approx(1000.00, abs=0.01), (
        "el split NO cambia el costo total")
    assert cg['unrealized']['gain'] == pytest.approx(0.00, abs=0.01)


def test_la_fila_de_split_no_cuenta_como_acciones_sin_costo():
    """Contracara del anterior: el reinicio de balance llega con Amount $0, pero NO puede
    disparar el guard de «acciones sin costo registrado» — si lo hiciera, cualquier fondo que
    haya hecho split quedaría indeterminado para siempre."""
    df = _df([
        ('2024-01-10', 'Buy',           'MSTY', 100, 10.00, -1000.00),
        ('2025-12-01', 'Reverse Split', 'MSTY',  20,  0.00,     0.00),
    ])
    assert logic.build_capital_gains(df, 'MSTY', market_price=50.0)['estado'] == 'ok'


# ── Regla 3b: dos vistas del mismo número ───────────────────────────────────────────

def test_identidad_exacta_sin_ventas_contra_pocket_investment():
    """Regla 3b del contrato fiscal: dos vistas del mismo número, comparadas entre sí.

    SIN ninguna venta, `pocket_investment` no ha restado ningún importe recibido, así que ahí
    —y solo ahí— SÍ es la base de costo. La identidad tiene que ser exacta:

        unrealized['gain'] == market_value − (pocket_investment + dividends_collected_drip)

    Si no cuadra, el motor está mal, no el test. El lado derecho se calcula con el recorrido
    de `analyze_portfolio` (los mismos predicados), no con el motor que se está probando.
    """
    filas = [
        ('2024-01-10', 'Buy',              'MSTY', 100, 10.00, -1000.00),
        ('2024-02-10', 'Buy',              'MSTY',  50, 12.00,  -600.00),
        ('2024-03-01', 'Reinvest Shares',  'MSTY',  10,  8.00,   -80.00),
        ('2024-03-01', 'Reinvest Dividend','MSTY',   0,  0.00,    80.00),
        ('2024-04-01', 'Cash Dividend',    'MSTY',   0,  0.00,    45.00),
    ]
    df = _df(filas)
    precio = 14.00
    cg = logic.build_capital_gains(df, 'MSTY', market_price=precio, today='2024-05-01')

    # Lado independiente: reconstruido con la semántica del recorrido principal.
    pocket_investment = 1000.00 + 600.00          # solo compras de bolsillo
    dividends_collected_drip = 80.00              # la reinversión también costó dinero
    shares = 100 + 50 + 10
    market_value = shares * precio

    esperado = market_value - (pocket_investment + dividends_collected_drip)

    assert cg['estado'] == 'ok'
    assert cg['unrealized']['shares'] == pytest.approx(shares)
    assert cg['unrealized']['market_value'] == pytest.approx(market_value, abs=0.01)
    assert cg['unrealized']['gain'] == pytest.approx(esperado, abs=0.01)


def test_la_identidad_se_rompe_con_ventas_y_por_eso_solo_vale_sin_ellas():
    """La contracara del test anterior, y la razón de que esté acotado a «sin ventas».

    Con una venta, `pocket_investment` RESTA el importe recibido, así que deja de ser la base
    de costo y la identidad ya no aplica. Fijarlo evita que alguien «arregle» el motor para
    que cuadre también aquí — que sería reintroducir el defecto que motivó la Fase 3.
    """
    filas = [
        ('2024-01-10', 'Buy',  'AAA', 100, 10.00, -1000.00),
        ('2024-06-01', 'Sell', 'AAA',  50, 30.00,  1500.00),
    ]
    cg = logic.build_capital_gains(_df(filas), 'AAA', market_price=30.00)

    pocket_investment = 1000.00 - 1500.00   # flujo de caja neto: NEGATIVO
    market_value = 50 * 30.00

    identidad_ingenua = market_value - pocket_investment       # 1500 − (−500) = 2000
    assert cg['unrealized']['gain'] == pytest.approx(1000.00, abs=0.01)
    assert cg['unrealized']['gain'] != pytest.approx(identidad_ingenua, abs=0.01)


# ── Contrato del objeto ─────────────────────────────────────────────────────────────

def test_el_objeto_declara_base_momento_y_que_el_roc_no_esta_dentro():
    """Regla 2: cada cifra declara base y momento. Y la Regla 1 dice que el ROC mueve la base
    fiscal — como aquí todavía NO se aplica, el objeto tiene que declararlo para que ninguna
    vista pueda afirmar lo contrario."""
    df = _df([
        ('2024-01-10', 'Buy',  'AAA', 100, 10.00, -1000.00),
        ('2024-06-01', 'Sell', 'AAA',  50, 20.00,  1000.00),
    ])
    cg = logic.build_capital_gains(df, 'AAA', market_price=20.0)

    assert cg['moment_realized'] == 'al_cierre_de_la_venta'
    assert cg['moment_unrealized'] == 'a_precio_de_mercado_hoy'
    assert cg['roc_basis_adjustment_applied'] is False
    assert cg['is_estimate'] is True


def test_sin_transacciones_no_inventa_nada():
    cg = logic.build_capital_gains(_df([]), 'AAA')
    assert cg['estado'] == 'indeterminado'
    assert cg['realized_total'] is None
    assert cg['unrealized'] is None


# ── El agregador de cartera (`ui.adapters`) ─────────────────────────────────────────

def _stats(cg, **extra):
    base = {"shares_owned": 10, "pocket_investment": 100.0, "capital_gains": cg}
    base.update(extra)
    return base


def _cg_ok(realized_total=0.0, n_ventas=0, gain=None, valor=None, base=None):
    return {
        "ticker": None, "method": "costo_promedio_ponderado", "estado": "ok", "motivo": None,
        "realized": [{"gain": realized_total}] * n_ventas,
        "realized_total": realized_total,
        "unrealized": (None if gain is None else
                       {"shares": 10, "basis": base, "market_value": valor, "gain": gain,
                        "holding_days_ponderado": 400, "tramo": "lt_2y"}),
        "basis": "costo_promedio", "moment_realized": "al_cierre_de_la_venta",
        "moment_unrealized": "a_precio_de_mercado_hoy",
        "roc_basis_adjustment_applied": False, "is_estimate": True,
    }


def test_el_agregador_no_suma_un_indeterminado_como_cero():
    """La aserción central del agregador: un ticker sin base NO aporta $0 al total — se aparta
    y se nombra. Sumarlo como cero es el mismo cero falso, una capa más arriba."""
    from ui import adapters

    resultados = {
        "AAA": _stats(_cg_ok(gain=500.0, valor=1500.0, base=1000.0)),
        "BBB": _stats({"estado": "indeterminado", "motivo": "acciones_sin_costo_registrado",
                       "realized": [], "realized_total": None, "unrealized": None}),
    }
    g = adapters._ganancias_capital_cartera(resultados)

    assert g["estado"] == "parcial"
    assert g["tickers_indeterminados"] == ["BBB"]
    assert g["n_fondos"] == 1 and g["n_fondos_total"] == 2, (
        "el alcance tiene que viajar con las cifras: 1 de 2, no «el total»")
    assert g["no_realizado"]["monto"] == pytest.approx(500.0)
    assert g["no_realizado"]["valor_mercado"] == pytest.approx(1500.0), (
        "el valor de mercado tampoco puede incluir al indeterminado")


def test_el_agregador_no_suma_realizado_con_no_realizado():
    """Regla 2: momentos distintos no se combinan en un total. Salen como dos cifras."""
    from ui import adapters

    g = adapters._ganancias_capital_cartera({
        "AAA": _stats(_cg_ok(realized_total=300.0, n_ventas=2,
                             gain=500.0, valor=1500.0, base=1000.0)),
    })
    assert g["realizado"]["monto"] == pytest.approx(300.0)
    assert g["realizado"]["n_ventas"] == 2
    assert g["no_realizado"]["monto"] == pytest.approx(500.0)
    assert "total" not in g, "no existe un total que mezcle los dos momentos"
    assert g["estado"] == "ok"


def test_la_retencion_de_eeuu_es_cero_por_definicion():
    """El mensaje del peldaño: para un no residente, la ganancia de capital de un ETF o acción
    normal no es renta de fuente estadounidense. No es una estimación."""
    from ui import adapters

    g = adapters._ganancias_capital_cartera({
        "AAA": _stats(_cg_ok(gain=500.0, valor=1500.0, base=1000.0)),
    })
    assert g["retencion_eeuu"] == 0.0
    assert g["roc_basis_adjustment_applied"] is False


def test_el_slot_de_ganancias_ya_no_esta_en_los_pendientes():
    """La Fase 3 LLENA el slot reservado; no crea uno nuevo ni deja el «PRÓXIMAMENTE». El de
    la Fase 4 (`impuesto_local`) se queda intacto."""
    from ui import adapters

    demo_mode = _demos()
    resultados = (demo_mode.load_demo_case("ib") or {}).get("_results") or {}
    assert resultados, "el demo de IB no trajo resultados"

    datos = adapters.impuestos_data(resultados, {"country": None, "rate_pct": None}, [])
    assert datos is not None

    ids = [s["id"] for s in datos.get("slots_pendientes", [])]
    assert ids == ["impuesto_local"], (
        "el slot de ganancias tiene que quedar LLENO, y el de la Fase 4 intacto")
    assert datos.get("ganancias_capital"), "el peldaño 5 no trae datos"


# ── El gate cruzado sobre datos REALES ──────────────────────────────────────────────

def _demos():
    import demo_mode
    if not demo_mode.demo_available():
        pytest.skip("real_examples/ no montado — el cruce sobre datos reales no puede correr")
    return demo_mode


@pytest.mark.parametrize('caso', ['ib', 'schwab', 'schwab2'])
def test_cruce_contra_analyze_portfolio_sobre_los_casos_reales(caso):
    """El gate que exige la Regla 3b: dos vistas del mismo número, comparadas ENTRE SÍ sobre
    datos reales — no cada una contra sí misma.

    Los dos lados son genuinamente independientes: `build_capital_gains` hace su propio
    recorrido de filas, y `stats['shares_owned']` / `pocket_investment` salen del recorrido de
    `analyze_portfolio`. Este cruce cazó los DOS defectos que los fixtures sintéticos no
    vieron:

    - **Acciones sin costo** — XLK de `?demo=schwab`, un `Internal Transfer` de 8.2230
      acciones a $0.00: base $904.22 contra $1,991.22, $1,087.00 de ganancia fantasma.
    - **Split declarado en el CSV** — MSTY de `?demo=schwab2`: 9.6443 acciones contra 9.1508,
      un 5.39%, por aplicar a la vez el factor de mercado y la fila del CSV.

    Los tickers en `'indeterminado'` se saltan a propósito: ahí el motor declara que NO tiene
    la base, y esa es la respuesta correcta, no una divergencia.
    """
    demo_mode = _demos()
    bundle = demo_mode.load_demo_case(caso)
    if not bundle:
        pytest.skip(f"el caso {caso} no está disponible")
    resultados = bundle.get('_results') or {}
    assert resultados, f"el demo {caso} no trajo resultados"

    comprobados = 0
    for ticker, stats in sorted(resultados.items()):
        cg = (stats or {}).get('capital_gains') or {}
        if cg.get('estado') != 'ok':
            continue
        u = cg.get('unrealized')
        if not u:
            continue
        comprobados += 1

        assert u['shares'] == pytest.approx(stats.get('shares_owned'), abs=0.01), (
            f"{caso}/{ticker}: las acciones del motor de ganancias no cuadran con "
            f"stats['shares_owned'] — mira el ajuste por split")

        # La base solo es comparable SIN ventas: con una venta `pocket_investment` resta el
        # importe recibido y deja de ser base de costo (el hallazgo que motivó esta fase).
        if (stats.get('shares_sold') or 0) == 0:
            esperado = ((stats.get('pocket_investment') or 0.0)
                        + (stats.get('dividends_collected_drip') or 0.0))
            assert u['basis'] == pytest.approx(esperado, abs=0.02), (
                f"{caso}/{ticker}: la base de costo no cuadra con pocket_investment + DRIP")

    assert comprobados > 0, f"el caso {caso} no ejerció ni un ticker — el test no probó nada"
