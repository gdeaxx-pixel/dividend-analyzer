"""Tests de UI de privacidad (F2, F4): `streamlit.testing.v1.AppTest` sobre `ui/carga.py`
y guards de contenido sobre `PRIVACY.md`.
"""
import os
import sys

import pandas as pd
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
