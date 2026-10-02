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
    """CSV sintético del fixture (misma ruta que usa el modo demo de `app.py`),
    normalizado como llega a `_wizard_df_clean` tras el Bloque 1."""
    ruta = os.path.join(os.path.dirname(__file__),
                         "fixtures", "schwab_synth_1", "synthetic_transactions.csv")
    return logic.normalize_csv(pd.read_csv(ruta))


def _at_con_posiciones_confirmadas(broker="schwab"):
    """AppTest con Bloque 1 y Bloque 2 ya resueltos, listo para ejercitar el Bloque 3.

    `default_timeout=25`: con posiciones confirmadas, la dona de cobertura (U4) lee los
    resultados vía `obtener_resultados`, que dispara `analyze_portfolio` (~2.5 s la
    primera vez en el proceso; después pega el caché). El timeout por defecto (3 s) se
    queda corto y el fallo sale como `RuntimeError: AppTest timed out`."""
    limpio = _df_schwab()
    at = AppTest.from_string(_SCRIPT, default_timeout=25)
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
    """Un `income_code` que llega como entero 37 (así lo devolvía el lector de Gemini,
    retirado el 2026-09-18) no puede dejar el crédito ROC en $0: la normalización se
    conserva como defensa."""
    at = _at_con_posiciones_confirmadas(broker="schwab")
    at.session_state["_wizard_1042s"] = {
        "tax_year": 2025,
        "source": "pdfplumber",
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


# ── f) «Usar <país>» del 1042-S y el selector de residencia ──────────────────
#
# Bug medido el 2026-10-02 con un 1042-S real (casilla 13b = CO): pulsar «Usar Colombia»
# no cambiaba nada. El botón declaraba el país y hacía `st.rerun()`, pero el `selectbox`
# con `key` conservaba «sin declarar» e `index=` no lo movía; la línea que declaraba en
# cada render con el valor del selector lo borraba. Elegir a mano sí funcionaba.

def _forms_1042s(codigo="CO"):
    return {"tax_year": 2025, "source": "pdfplumber", "recipient_country_code": codigo,
            "forms": [{"unique_form_id": "1", "income_code": "06", "gross_income": 28.0,
                       "federal_tax_withheld": 8.0, "withholding_credit": 8.0,
                       "conflict": False}]}


def _selector(at):
    return next(s for s in at.selectbox if "residencia fiscal" in (s.label or "").lower())


def _boton_usar(at):
    return next(b for b in at.button if b.proto.id.endswith("_vd_conf_pais_1042s"))


def test_usar_pais_del_1042s_declara_la_residencia():
    at = _at_con_posiciones_confirmadas(broker="schwab")
    at.session_state["_wizard_1042s"] = _forms_1042s("CO")
    at.run()
    assert at.exception == []
    assert _selector(at).value.startswith("—")
    _boton_usar(at).click()
    at.run()
    assert at.exception == []
    assert at.session_state["_perfil_fiscal_pais"] == "Colombia"
    assert at.session_state["_perfil_fiscal_fuente"] == "1042s"
    sel = _selector(at)
    assert sel.value == "Colombia"
    assert sel.proto.set_value, "el navegador seguiría mostrando «sin declarar»"
    assert not [b for b in at.button if b.proto.id.endswith("_vd_conf_pais_1042s")]
    at.run()                                         # y sobrevive al render siguiente
    assert at.session_state["_perfil_fiscal_pais"] == "Colombia"
    assert at.session_state["_perfil_fiscal_fuente"] == "1042s"


def test_volver_a_sin_declarar_tras_usar_el_1042s():
    at = _at_con_posiciones_confirmadas(broker="schwab")
    at.session_state["_wizard_1042s"] = _forms_1042s("CO")
    at.run()
    _boton_usar(at).click()
    at.run()
    _selector(at).select(_selector(at).options[0]).run()
    assert at.exception == []
    assert "_perfil_fiscal_pais" not in at.session_state


@pytest.mark.parametrize("via", ["selector", "boton"])
def test_el_anillo_ve_la_residencia_en_el_mismo_render(monkeypatch, via):
    """La dona se dibuja ARRIBA del selector: si el país se declarase al dibujar el
    selector, la dona de ese render leería el perfil viejo e iría un paso atrasada."""
    from ui import adapters
    vistos = []
    real = adapters.cobertura_data

    def _espia(resultados):
        datos = real(resultados)
        vistos.append(bool(__import__("ui.estado", fromlist=["x"]).perfil_fiscal()["rate_declared"]))
        return datos

    monkeypatch.setattr(adapters, "cobertura_data", _espia)
    at = _at_con_posiciones_confirmadas(broker="schwab")
    at.session_state["_wizard_1042s"] = _forms_1042s("CO")
    at.run()
    assert vistos[-1] is False
    if via == "selector":
        _selector(at).select("Colombia")
    else:
        _boton_usar(at).click()
    at.run()
    assert at.exception == []
    assert vistos[-1] is True, "la dona dibujó el perfil del render anterior"
