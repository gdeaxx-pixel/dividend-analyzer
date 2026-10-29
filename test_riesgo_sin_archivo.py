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
    monkeypatch.setattr(riesgo, "_historias_estres", lambda tickers, inicio, fin: {})
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


def test_entrar_sin_archivo_no_anuncia_el_paso_3(app):
    at = app(dict(RECETA))
    at.button(key=_ENTRADA).click().run()
    assert at.session_state["vd_categoria"] == "riesgo"
    assert not [t for t in at.toast if "Paso 3" in t.value]


@pytest.mark.parametrize("categoria", ["riesgo", "detalle", "comparacion", "metodo", "impuestos"])
def test_sin_archivo_toda_categoria_ofrece_volver_a_la_carga(app, categoria):
    at = app(dict(RECETA))
    at.button(key=_ENTRADA).click().run()
    at.session_state["vd_categoria"] = categoria
    at.run()
    assert len(at.exception) == 0
    assert at.session_state["vd_categoria"] == categoria
    assert [b.key for b in at.button].count(_REGRESO) == 1

    at.button(key=_REGRESO).click().run()
    assert _ENTRADA in _claves_boton(at)


def test_tras_volver_a_la_carga_se_aterriza_en_portafolios(app):
    from ui import chrome

    at = app(dict(RECETA))
    at.button(key=_ENTRADA).click().run()
    at.button(key=_REGRESO).click().run()
    # lo único que hace «Ver resultados →» con el archivo ya cargado
    at.session_state["_wizard_listo"] = True
    at.run()
    assert at.session_state["vd_categoria"] == chrome.CAT_ORDER_TOTAL[0]


@pytest.mark.parametrize("csv, resultados", [("csv", {}), (None, {"AAA": {}})],
                         ids=["con_csv", "con_resultados"])
def test_con_archivo_no_se_ofrece_volver_a_la_carga(app, csv, resultados):
    at = app(dict(RECETA))
    at.session_state["_wizard_listo"] = True
    at.session_state["_wizard_df_clean"] = csv
    at.session_state["_vd_resultados"] = resultados
    at.session_state["vd_categoria"] = "metodo"
    at.run()
    assert len(at.exception) == 0
    assert _REGRESO not in _claves_boton(at)
