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

from _auto_alto import AUTO_ALTO_JS

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

    # Tras el corte de producción el `app.py` viejo es `app_old.py`. El demo conserva el
    # nombre antiguo (es fuente del artifact y no se toca), así que la referencia se
    # corrige aquí: sin esto, regenerar revierte el fix del PR #2 en silencio.
    script = script.replace("_build_clusters (app.py)", "_build_clusters (app_old.py)")

    return f"""<!-- Derivado del demo del artifact en su ORIGEN, y mantenido a mano desde entonces.
     Las fases 3.3a/3.3b cablearon este componente a datos reales ({{{{DATA_JSON}}}}) y ahí
     murió el contrato: el demo YA NO es su fuente. `tools/extract_cashflow.py` quedó como
     referencia histórica y ya no escribe — regenerarlo borraría el cableado.
     Lo que SÍ se sigue generando del demo es la taxonomía y los tokens, con
     `tools/extract_design_system.py`. Ese contrato está vivo y su `--check` pasa. -->
<meta charset="utf-8">
{css}
<style>
  /* El componente vive dentro de un iframe con su propio fondo: sin esto se ve un
     rectángulo blanco recortado sobre la superficie de la página. */
  body {{ margin: 0; background: var(--ground); }}
  .rail {{ display: none; }}  /* el rail es nativo en el port, no del componente */

  /* El chasis de 940px se aplica DOS veces en el port: `.block-container` (ui/chrome.py)
     deja el iframe en 860px, y dentro el `.wrap` vuelve a poner su padding lateral
     (clamp = 34.4px por lado) → 791px útiles contra los 820 del `min-width` de `.fall`.
     De ahí los 29px de scroll horizontal, iguales a 1280 y a 1440 porque el chasis está
     topado. Aquí la cascada sangra hasta los bordes del iframe (ese padding ya lo puso
     `.block-container`) y suelta el piso de 820, que era arbitrario: el min-content real
     es 503px. El media query mide el viewport del IFRAME (860 en escritorio, 706 en iPad
     vertical, 337 a 375px), así que el deslizamiento horizontal aprobado en móvil queda
     intacto por debajo de 760. */
  @media (min-width: 760px) {{
    .fall-scroll {{
      margin-left: calc(-1 * clamp(16px, 4vw, 40px));   /* espeja el padding del `.wrap` */
      margin-right: calc(-1 * clamp(16px, 4vw, 40px));
    }}
    .fall {{ min-width: 0; }}
  }}
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
{AUTO_ALTO_JS}
"""


_DESARMADO = """Este extractor ya NO escribe (desarmado el 2026-08-18).

Nació con un contrato real: el demo del artifact era la fuente y este script regeneraba
`ui/componentes/cashflow.html`. Ese contrato murió cuando las fases 3.3a/3.3b cablearon el componente a datos
vivos ({{DATA_JSON}}): desde entonces todo lo que se le añadió —guards, ramas honestas,
textos derivados de cifras medidas— se escribió a mano en el componente, no en el demo.

Regenerar hoy no actualizaría nada: borraría ese cableado y devolvería cifras congeladas a
la pantalla, que es justo el bug que este repo lleva meses cerrando. Por eso el comando
sale con error en vez de escribir.

Tampoco se conserva `--check`: con el componente mantenido a mano, la comparación contra el
demo solo puede responder DESACTUALIZADO, siempre y por diseño. Un termómetro clavado en
fiebre no mide nada.

Lo que SÍ sigue vivo es `tools/extract_design_system.py` — taxonomía (`ui/nav.py`) y tokens
(`ui/tokens.py`) se siguen generando del demo, y su `--check` pasa.

Este archivo se conserva como referencia histórica de cómo se derivó el componente."""


def main() -> int:
    ap = argparse.ArgumentParser(description=_DESARMADO)
    ap.add_argument("--check", action="store_true",
                    help="(retirado) ver la explicación al ejecutar sin argumentos")
    ap.parse_args()
    print(_DESARMADO)
    return 2


if __name__ == "__main__":
    sys.exit(main())
