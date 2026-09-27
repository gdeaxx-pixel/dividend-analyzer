"""El script de auto-alto (`tools/_auto_alto.py`) corre de verdad en Node contra un iframe y
un contenedor de juguete.

Por qué existe: con Streamlit 1.52 el `stElementContainer` que envuelve cada
`components.html` toma `flex: 0 0 <alto de Python>` y ya no sigue al iframe. Medido el
2026-09-26 en el navegador con `?demo=schwab`: Portafolios pinta 1160 px dentro de un
contenedor de 2400 px, así que quedan ~1240 px de hueco. Ningún test de texto lo ve; este
ejecuta el script y mira el estilo que deja en el contenedor.
"""
import glob
import json
import os
import subprocess

import pytest

_RAIZ = os.path.dirname(os.path.abspath(__file__))

import sys
sys.path.insert(0, os.path.join(_RAIZ, "tools"))
from _auto_alto import AUTO_ALTO_JS  # noqa: E402

_JS = AUTO_ALTO_JS.replace("<script>", "").replace("</script>", "")

# Contenedor e iframe de juguete. `setInterval` no se deja correr: el arnés llama a
# `__vdAjustarAlto` a mano para no depender de temporizadores.
_ARNES = """
var cont = { style: { flexBasis: "2400px" } };
var fe = { parentElement: cont, style: {}, attrs: {},
           setAttribute: function (k, v) { this.attrs[k] = v; } };
var window = { frameElement: fe, addEventListener: function () {} };
var document = { body: { scrollHeight: 1160 } };
function setTimeout() {}
function setInterval() {}
%s
var r = { tras_cargar: cont.style.flexBasis, iframe: fe.style.height };
cont.style.flexBasis = "2400px";           // un rerun de Streamlit reescribe el contenedor
window.__vdAjustarAlto();
r.tras_rerun = cont.style.flexBasis;
document.body.scrollHeight = 900;           // el contenido encoge (p. ej. se cierra un panel)
window.__vdAjustarAlto();
r.tras_encoger = cont.style.flexBasis;
r.iframe_tras_encoger = fe.style.height;
console.log(JSON.stringify(r));
"""


def _correr(js):
    r = subprocess.run(["node", "-e", _ARNES % js], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_el_contenedor_sigue_al_iframe_tambien_despues_de_un_rerun():
    r = _correr(_JS)
    assert r == {
        "tras_cargar": "1160px",
        "iframe": "1160px",
        "tras_rerun": "1160px",
        "tras_encoger": "900px",
        "iframe_tras_encoger": "900px",
    }


@pytest.mark.parametrize("ruta", sorted(glob.glob(os.path.join(_RAIZ, "ui", "componentes", "*.html"))),
                         ids=os.path.basename)
def test_cada_componente_lleva_el_auto_alto_vigente(ruta):
    """Los extractores interpolan `AUTO_ALTO_JS`; los componentes sin extractor lo llevan
    copiado. Si una copia se queda con la versión vieja, ese componente vuelve a dejar
    hueco con Streamlit 1.52."""
    with open(ruta, encoding="utf-8") as f:
        html = f.read()
    if "window.frameElement" not in html:
        pytest.skip("componente sin auto-alto")
    assert AUTO_ALTO_JS in html
