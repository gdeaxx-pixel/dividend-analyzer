"""Tests del JS de las reacciones de ROC (fase 2) con un DOM falso en node.

Escrito y verificado por Opus (planificador) contra `fase0-r2/roc.html`; el ejecutor lo copia
con `cp`, no lo edita. Corre el script REAL de `ui/componentes/roc.html` (el motor del sprite
+ el script principal; el auto-alto no, que tiene su propio guard) con relojes simulados, un
documento de la app y un documento `top` falsos. Así se miden los EFECTOS que no se ven en
AppTest: el favicon que gira y vuelve al original, el búho expectante al arrastrar un archivo,
los dos asentimientos y el ojo entrecerrado.

Todos los esperados son literales medidos (26-sep-2026).
"""
import json
import os
import re
import shutil
import subprocess

import pytest

_RAIZ = os.path.dirname(os.path.abspath(__file__))
_HTML = os.path.join(_RAIZ, "ui", "componentes", "roc.html")
_SPRITE = os.path.join(_RAIZ, "ui", "componentes", "roc_sprite.js")
_FAVICON_PY = os.path.join(_RAIZ, "tools", "generar_favicon_roc.py")

_PIDE_NODE = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node no está en el PATH: el guard del JS de ROC NO corrió. Un skip no es un pass.")

_ARNES = r"""
var reloj = 0, tareas = [];
function setTimeout(fn, ms) { tareas.push({t: reloj + (ms || 0), fn: fn, rep: 0}); return tareas.length; }
function setInterval(fn, ms) { tareas.push({t: reloj + ms, fn: fn, rep: ms}); return tareas.length; }
function clearTimeout(id) { if (id && tareas[id - 1]) tareas[id - 1].muerta = true; }
function avanzar(ms) {
  var fin = reloj + ms;
  for (;;) {
    var sig = null;
    tareas.forEach(function (x) { if (!x.muerta && x.t <= fin && (!sig || x.t < sig.t)) sig = x; });
    if (!sig) break;
    reloj = sig.t;
    if (sig.rep) sig.t += sig.rep; else sig.muerta = true;
    sig.fn();
  }
  reloj = fin;
}
function Oyente() {
  var o = {};
  return {
    addEventListener: function (t, f) { (o[t] = o[t] || []).push(f); },
    removeEventListener: function (t, f) { o[t] = (o[t] || []).filter(function (g) { return g !== f; }); },
    disparar: function (t, ev) { (o[t] || []).slice().forEach(function (f) { f(ev || {}); }); },
    cuantos: function (t) { return (o[t] || []).length; }
  };
}
function Link(href) {
  var a = {href: href};
  return {getAttribute: function (k) { return a[k]; }, setAttribute: function (k, v) { a[k] = String(v); }};
}
function DocFalso(href) {
  var d = Oyente();
  d.links = [Link(href)];
  d.querySelectorAll = function (sel) { return sel === 'link[rel~="icon"]' ? d.links : []; };
  return d;
}
var docApp = DocFalso("./media/roc.png"), docTop = DocFalso("/~/+/media/roc.png");
var lienzos = 0;
var spr = {innerHTML: ""};
var frase = {textContent: "", hidden: true, _c: null,
  style: {setProperty: function (k, v) { frase._c = v; }}};
var window = Oyente();
window.frameElement = {ownerDocument: docApp, getBoundingClientRect: function () { return {left: 0, top: 0}; }};
window.top = {document: docTop};
window.matchMedia = function () { return {matches: !!OPC.quieto}; };
var document = Oyente();
document.getElementById = function (id) { return id === "spr" ? spr : id === "frase" ? frase : null; };
document.createElement = function () {
  var n = ++lienzos;
  return {width: 0, height: 0,
    getContext: function () { return {fillRect: function () {}, clearRect: function () {}, fillStyle: ""}; },
    toDataURL: function () { return "data:cuadro-" + n; }};
};
spr.getBoundingClientRect = function () { return {left: 0, top: 0, width: 48, height: 51}; };
"""

_ESCENARIOS = r"""
var out = {};
function etiqueta() { var m = /aria-label="([^"]*)"/.exec(spr.innerHTML); return m ? m[1] : null; }
if (OPC.caso === "favicon") {
  var vistos = {};
  for (var i = 0; i < 12; i++) { avanzar(130); vistos[docTop.links[0].getAttribute("href")] = 1; }
  out.cuadros_top = Object.keys(vistos).length;
  out.app_durante = docApp.links[0].getAttribute("href");
  window.disparar("pagehide");
  out.app_tras = docApp.links[0].getAttribute("href");
  out.top_tras = docTop.links[0].getAttribute("href");
}
if (OPC.caso === "arrastre") {
  out.inicio = [etiqueta(), frase.hidden];
  docApp.disparar("dragenter", {dataTransfer: {types: ["text/plain"]}});
  out.con_texto = [etiqueta(), frase.hidden];
  docApp.disparar("dragenter", {dataTransfer: {types: ["Files"]}});
  out.con_archivo = [etiqueta(), frase.hidden, frase.textContent, frase._c];
  avanzar(300); docApp.disparar("dragover", {dataTransfer: {types: ["Files"]}});
  avanzar(300);
  out.sigue = [etiqueta(), frase.hidden];
  avanzar(200);
  out.sin_dragover = [etiqueta(), frase.hidden];
  docTop.disparar("dragenter", {dataTransfer: {types: ["Files"]}});
  out.desde_top = etiqueta();
  docTop.disparar("drop", {});
  out.tras_soltar = etiqueta();
  window.disparar("pagehide");
  out.oyentes_tras_pagehide = docApp.cuantos("dragenter") + docApp.cuantos("dragover") + docApp.cuantos("drop");
}
if (OPC.caso === "asiente") {
  var nodos = 0, abajo = false;
  for (var k = 0; k < 40; k++) {
    avanzar(50);
    var b = spr.innerHTML.indexOf('class="pP" x="3" y="8"') >= 0;
    if (b && !abajo) nodos++;
    abajo = b;
  }
  out.asentimientos = nodos;
  out.al_final_abajo = abajo;
}
if (OPC.caso === "solo_frase") {
  avanzar(20000);
  out.spr = [spr.innerHTML, !!spr.hidden];
  out.frase = [frase.hidden, frase.textContent, frase._c];
  out.tareas = tareas.length;
  out.oyentes = docApp.cuantos("dragenter") + docApp.cuantos("mousemove");
}
if (OPC.caso === "ojo") {
  out.parpado_izq = spr.innerHTML.indexOf('class="pL" x="2" y="5"') >= 0;
  out.parpado_der = spr.innerHTML.indexOf('class="pL" x="10" y="5"') >= 0;
  out.color = frase._c;
}
console.log(JSON.stringify(out));
"""


def _scripts(estado, frase, tam, reaccion, buho=True):
    """El sprite y el script principal de roc.html con los huecos rellenos igual que
    `render_roc` (el auto-alto, tercer <script>, se deja fuera)."""
    with open(_HTML, encoding="utf-8") as f:
        html = f.read()
    with open(_SPRITE, encoding="utf-8") as f:
        sprite = f.read()
    html = (html.replace("{{ESTADO_JSON}}", json.dumps(estado))
                .replace("{{FRASE_JSON}}", json.dumps(frase, ensure_ascii=False))
                .replace("{{TAM}}", str(tam))
                .replace("{{REACCION_JSON}}", json.dumps(reaccion, ensure_ascii=False))
                .replace("{{BUHO_JSON}}", json.dumps(buho))
                .replace("{{SPRITE_JS}}", sprite))
    bloques = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert len(bloques) == 3, f"roc.html debería tener 3 <script>, tiene {len(bloques)}"
    return bloques[0] + "\n" + bloques[1]


def _correr(caso, estado, frase, tam, reaccion, quieto=False, buho=True):
    js = ("var OPC = %s;\n" % json.dumps({"caso": caso, "quieto": quieto})
          + _ARNES + _scripts(estado, frase, tam, reaccion, buho) + _ESCENARIOS)
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@_PIDE_NODE
def test_favicon_gira_en_los_dos_documentos_y_vuelve_al_original():
    out = _correr("favicon", "calculando", "Leyendo tu portafolio…", 64, {"tipo": "favicon"})
    assert out["cuadros_top"] == 6
    assert out["app_durante"].startswith("data:cuadro-")
    assert out["app_tras"] == "./media/roc.png"
    assert out["top_tras"] == "/~/+/media/roc.png"


@_PIDE_NODE
def test_calculando_sin_reaccion_no_toca_el_favicon():
    out = _correr("favicon", "calculando", "Leyendo tu portafolio…", 64, None)
    assert out["cuadros_top"] == 1
    assert out["app_durante"] == "./media/roc.png"


@_PIDE_NODE
@pytest.mark.parametrize("quieto", [False, True])
def test_arrastre_de_archivo_pone_expectante_y_vuelve(quieto):
    out = _correr("arrastre", "vigilante", None, 48,
                  {"tipo": "arrastre", "frase": "Suéltalo."}, quieto=quieto)
    assert out == {
        "inicio": ["ROC, vigilante", True],
        "con_texto": ["ROC, vigilante", True],
        "con_archivo": ["ROC, expectante", False, "Suéltalo.", "var(--warn)"],
        "sigue": ["ROC, expectante", False],
        "sin_dragover": ["ROC, vigilante", True],
        "desde_top": "ROC, expectante",
        "tras_soltar": "ROC, vigilante",
        "oyentes_tras_pagehide": 0,
    }


@_PIDE_NODE
def test_asiente_dos_veces_y_termina_arriba():
    out = _correr("asiente", "vigilante", "Interactive Brokers: 3 tickers leídos.", 48,
                  {"tipo": "asiente"})
    assert out == {"asentimientos": 2, "al_final_abajo": False}


@_PIDE_NODE
def test_sin_reaccion_no_asiente():
    out = _correr("asiente", "vigilante", "Interactive Brokers: 3 tickers leídos.", 48, None)
    assert out == {"asentimientos": 0, "al_final_abajo": False}


@_PIDE_NODE
def test_ojo_entrecerrado_solo_el_izquierdo_y_frase_en_warn():
    out = _correr("ojo", "impuestos", "En 2 fondos la retención no cuadra.", 64, {"tipo": "ojo"})
    assert out == {"parpado_izq": True, "parpado_der": False, "color": "var(--warn)"}


@_PIDE_NODE
def test_reaccion_incompatible_se_ignora_en_el_js():
    # Python ya la rechaza (`render_roc` lanza); el JS, además, no la aplica.
    out = _correr("ojo", "alerta", "Ojo: NAV -38%/año.", 72, {"tipo": "ojo"})
    assert out == {"parpado_izq": False, "parpado_der": False, "color": "var(--loss)"}


def test_paleta_del_favicon_animado_es_la_del_favicon_estatico():
    with open(_HTML, encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"var FAV = \{(.*?)\};", html, re.S)
    assert m, "roc.html no declara la paleta FAV"
    js = {k: v.lower() for k, v in re.findall(r'(\w): "(#[0-9A-Fa-f]{6})"', m.group(1))}
    with open(_FAVICON_PY, encoding="utf-8") as f:
        py = f.read()
    tuplas = re.findall(r'"(\w)": \(0x(\w\w), 0x(\w\w), 0x(\w\w), 255\)', py)
    estatica = {k: ("#" + r + g + b).lower() for k, r, g, b in tuplas}
    assert len(estatica) == 9
    assert js == estatica


@_PIDE_NODE
@pytest.mark.parametrize("estado,reaccion,color", [
    ("alerta", None, "var(--loss)"),
    ("impuestos", {"tipo": "ojo"}, "var(--warn)"),
    ("calculando", {"tipo": "favicon"}, "var(--drip)"),
])
def test_solo_frase_no_dibuja_buho_ni_anima(estado, reaccion, color):
    """`buho=False` (el búho vive en el encabezado, Daniel 2026-09-28): solo la frase, con el
    color del estado; sin sprite, sin temporizadores y sin oyentes — un favicon o un arrastre
    duplicados abajo pelearían con los del búho de arriba."""
    out = _correr("solo_frase", estado, "Frase de prueba.", 64, reaccion, buho=False)
    assert out == {"spr": ["", True], "frase": [False, "Frase de prueba.", color],
                   "tareas": 0, "oyentes": 0}
