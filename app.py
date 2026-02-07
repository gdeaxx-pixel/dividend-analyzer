import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
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
    
    /* Custom Alert Boxes */
    div[data-testid="stMarkdownContainer"] > div.stAlert {
        background-color: rgba(255, 50, 50, 0.1);
        border: 1px solid #ff3333;
        color: #ffaaaa;
    }
    
    /* Math Formula Style */
    .katex { font-size: 1.2em; color: #b3b3b3; }
    
</style>
""", unsafe_allow_html=True)


st.title("DIVIDEND // ANALYZER")
st.markdown("""
<div style='margin-top: -15px; margin-bottom: 30px; color: #666; font-size: 1.1rem;'>
    AUDITORÍA FORENSE DE PORTAFOLIOS & SIMULADOR DE ESTRATEGIAS
</div>
""", unsafe_allow_html=True)


with st.expander("📚 ¿Cómo calcula la App mi Ganancia Real? (La Fórmula)"):
    st.markdown(r"""
    ### 🧮 La Fórmula de la Verdad
    Esta app busca tu rentabilidad real, separando lo que pusiste de tu bolsillo de lo que el mercado te ha dado.

    $$
    \text{Ganancia Total} = (\text{Valor Mercado} + \text{Cash}) - \text{Bolsillo}
    $$
    
    1. **🛑 Inversión de Bolsillo (Resta)**:  
       Es la "deuda" que tienes contigo mismo. Solo suma el dinero nuevo que salió de tu banco para compra de acciones.  
       *Ejemplo: Transferiste $1,000 para comprar.*

    2. **📉 Valor de Mercado (Suma)**:
       Es cuánto valen TODAS tus acciones hoy si las vendieras.
       * **Composición**: (Acciones Compradas + Acciones Ganadas por DRIP) × Precio Actual.
       * *Nota: Aquí vive el valor acumulado de tus reinversiones.*

    3. **💵 Dividendos Cash (Suma)**:  
       Es la **Suma Total** de los dividendos que cobraste en efectivo (líquido) y NO reinvertiste.
       * *Este dinero ya está "a salvo" en tu cuenta, fuera del riesgo del mercado.*

    ---
    ### 💡 Ejemplo Visual
    Imagina que compraste **10 acciones** y con el tiempo...
    - El DRIP compró **1 acción extra** (Total: 11 acciones).
    - Te pagaron **$50 en efectivo** (para la cena).

    **Tu Riqueza Real es:**
    1. Lo que valen esas **11 acciones** hoy en el mercado.
    2. MAS los **$50** que ya te gastaste.
    3. MENOS lo que te costaron las 10 originales.
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
                            "🏦 Inversión (el dinero que tu pusiste)",
                            "📉 Valor de Mercado (valor de tu inversión hoy)",
                            "💰 Div. Efectivo (dividendos pagados a tu balance)",
                            "💰 Div. Acciones (dividendos re invertidos)",
                            "💰 Total generado en dividendos (Div. Efectivo + Div. Acciones)",
                            "🟢 Ganancia en $",
                            "🟢 Ganancia en %",
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

                    st.markdown("### 🧮 Tu Verificación Rápida")
                    
                    # LaTeX Formula (Simplified for compatibility)
                    # We render the generic formula first
                    # LaTeX Formula (Simplified for compatibility)
                    # We render the generic formula first
                    # (Removed redundant single-line formula)
                    
                    # Then the inputs with specific values
                    # Determine color for the result
                    result_color = "green" if stats['net_profit'] >= 0 else "red"
                    
                    st.latex(r"""
                    \footnotesize
                    \begin{array}{r c c c c c}
                    \text{Ganancia} = & \boxed{(\text{Div. Acciones} + \text{Tus Acciones}) \times \text{Precio}} & + & \text{Div. Efectivo} & - & \text{Inversión} \\[0.5em]
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
