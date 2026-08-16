"""Fase 3.3b — `ui.adapters.metodo_data` (Método tradicional · La matriz).

`ui/componentes/metodo.html` tenía `var MATRIZ`/`var ROC_19A` congelados: una copia a mano
de la hoja de la clase de Greco fechada 5/1/2026, y una copia de `knowledge/roc_19a.yaml`
que ya había divergido del yaml vivo (CONY 53.07% congelado vs 51.52% real al momento de
este PR). Esta fase deriva `div`/`tot`/`val`/`ult` de cada fila con
`price_cache.load_history` + `backtest.run_backtest` (el motor reconciliado al 0.013% contra
el extracto real de IB en la Fase 3.1) y lee `ROC_19A` de `logic.load_roc_19a()`.

A diferencia de `test_comparacion_data.py` (Fase 3.3a), aquí NO hay un `last`/ground-truth
de retorno fijo que pinear: `metodo_data()` corre hasta HOY (se auto-refresca con el caché
semanal), así que las cifras se mueven cada semana por diseño. Lo que se protege es la
FORMA y las INVARIANTES matemáticas — no un número puntual que cambiaría solo y rompería
el test sin que hubiera ningún bug real.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from ui.adapters import MET_CASO, metodo_data  # noqa: E402

_COMPONENTE = os.path.join(os.path.dirname(__file__), "ui", "componentes", "metodo.html")

# El caso de estudio (ticker/fecha de apertura/aporte inicial/RENDI de la hoja) es el
# dinero LITERAL que salió del bolsillo de Greco — congelado a propósito, nunca se deriva.
# Ver docstring de `MET_CASO` en `ui/adapters.py`.
_CASO_ESPERADO = {c["t"]: c for c in MET_CASO}


@pytest.fixture(scope="module")
def datos():
    d = metodo_data()
    assert d is not None, (
        "metodo_data() devolvió None — algún ticker del caso de estudio no cargó "
        "historia (ni caché ni yfinance en vivo). Con solo 5 filas fijas, no hay "
        "'universo parcial' razonable que mostrar.")
    return d


# ── Forma del JSON ───────────────────────────────────────────────────────────────────────

def test_las_5_filas_del_caso_de_estudio_estan_presentes_y_en_orden(datos):
    tickers = [r["t"] for r in datos["matriz"]]
    assert tickers == ["CONY", "NVDY", "MSTY", "TSLY", "NFLY"]


@pytest.mark.parametrize("tk", ["CONY", "NVDY", "MSTY", "TSLY", "NFLY"])
def test_ini_inv_dr_son_los_literales_congelados_de_la_hoja(datos, tk):
    """`ini`/`inv`/`dr` son el caso de estudio — NUNCA se derivan, así que tienen que
    coincidir al centavo con la hoja de la clase, siempre, sin importar cuándo corra el
    test (a diferencia de div/val/ult, que sí se mueven cada semana)."""
    fila = next(r for r in datos["matriz"] if r["t"] == tk)
    esperado = _CASO_ESPERADO[tk]
    assert fila["ini"] == esperado["ini"]
    assert fila["inv"] == pytest.approx(esperado["inv"], abs=0.001)
    assert fila["dr"] == pytest.approx(esperado["dr"], abs=0.001)


def test_tot_inv_es_la_suma_exacta_de_los_aportes_congelados(datos):
    # Este SÍ es un número fijo para siempre: es la suma de 5 literales que nunca cambian.
    assert datos["tot"]["inv"] == pytest.approx(48286.22, abs=0.01)


# ── Invariantes matemáticas (protegen contra un cableado invertido/roto,
# sin depender de un número puntual que se mueve con el mercado) ──────────────────────────

@pytest.mark.parametrize("tk", ["CONY", "NVDY", "MSTY", "TSLY", "NFLY"])
def test_val_con_drip_nunca_es_menor_que_max_sin_drip(datos, tk):
    """Con DRIP, las acciones originales siguen ahí Y se suman las que compró cada
    distribución (>= 0 cada vez) — `val` (Con DRIP) tiene que ser SIEMPRE >= `max` (Sin
    DRIP, solo las acciones originales). Si esto falla, `drip=True`/`drip=False` están
    invertidos en alguna parte del cableado."""
    fila = next(r for r in datos["matriz"] if r["t"] == tk)
    assert fila["val"] >= fila["max"] - 0.01, (
        f"{tk}: val ({fila['val']}) < max ({fila['max']}) — el DRIP no puede valer menos "
        "que no haber reinvertido nada.")


@pytest.mark.parametrize("tk", ["CONY", "NVDY", "MSTY", "TSLY", "NFLY"])
def test_tot_es_inv_mas_div_el_doble_conteo_que_denuncia_la_seccion(datos, tk):
    fila = next(r for r in datos["matriz"] if r["t"] == tk)
    assert fila["tot"] == pytest.approx(fila["inv"] + fila["div"], abs=0.01)


def test_tot_agregado_es_la_suma_de_las_filas(datos):
    tot = datos["tot"]
    for campo in ("div", "val", "ult"):
        suma = sum(r[campo] for r in datos["matriz"])
        assert tot[campo] == pytest.approx(suma, abs=0.02), f"tot[{campo!r}] no cuadra"
    assert tot["totHoja"] == round(tot["inv"] + tot["div"])


@pytest.mark.parametrize("tk", ["CONY", "NVDY", "MSTY", "TSLY", "NFLY"])
def test_div_val_ult_max_son_positivos(datos, tk):
    """No es un valor puntual — pero div/val/max NEGATIVOS, o div=0 (cero distribuciones
    en ~2-3 años de un fondo que paga semanal/mensual) delatarían un cableado roto antes
    de mirar cifras exactas."""
    fila = next(r for r in datos["matriz"] if r["t"] == tk)
    assert fila["div"] > 0
    assert fila["val"] > 0
    assert fila["max"] > 0
    assert fila["ult"] >= 0


# ── ROC 19a: yaml vivo, no la copia congelada ────────────────────────────────────────────

def test_roc19a_viene_del_yaml_vivo_no_de_una_copia_congelada(datos):
    """Ground truth: al momento de este PR, `knowledge/roc_19a.yaml` tenía CONY 51.52% y
    NVDY 41.22% — la copia congelada que reemplaza este PR tenía 53.07%/41.08%. No fijamos
    el valor exacto (el yaml se refresca semanalmente), pero si algún día vuelve a leer
    53.07%/41.08% en vez de lo que hay en el yaml, este test lo caza: son números
    incompatibles con `logic.load_roc_19a()` en cualquier semana razonable."""
    import logic
    yaml_vivo = logic.load_roc_19a()
    for tk in ("CONY", "NVDY", "MSTY", "TSLY", "NFLY"):
        assert tk in datos["roc19a"], f"falta {tk} en roc19a"
        esperado = yaml_vivo.get(tk, {}).get("weighted_pct")
        if esperado is None:
            continue
        assert datos["roc19a"][tk] == pytest.approx(float(esperado) / 100.0, abs=0.0001)


def test_roc19a_es_una_fraccion_0_1(datos):
    for tk, v in datos["roc19a"].items():
        assert 0.0 <= v <= 1.0, f"{tk}: roc19a fuera de rango [0,1]: {v}"


# ── Fuente declarada: cache pineado en el repo, sin degradados ──────────────────────────

def test_fuente_es_cache_para_las_5_filas(datos):
    assert set(datos["fuente"]) == {"CONY", "NVDY", "MSTY", "TSLY", "NFLY"}
    for tk, fuente in datos["fuente"].items():
        assert fuente == "cache", f"{tk} no vino de caché ({fuente!r})"
    assert datos["degradado"] == []


def test_nfly_tiene_cache_propio():
    """Fase 3.3b agregó NFLY a `fetch_price_cache.py` — antes faltaba del todo (el caso
    de estudio lo necesita y no estaba en la lista de 8 tickers de la Fase 3.2)."""
    ruta = os.path.join(os.path.dirname(__file__), "knowledge", "price_cache", "NFLY.parquet")
    assert os.path.exists(ruta), "falta knowledge/price_cache/NFLY.parquet"


# ── No hay cifras congeladas: MATRIZ/ROC_19A viejos no pueden reaparecer ─────────────────

def test_metodo_html_no_tiene_la_matriz_congelada():
    """`metodo.html` (pre esta fase) declaraba `var MATRIZ = [{ t:"CONY", ini:"9/6/2023",
    dr:74.05, inv: 9004.87, div:22873.37, ... }, ...]` con literales numéricos inline —
    la copia a mano de la hoja fechada 5/1/2026. Aserción estructural: esa declaración con
    literales no puede reaparecer; `MATRIZ` tiene que venir de `DATA.matriz`."""
    with open(_COMPONENTE, encoding="utf-8") as f:
        html = f.read()

    assert "{{DATA_JSON}}" in html, "falta el punto de inyección {{DATA_JSON}}"
    assert "var DATA = {{DATA_JSON}}" in html
    assert "var MATRIZ = DATA.matriz" in html
    assert "var ROC_19A = DATA.roc19a" in html

    # El patrón viejo: `var MATRIZ = [` con un array-literal inline (la copia congelada
    # de la hoja) — ya no debe existir en absoluto, la única declaración de `var MATRIZ`
    # tiene que ser la que lee de `DATA.matriz` (aserción de arriba).
    assert not re.search(r"var MATRIZ\s*=\s*\[", html), (
        "`var MATRIZ` volvió a declararse como array-literal — la copia congelada "
        "reapareció")
    assert not re.search(r't\s*:\s*"CONY".*?div\s*:\s*[\d.]+', html, re.S), (
        "encontré un literal tipo `{ t:\"CONY\", ..., div:NNN }` — parece la matriz "
        "vieja copiada a mano")

    # ROC_19A viejo: `var ROC_19A = { CONY:0.5307, ... }` con literales inline.
    m2 = re.search(r"var ROC_19A\s*=\s*([^;]+);", html)
    assert m2 is not None, "no se encontró la declaración de `var ROC_19A`"
    assert not re.search(r"CONY\s*:\s*[\d.]+", m2.group(1)), (
        "`var ROC_19A` volvió a tener literales inline — la copia congelada del yaml "
        "reapareció")


def test_metodo_html_no_declara_tot_con_literales():
    with open(_COMPONENTE, encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"var TOT\s*=\s*([^;]+);", html)
    assert m is not None, "no se encontró la declaración de `var TOT`"
    assert m.group(1).strip() == "DATA.tot", (
        f"`var TOT` ya no lee de DATA.tot: {m.group(1)!r}")


def test_render_metodo_inyecta_data_json():
    """`ui.componentes.render_metodo` debe recibir `datos` y usarlo para reemplazar
    `{{DATA_JSON}}` — antes de esta fase la función no tomaba `datos` en absoluto."""
    ruta = os.path.join(os.path.dirname(__file__), "ui", "componentes", "__init__.py")
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"def render_metodo\(([^)]*)\)", src)
    assert m is not None
    assert "datos" in m.group(1), "render_metodo ya no acepta `datos`"
    inicio = src.index("def render_metodo(")
    fin = src.index("\ndef ", inicio + 1)
    cuerpo = src[inicio:fin]
    assert '"{{DATA_JSON}}"' in cuerpo and "json.dumps(datos" in cuerpo
