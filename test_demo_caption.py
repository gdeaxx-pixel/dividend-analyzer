"""`?demo=` en un despliegue sin `real_examples/` (producción) no cae en silencio a la carga.

Auditoría 2026-10-07, F9: el caption solo salía con `demo_mode.demo_available()`; sin datos
privados `?demo=schwab` mostraba la pantalla de carga sin explicar por qué.
"""

import os

import pytest
from streamlit.testing.v1 import AppTest

import demo_mode
import stale_guard

_APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
_FRASE = "instalación local"


@pytest.mark.parametrize("demo, espera_caption", [("ib", True), (None, False)])
def test_demo_sin_real_examples_lo_explica(monkeypatch, demo, espera_caption):
    # Dentro de la suite completa, otros tests dejan fechas en `stale_guard._fechas` y
    # `app.py` recarga todos los módulos propios al arrancar: la recarga re-ejecuta
    # `demo_mode` y pisa los dobles de abajo (medido: tras el run `demo_available` volvía a
    # ser la función real y el demo «ib» cargaba). El guardián no es lo que se prueba aquí.
    monkeypatch.setattr(stale_guard, "asegurar_frescura", lambda: [])
    monkeypatch.setattr(demo_mode, "demo_available", lambda: False)
    monkeypatch.setattr(demo_mode, "load_demo_case", lambda param: None)

    at = AppTest.from_file(_APP, default_timeout=60)
    if demo:
        at.query_params["demo"] = demo
    at.run()

    assert len(at.exception) == 0
    captions = [c.value for c in at.caption]
    assert any(_FRASE in c for c in captions) is espera_caption, captions
