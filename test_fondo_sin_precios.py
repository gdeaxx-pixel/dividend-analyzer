"""Un fondo cuyo análisis falló por precios no se ofrece ni se dibuja con ceros, y una
cifra de valor que no es un número no tumba los totales de la cuenta.

Cifras sintéticas, inventadas.
"""
import pytest

from test_cascada_eje import STATS_SCHB
from test_total_de_la_cuenta import _stats
from ui import vistas
from ui.adapters import (DatosIncompletos, cashflow_data, fondos_por_categoria,
                         portafolios_data, total_cuenta_data)
from ui.chrome import Ruta
from ui.heredadas import _agregados

_CON = {"net_profit": 1.0}
_FALLO = {"error": "No market data found: x"}
_SIN_VALOR = dict(_stats(500.0, 400.0, 20.0), market_value=float("nan"))


def test_el_fondo_con_fallo_de_precios_no_se_ofrece_en_el_menu():
    res = {"MSTY": _CON, "TSLY": _FALLO, "SCHB": _FALLO, "VOO": _CON}
    assert fondos_por_categoria(res) == {"dividendos": ("MSTY",), "largo": ("VOO",)}


def test_el_recorrido_no_se_arma_con_ceros_si_fallaron_los_precios():
    with pytest.raises(DatosIncompletos):
        cashflow_data(dict(_FALLO), "MSTY")
    assert cashflow_data(STATS_SCHB, "SCHB")["POCKET"] > 0


class _FakeSt:
    def __init__(self, resultados):
        self.out = []
        self.session_state = {"_vd_resultados": resultados}

    def markdown(self, h, **k):
        self.out.append(h)


def _aviso(monkeypatch, resultados, etf):
    fake = _FakeSt(resultados)
    monkeypatch.setattr(vistas, "st", fake)
    monkeypatch.setattr(vistas, "_resultados", lambda: resultados)
    ruta = Ruta(categoria="dividendos", vista="viaje", etf=etf, tema="Claro")
    return vistas._stats_o_aviso(ruta), " ".join(fake.out)


def test_la_pantalla_dice_que_faltan_precios_y_no_que_falta_el_fondo(monkeypatch):
    stats, html = _aviso(monkeypatch, {"MSTY": _FALLO}, "MSTY")
    assert stats is None
    assert "No pudimos traer los precios de MSTY" in html
    assert "no está en tu archivo" not in html


def test_el_fondo_ausente_o_descartado_conserva_su_aviso(monkeypatch):
    for res in ({}, {"MSTY": {"skipped": True}}):
        stats, html = _aviso(monkeypatch, res, "MSTY")
        assert stats is None
        assert "MSTY no está en tu archivo" in html
        assert "precios" not in html


def test_el_fondo_con_datos_pasa_tal_cual(monkeypatch):
    stats, html = _aviso(monkeypatch, {"MSTY": _CON}, "MSTY")
    assert stats is _CON and html == ""


def test_el_nombre_del_fondo_en_el_aviso_va_como_texto(monkeypatch):
    _, html = _aviso(monkeypatch, {}, "<img src=x>")
    assert "<img" not in html and "&lt;img src=x&gt;" in html


def test_un_valor_que_no_es_numero_no_tumba_el_total_de_la_cuenta():
    sano = {"A": _stats(1000.0, 1100.0, 50.0)}
    con = dict(sano, B=_SIN_VALOR)
    assert total_cuenta_data(con) == total_cuenta_data(sano)
    assert total_cuenta_data({"B": _SIN_VALOR}) is None


def test_un_valor_que_no_es_numero_no_entra_a_los_agregados_por_portafolio():
    sano = {"MSTY": _stats(1000.0, 1100.0, 50.0)}
    con = dict(sano, TSLY=_SIN_VALOR)
    assert _agregados(con, ["MSTY", "TSLY"]) == _agregados(sano, ["MSTY"])
    modos = {"MSTY": "mode_a", "TSLY": "mode_a"}
    assert portafolios_data(con, modos) == portafolios_data(sano, {"MSTY": "mode_a"})
