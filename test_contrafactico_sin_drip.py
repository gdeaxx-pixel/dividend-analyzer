"""Guardas del contrafáctico «Sin DRIP» (auditoría 2026-08-21).

El bug: `metodo_data` entregaba un solo `div` —los dividendos de la corrida CON DRIP— y
la fila «Sin DRIP» de `metodo.html` lo sumaba sobre `r.max`, que sale de la corrida SIN
DRIP. La fila mezclaba dos mundos contrafácticos: le cobraba a las acciones que nunca se
compraron los dividendos que nunca pagaron. Medido: $165,780 contra $67,307 reales
(2.46x), total de la tabla inflado 2.25x, y el veredicto DRIP-vs-efectivo invertido en
NVDY y TSLY — contradiciendo el hallazgo que `test_comparacion_data.py` protege
explícitamente («en TSLY el DRIP gana»).

**Por qué la suite no lo cazó, y qué cambia aquí.** Los 562 tests previos verificaban cada
vista contra sí misma. Ninguno comparaba *dos vistas del mismo número*, así que la suite
podía estar verde con dos pantallas del mismo submenú discrepando $98K. Estos tests son
todos cruzados o de propiedad: ninguno se puede satisfacer reimplementando la fórmula que
generó el dato.

Tres guardas, de la más barata a la más valiosa:

  1. `TestMonotonicidadFiscal` — propiedad pura, sin ground truth: ningún régimen con
     retención puede rendir más que uno sin ella.
  2. `TestReconciliacionVistas` — la tabla contra la gráfica. Fuentes genuinamente
     independientes: una suma columnas redondeadas a dólar como hace el JS, la otra sale
     de `run_backtest` mes a mes.
  3. `TestIdentidadContrafactico` — ancla la fila a la simulación (`r_sin`), no a una
     suma rehecha a mano.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import backtest  # noqa: E402
import price_cache  # noqa: E402
from ui.adapters import MET_CASO, metodo_data, metodo_serie_data  # noqa: E402

_COMPONENTE = os.path.join(os.path.dirname(__file__), "ui", "componentes", "metodo.html")
_MODOS = ("bruto", "roc", "plano")


@pytest.fixture(scope="module")
def datos():
    d = metodo_data()
    assert d is not None, "metodo_data() devolvió None — falta historia de algún ticker"
    return d


@pytest.fixture(scope="module")
def serie():
    d = metodo_serie_data()
    assert d is not None, "metodo_serie_data() devolvió None"
    return d


# ── Réplica del único punto de cálculo del componente ────────────────────────────────────
# Espejo de `computeAll()` en metodo.html. Es deliberadamente una RÉPLICA y no un import:
# la lógica vive en JS y no hay runtime de JS en la suite. Para que no se vuelva
# tautológica, `test_replica_fiel_al_componente` verifica contra el HTML real que las
# expresiones clave siguen escritas como aquí — si alguien cambia el JS sin tocar esto, el
# test avisa en vez de seguir validando una fórmula fantasma.

def _compute_all(datos, modo):
    """Espejo de computeAll(): dos mundos, dos bases."""
    tasa, roc = datos["tasaNra"], datos["roc19a"]

    def base(x):
        return x if modo == "bruto" else x * (1 - tasa)

    def devuelto(bruto, tk):
        return round(tasa * roc[tk] * bruto) if modo == "roc" else 0

    filas, con_tot, sin_tot = {}, 0, 0
    for r in datos["matriz"]:
        mx, real, tk = r["max"], round(r["val"]), r["t"]
        con = mx + round(base(real - mx)) + devuelto(r["div"], tk)
        sin = mx + round(base(r["divSin"])) + devuelto(r["divSin"], tk)
        filas[tk] = {"con": con, "sin": sin}
        con_tot += con
        sin_tot += sin
    return {"filas": filas, "conTot": con_tot, "sinTot": sin_tot}


def test_replica_fiel_al_componente():
    """La réplica de arriba solo vale si el componente sigue calculando así. Fija las dos
    expresiones que el bug tocaba: que la fila Sin DRIP use `divSin` en AMBAS columnas
    (dividendos y devuelto), y que la Con DRIP siga con `div`."""
    src = open(_COMPONENTE, encoding="utf-8").read()
    assert "var sinDripTot = r.max + divSin + devueltoSin;" in src, (
        "la fila Sin DRIP dejó de sumar divSin/devueltoSin — si volvió a `div`, el bug "
        "del contrafáctico está de vuelta")
    assert "var conDripTot = r.max + dripHoy + devuelto;" in src
    assert "var divSin = baseRound(DIV_SIN[r.t]);" in src
    assert "var devueltoSin = devueltoRound(DIV_SIN[r.t], r.t);" in src


# ── Guarda 1 · monotonicidad fiscal ──────────────────────────────────────────────────────

class TestMonotonicidadFiscal:
    """Ningún régimen con retención puede rendir MÁS que uno sin retención. Es propiedad
    pura: no necesita ground truth, no envejece con los precios, y cazaba sola el síntoma
    del `Devuelto` sobredimensionado."""

    def test_sin_drip_respeta_bruto_mayor_o_igual_que_roc_y_plano(self, datos):
        tot = {m: _compute_all(datos, m)["sinTot"] for m in _MODOS}
        assert tot["bruto"] >= tot["roc"] >= tot["plano"], (
            f"Sin DRIP viola monotonicidad fiscal: {tot}. Retener no puede enriquecer.")

    @pytest.mark.parametrize("tk", [c["t"] for c in MET_CASO])
    def test_sin_drip_monotona_tambien_por_ticker(self, datos, tk):
        f = {m: _compute_all(datos, m)["filas"][tk]["sin"] for m in _MODOS}
        assert f["bruto"] >= f["roc"] >= f["plano"], f"{tk}: {f}"

    def test_la_grafica_respeta_monotonicidad_en_los_seis_escenarios(self, serie):
        """La 3ª gráfica simula evento a evento; ahí la propiedad tiene que cumplirse en
        los dos mundos, sin excepción."""
        for vista in ("con", "sin"):
            fin = {}
            for m in _MODOS:
                s = serie["serie"][m][vista]
                fin[m] = s[max(s, key=lambda k: int(k))]
            assert fin["bruto"] >= fin["roc"] >= fin["plano"], f"{vista}: {fin}"

    @pytest.mark.xfail(strict=True, reason=(
        "Defecto CONOCIDO y acotado (Frente B de la auditoría 2026-08-21), no una "
        "tolerancia ampliada para pasar. En la fila Con DRIP el método post-hoc aplica la "
        "penalización del 30% al INCREMENTO DE VALOR ($19,705) mientras el reembolso ROC "
        "sale de los DIVIDENDOS BRUTOS ($27,825): bases distintas, y el reembolso gana por "
        "$8,120, así que 'roc' supera a 'bruto'. No lo causa el bug del contrafáctico —"
        "sobrevivió a su arreglo— sino la aproximación post-hoc. Se cierra unificando la "
        "metodología con la de la gráfica. `strict=True` a propósito: cuando el Frente B "
        "entre, este test pasará y pytest lo reportará como XPASS fallido, obligando a "
        "borrar el xfail en vez de dejarlo enmascarando el arreglo."))
    def test_con_drip_respeta_monotonicidad(self, datos):
        tot = {m: _compute_all(datos, m)["conTot"] for m in _MODOS}
        assert tot["bruto"] >= tot["roc"] >= tot["plano"], tot


# ── Guarda 2 · reconciliación entre vistas ───────────────────────────────────────────────

class TestReconciliacionVistas:
    """Tabla contra gráfica. La discrepancia que este test caza llegó a producción sin que
    ningún test la viera, porque cada vista era correcta *contra sí misma*."""

    @pytest.mark.parametrize("modo", _MODOS)
    def test_sin_drip_cuadra_con_el_final_de_la_serie(self, datos, serie, modo):
        """En el mundo sin reinversión la retención es lineal (no hay interés compuesto que
        perder), así que el atajo post-hoc y la simulación evento a evento coinciden en los
        TRES modos. La tolerancia es de redondeo: la tabla redondea a dólar por fila."""
        tabla = _compute_all(datos, modo)["sinTot"]
        s = serie["serie"][modo]["sin"]
        grafica = s[max(s, key=lambda k: int(k))]
        assert tabla == pytest.approx(grafica, abs=len(MET_CASO)), (
            f"{modo}: tabla ${tabla:,.0f} contra gráfica ${grafica:,.2f} — dos vistas del "
            f"mismo número no pueden discrepar más allá del redondeo por fila")

    def test_con_drip_cuadra_en_bruto(self, datos, serie):
        """Sin retención las dos metodologías son la misma; si esto se rompe, se rompió el
        cableado, no el método."""
        tabla = _compute_all(datos, "bruto")["conTot"]
        s = serie["serie"]["bruto"]["con"]
        grafica = s[max(s, key=lambda k: int(k))]
        assert tabla == pytest.approx(grafica, abs=len(MET_CASO))

    def test_capital_aportado_invariante_en_los_seis_escenarios(self, datos, serie):
        """Regla 1 del contrato fiscal: el capital aportado no lo mueve ningún régimen."""
        assert serie["invTotal"] == pytest.approx(datos["tot"]["inv"], abs=0.01)
        assert datos["tot"]["inv"] == pytest.approx(
            sum(c["inv"] for c in MET_CASO), abs=0.01)


# ── Guarda 3 · identidad del contrafáctico ───────────────────────────────────────────────

class TestIdentidadContrafactico:
    """Ancla la fila Sin DRIP a la simulación en vez de a una suma rehecha a mano."""

    @pytest.mark.parametrize("caso", MET_CASO, ids=lambda c: c["t"])
    def test_divsin_sale_de_la_corrida_sin_drip(self, datos, caso):
        tk = caso["t"]
        hr = price_cache.load_history(tk)
        r_sin = backtest.run_backtest(tk, start_date=caso["start"],
                                      initial_capital=caso["inv"], drip=False,
                                      nra_rate=0.0, history=hr.history)
        fila = next(r for r in datos["matriz"] if r["t"] == tk)
        assert fila["divSin"] == pytest.approx(r_sin.gross_dividends_total, abs=0.01)
        assert fila["sinTotReal"] == pytest.approx(r_sin.final_total_value, abs=0.01)
        # `cash_accum == gross` solo con nra_rate=0: si algún día se retiene aquí, esta
        # igualdad deja de valer y el test obliga a revisarlo en vez de asumirlo.
        assert float(r_sin.daily["cash_accum"].iloc[-1]) == pytest.approx(
            r_sin.gross_dividends_total, abs=0.01)

    @pytest.mark.parametrize("caso", MET_CASO, ids=lambda c: c["t"])
    def test_divsin_es_estrictamente_menor_que_div(self, datos, caso):
        """Reinvertir compra acciones que a su vez cobran: el mundo con DRIP siempre cobra
        más. Si esto se invierte o se iguala, alguien volvió a cablear la misma serie en
        los dos campos."""
        fila = next(r for r in datos["matriz"] if r["t"] == caso["t"])
        assert fila["divSin"] < fila["div"]

    def test_la_suma_de_columnas_iguala_el_total_del_motor(self, datos):
        """En modo bruto la fila Sin DRIP es `max + divSin`, y eso tiene que ser el
        `final_total_value` de la corrida sin DRIP — que es la fuente independiente."""
        tabla = _compute_all(datos, "bruto")["sinTot"]
        assert tabla == pytest.approx(datos["tot"]["sinTotReal"], abs=len(MET_CASO))


# ── El copy no puede volver a cablear un veredicto ───────────────────────────────────────

class TestVeredictoDerivado:
    def test_el_recuento_de_fondos_se_deriva_y_no_esta_cableado(self):
        """Decía «Los 5 fondos favorecen al efectivo» en duro. Con la base corregida son 3
        de 5 (NVDY y TSLY favorecen al DRIP), así que el número tiene que contarse en
        tiempo de render."""
        src = open(_COMPONENTE, encoding="utf-8").read()
        assert "function cashNote(D)" in src
        assert "setHtml(\"mCashNote\", cashNote(D));" in src
        assert not re.search(r"Los <b>5 fondos</b> favorecen al efectivo", src), (
            "volvió el recuento cableado en modal-cash")

    def test_el_veredicto_por_ticker_no_es_unanime(self, datos):
        """La lección correcta —y la que `test_comparacion_data.py` ya protege— es que la
        caída del precio NO decide sola: manda la trayectoria. Si algún día los 5 fondos
        cayeran del mismo lado, el copy derivado lo dirá, pero hoy el contraejemplo tiene
        que existir, porque es la mitad de la lección."""
        f = _compute_all(datos, "bruto")["filas"]
        favor_drip = [tk for tk, v in f.items() if v["sin"] < v["con"]]
        assert favor_drip, (
            "ningún fondo favorece al DRIP — revisar si volvió el bug del contrafáctico, "
            "que era justo lo que borraba los contraejemplos")
