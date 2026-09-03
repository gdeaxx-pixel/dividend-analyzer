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
var IDS = ["impLede","impTitle","impEscalera","impTabla","impRutas","impFoot","impBlock"];
var store = {};
IDS.forEach(function (id) {
  store[id] = { id: id, innerHTML: "", removed: false, remove: function () { this.removed = true; } };
});
function _muerto(id) { return store[id].removed || (id === "impTabla" && store.impBlock.removed); }
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

    assert tit["alive"] and tit["html"] == _TITULOS[vista], (
        f"{vista}: h2 = {tit['html']!r}, esperaba {_TITULOS[vista]!r}")

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
    """Si `gap`/`roc` se comprueban ANTES de los guards `!declarado`/`parcial`, en esas
    dos ramas `R.gap_w8ben` es null → TypeError → script muerto. El harness lo caza como
    returncode != 0."""
    script = _primer_script()
    # reorden ingenuo: la rama del gap (que dereferencia `R.gap_w8ben.monto` sin guard,
    # como haría quien mueve una fila de la tabla) pasa ANTES de `!declarado`
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
