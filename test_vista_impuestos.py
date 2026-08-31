"""Vista «Impuestos» · la escalera de cartera (Fase 2 de la vista fiscal).

`ui.adapters.impuestos_data` NO calcula fiscalidad: lee objetos que ya existen
(`build_tax_summaries`, `build_withholding_diagnosis`, `diagnose_broker_refund_from_forms`)
y los reordena en cuatro peldaños. Estos tests son cruzados o de propiedad — ninguno se
satisface reimplementando la fórmula que generó el dato.

Guardas:
  1. Regla 3b — el bruto del peldaño 1 para un ticker es IDÉNTICO al `BRUTO` que ya
     publican `cashflow_data` y `hoja_data` para ese mismo ticker sobre el mismo fixture.
     Una suite donde cada vista se verifica contra sí misma puede estar verde con dos
     pantallas contradiciéndose (ya pasó en este repo, $98K).
  2. Los tres buckets suman EXACTO lo retenido, sobre fixtures reales de los dos brokers.
  3. Sin país declarado, el peldaño 3 sale `None` (no `0.0`) y no hay devolución estimada.
  4. Caso de regresión con la aritmética fiscal conocida: ROC 100 % ⇒ retención correcta
     $0 y todo lo retenido es recuperable; ROC 0 % a la tasa aplicada ⇒ nada recuperable.
"""
import io
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(__file__))
import logic  # noqa: E402
from ui.adapters import cashflow_data, hoja_data, impuestos_data  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))


class _FakeFile:
    def __init__(self, content: bytes, name: str):
        self._buf = io.BytesIO(content)
        self.name = name

    def read(self):
        return self._buf.read()

    def seek(self, n):
        self._buf.seek(n)


_MKT_MOCK = lambda t, d: (
    pd.DataFrame({"Close": [20.0], "Dividends": [0.0], "Stock Splits": [0.0]},
                 index=pd.to_datetime(["2026-01-01"])), None)


def _resultados_de_fixture(monkeypatch, fixture: str, version: str):
    ruta = os.path.join(BASE, "fixtures", fixture, "synthetic_transactions.csv")
    if not os.path.exists(ruta):
        pytest.skip(f"falta el fixture {fixture}")
    with open(ruta, "rb") as f:
        df, _broker = logic.load_and_detect_csv(_FakeFile(f.read(), f"{fixture}.csv"))
    dfc = logic.normalize_csv(df)
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    return logic.analyze_portfolio(dfc, version=version), dfc


# ── 1. Regla 3b — dos vistas del mismo número, comparadas entre sí ──────────────────────

@pytest.mark.parametrize("fixture", ["schwab_synth_1", "ib_synth_1"])
def test_peldano1_bruto_coincide_con_cashflow_y_hoja(monkeypatch, fixture):
    res, dfc = _resultados_de_fixture(monkeypatch, fixture, f"IMP_XVIEW_{fixture}")
    perfil = logic.build_fiscal_profile("México")
    datos = impuestos_data(res, perfil, [])
    assert datos and datos["fondos"]

    for fondo in datos["fondos"]:
        tk = fondo["ticker"]
        cf = cashflow_data(res[tk], tk)
        hj = hoja_data(res[tk], tk, dfc)
        assert fondo["bruto"] == pytest.approx(cf["BRUTO"], abs=0.01), (
            f"{tk}: peldaño 1 ({fondo['bruto']}) ≠ cashflow BRUTO ({cf['BRUTO']})")
        assert fondo["bruto"] == pytest.approx(hj["BRUTO"], abs=0.01), (
            f"{tk}: peldaño 1 ({fondo['bruto']}) ≠ hoja BRUTO ({hj['BRUTO']})")

    # y el total del peldaño 1 es la suma de los BRUTO de cashflow, no una cuenta propia
    suma_cf = sum(cashflow_data(res[f["ticker"]], f["ticker"])["BRUTO"]
                  for f in datos["fondos"])
    assert datos["peldanos"]["bruto"]["monto"] == pytest.approx(suma_cf, abs=0.02)


# ── 2. Los tres buckets suman exacto lo retenido AL COBRO ──────────────────────────────
#
# ⚠️ TAUTOLÓGICO — no cuenta como cobertura del bucket gris. `retencion_correcta` SE DEFINE
# como `retenido_al_cobro − recuperable_roc − gap_w8ben`, así que esta suma pasa con
# cualquier entrada (medido: pasa con refund_roc=$1000 y gap=−$500). Además, en estos tres
# fixtures las 17 filas de impuesto son NEGATIVAS — no hay un solo reembolso —, así que
# `withheld_at_payment == withheld_tax_total` y el residuo nunca puede salir negativo. La
# cobertura real del momento mezclado está en `test_bucket_gris_no_negativo_con_reembolso`.

@pytest.mark.parametrize("fixture", ["schwab_synth_1", "ib_synth_1"])
def test_tres_buckets_suman_lo_retenido_al_cobro_TAUTOLOGICO(monkeypatch, fixture):
    res, _dfc = _resultados_de_fixture(monkeypatch, fixture, f"IMP_BUCKETS_{fixture}")
    perfil = logic.build_fiscal_profile("México")
    datos = impuestos_data(res, perfil, [])

    for fondo in datos["fondos"]:
        suma = (fondo["retencion_correcta"] + fondo["recuperable_roc"]
                + fondo["gap_w8ben"])
        assert suma == pytest.approx(fondo["retenido"], abs=0.02), (
            f"{fondo['ticker']}: buckets suman {suma:.2f}, retenido al cobro {fondo['retenido']:.2f}")
        # sin reembolsos en el fixture: al cobro == neteado
        wtt = float(res[fondo["ticker"]].get("withheld_tax_total") or 0.0)
        assert fondo["retenido"] == pytest.approx(wtt, abs=0.01)
        assert fondo["ya_devuelto"] == pytest.approx(0.0, abs=0.01)

    R = datos["peldanos"]["retenido"]
    assert R["estado"] == "ok"
    total_buckets = (R["correcta"]["monto"] + R["recuperable_roc"]["monto"]
                     + R["gap_w8ben"]["monto"])
    assert total_buckets == pytest.approx(R["monto"], abs=0.03)


def test_bucket_gris_no_negativo_con_reembolso():
    """LA COBERTURA REAL. Cuando el bróker YA devolvió la porción ROC (reembolso automático
    de IB), `withheld_tax_total` netea ese crédito pero `withheld_at_payment` no. Restar el
    residuo contra el neteado daba un bucket gris de −$61 (Regla 2 rota: momentos mezclados).

    Repro de la auditoría: MSTY reparte $350, le retienen $105 al cobro, el bróker devuelve
    $75 en agosto. ROC 60 %, residencia México (10 %). Al cobro: correcta $14, ROC $63,
    W-8BEN $28 (suman $105); el $75 devuelto va APARTE.
    """
    hist = pd.DataFrame({
        "Date": pd.to_datetime(["2025-02-10", "2025-02-10", "2025-08-15"]),
        "Action": ["Cash Dividend", "NRA Tax Adj", "NRA Tax Adj"],
        "Amount": [350.0, -105.0, 75.0],
    })
    stats = {
        "pocket_investment": 1000.0, "market_value": 900.0,
        "dividends_collected_drip": 0.0, "dividends_collected_cash": 350.0,
        "total_dividends": 245.0,
        "dividends_gross_total": 350.0, "dividends_net_total": 245.0,
        "dividends_gross_by_year": {2025: 350.0}, "withheld_by_year": {2025: 30.0},
        "tax_refund_observed_by_year": {2025: 75.0},
        "withheld_tax_total": 30.0,        # NETEADO: 105 − 75
        "roc_percent": 60.0, "roc_source": "19a",
        "history": hist,
    }
    datos = impuestos_data({"MSTY": stats}, logic.build_fiscal_profile("México"), [])
    f = datos["fondos"][0]

    assert f["retenido"] == pytest.approx(105.0, abs=0.01), "peldaño 4 = retenido AL COBRO"
    assert f["ya_devuelto"] == pytest.approx(75.0, abs=0.01)
    assert f["retencion_correcta"] is not None and f["retencion_correcta"] >= 0.0
    assert f["retencion_correcta"] == pytest.approx(14.0, abs=0.5)
    assert f["recuperable_roc"] + f["gap_w8ben"] <= f["retenido"] + 0.01
    assert (f["retencion_correcta"] + f["recuperable_roc"] + f["gap_w8ben"]
            == pytest.approx(105.0, abs=0.02))

    R = datos["peldanos"]["retenido"]
    assert R["monto"] == pytest.approx(105.0, abs=0.02)      # al cobro, no los 30 neteados
    assert R["ya_devuelto"]["monto"] == pytest.approx(75.0, abs=0.02)
    assert R["estado"] == "ok"


def test_ib_split_reversal_no_reconcilia_desglose_parcial():
    """IB: la fila positiva 'Dividend - Foreign Tax Withholding' es un reverso del split
    inverso, no un reembolso ROC — `logic.py` la netea pero NO la expone como reembolso, así
    que `withheld_at_payment` ($100) queda INFLADO frente a lo económico ($30). No reconcilia
    → el peldaño 4 usa la cifra económica y NO publica el desglose de ese fondo.
    """
    hist = pd.DataFrame({
        "Date": pd.to_datetime(["2025-02-10", "2025-02-10", "2025-12-20"]),
        "Action": ["Cash Dividend",
                   "Dividend - Foreign Tax Withholding",
                   "Dividend - Foreign Tax Withholding"],
        "Amount": [350.0, -100.0, 70.0],       # reverso +70 (mecánica de split, no ROC)
    })
    stats = {
        "pocket_investment": 1000.0, "market_value": 900.0,
        "dividends_collected_drip": 0.0, "dividends_collected_cash": 250.0,
        "total_dividends": 250.0, "dividends_gross_total": 350.0,
        "dividends_net_total": 250.0, "dividends_gross_by_year": {2025: 350.0},
        "withheld_by_year": {2025: 30.0},
        "withheld_tax_total": 30.0, "roc_percent": None, "roc_source": None,
        "history": hist,
    }
    datos = impuestos_data({"CONY": stats}, logic.build_fiscal_profile("México"), [])
    f = datos["fondos"][0]

    assert f["indeterminado"] is True
    assert f["retenido"] == pytest.approx(30.0, abs=0.5), "usa lo económico, no los $100 inflados"
    assert f["retencion_correcta"] is None
    assert f["recuperable_roc"] is None and f["gap_w8ben"] is None
    assert f["ya_devuelto"] == pytest.approx(0.0, abs=0.01)  # el +70 NO es reembolso

    R = datos["peldanos"]["retenido"]
    assert R["estado"] == "parcial"
    assert "CONY" in R["fondos_sin_desglose"]
    assert R["correcta"] is None and R["recuperable_roc"] is None


def test_residuo_negativo_no_se_publica():
    """Si tras igualar el momento el residuo AÚN sale negativo, no se pinta la cifra
    (`indeterminado`), nunca un negativo ni un cero falso — mismo criterio que la Fase 1.

    Se fuerza monkepatcheando `build_withholding_diagnosis` para que devuelva buckets que
    superan lo retenido al cobro (no es alcanzable por la aritmética real, pero el guard
    tiene que existir por si una fuente cambia)."""
    import unittest.mock as mock

    hist = pd.DataFrame({
        "Date": pd.to_datetime(["2025-02-10", "2025-02-10"]),
        "Action": ["Cash Dividend", "NRA Tax Adj"],
        "Amount": [350.0, -100.0],
    })
    stats = {
        "pocket_investment": 1000.0, "market_value": 900.0,
        "dividends_collected_drip": 0.0, "dividends_collected_cash": 350.0,
        "total_dividends": 250.0, "dividends_gross_total": 350.0,
        "dividends_net_total": 250.0, "dividends_gross_by_year": {2025: 350.0},
        "withheld_by_year": {2025: 100.0}, "tax_refund_observed_by_year": {},
        "withheld_tax_total": 100.0, "roc_percent": 50.0, "roc_source": "19a",
        "history": hist,
    }
    fake = {"withheld_at_payment": 100.0, "refund_roc": 90.0, "gap_w8ben": 40.0,
            "gross": 350.0, "verdict": "tratado_no_aplicado", "label": ""}
    with mock.patch.object(logic, "build_withholding_diagnosis", return_value=fake):
        datos = impuestos_data({"MSTY": stats}, logic.build_fiscal_profile("México"), [])

    f = datos["fondos"][0]
    assert f["indeterminado"] is True
    assert f["retencion_correcta"] is None
    assert datos["peldanos"]["retenido"]["estado"] == "parcial"
    assert datos["peldanos"]["retenido"]["correcta"] is None


# ── 3. Sin país declarado no hay cifra en el peldaño 3 ─────────────────────────────────

def test_sin_pais_declarado_peldano3_es_none(monkeypatch):
    res, _dfc = _resultados_de_fixture(monkeypatch, "schwab_synth_1", "IMP_UNDECL")
    datos = impuestos_data(res, logic.build_fiscal_profile(), [])

    assert datos["declarado"] is False
    assert datos["peldanos"]["corresponde"] is None
    assert datos["peldanos"]["retenido"]["estado"] == "sin_pais"
    for fondo in datos["fondos"]:
        assert fondo["corresponde"] is None
        assert fondo["retencion_correcta"] is None
    # Sin país no se publica ninguno de los tres buckets de cartera.
    assert datos["peldanos"]["retenido"]["recuperable_roc"] is None


# ── 4. Regresión — la aritmética fiscal conocida de un 1042-S real ─────────────────────

def _stats_sinteticos(ticker, gross, withheld, roc_pct, roc_source):
    """Un `stats` mínimo pero completo para `impuestos_data`: el `history` sintético hace
    que `build_withholding_diagnosis` mida una tasa aplicada real (retenido / bruto)."""
    hist = pd.DataFrame({
        "Date": pd.to_datetime(["2025-06-15", "2025-06-15"]),
        "Action": ["Cash Dividend", "NRA Tax Adj"],
        "Amount": [gross, -withheld],
    })
    return {
        "pocket_investment": 1000.0, "market_value": 900.0,
        "dividends_collected_drip": 0.0, "dividends_collected_cash": gross,
        "total_dividends": round(gross - withheld, 2),
        "dividends_gross_total": gross, "dividends_net_total": round(gross - withheld, 2),
        "dividends_gross_by_year": {2025: gross}, "withheld_by_year": {2025: withheld},
        "withheld_tax_total": withheld,
        "roc_percent": roc_pct, "roc_source": roc_source,
        "history": hist,
    }


def test_regresion_roc_100_todo_recuperable_y_roc_0_nada():
    """Números con la forma del 1042-S 2025 de Daniel: MSTY 100 % ROC ⇒ la retención
    ($82.81) es toda recuperable y la «correcta» es $0; SCHB 0 % ROC retenido a la tasa
    aplicada ⇒ recuperable $0.

    NOTA: sobre el CSV de transacciones real (`real_examples/charles_schwab_data/
    daniel_zambrano`) el pipeline estima MSTY con ROC 72.9 % vía avisos 19(a), no 100 %
    del cierre fiscal — la precedencia cierre-fiscal > 19(a) (Regla 4b) vive en `logic.py`
    y queda fuera del alcance de esta fase. Este test fija la aritmética de los buckets,
    que es lo que `impuestos_data` sí decide.
    """
    res = {
        "MSTY": _stats_sinteticos("MSTY", 275.97, 82.81, 100.0, "ici"),
        "SCHB": _stats_sinteticos("SCHB", 13.81, 4.14, 0.0, "19a"),
    }
    perfil = logic.build_fiscal_profile("Colombia")  # 30 %, sin tratado
    datos = impuestos_data(res, perfil, [])
    fondos = {f["ticker"]: f for f in datos["fondos"]}

    assert fondos["MSTY"]["retenido"] == pytest.approx(82.81, abs=0.01)
    assert fondos["MSTY"]["retencion_correcta"] == pytest.approx(0.0, abs=0.05)
    assert fondos["MSTY"]["recuperable_roc"] == pytest.approx(82.81, abs=0.05)

    assert fondos["SCHB"]["retenido"] == pytest.approx(4.14, abs=0.01)
    assert fondos["SCHB"]["recuperable_roc"] == pytest.approx(0.0, abs=0.05)

    # y la escalera de cartera suma los dos fondos sin doble conteo
    assert datos["peldanos"]["retenido"]["monto"] == pytest.approx(86.95, abs=0.02)


# ── 5. «Foreign Tax Paid» — línea aparte, no un cuarto bucket ──────────────────────────

def test_foreign_tax_paid_linea_aparte_no_cuarto_bucket(monkeypatch):
    """`schwab_synth_1` SCHB tiene `Foreign Tax Paid` -$0.08. `impuestos_data` lo expone en
    `peldanos.retenido.impuesto_extranjero` — una línea aparte —, NUNCA como un cuarto
    elemento de la partición de la retención NRA (los tres buckets siguen sumando exacto lo
    retenido, sin el impuesto extranjero dentro)."""
    res, _ = _resultados_de_fixture(monkeypatch, "schwab_synth_1", "IMP_FTP")
    datos = impuestos_data(res, logic.build_fiscal_profile("Colombia"), [])
    R = datos["peldanos"]["retenido"]

    assert R["impuesto_extranjero"] is not None
    assert R["impuesto_extranjero"]["monto"] == pytest.approx(0.08, abs=0.01)

    # sigue siendo la partición de la retención NRA: los tres buckets, sin el FTP dentro
    if R["estado"] == "ok":
        suma = (R["correcta"]["monto"] + R["recuperable_roc"]["monto"]
                + R["gap_w8ben"]["monto"])
        assert suma == pytest.approx(R["monto"], abs=0.02)
        assert suma == pytest.approx(R["monto"])  # el FTP no infla el monto retenido

    # y el fondo SCHB lleva su propio importe
    fondos = {f["ticker"]: f for f in datos["fondos"]}
    assert fondos["SCHB"]["impuesto_extranjero"] == pytest.approx(0.08, abs=0.01)


def test_sin_foreign_tax_paid_no_hay_linea(monkeypatch):
    """`ib_synth_1` no tiene ninguna fila `Foreign Tax Paid` → la línea no aparece (None)."""
    res, _ = _resultados_de_fixture(monkeypatch, "ib_synth_1", "IMP_NO_FTP")
    datos = impuestos_data(res, logic.build_fiscal_profile("Colombia"), [])
    assert datos["peldanos"]["retenido"]["impuesto_extranjero"] is None


# ── 6. Peldaño 2 (gravable) — el % de ROC no depende del país ni de la retención ───────

def test_peldano2_descuenta_roc_sin_pais_declarado():
    """El bug de `?demo=ib`: sin país declarado el peldaño 2 mostraba el 100 % del bruto
    como gravable aunque el motor SÍ tenía el % de ROC. Ahora descuenta."""
    res = {"MSTY": _stats_sinteticos("MSTY", 1000.0, 100.0, 60.0, "19a")}
    datos = impuestos_data(res, logic.build_fiscal_profile(), [])   # sin país
    f = {x["ticker"]: x for x in datos["fondos"]}["MSTY"]
    assert f["roc_pct"] == pytest.approx(60.0, abs=0.01)
    assert f["gravable"] == pytest.approx(400.0, abs=0.02)          # 1000 × (1 − 0.60)
    assert datos["peldanos"]["gravable"]["monto"] == pytest.approx(400.0, abs=0.02)
    assert datos["peldanos"]["gravable"]["sin_roc"] == []


def test_peldano2_descuenta_roc_sin_retencion_nra_con_pais():
    """El camino que nadie había contado, el de `?demo=schwab`: retención NRA $0 en todos
    los fondos y país declarado — el peldaño 2 igual descuenta el ROC."""
    res = {"MSTY": _stats_sinteticos("MSTY", 1000.0, 0.0, 60.0, "19a")}
    datos = impuestos_data(res, logic.build_fiscal_profile("Colombia"), [])
    f = {x["ticker"]: x for x in datos["fondos"]}["MSTY"]
    assert f["roc_pct"] == pytest.approx(60.0, abs=0.01)
    assert f["gravable"] == pytest.approx(400.0, abs=0.02)


def test_peldano2_roc_negativo_no_descuenta_y_se_declara():
    """`roc_percent` negativo (método 'broker' que no cuadra) ⇒ la fila figura «sin dato»
    (`roc_pct` None) y tributa sobre el bruto completo; el peldaño lo declara en `sin_roc`."""
    res = {
        "PLTY": _stats_sinteticos("PLTY", 130.95, 39.21, -0.78, "broker"),
        "SMH": _stats_sinteticos("SMH", 13.13, 3.94, -65.29, "broker"),
        "CONY": _stats_sinteticos("CONY", 3162.65, 202.98, 61.24, "19a"),
    }
    datos = impuestos_data(res, logic.build_fiscal_profile("Colombia"), [])
    f = {x["ticker"]: x for x in datos["fondos"]}
    for tk in ("PLTY", "SMH"):
        assert f[tk]["roc_pct"] is None, tk
        assert f[tk]["roc_fuente"] is None, tk
        assert f[tk]["gravable"] == pytest.approx(f[tk]["bruto"], abs=0.01), tk
    assert f["CONY"]["roc_pct"] == pytest.approx(61.24, abs=0.01)
    g = datos["peldanos"]["gravable"]
    assert set(g["sin_roc"]) == {"PLTY", "SMH"}
    assert g["cubiertos"] == 1 and g["total"] == 3


def test_peldano2_roc_cero_medido_es_dato():
    """`roc_percent == 0.0` (cero MEDIDO, no ausencia) ⇒ `roc_pct` 0.0, fuera de `sin_roc`,
    gravable == bruto (0 % no reduce nada, pero por resultado, no por falta de dato)."""
    res = {"SMH": _stats_sinteticos("SMH", 100.0, 10.0, 0.0, "broker")}
    datos = impuestos_data(res, logic.build_fiscal_profile("Colombia"), [])
    f = {x["ticker"]: x for x in datos["fondos"]}["SMH"]
    assert f["roc_pct"] == 0.0
    assert f["roc_fuente"] == "broker"
    assert datos["peldanos"]["gravable"]["sin_roc"] == []
    assert datos["peldanos"]["gravable"]["cubiertos"] == 1


# ── 7. Cruce contra los demos reales (patrón del #99) ──────────────────────────────────
#
# El bruto NO depende del ROC → se pinea exacto. El gravable y `sin_roc` SÍ dependen de
# `roc_percent`, que para PLTY/QYLD/SVOL (sin parquet en `knowledge/price_cache/`, precio
# de yfinance en vivo) queda a centímetros del umbral `_prefer_19a_roc` (borde documentado
# en CLAUDE.md: PLTY a $0.72). Por eso solo `schwab2` —cuyos tres fondos tienen parquet y
# ROC estable— se pinea al céntimo; para `ib`/`schwab` se asertan las propiedades
# ESTRUCTURALES (Regla 6: un invariante no es un hecho de mercado).

def _impuestos_demo(alias):
    import demo_mode
    if not demo_mode.demo_available():
        pytest.skip("real_examples/ no montado")
    bundle = demo_mode.load_demo_case(alias)
    assert bundle is not None
    return impuestos_data(bundle["_results"], logic.build_fiscal_profile(), [])


def test_cruce_peldano2_schwab2_exacto():
    """`?demo=schwab2`: MSTY (19a 74.18 %) + SCHB/XLK sin dato. Determinista."""
    datos = _impuestos_demo("schwab2")
    g = datos["peldanos"]["gravable"]
    assert datos["peldanos"]["bruto"]["monto"] == pytest.approx(385.78, abs=0.02)
    assert g["monto"] == pytest.approx(126.02, abs=0.05)
    assert set(g["sin_roc"]) == {"SCHB", "XLK"}
    assert (g["cubiertos"], g["total"]) == (1, 3)


@pytest.mark.parametrize("alias,bruto_esp,sin_roc_min", [
    ("ib", 18319.69, {"SCHB", "SMH", "XLK"}),
    ("schwab", 5827.18, {"SCHB", "XLK"}),
])
def test_cruce_peldano2_estructural(alias, bruto_esp, sin_roc_min):
    datos = _impuestos_demo(alias)
    fondos = datos["fondos"]
    g = datos["peldanos"]["gravable"]

    assert datos["peldanos"]["bruto"]["monto"] == pytest.approx(bruto_esp, abs=0.02)
    # los ETF de índice con roc_percent sólidamente negativo/None SIEMPRE quedan sin dato
    assert sin_roc_min <= set(g["sin_roc"])
    # invariante por fila: sin dato ⇒ gravable == bruto; con dato ⇒ bruto × (1 − ROC/100)
    for f in fondos:
        if f["roc_pct"] is None:
            assert f["gravable"] == pytest.approx(f["bruto"], abs=0.01), f["ticker"]
        else:
            esperado = f["bruto"] * (1 - f["roc_pct"] / 100.0)
            assert f["gravable"] == pytest.approx(esperado, abs=0.02), f["ticker"]
    # el peldaño reconcilia con la suma por fondo y con la cobertura declarada
    assert g["monto"] == pytest.approx(sum(f["gravable"] for f in fondos), abs=0.05)
    assert g["cubiertos"] == len(fondos) - len(g["sin_roc"])
    assert g["total"] == len(fondos)
    # al menos un fondo con 19a descuenta de verdad (gravable < bruto de cartera)
    assert g["monto"] < datos["peldanos"]["bruto"]["monto"] - 1.0
