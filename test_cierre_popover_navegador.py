"""El menú de la ruta se cierra solo al elegir, en un Streamlit de verdad (30-oct-2026).

`test_cierre_popover.py` comprueba el script; este, que el popover de la versión instalada de
Streamlit le hace caso. Es el test que hay que mirar al subir Streamlit: el cierre depende de
cómo el popover detecta un clic de fuera, que no es API pública. Con Streamlit 1.66.1 el
script viejo cerraba 11 de 48 elecciones; nadie lo vio porque ningún test abría el menú.

Arranca `render_ruta` sola (sin vistas ni datos) en un puerto libre y elige cuatro veces
seguidas en el menú, sin ningún otro rerun entre una y otra: es el caso que fallaba. Desde
el 30-oct (P1) las secciones son una fila visible y el único popover que queda es «Ayuda»,
así que las cuatro elecciones alternan sus dos opciones.
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

_RAIZ = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = """
import sys
sys.path.insert(0, {raiz!r})
from ui.chrome import render_ruta
render_ruta(False, None)
"""
_ELECCIONES = ("vd_menu_metodologia", "vd_menu_validacion",
               "vd_menu_metodologia", "vd_menu_validacion")


def _arrancar(script):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(script), "--server.port", str(puerto),
         "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        cwd=_RAIZ, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{puerto}"
    sin_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(240):
        try:
            if sin_proxy.open(url + "/_stcore/health", timeout=1).read() == b"ok":
                return proc, url
        except OSError:
            time.sleep(0.25)
    proc.terminate()
    pytest.fail("Streamlit no arrancó en 60 s")


@pytest.fixture(scope="module")
def cierres(tmp_path_factory):
    script = tmp_path_factory.mktemp("cierre_popover") / "ruta.py"
    script.write_text(_SCRIPT.format(raiz=_RAIZ))
    proc, url = _arrancar(script)
    try:
        with sync_api.sync_playwright() as pw:
            try:
                nav = pw.chromium.launch()
            except Exception as error:  # sin Chromium instalado (CI)
                pytest.skip(f"Chromium no disponible: {error}")
            pagina = nav.new_page()
            pagina.goto(url)
            menu = pagina.locator('[data-testid="stPopoverButton"]').first
            menu.wait_for(timeout=60000)
            resultado = {}
            for n, clave in enumerate(_ELECCIONES):
                if pagina.locator('[data-testid="stPopoverBody"]').count():
                    pagina.keyboard.press("Escape")
                menu.click()
                opcion = pagina.locator(f".st-key-{clave} button")
                opcion.wait_for(state="visible", timeout=10000)
                opcion.click()
                try:
                    pagina.locator('[data-testid="stPopoverBody"]').wait_for(
                        state="detached", timeout=5000)
                    resultado[f"{n}:{clave}"] = True
                except sync_api.TimeoutError:
                    resultado[f"{n}:{clave}"] = False
            nav.close()
            return resultado
    finally:
        proc.terminate()
        proc.wait(10)


def test_el_menu_se_cierra_en_cada_eleccion_seguida(cierres):
    assert cierres == {f"{n}:{clave}": True for n, clave in enumerate(_ELECCIONES)}
