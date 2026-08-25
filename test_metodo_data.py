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

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(__file__))
import logic  # noqa: E402
from ui.adapters import MET_CASO, _payback_contraejemplo, metodo_data  # noqa: E402

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


# ── Fase 3.3c (traspaso 2026-08-17) · Escalera / Payback / Tasa a datos reales ───────────
#
# Mismo criterio que el resto del archivo: forma e invariantes matemáticas, nunca un
# número puntual — `metodo_data()` corre hasta hoy y estas cifras se mueven cada semana
# por diseño. Lo que se protege es que las fórmulas declaradas en el traspaso sigan
# reconciliando entre sí (Regla 2/3 del contrato: nunca dos cifras de bases o momentos
# distintos operadas en la misma fila).

def test_escalera_tiene_las_claves_declaradas(datos):
    esc = datos["escalera"]
    esperadas = {"anuncioTotal", "anuncioAnual", "realPct", "realD", "xirrPct",
                 "ventanaPondAnos", "naivePct", "efectivoPct", "efectivoD",
                 "efectivoXirrPct", "maxTot", "multTot", "multAnual"}
    assert esperadas <= set(esc)


def test_escalera_no_expone_ningun_plazo_inventado(datos):
    """Decisión de Daniel (2026-08-17): «prefiero que sea exacto». `N` era un 3
    redondeado a mano y `cagrPct` la anualización que dependía de él; los dos salieron.
    Dejar conviviendo dos anualizaciones del mismo retorno en el mismo objeto es
    exactamente el defecto que este trabajo cierra."""
    esc = datos["escalera"]
    for prohibida in ("N", "cagrPct", "efectivoCagrPct"):
        assert prohibida not in esc, (
            f"`{prohibida}` volvió a la escalera: el anualizado es TIR exacta, no un "
            "CAGR sobre un plazo elegido a mano")


def test_escalera_anuncio_es_el_literal_fijo_de_la_llamada(datos):
    # 1499%/499% por año es lo que se dijo en la llamada — un dato histórico, no algo
    # que el motor pueda medir. Nunca se mueve.
    assert datos["escalera"]["anuncioTotal"] == pytest.approx(1499.0)
    assert datos["escalera"]["anuncioAnual"] == pytest.approx(499.0)


def test_escalera_real_pct_reconcilia_contra_tot(datos):
    """`realPct` no puede desviarse de `(TOT.val - TOT.inv) / TOT.inv * 100` — es la
    misma cuenta que hace `mCmpCorrectPct`/`metodologia.html` § 9 sobre el mismo TOT."""
    tot = datos["tot"]
    esperado = (tot["val"] - tot["inv"]) / tot["inv"] * 100.0
    assert datos["escalera"]["realPct"] == pytest.approx(esperado, abs=0.01)
    assert datos["escalera"]["realD"] == pytest.approx(tot["val"] - tot["inv"], abs=0.01)


def test_escalera_ventana_ponderada_es_medida_no_un_plazo_redondeado(datos):
    """La ventana que alimenta el ÷N ingenuo es `Σ(inv·años)/Σinv` sobre las fechas de
    apertura reales de `MET_CASO`, contra el `asof` de la corrida. Se recalcula aquí
    desde las mismas fuentes: si alguien vuelve a cablear un 3, esto cae."""
    esc = datos["escalera"]
    asof = pd.Timestamp(datos["asof"])
    pares = [(c["inv"], (asof - pd.Timestamp(c["start"])).days / 365.25) for c in MET_CASO]
    esperada = round(sum(inv * a for inv, a in pares) / sum(inv for inv, _ in pares), 2)
    assert esc["ventanaPondAnos"] == pytest.approx(esperada, abs=0.001)
    # Ningún aporte es más viejo que el más viejo ni más nuevo que el más nuevo.
    assert min(a for _, a in pares) <= esc["ventanaPondAnos"] <= max(a for _, a in pares)


def test_escalera_naive_es_la_division_por_esa_ventana(datos):
    """El ÷N que el panel denuncia tiene que ser el ÷N que el panel muestra — si la
    frase dice «÷ 2.77 años» y la cifra salió de dividir entre otra cosa, la lección
    miente sobre su propio ejemplo."""
    esc = datos["escalera"]
    assert esc["naivePct"] == pytest.approx(esc["realPct"] / esc["ventanaPondAnos"], abs=0.01)


def test_escalera_xirr_es_la_tir_de_los_aportes_reales_contra_tot_val(datos):
    """`xirrPct` es la TIR de los cinco aportes de `MET_CASO` en sus fechas contra el
    valor de mercado de hoy. Los dividendos NO entran: se reinvirtieron, nunca tocaron el
    bolsillo, y su efecto ya está dentro de `tot.val` — meterlos los contaría dos veces.
    """
    esc, tot = datos["escalera"], datos["tot"]
    esperado = logic.xirr(
        [(c["start"], -c["inv"]) for c in MET_CASO] + [(datos["asof"], tot["val"])]
    )
    assert esperado is not None
    assert esc["xirrPct"] == pytest.approx(esperado * 100.0, abs=0.01)


def test_escalera_la_tir_no_coincide_con_el_atajo_que_denuncia(datos):
    """Si `xirrPct` == `naivePct`, el panel dejó de ilustrar nada: estaría denunciando un
    error y mostrando ese mismo error como respuesta correcta."""
    esc = datos["escalera"]
    if esc["realPct"] > 0:
        assert esc["xirrPct"] != pytest.approx(esc["naivePct"], abs=0.05)


def test_escalera_max_tot_es_la_suma_de_max_de_la_matriz(datos):
    esperado = round(sum(f["max"] for f in datos["matriz"]), 2)
    assert datos["escalera"]["maxTot"] == pytest.approx(esperado, abs=0.02)


def test_escalera_efectivo_es_max_tot_mas_divsin_menos_inv(datos):
    """Fila «Si los dividendos fueran efectivo»: el contrafáctico sin reinversión —
    `maxTot` (techo sin DRIP) + dividendos que habría cobrado ESA posición − lo aportado.

    Antes esta aserción usaba `tot["div"]` (los dividendos del mundo que SÍ reinvirtió) y
    por tanto fijaba el bug en vez de cazarlo: pasaba porque comparaba la fórmula consigo
    misma. El panel dice «retorno teórico si nada se hubiera reinvertido», y su celda
    vecina (`efectivoXirrPct`) siempre salió de la corrida sin DRIP — las dos mitades de
    la misma fila describían mundos distintos (+267.2% contra un XIRR cuyos flujos suman
    +63.2%). Ver `test_contrafactico_sin_drip.py`."""
    esc, tot = datos["escalera"], datos["tot"]
    esperado_d = esc["maxTot"] + tot["divSin"] - tot["inv"]
    assert esc["efectivoD"] == pytest.approx(esperado_d, abs=0.02)
    assert esc["efectivoPct"] == pytest.approx(esperado_d / tot["inv"] * 100.0, abs=0.01)


def test_escalera_efectivo_describe_el_mismo_mundo_que_su_xirr(datos):
    """Guarda no-tautológica de la fila: el total y la anualización que se muestran juntos
    tienen que salir de la misma simulación. `efectivoD + inv` es el valor final del
    contrafáctico, y eso debe ser `sinTotReal` (el `final_total_value` de `r_sin`), que es
    de donde también salen los flujos del XIRR. Es la aserción que faltaba: la de arriba
    reconcilia la fórmula, esta reconcilia contra el motor."""
    esc, tot = datos["escalera"], datos["tot"]
    assert esc["efectivoD"] + tot["inv"] == pytest.approx(tot["sinTotReal"], abs=0.05)


# `test_escalera_efectivo_es_siempre_mayor_que_real_el_doble_conteo_que_denuncia` se
# JUBILÓ el 2026-08-23 (traspaso de los 16 tests del caché móvil). No se jubila por el
# doble conteo —esa lección la cazan los dos guards de arriba, vivos— sino porque su
# aserción final (`efectivoPct > realPct`) era un HECHO DE MERCADO: +63.2% contra +59.9%
# cuando se escribió, y hoy midió 64.02 contra 68.08 — se invirtió sin que nadie rompiera
# nada. Su propio docstring lo anticipaba: «si un día se invierte, es dato nuevo —el DRIP
# pasó a ganar a nivel cartera— y no un bug: la lección del panel (÷N no es anualizar) no
# depende del signo». La lección real sigue guardada; solo se retiró la apuesta al signo
# del mercado (Regla 6 del contrato).


def test_escalera_mult_son_none_o_positivos_y_reconcilian(datos):
    esc = datos["escalera"]
    if esc["realPct"] > 0:
        assert esc["multTot"] == pytest.approx(esc["anuncioTotal"] / esc["realPct"], abs=0.1)
    else:
        assert esc["multTot"] is None
    if esc["xirrPct"] is not None and esc["xirrPct"] > 0:
        assert esc["multAnual"] == pytest.approx(esc["anuncioAnual"] / esc["xirrPct"], abs=0.1)
    else:
        assert esc["multAnual"] is None


# ── modal-tmtot · la paradoja «ganó y perdió» (traspaso 2026-08-17, Duda 3) ────────────

def test_ratios_tienen_perdida_capital_por_fila(datos):
    """Es la versión per-fila del agregado que ya dibuja el modal arriba
    (`mTmtotPerdida`): Total inv. − Valor mer. Si la suma de las filas no da el agregado,
    una de las dos está mirando otra base."""
    ratios = {r["t"]: r["perdidaCapital"] for r in datos["ratios"]}
    for f in datos["matriz"]:
        assert ratios[f["t"]] == pytest.approx((f["inv"] + f["div"]) - f["val"], abs=0.02)
    tot = datos["tot"]
    assert sum(ratios.values()) == pytest.approx((tot["inv"] + tot["div"]) - tot["val"], abs=0.1)


def test_perdida_capital_es_contra_total_inv_no_contra_lo_aportado(datos):
    """Regla 2 del contrato de auditoría: declarar la base. La cifra que el modal
    presenta como «pérdida de capital frente a su Total inv.» tiene que estar medida
    contra Total inv. (aportado + dividendos reinvertidos), no contra el aportado — son
    bases distintas y confundirlas es justo lo que el modal existe para desenredar."""
    for f, r in zip(datos["matriz"], datos["ratios"]):
        assert r["t"] == f["t"]
        contra_aportado = f["inv"] - f["val"]
        if abs(f["div"]) > 1.0:
            assert r["perdidaCapital"] != pytest.approx(contra_aportado, abs=0.5), (
                f"{f['t']}: `perdidaCapital` quedó medida contra el aportado, no contra "
                "Total inv. — cambió de base sin decirlo")


def test_tmtot_ejemplo_es_el_mayor_retorno_entre_los_que_perdieron_capital(datos):
    """El protagonista del párrafo se elige en cada corrida, no se cablea: es el ticker
    donde la paradoja se ve mejor (ganó más y aun así está bajo su Total inv.)."""
    tk = datos["tmtotEjemplo"]
    candidatos = [r for r in datos["ratios"] if r["perdidaCapital"] > 0]
    if not candidatos:
        assert tk is None
        return
    assert tk == max(candidatos, key=lambda r: r["ret"])["t"]
    fila = [r for r in datos["ratios"] if r["t"] == tk][0]
    # La paradoja tiene que ser una paradoja: ganó Y perdió capital a la vez.
    assert fila["perdidaCapital"] > 0


def test_modal_tmtot_no_conserva_las_dos_cifras_congeladas_de_nvdy():
    """Los dos literales que el modal citaba a mano (+244.1% de retorno y $11,673.52 de
    pérdida de capital) eran del día que se armó la hoja; medidos hoy dan +282.9% y
    $12,281.41. Vivían a dos párrafos de cuatro cifras que sí se alimentaban en vivo."""
    with open(_COMPONENTE, encoding="utf-8") as f:
        html = f.read()
    for literal in ("+244.1%", "$11,673.52"):
        assert literal not in html.split("<script")[0], (
            f"el literal congelado {literal!r} volvió al marcado de modal-tmtot")
    assert 'id="mTmtotParadoja"' in html, "falta el punto de inyección del párrafo"
    assert "DATA.tmtotEjemplo" in html, (
        "el modal no lee `tmtotEjemplo` — ¿volvió a cablear el protagonista a mano?")


# ── Payback ≠ ganancia (Bloque 4) ─────────────────────────────────────────────────────

def test_ratios_las_5_filas_en_el_mismo_orden_que_met_caso(datos):
    assert [r["t"] for r in datos["ratios"]] == ["CONY", "NVDY", "MSTY", "TSLY", "NFLY"]


@pytest.mark.parametrize("tk", ["CONY", "NVDY", "MSTY", "TSLY", "NFLY"])
def test_ratios_por_fila_reconcilian_contra_la_matriz(datos, tk):
    """`pb`/`ret`/`retD` no son un cálculo aparte: tienen que salir exactamente
    de la misma fila de `matriz` que ya reconcilió `test_val_con_drip_...` — Regla 2
    del contrato, nunca mezclar bases dentro de la misma fila."""
    fila = next(f for f in datos["matriz"] if f["t"] == tk)
    r = next(x for x in datos["ratios"] if x["t"] == tk)
    pb_esperado = fila["div"] / fila["inv"]
    assert r["pb"] == pytest.approx(pb_esperado, abs=0.001)
    assert r["ret"] == pytest.approx((fila["val"] - fila["inv"]) / fila["inv"] * 100.0, abs=0.01)
    assert r["retD"] == pytest.approx(fila["val"] - fila["inv"], abs=0.01)


# ── `tasaNra`: la única cifra fiscal simulada que sigue expuesta ──────────────────────

def test_tasa_nra_es_030_la_cota_superior_de_siempre(datos):
    # Decisión 3/4 del traspaso: el valor no cambia, solo deja de estar escrito dos
    # veces (Python y JS). Sigue siendo una simulación, no el perfil fiscal de nadie.
    assert datos["tasaNra"] == pytest.approx(0.30)


# ── `paybackContraejemplo`: por dato, no a mano (Duda 2 del traspaso) ────────────────────

def test_payback_contraejemplo_elige_el_de_mayor_pb_entre_los_negativos_sintetico():
    """Reconciliación independiente de `_payback_contraejemplo` con datos sintéticos —
    no depende de que el mercado de hoy tenga un ticker en rojo. Dos negativos: el de
    mayor payback bruto gana, aunque no sea el que perdió más (perder mucho no es lo
    mismo que haber cobrado mucho de vuelta antes de perder)."""
    ratios = [
        {"t": "AAA", "pb": 1.10, "ret": -5.0},
        {"t": "BBB", "pb": 3.50, "ret": -1.0},   # mayor pb entre los negativos
        {"t": "CCC", "pb": 9.00, "ret": 40.0},   # positivo, no cuenta
    ]
    assert _payback_contraejemplo(ratios) == "BBB"


def test_payback_contraejemplo_es_none_si_nadie_perdio_capital_sintetico():
    """Duda 2 del traspaso, forzada con datos sintéticos: si en una corrida ningún
    ticker tiene retorno negativo, la función no puede inventar un contraejemplo — el
    panel tiene que poder decir, sin mentir, que esta semana no hay uno."""
    ratios = [
        {"t": "AAA", "pb": 1.10, "ret": 5.0},
        {"t": "BBB", "pb": 3.50, "ret": 12.0},
    ]
    assert _payback_contraejemplo(ratios) is None

def test_la_leyenda_por_modo_vive_en_el_modal_y_no_suelta_en_la_vista():
    """`#tmModoCap` se mudó a `#mMetodoEscenario` dentro de `#modal-tmmetodo` para
    liberar ~60px verticales. Si alguien reintroduce el <p> suelto vuelve el bloque de
    4 renglones que Daniel pidió compactar; y si `aplicarModo` sigue escribiendo en el
    id viejo, la leyenda queda muda: `setHtml` sobre un id inexistente no lanza."""
    cuerpo = open(_COMPONENTE, encoding="utf-8").read()
    assert 'id="tmModoCap"' not in cuerpo
    assert 'setHtml("tmModoCap"' not in cuerpo
    assert 'id="mMetodoEscenario"' in cuerpo
    assert 'setHtml("mMetodoEscenario", MODO_CAP[modo])' in cuerpo


def test_el_modal_del_metodo_engancha_todos_sus_disparadores():
    """Hay dos disparadores del modal: el ⓘ del título «Método tradicional» y el ⓘ
    suelto al final de la fila de filtros. Con `querySelector` en singular el segundo
    queda como adorno muerto: se ve y no abre nada. No lanza, no ensucia la consola —
    solo no funciona. Y ese ⓘ es la ÚNICA afordancia de la fila desde que se quitaron
    las etiquetas «Reinversión» y «Base fiscal», así que si muere, la explicación de
    los tres escenarios fiscales queda sin puerta de entrada junto al control.

    Se cuentan ETIQUETAS HTML con el atributo (regex sobre `<tag ... data-tip=...>`),
    no la substring pelada: las reglas CSS `.he-lab[data-tip="tm-metodo"]` (base y
    ::after) también la contienen. Contar la substring cerrando en `">` funcionaría
    hoy pero se rompe en cuanto alguien reordene los atributos del botón."""
    cuerpo = open(_COMPONENTE, encoding="utf-8").read()
    etiquetas = re.findall(r'<[a-zA-Z]+[^<>]*\bdata-tip="tm-metodo"[^<>]*>', cuerpo)
    assert len(etiquetas) == 2, f"esperaba 2 disparadores HTML, hay {len(etiquetas)}: {etiquetas}"
    assert "querySelectorAll('[data-tip=\"tm-metodo\"]')" in cuerpo


def test_el_info_de_la_fila_de_filtros_es_alcanzable_por_teclado():
    """El ⓘ de la fila reemplazó a la etiqueta «Base fiscal» como único acceso a la
    explicación de los modos. Si vuelve a ser un <span> con `::after` (el patrón del
    resto de la vista, donde el ⓘ acompaña a un texto que ya se lee), deja de recibir
    foco y de anunciarse: un icono sin nombre accesible y sin tabulación."""
    cuerpo = open(_COMPONENTE, encoding="utf-8").read()
    boton = re.search(r'<button[^<>]*\bclass="cmp-info"[^<>]*>', cuerpo)
    assert boton, "el ⓘ de la fila de filtros debe ser un <button class=\"cmp-info\">"
    assert 'aria-label=' in boton.group(0), "sin aria-label el ⓘ no tiene nombre accesible"
    assert 'data-tip="tm-metodo"' in boton.group(0)
