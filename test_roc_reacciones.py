"""Tests de ROC fase 2 (reacciones) del lado Python: frases, validación de la reacción,
y los tres cableados (bloque 1 de la carga, Impuestos y el cálculo con favicon).

El JS de las reacciones se prueba aparte en `test_roc_reacciones_js.py` (DOM falso en node).
Todos los esperados son LITERALES medidos: ningún test calcula el valor esperado con la
función que prueba.
"""
import os
import sys
from types import SimpleNamespace

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

_RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _RAIZ)

import logic
import ui.componentes as componentes
from ui.adapters import roc_csv_frase, roc_impuestos_data

_IB = os.path.join(_RAIZ, "fixtures", "ib_synth_1", "synthetic_transactions.csv")
# 4 tickers (AAPL, MSTY, SCHB, TSLY) y 2 filas SIN símbolo (interés y transferencia).
_SCHWAB = os.path.join(_RAIZ, "fixtures", "schwab_synth_1", "synthetic_transactions.csv")


# ── 1. Frases ───────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("etiqueta, n, frase", [
    ("Interactive Brokers", 3, "Interactive Brokers: 3 tickers leídos."),
    ("Charles Schwab", 1, "Charles Schwab: 1 ticker leído."),
    ("Formato genérico", 0, "Formato genérico: 0 tickers leídos."),
])
def test_roc_csv_frase(etiqueta, n, frase):
    assert roc_csv_frase(etiqueta, n) == frase


def _datos(estado, sin_desglose):
    # `fondos` tiene 3 a propósito: distinto de `fondos_sin_desglose`, para que leer la
    # lista equivocada cambie la cifra.
    return {"fondos": [{"ticker": t} for t in ("MSTY", "SCHB", "TSLY")],
            "peldanos": {"retenido": {"estado": estado, "fondos_sin_desglose": sin_desglose}}}


@pytest.mark.parametrize("datos, frase, reaccion", [
    (_datos("parcial", ["MSTY", "TSLY"]), "En 2 fondos la retención no cuadra.", {"tipo": "ojo"}),
    (_datos("parcial", ["MSTY"]), "En 1 fondo la retención no cuadra.", {"tipo": "ojo"}),
    (_datos("parcial", []), "Casilla por casilla.", None),
    (_datos("ok", []), "Casilla por casilla.", None),
    (_datos("sin_pais", []), "Casilla por casilla.", None),
    ({}, "Casilla por casilla.", None),
    (None, "Casilla por casilla.", None),
])
def test_roc_impuestos_data(datos, frase, reaccion):
    out = roc_impuestos_data(datos)
    assert "frase" in out and "reaccion" in out
    assert out == {"frase": frase, "reaccion": reaccion}


# ── 2. render_roc con reacción ──────────────────────────────────────────────────────────

@pytest.fixture
def capturado(monkeypatch):
    cap = {}

    def _html(html, height=None, scrolling=None):
        cap["html"] = html
        cap["height"] = height

    monkeypatch.setattr(componentes.components, "html", _html)
    return cap


def test_render_roc_pasa_la_reaccion_al_componente(capturado):
    componentes.render_roc("vigilante", "Claro", None, tam=48,
                           reaccion={"tipo": "arrastre", "frase": "Suéltalo."})
    html = capturado["html"]
    assert 'var REACCION = {"tipo": "arrastre", "frase": "Suéltalo."};' in html
    assert "{{" not in html
    assert html.count("function rocGrid") == 1
    assert capturado["height"] == 59


def test_render_roc_sin_reaccion_es_null(capturado):
    componentes.render_roc("vigilante", "Claro", "Interactive Brokers: 3 tickers leídos.", tam=48)
    assert "var REACCION = null;" in capturado["html"]
    assert capturado["height"] == 131


@pytest.mark.parametrize("estado, reaccion", [
    ("alerta", {"tipo": "ojo"}),
    ("vigilante", {"tipo": "favicon"}),
    ("impuestos", {"tipo": "asiente"}),
    ("calculando", {"tipo": "arrastre", "frase": "Suéltalo."}),
    ("vigilante", {"tipo": "bailar"}),
    ("vigilante", {}),
])
def test_render_roc_rechaza_reaccion_incompatible(capturado, estado, reaccion):
    with pytest.raises(ValueError):
        componentes.render_roc(estado, "Claro", None, reaccion=reaccion)
    assert "html" not in capturado


# ── 3. Bloque 1 de la carga ─────────────────────────────────────────────────────────────

_SCRIPT_BLOQUE1 = """
import io
import sys
sys.path.insert(0, __RAIZ__)
import streamlit as st
from ui import carga

class _Archivo(io.BytesIO):
    def __init__(self, datos, nombre):
        super().__init__(datos)
        self.name = nombre

_CASOS = {
    "ninguno": None,
    "vacio": (b"", "x.csv"),
    "dos_columnas": (b"a,b\\n1,2\\n", "x.csv"),
    "ib": (open(__IB__, "rb").read(), "ib.csv"),
    "schwab": (open(__SCHWAB__, "rb").read(), "schwab.csv"),
}
_caso = _CASOS[st.session_state["_prueba_caso"]]
st.file_uploader = lambda *a, **k: (_Archivo(*_caso) if _caso else None)
carga.render_bloque_transacciones()
""".replace("__RAIZ__", repr(_RAIZ)).replace("__IB__", repr(_IB)).replace(
    "__SCHWAB__", repr(_SCHWAB))


def _bloque1(monkeypatch, caso):
    # El script sustituye `st.file_uploader` en el módulo compartido: se restaura al salir.
    monkeypatch.setattr(st, "file_uploader", st.file_uploader)
    at = AppTest.from_string(_SCRIPT_BLOQUE1, default_timeout=25)
    at.session_state["_prueba_caso"] = caso
    at.run()
    return at


def _rocs(at):
    return [f.proto.srcdoc for f in at.get("iframe") if "function rocGrid" in f.proto.srcdoc]


def test_bloque1_sin_archivo_roc_escucha_el_arrastre(monkeypatch):
    at = _bloque1(monkeypatch, "ninguno")
    assert at.exception == []
    rocs = _rocs(at)
    assert len(rocs) == 1
    assert 'var ESTADO = "vigilante";' in rocs[0]
    assert "var FRASE = null;" in rocs[0]
    assert "var TAM = 28;" in rocs[0]
    assert 'var REACCION = {"tipo": "arrastre", "frase": "Suéltalo."};' in rocs[0]


@pytest.mark.parametrize("caso, error", [
    ("vacio", "No pudimos leer el formato del archivo."),
    ("dos_columnas", "Falta(n) la(s) columna(s): Date, Ticker, Amount"),
])
def test_bloque1_csv_rechazado_roc_confundido_y_callado(monkeypatch, caso, error):
    at = _bloque1(monkeypatch, caso)
    assert at.exception == []
    assert len(at.error) == 1 and at.error[0].value.startswith(error)
    rocs = _rocs(at)
    assert len(rocs) == 1
    assert 'var ESTADO = "confundido";' in rocs[0]
    assert "var FRASE = null;" in rocs[0]
    assert "var REACCION = null;" in rocs[0]


def test_bloque1_error_inesperado_roc_confundido(monkeypatch):
    def _revienta(*a, **k):
        raise RuntimeError("parser roto")
    monkeypatch.setattr(logic, "load_and_detect_csv", _revienta)
    at = _bloque1(monkeypatch, "vacio")
    assert at.error[0].value == "Error procesando el archivo: parser roto"
    rocs = _rocs(at)
    assert len(rocs) == 1 and 'var ESTADO = "confundido";' in rocs[0]


def test_bloque1_csv_valido_asiente_una_sola_vez_con_la_cifra_del_resumen(monkeypatch):
    at = _bloque1(monkeypatch, "ib")
    assert at.exception == []
    rocs = _rocs(at)
    assert len(rocs) == 1
    assert 'var FRASE = "Interactive Brokers: 3 tickers leídos.";' in rocs[0]
    assert 'var REACCION = {"tipo": "asiente"};' in rocs[0]
    # Mascota y resumen dicen la MISMA cifra.
    assert any("ib.csv · Interactive Brokers · 3 tickers" in m.value for m in at.markdown)
    # Siguiente rerun: misma frase, ya sin asentir.
    at.run()
    rocs = _rocs(at)
    assert len(rocs) == 1
    assert 'var FRASE = "Interactive Brokers: 3 tickers leídos.";' in rocs[0]
    assert "var REACCION = null;" in rocs[0]


def test_bloque1_no_cuenta_las_filas_sin_simbolo_como_ticker(monkeypatch):
    """Intereses y transferencias llegan con `Symbol` vacío y la limpieza los deja como
    ticker «nan». Contaban como un ticker más en la mascota y el resumen (medido
    2026-10-02: 5 en vez de 4 aquí, 615 en un CSV real). El paso 2 ya los filtraba."""
    at = _bloque1(monkeypatch, "schwab")
    assert at.exception == []
    rocs = _rocs(at)
    assert len(rocs) == 1
    assert 'var FRASE = "Charles Schwab: 4 tickers leídos.";' in rocs[0]
    assert any("schwab.csv · Charles Schwab · 4 tickers" in m.value for m in at.markdown)


_SCRIPT_CARGA = """
import sys
sys.path.insert(0, __RAIZ__)
from ui.chrome import render_encabezado
from ui.carga import render_carga
render_encabezado(False)
render_carga()
""".replace("__RAIZ__", repr(_RAIZ))


def _en_orden(nodo):
    for hijo in getattr(nodo, "children", {}).values():
        yield hijo
        yield from _en_orden(hijo)


def test_carga_un_solo_roc_en_el_encabezado_y_es_el_que_escucha_el_arrastre():
    """La pantalla de carga completa (encabezado + bloques) lleva UN búho, a la DERECHA
    del wordmark, y es el del bloque 1: el que escucha el arrastre. Mutantes que caza:
    el encabezado vuelve a dibujar su propio ROC (dos búhos), o el bloque 1 deja de usar
    el hueco junto al wordmark (el búho cae debajo, en los bloques)."""
    at = AppTest.from_string(_SCRIPT_CARGA, default_timeout=25)
    at.run()
    assert at.exception == []
    orden = []
    for el in _en_orden(at.main):
        srcdoc = getattr(getattr(el, "proto", None), "srcdoc", "")
        if "function rocGrid" in srcdoc:
            orden.append(("roc", srcdoc))
        elif getattr(el, "type", None) == "markdown" and "vd-wordmark" in el.value:
            orden.append(("wordmark", None))
    assert [t for t, _ in orden] == ["wordmark", "roc"]
    assert 'var REACCION = {"tipo": "arrastre", "frase": "Suéltalo."};' in orden[1][1]
    assert "var TAM = 28;" in orden[1][1]
    # A su derecha = en la misma fila horizontal que el wordmark, no más abajo.
    fila = next(el for el in _en_orden(at.main)
                if any(getattr(h, "type", None) == "markdown" and "vd-wordmark" in h.value
                       for h in getattr(el, "children", {}).values()))
    assert any("function rocGrid" in (getattr(getattr(el, "proto", None), "srcdoc", "") or "")
               for el in _en_orden(fila))


def test_carga_sin_frase_de_bloques_y_uploader_sin_help_invisible():
    at = AppTest.from_string(_SCRIPT_CARGA, default_timeout=25)
    at.run()
    textos = "\n".join(m.value for m in at.markdown)
    assert "Tres bloques" not in textos
    assert "¿Dónde lo exporto? Interactive Brokers: Informes → Extractos" in textos
    assert "Tu archivo se procesa en memoria y no se escribe a disco." in textos


# ── 4. Impuestos ────────────────────────────────────────────────────────────────────────

def _impuestos(monkeypatch, datos_fiscales):
    from ui import adapters
    from ui import impuestos as vista_impuestos
    llamadas = []
    monkeypatch.setattr("ui.vistas.obtener_resultados", lambda: {"MSTY": {}})
    monkeypatch.setattr(vista_impuestos.estado, "perfil_fiscal", lambda: {})
    monkeypatch.setattr(adapters, "impuestos_data", lambda *a, **k: datos_fiscales)
    monkeypatch.setattr(componentes, "render_impuestos",
                        lambda datos, tema, *a, **k: llamadas.append("render_impuestos"))
    monkeypatch.setattr(componentes, "render_roc",
                        lambda estado, tema, frase=None, tam=72, reaccion=None:
                        llamadas.append(("render_roc", estado, frase, tam, reaccion)))
    vista_impuestos.render_vista(vista_impuestos.VIEW_ORDER[0],
                                 SimpleNamespace(etf="MSTY", tema="Claro"))
    return llamadas


def test_impuestos_con_retencion_que_no_reconcilia_entrecierra_el_ojo(monkeypatch):
    llamadas = _impuestos(monkeypatch, _datos("parcial", ["MSTY", "TSLY"]))
    assert llamadas == [("render_roc", "impuestos", "En 2 fondos la retención no cuadra.", 64,
                         {"tipo": "ojo"}), "render_impuestos"]


def test_impuestos_normal_sin_reaccion(monkeypatch):
    llamadas = _impuestos(monkeypatch, _datos("ok", []))
    assert llamadas == [("render_roc", "impuestos", "Casilla por casilla.", 64, None),
                        "render_impuestos"]


# ── 5. Cálculo: favicon y retirada aunque el cálculo falle ──────────────────────────────

_SCRIPT_CALCULO = """
import sys
sys.path.insert(0, __RAIZ__)
import pandas as pd
import streamlit as st
import logic
import ui.vistas as vistas

def _analyze(df, position_overrides=None):
    if st.session_state.get("_prueba_falla"):
        raise RuntimeError("mercado caído")
    return {}
logic.analyze_portfolio = _analyze
st.session_state["_wizard_df_clean"] = pd.DataFrame({"ticker": ["MSTY"], "monto": [1.0]})
vistas._resultados()
""".replace("__RAIZ__", repr(_RAIZ))


def _calculo(monkeypatch, falla, espia):
    import ui.vistas as vistas
    monkeypatch.setattr(logic, "analyze_portfolio", logic.analyze_portfolio)
    monkeypatch.setattr(vistas, "render_roc",
                        lambda estado, tema, frase=None, tam=72, reaccion=None:
                        espia.append((estado, reaccion)) or componentes.render_roc(
                            estado, tema, frase, tam, reaccion))
    at = AppTest.from_string(_SCRIPT_CALCULO, default_timeout=25)
    at.session_state["_prueba_falla"] = falla
    at.run()
    return at


def test_calculo_pide_el_favicon_que_gira(monkeypatch):
    espia = []
    at = _calculo(monkeypatch, False, espia)
    assert at.exception == []
    assert espia == [("calculando", {"tipo": "favicon"})]


def test_calculo_que_falla_retira_a_roc_igual(monkeypatch):
    espia = []
    at = _calculo(monkeypatch, True, espia)
    assert at.exception, "el fallo del cálculo debe verse, no tragarse"
    assert espia == [("calculando", {"tipo": "favicon"})]
    assert not any('var ESTADO = "calculando";' in s for s in _rocs(at))
