#!/usr/bin/env python3
"""Refresca knowledge/roc_19a.yaml con el % de Retorno de Capital (ROC) que YieldMax publica
por distribución en la página oficial de cada fondo.

La tabla de distribuciones se renderiza por JS, así que se usa Playwright (chromium headless)
para obtener el HTML renderizado y luego pandas.read_html para extraer la tabla. El parser
(parse_distributions_from_html) está separado del fetch para poder testearlo sin navegador.

Lo corre el GitHub Action semanal (.github/workflows/refresh-roc-19a.yml). Resiliencia: si un
fondo falla al cargar/parsear, se CONSERVA su entrada previa (no se borra).

Uso local:  pip install playwright pandas lxml pyyaml && playwright install chromium
            python fetch_roc_19a.py [TICKER ...]
"""
import os
import re
import sys
import datetime
import yaml
import pandas as pd
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
ROC_PATH = os.path.join(HERE, "knowledge", "roc_19a.yaml")
INSTR_PATH = os.path.join(HERE, "knowledge", "instruments.yaml")
FUND_URL = "https://yieldmaxetfs.com/our-etfs/{tk}/"


def yieldmax_tickers():
    """Tickers tipo 'yieldmax' en instruments.yaml (la lista a refrescar)."""
    try:
        with open(INSTR_PATH, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        return []
    return sorted(str(t).upper() for t, v in data.items()
                  if isinstance(v, dict) and str(v.get("type", "")).lower() == "yieldmax")


def _parse_date(v):
    try:
        ts = pd.to_datetime(str(v), errors="coerce")
        return None if pd.isna(ts) else ts.date().isoformat()
    except Exception:
        return None


def _parse_pct(v):
    m = re.search(r"(\d{1,3}(?:\.\d+)?)", str(v))
    if not m:
        return None
    try:
        p = float(m.group(1))
        return p if 0 <= p <= 100 else None
    except ValueError:
        return None


def _parse_money(v):
    m = re.search(r"(\d+(?:\.\d+)?)", str(v).replace(",", ""))
    return float(m.group(1)) if m else None


def parse_distributions_from_html(html):
    """[(date 'YYYY-MM-DD', roc_pct, amount|None)] desde el HTML renderizado.
    Detecta la tabla por encabezados (una columna con 'date' y otra con 'roc'/'return of capital').
    Usa BeautifulSoup + html.parser (sin lxml/html5lib). Dedup por fecha."""
    soup = BeautifulSoup(html or "", "html.parser")
    for table in soup.find_all("table"):
        header_cells = table.find_all("th")
        if not header_cells:
            first = table.find("tr")
            header_cells = first.find_all(["td", "th"]) if first else []
        headers = [c.get_text(" ", strip=True).lower() for c in header_cells]
        roc_idx = next((i for i, h in enumerate(headers)
                        if "roc" in h or "return of capital" in h), None)
        date_idx = next((i for i, h in enumerate(headers) if "date" in h), None)
        if roc_idx is None or date_idx is None:
            continue
        amt_idx = next((i for i, h in enumerate(headers)
                        if "amount" in h or "per share" in h or "$" in h), None)
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
            if len(cells) <= max(roc_idx, date_idx):
                continue
            d = _parse_date(cells[date_idx])
            p = _parse_pct(cells[roc_idx])
            if d is None or p is None:
                continue
            a = _parse_money(cells[amt_idx]) if (amt_idx is not None and amt_idx < len(cells)) else None
            rows.append((d, p, a))
        if rows:
            seen, ded = set(), []
            for d, p, a in rows:
                if d in seen:
                    continue
                seen.add(d)
                ded.append((d, p, a))
            return ded
    return []


def build_entry(tk, rows):
    """Entrada de roc_19a.yaml: asof, source_url, weighted_pct (trailing ~12m por monto), per_distribution."""
    rows = sorted(rows, key=lambda r: r[0], reverse=True)
    cut = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
    num = den = 0.0
    for d, p, a in rows:
        if a and d >= cut:
            num += a * p
            den += a
    if den > 0:
        weighted = round(num / den, 2)
    elif rows:                      # sin montos: promedio simple del último año (o de todo)
        recent = [p for d, p, _ in rows if d >= cut] or [p for _, p, _ in rows]
        weighted = round(sum(recent) / len(recent), 2)
    else:
        weighted = None
    return {
        "asof": datetime.date.today().isoformat(),
        "source_url": FUND_URL.format(tk=tk.lower()),
        "weighted_pct": weighted,
        "per_distribution": [{"date": d, "roc_pct": p} for d, p, _ in rows],
    }


def fetch_rendered_html(url):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent="Mozilla/5.0")
        page.goto(url, wait_until="networkidle", timeout=60000)
        try:
            page.wait_for_selector("table", timeout=20000)
        except Exception:
            pass
        html = page.content()
        browser.close()
    return html


def main(argv):
    tickers = [t.upper() for t in argv[1:]] or yieldmax_tickers()
    if not tickers:
        print("No hay tickers yieldmax que refrescar.", file=sys.stderr)
        return 0

    existing = {}
    if os.path.exists(ROC_PATH):
        try:
            with open(ROC_PATH, "r", encoding="utf-8") as fh:
                existing = yaml.safe_load(fh) or {}
        except Exception:
            existing = {}
    out = dict(existing)

    for tk in tickers:
        url = FUND_URL.format(tk=tk.lower())
        try:
            rows = parse_distributions_from_html(fetch_rendered_html(url))
            if rows:
                out[tk] = build_entry(tk, rows)
                print(f"{tk}: {len(rows)} distribuciones, weighted_pct {out[tk]['weighted_pct']}%")
            else:
                print(f"{tk}: sin filas parseadas; conservo entrada previa", file=sys.stderr)
        except Exception as e:
            print(f"{tk}: ERROR {e}; conservo entrada previa", file=sys.stderr)

    os.makedirs(os.path.dirname(ROC_PATH), exist_ok=True)
    with open(ROC_PATH, "w", encoding="utf-8") as fh:
        fh.write("# Generado por fetch_roc_19a.py (fuente: páginas oficiales de YieldMax).\n"
                 "# Refresco semanal vía .github/workflows/refresh-roc-19a.yml. No editar a mano.\n")
        yaml.safe_dump(out, fh, sort_keys=False, allow_unicode=True)
    print(f"Escrito {ROC_PATH} ({len(out)} fondos).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
