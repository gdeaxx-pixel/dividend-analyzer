#!/usr/bin/env python3
"""Registra el veredicto de salud del NAV (ROC destructivo vs contable) por fondo, a NIVEL
FONDO (independiente de cualquier portafolio), para poder graficar su evolución mes a mes.

Para cada YieldMax: toma el % de ROC ponderado del knowledge/roc_19a.yaml + el CAGR de
precio reciente (12m) bajado por yfinance, y aplica logic.classify_roc_health. Hace append
idempotente por fecha en knowledge/roc_health_history.yaml:
    {TICKER: [{date, verdict, roc_pct, price_cagr}]}

Lo corre el mismo GitHub Action que fetch_roc_19a.py, justo después. Determinista, sin LLM.

Uso local:  python snapshot_roc_health.py [TICKER ...]
"""
import os
import sys
import datetime

import yaml

import logic
from fetch_roc_19a import yieldmax_tickers

HERE = os.path.dirname(os.path.abspath(__file__))
ROC_PATH = os.path.join(HERE, "knowledge", "roc_19a.yaml")
HIST_PATH = os.path.join(HERE, "knowledge", "roc_health_history.yaml")
ALERTS_PATH = os.path.join(HERE, "roc_health_alerts.txt")  # lo lee el paso de Telegram del Action
LOOKBACK_DAYS = 420   # ~14 meses: cubre la ventana de 12m del CAGR reciente con margen


def _load_yaml(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def _price_cagr_recent(ticker):
    """CAGR de precio de los últimos 12m (= erosión/apreciación observada del NAV). None si falla."""
    start = (datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()
    df, err = logic.fetch_market_data(ticker, start)
    if df is None or getattr(df, "empty", True) or "Close" not in df.columns:
        return None, None
    cagr = logic._annualized_cagr(df["Close"], days=365)
    cc = df["Close"].dropna()
    days = int((cc.index[-1] - cc.index[0]).days) if len(cc) >= 2 else None
    return cagr, days


def snapshot(tickers):
    roc19a = _load_yaml(ROC_PATH)
    hist = _load_yaml(HIST_PATH)
    today = datetime.date.today().isoformat()
    alerts = []   # cambios de veredicto relevantes -> aviso por Telegram

    for tk in tickers:
        entry = roc19a.get(tk) or {}
        roc_pct = entry.get("weighted_pct")
        asof = entry.get("asof")
        asof_days = None
        if asof:
            try:
                asof_days = (datetime.date.today() - datetime.date.fromisoformat(asof)).days
            except Exception:
                asof_days = None

        price_cagr, hist_days = _price_cagr_recent(tk)
        verdict = logic.classify_roc_health(
            roc_pct=roc_pct,
            price_cagr=price_cagr,
            total_return_pct=None,        # a nivel fondo no hay portafolio
            history_days=hist_days,
            roc_asof_days=asof_days)

        row = {
            "date": today,
            "verdict": verdict["verdict"],
            "roc_pct": round(float(roc_pct), 1) if roc_pct is not None else None,
            "price_cagr": round(float(price_cagr), 1) if price_cagr is not None else None,
        }
        series = [r for r in (hist.get(tk) or []) if r.get("date") != today]  # idempotente por fecha
        prev_verdict = series[-1]["verdict"] if series else None
        series.append(row)
        hist[tk] = sorted(series, key=lambda r: r.get("date") or "")
        print(f"{tk}: {verdict['verdict']} (ROC {row['roc_pct']}%, NAV {row['price_cagr']}%/año)")

        # Aviso cuando el veredicto CAMBIA hacia/desde destructivo (lo importante de seguir).
        new_v = verdict["verdict"]
        if prev_verdict and prev_verdict != new_v and "destructive" in (prev_verdict, new_v):
            if new_v == "destructive":
                alerts.append(f"🔴 {tk} pasó a ROC DESTRUCTIVO "
                              f"(antes {prev_verdict}): NAV {row['price_cagr']}%/año, ROC {row['roc_pct']}%.")
            else:
                alerts.append(f"🟢 {tk} salió de ROC destructivo → {new_v} "
                              f"(NAV {row['price_cagr']}%/año, ROC {row['roc_pct']}%).")

    os.makedirs(os.path.dirname(HIST_PATH), exist_ok=True)
    with open(HIST_PATH, "w", encoding="utf-8") as fh:
        fh.write("# Generado por snapshot_roc_health.py. Histórico del veredicto de salud del NAV\n"
                 "# por fondo (ROC destructivo vs contable). No editar a mano.\n")
        yaml.safe_dump(hist, fh, sort_keys=True, allow_unicode=True)
    print(f"Escrito {HIST_PATH} ({len(hist)} fondos).")

    # Deja los avisos en disco para que el paso de Telegram del Action los envíe (si los hay).
    if alerts:
        with open(ALERTS_PATH, "w", encoding="utf-8") as fh:
            fh.write("\n".join(alerts))
        print(f"{len(alerts)} cambio(s) de veredicto -> {ALERTS_PATH}")
    elif os.path.exists(ALERTS_PATH):
        os.remove(ALERTS_PATH)
    return 0


def main(argv):
    tickers = [t.upper() for t in argv[1:]] or yieldmax_tickers()
    if not tickers:
        print("No hay tickers yieldmax que snapshotear.", file=sys.stderr)
        return 0
    return snapshot(tickers)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
