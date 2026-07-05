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
import time
import datetime
import yaml
import pandas as pd
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
ROC_PATH = os.path.join(HERE, "knowledge", "roc_19a.yaml")
DIST_RATE_PATH = os.path.join(HERE, "knowledge", "distribution_rate.yaml")
INSTR_PATH = os.path.join(HERE, "knowledge", "instruments.yaml")
FUND_URL = "https://yieldmaxetfs.com/our-etfs/{tk}/"

RETRIES = 3            # intentos por fondo si la tabla aún no renderiza (anti-blip transitorio)
RETRY_WAIT = 5         # segundos entre reintentos
FUND_DELAY = 1.5       # pausa entre fondos para no gatillar throttle de YieldMax


def yieldmax_tickers():
    """Tickers tipo 'yieldmax' en instruments.yaml (la lista a refrescar). Los marcados
    `delisted` (fondo cerrado/liquidado) se saltan: su página ya no existe y sus datos
    históricos previos se conservan tal cual."""
    try:
        with open(INSTR_PATH, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        return []
    return sorted(str(t).upper() for t, v in data.items()
                  if isinstance(v, dict) and str(v.get("type", "")).lower() == "yieldmax"
                  and not v.get("delisted"))


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


def _parse_rate_pct(v):
    """Como _parse_pct pero permite tasas > 100%: las 'distribution rate' anualizadas de
    YieldMax pueden superar el 100% (p.ej. fondos muy volátiles)."""
    m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", str(v))
    if not m:
        return None
    try:
        p = float(m.group(1))
        return p if 0 < p <= 999 else None
    except ValueError:
        return None


def parse_distribution_rate_from_html(html):
    """Extrae la 'Distribution Rate' TITULAR (y su fecha 'as of' si está) del fund page de
    YieldMax. Devuelve {'rate_pct': float|None, 'as_of': 'YYYY-MM-DD'|None}.

    YieldMax la muestra como una stat destacada (fuera de la tabla de distribuciones): una
    etiqueta 'Distribution Rate' con un valor 'XX.XX%' cercano. Se toma el primer % DESPUÉS de
    la etiqueta (sin cruzar otro %), para no confundirlo con '30-Day SEC Yield'. Testeable sin
    navegador."""
    out = {"rate_pct": None, "as_of": None}
    soup = BeautifulSoup(html or "", "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    # En la página real el valor titular PRECEDE a la etiqueta: "65.82% Distribution Rate*".
    # Exigimos decimales para no capturar el "12% distribution rate" de la prosa de marketing
    # ni el "30-Day SEC Yield" contiguo.
    m = re.search(r"(\d{1,3}\.\d+)\s*%\s*distribution\s+rate", text, re.IGNORECASE)
    if m:
        out["rate_pct"] = _parse_rate_pct(m.group(1) + "%")
        # Fecha "As of: MM/DD/YYYY" en la ventana inmediata tras la etiqueta titular.
        tail = text[m.end():m.end() + 140]
        md = re.search(r"as of:?\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})", tail, re.IGNORECASE)
        if md:
            out["as_of"] = _parse_date(md.group(1))
    return out


def build_rate_entry(tk, rate_info):
    """Entrada de distribution_rate.yaml para un fondo."""
    return {
        "rate_pct": rate_info.get("rate_pct"),
        "as_of": rate_info.get("as_of") or datetime.date.today().isoformat(),
        "source_url": FUND_URL.format(tk=tk.lower()),
    }


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
        try:
            page = browser.new_page(user_agent="Mozilla/5.0")
            page.goto(url, wait_until="networkidle", timeout=60000)
            # Espera a que aparezca una tabla y, mejor aún, a que alguna traiga "ROC"
            # (la tabla de distribuciones se renderiza por JS y a veces tarda).
            try:
                page.wait_for_selector("table", timeout=25000)
                try:
                    page.wait_for_function(
                        "() => Array.from(document.querySelectorAll('table'))"
                        ".some(t => /roc|return of capital/i.test(t.innerText))",
                        timeout=15000)
                except Exception:
                    pass
                page.wait_for_timeout(2500)   # margen para que termine de poblar la tabla
            except Exception:
                pass
            html = page.content()
        finally:
            browser.close()
    return html


_BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    "Referer": "https://yieldmaxetfs.com/",
}

_CHALLENGE_MARKERS = ("just a moment", "cf-challenge", "attention required",
                      "verify you are human", "checking your browser")


def _challenge_hint(html, tk):
    """Si el HTML recibido parece una página de challenge anti-bot, dejarlo dicho en el log
    (distingue 'nos bloquean' de 'cambió la página')."""
    low = (html or "").lower()
    for marker in _CHALLENGE_MARKERS:
        if marker in low:
            print(f"::warning::{tk}: el HTML recibido parece challenge anti-bot "
                  f"('{marker}') — bloqueo al runner, no cambio de página.", file=sys.stderr)
            return True
    return False


def fetch_plain_html(url):
    """Fetch sin navegador: la tabla de distribuciones hoy viene server-rendered en el HTML
    plano, así que esto suele bastar y evita el fingerprint de chromium headless."""
    import requests
    resp = requests.get(url, headers=_BROWSER_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


class PageGone(Exception):
    """La página del fondo devuelve 404: fondo cerrado/renombrado, no un fallo del parser."""


def fetch_rows_with_retries(url, tk):
    """Capas: (1) HTTP plano con headers de navegador; (2) Playwright renderizado.
    Reintenta si la tabla no rindió (0 filas). Devuelve (rows, html): las filas ROC y el
    HTML de la última carga (para parsear también la Distribution Rate titular de la MISMA
    carga de página). Lanza PageGone si la página da 404 (fondo retirado)."""
    rows, html = [], ""
    for attempt in range(1, RETRIES + 1):
        try:
            html = fetch_plain_html(url)
            rows = parse_distributions_from_html(html)
        except Exception as e:
            if getattr(getattr(e, "response", None), "status_code", None) == 404:
                raise PageGone(url)
            print(f"::warning::{tk}: intento plano {attempt}/{RETRIES} ERROR: {e}", file=sys.stderr)
        if rows:
            return rows, html
        _challenge_hint(html, tk)
        if attempt < RETRIES:
            time.sleep(RETRY_WAIT)
    for attempt in range(1, RETRIES + 1):
        try:
            html = fetch_rendered_html(url)
            rows = parse_distributions_from_html(html)
        except Exception as e:
            print(f"::warning::{tk}: intento {attempt}/{RETRIES} ERROR: {e}", file=sys.stderr)
        if rows:
            return rows, html
        _challenge_hint(html, tk)
        if attempt < RETRIES:
            time.sleep(RETRY_WAIT)
    return rows, html


def main(argv):
    tickers = [t.upper() for t in argv[1:]] or yieldmax_tickers()
    if not tickers:
        print("No hay tickers yieldmax que refrescar.", file=sys.stderr)
        return 0

    def _load_yaml(path):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    return yaml.safe_load(fh) or {}
            except Exception:
                return {}
        return {}

    existing = _load_yaml(ROC_PATH)
    out = dict(existing)
    existing_rates = _load_yaml(DIST_RATE_PATH)
    out_rates = dict(existing_rates)

    regressions, empty_new = [], []
    for tk in tickers:
        url = FUND_URL.format(tk=tk.lower())
        try:
            rows, html = fetch_rows_with_retries(url, tk)
        except PageGone:
            print(f"::warning::{tk}: la página del fondo da 404 (¿cerrado/renombrado?). "
                  f"Conservo datos previos; si cerró, marca `delisted:` en instruments.yaml.",
                  file=sys.stderr)
            time.sleep(FUND_DELAY)
            continue
        time.sleep(FUND_DELAY)
        if rows:
            out[tk] = build_entry(tk, rows)
            print(f"{tk}: {len(rows)} distribuciones, weighted_pct {out[tk]['weighted_pct']}%")
        else:
            had_prior = bool((existing.get(tk) or {}).get("per_distribution"))
            if had_prior:
                # Tenía datos y ahora no parsea nada -> probable cambio en la página. Auto-vigilancia.
                regressions.append(tk)
                print(f"::error::{tk}: 0 filas parseadas pero tenía datos previos "
                      f"(¿cambió la página de YieldMax?). Conservo la entrada previa.", file=sys.stderr)
            else:
                empty_new.append(tk)
                print(f"::warning::{tk}: sin filas y sin datos previos "
                      f"(¿ticker/URL correctos? {url})", file=sys.stderr)

        # Distribution Rate titular (de la misma carga de página). Resiliencia: si no se
        # parsea pero había valor previo, se conserva (no se pisa con None).
        rate_info = parse_distribution_rate_from_html(html)
        if rate_info.get("rate_pct") is not None:
            out_rates[tk] = build_rate_entry(tk, rate_info)
            print(f"{tk}: distribution rate titular {out_rates[tk]['rate_pct']}%")
        elif (existing_rates.get(tk) or {}).get("rate_pct") is not None:
            print(f"::warning::{tk}: no se parseó la Distribution Rate (conservo la previa "
                  f"{existing_rates[tk]['rate_pct']}%).", file=sys.stderr)
        else:
            print(f"::warning::{tk}: sin Distribution Rate titular y sin valor previo.",
                  file=sys.stderr)

    os.makedirs(os.path.dirname(ROC_PATH), exist_ok=True)
    with open(ROC_PATH, "w", encoding="utf-8") as fh:
        fh.write("# Generado por fetch_roc_19a.py (fuente: páginas oficiales de YieldMax).\n"
                 "# Refresco semanal vía .github/workflows/refresh-roc-19a.yml. No editar a mano.\n")
        yaml.safe_dump(out, fh, sort_keys=False, allow_unicode=True)
    with open(DIST_RATE_PATH, "w", encoding="utf-8") as fh:
        fh.write("# Generado por fetch_roc_19a.py: tasa de distribución TITULAR que anuncia "
                 "YieldMax por fondo.\n# Refresco semanal vía .github/workflows/refresh-roc-19a.yml. "
                 "No editar a mano.\n")
        yaml.safe_dump(out_rates, fh, sort_keys=False, allow_unicode=True)
    print(f"Escrito {ROC_PATH} ({len(out)} fondos) y {DIST_RATE_PATH} ({len(out_rates)} tasas). "
          f"Nuevos sin datos: {empty_new or '—'}. Regresiones: {regressions or '—'}.")

    # Salir con error SOLO si un fondo que tenía datos los perdió (dispara email de GitHub).
    # Los datos buenos ya se escribieron; el commit corre con if: always().
    if regressions:
        print(f"::error::Regresión en: {', '.join(regressions)}. "
              f"Revisa el parser/página. Los demás fondos se actualizaron igual.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
