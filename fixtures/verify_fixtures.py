#!/usr/bin/env python3
"""Verifica que los fixtures sintéticos coinciden con lo que produce `logic.py`.

Corre sin red: solo ejercita detección de bróker, parseo, normalización, clasificación
de tickers y la agregación de vista previa del Bloque 1. No llama a `analyze_portfolio`
(que necesita yfinance), así que sirve como chequeo rápido y determinista.

    python3 fixtures/verify_fixtures.py

Código de salida: 0 si todo coincide; 1 si algún valor difiere.
"""
import io
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(BASE)
sys.path.insert(0, REPO)

import logic  # noqa: E402

TOL = 0.01


class FakeFile:
    """Replica el objeto de Streamlit que esperan los parsers de logic.py."""

    def __init__(self, content: bytes, name: str):
        self._buf = io.BytesIO(content)
        self.name = name

    def read(self):
        return self._buf.read()

    def seek(self, n):
        self._buf.seek(n)


def csv_preview_aggregate(clean):
    """Réplica exacta de la agregación de `app.py:1400-1412` (`_csv_ticker_data`).

    Filtra por `Action.contains('buy')`: no suma reinversiones ni resta ventas.
    Es la vista previa del Bloque 1, NO la posición real.
    """
    out = {}
    for ticker, group in clean.groupby('Ticker'):
        buys = group[group['Action'].str.lower().str.contains('buy', na=False)]
        out[ticker] = {
            'shares': float(buys['Quantity'].sum()) if not buys.empty else 0.0,
            'invested': abs(float(buys['Amount'].sum())) if not buys.empty else 0.0,
        }
    return out


def check(label, expected, got, failures):
    ok = abs(expected - got) < TOL
    mark = "ok  " if ok else "FALLA"
    print(f"  [{mark}] {label:34s} esperado {expected:>10.4f}   código {got:>10.4f}")
    if not ok:
        failures.append(label)


def main():
    failures = []

    for case in ("schwab_synth_1", "ib_synth_1"):
        case_dir = os.path.join(BASE, case)
        with open(os.path.join(case_dir, "expected.json"), encoding="utf-8") as f:
            exp = json.load(f)

        csv_path = os.path.join(BASE, exp["csv_glob"])
        with open(csv_path, "rb") as f:
            raw = f.read()

        print(f"\n=== {case} ===")

        df, broker = logic.load_and_detect_csv(FakeFile(raw, os.path.basename(csv_path)))
        if broker == exp["broker"]:
            print(f"  [ok  ] broker detectado                 {broker}")
        else:
            print(f"  [FALLA] broker detectado: {broker!r}, esperado {exp['broker']!r}")
            failures.append(f"{case}: broker")

        clean = logic.normalize_csv(df)
        missing = [c for c in ("Date", "Ticker", "Amount") if c not in clean.columns]
        if missing:
            print(f"  [FALLA] faltan columnas requeridas: {missing}")
            failures.append(f"{case}: columnas")
            continue
        print(f"  [ok  ] columnas requeridas presentes    {len(clean)} filas")

        tickers = sorted(t for t in clean["Ticker"].dropna().unique() if t and t != 'nan')
        modes = logic.classify_tickers(tickers)
        for ticker in exp["tickers"]:
            mode = modes.get(ticker)
            if mode in ("mode_a", "mode_b"):
                print(f"  [ok  ] {ticker} clasificado              {mode}")
            else:
                print(f"  [FALLA] {ticker} clasificado {mode!r}, esperaba mode_a/mode_b")
                failures.append(f"{case}: {ticker} modo")
        for ticker, reason in exp.get("excluded_tickers", {}).items():
            mode = modes.get(ticker)
            if mode == "mode_skip":
                print(f"  [ok  ] {ticker} excluido                 {reason}")
            else:
                print(f"  [FALLA] {ticker} deberia ser mode_skip, es {mode!r}")
                failures.append(f"{case}: {ticker} deberia excluirse")

        preview = csv_preview_aggregate(clean)
        pexp = exp["csv_preview_expected"]
        for ticker, shares in pexp["shares"].items():
            check(f"{ticker} vista previa acciones", shares,
                  preview.get(ticker, {}).get("shares", 0.0), failures)
        for ticker, invested in pexp["invested"].items():
            check(f"{ticker} vista previa invertido", invested,
                  preview.get(ticker, {}).get("invested", 0.0), failures)

    print()
    if failures:
        print(f"FALLA — {len(failures)} discrepancias:")
        for f in failures:
            print(f"  · {f}")
        return 1
    print("OK — los fixtures coinciden con logic.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
