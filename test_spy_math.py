import pandas as pd
import yfinance as yf
import datetime

# Mock Data simulating user's problem case
# Let's say we buy 1 share of TSLY every month for 5 months
dates = pd.date_range(start='2024-01-01', periods=5, freq='MS')
df = pd.DataFrame({
    'Date': dates,
    'Action': ['Buy'] * 5,
    'Ticker': ['TSLY'] * 5,
    'Quantity': [100, 100, 100, 100, 100],
    'Amount': [1500, 1400, 1600, 1500, 1450] # Positive amounts like the user's Excel
})

# Let's run a slimmed down version of the logic to trace the math
first_date = df['Date'].min()
end_date = df['Date'].max() + datetime.timedelta(days=10)

# Fetch VOO
voo = yf.download('VOO', start=first_date, end=end_date, progress=False, auto_adjust=True)
if isinstance(voo.columns, pd.MultiIndex):
    voo.columns = voo.columns.get_level_values(0)

# 1. Process CSV to get daily Cash Flows
cash_flows = []
for idx, row in df.iterrows():
    if row['Action'] == 'Buy':
        cash_flows.append(abs(row['Amount'])) # Force positive for "Money IN"
df['Cash_Flow_In'] = cash_flows

# 2. Resample to Market Data
daily_activity = df.groupby('Date')[['Cash_Flow_In']].sum()
daily_history = daily_activity.reindex(voo.index).fillna(0)

# 3. Apply the VOO math exactly as written in logic.py
daily_history['VOO Price'] = voo['Close']
safe_voo_price = daily_history['VOO Price'].replace(0, pd.NA).ffill().bfill()

daily_history['VOO Shares Bought'] = daily_history['Cash_Flow_In'] / safe_voo_price
daily_history['VOO Shares Held'] = daily_history['VOO Shares Bought'].cumsum()

daily_history['Invested Capital'] = daily_history['Cash_Flow_In'].cumsum()
daily_history['SPY Profit (Total Value)'] = daily_history['VOO Shares Held'] * daily_history['VOO Price']

print("--- DAILY HISTORY (DATES WITH INJECTIONS) ---")
print(daily_history[daily_history['Cash_Flow_In'] > 0][['Cash_Flow_In', 'VOO Price', 'VOO Shares Bought', 'VOO Shares Held', 'Invested Capital', 'SPY Profit (Total Value)']])

print("\n--- FINAL DAY ---")
print(daily_history.iloc[-1][['Invested Capital', 'SPY Profit (Total Value)']])

