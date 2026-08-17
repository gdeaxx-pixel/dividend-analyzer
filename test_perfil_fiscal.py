"""Perfil fiscal del cliente — red anti-regresión.

Contexto: la retención NRA depende de la residencia del cliente (0% residente US, 10% México,
15% Chile, 30% sin tratado), pero durante todo el port la app la asumió en 30% para todos. La
causa fue **deriva de claves**: `ui/vistas.py` leía `st.session_state["proj_country"]` mientras
el único selector vivo escribía `key="vd_her_proj_country"`. Dos strings distintos, ningún
error, ninguna prueba en rojo — y Comparación · Real quedó clavada en 30% aunque el cliente
declarara México.

Arreglar el string no bastaba: la siguiente vista que necesitara el país lo volvería a leer a
mano. Por eso la clave es privada de `ui/estado.py` y el Tier 1 de este archivo **falla si
cualquier otro módulo vuelve a leer un país desde `st.session_state`**.

Tier 1 (estructural, por AST): nadie se salta el accesor.
Tier 2 (aritmético): el país llega al objeto fiscal, y «sin declarar» no es 0%.
"""
import ast
import os
import sys

import pytest

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import logic  # noqa: E402

_UI = os.path.join(BASE, "ui")
_DUENO = os.path.join(_UI, "estado.py")

# Fragmentos que delatan una clave de sesión con residencia fiscal dentro.
_SOSPECHOSAS = ("country", "pais", "país", "residencia", "perfil_fiscal", "nra_rate")


def _modulos_ui():
    for nombre in sorted(os.listdir(_UI)):
        ruta = os.path.join(_UI, nombre)
        if nombre.endswith(".py") and ruta != _DUENO:
            yield ruta


def _claves_de_session_state(arbol):
    """Toda clave literal con la que un módulo toca `st.session_state`.

    Cubre las tres formas: `st.session_state["x"]`, `st.session_state.get("x")` y
    `st.session_state.pop("x")`.
    """
    claves = []

    def _es_session_state(nodo):
        return (isinstance(nodo, ast.Attribute) and nodo.attr == "session_state"
                and isinstance(nodo.value, ast.Name) and nodo.value.id == "st")

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Subscript) and _es_session_state(nodo.value):
            if isinstance(nodo.slice, ast.Constant) and isinstance(nodo.slice.value, str):
                claves.append((nodo.lineno, nodo.slice.value))
        elif (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
              and nodo.func.attr in ("get", "pop", "setdefault")
              and _es_session_state(nodo.func.value) and nodo.args
              and isinstance(nodo.args[0], ast.Constant)
              and isinstance(nodo.args[0].value, str)):
            claves.append((nodo.lineno, nodo.args[0].value))
    return claves


# ── Tier 1 — nadie se salta el accesor ───────────────────────────────────────


def test_solo_ui_estado_lee_la_residencia_de_session_state():
    """**El test que habría cazado el bug.** Si otra vista vuelve a leer el país por su
    cuenta, la deriva de claves puede repetirse en silencio."""
    culpables = []
    for ruta in _modulos_ui():
        with open(ruta, encoding="utf-8") as f:
            arbol = ast.parse(f.read(), filename=ruta)
        for linea, clave in _claves_de_session_state(arbol):
            if any(frag in clave.lower() for frag in _SOSPECHOSAS):
                culpables.append(f"{os.path.basename(ruta)}:{linea} → {clave!r}")

    assert not culpables, (
        "estos módulos leen la residencia fiscal de session_state por su cuenta en vez de "
        "usar `ui.estado.perfil_fiscal()`; así nació el bug de `proj_country`:\n  "
        + "\n  ".join(culpables))


def test_la_clave_muerta_proj_country_no_reaparece():
    """`proj_country` solo existía en `app_old.py`. Ningún módulo vivo debe volver a leerla."""
    for ruta in list(_modulos_ui()) + [_DUENO, os.path.join(BASE, "app.py")]:
        with open(ruta, encoding="utf-8") as f:
            arbol = ast.parse(f.read(), filename=ruta)
        claves = [c for _, c in _claves_de_session_state(arbol)]
        assert "proj_country" not in claves, f"{os.path.basename(ruta)} revive `proj_country`"


def test_las_vistas_pasan_la_residencia_a_build_tax_summaries():
    """`build_tax_summaries(resultados)` a secas significa «sin declarar»: correcto como
    default del motor, y un bug si lo llama una vista que sí puede leer el perfil. Era
    literalmente la llamada de `_yield_audit`, y por eso la Hoja Excel y la auditoría de
    yield corrían a la tasa por defecto pasara lo que pasara."""
    culpables = []
    for ruta in _modulos_ui():
        with open(ruta, encoding="utf-8") as f:
            arbol = ast.parse(f.read(), filename=ruta)
        for nodo in ast.walk(arbol):
            if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                    and nodo.func.attr == "build_tax_summaries"):
                kw = {k.arg for k in nodo.keywords}
                if "base_rate_pct" not in kw or "country" not in kw:
                    culpables.append(f"{os.path.basename(ruta)}:{nodo.lineno}")
    assert not culpables, (
        "estas vistas llaman build_tax_summaries sin la residencia declarada, así que "
        "muestran la tasa por defecto a todo el mundo:\n  " + "\n  ".join(culpables))


def test_el_copy_no_fija_la_tasa_junto_a_cifras_reales():
    """`ui/heredadas.py` acompaña cifras reales del bróker: fijar «~30%» ahí le miente a un
    residente de México (10%) o de EE.UU. (0%). Los paneles pedagógicos de `metodo.html` sí
    pueden, porque rotulan la cifra como «simulada» / «hasta» / «cota superior»."""
    with open(os.path.join(_UI, "heredadas.py"), encoding="utf-8") as f:
        lineas = f.readlines()
    malas = [f"{i}: {l.strip()[:90]}" for i, l in enumerate(lineas, 1)
             if "30% de impuesto" in l and not l.lstrip().startswith("#")]
    assert not malas, "copy con la tasa cableada junto a cifras reales:\n  " + "\n  ".join(malas)


# ── Tier 2 — la aritmética ───────────────────────────────────────────────────


def test_build_fiscal_profile_sin_pais_no_declara():
    p = logic.build_fiscal_profile()
    assert p["rate_declared"] is False
    assert p["rate_pct"] == logic.RATE_UNDECLARED
    assert p["country"] is None


@pytest.mark.parametrize("pais,tasa,tratado", [
    ("México", 10.0, True),
    ("Chile", 15.0, True),
    ("Colombia", 30.0, False),
    ("Estados Unidos", 0.0, False),
])
def test_build_fiscal_profile_resuelve_pais(pais, tasa, tratado):
    p = logic.build_fiscal_profile(pais)
    assert p["rate_declared"] is True
    assert p["rate_pct"] == pytest.approx(tasa)
    assert p["has_treaty"] is tratado
    assert p["country"] == pais


def test_pais_desconocido_no_cae_al_30_por_ciento():
    """`NRA_COUNTRY_RATES.get(x, (30, False))` convertía cualquier país no listado en 30%
    silencioso. Un país que no conocemos es «sin declarar», no «sin tratado»."""
    p = logic.build_fiscal_profile("Narnia")
    assert p["rate_declared"] is False
    assert p["rate_pct"] == logic.RATE_UNDECLARED


def test_estados_unidos_esta_en_la_tabla():
    """Sin una entrada explícita de 0% no hay forma de declarar residencia fiscal en EE.UU.
    salvo dejándolo «sin declarar», que significa otra cosa."""
    assert logic.NRA_COUNTRY_RATES["Estados Unidos"][0] == 0.0


def test_el_selector_vive_en_el_paso_2_y_escribe_el_perfil():
    """El control tiene que estar donde el cliente carga sus datos, no enterrado en una
    sub-vista. Antes vivía en Detalle → Proyección, dentro de un expander colapsado, y su
    valor no salía de esa función.

    Se ejercita `render_bloque_posiciones` con `AppTest` (mismo patrón que
    `test_carga_1042s.py`): el selectbox debe existir, y elegir un país debe dejar el perfil
    declarado con la tasa del tratado."""
    import pandas as pd
    from streamlit.testing.v1 import AppTest

    script = """
import sys
sys.path.insert(0, {path!r})
from ui.carga import render_bloque_posiciones
render_bloque_posiciones()
""".format(path=BASE)

    ruta = os.path.join(BASE, "fixtures", "schwab_synth_1", "synthetic_transactions.csv")
    if not os.path.exists(ruta):
        pytest.skip("falta el fixture schwab_synth_1")

    at = AppTest.from_string(script)
    at.session_state["_wizard_df_clean"] = logic.normalize_csv(pd.read_csv(ruta))
    at.session_state["_wizard_csv_ticker_data"] = {}
    at.run()

    etiquetas = [s.label for s in at.selectbox]
    assert any("residencia fiscal" in (l or "").lower() for l in etiquetas), (
        f"el selector de residencia no está en el Paso 2; selectboxes presentes: {etiquetas}")

    sel = next(s for s in at.selectbox if "residencia fiscal" in (s.label or "").lower())
    assert sel.value.startswith("—"), "el default tiene que ser «sin declarar»"
    assert "México" in sel.options and "Estados Unidos" in sel.options

    at2 = sel.select("México").run()
    assert at2.session_state["_perfil_fiscal_pais"] == "México"


def test_rate_undeclared_no_es_un_numero():
    """Si el centinela fuera 0 o None, cualquier `float(...)` descuidado lo convertiría en
    una tasa de 0% — el escenario exacto que este diseño evita."""
    assert not isinstance(logic.RATE_UNDECLARED, (int, float))
    assert logic.RATE_UNDECLARED is not None
