import pandas as pd
import numpy as np
import numpy_financial as npf
import yfinance as yf
import datetime
import streamlit as st
from curl_cffi import requests as crequests
import re
import io
import os
from collections import defaultdict

try:
    import yaml as _yaml
except Exception:
    _yaml = None

GEMINI_VISION_MODEL = "gemini-2.5-flash"
GEMINI_VISION_FALLBACKS = ["gemini-2.5-flash-lite"]


def extract_positions_from_images(images, candidate_tickers, api_key):
    """Lee fotos de la tabla de posiciones de un broker con Gemini Vision.

    Devuelve {TICKER: {'cost_basis': float, 'shares': float|None, 'market_value': float|None}}
    para los tickers solicitados que aparezcan con costo base > 0.
    images: lista de (bytes, mime_type). candidate_tickers: simbolos a buscar. api_key: Gemini API.
    Nunca lanza excepcion: devuelve {} ante cualquier fallo (sin SDK/red/cuota/JSON invalido).
    """
    if not images or not candidate_tickers or not api_key:
        return {}
    try:
        from google import genai
        from google.genai import types
        import json as _json
        import time as _time
    except Exception:
        return {}

    cand = [str(t).upper().strip() for t in candidate_tickers]
    cand_set = set(cand)

    prompt = (
        "Estas son una o varias imagenes de la pantalla de posiciones de un broker: "
        "Interactive Brokers (seccion 'Sus participaciones', en espanol) o Charles Schwab (en ingles). "
        "Para cada simbolo solicitado, lee la FILA COMPLETA y devuelve: "
        "1) 'cost_basis' = la columna cuyo ENCABEZADO es 'BASE DE COSTE' (Interactive Brokers) o "
        "'Cost Basis' (Charles Schwab) = el COSTO TOTAL invertido en esa posicion; "
        "2) 'shares' = la cantidad de acciones, columna 'POSICION' (Interactive Brokers) o 'Qty' (Charles Schwab). "
        "Tambien, para reducir errores, devuelve 'price' (precio por accion: 'ULTIMO'/'Price') y "
        "'market_value' (valor de mercado: 'VALOR DE MERCADO'/'Mkt Val'). "
        "NO confundas cost_basis con price, market_value ni gain/loss; identifica cada columna por su ENCABEZADO. "
        "Como referencia de layout: Interactive Brokers suele ser "
        "INSTRUMENTO, POSICION, ULTIMO, % VARIACION, BASE DE COSTE, VALOR DE MERCADO, PRECIO MEDIO; "
        "Charles Schwab suele ser Symbol, Description, Qty, Price, ..., Mkt Val, ..., Cost Basis, Gain/Loss. "
        "Formatos numericos: Interactive Brokers usa formato europeo ('4.231,32' = 4231.32 ; '14.794' = 14794); "
        "Charles Schwab usa formato US con simbolo de dolar ('$4,553.06' = 4553.06). "
        "Devuelve SIEMPRE numeros con punto decimal y sin simbolos ni separadores de miles. "
        "Incluye UNICAMENTE estos simbolos si aparecen: " + ", ".join(cand) +
        ". Omite cualquier otro simbolo. Si un simbolo de la lista no aparece en las imagenes, no lo incluyas."
    )

    schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "positions": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "ticker": types.Schema(type=types.Type.STRING),
                        "shares": types.Schema(type=types.Type.NUMBER),
                        "price": types.Schema(type=types.Type.NUMBER),
                        "cost_basis": types.Schema(type=types.Type.NUMBER),
                        "market_value": types.Schema(type=types.Type.NUMBER),
                    },
                    required=["ticker", "cost_basis"],
                ),
            )
        },
        required=["positions"],
    )

    try:
        client = genai.Client(api_key=api_key)
    except Exception:
        return {}

    def _num(v):
        try:
            f = float(v)
            return f if f > 0 else None
        except (TypeError, ValueError):
            return None

    # Todas las fotos en UN solo request (las posiciones pueden estar repartidas en varias capturas).
    contents = [types.Part.from_bytes(data=b, mime_type=(m or "image/jpeg")) for b, m in images]
    contents.append(prompt)

    cfg = types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json",
        response_schema=schema,
    )
    # Reintentos + modelo de respaldo: gemini-2.5-flash a veces devuelve 503 (saturado);
    # se reintenta una vez y luego se cae a un modelo alterno con otra capacidad.
    for _model in [GEMINI_VISION_MODEL] + GEMINI_VISION_FALLBACKS:
        for _attempt in range(2):
            try:
                resp = client.models.generate_content(model=_model, contents=contents, config=cfg)
                data = _json.loads(resp.text)
                out = {}
                for row in data.get("positions", []):
                    tk = str(row.get("ticker", "")).upper().strip()
                    if tk not in cand_set:
                        continue
                    cost = _num(row.get("cost_basis"))
                    if cost is None:
                        continue
                    out[tk] = {
                        "cost_basis": cost,
                        "shares": _num(row.get("shares")),
                        "market_value": _num(row.get("market_value")),
                    }
                return out  # llamada exitosa (out puede estar vacio si no encontro tickers)
            except Exception as _e:
                _msg = str(_e)
                _transient = any(s in _msg for s in (
                    "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "overloaded", "high demand"))
                if _transient and _attempt == 0:
                    try:
                        _time.sleep(2)
                    except Exception:
                        pass
                    continue  # reintentar el mismo modelo
                break  # error no transitorio o ya reintentado -> probar siguiente modelo

    return {}


def extract_cost_basis_from_images(images, candidate_tickers, api_key):
    """Wrapper de compatibilidad: devuelve solo {TICKER: costo_base_float}."""
    rich = extract_positions_from_images(images, candidate_tickers, api_key)
    return {t: v["cost_basis"] for t, v in rich.items() if v.get("cost_basis")}


def _sum_roc_credit_from_forms(per_form):
    """Suma el credito de retencion (casilla 10) de los formularios 1042-S con
    income code 37 (Return of Capital). Los codigos 01 (interes) y 06 (dividendo)
    nunca se suman. Si falta withholding_credit usa federal_tax_withheld (7a) de respaldo.
    Devuelve {'credit': float, 'roc_gross': float, 'per_form': [...]} (vacio si no hay code 37).
    """
    def _code37(v):
        m = re.search(r"\d+", str(v or ""))
        return m is not None and int(m.group()) == 37

    def _num(v):
        try:
            f = float(v)
            return f
        except (TypeError, ValueError):
            return 0.0

    matched = []
    credit_total = 0.0
    gross_total = 0.0
    for row in per_form or []:
        if not isinstance(row, dict) or not _code37(row.get("income_code")):
            continue
        credit = _num(row.get("withholding_credit"))
        if not credit:
            credit = _num(row.get("federal_tax_withheld"))
        gross = _num(row.get("gross_income"))
        credit_total += credit
        gross_total += gross
        matched.append(row)

    if not matched:
        return {"credit": 0.0, "roc_gross": 0.0, "per_form": []}
    return {"credit": credit_total, "roc_gross": gross_total, "per_form": matched}


def extract_roc_credit_from_pdf(pdf_bytes, api_key):
    """Lee un 1042-S en PDF con Gemini y devuelve el credito ROC (income code 37, casilla 10).

    Devuelve {'credit': float, 'roc_gross': float, 'per_form': [...]} o None ante cualquier
    fallo (sin SDK/red/cuota/JSON invalido). El PDF nunca se guarda; se procesa en memoria.
    """
    if not pdf_bytes or not api_key:
        return None
    try:
        from google import genai
        from google.genai import types
        import json as _json
        import time as _time
    except Exception:
        return None

    prompt = (
        "Este es un formulario fiscal IRS 1042-S (puede contener varios formularios o paginas, "
        "uno por cada income code). Por cada formulario que encuentres, extrae: "
        "1) 'income_code' = Box 1 (Income code); "
        "2) 'gross_income' = Box 2 (Gross income); "
        "3) 'federal_tax_withheld' = Box 7a (Federal tax withheld); "
        "4) 'withholding_credit' = Box 10 (Total withholding credit). "
        "Devuelve SIEMPRE numeros con punto decimal y sin simbolos ni separadores de miles. "
        "Incluye TODOS los formularios que encuentres, sin filtrar por income code; "
        "el filtrado lo hace otro sistema."
    )

    schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "forms": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "income_code": types.Schema(type=types.Type.STRING),
                        "gross_income": types.Schema(type=types.Type.NUMBER),
                        "federal_tax_withheld": types.Schema(type=types.Type.NUMBER),
                        "withholding_credit": types.Schema(type=types.Type.NUMBER),
                    },
                    required=["income_code"],
                ),
            )
        },
        required=["forms"],
    )

    try:
        client = genai.Client(api_key=api_key)
    except Exception:
        return None

    contents = [types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), prompt]
    cfg = types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json",
        response_schema=schema,
    )
    for _model in [GEMINI_VISION_MODEL] + GEMINI_VISION_FALLBACKS:
        for _attempt in range(2):
            try:
                resp = client.models.generate_content(model=_model, contents=contents, config=cfg)
                data = _json.loads(resp.text)
                return _sum_roc_credit_from_forms(data.get("forms", []))
            except Exception as _e:
                _msg = str(_e)
                _transient = any(s in _msg for s in (
                    "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "overloaded", "high demand"))
                if _transient and _attempt == 0:
                    try:
                        _time.sleep(2)
                    except Exception:
                        pass
                    continue
                break

    return None


def get_session():
    """
    Creates a curl_cffi session mimicking Chrome to bypass bot detection.
    """
    return crequests.Session(impersonate="chrome")


def _cumul_split_factor(tx_date, splits_series: pd.Series) -> float:
    """Return the cumulative split factor that applies to a share purchased on tx_date.

    Multiplies all split ratios that occurred AFTER tx_date so that historical
    share quantities from the CSV (which are in pre-split units) are correctly
    scaled to today's share count.

    Example: XLK 2:1 split on 2025-12-05.
    A share bought on 2024-08-26 → factor = 2.0 → counts as 2 shares today.
    A share bought on 2026-01-29 (post-split) → factor = 1.0 → no adjustment.
    """
    if splits_series is None or splits_series.empty:
        return 1.0
    try:
        tx_ts = pd.Timestamp(tx_date).normalize()
        if tx_ts.tzinfo is not None:
            tx_ts = tx_ts.tz_localize(None)
        idx = splits_series.index
        if idx.tzinfo is not None:
            idx = idx.tz_localize(None)
        future = splits_series[idx.normalize() > tx_ts]
        factor = 1.0
        for r in future:
            factor *= float(r)
        return factor
    except Exception:
        return 1.0

def _net_transfer_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """Neutraliza pares de migración entre brokers (p. ej. TD Ameritrade -> Schwab).

    Una transferencia de cuenta aparece como DOS filas el mismo día y mismo ticker:
    una 'Journaled Shares' de salida (Quantity < 0, descripción "...TRANSFER...OUT")
    y una 'Internal Transfer' de entrada (Quantity > 0). Son las dos patas del mismo
    movimiento; si se suman se anulan y la posición transferida cuenta 0. Eliminamos la
    pata de salida (journaled OUT) cuando existe su entrada gemela, dejando solo la
    entrada neta. Las 'Journaled Shares' sin gemela (salidas reales) se conservan.
    """
    if df is None or df.empty or 'Action' not in df.columns or 'Quantity' not in df.columns:
        return df
    if 'Ticker' not in df.columns or 'Date' not in df.columns:
        return df
    out = df.copy()
    act = out['Action'].astype(str).str.lower()
    qty = pd.to_numeric(out['Quantity'], errors='coerce').fillna(0)
    journal_out = act.str.contains('journal', na=False) & (qty < 0)
    transfer_in = act.str.contains('transfer', na=False) & (qty > 0)
    if not journal_out.any() or not transfer_in.any():
        return df
    drop_idx = []
    in_idx = list(out.index[transfer_in])
    for i in out.index[journal_out]:
        t, d, q = out.at[i, 'Ticker'], out.at[i, 'Date'], abs(qty[i])
        for j in in_idx:
            if (out.at[j, 'Ticker'] == t and out.at[j, 'Date'] == d
                    and abs(abs(qty[j]) - q) < 1e-6 and j not in drop_idx):
                drop_idx.append(i)
                in_idx.remove(j)  # cada entrada empareja con una sola salida
                break
    return out.drop(index=drop_idx) if drop_idx else df


def _winsorize_returns(returns, lower=0.01, upper=0.99, min_len=20):
    """Acota una serie de retornos diarios a sus cuantiles [lower, upper] para que outliers
    espurios (transferencias de acciones sin efectivo, desfases de split, ticks malos de la API)
    no distorsionen vol/Sharpe/Sortino/beta. Series cortas (<min_len) se devuelven tal cual
    (los cuantiles no serían fiables). Defensiva ante entradas no-Series."""
    try:
        r = returns.dropna()
    except AttributeError:
        return returns
    if len(r) < min_len:
        return r
    lo, hi = r.quantile(lower), r.quantile(upper)
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return r
    return r.clip(lo, hi)


def _sortino_ratio(daily_returns, rf_daily, periods: int = 252):
    """Sortino anualizado con downside deviation estándar (CFA/GIPS).

    Downside deviation = raíz de la media de (min(r - MAR, 0))^2 sobre TODOS los
    períodos (no solo los días negativos), con MAR = rf_daily. Esto difiere de usar
    `std` de los retornos negativos (que excluye los días positivos del denominador
    y subestima el riesgo a la baja). Devuelve None si no hay datos suficientes o no
    hay desviación a la baja.
    """
    r = daily_returns.dropna() if hasattr(daily_returns, 'dropna') else pd.Series(list(daily_returns))
    if len(r) < 2:
        return None
    downside = np.minimum(r - rf_daily, 0.0)
    dd = float(np.sqrt((downside ** 2).mean()))
    if dd <= 1e-9:
        return None
    excess = float(r.mean()) - rf_daily
    return float((excess / dd) * np.sqrt(periods))


def normalize_csv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardizes a broker's CSV export into a unified format for analysis.
    
    Args:
        df: The raw DataFrame loaded from the CSV.
        
    Returns:
        A normalized DataFrame with standard columns: Date, Action, Ticker, Quantity, Price, Amount.
    """
    # 0. Smart Header Detection (Metadata Skipping)
    # Check if we need to find the header row
    # Heuristic: If "Ticker" or "Date" is not in columns, scan first 20 rows
    
    # Potential keywords that signify a header row
    header_keywords = [
        'ticker', 'symbol', 'símbolo', 'simbolo', 
        'date', 'fecha', 'time',
        'quantity', 'cantidad', 'shares', 'acciones',
        'price', 'precio', 
        'amount', 'monto', 'total', 'valor',
        'action', 'accion', 'operacion', 'operation', 'tipo'
    ]
    
    def is_likely_header(row_vals):
        # Count how many keywords appear in this row
        matches = 0
        row_str = [str(x).lower() for x in row_vals]
        for key in header_keywords:
            if any(key in str(cell) for cell in row_str):
                matches += 1
        return matches >= 2 # At least 2 matches to be confident (e.g. Date AND Ticker)

    # Check current columns first
    if not is_likely_header(df.columns):
        # Scan first 20 rows
        for i in range(min(20, len(df))):
            row = df.iloc[i]
            if is_likely_header(row.values):
                # Found the header!
                # Set this row as header
                df.columns = df.iloc[i]
                # Mod: slice data from next row
                df = df[i+1:].reset_index(drop=True)
                break

    # 1. Robust Column Renaming
    # Strip whitespace from headers and try to match case-insensitively
    df.columns = df.columns.astype(str).str.strip()
    
    # Ensure column names are unique (to prevent Streamlit/Arrow rendering errors)
    new_cols = []
    seen = {}
    for c in df.columns:
        if c in seen:
            seen[c] += 1
            new_cols.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            new_cols.append(c)
    df.columns = new_cols
    
    # Internal map (lowercase keys for matching)
    col_map_lower = {
        'fecha': 'Date', 'date': 'Date', 'time': 'Date',
        'descripción': 'Action', 'descripcion': 'Action', 'action': 'Action', 'operación': 'Action', 'operacion': 'Action',
        'símbolo': 'Ticker', 'simbolo': 'Ticker', 'ticker': 'Ticker', 'symbol': 'Ticker',
        'cantidad': 'Quantity', 'quantity': 'Quantity', 'shares': 'Quantity',
        'precio': 'Price', 'price': 'Price',
        'monto': 'Amount', 'amount': 'Amount', 'total': 'Amount', 'value': 'Amount'
    }
    
    # Create a rename dict by checking lowercase versions of actual columns
    actual_rename_map = {}
    for col in df.columns:
        col_lower = str(col).lower()
        if col_lower in col_map_lower:
            actual_rename_map[col] = col_map_lower[col_lower]
            
    df = df.rename(columns=actual_rename_map)
    
    # Ensure Date is datetime
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date'])
    
    # Clean Ticker (remove spaces)
    if 'Ticker' in df.columns:
        df['Ticker'] = df['Ticker'].astype(str).str.strip()

    # Clean Numeric Columns (Aggressive Regex)
    cols_to_clean = ['Quantity', 'Price', 'Amount']
    for col in cols_to_clean:
        if col in df.columns:
            # European Format Handling: 1.000,00 -> 1000.00
            # 1. Remove thousands separator (.) if present
            # 2. Replace decimal separator (,) with (.)
            # NOTE: This approach optimizes for the user's specific Screenshot format ($ 2,34)
            # It assumes the file is NOT using commas for thousands (e.g. 1,000.00 would break)
            
            # Helper to clean single value
            # Disambiguates US (1,234.56) vs European (1.234,56) by the LAST
            # separator: whichever of '.'/',' appears last is the decimal point;
            # the other is the thousands separator and gets stripped.
            def clean_val(x):
                s = str(x).strip()
                has_comma = ',' in s
                has_dot = '.' in s
                if has_comma and has_dot:
                    if s.rfind(',') > s.rfind('.'):
                        # European: 12.500,00 -> dot=thousands, comma=decimal
                        s = s.replace('.', '').replace(',', '.')
                    else:
                        # US: 12,500.00 -> comma=thousands, dot=decimal
                        s = s.replace(',', '')
                elif has_comma:
                    # Only a comma present: treat as decimal (European / IB '0,155').
                    # NOTA: no se puede distinguir la coma de miles US ("1,234"→1234) del
                    # decimal europeo ("579,314"→579.314) desde el string — ambos son
                    # \d{1,3},\d{3}. Se prioriza IB (formato real en uso); un CSV genérico
                    # US con miles y sin decimales es un caso hipotético que no se soporta.
                    s = s.replace(',', '.')
                # only a dot or no separator: already valid
                return s

            df[col] = df[col].apply(clean_val)
            
            # 1. Convert to string
            # 2. Remove anything that is NOT a digit, dot, or minus sign
            # 3. Handle empty strings resulting from bad data
            df[col] = df[col].astype(str).str.replace(r'[^\d.-]', '', regex=True)
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    return df

@st.cache_data(ttl=3600)

def fetch_data_from_html(ticker):
    """
    Fallback: Scrapes historical data from Yahoo Finance HTML if API fails.
    Uses curl_cffi to mimic a browser and regex to parse the table.
    """
    print(f"Scraping HTML for {ticker}...")
    url = f"https://finance.yahoo.com/quote/{ticker}/history?p={ticker}"
    
    try:
        session = get_session()
        response = session.get(url, timeout=10)
        
        if response.status_code == 200:
            if "Historical Data" in response.text:
                # Regex parse table rows
                rows = re.findall(r'<tr.*?>(.*?)</tr>', response.text, re.DOTALL)
                data = []
                for row in rows:
                    cols = re.findall(r'<td.*?>(.*?)</td>', row, re.DOTALL)
                    cols = [re.sub(r'<.*?>', '', c).strip() for c in cols]
                    if len(cols) == 7: # Standard price row
                        data.append(cols)
                
                if data:
                    df = pd.DataFrame(data, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume'])
                    
                    # Clean and Convert Data
                    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
                    df = df.dropna(subset=['Date'])
                    df = df.set_index('Date').sort_index()
                    
                    cols_to_numeric = ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
                    for col in cols_to_numeric:
                        # Remove commas from volume, handle errors
                        df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
                    
                    return df.dropna()
                    
            print("HTML Scraping failed to find valid data table.")
            return pd.DataFrame()
        else:
            print(f"HTML Scrape failed. Status: {response.status_code}")
            return pd.DataFrame()
    except Exception as e:
        print(f"HTML Scrape Exception: {e}")
        return pd.DataFrame()

def fetch_market_data(ticker, start_date):
    """
    Fetches raw market data (auto_adjust=False) to correctly calculate dividends and splits.
    Includes robust keys and fallback mechanisms.
    """
    # Extend start date back a bit to ensure we cover the first transaction
    start_date_obj = pd.to_datetime(start_date)
    buffer_date = start_date_obj - datetime.timedelta(days=10)

    def _naive_index(_d):
        # yf.Ticker().history() devuelve indice tz-aware (zona del exchange); yf.download() suele ser
        # tz-naive. Normalizar SIEMPRE a tz-naive para no romper comparaciones con fechas del CSV.
        try:
            if getattr(_d.index, "tz", None) is not None:
                _d.index = _d.index.tz_localize(None)
        except (TypeError, AttributeError):
            try:
                _d.index = pd.to_datetime(_d.index).tz_localize(None)
            except Exception:
                pass
        return _d


    # 1. Try yf.download (Standard Bulk API) - 2 Attempts
    try:
        session = get_session()
    except Exception as e:
        print(f"Failed to create curl_cffi session: {e}")
        session = None

    for attempt in range(2):
        try:
            # print(f"Downloading {ticker} (Attempt {attempt+1})...")
            data = yf.download(ticker, start=buffer_date, progress=False, auto_adjust=False, actions=True, session=session)
            
            if not data.empty:
                # Flatten MultiIndex if present
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                return _naive_index(data), None
        except Exception as e:
            print(f"Error downloading {ticker} (Attempt {attempt+1}): {e}")
    
    # 2. Fallback: yf.Ticker().history (Single API)
    # Sometimes yf.download fails for specific tickers/IPs, but Ticker object works.
    print(f"Falling back to yf.Ticker({ticker}).history()...")
    try:
        t = yf.Ticker(ticker, session=session)
        data = t.history(start=buffer_date, auto_adjust=False, actions=True)
        
        if not data.empty:
            # history() devuelve indice tz-aware: normalizar a tz-naive antes de retornar.
            return _naive_index(data), None
            
    except Exception as e:
        print(f"Fallback error for {ticker}: {e}")
        
    # 3. Last Resort: HTML Scraping
    print(f"Attempting HTML scraping for {ticker}...")
    data = fetch_data_from_html(ticker)
    if not data.empty:
        # Filter by start date if needed
        data = _naive_index(data)
        data = data[data.index >= pd.to_datetime(buffer_date)]
        return data, None

    return pd.DataFrame(), "No market data found: API Rate Limited & Scraper failed."

@st.cache_data(show_spinner=False)
def simulate_strategy_cached(ticker, start_date_str, initial_investment):
    """Cache wrapper for simulate_strategy. Uses string for start_date to ensure hashability."""
    start_date = datetime.date.fromisoformat(start_date_str)
    return simulate_strategy(ticker, start_date, initial_investment)


@st.cache_data(show_spinner=False)
def analyze_portfolio(df: pd.DataFrame, version: str = "1.2.1", ib_cost_basis_map: dict = None,
                      position_overrides: dict = None) -> dict:
    """
    Performs a forensic analysis of a portfolio history to calculate true ROI and dividend performance.
    
    This function separates 'Pocket Investment' (real cash out) from 'DRIP implementation' 
    (dividends used to buy shares) to provide a true picture of performance.
    
    Args:
        df: Normalized DataFrame containing transaction history.
        version: Cache-busting version string.
        
    Returns:
        A dictionary keyed by Ticker containing detailed performance metrics and daily history.
    """
    results = {}

    # Neutralizar pares de migración entre brokers (TDA -> Schwab) antes de contar.
    df = _net_transfer_pairs(df)

    # Fecha del snapshot del CSV (última actividad registrada): referencia para "rancio" y TTM,
    # así un CSV exportado hace meses no marca falsos positivos contra el today real.
    try:
        _snapshot_date = pd.to_datetime(df['Date'], errors='coerce').max()
        if pd.isna(_snapshot_date):
            _snapshot_date = None
    except Exception:
        _snapshot_date = None

    # Group by Ticker
    tickers = df['Ticker'].unique()
    
    for ticker in tickers:
        ticker_df = df[df['Ticker'] == ticker].sort_values('Date')
        if ticker_df.empty:
            continue

        # v2.1 — Descartar tickers no reconocidos como ETF de largo plazo (antes de API call)
        ticker_mode_early = classify_tickers([ticker]).get(ticker, 'mode_skip')
        if ticker_mode_early == 'mode_skip':
            results[ticker] = {
                "skipped": True,
                "reason": "not_known_etf",
                "ticker": ticker,
            }
            continue

        # v2.1 — Descartar posiciones cerradas en < 14 días (trades de muy corto plazo)
        too_brief, holding_days = is_held_too_briefly(ticker_df, threshold_days=14)
        if too_brief:
            results[ticker] = {
                "skipped": True,
                "reason": "held_less_than_14_days",
                "holding_days": holding_days,
                "ticker": ticker,
            }
            continue

        first_date = ticker_df['Date'].min()
        market_data, error_msg = fetch_market_data(ticker, first_date)
        
        if market_data.empty:
            results[ticker] = {"error": f"No market data found: {error_msg}"}
            continue

        current_price = market_data['Close'].iloc[-1]
        
        # --- Split data for per-transaction adjustment ---
        # market_data is fetched with actions=True so it includes Stock Splits column.
        # We build a Series of (split_date → ratio) covering the holding period.
        _splits_col = pd.Series(dtype=float)
        if 'Stock Splits' in market_data.columns:
            _raw = market_data['Stock Splits']
            _splits_col = _raw[_raw > 0]  # keep only actual split events
        splits_detected = []
        if not _splits_col.empty:
            for _sd, _sr in _splits_col.items():
                splits_detected.append({"date": str(_sd)[:10], "ratio": float(_sr)})

        # --- Analysis Variables ---
        pocket_investment = 0.0 # Net cash flow from user's pocket
        shares_owned = 0.0
        shares_owned_pocket = 0.0
        shares_owned_drip = 0.0
        total_shares_bought = 0.0  # gross buys (before sells)
        total_shares_sold = 0.0    # gross sells
        dividends_collected_cash = 0.0
        dividends_collected_drip = 0.0 # Value of dividends reinvested
        history_incomplete = False  # True when sells exceed tracked buys (CSV missing prior history)
        
        # Helper for defensive parsing
        def safe_float(val):
            try:
                if pd.isna(val): return 0.0
                return float(val)
            except ValueError:
                # Cleaning fallback
                clean_val = str(val).replace('$', '').replace(',', '').replace(' ', '')
                try:
                    return float(clean_val)
                except ValueError:
                    return 0.0

        # Iterate through transactions to build history
        cash_flows      = []
        irr_flows_dated = []   # (date, signed_amount) para cálculo de IRR real
        dist_dated      = []   # (date, monto) de distribuciones recibidas (cash + reinvertido) p/ ROC 19a
        divs_by_year    = defaultdict(float)  # año calendario -> dividendos netos del año (cash + drip)
        for idx, row in ticker_df.iterrows():
            action = str(row['Action']).lower()
            qty = safe_float(row.get('Quantity', 0))
            amount = safe_float(row.get('Amount', 0))
            
            # --- Semantic Classification (Robust) ---
            # Determine intent based on description keywords
            
            # 1. DRIP (Reinversión)
            # Keywords: reinvest, reinversión, drip
            is_drip = 'reinvest' in action or 'reinversión' in action or 'drip' in action
            
            # 2. Buy (Compra)
            # Keywords: buy, bought, compra
            # Exclusion: Ensure it's not a 'reinvest' buy (which is handled by DRIP logic)
            is_buy = ('buy' in action or 'bought' in action or 'compra' in action) and not is_drip
            
            # 3. Sell (Venta)
            # Keywords: sell, sold, venta
            is_sell = 'sell' in action or 'sold' in action or 'venta' in action
            
            # 5. Deposit / Transfer (Depósito / Transferencia)
            # Keywords: deposit, deposito, transfer, journal, contribution
            is_deposit = 'deposit' in action or 'depósito' in action or 'transfer' in action or 'journal' in action or 'contribution' in action
            
            # 6. Dividend Payout (Pago de Dividendo en Efectivo)
            # Keywords: dividend, payout, yield, interest (excluding reinvestment)
            is_div_payout = ('dividend' in action or 'dividendo' in action or 'yield' in action or 'interest' in action) and not is_drip
            
            # Logic
            row_cash_flow = 0.0
            
            # Split adjustment: shares from this transaction may have multiplied since
            # the purchase date due to forward splits (or reduced via reverse splits).
            _tx_date = row.get('Date', None)
            _sf = _cumul_split_factor(_tx_date, _splits_col)

            if is_buy:
                _adj_qty = abs(qty) * _sf
                pocket_investment += abs(amount)
                shares_owned += _adj_qty
                shares_owned_pocket += _adj_qty
                total_shares_bought += _adj_qty
                row_cash_flow = abs(amount)
                irr_flows_dated.append((_tx_date, -abs(amount)))
            elif is_deposit:
                is_internal = 'transfer' in action or 'journal' in action
                if is_internal:
                    # Internal transfers: signed qty so transfer-out(-) + transfer-in(+) = 0 net shares
                    # Only count cost basis when shares are arriving (qty > 0 = transfer-in)
                    _adj_qty = qty * _sf
                    shares_owned += _adj_qty
                    shares_owned_pocket += _adj_qty
                    if _adj_qty > 0:
                        total_shares_bought += _adj_qty
                        if amount != 0:
                            pocket_investment += abs(amount)
                            row_cash_flow = abs(amount)
                            # Capital que entra con costo: el IRR debe verlo igual que ROI/CAGR.
                            irr_flows_dated.append((_tx_date, -abs(amount)))
                else:
                    # External deposit / contribution: new money from pocket
                    _adj_qty = abs(qty) * _sf
                    pocket_investment += abs(amount)
                    shares_owned += _adj_qty
                    shares_owned_pocket += _adj_qty
                    total_shares_bought += _adj_qty
                    row_cash_flow = abs(amount)
                    # Capital que entra con costo: el IRR debe verlo igual que ROI/CAGR.
                    irr_flows_dated.append((_tx_date, -abs(amount)))

            elif is_drip:
                # Pattern 1: "Reinvest Shares" / "Comprar Acciones"
                if 'share' in action or 'acciones' in action:
                    _adj_qty = abs(qty) * _sf
                    shares_owned += _adj_qty
                    shares_owned_drip += _adj_qty
                    dividends_collected_drip += abs(amount)
                    dist_dated.append((_tx_date, abs(amount)))
                    _dy = _row_year(_tx_date)
                    if _dy is not None:
                        divs_by_year[_dy] += abs(amount)

                # Pattern 2: "Reinvest Dividend" — source row, skip to avoid double count
                elif 'dividend' in action or 'dividendo' in action:
                    pass

                # Pattern 3: Ambiguous fallback
                else:
                    _adj_qty = abs(qty) * _sf
                    shares_owned += _adj_qty
                    shares_owned_drip += _adj_qty
                    if amount < 0:
                        dividends_collected_drip += abs(amount)
                        dist_dated.append((_tx_date, abs(amount)))
                        _dy = _row_year(_tx_date)
                        if _dy is not None:
                            divs_by_year[_dy] += abs(amount)

            elif is_div_payout:
                # Cash dividend NOT reinvested. Use signed amount so IB correction
                # entries (negative) reduce the total instead of inflating it.
                if not is_drip:
                    dividends_collected_cash += amount
                    _dy = _row_year(_tx_date)
                    if _dy is not None:
                        divs_by_year[_dy] += amount
                    irr_flows_dated.append((_tx_date, amount))
                    if amount > 0:
                        dist_dated.append((_tx_date, amount))

            elif is_sell:
                _adj_qty = abs(qty) * _sf
                pocket_investment -= abs(amount)
                shares_owned -= _adj_qty
                shares_owned_pocket -= _adj_qty
                total_shares_sold += _adj_qty
                row_cash_flow = -abs(amount)
                irr_flows_dated.append((_tx_date, abs(amount)))
                # Guard: CSV missing prior history → sells exceed tracked buys → floor at 0
                if shares_owned < 0:
                    shares_owned = 0.0
                    history_incomplete = True
                if shares_owned_pocket < 0:
                    shares_owned_pocket = 0.0
                 
            # Special Handling: Splits in CSV
            # Ideally the CSV has the adjusted quantity. If we see a massive quantity change without amount, likely split.
            # But the SKILL says: "Balance Reset: Al detectar un 'Reverse Split' con una cantidad positiva en el CSV, trátalo como un Reinicio de Balance."
            if 'split' in action:
                if qty > 0:
                    if shares_owned > 0:
                        ratio = qty / shares_owned
                        shares_owned_pocket *= ratio
                        shares_owned_drip *= ratio
                    shares_owned = qty
                     
            cash_flows.append(row_cash_flow)
            
        ticker_df['Cash_Flow_In'] = cash_flows

        # --- Final High-Level Calculations ---
        market_value = shares_owned * current_price

        # ── Reconciliación desde la captura del broker ───────────────────
        # Si el broker (snapshot del usuario) reporta acciones/costo que difieren del CSV,
        # el CSV está incompleto (ventana de export ~3-4 años) -> confiar en el snapshot.
        # Se aplica ANTES de las métricas derivadas (IRR, ROI, CAGR, yield, ROC) para que se
        # recalculen solas con los valores corregidos. El daily_history/timeline NO se toca
        # (se construye aparte desde las transacciones) -> queda parcial a propósito.
        reconciled_from_snapshot = False
        reconciled_fields = []
        _prefer_19a_roc = False  # fondo con ROC e historial completo: conservar costo real, ROC vía 19a
        _ov = (position_overrides or {}).get(ticker)
        if _ov:
            _ov_sh = _ov.get('shares')
            _ov_co = _ov.get('cost_basis')
            try:
                if _ov_sh and abs(float(_ov_sh) - shares_owned) > max(0.02 * shares_owned, 0.01):
                    shares_owned = float(_ov_sh)
                    reconciled_from_snapshot = True
                    reconciled_fields.append('shares')
            except (TypeError, ValueError):
                pass
            try:
                if _ov_co:
                    _ov_co_f = float(_ov_co)
                    # Fondo con Retorno de Capital (publica avisos 19a) e historial COMPLETO: el bróker
                    # reporta una base ya reducida por el ROC, por debajo de lo que metiste (efectivo +
                    # reinvertido). Conservamos tu COSTO REAL del CSV —"Invertido", ROI y CAGR usan tu
                    # efectivo, no la base del bróker— y el ROC se estima con el % oficial 19a (la resta
                    # lo subestima al reinvertir). No es 'reconciliado': el historial está completo.
                    if (not history_incomplete
                            and _ov_co_f < pocket_investment + dividends_collected_drip
                            and str(ticker).upper() in load_roc_19a()):
                        _prefer_19a_roc = True
                    elif abs(_ov_co_f - pocket_investment) > max(0.02 * pocket_investment, 0.5):
                        pocket_investment = _ov_co_f
                        reconciled_from_snapshot = True
                        reconciled_fields.append('cost_basis')
            except (TypeError, ValueError):
                pass
            if reconciled_from_snapshot:
                market_value = shares_owned * current_price

        # ── Fase 7: IRR anualizado con timing real de flujos ─────────────
        irr_anual = None
        try:
            _irr_all = list(irr_flows_dated) + [(pd.Timestamp.today(), market_value)]
            _buckets  = defaultdict(float)
            for _dt, _amt in _irr_all:
                _ts = pd.Timestamp(_dt)
                _buckets[(_ts.year, _ts.month)] += _amt
            _min_k = min(_buckets.keys())
            _max_k = max(_buckets.keys())
            _keys, _y, _m = [], _min_k[0], _min_k[1]
            while (_y, _m) <= _max_k:
                _keys.append((_y, _m))
                _m += 1
                if _m > 12:
                    _m, _y = 1, _y + 1
            _cf_list = [_buckets.get(k, 0.0) for k in _keys]
            _monthly  = npf.irr(_cf_list)
            if _monthly is not None and not np.isnan(_monthly) and not np.isinf(_monthly) and _monthly > -1:
                irr_anual = round(((1 + _monthly) ** 12 - 1) * 100, 2)
        except Exception:
            irr_anual = None

        # ── Fase 2: Validación cruzada precio CSV vs yfinance ────────────
        price_discrepancies = []
        try:
            _close = market_data['Close'].copy()
            _cidx  = pd.to_datetime(_close.index).tz_localize(None) if _close.index.tzinfo else pd.to_datetime(_close.index)
            _close.index = _cidx
            _buy_rows = ticker_df[ticker_df['Action'].str.lower().str.contains(
                r'buy|bought|compra', na=False, regex=True)]
            for _, _br in _buy_rows.iterrows():
                _bq  = abs(safe_float(_br.get('Quantity', 0)))
                _bam = abs(safe_float(_br.get('Amount',   0)))
                _bp  = safe_float(_br.get('Price', 0)) or (_bam / _bq if _bq > 0 else 0)
                if _bp <= 0:
                    continue
                _bdt   = pd.Timestamp(_br['Date']).tz_localize(None)
                _diffs = abs(_close.index - _bdt)
                _ni    = _diffs.argmin()
                if _diffs[_ni].days > 5:
                    continue
                _yp = float(_close.iloc[_ni])
                if _yp <= 0:
                    continue
                _ratio = _bp / _yp
                if _ratio > 1.15 or _ratio < 0.85:
                    # Suprimir si el ratio coincide con un split ya detectado (Fase 1 ya lo maneja)
                    _already_known = any(
                        abs(_ratio - _sp['ratio']) < 0.2 or abs(_ratio - 1.0 / _sp['ratio']) < 0.2
                        for _sp in splits_detected
                    )
                    if not _already_known:
                        price_discrepancies.append({
                            "date":      str(_br['Date'])[:10],
                            "csv_price": round(_bp,    2),
                            "yf_price":  round(_yp,    2),
                            "ratio":     round(_ratio,  2),
                        })
        except Exception:
            price_discrepancies = []
        
        # Total Return Formula from Skill:
        # Total Return = (Valor Mercado Actual + Cash Cobrado) - Inversión Bolsillo
        # NOTE: Total Return includes the current VALUE of the DRIP shares (in market_value) PLUS the Cash collected.
        # It does NOT include the historical `dividends_collected_drip` value directly, as that money is now inside `market_value`.
        
        gross_value = market_value + dividends_collected_cash
        net_profit = gross_value - pocket_investment
        roi = (net_profit / pocket_investment * 100) if pocket_investment != 0 else 0
        
        # Total Dividends (Informational)
        total_dividends = dividends_collected_cash + dividends_collected_drip
        
        # --- Calculate Daily History (For Chart) ---
        # 1. Resample transactions to daily to handle multiple trades per day
        # Only count Quantity from buy/sell/split/DRIP rows — cash dividend rows in Schwab CSVs
        # sometimes carry a non-zero Quantity that would inflate the running share count.
        # 'split' is excluded: the split loop below (Stock Splits column from yfinance) is
        # the authoritative handler. If the broker CSV also records splits as share-adding rows,
        # including 'split' here would double-count (CSV shares + loop multiplication).
        qty_rows = ticker_df[ticker_df['Action'].str.lower().str.contains(
            r'buy|bought|compra|sell|sold|venta|reinvest|reinversión|drip|deposit|transfer|journal|contribution',
            na=False, regex=True
        )].copy()
        # Schwab (y algunos otros brokers) exporta Quantity positiva para ventas.
        # Negamos explícitamente las filas de venta para que el cumsum reste shares correctamente.
        sell_mask = qty_rows['Action'].str.lower().str.contains(r'sell|sold|venta', na=False, regex=True)
        qty_rows.loc[sell_mask, 'Quantity'] = -qty_rows.loc[sell_mask, 'Quantity'].abs()
        qty_by_date = qty_rows.groupby('Date')['Quantity'].sum()
        daily_activity = ticker_df.groupby('Date')[['Amount', 'Cash_Flow_In']].sum()
        daily_activity['Quantity'] = qty_by_date.reindex(daily_activity.index).fillna(0)
        
        # 2. Reindex to market data (daily)
        daily_history = daily_activity.reindex(market_data.index).fillna(0)
        
        # 3. Calculate Cumulative Shares (Iterative Fix for Splits)
        # The simple cumsum() fails when price is adjusted but shares aren't.
        # We must apply the split factor to the *accumulated* shares.
        
        # Ensure we have split data from market_data (it comes from yf.download(actions=True))
        if 'Stock Splits' in market_data.columns:
             splits = market_data['Stock Splits'].reindex(daily_history.index).fillna(0)
        else:
             splits = pd.Series(0, index=daily_history.index)

        running_shares = 0.0
        shares_series = []

        for date in daily_history.index:
            split_val = splits.loc[date]
            if split_val != 0 and split_val > 0:
                loc = daily_history.index.get_loc(date)
                if loc > 0:
                    prev_date = daily_history.index[loc - 1]
                    try:
                        price_today = float(market_data['Close'].loc[date])
                        price_prev  = float(market_data['Close'].loc[prev_date])
                        actual_ratio   = price_today / price_prev if price_prev > 0 else 1.0
                        expected_ratio = 1.0 / float(split_val)
                        # yfinance sometimes returns already-adjusted prices even with
                        # auto_adjust=False (confirmed for SCHB 3-for-1, Oct 2024).
                        # When prices didn't drop by ~1/split_val, they're pre-adjusted:
                        # retroactively scale all past share counts so the chart is smooth.
                        if abs(actual_ratio - expected_ratio) / expected_ratio > 0.15:
                            shares_series = [s * split_val for s in shares_series]
                        running_shares *= split_val
                    except Exception:
                        running_shares *= split_val
                else:
                    running_shares *= split_val

            net_qty = daily_history.loc[date, 'Quantity']
            running_shares += net_qty
            if running_shares < 0:
                running_shares = 0.0
            shares_series.append(running_shares)

        daily_history['Shares Held'] = shares_series
        
        # 4. Calculate Values
        daily_history['Price'] = market_data['Close']
        daily_history['Market Value'] = daily_history['Shares Held'] * daily_history['Price']
        
        # 5. Calculate Cumulative Investment (Cost Basis) over time
        # Investment = Sum of (Buys - Sells). 
        # Using explicit Cash_Flow_In which avoids CSV sign parsing issues
        daily_history['Daily Invested'] = daily_activity['Cash_Flow_In'].reindex(market_data.index).fillna(0)
        daily_history['Invested Capital'] = daily_history['Daily Invested'].cumsum()

        # 5b. Flujo por TRANSFERENCIA de acciones sin efectivo (Internal Transfer / Journaled
        # Shares / ACATS): valor = cantidad × cierre del día. Una transferencia entra a $0 de
        # efectivo, así que sin esto ni el benchmark VOO ni el TWR la ven como capital → el chart
        # haría ver que la posición "aplasta" al S&P (falso). 'Flujo Efectivo' = efectivo +
        # transferencias se usa en AMBOS (benchmark y TWR). NO se toca Invested Capital (ROI).
        # Caso real: SCHB +18.9 acc. el 2024-05-13 (benchmark pasaba a $0).
        transfer_flow = pd.Series(0.0, index=daily_history.index)
        try:
            _xfer = ticker_df[ticker_df['Action'].str.lower().str.contains(
                'transfer|journal|acats|in kind|en especie', na=False)]
            for _, _xr in _xfer.iterrows():
                _xd = pd.Timestamp(_xr['Date']).normalize()
                _xq = pd.to_numeric(_xr.get('Quantity'), errors='coerce')
                _xa = _clean_money(_xr.get('Amount', 0))
                if _xd in transfer_flow.index and pd.notna(_xq) and _xq != 0 and (pd.isna(_xa) or abs(_xa) < 0.01):
                    _xpx = float(daily_history['Price'].get(_xd, 0) or 0)
                    if _xpx > 0:
                        transfer_flow.loc[_xd] += float(_xq) * _xpx
        except Exception:
            pass
        daily_history['Transfer Flow'] = transfer_flow
        daily_history['Flujo Efectivo'] = daily_history['Daily Invested'] + daily_history['Transfer Flow']

        # 6. Calculate User Profit (Real)
        # We need to track Cumulative Cash Dividends to add to Market Value
        # Identify Cash Dividend rows in original DF.
        # Schwab records DRIP as two rows: "Cash Dividend" + "Reinvestment".
        # The "Cash Dividend" row must be excluded when a reinvestment happened on
        # the same date — otherwise it is double-counted (once as shares in Market
        # Value, once as cash in Cumulative Cash Div).
        drip_dates = set(
            ticker_df[ticker_df['Action'].str.lower().str.contains(
                r'reinvest|reinversión|drip', na=False, regex=True
            )]['Date'].tolist()
        )
        cash_div_rows = ticker_df[
            (ticker_df['Action'].str.lower().str.contains('dividend|dividendo|yield|interest', na=False)) &
            (~ticker_df['Action'].str.lower().str.contains('reinvest|reinversión|drip', na=False)) &
            (~ticker_df['Date'].isin(drip_dates))
        ]
        
        # Resample cash divs to daily
        if not cash_div_rows.empty:
            daily_cash_divs = cash_div_rows.groupby('Date')['Amount'].sum().abs()
            daily_history['Daily Cash Div'] = daily_cash_divs.reindex(market_data.index).fillna(0)
        else:
            daily_history['Daily Cash Div'] = 0.0
            
        daily_history['Cumulative Cash Div'] = daily_history['Daily Cash Div'].cumsum()
        
        # User Profit = (Market Value + Cumulative Cash Received) - Invested Capital
        daily_history['User Profit'] = (daily_history['Market Value'] + daily_history['Cumulative Cash Div']) - daily_history['Invested Capital']

        # 7. Calculate Time-Weighted Return (TWR) & SPY Benchmark
        # ---------------------------------------------------------
        
        # A. SPY/VOO Benchmark Simulation
        try:
            benchmark_ticker = 'VOO'
            session = None
            try:
                session = get_session()
            except:
                pass

            # auto_adjust=False mantiene precios históricos reales (no ajustados por dividendos).
            # actions=True trae columna Dividends para reinvertirlos en la simulación.
            spy_data = yf.download(benchmark_ticker, start=first_date, progress=False,
                                   auto_adjust=False, actions=True, session=session)

            if isinstance(spy_data.columns, pd.MultiIndex):
                spy_data.columns = spy_data.columns.get_level_values(0)

            if getattr(spy_data.index, "tz", None) is not None:
                spy_data.index = spy_data.index.tz_localize(None)

            spy_prices = spy_data['Close'].reindex(daily_history.index).ffill()
            voo_divs   = (spy_data['Dividends'].reindex(daily_history.index).fillna(0)
                          if 'Dividends' in spy_data.columns
                          else pd.Series(0.0, index=daily_history.index))

            daily_history['VOO Price'] = spy_prices
            safe_voo_price = daily_history['VOO Price'].replace(0, pd.NA).ffill().bfill()

            # Simulación con reinversión de dividendos de VOO (Total Return apples-to-apples).
            # Usa 'Flujo Efectivo' (efectivo + transferencias de acciones) para que el benchmark
            # refleje el capital que realmente entró, incluido el que llegó por transferencia.
            voo_shares_running = 0.0
            voo_shares_series  = []
            daily_invested_s   = daily_history['Flujo Efectivo']

            for date in daily_history.index:
                vp = float(safe_voo_price.loc[date]) if not pd.isna(safe_voo_price.loc[date]) else 0.0
                if vp > 0:
                    voo_shares_running += float(daily_invested_s.loc[date]) / vp
                    div = float(voo_divs.loc[date])
                    if div > 0 and voo_shares_running > 0:
                        voo_shares_running += (div * voo_shares_running) / vp
                voo_shares_running = max(voo_shares_running, 0.0)
                voo_shares_series.append(voo_shares_running)

            daily_history['VOO Shares Held'] = voo_shares_series
            daily_history['SPY Profit'] = daily_history['VOO Shares Held'] * daily_history['VOO Price']
            # Guardado para beta/alpha: retorno TOTAL de VOO (precio + dividendos), sin flujos.
            daily_history['VOO Div'] = voo_divs

        except Exception as e:
            print(f"Error calculating benchmark (VOO): {e}")
            daily_history['SPY Profit'] = 0.0

        # ── Fase 8: Benchmark con timing real (extraído de SPY Profit ya calculado) ─
        try:
            _spy_final    = float(daily_history['SPY Profit'].replace(0, np.nan).dropna().iloc[-1])
            benchmark_value = _spy_final
            # El benchmark invierte 'Flujo Efectivo' (efectivo + valor de transferencias), así que
            # su ROI debe medirse sobre ESA misma base, no sobre pocket_investment (que excluye
            # transferencias) — de lo contrario numerador y denominador hablan de capitales distintos.
            _bench_base = float(daily_history['Flujo Efectivo'][daily_history['Flujo Efectivo'] > 0].sum()) \
                if 'Flujo Efectivo' in daily_history.columns else pocket_investment
            if _bench_base <= 0:
                _bench_base = pocket_investment
            benchmark_roi   = (_spy_final - _bench_base) / _bench_base * 100 if _bench_base > 0 else None
        except Exception:
            benchmark_value = None
            benchmark_roi   = None

        # Also compute User Total Value for graphing
        daily_history['User Total Value'] = daily_history['Market Value'] + daily_history['Cumulative Cash Div']

        # B. User Portfolio TWR (Time-Weighted Return)
        # Formula: Unit Return r_t = (EndVal_t - (StartVal_t + NetFlow_t)) / (StartVal_t + NetFlow_t)
        # But commonly: r_t = (EndVal_t - EndVal_{t-1} - NetFlow_t) / (EndVal_{t-1} + 0.5 * NetFlow_t) 
        # (Modified Dietz) ... OR True TWR if we have exact daily vals.
        
        # We have:
        # EndVal_t = 'Market Value' + 'Daily Cash Div' (Total value at end of day, assuming divs collected)
        # StartVal_t = EndVal_{t-1}
        # NetFlow_t = 'Daily Invested' (Positive for deposits vs Negative for withdrawals? 
        #              Wait, 'Daily Invested' was calc as: Amount * -1. 
        #              So Buy (Neg Amount) -> Pos Invested (Inflow). Correct.)
        
        # El flujo por transferencia de acciones sin efectivo ya se computó arriba
        # ('Transfer Flow' / 'Flujo Efectivo') y lo usa también el benchmark VOO.

        twr_series = []
        cum_twr = 1.0 # Start at 1.0 (100%)

        prev_total_val = 0.0

        for date, row in daily_history.iterrows():
            # End Value of standard assets
            market_val = row['Market Value']
            
            # Add dividends received today to the "End Value" of the period
            cash_div = row['Daily Cash Div']
            
            # Total Value Owner Has at End of Day
            end_val = market_val + cash_div
            
            # Net Flow (New money coming in/out) — efectivo + transferencias de acciones sin efectivo
            net_flow = row['Flujo Efectivo']
            
            # Start Value is yesterday's end value
            start_val = prev_total_val
            
            # Calculate Period Return
            # We use "End of Day" flow assumption for subsequent deposits to avoid dilution.
            # If we add $1000 and price jumps 10%, we assume the $1000 didn't catch the jump (conservative/safe).
            # If start_val is 0 (First day), we must assume Start of Day.
            
            if start_val > 0.0001:
                # End of Day Flow Formula: r = (End - Flow - Start) / Start
                # Simplified: (End - Flow) / Start - 1
                period_return = ((end_val - net_flow) / start_val) - 1
            elif net_flow > 0.0001:
                # First Day (Start of Day Flow)
                # r = (End - Start - Flow) / (Start + Flow)
                # Since Start=0: r = (End - Flow) / Flow
                # Simplified: End / Flow - 1
                period_return = (end_val / net_flow) - 1
            else:
                period_return = 0.0
                
            # Chain it
            cum_twr *= (1 + period_return)
            
            # Store Percentage (e.g. 1.05 -> 5.0)
            twr_series.append((cum_twr - 1) * 100)
            
            # Update for next day. 
            # Note: For TWR, the "Start Value" for tomorrow excludes likely withdrawals? 
            # But here `end_val` included Cash Div. 
            # If we pocket the cash, it's gone.
            # So `prev_total_val` should be just the `market_val` (assets remaining).
            prev_total_val = market_val 
            
        daily_history['User Return %'] = twr_series

        # ============================================================
        # MÉTRICAS CUANTITATIVAS AJUSTADAS POR RIESGO
        # Generadas por quant-analyst — inserción no destructiva
        # ============================================================

        # 1. Retornos diarios desde la serie TWR acumulada (evita contaminación por flujos de capital)
        # User Return % es TWR acumulado en %. Convertimos a factor y derivamos retornos diarios.
        twr_factor = (1 + daily_history['User Return %'] / 100).replace(0, np.nan)
        daily_returns_q = twr_factor.pct_change().dropna()

        # Beta/alpha contra el retorno TOTAL de VOO (precio + dividendos reinvertidos), NO contra
        # 'SPY Profit' (valor de la cartera VOO simulada, que salta cada vez que entra capital y
        # mete "retornos" falsos en el benchmark). Fallback a SPY Profit si no hay serie de precio.
        if ('VOO Price' in daily_history.columns
                and daily_history['VOO Price'].replace(0, np.nan).notna().sum() > 2):
            _vp = daily_history['VOO Price'].replace(0, np.nan)
            _vd = (daily_history['VOO Div'] if 'VOO Div' in daily_history.columns
                   else pd.Series(0.0, index=daily_history.index)).fillna(0.0)
            spy_daily_returns_q = ((_vp + _vd) / _vp.shift(1) - 1).dropna()
        else:
            spy_vals = daily_history['SPY Profit'].replace(0, np.nan)
            spy_daily_returns_q = spy_vals.pct_change(fill_method=None).dropna()

        # 1b. Winsorizar retornos diarios (robustez ante saltos que NO son rendimientos):
        # transferencias de acciones a $0 de efectivo (Internal Transfer / Journaled Shares),
        # desfases de split o ticks malos de la API crean un "retorno" diario espurio de miles
        # de % que disparaba la volatilidad/Sharpe/Sortino/beta. Acotar al rango [1%, 99%] de la
        # propia serie elimina esos outliers sin tocar la reconstrucción de P&L/ROI/equity curve.
        # (Caso real: SCHB transfer 18.9 acc. el 2024-05-13 → MV $16→$1164 → vol falsa de 3443%.)
        daily_returns_q = _winsorize_returns(daily_returns_q)
        spy_daily_returns_q = _winsorize_returns(spy_daily_returns_q)

        # 2. Volatilidad anualizada
        if len(daily_returns_q) >= 2:
            volatilidad_anualizada = float(daily_returns_q.std() * np.sqrt(252) * 100)
        else:
            volatilidad_anualizada = None

        # 3. Sharpe Ratio (Rf = 5% anual)
        RF_ANUAL = 0.05
        rf_diario = RF_ANUAL / 252
        if len(daily_returns_q) >= 2 and daily_returns_q.std() > 1e-9:
            exceso = daily_returns_q.mean() - rf_diario
            sharpe_ratio = float((exceso / daily_returns_q.std()) * np.sqrt(252))
        else:
            sharpe_ratio = None

        # 4. Sortino Ratio — downside deviation estándar (no std de solo los negativos)
        sortino_ratio = _sortino_ratio(daily_returns_q, rf_diario)

        # 5. Maximum Drawdown
        valor_port = daily_history['User Total Value'].replace(0, np.nan).dropna()
        if len(valor_port) >= 2:
            peak_acum = valor_port.cummax()
            drawdown_serie = (valor_port - peak_acum) / peak_acum * 100
            max_drawdown = float(drawdown_serie.min())
            daily_history['Drawdown %'] = drawdown_serie.reindex(daily_history.index).fillna(np.nan)
        else:
            max_drawdown = None
            daily_history['Drawdown %'] = np.nan

        # 6. Calmar Ratio — CAGR compuesto desde los retornos diarios YA winsorizados (no desde el
        # TWR acumulado crudo, que puede estar corrupto por transferencias / costo incompleto).
        if max_drawdown is not None and max_drawdown < -1e-9 and len(daily_returns_q) >= 2:
            cum_twr_final = float((1 + daily_returns_q).prod())
            anios_twr = len(daily_returns_q) / 252
            if anios_twr > 0 and cum_twr_final > 0:
                cagr_twr = ((cum_twr_final ** (1 / anios_twr)) - 1) * 100
                calmar_ratio = float(cagr_twr / abs(max_drawdown))
            else:
                calmar_ratio = None
        else:
            calmar_ratio = None

        # 7. Beta vs VOO
        retornos_alineados = pd.DataFrame({
            'portfolio': daily_returns_q,
            'spy': spy_daily_returns_q
        }).dropna()
        if len(retornos_alineados) >= 10 and retornos_alineados['spy'].var() > 1e-12:
            cov_mat = retornos_alineados.cov()
            beta = float(cov_mat.loc['portfolio', 'spy'] / retornos_alineados['spy'].var())
        else:
            beta = None

        # 8. Alpha de Jensen
        if beta is not None and len(retornos_alineados) >= 10:
            rp_anual = float(retornos_alineados['portfolio'].mean() * 252 * 100)
            rm_anual = float(retornos_alineados['spy'].mean() * 252 * 100)
            alpha = float(rp_anual - (RF_ANUAL * 100 + beta * (rm_anual - RF_ANUAL * 100)))
        else:
            alpha = None

        # --- v2.0: Classify ticker mode ---
        ticker_mode = classify_tickers([ticker]).get(ticker, 'mode_b')

        # --- v2.0: Monthly income & yield on cost (Mode A and Mode B) ---
        # Mode A: all dividend/reinvest rows (YieldMax pays monthly)
        # Mode B: cash dividends only (VTI, SCHB, SCHD pay quarterly cash divs)
        monthly_income = pd.Series(dtype=float)
        yield_on_cost = 0.0
        if ticker_mode in ('mode_a', 'mode_b'):
            try:
                if ticker_mode == 'mode_a':
                    # Fuente única: _dividend_events cuenta 'Reinvest Dividend' (bruto) y
                    # omite 'Reinvest Shares' (compra neta post-tax). Evita el neteo del DRIP
                    # de Schwab que subestimaba los meses con reinversión.
                    div_events = _dividend_events(ticker_df)
                    if not div_events.empty:
                        monthly_income = div_events.groupby(
                            div_events.index.to_period('M').astype(str)
                        ).sum()
                else:
                    # mode_b: cash dividends only (exclude reinvest rows to avoid double-count)
                    div_rows = ticker_df[
                        ticker_df['Action'].str.lower().str.contains('dividend|dividendo|yield', na=False) &
                        ~ticker_df['Action'].str.lower().str.contains('reinvest|reinversión|drip', na=False)
                    ].copy()
                    if not div_rows.empty:
                        div_rows['Month'] = div_rows['Date'].dt.to_period('M').astype(str)
                        monthly_income = div_rows.groupby('Month')['Amount'].sum().abs()
                years = max((ticker_df['Date'].max() - ticker_df['Date'].min()).days / 365.25, 0.01)
                ann_divs = total_dividends / years
                yield_on_cost = (ann_divs / pocket_investment * 100) if pocket_investment > 0 else 0
            except Exception as e:
                print(f"Income calc error for {ticker}: {e}")

        # --- v2.0: Mode B — growth metrics ---
        shares_bought = total_shares_bought
        shares_sold   = total_shares_sold
        cagr = None
        try:
            years_held = max((ticker_df['Date'].max() - ticker_df['Date'].min()).days / 365.25, 0.01)
            if pocket_investment > 0 and market_value > 0:
                cagr = ((market_value / pocket_investment) ** (1 / years_held) - 1) * 100
        except Exception:
            pass

        # ── Fase 6: Cobertura del CSV vs historial completo disponible ───
        csv_coverage_pct  = None
        csv_inception_yf  = None
        try:
            _fi = yf.Ticker(ticker).fast_info
            _ep = getattr(_fi, 'first_trade_date', None)
            if _ep:
                _inc = pd.Timestamp(_ep).tz_localize(None)
                _tot = (pd.Timestamp.today() - _inc).days
                _cov = (pd.Timestamp.today() - pd.Timestamp(first_date).tz_localize(None)).days
                csv_coverage_pct = min(round(_cov / _tot * 100, 1), 100.0) if _tot > 0 else 100.0
                csv_inception_yf = str(_inc)[:10]
        except Exception:
            pass

        # ── Fase 3: Acciones corporativas en el período ──────────────────
        corporate_actions = []
        try:
            if 'Stock Splits' in market_data.columns:
                _sp = market_data['Stock Splits'][market_data['Stock Splits'] > 0]
                for _sd, _sr in _sp.items():
                    corporate_actions.append({
                        "type": "Split" if _sr > 1 else "Reverse Split",
                        "date": str(_sd)[:10], "ratio": float(_sr)
                    })
            if 'Dividends' in market_data.columns:
                _divs = market_data['Dividends'][market_data['Dividends'] > 0]
                if not _divs.empty:
                    _avg = _divs.mean()
                    for _dd, _da in _divs[_divs > _avg * 3].items():
                        corporate_actions.append({
                            "type": "Dividendo especial",
                            "date": str(_dd)[:10], "amount": round(float(_da), 4)
                        })
        except Exception:
            pass

        # ── ROC: Return of Capital ────────────────────────────────────────
        # El ROC reduce el costo base dólar a dólar; el DRIP (reinversión) lo SUBE dólar a dólar.
        # Por eso el dinero total que entró a comprar acciones = cash de tu bolsillo + reinvertido.
        #   ROC = (invertido + reinvertido) − costo base del bróker.
        # roc_percent = qué parte de TUS DISTRIBUCIONES fue ROC (denominador = total_dividends).
        _ib_basis = None
        _roc_accum = None
        _roc_pct = None
        _roc_source = None
        _basis_in = pocket_investment + dividends_collected_drip
        # Si la reconciliación desde el snapshot del broker sobreescribió pocket_investment con el
        # costo base del broker (reconciled_fields incluye 'cost_basis'), ese MISMO número alimenta
        # ib_cost_basis_map. Entonces (pocket+drip) − ib_basis se cancela y el ROC 'broker' colapsa a
        # ~0 (= solo el drip), justo en YieldMax reconciliados donde el ROC es grande. En ese caso el
        # método broker no puede derivar ROC: no tenemos el costo ORIGINAL, solo el actual ya reducido
        # por el ROC. Mostramos el costo del broker igual, pero estimamos el ROC con los 19a (abajo).
        _cost_reconciled = 'cost_basis' in (reconciled_fields or [])
        if ib_cost_basis_map:
            _raw_basis = ib_cost_basis_map.get(ticker)
            if _raw_basis is not None:
                try:
                    _ib_basis = float(str(_raw_basis).replace(',', '').replace('$', '').strip())
                    if _basis_in > 0 and _ib_basis >= 0 and not _cost_reconciled and not _prefer_19a_roc:
                        _roc_accum = round(_basis_in - _ib_basis, 2)
                        _roc_pct   = round(_roc_accum / total_dividends * 100, 2) if total_dividends > 0 else None
                        _roc_source = 'broker'
                except (ValueError, TypeError):
                    pass

        # Respaldo: si no hay costo base del bróker, estimar el ROC con el % que el fondo
        # publica en sus avisos 19a (ver knowledge/roc_19a.yaml). Empate por fecha si hay
        # historial por distribución; si no, % ponderado del fondo.
        if _roc_accum is None and total_dividends > 0:
            _est_roc, _est_pct = _estimate_roc_from_19a(ticker, dist_dated)
            if _est_roc is not None:
                _roc_accum = round(_est_roc, 2)
                _roc_pct   = round(_est_pct, 2) if _est_pct is not None else None
                _roc_source = '19a'

        # ── Forward vs realized yield + retención real (Mejoras 3 y 4) ────
        _fy = forward_realized_yield(ticker_df, market_value, today=_snapshot_date)
        _withheld = withheld_tax_total(ticker_df)
        _withheld_by_year = withheld_tax_total_by_year(ticker_df)
        _refund_obs_by_year = observed_tax_refund_by_year(ticker_df)
        _gross_by_year = {
            _y: round(divs_by_year.get(_y, 0.0) + _withheld_by_year.get(_y, 0.0), 2)
            for _y in (set(divs_by_year) | set(_withheld_by_year))
        }
        _cadence_change = detect_cadence_change(ticker_df)

        # CAGR de precio puro (no contaminado por DRIP/aportes): la erosión/apreciación
        # observada del NAV. Se calcula sobre toda la ventana Y sobre los últimos 12 meses;
        # la proyección prefiere el reciente para no extrapolar una caída vieja como eterna.
        _price_cagr = None
        _price_cagr_recent = None
        _price_history_days = None     # cuántos días de NAV observamos (guarda anti falso-veredicto)
        _close = None
        _fund_divs = None
        try:
            _close = market_data['Close'] if 'Close' in market_data.columns else None
            _fund_divs = market_data['Dividends'] if 'Dividends' in market_data.columns else None
            if _close is not None:
                _price_cagr = _annualized_cagr(_close)
                _price_cagr_recent = _annualized_cagr(_close, days=365)
                _cc = _close.dropna()
                if len(_cc) >= 2:
                    _price_history_days = int((_cc.index[-1] - _cc.index[0]).days)
        except Exception:
            pass

        # ── Módulo 1: exposición al subyacente (solo YieldMax) ────────────
        # MSTY sigue a MSTR, TSLY a TSLA, etc. Traemos el retorno reciente del subyacente
        # para contrastar la asimetría: el fondo captura casi toda la caída pero capa la subida.
        _underlying_tk = None
        _underlying_cagr_recent = None
        _underlying_hold_value = None
        _underlying_close = None
        _underlying_divs = None
        try:
            _info_u = load_instruments().get(str(ticker).upper(), {})
            _is_ym = ticker_mode == 'mode_a' or (_info_u.get('type') or '').lower() == 'yieldmax'
            _u = _info_u.get('underlying')
            if _is_ym and _u and str(_u).upper() not in ('N/A', 'NA', ''):
                _underlying_tk = str(_u).upper()
                _udf, _uerr = fetch_market_data(_underlying_tk, first_date)
                if _udf is not None and not _udf.empty and 'Close' in _udf.columns:
                    _underlying_cagr_recent = _annualized_cagr(_udf['Close'], days=365)
                    _underlying_close = _udf['Close']
                    _underlying_divs = _udf['Dividends'] if 'Dividends' in _udf.columns else None
                    # #1: ¿y si hubieras tenido el subyacente directo? (misma plata y timing)
                    _up = _udf['Close'].reindex(daily_history.index).ffill()
                    _ud = (_udf['Dividends'].reindex(daily_history.index).fillna(0)
                           if 'Dividends' in _udf.columns else None)
                    _underlying_hold_value = round(
                        _simulate_hold_value(_up, _ud, daily_history['Flujo Efectivo']), 2)
        except Exception:
            pass

        results[ticker] = {
            # Métricas existentes (sin cambios)
            "current_price": current_price,
            "shares_owned": shares_owned,
            "shares_owned_pocket": shares_owned_pocket,
            "shares_owned_drip": shares_owned_drip,
            "pocket_investment": pocket_investment,
            "market_value": market_value,
            "dividends_collected_cash": dividends_collected_cash,
            "dividends_collected_drip": dividends_collected_drip,
            "total_dividends": total_dividends,
            "net_profit": net_profit,
            "roi_percent": roi,
            "history": ticker_df,
            "daily_trend": daily_history[['User Profit', 'SPY Profit', 'User Return %', 'Invested Capital', 'Market Value', 'User Total Value', 'Drawdown %']],
            # Métricas cuantitativas
            "volatilidad_anualizada": volatilidad_anualizada,
            "sharpe_ratio":           sharpe_ratio,
            "sortino_ratio":          sortino_ratio,
            "max_drawdown":           max_drawdown,
            "calmar_ratio":           calmar_ratio,
            "beta_vs_voo":            beta,
            "alpha_anualizado":       alpha,
            # v2.0 — clasificación y métricas por modo
            "ticker_mode":     ticker_mode,
            "monthly_income":  monthly_income,
            "yield_on_cost":   yield_on_cost,
            "shares_bought":      shares_bought,
            "shares_sold":        shares_sold,
            "cagr":               cagr,
            "history_incomplete": history_incomplete,
            "splits_detected":    splits_detected,
            # Fases 2, 3, 6, 7, 8
            "irr_anual":           irr_anual,
            "price_discrepancies": price_discrepancies,
            "benchmark_value":     benchmark_value,
            "benchmark_roi":       benchmark_roi,
            "csv_coverage_pct":    csv_coverage_pct,
            "csv_inception_yf":    csv_inception_yf,
            "corporate_actions":   corporate_actions,
            # ROC
            "ib_cost_basis":       _ib_basis,
            "roc_accumulated":     _roc_accum,
            "roc_percent":         _roc_pct,
            "roc_source":          _roc_source,
            # Reconciliación desde la captura del broker
            "reconciled_from_snapshot": reconciled_from_snapshot,
            "reconciled_fields":        reconciled_fields,
            # v3.0 — yield doble (realizado vs forward) y retención real del CSV
            "forward_yield":     _fy['forward_yield'],
            "realized_yield":    _fy['realized_yield'],
            "advertised_yield":  advertised_distribution_rate(ticker),
            "payments_per_year": _fy['payments_per_year'],
            "last_payment":      _fy['last_payment'],
            "ttm_income":        _fy['ttm_income'],
            "forward_stale":     _fy.get('stale', False),
            "withheld_tax_total": _withheld,
            "dividends_gross_by_year": _gross_by_year,
            "withheld_by_year": dict(_withheld_by_year),
            "tax_refund_observed_by_year": dict(_refund_obs_by_year),
            "price_cagr":        _price_cagr,
            "price_cagr_recent": _price_cagr_recent,
            "price_history_days": _price_history_days,
            "cadence_change":    _cadence_change,
            "underlying_ticker": _underlying_tk,
            "underlying_cagr_recent": _underlying_cagr_recent,
            "underlying_hold_value": _underlying_hold_value,
            "fund_close_series": _close,
            "underlying_close_series": _underlying_close,
            "fund_dividends_series": _fund_divs,
            "underlying_dividends_series": _underlying_divs,
        }
        
    return results

def get_params_from_csv(df):
    """
    Extracts default params for a simulation based on the CSV.
    E.g. finds the earliest date and the most common ticker.
    """
    if df.empty:
        return None, None
        
    tickers = df['Ticker'].unique()
    main_ticker = tickers[0] if len(tickers) > 0 else 'TSLY'
    min_date = df['Date'].min().date()
    
    return main_ticker, min_date

def simulate_strategy(ticker, start_date, initial_investment):
    """
    Simulates a perfect DRIP vs No-DRIP strategy for comparison.
    """
    market_data, error_msg = fetch_market_data(ticker, start_date)
    if market_data.empty:
        return None, error_msg

    # Filter data to start from start_date
    market_data = market_data[market_data.index >= pd.to_datetime(start_date)]
    if market_data.empty:
        return None, "No data found after start date"

    # Initial Setup
    start_price = market_data['Close'].iloc[0]
    initial_shares = initial_investment / start_price
    
    # Trackers
    drip_shares = initial_shares
    nodrip_shares = initial_shares
    nodrip_cash = 0.0
    
    history = []
    
    for date, row in market_data.iterrows():
        price = row['Close']
        div = row['Dividends'] if 'Dividends' in row else 0.0

        # NO se ajustan acciones por split: fetch_market_data ya entrega el Close
        # ajustado por split (continuo), asi que multiplicar las acciones por el
        # ratio del split contaria doble (bug confirmado con XLK 2:1 y TSLY/MSTY 1:5).

        # --- Handle Dividends ---
        if div > 0:
            # DRIP: Buy more shares
            new_shares = (div * drip_shares) / price
            drip_shares += new_shares
            
            # No-DRIP: Keep cash
            cash_payout = (div * nodrip_shares)
            nodrip_cash += cash_payout
            
        # --- Daily Valuation ---
        drip_value = drip_shares * price
        nodrip_value_assets = nodrip_shares * price
        nodrip_total_wealth = nodrip_value_assets + nodrip_cash
        
        history.append({
            'Date': date,
            'DRIP Wealth': drip_value,
            'No-DRIP Wealth': nodrip_total_wealth,
            'No-DRIP Cash': nodrip_cash,
            'Price': price
        })
        
    results_df = pd.DataFrame(history).set_index('Date')
    
    final_stats = {
        'initial_investment': initial_investment,
        'drip_final_value': results_df['DRIP Wealth'].iloc[-1],
        'nodrip_final_value': results_df['No-DRIP Wealth'].iloc[-1],
        'drip_roi_percent': (results_df['DRIP Wealth'].iloc[-1] - initial_investment) / initial_investment * 100,
        'nodrip_roi_percent': (results_df['No-DRIP Wealth'].iloc[-1] - initial_investment) / initial_investment * 100,
        'history': results_df
    }

    return final_stats, None


def _normalize_series_index(s):
    idx = pd.DatetimeIndex(s.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    s = s.copy()
    s.index = idx.normalize()
    s.index.name = 'Date'
    return s


def simulate_portfolio_comparison(dividend_tickers, growth_tickers, amount_per_portfolio, start_date):
    """Backtest de dos canastas equal-weight con DRIP desde start_date.

    Reutiliza simulate_strategy por ticker (capital unitario) y reescala, porque el
    patrimonio DRIP es lineal en el capital inicial. Ambas canastas arrancan el mismo
    dia (common_start) con exactamente amount_per_portfolio cada una.
    """
    warnings = []

    def _simulate_basket(tickers):
        series_map = {}
        for t in tickers:
            try:
                stats, err = simulate_strategy(t, start_date, 1.0)
            except Exception as e:
                stats, err = None, str(e)
            if stats is None or stats['history'].empty:
                warnings.append(f"{t}: sin datos historicos ({err or 'vacio'}), se omitio del portafolio.")
                continue
            series_map[t] = _normalize_series_index(stats['history']['DRIP Wealth'])
        return series_map

    div_series = _simulate_basket(dividend_tickers)
    grw_series = _simulate_basket(growth_tickers)

    if not div_series:
        return None, "El portafolio de Dividendos no tiene tickers validos."
    if not grw_series:
        return None, "El portafolio de Crecimiento no tiene tickers validos."

    all_firsts = [s.index[0] for s in list(div_series.values()) + list(grw_series.values())]
    common_start = max(all_firsts)
    requested_start = pd.to_datetime(start_date)
    if common_start > requested_start + pd.Timedelta(days=7):
        warnings.append(
            f"La ventana se acorto a {common_start.date()}: algun ETF no cotiza desde {requested_start.date()}.")

    def _build_basket(series_map):
        allocation = amount_per_portfolio / len(series_map)
        cols = {}
        for t, s in series_map.items():
            s = s[s.index >= common_start]
            if s.empty:
                continue
            cols[t] = s / s.iloc[0] * allocation
        basket_df = pd.concat(cols, axis=1).sort_index().ffill().dropna()
        total = basket_df.sum(axis=1)
        per_ticker = [
            {
                'Ticker': t,
                'Asignacion': allocation,
                'Valor Final': basket_df[t].iloc[-1],
                'ROI %': (basket_df[t].iloc[-1] / allocation - 1) * 100,
            }
            for t in basket_df.columns
        ]
        return total, per_ticker

    div_total, div_per = _build_basket(div_series)
    grw_total, grw_per = _build_basket(grw_series)

    history = pd.concat({'Dividendos': div_total, 'Crecimiento': grw_total}, axis=1).sort_index().ffill().dropna()
    if history.empty:
        return None, "No hay datos suficientes en la ventana seleccionada."
    history.index.name = 'Date'

    div_final = history['Dividendos'].iloc[-1]
    grw_final = history['Crecimiento'].iloc[-1]

    result = {
        'history': history,
        'common_start': common_start.date(),
        'amount_per_portfolio': amount_per_portfolio,
        'dividend_stats': {'final_value': div_final, 'roi_percent': (div_final / amount_per_portfolio - 1) * 100},
        'growth_stats': {'final_value': grw_final, 'roi_percent': (grw_final / amount_per_portfolio - 1) * 100},
        'per_ticker': {'Dividendos': div_per, 'Crecimiento': grw_per},
        'warnings': warnings,
    }
    return result, None


@st.cache_data(show_spinner=False)
def simulate_portfolio_comparison_cached(div_csv, growth_csv, amount, start_date_str):
    """Cache wrapper. Recibe tickers como CSV y fecha como ISO string para hashabilidad."""
    dividend_tickers = [t.strip().upper() for t in div_csv.split(',') if t.strip()]
    growth_tickers = [t.strip().upper() for t in growth_csv.split(',') if t.strip()]
    start_date = datetime.date.fromisoformat(start_date_str)
    return simulate_portfolio_comparison(dividend_tickers, growth_tickers, amount, start_date)


# ============================================================
# v2.0 — BROKER DETECTION & PARSING
# ============================================================

def detect_broker(raw_text: str) -> str:
    """
    Detects the broker type from the first 30 lines of raw CSV text.
    Returns: 'schwab', 'ibkr', or 'generic'
    """
    lines = raw_text[:3000].lower()
    # 'fees & comm' es la firma del export actual de Schwab, cuyo header empieza
    # directo con "Date","Action","Symbol",...,"Fees & Comm","Amount" (sin la
    # antigua línea "Transactions for account").
    if ('charles schwab' in lines or 'brokerage account' in lines
            or 'transactions for account' in lines or 'fees & comm' in lines):
        return 'schwab'
    if 'interactive brokers' in lines or 'brokerid' in lines or ('transaction history' in lines and 'transaction type' in lines) or ('trades' in lines and 'header' in lines and 'symbol' in lines):
        return 'ibkr'
    return 'generic'


def parse_schwab_csv(raw_bytes: bytes) -> pd.DataFrame:
    """
    Parses a Charles Schwab CSV export.
    Schwab files have 2-4 metadata rows before the real header (Date, Action, Symbol...).
    Strips metadata rows and returns a raw DataFrame ready for normalize_csv().
    """
    for encoding in ['utf-8', 'latin1', 'cp1252']:
        try:
            text = raw_bytes.decode(encoding)
            break
        except Exception:
            continue
    else:
        text = raw_bytes.decode('utf-8', errors='replace')

    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if ('date' in line_lower or 'fecha' in line_lower) and ('symbol' in line_lower or 'action' in line_lower):
            header_idx = i
            break

    if header_idx is None:
        # No metadata found — treat as generic
        return pd.read_csv(io.StringIO(text), engine='python')

    clean_text = '\n'.join(lines[header_idx:])
    # Drop trailing disclaimer rows (Schwab appends totals/notes after last data row)
    clean_lines = []
    for line in clean_text.splitlines():
        if line.strip().startswith('"Transactions Total"') or line.strip().startswith('Transactions Total'):
            break
        clean_lines.append(line)

    return pd.read_csv(io.StringIO('\n'.join(clean_lines)), engine='python')


# ============================================================
# v2.9 — INVESTMENT INCOME (segunda fuente de validación)
# ============================================================
# Charles Schwab exporta un archivo "Investment Income" aparte del de transacciones.
# Sirve como SEGUNDA fuente independiente para validar el ingreso por dividendos que
# hoy se calcula 100% desde el CSV de transacciones. Las filas 'Estimated' son la
# proyección del broker (históricamente sobreestima en YieldMax) y NO se usan para
# cálculo; solo las 'Received' (histórico real).

# CUSIP→ticker: el income file reporta la historia previa a una reorganización del
# fondo bajo el CUSIP en vez del ticker. IMPORTANTE: este mapa se usa EXCLUSIVAMENTE
# al parsear el income file. Nunca debe aplicarse al CSV de transacciones (ese sí
# trae el CUSIP en filas de reverse split y hoy se descarta a propósito como mode_skip).
CUSIP_ALIAS = {
    "88634T493": "MSTY",   # YieldMax MSTR — migró de trust (reverse split 12/2025)
}

# Respaldo por descripción cuando el símbolo es un CUSIP/no reconocido.
_INCOME_DESC_HINTS = [
    ("YIELDMAX MSTR", "MSTY"),
]


def _row_year(dt):
    """Año calendario de la fecha de una fila de transacción, o None si no es una fecha
    válida (ausente/NaT). Usado para agrupar dividendos y retención por año fiscal."""
    if dt is None:
        return None
    try:
        if pd.isna(dt):
            return None
        return pd.Timestamp(dt).year
    except (TypeError, ValueError):
        return None


def _clean_money(raw) -> float:
    """Convierte un monto del broker ('$1,234.56', '6.57', '') a float; nan si no se puede."""
    try:
        if pd.isna(raw):
            return float('nan')
    except (TypeError, ValueError):
        pass
    s = str(raw).replace('$', '').replace(',', '').strip()
    if s in ('', '-', 'nan', 'N/A', 'None'):
        return float('nan')
    try:
        return float(s)
    except (ValueError, TypeError):
        return float('nan')


def _resolve_income_ticker(symbol, description):
    """Resuelve la identidad de una fila del income file -> (ticker, folded_bool).

    folded=True cuando hubo que plegar un CUSIP/descripción al ticker real.
    Solo aplica al income file; nunca al CSV de transacciones.
    """
    sym = str(symbol).upper().strip()
    if sym in CUSIP_ALIAS:
        return CUSIP_ALIAS[sym], True
    if sym in YIELDMAX_WHITELIST or sym in ETF_WHITELIST:
        return sym, False
    looks_like_cusip = len(sym) == 9 and any(c.isdigit() for c in sym)
    if looks_like_cusip:
        desc = str(description).upper()
        for hint, tk in _INCOME_DESC_HINTS:
            if hint in desc:
                return tk, True
    return sym, False


def parse_schwab_income_csv(raw_bytes: bytes):
    """Parsea el export 'Investment Income' de Charles Schwab.

    Devuelve un DataFrame [Date, Symbol, Ticker, Description, SecurityType, TxnType,
    IncomeType, Account, Amount, folded] o None si el archivo NO es un income file de
    Schwab (rechazo suave — p.ej. si suben por error el CSV de transacciones o uno de
    IBKR, que no exporta este formato). Filtra interés/cash y resuelve CUSIP->ticker.
    Filtra por la columna 'Income Type', nunca por posición (el archivo abre con filas
    'Estimated' antes de las 'Received').
    """
    # Excel (.xlsx): Schwab también exporta el Investment Income como libro de Excel.
    # Se convierte la hoja a texto CSV y se sigue exactamente el mismo camino que un CSV
    # (la firma 'PK\x03\x04' es la del ZIP que envuelve todo .xlsx).
    if raw_bytes[:4] == b'PK\x03\x04':
        try:
            _xl = pd.read_excel(io.BytesIO(raw_bytes), header=None, dtype=str, engine='openpyxl')
            text = _xl.to_csv(index=False, header=False)
        except Exception:
            return None
    else:
        for encoding in ('utf-8', 'latin1', 'cp1252'):
            try:
                text = raw_bytes.decode(encoding)
                break
            except Exception:
                continue
        else:
            text = raw_bytes.decode('utf-8', errors='replace')

    # Detección por encabezado de columnas (robusta a cambios del título de la primera
    # línea). La combinación 'transaction date' + 'symbol' + 'income type' es exclusiva
    # del export de Investment Income; el CSV de transacciones u otros brokers no la traen.
    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines[:40]):
        ll = line.lower()
        if 'transaction date' in ll and 'symbol' in ll and 'income type' in ll:
            header_idx = i
            break
    if header_idx is None:
        return None

    try:
        df = pd.read_csv(io.StringIO('\n'.join(lines[header_idx:])), engine='python')
    except Exception:
        return None
    df.columns = [str(c).strip() for c in df.columns]

    def _col(name):
        for c in df.columns:
            if c.lower() == name:
                return c
        return None

    c_date = _col('transaction date'); c_sym = _col('symbol'); c_desc = _col('security description')
    c_sectype = _col('security type'); c_txn = _col('transaction type')
    c_amt = _col('transaction amount'); c_inc = _col('income type'); c_acct = _col('account number')
    if not (c_date and c_amt and c_inc):
        return None

    out = pd.DataFrame()
    out['Date'] = pd.to_datetime(df[c_date], errors='coerce')
    out['Symbol'] = df[c_sym].astype(str).str.strip() if c_sym else ''
    out['Description'] = df[c_desc].astype(str) if c_desc else ''
    out['SecurityType'] = df[c_sectype].astype(str) if c_sectype else ''
    out['TxnType'] = df[c_txn].astype(str) if c_txn else ''
    out['IncomeType'] = df[c_inc].astype(str).str.strip()
    out['Account'] = df[c_acct].astype(str).str.strip() if c_acct else ''
    out['Amount'] = df[c_amt].apply(_clean_money)

    # Excluir interés de cash (no es de un ticker) y montos/fechas malformados.
    mask_cash = (out['SecurityType'].str.contains('cash', case=False, na=False)
                 | out['Symbol'].str.upper().isin(['NO NUMBER', 'NAN', '']))
    out = out[~mask_cash].copy()
    out = out.dropna(subset=['Date', 'Amount'])

    resolved = [_resolve_income_ticker(s, d) for s, d in zip(out['Symbol'], out['Description'])]
    out['Ticker'] = [r[0] for r in resolved]
    out['folded'] = [r[1] for r in resolved]
    return out.reset_index(drop=True)


def summarize_income(df) -> dict:
    """Resume el income file por ticker. Solo filas 'Received' (histórico real) para
    cálculo; las 'Estimated' (proyección del broker) se guardan aparte y NO se usan.

    Devuelve {'tickers': {ticker: {...}}, 'multi_account': bool, 'accounts': [...]}.
    """
    empty = {'tickers': {}, 'multi_account': False, 'accounts': []}
    if df is None or len(df) == 0:
        return empty

    accounts = sorted({a for a in df['Account'].astype(str) if a and a.lower() != 'nan'})
    rec = df[df['IncomeType'].str.lower() == 'received'].copy()
    est = df[df['IncomeType'].str.lower() == 'estimated'].copy()

    tickers = {}
    for tk, g in rec.groupby('Ticker'):
        amt = g['Amount'].dropna()
        by_year = g.assign(_Y=g['Date'].dt.year).groupby('_Y')['Amount'].sum()
        tickers[tk] = {
            'received_total': float(amt.sum()),
            'received_by_year': {int(k): round(float(v), 2) for k, v in by_year.items()},
            'received_window': (g['Date'].min(), g['Date'].max()),
            'folded': bool(g['folded'].any()),
            'n_payments': int(len(g)),
        }
    for tk, g in est.groupby('Ticker'):
        amt = g['Amount'].dropna()
        slot = tickers.setdefault(tk, {})
        slot['est_per_payment'] = float(amt.iloc[-1]) if len(amt) else None
        slot['est_n'] = int(len(g))

    return {'tickers': tickers, 'multi_account': len(accounts) > 1, 'accounts': accounts}


def parse_ibkr_csv(raw_bytes: bytes) -> pd.DataFrame:
    """
    Parses an Interactive Brokers Activity Statement CSV.
    IBKR exports are multi-section: each section has a Header row and Data rows.
    Extracts Trades (Stocks) and Dividends sections and merges into unified format.
    """
    for encoding in ['utf-8', 'latin1', 'cp1252']:
        try:
            text = raw_bytes.decode(encoding)
            break
        except Exception:
            continue
    else:
        text = raw_bytes.decode('utf-8', errors='replace')

    import csv as _csv
    text = text.lstrip('﻿')  # Remove BOM if present
    lines = text.splitlines()
    frames = []

    def _safe_float(raw: str) -> float:
        s = str(raw).strip().replace(',', '')
        try:
            return float(s)
        except (ValueError, TypeError):
            return 0.0

    def _ibkr_reader(section_name: str):
        """Yield (header, [data_rows]) for a named IB section using csv.reader."""
        header = None
        rows = []
        for parts in _csv.reader(io.StringIO(text)):
            parts = [p.strip() for p in parts]
            if len(parts) < 2:
                continue
            if parts[0] == section_name and parts[1] == 'Header':
                header = parts[2:]
            elif parts[0] == section_name and parts[1] == 'Data' and header:
                row = parts[2:]
                if len(row) >= len(header):
                    rows.append(row[:len(header)])
                elif row:
                    rows.append(row + [''] * (len(header) - len(row)))
        return header, rows

    # --- Transaction History format (IB "Transaction History" export, not Activity Statement) ---
    # Rows look like: Transaction History,Data,Date,Account,Description,Transaction Type,Symbol,...
    try:
        tx_header, tx_rows = _ibkr_reader('Transaction History')

        if tx_header and tx_rows:
            tx_df = pd.DataFrame(tx_rows, columns=tx_header)

            action_map = {
                'Dividend':              'Dividend',
                'Buy':                   'Buy',
                'Sell':                  'Sell',
                'Payment in Lieu':       'Dividend',   # pago sustituto de dividendo (securities lending)
                'Foreign Tax Withholding': 'Dividend', # retención de impuesto — monto negativo, reduce dividendos
            }
            tx_type_col = next((c for c in tx_df.columns if 'transaction type' in c.lower() or 'tipo' in c.lower()), None)
            if tx_type_col:
                tx_df = tx_df[tx_df[tx_type_col].isin(action_map)].copy()
            else:
                tx_type_col = 'Transaction Type'

            gross_col = next((c for c in tx_df.columns if 'gross' in c.lower()), None)
            net_col = next((c for c in tx_df.columns if c.lower() == 'net amount' or (c.lower().startswith('net') and 'amount' in c.lower())), None)
            symbol_col = next((c for c in tx_df.columns if c.lower() in ('symbol', 'símbolo', 'simbolo', 'ticker')), None) or 'Symbol'
            qty_col = next((c for c in tx_df.columns if 'quantity' in c.lower() or 'cantidad' in c.lower()), None) or 'Quantity'
            price_col = next((c for c in tx_df.columns if c.lower() == 'price' or c.lower() == 'precio'), None) or 'Price'
            date_col = next((c for c in tx_df.columns if c.lower() in ('date', 'fecha')), None) or 'Date'

            result_rows = []
            for _, row in tx_df.iterrows():
                action = action_map.get(str(row.get(tx_type_col, '')).strip(), '')
                if not action:
                    continue
                qty_raw = str(row.get(qty_col, '-')).strip()
                price_raw = str(row.get(price_col, '-')).strip()
                gross_raw = str(row.get(gross_col, '-')).strip() if gross_col else '-'
                net_raw = str(row.get(net_col, '-')).strip() if net_col else '-'
                qty = 0.0 if qty_raw in ('-', '') else _safe_float(qty_raw)
                price = 0.0 if price_raw in ('-', '') else _safe_float(price_raw)
                amount_raw = (net_raw if net_raw not in ('-', '') else gross_raw) if action == 'Dividend' else gross_raw
                amount = 0.0 if amount_raw in ('-', '') else _safe_float(amount_raw)
                raw_ticker = str(row.get(symbol_col, '')).strip()
                # Normalizar sufijos IB: TSLY.OLD → TSLY, XYZ.WS → XYZ, etc.
                norm_ticker = raw_ticker.split('.')[0] if '.' in raw_ticker and raw_ticker.split('.')[-1].upper() in ('OLD', 'WS', 'WI', 'RT', 'CV') else raw_ticker
                if not norm_ticker or norm_ticker == '-':
                    continue
                result_rows.append({
                    'Date': str(row.get(date_col, '')).strip(),
                    'Action': action,
                    'Ticker': norm_ticker,
                    'Quantity': qty,
                    'Price': price,
                    'Amount': amount,
                })

            if result_rows:
                frames.append(pd.DataFrame(result_rows))
                return pd.concat(frames, ignore_index=True)
    except Exception as e:
        print(f"IBKR Transaction History parse error: {e}")

    # --- Extract Trades section ---
    try:
        trade_header, trade_rows = _ibkr_reader('Trades')

        if trade_header and trade_rows:
            trades_df = pd.DataFrame(trade_rows, columns=trade_header)
            # Filter stocks only
            if 'Asset Category' in trades_df.columns:
                trades_df = trades_df[trades_df['Asset Category'].str.lower().str.contains('stock|equity', na=False)]

            # Map columns
            col_map = {}
            for col in trades_df.columns:
                cl = col.lower()
                if 'date' in cl or 'time' in cl:
                    col_map[col] = 'Date'
                elif col.lower() == 'symbol':
                    col_map[col] = 'Ticker'
                elif 'quantity' in cl:
                    col_map[col] = 'Quantity'
                elif 't. price' in cl or 'trade price' in cl:
                    col_map[col] = 'Price'
                elif 'proceeds' in cl:
                    col_map[col] = 'Amount'

            trades_df = trades_df.rename(columns=col_map)

            # Derive Action from Quantity sign
            if 'Quantity' in trades_df.columns:
                trades_df['Quantity_num'] = pd.to_numeric(
                    trades_df['Quantity'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
                trades_df['Action'] = trades_df['Quantity_num'].apply(
                    lambda q: 'Buy' if q > 0 else 'Sell')
                trades_df['Quantity'] = trades_df['Quantity_num'].abs()
                trades_df = trades_df.drop(columns=['Quantity_num'])

            keep = [c for c in ['Date', 'Action', 'Ticker', 'Quantity', 'Price', 'Amount'] if c in trades_df.columns]
            frames.append(trades_df[keep])
    except Exception as e:
        print(f"IBKR trades parse error: {e}")

    # --- Extract Dividends section ---
    try:
        div_header, div_rows = _ibkr_reader('Dividends')

        if div_header and div_rows:
            divs_df = pd.DataFrame(div_rows, columns=div_header)

            # Extract ticker from Description (pattern: "TICKER(CUSIP) Cash Dividend")
            if 'Description' in divs_df.columns:
                divs_df['Ticker'] = divs_df['Description'].str.extract(r'^([A-Z]+)', expand=False)

            col_map = {}
            for col in divs_df.columns:
                cl = col.lower()
                if 'date' in cl:
                    col_map[col] = 'Date'
                elif 'amount' in cl:
                    col_map[col] = 'Amount'

            divs_df = divs_df.rename(columns=col_map)
            divs_df['Action'] = 'Dividend'
            divs_df['Quantity'] = 0
            divs_df['Price'] = 0

            keep = [c for c in ['Date', 'Action', 'Ticker', 'Quantity', 'Price', 'Amount'] if c in divs_df.columns]
            frames.append(divs_df[keep])
    except Exception as e:
        print(f"IBKR dividends parse error: {e}")

    if frames:
        return pd.concat(frames, ignore_index=True)

    # Fallback: return raw first-pass parse
    return pd.read_csv(io.StringIO(text), engine='python', on_bad_lines='skip')


def load_and_detect_csv(uploaded_file) -> tuple:
    """
    Wrapper: reads uploaded file, detects broker, routes to correct parser.
    Returns: (raw_df, broker_name_str)
    """
    raw_bytes = uploaded_file.read()
    uploaded_file.seek(0)

    # Detect broker from first 3KB
    try:
        preview = raw_bytes[:3000].decode('utf-8', errors='replace')
    except Exception:
        preview = ''

    broker = detect_broker(preview)

    try:
        if broker == 'schwab':
            df = parse_schwab_csv(raw_bytes)
        elif broker == 'ibkr':
            df = parse_ibkr_csv(raw_bytes)
        else:
            # Generic: try encodings
            success = False
            for encoding in ['utf-8', 'latin1', 'cp1252', 'utf-16']:
                for sep in [None, ';', '\t']:
                    try:
                        uploaded_file.seek(0)
                        df = pd.read_csv(uploaded_file, sep=sep, encoding=encoding, engine='python')
                        if len(df.columns) > 1:
                            success = True
                            break
                    except Exception:
                        continue
                if success:
                    break
            if not success:
                df = pd.DataFrame()
    except Exception as e:
        print(f"load_and_detect_csv error: {e}")
        df = pd.DataFrame()

    return df, broker


# ============================================================
# v2.0 — TICKER CLASSIFICATION
# ============================================================

# v2.2 — Solo ETFs YieldMax confirmados por YieldMax LLC
# NVDL removido: es GraniteShares 2x Long NVDA, NO es YieldMax
YIELDMAX_WHITELIST = {
    'TSLY', 'NVDY', 'MSFO', 'AMZY', 'GOOY', 'CONY', 'JPMO', 'DISO',
    'YMAX', 'YMAG', 'MSTY', 'AMDY', 'ULTY', 'APLY', 'NFLY',
    'PYPY', 'GDXY', 'SNOY', 'XOMY', 'MRNY', 'BALY', 'COINY',
    'TSMY', 'PLTY', 'ABNY', 'LFGY',
}

# v2.2 — ETFs de crecimiento de largo plazo
# Removidos: TLT, XLE, XLI, XLF (sectoriales de corto plazo), ARKK (thematic especulativo)
# Excluidos por diseño: inversos (SDS, SQQQ, SPXS) y apalancados (TQQQ, UPRO, SPXL)
ETF_WHITELIST = {
    # Broad market
    'VTI', 'VOO', 'SPY', 'IVV', 'VT', 'ITOT', 'SCHB', 'SCHX', 'SCHA',
    # International
    'VEA', 'VWO', 'VXUS', 'EFA', 'EEM', 'ACWI',
    # Bonds (solo corto/medio plazo)
    'BND', 'AGG', 'BNDX', 'IEF', 'SHY', 'VCSH', 'VCIT',
    # Sector — solo tecnología y salud (largo plazo)
    'XLK', 'XLV', 'XLC', 'XLP', 'XLY', 'XLRE', 'XLU', 'XLB',
    # Tech / Semiconductores
    'QQQ', 'QQQM', 'SOXX', 'SMH', 'VGT', 'IGV', 'CIBR', 'HACK', 'BOTZ',
    # Dividend
    'SCHD', 'VYM', 'JEPI', 'JEPQ', 'HDV', 'DVY', 'DGRO',
    # Small / Mid cap
    'VB', 'VO', 'IJR', 'IJH', 'IWM', 'IWO', 'IWN',
    # Real estate
    'VNQ', 'IYR',
    # Commodities / Gold
    'GLD', 'IAU', 'SLV', 'GSG', 'DJP',
    # Growth
    'SCHG', 'IWF', 'VUG', 'MGK',
    # Multi-asset / Balanced
    'AOA', 'AOM', 'AOR', 'AOK',
    # Income / covered-call & prima de volatilidad (alto yield; el filtro de income los bucketea)
    'QYLD', 'SVOL',
}


def classify_tickers(tickers: list) -> dict:
    """
    Classifies each ticker into one of three modes:
    - 'mode_a': YieldMax ETF — solo whitelist explícita (sin regex para evitar falsos positivos)
    - 'mode_b': ETF de largo plazo conocido (ETF_WHITELIST) — sin inversos ni apalancados
    - 'mode_skip': Todo lo demás (acciones individuales, ETFs inversos/apalancados, desconocidos)
    """
    result = {}
    for ticker in tickers:
        t = str(ticker).upper().strip()
        if t in YIELDMAX_WHITELIST:
            result[t] = 'mode_a'
        elif t in ETF_WHITELIST:
            result[t] = 'mode_b'
        else:
            result[t] = 'mode_skip'
    return result


def is_held_too_briefly(ticker_df: pd.DataFrame, threshold_days: int = 14) -> tuple:
    """
    Returns (True, holding_days) if the position was fully closed in < threshold_days.
    Returns (False, None) if position is still open OR was held long enough.
    Only triggers when ALL shares have been sold (net_shares ≈ 0).
    """
    # Excluye 'transfer'/'journal': una salida por transferencia trae Quantity negativa y, con
    # abs(), inflaba total_bought — una posición realmente cerrada podía no detectarse.
    buys = ticker_df[ticker_df['Action'].str.lower().str.contains(
        'buy|bought|compra|deposit|contribution', na=False)]
    sells = ticker_df[ticker_df['Action'].str.lower().str.contains(
        'sell|sold|venta', na=False)]

    if buys.empty or sells.empty:
        return False, None  # Sin ventas → posición abierta → no filtrar

    # abs() en ambos: IB exporta ventas con Quantity negativa; sin abs el neto
    # se inflaría (bought - (-sold)) y una posición cerrada nunca se detectaría.
    total_bought = pd.to_numeric(buys['Quantity'], errors='coerce').fillna(0).abs().sum()
    total_sold = pd.to_numeric(sells['Quantity'], errors='coerce').fillna(0).abs().sum()
    net_shares = total_bought - total_sold

    if net_shares > 0.01:
        return False, None  # Todavía tiene shares → no filtrar

    # Posición completamente cerrada — calcular período
    first_buy = buys['Date'].min()
    last_sell = sells['Date'].max()
    holding_days = (last_sell - first_buy).days

    if holding_days < threshold_days:
        return True, holding_days

    return False, None


# ============================================================
# v2.0 — RISK ANALYSIS
# ============================================================

YIELDMAX_RISK_PROFILES = {
    'TSLY':  {'underlying': 'TSLA',  'name': 'Tesla',        'risk': 'HIGH',   'reason': 'Stock EV único, alta volatilidad, dependiente de Elon Musk y ciclos de demanda'},
    'CONY':  {'underlying': 'COIN',  'name': 'Coinbase',     'risk': 'HIGH',   'reason': 'Exchange cripto, riesgo regulatorio intenso, correlacionado con BTC'},
    'NVDY':  {'underlying': 'NVDA',  'name': 'NVIDIA',       'risk': 'HIGH',   'reason': 'Semiconductor único, ciclo de demanda IA, valuación elevada'},
    'MSTY':  {'underlying': 'MSTR',  'name': 'MicroStrategy','risk': 'HIGH',   'reason': 'Proxy de Bitcoin con apalancamiento, volatilidad extrema'},
    'YMAX':  {'underlying': 'Multi', 'name': 'YieldMax Universe', 'risk': 'HIGH', 'reason': 'Basket de covered-call ETFs, erosión de NAV compuesta'},
    'YMAG':  {'underlying': 'Mag-7', 'name': 'YieldMax Mag7','risk': 'HIGH',   'reason': 'Basket Mag-7 covered-call, beta alto a FAANG'},
    'NVDL':  {'underlying': 'NVDA',  'name': 'NVIDIA 2x',    'risk': 'HIGH',   'reason': 'NVIDIA con apalancamiento 2x — riesgo amplificado'},
    'AMZY':  {'underlying': 'AMZN',  'name': 'Amazon',       'risk': 'MEDIUM', 'reason': 'Mega-cap e-commerce + AWS, volatilidad moderada'},
    'GOOY': {'underlying': 'GOOGL', 'name': 'Alphabet',     'risk': 'MEDIUM', 'reason': 'Mega-cap búsqueda + ads + cloud, negocio diversificado'},
    'MSFO':  {'underlying': 'MSFT',  'name': 'Microsoft',    'risk': 'MEDIUM', 'reason': 'Mega-cap diversificado, flujos de caja estables, menor volatilidad'},
    'JPMO':  {'underlying': 'JPM',   'name': 'JPMorgan',     'risk': 'MEDIUM', 'reason': 'Banco más grande de EE.UU., servicios financieros diversificados'},
    'DISO':  {'underlying': 'DIS',   'name': 'Disney',       'risk': 'MEDIUM', 'reason': 'Media + streaming + parques, en proceso de reestructuración'},
    'AMDY':  {'underlying': 'AMD',   'name': 'AMD',          'risk': 'HIGH',   'reason': 'Semiconductor, compite con NVIDIA en IA, ciclos de demanda'},
}

COMPANY_DESCRIPTIONS = {
    'NVDA':  'Diseña GPUs y chips de IA; líder dominante en data center y entrenamiento de modelos',
    'AAPL':  'iPhone, Mac, servicios (App Store, iCloud); mayor empresa del mundo por capitalización',
    'MSFT':  'Office, Azure (nube), Windows; socio estratégico de OpenAI en IA empresarial',
    'TSMC':  'Mayor foundry de semiconductores del mundo; fabrica chips para Apple, NVIDIA y AMD',
    'ASML':  'Monopolio global en máquinas de litografía EUV para chips avanzados',
    'AVGO':  'Broadcom — chips de redes, infraestructura de software, adquisición de VMware',
    'AMD':   'CPUs Ryzen y GPUs Radeon; compite con Intel y NVIDIA en data center y gaming',
    'AMZN':  'E-commerce + AWS (mayor proveedor de nube del mundo) + publicidad digital',
    'GOOGL': 'Búsqueda, YouTube, Google Cloud, Android; IA vía modelos Gemini',
    'META':  'Facebook, Instagram, WhatsApp; ingresos por publicidad digital, apuesta en VR',
    'TSM':   'Mayor foundry de semiconductores; fabrica para Apple, NVIDIA, AMD y Qualcomm',
    'INTC':  'Intel — CPUs para PC y servidores; en transición hacia foundry propio',
    'QCOM':  'Qualcomm — chips Snapdragon para smartphones, líder en módem 5G',
    'TXN':   'Texas Instruments — semiconductores analógicos para industria y automoción',
    'MU':    'Micron — memoria DRAM y NAND Flash para data centers y dispositivos',
    'AMAT':  'Applied Materials — equipos de fabricación de semiconductores',
    'LRCX':  'Lam Research — sistemas de grabado para fabricación de chips',
    'KLAC':  'KLA — equipos de inspección y metrología para fabs de semiconductores',
    'ON':    'ON Semiconductor — chips de gestión de energía para vehículos eléctricos',
    'MRVL':  'Marvell — chips de redes e infraestructura de nube',
    'ORCL':  'Oracle — bases de datos empresariales y nube (OCI)',
    'CRM':   'Salesforce — CRM líder, plataforma de ventas y marketing en la nube',
    'CSCO':  'Cisco — infraestructura de redes, switches y seguridad empresarial',
    'IBM':   'IBM — servicios de TI empresarial, mainframes, consultoría con IA (watsonx)',
    'V':     'Visa — red de pagos digitales global, procesamiento de transacciones',
    'JPM':   'JPMorgan Chase — banco más grande de EE.UU., banca de inversión y retail',
    'BRK':   'Berkshire Hathaway — conglomerado de Warren Buffett, seguros y holdings',
    'JNJ':   'Johnson & Johnson — farmacéutica y dispositivos médicos diversificada',
    'UNH':   'UnitedHealth — mayor aseguradora de salud de EE.UU.',
    'XOM':   'ExxonMobil — petróleo integrado, mayor productor de EE.UU.',
    'CVX':   'Chevron — petróleo y gas integrado, operaciones globales',
}


_INSTRUMENTS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'knowledge', 'instruments.yaml')


@st.cache_data(ttl=3600, show_spinner=False)
def load_instruments() -> dict:
    """Carga la base de conocimiento editable de instrumentos (knowledge/instruments.yaml).

    Es la fuente de verdad para la sección de riesgo y el bloque de interpretación.
    Cada entrada del YAML enriquece/sobre-escribe el fallback embebido
    (YIELDMAX_RISK_PROFILES). Defensivo: ante cualquier error —archivo ausente, YAML
    inválido o PyYAML no instalado— devuelve el fallback embebido, así nunca queda
    peor que hoy. Claves por ticker en MAYÚSCULAS.
    """
    base = {k.upper(): dict(v) for k, v in YIELDMAX_RISK_PROFILES.items()}
    if _yaml is None:
        return base
    try:
        with open(_INSTRUMENTS_PATH, 'r', encoding='utf-8') as fh:
            data = _yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            return base
        for tk, prof in data.items():
            if not isinstance(prof, dict):
                continue
            merged = dict(base.get(str(tk).upper(), {}))
            merged.update({k: v for k, v in prof.items() if v is not None})
            base[str(tk).upper()] = merged
        return base
    except Exception:
        return base


_ROC19A_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'knowledge', 'roc_19a.yaml')
_ROC19A_CACHE = {}


def load_roc_19a() -> dict:
    """Carga el % de Retorno de Capital que YieldMax publica por distribución
    (knowledge/roc_19a.yaml), refrescado semanalmente por el GitHub Action que corre
    fetch_roc_19a.py contra la página oficial del fondo.

    Estructura por ticker (MAYÚSCULAS): {asof, source_url, weighted_pct,
    per_distribution: [{date, roc_pct}]}. Defensivo: archivo ausente/ inválido → {}.
    """
    if _ROC19A_CACHE.get('_loaded'):
        return _ROC19A_CACHE['data']
    data = {}
    if _yaml is not None:
        try:
            with open(_ROC19A_PATH, 'r', encoding='utf-8') as fh:
                raw = _yaml.safe_load(fh) or {}
            if isinstance(raw, dict):
                data = {str(k).upper(): v for k, v in raw.items() if isinstance(v, dict)}
        except Exception:
            data = {}
    _ROC19A_CACHE['_loaded'] = True
    _ROC19A_CACHE['data'] = data
    return data


_DISTRATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'knowledge', 'distribution_rate.yaml')
_DISTRATE_CACHE = {}


def load_distribution_rate() -> dict:
    """Carga la tasa de distribución TITULAR que anuncia YieldMax por fondo
    (knowledge/distribution_rate.yaml), refrescada semanalmente por el GitHub Action que corre
    fetch_roc_19a.py contra la página oficial del fondo.

    Estructura por ticker (MAYÚSCULAS): {rate_pct, as_of, source_url}. Defensivo: archivo
    ausente/ inválido → {}.
    """
    if _DISTRATE_CACHE.get('_loaded'):
        return _DISTRATE_CACHE['data']
    data = {}
    if _yaml is not None:
        try:
            with open(_DISTRATE_PATH, 'r', encoding='utf-8') as fh:
                raw = _yaml.safe_load(fh) or {}
            if isinstance(raw, dict):
                data = {str(k).upper(): v for k, v in raw.items() if isinstance(v, dict)}
        except Exception:
            data = {}
    _DISTRATE_CACHE['_loaded'] = True
    _DISTRATE_CACHE['data'] = data
    return data


def advertised_distribution_rate(ticker) -> float:
    """% de distribución titular publicado por YieldMax para `ticker`, o None si no se conoce."""
    info = load_distribution_rate().get(str(ticker).upper()) or {}
    r = info.get('rate_pct')
    try:
        return float(r) if r is not None else None
    except (TypeError, ValueError):
        return None


_ROCHEALTH_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'knowledge', 'roc_health_history.yaml')
_ROCHEALTH_CACHE = {}


def load_roc_health_history() -> dict:
    """Carga el histórico del veredicto de salud del NAV por fondo
    (knowledge/roc_health_history.yaml), generado semanalmente por snapshot_roc_health.py.

    Estructura por ticker (MAYÚSCULAS): [{date, verdict, roc_pct, price_cagr}].
    Defensivo: archivo ausente/ inválido → {}.
    """
    if _ROCHEALTH_CACHE.get('_loaded'):
        return _ROCHEALTH_CACHE['data']
    data = {}
    if _yaml is not None:
        try:
            with open(_ROCHEALTH_PATH, 'r', encoding='utf-8') as fh:
                raw = _yaml.safe_load(fh) or {}
            if isinstance(raw, dict):
                data = {str(k).upper(): v for k, v in raw.items() if isinstance(v, list)}
        except Exception:
            data = {}
    _ROCHEALTH_CACHE['_loaded'] = True
    _ROCHEALTH_CACHE['data'] = data
    return data


def latest_health_verdict(ticker):
    """Último veredicto registrado del fondo en knowledge/roc_health_history.yaml
    (para la histéresis de classify_roc_health). None si el ticker no tiene histórico."""
    series = load_roc_health_history().get(str(ticker).upper()) or []
    if not series:
        return None
    last = sorted(series, key=lambda r: r.get('date') or '')[-1]
    return last.get('verdict')


def _estimate_roc_from_19a(ticker, dist_dated):
    """Estima el ROC del holder con el % que el fondo publica en sus avisos 19a.

    `dist_dated`: lista de (fecha, monto) de distribuciones recibidas (cash + reinvertido).
    Empata cada distribución con el %ROC publicado de esa fecha (±7 días); si no hay empate
    usa el % ponderado del fondo (`weighted_pct`). Devuelve (roc_$|None, roc_%|None).
    """
    info = load_roc_19a().get(str(ticker).upper())
    if not info or not dist_dated:
        return None, None
    total = sum(abs(a or 0) for _, a in dist_dated)
    if total <= 0:
        return None, None

    dated = []
    for rowp in (info.get('per_distribution') or []):
        try:
            dated.append((pd.Timestamp(rowp['date']).normalize(), float(rowp['roc_pct'])))
        except Exception:
            continue
    weighted = info.get('weighted_pct')
    weighted = float(weighted) if weighted is not None else None

    roc_sum = 0.0
    for dt, amt in dist_dated:
        amt = abs(amt or 0)
        pct = None
        if dated and dt is not None:
            best = min(dated, key=lambda dp: abs((dp[0] - pd.Timestamp(dt).normalize()).days))
            if abs((best[0] - pd.Timestamp(dt).normalize()).days) <= 7:
                pct = best[1]
        if pct is None:
            pct = weighted
        if pct is None:
            return None, None
        roc_sum += amt * (pct / 100.0)
    return roc_sum, (roc_sum / total * 100.0)


def build_total_return_series(close, dividends, withhold_schedule=None):
    """Total Return base 100 de una serie de precios con sus dividendos, en dos escenarios:
    reinversión (DRIP) y cobro en efectivo sin reinvertir. Función PURA, sin Streamlit.

    Args:
        close: pd.Series de precios de cierre, indexada por fecha (orden ascendente).
        dividends: pd.Series de dividendo por acción, mismo tipo de índice que `close`
            (0 o NaN los días sin pago). Se reindexa contra `close`.
        withhold_schedule: retención aplicada a cada distribución antes de reinvertir/
            acumular. None = sin retención (bruto). Puede ser un float plano en fracción
            0.0–1.0 (0.30 = 30%) o un dict {fecha: tasa} con la tasa efectiva por distribución
            (ver `build_roc_aware_withholding`). Fechas no presentes en el dict → 0.

    Devuelve un DataFrame indexado como `close` con columnas:
        'drip' — reinvertir cada dividendo neto al close del día de pago.
        'cash' — acciones fijas desde el día 0 + caja neta acumulada (NAV restante + caja).
    Si el fondo no paga dividendos, 'drip' == 'cash' == retorno de solo precio (Price Return).
    """
    if close is None or len(close) == 0:
        return pd.DataFrame(columns=['drip', 'cash'])

    close = close.dropna()
    if dividends is not None:
        divs = dividends.reindex(close.index).fillna(0.0)
    else:
        divs = pd.Series(0.0, index=close.index)

    close0 = float(close.iloc[0]) if len(close) else 0.0
    if close0 <= 0:
        return pd.DataFrame({'drip': [None] * len(close), 'cash': [None] * len(close)},
                             index=close.index)

    def _rate_for(dt):
        if withhold_schedule is None:
            return 0.0
        if isinstance(withhold_schedule, dict):
            if dt in withhold_schedule:
                return float(withhold_schedule[dt] or 0.0)
            key = pd.Timestamp(dt).normalize()
            return float(withhold_schedule.get(key, 0.0) or 0.0)
        try:
            return float(withhold_schedule)
        except (TypeError, ValueError):
            return 0.0

    shares_drip = 100.0 / close0
    shares_cash = 100.0 / close0
    cash_accum = 0.0
    drip_vals, cash_vals = [], []
    for dt, px in close.items():
        px = float(px)
        d = float(divs.loc[dt] or 0.0)
        if d > 0 and px > 0:
            rate = max(0.0, min(1.0, _rate_for(dt)))
            net_div = d * (1.0 - rate)
            cash_from_div = shares_drip * net_div
            shares_drip += cash_from_div / px
            cash_accum += shares_cash * net_div
        drip_vals.append(shares_drip * px)
        cash_vals.append(shares_cash * px + cash_accum)

    return pd.DataFrame({'drip': drip_vals, 'cash': cash_vals}, index=close.index)


def build_roc_aware_withholding(ticker, dividend_dates, base_rate=0.30):
    """Tasa de retención NRA efectiva por distribución, usando el escudo fiscal del ROC
    publicado en los avisos 19a del fondo (`knowledge/roc_19a.yaml`).

    Cada distribución empata con el aviso 19a más cercano en fecha (tolerancia ±6 días);
    `tasa_efectiva = base_rate × (1 − roc_pct/100)`. Si una fecha no tiene aviso dentro de
    tolerancia, usa el promedio de roc_pct de los avisos dentro de la ventana de
    `dividend_dates` (o `weighted_pct` del fondo si no hay ninguno en la ventana).

    Args:
        ticker: símbolo del fondo (YieldMax u otro con datos 19a).
        dividend_dates: fechas (ex-date) de las distribuciones recibidas en la ventana.
        base_rate: tasa de retención NRA sin escudo, en fracción 0.0–1.0 (default 0.30 = 30%;
            usar la tasa del país del inversor si se conoce — ver NRA_COUNTRY_RATES).

    Devuelve dict {fecha (pd.Timestamp normalizada): tasa efectiva}, o None si el fondo no
    tiene datos 19a (`load_roc_19a()` sin entrada para el ticker).
    """
    dividend_dates = list(dividend_dates) if dividend_dates is not None else []
    info = load_roc_19a().get(str(ticker).upper())
    if not info or not dividend_dates:
        return None

    dts_norm = [pd.Timestamp(dt).normalize() for dt in dividend_dates]

    dated = []
    for rowp in (info.get('per_distribution') or []):
        try:
            dated.append((pd.Timestamp(rowp['date']).normalize(), float(rowp['roc_pct'])))
        except Exception:
            continue

    weighted = info.get('weighted_pct')
    weighted = float(weighted) if weighted is not None else None

    fallback_pct = weighted
    if dated:
        win_min, win_max = min(dts_norm), max(dts_norm)
        window_pcts = [pct for dt, pct in dated if win_min <= dt <= win_max]
        if window_pcts:
            fallback_pct = sum(window_pcts) / len(window_pcts)

    if not dated and fallback_pct is None:
        return None

    result = {}
    for dt in dts_norm:
        pct = None
        if dated:
            best = min(dated, key=lambda dp: abs((dp[0] - dt).days))
            if abs((best[0] - dt).days) <= 6:
                pct = best[1]
        if pct is None:
            pct = fallback_pct
        if pct is None:
            continue
        rate = base_rate * (1.0 - pct / 100.0)
        result[dt] = max(0.0, min(1.0, rate))

    return result if result else None


# ── Veredicto de salud del NAV: ¿el ROC es destructivo o contable? ───────────
# Umbrales del clasificador. La VERDAD sobre destructividad es la tendencia del NAV
# (price_cagr) + el total return honesto, NO el % del aviso 19a (que salta entre 0% y
# 99% por motivos fiscales). El 19a solo dice cuánta de la distribución se cataloga
# como ROC; si ese ROC es alto Y el NAV cae Y el total return ≤0, entonces te están
# devolviendo tu propio capital (destructivo). Si el NAV aguanta/sube, es contable.
ROC_HEALTH_HIGH_PCT     = 50.0   # ROC ≥ esto = "alto" (gran parte de la distribución es capital)
# Histéresis anti-parpadeo del umbral de ROC alto: para SALIR de destructivo el ROC debe caer
# bajo 45; para ENTRAR debe subir sobre 55 — evita alertas falsas cuando oscila cerca de 50.
ROC_HEALTH_HIGH_EXIT_PCT  = 45.0
ROC_HEALTH_HIGH_ENTER_PCT = 55.0
ROC_HEALTH_NAV_FLAT_PCT = 2.0    # |price_cagr| ≤ esto = NAV prácticamente plano
ROC_HEALTH_MIN_DAYS     = 180    # < esto de historia de precio = no se puede afirmar nada
ROC_HEALTH_STALE_DAYS   = 45     # aviso 19a más viejo que esto = dato desactualizado
# Filtro de justicia de mercado: cuánto peor que su subyacente puede caer el NAV del fondo
# antes de dejar de ser "cae por el mercado" y contar como canibalización adicional.
ROC_HEALTH_REL_TOL_PCT  = 10.0

_ROC_HEALTH_COLORS = {
    'destructive':  '#e05c5c',   # rojo
    'accounting':   '#4caf82',   # verde
    'mixed':        '#e0a23c',   # ámbar
    'insufficient': '#8a8f98',   # gris
}
_ROC_HEALTH_LABELS = {
    'destructive':  'ROC DESTRUCTIVO',
    'accounting':   'ROC CONTABLE',
    'mixed':        'VIGILAR',
    'insufficient': 'DATOS INSUFICIENTES',
}
# Titular humano (capa simple, visible para cualquiera; el `reason` técnico va en el desplegable).
_ROC_HEALTH_HEADLINES = {
    'destructive':  '🔴 Tu capital se está encogiendo',
    'accounting':   '🟢 Tu capital está sano',
    'mixed':        '🟡 Señales mezcladas — vigílalo',
    'insufficient': '⚪ Aún no se puede medir',
}
_PLAIN_INSUFFICIENT = ("Todavía no hay suficiente historia (o el dato está viejo) para decir con "
                       "certeza si tu capital se está erosionando. Vuelve a revisar cuando el fondo "
                       "tenga más recorrido o se actualice el dato.")


def _roc_health_gauge(price_cagr):
    """Posición 0–100 en el medidor 'Sano ↔ Destruyéndose' a partir del CAGR del NAV.
    0 = sano (NAV +10%/año o mejor), 100 = destruyéndose (NAV −50%/año o peor). None si no hay dato."""
    if price_cagr is None:
        return None
    score = (10.0 - float(price_cagr)) / 60.0 * 100.0
    return round(max(0.0, min(100.0, score)), 1)


def classify_roc_health(roc_pct, price_cagr, total_return_pct=None,
                        history_days=None, roc_asof_days=None,
                        prev_verdict=None, underlying_cagr=None) -> dict:
    """Veredicto único de salud del NAV de un YieldMax. Función PURA y testeable.

    Parámetros (todos numéricos, None si no disponibles):
      roc_pct          % de la distribución catalogado como ROC (19a o broker).
      price_cagr       CAGR de precio observado (= erosión/apreciación del NAV), %.
                       Pasar el reciente (12m) si existe; si no, el de toda la ventana.
      total_return_pct Total return honesto (precio + income), % — opcional, prioritario.
      history_days     días de historia de precio observada (guarda anti falso-veredicto).
      roc_asof_days    antigüedad en días del dato 19a (guarda de frescura).
      prev_verdict     veredicto anterior del fondo (histórico) — activa la histéresis del
                       umbral de ROC alto: viniendo de 'destructive' se sale solo si el ROC
                       cae bajo ROC_HEALTH_HIGH_EXIT_PCT (45); viniendo de 'accounting'/
                       'mixed' se entra solo si sube sobre ROC_HEALTH_HIGH_ENTER_PCT (55).
                       None o 'insufficient' → umbral simple de 50 (comportamiento clásico).
      underlying_cagr  CAGR reciente (12m) del activo subyacente, % — filtro de justicia de
                       mercado. None → comportamiento absoluto clásico (sin este filtro): un
                       fondo que cae ~1:1 con un subyacente que también cae NO es destructivo,
                       solo es riesgo de mercado; se confirma destructivo si el subyacente se
                       recupera y el fondo no.

    Devuelve {'verdict','label','color','reason','headline','plain','gauge_score'} con
    verdict ∈ {'destructive','accounting','mixed','insufficient'}.
    - reason: detalle TÉCNICO (para el desplegable). - headline/plain: capa SIMPLE.
    - gauge_score: 0 (sano) … 100 (destruyéndose), None si 'insufficient'.
    """
    def _out(v, reason, plain):
        gauge = None if v == 'insufficient' else _roc_health_gauge(price_cagr)
        return {'verdict': v, 'label': _ROC_HEALTH_LABELS[v], 'color': _ROC_HEALTH_COLORS[v],
                'reason': reason, 'headline': _ROC_HEALTH_HEADLINES[v], 'plain': plain,
                'gauge_score': gauge}

    # ── Guarda de confianza: sin datos suficientes no se emite veredicto ──
    if roc_pct is None or price_cagr is None:
        return _out('insufficient',
                    "Faltan datos de ROC o del precio del fondo para emitir un veredicto.",
                    _PLAIN_INSUFFICIENT)
    if history_days is not None and history_days < ROC_HEALTH_MIN_DAYS:
        return _out('insufficient',
                    f"Historia muy corta (~{int(history_days)} días): no se puede afirmar "
                    f"erosión de NAV a ciencia cierta. Se necesitan ≥{ROC_HEALTH_MIN_DAYS} días.",
                    _PLAIN_INSUFFICIENT)
    if roc_asof_days is not None and roc_asof_days > ROC_HEALTH_STALE_DAYS:
        return _out('insufficient',
                    f"El dato de ROC (19a) tiene ~{int(roc_asof_days)} días: está "
                    f"desactualizado para juzgar el estado actual del fondo.",
                    _PLAIN_INSUFFICIENT)

    # La VERDAD sobre destructividad es la tendencia del NAV (señal PRIMARIA). El total
    # return solo MATIZA — si tu income compensó la erosión, sigue siendo ROC destructivo
    # al NAV, solo que aún vas arriba (pero la distribución futura tiende a bajar).
    # Umbral de ROC alto con histéresis según el veredicto anterior (anti-parpadeo).
    if prev_verdict == 'destructive':
        roc_high = roc_pct >= ROC_HEALTH_HIGH_EXIT_PCT
    elif prev_verdict in ('accounting', 'mixed'):
        roc_high = roc_pct >= ROC_HEALTH_HIGH_ENTER_PCT
    else:
        roc_high = roc_pct >= ROC_HEALTH_HIGH_PCT
    nav_falling = price_cagr < -ROC_HEALTH_NAV_FLAT_PCT
    nav_rising  = price_cagr >  ROC_HEALTH_NAV_FLAT_PCT
    tr_pos = total_return_pct is not None and total_return_pct > 0
    tr_neg = total_return_pct is not None and total_return_pct <= 0

    nav_txt = f"el NAV {'cae' if nav_falling else 'sube' if nav_rising else 'está plano'} ({price_cagr:+.0f}%/año)"
    tr_txt  = (f" El total return honesto es {total_return_pct:+.0f}%." if total_return_pct is not None else "")
    tr_nuance = (" Aun así tu income ha más que compensado la erosión, pero el NAV sigue "
                 "encogiendo y la distribución futura tiende a bajar." if tr_pos else "")
    # Matiz en lenguaje llano cuando el income aún compensa la caída del precio.
    plain_nuance = (" Por ahora tus dividendos cobrados compensan la caída, pero el fondo se "
                    "sigue achicando." if tr_pos else "")

    # ── Filtro de justicia de mercado: ¿la caída del NAV es del fondo, o de su subyacente? ──
    under_falling = underlying_cagr is not None and underlying_cagr < -ROC_HEALTH_NAV_FLAT_PCT
    nav_gap = (price_cagr - underlying_cagr) if underlying_cagr is not None else None
    market_justified = under_falling and nav_gap is not None and nav_gap >= -ROC_HEALTH_REL_TOL_PCT

    # ── NAV cae ──
    if nav_falling:
        if roc_high:
            if market_justified:
                out = _out('mixed',
                            f"{nav_txt[0].upper()+nav_txt[1:]} pero el subyacente cayó "
                            f"{underlying_cagr:+.0f}%/año: la caída del NAV (gap {nav_gap:+.0f} pts) es "
                            f"consistente con el mercado, no con destrucción de capital. El "
                            f"{roc_pct:.0f}% de ROC es etiqueta fiscal.{tr_nuance or tr_txt}",
                            "El fondo cae porque su activo base cae, no porque te esté devolviendo tu "
                            "capital a escondidas. Riesgo de mercado, no destrucción."
                            + plain_nuance +
                            " <b>Qué vigilar:</b> si el fondo empieza a caer bastante más que su "
                            "subyacente, o si el subyacente se recupera y el fondo no.")
                out['headline'] = '🟠 Cae por el mercado, no por el fondo'
                return out
            reason_extra = ""
            if under_falling and nav_gap is not None and nav_gap < -ROC_HEALTH_REL_TOL_PCT:
                reason_extra = (f" Además cae {abs(nav_gap):.0f} pts MÁS que su subyacente "
                                f"({underlying_cagr:+.0f}%/año) — sobre-captura de la pérdida.")
            elif underlying_cagr is not None and not under_falling:
                reason_extra = (f" El subyacente está plano/recuperado ({underlying_cagr:+.0f}%/año) y "
                                f"el fondo sigue cayendo: no recupera porque liquidó capital — "
                                f"destructivo confirmado.")
            return _out('destructive',
                        f"{nav_txt[0].upper()+nav_txt[1:]} y el {roc_pct:.0f}% de la distribución es "
                        f"ROC: el fondo se sostiene devolviéndote tu propio capital — erosión del NAV."
                        f"{tr_nuance or tr_txt}{reason_extra}",
                        "El fondo te paga sacando dinero de tu propio bolsillo, no solo de ganancias "
                        "reales. El cheque mensual se ve bien, pero cada mes tu inversión vale menos."
                        + plain_nuance +
                        " Este veredicto mide el motor de los cheques (de dónde sale el pago), no tu "
                        "resultado final como inversionista — para eso revisa la pestaña «Resultado real»."
                        " <b>Qué vigilar:</b> si el precio del fondo sigue cayendo, el pago futuro también baja.")
        if tr_neg:
            return _out('destructive',
                        f"{nav_txt[0].upper()+nav_txt[1:]}{tr_txt} Aunque el ROC reportado sea "
                        f"{roc_pct:.0f}%, el precio se erosiona y el total return es negativo.",
                        "Aunque casi todo lo que te pagan sea ganancia real, el precio del fondo se "
                        "hunde más rápido: sumando todo, hoy tienes menos de lo que pusiste. "
                        "Este veredicto mide el motor de los cheques (de dónde sale el pago), no tu "
                        "resultado final como inversionista — para eso revisa la pestaña «Resultado real». "
                        "<b>Qué vigilar:</b> si el activo que sigue no se recupera, seguirás perdiendo capital.")
        # ROC bajo + NAV cae + (TR positivo o desconocido): la caída viene más del subyacente
        return _out('mixed',
                    f"{nav_txt[0].upper()+nav_txt[1:]} pero solo el {roc_pct:.0f}% es ROC: la caída "
                    f"viene más del subyacente que de devolución de capital.{tr_nuance or tr_txt} Vigílalo.",
                    "El precio baja, pero la mayor parte de lo que te pagan sí es ganancia real; la "
                    "caída viene más del activo que el fondo sigue que de devolverte tu dinero."
                    + plain_nuance +
                    " <b>Qué vigilar:</b> revísalo el próximo mes — si el ROC sube y el precio sigue "
                    "cayendo, pasaría a destructivo.")

    # ── NAV sube o plano ──
    if nav_rising or tr_pos:
        extra = (f" El {roc_pct:.0f}% catalogado como ROC es clasificación fiscal, no pérdida de capital."
                 if roc_high else "")
        return _out('accounting',
                    f"{nav_txt[0].upper()+nav_txt[1:]}{tr_txt} El ROC es contable (pass-through), "
                    f"no destructivo: tu capital no se está erosionando.{extra}",
                    "El fondo te paga con dinero que de verdad gana (vendiendo opciones), no con el "
                    "tuyo. Que la etiqueta diga 'retorno de capital' es solo un tema de impuestos. "
                    "<b>Tu capital se mantiene o crece.</b>")

    # ── NAV plano sin señal de total return ──
    return _out('mixed',
                f"{nav_txt[0].upper()+nav_txt[1:]}, con {roc_pct:.0f}% de ROC.{tr_txt} Ni claramente "
                f"destructivo ni claramente sano — conviene seguirlo mes a mes.",
                "El precio está plano y las señales no son claras: ni se nota erosión ni crecimiento. "
                "<b>Qué vigilar:</b> síguelo mes a mes para ver hacia dónde se inclina.")


def get_yieldmax_risk_profile(ticker: str) -> dict:
    """Perfil de riesgo de un ticker desde la base de conocimiento (con fallback). Sin API.

    Devuelve siempre las 4 claves que consume la sección de riesgo
    (underlying/name/risk/reason); los campos profundos los lee build_interpretation.
    """
    prof = load_instruments().get(str(ticker).upper())
    if prof:
        return {
            'underlying': prof.get('underlying', 'N/A'),
            'name': prof.get('name', ticker),
            'risk': prof.get('risk', 'UNKNOWN'),
            'reason': prof.get('reason', ''),
        }
    return {
        'underlying': 'N/A', 'name': ticker, 'risk': 'UNKNOWN',
        'reason': 'Perfil de riesgo no disponible para este ticker'
    }


def build_underlying_exposure(results: dict, ticker: str) -> dict:
    """Explica la exposición ASIMÉTRICA de un YieldMax a su subyacente: captura casi toda la
    caída pero le capan la subida. Combina el conocimiento curado (instruments.yaml) con el
    contraste de retornos reales (subyacente vs fondo, últimos 12m). Devuelve {'lines': [...]}.
    Vacío si el ticker no es YieldMax o no tiene subyacente conocido.
    """
    s = results.get(ticker, {}) or {}
    if not isinstance(s, dict) or 'error' in s:
        return {'lines': []}
    info = load_instruments().get(str(ticker).upper(), {})
    if (info.get('type') or '').lower() != 'yieldmax':
        return {'lines': []}
    under = s.get('underlying_ticker') or info.get('underlying')
    if not under or str(under).upper() in ('N/A', 'NA', ''):
        return {'lines': []}
    under = str(under).upper()
    name = info.get('name', under)
    driver = info.get('driver')

    lines = []
    chain = f"{ticker} sigue a {under} ({name})"
    if driver:
        chain += f", que a su vez se mueve con {driver}"
    lines.append(chain + ".")
    lines.append(
        f"Su estrategia vende opciones sobre {under}: te llevas casi toda la CAÍDA de {under}, "
        f"pero te CAPAN la subida. La exposición es asimétrica — riesgo completo a la baja, "
        f"beneficio limitado al alza.")
    u = s.get('underlying_cagr_recent')
    f = s.get('price_cagr_recent')
    if u is not None and f is not None:
        contrast = ("Cuando el subyacente cae, el fondo lo acompaña casi 1:1." if u < 0 else
                    f"Aunque {under} subió, {ticker} capturó solo una fracción de esa subida.")
        lines.append(f"Últimos 12 meses: {under} {u:+.0f}% vs {ticker} {f:+.0f}%. {contrast}")
    lines.append(
        f"Conclusión: si {under} se recupera, {ticker} sube poco; si {under} cae, {ticker} cae "
        f"casi igual. Tu income depende de que {under} no se desplome.")

    # ¿Y si hubieras tenido el subyacente directo? (misma plata y fechas, total return)
    hold = s.get('underlying_hold_value')
    fund_total = (s.get('market_value') or 0) + (s.get('dividends_collected_cash') or 0)
    if hold and hold > 0 and fund_total > 0:
        diff = fund_total - hold
        signo = '+' if diff >= 0 else '−'
        veredicto = (f"el income compensó: vas {signo}${abs(diff):,.0f} arriba de haber tenido {under}"
                     if diff >= 0 else
                     f"con {under} directo tendrías ${abs(diff):,.0f} más — la apreciación superó al income")
        lines.append(
            f"En tu período, {ticker} (posición hoy + dividendos cobrados) vale ${fund_total:,.0f}; "
            f"con la misma plata y fechas en {under} directo serían ${hold:,.0f}: {veredicto}.")

    seen, out = set(), []
    for ln in lines:
        if ln and ln not in seen:
            seen.add(ln); out.append(ln)
    return {'lines': out}


def build_interpretation(results: dict, ticker: str, mode: str = None) -> dict:
    """Interpretación EDUCATIVA por ticker: combina el conocimiento curado
    (instruments.yaml) con los números ya calculados. Nunca recomienda comprar/vender
    ni inventa conocimiento que no esté en el YAML. Devuelve {'lines': [str, ...]}.
    """
    s = results.get(ticker, {}) or {}
    if not isinstance(s, dict) or 'error' in s:
        return {'lines': []}
    info = load_instruments().get(str(ticker).upper(), {})

    pocket = s.get('pocket_investment', 0) or 0
    market = s.get('market_value', 0) or 0
    inc = s.get('dividends_collected_cash', 0) or 0
    total_ret = market + inc - pocket
    cap = market - pocket

    def _signed(v):
        return f"{'-' if v < 0 else '+'}${abs(v):,.0f}"

    lines = []

    # (1) Qué es — solo conocimiento curado, jamás inventado
    if info.get('income_mechanism'):
        lines.append(info['income_mechanism'])
    elif info.get('note') and info.get('type') in ('etf', 'leveraged'):
        lines.append(info['note'])

    # (2) Qué dicen TUS números — derivado de datos reales
    if pocket > 0:
        if cap < 0 and inc > 0:
            if inc + cap >= 0:
                lines.append(
                    f"En tu caso el precio cayó ${abs(cap):,.0f} pero cobraste ${inc:,.0f} "
                    f"en dividendos: el income ya compensó la caída (retorno total "
                    f"{_signed(total_ret)}). Por eso se evalúa por retorno total, no por el precio."
                )
            else:
                lines.append(
                    f"En tu caso el precio cayó ${abs(cap):,.0f} y llevas ${inc:,.0f} en "
                    f"dividendos: el income todavía no cubre la caída (retorno total "
                    f"{_signed(total_ret)})."
                )
        elif total_ret != 0:
            lines.append(
                f"Tu retorno total es {_signed(total_ret)} "
                f"(capital {_signed(cap)} + income ${inc:,.0f})."
            )

    # (2b) Yield forward (lo que anuncian) vs realizado (lo que cobraste)
    _fwd_y = s.get('forward_yield')
    _real_y = s.get('realized_yield')
    if _fwd_y and _real_y:
        _ln = (f"Yield forward {_fwd_y:.1f}% (último pago anualizado — lo que anuncian) "
               f"vs yield realizado {_real_y:.1f}% (lo que de verdad cobraste en 12 meses).")
        if _fwd_y > _real_y * 1.15:
            _ln += " El forward es optimista: tus pagos recientes vienen por debajo de ese ritmo."
        lines.append(_ln)

    # (2c) Cambio de frecuencia de pago (p.ej. mensual → semanal)
    _cad = s.get('cadence_change')
    if isinstance(_cad, dict) and _cad.get('changed'):
        lines.append(
            f"{_cad['note']} Por eso el ritmo de pagos no se compara 1:1 con antes "
            f"(un pago {_cad['recent_label']} es menor que uno {_cad['old_label']}, "
            f"aunque sumen parecido al año).")

    # (3) Qué considerar — sostenibilidad / nota curada
    if info.get('income_mechanism') and info.get('sustainability'):
        lines.append(info['sustainability'])
    elif info.get('income_mechanism') and info.get('note'):
        lines.append(info['note'])
    elif info.get('type') == 'leveraged' and info.get('nav_erosion'):
        lines.append(info['nav_erosion'])

    seen, out = set(), []
    for ln in lines:
        if ln and ln not in seen:
            seen.add(ln)
            out.append(ln)
    return {'lines': out[:4]}


def build_portfolio_verdict(results: dict, classify_map: dict = None) -> dict:
    """Síntesis EDUCATIVA a nivel de portafolio (concentración, peso en income tipo
    YieldMax, y balance capital-vs-income). Deriva todo de los números ya calculados;
    no recomienda comprar/vender. Devuelve {'lines': [str, ...]} (puede ir vacío).
    """
    valid = {t: s for t, s in results.items()
             if isinstance(s, dict) and 'error' not in s and not s.get('skipped')}
    if not valid:
        return {'lines': []}

    total_market = sum(s.get('market_value', 0) or 0 for s in valid.values())
    total_inv = sum(s.get('pocket_investment', 0) or 0 for s in valid.values())
    total_inc = sum(s.get('dividends_collected_cash', 0) or 0 for s in valid.values())
    lines = []

    # Concentración: mayor posición como % del valor
    if total_market > 0:
        top_t, top_v = max(((t, s.get('market_value', 0) or 0) for t, s in valid.items()),
                           key=lambda x: x[1])
        top_pct = top_v / total_market * 100
        nivel = "alta" if top_pct >= 40 else ("moderada" if top_pct >= 25 else "baja")
        lines.append(
            f"Tu mayor posición, {top_t}, pesa {top_pct:.0f}% del valor del portafolio "
            f"— concentración {nivel}.")

    # Peso en ETFs de income tipo YieldMax (mode_a)
    if classify_map and total_market > 0:
        ym_val = sum((valid[t].get('market_value', 0) or 0)
                     for t, m in classify_map.items() if m == 'mode_a' and t in valid)
        ym_pct = ym_val / total_market * 100
        if ym_pct >= 1:
            lines.append(
                f"El {ym_pct:.0f}% de tu valor está en ETFs de income tipo YieldMax: ahí el "
                f"retorno depende de que los dividendos compensen la erosión de precio, no de "
                f"la apreciación. Evalúalos por retorno total, no por el yield titular.")

    # Balance capital vs income a nivel agregado
    cap = total_market - total_inv
    if total_inc > 0 and cap < 0 and (total_inc + cap) >= 0:
        lines.append(
            f"En conjunto, tus dividendos cobrados (${total_inc:,.0f}) ya cubren la caída de "
            f"precio (${abs(cap):,.0f}): hoy el income es lo que sostiene tu retorno.")

    return {'lines': lines[:4]}


# Factor macro compartido por subyacentes distintos (riesgo de correlación oculta).
UNDERLYING_FACTOR_MAP = {
    'MSTR': 'Bitcoin', 'COIN': 'Bitcoin', 'MARA': 'Bitcoin', 'RIOT': 'Bitcoin',
    'BITX': 'Bitcoin', 'IBIT': 'Bitcoin', 'CLSK': 'Bitcoin',
}


def _ticker_factor(ticker, info=None):
    """Factor macro de un ticker: el subyacente, con los proxies de cripto agrupados en
    'Bitcoin'. None si el subyacente es un índice genérico/mercado o no aplica."""
    info = info if info is not None else load_instruments().get(str(ticker).upper(), {})
    und = (info.get('underlying') or '').strip()
    if not und or und.upper() in ('N/A', 'NA', 'MULTI', 'MERCADO', ''):
        return None
    return UNDERLYING_FACTOR_MAP.get(und.upper(), und)


def build_factor_concentration(results: dict, classify_map: dict = None, min_share_pct: float = 40.0) -> dict:
    """Concentración del INGRESO por factor macro subyacente (riesgo de correlación oculta):
    p.ej. MSTY y CONY se ven como dos posiciones, pero ambas dependen de Bitcoin. Agrupa el
    ingreso forward anual (forward_yield × valor) por factor (subyacente; MSTR/COIN→Bitcoin)
    y devuelve los pesos.

    Devuelve {'factors': [{factor, tickers, annual_income, income_share_pct}], 'top_factor',
    'top_share_pct', 'hidden_correlation': bool}. `hidden_correlation` es True cuando el factor
    dominante pesa ≥`min_share_pct` Y lo componen ≥2 tickers (correlación que se ve diversificada
    pero no lo es). Vacío si no hay activos de income con subyacente conocido.
    """
    instruments = load_instruments()
    by_factor, total = {}, 0.0
    for tk, s in results.items():
        if not isinstance(s, dict) or 'error' in s or s.get('skipped'):
            continue
        fy = s.get('forward_yield') or 0
        mv = s.get('market_value') or 0
        if fy <= 0 or mv <= 0:
            continue
        factor = _ticker_factor(tk, instruments.get(str(tk).upper(), {}))
        if factor is None:
            continue
        ann_income = fy / 100.0 * mv
        d = by_factor.setdefault(factor, {'tickers': [], 'annual_income': 0.0})
        d['tickers'].append(tk)
        d['annual_income'] += ann_income
        total += ann_income
    if total <= 0:
        return {'factors': [], 'top_factor': None, 'top_share_pct': None, 'hidden_correlation': False}
    factors = sorted(
        ({'factor': f, 'tickers': sorted(d['tickers']),
          'annual_income': round(d['annual_income'], 2),
          'income_share_pct': round(d['annual_income'] / total * 100, 1)}
         for f, d in by_factor.items()),
        key=lambda x: x['income_share_pct'], reverse=True)
    top = factors[0]
    return {'factors': factors, 'top_factor': top['factor'], 'top_share_pct': top['income_share_pct'],
            'hidden_correlation': top['income_share_pct'] >= min_share_pct and len(top['tickers']) >= 2}


@st.cache_data(ttl=86400, show_spinner=False)
def get_etf_holdings(ticker: str) -> list:
    """
    Fetches top 10 holdings for an ETF via yFinance.
    Returns list of dicts: {name, symbol, weight, description}
    Falls back gracefully through 3 yfinance paths.
    """
    try:
        t = yf.Ticker(ticker)

        # Path 1: funds_data.top_holdings (yfinance >= 0.2.37)
        try:
            fd = t.funds_data
            top = fd.top_holdings
            if top is not None and not top.empty:
                results = []
                for symbol, row in top.head(10).iterrows():
                    sym = str(symbol)
                    name = row.get('holdingName', sym)
                    weight = float(row.get('holdingPercent', 0))
                    desc = COMPANY_DESCRIPTIONS.get(sym, COMPANY_DESCRIPTIONS.get(name.split()[0] if name else sym, ''))
                    results.append({'symbol': sym, 'name': name, 'weight': weight, 'description': desc})
                return results
        except Exception:
            pass

        # Path 2: info["holdings"]
        try:
            info = t.info
            holdings = info.get('holdings', [])
            if holdings:
                results = []
                for h in holdings[:10]:
                    sym = h.get('symbol', '')
                    name = h.get('holdingName', sym)
                    weight = float(h.get('holdingPercent', 0))
                    desc = COMPANY_DESCRIPTIONS.get(sym, '')
                    results.append({'symbol': sym, 'name': name, 'weight': weight, 'description': desc})
                return results
        except Exception:
            pass

    except Exception as e:
        print(f"get_etf_holdings error for {ticker}: {e}")

    return []


def build_risk_analysis(results: dict, classify_map: dict, total_portfolio_value: float) -> dict:
    """
    Orchestrates full risk analysis.
    Returns structured dict with yieldmax_risk and etf_holdings sections.
    """
    yieldmax_risk = []
    etf_holdings_list = []

    for ticker, mode in classify_map.items():
        if ticker not in results or 'error' in results[ticker]:
            continue

        stats = results[ticker]
        market_val = stats.get('market_value', 0)
        port_pct = (market_val / total_portfolio_value * 100) if total_portfolio_value > 0 else 0

        if mode == 'mode_a':
            profile = get_yieldmax_risk_profile(ticker)
            yieldmax_risk.append({
                'ticker': ticker,
                'underlying': profile['underlying'],
                'name': profile['name'],
                'risk_level': profile['risk'],
                'reason': profile['reason'],
                'market_value': market_val,
                'portfolio_pct': port_pct,
            })
        else:
            holdings = get_etf_holdings(ticker)
            if holdings:
                top3_pct = sum(h['weight'] for h in holdings[:3]) * 100
                etf_holdings_list.append({
                    'ticker': ticker,
                    'top_holdings': holdings,
                    'top3_concentration_pct': top3_pct,
                })

    # Sort YieldMax by portfolio %
    yieldmax_risk.sort(key=lambda x: -x['portfolio_pct'])

    return {
        'yieldmax_risk': yieldmax_risk,
        'etf_holdings': etf_holdings_list,
    }


# ============================================================
# v2.5 — SERIE TEMPORAL: DIVIDENDOS vs CRECIMIENTO
# ============================================================

VALUE_WITHOUT_COST_RATIO = 1.3   # primer dia con costo: valor > costo*ratio => acciones sin costo registrado
LOW_COVERAGE_PCT = 80.0          # cobertura del CSV bajo este % => parcial

# v2.9 — Tolerancias de reconciliación con el income file (segunda fuente).
INCOME_MATCH_TOL_REL = 0.02      # ±2% del mayor de los dos totales
INCOME_MATCH_TOL_ABS = 1.0       # ±$1 (para posiciones pequeñas); se usa max(rel, abs)
INCOME_WINDOW_BUFFER_DAYS = 5    # colchón por desfase ex-div/record/payment (YieldMax semanal)


def assess_ticker_quality(results: dict, ticker: str) -> dict:
    """Evalua la calidad de datos de UN ticker. Fuente unica de verdad para toda la app.

    Devuelve {'level': 'ok'|'partial'|'reconciled'|'unreliable', 'flags': [...], 'coverage_pct': float|None,
              'reason': str, 'action': str}.
    'reconciled' = costo/acciones tomados de la captura del broker (cabecera confiable; timeline parcial).
    'unreliable' = el costo base esta incompleto y NO se reconcilio -> no confiar en metricas de costo.
    'partial' = cobertura baja del CSV pero costo coherente. 'ok' = confiable.
    """
    s = results.get(ticker, {}) or {}
    flags = []
    cov = s.get('csv_coverage_pct')

    if s.get('reconciled_from_snapshot'):
        _f = s.get('reconciled_fields') or []
        return {
            'level': 'reconciled',
            'flags': ['reconciled_' + x for x in _f] or ['reconciled'],
            'coverage_pct': cov,
            'reason': ("Acciones y/o costo tomados de tu captura del broker (el CSV no traía el "
                       "historial completo). El valor, ROI y ROC de cabecera son correctos; la línea "
                       "de tiempo histórica de esta posición es parcial."),
            'action': "",
        }

    if s.get('history_incomplete'):
        flags.append('sells_exceed_buys')

    dt = s.get('daily_trend')
    if dt is not None and len(dt) > 0 and {'Invested Capital', 'User Total Value'}.issubset(dt.columns):
        costed = dt[dt['Invested Capital'] > 0]
        if costed.empty:
            flags.append('no_cost_recorded')
        else:
            first = costed.iloc[0]
            if first['User Total Value'] > first['Invested Capital'] * VALUE_WITHOUT_COST_RATIO:
                flags.append('value_without_cost')

    if s.get('splits_detected'):
        flags.append('splits_detected')
    if cov is not None and cov < LOW_COVERAGE_PCT:
        flags.append('low_coverage')

    cost_broken = {'sells_exceed_buys', 'value_without_cost', 'no_cost_recorded'} & set(flags)
    # csv_coverage_pct mide la vida del FONDO, no de la posición: un fondo viejo con la posición
    # abierta hace poco pero documentada al 100% marca % bajo aunque el historial esté completo.
    # Por eso 'low_coverage' solo degrada a 'partial' si además hay una señal real de historial
    # truncado (history_incomplete / value_without_cost); por sí solo no es evidencia de nada.
    low_cov_meaningful = 'low_coverage' in flags and (
        s.get('history_incomplete') or 'value_without_cost' in flags)
    if cost_broken:
        level = 'unreliable'
        reason = ("El historial de compras de este ticker en el CSV esta incompleto "
                  "(tienes acciones sin costo registrado o vendiste mas de lo que figura comprado). "
                  "Esto no solo afecta el ROI/%: el numero de acciones y el valor de mercado "
                  "calculados tambien pueden diferir de los de tu broker.")
        action = (f"Exporta el historial COMPLETO de {ticker} desde la apertura de la posicion "
                  "y vuelve a subir el archivo. Mientras tanto no compares 1:1 con tu broker "
                  "las acciones, el valor ni el ROI de este ticker.")
    elif low_cov_meaningful:
        level = 'partial'
        reason = (f"El CSV cubre solo ~{cov:.0f}% de la vida del fondo y además falta parte del "
                  "historial de la posición; las métricas de largo plazo (CAGR, drawdown) pueden "
                  "quedar incompletas.")
        action = f"Si quieres precisión total, exporta {ticker} desde la apertura de la posición."
    else:
        level = 'ok'
        reason = ""
        action = ""

    return {'level': level, 'flags': flags, 'coverage_pct': cov, 'reason': reason, 'action': action}


def assess_data_quality(results: dict, classify_map: dict = None) -> dict:
    """Evalua todos los tickers (no skipped). Devuelve {ticker: assess_ticker_quality(...)}.

    Si se pasa classify_map, solo evalua los que esten clasificados (mode_a/mode_b/mode_skip presentes).
    """
    out = {}
    for t, s in results.items():
        if not isinstance(s, dict) or s.get('skipped') or 'error' in s:
            continue
        out[t] = assess_ticker_quality(results, t)
    return out


def _cost_incomplete(results: dict, ticker: str) -> bool:
    """True si el ticker debe EXCLUIRSE del time-series del comparativo (su línea de tiempo es parcial).

    Aplica a 'unreliable' (costo incompleto sin reconciliar) y a 'reconciled' (cabecera corregida
    desde la captura pero timeline histórica parcial). Fuente única con el panel de la app.
    """
    return assess_ticker_quality(results, ticker)['level'] in ('unreliable', 'reconciled')


def _csv_dividends_in_window(history_df, start=None, end=None) -> float:
    """Suma el dividendo BRUTO declarado en el CSV, opcionalmente restringido a una ventana.

    Misma base que el income file del broker (que reporta dividendo bruto, antes de la
    retención NRA que va en filas aparte): suma las filas 'Reinvest Dividend' (monto
    bruto reinvertido) y los dividendos en efectivo ('Qualified/Cash Dividend'). NO suma
    las filas 'Reinvest Shares' (esas son la COMPRA neta de acciones tras impuesto, que
    subestima el bruto) ni las 'NRA Tax Adj'. Los dividendos son dólares, no se ajustan
    por split.
    """
    if history_df is None or len(history_df) == 0:
        return 0.0
    df = history_df
    if 'Date' in df.columns and (start is not None or end is not None):
        d = pd.to_datetime(df['Date'], errors='coerce')
        if start is not None:
            df = df[d >= start]
            d = pd.to_datetime(df['Date'], errors='coerce')
        if end is not None:
            df = df[d <= end]
    total = 0.0
    for _, row in df.iterrows():
        action = str(row.get('Action', '')).lower()
        amount = _clean_money(row.get('Amount', 0))
        if pd.isna(amount):
            amount = 0.0
        is_drip = 'reinvest' in action or 'reinversión' in action or 'drip' in action
        # 'Reinvest Shares' = compra de acciones (monto neto post-tax) -> omitir.
        if is_drip and ('share' in action or 'acciones' in action):
            continue
        # 'Reinvest Dividend' (bruto) o dividendo en efectivo -> contar.
        if 'dividend' in action or 'dividendo' in action:
            total += amount
    return total


def _dividend_events(history_df) -> 'pd.Series':
    """Serie de dividendo BRUTO por fecha de pago (un valor por día con dividendo).

    Misma base que `_csv_dividends_in_window`: cuenta filas 'dividend'/'dividendo'
    (incluye 'Reinvest Dividend' bruto y dividendo en efectivo) y omite 'Reinvest Shares'
    (compra neta post-impuesto). Índice = fecha normalizada, valor = monto del pago (positivo).
    Sirve para derivar frecuencia, último pago y TTM sin depender del income file del broker.
    """
    if history_df is None or len(history_df) == 0 or 'Date' not in history_df.columns:
        return pd.Series(dtype=float)
    rows = []
    for _, row in history_df.iterrows():
        action = str(row.get('Action', '')).lower()
        if 'dividend' not in action and 'dividendo' not in action:
            continue
        is_drip = 'reinvest' in action or 'reinversión' in action or 'drip' in action
        if is_drip and ('share' in action or 'acciones' in action):
            continue
        amt = _clean_money(row.get('Amount', 0))
        if pd.isna(amt) or amt == 0:
            continue
        rows.append((pd.to_datetime(row.get('Date'), errors='coerce'), abs(float(amt))))
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows, columns=['Date', 'Amount']).dropna(subset=['Date'])
    if df.empty:
        return pd.Series(dtype=float)
    df['Date'] = df['Date'].dt.normalize()
    return df.groupby('Date')['Amount'].sum().sort_index()


def _annualized_cagr(close, days=None):
    """CAGR de precio anualizado (%) sobre una serie de cierres. `days`=None usa toda la
    serie; `days`=365 usa la ventana de los últimos 12 meses. Defensivo → None si no aplica."""
    try:
        c = close.dropna()
        if len(c) < 5:
            return None
        if days is not None:
            c = c[c.index >= c.index[-1] - pd.Timedelta(days=days)]
            if len(c) < 5:
                return None
        p0 = float(c.iloc[0]); p1 = float(c.iloc[-1])
        yrs = max((c.index[-1] - c.index[0]).days / 365.25, 0.05)
        return round(((p1 / p0) ** (1 / yrs) - 1) * 100, 2) if p0 > 0 else None
    except Exception:
        return None


def _simulate_hold_value(price_s, div_s, flow_s):
    """Simula invertir `flow_s` (flujo de capital diario) en un instrumento con precio `price_s`
    y dividendos `div_s` reinvertidos — el 'qué hubiera pasado si tenías el subyacente directo'.
    Mismo patrón que el benchmark VOO. Series alineadas al mismo índice. Devuelve el valor final."""
    shares = 0.0
    last_val = 0.0
    for date in price_s.index:
        vp = price_s.loc[date]
        vp = float(vp) if not pd.isna(vp) else 0.0
        if vp > 0:
            shares += float(flow_s.get(date, 0.0) or 0.0) / vp
            dv = float(div_s.get(date, 0.0) or 0.0) if div_s is not None else 0.0
            if dv > 0 and shares > 0:
                shares += (dv * shares) / vp
        shares = max(shares, 0.0)
        last_val = shares * vp
    return last_val


def forward_realized_yield(history_df, market_value, today=None) -> dict:
    """Forward yield (lo que ANUNCIAN) vs realized yield (lo que COBRASTE), ambos sobre el
    valor de mercado actual.

      - forward_yield  = último pago × frecuencia anual / valor de mercado × 100
        (lo que las páginas y el broker muestran: asume que el último pago se repite plano).
      - realized_yield = dividendos cobrados en los últimos 12 meses / valor de mercado × 100
        (lo que de verdad entró a tu bolsillo, reconstruido del CSV).

    Devuelve {forward_yield, realized_yield, payments_per_year, last_payment, ttm_income, stale}.
    `forward_yield` es None cuando el último pago es RANCIO (la posición dejó de pagar — vendida
    o transferida fuera, faltan varios pagos): anualizar un pago viejo sobre el valor actual da
    un yield inflado y falso (caso real: QYLD con último pago hace ~600 días → 67% espurio). El
    `realized_yield` (TTM real) sí se mantiene. Todo None si falta historial o valor de mercado.
    """
    out = {'forward_yield': None, 'realized_yield': None, 'payments_per_year': None,
           'last_payment': None, 'ttm_income': None, 'stale': False}
    ev = _dividend_events(history_df)
    if ev.empty or not market_value or market_value <= 0:
        return out
    today = pd.Timestamp.today().normalize() if today is None else pd.Timestamp(today).normalize()

    dates = list(ev.index[-12:])
    gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates)) if (dates[i] - dates[i - 1]).days > 0]
    median_gap = sorted(gaps)[len(gaps) // 2] if gaps else 30
    ppy = max(1, round(365 / median_gap)) if median_gap > 0 else 12

    last_payment = float(ev.iloc[-1])
    ttm = float(ev[ev.index >= today - pd.Timedelta(days=365)].sum())
    out['payments_per_year'] = int(ppy)
    out['last_payment'] = round(last_payment, 4)
    out['ttm_income'] = round(ttm, 2)
    out['realized_yield'] = round(ttm / market_value * 100, 2)

    # Rancio: el último pago es más viejo que ~varios intervalos esperados → la posición dejó de
    # pagar (vendida/transferida). No proyectamos un forward inflado sobre ese pago muerto.
    days_since_last = (today - ev.index[-1]).days
    if days_since_last > max(2.5 * median_gap, 45):
        out['stale'] = True
        return out                      # forward_yield queda None
    out['forward_yield'] = round(last_payment * ppy / market_value * 100, 2)
    return out


# Holgura para comparar el yield titular contra el mecanismo: absoluta (puntos %) o relativa
# (fracción del titular), la mayor. Los YieldMax corren 30-85%, así que una banda solo absoluta
# sería demasiado estricta para los altos y demasiado laxa para los bajos.
ADVERTISED_ABS_TOL = 5.0
ADVERTISED_REL_TOL = 0.15


def audit_advertised_yield(advertised, forward, realized):
    """Audita el yield TITULAR que publica YieldMax contra la realidad reconstruida del CSV.

    3 vías (todas en % anual sobre el valor de mercado actual):
      advertised : lo que YieldMax PUBLICA (scrapeado, `advertised_yield`).
      forward    : su propio mecanismo HOY = último pago real × frecuencia / valor (`forward_yield`).
      realized   : lo que de verdad cobraste = dividendos TTM / valor (`realized_yield`).

    Devuelve {verdict, label, advertised, forward, realized, gap_fwd, gap_real} donde:
      verdict='match'   → titular ≈ mecanismo: anuncian lo que su fórmula paga (honesto en la forma).
      verdict='ahead'   → titular ≫ mecanismo: el titular va por delante de lo que pagan ahora.
      verdict='behind'  → titular ≪ mecanismo: el titular va por debajo (poco común).
      verdict='unknown' → falta el titular (sin scrape) o el mecanismo (posición rancia/sin pagos).
    `gap_real` (titular − realizado) es el dato educativo: aun siendo honesto en la forma, el
    titular casi siempre supera lo que de verdad entró a tu bolsillo.
    """
    def _f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None
    a, fwd, rz = _f(advertised), _f(forward), _f(realized)
    gap_fwd = (a - fwd) if (a is not None and fwd is not None) else None
    gap_real = (a - rz) if (a is not None and rz is not None) else None
    if a is None or fwd is None:
        verdict, label = 'unknown', 'Sin dato suficiente para auditar el titular'
    else:
        tol = max(ADVERTISED_ABS_TOL, ADVERTISED_REL_TOL * a)
        if abs(gap_fwd) <= tol:
            verdict, label = 'match', 'Anuncian lo que su mecanismo paga'
        elif gap_fwd > 0:
            verdict, label = 'ahead', 'El titular va por delante de lo que pagan ahora'
        else:
            verdict, label = 'behind', 'El titular va por debajo de lo que pagan ahora'
    return {'verdict': verdict, 'label': label, 'advertised': a, 'forward': fwd,
            'realized': rz, 'gap_fwd': gap_fwd, 'gap_real': gap_real}


def _roc_pct_for(ticker, stats):
    """% ROC representativo del fondo: el ponderado de los avisos 19a si existe, si no el
    estimado del broker (`roc_percent`)."""
    info = load_roc_19a().get(str(ticker).upper()) or {}
    w = info.get('weighted_pct')
    if w is not None:
        try:
            return float(w)
        except (TypeError, ValueError):
            pass
    return stats.get('roc_percent')


def build_hoja_excel(results, classify_map=None):
    """Filas de la sección educativa 'Hoja Excel' (solo fondos de income): el método tradicional
    de la hoja de cálculo —con sus errores— contra la vista honesta corregida.

    Método tradicional (replicado tal cual, a propósito con su sesgo):
      total_inv_naive = inversión + dividendos  → trata el retorno como capital aportado (infla).

    Vista honesta:
      total_return = valor de mercado + dividendos en efectivo − inversión  (DRIP ya está en el
      valor de mercado, por eso NO se suma; mismo criterio que la tarjeta de Retorno Total).
      dividendos: bruto = neto + impuesto NRA  (total_dividends ya viene neto de NRA).
      nav_health = classify_roc_health(...)  → veredicto honesto por tendencia del NAV.
      audit = audit_advertised_yield(...)    → titular vs mecanismo vs realizado.

    Devuelve {'rows': [...], 'totals': {...}} ordenado por valor de mercado desc.
    """
    import datetime as _dt
    rows = []
    items = [(t, s) for t, s in (results or {}).items()
             if isinstance(s, dict) and 'error' not in s
             and (classify_map is None or classify_map.get(t) == 'mode_a')]
    roc19a = load_roc_19a()
    for tk, s in items:
        pocket = s.get('pocket_investment') or 0.0
        net_div = s.get('total_dividends') or 0.0          # drip + cash, ya neto de NRA
        nra = s.get('withheld_tax_total') or 0.0
        gross_div = net_div + nra
        mv = s.get('market_value') or 0.0
        cash_div = s.get('dividends_collected_cash') or 0.0

        inicio = None
        hist = s.get('history')
        try:
            if hist is not None and len(hist) and 'Date' in hist.columns:
                inicio = pd.to_datetime(hist['Date']).min().date().isoformat()
        except Exception:
            inicio = None

        # Último dividendo: promedio de los últimos 4 pagos, para suavizar la volatilidad
        # semanal (un solo pago puede ser atípico). Cae a `last_payment` si no hay historial.
        last_div_avg = s.get('last_payment')
        try:
            _ev = _dividend_events(hist)
            if _ev is not None and len(_ev):
                last_div_avg = float(_ev.tail(4).mean())
        except Exception:
            pass

        total_inv_naive = pocket + net_div                 # la fórmula defectuosa
        total_return = mv + cash_div - pocket              # la honesta
        total_return_pct = (total_return / pocket * 100) if pocket > 0 else None

        roc_pct = _roc_pct_for(tk, s)
        price_cagr = (s.get('price_cagr_recent') if s.get('price_cagr_recent') is not None
                      else s.get('price_cagr'))
        asof_days = None
        _asof = (roc19a.get(str(tk).upper()) or {}).get('asof')
        if _asof:
            try:
                asof_days = (_dt.date.today() - _dt.date.fromisoformat(_asof)).days
            except Exception:
                asof_days = None
        nav_health = classify_roc_health(roc_pct, price_cagr, total_return_pct=total_return_pct,
                                         history_days=s.get('price_history_days'),
                                         roc_asof_days=asof_days,
                                         underlying_cagr=s.get('underlying_cagr_recent'))
        audit = audit_advertised_yield(s.get('advertised_yield'), s.get('forward_yield'),
                                       s.get('realized_yield'))
        # ROC en dólares = % de retorno de capital × distribución bruta. NO es una resta de
        # costos (Inv+Reinv−Costo): es la porción de lo distribuido que era tu propio capital
        # de vuelta. Sirve para «desinflar» el total_inv_naive en la revelación de la trampa.
        roc_dollars = (roc_pct / 100.0 * gross_div) if roc_pct is not None else None
        rows.append({
            'ticker': tk, 'inicio': inicio, 'advertised': s.get('advertised_yield'),
            'investment': pocket, 'dividends_net': net_div, 'dividends_gross': gross_div,
            'nra_tax': nra, 'total_inv_naive': total_inv_naive, 'market_value': mv,
            'last_div': s.get('last_payment'), 'last_div_avg': last_div_avg,
            'total_return': total_return, 'total_return_pct': total_return_pct,
            'roc_pct': roc_pct, 'roc_dollars': roc_dollars,
            'yield_on_cost': s.get('yield_on_cost'), 'realized_yield': s.get('realized_yield'),
            'forward_yield': s.get('forward_yield'), 'nav_health': nav_health, 'audit': audit,
        })

    rows.sort(key=lambda r: -(r['market_value'] or 0))
    totals = {k: sum((r[k] or 0) for r in rows) for k in
              ('investment', 'dividends_net', 'dividends_gross', 'nra_tax',
               'total_inv_naive', 'market_value', 'total_return', 'roc_dollars')}
    totals['total_return_pct'] = (totals['total_return'] / totals['investment'] * 100
                                  if totals['investment'] > 0 else None)
    return {'rows': rows, 'totals': totals}


# Frecuencias estándar (pagos/año) → etiqueta legible. Se mapea por cercanía.
_CADENCE_STD = [(52, 'semanal'), (26, 'quincenal'), (12, 'mensual'),
                (4, 'trimestral'), (2, 'semestral'), (1, 'anual')]


def _cadence_label(ppy):
    """Etiqueta la frecuencia de pago más cercana a `ppy` (pagos/año)."""
    if not ppy:
        return 'desconocida'
    return min(_CADENCE_STD, key=lambda x: abs(x[0] - ppy))[1]


def _ppy_from_dates(dates):
    """Pagos/año a partir de la mediana de gaps (días) entre fechas de pago."""
    gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))
            if (dates[i] - dates[i - 1]).days > 0]
    if not gaps:
        return None
    g = sorted(gaps)[len(gaps) // 2]
    return max(1, round(365 / g)) if g > 0 else None


def detect_cadence_change(history_df, window=6):
    """Detecta cambios de frecuencia de pago (p.ej. mensual → semanal) comparando la
    cadencia de la ventana reciente vs la anterior. Devuelve None si no hay pagos
    suficientes, o {recent_ppy, old_ppy, recent_label, old_label, changed, note}.

    Importante para no comparar peras con manzanas: un pago semanal de $28 no equivale a
    uno mensual de $200. El yield realizado (TTM) es inmune (suma 12m reales); solo el
    forward depende de acertar la frecuencia actual, que la mediana móvil ya resuelve.
    """
    ev = _dividend_events(history_df)
    dts = list(ev.index)
    if len(dts) < 6:                       # mínimo: dos ventanas de 3 pagos
        return None
    n = min(window, len(dts) // 2)
    # Cadencia actual (últimos n) vs la del inicio del registro (primeros n): así se detecta
    # "antes pagaba mensual, ahora semanal" aunque el cambio haya sido hace varios pagos.
    recent, older = dts[-n:], dts[:n]
    if len(recent) < 3 or len(older) < 3:
        return None
    rp, op = _ppy_from_dates(recent), _ppy_from_dates(older)
    if rp is None or op is None:
        return None
    rl, ol = _cadence_label(rp), _cadence_label(op)
    changed = rl != ol
    note = (f"Cambió su frecuencia de pago: {ol} → {rl}." if changed
            else f"Frecuencia de pago estable ({rl}).")
    return {'recent_ppy': rp, 'old_ppy': op, 'recent_label': rl,
            'old_label': ol, 'changed': changed, 'note': note}


# ── Módulo fiscal NRA (no-residente): tasa por país × escudo del ROC ──────────
# Tasas de retención sobre dividendos de fuente EE.UU. para residentes de cada país
# (tablas IRS / tratados). (tasa_%, ¿tiene_tratado?). Default 30% sin tratado.
NRA_DEFAULT_RATE = 30.0
NRA_COUNTRY_RATES = {
    'México':      (10.0, True),
    'Chile':       (15.0, True),
    'Colombia':    (30.0, False),
    'Perú':        (30.0, False),
    'Argentina':   (30.0, False),
    'Brasil':      (30.0, False),
    'Otros LATAM': (30.0, False),
}


def nra_tax_breakdown(country, roc_fraction_pct, nominal_income=None):
    """Módulo fiscal NRA: retención REAL sobre dividendos de fuente EE.UU. con la
    'Ecuación Nugget': `efectiva = tasa_país × (1 − ROC)`. El Retorno de Capital no es
    dividendo gravable, así que actúa como escudo fiscal en el presente.

    Devuelve {country, base_rate, has_treaty, roc_fraction, effective_rate, lines[], audit_note}.
    `lines` cumple los 4 requisitos del spec (tratado, ROC=escudo, costo base, contraste
    nominal vs efectivo). SIEMPRE acompañar con `audit_note` al renderizar.

    NOTA (v2, diferido): (1 − ROC) es una aproximación ligeramente CONSERVADORA — estrictamente,
    además del ROC, las ganancias de capital de LARGO plazo de la distribución tampoco sufren
    retención NRA, así que la fracción gravable real puede ser aún menor. Hoy roc_19a.yaml solo
    guarda `roc_pct`; el desglose completo (ordinary / ST cap gains / LT cap gains / ROC) requiere
    extender fetch_roc_19a.py y el esquema del YAML. Ver follow-up.
    """
    base, treaty = NRA_COUNTRY_RATES.get(country, (NRA_DEFAULT_RATE, False))
    roc = max(0.0, min(100.0, float(roc_fraction_pct or 0)))
    effective = round(base * (1 - roc / 100.0), 2)

    lines = []
    if treaty:
        lines.append(f"Vives en {country}: por el tratado fiscal con EE.UU., la retención base "
                     f"sobre dividendos es {base:.0f}% (no el 30% general).")
    else:
        lines.append(f"{country} no tiene tratado fiscal vigente con EE.UU., así que aplica la "
                     f"tasa base del {base:.0f}% por defecto sobre dividendos.")
    if roc > 0:
        lines.append(f"De este fondo, ~{roc:.0f}% de lo que reparte es Retorno de Capital (ROC): "
                     f"NO es un dividendo gravable, es tu propio dinero que te devuelven. Actúa "
                     f"como escudo fiscal — esa parte hoy no paga retención.")
        lines.append("Ojo amable: ese Retorno de Capital baja tu costo de compra de la acción. No "
                     "es gratis para siempre — el impuesto se pospone hasta que vendas (ahí pagarás "
                     "más ganancia de capital).")
    if nominal_income and nominal_income > 0:
        nom_amt = nominal_income * base / 100.0
        eff_amt = nominal_income * effective / 100.0
        lines.append(f"Creías que te quitaban el {base:.0f}% (${nom_amt:,.0f}); en realidad, con el "
                     f"escudo del ROC, la retención efectiva es ~{effective:.1f}% (${eff_amt:,.0f}). "
                     f"Diferencia a tu favor: ${nom_amt - eff_amt:,.0f}.")
    else:
        lines.append(f"Creías que te quitaban el {base:.0f}%; con el escudo del ROC, la retención "
                     f"efectiva real es ~{effective:.1f}%.")

    audit = ("Cálculos basados en las tablas vigentes del IRS y PwC. La legislación fiscal "
             "internacional cambia y tu bróker puede retener distinto en la fuente: confirma "
             "siempre con tu bróker o un asesor fiscal.")
    return {'country': country, 'base_rate': base, 'has_treaty': treaty,
            'roc_fraction': round(roc, 1), 'effective_rate': effective,
            'lines': lines, 'audit_note': audit}


def estimate_roc_refund(gross, withheld, roc_pct, base_rate=0.30):
    """Cuánto de la retención NRA real podría volver con la reclasificación anual (19a).

    `retencion_justa = base_rate × bruto × (1 − roc_pct/100)`; la devolución es la
    diferencia entre lo retenido de verdad y esa retención justa, acotada a [0, withheld].
    Es una ESTIMACIÓN (el % 19a puede variar; lo definitivo llega en el 1042-S).
    """
    if gross is None or withheld is None or withheld <= 0:
        return {'fair_withholding': 0.0, 'refund': 0.0, 'refund_pct': 0.0}
    gross = max(0.0, float(gross))
    withheld = max(0.0, float(withheld))
    roc = max(0.0, min(100.0, float(roc_pct or 0)))
    fair = max(0.0, base_rate * gross * (1 - roc / 100.0))
    refund = max(0.0, min(withheld, withheld - fair))
    refund_pct = (refund / withheld * 100.0) if withheld > 0 else 0.0
    return {'fair_withholding': round(fair, 2), 'refund': round(refund, 2),
            'refund_pct': round(refund_pct, 1)}


def estimate_roc_refund_by_year(gross_by_year, withheld_by_year, ticker, base_rate=0.30,
                                 roc_fallback_pct=None):
    """`estimate_roc_refund` desglosado por año calendario — la reclasificación del broker
    opera por año fiscal, así que cada año usa el %ROC promedio de los avisos 19a publicados
    ESE año (no el histórico completo del fondo). Reutiliza `estimate_roc_refund` por año,
    no duplica la fórmula.

    Args:
        gross_by_year / withheld_by_year: dict {año -> monto}, del mismo ticker (ver
            `dividends_gross_by_year` / `withheld_by_year` en el dict de resultados).
        roc_fallback_pct: %ROC a usar en años sin avisos 19a en la ventana (normalmente el
            `roc_percent` ya calculado del holder para ese ticker).

    Devuelve dict {año: {'fair_withholding', 'refund', 'refund_pct', 'roc_pct_usado'}} más
    la clave 'total' con los mismos tres primeros campos agregados sobre todos los años.
    """
    info = load_roc_19a().get(str(ticker).upper()) or {}
    roc_by_year = defaultdict(list)
    for rowp in (info.get('per_distribution') or []):
        try:
            _y = pd.Timestamp(rowp['date']).year
            roc_by_year[_y].append(float(rowp['roc_pct']))
        except Exception:
            continue

    years = sorted(set(gross_by_year or {}) | set(withheld_by_year or {}))
    out = {}
    tot_fair = tot_refund = tot_withheld = 0.0
    for y in years:
        gross = (gross_by_year or {}).get(y, 0.0) or 0.0
        withheld = (withheld_by_year or {}).get(y, 0.0) or 0.0
        vals = roc_by_year.get(y)
        roc_pct = (sum(vals) / len(vals)) if vals else (roc_fallback_pct if roc_fallback_pct
                                                          is not None else 0.0)
        res = estimate_roc_refund(gross, withheld, roc_pct, base_rate=base_rate)
        out[y] = dict(res, roc_pct_usado=round(roc_pct, 2))
        tot_fair += res['fair_withholding']
        tot_refund += res['refund']
        tot_withheld += withheld
    total_refund_pct = round(tot_refund / tot_withheld * 100.0, 1) if tot_withheld > 0 else 0.0
    out['total'] = {'fair_withholding': round(tot_fair, 2), 'refund': round(tot_refund, 2),
                     'refund_pct': total_refund_pct}
    return out


def _ticker_roc_fraction(ticker, results=None):
    """Fracción ROC (%) de un ticker para el módulo fiscal (proyecciones, Monte Carlo,
    retención NRA forward). Preferencia: (1) promedio de los ÚLTIMOS 12 avisos 19a
    per_distribution, ordenados por fecha desc (mínimo 3 avisos disponibles, para no fiarse
    de 1-2 datos); (2) `weighted_pct` histórico completo del fondo; (3) `roc_percent` ya
    calculado del holder en `results`; (4) 0. Acotada a [0, 100].

    El histórico ponderado sobreestima el escudo fiscal forward cuando el fondo viene
    reduciendo su ROC recientemente (ej. MSTY: weighted ~72% vs. promedio de los últimos
    12 avisos ~48%, 2026-07-13) — por eso se prefiere el dato reciente para proyectar hacia
    adelante. El bloque retrospectivo de Salud del NAV (`build_roc_aware_withholding`) NO usa
    esta función: ahí interesa el % de CADA distribución de la ventana, no un promedio forward.
    """
    info = load_roc_19a().get(str(ticker).upper()) or {}
    dated = []
    for rowp in (info.get('per_distribution') or []):
        try:
            dated.append((pd.Timestamp(rowp['date']), float(rowp['roc_pct'])))
        except Exception:
            continue
    if len(dated) >= 3:
        dated.sort(key=lambda dp: dp[0], reverse=True)
        recent = dated[:12]
        try:
            avg = sum(v for _, v in recent) / len(recent)
            return max(0.0, min(100.0, float(avg)))
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    wpct = info.get('weighted_pct')
    if wpct is not None:
        try:
            return max(0.0, min(100.0, float(wpct)))
        except (TypeError, ValueError):
            pass
    if results and isinstance(results.get(ticker), dict):
        rp = results[ticker].get('roc_percent')
        if rp is not None:
            try:
                return max(0.0, min(100.0, float(rp)))
            except (TypeError, ValueError):
                pass
    return 0.0


def withheld_tax_total(history_df) -> float:
    """Retención de impuesto NETA REAL registrada en el CSV (retenciones − reembolsos), ≥0.

    Schwab deja la retención en filas aparte ('NRA Tax Adj') que sobreviven en el historial;
    se detectan por palabra clave en la columna Action. (En IB la retención 'Foreign Tax
    Withholding' ya viene plegada como dividendo negativo durante el parseo, así que ahí el
    dividendo del CSV ya es neto y esta función devolverá 0.) Sirve para mostrar la tasa
    efectiva real cuando el dato existe, en vez de la tasa asumida.

    NETEA POR SIGNO: en el CSV la retención es un monto NEGATIVO (sale efectivo) y un
    reembolso/reclasificación (p.ej. la devolución de la porción ROC) es POSITIVO. Antes se
    sumaba `abs()` de todas las filas de impuesto, de modo que un reembolso se contaba como
    MÁS retención (bug: $105 retenidos + $75 devueltos → reportaba $180 en vez de $30 neto).
    Ahora la retención neta = −Σ(montos con signo), acotada a ≥0. La detección/exhibición del
    reembolso como movimiento propio vive aparte (objeto fiscal único, ver estimate_roc_refund).
    """
    if history_df is None or len(history_df) == 0 or 'Action' not in history_df.columns:
        return 0.0
    signed = 0.0                       # + reembolsos, − retenciones (tal cual el CSV)
    for _, row in history_df.iterrows():
        action = str(row.get('Action', '')).lower()
        is_tax = ('nra tax' in action or 'tax adj' in action or 'withholding' in action
                  or 'foreign tax' in action or 'retención' in action or 'retencion' in action)
        if not is_tax:
            continue
        amt = _clean_money(row.get('Amount', 0))
        if pd.isna(amt):
            continue
        signed += float(amt)
    return round(max(0.0, -signed), 2)  # retención neta soportada (≥0)


def withheld_tax_total_by_year(history_df) -> dict:
    """Como `withheld_tax_total` pero agrupada por año calendario de la fila (`Date`).

    Netea por signo dentro de cada año (retenciones − reembolsos), acotado a ≥0, igual que
    `withheld_tax_total`; sin reembolsos la suma de todos los años cuadra con esa función.

    OJO con el supuesto de la reclasificación: opera por año fiscal, PERO en los casos reales
    observados la devolución de la porción ROC NO aparece como movimiento en el broker (ni un
    solo crédito 'NRA Tax Adj' positivo en >1 año de historial). Por eso la devolución se
    ESTIMA (`estimate_roc_refund_by_year`), no se lee de aquí: es una recuperación teórica que
    el inversor tendría que reclamar (1040-NR), no un reembolso automático garantizado.
    """
    out = {}
    if history_df is None or len(history_df) == 0 or 'Action' not in history_df.columns:
        return out
    signed = {}                        # por año: + reembolsos, − retenciones (tal cual el CSV)
    for _, row in history_df.iterrows():
        action = str(row.get('Action', '')).lower()
        is_tax = ('nra tax' in action or 'tax adj' in action or 'withholding' in action
                  or 'foreign tax' in action or 'retención' in action or 'retencion' in action)
        if not is_tax:
            continue
        amt = _clean_money(row.get('Amount', 0))
        if pd.isna(amt):
            continue
        y = _row_year(row.get('Date'))
        if y is None:
            continue
        signed[y] = signed.get(y, 0.0) + float(amt)
    for y, s in signed.items():
        out[y] = round(max(0.0, -s), 2)  # retención neta del año (≥0)
    return out


def observed_tax_refund_by_year(history_df) -> dict:
    """Reembolsos de retención NRA REALES ya acreditados en el CSV, por año calendario.

    Espejo POSITIVO de `withheld_tax_total_by_year`: cuando el bróker reclasifica una
    distribución como ROC (no gravable) y devuelve la retención cobrada de más, ese crédito
    aparece como una fila de impuesto con monto POSITIVO (p. ej. una 'NRA Tax Adj' positiva en
    Schwab, o un 'Foreign Tax Withholding' positivo en IB). Sirve para distinguir en la UI
    "ya te devolvieron $X" (dato real) de "pendiente" (estimado).

    Limitación conocida: en IB los 'Foreign Tax Withholding' —negativos y positivos— se pliegan
    como dividendo durante el parseo (`action_map`), así que ahí esta función devuelve {} y el
    reembolso IB queda absorbido en el dividendo neto (pendiente: separarlo, traspaso 2026-07-14).
    """
    out = {}
    if history_df is None or len(history_df) == 0 or 'Action' not in history_df.columns:
        return out
    for _, row in history_df.iterrows():
        action = str(row.get('Action', '')).lower()
        is_tax = ('nra tax' in action or 'tax adj' in action or 'withholding' in action
                  or 'foreign tax' in action or 'retención' in action or 'retencion' in action)
        if not is_tax:
            continue
        amt = _clean_money(row.get('Amount', 0))
        if pd.isna(amt) or float(amt) <= 0:      # solo reembolsos (montos positivos)
            continue
        y = _row_year(row.get('Date'))
        if y is None:
            continue
        out[y] = round(out.get(y, 0.0) + float(amt), 2)
    return out


# ============================================================
# v3.0 — PROYECCIÓN A FUTURO (inspirada en calculadoras DRIP, con guardarraíl de realismo)
# ============================================================

PROJ_DEFAULTS = {
    'horizon_years': 5,
    'monthly_contribution': 0.0,
    'drip': True,
    'tax_rate_pct': 0.0,
    'dividend_growth_pct': 0.0,     # crecimiento anual del dividendo (ETFs de dividendo)
    'price_appreciation_pct': 0.0,  # apreciación anual del precio (ETFs de crecimiento)
    'yieldmax_decay_fallback_pct': -10.0,  # decaimiento anual si no hay CAGR observado
    'income_goal_monthly': None,    # hito de ingreso mensual (objetivo)
    'upside_capture': 0.5,          # YieldMax: fracción de la SUBIDA del subyacente que captura
    'downside_capture': 1.0,        # YieldMax: fracción de la CAÍDA del subyacente que toma
}


def _yieldmax_nav_from_underlying(scenario_return, underlying_obs, fund_obs,
                                  upside_capture=0.5, downside_capture=1.0):
    """Proyecta el retorno anual de NAV de un YieldMax a partir de un escenario del subyacente
    (p.ej. '¿y si MSTR/Bitcoin se recupera +30%?'), con captura ASIMÉTRICA: toma casi toda la
    caída (`downside_capture`≈1) pero poca de la subida (`upside_capture`≈0.5), más un 'drag'
    estructural (comisiones + erosión por ROC) calibrado al punto observado real
    (`underlying_obs` → `fund_obs`). Devuelve % anual o None si falta el punto de calibración.

    Modelo: cap(R) = downside·min(R,0) + upside·max(R,0);  drag = cap(underlying_obs) − fund_obs;
    NAV(escenario) = cap(scenario_return) − drag. Así el escenario base (= observado) reproduce
    el comportamiento real, y un escenario alcista sube el fondo solo parcialmente (techo + drag).
    """
    if underlying_obs is None or fund_obs is None:
        return None

    def cap(r):
        return downside_capture * min(r, 0.0) + upside_capture * max(r, 0.0)

    drag = cap(underlying_obs) - fund_obs
    return round(cap(scenario_return) - drag, 2)


def _simulate_forward(shares0, price0, fwd_yield_pct, months, monthly_contribution=0.0,
                      drip=True, tax_rate=0.0, annual_price_growth=0.0, annual_div_growth=0.0):
    """Simula un ticker mes a mes. Devuelve lista de tuplas mensuales
    (month, shares, price, value, annual_income_net, cum_div_net, cum_contrib).

    `fwd_yield_pct`: yield forward anual (%) al nivel actual → dividendo anual por acción =
    fwd_yield_pct/100 × price0. El precio evoluciona a `annual_price_growth` y el dividendo
    por acción a `annual_div_growth` (en el modelo de erosión ambos van juntos: el yield se
    mantiene fijo sobre un NAV que cae). `value` incluye el efectivo acumulado si DRIP está off.
    """
    dps_annual = (fwd_yield_pct / 100.0) * price0
    mpg = (1 + annual_price_growth / 100.0) ** (1 / 12.0) - 1
    mdg = (1 + annual_div_growth / 100.0) ** (1 / 12.0) - 1
    shares, price, cash = float(shares0), float(price0), 0.0
    cum_div_net, cum_contrib = 0.0, 0.0
    monthly = []
    for m in range(1, months + 1):
        if monthly_contribution > 0 and price > 0:
            shares += monthly_contribution / price
            cum_contrib += monthly_contribution
        gross = shares * (dps_annual / 12.0)
        net = gross * (1 - tax_rate)
        cum_div_net += net
        if drip and price > 0:
            shares += net / price
        else:
            cash += net
        price *= (1 + mpg)
        dps_annual *= (1 + mdg)
        annual_income_net = shares * dps_annual * (1 - tax_rate)
        value = shares * price + (0.0 if drip else cash)
        monthly.append((m, shares, price, value, annual_income_net, cum_div_net, cum_contrib))
    return monthly


def _yearly_from_monthly(monthly):
    """Resume la simulación mensual a filas anuales (snapshot de fin de cada año)."""
    rows = []
    for (m, shares, price, value, ann_inc, cum_div, cum_contrib) in monthly:
        if m % 12 == 0:
            rows.append({
                'year': m // 12, 'shares': round(shares, 4), 'price': round(price, 2),
                'portfolio_value': round(value, 2), 'annual_income': round(ann_inc, 2),
                'cumulative_dividends': round(cum_div, 2),
                'cumulative_contributions': round(cum_contrib, 2),
            })
    return rows


def project_portfolio_forward(results, params=None, classify_map=None) -> dict:
    """Proyección a futuro por ticker y consolidada, periodo a periodo (mensual).

    Ramifica por tipo de instrumento — el guardarraíl de realismo:
      • YieldMax (mode_a / type:yieldmax) → modelo de EROSIÓN: el NAV decae a la tasa
        observada (`price_cagr`, capada a ≤0: nunca se asume apreciación positiva en un
        YieldMax) y el yield se mantiene fijo sobre ese NAV que cae, así que el dividendo
        por acción también baja. Calcula la carrera ingreso-acumulado vs pérdida-de-capital,
        el mes de breakeven, el retorno total honesto y la fracción que es Retorno de
        Capital (19a, no es rendimiento real).
      • ETF de crecimiento/dividendo → modelo ESTÁNDAR: dividendo crece a
        `dividend_growth_pct`, precio se aprecia a `price_appreciation_pct` (defaults 0%).

    Solo proyecta tickers con `forward_yield`, acciones y precio. Devuelve
    {'per_ticker': {tk: {...}}, 'portfolio': {...}, 'params': {...}, 'eligible': [...]}.
    """
    p = dict(PROJ_DEFAULTS)
    if params:
        p.update({k: v for k, v in params.items() if v is not None})
    months = max(1, int(round(float(p['horizon_years']) * 12)))
    tax = max(0.0, min(1.0, float(p['tax_rate_pct']) / 100.0))
    country = p.get('country')   # si se da, la retención es por país × escudo ROC (por ticker)
    contrib = max(0.0, float(p['monthly_contribution']))
    drip = bool(p['drip'])
    classify_map = classify_map or classify_tickers(list(results.keys()))
    instruments = load_instruments()
    roc19a = load_roc_19a()

    per_ticker, eligible = {}, []
    n_eligible = sum(1 for t, s in results.items()
                     if isinstance(s, dict) and 'error' not in s and (s.get('forward_yield') or 0) > 0
                     and (s.get('shares_owned') or 0) > 0 and (s.get('current_price') or 0) > 0)
    contrib_each = contrib / n_eligible if n_eligible > 0 else 0.0  # reparte el aporte mensual

    for tk, s in results.items():
        if not isinstance(s, dict) or 'error' in s:
            continue
        fwd = s.get('forward_yield') or 0
        shares0 = s.get('shares_owned') or 0
        price0 = s.get('current_price') or 0
        if fwd <= 0 or shares0 <= 0 or price0 <= 0:
            continue
        eligible.append(tk)

        info = instruments.get(str(tk).upper(), {})
        is_ym = classify_map.get(tk) == 'mode_a' or (info.get('type') or '').lower() == 'yieldmax'

        # Retención por ticker: si hay país, tasa efectiva = país × (1 − ROC); si no, la plana.
        if country:
            _base, _ = NRA_COUNTRY_RATES.get(country, (NRA_DEFAULT_RATE, False))
            _roc_frac = _ticker_roc_fraction(tk, results)
            tk_eff_rate = round(_base * (1 - _roc_frac / 100.0), 2)
            tk_tax = max(0.0, min(1.0, tk_eff_rate / 100.0))
        else:
            tk_tax = tax
            tk_eff_rate = round(tax * 100, 2)

        decay_window = None
        if is_ym:
            _scen = (p.get('underlying_scenarios') or {}).get(tk)
            _scen_nav = None
            if _scen is not None:
                # Escenario del subyacente: deriva el NAV del fondo vía captura asimétrica.
                _scen_nav = _yieldmax_nav_from_underlying(
                    float(_scen), s.get('underlying_cagr_recent'), s.get('price_cagr_recent'),
                    p['upside_capture'], p['downside_capture'])
            if _scen_nav is not None:
                decay = _scen_nav            # puede ser positivo: el escenario lo permite a propósito
                decay_window = 'escenario'
            else:
                decay = p.get('nav_decay_overrides', {}).get(tk)
                if decay is None:
                    # Preferir el decaimiento de los últimos 12 meses (régimen actual) sobre el de
                    # toda la vida del fondo: no extrapola una caída vieja como si fuera eterna.
                    obs = s.get('price_cagr_recent')
                    decay_window = '12m'
                    if obs is None:
                        obs = s.get('price_cagr'); decay_window = 'vida'
                    decay = min(obs, 0.0) if obs is not None else p['yieldmax_decay_fallback_pct']
                    if obs is None:
                        decay_window = 'default'
                else:
                    decay_window = 'manual'
            price_growth, div_growth = decay, decay  # yield fijo sobre NAV que cae
        else:
            price_growth = p['price_appreciation_pct']
            div_growth = p['dividend_growth_pct']

        monthly = _simulate_forward(
            shares0, price0, fwd, months, monthly_contribution=contrib_each, drip=drip,
            tax_rate=tk_tax, annual_price_growth=price_growth, annual_div_growth=div_growth)
        monthly_nodrip = _simulate_forward(
            shares0, price0, fwd, months, monthly_contribution=contrib_each, drip=False,
            tax_rate=tk_tax, annual_price_growth=price_growth, annual_div_growth=div_growth)

        end_val_drip = monthly[-1][3]
        end_val_nodrip = monthly_nodrip[-1][3]
        entry = {
            'is_yieldmax': is_ym,
            'forward_yield': fwd,
            'realized_yield': s.get('realized_yield'),
            'price_growth_pct': round(price_growth, 2),
            'div_growth_pct': round(div_growth, 2),
            'yearly': _yearly_from_monthly(monthly),
            'end_value': round(end_val_drip, 2),
            'end_value_nodrip': round(end_val_nodrip, 2),
            'drip_advantage': round(end_val_drip - end_val_nodrip, 2),
            'cumulative_dividends_net': round(monthly[-1][5], 2),
            'start_value': round(shares0 * price0, 2),
            'cadence_change': s.get('cadence_change'),
            'tax_effective_rate': tk_eff_rate,
        }

        if is_ym:
            # Carrera ingreso vs erosión: buy-and-hold, distribuciones en cash, sin aportes.
            race = _simulate_forward(shares0, price0, fwd, months, monthly_contribution=0.0,
                                     drip=False, tax_rate=tk_tax,
                                     annual_price_growth=price_growth, annual_div_growth=div_growth)
            start_principal = shares0 * price0
            breakeven_m, race_rows = None, []
            for (m, sh, pr, val, ann, cum_div, _c) in race:
                capital_loss = start_principal - sh * pr  # sh es constante (sin DRIP/aporte)
                if breakeven_m is None and cum_div >= capital_loss:
                    breakeven_m = m
                race_rows.append({'month': m, 'cum_income_net': round(cum_div, 2),
                                  'capital_loss': round(capital_loss, 2),
                                  'principal_value': round(sh * pr, 2)})
            end_income = race[-1][5]
            end_principal = race[-1][1] * race[-1][2]
            honest_tr = ((end_income + end_principal - start_principal) / start_principal * 100
                         if start_principal > 0 else None)
            wpct = roc19a.get(str(tk).upper(), {}).get('weighted_pct')
            entry.update({
                'breakeven_month': breakeven_m,
                'race': race_rows,
                'total_income_net': round(end_income, 2),
                'ending_principal': round(end_principal, 2),
                'honest_total_return_pct': round(honest_tr, 1) if honest_tr is not None else None,
                'roc_fraction_pct': round(float(wpct), 1) if wpct is not None else s.get('roc_percent'),
                'decay_window': decay_window,
            })
        per_ticker[tk] = entry

    # ── Consolidado del portafolio: suma por año entre tickers ──
    portfolio = {'yearly': [], 'start_value': 0.0, 'end_value': 0.0,
                 'end_value_nodrip': 0.0, 'drip_advantage': 0.0,
                 'cumulative_dividends_net': 0.0}
    if per_ticker:
        n_years = max(len(e['yearly']) for e in per_ticker.values())
        for y in range(1, n_years + 1):
            v = inc = cdiv = contribs = 0.0
            for e in per_ticker.values():
                yr = next((r for r in e['yearly'] if r['year'] == y), None)
                if yr:
                    v += yr['portfolio_value']; inc += yr['annual_income']
                    cdiv += yr['cumulative_dividends']; contribs += yr['cumulative_contributions']
            portfolio['yearly'].append({
                'year': y, 'portfolio_value': round(v, 2), 'annual_income': round(inc, 2),
                'cumulative_dividends': round(cdiv, 2), 'cumulative_contributions': round(contribs, 2),
            })
        portfolio['start_value'] = round(sum(e['start_value'] for e in per_ticker.values()), 2)
        portfolio['end_value'] = round(sum(e['end_value'] for e in per_ticker.values()), 2)
        portfolio['end_value_nodrip'] = round(sum(e['end_value_nodrip'] for e in per_ticker.values()), 2)
        portfolio['drip_advantage'] = round(portfolio['end_value'] - portfolio['end_value_nodrip'], 2)
        portfolio['cumulative_dividends_net'] = round(
            sum(e['cumulative_dividends_net'] for e in per_ticker.values()), 2)

        # Hito: mes en que el ingreso mensual del portafolio cruza el objetivo.
        goal = p.get('income_goal_monthly')
        if goal and float(goal) > 0:
            goal = float(goal)
            hit_year = next((r['year'] for r in portfolio['yearly']
                             if r['annual_income'] / 12.0 >= goal), None)
            portfolio['income_goal_monthly'] = goal
            portfolio['income_goal_year'] = hit_year

    return {'per_ticker': per_ticker, 'portfolio': portfolio,
            'params': {**p, 'months': months}, 'eligible': eligible}


def _mc_simulate_path(asset, n_years, contrib_each, drip, rng, div_growth_base):
    """Un camino Monte Carlo de un activo: sortea un retorno anual NUEVO cada año (riesgo de
    secuencia) ~ Normal(media, vol) y compone mes a mes. Devuelve (valores_por_año[],
    ingreso_anual_final).

    Modelo de YIELD-SOBRE-PRECIO: el dividendo se calcula como `yield × precio` cada mes, así
    que si el precio cae, el dividendo cae proporcional (realista) y el DRIP nunca explota
    (la compra de acciones queda atada al yield, no a un dividendo nominal fijo / precio→0).
    YieldMax: yield constante sobre el NAV que cae. ETF: el yield-on-price crece con `div_growth`.
    """
    shares = float(asset['shares0']); price = float(asset['price0'])
    yld = (asset['fwd'] or 0) / 100.0        # yield anual sobre el precio actual
    tax = asset['tax']
    cash = 0.0
    yearly = []
    for _y in range(n_years):
        g = float(rng.normal(asset['mean'], asset['vol']))
        if asset.get('ym_clamp', asset['is_ym']):
            g = min(g, 0.0)                       # guardarraíl: YieldMax nunca aprecia (salvo escenario)
        g = max(min(g, 150.0), -99.0)             # acota el año a [-99%, +150%]
        mpg = (1 + g / 100.0) ** (1 / 12.0) - 1
        # ETF: el yield-on-price crece con el dividendo. YieldMax: yield fijo sobre NAV.
        # NOTA: se mantiene a propósito el modelo yield-on-price (dividendo atado al precio):
        # desacoplar el dps del precio para igualar al determinista reintroduce la explosión
        # del DRIP cuando el precio→0 bajo volatilidad corrupta (ver test_monte_carlo_corrupt_vol).
        myg = 0.0 if asset['is_ym'] else ((1 + max(min(div_growth_base, 150.0), -99.0) / 100.0) ** (1 / 12.0) - 1)
        for _m in range(12):
            if contrib_each > 0 and price > 0:
                shares += contrib_each / price
            net = shares * (yld / 12.0) * price * (1 - tax)   # dividendo del mes (atado al precio)
            if drip and price > 0:
                shares += net / price                          # = shares × yld/12 × (1−tax): acotado
            else:
                cash += net
            price = max(price * (1 + mpg), 1e-9)
            yld *= (1 + myg)
        yearly.append(shares * price + (0.0 if drip else cash))
    return yearly, shares * yld * price * (1 - tax)


def monte_carlo_projection(results, params=None, classify_map=None, n_paths=500, seed=None) -> dict:
    """Monte Carlo de la proyección: en vez de una sola línea, sortea el retorno anual de cada
    activo ~ Normal(media=supuesto, sd=volatilidad observada) — un valor NUEVO por año (riesgo
    de secuencia) — y corre N caminos. Reporta bandas p10/p50/p90 del valor del portafolio por
    año, la probabilidad de cumplir la meta de ingreso mensual, y el rango de valor final.
    `inflation_pct` + `real_view` permiten ver en términos reales. Determinista con `seed`.

    Devuelve {bands:[{year,p10,p50,p90}], final:{p10,p50,p90}, prob_goal, n_paths, real_view, params}.
    """
    p = dict(PROJ_DEFAULTS)
    if params:
        p.update({k: v for k, v in params.items() if v is not None})
    n_years = max(1, int(round(float(p['horizon_years']))))
    tax = max(0.0, min(1.0, float(p['tax_rate_pct']) / 100.0))
    country = p.get('country')
    contrib = max(0.0, float(p['monthly_contribution']))
    drip = bool(p['drip'])
    inflation = float(p.get('inflation_pct', 3.0) or 0.0)
    real_view = bool(p.get('real_view', False))
    goal = p.get('income_goal_monthly')
    classify_map = classify_map or classify_tickers(list(results.keys()))
    instruments = load_instruments()
    rng = np.random.default_rng(seed)

    assets = []
    for tk, s in results.items():
        if not isinstance(s, dict) or 'error' in s:
            continue
        fwd = s.get('forward_yield') or 0
        shares0 = s.get('shares_owned') or 0
        price0 = s.get('current_price') or 0
        if fwd <= 0 or shares0 <= 0 or price0 <= 0:
            continue
        info = instruments.get(str(tk).upper(), {})
        is_ym = classify_map.get(tk) == 'mode_a' or (info.get('type') or '').lower() == 'yieldmax'
        ym_clamp = is_ym   # YieldMax normalmente no aprecia; un escenario alcista lo desactiva
        if is_ym:
            _scen = (p.get('underlying_scenarios') or {}).get(tk)
            _scen_nav = (_yieldmax_nav_from_underlying(
                float(_scen), s.get('underlying_cagr_recent'), s.get('price_cagr_recent'),
                p['upside_capture'], p['downside_capture']) if _scen is not None else None)
            if _scen_nav is not None:
                mean_growth = _scen_nav      # media centrada en el escenario del subyacente
                ym_clamp = False             # permitir caminos positivos si el escenario es alcista
            else:
                obs = s.get('price_cagr_recent')
                if obs is None:
                    obs = s.get('price_cagr')
                mean_growth = min(obs, 0.0) if obs is not None else p['yieldmax_decay_fallback_pct']
        else:
            mean_growth = p['price_appreciation_pct']
        # Vol anualizada (%); acotada a [5, 100]: algunos tickers traen vol corrupta
        # (p.ej. SCHB/XLK con miles de %), que sin tope haría explotar el Monte Carlo.
        vol = s.get('volatilidad_anualizada')
        try:
            vol = min(max(5.0, float(vol)), 100.0) if vol is not None else 30.0
        except (TypeError, ValueError):
            vol = 30.0
        if country:
            _base, _ = NRA_COUNTRY_RATES.get(country, (NRA_DEFAULT_RATE, False))
            tk_tax = max(0.0, min(1.0, _base * (1 - _ticker_roc_fraction(tk, results) / 100.0) / 100.0))
        else:
            tk_tax = tax
        assets.append({'tk': tk, 'shares0': shares0, 'price0': price0, 'fwd': fwd,
                       'mean': mean_growth, 'vol': vol, 'is_ym': is_ym, 'ym_clamp': ym_clamp,
                       'tax': tk_tax})

    if not assets:
        return {'bands': [], 'final': {}, 'prob_goal': None, 'n_paths': 0,
                'real_view': real_view, 'params': {**p, 'n_years': n_years}}

    contrib_each = contrib / len(assets)
    div_growth_base = p['dividend_growth_pct']
    year_values = np.zeros((n_paths, n_years))
    final_income = np.zeros(n_paths)
    for i in range(n_paths):
        for a in assets:
            yvals, fi = _mc_simulate_path(a, n_years, contrib_each, drip, rng, div_growth_base)
            year_values[i, :] += np.array(yvals)
            final_income[i] += fi

    # Deflactar a términos reales si se pide (poder de compra de hoy).
    if real_view and inflation != 0:
        deflator = np.array([(1 + inflation / 100.0) ** (y + 1) for y in range(n_years)])
        year_values = year_values / deflator
        final_income = final_income / ((1 + inflation / 100.0) ** n_years)

    bands = []
    for y in range(n_years):
        col = year_values[:, y]
        bands.append({'year': y + 1,
                      'p10': round(float(np.percentile(col, 10)), 2),
                      'p50': round(float(np.percentile(col, 50)), 2),
                      'p90': round(float(np.percentile(col, 90)), 2)})
    fin = year_values[:, -1]
    final = {'p10': round(float(np.percentile(fin, 10)), 2),
             'p50': round(float(np.percentile(fin, 50)), 2),
             'p90': round(float(np.percentile(fin, 90)), 2)}
    prob_goal = None
    if goal and float(goal) > 0:
        prob_goal = round(float(np.mean((final_income / 12.0) >= float(goal))) * 100, 1)

    return {'bands': bands, 'final': final, 'prob_goal': prob_goal, 'n_paths': n_paths,
            'real_view': real_view, 'params': {**p, 'n_years': n_years}}


def reconcile_income(results: dict, income_summary: dict) -> dict:
    """Cruza el ingreso por dividendos del CSV (cash+drip) contra el income file del
    broker, por ventana solapada. Es PURAMENTE INFORMATIVO: no muta `results` ni
    altera assess_ticker_quality / _cost_incomplete (el nivel de calidad no cambia).

    Devuelve {ticker: {status, csv_total, csv_in_window, income_total, folded,
    history_incomplete, badge, note, est_per_payment}}.

    status ∈ {match, cusip_folded, csv_window_longer, income_higher,
              csv_overcount_suspected, missing_in_income, missing_in_csv}.
    """
    out = {}
    if not income_summary or not income_summary.get('tickers'):
        return out
    inc = income_summary['tickers']
    csv_tickers = {t: s for t, s in results.items()
                   if isinstance(s, dict) and not s.get('skipped') and 'error' not in s}

    for tk in sorted(set(list(inc.keys()) + list(csv_tickers.keys()))):
        s = csv_tickers.get(tk)
        i = inc.get(tk) or {}
        income_total = i.get('received_total')
        folded = bool(i.get('folded'))
        est_pp = i.get('est_per_payment')

        # Ticker en el income que el CSV no analizó (vendido / no-whitelist / mode_skip).
        if s is None:
            if income_total:
                out[tk] = {'status': 'missing_in_csv', 'csv_total': None,
                           'csv_in_window': None, 'income_total': round(income_total, 2),
                           'folded': folded, 'history_incomplete': False,
                           'badge': 'info', 'est_per_payment': est_pp,
                           'note': 'Aparece en el income del broker pero no en el análisis del CSV '
                                   '(posición vendida o no es un ETF de largo plazo).'}
            continue

        # Dividendo BRUTO del CSV (misma base que el income file). Se reconstruye desde el
        # historial, NO desde dividends_collected_drip (que es neto post-NRA-tax).
        csv_total = _csv_dividends_in_window(s.get('history'))
        hist_inc = bool(s.get('history_incomplete'))

        # Ticker en el CSV sin ingreso 'Received' en el income (fuera de ventana / solo Estimated).
        if not income_total:
            out[tk] = {'status': 'missing_in_income', 'csv_total': round(csv_total, 2),
                       'csv_in_window': None, 'income_total': None, 'folded': folded,
                       'history_incomplete': hist_inc, 'badge': 'info', 'est_per_payment': est_pp,
                       'note': 'El CSV registra dividendos pero el income del broker no los cubre '
                               '(distinta ventana de fechas).'}
            continue

        # Comparación por ventana solapada: restringir el CSV a la ventana del income (+buffer).
        win = i.get('received_window')
        if win and win[0] is not None and win[1] is not None:
            buf = pd.Timedelta(days=INCOME_WINDOW_BUFFER_DAYS)
            csv_in_window = _csv_dividends_in_window(s.get('history'), win[0] - buf, win[1] + buf)
        else:
            csv_in_window = csv_total

        tol = max(INCOME_MATCH_TOL_ABS, INCOME_MATCH_TOL_REL * max(income_total, csv_in_window))
        diff = csv_in_window - income_total

        if abs(diff) <= tol:
            if folded:
                status, badge = 'cusip_folded', 'ok'
                note = 'Validado contra el ingreso del broker (se plegó la identidad CUSIP→ticker).'
            elif csv_total > income_total + tol:
                status, badge = 'csv_window_longer', 'ok'
                note = ('Validado en la ventana común. El CSV reporta más en total porque cubre '
                        'fechas previas al income (historia más larga), no es un error.')
            else:
                status, badge = 'match', 'ok'
                note = 'Validado contra el ingreso del broker.'
        elif diff > tol:  # CSV reporta MÁS que el income dentro de la misma ventana
            if hist_inc:
                status, badge = 'csv_overcount_suspected', 'warn'
                note = ('El CSV reporta más dividendos que el broker en la misma ventana y su '
                        'historial está incompleto (ventas > compras): posible sobre-conteo de '
                        'acciones. Revisa con tu captura del broker.')
            else:
                status, badge = 'csv_higher', 'warn'
                note = ('El CSV reporta más dividendos que el broker en la misma ventana '
                        '(posible desfase de fechas o fila duplicada).')
        else:  # income > CSV dentro de la ventana → al CSV le faltan dividendos
            status, badge = 'income_higher', 'warn'
            note = ('El broker reporta más ingreso que el CSV en la misma ventana: al CSV le '
                    'faltan dividendos (historial de transacciones incompleto).')

        out[tk] = {
            'status': status, 'badge': badge, 'note': note,
            'csv_total': round(csv_total, 2), 'csv_in_window': round(csv_in_window, 2),
            'income_total': round(income_total, 2), 'folded': folded,
            'history_incomplete': hist_inc, 'est_per_payment': est_pp,
        }
    return out


# v2.9 — proyección de ingresos: broker (Estimated) vs nuestra (run-rate reciente).
INCOME_PROJ_MIN_PAYMENTS = 4     # mínimo de pagos 'Received' para proyectar con sentido
INCOME_OVERSTATE_FLAG_PCT = 15.0 # sobre este % de sobreestimación, marcar en la justificación


def project_income(income_df, results: dict = None) -> dict:
    """Proyección de ingresos por dividendos a 12 meses: la del broker (filas `Estimated`) vs la
    nuestra (run-rate reciente: promedio de los últimos ~3 meses de pagos × frecuencia anual).
    Todo en base anual/12m para que las barras sean comparables con lo recibido en 12 meses.

    Solo incluye tickers con ≥`INCOME_PROJ_MIN_PAYMENTS` pagos `Received` Y filas `Estimated`
    (la proyección solo aplica donde el broker proyecta y nosotros tenemos historia suficiente
    para el run-rate). Las `Estimated` se usan SOLO aquí, para contraste; nunca en el cálculo.

    Devuelve {ticker: {schwab_received_12m, our_received_12m, schwab_received_total,
    our_received_total, schwab_proj, our_proj, anchor_per_payment, recent_per_payment,
    payments_per_year, decline_pct, overstatement_pct}}.
    """
    out = {}
    if income_df is None or len(income_df) == 0:
        return out
    today = pd.Timestamp.today().normalize()
    yr_ago = today - pd.Timedelta(days=365)

    for tk, g in income_df.groupby('Ticker'):
        rec = g[g['IncomeType'].str.lower() == 'received'].dropna(subset=['Amount', 'Date']).sort_values('Date')
        est = g[g['IncomeType'].str.lower() == 'estimated'].dropna(subset=['Amount'])
        if len(rec) < INCOME_PROJ_MIN_PAYMENTS or est.empty:
            continue

        # Cadencia: mediana de días entre los últimos ~12 pagos recibidos.
        dates = list(rec['Date'].tail(12))
        gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates)) if (dates[i] - dates[i - 1]).days > 0]
        median_gap = sorted(gaps)[len(gaps) // 2] if gaps else 30
        ppy = max(1, round(365 / median_gap)) if median_gap > 0 else 12

        # Proyección del broker (próx. 365 días) y su pago-ancla.
        est_future = est[(est['Date'] >= today) & (est['Date'] <= today + pd.Timedelta(days=365))]
        schwab_proj = float(est_future['Amount'].sum()) if not est_future.empty else float(est['Amount'].iloc[-1]) * ppy
        anchor_pp = float(est['Amount'].iloc[-1])

        # Run-rate reciente: promedio de ~3 meses de pagos (nivel actual, ya caído).
        n_recent = max(2, round(ppy / 4))
        recent_pp = float(rec['Amount'].tail(n_recent).mean())
        our_proj = recent_pp * ppy

        # Recibido 12m: Schwab (income) y nuestro (reconstruido del CSV).
        schwab_recv_12m = float(rec[rec['Date'] >= yr_ago]['Amount'].sum())
        our_recv_12m = None
        if results and isinstance(results.get(tk), dict):
            our_recv_12m = round(_csv_dividends_in_window(results[tk].get('history'), yr_ago, today), 2)

        # Total histórico: Schwab (todas las filas Received) y nuestro (todo el CSV, sin ventana).
        schwab_recv_total = float(rec['Amount'].sum())
        our_recv_total = None
        if results and isinstance(results.get(tk), dict):
            our_recv_total = round(_csv_dividends_in_window(results[tk].get('history')), 2)

        # Caída: promedio por pago del tercio reciente vs el más antiguo dentro de 12m.
        last_yr = rec[rec['Date'] >= yr_ago]
        decline_pct = None
        if len(last_yr) >= 4:
            k = max(1, len(last_yr) // 3)
            old_avg = last_yr['Amount'].head(k).mean()
            if old_avg > 0:
                decline_pct = round((last_yr['Amount'].tail(k).mean() / old_avg - 1) * 100, 1)

        out[tk] = {
            'schwab_received_12m': round(schwab_recv_12m, 2),
            'our_received_12m': our_recv_12m,
            'schwab_received_total': round(schwab_recv_total, 2),
            'our_received_total': our_recv_total,
            'schwab_proj': round(schwab_proj, 2),
            'our_proj': round(our_proj, 2),
            'anchor_per_payment': round(anchor_pp, 4),
            'recent_per_payment': round(recent_pp, 4),
            'payments_per_year': int(ppy),
            'decline_pct': decline_pct,
            'overstatement_pct': round((schwab_proj / our_proj - 1) * 100, 1) if our_proj > 0 else None,
        }
    return out


# ── Filtro de "portafolio de ingresos": qué activos pertenecen a la gráfica ───
# La gráfica de Schwab vs proyección solo tiene sentido para activos cuya estrategia
# es la distribución recurrente de income alto (YieldMax/opción-ingreso, o ETFs/acciones
# de dividendo alto). Los índices/crecimiento con dividendo marginal (SCHB, XLK) aplastan
# la escala y distorsionan el propósito. Clasificación híbrida: type curado + yield real.
INCOME_ASSET_MIN_YIELD_PCT = 4.0   # yield anualizado mínimo para clasificar "activo de dividendos"


def is_income_strategy_asset(ticker, proj_entry, results=None,
                             min_yield_pct=INCOME_ASSET_MIN_YIELD_PCT):
    """¿Pertenece `ticker` al portafolio de generación de ingresos? (income/dividendo alto).

    Híbrido, sobre la base de conocimiento curada (instruments.yaml) + yield real:
      1. type == 'yieldmax'  -> SIEMPRE income (estrategia de opción-ingreso por definición).
      2. type == 'leveraged' -> NUNCA income (apalancado de crecimiento, p.ej. NVDL).
      3. resto (etf/stock/desconocido) -> yield anualizado = dividendos 12m / valor de mercado;
         income si yield >= `min_yield_pct`.
    Degradación elegante: si no hay valor de mercado o dividendos para calcular el yield, cae al
    type (yieldmax->True, leveraged->False, otro/desconocido->True: no oculta sin prueba).
    Devuelve (bool, {'reason': str, 'yield_pct': float|None}).
    """
    info = load_instruments().get(str(ticker).upper(), {})
    typ = (info.get('type') or '').lower()
    if typ == 'yieldmax':
        return True, {'reason': 'type:yieldmax', 'yield_pct': None}
    if typ == 'leveraged':
        return False, {'reason': 'type:leveraged', 'yield_pct': None}

    proj_entry = proj_entry or {}
    recv = proj_entry.get('our_received_12m')
    if recv is None:
        recv = proj_entry.get('schwab_received_12m')
    mkt = None
    if results and isinstance(results.get(ticker), dict):
        mkt = results[ticker].get('market_value')

    if recv is not None and mkt and mkt > 0:
        y = recv / mkt * 100
        return (y >= min_yield_pct), {'reason': f'yield {y:.1f}%', 'yield_pct': round(y, 2)}

    # Sin datos para el yield -> degradar por type (no ocultar sin prueba).
    return (typ != 'leveraged'), {'reason': 'sin yield calculable', 'yield_pct': None}


def filter_income_assets(proj, results=None, min_yield_pct=INCOME_ASSET_MIN_YIELD_PCT):
    """Filtra el dict de `project_income` a SOLO los activos de generación de ingresos.

    Devuelve (kept_dict, dropped_list[(ticker, reason)]). A cada entrada conservada le
    anexa `_yield_pct` (para tooltips/depuración). No muta el dict de entrada.
    """
    kept, dropped = {}, []
    for t, d in (proj or {}).items():
        ok, meta = is_income_strategy_asset(t, d, results, min_yield_pct)
        if ok:
            kept[t] = {**d, '_yield_pct': meta.get('yield_pct')}
        else:
            dropped.append((t, meta.get('reason')))
    return kept, dropped


def is_growth_asset(ticker, results=None, proj_entry=None, min_yield_pct=INCOME_ASSET_MIN_YIELD_PCT):
    """¿Pertenece `ticker` al portafolio de crecimiento (apreciación de precio, no income)?

    Complemento de `is_income_strategy_asset` pero SIN depender del income file:
      1. type == 'yieldmax'  -> NUNCA crecimiento (estrategia de income por definición).
      2. type == 'leveraged' -> SIEMPRE crecimiento (apalancado de crecimiento, p.ej. NVDL).
      3. resto -> yield anualizado. Si hay dato del income file (`proj_entry`) usa
         dividendos 12m / valor de mercado; si no, cae a `yield_on_cost` del CSV.
         Es crecimiento si el yield < `min_yield_pct`.
    Degradación: sin yield calculable, solo es crecimiento si el type es de crecimiento
    explícito (no clasifica como crecimiento sin prueba).
    Devuelve (bool, {'reason': str, 'yield_pct': float|None}).
    """
    info = load_instruments().get(str(ticker).upper(), {})
    typ = (info.get('type') or '').lower()
    if typ == 'yieldmax':
        return False, {'reason': 'type:yieldmax', 'yield_pct': None}
    if typ == 'leveraged':
        return True, {'reason': 'type:leveraged', 'yield_pct': None}

    proj_entry = proj_entry or {}
    recv = proj_entry.get('our_received_12m')
    if recv is None:
        recv = proj_entry.get('schwab_received_12m')
    r = results.get(ticker) if (results and isinstance(results.get(ticker), dict)) else None
    mkt = r.get('market_value') if r else None

    # Yield-on-market desde el income file (preferido, mismo criterio que income).
    if recv is not None and mkt and mkt > 0:
        y = recv / mkt * 100
        return (y < min_yield_pct), {'reason': f'yield {y:.1f}%', 'yield_pct': round(y, 2)}

    # Fallback solo-CSV: yield sobre costo (presente en results aunque no haya income file).
    if r is not None and r.get('yield_on_cost') is not None:
        y = float(r.get('yield_on_cost') or 0)
        return (y < min_yield_pct), {'reason': f'yield_on_cost {y:.1f}%', 'yield_pct': round(y, 2)}

    return (typ == 'leveraged'), {'reason': 'sin yield calculable', 'yield_pct': None}


def filter_growth_assets(results, proj=None, min_yield_pct=INCOME_ASSET_MIN_YIELD_PCT):
    """Selecciona del análisis (`results`) SOLO los activos de crecimiento (no-income).

    Cubre TODAS las posiciones válidas (no solo las del income file). Excluye skipped/error.
    Devuelve {ticker: {market_value, pocket_investment, dividends_collected_cash, roi_percent,
    benchmark_value, benchmark_roi, _yield_pct}}.
    """
    out = {}
    for t, s in (results or {}).items():
        if not isinstance(s, dict) or s.get('skipped') or 'error' in s:
            continue
        is_g, meta = is_growth_asset(t, results, (proj or {}).get(t), min_yield_pct)
        if not is_g:
            continue
        out[t] = {
            'market_value': s.get('market_value'),
            'pocket_investment': s.get('pocket_investment'),
            'dividends_collected_cash': s.get('dividends_collected_cash'),
            'roi_percent': s.get('roi_percent'),
            'benchmark_value': s.get('benchmark_value'),
            'benchmark_roi': s.get('benchmark_roi'),
            '_yield_pct': meta.get('yield_pct'),
        }
    return out


# ── Captura de casos de estudio (golden harness) ─────────────────────────────
# Diseño: anonimización por construcción. Solo se conservan las columnas que el
# pipeline consume; cualquier columna del broker con cuenta/nombre/dirección se
# descarta. Nunca se guardan imágenes, ni IP, ni geo. Ver PRIVACY.md.

CAPTURE_MIN_COLUMNS = ['Date', 'Action', 'Ticker', 'Quantity', 'Price', 'Amount']
CAPTURE_MIN_OK_TICKERS = 2          # mínimo de tickers nivel 'ok' para considerar el caso "sólido"
CAPTURE_SCHEMA_VERSION = '1.0'


def _safe_round(v, nd: int = 4):
    try:
        if v is None:
            return None
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def anonymize_to_min_rows(df_clean: pd.DataFrame) -> pd.DataFrame:
    """Reduce un DataFrame normalizado a SOLO las columnas del pipeline.

    Whitelist estricta: descarta por construcción cualquier columna del broker
    (número de cuenta, titular, dirección, descripción libre). La fecha se trunca
    a YYYY-MM-DD para no arrastrar timestamps/zona horaria identificables.
    """
    cols = [c for c in CAPTURE_MIN_COLUMNS if c in df_clean.columns]
    out = df_clean[cols].copy()
    if 'Date' in out.columns:
        out['Date'] = pd.to_datetime(out['Date'], errors='coerce').dt.strftime('%Y-%m-%d')
        out = out.dropna(subset=['Date'])
    if 'Ticker' in out.columns:
        out['Ticker'] = out['Ticker'].astype(str).str.strip().str.upper()
        out = out[out['Ticker'].ne('') & out['Ticker'].ne('NAN')]
    if 'Action' in out.columns:
        out['Action'] = out['Action'].astype(str).str.strip()
    return out.reset_index(drop=True)


def is_capture_worthy(quality_map: dict, overrides: dict) -> tuple:
    """Decide si un caso es lo bastante sólido/completo para capturar.

    Devuelve (bool, motivo). Regla: posiciones confirmadas por el usuario +
    al menos CAPTURE_MIN_OK_TICKERS tickers con calidad 'ok'.
    """
    if not overrides:
        return False, 'sin posiciones confirmadas'
    n_ok = sum(1 for q in (quality_map or {}).values() if isinstance(q, dict) and q.get('level') == 'ok')
    if n_ok < CAPTURE_MIN_OK_TICKERS:
        return False, f'solo {n_ok} ticker(s) con datos completos (se requieren {CAPTURE_MIN_OK_TICKERS})'
    has_confirmed = any(
        _safe_round((v or {}).get('cost_basis')) and _safe_round((v or {}).get('shares'))
        for v in overrides.values()
    )
    if not has_confirmed:
        return False, 'ninguna posición con acciones y costo confirmados'
    return True, 'ok'


def build_capture_bundle(df_clean: pd.DataFrame, broker: str, overrides: dict,
                         quality_map: dict, gemini_raw: dict = None,
                         app_version: str = '2.8') -> dict:
    """Construye el bundle anónimo de un caso de estudio (sin red, testeable).

    Todos los payloads son números/enums/texto genérico: cero PII por construcción.
    """
    import uuid
    min_df = anonymize_to_min_rows(df_clean)
    case_id = uuid.uuid4().hex[:12]

    ground_truth = {}
    for t, v in (overrides or {}).items():
        v = v or {}
        ground_truth[str(t).strip().upper()] = {
            'cost_basis': _safe_round(v.get('cost_basis'), 2),
            'shares': _safe_round(v.get('shares'), 4),
        }

    quality = {}
    for t, q in (quality_map or {}).items():
        if not isinstance(q, dict):
            continue
        quality[str(t)] = {
            'level': q.get('level'),
            'flags': list(q.get('flags') or []),
            'coverage_pct': q.get('coverage_pct'),
        }

    raw = {}
    for t, v in (gemini_raw or {}).items():
        v = v or {}
        raw[str(t)] = {k: v.get(k) for k in ('cost_basis', 'shares', 'market_value', 'price') if k in v}

    meta = {
        'case_id': case_id,
        'broker': broker or 'generic',
        'app_version': app_version,
        'schema_version': CAPTURE_SCHEMA_VERSION,
        'captured_at': datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + 'Z',
        'n_rows': int(len(min_df)),
        'tickers': sorted(ground_truth.keys()),
    }

    return {
        'case_id': case_id,
        'broker': meta['broker'],
        'transactions_min_csv': min_df.to_csv(index=False),
        'ground_truth': ground_truth,
        'quality': quality,
        'gemini_raw': raw,
        'meta': meta,
    }


def build_portfolio_comparison_series(results: dict, classify_map: dict) -> pd.DataFrame:
    """
    Aggregates each portfolio block (mode_a = Dividendos, mode_b = Crecimiento)
    into a single time series, reusing the per-ticker 'daily_trend' frames.

    Returns a long-format DataFrame: Fecha, Portafolio, Rendimiento (%), Valor ($).
    A block with no valid tickers is omitted. No network calls — pure aggregation.
    """
    blocks = {'mode_a': 'Dividendos', 'mode_b': 'Crecimiento'}
    frames = []

    for mode, label in blocks.items():
        # Excluir tickers con costo base incompleto (sells > buys, o valor sin costo registrado por
        # acciones previas al CSV): su capital invertido esta subestimado y distorsiona el % del bloque.
        tickers = [t for t, m in classify_map.items()
                   if m == mode and t in results and 'error' not in results[t]
                   and not _cost_incomplete(results, t)]
        trends = []
        for t in tickers:
            dt = results[t].get('daily_trend')
            if dt is None or len(dt) == 0:
                continue
            if not {'Invested Capital', 'User Total Value'}.issubset(dt.columns):
                continue
            trends.append(dt[['Invested Capital', 'User Total Value']])

        if not trends:
            continue

        all_dates = trends[0].index
        for dt in trends[1:]:
            all_dates = all_dates.union(dt.index)
        all_dates = all_dates.sort_values()

        port_invested = pd.Series(0.0, index=all_dates)
        port_value = pd.Series(0.0, index=all_dates)
        for dt in trends:
            aligned = dt.reindex(all_dates).ffill().fillna(0)
            port_invested = port_invested.add(aligned['Invested Capital'], fill_value=0)
            port_value = port_value.add(aligned['User Total Value'], fill_value=0)

        rendimiento = np.where(port_invested > 0,
                               (port_value - port_invested) / port_invested * 100,
                               np.nan)

        frames.append(pd.DataFrame({
            'Fecha': all_dates,
            'Portafolio': label,
            'Rendimiento': rendimiento,
            'Valor': port_value.values,
        }))

    if not frames:
        return pd.DataFrame(columns=['Fecha', 'Portafolio', 'Rendimiento', 'Valor'])

    return pd.concat(frames, ignore_index=True)


# ============================================================
# v2.0 — TRIPLE STRATEGY COMPARISON
# ============================================================

@st.cache_data(show_spinner=False)
def simulate_triple_comparison(buy_flows_json: str) -> dict:
    """
    Simulates 4 strategies using the exact same cash flows (date, amount pairs).
    buy_flows_json: JSON string of list of [date_str, amount] pairs (pre-serialized for caching).
    Returns ranked dict of strategies.
    """
    import json

    try:
        buy_flows = json.loads(buy_flows_json)
        if not buy_flows:
            return {}

        dates = [pd.to_datetime(d) for d, _ in buy_flows]
        amounts = [float(a) for _, a in buy_flows]
        total_invested = sum(amounts)

        earliest = min(dates)

        strategies = {
            'all_vti':  ('VTI',  'Todo en VTI'),
            'all_ymax': ('YMAX', 'Todo en YMAX'),
            'all_spy':  ('SPY',  'Todo en SPY'),
        }

        strategy_results = {}

        for key, (sticker, label) in strategies.items():
            try:
                mdata, _ = fetch_market_data(sticker, earliest)
                if mdata.empty:
                    continue

                mdata = mdata.sort_index()
                safe_prices = mdata['Close'].replace(0, pd.NA).ffill().bfill()
                divs = (mdata['Dividends'] if 'Dividends' in mdata.columns
                        else pd.Series(0.0, index=mdata.index))

                # Asigna cada flujo al último día de mercado disponible (<= fecha del flujo).
                invested_on = {}
                for dt, amt in zip(dates, amounts):
                    trade_day = safe_prices.index.asof(dt)
                    if pd.isna(trade_day):
                        trade_day = safe_prices.index[0]
                    invested_on[trade_day] = invested_on.get(trade_day, 0.0) + amt

                # Total Return: reinvierte los dividendos del ticker (mismo patrón que VOO).
                shares = 0.0
                for date in safe_prices.index:
                    vp = float(safe_prices.loc[date]) if not pd.isna(safe_prices.loc[date]) else 0.0
                    if vp > 0:
                        add_cash = invested_on.get(date, 0.0)
                        if add_cash:
                            shares += add_cash / vp
                        div = float(divs.get(date, 0.0) or 0.0)
                        if div > 0 and shares > 0:
                            shares += (div * shares) / vp
                    shares = max(shares, 0.0)

                final_price = float(safe_prices.iloc[-1])
                final_value = shares * final_price
                ret_pct = (final_value - total_invested) / total_invested * 100 if total_invested > 0 else 0

                strategy_results[key] = {
                    'label': label,
                    'total_invested': total_invested,
                    'final_value': final_value,
                    'return_pct': ret_pct,
                }
            except Exception as e:
                print(f"simulate_triple_comparison error for {sticker}: {e}")

        return strategy_results

    except Exception as e:
        print(f"simulate_triple_comparison outer error: {e}")
        return {}


@st.cache_data(show_spinner=False, ttl=3600)
def build_yieldmax_total_return_series(tickers: list, start: str = None) -> pd.DataFrame:
    """
    Descarga precios ajustados (auto_adjust=True: total return, dividendos/ROC reinvertidos)
    para una lista de tickers desde `start` (o desde la inception de cada uno si start es None),
    normalizados a base 100 en la primera fecha común de la serie.
    Retorna long-format: Fecha, Ticker, Valor. Ignora tickers que fallen la descarga.
    """
    frames = []
    for tk in tickers:
        try:
            if start:
                raw = yf.download(tk, start=start, auto_adjust=True, progress=False)
            else:
                raw = yf.download(tk, period="max", auto_adjust=True, progress=False)
            if raw is None or raw.empty:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            prices = raw['Close'].dropna()
            if prices.empty:
                continue
            if getattr(prices.index, 'tz', None) is not None:
                prices.index = prices.index.tz_localize(None)
            prices.index = prices.index.normalize()
            base = float(prices.iloc[0])
            if base <= 0:
                continue
            norm = (prices / base) * 100.0
            df = norm.reset_index()
            df.columns = ['Fecha', 'Valor']
            df['Ticker'] = tk
            frames.append(df)
        except Exception as e:
            print(f"build_yieldmax_total_return_series error for {tk}: {e}")
    if not frames:
        return pd.DataFrame(columns=['Fecha', 'Ticker', 'Valor'])
    return pd.concat(frames, ignore_index=True)

