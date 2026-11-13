"""El medidor de datos ya no abre la pantalla de carga (13-nov).

Hasta hoy la dona de 5 segmentos se dibujaba arriba del todo, debajo del wordmark. Medido en
el piloto de interfaz: en teléfono salía **antes del título** y «4 de 5 verificados · Falta:
información fiscal» se leía como una nota de examen y como un error del cliente, cuando ese
paso es opcional. Daniel: «es mucha vaina… que no asuste al cliente con tanto».

Ahora la hoja abre con un titular que dice qué se obtiene, y el medidor baja al pie —una
frase antes de «Ver resultados», que es donde el dato decide algo— con los cinco controles a
un clic. La fuente de los estados no cambia: sigue siendo `adapters.cobertura_data`.
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from test_carga_1042s import _at_con_posiciones_confirmadas
from ui import componentes

RAIZ = Path(__file__).resolve().parent

_CARGA = """
import sys
sys.path.insert(0, {path!r})
from ui.carga import render_carga

render_carga()
""".format(path=str(RAIZ))


def _markdown(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def _texto(at) -> str:
    """Todo lo que el cliente puede leer: markdown, captions y los títulos de los
    desplegables — el label de un expander no es markdown y no sale en `at.markdown`."""
    etiquetas = [getattr(e, "label", "") or "" for e in at.get("expander")]
    return "\n".join([_markdown(at)] + [c.value for c in at.caption] + etiquetas)


@pytest.fixture
def donas(monkeypatch):
    """Registra cada vez que la hoja dibuja la dona, sin dibujarla."""
    llamadas = []
    monkeypatch.setattr(componentes, "render_cobertura",
                        lambda *a, **k: llamadas.append(a[0] if a else None))
    return llamadas


def test_la_hoja_abre_con_el_titular_y_sin_el_medidor(donas):
    at = AppTest.from_string(_CARGA, default_timeout=25)
    at.run()
    assert at.exception == []
    assert "cuánto has ganado de verdad" in _markdown(at), "falta el titular de la carga"
    assert not donas, "la dona volvió a abrir la pantalla"


def test_sin_posiciones_confirmadas_no_se_habla_de_controles(donas):
    """El medidor informa al final. Antes de confirmar no hay nada que decidir con él."""
    at = AppTest.from_string(_CARGA, default_timeout=25)
    at.run()
    assert "Ver qué revisamos" not in _texto(at)


def test_con_las_posiciones_confirmadas_la_frase_sale_al_pie(donas):
    at = _at_con_posiciones_confirmadas()
    at.run()
    assert at.exception == []
    texto = _texto(at)
    assert "Ver qué revisamos" in texto, "el medidor no aparece antes de «Ver resultados»"
    assert "ya salen tus cifras" in texto or "están revisados" in texto
    assert not donas, "la dona se dibujó además de la frase"
    assert [b for b in at.button if b.key == "_vd_ir_resultados"], "falta «Ver resultados»"


def test_la_frase_nombra_lo_que_falta_en_vez_de_contar_una_nota(donas):
    """«4 de 5 verificados» se leía como un examen suspendido. La frase dice qué falta."""
    at = _at_con_posiciones_confirmadas()
    at.run()
    texto = _texto(at)
    assert "de 5 verificados" not in texto, "volvió el recuento con forma de nota"
    assert "Falta:" not in texto, "volvió el aviso que suena a error del cliente"


def test_los_cinco_controles_siguen_estando_a_un_clic(donas):
    """Mover el medidor no puede perder el detalle: era lo que daban los pop-outs de la dona."""
    at = _at_con_posiciones_confirmadas()
    at.run()
    nombres = ["Movimientos", "Posiciones", "Información fiscal", "Valoración", "Excluidos"]
    md = _markdown(at)
    faltan = [n for n in nombres if n not in md]
    assert not faltan, f"el desplegable no lista estos controles: {faltan}"


@pytest.mark.parametrize("faltan, esperado", [
    (["Información fiscal"], "falta información fiscal."),
    (["Movimientos", "Información fiscal"], "faltan movimientos e información fiscal."),
    (["Movimientos", "Valoración"], "faltan movimientos y valoración."),
])
def test_la_frase_concuerda_y_usa_la_e_ante_i(monkeypatch, faltan, esperado):
    """Medido en vivo el 13-nov: salía «Para afinarlas falta movimientos, historial de
    posiciones y información fiscal» — singular con tres cosas, y «y» ante i-."""
    from ui import adapters, carga

    nombres = ["Movimientos", "Posiciones", "Información fiscal", "Valoración", "Excluidos"]
    monkeypatch.setattr(adapters, "cobertura_data", lambda *a, **k: {
        "segmentos": [{"clave": n.lower(), "nombre": n,
                       "estado": "pendiente" if n in faltan else "ok",
                       "falta": "x", "como": "y"} for n in nombres],
        "verificados": len(nombres) - len(faltan)})
    dichos = []
    monkeypatch.setattr(carga.st, "caption", lambda texto, **k: dichos.append(texto))
    monkeypatch.setattr(carga.st, "expander", lambda *a, **k: __import__("contextlib").nullcontext())
    monkeypatch.setattr(carga.st, "markdown", lambda *a, **k: None)
    monkeypatch.setattr(carga, "_resultados_para_cobertura", lambda: {"x": 1})
    carga._render_cobertura_frase()
    assert dichos and dichos[0].endswith(esperado), dichos


def test_el_titular_lleva_su_regla_de_tamano():
    """Streamlit pinta los encabezados a 36px y gana por especificidad: sin una regla sobre el
    ELEMENTO, el titular salía en cuatro líneas a 390px (medido el 13-nov con viewport real;
    con la regla, 20px y 80px de alto). Este guard solo vigila que la regla siga ahí — el
    tamaño real se mide en el navegador, no aquí."""
    from ui import carga

    at = AppTest.from_string(_CARGA, default_timeout=25)
    at.run()
    titular = [m.value for m in at.markdown if "Sube tu historial" in m.value]
    assert titular, "no se dibujó el titular"
    assert 'class="vd-title vd-carga-h"' in titular[0], "el titular perdió sus clases"
    assert "h2.vd-title.vd-carga-h" in carga.ESTILOS_CARGA, (
        "falta la regla que vence al tamaño por defecto de Streamlit")
    assert "!important" in carga.ESTILOS_CARGA.split("h2.vd-title.vd-carga-h")[1][:200], (
        "la regla del titular ya no reafirma el tamaño y Streamlit vuelve a ganar")
