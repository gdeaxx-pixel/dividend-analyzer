#!/usr/bin/env python3
"""
market_context.py
Snapshot bimensual de ETFs clave — genera nota Markdown en Obsidian.
Corre el 1 y el 15 de cada mes via cron.
"""

import yfinance as yf
from datetime import date, datetime
import os
import sys

VAULT    = "/Users/danielzambrano/Desktop/Habilidades de agentes/Obsidian"
OUT_PATH = f"{VAULT}/APPs/Dividend-Analyzer/contexto-mercado.md"

GROUPS = {
    "Benchmarks": ["SPY", "QQQ", "VOO", "DIA", "IWM"],
    "Sectores":   ["XLK", "SMH", "XLF", "XLE", "XLV", "XLY"],
    "YieldMax / Income ETFs": ["TSLY", "NVDY", "MSTY", "CONY", "YMAX", "YMAG", "ULTY"],
    "Renta Fija / Commodities": ["TLT", "GLD", "BTC-USD"],
}


def fetch(symbol: str) -> dict:
    try:
        hist = yf.Ticker(symbol).history(period="max")
        if hist.empty:
            return {"error": "sin datos"}

        close   = hist["Close"]
        current = float(close.iloc[-1])
        ath     = float(close.max())

        def ret(n):
            if len(close) < n + 1:
                return None
            return (current - float(close.iloc[-(n + 1)])) / float(close.iloc[-(n + 1)]) * 100

        this_year  = date.today().year
        ytd_series = close[close.index.year == this_year]
        ytd = None
        if len(ytd_series) > 1:
            ytd = (current - float(ytd_series.iloc[0])) / float(ytd_series.iloc[0]) * 100

        last_252 = close.tail(252)
        w52_high = float(last_252.max())
        w52_low  = float(last_252.min())

        return {
            "price":       current,
            "ath":         ath,
            "vs_ath":      (current - ath) / ath * 100,
            "52w_high":    w52_high,
            "52w_low":     w52_low,
            "vs_52w_high": (current - w52_high) / w52_high * 100,
            "ytd":         ytd,
            "1m":          ret(21),
            "3m":          ret(63),
            "6m":          ret(126),
            "1y":          ret(252),
            "3y":          ret(756),
        }
    except Exception as e:
        return {"error": str(e)}


def _pct(v):
    if v is None:
        return "N/A"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def _usd(v):
    return f"${v:,.2f}" if v is not None else "N/A"


def build_note(data: dict) -> str:
    today = date.today().isoformat()
    lines = [
        "---",
        f"created: {today}",
        f"updated: {today}",
        "tags:",
        "  - market-context",
        "  - dividend-analyzer",
        "  - etf",
        "---",
        "",
        "# Contexto de Mercado — ETFs Clave",
        f"**Actualizado:** {today}  |  **Frecuencia:** cada 2 semanas (día 1 y 15 del mes)",
        "",
        "> Esta nota es leída por Claude Code al inicio de sesiones del Dividend Analyzer.",
        "> Contiene precios, distancia al ATH y rendimientos históricos de los ETFs clave.",
        "> Agregar notas cualitativas en la sección al final.",
        "",
    ]

    for group, tickers in data.items():
        lines.append(f"## {group}")
        lines.append("")
        lines.append("| Ticker | Precio | ATH | vs ATH | Máx 52s | Mín 52s | vs Máx 52s | YTD | 1M | 3M | 6M | 1Y | 3Y |")
        lines.append("|--------|--------|-----|--------|---------|---------|------------|-----|----|----|----|----|-----|")

        for ticker, d in tickers.items():
            if "error" in d:
                lines.append(f"| **{ticker}** | — | — | — | — | — | — | — | — | — | — | — | — |")
                continue
            lines.append(
                f"| **{ticker}** "
                f"| {_usd(d['price'])} "
                f"| {_usd(d['ath'])} "
                f"| {_pct(d['vs_ath'])} "
                f"| {_usd(d['52w_high'])} "
                f"| {_usd(d['52w_low'])} "
                f"| {_pct(d['vs_52w_high'])} "
                f"| {_pct(d['ytd'])} "
                f"| {_pct(d['1m'])} "
                f"| {_pct(d['3m'])} "
                f"| {_pct(d['6m'])} "
                f"| {_pct(d['1y'])} "
                f"| {_pct(d['3y'])} |"
            )
        lines.append("")

    lines += [
        "## Notas de Contexto Manual",
        "",
        "> Espacio para que Daniel agregue contexto cualitativo: decisiones de la Fed,",
        "> earnings relevantes, eventos macro, narrativas de mercado, etc.",
        "> Claude lee esta sección para tener contexto que yfinance no entrega.",
        "",
        "<!-- Agregar notas aquí -->",
        "",
    ]

    return "\n".join(lines)


def main():
    print(f"[market_context] {datetime.now().strftime('%Y-%m-%d %H:%M')} — iniciando fetch")

    results = {}
    errors  = []
    for group, tickers in GROUPS.items():
        results[group] = {}
        for ticker in tickers:
            print(f"  {ticker}... ", end="", flush=True)
            d = fetch(ticker)
            results[group][ticker] = d
            if "error" in d:
                print(f"ERROR: {d['error']}")
                errors.append(ticker)
            else:
                print(f"${d['price']:,.2f}  |  ATH {_usd(d['ath'])}  |  vs ATH {_pct(d['vs_ath'])}")

    note = build_note(results)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(note)

    print(f"\n[market_context] Nota guardada: {OUT_PATH}")
    if errors:
        print(f"[market_context] Tickers con error: {', '.join(errors)}")


if __name__ == "__main__":
    main()
