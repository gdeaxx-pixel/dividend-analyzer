"""Cifras de los dos mapas de riesgo de la nota de Valuación, con el motor de la app.

Uso, con cwd en la raíz del repo o de una copia sacada con `git archive`:

    .venv/bin/python -I -B tools/mapa_riesgo.py --historia-a CARPETA [--historia-b CARPETA]

Todo va antes de impuestos (modo `bruto` de `ui.adapters._politica_fiscal`): sin retención y sin
devolución de capital. Mapa B: cada acción contra su YieldMax, reinvirtiendo y cobrando, con el
caché de precios del repo, desde `--inicio-b` y en las paradas de la barra de la nota (cada año
calendario, los últimos 3 años y desde `--inicio-b`). Mapa A: fondos de largo plazo en cuatro
periodos, con la historia que pasa quien llama (`{TK}.csv` o `{TK}.parquet`: fecha, `Close` sin ajustar por dividendo y
`Dividends`). No baja nada de la red. Escribe JSON por stdout; si los datos no pasan sus
controles, sale con código 2 y el motivo por stderr.
"""
import argparse
import contextlib
import json
import math
import re
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
ANIOS_PARADA_B = 3
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
DESDE_A = "2011-12-31"
MERCADO = "SCHB"
FUERTES = 0.8
SIMBOLO = re.compile(r"[A-Z0-9^][A-Z0-9.^=-]{0,14}")
SUPUESTOS = [
    "Antes de impuestos: ni retención ni impuesto de ningún país. Así le llega cada pago a un residente fiscal de Estados Unidos.",
    "Reinvirtiendo, cada pago se reinvierte al cierre del día ex.",
    "Cobrando, el efectivo no gana interés.",
    "Compra al cierre del día de compra; el pago de ese mismo día no cuenta.",
]


class DatosMalos(Exception):
    pass


def validar(capital, parejas, referencias, inicio_b, fondos_a, anios_a, mercado):
    if not (math.isfinite(capital) and capital > 0):
        raise DatosMalos(f"el capital tiene que ser un número positivo: {capital}")
    try:
        fecha = pd.Timestamp(inicio_b)
    except (ValueError, TypeError):
        fecha = pd.NaT
    if pd.isna(fecha):
        raise DatosMalos(f"el inicio del Mapa B no es una fecha: {inicio_b!r}")
    if any(len(p) != 2 for p in parejas):
        raise DatosMalos("cada pareja va como ACCIÓN:FONDO")
    de_parejas = [t for p in parejas for t in p]
    raros = [s for s in [*de_parejas, *referencias, *fondos_a, mercado]
             if not (isinstance(s, str) and SIMBOLO.fullmatch(s))]
    if raros:
        raise DatosMalos("símbolos no válidos: " + ", ".join(map(repr, raros)))
    for nombre, lista in (("las parejas", de_parejas), ("las referencias", list(referencias)),
                          ("los fondos del Mapa A", list(fondos_a)), ("los años del Mapa A", list(anios_a))):
        if len(set(lista)) != len(lista):
            raise DatosMalos(f"hay repetidos en {nombre}: {lista}")
    if any(isinstance(n, bool) or not isinstance(n, int) or n <= 0 for n in anios_a):
        raise DatosMalos(f"los años del Mapa A van en enteros positivos: {list(anios_a)}")
    if mercado not in referencias or mercado not in fondos_a:
        raise DatosMalos(f"el mercado ({mercado}) tiene que estar en las referencias y en los fondos del Mapa A")


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


def _cifra(x):
    return float(x) if math.isfinite(x) else None


def filas_buenas(tk, h, malas):
    """Close finito y mayor que 0, Dividends finito y no negativo, fechas únicas. Una fila mala sin
    pago se quita y se anota; con pago, o con el pago desconocido o imposible, se para."""
    if not h.index.is_unique:
        raise DatosMalos(f"{tk}: fechas repetidas")
    c, dv = h["Close"], h["Dividends"]
    mala = ~np.isfinite(c) | (c <= 0) | ~np.isfinite(dv) | (dv < 0)
    for fecha, fila in h[mala].iterrows():
        con_pago = fila["Dividends"] != 0
        malas.append({"tk": tk, "fecha": str(fecha.date()),
                      "Close": _cifra(fila["Close"]), "Dividends": _cifra(fila["Dividends"]),
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
    if len(res.daily) < 3:
        raise DatosMalos(f"{tk}: menos de tres cierres entre {pd.Timestamp(inicio).date()} y {pd.Timestamp(fin).date()}")
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
    """Cada semana va del último cierre de la anterior al último suyo y lleva la fecha de ese cierre;
    la primera arranca en el cierre de compra, así que el producto de las semanas da el rendimiento
    total. Con la fecha real, dos series solo empatan semana a semana si cierran el mismo día."""
    r = res.daily["total_value"].pct_change().iloc[1:]
    semana = r.index.to_period("W-FRI")
    w = (1 + r).groupby(semana).prod() - 1
    w.index = pd.DatetimeIndex(r.index.to_series().groupby(semana).max().to_numpy())
    return w


def crece(r):
    return float(np.prod(1 + r.to_numpy()) - 1)


def semanas(B, parejas, inicio, T):
    js = {"inicio": str(inicio.date()), "fin": str(T.date()), "semana": "último cierre de cada semana",
          "fuertes": "la quinta parte de las semanas en que más subió la acción", "parejas": {}}
    for acc, f in parejas:
        ra = semanal(B[acc])
        fuerte = ra >= ra.quantile(FUERTES)
        resto = ~fuerte
        if not resto.any():
            raise DatosMalos(f"{acc}: no quedan semanas fuera de las fuertes, no hay con qué comparar")
        d = {"fondo": f, "semanas": len(ra), "fuertes": int(fuerte.sum()), "resto": int(resto.sum()),
             "accion_fuertes": crece(ra[fuerte]), "accion_resto": crece(ra[resto])}
        for variante in ("reinvirtiendo", "cobrando"):
            rf = semanal(B[f"{f}_{variante}"])
            if not rf.index.equals(ra.index):
                raise DatosMalos(f"{f} {variante}: no tiene las mismas semanas que {acc}")
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


def mismas_fechas(crudas, mercado, desde, hasta, mapa):
    """Sobre las fechas que trae la fuente, antes de quitar filas malas: una fecha que falta puede
    esconder un pago, así que cuenta como un pago desconocido y se para."""
    def fechas(h):
        return h.index[(h.index >= desde) & (h.index <= hasta)]

    ref = fechas(crudas[mercado])
    for tk, h in sorted(crudas.items()):
        distintas = ref.symmetric_difference(fechas(h))
        if len(distintas):
            raise DatosMalos(f"{tk}: en el {mapa} no tiene las mismas fechas que {mercado} "
                             f"(la primera distinta, el {distintas[0].date()})")


def cortes_b(indice, T, inicio, inicio_b, primer_fondo):
    """(id, compra, fin, medida) de cada parada del Mapa B, en el orden de la barra. Un año calendario
    va del último cierre del año anterior al último suyo, o a T, y da el rendimiento del periodo; las
    otras dos dan el rendimiento por año. Hay año desde que algún fondo ya cotizaba el día de compra y
    la ventana tiene los tres cierres que pide el motor: el primer día hábil de enero todavía no."""
    cortes = []
    for anio in range(indice[0].year + 1, T.year + 1):
        compra = indice[indice < pd.Timestamp(anio, 1, 1)][-1]
        fin = indice[indice < pd.Timestamp(anio + 1, 1, 1)][-1]
        if compra >= primer_fondo and ((indice >= compra) & (indice <= fin)).sum() >= 3:
            cortes.append((str(anio), compra, fin, "total"))
    previos = indice[indice <= T - pd.DateOffset(years=ANIOS_PARADA_B)]
    if len(previos):
        cortes.append((f"{ANIOS_PARADA_B}-anios", previos[-1], T, "anual"))
    desde = pd.Timestamp(inicio_b)
    cortes.append((f"{MESES[desde.month - 1]}-{desde.year}", inicio, T, "anual"))
    return cortes


def paradas_b(crudas, buenas, parejas, referencias, T, inicio, inicio_b, mercado, capital):
    """Las series del Mapa B en cada parada. Un fondo que no cotizaba el día de compra va en null en
    sus dos versiones; su acción sí va."""
    nace = {tk: h.index[0] for tk, h in crudas.items()}
    primer_fondo = min(nace[f] for _, f in parejas)
    paradas = []
    for pid, compra, fin, medida in cortes_b(buenas[mercado].index, T, inicio, inicio_b, primer_fondo):
        vivos = {f for _, f in parejas if nace[f] <= compra}
        usados = sorted({a for a, _ in parejas} | vivos | set(referencias))
        for tk in usados:
            for fecha in (compra, fin):
                if fecha not in buenas[tk].index:
                    raise DatosMalos(f"{tk}: falta el cierre del {fecha.date()}, que usa la parada {pid}")
        mismas_fechas({tk: crudas[tk] for tk in usados}, mercado, compra, fin, f"Mapa B (parada {pid})")

        def serie(tk, drip):
            s = con_base(metricas(correr(tk, buenas[tk], compra, fin, drip, capital), capital), fin)
            s["rendimiento"] = s["rendimiento_anual"] if medida == "anual" else s["valor_final"] / capital - 1
            return s

        series = {}
        for accion, fondo in parejas:
            series[accion] = serie(accion, True)
            for variante, drip in (("reinvirtiendo", True), ("cobrando", False)):
                series[f"{fondo}_{variante}"] = serie(fondo, drip) if fondo in vivos else None
        for tk in referencias:
            series[tk] = serie(tk, True)
        paradas.append({"id": pid, "compra": str(compra.date()), "fin": str(fin.date()), "medida": medida,
                        "series": series})
    return paradas


def calcular(historia_a, historia_b, capital=CAPITAL, parejas=PAREJAS, referencias=REFERENCIAS,
             inicio_b=INICIO_B, fondos_a=FONDOS_A, anios_a=ANIOS_A, mercado=MERCADO):
    validar(capital, parejas, referencias, inicio_b, fondos_a, anios_a, mercado)
    malas = []
    crudas_b = {tk: leer(historia_b, tk) for tk in sorted({t for p in parejas for t in p} | set(referencias))}
    hb = {tk: filas_buenas(tk, h, malas) for tk, h in crudas_b.items()}
    cortas = [tk for tk, h in hb.items() if len(h) < 2]
    if cortas:
        raise DatosMalos("sin al menos dos cierres buenos: " + ", ".join(cortas))
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
    inicio = arranques[mercado][0]
    for tk, h in hb.items():
        if T1 not in h.index:
            raise DatosMalos(f"{tk}: falta el cierre del {T1.date()}")
    mismas_fechas(crudas_b, mercado, inicio, T, "Mapa B")
    crudas_a, ha = {}, {}
    for tk in fondos_a:
        crudas_a[tk] = leer(historia_a, tk)
        h = filas_buenas(tk, crudas_a[tk][crudas_a[tk].index <= T], malas)
        if not len(h) or h.index[-1] != T:
            raise DatosMalos(f"{tk}: la historia del Mapa A no llega al {T.date()}")
        if T1 not in h.index:
            raise DatosMalos(f"{tk}: a la historia del Mapa A le falta el cierre del {T1.date()}")
        ha[tk] = h
    periodos = [("desde-2012", None)] + [(f"{n}-anios", n) for n in anios_a]
    compras = {pid: fecha_compra(ha[mercado].index, T, n) for pid, n in periodos}
    for pid, c in compras.items():
        for tk in fondos_a:
            if c not in ha[tk].index:
                raise DatosMalos(f"{tk} no cotizó el {c.date()} ({pid})")
    mismas_fechas(crudas_a, mercado, min(compras.values()), T, "Mapa A")

    def serie_b(fin):
        out = {}
        for accion, fondo in parejas:
            out[accion] = correr(accion, hb[accion], inicio, fin, True, capital)
            out[f"{fondo}_reinvirtiendo"] = correr(fondo, hb[fondo], inicio, fin, True, capital)
            out[f"{fondo}_cobrando"] = correr(fondo, hb[fondo], inicio, fin, False, capital)
        for tk in referencias:
            out[tk] = correr(tk, hb[tk], inicio, fin, True, capital)
        return out

    def serie_a(fin):
        return {(pid, tk): correr(tk, ha[tk], compras[pid], fin, True, capital)
                for pid, _ in periodos for tk in fondos_a}

    B, B1, A, A1 = serie_b(T), serie_b(T1), serie_a(T), serie_a(T1)
    m = lambda res, t: con_base(metricas(res, capital), t)  # noqa: E731
    mapa_b = {"inicio": str(inicio.date()), "parejas": [], "referencias": {}}
    for accion, fondo in parejas:
        ks = (accion, f"{fondo}_reinvirtiendo", f"{fondo}_cobrando")
        mapa_b["parejas"].append({"accion": accion, "fondo": fondo,
                                  "series": {k: m(B[k], T) for k in ks},
                                  "en_cierre_anterior": {k: m(B1[k], T1) for k in ks}})
    for tk in referencias:
        mapa_b["referencias"][tk] = m(B[tk], T)
        mapa_b["referencias"][tk + "_en_cierre_anterior"] = m(B1[tk], T1)
    mapa_b["linea_mercado"] = linea_mercado(mapa_b["referencias"][mercado], mercado)
    mapa_b["semanas"] = semanas(B, parejas, inicio, T)
    mapa_b["paradas"] = paradas_b(crudas_b, hb, parejas, referencias, T, inicio, inicio_b, mercado, capital)
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
            "mapa_b": "precios y pagos de --historia-b; sin ella, el caché de precios de la app",
            "mapa_a": "historia que pasa quien llama en --historia-a, cortada en T",
        },
        "supuestos": SUPUESTOS,
        "filas_malas": malas,
        "mapa_a": mapa_a, "mapa_b": mapa_b,
    }


def _lista(s):
    return [x.strip().upper() for x in s.split(",") if x.strip()]


def _enteros(s):
    try:
        return [int(x) for x in _lista(s)]
    except ValueError:
        raise DatosMalos(f"--anios-a lleva enteros separados por comas: {s}") from None


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
                     anios_a=_enteros(a.anios_a), mercado=a.mercado.strip().upper())
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
