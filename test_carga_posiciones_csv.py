"""Paso 2 — CSV de posiciones de Charles Schwab (plan 2026-10-04, PR1 frentes A y B).

Todo sintético: cuenta, tickers y cifras inventados. El lector se prueba sobre texto; la UI,
con `AppTest` sustituyendo `st.file_uploader` SOLO para `_vd_upload_pos_csv` y `_vd_fotos`.
Como en `test_carga_foto.py`, AppTest no modela el navegador: se exige `set_value` en el proto
para saber que la cifra llega al campo visible.
"""
import io
import os
import re
import sys

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, os.path.dirname(__file__))
import logic
import promote_case
from ui import carga
from ui.validacion import _excluidos_pendientes

BASE = os.path.dirname(os.path.abspath(__file__))

_CABECERA = (
    '"Symbol","Description","Qty (Quantity)","Price","Price Chng $ (Price Change $)",'
    '"Price Chng % (Price Change %)","Mkt Val (Market Value)","Day Chng $ (Day Change $)",'
    '"Day Chng % (Day Change %)","Cost Basis","Gain $ (Gain/Loss $)","Gain % (Gain/Loss %)",'
    '"Ratings","Reinvest?","Reinvest Capital Gains?","% of Acct (% of Account)",'
    '"Asset Type",\n'
)


def _fila(simbolo, qty, mkt, costo, tipo="ETFs & Closed End Funds"):
    return (f'"{simbolo}","DESCRIPCION, SINTETICA","{qty}","1.00","0.01","0.1%","{mkt}","$1.00",'
            f'"0.1%","{costo}","$0.00","0.0%","A","No","N/A","1.0%","{tipo}",\n')


_TITULO = '"Positions for account Individual ...999 as of 10:00 AM ET, 2026/01/02"\n\n'
_COLA = (
    '"Cash & Cash Investments","--","--","--","--","--","$50.00","$0.00","0%","--","--","--",'
    '"--","--","--","1.0%","Cash and Money Market",\n'
    '"Positions Total","--","--","--","--","--","$9,999.00","$0.00","0%","$8,000.00","--","--",'
    '"--","--","--","--","--",\n'
)

_POSICIONES = (
    _TITULO + _CABECERA
    + _fila("AAA", "12.5", "$1,234.56", "$1,000.00")
    + _fila("BBB", "30", "-$12.34", "$650.50")
    + _fila("CCC", "4", "$100.00", "--")
    + _COLA
).encode("utf-8")


def test_lector_basico():
    r = logic.parse_schwab_positions_csv(_POSICIONES)
    assert set(r) == {"AAA", "BBB", "CCC"}
    assert r["AAA"] == {"shares": 12.5, "cost_basis": 1000.0, "market_value": 1234.56}
    assert r["BBB"]["market_value"] == -12.34
    assert r["CCC"]["cost_basis"] is None          # `--` es «sin dato», no cero


def test_lector_tolera_bom():
    r = logic.parse_schwab_positions_csv(b"\xef\xbb\xbf" + _POSICIONES)
    assert set(r) == {"AAA", "BBB", "CCC"}


def test_lector_no_asume_la_cabecera_en_la_linea_3():
    dos_titulos = ('"Aviso sintetico adicional"\n' + _POSICIONES.decode()).encode()
    r = logic.parse_schwab_positions_csv(dos_titulos)
    assert set(r) == {"AAA", "BBB", "CCC"}


def test_lector_cash_y_total_se_saltan_por_dos_razones_independientes():
    """Un símbolo con forma de ticker de Cash (fondo monetario) o con Asset Type `--` también
    se descarta: la forma del símbolo sola no basta."""
    extra = (_fila("SWVXX", "500", "$500.00", "$500.00", tipo="Cash and Money Market")
             + _fila("ZZZ", "7", "$70.00", "$70.00", tipo="--")
             + _fila("Account Total", "9", "$90.00", "$90.00", tipo="Equity"))
    crudo = (_TITULO + _CABECERA + _fila("AAA", "1", "$1.00", "$1.00") + extra
             + _COLA).encode()
    assert set(logic.parse_schwab_positions_csv(crudo)) == {"AAA"}


def test_lector_varias_cuentas():
    doble = _POSICIONES + b"\n" + _POSICIONES
    assert logic.parse_schwab_positions_csv(doble) == {"error": "varias_cuentas"}


def test_lector_cantidad_cero_o_negativa_se_omite():
    crudo = (_TITULO + _CABECERA + _fila("AAA", "0", "$0.00", "$0.00")
             + _fila("BBB", "-3", "$1.00", "$1.00") + _fila("CCC", "2", "$2.00", "$2.00")
             + _COLA).encode()
    assert set(logic.parse_schwab_positions_csv(crudo)) == {"CCC"}


def test_lector_rechaza_el_csv_de_transacciones_y_basura():
    tx = ('"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"\n'
          '"01/15/2025","Buy","AAA","ETF","40","$25.00","","-$1000.00"\n').encode()
    assert logic.parse_schwab_positions_csv(tx) is None
    assert logic.parse_schwab_positions_csv(b"") is None
    assert logic.parse_schwab_positions_csv(b"\x00\xff\xfe basura") is None


# ── UI ──────────────────────────────────────────────────────────────────────────────

_CSV = (
    '"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"\n'
    '"01/15/2025","Buy","MSTY","ETF SINTETICO A","40","$25.00","","-$1000.00"\n'
    '"01/15/2025","Buy","SCHB","ETF SINTETICO B","10","$20.00","","-$200.00"\n'
    '"01/15/2025","Buy","SLV","ETF SINTETICO C","4","$25.00","","-$100.00"\n'
)
_PREVIA = {
    "MSTY": {"shares": 40.0, "invested": 1000.0},
    "SCHB": {"shares": 10.0, "invested": 200.0},
    "SLV": {"shares": 4.0, "invested": 100.0},
}
_POS_UI = (
    _TITULO + _CABECERA
    + _fila("MSTY", "12.5", "$300.00", "$900.00")
    + _fila("SCHB", "30.25", "$700.00", "$650.50")
    + _fila("AAPL", "3", "$600.00", "$500.00", tipo="Equity")
    + _COLA
).encode("utf-8")
_FOTO = {"MSTY": {"shares": 1.0, "cost_basis": 2.0}, "SLV": {"shares": 3.0, "cost_basis": 4.0}}

_SCRIPT = """
import sys
sys.path.insert(0, {path!r})
import streamlit as st
from ui.carga import render_carga


class _Subido:
    type = "text/csv"

    def __init__(self, clave):
        self._clave = clave

    def getvalue(self):
        return st.session_state.get(self._clave, b"")


_real = st.file_uploader


st.session_state["_test_llamados"] = []


def _uploader(*args, **kwargs):
    st.session_state["_test_llamados"].append(kwargs.get("key"))
    if kwargs.get("key") == "_vd_upload_pos_csv":
        return _Subido("_test_pos_bytes") if st.session_state.get("_test_pos_bytes") else None
    if kwargs.get("key") == "_vd_fotos":
        return [_Subido("_test_foto_bytes")] if st.session_state.get("_test_foto_bytes") else []
    return _real(*args, **kwargs)


st.file_uploader = _uploader
try:
    render_carga()
finally:
    st.file_uploader = _real
""".format(path=BASE)


def _at():
    at = AppTest.from_string(_SCRIPT, default_timeout=40)
    at.session_state["_wizard_df_clean"] = logic.normalize_csv(pd.read_csv(io.StringIO(_CSV)))
    at.session_state["_wizard_csv_ticker_data"] = dict(_PREVIA)
    at.session_state["_wizard_broker"] = "schwab"
    at.session_state["_wizard_csv_name"] = "sintetico.csv"
    return at


def _campo(at, clave):
    return [w for w in at.number_input if w.proto.id.endswith(clave)][0].value


def _proto(at, clave):
    return [w for w in at.number_input if w.proto.id.endswith(clave)][0].proto


def _textos(at):
    return " ".join(str(getattr(e, "value", "")) for e in
                    list(at.markdown) + list(at.warning) + list(at.info) + list(at.caption)
                    + list(at.error))


def _subir_pos(at, crudo=_POS_UI):
    at.session_state["_test_pos_bytes"] = crudo
    at.run()


def _confirmar(at):
    [b for b in at.button if b.proto.id.endswith("_vd_confirm_pos")][0].click()
    at.run()


@pytest.fixture
def sin_clave(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(carga, "_clave_gemini", lambda: None)


@pytest.fixture
def con_foto(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(logic, "extract_positions_from_images",
                        lambda payload, analizables, clave: {t: dict(v) for t, v in
                                                             _FOTO.items()})


def test_el_uploader_del_csv_existe_sin_clave_de_gemini(monkeypatch):
    """El CSV no depende de la clave: el AppTest sustituye el uploader por clave, así que si
    el uploader estuviera dentro de `if clave:` la subida no llegaría a leerse."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(carga, "_clave_gemini", lambda: None)
    at = _at()
    at.run()
    assert not at.exception
    assert "Si lo subes, no hace falta foto" in _textos(at)
    _subir_pos(at)
    assert not at.exception
    assert _campo(at, "_vd_sh_MSTY") == 12.5


def test_csv_llena_los_campos_y_el_ausente_va_a_cero(sin_clave):
    at = _at()
    at.run()
    assert _campo(at, "_vd_sh_MSTY") == 40.0           # vista previa antes de subir
    _subir_pos(at)
    assert not at.exception
    assert _campo(at, "_vd_sh_MSTY") == 12.5
    assert _campo(at, "_vd_cb_MSTY") == 900.0
    assert _campo(at, "_vd_sh_SCHB") == 30.25
    assert _campo(at, "_vd_cb_SCHB") == 650.5
    assert _campo(at, "_vd_sh_SLV") == 0.0
    assert _campo(at, "_vd_cb_SLV") == 0.0
    for clave, valor in (("_vd_sh_MSTY", 12.5), ("_vd_cb_MSTY", 900.0), ("_vd_sh_SLV", 0.0)):
        p = _proto(at, clave)
        assert p.set_value and p.value == valor, clave
    texto = _textos(at)
    assert "SLV no aparece en tu archivo de posiciones: lo pusimos en 0" in texto
    assert "MSTY no aparece" not in texto
    assert "Archivo de posiciones leído" in texto
    assert "2 de 3 instrumentos" in texto                # AAPL no cuenta: no se analiza
    assert "Los valores vienen de tu archivo de posiciones de Schwab" in texto
    assert '<span class="vd-ocr">archivo</span>' in texto
    assert "captura</span>" not in texto
    assert "AAPL" not in texto                           # fuera del análisis: no se muestra


def test_csv_gana_a_la_foto(con_foto):
    at = _at()
    at.session_state["_test_foto_bytes"] = b"foto"
    at.run()
    assert _campo(at, "_vd_sh_MSTY") == 1.0              # sin CSV manda la foto
    texto = _textos(at)
    assert '<span class="vd-ocr">captura</span>' in texto
    assert "archivo</span>" not in texto
    assert "vista previa" in texto
    assert "Los valores vienen de tu archivo de posiciones" not in texto
    at.session_state["_wizard_pos_csv_sig"] = None
    _subir_pos(at)
    assert not at.exception
    assert _campo(at, "_vd_sh_MSTY") == 12.5             # con CSV manda el CSV
    assert _campo(at, "_vd_sh_SLV") == 0.0               # SLV está en la foto pero no en el CSV
    # El stub del script sustituye al uploader de fotos sin dibujar widget, así que no se
    # puede buscar en el árbol: se mira si se pidió.
    assert "_vd_fotos" not in at.session_state["_test_llamados"]
    texto = _textos(at)
    assert "Capturas leídas" not in texto
    assert "en tu captura" not in texto


def test_el_origen_es_archivo_tras_confirmar(sin_clave):
    at = _at()
    at.run()
    _subir_pos(at)
    _confirmar(at)
    origen = at.session_state["_captura_origen"]
    assert origen["MSTY"] == {"shares": "archivo", "cost_basis": "archivo"}
    assert origen["SCHB"] == {"shares": "archivo", "cost_basis": "archivo"}
    assert origen["SLV"] == {"shares": "archivo", "cost_basis": "archivo"}


def test_origen_posiciones_distingue_archivo_de_captura():
    conf = {"A": {"shares": 5.0, "cost_basis": 50.0}}
    leido = {"A": {"shares": 5.0, "cost_basis": 50.0}}
    assert logic.origen_posiciones(conf, leido, {}, fuente_lectura="archivo") == {
        "A": {"shares": "archivo", "cost_basis": "archivo"}}
    assert logic.origen_posiciones(conf, leido, {}) == {
        "A": {"shares": "captura", "cost_basis": "captura"}}
    editado = {"A": {"shares": 6.0, "cost_basis": 50.0}}
    assert logic.origen_posiciones(editado, leido, {}, fuente_lectura="archivo")["A"] == {
        "shares": "editado", "cost_basis": "archivo"}


def test_archivo_es_origen_valido_y_promovible():
    assert "archivo" in logic.CAPTURE_ORIGENES
    assert "archivo" in promote_case.ORIGENES_PROMOVIBLES
    gt = {"A": {"shares": 10.0, "origen_shares": "archivo"},
          "B": {"shares": 20.0, "origen_shares": "vista_previa"}}
    q = {"A": {"level": "ok"}, "B": {"level": "ok"}}
    assert promote_case.promotable_shares(gt, q) == {"A": 10.0}


def test_excluido_abierto_con_origen_archivo_deja_la_cobertura_pendiente():
    tuyos = {"ZZZ": {"skipped": True, "reason": "held_less_than_14_days"}}
    pos = {"ZZZ": {"shares": 5.0, "cost_basis": 50.0}}
    assert _excluidos_pendientes(tuyos, pos, {"ZZZ": {"shares": "archivo"}}) == tuyos
    assert _excluidos_pendientes(tuyos, pos, {"ZZZ": {"shares": "vista_previa"}}) == {}


def _at_confirmado():
    at = _at()
    at.session_state["_wizard_positions"] = {"MSTY": {"shares": 12.5, "cost_basis": 900.0}}
    at.session_state["_wizard_pos_confirmed"] = True
    at.session_state["_wizard_pos_csv"] = {"MSTY": {"shares": 12.5, "cost_basis": 900.0}}
    at.session_state["_wizard_pos_csv_sig"] = "firma"
    at.session_state["_wizard_pos_csv_error"] = "no_reconocido"
    return at


def test_editar_paso_1_borra_las_claves_del_csv():
    for clave in ("_wizard_pos_csv", "_wizard_pos_csv_sig", "_wizard_pos_csv_error"):
        assert clave in carga.CLAVES_CONTEXTO_CARTERA
    at = _at_confirmado()
    at.run()
    assert not at.exception
    [b for b in at.button if b.proto.id.endswith("_vd_edit_csv")][0].click().run()
    assert not at.exception
    filtrado = at.session_state.filtered_state
    for clave in ("_wizard_pos_csv", "_wizard_pos_csv_sig", "_wizard_pos_csv_error"):
        assert clave not in filtrado, clave


def test_editar_paso_2_conserva_el_csv(sin_clave):
    at = _at_confirmado()
    at.run()
    [b for b in at.button if b.proto.id.endswith("_vd_edit_pos")][0].click().run()
    assert not at.exception
    assert at.session_state.filtered_state.get("_wizard_pos_csv")
    assert _campo(at, "_vd_sh_MSTY") == 12.5


def test_quitar_archivo_devuelve_la_vista_previa(sin_clave):
    at = _at()
    at.run()
    _subir_pos(at)
    at.session_state["_test_pos_bytes"] = None
    [b for b in at.button if b.proto.id.endswith("_vd_quitar_pos_csv")][0].click().run()
    assert not at.exception
    assert "_wizard_pos_csv" not in at.session_state.filtered_state
    assert _campo(at, "_vd_sh_MSTY") == 40.0
    assert _proto(at, "_vd_sh_MSTY").set_value


def test_archivo_no_reconocido(sin_clave):
    at = _at()
    at.run()
    _subir_pos(at, _CSV.encode())
    assert not at.exception
    assert "No reconocimos este archivo como el CSV de posiciones de Schwab" in _textos(at)
    assert _campo(at, "_vd_sh_MSTY") == 40.0


def test_csv_sin_ningun_analizable(sin_clave):
    solo_acciones = (_TITULO + _CABECERA + _fila("AAPL", "3", "$600.00", "$500.00",
                                                 tipo="Equity") + _COLA).encode()
    at = _at()
    at.run()
    _subir_pos(at, solo_acciones)
    assert not at.exception
    assert "no trae ninguno de los instrumentos" in _textos(at)
    assert "_wizard_pos_csv" not in at.session_state.filtered_state
    assert _campo(at, "_vd_sh_MSTY") == 40.0


def test_foto_ilegible_no_pisa_lo_tecleado(monkeypatch):
    """Una foto que Gemini no lee devuelve {}: no hay nada que empujar, y empujar la vista
    previa con `set_value` borraría en el navegador lo que el cliente ya escribió."""
    monkeypatch.setenv("GEMINI_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(logic, "extract_positions_from_images", lambda *a, **k: {})
    at = _at()
    at.run()
    [w for w in at.number_input if w.proto.id.endswith("_vd_sh_MSTY")][0].set_value(7.0).run()
    at.session_state["_test_foto_bytes"] = b"foto"
    at.run()
    assert not at.exception
    assert not _proto(at, "_vd_sh_MSTY").set_value


def test_archivo_con_varias_cuentas(sin_clave):
    at = _at()
    at.run()
    _subir_pos(at, _POS_UI + b"\n" + _POS_UI)
    assert "más de una cuenta" in _textos(at)


# ── Frente B: textos de ayuda ────────────────────────────────────────────────────────

_FUENTES_UI = [os.path.join(BASE, "ui", f) for f in sorted(os.listdir(os.path.join(BASE, "ui")))
               if f.endswith(".py")]


def _fuente_ui():
    out = ""
    for ruta in _FUENTES_UI:
        with open(ruta, encoding="utf-8") as f:
            out += f.read()
    return re.sub(r'"\s*\n\s*"', "", out)               # une literales contiguos


@pytest.mark.parametrize("ruta", [
    "Accounts → Transaction History (Historial de transacciones)",
    "Date range «All» → Search → ícono de descarga (Export) → CSV",
    "Accounts → Statements & Tax Forms (Estados de cuenta y formularios) → Document Types "
    "«Tax Forms» → Date range «Current year» → Search",
    "Descarga el que se llama «1042S - año» con el año más alto",
    "Accounts → Statements & Tax Forms → Document Types «Tax Forms»)",
    "Accounts → Investment Income (Ingresos de inversión) → ícono de descarga → Date Range "
    "«All» → Download",
    "elige «All» en el menú **Date Range** del cuadro de exportación",
])
def test_rutas_nuevas_presentes(ruta):
    assert ruta in _fuente_ui()


@pytest.mark.parametrize("vieja", ["Cuenta → Documentos", "Historial → Transacciones",
                                   "amplía el rango", "Cuenta → Historial",
                                   "pestaña Tax Forms", "Tax Forms → Current year", "Tax Forms → Previous"])
def test_rutas_viejas_ausentes(vieja):
    assert vieja not in _fuente_ui()


def test_leer_transacciones_acepta_xlsx_en_mayusculas(monkeypatch):
    llamadas = []
    monkeypatch.setattr(pd, "read_excel", lambda a: llamadas.append(a) or pd.DataFrame())

    class _A:
        name = "MIS_TRANSACCIONES.XLSX"

    _, broker = carga._leer_transacciones(_A())
    assert llamadas and broker == "generic"
