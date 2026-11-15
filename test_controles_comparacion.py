"""Los controles de Comparación, en dos columnas (14-nov).

Medido en la app: de los 485 px que había entre las pestañas y la gráfica, 212 eran los
cuatro campos de control apilados —fondo base, supuesto de reinversión, crecimiento y
otros YieldMax—, más que el título, el lede y el veredicto juntos. En dos columnas ocupan
120 px y la gráfica sube a 351.

En el teléfono vuelven a una sola columna (`auto-fit`), sin desborde horizontal: medido a
390 px de ancho.
"""
import re
from pathlib import Path

import pytest

COMPONENTES = Path(__file__).resolve().parent / "ui" / "componentes"
USAN = ["comparacion.html", "comparacion_real.html"]

_REGLA = re.compile(r"\.cmp-controls \{([^}]*)\}")


def _regla(nombre: str) -> str:
    m = _REGLA.search((COMPONENTES / nombre).read_text(encoding="utf-8"))
    assert m, f"{nombre}: ya no está la regla de .cmp-controls"
    return m.group(1)


@pytest.mark.parametrize("nombre", USAN)
def test_los_controles_van_en_rejilla_no_apilados(nombre):
    cuerpo = _regla(nombre)
    assert "display: grid" in cuerpo, "volvieron a apilarse"
    assert "flex-direction: column" not in cuerpo


@pytest.mark.parametrize("nombre", USAN)
def test_la_segunda_columna_cabe_en_el_panel(nombre):
    """Con un mínimo muy ancho, `auto-fit` se queda en una sola columna y el cambio no
    sirve de nada. El panel mide ~780 px en escritorio."""
    m = re.search(r"repeat\(auto-fit,\s*minmax\((\d+)px", _regla(nombre))
    assert m, "ya no es un auto-fit con minmax"
    assert int(m.group(1)) <= 340, f"{m.group(1)}px de mínimo: no caben dos columnas"


@pytest.mark.parametrize("nombre", USAN)
def test_en_el_telefono_vuelven_a_una_columna(nombre):
    """`auto-fit` + `minmax` lo hace solo, pero una columna fija lo rompería."""
    m = re.search(r"grid-template-columns:\s*([^;]+)", _regla(nombre))
    assert m and "auto-fit" in m.group(1), m.group(1) if m else "sin grid-template-columns"


def test_las_copias_del_bloque_no_divergen():
    """El CSS de Comparación está copiado en varios componentes (los extractores quedaron
    desarmados). Si una copia se queda atrás, el próximo que la mire creerá que así es."""
    vivos = {p.name: _REGLA.search(p.read_text(encoding="utf-8"))
             for p in COMPONENTES.glob("*.html") if p.name != "metodo_real.html"}
    cuerpos = {n: m.group(1).strip() for n, m in vivos.items() if m}
    assert len(set(cuerpos.values())) == 1, (
        "las copias de .cmp-controls dejaron de ser iguales: "
        + ", ".join(sorted(cuerpos)))
