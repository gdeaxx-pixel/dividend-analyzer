#!/usr/bin/env python3
"""Extrae «Método tradicional» (5 sub-vistas + sus ~20 modales) del demo.

Misma regla que los demás extractores. `initMetodo()` (~780 líneas) audita una cartera
AJENA — no la del usuario — así que **no se conecta al CSV** y se porta tal cual, cifras
incluidas (mapa-datos.md § 6, NO TOCAR). Por eso este componente tampoco tiene adapter:
no recibe nada de Python salvo qué sub-vista mostrar.

Las 5 sub-vistas (`met-panel-matriz/rendimiento/payback/tasa/otras`) viven TODAS en un
solo componente, porque `initMetodo()` las llena de una sola pasada al cargar — nunca
recalcula al cambiar de tab (`showMetTab` en el demo solo alterna `hidden`). El port
replica exactamente eso: el componente dibuja las 5, y un script final oculta las que no
tocan según `{{VISTA_ACTIVA}}` (una de `matriz`, `rendimiento`, `payback`, `tasa`, `otras`).

Los 20 modales viven fuera de `view-metodo` en el DOM del demo (son diálogos flotantes,
su posición no importa) pero SOLO los abre/cierra `initMetodo()` — se extraen junto con
él, no junto a Hoja Excel ni Cash flow.

Produce `ui/componentes/metodo.html`, con un hueco: {{VISTA_ACTIVA}}.

    python3 tools/extract_metodo.py [--check]
"""
import argparse
import os
import re
import sys

from _auto_alto import AUTO_ALTO_JS

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(BASE, "ui", "componentes", "metodo.html")

DEFAULT_DEMO = os.path.expanduser(
    "~/Desktop/Habilidades de agentes/Obsidian/APPs/Dividend-Analyzer/demos/"
    "viaje-dinero-waterfall.html"
)

MET_ORDER = ("matriz", "rendimiento", "payback", "tasa", "otras")


def load_demo() -> str:
    path = os.environ.get("DIVIDEND_DEMO_HTML", DEFAULT_DEMO)
    if not os.path.exists(path):
        sys.exit(f"No encuentro el demo en {path}\n"
                 "Indica su ruta con DIVIDEND_DEMO_HTML=/ruta/al/demo.html")
    with open(path, encoding="utf-8") as f:
        return f.read()


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

    # 2 · Las 5 sub-vistas.
    i = html.find('<div id="view-metodo" hidden>')
    j = html.find("\n\n  <!-- ============ VISTA: CÓMO FUNCIONA", i)
    if i < 0 or j < 0:
        sys.exit("No pude aislar `view-metodo` en el demo — ¿cambió su estructura?")
    panel = html[i:j].rstrip()

    # El envoltorio `view-metodo` trae `hidden` porque en el demo es una vista de nivel
    # superior que `showCat()` desoculta al seleccionarla (mismo mecanismo, un nivel más
    # arriba, que el `hidden` de `panel-hoja` en `extract_hoja.py`). Aquí no hay
    # `showCat` — el componente completo es la única vista del iframe.
    apertura_view = '<div id="view-metodo" hidden>'
    if apertura_view not in panel:
        sys.exit("No encontré `hidden` en `view-metodo` — ¿cambió el demo?")
    panel = panel.replace(apertura_view, '<div id="view-metodo">', 1)

    # 3 · Los 20 modales — viven después de Metodología en el DOM, no dentro de
    #     `view-metodo`, pero son de esta vista (ver docstring).
    mi = html.find("<!-- ============ MODAL: Valor real hoy")
    mj = html.find("\n<script>", mi)
    if mi < 0 or mj < 0:
        sys.exit("No pude aislar el bloque de modales de Método tradicional.")
    modales = html[mi:mj].rstrip()
    n_modales = modales.count('role="dialog"')
    if n_modales != 20:
        sys.exit(f"Se esperaban 20 modales y se extrajeron {n_modales} — revisa los marcadores.")

    # 4 · El módulo JS de `initMetodo`, tal cual — sin sustituir ninguna constante (las
    #     cifras de la cartera de la clase son intencionalmente ajenas al CSV del
    #     usuario). Termina justo antes de `showCat(...)`, que es navegación del demo
    #     que el port no usa (Streamlit ya decide qué vista mostrar).
    ini = html.find("(function initMetodo() {")
    fin = html.find('\n\n  showCat("dividendos");', ini)
    if ini < 0 or fin < 0:
        sys.exit("No pude aislar el módulo JS de Método tradicional.")
    script = html[ini:fin].rstrip()

    # `ajustarMetodoNra` es una variable global (`var ajustarMetodoNra = null;`) que en
    # el demo vive en el `<script>` grande, para que `showMetTab` la llame al abrir la
    # sub-vista "matriz". Acá no hay `showMetTab`, pero el propio módulo SÍ la lee en su
    # listener de `resize` (unas líneas más abajo, en el mismo IIFE) — a diferencia de
    # `ajustarHoja` en Hoja Excel, esta no es código muerto: solo le falta la
    # declaración `var` que en el demo pone el script compartido. Sin ella, con
    # `"use strict"`, la asignación revienta (`ReferenceError: ajustarMetodoNra is not
    # defined`) y tumba todo el script antes de llegar al control de sub-vista de abajo
    # — iframe en negro.
    script = "  var ajustarMetodoNra;\n" + script

    # Control de sub-vista: el port no tiene `showMetTab` (era parte de la navegación
    # del demo). Un script mínimo, propio del port, oculta las 4 sub-vistas que no
    # tocan — initMetodo ya llenó las 5 de una pasada, así que basta con `hidden`.
    #
    # `showMetTab("matriz")` en el demo también llama a `ajustarMetodoNra()` cada vez
    # que se entra a esa sub-vista — reserva el alto máximo entre los 3 modos fiscales
    # (bruto/ROC/plano) para que cambiar de modo no mueva el layout. Sin esto, el alto
    # solo se corrige si por casualidad se dispara un `resize` (el único otro sitio que
    # la llama), así que el `scrollHeight` medido en el navegador es indeterminado:
    # ~1670px sin ajustar, ~2540px ajustado — se midió el número equivocado más de una
    # vez antes de encontrar esto.
    control_vista = (
        "  var VISTA_ACTIVA = " + '"{{VISTA_ACTIVA}}";\n'
        "  " + repr(list(MET_ORDER)).replace("'", '"') + ".forEach(function (n) {\n"
        '    var el = document.getElementById("met-panel-" + n);\n'
        "    if (el) el.hidden = (n !== VISTA_ACTIVA);\n"
        "  });\n"
        '  if (VISTA_ACTIVA === "matriz" && ajustarMetodoNra) ajustarMetodoNra();'
    )

    return f"""<!-- GENERADO POR tools/extract_metodo.py — NO EDITAR A MANO.
     Fuente: el demo del artifact. Para cambiar algo, se cambia el demo y se regenera. -->
<meta charset="utf-8">
{css}
<style>
  body {{ margin: 0; background: var(--ground); }}
</style>
<main class="wrap" style="padding-top:0">
{panel}
</main>
{modales}
<script>
(function () {{
  "use strict";
{script}
{control_vista}
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
    if "{{VISTA_ACTIVA}}" not in contenido:
        sys.exit("El componente salió sin el hueco {{VISTA_ACTIVA}} — revisa el extractor.")
    print(f"generado: {rel}  ({len(contenido):,} caracteres, hueco VISTA_ACTIVA, 20 modales)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
