import streamlit as st
import pandas as pd

import datetime
import logic
import importlib
importlib.reload(logic)


st.set_page_config(page_title="Dividend Portfolio Analyzer", layout="wide", page_icon="💰")

# --- CUSTOM CSS: THE "CYBER-INSTITUTIONAL" AESTHETIC ---
# Guidelines: Bold, Dark, Neon Accents, Glassmorphism, 'Outfit' Font.
st.markdown("""
<style>
    /* 1. IMPORT FONTS */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    /* 2. GLOBAL VARIABLES */
    :root {
        --bg-color: #050505;
        --card-bg: #121212;
        --text-color: #E0E0E0;
        --accent-green: #00FF94;  /* Cyber Green */
        --accent-purple: #BC13FE; /* Cyber Purple for DRIP */
        --border-color: #2A2A2A;
    }
    
    /* 3. RESET & BASE STYLES */
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
        background-color: var(--bg-color);
        color: var(--text-color);
    }
    
    /* Hide Default Header/Footer */
    header {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* 4. TYPOGRAPHY */
    h1, h2, h3 {
        font-weight: 700;
        letter-spacing: -0.02em;
        color: white;
    }
    
    h1 {
        font-size: 3.5rem !important;
        background: linear-gradient(90deg, #FFFFFF 0%, #888888 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    
    h3 {
        color: var(--accent-green);
        text-transform: uppercase;
        font-size: 1rem !important;
        letter-spacing: 0.1em;
        margin-top: 2rem !important;
        opacity: 0.9;
    }
    
    /* 5. CARDS & CONTAINERS */
    div[data-testid="stExpander"] {
        background-color: var(--card-bg);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    }
    
    div[data-testid="stExpander"] details {
        background-color: transparent;
    }
    
    /* 6. BUTTONS */
    div.stButton > button {
        background-color: transparent;
        border: 1px solid var(--accent-green);
        color: var(--accent-green);
        border-radius: 8px;
        padding: 0.6rem 1.2rem;
        font-weight: 600;
        transition: all 0.3s ease;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    div.stButton > button:hover {
        background-color: var(--accent-green);
        color: black;
        box-shadow: 0 0 15px rgba(0, 255, 148, 0.4);
        transform: translateY(-2px);
    }
    
    /* 7. METRICS */
    div[data-testid="stMetricValue"] {
        font-size: 2.5rem !important;
        font-weight: 700;
        color: white;
    }
    
    div[data-testid="stMetricLabel"] {
        font-size: 0.9rem !important;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    div[data-testid="stMetricDelta"] svg {
        fill: var(--accent-green) !important;
    }
    
    div[data-testid="stMetricDelta"] > div {
        color: var(--accent-green) !important;
    }
    
    /* 8. DATAFRAME / TABLES */
    div[data-testid="stDataFrame"] {
        border: 1px solid var(--border-color);
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* 9. SIDEBAR */
    section[data-testid="stSidebar"] {
        background-color: #000000;
        border-right: 1px solid var(--border-color);
    }

    /* Sidebar Button Specifics (Neutral & Small) */
    section[data-testid="stSidebar"] div.stButton > button {
        color: #666666 !important;
        border: 1px solid #222222 !important;
        font-size: 0.6rem !important;
        height: auto !important;
        min-height: 0px !important;
        padding: 0.3rem 0.8rem !important;
        line-height: 1.2 !important;
    }
    
    section[data-testid="stSidebar"] div.stButton > button:hover {
        color: #E0E0E0;
        border-color: #666666;
        background-color: rgba(255,255,255,0.05);
        box-shadow: none;
        transform: none;
    }
    
    /* Custom Alert Boxes */
    div[data-testid="stMarkdownContainer"] > div.stAlert {
        background-color: rgba(255, 50, 50, 0.1);
        border: 1px solid #ff3333;
        color: #ffaaaa;
    }
    
    /* Math Formula Style */
    .katex { font-size: 1.2em; color: #b3b3b3; }
    
    /* 10. TRANSLATE FILE UPLOADER & COMPACT STYLE */
    [data-testid="stFileUploaderDropzone"] {
        min-height: 0px !important;
        padding: 0px !important;
        border: none !important;
        background-color: transparent !important;
    }
    
    [data-testid="stFileUploaderDropzone"] div {
        padding: 0px !important;
        margin: 0px !important;
    }

    [data-testid="stFileUploaderDropzone"] button {
        visibility: hidden;
        position: relative;
        height: auto !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    [data-testid="stFileUploaderDropzone"] button::after {
        content: "SUBIR ARCHIVO";
        visibility: visible;
        position: relative;
        display: inline-block;
        background-color: rgba(255, 255, 255, 0.05); /* Slight BG for visibility */
        border: 1px dashed var(--accent-green); /* Dashed to indicate dropzone */
        color: var(--accent-green);
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.75rem; /* Match sidebar button */
        padding: 0.4rem 0.8rem; /* Match sidebar button */
        text-transform: uppercase;
        cursor: pointer;
        width: 100%;
        text-align: center;
    }
    
    [data-testid="stFileUploaderDropzone"] > div > div > span {
        display: none;
    }
    [data-testid="stFileUploaderDropzone"] > div > div::before {
        display: none;
    }
    [data-testid="stFileUploaderDropzone"] > div > div > small {
        display: none;
    }

    /* 11. GLASS METRIC CARD */
    div[data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 15px;
        border-radius: 10px;
        transition: all 0.3s ease;
    }
    
    div[data-testid="stMetric"]:hover {
        background-color: rgba(255, 255, 255, 0.08); /* Lighter on hover */
        border-color: var(--accent-green);
        box-shadow: 0 0 15px rgba(0, 255, 148, 0.2);
    }
</style>
""", unsafe_allow_html=True)


st.markdown("<h1 style='margin-bottom:0px;'>DIVIDEND // ANALYZER <span style='font-size:0.3em; color:#00ff94; vertical-align:middle;'>v1.2.1</span></h1>", unsafe_allow_html=True)
st.markdown("""
<div style='margin-top: -15px; margin-bottom: 30px; color: #666; font-size: 1.1rem;'>
    AUDITORÍA FORENSE DE PORTAFOLIOS & SIMULADOR DE ESTRATEGIAS
</div>
""", unsafe_allow_html=True)




# --- Sidebar: Input Method ---
with st.sidebar:
    input_method = st.radio("Modo de Análisis:", ["Subir CSV/Excel", "Simulación Teórica"])

    uploaded_file = None
    if input_method == "Subir CSV/Excel":
        uploaded_file = st.file_uploader("Upload", type=['csv', 'xlsx'], label_visibility="collapsed")


    
    st.sidebar.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)
    if st.sidebar.button("🧹 Limpiar Caché"):
        st.cache_data.clear()
        st.rerun()

# --- Main Logic ---

if input_method == "Subir CSV/Excel" and uploaded_file is not None:
    st.subheader("📊 Análisis de Portafolio Real")
    
    try:
        if uploaded_file.name.endswith('.csv'):
            # Ultra-Robust CSV Reader
            success = False
            encodings = ['utf-8', 'latin1', 'cp1252', 'utf-16']
            separators = [None, ';', '\t'] # None = Auto-detect with python engine
            
            for encoding in encodings:
                for sep in separators:
                    try:
                        uploaded_file.seek(0)
                        df = pd.read_csv(uploaded_file, sep=sep, encoding=encoding, engine='python')
                        if len(df.columns) > 1: # Basic check: Did we parse columns?
                            success = True
                            st.toast(f"📖 Leído con éxito: {encoding} | Sep: {sep if sep else 'Auto'}", icon="✅")
                            break
                    except:
                        continue
                if success: break
            
            if not success:
               st.error("❌ No pudimos leer el formato del CSV. Intenta guardarlo como 'CSV UTF-8' o usa Excel (.xlsx).")
               st.stop()
               
        else:
            df = pd.read_excel(uploaded_file)
            
        # 1. Normalize
        df_clean = logic.normalize_csv(df)
        
        with st.expander("Ver datos procesados (Primeras 5 filas)"):
            st.dataframe(df_clean.head())

        # 1.5 Validate Columns
        required_cols = ['Date', 'Ticker', 'Amount']
        missing_cols = [col for col in required_cols if col not in df_clean.columns]
        
        if missing_cols:
            st.error(f"❌ Error de Formato: No encontramos las columnas: {', '.join(missing_cols)}")
            st.warning(f"Columnas encontradas: {list(df_clean.columns)}")
            st.info("💡 Consejo: Asegúrate de que tu autodetector de cabecera funcionó. Si tu archivo tiene muchas filas vacías al inicio, intenta borrarlas.")
            st.stop()
        
        # 2. Analyze
        if st.button("Ejecutar Análisis Forense"):
            with st.spinner("Analizando transacciones, splits y dividendos..."):
                # Use a defensive call in case version is not yet supported in memory
                try:
                    results = logic.analyze_portfolio(df_clean, version="1.2.1")
                except TypeError:
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
                            "🏦 Inversión (el dinero que tu pusiste)",
                            "📉 Valor de Mercado (valor de tu inversión hoy)",
                            "💰 Div. Efectivo (dividendos pagados a tu balance)",
                            "💰 Valor de Div. Reinvertidos",
                            "💰 Total generado en dividendos (Cash + Reinversión)",
                            "📊 Acciones Compradas",
                            "📊 Acciones por DRIP",
                            "📊 Acciones Totales",
                            "🟢 Ganancia en $",
                            "🟢 Ganancia en %"
                        ],
                        "Valor": [
                            f"${stats['pocket_investment']:,.2f}",
                            f"${stats['market_value']:,.2f}",
                            f"${stats['dividends_collected_cash']:,.2f}",
                            f"${stats['dividends_collected_drip']:,.2f}",
                            f"${stats['total_dividends']:,.2f}",
                            f"{stats.get('shares_owned_pocket', 0):.4f}",
                            f"{stats.get('shares_owned_drip', 0):.4f}",
                            f"{stats['shares_owned']:.4f}",
                            f"${stats['net_profit']:,.2f}",
                            f"{stats['roi_percent']:.2f}%"
                        ]
                    }
                    
                    results_df = pd.DataFrame(results_data)
                    
                    # Enhanced Dataframe with Progress Bar for Profit %
                    st.dataframe(
                        results_df,
                        column_config={
                            "Indicador": st.column_config.TextColumn("Métrica", width="medium"),
                            "Valor": st.column_config.TextColumn("Resultado", width="large"),
                        },
                        hide_index=True,
                        use_container_width=True
                    )

                    st.markdown("### 🧮 Tu Verificación Rápida")
                    
                    # LaTeX Formula (Corrected conceptual error: Shares + Shares, not Dollars + Shares)
                    # Determine color for the result
                    result_color = "green" if stats['net_profit'] >= 0 else "red"
                    
                    st.latex(r"""
                    \footnotesize
                    \begin{array}{r c c c c c}
                    \text{Ganancia} = & \boxed{(\text{Acciones DRIP} + \text{Acciones Compradas}) \times \text{Precio}} & + & \text{Div. Efectivo} & - & \text{Inversión} \\[0.5em]
                    & \downarrow & & & & \\[0.5em]
                    \text{Ganancia} = & \text{Valor de Mercado} & + & \text{Div. Efectivo} & - & \text{Inversión} \\[1.5em]
                    \textcolor{%s}{%s} = & %s & + & %s & - & %s
                    \end{array}
                    """ % (
                        result_color,
                        f"\\${stats['net_profit']:,.2f}",
                        f"{stats['market_value']:,.2f}", 
                        f"{stats['dividends_collected_cash']:,.2f}", 
                        f"{stats['pocket_investment']:,.2f}"
                    ))
                    
                    # Result line removed as requested

                    
                    # --- New Chart: Evolution of Capital vs S&P 500 ---
                    if 'daily_trend' in stats and not stats['daily_trend'].empty:
                        st.markdown("### 📈 SIMULACIÓN VS S&P 500 (VOO)")
                        
                        # Prepare data for chart
                        chart_data = stats['daily_trend'][['User Total Value', 'SPY Profit']].copy()
                        
                        # Rename columns for display
                        chart_data = chart_data.rename(columns={
                            'User Total Value': 'Portafolio Real ($)',
                            'SPY Profit': 'S&P 500 Simulado ($)'
                        })
                        
                        # Calculate Percentage Difference daily
                        # % Diff = (Portfolio - SPY) / SPY * 100
                        # Avoid division by zero
                        safe_spy = chart_data['S&P 500 Simulado ($)'].replace(0, pd.NA)
                        chart_data['Diferencia %'] = ((chart_data['Portafolio Real ($)'] - safe_spy) / safe_spy) * 100
                        chart_data['Diferencia %'] = chart_data['Diferencia %'].fillna(0)
                        
                        # Save the difference column before melting so we can attach it in tooltip
                        # We need to reset index to have 'Date' as a column
                        chart_data_reset = chart_data.reset_index()
                        
                        # Transform data for Altair (Long Format)
                        chart_data_long = chart_data_reset.melt(
                            id_vars=['Date', 'Diferencia %'], 
                            value_vars=['Portafolio Real ($)', 'S&P 500 Simulado ($)'],
                            var_name='Estrategia', 
                            value_name='Valor'
                        )
                        
                        import altair as alt
                        
                        base = alt.Chart(chart_data_long).encode(
                            x=alt.X('Date:T', title='Fecha'),
                            y=alt.Y('Valor:Q', title='Valor Acumulado ($)', axis=alt.Axis(format='$,.0f')), 
                            color=alt.Color('Estrategia:N', scale=alt.Scale(
                                domain=['Portafolio Real ($)', 'S&P 500 Simulado ($)'], 
                                range=['#00FF94', '#BC13FE'] # Cyber Green vs Cyber Purple
                            )),
                            tooltip=[
                                alt.Tooltip('Date:T', format='%Y-%m-%d', title='Fecha'), 
                                alt.Tooltip('Estrategia:N', title='Estrategia'), 
                                alt.Tooltip('Valor:Q', format='$,.2f', title='Valor USD'),
                                alt.Tooltip('Diferencia %:Q', format='.2f', title='Dif. vs S&P 500 (%)')
                            ]
                        )
                        
                        # Note regarding Reverse Splits:
                        # The logic in logic.py handles both forward (ratio > 1) and reverse (ratio < 1) splits correctly.
                        # For a 1-for-2 reverse split, the ratio is 0.5, which halves the share count as expected.
                        
                        chart = base.mark_line().properties(
                            height=400,
                            background='transparent'
                        ).configure_axis(
                            grid=False,
                            domainColor='#2A2A2A',
                            tickColor='#2A2A2A',
                            labelColor='#888',
                            titleColor='#888'
                        ).configure_view(
                            strokeWidth=0
                        ).configure_legend(
                            labelColor='#E0E0E0',
                            titleColor='#888'
                        )
                        
                        st.altair_chart(chart, use_container_width=True)
                    

                    st.divider()

    except Exception as e:
        import traceback
        st.error(f"Error procesando el archivo: {e}")
        with st.expander("Ver detalles del error (Stacktrace)"):
            st.code(traceback.format_exc())

elif input_method == "Simulación Teórica":
    st.subheader("🧪 Simulación de Estrategia DRIP")
    
    col1, col2, col3 = st.columns(3)
    ticker = col1.text_input("Ticker", "TSLY")
    start_date = col2.date_input("Fecha Inicio", datetime.date(2023, 1, 1))
    amount = col3.number_input("Inversión Inicial ($)", value=10000)
    
    if st.button("Simular"):
        with st.spinner(f"Simulando {ticker}..."):
            sim_results, error_msg = logic.simulate_strategy(ticker, start_date, amount)
            
        if sim_results is None:
            st.error(f"Error: {error_msg}")
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

# --- Footer Disclaimer ---
st.markdown("---")
st.markdown("""
<div style="font-size: 0.8rem; color: #888; text-align: center; margin-top: 3rem; padding-bottom: 2rem;">
    ⚠️ <b>Aviso Importante: Calculadora en Versión Beta</b><br><br>
    Esta herramienta de seguimiento de dividendos se encuentra actualmente en fase de prueba (Beta) y en desarrollo continuo. Los datos, cálculos y proyecciones que arroja son estrictamente de carácter informativo y estimativo, por lo que podrían presentar errores o inexactitudes.<br><br>
    No tomes esta información como un resultado definitivo ni como asesoría financiera. Es fundamental que siempre verifiques y compares estos números con tus propios registros, los estados de cuenta de tu casa de bolsa o tus métodos personales de seguimiento.<br><br>
    El uso de esta aplicación es bajo tu propio riesgo. ¡Agradecemos mucho tus reportes sobre cualquier fallo o inconsistencia para ayudarnos a seguir mejorando la herramienta!
</div>
""", unsafe_allow_html=True)
