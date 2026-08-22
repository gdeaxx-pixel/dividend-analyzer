"""Un solo motor y un solo modelo fiscal para las dos vistas de «Comparación»
(migración 2026-08-21, la segunda mitad).

El bug que estos tests cierran: la app mostraba **dos números distintos para el mismo
fondo bajo la misma etiqueta**. «Con NRA · ROC 19a» daba NVDY +250.85% en «Comparación ·
Real» y +232.0% en «Comparación · Simulación» — 19 puntos porcentuales de diferencia, dos
submenús de distancia, porque cada vista corría un motor distinto:

  - «Simulación» → `backtest.run_backtest` (migrada al modelo exacto en el PR #62).
  - «Real» → `logic.build_drip_comparison_series`, que además de bajar de yfinance EN
    RUNTIME modelaba el escudo ROC como tasa efectiva `tasa × (1 − ROC)` aplicada al
    cobro — o sea asumiendo que el dinero nunca sale del fondo. Esa función y las dos que
    la sostenían se borraron el 2026-08-21, ya sin consumidor.

Hoy las dos leen `price_cache` y corren `run_backtest` con `_politica_fiscal`. Medido al
migrar: `bruto` y `plano` no se movieron **ni un decimal** en los 8 tickers (los dos
motores ya coincidían donde no hay escudo que modelar), y `roc` se movió solo en los 4
fondos con avisos 19(a). Que el cambio esté confinado exactamente ahí es la evidencia de
que se cambió el MODELO y no, de paso, el motor de precios.

Los tests de aquí son cruzados, estructurales o sobre el código fuente. Ninguno se
satisface reimplementando la fórmula que genera el dato.
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
    _CMP_FLAT_RATE, _politica_fiscal, TRG_MODOS, TRG_YM, TRG_UNIVERSO_REAL,
    comparacion_data, trg_real_data)

_UI = os.path.join(os.path.dirname(__file__), "ui")

# Cartera mínima: `trg_real_data` solo la usa para elegir el fondo base por defecto.
_CARTERA = {"MSTY": {"market_value": 500}}


@pytest.fixture(scope="module")
def real():
    """«Comparación · Real» a la tasa plana de los paneles pedagógicos (30%), que es la
    única tasa a la que se puede comparar contra «Simulación» — esa vista no tiene país."""
    d = trg_real_data(_CARTERA, tasa_pct=_CMP_FLAT_RATE * 100.0, pais="México")
    assert d is not None, "trg_real_data devolvió None — ningún ticker cargó del caché"
    return d


@pytest.fixture(scope="module")
def simulacion():
    d = comparacion_data()
    assert d is not None, "comparacion_data devolvió None"
    return d


def _retorno(datos: dict, modo: str, tk: str) -> float:
    """Retorno total de la serie tal como lo lee el JS: último mes contra el mes de
    incepción del propio ticker."""
    serie = datos["idx"][modo][tk]
    return serie[str(datos["last"])] / serie[str(datos["incep"][tk])] - 1.0


# ── El guard que faltaba: dos vistas del mismo número ───────────────────────────────────

class TestReconciliacionEntreLasDosVistas:
    """Regla 3b del contrato: todo eje con más de una vista necesita un test que compare
    **dos vistas del mismo número entre sí**. Este eje tenía dos vistas y ninguna prueba
    que las cruzara — por eso pudieron discrepar 19 pp durante meses con la suite verde.

    Limitación declarada: ambas vistas comparten hoy motor (`run_backtest`) y política
    (`_politica_fiscal`), así que esto no es una reconciliación contra una fuente
    independiente — es un guard de NO DIVERGENCIA. Es exactamente la regresión que
    ocurrió: alguien migra una vista y deja la otra atrás.
    """

    def test_la_ventana_de_los_ym_coincide_en_las_dos_vistas(self, real, simulacion):
        """Precondición del test de abajo, verificada en vez de asumida. «Real» ancla
        todas las series al YM más antiguo; «Simulación» arranca cada una en su propia
        incepción. Para los YM las dos coinciden **por construcción** —el ancla ES el YM
        más antiguo, así que ningún YM puede empezar antes que ella—, y por eso son los
        tickers comparables. Los ETF de crecimiento no lo son: si el caché guardara más
        historia de SCHB que del ancla, «Real» la recorta y «Simulación» no."""
        for tk in TRG_YM:
            if tk not in real["idx"]["bruto"] or tk not in simulacion["idx"]["bruto"]:
                continue
            mes_real = real["incep"][tk] + real["origen"][0] * 12 + real["origen"][1]
            mes_sim = (simulacion["incep"][tk] + simulacion["origen"][0] * 12
                       + simulacion["origen"][1])
            assert mes_real == mes_sim, (
                f"{tk}: «Real» arranca en el mes absoluto {mes_real} y «Simulación» en "
                f"{mes_sim} — con ventanas distintas los retornos no son comparables y "
                "el test de abajo dejaría de significar lo que dice")

    @pytest.mark.parametrize("modo", TRG_MODOS)
    def test_el_mismo_fondo_da_el_mismo_retorno_en_las_dos_vistas(self, real, simulacion,
                                                                 modo):
        """**El test que da sentido a esta migración.** A la misma tasa (30%), sobre la
        misma ventana y con el mismo fondo, las dos vistas tienen que dar el mismo número.
        Antes solo cuadraban en `bruto` y `plano`; en `roc` discrepaban hasta 19 pp.

        Tolerancia 0.05 pp: las series se redondean a 4 decimales sobre una escala de ~100
        en cada vista por separado, así que la coincidencia no puede ser exacta al bit,
        pero cualquier diferencia de MODELO es de órdenes de magnitud más."""
        comparados = 0
        for tk in TRG_YM:
            if tk not in real["idx"][modo] or tk not in simulacion["idx"][modo]:
                continue
            r = _retorno(real, modo, tk) * 100.0
            s = _retorno(simulacion, modo, tk) * 100.0
            assert r == pytest.approx(s, abs=0.05), (
                f"{tk}/{modo}: «Real» da {r:.2f}% y «Simulación» {s:.2f}% para el mismo "
                f"fondo, la misma ventana y la misma tasa — dos vistas del mismo número "
                "no pueden discrepar")
            comparados += 1
        assert comparados >= 4, (
            f"solo se compararon {comparados} fondos: el test está pasando por vacío")


# ── El motor viejo no puede volver a cablearse a una vista ───────────────────────────────

class TestElMotorViejoNoVuelve:
    """Tests sobre el CÓDIGO FUENTE, no sobre el resultado. `build_drip_comparison_series`,
    `build_roc_aware_withholding` y `build_total_return_series` se **borraron** de `logic.py`
    el 2026-08-21, al quedarse sin consumidor vivo. Hoy llamarlas reventaría con
    `AttributeError`, así que este guard ya no impide una llamada: impide que alguien las
    **reintroduzca** —copiándolas de `app_old.py` o del historial— para volver a modelar el
    escudo ROC dentro de la tasa. El nombre es la firma de esa regresión.
    """

    _PROHIBIDAS = ("build_drip_comparison_series", "build_roc_aware_withholding",
                   "build_total_return_series")

    def _fuentes_ui(self):
        for raiz, _, archivos in os.walk(_UI):
            for nombre in archivos:
                if nombre.endswith(".py"):
                    ruta = os.path.join(raiz, nombre)
                    with open(ruta, encoding="utf-8") as fh:
                        yield ruta, fh.read()

    def test_ninguna_vista_llama_al_motor_de_tasa_efectiva(self):
        """Busca LLAMADAS (`logic.x(`), no menciones: los docstrings de `ui/adapters.py` y
        `ui/vistas.py` nombran estas funciones a propósito, para explicar de dónde viene la
        vista y por qué se retiraron. Un guard que prohibiera la palabra obligaría a borrar
        la explicación."""
        patron = re.compile(r"logic\.(" + "|".join(self._PROHIBIDAS) + r")\s*\(")
        for ruta, src in self._fuentes_ui():
            m = patron.search(src)
            assert m is None, (
                f"{os.path.basename(ruta)} volvió a llamar a `{m.group(1)}` — ese motor "
                "mete el escudo ROC dentro de la tasa. La política fiscal de las vistas "
                "es `_politica_fiscal` + `backtest.run_backtest`.")

    def test_ninguna_vista_baja_precios_de_la_red_en_runtime(self):
        """`logic.fetch_market_data` va a yfinance. Hasta esta migración `trg_real_data`
        llegaba a él indirectamente (vía `build_drip_comparison_series`), así que el
        chequeo mecánico del barrido —que solo mira llamadas directas a yfinance dentro
        de `ui/`— lo daba por bueno. Toda la historia de precio de la UI sale de
        `price_cache`."""
        patron = re.compile(r"logic\.fetch_market_data\s*\(")
        for ruta, src in self._fuentes_ui():
            assert patron.search(src) is None, (
                f"{os.path.basename(ruta)} llama a `fetch_market_data` — la UI lee del "
                "caché de precio (`price_cache.load_history`), nunca de la red.")


# ── La política fiscal recibida por el motor ─────────────────────────────────────────────

class TestPoliticaQueRecibeElMotor:
    """Igual que `test_comparacion_data.py::TestUnSoloModeloRoc`, pero para «Real»: se
    vigila lo que el motor RECIBE, porque un modelo fiscal equivocado produce cifras
    plausibles."""

    @pytest.fixture(scope="class")
    def llamadas(self):
        registro = []
        original = backtest.run_backtest

        def espia(ticker, **kw):
            registro.append({"ticker": ticker, "nra_rate": kw.get("nra_rate", 0.0),
                             "roc_pct_by_year": dict(kw.get("roc_pct_by_year") or {})})
            return original(ticker, **kw)

        backtest.run_backtest = espia
        try:
            d = trg_real_data(_CARTERA, tasa_pct=10.0, pais="México")
        finally:
            backtest.run_backtest = original
        assert d is not None
        assert registro, "el espía no vio ninguna corrida: la vista dejó de usar el motor"
        return registro

    def test_la_tasa_del_pais_llega_al_motor_sin_diluirse(self, llamadas):
        """Con tratado (México, 10%) el motor tiene que recibir 0.10 al cobro, no 0.30 y
        no una tasa efectiva intermedia. `_politica_fiscal` podría ignorar `base_rate` y
        seguir dando 30% sin que ninguna cifra de pantalla lo delatara a simple vista."""
        tasas = {round(c["nra_rate"], 4) for c in llamadas}
        assert tasas <= {0.0, 0.10}, (
            f"tasas inesperadas en las corridas: {sorted(tasas)}. Con 10% declarado solo "
            "pueden existir 0.0 (bruto) y 0.10 (plano y roc, que retienen completo).")
        assert 0.10 in tasas, "ninguna corrida retuvo: los modos con NRA se perdieron"

    def test_el_escudo_no_viaja_dentro_de_la_tasa(self, llamadas):
        """Reclamar ROC presupone haber retenido: un reembolso sobre una tasa ya rebajada
        devolvería dos veces el mismo dinero."""
        for c in llamadas:
            if c["roc_pct_by_year"]:
                assert c["nra_rate"] == pytest.approx(0.10), (
                    f"{c['ticker']}: reclama ROC sobre una retención de {c['nra_rate']}")

    def test_los_fondos_con_avisos_19a_reclaman_su_roc(self, llamadas):
        roc19a = logic.load_roc_19a()
        con_avisos = {tk for tk in TRG_UNIVERSO_REAL
                      if _politica_fiscal(tk, "roc", roc19a).roc_pct_by_year}
        assert con_avisos, "ningún ticker del universo publica avisos 19(a) en el yaml"
        con_escudo = {c["ticker"] for c in llamadas if c["roc_pct_by_year"]}
        assert con_avisos <= con_escudo, (
            f"sin escudo ROC en {sorted(con_avisos - con_escudo)} pese a tener avisos")


# ── Propiedades estructurales de la tasa ─────────────────────────────────────────────────

class TestLaTasaDelPaisMandaDeVerdad:
    """Que `base_rate` llegue al motor (arriba) y que MUEVA el resultado (aquí) son dos
    cosas distintas: la primera se puede satisfacer pasando el parámetro y no usándolo."""

    @pytest.fixture(scope="class")
    def por_tasa(self):
        return {pct: trg_real_data(_CARTERA, tasa_pct=pct, pais="México" if pct == 10 else None)
                for pct in (10.0, 30.0)}

    def test_bruto_no_depende_de_la_tasa(self, por_tasa):
        """Estructural: en `bruto` nadie retiene, así que la tasa declarada no puede
        cambiar ni un decimal. Si se mueve, la tasa se está aplicando donde no toca."""
        for tk in por_tasa[10.0]["idx"]["bruto"]:
            assert _retorno(por_tasa[10.0], "bruto", tk) == pytest.approx(
                _retorno(por_tasa[30.0], "bruto", tk), abs=1e-9), tk

    def test_retener_menos_deja_mas(self, por_tasa):
        """Estructural en `plano`: sin escudo ni reembolso, una tasa menor deja más
        efectivo reinvertido en cada distribución, siempre. Solo se afirma sobre fondos
        que de verdad distribuyen — en uno sin dividendos las dos tasas dan lo mismo y la
        aserción sería vacía."""
        comparados = 0
        for tk in por_tasa[10.0]["idx"]["plano"]:
            bruto = _retorno(por_tasa[30.0], "bruto", tk)
            if _retorno(por_tasa[30.0], "plano", tk) == pytest.approx(bruto, abs=1e-9):
                continue                      # sin distribuciones: no hay nada que retener
            assert _retorno(por_tasa[10.0], "plano", tk) > _retorno(por_tasa[30.0], "plano", tk), tk
            comparados += 1
        assert comparados >= 4, f"solo {comparados} fondos distribuyeron: test vacío"
