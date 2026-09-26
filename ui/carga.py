"""Hoja de carga (Fase 2) — los tres bloques del wizard con el lenguaje del artifact.

**El flujo no cambia, solo la piel.** Replica `app_old.py:1318-1730`: Transacciones →
Posiciones → Ingresos, con el mismo estado en `st.session_state` y las mismas llamadas a
`logic.py`. Lo que cambia es el tratamiento visual: eyebrow mono en mayúsculas, bordes
dashed, cero border-radius, y todos los colores desde los tokens extraídos del demo.

Ningún color se escribe a mano aquí: se usan las variables CSS que inyecta `ui.chrome`.
"""

from __future__ import annotations

import hashlib
import os

import streamlit as st

import logic
import storage
from ui import adapters, componentes, estado


CLAVES_CONTEXTO_CARTERA = (
    "_wizard_df_clean", "_wizard_csv_ticker_data", "_wizard_broker", "_wizard_csv_name",
    "_wizard_positions", "_wizard_income_summary", "_wizard_income_df", "_wizard_income_multi",
    "_vd_resultados", "_wizard_1042s", "_wizard_1042s_sig", "_wizard_1042s_error",
    "_wizard_ocr_positions",
    "_wizard_photo_sig",
    # F2 §4.4: la captura de casos se limpia al «editar» el CSV del paso 1 (cartera nueva,
    # consentimiento nuevo). `_captura_consent` es la instantánea del consentimiento
    # (ver `_capturar_caso`); `_consent_capture` es clave de widget y también se purga aquí.
    "_consent_capture", "_captura_consent", "_captura_origen", "_captura_case_id",
)

# F2 §4.1 — Días de retención de un caso capturado antes de borrado automático
# (regla de lifecycle del bucket). La Fase 4 lo usará también en PRIVACY.md.
CAPTURA_RETENCION_DIAS = 90

# Textos de la casilla de consentimiento — LITERALES, aprobados por Daniel el
# 2026-09-25. No reescribir.
_ETIQUETA_CAPTURA = "Ayúdanos a mejorar la calculadora con tu caso"

_AYUDA_CAPTURA = (
    "Guardamos una copia de tus movimientos sin nombre, correo ni número de cuenta "
    "(fecha, ticker, cantidad, precio, importe) y las posiciones que confirmas, para "
    "comprobar que la calculadora sigue acertando con casos reales. No entrena ninguna IA. "
    f"Se borra a los {CAPTURA_RETENCION_DIAS} días salvo que lo convirtamos en caso de "
    "prueba; puedes pedir que lo borremos cuando quieras. Opcional: sin marcarla la app "
    "funciona igual."
)

_QUE_GUARDAMOS = (
    "Sí: fechas, tipo de movimiento, ticker, cantidad, precio, importe; acciones y costo "
    "que confirmas; totales leídos del 1042-S. No: el archivo original, el nombre del "
    "archivo, tus capturas, el PDF, tu correo, tu nombre, tu número de cuenta ni tu IP."
)


def _clave_gemini():
    """Resuelve la clave de Gemini sin ensuciar la interfaz.

    Invierte el orden de `app_old.py:1219` (que mira `st.secrets` primero) por dos motivos
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

    Equivale a `_da_block_header` de app_old.py, pero sin hex hardcodeados: el estado se
    expresa con las variables del artifact (--accent, --cash, --hair). `vd-reveal`
    (fila 34) es la animación de entrada — copiada literal de `.da-reveal` en
    `app_old.py:1314-1319`, solo con el prefijo del port.
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
    `app_old.py:1358-1362`. Se llama desde `app_old.py` en cada run (no solo mientras se
    dibuja la carga): la transición al pill 3 ocurre justo cuando `con_datos` pasa a
    `True`, momento en el que `app_old.py` deja de invocar `render_carga` — por eso el
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
    """Parseo del CSV/Excel — misma ruta que `app_old.py`, sin lógica propia."""
    if archivo.name.endswith(".xlsx"):
        import pandas as pd
        return pd.read_excel(archivo), "generic"
    return logic.load_and_detect_csv(archivo)


def _resumen_por_ticker(df_limpio) -> dict:
    """Vista previa del Bloque 1 — réplica de `app_old.py:1400-1412`.

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
        _descarte = st.session_state.get("_wizard_csv_descarte")
        if _descarte and _descarte.get("total"):
            # E3 (spec S5 §3): toda fila "MM/DD/YYYY as of MM/DD/YYYY" que el parser de
            # fechas no reconoce se descartaba en silencio — Stock Split, MoneyLink
            # Transfer, Pr Yr Div Reinvest, etc. Las que SÍ se recuperan (paso 2, la
            # fecha efectiva) no llegan aquí: esto son las que se siguen descartando.
            _detalle = ", ".join(f"{v}× {k}" for k, v in
                                 sorted(_descarte["por_accion"].items(),
                                        key=lambda kv: -kv[1]))
            st.caption(f"⚠️ {_descarte['total']} fila(s) con fecha «... as of ...» que no "
                      f"se pudieron ubicar en el tiempo, excluidas: {_detalle}.")
        _, col = st.columns([5, 1])
        with col:
            if st.button("editar", key="_vd_edit_csv", type="tertiary",
                         use_container_width=True):
                # `_vd_resultados` va en la lista: es el caché de `analyze_portfolio`, y sin
                # borrarlo `ui/vistas.py::_resultados` lo devuelve tal cual —solo recalcula
                # cuando es `None`—, así que el CSV nuevo se mostraría con las cifras del
                # anterior. Con la captura dentro del cálculo, además arrastraría posiciones
                # de un portafolio a otro.
                for clave in CLAVES_CONTEXTO_CARTERA:
                    st.session_state.pop(clave, None)
                st.session_state["_wizard_pos_confirmed"] = False
                st.session_state["_wizard_listo"] = False
                st.rerun()
        return True

    st.markdown(bloque_header(1, "Transacciones", "activo"),
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
        st.session_state["_wizard_csv_descarte"] = getattr(
            logic.normalize_csv, "ultimo_descarte", None)
        st.rerun()
    except Exception as error:                                    # noqa: BLE001
        st.error(f"Error procesando el archivo: {error}")
        with st.expander("Ver detalles"):
            import traceback
            st.code(traceback.format_exc())
    return False


_SIN_DECLARAR = "— No lo sé / prefiero no decirlo —"


def _render_residencia_fiscal() -> None:
    """Residencia fiscal del cliente — vive aquí porque es una propiedad de ÉL, no de una
    vista. Antes el único selector estaba enterrado en Detalle → Proyección, dentro de un
    expander colapsado, y su valor no salía de esa función: todas las cifras fiscales de la
    app corrían a 30% pasara lo que pasara.

    Sin declarar es el default a propósito. La alternativa —asumir 30%— le inventa a un
    mexicano una retención tres veces mayor a la que le corresponde; y asumir 0% le dice a
    cualquiera que toda su retención vuelve. Ninguna de las dos es un dato.
    """
    opciones = [_SIN_DECLARAR] + list(logic.NRA_COUNTRY_RATES.keys())
    actual = estado.perfil_fiscal()["country"]
    idx = opciones.index(actual) if actual in opciones else 0

    col_sel, col_nota = st.columns([1, 1.4])
    with col_sel:
        elegido = st.selectbox(
            "Tu residencia fiscal", opciones, index=idx, key="_vd_residencia",
            help="Determina la retención a la que tienes DERECHO sobre dividendos de "
                 "fuente EE.UU.: 30% base para no-residentes, 10% México y 15% Chile, "
                 "España y Venezuela por "
                 "tratado, 0% si eres residente fiscal en EE.UU. Sin este dato no "
                 "estimamos cuánto de lo retenido puedes recuperar.")
    estado.declarar_pais(None if elegido == _SIN_DECLARAR else elegido)

    perfil = estado.perfil_fiscal()
    with col_nota:
        if not perfil["rate_declared"]:
            st.markdown(
                '<p class="vd-nota">Sin este dato mostramos la retención <b>real</b> de tu '
                'archivo, pero no estimamos cuánto vuelve — esa cifra dependería por '
                'completo del supuesto.</p>', unsafe_allow_html=True)
        else:
            tasa = perfil["rate_pct"]
            extra = (" por el tratado fiscal — solo aplica si tu <b>W-8BEN</b> está "
                     "presentado y vigente" if perfil["has_treaty"] else "")
            st.markdown(
                f'<p class="vd-nota">Retención con derecho: <b>{tasa:.0f}%</b>{extra}. '
                'Verificamos contra tu archivo si es la que te aplicaron de verdad.</p>',
                unsafe_allow_html=True)


def _firma_fotos(fotos) -> tuple:
    """Firma por CONTENIDO, no por (nombre, tamaño): dos capturas distintas guardadas con el
    mismo nombre y el mismo tamaño dejaban la firma igual, el OCR no se volvía a correr y la
    tabla seguía mostrando las posiciones de la foto anterior."""
    return tuple(hashlib.sha256(f.getvalue()).hexdigest() for f in fotos)


def render_bloque_posiciones() -> bool:
    """Bloque 2. Confirma acciones y costo real por ETF."""
    if st.session_state.get("_wizard_pos_confirmed"):
        posiciones = st.session_state.get("_wizard_positions") or {}
        st.markdown(bloque_resumen("Posiciones confirmadas",
                                   f"{len(posiciones)} instrumentos"),
                    unsafe_allow_html=True)
        # U4 §5.3.1 (§3A.1): completados resumidos con Editar. Mismo patrón que el
        # «editar» del paso 1, pero borrando SOLO la confirmación — NO todo
        # CLAVES_CONTEXTO_CARTERA: eso tiraría también el CSV del paso 1.
        _, col = st.columns([5, 1])
        with col:
            if st.button("editar", key="_vd_edit_pos", type="tertiary",
                         use_container_width=True):
                st.session_state["_wizard_pos_confirmed"] = False
                st.session_state["_wizard_listo"] = False
                # `_vd_resultados` va: `analyze_portfolio` corrió con la captura
                # confirmada; si el cliente edita los importes, el caché ya no
                # corresponde a lo que ve (mismo motivo que en el editar del paso 1).
                st.session_state.pop("_vd_resultados", None)
                st.rerun()
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
    # Rellena la tabla desde capturas del bróker, igual que `app_old.py:1455`. Reusa
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
                 "Basis» y rellenamos la tabla por ti. "
                 "Las imágenes se envían a Google Gemini para leerlas; esta app no las guarda.")
        st.caption("Las capturas se leen con Google Gemini. Antes de subirlas, recorta tu "
                  "nombre y tu número de cuenta.")
        if fotos:
            firma = _firma_fotos(fotos)
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

    # U4 §5.3.2: la residencia fiscal se muda del paso 2 al paso 3
    # (`render_bloque_1042s`). Aquí desaparecía al confirmar posiciones — la rama
    # confirmada retorna antes— y un cliente de IBKR nunca podía declararla.

    # Plegado a propósito: en una cartera real esta lista pasa de 300 tickers y aplasta
    # el bloque. Mismo tratamiento que `app_old.py:6289`.
    if excluidos:
        with st.expander(f"{len(excluidos)} instrumentos fuera del análisis"):
            st.caption("Acciones individuales, ETFs apalancados o inversos, y todo lo que "
                       "la calculadora no sabe interpretar todavía.")
            st.write(", ".join(excluidos))

    # F2 §4.1 — Casilla de consentimiento de captura de casos (textos literales
    # aprobados por Daniel el 2026-09-25). Solo se dibuja con backend activo: sin
    # él, la pantalla queda idéntica a antes.
    if storage.is_enabled():
        # El texto va VISIBLE debajo, no en `help=`: un tooltip detrás de un «?» no es
        # consentimiento informado (mockup aprobado por Daniel, auditoría Opus 25-sep).
        st.checkbox(_ETIQUETA_CAPTURA, value=False, key="_consent_capture")
        st.caption(_AYUDA_CAPTURA)
        with st.expander("Qué guardamos y qué no"):
            st.caption(_QUE_GUARDAMOS)

    if st.button("Confirmar posiciones", key="_vd_confirm_pos", type="primary"):
        st.session_state["_wizard_positions"] = posiciones
        st.session_state["_wizard_pos_confirmed"] = True
        # F2 §4.1: el origen se calcula con los valores por defecto que vio el cliente
        # (`leido`/`previa` son locales de ESTE render), no con lo que haya en sesión
        # más tarde. El consentimiento se instantanea por el mismo motivo y porque
        # Streamlit purga las claves de widget que no se instancian en el run
        # (MEDIDO: al confirmar, esta rama deja de dibujar la casilla y
        # `_consent_capture` desaparece de la sesión antes de llegar a
        # «Ver resultados»). `_capturar_caso` lee la instantánea.
        st.session_state["_captura_origen"] = logic.origen_posiciones(posiciones, leido, previa)
        st.session_state["_captura_consent"] = st.session_state.get("_consent_capture") is True
        # La captura entra a `analyze_portfolio` como base de costo (ver `ui/vistas.py`
        # :_resultados), así que unos resultados calculados ANTES de confirmarla se quedarían
        # sin ella y el peldaño 5 declararía indeterminado un costo que el cliente ya dio.
        st.session_state.pop("_vd_resultados", None)
        st.rerun()
    return False


def _render_residencia_detectada() -> None:
    """El 1042-S declara la residencia del cliente (casilla 13b) y la tasa que le APLICARON
    (casilla 3b). Es la fuente autoritativa: la emite el agente de retención ante el IRS.

    **Se propone, no se aplica.** El mapeo de código IRS a país es best-effort (el IRS tiene
    su propia tabla y no siempre coincide con ISO), así que un código mal traducido lo tiene
    que cazar el humano antes de que mueva una sola cifra. Mismo criterio que el uploader
    del crédito ROC, que ya exige confirmación.
    """
    datos = st.session_state.get("_wizard_1042s") or {}
    codigo = datos.get("recipient_country_code")
    if not codigo:
        return

    detectado = logic.pais_desde_codigo_1042s(codigo)
    perfil = estado.perfil_fiscal()
    if perfil["rate_declared"] and perfil["country"] == detectado:
        return                                    # ya está declarado y coincide: nada que hacer

    if detectado is None:
        st.info(f"Tu 1042-S declara el país **{codigo}** (casilla 13b), que no está en "
                "nuestra tabla de tasas. Elige tu residencia a mano en el Paso 2.")
        return

    tasa = logic.NRA_COUNTRY_RATES[detectado][0]
    if perfil["rate_declared"]:
        aviso = (f"Tu 1042-S dice **{detectado}** ({codigo}), pero declaraste "
                 f"**{perfil['country']}**.")
    else:
        aviso = f"Tu 1042-S declara residencia en **{detectado}** ({codigo})."

    st.info(f"{aviso} Con ese país la retención con derecho es del **{tasa:.0f}%**.")
    col, _ = st.columns([1, 2])
    with col:
        if st.button(f"Usar {detectado}", key="_vd_conf_pais_1042s", type="primary",
                     use_container_width=True):
            estado.declarar_pais(detectado, source="1042s")
            st.rerun()


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
    _render_residencia_detectada()
    _, col = st.columns([5, 1])
    with col:
        if st.button("editar", key="_vd_edit_1042s", type="tertiary",
                     use_container_width=True):
            st.session_state.pop("_wizard_1042s", None)
            st.session_state.pop("_wizard_1042s_sig", None)
            st.session_state.pop("_wizard_1042s_error", None)
            st.rerun()


def _render_1042s_uploader() -> None:
    """Sube y parsea el 1042-S. Literal de `app_old.py:1624-1674`."""
    archivo = st.file_uploader("Formulario 1042-S", type=["pdf"],
                               key="_vd_upload_1042s", label_visibility="collapsed")
    st.caption(
        "Tu broker te lo envía a inicio de año (Schwab: Cuenta → Documentos → Impuestos). "
        "**Solo se emite a extranjeros no residentes** — si declaras como residente fiscal "
        "de EE.UU., recibes un 1099-DIV y puedes saltarte este paso. "
        "El PDF no se guarda: se lee en memoria, no se envía a ningún servicio externo y se "
        "descarta.")

    if archivo is None:
        return

    # El fallo se guarda en sesión, no se pinta y se olvida: la guarda por firma corta
    # antes de releer el mismo archivo, así que sin persistirlo el mensaje desaparecía en
    # el primer rerun y el usuario quedaba con su PDF adjunto, sin error y sin resultado.
    sig = (archivo.name, archivo.size)
    if sig != st.session_state.get("_wizard_1042s_sig"):
        with st.spinner("Leyendo tu 1042-S…"):
            resultado = logic.extract_1042s(archivo.getvalue())
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
        st.error("No pudimos leer este PDF de forma automática.")
        st.caption("Verifica que sea el 1042-S que te envió tu broker (Schwab: Cuenta → "
                   "Documentos → Impuestos). Si es escaneado, pide la versión digital. También "
                   "puedes saltar este paso: la app funciona sin el 1042-S; solo pierdes la "
                   "validación contra el documento oficial.")
    elif error == "sin_dividendos":
        st.warning("Leímos el PDF, pero no encontramos dividendos (código 06) ni ROC "
                   "(código 37) en tus formularios.")


def _render_income_resumen() -> None:
    """Income CSV ya leído: tarjeta resumen + editar. Literal de `app_old.py:1599-1612`."""
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
    """Sube y parsea el Investment Income de Schwab. Literal de `app_old.py:1676-1724`
    (fila 5: restaura el income CSV, que convive con el 1042-S sin sustituirlo).

    U4 §5.3.3: ya no trae su propio expander — vive dentro del desplegable único
    «Añadir documentos» del paso 3, y Streamlit no permite anidar expanders (lanza
    `StreamlitAPIException`). El uploader y su lógica de parseo no cambian."""
    st.caption("Investment Income (opcional): añade la validación dividendo por "
               "dividendo y la proyección de ingresos.")
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
    """Bloque 3 — opcional. Residencia fiscal + 1042-S y/o income CSV (Investment
    Income) de Schwab; las dos fuentes conviven, ninguna sustituye a la otra (fila 5,
    Fase 5b).

    U4 §5.3.2 (§6›9 B C): la residencia fiscal se muda aquí desde el paso 2 y va
    ANTES de los dos retornos tempranos (documentos ya cargados, e IBKR). Si quedara
    después, un cliente de IBKR NUNCA podría declarar su país y todas sus cifras
    fiscales correrían al 30%. Persiste por `ui/estado.py::declarar_pais`, no por la
    clave del widget.
    U4 §5.3.3 (§3A.5): los dos documentos quedan bajo un único desplegable «Añadir
    documentos»; los uploaders y su lógica no cambian, solo se envuelven."""
    st.markdown(bloque_header(3, "Información fiscal · opcional", "activo",
                              "Tu residencia y, si los tienes, tus documentos fiscales."),
                unsafe_allow_html=True)
    # Título del bloque — antes decía «Formulario 1042-S · opcional»; el paso ahora
    # empieza por la residencia. Aprobado por Daniel el 23-sep.

    _render_residencia_fiscal()

    tiene_1042s = st.session_state.get("_wizard_1042s") is not None
    tiene_income = st.session_state.get("_wizard_income_summary") is not None

    if tiene_1042s or tiene_income:
        if tiene_1042s:
            _render_1042s_resumen()
        if tiene_income:
            _render_income_resumen()
        return

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

    # Etiqueta del desplegable — literal de la referencia (§3A.5: «Añadir documentos»
    # + micro «1042-S / Investment Income»). Aprobada por Daniel el 23-sep.
    with st.expander("Añadir documentos · 1042-S / Investment Income", expanded=False):
        _render_1042s_uploader()
        _render_income_uploader()


_ANEXO = "## Anexo"


def _privacy_visible(texto: str) -> str:
    """Lo que ve el cliente en el paso de carga.

    Recorta la VISTA, no el documento: `PRIVACY.md` sigue siendo la fuente única y
    completa. Fuera quedan el título del documento (el expander ya tiene el suyo),
    la línea de fecha y el anexo técnico, que describe un mecanismo desactivado.
    """
    cuerpo = texto.split(_ANEXO)[0]
    lineas = []
    for linea in cuerpo.splitlines():
        s = linea.strip()
        if not lineas and (s.startswith("# ") or s.startswith("*Actualizado:") or not s):
            continue
        lineas.append(linea)
    return "\n".join(lineas).strip()


def _resultados_para_cobertura() -> dict:
    """Resultados que lee la dona de cobertura, SIN disparar `analyze_portfolio` antes
    de confirmar posiciones (spec U4 §4.3, decisión de Daniel del 18-sep).

    Antes de confirmar, `analyze_portfolio` no ha corrido — `ui/vistas.py::_resultados`
    lo calcula perezosamente y `ui/carga.py` borra `_vd_resultados` justo al confirmar—:
    la dona lee solo el caché si existiera (normalmente `None` → los 5 segmentos van
    pendientes). Llamar a `obtener_resultados()` aquí sería una llamada de red de varios
    segundos en mitad de un formulario. Después de confirmar, la dona SÍ lee el caché
    vía `obtener_resultados` — importación DENTRO de la función: `ui.vistas` ya importa
    `ui.componentes`, y una importación a nivel de módulo crea un ciclo y rompe la app
    (mismo patrón que `ui/impuestos.py` y `ui/heredadas.py`).
    """
    if st.session_state.get("_wizard_pos_confirmed") is True:
        from ui.vistas import obtener_resultados
        return obtener_resultados()
    return st.session_state.get("_vd_resultados") or {}


def _render_cobertura() -> None:
    """La dona de 5 segmentos (U4 · integrada v2): arriba del flujo de carga, debajo del
    wordmark. Mide verificación REAL — los estados salen de `ui.adapters.cobertura_data`,
    el componente no calcula nada (Regla 3)."""
    tema = st.session_state.get("vd_tema", "Claro")
    componentes.render_cobertura(
        adapters.cobertura_data(_resultados_para_cobertura()), tema)


def _capturar_caso() -> None:
    """F2 §4.2 — captura el caso anónimo si el cliente dio consentimiento.

    Se llama UNA vez, en el handler de «Ver resultados →», cuando ya hay posiciones
    confirmadas y (si el cliente lo subió) 1042-S. Nunca propaga excepciones: un fallo
    de la captura no puede interrumpir el análisis del cliente.

    El consentimiento se lee del widget `_consent_capture` si existe en el run, y si no
    de la instantánea `_captura_consent` que toma «Confirmar posiciones». La instantánea
    es necesaria porque Streamlit purga las claves de widget que no se instancian en el
    run (MEDIDO 2026-09-25: al confirmar, la casilla deja de dibujarse y su clave
    desaparece de la sesión antes de que exista el botón «Ver resultados»).
    """
    try:
        if (st.session_state.get("_consent_capture") is not True
                and st.session_state.get("_captura_consent") is not True):
            return
        if not storage.is_enabled():
            return
        df_clean = st.session_state.get("_wizard_df_clean")
        if df_clean is None:
            return

        # Importación DENTRO de la función (mismo patrón que `_resultados_para_cobertura`):
        # `ui.vistas` importa `ui.componentes` y a nivel de módulo crearía un ciclo.
        from ui.vistas import obtener_resultados
        resultados = obtener_resultados()
        quality_map = logic.assess_data_quality(
            resultados, logic.classify_tickers(list(resultados)))

        tasa, pais = estado.tasa_y_pais()

        # Señales para el harness — cada una en su propio try: si fallan, lista vacía
        # y la captura sigue (spec §4.2.4).
        try:
            datos = adapters.metodo_real_data(resultados, df_clean, tasa, pais)
            bloqueos = [e["t"] for e in (datos or {}).get("excluidos", [])]
        except Exception:                                       # noqa: BLE001
            bloqueos = []
        try:
            indeterminados = adapters._ganancias_capital_cartera(
                resultados)["tickers_indeterminados"]
        except Exception:                                       # noqa: BLE001
            indeterminados = []

        # NO se pasa `_wizard_csv_name` ni nada derivado del nombre del archivo:
        # `build_capture_bundle` no tiene ese parámetro a propósito (el nombre del CSV
        # de IB lleva el número de cuenta).
        bundle = logic.build_capture_bundle(
            df_clean,
            st.session_state.get("_wizard_broker", "generic"),
            st.session_state.get("_wizard_positions") or {},
            quality_map,
            gemini_raw=st.session_state.get("_wizard_ocr_positions"),
            origen=st.session_state.get("_captura_origen"),
            form_1042s=st.session_state.get("_wizard_1042s"),
            pais=pais,
            bloqueos=bloqueos,
            indeterminados=indeterminados,
        )

        # Un caso por sesión (spec §4.2.5): si ya hay id, se reutiliza y el backend
        # sobrescribe la misma carpeta.
        previo = st.session_state.get("_captura_case_id")
        if previo:
            bundle["case_id"] = previo
            bundle["meta"]["case_id"] = previo

        nuevo = storage.upload_case(bundle)
        if nuevo:
            st.session_state["_captura_case_id"] = nuevo
    except Exception:                                           # noqa: BLE001
        pass


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

    # La dona de cobertura va ARRIBA de los tres bloques (integrada v2: antes vivía al
    # final; ver spec U4 §5.1.4 y referencia-carga-cobertura-integrada-v2.html).
    _render_cobertura()

    with st.expander("Cómo tratamos tus datos"):
        ruta_privacy = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "PRIVACY.md")
        with open(ruta_privacy, encoding="utf-8") as f:
            st.markdown(_privacy_visible(f.read()))

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
        # F2 §4.2: la captura del caso (si hay consentimiento) ocurre AQUÍ, una sola
        # vez por sesión, justo antes de pasar a resultados — no en cada render.
        _capturar_caso()
        st.session_state["_wizard_listo"] = True
        st.rerun()

    return bool(st.session_state.get("_wizard_listo"))


ESTILOS_CARGA = """
        /* Fila 34 — animación de revelación progresiva, copiada literal de
           `.da-reveal`/`@keyframes da-rev` en `app_old.py:1314-1319` (mismo timing y easing,
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
"""
