import pandas as pd
import os
import sys

# Add current dir to path to import logic
sys.path.append(os.getcwd())
import logic

def run_test():
    print("🚀 Iniciando Validación de Lógica...")
    
    # Path del CSV de referencia (Ground Truth)
    csv_path = "../CONY 3-15-2026 Individual_XXX535_Transactions_20260315-155550.csv"
    
    if not os.path.exists(csv_path):
        print(f"❌ Error: No se encontró el archivo de referencia en {csv_path}")
        return

    try:
        # 1. Leer y normalizar
        df = pd.read_csv(csv_path)
        df_clean = logic.normalize_csv(df)
        
        # 2. Mocking Fetch Data (para evitar llamadas a API durante el test)
        original_fetch = logic.fetch_market_data
        class MockMarketData:
            def __getitem__(self, key):
                return pd.Series([31.434], index=[pd.Timestamp('2026-03-15')])
            @property
            def empty(self): return False
            @property
            def index(self): return pd.DatetimeIndex(['2026-03-15'])
            def __len__(self): return 1
            
        def mock_fetch(ticker, start_date):
            # Mock close price and actions
            data = pd.DataFrame({
                'Close': [31.434],
                'Dividends': [0.0],
                'Stock Splits': [0.0],
                'VOO Price': [450.0]
            }, index=[pd.Timestamp('2026-03-15')])
            return data, None
            
        logic.fetch_market_data = mock_fetch
        
        # 3. Analizar
        results = logic.analyze_portfolio(df_clean, version="TEST_RUN")
        
        for ticker, stats in results.items():
            print(f"\n✅ RESULTADOS PARA {ticker}:")
            print(f"   - Inversión: ${stats['pocket_investment']:.2f} (Esperado: $311.46)")
            print(f"   - Acciones Compradas: {stats['shares_owned_pocket']:.4f} (Esperado: 10.0000)")
            print(f"   - Acciones por DRIP: {stats['shares_owned_drip']:.4f} (Esperado: 0.1675)")
            print(f"   - Acciones Totales: {stats['shares_owned']:.4f} (Esperado: 10.1675)")
            print(f"   - Valor Reinvertido: ${stats['dividends_collected_drip']:.2f} (Esperado: $5.11)")
            
            # Validaciones Atómicas
            assert round(stats['pocket_investment'], 2) == 311.46, "Error en Inversión"
            assert round(stats['shares_owned'], 4) == 10.1675, "Error en Acciones Totales"
            print("\n💯 ¡VALIDACIÓN EXITOSA! Los cálculos coinciden con el Ground Truth.")
            
    except Exception as e:
        print(f"❌ FALLO EN LA PRUEBA: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logic.fetch_market_data = original_fetch

if __name__ == "__main__":
    run_test()
