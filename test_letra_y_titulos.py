"""D2 y D3 de la propuesta de interfaz (2026-10-30): letra de 11 px como mínimo y títulos en
letra normal y en frase normal.

D2 — En 8 componentes cerca de un tercio de los tamaños de letra declarados bajaban de 11 px
(en Cash flow, 34 de 99), y el aviso de validación iba a 9 px. Ahora ninguno baja de 11.

D3 — «La escalera de tus impuestos» y los títulos de Comparación, Método, Metodología y la
Hoja iban en letra de máquina; los pasos de la carga, en mayúsculas espaciadas. Ahora los
títulos van en letra normal y en frase normal; la letra de máquina y las mayúsculas quedan para
cifras y etiquetas pequeñas. Los títulos de los popups no cambian: son el patrón aprobado.

`ui/componentes/impuestos.html` (v1) no se toca: ya no se dibuja y es la referencia congelada del
guard de frases. `metodo_real.html` se genera del demo del artifact: su hoja de estilos cambió en
el demo y se regeneró (lo vigila `test_contrato_componentes.py`).
"""
import os
import re

import pytest

_RAIZ = os.path.dirname(os.path.abspath(__file__))
_COMP = os.path.join(_RAIZ, "ui", "componentes")
_MINIMO = 11


def _leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def _pequenos(texto):
    """Cada tamaño de letra por debajo del mínimo: `font-size: Xpx` y `font-size="X"`."""
    css = [float(x) for x in re.findall(r"font-size:\s*(\d+(?:\.\d+)?)px", texto)]
    svg = [float(x) for x in re.findall(r'font-size="(\d+(?:\.\d+)?)"', texto)]
    return sorted(x for x in css + svg if x < _MINIMO)


_COMPONENTES = sorted(f for f in os.listdir(_COMP)
                      if f.endswith(".html") and f != "impuestos.html")
_ESTILOS_APP = sorted(f for f in os.listdir(os.path.join(_RAIZ, "ui")) if f.endswith(".py"))


@pytest.mark.parametrize("archivo", _COMPONENTES)
def test_ningun_componente_baja_de_11_px(archivo):
    assert _pequenos(_leer(os.path.join(_COMP, archivo))) == [], (
        f"{archivo} declara letra por debajo de {_MINIMO} px")


@pytest.mark.parametrize("archivo", _ESTILOS_APP)
def test_los_estilos_de_la_app_no_bajan_de_11_px(archivo):
    assert _pequenos(_leer(os.path.join(_RAIZ, "ui", archivo))) == [], (
        f"ui/{archivo} declara letra por debajo de {_MINIMO} px")


def _regla(texto, selector):
    m = re.search(r"(?m)^\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", texto)
    assert m, f"no encuentro la regla {selector}"
    return m.group(1)


_TITULOS = [(c, sel) for c in ("cashflow.html", "comparacion.html", "comparacion_real.html",
                                "hoja.html", "metodo.html", "metodo_real.html", "metodologia.html")
            for sel in (".soon-title", ".cmp-title")] + [("impuestos_v2.html", ".imp-title")]


@pytest.mark.parametrize("archivo, selector", _TITULOS)
def test_los_titulos_de_seccion_van_en_letra_normal(archivo, selector):
    regla = _regla(_leer(os.path.join(_COMP, archivo)), selector)
    assert "var(--font-sans)" in regla and "font-mono" not in regla, (
        f"{archivo} {selector} sigue en letra de máquina")


def test_el_titulo_de_cada_paso_de_la_carga_va_en_frase_normal():
    from ui import carga
    regla = _regla(carga.ESTILOS_CARGA, ".vd-bloque-titulo")
    assert "var(--font-sans)" in regla, "el título del paso sigue en letra de máquina"
    assert "uppercase" not in regla, "el título del paso sigue en mayúsculas"
