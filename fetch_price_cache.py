#!/usr/bin/env python3
"""Refresca el cache de historia de precio/dividendo/split (`knowledge/price_cache/`) que usa
`price_cache.py` para alimentar `backtest.run_backtest(..., history=...)` sin llamar a
yfinance en cada carga.

Fase 3.2 del plan de remediacion (`vivid-popping-clover.md`). Reusa `backtest.fetch_history`/
`backtest.fetch_splits` (ya auditados en la Fase 3.1 — gate de reconciliacion MSTY vs extracto
real de IB, 0.013% de diferencia) en vez de reimplementar el fetch: asi el cache queda
garantizado con la MISMA convencion de split-adjustment que el motor ya prueba, no una segunda
version que pueda divergir en silencio.

Que escribe, por ticker:
  - `knowledge/price_cache/{TICKER}.parquet` — columnas ['Close', 'Dividends'], index=fecha
    (precio crudo sin ajustar por dividendo + dividendo/accion, ambos ya split-adjusted por
    yfinance — ver docstring de backtest.py).
  - `knowledge/price_cache/_splits.yaml` — un entry por ticker con [{date, ratio}, ...]
    (ratio < 1.0 = split inverso). Vive en un yaml (chico, legible) separado del parquet
    (grande, filas diarias) a proposito — ver nota de tamano del plan.
  - `knowledge/price_cache/_meta.yaml` — {generated_at, start, end, rows} por ticker: la
    fecha de generacion y el rango cubierto, para que `price_cache.py` decida frescura y para
    que la UI de la Fase 3.3 pueda mostrar "datos al DD/MM".

Rango: arranca en CACHE_START (2022-11-23, incepcion de TSLY — el fondo YieldMax mas antiguo
de la lista) para TODOS los tickers, incluidos los ETF de crecimiento (SCHB/XLK/SMH) que
tienen historia real desde 1998-2009: la comparacion nunca necesita mas atras que el fondo
base mas viejo, y commitear 25 anios de precios que nadie usa es peso muerto en el repo.

Resiliencia (mismo patron que fetch_roc_19a.py): si un ticker falla al bajar, se CONSERVA su
entrada de cache previa (parquet + meta + splits) tal cual — nunca se borra ni se pisa con
datos parciales. Exit code 1 solo si un ticker que YA tenia cache ahora falla (regresion real,
dispara el aviso de Telegram del workflow); un ticker nuevo que aun no tiene cache y falla al
bajar por primera vez es un warning, no un error de CI.

Dividendos de YieldMax: yfinance se equivoca y el cache lo arrastraba. El 1-oct-2026 copió la
distribución del 8-oct sobre la del 1-oct en todos los fondos con ex-date en jueves (MSTY
0.245 contra 0.3111 oficial). Para los fondos de `DISTRIBUCIONES_OFICIALES` los dividendos se
contrastan con la tabla oficial de la página de cada fondo y, donde difieren más que el
redondeo de yfinance, manda la oficial (`reconciliar_dividendos`). Si la tabla oficial no carga,
o el contraste pide cambiar demasiadas filas, el fondo conserva su cache previo: escribir lo de
yfinance sin contrastar devolvería al cache los errores ya corregidos.

Uso local:  ./.venv/bin/python fetch_price_cache.py [TICKER ...]
"""
import datetime as dt
import os
import re
import sys
import time

import pandas as pd
import yaml
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt   # noqa: E402
import fetch_roc_19a as roc   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "knowledge", "price_cache")
META_PATH = os.path.join(CACHE_DIR, "_meta.yaml")
SPLITS_PATH = os.path.join(CACHE_DIR, "_splits.yaml")

# Incepcion de TSLY (2022-11-23) — el fondo YieldMax base mas antiguo de la lista. Ver nota de
# tamano del plan: recortar aqui evita commitear decadas de historia de SCHB/XLK/SMH que la
# comparacion nunca usa.
CACHE_START = "2022-11-23"

# YMAX entra por la vista «Estrategias» (`ui/heredadas._ESTR_ETF_MAP`), que compara el
# portafolio real contra poner todo en un solo ETF. Sin el en el cache esa vista seguia
# bajando de yfinance en cada render.
# PLTY, QYLD y SVOL entran porque eran los unicos tickers del portafolio que `price_cache`
# resolvia por `source="live"` (medido 2026-09-01: MSTY daba "cache", estos tres "live"), asi
# que las vistas que SI leen el cache —backtest / Total Return Graph / Estrategias— bajaban su
# historia de yfinance en cada render. Con el parquet dan "cache" como los demas.
#
# OJO CON EL ALCANCE, medido y NO supuesto: esto NO estabiliza el ROC del peldano 2. `logic.py`
# no importa `price_cache` en absoluto (lo dice el docstring del propio modulo: «ui/ NO importa
# este modulo todavia, eso es la Fase 3.3») — llama `yf.download`/`yf.Ticker` directo. Un solo
# `analyze_portfolio` del caso IB real dispara 63 llamadas a yfinance, incluidas las de tickers
# que YA tienen parquet. Verificado A/B: el `roc_percent` de PLTY sale 66.48 identico con
# parquet, sin parquet y con la red caida. El no-determinismo de la cobertura del peldano 2 se
# cierra en la Fase 3.3, no aqui.
TICKERS = ["NVDY", "TSLY", "CONY", "MSTY", "CHPY", "SCHB", "XLK", "SMH", "NFLY", "YMAX",
           "NVDA", "TSLA", "COIN", "MSTR", "PLTY", "QYLD", "SVOL"]

# Fondos de TICKERS cuyas distribuciones publica YieldMax en la página del fondo. CHPY va
# aunque no tenga ficha en instruments.yaml: es YieldMax y su página existe.
DISTRIBUCIONES_OFICIALES = ["NVDY", "TSLY", "CONY", "MSTY", "CHPY", "NFLY", "YMAX", "PLTY"]

# yfinance publica cada distribución redondeada a 3 decimales: hasta media milésima de
# diferencia es redondeo, no error (medido 2026-10-30: NFLY 0.050 contra 0.0495 oficial, YMAX
# 0.034 contra 0.0336). Sin tocar el redondeo, el gate MSTY contra el extracto de IB no se mueve.
TOL_REDONDEO = 0.0005 + 1e-9

# Un fallo de yfinance toca una o dos filas (el del 1-oct-2026, una por fondo). Si el
# contraste quiere cambiar más, lo sospechoso es el parser o la página: no se aplica nada.
MAX_CORRECCIONES = 3


def _parquet_path(ticker: str) -> str:
    return os.path.join(CACHE_DIR, f"{ticker.upper()}.parquet")


def _load_yaml(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def fetch_one(ticker: str):
    """(hist, splits) reales para `ticker` desde CACHE_START, via backtest.py. Deja que
    cualquier error de red/yfinance suba tal cual — el caller decide (mismo contrato que
    `backtest.fetch_history`: no hay fallback silencioso a datos falsos)."""
    hist = bt.fetch_history(ticker, start=CACHE_START)
    splits = bt.fetch_splits(ticker)
    return hist, splits


class ContrasteSospechoso(Exception):
    """El contraste con la tabla oficial pide cambiar más filas de las que rompe yfinance."""


def parse_distribuciones_oficiales(html) -> pd.Series:
    """Serie ex-date -> distribución por acción desde la tabla oficial de YieldMax
    («DISTRIBUTION PER SHARE | DECLARED DATE | EX DATE | RECORD DATE | PAYABLE DATE | ROC»).

    La columna de fecha se busca por nombre: `fetch_roc_19a.parse_distributions_from_html` toma
    la primera que contiene «date», que en esta tabla es la de declaración, un día antes del
    ex-date. La tabla repite filas (medido 2026-10-30: TSLY, CONY y MSTY listan dos veces sus
    pagos anteriores a dic-2025, con el mismo importe); si una fecha trajera dos importes
    distintos la fuente sería ambigua y se lanza `ValueError`."""
    soup = BeautifulSoup(html or "", "html.parser")
    for table in soup.find_all("table"):
        filas = table.find_all("tr")
        if not filas:
            continue
        cab = [c.get_text(" ", strip=True).lower() for c in filas[0].find_all(["th", "td"])]
        i_ex = next((i for i, h in enumerate(cab) if re.search(r"\bex\b[\s-]*date", h)), None)
        i_monto = next((i for i, h in enumerate(cab) if "per share" in h), None)
        if i_ex is None or i_monto is None:
            continue
        out = {}
        for tr in filas[1:]:
            celdas = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
            if len(celdas) <= max(i_ex, i_monto):
                continue
            fecha = roc._parse_date(celdas[i_ex])
            monto = roc._parse_money(celdas[i_monto])
            if fecha is None or monto is None:
                continue
            fecha = pd.Timestamp(fecha)
            if fecha in out and abs(out[fecha] - monto) > 1e-9:
                raise ValueError(f"la tabla oficial trae dos importes para el ex-date "
                                 f"{fecha.date()}: {out[fecha]} y {monto}")
            out.setdefault(fecha, monto)
        if out:
            return pd.Series(out, dtype=float).sort_index()
    return pd.Series(dtype=float)


def fetch_oficial(ticker: str) -> pd.Series:
    """Distribuciones oficiales de `ticker` desde su página de YieldMax, con el fetch HTTP
    plano de `fetch_roc_19a` (la tabla viene en el HTML; el chromium headless lo bloquean en
    los runners). Lanza si tras los reintentos la página no trae la tabla."""
    url = roc.FUND_URL.format(tk=ticker.lower())
    motivo = None
    for intento in range(1, roc.RETRIES + 1):
        time.sleep(roc.FUND_DELAY)
        try:
            serie = parse_distribuciones_oficiales(roc.fetch_plain_html(url))
            if not serie.empty:
                return serie
            motivo = "la página no trae la tabla de distribuciones"
        except Exception as e:
            motivo = e
        if intento < roc.RETRIES:
            time.sleep(roc.RETRY_WAIT)
    raise RuntimeError(f"sin tabla oficial de distribuciones en {url} ({motivo})")


def reconciliar_dividendos(dividendos: pd.Series, oficial: pd.Series, splits=None):
    """Contrasta los dividendos de yfinance con la tabla oficial; donde difieren más que el
    redondeo (`TOL_REDONDEO`), manda la oficial: corrige el importe, añade el que falta y quita
    el que la tabla no tiene.

    Solo se contrasta desde el día siguiente al último split. Antes de un split la tabla oficial
    no siempre está en la base de acciones de yfinance: medido 2026-10-30, en las 14
    distribuciones de TSLY anteriores a su split de feb-2024 la oficial da justo el doble, y la
    caída del precio en cada ex-date es 0.9 veces el valor de yfinance y 0.45 veces el oficial.
    Ahí yfinance es coherente con su propia serie de precios y no se toca. Tampoco se juzga lo
    posterior a la última fila oficial: la página puede ir un día por detrás de yfinance.

    Devuelve `(serie, correcciones, sin_fila)`: `correcciones` es la lista de cambios aplicados
    y `sin_fila` las ex-dates oficiales sin fila de precio en yfinance, que no se pueden
    colocar. Lanza `ContrasteSospechoso` sin aplicar nada si hay más de `MAX_CORRECCIONES`."""
    divs = dividendos.astype(float).copy()
    if oficial is None or oficial.empty or divs.empty:
        return divs, [], []
    inicio = max(oficial.index.min(), divs.index.min())
    if splits is not None and len(splits):
        inicio = max(inicio, splits.index.max() + pd.Timedelta(days=1))
    fin = min(oficial.index.max(), divs.index.max())
    of = oficial[(oficial.index >= inicio) & (oficial.index <= fin)]

    correcciones, sin_fila = [], []
    for fecha, monto in of.items():
        if fecha not in divs.index:
            sin_fila.append(fecha)
            continue
        actual = float(divs.loc[fecha])
        if abs(actual - monto) > TOL_REDONDEO:
            correcciones.append({"fecha": fecha.date().isoformat(),
                                 "tipo": "importe" if actual > 0 else "faltaba",
                                 "yfinance": actual, "oficial": float(monto)})
            divs.loc[fecha] = float(monto)
    ventana = dividendos[(dividendos.index >= inicio) & (dividendos.index <= fin)]
    for fecha, valor in ventana[ventana > 0].items():
        if fecha not in of.index:
            correcciones.append({"fecha": fecha.date().isoformat(), "tipo": "sobraba",
                                 "yfinance": float(valor), "oficial": 0.0})
            divs.loc[fecha] = 0.0

    if len(correcciones) > MAX_CORRECCIONES:
        raise ContrasteSospechoso(
            f"el contraste pide {len(correcciones)} cambios (máximo {MAX_CORRECCIONES}): "
            f"{correcciones}")
    correcciones.sort(key=lambda c: c["fecha"])
    return divs, correcciones, sin_fila


def main(argv):
    tickers = [t.upper() for t in argv[1:]] or TICKERS
    os.makedirs(CACHE_DIR, exist_ok=True)

    meta = _load_yaml(META_PATH)
    splits_out = _load_yaml(SPLITS_PATH)
    today = dt.date.today().isoformat()

    regressions, failures = [], []
    for tk in tickers:
        had_prior = tk in meta
        try:
            hist, splits = fetch_one(tk)
        except Exception as e:
            print(f"::warning::{tk}: fallo la descarga ({e}). Conservo el cache previo.",
                  file=sys.stderr)
            failures.append(tk)
            if had_prior:
                regressions.append(tk)
            continue

        if hist is None or hist.empty:
            print(f"::warning::{tk}: yfinance devolvio historia vacia. Conservo el cache "
                  f"previo.", file=sys.stderr)
            failures.append(tk)
            if had_prior:
                regressions.append(tk)
            continue

        cols = hist[["Close", "Dividends"]].copy()

        # Barra pendiente de yfinance: la sesión del día en curso puede venir como fila con
        # `Close` NULO. No es "un día sin datos" — yfinance NO emite fila para festivos ni
        # días sin sesión, así que una fila que EXISTE con Close nulo es una barra que aún no
        # se publicó. Si se guarda, el NaN se propaga por el motor de backtest y las series
        # salen TODAS en cero (incidente 2026-08-29: `127e2f6` metió una fila 2026-08-28 con
        # Close NaN en los 14 parquets; 12 tests en rojo y producción mostrando
        # «VALOR MER. $0.00» en todos los fondos).
        #
        # Se recortan solo las nulas del FINAL. Un nulo a media serie no se descarta en
        # silencio: eso cambiaría la serie sin dejar rastro, así que se trata como fallo y el
        # ticker conserva su cache previo (el workflow sale en rojo por `regressions`).
        n_antes = len(cols)
        while len(cols) and pd.isna(cols["Close"].iloc[-1]):
            cols = cols.iloc[:-1]
        if len(cols) < n_antes:
            print(f"::warning::{tk}: descartadas {n_antes - len(cols)} fila(s) final(es) con "
                  f"Close nulo (barra pendiente de yfinance).", file=sys.stderr)

        if cols["Close"].isna().any():
            n_huecos = int(cols["Close"].isna().sum())
            print(f"::warning::{tk}: {n_huecos} fila(s) con Close nulo a MEDIA serie — no se "
                  f"descartan en silencio. Conservo el cache previo.", file=sys.stderr)
            failures.append(tk)
            if had_prior:
                regressions.append(tk)
            continue

        if cols.empty:
            print(f"::warning::{tk}: no queda ninguna fila con Close tras recortar las "
                  f"pendientes. Conservo el cache previo.", file=sys.stderr)
            failures.append(tk)
            if had_prior:
                regressions.append(tk)
            continue

        correcciones = None
        if tk in DISTRIBUCIONES_OFICIALES:
            try:
                cols["Dividends"], correcciones, sin_fila = reconciliar_dividendos(
                    cols["Dividends"], fetch_oficial(tk), splits)
            except Exception as e:
                print(f"::warning::{tk}: no se pudo contrastar con la tabla oficial de YieldMax "
                      f"({e}). Conservo el cache previo.", file=sys.stderr)
                failures.append(tk)
                if had_prior:
                    regressions.append(tk)
                continue
            for c in correcciones:
                print(f"{tk}: dividendo {c['fecha']} ({c['tipo']}): yfinance {c['yfinance']} "
                      f"-> oficial {c['oficial']}")
            for fecha in sin_fila:
                print(f"::warning::{tk}: la tabla oficial trae ex-date {fecha.date()} y yfinance "
                      f"no tiene fila de precio ese día; no se aplica.", file=sys.stderr)

        cols.to_parquet(_parquet_path(tk))

        meta[tk] = {
            "generated_at": today,
            "start": cols.index.min().date().isoformat(),
            "end": cols.index.max().date().isoformat(),
            "rows": int(len(cols)),
            "dividends_source": "yfinance" if correcciones is None else "yieldmax_oficial",
        }
        if correcciones is not None:
            meta[tk]["dividend_corrections"] = [
                f"{c['fecha']}: {c['yfinance']} -> {c['oficial']}" for c in correcciones]
        splits_out[tk] = [
            {"date": ts.date().isoformat(), "ratio": float(ratio)}
            for ts, ratio in splits.items()
        ] if splits is not None else []

        print(f"{tk}: {len(cols)} filas [{meta[tk]['start']} .. {meta[tk]['end']}], "
              f"{len(splits_out[tk])} split(s)")

    with open(META_PATH, "w", encoding="utf-8") as fh:
        fh.write("# Generado por fetch_price_cache.py. Fecha de generacion y rango cubierto "
                  "por ticker del cache en knowledge/price_cache/*.parquet.\n"
                  "# Refresco semanal via .github/workflows/refresh-price-cache.yml. "
                  "No editar a mano.\n")
        yaml.safe_dump(meta, fh, sort_keys=False, allow_unicode=True)
    with open(SPLITS_PATH, "w", encoding="utf-8") as fh:
        fh.write("# Generado por fetch_price_cache.py (fuente: yfinance, Ticker.splits).\n"
                  "# Splits reales por ticker (ratio < 1.0 = split inverso). Refresco semanal "
                  "via .github/workflows/refresh-price-cache.yml. No editar a mano.\n")
        yaml.safe_dump(splits_out, fh, sort_keys=False, allow_unicode=True)

    print(f"Escrito {META_PATH} y {SPLITS_PATH} ({len(meta)} tickers en cache). "
          f"Fallos: {failures or '—'}. Regresiones: {regressions or '—'}.")

    if regressions:
        print(f"::error::Regresion en: {', '.join(regressions)} (tenian cache y ahora "
              f"fallaron). Los demas tickers se actualizaron igual.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
