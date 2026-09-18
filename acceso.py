"""Puerta de acceso de la Calculadora de Dividendos (Fase 2).

Lógica pura: reloj, red y envío se inyectan. `app.py` solo conecta `puerta()`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Mapping, Optional

import streamlit as st

WHATSAPP_URL = (
    "https://wa.me/573195994689?text=Hola%2C%20pagu%C3%A9%20Vive%20de%20Dividendos%20y%20no"
    "%20puedo%20entrar%20a%20la%20Calculadora.%20Mi%20correo%20de%20compra%20es%3A%20"
)
ENTRENAMIENTO_URL = "https://invierteygana.net/entrenamiento-vive-de-dividendos/"
HOTMART_URL = "https://consumer.hotmart.com"

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

MODOS_VALIDOS = ("aplicar", "observar", "apagado")

PRODUCT_ID_ESPERADO = 4903539


def hash_correo(correo: str, clave: str) -> str:
    normalizado = correo.strip().lower()
    return hmac.new(clave.encode(), normalizado.encode(), hashlib.sha256).hexdigest()


def fecha_es(fecha_iso: str) -> str:
    anio, mes, dia = fecha_iso.split("-")
    return f"{int(dia)} de {MESES[int(mes) - 1]}"


def resolver_modo(secrets: Mapping) -> str:
    if "auth" not in secrets:
        return "apagado"
    acceso = secrets.get("acceso", {})
    modo = acceso.get("modo")
    if modo in MODOS_VALIDOS:
        return modo
    return "observar"


def _lista_valida(lista) -> bool:
    try:
        if not isinstance(lista, dict):
            return False
        if lista.get("version") != 1:
            return False
        if lista.get("product_id") != PRODUCT_ID_ESPERADO:
            return False
        entries = lista.get("entries")
        if not isinstance(entries, dict):
            return False
        if lista.get("count") != len(entries):
            return False
        for datos in entries.values():
            estado = datos.get("estado")
            if estado not in ("vigente", "gracia"):
                return False
            if estado == "gracia":
                date.fromisoformat(datos.get("hasta"))
        generated_at = lista.get("generated_at")
        if not isinstance(generated_at, str):
            return False
        generado = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        if generado.tzinfo is None:
            return False
        return True
    except Exception:
        return False


def lista_vieja(lista, ahora: datetime) -> bool:
    generado = datetime.fromisoformat(lista["generated_at"].replace("Z", "+00:00"))
    return (ahora - generado) > timedelta(hours=24)


class ListaCache:
    def __init__(self, fetch: Callable[[], Optional[dict]], ahora: Callable[[], datetime], ttl_s: int = 1800):
        self._fetch = fetch
        self._ahora = ahora
        self._ttl_s = ttl_s
        self._ultima_buena: Optional[dict] = None
        self._momento_lectura: Optional[datetime] = None
        self._ultimo_intento_fallido: Optional[datetime] = None

    def obtener(self):
        ahora = self._ahora()

        if self._momento_lectura is not None:
            edad = (ahora - self._momento_lectura).total_seconds()
            if edad < self._ttl_s:
                return self._ultima_buena, "cache"

        if self._ultimo_intento_fallido is not None:
            desde_fallo = (ahora - self._ultimo_intento_fallido).total_seconds()
            if desde_fallo < 60:
                if self._ultima_buena is not None:
                    return self._ultima_buena, "ultima_buena"
                return None, "ninguna"

        try:
            nueva = self._fetch()
        except Exception:
            nueva = None

        if nueva is not None and _lista_valida(nueva):
            self._ultima_buena = nueva
            self._momento_lectura = ahora
            self._ultimo_intento_fallido = None
            return self._ultima_buena, "fresca"

        self._ultimo_intento_fallido = ahora
        if self._ultima_buena is not None:
            return self._ultima_buena, "ultima_buena"
        return None, "ninguna"


@dataclass
class Decision:
    accion: str
    gracia_hasta: Optional[str] = None
    correo_rechazado: Optional[str] = None


def decidir(modo: str, usuario: dict, lista: Optional[dict], clave: str) -> Decision:
    if modo == "apagado":
        return Decision(accion="pasar")

    if usuario.get("is_logged_in") is not True:
        return Decision(accion="login")

    if usuario.get("email_verified") is not True:
        if modo == "aplicar":
            return Decision(accion="no_verificado")
        return Decision(accion="pasar", correo_rechazado=usuario.get("email"))

    if lista is None:
        return Decision(accion="pasar")

    correo = usuario.get("email", "")
    h = hash_correo(correo, clave)
    entrada = lista.get("entries", {}).get(h)

    if entrada is None:
        if modo == "aplicar":
            return Decision(accion="rechazar")
        return Decision(accion="pasar", correo_rechazado=correo)

    if entrada.get("estado") == "gracia":
        return Decision(accion="pasar", gracia_hasta=entrada.get("hasta"))

    return Decision(accion="pasar")


def _debe_avisar_rechazo(modo: str, decision: Decision) -> bool:
    return modo == "observar" and decision.correo_rechazado is not None


class Avisador:
    def __init__(self, enviar: Callable[[str], None], ahora: Callable[[], datetime]):
        self._enviar = enviar
        self._ahora = ahora
        self._rechazos_enviados: dict[str, str] = {}
        self._ultimo_por_tipo: dict[str, datetime] = {}

    def _enviar_seguro(self, mensaje: str) -> None:
        try:
            self._enviar(mensaje)
        except Exception:
            pass

    def rechazo_observar(self, correo: str) -> None:
        normalizado = correo.strip().lower()
        ahora = self._ahora()
        hoy = ahora.date().isoformat()
        if self._rechazos_enviados.get(normalizado) == hoy:
            return
        self._rechazos_enviados[normalizado] = hoy
        self._enviar_seguro(f"Rechazo (observar): {correo}")

    def _con_freno_6h(self, tipo: str, mensaje: str) -> None:
        ahora = self._ahora()
        ultimo = self._ultimo_por_tipo.get(tipo)
        if ultimo is not None and (ahora - ultimo) < timedelta(hours=6):
            return
        self._ultimo_por_tipo[tipo] = ahora
        self._enviar_seguro(mensaje)

    def lista_ilegible(self) -> None:
        self._con_freno_6h("lista_ilegible", "La allowlist no se pudo leer.")

    def lista_vieja(self) -> None:
        self._con_freno_6h("lista_vieja", "La allowlist tiene más de 24 h.")

    def modo_invalido(self) -> None:
        self._con_freno_6h("modo_invalido", "El modo de acceso configurado es inválido.")

    def login_roto(self, nombre_error: str) -> None:
        self._con_freno_6h(
            "login_roto",
            f"El login falló ({nombre_error}): la puerta quedó cerrada para quien no tenía sesión.")

    def puerta_abierta_por_error(self, nombre_error: str) -> None:
        self._con_freno_6h("puerta_abierta", f"Puerta ABIERTA por error ({nombre_error}).")


def _fetch_allowlist(pat: str) -> dict:
    request = urllib.request.Request(
        "https://api.github.com/repos/gdeaxx-pixel/iyg-allowlist/contents/allowlist.json",
        headers={
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github.raw",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as respuesta:
        return json.loads(respuesta.read())


def _enviar_telegram(token: str, chat_id: str, mensaje: str) -> None:
    payload = json.dumps({"chat_id": chat_id, "text": mensaje}).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5):
        pass


@st.cache_resource
def _lista_cache_singleton(pat: str) -> ListaCache:
    return ListaCache(fetch=lambda: _fetch_allowlist(pat), ahora=lambda: datetime.now(timezone.utc))


@st.cache_resource
def _avisador_singleton(token: str, chat_id: str) -> Avisador:
    return Avisador(
        enviar=lambda mensaje: _enviar_telegram(token, chat_id, mensaje),
        ahora=lambda: datetime.now(timezone.utc),
    )


def _usuario_actual() -> dict:
    return st.experimental_user.to_dict()


def _pantalla_login(avisador: Avisador) -> None:
    st.title("Calculadora de Dividendos · acceso para miembros")
    st.write(
        "Entra con el correo con el que compraste Vive de Dividendos. "
        "Te enviaremos un código de 6 dígitos."
    )
    if st.button("Recibir código"):
        try:
            st.login("auth0")
        except Exception as e:
            st.error("El acceso no está disponible en este momento. Escríbenos y te ayudamos.")
            st.markdown(f"[Escríbenos por WhatsApp]({WHATSAPP_URL})")
            try:
                avisador.login_roto(type(e).__name__)
            except Exception:
                pass


def _pantalla_rechazo(correo: Optional[str]) -> None:
    st.error(f"Este correo no tiene acceso activo a la Calculadora: {correo}")
    st.write("La Calculadora es para miembros de Vive de Dividendos con la suscripción al día.")
    st.markdown(f"[Conocer Vive de Dividendos]({ENTRENAMIENTO_URL})")
    st.markdown(f"[¿Pagaste y no puedes entrar? Escríbenos por WhatsApp]({WHATSAPP_URL})")
    if st.button("Entrar con otro correo"):
        st.logout()


def _pantalla_no_verificado() -> None:
    st.error("No pudimos verificar tu correo. Vuelve a entrar.")
    if st.button("Entrar con otro correo"):
        st.logout()


def _aviso_gracia(gracia_hasta: str) -> None:
    st.warning(
        f"Tu último pago no se procesó. Actualízalo antes del {fecha_es(gracia_hasta)} "
        "para no perder el acceso.\n\n"
        f"[Regularizar mi pago]({HOTMART_URL}) — Mis compras → Vive de Dividendos → "
        "Regularizar pagos pendientes"
    )


def puerta() -> bool:
    try:
        return _puerta()
    except Exception as e:
        print(f"acceso: puerta abierta por error {type(e).__name__}")
        try:
            acceso_secrets = st.secrets.get("acceso", {})
            _avisador_singleton(
                acceso_secrets.get("telegram_token", ""),
                acceso_secrets.get("telegram_chat_id", ""),
            ).puerta_abierta_por_error(type(e).__name__)
        except Exception:
            pass
        return True


def _puerta() -> bool:
    secrets = st.secrets
    modo = resolver_modo(secrets)
    acceso_secrets = secrets.get("acceso", {})

    clave = acceso_secrets.get("hmac_key", "")
    pat = acceso_secrets.get("allowlist_pat", "")
    token = acceso_secrets.get("telegram_token", "")
    chat_id = acceso_secrets.get("telegram_chat_id", "")

    if "auth" in secrets and acceso_secrets.get("modo") not in MODOS_VALIDOS:
        _avisador_singleton(token, chat_id).modo_invalido()

    if modo == "apagado":
        return True

    usuario = _usuario_actual()
    lista = None
    origen = "ninguna"
    if pat and clave:
        cache = _lista_cache_singleton(pat)
        lista, origen = cache.obtener()

    avisador = _avisador_singleton(token, chat_id)

    if origen == "ninguna":
        avisador.lista_ilegible()
    elif lista is not None and lista_vieja(lista, datetime.now(timezone.utc)):
        avisador.lista_vieja()

    decision = decidir(modo, usuario, lista, clave)

    if _debe_avisar_rechazo(modo, decision):
        avisador.rechazo_observar(decision.correo_rechazado)

    if decision.accion == "login":
        _pantalla_login(avisador)
        return False
    if decision.accion == "no_verificado":
        _pantalla_no_verificado()
        return False
    if decision.accion == "rechazar":
        _pantalla_rechazo(usuario.get("email"))
        return False

    if decision.gracia_hasta is not None:
        _aviso_gracia(decision.gracia_hasta)

    return True
