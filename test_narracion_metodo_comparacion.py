"""La narración llega a Comparación y a Método, cada una como decidió la guía (14-nov).

`APPs/Dividend-Analyzer/guia-graficas.md` § «Cómo se revela una gráfica» dice, vista por
vista:

- Comparación: **solo la aparición**, nunca el trazado de la línea — una línea
  dibujándose se lee como el dinero avanzando, y aquí las series ya están completas.
- Método · La matriz: **solo el momento en que la hoja duplica el dividendo**, que es la
  demostración del error; la matriz entera, no.

Y en las dos, una vez por visita: los chips y las pestañas se pulsan muchas veces, y lo
que se ve muchas veces no se anima.

Comprobado en la app local: en Comparación el rótulo y la cifra ya están a 1 cuando las
barras y la gráfica siguen a 0, y acaban las cuatro en 1. En La matriz, el puente pasa de
0 a 1 después de que se dibujen los bordes de las dos columnas.
"""
import re
from pathlib import Path

import pytest

COMPONENTES = Path(__file__).resolve().parent / "ui" / "componentes"
COMPARACION = ["comparacion.html", "comparacion_real.html"]


def _fuente(nombre):
    return (COMPONENTES / nombre).read_text(encoding="utf-8")


def _retardo(fuente, selector):
    """El `animation-delay` del selector.

    Un mismo selector sale dos veces: en la lista que declara la animación para todos y
    luego en su regla propia con el retardo. Por eso no vale la primera que aparece.
    """
    reglas = [m for m in re.finditer(re.escape(selector) + r"\s*\{([^}]*)\}", fuente)]
    assert reglas, f"no está la regla de «{selector}»"
    for m in reglas:
        d = re.search(r"animation-delay:\s*(\d+)ms", m.group(1))
        if d:
            return int(d.group(1))
    pytest.fail(f"«{selector}» no tiene retardo en ninguna de sus {len(reglas)} reglas")


# ── Comparación ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("nombre", COMPARACION)
def test_comparacion_revela_en_el_orden_en_que_se_lee(nombre):
    f = _fuente(nombre)
    pasos = [".narra-v .v-kick", ".narra-v .v-big", ".narra-v .v-sub",
             ".narra-v .io-row:nth-of-type(1)", ".narra-v .io-row:nth-of-type(2)",
             ".narra-v .cmp-note", ".narra-v .cmp-plot-wrap"]
    retardos = [_retardo(f, s) for s in pasos]
    assert retardos == sorted(retardos), f"el orden no es el de lectura: {retardos}"
    assert retardos[0] > 0 and retardos[-1] <= 5000, retardos


@pytest.mark.parametrize("nombre", COMPARACION)
def test_comparacion_no_traza_la_linea(nombre):
    """Lo que la guía prohíbe aquí: dibujar la serie como si el dinero avanzara."""
    f = _fuente(nombre)
    bloque = f[f.index("@keyframes cmp-entra"):f.index("@media (prefers-reduced-motion", f.index("@keyframes cmp-entra"))]
    assert "stroke-dash" not in bloque and "cmp-svg" not in bloque, bloque[:200]


@pytest.mark.parametrize("nombre", COMPARACION)
def test_comparacion_se_narra_una_vez_por_visita(nombre):
    f = _fuente(nombre)
    assert re.search(r'var _clave = "vd_narra_cmp_\w+";', f), "sin clave propia de la vista"
    assert "sessionStorage.getItem(_clave)" in f and "sessionStorage.setItem(_clave" in f
    assert 'classList.add("narra-v")' in f


@pytest.mark.parametrize("nombre", COMPARACION)
def test_comparacion_sin_sessionStorage_no_revienta(nombre):
    f = _fuente(nombre)
    i = f.index("vd_narra_cmp_")
    assert "try {" in f[i - 400:i] and "catch (e)" in f[i:i + 400]


@pytest.mark.parametrize("nombre", COMPARACION)
def test_comparacion_respeta_el_movimiento_reducido(nombre):
    f = _fuente(nombre)
    i = f.index("@keyframes cmp-entra")
    bloque = f[i:i + 1400]
    j = bloque.index("@media (prefers-reduced-motion")
    assert "animation: none" in bloque[j:]


def test_las_dos_pestanas_de_comparacion_no_comparten_la_marca():
    """Real y Simulación son dos pantallas: si compartieran clave, ver una dejaría la otra
    sin narrar."""
    claves = {re.search(r'"(vd_narra_cmp_\w+)"', _fuente(n)).group(1) for n in COMPARACION}
    assert len(claves) == 2, claves


# ── Método · La matriz ────────────────────────────────────────────────────────────────

def test_metodo_narra_la_duplicacion_en_dos_pasos():
    """Primero los bordes de las dos columnas que la hoja suma, después el puente que las
    une en el Total."""
    f = _fuente("metodo.html")
    marca = _retardo(f, ".narra-dup .he-h.he-mark .he-lab")
    puente = _retardo(f, ".narra-dup .he-bridge")
    assert marca < puente, f"el puente llega antes que las columnas ({marca} vs {puente})"
    assert puente <= 3000, puente


def test_metodo_no_anima_la_matriz_entera():
    """La guía pide el momento del error, no la tabla: si se animan las filas, vuelve a
    ser una gráfica que se dibuja sola."""
    f = _fuente("metodo.html")
    reglas = re.findall(r"\.narra-dup ([^{]+)\{", f)
    for r in reglas:
        assert "he-r" not in r and "he-c" not in r, f"también anima las celdas: {r}"


def test_metodo_se_narra_una_vez_por_visita():
    f = _fuente("metodo.html")
    assert 'sessionStorage.getItem("vd_narra_metodo_dup")' in f
    assert 'sessionStorage.setItem("vd_narra_metodo_dup", "1")' in f
    assert 'classList.add("narra-dup")' in f


def test_metodo_solo_marca_el_bloque_con_drip():
    """Una narración por pantalla: «Sin DRIP» cuenta lo mismo y duplicarla sería ruido."""
    f = _fuente("metodo.html")
    assert 'getElementById("tmConDripBlock")' in f
    assert 'classList.add("narra-dup")' in f
    assert f.count('classList.add("narra-dup")') == 1


def test_metodo_respeta_el_movimiento_reducido():
    f = _fuente("metodo.html")
    i = f.index("@keyframes dup-marca")
    bloque = f[i:i + 900]
    assert "@media (prefers-reduced-motion" in bloque
    assert "animation: none" in bloque[bloque.index("@media (prefers-reduced-motion"):]
