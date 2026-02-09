import pandas as pd
import yfinance as yf
import datetime

def normalize_csv(df):
    """
    Normalizes input dataframe to allow for different broker export formats.
    Expected columns (mappings will be attempted):
    - Date: Fecha
    - Action: Tipo de operacion (Buy, Reinvest, Dividend)
    - Ticker: Simbolo
    - Quantity: Cantidad
    - Price: Precio
    - Amount: Monto/Total
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

def fetch_market_data(ticker, start_date):
    """
    Fetches raw market data (auto_adjust=False) to correctly calculate dividends and splits.
    """
    # Extend start date back a bit to ensure we cover the first transaction
    start_date_obj = pd.to_datetime(start_date)
    buffer_date = start_date_obj - datetime.timedelta(days=10)
    
    try:
        data = yf.download(ticker, start=buffer_date, progress=False, auto_adjust=False, actions=True)
        # Flatten MultiIndex if present
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
            
        return data
    except Exception as e:
        print(f"Error downloading {ticker}: {e}")
        return pd.DataFrame()

def analyze_portfolio(df):
    """
    Core function to analyze the portfolio from the normalized CSV.
    Detailed 'Forensic' analysis logic from SKILL.md.
    """
    results = {}
    
    # Group by Ticker
    tickers = df['Ticker'].unique()
    
    for ticker in tickers:
        ticker_df = df[df['Ticker'] == ticker].sort_values('Date')
        if ticker_df.empty:
            continue
            
        first_date = ticker_df['Date'].min()
        market_data = fetch_market_data(ticker, first_date)
        
        if market_data.empty:
            results[ticker] = {"error": "No market data found"}
            continue

        current_price = market_data['Close'].iloc[-1]
        
        # --- Analysis Variables ---
        pocket_investment = 0.0 # Net cash flow from user's pocket
        shares_owned = 0.0
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
            
            # 4. Dividend Payout (Pago Cash)
            # Keywords: dividend, dividendo, yield, interest
            # Exclusion: MUST NOT be a reinvestment (handled by DRIP logic) to distinguish Cash vs Reinv.
            is_div_payout = ('dividend' in action or 'dividendo' in action or 'yield' in action or 'interest' in action) and not is_drip
            
            # Logic
            if is_buy:
                pocket_investment += abs(amount) # Amount usually negative for buys in many brokers, force positive cost
                shares_owned += abs(qty)
            
            elif is_drip:
                # Semantic Analysis of Description (User Request)
                # instead of just looking at positive/negative, we look at the intent in the text.
                
                # Pattern 1: "Reinvest Shares" / "Comprar Acciones"
                # This explicitly describes the act of using money to buy shares.
                # This is the "Realization" of the DRIP. We count this value.
                if 'share' in action or 'acciones' in action:
                    shares_owned += abs(qty)
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
                 
            # Special Handling: Splits in CSV
            # Ideally the CSV has the adjusted quantity. If we see a massive quantity change without amount, likely split.
            # But the SKILL says: "Balance Reset: Al detectar un 'Reverse Split' con una cantidad positiva en el CSV, trátalo como un Reinicio de Balance."
            if 'split' in action:
                if qty > 0:
                     shares_owned = qty # Reset balance to what CSV says
        
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
        daily_activity = ticker_df.groupby('Date')[['Quantity', 'Amount']].sum()
        
        # 2. Reindex to market data (daily)
        daily_history = daily_activity.reindex(market_data.index).fillna(0)
        
        # 3. Calculate Cumulative Shares
        daily_history['Shares Held'] = daily_history['Quantity'].cumsum()
        
        # 4. Calculate Values
        daily_history['Price'] = market_data['Close']
        daily_history['Market Value'] = daily_history['Shares Held'] * daily_history['Price']
        
        # 5. Calculate Cumulative Investment (Cost Basis) over time
        # Investment = Sum of (Buys - Sells). Amount is negative for buys.
        daily_history['Daily Invested'] = daily_activity['Amount'].reindex(market_data.index).fillna(0) * -1 
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

        # 7. Calculate SPY Benchmark (Simulated)
        try:
             # Fetch SPY data covering the same range
            spy_data = yf.download('SPY', start=first_date, progress=False, auto_adjust=True) # Use Adj Close for Total Return
            if isinstance(spy_data.columns, pd.MultiIndex):
                spy_data.columns = spy_data.columns.get_level_values(0)
            
            # Reindex SPY to match portfolio dates (ffill for missing days)
            spy_prices = spy_data['Close'].reindex(daily_history.index).ffill()
            
            # Simulate buying SPY with the *same* invested capital flow
            spy_shares_owned = 0.0
            spy_value_history = []
            
            for date, row in daily_history.iterrows():
                invested_today = row['Daily Invested']
                spy_price = spy_prices.loc[date]
                
                if pd.notna(spy_price) and spy_price > 0:
                    # Buy/Sell SPY shares equivalent to the cash flow
                    shares_bought = invested_today / spy_price
                    spy_shares_owned += shares_bought
                
                # Current Value of SPY position
                current_spy_value = spy_shares_owned * (spy_price if pd.notna(spy_price) else 0)
                spy_value_history.append(current_spy_value)
            
            daily_history['SPY Value'] = spy_value_history
            daily_history['SPY Profit'] = daily_history['SPY Profit'] = daily_history['SPY Value'] - daily_history['Invested Capital']
            
        except Exception as e:
            print(f"Error calculating benchmark: {e}")
            daily_history['SPY Profit'] = 0.0 # Fallback

        # 8. Calculate Percentage Returns (ROI %)
        # Avoid division by zero
        daily_history['User Return %'] = daily_history.apply(
            lambda row: (row['User Profit'] / row['Invested Capital'] * 100) if row['Invested Capital'] > 0 else 0.0, axis=1
        )
        
        daily_history['SPY Return %'] = daily_history.apply(
            lambda row: (row['SPY Profit'] / row['Invested Capital'] * 100) if row['Invested Capital'] > 0 else 0.0, axis=1
        )
        
        results[ticker] = {
            "current_price": current_price,
            "shares_owned": shares_owned,
            "pocket_investment": pocket_investment,
            "market_value": market_value,
            "dividends_collected_cash": dividends_collected_cash,
            "dividends_collected_drip": dividends_collected_drip,
            "total_dividends": total_dividends,
            "net_profit": net_profit,
            "roi_percent": roi,
            "history": ticker_df,
            "daily_trend": daily_history[['User Profit', 'SPY Profit', 'User Return %', 'SPY Return %', 'Invested Capital', 'Market Value']] 
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
    market_data = fetch_market_data(ticker, start_date)
    if market_data.empty:
        return None

    # Filter data to start from start_date
    market_data = market_data[market_data.index >= pd.to_datetime(start_date)]
    if market_data.empty:
        return None

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
    
    return final_stats

