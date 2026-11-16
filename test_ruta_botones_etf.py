"""Ruta con botones directos de ETF (Daniel 2026-09-29).

En Dividendos y Largo Plazo el ETF ya no es un popover con la lista fija de `nav.CATS`:
son botones con SOLO los tickers que el archivo trae con datos. Una categoría sin ninguno
se oculta del menú, y un ETF que no está en el archivo cae al primero habilitado — antes
se aterrizaba en «MSTY no está en tu archivo»."""

import os

from streamlit.testing.v1 import AppTest

from ui import chrome
from ui.chrome import etfs_habilitados

_RAIZ = os.path.dirname(os.path.abspath(__file__))

_SCRIPT = """
import sys
sys.path.insert(0, {path!r})
import streamlit as st
from ui.chrome import render_ruta
r = render_ruta(False, st.session_state.get("_hab"))
st.session_state["_ruta"] = (r.categoria, r.etf)
"""


def _app(**estado) -> AppTest:
    at = AppTest.from_string(_SCRIPT.format(path=_RAIZ), default_timeout=25)
    for clave, valor in estado.items():
        at.session_state[clave] = valor
    at.run()
    assert at.exception == []
    return at


def test_etfs_habilitados_solo_los_del_archivo_con_datos():
    resultados = {"TSLY": {"net_profit": 1}, "CONY": {"skipped": True}, "NVDY": {},
                  "SCHB": {"net_profit": 2}, "JEPI": {"net_profit": 3}}
    # Desde P3 (30-oct) entran también los fondos fuera de la lista fija, detrás de ella:
    # JEPI es de largo plazo para `classify_tickers`.
    assert etfs_habilitados(resultados) == {"dividendos": ("TSLY",), "largo": ("SCHB", "JEPI")}


def test_botones_solo_habilitados_y_etf_invalido_cae_al_primero():
    at = _app(_hab={"dividendos": ("TSLY", "NVDY"), "largo": ("SCHB",)},
              vd_categoria="dividendos", vd_etf_dividendos="MSTY")
    grupo = at.button_group(key="vd_etf_w_dividendos")
    assert list(grupo.options) == ["TSLY", "NVDY"]
    assert grupo.value == "TSLY"
    assert at.session_state["_ruta"] == ("dividendos", "TSLY")


def test_elegir_boton_cambia_el_etf():
    at = _app(_hab={"dividendos": ("TSLY", "NVDY"), "largo": ("SCHB",)},
              vd_categoria="dividendos")
    at.button_group(key="vd_etf_w_dividendos").set_value("NVDY").run()
    assert at.session_state["vd_etf_dividendos"] == "NVDY"
    assert at.session_state["_ruta"] == ("dividendos", "NVDY")


def test_deseleccionar_el_activo_conserva_el_etf():
    at = _app(_hab={"dividendos": ("TSLY", "NVDY"), "largo": ("SCHB",)},
              vd_categoria="dividendos", vd_etf_dividendos="NVDY")
    at.button_group(key="vd_etf_w_dividendos").set_value(None).run()
    assert at.session_state["_ruta"] == ("dividendos", "NVDY")
    assert at.button_group(key="vd_etf_w_dividendos").value == "NVDY"


def test_con_fondos_en_un_solo_grupo_la_seccion_sigue_en_el_menu():
    # Desde el 30-oct (P1) las secciones son una fila visible, no un popover; desde el
    # 14-nov (Q3) los dos grupos de fondos son UNA entrada, «Fondo por fondo».
    at = _app(_hab={"dividendos": ("TSLY",), "largo": ()}, vd_categoria="dividendos")
    secciones = list(at.button_group(key="vd_cat_w").options)   # etiquetas visibles
    assert chrome.LABEL_FONDOS in secciones
    assert "Dividendos" not in secciones and "Largo Plazo" not in secciones


def test_un_grupo_vacio_pasa_al_otro_sin_echarte_de_la_seccion():
    """Antes, con el grupo activo vacío, se salía a Portafolios. Ahora el menú no
    distingue los dos grupos, así que quedarse es lo que espera el cliente."""
    at = _app(_hab={"dividendos": ("TSLY",), "largo": ()}, vd_categoria="largo")
    assert at.session_state["_ruta"] == ("dividendos", "TSLY")


def test_sin_fondos_en_ninguno_de_los_dos_vuelve_a_portafolios():
    at = _app(_hab={"dividendos": (), "largo": ()}, vd_categoria="largo")
    assert at.session_state["_ruta"] == ("detalle", None)
    assert chrome.LABEL_FONDOS not in list(at.button_group(key="vd_cat_w").options)
