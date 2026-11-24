"""Un refresco automático no reemplaza lo guardado por algo vacío o recortado.

Una historia de precios a medias o una tabla 19(a) truncada llegan sin error. Si traen menos
del 90 % de las filas que ya había, se conserva lo guardado y la corrida sale en rojo.
"""
import pandas as pd
import pytest
import yaml

import fetch_price_cache as fpc
import fetch_roc_19a as roc


# ── Precios ─────────────────────────────────────────────────────────────────────────────

def _hist(n, cierre=10.0):
    idx = pd.bdate_range("2024-01-02", periods=n)
    return pd.DataFrame({"Close": cierre, "Dividends": 0.0}, index=idx)


def _splits(n):
    idx = pd.to_datetime([f"202{i}-03-01" for i in range(n)])
    return pd.Series([2.0] * n, index=idx)


@pytest.fixture
def cache(monkeypatch, tmp_path):
    monkeypatch.setattr(fpc, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(fpc, "META_PATH", str(tmp_path / "_meta.yaml"))
    monkeypatch.setattr(fpc, "SPLITS_PATH", str(tmp_path / "_splits.yaml"))

    def correr(hist, splits=None):
        monkeypatch.setattr(fpc, "fetch_one", lambda tk: (hist, splits))
        return fpc.main(["fetch_price_cache.py", "SCHB"])
    return tmp_path, correr


def _guardado(tmp_path):
    return pd.read_parquet(tmp_path / "SCHB.parquet")


@pytest.mark.parametrize("filas_nuevas,se_guarda", [(89, False), (90, True), (100, True),
                                                    (130, True)])
def test_la_historia_recortada_no_pisa_el_cache(cache, capsys, filas_nuevas, se_guarda):
    """Borde medido a una fila de cada lado: con 100 guardadas, 90 entran y 89 no."""
    tmp_path, correr = cache
    assert correr(_hist(100, cierre=10.0)) == 0
    meta_antes = (tmp_path / "_meta.yaml").read_text()
    codigo = correr(_hist(filas_nuevas, cierre=20.0))
    guardado = _guardado(tmp_path)
    if se_guarda:
        assert codigo == 0
        assert len(guardado) == filas_nuevas and guardado["Close"].iloc[0] == 20.0
    else:
        assert codigo == 1, "tenía cache y lo nuevo llegó recortado: es regresión"
        assert len(guardado) == 100 and guardado["Close"].iloc[0] == 10.0
        assert yaml.safe_load((tmp_path / "_meta.yaml").read_text()) == yaml.safe_load(meta_antes)
        aviso = capsys.readouterr().err
        assert "89 filas y había 100 guardadas" in aviso and "Conservo el cache previo" in aviso


def test_sin_cache_previo_cualquier_historia_entra(cache):
    tmp_path, correr = cache
    assert correr(_hist(3)) == 0
    assert len(_guardado(tmp_path)) == 3


def test_el_parquet_previo_cuenta_aunque_el_meta_no_lo_tenga(cache):
    """La guarda mira el archivo guardado, no lo que el meta diga de él."""
    tmp_path, correr = cache
    _hist(100).to_parquet(tmp_path / "SCHB.parquet")
    assert correr(_hist(50, cierre=20.0)) == 1
    assert len(_guardado(tmp_path)) == 100


@pytest.mark.parametrize("llegan", [None, 0, 1])
def test_los_splits_guardados_no_se_pierden_si_llegan_menos(cache, capsys, llegan):
    tmp_path, correr = cache
    assert correr(_hist(100), _splits(2)) == 0
    antes = yaml.safe_load((tmp_path / "_splits.yaml").read_text())["SCHB"]
    assert len(antes) == 2
    codigo = correr(_hist(101, cierre=20.0), None if llegan is None else _splits(llegan))
    assert codigo == 1
    assert yaml.safe_load((tmp_path / "_splits.yaml").read_text())["SCHB"] == antes
    assert "había 2 guardados. Conservo los previos" in capsys.readouterr().err
    assert len(_guardado(tmp_path)) == 101, "los precios sí se actualizan"


def test_los_splits_que_crecen_o_se_mantienen_se_escriben(cache):
    tmp_path, correr = cache
    assert correr(_hist(100), _splits(1)) == 0
    assert correr(_hist(100), _splits(1)) == 0
    assert correr(_hist(100), _splits(3)) == 0
    assert len(yaml.safe_load((tmp_path / "_splits.yaml").read_text())["SCHB"]) == 3


# ── Tabla 19(a) ─────────────────────────────────────────────────────────────────────────

def _filas(n, pct=50.0):
    return [(f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", pct, 1.0) for i in range(n)]


@pytest.fixture
def tabla(monkeypatch, tmp_path):
    monkeypatch.setattr(roc, "ROC_PATH", str(tmp_path / "roc_19a.yaml"))
    monkeypatch.setattr(roc, "DIST_RATE_PATH", str(tmp_path / "rate.yaml"))
    monkeypatch.setattr(roc, "FUND_DELAY", 0)
    monkeypatch.setattr(roc, "parse_distribution_rate_from_html", lambda html: {})

    def correr(filas):
        monkeypatch.setattr(roc, "fetch_rows_with_retries", lambda url, tk: (filas, ""))
        return roc.main(["fetch_roc_19a.py", "MSTY"])

    def leer():
        return yaml.safe_load((tmp_path / "roc_19a.yaml").read_text())["MSTY"]
    return correr, leer


@pytest.mark.parametrize("filas_nuevas,se_guarda", [(35, False), (36, True), (40, True),
                                                    (44, True)])
def test_la_tabla_truncada_no_reemplaza_la_entrada(tabla, capsys, filas_nuevas, se_guarda):
    """Con 40 distribuciones guardadas, 36 entran (90 %) y 35 no."""
    correr, leer = tabla
    assert correr(_filas(40, pct=50.0)) == 0
    codigo = correr(_filas(filas_nuevas, pct=80.0))
    entrada = leer()
    if se_guarda:
        assert codigo == 0
        assert len(entrada["per_distribution"]) == filas_nuevas
        assert entrada["weighted_pct"] == 80.0
    else:
        assert codigo == 1
        assert len(entrada["per_distribution"]) == 40 and entrada["weighted_pct"] == 50.0
        aviso = capsys.readouterr().err
        assert "35 distribuciones y había 40 guardadas" in aviso
        assert "Conservo la entrada previa" in aviso


def test_un_fondo_nuevo_entra_con_las_filas_que_traiga(tabla):
    correr, leer = tabla
    assert correr(_filas(2)) == 0
    assert len(leer()["per_distribution"]) == 2


def test_la_tabla_vacia_sigue_conservando_la_entrada(tabla):
    correr, leer = tabla
    assert correr(_filas(40)) == 0
    assert correr([]) == 1
    assert len(leer()["per_distribution"]) == 40


def test_el_umbral_es_el_mismo_en_los_dos_refrescos():
    assert roc.refresco_recortado(89, 100) and not roc.refresco_recortado(90, 100)
    assert not roc.refresco_recortado(0, 0) and not roc.refresco_recortado(5, None)
    assert roc.refresco_recortado(0, 1)
