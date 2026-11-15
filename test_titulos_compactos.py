"""C4 — títulos y cifras compactos (pedido de Daniel, 13-nov; aplicado el 14-nov).

Medido en la app antes de tocar nada: los títulos de sección salían a 26 px (Portafolios,
Riesgo, «Lo que toca vigilar») y a 24 px (Impuestos, Comparación), y las cifras de sección
a 43 px — por encima de la respuesta principal de la página, que mide 34. La jerarquía
estaba al revés: lo más grande de la pantalla no era la respuesta.

Los topes salen del piloto que Daniel aprobó (`demos/propuesta-ui-2026-11-13.html`): la
cifra respuesta llega a 40 px y las de sección se quedan en 26-28.

Qué NO vigila esto: que la página sea más corta. Se midió y el ahorro es pequeño (27 px en
Portafolios, 57 en Riesgo); el espacio está en otro sitio —en Comparación, 212 px de
controles apilados— y eso es otro cambio.
"""
import re
from pathlib import Path

import pytest

COMPONENTES = Path(__file__).resolve().parent / "ui" / "componentes"

# `metodo_real.html` lo GENERA `tools/extract_metodo_real.py` desde el demo del vault
# (`test_contrato_componentes::test_los_contratos_vivos_siguen_pasando_su_check`): se
# compacta cambiando el demo y regenerando, no a mano. Por eso queda fuera.
GENERADOS = {"metodo_real.html"}

# Las clases de título que SÍ se usan en el marcado. `soon-title` (27 px) no aparece en
# ningún `class=`: es CSS muerto y vigilarlo solo daría ruido.
TITULOS = {"card-title", "sec-title", "cmp-title", "imp-title", "title"}

TOPE_TITULO = 21   # título de sección
TOPE_CIFRA = 34    # la respuesta principal de una pantalla; las de sección, 28

_REGLA = re.compile(r"([^\n{}]+)\{([^}]*)\}")
_FS = re.compile(r"font-size:\s*([^;]+)")


def _editables():
    return [p for p in sorted(COMPONENTES.glob("*.html")) if p.name not in GENERADOS]


def _tamaños(ruta):
    """(selector, texto del font-size, px máximo) de cada regla con tamaño."""
    for m in _REGLA.finditer(ruta.read_text(encoding="utf-8")):
        fs = _FS.search(m.group(2))
        if not fs:
            continue
        px = [int(x) for x in re.findall(r"(\d+)px", fs.group(1))]
        if px:
            yield m.group(1).strip(), fs.group(1).strip(), max(px)


@pytest.mark.parametrize("ruta", _editables(), ids=lambda p: p.name)
def test_ningun_titulo_de_seccion_pasa_de_21px(ruta):
    for selector, texto, px in _tamaños(ruta):
        clases = set(re.findall(r"\.([a-z0-9-]+)", selector))
        if clases & TITULOS and px > TOPE_TITULO:
            pytest.fail(f"{ruta.name}: «{selector}» a {px}px ({texto}); el tope es "
                        f"{TOPE_TITULO}px — ver feedback_titulos-compactos")


@pytest.mark.parametrize("ruta", _editables(), ids=lambda p: p.name)
def test_ninguna_cifra_pasa_de_la_respuesta_principal(ruta):
    """Una sola cifra grande por pantalla. Si una de sección crece por encima de 34, vuelve
    a tapar a la respuesta."""
    for selector, texto, px in _tamaños(ruta):
        if px > TOPE_CIFRA:
            pytest.fail(f"{ruta.name}: «{selector}» a {px}px ({texto}); el tope es "
                        f"{TOPE_CIFRA}px")


def test_las_dos_cifras_de_portafolio_son_mas_pequenas_que_el_total():
    """Portafolios lleva tres cifras: el valor de mercado en el centro de la dona y el
    retorno de cada portafolio. El total manda."""
    fuente = (COMPONENTES / "portafolios.html").read_text(encoding="utf-8")
    centro = re.search(r"\.c-v \{[^}]*font-size:\s*(\d+)px", fuente)
    tarjeta = re.search(r"\.big \.num \{[^}]*font-size:\s*clamp\([^)]*?(\d+)px\s*\)", fuente)
    assert centro and tarjeta, "cambiaron los selectores de las cifras"
    assert int(tarjeta.group(1)) < int(centro.group(1)), (
        f"la cifra de cada portafolio ({tarjeta.group(1)}px) no puede ser mayor que el "
        f"valor de mercado ({centro.group(1)}px)")


def test_riesgo_tambien_baja_su_titulo_en_pantalla_estrecha():
    """La regla del `@media` pisaba a la general: sin bajarla también, el teléfono se
    quedaba con el título viejo."""
    fuente = (COMPONENTES / "riesgo.html").read_text(encoding="utf-8")
    estrecho = re.findall(r"@media[^{]*\{[^@]*?\.title \{ font-size: (\d+)px", fuente, re.S)
    assert estrecho, "ya no está la regla estrecha de .title"
    assert all(int(px) <= TOPE_TITULO for px in estrecho), estrecho
