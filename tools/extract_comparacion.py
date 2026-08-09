#!/usr/bin/env python3
"""Extrae el componente «Comparación · Simulación» (Total Return Graph) del demo.

Misma regla que los demás extractores: lo que se puede extraer del artifact se extrae,
no se teclea. `initComparacion()` (~225 líneas) es un modelo paramétrico que NO se
conecta al CSV — se porta **tal cual**, cifras incluidas (mapa-datos.md § 4: «es un
modelo paramétrico etiquetado como simulación»). Por eso este componente no tiene
adapter ni hueco `{{DATA_JSON}}`: no recibe nada de Python.

Produce `ui/componentes/comparacion.html`.

    python3 tools/extract_comparacion.py [--check]
"""
import argparse
import os
import re
import sys

from _auto_alto import AUTO_ALTO_JS

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(BASE, "ui", "componentes", "comparacion.html")

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


def _entre(html: str, inicio: str, fin: str, que: str) -> str:
    i = html.find(inicio)
    j = html.find(fin, i + len(inicio)) if i >= 0 else -1
    if i < 0 or j < 0:
        sys.exit(f"No pude aislar {que} en el demo — ¿cambió su estructura?")
    return html[i:j + len(fin)]


def extraer(html: str) -> str:
    # 1 · Hoja de estilo completa — mismo bloque y mismo motivo que en los demás
    #     extractores: ver extract_cashflow.py.
    css = ""
    for m in re.finditer(r"<style>.*?</style>", html, re.S):
        if "--ground:" in m.group(0):
            css = m.group(0)
            break
    if not css:
        sys.exit("No encontré el bloque de estilos del diseño (el que declara --ground).")

    # 2 · Solo el panel de Simulación — «Real» (`cmp-panel-real`) sigue sin diseño en el
    #     demo (placeholder «En diseño») y se construye aparte, sobre datos reales.
    apertura = '<div class="panel" id="cmp-panel-simulacion"'
    i = html.find(apertura)
    if i < 0:
        sys.exit("No pude localizar el panel de Comparación · Simulación en el demo.")
    fin = html.find('<div class="panel" id="cmp-panel-real"', i)
    if fin < 0:
        sys.exit("No pude localizar el cierre del panel de Simulación (antes de «Real»).")
    panel = html[i:fin].rstrip()

    # 3 · Tooltip flotante compartido: `initComparacion` llama a `showTip`/`hideTip` (el
    #     hover sobre la gráfica) pero no las define — viven arriba, en el `<script>`
    #     grande que comparten Cash flow, Hoja Excel y esta vista. Sin esto el componente
    #     compila pero truena en el navegador al primer hover.
    tip = '<div id="tip" role="status"></div>'
    ti = html.find("  // ---------- tooltip ----------")
    tj = html.find("  // ---------- verdict card (portada) ----------", ti)
    if ti < 0 or tj < 0:
        sys.exit("No pude aislar el helper compartido de tooltip (showTip/hideTip/tipHtml).")
    tooltip_helper = html[ti:tj].rstrip()

    # 4 · El módulo JS de `initComparacion`, tal cual — sin sustituir ninguna constante.
    script = _entre(html, "(function initComparacion() {", "\n\n  })();",
                    "el módulo JS de Comparación · Simulación")

    # `ajustarHoja = igualarCintas;` escribe una variable global (`var ajustarHoja`)
    # que en el demo vive en el `<script>` grande y que `showTab` llama al abrir la
    # pestaña «hoja». Aquí no hay pestañas que abrir — `igualarCintas()` ya corre
    # sola al cargar y en cada resize — así que es una asignación a un global
    # inexistente. Con `"use strict"` eso es un `ReferenceError` que tumba todo el
    # script (`ReferenceError: ajustarHoja is not defined`, iframe en negro).
    linea_ajustar = "    ajustarHoja = igualarCintas;      // showTab lo llama al abrir la sección\n"
    if linea_ajustar not in script:
        sys.exit("No encontré la línea de ajustarHoja — ¿cambió el demo? Revisa si sigue haciendo falta este parche.")
    script = script.replace(linea_ajustar, "", 1)

    return f"""<!-- GENERADO POR tools/extract_comparacion.py — NO EDITAR A MANO.
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
    print(f"generado: {rel}  ({len(contenido):,} caracteres, sin datos de Python)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
