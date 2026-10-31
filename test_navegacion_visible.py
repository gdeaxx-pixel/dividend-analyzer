"""Navegación visible de la propuesta de interfaz del 2026-10-30 (P1, P2, P7, P8).

P1: las secciones son una fila siempre visible (antes un popover que solo mostraba la
activa) y la confiabilidad es una etiqueta con su nivel. P2: «Cambiar datos» reabre la carga
sin borrar lo subido. P7: cada vista dice si sus cifras son tuyas o del caso de ejemplo, y con
archivo se abre primero la que usa tus datos. P8: el tema es un botón y sigue al del
dispositivo una sola vez por visita. Mutantes en el cuerpo del PR.
"""
import os

from streamlit.testing.v1 import AppTest

from ui import chrome, validacion

_RAIZ = os.path.dirname(os.path.abspath(__file__))
_RESULTADOS = {"MSTY": {"net_profit": 1.0}}

_RUTA = """
import sys
sys.path.insert(0, {path!r})
import streamlit as st
from ui import chrome

st.session_state.setdefault("vd_tema", "Claro")
r = chrome.render_ruta(st.session_state.get("_alerta", False), st.session_state.get("_hab"),
                       confiabilidad=st.session_state.get("_nivel"))
st.session_state["_ruta"] = (r.categoria, r.vista)
""".format(path=_RAIZ)

_CABECERA = """
import sys
sys.path.insert(0, {path!r})
import streamlit as st
from ui import chrome

chrome.render_encabezado(True)
""".format(path=_RAIZ)


def _app(script=_RUTA, **estado) -> AppTest:
    at = AppTest.from_string(script, default_timeout=25)
    for clave, valor in estado.items():
        at.session_state[clave] = valor
    at.run()
    assert at.exception == [], [e.value for e in at.exception]
    return at


def _origen(at) -> str:
    return " ".join(m.value for m in at.markdown if "vd-origen" in m.value)


def _claves(at) -> set:
    return {b.key for b in at.button}


# ── P1 · secciones a la vista ─────────────────────────────────────────────────────────

def test_las_secciones_estan_a_la_vista_y_no_en_un_popover():
    at = _app(_vd_resultados=_RESULTADOS)
    secciones = list(at.button_group(key="vd_cat_w").options)
    assert secciones == [chrome.CAT_LABELS_TOTAL[c] for c in chrome.CAT_ORDER_TOTAL]
    assert not [k for k in _claves(at) if (k or "").startswith("vd_pop_")]


def test_elegir_una_seccion_la_abre():
    at = _app(_vd_resultados=_RESULTADOS)
    at.button_group(key="vd_cat_w").set_value("impuestos").run()
    assert at.session_state["_ruta"][0] == "impuestos"


def test_la_confiabilidad_se_ve_con_su_nivel_y_abre_validacion():
    at = _app(_vd_resultados=_RESULTADOS, _alerta=True, _nivel="Media")
    chip = at.button(key="vd_chip_confiabilidad")
    assert chip.label == "Confiabilidad media"
    chip.click().run()
    assert at.session_state["vd_panel"] == "validacion"


def test_sin_alerta_no_hay_etiqueta_de_confiabilidad():
    at = _app(_vd_resultados=_RESULTADOS, _alerta=False, _nivel="Alta")
    assert "vd_chip_confiabilidad" not in _claves(at)


def test_nivel_de_confiabilidad_sin_resultados():
    assert validacion.nivel_confiabilidad({}) is None


# ── P2 · «Cambiar datos» ──────────────────────────────────────────────────────────────

def test_cambiar_datos_reabre_la_carga_sin_borrar_lo_subido():
    at = _app(_vd_resultados=_RESULTADOS, _wizard_listo=True, _wizard_df_clean="csv")
    at.button(key="vd_cambiar_datos").click().run()
    assert at.session_state["_wizard_listo"] is False
    assert at.session_state["_wizard_df_clean"] == "csv"
    assert at.session_state["_vd_resultados"] == _RESULTADOS
    assert at.session_state["_vd_subir_al_inicio"] is True


def test_sin_archivo_no_hay_cambiar_datos():
    """Riesgo sin archivo ya trae su propio «volver» a la carga (`riesgo.volver_a_cargar`)."""
    at = _app()
    assert "vd_cambiar_datos" not in _claves(at)


# ── P7 · de dónde salen las cifras ────────────────────────────────────────────────────

def test_con_archivo_comparacion_abre_en_tus_datos():
    at = _app(_vd_resultados=_RESULTADOS, vd_categoria="comparacion")
    assert at.session_state["_ruta"] == ("comparacion", "real")
    assert list(at.button_group(key="vd_vista_w_comparacion").options) == ["Real", "Simulación"]
    assert "Con tus datos" in _origen(at)


def test_con_archivo_metodo_abre_en_matriz_2():
    at = _app(_vd_resultados=_RESULTADOS, vd_categoria="metodo")
    assert at.session_state["_ruta"] == ("metodo", "matriz2")


def test_las_vistas_de_la_clase_dicen_caso_de_ejemplo():
    for categoria, vista in (("comparacion", "simulacion"), ("metodo", "matriz")):
        at = _app(_vd_resultados=_RESULTADOS, vd_categoria=categoria, vd_vista=vista)
        assert at.session_state["_ruta"] == (categoria, vista)
        assert "Caso de ejemplo" in _origen(at), categoria


def test_sin_archivo_la_comparacion_conserva_el_orden_del_demo():
    at = _app(vd_categoria="comparacion")
    assert at.session_state["_ruta"] == ("comparacion", "simulacion")


# ── P8 · tema ─────────────────────────────────────────────────────────────────────────

def _scripts_de_tema(at) -> list:
    return [h for h in at.get("html") if "prefers-color-scheme" in h.proto.body]


def test_el_tema_sigue_al_dispositivo_una_sola_vez_por_visita():
    at = _app(_CABECERA)
    assert len(_scripts_de_tema(at)) == 1
    at.run()
    assert _scripts_de_tema(at) == [], "el script vuelve en cada rerun y pelearía con el cliente"


def test_el_boton_de_tema_alterna_claro_y_oscuro():
    at = _app(_CABECERA)
    at.button(key="vd_tema_btn").click().run()
    assert at.session_state["vd_tema"] == "Oscuro"
    at.button(key="vd_tema_btn").click().run()
    assert at.session_state["vd_tema"] == "Claro"
