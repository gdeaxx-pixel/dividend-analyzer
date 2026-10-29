"""Prueba de estrés «¿Y en una caída como la de 2022?» de la sección Riesgo.

Funciones puras, sin Streamlit ni red. Los fondos de dividendos YieldMax no existían en 2022, así
que se simulan con su acción (el subyacente) y su forma de trabajar: tienen la acción y venden
una opción de compra cubierta, cobrando una prima (método «A»: opción cubierta sintética con
Black-Scholes, tasa 0). Los fondos con historia real de 2022 (los de crecimiento, por ejemplo)
usan sus datos reales. `datos_estres` arma lo que dibuja `ui/componentes/riesgo.html` y
`resumen_estres` es la misma cuenta que su motor JS (regla 3b: `test_estres_2022.py` las compara).

Los parámetros (periodo de la opción, distancia del precio de ejercicio, factor de volatilidad)
están en `knowledge/estres_2022/parametros.yaml`, con su validación fuera de tiempo.
"""
from __future__ import annotations

import math
import os
import re

import numpy as np
import pandas as pd
import yaml

BASE = 10_000
GASTO = 0.0099
VENTANA_VOL = 21
PISO_VOL = 0.15
DIAS_MINIMOS = 60


def _n(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _call(s: float, k: float, t: float, sigma: float) -> float:
    """Valor Black-Scholes de una opción de compra, tasa 0. Al vencer, el valor intrínseco."""
    if t <= 1e-9:
        return max(s - k, 0.0)
    d1 = (math.log(s / k) + 0.5 * sigma * sigma * t) / (sigma * math.sqrt(t))
    return s * _n(d1) - k * _n(d1 - sigma * math.sqrt(t))


def vol_real(close: pd.Series) -> pd.Series:
    """Volatilidad anualizada de 21 sesiones de la acción, rellenada hacia atrás al inicio y
    con piso de 0.15."""
    lr = np.log(close).diff()
    return np.maximum(lr.rolling(VENTANA_VOL).std().bfill() * np.sqrt(252), PISO_VOL)


def simular(close_u: pd.Series, per: int, m: float, k: float,
            inicio: pd.Timestamp, fin: pd.Timestamp) -> pd.Series:
    """Retorno diario simulado del fondo, de la sesión siguiente a `inicio` hasta `fin`.

    `close_u`: cierre del subyacente con la historia que haya (la volatilidad usa toda). Cada
    `per` sesiones, contadas desde `inicio`, se vende una opción de compra a `S0·(1+m)` con
    volatilidad `k·vol(t0)` y se cobra su prima; el valor del fondo cada día es
    `S − call + prima`, menos el gasto anual del fondo."""
    close_u = close_u[~close_u.index.duplicated(keep="last")].sort_index()
    inicio, fin = pd.Timestamp(inicio), pd.Timestamp(fin)
    rv = vol_real(close_u)
    i_ini = close_u.index.get_loc(inicio)
    i_fin = close_u.index.searchsorted(fin, side="right") - 1
    s = close_u.to_numpy()[i_ini:i_fin + 1]
    rvw = rv.to_numpy()[i_ini:i_fin + 1]
    out = np.zeros(len(s) - 1)
    i0 = 0
    while i0 < len(s) - 1:
        i1 = min(i0 + per, len(s) - 1)
        s0, sig = s[i0], k * rvw[i0]
        strike = s0 * (1 + m)
        horizonte = per / 252
        prima = _call(s0, strike, horizonte, sig)
        previo = s0
        for j in range(i0 + 1, i1 + 1):
            tau = horizonte - (j - i0) / 252
            nav = s[j] - _call(s[j], strike, max(tau, 0.0), sig) + prima
            out[j - 1] = nav / previo - 1 - GASTO / 252
            previo = nav
        i0 = i1
    return pd.Series(out, index=close_u.index[i_ini + 1:i_fin + 1])


def _retorno_real(h: pd.DataFrame) -> pd.Series:
    h = h[~h.index.duplicated(keep="last")].sort_index()
    h = h[h["Close"] > 0]
    return ((h["Close"] + h["Dividends"].fillna(0.0)) / h["Close"].shift(1) - 1).iloc[1:]


def _parametros_fondo(parametros: dict, fondo: str) -> tuple[int, float, float]:
    p = parametros["fondos"].get(fondo) or parametros["global"]
    return int(p["per"]), float(p["m"]), float(p["k"])


def _cubre(h: pd.DataFrame | None, inicio: pd.Timestamp, fin: pd.Timestamp) -> bool:
    if h is None or len(h) == 0:
        return False
    return bool(h.index.min() <= inicio and h.index.max() >= fin and inicio in h.index)


def datos_estres(div_mv: dict, crec_mv: dict, historias_2022: dict, parametros: dict,
                 subyacentes: dict) -> dict | None:
    """Lo que dibuja el bloque «Simulación». `div_mv` / `crec_mv`: {ticker: peso} de cada
    grupo. `historias_2022`: {ticker: ['Close', 'Dividends']} con la ventana de 2022
    (los fondos reales y los subyacentes). `subyacentes`: {fondo YieldMax: ticker de su
    acción}. Un fondo de dividendos con subyacente conocido se simula; uno con historia real
    desde el inicio de la ventana usa sus datos; el resto queda fuera. `None` si algún grupo
    se queda vacío, si no hay nada que simular o la ventana común es demasiado corta."""
    v = parametros["ventana"]
    inicio, fin = pd.Timestamp(v["inicio"]), pd.Timestamp(v["fin"])
    banda = float(parametros["banda"])
    hist = {t: h for t, h in historias_2022.items() if h is not None}

    def clasificar(pesos: dict, simulable: bool):
        usados, fuera = {}, []
        for f, w in pesos.items():
            if not w or w <= 0:
                continue
            u = subyacentes.get(f) if simulable else None
            if u and _cubre(hist.get(u), inicio, fin):
                usados[f] = ("sim", u, float(w))
            elif _cubre(hist.get(f), inicio, fin):
                usados[f] = ("real", f, float(w))
            else:
                fuera.append(f)
        return usados, fuera

    div, fuera_d = clasificar(div_mv, True)
    crec, fuera_c = clasificar(crec_mv, False)
    if not div or not crec:
        return None
    sims = {f: x for f, x in div.items() if x[0] == "sim"}
    if not sims:
        return None

    reales_por_fondo = {f: _retorno_real(hist[x[1]]) for f, x in {**div, **crec}.items() if x[0] == "real"}
    base = None
    for r in list(reales_por_fondo.values()) + [_retorno_real(hist[x[1]]) for x in sims.values()]:
        base = r.index if base is None else base.intersection(r.index)
    idx = base[(base > inicio) & (base <= fin)].sort_values()
    if len(idx) < DIAS_MINIMOS:
        return None

    def sim(f, dk):
        per, m, k = _parametros_fondo(parametros, f)
        close = hist[sims[f][1]]["Close"]
        return simular(close, per, m, k + dk, inicio, fin).reindex(idx).to_numpy()

    def serie_fondo(f, dk):
        return sim(f, dk) if f in sims else reales_por_fondo[f].reindex(idx).to_numpy()

    def grupo(g, dk):
        total = sum(x[2] for x in g.values())
        return sum(x[2] * serie_fondo(f, dk) for f, x in g.items()) / total

    # La banda mueve solo la prima de los fondos simulados; los datos reales no cambian.
    r_div, r_bajo, r_alto = grupo(div, 0.0), grupo(div, -banda), grupo(div, banda)
    r_crec = grupo(crec, 0.0)
    for r in (r_div, r_bajo, r_alto, r_crec):
        if np.isnan(r).any():
            return None
    primeros = {x[1]: hist[x[1]].index.min() for x in [*div.values(), *crec.values()]}
    limitantes = sorted(t for t, d in primeros.items() if d == inicio)
    peso = lambda g: sorted(g, key=lambda f: (-g[f][2], f))
    redondea = lambda r: [round(float(x), 6) for x in r]
    reales = peso({f: x for f, x in {**div, **crec}.items() if x[0] == "real"})
    return {
        "inicio": str(inicio.date()),
        "fin": str(idx[-1].date()),
        "limitante": limitantes[0] if limitantes else None,
        "dias": [int((d - inicio).days) for d in idx],
        "div": redondea(r_div), "div_bajo": redondea(r_bajo), "div_alto": redondea(r_alto),
        "crec": redondea(r_crec),
        "simulados": peso(sims),
        "subyacente": {f: x[1] for f, x in sims.items()},
        "reales": reales,
        "fuera": sorted(fuera_d + fuera_c),
    }


def _peor_entrada(v: np.ndarray) -> int:
    pico, mejor, ent = 0, 0.0, 0
    for i in range(1, len(v)):
        if v[i] > v[pico]:
            pico = i
        dd = 1 - v[i] / v[pico]
        if dd > mejor:
            mejor, ent = dd, pico
    return ent


def _indice(r_div, r_crec, q):
    r = q * np.asarray(r_div) + (1 - q) * np.asarray(r_crec)
    return np.concatenate([[1.0], np.cumprod(1 + r)])


def resumen_estres(estres: dict, p: int) -> dict:
    """La misma cuenta que `estres()` del componente (motor JS), para compararlas en los tests.
    La entrada es el peor día de la serie central; la banda se mide desde esa misma entrada."""
    q = p / 100
    vm = _indice(estres["div"], estres["crec"], q)
    desde = _peor_entrada(vm)

    def camino(v):
        return BASE * v[desde:] / v[desde]

    cm = camino(vm)
    cg = camino(_indice(estres["div"], estres["crec"], 0.0))
    cb = camino(_indice(estres["div_bajo"], estres["crec"], q))
    ca = camino(_indice(estres["div_alto"], estres["crec"], q))
    km, kg = int(np.argmin(cm)), int(np.argmin(cg))
    lo, hi = float(cb[int(np.argmin(cb))]), float(ca[int(np.argmin(ca))])
    rec = None
    if cm[km] < BASE:
        arriba = np.nonzero(cm[km:] >= BASE)[0]
        rec = -1 if not len(arriba) else desde + km + int(arriba[0])
    return {"desde": desde, "min": round(float(cm[km])), "min_i": desde + km,
            "hoy": round(float(cm[-1])), "min_crec": round(float(cg[kg])),
            "hoy_crec": round(float(cg[-1])),
            "rango": [round(min(lo, hi)), round(max(lo, hi))], "recupera": rec}


def subyacentes_yieldmax(instrumentos: dict) -> dict:
    """{fondo YieldMax: ticker de su acción} a partir de `logic.load_instruments()`. Los que
    siguen varias acciones o un índice ('Multi', 'Mag-7', 'Oro'…) no son un ticker: quedan fuera."""
    return {t: str(p["underlying"]) for t, p in instrumentos.items()
            if isinstance(p, dict) and p.get("type") == "yieldmax"
            and re.fullmatch(r"[A-Z]{1,5}", str(p.get("underlying") or ""))}


def cargar_parametros(ruta: str | None = None) -> dict:
    ruta = ruta or os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge", "estres_2022",
                                "parametros.yaml")
    with open(ruta, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def filas_modal(parametros: dict) -> dict:
    """Lo que muestra el modal «¿Cómo simulamos 2022?»: la prueba fuera de tiempo por fondo."""
    v = parametros["validacion"]
    return {"desde": str(v["desde"]), "hasta": str(v["hasta"]),
            "filas": [{"fondo": f, "real": float(x["real"]), "simulada": float(x["simulada"])}
                      for f, x in v["fondos"].items()]}
