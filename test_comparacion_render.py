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

_node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node ausente: el gate de CONSECUENCIA no corre — y un skip no es un pass")


def _extraer_funcion(nombre: str) -> str:
    """Extrae `function NOMBRE(...) { ... }` del componente por balance de llaves —
    sin regex de una línea, que se corta en la primera `}` (hay varias anidadas)."""
    with open(_HTML, encoding="utf-8") as f:
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
    from ui.adapters import _mensualizar_desde

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
            serie = r.daily["portfolio_value"].sort_index()
            grupos = serie.groupby(serie.index.to_period("M"))
            fecha_por_mes = {}
            for periodo, grp in grupos:
                fecha = grp.index.max()
                m = (periodo.year - origen[0]) * 12 + (periodo.month - 1 - origen[1])
                fecha_por_mes[m] = fecha
            fecha_por_mes[0] = origen_start
    precio_sin = {"X": precio_sin_m}

    last = max(int(k) for k in precio_sin_m)
    fn = _extraer_funcion("seriesSin")

    # dos meses de corte, análogos a 2025-03-31 / 2025-12-31 de la spec: uno temprano y
    # uno tardío, comparados contra "compra nueva" en la FECHA EXACTA de ese índice.
    for t0 in (5, 18):
        assert 0 < t0 < last, f"t0={t0} fuera de rango (0, {last})"
        fecha_t0 = fecha_por_mes[t0]

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
    """`series()` (Con DRIP) usa la misma división por `base0` de siempre — Q4 NO la
    toca. Control: en bruto y plano da lo mismo antes y después (el modo roc se excluye
    a propósito — Q5, hallazgo nuevo no arreglado en esta rama: con DRIP las acciones
    cambian después de t0 y ni la fórmula vieja ni la de Q4 aciertan)."""
    fn = _IDX_AT + _extraer_funcion("series")
    for modo in ("bruto", "plano"):
        data = {"idx": {modo: {"X": {"0": 1000.0, "1": 1050.0, "2": 1200.0}}}}
        rep = _correr_js(fn, data, last=2, llamada=f'series("X", 0, "{modo}")')
        esperado = {m: data["idx"][modo]["X"][str(m)] / data["idx"][modo]["X"]["0"] - 1
                   for m in (0, 1, 2)}
        for m, v in esperado.items():
            assert rep["data"][str(m)] == pytest.approx(v, abs=1e-9), (
                f"{modo} m={m}: series() cambió — Q4 no debía tocarla")
