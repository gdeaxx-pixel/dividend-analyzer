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
    # Map common column names to standard internal names
    col_map = {
        'Fecha': 'Date', 'date': 'Date', 'Time': 'Date',
        'Descripción': 'Action', 'Action': 'Action', 'Operación': 'Action',
        'Símbolo': 'Ticker', 'Ticker': 'Ticker', 'Symbol': 'Ticker',
        'Cantidad': 'Quantity', 'Quantity': 'Quantity', 'Shares': 'Quantity',
        'Precio': 'Price', 'Price': 'Price',
        'Monto': 'Amount', 'Amount': 'Amount', 'Total': 'Amount', 'Value': 'Amount'
    }
    
    df = df.rename(columns=col_map)
    
    # Ensure Date is datetime
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    # Filter out invalid dates (handles metadata rows like 'Data as of...')
    df = df.dropna(subset=['Date'])
    
    # Clean Ticker (remove spaces)
    if 'Ticker' in df.columns:
        df['Ticker'] = df['Ticker'].str.strip()
        
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
        
        # Iterate through transactions to build history
        for idx, row in ticker_df.iterrows():
            action = str(row['Action']).lower()
            qty = float(row['Quantity']) if not pd.isna(row['Quantity']) else 0.0
            amount = float(row['Amount']) if not pd.isna(row['Amount']) else 0.0
            
            # Identify Transaction Type
            is_buy = 'buy' in action or 'compra' in action
            is_sell = 'sell' in action or 'venta' in action
            is_drip = 'reinvest' in action or 'reinversión' in action or 'drip' in action
            is_div_payout = 'dividend' in action or 'dividendo' in action
            
            # Logic
            if is_buy:
                pocket_investment += abs(amount) # Amount usually negative for buys in many brokers, force positive cost
                shares_owned += abs(qty)
            
            elif is_drip:
                # DRIP is not 'out of pocket', it's internal compounding
                # Some brokers record DRIP as Dividend (Credit) + Reinvest (Debit).
                # Example: Recibes $100 (Credit), then buys shares for -$100 (Debit).
                # We want to count the Value ($100) only ONCE.
                
                # Logic Revision (Step 3):
                # User data shows TDA format: "Reinvest Shares" with NEGATIVE amount. 
                # User data also showed "Reinvest Dividend" (Positive) + "Reinvest Shares" (Negative).
                # To capture BOTH correctly without double counting:
                # We count the "Purchase" (Negative Amount) as the realization of the DRIP.
                # We ignore the "Credit" (Positive Amount) if it falls under 'Reinvest' to avoid double count.
                
                shares_owned += abs(qty)
                
                if amount < 0:
                     dividends_collected_drip += abs(amount)
                # If positive (the funding credit), we ignore it here.
                
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
        # Note: simplistic split handling for chart (relying on market_data logic could be complex mixed with CSV)
        # For a "good enough" visual, we cumsum shares. 
        # Ideally, we would apply splits to the cumulative sum if not present in CSV. 
        # Given constraints, we assume simplistically for the chart.
        daily_history['Shares Held'] = daily_history['Quantity'].cumsum()
        
        # 4. Calculate Values
        daily_history['Price'] = market_data['Close']
        daily_history['Market Value'] = daily_history['Shares Held'] * daily_history['Price']
        
        # 5. Calculate Cumulative Investment (Cost Basis) over time
        # Amount is negative for buys. We want "Cost Basis" (positive input).
        # Investment = Sum of (Buys - Sells). 
        # To just show "Capital vs Market", we can track "Net Out of Pocket"
        # We assume Amount is negative for buys.
        daily_history['Daily Invested'] = daily_activity['Amount'].reindex(market_data.index).fillna(0) * -1 # Make buy positive
        daily_history['Invested Capital'] = daily_history['Daily Invested'].cumsum()

        
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
            "daily_trend": daily_history[['Market Value', 'Invested Capital']] 
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

