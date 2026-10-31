"""P6 de la propuesta de interfaz (2026-10-30): «Lo que toca vigilar» ordenado por lo que cuesta
y con una fila por fondo.

Antes los fondos iban en el orden de `salud_por_ticker` (alfabético), así que el que más dinero
perdía podía quedar segundo o tercero, y cada punto ocupaba una fila de 56 px con su frase
completa: con 6 fondos de 4 puntos, 2,069 px a 1280 de ancho y 3,170 a 375 (medido en Chromium).
Ahora el que más pierde va arriba y cada punto es una etiqueta corta («Precio −60% al año»,
«Faltan $250.00») que abre el mismo popup aprobado. La frase completa sigue en el popup y en el
`aria-label`; el orden de gravedad dentro del fondo no cambia.

Cifras sintéticas: las de `test_vigilar_data.py`, literales de la spec V1.
"""
import json

import pytest

from test_vigilar_data import (DEST, MIXN, MIXT, RES, SALUD, _HARNESS_VIG, _PIDE_NODE,
                               _SCRIPT_RE, _VIG_HTML, _corre_node)
from ui import componentes
from ui.adapters import vigilar_data


# ── Orden ────────────────────────────────────────────────────────────────────────────────

def test_el_que_mas_pierde_va_arriba():
    """Alfabético: AAA, BBB, CCC. Por lo que pierden: BBB (−$250), AAA (−$30), CCC (+$50)."""
    res = {"AAA": dict(MIXN), "BBB": dict(DEST), "CCC": dict(MIXT)}
    salud = {"AAA": SALUD["MIXN"], "BBB": SALUD["DEST"], "CCC": SALUD["MIXT"]}
    assert [fo["ticker"] for fo in vigilar_data(res, salud)["fondos"]] == ["BBB", "AAA", "CCC"]


def test_a_igual_perdida_manda_el_ticker():
    res = {"ZZZ": dict(DEST), "AAA": dict(DEST)}
    salud = {"ZZZ": SALUD["DEST"], "AAA": SALUD["DEST"]}
    assert [fo["ticker"] for fo in vigilar_data(res, salud)["fondos"]] == ["AAA", "ZZZ"]


def test_la_cabecera_dice_el_orden_solo_con_varios_fondos():
    assert vigilar_data(RES, SALUD)["eyebrow"].endswith(" · el que más te cuesta, arriba")
    uno = vigilar_data({"DEST": dict(DEST), "SANO": RES["SANO"]},
                       {"DEST": SALUD["DEST"], "SANO": SALUD["SANO"]})
    assert uno["eyebrow"] == "Portafolio Dividendos · 2 fondos"


# ── Etiquetas cortas ─────────────────────────────────────────────────────────────────────

def test_cada_punto_trae_su_etiqueta_corta():
    dest, mixn, mixt = vigilar_data(RES, SALUD)["fondos"]
    assert [(f["clave"], f["corto"]) for f in dest["flags"]] == [
        ("precio", "Precio −60% al año"),
        ("cubre", "Faltan $250.00"),
        ("roc", "ROC ~$300"),
        ("yield", "Yield 40.0% cobrado"),
    ]
    assert [f["corto"] for f in mixn["flags"]] == ["Faltan $30.00", "Precio −5% al año"]
    assert [f["corto"] for f in mixt["flags"]] == ["Precio −8% al año", "ROC ~$10"]


@pytest.mark.parametrize("veredicto, esperado", [
    ("destructive", "Precio a la baja"), ("mixed", "Precio con señales mezcladas")])
def test_sin_ritmo_del_precio_la_etiqueta_dice_la_direccion(veredicto, esperado):
    d = vigilar_data({"DEST": dict(DEST)}, {"DEST": {"verdict": veredicto, "nav_cagr": None}})
    precio = next(f for f in d["fondos"][0]["flags"] if f["clave"] == "precio")
    assert precio["cifra"] is None
    assert precio["corto"] == esperado


# ── El componente: una fila de etiquetas por fondo ───────────────────────────────────────

_HARNESS_FILAS = _HARNESS_VIG.split("__SCRIPT__")[0] + "__SCRIPT__" + r"""
var flags = _all.filter(function (n) { return n._classes.indexOf("flag") >= 0; });
console.log(JSON.stringify({
  textos: flags.map(function (n) { return n.textContent; }),
  arias: flags.map(function (n) { return n.getAttribute("aria-label"); }),
  padres: flags.map(function (n) { return n.parentNode ? n.parentNode.className : null; }),
  lis: _all.filter(function (n) { return String(n.tagName).toLowerCase() === "li"; }).length,
  hint: store["vig-hint"].hidden,
}));
"""


@_PIDE_NODE
def test_cada_punto_es_una_etiqueta_corta_en_la_fila_de_su_fondo():
    with open(_VIG_HTML, encoding="utf-8") as f:
        js = _SCRIPT_RE.findall(f.read())[0]
    js = js.replace("{{DATA_JSON}}", json.dumps(vigilar_data(RES, SALUD), ensure_ascii=False))
    r = _corre_node(_HARNESS_FILAS.replace("__SCRIPT__", js))
    assert r.returncode == 0, f"el <script> del componente reventó:\n{r.stderr}"
    out = json.loads(r.stdout.strip().splitlines()[-1])

    assert out["textos"] == ["Precio −60% al año", "Faltan $250.00", "ROC ~$300",
                             "Yield 40.0% cobrado", "Faltan $30.00", "Precio −5% al año",
                             "Precio −8% al año", "ROC ~$10"]
    assert out["lis"] == 0, "los puntos volvieron a ir en filas de lista, uno por línea"
    assert set(out["padres"]) == {"pills"}
    # La frase completa y la gravedad siguen al alcance del lector de pantalla.
    assert out["arias"][0] == "Alto: El precio se está encogiendo, −60% al año. Ver qué pasa."
    assert out["arias"][6] == "Medio: El precio da señales mezcladas, −8% al año. Ver qué pasa."
    assert out["hint"] is False


_MEDIR = """() => ({
  alto: Math.ceil(document.getElementById('vig-root').getBoundingClientRect().height),
  fondos: document.querySelectorAll('.fund').length,
  desborde: document.documentElement.scrollWidth > innerWidth,
  tonos: ['.flag.alto', '.flag.medio'].map(sel => {
    const c = getComputedStyle(document.querySelector(sel));
    return [c.backgroundColor, c.borderLeftColor];
  }),
})"""


@pytest.fixture(scope="module")
def altos():
    """6 fondos de 4 puntos, el caso del que salió la propuesta. Una página por medida:
    `set_content` reutiliza la ventana y el segundo `const DATA` revienta."""
    sync_api = pytest.importorskip("playwright.sync_api")
    res, salud = {}, {}
    for i, tk in enumerate(("MSTY", "CONY", "TSLY", "PLTY", "NFLY", "NVDY")):
        res[tk] = dict(DEST, net_profit=-250 - 37 * i)
        salud[tk] = {"verdict": "destructive", "nav_cagr": -60.0 - i}
    html = componentes._con_tema(componentes._plantilla("vigilar.html"), "Claro").replace(
        "{{DATA_JSON}}", json.dumps(vigilar_data(res, salud), ensure_ascii=False))
    out = {}
    try:
        with sync_api.sync_playwright() as pw:
            nav = pw.chromium.launch()
            for ancho in (1280, 375, 320):
                pagina = nav.new_page(viewport={"width": ancho, "height": 900})
                pagina.set_content(html)
                out[ancho] = pagina.evaluate(_MEDIR)
                pagina.close()
            nav.close()
    except Exception as error:  # sin Chromium instalado (CI)
        pytest.skip(f"Chromium no disponible: {error}")
    return out


@pytest.mark.parametrize("ancho, techo", [(1280, 1000), (375, 1500), (320, 1500)])
def test_seis_fondos_caben_en_menos_de_la_mitad_del_alto_de_antes(altos, ancho, techo):
    """Antes: 2,069 px a 1280 y 3,170 a 375. Medido tras P6: 841 y 1,276."""
    m = altos[ancho]
    assert m["fondos"] == 6, "el componente no dibujó los 6 fondos"
    assert m["alto"] <= techo, f"a {ancho} px «Vigilar» mide {m['alto']} px (techo {techo})"
    assert not m["desborde"], f"a {ancho} px algo se sale de lado"


def test_alto_y_medio_se_distinguen_a_la_vista(altos):
    """Sin la palabra «Alto» / «Medio» en la fila, la gravedad la dicen el fondo y el borde."""
    alto, medio = altos[1280]["tonos"]
    assert alto[0] != medio[0], "las etiquetas de gravedad alta y media tienen el mismo fondo"
    assert alto[1] != medio[1], "las etiquetas de gravedad alta y media tienen el mismo borde"
