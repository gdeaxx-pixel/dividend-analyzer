"""Paso 2 — lo leído de la foto debe LLEGAR a los campos de acciones y costo.

Bug medido el 2026-10-02 con un CSV Schwab real + captura de posiciones: Gemini leyó bien,
pero los `number_input` con `key` fijo ya existían (vista previa del CSV) y Streamlit 1.52
ignora un `value=` nuevo en un widget con clave creada. El campo seguía mostrando la vista
previa y `origen_posiciones` lo etiquetaba `editado`.

El campo del servidor NO basta como oráculo: tras `st.rerun()` Streamlit purga los widgets que
no se instanciaron y el valor del servidor sí cambia, pero el navegador conserva su estado
local (misma id por `key`) mientras el proto no lleve `set_value=True`, y lo reenvía al
confirmar. AppTest no modela ese estado del navegador, así que el test exige `set_value` y
`value` en el proto: es la señal que hace que el campo visible cambie.

`AppTest` no puede adjuntar ficheros: el script sustituye `st.file_uploader` SOLO para la
clave `_vd_fotos` y lo restaura al terminar. La lectura de Gemini va mockeada
(`logic.extract_positions_from_images`). Cifras sintéticas, escritas a mano.
"""
import io
import os
import sys

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, os.path.dirname(__file__))
import logic

BASE = os.path.dirname(os.path.abspath(__file__))

_CSV = (
    '"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"\n'
    '"01/15/2025","Buy","MSTY","ETF SINTETICO A","40","$25.00","","-$1000.00"\n'
    '"01/15/2025","Buy","SCHB","ETF SINTETICO B","10","$20.00","","-$200.00"\n'
    '"01/15/2025","Buy","SLV","ETF SINTETICO C","4","$25.00","","-$100.00"\n'
)

_PREVIA = {
    "MSTY": {"shares": 40.0, "invested": 1000.0},
    "SCHB": {"shares": 10.0, "invested": 200.0},
    "SLV": {"shares": 4.0, "invested": 100.0},
}

# Lo que «devuelve Gemini»: SLV no sale en la captura → va a 0 (Daniel, 2026-10-02).
_LEIDO = {
    "MSTY": {"shares": 12.5, "cost_basis": 900.0},
    "SCHB": {"shares": 30.25, "cost_basis": 650.5},
}

_SCRIPT = """
import sys
sys.path.insert(0, {path!r})
import streamlit as st
from ui.carga import render_carga


class _Foto:
    type = "image/png"

    def getvalue(self):
        return st.session_state.get("_test_foto_bytes", b"")


_real = st.file_uploader


def _uploader(*args, **kwargs):
    if kwargs.get("key") == "_vd_fotos":
        return [_Foto()] if st.session_state.get("_test_foto_bytes") else []
    return _real(*args, **kwargs)


st.file_uploader = _uploader
try:
    render_carga()
finally:
    st.file_uploader = _real
""".format(path=BASE)


def _at():
    at = AppTest.from_string(_SCRIPT, default_timeout=40)
    at.session_state["_wizard_df_clean"] = logic.normalize_csv(pd.read_csv(io.StringIO(_CSV)))
    at.session_state["_wizard_csv_ticker_data"] = dict(_PREVIA)
    at.session_state["_wizard_broker"] = "schwab"
    at.session_state["_wizard_csv_name"] = "sintetico.csv"
    return at


def _campo(at, clave):
    encontrados = [w for w in at.number_input if w.proto.id.endswith(clave)]
    assert encontrados, f"ningún number_input con id terminado en {clave!r}"
    return encontrados[0].value


def _proto(at, clave):
    return [w for w in at.number_input if w.proto.id.endswith(clave)][0].proto


def _empuja(at, clave, valor):
    """El navegador muestra `valor`: el proto lo fuerza (`set_value`) con ese valor."""
    p = _proto(at, clave)
    assert p.set_value, f"{clave}: el proto no fuerza el valor; el navegador conserva el viejo"
    assert p.value == valor, f"{clave}: el proto empuja {p.value}, se esperaba {valor}"


def _textos(at):
    return " ".join(str(getattr(e, "value", "")) for e in
                    list(at.markdown) + list(at.warning) + list(at.info) + list(at.caption))


@pytest.fixture
def lectura(monkeypatch):
    llamadas = []

    def _falso(payload, analizables, clave):
        llamadas.append(list(analizables))
        return {t: dict(v) for t, v in _LEIDO.items()}

    monkeypatch.setenv("GEMINI_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(logic, "extract_positions_from_images", _falso)
    return llamadas


def _subir_foto(at, contenido=b"foto-1"):
    """Un solo `at.run()`: lee la foto, `st.rerun()` y el pase siguiente crea los campos.
    El árbol que queda es el de ESE pase, el que el navegador recibe con el empuje."""
    at.session_state["_test_foto_bytes"] = contenido
    at.run()


def test_foto_reemplaza_la_vista_previa_en_los_campos(lectura):
    at = _at()
    at.run()
    assert not at.exception
    assert _campo(at, "_vd_sh_MSTY") == 40.0           # vista previa: los widgets ya existen

    _subir_foto(at)
    assert not at.exception
    assert lectura, "la lectura de la foto no llegó a correr"
    assert _campo(at, "_vd_sh_MSTY") == 12.5
    assert _campo(at, "_vd_cb_MSTY") == 900.0
    assert _campo(at, "_vd_sh_SCHB") == 30.25
    assert _campo(at, "_vd_cb_SCHB") == 650.5
    assert _campo(at, "_vd_sh_SLV") == 0.0             # ausente de la foto: a 0
    assert _campo(at, "_vd_cb_SLV") == 0.0
    _empuja(at, "_vd_sh_MSTY", 12.5)
    _empuja(at, "_vd_cb_MSTY", 900.0)
    _empuja(at, "_vd_sh_SCHB", 30.25)
    _empuja(at, "_vd_cb_SCHB", 650.5)
    _empuja(at, "_vd_sh_SLV", 0.0)
    _empuja(at, "_vd_cb_SLV", 0.0)


def test_el_empuje_es_de_un_solo_render(lectura):
    """Tras aplicar la foto, el siguiente render ya no fuerza nada: si lo hiciera, pisaría
    en cada rerun lo que el cliente escriba a mano."""
    at = _at()
    at.run()
    _subir_foto(at)
    at.run()
    assert not _proto(at, "_vd_sh_MSTY").set_value
    assert _campo(at, "_vd_sh_MSTY") == 12.5


def test_origen_captura_tras_confirmar(lectura):
    at = _at()
    at.run()
    _subir_foto(at)
    [b for b in at.button if b.proto.id.endswith("_vd_confirm_pos")][0].click()
    at.run()
    origen = at.session_state["_captura_origen"]
    assert origen["MSTY"] == {"shares": "captura", "cost_basis": "captura"}
    assert origen["SCHB"] == {"shares": "captura", "cost_basis": "captura"}
    assert origen["SLV"] == {"shares": "captura", "cost_basis": "captura"}


def test_edicion_manual_posterior_a_la_foto_se_conserva(lectura):
    at = _at()
    at.run()
    _subir_foto(at)
    [w for w in at.number_input if w.proto.id.endswith("_vd_sh_MSTY")][0].set_value(13.0)
    at.run()
    assert _campo(at, "_vd_sh_MSTY") == 13.0
    assert len(lectura) == 1                           # misma foto: no se relee


def test_aviso_de_tickers_ausentes_en_la_foto(lectura):
    at = _at()
    at.run()
    assert "no aparece" not in _textos(at)
    _subir_foto(at)
    texto = _textos(at)
    assert "SLV no aparece en tu captura: los pusimos en 0" in texto
    assert "MSTY no aparece" not in texto
