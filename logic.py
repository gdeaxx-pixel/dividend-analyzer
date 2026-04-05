import pandas as pd
import numpy as np
import yfinance as yf
import datetime
import streamlit as st
from curl_cffi import requests as crequests
import re
import io

def get_session():
    """
    Creates a curl_cffi session mimicking Chrome to bypass bot detection.
    """
    return crequests.Session(impersonate="chrome")

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
            def clean_val(x):
                s = str(x)
                # If it looks like European format (has comma, maybe has dot before)
                if ',' in s:
                    s = s.replace('.', '') # remove thousands dot
                    s = s.replace(',', '.') # comma to decimal point
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
                return data, None
        except Exception as e:
            print(f"Error downloading {ticker} (Attempt {attempt+1}): {e}")
    
    # 2. Fallback: yf.Ticker().history (Single API)
    # Sometimes yf.download fails for specific tickers/IPs, but Ticker object works.
    print(f"Falling back to yf.Ticker({ticker}).history()...")
    try:
        t = yf.Ticker(ticker, session=session)
        data = t.history(start=buffer_date, auto_adjust=False, actions=True)
        
        if not data.empty:
            # Ensure index is timezone-aware/naive compatible if needed
            # history() usually returns single header level for single ticker
            return data, None
            
    except Exception as e:
        print(f"Fallback error for {ticker}: {e}")
        
    # 3. Last Resort: HTML Scraping
    print(f"Attempting HTML scraping for {ticker}...")
    data = fetch_data_from_html(ticker)
    if not data.empty:
        # Filter by start date if needed
        data = data[data.index >= pd.to_datetime(buffer_date)]
        return data, None

    return pd.DataFrame(), "No market data found: API Rate Limited & Scraper failed."

@st.cache_data(show_spinner=False)
def simulate_strategy_cached(ticker, start_date_str, initial_investment):
    """Cache wrapper for simulate_strategy. Uses string for start_date to ensure hashability."""
    start_date = datetime.date.fromisoformat(start_date_str)
    return simulate_strategy(ticker, start_date, initial_investment)


@st.cache_data(show_spinner=False)
def analyze_portfolio(df: pd.DataFrame, version: str = "1.2.1") -> dict:
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
    
    # Group by Ticker
    tickers = df['Ticker'].unique()
    
    for ticker in tickers:
        ticker_df = df[df['Ticker'] == ticker].sort_values('Date')
        if ticker_df.empty:
            continue
            
        first_date = ticker_df['Date'].min()
        market_data, error_msg = fetch_market_data(ticker, first_date)
        
        if market_data.empty:
            results[ticker] = {"error": f"No market data found: {error_msg}"}
            continue

        current_price = market_data['Close'].iloc[-1]
        
        # --- Analysis Variables ---
        pocket_investment = 0.0 # Net cash flow from user's pocket
        shares_owned = 0.0
        shares_owned_pocket = 0.0
        shares_owned_drip = 0.0
        dividends_collected_cash = 0.0
        dividends_collected_drip = 0.0 # Value of dividends reinvested
        
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
        cash_flows = []
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
            
            if is_buy or is_deposit:
                pocket_investment += abs(amount) # Amount usually negative for buys in many brokers, force positive cost
                shares_owned += abs(qty)
                shares_owned_pocket += abs(qty)
                row_cash_flow = abs(amount)
            
            elif is_drip:
                # Semantic Analysis of Description (User Request)
                # instead of just looking at positive/negative, we look at the intent in the text.
                
                # Pattern 1: "Reinvest Shares" / "Comprar Acciones"
                # This explicitly describes the act of using money to buy shares.
                # This is the "Realization" of the DRIP. We count this value.
                if 'share' in action or 'acciones' in action:
                    shares_owned += abs(qty)
                    shares_owned_drip += abs(qty)
                    dividends_collected_drip += abs(amount)
                    
                # Pattern 2: "Reinvest Dividend" / "Dividendo Reinversión"
                # This describes the source of funds (the dividend payout).
                # To avoid double counting (since we counted the share purchase above), we ignore this value.
                elif 'dividend' in action or 'dividendo' in action:
                    # We might still want to capture shares if for some reason they are only reported here
                    # But usually 'Dividend' rows are cash flow, not share movement, or they duplicate the share movement.
                    # Safe bet: If Amount is positive, it's the funding. Ignore value.
                    pass
                
                # Pattern 3: Ambiguous / Fallback (e.g. just "DRIP" or "Reinv")
                # Use the sign heuristic:
                # Negative amount = Purchase = Count Value
                else: 
                     shares_owned += abs(qty)
                     shares_owned_drip += abs(qty)
                     if amount < 0:
                        dividends_collected_drip += abs(amount)
                
            elif is_div_payout:
                # Cash dividend NOT reinvested
                if not is_drip: # Ensure we didn't double count if logic overlaps
                     dividends_collected_cash += abs(amount)
                     
            elif is_sell:
                 # Selling returns money to pocket (reduces net investment)
                 pocket_investment -= abs(amount) 
                 shares_owned -= abs(qty)
                 shares_owned_pocket -= abs(qty)
                 row_cash_flow = -abs(amount)
                 
            # Special Handling: Splits in CSV
            # Ideally the CSV has the adjusted quantity. If we see a massive quantity change without amount, likely split.
            # But the SKILL says: "Balance Reset: Al detectar un 'Reverse Split' con una cantidad positiva en el CSV, trátalo como un Reinicio de Balance."
            if 'split' in action:
                if qty > 0:
                     shares_owned = qty # Reset balance to what CSV says
                     
            cash_flows.append(row_cash_flow)
            
        ticker_df['Cash_Flow_In'] = cash_flows
        
        # --- Final High-Level Calculations ---
        market_value = shares_owned * current_price
        
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
        daily_activity = ticker_df.groupby('Date')[['Quantity', 'Amount', 'Cash_Flow_In']].sum()
        
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
            # Check for split
            split_val = splits.loc[date]
            if split_val != 0:
                 # Standard definition: Split 2.0 means 2-for-1 (shares double).
                 # Split 0.5 means 1-for-2 (shares halve).
                 running_shares *= split_val
            
            # Add daily activity (Net Quantity from Buys/Sells)
            net_qty = daily_history.loc[date, 'Quantity']
            running_shares += net_qty
            
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

        # 6. Calculate User Profit (Real)
        # We need to track Cumulative Cash Dividends to add to Market Value
        # Identify Cash Dividend rows in original DF
        cash_div_rows = ticker_df[
            (ticker_df['Action'].str.lower().str.contains('dividend|dividendo|yield|interest')) & 
            (~ticker_df['Action'].str.lower().str.contains('reinvest|reinversión|drip'))
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
            # Fetch VOO data covering the same range (auto_adjust=True for Total Return)
            benchmark_ticker = 'VOO'
            session = None
            try:
                session = get_session()
            except:
                pass
                
            spy_data = yf.download(benchmark_ticker, start=first_date, progress=False, auto_adjust=True, session=session)
            
            if isinstance(spy_data.columns, pd.MultiIndex):
                spy_data.columns = spy_data.columns.get_level_values(0)
            
            # Reindex SPY to match portfolio dates (ffill to handle weekends/holidays if mapped)
            spy_prices = spy_data['Close'].reindex(daily_history.index).ffill()
            
            # Simulate buying VOO shares with the exact same 'Daily Invested' amounts
            daily_history['VOO Price'] = spy_prices
            # Handle potential zeros or NaNs in VOO Price to avoid division by zero
            safe_voo_price = daily_history['VOO Price'].replace(0, pd.NA).ffill().bfill()
            
            # Calculate shares bought each day (Daily Invested / Price)
            # Note: Sells (negative Daily Invested) will correctly reduce shares
            daily_history['VOO Shares Bought'] = daily_history['Daily Invested'] / safe_voo_price
            daily_history['VOO Shares Held'] = daily_history['VOO Shares Bought'].cumsum()
            
            # Simulated Total Value
            daily_history['SPY Profit'] = daily_history['VOO Shares Held'] * daily_history['VOO Price'] 
            
        except Exception as e:
            print(f"Error calculating benchmark (VOO): {e}")
            daily_history['SPY Profit'] = 0.0
            
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
            
            # Net Flow (New money coming in/out)
            net_flow = row['Daily Invested']
            
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

        spy_vals = daily_history['SPY Profit'].replace(0, np.nan)
        spy_daily_returns_q = spy_vals.pct_change().dropna()

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

        # 4. Sortino Ratio
        retornos_neg = daily_returns_q[daily_returns_q < 0]
        if len(retornos_neg) >= 2 and retornos_neg.std() > 1e-9:
            exceso_s = daily_returns_q.mean() - rf_diario
            sortino_ratio = float((exceso_s / retornos_neg.std()) * np.sqrt(252))
        else:
            sortino_ratio = None

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

        # 6. Calmar Ratio — CAGR derivado de TWR para consistencia temporal
        if max_drawdown is not None and max_drawdown < -1e-9 and len(daily_returns_q) >= 2:
            # Usamos el TWR acumulado final (no ROI simple) para calcular CAGR
            twr_final = daily_history['User Return %'].dropna()
            if len(twr_final) > 0:
                cum_twr_final = 1 + twr_final.iloc[-1] / 100
                anios_twr = len(twr_final) / 252
                cagr_twr = ((cum_twr_final ** (1 / anios_twr)) - 1) * 100 if anios_twr > 0 else 0
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
            # Nuevas métricas cuantitativas
            "volatilidad_anualizada": volatilidad_anualizada,
            "sharpe_ratio":           sharpe_ratio,
            "sortino_ratio":          sortino_ratio,
            "max_drawdown":           max_drawdown,
            "calmar_ratio":           calmar_ratio,
            "beta_vs_voo":            beta,
            "alpha_anualizado":       alpha,
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
        splits = row['Stock Splits'] if 'Stock Splits' in row else 0.0
        
        # --- Handle Splits ---
        if splits != 0:
            # yfinance reports splits as ratio. e.g. 2.0 means 2-for-1.
            # If 0.5 (reverse split 1-for-2).
            # We must adjust share count.
            drip_shares = drip_shares * splits
            nodrip_shares = nodrip_shares * splits
            
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

