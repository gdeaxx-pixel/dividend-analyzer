"""Fase 3.3a — `ui.adapters.comparacion_data` (Total Return Graph · Simulación).

Cierra el hueco de tests que dejó un agente que se colgó implementando el cableado a
datos reales (rescatado en el commit `93b9964`, verificado en vivo en el navegador por
Opus). Estos tests NO reimplementan ni recalculan nada: fijan el ground truth que Opus
ya verificó contra la app corriendo, y protegen dos invariantes:

  1. Las cifras de retorno (Con DRIP / Sin DRIP) para los 4 fondos YieldMax con más
     historia — reconciliadas por `backtest.run_backtest` al 0.013% contra el extracto
     real de IB (Fase 3.1).
  2. El hallazgo pedagógico central de toda la remediación: para TSLY el DRIP gana
     (ventaja del efectivo NEGATIVA) y para MSTY el efectivo gana (ventaja POSITIVA).
     Antes del fix (`F`/`shapeOf`/`targetEnd`, ver `git show 93b9964` en
     `ui/componentes/comparacion.html`), las cifras venían de un modelo paramétrico
     inventado que llegaba a tener el signo invertido.

Ver `ui/adapters.py::comparacion_data` para el porqué de cada pieza del JSON.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from ui.adapters import TRG_SUB, TRG_UNIVERSO, TRG_UNIVERSO_REAL, comparacion_data  # noqa: E402

_COMPONENTE = os.path.join(os.path.dirname(__file__), "ui", "componentes", "comparacion.html")

# Ground truth verificado en vivo por Opus (retorno total Con DRIP / Sin DRIP, en %,
# desde la incepción de cada fondo hasta `last`). Ver traspaso de la tarea.
_RETORNO_ESPERADO = {
    #        con DRIP   sin DRIP
    "NVDY": (365.5, 169.4),
    "TSLY": (32.1, 7.8),
    "CONY": (19.8, 79.9),
    "MSTY": (19.4, 133.5),
}

# Ventaja del efectivo (Sin DRIP − Con DRIP, en puntos porcentuales): negativa = el DRIP
# gana, positiva = el efectivo gana. Es el hallazgo pedagógico que justifica la vista.
_VENTAJA_EFECTIVO_ESPERADA = {
    "TSLY": -24.3,
    "MSTY": 114.1,
}


@pytest.fixture(scope="module")
def datos():
    """Una sola corrida de `comparacion_data()` para todo el módulo — cada llamada
    dispara `backtest.run_backtest` sobre 8 tickers x 3 modos (Con DRIP) + 5 x 1
    (Sin DRIP), no es gratis repetirla por test."""
    d = comparacion_data()
    assert d is not None, (
        "comparacion_data() devolvió None — ningún ticker del universo cargó historia "
        "(ni caché ni yfinance en vivo). Sin esto no hay nada que verificar.")
    return d


def _retorno_total(d: dict, tk: str, modo: str, clave_idx: str) -> float:
    """Retorno total (fracción) de `tk` en el modo `modo`, leyendo `d[clave_idx]`
    (`'idx'` para Con DRIP, `'idxSin'` para Sin DRIP) desde la incepción del ticker
    hasta `d['last']` — mismo cálculo que hace `series()`/`seriesSin()` en JS."""
    last, incep = str(d["last"]), str(d["incep"][tk])
    serie = d[clave_idx][modo][tk]
    return serie[last] / serie[incep] - 1.0


# ── Las 8 cifras de la tabla (4 tickers x Con/Sin DRIP) ─────────────────────────────────

class TestRetornoTotalContraGroundTruth:
    """Modo 'bruto' (DRIP bruto, sin retención) — el modo por defecto de la vista.
    Tolerancia de 0.5 pp: generosa frente a la fuente de precio (cierre diario
    remuestreado a fin de mes) pero estrecha para cazar un cableado invertido o una
    serie equivocada, que mueven estas cifras en decenas de puntos, no en decimales.
    """

    @pytest.mark.parametrize("tk", ["NVDY", "TSLY", "CONY", "MSTY"])
    def test_con_drip(self, datos, tk):
        esperado_pct, _ = _RETORNO_ESPERADO[tk]
        obtenido_pct = _retorno_total(datos, tk, "bruto", "idx") * 100.0
        assert obtenido_pct == pytest.approx(esperado_pct, abs=0.5), (
            f"{tk} Con DRIP: esperado {esperado_pct}%, obtenido {obtenido_pct:.1f}%")

    @pytest.mark.parametrize("tk", ["NVDY", "TSLY", "CONY", "MSTY"])
    def test_sin_drip(self, datos, tk):
        _, esperado_pct = _RETORNO_ESPERADO[tk]
        obtenido_pct = _retorno_total(datos, tk, "bruto", "idxSin") * 100.0
        assert obtenido_pct == pytest.approx(esperado_pct, abs=0.5), (
            f"{tk} Sin DRIP: esperado {esperado_pct}%, obtenido {obtenido_pct:.1f}%")


# ── Contraejemplo TSLY/MSTY: el signo de la ventaja del efectivo ────────────────────────

@pytest.mark.parametrize("tk,esperado_pp", sorted(_VENTAJA_EFECTIVO_ESPERADA.items()))
def test_ventaja_efectivo_signo_y_magnitud(datos, tk, esperado_pp):
    """Este test protege el hallazgo pedagógico central de la remediación: NO basta con
    que las cifras existan, el SIGNO tiene que ser el correcto en ambos sentidos. Antes
    del fix, el modelo paramétrico (`shapeOf`/`targetEnd`) llegaba a invertir signos
    (ver docstring de `comparacion_data` y el diff de `93b9964`) — si alguien vuelve a
    romper el cableado (p.ej. invierte `idx`/`idxSin`), este test lo caza aunque las
    otras 8 cifras por casualidad sigan en el rango correcto."""
    con = _retorno_total(datos, tk, "bruto", "idx") * 100.0
    sin = _retorno_total(datos, tk, "bruto", "idxSin") * 100.0
    ventaja_pp = sin - con
    assert ventaja_pp == pytest.approx(esperado_pp, abs=0.5), (
        f"{tk}: ventaja del efectivo esperada {esperado_pp} pp, obtenida {ventaja_pp:.1f} pp")
    if esperado_pp < 0:
        assert ventaja_pp < 0, f"{tk}: el DRIP debe ganar (ventaja negativa), dio {ventaja_pp:.1f} pp"
    else:
        assert ventaja_pp > 0, f"{tk}: el efectivo debe ganar (ventaja positiva), dio {ventaja_pp:.1f} pp"


def test_tsly_y_msty_van_en_direcciones_opuestas(datos):
    """Sanity check adicional, barato de leer: TSLY y MSTY no solo tienen la ventaja del
    efectivo esperada cada uno por su lado, la diferencia entre ambos tiene que tener
    signo opuesto — si un bug futuro moviera las dos en la misma dirección (p.ej. un
    offset global mal aplicado), esto lo caza aunque cada cifra individual quedara
    dentro de tolerancia por casualidad."""
    con_tsly = _retorno_total(datos, "TSLY", "bruto", "idx") * 100.0
    sin_tsly = _retorno_total(datos, "TSLY", "bruto", "idxSin") * 100.0
    con_msty = _retorno_total(datos, "MSTY", "bruto", "idx") * 100.0
    sin_msty = _retorno_total(datos, "MSTY", "bruto", "idxSin") * 100.0
    assert (sin_tsly - con_tsly) < 0 < (sin_msty - con_msty)


# ── Fuente declarada: sin degradados silenciosos ────────────────────────────────────────

def test_fuente_es_cache_para_todo_el_universo(datos):
    assert set(datos["fuente"]) == set(TRG_UNIVERSO)
    for tk in TRG_UNIVERSO:
        assert datos["fuente"][tk] == "cache", (
            f"{tk} no vino de caché ({datos['fuente'][tk]!r}) — con datos de caché "
            "pineados en el repo esto no debería pasar; si pasa, es un degradado real.")


def test_sin_degradados_ni_faltantes(datos):
    assert datos["degradado"] == []
    assert datos["faltantes"] == []


def test_last_es_45_como_verifico_opus(datos):
    # No es una propiedad estructural (podría cambiar si se actualiza el caché de
    # precio con más historia) — lo fijamos porque todo el ground truth de este archivo
    # se calculó contra `last=45`; si esto se mueve, hay que re-derivar la tabla, no
    # solo tocar este número.
    assert datos["last"] == 45


# ── No hay cifras inventadas: el modelo paramétrico viejo no puede reaparecer ───────────

def test_comparacion_html_no_tiene_el_modelo_parametrico_viejo():
    """`comparacion.html` (pre-93b9964) fabricaba la curva con `shapeOf`/`targetEnd` sobre
    un `var F = { NVDY: { price: ... }, ... }` con literales de precio inventados —
    llegó a invertir signos (NVDY +50% inventado vs -34.3% real). Aserción estructural:
    esas tres piezas no pueden reaparecer en el archivo.

    OJO: SÍ existe un `var F = {}` legítimo en el archivo actual (líneas ~1092-1095) que
    arranca vacío y se llena en un loop desde `DATA.incep`/`DATA.grp` — no confundir. Lo
    que se prohíbe es la declaración con literales numéricos inline (`var F = {` seguido
    en la misma expresión de una key con `price:` o similar), no el nombre de variable.
    """
    with open(_COMPONENTE, encoding="utf-8") as f:
        html = f.read()

    assert "function shapeOf" not in html
    assert "function targetEnd" not in html

    # `var F = {` legítimo actual: siempre seguido (modulo espacio) de un `}` que cierra
    # el objeto vacío inmediatamente (se llena después, línea por línea, vía
    # `F[tk] = {...}` dentro de un forEach). El modelo viejo en cambio abría el objeto y
    # metía las keys (tickers) ahí mismo, con un `price:` numérico dentro.
    m = re.search(r"var F\s*=\s*(\{[^;]*?\});", html)
    assert m is not None, "no se encontró la declaración de `var F` — el patrón cambió, revisar a mano"
    assert re.fullmatch(r"\{\s*\}", m.group(1)), (
        f"`var F` ya no arranca vacío, volvió a tener literales inline: {m.group(1)!r}")
    assert "price:" not in html


def test_seriessin_normaliza_series_reales_no_inventadas():
    """`seriesSin` debe leer `DATA.idxSin`/`DATA.precioSin` (poblados desde Python por
    `comparacion_data`) y no fabricar una rampa lineal/senoidal propia."""
    with open(_COMPONENTE, encoding="utf-8") as f:
        html = f.read()
    inicio = html.index("function seriesSin")
    fin = html.index("\n    }", inicio)
    cuerpo = html[inicio:fin]
    assert "DATA.idxSin" in cuerpo
    assert "DATA.precioSin" in cuerpo
    assert "Math.sin" not in cuerpo and "Math.cos" not in cuerpo


# ── Subyacentes (NVDA/TSLA/COIN/MSTR): universo genérico de fondo base ──────────────────

def test_subyacentes_en_el_payload_con_color_grupo_y_par(datos):
    """Un ticker sin color entra al CSS como `background:undefined` y no lo caza nada más."""
    for tk in TRG_SUB:
        assert tk in datos["col"], f"{tk} sin color en TRG_COLORES"
        assert datos["grp"][tk] == "sub", f"{tk} debería ser grupo 'sub'"
    assert datos["par"] == {"NVDY": "NVDA", "TSLY": "TSLA", "CONY": "COIN", "MSTY": "MSTR"}
    assert "CHPY" not in datos["par"], "CHPY no tiene subyacente en ningún mapeo del repo"


def test_idxsin_cubre_todo_el_universo(datos):
    """Desde que cualquier ticker puede ser fondo base, el toggle «Reinversión» necesita
    datos Sin DRIP para los 12 — si falta uno, `seriesSin` recibe undefined y la vista
    revienta al elegirlo como base."""
    for tk in TRG_UNIVERSO:
        for modo in ("bruto", "roc", "plano"):
            assert tk in datos["idxSin"][modo], f"{tk} sin idxSin[{modo}]"
        assert tk in datos["precioSin"], f"{tk} sin precioSin"


def test_la_vista_real_no_arrastra_los_subyacentes():
    """`trg_real_data` comparte constantes con `comparacion_data`. Si volviera a usar
    TRG_UNIVERSO bajaría 4 tickers x 3 modos que su HTML nunca dibuja, y los listaría en su
    aviso «Sin datos»."""
    for tk in TRG_SUB:
        assert tk not in TRG_UNIVERSO_REAL


@pytest.mark.parametrize("tk", ["TSLA", "COIN", "MSTR"])
def test_accion_sin_dividendos_es_indiferente_al_drip_y_al_modo(datos, tk):
    """Invariante independiente de las cifras: sin distribuciones no hay nada que reinvertir
    ni que retener, así que las 4 series (Con/Sin DRIP x 3 modos) tienen que coincidir. Caza
    un cableado cruzado sin depender de un número transcrito."""
    assert tk in datos["sin_dividendos"], f"{tk} no debería tener dividendos en el caché"
    con = _retorno_total(datos, tk, "bruto", "idx")
    assert _retorno_total(datos, tk, "bruto", "idxSin") == pytest.approx(con, abs=1e-9)
    for modo in ("roc", "plano"):
        assert _retorno_total(datos, tk, modo, "idx") == pytest.approx(con, abs=1e-9)


def test_nvda_si_paga_dividendo_y_la_retencion_se_nota(datos):
    """El contraejemplo de la prueba anterior: NVDA sí distribuye (poco), así que el modo con
    retención tiene que rendir estrictamente menos. Si diera igual, la retención no se estaría
    aplicando a ningún ticker."""
    assert "NVDA" not in datos["sin_dividendos"]
    assert _retorno_total(datos, "NVDA", "bruto", "idx") > _retorno_total(datos, "NVDA", "plano", "idx")


# Ventaja del efectivo (Sin DRIP − Con DRIP, pp) de los ETFs de crecimiento, medida el
# 2026-08-18 contra el caché pineado. Es el contraste pedagógico con MSTY (+114.1): en un
# fondo que aprecia, reinvertir gana por poco; en uno con el NAV colapsado, el efectivo gana
# por mucho.
_VENTAJA_EFECTIVO_GROWTH = {"SCHB": -3.2, "XLK": -3.5, "SMH": -9.2}


@pytest.mark.parametrize("tk,esperado_pp", sorted(_VENTAJA_EFECTIVO_GROWTH.items()))
def test_growth_sin_drip_pierde_por_poco(datos, tk, esperado_pp):
    con = _retorno_total(datos, tk, "bruto", "idx") * 100.0
    sin = _retorno_total(datos, tk, "bruto", "idxSin") * 100.0
    ventaja_pp = sin - con
    assert ventaja_pp == pytest.approx(esperado_pp, abs=0.5), (
        f"{tk}: ventaja del efectivo esperada {esperado_pp} pp, obtenida {ventaja_pp:.1f} pp")
    assert ventaja_pp < 0, f"{tk}: en un ETF de crecimiento el DRIP debe ganar"
