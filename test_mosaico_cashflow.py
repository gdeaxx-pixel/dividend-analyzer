"""Mosaico de cuadritos del Cash flow (Daniel, 2026-09-29).

En la pestaña «Mercado» la cascada ya mostraba la subida de SCHB (+$13.37) y el mosaico seguía
en el capital de antes: el mercado solo entraba en el último paso. Y al entrar lo hacía mal —
«Apreciación · $0.00», con el verde del efectivo—. De paso: el texto de la escala era un
literal del demo ($9.66 de un pico de $966.48) para todos los fondos, el techo del adapter no
cubría las sumas que el mosaico apila (MSTY dibujaba 133 cuadritos en una rejilla de 100), y la
cascada usaba ese techo como «bolsillo + bruto» (SCHB: → $1,680.49 en vez de $1,672.54).

Los datos salen de `ui.adapters.cashflow_data`, igual que en la app. Se mide en Chromium.
"""
import json

import pytest

from test_cascada_eje import STATS_MSTY, STATS_SCHB, _stats
from ui import componentes
from ui.adapters import cashflow_data

sync_api = pytest.importorskip("playwright.sync_api")

SCHB = cashflow_data(STATS_SCHB, "SCHB")
# El mismo SCHB con +20% de mercado: una subida que ocupa varios cuadritos.
SCHB_SUBE = cashflow_data(dict(STATS_SCHB, market_value=round(1663.57 * 1.2, 2)), "SCHB")
MSTY = cashflow_data(STATS_MSTY, "MSTY")
# Baja de $3.57: en cuadritos empata (99 contra 99), así que solo el signo de MERCADO dice
# que no hubo subida.
SCHB_BAJA = cashflow_data(dict(STATS_SCHB, market_value=1660.0), "SCHB")
# Bolsillo 97.5 cuadritos y bruto 2.5: el redondeo por pieza suma 101 en el paso 1.
REDONDEO = cashflow_data(_stats(975.0, 25.0, 5.0, 20.0, 20.0, 0.0, 980.0), "ZZZR")
# Efectivo que SALIÓ sin ser dividendo (una comisión): el mosaico lo pinta igual, en valor
# absoluto, así que el techo también tiene que contarlo.
SCHB_COMISION = cashflow_data(dict(STATS_SCHB, misc_cash_total=-30.0,
                                   misc_cash_breakdown={"ADR Mgmt Fee": -30.0}), "SCHB")
CASOS = {"SCHB": SCHB, "SCHB_COMISION": SCHB_COMISION, "SCHB_SUBE": SCHB_SUBE, "MSTY": MSTY, "SCHB_BAJA": SCHB_BAJA,
         "REDONDEO": REDONDEO}
PASO_MERCADO = SCHB["STEP_LABELS"].index("Mercado")

_LEER = """() => {
  const n = {};
  document.querySelectorAll('#grid .sq').forEach(s => {
    const k = s.className.replace('sq ', ''); n[k] = (n[k] || 0) + 1; });
  return {
    n: n, total: document.querySelectorAll('#grid .sq').length,
    leyenda: [...document.querySelectorAll('#legend .leg-txt strong')].map(e => e.textContent),
    surv: document.getElementById('surv').textContent,
    survGana: document.getElementById('surv').classList.contains('surv-gain'),
    nota: document.getElementById('waffleNote').textContent,
    acum: [...document.querySelectorAll('.cap-run')].map(e => e.textContent.trim()).filter(Boolean),
  };
}"""


def test_el_techo_cubre_toda_suma_que_el_mosaico_apila():
    """Estructural, sin navegador: el 100% del mosaico es la mayor pila de cualquier paso."""
    for d in CASOS.values():
        otros = abs(d["OTROS"])
        for pila in (d["POCKET"] + d["BRUTO"],
                     d["POCKET"] + d["DRIP"] + d["CASH"] + otros,
                     d["VALOR_HOY"] + d["CASH"] + otros):
            assert d["PICO"] >= round(pila, 2) - 0.01, (d["ticker"], pila, d["PICO"])


@pytest.fixture(scope="module")
def pasos():
    try:
        with sync_api.sync_playwright() as pw:
            nav = pw.chromium.launch()
            out = {}
            for nombre, datos in CASOS.items():
                for paso in range(len(datos["STEP_LABELS"])):
                    html = componentes._con_tema(componentes._plantilla("cashflow.html"), "Claro")
                    html = (html.replace("{{DATA_JSON}}", json.dumps(datos, ensure_ascii=False))
                                .replace("{{PASO}}", str(paso)))
                    pagina = nav.new_page(viewport={"width": 860, "height": 1400})
                    pagina.set_content("<!doctype html>" + html)
                    pagina.wait_for_timeout(300)
                    out[nombre, paso] = pagina.evaluate(_LEER)
                    pagina.close()
            nav.close()
            return out
    except Exception as error:  # sin Chromium instalado (CI)
        pytest.skip(f"Chromium no disponible: {error}")


@pytest.mark.parametrize("caso", list(CASOS))
def test_ningun_paso_pinta_mas_de_100_cuadritos(pasos, caso):
    for paso in range(len(CASOS[caso]["STEP_LABELS"])):
        assert pasos[caso, paso]["total"] == 100, (caso, paso, pasos[caso, paso]["n"])


def test_la_subida_entra_al_mosaico_en_el_paso_mercado(pasos):
    antes, mercado = pasos["SCHB_SUBE", PASO_MERCADO - 1], pasos["SCHB_SUBE", PASO_MERCADO]
    assert "q-gain" not in antes["n"]
    assert mercado["n"].get("q-gain", 0) >= 15
    # La subida no se pinta con el verde del efectivo: SCHB no cobró efectivo.
    assert "q-cash" not in mercado["n"]
    assert "Subida del mercado · +$%.2f" % SCHB_SUBE["MERCADO"] in mercado["leyenda"]
    assert "hoy valen $120" in mercado["surv"]
    # La franja de la frase sigue el signo: sin el borde rojo de pérdida cuando el fondo sube.
    assert mercado["survGana"] and not antes["survGana"]


def test_una_subida_de_centavos_sigue_en_la_leyenda_con_su_monto(pasos):
    leyenda = pasos["SCHB", PASO_MERCADO]["leyenda"]
    assert "Subida del mercado · +$%.2f" % SCHB["MERCADO"] in leyenda
    assert not any("$0.00" in fila and "Subida" in fila for fila in leyenda)


def test_la_caida_tacha_cuadritos_desde_el_paso_mercado(pasos):
    antes, mercado = pasos["MSTY", PASO_MERCADO - 1], pasos["MSTY", PASO_MERCADO]
    assert "q-sd" not in antes["n"]
    assert mercado["n"].get("q-sd", 0) > 0
    assert "q-gain" not in mercado["n"]
    assert "se destruyeron" in mercado["surv"]
    assert not mercado["survGana"]


def test_la_escala_se_calcula_con_el_pico_del_fondo(pasos):
    for nombre, d in CASOS.items():
        nota = pasos[nombre, 0]["nota"]
        assert "$%.2f" % (d["PICO"] / 100) in nota and "$%.2f" % d["PICO"] in nota, (nombre, nota)


@pytest.mark.parametrize("caso", list(CASOS))
def test_la_cascada_acumula_bolsillo_mas_bruto_no_el_techo(pasos, caso):
    d = CASOS[caso]
    acum = pasos[caso, 2]["acum"]
    assert acum[1] == "$%.2f" % (d["POCKET"] + d["BRUTO"])
    assert acum[2] == "$%.2f" % (d["POCKET"] + d["BRUTO"] - d["IMPUESTO"])


def test_una_baja_de_centavos_no_se_rotula_como_subida(pasos):
    mercado = pasos["SCHB_BAJA", PASO_MERCADO]
    assert SCHB_BAJA["MERCADO"] < 0
    assert "q-gain" not in mercado["n"]
    assert not any("Subida" in fila for fila in mercado["leyenda"])


def test_sin_drip_la_leyenda_no_lo_nombra(pasos):
    """MSTY no reinvierte: la leyenda decía «DRIP · $0.00 · Los 0 siguen vivos»."""
    assert MSTY["DRIP"] == 0
    for paso in range(len(MSTY["STEP_LABELS"])):
        assert not any(fila.startswith("DRIP") for fila in pasos["MSTY", paso]["leyenda"]), paso
    # Con DRIP la fila sigue ahí.
    assert any(fila.startswith("DRIP") for fila in pasos["SCHB", PASO_MERCADO]["leyenda"])
