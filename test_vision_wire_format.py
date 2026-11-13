"""El cuerpo que el SDK manda a Gemini lleva los nombres que la API reconoce.

Por qué existe (13-nov-2026). `requirements.txt` pedía `google-genai>=1.0.0`. En un deploy
cualquiera, Streamlit Cloud reinstaló una 2.2x que serializa `inlineData.mime_type` en
snake_case — hasta la 2.20.0 mandaba `mimeType` —, la API respondió `400 BadRequest` y el
lector de capturas quedó caído **sin que nadie tocara el código**. Nada lo detectó: la
excepción se tragaba, no había log, y el aviso de la app culpaba a la captura del cliente.

Estos tests no gastan cuota ni tocan la red: interceptan el cuerpo en `build_request` y
abortan antes de enviarlo, con una clave falsa. Por eso NO llevan la marca `vision`.

Dos trampas que estos tests evitan a propósito:
  1. No reconstruyen el request a mano — llaman a `logic.extract_positions_from_images`, que
     es el código que va a producción. Un test que arma su propio cuerpo se compara consigo
     mismo y seguiría verde con la función rota.
  2. Si no logran capturar nada, FALLAN en vez de pasar en vacío. Medido: con la rama 3.x del
     SDK el transporte es otro y una sonda así devuelve «ningún campo en snake_case», que
     parece un aprobado y es una respuesta vacía.
"""
import json

import httpx
import pytest

import logic

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture
def cuerpo_enviado(monkeypatch):
    """Devuelve el cuerpo JSON que el SDK arma para Gemini, sin enviarlo a ninguna parte."""
    capturado = {}

    class Corta(RuntimeError):
        pass

    def espia(self, *a, **kw):
        req = _orig(self, *a, **kw)
        try:
            d = json.loads(req.content)
        except Exception:
            d = None
        if isinstance(d, dict) and ("contents" in d or "generationConfig" in d):
            capturado.setdefault("cuerpo", d)
            raise Corta("cortado por el test: no se envía nada")
        return req

    _orig = httpx.Client.build_request
    monkeypatch.setattr(httpx.Client, "build_request", espia)

    logic.extract_positions_from_images(
        [(PNG, "image/png")], ["MSTY", "SCHB"], "clave-falsa-de-test")

    assert "cuerpo" in capturado, (
        "no se pudo capturar el cuerpo: el SDK cambió de transporte y esta sonda ya no lo ve. "
        "Un resultado vacío NO es un aprobado — arregla la sonda antes de confiar en este guard."
    )
    return capturado["cuerpo"]


def _partes(cuerpo):
    return [p for c in cuerpo.get("contents", []) for p in c.get("parts", [])]


def test_el_adjunto_va_como_mimeType_no_mime_type(cuerpo_enviado):
    """La regresión exacta del 13-nov-2026: `mime_type` donde la API espera `mimeType`."""
    inline = [p.get("inlineData") or p.get("inline_data") for p in _partes(cuerpo_enviado)]
    inline = [d for d in inline if d]
    assert inline, f"ninguna parte lleva la imagen: {_partes(cuerpo_enviado)}"
    for d in inline:
        assert "mime_type" not in d, (
            "el SDK manda inlineData.mime_type en snake_case y Gemini responde 400. "
            f"Versión instalada incompatible; hasta la 2.20.0 mandaba mimeType. Campos: {sorted(d)}")
        assert "mimeType" in d, f"falta mimeType en el adjunto: {sorted(d)}"


def test_la_imagen_viaja_en_el_cuerpo(cuerpo_enviado):
    """Si la imagen no va, el 'arreglo' del nombre del campo no significaría nada."""
    datos = [(p.get("inlineData") or p.get("inline_data") or {}).get("data")
             for p in _partes(cuerpo_enviado)]
    assert any(d for d in datos), "el cuerpo no lleva ninguna imagen"


def test_el_contenedor_del_adjunto_es_el_que_la_api_espera(cuerpo_enviado):
    """Mismo fallo, un nivel más arriba: `inline_data` en vez de `inlineData` también da 400."""
    for p in _partes(cuerpo_enviado):
        assert "inline_data" not in p, f"parte en snake_case: {sorted(p)}"


def test_sin_clave_no_se_llama_a_gemini_y_se_marca_el_fallo(monkeypatch):
    """Sin clave es un fallo técnico, no una captura mala: no debe confundirse con {}."""
    def no_llamar(*a, **kw):
        raise AssertionError("no debería construirse ninguna petición sin clave")

    monkeypatch.setattr(httpx.Client, "build_request", no_llamar)
    assert logic.extract_positions_from_images([(PNG, "image/png")], ["MSTY"], "") == {
        "error": "lector"}


def test_sin_imagenes_devuelve_vacio_sin_marcar_fallo():
    """No hay nada que leer: eso no es que el lector esté caído."""
    assert logic.extract_positions_from_images([], ["MSTY"], "clave") == {}
    assert logic.extract_positions_from_images([(PNG, "image/png")], [], "clave") == {}


def test_un_fallo_de_red_se_marca_como_fallo_del_lector(monkeypatch):
    """Lo que antes se tragaba: la llamada revienta y la UI no podía saberlo."""
    def revienta(self, *a, **kw):
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(httpx.Client, "send", revienta)
    assert logic.extract_positions_from_images(
        [(PNG, "image/png")], ["MSTY"], "clave-falsa-de-test") == {"error": "lector"}


def test_el_wrapper_de_costo_base_no_se_atraganta_con_la_marca(monkeypatch):
    """`extract_cost_basis_from_images` recorre el dict: la marca no puede romperlo."""
    monkeypatch.setattr(logic, "extract_positions_from_images",
                        lambda *a, **k: {"error": "lector"})
    assert logic.extract_cost_basis_from_images([(PNG, "image/png")], ["MSTY"], "k") == {}
