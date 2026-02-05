import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import datetime
import logic

st.set_page_config(page_title="Dividend Portfolio Analyzer", layout="wide")


st.title("💰 Dividend Portfolio Analyzer")
st.markdown("""
Sube tu historial de transacciones para obtener una auditoría forense de tu rendimiento, 
o simula una estrategia de dividendos teórica.
""")

# --- Sidebar: Input Method ---
with st.sidebar:
    st.header("Configuración")
    input_method = st.radio("Modo de Análisis:", ["Subir CSV/Excel", "Simulación Teórica"])

    uploaded_file = None
    if input_method == "Subir CSV/Excel":
        uploaded_file = st.file_uploader("Arrastra tu archivo aquí", type=['csv', 'xlsx'])
        st.info("El archivo debe contener columnas como: Fecha, Acción, Ticker, Cantidad, Monto.")

# --- Main Logic ---

if input_method == "Subir CSV/Excel" and uploaded_file is not None:
    st.subheader("📊 Análisis de Portafolio Real")
    
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
            
        # 1. Normalize
        df_clean = logic.normalize_csv(df)
        
        with st.expander("Ver datos procesados (Primeras 5 filas)"):
            st.dataframe(df_clean.head())
        
        # 2. Analyze
        if st.button("Ejecutar Análisis Forense"):
            with st.spinner("Analizando transacciones, splits y dividendos..."):
                results = logic.analyze_portfolio(df_clean)
                
            if not results:
                st.error("No se pudieron extraer tickers válidos o datos del archivo.")
            else:
                # Display Results per Ticker
                for ticker, stats in results.items():
                    if "error" in stats:
                        st.error(f"Error con {ticker}: {stats['error']}")
                        continue
                        
                    st.markdown(f"### Result for: **{ticker}**")
                    
                    # Create data for the requested table format
                    results_data = {
                        "Indicador": [
                            "💰 Inversión Neta (Tu Bolsillo)",
                            "📉 Valor de Mercado Actual",
                            "💵 Dividendos (Cash)",
                            "🔄 Dividendos (DRIP)",
                            "💰 Total Generado (Cash + Valor DRIP)",
                            "🟢 Ganancia Neta Total",
                            "🚀 ROI (Retorno Total)",
                            "📊 Acciones Totales (Inc. DRIP)"
                        ],
                        "Valor": [
                            f"${stats['pocket_investment']:,.2f}",
                            f"${stats['market_value']:,.2f}",
                            f"${stats['dividends_collected_cash']:,.2f}",
                            f"${stats['dividends_collected_drip']:,.2f}",
                            f"${stats['total_dividends']:,.2f}",
                            f"${stats['net_profit']:,.2f}",
                            f"{stats['roi_percent']:.2f}%",
                            f"{stats['shares_owned']:.4f}"
                        ]
                    }
                    
                    results_df = pd.DataFrame(results_data)
                    st.table(results_df)
                    
                    # --- New Chart: Evolution of Capital ---
                    if 'daily_trend' in stats and not stats['daily_trend'].empty:
                        st.subheader("📈 Evolución de Patrimonio")
                        st.line_chart(stats['daily_trend'])
                    
                    st.divider()

    except Exception as e:
        st.error(f"Error procesando el archivo: {e}")

elif input_method == "Simulación Teórica":
    st.subheader("🧪 Simulación de Estrategia DRIP")
    
    col1, col2, col3 = st.columns(3)
    ticker = col1.text_input("Ticker", "TSLY")
    start_date = col2.date_input("Fecha Inicio", datetime.date(2023, 1, 1))
    amount = col3.number_input("Inversión Inicial ($)", value=10000)
    
    if st.button("Simular"):
        with st.spinner(f"Simulando {ticker}..."):
            sim_results = logic.simulate_strategy(ticker, start_date, amount)
            
        if sim_results is None:
            st.error("No se encontraron datos o fecha inválida.")
        else:
            # Metrics
            st.success("Simulación Completada")
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Inversión Inicial", f"${amount:,.0f}")
            m2.metric("Final (DRIP)", f"${sim_results['drip_final_value']:,.2f}", 
                      delta=f"{sim_results['drip_roi_percent']:.2f}%")
            m3.metric("Final (NO-DRIP + Cash)", f"${sim_results['nodrip_final_value']:,.2f}",
                      delta=f"{sim_results['nodrip_roi_percent']:.2f}%")
            
            # Chart
            st.subheader("Evolución de Patrimonio")
            hist = sim_results['history']
            st.line_chart(hist[['DRIP Wealth', 'No-DRIP Wealth']])

else:
    st.info("👈 Selecciona una opción en el menú lateral para comenzar.")
