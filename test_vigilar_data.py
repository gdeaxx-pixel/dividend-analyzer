"""V1 (2026-09-28) — «Lo que toca vigilar»: adapter `vigilar_data`, componente
`ui/componentes/vigilar.html` y recableado de `ui/heredadas.py`.

Pytest puro. Las cifras esperadas son LITERALES de la spec
`Obsidian/IA/specs-externo-2026-09-28/V1-qwen-lo-que-toca-vigilar.md` §5.2, medidas por
Opus: ningún esperado se calcula con `vigilar_data` ni con sus helpers `_vig_*`.
Fixture sintética con cifras redondas inventadas (el repo es público).
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from ui import adapters
from ui.adapters import VIG_ORDEN_RUTAS, VIG_RUTAS, portafolios_data, vigilar_data

_RAIZ = os.path.dirname(os.path.abspath(__file__))
_VIG_HTML = os.path.join(_RAIZ, "ui", "componentes", "vigilar.html")

# ── Fixture común (literal de la spec §5.2) ────────────────────────────────────────────

DEST = {"pocket_investment": 1000, "market_value": 700, "dividends_net_total": 400,
        "dividends_collected_cash": 50, "net_profit": -250, "roc_accumulated": 300.4,
        "realized_yield": 40.0, "forward_yield": 20.0, "underlying_ticker": "UNDR",
        "underlying_cagr_recent": -40.0,
        "monthly_income": pd.Series([30.0, 0.0, 20.0, 10.0, 15.0])}
SANO = {"pocket_investment": 500, "market_value": 560, "dividends_net_total": 40,
        "net_profit": 100, "roc_accumulated": 5.0}
MIXT = {"pocket_investment": 800, "market_value": 790, "dividends_net_total": 60,
        "net_profit": 50, "roc_accumulated": 10.0, "realized_yield": 9.5}
MIXN = {"pocket_investment": 600, "market_value": 560, "dividends_net_total": 10,
        "net_profit": -30}
RES = {"DEST": DEST, "SANO": SANO, "MIXT": MIXT, "MIXN": MIXN, "SKIP": {"skipped": True}}
SALUD = {"DEST": {"verdict": "destructive", "nav_cagr": -60.0},
         "SANO": {"verdict": "accounting", "nav_cagr": 2.0},
         "MIXT": {"verdict": "mixed", "nav_cagr": -8.0},
         "MIXN": {"verdict": "mixed", "nav_cagr": -5.0},
         "SKIP": {"verdict": "sin_datos"}}


def _num(s):
    return float(s.replace("−", "-").replace("$", "").replace(",", "").replace("+", ""))


# ── V1 · reglas de gravedad y orden ────────────────────────────────────────────────────

def test_reglas_gravedad_y_orden():
    d = vigilar_data(RES, SALUD)
    assert d["eyebrow"] == "Portafolio Dividendos · 4 fondos"
    assert d["sanos"] == "SANO: sin alertas."
    assert [f["ticker"] for f in d["fondos"]] == ["DEST", "MIXT", "MIXN"]

    dest, mixt, mixn = d["fondos"]
    assert [(f["clave"], f["gravedad"], f["cifra"]) for f in dest["flags"]] == [
        ("precio", "alto", "−60% al año"),
        ("cubre", "alto", "faltan $250.00"),
        ("roc", "medio", "ROC ~$300"),
        ("yield", "medio", "40.0% cobrado"),
    ]
    assert [(f["clave"], f["gravedad"], f["cifra"]) for f in mixt["flags"]] == [
        ("precio", "medio", "−8% al año"),
        ("roc", "medio", "ROC ~$10"),
    ]
    assert [(f["clave"], f["gravedad"], f["cifra"]) for f in mixn["flags"]] == [
        ("cubre", "alto", "faltan $30.00"),
        ("precio", "medio", "−5% al año"),
    ]

    def _cab(fo):
        return (fo["chip_texto"], fo["chip_tono"], fo["retorno"], fo["retorno_pct"], fo["tono"])

    assert _cab(dest) == ("Encogiéndose", "loss", "−$250.00", "−25.00%", "neg")
    assert _cab(mixt) == ("Señales mezcladas", "warn", "$50.00", "+6.25%", "pos")
    assert _cab(mixn) == ("Señales mezcladas", "warn", "−$30.00", "−5.00%", "neg")

    # Ningún fondo del fixture está en el menú de Dividendos: no hay ruta a Cash flow.
    assert [r["clave"] for r in d["rutas"]] == ["real", "impuestos", "metodo"]

    assert [(f["clave"], f["tip"]["ruta"]) for f in dest["flags"]] == [
        ("precio", "Comparación › Real"),
        ("cubre", None),
        ("roc", "Impuestos"),
        ("yield", "Método tradicional › La matriz"),
    ]


# ── V2 · la cascada del modal cierra y coincide con Portafolios (regla 3b) ─────────────

def test_cascada_del_modal_cierra_y_coincide_con_portafolios():
    d = vigilar_data(RES, SALUD)
    cubre = next(f for f in d["fondos"][0]["flags"] if f["clave"] == "cubre")
    filas = cubre["tip"]["filas"]
    assert filas == [["Caída del precio", "−$650.00", "loss"],
                     ["Dividendos cobrados", "+$400.00", "cash"],
                     ["Retorno total", "−$250.00", "loss"]]

    g = portafolios_data({"DEST": DEST}, {"DEST": "mode_a"})["grupos"][0]
    assert _num(filas[0][1]) == pytest.approx(g["precio"])
    assert _num(filas[1][1]) == pytest.approx(g["dividendos"])
    assert _num(filas[2][1]) == pytest.approx(g["retorno"])


# ── V3 · el ritmo es el de los últimos 3 meses ─────────────────────────────────────────

def test_ritmo_es_el_de_los_ultimos_3_meses():
    d = vigilar_data(RES, SALUD)
    cubre_dest = next(f for f in d["fondos"][0]["flags"] if f["clave"] == "cubre")
    assert cubre_dest["tip"]["nota"] == (
        "Al ritmo de los últimos 3 meses ($15.00/mes) faltan unos 17 meses para empatar, "
        "si el precio no baja más.")
    cubre_mixn = next(f for f in d["fondos"][2]["flags"] if f["clave"] == "cubre")
    assert cubre_mixn["tip"]["nota"] == (
        "Sin pagos recientes suficientes para estimar cuánto falta.")


# ── V4 · la ruta lleva ETF solo si el fondo está en el menú ────────────────────────────

def test_ruta_lleva_etf_solo_si_esta_en_el_menu():
    d = vigilar_data({"MSTY": dict(MIXN)},
                     {"MSTY": {"verdict": "accounting", "nav_cagr": 1.0}})
    flags = d["fondos"][0]["flags"]
    assert len(flags) == 1 and flags[0]["clave"] == "cubre"
    assert flags[0]["ruta"] == "viaje"
    assert flags[0]["tip"]["ruta"] == "Dividendos › MSTY"
    assert d["rutas"] == [{
        "clave": "viaje", "etiqueta": "Dividendos › MSTY",
        "que": "El recorrido de cada dólar: tu bolsillo, el impuesto, el DRIP y el efectivo.",
        "cat": "dividendos", "vista": "viaje", "etf": "MSTY",
    }]

    # DEST no está en el menú: no hay Cash flow al que mandar.
    d1 = vigilar_data(RES, SALUD)
    cubre_dest = next(f for f in d1["fondos"][0]["flags"] if f["clave"] == "cubre")
    assert cubre_dest["ruta"] is None
    assert cubre_dest["tip"]["ruta"] is None

    d2 = vigilar_data({"MSTY": DEST, "DEST": DEST},
                      {"MSTY": {"verdict": "destructive", "nav_cagr": -10.0},
                       "DEST": {"verdict": "destructive", "nav_cagr": -10.0}})
    r0 = d2["rutas"][0]
    assert (r0["clave"], r0["etiqueta"], r0["etf"]) == ("viaje", "Dividendos › MSTY", "MSTY")


# ── V5 · las rutas apuntan a vistas que existen ────────────────────────────────────────

def test_rutas_apuntan_a_vistas_que_existen():
    import ui.chrome

    for r in VIG_RUTAS.values():
        assert r["cat"] in ui.chrome.CAT_ORDER_TOTAL
        assert r["vista"] in ui.chrome._orden(r["cat"])
    assert set(VIG_ORDEN_RUTAS) == set(VIG_RUTAS)


# ── V6 · base mixta: el neto y net_profit ──────────────────────────────────────────────

def test_base_mixta_usa_el_neto_y_net_profit():
    S = {"pocket_investment": 1000, "market_value": 800, "dividends_net_total": 300,
         "dividends_collected_cash": 400, "net_profit": -100}
    d = vigilar_data({"S": S}, {"S": {}})
    cubre = next(f for f in d["fondos"][0]["flags"] if f["clave"] == "cubre")
    # el neto 300, no el bruto 400; `net_profit`, no `mv + cash − inv`.
    assert cubre["tip"]["filas"] == [["Caída del precio", "−$400.00", "loss"],
                                     ["Dividendos cobrados", "+$300.00", "cash"],
                                     ["Retorno total", "−$100.00", "loss"]]

    E = {"pocket_investment": 1000, "market_value": 900, "dividends_collected_cash": 30,
         "net_profit": -70}
    d2 = vigilar_data({"E": E}, {"E": {}})
    cubre2 = next(f for f in d2["fondos"][0]["flags"] if f["clave"] == "cubre")
    assert cubre2["tip"]["filas"] == [["Caída del precio", "−$100.00", "loss"],
                                      ["Dividendos cobrados", "+$30.00", "cash"],
                                      ["Retorno total", "−$70.00", "loss"]]


# ── V7 · sin fondos → None ─────────────────────────────────────────────────────────────

def test_sin_fondos_devuelve_none():
    assert vigilar_data({}, {}) is None
    assert vigilar_data({"X": {"skipped": True}}, {"X": {}}) is None


# ── V8 · render_vigilar inyecta datos y tema ───────────────────────────────────────────

def test_render_vigilar_inyecta_datos_y_tema(monkeypatch):
    from ui import componentes

    capturado = {}

    def _spy(html, height=None, scrolling=None):
        capturado["html"] = html
        capturado["height"] = height
        capturado["scrolling"] = scrolling

    monkeypatch.setattr(componentes.components, "html", _spy)
    componentes.render_vigilar(vigilar_data(RES, SALUD), "Oscuro")

    html = capturado["html"]
    assert "{{" not in html, "quedó un placeholder sin sustituir"
    assert 'data-theme", "dark"' in html, "el tema no llegó al iframe (lo pone _con_tema)"
    inicio = html.index("const DATA = ") + len("const DATA = ")
    fin = html.index(";\n", inicio)
    payload = json.loads(html[inicio:fin])
    assert payload["fondos"][0]["ticker"] == "DEST"
    assert capturado["height"] == componentes.ALTO_VIGILAR
    assert capturado["scrolling"] is False


# ── V9 · tokens del componente en los cuatro bloques ───────────────────────────────────
# Copia de `test_vista_impuestos_render.py::test_todo_token_usado_esta_en_los_cuatro_bloques`
# apuntando a `vigilar.html`: el iframe no ve `ui/tokens.py`.

def test_tokens_del_componente_en_los_cuatro_bloques():
    with open(_VIG_HTML, encoding="utf-8") as f:
        src = f.read()
    style = src[src.index("<style>"):src.index("</style>")]
    usados = set(re.findall(r"var\((--[\w-]+)\)", src))
    bloques = re.findall(r"(?::root(?:\[data-theme=\"\w+\"])?|@media[^{]+\{\s*:root)\s*\{([^}]*)\}", style)
    assert len(bloques) >= 4, f"esperaba ≥4 bloques de tokens, encontré {len(bloques)}"
    ignora = {"--font-mono", "--font-sans"}   # se declaran una vez, no cambian con el tema
    for tok in sorted(usados - ignora):
        faltan = [i for i, b in enumerate(bloques) if (tok + ":") not in b.replace(" ", "")]
        assert not faltan, f"{tok} usado pero ausente en los bloques de tokens #{faltan}"


# ── V10 · los botones de ruta navegan (AppTest) ────────────────────────────────────────

_RUTAS_V10 = [
    {"clave": "viaje", "etiqueta": "Dividendos › MSTY", "que": "q",
     "cat": "dividendos", "vista": "viaje", "etf": "MSTY"},
    {"clave": "impuestos", "etiqueta": "Impuestos", "que": "q",
     "cat": "impuestos", "vista": "impuestos", "etf": None},
]

_SCRIPT_BOTONES = """
import sys
sys.path.insert(0, {path!r})
from ui import heredadas
RUTAS = {rutas!r}
heredadas._botones_ruta(RUTAS)
""".format(path=_RAIZ, rutas=_RUTAS_V10)


def test_botones_ruta_navegan():
    at = AppTest.from_string(_SCRIPT_BOTONES, default_timeout=25)
    at.run()
    assert at.exception == []

    boton = at.button(key="vd_vig_ruta_viaje")
    assert boton.label == "1 · Dividendos › MSTY →"
    boton.click().run()
    assert at.session_state["vd_categoria"] == "dividendos"
    assert at.session_state["vd_vista"] == "viaje"
    assert at.session_state["vd_etf_dividendos"] == "MSTY"

    at.button(key="vd_vig_ruta_impuestos").click().run()
    assert at.session_state["vd_categoria"] == "impuestos"
    assert at.session_state["vd_vista"] == "impuestos"
    assert at.session_state["vd_etf_dividendos"] == "MSTY", (
        "una ruta sin ETF no debe borrar el ETF de contexto anterior")


# ── V11 · el modal abre la explicación del punto tocado (Node) ─────────────────────────

_PIDE_NODE = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node no está en el PATH: el guard del modal NO corrió. Un skip no es un pass.")

_SCRIPT_RE = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S)

_HARNESS_VIG = r"""
var _all = [];
function _mk(tag) {
  var self = {
    tagName: tag, children: [], _attrs: {}, _classes: [], textContent: "",
    hidden: false,
    appendChild: function (c) { self.children.push(c); c.parentNode = self; return c; },
    removeChild: function (c) { var i = self.children.indexOf(c); if (i >= 0) self.children.splice(i, 1); return c; },
    setAttribute: function (k, v) { self._attrs[k] = String(v); },
    getAttribute: function (k) { return (k in self._attrs) ? self._attrs[k] : null; },
    addEventListener: function () {},
    focus: function () {},
    scrollIntoView: function () {}
  };
  Object.defineProperty(self, "firstChild", {
    get: function () { return self.children.length ? self.children[0] : null; }
  });
  Object.defineProperty(self, "className", {
    get: function () { return self._classes.join(" "); },
    set: function (v) { self._classes = String(v).split(/\s+/).filter(Boolean); }
  });
  self.classList = {
    add: function (c) { if (self._classes.indexOf(c) < 0) self._classes.push(c); },
    remove: function (c) { var i = self._classes.indexOf(c); if (i >= 0) self._classes.splice(i, 1); },
    contains: function (c) { return self._classes.indexOf(c) >= 0; }
  };
  _all.push(self);
  return self;
}
var store = {};
function _attrSel(n, sel) {
  var re = /\[([\w-]+)="([^"]*)"\]/g, m;
  while ((m = re.exec(sel))) { if (n.getAttribute(m[1]) !== m[2]) return false; }
  return true;
}
function _sel(sel) {
  return _all.filter(function (n) { return n._classes.indexOf("flag") >= 0 && _attrSel(n, sel); });
}
globalThis.window = globalThis;
globalThis.document = {
  getElementById: function (id) { if (!store[id]) store[id] = _mk("div"); return store[id]; },
  createElement: function (t) { return _mk(t); },
  querySelectorAll: function (sel) { return _sel(sel); },
  querySelector: function (sel) { var r = _sel(sel); return r.length ? r[0] : null; },
  addEventListener: function () {}
};
/* Estado inicial del HTML real: hint y sanos nacen `hidden`. */
document.getElementById("vig-hint").hidden = true;
document.getElementById("vig-sanos").hidden = true;
__SCRIPT__
function _rows() { return store["vm-rows"] ? store["vm-rows"].children.length : -1; }
function _t(id) { return store[id] ? store[id].textContent : null; }
var out = {};
window.__vigAbrir(0, 1);
out.abrir01 = { title: _t("vm-title"), rows: _rows(), go: _t("vm-go") };
window.__vigAbrir(0, 0);
out.abrir00 = { title: _t("vm-title"), rows: _rows(), go: _t("vm-go") };
window.__vigAbrir(2, 1);
out.abrir21 = { title: _t("vm-title") };
out.sanos = { text: _t("vig-sanos"), hidden: store["vig-sanos"] ? store["vig-sanos"].hidden : null };
out.chips = _all.filter(function (n) { return n._classes.indexOf("chip") >= 0; }).map(function (n) { return n.className; });
out.hint = store["vig-hint"].hidden;
console.log(JSON.stringify(out));
"""


def _corre_node(prog):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as t:
        t.write(prog)
        ruta = t.name
    try:
        r = subprocess.run(["node", ruta], capture_output=True, text=True)
    finally:
        os.unlink(ruta)
    return r


@_PIDE_NODE
def test_el_modal_abre_la_explicacion_del_punto_tocado():
    with open(_VIG_HTML, encoding="utf-8") as f:
        scripts = _SCRIPT_RE.findall(f.read())
    js = scripts[0]   # el de datos/modal; el segundo es el auto-alto y no corre aquí
    assert "{{DATA_JSON}}" in js
    js = js.replace("{{DATA_JSON}}", json.dumps(vigilar_data(RES, SALUD), ensure_ascii=False))
    prog = _HARNESS_VIG.replace("__SCRIPT__", js)
    r = _corre_node(prog)
    assert r.returncode == 0, f"el <script> del componente reventó:\n{r.stderr}"
    out = json.loads(r.stdout.strip().splitlines()[-1])

    assert out["abrir01"]["title"] == "Los dividendos aún no cubren la caída"
    assert out["abrir01"]["rows"] == 3
    assert out["abrir01"]["go"] == ""

    assert out["abrir00"]["go"] == "Estúdialo en Comparación › Real"
    # 3 filas, no 6: `llenar` vacía la tabla entre aperturas.
    assert out["abrir00"]["rows"] == 3

    assert out["abrir21"]["title"] == "El precio da señales mezcladas"

    assert out["sanos"]["hidden"] is False
    assert out["sanos"]["text"] == "SANO: sin alertas."

    # El color del chip ES el estado (rojo encogiéndose, ámbar mezclado): sin esto, un chip
    # que siempre sale rojo pasaba la suite (mutante A4 de la auditoría de Opus).
    assert out["chips"] == ["chip chip-loss", "chip chip-warn", "chip chip-warn"]
    assert out["hint"] is False, "hay puntos clicables: la pista «Toca un punto…» debe verse"
