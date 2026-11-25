"""Tests de `tools/mapa_riesgo.py`, las cifras de los mapas de riesgo de la nota de Valuación.

Sin red y sin datos privados: cada test arma su historia en `tmp_path` y compara contra cifras que
se sacan a mano de esa historia (forma cerrada), nunca contra las funciones del propio CLI.

Escenario chico (`_escenario`), seis viernes de 2024:
- FON cierra 10, 10, 10, 20, 20, 25 y paga 0.70 el día de compra (no cuenta) y 0.50 el 19-ene.
  Con 10,000 compra 1,000 acciones. Reinvirtiendo, el pago compra 50 más a 10: 1,050 × 25 =
  26,250. Cobrando, quedan 1,000 × 25 = 25,000 invertidos y 500 en efectivo: 25,500.
- ACC sube 10 %, baja 10 %, sube 10 %, sube 20 % y baja 10 %.
- MKT es el mercado. En el Mapa A cierra 50 el 30-dic-2011, 80 el 8-feb-2023 y 100 el día T.
"""
import ast
import importlib.util
import json
import math
import socket
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parent
CLI = RAIZ / "tools" / "mapa_riesgo.py"

SEMANAS = ["2024-01-05", "2024-01-12", "2024-01-19", "2024-01-26", "2024-02-02", "2024-02-09"]
UNIVERSO = dict(parejas=[("ACC", "FON")], referencias=["MKT"], inicio_b="2024-01-05",
                fondos_a=["MKT"], anios_a=[1], mercado="MKT")
CAMPOS_SERIE = {"inicio", "fin", "dias", "rendimiento_anual", "se_mueve", "peor_caida", "pico", "piso",
                "recupera", "semana_normal_usd", "valor_final", "base", "momento"}
CAMPOS_COBRANDO = {"sigue_invertido", "efectivo_cobrado"}


@pytest.fixture(scope="module")
def mr():
    spec = importlib.util.spec_from_file_location("mapa_riesgo_cli", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _guardar(carpeta, tk, filas):
    carpeta.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(filas, columns=["Date", "Close", "Dividends"]).to_csv(carpeta / f"{tk}.csv", index=False)


def _escenario(tmp_path, **cambios):
    b, a = tmp_path / "b", tmp_path / "a"
    filas = {
        "ACC": list(zip(SEMANAS, [100, 110, 99, 108.9, 130.68, 117.612], [0] * 6)),
        "FON": list(zip(SEMANAS, [10, 10, 10, 20, 20, 25], [0.7, 0, 0.5, 0, 0, 0])),
        "MKT": list(zip(SEMANAS, [100, 101, 99, 102, 104, 103], [0] * 6)),
        "A_MKT": [("2011-12-30", 50, 0), ("2012-06-29", 60, 0), ("2023-02-08", 80, 0),
                  ("2023-02-10", 88, 0), ("2024-02-02", 90, 0), ("2024-02-09", 100, 0),
                  ("2024-02-16", 120, 0)],
    }
    filas.update(cambios)
    for tk, f in filas.items():
        if tk.startswith("A_"):
            _guardar(a, tk[2:], f)
        else:
            _guardar(b, tk, f)
    return a, b


def _calcular(mr, tmp_path, **cambios):
    a, b = _escenario(tmp_path, **cambios)
    return mr.calcular(a, b, **UNIVERSO)


# ---- métricas de una serie, en forma cerrada ----

def test_rendimiento_anual_cuenta_anios_de_365_25_dias(mr):
    v = pd.Series([100.0, 150.0, 200.0], index=pd.to_datetime(["2020-01-01", "2022-01-01", "2024-01-01"]))
    m = mr.metricas_serie(v, 10_000)
    assert m["dias"] == 1461
    assert m["rendimiento_anual"] == pytest.approx(2 ** 0.25 - 1, rel=1e-12)


def test_se_mueve_es_la_desviacion_muestral_anualizada_con_252(mr):
    v = pd.Series([100, 101, 99.99, 100.9899, 99.980001], index=pd.bdate_range("2024-01-01", periods=5))
    m = mr.metricas_serie(v, 10_000)
    esperado = math.sqrt(4 * 0.01 ** 2 / 3) * math.sqrt(252)
    assert m["se_mueve"] == pytest.approx(esperado, rel=1e-9)
    assert m["semana_normal_usd"] == pytest.approx(10_000 * esperado / math.sqrt(52), rel=1e-9)


def test_peor_caida_mide_desde_el_pico_anterior_al_piso(mr):
    idx = pd.bdate_range("2024-01-01", periods=6)
    m = mr.metricas_serie(pd.Series([100, 120, 90, 130, 117, 140.0], index=idx), 10_000)
    assert m["peor_caida"] == pytest.approx(-0.25, abs=1e-12)
    assert (m["pico"], m["piso"], m["recupera"]) == tuple(str(idx[i].date()) for i in (1, 2, 3))


def test_recupera_al_igualar_el_pico_y_none_si_no_llega(mr):
    idx = pd.bdate_range("2024-01-01", periods=4)
    assert mr.metricas_serie(pd.Series([100, 120, 90, 120.0], index=idx), 1)["recupera"] == str(idx[3].date())
    assert mr.metricas_serie(pd.Series([100, 120, 90, 110.0], index=idx), 1)["recupera"] is None


# ---- el cálculo entero sobre el escenario chico ----

def test_reinvirtiendo_y_cobrando_dan_lo_que_sale_a_mano(mr, tmp_path):
    d = _calcular(mr, tmp_path)
    par = d["mapa_b"]["parejas"][0]
    s, ant = par["series"], par["en_cierre_anterior"]
    assert (par["accion"], par["fondo"]) == ("ACC", "FON")
    assert s["FON_reinvirtiendo"]["valor_final"] == pytest.approx(26_250, rel=1e-12)
    assert s["FON_cobrando"]["valor_final"] == pytest.approx(25_500, rel=1e-12)
    assert s["FON_cobrando"]["sigue_invertido"] == pytest.approx(25_000, rel=1e-12)
    assert s["FON_cobrando"]["efectivo_cobrado"] == pytest.approx(500, rel=1e-12)
    assert s["ACC"]["valor_final"] == pytest.approx(10_000 * 117.612 / 100, rel=1e-12)
    assert ant["FON_reinvirtiendo"]["valor_final"] == pytest.approx(21_000, rel=1e-12)
    assert ant["FON_cobrando"]["valor_final"] == pytest.approx(20_500, rel=1e-12)


def test_solo_cobrando_lleva_lo_que_sigue_invertido_y_el_efectivo(mr, tmp_path):
    s = _calcular(mr, tmp_path)["mapa_b"]["parejas"][0]["series"]
    assert CAMPOS_COBRANDO <= set(s["FON_cobrando"])
    assert not CAMPOS_COBRANDO & set(s["FON_reinvirtiendo"])
    assert not CAMPOS_COBRANDO & set(s["ACC"])


def test_todo_es_antes_de_impuestos_y_lo_dice(mr, tmp_path):
    d = _calcular(mr, tmp_path)
    assert (d["base"], d["base_texto"]) == ("bruto", "Antes de impuestos")
    assert any("Antes de impuestos" in x for x in d["supuestos"])
    series = [s for p in d["mapa_b"]["parejas"] for k in ("series", "en_cierre_anterior") for s in p[k].values()]
    series += list(d["mapa_b"]["referencias"].values())
    series += [s for p in d["mapa_a"]["periodos"] for k in ("series", "en_cierre_anterior") for s in p[k].values()]
    assert series and {s["base"] for s in series} == {"bruto"}


def test_el_ultimo_cierre_y_el_anterior_salen_del_mercado(mr, tmp_path):
    d = _calcular(mr, tmp_path)
    assert (d["T"], d["T_anterior"]) == ("2024-02-09", "2024-02-02")
    par = d["mapa_b"]["parejas"][0]
    assert par["series"]["FON_cobrando"]["momento"] == "al cierre del 2024-02-09"
    assert par["en_cierre_anterior"]["FON_cobrando"]["momento"] == "al cierre del 2024-02-02"
    assert par["series"]["FON_cobrando"]["fin"] == "2024-02-09"
    assert par["en_cierre_anterior"]["FON_cobrando"]["fin"] == "2024-02-02"


def test_mapa_a_compra_el_ultimo_dia_habil_antes_de_cada_corte(mr, tmp_path):
    pa = {p["id"]: p for p in _calcular(mr, tmp_path)["mapa_a"]["periodos"]}
    assert list(pa) == ["desde-2012", "1-anios"]
    assert pa["desde-2012"]["compra"] == "2011-12-30"
    assert pa["1-anios"]["compra"] == "2023-02-08"
    assert pa["desde-2012"]["series"]["MKT"]["valor_final"] == pytest.approx(20_000, rel=1e-12)
    assert pa["desde-2012"]["en_cierre_anterior"]["MKT"]["valor_final"] == pytest.approx(18_000, rel=1e-12)
    assert pa["1-anios"]["series"]["MKT"]["valor_final"] == pytest.approx(12_500, rel=1e-12)
    assert pa["1-anios"]["en_cierre_anterior"]["MKT"]["valor_final"] == pytest.approx(11_250, rel=1e-12)


def test_mapa_a_se_corta_en_el_ultimo_cierre_del_mapa_b(mr, tmp_path):
    p = _calcular(mr, tmp_path)["mapa_a"]["periodos"][0]
    assert p["series"]["MKT"]["fin"] == "2024-02-09"


def test_la_linea_de_mercado_es_rendimiento_entre_movimiento_del_mercado(mr, tmp_path):
    d = _calcular(mr, tmp_path)
    mk = d["mapa_b"]["referencias"]["MKT"]
    assert d["mapa_b"]["linea_mercado"] == {"pendiente": pytest.approx(mk["rendimiento_anual"] / mk["se_mueve"]),
                                            "de": "MKT"}
    for p in d["mapa_a"]["periodos"]:
        s = p["series"]["MKT"]
        assert p["linea_mercado"]["pendiente"] == pytest.approx(s["rendimiento_anual"] / s["se_mueve"])


def test_semanas_fuertes_de_la_accion_en_forma_cerrada(mr, tmp_path):
    w = _calcular(mr, tmp_path)["mapa_b"]["semanas"]["parejas"]["ACC"]
    assert (w["fondo"], w["semanas"], w["fuertes"], w["resto"]) == ("FON", 5, 1, 4)
    assert w["accion_fuertes"] == pytest.approx(0.2, abs=1e-12)
    assert w["accion_resto"] == pytest.approx(1.089 * 0.9 - 1, abs=1e-12)
    assert w["reinvirtiendo"]["fondo_fuertes"] == pytest.approx(0.0, abs=1e-12)
    assert w["reinvirtiendo"]["fondo_resto"] == pytest.approx(26_250 / 10_000 - 1, abs=1e-12)
    assert w["cobrando"]["fondo_resto"] == pytest.approx(25_500 / 10_000 - 1, abs=1e-12)
    assert w["reinvirtiendo"]["gana_fondo_resto"] == pytest.approx(0.75)
    assert w["cobrando"]["gana_fondo_resto"] == pytest.approx(0.75)


def test_la_semana_es_el_ultimo_cierre_de_cada_viernes(mr):
    idx = pd.to_datetime(["2024-01-04", "2024-01-05", "2024-01-11", "2024-01-12", "2024-01-18", "2024-01-19"])

    class Corrida:
        daily = pd.DataFrame({"total_value": [90, 100, 95, 110, 130, 99.0]}, index=idx)

    r = mr.semanal(Corrida)
    assert list(r.index.strftime("%Y-%m-%d")) == ["2024-01-12", "2024-01-19"]
    assert r.tolist() == pytest.approx([0.10, -0.10], abs=1e-12)


def test_una_fila_mala_sin_pago_se_quita_y_se_anota(mr, tmp_path):
    acc = list(zip(SEMANAS, [100, float("nan"), 99, 108.9, 130.68, 117.612], [0] * 6))
    d = _calcular(mr, tmp_path, ACC=acc)
    assert d["filas_malas"] == [{"tk": "ACC", "fecha": "2024-01-12", "Close": None, "Dividends": 0.0,
                                 "accion": "quitada"}]


# ---- datos que no pasan: se para con el motivo ----

@pytest.mark.parametrize("cambios, motivo", [
    ({"FON": list(zip(SEMANAS[:-1], [10, 10, 10, 20, 20], [0.7, 0, 0.5, 0, 0]))}, "no termina el mismo día"),
    ({"FON": list(zip(SEMANAS, [10, 10, float("nan"), 20, 20, 25], [0.7, 0, 0.5, 0, 0, 0]))}, "fila mala con pago"),
    ({"FON": list(zip(SEMANAS, [10, 10, 10, 20, 20, 25], [0.7, 0, float("nan"), 0, 0, 0]))}, "fila mala con pago"),
    ({"FON": list(zip(SEMANAS[:1] + SEMANAS, [10] * 7, [0] * 7))}, "fechas repetidas"),
    ({"FON": list(zip(SEMANAS[1:], [10, 10, 20, 20, 25], [0] * 5))}, "no arranca el mismo día"),
    ({"FON": list(zip(SEMANAS[:4] + SEMANAS[5:], [10, 10, 10, 20, 25], [0] * 5))}, "falta el cierre del 2024-02-02"),
    ({"MKT": list(zip(SEMANAS, [100] * 6, [0] * 6))}, "no se movió"),
    ({"A_MKT": [("2011-12-30", 50, 0), ("2023-02-08", 80, 0), ("2024-02-02", 90, 0)]}, "no llega al 2024-02-09"),
    ({"A_MKT": [("2011-12-30", 50, 0), ("2023-02-08", 80, 0), ("2024-02-09", 100, 0)]}, "le falta el cierre del 2024-02-02"),
    ({"A_MKT": [("2012-01-03", 50, 0), ("2023-02-08", 80, 0), ("2024-02-02", 90, 0), ("2024-02-09", 100, 0)]},
     "empieza el 2012-01-03"),
])
def test_datos_que_no_pasan_paran_con_su_motivo(mr, tmp_path, cambios, motivo):
    with pytest.raises(mr.DatosMalos, match=motivo):
        _calcular(mr, tmp_path, **cambios)


def test_un_fondo_del_mapa_a_que_no_cotizo_el_dia_de_compra_para(mr, tmp_path):
    a, b = _escenario(tmp_path)
    _guardar(a, "OTR", [("2011-12-30", 5, 0), ("2023-02-10", 8, 0), ("2024-02-02", 9, 0), ("2024-02-09", 10, 0)])
    with pytest.raises(mr.DatosMalos, match="OTR no cotizó el 2023-02-08"):
        mr.calcular(a, b, **{**UNIVERSO, "fondos_a": ["MKT", "OTR"]})


def test_un_simbolo_que_falta_para(mr, tmp_path):
    a, b = _escenario(tmp_path)
    (b / "FON.csv").unlink()
    with pytest.raises(mr.DatosMalos, match="FON: no está en"):
        mr.calcular(a, b, **UNIVERSO)


# ---- lectura: CSV y el parquet del caché leen igual ----

def test_parquet_y_csv_dan_la_misma_historia(mr, tmp_path):
    h = pd.DataFrame({"Close": [10.0, 11.0], "Dividends": [0.0, 0.25]},
                     index=pd.DatetimeIndex(pd.to_datetime(["2024-01-05", "2024-01-12"]), name="Date"))
    (tmp_path / "pq").mkdir()
    h.to_parquet(tmp_path / "pq" / "X.parquet")
    _guardar(tmp_path / "csv", "X", [("2024-01-05", 10.0, 0.0), ("2024-01-12", 11.0, 0.25)])
    pd.testing.assert_frame_equal(mr.leer(tmp_path / "pq", "X"), mr.leer(tmp_path / "csv", "X"), check_freq=False,
                                  check_index_type=False)


def test_el_parquet_real_del_cache_se_lee_con_sus_fechas(mr):
    crudo = pd.read_parquet(RAIZ / "knowledge" / "price_cache" / "SCHB.parquet")
    h = mr.leer(RAIZ / "knowledge" / "price_cache", "SCHB")
    assert list(h.columns) == ["Close", "Dividends"] and len(h) == len(crudo)
    assert list(h.index.strftime("%Y-%m-%d")) == list(pd.DatetimeIndex(crudo.index).strftime("%Y-%m-%d"))


# ---- sin red ----

def test_el_cli_no_importa_nada_de_red_y_siempre_pasa_la_historia():
    arbol = ast.parse(CLI.read_text(encoding="utf-8"))
    prohibidos = {"yfinance", "requests", "urllib", "http", "socket", "price_cache"}
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            assert not {a.name.split(".")[0] for a in n.names} & prohibidos
        if isinstance(n, ast.ImportFrom):
            assert (n.module or "").split(".")[0] not in prohibidos
        if isinstance(n, ast.Attribute):
            assert n.attr not in {"fetch_history", "download", "load_history"}
    llamadas = [n for n in ast.walk(arbol) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == "run_backtest"]
    assert llamadas
    for c in llamadas:
        hist = [k.value for k in c.keywords if k.arg == "history"]
        assert hist and not (isinstance(hist[0], ast.Constant) and hist[0].value is None)


def test_el_calculo_no_baja_nada(mr, tmp_path, monkeypatch):
    """Yahoo se baja con curl_cffi, que no pasa por `socket`: por eso se vigila también la puerta
    del motor (`backtest.fetch_history`) y no solo los sockets de Python."""
    intentos = []

    def cortar(*a, **k):
        intentos.append(a)
        raise OSError("sin red en este test")

    monkeypatch.setattr(mr.backtest, "fetch_history", cortar)
    monkeypatch.setattr(socket.socket, "connect", cortar)
    monkeypatch.setattr(socket, "create_connection", cortar)
    monkeypatch.setattr(socket, "getaddrinfo", cortar)
    try:
        _calcular(mr, tmp_path)
    finally:
        assert intentos == []


# ---- de punta a punta, como lo corre la nota ----

def _historia_sintetica(fechas, base, paga_cada=0):
    filas, precio = [], base
    for i, f in enumerate(fechas):
        if i:
            precio *= 1.004 if i % 3 else 0.993
        filas.append((str(f.date()), round(precio, 4), 0.35 if paga_cada and i and i % paga_cada == 0 else 0.0))
    return filas


def _universo_por_defecto(tmp_path):
    b, a = tmp_path / "b", tmp_path / "a"
    dias_b = pd.bdate_range("2024-02-22", "2024-08-30")
    for i, tk in enumerate(["NVDA", "TSLA", "MSTR", "SCHB", "SMH"]):
        _guardar(b, tk, _historia_sintetica(dias_b, 50 + 10 * i))
    for i, tk in enumerate(["NVDY", "TSLY", "MSTY"]):
        _guardar(b, tk, _historia_sintetica(dias_b, 20 + 5 * i, paga_cada=21))
    dias_a = pd.bdate_range("2011-12-01", "2024-08-30")
    for i, tk in enumerate(["SCHB", "QQQ", "XLK", "SMH"]):
        _guardar(a, tk, _historia_sintetica(dias_a, 30 + 7 * i, paga_cada=63))
    return a, b


def _correr_cli(*args, cwd):
    return subprocess.run([sys.executable, "-I", "-B", str(CLI), *map(str, args)], cwd=cwd,
                          capture_output=True, text=True, timeout=300)


def test_de_punta_a_punta_la_salida_es_un_solo_json_con_el_contrato(tmp_path):
    a, b = _universo_por_defecto(tmp_path)
    r = _correr_cli("--historia-a", a, "--historia-b", b, cwd=tmp_path)
    assert r.returncode == 0, r.stderr[-2000:]
    assert r.stdout.count("\n") == 1 and r.stdout.startswith("{")
    d = json.loads(r.stdout)
    assert {"base", "base_texto", "T", "T_anterior", "capital", "origen", "supuestos", "filas_malas",
            "mapa_a", "mapa_b"} <= set(d)
    assert (d["T"], d["T_anterior"], d["capital"]) == ("2024-08-30", "2024-08-29", 10_000.0)
    assert [(p["accion"], p["fondo"]) for p in d["mapa_b"]["parejas"]] == [("NVDA", "NVDY"), ("TSLA", "TSLY"),
                                                                           ("MSTR", "MSTY")]
    assert set(d["mapa_b"]["referencias"]) == {"SCHB", "SMH", "SCHB_en_cierre_anterior", "SMH_en_cierre_anterior"}
    assert d["mapa_b"]["inicio"] == "2024-02-22" and d["mapa_b"]["linea_mercado"]["de"] == "SCHB"
    schb = pd.read_csv(b / "SCHB.csv")["Close"]
    assert d["mapa_b"]["referencias"]["SCHB"]["valor_final"] == pytest.approx(10_000 * schb.iloc[-1] / schb.iloc[0],
                                                                               rel=1e-12)
    assert [p["id"] for p in d["mapa_a"]["periodos"]] == ["desde-2012", "10-anios", "5-anios", "3-anios"]
    for p in d["mapa_b"]["parejas"]:
        for k in ("series", "en_cierre_anterior"):
            assert set(p[k]) == {p["accion"], f"{p['fondo']}_reinvirtiendo", f"{p['fondo']}_cobrando"}
            for nombre, s in p[k].items():
                extra = CAMPOS_COBRANDO if nombre.endswith("_cobrando") else set()
                assert set(s) == CAMPOS_SERIE | extra, nombre
    for p in d["mapa_a"]["periodos"]:
        assert set(p["series"]) == set(p["en_cierre_anterior"]) == {"SCHB", "QQQ", "XLK", "SMH"}
        assert all(set(s) == CAMPOS_SERIE for s in p["series"].values())
    assert set(d["mapa_b"]["semanas"]["parejas"]) == {"NVDA", "TSLA", "MSTR"}


def test_de_punta_a_punta_datos_malos_salen_con_codigo_2_y_el_motivo(tmp_path):
    a, b = _universo_por_defecto(tmp_path)
    (a / "QQQ.csv").unlink()
    r = _correr_cli("--historia-a", a, "--historia-b", b, cwd=tmp_path)
    assert r.returncode == 2
    assert r.stdout == ""
    assert "mapa_riesgo: QQQ: no está en" in r.stderr
