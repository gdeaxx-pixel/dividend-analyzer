#!/usr/bin/env python3
"""Extrae el componente «Hoja Excel» del demo y lo deja listo para inyectarle datos.

Misma regla que `extract_cashflow.py`: lo que se puede extraer del artifact se extrae,
no se teclea. `initHoja()` son ~200 líneas de JS ya escritas y depuradas (las dos
lecturas de la posición, las cintas de ecuación, el interruptor «Corregir la hoja»).

Produce `ui/componentes/hoja.html`, con tres huecos que rellena Python en cada rerun:

    {{DATA_JSON}}   las 12 constantes del Cash flow + INICIO/TICKER, desde
                     `ui.adapters.hoja_data`
    {{HONEST}}       "true"/"false" — si el interruptor «Corregir la hoja» arranca
                      encendido; en el port lo maneja el propio JS del componente
                      (no hay control nativo para esto: es un estado puramente visual)

    python3 tools/extract_hoja.py [--check]
"""
import argparse
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(BASE, "ui", "componentes", "hoja.html")

DEFAULT_DEMO = os.path.expanduser(
    "~/Desktop/Habilidades de agentes/Obsidian/APPs/Dividend-Analyzer/demos/"
    "viaje-dinero-waterfall.html"
)

# Las 12 constantes del Cash flow (mismo bloque que usa Hoja Excel) más las dos que
# introduce initHoja: fecha de la primera compra y ticker.
CONSTANTES = ("POCKET", "BRUTO", "IMPUESTO", "NETO", "DRIP", "CASH", "TOTAL_TRABAJANDO",
              "MERCADO", "VALOR_HOY", "CAPITAL_ACTUAL", "RESULTADO", "PICO")


def load_demo() -> str:
    path = os.environ.get("DIVIDEND_DEMO_HTML", DEFAULT_DEMO)
    if not os.path.exists(path):
        sys.exit(f"No encuentro el demo en {path}\n"
                 "Indica su ruta con DIVIDEND_DEMO_HTML=/ruta/al/demo.html")
    with open(path, encoding="utf-8") as f:
        return f.read()


def _entre(html: str, inicio: str, fin: str, que: str) -> str:
    i = html.find(inicio)
    j = html.find(fin, i + len(inicio)) if i >= 0 else -1
    if i < 0 or j < 0:
        sys.exit(f"No pude aislar {que} en el demo — ¿cambió su estructura?")
    return html[i:j + len(fin)]


def extraer(html: str) -> str:
    # 1 · Hoja de estilo completa — mismo bloque que usa Cash flow (--ground) y el
    #     mismo motivo para no tomar el primer <style>: ver extract_cashflow.py.
    css = ""
    for m in re.finditer(r"<style>.*?</style>", html, re.S):
        if "--ground:" in m.group(0):
            css = m.group(0)
            break
    if not css:
        sys.exit("No encontré el bloque de estilos del diseño (el que declara --ground).")

    # 2 · El panel de la Hoja Excel: de su apertura al `</div>` que lo cierra, justo
    #     antes de que el demo cierre el envoltorio `etf-view` (comentario propio, no
    #     hay `<!-- /panel-hoja -->` como en Cash flow).
    apertura = '<div class="panel" id="panel-hoja"'
    i = html.find(apertura)
    if i < 0:
        sys.exit("No pude localizar el panel de Hoja Excel en el demo.")
    fin_envoltorio = html.find("</div><!-- /etf-view -->", i)
    if fin_envoltorio < 0:
        sys.exit("No pude localizar el cierre de `etf-view` tras el panel de Hoja Excel.")
    panel = html[i:fin_envoltorio].rstrip()

    # 3 · El tooltip flotante. `initHoja` LLAMA a `showTip`/`hideTip` (los `data-tip` de
    #     sus encabezados), pero esas funciones NO están definidas dentro de su propio
    #     IIFE — viven arriba, en el `<script>` grande que las comparte con Cash flow,
    #     Comparación y el resto. Sin este bloque el componente compila pero truena en
    #     el navegador (`ReferenceError: showTip is not defined`) al primer hover — el
    #     mismo modo de fallo que el traspaso pide cazar con la consola, no a ojo.
    tip = '<div id="tip" role="status"></div>'
    ti = html.find("  // ---------- tooltip ----------")
    tj = html.find("  // ---------- verdict card (portada) ----------", ti)
    if ti < 0 or tj < 0:
        sys.exit("No pude aislar el helper compartido de tooltip (showTip/hideTip/tipHtml).")
    tooltip_helper = html[ti:tj].rstrip()

    # 4 · El módulo JS de `initHoja`.
    script = _entre(html, "(function initHoja() {", "\n\n  })();",
                    "el módulo JS de Hoja Excel")

    # Las constantes en duro se sustituyen por el JSON que inyecta el adapter — el
    # mismo patrón que `extract_cashflow.py`. INICIO/TICKER también salen del JSON:
    # en el demo son literales; en el port dependen del CSV cargado.
    patron_constantes = re.compile(r"var TOTALINV = POCKET \+ NETO;\n"
                                   r'    var INICIO = "[^"]*", TICKER = "[^"]*";', re.S)
    if not patron_constantes.search(script):
        sys.exit("No encontré el bloque INICIO/TICKER del demo — ¿cambió su formato?")
    script = patron_constantes.sub(
        "var D = {{DATA_JSON}};\n"
        "    " + ", ".join(f"{c} = D.{c}" for c in CONSTANTES).join(("var ", ";")) + "\n"
        "    var INICIO = D.INICIO, TICKER = D.TICKER;\n"
        "    var TOTALINV = POCKET + NETO;",
        script, count=1)

    return f"""<!-- GENERADO POR tools/extract_hoja.py — NO EDITAR A MANO.
     Fuente: el demo del artifact. Para cambiar algo, se cambia el demo y se regenera. -->
<meta charset="utf-8">
{css}
<style>
  body {{ margin: 0; background: var(--ground); }}
</style>
<main class="wrap" style="padding-top:0">
{panel}
</main>
{tip}
<script>
(function () {{
  "use strict";
{tooltip_helper}
{script}
}})();
</script>
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
