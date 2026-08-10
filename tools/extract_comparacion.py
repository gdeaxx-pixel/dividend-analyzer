#!/usr/bin/env python3
"""Extrae el componente «Comparación · Simulación» (Total Return Graph) del demo.

Misma regla que los demás extractores: lo que se puede extraer del artifact se extrae,
no se teclea. `initComparacion()` (~225 líneas) es un modelo paramétrico que NO se
conecta al CSV — se porta **tal cual**, cifras incluidas (mapa-datos.md § 4: «es un
modelo paramétrico etiquetado como simulación»). Por eso este componente no tiene
adapter ni hueco `{{DATA_JSON}}`: no recibe nada de Python.

Las piezas (`cargar_css`, `cargar_tooltip`, `cargar_panel_simulacion`,
`cargar_script_comparacion`) son funciones reusables a propósito: `tools/
extract_comparacion_real.py` las importa para no duplicar este archivo (mismo CSS,
mismo tooltip, mismo panel base) y solo aplica sus propias sustituciones sobre el JS
que devuelve `cargar_script_comparacion`.

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

TIP_HTML = '<div id="tip" role="status"></div>'

MARCADOR_INICIO_SCRIPT = "(function initComparacion() {"
# H3 (traspaso 2026-08-10): el cierre real de este IIFE NO tiene línea en blanco antes
# de `})();` (a diferencia de otros módulos del demo), así que buscar el delimitador
# "\n\n  })();" salta ese cierre y engancha el de `initHoja`, ~200 líneas más abajo (ese
# sí tiene blanco antes) — arrastrando `initHoja` completo, sin sus constantes
# (`ReferenceError: POCKET is not defined`, dos veces por carga, una por cada
# ocurrencia — ver comparacion.html:1492 antes de este fix). El corte correcto es el
# comentario que abre la sección siguiente.
MARCADOR_FIN_HOJA = "  // ================= HOJA EXCEL · una matriz, dos lecturas ================="

# H2 (traspaso 2026-08-10): el observer de tema comprobaba `#view-comparacion`
# (envoltorio de nivel superior del DEMO, con sus pestañas) antes de redibujar. El
# extractor solo se lleva el panel de Simulación — ese id no existe en el componente —
# así que la comprobación siempre lanzaba `TypeError: Cannot read properties of null
# (reading 'hidden')` al cambiar de tema, y el SVG (cuyos colores dependen de los
# tokens) nunca se redibujaba. El observer sigue teniendo sentido — lo que sobra es el
# guard a un elemento que no existe.
LINEA_OBSERVER_VIEJA = ('    var _mo = new MutationObserver(function(){ '
                        'if (!document.getElementById("view-comparacion").hidden) draw(); });\n')
LINEA_OBSERVER_NUEVA = '    var _mo = new MutationObserver(function(){ draw(); });\n'


def load_demo() -> str:
    path = os.environ.get("DIVIDEND_DEMO_HTML", DEFAULT_DEMO)
    if not os.path.exists(path):
        sys.exit(f"No encuentro el demo en {path}\n"
                 "Indica su ruta con DIVIDEND_DEMO_HTML=/ruta/al/demo.html")
    with open(path, encoding="utf-8") as f:
        return f.read()


def cargar_css(html: str) -> str:
    """Hoja de estilo completa — mismo bloque y mismo motivo que en los demás
    extractores: ver extract_cashflow.py."""
    for m in re.finditer(r"<style>.*?</style>", html, re.S):
        if "--ground:" in m.group(0):
            return m.group(0)
    sys.exit("No encontré el bloque de estilos del diseño (el que declara --ground).")


def cargar_tooltip(html: str) -> str:
    """Tooltip flotante compartido: `initComparacion` llama a `showTip`/`hideTip` (el
    hover sobre la gráfica) pero no las define — viven arriba, en el `<script>` grande
    que comparten Cash flow, Hoja Excel y esta vista. Sin esto el componente compila
    pero truena en el navegador al primer hover."""
    ti = html.find("  // ---------- tooltip ----------")
    tj = html.find("  // ---------- verdict card (portada) ----------", ti)
    if ti < 0 or tj < 0:
        sys.exit("No pude aislar el helper compartido de tooltip (showTip/hideTip/tipHtml).")
    return html[ti:tj].rstrip()


def cargar_panel_simulacion(html: str) -> str:
    """Solo el panel de Simulación — «Real» (`cmp-panel-real`) sigue sin diseño en el
    demo (placeholder «En diseño») y se construye aparte, sobre datos reales
    (`tools/extract_comparacion_real.py`)."""
    apertura = '<div class="panel" id="cmp-panel-simulacion"'
    i = html.find(apertura)
    if i < 0:
        sys.exit("No pude localizar el panel de Comparación · Simulación en el demo.")
    fin = html.find('<div class="panel" id="cmp-panel-real"', i)
    if fin < 0:
        sys.exit("No pude localizar el cierre del panel de Simulación (antes de «Real»).")
    return html[i:fin].rstrip()


def cargar_script_comparacion(html: str) -> str:
    """El módulo JS de `initComparacion`, con los parches H2 y H3 aplicados (arriba).
    Se porta tal cual — sin sustituir ninguna constante — para Simulación;
    `extract_comparacion_real.py` parte de este mismo texto y le aplica sus propias
    sustituciones para leer `{{DATA_JSON}}` en vez del modelo paramétrico."""
    i = html.find(MARCADOR_INICIO_SCRIPT)
    if i < 0:
        sys.exit("No pude localizar el inicio de initComparacion() en el demo.")
    j = html.find(MARCADOR_FIN_HOJA, i)
    if j < 0:
        sys.exit("No encontré el marcador de cierre de initComparacion (el comentario "
                 "que abre HOJA EXCEL) — ¿cambió el demo? Revisa si el corte sigue siendo válido.")
    script = html[i:j].rstrip()

    if LINEA_OBSERVER_VIEJA not in script:
        sys.exit("No encontré la línea del MutationObserver de tema — ¿cambió el demo? "
                 "Revisa si el parche H2 sigue haciendo falta.")
    script = script.replace(LINEA_OBSERVER_VIEJA, LINEA_OBSERVER_NUEVA, 1)

    return script


def extraer(html: str) -> str:
    css = cargar_css(html)
    panel = cargar_panel_simulacion(html)
    tooltip_helper = cargar_tooltip(html)
    script = cargar_script_comparacion(html)

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
    print(f"generado: {rel}  ({len(contenido):,} caracteres, sin datos de Python)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
