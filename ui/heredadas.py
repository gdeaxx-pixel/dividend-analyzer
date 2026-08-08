"""Categoría «Detalle» — secciones de `app.py` que el artifact nunca cubrió.

Fase 5 (traspaso § Fase 5 — Arquitectura): estas 4 vistas agrupan las secciones
heredadas que Daniel decidió que vivan en su propia categoría de la ruta, en vez de
resucitar el scroll infinito de `app.py`. A diferencia de `ui/nav.py`, este módulo
**no se genera** — el demo del artifact no tiene una quinta categoría, así que
inventarla ahí rompería el `--check` de `tools/extract_design_system.py` y dejaría
que el port divergiera de su fuente sin que nadie lo note. Aquí sí se escribe a mano,
porque no hay nada que extraer: nunca existió en el artifact.

Regla de método de esta fase (no la de las fases 1-4): se copia la lógica y el texto
literal de `app.py`, re-vestido con `ui/tokens.py`. No se redactan de nuevo los
textos ni se reinterpretan las cifras.
"""

from __future__ import annotations

CAT_CLAVE = "detalle"
CAT_LABEL = "Detalle"

VIEWS = {
    "portafolios": "Portafolios",
    "ingresos": "Ingresos",
    "proyeccion": "Proyección",
    "estrategias": "Estrategias",
}

VIEW_ORDER = ("portafolios", "ingresos", "proyeccion", "estrategias")


def render_vista(vista: str, ruta) -> None:
    """Despacho de las 4 vistas de Detalle. 5a las deja como superficie honesta
    (`render_placeholder`); 5b porta Portafolios/Ingresos, 5c Proyección/Estrategias."""
    from ui.chrome import render_placeholder

    render_placeholder(ruta)
