#!/usr/bin/env python3
"""Congela la historia de 2022 que usa la prueba de estrés de «Riesgo» (`estres_2022.py`).

Se corre UNA vez y se commitea: la historia de 2022 no cambia, así que NO entra al workflow de
refresco (`refresh-price-cache.yml`). El caché de precios (`fetch_price_cache.CACHE_START`)
empieza el 2022-11-23 y no trae 2022, por eso esto va aparte.

Escribe, por ticker:
  - `knowledge/estres_2022/{TICKER}.parquet` — columnas ['Close', 'Dividends'] (precio sin
    ajustar por dividendo + dividendo por acción, ambos split-adjusted), mismo formato que el
    caché de precios, vía `backtest.fetch_history`.
  - `knowledge/estres_2022/_meta.yaml` — {generated_at, start, end, rows} por ticker.

Uso local:  ./.venv/bin/python fetch_estres_2022.py [TICKER ...]
"""
import datetime as dt
import os
import sys

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "knowledge", "estres_2022")
META_PATH = os.path.join(DIR, "_meta.yaml")

# Un mes antes del inicio de la ventana (14-abr-2021): la volatilidad usa 21 sesiones previas.
START = "2021-03-01"
END = "2024-01-01"            # exclusivo en yfinance: la última sesión es el 29-dic-2023

TICKERS = ["TSLA", "NVDA", "COIN", "NFLX", "MSTR", "XLK", "SMH", "SCHB"]


def main(argv):
    tickers = [t.upper() for t in argv[1:]] or TICKERS
    os.makedirs(DIR, exist_ok=True)
    meta = {}
    if os.path.exists(META_PATH):
        with open(META_PATH, "r", encoding="utf-8") as fh:
            meta = yaml.safe_load(fh) or {}
    hoy = dt.date.today().isoformat()
    fallos = []
    for tk in tickers:
        try:
            hist = bt.fetch_history(tk, start=START, end=END)
        except Exception as e:                                     # noqa: BLE001
            print(f"{tk}: falló la descarga ({e}). No se escribe nada.", file=sys.stderr)
            fallos.append(tk)
            continue
        if hist is None or hist.empty:
            print(f"{tk}: yfinance devolvió historia vacía.", file=sys.stderr)
            fallos.append(tk)
            continue
        cols = hist[["Close", "Dividends"]].copy()
        if cols["Close"].isna().any():
            print(f"{tk}: hay Close nulo; no se escribe.", file=sys.stderr)
            fallos.append(tk)
            continue
        cols.to_parquet(os.path.join(DIR, f"{tk}.parquet"))
        meta[tk] = {"generated_at": hoy,
                    "start": cols.index.min().date().isoformat(),
                    "end": cols.index.max().date().isoformat(),
                    "rows": int(len(cols))}
        print(f"{tk}: {len(cols)} filas [{meta[tk]['start']} .. {meta[tk]['end']}]")
    with open(META_PATH, "w", encoding="utf-8") as fh:
        fh.write("# Generado por fetch_estres_2022.py (una sola vez; la historia de 2022 no cambia).\n"
                 "# No entra al workflow de refresco. No editar a mano.\n")
        yaml.safe_dump(meta, fh, sort_keys=True, allow_unicode=True)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
