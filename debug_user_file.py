import logic
import pandas as pd
import sys

def debug_user_file():
    file_path = "/Users/danielzambrano/Desktop/Individual_XXX550_Transactions_20260210-131439.csv"
    print(f"Loading file: {file_path}")
    
    try:
        # Mimic app.py loading logic
        df = pd.read_csv(file_path) # Auto-detect separator usually works for comma
        print(f"Raw columns: {df.columns.tolist()}")
        print(f"First 5 rows:\n{df.head()}")
        
        print("\n--- Normalizing ---")
        df_clean = logic.normalize_csv(df)
        print(f"Normalized columns: {df_clean.columns.tolist()}")
        print(f"Normalized data head:\n{df_clean.head()}")
        
        print("\n--- Analysing tickers ---")
        tickers = df_clean['Ticker'].unique()
        print(f"Found tickers: {tickers}")
        
        for t in tickers:
            print(f"Checking ticker '{t}' (Length: {len(t)})")
            # explicitly check for hidden characters
            print(f"ASCII values: {[ord(c) for c in t]}")
            
        print("\n--- Running Analysis ---")
        results = logic.analyze_portfolio(df_clean)
        
        for ticker, res in results.items():
            if "error" in res:
                print(f"ERROR for {ticker}: {res['error']}")
            else:
                print(f"SUCCESS for {ticker}: Market Value = {res.get('market_value')}")
                
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_user_file()
