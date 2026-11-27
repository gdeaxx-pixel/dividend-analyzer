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


def test_cada_semana_va_de_ultimo_cierre_a_ultimo_cierre_y_la_primera_desde_la_compra(mr):
    idx = pd.to_datetime(["2024-01-04", "2024-01-05", "2024-01-11", "2024-01-12", "2024-01-18", "2024-01-19"])

    class Corrida:
        daily = pd.DataFrame({"total_value": [90, 100, 95, 110, 130, 99.0]}, index=idx)

    r = mr.semanal(Corrida)
    assert list(r.index.strftime("%Y-%m-%d")) == ["2024-01-05", "2024-01-12", "2024-01-19"]
    assert r.tolist() == pytest.approx([100 / 90 - 1, 0.10, -0.10], abs=1e-12)


def test_la_semana_lleva_la_fecha_de_su_ultimo_cierre_aunque_no_sea_viernes(mr):
    """El 29-mar-2024 (Viernes Santo) no hubo mercado: esa semana cierra el jueves 28."""
    idx = pd.to_datetime(["2024-03-27", "2024-03-28", "2024-04-01", "2024-04-05"])

    class Corrida:
        daily = pd.DataFrame({"total_value": [100, 104, 99, 110.0]}, index=idx)

    r = mr.semanal(Corrida)
    assert list(r.index.strftime("%Y-%m-%d")) == ["2024-03-28", "2024-04-05"]
    assert r.tolist() == pytest.approx([0.04, 110 / 104 - 1], abs=1e-12)


def test_las_semanas_encadenan_desde_el_cierre_de_compra(mr, tmp_path):
    """La compra del Mapa B cae en jueves (22-feb-2024): sin la primera semana corta, el producto de
    las semanas no da lo que gana la serie."""
    a, b = _universo_por_defecto(tmp_path)
    d = mr.calcular(a, b)
    for par in d["mapa_b"]["parejas"]:
        w, s = d["mapa_b"]["semanas"]["parejas"][par["accion"]], par["series"]
        assert (1 + w["accion_fuertes"]) * (1 + w["accion_resto"]) == pytest.approx(
            s[par["accion"]]["valor_final"] / 10_000, rel=1e-12)
        for v in ("reinvirtiendo", "cobrando"):
            assert (1 + w[v]["fondo_fuertes"]) * (1 + w[v]["fondo_resto"]) == pytest.approx(
                s[f"{par['fondo']}_{v}"]["valor_final"] / 10_000, rel=1e-12)


class _Corrida:
    def __init__(self, valores):
        fechas = pd.date_range("2024-01-05", periods=len(valores), freq="W-FRI")
        self.daily = pd.DataFrame({"total_value": [float(x) for x in valores]}, index=fechas)


def test_semanas_fuertes_con_empate_en_el_corte_y_con_empate_entre_fondo_y_accion(mr):
    """Seis semanas: el corte de la quinta parte cae justo en la segunda mejor (posición 4 de 0 a 5),
    que cuenta como fuerte. En las semanas 1 y 2 el fondo empata con la acción: empatar no es ganar."""
    acc = _Corrida([100, 101, 100, 105, 112, 110, 121])
    fon = _Corrida([200, 202, 200, 200, 230, 220, 230])
    js = mr.semanas({"ACC": acc, "FON_reinvirtiendo": fon, "FON_cobrando": fon}, [("ACC", "FON")],
                    pd.Timestamp("2024-01-05"), pd.Timestamp("2024-02-16"))
    assert (js["inicio"], js["fin"]) == ("2024-01-05", "2024-02-16")
    assert js["semana"] == "último cierre de cada semana"
    assert js["fuertes"] == "la quinta parte de las semanas en que más subió la acción"
    w = js["parejas"]["ACC"]
    assert (w["fondo"], w["semanas"], w["fuertes"], w["resto"]) == ("FON", 6, 2, 4)
    assert w["accion_fuertes"] == pytest.approx(16 / 15 * 11 / 10 - 1, abs=1e-12)
    assert w["accion_resto"] == pytest.approx(105 / 100 * 110 / 112 - 1, abs=1e-12)
    for v in ("reinvirtiendo", "cobrando"):
        assert w[v]["fondo_fuertes"] == pytest.approx(23 / 20 * 23 / 22 - 1, abs=1e-12)
        assert w[v]["fondo_resto"] == pytest.approx(220 / 230 - 1, abs=1e-12)
        assert w[v]["gana_fondo_resto"] == 0.0


@pytest.mark.parametrize("fon", [[200, 202, 200, 230, 220, 230], [200, 202, 200, 200, 230, 220, 230, 240]])
def test_un_fondo_sin_las_mismas_semanas_que_su_accion_para(mr, fon):
    acc = _Corrida([100, 101, 100, 105, 112, 110, 121])
    with pytest.raises(mr.DatosMalos, match="FON reinvirtiendo: no tiene las mismas semanas que ACC"):
        mr.semanas({"ACC": acc, "FON_reinvirtiendo": _Corrida(fon), "FON_cobrando": _Corrida(fon)},
                   [("ACC", "FON")], pd.Timestamp("2024-01-05"), pd.Timestamp("2024-02-16"))


@pytest.mark.parametrize("acc", [[100, 200, 400, 800], [100, 101]])
def test_sin_semanas_fuera_de_las_fuertes_para(mr, acc):
    """Si todas las semanas empatan en el corte, o hay una sola, no queda resto con qué comparar."""
    fon = _Corrida([10] * len(acc))
    with pytest.raises(mr.DatosMalos, match="ACC: no quedan semanas fuera de las fuertes"):
        mr.semanas({"ACC": _Corrida(acc), "FON_reinvirtiendo": fon, "FON_cobrando": fon}, [("ACC", "FON")],
                   pd.Timestamp("2024-01-05"), pd.Timestamp("2024-02-16"))


def test_una_fila_mala_sin_pago_se_quita_y_se_anota(mr, tmp_path):
    dias = SEMANAS[:1] + ["2024-01-10"] + SEMANAS[1:]
    d = _calcular(mr, tmp_path,
                  ACC=list(zip(dias, [100, float("nan"), 110, 99, 108.9, 130.68, 117.612], [0] * 7)),
                  FON=list(zip(dias, [10, 10, 10, 10, 20, 20, 25], [0.7, 0, 0, 0.5, 0, 0, 0])),
                  MKT=list(zip(dias, [100, 100.5, 101, 99, 102, 104, 103], [0] * 7)))
    assert d["filas_malas"] == [{"tk": "ACC", "fecha": "2024-01-10", "Close": None, "Dividends": 0.0,
                                 "accion": "quitada"}]
    acc = d["mapa_b"]["parejas"][0]["series"]["ACC"]
    assert acc["valor_final"] == pytest.approx(10_000 * 117.612 / 100, rel=1e-12)
    assert math.isfinite(acc["se_mueve"])
    assert d["mapa_b"]["semanas"]["parejas"]["ACC"]["semanas"] == 5


def test_una_fila_mala_en_el_ultimo_cierre_de_una_semana_para(mr, tmp_path):
    """Sin el viernes 19-ene, la semana de ACC cierra el jueves y la de FON el viernes: ya no miden
    lo mismo y se para, aunque las dos semanas lleven la misma etiqueta."""
    dias = SEMANAS[:2] + ["2024-01-18"] + SEMANAS[2:]
    with pytest.raises(mr.DatosMalos, match="FON reinvirtiendo: no tiene las mismas semanas que ACC"):
        _calcular(mr, tmp_path,
                  ACC=list(zip(dias, [100, 110, 105, float("nan"), 108.9, 130.68, 117.612], [0] * 7)),
                  FON=list(zip(dias, [10, 10, 10, 10, 20, 20, 25], [0.7, 0, 0, 0.5, 0, 0, 0])),
                  MKT=list(zip(dias, [100, 101, 100, 99, 102, 104, 103], [0] * 7)))


def test_las_referencias_tambien_llevan_su_cierre_anterior(mr, tmp_path):
    ref = _calcular(mr, tmp_path)["mapa_b"]["referencias"]
    assert ref["MKT"]["valor_final"] == pytest.approx(10_000 * 103 / 100, rel=1e-12)
    ant = ref["MKT_en_cierre_anterior"]
    assert ant["valor_final"] == pytest.approx(10_000 * 104 / 100, rel=1e-12)
    assert (ant["fin"], ant["momento"]) == ("2024-02-02", "al cierre del 2024-02-02")


def test_el_mapa_b_dice_el_primer_cierre_de_verdad_si_el_inicio_no_es_dia_habil(mr, tmp_path):
    a, b = _escenario(tmp_path)
    mb = mr.calcular(a, b, **{**UNIVERSO, "inicio_b": "2024-01-03"})["mapa_b"]
    assert mb["inicio"] == mb["semanas"]["inicio"] == mb["parejas"][0]["series"]["ACC"]["inicio"] == "2024-01-05"


def test_el_capital_escala_el_dinero_y_no_los_porcentajes(mr, tmp_path):
    a, b = _escenario(tmp_path)
    s0 = mr.calcular(a, b, **UNIVERSO)["mapa_b"]["parejas"][0]["series"]["FON_cobrando"]
    d = mr.calcular(a, b, capital=25_000, **UNIVERSO)
    s1 = d["mapa_b"]["parejas"][0]["series"]["FON_cobrando"]
    assert d["capital"] == 25_000
    assert s1["valor_final"] == pytest.approx(25_500 * 2.5, rel=1e-12)
    for k in ("valor_final", "semana_normal_usd", "sigue_invertido", "efectivo_cobrado"):
        assert s1[k] == pytest.approx(2.5 * s0[k], rel=1e-9), k
    for k in ("rendimiento_anual", "se_mueve", "peor_caida"):
        assert s1[k] == pytest.approx(s0[k], rel=1e-9), k


def test_la_salida_no_lleva_rutas_de_la_maquina(mr, tmp_path):
    assert str(tmp_path) not in json.dumps(_calcular(mr, tmp_path), ensure_ascii=False)


# ---- Mapa A: el corte, el aniversario, las filas malas y la línea de mercado ----

def test_si_hay_cierre_justo_en_el_aniversario_compra_ese_dia(mr, tmp_path):
    a_mkt = [("2011-12-30", 50, 0), ("2023-02-08", 80, 0), ("2023-02-09", 82, 0), ("2023-02-10", 88, 0),
             ("2024-02-02", 90, 0), ("2024-02-09", 100, 0)]
    pa = {p["id"]: p for p in _calcular(mr, tmp_path, A_MKT=a_mkt)["mapa_a"]["periodos"]}
    assert pa["1-anios"]["compra"] == "2023-02-09"
    assert pa["1-anios"]["series"]["MKT"]["valor_final"] == pytest.approx(10_000 * 100 / 82, rel=1e-12)


def test_el_mapa_a_tambien_quita_y_anota_sus_filas_malas(mr, tmp_path):
    """La fila quitada no rompe el empate de fechas con OTR: ese empate se mide sobre lo que trae la fuente."""
    a, b = _escenario(tmp_path, A_MKT=[("2011-12-30", 50, 0), ("2012-06-29", float("nan"), 0), ("2023-02-08", 80, 0),
                                       ("2023-02-10", 88, 0), ("2024-02-02", 90, 0), ("2024-02-09", 100, 0)])
    _guardar(a, "OTR", [("2011-12-30", 5, 0), ("2012-06-29", 7, 0), ("2023-02-08", 8, 0), ("2023-02-10", 8.4, 0),
                        ("2024-02-02", 9, 0), ("2024-02-09", 11, 0)])
    d = mr.calcular(a, b, **{**UNIVERSO, "fondos_a": ["MKT", "OTR"]})
    assert d["filas_malas"] == [{"tk": "MKT", "fecha": "2012-06-29", "Close": None, "Dividends": 0.0,
                                 "accion": "quitada"}]
    desde = d["mapa_a"]["periodos"][0]["series"]
    assert desde["MKT"]["valor_final"] == pytest.approx(20_000, rel=1e-12) and math.isfinite(desde["MKT"]["se_mueve"])
    assert desde["OTR"]["valor_final"] == pytest.approx(22_000, rel=1e-12)


@pytest.mark.parametrize("fila, motivo", [
    (("2012-06-29", float("nan"), 0.3), "MKT 2012-06-29: fila mala con pago"),
    (("2024-02-09", float("nan"), 0), "MKT: la historia del Mapa A no llega al 2024-02-09"),
])
def test_el_mapa_a_para_con_una_fila_mala_con_pago_o_en_su_ultimo_cierre(mr, tmp_path, fila, motivo):
    a_mkt = {f: (f, c, p) for f, c, p in [("2011-12-30", 50, 0), ("2012-06-29", 60, 0), ("2023-02-08", 80, 0),
                                         ("2023-02-10", 88, 0), ("2024-02-02", 90, 0), ("2024-02-09", 100, 0)]}
    a_mkt[fila[0]] = fila
    with pytest.raises(mr.DatosMalos, match=motivo):
        _calcular(mr, tmp_path, A_MKT=list(a_mkt.values()))


def test_la_linea_del_mapa_a_sale_del_mercado_aunque_no_vaya_primero(mr, tmp_path):
    a, b = _escenario(tmp_path)
    _guardar(a, "OTR", [("2011-12-30", 5, 0), ("2012-06-29", 7, 0), ("2023-02-08", 8, 0), ("2023-02-10", 8.4, 0),
                        ("2024-02-02", 9, 0), ("2024-02-09", 11, 0)])
    d = mr.calcular(a, b, **{**UNIVERSO, "fondos_a": ["OTR", "MKT"]})
    for p in d["mapa_a"]["periodos"]:
        mk, otr = p["series"]["MKT"], p["series"]["OTR"]
        assert p["linea_mercado"] == {"pendiente": pytest.approx(mk["rendimiento_anual"] / mk["se_mueve"]), "de": "MKT"}
        assert otr["rendimiento_anual"] / otr["se_mueve"] != pytest.approx(p["linea_mercado"]["pendiente"])


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


@pytest.mark.parametrize("close, div, accion, anotado", [
    (0.0, 0.0, "quitada", (0.0, 0.0)),
    (-5.0, 0.0, "quitada", (-5.0, 0.0)),
    (float("inf"), 0.0, "quitada", (None, 0.0)),
    (float("nan"), 0.0, "quitada", (None, 0.0)),
    (0.0, 0.4, "para", (0.0, 0.4)),
    (10.0, -0.1, "para", (10.0, -0.1)),
    (10.0, float("inf"), "para", (10.0, None)),
    (10.0, float("nan"), "para", (10.0, None)),
])
def test_que_fila_es_mala_y_que_se_hace_con_ella(mr, close, div, accion, anotado):
    h = pd.DataFrame({"Close": [10.0, close, 11.0], "Dividends": [0.25, div, 0.0]},
                     index=pd.to_datetime(["2024-01-05", "2024-01-08", "2024-01-09"]))
    malas = []
    if accion == "para":
        with pytest.raises(mr.DatosMalos, match="XYZ 2024-01-08: fila mala con pago"):
            mr.filas_buenas("XYZ", h, malas)
    else:
        buenas = mr.filas_buenas("XYZ", h, malas)
        assert list(buenas.index.strftime("%Y-%m-%d")) == ["2024-01-05", "2024-01-09"]
        assert buenas["Dividends"].tolist() == [0.25, 0.0]
    assert malas == [{"tk": "XYZ", "fecha": "2024-01-08", "Close": anotado[0], "Dividends": anotado[1],
                      "accion": accion}]


@pytest.mark.parametrize("cambio, motivo", [
    ({"capital": 0}, "el capital tiene que ser un número positivo"),
    ({"capital": -1}, "el capital tiene que ser un número positivo"),
    ({"capital": float("nan")}, "el capital tiene que ser un número positivo"),
    ({"capital": float("inf")}, "el capital tiene que ser un número positivo"),
    ({"inicio_b": "xx"}, "el inicio del Mapa B no es una fecha: 'xx'"),
    ({"inicio_b": ""}, "el inicio del Mapa B no es una fecha: ''"),
    ({"parejas": [("ACC",)]}, "cada pareja va como ACCIÓN:FONDO"),
    ({"parejas": [("ACC", "FON", "X")]}, "cada pareja va como ACCIÓN:FONDO"),
    ({"parejas": [("ACC", "FON"), ("ACC", "FON2")]}, "hay repetidos en las parejas"),
    ({"parejas": [("ACC", "ACC")]}, "hay repetidos en las parejas"),
    ({"referencias": ["MKT", "MKT"]}, "hay repetidos en las referencias"),
    ({"fondos_a": ["MKT", "MKT"]}, "hay repetidos en los fondos del Mapa A"),
    ({"anios_a": [1, 1]}, "hay repetidos en los años del Mapa A"),
    ({"anios_a": [0]}, "los años del Mapa A van en enteros positivos"),
    ({"anios_a": [1.5]}, "los años del Mapa A van en enteros positivos"),
    ({"anios_a": [True]}, "los años del Mapa A van en enteros positivos"),
    ({"parejas": [("ACC", "FON/X")]}, "símbolos no válidos: 'FON/X'"),
    ({"referencias": ["MKT", "../x"]}, "símbolos no válidos: '../x'"),
    ({"parejas": [("ACC", "")]}, "símbolos no válidos: ''"),
    ({"mercado": "OTR"}, r"el mercado \(OTR\) tiene que estar en las referencias y en los fondos del Mapa A"),
    ({"fondos_a": ["OTR"]}, r"el mercado \(MKT\) tiene que estar"),
    ({"referencias": ["OTR"]}, r"el mercado \(MKT\) tiene que estar"),
])
def test_lo_que_pide_quien_llama_se_revisa_antes_de_leer_nada(mr, tmp_path, cambio, motivo):
    with pytest.raises(mr.DatosMalos, match=motivo):
        mr.calcular(tmp_path / "no-existe", tmp_path / "no-existe", **{**UNIVERSO, **cambio})


@pytest.mark.parametrize("cambios, motivo", [
    ({"FON": list(zip(SEMANAS[:3] + SEMANAS[4:], [10, 10, 10, 20, 25], [0.7, 0, 0.5, 0, 0]))},
     r"FON: en el Mapa B no tiene las mismas fechas que MKT \(la primera distinta, el 2024-01-26\)"),
    ({"ACC": list(zip(SEMANAS[:1] + ["2024-01-10"] + SEMANAS[1:], [100, 105, 110, 99, 108.9, 130.68, 117.612],
                      [0] * 7))},
     r"ACC: en el Mapa B no tiene las mismas fechas que MKT \(la primera distinta, el 2024-01-10\)"),
    ({"MKT": [("2024-01-04", 100, 0)] + list(zip(SEMANAS, [100, 101, 99, 102, 104, 103], [0] * 6))}, None),
])
def test_en_el_mapa_b_todas_cotizan_los_mismos_dias_desde_el_inicio(mr, tmp_path, cambios, motivo):
    if motivo is None:
        assert _calcular(mr, tmp_path, **cambios)["mapa_b"]["inicio"] == "2024-01-05"
    else:
        with pytest.raises(mr.DatosMalos, match=motivo):
            _calcular(mr, tmp_path, **cambios)


def test_en_el_mapa_a_todos_cotizan_los_mismos_dias_desde_la_primera_compra(mr, tmp_path):
    a, b = _escenario(tmp_path)
    _guardar(a, "OTR", [("2011-12-30", 5, 0), ("2023-02-08", 8, 0), ("2023-02-10", 8.4, 0),
                        ("2024-02-02", 9, 0), ("2024-02-09", 11, 0)])
    with pytest.raises(mr.DatosMalos, match=r"OTR: en el Mapa A no tiene las mismas fechas que MKT "
                                            r"\(la primera distinta, el 2012-06-29\)"):
        mr.calcular(a, b, **{**UNIVERSO, "fondos_a": ["MKT", "OTR"]})


def test_un_inicio_del_mapa_b_sin_cierres_para(mr, tmp_path):
    a, b = _escenario(tmp_path)
    with pytest.raises(mr.DatosMalos, match="hay símbolos sin cierres desde el 2024-03-01"):
        mr.calcular(a, b, **{**UNIVERSO, "inicio_b": "2024-03-01"})


@pytest.mark.parametrize("cambios, motivo", [
    ({"FON": []}, "sin al menos dos cierres buenos: FON"),
    ({"MKT": [("2024-02-09", 103, 0)]}, "sin al menos dos cierres buenos: MKT"),
])
def test_una_historia_vacia_o_de_un_cierre_para(mr, tmp_path, cambios, motivo):
    with pytest.raises(mr.DatosMalos, match=motivo):
        _calcular(mr, tmp_path, **cambios)


@pytest.mark.parametrize("n", [1, 2, 3])
def test_el_motor_necesita_al_menos_tres_cierres(mr, n):
    h = pd.DataFrame({"Close": [10.0, 11.0, 12.0][:n], "Dividends": [0.0] * n},
                     index=pd.bdate_range("2024-01-01", periods=n))
    if n == 3:
        assert len(mr.correr("XYZ", h, h.index[0], h.index[-1], True, 10_000).daily) == 3
    else:
        with pytest.raises(mr.DatosMalos, match=f"XYZ: menos de tres cierres entre 2024-01-01 y {h.index[-1].date()}"):
            mr.correr("XYZ", h, h.index[0], h.index[-1], True, 10_000)


# ---- lectura: CSV y el parquet del caché leen igual ----

def test_parquet_y_csv_dan_la_misma_historia(mr, tmp_path):
    h = pd.DataFrame({"Close": [10.0, 11.0], "Dividends": [0.0, 0.25]},
                     index=pd.DatetimeIndex(pd.to_datetime(["2024-01-05", "2024-01-12"]), name="Date"))
    (tmp_path / "pq").mkdir()
    h.to_parquet(tmp_path / "pq" / "X.parquet")
    _guardar(tmp_path / "csv", "X", [("2024-01-05", 10.0, 0.0), ("2024-01-12", 11.0, 0.25)])
    pd.testing.assert_frame_equal(mr.leer(tmp_path / "pq", "X"), mr.leer(tmp_path / "csv", "X"), check_freq=False,
                                  check_index_type=False)


def test_si_hay_parquet_y_csv_manda_el_parquet(mr, tmp_path):
    pd.DataFrame({"Close": [10.0, 11.0], "Dividends": [0.0, 0.0]},
                 index=pd.DatetimeIndex(pd.to_datetime(["2024-01-05", "2024-01-12"]), name="Date")
                 ).to_parquet(tmp_path / "X.parquet")
    _guardar(tmp_path, "X", [("2024-01-05", 20.0, 0.0), ("2024-01-12", 22.0, 0.0)])
    assert mr.leer(tmp_path, "X")["Close"].tolist() == [10.0, 11.0]


def test_una_historia_sin_close_o_sin_dividends_para(mr, tmp_path):
    pd.DataFrame({"Date": ["2024-01-05"], "Close": [10.0]}).to_csv(tmp_path / "X.csv", index=False)
    with pytest.raises(mr.DatosMalos, match="X: le falta Close o Dividends"):
        mr.leer(tmp_path, "X")


def test_el_parquet_real_del_cache_se_lee_con_sus_fechas(mr):
    crudo = pd.read_parquet(RAIZ / "knowledge" / "price_cache" / "SCHB.parquet")
    h = mr.leer(RAIZ / "knowledge" / "price_cache", "SCHB")
    assert list(h.columns) == ["Close", "Dividends"] and len(h) == len(crudo)
    assert list(h.index.strftime("%Y-%m-%d")) == list(pd.DatetimeIndex(crudo.index).strftime("%Y-%m-%d"))


# ---- las paradas de la barra del Mapa B ----

DIAS_P = ["2021-12-31", "2022-06-30", "2022-12-30", "2023-01-03", "2023-06-30", "2023-11-17", "2023-11-21",
          "2023-12-29", "2024-01-02", "2024-02-22", "2024-06-28", "2024-12-31", "2025-01-02", "2025-06-30",
          "2025-12-31", "2026-01-02", "2026-06-30", "2026-11-19", "2026-11-20"]
ACC_P = dict(zip(DIAS_P, [40, 44, 50, 60, 75, 70, 72, 90, 99, 110, 130, 180, 170, 150, 120, 130, 160, 190, 198]))
UNIVERSO_P = dict(parejas=[("ACC", "FON"), ("ACD", "NUE")], referencias=["MKT"], inicio_b="2024-02-22",
                  fondos_a=["MKT"], anios_a=[1], mercado="MKT")
FIN_P = {"2023": ("2022-12-30", "2023-12-29"), "2024": ("2023-12-29", "2024-12-31"),
         "2025": ("2024-12-31", "2025-12-31"), "2026": ("2025-12-31", "2026-11-20"),
         "3-anios": ("2023-11-17", "2026-11-20"), "feb-2024": ("2024-02-22", "2026-11-20")}


def _paradas(mr, tmp_path, dias=DIAS_P, nace_fon="2022-12-30", nace_nue="2024-01-02", cambiar=None):
    """Dos parejas: FON nace el día de compra de 2023 y NUE el primer día hábil de 2024. MKT, ACC y
    ACD cotizan desde fines de 2021, cuando todavía no había ningún fondo."""
    precios = {**ACC_P, **{d: 200 + i for i, d in enumerate(d for d in dias if d not in ACC_P)}}
    filas = {
        "MKT": [(d, 100 + 2 * i + 3 * (i % 2), 0) for i, d in enumerate(dias)],
        "ACC": [(d, precios[d], 0) for d in dias],
        "ACD": [(d, 30 + i + 2 * (i % 3), 0) for i, d in enumerate(dias)],
        "FON": [(d, 20 + i % 3, 0.4 if d.endswith(("-06-30", "-06-28")) else 0)
                for i, d in enumerate(dias) if d >= nace_fon],
        "NUE": [(d, 25 - i % 2, 0.5 if d.endswith(("-06-30", "-06-28")) else 0)
                for i, d in enumerate(dias) if d >= nace_nue],
    }
    for tk, cambio in (cambiar or {}).items():
        filas[tk] = cambio(filas[tk])
    for tk, f in filas.items():
        _guardar(tmp_path / "b", tk, f)
    _guardar(tmp_path / "a", "MKT", [("2011-12-30", 50, 0)] + filas["MKT"])
    d = mr.calcular(tmp_path / "a", tmp_path / "b", **UNIVERSO_P)
    return d, {p["id"]: p for p in d["mapa_b"]["paradas"]}


def test_las_paradas_van_en_el_orden_de_la_barra_con_su_medida(mr, tmp_path):
    d, _ = _paradas(mr, tmp_path)
    assert [(p["id"], p["medida"]) for p in d["mapa_b"]["paradas"]] == [
        ("2023", "total"), ("2024", "total"), ("2025", "total"), ("2026", "total"),
        ("3-anios", "anual"), ("feb-2024", "anual")]


def test_cada_parada_compra_y_termina_en_sus_fechas(mr, tmp_path):
    """Un año calendario compra al último cierre del año anterior; «últimos 3 años», al último cierre
    que no pasa de T menos 3 años (el 20-nov-2023 aquí no hubo mercado)."""
    _, pa = _paradas(mr, tmp_path)
    assert {k: (p["compra"], p["fin"]) for k, p in pa.items()} == FIN_P
    for k, p in pa.items():
        for nombre, s in p["series"].items():
            if s is not None:
                assert (s["inicio"], s["fin"], s["momento"]) == (*FIN_P[k], f"al cierre del {FIN_P[k][1]}"), (k, nombre)


def test_ultimos_3_anios_compra_en_el_aniversario_si_hubo_cierre(mr, tmp_path):
    dias = sorted(DIAS_P + ["2023-11-20"])
    _, pa = _paradas(mr, tmp_path, dias=dias)
    assert pa["3-anios"]["compra"] == "2023-11-20"


def test_un_anio_calendario_da_el_rendimiento_del_periodo_sin_anualizar(mr, tmp_path):
    _, pa = _paradas(mr, tmp_path)
    for anio in ("2023", "2024", "2025", "2026"):
        compra, fin = FIN_P[anio]
        s = pa[anio]["series"]["ACC"]
        assert s["rendimiento"] == pytest.approx(ACC_P[fin] / ACC_P[compra] - 1, rel=1e-12), anio
        assert s["rendimiento"] != pytest.approx(s["rendimiento_anual"], rel=1e-6), anio


def test_las_paradas_de_varios_anios_dan_el_rendimiento_por_anio(mr, tmp_path):
    _, pa = _paradas(mr, tmp_path)
    for pid in ("3-anios", "feb-2024"):
        compra, fin = FIN_P[pid]
        dias = (pd.Timestamp(fin) - pd.Timestamp(compra)).days
        esperado = (ACC_P[fin] / ACC_P[compra]) ** (365.25 / dias) - 1
        s = pa[pid]["series"]["ACC"]
        assert s["rendimiento"] == s["rendimiento_anual"] == pytest.approx(esperado, rel=1e-12), pid


def test_un_fondo_que_no_existia_el_dia_de_compra_va_en_null_y_su_accion_si_va(mr, tmp_path):
    """NUE nace dentro de 2024 y dentro de «últimos 3 años»: en las dos falta, con sus dos versiones.
    FON nace el mismo día de compra de 2023, así que ahí sí está."""
    _, pa = _paradas(mr, tmp_path)
    todas = {"ACC", "FON_reinvirtiendo", "FON_cobrando", "ACD", "NUE_reinvirtiendo", "NUE_cobrando", "MKT"}
    faltan = {k: {n for n, s in p["series"].items() if s is None} for k, p in pa.items()}
    assert all(set(p["series"]) == todas for p in pa.values())
    nue = {"NUE_reinvirtiendo", "NUE_cobrando"}
    assert faltan == {"2023": nue, "2024": nue, "2025": set(), "2026": set(), "3-anios": nue, "feb-2024": set()}


def test_en_las_paradas_solo_cobrando_lleva_lo_que_sigue_invertido(mr, tmp_path):
    _, pa = _paradas(mr, tmp_path)
    for p in pa.values():
        for nombre, s in p["series"].items():
            if s is None:
                continue
            extra = CAMPOS_COBRANDO if nombre.endswith("_cobrando") else set()
            assert set(s) == CAMPOS_SERIE | {"rendimiento"} | extra, (p["id"], nombre)
            assert s["base"] == "bruto"
    s = pa["2025"]["series"]["FON_cobrando"]
    precios = pd.read_csv(tmp_path / "b" / "FON.csv").set_index("Date")["Close"]
    acciones = 10_000 / precios["2024-12-31"]
    assert s["efectivo_cobrado"] == pytest.approx(acciones * 0.4, rel=1e-12)
    assert s["sigue_invertido"] == pytest.approx(acciones * precios["2025-12-31"], rel=1e-12)
    assert s["rendimiento"] == pytest.approx((s["sigue_invertido"] + s["efectivo_cobrado"]) / 10_000 - 1, rel=1e-12)


def test_no_hay_boton_de_un_anio_sin_ningun_fondo_vivo_al_comprar(mr, tmp_path):
    """Si el fondo más viejo nace el primer día hábil de 2023, ese año no se podía comprar ninguno."""
    d, _ = _paradas(mr, tmp_path, nace_fon="2023-01-03")
    assert [p["id"] for p in d["mapa_b"]["paradas"]] == ["2024", "2025", "2026", "3-anios", "feb-2024"]


@pytest.mark.parametrize("nuevos, aparece", [
    (["2026-12-31", "2027-01-04"], False),
    (["2026-12-31", "2027-01-04", "2027-01-05"], True),
])
def test_el_anio_nuevo_aparece_solo_cuando_ya_tiene_tres_cierres(mr, tmp_path, nuevos, aparece):
    """El primer día hábil de enero la ventana tiene dos cierres y el motor pide tres: el año nuevo
    espera un día, y el cálculo no se cae por eso."""
    _, pa = _paradas(mr, tmp_path, dias=DIAS_P + nuevos)
    anios = [k for k in pa if k.isdigit()]
    assert anios == ["2023", "2024", "2025", "2026"] + (["2027"] if aparece else [])
    assert pa["2026"]["fin"] == "2026-12-31"
    if aparece:
        assert (pa["2027"]["compra"], pa["2027"]["fin"], pa["2027"]["medida"]) == ("2026-12-31", "2027-01-05", "total")


def test_la_parada_del_inicio_es_la_misma_corrida_que_las_parejas(mr, tmp_path):
    d, pa = _paradas(mr, tmp_path)
    series = {k: v for p in d["mapa_b"]["parejas"] for k, v in p["series"].items()}
    series["MKT"] = d["mapa_b"]["referencias"]["MKT"]
    de_la_parada = {k: {c: x for c, x in s.items() if c != "rendimiento"}
                    for k, s in pa["feb-2024"]["series"].items()}
    assert de_la_parada == series


def test_la_parada_del_inicio_toma_su_nombre_del_inicio_pedido(mr, tmp_path):
    a, b = _escenario(tmp_path)
    d = mr.calcular(a, b, **{**UNIVERSO, "inicio_b": "2024-01-04"})
    assert [(p["id"], p["compra"], p["medida"]) for p in d["mapa_b"]["paradas"]] == [("ene-2024", "2024-01-05", "anual")]


@pytest.mark.parametrize("tk, fecha, pid", [("ACC", "2023-06-30", "2023"), ("FON", "2023-06-30", "2023"),
                                            ("MKT", "2023-11-21", "2023")])
def test_un_dia_que_falta_antes_del_inicio_para_en_la_parada_que_lo_usa(mr, tmp_path, tk, fecha, pid):
    quitar = {tk: lambda f: [x for x in f if x[0] != fecha]}
    with pytest.raises(mr.DatosMalos, match=rf"en el Mapa B \(parada {pid}\) no tiene las mismas fechas que MKT "
                                            rf"\(la primera distinta, el {fecha}\)"):
        _paradas(mr, tmp_path, cambiar=quitar)


@pytest.mark.parametrize("fecha", ["2022-12-30", "2023-12-29"])
def test_si_la_fila_mala_quitada_era_la_compra_o_el_fin_de_una_parada_para(mr, tmp_path, fecha):
    """Sin ese cierre el motor compraría o terminaría otro día sin decirlo."""
    romper = {"ACC": lambda f: [(d, float("nan") if d == fecha else c, v) for d, c, v in f]}
    with pytest.raises(mr.DatosMalos, match=f"ACC: falta el cierre del {fecha}, que usa la parada 2023"):
        _paradas(mr, tmp_path, cambiar=romper)


def test_sin_tres_anios_de_historia_no_hay_boton_de_tres_anios(mr, tmp_path):
    a, b = _universo_por_defecto(tmp_path)
    assert [p["id"] for p in mr.calcular(a, b)["mapa_b"]["paradas"]] == ["feb-2024"]


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


# ---- lo que recibe la línea de comandos ----

def _argv(a, b, *extra):
    return ["--historia-a", str(a), "--historia-b", str(b), "--parejas", "ACC:FON", "--referencias", "MKT",
            "--inicio-b", "2024-01-05", "--fondos-a", "MKT", "--anios-a", "1", "--mercado", "MKT", *extra]


def test_la_linea_de_comandos_acepta_minusculas_y_el_capital(mr, tmp_path, capsys):
    a, b = _escenario(tmp_path)
    assert mr.main(_argv(a, b, "--parejas", " acc:fon ", "--referencias", "mkt", "--fondos-a", "mkt",
                         "--mercado", " mkt", "--capital", "25000")) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["capital"] == 25_000
    assert [(p["accion"], p["fondo"]) for p in d["mapa_b"]["parejas"]] == [("ACC", "FON")]
    assert d["mapa_b"]["parejas"][0]["series"]["FON_cobrando"]["valor_final"] == pytest.approx(25_500 * 2.5,
                                                                                               rel=1e-12)
    assert d["mapa_a"]["periodos"][1]["series"]["MKT"]["valor_final"] == pytest.approx(12_500 * 2.5, rel=1e-12)


@pytest.mark.parametrize("extra, motivo", [
    (["--inicio-b", "xx"], "el inicio del Mapa B no es una fecha"),
    (["--parejas", "ACC"], "cada pareja va como ACCIÓN:FONDO"),
    (["--anios-a", "1,x"], "--anios-a lleva enteros separados por comas: 1,x"),
    (["--capital", "nan"], "el capital tiene que ser un número positivo"),
    (["--capital", "-5"], "el capital tiene que ser un número positivo"),
])
def test_la_linea_de_comandos_para_con_codigo_2_y_sin_salida(mr, tmp_path, capsys, extra, motivo):
    a, b = _escenario(tmp_path)
    assert mr.main(_argv(a, b, *extra)) == 2
    salida = capsys.readouterr()
    assert salida.out == ""
    assert f"mapa_riesgo: {motivo}" in salida.err


def test_una_cifra_no_finita_no_sale_como_json(mr, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(mr, "calcular", lambda *a, **k: {"x": float("nan")})
    assert mr.main(_argv(tmp_path, tmp_path)) == 2
    salida = capsys.readouterr()
    assert salida.out == "" and "mapa_riesgo: cifra no finita o dato inválido" in salida.err


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
    (parada,) = d["mapa_b"]["paradas"]
    assert set(parada) == {"id", "compra", "fin", "medida", "series"}
    assert (parada["id"], parada["compra"], parada["fin"], parada["medida"]) == (
        "feb-2024", "2024-02-22", "2024-08-30", "anual")
    assert set(parada["series"]) == {"SCHB", "SMH"} | {k for p in d["mapa_b"]["parejas"] for k in p["series"]}


def test_de_punta_a_punta_datos_malos_salen_con_codigo_2_y_el_motivo(tmp_path):
    a, b = _universo_por_defecto(tmp_path)
    (a / "QQQ.csv").unlink()
    r = _correr_cli("--historia-a", a, "--historia-b", b, cwd=tmp_path)
    assert r.returncode == 2
    assert r.stdout == ""
    assert "mapa_riesgo: QQQ: no está en" in r.stderr
