"""Q3 — «Largo Plazo» y «Dividendos», una sola pestaña: «Fondo por fondo» (14-nov).

Las dos abrían la MISMA pantalla —el Cash flow de un fondo— y solo cambiaba la lista del
selector, así que para ver NVDY había que acertar antes en qué grupo lo pusimos. Ahora el
menú tiene seis entradas y dentro están los dos grupos, cada uno con su nombre: la
separación entre fondos de crecimiento y de dividendos es parte del método, no del menú.

La taxonomía (`ui/nav.py`, generada desde el demo) no cambia: por dentro cada fondo sigue
en su categoría, que es lo que entienden las vistas y los adaptadores. Lo que se une es la
presentación.

Medido en la app local: seis secciones; en el teléfono los grupos se apilan (124 px de
alto, sin desborde) y en escritorio van lado a lado (58 px).
"""
import os

from streamlit.testing.v1 import AppTest

from ui import chrome, nav

_RAIZ = os.path.dirname(os.path.abspath(__file__))
_RESULTADOS = {"MSTY": {"net_profit": 1.0}}

_SCRIPT = """
import sys
sys.path.insert(0, {path!r})
import streamlit as st
from ui import chrome

st.session_state.setdefault("vd_tema", "Claro")
r = chrome.render_ruta(False, st.session_state.get("_hab"))
st.session_state["_ruta"] = (r.categoria, r.vista, r.etf)
""".format(path=_RAIZ)

_HAB = {"largo": ["SCHB", "XLK"], "dividendos": ["MSTY", "NVDY"]}


def _app(**estado) -> AppTest:
    at = AppTest.from_string(_SCRIPT, default_timeout=25)
    for clave, valor in estado.items():
        at.session_state[clave] = valor
    at.run()
    assert at.exception == [], [e.value for e in at.exception]
    return at


def _secciones(at):
    return list(at.button_group(key="vd_cat_w").options)


# ── El menú ───────────────────────────────────────────────────────────────────────────

def test_el_menu_tiene_una_entrada_en_vez_de_dos():
    at = _app(_vd_resultados=_RESULTADOS, _hab=_HAB)
    secciones = _secciones(at)
    assert chrome.LABEL_FONDOS in secciones
    assert "Largo Plazo" not in secciones and "Dividendos" not in secciones
    assert len(secciones) == len(chrome.CAT_ORDER_TOTAL) - 1


def test_estando_en_un_fondo_la_pestana_marcada_es_la_unida():
    at = _app(_vd_resultados=_RESULTADOS, _hab=_HAB, vd_categoria="dividendos")
    assert at.session_state["vd_cat_w"] == chrome.CAT_FONDOS


def test_la_ruta_nunca_se_queda_en_la_entrada_del_menu():
    """«fondos» es una entrada de menú, no una categoría: las vistas y los adaptadores no
    sabrían qué hacer con ella."""
    at = _app(_vd_resultados=_RESULTADOS, _hab=_HAB, vd_categoria=chrome.CAT_FONDOS)
    categoria, _, _ = at.session_state["_ruta"]
    assert categoria in chrome.CATS_FONDOS
    assert at.session_state["vd_categoria"] in nav.CATS


# ── Los dos grupos, dentro ────────────────────────────────────────────────────────────

def test_cada_grupo_trae_su_nombre_y_sus_fondos():
    at = _app(_vd_resultados=_RESULTADOS, _hab=_HAB, vd_categoria="largo")
    for grupo, fondos in _HAB.items():
        control = at.button_group(key=f"vd_etf_w_{grupo}")
        assert list(control.options) == fondos
        assert control.label == chrome.CAT_LABELS_TOTAL[grupo], (
            "sin el nombre del grupo, los dos bloques de chips no se distinguen")


def test_solo_esta_marcado_el_fondo_del_grupo_activo():
    """Dos chips encendidos a la vez dirían que estás viendo dos fondos. Se mira lo que
    el control muestra marcado, no el estado: un valor que no está entre sus opciones
    Streamlit lo descarta solo, y entonces el estado no delata nada."""
    at = _app(_vd_resultados=_RESULTADOS, _hab=_HAB, vd_categoria="largo")
    marcados = {g: at.button_group(key=f"vd_etf_w_{g}").value for g in _HAB}
    assert marcados["largo"] in _HAB["largo"]
    assert marcados["dividendos"] is None, marcados


def test_elegir_un_fondo_del_otro_grupo_cambia_de_grupo():
    """La prueba de verdad: el clic tiene que mover también la categoría interna."""
    at = _app(_vd_resultados=_RESULTADOS, _hab=_HAB, vd_categoria="largo")
    at.button_group(key="vd_etf_w_dividendos").set_value("NVDY").run()
    categoria, _, etf = at.session_state["_ruta"]
    assert categoria == "dividendos" and etf == "NVDY"
    assert at.session_state["vd_cat_w"] == chrome.CAT_FONDOS


def test_un_grupo_sin_fondos_en_el_archivo_no_se_dibuja():
    at = _app(_vd_resultados=_RESULTADOS, _hab={"largo": [], "dividendos": ["MSTY"]},
              vd_categoria="dividendos")
    claves = {b.key for b in at.button_group}
    assert "vd_etf_w_dividendos" in claves
    assert "vd_etf_w_largo" not in claves


def test_sin_ningun_fondo_la_seccion_desaparece_del_menu():
    at = _app(_vd_resultados=_RESULTADOS, _hab={"largo": [], "dividendos": []})
    assert chrome.LABEL_FONDOS not in _secciones(at)
