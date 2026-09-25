"""Tests de la rama b2 de storage.py (Fase 3-B, spec F3B-qwen-adaptador-b2).

Cliente FALSO en memoria que versiona como Backblaze B2 de verdad:
  - put_object AÑADE una versión nueva a la lista de la clave;
  - delete_object SIN VersionId solo añade un delete marker (el dato sigue ahí,
    igual que en B2/S3 versionado); CON VersionId borra esa versión de verdad.

Ninguna credencial real: todos los valores son obviamente falsos.
Los esperados están escritos a mano.
"""
import io
import os
import sys

import pytest
from botocore.exceptions import ClientError

import storage


# ── Valores de prueba (obviamente falsos) ────────────────────────────────────

_ENDPOINT = "https://s3.us-west-004.backblazeb2.com"
_CLAVE_FICTICIA = "valor-ficticio-para-pruebas"
_CSV = "fecha,ticker,cantidad\n2026-01-15,AAA,100\n"
_RAIZ = "prueba/captured/schwab/caso-1"

# Las 5 claves que upload_case debe escribir, escritas a mano:
# <prefix>/captured/<broker>/<case_id>/<archivo>
_CLAVES_ESPERADAS = sorted(f"{_RAIZ}/{n}" for n in (
    "transactions_min.csv", "ground_truth.json", "quality.json",
    "gemini_raw.json", "meta.json"))

# Contenidos esperados, escritos a mano (los JSON son el volcado exacto de
# json.dumps(..., ensure_ascii=False, indent=2): 2 espacios por nivel, sin
# espacio al final de línea y sin salto de línea final).
_ESPERADOS = {
    "transactions_min.csv": _CSV,
    "ground_truth.json": '{\n  "AAA": {\n    "shares": 100\n  }\n}',
    "quality.json": '{\n  "AAA": {\n    "level": "ok"\n  }\n}',
    "gemini_raw.json": '{\n  "modelo": "falso"\n}',
    "meta.json": '{\n  "case_id": "caso-1",\n  "n_rows": 1\n}',
}


def _bundle(case_id="caso-1", broker="schwab"):
    return {
        "case_id": case_id,
        "broker": broker,
        "transactions_min_csv": _CSV,
        "ground_truth": {"AAA": {"shares": 100}},
        "quality": {"AAA": {"level": "ok"}},
        "gemini_raw": {"modelo": "falso"},
        "meta": {"case_id": case_id, "n_rows": 1},
    }


# ── Cliente falso ────────────────────────────────────────────────────────────

class FakeB2:
    """boto3.client('s3') de juguete: guarda versiones y registra cada llamada.

    solo_escritura=True lanza ante CUALQUIER método que no sea put_object
    (así se prueba que la subida no lee ni lista: la clave real será de solo
    escritura). put_error hace que put_object lance esa excepción.
    """

    def __init__(self, put_error=None, solo_escritura=False):
        self.versiones = {}    # clave -> [{'VersionId': str, 'Body': bytes|None}]
        self.llamadas = []     # nombres de método, en orden
        self._seq = 0
        self.put_error = put_error
        self.solo_escritura = solo_escritura

    def _vid(self):
        self._seq += 1
        return f"v{self._seq}"

    def _vigilar(self, metodo):
        self.llamadas.append(metodo)
        if self.solo_escritura and metodo != "put_object":
            raise PermissionError(
                f"la clave de producción es de solo escritura: {metodo}")

    def __getattr__(self, nombre):
        # Método no implementado (p.ej. head_object) = llamada prohibida:
        # durante la subida la app real no puede leer ni listar nada.
        if nombre.startswith("__"):
            raise AttributeError(nombre)

        def _prohibido(**kwargs):
            self._vigilar(nombre)
            raise PermissionError(f"método no permitido en la subida: {nombre}")
        return _prohibido

    def add_delete_marker(self, clave):
        """Añade un delete marker como lo dejaría un borrado 'normal' en B2."""
        self.versiones.setdefault(clave, []).append(
            {"VersionId": self._vid(), "Body": None})

    # ── API usada por storage.py ──

    def put_object(self, Bucket, Key, Body, ContentType=None, **resto):
        self._vigilar("put_object")
        if self.put_error is not None:
            raise self.put_error
        self.versiones.setdefault(Key, []).append(
            {"VersionId": self._vid(), "Body": bytes(Body)})
        return {"ETag": '"falso"'}

    def list_objects_v2(self, Bucket, Prefix="", ContinuationToken=None, **resto):
        self._vigilar("list_objects_v2")
        contents = []
        for clave in sorted(self.versiones):
            if not clave.startswith(Prefix):
                continue
            ult = self.versiones[clave][-1]
            if ult["Body"] is None:        # delete marker: objeto invisible
                continue
            contents.append({"Key": clave, "Size": len(ult["Body"])})
        return {"Contents": contents, "IsTruncated": False}

    def get_object(self, Bucket, Key, **resto):
        self._vigilar("get_object")
        versiones = self.versiones.get(Key)
        ult = versiones[-1] if versiones else None
        if ult is None or ult["Body"] is None:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "no existe"},
                 "ResponseMetadata": {"HTTPStatusCode": 404}}, "GetObject")
        return {"Body": io.BytesIO(ult["Body"])}

    def list_object_versions(self, Bucket, Prefix="", KeyMarker=None,
                             VersionIdMarker=None, **resto):
        self._vigilar("list_object_versions")
        versiones, marcadores = [], []
        for clave in sorted(self.versiones):
            if not clave.startswith(Prefix):
                continue
            for v in self.versiones[clave]:
                entrada = {"Key": clave, "VersionId": v["VersionId"]}
                (marcadores if v["Body"] is None else versiones).append(entrada)
        return {"Versions": versiones, "DeleteMarkers": marcadores,
                "IsTruncated": False}

    def delete_object(self, Bucket, Key, VersionId=None, **resto):
        self._vigilar("delete_object")
        versiones = self.versiones.setdefault(Key, [])
        if VersionId is None:
            # Semántica REAL de B2 versionado: sin VersionId solo se añade un
            # delete marker; las versiones anteriores siguen ahí.
            versiones.append({"VersionId": self._vid(), "Body": None})
        else:
            restantes = [v for v in versiones if v["VersionId"] != VersionId]
            if restantes:
                self.versiones[Key] = restantes
            else:
                del self.versiones[Key]
        return {}


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def env_b2(monkeypatch):
    """Configuración por variables de entorno (la ruta que usa Daniel en local)."""
    monkeypatch.delenv("CAPTURE_LOCAL_DIR", raising=False)
    monkeypatch.setenv("CAPTURE_B2_BUCKET", "bucket-de-prueba")
    monkeypatch.setenv("CAPTURE_B2_ENDPOINT", _ENDPOINT)
    monkeypatch.setenv("CAPTURE_B2_KEY_ID", "id-de-prueba")
    monkeypatch.setenv("CAPTURE_B2_APP_KEY", _CLAVE_FICTICIA)
    monkeypatch.setenv("CAPTURE_B2_PREFIX", "prueba")


@pytest.fixture
def fake(env_b2, monkeypatch):
    """Cliente falso inyectado en storage._b2_client."""
    f = FakeB2()
    monkeypatch.setattr(storage, "_b2_client", lambda: f)
    return f


# ── T1 · backend con env ─────────────────────────────────────────────────────

def test_backend_con_las_cuatro_variables_es_b2(fake):
    assert storage.backend() == "b2"


# ── T2 · configuración incompleta ────────────────────────────────────────────

def test_sin_app_key_no_es_b2(env_b2, monkeypatch):
    monkeypatch.delenv("CAPTURE_B2_APP_KEY")
    assert storage.backend() != "b2"


# ── T3 · local manda ─────────────────────────────────────────────────────────

def test_local_manda_sobre_b2(fake, monkeypatch, tmp_path):
    monkeypatch.setenv("CAPTURE_LOCAL_DIR", str(tmp_path))
    assert storage.backend() == "local"


# ── T4 · sin boto3 ───────────────────────────────────────────────────────────

def test_sin_boto3_no_hay_b2_y_upload_devuelve_none(env_b2, monkeypatch):
    # sys.modules['boto3'] = None hace que `import boto3` lance ImportError
    # (comportamiento documentado de Python), sin desinstalar nada.
    monkeypatch.setitem(sys.modules, "boto3", None)
    assert storage.backend() != "b2"
    assert storage.upload_case(_bundle()) is None      # y sin lanzar


# ── T5 · claves ──────────────────────────────────────────────────────────────

def test_upload_escribe_exactamente_las_cinco_claves(fake):
    assert storage.upload_case(_bundle()) == "caso-1"
    assert sorted(fake.versiones) == _CLAVES_ESPERADAS


# ── T6 · solo escritura ──────────────────────────────────────────────────────

def test_la_subida_solo_llama_a_put_object(env_b2, monkeypatch):
    f = FakeB2(solo_escritura=True)   # lanza ante cualquier otro método
    monkeypatch.setattr(storage, "_b2_client", lambda: f)
    assert storage.upload_case(_bundle()) == "caso-1"
    assert sorted(f.versiones) == _CLAVES_ESPERADAS
    assert f.llamadas == ["put_object"] * 5


# ── T7 · ida y vuelta ────────────────────────────────────────────────────────

def test_subir_listar_y_descargar_devuelve_lo_mismo(fake):
    storage.upload_case(_bundle())

    casos = storage.list_cases()
    assert casos == [{"case_id": "caso-1", "broker": "schwab", "backend": "b2"}]

    traidos = storage.fetch_case("schwab", "caso-1")
    assert sorted(traidos) == sorted(_ESPERADOS)
    for nombre, contenido in _ESPERADOS.items():
        assert traidos[nombre] == contenido, nombre


# ── T8 · borrado real (todas las versiones) ─────────────────────────────────

def test_borrado_elimina_todas_las_versiones_y_marcadores(fake):
    storage.upload_case(_bundle())                      # versión 1 de cada clave
    storage.upload_case(_bundle())                      # versión 2 de cada clave
    fake.add_delete_marker(f"{_RAIZ}/meta.json")        # + un marcador
    assert len(fake.versiones[f"{_RAIZ}/meta.json"]) == 3
    storage.upload_case(_bundle(case_id="caso-2"))      # otro caso, debe quedar intacto

    assert storage.delete_case("schwab", "caso-1") is True

    supervivientes = sorted(fake.versiones)
    assert not any(c.startswith(_RAIZ + "/") for c in supervivientes), supervivientes
    raiz2 = "prueba/captured/schwab/caso-2"
    assert supervivientes == sorted(f"{raiz2}/{n}" for n in _ESPERADOS)

    # borrar un caso que no existe no cuenta como borrado
    assert storage.delete_case("schwab", "caso-inexistente") is False


# ── T9 · región extraída del endpoint ────────────────────────────────────────

def test_el_cliente_se_crea_con_la_region_del_endpoint(env_b2, monkeypatch):
    import boto3
    capturados = {}

    def cliente_falso(*args, **kwargs):
        capturados["args"] = args
        capturados["kwargs"] = kwargs
        return FakeB2()

    monkeypatch.setattr(boto3, "client", cliente_falso)
    storage._b2_client()
    # https://s3.us-west-004.backblazeb2.com → región us-west-004
    assert capturados["kwargs"]["region_name"] == "us-west-004"
    assert capturados["kwargs"]["endpoint_url"] == _ENDPOINT


# ── T10 · checksums solo cuando se exigen ────────────────────────────────────

def test_el_cliente_desactiva_los_checksums_por_defecto(env_b2, monkeypatch):
    import boto3
    capturados = {}

    def cliente_falso(*args, **kwargs):
        capturados["kwargs"] = kwargs
        return FakeB2()

    monkeypatch.setattr(boto3, "client", cliente_falso)
    storage._b2_client()
    config = capturados["kwargs"]["config"]
    assert config.request_checksum_calculation == "when_required"
    assert config.response_checksum_validation == "when_required"


# ── T11 · la clave no se filtra ──────────────────────────────────────────────

def test_la_clave_no_aparece_en_la_salida_ni_en_la_excepcion(env_b2, monkeypatch, capsys):
    f = FakeB2(put_error=RuntimeError("fallo simulado en put_object"))
    monkeypatch.setattr(storage, "_b2_client", lambda: f)

    with pytest.raises(RuntimeError) as excinfo:
        storage.upload_case(_bundle())

    capturado = capsys.readouterr()
    secreto = os.environ["CAPTURE_B2_APP_KEY"]   # el valor ficticio de la fixture
    assert secreto not in str(excinfo.value)
    assert secreto not in capturado.out
    assert secreto not in capturado.err
