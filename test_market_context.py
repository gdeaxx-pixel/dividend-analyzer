"""`market_context.py`: ventanas de calendario, niveles sin ajustar y nota que no se pisa.

Sin red: los historiales son series construidas aquí y los esperados salen de la fecha,
no del número de filas.
"""
from datetime import date
import os

import pandas as pd
import pytest

import market_context as mc

HOY = date(2026, 11, 20)


def _diaria(inicio, fin, base=1000.0):
    idx = pd.date_range(inicio, fin, freq="D")
    return pd.DataFrame({"Close": [base + i for i in range(len(idx))]}, index=idx)


def _valor(hist, fecha):
    return float(hist["Close"][pd.Timestamp(fecha)])


def test_siete_dias_por_semana_un_mes_es_un_mes_de_calendario():
    hist = _diaria("2023-01-01", "2026-11-20")
    r = mc.calcular(hist, HOY)
    actual = _valor(hist, "2026-11-20")
    for clave, fecha in (("1m", "2026-10-20"), ("3m", "2026-08-20"), ("6m", "2026-05-20"),
                         ("1y", "2025-11-20"), ("3y", "2023-11-20")):
        base = _valor(hist, fecha)
        assert r[clave] == pytest.approx((actual - base) / base * 100), clave


def test_siete_dias_por_semana_el_minimo_de_52_semanas_mira_un_anio_entero():
    hist = _diaria("2023-01-01", "2026-11-20")
    r = mc.calcular(hist, HOY)
    assert r["52w_low"] == pytest.approx(_valor(hist, "2025-11-21"))
    assert r["52w_high"] == pytest.approx(_valor(hist, "2026-11-20"))


def test_el_anio_en_curso_parte_del_ultimo_cierre_del_anio_anterior():
    hist = _diaria("2023-01-01", "2026-11-20")
    r = mc.calcular(hist, HOY)
    base = _valor(hist, "2025-12-31")
    assert r["ytd"] == pytest.approx((_valor(hist, "2026-11-20") - base) / base * 100)


def test_sin_anio_anterior_el_anio_en_curso_parte_del_primer_cierre():
    hist = _diaria("2026-03-02", "2026-11-20")
    r = mc.calcular(hist, HOY)
    base = _valor(hist, "2026-03-02")
    assert r["ytd"] == pytest.approx((_valor(hist, "2026-11-20") - base) / base * 100)


def test_sin_cierres_este_anio_no_hay_rendimiento_del_anio():
    assert mc.calcular(_diaria("2025-01-01", "2025-12-31"), HOY)["ytd"] is None


def test_dias_habiles_la_base_es_el_ultimo_cierre_en_o_antes_de_la_fecha():
    idx = pd.bdate_range("2024-01-01", "2026-11-20")
    hist = pd.DataFrame({"Close": [100.0 + i for i in range(len(idx))]}, index=idx)
    r = mc.calcular(hist, HOY)
    actual = float(hist["Close"].iloc[-1])
    base_6m = float(hist["Close"][pd.Timestamp("2026-05-20")])
    assert r["6m"] == pytest.approx((actual - base_6m) / base_6m * 100)
    assert pd.Timestamp("2026-09-20").weekday() == 6
    base_2m_domingo = float(hist["Close"][pd.Timestamp("2026-09-18")])
    idx_corto = hist.index[hist.index <= pd.Timestamp("2026-10-20")]
    r2 = mc.calcular(hist.loc[idx_corto], HOY)
    actual2 = float(hist["Close"][pd.Timestamp("2026-10-20")])
    assert r2["1m"] == pytest.approx((actual2 - base_2m_domingo) / base_2m_domingo * 100)


def test_historial_corto_no_inventa_el_rendimiento_largo():
    r = mc.calcular(_diaria("2025-06-01", "2026-11-20"), HOY)
    assert r["3y"] is None
    assert r["1y"] is not None


def test_niveles_del_cierre_sin_ajustar_y_rendimientos_del_ajustado():
    idx = pd.date_range("2025-01-01", "2026-11-20", freq="D")
    n = len(idx)
    close = [50.0] * n
    close[10] = 80.0
    close[-1] = 40.0
    adj = [15.0 + 15.0 * i / (n - 1) for i in range(n)]
    hist = pd.DataFrame({"Close": close, "Adj Close": adj}, index=idx)
    r = mc.calcular(hist, HOY)
    assert r["price"] == 40.0
    assert r["ath"] == 80.0
    assert r["vs_ath"] == pytest.approx(-50.0)
    assert r["52w_high"] == 50.0
    assert r["52w_low"] == 40.0
    base = float(hist["Adj Close"][pd.Timestamp("2025-11-20")])
    assert r["1y"] == pytest.approx((30.0 - base) / base * 100)
    assert r["1y"] > 0


def test_fechas_con_zona_horaria_y_ultimo_cierre_vacio():
    hist = _diaria("2025-01-01", "2026-11-20")
    hist.index = hist.index.tz_localize("America/New_York")
    hist.iloc[-1, 0] = float("nan")
    r = mc.calcular(hist, HOY)
    assert r["price"] == pytest.approx(1000.0 + len(hist) - 2)


def test_historial_vacio_es_error():
    assert "error" in mc.calcular(pd.DataFrame(), HOY)
    assert "error" in mc.calcular(pd.DataFrame({"Close": [float("nan")]},
                                               index=pd.to_datetime(["2026-11-20"])), HOY)


_DATO = {"price": 10.0, "ath": 20.0, "vs_ath": -50.0, "52w_high": 15.0, "52w_low": 5.0,
         "vs_52w_high": -33.33, "ytd": 1.0, "1m": 2.0, "3m": 3.0, "6m": 4.0, "1y": 5.0, "3y": None}
_TODOS = [t for g in mc.GROUPS.values() for t in g]


def _nota_previa(tmp_path, cuerpo_manual):
    ruta = tmp_path / "nota.md"
    ruta.write_text("# vieja\n\n| **SPY** | $1.00 |\n\n" + mc._TITULO_NOTAS + "\n\n" + cuerpo_manual,
                    encoding="utf-8")
    return ruta


def test_corrida_caida_conserva_la_nota_y_sale_con_error(tmp_path, capsys):
    ruta = _nota_previa(tmp_path, "La Fed baja tasas.\n")
    antes = ruta.read_bytes()
    assert mc.main(str(ruta), traer=lambda t: {"error": "sin red"}) == 1
    assert ruta.read_bytes() == antes
    assert os.listdir(tmp_path) == ["nota.md"]


def test_mitad_exacta_caida_todavia_escribe_y_una_mas_ya_no(tmp_path):
    n = len(_TODOS)
    for caidos, codigo in ((n // 2, 0), (n // 2 + 1, 1)):
        ruta = tmp_path / f"n{caidos}.md"
        malos = set(_TODOS[:caidos])
        assert mc.main(str(ruta), traer=lambda t: {"error": "x"} if t in malos else dict(_DATO)) == codigo
        assert ruta.exists() == (codigo == 0)


def test_corrida_buena_conserva_lo_que_daniel_escribio(tmp_path):
    ruta = _nota_previa(tmp_path, "La Fed baja tasas.\n\n- earnings de NVDA el 19\n")
    assert mc.main(str(ruta), traer=lambda t: {"error": "x"} if t == "TLT" else dict(_DATO)) == 0
    texto = ruta.read_text(encoding="utf-8")
    assert texto.endswith(mc._TITULO_NOTAS + "\n\nLa Fed baja tasas.\n\n- earnings de NVDA el 19\n")
    assert texto.count(mc._TITULO_NOTAS) == 1
    assert "# vieja" not in texto
    assert "**Sin dato en esta corrida:** TLT" in texto
    assert "| **SPY** | $10.00 | $20.00 | -50.00% |" in texto
    assert "| **TLT** | — |" in texto


def test_sin_nota_previa_sale_la_plantilla_y_sin_aviso_si_todo_llego(tmp_path):
    ruta = tmp_path / "sub" / "nota.md"
    assert mc.main(str(ruta), traer=lambda t: dict(_DATO)) == 0
    texto = ruta.read_text(encoding="utf-8")
    assert texto.endswith("<!-- Agregar notas aquí -->\n")
    assert "Sin dato en esta corrida" not in texto


def test_si_falla_la_escritura_la_nota_anterior_queda_entera(tmp_path, monkeypatch):
    ruta = _nota_previa(tmp_path, "intacta\n")
    antes = ruta.read_bytes()

    def revienta(*a, **k):
        raise OSError("disco lleno")

    monkeypatch.setattr(mc.os, "replace", revienta)
    with pytest.raises(OSError):
        mc.guardar(str(ruta), "medio archivo")
    assert ruta.read_bytes() == antes
    assert os.listdir(tmp_path) == ["nota.md"]
