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
)
if not all(hasattr(logic, _s) for _s in _LOGIC_SENTINELS):
    logic = importlib.reload(logic)


def _roc_detail_card(stats):
    """HTML del valor 'Costo base IB / ROC' de las tarjetas de detalle por activo.
    Soporta ROC estimado por avisos 19a (cuando no hay costo base del bróker)."""
    if stats.get("ib_cost_basis") is not None:
        return (f'<p class="da-tkpi-value">${stats["ib_cost_basis"]:,.2f}</p>'
                f'<p class="da-tkpi-sub" style="color:#16a34a;">ROC: ${stats["roc_accumulated"]:,.2f} '
                f'({stats["roc_percent"]:.1f}%)</p>')
    if stats.get("roc_accumulated") is not None:
        return (f'<p class="da-tkpi-value" style="color:#16a34a;">ROC ~${stats["roc_accumulated"]:,.0f}</p>'
                f'<p class="da-tkpi-sub" style="color:#8899aa;">est. 19a '
                f'({(stats.get("roc_percent") or 0):.0f}% de distrib.)</p>')
    return ('<p class="da-tkpi-value" style="color:#cbd5e1;">—</p>'
            '<p class="da-tkpi-sub">Edítala al cargar (Paso 1)</p>')


st.set_page_config(page_title="Calculadora de Dividendos", layout="wide")

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

    /* 22e. TABLA KPI INGRESOS — consolidada (ETF una sola vez, 4 grupos a lo ancho) */
    .da-kpiwide-row, .da-kpiwide-grouphead, .da-kpiwide-subhead {
        display: grid;
        grid-template-columns: minmax(48px, 1.1fr) repeat(12, 1fr);
        gap: 8px;
        align-items: baseline;
        padding: 3px 0;
    }
    .da-kpiwide-grouphead { padding: 2px 0 0 0; }
    .da-kpiwide-grouphead .grp {
        grid-column: span 3;
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

    /* 22f. TABLA ROC — desglose de Retorno de Capital por ETF (8 columnas) */
    .da-roc-row, .da-roc-subhead {
        display: grid;
        grid-template-columns: minmax(48px, 1.1fr) repeat(7, 1fr);
        gap: 8px;
        align-items: baseline;
        padding: 3px 0;
        min-width: 740px;
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


# --- Utilidad de formateo para métricas cuantitativas ---
def fmt_ratio(val, decimales=2, sufijo=""):
    if val is None: return "N/A"
    return f"{val:.{decimales}f}{sufijo}"


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


def _render_load_progress(csv_done, pos_done, income_done):
    """Barra de progreso interna de 3 segmentos (CSV / Posiciones / Ingresos)."""
    _pct = 100 if income_done else 66 if pos_done else 33 if csv_done else 0
    _segs = [("Transacciones", csv_done), ("Posiciones", pos_done), ("Ingresos · opc", income_done)]
    _cells = ""
    for _label, _done in _segs:
        _fill = ('<div class="da-seg-fill" style="height:100%;background:#006497;"></div>'
                 if _done else '')
        _lc = '#021C36' if _done else '#aab4be'
        _cells += (
            '<div style="flex:1;">'
            f'<div style="height:6px;background:#eae7e7;overflow:hidden;">{_fill}</div>'
            '<div style="font-family:Inter,sans-serif;font-size:9.5px;font-weight:700;'
            f'letter-spacing:0.06em;text-transform:uppercase;color:{_lc};margin-top:6px;">{_label}</div>'
            '</div>'
        )
    st.markdown(
        _LOAD_PROGRESS_STYLE +
        '<div style="display:flex;align-items:flex-end;justify-content:space-between;margin:2px 0 7px 0;">'
        '<span style="font-family:Inter,sans-serif;font-size:10px;font-weight:700;letter-spacing:0.1em;'
        'text-transform:uppercase;color:#8a96a3;">Progreso de carga</span>'
        f'<span style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;color:#006497;">{_pct}%</span>'
        '</div>'
        f'<div style="display:flex;gap:6px;">{_cells}</div>'
        '<div style="font-family:Inter,sans-serif;font-size:10.5px;color:#8a96a3;margin:9px 0 18px 0;">'
        'Mínimo requerido: <b style="color:#5a6b7a;">Posiciones (66%)</b> · Ingresos es validación extra opcional.'
        '</div>',
        unsafe_allow_html=True
    )


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
        _render_load_progress(_csv_done, _pos_done, _income_done)

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
            st.caption("Formatos aceptados: CSV · XLSX")
            with st.expander("¿No sabes cómo exportar tu archivo?"):
                st.markdown(
                    '<div style="font-family:Inter,sans-serif;font-size:12.5px;color:#445566;line-height:1.7;">'
                    '<p style="margin:0 0 8px 0;"><b style="color:#021C36;">Interactive Brokers</b> — '
                    'Informes → Extractos → <i>Transaction History</i> → elige el rango de fechas → exporta en CSV.</p>'
                    '<p style="margin:0 0 8px 0;"><b style="color:#021C36;">Charles Schwab</b> — '
                    'Historial → Transacciones → <i>Exportar</i> (CSV).</p>'
                    '<p style="margin:0;"><b style="color:#021C36;">Ingresos (opcional, solo Schwab)</b> — '
                    'Cuenta → Historial → <i>Investment Income</i> → Exportar; se sube luego en el Bloque 3.</p>'
                    '<p style="font-size:11px;color:#8899aa;margin:9px 0 0 0;">¿Otro broker? Sube un Excel (.xlsx) con columnas Fecha, Ticker, Cantidad y Monto y lo intentamos detectar.</p>'
                    '</div>',
                    unsafe_allow_html=True
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

            # Explicación "triangula con 3 fuentes" eliminada (sobraba al subir el primer archivo).
            if _pos_tickers and _gem_key:
                st.markdown(
                    '<p style="font-family:Inter,sans-serif;font-size:13px;color:#445566;line-height:1.7;margin:0 0 8px 0;">'
                    'Sube una o más <b>fotos de tu portafolio</b> (donde se vean “Acciones/Posición” y '
                    '“Base de coste / Cost Basis”) y rellenamos la tabla por ti. Útil sobre todo si tu broker solo '
                    'exporta los últimos años: confirmamos tus posiciones completas desde la foto. '
                    'Pueden estar repartidas en varias capturas; revisa y corrige antes de continuar.'
                    '</p>',
                    unsafe_allow_html=True
                )
                _imgs_s2 = st.file_uploader(
                    "Fotos del portafolio",
                    type=['png', 'jpg', 'jpeg'],
                    accept_multiple_files=True,
                    label_visibility="collapsed",
                    key="_step2_photos"
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
            elif _pos_tickers:
                st.markdown(
                    '<p style="font-family:Inter,sans-serif;font-size:13px;color:#445566;line-height:1.7;margin:0 0 8px 0;">'
                    'Confirma las <b>acciones</b> y el <b>costo de inversión</b> de cada posición tal como aparecen en tu broker. '
                    'Es clave si tu broker solo exporta los últimos años (las acciones viejas no están en el CSV). Deja en 0 lo que no aplique.'
                    '</p>',
                    unsafe_allow_html=True
                )

            if _pos_tickers:
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
            st.markdown(
                '<p style="font-family:Inter,sans-serif;font-size:13px;color:#445566;line-height:1.7;margin:0 0 8px 0;">'
                'Exporta tu reporte de <b>Investment Income</b> de Charles Schwab '
                '(Cuenta → Historial → <i>Investment Income</i> → Exportar) y súbelo aquí. Lo usamos como '
                '<b>tercera fuente</b> para confirmar que los dividendos del CSV cuadran con lo realmente '
                'recibido. Es opcional y no cambia tus métricas; solo agrega una verificación. '
                'Las proyecciones (“Estimated”) del broker se ignoran porque sobreestiman en ETFs tipo YieldMax.'
                '</p>',
                unsafe_allow_html=True
            )
            _inc_file = st.file_uploader(
                "Archivo de ingresos (Investment Income)",
                type=['csv'], key="_step2_income", label_visibility="collapsed"
            )
            if _inc_file is not None:
                try:
                    _parseo(["Leyendo ingresos…", "Conciliando dividendos recibidos…"])
                    _inc_df = logic.parse_schwab_income_csv(_inc_file.getvalue())
                    if _inc_df is None or len(_inc_df) == 0:
                        st.session_state['_wizard_income_summary'] = None
                        st.session_state['_wizard_income_df'] = None
                        st.warning(
                            "No reconocimos este archivo como un “Investment Income” de Charles Schwab. "
                            "Asegúrate de exportar el reporte de ingresos (no el de transacciones)."
                        )
                    else:
                        _inc_summ = logic.summarize_income(_inc_df)
                        st.session_state['_wizard_income_summary'] = _inc_summ
                        st.session_state['_wizard_income_df'] = _inc_df
                        if _inc_summ.get('multi_account'):
                            st.warning("El archivo incluye más de una cuenta; los totales podrían mezclarse. "
                                       "Exporta el income de una sola cuenta para una validación exacta.")
                        st.rerun()
                except Exception as _ie:
                    st.session_state['_wizard_income_summary'] = None
                    st.session_state['_wizard_income_df'] = None
                    st.warning(f"No pudimos leer el archivo de ingresos: {_ie}")
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
            else:
                st.caption("Puedes continuar ahora o añadir el archivo de ingresos para una validación extra.")
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
            _dq_approx = _dq_unrel + _dq_recon + _dq_part

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
            _n_approx = len(_dq_approx)
            if _dq_unrel:
                _conf_color = '#e0a23c'
            elif _n_approx:
                _conf_color = '#006497'
            else:
                _conf_color = '#4caf82'
            _conf_delta = 'todas verificadas' if _n_approx == 0 else f'{_n_approx} aproximada(s)'

            # ── "En corto · tu ingreso por dividendos" se movió al pie, bajo Análisis de riesgo ──

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
                _da_section('¿De dónde viene tu ingreso?',
                            'Cuánto aporta cada posición a tu ingreso anual por dividendos. Mientras más concentrado en pocos nombres, más depende tu ingreso de ellos.')
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
                    _diverg    = ((_sum_sproj / _sum_oproj - 1) * 100) if _sum_oproj > 0 else 0
                    _div_color = '#e0a23c' if _diverg > 5 else ('#4caf82' if abs(_diverg) <= 5 else '#006497')

                    def _tip_for(kind, tot_s, tot_c):
                        # Tooltip adaptativo: intro fija + interpretación del Δ% TOTAL real.
                        pct = ((tot_s / tot_c - 1) * 100) if tot_c else None
                        v = f'{pct:+.0f}%' if pct is not None else None
                        if kind == 'recv':
                            intro = ('<b>¿Qué es?</b> Los dividendos que ya cobraste en los últimos 12 meses, '
                                     'ETF por ETF. La columna <b>Schwab</b> es lo que tu broker reporta haberte '
                                     'pagado; la columna <b>Calc</b> es lo mismo, pero reconstruido por la '
                                     'calculadora desde tu archivo CSV. <b>Δ%</b> es la diferencia entre ambas.')
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
                                     'historia</b> (no solo los últimos 12 meses), ETF por ETF. La columna '
                                     '<b>Schwab</b> es lo que tu broker reporta haberte pagado en todo el income; '
                                     'la columna <b>Calc</b> es lo mismo, reconstruido por la calculadora desde tu '
                                     'archivo CSV.<br><br>'
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

                    def _kpi_wide(groups):
                        # groups: [(title, kind, accent_color, tip_r, rows), ...]
                        # rows alineadas por índice al mismo orden de tickers (_items)
                        totals = [_group_total(g[4]) for g in groups]

                        ghead = '<div class="da-kpiwide-grouphead"><span></span>'
                        for i, (_title, _kind, _color, _tipr, _rows) in enumerate(groups):
                            ts, tcv = totals[i]
                            tip = _tip_for(_kind, ts, tcv)
                            box_cls = 'da-tip-box r' if _tipr else 'da-tip-box'
                            ghead += (f'<span class="grp da-tip" style="border-bottom-color:{_color};">'
                                      f'{_title}<span class="da-tip-i">i</span>'
                                      f'<span class="{box_cls}">{tip}</span></span>')
                        ghead += '</div>'

                        sub = '<div class="da-kpiwide-subhead"><span class="lbl">ETF</span>'
                        for _ in groups:
                            sub += '<span>Schwab</span><span>Calc</span><span>Δ%</span>'
                        sub += '</div>'

                        body = ''
                        for r in range(len(groups[0][4])):
                            cells = f'<span class="tk">{groups[0][4][r][0]}</span>'
                            for _g in groups:
                                _tk, _s, _c = _g[4][r]
                                cells += (f'<span class="num">{_fmt_money(_s)}</span>'
                                          f'<span class="num">{_fmt_money(_c)}</span>'
                                          f'{_pct_html(_s, _c)}')
                            body += f'<div class="da-kpiwide-row">{cells}</div>'

                        trow = '<span class="tk">TOTAL</span>'
                        for i in range(len(groups)):
                            ts, tcv = totals[i]
                            trow += (f'<span class="num">{_fmt_money(ts)}</span>'
                                     f'<span class="num">{_fmt_money(tcv)}</span>'
                                     f'{_pct_html(ts, tcv)}')
                        total = f'<div class="da-kpiwide-row da-kpiwide-total">{trow}</div>'

                        return f'<div class="da-kpi-cell">{ghead}{sub}{body}{total}</div>'

                    _items = sorted(_proj.items(),
                                    key=lambda kv: (kv[1].get('schwab_received_12m') or 0), reverse=True)
                    _rows_recv = [(_tk, _d.get('schwab_received_12m'), _d.get('our_received_12m'))
                                  for _tk, _d in _items]
                    _rows_ann  = [(_tk, _d.get('schwab_proj'), _d.get('our_proj')) for _tk, _d in _items]
                    _rows_mon  = [(_tk,
                                   (_d.get('schwab_proj') or 0) / 12,
                                   (_d.get('our_proj') / 12 if _d.get('our_proj') is not None else None))
                                  for _tk, _d in _items]
                    _rows_hist = [(_tk, _d.get('schwab_received_total'), _d.get('our_received_total'))
                                  for _tk, _d in _items]

                    _da_section('Ingreso, ROC y comparación con el broker',
                                'El número fino: lo recibido vs lo proyectado, tu Retorno de Capital por activo y por qué la proyección del broker suele estar inflada.')
                    _inc_exp = st.expander('Ver detalle · tabla Schwab vs tu cálculo · ROC · gráfica de ingresos', expanded=False)
                    _inc_exp.markdown(
                        _kpi_wide([
                            ('Total dividendos',   'hist', '#021C36',   False, _rows_hist),
                            ('Últimos 12 meses',   'recv', '#006497',   False, _rows_recv),
                            ('Proyectado anual',   'ann',  _div_color,  True,  _rows_ann),
                            ('Proyectado mensual', 'mon',  '#4caf82',   True,  _rows_mon),
                        ]),
                        unsafe_allow_html=True
                    )

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
                    _inc_exp.caption('La acumulación reparte el total anual de forma pareja entre los 12 meses; '
                                     'es una simplificación para comparar los dos métodos, no un calendario exacto de pagos.')
                    if _dropped:
                        _drop_txt = ', '.join(t for t, _ in _dropped)
                        _inc_exp.caption(f'Ocultados (dividendo marginal, fuera del portafolio de ingresos): {_drop_txt}.')

                    # Justificación auto-generada: por qué la proyección de Schwab está inflada.
                    _flagged = sorted(
                        [(t, d) for t, d in _proj.items() if (d.get('overstatement_pct') or 0) > logic.INCOME_OVERSTATE_FLAG_PCT],
                        key=lambda x: -(x[1]['overstatement_pct'] or 0))
                    _stable = [t for t, d in _proj.items() if abs(d.get('overstatement_pct') or 0) <= 5]
                    if _flagged:
                        _just_li = ''.join(
                            f'<li style="margin:7px 0;line-height:1.6;"><b>{t}</b>: Schwab proyecta '
                            f'<b>${d["schwab_proj"]:,.0f}</b>/año asumiendo <b>${d["anchor_per_payment"]:,.2f}</b> por pago, '
                            f'pero tu pago real reciente promedia <b>${d["recent_per_payment"]:,.2f}</b> — un ancla '
                            f'<b style="color:#c9821f;">{d["overstatement_pct"]:.0f}% por encima</b> del nivel actual. '
                            f'Proyectando tu run-rate real: <b style="color:#006497;">${d["our_proj"]:,.0f}</b>/año. '
                            f'(Recibido últimos 12m: ${d["schwab_received_12m"]:,.0f}.)</li>'
                            for t, d in _flagged
                        )
                        _stable_html = ''
                        if _stable:
                            _stable_html = (
                                '<p style="font-family:Inter,sans-serif;font-size:12px;color:#5a6b7a;margin:8px 0 0 0;line-height:1.6;">'
                                f'En cambio, en ETFs de dividendo estable ({", ".join(_stable)}) la proyección de Schwab y la '
                                'nuestra coinciden (±5%). El sesgo es específico de los ETFs de opción-ingreso tipo YieldMax: '
                                'su distribución por acción cae con el tiempo, pero Schwab proyecta plano desde un pago-ancla '
                                'más alto, ignorando la caída.</p>'
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
                        c = '#4caf82' if roc_acc > 0 else ('#e05c5c' if roc_acc < 0 else '#8899aa')
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

                    _ROC_TIP = (
                        '<b>ROC (Retorno de Capital)</b> es la parte de tus distribuciones que es '
                        '<b>devolución de tu propio capital</b>, no rendimiento. Se calcula como '
                        '<b>(Invertido + Reinvertido) − Costo bróker</b>: lo que metiste a comprar acciones '
                        '(incluido lo reinvertido, que sube tu base) menos lo que el bróker dice que vale tu '
                        'base ahora; ese hueco es ROC ya contabilizado.<br>'
                        'Si <b>no tienes el costo base del bróker</b>, se estima con el <b>% que el fondo '
                        'publica en sus avisos 19a-1</b> (marcado <b>est.19a</b>). El dato fiscal definitivo '
                        'está en tu <b>1099-DIV casilla 3</b>.<br>'
                        'Señal de "ingreso no gratis": si <b>Valor actual</b> cayó muy por debajo de '
                        '<b>Invertido</b> pese a cobrar distribuciones (típico de YieldMax), gran parte de tu '
                        '"ingreso" fue erosión de tu capital.'
                    )

                    def _roc_th(label, tip, right=False, lbl=False):
                        # Header de columna con tooltip (mismo patrón .da-tip de la tabla comparativa).
                        _bc = 'da-tip-box r' if right else 'da-tip-box'
                        _cls = 'lbl da-tip' if lbl else 'da-tip'
                        return (f'<span class="{_cls}">{label}'
                                f'<span class="da-tip-i">i</span>'
                                f'<span class="{_bc}">{tip}</span></span>')

                    _roc_sub = (
                        '<div class="da-roc-subhead">'
                        + _roc_th('ETF', 'El fondo o acción. Cada fila desglosa de dónde viene su ROC.', lbl=True)
                        + _roc_th('Div. pagados', 'Lo que de verdad entró a tu cuenta: lo reinvertido más lo recibido en efectivo, ya <b>neto</b> de la retención de impuesto a extranjeros (NRA). Por eso es menor que el "Total dividendos" de arriba, que es el bruto antes de impuesto.')
                        + _roc_th('Reinvertidos', 'La parte de tus distribuciones que se reinvirtió comprando más acciones (DRIP). <b>Sube</b> tu costo base.')
                        + _roc_th('En efectivo', 'La parte de tus distribuciones que cobraste en efectivo, sin reinvertir.')
                        + _roc_th('Invertido', 'El dinero de <b>tu propio bolsillo</b> que metiste a comprar acciones, sin contar lo reinvertido.', right=True)
                        + _roc_th('Valor actual', 'Cuánto vale hoy tu posición. En <b>rojo</b> si vale menos que lo invertido: señal de erosión del NAV.', right=True)
                        + _roc_th('Costo bróker', 'La base de costo que tu bróker reporta hoy; el ROC ya la <b>redujo</b> dólar a dólar.', right=True)
                        + _roc_th('ROC', _ROC_TIP, right=True)
                        + '</div>'
                    )
                    _roc_body = ''
                    _r_paid = _r_drip = _r_cash = _r_pkt = _r_mv = 0.0
                    _r_basis = _r_roc = _r_dist_for_roc = 0.0
                    _r_basis_has = _r_roc_has = _r_any_19a = False
                    for _tk, _ in _items:
                        _rs = results.get(_tk, {})
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
                                      f'<span class="num">{_fmt_money(_paid)}</span>'
                                      f'<span class="num">{_fmt_money(_drip)}</span>'
                                      f'<span class="num">{_fmt_money(_cash)}</span>'
                                      f'<span class="num">{_fmt_money(_pkt)}</span>'
                                      f'{_val_html(_mv, _pkt)}'
                                      f'<span class="num">{_fmt_money(_basis)}</span>'
                                      f'{_roc_html(_roc_a, _roc_p, _roc_src, _roc_approx)}</div>')
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
                                  f'<span class="num">{_fmt_money(_r_paid)}</span>'
                                  f'<span class="num">{_fmt_money(_r_drip)}</span>'
                                  f'<span class="num">{_fmt_money(_r_cash)}</span>'
                                  f'<span class="num">{_fmt_money(_r_pkt)}</span>'
                                  f'{_val_html(_r_mv, _r_pkt)}'
                                  f'<span class="num">{_fmt_money(_r_basis_disp)}</span>'
                                  f'{_roc_html(_r_roc_disp, _r_roc_pct, "19a" if _r_any_19a else None)}</div>')
                    _inc_exp.markdown(
                        '<div style="margin:14px 0 2px 0;"><p style="font-family:Inter,sans-serif;font-size:13px;'
                        'font-weight:800;color:#021C36;margin:0 0 2px 0;">Retorno de Capital (ROC) por activo</p>'
                        '<p style="font-family:Inter,sans-serif;font-size:12px;color:#8899aa;margin:0 0 8px 0;line-height:1.6;">'
                        'Pasa el cursor por el ícono <span style="font-size:9px;font-weight:700;color:#fff;'
                        'background:#94a3b8;padding:0 4px;">i</span> de cada columna (sobre todo <b>ROC</b>) para ver qué '
                        'significa y cómo se calcula.</p></div>',
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
                        _inc_exp.caption(f'ROC marcado "est.19a": % que el fondo publica en sus avisos 19a, '
                                   f'actualizado al {_roc_19a_asof}.{_warn}')

            # ── Cuadrículas Schwab vs tu cálculo: inversión · dividendos · ROC ──
                _cmp_valid = sorted([t for t, s in results.items()
                                     if isinstance(s, dict) and 'error' not in s],
                                    key=lambda t: -(results[t].get('market_value') or 0))
                if _cmp_valid:
                    def _cell(v, kind='money'):
                        if v is None:
                            return '<span class="num" style="color:#b8c2cc;">n/d</span>'
                        if kind == 'pct':
                            return f'<span class="num" style="color:{"#4caf82" if v >= 0 else "#e05c5c"};">{v:+.0f}%</span>'
                        return f'<span class="num">${v:,.0f}</span>'

                    def _delta(s, c, kind='money'):
                        if s is None or c is None:
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

                    def _triplet(groups, tks):
                        g = _grid_css(3 * len(groups))
                        h = f'<div class="da-kpiwide-grouphead" style="{g}"><span></span>'
                        for lab, acc, _gt, _kd in groups:
                            h += f'<span class="grp" style="border-bottom-color:{acc};">{lab}</span>'
                        h += f'</div><div class="da-kpiwide-subhead" style="{g}"><span class="lbl">ETF</span>'
                        for _ in groups:
                            h += '<span>Schwab</span><span>Calc</span><span>Δ</span>'
                        h += '</div>'
                        tot = [[0.0, 0.0, False, False] for _ in groups]
                        for t in tks:
                            h += f'<div class="da-kpiwide-row" style="{g}"><span class="tk">{t}</span>'
                            for i, (lab, acc, getter, kind) in enumerate(groups):
                                s, c = getter(t)
                                h += _cell(s, kind) + _cell(c, kind) + _delta(s, c, kind)
                                if kind == 'money':
                                    if s is not None:
                                        tot[i][0] += s; tot[i][2] = True
                                    if c is not None:
                                        tot[i][1] += c; tot[i][3] = True
                            h += '</div>'
                        h += f'<div class="da-kpiwide-row da-kpiwide-total" style="{g}"><span class="tk">TOTAL</span>'
                        for i, (lab, acc, getter, kind) in enumerate(groups):
                            if kind == 'money':
                                ss = tot[i][0] if tot[i][2] else None
                                cc = tot[i][1] if tot[i][3] else None
                                h += _cell(ss, kind) + _cell(cc, kind) + _delta(ss, cc, kind)
                            else:
                                h += '<span class="num" style="color:#b8c2cc;">—</span>' * 2 + '<span class="pct" style="color:#b8c2cc;">—</span>'
                        return h + '</div>'

                    def _subtitle(txt):
                        return (f'<p style="font-family:Inter,sans-serif;font-size:11px;font-weight:800;'
                                f'color:#021C36;letter-spacing:0.04em;text-transform:uppercase;'
                                f'margin:18px 0 6px 0;">{txt}</p>')

                    _da_section("Comparación con el broker · Schwab vs tu cálculo",
                                "Lo que reporta Schwab frente a lo que reconstruye la calculadora desde tu CSV: tu inversión, tus dividendos y tu Retorno de Capital, fondo por fondo.")
                    _cmp_exp = st.expander("Ver las 3 cuadrículas · inversión, dividendos y ROC", expanded=False)

                    # Cuadrícula A — rendimiento de la inversión
                    def _A_inv(t):
                        return (results[t].get('ib_cost_basis'), results[t].get('pocket_investment'))

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

                    _gridA = _triplet([('Invertido', '#021C36', _A_inv, 'money'),
                                       ('Valor hoy', '#006497', _A_val, 'money'),
                                       ('Rendim. $', '#4caf82', _A_gain, 'money'),
                                       ('Rendim. %', '#2d3748', _A_ret, 'pct')], _cmp_valid)
                    _cmp_exp.markdown(_subtitle('Rendimiento de tu inversión') + f'<div class="da-kpi-cell">{_gridA}</div>',
                                      unsafe_allow_html=True)
                    _cmp_exp.caption("«Invertido» en Schwab es el cost basis del bróker (ya reducido por el ROC); en la calculadora "
                                     "es el capital real que desplegaste. Por eso Schwab suele mostrar una ganancia mayor: compara "
                                     "contra una base más baja. El valor de mercado es el mismo en ambas (precio × acciones).")

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

                        def _B_net(t):
                            p = _proj_all.get(t, {}) or {}
                            gs = p.get('schwab_received_total'); gc = p.get('our_received_total')
                            x = results[t].get('withheld_tax_total') or 0
                            return ((gs - x) if gs is not None else None,
                                    (gc - x) if gc is not None else None)

                        def _B_drip(t):
                            d = results[t].get('dividends_collected_drip')
                            return (d, d)

                        def _B_cash(t):
                            c = results[t].get('dividends_collected_cash')
                            return (c, c)

                        _gridB = _triplet([('Total div. (bruto)', '#021C36', _B_gross, 'money'),
                                           ('Impuesto NRA', '#e05c5c', _B_tax, 'money'),
                                           ('Neto recibido', '#4caf82', _B_net, 'money'),
                                           ('Reinvertidos', '#006497', _B_drip, 'money'),
                                           ('En efectivo', '#2d3748', _B_cash, 'money')], _divtks)
                        _cmp_exp.markdown(_subtitle('Dividendos: bruto, impuesto y neto') + f'<div class="da-kpi-cell">{_gridB}</div>',
                                          unsafe_allow_html=True)
                        _cmp_exp.caption("El bruto es lo que el fondo declaró; el impuesto NRA (retención a extranjeros, ~30%) se "
                                         "descuenta y deja el neto que de verdad entró a tu cuenta. «Reinvertidos» y «En efectivo» "
                                         "salen de tu CSV, así que Schwab y la calculadora coinciden.")

                    # Cuadrícula C — Retorno de Capital (ROC)
                    _roctks = [t for t in _cmp_valid
                               if results[t].get('roc_accumulated') is not None
                               or (results[t].get('total_dividends') or 0) > 0]
                    if _roctks:
                        gC = _grid_css(5)
                        hC = (f'<div class="da-kpiwide-subhead" style="{gC}"><span class="lbl">ETF</span>'
                              '<span>Costo bróker</span><span>Costo real</span><span>ROC $</span>'
                              '<span>ROC %</span><span>ROC ÷ div.</span></div>')
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

            # ── Portafolio de crecimiento — rendimiento de precio ──────
            # Robustez en Streamlit Cloud: tras un deploy, el watcher puede reejecutar app.py
            # pero conservar en memoria un `logic` viejo (sin la función nueva). Preferimos la
            # función del módulo (canónica, testeada) y, si no existe (módulo stale), caemos a
            # una clasificación equivalente local usando solo API antigua de logic — app.py
            # siempre se reejecuta fresco, así que esto nunca falla por el cacheo del módulo.
            _filter_growth = getattr(logic, 'filter_growth_assets', None)
            if _filter_growth is not None:
                _growth = _filter_growth(results)
            else:
                _instr_g = logic.load_instruments()
                _min_yg = getattr(logic, 'INCOME_ASSET_MIN_YIELD_PCT', 4.0)
                _growth = {}
                for _gt, _gs in (results or {}).items():
                    if not isinstance(_gs, dict) or _gs.get('skipped') or 'error' in _gs:
                        continue
                    _gtyp = (_instr_g.get(str(_gt).upper(), {}).get('type') or '').lower()
                    if _gtyp == 'yieldmax':
                        _is_g = False
                    elif _gtyp == 'leveraged':
                        _is_g = True
                    else:
                        _gy = _gs.get('yield_on_cost')
                        _is_g = (float(_gy or 0) < _min_yg) if _gy is not None else False
                    if _is_g:
                        _growth[_gt] = {_k: _gs.get(_k) for _k in (
                            'market_value', 'pocket_investment', 'dividends_collected_cash',
                            'roi_percent', 'benchmark_value', 'benchmark_roi')}
            if _growth:
                def _gfmt_money(v):
                    return f'${v:,.0f}' if v is not None else 'n/d'

                def _gmoney_ret(v):
                    if v is None:
                        return '<span style="color:#b8c2cc;">n/d</span>'
                    c = '#4caf82' if v >= 0 else '#e05c5c'
                    return f'<span style="color:{c};">{"+" if v >= 0 else "−"}${abs(v):,.0f}</span>'

                def _gret_html(pct, suffix='%'):
                    if pct is None:
                        return '<span style="color:#b8c2cc;">n/d</span>'
                    c = '#4caf82' if pct >= 0 else '#e05c5c'
                    return f'<span style="color:{c};">{pct:+.0f}{suffix}</span>'

                _g_items = sorted(_growth.items(),
                                  key=lambda kv: (kv[1].get('market_value') or 0), reverse=True)
                _g_head = ('<div class="da-growth-row da-growth-head"><span>ETF</span>'
                           '<span>Invertido</span><span>Valor</span><span>Rendim. $</span>'
                           '<span>Rendim. %</span></div>')
                _g_body = ''
                _g_mv = _g_pocket = _g_div = 0.0
                for _tk, _d in _g_items:
                    _mv  = _d.get('market_value');             _pk = _d.get('pocket_investment')
                    _dv  = _d.get('dividends_collected_cash'); _roi = _d.get('roi_percent')
                    _gain = ((_mv or 0) + (_dv or 0) - _pk) if _pk is not None else None
                    _g_body += (f'<div class="da-growth-row"><span>{_tk}</span>'
                                f'<span>{_gfmt_money(_pk)}</span>'
                                f'<span>{_gfmt_money(_mv)}</span>'
                                f'<span>{_gmoney_ret(_gain)}</span>'
                                f'<span>{_gret_html(_roi)}</span></div>')
                    _g_mv += (_mv or 0); _g_pocket += (_pk or 0); _g_div += (_dv or 0)
                _g_tgain = (_g_mv + _g_div - _g_pocket) if _g_pocket > 0 else None
                _g_troi = ((_g_mv + _g_div - _g_pocket) / _g_pocket * 100) if _g_pocket > 0 else None
                _g_total = ('<div class="da-growth-row da-growth-total"><span>TOTAL</span>'
                            f'<span>{_gfmt_money(_g_pocket)}</span>'
                            f'<span>{_gfmt_money(_g_mv)}</span>'
                            f'<span>{_gmoney_ret(_g_tgain)}</span>'
                            f'<span>{_gret_html(_g_troi)}</span></div>')
                _g_tip = ('<b>¿Qué es?</b> El rendimiento de precio de tus activos de '
                          '<b>crecimiento</b> (posiciones de baja distribución: índices, ETFs y '
                          'acciones de apreciación), activo por activo.<br><br>'
                          '<b>Invertido</b>: lo que pusiste de tu bolsillo (costo base) en cada '
                          'posición.<br>'
                          '<b>Valor</b>: lo que vale hoy a precio de mercado.<br>'
                          '<b>Rendim. $</b>: tu ganancia en dólares = valor + dividendos en '
                          'efectivo − invertido.<br>'
                          '<b>Rendim. %</b>: lo mismo en porcentaje (Rendim. $ ÷ invertido). Es tu '
                          'rendimiento <b>total acumulado</b> desde tu primera compra; en '
                          'crecimiento los dividendos son marginales, así que ≈ apreciación del '
                          'precio. Verde = ganas, rojo = pierdes.<br><br>'
                          '<b>Ojo</b>: el rendimiento es <b>acumulado, no anual</b>, así que una '
                          'posición con más tiempo de tenencia tiene ventaja natural; para comparar '
                          'por año, mira el CAGR en el detalle de cada activo más abajo.')
                _g_card = (f'<div class="da-kpi-cell da-kpi-navy da-tip">'
                           f'<p class="da-kpi-label">Crecimiento · rendimiento de precio'
                           f'<span class="da-tip-i">i</span></p>'
                           f'<div class="da-growth-wrap">{_g_head}{_g_body}{_g_total}</div>'
                           f'<span class="da-tip-box">{_g_tip}</span></div>')
                _da_section("Portafolio crecimiento",
                            "Tus posiciones de apreciación (no-income): cuánto pusiste, cuánto valen y cuánto han rendido.")
                st.markdown(
                    f'<div style="margin:6px 0 4px 0;">{_g_card}</div>',
                    unsafe_allow_html=True
                )

                # ── Gráfico comparativo por posición vs S&P 500 (toggle USD / %) ──
                import pandas as pd
                import altair as alt
                _spc_rows = []
                _spy_usd = {}
                _spy_inv = {}
                for _gt in _growth:
                    _dt = results.get(_gt, {}).get('daily_trend')
                    if _dt is None or len(_dt) == 0:
                        continue
                    _dd = _dt.reset_index()
                    _dcol = _dd.columns[0]
                    for _, _r in _dd.iterrows():
                        _date = pd.Timestamp(_r[_dcol])
                        _ret = _r.get('User Return %')
                        _spc_rows.append({'Fecha': _date, 'Serie': _gt,
                                          'USD': float(_r.get('User Profit') or 0),
                                          'Pct': (None if _ret is None else float(_ret))})
                        _spy_usd[_date] = _spy_usd.get(_date, 0.0) + float(_r.get('SPY Profit') or 0)
                        _spy_inv[_date] = _spy_inv.get(_date, 0.0) + float(_r.get('Invested Capital') or 0)
                if _spc_rows and _spy_usd:
                    for _date in sorted(_spy_usd):
                        _inv = _spy_inv.get(_date, 0)
                        _spc_rows.append({'Fecha': _date, 'Serie': 'S&P 500',
                                          'USD': _spy_usd[_date],
                                          'Pct': (_spy_usd[_date] / _inv * 100) if _inv else None})
                    _spc_df = pd.DataFrame(_spc_rows)
                    _spc_df['Fecha'] = pd.to_datetime(_spc_df['Fecha'])
                    st.markdown(
                        '<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;color:#021C36;'
                        'margin:18px 0 6px 0;">Cada posición frente al S&amp;P 500</p>', unsafe_allow_html=True)
                    _spc_key = f"_spc_metric_{st.session_state.get('_file_id', 'x')}"
                    if hasattr(st, 'segmented_control'):
                        _spc_metric = st.segmented_control(
                            "Métrica", options=["% de rendimiento", "Ganancia ($)"],
                            default="% de rendimiento", key=_spc_key,
                            label_visibility="collapsed") or "% de rendimiento"
                    else:
                        _spc_metric = st.radio("Métrica", ["% de rendimiento", "Ganancia ($)"],
                                               horizontal=True, key=_spc_key, label_visibility="collapsed")
                    if _spc_metric == "Ganancia ($)":
                        _spc_y = alt.Y('USD:Q', axis=_ed_axis('y', fmt='$,.0f', title='Ganancia ($)'))
                        _spc_plot = _spc_df.dropna(subset=['USD'])
                    else:
                        _spc_y = alt.Y('Pct:Q', axis=_ed_axis('y', fmt='+.0f', title='% Retorno'))
                        _spc_plot = _spc_df.dropna(subset=['Pct'])
                    _spc_tickers = sorted(_growth.keys())
                    _spc_domain = _spc_tickers + ['S&P 500']
                    _spc_range = (['#006497', '#021C36', '#4caf82', '#c9821f', '#60A5FA', '#166534'][:len(_spc_tickers)]
                                  + ['#9aa5b1'])
                    _spc_chart = alt.Chart(_spc_plot).mark_line(strokeWidth=2.4).encode(
                        x=alt.X('Fecha:T', title=None, axis=_ed_axis('x', fmt='%b %Y', label_angle=0, year_ticks=True)),
                        y=_spc_y,
                        color=alt.Color('Serie:N', scale=alt.Scale(domain=_spc_domain, range=_spc_range),
                                        legend=alt.Legend(title=None, orient='bottom', labelFontSize=11)),
                        strokeDash=alt.condition("datum.Serie == 'S&P 500'", alt.value([5, 4]), alt.value([1, 0])),
                        tooltip=[alt.Tooltip('Fecha:T', format='%d %b %Y', title='Fecha'),
                                 alt.Tooltip('Serie:N', title='Activo'),
                                 alt.Tooltip('USD:Q', format='$,.0f', title='Ganancia'),
                                 alt.Tooltip('Pct:Q', format='+.1f', title='% Retorno')],
                    ).properties(height=380, background=CHART_PALETTE['bg']).configure_view(
                        strokeOpacity=0, fill=CHART_PALETTE['bg'])
                    st.altair_chart(_spc_chart, use_container_width=True)
                    st.caption("Cada posición de crecimiento frente al S&P 500 (línea punteada gris), con tu mismo capital "
                               "y timing. Alterna entre % de rendimiento y ganancia en dólares.")

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
                # ── Consolidado: Dividendos vs Crecimiento ──────────────
                import pandas as pd

                _comb_inv  = _cmp_a_inv + _cmp_b_inv
                _comb_val  = _cmp_a_mv  + _cmp_b_mv
                _comb_div  = _cmp_a_div + _cmp_b_div
                _comb_gain = _cmp_a_tr  + _cmp_b_tr
                _comb_pct  = _comb_gain / _comb_inv * 100 if _comb_inv > 0 else 0
                _comb_color = "#4caf82" if _comb_pct >= 0 else "#e05c5c"

                _a_share = _cmp_a_inv / _comb_inv * 100 if _comb_inv > 0 else 0
                _b_share = _cmp_b_inv / _comb_inv * 100 if _comb_inv > 0 else 0

                _a_tickers_detail = [
                    (t, s['pocket_investment'] / _cmp_a_inv * 100)
                    for t, s in sorted(_cmp_a_rows, key=lambda x: x[1]['pocket_investment'], reverse=True)
                ] if _cmp_a_inv > 0 else []
                _b_tickers_detail = [
                    (t, s['pocket_investment'] / _cmp_b_inv * 100)
                    for t, s in sorted(_cmp_b_rows, key=lambda x: x[1]['pocket_investment'], reverse=True)
                ] if _cmp_b_inv > 0 else []

                # Alturas idénticas: la zona de tickers reserva el alto del bloque con MÁS tickers,
                # así ambas tarjetas terminan en la misma línea base aunque tengan distinto nº de tickers.
                _tk_minh = max(len(_a_tickers_detail), len(_b_tickers_detail), 1) * 23

                def _ticker_rows(tickers_detail):
                    return ''.join(
                        f'<div style="display:flex;justify-content:space-between;padding:3px 0;'
                        f'border-bottom:1px solid rgba(0,0,0,0.06);">'
                        f'<span style="font-family:Inter,sans-serif;font-size:11px;font-weight:700;color:#021C36;">{t}</span>'
                        f'<span style="font-family:Inter,sans-serif;font-size:11px;color:#8899aa;">{pct:.1f}%</span>'
                        f'</div>'
                        for t, pct in tickers_detail
                    )

                _da_section("Distribución de tu capital",
                            "Cómo se reparte tu capital entre Dividendos y Crecimiento. El rendimiento comparado de ambos va en la gráfica de la sección siguiente.")

                # ── Pie chart de asignación del capital (dividendos vs crecimiento, por ETF) ──
                import altair as alt
                import pandas as pd
                _pie_rows = ([{'ETF': t, 'Grupo': 'Dividendos', 'Capital': (s.get('pocket_investment') or 0)}
                              for t, s in _cmp_a_rows]
                             + [{'ETF': t, 'Grupo': 'Crecimiento', 'Capital': (s.get('pocket_investment') or 0)}
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
                                 alt.Tooltip('Capital:Q', format='$,.0f', title='Invertido'),
                                 alt.Tooltip('Pct:Q', format='.1f', title='% del capital')])
                    _pie_arc = _pie_base.mark_arc(innerRadius=68, stroke='#fcf9f8', strokeWidth=2)
                    _pie_txt = _pie_base.mark_text(radius=112, fontSize=11,
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
                        f'Dividendos <b>{_a_share:.0f}%</b> · ${_cmp_a_inv:,.0f}</span>'
                        '<span style="font-family:Inter,sans-serif;font-size:12px;color:#021C36;">'
                        '<span style="display:inline-block;width:9px;height:9px;background:#2d3748;margin-right:6px;vertical-align:middle;"></span>'
                        f'Crecimiento <b>{_b_share:.0f}%</b> · ${_cmp_b_inv:,.0f}</span>'
                        '</div>',
                        unsafe_allow_html=True)

                st.markdown('<hr class="da-section-rule">', unsafe_allow_html=True)

            mode_a_tickers = [t for t, m in classify_map.items() if m == 'mode_a']
            mode_b_tickers = [t for t, m in classify_map.items() if m == 'mode_b']

            # ── Rendimiento en el tiempo: Dividendos vs Crecimiento ───
            if mode_a_tickers and mode_b_tickers:
                import altair as alt
                import pandas as pd
                _cmp_key = f"_cmp_series_{st.session_state.get('_file_id', 'x')}"
                if _cmp_key not in st.session_state:
                    st.session_state[_cmp_key] = logic.build_portfolio_comparison_series(results, classify_map)
                _cmp_series = st.session_state[_cmp_key]
                if _cmp_series is not None and not _cmp_series.empty:
                    _da_section("Rendimiento en el tiempo",
                                "Evolución de tu portafolio de Dividendos frente al de Crecimiento, lado a lado")
                    _cmp_metric_key = f"_cmp_metric_{st.session_state.get('_file_id', 'x')}"
                    if hasattr(st, 'segmented_control'):
                        _cmp_metric = st.segmented_control(
                            "Métrica", options=["% de rendimiento", "Valor ($)"],
                            default="% de rendimiento", key=_cmp_metric_key,
                            label_visibility="collapsed",
                        ) or "% de rendimiento"
                    else:
                        _cmp_metric = st.radio(
                            "Métrica", ["% de rendimiento", "Valor ($)"],
                            horizontal=True, key=_cmp_metric_key,
                            label_visibility="collapsed",
                        )

                    _cmp_df = _cmp_series.copy()
                    _cmp_df['Fecha'] = pd.to_datetime(_cmp_df['Fecha'])

                    if _cmp_metric == "Valor ($)":
                        _cmp_y = alt.Y('Valor:Q', axis=_ed_axis('y', fmt='$,.0f', title='Valor ($)'))
                        _cmp_plot = _cmp_df
                    else:
                        _cmp_y = alt.Y('Rendimiento:Q', axis=_ed_axis('y', fmt='+.0f', title='% Retorno'))
                        _cmp_plot = _cmp_df.dropna(subset=['Rendimiento'])

                    _cmp_chart = alt.Chart(_cmp_plot).mark_line(strokeWidth=2.5).encode(
                        x=alt.X('Fecha:T', title=None, axis=_ed_axis('x', fmt='%b %Y', label_angle=0, year_ticks=True)),
                        y=_cmp_y,
                        color=alt.Color('Portafolio:N',
                            scale=alt.Scale(domain=['Dividendos', 'Crecimiento'],
                                            range=['#006497', '#2d3748']),
                            legend=alt.Legend(orient='bottom', columns=2, labelFontSize=12,
                                              titleFontSize=0, symbolSize=120)
                        ),
                        tooltip=[
                            alt.Tooltip('Fecha:T', title='Fecha', format='%d %b %Y'),
                            alt.Tooltip('Portafolio:N', title='Portafolio'),
                            alt.Tooltip('Rendimiento:Q', title='Rendimiento', format='+.2f'),
                            alt.Tooltip('Valor:Q', title='Valor', format='$,.0f'),
                        ]
                    ).properties(height=420, background=CHART_PALETTE['bg']).configure_view(
                        strokeOpacity=0, fill=CHART_PALETTE['bg']
                    )
                    st.altair_chart(_cmp_chart, use_container_width=True)
                    _excl_cmp = [t for t, m in classify_map.items()
                                 if m in ('mode_a', 'mode_b') and t in results
                                 and logic._cost_incomplete(results, t)]
                    if _excl_cmp:
                        st.caption(
                            "Nota: " + ", ".join(sorted(_excl_cmp)) +
                            " se excluyó de esta gráfica por historial incompleto en el CSV "
                            "(ventas que superan las compras registradas), lo que distorsionaría el % del bloque. "
                            "El % es el retorno sobre el capital que aportaste: baja cuando agregas capital nuevo "
                            "(aún sin ganancia), por eso puede caer mientras el valor en $ sube."
                        )
                    st.markdown('<hr class="da-section-rule">', unsafe_allow_html=True)

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


            # Eventos técnicos consolidados → acordeón al pie (se llenan en los loops de detalle)
            _tech_events = []

            # ── ACORDEÓN: Detalle por portafolio ───────────────────────
            _da_section("Detalle por portafolio",
                        "Abre cada portafolio para ver sus posiciones y métricas de riesgo")
            tab_a = st.expander(
                f"PORTAFOLIO DE DIVIDENDOS   ·   income mensual   ·   {len(mode_a_tickers)} fondos",
                expanded=True,
            )
            tab_b = st.expander(
                f"PORTAFOLIO DE CRECIMIENTO   ·   apreciación de capital   ·   {len(mode_b_tickers)} ETFs",
                expanded=False,
            )

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
                        x=alt.X('Date:T', axis=_ed_axis('x', fmt='%b %Y', label_angle=0, year_ticks=True)),
                        y=alt.Y('Valor:Q', axis=_ed_axis('y', fmt='$,.0f', title='Valor ($)')),
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
                    ).configure_legend(
                        labelColor=CHART_PALETTE["title"], titleColor=CHART_PALETTE["axis"],
                        labelFont='Inter, system-ui, sans-serif', titleFont='Inter, system-ui, sans-serif',
                        labelFontSize=12, titleFontSize=10, titleFontWeight=500,
                        strokeColor='transparent', fillColor=CHART_PALETTE["bg"], padding=12, cornerRadius=0
                    )
                    st.altair_chart(chart, use_container_width=True)

                    # Aviso de honestidad: si el costo de origen es incompleto (acciones llegadas
                    # por transferencia con costo desconocido), la comparación vs VOO arranca desde
                    # donde el CSV tiene datos, no desde la compra original — el ROI es aproximado.
                    try:
                        _cq = logic.assess_ticker_quality(results, ticker) if ticker else {'level': 'ok'}
                    except Exception:
                        _cq = {'level': 'ok'}
                    if _cq.get('level') in ('unreliable', 'reconciled'):
                        st.markdown(
                            '<div style="border-left:4px solid #e0a23c;background:#fff8ec;padding:10px 14px;'
                            'margin:4px 0 0 0;font-family:Inter,sans-serif;font-size:12px;color:#664d1a;'
                            'line-height:1.5;"><b>Comparación aproximada.</b> A este activo le falta el '
                            'costo de origen en el CSV (probablemente las acciones llegaron por una '
                            '<b>transferencia</b>, con costo de compra desconocido). La curva vs S&amp;P 500 '
                            'arranca desde donde hay datos, no desde tu compra original, así que el ROI y la '
                            'diferencia con el índice son <b>estimados</b>, no exactos.</div>',
                            unsafe_allow_html=True)

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
                    <div class="da-tkpi">
                        <div class="da-tkpi-cell">
                            <p class="da-tkpi-label">Acciones</p>
                            <p class="da-tkpi-value">{stats['shares_owned']:.4f}</p>
                            <p class="da-tkpi-sub">Compradas {_hb_buys:.2f} · Vendidas {_hb_sells:.2f}</p>
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
                            _tech_events.append({'date': _b_ca['date'], 'ticker': ticker, 'tipo': 'Dividendo especial', 'desc': f"${_b_ca.get('amount', 0):.4f} por acción"})

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

                    _render_interpretation(ticker)

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
                            x=alt.X('Mes:O', sort=None, axis=_ed_axis('x', label_angle=0, title='Mes')),
                            y=alt.Y('Dividendo:Q', axis=_ed_axis('y', fmt='$,.2f', title='Dividendo ($)')),
                            tooltip=[alt.Tooltip('Mes:O', title='Mes'), alt.Tooltip('Dividendo:Q', format='$,.2f', title='Ingreso')]
                        ).properties(height=160, background=CHART_PALETTE["bg"]).configure_view(
                            strokeOpacity=0, fill=CHART_PALETTE["bg"]
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
            _da_section("Análisis de riesgo",
                        "Riesgo por subyacente (YieldMax) y concentración de holdings (ETFs de crecimiento)")
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
