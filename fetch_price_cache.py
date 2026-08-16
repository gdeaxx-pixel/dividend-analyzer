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

Uso local:  ./.venv/bin/python fetch_price_cache.py [TICKER ...]
"""
import datetime as dt
import os
import sys

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "knowledge", "price_cache")
META_PATH = os.path.join(CACHE_DIR, "_meta.yaml")
SPLITS_PATH = os.path.join(CACHE_DIR, "_splits.yaml")

# Incepcion de TSLY (2022-11-23) — el fondo YieldMax base mas antiguo de la lista. Ver nota de
# tamano del plan: recortar aqui evita commitear decadas de historia de SCHB/XLK/SMH que la
# comparacion nunca usa.
CACHE_START = "2022-11-23"

TICKERS = ["NVDY", "TSLY", "CONY", "MSTY", "CHPY", "SCHB", "XLK", "SMH", "NFLY"]


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
        cols.to_parquet(_parquet_path(tk))

        meta[tk] = {
            "generated_at": today,
            "start": cols.index.min().date().isoformat(),
            "end": cols.index.max().date().isoformat(),
            "rows": int(len(cols)),
        }
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
