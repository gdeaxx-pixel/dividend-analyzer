import sys
import os
import pandas as pd
import logic

# Path to the user's file
file_path = "../Copy of TSLY, NVDY, MSTY.xlsx"

print(f"Loading {file_path}...")
try:
    df = pd.read_excel(file_path)
    print("Columns found:", df.columns.tolist())
    
    # Normalize
    df_clean = logic.normalize_csv(df)
    
    # Filter for TSLY specifically as requested, or analyze all
    # User said "analiza el portafolio tsly"
    if 'Ticker' in df_clean.columns:
        tsly_df = df_clean[df_clean['Ticker'] == 'TSLY']
        if not tsly_df.empty:
            print("Analyzing TSLY data...")
            results = logic.analyze_portfolio(tsly_df)
        else:
            print("TSLY ticker not found, analyzing all...")
            results = logic.analyze_portfolio(df_clean)
    else:
         results = logic.analyze_portfolio(df_clean)

    for ticker, stats in results.items():
        if "error" in stats:
            print(f"Error for {ticker}: {stats['error']}")
            continue
            
        print(f"\n--- Analysis for {ticker} ---")
        print(f"Inversión Bolsillo: ${stats['pocket_investment']:,.2f}")
        print(f"Valor Mercado Hoy: ${stats['market_value']:,.2f}")
        print(f"Dividendos Cobrados (Cash): ${stats['dividends_collected_cash']:,.2f}")
        print(f"Ganancia/Pérdida Neta: ${stats['net_profit']:,.2f}")
        print(f"ROI: {stats['roi_percent']:.2f}%")
        print(f"Acciones Totales: {stats['shares_owned']:.4f}")
        print(f"Precio Actual: ${stats['current_price']:.2f}")

except Exception as e:
    print(f"FATAL ERROR: {e}")
    import traceback
    traceback.print_exc()
