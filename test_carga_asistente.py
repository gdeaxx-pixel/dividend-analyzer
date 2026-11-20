"""Arreglos del asistente de carga (auditoría S7, 2026-11-20): H1 documentos fiscales,
H2 nombre de archivo escapado, H3 símbolo en minúsculas, H4 rótulos. Todo sintético."""
import pytest

from test_carga_1042s import _at_con_posiciones_confirmadas, _tiene_uploader_pdf
from test_carga_posiciones_csv import _at, _campo
from ui import carga

_LECTURA_1042S = {"tax_year": 2025, "source": "pdfplumber", "forms": [
    {"unique_form_id": "2025417493", "income_code": "06", "gross_income": 28.0,
     "federal_tax_withheld": 8.0, "withholding_credit": 8.0, "conflict": False}]}
_INGRESOS = {"tickers": {"ZZZZ": {"received_total": 5.0}}, "multi_account": False}
_NOMBRE_HOSTIL = "<b onmouseover=alert(1)>a</b>&<img src=x onerror=alert(2)>.csv"


@pytest.fixture
def sin_clave(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(carga, "_clave_gemini", lambda: None)


def _tiene_uploader_ingresos(at):
    return any(w.key == "_vd_upload_inc" for w in at.get("file_uploader"))


def _markdown(at):
    return "\n".join(m.value for m in at.markdown)


def test_h1_con_el_1042s_leido_el_cargador_de_ingresos_sigue():
    at = _at_con_posiciones_confirmadas()
    at.session_state["_wizard_1042s"] = _LECTURA_1042S
    at.run()
    assert not at.exception
    assert "1042-S leído" in _markdown(at)
    assert not _tiene_uploader_pdf(at)
    assert _tiene_uploader_ingresos(at)


def test_h1_con_los_ingresos_leidos_el_cargador_del_1042s_sigue():
    at = _at_con_posiciones_confirmadas()
    at.session_state["_wizard_income_summary"] = _INGRESOS
    at.run()
    assert not at.exception
    assert "Ingresos cargados" in _markdown(at)
    assert _tiene_uploader_pdf(at)
    assert not _tiene_uploader_ingresos(at)


def test_h1_con_los_dos_leidos_ninguno_se_dibuja():
    at = _at_con_posiciones_confirmadas()
    at.session_state["_wizard_1042s"] = _LECTURA_1042S
    at.session_state["_wizard_income_summary"] = _INGRESOS
    at.run()
    assert not at.exception
    assert "1042-S leído" in _markdown(at) and "Ingresos cargados" in _markdown(at)
    assert not _tiene_uploader_pdf(at)
    assert not _tiene_uploader_ingresos(at)


def test_h2_el_nombre_del_archivo_sale_escapado():
    at = _at()
    at.session_state["_wizard_csv_name"] = _NOMBRE_HOSTIL
    at.run()
    assert not at.exception
    bloque = next(m.value for m in at.markdown if "CSV cargado" in m.value)
    assert "<b onmouseover" not in bloque
    assert "<img" not in bloque
    assert "&lt;b onmouseover" in bloque


def test_h3_un_simbolo_en_minusculas_no_deja_la_tabla_en_cero(sin_clave):
    at = _at()
    at.session_state["_wizard_csv_ticker_data"] = {
        "msty": {"shares": 40.0, "invested": 1000.0}}
    at.session_state["_vd_modo_pos"] = "mano"
    at.run()
    assert not at.exception
    assert _campo(at, "_vd_sh_MSTY") == 40.0
    assert _campo(at, "_vd_cb_MSTY") == 1000.0


def test_h4_posiciones_confirmadas_cuenta_solo_las_que_tienen_acciones(sin_clave):
    at = _at()
    at.session_state["_wizard_positions"] = {
        "MSTY": {"shares": 0.0, "cost_basis": 0.0},
        "SCHB": {"shares": 0.0, "cost_basis": 0.0},
        "TSLY": {"shares": 0.0, "cost_basis": 0.0}}
    at.session_state["_wizard_pos_confirmed"] = True
    at.run()
    assert not at.exception
    assert "Posiciones confirmadas</span><span class=\"vd-resumen-detalle\"> · 0 instrumentos" \
        in _markdown(at)


def test_h4_con_acciones_cuenta_solo_las_positivas(sin_clave):
    at = _at()
    at.session_state["_wizard_positions"] = {
        "MSTY": {"shares": 5.0, "cost_basis": 10.0},
        "SCHB": {"shares": 0.0, "cost_basis": 0.0}}
    at.session_state["_wizard_pos_confirmed"] = True
    at.run()
    assert "· 1 instrumento<" in _markdown(at)


def test_h4_el_rotulo_de_ingresos_dice_cargados():
    at = _at_con_posiciones_confirmadas()
    at.session_state["_wizard_income_summary"] = _INGRESOS
    at.run()
    texto = _markdown(at)
    assert "Ingresos cargados" in texto
    assert "Ingresos validados" not in texto
