"""Arreglos rápidos de la propuesta de interfaz del 2026-10-30 (A3, A5, A7–A11, D4, D5).

Un guard por arreglo con forma de regresión: cada uno cae con el mutante que devuelve el
texto o el estilo de antes (tabla de mutantes en el cuerpo del PR). Los de Impuestos (A1,
A2) viven en `test_vista_impuestos_render.py`, junto a su arnés de Node. A4 (un solo
mensaje de espera) y A6 («Cambiar» en la fila del resumen) se verificaron en el navegador.
"""
import ast
import json
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from test_carga_1042s import _at_con_posiciones_confirmadas
from ui import adapters, carga, chrome, nav, pie, texto

RAIZ = Path(__file__).resolve().parent

_CARGA = """
import sys
sys.path.insert(0, {path!r})
from ui.carga import render_carga

render_carga()
""".format(path=str(RAIZ))


def _markdown(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def _textos_de_ui():
    """(archivo, línea, texto) de cada literal de texto de `ui/*.py` que puede llegar a
    pantalla: sin docstrings, que documentan y no se muestran. Los literales contiguos ya
    vienen unidos, así que una frase partida en dos líneas se lee entera."""
    for ruta in sorted((RAIZ / "ui").glob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        docstrings = {id(n.body[0].value) for n in ast.walk(arbol)
                      if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                        ast.AsyncFunctionDef))
                      and n.body and isinstance(n.body[0], ast.Expr)
                      and isinstance(n.body[0].value, ast.Constant)
                      and isinstance(n.body[0].value.value, str)}
        for nodo in ast.walk(arbol):
            if (isinstance(nodo, ast.Constant) and isinstance(nodo.value, str)
                    and id(nodo) not in docstrings):
                yield ruta.name, nodo.lineno, nodo.value


# ── A7 · plurales ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("n, esperado", [
    (0, "0 posiciones"), (1, "1 posición"), (2, "2 posiciones"),
])
def test_plural_concuerda_con_el_numero(n, esperado):
    assert texto.plural(n, "posición", "posiciones") == esperado


_PLURAL_A_MEDIAS = re.compile(r"\w\((?:s|es|n)\)")


def test_la_ui_no_escribe_plurales_a_medias():
    """«posición(es)», «ticker(s)», «Falta(n)» en los textos de `ui/*.py`."""
    hallazgos = [f"{archivo}:{linea}: {valor.strip()[:70]}"
                 for archivo, linea, valor in _textos_de_ui()
                 if _PLURAL_A_MEDIAS.search(valor)]
    assert not hallazgos, "plurales a medias:\n  " + "\n  ".join(hallazgos)


# ── A3 · el paso 3 se llama igual bloqueado y abierto ─────────────────────────────────

def test_el_paso_3_bloqueado_lleva_el_titulo_del_abierto():
    at = AppTest.from_string(_CARGA, default_timeout=25)
    at.run()
    assert at.exception == []
    bloqueado = _markdown(at)
    assert carga.TITULO_BLOQUE_FISCAL in bloqueado
    assert "Formulario 1042-S · opcional" not in bloqueado


def test_el_paso_3_abierto_lleva_el_mismo_titulo():
    at = _at_con_posiciones_confirmadas()
    at.run()
    assert at.exception == []
    assert carga.TITULO_BLOQUE_FISCAL in _markdown(at)


# ── A5 · los resultados abren arriba ──────────────────────────────────────────────────

def _subidas(at) -> list[str]:
    return [h.proto.body for h in at.get("html") if "scrollTo(0, 0)" in h.proto.body]


def test_ver_resultados_pide_subir_al_inicio():
    """La hoja de carga sola no consume la petición: la deja para la cabecera."""
    at = _at_con_posiciones_confirmadas()
    at.run()
    boton = next(b for b in at.button if b.proto.id.endswith("_vd_ir_resultados"))
    boton.click().run()
    assert at.exception == []
    assert at.session_state["_wizard_listo"] is True
    try:
        pedido = at.session_state["_vd_subir_al_inicio"]
    except KeyError:
        pedido = None
    assert pedido is True, "«Ver resultados →» no pidió abrir los resultados arriba"


_CABECERA = """
import sys
sys.path.insert(0, {path!r})
import streamlit as st
from ui import chrome, estado

if "_ya_pedido" not in st.session_state:
    st.session_state["_ya_pedido"] = True
    estado.pedir_subir_al_inicio()
chrome.render_encabezado(True)
""".format(path=str(RAIZ))


def test_la_cabecera_sube_al_inicio_una_sola_vez():
    at = AppTest.from_string(_CABECERA, default_timeout=25)
    at.run()
    assert at.exception == []
    assert len(_subidas(at)) == 1, "tras «Ver resultados» la cabecera no sube la página"
    at.run()
    assert _subidas(at) == [], "la subida se repite en cada rerun (p. ej. al tocar el riel)"


# ── A8 · Validación dice de dónde salieron las posiciones ─────────────────────────────

_RECONCILIADO = {"MSTY": {"reconciled_from_snapshot": True, "reconciled_fields": ["shares"]}}

_VALIDACION = """
import sys
sys.path.insert(0, {path!r})
import streamlit as st
from ui import validacion

datos = {datos!r}
validacion._render_calidad_datos(datos)
nivel, razones = validacion._puntuacion_acertividad(datos)
st.text("RAZONES|" + "|".join(razones))
""".format(path=str(RAIZ), datos=_RECONCILIADO)


def test_validacion_no_atribuye_a_una_captura_lo_que_confirmo_el_cliente():
    at = AppTest.from_string(_VALIDACION, default_timeout=25)
    at.run()
    assert at.exception == []
    tarjetas = _markdown(at)
    assert "Reconciliado con tus posiciones" in tarjetas
    assert "confirmaste en el paso 2" in tarjetas
    assert "captura" not in tarjetas
    razones = next(t.value for t in at.text if t.value.startswith("RAZONES|"))
    assert "1 posición tomada de lo que confirmaste en el paso 2, no del CSV." in razones
    assert "captura" not in razones


# ── A9 · «¿Cómo funciona?» solo nombra vistas que el menú ofrece ──────────────────────

def test_como_funciona_no_nombra_vistas_fuera_del_menu():
    alcanzables = {etiqueta for cat in chrome.CAT_ORDER_TOTAL
                   for etiqueta in chrome._vistas(cat).values()}
    assert alcanzables, "no pude leer las vistas del menú"
    retiradas = set(nav.SECTIONS.values()) - alcanzables
    html = (RAIZ / "ui" / "componentes" / "metodologia.html").read_text(encoding="utf-8")
    nombres = (re.findall(r'<h3 class="meth-h">(.*?)</h3>', html)
               + re.findall(r'lab: "([^"]+)"', html))
    assert len(nombres) > 20, "no encontré el índice ni los títulos de Metodología"
    nombradas = sorted({v for v in retiradas for n in nombres if v in n})
    assert not nombradas, f"Metodología nombra vistas que el menú no ofrece: {nombradas}"


# ── A10 · el aviso legal se lee ───────────────────────────────────────────────────────

def test_el_aviso_legal_no_baja_de_12_px():
    tamanos = {m.group(1): float(m.group(2)) for m in re.finditer(
        r"\.(vd-pie-legal[\w-]*)\s*\{[^}]*?font-size:\s*([\d.]+)px", pie.ESTILOS_PIE)}
    assert {"vd-pie-legal-titulo", "vd-pie-legal-cuerpo1",
            "vd-pie-legal-cuerpo2", "vd-pie-legal-badge"} <= set(tamanos), tamanos
    for clase in ("vd-pie-legal-titulo", "vd-pie-legal-cuerpo1", "vd-pie-legal-cuerpo2"):
        assert tamanos[clase] >= 12, f"{clase} a {tamanos[clase]}px"
    assert tamanos["vd-pie-legal-badge"] >= 11


# ── A11 · la ayuda de exportación, una línea por bróker ───────────────────────────────

def test_la_ayuda_de_exportacion_va_una_linea_por_broker():
    at = AppTest.from_string(_CARGA, default_timeout=25)
    at.run()
    ayuda = next(m.value for m in at.markdown if "¿Dónde lo exporto?" in m.value)
    lineas = [re.sub(r"<[^>]+>", "", trozo).strip() for trozo in ayuda.split("<br>")]
    assert lineas[0] == "¿Dónde lo exporto?"
    assert [linea.split(":")[0] for linea in lineas[1:]] == ["Interactive Brokers",
                                                            "Charles Schwab"]


# ── D4 · el paso activo del recorrido no va en rojo ───────────────────────────────────

def test_el_paso_activo_del_recorrido_no_usa_el_rojo_de_perdida():
    reglas = re.findall(r"([^{}]*_now[^{}]*)\{([^}]*)\}", chrome._ESTILOS)
    assert reglas, "no encontré las reglas del paso activo (`_now`)"
    rojas = [sel.strip() for sel, cuerpo in reglas if "var(--loss)" in cuerpo]
    assert not rojas, f"el paso activo usa el rojo de pérdida: {rojas}"


# ── D5 · el recorrido se llama igual que sus columnas ─────────────────────────────────

def test_el_recorrido_se_llama_igual_que_sus_columnas():
    html = (RAIZ / "ui" / "componentes" / "cashflow.html").read_text(encoding="utf-8")
    js = json.loads("[" + re.search(r"var STEP_LABELS = \[(.*?)\];", html, re.S).group(1) + "]")
    columnas = re.findall(r'lab:"([^"]+)"', html)
    assert len(columnas) == 8, columnas
    assert list(adapters.STEP_LABELS) == js == columnas
    mercado = re.search(r'STEP_LABELS\.indexOf\("([^"]+)"\)', html).group(1)
    assert mercado in adapters.STEP_LABELS, f"«{mercado}» no es un paso: indexOf daría -1"


def test_el_texto_de_la_ui_no_manda_al_paso_2_a_declarar_el_pais():
    """A2 en Python (`ui/carga.py`): la residencia está en el paso 3 desde el 23-sep."""
    mal = [f"{archivo}:{linea}" for archivo, linea, valor in _textos_de_ui()
           if re.search(r"(?i)(residencia|país)[^\n]{0,80}paso 2", valor)]
    assert not mal, f"textos que mandan al paso 2: {mal}"
