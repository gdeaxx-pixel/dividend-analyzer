"""A4 — la app sugiere el país desde donde te conectas; declararlo lo sigue haciendo el
cliente (19-nov).

Pedido de Daniel: «que lo sugiera… si se equivoca, la persona hace clic y aparece toda la
lista para seleccionarlo manualmente».

De dónde sale: la zona horaria y el idioma que reporta el navegador (`st.context`). Medido
con un navegador puesto en Bogotá: la app ve `America/Bogota` y `es-CO`. **No se usa la IP
ni ningún servicio de fuera.**

Por qué sugiere y no declara: dónde te conectas no es dónde tributas —Daniel vive en
México y tributa en Colombia— y de la residencia cuelga la retención con derecho, que
decide cuánto dice la app que te devuelven. «Sin declarar» sigue siendo el default.

Verificado en vivo sobre el componente real: desde Bogotá sale «Parece que estás en
Colombia · usarlo» y, al pulsarlo, el perfil queda `country=Colombia, source=navegador`;
desde Berlín no se sugiere nada y el desplegable sigue en su sitio.
"""
import os

import pytest
from streamlit.testing.v1 import AppTest

import logic
from ui.estado import pais_sugerido

_RAIZ = os.path.dirname(os.path.abspath(__file__))

_SCRIPT = """
import sys
sys.path.insert(0, {path!r})
import streamlit as st
from ui import carga, estado

carga._contexto_navegador = lambda: (st.session_state.get("_tz"), st.session_state.get("_loc"))
carga._render_residencia_fiscal()
st.session_state["_perfil"] = estado.perfil_fiscal()
""".format(path=_RAIZ)


def _app(**estado) -> AppTest:
    at = AppTest.from_string(_SCRIPT, default_timeout=25)
    for clave, valor in estado.items():
        at.session_state[clave] = valor
    at.run()
    assert at.exception == [], [e.value for e in at.exception]
    return at


def _boton(at):
    return next((b for b in at.button if b.key == "_vd_pais_sugerido"), None)


# ── El mapa ───────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tz, pais", [
    ("America/Bogota", "Colombia"),
    ("America/Mexico_City", "México"),
    ("America/Tijuana", "México"),
    ("America/Santiago", "Chile"),
    ("America/Caracas", "Venezuela"),
    ("Europe/Madrid", "España"),
    ("America/Lima", "Perú"),
    ("America/Sao_Paulo", "Brasil"),
    ("America/New_York", "Estados Unidos"),
    ("America/Guayaquil", "Otros LATAM"),
])
def test_la_zona_horaria_dice_el_pais(tz, pais):
    assert pais_sugerido(tz, None) == pais


def test_argentina_se_resuelve_por_prefijo():
    """Argentina reparte sus provincias en `America/Argentina/<ciudad>`: listarlas una a
    una dejaría fuera a quien viva en la que falte."""
    for ciudad in ("Buenos_Aires", "Cordoba", "Mendoza", "Ushuaia", "Salta"):
        assert pais_sugerido(f"America/Argentina/{ciudad}", None) == "Argentina"


def test_sin_zona_horaria_queda_el_idioma():
    assert pais_sugerido(None, "es-CO") == "Colombia"
    assert pais_sugerido("", "pt-BR") == "Brasil"
    assert pais_sugerido("", "en_US") == "Estados Unidos"


def test_la_zona_horaria_manda_sobre_el_idioma():
    """Un navegador en inglés en Bogotá sigue estando en Bogotá."""
    assert pais_sugerido("America/Bogota", "en-US") == "Colombia"


def test_lo_que_no_se_reconoce_no_se_sugiere():
    for tz, loc in (("Europe/Berlin", "de-DE"), ("Asia/Tokyo", "ja-JP"),
                    ("", ""), (None, None), ("basura", "xx"), ("", "es")):
        assert pais_sugerido(tz, loc) is None, (tz, loc)


def test_solo_se_sugiere_un_pais_que_la_app_sepa_tasar():
    """Un país fuera de la lista haría que el botón declarara algo que `declarar_pais`
    descarta en silencio: el cliente pulsaría y no pasaría nada."""
    for tz in ("America/Bogota", "Europe/Madrid", "America/Argentina/Cordoba"):
        assert pais_sugerido(tz, None) in logic.NRA_COUNTRY_RATES


# ── El botón ──────────────────────────────────────────────────────────────────────────

def test_el_boton_aparece_con_el_pais_detectado():
    at = _app(_tz="America/Bogota", _loc="es-CO")
    boton = _boton(at)
    assert boton is not None, "no se ofreció el país detectado"
    assert "Colombia" in boton.label


def test_sugerir_no_es_declarar():
    """EL punto de todo esto: hasta que el cliente no pulsa, su residencia sigue sin
    declarar y la app no estima devoluciones."""
    at = _app(_tz="America/Mexico_City", _loc="es-MX")
    assert at.session_state["_perfil"]["rate_declared"] is False
    assert at.session_state["_perfil"]["country"] is None


def test_al_pulsarlo_queda_declarado_y_se_sabe_de_donde_salio():
    at = _app(_tz="America/Bogota", _loc="es-CO")
    _boton(at).click().run()
    perfil = at.session_state["_perfil"]
    assert perfil["country"] == "Colombia"
    assert perfil["rate_declared"] is True
    assert perfil["source"] == "navegador", "sin esto no se sabe que fue una sugerencia"


def test_con_el_pais_ya_declarado_no_se_insiste():
    at = _app(_tz="America/Bogota", _loc="es-CO", _perfil_fiscal_pais="México",
              _perfil_fiscal_fuente="manual")
    assert _boton(at) is None, "no se le discute al cliente lo que ya declaró"


def test_sin_deteccion_queda_el_desplegable_de_siempre():
    at = _app(_tz="Europe/Berlin", _loc="de-DE")
    assert _boton(at) is None
    assert at.selectbox, "el desplegable tiene que seguir estando"


def test_sin_deteccion_no_se_ofrece_nada():
    at = _app()
    assert at.exception == []
    assert _boton(at) is None


def test_si_el_navegador_no_dice_nada_la_carga_no_se_cae(monkeypatch):
    """`st.context` no existe en algunos arneses y el componente no puede depender de él.

    Se prueba la función REAL, no el doble que usan los otros tests: con el doble puesto,
    el `try` nunca corre y quitarlo pasaba verde — medido.
    """
    from ui import carga

    class SinContexto:
        @property
        def timezone(self):
            raise RuntimeError("este arnés no tiene contexto de navegador")

        @property
        def locale(self):
            raise RuntimeError("este arnés no tiene contexto de navegador")

    monkeypatch.setattr(carga.st, "context", SinContexto())
    assert carga._contexto_navegador() == (None, None)
