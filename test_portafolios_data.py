"""Tests de `ui.adapters.portafolios_data` y del render del componente Portafolios v3.

Pytest puro con fixtures de dicts sintéticos (cifras inventadas, números redondos):
`_agregados` lee `pocket_investment`, `market_value`, `dividends_net_total` /
`dividends_collected_cash`, `net_profit` y el filtro `_tiene_datos`, así que no hace
falta correr `analyze_portfolio`. Desde E1 (`fix/retorno-total-net-profit`) el retorno
total sale de `net_profit` con acceso duro `[]` — medido por Opus: las 24 posiciones
reales lo traen siempre y el único llamador de producción pasa por `analyze_portfolio`,
así que el contrato duro es correcto y son los fixtures los que deben declararlo.
Toda cifra esperada se calcula a mano aquí — nunca con la función auditada (trampa 3
del traspaso).
"""
import json

import pytest

from ui.adapters import _veredicto_portafolio, portafolios_data
from ui.heredadas import _agregados


def _stats(inv, mv, neto, bruto=None, net_profit=None):
    """Un ticker analizado mínimo. `bruto` distinto de `neto` simula la convención
    Schwab (bruto al cobro, retención en fila aparte) que `_agregados` resuelve.

    `net_profit` es el campo que E1 convirtió en contrato duro de `_agregados` para el
    retorno total. Si no se pasa, cae a `mv + neto - inv` (la fórmula pre-E1), que es lo
    que los tests que no miran `retorno` necesitan. Los fixtures que SÍ vigilan el
    retorno lo pasan siempre DISTINTO de `mv + neto - inv`: si coincidiera, un `_agregados`
    que volviera a la fórmula vieja pasaría en verde sin vigilar nada (mismo patrón que
    el test de E1, 1234 vs 1000)."""
    s = {"pocket_investment": inv, "market_value": mv, "dividends_net_total": neto}
    s["dividends_collected_cash"] = neto if bruto is None else bruto
    s["net_profit"] = mv + neto - inv if net_profit is None else net_profit
    return s


# ── Fixture base: un grupo por modo, convención Schwab (neto != cash) ──────────────

RESULTADOS = {
    "GROW": _stats(1000, 1200, 10, bruto=20, net_profit=180),    # mode_b — crecimiento
    "YIEL": _stats(2000, 1800, 300, bruto=400, net_profit=50),   # mode_a — dividendos
}
CLASSIFY = {"GROW": "mode_b", "YIEL": "mode_a"}


def _grupo(datos, clave):
    for g in datos["grupos"]:
        if g["clave"] == clave:
            return g
    raise AssertionError(f"grupo {clave!r} ausente")


def test_grupo_coincide_con_agregados():
    """Los agregados del grupo salen de `_agregados` (neto por fila), NO de
    `dividends_collected_cash` (bruto en Schwab). Cifras esperadas escritas a mano y
    además comparadas contra `_agregados`, que es la fuente auditada de la vista."""
    datos = portafolios_data(RESULTADOS, CLASSIFY)

    # Orden de grupos: crecimiento primero (el componente dibuja en este orden).
    assert datos["grupos"][0]["clave"] == "crec"
    assert datos["grupos"][1]["clave"] == "div"

    inv_e, mv_e, div_e, tr_e, pct_e = _agregados(RESULTADOS, ["GROW"])
    g = _grupo(datos, "crec")
    assert g["nombre"] == "Crecimiento"
    assert g["invertido"] == pytest.approx(inv_e) == 1000
    assert g["mv"] == pytest.approx(mv_e) == 1200
    # El punto del test: neto (10), no el bruto de Schwab (20).
    assert g["dividendos"] == pytest.approx(div_e) == 10
    assert g["retorno"] == pytest.approx(tr_e) == 180        # net_profit declarado (E1)
    assert g["retorno_pct"] == pytest.approx(pct_e) == 18.0  # 180/1000
    assert g["precio"] == pytest.approx(200)                 # mv − inv

    inv_d, mv_d, div_d, tr_d, _ = _agregados(RESULTADOS, ["YIEL"])
    d = _grupo(datos, "div")
    assert d["nombre"] == "Dividendos"
    assert (d["invertido"], d["mv"], d["dividendos"], d["retorno"]) == (
        pytest.approx((inv_d, mv_d, div_d, tr_d)))
    assert d["dividendos"] == 300  # neto, no 400

    assert datos["total_mv"] == pytest.approx(mv_e + mv_d) == 3000


def test_excluye_sin_datos_y_mv_cero():
    """Tickers `skipped`/con error no entran al grupo; fondos con `market_value` ≤ 0
    (o nulo) no entran a la lista de fondos aunque el ticker tenga datos."""
    resultados = {
        "GROW": _stats(1000, 1200, 0),
        "DEAD": {"skipped": True, "reason": "held_less_than_14_days"},
        "ERRA": {"error": "No market data"},
        "ZERO": _stats(500, 0, 0),        # con datos, pero mv = 0
    }
    classify = {"GROW": "mode_b", "DEAD": "mode_b", "ERRA": "mode_b",
                "ZERO": "mode_b"}
    datos = portafolios_data(resultados, classify)

    g = _grupo(datos, "crec")
    tickers = [f["ticker"] for f in g["fondos"]]
    assert tickers == ["GROW"]
    # Los excluidos de la lista de fondos tampoco contaminan los agregados: DEAD/ERRA
    # no llegan a `_agregados`; ZERO/NULA sí (tienen datos) pero suman mv = 0.
    assert g["mv"] == pytest.approx(1200)


def test_pcts_de_fondos_suman_100():
    resultados = {
        "AAA": _stats(100, 600, 0),
        "BBB": _stats(100, 300, 0),
        "CCC": _stats(100, 100, 0),
        "DDD": _stats(100, 1000, 0),
    }
    classify = {"AAA": "mode_b", "BBB": "mode_b", "CCC": "mode_a", "DDD": "mode_a"}
    datos = portafolios_data(resultados, classify)

    pcts = [f["pct"] for g in datos["grupos"] for f in g["fondos"]]
    assert sum(pcts) == pytest.approx(100.0)
    assert sum(g["pct"] for g in datos["grupos"]) == pytest.approx(100.0)
    assert datos["total_mv"] == pytest.approx(2000)

    # Orden por mv descendente dentro del grupo.
    crec = _grupo(datos, "crec")
    assert [f["ticker"] for f in crec["fondos"]] == ["AAA", "BBB"]
    # Sin redondear en Python (redondea el JS).
    assert crec["fondos"][1]["pct"] == pytest.approx(15.0)
    assert _grupo(datos, "div")["fondos"][0]["pct"] == pytest.approx(50.0)


def test_un_solo_grupo():
    resultados = {"YIEL": _stats(2000, 1800, 300)}
    datos = portafolios_data(resultados, {"YIEL": "mode_a"})

    assert len(datos["grupos"]) == 1
    g = datos["grupos"][0]
    assert g["clave"] == "div"
    assert g["pct"] == pytest.approx(100.0)
    assert datos["total_mv"] == pytest.approx(1800)


def test_sin_grupos_devuelve_none():
    assert portafolios_data({}, {}) is None
    # Todos skipped → ningún grupo utilizable.
    resultados = {"DEAD": {"skipped": True, "reason": "held_less_than_14_days"}}
    assert portafolios_data(resultados, {"DEAD": "mode_a"}) is None


# ── Veredictos: una fixture por rama ───────────────────────────────────────────────

def test_veredicto_precio_explica_70_o_mas():
    # share = round(80/100*100) = 80 ≥ 70 → el precio manda.
    v = _veredicto_portafolio(precio=80, dividendos=20, retorno=100, invertido=1000)
    assert v == ("El 80% del resultado viene del precio. Los dividendos son un extra.")


def test_veredicto_precio_explica_menos_de_70():
    # share = round(30/100*100) = 30 < 70.
    v = _veredicto_portafolio(precio=30, dividendos=70, retorno=100, invertido=1000)
    assert v == "El precio aporta el 30% del resultado; los dividendos, el resto."


def test_veredicto_cubre_con_margen():
    # dividendos (250) > caída (100); retorno/invertido = 0.15 ≥ 0.10 → sin «poco margen».
    # El 0.15 va a propósito entre 0.10 y 0.20: si alguien mueve el umbral a 0.20,
    # este test debe morir (mutante 2 del traspaso).
    v = _veredicto_portafolio(precio=-100, dividendos=250, retorno=150, invertido=1000)
    assert v == "El precio cayó 10%. Los dividendos cubren esa caída."


def test_veredicto_cubre_con_poco_margen():
    # dividendos == caída exacta (100 == 100): con `>` estricto esto diría «no alcanzan»
    # (mutante 1 del traspaso). retorno/invertido = 0 < 0.10 → «con poco margen».
    v = _veredicto_portafolio(precio=-100, dividendos=100, retorno=0, invertido=1000)
    assert v == "El precio cayó 10%. Los dividendos cubren esa caída, con poco margen."


def test_veredicto_no_alcanza():
    # dividendos (50) < caída (100).
    v = _veredicto_portafolio(precio=-100, dividendos=50, retorno=-50, invertido=1000)
    assert v == "El precio cayó 10% y los dividendos no alcanzan a cubrirlo."


def test_veredicto_invertido_cero_o_negativo_devuelve_none():
    assert _veredicto_portafolio(precio=50, dividendos=10, retorno=60, invertido=0) is None
    assert _veredicto_portafolio(precio=50, dividendos=10, retorno=60, invertido=-100) is None


def test_veredicto_precio_plano_sin_retorno_devuelve_none():
    # precio ≥ 0 y retorno == 0 → nada que explicar (y evitaría dividir por cero).
    assert _veredicto_portafolio(precio=0, dividendos=0, retorno=0, invertido=1000) is None


# ── Render del componente ──────────────────────────────────────────────────────────

def test_render_portafolios_inyecta_datos_y_tema(monkeypatch):
    from ui import componentes

    capturado = {}

    def _spy(html, height=None, scrolling=None):
        capturado["html"] = html
        capturado["height"] = height
        capturado["scrolling"] = scrolling

    monkeypatch.setattr(componentes.components, "html", _spy)
    datos = portafolios_data(RESULTADOS, CLASSIFY)
    componentes.render_portafolios(datos, "Oscuro")

    html = capturado["html"]
    assert "{{" not in html, "quedó un placeholder sin sustituir"
    assert 'data-theme", "dark"' in html, "el tema no llegó al iframe (lo pone _con_tema)"
    # El JSON inyectado parsea y trae las cifras del adapter.
    inicio = html.index("const DATA = ") + len("const DATA = ")
    fin = html.index(";\n", inicio)
    payload = json.loads(html[inicio:fin])
    assert payload["total_mv"] == pytest.approx(3000)
    assert payload["grupos"][0]["clave"] == "crec"
    assert capturado["height"] == componentes.ALTO_PORTAFOLIOS
    assert capturado["scrolling"] is False
