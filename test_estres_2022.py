"""Puerta de «¿Y en una caída como la de 2022?»: sin G1 no se muestra 2022.

G1 — fuera de tiempo, por fondo: parámetros calibrados solo hasta 2024-12-31, medidos contra la
historia REAL de 2025-01-02 en adelante (snapshot congelado del caché, que no se mueve). Se exige
que la peor caída y la volatilidad simuladas (mediana de las fases del ciclo) queden cerca de las
reales, fondo por fondo.
G2 — regla 3b: `resumen_estres` (Python) contra el motor JS del componente.
G3 (cifras de control con la canasta de referencia) vive fuera del repo: lleva la receta.
G4 — cada fondo simulado solo en 2022, al dólar, contra una medición independiente.
Snapshot — todo fondo que la app reconoce tiene su 2022 congelado (o declarado sin sesiones en la
ventana), y la UI no baja nada en vivo.
"""
import json
import os
import re
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest
import yaml

import estres_2022 as e22
import logic

AQUI = os.path.dirname(os.path.abspath(__file__))
CONGELADO = os.path.join(AQUI, "knowledge", "price_cache_frozen")
PARAMETROS = os.path.join(AQUI, "knowledge", "estres_2022", "parametros.yaml")
VALIDACION = os.path.join(AQUI, "knowledge", "estres_2022", "validacion")
META = os.path.join(AQUI, "knowledge", "estres_2022", "_meta.yaml")
FONDOS = ("TSLY", "NVDY", "CONY", "NFLY", "MSTY")
CORTE = pd.Timestamp("2024-12-31")

# Umbrales de la puerta (puntos porcentuales). No se suben para que algo pase.
TOPE_CAIDA_PP = 8.0
TOPE_VOL_PP = 6.0


def _params():
    with open(PARAMETROS, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _hist(t):
    # NFLX no está en el caché de precios; su snapshot (al mismo 21-ago-2026) vive aparte.
    carpeta = VALIDACION if t == "NFLX" else CONGELADO
    h = pd.read_parquet(os.path.join(carpeta, f"{t}.parquet"))
    return h[~h.index.duplicated(keep="last")].sort_index()


def _metricas(r):
    v = np.concatenate([[1.0], np.cumprod(1 + np.asarray(r))])
    return float((1 - v / np.maximum.accumulate(v)).max()) * 100, float(np.std(r, ddof=1) * np.sqrt(252)) * 100


def _fuera_de_tiempo(fondo, parametros=None, subyacente=None):
    """(real, simuladas): peor caída y volatilidad reales, y las simuladas con cada fase del ciclo."""
    p = (parametros or _params())["calibrados_hasta_2024"][fondo]
    h = _hist(fondo)
    real = e22._retorno_real(h)
    real = real[real.index > CORTE]
    # El subyacente sale del mismo camino que usa la app (`instruments.yaml`), no de una copia.
    close_u = _hist(subyacente or e22.subyacentes_yieldmax(logic.load_instruments())[fondo])["Close"]
    # El día en que arranca el ciclo de ventas de la opción es arbitrario y mueve la cifra (NFLY:
    # el error de su caída simulada va de +2.4 a +10.0 pp según la fase). Se simula con cada fase posible
    # (arrancando 0..per-1 sesiones después del primer día del fondo) y se mide solo lo posterior
    # al corte.
    sims = []
    for fase in range(p["per"]):
        sim = e22.simular(close_u, p["per"], p["m"], p["k"], h.index[fase], real.index[-1]).reindex(real.index)
        assert not sim.isna().any()
        sims.append(_metricas(sim))
    return _metricas(real), sims


@pytest.mark.parametrize("fondo", sorted(FONDOS))
def test_g1_fuera_de_tiempo(fondo, capsys):
    """Se exige la MEDIANA de las fases: una sola fase mide esa fase, no el método."""
    (cr, vr), sims = _fuera_de_tiempo(fondo)
    dc = np.array([c - cr for c, _ in sims])
    dv = np.array([v - vr for _, v in sims])
    with capsys.disabled():
        print(f"\nG1 {fondo} ({len(sims)} fases): Δ peor caída mediana {np.median(dc):+.1f} "
              f"[{dc.min():+.1f} a {dc.max():+.1f}] · Δ volatilidad mediana {np.median(dv):+.1f} "
              f"[{dv.min():+.1f} a {dv.max():+.1f}]")
    assert abs(np.median(dc)) <= TOPE_CAIDA_PP, (fondo, cr, dc.tolist())
    assert abs(np.median(dv)) <= TOPE_VOL_PP, (fondo, vr, dv.tolist())


# ── G4 · cada fondo simulado solo, en 2022, al dólar ──────────────────────────
# Cifras del `modelo.py` de la medición del 28-oct-2026: código independiente de `estres_2022`
# (otro bucle, otra normal), un fondo a la vez y sin mezcla. Fijan el modelo en CI, donde no
# corren las cifras de control con la canasta (viven fuera del repo). Con $10,000 desde el peor
# día de la serie central: mínimo, rango de la prima (k ± banda) y valor al 29-dic-2023.
G4 = {
    "CONY": {"desde": "2021-04-16", "min": 1240, "rango": (1049, 1481), "hoy": 3779},
    "MSTY": {"desde": "2021-11-08", "min": 1831, "rango": (1436, 2274), "hoy": 5156},
    "NFLY": {"desde": "2021-11-17", "min": 2995, "rango": (2894, 3101), "hoy": 6331},
    "NVDY": {"desde": "2021-11-29", "min": 3819, "rango": (3607, 4069), "hoy": 10413},
    "TSLY": {"desde": "2021-11-04", "min": 3124, "rango": (2709, 3642), "hoy": 5499},
}


@pytest.mark.parametrize("fondo", sorted(G4))
def test_g4_cada_fondo_en_2022_al_dolar(fondo):
    sub = e22.subyacentes_yieldmax(logic.load_instruments())
    carpeta = os.path.join(AQUI, "knowledge", "estres_2022")
    hist = {t: pd.read_parquet(os.path.join(carpeta, f"{t}.parquet")) for t in (sub[fondo], "XLK")}
    est = e22.datos_estres({fondo: 1.0}, {"XLK": 1.0}, hist, _params(), sub)
    r = e22.resumen_estres(est, 100)
    desde = pd.Timestamp(est["inicio"]) + pd.Timedelta(days=([0] + est["dias"])[r["desde"]])
    esperado = G4[fondo]
    assert str(desde.date()) == esperado["desde"]
    assert abs(r["min"] - esperado["min"]) <= 1, (fondo, r["min"])
    assert all(abs(a - b) <= 1 for a, b in zip(r["rango"], esperado["rango"])), (fondo, r["rango"])
    assert abs(r["hoy"] - esperado["hoy"]) <= 1, (fondo, r["hoy"])


# ── G2 · regla 3b: motor JS del componente = resumen_estres ───────────────────

def _estres_sintetico():
    """Tres series de dividendos que no comparten el peor día: la central cae a mitad, la banda
    baja cae antes y más hondo, la alta cae después. Crecimiento: tendencia con un bache."""
    rng = np.random.default_rng(7)
    n = 220
    base = 0.0006 + 0.012 * rng.standard_normal(n)
    base[90:140] -= 0.012
    bajo = base - 0.0009
    bajo[40:70] -= 0.015
    alto = base + 0.0009
    alto[150:190] -= 0.012
    crec = 0.0005 + 0.006 * rng.standard_normal(n)
    crec[100:120] -= 0.006
    r = lambda x: [round(float(v), 6) for v in x]
    return {"inicio": "2021-04-14", "fin": "2022-03-01", "limitante": "AAA", "dias": list(range(1, n + 1)),
            "div": r(base), "div_bajo": r(bajo), "div_alto": r(alto), "crec": r(crec),
            "simulados": ["XXX"], "subyacente": {"XXX": "AAA"}, "reales": ["CCC"], "fuera": []}


def test_g2_motor_js_igual_a_python(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("no hay node en el PATH: no se puede correr el motor del componente")
    html = open(os.path.join(AQUI, "ui", "componentes", "riesgo.html"), encoding="utf-8").read()
    motor = re.search(r'<script id="motor">(.*?)</script>', html, re.S).group(1)
    est = _estres_sintetico()
    js = motor + """
var S = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8")), out = {};
[0, 23, 50, 77, 80, 100].forEach(function (p) {
  var e = Motor.estresPara(S, p / 100), f = e.mezcla.length - 1;
  out[p] = { desde: e.desde, min: e.mezcla[e.minM], min_i: e.desde + e.minM, hoy: e.mezcla[f],
    min_crec: e.crec[e.minG], hoy_crec: e.crec[f], rango: [Math.min(e.lo, e.hi), Math.max(e.lo, e.hi)],
    recupera: e.mezcla[e.minM] < 10000 ? (e.recM < 0 ? -1 : e.desde + e.recM) : null };
});
console.log(JSON.stringify(out));"""
    (tmp_path / "m.js").write_text(js)
    (tmp_path / "d.json").write_text(json.dumps(est))
    salida = json.loads(subprocess.run(["node", str(tmp_path / "m.js"), str(tmp_path / "d.json")],
                                       capture_output=True, text=True, check=True).stdout)
    banda_propia_distinta = False
    for p in (0, 23, 50, 77, 80, 100):
        py, j = e22.resumen_estres(est, p), salida[str(p)]
        for c in ("min", "hoy", "min_crec", "hoy_crec"):
            assert abs(py[c] - j[c]) <= 1, f"{p} {c}: python {py[c]}, js {j[c]}"
        for a, b in zip(py["rango"], j["rango"]):
            assert abs(a - b) <= 1, f"{p} rango: python {py['rango']}, js {j['rango']}"
        for c in ("desde", "min_i", "recupera"):
            assert py[c] == j[c], f"{p} {c}: python {py[c]}, js {j[c]}"
        if p > 0:
            propio = e22._peor_entrada(e22._indice(est["div_bajo"], est["crec"], p / 100))
            banda_propia_distinta |= propio != py["desde"]
    assert banda_propia_distinta, "los datos sintéticos no distinguen la entrada central de la propia de la banda"


# ── Qué entra a la simulación y qué queda fuera ───────────────────────────────

def _historia_sintetica(inicio, n, semilla, deriva=0.0004, dividendo=0.0):
    rng = np.random.default_rng(semilla)
    idx = pd.bdate_range(inicio, periods=n)
    close = 100 * np.cumprod(1 + deriva + 0.02 * rng.standard_normal(n))
    div = np.zeros(n)
    div[::21] = dividendo
    return pd.DataFrame({"Close": close, "Dividends": div}, index=idx)


PARAM_SINT = {"ventana": {"inicio": "2021-04-14", "fin": "2022-12-30"}, "banda": 0.1,
              "fondos": {"FFA": {"per": 21, "m": 0.1, "k": 1.0}},
              "global": {"per": 5, "m": 0.075, "k": 0.9}}


def _mundo():
    hist = {"UUA": _historia_sintetica("2021-03-01", 700, 1), "UUB": _historia_sintetica("2021-04-14", 680, 2),
            "RRR": _historia_sintetica("2021-03-01", 700, 3, dividendo=0.2),
            "TARDE": _historia_sintetica("2021-09-01", 500, 4)}
    sub = {"FFA": "UUA", "FFB": "UUB", "FFC": "UUC"}
    return hist, sub


def test_clasifica_simulado_real_y_fuera():
    hist, sub = _mundo()
    d = e22.datos_estres({"FFA": 3.0, "FFB": 1.0, "FFC": 1.0, "TARDE": 1.0, "RRR": 2.0}, {"RRR": 1.0},
                         hist, PARAM_SINT, sub)
    # FFC: subyacente sin historia → fuera. TARDE: empieza después de la ventana → fuera.
    assert d["simulados"] == ["FFA", "FFB"]
    assert d["subyacente"] == {"FFA": "UUA", "FFB": "UUB"}
    assert d["reales"] == ["RRR"]
    assert d["fuera"] == ["FFC", "TARDE"]
    assert d["limitante"] == "UUB"
    assert d["inicio"] == "2021-04-14" and d["dias"][0] == 1


def test_sin_nada_que_simular_o_sin_un_grupo_no_hay_estres():
    hist, sub = _mundo()
    assert e22.datos_estres({"RRR": 1.0}, {"RRR": 1.0}, hist, PARAM_SINT, sub) is None
    assert e22.datos_estres({"FFA": 1.0}, {"TARDE": 1.0}, hist, PARAM_SINT, sub) is None
    assert e22.datos_estres({"FFC": 1.0}, {"RRR": 1.0}, hist, PARAM_SINT, sub) is None


def test_la_banda_mueve_solo_la_prima():
    hist, sub = _mundo()
    d = e22.datos_estres({"FFA": 1.0}, {"RRR": 1.0}, hist, PARAM_SINT, sub)
    assert d["div_bajo"] != d["div"] != d["div_alto"]
    # Un fondo real en el grupo de dividendos no se mueve con la banda.
    d2 = e22.datos_estres({"RRR": 1.0, "FFA": 0.000001}, {"RRR": 1.0}, hist, PARAM_SINT, sub)
    assert d2["div_bajo"] == pytest.approx(d2["div"], abs=1e-4)


def test_subyacentes_yieldmax_descarta_lo_que_no_es_un_ticker():
    ins = {"AAA": {"type": "yieldmax", "underlying": "BBB"}, "MULTI": {"type": "yieldmax", "underlying": "Multi"},
           "ETF": {"type": "etf", "underlying": "CCC"}, "SIN": {"type": "yieldmax", "underlying": None}}
    assert e22.subyacentes_yieldmax(ins) == {"AAA": "BBB"}


def test_simular_arranca_en_inicio_y_termina_en_fin():
    h = _historia_sintetica("2021-03-01", 100, 5)
    ini, fin = h.index[30], h.index[80]
    s = e22.simular(h["Close"], 5, 0.05, 1.0, ini, fin)
    assert s.index[0] == h.index[31] and s.index[-1] == fin and len(s) == 50


def test_parametros_reales_cubren_los_cinco_fondos_y_la_validacion():
    p = _params()
    assert set(p["fondos"]) == set(FONDOS) == set(p["calibrados_hasta_2024"]) == set(p["validacion"]["fondos"])
    assert e22.filas_modal(p)["desde"] == "2025-01-02"


# ── Conexión: ui.riesgo → adapters → riesgo_mezcla ────────────────────────────

def _sub_y_hist():
    hist, _ = _mundo()
    return hist


def test_datos_seccion_pone_estres_en_cada_modo_con_los_pesos_de_cada_grupo():
    import riesgo_mezcla as rm

    llamadas = []

    def _estres(pd_, pc_):
        llamadas.append((dict(pd_), dict(pc_)))
        return {"marca": len(llamadas)}

    n = 150
    idx = pd.bdate_range("2024-01-01", periods=n)
    hist = {t: pd.DataFrame({"Close": 100 + 0.1 * np.arange(n) + (i % 3), "Dividends": 0.0}, index=idx)
            for i, t in enumerate(("AAA", "BBB", "CCC"))}
    receta = {"nombre": "R", "canasta": "Canasta R", "pct_dividendos": 70, "dividendos": ["AAA"], "crecimiento": ["CCC"]}
    datos = rm.datos_seccion({"BBB": 5.0}, {"CCC": 7.0}, hist, receta, estres=_estres)
    assert [m["estres"] for m in datos["modos"]] == [{"marca": 1}, {"marca": 2}]
    assert llamadas == [({"BBB": 5.0}, {"CCC": 7.0}), ({"AAA": 1.0}, {"CCC": 1.0})]
    assert all(m["estres"] is None for m in rm.datos_seccion({"BBB": 5.0}, {"CCC": 7.0}, hist)["modos"])


def test_estres_para_une_parametros_subyacentes_y_modal(monkeypatch):
    from ui import riesgo

    pedidos = []
    monkeypatch.setattr(riesgo, "_historias_estres", lambda tickers: pedidos.append(tickers) or {})
    fn, modal = riesgo._estres_para({"MSTY", "CONY", "SCHB", "ZZZZ"}, None)
    # Los YieldMax piden su acción, no ellos mismos; lo demás se pide tal cual.
    assert pedidos == [("COIN", "MSTR", "SCHB", "ZZZZ")]
    assert [f["fondo"] for f in modal["filas"]] == list(FONDOS) or set(f["fondo"] for f in modal["filas"]) == set(FONDOS)
    assert fn({"MSTY": 1.0}, {"SCHB": 1.0}) is None, "sin historia de 2022 no hay simulación"


def test_la_historia_de_2022_no_baja_nada_en_vivo(monkeypatch):
    """CLAUDE.md: no se llama a yfinance desde la UI. Con la red cortada, lo congelado entra y lo
    que no está queda fuera sin pedir nada. Una descarga en vivo de vuelta en `_historias_estres`
    deja su intento anotado aquí aunque la excepción se trague dentro."""
    import socket

    import backtest
    import yfinance as yf
    from ui import riesgo

    intentos = []

    def _sin_red(*a, **k):
        intentos.append(a[:1])
        raise ConnectionError("red cortada en el test")

    for objeto, nombre in ((backtest, "fetch_history"), (yf, "Ticker"), (yf, "download"),
                           (socket.socket, "connect"), (socket.socket, "connect_ex")):
        monkeypatch.setattr(objeto, nombre, _sin_red)
    riesgo._historias_estres.clear()
    try:
        h = riesgo._historias_estres(("SCHB", "ZZZZ"))
    finally:
        riesgo._historias_estres.clear()
    assert intentos == []
    assert set(h) == {"SCHB"} and list(h["SCHB"].columns) == ["Close", "Dividends"]


def test_todo_fondo_que_la_app_reconoce_tiene_su_2022_congelado(monkeypatch):
    """Sin descarga en vivo, un fondo de las listas blancas cuyo 2022 no esté congelado quedaría
    fuera de la simulación en silencio. Todo lo que `_estres_para` pide para ellos (la acción de un
    YieldMax con subyacente, el propio ticker del resto) tiene su archivo, o `_meta.yaml` lo
    declara sin sesiones en la ventana: nació después, o Yahoo no lo conoce.
    Si falla tras sumar un fondo o un subyacente: `./.venv/bin/python fetch_estres_2022.py`."""
    from ui import riesgo

    cargar = riesgo._historias_estres
    pedidos = []
    monkeypatch.setattr(riesgo, "_historias_estres", lambda tickers: pedidos.append(tickers) or {})
    riesgo._estres_para(logic.YIELDMAX_WHITELIST | logic.ETF_WHITELIST, None)
    assert len(pedidos) == 1
    cargar.clear()
    historias = cargar(pedidos[0])
    with open(META, encoding="utf-8") as fh:
        meta = yaml.safe_load(fh)
    sin_sesiones = {t for t, m in meta.items() if m["rows"] == 0}

    faltan = sorted(set(pedidos[0]) - set(historias) - sin_sesiones)
    assert not faltan, f"sin 2022 congelado ni declarado: {faltan}"
    assert not set(historias) & sin_sesiones
    assert {t: len(h) for t, h in historias.items()} == {t: meta[t]["rows"] for t in historias}
    v = _params()["ventana"]
    assert e22._cubre(historias["SPY"], pd.Timestamp(v["inicio"]), pd.Timestamp(v["fin"])), (
        "el snapshot ya no cubre la ventana de parametros.yaml: volver a congelar")


def test_render_con_estres_dibuja_el_bloque_y_sin_receta_en_el_html(monkeypatch):
    from ui import componentes

    capturado = {}
    monkeypatch.setattr(componentes.components, "html", lambda html, height=None, scrolling=None: capturado.update(html=html))
    est = _estres_sintetico()
    n = 120
    modo = {"clave": "tus", "boton": "Tus fondos", "grupos": [], "nota": None, "inicio": "2024-01-01", "fin": "2024-06-01",
            "limitante": "XXX", "meses": 5, "corta": True, "dias_comunes": n, "dias": list(range(1, n + 1)),
            "div": [0.001] * n, "crec": [0.0005] * n, "rend_div": 0.1, "rend_crec": 0.01,
            "compra": {"i": 0, "fecha_real": None, "recortada": False}, "atajos": [], "p_inicial": 50, "estres": est}
    datos = {"modo_inicial": "tus", "aviso": None, "modos": [modo], "estres_modal": e22.filas_modal(_params())}
    componentes.render_riesgo(datos, "Claro")
    html = capturado["html"]
    assert 'id="estres"' in html and 'id="modal-estres"' in html and "Simulación" in html
    inicio = html.index("var DATA = ") + len("var DATA = ")
    assert json.loads(html[inicio:html.index(";\n", inicio)])["modos"][0]["estres"]["simulados"] == ["XXX"]
    for prohibido in ("Greco", "80/20"):
        assert prohibido not in html
