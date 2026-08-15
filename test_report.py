"""Tests del PDF (report.py).

Regresión: las fuentes core de fpdf2 solo codifican latin-1, así que cualquier
em-dash / comilla tipográfica / flecha en los textos (o en datos dinámicos)
rompía generate_report_pdf por completo. Ver _lat1() en report.py.
"""
import report
from report import generate_report_pdf, _lat1, _PDF


def _fake_results():
    """Resultados mínimos con un fondo YieldMax (Modo A) y un ETF (Modo B)."""
    return {
        "MSTY": {
            "pocket_investment": 2000.0, "market_value": 1200.0,
            "dividends_collected_cash": 400.0, "ticker_mode": "mode_a",
            "roc_accumulated": 191.0, "roc_source": "19a", "ib_cost_basis": 1800.0,
        },
        "SCHB": {
            "pocket_investment": 1000.0, "market_value": 1300.0,
            "dividends_collected_cash": 20.0, "ticker_mode": "mode_b",
        },
    }


def test_lat1_mapea_caracteres_unicode():
    assert _lat1("ROC — fiscal") == "ROC - fiscal"
    assert _lat1("“hola” ‘mundo’") == '"hola" \'mundo\''
    assert _lat1("a → b … c") == "a -> b ... c"
    # Cualquier carácter exótico no mapeado no debe explotar (se sustituye).
    assert "☃" not in _lat1("nieve ☃")


def test_pdf_se_genera_sin_crashear_con_emdash():
    """Antes del fix, el em-dash de la nota y de los títulos MODO A/B rompía el PDF."""
    pdf = generate_report_pdf(_fake_results(), "ibkr", version="2.0")
    assert isinstance(pdf, (bytes, bytearray))
    assert len(pdf) > 1000
    assert pdf[:4] == b"%PDF"


def test_pdf_usa_efectivo_real_pocket_investment():
    """El 'Total Invertido' del PDF debe ser la suma de pocket_investment (capital real),
    no la base de coste reducida por ROC del broker."""
    captured = {}
    orig = _PDF._row

    def _spy_row(self, label, value, **kw):
        captured[label] = value
        return orig(self, label, value, **kw)

    _PDF._row = _spy_row
    try:
        generate_report_pdf(_fake_results(), "ibkr", version="2.0")
    finally:
        _PDF._row = orig
    # 2000 (MSTY, efectivo real, NO 1800 del broker) + 1000 (SCHB) = 3000
    assert captured.get("Total Invertido") == "$3,000.00"


def _fake_results_schwab_style():
    """Como `_fake_results`, pero con la asimetría Schwab real: `dividends_collected_cash`
    trae el BRUTO (462.0, retención en fila aparte que ese campo nunca ve) y
    `dividends_net_total` — el objeto fiscal único, `logic.build_dividend_tax_totals` — trae
    el NETO correcto (323.40, retención $138.60). Ground truth de `fixtures/schwab_synth_2`
    MSTY (ver test_logic.py)."""
    res = _fake_results()
    res["MSTY"]["dividends_net_total"] = 323.40
    res["MSTY"]["dividends_gross_total"] = 462.00
    return res


def test_pdf_dividendos_neto_impuestos_es_realmente_neto():
    """PR C, Parte 3: `report.py:226,291` rotulan la cifra "(neto impuestos)" — antes leían
    `dividends_collected_cash`, que para Schwab es BRUTO ($462.00, la retención vive en una
    fila aparte que ese campo nunca resta). La etiqueta prometía neto y mostraba bruto. Ahora
    debe leer `dividends_net_total` (el objeto fiscal único) y mostrar $323.40 — y ese mismo
    número debe alimentar Retorno Total/ROI (Parte 1: la retención no puede desaparecer de
    ninguno de los dos)."""
    captured = {}  # label -> lista de valores (la fila por-ticker se repite, una por página)
    orig = _PDF._row

    def _spy_row(self, label, value, **kw):
        captured.setdefault(label, []).append(value)
        return orig(self, label, value, **kw)

    _PDF._row = _spy_row
    try:
        generate_report_pdf(_fake_results_schwab_style(), "schwab", version="2.0")
    finally:
        _PDF._row = orig
    # Resumen global: 323.40 (MSTY, objeto fiscal único) + 20 (SCHB, sin objeto fiscal -> degrada al crudo)
    assert captured.get("Dividendos Cobrados (neto impuestos)") == ["$343.40"]
    # Página por ticker: MSTY primero (Modo A), SCHB después (Modo B)
    assert captured.get("Dividendos Efectivo (neto impuestos)") == ["$323.40", "$20.00"]


def test_pdf_unicode_dinamico_en_ticker_no_crashea():
    """Si un dato dinámico trae un carácter unicode, tampoco debe romper el export."""
    res = _fake_results()
    res["MSTY"]["company_name"] = "Tesla — Option Income"  # campo arbitrario con em-dash
    pdf = generate_report_pdf(res, "ibkr", version="2.0")
    assert pdf[:4] == b"%PDF"
