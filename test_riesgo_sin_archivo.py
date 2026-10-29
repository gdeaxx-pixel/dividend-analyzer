"""«Riesgo» sin archivo: la hoja de carga ofrece la entrada y la vista ofrece el regreso.

Datos sintéticos: la canasta es la receta de prueba de `test_riesgo_mezcla.py`; nunca la real.
"""
import os

import pytest
from streamlit.testing.v1 import AppTest

import stale_guard
from test_riesgo_mezcla import RECETA, _serie

_APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
_ENTRADA = "_vd_riesgo_sin_archivo"
_REGRESO = "_vd_riesgo_subir_archivo"


def _claves_boton(at):
    return {b.key for b in at.button}


def _iframes_riesgo(at):
    return [f for f in at.get("iframe") if 'id="riesgo-root"' in f.proto.srcdoc]


@pytest.fixture
def app(monkeypatch):
    from ui import riesgo

    monkeypatch.setattr(stale_guard, "asegurar_frescura", lambda: [])
    monkeypatch.setattr(riesgo, "_historias_riesgo",
                        lambda tickers: ({t: _serie(150) for t in ("AAA", "BBB", "CCC")}, []))

    def _crear(receta):
        monkeypatch.setattr(riesgo, "_receta_referencia", lambda: receta)
        at = AppTest.from_file(_APP, default_timeout=60)
        at.run()
        assert len(at.exception) == 0
        return at

    return _crear


def test_sin_receta_la_carga_no_ofrece_la_entrada(app):
    assert _ENTRADA not in _claves_boton(app(None))


def test_con_receta_se_entra_a_riesgo_sin_archivo_y_se_vuelve_a_cargar(app):
    at = app(dict(RECETA))
    assert _ENTRADA in _claves_boton(at)

    at.button(key=_ENTRADA).click().run()
    assert len(at.exception) == 0
    assert at.session_state["vd_categoria"] == "riesgo"
    assert len(_iframes_riesgo(at)) == 1
    assert any("Sube tu archivo" in c.value for c in at.caption)
    assert _REGRESO in _claves_boton(at)

    at.button(key=_REGRESO).click().run()
    assert len(at.exception) == 0
    assert _iframes_riesgo(at) == []
    assert _ENTRADA in _claves_boton(at)
