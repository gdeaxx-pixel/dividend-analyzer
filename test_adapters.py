"""Objeto fiscal único en ui/adapters.py: cashflow_data (bruto/neto ya NO se reconstruyen
sumando/restando sobre `total_dividends`) y verificar_identidades (el guard nuevo reconcilia
contra una relectura independiente del CSV, no contra la propia fórmula — Regla 3 del
invariante ROC/NRA).
"""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import logic                                            # noqa: E402
from ui.adapters import cashflow_data, verificar_identidades  # noqa: E402


class FakeFile:
    def __init__(self, content: bytes, name: str = "test.csv"):
        self._buf = io.BytesIO(content)
        self.name = name

    def read(self):
        return self._buf.read()

    def seek(self, n):
        self._buf.seek(n)


_MKT_MOCK = lambda t, d: (
    __import__("pandas").DataFrame(
        {"Close": [20.0], "Dividends": [0.0], "Stock Splits": [0.0]},
        index=__import__("pandas").to_datetime(["2026-01-01"])), None)


def _schwab_msty_stats(monkeypatch, version="TEST_ADAPTERS_SCHWAB"):
    """`stats["MSTY"]` real vía analyze_portfolio sobre fixtures/schwab_synth_2 — ground
    truth: bruto $462.00, retención $138.60, neto $323.40, sin DRIP.

    `version` es la cache key de `@st.cache_data` sobre `analyze_portfolio`: un test que
    monkeypatchea una función interna (p.ej. `logic._dividend_tax_netted`) y reusa la misma
    version que otro test ya corrido en la sesión recibiría el resultado CACHEADO de ese otro
    test, sin pasar de nuevo por la función sabotajeada — silenciosamente inválido. Cada test
    que sabotea algo debe pasar su propia version única.
    """
    raw = open(os.path.join(os.path.dirname(__file__), "fixtures", "schwab_synth_2",
                             "synthetic_transactions.csv"), "rb").read()
    df, broker = logic.load_and_detect_csv(FakeFile(raw, "schwab_synth_2.csv"))
    assert broker == "schwab"
    dfc = logic.normalize_csv(df)
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    res = logic.analyze_portfolio(dfc, version=version)
    return res["MSTY"]


def _ib_msty_stats(monkeypatch):
    """`stats["MSTY"]` real vía analyze_portfolio sobre real_examples/interactive_brokers_data/1
    — ground truth: bruto $7,224.59, retención $545.52, neto $6,679.07."""
    base = os.path.dirname(__file__)
    csv_path = os.path.join(base, "real_examples", "interactive_brokers_data", "1",
                             "U15179613.TRANSACTIONS.20240820.20260514.csv")
    if not os.path.exists(csv_path):
        pytest.skip("real_examples/interactive_brokers_data/1 no disponible")
    with open(csv_path, "rb") as f:
        df, broker = logic.load_and_detect_csv(FakeFile(f.read(), "ib_1.csv"))
    assert broker == "ibkr"
    dfc = logic.normalize_csv(df)
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    res = logic.analyze_portfolio(dfc, version="TEST_ADAPTERS_IB")
    return res["MSTY"]


# ── cashflow_data: bruto/neto leídos del objeto fiscal, no reconstruidos ────────────────────

def test_cashflow_data_bruto_neto_schwab_no_duplica_retencion(monkeypatch):
    """Antes del fix, BRUTO = total_dividends + impuesto duplicaba la retención para Schwab
    (total_dividends YA era el bruto). Ahora BRUTO/NETO vienen de `dividends_gross_total` /
    `dividends_net_total`, declarados por `build_dividend_tax_totals`."""
    s = _schwab_msty_stats(monkeypatch)
    datos = cashflow_data(s, "MSTY")
    assert datos["BRUTO"] == pytest.approx(462.00, abs=0.01)
    assert datos["IMPUESTO"] == pytest.approx(138.60, abs=0.01)
    assert datos["NETO"] == pytest.approx(323.40, abs=0.01)
    # CASH ya no es el `dividends_collected_cash` bruto crudo (462): es lo que de verdad
    # quedó líquido tras el impuesto (neto − drip, aquí sin DRIP → neto completo).
    assert datos["CASH"] == pytest.approx(323.40, abs=0.01)
    assert datos["DRIP"] == pytest.approx(0.0, abs=0.01)
    # CAPITAL_ACTUAL/RESULTADO heredan el fix (ya no inflados con el bruto sin retener).
    assert datos["CAPITAL_ACTUAL"] == pytest.approx(
        s["market_value"] + 323.40, abs=0.01)


def test_cashflow_data_bruto_neto_ib_ya_neteado(monkeypatch):
    """Convención IB: `dividends_collected_cash` ya viene neto (la retención está plegada en
    la propia fila) — CASH no cambia respecto del campo crudo, a diferencia de Schwab."""
    s = _ib_msty_stats(monkeypatch)
    datos = cashflow_data(s, "MSTY")
    assert datos["BRUTO"] == pytest.approx(7224.59, abs=0.01)
    assert datos["IMPUESTO"] == pytest.approx(545.52, abs=0.01)
    assert datos["NETO"] == pytest.approx(6679.07, abs=0.01)
    assert datos["CASH"] == pytest.approx(
        datos["NETO"] - datos["DRIP"], abs=0.01)


def test_e4_cashflow_lee_el_efectivo_del_motor():
    """Ancla absoluta, sin precio: unos `stats` con dividends_cash_net = 12.34 y
    neto - drip = -99.0 dan CASH == 12.34; sin el campo (legado) siguen dando -99.0. Este
    es el test que impide que la identidad se cumpla moviendo los dos lados a la vez."""
    base_stats = {
        "pocket_investment": 1000.0, "market_value": 900.0,
        "dividends_gross_total": 200.0, "dividends_net_total": 1.0,
        "dividends_collected_drip": 100.0, "dividends_collected_cash": 1.0,
        "withheld_tax_total": 60.0,
    }
    con_campo = dict(base_stats, dividends_cash_net=12.34)
    datos_con = cashflow_data(con_campo, "ZZZZ")
    assert datos_con["CASH"] == pytest.approx(12.34, abs=0.001)

    sin_campo = dict(base_stats)
    datos_sin = cashflow_data(sin_campo, "ZZZZ")
    assert datos_sin["CASH"] == pytest.approx(-99.0, abs=0.001)


def test_cashflow_data_legado_sin_objeto_fiscal_no_rompe():
    """Fixture armado a mano sin `dividends_gross_total`/`dividends_net_total` (no vía
    analyze_portfolio): degrada al supuesto anterior en vez de lanzar KeyError/TypeError."""
    stats = {
        "pocket_investment": 1000.0, "total_dividends": 200.0,
        "withheld_tax_total": 60.0, "market_value": 900.0,
        "dividends_collected_cash": 200.0, "dividends_collected_drip": 0.0,
    }
    datos = cashflow_data(stats, "ZZZZ")
    assert datos["NETO"] == pytest.approx(200.0, abs=0.01)
    assert datos["BRUTO"] == pytest.approx(260.0, abs=0.01)
    assert datos["CASH"] == pytest.approx(200.0, abs=0.01)


# ── verificar_identidades: guard real (no tautológico) ──────────────────────────────────────

def test_verificar_identidades_pasa_con_datos_reales_schwab(monkeypatch):
    s = _schwab_msty_stats(monkeypatch)
    datos = cashflow_data(s, "MSTY")
    assert verificar_identidades(datos, s) == []


def test_verificar_identidades_pasa_con_datos_reales_ib(monkeypatch):
    s = _ib_msty_stats(monkeypatch)
    datos = cashflow_data(s, "MSTY")
    assert verificar_identidades(datos, s) == []


def test_verificar_identidades_sin_stats_omite_el_guard_independiente(monkeypatch):
    """Compatibilidad: sin `stats` (o sin 'history' dentro), el guard independiente se omite
    y solo corren las identidades definitorias — no debe lanzar excepción."""
    s = _schwab_msty_stats(monkeypatch)
    datos = cashflow_data(s, "MSTY")
    assert verificar_identidades(datos) == []
    assert verificar_identidades(datos, stats={}) == []


def test_verificar_identidades_no_es_ciego_al_predicado_roto(monkeypatch):
    """PR C, Parte 2 (adaptado al fix de la familia `_dividend_*`): el guard debe cazar un
    objeto fiscal roto aunque la rotación venga del PREDICADO compartido. Hoy el sabotaje
    que rompe el BRUTO es apagar `_is_tax_row_action` (las filas de retención de IB vuelven
    a contarse como dividendo — el defecto A1 de la auditoría del 22-ago, +55–78% medido);
    con la detección rota, `analyze_portfolio` produce un BRUTO inflado y el guard
    (`_bruto_independiente_del_csv`, que NO pasa por el predicado compartido) debe fallar.
    Nota: sabotear `_dividend_tax_netted` ya NO rompe nada — tras el fix esa detección solo
    declara procedencia, no participa en la aritmética del bruto."""
    monkeypatch.setattr(logic, "_is_tax_row_action", lambda action: False)
    s = _ib_msty_stats_saboteada(monkeypatch)
    datos = cashflow_data(s, "MSTY")
    # Con el predicado apagado, el objeto fiscal único queda roto: las filas 'Dividend -
    # Foreign Tax Withholding' se suman dentro del ledger (el "bruto" colapsa al NETO,
    # $6,679.07) y `withheld_tax_total` deja de ver la retención ($0). Confirmamos el
    # sabotaje antes de exigirle nada al guard.
    assert datos["BRUTO"] == pytest.approx(6679.07, abs=0.01)
    assert datos["BRUTO"] != pytest.approx(7224.59, abs=0.01)   # el bruto real del CSV
    fallos = verificar_identidades(datos, s)
    assert any("CSV releído independiente" in f for f in fallos), (
        "el guard debe reportar el BRUTO inflado por el predicado roto, no pasar en silencio")


def _ib_msty_stats_saboteada(monkeypatch):
    """Como `_ib_msty_stats` pero corriendo `analyze_portfolio` CON el predicado ya
    saboteado (necesita su propia cache key — ver la nota en `_schwab_msty_stats`)."""
    base = os.path.dirname(__file__)
    csv_path = os.path.join(base, "real_examples", "interactive_brokers_data", "1",
                             "U15179613.TRANSACTIONS.20240820.20260514.csv")
    if not os.path.exists(csv_path):
        pytest.skip("real_examples/interactive_brokers_data/1 no disponible")
    with open(csv_path, "rb") as f:
        df, broker = logic.load_and_detect_csv(FakeFile(f.read(), "ib_1.csv"))
    dfc = logic.normalize_csv(df)
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    res = logic.analyze_portfolio(dfc, version="TEST_ADAPTERS_IB_SABOTAGE_PREDICADO")
    return res["MSTY"]


def test_verificar_identidades_detecta_objeto_fiscal_roto(monkeypatch):
    """El guard independiente relee el CSV desde cero (`logic._csv_dividends_in_window`) y
    debe CAZAR un BRUTO que no coincide con lo que el CSV realmente declara — a diferencia de
    las identidades definitorias (`bruto = neto + impuesto`), que no pueden fallar nunca
    porque comparan la fórmula contra sí misma."""
    s = _schwab_msty_stats(monkeypatch)
    datos = cashflow_data(s, "MSTY")
    # Sabotaje del check tautológico: BRUTO se infla a mano manteniendo la identidad interna
    # (BRUTO = NETO + IMPUESTO sigue cuadrando), así que solo el guard independiente lo caza.
    datos_rotos = dict(datos)
    datos_rotos["BRUTO"] = round(datos["NETO"] + datos["IMPUESTO"] + 100.0, 2)
    datos_rotos["IMPUESTO"] = round(datos["IMPUESTO"] + 100.0, 2)
    fallos_sin_guard = verificar_identidades(datos_rotos)          # sin stats: no lo ve
    fallos_con_guard = verificar_identidades(datos_rotos, s)       # con stats: sí lo ve
    assert fallos_sin_guard == []
    assert any("CSV releído independiente" in f for f in fallos_con_guard)


# ── El guard y el NaN: toda comparación con NaN es falsa ──────────────────────────────

def test_verificar_identidades_caza_nan_en_vez_de_pasar_en_silencio(monkeypatch):
    """El hueco que dejó abierto el traspaso 2026-08-17. `abs(nan - x) > tolerancia` es
    **False**: un NaN no rompe las identidades, las desactiva. El guard que existe para no
    dibujar algo que miente pasaba limpio justo cuando los datos estaban rotos.

    No es hipotético: yfinance devolvió cierres NaN el 2026-08-18 y `market_value` salió
    NaN. Se prueba con cada clave por separado, porque bastaba UNA para cegar el guard.
    """
    s = _schwab_msty_stats(monkeypatch)
    datos = cashflow_data(s, "MSTY")
    assert verificar_identidades(datos) == []          # sano, para no probar sobre ruido

    for clave in ("VALOR_HOY", "CAPITAL_ACTUAL", "RESULTADO", "MERCADO",
                  "TOTAL_TRABAJANDO", "BRUTO", "NETO", "IMPUESTO", "DRIP", "CASH",
                  "POCKET"):
        rotos = dict(datos)
        rotos[clave] = float("nan")
        fallos = verificar_identidades(rotos)
        assert fallos, f"un NaN en {clave} no fue reportado — el guard sigue ciego"
        assert clave in fallos[0]


def test_verificar_identidades_caza_infinito_y_none(monkeypatch):
    """±inf sí dispararía las restas, pero el mensaje sería «inf ≠ inf» en vez de decir qué
    pasó; y un `None` reventaba con TypeError. Los dos son «no es un número», y el guard
    tiene que nombrarlos igual que al NaN."""
    s = _schwab_msty_stats(monkeypatch)
    datos = cashflow_data(s, "MSTY")
    for valor in (float("inf"), float("-inf"), None):
        rotos = dict(datos)
        rotos["VALOR_HOY"] = valor
        fallos = verificar_identidades(rotos)
        assert fallos and "VALOR_HOY" in fallos[0], f"{valor!r} no fue reportado"


def test_el_guard_de_nan_no_le_gana_al_guard_de_convencion(monkeypatch):
    """La comprobación de finitud va ANTES y devuelve de inmediato — pero solo debe
    dispararse cuando hay una cifra no numérica. Con datos sanos y el predicado de fila-de-
    impuesto roto (BRUTO inflado), el fallo que se reporta tiene que seguir siendo el del
    CSV releído, no un falso NaN."""
    monkeypatch.setattr(logic, "_is_tax_row_action", lambda action: False)
    s = _ib_msty_stats_saboteada(monkeypatch)
    datos = cashflow_data(s, "MSTY")
    fallos = verificar_identidades(datos, s)
    assert any("CSV releído independiente" in f for f in fallos)
    assert not any("no numérica" in f for f in fallos)


# ── efectivo no distributivo (Cash In Lieu y compañía) ──────────────────────────────────────
#
# La forma real del CSV que destapó el defecto (MSTY de Schwab, 2026-09-24): el split
# inverso liquida la fracción de acción y paga «Cash In Lieu». Ese dinero entraba a
# `dividends_collected_cash` —el balde del dividendo— y hacía que `DRIP + CASH` superara
# al NETO del objeto fiscal en exactamente esa cifra. El guard hacía lo correcto:
# bloqueaba Cash flow y Hoja Excel.
_CSV_LIEU = (
    b'"Transactions for account XXXX-1234","","","","","","",""\n'
    b'"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"\n'
    b'"03/01/2025","Buy","MSTY","YIELDMAX MSTY","100","20.00","","-2000.00"\n'
    b'"04/11/2025","Reinvest Dividend","MSTY","YIELDMAX MSTY","","","","100.00"\n'
    b'"04/11/2025","NRA Tax Adj","MSTY","YIELDMAX MSTY","","","","-30.00"\n'
    b'"04/11/2025","Reinvest Shares","MSTY","YIELDMAX MSTY","3.5","20.00","","-70.00"\n'
    b'"05/09/2025","Cash Dividend","MSTY","YIELDMAX MSTY","","","","50.00"\n'
    b'"05/09/2025","NRA Tax Adj","MSTY","YIELDMAX MSTY","","","","-15.00"\n'
    b'"06/06/2025","Cash In Lieu","MSTY","YIELDMAX MSTY","","","","18.32"\n'
)


def _stats_lieu(monkeypatch, version="TEST_ADAPTERS_LIEU"):
    df, broker = logic.load_and_detect_csv(FakeFile(_CSV_LIEU, "lieu.csv"))
    assert broker == "schwab"
    dfc = logic.normalize_csv(df)
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    return logic.analyze_portfolio(dfc, version=version)["MSTY"]


def test_el_efectivo_del_split_no_entra_en_el_balde_del_dividendo(monkeypatch):
    """Bruto $150, retención $45, neto $105 = DRIP $70 + efectivo $35. El Cash In Lieu
    ($18.32) va aparte, en OTROS — si se cuela en CASH, la identidad se rompe por su
    importe exacto, que es el bug real que se vio en producción."""
    s = _stats_lieu(monkeypatch)
    datos = cashflow_data(s, "MSTY")
    assert datos["NETO"] == pytest.approx(105.00, abs=0.01)
    assert datos["DRIP"] == pytest.approx(70.00, abs=0.01)
    assert datos["CASH"] == pytest.approx(35.00, abs=0.01)
    assert datos["OTROS"] == pytest.approx(18.32, abs=0.01)
    assert datos["OTROS_DETALLE"] == {"Cash In Lieu": 18.32}
    assert verificar_identidades(datos, s) == []


def test_el_efectivo_del_split_sigue_contando_en_el_capital_actual(monkeypatch):
    """Sacarlo del dividendo no puede perderlo: es dinero que está en la cuenta. Gate de
    Regla 3b — el RESULTADO del recorrido contra el `net_profit` del motor, dos fuentes
    independientes del mismo número."""
    s = _stats_lieu(monkeypatch)
    datos = cashflow_data(s, "MSTY")
    assert datos["CAPITAL_ACTUAL"] == pytest.approx(
        datos["VALOR_HOY"] + 35.00 + 18.32, abs=0.01)
    assert datos["RESULTADO"] == pytest.approx(s["net_profit"], abs=0.01)


def test_el_guard_caza_el_efectivo_no_distributivo_de_vuelta_en_el_dividendo(monkeypatch):
    """Mutante = el bug original: devolver el Cash In Lieu a `CASH`. El guard debe
    reportarlo, y por el importe exacto."""
    s = _stats_lieu(monkeypatch, version="TEST_ADAPTERS_LIEU_MUT")
    # El mutante se aplica sobre los STATS —el estado exacto que producía el motor antes
    # del fix: el Cash In Lieu dentro del efectivo del dividendo, y ningún balde propio—
    # y se deja pasar por `cashflow_data`, en vez de retocar su salida.
    mutados = dict(s)
    mutados["dividends_cash_net"] = round(s["dividends_cash_net"] + s["misc_cash_total"], 2)
    mutados["misc_cash_total"] = 0.0
    fallos = verificar_identidades(cashflow_data(mutados, "MSTY"), mutados)
    assert any("neto = reinvertido + efectivo" in f for f in fallos), fallos
    # 105.00 de neto contra 70.00 de DRIP + 53.32 de «efectivo» con el Cash In Lieu dentro.
    assert any("105.00 ≠ 123.32" in f for f in fallos), fallos


def test_sin_efectivo_no_distributivo_otros_es_cero(monkeypatch):
    """Control: el CSV sin filas I5 no inventa un OTROS — y el capital actual queda
    idéntico a como estaba antes del cambio."""
    s = _schwab_msty_stats(monkeypatch, version="TEST_ADAPTERS_SIN_LIEU")
    datos = cashflow_data(s, "MSTY")
    assert datos["OTROS"] == 0.0
    assert datos["OTROS_DETALLE"] == {}
    assert datos["CAPITAL_ACTUAL"] == pytest.approx(datos["VALOR_HOY"] + datos["CASH"], abs=0.01)
    assert verificar_identidades(datos, s) == []


# ── el aviso de bloqueo dice QUÉ le falta al export ─────────────────────────────────────────
#
# Los 9 bloqueos que quedaban el 2026-09-24 tras el #143 tienen todos la misma causa, y NO es
# un error de cálculo: al export le faltan las filas `Reinvest Dividend` que respaldan las
# compras del DRIP. El guard tenía razón; el mensaje no servía para actuar.
_CSV_DRIP_SIN_FUENTE = (
    b'"Transactions for account XXXX-1234","","","","","","",""\n'
    b'"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"\n'
    b'"03/01/2025","Buy","MSTY","YIELDMAX MSTY","100","20.00","","-2000.00"\n'
    b'"04/11/2025","Reinvest Dividend","MSTY","YIELDMAX MSTY","","","","100.00"\n'
    b'"04/11/2025","Reinvest Shares","MSTY","YIELDMAX MSTY","5","20.00","","-100.00"\n'
    # Estas dos compras no traen su distribución: el archivo empieza tarde.
    b'"05/09/2025","Reinvest Shares","MSTY","YIELDMAX MSTY","2","20.00","","-40.00"\n'
    b'"06/06/2025","Reinvest Shares","MSTY","YIELDMAX MSTY","1.5","20.00","","-30.00"\n'
)


def _stats_drip_sin_fuente(monkeypatch, version="TEST_ADAPTERS_DRIPSF"):
    df, _ = logic.load_and_detect_csv(FakeFile(_CSV_DRIP_SIN_FUENTE, "dripsf.csv"))
    dfc = logic.normalize_csv(df)
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    return logic.analyze_portfolio(dfc, version=version)["MSTY"]


def test_el_aviso_nombra_las_filas_que_faltan_y_su_importe(monkeypatch):
    """Las dos cifras del aviso salen del CSV, no de una plantilla: 3 compras contra 1
    distribución, 2 huérfanas, $70.00 sin respaldo."""
    from ui.adapters import diagnosticar_bloqueo
    s = _stats_drip_sin_fuente(monkeypatch)
    datos = cashflow_data(s, "MSTY")
    fallos = verificar_identidades(datos, s)
    assert fallos, "el fixture debe bloquear, si no el aviso no se prueba"
    dx = diagnosticar_bloqueo(datos, s, fallos)
    texto = " ".join([dx["titular"]] + dx["cuerpo"])
    assert "le faltan filas" in dx["titular"]
    assert "3 compras" in texto and "1 distribución" in texto   # singular, no "1 distribuciones"
    assert "$70.00" in texto
    assert dx["nuestro"] is False
    assert "History" in dx["accion"]


def test_el_aviso_no_culpa_al_export_cuando_la_culpa_es_del_motor(monkeypatch):
    """Si lo que falla es el guard independiente (el CSV releído contra el bruto del
    motor), el descuadre es NUESTRO: el aviso pide que lo reporten en vez de mandar al
    cliente a pedirle datos a su bróker."""
    from ui.adapters import diagnosticar_bloqueo
    monkeypatch.setattr(logic, "_is_tax_row_action", lambda action: False)
    s = _ib_msty_stats_saboteada(monkeypatch)
    datos = cashflow_data(s, "MSTY")
    fallos = verificar_identidades(datos, s)
    dx = diagnosticar_bloqueo(datos, s, fallos)
    assert dx["nuestro"] is True
    assert "fallo nuestro" in dx["titular"]
    assert "bróker" not in " ".join(dx["cuerpo"])


def test_el_aviso_nombra_el_bolsillo_negativo_como_historial_que_falta():
    """Ventas sin las compras que las originaron: el capital aportado sale negativo. Es
    otra cara del mismo archivo incompleto, y se dice aparte."""
    from ui.adapters import diagnosticar_bloqueo
    datos = {"POCKET": -2439.63, "DRIP": 583.76, "CASH": 0.0, "NETO": 137.29, "OTROS": 0.0}
    fallos = ["neto = reinvertido + efectivo: 137.29 ≠ 583.76", "bolsillo negativo: -2439.63"]
    dx = diagnosticar_bloqueo(datos, {"history": None}, fallos)
    cuerpo = " ".join(dx["cuerpo"])
    assert "negativo" in cuerpo and "-2,439.63" in cuerpo
    assert "ventas sin las compras" in cuerpo


def test_una_causa_desconocida_no_se_disfraza_de_export_incompleto():
    """Sin filas huérfanas ni bolsillo negativo, el aviso NO inventa una causa: dice que
    no la reconoce y manda a reportar. El mutante que hace esto fallar es cualquiera que
    devuelva el texto del export por defecto."""
    from ui.adapters import diagnosticar_bloqueo
    datos = {"POCKET": 100.0, "DRIP": 0.0, "CASH": 0.0, "NETO": 50.0, "OTROS": 0.0}
    dx = diagnosticar_bloqueo(datos, {"history": None}, ["capital actual = valor hoy + efectivo + otros: 1.00 ≠ 2.00"])
    assert dx["nuestro"] is True
    assert "no cuadran entre sí" in dx["titular"]
    assert "export" not in dx["titular"]


_CSV_DOS_COMPRAS_UN_DIA = (
    b'"Transactions for account XXXX-1234","","","","","","",""\n'
    b'"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"\n'
    b'"03/01/2025","Buy","MSTY","YIELDMAX MSTY","100","20.00","","-2000.00"\n'
    b'"04/11/2025","Reinvest Dividend","MSTY","YIELDMAX MSTY","","","","100.00"\n'
    b'"04/11/2025","Reinvest Shares","MSTY","YIELDMAX MSTY","5","20.00","","-100.00"\n'
    b'"05/09/2025","Reinvest Dividend","MSTY","YIELDMAX MSTY","","","","60.00"\n'
    b'"05/09/2025","Reinvest Shares","MSTY","YIELDMAX MSTY","2","20.00","","-40.00"\n'
    b'"05/09/2025","Reinvest Shares","MSTY","YIELDMAX MSTY","1","20.00","","-20.00"\n'
    b'"06/06/2025","Reinvest Shares","MSTY","YIELDMAX MSTY","1.5","20.00","","-30.00"\n'
)


def test_las_huerfanas_se_cuentan_por_dia_no_por_total_de_filas():
    """La forma de TSLY del caso 1: un día con DOS compras y UNA distribución. Por conteo
    global salen 2 huérfanas (4 compras − 2 fuentes); por día sale **1**, la del 06/06, y
    su importe es $30.00, no $50.00. El criterio por día es el único que puede decir
    cuánto dinero queda sin respaldo — que es lo que el aviso promete."""
    df, _ = logic.load_and_detect_csv(FakeFile(_CSV_DOS_COMPRAS_UN_DIA, "dosc.csv"))
    dfc = logic.normalize_csv(df)
    h = logic.drip_huerfanas(dfc[dfc["Ticker"] == "MSTY"])
    assert h == {"compras": 4, "fuentes": 2, "huerfanas": 1, "importe": 30.00}, h


def test_el_titular_nombra_lo_que_no_se_dibuja(monkeypatch):
    """El mismo aviso sirve a dos vistas, así que el sujeto se pasa: «Este recorrido» en
    Cash flow, «Esta hoja» en la Hoja Excel. (De la segunda no hay test de render: hoy
    `ui.chrome._orden` deja las categorías de fondos con una sola sección —«viaje»—, así
    que la Hoja Excel existe pero no es navegable en la app.)"""
    from ui.adapters import diagnosticar_bloqueo
    s = _stats_drip_sin_fuente(monkeypatch, version="TEST_ADAPTERS_SUJETO")
    datos = cashflow_data(s, "MSTY")
    fallos = verificar_identidades(datos, s)
    assert diagnosticar_bloqueo(datos, s, fallos)["titular"].startswith("Este recorrido")
    assert diagnosticar_bloqueo(datos, s, fallos, sujeto="Esta hoja")["titular"].startswith("Esta hoja")
