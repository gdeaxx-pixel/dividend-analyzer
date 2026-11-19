"""A1 — la línea de la cuenta, arriba de los resultados (18-nov).

Antes había que sumar mentalmente las dos tarjetas de portafolio para saber cómo va la
cuenta entera. Ahora los resultados abren con tres cifras: lo que pusiste, lo que tienes
hoy y la diferencia.

Auditado con `/auditoria-financiera` ANTES de escribirla (módulo M1). Lo medido sobre los
tres casos reales:

- `(market_value + dividends_cash_net + misc_cash_total) − pocket_investment ==
  net_profit` al centavo en los tres.
- Usar `dividends_net_total` —el objeto FISCAL, que incluye los dividendos reinvertidos,
  ya dentro de `market_value` en forma de acciones— habría duplicado el DRIP: +$6.211,39 y
  +$269,92 en los dos casos de Schwab, 0 en el de IB. Ese es el error que estos guards
  vigilan.
- `gross_value` no se publica en las stats (0 de 21 tickers): la caja se suma de sus tres
  campos.
"""
import re
from pathlib import Path

from ui.adapters import portafolios_data, total_cuenta_data


def _stats(inv, mv, cash, neto=None, misc=0.0):
    """Un ticker analizado. `neto` es el objeto fiscal (con lo reinvertido); `cash`, el
    efectivo que de verdad entró."""
    return {
        "pocket_investment": inv,
        "market_value": mv,
        "dividends_cash_net": cash,
        "dividends_net_total": neto if neto is not None else cash,
        "misc_cash_total": misc,
        "net_profit": mv + cash + misc - inv,
        "shares": 10,
        "current_price": mv / 10 if mv else 0,
    }


# Un portafolio con DRIP: cobró 900 pero solo 100 quedaron en efectivo; los otros 800
# compraron acciones que ya están dentro de `market_value`.
CON_DRIP = {"MSTY": _stats(1000.0, 1200.0, 100.0, neto=900.0)}


def test_sin_fondos_con_datos_no_hay_linea():
    assert total_cuenta_data({}) is None
    assert total_cuenta_data({"MSTY": {"skipped": True}}) is None


def test_las_tres_cifras_cierran_entre_si():
    d = total_cuenta_data({"A": _stats(1000.0, 1100.0, 50.0), "B": _stats(500.0, 400.0, 20.0)})
    assert d["tienes_hoy"] - d["pusiste"] == d["retorno"]


def test_el_retorno_es_el_mismo_que_calcula_el_motor():
    """`net_profit` llega por otra ruta: si la línea lo recalculara mal, aquí se separa.

    Uno de los tres fondos tiene DRIP a propósito: sin él, el fixture no distingue el
    objeto fiscal del efectivo y el test sobrevive al mutante que los confunde — medido.
    """
    res = {"A": _stats(1000.0, 1100.0, 50.0), "B": _stats(500.0, 400.0, 20.0, misc=7.5),
           "C": _stats(900.0, 1500.0, 120.0, neto=640.0)}
    d = total_cuenta_data(res)
    motor = sum(s["net_profit"] for s in res.values())
    assert abs(d["retorno"] - motor) < 1e-9
    # Y la identidad entera, que es la que medí en los casos reales: comparar `retorno`
    # con `net_profit` a secas es compararlo consigo mismo —sale de ahí— y deja pasar un
    # «tienes hoy» mal armado. Medido: ese mutante sobrevivía.
    assert abs((d["tienes_hoy"] - d["pusiste"]) - motor) < 1e-9


def test_el_dividendo_reinvertido_no_se_cuenta_dos_veces():
    """EL guard de la auditoría. Con DRIP, el objeto fiscal trae 900 y en caja solo hay
    100: las otras 800 ya están en el valor de las acciones. Sumar el fiscal daría
    $2,100 de «tienes hoy» en vez de $1,300."""
    d = total_cuenta_data(CON_DRIP)
    assert d["tienes_hoy"] == 1300.0, d
    assert d["retorno"] == 300.0
    assert d["tienes_hoy"] != 1200.0 + 900.0


def test_el_efectivo_que_no_es_dividendo_tambien_esta_en_la_caja():
    """`misc_cash_total` (Cash In Lieu y compañía) es dinero que está en la cuenta y va
    como sumando propio desde el 2026-09-24."""
    sin = total_cuenta_data({"A": _stats(100.0, 100.0, 0.0)})
    con = total_cuenta_data({"A": _stats(100.0, 100.0, 0.0, misc=12.0)})
    assert con["tienes_hoy"] - sin["tienes_hoy"] == 12.0
    assert con["retorno"] - sin["retorno"] == 12.0


def test_el_capital_aportado_entra_tal_cual():
    """Regla 1 del contrato: el capital aportado es invariante; la línea no lo ajusta."""
    d = total_cuenta_data({"A": _stats(1234.56, 0.0, 0.0)})
    assert d["pusiste"] == 1234.56


def test_lo_que_se_muestra_tambien_cierra_al_redondear():
    """Redondear las tres por separado descuadra la resta que el cliente hace de cabeza:
    medido en la app, $8,066 + $3,207 contra un «tienes hoy» de $11,274."""
    d = total_cuenta_data({"A": _stats(8065.6, 10774.9, 499.3)})
    assert d["pusiste_vista"] + d["retorno_vista"] == d["tienes_hoy_vista"]
    assert isinstance(d["retorno_vista"], int)


def test_la_linea_y_el_reparto_cuentan_la_misma_cuenta():
    """Regla 5 de la auditoría: dos vistas del mismo número se comparan entre sí. El
    retorno de la línea es el de los dos portafolios cuando todos los fondos están
    clasificados."""
    res = {"MSTY": _stats(1000.0, 800.0, 200.0), "SCHB": _stats(2000.0, 2600.0, 10.0)}
    clas = {"MSTY": "mode_a", "SCHB": "mode_b"}
    linea = total_cuenta_data(res)
    reparto = portafolios_data(res, clas)
    assert reparto is not None
    suma = sum(g["retorno"] for g in reparto["grupos"])
    assert abs(linea["retorno"] - suma) < 1e-9, (linea["retorno"], suma)


def test_un_fondo_fuera_de_los_dos_grupos_sale_en_la_linea_y_no_en_el_reparto():
    """El alcance se declara (Regla 3b): la línea es la cuenta ENTERA, el reparto son los
    dos portafolios. Si algún día un fondo no cae en ninguno, la diferencia es real y no
    un error de cuentas."""
    res = {"MSTY": _stats(1000.0, 800.0, 200.0), "RARO": _stats(500.0, 700.0, 0.0)}
    linea = total_cuenta_data(res)
    reparto = portafolios_data(res, {"MSTY": "mode_a"})
    suma = sum(g["retorno"] for g in reparto["grupos"])
    assert linea["retorno"] > suma
    assert linea["fondos"] == 2


def test_la_vista_no_calcula_nada():
    """Regla 3 del contrato: las vistas renderizan el objeto, no lo recalculan."""
    fuente = (Path(__file__).resolve().parent / "ui" / "heredadas.py").read_text(encoding="utf-8")
    i = fuente.index("def _render_total_cuenta")
    cuerpo = fuente[i:fuente.index("\ndef ", i + 1)]
    assert "total_cuenta_data(resultados)" in cuerpo
    assert not re.search(r"(pocket_investment|market_value|net_profit|dividends_)", cuerpo), cuerpo


def test_un_resultado_de_cero_no_sale_con_menos():
    fuente = (Path(__file__).resolve().parent / "ui" / "heredadas.py").read_text(encoding="utf-8")
    i = fuente.index("def _usd(")
    assert "entero == 0" in fuente[i:i + 500], "sin normalizar, −0.4 se muestra como «−$0»"
