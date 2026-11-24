"""«Matriz 2» — `logic.xirr` y `ui.adapters.metodo_real_data` (traspaso 2026-08-17).

«La matriz» audita la cartera de Greco: una compra por ticker, en una fecha, con DRIP
total. «Matriz 2» corre las mismas cuatro lecciones sobre el CSV del usuario, donde nada
de eso se cumple — y cada una de esas diferencias es un sitio donde una cifra puede salir
falsa sobre dinero real. Lo que se protege aquí es exactamente eso, no números puntuales
(el valor de mercado se mueve solo cada día).

Sin red: `logic.fetch_market_data` se monkeypatchea con el mismo mock que `test_adapters.py`.
"""
import io
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(__file__))
import logic                                     # noqa: E402
from ui.adapters import metodo_real_data          # noqa: E402


class FakeFile:
    def __init__(self, content: bytes, name: str = "test.csv"):
        self._buf = io.BytesIO(content)
        self.name = name

    def read(self):
        return self._buf.read()

    def seek(self, n):
        self._buf.seek(n)


def _mkt_mock(precio: float):
    """Precio de cierre fijo — el valor de mercado deja de depender de la red (y de que
    yfinance esté sano: el 2026-08-18 devolvía filas con `Close` = NaN)."""
    return lambda t, d: (pd.DataFrame(
        {"Close": [precio], "Dividends": [0.0], "Stock Splits": [0.0]},
        index=pd.to_datetime(["2026-01-01"])), None)


def _resultados(monkeypatch, fixture: str, version: str, precio: float = 20.0):
    raw = open(os.path.join(os.path.dirname(__file__), "fixtures", fixture,
                            "synthetic_transactions.csv"), "rb").read()
    df, _ = logic.load_and_detect_csv(FakeFile(raw, f"{fixture}.csv"))
    dfc = logic.normalize_csv(df)
    monkeypatch.setattr(logic, "fetch_market_data", _mkt_mock(precio))
    return logic.analyze_portfolio(dfc, version=version), dfc


# ── logic.xirr — el retorno anual exacto ────────────────────────────────────────────────

def test_xirr_caso_cerrado_a_mano():
    """−100 hace dos años y +121 hoy son exactamente +10% anual compuesto."""
    hoy = pd.Timestamp("2026-01-01")
    r = logic.xirr([(hoy - pd.Timedelta(days=730.5), -100.0), (hoy, 121.0)])
    assert r == pytest.approx(0.10, abs=1e-4)


def test_xirr_coincide_con_el_cagr_clasico_cuando_hay_un_solo_aporte():
    """La generalización no puede romper el caso simple: con UN aporte y UN valor final,
    la TIR y el CAGR `(vf/v0)**(1/n)−1` son la misma cosa. Si algún día divergen, es que
    el descuento por fechas se torció."""
    hoy = pd.Timestamp("2026-01-01")
    n = 3.5
    v0, vf = 10_000.0, 23_000.0
    cagr = (vf / v0) ** (1 / n) - 1
    r = logic.xirr([(hoy - pd.Timedelta(days=n * 365.25), -v0), (hoy, vf)])
    assert r == pytest.approx(cagr, abs=1e-4)


def test_xirr_devuelve_none_y_no_cero_cuando_no_hay_respuesta():
    """`0.0` es un resultado («no rindió nada»); `None` es «no se puede calcular». La UI
    tiene que poder distinguirlos — un cero inventado se lee como medido."""
    hoy = pd.Timestamp("2026-01-01")
    assert logic.xirr([]) is None
    assert logic.xirr([(hoy, 100.0), (hoy, 50.0)]) is None          # sin flujo negativo
    assert logic.xirr([(hoy, -100.0), (hoy, -50.0)]) is None        # sin flujo positivo


def test_xirr_ignora_nan_y_fechas_invalidas():
    hoy = pd.Timestamp("2026-01-01")
    r = logic.xirr([(hoy - pd.Timedelta(days=365.25), -100.0),
                    (None, 999.0), (hoy, float("nan")), (hoy, 110.0)])
    assert r == pytest.approx(0.10, abs=1e-4)


def test_xirr_no_revienta_si_una_fecha_trae_zona_horaria():
    """Los cierres de Yahoo llegan a veces con zona horaria y las filas del CSV sin ella.
    Restarlas lanzaba `TypeError`; ahora se compara la fecha de calendario."""
    hoy = pd.Timestamp("2026-01-01")
    antes = pd.Timestamp("2026-01-01", tz="UTC") - pd.Timedelta(days=365.25)
    assert logic.xirr([(antes, -100.0), (hoy, 110.0)]) == pytest.approx(0.10, abs=1e-4)


@pytest.mark.parametrize("queda, tasa", [(0.0001, -0.99999901), (0.001, -0.99999008), (1.0, -0.99003149)])
def test_xirr_mide_una_perdida_casi_total(queda, tasa):
    """−100 hace 365 días y `queda` hoy: la tasa es `(queda/100) ** (365.25/365) − 1`. Por
    debajo de −99,99 % devolvía `None`, y una posición que lo perdió casi todo se leía
    como «sin dato»."""
    hoy = pd.Timestamp("2026-01-01")
    r = logic.xirr([(hoy - pd.Timedelta(days=365), -100.0), (hoy, queda)])
    assert r == pytest.approx((queda / 100) ** (365.25 / 365) - 1, abs=1e-9)
    assert r == pytest.approx(tasa, abs=1e-8)


def test_xirr_no_anualiza_por_encima_de_once_veces_al_ano():
    """Decisión (nov-2026): el tope de arriba se queda. Multiplicar por 10 en un año
    (+900 %) se mide; por 12 ya no — casi siempre es una tenencia de días, y anualizarla
    pone en pantalla un porcentaje de varias cifras que no describe nada."""
    hoy = pd.Timestamp("2026-01-01")
    hace_un_ano = hoy - pd.Timedelta(days=365)
    assert logic.xirr([(hace_un_ano, -100.0), (hoy, 1000.0)]) == pytest.approx(10 ** (365.25 / 365) - 1, abs=1e-6)
    assert logic.xirr([(hace_un_ano, -100.0), (hoy, 1200.0)]) is None
    assert logic.xirr([(hoy - pd.Timedelta(days=30), -100.0), (hoy, 5000.0)]) is None


def test_xirr_con_dos_soluciones_no_elige_una():
    """Un cobro ANTES de la primera compra (acciones que llegaron sin costo) da flujos
    +100, −230, +132 a un año de distancia: la ecuación se anula en ~10 % y en ~20 %.
    Ninguna de las dos es «la» rentabilidad, y el resultado es sin dato. El cálculo por
    mes que tenía `irr_anual` devolvía una de las dos."""
    t0 = pd.Timestamp("2024-01-01")
    flujos = [(t0, 100.0), (t0 + pd.Timedelta(days=365), -230.0), (t0 + pd.Timedelta(days=730), 132.0)]
    vpn = lambda r: sum(v / (1 + r) ** ((d - t0).days / 365.25) for d, v in flujos)
    assert vpn(0.05) > 0 > vpn(0.15) and vpn(0.25) > 0
    assert logic.xirr(flujos) is None


def test_xirr_pesa_por_tiempo_no_por_monto_promedio():
    """El punto de usar TIR y no un CAGR sobre plazo promedio: dos aportes iguales en
    fechas distintas NO dan lo mismo que un aporte doble en la fecha media."""
    hoy = pd.Timestamp("2026-01-01")
    temprano = hoy - pd.Timedelta(days=4 * 365.25)
    tarde = hoy - pd.Timedelta(days=365.25)
    repartido = logic.xirr([(temprano, -100.0), (tarde, -100.0), (hoy, 260.0)])
    junto = logic.xirr([(hoy - pd.Timedelta(days=2.5 * 365.25), -200.0), (hoy, 260.0)])
    assert repartido is not None and junto is not None
    assert repartido != pytest.approx(junto, abs=1e-3)


# ── metodo_real_data — forma e invariantes ──────────────────────────────────────────────

def test_devuelve_none_sin_posiciones():
    assert metodo_real_data({}, None, 30.0, "MX") is None


def test_matriz_identidad_total_inv(monkeypatch):
    """`Total inv. = Inversión + Dividendos` por fila y en el total — es LA suma que la
    sección existe para desmentir, así que tiene que ser exactamente la que hace la hoja."""
    res, dfc = _resultados(monkeypatch, "schwab_synth_2", "TEST_M2_IDENT")
    d = metodo_real_data(res, dfc, 30.0, "MX")
    assert d is not None
    for f in d["matriz"]:
        assert f["tot"] == pytest.approx(f["inv"] + f["div"], abs=0.01)
    assert d["tot"]["tot"] == pytest.approx(d["tot"]["inv"] + d["tot"]["div"], abs=0.01)


def test_capital_aportado_no_se_mueve_con_el_pais(monkeypatch):
    """Regla 1 del contrato: el capital aportado es invariante. Cambiar la residencia
    declarada mueve el bucket de impuesto, nunca lo que salió del bolsillo."""
    res, dfc = _resultados(monkeypatch, "schwab_synth_2", "TEST_M2_PAIS")
    mx = metodo_real_data(res, dfc, 30.0, "MX")
    cl = metodo_real_data(res, dfc, 10.0, "CL")
    assert mx["tot"]["inv"] == pytest.approx(cl["tot"]["inv"], abs=0.01)
    assert [f["inv"] for f in mx["matriz"]] == pytest.approx([f["inv"] for f in cl["matriz"]])


def test_sin_pais_declarado_no_se_asume_30_por_ciento(monkeypatch):
    """«Sin declarar» no es 0% ni 30%: es no estimar. Sin país no hay payback neto."""
    res, dfc = _resultados(monkeypatch, "schwab_synth_2", "TEST_M2_SINPAIS")
    d = metodo_real_data(res, dfc, logic.RATE_UNDECLARED, None)
    assert d["paisDeclarado"] is False
    assert "pbn" not in d["ratiosTot"]
    assert all("pbn" not in r for r in d["ratios"])
    assert d["nra"]["netoDeclarado"] is None


def test_el_retorno_no_usa_el_atajo_de_la_matriz(monkeypatch):
    """**La trampa del traspaso.** En «La matriz» el DRIP fue total, así que
    `valor − aportado` ya es el retorno. Aquí el DRIP es parcial: parte de los dividendos
    se cobró en efectivo y nunca compró acciones, así que ese atajo se deja fuera ese
    dinero. La fórmula válida es `valor + efectivo − aportado`.

    Si alguien «simplifica» a la resta, este test cae: sobre un fixture con dividendos
    cobrados en efectivo, las dos fórmulas difieren justo en ese efectivo.
    """
    res, dfc = _resultados(monkeypatch, "schwab_synth_2", "TEST_M2_TRAMPA")
    d = metodo_real_data(res, dfc, 30.0, "MX")
    atajo = d["tot"]["val"] - d["tot"]["inv"]
    assert d["ratiosTot"]["retD"] != pytest.approx(atajo, abs=0.01), (
        "el retorno coincide con `valor − aportado`: o el fixture no tiene efectivo sin "
        "reinvertir (y entonces este test no prueba nada), o se coló el atajo de «La matriz»")


def test_posicion_sin_precio_se_excluye_declarandolo(monkeypatch):
    """Un NaN en una cifra de dinero no puede entrar a un total: contamina por aritmética
    y, como toda comparación con NaN es falsa, la posición se volvería invisible en vez de
    ruidosa. Se excluye con motivo, nunca en silencio."""
    res, dfc = _resultados(monkeypatch, "schwab_synth_2", "TEST_M2_NAN",
                           precio=float("nan"))
    d = metodo_real_data(res, dfc, 30.0, "MX")
    if d is None:
        return  # ninguna posición valorable: degradó del todo, que también es honesto
    for f in d["matriz"]:
        assert all(v == v for v in (f["inv"], f["div"], f["tot"], f["val"]))
    assert d["tot"]["val"] == d["tot"]["val"]


def test_contraejemplo_sale_del_dato_no_de_un_ticker_cableado(monkeypatch):
    """El panel marca «cobró y perdió». Ese ticker se elige por dato (mayor payback entre
    los de retorno negativo) — cablearlo a mano es lo que dejó a CONY etiquetado como
    perdedor meses después de que dejara de perder."""
    res, dfc = _resultados(monkeypatch, "schwab_synth_2", "TEST_M2_CONTRA")
    d = metodo_real_data(res, dfc, 30.0, "MX")
    tk = d["paybackContraejemplo"]
    negativos = [r for r in d["ratios"] if r["ret"] < 0]
    if not negativos:
        assert tk is None, "no hay perdedores, no puede haber contraejemplo"
    else:
        assert tk == max(negativos, key=lambda r: r["pb"])["t"]


def test_escalera_sin_plazo_inventado(monkeypatch):
    """Decisión de Daniel: exacto. La escalera no expone ningún «N años» — el anualizado
    es TIR sobre fechas reales, o no está."""
    res, dfc = _resultados(monkeypatch, "schwab_synth_2", "TEST_M2_ESC")
    d = metodo_real_data(res, dfc, 30.0, "MX")
    esc = d["escalera"]
    assert esc is not None
    for prohibida in ("N", "cagrPct", "naivePct"):
        assert prohibida not in esc, (
            f"`{prohibida}` volvió a la escalera: es un plazo/promedio inventado, y la "
            "decisión fue anualizar con TIR exacta")
    assert "xirrPct" in esc


def test_el_peldano_del_efectivo_se_declara_no_disponible(monkeypatch):
    """El contrafáctico «si los dividendos fueran efectivo» necesita el valor de hoy de
    SOLO las acciones compradas con dinero propio, que no existe por posición en un CSV con
    compras fraccionadas. Se declara faltante en vez de aproximarse."""
    res, dfc = _resultados(monkeypatch, "schwab_synth_2", "TEST_M2_EFECTIVO")
    d = metodo_real_data(res, dfc, 30.0, "MX")
    assert d["escalera"]["efectivoDisponible"] is False


def test_tickers_sin_ficha_del_emisor_se_listan_no_se_ocultan(monkeypatch):
    res, dfc = _resultados(monkeypatch, "schwab_synth_2", "TEST_M2_FICHA")
    d = metodo_real_data(res, dfc, 30.0, "MX")
    en_matriz = {f["t"] for f in d["matriz"]}
    assert set(d["conFicha"]) | set(d["sinFicha"]) == en_matriz


def test_el_componente_no_reintroduce_literales_de_la_escalera():
    """Red anti-regresión de la misma clase que protege a «La matriz»: el componente
    RENDERIZA `DATA`, no puede volver a traer cifras propias."""
    ruta = os.path.join(os.path.dirname(__file__), "ui", "componentes", "metodo_real.html")
    html = open(ruta, encoding="utf-8").read()
    assert "{{DATA_JSON}}" in html
    for muerta in ("esc.cagrPct", "esc.naivePct", "esc.N."):
        assert muerta not in html, f"`{muerta}` ya no existe en el adapter — quedó código muerto"


# ── El precio de hoy cuando el mercado aún no abrió ──────────────────────────────────────

def _mkt_mock_con_barra_vacia(precio: float):
    """Reproduce lo que devuelve yfinance antes de la apertura: la serie histórica normal
    MÁS una barra para la sesión en curso con `Close` = NaN."""
    return lambda t, d: (pd.DataFrame(
        {"Close": [precio, float("nan")],
         "Dividends": [0.0, 0.0],
         "Stock Splits": [0.0, 0.0]},
        index=pd.to_datetime(["2026-01-01", "2026-01-02"])), None)


def test_precio_ignora_la_barra_en_curso_sin_datos(monkeypatch):
    """`analyze_portfolio` tomaba `Close.iloc[-1]` a ciegas. yfinance entrega una barra para
    el día en curso desde antes de la apertura, con `Close` = NaN — así que abrir la app por
    la mañana daba `market_value = shares * NaN` en TODAS las posiciones, y como ninguna
    comparación con NaN es verdadera, ningún guard lo veía: parecía dato faltante, no error.

    Se saltea la barra vacía y se usa el último cierre con dato.
    """
    raw = open(os.path.join(os.path.dirname(__file__), "fixtures", "schwab_synth_2",
                            "synthetic_transactions.csv"), "rb").read()
    df, _ = logic.load_and_detect_csv(FakeFile(raw, "schwab_synth_2.csv"))
    dfc = logic.normalize_csv(df)
    monkeypatch.setattr(logic, "fetch_market_data", _mkt_mock_con_barra_vacia(20.0))
    res = logic.analyze_portfolio(dfc, version="TEST_BARRA_VACIA")

    valorados = [s for s in res.values()
                 if isinstance(s, dict) and not s.get("skipped") and "error" not in s]
    assert valorados, "ninguna posición se analizó: el fixture no ejercita esta rama"
    for s in valorados:
        mv = s.get("market_value")
        assert mv == mv, "market_value salió NaN: volvió a colarse la barra en curso"


def test_la_rentabilidad_anual_de_la_cartera_cuenta_el_valor_de_hoy_una_sola_vez(monkeypatch):
    """Dos fondos: $1,000 y $500 puestos hace 366 días, que hoy valen $1,100 y $550.
    Esperado a mano: `1.1 ** (365.25 / 366) − 1` = 9,98 %. Contar dos veces el valor de hoy
    daría más del 100 %; no contarlo, una pérdida casi total."""
    import datetime

    import pandas as pd

    from ui import adapters

    hoy = datetime.date(2025, 1, 2)

    class _Fecha(datetime.date):
        @classmethod
        def today(cls):
            return hoy

    monkeypatch.setattr(adapters.datetime, "date", _Fecha)
    inicio = pd.Timestamp("2024-01-02")
    res = {"A": {"cash_flows_dated": [(inicio, -1000.0)], "market_value": 1100.0},
           "B": {"cash_flows_dated": [(inicio, -500.0)], "market_value": 550.0},
           "C": {"cash_flows_dated": [(inicio, -900.0)], "market_value": 5.0}}
    tasa = adapters._xirr_cartera(res, ["A", "B"])
    assert tasa == pytest.approx((1.1 ** (365.25 / 366) - 1) * 100, abs=0.006)
    assert tasa == pytest.approx(9.98, abs=0.006)
