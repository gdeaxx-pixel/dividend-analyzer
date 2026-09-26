"""F2 §5 — La casilla de consentimiento de captura y la llamada en el flujo.

`streamlit.testing.v1.AppTest` sobre `ui.carga.render_carga` (y `ui.pie.render_pie`
para el código del caso). Mercado mockeado con `_MKT_MOCK` del repo (devuelve la
tupla `(df, None)`); CSV sintético de 2 ETFs con cifras redondas inventadas,
construido en este archivo; backend local apuntado a `tmp_path`.

DESVÍO DECLARADO (medido 2026-09-25, experimento AppTest): Streamlit PURGA las
claves de widget que no se instancian en el run — al confirmar posiciones la
casilla deja de dibujarse y `_consent_capture` desaparece de la sesión ANTES de
que exista el botón «Ver resultados». Por eso «Confirmar posiciones» toma una
instantánea `_captura_consent` y `_capturar_caso` lee el widget si existe y si no
la instantánea. Sin ella la captura NUNCA ocurriría en el flujo real.

Los esperados están escritos a mano; nunca se calculan con la función probada.
"""
import io
import json
import os
import sys

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, os.path.dirname(__file__))
import logic
import storage
from test_logic import _MKT_MOCK

BASE = os.path.dirname(os.path.abspath(__file__))

# ── Datos sintéticos (cifras redondas inventadas) ────────────────────────────

_CSV = (
    '"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"\n'
    '"01/15/2025","Buy","MSTY","ETF SINTETICO A","40","$25.00","","-$1000.00"\n'
    '"01/15/2025","Buy","SCHB","ETF SINTETICO B","10","$20.00","","-$200.00"\n'
    '"03/01/2025","Cash Dividend","MSTY","ETF SINTETICO A","","","","$50.00"\n'
)

# Vista previa escrita A MANO (compras del CSV: 40×MSTY $1000, 10×SCHB $200):
# es el defecto de los number_input del paso 2 y la referencia de `origen_posiciones`.
_PREVIA = {
    "MSTY": {"shares": 40.0, "invested": 1000.0},
    "SCHB": {"shares": 10.0, "invested": 200.0},
}

_ARCHIVOS_CASO = ("transactions_min.csv", "ground_truth.json", "quality.json",
                  "gemini_raw.json", "meta.json")

# Textos aprobados (Daniel, 2026-09-25) — LITERALES, copiados de la spec §4.1.
_ETIQUETA = "Ayúdanos a mejorar la calculadora con tu caso"
_AYUDA = (
    "Guardamos una copia de tus movimientos sin nombre, correo ni número de cuenta "
    "(fecha, ticker, cantidad, precio, importe) y las posiciones que confirmas, para "
    "comprobar que la calculadora sigue acertando con casos reales. No entrena ninguna IA. "
    "Se borra a los 90 días salvo que lo convirtamos en caso de prueba; puedes pedir que "
    "lo borremos cuando quieras. Opcional: sin marcarla la app funciona igual."
)
_GUARDAMOS = (
    "Sí: fechas, tipo de movimiento, ticker, cantidad, precio, importe; acciones y costo "
    "que confirmas; totales leídos del 1042-S. No: el archivo original, el nombre del "
    "archivo, tus capturas, el PDF, tu correo, tu nombre, tu número de cuenta ni tu IP."
)

_VARS_B2 = ("CAPTURE_B2_BUCKET", "CAPTURE_B2_ENDPOINT", "CAPTURE_B2_KEY_ID",
            "CAPTURE_B2_APP_KEY", "CAPTURE_B2_PREFIX")

# ── Scripts de AppTest ───────────────────────────────────────────────────────

_SCRIPT_CARGA = """
import sys
sys.path.insert(0, {path!r})
from ui.carga import render_carga

render_carga()
""".format(path=BASE)

_SCRIPT_CON_PIE = """
import sys
sys.path.insert(0, {path!r})
import streamlit as st
from ui.carga import render_carga

listo = render_carga()
if listo:
    from ui.pie import render_pie
    render_pie(st.session_state.get("_vd_resultados") or {{"sin_datos": True}})
""".format(path=BASE)


def _df():
    """CSV sintético normalizado, como llega a `_wizard_df_clean` tras el Bloque 1."""
    return logic.normalize_csv(pd.read_csv(io.StringIO(_CSV)))


def _at(script=_SCRIPT_CARGA, timeout=40):
    return AppTest.from_string(script, default_timeout=timeout)


def _seed(at, csv_name="transacciones_sinteticas.csv"):
    at.session_state["_wizard_df_clean"] = _df()
    at.session_state["_wizard_csv_ticker_data"] = dict(_PREVIA)
    at.session_state["_wizard_broker"] = "schwab"
    at.session_state["_wizard_csv_name"] = csv_name


def _wid(lista, sufijo):
    """Elemento de AppTest por sufijo de `proto.id` (patrón probado en
    `test_privacidad_ui.py`: `.key` no es fiable en todos los widgets)."""
    encontrados = [w for w in lista if w.proto.id.endswith(sufijo)]
    assert encontrados, f"ningún widget con id terminado en {sufijo!r}"
    return encontrados[0]


def _ss(at, clave):
    """Lectura segura de session_state: el proxy lanza KeyError en vez de devolver
    None (patrón `test_carga_cobertura.py::_ss`)."""
    try:
        return at.session_state[clave]
    except Exception:
        return None


def _casos(disco):
    """Carpetas de caso bajo <local>/captured/<broker>/ — rutas absolutas, una por caso."""
    raiz = os.path.join(str(disco), "captured")
    if not os.path.isdir(raiz):
        return []
    casos = []
    for broker in os.listdir(raiz):
        bdir = os.path.join(raiz, broker)
        if not os.path.isdir(bdir):
            continue
        for cid in os.listdir(bdir):
            cdir = os.path.join(bdir, cid)
            if os.path.isdir(cdir):
                casos.append(cdir)
    return sorted(casos)


# ── Quirk de AppTest: fantasmas de widget tras un st.rerun() de handler ──────
#
# MEDIDO 2026-09-25: cuando un handler hace `st.rerun()` (Confirmar posiciones,
# Ver resultados), el árbol de AppTest queda con la UNION de los dos pases del
# script: los number_input del formulario (pase 1) sobreviven como nodos
# «fantasma» cuyos valores de sesión Streamlit ya purgó (la rama confirmada no
# los instancia). El siguiente `at.run()` itera el árbol para enviar
# `get_widget_states()` y muere con `KeyError: '_vd_cb_MSTY'`.
# Solución: snapshot de valores ANTES del clic y, tras el run, PINEAR los
# fantasmas con `set_value` (API pública) para que su `.value` no consulte la
# sesión. Los botones no necesitan pin (su valor no vive en sesión).

def _snapshot_widgets(at):
    vals = {}
    for w in list(at.number_input) + list(at.checkbox) + list(at.selectbox):
        try:
            vals[w.proto.id] = w.value
        except Exception:                                  # fantasma ya purgado
            pass
    return vals


def _pinear(at, vals):
    for w in list(at.number_input) + list(at.checkbox) + list(at.selectbox):
        if w.proto.id in vals:
            w.set_value(vals[w.proto.id])


def _run(at):
    """at.run() a prueba de fantasmas: snapshot → run → pin."""
    vals = _snapshot_widgets(at)
    at.run()
    _pinear(at, vals)
    return at


def _marcar(at):
    _wid(at.checkbox, "_consent_capture").check()


def _confirmar(at):
    _wid(at.button, "_vd_confirm_pos").click()
    _run(at)


def _ver_resultados(at):
    _wid(at.button, "_vd_ir_resultados").click()
    _run(at)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _mercado_plano(monkeypatch):
    """Sin red: `fetch_market_data` mockeado con el `_MKT_MOCK` del repo (tupla)."""
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)


@pytest.fixture
def sin_backend(monkeypatch):
    for var in ("CAPTURE_LOCAL_DIR", *_VARS_B2):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def con_backend(monkeypatch, tmp_path):
    """Backend local apuntado a tmp_path (spec §1); sin variables B2 que se cuelen."""
    for var in _VARS_B2:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CAPTURE_LOCAL_DIR", str(tmp_path))
    return tmp_path


# ── T1 · sin backend, pantalla idéntica ──────────────────────────────────────

def test_sin_backend_no_hay_casilla(sin_backend):
    at = _at()
    _seed(at)
    at.run()
    assert at.exception == []
    # El paso 2 SÍ se dibujó (si no, el test sería vacuo):
    _wid(at.button, "_vd_confirm_pos")
    assert [c for c in at.checkbox if c.proto.id.endswith("_consent_capture")] == []
    assert all(_ETIQUETA not in (c.label or "") for c in at.checkbox)


# ── T2 · casilla desmarcada por defecto ──────────────────────────────────────

def test_con_backend_la_casilla_existe_y_empieza_desmarcada(con_backend):
    at = _at()
    _seed(at)
    at.run()
    assert at.exception == []
    cb = _wid(at.checkbox, "_consent_capture")
    assert cb.value is False                      # NUNCA value=True
    assert cb.label == _ETIQUETA                  # texto literal aprobado
    assert _GUARDAMOS in [c.value for c in at.caption]   # el desplegable existe


# ── T3 · sin marcar no guarda ────────────────────────────────────────────────

def test_sin_marcar_no_se_guarda_nada(con_backend):
    at = _at()
    _seed(at)
    at.run()
    _wid(at.checkbox, "_consent_capture")         # backend activo (no vacuo)
    _confirmar(at)
    _ver_resultados(at)
    assert at.exception == []
    assert _ss(at, "_captura_case_id") is None
    assert _casos(con_backend) == []


# ── T4 · marcada guarda UNO (y solo uno tras 3 reruns) ──────────────────────

def test_marcada_guarda_un_solo_caso(con_backend):
    at = _at()
    _seed(at)
    at.run()
    # Render del formulario: todavía NO se captura nada (la captura vive en el
    # botón «Ver resultados →», no en cada render — M7).
    assert _casos(con_backend) == []
    _marcar(at)
    _confirmar(at)
    # Confirmar tampoco captura: el botón aún no se ha pulsado.
    assert _casos(con_backend) == []
    _ver_resultados(at)
    for _ in range(3):                            # reruns extra: rail, tema, etc.
        _run(at)
    assert at.exception == []
    casos = _casos(con_backend)
    assert len(casos) == 1, casos
    assert os.path.basename(os.path.dirname(casos[0])) == "schwab"
    assert sorted(os.listdir(casos[0])) == sorted(_ARCHIVOS_CASO)
    # 3 reruns más con el caso ya capturado no crean carpetas nuevas.
    assert len(_casos(con_backend)) == 1


# ── T5 · el fallo de la captura no rompe el análisis ────────────────────────

def test_un_fallo_de_subida_no_rompe_los_resultados(con_backend, monkeypatch):
    def boom(bundle):
        raise RuntimeError("fallo simulado de backend")

    monkeypatch.setattr(storage, "upload_case", boom)
    at = _at()
    _seed(at)
    at.run()
    _marcar(at)
    _confirmar(at)
    _ver_resultados(at)
    assert at.exception == []                     # la vista de resultados se pinta
    assert _ss(at, "_wizard_listo") is True       # el flujo siguió
    assert _ss(at, "_captura_case_id") is None


# ── T6 · el nombre del archivo no viaja ─────────────────────────────────────

def test_el_nombre_del_csv_no_aparece_en_el_caso(con_backend):
    nombre = "U15179613.TRANSACTIONS.20240820.csv"   # el nombre real de IB lleva la cuenta
    at = _at()
    _seed(at, csv_name=nombre)
    at.run()
    _marcar(at)
    _confirmar(at)
    _ver_resultados(at)
    assert at.exception == []
    casos = _casos(con_backend)
    assert len(casos) == 1, "sin carpeta no hay nada que auditar"
    for ruta, _dirs, archivos in os.walk(casos[0]):
        for archivo in archivos:
            with open(os.path.join(ruta, archivo), encoding="utf-8") as f:
                contenido = f.read()
            assert "U15179613" not in contenido, archivo
            assert "TRANSACTIONS" not in contenido, archivo
        for parte in os.path.basename(ruta).split("/"):
            assert "U15179613" not in parte and "TRANSACTIONS" not in parte


# ── T7 · origen por ticker (editado vs vista_previa) ────────────────────────

def test_el_origen_distingue_editado_de_vista_previa(con_backend):
    at = _at()
    _seed(at)
    at.run()
    _marcar(at)
    # El cliente EDITA las acciones de MSTY (40 → 41) y DEJA las de SCHB (10):
    _wid(at.number_input, "_vd_sh_MSTY").set_value(41.0)
    _confirmar(at)
    _ver_resultados(at)
    assert at.exception == []
    casos = _casos(con_backend)
    assert len(casos) == 1
    with open(os.path.join(casos[0], "ground_truth.json"), encoding="utf-8") as f:
        gt = json.load(f)
    # Esperados escritos A MANO: 41 ≠ 40 (defecto) → editado; 10 == 10 → vista_previa.
    assert gt["MSTY"]["origen_shares"] == "editado"
    assert gt["SCHB"]["origen_shares"] == "vista_previa"
    assert gt["MSTY"]["shares"] == 41.0
    assert gt["SCHB"]["shares"] == 10.0


# ── T8 · el código del caso se muestra en el pie ────────────────────────────

def test_el_pie_muestra_el_codigo_del_caso_que_existe_en_disco(con_backend):
    at = _at(script=_SCRIPT_CON_PIE)
    _seed(at)
    at.run()
    _marcar(at)
    _confirmar(at)
    _ver_resultados(at)
    at.run()                                      # render de resultados con el pie
    assert at.exception == []
    cid = _ss(at, "_captura_case_id")
    assert cid, "no se capturó ningún caso"
    esperada = (f"Gracias. Código de tu caso: {cid}. "
                "Guárdalo si algún día quieres que lo borremos.")
    avisos = [c.value for c in at.caption if "Código de tu caso" in c.value]
    assert avisos == [esperada]                   # exactamente una vez por render
    assert os.path.isdir(os.path.join(str(con_backend), "captured", "schwab", cid))


# ── T9 · editar el paso 2 y volver: mismo caso, una carpeta ─────────────────

def test_editar_paso2_y_volver_reutiliza_el_mismo_caso(con_backend):
    at = _at()
    _seed(at)
    at.run()
    _marcar(at)
    _confirmar(at)
    _ver_resultados(at)
    cid_1 = _ss(at, "_captura_case_id")
    assert cid_1 and len(_casos(con_backend)) == 1

    # «editar» del paso 2 → vuelve el formulario con la casilla SIN marcar (Streamlit
    # purgó el widget): el cliente la vuelve a marcar y re-confirma (mismo caso).
    _wid(at.button, "_vd_edit_pos").click()
    at.run()
    _marcar(at)
    _confirmar(at)
    _ver_resultados(at)
    assert at.exception == []
    cid_2 = _ss(at, "_captura_case_id")
    assert cid_2 == cid_1, f"el caso cambió de id: {cid_1} → {cid_2}"
    assert len(_casos(con_backend)) == 1, _casos(con_backend)


# ── T10 · texto aprobado, con el 90 de la constante ─────────────────────────

def test_el_texto_de_la_casilla_es_el_aprobado(con_backend):
    from ui.carga import CAPTURA_RETENCION_DIAS

    assert CAPTURA_RETENCION_DIAS == 90           # escrito a mano (spec §4.1)

    at = _at()
    _seed(at)
    at.run()
    cb = _wid(at.checkbox, "_consent_capture")
    assert cb.label == _ETIQUETA
    ayuda = cb.proto.help
    assert "No entrena ninguna IA" in ayuda
    assert "90 días" in ayuda
    # El texto pintado ES el literal aprobado, transcrito a mano en este archivo:
    # si alguien reescribe la constante de ui/carga.py, esta comparación cae.
    assert ayuda == _AYUDA
    # Y el «90» del texto sale de la constante (f-string dentro de ella):
    from ui.carga import _AYUDA_CAPTURA
    assert _AYUDA_CAPTURA.replace(f"{CAPTURA_RETENCION_DIAS} días", "N días") != _AYUDA_CAPTURA
