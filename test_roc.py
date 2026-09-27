"""Tests de ROC, la mascota búho (fase 1): mapeo veredicto→estado, frases, montaje del
componente, motor del sprite en node, favicon y los dos cableados con estado propio
(Salud NAV y carga del análisis).

Todos los esperados son LITERALES medidos: ningún test calcula el valor esperado con la
función que prueba.
"""
import re
import json
import os
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

_RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _RAIZ)

import logic
import ui.componentes as componentes
import ui.vistas as vistas
from ui.adapters import ROC_ESTADOS, roc_salud_data

_SPRITE = os.path.join(_RAIZ, "ui", "componentes", "roc_sprite.js")
_FAVICON = os.path.join(_RAIZ, "ui", "assets", "roc_favicon.png")

# El script de AppTest de `test_carga_*` anota aquí el orden de sus llamadas.
LLAMADAS = []


# ── 1. Mapeo veredicto → estado ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("veredicto, estado", [
    ("destructive", "alerta"),
    ("accounting", "tranquilo"),
    ("mixed", "vigilante"),
    ("insufficient", "confundido"),
])
def test_mapeo_veredicto_a_estado(veredicto, estado):
    r = roc_salud_data({"verdict": veredicto, "nav_cagr": None})
    assert "estado" in r
    assert r["estado"] == estado


# ── 2. Frases ───────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("datos, estado, frase", [
    ({"verdict": "destructive", "nav_cagr": -38.2}, "alerta", "Ojo: NAV -38%/año."),
    ({"verdict": "accounting", "nav_cagr": 1.4}, "tranquilo",
     "NAV +1%/año: ROC contable, no destructivo."),
    ({"verdict": "mixed", "nav_cagr": -6.6}, "vigilante",
     "NAV -7%/año. Señales mezcladas: lo vigilo."),
    ({"verdict": "insufficient", "nav_cagr": -10.0}, "confundido", None),
])
def test_frases_de_roc(datos, estado, frase):
    r = roc_salud_data(datos)
    assert "estado" in r and "frase" in r
    assert r["estado"] == estado
    assert r["frase"] == frase


@pytest.mark.parametrize("veredicto, estado", [
    ("destructive", "alerta"),
    ("accounting", "tranquilo"),
    ("mixed", "vigilante"),
])
def test_sin_nav_roc_calla(veredicto, estado):
    r = roc_salud_data({"verdict": veredicto, "nav_cagr": None})
    assert "estado" in r and "frase" in r
    assert r["estado"] == estado
    assert r["frase"] is None


def test_veredicto_desconocido_no_rompe_la_vista():
    r = roc_salud_data({"verdict": "nuevo_desconocido", "nav_cagr": -5})
    assert "estado" in r and "frase" in r
    assert r == {"estado": "vigilante", "frase": None}


# ── 3. render_roc ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def capturado(monkeypatch):
    cap = {}

    def _html(html, height=None, scrolling=None):
        cap["html"] = html
        cap["height"] = height
        cap["scrolling"] = scrolling

    monkeypatch.setattr(componentes.components, "html", _html)
    return cap


def test_render_roc_rellena_los_huecos_y_pone_estado_frase_y_tema(capturado):
    componentes.render_roc("alerta", "Oscuro", "Ojo: NAV -38%/año.", tam=72)
    html = capturado["html"]
    # Ningún hueco `{{…}}` queda sin rellenar, y el motor del sprite entra UNA sola vez
    # (los comentarios de la plantilla y del motor ya no citan el hueco: antes se inlineaba
    # dos veces, desvío D1 de la auditoría R1).
    assert re.search(r"\{\{\w+\}\}", html) is None
    assert html.count("function rocGrid") == 1
    assert 'var ESTADO = "alerta";' in html
    assert 'data-theme", "dark"' in html
    assert 'var FRASE = "Ojo: NAV -38%/año.";' in html
    assert "var TAM = 72;" in html
    assert capturado["height"] == 157
    assert capturado["scrolling"] is False


def test_render_roc_sin_frase_y_en_tema_claro(capturado):
    componentes.render_roc("vigilante", "Claro", None, tam=72)
    html = capturado["html"]
    assert "var FRASE = null;" in html
    assert 'data-theme", "light"' in html
    assert capturado["height"] == 85


def test_render_roc_estado_desconocido_lanza(capturado):
    with pytest.raises(ValueError):
        componentes.render_roc("feliz", "Claro", None)
    assert "html" not in capturado


# ── 4. alto_roc ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tam, con_frase, esperado", [
    (72, False, 85),
    (72, True, 157),
    (28, False, 38),
    (64, True, 148),
])
def test_alto_roc(tam, con_frase, esperado):
    assert componentes.alto_roc(tam, con_frase) == esperado


# ── 5. Sprite en node ───────────────────────────────────────────────────────────────────

def _rejas(opciones: list) -> list:
    """Una sola llamada a node: la reja (16 filas) de cada `opciones[i]`, más el
    ROC_ESTADOS del propio JS."""
    js = ("var m = require(%s); var ops = %s;"
          "console.log(JSON.stringify({rejas: ops.map(function (o) {"
          " return m.rocGrid(o).map(function (r) { return r.join(''); }); }),"
          " estados: m.ROC_ESTADOS}));" % (json.dumps(_SPRITE), json.dumps(opciones)))
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


_PIDE_NODE = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node no está en el PATH: el guard del sprite NO corrió. Un skip no es un pass.")


@_PIDE_NODE
def test_sprite_filas_literales():
    opciones = [{}, {"st": "alerta"}, {"st": "tranquilo"}, {"st": "confundido"},
                {"st": "impuestos"}, {"face": "back"}, {"face": "r2"}]
    base, alerta, tranquilo, confundido, impuestos, espalda, r2 = _rejas(opciones)["rejas"]
    assert base[0] == "................"
    assert base[5] == ".BEEEEBBBBEEEEB."
    assert base[6] == ".BEPPEBBBBEPPEB."
    assert base[11] == ".WBCCCCCCCCCCBW."
    assert alerta[0] == "..T..........T.."
    assert alerta[5] == ".BEEBBBBBBBBEEB."
    assert alerta[6] == ".BEPPBBBBBBPPEB."
    assert tranquilo[5] == ".BLLLLBBBBLLLLB."
    assert tranquilo[6] == ".BLLLLBBBBLLLLB."
    assert tranquilo[7] == ".BEPPEBKKBEPPEB."
    assert confundido[0] == ".............T.."
    assert confundido[1] == ".............T.."
    assert confundido[4] == ".BBBBBBBBBEPPEB."
    assert impuestos[11] == ".WBCQHHHHHHQCBW."
    assert impuestos[13] == ".WBWQHHHHQQQWBW."
    assert espalda[7] == ".BBBBBBWWBBBBBB."
    assert r2[7] == ".BBBBBBBBBEEPPKK"


@_PIDE_NODE
def test_sprite_ojos_siempre_azules_en_todos_los_estados():
    estados = _rejas([])["estados"]
    assert estados == list(ROC_ESTADOS)
    rejas = _rejas([{"st": e} for e in estados])["rejas"]
    assert len(rejas) == 6
    for estado, reja in zip(estados, rejas):
        assert len(reja) == 16, estado
        assert not any("R" in fila for fila in reja), estado
        assert any("P" in fila for fila in reja), estado


# ── 6. Favicon ──────────────────────────────────────────────────────────────────────────

def test_favicon_de_roc():
    from PIL import Image
    assert os.path.exists(_FAVICON)
    img = Image.open(_FAVICON)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"
    assert img.getpixel((0, 0))[3] == 0
    assert img.getpixel((13, 25)) == (0, 100, 151, 255)
    assert img.getpixel((9, 21)) == (255, 255, 255, 255)
    assert img.getpixel((5, 17)) == (2, 28, 54, 255)


def test_app_usa_el_favicon_de_roc():
    with open(os.path.join(_RAIZ, "app.py"), encoding="utf-8") as f:
        fuente = f.read()
    assert '"roc_favicon.png"' in fuente
    assert 'page_icon="📈"' not in fuente


# ── 7. Integración: Salud NAV ───────────────────────────────────────────────────────────

def test_salud_nav_dibuja_a_roc_con_la_misma_cifra_que_el_detalle(monkeypatch):
    datos = {
        "ticker": "TSLY", "verdict": "destructive", "label": "Destructivo",
        "color": "#b00020", "reason": "El NAV cae.", "headline": "Titular de prueba",
        "plain": "Texto de prueba.", "gauge_score": 10,
        "nav_cagr": -38.2, "roc_pct": 60.0, "total_return_pct": -20.0,
    }
    rocs, captions = [], []
    monkeypatch.setattr(vistas, "_stats_o_aviso", lambda ruta: {"stats": "sintéticos"})
    monkeypatch.setattr(vistas, "salud_nav_data", lambda etf, stats: datos)
    monkeypatch.setattr(vistas.logic, "load_instruments", lambda: {})
    monkeypatch.setattr(vistas, "render_roc",
                        lambda estado, tema, frase=None, tam=72:
                        rocs.append((estado, tema, frase, tam)))
    monkeypatch.setattr(vistas.st, "caption", lambda texto, *a, **k: captions.append(texto))

    vistas.render_salud_nav(SimpleNamespace(etf="TSLY", tema="Claro"))

    assert rocs == [("alerta", "Claro", "Ojo: NAV -38%/año.", 72)]
    assert len(captions) == 1
    assert "NAV -38%/año" in captions[0]
    assert "NAV -38%/año" in rocs[0][2]


# ── 8. Integración: carga del análisis ──────────────────────────────────────────────────

_SCRIPT_CARGA = """
import sys
sys.path.insert(0, __RAIZ__)
import pandas as pd
import streamlit as st
import logic
import test_roc
import ui.vistas as vistas

if not getattr(logic.analyze_portfolio, "_espia_roc", False):
    def _analyze(df, **kw):
        test_roc.LLAMADAS.append("analyze_portfolio")
        return {}
    _analyze._espia_roc = True
    logic.analyze_portfolio = _analyze

if not getattr(vistas.render_roc, "_espia_roc", False):
    _original = vistas.render_roc
    def _roc(estado, tema, frase=None, tam=72, reaccion=None):
        test_roc.LLAMADAS.append(("render_roc", estado))
        return _original(estado, tema, frase, tam, reaccion)
    _roc._espia_roc = True
    vistas.render_roc = _roc

st.session_state["_wizard_df_clean"] = pd.DataFrame({"ticker": ["MSTY"], "monto": [1.0]})
vistas._resultados()
""".replace("__RAIZ__", repr(_RAIZ))


def test_carga_dibuja_a_roc_antes_de_calcular_y_lo_retira_al_terminar(monkeypatch):
    monkeypatch.setattr(logic, "analyze_portfolio", logic.analyze_portfolio)
    monkeypatch.setattr(vistas, "render_roc", vistas.render_roc)
    LLAMADAS.clear()

    at = AppTest.from_string(_SCRIPT_CARGA, default_timeout=25)
    at.run()

    assert at.exception == []
    # (a) ROC «calculando» se dibuja ANTES de que arranque el cálculo.
    assert LLAMADAS == [("render_roc", "calculando"), "analyze_portfolio"]
    # (b) Al terminar el run ya no queda ningún iframe de «calculando».
    srcdocs = [f.proto.srcdoc for f in at.get("iframe")]
    assert not any('var ESTADO = "calculando";' in s for s in srcdocs)


# ── Guards añadidos en la auditoría (X1/X2): encabezado e Impuestos ─────────────────────

_SCRIPT_ENCABEZADO = """
import sys
sys.path.insert(0, __RAIZ__)
import streamlit as st
from ui.chrome import render_encabezado
render_encabezado(st.session_state.get("_con_datos_prueba", False))
""".replace("__RAIZ__", repr(_RAIZ))


@pytest.mark.parametrize("con_datos", [False, True])
def test_encabezado_lleva_a_roc(con_datos):
    """X1: el búho de 28px del encabezado, con y sin datos. Sin datos va solo; con datos va
    junto a la marca «Invierte & Gana»."""
    at = AppTest.from_string(_SCRIPT_ENCABEZADO, default_timeout=25)
    at.session_state["_con_datos_prueba"] = con_datos
    at.run()
    assert not at.exception
    rocs = [f for f in at.get("iframe") if 'var ESTADO = "vigilante";' in f.proto.srcdoc]
    assert len(rocs) == 1
    assert "var TAM = 28;" in rocs[0].proto.srcdoc
    marca = any("Invierte &amp; Gana" in m.value for m in at.markdown)
    assert marca is con_datos


def _impuestos_con(monkeypatch, datos_fiscales):
    from ui import adapters, componentes
    from ui import impuestos as vista_impuestos
    llamadas = []
    monkeypatch.setattr("ui.vistas.obtener_resultados", lambda: {"MSTY": {}})
    monkeypatch.setattr(vista_impuestos.estado, "perfil_fiscal", lambda: {})
    monkeypatch.setattr(adapters, "impuestos_data", lambda *a, **k: datos_fiscales)
    monkeypatch.setattr(componentes, "render_impuestos",
                        lambda datos, tema, *a, **k: llamadas.append("render_impuestos"))
    monkeypatch.setattr(componentes, "render_roc",
                        lambda estado, tema, frase=None, tam=72, reaccion=None:
                        llamadas.append(("render_roc", estado, frase, tam)))
    vista_impuestos.render_vista(vista_impuestos.VIEW_ORDER[0],
                                 SimpleNamespace(etf="MSTY", tema="Claro"))
    return llamadas


def test_impuestos_lleva_a_roc_sobre_la_dona(monkeypatch):
    """X2: ROC con el documento, justo antes de la dona fiscal."""
    llamadas = _impuestos_con(monkeypatch, {"fondos": [{"ticker": "MSTY"}]})
    assert llamadas == [("render_roc", "impuestos", "Casilla por casilla.", 64),
                        "render_impuestos"]


def test_impuestos_sin_dividendos_no_lleva_a_roc(monkeypatch):
    llamadas = _impuestos_con(monkeypatch, None)
    assert llamadas == []


# ── R1-bis: ROC encabeza «La erosión del precio (NAV)» (fila 9, Portafolios) ────────────

from ui.adapters import roc_cartera_data  # noqa: E402


@pytest.mark.parametrize("veredictos, estado, frase", [
    (["destructive", "destructive", "mixed", "accounting", "insufficient"],
     "alerta", "Ojo: 2 de 5 fondos con el NAV encogiéndose."),
    (["mixed", "accounting", "accounting"],
     "vigilante", "1 de 3 fondos con señales mezcladas: los vigilo."),
    (["accounting", "insufficient"], "tranquilo", "1 de 2 fondos con el NAV sano."),
    (["insufficient", "veredicto_raro"], "confundido", None),
    ([], "vigilante", None),
])
def test_roc_cartera_resume_la_lista(veredictos, estado, frase):
    r = roc_cartera_data([{"verdict": v} for v in veredictos])
    assert "estado" in r and "frase" in r
    assert r == {"estado": estado, "frase": frase}


def test_fila_9_dibuja_un_solo_roc_arriba_con_los_mismos_objetos(monkeypatch):
    from ui import adapters, componentes, heredadas
    eventos = []
    veredictos = {"CONY": "destructive", "MSTY": "destructive", "NVDY": "mixed"}

    def _salud(ticker, stats):
        eventos.append(("salud", ticker))
        return {"verdict": veredictos[ticker], "color": "#000", "headline": "H", "plain": "P",
                "nav_cagr": -10.0, "roc_pct": 50.0, "total_return_pct": -5.0, "reason": "R"}

    monkeypatch.setattr(adapters, "salud_nav_data", _salud)
    monkeypatch.setattr(componentes, "render_roc",
                        lambda estado, tema, frase=None, tam=72:
                        eventos.append(("roc", estado, frase, tam)))
    monkeypatch.setattr(heredadas.st, "markdown",
                        lambda texto, *a, **k: eventos.append(("md", texto)))
    monkeypatch.setattr(heredadas.logic, "load_instruments", lambda: {})
    monkeypatch.setattr(heredadas.estado, "perfil_fiscal",
                        lambda: {"rate_declared": False, "rate_pct": 30.0})

    resultados = {t: {} for t in veredictos} | {"PLTY": {"error": "sin datos"}}
    heredadas._portafolio_dividendos(resultados, ["CONY", "MSTY", "NVDY", "PLTY"])

    rocs = [e for e in eventos if e[0] == "roc"]
    assert rocs == [("roc", "alerta", "Ojo: 2 de 3 fondos con el NAV encogiéndose.", 64)]
    # Un solo cálculo por fondo (el ROC no recalcula) y el búho va ANTES del primer titular.
    assert [e for e in eventos if e[0] == "salud"] == [("salud", t) for t in ("CONY", "MSTY", "NVDY")]
    i_roc = eventos.index(rocs[0])
    i_titular = next(i for i, e in enumerate(eventos)
                     if e[0] == "md" and "vd-her-nav-headline" in e[1])
    assert i_roc < i_titular
