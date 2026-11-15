"""Las tres filas de «Por portafolio» se revelan en orden (14-nov).

Las filas —precio, dividendos y el total— ya existían, pero aparecían juntas y había que
reconstruir el orden leyendo. Ahora crecen una a una siguiendo el patrón de
`APPs/Dividend-Analyzer/guia-graficas.md` § «Cómo se revela una gráfica», que Daniel aprobó:
una cosa a la vez, el rótulo cuando su barra para, ~4,5 s, y una sola vez por cifras.

Esto vigila el contrato del componente. Que la animación se vea es cosa del navegador; se
comprobó a mano (clase `narra` aplicada, 6 barras, 2 marcadas como negativas).
"""
import re
from pathlib import Path

import pytest

COMPONENTE = Path(__file__).resolve().parent / "ui" / "componentes" / "portafolios.html"
FUENTE = COMPONENTE.read_text(encoding="utf-8")


def test_el_componente_trae_la_narracion():
    assert "@keyframes wf-crece" in FUENTE
    assert ".narra .wf-bar" in FUENTE, "no hay regla que anime las barras"


@pytest.mark.parametrize("fila, retardo", [(1, "250ms"), (2, "1500ms"), (3, "2750ms")])
def test_cada_fila_espera_a_la_anterior(fila, retardo):
    """Si dos crecieran a la vez, la secuencia dejaría de explicar el orden."""
    # La tercera fila lleva además su propia duración, así que no se exige el cierre inmediato.
    patron = rf"\.narra \.wf-row:nth-of-type\({fila}\) \.wf-bar \{{ animation-delay: {retardo};"
    assert re.search(patron, FUENTE), f"la fila {fila} no arranca en {retardo}"


def test_el_rotulo_llega_cuando_su_barra_para():
    """Primera barra: 250 + 1100 = 1350 ms. Su cifra no puede salir antes."""
    m = re.search(r"\.narra \.wf-row:nth-of-type\(1\) \.wf-v \{ animation-delay: (\d+)ms; \}", FUENTE)
    assert m, "la cifra de la primera fila no tiene retardo"
    assert int(m.group(1)) >= 1350, f"la cifra sale a los {m.group(1)}ms, antes de que pare su barra"


def test_la_barra_negativa_crece_desde_el_cero():
    """Una barra negativa va del cero hacia la izquierda: si creciera desde su extremo
    izquierdo parecería avanzar al revés."""
    assert ".narra .wf-bar.neg { transform-origin: right center; }" in FUENTE
    assert "(r.v < 0 ? ' neg' : '')" in FUENTE, "el JS ya no marca las barras negativas"


def test_se_narra_una_vez_por_cifras_y_no_en_cada_repintado():
    """Streamlit recrea el iframe en cada rerun: sin esto, la animación se repetiría cada vez
    que el cliente toca cualquier cosa de la página."""
    # Mirar que la palabra «sessionStorage» aparezca no basta: con `narra = true` el texto
    # sigue ahí (en el catch y en la firma) y la animación se repetiría en cada rerun. Medido
    # el 14-nov: ese mutante sobrevivía. Se exige la asignación que de verdad decide.
    assert 'narra = sessionStorage.getItem("vd_narra_port") !== firma;' in FUENTE, (
        "`narra` ya no sale de comparar la firma guardada")
    assert "g.retorno, g.precio" in FUENTE, "la firma ya no depende de las cifras"
    asignaciones = [l.strip() for l in FUENTE.splitlines()
                    if l.strip().startswith("narra = ") or l.strip().startswith("let narra")]
    assert "narra = true;" not in asignaciones, "alguien forzó la animación en cada repintado"


def test_sin_sessionStorage_no_se_anima_pero_tampoco_revienta():
    assert re.search(r"catch \(e\) \{ narra = false; \}", FUENTE), (
        "sin el catch, una ventana privada rompería la vista entera")


def test_respeta_el_ajuste_de_movimiento_reducido():
    bloque = FUENTE[FUENTE.index("prefers-reduced-motion"):][:260]
    assert ".narra .wf-bar" in bloque and "animation: none" in bloque
