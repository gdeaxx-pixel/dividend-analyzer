#!/usr/bin/env python3
"""Extrae el componente «Comparación · Real» (Total Return Graph con datos reales).

No hay diseño nuevo que aprobar (decisión 6 del traspaso 2026-08-10): el panel `Real`
del demo sigue siendo un placeholder «En diseño» — este componente se DERIVA del panel
de Simulación (`tools/extract_comparacion.py`), reusando su CSS, su tooltip y su panel
base para no duplicar ese archivo, y aplicando solo las sustituciones necesarias para
que `initComparacion()` deje de ser un modelo paramétrico (`hash`/`bump`/`shapeOf`/
`targetEnd` + la tabla `F` con cifras inventadas) y pase a LEER el índice TRI real que
manda `ui.adapters.trg_real_data` en `{{DATA_JSON}}`.

`series()`, `draw()`, `renderControls()`, `bindHover()` y `renderSummaryNotes()` NO se
tocan salvo la única línea de `renderSummaryNotes` que declaraba «Cifras del demo» —
ahí está la paridad visual con la Simulación, y es lo que hace barato este cambio.

Produce `ui/componentes/comparacion_real.html`, con un hueco que rellena Python en
cada rerun:

    {{DATA_JSON}}   el índice TRI de 8 tickers × 3 modos + metadatos, desde
                     `ui.adapters.trg_real_data`

    python3 tools/extract_comparacion_real.py [--check]
"""
import argparse
import os
import sys

from _auto_alto import AUTO_ALTO_JS
from extract_comparacion import (TIP_HTML, cargar_css, cargar_panel_simulacion,
                                 cargar_script_comparacion, cargar_tooltip, load_demo)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(BASE, "ui", "componentes", "comparacion_real.html")


def _reemplazar(texto: str, viejo: str, nuevo: str, que: str) -> str:
    if viejo not in texto:
        sys.exit(f"No encontré {que} — ¿cambió el demo? Revisa si esta sustitución sigue "
                 "siendo válida (tools/extract_comparacion_real.py).")
    return texto.replace(viejo, nuevo, 1)


def transformar_panel(panel: str) -> str:
    """Deriva el panel de «Real» del de Simulación: mismo HTML, otro id y otro
    encabezado — sin tocar controles/SVG/notas (son los mismos ids, y el componente
    vive en su propio iframe, así que no chocan con los de Simulación)."""
    panel = _reemplazar(
        panel, '<div class="panel" id="cmp-panel-simulacion" role="tabpanel">',
        '<div class="panel" id="cmp-panel-real" role="tabpanel">',
        "la apertura del panel de Simulación")
    panel = _reemplazar(
        panel, '<h2 class="cmp-title">Total Return Graph · simulación</h2>',
        '<h2 class="cmp-title">Total Return Graph · datos reales</h2>',
        "el título del panel")
    # Invariante de auditoría (feedback_dividend-invariante-roc-nra): toda cifra
    # fiscal declara su base y su momento. `{{ASOF}}` lo rellena `render_comparacion_
    # real` (ui/componentes/__init__.py) con `datos["asof"]` — no puede resolverse en
    # tiempo de extracción (build-time, sin cartera ni fecha de corrida).
    panel = _reemplazar(
        panel,
        '<p class="cmp-lede">Un fondo YieldMax contra ETFs de crecimiento en <b>igualdad '
        'de condiciones</b>: rendimiento total con distribuciones reinvertidas (DRIP), '
        'normalizado a <b>0% en la incepción del fondo base</b>.</p>',
        '<p class="cmp-lede">Un fondo YieldMax contra ETFs de crecimiento en <b>igualdad '
        'de condiciones</b>: rendimiento total con distribuciones reinvertidas (DRIP), '
        'normalizado a <b>0% en la incepción del fondo base</b>. Calculado sobre precios '
        'y dividendos reales hasta el {{ASOF}}, con reinversión por evento al cierre del '
        'día ex-dividendo.</p>',
        "el lede del panel")
    return panel


def transformar_script(script: str) -> str:
    """`initComparacion()` deja de ser un modelo paramétrico: lee `{{DATA_JSON}}` en
    vez de fabricar formas sintéticas. Cada sustitución busca su literal y falla con
    `sys.exit` si no aparece — mismo patrón que el resto de extractores."""
    script = _reemplazar(
        script,
        '    var LAST = 38, RATE = 0.30;            // May 2023 (0) .. Jul 2026 (38)\n',
        '    var DATA = {{DATA_JSON}}, LAST = DATA.last;\n',
        "la declaración de LAST/RATE")

    script = _reemplazar(
        script,
        '    function mDate(m) { return new Date(2023, 4 + m, 1); }\n',
        '    function mDate(m) { return new Date(DATA.origen[0], DATA.origen[1] + m, 1); }\n',
        "mDate()")

    script = _reemplazar(
        script,
        '    var COL = { NVDY:"#1f86c4", TSLY:"#d1662f", CONY:"#b95cae", MSTY:"#a8b020",\n'
        '                CHPY:"#17a89a", SCHB:"#b06a3d", XLK:"#8f76d4", SMH:"#c99a26" };\n',
        '    var COL = DATA.col;\n',
        "el objeto COL")

    # El comentario documenta las cifras ilustrativas de `roc` en F — ya no aplica:
    # F solo trae incep/grp, y `roc` real vive en knowledge/roc_19a.yaml (lo consume
    # logic.build_drip_comparison_series, no este componente). Se cae junto con F.
    script = _reemplazar(
        script,
        '    // roc: ROC 19a real ponderado (traspaso 2026-08-03, hallazgo L5 — unifica\n'
        '    // con ROC_19A de initMetodo, misma fuente knowledge/roc_19a.yaml asof\n'
        '    // 2026-07-25). Antes eran valores ilustrativos 0.85–0.92 sin relación con\n'
        '    // el dato real; solo cambia la separación entre "Neto ROC 19a" y "Peor\n'
        '    // caso 30%" — las formas siguen siendo sintéticas (shapeOf). CHPY no\n'
        '    // tiene aviso 19(a) en el yaml: se deja su valor ilustrativo (0.88), sin\n'
        '    // dato real que sustituir.\n'
        '    var F = {\n'
        '      NVDY:{ incep:0,  price:0.50,  div:2.86, roc:0.4108, grp:"ym" },\n'
        '      TSLY:{ incep:0,  price:-0.20, div:0.95, roc:0.5459, grp:"ym" },\n'
        '      CONY:{ incep:3,  price:-0.55, div:0.85, roc:0.5307, grp:"ym" },\n'
        '      MSTY:{ incep:9,  price:-0.75, div:0.65, roc:0.7156, grp:"ym" },\n'
        '      CHPY:{ incep:19, price:0.02,  div:0.26, roc:0.88,   grp:"ym" },   // sin 19(a) en el yaml — ilustrativo\n'
        '      SCHB:{ incep:0,  price:0.84,  div:0.02, roc:0,    grp:"growth" },\n'
        '      XLK: { incep:0,  price:1.40,  div:0.01, roc:0,    grp:"growth" },\n'
        '      SMH: { incep:0,  price:3.78,  div:0.00, roc:0,    grp:"growth" }\n'
        '    };\n',
        '    // F ya no fabrica precio/dividendo/ROC ilustrativos (mapa-datos.md § 5):\n'
        '    // incep/grp por ticker salen de DATA, uno por cada clave presente en\n'
        '    // DATA.incep (un ticker que no descargó simplemente no aparece — sin\n'
        '    // ceros ni interpolación, decisión del traspaso 2026-08-10).\n'
        '    var F = {};\n'
        '    Object.keys(DATA.incep).forEach(function(tk){\n'
        '      F[tk] = { incep: DATA.incep[tk], grp: DATA.grp[tk] };\n'
        '    });\n',
        "el bloque F (con su comentario)")

    script = _reemplazar(
        script,
        '    function hash(s){ var h=0; for (var i=0;i<s.length;i++) h=(h*31+s.charCodeAt(i))|0; return (h>>>0)%1000/1000; }\n'
        '    function bump(m,c,w){ var z=(m-c)/w; return Math.exp(-z*z); }\n'
        '    var _shape = {};\n'
        '    function shapeOf(tk){\n'
        '      if (_shape[tk]) return _shape[tk];\n'
        '      var f = F[tk], seed = hash(tk)*6.28, raw = {}, span = LAST - f.incep;\n'
        '      for (var m = f.incep; m <= LAST; m++){\n'
        '        var p = span > 0 ? (m - f.incep)/span : 1;\n'
        '        var beta = f.grp === "ym" ? 1.15 : 0.9;\n'
        '        var wob = 1 + 0.05*Math.sin(m*0.9+seed) + 0.035*Math.sin(m*0.37+seed*1.7)\n'
        '                    - beta*(0.11*bump(m,15,2.6) + 0.07*bump(m,30,2.4));\n'
        '        raw[m] = Math.pow(p, 0.85) * wob;\n'
        '      }\n'
        '      var denom = raw[LAST] || 1, S = {};\n'
        '      for (var mm = f.incep; mm <= LAST; mm++) S[mm] = raw[mm]/denom;\n'
        '      _shape[tk] = S; return S;\n'
        '    }\n'
        '    function targetEnd(tk, mode){\n'
        '      var f = F[tk];\n'
        '      var w = mode === "bruto" ? 0 : mode === "plano" ? RATE : RATE*(1 - f.roc);\n'
        '      return f.price + f.div*(1 - w);\n'
        '    }\n',
        '',
        "el modelo paramétrico (hash/bump/shapeOf/targetEnd)")

    script = _reemplazar(
        script,
        '    function idxAt(tk, m, mode){ return 1 + targetEnd(tk, mode) * shapeOf(tk)[m]; }\n',
        '    function idxAt(tk, m, mode){ return DATA.idx[mode][tk][m]; }\n',
        "idxAt()")

    # Los chips se dibujan desde YM/GROWTH, no desde los datos. Sin filtrar, un ticker
    # que no descargó (yfinance caído para ese símbolo) seguiría teniendo su chip: al
    # pulsarlo, `F[tk]` es undefined y `series()`/`draw()` truenan con TypeError en
    # `F[tk].incep`. El adapter ya lo omite de `DATA.incep` (verificado forzando la
    # rama: con CHPY caído devuelve 7 tickers, no 8), así que aquí solo hay que
    # respetarlo. Se filtra conservando el ORDEN del demo — es el de los chips.
    script = _reemplazar(
        script,
        '    var YM = ["NVDY","TSLY","CONY","MSTY","CHPY"], GROWTH = ["SCHB","XLK","SMH"];\n',
        '    var _presente = function(t){ return Object.prototype.hasOwnProperty.call(DATA.incep, t); };\n'
        '    var YM = ["NVDY","TSLY","CONY","MSTY","CHPY"].filter(_presente),\n'
        '        GROWTH = ["SCHB","XLK","SMH"].filter(_presente);\n',
        "la lista de tickers YM/GROWTH")

    script = _reemplazar(
        script,
        'var state = { base:"NVDY", mode:"bruto", growth:new Set(GROWTH), ym:new Set() };',
        'var state = { base:DATA.base_defecto, mode:"bruto", growth:new Set(GROWTH), ym:new Set() };',
        "el estado inicial (fondo base)")

    script = _reemplazar(
        script,
        '{k:"plano", lab:"Peor caso 30%"}',
        '{k:"plano", lab:"Peor caso " + DATA.tasa_pct + "%"}',
        "la etiqueta del modo «Peor caso»")

    # renderSummaryNotes: la nota «Cifras del demo» solo tenía sentido para el modelo
    # paramétrico. La real declara fuente y fecha de corte (asof) — regla de auditoría
    # del traspaso (feedback_dividend-invariante-roc-nra): toda cifra fiscal declara su
    # base y su momento. Sin la segunda frase, «Neto ROC 19a» y «Peor caso» dan el mismo
    # número para los 3 ETFs de crecimiento (sin avisos 19a en knowledge/roc_19a.yaml,
    # ambos modos retienen la tasa plana) y parece un bug — es el comportamiento
    # correcto de build_drip_comparison_series.
    script = _reemplazar(
        script,
        '        \'<span class="flag">Cifras del demo:</span> el modo <b>DRIP bruto</b> usa '
        'retornos reales medidos con la app; el <b>neto</b> es una estimación ilustrativa — '
        'el cálculo exacto (reinversión compuesta con tu retención real) vive en la app.\'\n',
        '        \'<span class="flag">Cifras reales:</span> precios y dividendos de Yahoo \'\n'
        '        + \'Finance hasta el \' + DATA.asof + \'. El <b>neto ROC 19a</b> aplica la \'\n'
        '        + \'retención solo sobre la porción no-ROC según los avisos 19(a); los ETFs \'\n'
        '        + \'de crecimiento no tienen avisos 19(a) y retienen la tasa plana.\'\n',
        "la nota «Cifras del demo»")

    return script


def extraer(html: str) -> str:
    css = cargar_css(html)
    panel = transformar_panel(cargar_panel_simulacion(html))
    tooltip_helper = cargar_tooltip(html)
    script = transformar_script(cargar_script_comparacion(html))

    return f"""<!-- GENERADO POR tools/extract_comparacion_real.py — NO EDITAR A MANO.
     Fuente: `ui/componentes/comparacion.html` (mismo demo), derivado — no hay diseño
     propio que extraer (`cmp-panel-real` sigue siendo un placeholder «En diseño» en
     el demo). Para cambiar algo, se cambia el demo o este extractor y se regenera. -->
<meta charset="utf-8">
{css}
<style>
  body {{ margin: 0; background: var(--ground); }}
</style>
<main class="wrap" style="padding-top:0">
{panel}
</main>
{TIP_HTML}
<script>
(function () {{
  "use strict";
{tooltip_helper}
{script}
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
