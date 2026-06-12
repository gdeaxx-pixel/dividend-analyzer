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
