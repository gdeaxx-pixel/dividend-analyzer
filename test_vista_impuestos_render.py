"""PR 1 «la mudanza» — la vista «Impuestos» se parte en 5 pantallas
(`ui.impuestos.VIEW_ORDER`) sin cambiar contenido: cada una RENDERIZA un trozo distinto
del mismo objeto fiscal.

Dos capas:

1. DESPACHO (`render_impuestos` inyecta la vista, alto por vista, cinturón de
   `impuestos.render_vista`). Estos auditan el FLAG.
2. CONSECUENCIA — se EJECUTA el `<script>` del componente en Node con un `document`
   de juguete y se mira el DOM resultante: cada vista deja solo su sección y sus
   marcadores, y quita las otras cuatro. Gate del repo: el mutante que pone las 6
   ramas de vista en `if (true)` tiene que poner ESTOS tests en rojo, o no valen.

La aritmética la siguen pineando `test_vista_impuestos.py` (por datos, no por marcado).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import ui.componentes as componentes  # noqa: E402
from ui import impuestos  # noqa: E402

_DATOS = {"fondos": [{"ticker": "MSTY"}], "peldanos": {}, "declarado": False}

_HTML = os.path.join(os.path.dirname(__file__), "ui", "componentes", "impuestos.html")
_SCRIPT_RE = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S)

# `_D` NO es un objeto fiscal coherente — es un dict que toca todas las ramas de RENDER
# de las 5 vistas (peldaños 1-6, tabla con buckets, Ruta A/B). La coherencia la piñan
# `test_vista_impuestos.py` contra el adapter real.
_D = {
    "declarado": True, "pais": "México", "tasa_pct": 10, "tiene_tratado": True,
    "residencia_1042s": {},
    "concentracion": {"otro_ticker": "SCHB", "pct": 92.1, "ticker": "MSTY",
                      "retenido": 80.0, "otro_retenido": 2.0},
    "peldanos": {
        "bruto": {"monto": 5827.18, "pct": 100.0},
        "gravable": {"monto": 2102.31, "pct": 36.1, "sin_roc": [], "cubiertos": 3, "total": 3},
        "corresponde": {"monto": 210.23, "pct": 3.6},
        "retenido": {
            "estado": "ok", "monto": 80.0, "pct": 1.37,
            "correcta": {"monto": 20.0, "pct": 0.34},
            "recuperable_roc": {"monto": 41.29, "pct": 0.71},
            "gap_w8ben": {"monto": 18.71, "pct": 0.32},
            "ya_devuelto": {"monto": 20.0, "pct": 0.34},
        },
    },
    "ganancias_capital": {
        "retencion_eeuu": 0.0,
        "no_realizado": {"monto": 1212.97, "valor_mercado": 12668.69, "base": 11455.72, "n_fondos": 2},
        "realizado": {"monto": 300.0, "n_ventas": 1, "n_fondos": 1},
        "n_fondos_total": 2, "tickers_indeterminados": [], "tickers_base_captura": [],
    },
    "impuesto_local": {
        "dividendos": {"bruto": 5827.18, "roc": 3724.87, "gravable_eeuu": 2102.31},
        "credito_eeuu": {"monto": 60.75, "definitivo": 19.46, "vuelve_por_roc": 41.29},
        "realizado_por_tramo": {
            "ge_2y": {"monto": 300.0, "n_ventas": 1},
            "lt_2y": {"monto": 0.0, "n_ventas": 0},
            "sin_tramo": {"monto": 0.0, "n_ventas": 0},
        },
        "no_realizado_excluido": 1212.97, "corte_tramo_dias": 730,
    },
    "ruta_a": {"tiene_1042s": False, "sin_retencion": False,
               "casilla9_esperada": 41.29, "veredicto": "pendiente"},
    "fondos": [
        {"ticker": "MSTY", "bruto": 5000.0, "roc_pct": 61, "gravable": 1950.0,
         "corresponde": 195.0, "retenido": 78.0, "ya_devuelto": 19.0, "indeterminado": False,
         "retencion_correcta": 19.0, "recuperable_roc": 40.0, "gap_w8ben": 19.0},
        {"ticker": "SCHB", "bruto": 827.18, "roc_pct": 0, "gravable": 152.31,
         "corresponde": 15.23, "retenido": 2.0, "ya_devuelto": 1.0, "indeterminado": False,
         "retencion_correcta": 1.0, "recuperable_roc": 1.29, "gap_w8ben": 0.0},
    ],
    "slots_pendientes": [],
}

# `document` de juguete: `getElementById` + `.innerHTML` + `.remove()`, lo único que
# toca el primer <script>. `impTabla` muere con su `impBlock` (contención real).
_HARNESS = r"""
var IDS = ["impLede","impTitle","impEscalera","impTabla","impTablaExtra","impRutas","impFoot","impBlock"];
var store = {};
IDS.forEach(function (id) {
  store[id] = { id: id, innerHTML: "", removed: false, remove: function () { this.removed = true; } };
});
function _muerto(id) {
  return store[id].removed
    || ((id === "impTabla" || id === "impTablaExtra") && store.impBlock.removed);
}
globalThis.document = { getElementById: function (id) {
  var el = store[id];
  return (!el || _muerto(id)) ? null : el;
} };
__SCRIPT__
var rep = {};
IDS.forEach(function (id) {
  var d = _muerto(id);
  rep[id] = { alive: !d, html: d ? null : store[id].innerHTML };
});
console.log(JSON.stringify(rep));
"""

_ORDER = impuestos.VIEW_ORDER
_TITULOS = {
    "corte": "La escalera de tus impuestos",
    "fondos": "De dónde salió cada dólar de retención",
    "venta": "Vender no es cobrar un dividendo",
    "pais": "La base y el crédito",
    "recuperar": "Lo que vuelve solo y lo que hay que reclamar",
}


def _primer_script():
    with open(_HTML, encoding="utf-8") as f:
        return _SCRIPT_RE.findall(f.read())[0]


def _ejecutar(vista, script=None, d=None):
    js = _primer_script() if script is None else script
    js = js.replace("{{DATA_JSON}}", json.dumps(_D if d is None else d, ensure_ascii=False))
    js = js.replace("{{VISTA_ACTIVA}}", vista)
    prog = _HARNESS.replace("__SCRIPT__", js)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as t:
        t.write(prog)
        ruta = t.name
    try:
        r = subprocess.run(["node", ruta], capture_output=True, text=True)
    finally:
        os.unlink(ruta)
    assert r.returncode == 0, f"el <script> reventó en la vista {vista!r}:\n{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def _assert_vista(vista, rep):
    """El DOM resultante de `vista`: su sección presente con sus marcadores, las otras
    cuatro fuera. Lo que rompe con el mutante if(true)x6."""
    esc, blk, tab = rep["impEscalera"], rep["impBlock"], rep["impTabla"]
    rut, foot, lede, tit = rep["impRutas"], rep["impFoot"], rep["impLede"], rep["impTitle"]

    assert tit["alive"] and _TITULOS[vista] in tit["html"], (
        f"{vista}: h2 = {tit['html']!r}, esperaba que contuviera {_TITULOS[vista]!r}")

    if vista == "corte":
        assert esc["alive"]
        for marca in ('class="imp-verdict"', "De cada dólar que repartieron tus fondos",
                      "Lo que el bróker se llevó — a la misma escala"):
            assert marca in esc["html"], f"corte sin {marca!r}"
        for n in ("Peldaño 5", "Peldaño 6"):
            assert n not in esc["html"], f"corte trae {n} — no aisló su sección"
        for gone in ("impBlock", "impRutas", "impFoot"):
            assert not rep[gone]["alive"], f"corte dejó {gone} en el DOM"
        assert lede["alive"], "corte perdió su lede"
    elif vista == "fondos":
        assert blk["alive"] and tab["alive"] and "<tr" in tab["html"]
        for gone in ("impEscalera", "impRutas", "impFoot", "impLede"):
            assert not rep[gone]["alive"], f"fondos dejó {gone} en el DOM"
    elif vista == "venta":
        assert esc["alive"] and "Peldaño 5" in esc["html"]
        for n in ("Peldaño 1", "Peldaño 4", "Peldaño 6"):
            assert n not in esc["html"], f"venta trae {n}"
        for gone in ("impBlock", "impRutas", "impFoot"):
            assert not rep[gone]["alive"], f"venta dejó {gone} en el DOM"
        assert lede["alive"], "venta perdió su lede"
    elif vista == "pais":
        assert esc["alive"] and "Peldaño 6" in esc["html"]
        for n in ("Peldaño 1", "Peldaño 5"):
            assert n not in esc["html"], f"pais trae {n}"
        for gone in ("impBlock", "impRutas", "impFoot"):
            assert not rep[gone]["alive"], f"pais dejó {gone} en el DOM"
        assert lede["alive"], "pais perdió su lede"
    elif vista == "recuperar":
        assert rut["alive"] and "Ruta A" in rut["html"] and "Ruta B" in rut["html"]
        assert foot["alive"] and foot["html"].strip()
        for gone in ("impEscalera", "impBlock", "impLede"):
            assert not rep[gone]["alive"], f"recuperar dejó {gone} en el DOM"
    else:
        raise AssertionError(f"vista desconocida {vista!r}")


_node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node ausente: el gate de CONSECUENCIA no corre — y un skip no es un pass")


def _captura(monkeypatch):
    caja = {}

    def _fake_html(html, height=None, scrolling=None):
        caja["html"] = html
        caja["height"] = height

    monkeypatch.setattr(componentes.components, "html", _fake_html)
    return caja


def test_viewset_tiene_las_cinco_vistas_en_orden():
    assert tuple(impuestos.VIEWS) == impuestos.VIEW_ORDER
    assert impuestos.VIEW_ORDER == ("corte", "fondos", "venta", "pais", "recuperar")


@pytest.mark.parametrize("vista", impuestos.VIEW_ORDER)
def test_render_impuestos_inyecta_solo_la_vista_pedida(monkeypatch, vista):
    caja = _captura(monkeypatch)
    componentes.render_impuestos(_DATOS, "Claro", vista=vista)

    assert "{{VISTA_ACTIVA}}" not in caja["html"], "quedó el placeholder sin sustituir"
    assert f'var VISTA_ACTIVA = "{vista}";' in caja["html"]
    for otra in impuestos.VIEW_ORDER:
        if otra != vista:
            assert f'var VISTA_ACTIVA = "{otra}";' not in caja["html"]


@pytest.mark.parametrize("vista", impuestos.VIEW_ORDER)
def test_cada_vista_trae_su_propio_alto(monkeypatch, vista):
    caja = _captura(monkeypatch)
    componentes.render_impuestos(_DATOS, "Claro", vista=vista)
    assert caja["height"] == componentes.ALTO_IMPUESTOS[vista]
    assert set(componentes.ALTO_IMPUESTOS) == set(impuestos.VIEW_ORDER)


def test_render_vista_cae_a_la_primera_vista_ante_una_clave_desconocida(monkeypatch):
    caja = _captura(monkeypatch)

    class _Ruta:
        tema = "Claro"

    monkeypatch.setattr(impuestos, "obtener_resultados", lambda: None, raising=False)
    # con `obtener_resultados` devolviendo None se corta antes del render (estado vacío);
    # el cinturón se prueba llamando a componentes.render_impuestos por la ruta real:
    componentes.render_impuestos(_DATOS, "Claro", vista="no-existe")
    # alto de respaldo = el mayor, nunca un KeyError
    assert caja["height"] == max(componentes.ALTO_IMPUESTOS.values())


def test_impuestos_render_vista_normaliza_la_clave(monkeypatch):
    """`impuestos.render_vista` debe pasar SIEMPRE una clave de `VIEWS` a
    `render_impuestos`, aunque el llamador pase basura."""
    import ui.adapters as adapters
    from ui import estado

    caja = _captura(monkeypatch)
    monkeypatch.setattr("ui.vistas.obtener_resultados", lambda: {"MSTY": object()})
    monkeypatch.setattr(estado, "perfil_fiscal", lambda: None)
    monkeypatch.setattr(adapters, "impuestos_data",
                        lambda *a, **k: {"fondos": [{"ticker": "MSTY"}]})

    class _Ruta:
        tema = "Claro"

    impuestos.render_vista("basura-total", _Ruta())
    assert 'var VISTA_ACTIVA = "corte";' in caja["html"]


# ── Capa 2 — CONSECUENCIA: se ejecuta el <script> y se mira el DOM ─────────────────────

@_node
@pytest.mark.parametrize("vista", _ORDER)
def test_cada_vista_deja_solo_su_seccion_en_el_dom(vista):
    _assert_vista(vista, _ejecutar(vista))


@_node
def test_gate_el_mutante_de_las_6_ramas_en_if_true_pone_todo_en_rojo():
    """Gate del repo (`if no muerde, no vale`): poner las 6 ramas de vista del <script>
    en `if (true)` hace que CADA vista construya TODO. Los tests de consecuencia tienen
    que caer en las 5 vistas — si sobreviven, auditan el flag, no el resultado."""
    original = _primer_script()
    # las 6 ramas viven a 2 espacios de sangría (las del bloque de título están a 4)
    mut = re.sub(r'^  if \(VISTA_ACTIVA === "\w+"\)', "  if (true)", original, flags=re.M)
    mut = re.sub(r'^  if \(VISTAS_ESCALERA\[VISTA_ACTIVA\]\)', "  if (true)", mut, flags=re.M)
    neutralizadas = len(re.findall(r"^  if \(true\)", mut, flags=re.M))
    assert neutralizadas == 6, (
        f"esperaba neutralizar 6 ramas, neutralicé {neutralizadas} — ¿cambió la sangría "
        "o el nombre de las ramas de vista?")

    cayeron = 0
    for vista in _ORDER:
        rep = _ejecutar(vista, script=mut)
        try:
            _assert_vista(vista, rep)
        except AssertionError:
            cayeron += 1
    assert cayeron == len(_ORDER), (
        f"el mutante if(true)x6 solo tumbó {cayeron}/{len(_ORDER)} vistas — "
        "los tests de consecuencia no discriminan lo suficiente")


# ── PR 2 «El corte»: veredicto derivado + barras a escala compartida ──────────────────

import copy  # noqa: E402


def _corte(d=None):
    return _ejecutar("corte", d=d or _D)["impEscalera"]["html"]


def _segs(html, bar):
    """{data-seg-suffix: width%} de la barra pedida, leídos del HTML renderizado."""
    out = {}
    for suf, w in re.findall(r'data-seg="' + str(bar) + r'-(\w+)"[^>]*?width:\s*([\d.]+)%', html):
        out[suf] = float(w)
    return out


_TOL = 0.05  # puntos porcentuales


def _cerca(a, b, msg=""):
    assert abs(a - b) <= _TOL, f"{msg}: {a:.4f}% vs {b:.4f}% esperado"


@_node
def test_barra_1_normalizada_a_bruto():
    """Barra 1: base `bruto`, llena el 100%. Cada segmento contra SU propio monto/bruto
    (no solo la suma — un intercambio de anchos sobrevive a «suman 100»)."""
    P = _D["peldanos"]
    bruto, grav = P["bruto"]["monto"], P["gravable"]["monto"]
    s = _segs(_corte(), 1)
    _cerca(s["anchor"], (bruto - grav) / bruto * 100, "barra1 anchor = (bruto−gravable)/bruto")
    _cerca(s["drip"], grav / bruto * 100, "barra1 drip = gravable/bruto")
    _cerca(s["anchor"] + s["drip"], 100.0, "barra1 llena el 100%")


@_node
def test_barra_2_NO_normalizada_comparte_escala_con_la_1():
    """El test espejo. Barra 2: MISMA base `bruto`, y los 3 segmentos suman
    `retenido/bruto` — es decir NO 100%. Si alguien la normaliza a ancho completo, las
    dos barras dejan de compartir escala y el exceso deja de verse: mutante que la suite
    entera dejaría pasar sin este assert."""
    P = _D["peldanos"]
    bruto = P["bruto"]["monto"]
    ret = P["retenido"]["monto"]
    c = P["retenido"]["correcta"]["monto"]
    rr = P["retenido"]["recuperable_roc"]["monto"]
    gg = P["retenido"]["gap_w8ben"]["monto"]
    s = _segs(_corte(), 2)
    _cerca(s["correcta"], c / bruto * 100, "barra2 correcta/bruto")
    _cerca(s["roc"], rr / bruto * 100, "barra2 roc/bruto")
    _cerca(s["gap"], gg / bruto * 100, "barra2 gap/bruto")
    suma = s["correcta"] + s["roc"] + s["gap"]
    _cerca(suma, ret / bruto * 100, "barra2: los 3 segmentos suman retenido/bruto")
    assert suma < 99.0, (
        f"barra2 sumó {suma:.2f}% — está normalizada a 100, ya no comparte escala con la barra 1")
    _cerca(s["rest"], 100.0 - suma, "barra2 rest = 100 − lo retenido")


@_node
def test_barra_3_zoom_sobre_retenido_NO_bruto():
    """§9.1 — el fallo que el auditor busca primero. Barra 3: base = `retenido`, los 3
    segmentos suman ≈100%. Con el divisor en `bruto` sumarían ≈`retenido/bruto` (aquí
    ~1.4%) y cada uno mentiría su porción."""
    P = _D["peldanos"]
    ret = P["retenido"]["monto"]
    c = P["retenido"]["correcta"]["monto"]
    rr = P["retenido"]["recuperable_roc"]["monto"]
    gg = P["retenido"]["gap_w8ben"]["monto"]
    s = _segs(_corte(), 3)
    _cerca(s["correcta"], c / ret * 100, "barra3 correcta/RETENIDO")
    _cerca(s["roc"], rr / ret * 100, "barra3 roc/RETENIDO")
    _cerca(s["gap"], gg / ret * 100, "barra3 gap/RETENIDO")
    _cerca(s["correcta"] + s["roc"] + s["gap"], 100.0, "barra3 zoom llena el 100% de lo retenido")


@_node
def test_mutante_barra_3_divide_entre_bruto_cae():
    """Prueba viva de que el test de arriba muerde: se reescribe el divisor de la barra 3
    a `bruto` y se exige que `test_barra_3_*` falle."""
    script = _primer_script()
    mut = script.replace(
        "var zC = clampW(ret > 0 ? mC / ret * 100 : 0);",
        "var zC = clampW(bruto > 0 ? mC / bruto * 100 : 0);").replace(
        "var zR = clampW(ret > 0 ? mRR / ret * 100 : 0);",
        "var zR = clampW(bruto > 0 ? mRR / bruto * 100 : 0);").replace(
        "var zG = clampW(ret > 0 ? mGG / ret * 100 : 0);",
        "var zG = clampW(bruto > 0 ? mGG / bruto * 100 : 0);")
    assert mut != script, "no encontré las líneas del divisor de la barra 3 — ¿se renombraron?"
    s = _segs(_ejecutar("corte", script=mut)["impEscalera"]["html"], 3)
    suma = s["correcta"] + s["roc"] + s["gap"]
    assert abs(suma - 100.0) > 1.0, (
        f"con el divisor en bruto la barra 3 sumó {suma:.2f}% y el test no lo cazaría")


_VER_FIXTURES = {
    "sin_pais": ("warn", "Falta tu residencia fiscal para saber si te retuvieron de más."),
    "parcial": ("warn", "no podemos decir cuánto sobra"),
    "gap": ("coral", "Te retuvieron $80.00 — te tocaban $210.23."),
    "solo_roc": ("warn", "Todo el exceso vuelve solo."),
    "justo": ("cash", "justo lo que te tocaba"),
}


def _D_para(rama):
    d = copy.deepcopy(_D)
    R = d["peldanos"]["retenido"]
    if rama == "sin_pais":
        d["declarado"] = False
        d["peldanos"]["corresponde"] = None
        R["estado"] = "sin_pais"
        R["correcta"] = R["recuperable_roc"] = R["gap_w8ben"] = None
    elif rama == "parcial":
        R["estado"] = "parcial"
        R["fondos_sin_desglose"] = ["CONY", "NFLY"]
        R["correcta"] = R["recuperable_roc"] = R["gap_w8ben"] = None
    elif rama == "gap":
        pass  # _D ya tiene gap_w8ben 18.71 y recuperable_roc 41.29
    elif rama == "solo_roc":
        R["gap_w8ben"] = {"monto": 0.0, "pct": 0.0}
    elif rama == "justo":
        R["gap_w8ben"] = {"monto": 0.0, "pct": 0.0}
        R["recuperable_roc"] = {"monto": 0.0, "pct": 0.0}
    return d


@_node
@pytest.mark.parametrize("rama", list(_VER_FIXTURES))
def test_veredicto_sale_del_dato_una_fixture_por_rama(rama):
    """Daniel §3: un test estructural («hay un switch») no ve que el ORDEN de las ramas
    es la protección — reordenar mete un TypeError sobre null (buckets son null salvo
    estado 'ok') que mata el script entero. Se pinea el orden como EFECTO: una fixture
    por rama, se asserta borde + titular resultantes."""
    borde_esp, frag = _VER_FIXTURES[rama]
    html = _corte(_D_para(rama))
    m = re.search(r'class="imp-verdict" data-borde="(\w+)"', html)
    assert m, f"{rama}: no se renderizó el veredicto"
    assert m.group(1) == borde_esp, f"{rama}: borde {m.group(1)}, esperaba {borde_esp}"
    big = re.search(r'imp-verdict-big">(.*?)</p>', html, re.S)
    assert big and frag in big.group(1), f"{rama}: titular {big and big.group(1)!r} sin {frag!r}"
    style = re.search(r'imp-verdict"[^>]*style="border-left-color:var\((--\w+)\)', html)
    assert style and style.group(1) == "--" + borde_esp, "el borde CSS no sigue al data-borde"


@_node
def test_mutante_reordenar_el_veredicto_mata_el_script():
    """`veredicto()` USA lecturas null-safe (`(R.gap_w8ben && R.gap_w8ben.monto) || 0`).
    Con ellas un reorden NO da un TypeError ruidoso — da un veredicto silenciosamente
    falso (una cartera parcial caería a «justo lo que te tocaba»); eso lo cazan las 5
    fixtures de `test_veredicto_sale_del_dato_una_fixture_por_rama`.

    Este test cubre el OTRO reorden: el ingenuo, que dereferencia `R.gap_w8ben.monto` sin
    guard —como haría quien mueve una fila de la tabla sin mirar `adapters.py:808-814`—.
    Ahí sí es TypeError → script muerto → `returncode != 0` (modo de fallo del #84)."""
    script = _primer_script()
    # reorden ingenuo: la rama del gap pasa ANTES de `!declarado`, sin null-guard.
    mut = script.replace(
        "    if (!D.declarado) {",
        "    if (R.gap_w8ben.monto > 0.01) { return { borde: 'coral', "
        "kick: kick, big: 'x', sub: '' }; }\n    if (!D.declarado) {")
    assert mut != script
    d = _D_para("sin_pais")
    js = mut.replace("{{DATA_JSON}}", json.dumps(d)).replace("{{VISTA_ACTIVA}}", "corte")
    prog = _HARNESS.replace("__SCRIPT__", js)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as t:
        t.write(prog)
        ruta = t.name
    try:
        r = subprocess.run(["node", ruta], capture_output=True, text=True)
    finally:
        os.unlink(ruta)
    assert r.returncode != 0 and "TypeError" in r.stderr, (
        "reordenar el veredicto debería matar el script con un TypeError sobre null; "
        f"returncode={r.returncode}")


@_node
@pytest.mark.parametrize("rama,marca", [
    ("gap", 'data-bar="3"'),                       # ok → barra 3 presente
    ("parcial", "no es una cifra fiable"),          # parcial → aviso de desglose
    ("sin_pais", "Declara tu país en el Paso 2"),   # sin_pais → CTA
])
def test_los_tres_estados_de_retenido_dibujan_lo_suyo(rama, marca):
    html = _corte(_D_para(rama))
    assert marca in html, f"estado {rama}: falta {marca!r}"
    if rama != "gap":
        assert 'data-bar="3"' not in html, f"estado {rama} NO debe tener barra 3 (zoom)"
    if rama == "sin_pais":
        assert 'data-rule' not in html, "sin_pais: sin regla vertical (no hay país)"


def test_todo_token_usado_esta_en_los_cuatro_bloques():
    """§5.2: el iframe no ve `ui/tokens.py`. Cualquier `var(--x)` que use el componente
    tiene que estar declarado en los CUATRO bloques (`:root`, `@media dark`,
    `[data-theme=light]`, `[data-theme=dark]`) o cae al color del navegador. Este guard
    nace del bug de `--anchor`/`--drip` (PR 2): la barra 1 salió invisible en vivo."""
    with open(_HTML, encoding="utf-8") as f:
        src = f.read()
    style = src[src.index("<style>"):src.index("</style>")]
    usados = set(re.findall(r"var\((--[\w-]+)\)", src))
    # los 4 bloques de tokens: cada uno arranca en `{` tras un selector raíz
    bloques = re.findall(r"(?::root(?:\[data-theme=\"\w+\"\])?|@media[^{]+\{\s*:root)\s*\{([^}]*)\}", style)
    assert len(bloques) >= 4, f"esperaba ≥4 bloques de tokens, encontré {len(bloques)}"
    ignora = {"--font-mono", "--font-sans"}   # se declaran una vez, no cambian con el tema
    for tok in sorted(usados - ignora):
        faltan = [i for i, b in enumerate(bloques) if (tok + ":") not in b.replace(" ", "")]
        assert not faltan, f"{tok} usado pero ausente en los bloques de tokens #{faltan}"


def test_ambar_no_reaparece_como_token_css():
    """`var(--ambar)` no existe en el repo (el ámbar es `--warn`). Guard de una línea."""
    hits = []
    for base, _, files in os.walk(os.path.join(os.path.dirname(__file__), "ui")):
        for f in files:
            if f.endswith((".html", ".py", ".css")):
                with open(os.path.join(base, f), encoding="utf-8") as fh:
                    if "var(--ambar)" in fh.read():
                        hits.append(os.path.join(base, f))
    assert not hits, f"var(--ambar) — token inexistente — reapareció en: {hits}"


# ── PR 3 «La letra chica»: la frase que se mueve a un ⓘ no puede evaporarse ────────────
#
# El guard que importa (Daniel): comparar el TEXTO RENDERIZADO de cada vista contra `main`
# —incluido el de los `.modal-*`—. Toda frase que estaba en la vista y ya no está es una
# regresión, salvo el puñado que aprobamos reescribir en la §4.4. No compara fuente (los
# literales de JS partidos en varias líneas dan falsos positivos).

# Fixture que dispara TODO el texto condicional de venta y pais (captura, panel fiscal,
# los dos CTA de gFaltan, aviso de crédito neto, aviso de ROC).
_D_FULL = json.loads(json.dumps(_D))
_D_FULL["peldanos"]["gravable"]["sin_roc"] = ["SVOL"]
_D_FULL["peldanos"]["gravable"]["cubiertos"] = 2
_D_FULL["ganancias_capital"].update({
    "tickers_indeterminados": ["ZZZ", "WWW"],
    "tickers_base_captura": ["SMH"],
    "tickers_captura_no_usada": ["WWW"],
    "fiscal_roc": {
        "n_fondos": 1, "tickers": ["MSTY"], "base_mercado": 11455.72, "base": 10800.0,
        "no_realizado": 900.0, "no_realizado_mercado": 1212.97,
        "realizado": 250.0, "realizado_mercado": 300.0,
        "tickers_19a_sin_ajuste": ["PLTY"], "roc_exceso": 42.0,
    },
})
_D_FULL["impuesto_local"]["credito_eeuu"] = {"monto": 60.75, "definitivo": 19.46,
                                             "vuelve_por_roc": 41.29}


def _script_de(html):
    return _SCRIPT_RE.findall(html)[0]


@pytest.fixture(scope="module")
def main_script():
    r = subprocess.run(
        ["git", "show", "origin/main:ui/componentes/impuestos.html"],
        cwd=os.path.dirname(__file__), capture_output=True, text=True)
    if r.returncode != 0 or "<script" not in r.stdout:
        r = subprocess.run(
            ["git", "show", "main:ui/componentes/impuestos.html"],
            cwd=os.path.dirname(__file__), capture_output=True, text=True)
    assert r.returncode == 0 and "<script" in r.stdout, "no pude leer impuestos.html de main"
    return _script_de(r.stdout)


# Apertura o cierre de un bloque → salto de línea (cada `<p>`, `<div>`, celda… es una
# unidad de texto distinta; sin esto un rótulo y la nota de al lado se pegan).
_BLOCK_RE = re.compile(r"</?(?:p|div|li|h\d|section|td|th|tr)(?:\s[^>]*)?>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
# Un número: $x, x%, o dígitos sueltos — NUNCA dígitos pegados a letras (para no partir
# «W-8BEN» ni «1042-S»).
_NUM_RE = re.compile(r"(?<![A-Za-z0-9-])(?:−?\$[\d.,]+|\d[\d.,]*\s?%?)(?![A-Za-z0-9])")
_WS_RE = re.compile(r"[^\S\n]+")


def _norm(html):
    """Texto renderizado, normalizado: cierres de bloque → salto, tags fuera, entidades
    resueltas, números → ·, espacios colapsados."""
    txt = _BLOCK_RE.sub("\n", html)
    txt = _TAG_RE.sub(" ", txt)
    txt = (txt.replace("&minus;", "−").replace("&rarr;", "→").replace("&amp;", "&")
              .replace("−", "-").replace("×", "x").replace("«", '"').replace("»", '"'))
    txt = _NUM_RE.sub("·", txt)
    return _WS_RE.sub(" ", txt).strip()


def _frases(html):
    """Las frases de un texto (para el lado `antes`): se parte en `.`/`:`/`—`/salto."""
    out = set()
    for trozo in re.split(r"(?<=[.:])\s+|\s+-\s+|\n+", _norm(html)):
        t = trozo.strip(" ·.-:;,\"")
        if len(t) >= 25:
            out.add(t)
    return out


def _texto_vista(view, script, d):
    rep = _ejecutar(view, script=script, d=d)
    return " ".join(v["html"] for v in rep.values() if v.get("html"))


# Frases de `main` que pueden NO sobrevivir verbatim (whitelist por vista). Hoy VACÍA en
# las 5: al mover la letra chica a los modales no se reescribe ni una — las notas de
# tarjeta que la §4.4 acortó conservan su versión larga dentro del modal correspondiente.
# Si algo entra aquí, tiene que venir con su justificación y un test que verifique que su
# «parte de más» sí está en un `.modal-*`.
_PERDIDAS_APROBADAS = {
    "corte": set(),
    "fondos": set(), "venta": set(), "pais": set(),
    # PR 4 «ventana de reembolso». ÚNICA pérdida aprobada de todo el rediseño, y no es una
    # pérdida de información: los meses dejan de ir en prosa y pasan a la franja de
    # `.imp-vent`, que además resalta SOLO la ventana del bróker del cliente en vez de
    # recitarle las dos. Aprobada por Daniel al pedir el PR 4.
    #
    # Una whitelist que solo tapa el hueco escondería una regresión, así que
    # `test_la_franja_de_ventanas_conserva_los_meses_que_salieron_de_la_prosa` (abajo)
    # comprueba que la franja marca de verdad ene-mar para IB y jun-sep para Schwab. Si esa
    # información se pierde, ese test cae aunque esta línea siga aquí.
    "recuperar": {
        "si tu bróker es Interactive Brokers, entre enero y marzo; "
        "si es Schwab, entre junio y septiembre",
    },
}


@_node
@pytest.mark.parametrize("view", _ORDER)
def test_ninguna_frase_desaparece_al_moverla_a_un_modal(view, main_script):
    antes = _frases(_texto_vista(view, main_script, _D_FULL))
    ahora = _norm(_texto_vista(view, _primer_script(), _D_FULL))
    aprob = _PERDIDAS_APROBADAS[view]
    perdidas = {f for f in antes
                if f not in ahora and not any(a in f or f in a for a in aprob)}
    assert not perdidas, (
        f"{view}: {len(perdidas)} frase(s) desaparecieron al mover la letra chica — "
        "deberían estar verbatim en algún .modal-*:\n  - "
        + "\n  - ".join(sorted(perdidas)))


_MODALES_ESPERADOS = {
    "corte": ["modal-imp-bruto", "modal-imp-roc", "modal-imp-retenido",
              "modal-imp-correcta", "modal-imp-vuelvesolo", "modal-imp-w8ben"],
    "fondos": ["modal-imp-tabla"],
    "venta": ["modal-imp-vender"],
    "pais": ["modal-imp-pais"],
    "recuperar": [],
}


@_node
@pytest.mark.parametrize("view", _ORDER)
def test_cada_modal_tiene_su_disparador_y_su_cierre(view):
    """Cableado (importa menos — un modal que no abre se ve enseguida): cada `#modal-*`
    que la vista construye trae su `#modal-*-close` Y un `[data-tip=...]` que lo dispara,
    y `wireModal` se llama para él."""
    rep = _ejecutar(view, d=_D_FULL)
    blob = " ".join(v["html"] for v in rep.values() if v.get("html"))
    ids = set(re.findall(r'id="(modal-imp-[\w-]+?)"', blob))
    ids = {i for i in ids if not i.endswith("-close") and not i.endswith("-title")}
    assert ids == set(_MODALES_ESPERADOS[view]), (
        f"{view}: modales {sorted(ids)}, esperaba {_MODALES_ESPERADOS[view]}")
    src = _primer_script()
    for mid in ids:
        tip = mid.replace("modal-", "", 1)
        assert f'id="{mid}-close"' in blob, f"{view}: {mid} sin botón de cerrar"
        assert f'data-tip="{tip}"' in blob, f"{view}: {mid} sin disparador [data-tip={tip}]"
        # cableado: o inline `wireModal("mid"` o en la lista `["mid", "tip"]`
        assert (f'wireModal("{mid}"' in src) or (f'["{mid}", "{tip}"]' in src), (
            f"{mid} no se cablea con wireModal")


@_node
def test_la_tarjeta_vuelve_solo_manda_el_matiz_puede_al_modal():
    """Daniel: la nota corta de §4.4 («En el cierre anual de tu bróker: …») afirma sin
    reservas lo que la vieja matizaba con «puede». Ese matiz tiene que estar en el modal."""
    html = _corte(_D_FULL)
    card = re.search(r'imp-bucket ambar.*?</div>', html, re.S).group(0)
    assert "puede volver solo" not in card.lower(), "la tarjeta ya no debe llevar el «puede»"
    modal = re.search(r'id="modal-imp-vuelvesolo".*?</div></div>', html, re.S).group(0)
    assert "Puede volver solo en el cierre anual del bróker" in modal, (
        "el modal de «Vuelve solo» perdió el matiz condicional")


# ---------------------------------------------------------------------------------------
# PR 4 — la ventana de reclasificación por bróker.
#
# El bróker NO se deduce de las cifras: llega por parámetro desde `ui/impuestos.py`
# (`session_state['_wizard_broker']`, lo que leyó `logic.detect_broker`) igual que el país.
# Estos tests cubren las tres ramas y, sobre todo, sostienen la única entrada de
# `_PERDIDAS_APROBADAS`: la información que salió de la prosa tiene que seguir en la franja.
# ---------------------------------------------------------------------------------------

_VENTANAS = [
    {"broker": "ibkr", "label": "Interactive Brokers", "desde": 1, "hasta": 3},
    {"broker": "schwab", "label": "Schwab", "desde": 6, "hasta": 9},
]
_MESES = ["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]


def _con_broker(broker):
    d = json.loads(json.dumps(_D_FULL))
    d["ruta_a"]["broker"] = broker
    d["ruta_a"]["ventanas"] = json.loads(json.dumps(_VENTANAS))
    return d


def _filas_franja(html):
    """[(label, apagada, [índices 1-12 marcados]), ...] leído del HTML de la franja."""
    filas = []
    for bloque in re.findall(r'<div class="imp-vent-fila([^"]*)">(.*?)</div></div>', html, re.S):
        clases, cuerpo = bloque
        lab = re.search(r'class="imp-vent-lab">(.*?)</p>', cuerpo, re.S)
        marcados = [i + 1 for i, m in enumerate(
            re.findall(r'<span class="imp-vent-mes([^"]*)">', cuerpo))
            if "dentro" in m]
        filas.append((re.sub(r"<[^>]+>", "", lab.group(1)).strip() if lab else "",
                      "apagada" in clases, marcados))
    return filas


@_node
def test_la_franja_de_ventanas_conserva_los_meses_que_salieron_de_la_prosa():
    """Sostiene la entrada de `_PERDIDAS_APROBADAS['recuperar']`. La frase «IB entre enero
    y marzo; Schwab entre junio y septiembre» se retiró de la prosa: si la franja no marca
    esos MISMOS meses, la información se perdió de verdad y la whitelist estaría tapando
    una regresión."""
    rep = _ejecutar("recuperar", d=_con_broker(None))
    filas = _filas_franja(rep["impRutas"]["html"])
    assert len(filas) == 2, f"esperaba las dos ventanas, encontré {len(filas)}"
    por_label = {f[0].split()[0]: f[2] for f in filas}
    assert por_label["Interactive"] == [1, 2, 3], "IB debe marcar ene-mar"
    assert por_label["Schwab"] == [6, 7, 8, 9], "Schwab debe marcar jun-sep"


@_node
@pytest.mark.parametrize("broker,label_tuyo,apagado", [
    ("schwab", "Schwab", "Interactive Brokers"),
    ("ibkr", "Interactive Brokers", "Schwab"),
])
def test_con_broker_conocido_solo_se_resalta_el_suyo(broker, label_tuyo, apagado):
    rep = _ejecutar("recuperar", d=_con_broker(broker))
    html = rep["impRutas"]["html"]
    filas = _filas_franja(html)
    activas = [f[0] for f in filas if not f[1]]
    apagadas = [f[0] for f in filas if f[1]]
    assert any(label_tuyo in a for a in activas), f"la fila de {label_tuyo} debe ir activa"
    assert any(apagado in a for a in apagadas), f"la fila de {apagado} debe ir apagada"
    assert "tu bróker" in html, "falta la marca «tu bróker» en la fila del cliente"
    assert label_tuyo in html and "cae en la ventana marcada arriba" in html


@_node
def test_sin_broker_se_muestran_las_dos_sin_apagar_ninguna():
    """`None` (incluye el 'generic' que el adapter normaliza): mostrar una sola ventana
    sería inventar cuál es la del cliente."""
    rep = _ejecutar("recuperar", d=_con_broker(None))
    html = rep["impRutas"]["html"]
    assert not any(f[1] for f in _filas_franja(html)), "sin bróker no se apaga ninguna"
    assert "No pudimos identificar tu bróker" in html
    assert "tu bróker</span>" not in html, "sin bróker no se marca ninguna como tuya"


@_node
def test_la_frase_del_ano_va_identica_en_las_tres_ramas():
    """La cola que carga el AÑO es la que el guard de frases compara verbatim contra
    `main`. Tiene que salir igual con bróker y sin él, y SIN negrita: un `</b>` pegado a la
    coma cambia el texto normalizado y la frase deja de casar con `main` (pasó al escribir
    el PR 4; lo cazó `test_ninguna_frase_desaparece_al_moverla_a_un_modal`)."""
    for b in (None, "schwab", "ibkr"):
        html = _ejecutar("recuperar", d=_con_broker(b))["impRutas"]["html"]
        assert "Es el cierre fiscal del año que analizaste, no de este." in html, (
            f"la cola del año cambió con broker={b!r}")


@_node
def test_la_franja_no_lleva_ano_ni_marca_de_hoy():
    """Regla 2: la ventana es el cierre fiscal del año ANALIZADO y cae en el año calendario
    siguiente. Un eje fechado —o un «hoy» sobre él— pondría dos momentos en la misma línea.
    Este test es el que impide que alguien «mejore» la franja añadiéndoselos."""
    html = _ejecutar("recuperar", d=_con_broker("schwab"))["impRutas"]["html"]
    franja = html[html.find('class="imp-vent"'):html.find("</div>", html.find("imp-vent-fila"))]
    assert not re.search(r"\b20\d{2}\b", franja), "la franja no debe llevar año"
    assert "hoy" not in franja.lower(), "la franja no debe marcar «hoy»"


# --- Capa del ADAPTER (PR 4) -----------------------------------------------------------
# Los tests de arriba miden el RENDER contra su propio fixture. Eso deja dos huecos que
# los mutantes destaparon: `'generic'` colándose como bróker, y las ventanas cambiando en
# `ui/adapters.py` sin que nadie se entere porque el fixture las duplica. Estos leen lo que
# el adapter publica DE VERDAD.

def _res_minimo():
    import pandas as pd
    hist = pd.DataFrame({
        "Date": pd.to_datetime(["2025-06-15", "2025-06-15"]),
        "Action": ["Cash Dividend", "NRA Tax Adj"],
        "Amount": [100.0, -30.0],
    })
    return {"MSTY": {
        "pocket_investment": 1000.0, "market_value": 900.0,
        "dividends_collected_drip": 0.0, "dividends_collected_cash": 100.0,
        "total_dividends": 70.0,
        "dividends_gross_total": 100.0, "dividends_net_total": 70.0,
        "dividends_gross_by_year": {2025: 100.0}, "withheld_by_year": {2025: 30.0},
        "withheld_tax_total": 30.0,
        "roc_percent": 50.0, "roc_source": "19a",
        "history": hist,
    }}


def _ruta_a(broker):
    import logic
    from ui.adapters import impuestos_data
    return impuestos_data(_res_minimo(), logic.build_fiscal_profile("Colombia"), [],
                          broker=broker)["ruta_a"]


@pytest.mark.parametrize("entrada,esperado", [
    ("schwab", "schwab"),
    ("ibkr", "ibkr"),
    # 'generic' es «no lo reconocí», no un bróker. Publicarlo haría que la vista dijera
    # «Tu bróker es generic» y resaltara una ventana inventada — el mismo error que
    # deducir el país de la tasa retenida.
    ("generic", None),
    (None, None),
    ("", None),
    ("SCHWAB", None),   # sin normalizar mayúsculas: lo que no viene tal cual, no pasa
])
def test_el_adapter_solo_publica_broker_reconocido(entrada, esperado):
    assert _ruta_a(entrada)["broker"] == esperado


def test_el_adapter_publica_las_ventanas_reales_de_cada_broker():
    """Ground truth, no un espejo del código: IB reclasifica ene-mar y Schwab jun-sep.
    Si alguien mueve esos meses en `ui/adapters.py`, este test cae — el de render no,
    porque tiene su propio fixture."""
    vent = {v["broker"]: v for v in _ruta_a("schwab")["ventanas"]}
    assert set(vent) == {"ibkr", "schwab"}
    assert (vent["ibkr"]["desde"], vent["ibkr"]["hasta"]) == (1, 3)
    assert (vent["schwab"]["desde"], vent["schwab"]["hasta"]) == (6, 9)
    assert vent["ibkr"]["label"] == "Interactive Brokers"
    assert vent["schwab"]["label"] == "Schwab"


def test_el_broker_no_mueve_ni_una_cifra():
    """`broker` solo gobierna qué ventana se resalta. Si alguna cifra cambia con él, algo
    lo está usando para calcular — y eso rompe la Regla 3."""
    import logic
    from ui.adapters import impuestos_data
    base = None
    for b in (None, "schwab", "ibkr", "generic"):
        d = impuestos_data(_res_minimo(), logic.build_fiscal_profile("Colombia"), [],
                           broker=b)
        d["ruta_a"] = {k: v for k, v in d["ruta_a"].items()
                       if k not in ("broker", "ventanas")}
        actual = json.dumps(d, sort_keys=True, default=str)
        if base is None:
            base = actual
        assert actual == base, f"broker={b!r} movió una cifra del objeto fiscal"


# ---------------------------------------------------------------------------------------
# Gap de W-8BEN residual — el titular no puede decir «todo» si una tarjeta muestra un resto.
#
# Visto en producción con la cartera real de Daniel: retenido $123.88 = correcta $42.65 +
# vuelve solo $81.22 + gap $0.01. El umbral era `gap > 0.01` y `0.01` no es `> 0.01`, así
# que el veredicto decía «Todo el exceso vuelve solo» mientras la tercera tarjeta de la
# MISMA pantalla mostraba «W-8BEN · $0.01». Dos sitios decidiendo lo mismo con criterios
# distintos: la regla 3b del repo (dos vistas del mismo número se comparan entre sí).
# ---------------------------------------------------------------------------------------

def _D_gap(gap, roc):
    d = copy.deepcopy(_D)
    R = d["peldanos"]["retenido"]
    R["estado"] = "ok"
    R["gap_w8ben"] = {"monto": gap, "pct": 0.0}
    R["recuperable_roc"] = {"monto": roc, "pct": 0.7}
    R["correcta"] = {"monto": round(R["monto"] - gap - roc, 2), "pct": 0.3}
    return d


def _titular_y_sub(html):
    big = re.search(r'imp-verdict-big">(.*?)</p>', html, re.S)
    sub = re.search(r'imp-verdict-sub">(.*?)</p>', html, re.S)
    return (big.group(1) if big else ""), (sub.group(1) if sub else "")


@_node
@pytest.mark.parametrize("gap,roc,frag_esperado,nombra_resto", [
    # el caso REAL de producción: un centavo exacto, justo en el borde del umbral
    (0.01, 41.29, "Prácticamente todo el exceso vuelve solo.", True),
    (0.01, 0.0, "prácticamente lo que te tocaba", True),
    (0.004, 41.29, "Prácticamente todo el exceso vuelve solo.", True),
    # sin resto: el lenguaje absoluto sí es correcto
    (0.0, 41.29, "Todo el exceso vuelve solo.", False),
    (0.0, 0.0, "justo lo que te tocaba", False),
])
def test_el_titular_no_dice_todo_si_queda_un_resto_de_w8ben(gap, roc, frag_esperado,
                                                            nombra_resto):
    big, sub = _titular_y_sub(_corte(_D_gap(gap, roc)))
    assert frag_esperado in big, f"gap={gap} roc={roc}: titular {big!r}"
    if nombra_resto:
        assert "gap de W-8BEN, que no vuelven solos" in sub, (
            f"gap={gap}: el titular se corrigió pero el resto no se nombra — sub={sub!r}")
        assert money_es(gap) in sub, f"gap={gap}: el sub no dice el monto"
    else:
        assert "gap de W-8BEN" not in sub, f"gap={gap}: nombra un resto que no existe"


def money_es(x):
    return ("−$" if x < 0 else "$") + f"{abs(x):.2f}"


@_node
@pytest.mark.parametrize("gap", [0.0, 0.004, 0.01, 5.0, 18.71])
def test_titular_y_tarjeta_de_w8ben_no_se_contradicen(gap):
    """El gate de verdad (regla 3b): comparar las DOS vistas del mismo número entre sí.
    Si la tarjeta de la barra 3 muestra un monto de W-8BEN distinto de cero, el titular no
    puede afirmar que todo vuelve solo ni que te retuvieron justo lo que tocaba. Este test
    no conoce el umbral — solo exige que las dos superficies cuenten lo mismo."""
    html = _corte(_D_gap(gap, 41.29))
    big, _ = _titular_y_sub(html)
    # Se lee la tarjeta REAL (la coral es la de W-8BEN), no un valor que calcule el test:
    # con un fallback, este test compararía el código consigo mismo y pasaría siempre.
    # Si la tarjeta no está, esto FALLA — que es lo correcto: sin las dos superficies no
    # hay nada que reconciliar.
    tarjeta = re.search(r'imp-bucket coral".*?imp-bucket-money">([^<]+)<', html, re.S)
    assert tarjeta, "no encontré la tarjeta coral de W-8BEN en la barra 3"
    monto_tarjeta = tarjeta.group(1)
    muestra_resto = monto_tarjeta != "$0.00"
    absoluto = ("Todo el exceso vuelve solo" in big) or ("justo lo que te tocaba" in big)
    assert not (muestra_resto and absoluto), (
        f"gap={gap}: la tarjeta muestra {monto_tarjeta} y el titular dice {big!r} — "
        "las dos vistas del mismo número se contradicen")
