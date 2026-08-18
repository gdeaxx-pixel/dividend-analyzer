#!/usr/bin/env python3
"""Extrae «Metodología» (11 entradas + formulario + bibliografía) del demo.

Contenido educativo, sin datos dinámicos — se porta como HTML estático completo
(mapa-datos.md § 7, NO TOCAR). Incluye `buildMethIndex()`, el único script de esta
vista: solo arma botones que hacen scroll dentro del propio documento, autocontenido y
sin datos de Python.

El botón «← Volver al análisis» del demo (`methBack`) SÍ se extrae como marcado, pero su
manejador (`backFromMetodologia`) no: depende de la navegación por estado del demo
(`crumb`/`etfView`/…), que el port no tiene — ahí decide `st.session_state` nativo, no
JS. Se quita la línea del botón; `ui/vistas.py` pone un `st.button` nativo equivalente
antes del componente (misma regla del traspaso: todo lo que cambia estado es widget
nativo).

Produce `ui/componentes/metodologia.html`. Sin huecos: no recibe nada de Python.

    python3 tools/extract_metodologia.py [--check]
"""
import argparse
import os
import re
import sys

from _auto_alto import AUTO_ALTO_JS

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(BASE, "ui", "componentes", "metodologia.html")

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

    # 2 · El panel completo, sin el botón «Volver» (lo reemplaza un widget nativo).
    i = html.find('<div id="view-metodologia" hidden>')
    j = html.find('\n\n  <footer class="foot">', i)
    if i < 0 or j < 0:
        sys.exit("No pude aislar `view-metodologia` en el demo — ¿cambió su estructura?")
    panel = html[i:j].rstrip()
    boton = '<button class="meth-back" id="methBack">← Volver al análisis</button>\n    '
    if boton not in panel:
        sys.exit("No encontré el botón «Volver» a quitar — ¿cambió su marcado?")
    panel = panel.replace(boton, "", 1)

    # `hidden` en el envoltorio: en el demo `view-metodologia` es una vista de nivel
    # superior que `showCat()` desoculta al seleccionarla (mismo patrón que
    # `view-metodo` en `extract_metodo.py` y `panel-hoja` en `extract_hoja.py`). Sin
    # `showCat` en el port, hay que quitarlo en la extracción o el iframe queda negro.
    apertura_view = '<div id="view-metodologia" hidden>'
    if apertura_view not in panel:
        sys.exit("No encontré `hidden` en `view-metodologia` — ¿cambió el demo?")
    panel = panel.replace(apertura_view, '<div id="view-metodologia">', 1)

    # 3 · `buildMethIndex`: arma los botones de salto del índice. Autocontenido — no
    #     depende de ningún estado del demo, así que se porta verbatim.
    ini = html.find("(function buildMethIndex() {")
    fin = html.find("\n  })();\n\n  // ================= COMPARACIÓN", ini)
    if ini < 0 or fin < 0:
        sys.exit("No pude aislar `buildMethIndex` en el demo — ¿cambió su estructura?")
    script = html[ini:fin] + "\n  })();"

    return f"""<!-- Derivado del demo del artifact en su ORIGEN, y mantenido a mano desde entonces.
     Las fases 3.3a/3.3b cablearon este componente a datos reales ({{{{DATA_JSON}}}}) y ahí
     murió el contrato: el demo YA NO es su fuente. `tools/extract_metodologia.py` quedó como
     referencia histórica y ya no escribe — regenerarlo borraría el cableado.
     Lo que SÍ se sigue generando del demo es la taxonomía y los tokens, con
     `tools/extract_design_system.py`. Ese contrato está vivo y su `--check` pasa. -->
<meta charset="utf-8">
{css}
<style>
  body {{ margin: 0; background: var(--ground); }}
</style>
<main class="wrap" style="padding-top:0">
{panel}
</main>
<script>
(function () {{
  "use strict";
{script}
}})();
</script>
{AUTO_ALTO_JS}
"""


_DESARMADO = """Este extractor ya NO escribe (desarmado el 2026-08-18).

Nació con un contrato real: el demo del artifact era la fuente y este script regeneraba
`ui/componentes/metodologia.html`. Ese contrato murió cuando las fases 3.3a/3.3b cablearon el componente a datos
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
