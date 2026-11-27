"""La línea «el efectivo puesto a trabajar» cuando la ventana empieza después del fondo.

En «Sin DRIP», la tercera línea de Comparación pone cada distribución a comprar el destino
el día que se cobra. Si otro fondo en pantalla nació más tarde, la ventana arranca después
de la incepción del fondo base, y quien compra ese día no tiene el destino que se compró
antes ni el reembolso de retenciones anteriores. Restar el valor de arranque no los quita:
lo que ese destino viejo se mueve después se le apuntaba a la ventana.

Los esperados de este archivo salen de aritmética a mano sobre un universo de cuatro series
planas por tramos, no del motor ni de `_serie_cosecha`:

  fondo A («TSLY»): precio 10 hasta 2024 y 8 desde 2025; paga 1,00 por acción el
      15-mar-2024 (antes del inicio) y 0,50 el 14-feb-2025 (después).
  fondo B («NVDY»): precio 20 hasta 2024 y 16 desde 2025; solo paga 1,00 el 15-mar-2024.
  el que recorta («CHPY»): nace en julio de 2024, mes 6.
  destino («SCHB»): precio 50 hasta feb-2025, 60 de marzo a junio, 90 desde julio; paga
      1,20 por acción el 15-may-2025, a precio 60.

Cuánto crece un dólar puesto en el destino con precio 50, hasta el final:
  bruto: (1 + 1,20/60) × 90/50                         = 1,836
  plano: (1 + 0,84/60) × 90/50                         = 1,8252
  roc (30 % al cobro, la mitad por cobrar): (1,014 × 90 + 1,20 × 0,30 × 0,50)/50 = 1,8288

Compra nueva de A a fin de julio de 2024 con 100: 10 acciones, que al final valen 80. Cobra
5,00 brutos el 14-feb-2025:
  bruto: 80 + 5,00 × 1,836                             =  89,18
  plano: 80 + 3,50 × 1,8252                            =  86,3882
  roc:   80 + 3,50 × 1,8288 + 5,00 × 0,30 × 0,50       =  87,1508
"""
import json
import types

import pandas as pd
import pytest

import price_cache
from test_comparacion_render import _correr_js, _extraer_funcion, _node
from ui import adapters

T0 = "6"
FIN = "21"
MODOS = ("bruto", "plano", "roc")
CRECE = {"bruto": 1.836, "plano": 1.8252, "roc": 1.8288}
A_FINAL = {"bruto": 89.18, "plano": 86.3882, "roc": 87.1508}
A_USD = {"bruto": {"cash": 5.0, "destino": 9.18},
         "plano": {"cash": 3.5, "destino": 6.39},
         "roc": {"cash": 3.5, "destino": 6.40}}
# Desde su incepción A tiene 10 acciones y cobra también los 10,00 de 2024. En «roc» lo
# retenido de 2024 que vuelve (10 × 0,30 × 0,50 = 1,50) llega el 3-mar-2025, con el
# destino a 60: crece (1,014 × 90 + 0,18)/60 = 1,524.
A_DESDE_INCEPCION = {"bruto": 80 + 15.0 * 1.836,
                     "plano": 80 + 10.5 * 1.8252,
                     "roc": 80 + 10.5 * 1.8288 + 1.5 * 1.524 + 0.75}


def _serie(inicio, tramos, pagos):
    fechas = pd.bdate_range(inicio, "2025-10-31")
    precio = pd.Series(0.0, index=fechas)
    for desde, valor in tramos:
        precio[fechas >= pd.Timestamp(desde)] = valor
    div = pd.Series(0.0, index=fechas)
    for dia, monto in pagos:
        assert pd.Timestamp(dia) in fechas, f"{dia} no es día hábil"
        div[pd.Timestamp(dia)] = monto
    return pd.DataFrame({"Close": precio, "Dividends": div, "Stock Splits": 0.0})


def _universo():
    return {
        "TSLY": _serie("2024-01-02", [("2024-01-02", 10.0), ("2025-01-01", 8.0)],
                       [("2024-03-15", 1.0), ("2025-02-14", 0.5)]),
        "NVDY": _serie("2024-01-02", [("2024-01-02", 20.0), ("2025-01-01", 16.0)],
                       [("2024-03-15", 1.0)]),
        "CHPY": _serie("2024-07-01", [("2024-07-01", 30.0)], []),
        "SCHB": _serie("2024-01-02", [("2024-01-02", 50.0), ("2025-03-01", 60.0),
                                      ("2025-07-01", 90.0)], [("2025-05-15", 1.2)]),
    }


def _politica(ticker, modo, roc19a, roc_ici, base_rate=0.30):
    return {"bruto": adapters._PoliticaFiscal(0.0, {}),
            "plano": adapters._PoliticaFiscal(0.30, {}),
            "roc": adapters._PoliticaFiscal(0.30, {2024: 50.0, 2025: 50.0})}[modo]


def _datos(monkeypatch, universo=None):
    universo = universo or _universo()

    def cargar(tk, *a, **k):
        if tk not in universo:
            raise KeyError(tk)
        return price_cache.HistoryResult(history=universo[tk], source="cache", ticker=tk,
                                         cache_asof="2025-10-31")

    monkeypatch.setattr(price_cache, "load_history", cargar)
    monkeypatch.setattr(adapters, "_politica_fiscal", _politica)
    d = adapters.comparacion_data()
    assert d["incep"] == {"TSLY": 0, "NVDY": 0, "CHPY": 6, "SCHB": 0}
    assert str(d["last"]) == FIN
    return d


@pytest.fixture
def datos(monkeypatch):
    return _datos(monkeypatch)


def _retorno(serie, desde=T0):
    return serie[FIN] / serie[desde] - 1


@pytest.mark.parametrize("modo", MODOS)
def test_la_compra_nueva_no_hereda_el_destino_comprado_antes(datos, modo):
    serie = datos["idxCosechaDesde"][modo]["TSLY"][T0]
    assert serie[T0] == pytest.approx(100.0, abs=1e-9), "arranca con lo que se invierte"
    assert serie[FIN] == pytest.approx(A_FINAL[modo], abs=1e-3)
    assert sorted(serie, key=int) == [str(m) for m in range(int(T0), int(FIN) + 1)]


@pytest.mark.parametrize("modo", MODOS)
def test_la_formula_de_restar_si_lo_heredaba(datos, modo):
    """Control: si restar el arranque diera lo mismo, este caso no vigilaría nada."""
    vieja, precio = datos["idxCosecha"][modo]["TSLY"], datos["precioSin"]["TSLY"]
    restando = (vieja[FIN] - vieja[T0]) / precio[T0]
    limpia = _retorno(datos["idxCosechaDesde"][modo]["TSLY"][T0])
    assert abs(restando - limpia) > 0.05, f"{restando:.4f} contra {limpia:.4f}"


@pytest.mark.parametrize("modo", MODOS)
def test_un_fondo_que_solo_pago_antes_va_igual_que_su_precio(datos, modo):
    """B no cobra nada dentro de la ventana: no hay efectivo que poner a trabajar, y en
    «roc» tampoco le toca el reembolso de lo que se retuvo antes de comprar."""
    serie, precio = datos["idxCosechaDesde"][modo]["NVDY"][T0], datos["precioSin"]["NVDY"]
    for m in range(int(T0), int(FIN) + 1):
        assert serie[str(m)] / serie[T0] == pytest.approx(precio[str(m)] / precio[T0], abs=1e-9)
    assert _retorno(serie) == pytest.approx(-0.20, abs=1e-9), "16 sobre 20"
    assert datos["cosechaUSDDesde"][modo]["NVDY"][T0] == {"cash": 0.0, "destino": 0.0}


@pytest.mark.parametrize("modo", MODOS)
def test_los_dolares_de_la_nota_son_los_de_la_ventana(datos, modo):
    assert datos["cosechaUSDDesde"][modo]["TSLY"][T0] == A_USD[modo]
    desde_incepcion = datos["cosechaUSD"][modo]["TSLY"]
    assert desde_incepcion["cash"] > A_USD[modo]["cash"] + 5, "desde 2024 cobró también lo de marzo"


def test_solo_hay_corrida_limpia_donde_hace_falta(datos):
    """Desde su propia incepción la serie de siempre ya es exacta; el que recorta y el
    destino no tienen tercera línea."""
    for modo in MODOS:
        assert set(datos["idxCosechaDesde"][modo]) == {"TSLY", "NVDY"}
        assert set(datos["cosechaUSDDesde"][modo]) == {"TSLY", "NVDY"}
        for tk in ("TSLY", "NVDY"):
            assert set(datos["idxCosechaDesde"][modo][tk]) == {T0}
            assert set(datos["cosechaUSDDesde"][modo][tk]) == {T0}


def test_si_el_destino_no_cubre_la_ventana_no_hay_linea(monkeypatch):
    universo = _universo()
    universo["SCHB"] = universo["SCHB"].loc["2024-09-02":]
    d = _datos_sin_comprobar(monkeypatch, universo)
    for modo in MODOS:
        assert d["idxCosechaDesde"][modo] == {} and d["cosechaUSDDesde"][modo] == {}


def test_un_hueco_del_destino_el_primer_dia_deja_esa_ventana_sin_linea(monkeypatch):
    """Al destino le falta la fila del día en que empieza la ventana (el último cierre
    del mes de inicio). Desde la incepción el hueco se cubre con el cierre anterior; la
    compra nueva no tiene cierre anterior dentro de su corrida, así que esa ventana se
    queda sin línea en vez de inventarla."""
    universo = _universo()
    primer_dia = universo["TSLY"].loc["2024-07"].index.max()
    universo["SCHB"] = universo["SCHB"].drop(primer_dia)
    d = _datos_sin_comprobar(monkeypatch, universo)
    for modo in MODOS:
        assert {"TSLY", "NVDY"} <= set(d["idxCosecha"][modo]), "desde su incepción sí hay línea"
        assert d["idxCosechaDesde"][modo] == {} and d["cosechaUSDDesde"][modo] == {}


def _datos_sin_comprobar(monkeypatch, universo):
    monkeypatch.setattr(price_cache, "load_history", lambda tk, *a, **k: (
        price_cache.HistoryResult(history=universo[tk], source="cache", ticker=tk,
                                  cache_asof="2025-10-31")
        if tk in universo else (_ for _ in ()).throw(KeyError(tk))))
    monkeypatch.setattr(adapters, "_politica_fiscal", _politica)
    return adapters.comparacion_data()


# ── El componente: de los datos del adaptador a la línea ──────────────────────────────

@_node
@pytest.mark.parametrize("modo", MODOS)
def test_la_linea_dibuja_la_compra_nueva(datos, modo):
    rep = _correr_js(_extraer_funcion("seriesSin"), datos, last=int(FIN),
                     llamada=f'seriesSin("TSLY", "{modo}", {T0})')
    assert "cosechaData" in rep, "con corrida limpia la tercera línea se dibuja"
    assert rep["cosechaData"][T0] == pytest.approx(0.0, abs=1e-12)
    assert rep["cosechaData"][FIN] == pytest.approx(A_FINAL[modo] / 100 - 1, abs=1e-5)
    # las otras dos líneas no cambian: precio 8 sobre 10 y el efectivo quieto encima
    assert rep["priceData"][FIN] == pytest.approx(-0.20, abs=1e-9)
    assert rep["data"][FIN] == pytest.approx(-0.20 + A_USD[modo]["cash"] / 100
                                             + (0.0075 if modo == "roc" else 0.0), abs=1e-5)


@_node
@pytest.mark.parametrize("modo", MODOS)
def test_desde_la_incepcion_la_linea_es_la_de_siempre(datos, modo):
    rep = _correr_js(_extraer_funcion("seriesSin"), datos, last=int(FIN),
                     llamada=f'seriesSin("TSLY", "{modo}", 0)')
    assert rep["cosechaData"]["0"] == pytest.approx(0.0, abs=1e-12)
    assert rep["cosechaData"][FIN] == pytest.approx(A_DESDE_INCEPCION[modo] / 100 - 1, abs=1e-5)


@_node
@pytest.mark.parametrize("quitar", ["la clave entera", "el modo", "el fondo", "ese inicio",
                                    "el arranque de la serie"])
def test_sin_corrida_limpia_la_linea_no_se_dibuja(datos, quitar):
    """Nunca una aproximación: si falta la corrida desde ese mes, no hay tercera línea."""
    d = json.loads(json.dumps(datos))
    if quitar == "la clave entera":
        del d["idxCosechaDesde"]
    elif quitar == "el modo":
        del d["idxCosechaDesde"]["bruto"]
    elif quitar == "el fondo":
        del d["idxCosechaDesde"]["bruto"]["TSLY"]
    elif quitar == "ese inicio":
        d["idxCosechaDesde"]["bruto"]["TSLY"] = {"3": d["idxCosechaDesde"]["bruto"]["TSLY"][T0]}
    else:
        del d["idxCosechaDesde"]["bruto"]["TSLY"][T0][T0]
    rep = _correr_js(_extraer_funcion("seriesSin"), d, last=int(FIN),
                     llamada=f'seriesSin("TSLY", "bruto", {T0})')
    assert "cosechaData" not in rep
    assert rep["priceData"][FIN] == pytest.approx(-0.20, abs=1e-9), "las otras dos siguen"
    desde_incepcion = _correr_js(_extraer_funcion("seriesSin"), d, last=int(FIN),
                                 llamada='seriesSin("TSLY", "bruto", 0)')
    assert "cosechaData" in desde_incepcion, "desde la incepción no depende de esa corrida"


# ── La pantalla: la línea y la nota, con Chromium ─────────────────────────────────────

_LEER = """() => ({
  notas: document.getElementById('cmpNotes').innerText,
  etiquetas: Array.from(document.querySelectorAll('#cmpSvg text')).map(t => t.textContent),
})"""


def _pantalla(datos, modo_chip=None):
    sync_api = pytest.importorskip("playwright.sync_api")
    from ui import componentes
    html = componentes._con_tema(componentes._plantilla("comparacion.html"), "Claro")
    html = html.replace("{{DATA_JSON}}", json.dumps(datos, ensure_ascii=False))
    try:
        with sync_api.sync_playwright() as pw:
            nav = pw.chromium.launch()
            pagina = nav.new_page(viewport={"width": 1200, "height": 1600})
            errores = []
            pagina.on("pageerror", lambda e: errores.append(str(e)))
            pagina.set_content("<!doctype html>" + html)
            pagina.wait_for_timeout(200)
            pagina.click("#cmpBase button:text-is('TSLY')")
            pagina.click("#cmpVista button:text-is('Sin DRIP')")
            if modo_chip:
                pagina.click(f"#cmpMode button:text-is('{modo_chip}')")
            antes = pagina.evaluate(_LEER)
            pagina.click("#cmpCmp button:has-text('CHPY')")
            pagina.wait_for_timeout(200)
            despues = pagina.evaluate(_LEER)
            nav.close()
    except sync_api.Error as e:
        pytest.skip(f"Chromium no disponible: {e}")
    assert not errores, errores
    return types.SimpleNamespace(antes=antes, despues=despues)


def test_la_nota_cuenta_los_dolares_de_la_ventana(datos):
    p = _pantalla(datos)
    assert "$15 cobrados" in p.antes["notas"] and "valdrían $28 hoy" in p.antes["notas"], (
        "desde la incepción: 15,00 cobrados, 15 × 1,836 = 27,54")
    assert "$5 cobrados" in p.despues["notas"] and "valdrían $9 hoy" in p.despues["notas"], (
        "desde julio de 2024: 5,00 cobrados, 9,18")
    assert "$15 cobrados" not in p.despues["notas"]
    assert "Ventana recortada" not in p.despues["notas"]
    assert "sacar el flujo a SCHB dio -11%" in p.despues["notas"], "89,18 sobre 100"


def test_la_nota_del_modo_roc_usa_su_corrida(datos):
    p = _pantalla(datos, modo_chip="Neto ROC")
    assert "$4 cobrados" in p.despues["notas"] and "valdrían $6 hoy" in p.despues["notas"], (
        "3,50 cobrados y 6,40 en el destino")
    assert "sacar el flujo a SCHB dio -13%" in p.despues["notas"], "87,15 sobre 100"


def test_sin_corrida_limpia_la_pantalla_lo_dice_y_no_inventa(datos):
    d = json.loads(json.dumps(datos))
    del d["idxCosechaDesde"]["bruto"]["TSLY"]
    p = _pantalla(d)
    assert "El efectivo puesto a trabajar" in p.antes["notas"]
    assert "Ventana recortada" in p.despues["notas"]
    assert "no se dibuja en esta ventana" in p.despues["notas"]
    assert "El efectivo puesto a trabajar" not in p.despues["notas"]
    assert "Rotar vs reinvertir" not in p.despues["notas"]
    assert any("SCHB" in t and "TSLY" in t for t in p.antes["etiquetas"]), p.antes["etiquetas"]
    assert not any("TSLY" in t and "SCHB" in t for t in p.despues["etiquetas"]), p.despues["etiquetas"]


def test_faltan_los_dolares_de_la_ventana_tampoco_se_usan_los_de_la_incepcion(datos):
    d = json.loads(json.dumps(datos))
    del d["cosechaUSDDesde"]["bruto"]["TSLY"][T0]
    p = _pantalla(d)
    assert "Ventana recortada" in p.despues["notas"]
    assert "cobrados" not in p.despues["notas"]
