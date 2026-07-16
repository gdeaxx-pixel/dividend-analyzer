import streamlit as st
import pandas as pd

import datetime
import importlib
import logic
import storage
import json
import os
import time

# Streamlit Cloud puede conservar en memoria una versión vieja de `logic` tras un push
# (el módulo importado no siempre se reimporta sin un "Reboot app" manual). Si falta
# algún símbolo reciente, el módulo está rancio → recargarlo desde disco. Equivale a un
# reboot automático: revive de un golpe todas las funciones nuevas sin crashear el análisis.
_LOGIC_SENTINELS = (
    "load_roc_19a", "project_portfolio_forward", "build_portfolio_verdict",
    "monte_carlo_projection", "build_factor_concentration", "build_underlying_exposure",
    "nra_tax_breakdown", "build_risk_analysis", "build_interpretation",
    "classify_roc_health", "load_roc_health_history", "latest_health_verdict",
    "build_yieldmax_total_return_series",
    "build_total_return_series", "build_roc_aware_withholding", "estimate_roc_refund",
    "estimate_roc_refund_by_year", "extract_roc_credit_from_pdf",
)
if not all(hasattr(logic, _s) for _s in _LOGIC_SENTINELS):
    logic = importlib.reload(logic)


def _roc_detail_card(stats):
    """HTML del valor 'Costo base IB / ROC' de las tarjetas de detalle por activo.
    Soporta ROC estimado por avisos 19a (cuando no hay costo base del bróker)."""
    if stats.get("ib_cost_basis") is not None:
        _cb = f'<p class="da-tkpi-value">${stats["ib_cost_basis"]:,.2f}</p>'
        _ra = stats.get("roc_accumulated")
        if _ra is not None:
            _rp = stats.get("roc_percent")
            _rp_txt = f' ({_rp:.1f}%)' if _rp is not None else ''
            # ROC en ámbar (no verde): un ROC alto no es buen resultado.
            return _cb + (f'<p class="da-tkpi-sub" style="color:#c9821f;">ROC: ${_ra:,.2f}{_rp_txt}</p>')
        return _cb
    if stats.get("roc_accumulated") is not None:
        return (f'<p class="da-tkpi-value" style="color:#c9821f;">ROC ~${stats["roc_accumulated"]:,.0f}</p>'
                f'<p class="da-tkpi-sub" style="color:#8899aa;">est. 19a '
                f'({(stats.get("roc_percent") or 0):.0f}% de distrib.)</p>')
    return ('<p class="da-tkpi-value" style="color:#cbd5e1;">—</p>'
            '<p class="da-tkpi-sub">Edítala al cargar (Paso 1)</p>')


def _money2(v, dash='n/d'):
    """Formatea $X.XX de forma None-segura (evita el crash de formatear None)."""
    return f'${v:,.2f}' if v is not None else dash


st.set_page_config(page_title="Calculadora de Dividendos", layout="wide")

# Flag reversible: panel "Explicación visual del ROC" (infografía IYG) por fondo con ROC.
# Poner en False lo desactiva al instante, sin tocar nada más. (added 2026-06-23)
SHOW_ROC_INFOGRAPHIC = True

if st.query_params.get("clear"):
    st.cache_data.clear()
    st.query_params.clear()
    st.rerun()

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
        transition: background-color 0.2s ease, transform 0.15s cubic-bezier(0.16, 1, 0.3, 1) !important;
        will-change: transform;
    }
    div.stButton > button:hover {
        background-color: var(--electric-hover) !important;
        box-shadow: none !important;
        transform: translateY(-1px) !important;
    }
    div.stButton > button:active {
        transform: scale(0.98) translateY(0px) !important;
        transition-duration: 0.05s !important;
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
        transition: background-color 0.2s ease, transform 0.15s cubic-bezier(0.16, 1, 0.3, 1) !important;
        will-change: transform;
    }
    div[data-testid="stDownloadButton"] > button:hover {
        background-color: #010f1e !important;
        box-shadow: none !important;
        transform: translateY(-1px) !important;
    }
    div[data-testid="stDownloadButton"] > button:active {
        transform: scale(0.98) translateY(0px) !important;
        transition-duration: 0.05s !important;
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

    /* 11. FILE UPLOADER — Drop Zone grande */
    [data-testid="stFileUploaderDropzone"] {
        min-height: 148px !important;
        padding: 0 !important;
        border: 2px dashed var(--electric-blue) !important;
        background-color: var(--electric-light) !important;
        position: relative !important;
        transition: background-color 0.2s ease, border-color 0.2s ease !important;
        cursor: pointer;
    }
    [data-testid="stFileUploaderDropzone"]:hover {
        background-color: rgba(0, 100, 151, 0.12) !important;
        border-color: var(--electric-hover) !important;
    }
    [data-testid="stFileUploaderDropzone"] div {
        padding: 0 !important;
        margin: 0 !important;
    }
    [data-testid="stFileUploaderDropzone"] button {
        visibility: hidden !important;
        position: absolute !important;
        inset: 0 !important;
        width: 100% !important;
        height: 100% !important;
        padding: 0 !important;
        margin: 0 !important;
        cursor: pointer !important;
        background: transparent !important;
        border: none !important;
    }
    [data-testid="stFileUploaderDropzone"] button::after {
        content: "Arrastra tu archivo aquí\A o haz clic para seleccionar";
        white-space: pre-line;
        visibility: visible !important;
        position: absolute !important;
        top: 50% !important;
        left: 50% !important;
        transform: translate(-50%, -50%) !important;
        color: var(--electric-blue) !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        letter-spacing: 0.03em !important;
        text-transform: none !important;
        text-align: center !important;
        line-height: 1.9 !important;
        width: auto !important;
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
    }
    [data-testid="stFileUploaderDropzone"] > div > div > span,
    [data-testid="stFileUploaderDropzone"] > div > div::before,
    [data-testid="stFileUploaderDropzone"] > div > div > small {
        display: none !important;
    }
    [data-testid="stFileUploaderDropzone"] svg {
        display: none !important;
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

    /* 15b. EXPANDER — acordeones de portafolio (detalle navegable) */
    [data-testid="stExpander"] {
        border: 1px solid #d8dde3 !important;
        border-radius: 0 !important;
        margin-bottom: 6px !important;
    }
    [data-testid="stExpander"] summary {
        font-family: 'Inter', sans-serif !important;
        font-size: 12px !important;
        font-weight: 700 !important;
        letter-spacing: 0.07em !important;
        color: #021C36 !important;
        padding: 10px 14px !important;
    }
    [data-testid="stExpander"] summary:hover {
        color: #006497 !important;
        background-color: #f6f3f2 !important;
    }

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
        padding: 10px 4px 10px 14px;
        background-color: transparent;
        margin: 26px 0 0 0;
        border-left: 3px solid #006497;
        border-bottom: 1px solid #e2e8f0;
    }
    .da-ticker-header .da-ticker-name {
        font-family: 'Inter', sans-serif;
        font-size: 18px;
        font-weight: 800;
        color: #0F172A;
        letter-spacing: -0.01em;
    }
    .da-ticker-header .da-mode-badge {
        font-family: 'Inter', sans-serif;
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        padding: 3px 8px;
        border-radius: 0px;
    }
    .da-ticker-header .da-mode-income  { background-color: #fdecea; color: #c8102e; }
    .da-ticker-header .da-mode-growth  { background-color: #e7f0f6; color: #006497; }
    .da-ticker-header .da-ticker-price {
        font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
        font-size: 12px;
        color: #64748B;
        margin-left: auto;
        letter-spacing: 0.02em;
    }

    /* 19. ROC CALLOUT */
    .da-roc-callout {
        background: #F8FAFC;
        border-left: 3px solid #16A34A;
        padding: 12px 18px;
        margin: 6px 0 16px 0;
    }
    .da-roc-callout .da-roc-callout-title {
        font-family: 'Inter', sans-serif;
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #16A34A;
        margin: 0 0 6px 0;
    }
    .da-roc-callout .da-roc-callout-values {
        display: flex;
        gap: 28px;
        align-items: baseline;
        flex-wrap: wrap;
    }
    .da-roc-callout .da-roc-number {
        font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
        font-size: 19px;
        font-weight: 700;
        color: #0F172A;
        letter-spacing: -0.01em;
    }
    .da-roc-callout .da-roc-sub {
        font-family: 'Inter', sans-serif;
        font-size: 10px;
        color: #64748B;
        letter-spacing: 0.04em;
    }
    .da-roc-callout .da-roc-explain {
        font-family: 'Inter', sans-serif;
        font-size: 10.5px;
        color: #334155;
        margin: 8px 0 0 0;
        line-height: 1.5;
    }

    /* 19b. KPI GRID EDITORIAL — detalle por activo */
    .da-tkpi {
        display: flex;
        border: 1px solid #e2e8f0;
        background: #ffffff;
        margin: 8px 0 14px 0;
    }
    .da-tkpi .da-tkpi-cell {
        flex: 1;
        padding: 13px 18px;
        border-right: 1px solid #e2e8f0;
    }
    .da-tkpi .da-tkpi-cell:last-child { border-right: none; }
    .da-tkpi-label {
        font-family: 'Inter', sans-serif;
        font-size: 10px;
        font-weight: 400;
        color: #64748B;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin: 0 0 6px 0;
    }
    .da-tkpi-value {
        font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
        font-size: 25px;
        font-weight: 700;
        color: #0F172A;
        letter-spacing: -0.01em;
        margin: 0 0 4px 0;
    }
    .da-tkpi-sub {
        font-family: 'Inter', sans-serif;
        font-size: 10px;
        color: #94a3b8;
        margin: 0;
    }
    @media (max-width: 640px) {
        .da-tkpi { flex-direction: column; }
        .da-tkpi .da-tkpi-cell { border-right: none; border-bottom: 1px solid #e2e8f0; }
        .da-tkpi .da-tkpi-cell:last-child { border-bottom: none; }
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
    .da-kpi-cell.da-kpi-navy   { border-top-color: #021C36; }
    .da-kpi-cell.da-kpi-roc    { border-top-color: #4caf82; background-color: #f0faf5; }
    .da-income-kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 2px;
        margin: 14px 0 10px 0;
    }
    .da-kpi-label {
        font-family: 'Inter', sans-serif;
        font-size: 9px;
        font-weight: 600;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #64748B;
        margin: 0 0 4px 0;
    }
    .da-kpi-value {
        font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
        font-size: 22px;
        font-weight: 700;
        color: #0F172A;
        letter-spacing: -0.01em;
        margin: 0;
    }
    .da-kpi-delta {
        font-family: 'Inter', sans-serif;
        font-size: 10px;
        font-weight: 600;
        margin: 3px 0 0 0;
    }

    /* 22b. KPI DOBLE FUENTE (Schwab vs Calculadora) + TOOLTIP */
    .da-kpi-dual {
        display: flex;
        gap: 20px;
        margin: 4px 0 2px 0;
    }
    .da-kpi-src {
        display: block;
        font-family: 'Inter', sans-serif;
        font-size: 9px;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #8899aa;
        margin: 0 0 1px 0;
    }
    .da-kpi-num {
        font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
        font-size: 19px;
        font-weight: 700;
        color: #0F172A;
        letter-spacing: -0.01em;
        line-height: 1.1;
    }
    .da-tip { position: relative; cursor: help; }
    .da-tip-i {
        display: inline-block;
        font-family: 'Inter', sans-serif;
        font-size: 9px;
        font-weight: 700;
        color: #ffffff;
        background: #94a3b8;
        width: 12px; height: 12px;
        line-height: 12px;
        text-align: center;
        margin-left: 5px;
        vertical-align: middle;
    }
    .da-tip-box {
        visibility: hidden;
        opacity: 0;
        position: absolute;
        z-index: 2000;
        bottom: 100%;
        left: 0;
        width: 300px;
        max-width: 90vw;
        max-height: 56vh;
        overflow-y: auto;
        background: #021C36;
        color: #d8e2ee;
        font-family: 'Inter', sans-serif;
        font-size: 11px;
        font-weight: 400;
        line-height: 1.55;
        letter-spacing: 0;
        text-transform: none;
        text-align: left;
        padding: 12px 14px;
        box-shadow: 0 8px 24px rgba(2, 28, 54, 0.28);
        transition: opacity 0.15s ease;
        pointer-events: auto;
    }
    .da-tip-box.r { left: auto; right: 0; }
    .da-tip-box b { color: #ffffff; font-weight: 700; }
    .da-tip:hover .da-tip-box { visibility: visible; opacity: 1; }
    /* El subhead de la cuadrícula C estila TODOS sus spans (8px, mayúsculas, gris);
       restauramos el ícono y la caja del tooltip cuando viven ahí dentro. */
    .da-kpiwide-subhead .da-tip-i {
        font-size: 9px; font-weight: 700; color: #ffffff;
        text-transform: none; text-align: center; letter-spacing: 0;
    }
    .da-kpiwide-subhead .da-tip-box {
        font-size: 11px; font-weight: 400; color: #d8e2ee;
        text-transform: none; text-align: left; letter-spacing: 0;
    }
    .da-kpiwide-subhead .da-tip-box b { color: #ffffff; font-weight: 700; }

    /* 22c. MINI-TABLA POR ETF dentro de cada tarjeta KPI */
    .da-mini { margin: 8px 0 2px 0; }
    .da-mini-row {
        display: grid;
        grid-template-columns: minmax(38px, 1fr) 1fr 1fr 0.85fr;
        gap: 8px;
        align-items: baseline;
        padding: 3px 0;
    }
    .da-mini-head span {
        font-family: 'Inter', sans-serif;
        font-size: 8px;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #8899aa;
    }
    .da-mini-row .tk, .da-kpiwide-row .tk, .da-roc-row .tk {
        font-family: 'Inter', sans-serif;
        font-size: 11px;
        font-weight: 700;
        color: #021C36;
        letter-spacing: 0.02em;
    }
    .da-mini-row .num, .da-kpiwide-row .num, .da-roc-row .num {
        font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
        font-size: 12px;
        font-weight: 700;
        color: #0F172A;
        text-align: right;
        letter-spacing: -0.01em;
    }
    .da-mini-row .pct, .da-kpiwide-row .pct {
        font-family: 'Inter', sans-serif;
        font-size: 11px;
        font-weight: 700;
        text-align: right;
    }
    .da-mini-head .num, .da-mini-head .pct { color: #8899aa; }
    .da-mini-total {
        border-top: 1px solid #d8d2cf;
        margin-top: 3px;
        padding-top: 5px;
    }
    .da-mini-total .tk { color: #021C36; }
    .da-mini-total .num { color: #021C36; font-size: 13px; }

    /* 22d. TABLA DE CRECIMIENTO — 6 columnas full-width */
    .da-growth-wrap { overflow-x: auto; margin: 8px 0 2px 0; }
    .da-growth-row {
        display: grid;
        grid-template-columns: minmax(46px, 1.2fr) repeat(4, 1fr);
        gap: 10px;
        align-items: baseline;
        padding: 4px 0;
        min-width: 460px;
    }
    .da-growth-row > span {
        font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
        font-size: 12px;
        font-weight: 700;
        color: #0F172A;
        text-align: right;
        letter-spacing: -0.01em;
    }
    .da-growth-row > span:first-child {
        font-family: 'Inter', sans-serif;
        text-align: left;
        color: #021C36;
        letter-spacing: 0.02em;
    }
    .da-growth-head > span {
        font-family: 'Inter', sans-serif;
        font-size: 8px;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #8899aa;
    }
    .da-growth-total {
        border-top: 1px solid #d8d2cf;
        margin-top: 3px;
        padding-top: 6px;
    }
    .da-growth-total > span { color: #021C36; font-size: 13px; }

    /* 22d-bis. CUADRÍCULAS «HOJA EXCEL» — método tradicional + vista honesta.
       Misma rejilla (display:grid) que la de crecimiento para que las columnas
       comunes coincidan en espacio entre ambas tablas. El grid-template-columns
       va inline por tabla (cuentan columnas distintas al expandir el drill-down). */
    /* Sin overflow en el wrap: los tooltips de encabezado se abren hacia arriba y
       no deben recortarse. El min-width vive en el div interno. */
    .da-he-wrap { margin: 6px 0 2px 0; }
    .da-he-grid { width: 100%; }
    .da-he-row {
        display: grid;
        gap: 10px;
        align-items: baseline;
        padding: 6px 0;
        border-bottom: 1px solid #eef1f4;
    }
    .da-he-row > span {
        font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
        font-size: 12px;
        font-weight: 700;
        color: #0F172A;
        text-align: right;
        letter-spacing: -0.01em;
    }
    .da-he-row > span.l {
        font-family: 'Inter', sans-serif;
        text-align: left;
        color: #021C36;
        letter-spacing: 0.02em;
    }
    .da-he-row > span.c { text-align: center; }
    .da-he-head { border-bottom: 2px solid #006497; }
    .da-he-head > span {
        font-family: 'Inter', sans-serif;
        font-size: 8px;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #8899aa;
    }
    .da-he-head > span.hl { text-align: left; }
    .da-he-head > span.c { text-align: center; }
    .da-he-head > span.da-tip { cursor: help; border-bottom: 1px dotted #b8c2cc; padding-bottom: 1px; }
    .da-he-head > span.da-tip:hover { border-bottom-color: #006497; color: #006497; }
    .da-he-total { border-top: 2px solid #006497; border-bottom: none; margin-top: 2px; padding-top: 7px; }
    .da-he-total > span { color: #021C36; font-size: 13px; }
    /* acentos semánticos preservados */
    .da-he-row > span.tk { font-family: 'Inter', sans-serif; font-weight: 800; color: #021C36; text-align: left; }
    .da-he-row > span.amber { color: #c9821f; }
    .da-he-row > span.naive { color: #c9821f; background: #fbf3e3; border-radius: 0; }
    .da-he-head > span.naive { color: #c9821f; background: #fbf3e3; }
    .da-he-row > span.nra { color: #cc6a6a; }
    .da-he-row > span.muted { color: #8aa0b2; }
    .da-he-row > span.pos { color: #1f8a5b; }
    .da-he-row > span.neg { color: #cf4b4b; }
    .da-he-badge {
        display: inline-block; padding: 2px 8px; font-weight: 700;
        font-size: 10px; letter-spacing: 0.04em; font-family: 'Inter', sans-serif;
    }

    /* 22e. TABLA KPI INGRESOS — consolidada (ETF una sola vez, 4 grupos a lo ancho)
       Cada grupo muestra solo el valor de la calculadora + Δ% vs Schwab (2 cols). */
    .da-kpiwide-row, .da-kpiwide-grouphead, .da-kpiwide-subhead {
        display: grid;
        grid-template-columns: minmax(48px, 1.1fr) repeat(8, 1fr);
        gap: 8px;
        align-items: baseline;
        padding: 3px 0;
    }
    .da-kpiwide-grouphead { padding: 2px 0 0 0; }
    .da-kpiwide-grouphead .grp {
        grid-column: span 2;
        font-family: 'Inter', sans-serif;
        font-size: 9px;
        font-weight: 600;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #64748B;
        border-bottom: 2px solid transparent;
        padding-bottom: 4px;
        margin: 0;
    }
    .da-kpiwide-subhead { padding-top: 2px; }
    .da-kpiwide-subhead span {
        font-family: 'Inter', sans-serif;
        font-size: 8px;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #8899aa;
        text-align: right;
    }
    .da-kpiwide-subhead span.lbl { text-align: left; }
    .da-kpiwide-total {
        border-top: 1px solid #d8d2cf;
        margin-top: 3px;
        padding-top: 6px;
    }
    .da-kpiwide-total .tk, .da-kpiwide-total .num { color: #021C36; }
    .da-kpiwide-total .num { font-size: 13px; }

    /* 22f. TABLA CONSOLIDADA — Total div + ROC + inversión + proyección por ETF (10 columnas) */
    .da-roc-row, .da-roc-subhead {
        display: grid;
        grid-template-columns: minmax(48px, 1.1fr) repeat(9, 1fr);
        gap: 8px;
        align-items: baseline;
        padding: 3px 0;
        min-width: 960px;
    }
    .da-roc-subhead span {
        font-family: 'Inter', sans-serif;
        font-size: 8px;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #8899aa;
        text-align: right;
    }
    .da-roc-subhead span.lbl { text-align: left; }
    .da-roc-total {
        border-top: 1px solid #d8d2cf;
        margin-top: 3px;
        padding-top: 6px;
    }
    .da-roc-total .tk, .da-roc-total .num { color: #021C36; }
    .da-roc-total .num { font-size: 13px; }

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

    /* 23b. TARJETAS "TUS DOS PORTAFOLIOS" */
    .da-port-cards {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 2px;
        margin: 16px 0 8px 0;
        align-items: stretch;
    }
    .da-port-card {
        background-color: #f6f3f2;
        padding: 18px 20px;
        border-top: 3px solid #006497;
    }
    .da-port-card.navy { border-top-color: #021C36; }
    .da-port-title {
        font-family: 'Inter', sans-serif;
        font-size: 12px;
        font-weight: 800;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #021C36;
        margin: 0 0 8px 0;
    }
    .da-port-chip {
        display: inline-block;
        font-family: 'Inter', sans-serif;
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 0.04em;
        color: #006497;
        background: #eef6fb;
        padding: 3px 8px;
        margin: 0 0 10px 0;
    }
    .da-port-card p.txt {
        font-family: 'Inter', sans-serif;
        font-size: 12px;
        color: #333333;
        line-height: 1.6;
        margin: 0 0 8px 0;
    }
    .da-port-mini {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 8px;
        margin: 12px 0 0 0;
        padding-top: 10px;
        border-top: 1px solid #e5e0de;
    }
    .da-port-mini .lbl {
        display: block;
        font-family: 'Inter', sans-serif;
        font-size: 8px;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #8899aa;
        margin: 0 0 2px 0;
    }
    .da-port-mini .val {
        display: block;
        font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
        font-size: 13px;
        font-weight: 700;
        color: #0F172A;
    }
    @media (max-width: 900px) {
        .da-port-cards { grid-template-columns: 1fr; }
        .da-port-mini { grid-template-columns: repeat(2, 1fr); }
    }

    /* 24. RESPONSIVE */
    @media (max-width: 768px) {
        .da-kpi-bar { grid-template-columns: repeat(2, 1fr); }
        .da-income-kpi-grid { grid-template-columns: repeat(2, 1fr); }
        .da-step-grid { grid-template-columns: 1fr; }
        .da-ticker-header { flex-direction: column; gap: 4px; }
    }
    @media (max-width: 480px) {
        .da-kpi-bar { grid-template-columns: 1fr; }
        .da-income-kpi-grid { grid-template-columns: 1fr; }
    }

    /* 25. ANIMACIONES DE ENTRADA — staggered fade-up */
    @keyframes da-fadein {
        from { opacity: 0; transform: translateY(10px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    .da-step-card {
        animation: da-fadein 0.35s cubic-bezier(0.16, 1, 0.3, 1) both;
    }
    .da-step-card:nth-child(1) { animation-delay: 0s; }
    .da-step-card:nth-child(2) { animation-delay: 0.08s; }
    .da-step-card:nth-child(3) { animation-delay: 0.16s; }
    .da-kpi-cell {
        animation: da-fadein 0.3s cubic-bezier(0.16, 1, 0.3, 1) both;
    }
    .da-kpi-cell:nth-child(1) { animation-delay: 0s; }
    .da-kpi-cell:nth-child(2) { animation-delay: 0.06s; }
    .da-kpi-cell:nth-child(3) { animation-delay: 0.12s; }
    .da-kpi-cell:nth-child(4) { animation-delay: 0.18s; }
    .da-kpi-cell:nth-child(5) { animation-delay: 0.24s; }
    .da-ticker-header {
        animation: da-fadein 0.3s cubic-bezier(0.16, 1, 0.3, 1) both;
    }
    .da-cache-btn button {
        all: unset !important;
        font-size: 10px !important;
        color: #c0c0c0 !important;
        cursor: pointer !important;
        letter-spacing: 0.06em !important;
        font-family: inherit !important;
        padding: 0 !important;
        margin: 0 !important;
        background: none !important;
        border: none !important;
        box-shadow: none !important;
        text-transform: lowercase !important;
    }
    .da-cache-btn button:hover {
        color: #888888 !important;
    }
</style>
""", unsafe_allow_html=True)


st.markdown("""
<div style="padding: 40px 0 28px 0; background-color: #fcf9f8;">
    <h1 style="
        font-family: 'Cinzel', serif;
        font-size: 2.8rem;
        font-weight: 700;
        letter-spacing: 0.02em;
        color: #1a1a1a;
        margin: 0;
        line-height: 1.1;
    ">
        CALCULADORA <span style="color:#006497;">//</span> DIVIDENDOS
        <span style="font-size:0.9rem;font-weight:400;letter-spacing:0.12em;color:#8899aa;margin-left:12px;vertical-align:middle;">v3.0</span>
    </h1>
</div>
""", unsafe_allow_html=True)

# (Las "Calculadoras de referencia" se movieron al pie de la página, arriba del disclaimer.)




# --- Paleta Python para Altair (Altair no interpreta CSS vars) ---
CHART_PALETTE = {
    "portfolio": "#006497",        # Electric Blue
    "sp500":     "#8a8a8a",        # Gris neutro referencia
    "axis":      "#64748B",        # ejes (gris editorial)
    "grid":      "#e8edf2",        # grid tenue editorial
    "bg":        "#fcf9f8",        # surface
    "title":     "#475569",        # títulos de eje
}

# ── Tokens editoriales (design-system unificado) ──────────────────────
_MONO_FONT = "'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace"
_INK      = "#0F172A"   # tinta de valores numéricos
_LABEL    = "#64748B"   # labels / ejes
_HAIRLINE = "#e2e8f0"   # divisores
_SURFACE  = "#F8FAFC"   # superficie tenue
_POS      = "#16A34A"   # verde positivo
_NEG      = "#DC2626"   # rojo negativo


def _ed_axis(kind="x", fmt=None, title=None, label_angle=None, year_ticks=False, tick_count=None):
    """Eje Altair editorial: label mono gris, sin dominio/ticks; grid horizontal punteado tenue solo en Y."""
    import altair as alt
    grid = (kind == "y")
    kw = dict(
        labelFont=_MONO_FONT, labelFontSize=10, labelColor=_LABEL,
        titleFont="Inter, system-ui, sans-serif", titleFontSize=11, titleColor=_LABEL,
        title=title, grid=grid, domain=False, ticks=False,
    )
    if grid:
        kw.update(gridColor=_HAIRLINE, gridDash=[3, 3], gridOpacity=0.7, tickCount=tick_count or 5)
    if fmt:
        kw["format"] = fmt
    if label_angle is not None:
        kw["labelAngle"] = label_angle
    if year_ticks:
        kw["tickCount"] = {"interval": "year", "step": 1}
    return alt.Axis(**kw)

# Wizard session state defaults
for _wk, _wv in [('_wizard_step', 1), ('_wizard_ib_map', {}), ('_wizard_csv_ticker_data', {}), ('_wizard_df_clean', None), ('_wizard_broker', None), ('_wizard_positions', {}), ('_wizard_overrides', {}), ('_wizard_photo_sig', None), ('_wizard_income_summary', None), ('_wizard_income_df', None), ('_prev_step', 1), ('_wizard_csv_name', None), ('_wizard_pos_confirmed', False), ('_prev_active_pill', 1)]:
    if _wk not in st.session_state:
        st.session_state[_wk] = _wv

_already_loaded = (st.session_state.get('_wizard_df_clean') is not None
                   or st.session_state.get('_wizard_step', 1) >= 3)
_col_mode, _col_cache = st.columns([6, 1])
with _col_mode:
    if _already_loaded:
        # Ya se subió el archivo: ocultar el selector CSV/Excel · Simulación Teórica.
        input_method = "Subir CSV/Excel"
    else:
        input_method = st.radio("Modo de Análisis:", ["Subir CSV/Excel", "Simulación Teórica"], horizontal=True, label_visibility="collapsed")
with _col_cache:
    st.markdown(
        '<a href="?clear=1" target="_self" style="'
        'font-size:10px;color:#c0c0c0;text-decoration:none;'
        'letter-spacing:0.05em;font-family:inherit;'
        'display:block;text-align:right;padding-top:6px;'
        '">limpiar caché</a>',
        unsafe_allow_html=True
    )


def _render_step_indicator(current_step, prev_step=None):
    _cur = current_step / 3 * 100
    _fill = f"width:{_cur}%;background:#006497;height:100%;"
    _kf = ""
    if prev_step and prev_step != current_step:
        _name = f"da-prog{prev_step}{current_step}"
        _kf = f"@keyframes {_name}{{from{{width:{prev_step / 3 * 100}%}}to{{width:{_cur}%}}}}"
        _fill += f"animation:{_name} .5s cubic-bezier(.16,1,.3,1) both;"
    st.markdown(
        f"<style>{_kf}@media (prefers-reduced-motion:reduce){{[data-da-prog]>div{{animation:none}}}}</style>"
        f"<div data-da-prog style='height:3px;background:#eae7e7;margin:0 0 14px 0;'>"
        f"<div style='{_fill}'></div></div>",
        unsafe_allow_html=True
    )
    steps = [("01", "Carga el Archivo"), ("02", "Configura Costos"), ("03", "Resultados")]
    pills = []
    for i, (num, label) in enumerate(steps, 1):
        if i == current_step:
            bg, fg = "#006497", "#ffffff"
        elif i < current_step:
            bg, fg = "#021C36", "#ffffff"
        else:
            bg, fg = "#eae7e7", "#8899aa"
        pills.append(
            f'<div style="background:{bg};padding:8px 18px;display:flex;align-items:center;">'
            f'<span style="font-family:Inter,sans-serif;font-size:9px;font-weight:700;'
            f'letter-spacing:0.12em;text-transform:uppercase;color:{fg};">{num} · {label}</span>'
            f'</div>'
        )
    sep = '<div style="width:14px;height:2px;background:#eae7e7;align-self:center;flex-shrink:0;"></div>'
    st.markdown(
        '<div style="display:flex;align-items:center;gap:0;margin-bottom:32px;">'
        + sep.join(pills) + '</div>',
        unsafe_allow_html=True
    )


def _get_gemini_key():
    try:
        _k = st.secrets.get("GEMINI_API_KEY")
        if _k:
            return _k
    except Exception:
        pass
    return os.getenv("GEMINI_API_KEY")

# --- Helpers de la carga consolidada (Paso 01) ---
_PARSEO_STYLE = (
    '<style>.da-ind{position:relative;height:3px;background:#e8eef3;overflow:hidden;}'
    '.da-ind::after{content:"";position:absolute;left:0;top:0;height:100%;width:35%;'
    'background:#006497;animation:da-ind 1s ease-in-out infinite;}'
    '@keyframes da-ind{0%{left:-35%}100%{left:100%}}'
    '@media (prefers-reduced-motion:reduce){.da-ind::after{animation:none;left:0;width:100%}}</style>'
)


def _parseo(messages, step=0.6):
    """Micro-animación de 'parseo': barra indeterminada + texto rotativo (~1-2s)."""
    _ph = st.empty()
    for _m in messages:
        _ph.markdown(
            _PARSEO_STYLE +
            '<div style="padding:8px 0 4px 0;">'
            f'<div style="font-family:Inter,sans-serif;font-size:12.5px;color:#5a6b7a;'
            f'font-style:italic;margin-bottom:7px;">{_m}</div>'
            '<div class="da-ind"></div></div>',
            unsafe_allow_html=True)
        time.sleep(step)
    _ph.empty()


def _da_block_header(num, title, state, subtitle=""):
    """Encabezado numerado de un bloque. state: 'active' | 'done' | 'locked'."""
    if state == 'done':
        _bg, _fg, _mark, _tc = '#4caf82', '#ffffff', '✓', '#1a1a1a'
    elif state == 'locked':
        _bg, _fg, _mark, _tc = '#eae7e7', '#b9c2cc', str(num), '#aab4be'
    else:
        _bg, _fg, _mark, _tc = '#006497', '#ffffff', str(num), '#021C36'
    _sub = (f'<div style="font-family:Inter,sans-serif;font-size:11px;color:#8a96a3;'
            f'margin-top:1px;">{subtitle}</div>') if subtitle else ''
    return (
        '<div class="da-reveal" style="display:flex;align-items:center;gap:11px;margin:2px 0 10px 0;">'
        f'<div style="flex-shrink:0;width:26px;height:26px;background:{_bg};color:{_fg};'
        'display:flex;align-items:center;justify-content:center;font-family:Inter,sans-serif;'
        f'font-size:12px;font-weight:800;">{_mark}</div>'
        '<div>'
        f'<div style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;letter-spacing:0.02em;'
        f'color:{_tc};text-transform:uppercase;">{title}</div>{_sub}</div></div>'
    )


def _da_summary(title, detail):
    """Resumen contraído de un bloque completado."""
    return (
        '<div class="da-reveal" style="display:flex;align-items:center;gap:11px;'
        'background:#f7faf8;border-left:4px solid #4caf82;padding:10px 14px;margin:2px 0 4px 0;">'
        '<div style="flex-shrink:0;width:22px;height:22px;background:#4caf82;color:#fff;'
        'display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:800;">✓</div>'
        '<div style="line-height:1.35;">'
        f'<span style="font-family:Inter,sans-serif;font-size:12px;font-weight:800;color:#1a1a1a;'
        f'text-transform:uppercase;letter-spacing:0.04em;">{title}</span>'
        f'<span style="font-family:Inter,sans-serif;font-size:12px;color:#5a6b7a;"> · {detail}</span>'
        '</div></div>'
    )


def _da_block3_locked():
    """Placeholder atenuado del Bloque 3 (visible desde el inicio, desactivado)."""
    return (
        '<div class="da-reveal" style="opacity:.55;border:1px dashed #d8dde2;padding:12px 14px;margin:4px 0;">'
        + _da_block_header(
            3, "Archivo de ingresos · opcional", "locked",
            "Validación extra · se desbloquea al confirmar tus posiciones.")
        + '</div>'
    )


_LOAD_PROGRESS_STYLE = (
    '<style>'
    '.da-reveal{animation:da-rev .42s cubic-bezier(.16,1,.3,1) both;}'
    '@keyframes da-rev{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}'
    '.da-seg-fill{animation:da-fill .55s cubic-bezier(.16,1,.3,1) both;transform-origin:left center;}'
    '@keyframes da-fill{from{transform:scaleX(0)}to{transform:scaleX(1)}}'
    '@media (prefers-reduced-motion:reduce){.da-reveal,.da-seg-fill{animation:none}}'
    '</style>'
)


def _inject_reveal_style():
    """Inyecta el CSS de animación de revelación progresiva (da-reveal / da-seg-fill)."""
    st.markdown(_LOAD_PROGRESS_STYLE, unsafe_allow_html=True)


# --- Main Logic ---

if input_method == "Subir CSV/Excel":
    _wizard_step = st.session_state.get('_wizard_step', 1)

    # Estado de los micro-pasos de la carga consolidada (Paso 01)
    _csv_done    = st.session_state.get('_wizard_df_clean') is not None
    _pos_done    = bool(st.session_state.get('_wizard_pos_confirmed'))
    _income_done = st.session_state.get('_wizard_income_summary') is not None

    # Píldora activa: dentro del Paso 01, la 02 ("Configura Costos") se ilumina
    # al entrar a la fase de Posiciones (CSV ya cargado); 03 en Resultados.
    if _wizard_step >= 3:
        _active_pill = 3
    elif _csv_done:
        _active_pill = 2
    else:
        _active_pill = 1
    _prev_pill = st.session_state.get('_prev_active_pill', _active_pill)

    _step_changed = st.session_state.get('_prev_step') != _wizard_step
    if _step_changed:
        # Anima la entrada del contenido SOLO al cambiar de paso mayor (1 ↔ 3)
        st.markdown(
            '<style>.block-container{animation:da-step-in .45s cubic-bezier(.16,1,.3,1) both;}'
            '@keyframes da-step-in{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}'
            '@media (prefers-reduced-motion:reduce){.block-container{animation:none}}</style>',
            unsafe_allow_html=True)

    # Stepper de píldoras (01·02·03) eliminado: se deja solo la barra "Progreso de carga".
    if _prev_pill != _active_pill:
        _ptoast = {2: "Configura tus costos", 3: "Paso 3 de 3 · Resultados"}
        if _active_pill in _ptoast:
            st.toast(_ptoast[_active_pill], icon=":material/check_circle:")
    st.session_state['_prev_active_pill'] = _active_pill
    st.session_state['_prev_step'] = _wizard_step

    # ══════════════════════════════════════════════════════════════════
    #  PASO 01 · CARGA EL ARCHIVO — vista única, revelación progresiva
    # ══════════════════════════════════════════════════════════════════
    if _wizard_step == 1:
        _inject_reveal_style()

        # ───────── BLOQUE 1 · Transacciones (CSV / Excel) ─────────
        if not _csv_done:
            st.markdown(_da_block_header(
                1, "Transacciones · CSV / Excel", "active",
                "Sube el export de tu broker para comenzar."), unsafe_allow_html=True)
            uploaded_file_w = st.file_uploader(
                "Sube tu archivo de transacciones (CSV o Excel)",
                type=['csv', 'xlsx'],
                label_visibility="collapsed",
                help="Interactive Brokers: Informes → Extractos → Transaction History  |  Charles Schwab: Historial → Transacciones → Exportar"
            )
            if uploaded_file_w is not None:
                try:
                    _parseo(["Leyendo el archivo…", "Detectando broker y analizando columnas…"])
                    if uploaded_file_w.name.endswith('.xlsx'):
                        _df_w = pd.read_excel(uploaded_file_w)
                        _broker_w = 'generic'
                    else:
                        _df_w, _broker_w = logic.load_and_detect_csv(uploaded_file_w)
                        if _df_w.empty:
                            st.error("No pudimos leer el formato del CSV. Intenta guardarlo como 'CSV UTF-8' o usa Excel (.xlsx).")
                            st.stop()

                    _df_clean_w = logic.normalize_csv(_df_w)
                    _req_cols_w = ['Date', 'Ticker', 'Amount']
                    _miss_cols_w = [c for c in _req_cols_w if c not in _df_clean_w.columns]

                    if _miss_cols_w:
                        st.error(f"Error de Formato: No encontramos las columnas: {', '.join(_miss_cols_w)}")
                        st.warning(f"Columnas encontradas: {list(_df_clean_w.columns)}")
                        st.info("Consejo: Asegúrate de que tu autodetector de cabecera funcionó. Si tu archivo tiene muchas filas vacías al inicio, intenta borrarlas.")
                    else:
                        _csv_td_w = {}
                        if 'Ticker' in _df_clean_w.columns and 'Action' in _df_clean_w.columns:
                            for _et_w, _eg_w in _df_clean_w.groupby('Ticker'):
                                _buys_w = _eg_w[_eg_w['Action'].str.lower().str.contains('buy', na=False)]
                                _divs_w = _eg_w[_eg_w['Action'].str.lower().str.contains('div', na=False)]
                                _csv_td_w[_et_w] = {
                                    'shares': float(_buys_w['Quantity'].sum()) if 'Quantity' in _buys_w.columns and not _buys_w.empty else 0.0,
                                    'invested': abs(float(_buys_w['Amount'].sum())) if not _buys_w.empty else 0.0,
                                    'dividends_csv': float(_divs_w['Amount'].sum()) if not _divs_w.empty else 0.0,
                                    'first_date': str(_eg_w['Date'].min())[:10] if not _eg_w.empty else 'N/A',
                                }
                        st.session_state['_wizard_df_clean'] = _df_clean_w
                        st.session_state['_wizard_csv_ticker_data'] = _csv_td_w
                        st.session_state['_wizard_broker'] = _broker_w
                        st.session_state['_wizard_csv_name'] = uploaded_file_w.name
                        st.rerun()

                except Exception as _e1:
                    import traceback as _tb1
                    st.error(f"Error procesando el archivo: {_e1}")
                    with st.expander("Ver detalles del error"):
                        st.code(_tb1.format_exc())
        else:
            # Bloque 1 contraído (modo resumen) + enlace para editar
            _bln = {'schwab': 'Charles Schwab', 'ibkr': 'Interactive Brokers', 'generic': 'Formato Genérico'}.get(
                st.session_state.get('_wizard_broker'), 'Archivo')
            _csvname = st.session_state.get('_wizard_csv_name') or 'transacciones.csv'
            _csvtd = st.session_state.get('_wizard_csv_ticker_data') or {}
            st.markdown(_da_summary("CSV cargado", f"{_csvname} · {_bln} · {len(_csvtd)} tickers"),
                        unsafe_allow_html=True)
            _ec1, _ec2 = st.columns([5, 1])
            with _ec2:
                if st.button("editar", key="_edit_csv", type="tertiary", use_container_width=True):
                    for _k in ['_wizard_df_clean', '_wizard_csv_ticker_data', '_wizard_broker',
                               '_wizard_csv_name', '_wizard_ib_map', '_wizard_positions',
                               '_wizard_overrides', '_wizard_photo_sig',
                               '_wizard_income_summary', '_wizard_income_df']:
                        st.session_state.pop(_k, None)
                    st.session_state['_wizard_pos_confirmed'] = False
                    st.rerun()

        # Bloque 3 visible (atenuado) desde el inicio, aun antes de cargar el CSV
        if not _csv_done:
            st.markdown(_da_block3_locked(), unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════
    #  Bloques 2 y 3 + acción SIGUIENTE — se revelan tras cargar el CSV
    # ══════════════════════════════════════════════════════════════════
    if _wizard_step == 1 and _csv_done:
        _df2 = st.session_state.get('_wizard_df_clean')
        _tickers_s2 = _df2['Ticker'].dropna().unique().tolist()
        _mmap_s2 = logic.classify_tickers(_tickers_s2)
        _pos_tickers = sorted([t for t, m in _mmap_s2.items() if m in ('mode_a', 'mode_b')])
        _gem_key = _get_gemini_key()
        _positions = st.session_state.get('_wizard_positions', {})
        _broker_s2 = st.session_state.get('_wizard_broker')

        # ───────── BLOQUE 2 · Posiciones del portafolio ─────────
        if not _pos_done:
            st.markdown(_da_block_header(
                2, "Posiciones del portafolio", "active",
                "Confirma acciones y costo real de cada ETF."), unsafe_allow_html=True)

            if _pos_tickers and _gem_key:
                _imgs_s2 = st.file_uploader(
                    "Fotos del portafolio",
                    type=['png', 'jpg', 'jpeg'],
                    accept_multiple_files=True,
                    label_visibility="collapsed",
                    key="_step2_photos",
                    help="Sube una o más fotos de tu portafolio (donde se vean 'Acciones/Posición' y "
                         "'Base de coste / Cost Basis') y rellenamos la tabla por ti."
                )
                st.caption("Formatos aceptados: PNG · JPG")
                if _imgs_s2:
                    _sig = tuple((f.name, f.size) for f in _imgs_s2)
                    if _sig != st.session_state.get('_wizard_photo_sig'):
                        _parseo(["Leyendo tus capturas…", "Cruzando posiciones y costos…"])
                        with st.spinner("Leyendo tu portafolio…"):
                            _imgs_payload = [(f.getvalue(), (f.type or 'image/jpeg')) for f in _imgs_s2]
                            _positions = logic.extract_positions_from_images(_imgs_payload, _pos_tickers, _gem_key)
                        st.session_state['_wizard_positions'] = _positions
                        st.session_state['_wizard_photo_sig'] = _sig
                    else:
                        _positions = st.session_state.get('_wizard_positions', {})
                    if _positions:
                        st.markdown(
                            f'<div style="border-left:4px solid #4caf82;background:#f0faf5;padding:10px 14px;margin:8px 0;">'
                            f'<span style="font-family:Inter,sans-serif;font-size:12px;font-weight:600;color:#1a1a1a;">'
                            f'Leídos {len(_positions)} de {len(_pos_tickers)} tickers. Revisa acciones y costo abajo antes de continuar.'
                            f'</span></div>',
                            unsafe_allow_html=True
                        )
                    else:
                        st.warning("No pudimos leer valores de las fotos (el servicio puede estar ocupado, o la imagen no muestra las columnas). Intenta de nuevo en unos segundos o escribe los valores abajo.")
                elif not st.session_state.get('_wizard_manual_entry'):
                    if st.button("Prefiero escribir los valores manualmente", key="_manual_entry_btn"):
                        st.session_state['_wizard_manual_entry'] = True
                        st.rerun()
            elif _pos_tickers:
                st.markdown(
                    '<p style="font-family:Inter,sans-serif;font-size:13px;color:#445566;line-height:1.7;margin:0 0 8px 0;">'
                    'Confirma las <b>acciones</b> y el <b>costo de inversión</b> de cada posición tal como aparecen en tu broker. '
                    'Es clave si tu broker solo exporta los últimos años (las acciones viejas no están en el CSV). Deja en 0 lo que no aplique.'
                    '</p>',
                    unsafe_allow_html=True
                )

            _show_pos_table = bool(_pos_tickers) and (
                not _gem_key
                or bool(st.session_state.get('_wizard_photo_sig'))
                or bool(st.session_state.get('_wizard_manual_entry'))
            )
            if _show_pos_table:
                _sig_now = st.session_state.get('_wizard_photo_sig')
                _editor_key = f"_step2_table_{abs(hash(_sig_now)) if _sig_now else 0}"
                _tbl_s2 = pd.DataFrame({
                    'Ticker': _pos_tickers,
                    'Acciones': [float((_positions.get(t) or {}).get('shares') or 0.0) for t in _pos_tickers],
                    'Costo de Inversión ($)': [float((_positions.get(t) or {}).get('cost_basis') or 0.0) for t in _pos_tickers],
                })
                _edited_s2 = st.data_editor(
                    _tbl_s2,
                    column_config={
                        'Ticker': st.column_config.TextColumn(disabled=True),
                        'Acciones': st.column_config.NumberColumn(
                            help="Acciones que tienes hoy según tu broker ('Posición' en IB, 'Qty' en Schwab). Si difiere del CSV, usamos este valor.",
                            min_value=0.0, format="%.4f"),
                        'Costo de Inversión ($)': st.column_config.NumberColumn(
                            help="'Base de coste' (IB) o 'Cost Basis' (Schwab): costo total de la posición. Deja en 0 si no aplica.",
                            min_value=0.0, format="%.2f"),
                    },
                    hide_index=True,
                    use_container_width=True,
                    num_rows="fixed",
                    key=_editor_key
                )
                _cc1, _cc2 = st.columns([3, 1])
                with _cc2:
                    if st.button("Confirmar posiciones →", type="primary", use_container_width=True, key="_confirm_pos"):
                        _ib_map_s2 = {}
                        _overrides_s2 = {}
                        for _, _row in _edited_s2.iterrows():
                            _t = _row['Ticker']
                            _co = float(_row.get('Costo de Inversión ($)') or 0)
                            _sh = float(_row.get('Acciones') or 0)
                            if _co > 0:
                                _ib_map_s2[_t] = str(_co)
                            if _co > 0 or _sh > 0:
                                _overrides_s2[_t] = {'cost_basis': _co or None, 'shares': _sh or None}
                        st.session_state['_wizard_ib_map'] = _ib_map_s2
                        st.session_state['_wizard_overrides'] = _overrides_s2
                        st.session_state['_wizard_pos_confirmed'] = True
                        st.rerun()
            else:
                st.info("No se detectaron posiciones de ETF analizables en este archivo. Puedes continuar al análisis directamente.")
                _nc1, _nc2 = st.columns([3, 1])
                with _nc2:
                    if st.button("Continuar →", type="primary", use_container_width=True, key="_confirm_nopos"):
                        st.session_state['_wizard_ib_map'] = {}
                        st.session_state['_wizard_overrides'] = {}
                        st.session_state['_wizard_pos_confirmed'] = True
                        st.rerun()
        else:
            # Bloque 2 contraído (modo resumen) + enlace para editar
            _ov = st.session_state.get('_wizard_overrides', {}) or {}
            _ncnt = len([t for t, v in _ov.items() if (v.get('shares') or v.get('cost_basis'))])
            _possum = f"{_ncnt} posiciones confirmadas" if _ncnt else "Sin posiciones para confirmar"
            st.markdown(_da_summary("Posiciones", _possum), unsafe_allow_html=True)
            _pc1, _pc2 = st.columns([5, 1])
            with _pc2:
                if st.button("editar", key="_edit_pos", type="tertiary", use_container_width=True):
                    st.session_state['_wizard_pos_confirmed'] = False
                    st.rerun()

        # ───────── BLOQUE 3 · Archivo de ingresos (opcional) ─────────
        if _income_done:
            _inc_sum = st.session_state.get('_wizard_income_summary') or {}
            _nrec = sum(1 for d in (_inc_sum.get('tickers') or {}).values() if d.get('received_total'))
            st.markdown(_da_summary("Ingresos validados", f"{_nrec} tickers con dividendos recibidos"),
                        unsafe_allow_html=True)
            if st.session_state.get('_wizard_income_multi'):
                st.caption("⚠️ El archivo incluye más de una cuenta; los totales podrían mezclarse. "
                           "Para una validación exacta, exporta el income de una sola cuenta.")
            _icc1, _icc2 = st.columns([5, 1])
            with _icc2:
                if st.button("editar", key="_edit_inc", type="tertiary", use_container_width=True):
                    st.session_state.pop('_wizard_income_summary', None)
                    st.session_state.pop('_wizard_income_df', None)
                    st.rerun()
        elif _pos_done:
            st.markdown(_da_block_header(
                3, "Archivo de ingresos · opcional", "active",
                "Validación extra: confirma los dividendos recibidos."), unsafe_allow_html=True)
            _inc_file = st.file_uploader(
                "Archivo de ingresos (Investment Income)",
                type=['csv', 'xlsx'], key="_step2_income", label_visibility="collapsed"
            )
            if _inc_file is not None:
                try:
                    _parseo(["Leyendo ingresos…", "Conciliando dividendos recibidos…"])
                    _inc_df = logic.parse_schwab_income_csv(_inc_file.getvalue())
                    if _inc_df is None:
                        st.session_state['_wizard_income_summary'] = None
                        st.session_state['_wizard_income_df'] = None
                        st.error(
                            "No reconocimos este archivo como un **Investment Income** de Charles Schwab.")
                        st.caption(
                            "Verifica que sea el reporte de **ingresos** (Cuenta → Historial → "
                            "*Investment Income* → Exportar) en formato **CSV** — no el de transacciones, "
                            "ni un Excel (.xls/.xlsx), ni un PDF.")
                    elif len(_inc_df) == 0:
                        st.session_state['_wizard_income_summary'] = None
                        st.session_state['_wizard_income_df'] = None
                        st.error("Leímos el archivo, pero no quedó ninguna fila de dividendos por ticker.")
                        st.caption(
                            "Puede que solo tuviera interés de cash o filas con montos/fechas vacíos. "
                            "Revisa que el export incluya las distribuciones de tus ETFs.")
                    else:
                        _inc_summ = logic.summarize_income(_inc_df)
                        _nrec_chk = sum(1 for d in (_inc_summ.get('tickers') or {}).values()
                                        if d.get('received_total'))
                        if _nrec_chk == 0:
                            # Parseó bien pero solo trae proyecciones "Estimated", sin "Received".
                            st.session_state['_wizard_income_summary'] = None
                            st.session_state['_wizard_income_df'] = None
                            st.error("Tu archivo solo trae proyecciones **“Estimated”**, no pagos **“Received”**.")
                            st.caption(
                                "Para validar necesitamos el histórico de ingresos **recibidos**. En Schwab, "
                                "amplía el rango de fechas hacia el pasado al exportar (la proyección futura "
                                "viene primero y se ignora).")
                        else:
                            st.session_state['_wizard_income_summary'] = _inc_summ
                            st.session_state['_wizard_income_df'] = _inc_df
                            st.session_state['_wizard_income_multi'] = bool(_inc_summ.get('multi_account'))
                            st.rerun()
                except Exception as _ie:
                    st.session_state['_wizard_income_summary'] = None
                    st.session_state['_wizard_income_df'] = None
                    st.error("No pudimos leer el archivo de ingresos.")
                    st.caption(f"Detalle técnico: {_ie}")
        else:
            # Visible desde el inicio pero desactivado (se activa tras Posiciones)
            st.markdown(_da_block3_locked(), unsafe_allow_html=True)

        # ───────── Consentimiento de captura anónima ─────────
        if storage.is_enabled():
            st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
            st.checkbox(
                "Permito guardar una versión anónima de estos datos para mejorar la herramienta.",
                value=False, key="_consent_capture")
            st.caption("Solo se guardan fechas, tickers, montos y las posiciones que confirmaste — nunca tu nombre, número de cuenta ni imágenes. Puedes pedir el borrado en cualquier momento. Ver PRIVACY.md.")

        # ───────── Resumen "Carga Completa" al 100% ─────────
        if _income_done:
            st.markdown(
                '<div class="da-reveal" style="border-left:4px solid #4caf82;background:#f0faf5;padding:14px 18px;margin:14px 0 4px 0;">'
                '<div style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;color:#021C36;'
                'text-transform:uppercase;letter-spacing:0.04em;">✓ Carga completa</div>'
                '<div style="font-family:Inter,sans-serif;font-size:12px;color:#5a6b7a;margin-top:3px;">'
                'Validaste por triple vía: transacciones, posiciones e ingresos. Listo para analizar.</div>'
                '</div>',
                unsafe_allow_html=True
            )

        # ───────── Acción principal: SIGUIENTE → (habilitada a ≥66%) ─────────
        st.markdown("<div style='height:10px;border-top:1px solid #eae7e7;margin-top:18px;'></div>", unsafe_allow_html=True)
        _nx1, _nx2 = st.columns([3, 1])
        with _nx1:
            if not _pos_done:
                st.caption("Confirma tus posiciones (66%) para habilitar el análisis. Los ingresos son opcionales.")
        with _nx2:
            if st.button("SIGUIENTE →", use_container_width=True, type="primary",
                         disabled=not _pos_done, key="_go_results"):
                _ib_map_s2 = st.session_state.get('_wizard_ib_map', {}) or {}
                _overrides_s2 = st.session_state.get('_wizard_overrides', {}) or {}
                with st.status("Analizando tu portafolio…", expanded=True) as _an_st:
                    st.write("Leyendo transacciones y ajustando splits…")
                    try:
                        _res_s2 = logic.analyze_portfolio(
                            _df2, version="2.0",
                            ib_cost_basis_map=_ib_map_s2 or None,
                            position_overrides=_overrides_s2 or None)
                    except TypeError:
                        _res_s2 = logic.analyze_portfolio(_df2)
                    st.write("Calculando dividendos, ROI y métricas de riesgo…")
                    _an_st.update(label="Análisis completo", state="complete", expanded=False)

                if not _res_s2:
                    st.error("No se pudieron extraer tickers válidos o datos del archivo.")
                else:
                    _skip_s2  = {t: s for t, s in _res_s2.items() if s.get("skipped")}
                    _valid_s2 = {t: s for t, s in _res_s2.items() if not s.get("skipped")}
                    _cmap_s2  = logic.classify_tickers(list(_valid_s2.keys()))
                    if not _valid_s2:
                        st.warning("Todos los tickers del archivo fueron descartados.")
                    else:
                        st.session_state['_results']      = _valid_s2
                        st.session_state['_classify_map'] = _cmap_s2
                        st.session_state['_skipped']      = _skip_s2
                        _buy_rows_s2 = []
                        for _tk, _ts in _valid_s2.items():
                            _h = _ts.get('history')
                            if _h is not None and not _h.empty:
                                for _, _r in _h[_h['Action'].str.lower().str.contains('buy|compra', na=False)].iterrows():
                                    _a = abs(float(_r.get('Amount', 0)))
                                    if _a > 0:
                                        _buy_rows_s2.append([str(_r['Date'].date()), _a])
                        if _buy_rows_s2:
                            with st.spinner("Calculando comparativa VTI · YMAX · SPY..."):
                                try:
                                    st.session_state['_strat_results'] = logic.simulate_triple_comparison(json.dumps(_buy_rows_s2))
                                except Exception:
                                    st.session_state['_strat_results'] = None
                        else:
                            st.session_state['_strat_results'] = None
                        if st.session_state.get('_consent_capture'):
                            try:
                                _q_cap = logic.assess_data_quality(_valid_s2)
                                _ok_cap, _ = logic.is_capture_worthy(_q_cap, _overrides_s2)
                                if _ok_cap:
                                    _bundle_cap = logic.build_capture_bundle(
                                        _df2, st.session_state.get('_wizard_broker', 'generic'),
                                        _overrides_s2, _q_cap,
                                        st.session_state.get('_wizard_positions', {}),
                                        app_version="2.8")
                                    storage.upload_case(_bundle_cap)
                            except Exception:
                                pass
                        st.session_state['_wizard_step'] = 3
                        st.rerun()

    # ── PASO 3: Resultados — botón de navegación al tope ─────────────────
    elif _wizard_step == 3:
        if st.button("← Nueva Consulta"):
            for _k in ['_wizard_step', '_wizard_df_clean', '_wizard_ib_map', '_wizard_csv_ticker_data',
                       '_wizard_broker', '_wizard_csv_name', '_wizard_pos_confirmed', '_prev_active_pill',
                       '_wizard_positions', '_wizard_overrides', '_wizard_photo_sig',
                       '_wizard_income_summary', '_wizard_income_df',
                       '_results', '_classify_map', '_skipped', '_strat_results', '_file_id']:
                st.session_state.pop(_k, None)
            st.rerun()

if input_method == "Subir CSV/Excel" and st.session_state.get('_wizard_step', 1) == 3:
    ib_cost_basis_map = st.session_state.get('_wizard_ib_map', {})
    _csv_ticker_data  = st.session_state.get('_wizard_csv_ticker_data', {})
    broker = st.session_state.get('_wizard_broker', 'generic')
    BROKER_LABELS = {'schwab': 'Charles Schwab', 'ibkr': 'Interactive Brokers', 'generic': 'Formato Genérico'}
    BROKER_COLORS = {'schwab': '#006497', 'ibkr': '#c8102e', 'generic': '#555555'}
    broker_label = BROKER_LABELS.get(broker, broker.upper())
    broker_color = BROKER_COLORS.get(broker, '#555555')
    try:
        results         = st.session_state.get('_results')
        classify_map    = st.session_state.get('_classify_map', {})
        skipped_tickers = st.session_state.get('_skipped', {})
        strat_results_cached = st.session_state.get('_strat_results')

        # (Los "ticker(s) excluidos del análisis" se movieron al pie, arriba del disclaimer.)

        if results:
            # ── Section header helper (jerarquía visual consistente) ──
            # Numera dinámicamente solo las secciones que sí se renderizan,
            # así la secuencia (01, 02, 03…) nunca se rompe aunque falte una.
            _section_no = [0]
            def _da_section(title, subtitle=""):
                _section_no[0] += 1
                _sub = (f'<p style="font-family:Inter,sans-serif;font-size:12px;'
                        f'color:#8899aa;margin:3px 0 0 0;line-height:1.45;">{subtitle}</p>') if subtitle else ''
                st.markdown(
                    f'<div style="display:flex;align-items:baseline;gap:14px;margin:36px 0 16px 0;'
                    f'padding-bottom:10px;border-bottom:2px solid #021C36;">'
                    f'<span style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;'
                    f'color:#006497;letter-spacing:0.04em;font-variant-numeric:tabular-nums;">'
                    f'{_section_no[0]:02d}</span>'
                    f'<div style="flex:1;"><p style="font-family:Inter,sans-serif;font-size:17px;'
                    f'font-weight:800;color:#021C36;letter-spacing:-0.01em;margin:0;">{title}</p>{_sub}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

            # ── Interpretación educativa por ticker (lee knowledge/instruments.yaml) ──
            def _render_interpretation(_t):
                _interp = logic.build_interpretation(results, _t)
                _exp_lines = logic.build_underlying_exposure(results, _t).get('lines', [])
                if not _interp.get('lines') and not _exp_lines:
                    return
                _items = ''.join(
                    f'<li style="margin:0 0 6px 0;">{_ln}</li>' for _ln in _interp.get('lines', []))
                st.markdown(
                    '<div style="border-left:4px solid #006497;background:#eef6fb;padding:12px 16px;margin:0 0 12px 0;">'
                    '<p style="font-family:Inter,sans-serif;font-size:9px;color:#006497;font-weight:700;'
                    'letter-spacing:0.12em;text-transform:uppercase;margin:0 0 8px 0;">Qué significa para ti</p>'
                    '<ul style="font-family:Inter,sans-serif;font-size:12px;color:#333333;line-height:1.55;'
                    'margin:0;padding-left:18px;">'
                    + _items + '</ul></div>',
                    unsafe_allow_html=True
                )
                if _exp_lines:
                    _eitems = ''.join(f'<li style="margin:0 0 6px 0;">{_ln}</li>' for _ln in _exp_lines)
                    st.markdown(
                        '<div style="border-left:4px solid #021C36;background:#f6f8fa;padding:12px 16px;margin:0 0 12px 0;">'
                        '<p style="font-family:Inter,sans-serif;font-size:9px;color:#021C36;font-weight:700;'
                        'letter-spacing:0.12em;text-transform:uppercase;margin:0 0 8px 0;">Exposición al subyacente — riesgo asimétrico</p>'
                        '<ul style="font-family:Inter,sans-serif;font-size:12px;color:#333333;line-height:1.55;'
                        'margin:0;padding-left:18px;">'
                        + _eitems + '</ul></div>',
                        unsafe_allow_html=True
                    )

            # ── Calidad de datos: se calcula aquí (lo usa el aviso de abajo) y se
            #    renderiza al final dentro de un expander vía _render_data_quality_panel. ──
            _dq = logic.assess_data_quality(results, classify_map)
            _dq_unrel = sorted([t for t, q in _dq.items() if q['level'] == 'unreliable'])
            _dq_recon = sorted([t for t, q in _dq.items() if q['level'] == 'reconciled'])
            _dq_part  = sorted([t for t, q in _dq.items() if q['level'] == 'partial'])
            _dq_ok    = sorted([t for t, q in _dq.items() if q['level'] == 'ok'])

            # ── Capa de comprensión (vista simple primero) ───────────────
            # En corto: ¿cuánto ingreso genera el portafolio, de dónde viene y
            # cuánto confiar en los números. El detalle denso vive más abajo.

            def _annual_income_for(_t):
                # Ingreso anual realista por ticker, con la fuente más confiable disponible:
                # realized (TTM real) → ttm_income → forward (anunciado). Siempre disponible.
                _s = results.get(_t) or {}
                if not isinstance(_s, dict) or 'error' in _s:
                    return 0.0
                _mv = _s.get('market_value') or 0
                _ry = _s.get('realized_yield')
                if _ry is not None and _mv:
                    return _ry / 100.0 * _mv
                _ttm = _s.get('ttm_income')
                if _ttm:
                    return float(_ttm)
                _fy = _s.get('forward_yield')
                if _fy is not None and _mv:
                    return _fy / 100.0 * _mv
                return 0.0

            _growth_fn = getattr(logic, 'filter_growth_assets', None)
            _growth_set = set((_growth_fn(results) or {}).keys()) if _growth_fn else set()
            _income_contrib = {}
            for _t in results:
                if _t in _growth_set:
                    continue
                _ai = _annual_income_for(_t)
                if _ai > 0:
                    _income_contrib[_t] = _ai
            _income_annual  = sum(_income_contrib.values())
            _income_monthly = _income_annual / 12.0
            _total_mv = sum((s.get('market_value') or 0) for s in results.values()
                            if isinstance(s, dict) and 'error' not in s)
            _income_yield = (_income_annual / _total_mv * 100) if _total_mv else 0.0

            # Confianza de datos (semáforo): exactas vs aproximadas
            _n_total = len(_dq) or len(results)
            _n_exact = len(_dq_ok)

            # Nota de acción: solo cuando hay posiciones no confiables (falta costo de origen).
            if _dq_unrel:
                st.markdown(
                    f'<div style="border-left:4px solid #e0a23c;background:#fbf7ef;padding:10px 16px;'
                    f'margin:2px 0 4px 0;font-family:Inter,sans-serif;font-size:12px;color:#5a4a2a;'
                    f'line-height:1.55;">A <b>{", ".join(_dq_unrel)}</b> le falta el costo de origen en el CSV '
                    f'(probablemente las acciones llegaron por <b>transferencia</b>): su ROI y la comparación con el '
                    f'índice son estimados. <b>Para volverlas exactas:</b> sube un estado de cuenta que incluya la '
                    f'compra original, o ingresa el costo base manualmente.</div>',
                    unsafe_allow_html=True)

            mode_a_tickers = [t for t, m in classify_map.items() if m == 'mode_a']
            mode_b_tickers = [t for t, m in classify_map.items() if m == 'mode_b']

            # Eventos técnicos consolidados → acordeón al pie (se llenan en los loops de detalle)
            _tech_events = []

            # ── HOJA EXCEL — método tradicional vs realidad ────────────
            def _render_hoja_excel():
                """Sección educativa: replica la 'hoja de Excel' tradicional (con sus errores) y
                la contrasta con la vista honesta + auditoría del yield titular de YieldMax."""
                _he = logic.build_hoja_excel(results, classify_map)
                _rows = _he['rows']
                if not _rows:
                    return
                _t = _he['totals']
                _money = lambda x: '—' if x is None else f'${x:,.2f}'
                _pct = lambda x, d=1: '—' if x is None else f'{x:.{d}f}%'
                _neg = lambda x: '—' if x is None else f'−${x:,.2f}'
                _fid = st.session_state.get('_file_id', 'x')
                _ttrc = '#1f8a5b' if (_t['total_return'] or 0) >= 0 else '#cf4b4b'

                # Tooltips por columna (reutilizan el copy de los párrafos explicativos).
                _TIP = {
                    'inicio': 'Fecha de tu primera compra de este activo. Un activo con más tiempo '
                              'tuvo más oportunidades de pagar y de moverse de precio.',
                    'accion': 'El ETF o acción. Aquí solo aparecen tus fondos de <b>income</b> '
                              '(distribución alta), no los de crecimiento.',
                    'titular': 'El yield <b>titular</b> que publica el fondo (marketing). Anualiza un '
                               'solo pago sobre el NAV; con distribuciones que saltan semana a semana '
                               'dice poco de lo que rinde de verdad.',
                    'inversion': 'Lo que pusiste de tu <b>bolsillo</b> (costo base): el capital real '
                                 'que aportaste, sin contar dividendos.',
                    'netos': 'Los dividendos que de verdad entraron a tu cuenta, <b>ya descontado</b> '
                             'el impuesto NRA. Incluye lo reinvertido (DRIP) y el efectivo.',
                    'bruto': 'El dividendo <b>bruto</b>: lo que el fondo declaró, <b>antes</b> de la '
                             'retención de impuesto a extranjeros.',
                    'nra': 'El impuesto que EE.UU. retiene a extranjeros (~30%) <b>antes</b> de '
                           'depositarte el dividendo. Por eso el neto es menor que el bruto.',
                    'totalinv': '⚠ El método viejo: <b>Inversión + Dividendos</b>, como si los '
                                'dividendos fueran capital que aportaste. <b>No lo son</b>: son '
                                'retorno —y en YieldMax buena parte es tu propio capital de vuelta '
                                '(ROC)—. Esta cifra infla el «invertido».',
                    'roc': '<b>Retorno de capital (ROC)</b>: la porción de lo distribuido que era '
                           '<b>tu propio dinero de vuelta</b>, no ganancia. Erosiona el NAV. Aquí se '
                           'resta del «total invertido» para corregir el engaño.',
                    'capreal': 'Tu <b>capital real aportado</b> una vez devuelto el ROC: Total inv '
                               '(Inv+Div) − ROC. Acerca el número inflado a lo que de verdad pusiste.',
                    'valor': 'Lo que valen hoy tus posiciones a precio de mercado.',
                    'retorno': '<b>Retorno total real</b> = Valor de mercado + dividendos en '
                               '<b>efectivo</b> − tu inversión. La única cifra que dice si ganaste o '
                               'perdiste. El DRIP no se suma aparte: ya está dentro del valor de mercado.',
                    'salud': 'Veredicto honesto por la <b>tendencia del precio del fondo</b> (erosión '
                             'del NAV), no por el yield titular.',
                    'ultdiv': 'Promedio de tus últimos ~4 pagos, para suavizar la volatilidad semana '
                              'a semana de un solo pago.',
                }

                def _sp(content, cls=''):
                    return f'<span class="{cls}">{content}</span>' if cls else f'<span>{content}</span>'

                def _th(label, tip, right=False, cls=''):
                    bc = 'da-tip-box r' if right else 'da-tip-box'
                    c = (cls + ' da-tip').strip()
                    return f'<span class="{c}">{label}<span class="{bc}">{tip}</span></span>'

                def _row(cells, tpl, cls=''):
                    c = ('da-he-row ' + cls).strip()
                    return f'<div class="{c}" style="grid-template-columns:{tpl};">{cells}</div>'

                def _grid(head, body, total, min_px):
                    return (f'<div class="da-he-wrap"><div class="da-he-grid" '
                            f'style="min-width:{min_px}px;">{head}{body}{total}</div></div>')

                # Anchos (fr) por columna lógica; el grid-template se arma por tabla y comparten
                # las columnas comunes para que coincidan en espacio entre ambas cuadrículas.
                _W = {'inicio': 'minmax(58px,0.85fr)', 'accion': '0.7fr', 'titular': '0.7fr',
                      'inversion': '1fr', 'bruto': '1fr', 'nra': '0.9fr', 'netos': '1fr',
                      'totalinv': '1.1fr', 'roc': '0.9fr', 'capreal': '1.1fr', 'valor': '1fr',
                      'retorno': '1.15fr', 'salud': '0.95fr', 'ultdiv': '1fr'}

                st.markdown(
                    '<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:700;'
                    'color:#021C36;margin:6px 0 2px 0;letter-spacing:0.04em;">HOJA EXCEL · EL '
                    'MÉTODO TRADICIONAL VS LA REALIDAD</p>'
                    '<p style="font-family:Inter,sans-serif;font-size:11.5px;color:#5a6b7a;'
                    'margin:0 0 10px 0;line-height:1.55;">La hoja de cálculo de toda la vida suma '
                    '<b>Inversión + Dividendos</b> para decir cuánto «tienes invertido». Abajo la '
                    'replicamos tal cual (con su sesgo) y la comparamos con lo que de verdad pasó '
                    'con tu dinero.</p>', unsafe_allow_html=True)

                # ── Tabla 1 — método tradicional (rejilla limpia, columnas comunes alineadas) ──
                _o1 = ['inicio', 'accion', 'inversion', 'netos', 'totalinv', 'valor', 'ultdiv', 'titular']
                _tpl1 = ' '.join(_W[k] for k in _o1)
                _h1 = _row(
                    _th('Inicio', _TIP['inicio'], cls='hl')
                    + _th('Acción', _TIP['accion'], cls='hl')
                    + _th('Inversión', _TIP['inversion'])
                    + _th('Dividendos', _TIP['netos'])
                    + _th('⚠ Total inv. (Inv+Div)', _TIP['totalinv'], cls='naive')
                    + _th('Valor mer.', _TIP['valor'])
                    + _th('Últ. div (~4 pagos)', _TIP['ultdiv'], right=True)
                    + _th('% Titular', _TIP['titular'], right=True),
                    _tpl1, cls='da-he-head')
                _b1 = ''
                for r in _rows:
                    _b1 += _row(
                        _sp(r['inicio'] or '—', 'l muted')
                        + _sp(r['ticker'], 'tk')
                        + _sp(_money(r['investment']))
                        + _sp(_money(r['dividends_net']))
                        + _sp(_money(r['total_inv_naive']), 'naive')
                        + _sp(_money(r['market_value']))
                        + _sp(_money(r.get('last_div_avg') or r['last_div']), 'muted')
                        + _sp(_pct(r['advertised']), 'amber'),
                        _tpl1)
                _tot1 = _row(
                    _sp('', 'l') + _sp('Total', 'l')
                    + _sp(_money(_t['investment']))
                    + _sp(_money(_t['dividends_net']))
                    + _sp(_money(_t['total_inv_naive']), 'naive')
                    + _sp(_money(_t['market_value']))
                    + _sp('') + _sp(''),
                    _tpl1, cls='da-he-total')
                st.markdown(
                    '<p style="font-family:Inter,sans-serif;font-size:11px;font-weight:700;'
                    'color:#64748B;margin:2px 0 3px 2px;letter-spacing:0.06em;">① MÉTODO TRADICIONAL '
                    '<span style="color:#c9821f;">(como tu hoja de Excel)</span></p>'
                    + _grid(_h1, _b1, _tot1, 620)
                    + '<p style="font-family:Inter,sans-serif;font-size:10px;color:#a06a1a;'
                    'margin:4px 0 16px 2px;line-height:1.5;">⚠ <b>«Total inv.»</b> suma tu dinero con '
                    'los dividendos como si fueran capital que aportaste. No lo son: son <b>retorno</b> '
                    '—y en YieldMax buena parte es <b>tu propio capital de vuelta (ROC)</b>—. Pasa el '
                    'cursor por cada encabezado para ver su explicación.</p>',
                    unsafe_allow_html=True)

                # ── Tabla 2 — vista honesta (interactiva, st.fragment: drill-down sin recarga) ──
                st.markdown(
                    '<p style="font-family:Inter,sans-serif;font-size:11px;font-weight:700;'
                    'color:#0F766E;margin:6px 0 3px 2px;letter-spacing:0.06em;">② VISTA HONESTA '
                    '<span style="color:#5a6b7a;font-weight:500;">(lo que de verdad pasó con tu '
                    'dinero)</span></p>', unsafe_allow_html=True)

                @st.fragment
                def _honest_grid():
                    _tc1, _tc2, _ = st.columns([1.1, 1.3, 0.9])
                    with _tc1:
                        _sd = st.toggle('Desglosar dividendos netos', value=False,
                                        key=f'_he_div_{_fid}',
                                        help='Abre Div. brutos y − Imp. NRA: netos = brutos − impuesto.')
                    with _tc2:
                        _strap = st.toggle('Revelar la trampa del «total invertido»', value=False,
                                           key=f'_he_trap_{_fid}',
                                           help='Resta el ROC al Inv+Div para mostrar tu capital real aportado.')
                    _o2 = ['inicio', 'accion', 'inversion']
                    if _sd:
                        _o2 += ['bruto', 'nra']
                    _o2 += ['netos', 'totalinv']
                    if _strap:
                        _o2 += ['roc', 'capreal']
                    _o2 += ['valor', 'retorno', 'salud']
                    _tpl2 = ' '.join(_W[k] for k in _o2)
                    _mw2 = max(620, len(_o2) * 86)

                    _hc = (_th('Inicio', _TIP['inicio'], cls='hl')
                           + _th('Acción', _TIP['accion'], cls='hl')
                           + _th('Tu inversión', _TIP['inversion']))
                    if _sd:
                        _hc += _th('Div. brutos', _TIP['bruto']) + _th('− Imp. NRA', _TIP['nra'])
                    _hc += (_th('Div. netos', _TIP['netos'])
                            + _th('⚠ Total inv.', _TIP['totalinv'], cls='naive'))
                    if _strap:
                        _hc += _th('− ROC', _TIP['roc']) + _th('Capital real', _TIP['capreal'], right=True)
                    _hc += (_th('Valor mer.', _TIP['valor'], right=True)
                            + _th('Retorno total real', _TIP['retorno'], right=True)
                            + _th('Salud del NAV', _TIP['salud'], right=True, cls='c'))
                    _h2 = _row(_hc, _tpl2, cls='da-he-head')

                    _b2 = ''
                    for r in _rows:
                        _trc = 'pos' if (r['total_return'] or 0) >= 0 else 'neg'
                        _nh = r['nav_health']
                        _badge = ('<span class="da-he-badge" style="background:' + _nh['color']
                                  + '22;color:' + _nh['color'] + ';">' + _nh['label'] + '</span>')
                        _cells = (_sp(r['inicio'] or '—', 'l muted')
                                  + _sp(r['ticker'], 'tk')
                                  + _sp(_money(r['investment'])))
                        if _sd:
                            _cells += (_sp(_money(r['dividends_gross']), 'muted')
                                       + _sp(_neg(r['nra_tax']), 'nra'))
                        _cells += (_sp(_money(r['dividends_net']))
                                   + _sp(_money(r['total_inv_naive']), 'naive'))
                        if _strap:
                            _cap = (r['total_inv_naive'] - r['roc_dollars']) if r['roc_dollars'] is not None else None
                            _cells += _sp(_neg(r['roc_dollars']), 'nra') + _sp(_money(_cap))
                        _ret = (_money(r['total_return'])
                                + '<br><span style="font-size:10px;">(' + _pct(r['total_return_pct']) + ')</span>')
                        _cells += _sp(_money(r['market_value'])) + _sp(_ret, _trc) + _sp(_badge, 'c')
                        _b2 += _row(_cells, _tpl2)

                    _trct = 'pos' if (_t['total_return'] or 0) >= 0 else 'neg'
                    _tc = _sp('', 'l') + _sp('Total', 'l') + _sp(_money(_t['investment']))
                    if _sd:
                        _tc += _sp(_money(_t['dividends_gross']), 'muted') + _sp(_neg(_t['nra_tax']), 'nra')
                    _tc += _sp(_money(_t['dividends_net'])) + _sp(_money(_t['total_inv_naive']), 'naive')
                    if _strap:
                        _tcap = _t['total_inv_naive'] - (_t['roc_dollars'] or 0)
                        _tc += _sp(_neg(_t['roc_dollars']), 'nra') + _sp(_money(_tcap))
                    _tret = _money(_t['total_return']) + ' (' + _pct(_t['total_return_pct']) + ')'
                    _tc += _sp(_money(_t['market_value'])) + _sp(_tret, _trct) + _sp('', 'c')
                    _tot2 = _row(_tc, _tpl2, cls='da-he-total')

                    st.markdown(_grid(_h2, _b2, _tot2, _mw2), unsafe_allow_html=True)
                    if _strap:
                        st.markdown(
                            '<p style="font-family:Inter,sans-serif;font-size:10px;color:#a06a1a;'
                            'margin:3px 0 6px 2px;line-height:1.5;">El «total inv.» inflado se corrige al '
                            '<b>devolver el ROC</b> —tu propio capital que el fondo te regresó como si fuera '
                            'dividendo—; lo que queda es tu <b>capital real aportado</b>.</p>',
                            unsafe_allow_html=True)

                _honest_grid()
                st.markdown(
                    '<p style="font-family:Inter,sans-serif;font-size:10px;color:#445566;'
                    'margin:3px 0 14px 2px;line-height:1.5;"><b>Retorno total real</b> = Valor de mercado '
                    '+ dividendos en efectivo − tu inversión. Es la única cifra que dice si ganaste o '
                    'perdiste. Los «Div. netos» incluyen lo <b>reinvertido (DRIP)</b>, que ya está dentro '
                    'del «Valor de mercado»; por eso el retorno suma solo el <b>efectivo</b>, para no '
                    'contar el mismo dinero dos veces. <b>Salud del NAV</b> juzga por la tendencia del '
                    'precio del fondo (erosión), no por el yield titular.</p>', unsafe_allow_html=True)

                # ── El viaje del dinero — desglose interactivo por fondo ──
                # Gate de integridad: solo fondos con todos los campos y ecuaciones
                # que cuadran (pocket+drip==total y bruto−imp==drip+cash, ±$1).
                _vj_data = {}
                _vj_excl = []
                for r in _rows:
                    _vtk = r['ticker']
                    _vpk = r['investment']
                    _vbr = r['dividends_gross']
                    _vim = r['nra_tax']
                    _vnt = r['dividends_net']
                    _vch = (results.get(_vtk) or {}).get('dividends_collected_cash')
                    if None in (_vpk, _vbr, _vim, _vnt, _vch) or _vpk <= 0:
                        continue
                    _vdr = _vnt - _vch
                    if _vdr < 0:
                        _vj_excl.append(_vtk)
                        continue
                    _vtc = _vpk + _vdr
                    if abs((_vpk + _vdr) - _vtc) > 1 or abs((_vbr - _vim) - (_vdr + _vch)) > 1:
                        _vj_excl.append(_vtk)
                        continue
                    _vj_data[_vtk] = {'pocket': _vpk, 'bruto': _vbr, 'imp': _vim,
                                      'neto': _vnt, 'drip': _vdr, 'cash': _vch, 'total': _vtc,
                                      'mv': r['market_value'] or 0, 'ret': r['total_return'],
                                      'ret_pct': r['total_return_pct'], 'nav': r.get('nav_health')}

                if _vj_data:
                    def _render_salud_nav(tk, d, results):
                        """Paso 'Salud del NAV': veredicto primero, luego la prueba de captura
                        asimétrica (tarjetas + gráficos), protagonista de la pestaña — no el %
                        de ROC (eso es etiqueta fiscal, ver logic.py:2453)."""
                        import altair as alt
                        import numpy as np
                        s = results.get(tk) or {}
                        st.markdown(
                            '<p style="font-family:Inter,sans-serif;font-size:11px;font-weight:700;'
                            'color:#006497;margin:6px 0 3px 2px;letter-spacing:0.06em;">¿SE ESTÁ '
                            'DESTRUYENDO TU CAPITAL, O SOLO BAJÓ CON EL MERCADO?</p>',
                            unsafe_allow_html=True)

                        # ── Veredicto primero ──
                        _nvh = d.get('nav')
                        if _nvh:
                            _verdict = _nvh.get('verdict')
                            _tint = {'destructive': '#fdeeec', 'accounting': '#edf7f1',
                                     'mixed': '#fdf3e4'}.get(_verdict, '#f2f2f2')
                            _score = _nvh.get('gauge_score')
                            if _score is None:
                                _gauge_html = ("<div style='height:14px;background:#e9ecef;color:#888;"
                                               "font-size:10px;text-align:center;line-height:14px;'>"
                                               "no medible aún</div>")
                            else:
                                _gauge_html = (
                                    "<div style='position:relative;height:14px;margin:8px 0 2px 0;"
                                    "background:linear-gradient(90deg,#4caf82 0%,#e0a23c 50%,#e05c5c 100%);'>"
                                    f"<div style='position:absolute;top:-3px;left:{_score:.0f}%;width:3px;"
                                    "height:20px;background:#021C36;transform:translateX(-50%);'></div></div>"
                                    "<div style='display:flex;justify-content:space-between;font-size:10px;"
                                    "color:#888;'><span>Sano</span><span>Destruyéndose</span></div>")
                            st.markdown(
                                f"<div style='border-left:4px solid {_nvh['color']};background:{_tint};"
                                f"padding:10px 14px;margin:4px 0 10px 0;'>"
                                f"<div style='font-weight:700;font-size:15px;color:{_nvh['color']};'>"
                                f"{_nvh['headline']}</div>"
                                f"<div style='font-size:12.5px;color:#333;margin:6px 0 2px 0;"
                                f"line-height:1.5;'>{_nvh['plain']}</div>"
                                f"{_gauge_html}</div>",
                                unsafe_allow_html=True)

                        def _mini_detalle():
                            _mini = ''
                            if _nvh and _nvh.get('reason'):
                                _mini += (f"<div style='font-size:12.5px;color:#333;"
                                          f"line-height:1.5;margin:4px 0;'>{_nvh['reason']}</div>")
                            _roc_min = s.get('roc_percent')
                            if _roc_min is not None:
                                _mini += (f'<p style="font-family:Inter,sans-serif;font-size:10px;'
                                          f'color:#8899aa;margin:6px 0 4px 2px;">ROC 19a: '
                                          f'{_roc_min:.0f}% — etiqueta fiscal, no medida de '
                                          f'destrucción.</p>')
                            if _mini:
                                st.markdown(
                                    f"<details style='margin:2px 0 10px 0;'>"
                                    f"<summary style='cursor:pointer;font-size:12px;color:#006497;'>"
                                    f"Ver detalle técnico</summary>{_mini}</details>",
                                    unsafe_allow_html=True)

                        _fund_close = s.get('fund_close_series')
                        _under_close = s.get('underlying_close_series')
                        _under_tk = s.get('underlying_ticker')
                        if _fund_close is None or _under_close is None or not _under_tk:
                            st.markdown(
                                '<p style="font-family:Inter,sans-serif;font-size:12.5px;'
                                'color:#445566;margin:4px 0 10px 2px;line-height:1.5;">Este fondo no '
                                'tiene un subyacente conocido — no hay con qué contrastar su NAV.</p>',
                                unsafe_allow_html=True)
                            _mini_detalle()
                            return

                        _df = pd.concat(
                            {tk: _fund_close, _under_tk: _under_close}, axis=1).dropna()
                        if len(_df) < 2:
                            st.markdown(
                                '<p style="font-family:Inter,sans-serif;font-size:12px;'
                                'color:#8899aa;margin:4px 0 10px 2px;">No hay suficiente '
                                'historia superpuesta entre fondo y subyacente para graficar.</p>',
                                unsafe_allow_html=True)
                            _mini_detalle()
                            return

                        _base = _df.iloc[0]
                        _norm = _df / _base * 100.0
                        _fund_norm = _norm[tk]
                        _under_norm = _norm[_under_tk]

                        # ── Tarjetas de captura asimétrica ──
                        _rets = _df.pct_change().dropna()
                        if len(_rets) >= 30 and (_rets[_under_tk] != 0).any():
                            _up_mask = _rets[_under_tk] > 0
                            _down_mask = _rets[_under_tk] < 0
                            _up_den = _rets.loc[_up_mask, _under_tk].sum()
                            _down_den = _rets.loc[_down_mask, _under_tk].sum()
                            _up_cap = (_rets.loc[_up_mask, tk].sum() / _up_den) if _up_den else None
                            _down_cap = (_rets.loc[_down_mask, tk].sum() / _down_den) if _down_den else None
                            _ratio_now = (_fund_norm.iloc[-1] / _under_norm.iloc[-1]) * 100.0
                            if (_up_cap is not None and _down_cap is not None
                                    and _up_cap > 0 and _down_cap > 0):
                                _down_color = ('#8f2318' if _down_cap > _up_cap else '#333333')
                                _cards = [
                                    (f'Si {_under_tk} sube 10%',
                                     f'{tk} sube +{_up_cap * 10:.1f}%', '#333333'),
                                    (f'Si {_under_tk} cae 10%',
                                     f'{tk} cae −{_down_cap * 10:.1f}%', _down_color),
                                    (f'De cada $100 en {_under_tk}',
                                     f'{tk} conserva ${_ratio_now:.0f}', '#333333'),
                                ]
                                _cards_html = ''.join(
                                    f'<div style="flex:1;background:#ffffff;border:1px solid #e3ddd4;'
                                    f'padding:10px 12px;">'
                                    f'<div style="font-family:Inter,sans-serif;font-size:10px;'
                                    f'color:#8899aa;text-transform:uppercase;letter-spacing:0.04em;'
                                    f'margin-bottom:4px;">{_lbl}</div>'
                                    f'<div style="font-family:Inter,sans-serif;font-size:16px;'
                                    f'font-weight:700;color:{_clr};">{_val}</div></div>'
                                    for _lbl, _val, _clr in _cards)
                                st.markdown(
                                    f'<div style="display:flex;gap:8px;margin:2px 0 12px 0;">'
                                    f'{_cards_html}</div>', unsafe_allow_html=True)

                        # ── Gráfico principal: base-100 + sombreado + rebote anotado ──
                        _plot_df = _norm.rename_axis('Fecha').reset_index().melt(
                            id_vars='Fecha', var_name='Serie', value_name='Valor')
                        _lines = alt.Chart(_plot_df).mark_line(strokeWidth=2).encode(
                            x=alt.X('Fecha:T', title=None),
                            y=alt.Y('Valor:Q', title='Base 100 (inicio del período común)'),
                            color=alt.Color('Serie:N',
                                scale=alt.Scale(domain=[tk, _under_tk],
                                                range=['#006497', '#2d3748']),
                                legend=alt.Legend(title=None, orient='top', labelFontSize=12)),
                            tooltip=[alt.Tooltip('Fecha:T'), alt.Tooltip('Serie:N'),
                                     alt.Tooltip('Valor:Q', format='.1f', title='Índice')]
                        )
                        _area_df = pd.DataFrame({
                            'Fecha': _norm.index,
                            'low': np.minimum(_fund_norm.values, _under_norm.values),
                            'high': _under_norm.values,
                        })
                        _area = alt.Chart(_area_df).mark_area(opacity=0.12, color='#c0392b').encode(
                            x=alt.X('Fecha:T'), y=alt.Y('low:Q'), y2=alt.Y2('high:Q'),
                            tooltip=alt.value(None))
                        _layers = [_area, _lines]

                        _u_vals = _under_norm.values
                        _u_idx = _under_norm.index
                        _best_gain = -1.0
                        _best_i0 = _best_i1 = None
                        _min_i = 0
                        for _i in range(1, len(_u_vals)):
                            if _u_vals[_i] < _u_vals[_min_i]:
                                _min_i = _i
                            _gain = (_u_vals[_i] / _u_vals[_min_i]) - 1.0 if _u_vals[_min_i] else -1.0
                            if _gain > _best_gain:
                                _best_gain = _gain
                                _best_i0, _best_i1 = _min_i, _i
                        if _best_gain >= 0.15 and _best_i0 is not None and _best_i0 != _best_i1:
                            _d0, _d1 = _u_idx[_best_i0], _u_idx[_best_i1]
                            _und_move = int(round(_best_gain * 100))
                            _fund_move = int(round(
                                (_fund_norm.iloc[_best_i1] / _fund_norm.iloc[_best_i0] - 1.0) * 100))
                            _rule_df = pd.DataFrame({'Fecha': [_d0, _d1]})
                            _rules = alt.Chart(_rule_df).mark_rule(
                                color='#c9a86a', strokeDash=[4, 3]).encode(x='Fecha:T')
                            _txt_df = pd.DataFrame({
                                'Fecha': [_d1],
                                'Valor': [float(_norm.loc[_d1:].max().max()
                                                if not _norm.loc[_d1:].empty else _norm.values.max())],
                                'label': [f'En este rebote: {_under_tk} +{_und_move}% · {tk} {_fund_move:+d}%'],
                            })
                            _text = alt.Chart(_txt_df).mark_text(
                                align='left', dx=4, dy=-6, fontSize=10, color='#8a6d3b').encode(
                                x='Fecha:T', y='Valor:Q', text='label:N')
                            _layers += [_rules, _text]

                        _pct_u = _under_norm - 100.0
                        _pct_f = _fund_norm - 100.0
                        _hover_df = pd.DataFrame({
                            'Fecha': _norm.index,
                            'u_lbl': [f'{_v:+.0f}% desde el inicio' for _v in _pct_u],
                            'f_lbl': [f'{_v:+.0f}% desde el inicio' for _v in _pct_f],
                            'gap_lbl': [f'{_fv - _uv:+.0f} pts'
                                        for _fv, _uv in zip(_pct_f, _pct_u)],
                        })
                        _hover = alt.Chart(_hover_df).mark_rule(
                            strokeWidth=12, opacity=0.001).encode(
                            x=alt.X('Fecha:T'),
                            tooltip=[alt.Tooltip('Fecha:T', format='%d/%m/%y', title='Fecha'),
                                     alt.Tooltip('u_lbl:N', title=_under_tk),
                                     alt.Tooltip('f_lbl:N', title=tk),
                                     alt.Tooltip('gap_lbl:N',
                                                 title=f'{tk} vs {_under_tk}')])
                        _layers.append(_hover)

                        _sl_key = f'_nav_win_{tk}_{_fid}'
                        _dates = list(_norm.index)
                        _meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
                                  'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
                        _cur_win = st.session_state.get(_sl_key)
                        if _cur_win and (_cur_win[0] != _dates[0] or _cur_win[1] != _dates[-1]):
                            _hl_df = pd.DataFrame({'x0': [_cur_win[0]], 'x1': [_cur_win[1]]})
                            _hl = alt.Chart(_hl_df).mark_rect(
                                color='#c9a86a', opacity=0.15).encode(x='x0:T', x2='x1:T')
                            _layers.insert(0, _hl)

                        _chart = alt.layer(*_layers).properties(
                            height=280, background=CHART_PALETTE['bg']).configure_view(
                            strokeOpacity=0, fill=CHART_PALETTE['bg'])
                        st.altair_chart(_chart, use_container_width=True)

                        st.markdown(
                            '<p style="font-family:Inter,sans-serif;font-size:12px;color:#6b7683;'
                            'margin:2px 0 0 2px;">Mide cualquier tramo: mueve los dos extremos y '
                            'te digo cuánto subió o cayó cada uno (la ventana se resalta en el '
                            'gráfico).</p>', unsafe_allow_html=True)
                        _win_sel = st.select_slider(
                            'Tramo a medir', options=_dates,
                            value=(_dates[0], _dates[-1]),
                            format_func=lambda t: f'{t.day} {_meses[t.month - 1]} {str(t.year)[2:]}',
                            key=_sl_key, label_visibility='collapsed')
                        if _win_sel and len(_win_sel) == 2:
                            _t0, _t1 = sorted(_win_sel)
                            _win = _norm.loc[_t0:_t1]
                            if len(_win) >= 2:
                                _um = (_win[_under_tk].iloc[-1] / _win[_under_tk].iloc[0] - 1) * 100
                                _fm = (_win[tk].iloc[-1] / _win[tk].iloc[0] - 1) * 100
                                if _um > 1:
                                    if _fm < 0:
                                        _interp_clr = '#8f2318'
                                        _interp = (f'Mientras {_under_tk} subía, {tk} CAYÓ '
                                                   f'{_fm:.0f}% — no capturó nada de la subida')
                                    else:
                                        _cap_pct = _fm / _um * 100
                                        _interp_clr = '#8f2318' if _cap_pct < 60 else '#333333'
                                        _interp = (f'{tk} capturó el {_cap_pct:.0f}% de la subida '
                                                   f'de {_under_tk}')
                                elif _um < -1:
                                    if _fm > 0:
                                        _interp_clr = '#333333'
                                        _interp = (f'{tk} esquivó la caída de {_under_tk} '
                                                   f'en este tramo')
                                    else:
                                        _cap_pct = _fm / _um * 100
                                        _interp_clr = '#8f2318' if _cap_pct > 90 else '#333333'
                                        _interp = f'{tk} tomó el {_cap_pct:.0f}% de la caída'
                                else:
                                    _interp_clr = '#333333'
                                    _interp = 'El subyacente casi no se movió en este tramo.'
                                _f0 = f'{_t0.day} {_meses[_t0.month - 1]} {_t0.year}'
                                _f1 = f'{_t1.day} {_meses[_t1.month - 1]} {_t1.year}'
                                st.markdown(
                                    f'<div style="background:#ffffff;border:1px solid #e3ddd4;'
                                    f'padding:10px 14px;margin:2px 0 10px 0;'
                                    f'font-family:Inter,sans-serif;">'
                                    f'<div style="font-size:12px;color:#8899aa;'
                                    f'text-transform:uppercase;letter-spacing:0.04em;">'
                                    f'Del {_f0} al {_f1}</div>'
                                    f'<div style="font-size:15px;font-weight:700;color:#021C36;'
                                    f'margin:3px 0;">{_under_tk} {_um:+.0f}% · {tk} {_fm:+.0f}%</div>'
                                    f'<div style="font-size:12px;color:{_interp_clr};">{_interp}'
                                    f'</div></div>', unsafe_allow_html=True)

                        # ── Series TR en bruto (para el reencuadre del ratio, SIEMPRE en bruto,
                        # sin importar el radio fiscal del bloque "¿Dónde terminó el dinero?") ──
                        _fund_close_w = _df[tk]
                        _under_close_w = _df[_under_tk]
                        _fund_divs_raw = s.get('fund_dividends_series')
                        _fund_divs_w = (_fund_divs_raw.reindex(_df.index).fillna(0.0)
                                        if _fund_divs_raw is not None
                                        else pd.Series(0.0, index=_df.index))
                        _under_divs_raw = s.get('underlying_dividends_series')
                        _under_divs_w = (_under_divs_raw.reindex(_df.index).fillna(0.0)
                                         if _under_divs_raw is not None
                                         else pd.Series(0.0, index=_df.index))
                        _tr_df_bruto = logic.build_total_return_series(
                            _fund_close_w, _fund_divs_w, None)
                        _under_tr_df = logic.build_total_return_series(
                            _under_close_w, _under_divs_w, None)
                        _drip_bruto_final = (float(_tr_df_bruto['drip'].iloc[-1])
                                              if len(_tr_df_bruto) else float(_fund_norm.iloc[-1]))
                        _under_tr_final = (float(_under_tr_df['drip'].iloc[-1])
                                           if len(_under_tr_df) else float(_under_norm.iloc[-1]))
                        _ratio_con_div = (_drip_bruto_final / _under_tr_final * 100.0
                                          if _under_tr_final else None)

                        # ── Gráfico de ratio: el motor en una sola línea ──
                        st.markdown(
                            f'<p style="font-family:Inter,sans-serif;font-size:11px;font-weight:700;'
                            f'color:#006497;margin:10px 0 3px 2px;letter-spacing:0.06em;">EL MOTOR '
                            f'EN UNA SOLA LÍNEA: ¿CUÁNTO NAV CONSERVA {tk} POR CADA $100 DE '
                            f'{_under_tk}?</p>',
                            unsafe_allow_html=True)
                        _ratio_series = (_fund_norm / _under_norm * 100.0).dropna()
                        _rv = [float(v) for v in _ratio_series.values]
                        if len(_rv) >= 2:
                            _rw, _rh, _rp = 700.0, 120.0, 10.0
                            _rmax = max(110.0, max(_rv) * 1.05)
                            _n_r = len(_rv)
                            _pts = ' '.join(
                                f'{_rp + (_rw - 2 * _rp) * _i / (_n_r - 1):.1f},'
                                f'{_rh - 24 - (_rh - 34) * (_v / _rmax):.1f}'
                                for _i, _v in enumerate(_rv))
                            _y100 = _rh - 24 - (_rh - 34) * (100.0 / _rmax)
                            _y50 = _rh - 24 - (_rh - 34) * (50.0 / _rmax)
                            _y0 = _rh - 24
                            _fill_pts = (f'{_rp:.1f},{_y0:.1f} ' + _pts
                                         + f' {_rw - _rp:.1f},{_y0:.1f}')
                            _x_last = _rw - _rp
                            _y_last = _rh - 24 - (_rh - 34) * (_rv[-1] / _rmax)
                            _i0, _i1 = _ratio_series.index[0], _ratio_series.index[-1]
                            _lbl0 = f'{_i0.day} {_meses[_i0.month - 1]} {str(_i0.year)[2:]}'
                            _lbl1 = f'{_i1.day} {_meses[_i1.month - 1]} {str(_i1.year)[2:]}'
                            _grid = ''.join(
                                f'<line x1="{_rp}" y1="{_gy:.1f}" x2="{_rw - _rp}" y2="{_gy:.1f}" '
                                f'stroke="#e8e0d4" stroke-width="1"/>'
                                f'<text x="{_rp + 2}" y="{_gy - 3:.1f}" font-size="10" '
                                f'fill="#8899aa" font-family="Inter,sans-serif">${_gv}</text>'
                                for _gy, _gv in [(_y100, 100), (_y50, 50)])
                            st.markdown(
                                f'<svg viewBox="0 0 {_rw:.0f} {_rh:.0f}" role="img" '
                                f'style="width:100%;display:block;background:'
                                f'{CHART_PALETTE["bg"]};">'
                                f'{_grid}'
                                f'<line x1="{_rp}" y1="{_y0:.1f}" x2="{_rw - _rp}" y2="{_y0:.1f}" '
                                f'stroke="#c9c2b6" stroke-width="1"/>'
                                f'<polygon points="{_fill_pts}" fill="rgba(192,57,43,0.08)"/>'
                                f'<polyline points="{_pts}" fill="none" stroke="#c0392b" '
                                f'stroke-width="2.5"/>'
                                f'<circle cx="{_x_last:.1f}" cy="{_y_last:.1f}" r="3.5" '
                                f'fill="#c0392b"/>'
                                f'<text x="{_x_last - 6:.1f}" y="{_y_last - 8:.1f}" '
                                f'text-anchor="end" font-size="13" font-weight="700" '
                                f'fill="#8f2318" font-family="Inter,sans-serif">'
                                f'${_rv[-1]:.0f}</text>'
                                f'<text x="{_rp}" y="{_rh - 8:.1f}" font-size="10" fill="#8899aa" '
                                f'font-family="Inter,sans-serif">{_lbl0}</text>'
                                f'<text x="{_rw - _rp:.1f}" y="{_rh - 8:.1f}" text-anchor="end" '
                                f'font-size="10" fill="#8899aa" '
                                f'font-family="Inter,sans-serif">{_lbl1}</text>'
                                f'</svg>', unsafe_allow_html=True)

                        _ratio_final = float(_ratio_series.iloc[-1])
                        if _ratio_final < 85:
                            _ratio_txt = (f'desciende, {tk} está sufriendo una destrucción de '
                                          f'capital ADICIONAL a la del mercado.')
                        else:
                            _ratio_txt = (f'se mantiene, {tk} solo está acompañando al mercado — '
                                          f'no hay destrucción adicional que la del propio '
                                          f'subyacente.')
                        st.markdown(
                            f'<p style="font-family:Inter,sans-serif;font-size:12px;color:#6b7683;'
                            f'margin:4px 0 4px 2px;line-height:1.5;">Si esta línea fuera plana, '
                            f'{tk} solo estaría siguiendo a {_under_tk} (riesgo de mercado, no '
                            f'destrucción). Como {_ratio_txt} Esta línea no incluye dividendos a '
                            f'propósito: mide cuánto NAV queda generando tu próximo cheque, y parte '
                            f'de su caída es el arrastre natural de cada distribución.</p>',
                            unsafe_allow_html=True)
                        if _ratio_con_div is not None:
                            st.markdown(
                                f'<p style="font-family:Inter,sans-serif;font-size:12px;'
                                f'color:#6b7683;margin:0 0 12px 2px;line-height:1.5;">'
                                f'<span style="color:#0f6e56;font-weight:700;">Contando los '
                                f'dividendos reinvertidos, por cada $100 en {_under_tk} habrías '
                                f'tenido ~${_ratio_con_div:.0f}</span>.</p>',
                                unsafe_allow_html=True)

                        # ── ¿Dónde terminó el dinero? — Total Return (DRIP / efectivo) ──
                        # Price Return puro (arriba, motor del ratio) sirve para ver si el fondo
                        # se destruye, pero no es lo que el inversionista se llevó de verdad. Aquí
                        # se suman los dividendos, con impuesto NRA opcional (bruto / ROC-aware /
                        # peor caso 30% plano).
                        st.markdown(
                            '<p style="font-family:Inter,sans-serif;font-size:11px;font-weight:700;'
                            'color:#006497;margin:14px 0 3px 2px;letter-spacing:0.06em;">¿DÓNDE '
                            'TERMINÓ EL DINERO? — EL OTRO LADO DE LA MONEDA</p>',
                            unsafe_allow_html=True)
                        st.markdown(
                            '<p style="font-family:Inter,sans-serif;font-size:12px;color:#6b7683;'
                            'margin:0 0 8px 2px;line-height:1.5;">Arriba solo miramos el precio '
                            '(Price Return): dice si el fondo se está destruyendo, no lo que tú '
                            'te llevaste. Sumando los dividendos que cobraste o reinvertiste, esto '
                            'es lo que quedó de cada $100 — para el resultado completo con tus '
                            'impuestos reales del CSV, ve la pestaña «Resultado real».</p>',
                            unsafe_allow_html=True)

                        _roc19a_info = logic.load_roc_19a().get(str(tk).upper())
                        _country_sel = st.session_state.get('proj_country')
                        _country = _country_sel if _country_sel in logic.NRA_COUNTRY_RATES else None
                        _base_rate_pct = (logic.NRA_COUNTRY_RATES[_country][0] if _country
                                          else logic.NRA_DEFAULT_RATE)
                        _base_rate = _base_rate_pct / 100.0

                        _worst_lbl = f'Peor caso ({_base_rate_pct:.0f}% plano)'
                        _tr_options = ['Bruto (0%)', _worst_lbl]
                        if _roc19a_info:
                            _tr_options = ['Bruto (0%)', 'Neto estimado (ROC 19a)',
                                           _worst_lbl]
                        _tr_mode = st.radio('Escenario fiscal', _tr_options, horizontal=True,
                                            key=f'_nav_tr_mode_{tk}_{_fid}',
                                            label_visibility='collapsed')

                        if _tr_mode == 'Neto estimado (ROC 19a)':
                            _div_dates = _fund_divs_w[_fund_divs_w > 0].index
                            _schedule = logic.build_roc_aware_withholding(
                                tk, _div_dates, base_rate=_base_rate)
                            _tr_df = logic.build_total_return_series(
                                _fund_close_w, _fund_divs_w, _schedule)
                        elif _tr_mode == _worst_lbl:
                            _schedule = _base_rate
                            _tr_df = logic.build_total_return_series(
                                _fund_close_w, _fund_divs_w, _schedule)
                        else:
                            _schedule = None
                            _tr_df = _tr_df_bruto

                        _price_final = float(_fund_norm.iloc[-1])
                        _drip_final = (float(_tr_df['drip'].iloc[-1])
                                       if len(_tr_df) else _price_final)
                        _cash_final = (float(_tr_df['cash'].iloc[-1])
                                       if len(_tr_df) else _price_final)
                        _under_final = (float(_under_tr_df['drip'].iloc[-1])
                                        if len(_under_tr_df) else float(_under_norm.iloc[-1]))

                        if _tr_mode == 'Bruto (0%)':
                            _tr_cap = ('Sin ninguna retención — lo que el fondo pagó de verdad, '
                                       'antes de cualquier impuesto.')
                        elif _tr_mode == 'Neto estimado (ROC 19a)':
                            _avg_rate = (sum(_schedule.values()) / len(_schedule) * 100.0
                                         if _schedule else _base_rate_pct)
                            _tr_cap = (f'Retiene {_base_rate_pct:.0f}% solo sobre la porción NO '
                                       f'clasificada como Retorno de Capital de cada distribución '
                                       f'— lo que suele quedar tras la reclasificación anual del '
                                       f'broker (1099-DIV/1042-S). Tasa efectiva estimada en esta '
                                       f'ventana: ~{_avg_rate:.1f}%.')
                        else:
                            _tr_cap = (f'Retención plana de {_base_rate_pct:.0f}% sobre cada '
                                       f'distribución — lo que normalmente ves al momento del '
                                       f'cobro, antes de que el broker reclasifique al cierre del '
                                       f'año fiscal.')
                        if _country:
                            _tr_cap += (f' Usa la tasa de tu país en "Proyección a futuro" '
                                        f'({_country}, {_base_rate_pct:.0f}%) en vez del 30% '
                                        f'genérico de EE.UU.')
                        elif _tr_mode != 'Bruto (0%)':
                            _tr_cap += (' Sin país configurado en "Proyección a futuro" — se usa '
                                        'el 30% general (EE.UU. sin tratado).')
                        if not _roc19a_info:
                            _tr_cap += (f' {tk} no tiene avisos 19a disponibles, así que no hay '
                                        f'escenario ROC-aware.')
                        st.markdown(
                            f'<p style="font-family:Inter,sans-serif;font-size:11px;color:#8899aa;'
                            f'margin:2px 0 10px 2px;line-height:1.5;">{_tr_cap}</p>',
                            unsafe_allow_html=True)

                        _tr_cards = [
                            ('Solo precio', f'${_price_final:.1f}', '#333333'),
                            ('Reinvirtiendo (DRIP)', f'${_drip_final:.1f}', '#006497'),
                            ('Cobrando en efectivo', f'${_cash_final:.1f}', '#006497'),
                            (f'Subyacente ({_under_tk})', f'${_under_final:.1f}', '#2d3748'),
                        ]
                        _tr_cards_html = ''.join(
                            f'<div style="flex:1;background:#ffffff;border:1px solid #e3ddd4;'
                            f'padding:10px 12px;min-width:120px;">'
                            f'<div style="font-family:Inter,sans-serif;font-size:10px;'
                            f'color:#8899aa;text-transform:uppercase;letter-spacing:0.04em;'
                            f'margin-bottom:4px;">{_lbl}</div>'
                            f'<div style="font-family:Inter,sans-serif;font-size:16px;'
                            f'font-weight:700;color:{_clr};">{_val}</div></div>'
                            for _lbl, _val, _clr in _tr_cards)
                        st.markdown(
                            f'<div style="display:flex;gap:8px;flex-wrap:wrap;'
                            f'margin:2px 0 12px 0;">{_tr_cards_html}</div>',
                            unsafe_allow_html=True)

                        # Gráfico ESTÁTICO de 4 líneas base 100 — sin on_select (bug conocido:
                        # on_select no soporta alt.layer).
                        _lbl_price = f'{tk} solo precio'
                        _lbl_drip = f'{tk} TR DRIP'
                        _lbl_cash = f'{tk} TR efectivo'
                        _lbl_under = f'{_under_tk} TR'
                        _tr_plot = pd.DataFrame({
                            'Fecha': _df.index,
                            _lbl_price: _fund_norm.values,
                            _lbl_drip: _tr_df['drip'].values,
                            _lbl_cash: _tr_df['cash'].values,
                            _lbl_under: _under_tr_df['drip'].values,
                        }).melt(id_vars='Fecha', var_name='Serie', value_name='Valor')
                        _tr_chart = alt.Chart(_tr_plot).mark_line(strokeWidth=2).encode(
                            x=alt.X('Fecha:T', title=None),
                            y=alt.Y('Valor:Q', title='Base 100'),
                            color=alt.Color(
                                'Serie:N',
                                scale=alt.Scale(
                                    domain=[_lbl_price, _lbl_drip, _lbl_cash, _lbl_under],
                                    range=['#c0392b', '#006497', '#1d9e75', '#5f5e5a']),
                                legend=alt.Legend(title=None, orient='top', labelFontSize=11)),
                            tooltip=[alt.Tooltip('Fecha:T'), alt.Tooltip('Serie:N'),
                                     alt.Tooltip('Valor:Q', format='.1f', title='Índice')]
                        ).properties(height=240, background=CHART_PALETTE['bg']).configure_view(
                            strokeOpacity=0, fill=CHART_PALETTE['bg'])
                        st.altair_chart(_tr_chart, use_container_width=True)

                        # ── Exposición asimétrica al subyacente ──
                        _exp_lines = logic.build_underlying_exposure(results, tk).get('lines', [])
                        if _exp_lines:
                            _items = ''.join(f'<li style="margin:0 0 5px 0;">{_ln}</li>'
                                              for _ln in _exp_lines)
                            st.markdown(
                                '<div style="border-left:4px solid #006497;background:#eef6fb;'
                                'padding:10px 14px;margin:0 0 10px 0;">'
                                '<ul style="font-family:Inter,sans-serif;font-size:12px;color:#333333;'
                                'line-height:1.55;margin:0;padding-left:16px;">'
                                + _items + '</ul></div>', unsafe_allow_html=True)

                        # ── Detalle técnico colapsado: escenarios, CAGR, reason, ROC 19a ──
                        _u_cagr = s.get('underlying_cagr_recent')
                        _f_cagr = s.get('price_cagr_recent')
                        _detail_html = ''
                        if _u_cagr is not None and _f_cagr is not None:
                            _flat = logic.ROC_HEALTH_NAV_FLAT_PCT
                            _tol = logic.ROC_HEALTH_REL_TOL_PCT
                            _gap = _f_cagr - _u_cagr
                            _under_falling = _u_cagr < -_flat
                            _fund_falling = _f_cagr < -_flat
                            if _under_falling and _fund_falling and _gap >= -_tol:
                                _regime = 0
                            elif _under_falling and _fund_falling:
                                _regime = 1
                            elif _fund_falling:
                                _regime = 3
                            else:
                                _regime = 2
                            _scenario_rows = [
                                ('Cae', 'Cae ~1:1', 'Riesgo de mercado — justificado, NO destrucción'),
                                ('Cae', 'Cae mucho más', 'Sobre-captura: el fondo amplifica la pérdida'),
                                ('Plano/sube', 'Sigue el ritmo', 'Contable — dentro de lo esperado'),
                                ('Plano/sube', 'Cae o no recupera',
                                 'Destructivo confirmado — no recupera (liquidó capital)'),
                            ]
                            _tr = ''
                            for _i, (_a, _b, _c) in enumerate(_scenario_rows):
                                _hi = _i == _regime
                                _st_row = ('background:#eef6fb;font-weight:700;' if _hi else 'opacity:.65;')
                                _tr += (f'<tr style="{_st_row}"><td style="padding:4px 8px;">{_a}</td>'
                                        f'<td style="padding:4px 8px;">{_b}</td>'
                                        f'<td style="padding:4px 8px;">{_c}</td></tr>')
                            _detail_html += (
                                f'<table style="width:100%;border-collapse:collapse;font-family:Inter,'
                                f'sans-serif;font-size:11.5px;color:#333;margin:8px 0 4px 0;">'
                                f'<thead><tr style="color:#8899aa;font-size:9px;text-transform:uppercase;'
                                f'letter-spacing:0.05em;"><th style="text-align:left;padding:4px 8px;">'
                                f'Subyacente</th><th style="text-align:left;padding:4px 8px;">NAV del '
                                f'fondo</th><th style="text-align:left;padding:4px 8px;">Lectura</th>'
                                f'</tr></thead><tbody>{_tr}</tbody></table>'
                                f'<p style="font-family:Inter,sans-serif;font-size:10px;color:#8899aa;'
                                f'margin:2px 0 8px 2px;">Últimos 12 meses: {_under_tk} '
                                f'{_u_cagr:+.0f}%/año vs {tk} {_f_cagr:+.0f}%/año (gap {_gap:+.0f} pts).'
                                f'</p>')
                        if _nvh:
                            _detail_html += (
                                f"<div style='font-size:12.5px;color:#333;line-height:1.5;margin:4px 0;'>"
                                f"{_nvh['reason']}</div>")
                        _roc_pct = s.get('roc_percent')
                        if _roc_pct is not None:
                            _detail_html += (
                                f'<p style="font-family:Inter,sans-serif;font-size:10px;color:#8899aa;'
                                f'margin:6px 0 4px 2px;">ROC 19a: {_roc_pct:.0f}% — etiqueta fiscal, no '
                                f'medida de destrucción.</p>')
                        if _detail_html:
                            st.markdown(
                                f"<details style='margin:2px 0 10px 0;'>"
                                f"<summary style='cursor:pointer;font-size:12px;color:#006497;'>"
                                f"Ver detalle técnico y escenarios</summary>{_detail_html}</details>",
                                unsafe_allow_html=True)

                    @st.fragment
                    def _viaje_dinero():
                        st.markdown(
                            '<p style="font-family:Inter,sans-serif;font-size:11px;font-weight:700;'
                            'color:#006497;margin:10px 0 3px 2px;letter-spacing:0.06em;">EL VIAJE DEL '
                            'DINERO <span style="color:#5a6b7a;font-weight:500;">(paso a paso, fondo '
                            'por fondo)</span></p>', unsafe_allow_html=True)
                        if hasattr(st, 'pills'):
                            _vj_tk = st.pills('Ver el viaje del dinero — elige un fondo',
                                              options=list(_vj_data.keys()),
                                              selection_mode='single',
                                              key=f'_vj_fondo_{_fid}')
                        else:
                            _vj_tk = st.radio('Ver el viaje del dinero — elige un fondo',
                                              options=['(ninguno)'] + list(_vj_data.keys()),
                                              horizontal=True, key=f'_vj_fondo_{_fid}')
                            _vj_tk = None if _vj_tk == '(ninguno)' else _vj_tk
                        if _vj_excl:
                            st.markdown(
                                f'<p style="font-family:Inter,sans-serif;font-size:11px;'
                                f'color:#445566;margin:2px 0 8px 2px;line-height:1.5;">'
                                f'{", ".join(_vj_excl)} no aparece(n) aquí porque sus '
                                f'movimientos no cuadran al centavo en el CSV — revísalo(s) '
                                f'en la tabla de abajo.</p>', unsafe_allow_html=True)
                        if not _vj_tk:
                            return
                        _d = _vj_data[_vj_tk]

                        _step_labels = ['Tu bolsillo', 'Total div. (bruto)', 'Impuesto NRA',
                                        'Reinvertidos y efectivo', 'Tu bolsillo + DRIP',
                                        'Resultado real', 'Salud del NAV']
                        if hasattr(st, 'pills'):
                            _sel = st.pills('Paso', options=_step_labels, default=_step_labels[0],
                                            selection_mode='single',
                                            key=f'_vj_{_vj_tk}_{_fid}',
                                            label_visibility='collapsed')
                            _step = _step_labels.index(_sel) if _sel in _step_labels else 0
                        else:
                            _sk = f'_vj_{_vj_tk}_{_fid}'
                            _step = int(st.session_state.get(_sk, 0))
                            _cprev, _cnext, _ = st.columns([0.2, 0.2, 0.6])
                            if _cprev.button('← Anterior', key=_sk + '_p', disabled=_step <= 0):
                                _step = max(0, _step - 1)
                            if _cnext.button('Siguiente →', key=_sk + '_n', disabled=_step >= 6):
                                _step = min(6, _step + 1)
                            st.session_state[_sk] = _step

                        if _step == 6:
                            _render_salud_nav(_vj_tk, _d, results)
                            return

                        # Micro-transiciones: keyframe único inyectado una vez por render
                        # del fragment (corre en cada cambio de paso — efecto buscado).
                        st.markdown(
                            '<style>@keyframes _vjin{from{opacity:0;'
                            'transform:translateY(4px);}to{opacity:1;transform:none;}}</style>',
                            unsafe_allow_html=True)

                        # Mini-tabla propia del stepper (no ensancha la tabla honesta).
                        _cell_idx = [0]

                        def _cell(cid, label, val, is_cur, color, sub='', dim=True):
                            _cst = ('border:2px solid #006497;background:#eef6fb;opacity:1;'
                                    if is_cur else
                                    f'border:2px solid transparent;'
                                    f'opacity:{".55" if dim else "1"};')
                            _delay = _cell_idx[0] * 45
                            _cell_idx[0] += 1
                            _anim = (f'animation:_vjin .35s cubic-bezier(0.16,1,0.3,1) both;'
                                     f'animation-delay:{_delay}ms;')
                            return (
                                f'<div style="{_cst}{_anim}padding:8px 10px;text-align:right;">'
                                f'<span style="display:block;font-family:Inter,sans-serif;font-size:8px;'
                                f'font-weight:600;letter-spacing:0.06em;text-transform:uppercase;'
                                f'color:#8899aa;margin-bottom:3px;">{label}</span>'
                                f'<span style="font-family:SFMono-Regular,ui-monospace,Menlo,Consolas,'
                                f'monospace;font-size:13px;font-weight:700;color:{color};'
                                f'letter-spacing:-0.01em;">{val}</span>{sub}</div>')

                        def _grid(cells_html, n):
                            return (f'<div style="display:grid;grid-template-columns:'
                                    f'repeat({n},minmax(96px,1fr));gap:6px;margin:8px 0 4px 0;">'
                                    f'{cells_html}</div>')

                        _no_imp = _d['imp'] <= 0.01
                        _no_drip = _d['drip'] <= 0.01
                        _cols = [('pocket', 'Tu bolsillo', _money(_d['pocket'])),
                                 ('bruto', 'Total div. (bruto)', _money(_d['bruto'])),
                                 ('imp', 'Impuesto NRA', _neg(_d['imp']))]
                        if not _no_imp:
                            _cols.append(('neto', 'Div. neto percibido', _money(_d['neto'])))
                        _cols += [('drip', 'Reinvertidos', _money(_d['drip'])),
                                  ('cash', 'En efectivo', _money(_d['cash'])),
                                  ('total', 'Tu bolsillo + DRIP', _money(_d['total']))]
                        _has_rend = _d['ret'] is not None and _d['ret_pct'] is not None

                        # ── Migas numéricas: el camino recorrido crece paso a paso ──
                        _migas_defs = [('Bolsillo', _money(_d['pocket']), False),
                                       ('Bruto', _money(_d['bruto']), False),
                                       ('Imp. NRA',
                                        ('$0.00' if _no_imp else '−' + _money(_d['imp'])),
                                        not _no_imp),
                                       ('Reinv + efvo',
                                        f"{_money(_d['drip'])} + {_money(_d['cash'])}", False),
                                       ('Capital trabajando', _money(_d['total']), False)]
                        if _has_rend:
                            _migas_defs.append(('Resultado real',
                                                f"{_money(_d['ret'])} ({_pct(_d['ret_pct'])})",
                                                (_d['ret'] or 0) < 0))
                        else:
                            _migas_defs.append(('Resultado real', '—', False))
                        _migas_html = ''
                        for _mi, (_mlb, _mvl, _mneg) in enumerate(_migas_defs[:_step + 1]):
                            _mcur = _mi == _step
                            _mvc = ('#e05c5c' if _mneg else
                                    ('#021C36' if _mcur else '#5a6b7a'))
                            _mlc = '#006497' if _mcur else '#8899aa'
                            _msep = ('<span style="color:#c3ccd4;margin:0 7px;">→</span>'
                                     if _mi else '')
                            _migas_html += (
                                f'{_msep}<span style="display:inline-block;vertical-align:top;">'
                                f'<span style="display:block;font-size:9px;font-weight:700;'
                                f'letter-spacing:0.05em;text-transform:uppercase;'
                                f'color:{_mlc};">{_mlb}</span>'
                                f'<span style="font-family:SFMono-Regular,ui-monospace,Menlo,'
                                f'Consolas,monospace;font-size:12px;font-weight:700;'
                                f'color:{_mvc};">{_mvl}</span></span>')
                        st.markdown(
                            f'<div style="font-family:Inter,sans-serif;margin:4px 0 10px 2px;'
                            f'line-height:1.3;">{_migas_html}</div>', unsafe_allow_html=True)

                        # ── Tu dinero en cuadritos — icon array, espejo visual del grid ──
                        _m = max(_d['total'], _d['bruto'], _d['mv'] + _d['cash'])
                        _u = 5000
                        for _cand in [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]:
                            if _cand == 0 or _m / _cand <= 90:
                                _u = _cand
                                break
                        _nb = lambda x: max(0, int(round(x / _u)))
                        _n_pk = _nb(_d['pocket'])
                        _n_br = _nb(_d['bruto'])
                        _n_im = _nb(_d['imp'])
                        _n_dr = _nb(_d['drip'])
                        _n_ca = _nb(_d['cash'])
                        _n_mv = _nb(_d['mv'])

                        _SQ = 'width:17px;height:17px;box-sizing:border-box;'
                        _COL_POCKET = f'{_SQ}background:#021C36;'
                        _COL_DRIP = f'{_SQ}background:#006497;'
                        _COL_TRANSITO = f'{_SQ}border:1px solid #006497;background:transparent;'
                        _COL_IMP = f'{_SQ}background:#e05c5c;'
                        _COL_CASH = f'{_SQ}background:#1f8a5b;'
                        _COL_FUNDIDO_PK = f'{_SQ}background:rgba(224,92,92,0.20);border:1px solid rgba(224,92,92,0.55);'
                        _COL_FUNDIDO_DR = f'{_SQ}background:rgba(224,92,92,0.09);border:1px solid rgba(224,92,92,0.30);'
                        _COL_TAX_STRUCK = (f'{_SQ}background:linear-gradient(to top right,'
                                           f'transparent calc(50% - 1px),#A32D2D calc(50% - 1px),'
                                           f'#A32D2D calc(50% + 1px),transparent calc(50% + 1px)),'
                                           f'rgba(224,92,92,0.20);'
                                           f'border:1px solid rgba(224,92,92,0.50);')
                        _COL_NAV_STRUCK_PK = _COL_TAX_STRUCK
                        _COL_NAV_STRUCK_DR = (f'{_SQ}background:linear-gradient(to top right,'
                                              f'transparent calc(50% - 1px),#c98b8b calc(50% - 1px),'
                                              f'#c98b8b calc(50% + 1px),transparent calc(50% + 1px)),'
                                              f'rgba(224,92,92,0.09);'
                                              f'border:1px solid rgba(224,92,92,0.30);')

                        def _blocks(n, style):
                            if n <= 0:
                                return ''
                            return f'<div style="{style}"></div>' * n

                        # ── Cuadritos agrupados en bloques semánticos etiquetados ──
                        _clusters = []
                        _pocket_amt = _money(_d['pocket'])
                        if _step == 0:
                            _clusters.append({'label': 'Tu bolsillo', 'amount': _pocket_amt,
                                              'sub': '', 'segs': [(_n_pk, _COL_POCKET)], 'ref': True})
                        elif _step == 1:
                            _clusters.append({'label': 'Tu bolsillo', 'amount': _pocket_amt,
                                              'sub': '', 'segs': [(_n_pk, _COL_POCKET)], 'ref': True})
                            _clusters.append({'label': 'Dividendos brutos', 'amount': _money(_d['bruto']),
                                              'sub': '', 'segs': [(_n_br, _COL_TRANSITO)], 'ref': False})
                        elif _step == 2:
                            _clusters.append({'label': 'Tu bolsillo', 'amount': _pocket_amt,
                                              'sub': '', 'segs': [(_n_pk, _COL_POCKET)], 'ref': True})
                            if _no_imp:
                                _clusters.append({'label': 'Dividendos brutos', 'amount': _money(_d['bruto']),
                                                  'sub': '', 'segs': [(_n_br, _COL_TRANSITO)], 'ref': False})
                            else:
                                _n_transito = max(0, _n_br - _n_im)
                                _clusters.append({'label': 'Dividendos brutos', 'amount': _money(_d['bruto']),
                                                  'sub': (f'El fisco cobra {_money(_d["imp"])} · te quedan {_money(_d["neto"])} (div. neto percibido)'
                                                          if _n_im > 0 else ''),
                                                  'segs': [(_n_im, _COL_TAX_STRUCK), (_n_transito, _COL_TRANSITO)],
                                                  'ref': False})
                        elif _step in (3, 4):
                            _clusters.append({'label': 'Tu bolsillo', 'amount': _pocket_amt,
                                              'sub': '', 'segs': [(_n_pk, _COL_POCKET)], 'ref': True})
                            if not _no_drip:
                                _clusters.append({'label': 'DRIP', 'amount': _money(_d['drip']),
                                                  'sub': '', 'segs': [(_n_dr, _COL_DRIP)], 'ref': False})
                            if _n_ca > 0:
                                _clusters.append({'label': 'Efectivo', 'amount': _money(_d['cash']),
                                                  'sub': '', 'segs': [(_n_ca, _COL_CASH)], 'ref': False})
                        else:  # _step == 5
                            _n_capital = _n_pk + _n_dr
                            if _n_mv >= _n_capital:
                                _pk_alive, _dr_alive = _n_pk, _n_dr
                                _pk_dead, _dr_dead = 0, 0
                                _n_extra = _n_mv - _n_capital
                            else:
                                _frac = (_n_mv / _n_capital) if _n_capital > 0 else 0
                                _pk_alive = int(round(_n_pk * _frac))
                                _dr_alive = int(round(_n_dr * _frac))
                                _pk_dead = _n_pk - _pk_alive
                                _dr_dead = _n_dr - _dr_alive
                                _n_extra = 0
                            _clusters.append({'label': 'Tu bolsillo', 'amount': _pocket_amt,
                                              'sub': (f'{_pk_alive} vivos · {_pk_dead} destruidos'
                                                      if _pk_dead > 0 else f'{_pk_alive} vivos'),
                                              'segs': [(_pk_alive, _COL_POCKET), (_pk_dead, _COL_NAV_STRUCK_PK)],
                                              'ref': True})
                            if _n_dr > 0:
                                _clusters.append({'label': 'DRIP', 'amount': _money(_d['drip']),
                                                  'sub': (f'{_dr_alive} vivos · {_dr_dead} destruidos'
                                                          if _dr_dead > 0 else f'{_dr_alive} vivos'),
                                                  'segs': [(_dr_alive, _COL_DRIP), (_dr_dead, _COL_NAV_STRUCK_DR)],
                                                  'ref': False})
                            if _n_extra > 0:
                                _clusters.append({'label': 'Apreciación', 'amount': '',
                                                  'sub': '', 'segs': [(_n_extra, _COL_CASH)], 'ref': False})
                            if _n_ca > 0:
                                _clusters.append({'label': 'Efectivo', 'amount': _money(_d['cash']),
                                                  'sub': '', 'segs': [(_n_ca, _COL_CASH)], 'ref': False})

                        # Leyenda derivada de los estilos realmente usados.
                        _LEGEND = {
                            _COL_POCKET: ('#021C36', 'tu bolsillo'),
                            _COL_DRIP: ('#006497', 'DRIP'),
                            _COL_TRANSITO: ('#006497 (borde)', 'dividendos en tránsito'),
                            _COL_IMP: ('#e05c5c', 'impuesto NRA'),
                            _COL_CASH: ('#1f8a5b', 'efectivo'),
                            _COL_FUNDIDO_PK: ('#cf5b5b (borde)', 'bolsillo destruido'),
                            _COL_FUNDIDO_DR: ('#e6a6a6 (borde)', 'DRIP destruido'),
                            _COL_TAX_STRUCK: ('#A32D2D (tachado)', 'destruido / impuesto'),
                            _COL_NAV_STRUCK_DR: ('#c98b8b (tachado)', 'DRIP destruido'),
                        }
                        _legend_bits = []
                        _seen_style = set()
                        for _c in _clusters:
                            for _n, _style in _c['segs']:
                                if _n > 0 and _style not in _seen_style and _style in _LEGEND:
                                    _seen_style.add(_style)
                                    _legend_bits.append(_LEGEND[_style])

                        _seen_leg = set()
                        _legend_html = ''
                        for _lcol, _ltxt in _legend_bits:
                            if _ltxt in _seen_leg:
                                continue
                            _seen_leg.add(_ltxt)
                            if '(tachado)' in _lcol:
                                _lglyph = '⊠'
                            elif '(borde)' in _lcol:
                                _lglyph = '□'
                            else:
                                _lglyph = '■'
                            _legend_html += (f'<span style="color:{_lcol.split(" ")[0]};">'
                                             f'{_lglyph}</span>&nbsp;{_ltxt}&nbsp;&nbsp;')
                        _u_str = f'${_u:,}' if _u >= 1000 else f'${_u}'

                        def _cluster_html(c):
                            inner = ''.join(_blocks(n, style) for n, style in c['segs'])
                            total = sum(n for n, _ in c['segs'])
                            border = '2px solid #445566' if c.get('ref') else '1px solid #d9dee3'
                            _amt = f' · {c["amount"]}' if c['amount'] else ''
                            head = (f'<div style="font-family:Inter,sans-serif;font-size:9px;'
                                    f'font-weight:700;letter-spacing:0.04em;text-transform:uppercase;'
                                    f'color:#8899aa;margin-bottom:3px;white-space:nowrap;">'
                                    f'{c["label"]}{_amt} · {total}</div>')
                            sub = (f'<div style="font-family:Inter,sans-serif;font-size:10px;'
                                   f'color:#8899aa;margin-top:4px;">{c["sub"]}</div>'
                                   if c.get('sub') else '')
                            return (f'<div style="min-width:0;">{head}'
                                    f'<div style="border-top:{border};padding-top:5px;">'
                                    f'<div style="display:flex;flex-wrap:wrap;gap:4px;'
                                    f'max-width:480px;">{inner}</div></div>{sub}</div>')

                        _row = ''.join(_cluster_html(c) for c in _clusters
                                       if sum(n for n, _ in c['segs']) > 0)

                        # Supervivencia por cada $100 invertidos (solo Resultado real) — integrada bajo los cuadros.
                        _surv_cap = ''
                        if _step == 5 and _d.get('total', 0) and _d['total'] > 0:
                            _work = _d['total']
                            _av = max(0.0, _d['mv'] / _work)
                            _cash_u = int(round(_d['cash'] / _work * 100))
                            if _av >= 1:
                                _gain_u = int(round((_av - 1) * 100))
                                _surv_cap = 'De cada $100 invertidos, los 100 siguen vivos'
                                if _gain_u > 0:
                                    _surv_cap += f' · +{_gain_u} de ganancia'
                            else:
                                _alive_u = int(round(_av * 100))
                                _dead_u = 100 - _alive_u
                                _surv_cap = (f'De cada $100 invertidos, {_alive_u} siguen vivos '
                                             f'y {_dead_u} se destruyeron')
                            if _d['cash'] > 0.01:
                                _surv_cap += f' · +{_cash_u} ya en efectivo'
                        st.markdown(
                            f'<div style="animation:_vjin .35s cubic-bezier(0.16,1,0.3,1) both;'
                            f'display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start;'
                            f'margin:6px 0 2px 0;min-height:34px;">{_row}</div>',
                            unsafe_allow_html=True)
                        if _surv_cap:
                            st.markdown(
                                f'<p style="font-family:Inter,sans-serif;font-size:11px;'
                                f'font-weight:600;color:#556677;margin:3px 0 2px 2px;">{_surv_cap}</p>',
                                unsafe_allow_html=True)
                        if _legend_html:
                            st.markdown(
                                f'<p style="font-family:Inter,sans-serif;font-size:10px;'
                                f'color:#8899aa;margin:4px 0 2px 2px;">cada cuadrito ≈ {_u_str}'
                                f'&nbsp;&nbsp;·&nbsp;&nbsp;{_legend_html}</p>',
                                unsafe_allow_html=True)

                        # Narrativa: callout del paso actual; el camino previo va plegado.
                        # Adaptativas: sin retención (imp≈0) y sin reinversión (drip≈0).
                        if _no_imp:
                            _n2 = (f'En este archivo no aparece retención de impuesto para '
                                   f'{_vj_tk}. Si eres inversionista extranjero (NRA), '
                                   f'normalmente EE.UU. retiene ~30% de cada dividendo — revisa '
                                   f'tu 1042-S. Aquí el dividendo pasó completo: '
                                   f'<b>{_money(_d["neto"])}</b>. En algunas cuentas (p. ej. '
                                   f'Interactive Brokers) la retención ya viene plegada dentro '
                                   f'del dividendo neto que reportamos, así que no aparece '
                                   f'aparte.')
                        else:
                            _n2 = (f'Por ser inversionista extranjero se retiene automáticamente '
                                   f'~30% de impuesto NRA (<b>{_neg(_d["imp"])}</b>). Te quedan '
                                   f'<b>{_money(_d["neto"])}</b> libres: tu <b>dividendo neto '
                                   f'percibido</b> — el dinero que ya es tuyo y de donde sale todo '
                                   f'lo demás. Ojo: es neto <i>en origen</i>; los impuestos de tu '
                                   f'país de residencia, si aplican, van aparte. Parte de esta '
                                   f'retención puede volver con la reclasificación anual del broker '
                                   f'si la distribución se cataloga como Retorno de Capital (ROC) — '
                                   f'ver el módulo fiscal NRA.')
                        if _no_drip:
                            _n3 = (f'Tus dividendos limpios se fueron completos a tu cuenta en '
                                   f'efectivo (<b>{_money(_d["cash"])}</b>) — en esta cuenta no '
                                   f'hay reinversión automática (DRIP).')
                            _n4 = (f'Sin reinversión, tu capital en {_vj_tk} sigue siendo tus '
                                   f'<b>{_money(_d["pocket"])}</b> originales; tus dividendos '
                                   f'(<b>{_money(_d["cash"])}</b>) están aparte, en efectivo.')
                        else:
                            _n3 = (f'De tu neto percibido, <b>{_money(_d["cash"])}</b> se '
                                   f'fueron a tu cuenta en efectivo (listos para retirar) y '
                                   f'<b>{_money(_d["drip"])}</b> compraron más acciones '
                                   f'automáticamente (DRIP).')
                            _n4 = (f'Tus <b>{_money(_d["pocket"])}</b> iniciales + los '
                                   f'<b>{_money(_d["drip"])}</b> que tu propio dinero generó y '
                                   f'reinvirtió (DRIP) = <b>{_money(_d["total"])}</b> de capital '
                                   f'trabajando en {_vj_tk}.')
                        if _no_imp:
                            _n1 = (f'{_vj_tk} generó <b>{_money(_d["bruto"])}</b> en dividendos '
                                   f'brutos por tus acciones. Veamos qué pasó con ellos en el '
                                   f'camino a tu cuenta…')
                        else:
                            _n1 = (f'{_vj_tk} generó <b>{_money(_d["bruto"])}</b> en dividendos '
                                   f'brutos por tus acciones. Pero antes de que lleguen a ti, el '
                                   f'gobierno de EE.UU. toma una parte…')
                        _ret_paren = f' ({_pct(_d["ret_pct"])})' if _d['ret_pct'] is not None else ''
                        _mkt = _d['mv'] - _d['total']
                        _mkt_neg_str = _money(-_mkt) if _mkt < 0 else ''
                        _mkt_pos_str = ('+' if _mkt >= 0 else '') + _money(_mkt)
                        _cat = _d['mv'] + _d['cash']
                        if _mkt < 0 and not _no_drip:
                            _n5 = (f'Aunque tu capital trabajando llegó a {_money(_d["total"])} '
                                   f'gracias al DRIP, el precio de {_vj_tk} cayó '
                                   f'(<b>−{_mkt_neg_str}</b> de impacto del mercado). Sumando el '
                                   f'valor actual de tus acciones ({_money(_d["mv"])}) más tu '
                                   f'dinero disponible en efectivo ({_money(_d["cash"])}), tu '
                                   f'<b>capital actual total</b> es {_money(_cat)}. Frente a los '
                                   f'{_money(_d["pocket"])} que pusiste de tu bolsillo, tu '
                                   f'resultado real es '
                                   f'<b>{_money(_d["ret"])}{_ret_paren}</b> — el mismo retorno '
                                   f'total de la portada.')
                        elif _mkt >= 0 and not _no_drip:
                            _n5 = (f'Tu capital trabajando de {_money(_d["total"])} además se '
                                   f'apreció (<b>{_mkt_pos_str}</b> de impacto del mercado). '
                                   f'Sumando el valor actual de tus acciones '
                                   f'({_money(_d["mv"])}) más tu dinero disponible en efectivo '
                                   f'({_money(_d["cash"])}), tu <b>capital actual total</b> es '
                                   f'{_money(_cat)}. Frente a los {_money(_d["pocket"])} que '
                                   f'pusiste de tu bolsillo, tu resultado real es '
                                   f'<b>{_money(_d["ret"])}{_ret_paren}</b> — el mismo retorno '
                                   f'total de la portada.')
                        elif _mkt < 0 and _no_drip:
                            _n5 = (f'Tus {_money(_d["pocket"])} cayeron con el precio de '
                                   f'{_vj_tk} (<b>−{_mkt_neg_str}</b> de impacto del mercado). '
                                   f'Sumando el valor actual de tus acciones '
                                   f'({_money(_d["mv"])}) más tu dinero disponible en efectivo, '
                                   f'aparte ({_money(_d["cash"])}), tu <b>capital actual '
                                   f'total</b> es {_money(_cat)}. Frente a los '
                                   f'{_money(_d["pocket"])} que pusiste de tu bolsillo, tu '
                                   f'resultado real es '
                                   f'<b>{_money(_d["ret"])}{_ret_paren}</b> — el mismo retorno '
                                   f'total de la portada.')
                        else:
                            _n5 = (f'Tus {_money(_d["pocket"])} además se apreciaron '
                                   f'(<b>{_mkt_pos_str}</b> de impacto del mercado). Sumando el '
                                   f'valor actual de tus acciones ({_money(_d["mv"])}) más tu '
                                   f'dinero disponible en efectivo, aparte '
                                   f'({_money(_d["cash"])}), tu <b>capital actual total</b> es '
                                   f'{_money(_cat)}. Frente a los {_money(_d["pocket"])} que '
                                   f'pusiste de tu bolsillo, tu resultado real es '
                                   f'<b>{_money(_d["ret"])}{_ret_paren}</b> — el mismo retorno '
                                   f'total de la portada.')
                        _narr = [
                            f'Este es el capital neto que pusiste de tu propio dinero para '
                            f'comprar {_vj_tk}.',
                            _n1,
                            _n2,
                            _n3,
                            _n4,
                            _n5,
                        ]
                        _cur_html = _narr[_step]
                        if _step == 4:
                            if _no_drip:
                                _honesty = 'La ganancia real está en el siguiente paso →'
                            else:
                                _honesty = (f'Ojo: {_money(_d["total"])} es <b>capital '
                                            f'invertido</b>, no ganancia. La ganancia real está '
                                            f'en el siguiente paso →')
                            _cur_html += (f'<span style="display:block;font-size:11px;'
                                          f'color:#445566;margin-top:6px;">{_honesty}</span>')
                        _nhtml = (f'<div style="border-left:3px solid #006497;background:#eef6fb;'
                                  f'padding:10px 14px;font-family:Inter,sans-serif;'
                                  f'font-size:12.5px;color:#021C36;line-height:1.6;'
                                  f'animation:_vjin .35s cubic-bezier(0.16,1,0.3,1) both;">'
                                  f'{_cur_html}</div>')
                        if _step > 0:
                            _prev = ''.join(
                                f'<p style="font-family:Inter,sans-serif;font-size:12px;'
                                f'color:#4a5568;line-height:1.55;margin:6px 0 3px 0;'
                                f'opacity:.75;">{_narr[_ni]}</p>' for _ni in range(_step))
                            _plural = 's' if _step > 1 else ''
                            _nhtml += (f'<details style="margin:6px 0 0 0;">'
                                       f'<summary style="cursor:pointer;font-family:Inter,'
                                       f'sans-serif;font-size:11.5px;color:#006497;">Ver el '
                                       f'camino recorrido ({_step} paso{_plural})</summary>'
                                       f'{_prev}</details>')
                        st.markdown(f'<div style="margin:8px 0 10px 2px;">{_nhtml}</div>',
                                    unsafe_allow_html=True)

                        # ── ¿Cuánto de este impuesto puede volver? — el escudo del ROC ──
                        if _step == 2 and not _no_imp:
                            _roc_pct_nra = (results.get(_vj_tk) or {}).get('roc_percent')
                            if _roc_pct_nra is not None:
                                _country_sel2 = st.session_state.get('proj_country')
                                _country2 = (_country_sel2 if _country_sel2
                                             in logic.NRA_COUNTRY_RATES else None)
                                _base_rate_pct2 = (logic.NRA_COUNTRY_RATES[_country2][0]
                                                    if _country2 else logic.NRA_DEFAULT_RATE)
                                _refund_info = logic.estimate_roc_refund(
                                    _d['bruto'], _d['imp'], _roc_pct_nra,
                                    base_rate=_base_rate_pct2 / 100.0)
                                _roc_lbl = f'ROC {_roc_pct_nra:.0f}%'
                                _gby = (results.get(_vj_tk) or {}).get(
                                    'dividends_gross_by_year') or {}
                                _wby = (results.get(_vj_tk) or {}).get(
                                    'withheld_by_year') or {}
                                _years_wh = sorted(y for y, v in _wby.items() if v > 0.01)
                                _obs_by_year = (results.get(_vj_tk) or {}).get(
                                    'tax_refund_observed_by_year') or {}
                                _obs_total = round(sum(_obs_by_year.values()), 2)
                                _refund_by_year = None
                                if len(_years_wh) > 1:
                                    _refund_by_year = logic.estimate_roc_refund_by_year(
                                        _gby, _wby, _vj_tk, base_rate=_base_rate_pct2 / 100.0,
                                        roc_fallback_pct=_roc_pct_nra)
                                    _rby_total = (_refund_by_year or {}).get('total')
                                    if _rby_total:
                                        # Tarjetas y tabla anual deben sumar igual: el total
                                        # sale del ROC de cada año, no del agregado.
                                        _refund_info = _rby_total
                                        _roc_lbl = 'ROC por año'
                                st.markdown(
                                    '<p style="font-family:Inter,sans-serif;font-size:11px;'
                                    'font-weight:700;color:#006497;margin:12px 0 3px 2px;'
                                    'letter-spacing:0.06em;">¿CUÁNTO DE ESTE IMPUESTO PUEDE '
                                    'VOLVER? — EL ESCUDO DEL ROC</p>', unsafe_allow_html=True)
                                _rf_cards = [
                                    ('Retenido real', _money(_d['imp']), '#8f2318',
                                     '1px solid #e3ddd4'),
                                    (f'Retención justa ({_roc_lbl})',
                                     _money(_refund_info['fair_withholding']), '#333333',
                                     '1px solid #e3ddd4'),
                                    ('Devolución estimada',
                                     f"{_money(_refund_info['refund'])} "
                                     f"({_refund_info['refund_pct']:.0f}%)", '#1d9e75',
                                     '2px solid #1d9e75'),
                                ]
                                _rf_html = ''.join(
                                    f'<div style="flex:1;background:#ffffff;border:{_bd};'
                                    f'padding:10px 12px;min-width:130px;">'
                                    f'<div style="font-family:Inter,sans-serif;font-size:10px;'
                                    f'color:#8899aa;text-transform:uppercase;'
                                    f'letter-spacing:0.04em;margin-bottom:4px;">{_lbl}</div>'
                                    f'<div style="font-family:Inter,sans-serif;font-size:16px;'
                                    f'font-weight:700;color:{_clr};">{_val}</div></div>'
                                    for _lbl, _val, _clr, _bd in _rf_cards)
                                st.markdown(
                                    f'<div style="display:flex;gap:8px;flex-wrap:wrap;'
                                    f'margin:2px 0 8px 0;">{_rf_html}</div>',
                                    unsafe_allow_html=True)
                                # Stepper de 3 niveles de certeza de la devolución del ROC:
                                # Estimado (19a) → Oficial (1042-S, lo teclea el usuario) →
                                # Efectivo (crédito real detectado en el CSV). Misma fórmula en los
                                # tres; sube la calidad del dato. El 1042-S se lee de session_state
                                # (lo escribe el number_input de abajo en el render previo).
                                _official_1042s = float(st.session_state.get(
                                    f'roc_1042s_{_vj_tk}', 0.0) or 0.0)
                                _est_ref = _refund_info['refund']
                                _lvl2_done = _official_1042s > 0.01
                                _lvl3_done = _obs_total > 0.01
                                _n_done = 1 + int(_lvl2_done) + int(_lvl3_done)
                                if _lvl3_done:
                                    _ref_base = _official_1042s if _lvl2_done else _est_ref
                                    _pend3 = max(0.0, _ref_base - _obs_total)
                                    _l3_status = ('✓ Ya se te devolvió.' +
                                                  (f' Faltarían ~{_money(_pend3)}.' if _pend3 > 0.01
                                                   else ' Ciclo completo.'))
                                else:
                                    _l3_status = ('Pendiente. Schwab: jun–sep (3–6 meses tras el '
                                                  '1042-S) · IB: ene–mar. Si no llega, reclámalo '
                                                  'con el 1040-NR.')
                                _levels = [
                                    {'tag': 'Nivel 1 · Estimado', 'done': True, 'accent': '#006497',
                                     'amount': _money(_est_ref), 'note': 'aprox. · avisos 19a',
                                     'desc': 'La app lo calcula con el %ROC provisional del fondo. '
                                             'Es una cota conservadora.',
                                     'status': '✓ Disponible ahora. Falta tu número oficial '
                                               '(1042-S, ~mediados de marzo).',
                                     'sbg': '#eef4f8', 'sfg': '#006497', 'conn': 'solid'},
                                    {'tag': 'Nivel 2 · Oficial', 'done': _lvl2_done, 'accent': '#006497',
                                     'amount': _money(_official_1042s) if _lvl2_done else '—',
                                     'note': '· 1042-S, casilla 10' if _lvl2_done else 'por completar',
                                     'desc': 'El número final que el IRS reconoce que te deben, '
                                             'sin estimar.',
                                     'status': ('✓ Lo tienes. Falta que el dinero se acredite en tu '
                                                'cuenta.' if _lvl2_done else 'Ingresa el crédito de '
                                                'tu 1042-S (casilla 10) en el campo de abajo.'),
                                     'sbg': '#eef4f8' if _lvl2_done else '#f4f2ee',
                                     'sfg': '#006497' if _lvl2_done else '#6b7683', 'conn': 'dashed'},
                                    {'tag': 'Nivel 3 · Efectivo devuelto', 'done': _lvl3_done,
                                     'accent': '#1d9e75' if _lvl3_done else '#c9821f',
                                     'amount': _money(_obs_total) if _lvl3_done else '$0',
                                     'note': '· acreditado' if _lvl3_done else 'hasta hoy',
                                     'desc': 'El reembolso real depositado en tu cuenta. Cierra el '
                                             'ciclo y confirma que el bróker pagó.',
                                     'status': _l3_status,
                                     'sbg': '#eaf7f1' if _lvl3_done else '#fbf6ea',
                                     'sfg': '#1d9e75' if _lvl3_done else '#a06a1a', 'conn': None},
                                ]
                                _steps_html = ''
                                for _lv in _levels:
                                    if _lv['done']:
                                        _node = (f'<div style="width:26px;height:26px;'
                                                 f'background:{_lv["accent"]};color:#fff;display:flex;'
                                                 f'align-items:center;justify-content:center;'
                                                 f'font-size:14px;">✓</div>')
                                    else:
                                        _node = (f'<div style="width:26px;height:26px;'
                                                 f'background:transparent;border:2px solid '
                                                 f'{_lv["accent"]};color:{_lv["accent"]};'
                                                 f'display:flex;align-items:center;'
                                                 f'justify-content:center;font-size:13px;">○</div>')
                                    _conn = ''
                                    if _lv['conn']:
                                        _cstyle = '#006497' if _lv['conn'] == 'solid' else '#c9cfd6'
                                        _conn = (f'<div style="width:2px;flex:1;min-height:22px;'
                                                 f'background:{_cstyle};"></div>')
                                    _steps_html += (
                                        f'<div style="display:flex;gap:12px;">'
                                        f'<div style="display:flex;flex-direction:column;'
                                        f'align-items:center;">{_node}{_conn}</div>'
                                        f'<div style="flex:1;padding-bottom:14px;">'
                                        f'<div style="font-family:Inter,sans-serif;font-size:10px;'
                                        f'color:{_lv["accent"]};font-weight:700;'
                                        f'letter-spacing:0.05em;text-transform:uppercase;">'
                                        f'{_lv["tag"]}</div>'
                                        f'<div style="font-family:Inter,sans-serif;font-size:18px;'
                                        f'font-weight:700;color:#0F172A;margin:1px 0;">'
                                        f'{_lv["amount"]} <span style="font-size:11px;color:#8899aa;'
                                        f'font-weight:400;">{_lv["note"]}</span></div>'
                                        f'<div style="font-family:Inter,sans-serif;font-size:12px;'
                                        f'color:#6b7683;line-height:1.5;margin:1px 0 5px;">'
                                        f'{_lv["desc"]}</div>'
                                        f'<div style="font-family:Inter,sans-serif;font-size:11.5px;'
                                        f'color:{_lv["sfg"]};background:{_lv["sbg"]};padding:5px 9px;'
                                        f'line-height:1.45;">{_lv["status"]}</div></div></div>')
                                st.markdown(
                                    f'<div style="margin:4px 0 4px 0;"><div style="display:flex;'
                                    f'justify-content:space-between;align-items:baseline;'
                                    f'margin-bottom:8px;"><span style="font-family:Inter,sans-serif;'
                                    f'font-size:11px;font-weight:700;color:#006497;'
                                    f'letter-spacing:0.05em;">TU DEVOLUCIÓN: 3 NIVELES DE '
                                    f'CERTEZA</span><span style="font-family:Inter,sans-serif;'
                                    f'font-size:11px;color:#8899aa;">{_n_done} de 3</span></div>'
                                    f'{_steps_html}</div>', unsafe_allow_html=True)
                                _roc_pdf = st.file_uploader(
                                    'Sube tu 1042-S (PDF) y lo leemos por ti',
                                    type=['pdf'], key=f'roc_1042s_pdf_{_vj_tk}')
                                st.caption(
                                    'El PDF no se guarda: se procesa de forma transitoria con '
                                    'Gemini (Google) solo para leer el número y luego se descarta.')
                                if _roc_pdf is not None:
                                    _roc_pdf_sig = (_roc_pdf.name, _roc_pdf.size)
                                    _roc_pdf_cache_key = f'_roc_pdf_extract_{_vj_tk}'
                                    if st.session_state.get(f'{_roc_pdf_cache_key}_sig') != _roc_pdf_sig:
                                        _gem_key_pdf = _get_gemini_key()
                                        with st.spinner('Leyendo tu 1042-S…'):
                                            _roc_pdf_result = logic.extract_roc_credit_from_pdf(
                                                _roc_pdf.getvalue(), _gem_key_pdf)
                                        st.session_state[_roc_pdf_cache_key] = _roc_pdf_result
                                        st.session_state[f'{_roc_pdf_cache_key}_sig'] = _roc_pdf_sig
                                        st.session_state.pop(f'{_roc_pdf_cache_key}_confirmed', None)
                                    _roc_pdf_result = st.session_state.get(_roc_pdf_cache_key)
                                    _roc_pdf_confirmed = st.session_state.get(
                                        f'{_roc_pdf_cache_key}_confirmed')
                                    if _roc_pdf_result is None:
                                        st.warning(
                                            'No pudimos procesar el PDF en este momento — '
                                            'intenta de nuevo en unos minutos o teclea el '
                                            'valor manualmente abajo.')
                                    elif not _roc_pdf_result.get('per_form'):
                                        st.warning(
                                            'No encontré un crédito ROC (código 37) en ese PDF — '
                                            'verifica que sea tu 1042-S o teclea el valor manualmente.')
                                    elif _roc_pdf_confirmed:
                                        _roc_manual_now = float(
                                            st.session_state.get(f'roc_1042s_{_vj_tk}', 0.0) or 0.0)
                                        if abs(_roc_manual_now - _roc_pdf_result['credit']) < 0.005:
                                            st.success(
                                                f'Crédito {_money(_roc_pdf_result["credit"])} '
                                                f'tomado de tu 1042-S y aplicado al campo de abajo.')
                                    else:
                                        st.markdown(
                                            f'Leí en tu 1042-S: crédito ROC '
                                            f'**{_money(_roc_pdf_result["credit"])}** '
                                            f'(sobre {_money(_roc_pdf_result["roc_gross"])} brutos '
                                            f'código 37) — ¿es correcto?')
                                        _cc1, _cc2 = st.columns(2)
                                        with _cc1:
                                            if st.button('Confirmar', type='primary',
                                                         key=f'_roc_pdf_ok_{_vj_tk}'):
                                                st.session_state[f'roc_1042s_{_vj_tk}'] = \
                                                    _roc_pdf_result['credit']
                                                st.session_state[f'{_roc_pdf_cache_key}_confirmed'] = True
                                                st.rerun()
                                        with _cc2:
                                            if st.button('Corregir', key=f'_roc_pdf_no_{_vj_tk}'):
                                                st.session_state.pop(_roc_pdf_cache_key, None)
                                                st.session_state.pop(f'{_roc_pdf_cache_key}_sig', None)
                                                st.rerun()
                                st.number_input(
                                    '…o ingresa manualmente el crédito de la casilla 10 '
                                    '(código 37 · ROC) para ver tu número exacto:',
                                    min_value=0.0, step=1.0, key=f'roc_1042s_{_vj_tk}',
                                    format='%.2f')
                                # Desglose por año calendario: la reclasificación del broker
                                # opera por año fiscal, no sobre el acumulado.
                                if _refund_by_year is not None:
                                    _cur_year = datetime.date.today().year
                                    _yr_rows = ''
                                    for _y in _years_wh:
                                        _yinfo = _refund_by_year.get(_y, {})
                                        _obs_y = _obs_by_year.get(_y, 0.0)
                                        if _obs_y > 0.01:
                                            _estado = f'✓ devuelto {_money(_obs_y)}'
                                        elif _y >= _cur_year:
                                            _estado = 'aún no; vuelve tras el 1042-S'
                                        else:
                                            _estado = 'pendiente — verifícalo en tu 1042-S / 1040-NR'
                                        _yr_rows += (
                                            f'<tr><td style="padding:4px 8px;">{_y}</td>'
                                            f'<td style="padding:4px 8px;text-align:right;">'
                                            f'{_money(_wby.get(_y, 0.0))}</td>'
                                            f'<td style="padding:4px 8px;text-align:right;'
                                            f'color:#1d9e75;">'
                                            f'{_money(_yinfo.get("refund", 0.0))}</td>'
                                            f'<td style="padding:4px 8px;font-size:11px;'
                                            f'color:#6b7683;">{_estado}</td></tr>')
                                    st.markdown(
                                        '<table style="width:100%;border-collapse:collapse;'
                                        'font-family:Inter,sans-serif;font-size:12px;'
                                        'color:#0F172A;margin:2px 0 8px 0;">'
                                        '<tr style="border-bottom:1px solid #e3ddd4;'
                                        'font-size:10px;color:#8899aa;'
                                        'text-transform:uppercase;">'
                                        '<td style="padding:4px 8px;">Año</td>'
                                        '<td style="padding:4px 8px;text-align:right;">'
                                        'Retenido</td>'
                                        '<td style="padding:4px 8px;text-align:right;">'
                                        'Devolución estimada</td>'
                                        '<td style="padding:4px 8px;">Estado</td></tr>'
                                        f'{_yr_rows}</table>', unsafe_allow_html=True)
                                if _refund_info['refund'] > 0.01 and _n_im > 0:
                                    _m_destach = min(
                                        _n_im,
                                        round(_n_im * _refund_info['refund_pct'] / 100.0))
                                    st.markdown(
                                        f'<p style="font-family:Inter,sans-serif;font-size:12px;'
                                        f'color:#6b7683;margin:0 0 4px 2px;line-height:1.5;">De '
                                        f'los ~{_n_im} cuadritos tachados arriba, ~{_m_destach} '
                                        f'deberían destacharse: esa parte del impuesto no debió '
                                        f'quedarse retenida.</p>', unsafe_allow_html=True)
                                st.markdown(
                                    '<p style="font-family:Inter,sans-serif;font-size:11px;'
                                    'color:#8899aa;margin:2px 0 10px 2px;line-height:1.5;">'
                                    'Estimación con el % ROC de tus distribuciones (avisos 19a); lo '
                                    'definitivo lo fija tu 1042-S. El % ROC real de un mal año suele '
                                    'ser mayor que el promedio 19a, así que esta cifra tiende a '
                                    'quedarse corta (conservadora).</p>',
                                    unsafe_allow_html=True)

                        st.markdown(
                            '<p style="font-family:Inter,sans-serif;font-size:8px;'
                            'font-weight:600;letter-spacing:0.06em;text-transform:uppercase;'
                            'color:#8899aa;margin:10px 0 2px 2px;">LOS NÚMEROS DETRÁS DEL '
                            'DIBUJO</p>', unsafe_allow_html=True)
                        if _step != 5:
                            if _no_imp:
                                _visible = {0: ['pocket'],
                                            1: ['pocket', 'bruto'],
                                            2: ['pocket', 'bruto', 'imp'],
                                            3: ['pocket', 'bruto', 'imp', 'drip', 'cash'],
                                            4: ['pocket', 'bruto', 'imp', 'drip', 'cash',
                                                'total']}[_step]
                            else:
                                _visible = {0: ['pocket'],
                                            1: ['pocket', 'bruto'],
                                            2: ['pocket', 'bruto', 'imp', 'neto'],
                                            3: ['pocket', 'bruto', 'imp', 'neto', 'drip', 'cash'],
                                            4: ['pocket', 'bruto', 'imp', 'neto', 'drip', 'cash',
                                                'total']}[_step]
                            _current = {0: {'pocket'}, 1: {'bruto'}, 2: {'imp', 'neto'},
                                        3: {'drip', 'cash'}, 4: {'pocket', 'total'}}[_step]
                            _vcells = ''
                            for _cid, _clabel, _cval in _cols:
                                if _cid not in _visible:
                                    continue
                                _is_cur = _cid in _current
                                _vcol = '#cc6a6a' if _cid == 'imp' else '#0F172A'
                                _vcells += _cell(_cid, _clabel, _cval, _is_cur, _vcol)
                            st.markdown(_grid(_vcells, len(_visible)), unsafe_allow_html=True)
                        else:
                            st.markdown(
                                '<p style="font-family:Inter,sans-serif;font-size:8px;'
                                'font-weight:600;letter-spacing:0.06em;text-transform:uppercase;'
                                'color:#8899aa;margin:0 0 2px 2px;">EL FLUJO DEL DIVIDENDO</p>',
                                unsafe_allow_html=True)
                            _flow_cells = ''
                            for _cid, _clabel, _cval in _cols:
                                _vcol = '#cc6a6a' if _cid == 'imp' else '#0F172A'
                                _flow_cells += _cell(_cid, _clabel, _cval, False, _vcol)
                            st.markdown(_grid(_flow_cells, len(_cols)), unsafe_allow_html=True)

                            st.markdown(
                                '<p style="font-family:Inter,sans-serif;font-size:8px;'
                                'font-weight:600;letter-spacing:0.06em;text-transform:uppercase;'
                                'color:#8899aa;margin:8px 0 2px 2px;">EL IMPACTO DEL MERCADO</p>',
                                unsafe_allow_html=True)
                            _mkt = _d['mv'] - _d['total']
                            _mkt_str = ('+' if _mkt >= 0 else '') + _money(_mkt)
                            _mkt_col = '#1f8a5b' if _mkt >= 0 else '#e05c5c'
                            _cat = _d['mv'] + _d['cash']
                            _mkt_cells = (
                                _cell('start', 'Capital trabajando', _money(_d['total']),
                                      False, '#0F172A', dim=False)
                                + _cell('mkt', 'Impacto del mercado', _mkt_str, False, _mkt_col,
                                        dim=False)
                                + _cell('hoy', 'Valor hoy', _money(_d['mv']), False, '#0F172A',
                                        dim=False)
                                + _cell('cash2', '+ En efectivo', '+' + _money(_d['cash']),
                                        False, '#0F172A', dim=False)
                                + _cell('cat', '= Capital actual total', _money(_cat),
                                        False, '#0F172A', dim=False)
                                + _cell('pkt2', '− Tu bolsillo', '−' + _money(_d['pocket']),
                                        False, '#0F172A', dim=False))
                            _n_mkt_cells = 6
                            if _has_rend:
                                _rend_col = '#1f8a5b' if (_d['ret'] or 0) >= 0 else '#e05c5c'
                                _rend_sub = (f'<span style="display:block;font-family:Inter,'
                                             f'sans-serif;font-size:9px;font-weight:600;'
                                             f'color:{_rend_col};margin-top:2px;">'
                                             f'({_pct(_d["ret_pct"])})</span>')
                                _mkt_cells += _cell('rend', 'Resultado real', _money(_d['ret']),
                                                     True, _rend_col, _rend_sub)
                                _n_mkt_cells = 7
                            st.markdown(_grid(_mkt_cells, _n_mkt_cells), unsafe_allow_html=True)
                            st.markdown(
                                '<p style="font-family:Inter,sans-serif;font-size:9px;'
                                'color:#8899aa;margin:3px 0 4px 2px;">Capital actual total = '
                                'Valor hoy + En efectivo&nbsp;&nbsp;·&nbsp;&nbsp;Resultado real '
                                '= Capital actual total − Tu bolsillo</p>',
                                unsafe_allow_html=True)
                            if _d.get('nav'):
                                _nvh = _d['nav']
                                _nvh_badge = (f'<span style="border:1px solid {_nvh["color"]};'
                                              f'color:{_nvh["color"]};padding:1px 7px;'
                                              f'font-size:9px;font-weight:600;'
                                              f'letter-spacing:0.05em;">{_nvh["label"]}</span>')
                                st.markdown(
                                    f'<p style="font-family:Inter,sans-serif;font-size:11px;'
                                    f'color:#445566;margin:3px 0 4px 2px;line-height:1.5;">'
                                    f'{_nvh_badge} así etiqueta la portada a {_vj_tk}: '
                                    f'{_nvh["headline"]}</p>', unsafe_allow_html=True)

                            # ── Conclusión: dos lecturas del mismo portafolio (cierre del
                            #    ejercicio — reemplaza al callout fijo del método viejo) ──
                            _cn_naive = _t['total_inv_naive']
                            _cn_ret = _t['total_return']
                            _cn_pct = _t['total_return_pct']
                            _cn_rc = '#1f8a5b' if (_cn_ret or 0) >= 0 else '#e05c5c'
                            _cn_anchor1 = (f'Lo viste en el paso 5: {_money(_d["total"])} es '
                                           f'capital trabajando, no ganancia')
                            if _no_imp:
                                _cn_anchor3 = ('En este fondo no hubo retención — pero la hoja '
                                               'vieja igual sumaría el bruto de los que sí')
                            else:
                                _cn_anchor3 = (f'Lo viste en el paso 3: −{_money(_d["imp"])} de '
                                               f'impuesto NRA')
                            if _d.get('nav'):
                                _cn_anchor2 = (f'Lo dice el veredicto de salud del NAV: '
                                               f'<b style="color:{_d["nav"]["color"]};">'
                                               f'{_d["nav"]["label"]}</b>')
                            else:
                                _cn_anchor2 = 'Compruébalo en el paso 7: Salud del NAV'
                            _cn_items = [
                                ('Cuenta el mismo dólar dos veces',
                                 'Cada dividendo reinvertido ya vive dentro del valor de tus '
                                 'acciones. Sumarlo otra vez como «capital invertido» infla '
                                 'la base — por eso cualquier fondo «se ve recuperado» '
                                 'aunque hayas perdido.',
                                 _cn_anchor1),
                                ('Llama ganancia a un pago mientras el NAV se erosiona',
                                 'En YieldMax parte del pago sale del propio fondo. La '
                                 'prueba no es la etiqueta fiscal (ROC): es la <b>tendencia '
                                 'del NAV frente a su activo subyacente</b>. Si el fondo cae '
                                 'más que la acción que sigue, te están devolviendo tu '
                                 'capital disfrazado de rendimiento.',
                                 _cn_anchor2),
                                ('Suma dinero que nunca llegó a tu cuenta',
                                 'EE.UU. retiene ~30% a extranjeros antes de depositarte. '
                                 'La hoja de Excel suma el bruto que el fondo declara, no '
                                 'lo que de verdad entró.',
                                 _cn_anchor3),
                                ('Se cree el % del folleto',
                                 'El yield anunciado toma <b>un solo pago</b> y lo '
                                 'anualiza. Con pagos que cambian cada semana, es como '
                                 'estimar tu sueldo anual con la propina de tu mejor '
                                 'viernes: una foto del mejor día, no tu historial.',
                                 'La auditoría de abajo lo mide con tus pagos reales →'),
                            ]
                            _cn_tr_html = ''
                            for _ci, (_ct, _cb, _ca) in enumerate(_cn_items):
                                _cbrd = ('border-bottom:none;' if _ci == len(_cn_items) - 1
                                         else 'border-bottom:1px solid #edf1f5;')
                                _cn_tr_html += (
                                    f'<div style="display:grid;grid-template-columns:26px 1fr;'
                                    f'gap:12px;padding:12px 2px;{_cbrd}">'
                                    f'<span style="font-size:15px;font-weight:800;'
                                    f'color:#c9821f;line-height:1.2;">{_ci + 1}</span>'
                                    f'<span><span style="display:block;font-size:12px;'
                                    f'font-weight:700;color:#021C36;margin-bottom:3px;">'
                                    f'{_ct}</span>'
                                    f'<span style="display:block;font-size:11.5px;'
                                    f'color:#4a5568;line-height:1.55;">{_cb}</span>'
                                    f'<span style="display:inline-block;margin-top:5px;'
                                    f'font-size:10.5px;font-weight:600;color:#006497;'
                                    f'background:#eef6fb;padding:2px 8px;">{_ca}</span>'
                                    f'</span></div>')
                            _cn_fondos = ''
                            for _cr in _rows:
                                _crc = ('#1f8a5b' if (_cr['total_return'] or 0) >= 0
                                        else '#e05c5c')
                                _cn_fondos += (
                                    f'<div style="display:grid;grid-template-columns:'
                                    f'64px 1fr 1.2fr;gap:10px;align-items:baseline;'
                                    f'padding:6px 2px;border-bottom:1px solid #edf1f5;'
                                    f'font-size:11.5px;">'
                                    f'<span style="font-weight:800;color:#021C36;">'
                                    f'{_cr["ticker"]}</span>'
                                    f'<span style="color:#a06a1a;"><s style="color:#b8946a;">'
                                    f'«{_money(_cr["total_inv_naive"])} invertidos»</s></span>'
                                    f'<span style="font-weight:700;color:{_crc};">'
                                    f'{_money(_cr["total_return"])} '
                                    f'({_pct(_cr["total_return_pct"])}) '
                                    f'<span style="font-weight:400;color:#8899aa;'
                                    f'font-size:10.5px;">· NAV '
                                    f'{_cr["nav_health"]["label"].lower()}</span></span></div>')
                            st.markdown(f"""
<div style="border-top:3px solid #021C36;margin:18px 0 6px 0;padding-top:16px;font-family:Inter,sans-serif;animation:_vjin .5s cubic-bezier(0.16,1,0.3,1) both;">
  <p style="font-size:11px;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;color:#021C36;margin:0 0 12px 0;">Conclusión — <span style="color:#006497;">dos lecturas del mismo portafolio</span></p>
  <div style="display:grid;grid-template-columns:1fr 1fr;">
    <div style="background:#fbf6ee;border-left:3px solid #c9821f;padding:14px 16px;">
      <p style="font-size:9.5px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#a06a1a;margin:0 0 7px 0;">Lo que dice la hoja de Excel</p>
      <p style="font-size:24px;font-weight:800;letter-spacing:-0.02em;line-height:1;color:#c9821f;margin:0 0 6px 0;">{_money(_cn_naive)}</p>
      <p style="font-size:11px;color:#5a6b7a;line-height:1.5;margin:0;">«capital invertido» — suma tu inversión más cada dividendo recibido, como si todo fuera dinero tuyo aportado.</p>
    </div>
    <div style="background:#eef6fb;border-left:3px solid #006497;padding:14px 16px;">
      <p style="font-size:9.5px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#006497;margin:0 0 7px 0;">Lo que acabas de recorrer</p>
      <p style="font-size:24px;font-weight:800;letter-spacing:-0.02em;line-height:1;color:{_cn_rc};margin:0 0 6px 0;">{_money(_cn_ret)} <span style="font-size:13px;">({_pct(_cn_pct)})</span></p>
      <p style="font-size:11px;color:#5a6b7a;line-height:1.5;margin:0;">resultado real — capital actual total menos lo que pusiste de tu bolsillo. El mismo número de la portada.</p>
    </div>
  </div>
  <p style="font-size:12.5px;color:#021C36;line-height:1.6;margin:12px 2px 2px 2px;">Los dos números salen de los <b>mismos pagos y las mismas acciones</b>. La diferencia no está en los datos: está en las cuatro trampas de la lectura vieja — y cada una la acabas de ver con tus propios números.</p>
  <div style="margin-top:10px;border-top:1px solid #e2e8f0;">{_cn_tr_html}</div>
  <p style="font-size:8px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;color:#8899aa;margin:12px 0 2px 2px;">El saldo, fondo por fondo</p>
  {_cn_fondos}
</div>
""", unsafe_allow_html=True)

                    _viaje_dinero()

                # ── Auditoría del yield titular: stepper narrativo de 3 preguntas ──
                # (inline, no en expander: esta sección ya vive dentro del expander del portafolio
                #  y Streamlit no permite anidar expanders; la tabla completa va en <details>.)
                if _rows:
                    _aud_rows = {r['ticker']: r for r in _rows}

                    @st.fragment
                    def _audit_yield():
                        st.markdown(
                            '<p style="font-family:Inter,sans-serif;font-size:12px;font-weight:700;'
                            'color:#021C36;margin:8px 0 4px 0;letter-spacing:0.03em;">🔍 ¿YieldMax '
                            'paga lo que anuncia?</p>'
                            '<p style="font-family:Inter,sans-serif;font-size:11.5px;color:#5a6b7a;'
                            'margin:0 0 8px 0;line-height:1.55;">Tres formas de medir el mismo '
                            'yield — recórrelas: cada paso es la misma pregunta, medida más '
                            'honestamente. Reconstruido de tus pagos reales.</p>',
                            unsafe_allow_html=True)
                        if hasattr(st, 'pills') and len(_aud_rows) > 1:
                            _au_tk = st.pills('Fondo a auditar',
                                              options=list(_aud_rows.keys()),
                                              default=list(_aud_rows.keys())[0],
                                              selection_mode='single',
                                              key=f'_au_fondo_{_fid}')
                        else:
                            _au_tk = list(_aud_rows.keys())[0]
                        _au_tk = _au_tk or list(_aud_rows.keys())[0]
                        _ar = _aud_rows[_au_tk]
                        _a = _ar['audit']
                        _yoc = _ar['yield_on_cost']

                        _au_steps = ['1. Lo que anuncian', '2. Lo que su fórmula paga hoy',
                                     '3. Lo que de verdad rindió']
                        if hasattr(st, 'pills'):
                            _au_sel = st.pills('Paso auditoría', options=_au_steps,
                                               default=_au_steps[0], selection_mode='single',
                                               key=f'_au_{_au_tk}_{_fid}',
                                               label_visibility='collapsed')
                            _au_i = (_au_steps.index(_au_sel)
                                     if _au_sel in _au_steps else 0)
                        else:
                            _au_i = 2

                        _adv, _fwd, _rzd = _a['advertised'], _a['forward'], _a['realized']
                        _vc = {'match': '#4caf82', 'ahead': '#e0a23c', 'behind': '#3b82f6',
                               'unknown': '#94a3b8'}.get(_a['verdict'], '#94a3b8')

                        if _au_i == 0:
                            _big, _bigc = _pct(_adv), '#c9821f'
                            if _adv is not None:
                                _au_txt = (f'{_au_tk} publica un yield <b>titular</b> de '
                                           f'{_pct(_adv)}: «por cada $100 en {_au_tk} hoy, te '
                                           f'pagaría ~${_adv:.0f} al año». Pero ese número '
                                           f'anualiza <b>un solo pago</b> — es marketing, no una '
                                           f'promesa.')
                            else:
                                _au_txt = (f'No tenemos la tasa titular publicada de {_au_tk} — '
                                           f'sigue a los pasos 2 y 3, que salen de tus pagos '
                                           f'reales.')
                        elif _au_i == 1:
                            _big, _bigc = _pct(_fwd), '#006497'
                            _au_txt = (f'Si el <b>último pago real</b> se repitiera 12 meses, el '
                                       f'mecanismo estaría pagando {_pct(_fwd)} sobre el valor '
                                       f'actual.')
                            if _fwd is not None and _adv is not None:
                                if _fwd > _adv * 1.1:
                                    _au_txt += (' Va <b>por encima</b> del titular: hoy pagan más '
                                                'de lo que anuncian. Suena bien… sigue al paso 3.')
                                elif _fwd < _adv * 0.9:
                                    _au_txt += (' Va <b>por debajo</b> del titular: hoy su fórmula '
                                                'paga menos de lo que anuncian.')
                                else:
                                    _au_txt += (' Coincide con el titular: anuncian lo que su '
                                                'fórmula paga hoy.')
                        else:
                            _big, _bigc = _pct(_rzd), '#e05c5c'
                            _au_txt = (f'En los últimos 12 meses {_au_tk} pagó el equivalente a '
                                       f'{_pct(_rzd)} de su valor actual. <b>Ojo: un número '
                                       f'disparado aquí NO es buena señal</b> — se infla porque '
                                       f'divides entre un NAV desplomado; es la erosión hablando. '
                                       f'Sobre <b>tu costo real</b> el rendimiento fue '
                                       f'<span style="color:#0F766E;font-weight:700;">'
                                       f'{_pct(_yoc)}</span>.')
                            _au_ret = _ar.get('total_return_pct')
                            if _au_ret is not None:
                                _au_rc = '#4caf82' if _au_ret >= 0 else '#e05c5c'
                                _au_txt += (f' Y aun así tu retorno total es <b style="color:'
                                            f'{_au_rc};">{_pct(_au_ret)}</b> — la cifra honesta '
                                            f'siempre es el retorno total de la tabla de arriba, '
                                            f'no el yield.')

                        _au_vals = [(_adv, 'Titular'), (_fwd, 'Mecanismo hoy'),
                                    (_rzd, 'Realizado s/ valor')]
                        _au_nums = [v for v, _ in _au_vals if v is not None]
                        _au_max = max(_au_nums) if _au_nums else 1
                        _bars = ''
                        for _bi, (_bv, _bl) in enumerate(_au_vals):
                            _bon = _bi <= _au_i and _bv is not None
                            _bh = int(round((_bv or 0) / _au_max * 84)) + 6
                            _bars += (
                                f'<div style="display:flex;flex-direction:column;'
                                f'align-items:center;gap:4px;opacity:{"1" if _bon else ".3"};">'
                                f'<span style="font-family:SFMono-Regular,ui-monospace,Menlo,'
                                f'monospace;font-size:12px;font-weight:700;'
                                f'color:{"#021C36" if _bi == _au_i else "#5a6b7a"};">'
                                f'{_pct(_bv)}</span>'
                                f'<div style="width:44px;height:{_bh}px;'
                                f'background:{"#006497" if _bi == _au_i else "#c3ccd4"};"></div>'
                                f'<span style="font-family:Inter,sans-serif;font-size:9px;'
                                f'font-weight:600;letter-spacing:0.05em;text-transform:uppercase;'
                                f'color:#8899aa;text-align:center;">{_bl}</span></div>')
                        _au_verdict = (f'<span style="display:inline-block;border:1px solid '
                                       f'{_vc};color:{_vc};font-size:10px;font-weight:600;'
                                       f'letter-spacing:0.05em;padding:2px 8px;margin-top:10px;'
                                       f'text-transform:uppercase;">{_a["label"]}</span>'
                                       if _au_i == 2 else '')
                        st.markdown(
                            f'<div style="border:1px solid #d9dee3;padding:16px 20px;'
                            f'animation:_vjin .3s ease both;font-family:Inter,sans-serif;">'
                            f'<span style="font-size:9.5px;font-weight:700;letter-spacing:0.08em;'
                            f'text-transform:uppercase;color:#8899aa;">'
                            f'{_au_steps[_au_i][3:]}</span>'
                            f'<div style="font-family:SFMono-Regular,ui-monospace,Menlo,monospace;'
                            f'font-size:32px;font-weight:700;letter-spacing:-0.02em;'
                            f'color:{_bigc};margin:2px 0;">{_big}</div>'
                            f'<div style="display:flex;align-items:flex-end;gap:30px;'
                            f'margin:12px 0 4px 0;">{_bars}</div>'
                            f'<p style="font-size:12.5px;color:#333;line-height:1.6;'
                            f'margin:8px 0 0 0;max-width:640px;">{_au_txt}</p>'
                            f'{_au_verdict}</div>', unsafe_allow_html=True)

                        _ab = ""
                        for r in _aud_rows.values():
                            a = r['audit']
                            _tvc = {'match': '#4caf82', 'ahead': '#e0a23c', 'behind': '#3b82f6',
                                    'unknown': '#94a3b8'}.get(a['verdict'], '#94a3b8')
                            _ab += (
                                '<tr style="border-bottom:1px solid #eef2f6;">'
                                f'<td style="padding:6px 10px;font-weight:700;color:#021C36;">{r["ticker"]}</td>'
                                f'<td style="padding:6px 10px;text-align:right;color:#c9821f;">{_pct(a["advertised"])}</td>'
                                f'<td style="padding:6px 10px;text-align:right;">{_pct(a["forward"])}</td>'
                                f'<td style="padding:6px 10px;text-align:right;">{_pct(a["realized"])}</td>'
                                f'<td style="padding:6px 10px;text-align:right;color:#0F766E;">{_pct(r["yield_on_cost"])}</td>'
                                f'<td style="padding:6px 10px;color:{_tvc};font-weight:600;">{a["label"]}</td>'
                                '</tr>')
                        _hh = ('padding:7px 10px;text-align:right;color:#64748B;font-weight:600;'
                               'font-size:10px;letter-spacing:0.06em;text-transform:uppercase;')
                        st.markdown(f"""
<details style="margin:8px 0 0 0;">
<summary style="cursor:pointer;font-family:Inter,sans-serif;font-size:11.5px;color:#006497;">Ver la tabla completa (todos los fondos)</summary>
<div style="overflow-x:auto;">
<table style="width:100%;border-collapse:collapse;font-family:Inter,sans-serif;font-size:12px;color:#334155;margin-top:8px;">
  <thead><tr style="border-bottom:2px solid #006497;">
    <th style="{_hh.replace('text-align:right','text-align:left')}">Fondo</th>
    <th style="{_hh}">Titular</th><th style="{_hh}">Mecanismo hoy</th>
    <th style="{_hh}">Realizado (s/ valor)</th><th style="{_hh}">Rend. s/ tu costo</th>
    <th style="{_hh.replace('text-align:right','text-align:left')}">Veredicto</th>
  </tr></thead><tbody>{_ab}</tbody>
</table></div>
<p style="font-family:Inter,sans-serif;font-size:10.5px;color:#64748B;margin:8px 0 0 0;line-height:1.55;"><b>Cómo leerlo:</b> si «titular ≈ mecanismo», anuncian lo que su fórmula paga. Fíjate en <b>«Rend. s/ tu costo»</b>: si se acerca al titular, el fondo sí paga ~lo prometido respecto a tu principal — lo que te empobrece es la <b>caída del NAV</b>, no que paguen poco.</p>
</details>
""", unsafe_allow_html=True)

                    _audit_yield()
                st.markdown('<hr class="da-section-rule">', unsafe_allow_html=True)

            # ── Helper: tarjeta semáforo de salud del NAV por fondo ────
            def _render_nav_health_card(tk, stats):
                # Datos independientes de los sliders de proyección (mismo patrón
                # que el veredicto del expander de proyección).
                _roc_pct = logic._roc_pct_for(tk, stats)
                _navc = stats.get('price_cagr_recent')
                if _navc is None:
                    _navc = stats.get('price_cagr')
                _pk = stats.get('pocket_investment')
                _tr_pct = ((((stats.get('market_value') or 0)
                             + (stats.get('dividends_collected_cash') or 0) - _pk)
                            / _pk * 100) if _pk else None)
                _asof_days = None
                _r19 = logic.load_roc_19a().get(str(tk).upper())
                if _r19 and _r19.get('asof'):
                    try:
                        _asof_days = (datetime.date.today()
                                      - datetime.date.fromisoformat(_r19['asof'])).days
                    except Exception:
                        _asof_days = None
                _prev_v = logic.latest_health_verdict(tk)
                _verdict = logic.classify_roc_health(
                    roc_pct=_roc_pct, price_cagr=_navc, total_return_pct=_tr_pct,
                    history_days=stats.get('price_history_days'), roc_asof_days=_asof_days,
                    prev_verdict=_prev_v, underlying_cagr=stats.get('underlying_cagr_recent'))
                _score = _verdict.get('gauge_score')
                if _score is None:
                    _gauge_html = ("<div style='height:14px;background:#e9ecef;color:#888;"
                                   "font-size:10px;text-align:center;line-height:14px;'>"
                                   "no medible aún</div>")
                else:
                    _gauge_html = (
                        "<div style='position:relative;height:14px;margin:6px 0 2px 0;"
                        "background:linear-gradient(90deg,#4caf82 0%,#e0a23c 50%,#e05c5c 100%);'>"
                        f"<div style='position:absolute;top:-3px;left:{_score:.0f}%;width:3px;"
                        "height:20px;background:#021C36;transform:translateX(-50%);'></div></div>"
                        "<div style='display:flex;justify-content:space-between;font-size:10px;"
                        "color:#888;'><span>Sano</span><span>Destruyéndose</span></div>")
                st.markdown(
                    f"<div style='margin:10px 0 2px 0;font-weight:700;font-size:15px;"
                    f"color:{_verdict['color']};'>{tk} — {_verdict['headline']}</div>"
                    f"{_gauge_html}"
                    f"<div style='font-size:12.5px;color:#333;margin:6px 0 2px 0;"
                    f"line-height:1.5;'>{_verdict['plain']}</div>",
                    unsafe_allow_html=True)
                _nums = []
                if _navc is not None:
                    _nums.append(f"NAV {_navc:+.0f}%/año")
                if _roc_pct is not None:
                    _nums.append(f"ROC {_roc_pct:.0f}%")
                if _tr_pct is not None:
                    _nums.append(f"retorno total {_tr_pct:+.0f}%")
                st.markdown(
                    "<details style='margin:2px 0 4px 0;'>"
                    "<summary style='cursor:pointer;font-size:12px;color:#006497;'>"
                    "Ver detalle técnico</summary>"
                    + (f"<div style='font-size:12px;color:#666;margin:4px 0;'>"
                       f"{' · '.join(_nums)}</div>" if _nums else "")
                    + f"<div style='font-size:12.5px;color:#333;line-height:1.5;'>"
                      f"{_verdict['reason']}</div></details>",
                    unsafe_allow_html=True)
                _info = logic.load_instruments().get(str(tk).upper(), {}) or {}
                _why = []
                if _info.get('nav_erosion'):
                    _why.append(f"<b>Erosión del NAV:</b> {_info['nav_erosion']}")
                if _info.get('sustainability'):
                    _why.append(f"<b>Sostenibilidad de la distribución:</b> {_info['sustainability']}")
                if _why:
                    st.markdown(
                        "<details style='margin:2px 0 10px 0;'>"
                        "<summary style='cursor:pointer;font-size:12px;color:#006497;'>"
                        f"¿Por qué pasa esto en {tk}?</summary>"
                        "<div style='font-size:12.5px;color:#333;line-height:1.55;margin:4px 0;'>"
                        + "<br><br>".join(_why) + "</div></details>",
                        unsafe_allow_html=True)

            # ── Agregados A/B (dividendos vs crecimiento) ───────────
            _cmp_a_rows = [(t, s) for t, s in results.items() if classify_map.get(t) == 'mode_a' and 'error' not in s]
            _cmp_b_rows = [(t, s) for t, s in results.items() if classify_map.get(t) == 'mode_b' and 'error' not in s]
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
            _comb_val = _cmp_a_mv + _cmp_b_mv
            # Participación referida al VALOR de todo el portafolio (market value), no a lo invertido.
            _a_share = _cmp_a_mv / _comb_val * 100 if _comb_val > 0 else 0
            _b_share = _cmp_b_mv / _comb_val * 100 if _comb_val > 0 else 0

            # ── Tus dos portafolios (tarjetas A/B) ───────────────────────
            if mode_a_tickers or mode_b_tickers:
                _da_section('Tus dos portafolios',
                            'Tu dinero está jugando dos juegos distintos al mismo tiempo. Cada uno gana (y pierde) de una forma diferente — por eso los separamos.')

                def _dp_mini(inv, mv, div, tr, pct):
                    _trc = '#4caf82' if tr >= 0 else '#e05c5c'
                    return (
                        '<div class="da-port-mini">'
                        f'<span><span class="lbl">Invertido</span><span class="val">${inv:,.0f}</span></span>'
                        f'<span><span class="lbl">Vale hoy</span><span class="val">${mv:,.0f}</span></span>'
                        f'<span><span class="lbl">Dividendos</span><span class="val">${div:,.0f}</span></span>'
                        f'<span><span class="lbl">Retorno total</span>'
                        f'<span class="val" style="color:{_trc};">${tr:,.0f} ({pct:+.1f}%)</span></span>'
                        '</div>')

                _dp_cards = []
                if mode_b_tickers:
                    _dp_cards.append(
                        '<div class="da-port-card">'
                        '<p class="da-port-title">Portafolio de crecimiento</p>'
                        f'<span class="da-port-chip">{len(mode_b_tickers)} fondos: {", ".join(mode_b_tickers)}</span>'
                        + _dp_mini(_cmp_b_inv, _cmp_b_mv, _cmp_b_div, _cmp_b_tr, _cmp_b_pct)
                        + '</div>')
                if mode_a_tickers:
                    _dp_cards.append(
                        '<div class="da-port-card navy">'
                        '<p class="da-port-title">Portafolio de dividendos</p>'
                        f'<span class="da-port-chip">{len(mode_a_tickers)} fondos: {", ".join(mode_a_tickers)}</span>'
                        + _dp_mini(_cmp_a_inv, _cmp_a_mv, _cmp_a_div, _cmp_a_tr, _cmp_a_pct)
                        + '</div>')
                _dp_grid_style = ' style="grid-template-columns:1fr;"' if len(_dp_cards) == 1 else ''
                st.markdown(
                    f'<div class="da-port-cards"{_dp_grid_style}>' + ''.join(_dp_cards) + '</div>',
                    unsafe_allow_html=True)

            # ── Comparativa directa A vs B (solo cuando hay ambos) ────
            if _cmp_a_rows and _cmp_b_rows:
                # ── Consolidado: Dividendos vs Crecimiento ──────────────
                import pandas as pd

                st.markdown(
                    '<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;color:#021C36;'
                    'margin:18px 0 6px 0;">¿Cómo está repartido tu dinero?</p>', unsafe_allow_html=True)

                # ── Pie chart de asignación por VALOR de mercado (dividendos vs crecimiento, por ETF) ──
                import altair as alt
                import pandas as pd
                _pie_rows = ([{'ETF': t, 'Grupo': 'Dividendos', 'Capital': (s.get('market_value') or 0)}
                              for t, s in _cmp_a_rows]
                             + [{'ETF': t, 'Grupo': 'Crecimiento', 'Capital': (s.get('market_value') or 0)}
                                for t, s in _cmp_b_rows])
                _pie_df = pd.DataFrame([r for r in _pie_rows if r['Capital'] > 0])
                if not _pie_df.empty:
                    _pie_tot = _pie_df['Capital'].sum()
                    _pie_df['Pct'] = _pie_df['Capital'] / _pie_tot * 100 if _pie_tot else 0
                    _pie_df['Etiqueta'] = _pie_df['ETF'] + '  ' + _pie_df['Pct'].round(0).astype(int).astype(str) + '%'
                    _pie_base = alt.Chart(_pie_df).encode(
                        theta=alt.Theta('Capital:Q', stack=True),
                        order=alt.Order('Grupo:N'),
                        color=alt.Color('Grupo:N',
                            scale=alt.Scale(domain=['Dividendos', 'Crecimiento'], range=['#006497', '#2d3748']),
                            legend=alt.Legend(title=None, orient='top', labelFontSize=12)),
                        tooltip=[alt.Tooltip('ETF:N', title='ETF'),
                                 alt.Tooltip('Grupo:N', title='Portafolio'),
                                 alt.Tooltip('Capital:Q', format='$,.0f', title='Valor de mercado'),
                                 alt.Tooltip('Pct:Q', format='.1f', title='% del portafolio')])
                    _pie_arc = _pie_base.mark_arc(innerRadius=68, outerRadius=130, stroke='#fcf9f8', strokeWidth=2)
                    _pie_txt = _pie_base.mark_text(radius=155, fontSize=11, fontWeight='bold',
                                                   font='Inter, system-ui, sans-serif').encode(
                        text=alt.Text('Etiqueta:N'), color=alt.value('#021C36'))
                    _pie_chart = (_pie_arc + _pie_txt).properties(
                        height=360, background=CHART_PALETTE['bg']
                    ).configure_view(strokeOpacity=0, fill=CHART_PALETTE['bg'])
                    st.altair_chart(_pie_chart, use_container_width=True)
                    st.markdown(
                        '<div style="display:flex;justify-content:center;gap:28px;margin:-6px 0 4px 0;">'
                        '<span style="font-family:Inter,sans-serif;font-size:12px;color:#021C36;">'
                        '<span style="display:inline-block;width:9px;height:9px;background:#006497;margin-right:6px;vertical-align:middle;"></span>'
                        f'Dividendos <b>{_a_share:.0f}%</b> · ${_cmp_a_mv:,.0f}</span>'
                        '<span style="font-family:Inter,sans-serif;font-size:12px;color:#021C36;">'
                        '<span style="display:inline-block;width:9px;height:9px;background:#2d3748;margin-right:6px;vertical-align:middle;"></span>'
                        f'Crecimiento <b>{_b_share:.0f}%</b> · ${_cmp_b_mv:,.0f}</span>'
                        '</div>',
                        unsafe_allow_html=True)

                st.markdown('<hr class="da-section-rule">', unsafe_allow_html=True)

            # ── Lo que nadie te cuenta del portafolio de dividendos ─────
            if mode_a_tickers:
                _da_section('Lo que nadie te cuenta del portafolio de dividendos',
                            'Los ETFs de dividendos altos no son una estafa, pero tampoco son lo que parecen. Estos son los cuatro costos ocultos — con los datos de TU portafolio.')

                # Bloque 1 — ROC en lenguaje llano
                st.markdown(
                    '<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;color:#021C36;'
                    'margin:18px 0 6px 0;">Tu dinero de vuelta disfrazado de dividendo (ROC)</p>',
                    unsafe_allow_html=True)
                st.markdown(
                    '<div style="border-left:4px solid #006497;background:#eef6fb;padding:12px 16px;'
                    'margin:0 0 12px 0;font-family:Inter,sans-serif;font-size:12px;color:#333333;line-height:1.6;">'
                    "<b>¿Qué es el ROC?</b> 'Return of Capital' — retorno de capital. Una parte de lo que el "
                    "fondo te 'paga' puede no ser ganancia: es <b>tu propio dinero que te devuelven</b>."
                    "<br>· Si pusiste $100 y te 'pagan' $10, pero $6 son ROC, solo $4 fueron ganancia real; "
                    'los otros $6 salieron de tu bolsa.'
                    '<br>· El fondo lo reporta en su aviso oficial <b>19a</b>, y esta calculadora lo lee '
                    'directo de ahí.'
                    '<br><b>¿Por qué importa?</b> Un yield gigante con mucho ROC puede ser un fondo '
                    'devolviéndote tu inversión en cuotas mientras su precio se desinfla.'
                    '<br><b>¿Qué hacer?</b> No juzgues el ROC solo: mira el semáforo de salud de abajo, '
                    'que cruza el ROC con la tendencia del precio.</div>',
                    unsafe_allow_html=True)

                # Bloque 2 — erosión del NAV, fondo por fondo (semáforo)
                st.markdown(
                    '<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;color:#021C36;'
                    'margin:18px 0 6px 0;">La erosión del precio (NAV), fondo por fondo</p>',
                    unsafe_allow_html=True)
                st.markdown(
                    '<p style="font-family:Inter,sans-serif;font-size:12px;color:#333333;line-height:1.6;'
                    'margin:0 0 8px 0;">El precio de estos ETFs tiende a bajar con el tiempo — se llama '
                    '<b>erosión del NAV</b>. Aquí el diagnóstico de cada fondo tuyo, con su tendencia real '
                    'de precio:</p>',
                    unsafe_allow_html=True)
                for _ctr_tk in mode_a_tickers:
                    _ctr_hs = results.get(_ctr_tk)
                    if not isinstance(_ctr_hs, dict) or 'error' in _ctr_hs:
                        continue
                    _render_nav_health_card(_ctr_tk, _ctr_hs)

                # Bloque 3 — yield anunciado vs realidad
                st.markdown(
                    '<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;color:#021C36;'
                    'margin:18px 0 6px 0;">El yield anunciado vs lo que de verdad ganas</p>',
                    unsafe_allow_html=True)
                st.markdown(
                    '<p style="font-family:Inter,sans-serif;font-size:12px;color:#333333;line-height:1.6;'
                    'margin:0 0 8px 0;">Un fondo puede anunciar \'80% de yield\' y aun así hacerte perder '
                    'dinero. El truco: el yield anualiza un solo pago de un flujo que salta cada semana, '
                    'y no descuenta la caída del precio.</p>',
                    unsafe_allow_html=True)
                with st.expander("La hoja de Excel que te venden vs la realidad", expanded=False):
                    _render_hoja_excel()

                # Bloque 4 — cierre honesto en un solo callout (el impuesto NRA ya se
                # explica dentro del viaje del dinero, paso "Impuesto NRA").
                st.markdown(
                    '<div style="border-left:4px solid #c9821f;background:#fbf6ee;padding:12px 16px;'
                    'margin:12px 0 12px 0;font-family:Inter,sans-serif;font-size:12px;color:#4a5568;line-height:1.65;">'
                    '<p style="font-family:Inter,sans-serif;font-size:11px;font-weight:800;'
                    'letter-spacing:0.08em;text-transform:uppercase;color:#a06a1a;margin:0 0 6px 0;">'
                    'El trato completo, en una línea</p>'
                    '<b style="color:#021C36;">Cuándo sí:</b> quieres ingreso mensual real hoy y lo '
                    'entiendes como renta, no crecimiento. &nbsp;·&nbsp; '
                    '<b style="color:#021C36;">El precio:</b> renuncias a la subida de la acción, el '
                    "NAV tiende a erosionarse, y parte del 'pago' es tu dinero de vuelta (ROC) menos "
                    '~30% de impuesto. &nbsp;·&nbsp; '
                    '<b style="color:#021C36;">Regla de bolsillo:</b> yield alto ≠ ganancia alta — la '
                    'cifra que manda es el retorno total de la portada.</div>',
                    unsafe_allow_html=True)


            def _render_data_quality_panel():
                # ── Calidad de datos (pre-flight) ─────────────────────────
                if _dq_unrel or _dq_recon or _dq_part:
                    _rows = []
                    _style = {
                        'unreliable': ('#e0a23c', 'No confiable', '#fbf7ef'),
                        'reconciled': ('#006497', 'Reconciliado desde tu captura', '#eef6fb'),
                        'partial':    ('#8899aa', 'Parcial', '#f6f3f2'),
                    }
                    for t in _dq_unrel + _dq_recon + _dq_part:
                        q = _dq[t]
                        _accent, _tag, _bg = _style[q['level']]
                        _action_html = (f'<p style="font-family:Inter,sans-serif;font-size:12px;color:#006497;'
                                        f'margin:3px 0 0 0;line-height:1.5;">→ {q["action"]}</p>') if q.get("action") else ''
                        _rows.append(
                            f'<div style="border-left:3px solid {_accent};padding:8px 14px;margin:8px 0;background:{_bg};">'
                            f'<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:700;color:#021C36;margin:0;">'
                            f'{t} · <span style="color:{_accent};font-weight:600;">{_tag}</span></p>'
                            f'<p style="font-family:Inter,sans-serif;font-size:12px;color:#555;margin:3px 0 0 0;line-height:1.5;">{q["reason"]}</p>'
                            f'{_action_html}'
                            f'</div>'
                        )
                    st.markdown(
                        '<div style="margin:8px 0 4px 0;"><p style="font-family:Inter,sans-serif;font-size:13px;'
                        'font-weight:800;color:#021C36;margin:0 0 4px 0;">Calidad de datos</p>'
                        '<p style="font-family:Inter,sans-serif;font-size:12px;color:#8899aa;margin:0 0 6px 0;">'
                        'Cuando el CSV no trae el historial completo, usamos tu captura del broker (acciones y costo) '
                        'para reconciliar la posición; los tickers no reconciliados se marcan y se excluyen del % en el tiempo.</p>'
                        + ''.join(_rows) + '</div>',
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        f'<div style="border-left:4px solid #4caf82;background:#f0faf5;padding:10px 14px;margin:8px 0;">'
                        f'<span style="font-family:Inter,sans-serif;font-size:12px;font-weight:600;color:#1a1a1a;">'
                        f'Datos completos · {len(results)} posiciones verificadas</span></div>',
                        unsafe_allow_html=True
                    )

                # ── Validación cruzada de ingresos (segunda fuente) ───────
                _inc_summary = st.session_state.get('_wizard_income_summary')
                if _inc_summary and _inc_summary.get('tickers'):
                    _recon = logic.reconcile_income(results, _inc_summary)
                    if _recon:
                        _badge_style = {
                            'ok':   ('#4caf82', '#f0faf5'),
                            'warn': ('#e0a23c', '#fbf7ef'),
                            'info': ('#8899aa', '#f6f3f2'),
                        }
                        _status_label = {
                            'match': 'Validado', 'cusip_folded': 'Validado (identidad CUSIP plegada)',
                            'csv_window_longer': 'Validado en ventana común',
                            'income_higher': 'Faltan dividendos en el CSV',
                            'csv_overcount_suspected': 'Posible sobre-conteo del CSV',
                            'csv_higher': 'El CSV reporta de más',
                            'missing_in_income': 'Sin cobertura en el income',
                            'missing_in_csv': 'Solo en el income (vendido)',
                        }
                        _order = {'warn': 0, 'ok': 1, 'info': 2}
                        _n_ok = sum(1 for r in _recon.values() if r['badge'] == 'ok')
                        _n_warn = sum(1 for r in _recon.values() if r['badge'] == 'warn')
                        _inc_rows = []
                        for t, r in sorted(_recon.items(), key=lambda x: (_order.get(x[1]['badge'], 3), x[0])):
                            _accent, _bg = _badge_style.get(r['badge'], _badge_style['info'])
                            _csv_v = f"${r['csv_total']:,.2f}" if r.get('csv_total') is not None else "—"
                            _inc_v = f"${r['income_total']:,.2f}" if r.get('income_total') is not None else "—"
                            _win_v = ""
                            if r.get('csv_in_window') is not None and r.get('csv_total') is not None and abs(r['csv_in_window'] - r['csv_total']) > 0.01:
                                _win_v = f' <span style="color:#8899aa;">(en ventana común: ${r["csv_in_window"]:,.2f})</span>'
                            _inc_rows.append(
                                f'<div style="border-left:3px solid {_accent};padding:8px 14px;margin:8px 0;background:{_bg};">'
                                f'<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:700;color:#021C36;margin:0;">'
                                f'{t} · <span style="color:{_accent};font-weight:600;">{_status_label.get(r["status"], r["status"])}</span></p>'
                                f'<p style="font-family:Inter,sans-serif;font-size:12px;color:#555;margin:3px 0 0 0;line-height:1.5;">'
                                f'Dividendo bruto — CSV: <b>{_csv_v}</b>{_win_v} · Broker recibido: <b>{_inc_v}</b></p>'
                                f'<p style="font-family:Inter,sans-serif;font-size:12px;color:#777;margin:3px 0 0 0;line-height:1.5;">{r["note"]}</p>'
                                f'</div>'
                            )
                        st.markdown(
                            '<div style="margin:8px 0 4px 0;"><p style="font-family:Inter,sans-serif;font-size:13px;'
                            'font-weight:800;color:#021C36;margin:0 0 4px 0;">Validación cruzada de ingresos</p>'
                            '<p style="font-family:Inter,sans-serif;font-size:12px;color:#8899aa;margin:0 0 6px 0;">'
                            f'Comparamos el dividendo bruto del CSV contra tu reporte de ingresos del broker (segunda fuente). '
                            f'{_n_ok} validado(s), {_n_warn} con alerta. Las proyecciones “Estimated” del broker no se usan.</p>'
                            + ''.join(_inc_rows) + '</div>',
                            unsafe_allow_html=True
                        )



            # ── Ingresos: Schwab vs tu cálculo + proyección (consolidado) ──
            _income_df_s3 = st.session_state.get('_wizard_income_df')
            if _income_df_s3 is not None and len(_income_df_s3) > 0:
                _proj_all = logic.project_income(_income_df_s3, results)
                # Filtro inteligente: solo activos de generación de ingresos (income/dividendo alto).
                # Los índices/crecimiento de dividendo marginal (SCHB, XLK) se ocultan para no aplastar la escala.
                _proj, _dropped = logic.filter_income_assets(_proj_all, results)
                if _proj:
                    import altair as alt

                    # ── Fila de KPIs: una fila por ETF de ingreso + TOTAL ──
                    _sum_sproj = sum((_d.get('schwab_proj') or 0) for _d in _proj.values())
                    _sum_oproj = sum((_d.get('our_proj') or 0) for _d in _proj.values())

                    def _tip_for(kind, tot_s, tot_c):
                        # Tooltip adaptativo: intro fija + interpretación del Δ% TOTAL real.
                        pct = ((tot_s / tot_c - 1) * 100) if tot_c else None
                        v = f'{pct:+.0f}%' if pct is not None else None
                        if kind == 'recv':
                            intro = ('<b>¿Qué es?</b> Los dividendos que ya cobraste en los últimos 12 meses, '
                                     'ETF por ETF. La cifra que ves es la que <b>reconstruye la calculadora</b> '
                                     'desde tu archivo CSV. <b>Δ%</b> es cuánto se desvía de lo que <b>Schwab</b> '
                                     'reporta haberte pagado: cerca de 0% significa que ambas fuentes coinciden.')
                            if pct is None:
                                interp = ('<b>Tu Δ% aún no está disponible.</b> La calculadora todavía no puede '
                                          'leer tus pagos desde el CSV. Sube el archivo con el historial de '
                                          'dividendos para poder comparar las dos fuentes.')
                            elif abs(pct) <= 5:
                                interp = (f'<b>Tu Δ% es {v}</b>, prácticamente cero, que es justo lo ideal. '
                                          'Quiere decir que tu archivo CSV está <b>completo</b> y coincide con lo '
                                          'que Schwab te pagó de verdad: <b>puedes confiar en estas cifras</b>.')
                            elif pct > 5:
                                interp = (f'<b>Tu Δ% es {v}</b>, que es alto. Significa que a tu CSV le '
                                          '<b>faltan pagos</b>: la calculadora está viendo menos dividendos de los '
                                          'que Schwab sí registró. Revisa que tu archivo incluya <b>todas</b> las '
                                          'transacciones del último año para que cuadren.')
                            else:
                                interp = (f'<b>Tu Δ% es {v}</b>: tu CSV muestra <b>más</b> de lo que Schwab '
                                          'reporta. Puede haber pagos duplicados o con fecha equivocada en el '
                                          'archivo; conviene revisarlo.')
                        elif kind == 'ann':
                            intro = ('<b>¿Qué es?</b> Una estimación de cuánto vas a cobrar en dividendos durante '
                                     'los próximos 12 meses, ETF por ETF. Se puede calcular de dos formas '
                                     'distintas:<br><br>'
                                     '<b>· Método Schwab (optimista):</b> toma tu <b>último pago de dividendos</b> '
                                     '(el más reciente que te depositaron) y supone que ese mismo monto se '
                                     'repetirá, igual, en cada pago durante todo el año.<br><br>'
                                     '<b>· Método calculadora (realista):</b> en vez de fiarse de un solo pago, '
                                     '<b>promedia tus pagos más recientes</b> (los de los últimos ~3 meses) y '
                                     'proyecta el año con ese promedio.<br><br>'
                                     '<b>¿Por qué la calculadora no cree que ese último pago se mantenga?</b> '
                                     'Porque muchos de estos ETF de dividendos altos suelen pagar <b>cada vez un '
                                     'poco menos</b>: si miras tus pagos anteriores, el monto de cada uno tiende '
                                     'a ir <b>bajando</b> con el tiempo. Por eso, dar por hecho que el último '
                                     'pago se repite igual casi siempre infla la cifra; promediar los pagos '
                                     'recientes capta esa caída y se acerca más a lo que de verdad vas a '
                                     'recibir.<br><br>'
                                     '<b>Δ%</b> es cuánto más alto proyecta Schwab frente a la calculadora.')
                            if pct is None:
                                interp = '<b>Δ% no disponible</b> por falta de datos para proyectar.'
                            elif abs(pct) <= 5:
                                interp = (f'<b>Tu Δ% es {v}</b>, casi sin diferencia. Tus pagos vienen '
                                          '<b>estables</b> y la proyección es confiable: puedes contar con ese '
                                          'ingreso anual.')
                            elif pct > 5:
                                interp = (f'<b>Tu Δ% es {v}</b>: Schwab proyecta bastante más que la calculadora. '
                                          'Como tus pagos recientes vienen <b>cayendo</b>, esa cifra optimista de '
                                          'Schwab difícilmente se cumpla. <b>Guíate por el número de la '
                                          'calculadora</b> (el menor), que es el realista.')
                            else:
                                interp = (f'<b>Tu Δ% es {v}</b>: la calculadora proyecta más que Schwab porque '
                                          'tus pagos recientes vienen <b>subiendo</b>. Aun así, planifica con '
                                          'prudencia.')
                        elif kind == 'hist':
                            intro = ('<b>¿Qué es?</b> El total de dividendos que has acumulado en <b>toda tu '
                                     'historia</b> (no solo los últimos 12 meses), ETF por ETF. La cifra que ves '
                                     'es la que <b>reconstruye la calculadora</b> desde tu archivo CSV; el '
                                     '<b>Δ%</b> es cuánto se desvía de lo que <b>Schwab</b> reporta en todo el '
                                     'income.<br><br>'
                                     '<b>Es el dividendo bruto</b> (lo que el fondo declaró, <b>antes</b> de la '
                                     'retención de impuesto a extranjeros). Lo que de verdad entró a tu cuenta, ya '
                                     'descontado ese impuesto, es el <b>neto</b> que ves abajo en la tabla de ROC '
                                     '(columna <b>Div. pagados</b>): por eso ese número es menor, no es un error.<br><br>'
                                     '<b>Ojo con el Δ%:</b> las dos fuentes pueden cubrir <b>ventanas de tiempo '
                                     'distintas</b>. Tu CSV suele tener <b>más historia</b> que el reporte de income '
                                     'de Schwab, así que un Δ% grande casi siempre significa que el CSV abarca más '
                                     'fechas, <b>no un error</b>.')
                            if pct is None:
                                interp = ('<b>Δ% no disponible</b>: falta una de las dos fuentes (sube el income de '
                                          'Schwab y el CSV para comparar el acumulado).')
                            elif abs(pct) <= 5:
                                interp = (f'<b>Tu Δ% es {v}</b>, prácticamente cero: ambas fuentes cubren casi la '
                                          'misma historia y coinciden. Puedes confiar en el acumulado.')
                            elif pct > 5:
                                interp = (f'<b>Tu Δ% es {v}</b>: Schwab reporta <b>más</b> acumulado que tu CSV. '
                                          'Revisa si a tu archivo le faltan <b>pagos antiguos</b> para que cuadre '
                                          'con todo lo que el broker registró.')
                            else:
                                interp = (f'<b>Tu Δ% es {v}</b>: tu CSV muestra <b>más</b> acumulado que el income de '
                                          'Schwab. Es lo normal cuando el CSV cubre fechas <b>previas</b> a tu '
                                          'reporte de income: más cobertura, no un error.')
                        else:  # mon
                            intro = ('<b>¿Qué es?</b> Lo mismo que el proyectado anual pero <b>dividido entre '
                                     '12</b>: lo que te entraría cada mes, ETF por ETF.<br><br>'
                                     'Recuerda las dos formas de proyectar: <b>Schwab</b> repite tu <b>último '
                                     'pago de dividendos</b> como si nunca cambiara (optimista), y la '
                                     '<b>calculadora</b> promedia tus pagos recientes para reflejar que, en estos '
                                     'ETF, el pago suele ir <b>bajando</b> con el tiempo (realista).<br><br>'
                                     '<b>Δ%</b> es cuánto más alto pinta Schwab el mes.')
                            if pct is None:
                                interp = '<b>Δ% no disponible</b> por falta de datos para proyectar.'
                            elif abs(pct) <= 5:
                                interp = (f'<b>Tu Δ% es {v}</b>, casi sin diferencia: puedes presupuestar ese '
                                          'ingreso mensual con tranquilidad.')
                            elif pct > 5:
                                interp = (f'<b>Tu Δ% es {v}</b>: Schwab pinta un mes más alto del que '
                                          'probablemente recibas. <b>Presupuesta con el número de la '
                                          'calculadora</b>, no con el de Schwab, para no quedarte corto.')
                            else:
                                interp = (f'<b>Tu Δ% es {v}</b>: la calculadora ve un poco más que Schwab; '
                                          'planifica con prudencia.')
                        return intro + '<br><br>' + interp

                    def _fmt_money(v):
                        return f'${v:,.0f}' if v is not None else 'n/d'

                    def _pct_html(schwab, calc):
                        if schwab is None or not calc:
                            return '<span class="pct" style="color:#b8c2cc;">—</span>'
                        p = (schwab / calc - 1) * 100
                        c = '#e0a23c' if p > 5 else ('#4caf82' if abs(p) <= 5 else '#006497')
                        return f'<span class="pct" style="color:{c};">{p:+.0f}%</span>'

                    def _group_total(rows):
                        ts, tc, tc_has = 0.0, 0.0, False
                        for _tk, _s, _c in rows:
                            ts += (_s or 0)
                            if _c is not None:
                                tc += _c
                                tc_has = True
                        return ts, (tc if tc_has else None)

                    _items = sorted(_proj.items(),
                                    key=lambda kv: (kv[1].get('schwab_received_12m') or 0), reverse=True)
                    _rows_ann  = [(_tk, _d.get('schwab_proj'), _d.get('our_proj')) for _tk, _d in _items]
                    _rows_hist = [(_tk, _d.get('schwab_received_total'), _d.get('our_received_total'))
                                  for _tk, _d in _items]

                    _da_section('Ingreso y comparación con el broker',
                                'El número fino: lo recibido vs lo proyectado, tu Retorno de Capital por activo y por qué la proyección del broker suele estar inflada.')
                    _inc_exp = st.expander('Ver detalle · tabla consolidada (Schwab vs tu cálculo · ROC) · gráfica de ingresos', expanded=False)
                    # Las columnas "Últimos 12 meses" y "Proyectado mensual" se eliminaron y todo
                    # (Total dividendos, ROC e inversión, Proyectado anual) se fundió en UNA sola
                    # cuadrícula estilo ROC, que se renderiza más abajo (tras la gráfica y la justificación).

                    # ── Gráfica: proyección de ingreso mensual (Schwab vs cálculo), 12 meses ──
                    _inc_exp.markdown(
                        '<div style="margin:14px 0 2px 0;"><p style="font-family:Inter,sans-serif;font-size:13px;'
                        'font-weight:800;color:#021C36;margin:0 0 2px 0;">Ingreso acumulado en el año: Schwab vs tu cálculo</p>'
                        '<p style="font-family:Inter,sans-serif;font-size:12px;color:#8899aa;margin:0 0 8px 0;line-height:1.6;">'
                        'Cada punto suma <b>todo lo que llevarías cobrado</b> desde hoy hasta ese mes, hasta cerrar el año. '
                        'La línea azul oscuro (<b>Schwab</b>) repite tu último pago como si nunca bajara; la azul claro '
                        '(<b>tu cálculo</b>) usa el <b>ritmo real reciente</b>, que capta la caída típica de los YieldMax. '
                        'Como ambas crecen mes a mes, <b>la separación se ensancha</b>: la franja ámbar es lo que Schwab '
                        'promete de más, y en el último mes equivale a la diferencia de <b>todo el año</b> (<b>Δ</b>).</p></div>',
                        unsafe_allow_html=True
                    )
                    _MES_ABBR = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
                                 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
                    _months = [_MES_ABBR[(datetime.date.today().month - 1 + _i) % 12] for _i in range(12)]
                    _m_sch = _sum_sproj / 12.0   # incremento mensual (total anual repartido parejo)
                    _m_cal = _sum_oproj / 12.0
                    _line_rows = []
                    _band_rows = []
                    for _i, _mname in enumerate(_months, start=1):
                        _sch_cum = _m_sch * _i
                        _cal_cum = _m_cal * _i
                        _line_rows.append({'Mes': _mname, 'Serie': 'Schwab (acumulado)', 'Monto': _sch_cum})
                        _line_rows.append({'Mes': _mname, 'Serie': 'Tu cálculo (acumulado)', 'Monto': _cal_cum})
                        _band_rows.append({'Mes': _mname, 'cal_cum': _cal_cum, 'sch_cum': _sch_cum})
                    _line_df = pd.DataFrame(_line_rows)
                    _band_df = pd.DataFrame(_band_rows)
                    _PROJ_SER = ['Schwab (acumulado)', 'Tu cálculo (acumulado)']
                    _PROJ_COL = ['#1E40AF', '#60A5FA']
                    _pline = alt.Chart(_line_df).mark_line(point=True, strokeWidth=2.5).encode(
                        x=alt.X('Mes:O', sort=_months, title=None,
                                axis=alt.Axis(labelAngle=0, labelFontSize=11)),
                        y=alt.Y('Monto:Q', title='USD acumulado', axis=alt.Axis(format='$,.0f')),
                        color=alt.Color('Serie:N', sort=_PROJ_SER,
                                        scale=alt.Scale(domain=_PROJ_SER, range=_PROJ_COL),
                                        legend=alt.Legend(title=None, orient='top', labelFontSize=11)),
                        tooltip=[alt.Tooltip('Mes:O', title='Mes'),
                                 alt.Tooltip('Serie:N', title='Serie'),
                                 alt.Tooltip('Monto:Q', format='$,.0f', title='USD acumulado al mes')],
                    )
                    _gap_pct = ((_sum_sproj / _sum_oproj - 1) * 100) if _sum_oproj > 0 else None
                    # Franja de discrepancia: el área entre tu acumulado y el de Schwab.
                    _pband = alt.Chart(_band_df).mark_area(opacity=0.12, color='#c9821f').encode(
                        x=alt.X('Mes:O', sort=_months),
                        y=alt.Y('cal_cum:Q'), y2=alt.Y2('sch_cum:Q'))
                    _player = [_pband, _pline]
                    if _gap_pct is not None and abs(_gap_pct) >= 1:
                        _lab_df = pd.DataFrame([{'Mes': _months[-1],
                                                 'Monto': _sum_sproj,
                                                 'Label': f'Δ {_gap_pct:+.0f}% · +${_sum_sproj - _sum_oproj:,.0f}/año'}])
                        _player.append(alt.Chart(_lab_df).mark_text(
                            baseline='bottom', align='right', dx=-4, dy=-8, fontSize=12, fontWeight='bold',
                            color='#c9821f', font='Inter, system-ui, sans-serif'
                        ).encode(x=alt.X('Mes:O', sort=_months), y=alt.Y('Monto:Q'),
                                 text=alt.Text('Label:N')))
                    _pchart = alt.layer(*_player).properties(
                        height=300, background=CHART_PALETTE["bg"]
                    ).configure_view(
                        strokeOpacity=0, fill=CHART_PALETTE["bg"]
                    ).configure_axis(
                        grid=True, gridColor=CHART_PALETTE["grid"], domainColor=CHART_PALETTE["axis"],
                        tickColor=CHART_PALETTE["axis"], labelColor=CHART_PALETTE["axis"],
                        titleColor=CHART_PALETTE["title"], labelFont='Inter, system-ui, sans-serif',
                        titleFont='Inter, system-ui, sans-serif', titleFontSize=11, titleFontWeight=500
                    ).configure_legend(labelColor=CHART_PALETTE["axis"])
                    _inc_exp.altair_chart(_pchart, use_container_width=True)
                    # Notas al pie: secundarias, en letra pequeña con * (no compiten con la gráfica).
                    _foot = ('* La acumulación reparte el total anual de forma pareja entre los 12 meses; es una '
                             'simplificación para comparar los dos métodos, no un calendario exacto de pagos.')
                    if _dropped:
                        _drop_txt = ', '.join(t for t, _ in _dropped)
                        _foot += (f'<br>* No se grafican {_drop_txt}: su dividendo es marginal y quedan fuera del '
                                  f'portafolio de ingresos.')
                    _inc_exp.markdown(
                        f'<p style="font-family:Inter,sans-serif;font-size:10px;color:#a3adb8;'
                        f'line-height:1.5;margin:4px 0 2px 0;">{_foot}</p>',
                        unsafe_allow_html=True
                    )

                    # Justificación auto-generada: por qué la proyección de Schwab está inflada.
                    _flagged = sorted(
                        [(t, d) for t, d in _proj.items() if (d.get('overstatement_pct') or 0) > logic.INCOME_OVERSTATE_FLAG_PCT],
                        key=lambda x: -(x[1]['overstatement_pct'] or 0))
                    _stable = [t for t, d in _proj.items() if abs(d.get('overstatement_pct') or 0) <= 5]
                    if _flagged:
                        def _pct_below(d):
                            a = d.get("anchor_per_payment") or 0
                            r = d.get("recent_per_payment") or 0
                            return (1 - r / a) * 100 if a else 0
                        _just_li = ''.join(
                            f'<li style="margin:7px 0;line-height:1.6;"><b>{t}</b>: Schwab supone que vas a seguir '
                            f'cobrando <b>{_money2(d.get("anchor_per_payment"))}</b> por acción en cada pago (tu último pago alto) '
                            f'y por eso proyecta <b>{_fmt_money(d.get("schwab_proj"))}</b> al año. Pero tus pagos recientes ya bajaron a '
                            f'<b>{_money2(d.get("recent_per_payment"))}</b> en promedio — '
                            f'<b style="color:#c9821f;">un {_pct_below(d):.0f}% más bajo</b>. Con ese ritmo real cobrarías unos '
                            f'<b style="color:#006497;">{_fmt_money(d.get("our_proj"))}</b> al año. '
                            f'(En los últimos 12 meses recibiste {_fmt_money(d.get("schwab_received_12m"))}.)</li>'
                            for t, d in _flagged
                        )
                        _stable_html = ''
                        if _stable:
                            _stable_html = (
                                '<p style="font-family:Inter,sans-serif;font-size:12px;color:#5a6b7a;margin:8px 0 0 0;line-height:1.6;">'
                                f'En cambio, en los fondos de dividendo estable ({", ".join(_stable)}) las dos proyecciones casi '
                                'coinciden. La diferencia solo aparece en los fondos tipo YieldMax: lo que pagan por acción va '
                                'bajando mes a mes, pero Schwab da por hecho que seguirás cobrando igual que en tu mejor pago.</p>'
                            )
                        _inc_exp.markdown(
                            '<div style="border-left:4px solid #e0a23c;background:#fbf7ef;padding:12px 16px;margin:6px 0 4px 0;">'
                            '<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;color:#021C36;margin:0 0 4px 0;">'
                            'Por qué la proyección de Schwab está inflada</p>'
                            '<ul style="font-family:Inter,sans-serif;font-size:12.5px;color:#444;margin:4px 0 0 0;padding-left:18px;">'
                            + _just_li + '</ul>' + _stable_html + '</div>',
                            unsafe_allow_html=True
                        )

                    # ── Tabla ROC: derivación del Retorno de Capital por ETF ──
                    def _roc_html(roc_acc, roc_pct, source=None, approx=False):
                        if roc_acc is None:
                            return '<span class="num" style="color:#b8c2cc;">n/d</span>'
                        # ROC NO se pinta de verde: un ROC alto no es "buen resultado" (es tu propio
                        # capital de vuelta). Ámbar = señal de cautela; rojo si fuera negativo.
                        c = '#c9821f' if roc_acc > 0 else ('#e05c5c' if roc_acc < 0 else '#8899aa')
                        _pct = f' ({roc_pct:.0f}%)' if roc_pct is not None else ''
                        _tilde = '~' if approx else ''
                        _tag = ''
                        if source == '19a':
                            _tag = ' <span style="font-size:9px;color:#8899aa;font-weight:600;">est.19a</span>'
                        elif approx:
                            _tag = ' <span style="font-size:9px;color:#8899aa;font-weight:600;">aprox*</span>'
                        return (f'<span class="num" style="color:{c};">'
                                f'{_tilde}{"−" if roc_acc < 0 else ""}${abs(roc_acc):,.0f}{_pct}{_tag}</span>')

                    _load_roc19a = getattr(logic, 'load_roc_19a', None)
                    _roc19a = _load_roc19a() if _load_roc19a else {}
                    _roc_19a_asof = None        # asof más viejo entre los fondos estimados por 19a
                    _roc_has_sells = False       # ¿algún ROC de bróker es aproximado por ventas?

                    def _val_html(mv, pkt):
                        # Valor actual; rojo si la posición vale menos que lo invertido (erosión de NAV).
                        if mv is None:
                            return '<span class="num" style="color:#b8c2cc;">n/d</span>'
                        c = '#e05c5c' if (pkt and mv < pkt) else '#0F172A'
                        return f'<span class="num" style="color:{c};">${mv:,.0f}</span>'

                    def _money_delta(calc, schwab):
                        # Celda "valor de la calculadora (Δ% vs Schwab)" inline, estilo ROC.
                        if calc is None:
                            return '<span class="num" style="color:#b8c2cc;">n/d</span>'
                        base = f'${calc:,.0f}'
                        if schwab is None or not calc:
                            return f'<span class="num">{base}</span>'
                        p = (schwab / calc - 1) * 100
                        col = '#e0a23c' if p > 5 else ('#4caf82' if abs(p) <= 5 else '#006497')
                        return (f'<span class="num">{base} '
                                f'<span style="font-size:9px;font-weight:600;color:{col};">{p:+.0f}%</span></span>')

                    _ROC_TIP = (
                        '<b>ROC (Retorno de Capital)</b> es la parte de tus distribuciones que el fondo '
                        'declara como <b>devolución de tu propio capital</b>, no rendimiento. La fuente '
                        'oficial es el <b>aviso 19a-1 del fondo</b> (= tu <b>1099-DIV casilla 3</b>, marcado '
                        '<b>est.19a</b>): si el 75% de lo que cobraste fue ROC, ese 75% era tu propio dinero '
                        'de vuelta, no ganancia.<br>'
                        'La app también puede <i>estimar</i> el ROC como <b>(Invertido + Reinvertido) − Costo '
                        'bróker</b> cuando tiene tu costo base; pero si <b>reinvertiste</b> tus distribuciones '
                        'esa resta <b>subestima</b> el ROC (la reinversión vuelve a subir tu base), por eso '
                        'manda el % oficial del fondo.<br>'
                        'Señal de "ingreso no gratis": si <b>Valor actual</b> cayó muy por debajo de lo que '
                        'pusiste pese a cobrar distribuciones (típico de YieldMax), gran parte de tu "ingreso" '
                        'fue erosión de tu capital.'
                    )

                    def _roc_th(label, tip, right=False, lbl=False):
                        # Header de columna con tooltip (mismo patrón .da-tip de la tabla comparativa).
                        _bc = 'da-tip-box r' if right else 'da-tip-box'
                        _cls = 'lbl da-tip' if lbl else 'da-tip'
                        return (f'<span class="{_cls}">{label}'
                                f'<span class="da-tip-i">i</span>'
                                f'<span class="{_bc}">{tip}</span></span>')

                    # Totales para los tooltips adaptativos de Total div (hist) y Proy. anual (ann).
                    _ts_hist, _tc_hist = _group_total(_rows_hist)
                    _ts_ann, _tc_ann = _group_total(_rows_ann)
                    _roc_sub = (
                        '<div class="da-roc-subhead">'
                        + _roc_th('ETF', 'El fondo o acción. Cada fila desglosa de dónde viene su ingreso y su ROC.', lbl=True)
                        + _roc_th('Total div.', _tip_for('hist', _ts_hist, _tc_hist))
                        + _roc_th('Div. pagados', 'Lo que de verdad entró a tu cuenta: lo reinvertido más lo recibido en efectivo, ya <b>neto</b> de la retención de impuesto a extranjeros (NRA). Por eso es menor que <b>Total div.</b> (el bruto antes de impuesto).')
                        + _roc_th('ROC', _ROC_TIP)
                        + _roc_th('Reinvertidos', 'La parte de tus distribuciones que se reinvirtió comprando más acciones (DRIP). <b>Sube</b> tu costo base y queda dentro de <b>Valor actual</b>.')
                        + _roc_th('En efectivo', 'La parte de tus distribuciones que cobraste en efectivo, sin reinvertir.')
                        + _roc_th('Invertido', 'El dinero de <b>tu propio bolsillo</b> que metiste a comprar acciones, sin contar lo reinvertido. Si tu historial está <b>incompleto</b>, la app puede mostrar aquí el costo base del bróker en su lugar.', right=True)
                        + _roc_th('Costo bróker', 'La base de costo que tu bróker reporta hoy; el ROC ya la <b>redujo</b>. No restes esta columna con «Invertido» para sacar el ROC: con reinversión esa resta lo <b>subestima</b>, por eso el ROC viene del % oficial del fondo (avisos 19a, marcado <b>est.19a</b>).', right=True)
                        + _roc_th('Valor actual', 'Cuánto vale hoy tu posición (ya <b>incluye el DRIP</b>: las acciones compradas por reinversión están dentro). En <b>rojo</b> si vale menos que lo invertido: señal de erosión del NAV.', right=True)
                        + _roc_th('Proy. anual', _tip_for('ann', _ts_ann, _tc_ann), right=True)
                        + '</div>'
                    )
                    _roc_body = ''
                    _r_paid = _r_drip = _r_cash = _r_pkt = _r_mv = 0.0
                    _r_basis = _r_roc = _r_dist_for_roc = 0.0
                    _r_basis_has = _r_roc_has = _r_any_19a = False
                    for _tk, _d in _items:
                        _rs = results.get(_tk, {})
                        _tot_div   = _d.get('our_received_total')      # bruto (antes de NRA)
                        _tot_div_s = _d.get('schwab_received_total')
                        _proy      = _d.get('our_proj')
                        _proy_s    = _d.get('schwab_proj')
                        _paid = _rs.get('total_dividends')
                        _drip = _rs.get('dividends_collected_drip')
                        _cash = _rs.get('dividends_collected_cash')
                        _pkt  = _rs.get('pocket_investment')
                        _mv   = _rs.get('market_value')
                        _basis = _rs.get('ib_cost_basis')
                        _roc_a = _rs.get('roc_accumulated')
                        _roc_p = _rs.get('roc_percent')
                        _roc_src = _rs.get('roc_source')
                        # ROC del bróker con ventas en la posición => aproximado (el invertido va neto de ventas).
                        _roc_approx = (_roc_src == 'broker'
                                       and ((_rs.get('shares_sold') or 0) > 0 or _rs.get('history_incomplete')))
                        if _roc_approx:
                            _roc_has_sells = True
                        if _roc_src == '19a':
                            _asof = (_roc19a.get(str(_tk).upper(), {}) or {}).get('asof')
                            if _asof and (_roc_19a_asof is None or _asof < _roc_19a_asof):
                                _roc_19a_asof = _asof
                        _roc_body += (f'<div class="da-roc-row"><span class="tk">{_tk}</span>'
                                      f'{_money_delta(_tot_div, _tot_div_s)}'
                                      f'<span class="num">{_fmt_money(_paid)}</span>'
                                      f'{_roc_html(_roc_a, _roc_p, _roc_src, _roc_approx)}'
                                      f'<span class="num">{_fmt_money(_drip)}</span>'
                                      f'<span class="num">{_fmt_money(_cash)}</span>'
                                      f'<span class="num">{_fmt_money(_pkt)}</span>'
                                      f'<span class="num">{_fmt_money(_basis)}</span>'
                                      f'{_val_html(_mv, _pkt)}'
                                      f'{_money_delta(_proy, _proy_s)}</div>')
                        _r_paid += (_paid or 0); _r_drip += (_drip or 0); _r_cash += (_cash or 0)
                        _r_pkt += (_pkt or 0); _r_mv += (_mv or 0)
                        if _basis is not None:
                            _r_basis += _basis; _r_basis_has = True
                        if _roc_a is not None:
                            _r_roc += _roc_a; _r_roc_has = True
                            _r_dist_for_roc += (_paid or 0)
                            if _roc_src == '19a':
                                _r_any_19a = True
                    _r_basis_disp = _r_basis if _r_basis_has else None
                    _r_roc_disp = _r_roc if _r_roc_has else None
                    _r_roc_pct = (_r_roc / _r_dist_for_roc * 100) if _r_dist_for_roc > 0 else None
                    _roc_total = ('<div class="da-roc-row da-roc-total"><span class="tk">TOTAL</span>'
                                  f'{_money_delta(_tc_hist, _ts_hist)}'
                                  f'<span class="num">{_fmt_money(_r_paid)}</span>'
                                  f'{_roc_html(_r_roc_disp, _r_roc_pct, "19a" if _r_any_19a else None)}'
                                  f'<span class="num">{_fmt_money(_r_drip)}</span>'
                                  f'<span class="num">{_fmt_money(_r_cash)}</span>'
                                  f'<span class="num">{_fmt_money(_r_pkt)}</span>'
                                  f'<span class="num">{_fmt_money(_r_basis_disp)}</span>'
                                  f'{_val_html(_r_mv, _r_pkt)}'
                                  f'{_money_delta(_tc_ann, _ts_ann)}</div>')
                    _inc_exp.markdown(
                        '<div style="margin:14px 0 2px 0;"><p style="font-family:Inter,sans-serif;font-size:13px;'
                        'font-weight:800;color:#021C36;margin:0 0 2px 0;">Ingreso, ROC y comparación con Schwab — consolidado</p>'
                        '<p style="font-family:Inter,sans-serif;font-size:12px;color:#8899aa;margin:0 0 8px 0;line-height:1.6;">'
                        'Una sola cuadrícula: <b>Total div.</b> (bruto, con su Δ% vs Schwab) → <b>Div. pagados</b> (neto) → '
                        '<b>ROC</b> a su lado, y al final la <b>Proyección anual</b>. Pasa el cursor por el ícono '
                        '<span style="font-size:9px;font-weight:700;color:#fff;background:#94a3b8;padding:0 4px;">i</span> '
                        'de cada columna (sobre todo <b>ROC</b>) para ver qué significa y cómo se calcula.</p></div>',
                        unsafe_allow_html=True
                    )
                    _inc_exp.markdown(
                        f'<div class="da-kpi-cell">{_roc_sub}{_roc_body}{_roc_total}</div>',
                        unsafe_allow_html=True
                    )
                    if not _r_basis_has and not _r_any_19a:
                        _inc_exp.caption('Sube el costo base de tu bróker en el paso de captura para calcular el ROC.')
                    if _roc_has_sells:
                        _inc_exp.caption('* ROC aproximado: la posición tiene ventas, así que "Invertido" va neto de ventas '
                                   'y el ROC del bróker es estimado. Es exacto en posiciones que solo acumulan.')
                    if _roc_19a_asof:
                        try:
                            _stale = (datetime.date.today() - datetime.date.fromisoformat(_roc_19a_asof)).days
                        except Exception:
                            _stale = 0
                        _warn = ' — dato desactualizado, revisa el refresco semanal (GitHub Action)' if _stale > 21 else ''
                        _inc_exp.caption(f'Cuando el ROC dice "est.19a" NO sale de restar Invertido − Costo bróker '
                                   f'(con reinversión esa resta subestima el ROC): es el % de devolución de capital que '
                                   f'el propio fondo declara en sus avisos 19a-1, el mismo dato que verás en tu 1099-DIV '
                                   f'casilla 3. Es la cifra que importa: ese % de tu "ingreso" fue tu propio capital de '
                                   f'vuelta, no ganancia — y si tu posición vale hoy menos de lo que pusiste, fue erosión '
                                   f'de tu capital. Actualizado al {_roc_19a_asof}.{_warn}')

                # ════ PANEL INFOGRAFÍA ROC (revertible · flag SHOW_ROC_INFOGRAPHIC) ════
                # Solo para fondos con ROC (YieldMax) en pérdida. Aditivo: solo LEE results.
                # try/except: si algo falla, no muestra nada y NO rompe la app.
                if SHOW_ROC_INFOGRAPHIC:
                    try:
                        from roc_infographic import roc_infographic_html
                        import streamlit.components.v1 as _components
                        for _it in results:
                            _is = results.get(_it) or {}
                            if not isinstance(_is, dict):
                                continue
                            _ira = _is.get('roc_accumulated'); _irp = _is.get('roc_percent')
                            _ipk = _is.get('pocket_investment'); _imv = _is.get('market_value')
                            _itd = _is.get('total_dividends') or 0
                            if (_ira and _irp and 25 <= _irp <= 100 and _ira <= _itd
                                    and _ipk and _imv is not None and _imv < _ipk):
                                _ig_html = roc_infographic_html(_is, _it)
                                if _ig_html:
                                    with st.expander(f"📊 Explicación visual del ROC — {_it}"):
                                        _components.html(_ig_html, height=2480, scrolling=True)
                    except Exception:
                        pass
                # ════ FIN PANEL INFOGRAFÍA ROC ════

            # ── Cuadrículas Schwab vs tu cálculo: inversión · dividendos · ROC ──
                _cmp_valid = sorted([t for t, s in results.items()
                                     if isinstance(s, dict) and 'error' not in s],
                                    key=lambda t: -(results[t].get('market_value') or 0))
                if _cmp_valid:
                    def _cell(v, kind='money'):
                        if v is None or v != v:   # None o NaN (precio de mercado no disponible) → n/d
                            return '<span class="num" style="color:#b8c2cc;">n/d</span>'
                        if kind == 'pct':
                            return f'<span class="num" style="color:{"#4caf82" if v >= 0 else "#e05c5c"};">{v:+.0f}%</span>'
                        return f'<span class="num">${v:,.0f}</span>'

                    def _delta(s, c, kind='money'):
                        if s is None or c is None or s != s or c != c:
                            return '<span class="pct" style="color:#b8c2cc;">—</span>'
                        if kind == 'pct':
                            d = s - c
                            col = '#8899aa' if abs(d) < 0.5 else ('#e0a23c' if d > 0 else '#006497')
                            return f'<span class="pct" style="color:{col};">{d:+.0f}pts</span>'
                        if not c:
                            return '<span class="pct" style="color:#b8c2cc;">—</span>'
                        p = (s / c - 1) * 100
                        col = '#8899aa' if abs(p) < 1 else ('#e0a23c' if p > 0 else '#006497')
                        return f'<span class="pct" style="color:{col};">{p:+.0f}%</span>'

                    def _grid_css(ncols):
                        return f'grid-template-columns:minmax(56px,1.2fr) repeat({ncols}, 1fr);'

                    def _hd(label, tip, right=False):
                        # Encabezado con ícono "i" + tooltip (mismo patrón .da-tip de la 1ª cuadrícula).
                        box = 'da-tip-box r' if right else 'da-tip-box'
                        return (f'<span class="da-tip">{label}'
                                f'<span class="da-tip-i">i</span>'
                                f'<span class="{box}">{tip}</span></span>')

                    def _triplet(groups, tks):
                        # groups: (label, accent, getter, kind, tip)
                        #   kind 'money'/'pct' -> getter(t)->(schwab, calc); muestra Calc + Δ (2 cols)
                        #   kind 'solo'        -> getter(t)->valor;          muestra solo el valor (1 col)
                        def _span(kind):
                            return 1 if kind == 'solo' else 2
                        ncols = sum(_span(_g[3]) for _g in groups)
                        g = _grid_css(ncols)
                        h = f'<div class="da-kpiwide-grouphead" style="{g}"><span></span>'
                        for idx, (lab, acc, _gt, kind, tip) in enumerate(groups):
                            box = 'da-tip-box r' if idx >= len(groups) - 2 else 'da-tip-box'
                            h += (f'<span class="grp da-tip" style="grid-column:span {_span(kind)};border-bottom-color:{acc};">{lab}'
                                  f'<span class="da-tip-i">i</span>'
                                  f'<span class="{box}">{tip}</span></span>')
                        h += f'</div><div class="da-kpiwide-subhead" style="{g}"><span class="lbl">ETF</span>'
                        for (lab, acc, getter, kind, _tp) in groups:
                            h += '<span>Calc</span>' if kind == 'solo' else '<span>Calc</span><span>Δ</span>'
                        h += '</div>'
                        tot = [[0.0, 0.0, False, False] for _ in groups]
                        for t in tks:
                            h += f'<div class="da-kpiwide-row" style="{g}"><span class="tk">{t}</span>'
                            for i, (lab, acc, getter, kind, _tp) in enumerate(groups):
                                if kind == 'solo':
                                    v = getter(t)
                                    h += _cell(v, 'money')
                                    if v is not None and v == v:
                                        tot[i][1] += v; tot[i][3] = True
                                    continue
                                s, c = getter(t)
                                # Solo el valor de la calculadora (c); el Δ sigue comparando contra Schwab (s).
                                h += _cell(c, kind) + _delta(s, c, kind)
                                if kind == 'money':
                                    if s is not None and s == s:
                                        tot[i][0] += s; tot[i][2] = True
                                    if c is not None and c == c:
                                        tot[i][1] += c; tot[i][3] = True
                            h += '</div>'
                        h += f'<div class="da-kpiwide-row da-kpiwide-total" style="{g}"><span class="tk">TOTAL</span>'
                        for i, (lab, acc, getter, kind, _tp) in enumerate(groups):
                            if kind == 'solo':
                                h += _cell(tot[i][1] if tot[i][3] else None, 'money')
                            elif kind == 'money':
                                ss = tot[i][0] if tot[i][2] else None
                                cc = tot[i][1] if tot[i][3] else None
                                h += _cell(cc, kind) + _delta(ss, cc, kind)
                            else:
                                h += '<span class="num" style="color:#b8c2cc;">—</span>' + '<span class="pct" style="color:#b8c2cc;">—</span>'
                        return h + '</div>'

                    def _subtitle(txt):
                        return (f'<p style="font-family:Inter,sans-serif;font-size:11px;font-weight:800;'
                                f'color:#021C36;letter-spacing:0.04em;text-transform:uppercase;'
                                f'margin:18px 0 6px 0;">{txt}</p>')

                    st.markdown(
                        '<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;color:#021C36;'
                        'margin:18px 0 6px 0;">Comparación con el broker · Schwab vs tu cálculo</p>',
                        unsafe_allow_html=True)
                    _cmp_exp = st.expander("Ver las 3 cuadrículas · inversión, dividendos y ROC", expanded=False)

                    # Cuadrícula A — rendimiento de la inversión
                    # Cascada de base de costo (columnas 'solo', un solo valor):
                    def _A_bolsillo(t):
                        return results[t].get('pocket_investment')                  # tu dinero, sin reinversión

                    def _A_real(t):
                        pk = results[t].get('pocket_investment')
                        dr = results[t].get('dividends_collected_drip') or 0
                        return (pk + dr) if pk is not None else None                # bolsillo + reinvertido (= costo real)

                    def _A_base_broker(t):
                        return results[t].get('ib_cost_basis')                      # base que reporta Schwab

                    def _A_base_roc(t):
                        # Solo aporta cuando el ROC viene del 19a. Con ROC del bróker,
                        # roc = (pocket+drip) − ib_basis, así que (pocket+drip) − roc == ib_basis
                        # (= Base · Schwab): sería una columna duplicada y engañosa → n/d.
                        if results[t].get('roc_source') != '19a':
                            return None
                        pk = results[t].get('pocket_investment')
                        dr = results[t].get('dividends_collected_drip') or 0
                        real = (pk + dr) if pk is not None else None
                        roc = results[t].get('roc_accumulated')
                        return (real - roc) if (real is not None and roc is not None) else None  # costo real − ROC real (19a)

                    def _A_val(t):
                        v = results[t].get('market_value')
                        return (v, v)

                    def _A_gain(t):
                        v = results[t].get('market_value'); cb = results[t].get('ib_cost_basis'); pk = results[t].get('pocket_investment')
                        return ((v - cb) if (v is not None and cb is not None) else None,
                                (v - pk) if (v is not None and pk is not None) else None)

                    def _A_ret(t):
                        v = results[t].get('market_value'); cb = results[t].get('ib_cost_basis'); pk = results[t].get('pocket_investment')
                        return (((v - cb) / cb * 100) if (v is not None and cb) else None,
                                ((v - pk) / pk * 100) if (v is not None and pk) else None)

                    _TIP_A_BOLS = ('<b>¿Qué es?</b> El dinero de <b>tu propio bolsillo</b> que metiste para comprar '
                                   'acciones, <b>sin contar lo reinvertido</b>. Es tu aporte real de capital, el punto de '
                                   'partida de la cascada.')
                    _TIP_A_REAL = ('<b>¿Qué es?</b> Tu bolsillo <b>más</b> los dividendos que reinvertiste (DRIP): todo el '
                                   'dinero que terminó comprando acciones. (Es el mismo número que <b>«Costo real»</b> en la '
                                   'cuadrícula de ROC.)')
                    _TIP_A_BROKER = ('<b>¿Qué es?</b> La base de costo que <b>Schwab reporta</b> hoy. El bróker suele bajar tu '
                                     'base por <b>menos</b> ROC del que el fondo declara, así que este número queda <b>más '
                                     'alto</b> de lo que sería con el ROC real. Por eso la app <b>no</b> calcula el ROC restando '
                                     'estas columnas: lo subestimaría.')
                    _TIP_A_BASEROC = ('<b>¿Qué es?</b> La misma base, pero restándole el <b>ROC real</b> que el fondo declaró '
                                      'en sus avisos <b>19a</b> (= 1099-DIV casilla 3). Sale <b>menor</b> que la base de Schwab; '
                                      'la <b>diferencia entre ambas es el ROC que Schwab no reflejó</b>. Indica cuánto de tu '
                                      'capital sigue «invertido de verdad» tras descontar lo que el fondo te devolvió. '
                                      'Solo se calcula cuando hay un ROC del fondo (19a); si no, aparece <b>n/d</b>.')
                    _TIP_A_VAL = ('<b>¿Qué es?</b> Cuánto vale hoy tu posición a precio de mercado (precio × acciones, '
                                  'ya <b>incluye el DRIP</b>). El valor de mercado no cambia entre métodos, por eso su '
                                  '<b>Δ</b> vs Schwab es <b>0%</b>.')
                    _TIP_A_GAIN = ('<b>¿Qué es?</b> Tu ganancia o pérdida en dólares: <b>Valor hoy − Tu bolsillo</b>. '
                                   'En verde si ganas, en rojo si pierdes. <b>Ojo:</b> es solo la plusvalía del precio; '
                                   '<b>no</b> incluye los dividendos que cobraste (esos van en la tabla de dividendos).')
                    _TIP_A_RET = ('<b>¿Qué es?</b> La misma ganancia o pérdida pero en <b>porcentaje</b> sobre lo '
                                  'invertido. Útil para comparar fondos de distinto tamaño. <b>No</b> incluye dividendos: '
                                  'es solo cuánto subió o bajó el precio de tu posición.')
                    _gridA = _triplet([('Tu bolsillo', '#021C36', _A_bolsillo, 'solo', _TIP_A_BOLS),
                                       ('+ Reinvertido', '#006497', _A_real, 'solo', _TIP_A_REAL),
                                       ('Base · Schwab', '#64748B', _A_base_broker, 'solo', _TIP_A_BROKER),
                                       ('Base · ROC real', '#c9821f', _A_base_roc, 'solo', _TIP_A_BASEROC),
                                       ('Valor hoy', '#006497', _A_val, 'money', _TIP_A_VAL),
                                       ('Rendim. $', '#4caf82', _A_gain, 'money', _TIP_A_GAIN),
                                       ('Rendim. %', '#2d3748', _A_ret, 'pct', _TIP_A_RET)], _cmp_valid)
                    _cmp_exp.markdown(_subtitle('Rendimiento de tu inversión') + f'<div class="da-kpi-cell">{_gridA}</div>',
                                      unsafe_allow_html=True)
                    _cmp_exp.caption("Primero la cascada de tu base de costo: «Tu bolsillo» (tu dinero) + lo «Reinvertido» = el "
                                     "capital real que compró acciones. Ese tramo final se muestra en dos escenarios: «Base · "
                                     "Schwab» es la base que reporta el bróker, y «Base · ROC real» es la que daría restando el ROC "
                                     "que el fondo declara en sus avisos 19a. La diferencia entre ambas es el ROC que Schwab no "
                                     "descontó de la base, por eso la app se guía por el 19a. Luego, «Valor hoy» y los rendimientos "
                                     "(solo plusvalía de precio, sin dividendos) con su Δ vs Schwab.")

                    # Cuadrícula B — dividendos (bruto · impuesto · neto)
                    _divtks = [t for t in _cmp_valid
                               if (results[t].get('total_dividends') or 0) > 0
                               or (_proj_all.get(t, {}) or {}).get('schwab_received_total')]
                    if _divtks:
                        def _B_gross(t):
                            p = _proj_all.get(t, {}) or {}
                            return (p.get('schwab_received_total'), p.get('our_received_total'))

                        def _B_tax(t):
                            x = results[t].get('withheld_tax_total')
                            return (x, x)

                        def _B_net_teo(t):              # bruto − impuesto; Δ vs Schwab
                            p = _proj_all.get(t, {}) or {}
                            gs = p.get('schwab_received_total'); gc = p.get('our_received_total')
                            x = results[t].get('withheld_tax_total') or 0
                            return ((gs - x) if gs is not None else None,
                                    (gc - x) if gc is not None else None)

                        def _B_net_real(t):             # transacciones reales (drip+cash); Δ vs el teórico
                            p = _proj_all.get(t, {}) or {}
                            gc = p.get('our_received_total')
                            x = results[t].get('withheld_tax_total') or 0
                            teo = (gc - x) if gc is not None else None   # base de comparación = teórico (calc)
                            real = results[t].get('total_dividends')     # = drip + cash, ya neto de NRA
                            return (teo, real)

                        def _B_drip(t):
                            d = results[t].get('dividends_collected_drip')
                            return (d, d)

                        def _B_cash(t):
                            c = results[t].get('dividends_collected_cash')
                            return (c, c)

                        # Orden = flujo del dinero (ver Obsidian: flujo-dinero-dividendo-orden-columnas):
                        # Bruto → Impuesto → Reinvertido → Efectivo → Neto real → Neto teórico.
                        _TIP_B_GROSS = ('<b>1. El punto de partida.</b> Todos los dividendos que el fondo declaró haberte '
                                        'pagado, <b>antes</b> de impuestos. <b>Δ</b> compara la calculadora con Schwab; cerca '
                                        'de <b>0%</b> = tu CSV está completo.')
                        _TIP_B_TAX = ('<b>2. Lo que te retienen.</b> El impuesto a extranjeros (<b>NRA</b>, ~30%) que EE.UU. '
                                      'descuenta del bruto antes de depositártelo. <b>No es un cargo extra:</b> ya venía '
                                      'restado. <b>Bruto − Impuesto = tu dinero limpio.</b>')
                        _TIP_B_DRIP = ('<b>3. Destino #1 de tu dinero limpio.</b> La parte que el <b>DRIP</b> reinvirtió '
                                       'automáticamente en más acciones. (En el CSV ya viene <b>neta</b> de impuesto.) Sale de '
                                       'tu CSV, por eso su Δ vs Schwab es 0%.')
                        _TIP_B_CASH = ('<b>4. Destino #2 de tu dinero limpio.</b> La parte que quedó en <b>efectivo</b>, sin '
                                       'reinvertir. Sale de tu CSV, por eso su Δ vs Schwab es 0%.')
                        _TIP_B_NET_REAL = ('<b>5. El resultado por transacciones.</b> <b>Reinvertidos + En efectivo</b> = a '
                                           'dónde fue de verdad tu dinero. El <b>Δ</b> lo compara con el neto teórico: cerca de '
                                           '<b>0%</b> = ambas rutas cuadran y puedes confiar; si difieren, a tu CSV puede '
                                           'faltarle algún movimiento.')
                        _TIP_B_NET_TEO = ('<b>6. El mismo neto, por la fórmula del impuesto.</b> <b>Bruto − Impuesto NRA</b>. '
                                          'Debería coincidir con el neto real; una diferencia de unos pocos dólares es normal '
                                          'porque el CSV guarda el reinvertido <b>neto</b> de impuesto pero el efectivo en '
                                          '<b>bruto</b>. El <b>Δ</b> es vs Schwab (completitud de datos). <b>Ojo:</b> ni el real '
                                          'ni el teórico son la distribución pre-impuesto — esa es el bruto de arriba.')
                        _gridB = _triplet([('Total div. (bruto)', '#021C36', _B_gross, 'money', _TIP_B_GROSS),
                                           ('Impuesto NRA', '#e05c5c', _B_tax, 'money', _TIP_B_TAX),
                                           ('Reinvertidos', '#006497', _B_drip, 'money', _TIP_B_DRIP),
                                           ('En efectivo', '#2d3748', _B_cash, 'money', _TIP_B_CASH),
                                           ('Neto recibido real', '#0F766E', _B_net_real, 'money', _TIP_B_NET_REAL),
                                           ('Neto recibido teórico', '#4caf82', _B_net_teo, 'money', _TIP_B_NET_TEO)], _divtks)
                        _formula_b = (
                            f'<div style="font-family:{_MONO_FONT};font-size:11px;color:#5a6b7a;line-height:1.8;'
                            'margin:-2px 0 10px 2px;letter-spacing:0.01em;">'
                            '<span style="display:inline-block;min-width:185px;color:#4caf82;font-weight:700;">'
                            'Neto recibido teórico</span>= Total dividendo bruto − Impuesto NRA<br>'
                            '<span style="display:inline-block;min-width:185px;color:#0F766E;font-weight:700;">'
                            'Neto recibido real</span>= Reinvertidos + En efectivo'
                            '<div style="font-family:Inter,sans-serif;font-size:10.5px;color:#8899aa;margin-top:3px;'
                            'font-style:italic;">Dos caminos al mismo neto: deberían coincidir.</div>'
                            '</div>'
                        )
                        _cmp_exp.markdown(_subtitle('Dividendos: el viaje del dinero, de bruto a neto') + _formula_b
                                          + f'<div class="da-kpi-cell">{_gridB}</div>',
                                          unsafe_allow_html=True)
                        _cmp_exp.caption("Sigue el dinero de izquierda a derecha: el fondo paga un dividendo «bruto»; EE.UU. "
                                         "retiene el «impuesto NRA»; lo que queda limpio se reparte en «Reinvertido» (DRIP) + «En "
                                         "efectivo», y su suma es el «Neto recibido real». Como verificación, el «Neto teórico» "
                                         "recalcula ese neto restando el impuesto al bruto. Ambos deberían coincidir; si difieren "
                                         "unos dólares es porque el CSV registra el reinvertido ya neto y el efectivo en bruto — no "
                                         "es un error, es un chequeo de que tus datos están completos.")

                    # Cuadrícula C — Retorno de Capital (ROC)
                    _roctks = [t for t in _cmp_valid
                               if results[t].get('roc_accumulated') is not None
                               or (results[t].get('total_dividends') or 0) > 0]
                    if _roctks:
                        gC = _grid_css(5)
                        _TIP_C_CB = ('<b>¿Qué es?</b> La base de costo que Schwab muestra hoy en tu posición. El ROC '
                                     'ya la <b>redujo</b>: cada vez que el fondo te devuelve capital, el bróker baja esta cifra.')
                        _TIP_C_REAL = ('<b>¿Qué es?</b> Lo que de verdad desplegaste: tu dinero de <b>bolsillo + lo '
                                       'reinvertido</b> (DRIP). No baja con el ROC, por eso suele ser mayor que el costo bróker.')
                        _TIP_C_ROCD = ('<b>¿Qué es?</b> El capital que el fondo te devolvió, en dólares: <b>costo real − '
                                       'costo bróker</b>. <b>No es ganancia</b>, es tu propio dinero de vuelta.')
                        _TIP_C_ROCP = ('<b>¿Qué es?</b> El ROC como <b>porcentaje</b> de tu base. Mientras más alto, '
                                       'mayor parte de tu costo fue devolución de capital y no rendimiento.')
                        _TIP_C_ROCDIV = ('<b>¿Qué es?</b> Qué parte de <b>todos tus dividendos</b> fue en realidad '
                                         'devolución de tu capital. Un 75% significa que de cada $100 cobrados, $75 eran '
                                         'tu propio dinero, no ganancia.')
                        hC = (f'<div class="da-kpiwide-subhead" style="{gC}"><span class="lbl">ETF</span>'
                              + _hd('Costo bróker', _TIP_C_CB)
                              + _hd('Costo real', _TIP_C_REAL)
                              + _hd('ROC $', _TIP_C_ROCD, right=True)
                              + _hd('ROC %', _TIP_C_ROCP, right=True)
                              + _hd('ROC ÷ div.', _TIP_C_ROCDIV, right=True)
                              + '</div>')
                        _tc1 = _tc2 = _tc3 = 0.0
                        _h1 = _h2 = _h3 = False
                        for t in _roctks:
                            cb = results[t].get('ib_cost_basis'); pk = results[t].get('pocket_investment')
                            dr = results[t].get('dividends_collected_drip') or 0
                            real = (pk + dr) if pk is not None else None
                            rocd = results[t].get('roc_accumulated'); rocp = results[t].get('roc_percent')
                            td = results[t].get('total_dividends') or 0
                            rocdiv = (rocd / td * 100) if (rocd is not None and td > 0) else None
                            hC += (f'<div class="da-kpiwide-row" style="{gC}"><span class="tk">{t}</span>'
                                   + _cell(cb) + _cell(real)
                                   + (f'<span class="num" style="color:#4caf82;">${rocd:,.0f}</span>' if rocd is not None
                                      else '<span class="num" style="color:#b8c2cc;">n/d</span>')
                                   + _cell(rocp, 'pct')
                                   + (f'<span class="num" style="color:#4caf82;">{rocdiv:.0f}%</span>' if rocdiv is not None
                                      else '<span class="num" style="color:#b8c2cc;">n/d</span>')
                                   + '</div>')
                            if cb is not None:
                                _tc1 += cb; _h1 = True
                            if real is not None:
                                _tc2 += real; _h2 = True
                            if rocd is not None:
                                _tc3 += rocd; _h3 = True
                        hC += (f'<div class="da-kpiwide-row da-kpiwide-total" style="{gC}"><span class="tk">TOTAL</span>'
                               + _cell(_tc1 if _h1 else None) + _cell(_tc2 if _h2 else None)
                               + (f'<span class="num" style="color:#4caf82;">${_tc3:,.0f}</span>' if _h3
                                  else '<span class="num" style="color:#b8c2cc;">—</span>')
                               + '<span class="num" style="color:#b8c2cc;">—</span>'
                               + '<span class="num" style="color:#b8c2cc;">—</span></div>')
                        _cmp_exp.markdown(_subtitle('Retorno de Capital (ROC)') + f'<div class="da-kpi-cell">{hC}</div>',
                                          unsafe_allow_html=True)
                        _cmp_exp.caption("«Costo bróker» es la base que muestra Schwab en tus posiciones; «Costo real» es lo que "
                                         "desplegaste (bolsillo + reinvertido). La diferencia es el ROC: capital que el fondo te "
                                         "devolvió y por el que el bróker bajó tu base. «ROC ÷ div.» es qué parte de tus dividendos "
                                         "fue en realidad devolución de tu capital. Si falta el costo del bróker, el ROC se estima "
                                         "con los avisos 19a del fondo.")

            # ── ¿De dónde viene tu ingreso? (dona de concentración) ──────
            if len(_income_contrib) >= 2:
                import altair as alt
                _don_items = sorted(_income_contrib.items(), key=lambda x: -x[1])
                if len(_don_items) > 6:
                    _don_items = _don_items[:6] + [('Otros', sum(v for _, v in _don_items[6:]))]
                _don_df = pd.DataFrame([{'Ticker': t, 'Ingreso': v} for t, v in _don_items])
                _don_total = _don_df['Ingreso'].sum()
                _don_df['Pct'] = _don_df['Ingreso'] / _don_total * 100 if _don_total else 0
                _don_palette = ['#021C36', '#006497', '#4caf82', '#166534', '#60A5FA', '#86EFAC', '#8899aa']
                _top_tk, _top_v = _don_items[0]
                _top_pct = (_top_v / _don_total * 100) if _don_total else 0
                st.markdown(
                    '<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;color:#021C36;'
                    'margin:18px 0 6px 0;">¿De dónde viene tu ingreso? (concentración)</p>',
                    unsafe_allow_html=True)
                _arc = (alt.Chart(_don_df).mark_arc(innerRadius=70, stroke='#fcf9f8', strokeWidth=2)
                        .encode(
                            theta=alt.Theta('Ingreso:Q', stack=True),
                            order=alt.Order('Ingreso:Q', sort='descending'),
                            color=alt.Color('Ticker:N',
                                            scale=alt.Scale(domain=list(_don_df['Ticker']), range=_don_palette),
                                            legend=alt.Legend(title=None, orient='right',
                                                              labelFont=_MONO_FONT, labelFontSize=11,
                                                              labelColor=_INK, symbolType='square', symbolSize=140)),
                            tooltip=[alt.Tooltip('Ticker:N', title='Activo'),
                                     alt.Tooltip('Ingreso:Q', format='$,.0f', title='Ingreso anual'),
                                     alt.Tooltip('Pct:Q', format='.1f', title='% del total')])
                        .properties(height=280)
                        .configure_view(strokeWidth=0))
                st.altair_chart(_arc, use_container_width=True)
                _top3 = _don_df['Pct'].iloc[:3].sum()
                _conc_txt = (f', y el <b style="color:#021C36;">{_top3:.0f}%</b> de tus 3 mayores.'
                             if len(_don_items) >= 3 else '.')
                st.markdown(
                    f'<p style="font-family:Inter,sans-serif;font-size:12.5px;color:#5a6b7a;'
                    f'margin:2px 0 12px 0;line-height:1.5;">El <b style="color:#021C36;">{_top_pct:.0f}%</b> '
                    f'de tu ingreso viene de <b style="color:#021C36;">{_top_tk}</b>{_conc_txt} '
                    'Una concentración alta significa que tu ingreso depende mucho de ese activo.</p>',
                    unsafe_allow_html=True)

            # ── ACORDEÓN: Detalle por portafolio ───────────────────────
            _da_section("Detalle por portafolio",
                        "Abre cada portafolio para ver sus posiciones y métricas de riesgo")
            tab_a = st.expander(
                f"PORTAFOLIO DE DIVIDENDOS   ·   income mensual   ·   {len(mode_a_tickers)} fondos",
                expanded=True,
            )

            # ── TAB A — Dividendos Income ──────────────────────────────
            with tab_a:
                shown_a = False

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
                        f'{_money2(stats.get("current_price"))} &nbsp;·&nbsp; '
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
                        f'<p class="da-tkpi-value" style="color:#16a34a;">${_proj_val:,.2f}</p>'
                        f'<p class="da-tkpi-sub">prom. últ. 3 meses</p>'
                    ) if _proj_val else (
                        '<p class="da-tkpi-value" style="color:#cbd5e1;">—</p>'
                        '<p class="da-tkpi-sub">sin historial</p>'
                    )
                    st.markdown(f"""
                    <div class="da-tkpi">
                        <div class="da-tkpi-cell">
                            <p class="da-tkpi-label">Acciones</p>
                            <p class="da-tkpi-value">{stats['shares_owned']:.4f}</p>
                            <p class="da-tkpi-sub">Compradas {_h_buys:.2f} · Vendidas {_h_sells:.2f}</p>
                        </div>
                        <div class="da-tkpi-cell">
                            <p class="da-tkpi-label">Tu inversión</p>
                            <p class="da-tkpi-value">${stats['pocket_investment']:,.2f}</p>
                            <p class="da-tkpi-sub">lo que pusiste de tu bolsillo</p>
                        </div>
                        <div class="da-tkpi-cell">
                            <p class="da-tkpi-label">Base broker (con ROC)</p>
                            {_roc_detail_card(stats)}
                        </div>
                        <div class="da-tkpi-cell">
                            <p class="da-tkpi-label">Valor de Mercado</p>
                            <p class="da-tkpi-value">${stats['market_value']:,.2f}</p>
                            <p class="da-tkpi-sub">@ ${stats['current_price']:,.2f} por acción</p>
                        </div>
                        <div class="da-tkpi-cell">
                            <p class="da-tkpi-label" style="color:#16a34a;">Próx. mes (est.)</p>
                            {_proj_cell}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    for _sp in stats.get('splits_detected', []):
                        _ratio = _sp['ratio']
                        _kind = "Split" if _ratio > 1 else "Reverse Split"
                        _tech_events.append({'date': _sp['date'], 'ticker': ticker, 'tipo': _kind, 'desc': f"{_ratio:.0f}:1 — las cantidades de acciones se ajustaron automáticamente."})

                    _q = logic.assess_ticker_quality(results, ticker)
                    if _q['level'] == 'unreliable':
                        st.warning(f"{ticker} · datos incompletos: {_q['reason']} {_q['action']}")
                    elif _q['level'] == 'reconciled':
                        _tech_events.append({'date': '', 'ticker': ticker, 'tipo': 'Reconciliación', 'desc': f"Reconciliado desde tu captura: {_q['reason']}"})

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
                            _tech_events.append({'date': _ca['date'], 'ticker': ticker, 'tipo': 'Dividendo especial', 'desc': f"${_ca.get('amount', 0):.4f} por acción"})

                    # Fase 9: Total Return primero — Capital + Income desglosados
                    _total_ret = stats['market_value'] + stats['dividends_collected_cash'] - stats['pocket_investment']
                    _total_ret_pct = (_total_ret / stats['pocket_investment'] * 100) if stats['pocket_investment'] > 0 else 0
                    _cap_comp = stats['market_value'] - stats['pocket_investment']
                    _inc_comp = stats['dividends_collected_cash']
                    _tr_color = "#4caf82" if _total_ret >= 0 else "#e05c5c"
                    _cap_color = "#4caf82" if _cap_comp >= 0 else "#e05c5c"
                    st.markdown(f"""
                    <div style="background:#F8FAFC;border-left:3px solid {_tr_color};padding:13px 18px;margin:8px 0 12px 0;">
                        <p style="font-family:Inter,sans-serif;font-size:10px;color:#64748B;font-weight:400;margin:0 0 4px 0;letter-spacing:0.08em;text-transform:uppercase;">Retorno Total</p>
                        <p style="font-family:'SFMono-Regular',ui-monospace,Menlo,Consolas,monospace;font-size:26px;font-weight:700;color:{_tr_color};margin:0 0 6px 0;letter-spacing:-0.01em;">${_total_ret:+,.2f} <span style="font-size:15px;font-weight:600;">({_total_ret_pct:+.2f}%)</span></p>
                        <p style="font-family:Inter,sans-serif;font-size:11.5px;color:#334155;margin:0;">Capital: <b style="color:{_cap_color};">${_cap_comp:+,.2f}</b> &nbsp;·&nbsp; Income: <b style="color:#16a34a;">${_inc_comp:,.2f}</b></p>
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

                    _render_interpretation(ticker)

                    if st.checkbox("Ver números crudos", key=f"raw_nums_{ticker}"):
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

                    st.divider()

                if shown_a:
                    _ca_rows = [
                        (ticker, stats) for ticker, stats in results.items()
                        if classify_map.get(ticker) == 'mode_a' and 'error' not in stats
                    ]
                    if len(_ca_rows) >= 2:
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

            # ── Proyección y escenarios (el resumen global se retiró) ──
            _da_section("Proyección a futuro y escenarios",
                        "Escenarios que tú controlas: cómo podría evolucionar tu portafolio y el rango de resultados posibles.")
            # ── Concentración por factor (riesgo de correlación oculta) ──
            _fc = logic.build_factor_concentration(results, classify_map)
            if _fc.get('factors') and len(_fc['factors']) >= 1:
                _accent = '#e0a23c' if _fc.get('hidden_correlation') else '#006497'
                _frows = ''.join(
                    f'<li style="margin:0 0 5px 0;"><b>{_f["factor"]}</b> — {_f["income_share_pct"]:.0f}% '
                    f'de tu ingreso ({", ".join(_f["tickers"])})</li>'
                    for _f in _fc['factors'][:5])
                _hdr = ("Correlación oculta detectada" if _fc.get('hidden_correlation')
                        else "De dónde viene tu ingreso (por factor)")
                _intro = ''
                if _fc.get('hidden_correlation'):
                    _top = _fc['factors'][0]
                    _intro = (f'<p style="font-family:Inter,sans-serif;font-size:12px;color:#664d1a;'
                              f'margin:0 0 8px 0;line-height:1.5;">Se ve diversificado, pero el '
                              f'<b>{_top["income_share_pct"]:.0f}% de tu ingreso depende de un solo factor '
                              f'({_top["factor"]})</b> vía {", ".join(_top["tickers"])}. Si ese factor cae, '
                              f'varias de tus posiciones caen juntas.</p>')
                st.markdown(
                    f'<div style="border-left:4px solid {_accent};background:#f6f8fa;padding:14px 18px;margin:6px 0 4px 0;">'
                    f'<p style="font-family:Inter,sans-serif;font-size:10px;color:{_accent};font-weight:800;'
                    f'letter-spacing:0.12em;text-transform:uppercase;margin:0 0 8px 0;">{_hdr}</p>'
                    + _intro +
                    '<ul style="font-family:Inter,sans-serif;font-size:12.5px;color:#333333;line-height:1.55;'
                    'margin:0;padding-left:18px;">' + _frows + '</ul>'
                    '<p style="font-family:Inter,sans-serif;font-size:10px;color:#8899aa;margin:8px 0 0 0;">'
                    'Ingreso forward anual agrupado por el subyacente de cada fondo (MSTR y COIN cuentan como '
                    'Bitcoin). Educativo — no es recomendación.</p></div>',
                    unsafe_allow_html=True
                )

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

            # ── Proyección a futuro (escenario) — inspirado en calculadoras DRIP ──
            _proj_elig = [t for t, s in results.items()
                          if isinstance(s, dict) and 'error' not in s
                          and (s.get('forward_yield') or 0) > 0
                          and (s.get('shares_owned') or 0) > 0 and (s.get('current_price') or 0) > 0]
            if _proj_elig:
                import altair as alt
                import pandas as pd
                with st.expander("Proyección a futuro (escenario)", expanded=False):
                    st.caption(
                        "Es un escenario, no una promesa: parte de tu yield actual y de supuestos que tú "
                        "controlas. Los YieldMax se proyectan con su erosión de NAV observada — nunca se asume "
                        "que su precio sube; los ETF de crecimiento usan los supuestos de abajo.")
                    _c1, _c2, _c3, _c4 = st.columns(4)
                    with _c1:
                        _p_hz = st.slider("Horizonte (años)", 1, 30, 5, key="proj_hz")
                    with _c2:
                        _p_contrib = st.number_input("Aporte mensual ($)", min_value=0.0, value=0.0,
                                                     step=50.0, key="proj_contrib")
                    with _c3:
                        _COUNTRIES = ['— sin impuesto —', 'Colombia', 'México', 'Chile', 'Perú',
                                      'Argentina', 'Brasil', 'Otros LATAM']
                        _p_country_sel = st.selectbox("Tu país (retención NRA)", _COUNTRIES, index=1,
                                                      key="proj_country",
                                                      help="No-residentes (NRA): 30% base sobre dividendos de "
                                                           "fuente EE.UU.; México 10% y Chile 15% por tratado. "
                                                           "El Retorno de Capital (ROC) reduce la retención real.")
                        _p_country = _p_country_sel if _p_country_sel in logic.NRA_COUNTRY_RATES else None
                    with _c4:
                        _p_drip = st.checkbox("Reinvertir (DRIP)", value=True, key="proj_drip")
                    _c5, _c6, _c7 = st.columns(3)
                    with _c5:
                        _p_divg = st.number_input("Crecim. dividendo % (solo ETFs)", min_value=-20.0,
                                                  max_value=30.0, value=0.0, step=1.0, key="proj_divg",
                                                  help="Aplica a ETF de dividendo/crecimiento. Los YieldMax "
                                                       "usan su erosión observada, no este valor.")
                    with _c6:
                        _p_priceg = st.number_input("Apreciación precio % (solo ETFs)", min_value=-20.0,
                                                    max_value=30.0, value=0.0, step=1.0, key="proj_priceg",
                                                    help="Aplica a ETF de crecimiento. En YieldMax se ignora.")
                    with _c7:
                        _p_goal = st.number_input("Meta ingreso mensual ($)", min_value=0.0, value=0.0,
                                                  step=100.0, key="proj_goal")

                    # Escenario del subyacente (YieldMax): "¿y si MSTR/BTC se recupera?".
                    # Deriva el NAV del fondo vía captura asimétrica calibrada a lo observado.
                    _ym_elig = [t for t in _proj_elig if classify_map.get(t) == 'mode_a'
                                and (results.get(t) or {}).get('underlying_cagr_recent') is not None]
                    _scenarios = {}
                    if _ym_elig:
                        with st.container(border=True):
                            st.markdown("**Escenario del subyacente (YieldMax) — ¿y si la acción base se recupera?**")
                            st.caption(
                                "Pon el retorno anual que esperas del SUBYACENTE (MSTR para MSTY, etc.) y el "
                                "fondo lo refleja con captura asimétrica: toma casi toda la caída pero poca de la "
                                "subida, menos su erosión estructural. El valor por defecto es el ritmo observado "
                                "del subyacente en los últimos 12 meses.")
                            for _ymt in _ym_elig:
                                _u = results[_ymt].get('underlying_ticker') or '?'
                                _uobs = results[_ymt].get('underlying_cagr_recent') or 0.0
                                _scenarios[_ymt] = st.number_input(
                                    f"{_ymt} — retorno anual de {_u} (%)", min_value=-90.0, max_value=300.0,
                                    value=float(round(_uobs, 1)), step=5.0, key=f"scen_{_ymt}")

                    _proj_params = {'horizon_years': _p_hz, 'monthly_contribution': _p_contrib,
                                    'drip': _p_drip, 'country': _p_country,
                                    'dividend_growth_pct': _p_divg, 'price_appreciation_pct': _p_priceg,
                                    'income_goal_monthly': (_p_goal or None),
                                    'underlying_scenarios': (_scenarios or None)}
                    _fwd = logic.project_portfolio_forward(results, _proj_params, classify_map)
                    _pf = _fwd['portfolio']
                    _pt = _fwd['per_ticker']

                    # Caveat de calidad: la proyección parte de costo/valor; si algún activo tiene
                    # costo incompleto (unreliable), su punto de partida es aproximado.
                    _proj_unrel = [t for t in _fwd['eligible']
                                   if logic.assess_ticker_quality(results, t)['level'] in ('unreliable', 'reconciled')]
                    if _proj_unrel:
                        st.caption("Aviso — " + ", ".join(_proj_unrel) + ": costo de origen incompleto (acciones "
                                   "por transferencia); su punto de partida y la proyección son aproximados.")

                    if _pf.get('yearly'):
                        _last = _pf['yearly'][-1]
                        _m1, _m2, _m3, _m4 = st.columns(4)
                        _m1.metric("Valor proyectado", f"${_pf['end_value']:,.0f}",
                                   f"{(_pf['end_value']/_pf['start_value']-1)*100:+.0f}% vs hoy"
                                   if _pf['start_value'] > 0 else None)
                        _m2.metric("Ingreso anual (último año)", f"${_last['annual_income']:,.0f}",
                                   f"${_last['annual_income']/12:,.0f}/mes")
                        _m3.metric("Dividendos netos acumulados", f"${_pf['cumulative_dividends_net']:,.0f}")
                        _m4.metric("Ventaja del DRIP", f"${_pf['drip_advantage']:,.0f}",
                                   help="Cuánto más vale el portafolio reinvirtiendo vs tomando los "
                                        "dividendos en efectivo, al final del horizonte.")
                        if _p_country:
                            st.caption(f"Ingresos netos de la retención NRA de {_p_country} (efectiva por activo, "
                                       "ya descontado el escudo del ROC). El histórico de arriba sigue en bruto.")
                        if _pf.get('income_goal_monthly'):
                            _gy = _pf.get('income_goal_year')
                            st.caption(f"Meta de ${_pf['income_goal_monthly']:,.0f}/mes: "
                                       + (f"se alcanza alrededor del año {_gy}." if _gy
                                          else "no se alcanza dentro del horizonte proyectado."))

                        # Gráfico: valor del portafolio y dividendos acumulados por año.
                        _crows = []
                        for _r in _pf['yearly']:
                            _crows.append({'Año': _r['year'], 'Serie': 'Valor del portafolio',
                                           'Valor': _r['portfolio_value']})
                            _crows.append({'Año': _r['year'], 'Serie': 'Dividendos acum. (neto)',
                                           'Valor': _r['cumulative_dividends']})
                        _cdf = pd.DataFrame(_crows)
                        _chart = alt.Chart(_cdf).mark_line(point=True).encode(
                            x=alt.X('Año:O', title='Año'),
                            y=alt.Y('Valor:Q', title='USD', axis=alt.Axis(format='$,.0f')),
                            color=alt.Color('Serie:N', scale=alt.Scale(
                                domain=['Valor del portafolio', 'Dividendos acum. (neto)'],
                                range=['#006497', '#4caf82']),
                                legend=alt.Legend(title=None, orient='top')),
                            tooltip=['Año', 'Serie', alt.Tooltip('Valor:Q', format='$,.0f')],
                        ).properties(height=280)
                        st.altair_chart(_chart, use_container_width=True)

                        # Tabla por activo: yield forward vs realizado + proyección.
                        _trows = []
                        for _tk in _fwd['eligible']:
                            _e = _pt[_tk]
                            _yl = _e['yearly'][-1]['annual_income'] if _e['yearly'] else None
                            _row = {
                                'Activo': _tk,
                                'Tipo': 'YieldMax' if _e['is_yieldmax'] else 'ETF',
                                'Yield forward': f"{_e['forward_yield']:.1f}%",
                                'Yield realizado': (f"{_e['realized_yield']:.1f}%"
                                                    if _e.get('realized_yield') is not None else '—'),
                                'Valor hoy': f"${_e['start_value']:,.0f}",
                                'Valor proyectado': f"${_e['end_value']:,.0f}",
                                'Ingreso anual final': f"${_yl:,.0f}" if _yl is not None else '—',
                                'Dividendos netos acum.': f"${_e['cumulative_dividends_net']:,.0f}",
                            }
                            if _p_country:
                                _row['Retención efectiva'] = f"{_e.get('tax_effective_rate', 0):.1f}%"
                            _trows.append(_row)
                        st.dataframe(pd.DataFrame(_trows), use_container_width=True, hide_index=True)
                        st.caption(
                            "Yield forward = último pago anualizado (lo que anuncian). "
                            "Yield realizado = lo que de verdad cobraste en los últimos 12 meses. "
                            "Cuando el forward es mucho mayor, la cifra de marketing es optimista.")

                        # Aviso de cambio de frecuencia de pago (mensual → semanal, etc.).
                        _cad_changes = []
                        for _tk in _fwd['eligible']:
                            _cc = (results.get(_tk) or {}).get('cadence_change')
                            if isinstance(_cc, dict) and _cc.get('changed'):
                                _cad_changes.append(f"**{_tk}**: {_cc['old_label']} → {_cc['recent_label']}")
                        if _cad_changes:
                            st.caption("Cambio de frecuencia de pago detectado — " + " · ".join(_cad_changes)
                                       + ". El forward usa la frecuencia actual; el realizado (lo cobrado) no se afecta.")

                        # YieldMax: carrera ingreso vs erosión de NAV + breakeven.
                        _ym = [(_tk, _pt[_tk]) for _tk in _fwd['eligible'] if _pt[_tk]['is_yieldmax']]
                        if _ym:
                            st.markdown("**YieldMax — ingreso vs erosión de capital (comprar y cobrar, sin DRIP)**")
                            _wlbl = {'12m': 'últimos 12 meses', 'vida': 'toda la vida del fondo',
                                     'manual': 'tu valor manual', 'default': 'estimación por defecto'}
                            st.caption(
                                "La línea verde es el dinero que cobras; la roja, cuánto cayó tu capital. "
                                "El cruce es el punto en que el ingreso ya cubrió la pérdida del precio. "
                                "El total return honesto incluye ambos efectos — no solo el yield de portada. "
                                "La erosión se estima con el decaimiento de los "
                                + _wlbl.get(next((_pt[t].get('decay_window') for t, _ in _ym), '12m'), 'últimos 12 meses')
                                + " (puedes ajustar el supuesto arriba).")
                            for _tk, _e in _ym:
                                _bm = _e.get('breakeven_month')
                                _be_txt = (f"breakeven al mes {_bm}" if _bm
                                           else "no alcanza breakeven en el horizonte")
                                _roc = _e.get('roc_fraction_pct')
                                _roc_txt = (f" · ~{_roc:.0f}% de las distribuciones es retorno de capital (no es rendimiento)"
                                            if _roc is not None else "")
                                _htr = _e.get('honest_total_return_pct')
                                st.markdown(
                                    f"**{_tk}** — yield portada {_e['forward_yield']:.0f}% · "
                                    f"total return honesto {('%+.0f%%' % _htr) if _htr is not None else 'n/d'} "
                                    f"a {_p_hz} año(s) · {_be_txt}{_roc_txt}")
                                # Veredicto de salud del NAV: ¿el ROC es destructivo o contable?
                                _rs = results.get(_tk, {}) or {}
                                _asof_days = None
                                _r19 = logic.load_roc_19a().get(str(_tk).upper())
                                if _r19 and _r19.get('asof'):
                                    try:
                                        _asof_days = (datetime.date.today()
                                                      - datetime.date.fromisoformat(_r19['asof'])).days
                                    except Exception:
                                        _asof_days = None
                                _prev_v = logic.latest_health_verdict(_tk)
                                _verdict = logic.classify_roc_health(
                                    roc_pct=_roc,
                                    price_cagr=(_rs.get('price_cagr_recent')
                                                if _rs.get('price_cagr_recent') is not None
                                                else _rs.get('price_cagr')),
                                    total_return_pct=_htr,
                                    history_days=_rs.get('price_history_days'),
                                    roc_asof_days=_asof_days,
                                    prev_verdict=_prev_v,
                                    underlying_cagr=_rs.get('underlying_cagr_recent'))
                                _vreason = _verdict['reason']
                                if _verdict['verdict'] == 'destructive':
                                    _u = _rs.get('underlying_cagr_recent')
                                    _f = _rs.get('price_cagr_recent')
                                    _und = _rs.get('underlying_ticker')
                                    if _u is not None and _f is not None and _und:
                                        _vreason += (f" En 12m el NAV de {_tk} hizo {_f:+.0f}% mientras "
                                                     f"{str(_und).upper()} hizo {_u:+.0f}%.")
                                # Capa SIMPLE: titular + medidor Sano↔Destruyéndose + explicación llana.
                                _score = _verdict.get('gauge_score')
                                if _score is None:
                                    _gauge_html = ("<div style='height:14px;background:#e9ecef;color:#888;"
                                                   "font-size:10px;text-align:center;line-height:14px;'>"
                                                   "no medible aún</div>")
                                else:
                                    _gauge_html = (
                                        "<div style='position:relative;height:14px;margin:6px 0 2px 0;"
                                        "background:linear-gradient(90deg,#4caf82 0%,#e0a23c 50%,#e05c5c 100%);'>"
                                        f"<div style='position:absolute;top:-3px;left:{_score:.0f}%;width:3px;"
                                        "height:20px;background:#021C36;transform:translateX(-50%);'></div></div>"
                                        "<div style='display:flex;justify-content:space-between;font-size:10px;"
                                        "color:#888;'><span>Sano</span><span>Destruyéndose</span></div>")
                                st.markdown(
                                    f"<div style='margin:6px 0 2px 0;font-weight:700;font-size:15px;"
                                    f"color:{_verdict['color']};'>{_verdict['headline']}</div>"
                                    f"{_gauge_html}"
                                    f"<div style='font-size:12.5px;color:#333;margin:6px 0 2px 0;"
                                    f"line-height:1.5;'>{_verdict['plain']}</div>",
                                    unsafe_allow_html=True)
                                # Capa TÉCNICA: detalle con los números, plegado. Se usa <details> HTML
                                # (no st.expander) porque esta sección YA vive dentro de un expander
                                # y Streamlit no permite expanders anidados.
                                _navc = _rs.get('price_cagr_recent')
                                if _navc is None:
                                    _navc = _rs.get('price_cagr')
                                _nums = []
                                if _navc is not None: _nums.append(f"NAV {_navc:+.0f}%/año")
                                if _roc is not None:  _nums.append(f"ROC {_roc:.0f}%")
                                if _htr is not None:  _nums.append(f"total return honesto {_htr:+.0f}%")
                                st.markdown(
                                    "<details style='margin:2px 0 8px 0;'>"
                                    "<summary style='cursor:pointer;font-size:12px;color:#006497;'>"
                                    "Ver detalle técnico</summary>"
                                    + (f"<div style='font-size:12px;color:#666;margin:4px 0;'>"
                                       f"{' · '.join(_nums)}</div>" if _nums else "")
                                    + f"<div style='font-size:12.5px;color:#333;line-height:1.5;'>"
                                      f"{_vreason}</div></details>",
                                    unsafe_allow_html=True)
                                # Evolución histórica del veredicto (se llena semanal vía el Action).
                                _vh = logic.load_roc_health_history().get(str(_tk).upper()) or []
                                if len(_vh) >= 2:
                                    _vhdf = pd.DataFrame(_vh)
                                    _vhdf['date'] = pd.to_datetime(_vhdf['date'])
                                    _vlabels = {'destructive': 'Destructivo', 'accounting': 'Contable',
                                                'mixed': 'Vigilar', 'insufficient': 'Sin datos'}
                                    _vhdf['Veredicto'] = _vhdf['verdict'].map(_vlabels).fillna(_vhdf['verdict'])
                                    _vchart = alt.Chart(_vhdf).mark_line(point=True, color='#8a8f98').encode(
                                        x=alt.X('date:T', title='Fecha'),
                                        y=alt.Y('price_cagr:Q', title='NAV %/año'),
                                        color=alt.Color('Veredicto:N', scale=alt.Scale(
                                            domain=['Destructivo', 'Contable', 'Vigilar', 'Sin datos'],
                                            range=['#e05c5c', '#4caf82', '#e0a23c', '#8a8f98'])),
                                        tooltip=['date:T', 'Veredicto:N', 'roc_pct:Q', 'price_cagr:Q'],
                                    ).properties(height=130)
                                    st.altair_chart(_vchart, use_container_width=True)
                                _exp = logic.build_underlying_exposure(results, _tk)
                                if _exp['lines']:
                                    st.markdown(
                                        "<div style='background:#f6f8fa;border-left:3px solid #021C36;"
                                        "padding:8px 12px;margin:2px 0 8px 0;font-size:12.5px;color:#333;"
                                        "line-height:1.5;'><b>Exposición al subyacente (riesgo asimétrico):"
                                        "</b><br>" + "<br>".join(_exp['lines']) + "</div>",
                                        unsafe_allow_html=True)
                                _rr = _e.get('race') or []
                                if _rr:
                                    _rdf_rows = []
                                    for _row in _rr:
                                        _rdf_rows.append({'Mes': _row['month'], 'Serie': 'Ingreso acum. (neto)',
                                                          'Valor': _row['cum_income_net']})
                                        _rdf_rows.append({'Mes': _row['month'], 'Serie': 'Pérdida de capital',
                                                          'Valor': _row['capital_loss']})
                                    _rdf = pd.DataFrame(_rdf_rows)
                                    _rchart = alt.Chart(_rdf).mark_line().encode(
                                        x=alt.X('Mes:Q', title='Mes'),
                                        y=alt.Y('Valor:Q', title='USD', axis=alt.Axis(format='$,.0f')),
                                        color=alt.Color('Serie:N', scale=alt.Scale(
                                            domain=['Ingreso acum. (neto)', 'Pérdida de capital'],
                                            range=['#4caf82', '#e05c5c']),
                                            legend=alt.Legend(title=None, orient='top')),
                                        tooltip=['Mes', 'Serie', alt.Tooltip('Valor:Q', format='$,.0f')],
                                    ).properties(height=220)
                                    st.altair_chart(_rchart, use_container_width=True)

                        # ── Módulo fiscal NRA: tu retención real por país × escudo ROC ──
                        if _p_country:
                            with st.container(border=True):
                                st.markdown(f"**Módulo fiscal — tu retención real en {_p_country}**")
                                _tax_rows = []
                                for _tk in _fwd['eligible']:
                                    _bd = logic.nra_tax_breakdown(_p_country, logic._ticker_roc_fraction(_tk, results))
                                    _tax_rows.append({'Activo': _tk, 'ROC': f"{_bd['roc_fraction']:.0f}%",
                                                      'Nominal (creías)': f"{_bd['base_rate']:.0f}%",
                                                      'Efectiva (real)': f"{_bd['effective_rate']:.1f}%"})
                                st.dataframe(pd.DataFrame(_tax_rows), use_container_width=True, hide_index=True)
                                st.caption("ROC reciente (últimos ~12 avisos 19a) — no el histórico "
                                           "completo del fondo, para reflejar mejor el escudo fiscal vigente.")
                                _best = max(_fwd['eligible'], default=None,
                                            key=lambda t: logic._ticker_roc_fraction(t, results))
                                if _best is not None:
                                    _eb = _pt[_best]
                                    _gross = _eb['forward_yield'] / 100.0 * _eb['start_value']
                                    _bd = logic.nra_tax_breakdown(
                                        _p_country, logic._ticker_roc_fraction(_best, results),
                                        nominal_income=_gross)
                                    st.markdown(f"**Ejemplo con {_best}** (ingreso anual estimado ${_gross:,.0f}):")
                                    for _l in _bd['lines']:
                                        st.markdown(f"- {_l}")
                                    st.caption(_bd['audit_note'])

                        # ── Escenarios (Monte Carlo): rango de resultados, no una sola línea ──
                        with st.container(border=True):
                            st.markdown("**Escenarios (Monte Carlo) — el rango de lo que puede pasar**")
                            _mcc1, _mcc2 = st.columns(2)
                            with _mcc1:
                                _mc_infl = st.number_input("Inflación anual % (para la vista real)", min_value=0.0,
                                                           max_value=20.0, value=3.0, step=0.5, key="mc_infl")
                            with _mcc2:
                                _mc_real = st.checkbox("Mostrar en poder de compra de hoy (descontar inflación)",
                                                       value=False, key="mc_real")
                            _mc = logic.monte_carlo_projection(
                                results, {**_proj_params, 'inflation_pct': _mc_infl, 'real_view': _mc_real},
                                classify_map, n_paths=500, seed=123)
                            if _mc['bands']:
                                _f = _mc['final']
                                _k1, _k2 = st.columns(2)
                                _k1.metric("Valor final — rango probable (p10–p90)",
                                           f"${_f['p10']:,.0f} – ${_f['p90']:,.0f}",
                                           f"mediana ${_f['p50']:,.0f}")
                                if _mc['prob_goal'] is not None:
                                    _k2.metric("Prob. de cumplir tu meta de ingreso", f"{_mc['prob_goal']:.0f}%")
                                _brows = []
                                for _b in _mc['bands']:
                                    _brows += [{'Año': _b['year'], 'Banda': 'Pesimista (p10)', 'Valor': _b['p10']},
                                               {'Año': _b['year'], 'Banda': 'Mediana (p50)', 'Valor': _b['p50']},
                                               {'Año': _b['year'], 'Banda': 'Optimista (p90)', 'Valor': _b['p90']}]
                                _bchart = alt.Chart(pd.DataFrame(_brows)).mark_line(point=True).encode(
                                    x=alt.X('Año:O', title='Año'),
                                    y=alt.Y('Valor:Q', title='USD', axis=alt.Axis(format='$,.0f')),
                                    color=alt.Color('Banda:N', scale=alt.Scale(
                                        domain=['Pesimista (p10)', 'Mediana (p50)', 'Optimista (p90)'],
                                        range=['#e05c5c', '#021C36', '#4caf82']),
                                        legend=alt.Legend(title=None, orient='top')),
                                    tooltip=['Año', 'Banda', alt.Tooltip('Valor:Q', format='$,.0f')],
                                ).properties(height=280)
                                st.altair_chart(_bchart, use_container_width=True)
                                st.caption(
                                    f"{_mc['n_paths']} escenarios aleatorios usando la volatilidad observada de "
                                    "cada activo, con un retorno distinto cada año (riesgo de secuencia). "
                                    + ("Valores en poder de compra de hoy (inflación descontada)."
                                       if _mc['real_view'] else "Valores nominales."))

                        st.caption("Proyección educativa con supuestos tuyos — no es recomendación de compra o venta.")

            # ── Comparativa de estrategias (auto-calculada) ───────────
            if strat_results_cached:
                _da_section("Comparativa de estrategias",
                            "Tu portafolio completo vs. poner ese mismo dinero, en las mismas fechas, todo en un solo ETF")
                _sr_invested = sum(s.get('pocket_investment', 0) for s in results.values() if 'error' not in s)
                _sr_value    = sum(s.get('market_value', 0) for s in results.values() if 'error' not in s)
                _sr_ret_pct  = (_sr_value - _sr_invested) / _sr_invested * 100 if _sr_invested > 0 else 0
                st.markdown(
                    f'<div style="font-family:Inter,sans-serif;font-size:12.5px;color:#5a6b7a;line-height:1.65;'
                    f'margin:0 0 16px 0;">Tomamos el <b>mismo dinero</b> que aportaste '
                    f'(<b>${_sr_invested:,.0f}</b> en total) en las <b>mismas fechas</b>, y lo invertimos 100% en cada ETF. '
                    f'La línea oscura es <b>tu portafolio real completo</b> — dividendos + crecimiento juntos; '
                    f'las demás responden: “¿y si ese mismo dinero hubiera ido todo a un solo fondo?”. '
                    f'Mismo capital, mismo timing: solo cambia el destino.</div>',
                    unsafe_allow_html=True
                )
                import altair as alt
                import yfinance as yf

                # ── Serie temporal: Portafolio Real vs Estrategias ────────
                _ts_key = f"_strat_ts_v5_{st.session_state.get('_file_id', 'x')}"
                if _ts_key not in st.session_state:
                    # Timing de aportes reconstruido desde la curva 'Invested Capital'
                    # (daily_trend) de cada posición: robusto a CSV incompletos y a
                    # transferencias que las filas "Buy" crudas no capturan. Es la misma
                    # curva de capital que dibuja la línea del portafolio real.
                    _flow_by_date = {}
                    for _t, _s in results.items():
                        if 'error' in _s or 'daily_trend' not in _s:
                            continue
                        _ic = _s['daily_trend'].get('Invested Capital')
                        if _ic is None or len(_ic) == 0:
                            continue
                        _inc = _ic.diff()
                        if len(_inc) > 0:
                            _inc.iloc[0] = _ic.iloc[0]   # día 0 = despliegue inicial
                        for _d, _amt in _inc[_inc > 0].items():
                            _key = pd.Timestamp(_d).normalize()
                            _flow_by_date[_key] = _flow_by_date.get(_key, 0.0) + float(_amt)
                    _buy_flows_ts = sorted(_flow_by_date.items(), key=lambda x: x[0])

                    # Respaldo: filas "buy" crudas si no hubo curva utilizable.
                    if not _buy_flows_ts:
                        for _t, _s in results.items():
                            if 'error' not in _s and 'history' in _s:
                                _h = _s['history']
                                _buys = _h[_h['Action'].str.lower().str.contains('buy', na=False)]
                                for _, _row in _buys.iterrows():
                                    try:
                                        _buy_flows_ts.append(
                                            (pd.to_datetime(_row['Date']).normalize(), abs(float(_row['Amount']))))
                                    except Exception:
                                        pass
                        _buy_flows_ts.sort(key=lambda x: x[0])

                    # Respaldo final: todo el capital desplegado en la fecha más temprana.
                    if not _buy_flows_ts and _sr_invested > 0:
                        _earliest = None
                        for _t, _s in results.items():
                            if 'error' not in _s and 'daily_trend' in _s and len(_s['daily_trend']) > 0:
                                _d0 = pd.Timestamp(_s['daily_trend'].index[0]).normalize()
                                _earliest = _d0 if _earliest is None else min(_earliest, _d0)
                        if _earliest is not None:
                            _buy_flows_ts = [(_earliest, _sr_invested)]

                    # Normaliza el capital total a "Invertido" (pocket_investment) para
                    # comparar 1:1 (mismo capital, mismo timing) en todas las filas.
                    _flow_total = sum(a for _, a in _buy_flows_ts)
                    if _flow_total > 0 and _sr_invested > 0:
                        _scale = _sr_invested / _flow_total
                        _buy_flows_ts = [(d, a * _scale) for d, a in _buy_flows_ts]

                    _frames_ts = []
                    _etf_final_vals = {}

                    _real_ts = None
                    for _t, _s in results.items():
                        if 'error' not in _s and 'daily_trend' in _s:
                            _col = _s['daily_trend']['User Total Value']
                            _real_ts = _col.copy() if _real_ts is None else _real_ts.add(_col, fill_value=0)
                    if _real_ts is not None:
                        _r_df = _real_ts.reset_index()
                        _r_df.columns = ['Fecha', 'Valor']
                        _r_df['Estrategia'] = 'Tu Portafolio Real'
                        _frames_ts.append(_r_df)

                    if _buy_flows_ts:
                        _ts_start = _buy_flows_ts[0][0] - pd.Timedelta(days=10)
                        _ts_end   = pd.Timestamp.today()
                        _etf_map  = {'SCHB': 'Todo en SCHB', 'XLK': 'Todo en XLK', 'YMAX': 'Todo en YMAX', 'SMH': 'Todo en SMH'}
                        for _etf_tk, _etf_lbl in _etf_map.items():
                            try:
                                _raw = yf.download(_etf_tk, start=_ts_start, end=_ts_end,
                                                   auto_adjust=True, progress=False)
                                if _raw is None or _raw.empty:
                                    continue
                                if isinstance(_raw.columns, pd.MultiIndex):
                                    _raw.columns = _raw.columns.get_level_values(0)
                                _prices_ts = _raw['Close']
                                if isinstance(_prices_ts, pd.DataFrame):
                                    _prices_ts = _prices_ts.iloc[:, 0]
                                _prices_ts = _prices_ts.dropna()
                                if _prices_ts.empty:
                                    continue
                                # Normalize index to tz-naive dates
                                if getattr(_prices_ts.index, 'tz', None) is not None:
                                    _prices_ts.index = _prices_ts.index.tz_localize(None)
                                _prices_ts.index = _prices_ts.index.normalize()
                                _port_val = pd.Series(0.0, index=_prices_ts.index)
                                for _bd, _amt in _buy_flows_ts:
                                    if float(_amt) <= 0:
                                        continue
                                    _bd_norm = pd.Timestamp(_bd).normalize()
                                    # Find first available price on or after buy date
                                    _future = _prices_ts[_prices_ts.index >= _bd_norm]
                                    if _future.empty:
                                        continue
                                    _buy_p = float(_future.iloc[0])
                                    if _buy_p <= 0:
                                        continue
                                    _shares = float(_amt) / _buy_p
                                    # Accumulate shares × price for all dates from buy date onward
                                    _mask = _prices_ts.index >= _bd_norm
                                    _port_val[_mask] += _shares * _prices_ts[_mask]
                                _vals = _port_val[_port_val > 0]
                                if not _vals.empty:
                                    _etf_final_vals[_etf_lbl] = float(_vals.iloc[-1])
                                _e_df = _vals.reset_index()
                                _e_df.columns = ['Fecha', 'Valor']
                                _e_df['Estrategia'] = _etf_lbl
                                _frames_ts.append(_e_df)
                            except Exception:
                                pass

                    st.session_state[_ts_key] = {
                        'df': pd.concat(_frames_ts, ignore_index=True) if _frames_ts else pd.DataFrame(),
                        'etf_final': _etf_final_vals,
                    }

                _ts_cache    = st.session_state[_ts_key]
                _line_data   = _ts_cache['df']
                _etf_finals  = _ts_cache.get('etf_final', {})

                # Tabla derivada de valores finales de la serie temporal
                _all_strats = {'real': {'label': 'Tu Portafolio Real', 'total_invested': _sr_invested,
                                        'final_value': _sr_value, 'return_pct': _sr_ret_pct, 'ok': True}}
                for _etf_lbl in ['Todo en SCHB', 'Todo en XLK', 'Todo en YMAX', 'Todo en SMH']:
                    if _etf_lbl in _etf_finals:
                        _fv = _etf_finals[_etf_lbl]
                        _rp = (_fv - _sr_invested) / _sr_invested * 100 if _sr_invested > 0 else 0
                        _all_strats[_etf_lbl] = {'label': _etf_lbl, 'total_invested': _sr_invested,
                                                 'final_value': _fv, 'return_pct': _rp, 'ok': True}
                    else:
                        _all_strats[_etf_lbl] = {'label': _etf_lbl, 'total_invested': _sr_invested,
                                                 'final_value': None, 'return_pct': None, 'ok': False}
                _sorted_strats = sorted(
                    _all_strats.items(),
                    key=lambda x: (0, -x[1]['return_pct']) if x[1]['ok'] else (1, 0.0)
                )
                _color_domain = ['Tu Portafolio Real', 'Todo en SCHB', 'Todo en XLK', 'Todo en YMAX', 'Todo en SMH']
                _color_range  = ['#021C36', '#006497', '#2e7d5d', '#c8102e', '#e67e22']
                _short = {'Tu Portafolio Real': 'TU PORTAFOLIO', 'Todo en SCHB': 'SCHB',
                          'Todo en XLK': 'XLK', 'Todo en YMAX': 'YMAX', 'Todo en SMH': 'SMH'}
                _cmap = dict(zip(_color_domain, _color_range))
                _MONO = "'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace"

                # ── Cuadro de rendimiento integrado (monoespaciado; sirve también de leyenda) ──
                _rows_html = ""
                for _, v in _sorted_strats:
                    _c = _cmap.get(v['label'], '#64748B')
                    _is_real = v['label'] == 'Tu Portafolio Real'
                    _nm = _short.get(v['label'], v['label'])
                    _fin = f"${v['final_value']:,.0f}" if v['ok'] else "—"
                    _ret = f"{v['return_pct']:+.2f}%" if v['ok'] else "sin datos"
                    _bg = '#eef4f8' if _is_real else 'transparent'
                    _wt = '800' if _is_real else '500'
                    _rows_html += (
                        f'<div style="display:flex;align-items:center;gap:10px;padding:7px 12px;background:{_bg};'
                        f'border-bottom:1px solid #eef2f5;">'
                        f'<span style="width:9px;height:9px;background:{_c};flex-shrink:0;"></span>'
                        f'<span style="font-family:{_MONO};font-size:12px;font-weight:{_wt};color:#021C36;'
                        f'flex:1;letter-spacing:0.02em;">{_nm}</span>'
                        f'<span style="font-family:{_MONO};font-size:11.5px;color:#64748B;width:92px;text-align:right;">{_fin}</span>'
                        f'<span style="font-family:{_MONO};font-size:12px;font-weight:{_wt};color:{_c};width:92px;text-align:right;">{_ret}</span>'
                        f'</div>'
                    )
                st.markdown(
                    '<div style="border:1px solid #e2e8f0;margin:2px 0 12px 0;">'
                    '<div style="display:flex;align-items:center;gap:10px;padding:6px 12px;background:#021C36;">'
                    '<span style="width:9px;flex-shrink:0;"></span>'
                    f'<span style="font-family:{_MONO};font-size:9.5px;font-weight:700;color:#9fb3c8;flex:1;letter-spacing:0.12em;">ESTRATEGIA</span>'
                    f'<span style="font-family:{_MONO};font-size:9.5px;font-weight:700;color:#9fb3c8;width:92px;text-align:right;letter-spacing:0.08em;">VALOR HOY</span>'
                    f'<span style="font-family:{_MONO};font-size:9.5px;font-weight:700;color:#9fb3c8;width:92px;text-align:right;letter-spacing:0.08em;">RETORNO</span>'
                    '</div>'
                    + _rows_html + '</div>',
                    unsafe_allow_html=True
                )
                _missing_etfs = [v['label'].replace('Todo en ', '') for _, v in _sorted_strats if not v['ok']]
                if _missing_etfs:
                    st.caption(f"No se pudieron descargar precios de: {', '.join(_missing_etfs)} (yfinance). "
                               "Vuelve a intentar en unos segundos.")

                if not _line_data.empty:
                    _line_data['Fecha'] = pd.to_datetime(_line_data['Fecha'])
                    _AXIS_GRAY = '#64748B'
                    _color = alt.Color('Estrategia:N',
                        scale=alt.Scale(domain=_color_domain, range=_color_range), legend=None)
                    _xaxis = alt.Axis(format='%b %Y', labelAngle=0,
                        tickCount={'interval': 'year', 'step': 1}, grid=False, domain=False, ticks=False,
                        labelFont=_MONO, labelFontSize=10, labelColor=_AXIS_GRAY, labelPadding=8, title=None)
                    _yaxis = alt.Axis(format='$,.0f', tickCount=5, grid=True, gridColor='#e2e8f0',
                        gridDash=[3, 3], gridOpacity=0.7, domain=False, ticks=False,
                        labelFont=_MONO, labelFontSize=10, labelColor=_AXIS_GRAY, title=None)
                    _tip = [alt.Tooltip('Fecha:T', title='Fecha', format='%d %b %Y'),
                            alt.Tooltip('Estrategia:N', title='Estrategia'),
                            alt.Tooltip('Valor:Q', title='Valor', format='$,.0f')]
                    _bench = _line_data[_line_data['Estrategia'] != 'Tu Portafolio Real']
                    _real  = _line_data[_line_data['Estrategia'] == 'Tu Portafolio Real']
                    _l_bench = alt.Chart(_bench).mark_line(strokeWidth=1.5, opacity=0.6).encode(
                        x=alt.X('Fecha:T', axis=_xaxis), y=alt.Y('Valor:Q', axis=_yaxis), color=_color, tooltip=_tip)
                    _l_real = alt.Chart(_real).mark_line(strokeWidth=3, opacity=1.0).encode(
                        x=alt.X('Fecha:T', axis=_xaxis), y=alt.Y('Valor:Q', axis=_yaxis), color=_color, tooltip=_tip)
                    _last = _line_data.loc[_line_data.groupby('Estrategia')['Fecha'].idxmax()].copy()
                    _last['lbl'] = _last['Estrategia'].map(_short)
                    # De-colisión vertical de las etiquetas finales + leader cuando dos
                    # estrategias terminan con valores casi iguales (evita que se encimen).
                    _yspan = max(float(_line_data['Valor'].max()), 1.0)
                    _gap = _yspan * (22.0 / 440.0)   # ~22px mínimos entre etiquetas
                    _last = _last.sort_values('Valor', ascending=False).reset_index(drop=True)
                    _ly, _prev = [], None
                    for _v in _last['Valor']:
                        _y = float(_v)
                        if _prev is not None and (_prev - _y) < _gap:
                            _y = _prev - _gap
                        _ly.append(_y); _prev = _y
                    _last['lbl_y'] = _ly
                    _last['moved'] = (_last['lbl_y'] - _last['Valor']).abs() > (_yspan * 3.0 / 440.0)
                    _leader = alt.Chart(_last[_last['moved']]).mark_rule(
                        strokeWidth=0.8, opacity=0.5, clip=False).encode(
                        x=alt.X('Fecha:T'), y=alt.Y('Valor:Q'), y2=alt.Y2('lbl_y'), color=_color)
                    _lab = alt.Chart(_last).mark_text(align='left', dx=8, fontSize=10, font=_MONO,
                        fontWeight='bold', clip=False).encode(
                        x=alt.X('Fecha:T'), y=alt.Y('lbl_y:Q'), text='lbl:N', color=_color)
                    _chart = (_l_bench + _l_real + _leader + _lab).properties(
                        height=440, background=CHART_PALETTE['bg'],
                        padding={'left': 4, 'top': 8, 'right': 96, 'bottom': 4}
                    ).configure_view(strokeOpacity=0, fill=CHART_PALETTE['bg'])
                    st.altair_chart(_chart, use_container_width=True)
                st.markdown('<hr class="da-section-rule">', unsafe_allow_html=True)

            # ── YieldMax vs Crecimiento — total return desde inception ──
            if mode_a_tickers:
                import altair as alt
                _YMAX_COMPARE = ['MSTY', 'CONY', 'TSLY', 'NVDY']
                _GROWTH_COMPARE = ['XLK', 'SMH', 'SCHB']
                _da_section("YieldMax vs Crecimiento — total return desde inception",
                            "Precio + todas las distribuciones reinvertidas, normalizado a base 100")

                st.markdown(
                    '<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;color:#021C36;'
                    'margin:6px 0 4px 0;">MSTY · CONY · TSLY · NVDY — entre sí (base 100)</p>',
                    unsafe_allow_html=True)
                _ymax_incep = logic.build_yieldmax_total_return_series(_YMAX_COMPARE)
                if not _ymax_incep.empty:
                    _latest_start = _ymax_incep.groupby('Ticker')['Fecha'].min().max()
                    _ymax_df = logic.build_yieldmax_total_return_series(
                        _YMAX_COMPARE, start=_latest_start.strftime('%Y-%m-%d'))
                    if not _ymax_df.empty:
                        _ymax_chart = alt.Chart(_ymax_df).mark_line(strokeWidth=2.2).encode(
                            x=alt.X('Fecha:T', title=None, axis=_ed_axis('x', fmt='%b %Y', label_angle=0, year_ticks=True)),
                            y=alt.Y('Valor:Q', axis=_ed_axis('y', fmt=',.0f', title='Base 100')),
                            color=alt.Color('Ticker:N', legend=alt.Legend(orient='bottom', title=None, labelFontSize=12)),
                            tooltip=[alt.Tooltip('Fecha:T', title='Fecha', format='%d %b %Y'),
                                     alt.Tooltip('Ticker:N', title='Fondo'),
                                     alt.Tooltip('Valor:Q', title='Índice (base 100)', format=',.1f')]
                        ).properties(height=360, background=CHART_PALETTE['bg']).configure_view(
                            strokeOpacity=0, fill=CHART_PALETTE['bg'])
                        st.altair_chart(_ymax_chart, use_container_width=True)
                        st.caption(f"Las 4 arrancan en {_latest_start.strftime('%d %b %Y')} — la inception más "
                                   "reciente de las cuatro — para comparar en la misma ventana. Base 100.")
                else:
                    st.caption("No se pudieron descargar precios de MSTY/CONY/TSLY/NVDY (yfinance).")

                _ymax_in_port = [t for t in _YMAX_COMPARE if t in mode_a_tickers]
                _anchor_default = (max(_ymax_in_port,
                                       key=lambda t: (results.get(t, {}) or {}).get('market_value') or 0)
                                   if _ymax_in_port else 'MSTY')
                _anchor_idx = _YMAX_COMPARE.index(_anchor_default) if _anchor_default in _YMAX_COMPARE else 0
                _anchor_tk = st.selectbox("Fondo YieldMax ancla", _YMAX_COMPARE, index=_anchor_idx,
                                          key="_ymax_anchor_select")
                st.markdown(
                    f'<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;color:#021C36;'
                    f'margin:14px 0 4px 0;">{_anchor_tk} vs XLK · SMH · SCHB — desde la inception de '
                    f'{_anchor_tk} (base 100)</p>',
                    unsafe_allow_html=True)
                _anchor_series = logic.build_yieldmax_total_return_series([_anchor_tk])
                if not _anchor_series.empty:
                    _anchor_start = _anchor_series['Fecha'].min()
                    _vs_growth_df = logic.build_yieldmax_total_return_series(
                        [_anchor_tk] + _GROWTH_COMPARE, start=_anchor_start.strftime('%Y-%m-%d'))
                    if not _vs_growth_df.empty:
                        _vs_chart = alt.Chart(_vs_growth_df).mark_line(strokeWidth=2.2).encode(
                            x=alt.X('Fecha:T', title=None, axis=_ed_axis('x', fmt='%b %Y', label_angle=0, year_ticks=True)),
                            y=alt.Y('Valor:Q', axis=_ed_axis('y', fmt=',.0f', title='Base 100')),
                            color=alt.Color('Ticker:N', legend=alt.Legend(orient='bottom', title=None, labelFontSize=12)),
                            tooltip=[alt.Tooltip('Fecha:T', title='Fecha', format='%d %b %Y'),
                                     alt.Tooltip('Ticker:N', title='Activo'),
                                     alt.Tooltip('Valor:Q', title='Índice (base 100)', format=',.1f')]
                        ).properties(height=360, background=CHART_PALETTE['bg']).configure_view(
                            strokeOpacity=0, fill=CHART_PALETTE['bg'])
                        st.altair_chart(_vs_chart, use_container_width=True)
                        st.caption(f"Todas arrancan en {_anchor_start.strftime('%d %b %Y')} — inception de "
                                   f"{_anchor_tk} — base 100. Incluye distribuciones reinvertidas.")
                else:
                    st.caption(f"No se pudo descargar precio de {_anchor_tk} (yfinance).")
                st.markdown('<hr class="da-section-rule">', unsafe_allow_html=True)

            # ── Confianza de datos (la sección "En corto · ingreso" se eliminó) ──
            _n_total = _n_total or len(results)
            if _n_total:
                _conf_extra = _n_total - _n_exact
                if _conf_extra <= 0:
                    _conf_c = '#4caf82'
                    _conf_msg = 'todas tus posiciones tienen el costo exacto'
                else:
                    _conf_c = '#006497' if _n_exact > 0 else '#e0a23c'
                    _conf_msg = (f'{_conf_extra} con costo aproximado: al CSV le faltan las compras originales. '
                                 'Sube la foto de posiciones para volverlas exactas.')
                st.markdown('<hr class="da-section-rule">', unsafe_allow_html=True)
                st.markdown(
                    '<div class="da-kpi-bar" style="grid-template-columns:1fr;">'
                    f'<div class="da-kpi-cell" style="border-top-color:{_conf_c};">'
                    '<p class="da-kpi-label">Confianza de datos</p>'
                    f'<p class="da-kpi-value" style="color:{_conf_c};">{_n_exact}/{_n_total} con costo exacto</p>'
                    f'<p class="da-kpi-delta" style="color:#8899aa;">{_conf_msg}</p></div>'
                    '</div>',
                    unsafe_allow_html=True)

            # ── Calidad de datos y validación cruzada (al final, expandible) ──
            st.markdown('<hr class="da-section-rule">', unsafe_allow_html=True)
            with st.expander("Calidad de datos y validación cruzada de ingresos", expanded=False):
                st.caption("Detalle técnico: cómo se reconciliaron tus posiciones y la verificación "
                           "del dividendo bruto contra el reporte de ingresos del broker.")
                _render_data_quality_panel()

            # ── Notas técnicas y eventos corporativos (consolidado, al pie) ──
            if _tech_events:
                _ev_sorted = sorted(_tech_events, key=lambda e: (e.get('date') or '9999-99', e.get('ticker', '')))
                _ev_rows = ""
                for _ev in _ev_sorted:
                    _ed = _ev.get('date') or '—'
                    _ev_rows += (
                        '<tr style="border-bottom:1px solid #eef2f5;">'
                        f'<td style="padding:7px 14px;font-family:SFMono-Regular,ui-monospace,Menlo,Consolas,monospace;font-size:11px;color:#64748B;white-space:nowrap;">{_ed}</td>'
                        f'<td style="padding:7px 14px;font-family:Inter,sans-serif;font-size:11px;font-weight:700;color:#021C36;">{_ev["ticker"]}</td>'
                        f'<td style="padding:7px 14px;font-family:Inter,sans-serif;font-size:11px;font-weight:600;color:#006497;white-space:nowrap;">{_ev["tipo"]}</td>'
                        f'<td style="padding:7px 14px;font-family:Inter,sans-serif;font-size:11.5px;color:#445566;line-height:1.45;">{_ev["desc"]}</td>'
                        '</tr>'
                    )
                st.markdown('<hr class="da-section-rule">', unsafe_allow_html=True)
                with st.expander(f"⚙️  Notas Técnicas y Eventos Corporativos Detectados · {len(_tech_events)} evento(s)", expanded=False):
                    st.markdown(
                        '<table style="width:100%;border-collapse:collapse;margin-top:2px;">'
                        '<thead><tr style="border-bottom:2px solid #021C36;">'
                        '<th style="padding:7px 14px;text-align:left;font-family:Inter,sans-serif;font-size:9px;font-weight:700;letter-spacing:0.11em;text-transform:uppercase;color:#8899aa;">Fecha</th>'
                        '<th style="padding:7px 14px;text-align:left;font-family:Inter,sans-serif;font-size:9px;font-weight:700;letter-spacing:0.11em;text-transform:uppercase;color:#8899aa;">Ticker</th>'
                        '<th style="padding:7px 14px;text-align:left;font-family:Inter,sans-serif;font-size:9px;font-weight:700;letter-spacing:0.11em;text-transform:uppercase;color:#8899aa;">Evento</th>'
                        '<th style="padding:7px 14px;text-align:left;font-family:Inter,sans-serif;font-size:9px;font-weight:700;letter-spacing:0.11em;text-transform:uppercase;color:#8899aa;">Detalle</th>'
                        '</tr></thead><tbody>'
                        + _ev_rows +
                        '</tbody></table>',
                        unsafe_allow_html=True
                    )
                    st.caption("Eventos detectados automáticamente al procesar tu archivo (splits, reconciliaciones desde captura y dividendos especiales). Las cantidades y métricas ya están ajustadas.")

    except Exception as e:
        import traceback
        st.error(f"Error procesando el archivo: {e}")
        with st.expander("Ver detalles del error (Stacktrace)"):
            st.code(traceback.format_exc())

elif input_method == "Simulación Teórica":
    st.markdown(
        '<div style="display:flex;align-items:baseline;gap:14px;margin:8px 0 18px 0;padding-bottom:10px;border-bottom:2px solid #021C36;">'
        '<span style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;color:#006497;letter-spacing:0.06em;">SIM</span>'
        '<div><p style="font-family:Inter,sans-serif;font-size:17px;font-weight:800;color:#021C36;letter-spacing:-0.01em;margin:0;">Simulación Teórica</p>'
        '<p style="font-family:Inter,sans-serif;font-size:12px;color:#8899aa;margin:3px 0 0 0;">Backtests hipotéticos con precios y dividendos históricos reales — no usa tu portafolio.</p></div></div>',
        unsafe_allow_html=True
    )

    sim_mode = st.radio(
        "Tipo de simulación:",
        ["Un activo: DRIP vs No-DRIP", "Dos portafolios: Dividendos vs Crecimiento"],
        horizontal=True
    )

    if sim_mode == "Un activo: DRIP vs No-DRIP":
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
                    x=alt.X('Date:T', axis=_ed_axis('x', fmt='%b %Y', label_angle=0, year_ticks=True)),
                    y=alt.Y('Valor:Q', axis=_ed_axis('y', fmt='$,.0f', title='Valor ($)')),
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
                ).configure_legend(
                    labelColor=CHART_PALETTE["title"], titleColor=CHART_PALETTE["axis"],
                    labelFont='Inter, system-ui, sans-serif', titleFont='Inter, system-ui, sans-serif',
                    labelFontSize=12, titleFontSize=10, titleFontWeight=500,
                    strokeColor='transparent', fillColor=CHART_PALETTE["bg"], padding=12, cornerRadius=0
                )
                st.altair_chart(_sim_chart, use_container_width=True)

    elif sim_mode == "Dos portafolios: Dividendos vs Crecimiento":
        st.caption("Reparte un mismo capital entre dos canastas (Dividendos y Crecimiento) en 5 mezclas distintas y compara la evolución real de cada parte. El monto de cada canasta se reparte equitativamente entre sus tickers y los dividendos se reinvierten (DRIP). Backtest con precios y dividendos históricos reales.")

        c1, c2 = st.columns(2)
        div_csv = c1.text_input("Portafolio Dividendos", "TSLY, NVDY, MSTY, CONY")
        growth_csv = c2.text_input("Portafolio Crecimiento", "SCHB, XLK, SMH")

        c3, c4 = st.columns(2)
        capital = c3.select_slider("Capital invertido ($)", options=[0, 1000, 2000, 5000, 10000], value=1000)
        years = c4.select_slider("Periodo de inversión (años)", options=[0, 1, 2, 3], value=2)

        if st.button("Comparar mezclas"):
            if capital <= 0 or years <= 0:
                st.info("Selecciona un capital y un periodo mayores a 0 para ver la evolución.")
            else:
                start_date_pp = (datetime.date.today() - datetime.timedelta(days=int(years) * 365)).isoformat()
                with st.spinner("Simulando portafolios..."):
                    comp, comp_err = logic.simulate_portfolio_comparison_cached(div_csv, growth_csv, 1.0, start_date_pp)

                if comp is None:
                    st.error(f"Error: {comp_err}")
                else:
                    for _w in comp.get('warnings', []):
                        st.info(_w)

                    st.success(f"Comparación completada · backtest desde {comp['common_start']}")

                    import altair as alt
                    hist = comp['history']  # Dividendos / Crecimiento normalizados a $1 por canasta
                    _r_div = comp['dividend_stats']['roi_percent']
                    _r_grw = comp['growth_stats']['roi_percent']

                    a1, a2 = st.columns(2)
                    a1.metric("Portafolio Dividendos (DRIP)", f"{_r_div:+.1f}%", help=div_csv)
                    a2.metric("Portafolio Crecimiento (DRIP)", f"{_r_grw:+.1f}%", help=growth_csv)
                    st.caption("Rendimiento de cada canasta en el periodo. Es el mismo para las 5 mezclas; lo que cambia es cuánto capital pones en cada una.")

                    _DIV_COLOR, _GRW_COLOR = "#006497", "#021C36"
                    _scale = alt.Scale(domain=['Dividendos', 'Crecimiento'], range=[_DIV_COLOR, _GRW_COLOR])

                    def _mix_chart(_long):
                        _area = alt.Chart(_long).mark_area(opacity=0.06, interpolate='monotone').encode(
                            x=alt.X('Date:T'),
                            y=alt.Y('Valor:Q'),
                            color=alt.Color('Parte:N', scale=_scale, legend=None)
                        )
                        _lines = alt.Chart(_long).mark_line(strokeWidth=2.5, interpolate='monotone').encode(
                            x=alt.X('Date:T', axis=_ed_axis('x', fmt='%b %Y', label_angle=0, year_ticks=True)),
                            y=alt.Y('Valor:Q', axis=_ed_axis('y', fmt='$,.0f', title='Valor ($)')),
                            color=alt.Color('Parte:N', scale=_scale, title='Parte'),
                            tooltip=[
                                alt.Tooltip('Date:T', format='%Y-%m-%d', title='Fecha'),
                                alt.Tooltip('Parte:N', title='Parte'),
                                alt.Tooltip('Valor:Q', format='$,.2f', title='Valor')
                            ]
                        )
                        return (_area + _lines).properties(
                            height=240, background=CHART_PALETTE["bg"]
                        ).configure_view(
                            strokeOpacity=0, fill=CHART_PALETTE["bg"]
                        ).configure_legend(
                            labelColor=CHART_PALETTE["title"], titleColor=CHART_PALETTE["axis"],
                            labelFont='Inter, system-ui, sans-serif', titleFont='Inter, system-ui, sans-serif',
                            labelFontSize=12, titleFontSize=10, titleFontWeight=500,
                            strokeColor='transparent', fillColor=CHART_PALETTE["bg"], padding=12, cornerRadius=0
                        )

                    _MIXES = [(80, 20), (60, 40), (50, 50), (40, 60), (20, 80)]
                    st.subheader("Evolución por mezcla de asignación")
                    for _i, (_pd, _pg) in enumerate(_MIXES, 1):
                        _div_part = hist['Dividendos'] * capital * (_pd / 100.0)
                        _grw_part = hist['Crecimiento'] * capital * (_pg / 100.0)
                        _df = pd.DataFrame({
                            'Date': hist.index,
                            'Dividendos': _div_part.values,
                            'Crecimiento': _grw_part.values,
                        })
                        _long = _df.melt(id_vars='Date', var_name='Parte', value_name='Valor')
                        _div_final = float(_div_part.iloc[-1])
                        _grw_final = float(_grw_part.iloc[-1])
                        _total = _div_final + _grw_final
                        _gain = _total - capital

                        st.markdown(f"**{_pd}% Dividendos · {_pg}% Crecimiento**  ·  Mezcla {_i} de 5")
                        mc1, mc2, mc3 = st.columns(3)
                        mc1.metric("Total combinado", f"${_total:,.0f}", delta=f"${_gain:,.0f}")
                        mc2.metric("En Dividendos", f"${_div_final:,.0f}", help=f"Inicial ${capital * _pd / 100.0:,.0f}")
                        mc3.metric("En Crecimiento", f"${_grw_final:,.0f}", help=f"Inicial ${capital * _pg / 100.0:,.0f}")
                        st.altair_chart(_mix_chart(_long), use_container_width=True)
                        if _i < len(_MIXES):
                            st.divider()

# --- Tickers excluidos del análisis (movido al pie, arriba del disclaimer) ---
_skipped_final = st.session_state.get('_skipped', {})
if _skipped_final:
    with st.expander(f"{len(_skipped_final)} ticker(s) excluidos del análisis"):
        for _t_sk, _s_sk in _skipped_final.items():
            _reason = _s_sk.get('reason', '')
            if _reason == 'not_known_etf':
                _reason_label = 'No reconocido como ETF de largo plazo (acción individual, ETF inverso o apalancado)'
            elif _reason == 'held_less_than_14_days':
                _reason_label = f'Posición cerrada en {_s_sk.get("holding_days", "?")} días (< 2 semanas)'
            else:
                _reason_label = 'Excluido'
            st.markdown(f'<p style="font-family:Inter,sans-serif;font-size:12px;color:#555555;margin:2px 0;">— <b>{_t_sk}</b> · <span style="color:#888888;">{_reason_label}</span></p>', unsafe_allow_html=True)

# --- Calculadoras de referencia (movidas al pie, arriba del disclaimer) ---
with st.expander("Calculadoras de referencia — en qué nos inspiramos y en qué nos diferenciamos"):
    st.markdown(
        "Esta herramienta se construyó estudiando las mejores calculadoras públicas de dividendos y tomando "
        "lo útil de cada una, pero con un principio propio: **realismo**, sobre todo en los ETF de alto "
        "rendimiento (YieldMax), donde el *yield* de portada engaña.\n\n"
        "- **[TipRanks](https://www.tipranks.com/tools/dividend-calculator)** y "
        "**[DividendCalculator.io](https://dividendcalculator.io/)** — proyección con DRIP, *yield on cost* y "
        "*forward yield*. → de aquí tomamos el **motor de proyección a futuro** y el *forward yield* vs realizado.\n"
        "- **[MiniWebtool](https://miniwebtool.com/dividend-reinvestment-calculator/)** y "
        "**[MarketBeat](https://www.marketbeat.com/dividends/calculator/)** — tabla año por año y efecto "
        "*bola de nieve* de la reinversión. → la **visualización del interés compuesto**.\n"
        "- **[DRIPCalc](https://www.dripcalc.com/yieldmax-etfs/)** — retorno con y sin DRIP para fondos YieldMax. "
        "→ la **comparación reinvertir vs cobrar en efectivo**.\n"
        "- **[NAV Erosion Calculator](https://dividend-wealth.com/tools/nav-erosion-calculator)** — la carrera "
        "*ingreso acumulado* vs *pérdida de capital* con punto de *breakeven*. → nuestro **modo realista YieldMax**.\n\n"
        "**Lo que ninguna hace y aquí sí:** descomponer cuánto de cada distribución es **Retorno de Capital** "
        "(datos oficiales 19a) y proyectar con la **erosión real observada** del fondo, en vez de asumir que el "
        "precio sube. Por eso un YieldMax nunca se proyecta como si fuera un ETF de crecimiento.")


# --- Footer Disclaimer — The Architectural Authority, anclaje #021C36 ---
FOOTER_STYLE = "background-color:#f0eeec;border-top:1px solid #e0ddd9;padding:24px 40px;margin-top:48px;"
BADGE_STYLE  = "display:inline-block;font-family:'Inter',sans-serif;font-size:9px;font-weight:500;letter-spacing:0.12em;text-transform:uppercase;color:#aaaaaa;border:1px solid #cccccc;padding:2px 6px;margin-bottom:10px;"
TITLE_STYLE  = "font-family:'Inter',sans-serif;font-size:12px;font-weight:600;letter-spacing:-0.01em;color:#555555;margin:0 0 8px 0;max-width:720px;line-height:1.5;"
BODY1_STYLE  = "font-family:'Inter',sans-serif;font-size:11px;color:#888888;line-height:1.7;margin:0 0 4px 0;max-width:720px;"
BODY2_STYLE  = "font-family:'Inter',sans-serif;font-size:11px;color:#aaaaaa;line-height:1.7;margin:0;max-width:720px;"

st.markdown(
    f'<div style="{FOOTER_STYLE}">'
    f'<span style="{BADGE_STYLE}">Versión Beta</span>'
    f'<p style="{TITLE_STYLE}">Esta herramienta es de carácter informativo y estimativo — no constituye asesoría financiera.</p>'
    f'<p style="{BODY1_STYLE}">Los datos, cálculos y proyecciones pueden presentar errores o inexactitudes. Siempre verifica con tus propios registros o los estados de cuenta de tu casa de bolsa.</p>'
    f'<p style="{BODY2_STYLE}">El uso de esta aplicación es bajo tu propio riesgo. Reporta cualquier fallo o inconsistencia para ayudarnos a seguir mejorando.</p>'
    '</div>',
    unsafe_allow_html=True
)
