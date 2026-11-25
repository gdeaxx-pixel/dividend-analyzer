"""Un pago o una operación de IBKR en otra moneda no se cuenta como dólares (auditoría
S6, ING-5): la fila queda fuera, se cuenta y se avisa. Todo sintético."""
import io
import os

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import logic
from test_carga_posiciones_csv import _at
from ui import carga

_RAIZ = os.path.dirname(os.path.abspath(__file__))
_IB_SYNTH = os.path.join(_RAIZ, "fixtures", "ib_synth_1", "synthetic_transactions.csv")

_CABECERA = (b'Statement,Header,Field Name,Field Value\n'
             b'Statement,Data,BrokerName,Interactive Brokers LLC\n')
_TRADES = (b'Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,'
           b'T. Price,C. Price,Proceeds,Comm/Fee,Basis,Realized P/L,Code\n')
_DIVS = b'Dividends,Header,Currency,Date,Description,Amount\n'
_RET = b'Withholding Tax,Header,Currency,Date,Description,Amount,Code\n'

_T_USD = b'Trades,Data,Order,Stocks,USD,SCHD,"2025-01-16, 09:30:00",100,27.5,27.5,-2750,-1,2751,0,O\n'
_T_CAD = b'Trades,Data,Order,Stocks,CAD,XYZ,"2025-01-15, 09:30:00",100,10,10,-1000,-1,1001,0,O\n'
_T_FX = b'Trades,Data,Order,Forex,EUR,EUR.USD,"2025-01-14, 09:30:00",500,1.1,1.1,-550,-2,0,0,\n'
_D_USD = (b'Dividends,Data,USD,2025-02-02,SCHD(US8085247976) Cash Dividend USD 0.25 per Share '
          b'(Ordinary Dividend),250\n')
_D_CAD = (b'Dividends,Data,CAD,2025-02-01,XYZ(CA123) Cash Dividend CAD 0.50 per Share '
          b'(Ordinary Dividend),50\n')
_D_EUR = (b'Dividends,Data,EUR,2025-02-03,ABC(DE123) Cash Dividend EUR 0.10 per Share '
          b'(Ordinary Dividend),10\n')
_D_TOTALES = (b'Dividends,Data,Total,,,300\n'
              b'Dividends,Data,Total in USD,,,285\n'
              b'Dividends,Data,Total Dividends in USD,,,285\n')
_R_USD = (b'Withholding Tax,Data,USD,2025-02-02,SCHD(US8085247976) Cash Dividend USD 0.25 per '
          b'Share - US Tax,-75,\n')
_R_CAD = (b'Withholding Tax,Data,CAD,2025-02-01,XYZ(CA123) Cash Dividend CAD 0.50 per Share - '
          b'CA Tax,-7.5,\n')

_MIXTO = (_CABECERA + _TRADES + _T_CAD + _T_USD + _DIVS + _D_CAD + _D_USD + _D_TOTALES
          + _RET + _R_CAD + _R_USD)
_SOLO_USD = _CABECERA + _TRADES + _T_USD + _DIVS + _D_USD + _D_TOTALES + _RET + _R_USD
_SOLO_CAD = _CABECERA + _TRADES + _T_CAD + _DIVS + _D_CAD + _RET + _R_CAD


def _cadena(crudo_bytes):
    crudo, broker = logic.load_and_detect_csv(io.BytesIO(crudo_bytes))
    return broker, crudo, logic.normalize_csv(crudo)


def _importes(n):
    return {accion: sorted(g["Amount"].tolist()) for accion, g in n.groupby("Action")}


# ── 1. La lectura ───────────────────────────────────────────────────────────────────────

def test_las_filas_en_otra_moneda_no_entran_como_dolares():
    broker, crudo, n = _cadena(_MIXTO)
    assert broker == "ibkr"
    assert sorted(n["Ticker"].unique()) == ["SCHD"]
    assert _importes(n) == {"Buy": [-2750.0], "Dividend": [250.0],
                            "Dividend - Foreign Tax Withholding": [-75.0]}
    assert crudo.attrs["otra_moneda"] == {"total": 3, "por_moneda": {"CAD": 3}}


def test_lo_que_queda_es_lo_mismo_que_un_archivo_solo_en_dolares():
    _, crudo_mixto, mixto = _cadena(_MIXTO)
    _, crudo_usd, usd = _cadena(_SOLO_USD)
    columnas = ["Date", "Action", "Ticker", "Quantity", "Price", "Amount"]
    assert mixto[columnas].reset_index(drop=True).equals(usd[columnas].reset_index(drop=True))
    assert "otra_moneda" not in crudo_usd.attrs
    assert len(crudo_mixto) == len(crudo_usd)


@pytest.mark.parametrize("seccion, fila, accion", [
    (_TRADES, _T_CAD, "Buy"),
    (_DIVS, _D_CAD, "Dividend"),
    (_RET, _R_CAD, "Dividend - Foreign Tax Withholding"),
])
def test_cada_seccion_deja_fuera_su_fila(seccion, fila, accion):
    _, crudo, n = _cadena(_SOLO_USD + seccion + fila)
    assert crudo.attrs["otra_moneda"] == {"total": 1, "por_moneda": {"CAD": 1}}
    assert "XYZ" not in set(n["Ticker"])
    assert len(n[n["Action"] == accion]) == 1


def test_las_filas_de_total_no_cuentan_como_otra_moneda():
    _, crudo, _ = _cadena(_SOLO_USD)
    assert "otra_moneda" not in crudo.attrs
    assert len(crudo) == 6


def test_el_cambio_de_divisas_no_cuenta_como_fila_excluida():
    _, crudo, n = _cadena(_CABECERA + _TRADES + _T_FX + _T_USD + _DIVS + _D_USD)
    assert "otra_moneda" not in crudo.attrs
    assert sorted(n["Ticker"].unique()) == ["SCHD"]


def test_cuenta_por_moneda():
    _, crudo, _ = _cadena(_MIXTO + _DIVS + _D_EUR + _D_EUR)
    assert crudo.attrs["otra_moneda"] == {"total": 5, "por_moneda": {"CAD": 3, "EUR": 2}}


def test_la_moneda_en_minusculas_se_lee_igual():
    _, crudo, n = _cadena(_CABECERA + _DIVS + _D_USD.replace(b",USD,", b",usd,")
                          + _D_CAD.replace(b",CAD,", b", cad ,"))
    assert crudo.attrs["otra_moneda"] == {"total": 1, "por_moneda": {"CAD": 1}}
    assert n["Amount"].tolist() == [250.0]


def test_todo_en_otra_moneda_no_deja_filas_y_lo_dice():
    _, crudo, _ = _cadena(_SOLO_CAD)
    assert crudo.empty
    assert crudo.attrs["otra_moneda"] == {"total": 3, "por_moneda": {"CAD": 3}}


def test_sin_columna_de_moneda_no_se_excluye_nada():
    sin_columna = (_CABECERA + b'Dividends,Header,Date,Description,Amount\n'
                   b'Dividends,Data,2025-02-01,XYZ(CA123) Cash Dividend CAD 0.50 per Share,50\n')
    _, crudo, n = _cadena(sin_columna)
    assert "otra_moneda" not in crudo.attrs
    assert n["Amount"].tolist() == [50.0]


def test_si_ninguna_seccion_se_puede_leer_la_cuenta_no_se_pierde(monkeypatch):
    partir = logic.re.split

    def _falla_en_la_fecha(patron, *a, **k):
        if patron == r'[,;]':
            raise ValueError("fecha")
        return partir(patron, *a, **k)

    monkeypatch.setattr(logic.re, "split", _falla_en_la_fecha)
    crudo = logic.parse_ibkr_csv(_SOLO_CAD)
    assert crudo.attrs["otra_moneda"] == {"total": 3, "por_moneda": {"CAD": 3}}


def test_el_aviso_se_limpia_con_el_resto_de_la_cartera():
    assert "_wizard_csv_otra_moneda" in carga.CLAVES_CONTEXTO_CARTERA
    assert "_wizard_csv_descarte" in carga.CLAVES_CONTEXTO_CARTERA


def test_el_historial_de_transacciones_no_cambia():
    with open(_IB_SYNTH, "rb") as f:
        datos = f.read()
    _, crudo, n = _cadena(datos)
    assert "otra_moneda" not in crudo.attrs
    assert len(crudo) == len(n) == 11
    assert float(crudo["Amount"].sum()) == pytest.approx(-2483.4)


# ── 2. El aviso en pantalla ─────────────────────────────────────────────────────────────

def test_el_texto_concuerda_en_singular_y_en_plural():
    assert carga._texto_otra_moneda({"total": 1, "por_moneda": {"CAD": 1}}) == (
        "1 fila en otra moneda (CAD) quedó fuera: aquí todo se calcula en dólares y no se "
        "convierte.")
    assert carga._texto_otra_moneda({"total": 5, "por_moneda": {"EUR": 2, "CAD": 3}}) == (
        "5 filas en otra moneda (CAD, EUR) quedaron fuera: aquí todo se calcula en dólares y "
        "no se convierte.")


def _avisos(at):
    return [c.value for c in at.caption if c.value.startswith("⚠️")]


def test_con_el_archivo_cargado_se_avisa():
    at = _at()
    at.session_state["_wizard_csv_otra_moneda"] = {"total": 3, "por_moneda": {"CAD": 3}}
    at.run()
    assert not at.exception
    assert _avisos(at) == [
        "⚠️ 3 filas en otra moneda (CAD) quedaron fuera: aquí todo se calcula en dólares y "
        "no se convierte."]


def test_sin_filas_excluidas_no_hay_aviso():
    at = _at()
    at.run()
    assert not at.exception
    assert _avisos(at) == []


_SCRIPT = """
import io
import sys
sys.path.insert(0, __RAIZ__)
import streamlit as st
from ui import carga

class _Archivo(io.BytesIO):
    def __init__(self, datos, nombre):
        super().__init__(datos)
        self.name = nombre

st.file_uploader = lambda *a, **k: _Archivo(st.session_state["_prueba_bytes"], "ib.csv")
carga.render_bloque_transacciones()
""".replace("__RAIZ__", repr(_RAIZ))


def _subir(monkeypatch, datos):
    monkeypatch.setattr(st, "file_uploader", st.file_uploader)
    at = AppTest.from_string(_SCRIPT, default_timeout=25)
    at.session_state["_prueba_bytes"] = datos
    at.run()
    return at


def test_subir_un_archivo_mixto_guarda_la_cuenta_y_la_muestra(monkeypatch):
    at = _subir(monkeypatch, _MIXTO)
    assert not at.exception
    assert at.session_state["_wizard_csv_otra_moneda"] == {"total": 3,
                                                           "por_moneda": {"CAD": 3}}
    assert sorted(at.session_state["_wizard_df_clean"]["Ticker"].unique()) == ["SCHD"]
    assert _avisos(at) == [
        "⚠️ 3 filas en otra moneda (CAD) quedaron fuera: aquí todo se calcula en dólares y "
        "no se convierte."]


def test_subir_un_archivo_en_dolares_borra_el_aviso_anterior(monkeypatch):
    monkeypatch.setattr(st, "file_uploader", st.file_uploader)
    at = AppTest.from_string(_SCRIPT, default_timeout=25)
    at.session_state["_prueba_bytes"] = _SOLO_USD
    at.session_state["_wizard_csv_otra_moneda"] = {"total": 3, "por_moneda": {"CAD": 3}}
    at.run()
    assert not at.exception
    assert at.session_state["_wizard_csv_otra_moneda"] is None
    assert _avisos(at) == []


def test_subir_un_archivo_todo_en_otra_moneda_explica_por_que_no_hay_nada(monkeypatch):
    at = _subir(monkeypatch, _SOLO_CAD)
    assert not at.exception
    assert [e.value for e in at.error] == [
        "3 filas en otra moneda (CAD) quedaron fuera: aquí todo se calcula en dólares y no "
        "se convierte. No quedó nada que analizar."]
    assert "_wizard_df_clean" not in at.session_state
