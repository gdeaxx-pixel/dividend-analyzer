"""El `flex-basis` inline que deja el auto-alto no puede estirar a un elemento sin iframe.

Por qué existe: `tools/_auto_alto.py` fija `flex-basis` INLINE en el `stElementContainer` de
cada `components.html`. Al cambiar de vista, React reutiliza ese nodo para el elemento que
cae en la misma posición y le cambia la clase, pero el inline se queda. Medido el
2026-09-28 en el navegador: el primer párrafo del aviso de bloqueo medía 170 px con 51 de
texto, y en Portafolios un título de 14 px ocupaba 170. La regla de `ui/chrome.py` lo anula.

Se mide con un motor CSS real (Chromium vía Playwright): lo que hay que probar es que el
`!important` le gana al inline y que el `:has(iframe)` deja en paz al contenedor del
iframe. Un test que busque el texto de la regla no ve ninguna de las dos cosas.
"""
import pytest

from ui.chrome import _ESTILOS

sync_api = pytest.importorskip("playwright.sync_api")

# Réplica mínima del DOM de Streamlit 1.52: columna flex, alto del iframe fijado por CLASE
# (`flex: 0 0 2400px`, lo que Streamlit pone con el alto de Python) y el inline del auto-alto.
_HTML = """<!doctype html><html><head><style>
  .bloque { display: flex; flex-direction: column; }
  .iframe-st { height: 2400px; flex: 0 0 2400px; }
  .md-st { height: auto; }
  p { margin: 0; height: 51px; }
  iframe { display: block; height: 719px; border: 0; }
  %s
</style></head><body><div class="bloque">
  <div id="con-iframe" data-testid="stElementContainer" class="iframe-st"
       style="flex-basis: 719px;"><iframe></iframe></div>
  <div id="parrafo" data-testid="stElementContainer" class="md-st"
       style="flex-basis: 170px;"><p>texto</p></div>
</div></body></html>"""


@pytest.fixture(scope="module")
def altos():
    try:
        with sync_api.sync_playwright() as pw:
            nav = pw.chromium.launch()
            pagina = nav.new_page()
            pagina.set_content(_HTML % _ESTILOS)
            medidos = pagina.evaluate(
                "() => Object.fromEntries(['con-iframe', 'parrafo'].map(id =>"
                " [id, document.getElementById(id).getBoundingClientRect().height]))")
            nav.close()
            return medidos
    except Exception as error:  # sin Chromium instalado (CI)
        pytest.skip(f"Chromium no disponible: {error}")


def test_un_parrafo_no_hereda_el_alto_del_iframe_anterior(altos):
    assert altos["parrafo"] == 51


def test_el_contenedor_del_iframe_sigue_al_auto_alto(altos):
    assert altos["con-iframe"] == 719
