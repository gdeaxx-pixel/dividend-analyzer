"""Cascada del Cash flow: eje cortado y cero scroll vertical (Daniel, 2026-09-28).

Con el eje en $0, un fondo que se movió poco frente a su capital (SCHB: ~$38 sobre ~$1,680)
dibujaba pasos de 1–3 px bajo anclas de 300. Ahora, si el recorrido cabe en una franja
estrecha, el eje arranca por debajo del mínimo y las anclas llevan zigzag. Aparte, el rótulo
«Lo que pusiste» y la caption «+ $3.55 Cash In Lieu» se salían de `.fall-scroll`, que por su
`overflow-x: auto` sacaba barra vertical (413 vs 404, medido en vivo).

Se mide con Chromium real: lo que importa es la geometría que pinta el JS, no el texto.
Esperados literales medidos el 2026-09-28 a 860 px (ancho del iframe en escritorio).
"""
import json

import pytest

from ui import componentes

sync_api = pytest.importorskip("playwright.sync_api")

_BASE = {"ticker": "SCHB", "POCKET": 1642.66, "BRUTO": 29.88, "IMPUESTO": 8.97, "NETO": 20.91,
         "DRIP": 20.91, "CASH": 0.0, "OTROS": 3.55, "OTROS_DETALLE": {"Cash In Lieu": 3.55},
         "TOTAL_TRABAJANDO": 1663.57, "MERCADO": 13.37, "VALOR_HOY": 1676.94,
         "CAPITAL_ACTUAL": 1680.49, "RESULTADO": 37.83, "PICO": 1672.54,
         "STEP_LABELS": ["Bolsillo", "Div. bruto", "Imp. NRA", "Reinv + Efvo", "Bols + DRIP",
                         "Mercado", "Cap. actual", "Resultado"],
         "impuesto_base": "gross_withheld", "impuesto_momento": "al cobro",
         "devolucion_estimada": 0.0, "devolucion_es_estimacion": True,
         "devolucion_momento": "annual_reclass_estimate", "tasa_declarada": False,
         "tasa_pais": None, "tasa_pct": None, "drip_sin_fuente": False}
# MSTY del demo IB: el NAV se hundió (20,245 → 4,092). Recorrido amplio: el eje sigue en $0.
_AMPLIO = dict(_BASE, ticker="MSTY", POCKET=20245.83, BRUTO=7224.59, IMPUESTO=545.52,
               NETO=6679.07, DRIP=0.0, CASH=6679.07, OTROS=0.0, OTROS_DETALLE={},
               TOTAL_TRABAJANDO=20245.83, MERCADO=-16153.33, VALOR_HOY=4092.5,
               CAPITAL_ACTUAL=10771.57, RESULTADO=-9474.26, PICO=20245.83)
# El mismo MSTY con +$30,156 en cada nivel: el recorrido ($22,832) es el 40% del techo. Aquí
# la fórmula de la base NO se anula sola (daría $20,000), así que es el umbral `CORTE_MAX`
# el único que impide cortar un recorrido que ya se ve bien desde $0.
_K = 30156
_MEDIO = dict(_AMPLIO, **{k: _AMPLIO[k] + _K for k in
                          ("POCKET", "TOTAL_TRABAJANDO", "VALOR_HOY", "CAPITAL_ACTUAL", "PICO")})

_MEDIR = """() => {
  const fs = document.querySelector('.fall-scroll');
  return {
    eje: (document.querySelector('.eje-corte') || {}).textContent || null,
    cortes: document.querySelectorAll('.seg.cut').length,
    segs: [...document.querySelectorAll('.seg')].map(e => [
      e.className.replace(/\\bseg\\b|\\bsettled\\b/g, '').trim(),
      Math.round(parseFloat(e.style.bottom)), Math.round(parseFloat(e.style.height))]),
    sobraY: fs.scrollHeight - fs.clientHeight,
    techo: Math.max(...[...document.querySelectorAll('.seg')].map(e =>
      Math.round(parseFloat(e.style.bottom) + parseFloat(e.style.height)))),
  };
}"""


def _html(datos):
    html = componentes._con_tema(componentes._plantilla("cashflow.html"), "Claro")
    return (html.replace("{{DATA_JSON}}", json.dumps(datos, ensure_ascii=False))
                .replace("{{PASO}}", "7"))


@pytest.fixture(scope="module")
def medidas():
    try:
        with sync_api.sync_playwright() as pw:
            nav = pw.chromium.launch()
            out = {}
            for nombre, datos, ancho in (("corto", _BASE, 860), ("amplio", _AMPLIO, 860),
                                         ("medio", _MEDIO, 860),
                                         ("movil", _BASE, 390)):
                pagina = nav.new_page(viewport={"width": ancho, "height": 1200})
                pagina.set_content("<!doctype html>" + _html(datos))
                pagina.wait_for_timeout(300)
                out[nombre] = pagina.evaluate(_MEDIR)
                pagina.close()
            nav.close()
            return out
    except Exception as error:  # sin Chromium instalado (CI)
        pytest.skip(f"Chromium no disponible: {error}")


def test_recorrido_corto_corta_el_eje_y_los_pasos_se_ven(medidas):
    m = medidas["corto"]
    assert m["eje"] == "Eje desde $1,610"
    assert m["cortes"] == 3  # Tu bolsillo, Capital trabajando y Resultado real
    segs = {cls: (b, h) for cls, b, h in m["segs"]}
    assert segs["s-transito"] == (139, 127)  # Dividendo bruto: +$29.88 → 127 px (antes 3)
    assert segs["s-loss"] == (228, 38)       # Impuesto NRA: −$8.97
    assert segs["s-drip"] == (139, 89)       # DRIP dentro de Capital trabajando


def test_recorrido_amplio_deja_el_eje_en_cero(medidas):
    m = medidas["amplio"]
    assert m["eje"] is None and m["cortes"] == 0
    # Bolsillo $20,245.83 sobre un techo de $26,924.90 (neto + efectivo cobrado) → 226 px.
    assert m["segs"][0] == ["s-anchor", 0, 226]


def test_recorrido_medio_no_se_corta(medidas):
    assert medidas["medio"]["eje"] is None and medidas["medio"]["cortes"] == 0


@pytest.mark.parametrize("caso", ["corto", "amplio"])
def test_ninguna_barra_se_sale_del_grafico(medidas, caso):
    """La escala tomaba `PICO` como techo, pero en MSTY el efectivo cobrado lo supera: la
    barra llegaba a 400 px en un gráfico de 300 y `.fall-scroll` la recortaba por arriba
    (medido con la versión de main). El techo es ahora el máximo real del recorrido."""
    assert medidas[caso]["techo"] <= 300


@pytest.mark.parametrize("caso", ["corto", "amplio", "movil"])
def test_la_cascada_no_saca_scroll_vertical(medidas, caso):
    assert medidas[caso]["sobraY"] <= 0
