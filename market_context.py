#!/usr/bin/env python3
"""
market_context.py
Snapshot bimensual de ETFs clave — genera nota Markdown en Obsidian.
Corre el 1 y el 15 de cada mes via cron.
"""

import yfinance as yf
import pandas as pd
from datetime import date, datetime
import os
import re
import sys
import tempfile

VAULT    = "/Users/danielzambrano/Desktop/Habilidades de agentes/Obsidian"
OUT_PATH = f"{VAULT}/APPs/Dividend-Analyzer/contexto-mercado.md"

GROUPS = {
    "Benchmarks": ["SPY", "QQQ", "VOO", "DIA", "IWM"],
    "Sectores":   ["XLK", "SMH", "XLF", "XLE", "XLV", "XLY"],
    "YieldMax / Income ETFs": ["TSLY", "NVDY", "MSTY", "CONY", "YMAX", "YMAG", "ULTY"],
    "Renta Fija / Commodities": ["TLT", "GLD", "BTC-USD"],
}


def calcular(hist: pd.DataFrame, hoy: date) -> dict:
    """Cifras de un símbolo a partir de su historial diario.

    Las ventanas son de calendario (un mes, un año), no de N sesiones: así valen igual
    para una acción (5 sesiones por semana) y para BTC-USD (7). Los niveles (precio,
    máximos, mínimos) salen del cierre sin ajustar; los rendimientos, del cierre
    ajustado por dividendos cuando el historial lo trae.
    """
    if hist is None or hist.empty or "Close" not in hist:
        return {"error": "sin datos"}
    hist = hist.sort_index()

    close = hist["Close"].dropna()
    if close.empty:
        return {"error": "sin datos"}
    total = hist["Adj Close"].dropna() if "Adj Close" in hist else close
    if total.empty:
        total = close

    ultimo  = close.index[-1]
    current = float(close.iloc[-1])
    ath     = float(close.max())
    actual_total = float(total.iloc[-1])

    def ret(**desde):
        objetivo = total.index[-1] - pd.DateOffset(**desde)
        previos = total[total.index <= objetivo]
        if previos.empty:
            return None
        base = float(previos.iloc[-1])
        if base <= 0:
            return None
        return (actual_total - base) / base * 100

    ytd = None
    if (total.index.year == hoy.year).any():
        previos = total[total.index.year < hoy.year]
        base = float(previos.iloc[-1]) if len(previos) else float(total[total.index.year == hoy.year].iloc[0])
        if base > 0:
            ytd = (actual_total - base) / base * 100

    ultimo_anio = close[close.index > ultimo - pd.DateOffset(years=1)]
    w52_high = float(ultimo_anio.max())
    w52_low  = float(ultimo_anio.min())

    return {
        "price":       current,
        "ath":         ath,
        "vs_ath":      (current - ath) / ath * 100,
        "52w_high":    w52_high,
        "52w_low":     w52_low,
        "vs_52w_high": (current - w52_high) / w52_high * 100,
        "ytd":         ytd,
        "1m":          ret(months=1),
        "3m":          ret(months=3),
        "6m":          ret(months=6),
        "1y":          ret(years=1),
        "3y":          ret(years=3),
    }


def fetch(symbol: str) -> dict:
    try:
        hist = yf.Ticker(symbol).history(period="max", auto_adjust=False)
        return calcular(hist, date.today())
    except Exception as e:
        return {"error": str(e)}


def _pct(v):
    if v is None:
        return "N/A"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def _usd(v):
    return f"${v:,.2f}" if v is not None else "N/A"


_TITULO_NOTAS = "## Notas de Contexto Manual"

_NOTAS_VACIAS = "\n".join([
    _TITULO_NOTAS,
    "",
    "> Espacio para que Daniel agregue contexto cualitativo: decisiones de la Fed,",
    "> earnings relevantes, eventos macro, narrativas de mercado, etc.",
    "> Claude lee esta sección para tener contexto que yfinance no entrega.",
    "",
    "<!-- Agregar notas aquí -->",
    "",
])


def notas_manuales(texto_previo: str) -> str:
    """La sección manual de la nota anterior, tal cual; la plantilla si no existe."""
    titulo = re.search(r"(?im)^##[ \t]+notas de contexto manual[ \t]*$", texto_previo or "")
    if titulo:
        seccion = texto_previo[titulo.start():]
        return seccion if seccion.endswith("\n") else seccion + "\n"
    return _NOTAS_VACIAS


def build_note(data: dict, notas: str = _NOTAS_VACIAS) -> str:
    today = date.today().isoformat()
    sin_dato = [t for tickers in data.values() for t, d in tickers.items() if "error" in d]
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
        "> Precio, ATH y 52 semanas: cierre sin ajustar. Rendimientos: con dividendos, por",
        "> fechas de calendario (1M = un mes atrás, 1Y = un año atrás).",
        "",
    ]
    if sin_dato:
        lines += [f"**Sin dato en esta corrida:** {', '.join(sin_dato)}", ""]

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

    return "\n".join(lines) + "\n" + notas


def guardar(ruta: str, texto: str) -> None:
    """Escribe entero o no escribe: archivo temporal al lado y cambio de nombre."""
    carpeta = os.path.dirname(ruta)
    os.makedirs(carpeta, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=carpeta, prefix=".contexto-mercado-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
        os.chmod(tmp, 0o644)
        os.replace(tmp, ruta)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def main(out_path: str = None, traer=None) -> int:
    out_path = out_path or OUT_PATH
    traer = traer or fetch
    print(f"[market_context] {datetime.now().strftime('%Y-%m-%d %H:%M')} — iniciando fetch")

    results = {}
    errors  = []
    total   = 0
    for group, tickers in GROUPS.items():
        results[group] = {}
        for ticker in tickers:
            total += 1
            print(f"  {ticker}... ", end="", flush=True)
            d = traer(ticker)
            results[group][ticker] = d
            if "error" in d:
                print(f"ERROR: {d['error']}")
                errors.append(ticker)
            else:
                print(f"${d['price']:,.2f}  |  ATH {_usd(d['ath'])}  |  vs ATH {_pct(d['vs_ath'])}")

    if len(errors) * 2 > total:
        print(f"\n[market_context] {len(errors)} de {total} tickers sin dato: la nota anterior se conserva.")
        return 1

    previo = ""
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            previo = f.read()
    guardar(out_path, build_note(results, notas_manuales(previo)))

    print(f"\n[market_context] Nota guardada: {out_path}")
    if errors:
        print(f"[market_context] Tickers con error: {', '.join(errors)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
