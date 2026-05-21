import streamlit as st
import pandas as pd

import datetime
import logic
import json


st.set_page_config(page_title="Calculadora de Dividendos", layout="wide")

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
        border-radius: 0px !important;
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
        box-shadow: none !important;
    }

    /* 6b. DOWNLOAD BUTTON */
    div[data-testid="stDownloadButton"] > button {
        background-color: var(--primary-container) !important;
        color: var(--on-primary) !important;
        border: none !important;
        border-radius: 0px !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        letter-spacing: 0.05em !important;
        text-transform: uppercase !important;
        padding: 0.6rem 1.5rem !important;
    }
    div[data-testid="stDownloadButton"] > button:hover {
        background-color: #010f1e !important;
        box-shadow: none !important;
    }

    /* 7. MÉTRICAS — surface-high cards */
    div[data-testid="stMetric"] {
        background-color: var(--surface-high) !important;
        padding: 20px 24px !important;
        border-radius: 0px !important;
        border-left: 3px solid var(--electric-blue) !important;
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

    /* 16. TABLE ROW HOVER — feedback visual en tablas HTML */
    .da-table tr:hover td {
        background-color: rgba(0, 100, 151, 0.04) !important;
        transition: background-color 0.15s ease !important;
    }

    /* 17. ROC BADGE */
    .da-roc-badge {
        display: inline-block;
        background: linear-gradient(135deg, #006497 0%, #004f79 100%);
        color: #ffffff;
        font-family: 'Inter', sans-serif;
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        padding: 2px 8px;
        border-radius: 0px;
    }

    /* 18. TICKER SECTION HEADER */
    .da-ticker-header {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 14px 20px;
        background-color: #021C36;
        margin: 24px 0 0 0;
        border-left: 4px solid #006497;
    }
    .da-ticker-header .da-ticker-name {
        font-family: 'Inter', sans-serif;
        font-size: 18px;
        font-weight: 800;
        color: #ffffff;
        letter-spacing: -0.01em;
    }
    .da-ticker-header .da-mode-badge {
        font-family: 'Inter', sans-serif;
        font-size: 9px;
        font-weight: 600;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        padding: 3px 8px;
        border-radius: 0px;
    }
    .da-ticker-header .da-mode-income  { background-color: #c8102e; color: #fff; }
    .da-ticker-header .da-mode-growth  { background-color: #006497; color: #fff; }
    .da-ticker-header .da-ticker-price {
        font-family: 'Inter', sans-serif;
        font-size: 12px;
        color: #8899aa;
        margin-left: auto;
        letter-spacing: 0.05em;
    }

    /* 19. ROC CALLOUT */
    .da-roc-callout {
        background: linear-gradient(135deg, #010f1c 0%, #021C36 100%);
        border-left: 4px solid #4caf82;
        padding: 14px 20px;
        margin: 8px 0 16px 0;
    }
    .da-roc-callout .da-roc-callout-title {
        font-family: 'Inter', sans-serif;
        font-size: 9px;
        font-weight: 600;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #4caf82;
        margin: 0 0 6px 0;
    }
    .da-roc-callout .da-roc-callout-values {
        display: flex;
        gap: 32px;
        align-items: baseline;
    }
    .da-roc-callout .da-roc-number {
        font-family: 'Inter', sans-serif;
        font-size: 24px;
        font-weight: 800;
        color: #4caf82;
        letter-spacing: -0.02em;
    }
    .da-roc-callout .da-roc-sub {
        font-family: 'Inter', sans-serif;
        font-size: 10px;
        color: #8899aa;
        letter-spacing: 0.06em;
    }
    .da-roc-callout .da-roc-explain {
        font-family: 'Inter', sans-serif;
        font-size: 10px;
        color: #6699aa;
        margin: 8px 0 0 0;
        line-height: 1.5;
    }

    /* 20. SECTION DIVIDER */
    .da-section-rule {
        height: 1px;
        background: linear-gradient(90deg, #006497 0%, rgba(0,100,151,0.0) 100%);
        margin: 28px 0 20px 0;
        border: none;
    }

    /* 21. STEP GUIDE (empty state) */
    .da-step-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 2px;
        margin: 32px 0;
    }
    .da-step-card {
        background-color: #f6f3f2;
        padding: 24px 20px;
        position: relative;
    }
    .da-step-num {
        font-family: 'Cinzel', serif;
        font-size: 36px;
        font-weight: 700;
        color: #eae7e7;
        line-height: 1;
        margin-bottom: 12px;
    }
    .da-step-title {
        font-family: 'Inter', sans-serif;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.10em;
        text-transform: uppercase;
        color: #1a1a1a;
        margin-bottom: 6px;
    }
    .da-step-desc {
        font-family: 'Inter', sans-serif;
        font-size: 12px;
        color: #555555;
        line-height: 1.6;
    }
    .da-step-tag {
        display: inline-block;
        background-color: #006497;
        color: #fff;
        font-size: 9px;
        font-weight: 600;
        letter-spacing: 0.10em;
        text-transform: uppercase;
        padding: 2px 8px;
        margin-bottom: 10px;
    }

    /* 22. KPI BAR — resumen global mejorado */
    .da-kpi-bar {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 2px;
        margin: 16px 0 24px 0;
    }
    .da-kpi-cell {
        background-color: #f6f3f2;
        padding: 16px 20px;
        border-top: 3px solid transparent;
    }
    .da-kpi-cell.da-kpi-accent { border-top-color: #006497; }
    .da-kpi-cell.da-kpi-green  { border-top-color: #4caf82; }
    .da-kpi-cell.da-kpi-red    { border-top-color: #e05c5c; }
    .da-kpi-cell.da-kpi-roc    { border-top-color: #4caf82; background-color: #f0faf5; }
    .da-kpi-label {
        font-family: 'Inter', sans-serif;
        font-size: 9px;
        font-weight: 600;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #8899aa;
        margin: 0 0 4px 0;
    }
    .da-kpi-value {
        font-family: 'Inter', sans-serif;
        font-size: 20px;
        font-weight: 800;
        color: #1a1a1a;
        letter-spacing: -0.02em;
        margin: 0;
    }
    .da-kpi-delta {
        font-family: 'Inter', sans-serif;
        font-size: 10px;
        font-weight: 600;
        margin: 3px 0 0 0;
    }

    /* 23. SIDEBAR ROC SECTION */
    section[data-testid="stSidebar"] .da-sidebar-white-text {
        color: #ffffff !important;
    }
    .da-sidebar-roc-header {
        background-color: #021C36;
        color: #4caf82 !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 9px !important;
        font-weight: 700 !important;
        letter-spacing: 0.14em !important;
        text-transform: uppercase !important;
        padding: 8px 12px !important;
        margin: 12px 0 4px 0;
        border-left: 3px solid #4caf82;
    }

    /* 24. RESPONSIVE */
    @media (max-width: 768px) {
        .da-kpi-bar { grid-template-columns: repeat(2, 1fr); }
        .da-step-grid { grid-template-columns: 1fr; }
        .da-ticker-header { flex-direction: column; gap: 4px; }
    }
    @media (max-width: 480px) {
        .da-kpi-bar { grid-template-columns: 1fr; }
    }
</style>
""", unsafe_allow_html=True)


st.markdown("""
<div style="padding: 40px 0 0 0; background-color: #fcf9f8;">
    <div style="display:flex; align-items:baseline; gap:16px; flex-wrap:wrap;">
        <h1 style="
            font-family: 'Cinzel', serif;
            font-size: 2.8rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            color: #1a1a1a;
            margin: 0 0 6px 0;
            line-height: 1.1;
        ">
            CALCULADORA <span style="color:#006497;">//</span> DIVIDENDOS
        </h1>
        <span style="
            font-family: 'Inter', sans-serif;
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: #ffffff;
            background-color: #006497;
            padding: 3px 10px;
            vertical-align: middle;
        ">v2.2</span>
    </div>
    <p style="
        font-family: 'Inter', sans-serif;
        font-size: 0.82rem;
        font-weight: 400;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #888888;
        margin: 4px 0 6px 0;
    ">Análisis de Dividendos &nbsp;·&nbsp; ROC &nbsp;·&nbsp; TIR (Retorno Real Anualizado) &nbsp;·&nbsp; Simulación vs S&P 500</p>
    <div style="display:flex; gap:2px; margin-bottom:32px; margin-top:10px;">
        <div style="width:48px; height:2px; background-color:#006497;"></div>
        <div style="width:12px; height:2px; background-color:#021C36;"></div>
        <div style="width:6px; height:2px; background-color:#eae7e7;"></div>
    </div>
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



    st.sidebar.markdown("---")
    st.sidebar.markdown(
        '<div style="margin:12px 0 0 0;">'
        '<div style="background:#006497;padding:10px 12px;">'
        '<span class="da-sidebar-white-text" style="font-family:Inter,sans-serif;font-size:9px;font-weight:800;'
        'letter-spacing:0.12em;text-transform:uppercase;display:block;">'
        'Costo de Tu Inversion por Ticker</span>'
        '</div>'
        '<div style="padding:10px 12px;background:#f6f3f2;border-left:3px solid #006497;">'
        '<span style="font-family:Inter,sans-serif !important;font-size:10px !important;font-weight:400 !important;color:#445566 !important;line-height:1.6 !important;text-transform:none !important;display:block;margin-bottom:10px !important;">'
        'Ingresa el costo de tu inversion tal como aparece en tu broker para cada ticker.'
        '</span>'
        '<span style="font-family:Inter,sans-serif !important;font-size:10px !important;font-weight:400 !important;color:#445566 !important;line-height:1.6 !important;text-transform:none !important;display:block;margin-bottom:10px !important;">'
        'Escribe <b style="color:#1a1a1a !important;">solo el numero</b>, sin puntos ni comas. Si tiene decimales usa el <b style="color:#1a1a1a !important;">punto (.)</b>'
        '</span>'
        '<span style="font-family:Inter,sans-serif !important;font-size:10px !important;font-weight:600 !important;color:#006497 !important;text-transform:none !important;display:block;">'
        'Ejemplo: 1250.45'
        '</span>'
        '</div>'
        '</div>',
        unsafe_allow_html=True
    )
    with st.sidebar.expander("Donde encuentro este valor", expanded=False):
        st.markdown(
            '<div style="padding:4px 0;">'
            '<span style="font-family:Inter,sans-serif !important;font-size:10px !important;font-weight:700 !important;'
            'color:#006497 !important;letter-spacing:0.08em !important;text-transform:uppercase !important;display:block;margin-bottom:6px;">'
            'Interactive Brokers</span>'
            '<ol style="font-family:Inter,sans-serif;font-size:10px;color:#555555;margin:0 0 12px 0;padding-left:16px;line-height:1.9;">'
            '<li>Ve a <b>Portafolio → Posiciones</b></li>'
            '<li>Columna <b>"Base de coste"</b></li>'
            '<li>Copia ese numero aqui</li>'
            '</ol>'
            '<span style="font-family:Inter,sans-serif !important;font-size:10px !important;font-weight:700 !important;'
            'color:#006497 !important;letter-spacing:0.08em !important;text-transform:uppercase !important;display:block;margin-bottom:6px;">'
            'Charles Schwab</span>'
            '<ol style="font-family:Inter,sans-serif;font-size:10px;color:#555555;margin:0;padding-left:16px;line-height:1.9;">'
            '<li>Ve a <b>Cuentas → Posiciones</b></li>'
            '<li>Columna <b>"Cost Basis"</b></li>'
            '<li>Copia ese numero aqui</li>'
            '</ol>'
            '</div>',
            unsafe_allow_html=True
        )

    _roc_tickers = ["MSTY", "CONY", "TSLY", "NVDY", "YMAX", "FEPI", "PLTY", "SMCY", "NFLY"]
    ib_cost_basis_map = {}
    for _rt in _roc_tickers:
        _val = st.sidebar.number_input(
            _rt,
            min_value=0.0,
            value=0.0,
            step=0.01,
            format="%.2f",
            key=f"ib_basis_{_rt}",
            label_visibility="visible"
        )
        if _val > 0:
            ib_cost_basis_map[_rt] = str(_val)

    _n_roc = sum(1 for v in ib_cost_basis_map.values() if float(v) > 0)
    if _n_roc > 0:
        st.sidebar.markdown(
            f'<p style="font-family:Inter,sans-serif;font-size:10px;color:#4caf82;font-weight:600;margin:6px 0 0 0;">'
            f'{_n_roc} ticker{"s" if _n_roc > 1 else ""} con Base de Coste registrada</p>',
            unsafe_allow_html=True
        )

    st.sidebar.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
    if st.sidebar.button("Limpiar Caché"):
        st.cache_data.clear()
        st.rerun()
    st.sidebar.caption("v2.2")

# --- Utilidad de formateo para métricas cuantitativas ---
def fmt_ratio(val, decimales=2, sufijo=""):
    if val is None: return "N/A"
    return f"{val:.{decimales}f}{sufijo}"

# --- Main Logic ---

if input_method == "Subir CSV/Excel" and uploaded_file is None:
    st.markdown("""
<div class="da-step-grid">
    <div class="da-step-card">
        <div class="da-step-tag">Paso 1</div>
        <div class="da-step-num">01</div>
        <div class="da-step-title">Exporta tu historial</div>
        <div class="da-step-desc">
            Descarga el CSV de transacciones desde Interactive Brokers
            (<b>Informes → Extractos → Transaction History</b>) o Charles Schwab
            (<b>Historial → Transacciones → Exportar</b>).
        </div>
    </div>
    <div class="da-step-card">
        <div class="da-step-tag">Paso 2</div>
        <div class="da-step-num">02</div>
        <div class="da-step-title">Sube el archivo</div>
        <div class="da-step-desc">
            Usa el botón <b>Subir Archivo</b> en el panel izquierdo.
            Se aceptan <b>.csv</b> y <b>.xlsx</b>. El broker se detecta
            automáticamente.
        </div>
    </div>
    <div class="da-step-card">
        <div class="da-step-tag">Paso 3</div>
        <div class="da-step-num">03</div>
        <div class="da-step-title">Ejecuta el análisis</div>
        <div class="da-step-desc">
            Haz clic en <b>Analizar Dividendos</b>. Obtén ROI real,
            TIR, ROC acumulado, comparativa vs S&P 500 y métricas de riesgo
            ajustado por ticker.
        </div>
    </div>
</div>
<hr class="da-section-rule">
<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:2px;margin-bottom:32px;">
    <div style="background:#f6f3f2;padding:14px 18px;border-top:2px solid #006497;">
        <div style="font-family:'Inter',sans-serif;font-size:9px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;color:#8899aa;margin-bottom:4px;">YieldMax Income</div>
        <div style="font-family:'Inter',sans-serif;font-size:12px;color:#1a1a1a;">MSTY · CONY · TSLY · NVDY · YMAX · PLTY · SMCY · NFLY · FEPI</div>
    </div>
    <div style="background:#f6f3f2;padding:14px 18px;border-top:2px solid #021C36;">
        <div style="font-family:'Inter',sans-serif;font-size:9px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;color:#8899aa;margin-bottom:4px;">ETFs de Crecimiento</div>
        <div style="font-family:'Inter',sans-serif;font-size:12px;color:#1a1a1a;">VTI · VOO · SCHB · SCHD · QQQ · SPY · XLK · SMH</div>
    </div>
    <div style="background:#f6f3f2;padding:14px 18px;border-top:2px solid #8a8a8a;">
        <div style="font-family:'Inter',sans-serif;font-size:9px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;color:#8899aa;margin-bottom:4px;">Brokers Soportados</div>
        <div style="font-family:'Inter',sans-serif;font-size:12px;color:#1a1a1a;">Interactive Brokers · Charles Schwab · Excel genérico</div>
    </div>
    <div style="background:#f0faf5;padding:14px 18px;border-top:2px solid #4caf82;">
        <div style="font-family:'Inter',sans-serif;font-size:9px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;color:#4caf82;margin-bottom:4px;">ROC Detectado</div>
        <div style="font-family:'Inter',sans-serif;font-size:12px;color:#1a1a1a;">Ingresa la base IB en el sidebar para ver el ROC acumulado por ticker</div>
    </div>
</div>
    """, unsafe_allow_html=True)

if input_method == "Subir CSV/Excel" and uploaded_file is not None:
    st.subheader("Análisis de Portafolio Real")

    try:
        if uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file)
            broker = 'generic'
        else:
            df, broker = logic.load_and_detect_csv(uploaded_file)
            if df.empty:
                st.error("No pudimos leer el formato del CSV. Intenta guardarlo como 'CSV UTF-8' o usa Excel (.xlsx).")
                st.stop()

        # Section A — Broker badge
        BROKER_LABELS = {'schwab': 'Charles Schwab', 'ibkr': 'Interactive Brokers', 'generic': 'Formato Genérico'}
        BROKER_COLORS = {'schwab': '#006497', 'ibkr': '#c8102e', 'generic': '#555555'}
        broker_label = BROKER_LABELS.get(broker, broker.upper())
        broker_color = BROKER_COLORS.get(broker, '#555555')
        st.markdown(f'<div style="display:inline-block;background-color:{broker_color};color:#ffffff;font-family:Inter,sans-serif;font-size:11px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;padding:4px 12px;margin-bottom:12px;">BROKER DETECTADO: {broker_label}</div>', unsafe_allow_html=True)

        # 1. Normalize
        df_clean = logic.normalize_csv(df)

        # Build lightweight CSV summary for richer error cards
        _csv_ticker_data = {}
        if 'Ticker' in df_clean.columns and 'Action' in df_clean.columns:
            for _et, _eg in df_clean.groupby('Ticker'):
                _et_buys = _eg[_eg['Action'].str.lower().str.contains('buy', na=False)]
                _et_divs = _eg[_eg['Action'].str.lower().str.contains('div', na=False)]
                _csv_ticker_data[_et] = {
                    'shares': float(_et_buys['Quantity'].sum()) if 'Quantity' in _et_buys.columns and not _et_buys.empty else 0.0,
                    'invested': abs(float(_et_buys['Amount'].sum())) if not _et_buys.empty else 0.0,
                    'dividends_csv': float(_et_divs['Amount'].sum()) if not _et_divs.empty else 0.0,
                    'first_date': str(_eg['Date'].min())[:10] if not _eg.empty else 'N/A',
                }

        with st.expander("Ver datos procesados (Primeras 5 filas)"):
            st.dataframe(df_clean.head())

        # 1.5 Validate Columns
        required_cols = ['Date', 'Ticker', 'Amount']
        missing_cols = [col for col in required_cols if col not in df_clean.columns]

        if missing_cols:
            st.error(f"Error de Formato: No encontramos las columnas: {', '.join(missing_cols)}")
            st.warning(f"Columnas encontradas: {list(df_clean.columns)}")
            st.info("Consejo: Asegúrate de que tu autodetector de cabecera funcionó. Si tu archivo tiene muchas filas vacías al inicio, intenta borrarlas.")
            st.stop()

        # 2. Analyze
        # ── Persist results across reruns via session_state ───────────────
        _fid = f"{uploaded_file.name}_{uploaded_file.size}"
        if st.session_state.get('_file_id') != _fid:
            st.session_state.update({
                '_file_id': _fid, '_results': None,
                '_classify_map': {}, '_skipped': {},
                '_strat_results': None,
            })

        if st.button("Analizar Dividendos"):
            with st.spinner("Analizando transacciones, splits y dividendos..."):
                try:
                    results = logic.analyze_portfolio(df_clean, version="2.0", ib_cost_basis_map=ib_cost_basis_map or None)
                except TypeError:
                    results = logic.analyze_portfolio(df_clean)

            if not results:
                st.error("No se pudieron extraer tickers válidos o datos del archivo.")
            else:
                skipped_tickers = {t: s for t, s in results.items() if s.get("skipped")}
                valid_results   = {t: s for t, s in results.items() if not s.get("skipped")}
                classify_map    = logic.classify_tickers(list(valid_results.keys()))
                if not valid_results:
                    st.warning("Todos los tickers del archivo fueron descartados. Asegúrate de subir transacciones de ETFs conocidos (VTI, VOO, TSLY, etc.).")
                else:
                    st.session_state['_results']      = valid_results
                    st.session_state['_classify_map'] = classify_map
                    st.session_state['_skipped']      = skipped_tickers

                    # ── Auto-compute strategy comparison ─────────────────
                    _all_buy_rows = []
                    for _t_key, _t_stats in valid_results.items():
                        _hist = _t_stats.get('history')
                        if _hist is not None and not _hist.empty:
                            _buys = _hist[_hist['Action'].str.lower().str.contains('buy|compra', na=False)]
                            for _, _row in _buys.iterrows():
                                _amt = abs(float(_row.get('Amount', 0)))
                                if _amt > 0:
                                    _all_buy_rows.append([str(_row['Date'].date()), _amt])
                    if _all_buy_rows:
                        with st.spinner("Calculando comparativa VTI · YMAX · SPY..."):
                            try:
                                _strat = logic.simulate_triple_comparison(json.dumps(_all_buy_rows))
                                st.session_state['_strat_results'] = _strat
                            except Exception:
                                st.session_state['_strat_results'] = None
                    else:
                        st.session_state['_strat_results'] = None

        # ── Render from session_state ─────────────────────────────────────
        results         = st.session_state.get('_results')
        classify_map    = st.session_state.get('_classify_map', {})
        skipped_tickers = st.session_state.get('_skipped', {})
        strat_results_cached = st.session_state.get('_strat_results')

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

        if results:
            # ── Portfolio Global Summary ──────────────────────────────
            total_invested = sum(s.get('pocket_investment', 0) for s in results.values() if 'error' not in s)
            total_market   = sum(s.get('market_value', 0)      for s in results.values() if 'error' not in s)
            total_divs     = sum(s.get('dividends_collected_cash', 0) + s.get('dividends_collected_drip', 0)
                                 for s in results.values() if 'error' not in s)
            total_gain     = (total_market + sum(s.get('dividends_collected_cash', 0)
                                 for s in results.values() if 'error' not in s)) - total_invested
            total_roi      = (total_gain / total_invested * 100) if total_invested else 0

            # ── KPI Bar — resumen global visual ──────────────────────
            _total_roc_all   = sum(s.get('roc_accumulated', 0) or 0 for s in results.values() if 'error' not in s)
            _has_any_roc     = any(s.get('roc_accumulated') is not None for s in results.values() if 'error' not in s)
            _gain_color      = "#4caf82" if total_gain >= 0 else "#e05c5c"
            _gain_sign       = "+" if total_gain >= 0 else ""
            _gain_accent     = "da-kpi-green" if total_gain >= 0 else "da-kpi-red"
            _roc_cell = (
                f'<div class="da-kpi-cell da-kpi-roc">'
                f'<p class="da-kpi-label">ROC Acumulado</p>'
                f'<p class="da-kpi-value" style="color:#4caf82;">${_total_roc_all:,.0f}</p>'
                f'<p class="da-kpi-delta" style="color:#4caf82;">'
                f'{sum(1 for s in results.values() if s.get("roc_accumulated")) } ticker(s)</p>'
                f'</div>'
            ) if _has_any_roc else (
                f'<div class="da-kpi-cell">'
                f'<p class="da-kpi-label">ROC Acumulado</p>'
                f'<p class="da-kpi-value" style="color:#cccccc;">—</p>'
                f'<p class="da-kpi-delta" style="color:#aaaaaa;">Ingresa base IB</p>'
                f'</div>'
            )
            st.markdown(f"""
<p style="font-family:'Inter',sans-serif;font-size:9px;font-weight:600;letter-spacing:0.14em;text-transform:uppercase;color:#8899aa;margin:20px 0 0 0;">Resumen global del portafolio</p>
<div class="da-kpi-bar">
    <div class="da-kpi-cell da-kpi-accent">
        <p class="da-kpi-label">Total Invertido</p>
        <p class="da-kpi-value">${total_invested:,.0f}</p>
        <p class="da-kpi-delta" style="color:#8899aa;">{len(results)} posiciones</p>
    </div>
    <div class="da-kpi-cell">
        <p class="da-kpi-label">Valor de Mercado</p>
        <p class="da-kpi-value">${total_market:,.0f}</p>
        <p class="da-kpi-delta" style="color:#8899aa;">precio actual</p>
    </div>
    <div class="da-kpi-cell {_gain_accent}">
        <p class="da-kpi-label">Ganancia / Pérdida</p>
        <p class="da-kpi-value" style="color:{_gain_color};">{_gain_sign}${total_gain:,.0f}</p>
        <p class="da-kpi-delta" style="color:{_gain_color};">{_gain_sign}{total_roi:.2f}%</p>
    </div>
    <div class="da-kpi-cell">
        <p class="da-kpi-label">Dividendos Totales</p>
        <p class="da-kpi-value">${total_divs:,.0f}</p>
        <p class="da-kpi-delta" style="color:#8899aa;">efectivo + DRIP</p>
    </div>
    {_roc_cell}
</div>
            """, unsafe_allow_html=True)
            st.caption("ROI = ganancia total acumulada desde el inicio · TIR (Tasa Interna de Retorno / IRR en inglés) = retorno anualizado considerando exactamente cuándo compraste cada lote — más preciso que el ROI para compras escalonadas")

            # ── PDF Report Download ───────────────────────────────────
            try:
                from report import generate_report_pdf
                from datetime import date as _date
                _pdf_bytes = generate_report_pdf(results, broker, version="2.0")
                st.download_button(
                    label="Descargar Reporte PDF",
                    data=_pdf_bytes,
                    file_name=f"auditoria-portafolio-{_date.today().isoformat()}.pdf",
                    mime="application/pdf",
                )
            except Exception:
                pass

            # Section B — Classification pills header
            mode_a_tickers = [t for t, m in classify_map.items() if m == 'mode_a']
            mode_b_tickers = [t for t, m in classify_map.items() if m == 'mode_b']

            st.markdown("### CLASIFICACIÓN DE PORTAFOLIO")
            b_col1, b_col2 = st.columns(2)
            with b_col1:
                st.markdown("**Dividendos Income — YieldMax**")
                pills_a = " ".join([f'<span style="display:inline-block;background-color:#c8102e;color:#fff;font-family:Inter,sans-serif;font-size:10px;font-weight:600;letter-spacing:0.08em;padding:2px 8px;margin:2px;border-radius:0px;">{t}</span>' for t in mode_a_tickers]) or '<span style="color:#888;font-size:12px;">Ninguno</span>'
                st.markdown(pills_a, unsafe_allow_html=True)
            with b_col2:
                st.markdown("**ETFs de Crecimiento**")
                pills_b = " ".join([f'<span style="display:inline-block;background-color:#006497;color:#fff;font-family:Inter,sans-serif;font-size:10px;font-weight:600;letter-spacing:0.08em;padding:2px 8px;margin:2px;border-radius:0px;">{t}</span>' for t in mode_b_tickers]) or '<span style="color:#888;font-size:12px;">Ninguno</span>'
                st.markdown(pills_b, unsafe_allow_html=True)

            st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

            # ── Comparativa de estrategias (auto-calculada) ───────────
            if strat_results_cached:
                st.markdown("### COMPARATIVA DE ESTRATEGIAS")
                st.markdown('<p style="font-family:Inter,sans-serif;font-size:12px;color:#555555;margin:0 0 12px 0;">Si hubieras invertido el mismo capital en VTI, YMAX o SPY con el mismo timing.</p>', unsafe_allow_html=True)
                _sr_invested = sum(s.get('pocket_investment', 0) for s in results.values() if 'error' not in s)
                _sr_value    = sum(s.get('market_value', 0) for s in results.values() if 'error' not in s)
                _sr_ret_pct  = (_sr_value - _sr_invested) / _sr_invested * 100 if _sr_invested > 0 else 0
                _all_strats  = {
                    'real': {'label': 'Tu Portafolio Real', 'total_invested': _sr_invested, 'final_value': _sr_value, 'return_pct': _sr_ret_pct},
                    **strat_results_cached
                }
                _sorted_strats = sorted(_all_strats.items(), key=lambda x: -x[1]['return_pct'])
                _strat_df = pd.DataFrame([
                    {'Estrategia': v['label'], 'Invertido': f"${v['total_invested']:,.0f}", 'Valor Final': f"${v['final_value']:,.0f}", 'Retorno': f"{v['return_pct']:+.2f}%"}
                    for _, v in _sorted_strats
                ])
                st.dataframe(_strat_df, hide_index=True, use_container_width=True)
                import altair as alt
                _bar_df = pd.DataFrame([{'Estrategia': v['label'], 'Retorno': v['return_pct']} for _, v in _sorted_strats])
                _bar_chart = alt.Chart(_bar_df).mark_bar().encode(
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
                st.altair_chart(_bar_chart, use_container_width=True)
                st.markdown('<hr class="da-section-rule">', unsafe_allow_html=True)

            # ── Comparativa directa A vs B (solo cuando hay ambos) ────
            _cmp_a_rows = [(t, s) for t, s in results.items() if classify_map.get(t) == 'mode_a' and 'error' not in s]
            _cmp_b_rows = [(t, s) for t, s in results.items() if classify_map.get(t) == 'mode_b' and 'error' not in s]
            if _cmp_a_rows and _cmp_b_rows:
                _cmp_a_inv = sum(s['pocket_investment'] for _, s in _cmp_a_rows)
                _cmp_a_mv  = sum(s['market_value'] for _, s in _cmp_a_rows)
                _cmp_a_div = sum(s.get('dividends_collected_cash', 0) for _, s in _cmp_a_rows)
                _cmp_a_tr  = _cmp_a_mv + _cmp_a_div - _cmp_a_inv
                _cmp_a_pct = _cmp_a_tr / _cmp_a_inv * 100 if _cmp_a_inv > 0 else 0
                _cmp_b_inv = sum(s['pocket_investment'] for _, s in _cmp_b_rows)
                _cmp_b_mv  = sum(s['market_value'] for _, s in _cmp_b_rows)
                _cmp_b_div = sum(s.get('dividends_collected_cash', 0) for _, s in _cmp_b_rows)
                _cmp_b_tr  = _cmp_b_mv + _cmp_b_div - _cmp_b_inv
                _cmp_b_pct = _cmp_b_tr / _cmp_b_inv * 100 if _cmp_b_inv > 0 else 0
                _cmp_diff  = abs(_cmp_a_pct - _cmp_b_pct)
                _cmp_winner_label = "Dividendos Income" if _cmp_a_pct >= _cmp_b_pct else "ETFs de Crecimiento"
                _cmp_winner_color = "#c8102e" if _cmp_a_pct >= _cmp_b_pct else "#006497"
                _cmp_a_ret_color = "#4caf82" if _cmp_a_pct >= 0 else "#e05c5c"
                _cmp_b_ret_color = "#4caf82" if _cmp_b_pct >= 0 else "#e05c5c"
                st.markdown("### INCOME VS CRECIMIENTO")
                st.markdown(
                    f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:2px;margin:0 0 12px 0;">'
                    f'<div style="background:#f6f3f2;padding:16px 20px;border-left:4px solid #c8102e;">'
                    f'<p style="font-family:Inter,sans-serif;font-size:9px;color:#c8102e;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;margin:0 0 8px 0;">Dividendos Income · {len(_cmp_a_rows)} tickers</p>'
                    f'<p style="font-family:Inter,sans-serif;font-size:28px;font-weight:800;color:{_cmp_a_ret_color};margin:0 0 4px 0;letter-spacing:-0.02em;">{_cmp_a_pct:+.2f}%</p>'
                    f'<p style="font-family:Inter,sans-serif;font-size:11px;color:#555555;margin:0 0 6px 0;">retorno total (capital + dividendos)</p>'
                    f'<div style="display:flex;gap:16px;">'
                    f'<div><p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;margin:0;letter-spacing:0.10em;text-transform:uppercase;">Dividendos</p>'
                    f'<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:700;color:#4caf82;margin:0;">${_cmp_a_div:,.0f}</p></div>'
                    f'<div><p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;margin:0;letter-spacing:0.10em;text-transform:uppercase;">Invertido</p>'
                    f'<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:700;color:#ffffff;margin:0;background:#021C36;padding:1px 6px;">${_cmp_a_inv:,.0f}</p></div>'
                    f'</div></div>'
                    f'<div style="background:#f6f3f2;padding:16px 20px;border-left:4px solid #006497;">'
                    f'<p style="font-family:Inter,sans-serif;font-size:9px;color:#006497;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;margin:0 0 8px 0;">ETFs de Crecimiento · {len(_cmp_b_rows)} tickers</p>'
                    f'<p style="font-family:Inter,sans-serif;font-size:28px;font-weight:800;color:{_cmp_b_ret_color};margin:0 0 4px 0;letter-spacing:-0.02em;">{_cmp_b_pct:+.2f}%</p>'
                    f'<p style="font-family:Inter,sans-serif;font-size:11px;color:#555555;margin:0 0 6px 0;">retorno total (capital + dividendos)</p>'
                    f'<div style="display:flex;gap:16px;">'
                    f'<div><p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;margin:0;letter-spacing:0.10em;text-transform:uppercase;">Dividendos</p>'
                    f'<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:700;color:#4caf82;margin:0;">${_cmp_b_div:,.0f}</p></div>'
                    f'<div><p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;margin:0;letter-spacing:0.10em;text-transform:uppercase;">Invertido</p>'
                    f'<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:700;color:#ffffff;margin:0;background:#021C36;padding:1px 6px;">${_cmp_b_inv:,.0f}</p></div>'
                    f'</div></div>'
                    f'</div>'
                    f'<p style="font-family:Inter,sans-serif;font-size:11px;color:#555555;margin:0 0 16px 0;">'
                    f'<b style="color:{_cmp_winner_color};">{_cmp_winner_label}</b> lleva ventaja por '
                    f'<b>{_cmp_diff:.2f} puntos porcentuales</b> en retorno total.</p>',
                    unsafe_allow_html=True
                )

            # ── TABS: Dividendos Income / ETFs de Crecimiento ──────────
            tab_a, tab_b = st.tabs([
                f"Dividendos Income ({len(mode_a_tickers)})",
                f"ETFs de Crecimiento ({len(mode_b_tickers)})",
            ])

            # ── Helper: render quant metrics + SPY chart (shared) ──────
            def render_quant_and_chart(stats, ticker=""):
                import altair as alt
                st.markdown('<hr class="da-section-rule">', unsafe_allow_html=True)
                st.markdown("### MÉTRICAS DE RIESGO AJUSTADO")
                qr1, qr2, qr3 = st.columns(3)
                qr1.metric("Sharpe Ratio",      fmt_ratio(stats.get('sharpe_ratio')))
                qr2.metric("Sortino Ratio",     fmt_ratio(stats.get('sortino_ratio')))
                qr3.metric("Max Drawdown",      fmt_ratio(stats.get('max_drawdown'), sufijo="%"))
                st.caption("Sharpe: retorno ajustado por riesgo (>1 = bueno, >2 = muy bueno) · Sortino: igual pero solo penaliza la volatilidad negativa · Max Drawdown: caída máxima desde el pico")
                qr4, qr5, qr6 = st.columns(3)
                qr4.metric("Beta vs VOO",       fmt_ratio(stats.get('beta_vs_voo')))
                qr5.metric("Alpha Anualizado",  fmt_ratio(stats.get('alpha_anualizado'), sufijo="%"))
                qr6.metric("Volatilidad Anual", fmt_ratio(stats.get('volatilidad_anualizada'), sufijo="%"))
                st.caption("Beta: correlación con el mercado (1 = se mueve igual que el índice) · Alpha: retorno extra sobre el mercado (positivo = supera al índice) · Volatilidad: desviación estándar anualizada")

                if 'daily_trend' in stats and not stats['daily_trend'].empty:
                    st.markdown('<hr class="da-section-rule">', unsafe_allow_html=True)
                    st.markdown("### SIMULACIÓN VS S&P 500 (VOO)")
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

            # ── TAB A — Dividendos Income ──────────────────────────────
            with tab_a:
                shown_a = False
                _a_valid = [(t, s) for t, s in results.items()
                            if classify_map.get(t) == 'mode_a' and 'error' not in s]

                # ── NAV PILLS ─────────────────────────────────────────────
                if _a_valid:
                    _pill_html = []
                    for _pt, _ps in _a_valid:
                        _pr = _ps.get('roi_percent', 0)
                        _pc = '#4caf82' if _pr >= 0 else '#e05c5c'
                        _yoc = _ps.get('yield_on_cost') or 0
                        _pill_html.append(
                            f'<div style="background:#021C36;padding:8px 14px;display:inline-flex;'
                            f'flex-direction:column;gap:1px;align-items:center;min-width:64px;">'
                            f'<span style="font-family:Inter,sans-serif;font-size:11px;font-weight:700;'
                            f'color:#ffffff;letter-spacing:0.05em;">{_pt}</span>'
                            f'<span style="font-family:Inter,sans-serif;font-size:10px;font-weight:600;'
                            f'color:{_pc};">{_pr:+.1f}%</span>'
                            f'<span style="font-family:Inter,sans-serif;font-size:9px;color:#556677;'
                            f'letter-spacing:0.08em;">YoC {_yoc:.1f}%</span>'
                            f'</div>'
                        )
                    st.markdown(
                        '<div style="display:flex;gap:2px;flex-wrap:wrap;margin:4px 0 16px 0;">'
                        + ''.join(_pill_html) + '</div>',
                        unsafe_allow_html=True
                    )

                # ── DIVIDEND CALENDAR ─────────────────────────────────────
                if _a_valid:
                    import altair as alt
                    _cal_agg = {}
                    for _ct, _cs in _a_valid:
                        _cmi = _cs.get('monthly_income')
                        if _cmi is not None and not _cmi.empty:
                            for _mon, _val in _cmi.items():
                                _cal_agg[_mon] = _cal_agg.get(_mon, 0.0) + float(_val)
                    if _cal_agg:
                        _cal_df = pd.DataFrame({
                            'Mes': list(_cal_agg.keys()),
                            'Income': list(_cal_agg.values())
                        })
                        _cal_df = _cal_df[_cal_df['Income'] > 0].sort_values('Mes').tail(12).copy()
                        _cal_df['Tipo'] = 'Histórico'
                        _avg_proj_cal = float(_cal_df['Income'].tail(3).mean())
                        if _avg_proj_cal > 0:
                            _last_dt_cal = pd.to_datetime(_cal_df['Mes'].max() + '-01')
                            _proj_rows_cal = [
                                {'Mes': (_last_dt_cal + pd.DateOffset(months=_i)).strftime('%Y-%m'),
                                 'Income': _avg_proj_cal, 'Tipo': 'Proyectado'}
                                for _i in range(1, 7)
                            ]
                            _cal_df = pd.concat([_cal_df, pd.DataFrame(_proj_rows_cal)], ignore_index=True)
                        _cal_df['MesDate'] = pd.to_datetime(_cal_df['Mes'] + '-01')
                        st.markdown("### CALENDARIO DE DIVIDENDOS")
                        _cal_chart = alt.Chart(_cal_df).mark_bar(cornerRadiusTopLeft=0, cornerRadiusTopRight=0).encode(
                            x=alt.X('MesDate:T', title=None, axis=alt.Axis(format='%b %y', labelAngle=-45)),
                            y=alt.Y('Income:Q', title='Dividendos ($)', axis=alt.Axis(format='$,.0f')),
                            color=alt.Color('Tipo:N', scale=alt.Scale(
                                domain=['Histórico', 'Proyectado'],
                                range=['#006497', '#8899aa']
                            ), legend=alt.Legend(orient='top-right', title=None)),
                            opacity=alt.condition(
                                alt.datum.Tipo == 'Proyectado', alt.value(0.55), alt.value(1.0)
                            ),
                            tooltip=[
                                alt.Tooltip('MesDate:T', title='Mes', format='%b %Y'),
                                alt.Tooltip('Income:Q', format='$,.2f', title='Dividendos'),
                                alt.Tooltip('Tipo:N', title='Tipo'),
                            ]
                        ).properties(height=200, background=CHART_PALETTE["bg"]).configure_view(
                            strokeOpacity=0, fill=CHART_PALETTE["bg"]
                        ).configure_axis(
                            grid=True, gridColor=CHART_PALETTE["grid"],
                            domainColor=CHART_PALETTE["axis"], tickColor=CHART_PALETTE["axis"],
                            labelColor=CHART_PALETTE["axis"], titleColor=CHART_PALETTE["title"],
                            labelFont='Inter, system-ui, sans-serif', titleFont='Inter, system-ui, sans-serif',
                            labelFontSize=11, titleFontSize=12, titleFontWeight=500
                        ).configure_legend(
                            labelColor=CHART_PALETTE["title"], titleColor=CHART_PALETTE["axis"],
                            labelFont='Inter, system-ui, sans-serif', titleFont='Inter, system-ui, sans-serif',
                            labelFontSize=12, titleFontSize=10, titleFontWeight=500,
                            strokeColor='transparent', fillColor=CHART_PALETTE["bg"], padding=12, cornerRadius=0
                        )
                        st.altair_chart(_cal_chart, use_container_width=True)
                        st.caption(
                            f"Histórico: dividendos cobrados por mes · "
                            f"Proyectado (gris): estimación basada en promedio últimos 3 meses "
                            f"(${_avg_proj_cal:,.2f}/mes para todo el portafolio Income)"
                        )
                        st.markdown('<hr class="da-section-rule">', unsafe_allow_html=True)

                for ticker, stats in results.items():
                    if classify_map.get(ticker) != 'mode_a':
                        continue
                    if "error" in stats:
                        _ec = _csv_ticker_data.get(ticker, {})
                        _ec_data_html = ''
                        if _ec:
                            _ec_data_html = (
                                f'<div><p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;'
                                f'margin:0;letter-spacing:0.10em;text-transform:uppercase;">Acciones compradas</p>'
                                f'<p style="font-family:Inter,sans-serif;font-size:16px;font-weight:700;'
                                f'color:#1a1a1a;margin:2px 0 0 0;">{_ec.get("shares",0):.4f}</p></div>'
                                f'<div><p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;'
                                f'margin:0;letter-spacing:0.10em;text-transform:uppercase;">Invertido (CSV)</p>'
                                f'<p style="font-family:Inter,sans-serif;font-size:16px;font-weight:700;'
                                f'color:#1a1a1a;margin:2px 0 0 0;">${_ec.get("invested",0):,.2f}</p></div>'
                                f'<div><p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;'
                                f'margin:0;letter-spacing:0.10em;text-transform:uppercase;">Dividendos CSV</p>'
                                f'<p style="font-family:Inter,sans-serif;font-size:16px;font-weight:700;'
                                f'color:#4caf82;margin:2px 0 0 0;">${_ec.get("dividends_csv",0):,.2f}</p></div>'
                                f'<div><p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;'
                                f'margin:0;letter-spacing:0.10em;text-transform:uppercase;">Primera compra</p>'
                                f'<p style="font-family:Inter,sans-serif;font-size:16px;font-weight:700;'
                                f'color:#1a1a1a;margin:2px 0 0 0;">{_ec.get("first_date","N/A")}</p></div>'
                            )
                        st.markdown(
                            f'<div style="border-left:4px solid #e05c5c;background:#fff8f8;'
                            f'padding:16px 20px;margin:8px 0 16px 0;">'
                            f'<p style="font-family:Inter,sans-serif;font-size:9px;color:#e05c5c;font-weight:700;'
                            f'letter-spacing:0.12em;text-transform:uppercase;margin:0 0 8px 0;">'
                            f'PRECIO NO DISPONIBLE · {ticker}</p>'
                            f'<p style="font-family:Inter,sans-serif;font-size:11px;color:#555;margin:0 0 10px 0;">'
                            f'yfinance no pudo cargar datos de mercado. Suele ocurrir con ETFs recientes '
                            f'(PLTY, NFLY, SMCY). Métricas de riesgo y valor de mercado no disponibles.</p>'
                            f'<div style="display:flex;gap:20px;flex-wrap:wrap;margin:0 0 8px 0;">'
                            f'{_ec_data_html}</div>'
                            f'<p style="font-family:Inter,sans-serif;font-size:10px;color:#999;margin:0;">'
                            f'Detalle: {stats["error"]}</p>'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                        continue
                    shown_a = True
                    _roi_a = stats.get('roi_percent', 0)
                    _roi_color_a = "#4caf82" if _roi_a >= 0 else "#e05c5c"
                    st.markdown(
                        f'<div class="da-ticker-header">'
                        f'<span class="da-ticker-name">{ticker}</span>'
                        f'<span class="da-mode-badge da-mode-income">Income</span>'
                        f'<span class="da-ticker-price">'
                        f'${stats["current_price"]:,.2f} &nbsp;·&nbsp; '
                        f'<span style="color:{_roi_color_a};font-weight:700;">{_roi_a:+.2f}% ROI</span>'
                        f'</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                    _h_buys = stats.get('shares_bought', 0)
                    _h_sells = stats.get('shares_sold', 0)
                    _proj_m = stats.get('monthly_income')
                    _proj_recent = _proj_m[_proj_m > 0].tail(3) if (_proj_m is not None and not _proj_m.empty) else None
                    _proj_val = _proj_recent.mean() if (_proj_recent is not None and len(_proj_recent) > 0) else None
                    _proj_cell = (
                        f'<p style="font-family:Inter,sans-serif;font-size:22px;font-weight:700;color:#4caf82;margin:0 0 2px 0;">${_proj_val:,.2f}</p>'
                        f'<p style="font-family:Inter,sans-serif;font-size:9px;color:#556677;margin:0;">prom. últ. 3 meses</p>'
                    ) if _proj_val else (
                        '<p style="font-family:Inter,sans-serif;font-size:22px;font-weight:700;color:#445566;margin:0 0 2px 0;">—</p>'
                        '<p style="font-family:Inter,sans-serif;font-size:9px;color:#445566;margin:0;">sin historial</p>'
                    )
                    st.markdown(f"""
                    <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:2px;margin:8px 0 14px 0;">
                        <div style="background:#021C36;padding:12px 16px;">
                            <p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;margin:0 0 2px 0;letter-spacing:0.12em;text-transform:uppercase;">Acciones</p>
                            <p style="font-family:Inter,sans-serif;font-size:22px;font-weight:700;color:#ffffff;margin:0 0 2px 0;">{stats['shares_owned']:.4f}</p>
                            <p style="font-family:Inter,sans-serif;font-size:9px;color:#556677;margin:0;">Compradas {_h_buys:.2f} · Vendidas {_h_sells:.2f}</p>
                        </div>
                        <div style="background:#021C36;padding:12px 16px;">
                            <p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;margin:0 0 2px 0;letter-spacing:0.12em;text-transform:uppercase;">Tu inversión</p>
                            <p style="font-family:Inter,sans-serif;font-size:22px;font-weight:700;color:#ffffff;margin:0 0 2px 0;">${stats['pocket_investment']:,.2f}</p>
                            <p style="font-family:Inter,sans-serif;font-size:9px;color:#556677;margin:0;">lo que pusiste de tu bolsillo</p>
                        </div>
                        <div style="background:#021C36;padding:12px 16px;">
                            <p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;margin:0 0 2px 0;letter-spacing:0.12em;text-transform:uppercase;">Base broker (con ROC)</p>
                            {f'<p style="font-family:Inter,sans-serif;font-size:22px;font-weight:700;color:#ffffff;margin:0 0 2px 0;">${stats["ib_cost_basis"]:,.2f}</p><p style="font-family:Inter,sans-serif;font-size:9px;color:#4caf82;margin:0;">ROC: ${stats["roc_accumulated"]:,.2f} ({stats["roc_percent"]:.1f}%)</p>' if stats.get("ib_cost_basis") is not None else '<p style="font-family:Inter,sans-serif;font-size:22px;font-weight:700;color:#445566;margin:0 0 2px 0;">—</p><p style="font-family:Inter,sans-serif;font-size:9px;color:#445566;margin:0;">Ingresa base IB en el sidebar</p>'}
                        </div>
                        <div style="background:#021C36;padding:12px 16px;">
                            <p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;margin:0 0 2px 0;letter-spacing:0.12em;text-transform:uppercase;">Valor de Mercado</p>
                            <p style="font-family:Inter,sans-serif;font-size:22px;font-weight:700;color:#ffffff;margin:0 0 2px 0;">${stats['market_value']:,.2f}</p>
                            <p style="font-family:Inter,sans-serif;font-size:9px;color:#556677;margin:0;">@ ${stats['current_price']:,.2f} por acción</p>
                        </div>
                        <div style="background:#021C36;padding:12px 16px;border-left:2px solid #4caf82;">
                            <p style="font-family:Inter,sans-serif;font-size:9px;color:#4caf82;margin:0 0 2px 0;letter-spacing:0.12em;text-transform:uppercase;">Prox. mes (est.)</p>
                            {_proj_cell}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    for _sp in stats.get('splits_detected', []):
                        _ratio = _sp['ratio']
                        _kind = "Split" if _ratio > 1 else "Reverse Split"
                        st.info(f"{_kind} detectado: {ticker} {_ratio:.0f}:1 el {_sp['date']} — las cantidades de acciones han sido ajustadas automáticamente.")

                    if stats.get('history_incomplete'):
                        st.warning(f"{ticker}: El CSV no contiene el historial completo de compras. Algunas ventas exceden las compras registradas — las métricas de riesgo (volatilidad, beta, alpha) pueden estar subestimadas. Exporta un CSV con historial desde el inicio de tu posición para resultados precisos.")

                    # ROC Callout — solo si hay datos de IB
                    if stats.get('ib_cost_basis') is not None and stats.get('roc_accumulated') is not None:
                        _roc_acc = stats['roc_accumulated']
                        _roc_pct_v = stats['roc_percent']
                        _ib_b_v = stats['ib_cost_basis']
                        _pocket_v = stats['pocket_investment']
                        st.markdown(
                            f'<div class="da-roc-callout">'
                            f'<p class="da-roc-callout-title">Return of Capital detectado</p>'
                            f'<div class="da-roc-callout-values">'
                            f'<div><p class="da-roc-number">${_roc_acc:,.2f}</p>'
                            f'<p class="da-roc-sub">ROC acumulado</p></div>'
                            f'<div><p class="da-roc-number">{_roc_pct_v:.1f}%</p>'
                            f'<p class="da-roc-sub">del costo real</p></div>'
                            f'<div><p class="da-roc-number">${_ib_b_v:,.2f}</p>'
                            f'<p class="da-roc-sub">base actual del broker</p></div>'
                            f'</div>'
                            f'<p class="da-roc-explain">Tu broker redujo tu base de ${_pocket_v:,.2f} a ${_ib_b_v:,.2f} '
                            f'porque {_roc_pct_v:.1f}% de las distribuciones fue clasificado como Return of Capital.'
                            f' Esto reduce tu ganancia de capital imponible al vender.</p>'
                            f'</div>',
                            unsafe_allow_html=True
                        )

                    # Fase 6: Cobertura del CSV
                    _cov = stats.get('csv_coverage_pct')
                    _inc_yf = stats.get('csv_inception_yf')
                    if _cov is not None:
                        _cov_color = "#006497" if _cov >= 80 else ("#e67e22" if _cov >= 60 else "#c0392b")
                        _inc_txt = f" (ticker cotiza desde {_inc_yf})" if _inc_yf else ""
                        st.markdown(f'<p style="font-family:Inter,sans-serif;font-size:11px;color:{_cov_color};margin:0 0 2px 0;">CSV cubre el <b>{_cov:.0f}%</b> del historial disponible{_inc_txt}</p>', unsafe_allow_html=True)
                        if _cov < 80:
                            st.caption("Se recomienda >=80% de cobertura para métricas de riesgo confiables")

                    # Fase 2: Discrepancias de precio
                    for _disc in stats.get('price_discrepancies', []):
                        st.warning(f"Posible evento corporativo no registrado en {ticker} el {_disc['date']}: precio CSV ${_disc['csv_price']:.2f} vs yfinance ${_disc['yf_price']:.2f} (ratio {_disc['ratio']:.2f}x). Verifica si hubo un split adicional.")

                    # Fase 3: Eventos corporativos (dividendos especiales)
                    for _ca in stats.get('corporate_actions', []):
                        if _ca['type'] == 'Dividendo especial':
                            st.info(f"Dividendo especial detectado en {ticker} el {_ca['date']}: ${_ca.get('amount', 0):.4f} por acción")

                    # Fase 9: Total Return primero — Capital + Income desglosados
                    _total_ret = stats['market_value'] + stats['dividends_collected_cash'] - stats['pocket_investment']
                    _total_ret_pct = (_total_ret / stats['pocket_investment'] * 100) if stats['pocket_investment'] > 0 else 0
                    _cap_comp = stats['market_value'] - stats['pocket_investment']
                    _inc_comp = stats['dividends_collected_cash']
                    _tr_color = "#4caf82" if _total_ret >= 0 else "#e05c5c"
                    _cap_color = "#4caf82" if _cap_comp >= 0 else "#e05c5c"
                    st.markdown(f"""
                    <div style="background-color:#021C36;padding:16px 20px;margin:8px 0 12px 0;border-left:4px solid #006497;">
                        <p style="font-family:Inter,sans-serif;font-size:10px;color:#8899aa;margin:0 0 4px 0;letter-spacing:0.12em;text-transform:uppercase;">Retorno Total</p>
                        <p style="font-family:Inter,sans-serif;font-size:26px;font-weight:800;color:{_tr_color};margin:0 0 8px 0;">${_total_ret:+,.2f} &nbsp;<span style="font-size:16px;font-weight:600;">({_total_ret_pct:+.2f}%)</span></p>
                        <p style="font-family:Inter,sans-serif;font-size:12px;color:#aaaaaa;margin:0;">Capital: <b style="color:{_cap_color};">${_cap_comp:+,.2f}</b> &nbsp;&nbsp;·&nbsp;&nbsp; Income: <b style="color:#4caf82;">${_inc_comp:,.2f}</b></p>
                    </div>
                    """, unsafe_allow_html=True)

                    # NAV Erosion callout — solo cuando el precio cayó (relevante para YieldMax)
                    if _cap_comp < 0:
                        _erosion_amt = abs(_cap_comp)
                        _offset = _inc_comp - _erosion_amt
                        _nav_m_income = stats.get('monthly_income')
                        _nav_avg_monthly = (
                            _nav_m_income.mean()
                            if (_nav_m_income is not None and not _nav_m_income.empty and _nav_m_income.mean() > 0)
                            else None
                        )
                        if _offset >= 0:
                            _nav_label   = "COMPENSADO"
                            _nav_border  = "#4caf82"
                            _nav_verdict = f"Los dividendos superaron la caída de precio en <b style='color:#4caf82;'>${_offset:,.2f}</b>. Tu capital está cubierto por el income."
                        else:
                            _deficit_nav = abs(_offset)
                            _nav_label   = "DEFICIT NETO"
                            _nav_border  = "#e05c5c"
                            if _nav_avg_monthly and _nav_avg_monthly > 0:
                                _months_nav = _deficit_nav / _nav_avg_monthly
                                _nav_verdict = (
                                    f"Faltan <b style='color:#e05c5c;'>${_deficit_nav:,.2f}</b> en dividendos para cubrir la caída — "
                                    f"a tasa actual (~${_nav_avg_monthly:,.0f}/mes): <b>~{_months_nav:.0f} meses más</b>"
                                )
                            else:
                                _nav_verdict = f"Faltan <b style='color:#e05c5c;'>${_deficit_nav:,.2f}</b> en dividendos para cubrir la caída de precio"
                        st.markdown(
                            f'<div style="border-left:4px solid {_nav_border};padding:12px 16px;margin:0 0 12px 0;background:#f6f3f2;">'
                            f'<p style="font-family:Inter,sans-serif;font-size:9px;color:{_nav_border};font-weight:700;'
                            f'letter-spacing:0.12em;text-transform:uppercase;margin:0 0 8px 0;">NAV EROSION · {_nav_label}</p>'
                            f'<div style="display:flex;gap:20px;align-items:flex-end;margin-bottom:8px;">'
                            f'<div><p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;margin:0 0 2px 0;'
                            f'letter-spacing:0.10em;text-transform:uppercase;">Caida de precio</p>'
                            f'<p style="font-family:Inter,sans-serif;font-size:20px;font-weight:800;color:#e05c5c;margin:0;">'
                            f'${_erosion_amt:,.2f}</p></div>'
                            f'<p style="font-family:Inter,sans-serif;font-size:16px;color:#cccccc;margin:0 0 4px 0;">vs</p>'
                            f'<div><p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;margin:0 0 2px 0;'
                            f'letter-spacing:0.10em;text-transform:uppercase;">Income cobrado</p>'
                            f'<p style="font-family:Inter,sans-serif;font-size:20px;font-weight:800;color:#4caf82;margin:0;">'
                            f'${_inc_comp:,.2f}</p></div>'
                            f'</div>'
                            f'<p style="font-family:Inter,sans-serif;font-size:11px;color:#555555;margin:0;">{_nav_verdict}</p>'
                            f'</div>',
                            unsafe_allow_html=True
                        )

                    # Fase 7: IRR + ROI + Yield on Cost + Break-even
                    _irr_val = stats.get('irr_anual')
                    _irr_str = f"{_irr_val:+.2f}%" if _irr_val is not None else "N/A"
                    _be_income = stats.get('monthly_income')
                    _be_avg = (
                        _be_income.mean()
                        if (_be_income is not None and not _be_income.empty and _be_income.mean() > 0)
                        else None
                    )
                    _divs_recv = stats.get('dividends_collected_cash', 0)
                    if _divs_recv >= stats['pocket_investment']:
                        _be_str = "Ya recuperado"
                        _be_help = f"Los dividendos cobrados (${_divs_recv:,.0f}) ya superan tu inversión inicial"
                    elif _be_avg and _be_avg > 0:
                        _remaining_to_recover = stats['pocket_investment'] - _divs_recv
                        _months_left = _remaining_to_recover / _be_avg
                        _be_date = (datetime.date.today() + datetime.timedelta(days=int(_months_left * 30.44))).strftime('%b %Y')
                        _be_str = f"{_be_date} (~{int(_months_left)} m)"
                        _be_help = (
                            f"Faltan ${_remaining_to_recover:,.0f} en dividendos para recuperar tu inversión. "
                            f"A ${_be_avg:,.0f}/mes promedio, ~{int(_months_left)} meses más."
                        )
                    else:
                        _be_str = "N/A"
                        _be_help = "Sin historial de dividendos suficiente para calcular"
                    _a1, _a2, _a3, _a4 = st.columns(4)
                    _a1.metric("ROI Total", f"{stats['roi_percent']:+.2f}%")
                    _a2.metric("TIR Anualizado", _irr_str, help="Tasa interna de retorno — considera el momento exacto de cada inversión. Más preciso que ROI para compras escalonadas.")
                    _a3.metric("Yield on Cost", f"{stats.get('yield_on_cost', 0):.2f}%")
                    _a4.metric("Break-even", _be_str, help=_be_help)

                    results_data = {
                        "Indicador": [
                            "Inversión (el dinero que tu pusiste)",
                            "Valor de Mercado (valor de tu inversión hoy)",
                            "Div. Efectivo (dividendos pagados a tu balance)",
                            "Valor de Div. Reinvertidos",
                            "Total generado en dividendos (Cash + Reinversión)",
                            "Acciones Compradas",
                            "Acciones por DRIP",
                            "Acciones Totales",
                            "Ganancia en $",
                            "Ganancia en %"
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

                    st.markdown("### VERIFICACIÓN RÁPIDA")
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
                        st.markdown("### CALENDARIO DE INCOME MENSUAL")
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

                if shown_a:
                    _ca_rows = [
                        (ticker, stats) for ticker, stats in results.items()
                        if classify_map.get(ticker) == 'mode_a' and 'error' not in stats
                    ]
                    if _ca_rows:
                        st.markdown("### RESUMEN CONSOLIDADO — FONDOS DE DIVIDENDOS")
                        _ca_total_inv = sum(s['pocket_investment'] for _, s in _ca_rows)
                        _ca_total_mv  = sum(s['market_value'] for _, s in _ca_rows)
                        _ca_total_div = sum(s.get('dividends_collected_cash', 0) for _, s in _ca_rows)
                        _ca_total_tr  = _ca_total_mv + _ca_total_div - _ca_total_inv
                        _ca_total_tr_pct = (_ca_total_tr / _ca_total_inv * 100) if _ca_total_inv > 0 else 0
                        _ca_tbody = ""
                        _ca_has_roc = any(_cs.get('ib_cost_basis') is not None for _, _cs in _ca_rows)
                        _ca_total_ib  = sum(_cs['ib_cost_basis'] for _, _cs in _ca_rows if _cs.get('ib_cost_basis') is not None)
                        _ca_total_roc = sum(_cs['roc_accumulated'] for _, _cs in _ca_rows if _cs.get('roc_accumulated') is not None)
                        _ca_total_roc_pct = round(_ca_total_roc / _ca_total_inv * 100, 1) if (_ca_has_roc and _ca_total_inv > 0) else None
                        for _ct, _cs in _ca_rows:
                            _cr = _cs['roi_percent']
                            _cc = "#4caf82" if _cr >= 0 else "#e05c5c"
                            _ib_b = _cs.get('ib_cost_basis')
                            _roc_a = _cs.get('roc_accumulated')
                            _roc_p = _cs.get('roc_percent')
                            _ib_str  = f'${_ib_b:,.2f}' if _ib_b is not None else '—'
                            _roc_str = f'${_roc_a:,.2f} <span style="color:#4caf82;">({_roc_p:.1f}%)</span>' if _roc_a is not None else '—'
                            _ib_color  = '#ffffff' if _ib_b is not None else '#445566'
                            _ca_tbody += (
                                f'<tr style="border-bottom:1px solid #0d2a42;">'
                                f'<td style="padding:7px 10px;font-weight:700;color:#ffffff;">{_ct}</td>'
                                f'<td style="padding:7px 10px;text-align:right;">{_cs["shares_owned"]:.4f}</td>'
                                f'<td style="padding:7px 10px;text-align:right;">${_cs["pocket_investment"]:,.2f}</td>'
                                f'<td style="padding:7px 10px;text-align:right;">${_cs.get("dividends_collected_cash",0):,.2f}</td>'
                                f'<td style="padding:7px 10px;text-align:right;">${_cs["market_value"]:,.2f}</td>'
                                f'<td style="padding:7px 10px;text-align:right;color:{_ib_color};">{_ib_str}</td>'
                                f'<td style="padding:7px 10px;text-align:right;">{_roc_str}</td>'
                                f'<td style="padding:7px 10px;text-align:right;color:{_cc};font-weight:600;">{_cr:+.2f}%</td>'
                                f'</tr>'
                            )
                        _ca_tr_color = "#4caf82" if _ca_total_tr_pct >= 0 else "#e05c5c"
                        _total_ib_str  = f'${_ca_total_ib:,.2f}' if _ca_has_roc else 'Ver broker'
                        _total_roc_str = f'${_ca_total_roc:,.2f} <span style="color:#4caf82;">({_ca_total_roc_pct:.1f}%)</span>' if _ca_has_roc else '—'
                        _total_ib_color = '#ffffff' if _ca_has_roc else '#445566'
                        st.markdown(f"""
<div style="overflow-x:auto;margin:4px 0 6px 0;">
<table class="da-table" style="width:100%;border-collapse:collapse;font-family:Inter,sans-serif;font-size:12px;color:#aaaaaa;background:#010f1c;">
  <thead>
    <tr style="border-bottom:2px solid #006497;">
      <th style="padding:8px 10px;text-align:left;color:#8899aa;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">Ticker</th>
      <th style="padding:8px 10px;text-align:right;color:#8899aa;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">Acciones</th>
      <th style="padding:8px 10px;text-align:right;color:#8899aa;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">Tu inversión</th>
      <th style="padding:8px 10px;text-align:right;color:#8899aa;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">Dividendos Cobrados</th>
      <th style="padding:8px 10px;text-align:right;color:#8899aa;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">Valor Mercado</th>
      <th style="padding:8px 10px;text-align:right;color:#8899aa;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">Base de Coste (ROC)</th>
      <th style="padding:8px 10px;text-align:right;color:#8899aa;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">ROC Acumulado</th>
      <th style="padding:8px 10px;text-align:right;color:#8899aa;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">ROI Total</th>
    </tr>
  </thead>
  <tbody>
    {_ca_tbody}
    <tr style="border-top:2px solid #006497;font-weight:700;">
      <td style="padding:8px 10px;color:#ffffff;">Total</td>
      <td style="padding:8px 10px;"></td>
      <td style="padding:8px 10px;text-align:right;color:#ffffff;">${_ca_total_inv:,.2f}</td>
      <td style="padding:8px 10px;text-align:right;color:#ffffff;">${_ca_total_div:,.2f}</td>
      <td style="padding:8px 10px;text-align:right;color:#ffffff;">${_ca_total_mv:,.2f}</td>
      <td style="padding:8px 10px;text-align:right;color:{_total_ib_color};">{_total_ib_str}</td>
      <td style="padding:7px 10px;text-align:right;">{_total_roc_str}</td>
      <td style="padding:8px 10px;text-align:right;color:{_ca_tr_color};">{_ca_total_tr_pct:+.2f}%</td>
    </tr>
  </tbody>
</table>
</div>
<p style="font-family:Inter,sans-serif;font-size:10px;color:#445566;margin:4px 0 16px 0;">Base de Coste (ROC): el broker reduce el costo base por distribuciones clasificadas como Return of Capital. En Interactive Brokers: Portafolio → Posiciones → columna "Base de coste". En Charles Schwab: Cuentas → Posiciones → columna "Cost Basis".</p>
                        """, unsafe_allow_html=True)

                if not shown_a:
                    st.info("No hay posiciones YieldMax activas en este portafolio.")

            # ── TAB B — ETFs de Crecimiento ────────────────────────────
            with tab_b:
                shown_b = False
                for ticker, stats in results.items():
                    if classify_map.get(ticker) != 'mode_b':
                        continue
                    if "error" in stats:
                        _ec_b = _csv_ticker_data.get(ticker, {})
                        _ec_b_html = ''
                        if _ec_b:
                            _ec_b_html = (
                                f'<div><p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;'
                                f'margin:0;letter-spacing:0.10em;text-transform:uppercase;">Acciones compradas</p>'
                                f'<p style="font-family:Inter,sans-serif;font-size:16px;font-weight:700;'
                                f'color:#1a1a1a;margin:2px 0 0 0;">{_ec_b.get("shares",0):.4f}</p></div>'
                                f'<div><p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;'
                                f'margin:0;letter-spacing:0.10em;text-transform:uppercase;">Invertido (CSV)</p>'
                                f'<p style="font-family:Inter,sans-serif;font-size:16px;font-weight:700;'
                                f'color:#1a1a1a;margin:2px 0 0 0;">${_ec_b.get("invested",0):,.2f}</p></div>'
                                f'<div><p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;'
                                f'margin:0;letter-spacing:0.10em;text-transform:uppercase;">Primera compra</p>'
                                f'<p style="font-family:Inter,sans-serif;font-size:16px;font-weight:700;'
                                f'color:#1a1a1a;margin:2px 0 0 0;">{_ec_b.get("first_date","N/A")}</p></div>'
                            )
                        st.markdown(
                            f'<div style="border-left:4px solid #e05c5c;background:#fff8f8;'
                            f'padding:16px 20px;margin:8px 0 16px 0;">'
                            f'<p style="font-family:Inter,sans-serif;font-size:9px;color:#e05c5c;font-weight:700;'
                            f'letter-spacing:0.12em;text-transform:uppercase;margin:0 0 8px 0;">'
                            f'PRECIO NO DISPONIBLE · {ticker}</p>'
                            f'<p style="font-family:Inter,sans-serif;font-size:11px;color:#555;margin:0 0 10px 0;">'
                            f'yfinance no pudo cargar datos de mercado para este ETF.</p>'
                            f'<div style="display:flex;gap:20px;flex-wrap:wrap;margin:0 0 8px 0;">'
                            f'{_ec_b_html}</div>'
                            f'<p style="font-family:Inter,sans-serif;font-size:10px;color:#999;margin:0;">'
                            f'Detalle: {stats["error"]}</p>'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                        continue
                    shown_b = True
                    _roi_b = stats.get('roi_percent', 0)
                    _roi_color_b = "#4caf82" if _roi_b >= 0 else "#e05c5c"
                    st.markdown(
                        f'<div class="da-ticker-header">'
                        f'<span class="da-ticker-name">{ticker}</span>'
                        f'<span class="da-mode-badge da-mode-growth">Growth</span>'
                        f'<span class="da-ticker-price">'
                        f'${stats["current_price"]:,.2f} &nbsp;·&nbsp; '
                        f'<span style="color:{_roi_color_b};font-weight:700;">{_roi_b:+.2f}% ROI</span>'
                        f'</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                    _hb_buys = stats.get('shares_bought', 0)
                    _hb_sells = stats.get('shares_sold', 0)
                    st.markdown(f"""
                    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:2px;margin:8px 0 14px 0;">
                        <div style="background:#021C36;padding:12px 16px;">
                            <p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;margin:0 0 2px 0;letter-spacing:0.12em;text-transform:uppercase;">Acciones</p>
                            <p style="font-family:Inter,sans-serif;font-size:22px;font-weight:700;color:#ffffff;margin:0 0 2px 0;">{stats['shares_owned']:.4f}</p>
                            <p style="font-family:Inter,sans-serif;font-size:9px;color:#556677;margin:0;">Compradas {_hb_buys:.2f} · Vendidas {_hb_sells:.2f}</p>
                        </div>
                        <div style="background:#021C36;padding:12px 16px;">
                            <p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;margin:0 0 2px 0;letter-spacing:0.12em;text-transform:uppercase;">Tu inversión</p>
                            <p style="font-family:Inter,sans-serif;font-size:22px;font-weight:700;color:#ffffff;margin:0 0 2px 0;">${stats['pocket_investment']:,.2f}</p>
                            <p style="font-family:Inter,sans-serif;font-size:9px;color:#556677;margin:0;">lo que pusiste de tu bolsillo</p>
                        </div>
                        <div style="background:#021C36;padding:12px 16px;">
                            <p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;margin:0 0 2px 0;letter-spacing:0.12em;text-transform:uppercase;">Base broker (con ROC)</p>
                            {f'<p style="font-family:Inter,sans-serif;font-size:22px;font-weight:700;color:#ffffff;margin:0 0 2px 0;">${stats["ib_cost_basis"]:,.2f}</p><p style="font-family:Inter,sans-serif;font-size:9px;color:#4caf82;margin:0;">ROC: ${stats["roc_accumulated"]:,.2f} ({stats["roc_percent"]:.1f}%)</p>' if stats.get("ib_cost_basis") is not None else '<p style="font-family:Inter,sans-serif;font-size:22px;font-weight:700;color:#445566;margin:0 0 2px 0;">—</p><p style="font-family:Inter,sans-serif;font-size:9px;color:#445566;margin:0;">Ingresa base IB en el sidebar</p>'}
                        </div>
                        <div style="background:#021C36;padding:12px 16px;">
                            <p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;margin:0 0 2px 0;letter-spacing:0.12em;text-transform:uppercase;">Valor de Mercado</p>
                            <p style="font-family:Inter,sans-serif;font-size:22px;font-weight:700;color:#ffffff;margin:0 0 2px 0;">${stats['market_value']:,.2f}</p>
                            <p style="font-family:Inter,sans-serif;font-size:9px;color:#556677;margin:0;">@ ${stats['current_price']:,.2f} por acción</p>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    for _sp in stats.get('splits_detected', []):
                        _ratio = _sp['ratio']
                        _kind = "Split" if _ratio > 1 else "Reverse Split"
                        st.info(f"{_kind} detectado: {ticker} {_ratio:.0f}:1 el {_sp['date']} — las cantidades de acciones han sido ajustadas automáticamente.")

                    if stats.get('history_incomplete'):
                        st.warning(f"{ticker}: El CSV no contiene el historial completo de compras. Algunas ventas exceden las compras registradas — las métricas de riesgo (volatilidad, beta, alpha) pueden estar subestimadas. Exporta un CSV con historial desde el inicio de tu posición para resultados precisos.")

                    # Fase 6: Cobertura del CSV
                    _b_cov = stats.get('csv_coverage_pct')
                    _b_inc_yf = stats.get('csv_inception_yf')
                    if _b_cov is not None:
                        _b_cov_color = "#006497" if _b_cov >= 80 else ("#e67e22" if _b_cov >= 60 else "#c0392b")
                        _b_inc_txt = f" (ticker cotiza desde {_b_inc_yf})" if _b_inc_yf else ""
                        st.markdown(f'<p style="font-family:Inter,sans-serif;font-size:11px;color:{_b_cov_color};margin:0 0 2px 0;">CSV cubre el <b>{_b_cov:.0f}%</b> del historial disponible{_b_inc_txt}</p>', unsafe_allow_html=True)
                        if _b_cov < 80:
                            st.caption("Se recomienda >=80% de cobertura para métricas de riesgo confiables")

                    # Fase 2: Discrepancias de precio
                    for _b_disc in stats.get('price_discrepancies', []):
                        st.warning(f"Posible evento corporativo no registrado en {ticker} el {_b_disc['date']}: precio CSV ${_b_disc['csv_price']:.2f} vs yfinance ${_b_disc['yf_price']:.2f} (ratio {_b_disc['ratio']:.2f}x). Verifica si hubo un split adicional.")

                    # Fase 3: Eventos corporativos (dividendos especiales)
                    for _b_ca in stats.get('corporate_actions', []):
                        if _b_ca['type'] == 'Dividendo especial':
                            st.info(f"Dividendo especial detectado en {ticker} el {_b_ca['date']}: ${_b_ca.get('amount', 0):.4f} por acción")

                    # Fase 4: Retorno total incluye dividendos cobrados (no solo apreciación de precio)
                    _b_divs = stats.get('dividends_collected_cash', 0)
                    _b_total_ret = stats['market_value'] + _b_divs - stats['pocket_investment']
                    _b_total_ret_pct = (_b_total_ret / stats['pocket_investment'] * 100) if stats['pocket_investment'] > 0 else 0
                    cagr_str = f"{stats['cagr']:.2f}%" if stats.get('cagr') is not None else "N/A"
                    _b_irr_val = stats.get('irr_anual')
                    _b_irr_str = f"{_b_irr_val:+.2f}%" if _b_irr_val is not None else "N/A"
                    bc3, bc4 = st.columns(2)
                    bc3.metric("Retorno Total", f"${_b_total_ret:+,.2f}", delta=f"{_b_total_ret_pct:+.2f}%", help="Apreciación de precio + dividendos cobrados")
                    bc4.metric("IRR Anualizado", _b_irr_str, help="Tasa interna de retorno — considera el timing real de cada compra. Más preciso que CAGR para compras escalonadas.")
                    _b_bench_roi = stats.get('benchmark_roi')
                    st.markdown(f'<p style="font-family:Inter,sans-serif;font-size:11px;color:#556677;margin:4px 0 4px 0;">CAGR: <b>{cagr_str}</b></p>', unsafe_allow_html=True)
                    # Fase 8: Benchmark con timing real
                    if _b_bench_roi is not None:
                        _b_diff = _b_total_ret_pct - _b_bench_roi
                        _b_bench_color = "#4caf82" if _b_diff >= 0 else "#e05c5c"
                        st.markdown(f'<p style="font-family:Inter,sans-serif;font-size:12px;color:{_b_bench_color};margin:0 0 12px 0;">vs VOO (mismo timing): <b>{_b_bench_roi:+.2f}%</b> · Tu ventaja: <b>{_b_diff:+.2f}%</b></p>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div style="margin-bottom:12px;"></div>', unsafe_allow_html=True)

                    # Mode B dividends (VTI, SCHB, SCHD pay quarterly cash dividends)
                    b_monthly = stats.get('monthly_income')
                    if b_monthly is not None and not b_monthly.empty:
                        import altair as alt
                        b_yoc = stats.get('yield_on_cost', 0)
                        b_total_div = stats.get('dividends_collected_cash', 0)
                        st.markdown("### DIVIDENDOS COBRADOS")
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

                if shown_b:
                    _cb_rows = [
                        (ticker, stats) for ticker, stats in results.items()
                        if classify_map.get(ticker) == 'mode_b' and 'error' not in stats
                    ]
                    if _cb_rows:
                        st.markdown("### RESUMEN CONSOLIDADO — ETFs DE CRECIMIENTO")
                        _cb_total_inv = sum(s['pocket_investment'] for _, s in _cb_rows)
                        _cb_total_mv  = sum(s['market_value'] for _, s in _cb_rows)
                        _cb_total_div = sum(s.get('dividends_collected_cash', 0) for _, s in _cb_rows)
                        _cb_total_tr  = _cb_total_mv + _cb_total_div - _cb_total_inv
                        _cb_total_tr_pct = (_cb_total_tr / _cb_total_inv * 100) if _cb_total_inv > 0 else 0
                        _cb_has_roc = any(_cs.get('ib_cost_basis') is not None for _, _cs in _cb_rows)
                        _cb_total_ib  = sum(_cs['ib_cost_basis'] for _, _cs in _cb_rows if _cs.get('ib_cost_basis') is not None)
                        _cb_total_roc = sum(_cs['roc_accumulated'] for _, _cs in _cb_rows if _cs.get('roc_accumulated') is not None)
                        _cb_total_roc_pct = round(_cb_total_roc / _cb_total_inv * 100, 1) if (_cb_has_roc and _cb_total_inv > 0) else None
                        _cb_tbody = ""
                        for _ct, _cs in _cb_rows:
                            _cr = _cs['roi_percent']
                            _cc = "#4caf82" if _cr >= 0 else "#e05c5c"
                            _ib_b = _cs.get('ib_cost_basis')
                            _roc_a = _cs.get('roc_accumulated')
                            _roc_p = _cs.get('roc_percent')
                            _ib_str  = f'${_ib_b:,.2f}' if _ib_b is not None else '—'
                            _roc_str = f'${_roc_a:,.2f} <span style="color:#4caf82;">({_roc_p:.1f}%)</span>' if _roc_a is not None else '—'
                            _ib_color  = '#ffffff' if _ib_b is not None else '#445566'
                            _cb_tbody += (
                                f'<tr style="border-bottom:1px solid #0d2a42;">'
                                f'<td style="padding:7px 10px;font-weight:700;color:#ffffff;">{_ct}</td>'
                                f'<td style="padding:7px 10px;text-align:right;">{_cs["shares_owned"]:.4f}</td>'
                                f'<td style="padding:7px 10px;text-align:right;">${_cs["pocket_investment"]:,.2f}</td>'
                                f'<td style="padding:7px 10px;text-align:right;">${_cs.get("dividends_collected_cash",0):,.2f}</td>'
                                f'<td style="padding:7px 10px;text-align:right;">${_cs["market_value"]:,.2f}</td>'
                                f'<td style="padding:7px 10px;text-align:right;color:{_ib_color};">{_ib_str}</td>'
                                f'<td style="padding:7px 10px;text-align:right;">{_roc_str}</td>'
                                f'<td style="padding:7px 10px;text-align:right;color:{_cc};font-weight:600;">{_cr:+.2f}%</td>'
                                f'</tr>'
                            )
                        _cb_tr_color = "#4caf82" if _cb_total_tr_pct >= 0 else "#e05c5c"
                        _total_cb_ib_str  = f'${_cb_total_ib:,.2f}' if _cb_has_roc else 'Ver broker'
                        _total_cb_roc_str = f'${_cb_total_roc:,.2f} <span style="color:#4caf82;">({_cb_total_roc_pct:.1f}%)</span>' if _cb_has_roc else '—'
                        _total_cb_ib_color = '#ffffff' if _cb_has_roc else '#445566'
                        st.markdown(f"""
<div style="overflow-x:auto;margin:4px 0 6px 0;">
<table class="da-table" style="width:100%;border-collapse:collapse;font-family:Inter,sans-serif;font-size:12px;color:#aaaaaa;background:#010f1c;">
  <thead>
    <tr style="border-bottom:2px solid #006497;">
      <th style="padding:8px 10px;text-align:left;color:#8899aa;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">Ticker</th>
      <th style="padding:8px 10px;text-align:right;color:#8899aa;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">Acciones</th>
      <th style="padding:8px 10px;text-align:right;color:#8899aa;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">Tu inversión</th>
      <th style="padding:8px 10px;text-align:right;color:#8899aa;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">Dividendos Cobrados</th>
      <th style="padding:8px 10px;text-align:right;color:#8899aa;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">Valor Mercado</th>
      <th style="padding:8px 10px;text-align:right;color:#8899aa;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">Base de Coste (ROC)</th>
      <th style="padding:8px 10px;text-align:right;color:#8899aa;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">ROC Acumulado</th>
      <th style="padding:8px 10px;text-align:right;color:#8899aa;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">ROI Total</th>
    </tr>
  </thead>
  <tbody>
    {_cb_tbody}
    <tr style="border-top:2px solid #006497;font-weight:700;">
      <td style="padding:8px 10px;color:#ffffff;">Total</td>
      <td style="padding:8px 10px;"></td>
      <td style="padding:8px 10px;text-align:right;color:#ffffff;">${_cb_total_inv:,.2f}</td>
      <td style="padding:8px 10px;text-align:right;color:#ffffff;">${_cb_total_div:,.2f}</td>
      <td style="padding:8px 10px;text-align:right;color:#ffffff;">${_cb_total_mv:,.2f}</td>
      <td style="padding:8px 10px;text-align:right;color:{_total_cb_ib_color};">{_total_cb_ib_str}</td>
      <td style="padding:7px 10px;text-align:right;">{_total_cb_roc_str}</td>
      <td style="padding:8px 10px;text-align:right;color:{_cb_tr_color};">{_cb_total_tr_pct:+.2f}%</td>
    </tr>
  </tbody>
</table>
</div>
<p style="font-family:Inter,sans-serif;font-size:10px;color:#445566;margin:4px 0 16px 0;">Base de Coste (ROC): el broker reduce el costo base por distribuciones clasificadas como Return of Capital. En Interactive Brokers: Portafolio → Posiciones → columna "Base de coste". En Charles Schwab: Cuentas → Posiciones → columna "Cost Basis".</p>
                        """, unsafe_allow_html=True)

                if not shown_b:
                    st.info("No hay ETFs de crecimiento activos en este portafolio.")

            # ============================================================
            # Section F — Risk Analysis
            # ============================================================
            st.markdown("### ANÁLISIS DE RIESGO")
            total_port_value = sum(s.get('market_value', 0) for s in results.values() if 'error' not in s)
            risk_data = logic.build_risk_analysis(results, classify_map, total_port_value)

            if risk_data['yieldmax_risk']:
                st.markdown("#### YieldMax — Riesgo por Subyacente")
                for item in risk_data['yieldmax_risk']:
                    risk_color = '#c8102e' if item['risk_level'] == 'HIGH' else '#e68a00' if item['risk_level'] == 'MEDIUM' else '#555555'
                    risk_badge = f'<span style="display:inline-block;background-color:{risk_color};color:#fff;font-family:Inter,sans-serif;font-size:9px;font-weight:700;letter-spacing:0.10em;padding:2px 7px;border-radius:0px;">{item["risk_level"]}</span>'
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
    st.subheader("Simulación de Estrategia DRIP")
    st.caption("DRIP (Dividend Reinvestment Plan) = los dividendos se reinvierten automáticamente comprando más acciones, en lugar de cobrarlos en efectivo")

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
            m2.metric("Con DRIP (dividendos reinvertidos)", f"${sim_results['drip_final_value']:,.2f}",
                      delta=f"{sim_results['drip_roi_percent']:.2f}%")
            m3.metric("Sin DRIP (dividendos en efectivo)", f"${sim_results['nodrip_final_value']:,.2f}",
                      delta=f"{sim_results['nodrip_roi_percent']:.2f}%")

            # Chart
            st.subheader("Evolución de Patrimonio")
            hist = sim_results['history']
            import altair as alt
            _sim_long = hist[['DRIP Wealth', 'No-DRIP Wealth']].reset_index().melt(
                id_vars='Date', var_name='Estrategia', value_name='Valor'
            )
            _sim_long['Estrategia'] = _sim_long['Estrategia'].map({
                'DRIP Wealth': 'Con DRIP (reinvirtiendo)',
                'No-DRIP Wealth': 'Sin DRIP (efectivo)'
            })
            _sim_area = alt.Chart(_sim_long[_sim_long['Estrategia'] == 'Con DRIP (reinvirtiendo)']).mark_area(
                opacity=0.08, color=CHART_PALETTE["portfolio"], interpolate='monotone'
            ).encode(x=alt.X('Date:T'), y=alt.Y('Valor:Q'))
            _sim_lines = alt.Chart(_sim_long).mark_line(strokeWidth=2.5, interpolate='monotone').encode(
                x=alt.X('Date:T', title='Fecha'),
                y=alt.Y('Valor:Q', title='Valor ($)', axis=alt.Axis(format='$,.0f')),
                color=alt.Color('Estrategia:N', scale=alt.Scale(
                    domain=['Con DRIP (reinvirtiendo)', 'Sin DRIP (efectivo)'],
                    range=[CHART_PALETTE["portfolio"], CHART_PALETTE["sp500"]]
                )),
                tooltip=[
                    alt.Tooltip('Date:T', format='%Y-%m-%d', title='Fecha'),
                    alt.Tooltip('Estrategia:N', title='Estrategia'),
                    alt.Tooltip('Valor:Q', format='$,.2f', title='Valor')
                ]
            )
            _sim_chart = (_sim_area + _sim_lines).properties(
                height=320, background=CHART_PALETTE["bg"]
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
            st.altair_chart(_sim_chart, use_container_width=True)

# --- Footer Disclaimer — The Architectural Authority, anclaje #021C36 ---
FOOTER_STYLE = "background-color:#021C36;padding:32px 40px;margin-top:48px;"
BADGE_STYLE  = "display:inline-block;font-family:'Inter',sans-serif;font-size:10px;font-weight:500;letter-spacing:0.12em;text-transform:uppercase;color:#006497;border:1px solid #006497;padding:3px 8px;margin-bottom:14px;"
TITLE_STYLE  = "font-family:'Inter',sans-serif;font-size:13px;font-weight:700;letter-spacing:-0.01em;color:#ffffff;margin:0 0 12px 0;max-width:720px;line-height:1.5;"
BODY1_STYLE  = "font-family:'Inter',sans-serif;font-size:11px;color:rgba(255,255,255,0.65);line-height:1.7;margin:0 0 8px 0;max-width:720px;"
BODY2_STYLE  = "font-family:'Inter',sans-serif;font-size:11px;color:rgba(255,255,255,0.40);line-height:1.7;margin:0;max-width:720px;"

st.markdown(
    f'<div style="{FOOTER_STYLE}">'
    f'<span style="{BADGE_STYLE}">Versión Beta</span>'
    f'<p style="{TITLE_STYLE}">Esta herramienta es de carácter informativo y estimativo — no constituye asesoría financiera.</p>'
    f'<p style="{BODY1_STYLE}">Los datos, cálculos y proyecciones pueden presentar errores o inexactitudes. Siempre verifica con tus propios registros o los estados de cuenta de tu casa de bolsa.</p>'
    f'<p style="{BODY2_STYLE}">El uso de esta aplicación es bajo tu propio riesgo. Reporta cualquier fallo o inconsistencia para ayudarnos a seguir mejorando.</p>'
    '</div>',
    unsafe_allow_html=True
)
