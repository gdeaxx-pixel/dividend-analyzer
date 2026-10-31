"""P3 de la propuesta de interfaz (2026-10-30): Dividendos y Largo plazo ofrecen todos los
fondos del archivo, no solo la lista fija del artifact.

En el caso de IB hay 6 fondos de dividendos: Portafolios y «Lo que toca vigilar» mostraban los
6, pero Dividendos solo ofrecía MSTY, TSLY, NVDY y CONY. PLTY y NFLY no tenían dónde abrirse, y
un cliente con ULTY o VOO no veía esos fondos en el menú. El 29-sep se decidió así porque se
creía que Cash flow solo sabía dibujar la lista fija; medido el 30-oct, `cashflow_data` solo lee
los `stats` del fondo.

Cifras sintéticas, inventadas.
"""
import os

from streamlit.testing.v1 import AppTest

from test_vigilar_data import DEST
from ui.adapters import cashflow_data, fondos_por_categoria, vigilar_data
from ui.chrome import etfs_habilitados

_RAIZ = os.path.dirname(os.path.abspath(__file__))
_CON = {"net_profit": 1.0}

# MSTY, TSLY y CONY de la lista fija (que no va en orden alfabético); PLTY y NFLY YieldMax fuera
# de ella; SCHB fija de largo plazo; VOO de largo plazo fuera de la lista; AAPL no es un fondo;
# XLK sin datos (menos de 14 días).
_RES = {"PLTY": _CON, "CONY": _CON, "MSTY": _CON, "NFLY": _CON, "TSLY": _CON, "VOO": _CON,
        "SCHB": _CON, "AAPL": _CON, "XLK": {"skipped": True}}


def test_todos_los_fondos_del_archivo_con_la_lista_fija_primero():
    assert fondos_por_categoria(_RES) == {
        "dividendos": ("MSTY", "TSLY", "CONY", "NFLY", "PLTY"),
        "largo": ("SCHB", "VOO"),
    }


def test_la_ruta_usa_la_misma_lista():
    assert etfs_habilitados(_RES) == fondos_por_categoria(_RES)


def test_sin_resultados_no_hay_fondos():
    assert fondos_por_categoria({}) == {"dividendos": (), "largo": ()}
    assert fondos_por_categoria(None) == {"dividendos": (), "largo": ()}


_SCRIPT = """
import sys
sys.path.insert(0, {path!r})
import streamlit as st
from ui.chrome import etfs_habilitados, render_ruta
r = render_ruta(False, etfs_habilitados(st.session_state["_res"]))
st.session_state["_ruta"] = (r.categoria, r.etf)
"""


def test_un_fondo_fuera_de_la_lista_se_elige_en_la_ruta():
    at = AppTest.from_string(_SCRIPT.format(path=_RAIZ), default_timeout=25)
    at.session_state["_res"] = _RES
    at.session_state["vd_categoria"] = "dividendos"
    at.run()
    assert at.exception == []
    grupo = at.button_group(key="vd_etf_w_dividendos")
    assert list(grupo.options) == ["MSTY", "TSLY", "CONY", "NFLY", "PLTY"]
    grupo.set_value("PLTY").run()
    assert at.session_state["_ruta"] == ("dividendos", "PLTY")


def test_cash_flow_no_depende_de_la_lista_fija():
    """El motivo del 29-sep, medido: los mismos `stats` dan el mismo recorrido con cualquier
    ticker; solo cambia el rótulo."""
    msty = cashflow_data(dict(DEST), "MSTY")
    plty = cashflow_data(dict(DEST), "PLTY")
    assert plty["ticker"] == "PLTY"
    assert {k: v for k, v in plty.items() if k != "ticker"} == \
           {k: v for k, v in msty.items() if k != "ticker"}


def test_vigilar_manda_al_cash_flow_de_un_fondo_fuera_de_la_lista():
    d = vigilar_data({"PLTY": dict(DEST)}, {"PLTY": {"verdict": "destructive", "nav_cagr": -50.0}})
    cubre = next(f for f in d["fondos"][0]["flags"] if f["clave"] == "cubre")
    assert cubre["ruta"] == "viaje"
    assert cubre["tip"]["ruta"] == "Dividendos › PLTY"
    viaje = next(r for r in d["rutas"] if r["clave"] == "viaje")
    assert (viaje["etiqueta"], viaje["etf"]) == ("Dividendos › PLTY", "PLTY")


def test_un_ticker_que_no_es_fondo_no_entra_en_ninguna_categoria():
    assert fondos_por_categoria({"AAPL": _CON, "DEST": _CON}) == {"dividendos": (), "largo": ()}
