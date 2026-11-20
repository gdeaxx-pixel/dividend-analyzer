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


def test_h2_el_simbolo_sale_escapado(sin_clave, monkeypatch):
    hostil = "<IMG SRC=X ONERROR=ALERT(1)>"
    monkeypatch.setattr(carga.logic, "classify_tickers", lambda ts: {t: "mode_a" for t in ts})
    at = _at()
    limpio = at.session_state["_wizard_df_clean"].copy()
    limpio["Ticker"] = hostil
    at.session_state["_wizard_df_clean"] = limpio
    at.session_state["_wizard_csv_ticker_data"] = {hostil: {"shares": 1.0, "invested": 10.0}}
    at.session_state["_vd_modo_pos"] = "mano"
    at.run()
    assert not at.exception
    bloque = next(m.value for m in at.markdown if 'class="vd-ticker"' in m.value)
    assert "<IMG" not in bloque
    assert "&lt;IMG SRC=X ONERROR=ALERT(1)&gt;" in bloque


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



def _avisos(at):
    return [c.value for c in at.caption if c.value.startswith("⚠️")]


def test_la_fecha_ilegible_se_avisa_aparte_de_las_as_of(sin_clave):
    at = _at()
    at.session_state["_wizard_csv_descarte"] = {
        "total": 3, "por_accion": {"Stock Split": 1}, "fecha_ilegible": 2}
    at.run()
    assert not at.exception
    assert _avisos(at) == [
        "⚠️ 1 fila con fecha «... as of ...» que no se pudo ubicar en el tiempo, excluida: "
        "1× Stock Split.",
        "⚠️ 2 filas con una fecha que no pudimos leer, excluidas."]


def test_solo_fechas_ilegibles_no_habla_de_as_of(sin_clave):
    at = _at()
    at.session_state["_wizard_csv_descarte"] = {"total": 1, "por_accion": {}, "fecha_ilegible": 1}
    at.run()
    assert not at.exception
    assert _avisos(at) == ["⚠️ 1 fila con una fecha que no pudimos leer, excluida."]


_INGRESOS_CSV = (
    b'"Investment Income Transactions as of 06/30/2025"\n'
    b'Transaction Date,Account Number,Account Name,Account Type,Security Description,Symbol,'
    b'Security Type,Transaction Type,Transaction Amount,Income Type,\n'
    b'02/28/2025,...111,Ind,BROKERAGE,Fund A,TSLY,ETFs,Dividend,40.00,Received,\n'
    b'%s,...111,Ind,BROKERAGE,Fund A,TSLY,ETFs,Dividend,%s,Received,\n')


def _con_ingresos(fecha, importe):
    at = _at_con_posiciones_confirmadas()
    df = carga.logic.parse_schwab_income_csv(_INGRESOS_CSV % (fecha, importe))
    at.session_state["_wizard_income_df"] = df
    at.session_state["_wizard_income_summary"] = carga.logic.summarize_income(df)
    at.run()
    assert not at.exception
    return at


def test_el_resumen_de_ingresos_avisa_de_los_pagos_que_quedaron_fuera():
    assert _avisos(_con_ingresos(b"sin fecha", b"25.00")) == [
        "⚠️ 1 pago recibido quedó fuera: no pudimos leer su importe o su fecha."]


def test_el_resumen_de_ingresos_no_avisa_si_no_quedo_nada_fuera():
    assert _avisos(_con_ingresos(b"03/28/2025", b"25.00")) == []

