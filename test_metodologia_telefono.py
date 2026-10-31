"""Metodología cabe en el ancho del teléfono (2026-10-30).

A 375 px de viewport (iframe de 343) Metodología se salía 171 px por la derecha: la tabla de
ratios de «8 · Los ratios que sí sirven» tiene `min-width: 480px` y su propio scroll lateral
(`.meth-tbl-wrap`), pero `.meth-grid` usaba `1fr`, que no baja del ancho mínimo de su contenido,
y estiraba TODAS las secciones a 498 px. Con `minmax(0, 1fr)` la columna se ajusta al ancho y la
tabla se desplaza dentro de su caja. Ya pasaba antes de D2 (medido en `main`).

Se monta lo que `render_metodologia` le da a `st.iframe`, en Chromium, a tres anchos de iframe:
teléfono (343), tableta en vertical (707) y escritorio (860).
"""
import pytest

from ui import componentes
from ui.adapters import metodo_data

_MEDIR = """() => {
  const de = document.documentElement, W = de.clientWidth;
  const secciones = [...document.querySelectorAll('.meth-item')];
  const fuera = secciones.filter(s => s.getBoundingClientRect().right > W + 0.5).map(s => s.id);
  const caja = document.querySelector('#mt-ratios .meth-tbl-wrap');
  return {dx: de.scrollWidth - W, n: secciones.length, fuera,
          tablaDesplaza: caja.scrollWidth > caja.clientWidth + 0.5,
          tablaAncho: Math.round(caja.querySelector('table').getBoundingClientRect().width)};
}"""


@pytest.fixture(scope="module")
def medidas():
    sync_api = pytest.importorskip("playwright.sync_api")
    capturado = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(componentes.st, "iframe", lambda doc, height=None: capturado.append(doc))
        componentes.render_metodologia("Claro", anchor=None, datos=metodo_data())
    out = {}
    try:
        with sync_api.sync_playwright() as pw:
            nav = pw.chromium.launch()
            for ancho in (343, 707, 860):
                pagina = nav.new_page(viewport={"width": ancho, "height": 900})
                pagina.set_content(capturado[0])
                pagina.wait_for_timeout(300)
                out[ancho] = pagina.evaluate(_MEDIR)
                pagina.close()
            nav.close()
    except Exception as error:  # sin Chromium instalado (CI)
        pytest.skip(f"Chromium no disponible: {error}")
    return out


@pytest.mark.parametrize("ancho", [343, 707, 860])
def test_metodologia_no_se_sale_del_ancho(medidas, ancho):
    m = medidas[ancho]
    assert m["n"] > 0, "no encontré las secciones de Metodología"
    assert m["fuera"] == [], f"a {ancho} px se salen: {m['fuera']}"
    assert m["dx"] == 0, f"a {ancho} px la página se desplaza {m['dx']} px de lado"


def test_en_el_telefono_la_tabla_de_ratios_se_desplaza_en_su_caja(medidas):
    """La tabla no se aplasta: conserva sus 480 px y se recorre dentro de `.meth-tbl-wrap`."""
    m = medidas[343]
    assert m["tablaAncho"] >= 480
    assert m["tablaDesplaza"]
