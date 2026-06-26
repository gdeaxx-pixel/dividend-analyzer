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


def test_pdf_unicode_dinamico_en_ticker_no_crashea():
    """Si un dato dinámico trae un carácter unicode, tampoco debe romper el export."""
    res = _fake_results()
    res["MSTY"]["company_name"] = "Tesla — Option Income"  # campo arbitrario con em-dash
    pdf = generate_report_pdf(res, "ibkr", version="2.0")
    assert pdf[:4] == b"%PDF"
