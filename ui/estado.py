"""Estado de sesión compartido entre vistas — dueño único de las claves que cruzan módulos.

**Por qué existe este módulo.** El perfil fiscal se rompió por deriva de claves: `ui/vistas.py`
leía `st.session_state["proj_country"]` mientras el único selector vivo escribía
`key="vd_her_proj_country"`. Dos strings distintos, ningún error, ninguna prueba en rojo — y
Comparación · Real quedó clavada en 30% para todos los clientes, incluidos los que declaraban
México. El bug sobrevivió al port completo de la app.

Arreglar el string no habría bastado: la siguiente vista que necesitara el país volvería a
escribir la clave a mano. Por eso la clave es **privada de este módulo** y el acceso pasa por
funciones. Un test estructural (`test_perfil_fiscal.py`) falla si cualquier otro módulo vuelve a
leer una clave de país desde `st.session_state`.

Mismo principio que el objeto fiscal único (Regla 3 de `specs/roc-nra-invariants.md`): una sola
fuente, las vistas la LEEN, ninguna la reconstruye.
"""

from __future__ import annotations

import streamlit as st

import logic

# Clave privada. Nadie fuera de este módulo debe escribirla ni leerla — usa las funciones.
_CLAVE_PAIS = "_perfil_fiscal_pais"
_CLAVE_FUENTE = "_perfil_fiscal_fuente"
_CLAVE_SUBIR = "_vd_subir_al_inicio"
_CLAVE_RUTAS = "_vd_rutas_propias"


def pedir_subir_al_inicio() -> None:
    """La pide «Ver resultados →» (`ui.carga`): Streamlit conserva el desplazamiento de la
    hoja de carga y los resultados abrían bajados, con el menú fuera de la vista (A5 de la
    propuesta del 2026-10-30). La consume la cabecera de resultados (`ui.chrome`)."""
    st.session_state[_CLAVE_SUBIR] = True


def consumir_subir_al_inicio() -> bool:
    """True una sola vez por cada `pedir_subir_al_inicio`."""
    return bool(st.session_state.pop(_CLAVE_SUBIR, False))


def ya_ofrece_a_donde_ir() -> None:
    """La pide una vista que ya propone sus propios caminos —hoy «Para entenderlo a fondo»
    de Portafolios (`ui.heredadas`)— para que el pie no añada un segundo «Siguiente»
    debajo diciendo otra cosa. La consume `ui.chrome.render_siguiente` en la misma
    corrida."""
    st.session_state[_CLAVE_RUTAS] = True


def consumir_ofrece_a_donde_ir() -> bool:
    """True una sola vez por cada `ya_ofrece_a_donde_ir`."""
    return bool(st.session_state.pop(_CLAVE_RUTAS, False))


# Zonas horarias del navegador por país de la lista de la app (`logic.NRA_COUNTRY_RATES`).
# Solo las que identifican un país sin ambigüedad; lo que no esté aquí no se sugiere.
_TZ_PAIS = {
    "America/Bogota": "Colombia",
    "America/Mexico_City": "México", "America/Tijuana": "México",
    "America/Monterrey": "México", "America/Cancun": "México",
    "America/Merida": "México", "America/Chihuahua": "México",
    "America/Hermosillo": "México", "America/Mazatlan": "México",
    "America/Matamoros": "México", "America/Ojinaga": "México",
    "America/Santiago": "Chile", "Pacific/Easter": "Chile",
    "America/Punta_Arenas": "Chile",
    "America/Caracas": "Venezuela",
    "Europe/Madrid": "España", "Atlantic/Canary": "España", "Africa/Ceuta": "España",
    "America/Lima": "Perú",
    "America/Sao_Paulo": "Brasil", "America/Bahia": "Brasil",
    "America/Fortaleza": "Brasil", "America/Recife": "Brasil",
    "America/Manaus": "Brasil", "America/Belem": "Brasil",
    "America/New_York": "Estados Unidos", "America/Chicago": "Estados Unidos",
    "America/Denver": "Estados Unidos", "America/Los_Angeles": "Estados Unidos",
    "America/Phoenix": "Estados Unidos", "America/Anchorage": "Estados Unidos",
    "America/Detroit": "Estados Unidos", "Pacific/Honolulu": "Estados Unidos",
    # El resto de América Latina cae en la entrada que la app ya tiene para ellos.
    "America/Guayaquil": "Otros LATAM", "America/La_Paz": "Otros LATAM",
    "America/Asuncion": "Otros LATAM", "America/Montevideo": "Otros LATAM",
    "America/Panama": "Otros LATAM", "America/Costa_Rica": "Otros LATAM",
    "America/Guatemala": "Otros LATAM", "America/El_Salvador": "Otros LATAM",
    "America/Tegucigalpa": "Otros LATAM", "America/Managua": "Otros LATAM",
    "America/Santo_Domingo": "Otros LATAM", "America/Havana": "Otros LATAM",
    "America/Puerto_Rico": "Otros LATAM", "America/Port-au-Prince": "Otros LATAM",
}
# Argentina reparte sus provincias en `America/Argentina/<ciudad>`: se resuelven por prefijo.
_TZ_PREFIJO_PAIS = (("America/Argentina/", "Argentina"),)
# Si el navegador no da zona horaria, queda el idioma con región (`es-CO`, `pt-BR`).
_LOCALE_PAIS = {
    "CO": "Colombia", "MX": "México", "CL": "Chile", "VE": "Venezuela", "ES": "España",
    "PE": "Perú", "AR": "Argentina", "BR": "Brasil", "US": "Estados Unidos",
    "EC": "Otros LATAM", "BO": "Otros LATAM", "PY": "Otros LATAM", "UY": "Otros LATAM",
    "PA": "Otros LATAM", "CR": "Otros LATAM", "GT": "Otros LATAM", "SV": "Otros LATAM",
    "HN": "Otros LATAM", "NI": "Otros LATAM", "DO": "Otros LATAM", "CU": "Otros LATAM",
    "PR": "Otros LATAM",
}


def pais_sugerido(timezone: str | None, locale: str | None) -> str | None:
    """El país desde donde PARECE que se conecta el cliente, o `None` si no se puede decir.

    Función pura: la vista le pasa lo que el navegador reportó (`st.context.timezone` y
    `st.context.locale`) y aquí no se toca ni la red ni la IP. La zona horaria manda sobre
    el idioma: un navegador en inglés en Bogotá sigue estando en Bogotá.

    **Esto NO declara nada.** Dónde te conectas no es dónde tributas, y de la residencia
    cuelga la retención con derecho. La sugerencia se ofrece y el cliente la confirma.
    """
    import logic

    tz = (timezone or "").strip()
    if tz in _TZ_PAIS:
        pais = _TZ_PAIS[tz]
    else:
        pais = next((p for pref, p in _TZ_PREFIJO_PAIS if tz.startswith(pref)), None)
    if pais is None:
        # Solo vale el idioma que trae REGIÓN: con «es» a secas, partir por el guion
        # devolvía «ES» y un navegador en español genérico salía como España.
        partes = (locale or "").replace("_", "-").split("-")
        region = partes[-1].upper() if len(partes) >= 2 else ""
        pais = _LOCALE_PAIS.get(region) if len(region) == 2 else None
    # Un país que la app no sabe tasar no se puede sugerir: el botón declararía algo que
    # `declarar_pais` descartaría en silencio.
    return pais if pais in logic.NRA_COUNTRY_RATES else None


def perfil_fiscal() -> dict:
    """Perfil fiscal vigente del cliente. Siempre devuelve un dict válido.

    Sin país declarado: `rate_declared=False` y `rate_pct=logic.RATE_UNDECLARED` — las vistas
    no deben estimar devolución con eso (ver el centinela en `logic.py`).
    """
    return logic.build_fiscal_profile(
        country=st.session_state.get(_CLAVE_PAIS),
        source=st.session_state.get(_CLAVE_FUENTE),
    )


def declarar_pais(country: str | None, source: str = "manual") -> None:
    """Declara la residencia fiscal. `country=None` la borra (vuelve a «sin declarar»).

    `source` documenta de dónde salió: 'manual' (el cliente lo eligió), '1042s' (detectado
    del formulario y confirmado por él) o 'navegador' (sugerido por la zona horaria y
    confirmado con un clic, A4). Nunca se escribe sin que el cliente confirme.
    """
    if country in logic.NRA_COUNTRY_RATES:
        st.session_state[_CLAVE_PAIS] = country
        st.session_state[_CLAVE_FUENTE] = source
    else:
        st.session_state.pop(_CLAVE_PAIS, None)
        st.session_state.pop(_CLAVE_FUENTE, None)


def reflejar_en_selector(clave: str, opciones: list, sin_declarar: str) -> None:
    """Antes de dibujar el selector de residencia, iguala su valor al perfil. Solo escribe
    si difieren: así el perfil declarado por otra vía (el botón del 1042-S) llega al
    navegador (`set_value`) y un selector con `key` no lo pisa con su valor viejo."""
    pais = perfil_fiscal()["country"]
    esperado = pais if pais in opciones else sin_declarar
    if st.session_state.get(clave) != esperado:
        st.session_state[clave] = esperado


def declarar_desde_selector(clave: str, sin_declarar: str) -> None:
    """`on_change` del selector: corre antes del script, así que todo lo que se dibuja
    arriba del selector (la dona) ya ve el país nuevo en ese mismo render."""
    elegido = st.session_state.get(clave)
    declarar_pais(None if elegido == sin_declarar else elegido)


def tasa_y_pais() -> tuple:
    """`(base_rate_pct, country)` listos para `logic.build_tax_summaries(...)`.

    Con el perfil sin declarar devuelve `(logic.RATE_UNDECLARED, None)` — que es justo lo que
    hace que el objeto fiscal no invente una devolución.
    """
    p = perfil_fiscal()
    return (p["rate_pct"] if p["rate_declared"] else logic.RATE_UNDECLARED), p["country"]


def tasa_para_motor() -> float:
    """Tasa en fracción [0,1] para `backtest.run_backtest(nra_rate=...)`.

    Sin declarar → 0.0 (bruto). Es el único sitio donde «sin declarar» colapsa a cero, y es
    correcto: el motor necesita un número para simular, y reinvertir el dividendo íntegro es
    el supuesto neutro que ya medía la versión anterior. La vista que lo use debe ROTULARLO
    como bruto — no presentarlo como la cifra neta del cliente.
    """
    p = perfil_fiscal()
    return (float(p["rate_pct"]) / 100.0) if p["rate_declared"] else 0.0
