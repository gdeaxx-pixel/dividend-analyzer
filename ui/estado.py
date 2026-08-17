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

    `source` documenta de dónde salió: 'manual' (el cliente lo eligió) o '1042s' (detectado
    del formulario y confirmado por él). Nunca se escribe sin que el cliente confirme.
    """
    if country in logic.NRA_COUNTRY_RATES:
        st.session_state[_CLAVE_PAIS] = country
        st.session_state[_CLAVE_FUENTE] = source
    else:
        st.session_state.pop(_CLAVE_PAIS, None)
        st.session_state.pop(_CLAVE_FUENTE, None)


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
