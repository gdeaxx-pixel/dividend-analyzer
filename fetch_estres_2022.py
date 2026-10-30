#!/usr/bin/env python3
"""Congela la historia de 2022 que usa la prueba de estrés de «Riesgo» (`estres_2022.py`).

Se corre a mano y se commitea: la historia de 2022 no cambia, así que NO entra al workflow de
refresco (`refresh-price-cache.yml`). El caché de precios (`fetch_price_cache.CACHE_START`)
empieza el 2022-11-23 y no trae 2022, por eso esto va aparte. La app no baja 2022 en vivo
(CLAUDE.md: no llamar a yfinance desde la UI): un ticker que no esté aquí queda fuera de la
simulación.

Universo: lo que `ui/riesgo.py:_estres_para` puede pedir para un fondo que la app reconoce
(`logic.YIELDMAX_WHITELIST` y `logic.ETF_WHITELIST`): la acción que sigue un YieldMax con
subyacente en `knowledge/instruments.yaml`, y el propio ticker para el resto. Si una de esas
listas o el yaml suman un ticker, `test_estres_2022.py` falla hasta correr esto.

Escribe, por ticker:
  - `knowledge/estres_2022/{TICKER}.parquet` — columnas ['Close', 'Dividends'] (precio sin
    ajustar por dividendo + dividendo por acción, ambos split-adjusted), mismo formato que el
    caché de precios, vía `backtest.fetch_history`.
  - `knowledge/estres_2022/_meta.yaml` — {generated_at, start, end, rows} por ticker. Uno sin
    ninguna sesión en el rango queda con `rows: 0` y su `primera_sesion`, medida con toda su
    historia: nació después de la ventana y no hay nada que congelar. `primera_sesion: null`
    es que Yahoo no tiene ninguna (ticker que no conoce), con `CONTROL` respondiendo a la vez:
    eso no es un fondo sin 2022 sino un ticker que no existe, y `test_estres_2022.py` falla
    hasta corregir la lista blanca o la ficha.

Uso local:  ./.venv/bin/python fetch_estres_2022.py [TICKER ...]
Sin argumentos baja solo lo que falta del universo; con tickers, esos (y los reescribe).
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
CONTROL = "SPY"


def _yahoo_responde() -> bool:
    """yfinance devuelve vacío tanto si Yahoo no conoce el ticker como si se cayó la red; solo
    se distinguen pidiendo en el mismo momento uno que seguro existe."""
    try:
        h = bt.fetch_history(CONTROL, start=START, end=END)
    except Exception:                                              # noqa: BLE001
        return False
    return h is not None and not h.empty


def universo() -> list[str]:
    import estres_2022
    import logic

    sub = estres_2022.subyacentes_yieldmax(logic.load_instruments())
    return sorted({sub.get(t, t) for t in logic.YIELDMAX_WHITELIST | logic.ETF_WHITELIST})


def main(argv):
    os.makedirs(DIR, exist_ok=True)
    meta = {}
    if os.path.exists(META_PATH):
        with open(META_PATH, "r", encoding="utf-8") as fh:
            meta = yaml.safe_load(fh) or {}
    tickers = [t.upper() for t in argv[1:]] or [t for t in universo() if t not in meta]
    hoy = dt.date.today().isoformat()
    fallos = []
    for tk in tickers:
        try:
            hist = bt.fetch_history(tk, start=START, end=END)
            toda = bt.fetch_history(tk) if hist is None or hist.empty else None
        except Exception as e:                                     # noqa: BLE001
            print(f"{tk}: falló la descarga ({e}). No se escribe nada.", file=sys.stderr)
            fallos.append(tk)
            continue
        if toda is not None:
            primera = None if toda.empty else toda.index.min()
            if primera is None and not _yahoo_responde():
                print(f"{tk}: historia vacía y {CONTROL} tampoco responde; no se escribe.", file=sys.stderr)
                fallos.append(tk)
                continue
            if primera is not None and primera < pd.Timestamp(END):
                print(f"{tk}: yfinance devolvió historia vacía.", file=sys.stderr)
                fallos.append(tk)
                continue
            meta[tk] = {"generated_at": hoy, "rows": 0,
                        "primera_sesion": None if primera is None else primera.date().isoformat()}
            print(f"{tk}: sin sesiones en la ventana (primera sesión: "
                  f"{meta[tk]['primera_sesion'] or 'ninguna: Yahoo no conoce el ticker, revisar la lista blanca'})")
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
        fh.write("# Generado por fetch_estres_2022.py: la historia de 2022 no cambia, solo se suma lo que falta.\n"
                 "# No entra al workflow de refresco. No editar a mano.\n"
                 "# rows: 0 = ninguna sesión en la ventana; primera_sesion es la primera que tiene\n"
                 "# Yahoo (null: ninguna).\n")
        yaml.safe_dump(meta, fh, sort_keys=True, allow_unicode=True)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
