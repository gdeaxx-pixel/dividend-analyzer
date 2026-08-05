"""Hoja de carga (Fase 2) — los tres bloques del wizard con el lenguaje del artifact.

**El flujo no cambia, solo la piel.** Replica `app.py:1318-1730`: Transacciones →
Posiciones → Ingresos, con el mismo estado en `st.session_state` y las mismas llamadas a
`logic.py`. Lo que cambia es el tratamiento visual: eyebrow mono en mayúsculas, bordes
dashed, cero border-radius, y todos los colores desde los tokens extraídos del demo.

Ningún color se escribe a mano aquí: se usan las variables CSS que inyecta `ui.chrome`.
"""

from __future__ import annotations

import streamlit as st

import logic


# ── Componentes de presentación ───────────────────────────────────────────────

def bloque_header(num: int, titulo: str, estado: str, subtitulo: str = "") -> str:
    """Encabezado numerado. `estado`: 'activo' | 'hecho' | 'bloqueado'.

    Equivale a `_da_block_header` de app.py, pero sin hex hardcodeados: el estado se
    expresa con las variables del artifact (--accent, --cash, --hair).
    """
    marca = {"hecho": "✓"}.get(estado, str(num))
    clase = f"vd-bloque-num vd-bloque-{estado}"
    sub = f'<div class="vd-bloque-sub">{subtitulo}</div>' if subtitulo else ""
    return (
        '<div class="vd-bloque-head">'
        f'<div class="{clase}">{marca}</div>'
        f'<div><div class="vd-bloque-titulo">{titulo}</div>{sub}</div>'
        "</div>"
    )


def bloque_resumen(titulo: str, detalle: str) -> str:
    """Bloque completado y contraído."""
    return (
        '<div class="vd-bloque-resumen">'
        '<div class="vd-bloque-num vd-bloque-hecho">✓</div>'
        f'<div><span class="vd-resumen-titulo">{titulo}</span>'
        f'<span class="vd-resumen-detalle"> · {detalle}</span></div>'
        "</div>"
    )


def bloque_bloqueado(num: int, titulo: str, subtitulo: str) -> str:
    """Bloque visible pero atenuado desde el inicio, para que el recorrido completo se
    intuya antes de empezar (mismo criterio que `_da_block3_locked`)."""
    return (f'<div class="vd-bloque-locked">{bloque_header(num, titulo, "bloqueado", subtitulo)}'
            "</div>")


# ── Flujo ─────────────────────────────────────────────────────────────────────

def _leer_transacciones(archivo) -> tuple:
    """Parseo del CSV/Excel — misma ruta que `app.py`, sin lógica propia."""
    if archivo.name.endswith(".xlsx"):
        import pandas as pd
        return pd.read_excel(archivo), "generic"
    return logic.load_and_detect_csv(archivo)


def _resumen_por_ticker(df_limpio) -> dict:
    """Vista previa del Bloque 1 — réplica de `app.py:1400-1412`.

    OJO: filtra por `Action.contains('buy')`, así que NO suma las reinversiones ni resta
    las ventas. Es una vista previa del archivo, **no la posición**, que se confirma en el
    Bloque 2. Ver `fixtures/*/expected.json` § csv_preview_expected.
    """
    datos = {}
    if "Ticker" not in df_limpio.columns or "Action" not in df_limpio.columns:
        return datos
    for ticker, grupo in df_limpio.groupby("Ticker"):
        compras = grupo[grupo["Action"].str.lower().str.contains("buy", na=False)]
        dividendos = grupo[grupo["Action"].str.lower().str.contains("div", na=False)]
        datos[ticker] = {
            "shares": float(compras["Quantity"].sum()) if not compras.empty else 0.0,
            "invested": abs(float(compras["Amount"].sum())) if not compras.empty else 0.0,
            "dividends_csv": float(dividendos["Amount"].sum()) if not dividendos.empty else 0.0,
            "first_date": str(grupo["Date"].min())[:10] if not grupo.empty else "N/A",
        }
    return datos


BROKER_LABEL = {
    "schwab": "Charles Schwab",
    "ibkr": "Interactive Brokers",
    "generic": "Formato genérico",
}

_AYUDA_BROKER = (
    "Interactive Brokers: Informes → Extractos → Transaction History  |  "
    "Charles Schwab: Historial → Transacciones → Exportar"
)


def render_bloque_transacciones() -> bool:
    """Bloque 1. Devuelve True cuando ya hay un CSV cargado."""
    if st.session_state.get("_wizard_df_clean") is not None:
        broker = BROKER_LABEL.get(st.session_state.get("_wizard_broker"), "Archivo")
        nombre = st.session_state.get("_wizard_csv_name") or "transacciones.csv"
        tickers = st.session_state.get("_wizard_csv_ticker_data") or {}
        st.markdown(bloque_resumen("CSV cargado",
                                   f"{nombre} · {broker} · {len(tickers)} tickers"),
                    unsafe_allow_html=True)
        _, col = st.columns([5, 1])
        with col:
            if st.button("editar", key="_vd_edit_csv", type="tertiary",
                         use_container_width=True):
                for clave in ("_wizard_df_clean", "_wizard_csv_ticker_data", "_wizard_broker",
                              "_wizard_csv_name", "_wizard_positions", "_wizard_income_summary"):
                    st.session_state.pop(clave, None)
                st.session_state["_wizard_pos_confirmed"] = False
                st.rerun()
        return True

    st.markdown(bloque_header(1, "Transacciones · CSV / Excel", "activo",
                              "Sube el export de tu bróker para comenzar."),
                unsafe_allow_html=True)
    archivo = st.file_uploader("Archivo de transacciones", type=["csv", "xlsx"],
                               label_visibility="collapsed", help=_AYUDA_BROKER,
                               key="_vd_upload_txn")
    if archivo is None:
        return False

    try:
        crudo, broker = _leer_transacciones(archivo)
        if crudo.empty:
            st.error("No pudimos leer el formato del archivo. "
                     "Intenta guardarlo como «CSV UTF-8» o usa Excel (.xlsx).")
            return False

        limpio = logic.normalize_csv(crudo)
        faltan = [c for c in ("Date", "Ticker", "Amount") if c not in limpio.columns]
        if faltan:
            st.error(f"Falta(n) la(s) columna(s): {', '.join(faltan)}")
            st.caption(f"Columnas encontradas: {list(limpio.columns)}")
            return False

        st.session_state["_wizard_df_clean"] = limpio
        st.session_state["_wizard_csv_ticker_data"] = _resumen_por_ticker(limpio)
        st.session_state["_wizard_broker"] = broker
        st.session_state["_wizard_csv_name"] = archivo.name
        st.rerun()
    except Exception as error:                                    # noqa: BLE001
        st.error(f"Error procesando el archivo: {error}")
        with st.expander("Ver detalles"):
            import traceback
            st.code(traceback.format_exc())
    return False


def render_bloque_posiciones() -> bool:
    """Bloque 2. Confirma acciones y costo real por ETF."""
    if st.session_state.get("_wizard_pos_confirmed"):
        posiciones = st.session_state.get("_wizard_positions") or {}
        st.markdown(bloque_resumen("Posiciones confirmadas",
                                   f"{len(posiciones)} instrumentos"),
                    unsafe_allow_html=True)
        return True

    st.markdown(bloque_header(2, "Posiciones del portafolio", "activo",
                              "Confirma acciones y costo real de cada ETF."),
                unsafe_allow_html=True)

    limpio = st.session_state.get("_wizard_df_clean")
    tickers = sorted(t for t in limpio["Ticker"].dropna().unique() if t and t != "nan")
    modos = logic.classify_tickers(tickers)
    analizables = sorted(t for t, m in modos.items() if m in ("mode_a", "mode_b"))
    excluidos = sorted(t for t, m in modos.items() if m == "mode_skip")

    if not analizables:
        st.warning("No encontramos ETFs analizables en este archivo.")
        return False

    previa = st.session_state.get("_wizard_csv_ticker_data") or {}
    posiciones = {}
    for ticker in analizables:
        fila = previa.get(ticker, {})
        col_t, col_a, col_c = st.columns([1.2, 1, 1.4])
        col_t.markdown(f'<p class="vd-ticker">{ticker}</p>', unsafe_allow_html=True)
        acciones = col_a.number_input(
            "Acciones", min_value=0.0, value=float(fila.get("shares", 0.0)),
            step=0.0001, format="%.4f", key=f"_vd_sh_{ticker}", label_visibility="collapsed")
        costo = col_c.number_input(
            "Costo base", min_value=0.0, value=float(fila.get("invested", 0.0)),
            step=0.01, format="%.2f", key=f"_vd_cb_{ticker}", label_visibility="collapsed")
        posiciones[ticker] = {"shares": acciones, "cost_basis": costo}

    st.markdown(
        '<p class="vd-nota">Los valores vienen del archivo como <b>vista previa</b>: '
        'cuentan compras, pero no las reinversiones ni las ventas. Ajústalos con lo que '
        'muestra tu bróker — esa es la cifra que manda.</p>', unsafe_allow_html=True)

    if excluidos:
        st.caption(f"Fuera del análisis: {', '.join(excluidos)} "
                   "(acciones individuales o instrumentos no soportados)")

    if st.button("Confirmar posiciones", key="_vd_confirm_pos", type="primary"):
        st.session_state["_wizard_positions"] = posiciones
        st.session_state["_wizard_pos_confirmed"] = True
        st.rerun()
    return False


def render_bloque_ingresos() -> None:
    """Bloque 3 — opcional, valida el ingreso contra el reporte del bróker."""
    if st.session_state.get("_wizard_income_summary") is not None:
        st.markdown(bloque_resumen("Ingresos cargados", "validación cruzada activa"),
                    unsafe_allow_html=True)
        return

    st.markdown(bloque_header(3, "Archivo de ingresos · opcional", "activo",
                              "Validación extra contra el reporte de tu bróker."),
                unsafe_allow_html=True)
    archivo = st.file_uploader("Archivo de ingresos", type=["csv", "xlsx"],
                               label_visibility="collapsed", key="_vd_upload_inc",
                               help="Schwab: Historial → Ingresos por inversión → Exportar")
    if archivo is not None:
        st.session_state["_wizard_income_name"] = archivo.name
        st.session_state["_wizard_income_summary"] = {"archivo": archivo.name}
        st.rerun()


def render_carga() -> bool:
    """Dibuja la hoja completa. Devuelve True cuando se puede pasar a resultados."""
    st.markdown('<span class="vd-badge">Paso 1 de 2 · Carga</span>', unsafe_allow_html=True)
    st.markdown('<h2 class="vd-title">Tu portafolio, tal como lo exporta tu bróker</h2>',
                unsafe_allow_html=True)
    st.markdown(
        '<p class="vd-lede">Tres bloques. El primero es obligatorio; los otros dos afinan '
        'la lectura. Nada sale de tu navegador hacia un servidor nuestro.</p>',
        unsafe_allow_html=True)

    hay_csv = render_bloque_transacciones()
    if not hay_csv:
        st.markdown(bloque_bloqueado(2, "Posiciones del portafolio",
                                     "Se desbloquea al cargar el archivo."),
                    unsafe_allow_html=True)
        st.markdown(bloque_bloqueado(3, "Archivo de ingresos · opcional",
                                     "Se desbloquea al confirmar tus posiciones."),
                    unsafe_allow_html=True)
        return False

    hay_posiciones = render_bloque_posiciones()
    if not hay_posiciones:
        st.markdown(bloque_bloqueado(3, "Archivo de ingresos · opcional",
                                     "Se desbloquea al confirmar tus posiciones."),
                    unsafe_allow_html=True)
        return False

    render_bloque_ingresos()
    return True


ESTILOS_CARGA = """
        .vd-bloque-head { display: flex; align-items: center; gap: 11px; margin: 18px 0 10px; }
        .vd-bloque-num {
          flex-shrink: 0; width: 26px; height: 26px; display: flex; align-items: center;
          justify-content: center; font-family: var(--font-mono); font-size: 12px;
          font-weight: 700; border-radius: 0;
        }
        .vd-bloque-activo { background: var(--accent); color: var(--panel); }
        .vd-bloque-hecho { background: var(--cash); color: var(--panel); }
        .vd-bloque-bloqueado { background: var(--hair); color: var(--ink-mut); }
        .vd-bloque-titulo {
          font-family: var(--font-mono); font-size: 12px; font-weight: 700;
          letter-spacing: .06em; text-transform: uppercase; color: var(--ink);
        }
        .vd-bloque-sub { font-size: 11.5px; color: var(--ink-mut); margin-top: 1px; }
        .vd-bloque-locked { opacity: .5; border: 1px dashed var(--hair); padding: 10px 14px; margin: 6px 0; }
        .vd-bloque-locked .vd-bloque-head { margin: 0; }
        .vd-bloque-resumen {
          display: flex; align-items: center; gap: 11px; background: var(--panel-tint);
          border-left: 3px solid var(--cash); padding: 10px 14px; margin: 12px 0 4px;
        }
        .vd-resumen-titulo {
          font-family: var(--font-mono); font-size: 11.5px; font-weight: 700;
          letter-spacing: .05em; text-transform: uppercase; color: var(--ink);
        }
        .vd-resumen-detalle { font-size: 12px; color: var(--ink-mut); }
        .vd-ticker {
          font-family: var(--font-mono); font-size: 14px; font-weight: 700;
          color: var(--ink); margin: .35rem 0 0;
        }
        .vd-nota {
          font-size: 12px; line-height: 1.5; color: var(--ink-2); background: var(--panel-tint);
          border-left: 3px solid var(--accent); padding: 10px 14px; margin: 14px 0;
        }
        .vd-nota b { color: var(--ink); }
        [data-testid="stFileUploader"] section {
          background: var(--panel); border: 1px dashed var(--hair); border-radius: 0;
        }
"""
