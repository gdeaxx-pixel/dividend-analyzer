"""Tarea 1 (2026-08-23) — test cruzado de base mixta en `ui/heredadas.py`.

Regla 3b del contrato (`specs/roc-nra-invariants.md`): todo eje con más de una vista
necesita un test que compare DOS VISTAS DEL MISMO NÚMERO entre sí. Las vistas aquí son:

  1. `_resumen_consolidado` («Dividendos cobrados» y el ROI del TOTAL)
  2. `_cuadricula_roc_consolidada` («Div. pagados (neto)» / «En efectivo»)
  3. `logic.build_dividend_tax_totals` (el objeto fiscal único, re-derivado directo del CSV)

El fixture es MIXTO Schwab+IB: un portafolio de un solo bróker NO vale — así nació el
test mentiroso del A1 (verde meses con el defecto vivo porque su fixture era solo-Schwab).
Se construye uniendo las transacciones normalizadas de `fixtures/schwab_synth_2`
(Schwab: retención en fila aparte, Action 'NRA Tax Adj', sin la palabra dividend) con las
de `fixtures/ib_synth_1` (IB: retención PLEGADA en la fila
'Dividend - Foreign Tax Withholding'), sin solapamiento de tickers.

Criterio de aceptación exacto (en los DOS brókers):

    neto − (drip + efectivo) == 0

Hoy (con el bug) da == −withheld en Schwab.
"""

import os

import pandas as pd
import pytest

import logic
from ui.heredadas import _agregados, _resumen_consolidado, _tarjeta_retorno_total


class FakeFile:
    def __init__(self, content: bytes, name: str = "test.csv"):
        import io
        self._buf = io.BytesIO(content)
        self.name = name

    def read(self):
        return self._buf.read()

    def seek(self, n):
        self._buf.seek(n)


_MKT_MOCK = lambda t, d: (pd.DataFrame({"Close": [20.0], "Dividends": [0.0], "Stock Splits": [0.0]},
                                       index=[pd.Timestamp("2024-10-15")]), None)


def _df_broker(fixture_dir, csv_name):
    raw = open(os.path.join(os.path.dirname(__file__), "fixtures", fixture_dir,
                            csv_name), "rb").read()
    df, broker = logic.load_and_detect_csv(FakeFile(raw, f"{fixture_dir}.csv"))
    return logic.normalize_csv(df), broker


def _resultados_mixtos(monkeypatch):
    """analyze_portfolio sobre Schwab synth_2 + IB synth_1 concatenados (tickers disjuntos)."""
    df_s, broker_s = _df_broker("schwab_synth_2", "synthetic_transactions.csv")
    assert broker_s == "schwab"
    df_i, broker_i = _df_broker("ib_synth_1", "synthetic_transactions.csv")
    assert broker_i == "ibkr"

    # columnas comunes, para no inventar nada: intersección preservando orden de schwab
    cols = [c for c in df_s.columns if c in df_i.columns]
    mixto = pd.concat([df_s[cols], df_i[cols]], ignore_index=True)

    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    results = logic.analyze_portfolio(mixto, version="TEST_BASE_MIXTA")
    return results, mixto


def _filas_ticker(mixto: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Sub-DataFrame del CSV mixto con SOLO las filas de este ticker (para correr
    `build_dividend_tax_totals` de verdad sobre la vista 3, no leer stats)."""
    return mixto[mixto["Ticker"] == ticker]


def test_base_mixta_resumen_cuadricula_y_objeto_fiscal_coinciden(monkeypatch):
    """Regla 3b: resumen consolidado == cuadrícula ROC == build_dividend_tax_totals,
    ticker a ticker y en TOTAL, sobre fixture MIXTO Schwab+IB."""
    results, mixto = _resultados_mixtos(monkeypatch)

    schwab_tickers = ["MSTY", "SCHB"]
    ib_tickers = ["NVDY", "CONY", "SMH"]
    todos = schwab_tickers + ib_tickers
    for t in todos:
        assert t in results, f"{t} debe sobrevivir analyze_portfolio en el fixture mixto"
        assert results[t].get("dividends_net_total") is not None, (
            f"{t}: el objeto fiscal único no llegó a stats — el fallback legado "
            "invalidaría este test")

    # ── vista 1: _resumen_consolidado (spy del dataframe que le pasa a streamlit) ──
    import ui.heredadas as heredadas_mod
    capturado = {}

    def _spy_dataframe(df_arg, *args, **kwargs):
        capturado["df"] = df_arg

    monkeypatch.setattr(heredadas_mod.st, "dataframe", _spy_dataframe)
    monkeypatch.setattr(heredadas_mod.st, "markdown", lambda *a, **k: None)
    monkeypatch.setattr(heredadas_mod.st, "caption", lambda *a, **k: None)

    rows = [(t, results[t]) for t in schwab_tickers]
    _resumen_consolidado(rows)
    fila_total = capturado["df"][capturado["df"]["Ticker"] == "TOTAL"].iloc[0]
    total_div_resumen = float(fila_total["Dividendos cobrados"]
                              .replace("$", "").replace(",", ""))

    # contra el objeto fiscal único (vista 3), mismo alcance (solo los de rows):
    # build_dividend_tax_totals corre DE VERDAD sobre las filas del ticker re-filtradas
    # desde el CSV mixto — no se lee `dividends_net_total` de stats (eso sería comparar
    # la vista consigo misma)
    esperado = sum(logic.build_dividend_tax_totals(_filas_ticker(mixto, t))["net"]
                   for t in schwab_tickers)
    assert total_div_resumen == pytest.approx(esperado, abs=0.01), (
        "el TOTAL del resumen consolidado diverge del objeto fiscal único "
        "(build_dividend_tax_totals corrido directo sobre el CSV)")
    for t in schwab_tickers:
        assert results[t]["dividends_net_total"] == pytest.approx(
            logic.build_dividend_tax_totals(_filas_ticker(mixto, t))["net"], abs=0.01), (
            f"{t}: stats y el objeto re-derivado del CSV divergen")

    # ── vista 2 (jubilada): _cuadricula_roc_consolidada se podó de `ui/heredadas.py`
    # con las vistas Ingresos/Proyección/Estrategias de Detalle (2026-08-25). La
    # identidad neto = bruto − retención sigue vigilada contra el objeto fiscal único
    # (en Schwab `dividends_collected_cash` es BRUTO: la retención vive aparte): ──
    for t in todos:
        neto = results[t]["dividends_net_total"]
        bruto = results[t]["dividends_gross_total"]
        retencion = results[t]["withheld_tax_total"]
        assert neto == pytest.approx(bruto - retencion, abs=0.005), (
            f"{t} ({'Schwab' if t in schwab_tickers else 'IB'}): "
            f"neto {neto} != bruto {bruto} − retención {retencion} — base mixta viva")


def test_base_mixta_roi_consolidado_resta_retencion_schwab(monkeypatch):
    """El ROI del TOTAL consolidado ya no infla con la retención NRA de Schwab.
    Pasa POR LA VISTA REAL (`_resumen_consolidado`, spy del dataframe): revertir el fix
    de A2 tiene que dejar este test ROJO, no solo al de identidad. El retorno mostrado
    es exactamente `retención_total` más negativo que el de la suma bruta — ni más ni
    menos (patrón de test_agregados_schwab_resta_retencion_nra_en_retorno_total)."""
    results, _mixto = _resultados_mixtos(monkeypatch)

    schwab_tickers = ["MSTY", "SCHB"]
    rows = [(t, results[t]) for t in schwab_tickers]

    import ui.heredadas as heredadas_mod
    capturado = {}

    def _spy_dataframe(df_arg, *args, **kwargs):
        capturado["df"] = df_arg

    monkeypatch.setattr(heredadas_mod.st, "dataframe", _spy_dataframe)
    monkeypatch.setattr(heredadas_mod.st, "markdown", lambda *a, **k: None)
    monkeypatch.setattr(heredadas_mod.st, "caption", lambda *a, **k: None)

    _resumen_consolidado(rows)
    fila_total = capturado["df"][capturado["df"]["Ticker"] == "TOTAL"].iloc[0]

    def _num(celda):
        return float(str(celda).replace("$", "").replace(",", ""))

    inv_vista = _num(fila_total["Tu inversión"])
    mv_vista = _num(fila_total["Valor mercado"])
    div_vista = _num(fila_total["Dividendos cobrados"])
    tr_vista = mv_vista + div_vista - inv_vista

    # lo que mostraba la vista con el bug (suma bruta), reconstruido de stats
    div_bruto_buggy = sum(s.get("dividends_collected_cash", 0) for _, s in rows)
    tr_buggy = mv_vista + div_bruto_buggy - inv_vista

    retencion = sum(results[t]["dividends_gross_total"] - results[t]["dividends_net_total"]
                    for t in schwab_tickers)
    assert retencion > 0, "el fixture Schwab debe traer retención para que el test muerda"

    assert div_vista == pytest.approx(div_bruto_buggy - retencion, abs=0.01), (
        "«Dividendos cobrados» del TOTAL no restó exactamente la retención Schwab")
    assert round(tr_buggy - tr_vista, 2) == pytest.approx(retencion, abs=0.01), (
        "el ROI del TOTAL mostrado por la vista no baja exactamente la retención")


def test_resumen_sin_objeto_fiscal_degrada_al_campo_crudo():
    """Fallback legado intacto: stats sin `dividends_net_total` (no pasaron por
    analyze_portfolio) usan `dividends_collected_cash`, igual que `_agregados`."""
    stats = {"pocket_investment": 100.0, "market_value": 120.0,
             "shares_owned": 1.0, "roi_percent": 20.0,
             "dividends_collected_cash": 30.0, "net_profit": 45.0}
    import ui.heredadas as heredadas_mod
    capturado = {}

    def _spy_dataframe(df_arg, *args, **kwargs):
        capturado["df"] = df_arg

    orig_df, orig_md, orig_cap = (heredadas_mod.st.dataframe, heredadas_mod.st.markdown,
                                  heredadas_mod.st.caption)
    heredadas_mod.st.dataframe = _spy_dataframe
    heredadas_mod.st.markdown = lambda *a, **k: None
    heredadas_mod.st.caption = lambda *a, **k: None
    try:
        _resumen_consolidado([("X", stats), ("Y", dict(stats))])
    finally:
        heredadas_mod.st.dataframe, heredadas_mod.st.markdown, heredadas_mod.st.caption = (
            orig_df, orig_md, orig_cap)

    fila_total = capturado["df"][capturado["df"]["Ticker"] == "TOTAL"].iloc[0]
    assert fila_total["Dividendos cobrados"] == "$60.00"  # 30 + 30, campo crudo


def test_resumen_ignora_posiciones_skipped_sin_net_profit(monkeypatch):
    """E1 indexa `s["net_profit"]` directo (regla: si una ruta nueva entrega stats sin
    `net_profit`, se quiere un error, no un número equivocado en pantalla). Esto exige que
    `_tiene_datos` (ui/adapters.py) filtre las posiciones `skipped` ANTES de llegar aquí —
    un `skipped` solo trae `skipped`/`reason`/`ticker`, nunca `net_profit`."""
    from ui.adapters import _tiene_datos

    resultados = {
        "X": {"pocket_investment": 100.0, "market_value": 120.0, "shares_owned": 1.0,
              "roi_percent": 20.0, "dividends_collected_cash": 30.0, "net_profit": 45.0},
        "Y": {"pocket_investment": 200.0, "market_value": 240.0, "shares_owned": 2.0,
              "roi_percent": 20.0, "dividends_collected_cash": 60.0, "net_profit": 90.0},
        "SKIP": {"skipped": True, "reason": "held_less_than_14_days", "ticker": "SKIP"},
    }
    rows = [(t, resultados[t]) for t in resultados if _tiene_datos(resultados.get(t))]
    assert sorted(t for t, _ in rows) == ["X", "Y"]  # SKIP quedó fuera

    import ui.heredadas as heredadas_mod
    monkeypatch.setattr(heredadas_mod.st, "dataframe", lambda *a, **k: None)
    monkeypatch.setattr(heredadas_mod.st, "markdown", lambda *a, **k: None)
    monkeypatch.setattr(heredadas_mod.st, "caption", lambda *a, **k: None)
    _resumen_consolidado(rows)  # no debe reventar con KeyError: 'net_profit'


def test_e1_retorno_total_de_cartera_es_la_suma_de_net_profit(monkeypatch):
    """C·1/E1: el titular de cartera (`_agregados`) ya no cuenta el DRIP dos veces —
    el total es la suma de `net_profit` del motor, no `mv + neto - inv`. El fixture
    mixto no trae DRIP real, así que se fuerza un `net_profit` distinto de
    `mv + div - pk` en una posición (simula lo que hace el DRIP: mv ya incluye las
    acciones reinvertidas) para probar que el código LEE net_profit y no recalcula."""
    results, _mixto = _resultados_mixtos(monkeypatch)
    todos = ["MSTY", "SCHB", "NVDY", "CONY", "SMH"]
    results["MSTY"]["net_profit"] = results["MSTY"]["net_profit"] + 500.0  # divergencia forzada

    inv, mv, div, tr, pct = _agregados(results, todos)

    esperado = sum(results[t]["net_profit"] for t in todos)
    formula_vieja = mv + div - inv
    assert tr == pytest.approx(esperado, abs=0.01)
    assert tr != pytest.approx(formula_vieja, abs=0.01), (
        "el total sigue siendo mv + div - inv, no net_profit")
    assert pct == pytest.approx(esperado / inv * 100, abs=0.01)


def test_e1_tarjeta_de_posicion_es_net_profit(monkeypatch):
    """C·1/E1: la tarjeta por posición (`_tarjeta_retorno_total`) publica `net_profit`,
    no `mv + neto - pk` (que cuenta el DRIP dos veces). Se fuerza un `net_profit`
    distinto de `mv + neto - pk` para probar que el código lo lee, no lo recalcula."""
    results, _mixto = _resultados_mixtos(monkeypatch)
    stats = results["MSTY"]
    stats["net_profit"] = stats["net_profit"] + 500.0  # divergencia forzada

    import ui.heredadas as heredadas_mod
    capturado = []
    monkeypatch.setattr(heredadas_mod.st, "markdown", lambda html, **k: capturado.append(html))

    _tarjeta_retorno_total(stats)

    texto_esperado = f'${stats["net_profit"]:,.2f}'  # `_money` formatea negativos como "$-X"
    assert any(texto_esperado in html for html in capturado), (
        f"la tarjeta no publicó {texto_esperado!r} (net_profit); capturado: {capturado[:1]}")


def test_e1_resumen_consolidado_es_la_suma_de_net_profit(monkeypatch):
    """C·1/E1: el TOTAL de `_resumen_consolidado` es la suma de `net_profit`, no
    `mv + div - inv`. Se fuerza una divergencia en una posición para probarlo."""
    results, _mixto = _resultados_mixtos(monkeypatch)
    schwab_tickers = ["MSTY", "SCHB"]
    results["MSTY"]["net_profit"] = results["MSTY"]["net_profit"] + 500.0
    rows = [(t, results[t]) for t in schwab_tickers]

    import ui.heredadas as heredadas_mod
    capturado = {}
    monkeypatch.setattr(heredadas_mod.st, "dataframe", lambda df, *a, **k: capturado.__setitem__("df", df))
    monkeypatch.setattr(heredadas_mod.st, "markdown", lambda *a, **k: None)
    monkeypatch.setattr(heredadas_mod.st, "caption", lambda *a, **k: None)

    _resumen_consolidado(rows)

    fila_total = capturado["df"][capturado["df"]["Ticker"] == "TOTAL"].iloc[0]

    def _num(celda):
        return float(str(celda).replace("$", "").replace(",", ""))

    inv_vista = _num(fila_total["Tu inversión"])
    mv_vista = _num(fila_total["Valor mercado"])
    div_vista = _num(fila_total["Dividendos cobrados"])
    roi_vista = float(str(fila_total["ROI total"]).replace("%", "").replace("+", ""))

    esperado = sum(results[t]["net_profit"] for t in schwab_tickers)
    roi_esperado = esperado / inv_vista * 100
    roi_viejo = (mv_vista + div_vista - inv_vista) / inv_vista * 100

    assert roi_vista == pytest.approx(roi_esperado, abs=0.01), (
        "el ROI total del consolidado no es la suma de net_profit")
    assert roi_esperado != pytest.approx(roi_viejo, abs=0.01), (
        "el total sigue siendo mv + div - inv, no net_profit")


def test_e1_capital_mas_income_es_el_total(monkeypatch):
    """G2: Capital + Income == Total al centavo, en las dos convenciones de bróker
    (Schwab y IB) y con DRIP real en el fixture (MSTY trae DRIP)."""
    results, _mixto = _resultados_mixtos(monkeypatch)

    import ui.heredadas as heredadas_mod
    for ticker in ("MSTY", "SCHB", "NVDY", "CONY", "SMH"):
        stats = results[ticker]
        capturado = []
        monkeypatch.setattr(heredadas_mod.st, "markdown", lambda html, **k: capturado.append(html))
        _tarjeta_retorno_total(stats)

        total = stats["net_profit"]
        inc = (stats.get("dividends_net_total") if stats.get("dividends_net_total") is not None
               else stats.get("dividends_collected_cash", 0))
        cap = total - inc
        assert cap + inc == pytest.approx(total, abs=0.005), (
            f"{ticker}: Capital + Income != Total")
