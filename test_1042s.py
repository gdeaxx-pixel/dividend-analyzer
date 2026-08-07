"""Tests del Bloque 3 (Formulario 1042-S): parser determinista y blindaje de
_sum_roc_credit_from_forms contra el triple conteo de copias B/C/D.

Nota de alcance: build_1042s_validation (T3 del traspaso) NO se implementa aquí — es
lógica fiscal fuera del alcance del ejecutor (la implementa Opus por separado). El caso
"el codigo 01 no entra al bruto" se valida agregando manualmente el resultado de
parse_1042s_pdf (T1), sin depender de esa función.

Sin datos reales: se construye un PDF sintético con fpdf2 replicando la estructura de
texto de un 1042-S de Charles Schwab (3 formularios x 3 copias B/C/D = 9 apariciones),
con los mismos valores de la tabla de ground truth del traspaso.
"""
import os
import sys

import pandas as pd
import pytest
from fpdf import FPDF

sys.path.insert(0, os.path.dirname(__file__))
import logic


GROUND_TRUTH = [
    # (unique_form_id, income_code, gross_income, federal_tax_withheld, withholding_credit)
    ("2025417492", "01", 1.0, 0.0, 0.0),
    ("2025417493", "06", 28.0, 8.0, 8.0),
    ("2025417494", "37", 276.0, 83.0, 83.0),
]


def _build_synthetic_1042s_pdf(forms=GROUND_TRUTH, copies=3):
    """Genera un 1042-S sintético: cada formulario se repite `copies` veces (copias
    B/C/D), replicando el layout de texto real que exige el parser determinista."""
    pdf = FPDF()
    pdf.set_font("Helvetica", size=10)
    for unique_form_id, code, gross, withheld, credit in forms:
        spaced_id = " ".join(list(unique_form_id))
        for _copy in range(copies):
            pdf.add_page()
            lines = [
                "Form 1042-S Foreign Person's U.S. Source Income Subject to Withholding",
                f"{spaced_id} UNIQUE FORM IDENTIFIER AMENDED AMENDMENT NO.",
                "1 Income 2 Gross income 3 Chapter indicator. Enter 3 or 4",
                f"{code} {gross:.2f} 3b Tax rate 30..00 4b Tax rate 00..00",
                "5 Withholding allowance 00.00",
                "6 Net income 00.00",
                f"7a Federal tax withheld {withheld:.2f}",
                "7b Check if federal tax withheld was not deposited with the IRS",
                "10 Total withholding credit (combine boxes 7a, 8, and 9)",
                f"{credit:.2f}",
                "11 Tax paid by withholding agent (amounts not withheld)",
            ]
            for line in lines:
                pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _build_unrelated_pdf():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "Este es un documento cualquiera, no un formulario fiscal.")
    return bytes(pdf.output())


@pytest.fixture(scope="module")
def synthetic_1042s_bytes():
    return _build_synthetic_1042s_pdf()


# ── T1 · parse_1042s_pdf ────────────────────────────────────────────────────────

def test_dedupe_por_unique_form_id(synthetic_1042s_bytes):
    result = logic.parse_1042s_pdf(synthetic_1042s_bytes)
    assert result is not None
    assert len(result["forms"]) == 3


def test_credito_roc_no_se_triplica(synthetic_1042s_bytes):
    result = logic.parse_1042s_pdf(synthetic_1042s_bytes)
    roc_forms = [f for f in result["forms"] if f["income_code"] == "37"]
    assert len(roc_forms) == 1
    assert roc_forms[0]["withholding_credit"] == 83.0
    assert roc_forms[0]["withholding_credit"] != 249.0


def test_interes_fuera_del_bruto(synthetic_1042s_bytes):
    """El código 01 (interés de cash) no forma parte del bruto de dividendos/ROC.

    build_1042s_validation (que calcularía 'bruto_1042s' oficialmente) es T3 y está
    fuera del alcance de este ejecutor; se valida el mismo invariante agregando a mano
    el resultado ya deduplicado de parse_1042s_pdf.
    """
    result = logic.parse_1042s_pdf(synthetic_1042s_bytes)
    bruto_1042s = sum(f["gross_income"] for f in result["forms"]
                       if f["income_code"] in ("06", "37"))
    assert bruto_1042s == 304.0
    codigo_01 = [f for f in result["forms"] if f["income_code"] == "01"]
    assert codigo_01 and codigo_01[0]["gross_income"] == 1.0
    assert codigo_01[0]["gross_income"] not in (bruto_1042s,)


def test_pdf_ajeno_devuelve_none():
    result = logic.parse_1042s_pdf(_build_unrelated_pdf())
    assert result is None


# ── T2 · _sum_roc_credit_from_forms blindado ────────────────────────────────────

def test_sum_roc_dedupe_sin_identificador():
    """3 filas idénticas de código 37 sin unique_form_id: deduplica por la tupla
    (income_code, gross_income, federal_tax_withheld, withholding_credit) y no
    triplica el crédito."""
    rows = [
        {"income_code": "37", "gross_income": 276.0,
         "federal_tax_withheld": 83.0, "withholding_credit": 83.0},
        {"income_code": "37", "gross_income": 276.0,
         "federal_tax_withheld": 83.0, "withholding_credit": 83.0},
        {"income_code": "37", "gross_income": 276.0,
         "federal_tax_withheld": 83.0, "withholding_credit": 83.0},
    ]
    result = logic._sum_roc_credit_from_forms(rows)
    assert result["credit"] == 83.0
    assert result["roc_gross"] == 276.0


def test_sum_roc_dedupe_con_identificador(synthetic_1042s_bytes):
    """Mismo blindaje pero via unique_form_id (como llegaría de parse_1042s_pdf antes
    de deduplicar, o de un Gemini que no filtrara las copias)."""
    rows = [
        {"unique_form_id": "2025417494", "income_code": "37", "gross_income": 276.0,
         "federal_tax_withheld": 83.0, "withholding_credit": 83.0},
        {"unique_form_id": "2025417494", "income_code": "37", "gross_income": 276.0,
         "federal_tax_withheld": 83.0, "withholding_credit": 83.0},
        {"unique_form_id": "2025417494", "income_code": "37", "gross_income": 276.0,
         "federal_tax_withheld": 83.0, "withholding_credit": 83.0},
    ]
    result = logic._sum_roc_credit_from_forms(rows)
    assert result["credit"] == 83.0


# ── T2 · extract_1042s (wrapper determinista → Gemini) ──────────────────────────

def test_extract_1042s_camino_determinista_sin_api_key(synthetic_1042s_bytes):
    """Sin GEMINI_API_KEY el Bloque 3 debe seguir funcionando: pdfplumber no la
    necesita (criterio de aceptación del traspaso)."""
    result = logic.extract_1042s(synthetic_1042s_bytes, api_key=None)
    assert result is not None
    assert result["source"] == "pdfplumber"
    assert len(result["forms"]) == 3


def test_extract_1042s_pdf_ajeno_sin_api_key_devuelve_none():
    result = logic.extract_1042s(_build_unrelated_pdf(), api_key=None)
    assert result is None


# ── T3 · build_1042s_validation ─────────────────────────────────────────────────

def _parsed(forms=None, tax_year=2025):
    """Dict con la forma que devuelven parse_1042s_pdf / extract_1042s."""
    if forms is None:
        forms = [{"unique_form_id": fid, "income_code": code, "gross_income": gross,
                  "federal_tax_withheld": wh, "withholding_credit": cr, "conflict": False}
                 for fid, code, gross, wh, cr in GROUND_TRUTH]
    return {"tax_year": tax_year, "forms": forms, "source": "pdfplumber"}


def _results_con_dividendos(total, year=2025):
    """`results` mínimo con un historial que produce `total` de dividendo BRUTO en `year`."""
    return {"MSTY": {"history": pd.DataFrame({
        "Date": [pd.Timestamp(year=year, month=6, day=15)],
        "Action": ["Cash Dividend"],
        "Amount": [total],
    })}}


def test_validation_interes_fuera_del_bruto():
    """Código 01 (interés de cash) NO entra al bruto; sí se reporta aparte."""
    v = logic.build_1042s_validation(_results_con_dividendos(304.0), _parsed())
    assert v["bruto_1042s"] == 304.0        # 28 (código 06) + 276 (código 37)
    assert v["interes_cash"] == 1.0         # código 01, fuera del bruto
    assert v["roc_1042s"] == 276.0
    assert v["retenido_1042s"] == 91.0      # 8 + 83


def test_validation_dedupe_defensivo_no_triplica_el_bruto():
    """9 filas (copias B/C/D) sin unique_form_id: el bruto debe ser 304, nunca 912."""
    forms = [{"income_code": code, "gross_income": gross,
              "federal_tax_withheld": wh, "withholding_credit": cr}
             for _fid, code, gross, wh, cr in GROUND_TRUTH for _copy in range(3)]
    v = logic.build_1042s_validation(_results_con_dividendos(304.0), _parsed(forms))
    assert v["bruto_1042s"] == 304.0
    assert v["bruto_1042s"] != 912.0
    assert v["roc_1042s"] == 276.0


def test_validation_no_muta_results():
    import copy
    results = _results_con_dividendos(304.0)
    antes = copy.deepcopy(results)
    logic.build_1042s_validation(results, _parsed())
    assert set(results.keys()) == set(antes.keys())
    assert results["MSTY"]["history"].equals(antes["MSTY"]["history"])
    assert list(results["MSTY"].keys()) == list(antes["MSTY"].keys())


def test_validation_match_dentro_del_redondeo():
    """El 1042-S redondea a dólares enteros: 2 dólares de diferencia sobre 304 caen
    dentro de la tolerancia (1 dólar por formulario de dividendo/ROC)."""
    v = logic.build_1042s_validation(_results_con_dividendos(306.0), _parsed())
    assert v["status"] == "match"


def test_validation_portafolio_mas_alto():
    v = logic.build_1042s_validation(_results_con_dividendos(500.0), _parsed())
    assert v["status"] == "portfolio_higher"
    assert v["delta"] == 196.0


def test_validation_formulario_mas_alto():
    v = logic.build_1042s_validation(_results_con_dividendos(100.0), _parsed())
    assert v["status"] == "form_higher"
    assert v["delta"] == -204.0


def test_validation_sin_solapamiento_no_es_error():
    """El CSV cubre otro año: no hay nada que comparar, y no debe reportarse como fallo."""
    v = logic.build_1042s_validation(_results_con_dividendos(304.0, year=2023), _parsed())
    assert v["status"] == "no_overlap"
    assert v["bruto_portafolio"] == 0.0


def test_validation_ignora_tickers_descartados():
    results = _results_con_dividendos(304.0)
    results["ZZZZ"] = {"skipped": True, "history": pd.DataFrame({
        "Date": [pd.Timestamp(year=2025, month=6, day=15)],
        "Action": ["Cash Dividend"],
        "Amount": [1000.0],
    })}
    v = logic.build_1042s_validation(results, _parsed())
    assert v["bruto_portafolio"] == 304.0


def test_income_code_str_normaliza_lo_que_devuelve_gemini():
    """El camino determinista da '37', pero Gemini puede dar 37, '037' o '37 '.
    Comparar crudo contra '37' haría que un ROC válido contara como cero."""
    assert logic.income_code_str("37") == "37"
    assert logic.income_code_str(37) == "37"
    assert logic.income_code_str("037") == "37"
    assert logic.income_code_str(" 37 ") == "37"
    assert logic.income_code_str(6) == "06"
    assert logic.income_code_str(None) == ""
    assert logic.income_code_str("") == ""


def test_validation_acepta_codigos_no_normalizados():
    """Un 1042-S leído por Gemini con códigos enteros debe dar el mismo bruto y ROC."""
    forms = [{"unique_form_id": fid, "income_code": int(code), "gross_income": gross,
              "federal_tax_withheld": wh, "withholding_credit": cr}
             for fid, code, gross, wh, cr in GROUND_TRUTH]
    v = logic.build_1042s_validation(_results_con_dividendos(304.0), _parsed(forms))
    assert v["bruto_1042s"] == 304.0
    assert v["roc_1042s"] == 276.0
    assert v["interes_cash"] == 1.0


def test_validation_sin_formularios_devuelve_none():
    assert logic.build_1042s_validation({}, None) is None
    assert logic.build_1042s_validation({}, {"tax_year": 2025, "forms": []}) is None
