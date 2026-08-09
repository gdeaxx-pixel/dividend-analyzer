#!/usr/bin/env python3
"""Extrae el sistema de diseño y la taxonomía del demo, y genera `ui/tokens.py` y `ui/nav.py`.

Existe porque las dos primeras entregas de la Fase 1 fallaron igual: al pedir que se
TRANSCRIBIERAN los tokens y la taxonomía, se reinterpretaron (paleta de `app.py` en vez de
la del artifact, categorías inventadas). Extraer elimina el modo de fallo: lo generado es
idéntico a la fuente por construcción, y cualquier divergencia futura se detecta corriendo
esto de nuevo.

    python3 tools/extract_design_system.py [--check]

`--check` no escribe: falla con exit 1 si los archivos generados ya no coinciden con el
demo. Sirve como gate de auditoría.

Fuente: el demo del artifact. No vive en este worktree (pesa 263 KB y contiene cifras
reales); se toma del vault, o de la ruta que indique DIVIDEND_DEMO_HTML.
"""
import argparse
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_DEMO = os.path.expanduser(
    "~/Desktop/Habilidades de agentes/Obsidian/APPs/Dividend-Analyzer/demos/"
    "viaje-dinero-waterfall.html"
)


def load_demo() -> str:
    path = os.environ.get("DIVIDEND_DEMO_HTML", DEFAULT_DEMO)
    if not os.path.exists(path):
        sys.exit(f"No encuentro el demo en {path}\n"
                 f"Indica su ruta con DIVIDEND_DEMO_HTML=/ruta/al/demo.html")
    with open(path, encoding="utf-8") as f:
        return f.read()


# ── Extracción ────────────────────────────────────────────────────────────────

def _vars(block: str) -> dict:
    """Pares `--nombre: valor;` de un bloque CSS, en orden de aparición."""
    return dict(re.findall(r"--([a-z0-9-]+):\s*([^;]+);", block))


def extract_tokens(html: str) -> tuple:
    """Devuelve (fuentes, colores_claro, colores_oscuro) del :root del demo."""
    root = re.search(r"\n  :root \{(.*?)\n  \}", html, re.S)
    dark = re.search(r':root\[data-theme="dark"\] \{(.*?)\}', html, re.S)
    if not root or not dark:
        sys.exit("No pude localizar los bloques :root del demo — ¿cambió su estructura?")

    all_light = _vars(root.group(1))
    fonts = {k: v for k, v in all_light.items() if k.startswith("font-")}
    light = {k: v for k, v in all_light.items() if not k.startswith("font-")}
    return fonts, light, _vars(dark.group(1))


def extract_nav(html: str) -> dict:
    """Devuelve la taxonomía literal del demo: categorías, ETFs y vistas."""
    def obj(name):
        m = re.search(r"var %s = \{(.*?)\};" % name, html, re.S)
        if not m:
            sys.exit(f"No pude localizar `var {name}` en el demo.")
        return m.group(1)

    def pairs(body):
        return dict(re.findall(r'(\w+)\s*:\s*"([^"]*)"', body))

    cat_labels = pairs(obj("CAT_LABELS"))

    cat_order = re.search(r'var CAT_ORDER = \[(.*?)\];', html, re.S)
    order = re.findall(r'"([^"]+)"', cat_order.group(1))

    cats_body = obj("CATS")
    cats = {k: re.findall(r'"([^"]+)"', v)
            for k, v in re.findall(r"(\w+)\s*:\s*\[([^\]]*)\]", cats_body)}

    return {
        "CAT_LABELS": cat_labels,
        "CAT_ORDER": order,
        "CATS": cats,
        "SECTIONS": pairs(obj("SECTIONS")),
        "SECTION_ORDER": re.findall(
            r'"([^"]+)"', re.search(r'var SECTION_ORDER = \[(.*?)\];', html).group(1)),
        "CMP_VIEWS": pairs(obj("CMP_VIEWS")),
        "CMP_ORDER": re.findall(
            r'"([^"]+)"', re.search(r'var CMP_ORDER = \[(.*?)\];', html).group(1)),
        "MET_VIEWS": pairs(obj("MET_VIEWS")),
        "MET_ORDER": re.findall(
            r'"([^"]+)"', re.search(r'var MET_ORDER = \[(.*?)\];', html).group(1)),
    }


# ── Generación ────────────────────────────────────────────────────────────────

HEADER = '''"""{doc}

GENERADO POR `tools/extract_design_system.py` — NO EDITAR A MANO.
Los valores salen del bloque `{origin}` del demo del artifact. Si hay que cambiarlos,
se cambia el demo y se regenera; así el port no puede divergir de su fuente.
"""
'''


def render_tokens(fonts, light, dark) -> str:
    def block(d):
        # repr(): los valores de fuente traen comillas dobles ("Iowan Old Style", …),
        # así que no se pueden envolver a mano sin romper el literal.
        return "\n".join(f"    {k!r}: {v.strip()!r}," for k, v in d.items())

    return HEADER.format(
        doc="Tokens del sistema visual del artifact (solo presentación).",
        origin=":root",
    ) + f'''
FONTS = {{
{block(fonts)}
}}

LIGHT = {{
{block(light)}
}}

DARK = {{
{block(dark)}
}}

THEMES = {{"Claro": LIGHT, "Oscuro": DARK}}


def css_variables(theme: str = "Claro") -> str:
    """Bloque `:root` con los tokens del tema pedido, listo para inyectar."""
    tokens = THEMES.get(theme, LIGHT)
    lines = [f"        --{{k}}: {{v}};" for k, v in {{**FONTS, **tokens}}.items()]
    return ":root {{\\n" + "\\n".join(lines) + "\\n        }}"
'''


def render_nav(nav) -> str:
    def lit(v, ind=4):
        pad = " " * ind
        if isinstance(v, dict):
            inner = "\n".join(f"{pad}    {k!r}: {lit(x, ind + 4)}," for k, x in v.items())
            return "{\n" + inner + "\n" + pad + "}"
        if isinstance(v, list):
            return "(" + ", ".join(repr(x) for x in v) + ("," if len(v) == 1 else "") + ")"
        return repr(v)

    body = "\n\n".join(f"{k} = {lit(v, 0)}" for k, v in nav.items())
    return HEADER.format(
        doc="Taxonomía de navegación del artifact: categorías, ETFs y vistas.",
        origin="las constantes JS de navegación",
    ) + "\n" + body + '''


# «Metodología» NO es una categoría: el demo la oculta al volver a la jerarquía
# (`showCat()`), y se llega a ella por el enlace «¿Cómo funciona? →» y por el pie.
METODOLOGIA_ES_CATEGORIA = False

# El tercer segmento (ETF) solo existe en «Cash flow»; en Salud NAV y Hoja Excel el
# demo lo oculta (`showTab`: `var conEtf = (name === "viaje")`).
VISTA_CON_ETF = "viaje"
'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="no escribe; falla si lo generado difiere de lo que hay en disco")
    args = ap.parse_args()

    html = load_demo()
    fonts, light, dark = extract_tokens(html)
    nav = extract_nav(html)

    outputs = {
        os.path.join(BASE, "ui", "tokens.py"): render_tokens(fonts, light, dark),
        os.path.join(BASE, "ui", "nav.py"): render_nav(nav),
    }

    stale = []
    for path, content in outputs.items():
        rel = os.path.relpath(path, BASE)
        if args.check:
            current = open(path, encoding="utf-8").read() if os.path.exists(path) else None
            if current != content:
                stale.append(rel)
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"generado: {rel}")

    if args.check:
        if stale:
            print("DESACTUALIZADO respecto al demo: " + ", ".join(stale))
            return 1
        print("OK — lo generado coincide con el demo")
        return 0

    print(f"  tokens: {len(fonts)} fuentes + {len(light)} colores claro / {len(dark)} oscuro")
    print(f"  navegación: {len(nav['CAT_ORDER'])} categorías, "
          f"{sum(len(v) for v in nav['CATS'].values())} ETFs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
