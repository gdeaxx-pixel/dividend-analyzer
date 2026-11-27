"""El porcentaje de un fondo con ventas va sobre todo lo comprado (27-nov).

`pocket_investment` es el flujo neto: lo comprado menos lo que devolvió cada venta. Como
base de un porcentaje se encogía con cada venta y hasta cambiaba de signo: comprar 1.000 y
vender todo en 1.500 daba −100 %, y vender casi todo con ganancia daba porcentajes de
cuatro cifras. El resultado en dólares siempre estuvo bien; lo que cambia es el divisor.

Tres cosas vigilan estos guards:

- el motor publica `capital_comprado` y divide por él (`roi_percent`, `yield_on_cost`,
  `cagr`), sin tocar `pocket_investment`;
- la línea de la cuenta y las tarjetas de portafolio suman sobre lo comprado, cuentan lo
  cobrado por ventas dentro de «Tienes hoy» y dejan fuera los fondos «unreliable»;
- una salida de acciones por transferencia sin pareja deja el fondo en «unreliable»: el
  archivo no dice a qué valor salieron, y el resultado la contaría como pérdida.

Los esperados salen de las filas del propio caso, calculados a mano.
"""
import json
import re
from pathlib import Path

import pandas as pd
import pytest

import logic
import ui.heredadas
from ui.adapters import (diagnosticar_bloqueo, portafolios_data, salud_nav_data,
                         total_cuenta_data, vigilar_data)
from ui.heredadas import _agregados, _notas_total_cuenta, _render_total_cuenta

COMPONENTE = (Path(__file__).resolve().parent / "ui" / "componentes"
              / "portafolios.html").read_text(encoding="utf-8")


def _mercado(precios, inicio="2024-01-02"):
    idx = pd.bdate_range(inicio, periods=len(precios))
    return pd.DataFrame({"Close": precios, "Dividends": 0.0, "Stock Splits": 0.0}, index=idx)


def _correr(monkeypatch, filas, mercado, ticker="VTI", **kw):
    df = pd.DataFrame(filas)
    df["Ticker"] = ticker
    df["Date"] = pd.to_datetime(df["Date"])
    for columna in ("Quantity", "Amount", "Price"):
        if columna not in df:
            df[columna] = 0.0
    monkeypatch.setattr(logic, "fetch_market_data", lambda t, d: (mercado.copy(), None))
    monkeypatch.setattr(logic, "_descargar_benchmark", lambda d, ticker="VOO": mercado.copy())
    return logic._analyze_portfolio_sin_cache(df, **kw)[ticker]


COMPRA_10_A_100 = dict(Date="2024-01-02", Action="Buy", Quantity=10, Amount=-1000.0)
COMPRA_100_A_25 = dict(Date="2024-01-02", Action="Buy", Quantity=100, Amount=-2500.0)
SUBE_A_150 = [100.0] * 30 + [150.0] * 240
SUBE_A_30 = [25.0] * 30 + [30.0] * 240


# ── El motor ────────────────────────────────────────────────────────────────────────────

def test_vender_todo_con_ganancia_da_el_porcentaje_de_esa_ganancia(monkeypatch):
    s = _correr(monkeypatch, [COMPRA_10_A_100,
                              dict(Date="2024-03-01", Action="Sell", Quantity=10, Amount=1500.0)],
                _mercado(SUBE_A_150))
    assert s["net_profit"] == pytest.approx(500.0, abs=0.01)
    assert s["capital_comprado"] == pytest.approx(1000.0, abs=0.01)
    assert s["pocket_investment"] == pytest.approx(-500.0, abs=0.01), "el flujo neto no cambia"
    assert s["roi_percent"] == pytest.approx(50.0, abs=0.01)


@pytest.mark.parametrize("vendidas", [0, 20, 50, 70, 90, 100])
def test_el_porcentaje_no_depende_de_cuantas_acciones_vendiste(monkeypatch, vendidas):
    """Compró a 25 y vale 30: ganó el 20 % venda lo que venda a 30. Sobre el flujo neto,
    vender 70 daba 125 % y vender 90 dejaba la base en negativo."""
    filas = [COMPRA_100_A_25]
    if vendidas:
        filas.append(dict(Date="2024-03-01", Action="Sell", Quantity=vendidas,
                          Amount=30.0 * vendidas))
    s = _correr(monkeypatch, filas, _mercado(SUBE_A_30))
    assert s["net_profit"] == pytest.approx(500.0, abs=0.01)
    assert s["roi_percent"] == pytest.approx(20.0, abs=0.01)


def test_lo_comprado_suma_cada_compra_y_no_resta_ninguna_venta(monkeypatch):
    s = _correr(monkeypatch, [COMPRA_100_A_25,
                              dict(Date="2024-02-01", Action="Buy", Quantity=40, Amount=-1100.0),
                              dict(Date="2024-03-01", Action="Sell", Quantity=60, Amount=1800.0)],
                _mercado(SUBE_A_30))
    assert s["capital_comprado"] == pytest.approx(2500.0 + 1100.0, abs=0.01)
    assert s["pocket_investment"] == pytest.approx(2500.0 + 1100.0 - 1800.0, abs=0.01)


@pytest.mark.parametrize("accion", ["Journaled Shares", "Deposit"])
def test_lo_que_entra_con_costo_por_transferencia_o_deposito_tambien_es_comprado(monkeypatch, accion):
    s = _correr(monkeypatch, [COMPRA_100_A_25,
                              dict(Date="2024-02-01", Action=accion, Quantity=20, Amount=-600.0),
                              dict(Date="2024-03-01", Action="Sell", Quantity=30, Amount=900.0)],
                _mercado(SUBE_A_30))
    assert s["capital_comprado"] == pytest.approx(2500.0 + 600.0, abs=0.01)
    assert s["pocket_investment"] == pytest.approx(2500.0 + 600.0 - 900.0, abs=0.01)


def test_sin_ventas_lo_comprado_es_el_capital_aportado(monkeypatch):
    s = _correr(monkeypatch, [COMPRA_100_A_25], _mercado(SUBE_A_30))
    assert s["capital_comprado"] == s["pocket_investment"] == pytest.approx(2500.0, abs=0.01)


def test_el_rendimiento_sobre_costo_va_sobre_lo_comprado(monkeypatch):
    """Cobró 100 en un año y un día sobre 2.500 comprados: ~4 %. Vender la mitad no lo
    duplica."""
    s = _correr(monkeypatch, [
        COMPRA_100_A_25,
        dict(Date="2024-06-03", Action="Dividend", Amount=50.0),
        dict(Date="2024-12-02", Action="Dividend", Amount=50.0),
        dict(Date="2025-01-02", Action="Sell", Quantity=50, Amount=1250.0),
    ], _mercado([25.0] * 300))
    años = 366 / 365.25
    assert s["yield_on_cost"] == pytest.approx(100.0 / años / 2500.0 * 100, abs=0.01)


def test_el_crecimiento_anual_cuenta_lo_cobrado_por_ventas(monkeypatch):
    """Vendió todo en 1.500 lo que compró en 1.000, un año y un día después."""
    s = _correr(monkeypatch, [COMPRA_10_A_100,
                              dict(Date="2025-01-02", Action="Sell", Quantity=10, Amount=1500.0)],
                _mercado([100.0] * 300))
    assert s["cagr"] == pytest.approx((1.5 ** (365.25 / 366) - 1) * 100, abs=0.01)


def test_con_la_captura_del_broker_manda_su_costo_arriba_y_abajo(monkeypatch):
    """Reconciliado: el costo de la captura es el capital aportado y también la base del %."""
    s = _correr(monkeypatch, [COMPRA_10_A_100], _mercado(SUBE_A_150),
                position_overrides={"VTI": {"cost_basis": 1200.0}})
    assert s["pocket_investment"] == s["capital_comprado"] == pytest.approx(1200.0, abs=0.01)
    assert s["roi_percent"] == pytest.approx((1500.0 - 1200.0) / 1200.0 * 100, abs=0.01)


def test_salir_por_transferencia_sin_pareja_deja_el_fondo_poco_fiable(monkeypatch):
    s = _correr(monkeypatch, [COMPRA_10_A_100,
                              dict(Date="2024-02-01", Action="Journaled Shares", Quantity=-4)],
                _mercado([100.0] * 270))
    assert s["acciones_traspasadas_fuera"] == pytest.approx(4.0)
    calidad = logic.assess_ticker_quality({"VTI": s}, "VTI")
    assert calidad["level"] == "unreliable"
    assert calidad["flags"] == ["shares_transferred_out"]
    assert "transferencia" in calidad["reason"]


def test_sin_salidas_por_transferencia_el_fondo_sigue_fiable(monkeypatch):
    """El control del anterior: la misma posición sin la fila de salida, y con una entrada."""
    sola = _correr(monkeypatch, [COMPRA_10_A_100], _mercado([100.0] * 270))
    assert sola["acciones_traspasadas_fuera"] == 0
    assert logic.assess_ticker_quality({"VTI": sola}, "VTI")["level"] == "ok"

    entra = _correr(monkeypatch, [COMPRA_10_A_100,
                                  dict(Date="2024-02-01", Action="Journaled Shares", Quantity=4)],
                    _mercado([100.0] * 270))
    assert entra["acciones_traspasadas_fuera"] == 0
    assert "shares_transferred_out" not in logic.assess_ticker_quality({"VTI": entra}, "VTI")["flags"]


SALEN_10 = dict(Date="2024-02-01", Action="Internal Transfer", Quantity=-10)


@pytest.mark.parametrize("filas", [
    [dict(Date="2024-02-01", Action="Journaled Shares", Quantity=-10),
     dict(Date="2024-02-05", Action="Internal Transfer", Quantity=10)],
    [SALEN_10, dict(Date="2024-02-01", Action="Internal Transfer", Quantity=10)],
    [dict(Date="2024-02-01", Action="Internal Transfer", Quantity=10),
     dict(Date="2024-02-05", Action="Internal Transfer", Quantity=-10)],
], ids=["vuelven otro dia", "salen y vuelven el mismo dia", "entran y luego salen"])
def test_una_ida_y_vuelta_entre_cuentas_no_es_una_salida(monkeypatch, filas):
    """Las diez acciones siguen ahí y costaron lo mismo: compró a 100, valen 150."""
    s = _correr(monkeypatch, [COMPRA_10_A_100] + filas, _mercado(SUBE_A_150))
    assert s["acciones_traspasadas_fuera"] == 0
    assert s["net_profit"] == pytest.approx(500.0, abs=0.01)
    assert logic.assess_ticker_quality({"VTI": s}, "VTI")["level"] == "ok"


def test_el_ajuste_de_una_migracion_no_es_una_salida(monkeypatch):
    """La migración deja la posición en las acciones traspasadas. Si el archivo contaba dos
    de más, quitarlas es una corrección de la cuenta, no acciones que se fueron."""
    s = _correr(monkeypatch, [dict(Date="2024-01-02", Action="Buy", Quantity=12, Amount=-1200.0),
                              dict(Date="2024-02-01", Action="Journaled Shares", Quantity=-10),
                              dict(Date="2024-02-01", Action="Internal Transfer", Quantity=10)],
                _mercado([100.0] * 270))
    assert s["shares"] == pytest.approx(10.0)
    assert s["acciones_traspasadas_fuera"] == 0


def test_las_que_no_vuelven_siguen_siendo_una_salida(monkeypatch):
    s = _correr(monkeypatch, [COMPRA_10_A_100, SALEN_10,
                              dict(Date="2024-02-05", Action="Internal Transfer", Quantity=6)],
                _mercado([100.0] * 270))
    assert s["acciones_traspasadas_fuera"] == pytest.approx(4.0)
    assert logic.assess_ticker_quality({"VTI": s}, "VTI")["level"] == "unreliable"


def test_lo_que_entra_con_costo_no_compensa_la_salida(monkeypatch):
    """Salen las diez de 1.000 y entran otras diez que costaron 1.500: son otra compra. Lo
    comprado sube a 2.500 y las que salieron siguen sin valor declarado."""
    s = _correr(monkeypatch, [COMPRA_10_A_100, SALEN_10,
                              dict(Date="2024-02-05", Action="Internal Transfer",
                                   Quantity=10, Amount=-1500.0)],
                _mercado(SUBE_A_150))
    assert s["capital_comprado"] == pytest.approx(2500.0, abs=0.01)
    assert s["acciones_traspasadas_fuera"] == pytest.approx(10.0)
    assert logic.assess_ticker_quality({"VTI": s}, "VTI")["level"] == "unreliable"


# ── La línea de la cuenta y las tarjetas ────────────────────────────────────────────────

def _stats(comprado, cobrado_ventas, mv, cash=0.0, **extra):
    """Un fondo analizado: compró `comprado`, las ventas le devolvieron `cobrado_ventas`,
    lo que le queda vale `mv` y cobró `cash` de dividendos en efectivo."""
    pocket = comprado - cobrado_ventas
    return {
        "capital_comprado": comprado,
        "pocket_investment": pocket,
        "market_value": mv,
        "dividends_cash_net": cash,
        "dividends_net_total": cash,
        "misc_cash_total": 0.0,
        "net_profit": mv + cash - pocket,
        "shares": 10,
        "current_price": mv / 10,
        **extra,
    }


SIN_VENTA = _stats(1000.0, 0.0, 1100.0, cash=50.0)          # +150
VENDIO_CASI_TODO = _stats(2500.0, 2700.0, 300.0)             # +500, bolsillo −200
POCO_FIABLE = _stats(400.0, 0.0, 5000.0, history_incomplete=True)   # «+4.600»
CUENTA = {"AAA": SIN_VENTA, "BBB": VENDIO_CASI_TODO, "ZZZ": POCO_FIABLE}
CLASES = {"AAA": "mode_a", "BBB": "mode_b", "ZZZ": "mode_b"}


def test_el_fondo_de_prueba_poco_fiable_lo_es():
    assert logic.assess_ticker_quality(CUENTA, "ZZZ")["level"] == "unreliable"
    assert {logic.assess_ticker_quality(CUENTA, t)["level"] for t in ("AAA", "BBB")} == {"ok"}


def test_la_linea_pone_lo_comprado_y_cuenta_lo_cobrado_por_ventas():
    d = total_cuenta_data({"BBB": VENDIO_CASI_TODO})
    assert d["pusiste"] == pytest.approx(2500.0)
    assert d["cobrado_ventas"] == pytest.approx(2700.0)
    assert d["tienes_hoy"] == pytest.approx(300.0 + 2700.0)
    assert d["retorno"] == pytest.approx(500.0)
    assert d["pct"] == pytest.approx(20.0)
    assert d["tienes_hoy"] - d["pusiste"] == pytest.approx(d["retorno"])
    assert d["tienes_hoy_vista"] - d["pusiste_vista"] == d["retorno_vista"]


def test_la_linea_no_cuenta_los_fondos_poco_fiables():
    d = total_cuenta_data(CUENTA)
    assert d["sin_contar"] == ["ZZZ"]
    assert d["fondos"] == 2
    assert d["pusiste"] == pytest.approx(1000.0 + 2500.0)
    assert d["retorno"] == pytest.approx(150.0 + 500.0)
    assert d["pct"] == pytest.approx(650.0 / 3500.0 * 100)


def test_las_tarjetas_suman_lo_mismo_que_la_linea():
    """Dos vistas del mismo resultado: la línea de arriba y la suma de las tarjetas."""
    linea = total_cuenta_data(CUENTA)
    grupos = portafolios_data(CUENTA, CLASES)["grupos"]
    assert sum(g["retorno"] for g in grupos) == pytest.approx(linea["retorno"])
    assert sum(g["invertido"] for g in grupos) == pytest.approx(linea["pusiste"])
    assert sorted(t for g in grupos for t in g["sin_contar"]) == linea["sin_contar"]


def test_el_fondo_poco_fiable_pesa_en_el_reparto_y_no_en_el_resultado():
    crec = next(g for g in portafolios_data(CUENTA, CLASES)["grupos"] if g["clave"] == "crec")
    assert crec["sin_contar"] == ["ZZZ"]
    assert crec["mv"] == pytest.approx(300.0 + 5000.0)
    assert [f["ticker"] for f in crec["fondos"]] == ["ZZZ", "BBB"]
    assert crec["retorno"] == pytest.approx(500.0)
    assert crec["retorno_pct"] == pytest.approx(20.0)


def test_un_fondo_reconciliado_con_la_captura_si_se_cuenta():
    """«unreliable» sale; «reconciled» no: su costo viene del bróker."""
    reconciliado = _stats(1000.0, 0.0, 1300.0, reconciled_from_snapshot=True,
                          history_incomplete=True)
    assert logic.assess_ticker_quality({"REC": reconciliado}, "REC")["level"] == "reconciled"
    d = total_cuenta_data({"REC": reconciliado, "ZZZ": POCO_FIABLE})
    assert d["sin_contar"] == ["ZZZ"] and d["retorno"] == pytest.approx(300.0)


def test_los_agregados_del_grupo_dividen_por_lo_comprado():
    inv, mv, div, tr, pct = _agregados({"BBB": VENDIO_CASI_TODO}, ["BBB"])
    assert (inv, mv, tr) == pytest.approx((2500.0, 300.0, 500.0))
    assert pct == pytest.approx(20.0)


def test_un_grupo_sin_ningun_fondo_medible_lo_dice():
    g = portafolios_data({"ZZZ": POCO_FIABLE}, {"ZZZ": "mode_b"})["grupos"][0]
    assert g["medible"] is False
    assert "no deja medir" in g["veredicto"]
    assert all(x["medible"] is True for x in portafolios_data(CUENTA, CLASES)["grupos"])
    d = total_cuenta_data({"ZZZ": POCO_FIABLE})
    assert d["fondos"] == 0 and d["sin_contar"] == ["ZZZ"]


def test_la_caida_del_precio_se_mide_contra_lo_que_costaron_las_acciones():
    """Compró 2.000, vendió la mitad en 800 y lo que queda vale 700: el precio le quitó 500
    sobre 2.000, el 25 %. Con el costo sin lo cobrado por la venta salía el 42 %."""
    cayo = _stats(2000.0, 800.0, 700.0)
    g = portafolios_data({"BBB": cayo}, {"BBB": "mode_b"})["grupos"][0]
    assert g["precio"] == pytest.approx(-500.0)
    assert "cayó 25%" in g["veredicto"]


def test_la_caida_no_se_diluye_con_el_valor_de_un_fondo_que_no_se_cuenta():
    cayo = _stats(2000.0, 800.0, 700.0)
    g = portafolios_data({"BBB": cayo, "ZZZ": POCO_FIABLE},
                         {"BBB": "mode_b", "ZZZ": "mode_b"})["grupos"][0]
    assert "cayó 25%" in g["veredicto"]


def test_vigilar_da_el_porcentaje_sobre_lo_comprado():
    """Compró 2.000, vendió 800 y pierde 500: −25 %, arriba y en el detalle del yield."""
    vendio = dict(_stats(2000.0, 800.0, 700.0), realized_yield=9.0)
    d = vigilar_data({"VEND": vendio}, {"VEND": {"verdict": "destructive", "nav_cagr": -60.0}})
    fondo = d["fondos"][0]
    assert fondo["retorno_pct"] == "−25.00%"
    del_yield = next(f for f in fondo["flags"] if f["clave"] == "yield")
    assert ["Tu retorno total", "−25.00%", "loss"] in del_yield["tip"]["filas"]


def test_salud_del_fondo_muestra_el_porcentaje_aunque_el_bolsillo_no_sea_positivo():
    liquidado = dict(_stats(1000.0, 1000.0, 300.0), roi_percent=30.0)
    assert liquidado["pocket_investment"] == 0
    assert salud_nav_data("VTI", liquidado)["total_return_pct"] == 30.0
    assert salud_nav_data("VTI", dict(_stats(0.0, 0.0, 300.0), roi_percent=0))["total_return_pct"] is None


# ── Lo que se le dice al cliente ────────────────────────────────────────────────────────

def test_la_nota_dice_que_fondos_no_se_cuentan_y_cuanto_viene_de_ventas():
    nota = _notas_total_cuenta(total_cuenta_data(CUENTA))
    assert "no cuenta ZZZ" in nota
    assert "$2,700" in nota and "cobraste al vender" in nota


def test_sin_nada_que_avisar_no_hay_nota():
    assert _notas_total_cuenta(total_cuenta_data({"AAA": SIN_VENTA})) == ""


def test_el_nombre_del_fondo_llega_escapado_a_la_nota():
    """El ticker viene del archivo del cliente y la nota se pinta como HTML."""
    malo = "<img src=x>"
    nota = _notas_total_cuenta(total_cuenta_data({malo: POCO_FIABLE, "AAA": SIN_VENTA}))
    assert "<img" not in nota and "&lt;img" in nota


def _pintado(monkeypatch, resultados):
    trozos = []
    monkeypatch.setattr(ui.heredadas.st, "markdown", lambda html, **kw: trozos.append(html))
    _render_total_cuenta(resultados)
    return "".join(trozos)


def test_la_linea_se_pinta_con_su_nota_debajo(monkeypatch):
    pintado = _pintado(monkeypatch, CUENTA)
    assert 'class="vd-cuenta"' in pintado
    assert pintado.index('class="vd-cuenta"') < pintado.index("no cuenta ZZZ")


def test_si_ningun_fondo_se_puede_medir_no_hay_cifras_solo_el_aviso(monkeypatch):
    pintado = _pintado(monkeypatch, {"ZZZ": POCO_FIABLE})
    assert 'class="vd-cuenta"' not in pintado and "Pusiste" not in pintado
    assert "no cuenta ZZZ" in pintado


def test_la_tarjeta_avisa_de_los_fondos_que_no_cuenta():
    etiqueta = re.search(r"'<p class=\"k\">Retorno total'[^\n]*", COMPONENTE).group(0)
    assert "sinContar(g)" in etiqueta
    funcion = COMPONENTE[COMPONENTE.index("const sinContar ="):COMPONENTE.index("const rows = filas(g)")]
    assert "grupo.sin_contar" in funcion
    assert "fuera.map(esc)" in funcion, "el ticker viene del archivo del cliente"


_TARJETAS = """() => [...document.querySelectorAll('.card')].map(c => ({
  titulo: c.querySelector('.card-title').textContent,
  cifra: c.querySelector('.big').textContent,
  apagada: !!c.querySelector('.big .num.sin-medir'),
  filas: c.querySelectorAll('.wf-row').length,
  etiqueta: c.querySelector('p.k').textContent,
  veredicto: c.querySelector('.verdict').textContent,
}))"""


def test_la_tarjeta_de_un_grupo_sin_fondos_medibles_no_pinta_un_cero():
    """Con Chromium: el grupo de Crecimiento solo tiene un fondo poco fiable. Un «+$0» en
    verde con su cascada sería una cifra que nadie midió."""
    sync_api = pytest.importorskip("playwright.sync_api")
    from ui import componentes
    datos = portafolios_data({"AAA": SIN_VENTA, "ZZZ": POCO_FIABLE},
                             {"AAA": "mode_a", "ZZZ": "mode_b"})
    html = componentes._con_tema(componentes._plantilla("portafolios.html"), "Claro")
    html = html.replace("{{DATA_JSON}}", json.dumps(datos, ensure_ascii=False))
    try:
        with sync_api.sync_playwright() as pw:
            nav = pw.chromium.launch()
            pagina = nav.new_page(viewport={"width": 1000, "height": 1400})
            pagina.set_content("<!doctype html>" + html)
            pagina.wait_for_timeout(300)
            tarjetas = {t["titulo"]: t for t in pagina.evaluate(_TARJETAS)}
            nav.close()
    except sync_api.Error as e:
        pytest.skip(f"Chromium no disponible: {e}")
    sin, con = tarjetas["Crecimiento"], tarjetas["Dividendos"]
    assert sin["cifra"] == "Sin medir" and sin["apagada"] and sin["filas"] == 0
    assert sin["etiqueta"] == "Retorno total · sin ZZZ"
    assert "no deja medir" in sin["veredicto"]
    assert con["filas"] == 3 and not con["apagada"]
    assert "150" in con["cifra"] and "15" in con["cifra"], "ganó 150 sobre 1.000"
    assert con["etiqueta"] == "Retorno total"


FALLO_BOLSILLO = ["bolsillo negativo: -200.00"]


def test_un_bolsillo_negativo_por_ventas_con_ganancia_no_culpa_al_archivo():
    aviso = diagnosticar_bloqueo({"POCKET": -200.0}, VENDIO_CASI_TODO, FALLO_BOLSILLO)
    assert "faltan filas" not in aviso["titular"]
    assert "$2,500.00" in aviso["cuerpo"][0] and "$2,700.00" in aviso["cuerpo"][0]
    assert aviso["nuestro"] is False


@pytest.mark.parametrize("stats", [
    dict(VENDIO_CASI_TODO, history_incomplete=True),
    _stats(0.0, 200.0, 300.0),
])
def test_un_bolsillo_negativo_sin_las_compras_sigue_culpando_al_archivo(stats):
    """Vendió más de lo que figura comprado, o no figura ninguna compra: ahí sí falta historia."""
    aviso = diagnosticar_bloqueo({"POCKET": -200.0}, stats, FALLO_BOLSILLO)
    assert "faltan filas" in aviso["titular"]


def test_con_otro_descuadre_ademas_del_bolsillo_el_aviso_no_cambia():
    fallos = ["neto = reinvertido + efectivo: 137.29 ≠ 583.76"] + FALLO_BOLSILLO
    aviso = diagnosticar_bloqueo({"POCKET": -200.0}, VENDIO_CASI_TODO, fallos)
    assert "faltan filas" in aviso["titular"]
