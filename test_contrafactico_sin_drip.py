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
# Desde la unificación (2026-08-21) el JS ya NO calcula fiscalidad: `metodo_data` entrega
# `escenarios[modo][ticker]` simulado por el motor y `computeAll()` solo redondea a dólar y
# suma. Esta réplica hace exactamente eso — es trivial a propósito, y esa trivialidad es la
# señal de que la lógica dejó de estar duplicada en dos lenguajes.

def _compute_all(datos, modo):
    """Espejo de computeAll(): redondear a dólar y sumar las filas redondeadas."""
    filas, con_tot, sin_tot = {}, 0, 0
    for tk, e in datos["escenarios"][modo].items():
        con = round(e["max"]) + round(e["dripHoy"]) + round(e["devueltoCon"])
        sin = round(e["max"]) + round(e["divSin"]) + round(e["devueltoSin"])
        filas[tk] = {"con": con, "sin": sin}
        con_tot += con
        sin_tot += sin
    return {"filas": filas, "conTot": con_tot, "sinTot": sin_tot}


def test_el_componente_no_recalcula_fiscalidad():
    """Regla 3 del contrato: las vistas RENDERIZAN el objeto fiscal, no lo recalculan. Si
    alguien reintroduce la reescala post-hoc en JS, vuelven los dos defectos que tenía
    (no cobrar el interés compuesto, y penalizar el valor mientras reembolsa sobre los
    dividendos) y las tablas se despegan otra vez de la gráfica."""
    src = open(_COMPONENTE, encoding="utf-8").read()
    assert "var ESCENARIOS = DATA.escenarios;" in src
    assert "var sinDripTot = max + divSin + devueltoSin;" in src
    assert "var conDripTot = max + dripHoy + devuelto;" in src
    for muerto in ("function baseVal(", "function baseRound(", "function devueltoRound("):
        assert muerto not in src, (
            f"volvió {muerto!r} al componente — la fiscalidad debe venir simulada de "
            "`ui.adapters.metodo_data`, no recalcularse en JS")


# ── Guarda 1 · monotonicidad fiscal ──────────────────────────────────────────────────────

class TestMonotonicidadFiscal:
    """Qué es y qué NO es invariante al subir el impuesto.

    **Invariante (aquí se asserta):** el IMPUESTO crece con la severidad del régimen, y en
    el mundo SIN reinversión el resultado cae. Sin DRIP el impuesto solo resta efectivo: no
    hay camino que alterar, así que la monotonía es estructural.

    **NO invariante (aquí NO se asserta, a propósito):** que el RESULTADO con DRIP caiga al
    subir el impuesto. Medido: MSTY cayó −91.4% y el escenario «roc» termina en $10,235
    contra $9,462 del escenario sin impuesto alguno. No es un bug — se verificó
    mecánicamente: en «bruto» se reinvirtieron los $41,921 completos en un fondo que se
    desplomaba; en «roc» solo $25,899, y $7,840 volvieron meses después a comprar más
    barato, con $1,121 todavía fuera como cuenta por cobrar. La retención funcionó como un
    retiro forzoso de un activo en colapso.

    Es el mismo patrón que el repo ya protege en `test_comparacion_data.py` («NAV cayendo ⇒
    el efectivo gana» es FALSO): manda la trayectoria, no el destino. Aquí la versión
    fiscal — «más impuesto ⇒ peor resultado» también es falso cuando hay reinversión.
    Añadir esa aserción convertiría una casualidad de mercado en invariante y rompería el
    día que otro fondo se comporte así.
    """

    @pytest.mark.parametrize("tk", [c["t"] for c in MET_CASO])
    def test_el_impuesto_si_es_monotono(self, datos, tk):
        """Lo que sí no puede violarse: cuanto más severo el régimen, más impuesto neto.
        `bruto` no retiene nada; `roc` retiene y devuelve parte; `plano` retiene todo."""
        imp = {m: datos["escenarios"][m][tk]["impuestoCon"] for m in _MODOS}
        assert imp["bruto"] == pytest.approx(0.0, abs=0.01)
        assert imp["roc"] < imp["plano"], f"{tk}: el escudo ROC no está reduciendo nada: {imp}"

    def test_sin_drip_respeta_bruto_mayor_o_igual_que_roc_y_plano(self, datos):
        tot = {m: _compute_all(datos, m)["sinTot"] for m in _MODOS}
        assert tot["bruto"] >= tot["roc"] >= tot["plano"], (
            f"Sin DRIP viola monotonicidad fiscal: {tot}. Retener no puede enriquecer.")

    @pytest.mark.parametrize("tk", [c["t"] for c in MET_CASO])
    def test_sin_drip_monotona_tambien_por_ticker(self, datos, tk):
        f = {m: _compute_all(datos, m)["filas"][tk]["sin"] for m in _MODOS}
        assert f["bruto"] >= f["roc"] >= f["plano"], f"{tk}: {f}"

    def test_la_grafica_respeta_monotonicidad_sin_drip(self, serie):
        """Misma propiedad estructural, verificada en la otra vista: sin reinversión, la
        curva de un régimen más severo nunca termina por encima."""
        fin = {}
        for m in _MODOS:
            s = serie["serie"][m]["sin"]
            fin[m] = s[max(s, key=lambda k: int(k))]
        assert fin["bruto"] >= fin["roc"] >= fin["plano"], fin

    def test_el_defecto_del_metodo_post_hoc_esta_cerrado(self, datos):
        """Regresión del Frente B. El método viejo penalizaba el VALOR ($19,705) y
        reembolsaba sobre los DIVIDENDOS ($27,825): bases distintas, así que a nivel
        CARTERA «roc» superaba a «bruto» por $8,120 con DRIP. Eso sí era un artefacto
        aritmético, no economía — y tiene que seguir cerrado.

        Ojo con la diferencia respecto al caso MSTY del docstring de la clase: allí un
        TICKER suelto supera por razones económicas reales (retiro forzoso de un fondo en
        colapso); aquí es la CARTERA completa, donde esos efectos se compensan y el
        artefacto no tiene dónde esconderse."""
        tot = {m: _compute_all(datos, m)["conTot"] for m in _MODOS}
        assert tot["bruto"] >= tot["roc"] >= tot["plano"], (
            f"volvió el artefacto post-hoc: {tot}")


# ── Guarda 2 · reconciliación entre vistas ───────────────────────────────────────────────

class TestReconciliacionVistas:
    """Tabla contra gráfica. La discrepancia que este test caza llegó a producción sin que
    ningún test la viera, porque cada vista era correcta *contra sí misma*."""

    @pytest.mark.parametrize("modo", _MODOS)
    @pytest.mark.parametrize("vista,clave", [("sin", "sinTot"), ("con", "conTot")])
    def test_las_seis_celdas_cuadran_con_la_grafica(self, datos, serie, modo, vista, clave):
        """**El test que da sentido al Frente B.** Antes solo cuadraba 1 de 6 (`bruto/con`):
        las tablas reescalaban post-hoc y la gráfica simulaba evento a evento, así que la
        misma pantalla mostraba $177,289 y $78,816 para la misma cifra. Hoy ambas leen la
        misma simulación y las seis coinciden.

        No es tautológico: la tabla suma cinco filas redondeadas a dólar en JS, la gráfica
        mensualiza `total_value` día a día y toma el último mes. Coinciden porque describen
        el mismo mundo, no porque compartan la línea de código que las imprime."""
        tabla = _compute_all(datos, modo)[clave]
        s = serie["serie"][modo][vista]
        grafica = s[max(s, key=lambda k: int(k))]
        assert tabla == pytest.approx(grafica, abs=len(MET_CASO)), (
            f"{modo}/{vista}: tabla ${tabla:,.0f} contra gráfica ${grafica:,.2f} — dos "
            f"vistas del mismo número no pueden discrepar más allá del redondeo por fila")

    @pytest.mark.parametrize("modo", _MODOS)
    def test_inversion_hoy_no_la_mueve_el_impuesto(self, datos, modo):
        """Regla 1 en su forma más literal: «Inversión Hoy» son las acciones originales,
        que sin reinversión nunca cambian de número. Ningún régimen fiscal puede moverlas —
        si un modo las mueve, alguien metió el impuesto en el bucket equivocado."""
        for tk, e in datos["escenarios"][modo].items():
            base = datos["escenarios"]["bruto"][tk]["max"]
            assert e["max"] == pytest.approx(base, abs=0.01), (
                f"{tk} en {modo}: Inversión Hoy {e['max']} contra {base} en bruto")

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

    def test_el_reembolso_llega_tarde_y_eso_se_nota(self, datos):
        """El escudo ROC NO es equivalente a bajar la tasa: se retiene el 30% completo y el
        reembolso llega con el 1042-S, meses después. La huella observable de ese retraso
        es la cuenta por cobrar viva a la fecha de corte (`devueltoCon` > 0 en «roc», y
        exactamente 0 en los otros dos modos, que no tienen nada que devolver).

        Si alguien vuelve a modelar el ROC como tasa efectiva al cobro, esta columna se va a
        cero y el test lo caza — que es justo la regresión que cerró el Frente B."""
        for tk, e in datos["escenarios"]["roc"].items():
            assert e["devueltoCon"] > 0, (
                f"{tk}: sin cuenta por cobrar, el ROC volvió a aplicarse al cobro")
        for modo in ("bruto", "plano"):
            for tk, e in datos["escenarios"][modo].items():
                assert e["devueltoCon"] == pytest.approx(0.0, abs=0.01), f"{tk}/{modo}"

    def test_mas_impuesto_no_implica_peor_resultado_con_drip(self):
        """Propiedad ESTRUCTURAL del motor: «más impuesto ⇒ peor resultado» es FALSO con
        DRIP, y la lección que enseña el copy necesita que eso sea cierto EN EL MOTOR — no
        en un ticker concreto.

        Antes esto escaneaba `datos["escenarios"]` buscando un fondo real que ilustrara la
        propiedad (MSTY lo hizo durante meses). Era un hecho de mercado codificado como
        guarda: el refresh del caché se lo llevó y el test quedaba rojo sin bug (Regla 6).
        Ahora la propiedad se demuestra por construcción: una historia SINTÉTICA determinista
        (fondo que paga dividendos gordos y luego colapsa antes del 1042-S) pasa por el motor
        REAL, y el escenario con retención+escudo ROC termina ARRIBA del bruto. Si alguien
        rompe el manejo del escudo o del DRIP de forma que «más impuesto» vuelva a ser
        monotónico, esta demostración deja de sostenerse y el test avisa.

        Lo que ya NO caza: que hoy exista un fondo REAL que ilustre la lección (eso es dato
        de mercado, no contrato). El copy de `metodo.html` deriva su veredicto del dato vivo;
        si ningún fondo lo ilustra, la pantalla lo dice sola."""
        import pandas as pd

        # Historia sintética: 2023 plano con dividendos mensuales gordos (se retiene 30% en
        # cada uno), enero-febrero 2024 colapsa ~x0.3, y desde marzo dividendos normales.
        # El reembolso del año fiscal 2023 llega el 1-mar-2024 y compra acciones a precio
        # hundido: eso es lo que hace que el escenario con impuesto gane con DRIP.
        idx = pd.date_range("2023-01-01", periods=900, freq="D")
        price, divs = [100.0], [0.0]
        for i, dt_ in enumerate(idx[1:], 1):
            d = 0.0
            if dt_.year == 2023:
                rate = 0.0
                if dt_.day == 1:
                    d = price[-1] * 0.04
            elif dt_.year == 2024 and dt_.month in (1, 2):
                rate = -0.02
            else:
                rate = 0.0
                if dt_.day == 1:
                    d = price[-1] * 0.02
            price.append(price[-1] * (1 + rate))
            divs.append(d)
        h = pd.DataFrame({"Close": price, "Dividends": divs}, index=idx)

        bruto = backtest.run_backtest("SINTETICO", idx[0], initial_capital=10000.0,
                                      drip=True, nra_rate=0.0, history=h)
        roc = backtest.run_backtest("SINTETICO", idx[0], initial_capital=10000.0,
                                    drip=True, nra_rate=0.30,
                                    roc_pct_by_year={2023: 100.0}, history=h)

        assert roc.final_total_value > bruto.final_total_value, (
            "el motor ya no puede producir 'más impuesto ⇒ mejor resultado' con DRIP ni "
            "siquiera en el escenario diseñado para ello (colapso entre la retención y el "
            "1042-S). Esto sí es un bug del escudo/del DRIP, no un cambio de mercado — la "
            f"lección del copy perdió su prueba de existencia: bruto="
            f"{bruto.final_total_value:.2f} vs roc={roc.final_total_value:.2f}")
        # Y la huella de que el mecanismo es el reembolso (no un artefacto): sin escudo, la
        # misma corrida con retención pierde contra bruto — el impuesto al cobro solo resta.
        plano = backtest.run_backtest("SINTETICO", idx[0], initial_capital=10000.0,
                                      drip=True, nra_rate=0.30, history=h)
        assert plano.final_total_value < bruto.final_total_value

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
