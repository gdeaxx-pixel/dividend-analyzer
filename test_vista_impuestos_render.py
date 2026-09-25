"""U2 «dona de dos fases» — la vista Impuestos pasa de 5 pantallas a UNA
(`ui/componentes/impuestos_v2.html`), con las fases 1/2 como estado LOCAL del iframe.

Tres capas:

1. DESPACHO — `render_impuestos` inyecta datos/tema y la altura única;
   `impuestos.render_vista` normaliza la clave. Auditan el cableado Python.
2. CONSECUENCIA — se EJECUTA el `<script>` del componente en Node con un `document`
   de juguete y se mira el DOM resultante: la dona dibuja la fase que toca, el
   veredicto sale del dato, las barras comparten escala, la franja marca los meses.
   Gate del repo: cada guard muere con SU mutante (ver `test_gate_*` y los mutantes
   documentados en la spec U2 §6/§7).
3. INVENTARIO — ninguna frase de las 5 vistas de `origin/main` desaparece al mudarse
   a la vista única (`test_ninguna_frase_desaparece_al_moverla_a_un_modal`, extendido
   a las 5 vistas por U2 §6 › 3). Las pérdidas deliberadas viven en
   `_PERDIDAS_APROBADAS` y se reportan a Daniel.

La aritmética la siguen pineando `test_vista_impuestos.py` (por datos, no por
marcado) — U2 §7 › 7: no re-pinear.
"""
import copy
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

_HTML = os.path.join(os.path.dirname(__file__), "ui", "componentes", "impuestos_v2.html")
_SCRIPT_RE = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S)
# `_D` NO es un objeto fiscal coherente — es un dict que toca todas las ramas de RENDER
# (peldaños 1-6, tabla con buckets, Ruta A/B, dona de dos fases con desglose completo).
# La coherencia la pinan `test_vista_impuestos.py` contra el adapter real.
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
        "credito_eeuu": {"monto": 80.0, "definitivo": 38.71, "vuelve_por_roc": 41.29,
                          "definitivo_motivo": None},
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
        {"ticker": "MSTY", "grupo": "mode_a", "bruto": 5000.0, "roc_pct": 61, "gravable": 1950.0,
         "corresponde": 195.0, "retenido": 78.0, "ya_devuelto": 19.0, "indeterminado": False,
         "retencion_correcta": 19.0, "recuperable_roc": 40.0, "gap_w8ben": 19.0},
        {"ticker": "SCHB", "grupo": "mode_b", "bruto": 827.18, "roc_pct": 0, "gravable": 152.31,
         "corresponde": 15.23, "retenido": 2.0, "ya_devuelto": 1.0, "indeterminado": False,
         "retencion_correcta": 1.0, "recuperable_roc": 1.29, "gap_w8ben": 0.0},
    ],
    "slots_pendientes": [],
}
# Nota de coherencia de la fixture: `credito_eeuu.vuelve_por_roc` (41.29) ==
# Σ fondos[].recuperable_roc (40.0 + 1.29) y `monto` (80.0) == vuelve + definitivo
# (38.71), como en los 4 casos reales medidos (spec U2 §4.2). `_D_divergente` (abajo)
# fuerza la divergencia para el guard de la Regla 3b.

# ── Harness NUEVO (v2): store genérico por id + volcados de fase0/fase1/selección ────
_HARNESS_V2 = r"""
var store = {};
function _mk(id) {
  var self = {
    id: id, innerHTML: "", _attrs: {}, removed: false, _classes: [],
    setAttribute: function (k, v) { this._attrs[k] = String(v); },
    getAttribute: function (k) { return (k in this._attrs) ? this._attrs[k] : null; },
    removeAttribute: function (k) { delete this._attrs[k]; },
    hasAttribute: function (k) { return k in this._attrs; },
    addEventListener: function () {},
    focus: function () {},
    closest: function () { return null; },
    remove: function () { this.removed = true; }
  };
  self.classList = {
    add: function (c) { if (self._classes.indexOf(c) < 0) self._classes.push(c); },
    remove: function (c) { var i = self._classes.indexOf(c); if (i >= 0) self._classes.splice(i, 1); },
    toggle: function (c, on) { if (on === undefined) on = !self.classList.contains(c);
      if (on) self.classList.add(c); else self.classList.remove(c); },
    contains: function (c) { return self._classes.indexOf(c) >= 0; }
  };
  return self;
}
globalThis.document = {
  getElementById: function (id) { if (!store[id]) store[id] = _mk(id); return store[id]; },
  addEventListener: function () {},
  querySelectorAll: function () { return []; },
  createElement: function () { return _mk("el"); },
  createElementNS: function (ns, tag) { return _mk("svg-" + tag); }
};
__SCRIPT__
function _dump() {
  var rep = {};
  Object.keys(store).forEach(function (id) {
    var e = store[id];
    rep[id] = { html: e.innerHTML, attrs: e._attrs, classes: e._classes.slice(), removed: e.removed };
  });
  return rep;
}
var out = { fase0: _dump() };
if (globalThis.__impSetFase) {
  globalThis.__impSetFase(1);
  out.fase1 = _dump();
  globalThis.__impSetFase(0);
}
if (globalThis.__impSelect) {
  globalThis.__impSelect("f:MSTY");
  out.sel = _dump();
  globalThis.__impSelect("f:MSTY");
}
console.log(JSON.stringify(out));
"""

# ── Harness VIEJO: solo para ejecutar el script de `origin/main` (guard de frases) ──
_HARNESS_OLD = r"""
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

_VISTAS_ANTIGUAS = ("corte", "fondos", "venta", "pais", "recuperar")


def _primer_script(ruta=None):
    with open(ruta or _HTML, encoding="utf-8") as f:
        return _SCRIPT_RE.findall(f.read())[0]


def _corre_node(prog):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as t:
        t.write(prog)
        ruta = t.name
    try:
        r = subprocess.run(["node", ruta], capture_output=True, text=True)
    finally:
        os.unlink(ruta)
    return r


def _ejecutar(d=None, script=None):
    """Ejecuta el script v2 y devuelve `{fase0, fase1, sel}` con el DOM de juguete."""
    js = _primer_script() if script is None else script
    js = js.replace("{{DATA_JSON}}", json.dumps(_D if d is None else d, ensure_ascii=False))
    prog = _HARNESS_V2.replace("__SCRIPT__", js)
    r = _corre_node(prog)
    assert r.returncode == 0, f"el <script> v2 reventó:\n{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def _ejecutar_old(vista, script, d):
    """Ejecuta el script VIEJO (de `origin/main`) en la vista dada — solo lo usa el
    guard de frases para construir el inventario `antes`."""
    js = script.replace("{{DATA_JSON}}", json.dumps(d, ensure_ascii=False))
    js = js.replace("{{VISTA_ACTIVA}}", vista)
    prog = _HARNESS_OLD.replace("__SCRIPT__", js)
    r = _corre_node(prog)
    assert r.returncode == 0, f"el <script> de main reventó en {vista!r}:\n{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def _texto(out, fase="fase0"):
    return " ".join(v["html"] for v in out[fase].values() if v.get("html"))


def _corte(d=None, script=None):
    return _ejecutar(d=d, script=script)["fase0"]["impEscalera"]["html"]


_node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node ausente: el gate de CONSECUENCIA no corre — y un skip no es un pass")


# ── Capa 1 — DESPACHO ────────────────────────────────────────────────────────────────

def _captura(monkeypatch):
    caja = {}

    def _fake_html(html, height=None, scrolling=None):
        caja["html"] = html
        caja["height"] = height
        caja["scrolling"] = scrolling

    monkeypatch.setattr(componentes.components, "html", _fake_html)
    return caja


def test_viewset_unica_vista():
    """U2 §5 › 3: las 5 vistas pasan a UNA (patrón `heredadas.VIEW_ORDER`)."""
    assert tuple(impuestos.VIEWS) == impuestos.VIEW_ORDER
    assert impuestos.VIEW_ORDER == ("impuestos",)


def test_render_impuestos_inyecta_datos_y_tema(monkeypatch):
    caja = _captura(monkeypatch)
    componentes.render_impuestos(_DATOS, "Oscuro")
    html = caja["html"]
    assert "{{DATA_JSON}}" not in html, "quedó el placeholder sin sustituir"
    assert "{{" not in html, "quedó un placeholder sin sustituir"
    assert 'data-theme", "dark"' in html, "el tema no llegó al iframe (lo pone _con_tema)"
    assert "const DATA = " in caja["html"]


def test_alto_unico_medido(monkeypatch):
    """`ALTO_IMPUESTOS` pasa de dict por vista a UNA altura (U2 §5 › 3)."""
    caja = _captura(monkeypatch)
    componentes.render_impuestos(_DATOS, "Claro")
    assert isinstance(componentes.ALTO_IMPUESTOS, int)
    assert caja["height"] == componentes.ALTO_IMPUESTOS
    assert caja["scrolling"] is False


def test_impuestos_render_vista_normaliza_la_clave(monkeypatch):
    """`impuestos.render_vista` acepta basura (p. ej. un `vd_vista="corte"` guardado
    antes de U2) y渲染 la vista única sin KeyError."""
    import ui.adapters as adapters
    from ui import estado

    caja = _captura(monkeypatch)
    monkeypatch.setattr("ui.vistas.obtener_resultados", lambda: {"MSTY": object()})
    monkeypatch.setattr(estado, "perfil_fiscal", lambda: None)
    monkeypatch.setattr(adapters, "impuestos_data",
                        lambda *a, **k: {"fondos": [{"ticker": "MSTY"}]})

    class _Ruta:
        tema = "Claro"

    impuestos.render_vista("corte-ya-no-existe", _Ruta())
    assert "const DATA = " in caja["html"]
    assert caja["height"] == componentes.ALTO_IMPUESTOS


def test_chrome_no_dibuja_segmento_de_vista_para_impuestos():
    """Con una sola vista, `unica_vista` apaga el segmento del breadcrumb — mismo
    patrón que Portafolios. Si alguien devuelve 5 vistas aquí, la app re-muestra el
    sub-menú que U2 retiró."""
    from ui import chrome
    assert len(chrome._vistas(impuestos.CAT_CLAVE)) == 1
    assert chrome._orden(impuestos.CAT_CLAVE) == ("impuestos",)


# ── Capa 2 — CONSECUENCIA: dona de dos fases ─────────────────────────────────────────

@_node
def test_fase_1_centro_retenido_y_arcos_por_etf():
    out = _ejecutar()
    dona = out["fase0"]["impDona"]["html"]
    assert "Retenido al cobro" in dona
    assert "$80.00" in dona, "el centro de la fase 1 debe ser peldanos.retenido.monto"
    # un arco por fondo con retención (MSTY 78 y SCHB 2), stroke ancho 28
    assert dona.count('stroke-width="28"') == 2
    assert 'data-sel="f:MSTY"' in dona and 'data-sel="f:SCHB"' in dona
    # leyenda con los dos grupos (mode_a/mode_b → Dividendos/Crecimiento)
    ley = out["fase0"]["impLeyenda"]["html"]
    assert "Dividendos" in ley and "Crecimiento" in ley
    assert "$78.00" in ley and "$2.00" in ley
    assert out["fase0"]["impColMonto"]["html"] == "RETENIDO"


@_node
def test_fase_2_centro_definitivo_y_anillo_doble():
    out = _ejecutar()
    dona1 = out["fase1"]["impDona"]["html"]
    assert "Retención restante" in dona1
    assert "$38.71" in dona1, "el centro de la fase 2 debe ser credito_eeuu.definitivo"
    # anillo interior: trama de ROC que vuelve + sólido restante
    assert 'stroke="url(#refundPattern)"' in dona1
    assert 'data-kind="remaining"' in dona1
    # anillo exterior fino (stroke-width 4): la distribución inicial conservada
    assert 'stroke-width="4"' in dona1
    assert out["fase1"]["impColMonto"]["html"] == "ROC QUE VUELVE"


@_node
def test_fase_2_por_etf_con_desglose_no_queda_pendiente():
    """§7.5 › 2: con país declarado y `fondos[].recuperable_roc` presente, la leyenda
    de la fase 2 NO puede quedar toda en «Pendiente»."""
    out = _ejecutar()
    ley1 = out["fase1"]["impLeyenda"]["html"]
    assert "Pendiente" not in ley1, "con desglose completo la fase 2 pintó «Pendiente»"
    assert "$40.00" in ley1 and "$1.29" in ley1, "faltan los ROC por ETF"
    # §7.5 › 1: la nota de la fase 2 ROTULA LA BASE de su porcentaje (sobre lo retenido,
    # no sobre el bruto como el ROC de la tabla) — 65.7% vs 66% se leían como la misma.
    nota1 = out["fase1"]["impNotas"]["html"]
    assert "de lo retenido al cobro" in nota1


@_node
def test_fase_2_sin_pais_corte_con_cifra_y_etf_pendiente():
    """§4.3: sin país, `vuelve_por_roc`/`definitivo` conservan valor pero
    `fondos[].recuperable_roc` es None en todos → corte agregado con cifra, desglose
    «Pendiente». NO «Sin dato» en el centro."""
    d = copy.deepcopy(_D)
    d["declarado"] = False
    d["peldanos"]["corresponde"] = None
    d["peldanos"]["retenido"]["estado"] = "sin_pais"
    d["peldanos"]["retenido"]["correcta"] = None
    d["peldanos"]["retenido"]["recuperable_roc"] = None
    d["peldanos"]["retenido"]["gap_w8ben"] = None
    for f in d["fondos"]:
        f["recuperable_roc"] = None
        f["retencion_correcta"] = None
        f["gap_w8ben"] = None
        f["indeterminado"] = True
    out = _ejecutar(d=d)
    dona1 = out["fase1"]["impDona"]["html"]
    assert "Retención restante" in dona1 and "$38.71" in dona1, \
        "sin país el corte agregado SÍ tiene cifra (definitivo no es None)"
    assert "Sin dato" not in dona1
    ley1 = out["fase1"]["impLeyenda"]["html"]
    assert ley1.count("Pendiente") >= 2, "sin país, cada ETF va «Pendiente»"


@_node
def test_fase_2_sin_dato_muestra_motivo_nunca_retenido_menos_cero():
    """§6›9 E: si `definitivo` es None → «Sin dato» con `definitivo_motivo`, NUNCA
    retenido − 0."""
    d = copy.deepcopy(_D)
    d["impuesto_local"]["credito_eeuu"]["definitivo"] = None
    d["impuesto_local"]["credito_eeuu"]["definitivo_motivo"] = "sin_dato_de_roc_recuperable"
    out = _ejecutar(d=d)
    dona1 = out["fase1"]["impDona"]["html"]
    assert "Sin dato" in dona1
    assert "no hay dato de ROC recuperable" in dona1
    assert "$80.00" not in dona1.split("imp-center")[-1], \
        "el centro sin dato pintó el retenido — es exactamente el retenido−0 prohibido"
    assert 'data-kind="sin-dato"' in dona1


@_node
def test_seleccion_de_fondo_mueve_el_centro():
    out = _ejecutar()
    sel = out["sel"]["impDona"]["html"]
    assert "MSTY" in sel and "$78.00" in sel
    # la fila del fondo queda marcada como activa/pressed en la leyenda
    ley = out["sel"]["impLeyenda"]["html"]
    fila = re.search(r'<button[^>]*data-sel="f:MSTY"[^>]*>', ley)
    assert fila and 'aria-pressed="true"' in fila.group(0)
    assert 'class="imp-row fund active"' in ley
    # el botón «Ver toda la cartera» se hace visible al fijar una selección
    assert "visible" in out["sel"]["impReset"]["classes"]


@_node
def test_sin_retencion_no_hay_dona_hay_mensaje():
    """§6›9 G / §4.3: `sin_retencion` (schwab_1 real) → sin dona, con mensaje."""
    d = copy.deepcopy(_D)
    d["peldanos"]["retenido"]["monto"] = 0.0
    for f in d["fondos"]:
        f["retenido"] = 0.0
        f["recuperable_roc"] = 0.0
    d["impuesto_local"]["credito_eeuu"] = {"monto": 0.0, "definitivo": 0.0,
                                            "vuelve_por_roc": 0.0, "definitivo_motivo": None}
    out = _ejecutar(d=d)
    dona = out["fase0"]["impDona"]["html"]
    assert "<svg" not in dona, "con retención cero no se dibuja la dona"
    assert "No hubo retención al cobro" in dona
    assert out["fase0"]["impFases"]["html"] == "", "los botones de fase no aplican"


@_node
def test_grupo_unico_sin_encabezados_de_grupo():
    """§6›9 G: un solo portafolio → leyenda sin encabezados de grupo."""
    d = copy.deepcopy(_D)
    d["fondos"] = [f for f in d["fondos"] if f["ticker"] == "MSTY"]
    out = _ejecutar(d=d)
    ley = out["fase0"]["impLeyenda"]["html"]
    assert "Dividendos" not in ley, "con un solo grupo no va encabezado"
    assert 'class="imp-row group' not in ley
    assert "MSTY" in ley


@_node
def test_gate_fase_el_mutante_que_congela_la_fase_pone_estos_tests_en_rojo():
    """Gate (equivalente al viejo if(true)x6): si `__impSetFase` no cambia la fase, la
    fase 2 dibuja lo mismo que la 1 y los tests de fase deben caer. Si sobreviven,
    auditan el flag, no el resultado."""
    script = _primer_script()
    mut = script.replace("fase = (n === 1) ? 1 : 0;", "")
    assert mut != script, "no encontré la asignación de fase — ¿cambió el hook?"
    out = _ejecutar(script=mut)
    assert out["fase0"] == out["fase1"], "sanity: el mutante no cambia nada"
    cayeron = 0
    for fn in (test_fase_2_centro_definitivo_y_anillo_doble,
               test_fase_2_por_etf_con_desglose_no_queda_pendiente):
        try:
            # se re-ejecuta el cuerpo del test con el script mutado: el mutante congela
            # fase 0, así que las afirmaciones de fase 2 sobre out["fase1"] ven fase 0.
            if fn is test_fase_2_centro_definitivo_y_anillo_doble:
                dona1 = out["fase1"]["impDona"]["html"]
                assert "Retención restante" in dona1 and "$38.71" in dona1
                assert 'stroke="url(#refundPattern)"' in dona1
            else:
                ley1 = out["fase1"]["impLeyenda"]["html"]
                assert "Pendiente" not in ley1 and "$40.00" in ley1
        except AssertionError:
            cayeron += 1
    assert cayeron == 2, f"el mutante de fase solo tumbó {cayeron}/2 bloques"


# ── Regla 3b — Σ fondos[].recuperable_roc vs vuelve_por_roc ──────────────────────────

def _D_divergente(sigma=30.0, vuelve=41.29):
    d = copy.deepcopy(_D)
    d["fondos"][0]["recuperable_roc"] = sigma - 1.29
    d["fondos"][1]["recuperable_roc"] = 1.29
    d["impuesto_local"]["credito_eeuu"]["vuelve_por_roc"] = vuelve
    return d


@_node
def test_regla_3b_divergencia_no_pinta_las_dos_cifras_como_equivalentes():
    """U2 §4.2: hoy coinciden en los 4 casos reales (Δ 0.00), pero tienen gates
    distintos (`desglose_ok` vs `reconcilia`). Si divergen, la UI debe NOMBRAR las dos
    cifras y su desacuerdo — nunca pintar una como si fuera la otra."""
    out = _ejecutar(d=_D_divergente(sigma=30.0, vuelve=41.29))
    aviso = out["fase0"]["impAviso3b"]["html"]
    assert "imp-aviso3b" in aviso, "sin aviso con divergencia"
    assert "$30.00" in aviso and "$41.29" in aviso, "el aviso debe nombrar las dos cifras"
    assert "no son la misma cifra" in aviso
    # y el resumen de «Lo que puede volver» no disimula: usa una sola de las dos, la del
    # desglose ok (peldanos.retenido.recuperable_roc = 41.29 en _D), no la Σ inventada.
    volver = out["fase0"]["impSumVolver"]["html"]
    assert "$41.29" in volver


@_node
def test_regla_3b_sin_divergencia_no_hay_aviso():
    out = _ejecutar()  # _D reconcilia: Σ 41.29 == vuelve_por_roc 41.29
    assert out["fase0"]["impAviso3b"]["html"] == "", "aviso 3b sin divergencia"


@_node
def test_mutante_regla_3b_quitar_el_aviso_hace_caer_el_guard():
    script = _primer_script()
    mut = script.replace("if (divergencia) {", "if (false) {")
    assert mut != script
    out = _ejecutar(d=_D_divergente(sigma=30.0, vuelve=41.29), script=mut)
    assert out["fase0"]["impAviso3b"]["html"] == ""
    with pytest.raises(AssertionError):
        aviso = out["fase0"]["impAviso3b"]["html"]
        assert "imp-aviso3b" in aviso


# ── Adapter: campo `grupo` (U2 §5 › 2) ────────────────────────────────────────────────

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


def test_el_adapter_publica_grupo_con_el_criterio_de_classify_tickers():
    """U2 §5 › 2: `grupo` = `logic.classify_tickers`, mismo criterio que
    `ui/heredadas.py:115-118` (mode_a dividendos / mode_b crecimiento)."""
    import logic
    from ui.adapters import impuestos_data
    resultados = _res_minimo()
    resultados["SCHB"] = dict(_res_minimo()["MSTY"])
    datos = impuestos_data(resultados, logic.build_fiscal_profile("Colombia"), [],
                           broker="schwab")
    por_ticker = {f["ticker"]: f for f in datos["fondos"]}
    esperado = logic.classify_tickers(["MSTY", "SCHB"])
    for t, f in por_ticker.items():
        assert "grupo" in f, f"{t}: la clave `grupo` debe EXISTIR (.get() no distingue None de ausente)"
        assert f["grupo"] == esperado[t]
    assert por_ticker["MSTY"]["grupo"] == "mode_a"
    assert por_ticker["SCHB"]["grupo"] == "mode_b"


def test_grupo_no_mueve_ni_una_cifra(monkeypatch):
    """Regla 3: `grupo` agrupa la leyenda; ninguna cifra puede depender de él. Se fuerza
    una clasificación DISTINTA (todo `mode_skip`) y el objeto fiscal —menos la clave
    `grupo`— tiene que salir idéntico. Si una cifra leyera el grupo, esto cae."""
    import logic
    from ui.adapters import impuestos_data
    resultados = _res_minimo()
    resultados["SCHB"] = dict(_res_minimo()["MSTY"])
    perfil = logic.build_fiscal_profile("Colombia")

    base = impuestos_data(resultados, perfil, [], broker=None)
    assert {f["ticker"]: f["grupo"] for f in base["fondos"]} == \
        {"MSTY": "mode_a", "SCHB": "mode_b"}

    monkeypatch.setattr(logic, "classify_tickers",
                        lambda tickers: {str(t).upper(): "mode_skip" for t in tickers})
    mutado = impuestos_data(resultados, perfil, [], broker=None)

    def _sin_grupo(d):
        d = json.loads(json.dumps(d, sort_keys=True, default=str))
        for f in d["fondos"]:
            f.pop("grupo", None)
        return json.dumps(d, sort_keys=True)

    assert {f["ticker"]: f["grupo"] for f in mutado["fondos"]} == \
        {"MSTY": "mode_skip", "SCHB": "mode_skip"}, "el monkeypatch no surtió efecto"
    assert _sin_grupo(base) == _sin_grupo(mutado), \
        "cambiar la clasificación movió una cifra — `grupo` dejó de ser solo render"


# ── «El corte» portado: veredicto + barras (PR 2) ────────────────────────────────────

_TOL = 0.05  # puntos porcentuales


def _segs(html, bar):
    """{data-seg-suffix: width%} de la barra pedida, leídos del HTML renderizado."""
    out = {}
    for suf, w in re.findall(r'data-seg="' + str(bar) + r'-(\w+)"[^>]*?width:\s*([\d.]+)%', html):
        out[suf] = float(w)
    return out


def _cerca(a, b, msg=""):
    assert abs(a - b) <= _TOL, f"{msg}: {a:.4f}% vs {b:.4f}% esperado"


@_node
def test_barra_1_normalizada_a_bruto():
    P = _D["peldanos"]
    bruto, grav = P["bruto"]["monto"], P["gravable"]["monto"]
    s = _segs(_corte(), 1)
    _cerca(s["anchor"], (bruto - grav) / bruto * 100, "barra1 anchor = (bruto−gravable)/bruto")
    _cerca(s["drip"], grav / bruto * 100, "barra1 drip = gravable/bruto")
    _cerca(s["anchor"] + s["drip"], 100.0, "barra1 llena el 100%")


@_node
def test_barra_2_NO_normalizada_comparte_escala_con_la_1():
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
        f"barra2 sumó {suma:.2f}% — está normalizada a 100, ya no comparte escala")
    _cerca(s["rest"], 100.0 - suma, "barra2 rest = 100 − lo retenido")


@_node
def test_barra_3_zoom_sobre_retenido_NO_bruto():
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
    script = _primer_script()
    mut = script.replace(
        "var zC = clampW(ret > 0 ? mC / ret * 100 : 0);",
        "var zC = clampW(bruto > 0 ? mC / bruto * 100 : 0);").replace(
        "var zR = clampW(ret > 0 ? mRR / ret * 100 : 0);",
        "var zR = clampW(bruto > 0 ? mRR / bruto * 100 : 0);").replace(
        "var zG = clampW(ret > 0 ? mGG / ret * 100 : 0);",
        "var zG = clampW(bruto > 0 ? mGG / bruto * 100 : 0);")
    assert mut != script, "no encontré las líneas del divisor de la barra 3 — ¿se renombraron?"
    s = _segs(_corte(script=mut), 3)
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
    """El ORDEN de las ramas del veredicto es la protección: una fixture por rama, se
    asserta borde + titular resultantes (pinado como EFECTO, no como estructura)."""
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
    """Reorden ingenuo (dereferenciar `R.gap_w8ben.monto` sin guard antes de
    `!declarado`) → TypeError sobre null → script muerto → returncode != 0 (#84)."""
    script = _primer_script()
    mut = script.replace(
        "    if (!DATA.declarado) {",
        "    if (R.gap_w8ben.monto > 0.01) { return { borde: 'coral', "
        "kick: kick, big: 'x', sub: '' }; }\n    if (!DATA.declarado) {")
    assert mut != script
    d = _D_para("sin_pais")
    js = mut.replace("{{DATA_JSON}}", json.dumps(d))
    prog = _HARNESS_V2.replace("__SCRIPT__", js)
    r = _corre_node(prog)
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


@_node
def test_banner_de_residencia_solo_sin_pais():
    assert "Falta tu residencia fiscal" in _ejecutar(d=_D_para("sin_pais"))["fase0"]["impStatus"]["html"]
    assert _ejecutar()["fase0"]["impStatus"]["html"] == "", "con país no va banner"


# ── Tokens / CSS ──────────────────────────────────────────────────────────────────────

def test_todo_token_usado_esta_en_los_cuatro_bloques():
    """§5.2: el iframe no ve `ui/tokens.py`. Cualquier `var(--x)` que use el componente
    tiene que estar declarado en los CUATRO bloques (`:root`, `@media dark`,
    `[data-theme=light]`, `[data-theme=dark]`) o cae al color del navegador."""
    with open(_HTML, encoding="utf-8") as f:
        src = f.read()
    style = src[src.index("<style>"):src.index("</style>")]
    usados = set(re.findall(r"var\((--[\w-]+)\)", src))
    bloques = re.findall(r"(?::root(?:\[data-theme=\"\w+\"\])?|@media[^{]+\{\s*:root)\s*\{([^}]*)\}", style)
    assert len(bloques) >= 4, f"esperaba ≥4 bloques de tokens, encontré {len(bloques)}"
    ignora = {"--font-mono", "--font-sans"}   # se declaran una vez, no cambian con el tema
    for tok in sorted(usados - ignora):
        faltan = [i for i, b in enumerate(bloques) if (tok + ":") not in b.replace(" ", "")]
        assert not faltan, f"{tok} usado pero ausente en los bloques de tokens #{faltan}"


# La rampa de la dona se arma por CONCATENACIÓN (`"var(" + rampa[0] + ")"` en `colorDe`),
# así que el regex `var\((--x)\)` del guard de arriba NO la ve. Mismo patrón que el
# `portafolios.html` auditado. Se cubre explícitamente: si un token de la rampa falta en
# algún bloque, el arco cae al color inicial del navegador (bug de `--anchor`/`--drip`,
# PR 2: la barra salió invisible en vivo).
_TOKENS_RAMPA = {"--f1", "--f3", "--f4", "--f5"}


def test_los_tokens_de_la_rampa_de_la_dona_estan_en_los_cuatro_bloques():
    with open(_HTML, encoding="utf-8") as f:
        src = f.read()
    style = src[src.index("<style>"):src.index("</style>")]
    bloques = re.findall(r"(?::root(?:\[data-theme=\"\w+\"\])?|@media[^{]+\{\s*:root)\s*\{([^}]*)\}", style)
    assert len(bloques) >= 4, f"esperaba ≥4 bloques de tokens, encontré {len(bloques)}"
    for tok in sorted(_TOKENS_RAMPA):
        faltan = [i for i, b in enumerate(bloques) if (tok + ":") not in b.replace(" ", "")]
        assert not faltan, f"{tok} (rampa de la dona) ausente en los bloques #{faltan}"


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


# ── Guard de frases (U2 §6 › 3): NINGUNA frase de las 5 vistas desaparece ─────────────

# Fixture que dispara TODO el texto condicional (captura, panel fiscal, los dos CTA de
# gFaltan, aviso de crédito neto, aviso de ROC).
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
_D_FULL["impuesto_local"]["credito_eeuu"] = {"monto": 80.0, "definitivo": 38.71,
                                              "vuelve_por_roc": 41.29,
                                              "definitivo_motivo": None}


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
    return _SCRIPT_RE.findall(r.stdout)[0]


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


# Frases de `main` que pueden NO sobrevivir verbatim en la vista única. U2 §8.bis: cada
# entrada va con su justificación y se reporta a Daniel.
#
# VACÍA, y medido, no asumido: las 5 vistas de `origin/main` (con `_D_FULL`) producen
# 122 frases; TODAS sobreviven verbatim en la vista única (dona + «Ver detalle fiscal»
# + los 4 desplegables), así que no hay ninguna pérdida que aprobar.
#
# La entrada heredada de PR 4 («si tu bróker es IB entre enero y marzo; si es Schwab,
# entre junio y septiembre») se retiró: `origin/main` YA no la emite — PR 4 se mergó y
# los meses viven solo en la franja `.imp-vent`, que sigue sostenida por
# `test_la_franja_de_ventanas_conserva_los_meses_que_salieron_de_la_prosa`. Dejarla aquí
# sería una whitelist tapando un hueco que ya no existe (y podría esconder una regresión
# futura). Verificado corriendo el guard con la whitelist vacía: pasa igual.
_PERDIDAS_APROBADAS = set()


@_node
def test_ninguna_frase_desaparece_al_moverla_a_un_modal(main_script):
    """U2 §6 › 3, extendido a las 5 vistas: el TEXTO RENDERIZADO de las 5 pantallas de
    `origin/main` (incluidos sus `.modal-*`) se compara contra el texto de la vista
    única nueva. Toda frase que estaba y ya no está es una regresión, salvo las de
    `_PERDIDAS_APROBADAS`. No compara fuente (los literales de JS partidos en varias
    líneas dan falsos positivos)."""
    antes = set()
    por_vista = {}
    for vista in _VISTAS_ANTIGUAS:
        rep = _ejecutar_old(vista, main_script, _D_FULL)
        texto = " ".join(v["html"] for v in rep.values() if v.get("html"))
        por_vista[vista] = _frases(texto)
        antes |= por_vista[vista]
    out = _ejecutar(d=_D_FULL)
    ahora = _norm(_texto(out, "fase0") + " " + _texto(out, "fase1"))
    perdidas = {f for f in antes
                if f not in ahora and not any(a in f or f in a for a in _PERDIDAS_APROBADAS)}
    assert not perdidas, (
        f"{len(perdidas)} frase(s) de las 5 vistas desaparecieron en la vista única — "
        "deberían estar verbatim en la dona, en «Ver detalle fiscal» o en los "
        "desplegables (U2 §6›9 F):\n  - " + "\n  - ".join(sorted(perdidas)))


# ── Modales ⓘ: cada uno con su disparador y su cierre ─────────────────────────────────

_MODALES_ESPERADOS = [
    "modal-imp-bruto", "modal-imp-roc", "modal-imp-retenido",
    "modal-imp-correcta", "modal-imp-vuelvesolo", "modal-imp-w8ben",
    "modal-imp-vender", "modal-imp-pais", "modal-imp-tabla",
]


@_node
def test_cada_modal_tiene_su_disparador_y_su_cierre():
    """Cableado: cada `#modal-*` trae su `#modal-*-close` Y un `[data-tip=...]` que lo
    dispara, y `wireModal` se llama para él."""
    out = _ejecutar(d=_D_FULL)
    blob = " ".join(v["html"] for v in out["fase0"].values() if v.get("html"))
    ids = set(re.findall(r'id="(modal-imp-[\w-]+?)"', blob))
    ids = {i for i in ids if not i.endswith("-close") and not i.endswith("-title")}
    assert ids == set(_MODALES_ESPERADOS), (
        f"modales {sorted(ids)}, esperaba {sorted(_MODALES_ESPERADOS)}")
    src = _primer_script()
    for mid in ids:
        tip = mid.replace("modal-", "", 1)
        assert f'id="{mid}-close"' in blob, f"{mid} sin botón de cerrar"
        assert f'data-tip="{tip}"' in blob, f"{mid} sin disparador [data-tip={tip}]"
        assert (f'wireModal("{mid}"' in src) or (f'["{mid}", "{tip}"]' in src), (
            f"{mid} no se cablea con wireModal")


@_node
def test_la_tarjeta_vuelve_solo_manda_el_matiz_puede_al_modal():
    """La nota corta afirma sin reservas lo que la vieja matizaba con «puede»: el matiz
    tiene que estar en el modal."""
    html = _corte(_D_FULL)
    card = re.search(r'imp-bucket ambar.*?</div>', html, re.S).group(0)
    assert "puede volver solo" not in card.lower(), "la tarjeta ya no debe llevar el «puede»"
    modal = re.search(r'id="modal-imp-vuelvesolo".*?</div></div>', html, re.S).group(0)
    assert "Puede volver solo en el cierre anual del bróker" in modal, (
        "el modal de «Vuelve solo» perdió el matiz condicional")


# ── §7.5 › 3: los desplegables que cubren las 5 vistas ────────────────────────────────

_DESPLEGABLES = [
    ("det-corte", "El corte"),
    ("det-tabla", "Ver detalle fiscal"),
    ("det-volver", "Lo que puede volver"),
    ("det-irs", "Vía IRS"),
    ("det-pais", "Dividendos y crédito fiscal"),
    ("det-venta", "Ventas y base fiscal"),
]


def test_los_desplegables_cubren_las_cinco_vistas():
    """§7.5 › 3: «Lo que puede volver», «Vía IRS», «Ventas y base fiscal» y el crédito
    fiscal + «Ver detalle fiscal» y «El corte». Sin ellos no se cubren las 5 vistas."""
    with open(_HTML, encoding="utf-8") as f:
        src = f.read()
    for did, titulo in _DESPLEGABLES:
        assert f'id="{did}"' in src, f"falta el desplegable {did}"
        assert titulo in src, f"falta el título {titulo!r}"


@_node
def test_tabla_roc_rotula_su_base_sobre_el_bruto():
    """§7.5 › 1: el ROC sale como 66% sobre el bruto en la tabla y 65.7% sobre lo
    retenido en la fase 2. Las DOS superficies rotulan su base."""
    out = _ejecutar(d=_D_FULL)
    tabla = out["fase0"]["impTabla"]["html"]
    assert "% del bruto" in tabla, "la columna ROC de la tabla no rotula su base"
    assert "sobre el bruto" in tabla, "el ROC total no rotula su base"
    nota1 = out["fase1"]["impNotas"]["html"]
    assert "de lo retenido al cobro" in nota1, "la fase 2 no rotula su base"


# ── PR 4 portado: la franja de ventanas por bróker ────────────────────────────────────

_VENTANAS = [
    {"broker": "ibkr", "label": "Interactive Brokers", "desde": 1, "hasta": 3},
    {"broker": "schwab", "label": "Schwab", "desde": 6, "hasta": 9},
]


def _con_broker(broker):
    d = json.loads(json.dumps(_D_FULL))
    d["ruta_a"]["broker"] = broker
    d["ruta_a"]["ventanas"] = json.loads(json.dumps(_VENTANAS))
    return d


def _rutaA(d):
    return _ejecutar(d=d)["fase0"]["impRutaA"]["html"]


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
    """Sostiene la entrada de `_PERDIDAS_APROBADAS`: si la franja no marca esos MISMOS
    meses, la información se perdió de verdad."""
    filas = _filas_franja(_rutaA(_con_broker(None)))
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
    html = _rutaA(_con_broker(broker))
    filas = _filas_franja(html)
    activas = [f[0] for f in filas if not f[1]]
    apagadas = [f[0] for f in filas if f[1]]
    assert any(label_tuyo in a for a in activas), f"la fila de {label_tuyo} debe ir activa"
    assert any(apagado in a for a in apagadas), f"la fila de {apagado} debe ir apagada"
    assert "tu bróker" in html, "falta la marca «tu bróker» en la fila del cliente"
    assert label_tuyo in html and "cae en la ventana marcada arriba" in html


@_node
def test_sin_broker_se_muestran_las_dos_sin_apagar_ninguna():
    html = _rutaA(_con_broker(None))
    assert not any(f[1] for f in _filas_franja(html)), "sin bróker no se apaga ninguna"
    assert "No pudimos identificar tu bróker" in html
    assert "tu bróker</span>" not in html, "sin bróker no se marca ninguna como tuya"


@_node
def test_la_frase_del_ano_va_identica_en_las_tres_ramas():
    for b in (None, "schwab", "ibkr"):
        html = _rutaA(_con_broker(b))
        assert "Es el cierre fiscal del año que analizaste, no de este." in html, (
            f"la cola del año cambió con broker={b!r}")


@_node
def test_la_franja_no_lleva_ano_ni_marca_de_hoy():
    """Regla 2: un eje fechado —o un «hoy» sobre él— pondría dos momentos en la misma
    línea."""
    html = _rutaA(_con_broker("schwab"))
    franja = html[html.find('class="imp-vent"'):html.find("</div>", html.find("imp-vent-fila"))]
    assert not re.search(r"\b20\d{2}\b", franja), "la franja no debe llevar año"
    assert "hoy" not in franja.lower(), "la franja no debe marcar «hoy»"


# --- Capa del ADAPTER (PR 4, sin cambios) ---------------------------------------------

def _ruta_a(broker):
    import logic
    from ui.adapters import impuestos_data
    return impuestos_data(_res_minimo(), logic.build_fiscal_profile("Colombia"), [],
                          broker=broker)["ruta_a"]


@pytest.mark.parametrize("entrada,esperado", [
    ("schwab", "schwab"),
    ("ibkr", "ibkr"),
    # 'generic' es «no lo reconocí», no un bróker.
    ("generic", None),
    (None, None),
    ("", None),
    ("SCHWAB", None),   # sin normalizar mayúsculas: lo que no viene tal cual, no pasa
])
def test_el_adapter_solo_publica_broker_reconocido(entrada, esperado):
    assert _ruta_a(entrada)["broker"] == esperado


def test_el_adapter_publica_las_ventanas_reales_de_cada_broker():
    """Ground truth, no un espejo del código: IB reclasifica ene-mar y Schwab jun-sep."""
    vent = {v["broker"]: v for v in _ruta_a("schwab")["ventanas"]}
    assert set(vent) == {"ibkr", "schwab"}
    assert (vent["ibkr"]["desde"], vent["ibkr"]["hasta"]) == (1, 3)
    assert (vent["schwab"]["desde"], vent["schwab"]["hasta"]) == (6, 9)
    assert vent["ibkr"]["label"] == "Interactive Brokers"
    assert vent["schwab"]["label"] == "Schwab"


def test_el_broker_no_mueve_ni_una_cifra():
    """`broker` solo gobierna qué ventana se resalta (Regla 3)."""
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


# ── Gap de W-8BEN residual (GAP_MATERIAL) — el titular no puede decir «todo» ──────────

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


def money_es(x):
    return ("−$" if x < 0 else "$") + f"{abs(x):.2f}"


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


@_node
@pytest.mark.parametrize("gap", [0.0, 0.004, 0.01, 5.0, 18.71])
def test_titular_y_tarjeta_de_w8ben_no_se_contradicen(gap):
    """El gate de verdad (regla 3b): comparar las DOS vistas del mismo número entre sí.
    Este test no conoce el umbral — solo exige que las dos superficies cuenten lo
    mismo."""
    html = _corte(_D_gap(gap, 41.29))
    big, _ = _titular_y_sub(html)
    # Se lee la tarjeta REAL (la coral es la de W-8BEN), sin fallback: si la tarjeta no
    # está, esto FALLA — sin las dos superficies no hay nada que reconciliar.
    tarjeta = re.search(r'imp-bucket coral".*?imp-bucket-money">([^<]+)<', html, re.S)
    assert tarjeta, "no encontré la tarjeta coral de W-8BEN en la barra 3"
    monto_tarjeta = tarjeta.group(1)
    muestra_resto = monto_tarjeta != "$0.00"
    absoluto = ("Todo el exceso vuelve solo" in big) or ("justo lo que te tocaba" in big)
    assert not (muestra_resto and absoluto), (
        f"gap={gap}: la tarjeta muestra {monto_tarjeta} y el titular dice {big!r} — "
        "las dos vistas del mismo número se contradicen")


@_node
@pytest.mark.parametrize("roc", [0.0, 0.004, 0.005, 0.01, 0.02, 41.29])
def test_titular_y_tarjeta_del_roc_no_se_contradicen(roc):
    """La hermana del test de arriba, sobre la tarjeta ÁMBAR («Vuelve solo»). Auditoría M4,
    ronda 2 (R2-H4): con un ROC recuperable de EXACTAMENTE $0.01 el titular decía «justo lo
    que te tocaba» mientras la tarjeta mostraba $0.01 — el mismo borde del centavo que el
    #115 cerró para el W-8BEN, en la rama de al lado (`roc > 0.01`).

    Tampoco conoce el umbral: exige que las dos superficies cuenten lo mismo en los dos
    sentidos. Si la tarjeta muestra dinero que vuelve, el titular no puede decir que te
    retuvieron «justo» lo tuyo; si la tarjeta muestra $0.00, el titular no puede anunciar un
    exceso que vuelve."""
    html = _corte(_D_gap(0.0, roc))
    big, _ = _titular_y_sub(html)
    tarjeta = re.search(r'imp-bucket ambar".*?imp-bucket-money">([^<]+)<', html, re.S)
    assert tarjeta, "no encontré la tarjeta ámbar («Vuelve solo») en la barra 3"
    monto_tarjeta = tarjeta.group(1)
    if monto_tarjeta != "$0.00":
        assert "justo lo que te tocaba" not in big, (
            f"roc={roc}: la tarjeta muestra {monto_tarjeta} que vuelven y el titular dice {big!r}")
    else:
        assert "vuelve solo" not in big, (
            f"roc={roc}: la tarjeta muestra $0.00 y el titular dice {big!r}")
