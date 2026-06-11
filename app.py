import streamlit as st
import pandas as pd

import datetime
import logic
import storage
import json
import os
import time


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
        content: "Arrastra tu archivo aquí\A o haz clic para seleccionar\A\A CSV  ·  XLSX";
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
    .da-mini-row .tk {
        font-family: 'Inter', sans-serif;
        font-size: 11px;
        font-weight: 700;
        color: #021C36;
        letter-spacing: 0.02em;
    }
    .da-mini-row .num {
        font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
        font-size: 12px;
        font-weight: 700;
        color: #0F172A;
        text-align: right;
        letter-spacing: -0.01em;
    }
    .da-mini-row .pct {
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
        grid-template-columns: minmax(46px, 1.2fr) repeat(5, 1fr);
        gap: 10px;
        align-items: baseline;
        padding: 4px 0;
        min-width: 560px;
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
        <span style="font-size:0.9rem;font-weight:400;letter-spacing:0.12em;color:#8899aa;margin-left:12px;vertical-align:middle;">v2.8</span>
    </h1>
</div>
""", unsafe_allow_html=True)




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

_col_mode, _col_cache = st.columns([6, 1])
with _col_mode:
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

    _render_step_indicator(_active_pill, _prev_pill)

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

            if _broker_s2 == 'schwab':
                _has_csv = True
                _has_photo = bool(_positions)
                _has_income = bool(st.session_state.get('_wizard_income_summary'))

                def _tri_row(ok, title, desc):
                    _c = '#4caf82' if ok else '#c9a227'
                    _mark = '✓' if ok else '○'
                    return (f'<div style="display:flex;gap:8px;align-items:flex-start;margin:4px 0;">'
                            f'<span style="color:{_c};font-weight:800;line-height:1.5;">{_mark}</span>'
                            f'<span style="font-family:Inter,sans-serif;font-size:12.5px;color:#334;line-height:1.5;">'
                            f'<b>{title}</b> — {desc}</span></div>')

                st.markdown(
                    '<div style="border-left:4px solid #006497;background:#eef6fb;padding:12px 16px;margin:4px 0 14px 0;">'
                    '<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;color:#021C36;margin:0 0 6px 0;">'
                    'Charles Schwab · triangula con 3 fuentes para máxima certeza</p>'
                    '<p style="font-family:Inter,sans-serif;font-size:12px;color:#5a6b7a;margin:0 0 8px 0;line-height:1.6;">'
                    'Cada fuente confirma algo distinto. Con las tres validamos por triple vía: '
                    'historia, posición real y dividendos recibidos.</p>'
                    + _tri_row(_has_csv, 'CSV de transacciones', 'compras, ventas y dividendos (ya cargado).')
                    + _tri_row(_has_photo, 'Foto de posiciones', 'acciones y costo reales de hoy — corrige el historial incompleto.')
                    + _tri_row(_has_income, 'Archivo de ingresos (Investment Income)', 'dividendos realmente recibidos — valida el ingreso.')
                    + '</div>',
                    unsafe_allow_html=True
                )

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

        if skipped_tickers:
            with st.expander(f"{len(skipped_tickers)} ticker(s) excluidos del análisis"):
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
                if not _interp.get('lines'):
                    return
                _items = ''.join(
                    f'<li style="margin:0 0 6px 0;">{_ln}</li>' for _ln in _interp['lines'])
                st.markdown(
                    '<div style="border-left:4px solid #006497;background:#eef6fb;padding:12px 16px;margin:0 0 12px 0;">'
                    '<p style="font-family:Inter,sans-serif;font-size:9px;color:#006497;font-weight:700;'
                    'letter-spacing:0.12em;text-transform:uppercase;margin:0 0 8px 0;">Qué significa para ti</p>'
                    '<ul style="font-family:Inter,sans-serif;font-size:12px;color:#333333;line-height:1.55;'
                    'margin:0;padding-left:18px;">'
                    + _items + '</ul></div>',
                    unsafe_allow_html=True
                )

            # ── Calidad de datos: se calcula aquí (lo usa el aviso de abajo) y se
            #    renderiza al final dentro de un expander vía _render_data_quality_panel. ──
            _dq = logic.assess_data_quality(results, classify_map)
            _dq_unrel = sorted([t for t, q in _dq.items() if q['level'] == 'unreliable'])
            _dq_recon = sorted([t for t, q in _dq.items() if q['level'] == 'reconciled'])
            _dq_part  = sorted([t for t, q in _dq.items() if q['level'] == 'partial'])

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
                    _SER = ['Schwab (recibido 12m)', 'Tu cálculo (recibido 12m)',
                            'Schwab (proyección 12m)', 'Tu proyección (12m)']
                    _COLORS = ['#166534', '#86EFAC', '#1E40AF', '#60A5FA']   # verde osc/claro · azul osc/claro
                    _METODO = {
                        _SER[0]: 'Dividendos efectivamente pagados por el broker en los últimos 12 meses.',
                        _SER[1]: 'Mismo recibido, reconstruido desde tu CSV — debe coincidir con Schwab.',
                        _SER[2]: 'Proyección del broker: pago-ancla más reciente × frecuencia anual (asume el pago plano).',
                        _SER[3]: 'Run-Rate: promedio de tus pagos recientes (~3 meses) × frecuencia anual; refleja la caída real.',
                    }

                    def _mkt_of(_t):
                        _r = results.get(_t) if results else None
                        return _r.get('market_value') if isinstance(_r, dict) else None

                    _rows_chart = []
                    def _push(_t, _serie, _monto, _mkt):
                        if _monto is None:
                            return
                        _yld = (_monto / _mkt * 100) if (_mkt and _mkt > 0) else None
                        _rows_chart.append({'Ticker': _t, 'Serie': _serie, 'Monto': _monto,
                                            'Yield': _yld, 'Metodo': _METODO[_serie]})
                    for _t, _d in _proj.items():
                        _mkt = _mkt_of(_t)
                        _push(_t, _SER[0], _d.get('schwab_received_12m'), _mkt)
                        if _d.get('our_received_12m') is not None:
                            _push(_t, _SER[1], _d.get('our_received_12m'), _mkt)
                        _push(_t, _SER[2], _d.get('schwab_proj'), _mkt)
                        _push(_t, _SER[3], _d.get('our_proj'), _mkt)
                    _chart_df = pd.DataFrame(_rows_chart)

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

                    def _kpi_card(title, kind, accent_cls, tip_r, rows, border_color=None):
                        # rows: lista de (ticker, schwab, calc)
                        head = ('<div class="da-mini-row da-mini-head"><span>ETF</span>'
                                '<span class="num">Schwab</span><span class="num">Calc</span>'
                                '<span class="pct">Δ%</span></div>')
                        body = ''
                        tot_s, tot_c, tot_c_has = 0.0, 0.0, False
                        for _tk, _s, _c in rows:
                            body += (f'<div class="da-mini-row"><span class="tk">{_tk}</span>'
                                     f'<span class="num">{_fmt_money(_s)}</span>'
                                     f'<span class="num">{_fmt_money(_c)}</span>'
                                     f'{_pct_html(_s, _c)}</div>')
                            tot_s += (_s or 0)
                            if _c is not None:
                                tot_c += _c
                                tot_c_has = True
                        _tot_c = tot_c if tot_c_has else None
                        total = ('<div class="da-mini-row da-mini-total"><span class="tk">TOTAL</span>'
                                 f'<span class="num">{_fmt_money(tot_s)}</span>'
                                 f'<span class="num">{_fmt_money(_tot_c)}</span>'
                                 f'{_pct_html(tot_s, _tot_c)}</div>')
                        tip = _tip_for(kind, tot_s, _tot_c)
                        style = f' style="border-top-color:{border_color};"' if border_color else ''
                        box_cls = 'da-tip-box r' if tip_r else 'da-tip-box'
                        return (f'<div class="da-kpi-cell {accent_cls} da-tip"{style}>'
                                f'<p class="da-kpi-label">{title}<span class="da-tip-i">i</span></p>'
                                f'<div class="da-mini">{head}{body}{total}</div>'
                                f'<span class="{box_cls}">{tip}</span></div>')

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

                    st.markdown(
                        '<div class="da-income-kpi-grid">'
                        + _kpi_card('Total histórico', 'hist', 'da-kpi-navy', False, _rows_hist)
                        + _kpi_card('Últimos 12 meses', 'recv', 'da-kpi-accent', False, _rows_recv)
                        + _kpi_card('Proyectado anual', 'ann', '', False, _rows_ann, border_color=_div_color)
                        + _kpi_card('Proyectado mensual', 'mon', 'da-kpi-green', True, _rows_mon)
                        + '</div>',
                        unsafe_allow_html=True
                    )

                    st.markdown(
                        '<div style="margin:8px 0 2px 0;"><p style="font-family:Inter,sans-serif;font-size:13px;'
                        'font-weight:800;color:#021C36;margin:0 0 2px 0;">Ingresos: Schwab vs tu cálculo, y proyección</p>'
                        '<p style="font-family:Inter,sans-serif;font-size:12px;color:#8899aa;margin:0 0 8px 0;line-height:1.6;">'
                        'Solo se muestran tus <b>activos de generación de ingresos</b> (los índices/crecimiento de dividendo '
                        'marginal se ocultan para no aplastar la escala). Las dos barras <b>verdes</b> son lo <b>recibido</b> '
                        'en 12 meses (Schwab vs tu cálculo — deben coincidir); las dos <b>azules</b> son la <b>proyección</b> '
                        'a 12 meses: la de Schwab (azul oscuro) frente a la nuestra por run-rate reciente (azul claro). '
                        'La etiqueta Δ sobre cada activo es cuánto infla Schwab su proyección.</p></div>',
                        unsafe_allow_html=True
                    )

                    # Toggle de métrica del eje: Dólares vs Yield anualizado.
                    _use_yield = st.radio(
                        'Métrica del eje', ['Dólares ($)', 'Yield (%)'],
                        horizontal=True, label_visibility='collapsed', key='_income_metric'
                    ).startswith('Yield')
                    _has_yield = _chart_df['Yield'].notna().any()
                    if _use_yield and not _has_yield:
                        st.caption('Sin valor de mercado para calcular el yield; mostrando dólares.')
                        _use_yield = False
                    _yfield, _yfmt, _ytitle = (
                        ('Yield:Q', '.1f', 'Yield anualizado (%)') if _use_yield
                        else ('Monto:Q', '$,.0f', 'USD / 12 meses')
                    )

                    _bars = alt.Chart(_chart_df).mark_bar().encode(
                        x=alt.X('Ticker:N', title=None, axis=alt.Axis(labelAngle=0, labelFontSize=12)),
                        xOffset=alt.XOffset('Serie:N', sort=_SER),
                        y=alt.Y(_yfield, title=_ytitle, axis=alt.Axis(format=_yfmt)),
                        color=alt.Color('Serie:N', sort=_SER,
                                        scale=alt.Scale(domain=_SER, range=_COLORS),
                                        legend=alt.Legend(title=None, orient='top', columns=2, labelFontSize=11)),
                        tooltip=[alt.Tooltip('Ticker:N'), alt.Tooltip('Serie:N', title='Serie'),
                                 alt.Tooltip('Monto:Q', format='$,.2f', title='Monto (USD/12m)'),
                                 alt.Tooltip('Yield:Q', format='.2f', title='Yield anualizado (%)'),
                                 alt.Tooltip('Metodo:N', title='Cómo se calcula')],
                    )

                    # Etiqueta Δ sobre cada activo: % que Schwab sobre-proyecta frente a nuestro run-rate.
                    _delta_rows = []
                    for _t, _d in _proj.items():
                        _ov = _d.get('overstatement_pct')
                        if _ov is None:
                            continue
                        _top = max(_d.get('schwab_proj') or 0, _d.get('our_proj') or 0)
                        _mkt = _mkt_of(_t)
                        _top_y = (_top / _mkt * 100) if (_use_yield and _mkt and _mkt > 0) else _top
                        _delta_rows.append({'Ticker': _t, 'Top': _top_y, 'Label': f'Δ {_ov:+.0f}%'})
                    _layers = [_bars]
                    if _delta_rows:
                        _text = alt.Chart(pd.DataFrame(_delta_rows)).mark_text(
                            baseline='bottom', dy=-4, fontSize=11, fontWeight='bold',
                            color='#c9821f', font='Inter, system-ui, sans-serif'
                        ).encode(x=alt.X('Ticker:N'), y=alt.Y('Top:Q'), text=alt.Text('Label:N'))
                        _layers.append(_text)

                    _chart = alt.layer(*_layers).properties(
                        height=320, background=CHART_PALETTE["bg"]
                    ).configure_view(
                        strokeOpacity=0, fill=CHART_PALETTE["bg"]
                    ).configure_axis(
                        grid=True, gridColor=CHART_PALETTE["grid"], domainColor=CHART_PALETTE["axis"],
                        tickColor=CHART_PALETTE["axis"], labelColor=CHART_PALETTE["axis"],
                        titleColor=CHART_PALETTE["title"], labelFont='Inter, system-ui, sans-serif',
                        titleFont='Inter, system-ui, sans-serif', titleFontSize=11, titleFontWeight=500
                    ).configure_legend(labelColor=CHART_PALETTE["axis"])
                    st.altair_chart(_chart, use_container_width=True)
                    if _dropped:
                        _drop_txt = ', '.join(t for t, _ in _dropped)
                        st.caption(f'Ocultados (dividendo marginal, fuera del portafolio de ingresos): {_drop_txt}.')

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
                        st.markdown(
                            '<div style="border-left:4px solid #e0a23c;background:#fbf7ef;padding:12px 16px;margin:6px 0 4px 0;">'
                            '<p style="font-family:Inter,sans-serif;font-size:13px;font-weight:800;color:#021C36;margin:0 0 4px 0;">'
                            'Por qué la proyección de Schwab está inflada</p>'
                            '<ul style="font-family:Inter,sans-serif;font-size:12.5px;color:#444;margin:4px 0 0 0;padding-left:18px;">'
                            + _just_li + '</ul>' + _stable_html + '</div>',
                            unsafe_allow_html=True
                        )

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
                           '<span>Rendim. %</span><span>vs SPY</span></div>')
                _g_body = ''
                _g_mv = _g_pocket = _g_div = _g_bench = 0.0
                _g_bench_has = False
                for _tk, _d in _g_items:
                    _mv  = _d.get('market_value');             _pk = _d.get('pocket_investment')
                    _dv  = _d.get('dividends_collected_cash'); _roi = _d.get('roi_percent')
                    _broi = _d.get('benchmark_roi');           _bv = _d.get('benchmark_value')
                    _gain = ((_mv or 0) + (_dv or 0) - _pk) if _pk is not None else None
                    _vs = (_roi - _broi) if (_roi is not None and _broi is not None) else None
                    _g_body += (f'<div class="da-growth-row"><span>{_tk}</span>'
                                f'<span>{_gfmt_money(_pk)}</span>'
                                f'<span>{_gfmt_money(_mv)}</span>'
                                f'<span>{_gmoney_ret(_gain)}</span>'
                                f'<span>{_gret_html(_roi)}</span>'
                                f'<span>{_gret_html(_vs, " pts")}</span></div>')
                    _g_mv += (_mv or 0); _g_pocket += (_pk or 0); _g_div += (_dv or 0)
                    if _bv is not None:
                        _g_bench += _bv; _g_bench_has = True
                _g_tgain = (_g_mv + _g_div - _g_pocket) if _g_pocket > 0 else None
                _g_troi = ((_g_mv + _g_div - _g_pocket) / _g_pocket * 100) if _g_pocket > 0 else None
                _g_tspy = ((_g_bench - _g_pocket) / _g_pocket * 100) if (_g_bench_has and _g_pocket > 0) else None
                _g_tvs  = (_g_troi - _g_tspy) if (_g_troi is not None and _g_tspy is not None) else None
                _g_total = ('<div class="da-growth-row da-growth-total"><span>TOTAL</span>'
                            f'<span>{_gfmt_money(_g_pocket)}</span>'
                            f'<span>{_gfmt_money(_g_mv)}</span>'
                            f'<span>{_gmoney_ret(_g_tgain)}</span>'
                            f'<span>{_gret_html(_g_troi)}</span>'
                            f'<span>{_gret_html(_g_tvs, " pts")}</span></div>')
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
                          'precio. Verde = ganas, rojo = pierdes.<br>'
                          '<b>vs SPY</b>: cuántos <b>puntos</b> le ganas (verde) o le pierdes (rojo) '
                          'a haber invertido lo mismo en el S&amp;P 500 con tu mismo timing de '
                          'aportes — es tu <b>alfa</b> contra el índice.<br><br>'
                          '<b>Ojo</b>: el rendimiento es <b>acumulado, no anual</b>, así que una '
                          'posición con más tiempo de tenencia tiene ventaja natural; para comparar '
                          'por año, mira el CAGR en el detalle de cada activo más abajo.')
                _g_card = (f'<div class="da-kpi-cell da-kpi-navy da-tip">'
                           f'<p class="da-kpi-label">Crecimiento · rendimiento de precio'
                           f'<span class="da-tip-i">i</span></p>'
                           f'<div class="da-growth-wrap">{_g_head}{_g_body}{_g_total}</div>'
                           f'<span class="da-tip-box">{_g_tip}</span></div>')
                _da_section("Portafolio de crecimiento — rendimiento de precio",
                            "Tus posiciones de apreciación (no-income): cuánto pusiste, cuánto valen, cuánto han rendido y si le ganan al S&P 500.")
                st.markdown(
                    f'<div style="margin:6px 0 4px 0;">{_g_card}</div>',
                    unsafe_allow_html=True
                )

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
            _n_div_all = sum(1 for t in results if classify_map.get(t) == 'mode_a' and 'error' not in results[t])
            _n_cre_all = sum(1 for t in results if classify_map.get(t) == 'mode_b' and 'error' not in results[t])
            _da_section("Resumen global del portafolio",
                        f"Todo tu portafolio combinado · {_n_cre_all} de crecimiento + {_n_div_all} de dividendos · datos de {broker_label}")
            # ── TL;DR: veredicto de una línea en lenguaje natural ──
            st.markdown(
                f'<div style="border-left:4px solid {_gain_color};background:#F8FAFC;padding:14px 20px;margin:6px 0 16px 0;">'
                f'<p style="font-family:Inter,sans-serif;font-size:10px;color:#64748B;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;margin:0 0 6px 0;">En resumen</p>'
                f'<p style="font-family:Inter,sans-serif;font-size:15px;color:#0F172A;line-height:1.5;margin:0;">'
                f'Hoy tu portafolio vale <b style="font-family:{_MONO_FONT};">${total_market:,.0f}</b> sobre '
                f'<b style="font-family:{_MONO_FONT};">${total_invested:,.0f}</b> invertidos — retorno total '
                f'<b style="font-family:{_MONO_FONT};color:{_gain_color};">{_gain_sign}{total_roi:.1f}%</b>'
                f' (incluye <b style="font-family:{_MONO_FONT};color:#16A34A;">${total_divs:,.0f}</b> en dividendos cobrados).</p>'
                f'</div>',
                unsafe_allow_html=True
            )
            st.markdown(f"""
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

            # ── Composición: las posiciones concretas que forman este portafolio global ──
            _pos_rows = sorted(
                [(t, s) for t, s in results.items() if 'error' not in s],
                key=lambda x: -(x[1].get('market_value', 0) or 0)
            )
            _chips = ''
            for _t, _s in _pos_rows:
                _mv = _s.get('market_value', 0) or 0
                _w  = (_mv / total_market * 100) if total_market else 0
                _is_div = classify_map.get(_t) == 'mode_a'
                _tipo   = 'Dividendos' if _is_div else 'Crecimiento'
                _c      = '#4caf82' if _is_div else '#006497'
                _chips += (
                    f'<div style="display:flex;align-items:center;gap:10px;padding:9px 13px;'
                    f'background:#f6f8fa;border-left:3px solid {_c};">'
                    f'<span style="font-family:Inter,sans-serif;font-size:14px;font-weight:800;color:#021C36;">{_t}</span>'
                    f'<span style="font-family:Inter,sans-serif;font-size:9.5px;font-weight:700;color:{_c};'
                    f'text-transform:uppercase;letter-spacing:0.07em;">{_tipo}</span>'
                    f'<span style="flex:1;"></span>'
                    f'<span style="font-family:Inter,sans-serif;font-size:12px;color:#5a6b7a;'
                    f'font-variant-numeric:tabular-nums;">${_mv:,.0f} · {_w:.0f}%</span></div>'
                )
            st.markdown(
                '<p style="font-family:Inter,sans-serif;font-size:13px;color:#021C36;margin:14px 0 9px 0;line-height:1.55;">'
                f'<b>Es tu portafolio completo, no solo crecimiento.</b> Lo forman estas {len(_pos_rows)} posiciones '
                f'({_n_cre_all} de crecimiento + {_n_div_all} de dividendos); los totales de arriba las suman todas.</p>'
                '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:8px;margin:0 0 6px 0;">'
                + _chips + '</div>',
                unsafe_allow_html=True
            )

            if _dq_unrel:
                st.caption("Aviso: " + ", ".join(_dq_unrel) + " tienen historial de compras incompleto en el CSV, "
                           "así que el Total Invertido y el ROI de arriba los incluyen con un costo subestimado "
                           "(su % se ve inflado). Revisa el panel 'Calidad de datos' y exporta el historial completo de esos tickers.")
            st.caption("ROI = ganancia total acumulada desde el inicio · TIR (Tasa Interna de Retorno / IRR en inglés) = retorno anualizado considerando exactamente cuándo compraste cada lote — más preciso que el ROI para compras escalonadas")

            # ── Lectura del portafolio (síntesis educativa) ───────────
            _verdict = logic.build_portfolio_verdict(results, classify_map)
            if _verdict.get('lines'):
                _v_items = ''.join(
                    f'<li style="margin:0 0 6px 0;">{_vl}</li>' for _vl in _verdict['lines'])
                st.markdown(
                    '<div style="border-left:4px solid #021C36;background:#f6f8fa;padding:14px 18px;margin:10px 0 4px 0;">'
                    '<p style="font-family:Inter,sans-serif;font-size:10px;color:#021C36;font-weight:800;'
                    'letter-spacing:0.12em;text-transform:uppercase;margin:0 0 8px 0;">Lectura de tu portafolio</p>'
                    '<ul style="font-family:Inter,sans-serif;font-size:12.5px;color:#333333;line-height:1.55;'
                    'margin:0;padding-left:18px;">'
                    + _v_items + '</ul>'
                    '<p style="font-family:Inter,sans-serif;font-size:10px;color:#8899aa;margin:8px 0 0 0;">'
                    'Lectura educativa de tus números — no es recomendación de compra o venta.</p>'
                    '</div>',
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

                _da_section("Distribución y rendimiento de tu portafolio",
                            "Cómo se reparte tu capital y cómo rindió cada bloque")

                # ── Banner: rendimiento combinado ─────────────────────────
                st.markdown(
                    f'<div style="background:#021C36;padding:16px 24px;margin-bottom:14px;">'
                    f'<p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;font-weight:700;'
                    f'letter-spacing:0.14em;text-transform:uppercase;margin:0 0 4px 0;">Rendimiento Combinado Total</p>'
                    f'<p style="font-family:Inter,sans-serif;font-size:34px;font-weight:800;'
                    f'color:{_comb_color};margin:0 0 4px 0;letter-spacing:-0.02em;">{_comb_pct:+.2f}%</p>'
                    f'<p style="font-family:Inter,sans-serif;font-size:11px;color:#8899aa;margin:0;">'
                    f'Capital: <b style="color:#ffffff;">${_comb_inv:,.0f}</b>'
                    f'&nbsp;&nbsp;→&nbsp;&nbsp;Valor actual: <b style="color:#ffffff;">${_comb_val:,.0f}</b>'
                    f'&nbsp;&nbsp;·&nbsp;&nbsp;Dividendos cobrados: <b style="color:#4caf82;">${_comb_div:,.0f}</b></p>'
                    f'</div>',
                    unsafe_allow_html=True
                )

                # ── Barra de asignación del capital (reemplaza la dona) ────
                st.markdown(
                    f'<div style="margin:0 0 18px 0;">'
                    f'<p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;font-weight:700;'
                    f'letter-spacing:0.12em;text-transform:uppercase;margin:0 0 6px 0;">Reparto del capital</p>'
                    f'<div style="display:flex;height:18px;width:100%;overflow:hidden;">'
                    f'<div style="width:{_a_share}%;background:#006497;" title="Dividendos"></div>'
                    f'<div style="width:{_b_share}%;background:#2d3748;" title="Crecimiento"></div>'
                    f'</div>'
                    f'<div style="display:flex;justify-content:space-between;margin-top:7px;">'
                    f'<span style="font-family:Inter,sans-serif;font-size:11px;color:#021C36;">'
                    f'<span style="display:inline-block;width:9px;height:9px;background:#006497;margin-right:6px;vertical-align:middle;"></span>'
                    f'Dividendos <b>{_a_share:.0f}%</b> · ${_cmp_a_inv:,.0f}</span>'
                    f'<span style="font-family:Inter,sans-serif;font-size:11px;color:#021C36;">'
                    f'Crecimiento <b>{_b_share:.0f}%</b> · ${_cmp_b_inv:,.0f}'
                    f'<span style="display:inline-block;width:9px;height:9px;background:#2d3748;margin-left:6px;vertical-align:middle;"></span></span>'
                    f'</div></div>',
                    unsafe_allow_html=True
                )

                # ── Tarjeta de bloque (Dividendos / Crecimiento) ──────────
                def _render_block_card(name, accent, share, n_tickers, inv, mv, div, pct, tickers_detail):
                    _ret_color = "#4caf82" if pct >= 0 else "#e05c5c"
                    _have_today = mv + div
                    _money_row = (
                        '<div style="display:flex;justify-content:space-between;">'
                        '<span style="font-family:Inter,sans-serif;font-size:10px;color:#8899aa;'
                        'text-transform:uppercase;letter-spacing:0.07em;">{label}</span>'
                        '<span style="font-family:Inter,sans-serif;font-size:12px;font-weight:700;color:{c};">{val}</span></div>'
                    )
                    st.markdown(
                        f'<div style="background:#f6f3f2;padding:20px 22px;border-top:3px solid {accent};height:100%;">'
                        f'<p style="font-family:Inter,sans-serif;font-size:9px;color:{accent};font-weight:700;'
                        f'letter-spacing:0.12em;text-transform:uppercase;margin:0 0 10px 0;">'
                        f'<span style="display:inline-block;width:9px;height:9px;background:{accent};margin-right:7px;vertical-align:middle;"></span>'
                        f'{name} · {share:.0f}% del capital · {n_tickers} ticker(s)</p>'
                        f'<p style="font-family:Inter,sans-serif;font-size:34px;font-weight:800;'
                        f'color:{_ret_color};margin:0 0 2px 0;letter-spacing:-0.02em;">{pct:+.2f}%</p>'
                        f'<p style="font-family:Inter,sans-serif;font-size:10px;color:#8899aa;margin:0 0 14px 0;">'
                        f'retorno total (precio + dividendos)</p>'
                        f'<div style="display:flex;flex-direction:column;gap:5px;">'
                        + _money_row.format(label='Invertido', c='#021C36', val=f'${inv:,.0f}')
                        + _money_row.format(label='Valor de mercado', c='#021C36', val=f'${mv:,.0f}')
                        + _money_row.format(label='Dividendos cobrados', c='#4caf82', val=f'+${div:,.0f}')
                        + f'</div>'
                        f'<div style="border-top:1px solid #d8d2cf;margin:10px 0;"></div>'
                        f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px;">'
                        f'<span style="font-family:Inter,sans-serif;font-size:12px;font-weight:700;color:#021C36;">Tienes hoy</span>'
                        f'<span style="font-family:Inter,sans-serif;font-size:15px;font-weight:800;color:{_ret_color};">'
                        f'${_have_today:,.0f} <span style="font-size:11px;font-weight:700;">({pct:+.1f}%)</span></span></div>'
                        f'<p style="font-family:Inter,sans-serif;font-size:9px;color:#8899aa;text-transform:uppercase;'
                        f'letter-spacing:0.10em;margin:0 0 6px 0;">Activos</p>'
                        f'<div style="min-height:{_tk_minh}px;">{_ticker_rows(tickers_detail)}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                _col_a, _col_b = st.columns([1, 1])
                with _col_a:
                    _render_block_card('Dividendos', '#006497', _a_share, len(_cmp_a_rows),
                                       _cmp_a_inv, _cmp_a_mv, _cmp_a_div, _cmp_a_pct, _a_tickers_detail)
                with _col_b:
                    _render_block_card('Crecimiento', '#2d3748', _b_share, len(_cmp_b_rows),
                                       _cmp_b_inv, _cmp_b_mv, _cmp_b_div, _cmp_b_pct, _b_tickers_detail)

                # ── Lectura en lenguaje natural ───────────────────────────
                if _b_share >= _a_share:
                    _lead_name, _lead_share, _lead_pct = 'Crecimiento', _b_share, _cmp_b_pct
                    _oth_name, _oth_share, _oth_pct, _oth_div = 'Dividendos', _a_share, _cmp_a_pct, _cmp_a_div
                else:
                    _lead_name, _lead_share, _lead_pct = 'Dividendos', _a_share, _cmp_a_pct
                    _oth_name, _oth_share, _oth_pct, _oth_div = 'Crecimiento', _b_share, _cmp_b_pct, _cmp_b_div
                _lead_role = 'sostiene' if _lead_pct >= 0 else 'arrastra'
                if _oth_pct < 0 and _oth_div > 0:
                    _oth_clause = f' (su precio cayó, aunque devolvió ${_oth_div:,.0f} en efectivo)'
                elif _oth_div > 0:
                    _oth_clause = f' (incluye ${_oth_div:,.0f} en dividendos cobrados)'
                else:
                    _oth_clause = ''
                _lectura = (
                    f'El <b>{_lead_share:.0f}%</b> de tu capital ({_lead_name}) rinde '
                    f'<b>{_lead_pct:+.0f}%</b> y {_lead_role} el portafolio; el <b>{_oth_share:.0f}%</b> '
                    f'en {_oth_name} rinde <b>{_oth_pct:+.0f}%</b>{_oth_clause}. '
                    f'En conjunto: <b>{_comb_pct:+.0f}%</b>.'
                )
                st.markdown(
                    '<div style="border-left:4px solid #021C36;background:#f6f8fa;padding:14px 18px;margin:16px 0 4px 0;">'
                    '<p style="font-family:Inter,sans-serif;font-size:10px;color:#021C36;font-weight:800;'
                    'letter-spacing:0.12em;text-transform:uppercase;margin:0 0 8px 0;">Lectura</p>'
                    f'<p style="font-family:Inter,sans-serif;font-size:12.5px;color:#333333;line-height:1.55;margin:0;">{_lectura}</p>'
                    '<p style="font-family:Inter,sans-serif;font-size:10px;color:#8899aa;margin:8px 0 0 0;">'
                    'Lectura educativa de tus números — no es recomendación de compra o venta.</p>'
                    '</div>',
                    unsafe_allow_html=True
                )

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
                            {f'<p class="da-tkpi-value">${stats["ib_cost_basis"]:,.2f}</p><p class="da-tkpi-sub" style="color:#16a34a;">ROC: ${stats["roc_accumulated"]:,.2f} ({stats["roc_percent"]:.1f}%)</p>' if stats.get("ib_cost_basis") is not None else '<p class="da-tkpi-value" style="color:#cbd5e1;">—</p><p class="da-tkpi-sub">Edítala al cargar (Paso 1)</p>'}
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
                            {f'<p class="da-tkpi-value">${stats["ib_cost_basis"]:,.2f}</p><p class="da-tkpi-sub" style="color:#16a34a;">ROC: ${stats["roc_accumulated"]:,.2f} ({stats["roc_percent"]:.1f}%)</p>' if stats.get("ib_cost_basis") is not None else '<p class="da-tkpi-value" style="color:#cbd5e1;">—</p><p class="da-tkpi-sub">Edítala al cargar (Paso 1)</p>'}
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
