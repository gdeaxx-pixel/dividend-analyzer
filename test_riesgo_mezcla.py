"""Tests de «Riesgo de la mezcla»: `riesgo_mezcla`, `ui.adapters.riesgo_mezcla_data`, la lectura
del secreto en `ui.riesgo` y el render de `ui/componentes/riesgo.html`.

Solo datos sintéticos: tickers inventados, historias armadas a mano con `pd.bdate_range` y una
receta sintética. Ninguna cifra esperada sale de la función auditada; la única comparación
entre dos implementaciones es la regla 3b (motor JS del componente contra `resumen_escenario`).
"""
import json
import os
import re
import shutil
import subprocess
import types

import pandas as pd
import pytest

import riesgo_mezcla as rm

RECETA = {"nombre": "Atajo X", "canasta": "Canasta X", "pct_dividendos": 70,
          "dividendos": ["AAA", "BBB"], "crecimiento": ["CCC"]}
INICIO = "2024-01-01"


def _hist(closes, divs=None, inicio=INICIO):
    idx = pd.bdate_range(inicio, periods=len(closes))
    divs = divs if divs is not None else [0.0] * len(closes)
    return pd.DataFrame({"Close": closes, "Dividends": divs}, index=idx)


def _serie(n, inicio=INICIO, base=100.0, paso=0.3):
    return _hist([base + paso * (i % 7) + 0.05 * i for i in range(n)], inicio=inicio)


def _modo(datos, clave):
    return next(m for m in datos["modos"] if m["clave"] == clave)


# ── Cálculo ────────────────────────────────────────────────────────────────────

def test_retorno_total_reinvierte_dividendo():
    h = _hist([10.0, 11.0, 10.5], [0.0, 0.0, 0.5])
    r = rm.retorno_total(h)
    # día 2: 11 / 10 − 1; día 3: (10.5 + 0.5) / 11 − 1 = 0 (el dividendo compensa la caída)
    assert list(r.index) == list(pd.bdate_range(INICIO, periods=3)[1:])
    assert r.iloc[0] == pytest.approx(0.10)
    assert r.iloc[1] == pytest.approx(0.0)


def test_entrada_es_el_primer_cierre_del_fondo_mas_joven():
    hist = {"AAA": _serie(200), "CCC": _serie(100, inicio="2024-03-01")}
    datos = rm.datos_seccion({"AAA": 1.0}, {"CCC": 1.0}, hist)
    modo = _modo(datos, "tus")
    assert modo["inicio"] == "2024-03-01"


def test_entrada_limitante_es_el_fondo_mas_joven():
    hist = {"AAA": _serie(200), "CCC": _serie(100, inicio="2024-03-01")}
    modo = _modo(rm.datos_seccion({"AAA": 1.0}, {"CCC": 1.0}, hist), "tus")
    assert modo["limitante"] == "CCC"
    # 100 cierres de CCC → 99 retornos, todos posteriores a la entrada y comunes con AAA
    assert modo["dias_comunes"] == 99


def test_compra_anterior_a_la_ventana_se_recorta():
    hist = {"AAA": _serie(200), "CCC": _serie(100, inicio="2024-03-01")}
    datos = rm.datos_seccion({"AAA": 1.0}, {"CCC": 1.0}, hist, compra_real=pd.Timestamp("2024-01-15"))
    compra = _modo(datos, "tus")["compra"]
    assert compra == {"i": 0, "fecha_real": "2024-01-15", "recortada": True}


def test_compra_dentro_de_la_ventana_entra_al_cierre_de_ese_dia():
    hist = {"AAA": _serie(200), "CCC": _serie(100, inicio="2024-03-01")}
    # 2024-03-01 es viernes (entrada, i=0); 2024-03-15 es el 10.º día hábil después → i=10
    datos = rm.datos_seccion({"AAA": 1.0}, {"CCC": 1.0}, hist, compra_real=pd.Timestamp("2024-03-15"))
    assert _modo(datos, "tus")["compra"] == {"i": 10, "fecha_real": "2024-03-15", "recortada": False}
    # Compra en sábado 2024-03-16 → entra al último cierre disponible, el viernes 15 (i=10)
    datos = rm.datos_seccion({"AAA": 1.0}, {"CCC": 1.0}, hist, compra_real=pd.Timestamp("2024-03-16"))
    assert _modo(datos, "tus")["compra"]["i"] == 10


def test_grupo_faltante_se_completa_con_la_canasta():
    hist = {t: _serie(150) for t in ("AAA", "BBB", "CCC")}
    datos = rm.datos_seccion({"AAA": 1000.0}, {}, hist, RECETA)
    assert datos["modo_inicial"] == "tus"
    assert [m["clave"] for m in datos["modos"]] == ["tus", "greco"]
    tus = _modo(datos, "tus")
    assert tus["grupos"][0]["fondos"] == ["AAA"] and tus["grupos"][0]["referencia"] is None
    assert tus["grupos"][1]["fondos"] == ["CCC"] and tus["grupos"][1]["referencia"] == "Canasta X"
    assert tus["nota"] == "Crecimiento: no tienes fondos de este grupo; usamos la canasta X."
    assert _modo(datos, "greco")["boton"] == "Canasta X"


def test_sin_receta_y_grupo_faltante_no_hay_seccion():
    hist = {t: _serie(150) for t in ("AAA", "CCC")}
    assert rm.datos_seccion({"AAA": 1000.0}, {}, hist, None) is None


def test_ticker_de_receta_sin_historia_no_crea_modo_greco():
    hist = {t: _serie(150) for t in ("AAA", "CCC")}
    receta = dict(RECETA, dividendos=["AAA", "DDD"])
    datos = rm.datos_seccion({"AAA": 1000.0}, {"CCC": 1000.0}, hist, receta)
    assert [m["clave"] for m in datos["modos"]] == ["tus"]
    assert "Atajo X" not in [a["etiqueta"] for a in _modo(datos, "tus")["atajos"]]


def test_menos_de_60_dias_no_hay_modo_tus_y_avisa():
    hist = {"AAA": _serie(150), "BBB": _serie(150), "CCC": _serie(150),
            "DDD": _serie(40, inicio="2024-06-03")}
    datos = rm.datos_seccion({"AAA": 1000.0}, {"DDD": 1000.0}, hist, RECETA)
    assert [m["clave"] for m in datos["modos"]] == ["greco"]
    assert datos["modo_inicial"] == "greco"
    # 40 cierres de DDD → 39 días en común
    assert datos["aviso"] == ("Tus fondos solo tienen 39 días de historia en común. "
                              "Te mostramos la canasta X.")


def test_mezcla_del_usuario_y_atajos():
    hist = {t: _serie(150) for t in ("AAA", "BBB", "CCC")}
    datos = rm.datos_seccion({"AAA": 3000.0, "BBB": 1000.0}, {"CCC": 6000.0}, hist, RECETA)
    tus = _modo(datos, "tus")
    # 4.000 de 10.000 en dividendos → 40/60
    assert tus["p_inicial"] == 40
    assert tus["atajos"] == [
        {"etiqueta": "Tu portafolio", "detalle": "40/60", "p": 40},
        {"etiqueta": "Atajo X", "detalle": "70/30", "p": 70},
        {"etiqueta": "Mitad y mitad", "detalle": "50/50", "p": 50},
        {"etiqueta": "Solo crecimiento", "detalle": "0/100", "p": 0},
    ]
    assert tus["grupos"][0]["fondos"] == ["AAA", "BBB"]


def test_rendimiento_12m_anualiza_historia_corta():
    divs = [0.0] * 100
    divs[20] = divs[60] = 0.1
    h = _hist([10.0] * 100, divs)
    fin = pd.bdate_range(INICIO, periods=100)[-1]
    assert str(fin.date()) == "2024-05-17"
    # 0,20 cobrados en 137 días (1-ene → 17-may) sobre un precio de 10, llevado a 365 días
    assert rm.rendimiento_12m(h, fin) == pytest.approx(0.2 / 10 * 365 / 137)


# ── Regla 3b: motor JS del componente = resumen_escenario ─────────────────────

def _datos_motor():
    n = 160
    # Dividendos: sube, cae ~30 % y recupera a medias, con un dividendo cada 20 días.
    div = [20 + 0.05 * i if i < 60 else (23 - 0.12 * (i - 60) if i < 110 else 17 + 0.04 * (i - 110))
           for i in range(n)]
    divs = [0.15 if i % 20 == 19 else 0.0 for i in range(n)]
    # Crecimiento: tendencia suave con un bache corto.
    crec = [50 + 0.08 * i - (3 if 80 <= i < 95 else 0) + 0.4 * ((i % 5) - 2) for i in range(n)]
    hist = {"AAA": _hist(div, divs), "CCC": _hist(crec)}
    return rm.datos_seccion({"AAA": 1000.0}, {"CCC": 1000.0}, hist,
                            compra_real=pd.Timestamp("2024-02-12"))


def test_motor_js_igual_a_python(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("no hay node en el PATH: no se puede correr el motor del componente")
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "componentes", "riesgo.html")
    html = open(ruta, encoding="utf-8").read()
    motor = re.search(r'<script id="motor">(.*?)</script>', html, re.S).group(1)
    modo = _modo(_datos_motor(), "tus")
    assert modo["compra"]["i"] > 0
    js = motor + """
var M = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8")), X = Motor.crear(M), out = {};
[0, 37, 70, 100].forEach(function (p) { ["compra", "peor"].forEach(function (e) {
  var q = p / 100, vol = X.volatilidad(q), s = X.escenario(q, e), f = s.mezcla.length - 1;
  out[p + "|" + e] = { nivel: X.nivel(vol), vol: vol, dividendos: X.dividendos(q), desde: s.desde,
    min: s.mezcla[s.minM], min_i: s.desde + s.minM, hoy: s.mezcla[f], min_crec: s.crec[s.minG],
    hoy_crec: s.crec[f], recupera: s.mezcla[s.minM] < 10000 ? (s.recM < 0 ? -1 : s.desde + s.recM) : null };
}); });
console.log(JSON.stringify(out));"""
    (tmp_path / "m.js").write_text(js)
    (tmp_path / "d.json").write_text(json.dumps(modo))
    salida = json.loads(subprocess.run(["node", str(tmp_path / "m.js"), str(tmp_path / "d.json")],
                                       capture_output=True, text=True, check=True).stdout)
    hubo_peor_distinto = False
    for p in (0, 37, 70, 100):
        for e in ("compra", "peor"):
            py, j = rm.resumen_escenario(modo, p, e), salida[f"{p}|{e}"]
            for c in ("dividendos", "min", "hoy", "min_crec", "hoy_crec"):
                assert abs(py[c] - j[c]) <= 1, f"{p}|{e} {c}: python {py[c]}, js {j[c]}"
            assert abs(py["vol"] - j["vol"]) <= 0.05, f"{p}|{e} vol: python {py['vol']}, js {j['vol']}"
            for c in ("nivel", "desde", "min_i", "recupera"):
                assert py[c] == j[c], f"{p}|{e} {c}: python {py[c]}, js {j[c]}"
            hubo_peor_distinto |= e == "peor" and py["desde"] != modo["compra"]["i"]
    assert hubo_peor_distinto, "los datos sintéticos no distinguen «compra» de «peor»"


# ── Adapter, secreto y render ─────────────────────────────────────────────────

def _tx(*filas):
    return pd.DataFrame(filas, columns=["Date", "Action"])


def test_adapter_usa_valor_de_mercado_y_filtra_sin_datos():
    from ui.adapters import riesgo_mezcla_data

    resultados = {
        "AAA": {"market_value": 3000.0, "pocket_investment": 100.0,
                "history": _tx(("2024-02-05", "Dividend"), ("2024-03-11", "Buy"))},
        "BBB": {"market_value": 1000.0, "pocket_investment": 9000.0,
                "history": _tx(("2024-04-01", "Bought"))},
        "CCC": {"market_value": 6000.0, "pocket_investment": 50.0,
                "history": _tx(("2024-03-04", "Compra"), ("2024-03-20", "Compra"))},
        # `logic.py` hoy no deja `market_value` en un descartado; el filtro no debe depender de eso.
        "DDD": {"skipped": True, "reason": "menos de 14 días", "market_value": 5000.0},
        "EEE": {"market_value": 0.0, "pocket_investment": 500.0,
                "history": _tx(("2024-01-02", "Buy"))},
    }
    classify = {"AAA": "mode_a", "BBB": "mode_a", "DDD": "mode_a", "CCC": "mode_b", "EEE": "mode_b"}
    hist = {t: _serie(150) for t in ("AAA", "BBB", "CCC", "DDD", "EEE")}
    datos = riesgo_mezcla_data(resultados, classify, hist, None)
    tus = _modo(datos, "tus")
    # 3.000 + 1.000 de 10.000 → 40/60; EEE (valor 0) y DDD (sin datos) quedan fuera
    assert tus["p_inicial"] == 40
    assert tus["grupos"][0]["fondos"] == ["AAA", "BBB"]
    assert tus["grupos"][1]["fondos"] == ["CCC"]
    # primera compra entre los fondos que entran, de los DOS grupos: la de CCC (Crecimiento)
    # el 4-mar gana a la de AAA el 11-mar, y el dividendo de AAA del 5-feb no cuenta
    assert tus["compra"]["fecha_real"] == "2024-03-04"


def _st_falso(cargado, secreto, llamadas):
    def get(clave, defecto=None):
        llamadas.append(clave)
        return secreto if clave == "receta_referencia" else defecto
    secrets = types.SimpleNamespace(load_if_toml_exists=lambda: cargado, get=get)
    return types.SimpleNamespace(secrets=secrets)


def test_receta_referencia_sin_archivo_no_toca_secrets(monkeypatch):
    from ui import riesgo

    llamadas = []
    monkeypatch.setattr(riesgo, "st", _st_falso(False, dict(RECETA), llamadas))
    assert riesgo._receta_referencia() is None
    assert llamadas == []


def test_receta_referencia_valida_y_rechaza_incompleta(monkeypatch):
    from ui import riesgo

    llamadas = []
    monkeypatch.setattr(riesgo, "st", _st_falso(True, dict(RECETA, dividendos=("AAA", "BBB")), llamadas))
    assert riesgo._receta_referencia() == dict(RECETA)
    for malo in (dict(RECETA, pct_dividendos=120), dict(RECETA, crecimiento=[]),
                 dict(RECETA, nombre=None), dict(RECETA, dividendos="AAA")):
        monkeypatch.setattr(riesgo, "st", _st_falso(True, malo, llamadas))
        assert riesgo._receta_referencia() is None, malo


def _resultado(valor, compra="2024-03-11"):
    return {"market_value": valor, "pocket_investment": 100.0, "history": _tx((compra, "Buy"))}


def _espiar_render_riesgo(monkeypatch):
    from ui import componentes

    llamadas = []
    monkeypatch.setattr(componentes, "render_riesgo", lambda datos, tema: llamadas.append(datos))
    return llamadas


def test_sin_historia_solo_avisa_de_fondos_del_usuario(monkeypatch):
    from ui import riesgo

    resultados = {"UUU": _resultado(3000.0), "VVV": _resultado(1000.0), "WWW": _resultado(6000.0)}
    classify = {"UUU": "mode_a", "VVV": "mode_a", "WWW": "mode_b"}
    historias = {t: _serie(150) for t in ("UUU", "WWW", "AAA", "CCC")}
    monkeypatch.setattr(riesgo, "_receta_referencia", lambda: dict(RECETA))
    monkeypatch.setattr(riesgo, "_historias_riesgo", lambda tickers: (historias, ["BBB", "VVV"]))
    llamadas = _espiar_render_riesgo(monkeypatch)

    riesgo._riesgo_mezcla(resultados, classify, "Claro")

    assert len(llamadas) == 1
    nota = _modo(llamadas[0], "tus")["nota"]
    assert nota == "Sin historia de precios, fuera de la simulación: VVV."
    assert "BBB" not in nota


def test_riesgo_vista_sin_archivo(monkeypatch):
    from ui import riesgo, vistas

    llamadas_st = []
    st_falso = types.SimpleNamespace(
        caption=lambda texto: llamadas_st.append(("caption", texto)),
        markdown=lambda texto, **kw: llamadas_st.append(("markdown", texto)))
    monkeypatch.setattr(riesgo, "st", st_falso)
    monkeypatch.setattr(vistas, "obtener_resultados", lambda: {})
    monkeypatch.setattr(riesgo, "_historias_riesgo",
                        lambda tickers: ({t: _serie(150) for t in ("AAA", "BBB", "CCC")}, []))
    llamadas = _espiar_render_riesgo(monkeypatch)
    ruta = types.SimpleNamespace(tema="Claro")

    monkeypatch.setattr(riesgo, "_receta_referencia", lambda: dict(RECETA))
    riesgo.render_vista("riesgo", ruta)
    assert len(llamadas) == 1
    assert [m["clave"] for m in llamadas[0]["modos"]] == ["greco"]
    assert ("caption", "Sube tu archivo de transacciones para comparar con tus fondos.") in llamadas_st

    llamadas.clear()
    llamadas_st.clear()
    monkeypatch.setattr(riesgo, "_receta_referencia", lambda: None)
    riesgo.render_vista("riesgo", ruta)
    assert llamadas == []
    assert [k for k, _ in llamadas_st] == ["markdown"] * 3
    assert "Riesgo" in llamadas_st[0][1] and "Riesgo" in llamadas_st[1][1]


def test_render_riesgo_inyecta_datos_y_tema(monkeypatch):
    from ui import componentes

    capturado = {}

    def _spy(html, height=None, scrolling=None):
        capturado.update(html=html, height=height, scrolling=scrolling)

    monkeypatch.setattr(componentes.components, "html", _spy)
    datos = _datos_motor()
    componentes.render_riesgo(datos, "Oscuro")

    html = capturado["html"]
    assert "{{" not in html, "quedó un placeholder sin sustituir"
    assert 'data-theme", "dark"' in html
    inicio = html.index("var DATA = ") + len("var DATA = ")
    fin = html.index(";\n", inicio)
    assert json.loads(html[inicio:fin]) == json.loads(json.dumps(datos))
    assert capturado["height"] == componentes.ALTO_RIESGO and capturado["scrolling"] is False
