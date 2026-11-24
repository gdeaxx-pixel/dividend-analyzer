"""Lo que no se pudo leer del 1042-S se dice; nunca sale como $0 ni desaparece.

Dos huecos (24-nov): una casilla 7a ilegible se pintaba «Retenido: $0.00» en la tarjeta de
validación, y un formulario cuya línea de ingreso no se leía se descartaba sin avisar,
dejando el bruto y el ROC cortos.
"""
import pytest
import streamlit as st
from fpdf import FPDF

import logic
from test_1042s import _build_synthetic_1042s_pdf, _parsed, _results_con_dividendos
from ui import carga, validacion


def _pagina(ufi, linea_ingreso, retenido="8.00"):
    return [
        "Form 1042-S Foreign Person's U.S. Source Income Subject to Withholding",
        " ".join(ufi) + " UNIQUE FORM IDENTIFIER AMENDED AMENDMENT NO.",
        "1 Income 2 Gross income 3 Chapter indicator. Enter 3 or 4",
        linea_ingreso,
        f"7a Federal tax withheld {retenido}",
        "10 Total withholding credit (combine boxes 7a, 8, and 9)",
        retenido,
    ]


def _pdf(paginas):
    pdf = FPDF()
    pdf.set_font("Helvetica", size=10)
    for lineas in paginas:
        pdf.add_page()
        for linea in lineas:
            pdf.cell(0, 6, linea, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


BUENA = "06 28.00 3b Tax rate 30..00 4b Tax rate 00..00"
ROTA = "37 #### 3b Tax rate 00..00 4b Tax rate 00..00"


def test_el_formulario_que_no_se_lee_queda_anotado():
    r = logic.parse_1042s_pdf(_pdf([_pagina("2025417493", BUENA), _pagina("2025417494", ROTA)]))
    assert [f["unique_form_id"] for f in r["forms"]] == ["2025417493"]
    assert r["ids_sin_leer"] == ["2025417494"]


def test_si_otra_copia_si_se_lee_no_cuenta_como_perdido():
    r = logic.parse_1042s_pdf(_pdf([_pagina("2025417494", ROTA),
                                    _pagina("2025417494", "37 276.00 3b Tax rate 00..00 4b"),
                                    _pagina("2025417493", BUENA)]))
    assert len(r["forms"]) == 2 and r["ids_sin_leer"] == []


def test_un_pdf_que_se_lee_entero_no_anota_nada():
    assert logic.parse_1042s_pdf(_build_synthetic_1042s_pdf())["ids_sin_leer"] == []


def test_al_unir_documentos_se_cuentan_los_perdidos_una_vez():
    a = dict(_parsed(), ids_sin_leer=["2025000001", "2025417493"])
    b = dict(_parsed(), ids_sin_leer=["2025000001", "2025000002"])
    assert logic.combinar_1042s([a, b])["formularios_sin_leer"] == 2
    assert logic.combinar_1042s([_parsed()])["formularios_sin_leer"] == 0


def test_la_validacion_distingue_ilegible_de_cero():
    """Por la extracción real: la etiqueta 7a se lee, el importe no."""
    leido = logic.parse_1042s_pdf(_build_synthetic_1042s_pdf(fed_legible=False))
    assert all(f["federal_tax_withheld"] is None for f in leido["forms"])
    v = logic.build_1042s_validation(_results_con_dividendos(304.0), leido)
    assert v["retenido_1042s_completo"] is False
    ok = logic.build_1042s_validation(_results_con_dividendos(304.0), _parsed())
    assert ok["retenido_1042s_completo"] is True and ok["retenido_1042s"] == 91.0


def test_un_cero_leido_si_es_cero():
    forms = [{"unique_form_id": "2025417494", "income_code": "37", "gross_income": 276.0,
              "federal_tax_withheld": 0.0, "withholding_credit": 0.0, "conflict": False}]
    v = logic.build_1042s_validation(_results_con_dividendos(276.0), _parsed(forms))
    assert v["retenido_1042s_completo"] is True


@pytest.fixture
def pintado(monkeypatch):
    out = []
    monkeypatch.setattr(st, "session_state", {})
    monkeypatch.setattr(validacion.st, "markdown", lambda h, **k: out.append(h))
    return out


def _tarjeta(pintado, lectura):
    st.session_state["_wizard_1042s"] = lectura
    validacion._render_1042s(_results_con_dividendos(304.0))
    return " ".join(pintado)


def test_la_tarjeta_dice_no_legible_y_no_cero(pintado):
    html = _tarjeta(pintado, logic.parse_1042s_pdf(_build_synthetic_1042s_pdf(fed_legible=False)))
    assert "Retenido: <b>no legible</b>" in html
    assert "Retenido: <b>$" not in html


def test_la_tarjeta_normal_sigue_con_su_cifra_y_sin_aviso(pintado):
    html = _tarjeta(pintado, _parsed())
    assert "Retenido: <b>$91.00</b>" in html
    assert "No pudimos leer" not in html


@pytest.mark.parametrize("n,frase", [(1, "No pudimos leer 1 formulario de tu 1042-S"),
                                     (2, "No pudimos leer 2 formularios de tu 1042-S")])
def test_la_tarjeta_avisa_de_los_formularios_perdidos(pintado, n, frase):
    assert frase in _tarjeta(pintado, dict(_parsed(), formularios_sin_leer=n))


def test_el_paso_de_carga_avisa_de_los_formularios_perdidos(monkeypatch):
    avisos = []
    monkeypatch.setattr(st, "session_state", {})
    monkeypatch.setattr(carga, "_resumen_con_cambiar", lambda *a, **k: False)
    for nombre in ("_render_aviso_1042s_tda", "_render_aviso_1042s_viejo"):
        monkeypatch.setattr(carga, nombre, lambda lectura: None)
    monkeypatch.setattr(carga, "_render_residencia_detectada", lambda: None)
    monkeypatch.setattr(carga.st, "warning", lambda t, **k: avisos.append(t))
    st.session_state["_wizard_1042s"] = dict(_parsed(), formularios_sin_leer=1)
    carga._render_1042s_resumen()
    assert any("No pudimos leer 1 formulario de tu 1042-S" in a for a in avisos), avisos
    avisos.clear()
    st.session_state["_wizard_1042s"] = _parsed()
    carga._render_1042s_resumen()
    assert avisos == []

