"""Contraste de los dividendos del cache con la tabla oficial de YieldMax (`fetch_price_cache`).

Incidente: el 1-oct-2026 yfinance copió la distribución del 8-oct sobre la del 1-oct en todos
los YieldMax con ex-date en jueves, y `knowledge/price_cache/` lo arrastró (MSTY 0.245 contra
0.3111 oficial). Las cifras de estos tests son de la página oficial de cada fondo y del cache
tal como estaba, leídas el 2026-10-30; ninguna sale del código que se prueba.

Sin red: el HTML es un recorte de la página real de MSTY y `fetch_oficial` se sustituye.
"""
import os
import sys

import pandas as pd
import pytest
import yaml

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import fetch_price_cache as fpc   # noqa: E402

# Recorte de https://yieldmaxetfs.com/our-etfs/msty/ (2026-10-30): la tabla de rendimientos va
# antes y no tiene ex-date; la de distribuciones repite el pago del 4-dic-2025, como la real.
HTML_MSTY = """
<table><thead><tr><th>Fund Ticker</th><th>1 Month</th><th>YTD</th></tr></thead>
<tbody><tr><td>MKT</td><td>12.21%</td><td>-0.71%</td></tr></tbody></table>
<table class="distributions-table"><thead><tr><th>DISTRIBUTION PER SHARE</th>
<th>DECLARED DATE</th><th>EX DATE</th><th>RECORD DATE</th><th>PAYABLE DATE</th><th>ROC</th>
</tr></thead><tbody>
<tr><td>$0.1630</td><td>10/28/2026</td><td>10/29/2026</td><td>10/29/2026</td><td>10/30/2026</td><td>13.70%</td></tr>
<tr><td>$0.1671</td><td>10/21/2026</td><td>10/22/2026</td><td>10/22/2026</td><td>10/23/2026</td><td>0.00%</td></tr>
<tr><td>$0.2474</td><td>10/14/2026</td><td>10/15/2026</td><td>10/15/2026</td><td>10/16/2026</td><td>0.00%</td></tr>
<tr><td>$0.2445</td><td>10/07/2026</td><td>10/08/2026</td><td>10/08/2026</td><td>10/09/2026</td><td>78.12%</td></tr>
<tr><td>$0.3111</td><td>09/30/2026</td><td>10/01/2026</td><td>10/01/2026</td><td>10/02/2026</td><td>98.87%</td></tr>
<tr><td>$0.3421</td><td>09/23/2026</td><td>09/24/2026</td><td>09/24/2026</td><td>09/25/2026</td><td>97.70%</td></tr>
<tr><td>$0.1388</td><td>12/03/2025</td><td>12/04/2025</td><td>12/04/2025</td><td>12/05/2025</td><td>—</td></tr>
<tr><td>$0.1388</td><td>12/03/2025</td><td>12/04/2025</td><td>12/04/2025</td><td>12/05/2025</td><td>92.88%</td></tr>
</tbody></table>
"""

# El cache de MSTY antes del arreglo: el 1-oct trae el 0.245 del 8-oct; los demás difieren de
# la tabla oficial solo por el redondeo a 3 decimales (el 8-oct, justo media milésima).
YF_MSTY = {"2026-09-24": 0.342, "2026-10-01": 0.245, "2026-10-08": 0.245,
           "2026-10-15": 0.247, "2026-10-22": 0.167}


def _serie(montos, inicio="2026-09-21", fin="2026-10-23"):
    """Dividendos de yfinance sobre días hábiles: cero salvo en las fechas dadas."""
    idx = pd.bdate_range(inicio, fin)
    s = pd.Series(0.0, index=idx)
    for fecha, monto in montos.items():
        s.loc[pd.Timestamp(fecha)] = monto
    return s


def _oficial(montos):
    return pd.Series({pd.Timestamp(k): v for k, v in montos.items()}, dtype=float).sort_index()


# ── Parser ──────────────────────────────────────────────────────────────────────────────

def test_el_parser_lee_el_ex_date_y_no_la_fecha_de_declaracion():
    s = fpc.parse_distribuciones_oficiales(HTML_MSTY)
    assert [d.date().isoformat() for d in s.index] == [
        "2025-12-04", "2026-09-24", "2026-10-01", "2026-10-08", "2026-10-15", "2026-10-22",
        "2026-10-29"]
    assert s[pd.Timestamp("2026-10-01")] == 0.3111
    assert s[pd.Timestamp("2025-12-04")] == 0.1388


def test_el_parser_sin_tabla_de_distribuciones_devuelve_vacio():
    solo_rendimientos = HTML_MSTY.split('<table class="distributions-table">')[0]
    assert fpc.parse_distribuciones_oficiales(solo_rendimientos).empty


def test_dos_importes_para_la_misma_fecha_no_se_resuelven_en_silencio():
    ambigua = HTML_MSTY.replace(
        "<td>$0.1388</td><td>12/03/2025</td><td>12/04/2025</td><td>12/04/2025</td>"
        "<td>12/05/2025</td><td>92.88%</td>",
        "<td>$0.6940</td><td>12/03/2025</td><td>12/04/2025</td><td>12/04/2025</td>"
        "<td>12/05/2025</td><td>92.88%</td>")
    assert ambigua != HTML_MSTY
    with pytest.raises(ValueError, match="2025-12-04"):
        fpc.parse_distribuciones_oficiales(ambigua)


# ── Contraste ───────────────────────────────────────────────────────────────────────────

def test_corrige_el_1_oct_y_deja_el_redondeo_de_yfinance():
    oficial = fpc.parse_distribuciones_oficiales(HTML_MSTY)
    serie, correcciones, sin_fila = fpc.reconciliar_dividendos(_serie(YF_MSTY), oficial)
    assert correcciones == [{"fecha": "2026-10-01", "tipo": "importe",
                             "yfinance": 0.245, "oficial": 0.3111}]
    assert sin_fila == []
    assert serie[pd.Timestamp("2026-10-01")] == 0.3111
    for fecha in ("2026-09-24", "2026-10-08", "2026-10-15", "2026-10-22"):
        assert serie[pd.Timestamp(fecha)] == YF_MSTY[fecha], f"{fecha}: es redondeo, no error"


def test_mas_de_media_milesima_ya_no_es_redondeo():
    serie, correcciones, _ = fpc.reconciliar_dividendos(
        _serie({"2026-10-01": 0.0506}), _oficial({"2026-10-01": 0.0500}))
    assert serie[pd.Timestamp("2026-10-01")] == 0.05
    assert len(correcciones) == 1


def test_no_contrasta_antes_del_ultimo_split():
    """El caso de TSLY: antes de su split de feb-2024 la tabla oficial da el doble que
    yfinance, y es yfinance el que cuadra con su serie de precios. Entre los dos splits la
    oficial está en importes de antes del split de dic-2025 (0.2 contra 1.0)."""
    divs = pd.Series(0.0, index=pd.bdate_range("2024-02-01", "2026-10-09"))
    divs.loc[pd.Timestamp("2024-02-07")] = 4.05
    divs.loc[pd.Timestamp("2025-06-05")] = 1.0
    divs.loc[pd.Timestamp("2026-10-01")] = 0.219
    divs.loc[pd.Timestamp("2026-10-08")] = 0.219
    oficial = _oficial({"2024-02-07": 0.8092, "2025-06-05": 0.2, "2026-10-01": 0.23,
                        "2026-10-08": 0.2193})
    splits = pd.Series({pd.Timestamp("2024-02-26"): 0.5, pd.Timestamp("2025-12-01"): 0.2})
    serie, correcciones, _ = fpc.reconciliar_dividendos(divs, oficial, splits)
    assert serie[pd.Timestamp("2024-02-07")] == 4.05
    assert serie[pd.Timestamp("2025-06-05")] == 1.0
    assert serie[pd.Timestamp("2026-10-01")] == 0.23
    assert [c["fecha"] for c in correcciones] == ["2026-10-01"]


def test_añade_la_que_falta_y_quita_la_que_sobra():
    """yfinance con el pago un día tarde: la fecha buena se rellena y la mala se vacía, así el
    pago no cuenta dos veces."""
    serie, correcciones, _ = fpc.reconciliar_dividendos(
        _serie({"2026-09-24": 0.342, "2026-10-02": 0.3111, "2026-10-08": 0.245}),
        _oficial({"2026-09-24": 0.3421, "2026-10-01": 0.3111, "2026-10-08": 0.2445}))
    assert serie[pd.Timestamp("2026-10-01")] == 0.3111
    assert serie[pd.Timestamp("2026-10-02")] == 0.0
    assert [(c["fecha"], c["tipo"]) for c in correcciones] == [
        ("2026-10-01", "faltaba"), ("2026-10-02", "sobraba")]


def test_lo_anterior_y_lo_posterior_a_la_tabla_no_se_juzga():
    """Antes de la primera fila oficial la tabla no dice nada, y después de la última puede ir
    un día por detrás de yfinance: en los dos lados se queda lo de yfinance."""
    serie, correcciones, _ = fpc.reconciliar_dividendos(
        _serie({"2026-09-17": 0.24, "2026-09-24": 0.342, "2026-10-01": 0.3111,
                "2026-10-08": 0.245}, inicio="2026-09-14"),
        _oficial({"2026-09-24": 0.3421, "2026-10-01": 0.3111}))
    assert serie[pd.Timestamp("2026-09-17")] == 0.24
    assert serie[pd.Timestamp("2026-10-08")] == 0.245
    assert correcciones == []


def test_fuera_del_historial_de_precios_no_hay_hueco():
    """Un ex-date posterior a la última fila de precio aún no tiene dónde ir, y uno anterior a
    la primera queda fuera del cache: ninguno de los dos es una fila que falte."""
    _, correcciones, sin_fila = fpc.reconciliar_dividendos(
        _serie({"2026-09-24": 0.342}, fin="2026-10-23"),
        _oficial({"2025-12-04": 0.1388, "2026-09-24": 0.3421, "2026-10-29": 0.163}))
    assert correcciones == [] and sin_fila == []


def test_un_ex_date_sin_fila_de_precio_se_avisa_y_no_se_coloca():
    serie, correcciones, sin_fila = fpc.reconciliar_dividendos(
        _serie({"2026-09-24": 0.342}), _oficial({"2026-09-24": 0.3421, "2026-10-03": 0.5}))
    assert sin_fila == [pd.Timestamp("2026-10-03")]
    assert correcciones == []
    assert pd.Timestamp("2026-10-03") not in serie.index


def test_tres_cambios_se_aplican_y_cuatro_se_rechazan_enteros():
    fechas = ["2026-09-24", "2026-10-01", "2026-10-08", "2026-10-15"]
    yf = _serie({f: 0.2 for f in fechas})
    tres = _oficial({f: (0.3 if i < 3 else 0.2) for i, f in enumerate(fechas)})
    _, correcciones, _ = fpc.reconciliar_dividendos(yf, tres)
    assert len(correcciones) == 3
    with pytest.raises(fpc.ContrasteSospechoso):
        fpc.reconciliar_dividendos(yf, _oficial({f: 0.3 for f in fechas}))
    assert (yf[yf > 0] == 0.2).all(), "la serie de entrada no se toca"


# ── main(): qué se escribe ──────────────────────────────────────────────────────────────

def _hist_msty():
    divs = _serie(YF_MSTY)
    return pd.DataFrame({"Close": 15.0, "Dividends": divs}, index=divs.index)


def _preparar(monkeypatch, tmp_path, oficial):
    monkeypatch.setattr(fpc, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(fpc, "META_PATH", str(tmp_path / "_meta.yaml"))
    monkeypatch.setattr(fpc, "SPLITS_PATH", str(tmp_path / "_splits.yaml"))
    monkeypatch.setattr(fpc, "fetch_one", lambda tk: (_hist_msty(), None))
    monkeypatch.setattr(fpc, "fetch_oficial", oficial)


def test_main_escribe_el_dato_oficial_y_lo_anota(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path, lambda tk: fpc.parse_distribuciones_oficiales(HTML_MSTY))
    assert fpc.main(["fetch_price_cache.py", "MSTY"]) == 0
    guardado = pd.read_parquet(tmp_path / "MSTY.parquet")
    assert guardado.loc[pd.Timestamp("2026-10-01"), "Dividends"] == 0.3111
    meta = yaml.safe_load((tmp_path / "_meta.yaml").read_text())["MSTY"]
    assert meta["dividends_source"] == "yieldmax_oficial"
    assert meta["dividend_corrections"] == ["2026-10-01: 0.245 -> 0.3111"]


def test_main_sin_tabla_oficial_conserva_el_cache_previo(monkeypatch, tmp_path):
    """Escribir lo de yfinance sin contrastar devolvería el 0.245 al cache."""
    previo = _hist_msty()
    previo.loc[pd.Timestamp("2026-10-01"), "Dividends"] = 0.3111
    previo.to_parquet(tmp_path / "MSTY.parquet")
    (tmp_path / "_meta.yaml").write_text(yaml.safe_dump({"MSTY": {"generated_at": "2026-10-24"}}))

    def _caida(tk):
        raise RuntimeError("challenge anti-bot")
    _preparar(monkeypatch, tmp_path, _caida)
    assert fpc.main(["fetch_price_cache.py", "MSTY"]) == 1, "tenía cache: es regresión"
    guardado = pd.read_parquet(tmp_path / "MSTY.parquet")
    assert guardado.loc[pd.Timestamp("2026-10-01"), "Dividends"] == 0.3111
    meta = yaml.safe_load((tmp_path / "_meta.yaml").read_text())["MSTY"]
    assert meta == {"generated_at": "2026-10-24"}


def test_main_contraste_sospechoso_no_escribe(monkeypatch, tmp_path):
    todo_distinto = {f: v * 2 for f, v in YF_MSTY.items()}
    _preparar(monkeypatch, tmp_path, lambda tk: _oficial(todo_distinto))
    assert fpc.main(["fetch_price_cache.py", "MSTY"]) == 0, "sin cache previo no hay regresión"
    assert not (tmp_path / "MSTY.parquet").exists()


def test_main_un_ticker_que_no_es_yieldmax_no_consulta_la_pagina(monkeypatch, tmp_path):
    def _no_llamar(tk):
        raise AssertionError(f"consultó la página oficial para {tk}")
    _preparar(monkeypatch, tmp_path, _no_llamar)
    assert fpc.main(["fetch_price_cache.py", "SCHB"]) == 0
    assert (tmp_path / "SCHB.parquet").exists()
    meta = yaml.safe_load((tmp_path / "_meta.yaml").read_text())["SCHB"]
    assert meta["dividends_source"] == "yfinance" and "dividend_corrections" not in meta


# ── Guardas sobre la lista y sobre el cache versionado ──────────────────────────────────

def test_todo_yieldmax_del_cache_se_contrasta():
    with open(os.path.join(BASE, "knowledge", "instruments.yaml"), encoding="utf-8") as fh:
        fichas = yaml.safe_load(fh) or {}
    yieldmax = {t for t, v in fichas.items()
                if isinstance(v, dict) and str(v.get("type", "")).lower() == "yieldmax"}
    sin_contraste = (yieldmax & set(fpc.TICKERS)) - set(fpc.DISTRIBUCIONES_OFICIALES)
    assert not sin_contraste, f"YieldMax en TICKERS sin contraste oficial: {sin_contraste}"
    assert set(fpc.DISTRIBUCIONES_OFICIALES) <= set(fpc.TICKERS)


@pytest.mark.parametrize("ticker,oficial", [
    ("NVDY", 0.0874), ("TSLY", 0.23), ("CONY", 0.2577), ("MSTY", 0.3111), ("PLTY", 0.2294)])
def test_el_cache_versionado_trae_el_1_oct_oficial(ticker, oficial):
    ruta = os.path.join(BASE, "knowledge", "price_cache", f"{ticker}.parquet")
    if not os.path.exists(ruta):
        pytest.skip(f"sin {ruta}")
    divs = pd.read_parquet(ruta)["Dividends"]
    assert divs.loc[pd.Timestamp("2026-10-01")] == pytest.approx(oficial, abs=1e-9)
