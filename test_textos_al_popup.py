"""Q5 — el texto largo de «La matriz» pasa al popup (18-nov).

Regla de Riesgo v15 (`APPs/Dividend-Decisiones.md`): cada sección responde con una cifra,
una frase y una gráfica; el detalle va al popup; nada se dice tres veces.

Medido en la app antes de tocar nada, contando los nodos de texto visibles fuera de los
popups: «La matriz» 855 palabras, «Matriz 2» 325 e Impuestos 141. **Impuestos ya cumplía
la regla y no se toca.** Tras mover el detalle, «La matriz» queda en 226 con el mismo
criterio, y el popup recoge 371 palabras.

Lo que se movió y por qué: los cuatro puntos de metodología, y la mitad del lede que
describe qué es cada línea — eso ya lo dice la leyenda de la propia gráfica, medido («Sin
NRA · reinvierte», «… · cobra», «Capital aportado»).

**Nada se borra.** Cada frase que salió de la vista existe íntegra en el popup, y eso es
lo que vigilan estos guards: un recorte que resume en vez de mover sería perder texto que
Daniel aprobó.
"""
import re
from pathlib import Path

COMPONENTE = Path(__file__).resolve().parent / "ui" / "componentes" / "metodo.html"
FUENTE = COMPONENTE.read_text(encoding="utf-8")

# Frases que vivían en la vista y ahora tienen que estar en el popup, palabra por palabra.
MOVIDAS = [
    "Hay seis porque los tres escenarios fiscales se cruzan",
    "La línea gris punteada es el",
    "capital aportado",
    "Qué mide la altura.",
    "De dónde salen los tres escenarios.",
    "Cuadra con las tablas de arriba, en los seis escenarios.",
    "<b>Fuente.</b>",
    "el camino importa ",
    "que esta sección entera existe para desmentir",
]


def _entre(desde: str, hasta: str) -> str:
    i = FUENTE.index(desde)
    return FUENTE[i:FUENTE.index(hasta, i)]


def test_el_popup_existe_con_el_patron_de_siempre():
    bloque = _entre('<div id="modal-tmserie"', "</div>\n\n<div id=\"modal-condriphoy\"")
    for pieza in ('class="modal-box"', 'class="modal-close"', 'class="modal-eyebrow"',
                  'class="modal-title"', 'id="mSerieLede"', 'id="mSerieNotas"'):
        assert pieza in bloque, pieza
    assert 'role="dialog"' in bloque and 'aria-modal="true"' in bloque


def test_la_vista_lo_ofrece_con_un_boton():
    assert 'id="tmSerieInfo"' in FUENTE
    i = FUENTE.index('id="tmSerieInfo"')
    assert "Cómo se midió" in FUENTE[i:i + 120]


def test_el_boton_abre_y_el_popup_se_cierra_de_las_tres_formas():
    bloque = _entre('var modal = document.getElementById("modal-tmserie")',
                    "// ---- Modal: DRIP Hoy")
    assert 'getElementById("tmSerieInfo")' in bloque
    assert 'classList.add("open")' in bloque
    assert "closeBtn.addEventListener" in bloque
    assert "if (e.target === modal) closeModal()" in bloque
    assert 'e.key === "Escape"' in bloque


def test_en_la_vista_queda_la_frase_que_situa_la_grafica():
    """La sección sigue diciendo qué estás mirando: lo demás es el detalle."""
    i = FUENTE.index('setHtml("tmSerieLede"')
    lede = FUENTE[i:FUENTE.index(");", i)]
    assert "esto es la película" in lede
    palabras = len(re.findall(r"\S+", re.sub(r"<[^>]+>|'|\+", " ", lede)))
    assert palabras <= 40, f"el lede de la vista se quedó en {palabras} palabras"


def test_nada_de_lo_que_salio_de_la_vista_se_perdio():
    """El texto se MUEVE, no se resume: cada frase sigue estando, palabra por palabra."""
    popup = _entre('setHtml("mSerieLede"', '      dibujar();')
    for frase in MOVIDAS:
        assert frase in popup, f"se perdió: {frase}"


def test_el_texto_del_popup_no_adelgaza_sin_que_nadie_lo_note():
    """Las frases ancla no bastan: medido, borrar media frase en medio de un párrafo no
    listado pasaba desapercibido. Esto fija el tamaño del bloque movido.

    Si se edita el texto a propósito, hay que actualizar el número aquí — ese es el
    punto: que el cambio pase por una revisión en vez de colarse.
    """
    popup = _entre('setHtml("mSerieLede"', '      dibujar();')
    limpio = re.sub(r"<[^>]+>", " ", popup)
    limpio = re.sub(r"['\"]\s*\+\s*$", " ", limpio, flags=re.M)
    palabras = len(re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ][\w·%$.,€-]*", limpio))
    assert palabras == 382, (
        f"el bloque del popup tiene {palabras} palabras y antes tenía 382: si lo editaste "
        "a propósito, actualiza el número; si no, se perdió texto")


def test_el_detalle_ya_no_esta_en_la_vista():
    """Si siguiera en los dos sitios, se diría dos veces — justo lo que la regla evita."""
    i = FUENTE.index('setHtml("tmSerieLede"')
    vista = FUENTE[i:FUENTE.index(");", i)]
    for frase in ("Hay seis porque", "capital aportado", "Qué mide la altura"):
        assert frase not in vista, frase


def test_el_hueco_viejo_de_las_notas_ya_no_se_rellena():
    """`tmSerieNotas` sigue en el marcado pero vacío; si alguien lo vuelve a rellenar, el
    texto largo regresa a la vista sin que nadie lo note."""
    assert 'id="tmSerieNotas"' in FUENTE
    assert 'setHtml("tmSerieNotas"' not in FUENTE


def test_el_popup_se_coloca_contra_la_ventana_y_no_contra_el_iframe():
    """El componente vive en un iframe tan alto como su contenido: un modal centrado se
    coloca en el centro de TODO el iframe. Medido: abría cortado por arriba; con el tope
    cae en 20-880 de una ventana de 900."""
    bloque = _entre('var trigger = document.getElementById("tmSerieInfo")',
                    "// ---- Modal: DRIP Hoy")
    assert "window.frameElement" in bloque
    assert "ownerDocument.defaultView.innerHeight" in bloque
    assert "document.documentElement.scrollHeight - box.offsetHeight" in bloque


def test_impuestos_no_se_toco():
    """Medido: 141 palabras, ya cumplía la regla. Tocarlo era inventar trabajo."""
    imp = (COMPONENTE.parent / "impuestos_v2.html").read_text(encoding="utf-8")
    assert "modal-tmserie" not in imp
