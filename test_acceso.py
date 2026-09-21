from datetime import datetime, timedelta, timezone

import pytest
from streamlit.testing.v1 import AppTest

import acceso

CLAVE = "clave-de-prueba"


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def _lista(entries=None, generated_at="2026-09-13T12:00:00+00:00", count=None, product_id=4903539, version=1):
    entries = entries if entries is not None else {}
    return {
        "version": version,
        "generated_at": generated_at,
        "product_id": product_id,
        "total_subs_api": 840,
        "count": count if count is not None else len(entries),
        "entries": entries,
    }


# --- M2: hash_correo normalizado (ground truth) ---

def test_hash_vector_normalizado():
    esperado = "4d579a7f8fb6c9cb9b2c472bdcac521f62e1c6e57d39008b2af08c498ad2de84"
    assert acceso.hash_correo("cliente@ejemplo.com", CLAVE) == esperado
    assert acceso.hash_correo("  Cliente@Ejemplo.COM ", CLAVE) == esperado


# --- M11: fecha_es ---

def test_fecha_es():
    assert acceso.fecha_es("2026-01-01") == "1 de enero"
    assert acceso.fecha_es("2026-09-15") == "15 de septiembre"
    assert acceso.fecha_es("2026-12-31") == "31 de diciembre"


# --- M10: sin [auth] -> apagado ---

def test_sin_auth_es_apagado():
    assert acceso.resolver_modo({}) == "apagado"
    assert acceso.resolver_modo({"acceso": {"modo": "aplicar"}}) == "apagado"


def test_resolver_modo_valido_y_default():
    assert acceso.resolver_modo({"auth": {}, "acceso": {"modo": "aplicar"}}) == "aplicar"
    assert acceso.resolver_modo({"auth": {}, "acceso": {"modo": "observar"}}) == "observar"
    assert acceso.resolver_modo({"auth": {}, "acceso": {"modo": "apagado"}}) == "apagado"
    assert acceso.resolver_modo({"auth": {}, "acceso": {"modo": "raro"}}) == "observar"
    assert acceso.resolver_modo({"auth": {}}) == "observar"


# --- M3: última buena no caduca por TTL ---

def test_ultima_buena_sobrevive_ttl():
    lista_ok = _lista({"h1": {"estado": "vigente"}})
    reloj = {"t": _dt("2026-09-13T12:00:00+00:00")}
    fetch_calls = {"n": 0}

    def fetch():
        fetch_calls["n"] += 1
        if fetch_calls["n"] == 1:
            return lista_ok
        raise RuntimeError("red caída")

    cache = acceso.ListaCache(fetch=fetch, ahora=lambda: reloj["t"], ttl_s=1800)

    lista, origen = cache.obtener()
    assert origen == "fresca"
    assert lista == lista_ok

    reloj["t"] = reloj["t"] + timedelta(minutes=31)
    lista2, origen2 = cache.obtener()
    assert origen2 == "ultima_buena"
    assert lista2 == lista_ok


# --- M15: backoff de 60s tras fallo ---

def test_backoff_tras_fallo():
    reloj = {"t": _dt("2026-09-13T12:00:00+00:00")}
    fetch_calls = {"n": 0}

    def fetch():
        fetch_calls["n"] += 1
        raise RuntimeError("red caída")

    cache = acceso.ListaCache(fetch=fetch, ahora=lambda: reloj["t"], ttl_s=1800)

    lista, origen = cache.obtener()
    assert origen == "ninguna"
    assert fetch_calls["n"] == 1

    reloj["t"] = reloj["t"] + timedelta(seconds=10)
    cache.obtener()
    assert fetch_calls["n"] == 1

    reloj["t"] = reloj["t"] + timedelta(seconds=61)
    cache.obtener()
    assert fetch_calls["n"] == 2


# --- M4: lista inválida no reemplaza la última buena ---

def test_lista_invalida_no_pisa():
    lista_ok = _lista({"h1": {"estado": "vigente"}})
    lista_mala = _lista({"h1": {"estado": "vigente"}}, product_id=999999)
    reloj = {"t": _dt("2026-09-13T12:00:00+00:00")}
    fetch_calls = {"n": 0}

    def fetch():
        fetch_calls["n"] += 1
        return lista_ok if fetch_calls["n"] == 1 else lista_mala

    cache = acceso.ListaCache(fetch=fetch, ahora=lambda: reloj["t"], ttl_s=1800)
    cache.obtener()

    reloj["t"] = reloj["t"] + timedelta(minutes=31)
    lista, origen = cache.obtener()
    assert origen == "ultima_buena"
    assert lista == lista_ok


# --- M13: lista con más de 24h se usa igual y avisa ---

def test_lista_vieja_se_usa_y_avisa():
    lista_vieja_dict = _lista({"h1": {"estado": "vigente"}}, generated_at="2026-09-10T12:00:00+00:00")
    ahora = _dt("2026-09-13T12:00:01+00:00")
    assert acceso.lista_vieja(lista_vieja_dict, ahora) is True

    lista_fresca = _lista({"h1": {"estado": "vigente"}}, generated_at="2026-09-13T11:00:00+00:00")
    assert acceso.lista_vieja(lista_fresca, ahora) is False

    decision = acceso.decidir(
        "aplicar",
        {"is_logged_in": True, "email_verified": True, "email": "cliente@ejemplo.com"},
        lista_vieja_dict,
        CLAVE,
    )
    h = acceso.hash_correo("cliente@ejemplo.com", CLAVE)
    assert h not in lista_vieja_dict["entries"]
    assert decision.accion == "rechazar"

    # El cache no debe descartar una lista vieja al leerla: se usa igual.
    reloj = {"t": ahora}
    cache = acceso.ListaCache(fetch=lambda: lista_vieja_dict, ahora=lambda: reloj["t"], ttl_s=1800)
    lista_cacheada, origen = cache.obtener()
    assert origen == "fresca"
    assert lista_cacheada == lista_vieja_dict


# --- M1: email_verified estricto ---

def test_email_verified_estricto():
    lista = _lista({acceso.hash_correo("cliente@ejemplo.com", CLAVE): {"estado": "vigente"}})
    usuario_string = {"is_logged_in": True, "email_verified": "true", "email": "cliente@ejemplo.com"}
    decision = acceso.decidir("aplicar", usuario_string, lista, CLAVE)
    assert decision.accion == "no_verificado"

    usuario_ausente = {"is_logged_in": True, "email": "cliente@ejemplo.com"}
    decision2 = acceso.decidir("aplicar", usuario_ausente, lista, CLAVE)
    assert decision2.accion == "no_verificado"

    usuario_bool = {"is_logged_in": True, "email_verified": True, "email": "cliente@ejemplo.com"}
    decision3 = acceso.decidir("aplicar", usuario_bool, lista, CLAVE)
    assert decision3.accion == "pasar"


# --- M5: fail-open sin lista en modo aplicar ---

def test_fail_open_sin_lista():
    usuario = {"is_logged_in": True, "email_verified": True, "email": "cliente@ejemplo.com"}
    decision = acceso.decidir("aplicar", usuario, None, CLAVE)
    assert decision.accion == "pasar"


# --- M6: observar nunca bloquea ---

def test_observar_no_bloquea():
    lista = _lista({})
    usuario = {"is_logged_in": True, "email_verified": True, "email": "fuera@ejemplo.com"}
    decision = acceso.decidir("observar", usuario, lista, CLAVE)
    assert decision.accion == "pasar"
    assert decision.correo_rechazado == "fuera@ejemplo.com"


def test_aplicar_rechaza_fuera_de_lista():
    lista = _lista({})
    usuario = {"is_logged_in": True, "email_verified": True, "email": "fuera@ejemplo.com"}
    decision = acceso.decidir("aplicar", usuario, lista, CLAVE)
    assert decision.accion == "rechazar"


# --- M7: gracia solo para estado gracia ---

def test_gracia_solo_estado_gracia():
    correo = "cliente@ejemplo.com"
    h = acceso.hash_correo(correo, CLAVE)
    lista_vigente = _lista({h: {"estado": "vigente", "hasta": "2026-09-19"}})
    usuario = {"is_logged_in": True, "email_verified": True, "email": correo}

    decision = acceso.decidir("aplicar", usuario, lista_vigente, CLAVE)
    assert decision.accion == "pasar"
    assert decision.gracia_hasta is None

    lista_gracia = _lista({h: {"estado": "gracia", "hasta": "2026-09-19"}})
    decision2 = acceso.decidir("aplicar", usuario, lista_gracia, CLAVE)
    assert decision2.accion == "pasar"
    assert decision2.gracia_hasta == "2026-09-19"


def test_sin_sesion_pide_login():
    decision = acceso.decidir("aplicar", {"is_logged_in": False}, _lista({}), CLAVE)
    assert decision.accion == "login"
    decision2 = acceso.decidir("observar", {}, _lista({}), CLAVE)
    assert decision2.accion == "login"


def test_modo_apagado_ignora_usuario_y_lista():
    decision = acceso.decidir("apagado", {}, None, CLAVE)
    assert decision.accion == "pasar"


# --- M8 / M9: freno de avisos de rechazo, uno por correo por día, se reinicia ---

def test_freno_un_aviso_por_dia():
    enviados = []
    reloj = {"t": _dt("2026-09-13T10:00:00+00:00")}
    avisador = acceso.Avisador(enviar=lambda m: enviados.append(m), ahora=lambda: reloj["t"])

    avisador.rechazo_observar("cliente@ejemplo.com")
    reloj["t"] = reloj["t"] + timedelta(hours=2)
    avisador.rechazo_observar("cliente@ejemplo.com")

    assert len(enviados) == 1


def test_freno_reinicia_cada_dia():
    enviados = []
    reloj = {"t": _dt("2026-09-13T23:00:00+00:00")}
    avisador = acceso.Avisador(enviar=lambda m: enviados.append(m), ahora=lambda: reloj["t"])

    avisador.rechazo_observar("cliente@ejemplo.com")
    reloj["t"] = reloj["t"] + timedelta(hours=2)  # 2026-09-14T01:00
    avisador.rechazo_observar("cliente@ejemplo.com")

    assert len(enviados) == 2


# --- M14: en aplicar no se avisa por rechazos ---

def test_aplicar_no_avisa_rechazos():
    # Construida a mano (no vía decidir): aísla la puerta modo=="observar" de
    # si acaso decidir() alguna vez rellenara correo_rechazado también en aplicar.
    decision_con_correo = acceso.Decision(accion="rechazar", correo_rechazado="fuera@ejemplo.com")
    assert acceso._debe_avisar_rechazo("aplicar", decision_con_correo) is False
    assert acceso._debe_avisar_rechazo("observar", decision_con_correo) is True


# --- M12: Avisador traga errores de enviar ---

def test_avisador_traga_errores():
    def enviar_falla(_mensaje):
        raise RuntimeError("Telegram caído")

    avisador = acceso.Avisador(enviar=enviar_falla, ahora=lambda: _dt("2026-09-13T10:00:00+00:00"))
    avisador.rechazo_observar("cliente@ejemplo.com")
    avisador.lista_ilegible()
    avisador.lista_vieja()
    avisador.modo_invalido()
    # No debe propagar ninguna excepción.


# ============================================================
# Correcciones de la auditoría (fase2-correcciones.md)
# ============================================================

CLAVE_SECRETS = "clave-de-prueba"


@pytest.fixture(autouse=True)
def _restaurar_internals_acceso():
    # Los scripts de AppTest.from_function monkeypatchean acceso._usuario_actual,
    # acceso._lista_cache_singleton y acceso._avisador_singleton sobre el módulo
    # REAL (no una copia): sin restaurar, un test contamina al siguiente.
    originales = (
        acceso._usuario_actual,
        acceso._lista_cache_singleton,
        acceso._avisador_singleton,
    )
    yield
    acceso._usuario_actual, acceso._lista_cache_singleton, acceso._avisador_singleton = originales


def _script_puerta_no_socio():
    import streamlit as st

    import acceso

    class _ListaDoble:
        def obtener(self):
            return (
                {
                    "version": 1,
                    "generated_at": "2026-09-13T12:00:00+00:00",
                    "product_id": 4903539,
                    "count": 0,
                    "entries": {},
                },
                "fresca",
            )

    class _AvisadorDoble:
        def lista_ilegible(self):
            pass

        def lista_vieja(self):
            pass

        def modo_invalido(self):
            pass

        def rechazo_observar(self, correo):
            pass

    acceso._usuario_actual = lambda: {
        "is_logged_in": True,
        "email_verified": True,
        "email": "nosocio@ejemplo.com",
    }
    acceso._lista_cache_singleton = lambda pat: _ListaDoble()
    acceso._avisador_singleton = lambda token, chat_id: _AvisadorDoble()

    st.session_state["resultado"] = acceso.puerta()


def test_puerta_aplicar_no_socio_ve_rechazo():
    at = AppTest.from_function(_script_puerta_no_socio)
    at.secrets["auth"] = {}
    at.secrets["acceso"] = {"modo": "aplicar", "hmac_key": CLAVE_SECRETS, "allowlist_pat": "pat-fake"}
    at.run()
    assert at.session_state["resultado"] is False
    assert any("no tiene acceso activo" in e.value for e in at.error)


def _script_puerta_socio_entra():
    import streamlit as st

    import acceso

    correo = "socio@ejemplo.com"
    clave = "clave-de-prueba"
    h = acceso.hash_correo(correo, clave)

    class _ListaDoble:
        def obtener(self):
            return (
                {
                    "version": 1,
                    "generated_at": "2026-09-13T12:00:00+00:00",
                    "product_id": 4903539,
                    "count": 1,
                    "entries": {h: {"estado": "vigente"}},
                },
                "fresca",
            )

    class _AvisadorDoble:
        def lista_ilegible(self):
            pass

        def lista_vieja(self):
            pass

        def modo_invalido(self):
            pass

        def rechazo_observar(self, correo):
            pass

    acceso._usuario_actual = lambda: {"is_logged_in": True, "email_verified": True, "email": correo}
    acceso._lista_cache_singleton = lambda pat: _ListaDoble()
    acceso._avisador_singleton = lambda token, chat_id: _AvisadorDoble()

    st.session_state["resultado"] = acceso.puerta()


def test_puerta_aplicar_socio_entra():
    at = AppTest.from_function(_script_puerta_socio_entra)
    at.secrets["auth"] = {}
    at.secrets["acceso"] = {"modo": "aplicar", "hmac_key": CLAVE_SECRETS, "allowlist_pat": "pat-fake"}
    at.run()
    assert at.session_state["resultado"] is True
    assert len(at.error) == 0


def _script_puerta_gracia():
    import streamlit as st

    import acceso

    correo = "gracia@ejemplo.com"
    clave = "clave-de-prueba"
    h = acceso.hash_correo(correo, clave)

    class _ListaDoble:
        def obtener(self):
            return (
                {
                    "version": 1,
                    "generated_at": "2026-09-13T12:00:00+00:00",
                    "product_id": 4903539,
                    "count": 1,
                    "entries": {h: {"estado": "gracia", "hasta": "2026-09-15"}},
                },
                "fresca",
            )

    class _AvisadorDoble:
        def lista_ilegible(self):
            pass

        def lista_vieja(self):
            pass

        def modo_invalido(self):
            pass

        def rechazo_observar(self, correo):
            pass

    acceso._usuario_actual = lambda: {"is_logged_in": True, "email_verified": True, "email": correo}
    acceso._lista_cache_singleton = lambda pat: _ListaDoble()
    acceso._avisador_singleton = lambda token, chat_id: _AvisadorDoble()

    st.session_state["resultado"] = acceso.puerta()


def test_puerta_gracia_muestra_fecha_es():
    at = AppTest.from_function(_script_puerta_gracia)
    at.secrets["auth"] = {}
    at.secrets["acceso"] = {"modo": "aplicar", "hmac_key": CLAVE_SECRETS, "allowlist_pat": "pat-fake"}
    at.run()
    assert at.session_state["resultado"] is True
    assert any("15 de septiembre" in w.value for w in at.warning)


def test_freno_normaliza_correo():
    enviados = []
    avisador = acceso.Avisador(enviar=lambda m: enviados.append(m), ahora=lambda: _dt("2026-09-13T10:00:00+00:00"))
    avisador.rechazo_observar("A@ejemplo.com")
    avisador.rechazo_observar(" a@ejemplo.com ")
    assert len(enviados) == 1


def _script_puerta_sin_hmac_key():
    import streamlit as st

    import acceso

    class _ListaDoble:
        def obtener(self):
            return (
                {
                    "version": 1,
                    "generated_at": "2026-09-13T12:00:00+00:00",
                    "product_id": 4903539,
                    "count": 0,
                    "entries": {},
                },
                "fresca",
            )

    class _AvisadorDoble:
        def lista_ilegible(self):
            pass

        def lista_vieja(self):
            pass

        def modo_invalido(self):
            pass

        def rechazo_observar(self, correo):
            pass

    acceso._usuario_actual = lambda: {
        "is_logged_in": True,
        "email_verified": True,
        "email": "cliente@ejemplo.com",
    }
    acceso._lista_cache_singleton = lambda pat: _ListaDoble()
    acceso._avisador_singleton = lambda token, chat_id: _AvisadorDoble()

    st.session_state["resultado"] = acceso.puerta()


def test_sin_hmac_key_no_bloquea():
    at = AppTest.from_function(_script_puerta_sin_hmac_key)
    at.secrets["auth"] = {}
    at.secrets["acceso"] = {"modo": "aplicar", "allowlist_pat": "pat-fake"}  # sin hmac_key
    at.run()
    assert at.session_state["resultado"] is True
    assert len(at.error) == 0


def test_lista_sin_generated_at_es_invalida():
    lista_sin_fecha = {
        "version": 1,
        "product_id": 4903539,
        "count": 0,
        "entries": {},
    }
    assert acceso._lista_valida(lista_sin_fecha) is False

    lista_fecha_mala = dict(lista_sin_fecha, generated_at="no-es-una-fecha")
    assert acceso._lista_valida(lista_fecha_mala) is False

    lista_ok = dict(lista_sin_fecha, generated_at="2026-09-13T12:00:00+00:00")
    assert acceso._lista_valida(lista_ok) is True


def test_sin_secrets_toml_es_apagado(monkeypatch, tmp_path):
    import streamlit.config as st_config
    from streamlit.runtime.secrets import Secrets

    nonexistent = str(tmp_path / "no-existe-secrets.toml")
    original_get_option = st_config.get_option

    def _fake_get_option(key):
        if key == "secrets.files":
            return [nonexistent]
        return original_get_option(key)

    monkeypatch.setattr(st_config, "get_option", _fake_get_option)
    monkeypatch.setattr(acceso.st, "secrets", Secrets())

    resultado = acceso.puerta()
    assert resultado is True


def test_app_aplicar_sin_sesion_muestra_login():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.secrets["auth"] = {}
    at.secrets["acceso"] = {"modo": "aplicar", "hmac_key": CLAVE_SECRETS, "allowlist_pat": "pat-fake"}
    at.run()
    assert at.title[0].value == "Calculadora de Dividendos · acceso para miembros"
    assert len(at.button) >= 1
    assert at.button[0].label == "Recibir código"


def _script_puerta_modo_ausente():
    import streamlit as st

    import acceso

    avisos = []

    class _ListaDoble:
        def obtener(self):
            return None, "ninguna"

    class _AvisadorDoble:
        def lista_ilegible(self):
            pass

        def lista_vieja(self):
            pass

        def modo_invalido(self):
            avisos.append("modo_invalido")

        def rechazo_observar(self, correo):
            pass

    acceso._usuario_actual = lambda: {"is_logged_in": False}
    acceso._lista_cache_singleton = lambda pat: _ListaDoble()
    acceso._avisador_singleton = lambda token, chat_id: _AvisadorDoble()

    acceso.puerta()
    st.session_state["avisos"] = list(avisos)


def test_modo_ausente_avisa():
    at = AppTest.from_function(_script_puerta_modo_ausente)
    at.secrets["auth"] = {}
    at.secrets["acceso"] = {"allowlist_pat": "pat-fake", "hmac_key": CLAVE_SECRETS}  # sin "modo"
    at.run()
    assert "modo_invalido" in at.session_state["avisos"]


# ============================================================
# Auditoría 2 (fase2-correcciones-2.md): la puerta nunca cierra
# por un fallo técnico
# ============================================================


def test_lista_generated_at_sin_zona_invalida():
    lista_sin_zona = _lista(generated_at="2026-09-13T17:14:48")  # sin offset
    assert acceso._lista_valida(lista_sin_zona) is False


def test_lista_entries_no_dict_invalida():
    lista_mala = {
        "version": 1,
        "generated_at": "2026-09-13T12:00:00+00:00",
        "product_id": 4903539,
        "count": 1,
        "entries": {"x": "vigente"},  # el valor debería ser un dict
    }
    assert acceso._lista_valida(lista_mala) is False

    reloj = {"t": _dt("2026-09-13T12:00:00+00:00")}
    cache = acceso.ListaCache(fetch=lambda: lista_mala, ahora=lambda: reloj["t"])
    lista, origen = cache.obtener()
    assert origen == "ninguna"
    assert lista is None


def test_lista_hasta_mal_formado_invalida():
    h = acceso.hash_correo("cliente@ejemplo.com", CLAVE)
    lista_mala = _lista({h: {"estado": "gracia", "hasta": "15/09"}})
    assert acceso._lista_valida(lista_mala) is False


def _script_puerta_error_interno():
    import streamlit as st

    import acceso

    def _usuario_que_falla():
        raise RuntimeError("boom")

    acceso._usuario_actual = _usuario_que_falla
    class _AvisadorMudo:
        def __getattr__(self, nombre):
            return lambda *args: None

    acceso._avisador_singleton = lambda token, chat_id: _AvisadorMudo()

    st.session_state["resultado"] = acceso.puerta()


def test_puerta_error_interno_abre():
    at = AppTest.from_function(_script_puerta_error_interno)
    at.secrets["auth"] = {}
    at.secrets["acceso"] = {"modo": "aplicar", "hmac_key": CLAVE_SECRETS, "allowlist_pat": "pat-fake"}
    at.run()
    assert len(at.exception) == 0
    assert at.session_state["resultado"] is True


def test_puerta_toml_invalido_abre(monkeypatch, tmp_path):
    import streamlit.config as st_config
    from streamlit.runtime.secrets import Secrets

    archivo_malo = tmp_path / "secrets.toml"
    archivo_malo.write_text("esto no es TOML valido [[[")

    original_get_option = st_config.get_option

    def _fake_get_option(key):
        if key == "secrets.files":
            return [str(archivo_malo)]
        return original_get_option(key)

    monkeypatch.setattr(st_config, "get_option", _fake_get_option)
    monkeypatch.setattr(acceso.st, "secrets", Secrets())

    resultado = acceso.puerta()
    assert resultado is True


def _script_puerta_normal():
    import streamlit as st

    import acceso

    st.session_state["resultado"] = acceso.puerta()


def _script_puerta_doble_stop():
    import streamlit as st

    import acceso

    def _usuario_que_para():
        st.stop()

    acceso._usuario_actual = _usuario_que_para

    st.session_state["antes"] = True
    acceso.puerta()
    st.session_state["nunca_llega"] = True


def test_red_no_traga_rerun():
    at_login = AppTest.from_function(_script_puerta_normal)
    at_login.secrets["auth"] = {}
    at_login.secrets["acceso"] = {"modo": "aplicar", "hmac_key": CLAVE_SECRETS, "allowlist_pat": "pat-fake"}
    at_login.run()
    assert at_login.title[0].value == "Calculadora de Dividendos · acceso para miembros"

    at_stop = AppTest.from_function(_script_puerta_doble_stop)
    at_stop.secrets["auth"] = {}
    at_stop.secrets["acceso"] = {"modo": "aplicar", "hmac_key": CLAVE_SECRETS, "allowlist_pat": "pat-fake"}
    at_stop.run()
    assert at_stop.session_state["antes"] is True
    assert "nunca_llega" not in at_stop.session_state


def _script_puerta_error_con_correo():
    import acceso

    def _usuario_que_falla():
        raise RuntimeError("fallo con a@ejemplo.com adentro")

    acceso._usuario_actual = _usuario_que_falla
    class _AvisadorMudo:
        def __getattr__(self, nombre):
            return lambda *args: None

    acceso._avisador_singleton = lambda token, chat_id: _AvisadorMudo()
    acceso.puerta()


def test_red_no_imprime_mensaje(capsys):
    at = AppTest.from_function(_script_puerta_error_con_correo)
    at.secrets["auth"] = {}
    at.secrets["acceso"] = {"modo": "aplicar", "hmac_key": CLAVE_SECRETS, "allowlist_pat": "pat-fake"}
    at.run()
    capturado = capsys.readouterr()
    assert "a@ejemplo.com" not in capturado.out
    assert "a@ejemplo.com" not in capturado.err


# ============================================================
# Auditoría de privacidad 2026-09-17, S3: el login roto no abre la puerta
# ============================================================

class _AvisadorEspia:
    """Registra cada aviso. Con `lanza_en`, ese aviso falla después de registrarse."""

    def __init__(self, lanza_en=None):
        self.avisos = []
        self._lanza_en = lanza_en

    def __getattr__(self, nombre):
        def _registrar(*args):
            self.avisos.append((nombre,) + args)
            if nombre == self._lanza_en:
                raise RuntimeError("aviso roto")
        return _registrar


class _ListaSinLeer:
    def obtener(self):
        return None, "ninguna"


@pytest.mark.parametrize("lanza_en", [None, "login_roto"])
def test_app_login_roto_no_abre_la_app(monkeypatch, lanza_en):
    """Con Authlib roto (la familia del PR #119) `st.login` lanza StreamlitAuthError. Antes el
    `except` de `puerta()` lo convertía en acceso: un anónimo pulsaba «Recibir código» y
    entraba. Ahora la puerta queda cerrada aunque el aviso a Telegram también falle."""
    import sys

    espia = _AvisadorEspia(lanza_en=lanza_en)
    monkeypatch.setattr(acceso, "_avisador_singleton", lambda token, chat_id: espia)
    monkeypatch.setattr(acceso, "_lista_cache_singleton", lambda pat: _ListaSinLeer())
    monkeypatch.setitem(sys.modules, "authlib", None)

    at = AppTest.from_file("app.py", default_timeout=60)
    at.secrets["auth"] = {}
    at.secrets["acceso"] = {"modo": "aplicar", "hmac_key": CLAVE_SECRETS, "allowlist_pat": "pat-fake"}
    at.run()
    at.button[0].click().run()

    assert len(at.get("file_uploader")) == 0, "la app se abrió a un visitante sin sesión"
    assert any("no está disponible" in e.value for e in at.error)
    assert at.title[0].value == "Calculadora de Dividendos · acceso para miembros"
    assert ("login_roto", "StreamlitAuthError") in espia.avisos


def _script_puerta_error_avisa(lanza):
    import streamlit as st

    import acceso

    avisos = []

    class _Avisador:
        def puerta_abierta_por_error(self, nombre):
            avisos.append(nombre)
            if lanza:
                raise RuntimeError("Telegram caído")

    def _usuario_que_falla():
        raise RuntimeError("fallo con a@ejemplo.com adentro")

    acceso._usuario_actual = _usuario_que_falla
    acceso._avisador_singleton = lambda token, chat_id: _Avisador()
    st.session_state["resultado"] = acceso.puerta()
    st.session_state["avisos"] = avisos


@pytest.mark.parametrize("lanza", [False, True])
def test_puerta_abierta_por_error_avisa_sin_datos(lanza):
    """El fail-open del resto de errores se conserva (decisión 3), pero deja de ser mudo: avisa
    por Telegram con el nombre de la excepción y nada más (el mensaje puede traer un correo)."""
    at = AppTest.from_function(_script_puerta_error_avisa, args=(lanza,))
    at.secrets["auth"] = {}
    at.secrets["acceso"] = {"modo": "aplicar", "hmac_key": CLAVE_SECRETS, "allowlist_pat": "pat-fake"}
    at.run()
    assert len(at.exception) == 0
    assert at.session_state["resultado"] is True
    assert at.session_state["avisos"] == ["RuntimeError"]


def test_avisos_de_puerta_con_freno_6h():
    enviados = []
    reloj = {"t": _dt("2026-09-18T10:00:00+00:00")}
    avisador = acceso.Avisador(enviar=enviados.append, ahora=lambda: reloj["t"])

    avisador.login_roto("StreamlitAuthError")
    avisador.login_roto("StreamlitAuthError")
    avisador.puerta_abierta_por_error("RuntimeError")
    avisador.puerta_abierta_por_error("RuntimeError")
    assert len(enviados) == 2

    reloj["t"] += timedelta(hours=6, seconds=1)
    avisador.login_roto("StreamlitAuthError")
    avisador.puerta_abierta_por_error("RuntimeError")
    assert len(enviados) == 4
    assert all("@" not in mensaje for mensaje in enviados)


# ============================================================
# Auditoría de privacidad 2026-09-17, N1: ?clear no corre antes de la puerta
# ============================================================

def _app_con_espia_de_clear(monkeypatch, secrets):
    import streamlit as st

    llamadas = []
    monkeypatch.setattr(st.cache_data, "clear", lambda: llamadas.append("clear"))
    monkeypatch.setattr(acceso, "_avisador_singleton", lambda token, chat_id: _AvisadorEspia())
    monkeypatch.setattr(acceso, "_lista_cache_singleton", lambda pat: _ListaSinLeer())
    at = AppTest.from_file("app.py", default_timeout=60)
    for clave, valor in secrets.items():
        at.secrets[clave] = valor
    at.query_params["clear"] = "1"
    at.run()
    return at, llamadas


def test_clear_no_vacia_el_cache_con_la_puerta_cerrada(monkeypatch):
    """`?clear` vaciaba el caché de TODOS los usuarios antes de `acceso.puerta()`: cualquier
    visitante sin sesión podía forzar recálculos y re-descargas de Yahoo."""
    at, llamadas = _app_con_espia_de_clear(monkeypatch, {
        "auth": {},
        "acceso": {"modo": "aplicar", "hmac_key": CLAVE_SECRETS, "allowlist_pat": "pat-fake"},
    })
    assert at.title[0].value == "Calculadora de Dividendos · acceso para miembros"
    assert llamadas == [], "un visitante sin sesión vació el caché global"


def test_clear_sigue_funcionando_con_la_puerta_abierta(monkeypatch):
    _, llamadas = _app_con_espia_de_clear(monkeypatch, {})
    assert llamadas == ["clear"]
