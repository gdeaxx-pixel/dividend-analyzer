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
