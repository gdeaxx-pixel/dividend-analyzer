"""Hoja de carga (Fase 2) — los tres bloques del wizard con el lenguaje del artifact.

**El flujo no cambia, solo la piel.** Replica `app.py:1318-1730`: Transacciones →
Posiciones → Ingresos, con el mismo estado en `st.session_state` y las mismas llamadas a
`logic.py`. Lo que cambia es el tratamiento visual: eyebrow mono en mayúsculas, bordes
dashed, cero border-radius, y todos los colores desde los tokens extraídos del demo.

Ningún color se escribe a mano aquí: se usan las variables CSS que inyecta `ui.chrome`.
"""

from __future__ import annotations

import os

import streamlit as st

import logic


def _clave_gemini():
    """Resuelve la clave de Gemini sin ensuciar la interfaz.

    Invierte el orden de `app.py:1219` (que mira `st.secrets` primero) por dos motivos
    prácticos de este árbol: aquí la clave llega por entorno, porque `secrets.toml` es
    del repo canónico y no se copia al worktree; y **tocar `st.secrets` sin archivo pinta
    un recuadro de error rojo en la página** aunque se capture la excepción — Streamlit lo
    renderiza por su cuenta. Por eso se comprueba que exista el archivo antes de leerlo.
    """
    clave = os.getenv("GEMINI_API_KEY")
    if clave:
        return clave

    rutas = (os.path.expanduser("~/.streamlit/secrets.toml"),
             os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          ".streamlit", "secrets.toml"))
    if not any(os.path.exists(r) for r in rutas):
        return None
    try:
        return st.secrets.get("GEMINI_API_KEY")
    except Exception:                                              # noqa: BLE001
        return None


# ── Componentes de presentación ───────────────────────────────────────────────

def bloque_header(num: int, titulo: str, estado: str, subtitulo: str = "") -> str:
    """Encabezado numerado. `estado`: 'activo' | 'hecho' | 'bloqueado'.

    Equivale a `_da_block_header` de app.py, pero sin hex hardcodeados: el estado se
    expresa con las variables del artifact (--accent, --cash, --hair). `vd-reveal`
    (fila 34) es la animación de entrada — copiada literal de `.da-reveal` en
    `app.py:1314-1319`, solo con el prefijo del port.
    """
    marca = {"hecho": "✓"}.get(estado, str(num))
    clase = f"vd-bloque-num vd-bloque-{estado}"
    sub = f'<div class="vd-bloque-sub">{subtitulo}</div>' if subtitulo else ""
    return (
        '<div class="vd-bloque-head vd-reveal">'
        f'<div class="{clase}">{marca}</div>'
        f'<div><div class="vd-bloque-titulo">{titulo}</div>{sub}</div>'
        "</div>"
    )


def bloque_resumen(titulo: str, detalle: str) -> str:
    """Bloque completado y contraído."""
    return (
        '<div class="vd-bloque-resumen vd-reveal">'
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


def notificar_progreso(con_datos: bool) -> None:
    """Toasts de transición entre bloques — fila 33, texto y disparo literal de
    `app.py:1358-1362`. Se llama desde `app_v2.py` en cada run (no solo mientras se
    dibuja la carga): la transición al pill 3 ocurre justo cuando `con_datos` pasa a
    `True`, momento en el que `app_v2.py` deja de invocar `render_carga` — por eso el
    disparo vive aquí como función independiente y no dentro de `render_carga`."""
    hay_csv = st.session_state.get("_wizard_df_clean") is not None
    activo = 3 if con_datos else (2 if hay_csv else 1)
    previo = st.session_state.get("_vd_prev_pill", activo)
    if previo != activo:
        mensajes = {2: "Configura tus costos", 3: "Paso 3 de 3 · Resultados"}
        if activo in mensajes:
            st.toast(mensajes[activo], icon=":material/check_circle:")
    st.session_state["_vd_prev_pill"] = activo


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
                              "_wizard_csv_name", "_wizard_positions", "_wizard_income_summary",
                              "_wizard_income_df", "_wizard_income_multi",
                              "_wizard_1042s", "_wizard_1042s_sig", "_wizard_1042s_error"):
                    st.session_state.pop(clave, None)
                st.session_state["_wizard_pos_confirmed"] = False
                st.session_state["_wizard_listo"] = False
                st.rerun()
        return True

    st.markdown(bloque_header(1, "Transacciones · CSV / Excel", "activo"),
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

    # ── Lectura de fotos con Gemini ───────────────────────────────────────────
    # Rellena la tabla desde capturas del bróker, igual que `app.py:1455`. Reusa
    # `logic.extract_positions_from_images` tal cual: no lanza nunca, devuelve {} ante
    # cualquier fallo (sin SDK, sin red, sin cuota). Solo aparece si hay clave — sin ella
    # el bloque seguiría funcionando a mano, y un uploader muerto solo confunde.
    clave = _clave_gemini()
    leido = st.session_state.get("_wizard_ocr_positions") or {}
    if clave and analizables:
        fotos = st.file_uploader(
            "Fotos del portafolio", type=["png", "jpg", "jpeg"],
            accept_multiple_files=True, label_visibility="collapsed",
            key="_vd_fotos",
            help="Sube capturas donde se vean «Acciones/Posición» y «Base de coste / Cost "
                 "Basis» y rellenamos la tabla por ti.")
        if fotos:
            firma = tuple((f.name, f.size) for f in fotos)
            if firma != st.session_state.get("_wizard_photo_sig"):
                with st.spinner("Leyendo tus capturas…"):
                    payload = [(f.getvalue(), f.type or "image/jpeg") for f in fotos]
                    leido = logic.extract_positions_from_images(
                        payload, analizables, clave) or {}
                st.session_state["_wizard_ocr_positions"] = leido
                st.session_state["_wizard_photo_sig"] = firma
                st.rerun()
        if leido:
            st.markdown(bloque_resumen("Capturas leídas",
                                       f"{len(leido)} de {len(analizables)} instrumentos"),
                        unsafe_allow_html=True)

    previa = st.session_state.get("_wizard_csv_ticker_data") or {}
    posiciones = {}

    col_h1, col_h2, col_h3 = st.columns([1.2, 1, 1.4])
    col_h2.markdown('<p class="vd-col-header">Acciones</p>', unsafe_allow_html=True)
    col_h3.markdown('<p class="vd-col-header">Costo base</p>', unsafe_allow_html=True)

    for ticker in analizables:
        fila = previa.get(ticker, {})
        ocr = leido.get(ticker) or {}

        # Lo leído de la captura MANDA sobre la vista previa del CSV: la captura muestra la
        # posición real del bróker (con reinversiones y ventas ya aplicadas), mientras el
        # CSV solo suma compras. Ese es el motivo de subir la foto.
        acciones_def = ocr.get("shares")
        if acciones_def is None:
            acciones_def = fila.get("shares", 0.0)
        costo_def = ocr.get("cost_basis") or fila.get("invested", 0.0)

        col_t, col_a, col_c = st.columns([1.2, 1, 1.4])
        marca = '<span class="vd-ocr">captura</span>' if ocr else ""
        col_t.markdown(f'<p class="vd-ticker">{ticker} {marca}</p>',
                       unsafe_allow_html=True)
        acciones = col_a.number_input(
            "Acciones", min_value=0.0, value=float(acciones_def),
            step=0.0001, format="%.4f", key=f"_vd_sh_{ticker}", label_visibility="collapsed")
        costo = col_c.number_input(
            "Costo base", min_value=0.0, value=float(costo_def),
            step=0.01, format="%.2f", key=f"_vd_cb_{ticker}", label_visibility="collapsed")
        posiciones[ticker] = {"shares": acciones, "cost_basis": costo}

    st.markdown(
        '<p class="vd-nota">Los valores vienen del archivo como <b>vista previa</b>: '
        'cuentan compras, pero no las reinversiones ni las ventas. Ajústalos con lo que '
        'muestra tu bróker — esa es la cifra que manda.</p>', unsafe_allow_html=True)

    # Plegado a propósito: en una cartera real esta lista pasa de 300 tickers y aplasta
    # el bloque. Mismo tratamiento que `app.py:6289`.
    if excluidos:
        with st.expander(f"{len(excluidos)} instrumentos fuera del análisis"):
            st.caption("Acciones individuales, ETFs apalancados o inversos, y todo lo que "
                       "la calculadora no sabe interpretar todavía.")
            st.write(", ".join(excluidos))

    if st.button("Confirmar posiciones", key="_vd_confirm_pos", type="primary"):
        st.session_state["_wizard_positions"] = posiciones
        st.session_state["_wizard_pos_confirmed"] = True
        st.rerun()
    return False


def _render_1042s_resumen() -> None:
    """1042-S ya leído: tarjeta resumen + editar. Extraído de `render_bloque_1042s` para
    poder mostrarse junto al resumen de ingresos (fila 5: las dos fuentes conviven)."""
    forms = (st.session_state.get("_wizard_1042s") or {}).get("forms") or []
    n = len(forms)
    credito = sum(f.get("withholding_credit") or 0.0 for f in forms
                  if logic.income_code_str(f.get("income_code")) == "37")
    detalle = f"{n} formularios"
    if credito:
        detalle += f" · crédito ROC ${credito:,.2f}"
    st.markdown(bloque_resumen("1042-S leído", detalle), unsafe_allow_html=True)
    _, col = st.columns([5, 1])
    with col:
        if st.button("editar", key="_vd_edit_1042s", type="tertiary",
                     use_container_width=True):
            st.session_state.pop("_wizard_1042s", None)
            st.session_state.pop("_wizard_1042s_sig", None)
            st.session_state.pop("_wizard_1042s_error", None)
            st.rerun()


def _render_1042s_uploader() -> None:
    """Sube y parsea el 1042-S. Literal de `app.py:1624-1674`."""
    archivo = st.file_uploader("Formulario 1042-S", type=["pdf"],
                               key="_vd_upload_1042s", label_visibility="collapsed")
    st.caption(
        "Tu broker te lo envía a inicio de año (Schwab: Cuenta → Documentos → Impuestos). "
        "**Solo se emite a extranjeros no residentes** — si declaras como residente fiscal "
        "de EE.UU., recibes un 1099-DIV y puedes saltarte este paso. "
        "El PDF no se guarda: se lee en memoria y se descarta.")

    if archivo is None:
        return

    # El fallo se guarda en sesión, no se pinta y se olvida: la guarda por firma corta
    # antes de releer el mismo archivo, así que sin persistirlo el mensaje desaparecía en
    # el primer rerun y el usuario quedaba con su PDF adjunto, sin error y sin resultado.
    sig = (archivo.name, archivo.size)
    if sig != st.session_state.get("_wizard_1042s_sig"):
        with st.spinner("Leyendo tu 1042-S…"):
            resultado = logic.extract_1042s(archivo.getvalue(), _clave_gemini())
        st.session_state["_wizard_1042s_sig"] = sig

        if resultado is None:
            st.session_state["_wizard_1042s_error"] = "ilegible"
        else:
            codigos = {logic.income_code_str(f.get("income_code"))
                       for f in (resultado.get("forms") or [])}
            if "06" not in codigos and "37" not in codigos:
                st.session_state["_wizard_1042s_error"] = "sin_dividendos"
            else:
                st.session_state.pop("_wizard_1042s_error", None)
                st.session_state["_wizard_1042s"] = resultado
                st.rerun()

    error = st.session_state.get("_wizard_1042s_error")
    if error == "ilegible":
        st.error("No reconocimos este PDF como un Formulario 1042-S.")
        st.caption("Verifica que sea el documento que te envió tu broker (Schwab: Cuenta → "
                   "Documentos → Impuestos), en formato PDF y sin escanear.")
    elif error == "sin_dividendos":
        st.warning("Leímos el PDF, pero no encontramos dividendos (código 06) ni ROC "
                   "(código 37) en tus formularios.")


def _render_income_resumen() -> None:
    """Income CSV ya leído: tarjeta resumen + editar. Literal de `app.py:1599-1612`."""
    inc_sum = st.session_state.get("_wizard_income_summary") or {}
    nrec = sum(1 for d in (inc_sum.get("tickers") or {}).values() if d.get("received_total"))
    st.markdown(bloque_resumen("Ingresos validados", f"{nrec} tickers con dividendos recibidos"),
                unsafe_allow_html=True)
    if st.session_state.get("_wizard_income_multi"):
        st.caption("⚠️ El archivo incluye más de una cuenta; los totales podrían mezclarse. "
                   "Para una validación exacta, exporta el income de una sola cuenta.")
    _, col = st.columns([5, 1])
    with col:
        if st.button("editar", key="_vd_edit_inc", type="tertiary",
                     use_container_width=True):
            st.session_state.pop("_wizard_income_summary", None)
            st.session_state.pop("_wizard_income_df", None)
            st.session_state.pop("_wizard_income_multi", None)
            st.rerun()


def _render_income_uploader() -> None:
    """Sube y parsea el Investment Income de Schwab. Literal de `app.py:1676-1724`
    (fila 5: restaura el income CSV, que convive con el 1042-S sin sustituirlo)."""
    with st.expander("¿Tienes también el Investment Income? (opcional)", expanded=False):
        st.caption("Añade la validación dividendo por dividendo y la proyección de ingresos.")
        archivo = st.file_uploader(
            "Archivo de ingresos (Investment Income)",
            type=["csv", "xlsx"], key="_vd_upload_inc", label_visibility="collapsed")
        if archivo is None:
            return
        try:
            with st.spinner("Leyendo ingresos…"):
                inc_df = logic.parse_schwab_income_csv(archivo.getvalue())
            if inc_df is None:
                st.session_state["_wizard_income_summary"] = None
                st.session_state["_wizard_income_df"] = None
                st.error(
                    "No reconocimos este archivo como un **Investment Income** de Charles Schwab.")
                st.caption(
                    "Verifica que sea el reporte de **ingresos** (Cuenta → Historial → "
                    "*Investment Income* → Exportar) en formato **CSV** — no el de transacciones, "
                    "ni un Excel (.xls/.xlsx), ni un PDF.")
            elif len(inc_df) == 0:
                st.session_state["_wizard_income_summary"] = None
                st.session_state["_wizard_income_df"] = None
                st.error("Leímos el archivo, pero no quedó ninguna fila de dividendos por ticker.")
                st.caption(
                    "Puede que solo tuviera interés de cash o filas con montos/fechas vacíos. "
                    "Revisa que el export incluya las distribuciones de tus ETFs.")
            else:
                inc_summ = logic.summarize_income(inc_df)
                nrec_chk = sum(1 for d in (inc_summ.get("tickers") or {}).values()
                               if d.get("received_total"))
                if nrec_chk == 0:
                    # Parseó bien pero solo trae proyecciones "Estimated", sin "Received".
                    st.session_state["_wizard_income_summary"] = None
                    st.session_state["_wizard_income_df"] = None
                    st.error("Tu archivo solo trae proyecciones **“Estimated”**, no pagos **“Received”**.")
                    st.caption(
                        "Para validar necesitamos el histórico de ingresos **recibidos**. En Schwab, "
                        "amplía el rango de fechas hacia el pasado al exportar (la proyección futura "
                        "viene primero y se ignora).")
                else:
                    st.session_state["_wizard_income_summary"] = inc_summ
                    st.session_state["_wizard_income_df"] = inc_df
                    st.session_state["_wizard_income_multi"] = bool(inc_summ.get("multi_account"))
                    st.rerun()
        except Exception as error:                                    # noqa: BLE001
            st.session_state["_wizard_income_summary"] = None
            st.session_state["_wizard_income_df"] = None
            st.error("No pudimos leer el archivo de ingresos.")
            st.caption(f"Detalle técnico: {error}")


def render_bloque_1042s() -> None:
    """Bloque 3 — opcional. 1042-S y/o income CSV (Investment Income) de Schwab; las dos
    fuentes conviven, ninguna sustituye a la otra (fila 5, Fase 5b)."""
    tiene_1042s = st.session_state.get("_wizard_1042s") is not None
    tiene_income = st.session_state.get("_wizard_income_summary") is not None

    if tiene_1042s or tiene_income:
        if tiene_1042s:
            _render_1042s_resumen()
        if tiene_income:
            _render_income_resumen()
        return

    st.markdown(bloque_header(3, "Formulario 1042-S · opcional", "activo",
                              "Validación fiscal: confirma retención y ROC del año."),
                unsafe_allow_html=True)

    es_ibkr = st.session_state.get("_wizard_broker") == "ibkr"

    if es_ibkr:
        # Misma asimetría que ya se resolvió con Daniel en `669731c`: IBKR no tiene ni
        # reporte de ingresos ni 1042-S aparte en esta app — ambos vienen incluidos en el
        # archivo de transacciones del Bloque 1.
        st.markdown(bloque_resumen(
            "1042-S",
            "No hace falta — Interactive Brokers ya incluye el detalle fiscal en el "
            "archivo del Bloque 1."),
            unsafe_allow_html=True)
        st.markdown(bloque_resumen(
            "Ingresos",
            "No hace falta — Interactive Brokers ya incluye el detalle de dividendos en el "
            "archivo del Bloque 1."),
            unsafe_allow_html=True)
        return

    _render_1042s_uploader()
    _render_income_uploader()


def render_carga() -> bool:
    """Dibuja la hoja completa. Devuelve True cuando se puede pasar a resultados.

    El eyebrow «Paso 1 de 2 · Carga» vive ahora en el encabezado (`ui.chrome`). El título
    de esta pantalla es el wordmark de la marca — la frase vieja y el subtítulo «Viaje del
    dinero» se eliminan, no se mueven a otro sitio (decidido con Daniel, Fase 3b)."""
    st.markdown('<h2 class="vd-title vd-wordmark">INVIERTE &amp; GANA</h2>',
                unsafe_allow_html=True)
    st.markdown(
        '<p class="vd-lede">Tres bloques. El primero es obligatorio; los otros dos afinan '
        'la lectura.</p>',
        unsafe_allow_html=True)

    hay_csv = render_bloque_transacciones()
    if not hay_csv:
        st.markdown(bloque_bloqueado(2, "Posiciones del portafolio",
                                     "Se desbloquea al cargar el archivo."),
                    unsafe_allow_html=True)
        st.markdown(bloque_bloqueado(3, "Formulario 1042-S · opcional",
                                     "Se desbloquea al confirmar tus posiciones."),
                    unsafe_allow_html=True)
        return False

    hay_posiciones = render_bloque_posiciones()
    if not hay_posiciones:
        st.markdown(bloque_bloqueado(3, "Formulario 1042-S · opcional",
                                     "Se desbloquea al confirmar tus posiciones."),
                    unsafe_allow_html=True)
        return False

    render_bloque_1042s()

    if st.button("Ver resultados →", key="_vd_ir_resultados", type="primary"):
        st.session_state["_wizard_listo"] = True
        st.rerun()

    return bool(st.session_state.get("_wizard_listo"))


ESTILOS_CARGA = """
        /* Fila 34 — animación de revelación progresiva, copiada literal de
           `.da-reveal`/`@keyframes da-rev` en `app.py:1314-1319` (mismo timing y easing,
           solo el prefijo cambia de `da-` a `vd-`). */
        .vd-reveal { animation: vd-rev .42s cubic-bezier(.16, 1, .3, 1) both; }
        @keyframes vd-rev {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: none; }
        }
        @media (prefers-reduced-motion: reduce) { .vd-reveal { animation: none; } }

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
        .vd-col-header {
          font-family: var(--font-mono); font-size: 10px; font-weight: 700;
          letter-spacing: .06em; text-transform: uppercase; color: var(--ink-mut);
          margin: 0 0 4px;
        }
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
        .vd-ocr {
          font-family: var(--font-mono); font-size: 9.5px; font-weight: 700;
          letter-spacing: .08em; text-transform: uppercase; color: var(--cash);
          border: 1px solid var(--cash); padding: 1px 5px; margin-left: 6px;
          vertical-align: middle;
        }
        .vd-nota {
          font-size: 12px; line-height: 1.5; color: var(--ink-2); background: var(--panel-tint);
          border-left: 3px solid var(--accent); padding: 10px 14px; margin: 14px 0;
        }
        .vd-nota b { color: var(--ink); }
        [data-testid="stFileUploader"] section {
          background: var(--panel); border: 1px dashed var(--hair); border-radius: 0;
        }
        [data-testid="stFileUploaderDropzoneInstructions"] {
          color: var(--ink);
        }
        [data-testid="stFileUploaderDropzoneInstructions"] span {
          color: var(--ink);
        }
        [data-testid="stFileUploaderDropzoneInstructions"] small {
          color: var(--ink-mut);
        }
        [data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] {
          background: var(--panel); color: var(--ink); border: 1px solid var(--hair);
          border-radius: 0;
        }
        .vd-1042s-card {
          background: var(--panel-tint); border-left: 3px solid var(--hair);
          padding: 10px 14px; margin: 0 0 18px;
        }
        .vd-1042s-titulo {
          font-family: var(--font-mono); font-size: 11.5px; font-weight: 700;
          letter-spacing: .05em; text-transform: uppercase; color: var(--ink);
          margin: 0;
        }
        .vd-1042s-detalle { font-size: 12px; color: var(--ink-2); margin: 4px 0 0; }
        .vd-1042s-nota { font-size: 12px; color: var(--ink-mut); margin: 3px 0 0; }
"""
