"""El gris de las notas cumple el contraste mínimo para letra pequeña (C3 del piloto, 13-nov).

Medido antes de tocarlo, con los colores del sistema sobre los tres fondos claros: 4.06 sobre
`ground`, 4.36 sobre `panel` y **3.94** sobre `panel-tint`. Lo recomendado para texto pequeño
es 4.5:1, y ese gris lo llevan la mayoría de las notas de 12-13 px. El tema oscuro ya cumplía
(5.17 en el peor fondo), así que solo se tocó el claro.

El guard calcula el contraste desde los tokens: si alguien aclara el gris o oscurece un fondo,
sale rojo. No mide texto por texto contra la pantalla — eso no lo cubre esta prueba.
"""
import pytest

from ui import tokens

MINIMO = 4.5
FONDOS = ("ground", "panel", "panel-tint")


def _luminancia(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    canales = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    canales = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * canales[0] + 0.7152 * canales[1] + 0.0722 * canales[2]


def _contraste(a: str, b: str) -> float:
    alta, baja = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (alta + 0.05) / (baja + 0.05)


def _paleta(tema: str) -> dict:
    """Los dos diccionarios de `ui/tokens.py`, por el fondo que usan."""
    for nombre in dir(tokens):
        valor = getattr(tokens, nombre)
        if isinstance(valor, dict) and "ink-mut" in valor and "ground" in valor:
            claro = not valor["ground"].startswith("#0")
            if (tema == "claro") == claro:
                return valor
    raise AssertionError(f"no encontré la paleta del tema {tema}")


def test_el_contraste_de_referencia_esta_bien_calculado():
    """Dos anclas conocidas: negro sobre blanco es 21:1 y un color contra sí mismo, 1:1.
    Sin esto, un error en la fórmula haría pasar los demás tests por la razón equivocada."""
    assert _contraste("#000000", "#ffffff") == pytest.approx(21, abs=0.01)
    assert _contraste("#6a7b8a", "#6a7b8a") == pytest.approx(1, abs=0.001)


@pytest.mark.parametrize("tema", ["claro", "oscuro"])
@pytest.mark.parametrize("fondo", FONDOS)
def test_las_notas_se_leen_sobre_los_tres_fondos(tema, fondo):
    paleta = _paleta(tema)
    razon = _contraste(paleta["ink-mut"], paleta[fondo])
    assert razon >= MINIMO, (
        f"tema {tema}: el gris de las notas da {razon:.2f}:1 sobre «{fondo}», "
        f"por debajo de {MINIMO}:1 para letra pequeña")


@pytest.mark.parametrize("tema", ["claro", "oscuro"])
def test_el_gris_de_las_notas_sigue_siendo_mas_claro_que_el_texto_normal(tema):
    """Subir el contraste no puede acabar con la jerarquía: la nota se distingue del cuerpo."""
    paleta = _paleta(tema)
    assert _contraste(paleta["ink-mut"], paleta[FONDOS[0]]) < _contraste(
        paleta["ink-2"], paleta[FONDOS[0]]), "la nota dejó de verse secundaria"
