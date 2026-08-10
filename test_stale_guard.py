"""Tests del guardián anti-stale.

El caso que importa es el que tumbó al guardián anterior: un arreglo DENTRO de una
función que ya existía, sin ningún símbolo nuevo (PR #11, `KeyError: pocket_investment`).
Vigilar la fecha del archivo lo detecta; vigilar símbolos no.
"""

import os

import pytest

import stale_guard


@pytest.fixture(autouse=True)
def _guardian_limpio():
    """Cada test parte sin fechas anotadas y deja el registro como estaba."""
    previas = dict(stale_guard._fechas)
    stale_guard._fechas.clear()
    yield
    stale_guard._fechas.clear()
    stale_guard._fechas.update(previas)


@pytest.fixture
def fecha_restaurada():
    """Permite mover la fecha de un archivo y la devuelve a su valor real al terminar."""
    tocados = {}

    def tocar(ruta, desplazamiento=120):
        if ruta not in tocados:
            tocados[ruta] = (os.path.getatime(ruta), os.path.getmtime(ruta))
        atime, mtime = tocados[ruta]
        os.utime(ruta, (atime, mtime + desplazamiento))

    yield tocar

    for ruta, tiempos in tocados.items():
        os.utime(ruta, tiempos)


def _ruta_de(nombre):
    return stale_guard.modulos_propios()[nombre]


def test_descubre_los_modulos_propios_sin_lista_a_mano():
    """Los 10 módulos de la app se detectan solos; nadie tiene que enumerarlos."""
    import logic  # noqa: F401
    from ui import carga, chrome, pie, vistas  # noqa: F401

    propios = stale_guard.modulos_propios()

    for esperado in ("logic", "ui.adapters", "ui.carga", "ui.chrome", "ui.componentes",
                     "ui.heredadas", "ui.nav", "ui.pie", "ui.tokens", "ui.vistas"):
        assert esperado in propios, f"{esperado} quedó fuera de la vigilancia"


def test_no_vigila_dependencias_ni_a_si_mismo():
    import pandas  # noqa: F401
    import streamlit  # noqa: F401

    propios = stale_guard.modulos_propios()

    assert "pandas" not in propios
    assert "streamlit" not in propios
    assert "stale_guard" not in propios


def test_primera_corrida_solo_toma_nota():
    import logic  # noqa: F401

    assert stale_guard.asegurar_frescura() == []
    assert "logic" in stale_guard._fechas


def test_sin_cambios_no_recarga_nada():
    import logic  # noqa: F401

    stale_guard.asegurar_frescura()

    assert stale_guard.asegurar_frescura() == []


def test_detecta_cambio_sin_simbolo_nuevo(fecha_restaurada):
    """EL CASO DE PR #11: cambia el cuerpo de una función, no aparece ningún símbolo.

    Es lo que el guardián de símbolos no veía. Mover la fecha del archivo equivale a
    cualquier edición: el guardián no mira QUÉ cambió, solo que el disco se movió.
    """
    from ui import adapters  # noqa: F401

    stale_guard.asegurar_frescura()
    fecha_restaurada(_ruta_de("ui.adapters"))

    recargados = stale_guard.asegurar_frescura()

    assert "ui.adapters" in recargados


def test_recarga_todo_el_grafo_no_solo_el_archivo_tocado(fecha_restaurada):
    """Quien hace `from otro import nombre` se queda con el nombre viejo si no se refresca."""
    import logic  # noqa: F401
    from ui import carga, chrome, pie, vistas  # noqa: F401

    stale_guard.asegurar_frescura()
    fecha_restaurada(_ruta_de("logic"))

    recargados = stale_guard.asegurar_frescura()

    for dependiente in ("ui.adapters", "ui.heredadas", "ui.vistas", "ui.chrome"):
        assert dependiente in recargados, f"{dependiente} se quedó con la versión vieja"


def test_recarga_en_orden_de_dependencias(fecha_restaurada):
    """`ui.vistas` importa nombres sueltos de adapters/chrome/componentes: va después."""
    import logic  # noqa: F401
    from ui import carga, chrome, pie, vistas  # noqa: F401

    stale_guard.asegurar_frescura()
    fecha_restaurada(_ruta_de("logic"))

    recargados = stale_guard.asegurar_frescura()

    for antes, despues in (("logic", "ui.adapters"), ("logic", "ui.heredadas"),
                           ("ui.adapters", "ui.vistas"), ("ui.chrome", "ui.vistas"),
                           ("ui.componentes", "ui.vistas"), ("ui.heredadas", "ui.chrome")):
        assert recargados.index(antes) < recargados.index(despues), \
            f"{despues} se recargó antes que {antes}"


def test_deja_de_anotar_lo_que_ya_no_esta_cargado():
    stale_guard._fechas["ui.fantasma"] = 1.0

    stale_guard.asegurar_frescura()

    assert "ui.fantasma" not in stale_guard._fechas


def test_la_app_sigue_viva_despues_de_recargar(fecha_restaurada):
    """Recargar no puede dejar el grafo a medias: los símbolos que usa `app.py` siguen ahí."""
    import logic
    from ui import carga, chrome, pie, vistas

    stale_guard.asegurar_frescura()
    fecha_restaurada(_ruta_de("logic"))
    stale_guard.asegurar_frescura()

    import sys

    assert hasattr(sys.modules["logic"], "classify_roc_health")
    assert hasattr(sys.modules["ui.carga"], "notificar_progreso")
    assert hasattr(sys.modules["ui.chrome"], "inyectar_estilos")
    assert hasattr(sys.modules["ui.pie"], "render_pie")
    assert hasattr(sys.modules["ui.vistas"], "render_vista")


def test_un_modulo_nuevo_no_se_queda_sin_sitio_en_el_orden():
    """Anti-rot: si aparece un módulo propio fuera de `_ORDEN`, hay que ubicarlo a mano.

    Se recargaría igual (al final, que es seguro), pero si importa nombres sueltos de
    otro módulo propio su sitio correcto puede no ser el último. Este test avisa.

    Corre en un subproceso a propósito: dentro de pytest, `sys.modules` acumula lo que
    importan los demás tests (`fetch_roc_19a`, `validate_real_cases`…), que son scripts
    sueltos y no parte de la app. Lo que hay que medir es el grafo que carga `app.py`.
    """
    import json
    import subprocess
    import sys

    sonda = """
import json, sys
import stale_guard
import logic
from ui import carga, chrome, pie, vistas
print(json.dumps(sorted(set(stale_guard.modulos_propios()) - set(stale_guard._ORDEN))))
"""
    salida = subprocess.run(
        [sys.executable, "-c", sonda],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        capture_output=True, text=True, check=True,
    )
    sin_sitio = json.loads(salida.stdout.strip().splitlines()[-1])

    assert not sin_sitio, (
        f"módulos propios sin sitio en stale_guard._ORDEN: {sin_sitio}. "
        "Ubícalos según sus dependencias."
    )
