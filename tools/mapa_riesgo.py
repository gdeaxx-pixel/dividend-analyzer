"""Cifras de los dos mapas de riesgo de la nota de Valuación, con el motor de la app.

Uso, con cwd en la raíz del repo o de una copia sacada con `git archive`:

    .venv/bin/python -I -B tools/mapa_riesgo.py --historia-a CARPETA [--historia-b CARPETA]

Todo va antes de impuestos (modo `bruto` de `ui.adapters._politica_fiscal`): sin retención y sin
devolución de capital. Mapa B: cada acción contra su YieldMax, reinvirtiendo y cobrando, con el
caché de precios del repo. Mapa A: fondos de largo plazo en cuatro periodos, con la historia que
pasa quien llama (`{TK}.csv` o `{TK}.parquet`: fecha, `Close` sin ajustar por dividendo y
`Dividends`). No baja nada de la red. Escribe JSON por stdout; si los datos no pasan sus
controles, sale con código 2 y el motivo por stderr.
"""
import argparse
import contextlib
import json
import math
import sys
import warnings
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

with contextlib.redirect_stdout(sys.stderr):
    import backtest  # noqa: E402
    from ui import adapters  # noqa: E402

CAPITAL = 10_000.0
PAREJAS = [("NVDA", "NVDY"), ("TSLA", "TSLY"), ("MSTR", "MSTY")]
REFERENCIAS = ["SCHB", "SMH"]
INICIO_B = "2024-02-22"
FONDOS_A = ["SCHB", "QQQ", "XLK", "SMH"]
ANIOS_A = [10, 5, 3]
DESDE_A = "2011-12-31"
MERCADO = "SCHB"
FUERTES = 0.8
SUPUESTOS = [
    "Antes de impuestos: ni retención ni impuesto de ningún país. Así le llega cada pago a un residente fiscal de Estados Unidos.",
    "Reinvirtiendo, cada pago se reinvierte al cierre del día ex.",
    "Cobrando, el efectivo no gana interés.",
    "Compra al cierre del día de compra; el pago de ese mismo día no cuenta.",
]


class DatosMalos(Exception):
    pass


def leer(carpeta, tk):
    carpeta = Path(carpeta)
    pq, csv = carpeta / f"{tk}.parquet", carpeta / f"{tk}.csv"
    if pq.exists():
        h = pd.read_parquet(pq)
    elif csv.exists():
        h = pd.read_csv(csv, index_col=0)
    else:
        raise DatosMalos(f"{tk}: no está en {carpeta}")
    if not {"Close", "Dividends"} <= set(h.columns):
        raise DatosMalos(f"{tk}: le falta Close o Dividends")
    h = h[["Close", "Dividends"]].astype(float)
    h.index = pd.to_datetime(pd.Index(h.index).astype(str).str[:10])
    return h.sort_index()


def filas_buenas(tk, h, malas):
    """Close sin NaN y > 0, Dividends sin NaN, fechas únicas. Una fila mala sin pago se quita
    y se anota; con pago, o con el pago desconocido, se para."""
    if not h.index.is_unique:
        raise DatosMalos(f"{tk}: fechas repetidas")
    mala = h["Close"].isna() | (h["Close"] <= 0) | h["Dividends"].isna()
    for fecha, fila in h[mala].iterrows():
        con_pago = pd.isna(fila["Dividends"]) or fila["Dividends"] > 0
        malas.append({"tk": tk, "fecha": str(fecha.date()),
                      "Close": None if pd.isna(fila["Close"]) else float(fila["Close"]),
                      "Dividends": None if pd.isna(fila["Dividends"]) else float(fila["Dividends"]),
                      "accion": "para" if con_pago else "quitada"})
        if con_pago:
            raise DatosMalos(f"{tk} {fecha.date()}: fila mala con pago")
    return h[~mala]


def tasa_bruto(tk):
    tasa, roc = adapters._politica_fiscal(tk, "bruto", {}, {})
    if tasa != 0.0 or roc:
        raise DatosMalos(f"{tk}: la política «bruto» ya no es antes de impuestos ({tasa}, {roc})")
    return tasa


def correr(tk, h, inicio, fin, drip, capital):
    with contextlib.redirect_stdout(sys.stderr):
        res = backtest.run_backtest(tk, inicio, initial_capital=capital, drip=drip, nra_rate=tasa_bruto(tk),
                                    end_date=fin, history=h, roc_pct_by_year=None)
    if len(res.daily) < 2:
        raise DatosMalos(f"{tk}: menos de dos cierres entre {pd.Timestamp(inicio).date()} y {pd.Timestamp(fin).date()}")
    return res


def metricas_serie(v, capital):
    dias = (v.index[-1] - v.index[0]).days
    r = v.pct_change().iloc[1:]
    vol = float(r.std(ddof=1) * math.sqrt(252))
    dd = v / v.cummax() - 1
    piso = dd.idxmin()
    pico = v.loc[:piso].idxmax()
    tras = v.loc[piso:]
    rec = tras[tras >= v.loc[pico]]
    return {
        "inicio": str(v.index[0].date()), "fin": str(v.index[-1].date()), "dias": int(dias),
        "rendimiento_anual": float((v.iloc[-1] / v.iloc[0]) ** (365.25 / dias) - 1),
        "se_mueve": vol,
        "peor_caida": float(dd.min()),
        "pico": str(pico.date()), "piso": str(piso.date()),
        "recupera": str(rec.index[0].date()) if len(rec) else None,
        "semana_normal_usd": capital * vol / math.sqrt(52),
        "valor_final": float(v.iloc[-1]),
    }


def metricas(res, capital):
    d = res.daily
    m = metricas_serie(d["total_value"], capital)
    m["valor_final"] = float(res.final_total_value)
    if not res.drip:
        m["sigue_invertido"] = float(d["portfolio_value"].iloc[-1])
        m["efectivo_cobrado"] = float(d["cash_accum"].iloc[-1])
    return m


def fecha_compra(indice, T, anios):
    tope = pd.Timestamp(DESDE_A) if anios is None else T - pd.DateOffset(years=anios)
    previos = indice[indice <= tope]
    if not len(previos):
        raise DatosMalos(f"la historia del Mapa A empieza el {indice[0].date()}, después de {tope.date()}")
    return previos[-1]


def semanal(res):
    v = res.daily["total_value"]
    return v.resample("W-FRI").last().dropna().pct_change().dropna()


def crece(r):
    return float(np.prod(1 + r.to_numpy()) - 1)


def semanas(B, parejas, inicio, T):
    js = {"inicio": inicio, "fin": str(T.date()), "semana": "último cierre de cada semana",
          "fuertes": "la quinta parte de las semanas en que más subió la acción", "parejas": {}}
    for acc, f in parejas:
        ra = semanal(B[acc])
        fuerte = ra >= ra.quantile(FUERTES)
        resto = ~fuerte
        d = {"fondo": f, "semanas": len(ra), "fuertes": int(fuerte.sum()), "resto": int(resto.sum()),
             "accion_fuertes": crece(ra[fuerte]), "accion_resto": crece(ra[resto])}
        for variante in ("reinvirtiendo", "cobrando"):
            rf = semanal(B[f"{f}_{variante}"]).reindex(ra.index)
            if rf.isna().any():
                raise DatosMalos(f"{f} {variante}: semanas sin dato")
            d[variante] = {"fondo_fuertes": crece(rf[fuerte]), "fondo_resto": crece(rf[resto]),
                           "gana_fondo_resto": float((rf[resto] > ra[resto]).mean())}
        js["parejas"][acc] = d
    return js


def con_base(m, T):
    return {**m, "base": "bruto", "momento": f"al cierre del {T.date()}"}


def linea_mercado(s, mercado):
    if not (math.isfinite(s["se_mueve"]) and s["se_mueve"] > 0):
        raise DatosMalos(f"{mercado}: no se movió en la ventana, no hay línea de mercado")
    return {"pendiente": s["rendimiento_anual"] / s["se_mueve"], "de": mercado}


def calcular(historia_a, historia_b, capital=CAPITAL, parejas=PAREJAS, referencias=REFERENCIAS,
             inicio_b=INICIO_B, fondos_a=FONDOS_A, anios_a=ANIOS_A, mercado=MERCADO):
    if mercado not in referencias or mercado not in fondos_a:
        raise DatosMalos(f"el mercado ({mercado}) tiene que estar en las referencias y en los fondos del Mapa A")
    malas = []
    hb = {tk: filas_buenas(tk, leer(historia_b, tk), malas)
          for tk in sorted({t for p in parejas for t in p} | set(referencias))}
    ultimos = {tk: h.index[-1] for tk, h in hb.items()}
    T = max(ultimos.values())
    if any(u != T for u in ultimos.values()):
        raise DatosMalos("el caché no termina el mismo día: " + ", ".join(f"{k} {v.date()}" for k, v in sorted(ultimos.items())))
    T1 = hb[mercado].index[-2]
    arranques = {tk: h.index[h.index >= pd.Timestamp(inicio_b)] for tk, h in hb.items()}
    if any(not len(a) for a in arranques.values()):
        raise DatosMalos(f"hay símbolos sin cierres desde el {inicio_b}")
    if len({a[0] for a in arranques.values()}) > 1:
        raise DatosMalos("el Mapa B no arranca el mismo día: " + ", ".join(f"{k} {a[0].date()}" for k, a in sorted(arranques.items())))
    for tk, h in hb.items():
        if T1 not in h.index:
            raise DatosMalos(f"{tk}: falta el cierre del {T1.date()}")
    ha = {}
    for tk in fondos_a:
        h = leer(historia_a, tk)
        h = h[h.index <= T]
        if not len(h) or h.index[-1] != T:
            raise DatosMalos(f"{tk}: la historia del Mapa A no llega al {T.date()}")
        ha[tk] = filas_buenas(tk, h, malas)
        if T1 not in ha[tk].index:
            raise DatosMalos(f"{tk}: a la historia del Mapa A le falta el cierre del {T1.date()}")
    periodos = [("desde-2012", None)] + [(f"{n}-anios", n) for n in anios_a]
    compras = {pid: fecha_compra(ha[mercado].index, T, n) for pid, n in periodos}
    for pid, c in compras.items():
        for tk in fondos_a:
            if c not in ha[tk].index:
                raise DatosMalos(f"{tk} no cotizó el {c.date()} ({pid})")

    def serie_b(fin):
        out = {}
        for accion, fondo in parejas:
            out[accion] = correr(accion, hb[accion], inicio_b, fin, True, capital)
            out[f"{fondo}_reinvirtiendo"] = correr(fondo, hb[fondo], inicio_b, fin, True, capital)
            out[f"{fondo}_cobrando"] = correr(fondo, hb[fondo], inicio_b, fin, False, capital)
        for tk in referencias:
            out[tk] = correr(tk, hb[tk], inicio_b, fin, True, capital)
        return out

    def serie_a(fin):
        return {(pid, tk): correr(tk, ha[tk], compras[pid], fin, True, capital)
                for pid, _ in periodos for tk in fondos_a}

    B, B1, A, A1 = serie_b(T), serie_b(T1), serie_a(T), serie_a(T1)
    m = lambda res, t: con_base(metricas(res, capital), t)  # noqa: E731
    mapa_b = {"inicio": inicio_b, "parejas": [], "referencias": {}}
    for accion, fondo in parejas:
        ks = (accion, f"{fondo}_reinvirtiendo", f"{fondo}_cobrando")
        mapa_b["parejas"].append({"accion": accion, "fondo": fondo,
                                  "series": {k: m(B[k], T) for k in ks},
                                  "en_cierre_anterior": {k: m(B1[k], T1) for k in ks}})
    for tk in referencias:
        mapa_b["referencias"][tk] = m(B[tk], T)
        mapa_b["referencias"][tk + "_en_cierre_anterior"] = m(B1[tk], T1)
    mapa_b["linea_mercado"] = linea_mercado(mapa_b["referencias"][mercado], mercado)
    mapa_b["semanas"] = semanas(B, parejas, inicio_b, T)
    mapa_a = {"periodos": []}
    for pid, _ in periodos:
        series = {tk: m(A[(pid, tk)], T) for tk in fondos_a}
        mapa_a["periodos"].append({
            "id": pid, "compra": str(compras[pid].date()), "series": series,
            "en_cierre_anterior": {tk: m(A1[(pid, tk)], T1) for tk in fondos_a},
            "linea_mercado": linea_mercado(series[mercado], mercado),
        })
    return {
        "base": "bruto", "base_texto": "Antes de impuestos",
        "T": str(T.date()), "T_anterior": str(T1.date()), "capital": capital,
        "origen": {
            "motor": "dividend-analyzer-app backtest.run_backtest + ui.adapters._politica_fiscal('bruto')",
            "mapa_b": f"{historia_b}: precios y pagos del caché de la app",
            "mapa_a": f"{historia_a}: historia que pasó quien llama, cortada en T",
        },
        "supuestos": SUPUESTOS,
        "filas_malas": malas,
        "mapa_a": mapa_a, "mapa_b": mapa_b,
    }


def _lista(s):
    return [x.strip().upper() for x in s.split(",") if x.strip()]


def main(argv=None):
    warnings.filterwarnings("ignore")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--historia-a", required=True, help="carpeta con la historia del Mapa A")
    p.add_argument("--historia-b", default=str(RAIZ / "knowledge" / "price_cache"), help="carpeta con la historia del Mapa B")
    p.add_argument("--capital", type=float, default=CAPITAL)
    p.add_argument("--parejas", default=",".join(f"{a}:{f}" for a, f in PAREJAS), help="ACCIÓN:FONDO,…")
    p.add_argument("--referencias", default=",".join(REFERENCIAS))
    p.add_argument("--inicio-b", default=INICIO_B)
    p.add_argument("--fondos-a", default=",".join(FONDOS_A))
    p.add_argument("--anios-a", default=",".join(map(str, ANIOS_A)))
    p.add_argument("--mercado", default=MERCADO)
    a = p.parse_args(argv)
    try:
        d = calcular(a.historia_a, a.historia_b, a.capital,
                     parejas=[tuple(x.split(":")) for x in _lista(a.parejas)],
                     referencias=_lista(a.referencias), inicio_b=a.inicio_b, fondos_a=_lista(a.fondos_a),
                     anios_a=[int(x) for x in _lista(a.anios_a)], mercado=a.mercado.upper())
        texto = json.dumps(d, ensure_ascii=False, allow_nan=False)
    except DatosMalos as e:
        print(f"mapa_riesgo: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"mapa_riesgo: cifra no finita o dato inválido: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(texto + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
