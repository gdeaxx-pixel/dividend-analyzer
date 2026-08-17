"""Guardián anti-stale: obliga a que el código en memoria sea el del disco.

EL PROBLEMA. Streamlit Cloud reescribe los archivos al desplegar, pero no siempre
reinicia el proceso. Cuando no lo hace, `sys.modules` conserva el bytecode viejo y
`import x` es un no-op: la app sirve código antiguo con archivos nuevos. Se reconoce
porque el traceback mezcla números de línea del archivo VIEJO con texto del NUEVO
(una función apuntando a un comentario recién escrito). Pasó dos veces el 2026-08-10
(PR #10 y #11) y en ambas hubo que hacer «Reboot app» a mano.

POR QUÉ NO SE VIGILAN SÍMBOLOS. El guardián anterior (`app_old.py:31-41`) miraba si a
`logic` le faltaba alguna función de una lista escrita a mano. Eso falla de tres formas,
las tres ya observadas:
  1. Solo ve símbolos NUEVOS. Un arreglo dentro de una función existente —el caso más
     común— es invisible. PR #11 fue exactamente eso más un helper privado.
  2. La lista hay que alimentarla en cada PR. Nadie lo hace, y envejece en silencio.
  3. Se perdió entera en el port, junto con los 9 módulos que el guardián no cubría.
Comparar la fecha del archivo no tiene ninguno de esos problemas: detecta cualquier
cambio, no hay lista que mantener y los módulos se descubren solos.

CÓMO FUNCIONA. Tras importar, `asegurar_frescura()` anota la fecha de modificación de
cada archivo propio ya cargado. En las corridas siguientes las vuelve a leer: si alguna
cambió, el disco se movió por debajo del proceso y se recargan TODOS los módulos
vigilados, en orden de dependencias. Equivale a un «Reboot app» automático.

Se recarga todo y no solo lo que cambió a propósito: un módulo que hace
`from otro import nombre` se queda con el `nombre` viejo aunque su propio archivo no se
haya tocado, así que refrescarlo es parte del arreglo.

Los módulos que se importan tarde (dentro de una función) no necesitan vigilancia para
la corrida en que aparecen: un import que ocurre por primera vez SIEMPRE lee del disco.
Quedan registrados a partir de ese momento.
"""

from __future__ import annotations

import importlib
import os
import sys

_RAIZ = os.path.dirname(os.path.abspath(__file__))

# Un módulo va DESPUÉS de aquellos de los que importa nombres sueltos: `reload` re-ejecuta
# los `from X import y`, y esos solo traen la versión nueva si `X` ya se refrescó.
# Lo que no esté aquí se recarga al final, que es el lugar seguro por defecto —
# `test_stale_guard.py` avisa cuando aparece un módulo nuevo sin sitio asignado.
_ORDEN = (
    "logic", "storage", "report", "demo_mode", "backtest", "price_cache",
    # `ui.estado` va antes que sus consumidores (carga, vistas, heredadas): es el dueño de
    # las claves de sesión compartidas, y recargarlo después dejaría a los demás apuntando
    # al módulo viejo.
    "ui.tokens", "ui.estado", "ui.nav", "ui.componentes", "ui.heredadas", "ui.adapters",
    "ui.chrome", "ui.carga", "ui.pie", "ui.validacion", "ui.vistas",
)

# módulo → fecha del archivo cuando lo cargamos. Vive aquí y no en `st.session_state`
# porque el estado de sesión nace vacío en cada visita: una sesión abierta después del
# despliegue anotaría las fechas nuevas como si fueran las suyas y no vería nada raro.
# Este módulo, en cambio, persiste en `sys.modules` mientras el proceso viva.
_fechas: dict[str, float] = {}


def modulos_propios() -> dict[str, str]:
    """Módulos ya cargados cuyo código vive en este repo (no dependencias, no este archivo).

    Los tests quedan fuera: no forman parte de la app desplegada y recargarlos en mitad
    de una corrida de pytest solo confunde al runner.
    """
    encontrados = {}
    for nombre, modulo in list(sys.modules.items()):
        if nombre == __name__ or modulo is None:
            continue
        archivo = getattr(modulo, "__file__", None)
        if not archivo:
            continue
        ruta = os.path.abspath(archivo)
        if not ruta.startswith(_RAIZ + os.sep) or f"{os.sep}.venv{os.sep}" in ruta:
            continue
        base = os.path.basename(ruta)
        if base.startswith("test_") or base == "conftest.py":
            continue
        encontrados[nombre] = ruta
    return encontrados


def _orden_de_recarga(nombre: str) -> int:
    return _ORDEN.index(nombre) if nombre in _ORDEN else len(_ORDEN)


def asegurar_frescura() -> list[str]:
    """Recarga los módulos si el disco cambió bajo el proceso. Devuelve los recargados.

    En la primera corrida solo toma nota; no hay con qué comparar todavía.
    """
    actuales = modulos_propios()

    movidos = []
    for nombre, ruta in actuales.items():
        try:
            fecha = os.path.getmtime(ruta)
        except OSError:
            continue
        if nombre in _fechas and _fechas[nombre] != fecha:
            movidos.append(nombre)
        _fechas[nombre] = fecha

    for nombre in list(_fechas):
        if nombre not in actuales:
            del _fechas[nombre]

    if not movidos:
        return []

    recargados = []
    for nombre in sorted(actuales, key=_orden_de_recarga):
        modulo = sys.modules.get(nombre)
        if modulo is None:
            continue
        try:
            importlib.reload(modulo)
        except Exception:
            # Un módulo que no puede recargarse no debe tumbar la app: sigue sirviendo
            # su versión vieja, que es exactamente lo que hacía sin guardián.
            continue
        recargados.append(nombre)
        try:
            _fechas[nombre] = os.path.getmtime(actuales[nombre])
        except OSError:
            pass

    return recargados
