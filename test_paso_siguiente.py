"""A3 y Q4 de la propuesta del 13-nov (tanda 3, resultados).

A3 — al pie de cada sección, el paso siguiente del recorrido. Antes, al terminar de leer
     una vista, había que volver arriba y adivinar cuál sigue.
Q4 — «Con tus datos» solo donde hay una vista de ejemplo con la que confundirla.

El recorrido es el mismo que ya ofrece el menú: sección por sección, en el orden de
`CAT_ORDER_TOTAL`, y dentro de cada una el orden de su fila de vistas.
"""
import os

import pytest
from streamlit.testing.v1 import AppTest

from ui import chrome

_RAIZ = os.path.dirname(os.path.abspath(__file__))
_RESULTADOS = {"MSTY": {"net_profit": 1.0}}

_SCRIPT = """
import sys
sys.path.insert(0, {path!r})
import streamlit as st
from ui import chrome, estado

st.session_state.setdefault("vd_tema", "Claro")
r = chrome.render_ruta(False, st.session_state.get("_hab"))
if st.session_state.get("_pide_saltar"):
    estado.ya_ofrece_a_donde_ir()
chrome.render_siguiente(r, st.session_state.get("_hab"))
st.session_state["_ruta"] = (r.categoria, r.vista)
""".format(path=_RAIZ)


def _app(**estado) -> AppTest:
    at = AppTest.from_string(_SCRIPT, default_timeout=25)
    for clave, valor in estado.items():
        at.session_state[clave] = valor
    at.run()
    assert at.exception == [], [e.value for e in at.exception]
    return at


def _siguiente(at):
    return next((b for b in at.button if b.key == "vd_ir_siguiente"), None)


def _origen(at) -> str:
    return " ".join(m.value for m in at.markdown if "vd-origen" in m.value)


# ── A3 · el paso siguiente ────────────────────────────────────────────────────────────

def test_la_primera_seccion_manda_a_la_segunda():
    at = _app(_vd_resultados=_RESULTADOS, vd_categoria="portafolios")
    boton = _siguiente(at)
    assert boton is not None, "no hay paso siguiente al pie"
    assert boton.label == "Riesgo →"


def test_pulsarlo_abre_esa_vista():
    """La prueba de verdad: no que el botón esté, sino que lleve a donde dice."""
    at = _app(_vd_resultados=_RESULTADOS, vd_categoria="portafolios")
    _siguiente(at).click().run()
    assert at.session_state["_ruta"] == ("riesgo", "riesgo")


def test_dentro_de_una_seccion_pasa_a_la_vista_de_al_lado():
    at = _app(_vd_resultados=_RESULTADOS, vd_categoria="comparacion", vd_vista="real")
    _siguiente(at).click().run()
    assert at.session_state["_ruta"] == ("comparacion", "simulacion")


def test_la_ultima_vista_no_ofrece_siguiente():
    cat, vista = chrome._recorrido()[-1]
    at = _app(_vd_resultados=_RESULTADOS, vd_categoria=cat, vd_vista=vista)
    assert _siguiente(at) is None, "hay un «siguiente» en la última vista"


def test_el_recorrido_no_repite_ni_se_salta_ninguna_vista():
    pasos = chrome._recorrido()
    assert len(pasos) == len(set(pasos)), "una vista aparece dos veces"
    esperadas = [(c, v) for c in chrome.CAT_ORDER_TOTAL for v in chrome._orden(c)]
    assert pasos == esperadas


def test_una_seccion_sin_etf_no_entra_en_el_recorrido():
    """Mismo filtro que el menú: si no hay fondos de esa clase, no se ofrece ir allí."""
    hab = {"largo": [], "dividendos": ["MSTY"]}
    cats = {c for c, _ in chrome._recorrido(hab)}
    assert "largo" not in cats and "dividendos" in cats


# ── Q4 · la etiqueta de origen ────────────────────────────────────────────────────────

def test_sin_vista_de_ejemplo_al_lado_no_hay_etiqueta():
    at = _app(_vd_resultados=_RESULTADOS, vd_categoria="portafolios")
    assert _origen(at) == "", "«Con tus datos» donde no hay nada que distinguir"


@pytest.mark.parametrize("vista, texto", [("real", "Con tus datos"),
                                          ("simulacion", "Caso de ejemplo")])
def test_donde_conviven_las_dos_cada_una_se_nombra(vista, texto):
    at = _app(_vd_resultados=_RESULTADOS, vd_categoria="comparacion", vd_vista=vista)
    assert texto in _origen(at)


def test_sin_archivo_todo_sigue_diciendo_caso_de_ejemplo():
    at = _app(vd_categoria="portafolios")
    assert "Caso de ejemplo" in _origen(at)


def test_la_etiqueta_desaparece_entera_no_queda_el_hueco():
    """Un `<span>` vacío dejaría el punto de color y el margen del contenedor."""
    at = _app(_vd_resultados=_RESULTADOS, vd_categoria="portafolios")
    assert not [m for m in at.markdown if "vd-origen" in m.value]


# ── La vista que ya guía ──────────────────────────────────────────────────────────────

def test_si_la_vista_ya_dice_a_donde_ir_el_pie_se_calla():
    """Portafolios cierra con «Para entenderlo a fondo»: dos destinos distintos, uno
    encima del otro, es justo el ruido que había que quitar."""
    at = _app(_vd_resultados=_RESULTADOS, vd_categoria="portafolios", _pide_saltar=True)
    assert _siguiente(at) is None


def test_ese_silencio_dura_solo_esa_corrida():
    """Si la marca no se consume, el pie desaparece para siempre tras pasar por
    Portafolios."""
    at = _app(_vd_resultados=_RESULTADOS, vd_categoria="portafolios", _pide_saltar=True)
    assert _siguiente(at) is None
    at.session_state["_pide_saltar"] = False
    at.run()
    assert _siguiente(at) is not None, "la marca se quedó pegada"


def test_portafolios_pide_el_silencio_de_verdad():
    """Que el pie sepa callarse no sirve si nadie se lo pide: la vista de Portafolios
    llama a `ya_ofrece_a_donde_ir` justo donde pinta sus rutas."""
    import inspect

    from ui import heredadas

    fuente = inspect.getsource(heredadas._botones_ruta)
    assert "ya_ofrece_a_donde_ir()" in fuente
