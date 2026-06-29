"""Tests del parser de fetch_roc_19a (sin navegador): valida la extracción de la tabla
de distribuciones renderizada y el cálculo de weighted_pct."""
import fetch_roc_19a as f


_HTML = """
<html><body>
<table><tr><th>Holdings</th><th>Weight</th></tr><tr><td>MSTR</td><td>5%</td></tr></table>
<table>
  <tr><th>Ex-Date</th><th>Distribution Amount</th><th>ROC %</th><th>Income %</th></tr>
  <tr><td>05/07/2026</td><td>$0.5553</td><td>99.10%</td><td>0.90%</td></tr>
  <tr><td>06/11/2026</td><td>$0.2117</td><td>0.00%</td><td>100.00%</td></tr>
  <tr><td>05/07/2026</td><td>$0.5553</td><td>99.10%</td><td>0.90%</td></tr>
</table>
</body></html>
"""


def test_parser_extracts_roc_table():
    rows = f.parse_distributions_from_html(_HTML)
    # dedup por fecha (la fila repetida del 05/07 se colapsa) y solo la tabla con ROC+date
    dates = {d for d, _, _ in rows}
    assert dates == {"2026-05-07", "2026-06-11"}
    by_date = {d: (p, a) for d, p, a in rows}
    assert by_date["2026-05-07"][0] == 99.10
    assert by_date["2026-06-11"][0] == 0.00
    assert by_date["2026-05-07"][1] == 0.5553


def test_parser_ignores_table_without_roc():
    html = "<table><tr><th>Date</th><th>Price</th></tr><tr><td>2026-01-01</td><td>$10</td></tr></table>"
    assert f.parse_distributions_from_html(html) == []


def test_build_entry_weighted_by_amount():
    rows = [("2026-05-07", 99.10, 0.5553), ("2026-06-11", 0.00, 0.2117)]
    entry = f.build_entry("MSTY", rows)
    # ponderado por monto: 0.5553*99.10 / (0.5553+0.2117) ≈ 71.75
    assert entry["weighted_pct"] == 71.75
    assert entry["source_url"].endswith("/msty/")
    assert len(entry["per_distribution"]) == 2


# Estructura real del fund page de YieldMax (valor ANTES de la etiqueta; SEC yield contiguo).
_RATE_HTML = """
<html><body>
  <p>...stay long COIN.</p>
  <span>77.28%</span> <span>Distribution Rate*</span>
  <span>9.12%</span> <span>30-Day SEC Yield**</span> <span>As of: 05/01/2026</span>
  <p>The Distribution Rate is the annual rate an investor would receive...
     This approach targets a 12% distribution rate by selling options.</p>
</body></html>
"""


def test_parse_distribution_rate_basic():
    info = f.parse_distribution_rate_from_html(_RATE_HTML)
    # toma el titular (precede a la etiqueta), NO el '30-Day SEC Yield' ni el '12%' de la prosa
    assert info["rate_pct"] == 77.28
    assert info["as_of"] == "2026-05-01"


def test_parse_distribution_rate_allows_over_100():
    html = "<div>134.50% Distribution Rate*</div>"
    assert f.parse_distribution_rate_from_html(html)["rate_pct"] == 134.50


def test_parse_distribution_rate_ignores_marketing_prose():
    # solo prosa con "12% distribution rate" (sin decimales, sin titular) -> None
    html = "<p>This approach targets a 12% distribution rate by selling options.</p>"
    assert f.parse_distribution_rate_from_html(html)["rate_pct"] is None


def test_parse_distribution_rate_absent():
    info = f.parse_distribution_rate_from_html("<div>Nothing here</div>")
    assert info["rate_pct"] is None
    assert info["as_of"] is None


def test_build_rate_entry():
    entry = f.build_rate_entry("MSTY", {"rate_pct": 77.28, "as_of": "2026-05-01"})
    assert entry["rate_pct"] == 77.28
    assert entry["as_of"] == "2026-05-01"
    assert entry["source_url"].endswith("/msty/")
