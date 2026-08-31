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


# ── Ramas que los datos reales NO ejercitan (M4 §3): forzadas a mano ────────────────

def test_traspaso_de_SALIDA_se_lleva_su_parte_de_la_base():
    """Rama que ningún demo alcanza hoy: acciones que SALEN por traspaso.

    Se van con su parte proporcional de la base — eso es contabilidad correcta, no una
    venta: no hay ingreso, así que no hay ganancia que realizar.

    **Diverge de `pocket_investment` a propósito**, y hay que saberlo: ese número es un flujo
    de caja y no se mueve aquí (no salió dinero), así que se queda en $1,000 mientras la base
    real baja a $600. Los dos son correctos y miden cosas distintas — que es exactamente el
    hallazgo que motivó esta fase. Por eso el test cruzado sobre los demos excluye estos
    tickers en vez de exigir que cuadren.
    """
    df = _df([
        ('2024-01-10', 'Buy',               'AAA', 100, 10.00, -1000.00),
        ('2024-06-01', 'Internal Transfer', 'AAA', -40,  0.00,     0.00),
    ])
    cg = logic.build_capital_gains(df, 'AAA', market_price=12.00)

    assert cg['estado'] == 'ok', cg['motivo']
    assert cg['realized'] == [], "un traspaso de salida NO es una venta: no realiza ganancia"
    assert cg['unrealized']['shares'] == pytest.approx(60.0)
    assert cg['unrealized']['basis'] == pytest.approx(600.00, abs=0.01), (
        "las 40 acciones que salieron se llevan su parte proporcional del costo")
    assert cg['unrealized']['gain'] == pytest.approx(120.00, abs=0.01)


def test_sin_precio_de_mercado_no_se_inventa_una_ganancia_latente():
    """Rama no alcanzada por los demos (allí siempre hay precio): sin `market_price` la
    ganancia latente es `None`, no cero. Cero diría «no has ganado nada»."""
    df = _df([('2024-01-10', 'Buy', 'AAA', 100, 10.00, -1000.00)])
    cg = logic.build_capital_gains(df, 'AAA', market_price=None)

    assert cg['estado'] == 'ok'
    assert cg['unrealized']['market_value'] is None
    assert cg['unrealized']['gain'] is None
    assert cg['unrealized']['basis'] == pytest.approx(1000.00, abs=0.01), (
        "la base sí se conoce aunque falte el precio")


def test_fecha_ilegible_no_revienta_ni_inventa_tenencia():
    """Rama no alcanzada: una fila con fecha que no parsea. El tramo de 2 años decide tarifa
    en la Fase 4, así que ante una fecha ilegible el tramo tiene que ser `None`, no un
    valor por defecto."""
    df = _df([
        ('no-es-una-fecha', 'Buy',  'AAA', 100, 10.00, -1000.00),
        ('no-es-una-fecha', 'Sell', 'AAA',  50, 20.00,  1000.00),
    ])
    cg = logic.build_capital_gains(df, 'AAA', market_price=20.0)

    assert cg['estado'] == 'ok', cg['motivo']
    r = cg['realized'][0]
    assert r['gain'] == pytest.approx(500.00, abs=0.01), "la aritmética no depende de la fecha"
    assert r['holding_days'] is None
    assert r['tramo'] is None, "sin fecha no se puede afirmar el tramo de 2 años"


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
        #
        # Y tampoco con un traspaso de SALIDA: ahí las acciones se van con su parte de la base
        # (contabilidad correcta) mientras `pocket_investment` no se mueve, porque es un flujo
        # de caja y no salió dinero. Los dos números son correctos y distintos. Se excluye a
        # propósito y no por comodidad — hoy ningún demo tiene uno, y sin esta exclusión el
        # día que aparezca este test daría un rojo falso, que es como se entrena a ignorarlos.
        acciones = pd.to_numeric(stats['history'].get('Quantity'), errors='coerce')
        acts = stats['history']['Action'].astype(str).str.lower()
        salida = bool(((acts.str.contains('transfer') | acts.str.contains('journal'))
                       & (acciones < 0)).any())

        if (stats.get('shares_sold') or 0) == 0 and not salida:
            esperado = ((stats.get('pocket_investment') or 0.0)
                        + (stats.get('dividends_collected_drip') or 0.0))
            assert u['basis'] == pytest.approx(esperado, abs=0.02), (
                f"{caso}/{ticker}: la base de costo no cuadra con pocket_investment + DRIP")

    assert comprobados > 0, f"el caso {caso} no ejerció ni un ticker — el test no probó nada"


# ── Ajuste de la base por ROC (Fase 3.5) ────────────────────────────────────────────
#
# La Regla 1 del contrato dice que la reclasificación mueve la base fiscal de la posición.
# Estos tests cubren las dos cosas que hacen que eso sea correcto y no una resta:
#   (1) el ROC entra FECHADO — a una venta solo le toca el ROC devengado antes de ella;
#   (2) la cifra ajustada viaja APARTE, sin pisar `basis`/`gain` (Regla 2: otro momento).

def _roc_caso_base():
    """Compra 100 @ $10; venta de 40 @ $12; ROC de $200 ANTES de la venta y $300 DESPUÉS."""
    df = _df([
        ('2024-01-15', 'Buy',  'YMAX', 100, 10.00, -1000.00),
        ('2024-06-01', 'Sell', 'YMAX',  40, 12.00,   480.00),
    ])
    eventos = [(pd.Timestamp('2024-03-01'), 200.0),   # antes de la venta
               (pd.Timestamp('2024-09-01'), 300.0)]   # después
    return df, eventos


def test_el_roc_posterior_a_la_venta_no_baja_la_base_de_lo_vendido():
    """El corazón del diseño fechado. Con $200 de ROC antes y $300 después de la venta:

    - a las 40 acciones vendidas solo les toca su parte de los $200 → base $320, ganancia $160;
    - los $300 posteriores caen enteros sobre las 60 que quedaron.

    Restar el ROC ACUMULADO al final daría $80 (la misma ganancia que sin ROC, porque la resta
    ocurriría después de que la venta ya se cerró); repartirlo a prorrata sobre todas las
    acciones daría $200. Las dos son cifras distintas de la correcta, así que este assert
    distingue el modelo fechado de sus dos alternativas plausibles.
    """
    df, eventos = _roc_caso_base()
    cg = logic.build_capital_gains(df, 'YMAX', market_price=8.00,
                                   roc_events=eventos, roc_source='19a')

    assert cg['estado'] == 'ok', cg['motivo']
    assert cg['roc_basis_adjustment_applied'] is True
    assert cg['roc_basis_source'] == '19a'

    venta = cg['realized'][0]
    assert venta['basis'] == pytest.approx(400.00, abs=0.01)
    assert venta['basis_roc_adjusted'] == pytest.approx(320.00, abs=0.01)
    assert venta['gain_roc_adjusted'] == pytest.approx(160.00, abs=0.01)

    u = cg['unrealized']
    assert u['basis'] == pytest.approx(600.00, abs=0.01)
    assert u['basis_roc_adjusted'] == pytest.approx(180.00, abs=0.01)


def test_las_cifras_sin_ajustar_no_se_mueven_al_aplicar_el_roc():
    """Regla 2: la base ajustada es otro MOMENTO, no una corrección de la original.

    Correr el mismo CSV con y sin serie de ROC tiene que dar `basis`/`gain` idénticos al
    centavo. Si el ajuste se hiciera en sitio, las vistas que ya consumen esos campos
    cambiarían de significado sin que nadie las tocara.
    """
    df, eventos = _roc_caso_base()
    sin = logic.build_capital_gains(df, 'YMAX', market_price=8.00)
    con = logic.build_capital_gains(df, 'YMAX', market_price=8.00,
                                    roc_events=eventos, roc_source='19a')

    assert con['realized'][0]['basis'] == pytest.approx(sin['realized'][0]['basis'], abs=0.001)
    assert con['realized'][0]['gain'] == pytest.approx(sin['realized'][0]['gain'], abs=0.001)
    assert con['realized_total'] == pytest.approx(sin['realized_total'], abs=0.001)
    assert con['unrealized']['basis'] == pytest.approx(sin['unrealized']['basis'], abs=0.001)
    assert con['unrealized']['gain'] == pytest.approx(sin['unrealized']['gain'], abs=0.001)


def test_sin_serie_de_roc_las_gemelas_salen_none_y_no_una_copia():
    """Sin ROC que aplicar, la cifra ajustada NO existe — no es igual a la sin ajustar.

    Publicar una copia haría que una vista la mostrara como segunda confirmación de un número
    que en realidad nadie ajustó. Es el mismo criterio por el que `estado='indeterminado'`
    devuelve `None` en vez de cero.
    """
    df, _ = _roc_caso_base()
    cg = logic.build_capital_gains(df, 'YMAX', market_price=8.00)

    assert cg['roc_basis_adjustment_applied'] is False
    assert cg['roc_basis_source'] is None
    assert cg['roc_basis_applied_total'] is None
    assert cg['realized_total_roc_adjusted'] is None
    assert cg['realized'][0]['basis_roc_adjusted'] is None
    assert cg['realized'][0]['gain_roc_adjusted'] is None
    assert cg['unrealized']['basis_roc_adjusted'] is None
    assert cg['unrealized']['gain_roc_adjusted'] is None


def test_el_origen_broker_no_ajusta_la_base():
    """`roc_source='broker'` es la resta contra el costo de HOY: no tiene fecha que repartir,
    y M1 §4 lo tiene medido como subestimador del ROC cuando hay reinversión ($18 contra $191
    reales en MSTY). Aunque llegue una serie, con ese origen no se aplica nada.
    """
    df, eventos = _roc_caso_base()
    cg = logic.build_capital_gains(df, 'YMAX', market_price=8.00,
                                   roc_events=eventos, roc_source='broker')

    assert cg['roc_basis_adjustment_applied'] is False
    assert cg['unrealized']['basis_roc_adjusted'] is None


def test_el_roc_que_excede_la_base_no_la_deja_negativa():
    """Una base fiscal negativa no existe: el ROC que supera la base es ganancia de capital
    inmediata. Se topa en cero y el excedente se declara aparte, para que una vista pueda
    decirlo en vez de mostrar un número imposible.
    """
    df = _df([('2024-01-15', 'Buy', 'YMAX', 100, 10.00, -1000.00)])
    cg = logic.build_capital_gains(df, 'YMAX', market_price=5.00,
                                   roc_events=[(pd.Timestamp('2024-06-01'), 1500.0)],
                                   roc_source='19a')

    assert cg['unrealized']['basis_roc_adjusted'] == pytest.approx(0.0, abs=0.01)
    assert cg['roc_basis_applied_total'] == pytest.approx(1000.00, abs=0.01)
    assert cg['roc_basis_excess'] == pytest.approx(500.00, abs=0.01)


def test_conservacion_la_base_baja_exactamente_lo_que_el_roc_aplico():
    """Invariante ESTRUCTURAL (no un hecho de mercado): la suma de lo que bajó la base —lo que
    queda vivo más lo que se fue con las ventas— es exactamente `roc_basis_applied_total`.

    Es lo que ata el reparto en el tiempo: si el recorrido perdiera un evento, contara uno dos
    veces, o no descontara la parte proporcional al vender, esta identidad se rompe.
    """
    df, eventos = _roc_caso_base()
    cg = logic.build_capital_gains(df, 'YMAX', market_price=8.00,
                                   roc_events=eventos, roc_source='19a')

    bajada_viva = cg['unrealized']['basis'] - cg['unrealized']['basis_roc_adjusted']
    bajada_vendida = sum(r['basis'] - r['basis_roc_adjusted'] for r in cg['realized'])
    assert bajada_viva + bajada_vendida == pytest.approx(cg['roc_basis_applied_total'], abs=0.01)


def test_una_distribucion_anterior_a_la_primera_compra_no_baja_nada():
    """Sin posición viva no hay base que reducir. Un evento huérfano no puede empujar la base
    a negativo ni contarse como exceso: el exceso es ROC que supera una base EXISTENTE.
    """
    df = _df([('2024-05-01', 'Buy', 'YMAX', 100, 10.00, -1000.00)])
    cg = logic.build_capital_gains(df, 'YMAX', market_price=9.00,
                                   roc_events=[(pd.Timestamp('2024-01-01'), 400.0)],
                                   roc_source='19a')

    assert cg['unrealized']['basis_roc_adjusted'] == pytest.approx(1000.00, abs=0.01)
    assert cg['roc_basis_applied_total'] == pytest.approx(0.0, abs=0.01)
    assert cg['roc_basis_excess'] == pytest.approx(0.0, abs=0.01)


@pytest.mark.parametrize('caso', ['ib', 'schwab', 'schwab2'])
def test_el_roc_aplicado_cuadra_con_el_acumulado_del_motor(caso):
    """Regla 5 del contrato: dos vistas del mismo número, comparadas ENTRE SÍ sobre datos
    reales. `roc_basis_applied_total` sale del recorrido cronológico de `build_capital_gains`;
    `stats['roc_accumulated']` sale del estimador que suma las distribuciones en
    `analyze_portfolio`. Son dos caminos distintos hasta el mismo dólar.

    La identidad solo se exige cuando NO hubo ventas ni exceso: al vender, parte del ROC ya
    aplicado se va con las acciones vendidas y la base viva deja de contenerlo entero —
    seguirían cuadrando, pero contra la suma de las dos patas, que es justo lo que verifica
    `test_conservacion_la_base_baja_exactamente_lo_que_el_roc_aplico` sobre datos sintéticos.
    """
    demo_mode = _demos()
    bundle = demo_mode.load_demo_case(caso)
    if not bundle:
        pytest.skip(f"el caso {caso} no está disponible")

    comprobados = 0
    for ticker, stats in sorted((bundle.get('_results') or {}).items()):
        cg = (stats or {}).get('capital_gains') or {}
        if not cg.get('roc_basis_adjustment_applied'):
            continue
        if cg.get('realized') or (cg.get('roc_basis_excess') or 0) > 0.01:
            continue
        comprobados += 1
        assert cg['roc_basis_applied_total'] == pytest.approx(
            stats.get('roc_accumulated'), abs=0.02), (
            f"{caso}/{ticker}: el ROC repartido en el tiempo no suma el acumulado del motor")

    assert comprobados > 0, (
        f"{caso}: ningún ticker ejerció el ajuste por ROC — el cruce no probó nada")


def test_un_fondo_con_19a_pero_sin_ajuste_se_nombra_en_vez_de_desaparecer():
    """El alcance del bloque fiscal no puede leerse como «los demás no tienen ROC».

    Un fondo puede publicar avisos 19a y aun así quedarse sin ajuste, porque su ROC se
    resolvió por la ruta del costo del bróker — donde la reclasificación de fin de año todavía
    no aparece. Ese fondo NO es un ETF amplio sin ROC, y callarlo convierte un «no lo sabemos»
    en un «no lo tiene».

    El borde que lo produce está medido: la ruta se decide por si el costo del bróker quedó
    por debajo de (aportado + reinvertido), y PLTY del demo de IB cae a $0.72 de ese umbral —
    dos centavos al otro lado mueven su ROC de −$0.01 a $96.26.
    """
    from ui import adapters

    demo_mode = _demos()
    bundle = demo_mode.load_demo_case('ib')
    if not bundle:
        pytest.skip("el caso ib no está disponible")

    resultados = bundle.get('_results') or {}
    datos = adapters._ganancias_capital_cartera(resultados)
    fiscal = (datos or {}).get('fiscal_roc') or {}
    assert fiscal, "el demo de IB tiene que ejercer el bloque fiscal"

    nombrados = set(fiscal.get('tickers') or []) | set(fiscal.get('tickers_19a_sin_ajuste') or [])
    olvidados = [
        tk for tk, st in resultados.items()
        if (st or {}).get('roc_19a_published')
        and ((st or {}).get('capital_gains') or {}).get('estado') == 'ok'
        and tk not in nombrados
    ]
    assert not olvidados, (
        f"fondos que publican 19a y no se nombran ni como ajustados ni como pendientes: "
        f"{olvidados} — el lector los leería como fondos sin ROC")
