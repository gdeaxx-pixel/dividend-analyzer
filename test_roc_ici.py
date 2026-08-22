"""Tests del parser de tools/fetch_roc_ici.py (sin red): valida la extracción del ICI Primary
Layout en Excel (2024/2025) y en PDF (2023), y el cálculo de %ROC = Σ(Nondividend
Distributions) / Σ(Total Distribution Per Share) por ticker y AÑO FISCAL.

El fixture del Excel se construye en `xlsx_2024_sample` (más abajo) en vez de commitear un
`.xlsx` binario: el repo ignora `*.xlsx` globalmente (`.gitignore`) y los demás fixtures de
`fixtures/` ya siguen ese patrón (CSV/JSON, nunca binarios de bróker). Reproduce el layout
MEDIDO del ICI real (cabecera con "Ticker Symbol", columnas fijas C/H/J/K/L/M/Z) poblado con
las filas REALES de CONY y NVDY del "2024 ICI Primary Layout - YieldMax.xlsx" oficial — sus
totales reproducen el ground truth verificado a mano en el traspaso (CONY 58.97%, NVDY
15.24%). Trae además una fila SINTÉTICA ("ZOOM", no es un fondo real) con la columna K (2023,
Prior Year) distinta de cero, para probar que el parser agrupa por la columna de año que lleva
el importe y no por `Ex-Dividend Date` ni por "asume que todo es el año del documento".

`fixtures/roc_ici_2023_sample.pdf` sí es un archivo commiteado: el PDF real de 2023 tal cual
(ya es pequeño — 4 páginas, ~77KB — y sus tickers objetivo están repartidos entre los dos
pares de páginas del documento, así que recortarlo no lo habría hecho más chico sin perder
cobertura).
"""
import datetime as dt
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools"))
import fetch_roc_ici as f  # noqa: E402

FIX_2023_PDF = os.path.join(HERE, "fixtures", "roc_ici_2023_sample.pdf")

# Filas reales de CONY 2024 (extraídas del "2024 ICI Primary Layout - YieldMax.xlsx" oficial;
# Σ J=20.2980, Σ Z=11.9697 -> ROC% = 58.97%, el ground truth del traspaso).
_CONY_ROWS = [
    ("2024-01-05", 2.6932, 1.90346642),
    ("2024-02-07", 1.0751, 0.75984581),
    ("2024-03-06", 1.6619000000000002, 1.17457702),
    ("2024-04-04", 2.7944, 1.97499129),
    ("2024-05-06", 2.2807, 1.61192479),
    ("2024-06-06", 1.6982, 1.20023268),
    ("2024-07-05", 1.5732000000000002, 1.11188674),
    ("2024-08-07", 1.0061, 0.71107885),
    ("2024-09-06", 1.0432000000000001, 0.73729993),
    ("2024-10-17", 1.1098, 0.78437065),
    ("2024-11-14", 2.0231, 0),
    ("2024-12-12", 1.3391, 0),
]

# Filas reales de NVDY 2024. Σ J=19.5329, Σ Z=2.9759 -> ROC% = 15.24%.
_NVDY_ROWS = [
    ("2024-01-05", 0.626, 0.10752732),
    ("2024-02-07", 1.5303999999999998, 0.26287509),
    ("2024-03-06", 2.6219, 0.45036082),
    ("2024-04-04", 2.6083, 0.44802476),
    ("2024-05-06", 1.1987999999999999, 0.20591653),
    ("2024-06-06", 2.5629999999999997, 0.44024363),
    ("2024-07-05", 2.4707000000000003, 0.42438936),
    ("2024-08-07", 1.2512, 0.21491722),
    ("2024-09-06", 1.3548, 0.23271247),
    ("2024-10-10", 1.0999, 0.18892859),
    ("2024-11-07", 1.0228, 0),
    ("2024-12-05", 1.1851, 0),
]


@pytest.fixture
def xlsx_2024_sample(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Primary Layout FINAL"

    header_row = 5   # deliberadamente distinto de la fila 13 del documento real (ver test
                      # test_parse_xlsx_finds_header_row_dynamically)
    ws.cell(row=header_row, column=1, value="Security Description (Fund Name)")
    ws.cell(row=header_row, column=3, value="Ticker Symbol")
    ws.cell(row=header_row, column=8, value="Ex-Dividend Date")
    ws.cell(row=header_row, column=10, value="Total Distribution Per Share (11+12+13)")
    ws.cell(row=header_row, column=11, value="2023 (Prior Year)")
    ws.cell(row=header_row, column=12, value="2025 (Next Year)")
    ws.cell(row=header_row, column=13, value="2024 (Current Year) (14+15+22+26+28+30)")
    ws.cell(row=header_row, column=26, value="Nondividend Distributions")

    row = header_row + 1
    for tk, rows in (("CONY", _CONY_ROWS), ("NVDY", _NVDY_ROWS)):
        for date_s, j, z in rows:
            y, m, d = (int(x) for x in date_s.split("-"))
            ws.cell(row=row, column=1, value=f"YieldMax {tk} Option Income Strategy ETF")
            ws.cell(row=row, column=3, value=tk)
            ws.cell(row=row, column=8, value=dt.datetime(y, m, d))
            ws.cell(row=row, column=10, value=j)
            ws.cell(row=row, column=13, value=j)  # M = J porque K y L son 0
            ws.cell(row=row, column=26, value=z)
            row += 1

    # Fila SINTÉTICA (no es un fondo real de YieldMax): "ZOOM" con K=1.0 (2023, Prior Year)
    # debe caer en 2023, no en 2024, aunque su Ex-Dividend Date esté en 2024.
    ws.cell(row=row, column=1, value="Fondo sintético de prueba (no es un fondo real)")
    ws.cell(row=row, column=3, value="ZOOM")
    ws.cell(row=row, column=8, value=dt.datetime(2024, 1, 10))
    ws.cell(row=row, column=10, value=1.0)
    ws.cell(row=row, column=11, value=1.0)
    ws.cell(row=row, column=13, value=0.0)
    ws.cell(row=row, column=26, value=0.5)

    path = tmp_path / "roc_ici_2024_sample.xlsx"
    wb.save(path)
    return str(path)


def _pct_by_ticker_year(rows):
    agg = f.aggregate([(tk, y, j, z, "doc", "url") for tk, y, j, z in rows])
    out = f.build_yaml_entries(agg, "2026-08-21")
    return {tk: {y: e["roc_pct"] for y, e in years.items()} for tk, years in out.items()}


def test_parse_xlsx_reproduce_2024_ground_truth(xlsx_2024_sample):
    # CONY y NVDY con sus 12 filas reales de 2024: Σ Total (J) y Σ ROC (Z) deben reproducir
    # EXACTAMENTE el ground truth del traspaso (58.97% y 15.24%), no una aproximación.
    rows = f.parse_xlsx(xlsx_2024_sample)
    pct = _pct_by_ticker_year(rows)
    assert pct["CONY"][2024] == 58.97
    assert pct["NVDY"][2024] == 15.24


def test_parse_xlsx_groups_by_year_attribution_column_not_exdiv_date(xlsx_2024_sample):
    # La fila sintética "ZOOM" tiene Ex-Dividend Date en 2024 pero K (2023, Prior Year) = 1.0
    # y M (2024, Current Year) = 0.0: el importe completo pertenece a 2023, no a 2024.
    rows = f.parse_xlsx(xlsx_2024_sample)
    pct = _pct_by_ticker_year(rows)
    assert 2023 in pct["ZOOM"] and pct["ZOOM"][2023] == 50.0
    assert 2024 not in pct.get("ZOOM", {})


def test_parse_xlsx_finds_header_row_dynamically(xlsx_2024_sample):
    # La fixture pone la cabecera en la fila 5 (no en la 13 del documento real de 2024): si
    # el parser tuviera la fila cableada en vez de buscar "Ticker Symbol", esto fallaría.
    rows = f.parse_xlsx(xlsx_2024_sample)
    assert len(rows) == 25  # 12 CONY + 12 NVDY + 1 ZOOM


def test_parse_pdf_ground_truth_2023_manual_check():
    # Valores verificados a mano contra el PDF fuente (ver reporte de comparación): TSLY
    # 2023 con sus 12 filas reales, Σ J=9.1226, Σ Z=7.2588 -> 79.57%.
    rows = f.parse_pdf(FIX_2023_PDF, 2023)
    pct = _pct_by_ticker_year(rows)
    assert pct["TSLY"][2023] == 79.57
    assert pct["CONY"][2023] == 0.0


def test_parse_pdf_msty_absent_in_2023():
    # MSTY incepcionó en julio de 2024: no debe aparecer en el documento de 2023. Que esté
    # ausente es correcto, no un fallo del parser (mismo caso que documenta el traspaso).
    rows = f.parse_pdf(FIX_2023_PDF, 2023)
    tickers = {tk for tk, _, _, _ in rows}
    assert "MSTY" not in tickers


def test_parse_pdf_raises_on_odd_page_count(monkeypatch):
    # Guard de forma: si el PDF no viene en dos mitades iguales de páginas, el layout
    # asumido no aplica y hay que fallar fuerte, no adivinar el apareo.
    import pdfplumber

    class _FakePage:
        def extract_text(self):
            return "2023 YEAR-END TAX REPORTING INFORMATION"

    class _FakePdf:
        pages = [_FakePage(), _FakePage(), _FakePage()]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(pdfplumber, "open", lambda _path: _FakePdf())
    try:
        f.parse_pdf("unused.pdf", 2023)
        assert False, "debía lanzar ValueError con número impar de páginas"
    except ValueError as e:
        assert "impar" in str(e)


def test_build_yaml_entries_carries_provenance(xlsx_2024_sample):
    rows = f.parse_xlsx(xlsx_2024_sample)
    tagged = [(tk, y, j, z, "2024 ICI Primary Layout - YieldMax.xlsx", "https://example.com/x.xlsx")
              for tk, y, j, z in rows]
    agg = f.aggregate(tagged)
    out = f.build_yaml_entries(agg, "2026-08-21")
    entry = out["CONY"][2024]
    assert entry["source_doc"] == "2024 ICI Primary Layout - YieldMax.xlsx"
    assert entry["source_url"] == "https://example.com/x.xlsx"
    assert entry["asof"] == "2026-08-21"


def test_aggregate_sums_multiple_docs_for_same_ticker_year():
    # Si dos documentos aportaran filas al mismo (ticker, año) -- no pasa hoy (2024 y 2025
    # no tienen atribución cruzada, ver el PR), pero el agregador debe sumarlas sin pisarlas.
    rows = [("XYZ", 2024, 1.0, 0.5, "docA", "urlA"), ("XYZ", 2024, 1.0, 0.1, "docB", "urlB")]
    agg = f.aggregate(rows)
    out = f.build_yaml_entries(agg, "2026-08-21")
    assert out["XYZ"][2024]["roc_pct"] == 30.0  # (0.5+0.1)/(1.0+1.0)*100
    assert sorted(out["XYZ"][2024]["source_doc"]) == ["docA", "docB"]
