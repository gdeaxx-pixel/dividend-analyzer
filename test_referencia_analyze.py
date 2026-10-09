"""La salida completa de `analyze_portfolio` no cambia mientras se parte su cuerpo (F4).

Corre `tools/referencia_analyze.py comparar`: reproduce las 16 corridas desde el cassette, sin
red, y exige 0 diferencias contra la referencia congelada. La referencia vive fuera del repo
(contiene posiciones privadas), así que sin ella el test se salta — en CI siempre. Es una
herramienta para la duración de los cortes, no un guard permanente.
"""
import glob
import os
import subprocess
import sys

import pytest

BASE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.environ.get(
    "DIVIDEND_REFERENCIA_DIR",
    os.path.join(os.path.expanduser("~"), ".local", "share", "dividend-analyzer",
                 "referencia_analyze"))


def test_analyze_portfolio_identico_a_la_referencia():
    if not glob.glob(os.path.join(RAIZ, "*", "referencia.json")):
        pytest.skip(f"sin referencia congelada en {RAIZ} (tools/referencia_analyze.py)")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    r = subprocess.run([sys.executable, os.path.join(BASE, "tools", "referencia_analyze.py"),
                        "comparar", "--limite", "40"],
                       cwd=BASE, env=env, capture_output=True, text=True, timeout=600)
    salida = "\n".join(l for l in (r.stdout + r.stderr).splitlines()
                       if "streamlit.runtime" not in l)
    assert r.returncode == 0, salida
    assert "\n0 diferencias" in "\n" + salida, salida
