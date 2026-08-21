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
import backtest  # noqa: E402
import logic  # noqa: E402
import price_cache  # noqa: E402
from ui.adapters import (  # noqa: E402
    _CMP_CAPITAL, _CMP_FLAT_RATE, _politica_fiscal, _tasa_efectiva_neta,
    TRG_MODOS, TRG_SUB, TRG_UNIVERSO, TRG_UNIVERSO_REAL, TRG_YM, comparacion_data)

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
def corrida():
    """Una sola corrida de `comparacion_data()` para todo el módulo — cada llamada dispara
    `backtest.run_backtest` sobre 12 tickers x 3 modos x 2 (Con/Sin DRIP), no es gratis
    repetirla por test.

    De paso ESPÍA lo que el adaptador le pasa al motor. El espía no cuesta una corrida
    extra —envuelve la que ya se hacía— y es lo que permite assertar sobre la POLÍTICA
    FISCAL recibida y no solo sobre el número que sale: un modelo fiscal equivocado puede
    producir cifras plausibles, y de hecho lo hizo durante meses (ver
    `TestUnSoloModeloRoc`)."""
    llamadas = []
    original = backtest.run_backtest

    def espia(ticker, **kw):
        # `history` queda fuera del registro a propósito: es un DataFrame por ticker y lo
        # que aquí se vigila es la política fiscal, no la fuente de precio (de eso ya se
        # ocupa `test_fuente_es_cache_para_todo_el_universo`).
        llamadas.append({"ticker": ticker, "drip": kw.get("drip"),
                         "nra_rate": kw.get("nra_rate", 0.0),
                         "roc_pct_by_year": dict(kw.get("roc_pct_by_year") or {})})
        return original(ticker, **kw)

    backtest.run_backtest = espia
    try:
        d = comparacion_data()
    finally:
        backtest.run_backtest = original

    assert d is not None, (
        "comparacion_data() devolvió None — ningún ticker del universo cargó historia "
        "(ni caché ni yfinance en vivo). Sin esto no hay nada que verificar.")
    assert llamadas, "el espía no registró ninguna corrida — `comparacion_data` dejó de usar el motor"
    return d, llamadas


@pytest.fixture(scope="module")
def datos(corrida):
    return corrida[0]


@pytest.fixture(scope="module")
def llamadas(corrida):
    return corrida[1]


@pytest.fixture(scope="module")
def con_avisos_19a():
    """Los tickers del universo que sí publican avisos 19(a) — los únicos que pueden tener
    escudo ROC. Se lee del yaml vivo, no de una lista transcrita: si mañana CHPY empieza a
    publicar, los guardas lo incorporan solos en vez de quedarse mudos sobre él."""
    roc19a = logic.load_roc_19a()
    return tuple(tk for tk in TRG_UNIVERSO if _politica_fiscal(tk, "roc", roc19a).roc_pct_by_year)


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


# ════════════════════════════════════════════════════════════════════════════════════════
# Un solo modelo del escudo ROC (migración 2026-08-21)
# ════════════════════════════════════════════════════════════════════════════════════════
# Hasta esta fecha `comparacion_data` simulaba el modo «roc» con la tasa EFECTIVA
# (`_tasa_efectiva_neta`: 0.30 × (1 − ROC)), o sea metiendo el escudo dentro de la tasa —
# lo que asume que aplica al cobro y que el dinero nunca sale del fondo. «La matriz» ya
# había migrado al modelo exacto (retención del 30% completo + reembolso que llega con el
# 1042-S, PR #59), así que la misma app decía «Con NRA · ROC 19a» en dos secciones con dos
# modelos distintos.
#
# Ninguno de los guardas de abajo se puede satisfacer reimplementando la fórmula que
# genera el dato: o miran lo que el motor RECIBE (el espía del fixture), o cruzan el
# payload contra una corrida independiente, o son propiedades estructurales.


@pytest.fixture(scope="module")
def corridas_ym(con_avisos_19a):
    """Corridas directas del motor para los fondos con avisos 19(a): el lado independiente
    de las reconciliaciones. `viejo_con` reproduce a propósito el modelo retirado (tasa
    efectiva, sin reembolso) para poder medir cuánto separaba a los dos."""
    roc19a = logic.load_roc_19a()
    out = {}
    for tk in con_avisos_19a:
        h = price_cache.load_history(tk).history.sort_index()
        start = h.index.min()

        def corre(modo, drip, exacto=True):
            pol = _politica_fiscal(tk, modo, roc19a)
            kw = {"roc_pct_by_year": pol.roc_pct_by_year} if exacto else {}
            rate = pol.rate if exacto else _tasa_efectiva_neta(tk, modo, roc19a)
            return backtest.run_backtest(tk, start_date=start, initial_capital=_CMP_CAPITAL,
                                         drip=drip, nra_rate=rate, history=h, **kw)

        out[tk] = {
            "roc_con": corre("roc", True), "roc_sin": corre("roc", False),
            "bruto_con": corre("bruto", True), "plano_con": corre("plano", True),
            "viejo_con": corre("roc", True, exacto=False),
        }
    return out


def _retorno_de(r) -> float:
    """Retorno total de una corrida medido como lo mide el payload: contra el `total_value`
    del PRIMER día, no contra `initial_capital` (`_mensualizar_desde` fija el primer bin en
    el valor real de arranque — ver `_CMP_CAPITAL`)."""
    return float(r.daily["total_value"].iloc[-1]) / float(r.daily["total_value"].iloc[0]) - 1.0


class TestUnSoloModeloRoc:
    """Lo que el motor RECIBE, que es donde vive el modelo. Un modelo fiscal equivocado
    produce cifras plausibles —la app enseñó las del modelo viejo durante meses sin que
    ningún test protestara—, así que estos guardas no miran el resultado."""

    def test_ninguna_corrida_recibe_una_tasa_efectiva(self, llamadas):
        """La firma del modelo viejo es una tasa ESTRICTAMENTE entre 0 y 30%: el escudo
        disuelto dentro de la retención (8.7% en MSTY, 17.6% en NVDY). Con el modelo exacto
        solo existen dos tasas al cobro —0% o el 30% completo— y el escudo viaja aparte."""
        efectivas = sorted({(c["ticker"], round(c["nra_rate"], 4)) for c in llamadas
                            if 0.0 < c["nra_rate"] < _CMP_FLAT_RATE})
        assert not efectivas, (
            f"volvió el escudo ROC dentro de la tasa: {efectivas}. La retención al cobro es "
            f"0.0 o {_CMP_FLAT_RATE}; el ROC se reclama por año con `roc_pct_by_year`.")
        assert {round(c["nra_rate"], 4) for c in llamadas} <= {0.0, round(_CMP_FLAT_RATE, 4)}

    def test_el_escudo_solo_acompana_a_la_retencion_completa(self, llamadas):
        """Reclamar ROC presupone haber retenido: un reembolso sobre una tasa ya rebajada
        devolvería dos veces el mismo dinero."""
        for c in llamadas:
            if c["roc_pct_by_year"]:
                assert c["nra_rate"] == pytest.approx(_CMP_FLAT_RATE), (
                    f"{c['ticker']}: reclama ROC {sorted(c['roc_pct_by_year'])} sobre una "
                    f"retención de {c['nra_rate']} — el reembolso quedaría duplicado")

    def test_los_fondos_con_avisos_19a_reclaman_su_roc(self, llamadas, con_avisos_19a):
        """Huella del reembolso, del lado de la entrada: si alguien revierte al modelo de
        tasa efectiva, `roc_pct_by_year` se va vacío para todos y esto lo caza."""
        assert con_avisos_19a, (
            "ningún ticker del universo publica avisos 19(a) — revisar "
            "`knowledge/roc_19a.yaml`, sin eso el modo «roc» no tiene nada que simular")
        con_escudo = {c["ticker"] for c in llamadas if c["roc_pct_by_year"]}
        assert set(con_avisos_19a) <= con_escudo, (
            f"sin escudo ROC en {sorted(set(con_avisos_19a) - con_escudo)} pese a tener "
            "avisos 19(a) en el yaml")
        # Con DRIP y sin DRIP: las dos corridas del modo «roc», no solo la que se ve primero.
        for tk in con_avisos_19a:
            drips = {c["drip"] for c in llamadas if c["ticker"] == tk and c["roc_pct_by_year"]}
            assert drips == {True, False}, f"{tk}: el escudo solo llegó a {drips}"

    def test_sin_avisos_19a_no_se_inventa_escudo(self, llamadas, con_avisos_19a):
        """El contraejemplo de la prueba anterior: un ETF de crecimiento no reclasifica
        nada, así que su modo «roc» tiene que ser idéntico al plano."""
        for c in llamadas:
            if c["ticker"] not in con_avisos_19a:
                assert not c["roc_pct_by_year"], (
                    f"{c['ticker']} no publica avisos 19(a) y aun así recibió "
                    f"{c['roc_pct_by_year']}")


class TestReconciliacionConElMotor:
    """El payload contra una corrida directa. La cadena que se verifica es la del contrato
    (Regla 3): `_politica_fiscal` → motor → JSON, sin nada que reescale por el camino."""

    def test_la_serie_roc_es_la_del_modelo_exacto(self, datos, corridas_ym):
        for tk, r in corridas_ym.items():
            for clave, corrida in (("idx", r["roc_con"]), ("idxSin", r["roc_sin"])):
                assert _retorno_total(datos, tk, "roc", clave) == pytest.approx(
                    _retorno_de(corrida), abs=1e-3), (
                    f"{tk}/{clave}: el payload no cuadra con una corrida hecha con la misma "
                    "política fiscal — alguien reescala fuera del motor")

    def test_el_reembolso_del_1042s_esta_dentro_de_la_serie(self, datos, corridas_ym):
        """Huella del reembolso, del lado de la salida. La cuenta por cobrar viva a la fecha
        de corte solo existe si se retuvo el 30% completo y el escudo vuelve DESPUÉS; con el
        modelo de tasa efectiva es cero por construcción. Como el test de arriba ancla el
        payload a esta misma corrida, la huella está en lo que se dibuja."""
        for tk, r in corridas_ym.items():
            assert r["roc_con"].roc_receivable_final > 0, (
                f"{tk}: sin cuenta por cobrar — el ROC volvió a aplicarse al cobro")
            assert r["roc_con"].roc_refund_total > 0, (
                f"{tk}: ningún reembolso llegó a cobrarse en todo el horizonte")

    def test_los_dos_modelos_no_son_equivalentes(self, corridas_ym):
        """Fija la lección, no la cifra (Regla 5 del contrato): que exista al menos un fondo
        donde meter el escudo en la tasa cambie el resultado de forma material. Si un día
        ninguno lo ilustra, esto avisa en vez de romper — puede ser el mercado, no un bug."""
        brechas = {tk: abs(_retorno_de(r["roc_con"]) - _retorno_de(r["viejo_con"])) * 100.0
                   for tk, r in corridas_ym.items()}
        assert max(brechas.values()) > 2.0, (
            f"los dos modelos del ROC dan casi lo mismo en todo el universo: {brechas}. No "
            "es necesariamente un bug —la brecha depende de cuánto ROC y cuánta caída haya "
            "habido—, pero el copy que enseña «el retraso importa» se queda sin ejemplo.")


class TestMonotoniaFiscalEstructural:
    """Qué es invariante al subir el impuesto, y qué NO.

    **Invariante:** sin reinversión el impuesto solo resta efectivo —las acciones son las
    mismas en los tres modos, así que también lo son las distribuciones brutas— y la TASA
    efectivamente pagada crece con la severidad del régimen en los dos mundos.

    **NO invariante, y a propósito no se asserta:** que el RESULTADO con DRIP caiga al subir
    el impuesto. Con reinversión el impuesto cambia el CAMINO: se reinvierte menos y parte
    del dinero vuelve más tarde, a otro precio. Ver `test_el_contraejemplo_sigue_vivo`.
    """

    @pytest.mark.parametrize("tk", TRG_UNIVERSO)
    def test_sin_drip_el_regimen_mas_severo_nunca_rinde_mas(self, datos, tk):
        r = {m: _retorno_total(datos, tk, m, "idxSin") for m in TRG_MODOS}
        recado = (f"{tk} viola monotonicidad fiscal sin DRIP: {r}. Retener no puede "
                  "enriquecer cuando no hay camino que alterar.")
        assert r["bruto"] >= r["roc"] - 1e-9, recado
        assert r["roc"] >= r["plano"] - 1e-9, recado

    def test_la_tasa_pagada_crece_con_la_severidad(self, corridas_ym):
        """La forma estructural de «más impuesto» con DRIP: no el importe —que depende del
        camino, porque un escenario que compone más cobra más dividendos y paga más— sino la
        TASA sobre lo cobrado. Esa es 0, 30 × (1 − ROC) y 30% por construcción."""
        for tk, r in corridas_ym.items():
            tasas = {}
            for modo, corrida in (("bruto", r["bruto_con"]), ("roc", r["roc_con"]),
                                  ("plano", r["plano_con"])):
                neto = (corrida.nra_withheld_total - corrida.roc_refund_total
                        - corrida.roc_receivable_final)
                tasas[modo] = neto / corrida.gross_dividends_total
            assert tasas["bruto"] == pytest.approx(0.0, abs=1e-9), f"{tk}: {tasas}"
            assert tasas["plano"] == pytest.approx(_CMP_FLAT_RATE, abs=1e-6), f"{tk}: {tasas}"
            assert 0.0 < tasas["roc"] < tasas["plano"], (
                f"{tk}: el escudo ROC no está reduciendo la tasa pagada: {tasas}")

    def test_el_contraejemplo_sigue_vivo(self, datos):
        """«Más impuesto ⇒ peor resultado» es FALSO con reinversión, y el copy de la vista
        enseña esa lección. Hoy la ilustra MSTY: retener funcionó como un retiro forzoso de
        un fondo en colapso, y parte del dinero volvió meses después a comprar más barato.

        Se afirma la propiedad, no el ticker (Regla 5): si un día ningún fondo la ilustra, el
        mensaje distingue «cambió el mercado» de «hay un bug»."""
        peores = {tk for tk in TRG_YM
                  if _retorno_total(datos, tk, "roc", "idx")
                  > _retorno_total(datos, tk, "bruto", "idx")}
        assert peores, (
            "ningún fondo ilustra ya que «más impuesto ⇒ peor resultado» es falso con DRIP. "
            "Puede ser que los precios cambiaran; pero antes de darlo por bueno, verificar "
            "que el reembolso del 1042-S sigue llegando en su fecha y no al cobro.")
