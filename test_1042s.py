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


def _build_synthetic_1042s_pdf(forms=GROUND_TRUTH, copies=3, country_code="CO"):
    """Genera un 1042-S sintético: cada formulario se repite `copies` veces (copias
    B/C/D), replicando el layout de texto real que exige el parser determinista.

    Tasas de la casilla 3b y país de la 13b copiados del 1042-S real de `real_examples`:
    el ROC (código 37) va al 0% y el resto al 30%, y el país del receptor va al FINAL de la
    línea siguiente a su etiqueta, detrás del nombre. Las copias alternan `30..00` y
    `30.0.0` porque el documento real lo hace — el parser tiene que tolerar ambos."""
    pdf = FPDF()
    pdf.set_font("Helvetica", size=10)
    for unique_form_id, code, gross, withheld, credit in forms:
        spaced_id = " ".join(list(unique_form_id))
        base = "00" if code == "37" else "30"
        for _copy in range(copies):
            rate = f"{base}..00" if _copy < copies - 1 else f"{base}.0.0"
            pdf.add_page()
            lines = [
                "Form 1042-S Foreign Person's U.S. Source Income Subject to Withholding",
                f"{spaced_id} UNIQUE FORM IDENTIFIER AMENDED AMENDMENT NO.",
                "1 Income 2 Gross income 3 Chapter indicator. Enter 3 or 4",
                f"{code} {gross:.2f} 3b Tax rate {rate} 4b Tax rate 00..00",
                "5 Withholding allowance 00.00",
                "6 Net income 00.00",
                f"7a Federal tax withheld {withheld:.2f}",
                "7b Check if federal tax withheld was not deposited with the IRS",
                "10 Total withholding credit (combine boxes 7a, 8, and 9)",
                f"{credit:.2f}",
                "11 Tax paid by withholding agent (amounts not withheld)",
                "13a Recipient's name 13b Recipient's country code",
                f"NOMBRE DE PRUEBA {country_code}",
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


# ── Casillas 3b (tasa aplicada) y 13b (país) — PR B ─────────────────────────────────────
#
# El país da la tasa a la que el cliente tiene DERECHO; la casilla 3b dice la que le
# APLICARON. No son la misma cantidad: el 10% de México solo corre si el W-8BEN está
# presentado y vigente, y sin él retienen 30% igual. Estos campos son la fuente autoritativa
# de ambas mitades del diagnóstico.

def test_extrae_la_tasa_aplicada_de_la_casilla_3b():
    """La tasa venía JUSTO al lado del ancla que el parser ya usaba, y se tiraba."""
    r = logic.parse_1042s_pdf(_build_synthetic_1042s_pdf())
    tasas = {f["income_code"]: f["tax_rate"] for f in r["forms"]}
    assert tasas["06"] == pytest.approx(30.0), "dividendo ordinario: 30% estatutario"
    assert tasas["37"] == pytest.approx(0.0), "ROC: no es renta gravable, tasa 0"
    assert tasas["01"] == pytest.approx(30.0)


def test_el_parser_no_fabrica_una_tasa_cuando_la_3b_viene_corta():
    """Ejercita el RECORTE del caller, no solo el helper.

    Con una 3b de 3 dígitos, si el parser no corta antes de «4b» los dígitos de esa casilla
    completan el hueco y sale una tasa inventada (0.04) en vez de admitir que no se pudo
    leer. Se prefiere `None` — una tasa fabricada es peor que ninguna: alimenta el
    diagnóstico de W-8BEN, y ahí un número falso acusa al cliente de algo que no pasó."""
    pdf = FPDF()
    pdf.set_font("Helvetica", size=10)
    pdf.add_page()
    for linea in [
        "Form 1042-S Foreign Person's U.S. Source Income Subject to Withholding",
        "2 0 2 5 4 1 7 4 9 3 UNIQUE FORM IDENTIFIER AMENDED AMENDMENT NO.",
        "1 Income 2 Gross income 3 Chapter indicator. Enter 3 or 4",
        "06 28.00 3b Tax rate 0..00 4b Tax rate 30..00",     # 3b corta, 4b con valor
        "7a Federal tax withheld 8.00",
        "10 Total withholding credit (combine boxes 7a, 8, and 9)",
        "8.00",
    ]:
        pdf.cell(0, 6, linea, new_x="LMARGIN", new_y="NEXT")

    r = logic.parse_1042s_pdf(bytes(pdf.output()))
    assert r is not None and r["forms"], "el resto del formulario debe seguir leyéndose"
    assert r["forms"][0]["tax_rate"] is None, (
        f'tasa fabricada: {r["forms"][0]["tax_rate"]} — los dígitos de la casilla 4b se '
        "colaron en la 3b")


def test_extrae_el_pais_del_receptor_de_la_casilla_13b():
    r = logic.parse_1042s_pdf(_build_synthetic_1042s_pdf(country_code="MX"))
    assert r["recipient_country_code"] == "MX"
    assert logic.pais_desde_codigo_1042s("MX") == "México"


def test_la_tasa_tolera_las_tres_variantes_del_formulario():
    """Regresión de las tres variantes que el documento real imprime en el MISMO PDF
    (copias B/C/D). No pretende ser mejor que un parseo decimal: medido, para estas
    entradas dan lo mismo. Fija el contrato, que es lo que puede romperse al refactorizar."""
    assert logic._tasa_3b(" 30..00 ") == pytest.approx(30.0)
    assert logic._tasa_3b(" 00..00 ") == pytest.approx(0.0)
    assert logic._tasa_3b(" 00.0.0 ") == pytest.approx(0.0)
    assert logic._tasa_3b(" 15..00 ") == pytest.approx(15.0)
    assert logic._tasa_3b("") is None
    assert logic._tasa_3b("basura") is None


def test_la_tasa_3b_no_se_contamina_con_la_4b():
    """Las dos casillas comparten línea: `3b Tax rate 30..00 4b Tax rate 00..00`. Si el
    caller no recorta antes de «4b», una 3b con menos dígitos de los esperados absorbe los
    de la 4b y sale una tasa inventada."""
    linea = " 0..00 4b Tax rate 30..00"
    # Recortado: 3 dígitos no alcanzan para NN.NN, así que se rechaza en vez de adivinar.
    assert logic._tasa_3b(linea.split("4b")[0]) is None
    # Sin recortar sale una tasa FABRICADA: el «4» de la etiqueta «4b» y los dígitos de esa
    # casilla completan el hueco (000 + 4 + 3000 → los 4 primeros son 0004 → 00.04).
    fabricada = logic._tasa_3b(linea)
    assert fabricada is not None and fabricada == pytest.approx(0.04)


@pytest.mark.parametrize("codigo,esperado", [
    ("MX", "México"),
    ("CO", "Colombia"),
    ("CI", "Chile"),        # código IRS
    ("CL", "Chile"),        # variante ISO — se aceptan ambas
    ("US", "Estados Unidos"),
    ("mx", "México"),       # insensible a mayúsculas
    ("ZZ", None),           # desconocido: NO se adivina
    ("", None),
    (None, None),
])
def test_mapeo_de_codigos_de_pais(codigo, esperado):
    assert logic.pais_desde_codigo_1042s(codigo) == esperado


def test_los_dos_caminos_de_gemini_piden_las_dos_casillas():
    """Estructural: hay tres extractores (pdfplumber + dos de Gemini) y los tres tienen que
    traer los mismos campos, o el resultado dependería de cuál respondió."""
    import inspect
    fuente = inspect.getsource(logic)
    assert fuente.count('"tax_rate": types.Schema') == 2, "falta tax_rate en algún schema"
    assert fuente.count('"recipient_country_code": types.Schema') == 2
    assert fuente.count("'tax_rate' = Box 3b") == 2, "falta la casilla 3b en algún prompt"
    assert fuente.count("'recipient_country_code' = Box 13b") == 2


def test_contra_el_1042s_real():
    """Ground truth del documento real de `real_examples` (privado, symlink): código 06
    dividendo al 30%, código 37 ROC al 0%, receptor en Colombia. Si el symlink no está
    montado el test hace SKIP — y un skip no es un pass."""
    import glob
    patron = os.path.join(os.path.dirname(__file__), "real_examples",
                          "charles_schwab_data", "*", "*.pdf")
    pdfs = glob.glob(patron)
    if not pdfs:
        pytest.skip("real_examples no montado (data privada)")

    r = None
    for ruta in pdfs:
        with open(ruta, "rb") as fh:
            r = logic.parse_1042s_pdf(fh.read())
        if r:
            break
    if not r:
        pytest.skip("ningún PDF de real_examples es un 1042-S legible")

    tasas = {f["income_code"]: f["tax_rate"] for f in r["forms"]}
    assert tasas.get("06") == pytest.approx(30.0)
    assert tasas.get("37") == pytest.approx(0.0)
    assert r["recipient_country_code"] == "CO"
    assert logic.pais_desde_codigo_1042s(r["recipient_country_code"]) == "Colombia"

    # La aritmética tiene que coincidir con la tasa declarada: $8 sobre $28 ≈ 30%. Es el
    # cruce que hace posible el diagnóstico de W-8BEN (PR C).
    div = next(f for f in r["forms"] if f["income_code"] == "06")
    observada = div["federal_tax_withheld"] / div["gross_income"] * 100
    assert observada == pytest.approx(tasas["06"], abs=2.0)


# ── Fase 1 · diagnose_broker_refund_from_forms ──────────────────────────────────
# «¿El bróker ya me devolvió la retención en exceso?» = 7a − casilla 10.


def test_refund_caso_real_2022_devuelto():
    """2022, code 36: 7a=$1.00, casilla 10=$0.00 → el bróker corrigió, devolvió $1.00."""
    rows = [{"income_code": "36", "gross_income": 3.0,
             "federal_tax_withheld": 1.0, "withholding_credit": 0.0}]
    r = logic.diagnose_broker_refund_from_forms(rows)
    assert r["veredicto"] == "devuelto"
    assert r["devuelto"] == pytest.approx(1.0)
    assert r["pendiente"] == pytest.approx(0.0)


def test_refund_caso_real_2025_pendiente():
    """2025, code 37: 7a=$83.00, casilla 10=$83.00 → nada volvió, toca 1040-NR."""
    rows = [{"income_code": "37", "gross_income": 276.0,
             "federal_tax_withheld": 83.0, "withholding_credit": 83.0}]
    r = logic.diagnose_broker_refund_from_forms(rows)
    assert r["veredicto"] == "pendiente"
    assert r["devuelto"] == pytest.approx(0.0)
    assert r["pendiente"] == pytest.approx(83.0)


def test_refund_sin_withholding_credit_es_indeterminado_no_cero():
    """Sin casilla 10 numérica el veredicto es 'indeterminado', NUNCA un cero falso."""
    for ausente in (None, "", "  ", "n/a"):
        rows = [{"income_code": "37", "gross_income": 276.0,
                 "federal_tax_withheld": 83.0, "withholding_credit": ausente}]
        r = logic.diagnose_broker_refund_from_forms(rows)
        assert r["veredicto"] == "indeterminado"
        assert r["devuelto"] is None
        assert r["devuelto"] != 0.0
        assert r["pendiente"] is None


def test_refund_devuelto_negativo_es_indeterminado():
    """7a=$5, casilla 10=$8 → devuelto −$3: la casilla 8 no es cero, no aplica la
    fórmula de dos términos. Ni número negativo ni truncado a cero."""
    rows = [{"income_code": "06", "gross_income": 20.0,
             "federal_tax_withheld": 5.0, "withholding_credit": 8.0}]
    r = logic.diagnose_broker_refund_from_forms(rows)
    assert r["veredicto"] == "indeterminado"
    assert r["devuelto"] is None


def test_refund_parcial():
    """7a=$10, casilla 10=$4 → devuelto $6 (0 < devuelto < 7a)."""
    rows = [{"income_code": "37", "gross_income": 100.0,
             "federal_tax_withheld": 10.0, "withholding_credit": 4.0}]
    r = logic.diagnose_broker_refund_from_forms(rows)
    assert r["veredicto"] == "parcial"
    assert r["devuelto"] == pytest.approx(6.0)
    assert r["pendiente"] == pytest.approx(4.0)


def test_refund_no_triplica_copias_bcd():
    """El mismo formulario 3× (copias B/C/D) no debe triplicar el retenido."""
    fila = {"income_code": "37", "gross_income": 276.0,
            "federal_tax_withheld": 83.0, "withholding_credit": 83.0}
    r = logic.diagnose_broker_refund_from_forms([dict(fila), dict(fila), dict(fila)])
    assert len(r["per_form"]) == 1
    assert r["retenido"] == pytest.approx(83.0)
    assert r["veredicto"] == "pendiente"
