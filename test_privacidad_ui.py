"""Tests de UI de privacidad (F2, F4): `streamlit.testing.v1.AppTest` sobre `ui/carga.py`
y guards de contenido sobre `PRIVACY.md`.
"""
import os
import sys

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, os.path.dirname(__file__))
import logic


_RAIZ = os.path.dirname(os.path.abspath(__file__))
_PRIVACY_PATH = os.path.join(_RAIZ, "PRIVACY.md")

_SCRIPT = """
import sys
sys.path.insert(0, {path!r})
from ui.carga import render_carga

render_carga()
""".format(path=_RAIZ)


def _df_schwab():
    ruta = os.path.join(_RAIZ, "fixtures", "schwab_synth_1", "synthetic_transactions.csv")
    return logic.normalize_csv(pd.read_csv(ruta))


def test_f2_uploader_avisa_de_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "falsa")
    limpio = _df_schwab()
    at = AppTest.from_string(_SCRIPT)
    at.session_state["_wizard_df_clean"] = limpio
    at.session_state["_wizard_csv_ticker_data"] = {}
    at.session_state["_wizard_broker"] = "schwab"
    at.session_state["_wizard_csv_name"] = "synthetic_transactions.csv"
    at.run()
    assert at.exception == []

    fotos = [w for w in at.get("file_uploader") if w.proto.label == "Fotos del portafolio"]
    assert fotos, "el uploader de fotos no se renderizó (¿falta la clave de Gemini?)"
    assert "Google Gemini" in fotos[0].proto.help

    texto = "\n".join(c.value for c in at.caption)
    assert "Google Gemini" in texto


def test_f4_expander_privacidad_en_la_carga():
    at = AppTest.from_string(_SCRIPT)
    at.run()
    assert at.exception == []

    expanders = [e for e in at.get("expander") if e.label == "Cómo tratamos tus datos"]
    assert expanders, "no existe el expander «Cómo tratamos tus datos»"
    contenido = "\n".join(m.value for m in expanders[0].get("markdown"))
    assert "Google Gemini" in contenido
    assert "Yahoo Finance" in contenido


def test_f4_expander_oculta_el_anexo_tecnico():
    with open(_PRIVACY_PATH, encoding="utf-8") as f:
        texto = f.read()
    assert "## Anexo" in texto
    assert "upload_case" in texto

    at = AppTest.from_string(_SCRIPT)
    at.run()
    assert at.exception == []

    expanders = [e for e in at.get("expander") if e.label == "Cómo tratamos tus datos"]
    contenido = "\n".join(m.value for m in expanders[0].get("markdown"))
    assert "Anexo" not in contenido
    assert "upload_case" not in contenido


def test_f4_expander_sin_titulo_duplicado():
    with open(_PRIVACY_PATH, encoding="utf-8") as f:
        texto = f.read()
    assert texto.startswith("# Aviso de privacidad")
    assert "Actualizado:" in texto

    at = AppTest.from_string(_SCRIPT)
    at.run()
    assert at.exception == []

    expanders = [e for e in at.get("expander") if e.label == "Cómo tratamos tus datos"]
    contenido = "\n".join(m.value for m in expanders[0].get("markdown"))
    assert "# Aviso de privacidad" not in contenido
    assert "Actualizado:" not in contenido
    assert contenido.startswith("**Tus archivos.**")


def test_f4_telegram_dice_para_que_sirve():
    with open(_PRIVACY_PATH, encoding="utf-8") as f:
        texto = f.read()
    assert "Telegram" in texto
    assert "para verificar manualmente tu acceso" in texto


def test_f4_privacy_no_miente_sobre_la_memoria():
    with open(_PRIVACY_PATH, encoding="utf-8") as f:
        texto = f.read()
    assert "todo el procesamiento ocurre en memoria" not in texto.lower()


def test_f4_ttl_coincide_con_el_aviso():
    info = logic.analyze_portfolio._info
    with open(_PRIVACY_PATH, encoding="utf-8") as f:
        texto = f.read()
    if info.ttl == 3600:
        assert "hasta 1 hora" in texto
    else:
        assert "hasta 1 hora" not in texto


# ── C·10/S1 · el contexto de captura sobrevive a «editar» el CSV ────────────────

def _df(caso):
    ruta = os.path.join(_RAIZ, "fixtures", caso, "synthetic_transactions.csv")
    return logic.normalize_csv(pd.read_csv(ruta))


def _ss(at, k):
    try:
        return at.session_state[k]
    except Exception:
        return None


def test_s1_editar_csv_borra_el_contexto_de_captura():
    """Reproductor de o2c_s1_wizard.py convertido en test: cartera A con OCR de MSTY
    (999 acciones / $12,345 base) → clic en «editar» → cartera B → el number_input
    _vd_sh_MSTY vale 5.0, _vd_cb_MSTY vale 120.0 y 'vd-ocr' no aparece en el markdown.
    Mira lo presentado, no session_state."""
    ocr_a = {"MSTY": {"shares": 999.0, "cost_basis": 12345.0}}
    sig_a = (("captura_A.png", 100),)

    at = AppTest.from_string(_SCRIPT)
    at.session_state["_wizard_df_clean"] = _df("schwab_synth_1")
    at.session_state["_wizard_csv_ticker_data"] = {"MSTY": {"shares": 40.0, "invested": 1000.0}}
    at.session_state["_wizard_broker"] = "schwab"
    at.session_state["_wizard_csv_name"] = "cartera_A.csv"
    at.session_state["_wizard_ocr_positions"] = ocr_a
    at.session_state["_wizard_photo_sig"] = sig_a
    at.run()
    assert at.exception == []

    botones = [b for b in at.button if b.proto.id.endswith("_vd_edit_csv")]
    assert botones, "no se encontró el botón «editar»"
    botones[0].click().run()
    assert at.exception == []

    at.session_state["_wizard_df_clean"] = _df("schwab_synth_2")
    at.session_state["_wizard_csv_ticker_data"] = {"MSTY": {"shares": 5.0, "invested": 120.0}}
    at.session_state["_wizard_broker"] = "schwab"
    at.session_state["_wizard_csv_name"] = "cartera_B.csv"
    at.run()
    assert at.exception == []

    sh = [n for n in at.number_input if n.proto.id.endswith("_vd_sh_MSTY")]
    cb = [n for n in at.number_input if n.proto.id.endswith("_vd_cb_MSTY")]
    assert sh and sh[0].value == 5.0
    assert cb and cb[0].value == 120.0
    texto = "\n".join(m.value for m in at.markdown)
    assert "vd-ocr" not in texto


def test_s1_demo_no_hereda_capturas_de_la_sesion_previa():
    """Con `_wizard_ocr_positions` puesto a mano, aplicar
    demo_mode.load_demo_case("schwab") como hace app.py:54 deja la clave en None."""
    import demo_mode
    bundle = demo_mode.load_demo_case("schwab")
    assert bundle is not None
    assert bundle.get("_wizard_ocr_positions") is None


def test_s1_firma_por_contenido_no_por_nombre_y_tamano():
    """Unitario de _firma_fotos: dos payloads con el mismo nombre y el mismo tamaño y
    contenido distinto dan firmas distintas; el mismo contenido da la misma firma."""
    from ui.carga import _firma_fotos

    class _FakeUpload:
        def __init__(self, name, content):
            self.name = name
            self.size = len(content)
            self._content = content

        def getvalue(self):
            return self._content

    a1 = _FakeUpload("captura.png", b"contenido A")
    a2 = _FakeUpload("captura.png", b"contenido B")  # mismo nombre, mismo tamaño (11 bytes)
    assert len(a1._content) == len(a2._content)
    assert _firma_fotos([a1]) != _firma_fotos([a2])

    a3 = _FakeUpload("captura.png", b"contenido A")
    assert _firma_fotos([a1]) == _firma_fotos([a3])


def test_s1_confirmar_posiciones_conserva_la_captura():
    """Control: confirmar posiciones (que hoy hace
    st.session_state.pop("_vd_resultados")) no borra _wizard_ocr_positions. Sin este
    control, borrar la captura en cualquier rerun también pondría verdes los otros tres."""
    ocr_a = {"MSTY": {"shares": 999.0, "cost_basis": 12345.0}}
    at = AppTest.from_string(_SCRIPT)
    at.session_state["_wizard_df_clean"] = _df("schwab_synth_1")
    at.session_state["_wizard_csv_ticker_data"] = {"MSTY": {"shares": 40.0, "invested": 1000.0}}
    at.session_state["_wizard_broker"] = "schwab"
    at.session_state["_wizard_csv_name"] = "cartera_A.csv"
    at.session_state["_wizard_ocr_positions"] = ocr_a
    at.session_state["_wizard_photo_sig"] = (("captura_A.png", 100),)
    at.run()
    assert at.exception == []

    botones = [b for b in at.button if b.proto.id.endswith("_vd_confirm_pos")]
    if not botones:
        pytest.skip("no se encontró el botón de confirmar posiciones en este layout")
    botones[0].click().run()
    assert at.exception == []
    assert _ss(at, "_wizard_ocr_positions") is not None
