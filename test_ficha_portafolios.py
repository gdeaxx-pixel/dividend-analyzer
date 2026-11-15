"""Cada fila de «Por portafolio» explica su parte al pulsarla (14-nov).

La gráfica decía QUÉ pasó; no decía por qué el precio de un fondo que reparte mucho baja
solo, ni que lo cobrado ya viene con la retención descontada. Eso estaba en el piloto
(`demos/propuesta-ui-2026-11-13.html`) y faltaba en la app.

Estos guards vigilan el contrato del componente: que la fila sea pulsable, que el marcado
sea válido dentro de un botón, que la ficha y las filas hablen de lo mismo, y que el modal
no se salga del iframe. Que se vea bien es cosa del navegador: medido en local con el caso
de ejemplo (6 filas pulsables, modal dentro del iframe en 653-1096 de 1116 px).
"""
import re
from pathlib import Path

import pytest

COMPONENTE = Path(__file__).resolve().parent / "ui" / "componentes" / "portafolios.html"
FUENTE = COMPONENTE.read_text(encoding="utf-8")


def _bloque(inicio: str, fin: str) -> str:
    a = FUENTE.index(inicio)
    b = FUENTE.index(fin, a)
    return FUENTE[a:b]


def test_la_fila_es_un_boton_y_no_un_div():
    """Un div con onclick no recibe foco ni responde a Enter."""
    assert '<button type="button" class="wf-row' in FUENTE
    assert "'<div class=\"wf-row" not in FUENTE, "la fila volvió a ser un div"


def test_la_fila_dice_qué_ficha_y_de_qué_portafolio():
    fila = _bloque("const rows = filas(g).map", "}).join(\"\");")
    assert "data-ficha=" in fila and "data-grupo=" in fila
    assert "aria-label=" in fila, "sin etiqueta no se sabe qué fila se va a abrir"


def test_dentro_de_un_boton_no_hay_p_ni_div():
    """HTML inválido: el navegador expulsa `<p>`/`<div>` del botón y parte la fila en dos."""
    fila = _bloque("const rows = filas(g).map", "}).join(\"\");")
    assert "<p " not in fila and "<div " not in fila, "marcado de bloque dentro del botón"


def test_el_contenedor_dejó_de_ser_una_imagen():
    """`role="img"` esconde del lector de pantalla los botones que ahora lleva dentro."""
    cascada = _bloque("'<div class=\"wf'", "+ rows + '</div>'")
    assert 'role="img"' not in cascada
    assert 'role="group"' in cascada and 'aria-label=' in cascada


def test_la_ficha_y_las_filas_hablan_de_las_mismas_tres_partes():
    """Si una se renombra y la otra no, pulsar esa fila no abriría nada."""
    filas = set(re.findall(r"\{ id: \"(\w+)\"", _bloque("const filas = (g) => [", "];")))
    fichas = set(re.findall(r"^    (\w+): \{$", _bloque("const FICHAS = {", "\n  };"), re.M))
    assert filas == fichas == {"precio", "dividendos", "retorno"}, (filas, fichas)


def test_cada_hueco_del_modal_existe_en_el_html():
    """`getElementById` de un id que no está devuelve null y el modal revienta al abrir."""
    usados = set(re.findall(r'getElementById\("(mp-[\w-]+)"\)', FUENTE))
    presentes = set(re.findall(r'id="(mp-[\w-]+)"', FUENTE))
    assert usados and usados <= presentes, usados - presentes


def test_la_tabla_del_modal_repite_las_cifras_de_las_filas():
    """Sin aritmética propia: un redondeo distinto descuadraría la ficha con la gráfica."""
    fn = _bloque("function fichaFilas(g)", "\n  }")
    assert "filas(g).map" in fn, "la ficha se calcula aparte de las filas"
    assert "signed(r.v)" in fn
    assert not re.search(r"r\.v\s*[-+*/]\s*\w", fn), "la ficha está haciendo cuentas"


def test_el_modal_se_coloca_contra_la_ventana_y_cabe_en_el_iframe():
    """Dentro de un iframe auto-dimensionado, `position: fixed` se centra en el iframe."""
    fn = _bloque("function abrirFicha(", "function cerrarFicha(")
    assert "window.frameElement" in fn, "sin esto el modal aparece fuera de la pantalla"
    assert "ownerDocument.defaultView.innerHeight" in fn
    assert "document.documentElement.scrollHeight - box.offsetHeight" in fn, (
        "falta sujetarlo al alto del iframe: el pie del modal se recorta")


@pytest.mark.parametrize("cierre, pista", [
    ('getElementById("mp-close").addEventListener("click"', "la ×"),
    ("if (e.target === md) cerrarFicha()", "el clic fuera"),
    ('e.key === "Escape"', "la tecla Escape"),
])
def test_la_ficha_se_puede_cerrar(cierre, pista):
    assert cierre in FUENTE, f"no se puede cerrar con {pista}"


def test_el_foco_vuelve_a_la_fila_al_cerrar():
    fn = _bloque("function cerrarFicha()", "\n  }")
    assert "abridor" in fn and "focus()" in fn


def test_el_clic_está_delegado_en_el_contenedor():
    """`buildCards()` recrea las tarjetas en cada repintado: un listener por fila se pierde."""
    assert '$("cards").addEventListener("click"' in FUENTE
    assert 'closest(".wf-row")' in FUENTE


def test_dice_que_el_dividendo_ya_trae_la_retención_descontada():
    """La cifra sale de `dividends_net_total` (ui/adapters.py), que es neto de NRA."""
    ficha = _bloque("    dividendos: {", "    retorno: {")
    assert "retención de impuestos descontada" in ficha
    assert "Impuestos" in ficha, "sin decir dónde está el desglose"


def test_explica_por_qué_baja_el_precio_de_un_fondo_que_reparte():
    ficha = _bloque("    precio: {", "    dividendos: {")
    assert "el fondo entrega el efectivo y su precio baja" in ficha
