"""Tests de UI del Bloque 3 (Formulario 1042-S) en `ui/carga.py`, con
`streamlit.testing.v1.AppTest`.

Bloque 3 es OPCIONAL: nunca gatea el paso a resultados (Bloque 2 confirmado ya
basta). El motor (parse_1042s_pdf / extract_1042s / build_1042s_validation) vive
en `logic.py` y ya tiene sus propios tests en `test_1042s.py`; aquí solo se
prueba el cableado de la interfaz.
"""
import os
import sys

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, os.path.dirname(__file__))
import logic


_SCRIPT = """
import sys
sys.path.insert(0, {path!r})
from ui.carga import render_carga

render_carga()
""".format(path=os.path.dirname(os.path.abspath(__file__)))


def _df_schwab():
    """CSV sintético del fixture (misma ruta que usa el modo demo de `app_v2.py`),
    normalizado como llega a `_wizard_df_clean` tras el Bloque 1."""
    ruta = os.path.join(os.path.dirname(__file__),
                         "fixtures", "schwab_synth_1", "synthetic_transactions.csv")
    return logic.normalize_csv(pd.read_csv(ruta))


def _at_con_posiciones_confirmadas(broker="schwab"):
    """AppTest con Bloque 1 y Bloque 2 ya resueltos, listo para ejercitar el Bloque 3."""
    limpio = _df_schwab()
    at = AppTest.from_string(_SCRIPT)
    at.session_state["_wizard_df_clean"] = limpio
    at.session_state["_wizard_csv_ticker_data"] = {}
    at.session_state["_wizard_broker"] = broker
    at.session_state["_wizard_csv_name"] = "synthetic_transactions.csv"
    at.session_state["_wizard_positions"] = {"MSTY": {"shares": 40.0, "cost_basis": 1000.0}}
    at.session_state["_wizard_pos_confirmed"] = True
    return at


def _tiene_uploader_pdf(at) -> bool:
    return any(w.key == "_vd_upload_1042s" for w in at.get("file_uploader"))


# ── a) bloqueado sin CSV ─────────────────────────────────────────────────────

def test_bloque3_bloqueado_sin_csv():
    at = AppTest.from_string(_SCRIPT)
    at.run()
    assert at.exception == []
    texto = "\n".join(m.value for m in at.markdown)
    assert "Formulario 1042-S" in texto
    assert not _tiene_uploader_pdf(at)


# ── b) IBKR sin uploader ─────────────────────────────────────────────────────

def test_bloque3_ibkr_sin_uploader():
    at = _at_con_posiciones_confirmadas(broker="ibkr")
    at.run()
    assert at.exception == []
    texto = "\n".join(m.value for m in at.markdown)
    assert "Interactive Brokers ya incluye el detalle fiscal" in texto
    assert not _tiene_uploader_pdf(at)


# ── c) resumen tras leer ─────────────────────────────────────────────────────

def test_bloque3_resumen_tras_leer():
    at = _at_con_posiciones_confirmadas(broker="schwab")
    at.session_state["_wizard_1042s"] = {
        "tax_year": 2025,
        "source": "pdfplumber",
        "forms": [
            {"unique_form_id": "2025417492", "income_code": "01",
             "gross_income": 1.0, "federal_tax_withheld": 0.0,
             "withholding_credit": 0.0, "conflict": False},
            {"unique_form_id": "2025417493", "income_code": "06",
             "gross_income": 28.0, "federal_tax_withheld": 8.0,
             "withholding_credit": 8.0, "conflict": False},
            {"unique_form_id": "2025417494", "income_code": "37",
             "gross_income": 276.0, "federal_tax_withheld": 83.0,
             "withholding_credit": 83.0, "conflict": False},
        ],
    }
    at.run()
    assert at.exception == []
    texto = "\n".join(m.value for m in at.markdown)
    assert "1042-S leído" in texto
    assert "$83.00" in texto
    assert not _tiene_uploader_pdf(at)


def test_bloque3_credito_con_codigo_no_normalizado():
    """El camino de Gemini pasa el `income_code` crudo: puede llegar como entero 37.
    Comparado contra la cadena "37" el crédito ROC se mostraba como $0."""
    at = _at_con_posiciones_confirmadas(broker="schwab")
    at.session_state["_wizard_1042s"] = {
        "tax_year": 2025,
        "source": "gemini",
        "forms": [
            {"unique_form_id": "2025417493", "income_code": 6, "gross_income": 28.0,
             "federal_tax_withheld": 8.0, "withholding_credit": 8.0, "conflict": False},
            {"unique_form_id": "2025417494", "income_code": 37, "gross_income": 276.0,
             "federal_tax_withheld": 83.0, "withholding_credit": 83.0, "conflict": False},
        ],
    }
    at.run()
    assert at.exception == []
    texto = "\n".join(m.value for m in at.markdown)
    assert "$83.00" in texto


# ── e) sin cobertura: el fallo de lectura ────────────────────────────────────
#
# `_wizard_1042s_error` persiste el fallo en sesión porque la guarda por firma corta antes
# de releer el mismo archivo: sin persistirlo, el mensaje se pintaba una vez y desaparecía
# en el primer rerun, dejando al usuario con su PDF adjunto, sin error y sin resultado.
#
# NO hay test de esto. El estado solo es alcanzable con un archivo adjunto al uploader, y
# `AppTest` no puede adjuntar ficheros; un test que precargue el flag sin archivo estaría
# afirmando lo contrario de lo correcto (sin archivo NO debe verse error). Verificado a
# mano en el navegador. Si algún día el arnés puede adjuntar, este es el caso a cubrir.


# ── d) no gatea resultados ───────────────────────────────────────────────────

def test_bloque3_no_gatea_resultados():
    at = _at_con_posiciones_confirmadas(broker="schwab")
    at.run()
    assert at.exception == []
    claves = [b.key for b in at.button]
    assert "_vd_ir_resultados" in claves
    boton = next(b for b in at.button if b.key == "_vd_ir_resultados")
    assert not boton.disabled
