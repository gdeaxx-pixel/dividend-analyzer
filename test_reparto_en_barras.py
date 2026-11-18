"""Q2 — el reparto del portafolio deja de ser una dona (18-nov).

La dona respondía bien «cuánto pesa cada fondo» y mal «cuánto pesa cada portafolio», que
es la pregunta de esa pantalla: comparar dos ángulos cuesta más que comparar dos barras
que arrancan en el mismo sitio. Daniel eligió dos barras —una por portafolio, a la misma
escala— sobre una sola barra apilada, donde un fondo de menos del 1% desaparece.

Medido en la app local con el caso de ejemplo: dos filas, siete tramos, barras al 79,67% y
20,33%, y al señalar un fondo los otros seis bajan a 0.2 de opacidad mientras el señalado
queda marcado y el total pasa a describirlo.
"""
import re
from pathlib import Path

COMPONENTE = Path(__file__).resolve().parent / "ui" / "componentes" / "portafolios.html"
FUENTE = COMPONENTE.read_text(encoding="utf-8")


def _funcion(nombre: str) -> str:
    i = FUENTE.index(f"function {nombre}(")
    j = FUENTE.index("\n  function ", i + 1)
    return FUENTE[i:j]


def test_ya_no_hay_dona():
    """Si vuelve el SVG, vuelven los ángulos — y con ellos la pregunta sin responder."""
    for resto in ('id="donut"', "buildDonut", "ring-mark", "function arc("):
        assert resto not in FUENTE, f"quedó {resto}"


def test_una_fila_por_portafolio_con_su_barra():
    fn = _funcion("buildBarras")
    assert "grupos.forEach" in fn
    assert '"rep-g"' in fn and '"rep-track"' in fn and '"rep-bar"' in fn


def test_las_dos_barras_comparten_escala():
    """El ancho de cada barra es el peso de su portafolio sobre el total. Si cada una se
    dibujara al 100% de su propia pista, las dos se verían iguales y no se podrían
    comparar — que es justo lo que no hacía bien la dona."""
    fn = _funcion("buildBarras")
    m = re.search(r"bar\.style\.width = ([^;]+);", fn)
    assert m, "la barra no fija su ancho"
    assert "g.pct" in m.group(1), m.group(1)
    assert "Math.min(100" in m.group(1), "sin tope, un dato sucio desborda la pista"


def test_cada_tramo_es_un_fondo_que_se_puede_pulsar():
    fn = _funcion("buildBarras")
    assert "g.fondos.forEach" in fn
    assert '"rep-seg"' in fn
    for evento in ("pointerenter", "pointerleave", "click"):
        assert evento in fn, f"al tramo le falta {evento}"
    assert "aria-label" in fn, "un tramo de color sin etiqueta no se puede leer"


def test_el_tramo_mide_lo_que_vale_el_fondo():
    fn = _funcion("buildBarras")
    m = re.search(r"seg\.style\.flex = ([^;]+);", fn)
    assert m and "f.mv" in m.group(1), m.group(1) if m else "el tramo no fija su tamaño"


def test_el_nombre_del_grupo_tambien_selecciona():
    fn = _funcion("buildBarras")
    assert '"rep-n"' in fn and "pin(selG)" in fn
    assert "bindRow(nombre, selG)" in fn, "el nombre no se resalta con el resto"


def test_señalar_un_fondo_apaga_los_demas():
    """Era lo que hacía la dona y es lo que hace útil el reparto: aislar un fondo."""
    i = FUENTE.index("fondos.forEach((f) => {", FUENTE.index("function render("))
    bloque = FUENTE[i:i + 400]
    assert "opacity" in bloque and "0.2" in bloque
    assert 'classList.toggle("is-on"' in bloque


def test_el_total_conserva_lo_que_decia_el_centro_de_la_dona():
    """El centro mostraba el valor de mercado y, al señalar, el fondo. Esa línea se
    mantiene: sin ella, aislar un fondo no diría cuánto vale."""
    assert '<div class="rep-total" aria-live="polite">' in FUENTE
    for hueco in ('id="c-k"', 'id="c-v"', 'id="c-s"'):
        assert hueco in FUENTE, hueco


def test_el_tramo_mas_pequeno_sigue_siendo_visible():
    """QYLD pesa menos del 1% en el caso de ejemplo: sin un mínimo, su tramo no existe."""
    m = re.search(r"\.rep-seg \{[^}]*min-width:\s*(\d+)px", FUENTE)
    assert m and int(m.group(1)) >= 3, "el tramo mínimo no llega a 3 px"


def test_el_movimiento_reducido_apaga_la_transicion():
    """El componente tiene dos bloques de movimiento reducido —la narración de las
    tarjetas y las transiciones— y el tramo vive en el segundo."""
    bloques = [FUENTE[m.start():m.start() + 300]
               for m in re.finditer(r"@media \(prefers-reduced-motion", FUENTE)]
    assert bloques, "no hay regla de movimiento reducido"
    assert any(".rep-seg" in b and "transition: none" in b for b in bloques), bloques
