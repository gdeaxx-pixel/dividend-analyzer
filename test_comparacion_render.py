"""C·2/Q4 — `seriesSin` (ui/componentes/comparacion.html) rebasaba "Sin DRIP" dividiendo
entre `tot[t0]` (que arrastra el efectivo cobrado ANTES del inicio elegido) en vez de
`precio[t0]` (el valor de las acciones en t0). Opción A (G3, Daniel 2026-09-18): el
inicio elegido es una COMPRA NUEVA.

Patrón de `test_vista_impuestos_render.py`: se EXTRAE el `<script>` (aquí, solo la
función bajo prueba, por brace-balance — el IIFE completo del componente toca DOM real
que no vale la pena mockear para esto) y se EJECUTA en Node, nunca se copia la fórmula
al test en Python (un test con su propia copia del valor que vigila se compara consigo
mismo y pasa siempre).
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

import pandas as pd
import pytest

import backtest

_HTML = os.path.join(os.path.dirname(__file__), "ui", "componentes", "comparacion.html")
_HTML_REAL = os.path.join(os.path.dirname(__file__), "ui", "componentes",
                          "comparacion_real.html")

_node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node ausente: el gate de CONSECUENCIA no corre — y un skip no es un pass")


def _extraer_funcion_de(ruta: str, nombre: str) -> str:
    """Extrae `function NOMBRE(...) { ... }` del componente en `ruta` por balance de
    llaves — sin regex de una línea, que se corta en la primera `}` (hay varias anidadas)."""
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    i = src.index(f"function {nombre}(")
    depth = 0
    started = False
    for k in range(i, len(src)):
        c = src[k]
        if c == "{":
            depth += 1
            started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return src[i:k + 1]
    raise AssertionError(f"no encontré el cierre de function {nombre}(")


def _extraer_funcion(nombre: str) -> str:
    return _extraer_funcion_de(_HTML, nombre)


def _correr_js(fn_src: str, data: dict, last: int, llamada: str) -> dict:
    """Ejecuta `fn_src` (una función standalone) en Node con `DATA`/`LAST` globales y
    `llamada` (una expresión que la invoca), y devuelve el resultado como dict."""
    prog = (
        "var DATA = " + json.dumps(data) + ";\n"
        "var LAST = " + str(last) + ";\n"
        + fn_src + "\n"
        "console.log(JSON.stringify(" + llamada + "));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as t:
        t.write(prog)
        ruta = t.name
    try:
        r = subprocess.run(["node", ruta], capture_output=True, text=True)
    finally:
        os.unlink(ruta)
    assert r.returncode == 0, f"el script reventó:\n{r.stderr}\n---\n{prog}"
    return json.loads(r.stdout.strip().splitlines()[-1])


@_node
def test_q4b_rebase_da_cien_por_ciento():
    """Caso Q4b del barrido cuantitativo: `tot[t0]` incluye efectivo cobrado antes de
    t0 (120) mientras `precio[t0]` es solo las acciones (100). Con `tot[LAST]`=220 el
    rebase viejo (÷tot[t0]) daba +83.3333%; el correcto (÷precio[t0]) da +100.0000%."""
    fn = _extraer_funcion("seriesSin")
    data = {
        "idxSin": {"bruto": {"X": {"0": 120.0, "1": 220.0}}},
        "precioSin": {"X": {"0": 100.0, "1": 180.0}},
    }
    rep = _correr_js(fn, data, last=1, llamada='seriesSin("X", "bruto", 0)')
    assert rep["data"]["1"] == pytest.approx(1.0, abs=1e-6), (
        f"esperaba +100.0000% (÷precio[t0]), di {rep['data']['1']*100:.4f}%")
    assert rep["data"]["1"] != pytest.approx(220.0 / 120.0 - 1.0, abs=1e-6), (
        "sigue dando +83.3333% — el rebase sigue dividiendo entre tot[t0]")


@_node
def test_q4_la_serie_arranca_en_cero():
    """Control: en t0 la serie sigue arrancando en 0%, en los tres modos — eso ya
    funcionaba y el fix no lo debe tocar."""
    fn = _extraer_funcion("seriesSin")
    for modo in ("bruto", "plano", "roc"):
        data = {
            "idxSin": {modo: {"X": {"0": 500.0, "1": 640.0, "2": 700.0}}},
            "precioSin": {"X": {"0": 500.0, "1": 600.0, "2": 650.0}},
        }
        rep = _correr_js(fn, data, last=2, llamada=f'seriesSin("X", "{modo}", 0)')
        assert rep["data"]["0"] == pytest.approx(0.0, abs=1e-9), f"{modo}: no arranca en 0%"


def _historia_sintetica():
    """24 meses de precio+dividendo sintéticos (nunca yfinance): precio sube con ruido
    determinista, dividendo mensual el día 15. Suficientemente irregular para que
    tot[t0] (con efectivo previo) y precio[t0] (solo acciones) diverjan de verdad."""
    fechas = pd.bdate_range("2024-01-02", "2025-12-31")
    precios, divs = [], []
    for i, d in enumerate(fechas):
        precios.append(round(20.0 + 0.015 * i + 1.5 * ((i % 21) - 10) / 10.0, 4))
        divs.append(0.18 if d.day == 15 else 0.0)
    return pd.DataFrame({"Close": precios, "Dividends": divs,
                         "Stock Splits": [0.0] * len(fechas)}, index=fechas)


@_node
def test_q4_rebase_reproduce_el_motor_en_los_tres_modos(monkeypatch):
    """El test que importa: corre `run_backtest` (bruto/plano/roc) desde la incepción y
    desde t0 sobre una historia sintética, alimenta `seriesSin` con la corrida desde la
    incepción y compara contra la corrida "compra nueva" (desde t0) — el oráculo sale
    del motor, no de una constante escrita a mano."""
    from ui.adapters import _fecha_por_mes, _mensualizar_desde

    history = _historia_sintetica()
    monkeypatch.setattr(backtest, "fetch_history",
                        lambda ticker, start=None, end=None: history)

    origen_start = history.index.min()
    origen = [int(origen_start.year), int(origen_start.month) - 1]
    politicas = {
        "bruto": dict(nra_rate=0.0, roc_pct_by_year=None),
        "plano": dict(nra_rate=0.30, roc_pct_by_year=None),
        "roc": dict(nra_rate=0.30, roc_pct_by_year={2024: 50.0, 2025: 50.0}),
    }

    idx_sin, precio_sin_m, fecha_por_mes = {}, None, None
    for modo, pol in politicas.items():
        r = backtest.run_backtest("X", start_date=origen_start, initial_capital=10000.0,
                                  drip=False, history=history, **pol)
        idx_sin[modo] = {"X": _mensualizar_desde(r.daily["total_value"], origen)}
        if precio_sin_m is None:
            precio_sin_m = _mensualizar_desde(r.daily["portfolio_value"], origen)
            # fecha REAL de trading (no el label de calendario de `.resample("ME")`, que
            # puede caer en fin de semana) de cada índice mensual — `seriesSin` compara
            # contra "compra nueva" en ese mismo día exacto, o precio[t0] no coincidiría.
            # Q5: era una copia inline de esta misma lógica; ahora usa el helper de módulo
            # (`_fecha_por_mes`), que es el que alimenta `idxDesde`. Dos copias de la
            # excepción de primer-bin divergen en una sola y nadie lo nota. Claves `str`.
            fecha_por_mes = _fecha_por_mes(r.daily["portfolio_value"], origen)
    precio_sin = {"X": precio_sin_m}

    last = max(int(k) for k in precio_sin_m)
    fn = _extraer_funcion("seriesSin")

    # dos meses de corte, análogos a 2025-03-31 / 2025-12-31 de la spec: uno temprano y
    # uno tardío, comparados contra "compra nueva" en la FECHA EXACTA de ese índice.
    for t0 in (5, 18):
        assert 0 < t0 < last, f"t0={t0} fuera de rango (0, {last})"
        fecha_t0 = fecha_por_mes[str(t0)]

        data = {"idxSin": idx_sin, "precioSin": precio_sin}
        for modo, pol in politicas.items():
            rep = _correr_js(fn, data, last=last, llamada=f'seriesSin("X", "{modo}", {t0})')
            rebase_js = rep["data"][str(last)]

            r_nueva = backtest.run_backtest("X", start_date=fecha_t0, initial_capital=10000.0,
                                            drip=False, history=history, **pol)
            compra_nueva_pct = r_nueva.total_return_pct

            assert rebase_js * 100 == pytest.approx(compra_nueva_pct, abs=1e-4), (
                f"modo={modo} t0={t0}: seriesSin dio {rebase_js*100:.6f}%, "
                f"compra nueva (run_backtest desde t0) dio {compra_nueva_pct:.6f}%")


_IDX_AT = 'function idxAt(tk, m, mode){ return DATA.idx[mode][tk][m]; }\n'


@_node
def test_q4_con_drip_bruto_y_plano_no_cambian():
    """`series()` (Con DRIP) usa la misma división por `base0` de siempre en bruto y plano
    — ni Q4 ni Q5 la tocan ahí. Control: da lo mismo antes y después.

    El modo roc YA está arreglado (Q5): `series()` lee la corrida limpia precalculada en
    `DATA.idxDesde` en vez de dividir por `tot[t0]`, que arrastraba el `roc_receivable`
    devengado antes del inicio elegido. Este test sigue siendo el control de que ese fix
    **no movió bruto ni plano**; que roc ignore `idxDesde` fuera de su modo lo vigila
    `test_q5_bruto_y_plano_ignoran_idxdesde`."""
    fn = _IDX_AT + _extraer_funcion("series")
    for modo in ("bruto", "plano"):
        data = {"idx": {modo: {"X": {"0": 1000.0, "1": 1050.0, "2": 1200.0}}}}
        rep = _correr_js(fn, data, last=2, llamada=f'series("X", 0, "{modo}")')
        esperado = {m: data["idx"][modo]["X"][str(m)] / data["idx"][modo]["X"]["0"] - 1
                   for m in (0, 1, 2)}
        for m, v in esperado.items():
            assert rep["data"][str(m)] == pytest.approx(v, abs=1e-9), (
                f"{modo} m={m}: series() cambió — Q4 no debía tocarla")


# ── U5 (2026-09-20): `priceData` y `cosechaData` — las otras dos series que el fix de
# Q4 rebasa y que los 4 tests de arriba NO miraban. Medido por Opus: revertir solo una
# de las dos a `X[m]/base0 − 1` (mutantes M7/M8) sobrevivía la suite entera — la línea
# de precio nacía 16.6667 puntos bajo cero sin que nada se pusiera rojo.
#
# Mismo patrón del archivo: la función se EXTRAE del HTML y se ejecuta en Node; los
# esperados son aritmética de mano sobre la fixture (números redondos sintéticos), no
# una transcripción de la fórmula auditada. La fixture reproduce el caso Q4b: `tot`
# arrastra efectivo cobrado ANTES de t0, así que tot[t0] ≠ precio[t0] en los tres modos
# — justo la diferencia que el fix deja de meter en el denominador.

_PRECIO_SIN = {"0": 100.0, "1": 200.0, "2": 250.0}
_TOT_POR_MODO = {
    "bruto": {"0": 130.0, "1": 240.0, "2": 300.0},   # efectivo pre-t0: 30 / 40
    "plano": {"0": 122.0, "1": 230.0, "2": 292.0},   # 22 / 30
    "roc":   {"0": 126.0, "1": 235.0, "2": 296.0},   # 26 / 35
}
_COSECHA_POR_MODO = {
    "bruto": {"0": 40.0, "1": 100.0, "2": 160.0},
    "plano": {"0": 35.0, "1": 90.0, "2": 145.0},
    "roc":   {"0": 38.0, "1": 105.0, "2": 155.0},
}
# Esperados de priceData[2] = precio[2]/precio[t0] − 1, a mano:
#   t0=0 → 250/100 − 1 = 1.5 · t0=1 → 250/200 − 1 = 0.25 (igual en los tres modos:
#   la línea de precio no depende del modo — el mutante M7 sí, y muere en los tres).
_PRECIO_ESPERADO = {0: 1.5, 1: 0.25}
# Esperados de cosechaData[2] = (cosecha[2] − cosecha[t0])/precio[t0], a mano:
#   t0=0 → bruto (160−40)/100 = 1.2 · plano (145−35)/100 = 1.1 · roc (155−38)/100 = 1.17
#   t0=1 → bruto (160−100)/200 = 0.3 · plano (145−90)/200 = 0.275 · roc (155−105)/200 = 0.25
_COSECHA_ESPERADA = {
    0: {"bruto": 1.2, "plano": 1.1, "roc": 1.17},
    1: {"bruto": 0.3, "plano": 0.275, "roc": 0.25},
}


@_node
def test_q4_pricedata_arranca_en_cero_y_rebasa_como_compra_nueva():
    """La línea de precio (acción sola) nace en 0% en t0 — como la de cartera — y crece
    contra `precio[t0]`. Con el denominador viejo (`tot[t0]`, que incluye el efectivo
    pre-t0) arrancaba en −16.6667% en el caso Q4b: dos líneas del mismo gráfico nacían
    de puntos distintos. En los tres modos y con dos inicios (t0=0 y t0 intermedio)."""
    fn = _extraer_funcion("seriesSin")
    for modo in ("bruto", "plano", "roc"):
        data = {"idxSin": {modo: {"X": _TOT_POR_MODO[modo]}},
                "precioSin": {"X": _PRECIO_SIN}}
        for t0 in (0, 1):
            rep = _correr_js(fn, data, last=2, llamada=f'seriesSin("X", "{modo}", {t0})')
            # Trampa 4: afirmar también que la clave ESTÁ — `undefined` se pierde en
            # JSON.stringify y `.get()` no distingue «vale None» de «no existe».
            assert "priceData" in rep, f"{modo} t0={t0}: la respuesta no trae priceData"
            serie = rep["priceData"]
            assert serie is not None, f"{modo} t0={t0}: priceData vino null"
            assert str(t0) in serie and "2" in serie, (
                f"{modo} t0={t0}: priceData incompleta — claves {sorted(serie)}")
            assert serie[str(t0)] == pytest.approx(0.0, abs=1e-12), (
                f"{modo} t0={t0}: la línea de precio debe arrancar en 0%, di "
                f"{serie[str(t0)] * 100:.4f}% — con ÷tot[t0] nace bajo cero")
            assert serie["2"] == pytest.approx(_PRECIO_ESPERADO[t0], abs=1e-9), (
                f"{modo} t0={t0}: priceData[LAST] = {serie['2'] * 100:.4f}%, esperaba "
                f"{_PRECIO_ESPERADO[t0] * 100:.4f}% (precio[LAST]/precio[t0] − 1)")


@_node
def test_q4_cosechadata_rebasa_como_compra_nueva():
    """La línea de cosecha (el efectivo puesto a comprar el destino) se rebasa con el
    MISMO denominador que las otras dos (`precio[t0]`) y nace en 0% en t0 — «las tres
    líneas nacen del mismo punto». El mutante M8 (÷`tot[t0]`) la movía entera y nadie
    lo notaba. En los tres modos y con dos inicios."""
    fn = _extraer_funcion("seriesSin")
    for modo in ("bruto", "plano", "roc"):
        data = {"idxSin": {modo: {"X": _TOT_POR_MODO[modo]}},
                "precioSin": {"X": _PRECIO_SIN},
                "idxCosecha": {modo: {"X": _COSECHA_POR_MODO[modo]}}}
        for t0 in (0, 1):
            rep = _correr_js(fn, data, last=2, llamada=f'seriesSin("X", "{modo}", {t0})')
            assert "cosechaData" in rep, (
                f"{modo} t0={t0}: la respuesta no trae cosechaData — con la fixture "
                "idxCosecha presente no puede ser undefined")
            serie = rep["cosechaData"]
            assert serie is not None, f"{modo} t0={t0}: cosechaData vino null"
            assert str(t0) in serie and "2" in serie, (
                f"{modo} t0={t0}: cosechaData incompleta — claves {sorted(serie)}")
            assert serie[str(t0)] == pytest.approx(0.0, abs=1e-12), (
                f"{modo} t0={t0}: la línea de cosecha debe arrancar en 0%, di "
                f"{serie[str(t0)] * 100:.4f}%")
            esperado = _COSECHA_ESPERADA[t0][modo]
            assert serie["2"] == pytest.approx(esperado, abs=1e-9), (
                f"{modo} t0={t0}: cosechaData[LAST] = {serie['2'] * 100:.4f}%, esperaba "
                f"{esperado * 100:.4f}% ((cosecha[LAST] − cosecha[t0])/precio[t0])")


# ── Q5 (2026-09-24): `series()` (Con DRIP) en modo roc. `DATA.idx` es `total_value`, que
# con DRIP es `portfolio_value + roc_receivable` (backtest.py:443). Dividir entre `tot[t0]`
# mete en el denominador la cuenta por cobrar devengada ANTES del inicio elegido, y con DRIP
# ese reembolso compra acciones cuando se cobra: la cuenta de quien compra nuevo en t0
# diverge de la vieja durante TODO el tramo posterior. Medido sobre el universo real: hasta
# 2.94 pp, y el signo cambia según el fondo. El arreglo es un dato precalculado en Python
# (`DATA.idxDesde`), no una fórmula — ver spec Q5 §3 (refutación) y §14 (prueba por
# superposición: el motor es homogéneo de grado 1, luego `viejo = limpio + receivable_pre_t0`).


@_node
def test_q5_con_drip_roc_reproduce_el_motor(monkeypatch):
    """El test que paga la spec: el gemelo Con DRIP de
    `test_q4_rebase_reproduce_el_motor_en_los_tres_modos`. El esperado sale del MOTOR
    (una compra nueva corrida desde t0), nunca de una transcripción de la fórmula."""
    from ui.adapters import _fecha_por_mes, _mensualizar_desde

    history = _historia_sintetica()
    monkeypatch.setattr(backtest, "fetch_history",
                        lambda ticker, start=None, end=None: history)

    origen_start = history.index.min()
    origen = [int(origen_start.year), int(origen_start.month) - 1]
    POL = dict(nra_rate=0.30, roc_pct_by_year={2024: 50.0, 2025: 50.0})
    CAPITAL = 10000.0

    r = backtest.run_backtest("X", start_date=origen_start, initial_capital=CAPITAL,
                              drip=True, history=history, **POL)
    idx = {"roc": {"X": _mensualizar_desde(r.daily["total_value"], origen)}}
    fecha_por_mes = _fecha_por_mes(r.daily["total_value"], origen)
    last = max(int(k) for k in idx["roc"]["X"])

    fn = _IDX_AT + _extraer_funcion("series")

    for t0 in (5, 18):
        assert 0 < t0 < last, f"t0={t0} fuera de rango (0, {last})"

        # ORÁCULO: compra nueva en t0 — el motor arranca con el receivable en cero por
        # construcción, que es justo lo que NO tiene quien ya venía desde la incepción.
        r_nueva = backtest.run_backtest("X", start_date=fecha_por_mes[str(t0)],
                                        initial_capital=CAPITAL, drip=True,
                                        history=history, **POL)
        compra_nueva_pct = r_nueva.total_return_pct

        idx_desde = {"X": {str(t0): _mensualizar_desde(r_nueva.daily["total_value"], origen)}}
        data = {"idx": idx, "idxDesde": idx_desde}
        rep = _correr_js(fn, data, last=last, llamada=f'series("X", {t0}, "roc")')

        assert rep["data"][str(last)] * 100 == pytest.approx(compra_nueva_pct, abs=1e-4), (
            f"t0={t0}: series() dio {rep['data'][str(last)]*100:.6f}%, "
            f"compra nueva (run_backtest desde t0) dio {compra_nueva_pct:.6f}%")

        # La serie sigue naciendo en 0% en t0 — el rebase no mueve el punto de partida.
        assert rep["data"][str(t0)] == pytest.approx(0.0, abs=1e-12), (
            f"t0={t0}: la serie no arranca en 0%")

        # Y el cálculo VIEJO no coincide: si coincidiera, la fixture no tendría receivable
        # pre-t0 y este test estaría verde sin vigilar nada.
        viejo = idx["roc"]["X"][str(last)] / idx["roc"]["X"][str(t0)] - 1
        assert rep["data"][str(last)] != pytest.approx(viejo, abs=1e-6), (
            f"t0={t0}: series() sigue dando el valor viejo — la fixture no tiene "
            "receivable pre-t0 o el fix no se aplicó")


# Fixture de números redondos para los dos guards de degradación: el esperado es
# aritmética de mano (240/120 − 1 = 1.0 · 300/120 − 1 = 1.5), no la fórmula auditada.
_Q5_IDX = {"0": 100.0, "1": 120.0, "2": 240.0, "3": 300.0}
_Q5_ESPERADO_T1 = {1: 0.0, 2: 1.0, 3: 1.5}


@_node
@pytest.mark.parametrize("etiqueta,idx_desde", [
    ("sin la clave", None),
    ("idxDesde vacío", {}),
    ("idxDesde sin ese t0", {"X": {"0": {"0": 1.0, "1": 2.0, "2": 3.0, "3": 4.0}}}),
])
def test_q5_sin_idxdesde_cae_a_la_formula_de_siempre(etiqueta, idx_desde):
    """Degradación: sin entrada aplicable, `series()` da exactamente `idx[m]/idx[t0] − 1`
    y NUNCA `NaN`. Las claves de `idxDesde` vienen de JSON: un mes ausente daría
    `undefined` y la división produciría un `NaN` silencioso (mutante M2)."""
    fn = _IDX_AT + _extraer_funcion("series")
    data = {"idx": {"roc": {"X": _Q5_IDX}}}
    if idx_desde is not None:
        data["idxDesde"] = idx_desde

    rep = _correr_js(fn, data, last=3, llamada='series("X", 1, "roc")')
    for m, v in _Q5_ESPERADO_T1.items():
        assert rep["data"][str(m)] is not None, f"{etiqueta} m={m}: valor ausente"
        assert rep["data"][str(m)] == pytest.approx(v, abs=1e-9), (
            f"{etiqueta} m={m}: dio {rep['data'][str(m)]}, esperado {v}")


@_node
@pytest.mark.parametrize("modo", ["bruto", "plano"])
def test_q5_bruto_y_plano_ignoran_idxdesde(modo):
    """En bruto y plano el `roc_receivable` es 0, `tot[t0] == precio[t0]` y la fórmula de
    siempre ya es exacta: `series()` debe ignorar `idxDesde` aunque esté presente y traiga
    valores deliberadamente distintos. Si alguien quita el `mode === "roc"`, esto cae
    (mutante M3)."""
    fn = _IDX_AT + _extraer_funcion("series")
    data = {
        "idx": {modo: {"X": _Q5_IDX}},
        # valores TRAMPA: nada que ver con `idx`, para que usarlos se note.
        "idxDesde": {"X": {"1": {"1": 7.0, "2": 7.0, "3": 7.0}}},
    }
    rep = _correr_js(fn, data, last=3, llamada=f'series("X", 1, "{modo}")')
    for m, v in _Q5_ESPERADO_T1.items():
        assert rep["data"][str(m)] == pytest.approx(v, abs=1e-9), (
            f"{modo} m={m}: dio {rep['data'][str(m)]}, esperado {v} — "
            "¿se quitó el guard de modo?")


# ── Q6 (2026-09-24): gemelo de Q5 en la vista REAL (`comparacion_real.html`). Mismo
# defecto —`series()` dividía entre `tot[startM]`, que en modo roc arrastra el
# `roc_receivable` devengado antes del inicio elegido— pero otra firma:
# `series(tk, mode, baseIncep)` calcula `startM = max(baseIncep, F[tk].incep)` DENTRO y
# devuelve `late`. Y otro cableado: `baseIncep` es la incepción del fondo base y nada más
# (no el máximo de la pantalla como `ventanaComun()` de la Simulación), así que aquí solo
# se ve afectado un comparador MÁS VIEJO que el base. Medido sobre el universo real:
# 10 combinaciones, peor error 2.94 pp, signo variable (spec Q6 §3). El arreglo es el
# mismo: dato precalculado en Python (`DATA.idxDesde` desde `trg_real_data`), no fórmula.
#
# `series()` del componente Real lee dos globales del IIFE: `DATA` (vía `idxAt`) y `F`
# (las incepciones). `_correr_js` ya inyecta `DATA`/`LAST`; `F` se inyecta aquí con la
# incepción que cada caso necesite.

_HTML_REAL_FN = "series"


def _fn_real(incep_x: int) -> str:
    """`idxAt` + `F` + la `series()` EXTRAÍDA de `comparacion_real.html` — mismos
    globales que le da el IIFE del componente, con `F["X"].incep` fijado por el test."""
    return (_IDX_AT
            + 'var F = {"X": {"incep": ' + str(incep_x) + "}};\n"
            + _extraer_funcion_de(_HTML_REAL, _HTML_REAL_FN))


@_node
def test_q6_real_con_drip_roc_reproduce_el_motor(monkeypatch):
    """El test que paga la spec (Q6 §5.1): gemelo de
    `test_q5_con_drip_roc_reproduce_el_motor` con la firma de la vista Real —
    `series(tk, mode, baseIncep)`, que calcula `startM` dentro. El esperado sale del
    MOTOR (una compra nueva corrida desde la fecha real de `startM`), nunca de una
    transcripción de la fórmula. `F["X"].incep` (2) es MENOR que los dos `baseIncep`
    probados (5, 18), así que `startM == baseIncep` — el caso del comparador más viejo
    que el fondo base, que es el único afectado en esta vista."""
    from ui.adapters import _fecha_por_mes, _mensualizar_desde

    history = _historia_sintetica()
    monkeypatch.setattr(backtest, "fetch_history",
                        lambda ticker, start=None, end=None: history)

    origen_start = history.index.min()
    origen = [int(origen_start.year), int(origen_start.month) - 1]
    POL = dict(nra_rate=0.30, roc_pct_by_year={2024: 50.0, 2025: 50.0})
    CAPITAL = 10000.0

    r = backtest.run_backtest("X", start_date=origen_start, initial_capital=CAPITAL,
                              drip=True, history=history, **POL)
    idx = {"roc": {"X": _mensualizar_desde(r.daily["total_value"], origen)}}
    fecha_por_mes = _fecha_por_mes(r.daily["total_value"], origen)
    last = max(int(k) for k in idx["roc"]["X"])

    incep_x = 2
    fn = _fn_real(incep_x)

    for base_incep in (5, 18):
        start_m = max(base_incep, incep_x)
        assert 0 < start_m < last, f"startM={start_m} fuera de rango (0, {last})"

        # ORÁCULO: compra nueva en startM — el motor arranca con el receivable en cero
        # por construcción, que es justo lo que NO tiene quien ya venía desde antes.
        r_nueva = backtest.run_backtest("X", start_date=fecha_por_mes[str(start_m)],
                                        initial_capital=CAPITAL, drip=True,
                                        history=history, **POL)
        compra_nueva_pct = r_nueva.total_return_pct

        idx_desde = {"X": {str(start_m): _mensualizar_desde(
            r_nueva.daily["total_value"], origen)}}
        data = {"idx": idx, "idxDesde": idx_desde}
        rep = _correr_js(fn, data, last=last,
                         llamada=f'series("X", "roc", {base_incep})')

        assert rep["startM"] == start_m, (
            f"baseIncep={base_incep}: startM = {rep['startM']}, esperaba {start_m}")
        assert rep["data"][str(last)] * 100 == pytest.approx(compra_nueva_pct, abs=1e-4), (
            f"baseIncep={base_incep}: series() dio {rep['data'][str(last)]*100:.6f}%, "
            f"compra nueva (run_backtest desde startM) dio {compra_nueva_pct:.6f}%")

        # La serie sigue naciendo en 0% en startM — el rebase no mueve el punto de partida.
        assert rep["data"][str(start_m)] == pytest.approx(0.0, abs=1e-12), (
            f"baseIncep={base_incep}: la serie no arranca en 0%")

        # `late` es del comparador contra el base: incep_x (2) > baseIncep (5/18) = False.
        assert rep["late"] is False, f"baseIncep={base_incep}: late debe ser False"

        # Y el cálculo VIEJO no coincide: si coincidiera, la fixture no tendría receivable
        # pre-startM y este test estaría verde sin vigilar nada.
        viejo = idx["roc"]["X"][str(last)] / idx["roc"]["X"][str(start_m)] - 1
        assert rep["data"][str(last)] != pytest.approx(viejo, abs=1e-6), (
            f"baseIncep={base_incep}: series() sigue dando el valor viejo — la fixture "
            "no tiene receivable pre-startM o el fix no se aplicó")


# Fixture de números redondos para la degradación: el esperado es aritmética de mano
# (240/120 − 1 = 1.0 · 300/120 − 1 = 1.5 · 300/240 − 1 = 0.25), no la fórmula auditada.
_Q6_IDX = {"0": 100.0, "1": 120.0, "2": 240.0, "3": 300.0}
_Q6_ESPERADO_STARTM1 = {1: 0.0, 2: 1.0, 3: 1.5}


@_node
def test_q6_real_degrada_y_respeta_el_modo():
    """Q6 §5.2, tres piezas en un solo test (el mutante M3 apunta a este nodeid):

    (a) Sin `DATA.idxDesde`, con `idxDesde` vacío, y con `idxDesde` SIN ese `startM`:
        `series()` da exactamente `idx[m]/idx[startM] − 1` y NUNCA `NaN` (las claves
        vienen de JSON: un mes ausente daría `undefined` y la división un `NaN`
        silencioso — mutante M2). Los tres casos, en modo `roc`.
    (b) Con `idxDesde` presente y valores TRAMPA deliberadamente distintos, en `bruto`
        y `plano`: sigue dando la fórmula de siempre. Si alguien quita el
        `mode === "roc"`, esto cae (mutante M3).
    (c) `late` sale correcto en las DOS ramas: la del dato precalculado y la del
        fallback (aquí con `F["X"].incep` (2) > `baseIncep` (1) → `late === true`,
        que es el comparador más nuevo que el base)."""
    fn = _fn_real(1)      # incep == baseIncep → startM=1, late=False
    fn_late = _fn_real(2)  # incep > baseIncep → startM=2, late=True

    # (a) los tres fallbacks, en roc
    trampas = [
        ("sin la clave", None),
        ("idxDesde vacío", {}),
        ("idxDesde sin ese startM", {"X": {"0": {"0": 9.0, "1": 9.0, "2": 9.0, "3": 9.0}}}),
    ]
    for etiqueta, idx_desde in trampas:
        data = {"idx": {"roc": {"X": _Q6_IDX}}}
        if idx_desde is not None:
            data["idxDesde"] = idx_desde
        rep = _correr_js(fn, data, last=3, llamada='series("X", "roc", 1)')
        assert rep["startM"] == 1, f"{etiqueta}: startM = {rep['startM']}"
        assert rep["late"] is False, f"{etiqueta}: late debe ser False (incep 1 == base 1)"
        for m, v in _Q6_ESPERADO_STARTM1.items():
            # Trampa 6: `JSON.stringify` pierde los `undefined` y los `NaN` salen `null` —
            # afirmar que la clave ESTÁ y que no es null antes de comparar.
            assert str(m) in rep["data"] and rep["data"][str(m)] is not None, (
                f"{etiqueta} m={m}: valor ausente o NaN — la degradación produjo NaN")
            assert rep["data"][str(m)] == pytest.approx(v, abs=1e-9), (
                f"{etiqueta} m={m}: dio {rep['data'][str(m)]}, esperado {v}")

    # (b) bruto y plano ignoran idxDesde aunque traiga valores trampa (M3)
    for modo in ("bruto", "plano"):
        data = {
            "idx": {modo: {"X": _Q6_IDX}},
            "idxDesde": {"X": {"1": {"1": 7.0, "2": 7.0, "3": 7.0}}},
        }
        rep = _correr_js(fn, data, last=3, llamada=f'series("X", "{modo}", 1)')
        for m, v in _Q6_ESPERADO_STARTM1.items():
            assert rep["data"][str(m)] == pytest.approx(v, abs=1e-9), (
                f"{modo} m={m}: dio {rep['data'][str(m)]}, esperado {v} — "
                "¿se quitó el guard `mode === \"roc\"`?")

    # (c) late=True en la rama del dato precalculado (valores distintos a idx a
    # propósito, para confirmar que se usó el dato: 600/500 − 1 = 0.2, no 300/240 − 1)
    data = {"idx": {"roc": {"X": _Q6_IDX}},
            "idxDesde": {"X": {"2": {"2": 500.0, "3": 600.0}}}}
    rep = _correr_js(fn_late, data, last=3, llamada='series("X", "roc", 1)')
    assert rep["startM"] == 2, f"startM = {rep['startM']}, esperaba max(1, 2) = 2"
    assert rep["late"] is True, "incep (2) > baseIncep (1): late debe ser True (rama dato)"
    assert rep["data"]["2"] == pytest.approx(0.0, abs=1e-12)
    assert rep["data"]["3"] == pytest.approx(0.2, abs=1e-9), (
        f"rama dato: dio {rep['data']['3']} — 600/500 − 1 = 0.2")

    # (c') late=True en la rama del fallback (sin idxDesde: 300/240 − 1 = 0.25)
    rep = _correr_js(fn_late, {"idx": {"roc": {"X": _Q6_IDX}}}, last=3,
                     llamada='series("X", "roc", 1)')
    assert rep["late"] is True, "incep (2) > baseIncep (1): late debe ser True (fallback)"
    assert rep["data"]["2"] == pytest.approx(0.0, abs=1e-12)
    assert rep["data"]["3"] == pytest.approx(0.25, abs=1e-9), (
        f"fallback: dio {rep['data']['3']} — 300/240 − 1 = 0.25")
