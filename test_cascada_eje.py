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
from ui.adapters import cashflow_data

sync_api = pytest.importorskip("playwright.sync_api")


def _stats(pocket, bruto, impuesto, neto, drip, cash, valor_hoy, otros=0.0, detalle=None):
    """`stats` mínimos de `analyze_portfolio` para `cashflow_data`. Los datos del componente
    salen del adapter, no escritos a mano: un dict copiado a mano traía `PICO = 1672.54`
    (bolsillo + bruto) mientras el adapter publica 1680.49 para SCHB, y la cascada que
    dependía de esa coincidencia pasaba en verde con las columnas mal dibujadas en la app."""
    return {"pocket_investment": pocket, "dividends_gross_total": bruto,
            "dividends_net_total": neto, "withheld_tax_total": impuesto,
            "dividends_collected_drip": drip, "dividends_cash_net": cash,
            "market_value": valor_hoy, "misc_cash_total": otros,
            "misc_cash_breakdown": detalle or {}}


# SCHB del demo Schwab (medido 2026-09-28): +$13.37 de mercado y $3.55 de Cash In Lieu.
STATS_SCHB = _stats(1642.66, 29.88, 8.97, 20.91, 20.91, 0.0, 1676.94, 3.55, {"Cash In Lieu": 3.55})
# MSTY del demo IB: el NAV se hundió (20,245 → 4,092). Recorrido amplio: el eje sigue en $0.
STATS_MSTY = _stats(20245.83, 7224.59, 545.52, 6679.07, 0.0, 6679.07, 4092.5)
_BASE = cashflow_data(STATS_SCHB, "SCHB")
_AMPLIO = cashflow_data(STATS_MSTY, "MSTY")
# El mismo MSTY con +$30,156 en el bolsillo y en el valor de hoy: el recorrido es ~40% del
# techo, así que es el umbral `CORTE_MAX` el único que impide cortar un recorrido que ya se
# ve bien desde $0.
_K = 30156
_MEDIO = cashflow_data(dict(STATS_MSTY, pocket_investment=20245.83 + _K,
                            market_value=4092.5 + _K), "MSTY")

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
    # Bolsillo $20,245.83 sobre un techo de $27,470.42 (bolsillo + bruto) → 221 px. Antes
    # medía 226 porque la columna del bruto salía con alto cero y el techo lo ponía el neto.
    assert m["segs"][0] == ["s-anchor", 0, 221]


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
