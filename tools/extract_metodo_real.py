#!/usr/bin/env python3
"""Extrae el componente «Matriz 2» (Método tradicional · las cuatro lecciones de «La
matriz» sobre el portafolio REAL del CSV cargado — traspaso 2026-08-17).

No hay diseño nuevo que aprobar (Decisión 2 del traspaso): reusa la hoja de estilos
completa y el vocabulario visual de `ui/componentes/metodo.html` (`.he-grid`/`.he-c`/
`.he-h`/`.tm-grid*`/`.tm-escalera`/`.tm-step`/`.cmp-head`/`.cmp-summary`/`.cmp-notes`),
igual que `tools/extract_comparacion_real.py` reusó CSS/panel de `comparacion.html`
para `comparacion_real.html`.

A diferencia de Comparación · Real, aquí NO hay un panel poblado del demo del que
derivar por sustitución quirúrgica: el panel «Matriz 2» del demo (`met-panel-matriz2`)
sigue siendo un placeholder «En diseño» (igual que `cmp-panel-real` lo fue hasta que se
construyó su componente) — así que el HTML/JS de las 4 secciones se ESCRIBE aquí,
reusando únicamente las CLASES CSS ya existentes (cero regla nueva), nunca copiando
literales del demo. `initMetodo()` (~780 líneas) audita la cartera FIJA de Greco y no
sirve de plantilla: cablea 5 filas fijas, no un número arbitrario de tickers.

Produce `ui/componentes/metodo_real.html`, con un hueco: `{{DATA_JSON}}`, que rellena
`ui.adapters.metodo_real_data`.

    python3 tools/extract_metodo_real.py [--check]
"""
import argparse
import os
import re
import sys

from _auto_alto import AUTO_ALTO_JS

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(BASE, "ui", "componentes", "metodo_real.html")

DEFAULT_DEMO = os.path.expanduser(
    "~/Desktop/Habilidades de agentes/Obsidian/APPs/Dividend-Analyzer/demos/"
    "viaje-dinero-waterfall.html"
)


def load_demo() -> str:
    path = os.environ.get("DIVIDEND_DEMO_HTML", DEFAULT_DEMO)
    if not os.path.exists(path):
        sys.exit(f"No encuentro el demo en {path}\n"
                 "Indica su ruta con DIVIDEND_DEMO_HTML=/ruta/al/demo.html")
    with open(path, encoding="utf-8") as f:
        return f.read()


def cargar_css(html: str) -> str:
    """Hoja de estilo completa del artifact — mismo bloque que usan los demás
    extractores (el que declara `--ground:`). Verbatim, sin recortar: las clases que
    usa este panel (`tm-grid6`, `tm-grid3`, `tm-grid2`, `tm-escalera`/`tm-step`,
    `he-block`/`he-block-lab`, `cmp-head`/`cmp-summary`/`cmp-notes`, `soon`) ya viven
    ahí, definidas para «La matriz»/Comparación — no se declara ninguna regla nueva."""
    for m in re.finditer(r"<style>.*?</style>", html, re.S):
        if "--ground:" in m.group(0):
            return m.group(0)
    sys.exit("No encontré el bloque de estilos del diseño (el que declara --ground).")


PANEL = """    <div class="panel" id="met-panel-matriz2" role="tabpanel">
      <header class="cmp-head">
        <h2 class="cmp-title">Matriz 2 &middot; tu portafolio</h2>
        <p class="cmp-lede">Las mismas cuatro lecciones de &laquo;La matriz&raquo; &mdash; aplicadas a <b>tu CSV real</b>: tu DRIP (parcial, no total), tu retenci&oacute;n efectiva y tu tasa fiscal declarada, no la simulaci&oacute;n de la cartera de Greco.</p>
      </header>

      <div class="he-scroll">
        <div class="he-grid tm-grid6" id="m2Grid">
          <div class="he-h he-l"><span class="he-lab">Acci&oacute;n</span></div>
          <div class="he-h"><span class="he-lab">Inicio</span></div>
          <div class="he-h he-mark"><span class="he-lab">Inversi&oacute;n</span></div>
          <div class="he-h"><span class="he-lab">Dividendos</span></div>
          <div class="he-h"><span class="he-lab">Total inv.</span></div>
          <div class="he-h he-mark"><span class="he-lab">Valor mer.</span></div>
        </div>
      </div>
      <p class="cmp-notes" id="m2Notes"></p>
      <p class="cmp-notes" id="m2Excluidos"></p>

      <div class="he-block">
        <p class="he-block-lab">El rendimiento</p>
        <div class="tm-escalera" id="m2Escalera"></div>
        <p class="cmp-summary" id="m2EscaleraCierre"></p>
        <p class="cmp-notes" id="m2EscaleraNotas"></p>
      </div>

      <div class="he-block">
        <p class="he-block-lab">Payback &ne; ganancia</p>
        <div class="he-scroll">
          <div class="he-grid tm-grid3" id="m2PaybackGrid">
            <div class="he-h he-l"><span class="he-lab">Acci&oacute;n</span></div>
            <div class="he-h"><span class="he-lab">Payback bruto</span></div>
            <div class="he-h"><span class="he-lab">Payback neto<span class="he-sub">tu tasa</span></span></div>
            <div class="he-h"><span class="he-lab">Retorno real</span></div>
          </div>
        </div>
        <p class="cmp-summary" id="m2PaybackMsg"></p>
        <p class="cmp-notes" id="m2PaybackNra"></p>
      </div>

      <div class="he-block">
        <p class="he-block-lab">Rendimiento vs. tasa de distribuci&oacute;n</p>
        <div class="he-scroll">
          <div class="he-grid tm-grid2" id="m2TasaGrid">
            <div class="he-h he-l"><span class="he-lab">Acci&oacute;n</span></div>
            <div class="he-h"><span class="he-lab">Ca&iacute;da de precio</span></div>
            <div class="he-h"><span class="he-lab">Yield realizado</span></div>
          </div>
        </div>
        <p class="cmp-notes" id="m2TasaNotes"></p>
        <p class="cmp-notes" id="m2SinFicha"></p>
      </div>
    </div>
"""

# El módulo JS: sin equivalente en el demo (no hay `initMetodo` que leer datos
# arbitrarios por ticker, solo 5 filas fijas de Greco). Escrito para este componente,
# reusando el vocabulario de formato (`fmtMoney`/`fmtPct1`/`fmtWhole`) que ya define
# `metodo.html` — mismos nombres, misma forma, para que un lector que conozca «La
# matriz» reconozca el patrón aquí.
SCRIPT = """(function initMatriz2() {
    "use strict";
    var DATA = {{DATA_JSON}};

    function fmtMoney(x) { var n = Math.abs(x); return (x < 0 ? "\\u2212" : "") + "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
    function fmtWhole(x) { return (x >= 0 ? "+" : "\\u2212") + "$" + Math.round(Math.abs(x)).toLocaleString("en-US"); }
    function fmtPct1(x) { return (x >= 0 ? "+" : "\\u2212") + Math.abs(x).toFixed(1) + "%"; }
    function fmtD(x) { return "$" + Math.round(x).toLocaleString("en-US"); }
    function setHtml(id, html) { var el = document.getElementById(id); if (el) el.innerHTML = html; }
    var MESES_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
    function fmtFechaCorta(iso) {
      if (!iso) return "";
      var p = String(iso).split("-");
      if (p.length !== 3) return "";
      var mIdx = parseInt(p[1], 10) - 1;
      return parseInt(p[2], 10) + " " + (MESES_ES[mIdx] || p[1]) + " " + p[0];
    }

    // ============ 1 · LA MATRIZ ============
    (function renderMatriz() {
      var rows = "";
      DATA.matriz.forEach(function (r) {
        var divOk = r.div >= r.inv;
        var valOk = r.val >= r.inv;
        rows +=
          '<div class="he-c he-l he-row-lab he-tk he-muted">' + r.t + '</div>' +
          '<div class="he-c he-mono">' + (r.ini || "\\u2014") + '</div>' +
          '<div class="he-c num">' + fmtMoney(r.inv) + '</div>' +
          '<div class="he-c num' + (divOk ? " he-cash" : "") + '">' + fmtMoney(r.div) + '</div>' +
          '<div class="he-c num">' + fmtMoney(r.tot) + '</div>' +
          '<div class="he-c num ' + (valOk ? "he-cash" : "he-loss") + '">' + fmtMoney(r.val) + '</div>';
      });
      rows +=
        '<div class="he-c he-l he-row-lab">TOTAL</div>' +
        '<div class="he-c he-ph">\\u2014</div>' +
        '<div class="he-c num">' + fmtMoney(DATA.tot.inv) + '</div>' +
        '<div class="he-c num he-cash">' + fmtMoney(DATA.tot.div) + '</div>' +
        '<div class="he-c num">' + fmtMoney(DATA.tot.tot) + '</div>' +
        '<div class="he-c num he-cash">' + fmtMoney(DATA.tot.val) + '</div>';
      document.getElementById("m2Grid").insertAdjacentHTML("beforeend", rows);

      setHtml("m2Notes",
        '<span class="flag">Lo correcto:</span> <span class="num">Retorno total real = Valor mer. + efectivo cobrado \\u2212 Inversi\\u00f3n</span> \\u2014 a diferencia de \\u00abLa matriz\\u00bb (DRIP total), aqu\\u00ed tu DRIP fue parcial: parte de los dividendos se cobr\\u00f3 en efectivo y nunca volvi\\u00f3 a comprar acciones, as\\u00ed que sumar Inversi\\u00f3n + Dividendos como hace la fila \\u00abTotal inv.\\u00bb sobreestima \\u2014 esa suma NO es tu retorno.' +
        (DATA.asof ? ' Datos al ' + fmtFechaCorta(DATA.asof) + '.' : ''));

      if (DATA.excluidos && DATA.excluidos.length) {
        setHtml("m2Excluidos",
          '<span class="flag">Excluidos de esta matriz</span> (sus cifras no reconciliaron): ' +
          DATA.excluidos.map(function (e) { return e.t + ' (' + e.motivo + ')'; }).join('; ') + '.');
      }
    })();

    // ============ 2 · EL RENDIMIENTO (ESCALERA) ============
    (function renderEscalera() {
      var esc = DATA.escalera;
      if (!esc) {
        setHtml("m2EscaleraCierre", "No hay posiciones con capital aportado en el CSV, as\\u00ed que no hay retorno que escalonar.");
        return;
      }
      // `xirrPct` es el retorno anual EXACTO (TIR sobre los flujos en sus fechas
      // reales, `logic.xirr`). No hay un plazo que elegir: con compras repartidas en
      // decenas de fechas, cualquier "N a\\u00f1os" ser\\u00eda una convenci\\u00f3n inventada, y
      // elegirla mueve el resultado. Si no se pudo resolver, el pelda\\u00f1o anualizado
      // se omite \\u2014 nunca se rellena con una aproximaci\\u00f3n disfrazada de medici\\u00f3n.
      var anual = (esc.xirrPct === null || esc.xirrPct === undefined)
        ? '' : '<span class="tm-step-anual num">' + fmtPct1(esc.xirrPct) + '/a\\u00f1o</span>';
      var ESCALERA = [
        { lab: "Lo que dir\\u00eda la hoja", val: fmtPct1(esc.hojaPct), estado: "mal" },
        { lab: "Su misma f\\u00f3rmula, bien aplicada", val: fmtPct1(esc.realPct) + anual, estado: "ok" },
        { lab: "Si los dividendos fueran efectivo", val: "no disponible", estado: "na" },
        { lab: "El n\\u00famero real", val: fmtPct1(esc.realPct) + anual, estado: "real" }
      ];
      var subAnual = anual
        ? ', que anualizado sobre las fechas reales de tus compras y cobros da <b class="num">' + fmtPct1(esc.xirrPct) + ' al a\\u00f1o</b>'
        : '';
      var SUB = [
        'Payback disfrazado de retorno: (Inversi\\u00f3n + Dividendos \\u2212 Inversi\\u00f3n) \\xf7 Inversi\\u00f3n \\u2014 el dinero de los dividendos ya vive dentro de Valor mer., contarlo dos veces infla el resultado.',
        'Retorno real: <b class="num">' + fmtWhole(esc.realD) + '</b>' + subAnual + '.',
        'Este paso necesita el valor de mercado de solo las acciones compradas con tu dinero (sin las que hubiera comprado el DRIP) valoradas hoy \\u2014 tu CSV tiene compras fraccionadas en muchas fechas y esa cifra no existe todav\\u00eda en los datos que ya calcula la app; no se inventa.',
        'El mismo n\\u00famero de la fila de arriba: no hay un quinto c\\u00e1lculo distinto \\u2014 \\u00abbien aplicada\\u00bb y \\u00abreal\\u00bb son la misma f\\u00f3rmula.'
      ];
      var html = "";
      ESCALERA.forEach(function (e, i) {
        html += '<div class="tm-step ' + e.estado + '">' +
          '<div class="tm-step-lab">' + e.lab + '</div>' +
          '<div class="tm-step-val num">' + e.val + '</div>' +
          '<div class="tm-step-sub">' + SUB[i] + '</div>' +
          '</div>';
      });
      document.getElementById("m2Escalera").innerHTML = html;

      setHtml("m2EscaleraCierre",
        'Tu portafolio no rindi\\u00f3 ' + fmtPct1(esc.hojaPct) + '. Rindi\\u00f3 <b>' + fmtPct1(esc.realPct) + '</b> en total'
        + (anual ? ', <b>' + fmtPct1(esc.xirrPct) + ' al a\\u00f1o</b>' : '') + '.');
      setHtml("m2EscaleraNotas",
        'El anualizado es una <b>TIR</b> sobre los flujos en sus fechas reales, no un promedio: cada d\\u00f3lar pesa por el tiempo que estuvo invertido. Por eso no aparece ning\\u00fan \\u00abhace N a\\u00f1os\\u00bb \\u2014 tus compras est\\u00e1n repartidas en muchas fechas y elegir un plazo \\u00fanico ser\\u00eda inventar la mitad de la respuesta.');
    })();

    // ============ 3 · PAYBACK \\u2260 GANANCIA ============
    (function renderPayback() {
      var contraTk = DATA.paybackContraejemplo;
      var rows = "";
      DATA.ratios.forEach(function (r) {
        var esContra = contraTk && r.t === contraTk;
        var flag = esContra ? " tm-flag" : "";
        rows +=
          '<div class="he-c he-l he-row-lab he-tk' + flag + '">' + r.t + (esContra ? '<span class="he-sub" style="color:var(--loss)">cobr\\u00f3 y perdi\\u00f3</span>' : '') + '</div>' +
          '<div class="he-c num' + flag + '">' + r.pb.toFixed(2) + '\\u00d7</div>' +
          '<div class="he-c num he-muted' + flag + '">' + (r.pbn != null ? r.pbn.toFixed(2) + '\\u00d7' : '\\u2014') + '</div>' +
          '<div class="he-c num ' + (r.ret >= 0 ? "he-cash" : "he-loss") + flag + '">' + fmtPct1(r.ret) + '<span class="he-sub">(' + fmtWhole(r.retD) + ')</span></div>';
      });
      var rt = DATA.ratiosTot;
      rows +=
        '<div class="he-c he-l he-row-lab">TOTAL</div>' +
        '<div class="he-c num">' + rt.pb.toFixed(2) + '\\u00d7</div>' +
        '<div class="he-c num he-muted">' + (rt.pbn != null ? rt.pbn.toFixed(2) + '\\u00d7' : '\\u2014') + '</div>' +
        '<div class="he-c num ' + (rt.ret >= 0 ? "he-cash" : "he-loss") + '">' + fmtPct1(rt.ret) + '<span class="he-sub">(' + fmtWhole(rt.retD) + ')</span></div>';
      document.getElementById("m2PaybackGrid").insertAdjacentHTML("beforeend", rows);

      if (contraTk) {
        var contra = DATA.ratios.filter(function (r) { return r.t === contraTk; })[0];
        setHtml("m2PaybackMsg",
          'El test verde de la hoja (dividendos \\u2265 inversi\\u00f3n) <b>es real</b> \\u2014 se llama <b>payback ratio</b> y mide cu\\u00e1nto de tu capital ya volvi\\u00f3. Pero es <b>necesario, no suficiente</b>: ' +
          contra.t + ' tiene payback <b>' + contra.pb.toFixed(2) + '\\u00d7</b> y aun as\\u00ed perdi\\u00f3 <b class="dn">' + fmtPct1(contra.ret) + '</b> de capital.');
      } else {
        setHtml("m2PaybackMsg",
          'El test verde de la hoja (dividendos \\u2265 inversi\\u00f3n) <b>es real</b> \\u2014 se llama <b>payback ratio</b> y mide cu\\u00e1nto de tu capital ya volvi\\u00f3. Pero es <b>necesario, no suficiente</b>: cobrar de vuelta tu dinero y ganar dinero no son la misma cosa, aunque en tu portafolio ning\\u00fan ticker lo ilustra hoy.');
      }

      if (DATA.nra.paisDeclarado) {
        setHtml("m2PaybackNra",
          'Con tu tasa declarada' + (DATA.nra.pais ? ' (' + DATA.nra.pais + ')' : '') + ' de ' + DATA.nra.tasaPct + '%: ' + fmtMoney(DATA.nra.divBruto) + ' brutos \\u2192 ~' + fmtMoney(DATA.nra.netoDeclarado) + ' netos tras la reclasificaci\\u00f3n anual del ROC (19a). \\u00abPayback neto\\u00bb usa esta cifra, no un 30% plano.');
      } else {
        setHtml("m2PaybackNra",
          'Los dividendos de esta matriz son <b>brutos</b>: ' + fmtMoney(DATA.nra.divBruto) + ', con ' + fmtMoney(DATA.nra.retenidoReal) + ' de retenci\\u00f3n NRA ya observada en tu CSV. Declara tu residencia fiscal para ver \\u00abPayback neto\\u00bb con tu tasa \\u2014 sin pa\\u00eds declarado no se asume ning\\u00fan porcentaje.');
      }
    })();

    // ============ 4 · RENDIMIENTO VS TASA ============
    (function renderTasa() {
      var rows = "";
      DATA.matriz.forEach(function (r) {
        var m = DATA.ymMedido[r.t];
        if (!m || !m.conFicha) return;
        var precio = m.precioCagrPct;
        rows +=
          '<div class="he-c he-l he-row-lab he-tk">' + r.t + '</div>' +
          '<div class="he-c num' + (precio != null && precio < 0 ? " he-loss" : "") + '">' + (precio != null ? fmtPct1(precio) + '/a\\u00f1o' : '\\u2014') + '</div>' +
          '<div class="he-c num he-warn">' + m.yieldRealizadoPct.toFixed(1) + '%</div>';
      });
      document.getElementById("m2TasaGrid").insertAdjacentHTML("beforeend", rows);

      setHtml("m2TasaNotes",
        '<b>Yield realizado</b> = dividendos brutos cobrados \\xf7 capital aportado (el mismo payback bruto de arriba, en porcentaje). <b>Ca\\u00edda de precio</b> es el retorno de precio anualizado que ya mide la app (Salud del NAV) \\u2014 cuando el yield es alto y el precio cae fuerte, la distribuci\\u00f3n se est\\u00e1 pagando devolvi\\u00e9ndote tu propio capital, no generando uno nuevo.');

      if (DATA.sinFicha && DATA.sinFicha.length) {
        setHtml("m2SinFicha",
          '<span class="flag">Sin ficha del emisor:</span> ' + DATA.sinFicha.join(', ') +
          ' \\u2014 la app no tiene conocimiento cargado para interpretarlos, pero su ca\\u00edda de precio y su yield realizado se miden igual que al resto (fila ' + DATA.sinFicha.join('/') + ' arriba, aunque no aparezca en esta tabla espec\\u00edfica de fichas).');
      }
    })();
})();
"""


def extraer(html: str) -> str:
    css = cargar_css(html)

    return f"""<!-- GENERADO POR tools/extract_metodo_real.py — NO EDITAR A MANO.
     Fuente: hoja de estilos de `ui/componentes/metodo.html` (mismo demo), reusada
     verbatim — el panel y el script de esta sección son propios (no hay panel poblado
     del demo que derivar: `met-panel-matriz2` sigue siendo un placeholder «En diseño»).
     Para cambiar algo, se cambia este extractor y se regenera. -->
<meta charset="utf-8">
{css}
<style>
  body {{ margin: 0; background: var(--ground); }}
</style>
<main class="wrap" style="padding-top:0">
{PANEL}
</main>
<script>
(function () {{
  "use strict";
{SCRIPT}
}})();
</script>
{AUTO_ALTO_JS}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="no escribe; falla si lo generado difiere de lo que hay en disco")
    args = ap.parse_args()

    contenido = extraer(load_demo())
    rel = os.path.relpath(SALIDA, BASE)

    if args.check:
        actual = open(SALIDA, encoding="utf-8").read() if os.path.exists(SALIDA) else None
        if actual != contenido:
            print(f"DESACTUALIZADO respecto al demo: {rel}")
            return 1
        print("OK — el componente coincide con el demo")
        return 0

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8") as f:
        f.write(contenido)
    if "{{DATA_JSON}}" not in contenido:
        sys.exit("El componente salió sin el hueco {{DATA_JSON}} — revisa el extractor.")
    print(f"generado: {rel}  ({len(contenido):,} caracteres, hueco DATA_JSON)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
