"""Tests de UI de privacidad (F2, F4): `streamlit.testing.v1.AppTest` sobre `ui/carga.py`
y guards de contenido sobre `PRIVACY.md`.

`default_timeout=25` en cada `AppTest.from_string`: el default de AppTest son 3 s y
`render_carga()` no siempre cabe ahí. Medido el 2026-09-23 sobre
`test_s1_confirmar_posiciones_conserva_la_captura`: en serie y con la maquina ociosa
falla ~1 de cada 11 corridas, pero con cuatro pytest compitiendo por CPU falla 4 de 4,
siempre en el segundo `.run()` (el de despues del clic) y siempre con
`RuntimeError: AppTest script run timed out after 3(s)`. No es un fallo del producto:
es el reloj del arnes. Mismo diagnostico y mismo valor que
`test_carga_1042s._at_con_posiciones_confirmadas`; este archivo era el unico con
`AppTest` que no lo llevaba.

Cuanto tarda, y de que (medido el 2026-09-24 sobre `febcd08`, cronometrando el `.run()`
con un guard sobre `socket.socket.connect`): el `run()` inicial tarda **0.13 s** y el de
despues del clic **3.55 - 6.87 s**, con **CERO conexiones de red**. O sea el coste es
render local del rerun, no I/O: si esto vuelve a enrojecer, no busques una llamada a
Yahoo. Eso tambien explica por que el archivo corrido SOLO fallaba 5 de 5 veces y dentro
de la suite completa pasaba — ahi los modulos ya estan calientes. Con el default de 3 s
no cabia ni en el mejor caso; los 25 s dejan ~3.6x de margen sobre el peor medido.

Importa porque un rojo intermitente aqui no se distingue de una regresion: los
workflows de refresco corren la suite y avisan por Telegram si queda roja (#117), y un
rojo que aparece y desaparece solo es exactamente lo que el mecanismo anti-deriva (B1)
tendria que poder descartar.
"""
import os
import re
import subprocess
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
    at = AppTest.from_string(_SCRIPT, default_timeout=25)
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
    at = AppTest.from_string(_SCRIPT, default_timeout=25)
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

    at = AppTest.from_string(_SCRIPT, default_timeout=25)
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

    at = AppTest.from_string(_SCRIPT, default_timeout=25)
    at.run()
    assert at.exception == []

    expanders = [e for e in at.get("expander") if e.label == "Cómo tratamos tus datos"]
    contenido = "\n".join(m.value for m in expanders[0].get("markdown"))
    assert "# Aviso de privacidad" not in contenido
    assert "Actualizado:" not in contenido
    assert contenido.startswith("**Tus archivos.**")


def test_f4_privacy_no_promete_telegram():
    with open(_PRIVACY_PATH, encoding="utf-8") as f:
        texto = f.read()
    assert "Telegram" not in texto


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

    at = AppTest.from_string(_SCRIPT, default_timeout=25)
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
    """El bundle del demo LIMPIA el contexto de captura de la sesión anterior.

    Mide la consecuencia, no la forma: vuelca el bundle sobre una sesión ya contaminada,
    igual que `app.py:52-55`. La versión anterior afirmaba `bundle.get(clave) is None`,
    que **no vigila nada**: `.get` devuelve `None` tanto si la clave vale `None` como si
    falta, así que un bundle que no traiga las claves dejaba la captura vieja intacta y
    el test seguía verde (medido: mutantes M2 y M4 de `mutar_s4_s1.sh` sobrevivían).
    """
    import demo_mode
    from ui.carga import CLAVES_CONTEXTO_CARTERA

    if not demo_mode.demo_available():
        # El demo solo existe donde está `real_examples/` (`demo_available()` es literalmente
        # `isdir(REAL)`): sin datos privados no hay bundle que probar. Mismo criterio que los
        # ~70 tests que se saltan sin `real_examples/`. Antes esto salía ROJO en CI y en la
        # nube, y habría disparado el aviso de Telegram de cada refresco semanal (auditoría M4).
        pytest.skip("real_examples/ no montado: sin datos privados no hay demo que cargar")
    bundle = demo_mode.load_demo_case("schwab")
    assert bundle is not None

    sesion = {"_wizard_ocr_positions": {"MSTY": {"shares": 999.0, "cost": 12345.0}},
              "_wizard_photo_sig": ("captura_de_otra_cartera.png", 4321)}
    for _k, _v in bundle.items():          # así lo aplica app.py:52-55
        sesion[_k] = _v

    for clave in ("_wizard_ocr_positions", "_wizard_photo_sig"):
        assert clave in CLAVES_CONTEXTO_CARTERA, f"{clave} salió del contrato de reset"
        assert clave in bundle, f"el bundle del demo no trae {clave}: no puede limpiarla"
        assert sesion[clave] is None, f"{clave} conserva la captura de la sesión previa"


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
    at = AppTest.from_string(_SCRIPT, default_timeout=25)
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


def test_s1_editar_borra_el_contexto_con_fotos_de_igual_nombre_y_tamano(monkeypatch):
    """Cierra el PARA de S1: M3_firma_nombre_tamano sobrevivía porque
    test_s1_firma_por_contenido_no_por_nombre_y_tamano mide `_firma_fotos` aislado, no el
    sitio de llamada real (`ui/carga.py:307`, dentro de render_bloque_posiciones).

    Este test pasa por la pantalla real: la firma de la foto A sale de un primer render
    (no se precalcula con el helper, para no imitar por construcción lo que el sitio de
    llamada debe hacer solo), y en un segundo render se sube la foto B — mismo name, mismo
    size, contenido distinto. Con la firma vieja por (nombre, tamaño) las dos fotos son
    indistinguibles y el OCR no se vuelve a correr; con la firma por contenido, sí."""
    import streamlit as st

    class _FakeUpload:
        def __init__(self, name, content):
            self.name = name
            self.size = len(content)
            self.type = "image/png"
            self._content = content

        def getvalue(self):
            return self._content

    contenido_a = b"contenido de la foto A"
    contenido_b = b"contenido de la foto B"
    assert len(contenido_a) == len(contenido_b)

    foto_a = _FakeUpload("captura.png", contenido_a)
    foto_b = _FakeUpload("captura.png", contenido_b)
    assert (foto_a.name, foto_a.size) == (foto_b.name, foto_b.size)

    ocr_a = {"MSTY": {"shares": 999.0, "cost_basis": 12345.0}}
    ocr_b = {"MSTY": {"shares": 5.0, "cost_basis": 120.0}}

    monkeypatch.setenv("GEMINI_API_KEY", "falsa")
    fotos_actuales = [foto_a]
    monkeypatch.setattr(st, "file_uploader", lambda *a, **k: fotos_actuales)
    resultados_ocr = iter([ocr_a, ocr_b])
    monkeypatch.setattr(logic, "extract_positions_from_images",
                        lambda *a, **k: next(resultados_ocr))

    at = AppTest.from_string(_SCRIPT, default_timeout=25)
    at.session_state["_wizard_df_clean"] = _df("schwab_synth_1")
    at.session_state["_wizard_csv_ticker_data"] = {"MSTY": {"shares": 40.0, "invested": 1000.0}}
    at.session_state["_wizard_broker"] = "schwab"
    at.session_state["_wizard_csv_name"] = "cartera_A.csv"
    at.run()
    assert at.exception == []
    sig_a = _ss(at, "_wizard_photo_sig")
    assert sig_a is not None
    assert _ss(at, "_wizard_ocr_positions") == ocr_a

    fotos_actuales[:] = [foto_b]
    at.run()
    assert at.exception == []

    assert _ss(at, "_wizard_photo_sig") != sig_a
    assert _ss(at, "_wizard_ocr_positions") == ocr_b


# ── Fase 4 de la captura · el aviso y la casilla dicen lo mismo ─────────────

def _privacy():
    with open(_PRIVACY_PATH, encoding="utf-8") as f:
        return f.read()


def test_f4_privacy_dice_los_mismos_dias_que_la_casilla():
    from ui.carga import CAPTURA_RETENCION_DIAS, _AYUDA_CAPTURA, _privacy_visible

    texto = _privacy()
    assert set(re.findall(r"(\d+) días", texto)) == {str(CAPTURA_RETENCION_DIAS)}
    assert f"{CAPTURA_RETENCION_DIAS} días" in _privacy_visible(texto)
    assert f"{CAPTURA_RETENCION_DIAS} días" in _AYUDA_CAPTURA


def test_f4_privacy_y_la_casilla_prometen_lo_mismo():
    from ui.carga import _AYUDA_CAPTURA, _QUE_GUARDAMOS, _privacy_visible

    visible = _privacy_visible(_privacy())
    no_guardamos = " ".join(visible.split("**Qué no guardamos:**")[1].split("\n- ")[0].split())
    no_casilla = _QUE_GUARDAMOS.split("No:")[1]
    for dato in ("el archivo original", "tus capturas", "tu correo", "tu nombre",
                 "tu número de cuenta", "tu IP"):
        assert dato in no_guardamos, dato
        assert dato in no_casilla, dato
    assert "No entrena ninguna IA" in _AYUDA_CAPTURA
    assert "No se usa para entrenar ningún modelo" in visible
    assert "Backblaze B2" in visible
    assert "desactivada" not in visible
    assert "no sale del servidor" not in visible


_TELEFONO = re.compile(
    r"wa\.me/|api\.whatsapp\.com/send"
    r"|\+\d{1,3}[\s.-]?\(?\d{1,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}"
    r"|(?<![\d.])(?:\+?57[\s-]?)?3\d{2}[\s-]?\d{3}[\s-]?\d{4}(?![\d.])",
    re.IGNORECASE,
)


def test_f4_contacto_es_el_correo_de_soporte_y_no_hay_telefonos_versionados():
    assert "soporte@invierteygana.net" in _privacy()

    versionados = subprocess.run(["git", "ls-files"], cwd=_RAIZ, capture_output=True,
                                 text=True, check=True).stdout.split()
    assert len(versionados) > 50
    hallados = []
    for ruta in versionados:
        try:
            with open(os.path.join(_RAIZ, ruta), encoding="utf-8") as f:
                contenido = f.read()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        hallados += [(ruta, m.group()) for m in _TELEFONO.finditer(contenido)]
    assert hallados == []
