import streamlit as st
import pandas as pd

import datetime
import logic


st.set_page_config(page_title="Dividend Portfolio Analyzer", layout="wide", page_icon="💰")

# --- CUSTOM CSS: THE ARCHITECTURAL AUTHORITY — SURFACE MODE ---
# Sistema de diseño: Invierte & Gana / tonal layering light
# Paleta: surface #fcf9f8 → surface-low #f6f3f2 → surface-high #eae7e7
# Anclajes oscuros: #021C36 (tabla header, footer, tooltips)
st.markdown("""
<style>
    /* 1. IMPORT FONTS */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Cinzel:wght@700&display=swap');

    /* 2. DESIGN TOKENS — Invierte & Gana Surface System */
    :root {
        --surface:           #fcf9f8;
        --surface-low:       #f6f3f2;
        --surface-high:      #eae7e7;
        --on-surface:        #1a1a1a;
        --on-surface-muted:  #555555;
        --on-primary:        #ffffff;
        --electric-blue:     #006497;
        --electric-hover:    #004f79;
        --electric-light:    rgba(0, 100, 151, 0.08);
        --primary:           #000000;
        --primary-container: #021C36;
        --logo-blue:         #0086d4;
        --shadow-sm:         rgba(26, 26, 26, 0.06);
        --shadow-md:         rgba(26, 26, 26, 0.08);
    }

    /* 3. RESET GLOBAL */
    html, body,
    [data-testid="stApp"],
    [data-testid="stAppViewContainer"],
    .main, .block-container {
        font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
        background-color: var(--surface) !important;
        color: var(--on-surface) !important;
    }

    header { visibility: hidden; }
    footer { visibility: hidden; }

    /* 4. TIPOGRAFÍA */
    h1, h2, h3 {
        font-family: 'Inter', sans-serif !important;
        font-weight: 800 !important;
        letter-spacing: -0.02em !important;
        color: var(--on-surface) !important;
    }
    h3 {
        color: var(--electric-blue) !important;
        text-transform: uppercase !important;
        font-size: 0.85rem !important;
        letter-spacing: 0.10em !important;
        font-weight: 500 !important;
        margin-top: 2rem !important;
    }

    /* 5. SIDEBAR — surface-low */
    section[data-testid="stSidebar"] {
        background-color: var(--surface-low) !important;
        border-right: none !important;
        box-shadow: 2px 0 8px var(--shadow-md);
    }
    section[data-testid="stSidebar"] * {
        color: var(--on-surface) !important;
    }
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] p {
        font-size: 11px !important;
        font-weight: 500 !important;
        letter-spacing: 0.10em !important;
        text-transform: uppercase !important;
        color: var(--on-surface-muted) !important;
    }
    section[data-testid="stSidebar"] div.stButton > button {
        background-color: transparent !important;
        color: var(--on-surface-muted) !important;
        border: 1px solid var(--surface-high) !important;
        border-radius: 0px !important;
        font-size: 0.65rem !important;
        padding: 0.3rem 0.8rem !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
    }
    section[data-testid="stSidebar"] div.stButton > button:hover {
        border-color: var(--electric-blue) !important;
        color: var(--electric-blue) !important;
        background-color: var(--electric-light) !important;
        box-shadow: none !important;
    }

    /* 6. BOTONES — Electric Blue CTA */
    div.stButton > button {
        background-color: var(--electric-blue) !important;
        color: var(--on-primary) !important;
        border: none !important;
        border-radius: 9999px !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        letter-spacing: 0.05em !important;
        text-transform: uppercase !important;
        padding: 0.6rem 1.5rem !important;
        transition: background-color 0.2s ease !important;
    }
    div.stButton > button:hover {
        background-color: var(--electric-hover) !important;
        box-shadow: 0 0 24px rgba(0, 100, 151, 0.20) !important;
    }

    /* 7. MÉTRICAS — surface-high cards */
    div[data-testid="stMetric"] {
        background-color: var(--surface-high) !important;
        padding: 20px 24px !important;
        border-radius: 0px !important;
        box-shadow: 0 2px 8px var(--shadow-md) !important;
        transition: box-shadow 0.2s ease !important;
    }
    div[data-testid="stMetric"]:hover {
        box-shadow: 0 4px 16px var(--shadow-md) !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 2.5rem !important;
        font-weight: 800 !important;
        letter-spacing: -0.02em !important;
        color: var(--on-surface) !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 10px !important;
        font-weight: 500 !important;
        letter-spacing: 0.10em !important;
        text-transform: uppercase !important;
        color: var(--on-surface-muted) !important;
    }
    div[data-testid="stMetricDelta"] svg { fill: var(--electric-blue) !important; }
    div[data-testid="stMetricDelta"] > div { color: var(--electric-blue) !important; }

    /* 8. DATAFRAME / TABLA */
    div[data-testid="stDataFrame"] {
        border-radius: 0px !important;
        overflow: hidden;
        box-shadow: 0 2px 8px var(--shadow-md);
    }

    /* 9. EXPANDER — surface-low */
    div[data-testid="stExpander"] {
        background-color: var(--surface-low) !important;
        border-radius: 0px !important;
        box-shadow: 0 2px 8px var(--shadow-sm) !important;
    }
    div[data-testid="stExpander"] details {
        background-color: transparent !important;
    }

    /* 10. INPUTS */
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stDateInput"] input {
        background-color: var(--surface-high) !important;
        color: var(--on-surface) !important;
        border: none !important;
        border-bottom: 1px solid var(--surface-high) !important;
        border-radius: 0px !important;
        font-family: 'Inter', sans-serif !important;
    }
    [data-testid="stTextInput"] input:focus,
    [data-testid="stNumberInput"] input:focus {
        border-bottom-color: var(--electric-blue) !important;
        outline: none !important;
    }

    /* 11. FILE UPLOADER */
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
        background-color: var(--electric-light);
        border: 1px dashed var(--electric-blue);
        color: var(--electric-blue);
        border-radius: 0px;
        font-weight: 600;
        font-size: 0.75rem;
        padding: 0.4rem 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        cursor: pointer;
        width: 100%;
        text-align: center;
    }
    [data-testid="stFileUploaderDropzone"] > div > div > span,
    [data-testid="stFileUploaderDropzone"] > div > div::before,
    [data-testid="stFileUploaderDropzone"] > div > div > small {
        display: none;
    }

    /* 12. ALERTS */
    div[data-testid="stAlert"] {
        border-radius: 0px !important;
        border-left: 3px solid var(--electric-blue) !important;
        background-color: var(--electric-light) !important;
        color: var(--on-surface) !important;
    }

    /* 13. LATEX */
    .katex { font-size: 1.1em; color: var(--on-surface) !important; }

    /* 14. ALTAIR TOOLTIP — anclaje oscuro deliberado */
    .vg-tooltip {
        background-color: var(--primary-container) !important;
        color: var(--on-primary) !important;
        border: none !important;
        border-radius: 0px !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 12px !important;
        padding: 10px 14px !important;
        box-shadow: 0 4px 16px rgba(26, 26, 26, 0.15) !important;
    }
</style>
""", unsafe_allow_html=True)


st.markdown("""
<div style="padding: 40px 0 0 0; background-color: #fcf9f8;">
    <h1 style="
        font-family: 'Inter', sans-serif;
        font-size: 2.8rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        color: #1a1a1a;
        margin-bottom: 6px;
        line-height: 1.1;
    ">
        DIVIDEND <span style="color:#006497;">//</span> ANALYZER
        <span style="
            font-size: 0.28em;
            font-weight: 500;
            letter-spacing: 0.10em;
            text-transform: uppercase;
            color: #555555;
            vertical-align: middle;
            margin-left: 12px;
        ">v1.2.1</span>
    </h1>
    <p style="
        font-family: 'Inter', sans-serif;
        font-size: 0.85rem;
        font-weight: 500;
        letter-spacing: 0.10em;
        text-transform: uppercase;
        color: #555555;
        margin: 0 0 20px 0;
    ">Auditoría forense de portafolios &amp; simulador de estrategias</p>
    <div style="width: 48px; height: 2px; background-color: #006497; margin-bottom: 32px;"></div>
</div>
""", unsafe_allow_html=True)




# --- Paleta Python para Altair (Altair no interpreta CSS vars) ---
CHART_PALETTE = {
    "portfolio": "#006497",        # Electric Blue
    "sp500":     "#8a8a8a",        # Gris neutro referencia
    "axis":      "#555555",        # on-surface-muted
    "grid":      "rgba(26,26,26,0.08)",
    "bg":        "#fcf9f8",        # surface
    "title":     "#1a1a1a",        # on-surface
}

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

# --- Utilidad de formateo para métricas cuantitativas ---
def fmt_ratio(val, decimales=2, sufijo=""):
    if val is None: return "N/A"
    return f"{val:.{decimales}f}{sufijo}"

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
                    except Exception:
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
                    
                    # --- Métricas de Riesgo Ajustado (quant-analyst) ---
                    st.markdown("### 📐 MÉTRICAS DE RIESGO AJUSTADO")
                    qr1, qr2, qr3 = st.columns(3)
                    qr1.metric("Sharpe Ratio",       fmt_ratio(stats.get('sharpe_ratio')))
                    qr2.metric("Sortino Ratio",      fmt_ratio(stats.get('sortino_ratio')))
                    qr3.metric("Max Drawdown",       fmt_ratio(stats.get('max_drawdown'), sufijo="%"))

                    qr4, qr5, qr6 = st.columns(3)
                    qr4.metric("Beta vs VOO",        fmt_ratio(stats.get('beta_vs_voo')))
                    qr5.metric("Alpha Anualizado",   fmt_ratio(stats.get('alpha_anualizado'), sufijo="%"))
                    qr6.metric("Volatilidad Anual",  fmt_ratio(stats.get('volatilidad_anualizada'), sufijo="%"))

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
                                range=[CHART_PALETTE["portfolio"], CHART_PALETTE["sp500"]]
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

                        # Área bajo la curva solo para el portafolio (mejora visual premium)
                        area = alt.Chart(chart_data_long[chart_data_long['Estrategia'] == 'Portafolio Real ($)']).mark_area(
                            opacity=0.08,
                            color=CHART_PALETTE["portfolio"],
                            interpolate='monotone'
                        ).encode(
                            x=alt.X('Date:T'),
                            y=alt.Y('Valor:Q')
                        )

                        chart = (area + base.mark_line(strokeWidth=2.5, interpolate='monotone')).properties(
                            height=400,
                            background=CHART_PALETTE["bg"]
                        ).configure_view(
                            strokeOpacity=0,
                            fill=CHART_PALETTE["bg"]
                        ).configure_axis(
                            grid=True,
                            gridColor=CHART_PALETTE["grid"],
                            domainColor=CHART_PALETTE["axis"],
                            tickColor=CHART_PALETTE["axis"],
                            labelColor=CHART_PALETTE["axis"],
                            titleColor=CHART_PALETTE["title"],
                            labelFont='Inter, system-ui, sans-serif',
                            titleFont='Inter, system-ui, sans-serif',
                            labelFontSize=11,
                            titleFontSize=12,
                            titleFontWeight=500
                        ).configure_legend(
                            labelColor=CHART_PALETTE["title"],
                            titleColor=CHART_PALETTE["axis"],
                            labelFont='Inter, system-ui, sans-serif',
                            titleFont='Inter, system-ui, sans-serif',
                            labelFontSize=12,
                            titleFontSize=10,
                            titleFontWeight=500,
                            strokeColor='transparent',
                            fillColor=CHART_PALETTE["bg"],
                            padding=12,
                            cornerRadius=0
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
            sim_results, error_msg = logic.simulate_strategy_cached(ticker, start_date.isoformat(), amount)
            
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

# --- Footer Disclaimer — The Architectural Authority, anclaje #021C36 ---
FOOTER_STYLE = "background-color:#021C36;padding:40px 48px;margin-top:48px;border-top:2px solid #006497;"
BADGE_STYLE  = "display:inline-block;font-family:'Inter',sans-serif;font-size:10px;font-weight:500;letter-spacing:0.12em;text-transform:uppercase;color:#006497;border:1px solid #006497;padding:4px 10px;"
TITLE_STYLE  = "font-family:'Inter',sans-serif;font-size:14px;font-weight:700;letter-spacing:-0.01em;color:#fcf9f8;margin:16px 0 20px 0;max-width:680px;line-height:1.4;"
BODY1_STYLE  = "font-family:'Inter',sans-serif;font-size:12px;color:rgba(252,249,248,0.55);line-height:1.7;margin:0 0 12px 0;max-width:680px;"
BODY2_STYLE  = "font-family:'Inter',sans-serif;font-size:12px;color:rgba(252,249,248,0.35);line-height:1.7;margin:0;max-width:680px;"

st.markdown(
    f'<div style="{FOOTER_STYLE}">'
    f'<span style="{BADGE_STYLE}">Versión Beta</span>'
    f'<p style="{TITLE_STYLE}">Esta herramienta es de carácter informativo y estimativo — no constituye asesoría financiera.</p>'
    f'<p style="{BODY1_STYLE}">Los datos, cálculos y proyecciones pueden presentar errores o inexactitudes. Siempre verifica con tus propios registros o los estados de cuenta de tu casa de bolsa.</p>'
    f'<p style="{BODY2_STYLE}">El uso de esta aplicación es bajo tu propio riesgo. Reporta cualquier fallo o inconsistencia para ayudarnos a seguir mejorando.</p>'
    '</div>',
    unsafe_allow_html=True
)
