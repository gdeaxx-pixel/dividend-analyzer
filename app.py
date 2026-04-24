import streamlit as st
import pandas as pd

import datetime
import logic
import json


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

    /* 15. TABS — Portafolio A / B prominentes */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0 !important;
        background-color: var(--surface-high) !important;
        padding: 0 !important;
        border-radius: 0 !important;
    }
    .stTabs [data-baseweb="tab"] {
        height: 52px !important;
        background-color: var(--surface-high) !important;
        border-radius: 0 !important;
        color: var(--on-surface-muted) !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 11px !important;
        font-weight: 600 !important;
        letter-spacing: 0.10em !important;
        text-transform: uppercase !important;
        padding: 0 32px !important;
        border: none !important;
        border-bottom: 3px solid transparent !important;
        transition: color 0.15s ease, border-color 0.15s ease !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: var(--electric-blue) !important;
        background-color: var(--surface) !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: var(--surface) !important;
        color: var(--electric-blue) !important;
        border-bottom: 3px solid var(--electric-blue) !important;
    }
    /* Ocultar la línea gris debajo del tab list que Streamlit agrega */
    .stTabs [data-baseweb="tab-highlight"] { display: none !important; }
    .stTabs [data-baseweb="tab-border"]    { display: none !important; }
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
        ">v2.0</span>
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
        if uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file)
            broker = 'generic'
        else:
            df, broker = logic.load_and_detect_csv(uploaded_file)
            if df.empty:
                st.error("❌ No pudimos leer el formato del CSV. Intenta guardarlo como 'CSV UTF-8' o usa Excel (.xlsx).")
                st.stop()

        # Section A — Broker badge
        BROKER_LABELS = {'schwab': 'Charles Schwab', 'ibkr': 'Interactive Brokers', 'generic': 'Formato Genérico'}
        BROKER_COLORS = {'schwab': '#006497', 'ibkr': '#c8102e', 'generic': '#555555'}
        broker_label = BROKER_LABELS.get(broker, broker.upper())
        broker_color = BROKER_COLORS.get(broker, '#555555')
        st.markdown(f'<div style="display:inline-block;background-color:{broker_color};color:#ffffff;font-family:Inter,sans-serif;font-size:11px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;padding:4px 12px;margin-bottom:12px;">BROKER DETECTADO: {broker_label}</div>', unsafe_allow_html=True)

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
                try:
                    results = logic.analyze_portfolio(df_clean, version="2.0")
                except TypeError:
                    results = logic.analyze_portfolio(df_clean)

            if not results:
                st.error("No se pudieron extraer tickers válidos o datos del archivo.")
            else:
                # v2.1 — Separar tickers descartados (mode_skip) de los válidos
                skipped_tickers = {t: s for t, s in results.items() if s.get("skipped")}
                valid_results   = {t: s for t, s in results.items() if not s.get("skipped")}

                # classify_map solo sobre válidos
                classify_map = logic.classify_tickers(list(valid_results.keys()))

                # Mostrar descartados si los hay
                if skipped_tickers:
                    with st.expander(f"⏩ {len(skipped_tickers)} ticker(s) excluidos del análisis"):
                        for t, s in skipped_tickers.items():
                            reason = s.get('reason', '')
                            if reason == 'not_known_etf':
                                reason_label = 'No reconocido como ETF de largo plazo (acción individual, ETF inverso o apalancado)'
                            elif reason == 'held_less_than_14_days':
                                reason_label = f'Posición cerrada en {s.get("holding_days", "?")} días (< 2 semanas)'
                            else:
                                reason_label = 'Excluido'
                            st.markdown(f'<p style="font-family:Inter,sans-serif;font-size:12px;color:#555555;margin:2px 0;">— <b>{t}</b> · <span style="color:#888888;">{reason_label}</span></p>', unsafe_allow_html=True)

                # Usar valid_results para todo el análisis
                results = valid_results

                if not results:
                    st.warning("Todos los tickers del archivo fueron descartados. Asegúrate de subir transacciones de ETFs conocidos (VTI, VOO, TSLY, etc.).")
                    st.stop()

                # ── Portfolio Global Summary ──────────────────────────────
                total_invested = sum(s.get('pocket_investment', 0) for s in results.values() if 'error' not in s)
                total_market   = sum(s.get('market_value', 0)      for s in results.values() if 'error' not in s)
                total_divs     = sum(s.get('dividends_collected_cash', 0) + s.get('dividends_collected_drip', 0)
                                     for s in results.values() if 'error' not in s)
                total_gain     = (total_market + sum(s.get('dividends_collected_cash', 0)
                                     for s in results.values() if 'error' not in s)) - total_invested
                total_roi      = (total_gain / total_invested * 100) if total_invested else 0

                st.markdown("### 💼 RESUMEN GLOBAL DEL PORTAFOLIO")
                sg1, sg2, sg3, sg4, sg5 = st.columns(5)
                sg1.metric("Total Invertido",    f"${total_invested:,.2f}")
                sg2.metric("Valor de Mercado",   f"${total_market:,.2f}")
                sg3.metric("Ganancia / Pérdida",
                           f"${total_gain:,.2f}",
                           delta=f"{total_roi:.2f}%",
                           delta_color="normal")
                sg4.metric("Dividendos Totales", f"${total_divs:,.2f}")
                sg5.metric("Posiciones Activas", f"{len(results)}")
                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

                # Section B — Classification pills header
                mode_a_tickers = [t for t, m in classify_map.items() if m == 'mode_a']
                mode_b_tickers = [t for t, m in classify_map.items() if m == 'mode_b']

                st.markdown("### 📊 CLASIFICACIÓN DE PORTAFOLIO")
                b_col1, b_col2 = st.columns(2)
                with b_col1:
                    st.markdown("**MODO A — YieldMax (Income)**")
                    pills_a = " ".join([f'<span style="display:inline-block;background-color:#c8102e;color:#fff;font-family:Inter,sans-serif;font-size:10px;font-weight:600;letter-spacing:0.08em;padding:2px 8px;margin:2px;border-radius:9999px;">{t}</span>' for t in mode_a_tickers]) or '<span style="color:#888;font-size:12px;">Ninguno</span>'
                    st.markdown(pills_a, unsafe_allow_html=True)
                with b_col2:
                    st.markdown("**MODO B — ETFs de Crecimiento**")
                    pills_b = " ".join([f'<span style="display:inline-block;background-color:#006497;color:#fff;font-family:Inter,sans-serif;font-size:10px;font-weight:600;letter-spacing:0.08em;padding:2px 8px;margin:2px;border-radius:9999px;">{t}</span>' for t in mode_b_tickers]) or '<span style="color:#888;font-size:12px;">Ninguno</span>'
                    st.markdown(pills_b, unsafe_allow_html=True)

                st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

                # ── TABS: Portafolio A / Portafolio B ──────────────────────
                tab_a, tab_b = st.tabs([
                    f"💰 Portafolio A — YieldMax ({len(mode_a_tickers)})",
                    f"📈 Portafolio B — ETFs de Crecimiento ({len(mode_b_tickers)})",
                ])

                # ── Helper: render quant metrics + SPY chart (shared) ──────
                def render_quant_and_chart(stats, ticker=""):
                    import altair as alt
                    st.markdown("### 📐 MÉTRICAS DE RIESGO AJUSTADO")
                    qr1, qr2, qr3 = st.columns(3)
                    qr1.metric("Sharpe Ratio",      fmt_ratio(stats.get('sharpe_ratio')))
                    qr2.metric("Sortino Ratio",     fmt_ratio(stats.get('sortino_ratio')))
                    qr3.metric("Max Drawdown",      fmt_ratio(stats.get('max_drawdown'), sufijo="%"))
                    qr4, qr5, qr6 = st.columns(3)
                    qr4.metric("Beta vs VOO",       fmt_ratio(stats.get('beta_vs_voo')))
                    qr5.metric("Alpha Anualizado",  fmt_ratio(stats.get('alpha_anualizado'), sufijo="%"))
                    qr6.metric("Volatilidad Anual", fmt_ratio(stats.get('volatilidad_anualizada'), sufijo="%"))

                    if 'daily_trend' in stats and not stats['daily_trend'].empty:
                        st.markdown("### 📈 SIMULACIÓN VS S&P 500 (VOO)")
                        port_label = f"{ticker} ($)" if ticker else "Portafolio Real ($)"
                        chart_data = stats['daily_trend'][['User Total Value', 'SPY Profit']].copy()
                        chart_data = chart_data.rename(columns={
                            'User Total Value': port_label,
                            'SPY Profit': 'S&P 500 Simulado ($)'
                        })
                        safe_spy = chart_data['S&P 500 Simulado ($)'].replace(0, pd.NA)
                        chart_data['Diferencia %'] = ((chart_data[port_label] - safe_spy) / safe_spy) * 100
                        chart_data['Diferencia %'] = chart_data['Diferencia %'].fillna(0)
                        chart_data_long = chart_data.reset_index().melt(
                            id_vars=['Date', 'Diferencia %'],
                            value_vars=[port_label, 'S&P 500 Simulado ($)'],
                            var_name='Estrategia', value_name='Valor'
                        )
                        base = alt.Chart(chart_data_long).encode(
                            x=alt.X('Date:T', title='Fecha'),
                            y=alt.Y('Valor:Q', title='Valor Acumulado ($)', axis=alt.Axis(format='$,.0f')),
                            color=alt.Color('Estrategia:N', scale=alt.Scale(
                                domain=[port_label, 'S&P 500 Simulado ($)'],
                                range=[CHART_PALETTE["portfolio"], CHART_PALETTE["sp500"]]
                            )),
                            tooltip=[
                                alt.Tooltip('Date:T', format='%Y-%m-%d', title='Fecha'),
                                alt.Tooltip('Estrategia:N', title='Estrategia'),
                                alt.Tooltip('Valor:Q', format='$,.2f', title='Valor USD'),
                                alt.Tooltip('Diferencia %:Q', format='.2f', title='Dif. vs S&P 500 (%)')
                            ]
                        )
                        area = alt.Chart(chart_data_long[chart_data_long['Estrategia'] == port_label]).mark_area(
                            opacity=0.08, color=CHART_PALETTE["portfolio"], interpolate='monotone'
                        ).encode(x=alt.X('Date:T'), y=alt.Y('Valor:Q'))
                        chart = (area + base.mark_line(strokeWidth=2.5, interpolate='monotone')).properties(
                            height=400, background=CHART_PALETTE["bg"]
                        ).configure_view(
                            strokeOpacity=0, fill=CHART_PALETTE["bg"]
                        ).configure_axis(
                            grid=True, gridColor=CHART_PALETTE["grid"], domainColor=CHART_PALETTE["axis"],
                            tickColor=CHART_PALETTE["axis"], labelColor=CHART_PALETTE["axis"],
                            titleColor=CHART_PALETTE["title"], labelFont='Inter, system-ui, sans-serif',
                            titleFont='Inter, system-ui, sans-serif', labelFontSize=11, titleFontSize=12, titleFontWeight=500
                        ).configure_legend(
                            labelColor=CHART_PALETTE["title"], titleColor=CHART_PALETTE["axis"],
                            labelFont='Inter, system-ui, sans-serif', titleFont='Inter, system-ui, sans-serif',
                            labelFontSize=12, titleFontSize=10, titleFontWeight=500,
                            strokeColor='transparent', fillColor=CHART_PALETTE["bg"], padding=12, cornerRadius=0
                        )
                        st.altair_chart(chart, use_container_width=True)

                # ── TAB A — YieldMax (Income) ──────────────────────────────
                with tab_a:
                    shown_a = False
                    for ticker, stats in results.items():
                        if classify_map.get(ticker) != 'mode_a':
                            continue
                        if "error" in stats:
                            st.error(f"Error con {ticker}: {stats['error']}")
                            continue
                        shown_a = True
                        st.markdown(f"### **{ticker}**")

                        if stats.get('history_incomplete'):
                            st.warning(f"⚠️ {ticker}: El CSV no contiene el historial completo de compras. Algunas ventas exceden las compras registradas — las métricas de riesgo (volatilidad, beta, alpha) pueden estar subestimadas. Exporta un CSV con historial desde el inicio de tu posición para resultados precisos.")

                        # DEBUG TEMPORAL — remover después
                        _mv = stats.get('market_value', 0)
                        _sh = stats.get('shares_owned', 0)
                        _pr = (_mv / _sh) if _sh else 0
                        _dc = stats.get('dividends_collected_cash', 0)
                        _pi = stats.get('pocket_investment', 0)
                        _np = _mv + _dc - _pi
                        _ri = (_np / _pi * 100) if _pi else 0
                        st.info(f"DEBUG {ticker}: precio={_pr:.4f} | shares={_sh:.4f} | market_value={_mv:.2f} | div_cash={_dc:.2f} | pocket={_pi:.2f} | net_profit={_np:.2f} | roi_calc={_ri:.2f}% | roi_stored={stats.get('roi_percent',0):.2f}%")

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
                        st.dataframe(
                            pd.DataFrame(results_data),
                            column_config={
                                "Indicador": st.column_config.TextColumn("Métrica", width="medium"),
                                "Valor": st.column_config.TextColumn("Resultado", width="large"),
                            },
                            hide_index=True, use_container_width=True
                        )

                        st.markdown("### 🧮 Tu Verificación Rápida")
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

                        # Section D — Monthly income calendar
                        monthly_income = stats.get('monthly_income')
                        if monthly_income is not None and not monthly_income.empty:
                            import altair as alt
                            st.markdown("### 📅 CALENDARIO DE INCOME MENSUAL")
                            yoc = stats.get('yield_on_cost', 0)
                            st.markdown(f'<p style="font-family:Inter,sans-serif;font-size:12px;color:#555555;margin:0 0 8px 0;">Yield on Cost: <b style="color:#006497;">{yoc:.2f}%</b> anual sobre tu capital invertido</p>', unsafe_allow_html=True)
                            income_df = monthly_income.reset_index()
                            income_df.columns = ['Mes', 'Dividendo']
                            income_chart = alt.Chart(income_df).mark_bar(color='#c8102e', opacity=0.85).encode(
                                x=alt.X('Mes:O', title='Mes', sort=None),
                                y=alt.Y('Dividendo:Q', title='Dividendo ($)', axis=alt.Axis(format='$,.2f')),
                                tooltip=[alt.Tooltip('Mes:O', title='Mes'), alt.Tooltip('Dividendo:Q', format='$,.2f', title='Ingreso')]
                            ).properties(height=200, background=CHART_PALETTE["bg"]).configure_view(
                                strokeOpacity=0, fill=CHART_PALETTE["bg"]
                            ).configure_axis(
                                grid=True, gridColor=CHART_PALETTE["grid"], domainColor=CHART_PALETTE["axis"],
                                tickColor=CHART_PALETTE["axis"], labelColor=CHART_PALETTE["axis"],
                                titleColor=CHART_PALETTE["title"], labelFont='Inter, system-ui, sans-serif',
                                titleFont='Inter, system-ui, sans-serif', labelFontSize=10, titleFontSize=11, titleFontWeight=500
                            )
                            st.altair_chart(income_chart, use_container_width=True)

                        render_quant_and_chart(stats, ticker)
                        st.divider()

                    if not shown_a:
                        st.info("No hay posiciones YieldMax activas en este portafolio.")

                # ── TAB B — ETFs de Crecimiento ────────────────────────────
                with tab_b:
                    shown_b = False
                    for ticker, stats in results.items():
                        if classify_map.get(ticker) != 'mode_b':
                            continue
                        if "error" in stats:
                            st.error(f"Error con {ticker}: {stats['error']}")
                            continue
                        shown_b = True
                        st.markdown(f"### **{ticker}**")

                        if stats.get('history_incomplete'):
                            st.warning(f"⚠️ {ticker}: El CSV no contiene el historial completo de compras. Algunas ventas exceden las compras registradas — las métricas de riesgo (volatilidad, beta, alpha) pueden estar subestimadas. Exporta un CSV con historial desde el inicio de tu posición para resultados precisos.")

                        cagr_str = f"{stats['cagr']:.2f}%" if stats.get('cagr') is not None else "N/A"
                        bc1, bc2, bc3, bc4 = st.columns(4)
                        bc1.metric("Inversión", f"${stats['pocket_investment']:,.2f}")
                        bc2.metric("Valor Actual", f"${stats['market_value']:,.2f}")
                        ganancia = stats['market_value'] - stats['pocket_investment']
                        bc3.metric("Ganancia $", f"${ganancia:,.2f}", delta=f"{stats['roi_percent']:.2f}%")
                        bc4.metric("CAGR", cagr_str)
                        shares_net = stats.get('shares_bought', 0) - stats.get('shares_sold', 0)
                        st.markdown(f'<p style="font-family:Inter,sans-serif;font-size:12px;color:#555555;margin:4px 0 16px 0;">Acciones compradas: <b>{stats.get("shares_bought", 0):.4f}</b> · Vendidas: <b>{stats.get("shares_sold", 0):.4f}</b> · Netas: <b>{shares_net:.4f}</b></p>', unsafe_allow_html=True)

                        # Mode B dividends (VTI, SCHB, SCHD pay quarterly cash dividends)
                        b_monthly = stats.get('monthly_income')
                        if b_monthly is not None and not b_monthly.empty:
                            import altair as alt
                            b_yoc = stats.get('yield_on_cost', 0)
                            b_total_div = stats.get('dividends_collected_cash', 0)
                            st.markdown("### 💵 DIVIDENDOS COBRADOS")
                            bd1, bd2 = st.columns(2)
                            bd1.metric("Total Dividendos", f"${b_total_div:,.2f}")
                            bd2.metric("Yield on Cost", f"{b_yoc:.2f}%" if b_yoc else "—")
                            b_income_df = b_monthly.reset_index()
                            b_income_df.columns = ['Mes', 'Dividendo']
                            b_income_chart = alt.Chart(b_income_df).mark_bar(color='#006497', opacity=0.85).encode(
                                x=alt.X('Mes:O', title='Mes', sort=None),
                                y=alt.Y('Dividendo:Q', title='Dividendo ($)', axis=alt.Axis(format='$,.2f')),
                                tooltip=[alt.Tooltip('Mes:O', title='Mes'), alt.Tooltip('Dividendo:Q', format='$,.2f', title='Ingreso')]
                            ).properties(height=160, background=CHART_PALETTE["bg"]).configure_view(
                                strokeOpacity=0, fill=CHART_PALETTE["bg"]
                            ).configure_axis(
                                grid=True, gridColor=CHART_PALETTE["grid"], domainColor=CHART_PALETTE["axis"],
                                tickColor=CHART_PALETTE["axis"], labelColor=CHART_PALETTE["axis"],
                                titleColor=CHART_PALETTE["title"], labelFont='Inter, system-ui, sans-serif',
                                titleFont='Inter, system-ui, sans-serif', labelFontSize=10, titleFontSize=11, titleFontWeight=500
                            )
                            st.altair_chart(b_income_chart, use_container_width=True)

                        render_quant_and_chart(stats, ticker)
                        st.divider()

                    if not shown_b:
                        st.info("No hay ETFs de crecimiento activos en este portafolio.")

                # ============================================================
                # Section E — Triple Strategy Comparison
                # ============================================================
                st.markdown("### ⚖️ COMPARATIVA DE ESTRATEGIAS")
                st.markdown('<p style="font-family:Inter,sans-serif;font-size:12px;color:#555555;margin:0 0 12px 0;">¿Qué habría pasado si hubieras invertido el mismo dinero en VTI, YMAX o SPY?</p>', unsafe_allow_html=True)

                if st.button("Calcular Comparativa"):
                    all_buy_rows = []
                    for t_key, t_stats in results.items():
                        if 'error' in t_stats:
                            continue
                        hist = t_stats.get('history')
                        if hist is not None and not hist.empty:
                            buys = hist[hist['Action'].str.lower().str.contains('buy|compra', na=False)]
                            for _, row in buys.iterrows():
                                amt = abs(float(row.get('Amount', 0)))
                                if amt > 0:
                                    all_buy_rows.append([str(row['Date'].date()), amt])

                    if not all_buy_rows:
                        st.warning("No se encontraron transacciones de compra en el portafolio.")
                    else:
                        buy_flows_json = json.dumps(all_buy_rows)
                        real_invested = sum(s.get('pocket_investment', 0) for s in results.values() if 'error' not in s)
                        real_value = sum(s.get('market_value', 0) for s in results.values() if 'error' not in s)
                        real_return_pct = (real_value - real_invested) / real_invested * 100 if real_invested > 0 else 0

                        with st.spinner("Calculando estrategias alternativas..."):
                            strat_results = logic.simulate_triple_comparison(buy_flows_json)

                        if strat_results:
                            all_strategies = {
                                'real': {'label': 'Tu Portafolio Real', 'total_invested': real_invested, 'final_value': real_value, 'return_pct': real_return_pct},
                                **strat_results
                            }
                            sorted_strats = sorted(all_strategies.items(), key=lambda x: -x[1]['return_pct'])
                            strat_df = pd.DataFrame([
                                {
                                    'Estrategia': v['label'],
                                    'Invertido': f"${v['total_invested']:,.0f}",
                                    'Valor Final': f"${v['final_value']:,.0f}",
                                    'Retorno %': f"{v['return_pct']:+.2f}%"
                                }
                                for _, v in sorted_strats
                            ])
                            st.dataframe(strat_df, hide_index=True, use_container_width=True)

                            import altair as alt
                            strat_chart_df = pd.DataFrame([
                                {'Estrategia': v['label'], 'Retorno': v['return_pct']}
                                for _, v in sorted_strats
                            ])
                            bar_chart = alt.Chart(strat_chart_df).mark_bar().encode(
                                x=alt.X('Retorno:Q', title='Retorno Total (%)', axis=alt.Axis(format='+.1f')),
                                y=alt.Y('Estrategia:N', sort='-x', title=None),
                                color=alt.condition(alt.datum.Retorno > 0, alt.value('#006497'), alt.value('#c8102e')),
                                tooltip=[alt.Tooltip('Estrategia:N', title='Estrategia'), alt.Tooltip('Retorno:Q', format='+.2f', title='Retorno %')]
                            ).properties(height=180, background=CHART_PALETTE["bg"]).configure_view(
                                strokeOpacity=0, fill=CHART_PALETTE["bg"]
                            ).configure_axis(
                                grid=True, gridColor=CHART_PALETTE["grid"], domainColor=CHART_PALETTE["axis"],
                                tickColor=CHART_PALETTE["axis"], labelColor=CHART_PALETTE["axis"],
                                titleColor=CHART_PALETTE["title"], labelFont='Inter, system-ui, sans-serif',
                                titleFont='Inter, system-ui, sans-serif', labelFontSize=11, titleFontSize=12, titleFontWeight=500
                            )
                            st.altair_chart(bar_chart, use_container_width=True)

                # ============================================================
                # Section F — Risk Analysis
                # ============================================================
                st.markdown("### 🔍 ANÁLISIS DE RIESGO")
                total_port_value = sum(s.get('market_value', 0) for s in results.values() if 'error' not in s)
                risk_data = logic.build_risk_analysis(results, classify_map, total_port_value)

                if risk_data['yieldmax_risk']:
                    st.markdown("#### YieldMax — Riesgo por Subyacente")
                    for item in risk_data['yieldmax_risk']:
                        risk_color = '#c8102e' if item['risk_level'] == 'HIGH' else '#e68a00' if item['risk_level'] == 'MEDIUM' else '#555555'
                        risk_badge = f'<span style="display:inline-block;background-color:{risk_color};color:#fff;font-family:Inter,sans-serif;font-size:9px;font-weight:700;letter-spacing:0.10em;padding:2px 7px;border-radius:9999px;">{item["risk_level"]}</span>'
                        port_pct = item['portfolio_pct']
                        st.markdown(
                            f'<div style="background-color:#f6f3f2;padding:12px 16px;margin-bottom:8px;border-left:3px solid {risk_color};">'
                            f'<div style="font-family:Inter,sans-serif;font-weight:700;font-size:14px;color:#1a1a1a;margin-bottom:4px;">{item["ticker"]} {risk_badge} · <span style="font-weight:400;font-size:12px;color:#555555;">Subyacente: {item["underlying"]} ({item["name"]})</span></div>'
                            f'<div style="font-family:Inter,sans-serif;font-size:11px;color:#555555;">{item["reason"]} · <b style="color:#006497;">{port_pct:.1f}% del portafolio</b></div>'
                            f'</div>',
                            unsafe_allow_html=True
                        )

                if risk_data['etf_holdings']:
                    st.markdown("#### ETFs de Crecimiento — Top Holdings")
                    for etf_item in risk_data['etf_holdings']:
                        conc = etf_item.get('top3_concentration_pct', 0)
                        with st.expander(f"{etf_item['ticker']} — Top 3 concentración: {conc:.1f}%"):
                            holdings_df = pd.DataFrame([
                                {
                                    'Symbol': h['symbol'],
                                    'Empresa': h['name'],
                                    'Peso %': f"{h['weight']*100:.2f}%",
                                    'Descripción': h['description']
                                }
                                for h in etf_item['top_holdings']
                            ])
                            st.dataframe(holdings_df, hide_index=True, use_container_width=True)

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
FOOTER_STYLE = "background-color:#eae7e7;padding:32px 40px;margin-top:48px;border-left:3px solid #006497;"
BADGE_STYLE  = "display:inline-block;font-family:'Inter',sans-serif;font-size:10px;font-weight:500;letter-spacing:0.12em;text-transform:uppercase;color:#006497;border:1px solid #006497;padding:3px 8px;margin-bottom:14px;"
TITLE_STYLE  = "font-family:'Inter',sans-serif;font-size:13px;font-weight:700;letter-spacing:-0.01em;color:#1a1a1a;margin:0 0 12px 0;max-width:720px;line-height:1.5;"
BODY1_STYLE  = "font-family:'Inter',sans-serif;font-size:11px;color:#555555;line-height:1.7;margin:0 0 8px 0;max-width:720px;"
BODY2_STYLE  = "font-family:'Inter',sans-serif;font-size:11px;color:#888888;line-height:1.7;margin:0;max-width:720px;"

st.markdown(
    f'<div style="{FOOTER_STYLE}">'
    f'<span style="{BADGE_STYLE}">Versión Beta</span>'
    f'<p style="{TITLE_STYLE}">Esta herramienta es de carácter informativo y estimativo — no constituye asesoría financiera.</p>'
    f'<p style="{BODY1_STYLE}">Los datos, cálculos y proyecciones pueden presentar errores o inexactitudes. Siempre verifica con tus propios registros o los estados de cuenta de tu casa de bolsa.</p>'
    f'<p style="{BODY2_STYLE}">El uso de esta aplicación es bajo tu propio riesgo. Reporta cualquier fallo o inconsistencia para ayudarnos a seguir mejorando.</p>'
    '</div>',
    unsafe_allow_html=True
)
