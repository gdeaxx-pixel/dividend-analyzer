"""El paso 2 distingue «tu captura no sirve» de «nuestro lector está caído».

Hasta el 13-nov-2026 los dos fracasos daban el mismo aviso: «No pudimos leer posiciones en
esa captura. Prueba con otra…». Con el lector caído por una regresión del SDK, eso mandaba
al cliente a recortar y resubir capturas suyas que estaban perfectas. Medido: una captura
sintética impecable recibía exactamente ese texto.

Reusa el montaje de `test_carga_foto` en vez de copiarlo: si cambia la forma de armar la
página, estos tests cambian con ella y no se quedan probando una copia vieja.
"""
import pytest

import logic
from test_carga_foto import _at, _subir_foto


def _avisos(at):
    """Todo lo que el cliente lee en los recuadros de aviso de la página."""
    return " ".join(str(getattr(e, "value", ""))
                    for e in list(at.error) + list(at.warning) + list(at.info))


def _pantalla_tras_fallar(at):
    """La segunda pasada: la primera llama al lector y hace `st.rerun()`."""
    _subir_foto(at)
    at.run()
    assert not at.exception, at.exception
    return _avisos(at)


@pytest.fixture
def modo_captura(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "clave-de-prueba")
    at = _at()
    at.session_state["_vd_modo_pos"] = "captura"
    return at


def test_el_lector_caido_no_culpa_a_la_captura(modo_captura, monkeypatch):
    monkeypatch.setattr(logic, "extract_positions_from_images",
                        lambda *a, **k: {"error": "lector"})
    texto = _pantalla_tras_fallar(modo_captura)
    assert "no está respondiendo" in texto, f"no salió el aviso del lector caído: {texto!r}"
    assert "No pudimos leer posiciones en esa captura" not in texto, (
        "sigue saliendo el aviso que culpa a la captura del cliente")
    assert "Archivo de Schwab" in texto, "el aviso no ofrece la salida que sí funciona"


def test_una_captura_sin_los_fondos_si_habla_de_la_captura(modo_captura, monkeypatch):
    """El otro lado: cuando el lector responde y no encuentra nada, el aviso correcto es el viejo."""
    monkeypatch.setattr(logic, "extract_positions_from_images", lambda *a, **k: {})
    texto = _pantalla_tras_fallar(modo_captura)
    assert "No pudimos leer posiciones en esa captura" in texto, (
        f"desapareció el aviso de la captura ilegible: {texto!r}")
    assert "no está respondiendo" not in texto, (
        "dice que el lector está caído cuando sí respondió")


def test_la_marca_de_fallo_no_llega_a_la_tabla_de_posiciones(modo_captura, monkeypatch):
    """`{'error': ...}` se saca antes de guardar: aguas abajo esto se recorre por ticker."""
    monkeypatch.setattr(logic, "extract_positions_from_images",
                        lambda *a, **k: {"error": "lector"})
    _pantalla_tras_fallar(modo_captura)
    guardado = modo_captura.session_state.get("_wizard_ocr_positions") or {}
    assert "error" not in guardado, f"la marca se coló en las posiciones: {guardado}"
    assert modo_captura.session_state.get("_wizard_ocr_fallo") == "lector"
