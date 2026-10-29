"""Riesgo de la mezcla Dividendos/Crecimiento (vista Portafolios).

Funciones puras, sin Streamlit ni red: reciben historias ['Close', 'Dividends'] y arman los
datos que dibuja `ui/componentes/riesgo.html`. El componente compone en el navegador la mezcla
que elige el usuario; `resumen_escenario` es la misma cuenta en Python y los tests comparan
las dos (regla 3b). Fuente: `Obsidian/APPs/Dividend-Analyzer/demos/riesgo_mezcla.py`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BASE = 10_000
CORTES_NIVEL = (0.5, 5, 12, 20, 30, 80)
DIAS_MINIMOS = 60
DIAS_HISTORIA_CORTA = 250
PATRON_COMPRA = r"buy|bought|compra"


def _indice_limpio(idx) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(pd.to_datetime(idx))
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()


def _historia(hist: pd.DataFrame) -> pd.DataFrame:
    h = hist[["Close", "Dividends"]].copy()
    h.index = _indice_limpio(h.index)
    h = h[~h.index.duplicated(keep="last")].sort_index()
    h["Dividends"] = h["Dividends"].fillna(0.0)
    return h[h["Close"].notna() & (h["Close"] > 0)]


def retorno_total(hist: pd.DataFrame) -> pd.Series:
    """Retorno diario con el dividendo reinvertido el día ex: (cierre + dividendo) / cierre anterior − 1."""
    h = _historia(hist)
    return ((h["Close"] + h["Dividends"]) / h["Close"].shift(1) - 1).iloc[1:]


def rendimiento_12m(hist: pd.DataFrame, fin: pd.Timestamp) -> float:
    """Dividendos de los últimos 365 días sobre el precio de hace 365 días. Con menos de un
    año de historia se anualiza lo cobrado desde el primer día."""
    h = _historia(hist)
    h = h[h.index <= fin]
    if h.empty:
        return 0.0
    ini = fin - pd.Timedelta(days=365)
    if h.index[0] <= ini:
        return float(h["Dividends"][h.index > ini].sum() / h["Close"][h.index >= ini].iloc[0])
    dias = max((fin - h.index[0]).days, 1)
    return float(h["Dividends"].iloc[1:].sum() / h["Close"].iloc[0] * 365 / dias)


def primera_compra(stats_por_ticker: dict) -> pd.Timestamp | None:
    """Fecha de la primera compra entre los fondos dados, con el mismo criterio de compra que
    `logic.py` (columna `Action` de `stats['history']`)."""
    fechas = []
    for stats in stats_por_ticker.values():
        tx = (stats or {}).get("history")
        if tx is None or len(tx) == 0 or "Action" not in tx or "Date" not in tx:
            continue
        compras = tx[tx["Action"].astype(str).str.lower().str.contains(PATRON_COMPRA, na=False, regex=True)]
        if len(compras):
            fechas.append(pd.to_datetime(compras["Date"]).min())
    return _indice_limpio(pd.DatetimeIndex([min(fechas)]))[0] if fechas else None


def atajos(p_usuario: int | None, receta: dict | None) -> list[dict]:
    lista = []
    if p_usuario is not None:
        lista.append({"etiqueta": "Tu portafolio", "detalle": f"{p_usuario}/{100 - p_usuario}", "p": p_usuario})
    if receta:
        pct = int(receta["pct_dividendos"])
        lista.append({"etiqueta": receta["nombre"], "detalle": f"{pct}/{100 - pct}", "p": pct})
    lista.append({"etiqueta": "Mitad y mitad", "detalle": "50/50", "p": 50})
    lista.append({"etiqueta": "Solo crecimiento", "detalle": "0/100", "p": 0})
    return lista


def armar_modo(clave: str, boton: str, grupos: list[dict], historias: dict,
               compra_real: pd.Timestamp | None, lista_atajos: list[dict], p_inicial: int) -> dict:
    """Un modo del selector. `grupos` va en orden Dividendos, Crecimiento; cada uno trae
    `pesos` {ticker: peso > 0} y `referencia` (texto si el grupo es la canasta de referencia).
    Devuelve `dias_comunes` para que el llamador decida si alcanza (`DIAS_MINIMOS`)."""
    tickers = [t for g in grupos for t in g["pesos"]]
    hist = {t: _historia(historias[t]) for t in tickers}
    rets = {t: retorno_total(historias[t]) for t in tickers}
    primeros = {t: hist[t].index[0] for t in tickers}
    entrada = max(primeros.values())
    limitante = sorted(t for t in tickers if primeros[t] == entrada)[0]
    comun = None
    for t in tickers:
        comun = rets[t].index if comun is None else comun.intersection(rets[t].index)
    comun = comun[comun > entrada].sort_values()
    fin = comun[-1] if len(comun) else entrada

    def grupo(g):
        total = sum(g["pesos"].values())
        r = sum(w * rets[t].reindex(comun).to_numpy() for t, w in g["pesos"].items()) / total
        rend = sum(w * rendimiento_12m(historias[t], fin) for t, w in g["pesos"].items()) / total
        return r, rend

    r_div, rend_div = grupo(grupos[0])
    r_crec, rend_crec = grupo(grupos[1])
    fechas = [entrada] + list(comun)
    if compra_real is None or compra_real <= entrada:
        i_compra = 0
    else:
        i_compra = int(np.searchsorted(np.array(fechas, dtype="datetime64[ns]"),
                                       np.datetime64(compra_real), side="right")) - 1
    i_compra = max(0, min(i_compra, len(comun) - 1))
    return {
        "clave": clave,
        "boton": boton,
        "grupos": [{"clave": g["clave"], "nombre": g["nombre"],
                    "fondos": sorted(g["pesos"], key=lambda t: (-g["pesos"][t], t)),
                    "referencia": g.get("referencia")} for g in grupos],
        "nota": None,
        "inicio": str(entrada.date()),
        "fin": str(fin.date()),
        "limitante": limitante,
        "meses": round((fin - entrada).days / 30.44),
        "corta": len(comun) < DIAS_HISTORIA_CORTA,
        "dias_comunes": len(comun),
        "dias": [int((d - entrada).days) for d in comun],
        "div": [round(float(x), 6) for x in r_div],
        "crec": [round(float(x), 6) for x in r_crec],
        "rend_div": round(float(rend_div), 4),
        "rend_crec": round(float(rend_crec), 4),
        "compra": {"i": i_compra,
                   "fecha_real": str(compra_real.date()) if compra_real is not None else None,
                   "recortada": compra_real is not None and compra_real < entrada},
        "atajos": lista_atajos,
        "p_inicial": p_inicial,
    }


def _con_historia(mv: dict, historias: dict) -> dict:
    return {t: float(v) for t, v in mv.items() if t in historias and v and v > 0}


def _grupo_referencia(clave, nombre, lista, receta):
    return {"clave": clave, "nombre": nombre, "pesos": {t: 1.0 for t in lista}, "referencia": receta["canasta"]}


def datos_seccion(div_mv: dict, crec_mv: dict, historias: dict, receta: dict | None = None,
                  compra_real: pd.Timestamp | None = None, sin_historia=(), estres=None) -> dict | None:
    """Todo lo que dibuja el componente. `div_mv` / `crec_mv`: {ticker: valor de mercado de
    hoy} de los fondos del usuario. `receta`: la configuración privada (nombre, canasta,
    pct_dividendos, dividendos, crecimiento) o None. `estres`: función opcional
    `(pesos_dividendos, pesos_crecimiento) -> dict | None` con la simulación de 2022 de cada
    modo (`estres_2022.datos_estres`); va en `modo["estres"]`. `None` si no hay nada que simular."""
    div_u, crec_u = _con_historia(div_mv, historias), _con_historia(crec_mv, historias)
    total = sum(div_u.values()) + sum(crec_u.values())
    p_usuario = round(100 * sum(div_u.values()) / total) if total > 0 else None
    receta_ok = bool(receta) and all(t in historias for t in list(receta["dividendos"]) + list(receta["crecimiento"]))
    receta_util = receta if receta_ok else None
    lista = atajos(p_usuario, receta_util)
    p_inicial = p_usuario if p_usuario is not None else (int(receta_util["pct_dividendos"]) if receta_util else 50)
    modos, motivo = [], None

    if total > 0:
        grupos, falta = [], []
        for clave, nombre, mv, ref in (("div", "Dividendos", div_u, "dividendos"), ("crec", "Crecimiento", crec_u, "crecimiento")):
            if mv:
                grupos.append({"clave": clave, "nombre": nombre, "pesos": mv, "referencia": None})
            elif receta_util:
                grupos.append(_grupo_referencia(clave, nombre, receta_util[ref], receta_util))
            else:
                falta.append(nombre)
        if falta:
            motivo = "Para simular la mezcla hacen falta fondos de los dos grupos."
        else:
            modo = armar_modo("tus", "Tus fondos", grupos, historias, compra_real, lista, p_inicial)
            if modo["dias_comunes"] < DIAS_MINIMOS:
                motivo = f"Tus fondos solo tienen {modo['dias_comunes']} días de historia en común."
            else:
                notas = [f"{g['nombre']}: no tienes fondos de este grupo; usamos la {g['referencia'][0].lower() + g['referencia'][1:]}."
                         for g in modo["grupos"] if g["referencia"]]
                if sin_historia:
                    notas.append("Sin historia de precios, fuera de la simulación: " + ", ".join(sorted(sin_historia)) + ".")
                modo["nota"] = " ".join(notas) or None
                modo["estres"] = estres(grupos[0]["pesos"], grupos[1]["pesos"]) if estres else None
                modos.append(modo)

    if receta_util:
        grupos = [_grupo_referencia("div", "Dividendos", receta_util["dividendos"], receta_util),
                  _grupo_referencia("crec", "Crecimiento", receta_util["crecimiento"], receta_util)]
        modo = armar_modo("greco", receta_util["canasta"], grupos, historias, compra_real, lista, p_inicial)
        if modo["dias_comunes"] >= DIAS_MINIMOS:
            modo["estres"] = estres(grupos[0]["pesos"], grupos[1]["pesos"]) if estres else None
            modos.append(modo)

    if not modos:
        return None
    aviso = None
    if motivo and modos[0]["clave"] == "greco":
        canasta = receta_util["canasta"]
        aviso = f"{motivo} Te mostramos la {canasta[0].lower() + canasta[1:]}."
    return {"modo_inicial": modos[0]["clave"], "aviso": aviso, "modos": modos}


def nivel(vol: float) -> int:
    return 1 + sum(vol >= c for c in CORTES_NIVEL)


def _peor_entrada(v: np.ndarray) -> int:
    pico, mejor, ent = 0, 0.0, 0
    for i in range(1, len(v)):
        if v[i] > v[pico]:
            pico = i
        dd = 1 - v[i] / v[pico]
        if dd > mejor:
            mejor, ent = dd, pico
    return ent


def resumen_escenario(modo: dict, p: int, entrada: str) -> dict:
    """La misma cuenta que el motor JS del componente, para compararlas en los tests."""
    q = p / 100
    r_div, r_crec = np.array(modo["div"]), np.array(modo["crec"])
    r = q * r_div + (1 - q) * r_crec
    vm = np.concatenate([[1.0], np.cumprod(1 + r)])
    vg = np.concatenate([[1.0], np.cumprod(1 + r_crec)])
    n = len(r)
    desde = _peor_entrada(vm) if entrada == "peor" else max(0, min(n - 1, modo["compra"]["i"]))
    cm, cg = BASE * vm[desde:] / vm[desde], BASE * vg[desde:] / vg[desde]
    km, kg = int(np.argmin(cm)), int(np.argmin(cg))
    rec = None
    if cm[km] < BASE:
        arriba = np.nonzero(cm[km:] >= BASE)[0]
        rec = km + int(arriba[0]) if len(arriba) else -1
    vol = float(np.std(r, ddof=1) * np.sqrt(252) * 100)
    return {"nivel": nivel(vol), "vol": round(vol, 1),
            "dividendos": round(BASE * (q * modo["rend_div"] + (1 - q) * modo["rend_crec"])),
            "desde": desde, "min": round(float(cm[km])), "min_i": desde + km,
            "hoy": round(float(cm[-1])), "min_crec": round(float(cg[kg])), "hoy_crec": round(float(cg[-1])),
            "recupera": None if rec is None else (rec if rec < 0 else desde + rec)}
