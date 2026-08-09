#!/usr/bin/env python3
"""Extrae el componente «Cash flow» del demo y lo deja listo para inyectarle datos.

Misma regla que `extract_design_system.py` y por el mismo motivo: lo que se puede extraer
del artifact se extrae, no se teclea. Aquí eso vale doble — el waterfall, el mosaico de
100 y la tarjeta de veredicto son ~380 líneas de JS ya escritas y depuradas; reescribirlas
a mano sería introducir bugs a cambio de nada.

Produce `ui/componentes/cashflow.html`, con dos huecos que rellena Python en cada rerun:

    {{DATA_JSON}}   las 12 constantes, desde `ui.adapters.cashflow_data`
    {{PASO}}        el paso activo del rail, que vive en `st.session_state`

El rail del demo NO se extrae: en el port es de botones nativos de Streamlit, porque
`components.html` no puede devolver interacciones a Python (ver traspaso § Arquitectura).

    python3 tools/extract_cashflow.py [--check]
"""
import argparse
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(BASE, "ui", "componentes", "cashflow.html")

DEFAULT_DEMO = os.path.expanduser(
    "~/Desktop/Habilidades de agentes/Obsidian/APPs/Dividend-Analyzer/demos/"
    "viaje-dinero-waterfall.html"
)

# Las 12 constantes que el demo declara en duro y que el port sustituye por datos reales.
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
    # 1 · Hoja de estilo completa. Va entera a propósito: el componente vive en un iframe,
    #     así que no hay conflicto con Streamlit, y recortar reglas es la vía rápida a que
    #     se caiga un detalle del waterfall sin que nadie lo note.
    #
    #     OJO: no vale buscar el primer `<style>`. La línea 1 del demo trae el runtime del
    #     artifact con su propio bloque diminuto (`:root{color-scheme:light}body{margin:0}`),
    #     y quedarse con ese deja el componente SIN layout ni color — con el DOM entero
    #     construido, así que inspeccionarlo no delata el fallo; solo se ve al abrirlo.
    #     Se ancla al bloque que declara los tokens, que es el del diseño por definición.
    css = ""
    for m in re.finditer(r"<style>.*?</style>", html, re.S):
        if "--ground:" in m.group(0):
            css = m.group(0)
            break
    if not css:
        sys.exit("No encontré el bloque de estilos del diseño (el que declara --ground).")

    # 2 · El panel del recorrido, delimitado por su propio comentario de cierre.
    panel = _entre(html, '<div class="panel" id="panel-viaje"',
                   "</div><!-- /panel-viaje -->", "el panel del Cash flow")

    # 3 · Tooltip flotante: vive fuera del panel pero lo usan sus barras.
    tip = '<div id="tip" role="status"></div>'

    # 4 · El módulo JS del recorrido: desde el arranque del IIFE hasta el primer render.
    #     Ahí termina el Cash flow y empieza la navegación, que en el port es nativa.
    script = _entre(html, '  "use strict";', "  render(pasoActual);",
                    "el módulo JS del Cash flow")

    # Las constantes en duro se sustituyen por el JSON que inyecta el adapter. Se localiza
    # el bloque por su primera y su última variable, no por número de línea.
    patron = re.compile(r"var POCKET = .*?PICO = [\d.]+;", re.S)
    if not patron.search(script):
        sys.exit("No encontré el bloque de constantes del demo — ¿cambió su formato?")
    script = patron.sub(
        "var D = {{DATA_JSON}};\n"
        "  " + ", ".join(f"{c} = D.{c}" for c in CONSTANTES).join(("var ", ";")),
        script, count=1)

    # El demo arranca en el paso final; en el port el paso lo manda Streamlit.
    script = re.sub(r"var pasoActual = \d+;", "var pasoActual = {{PASO}};", script)

    return f"""<!-- GENERADO POR tools/extract_cashflow.py — NO EDITAR A MANO.
     Fuente: el demo del artifact. Para cambiar algo, se cambia el demo y se regenera. -->
<meta charset="utf-8">
{css}
<style>
  /* El componente vive dentro de un iframe con su propio fondo: sin esto se ve un
     rectángulo blanco recortado sobre la superficie de la página. */
  body {{ margin: 0; background: var(--ground); }}
  .rail {{ display: none; }}  /* el rail es nativo en el port, no del componente */
</style>
<main class="wrap" style="padding-top:0">
{panel}
</main>
{tip}
<script>
(function () {{
  "use strict";
{script}
  render(pasoActual);
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
    faltan = [h for h in ("{{DATA_JSON}}", "{{PASO}}") if h not in contenido]
    if faltan:
        sys.exit(f"El componente salió sin los huecos {faltan} — revisa el extractor.")
    print(f"generado: {rel}  ({len(contenido):,} caracteres, huecos DATA_JSON y PASO)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
