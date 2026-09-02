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


# ── 8. La casilla 9 (ROC recuperable) se publica y NO depende del país ─────────────────
#
# `ruta_a.casilla9_esperada` es «lo que la casilla 9 del 1042-S DEBERÍA decir si el bróker
# ya reclasificó el ROC». Su fórmula usa la tasa OBSERVADA en el CSV y el escudo del ROC
# 19a — `entitled` (dato de tratado) no aparece —, así que es invariante al país. Antes,
# sin país declarado, `build_withholding_diagnosis` cortaba en 'sin_declarar' y devolvía
# `refund_roc: 0.0` sin calcularlo nunca: la app AFIRMABA un cero que no midió.

def test_casilla9_no_depende_del_pais(monkeypatch):
    """Con withheld=$100 y ROC 60 % la casilla 9 es $60.00 (100 × 0.60), idéntica sin país
    y con Colombia / México / España. El primer caso —sin país— daba $0.00 antes del fix."""
    res = {"MSTY": _stats_sinteticos("MSTY", 1000.0, 100.0, 60.0, "19a")}
    perfiles = {
        "sin_pais": logic.build_fiscal_profile(),
        "Colombia": logic.build_fiscal_profile("Colombia"),   # 30 %
        "México": logic.build_fiscal_profile("México"),       # 10 %
        "España": logic.build_fiscal_profile("España"),        # 15 %
    }
    valores = {
        nombre: impuestos_data(res, perfil, [])["ruta_a"]["casilla9_esperada"]
        for nombre, perfil in perfiles.items()
    }
    for nombre, v in valores.items():
        assert v == pytest.approx(60.0, abs=0.05), f"{nombre}: {v}"


def test_peldano4_no_amplia_su_alcance_sin_pais():
    """Publicar la casilla 9 sin país NO amplía el peldaño 4: sin residencia sigue en
    'sin_pais', sin los tres buckets de cartera. «No puedo separar los tres buckets» y
    «esta parte vuelve sola» son compatibles (decisión 3 del traspaso 2026-09-01)."""
    res = {"MSTY": _stats_sinteticos("MSTY", 1000.0, 100.0, 60.0, "19a")}
    R = impuestos_data(res, logic.build_fiscal_profile(), [])["peldanos"]["retenido"]

    assert R["estado"] == "sin_pais"
    assert R["recuperable_roc"] is None
    assert R["correcta"] is None
    assert R["gap_w8ben"] is None


def test_casilla9_respeta_el_guard_implausible(monkeypatch):
    """Una tasa aplicada > 30 % (retención inflada, p. ej. reversos de split de IB mal
    contados) hace que `_roc_refund_recuperable` no toque nada — con y sin país. Sin este
    guard el fix reabriría el #92 (casilla 9 inflada para clientes de IB)."""
    res = {"XXXX": _stats_sinteticos("XXXX", 100.0, 50.0, 60.0, "19a")}  # 50 % aplicada
    assert logic.applied_withholding_rate(res["XXXX"])["implausible"] is True

    for perfil in (logic.build_fiscal_profile(), logic.build_fiscal_profile("Colombia")):
        datos = impuestos_data(res, perfil, [])
        assert datos["ruta_a"]["casilla9_esperada"] == pytest.approx(0.0, abs=0.005)


@pytest.mark.parametrize("alias,casilla9_esp", [
    ("schwab_1", 0.00),
    ("schwab_2", 77.95),
    ("schwab_daniel", 81.22),
    # ACTUALIZADO 2026-09-02 (tolerancia del umbral del ROC): 1314.14 -> 1340.21. La
    # diferencia son los $26.07 de PLTY, que con captura caía a la ruta 'broker' por 72
    # centavos y quedaba «sin dato». Ese 1314.14 NO era la cifra buena: era la del cliente
    # que subía la foto del bróker, mientras el que no la subía veía 1340.21. El nuevo
    # valor es el de AMBAS rutas — ver `test_casilla9_converge_con_y_sin_captura`.
    ("ib_1", 1340.21),
])
def test_casilla9_no_regresion_con_pais(alias, casilla9_esp):
    """No-regresión: los 4 casos reales con Colombia declarada dan la misma casilla 9 que
    antes del fix — el cambio solo libera el carril del ROC sin país, no toca el camino con
    residencia."""
    import demo_mode
    if not demo_mode.demo_available():
        pytest.skip("real_examples/ no montado")
    bundle = demo_mode.load_demo_case(alias)
    assert bundle is not None, alias
    datos = impuestos_data(bundle["_results"], logic.build_fiscal_profile("Colombia"), [])
    assert datos["ruta_a"]["casilla9_esperada"] == pytest.approx(casilla9_esp, abs=0.05)


# ── 5. La segunda vía para declarar el país: la casilla 13b del 1042-S ─────────────────
# Hasta 2026-09-02 los CTA de la escalera solo nombraban el «Paso 2» y callaban que el
# 1042-S ya trae la residencia (casilla 13b). El cliente que subió el formulario tenía el
# dato delante sin saberlo. El adapter lo PUBLICA para el CTA; no declara nada — la
# residencia se sigue confirmando a mano en `ui/carga._render_residencia_detectada`.

def _res_min():
    return {"MSTY": _stats_sinteticos("MSTY", 100.0, 30.0, 50.0, "19a")}


def test_residencia_1042s_codigo_traducible_se_publica():
    """Código en la tabla: el CTA puede ofrecer el clic de confirmación."""
    datos = impuestos_data(_res_min(), logic.build_fiscal_profile(), [], "MX")
    assert datos["residencia_1042s"] == {"codigo": "MX", "pais_detectado": "México"}


def test_residencia_1042s_codigo_desconocido_no_inventa_pais():
    """Código fuera de la tabla: se conserva el código y el país queda en None — el CTA
    manda a elegirlo a mano en vez de prometer un atajo que no existe."""
    datos = impuestos_data(_res_min(), logic.build_fiscal_profile(), [], "ZZ")
    assert datos["residencia_1042s"]["codigo"] == "ZZ"
    assert datos["residencia_1042s"]["pais_detectado"] is None


def test_residencia_1042s_sin_formulario_queda_vacia():
    """Sin 1042-S (y con la firma vieja de 3 argumentos) no se publica residencia alguna."""
    for datos in (impuestos_data(_res_min(), logic.build_fiscal_profile(), []),
                  impuestos_data(_res_min(), logic.build_fiscal_profile(), [], None)):
        assert datos["residencia_1042s"] == {"codigo": None, "pais_detectado": None}


def test_residencia_1042s_normaliza_el_codigo():
    """El código llega del extractor: minúsculas o con espacios no deben perder el país."""
    datos = impuestos_data(_res_min(), logic.build_fiscal_profile(), [], " mx ")
    assert datos["residencia_1042s"]["pais_detectado"] == "México"


def test_residencia_1042s_no_declara_el_pais_por_su_cuenta():
    """LA INVARIANTE. Publicar la casilla 13b NO puede mover el peldaño 3: sin que el
    cliente confirme, la escalera sigue sin residencia declarada y sin cifra."""
    datos = impuestos_data(_res_min(), logic.build_fiscal_profile(), [], "MX")
    assert datos["declarado"] is False
    assert datos["pais"] is None
    assert datos["peldanos"]["corresponde"] is None


# ── 6. Peldaño 6 (Fase 4) — qué declaras en tu país ───────────────────────────────────
# Publica BASE y CRÉDITO, nunca una cifra de impuesto local: la tarifa del país de
# residencia es progresiva sobre la renta GLOBAL del contribuyente, que la app no conoce.

def _datos_f4(fixture, monkeypatch, pais=None):
    res, _ = _resultados_de_fixture(monkeypatch, fixture, f"F4_{fixture}")
    perfil = logic.build_fiscal_profile(pais) if pais else logic.build_fiscal_profile()
    return impuestos_data(res, perfil, [])


@pytest.mark.parametrize("fixture", ["schwab_synth_2", "ib_synth_1"])
def test_f4_base_y_credito_reconcilian_con_los_peldanos(monkeypatch, fixture):
    """REGLA 5 — dos vistas del mismo número. El peldaño 6 no recalcula nada: sus tres
    cifras tienen que ser IDÉNTICAS a los peldaños 1, 2 y 4, que las producen."""
    d = _datos_f4(fixture, monkeypatch)
    L, P = d["impuesto_local"], d["peldanos"]
    assert L["dividendos"]["bruto"] == P["bruto"]["monto"]
    assert L["dividendos"]["gravable_eeuu"] == P["gravable"]["monto"]
    assert L["credito_eeuu"]["monto"] == P["retenido"]["monto"]
    assert L["dividendos"]["roc"] == pytest.approx(
        round(P["bruto"]["monto"] - P["gravable"]["monto"], 2), abs=0.01)


@pytest.mark.parametrize("fixture", ["schwab_synth_2", "ib_synth_1"])
def test_f4_tramos_reconcilian_con_ganancias_capital(monkeypatch, fixture):
    """REGLA 5 — el desglose por tramo suma exactamente el realizado del peldaño 5."""
    d = _datos_f4(fixture, monkeypatch)
    tr = d["impuesto_local"]["realizado_por_tramo"]
    suma = round(sum(v["monto"] for v in tr.values()), 2)
    n = sum(v["n_ventas"] for v in tr.values())
    gc = d["ganancias_capital"]
    esperado = (gc.get("realizado") or {}).get("monto", 0.0) if gc else 0.0
    assert suma == pytest.approx(esperado or 0.0, abs=0.01)
    assert n == ((gc.get("realizado") or {}).get("n_ventas", 0) if gc else 0)


def test_f4_nunca_publica_tarifa_ni_total(monkeypatch):
    """LA INVARIANTE DE LA FASE. La app no conoce la renta global del contribuyente, así que
    no puede publicar ni tarifa ni un total de impuesto local — y lo dice, no lo omite."""
    d = _datos_f4("schwab_synth_2", monkeypatch)
    L = d["impuesto_local"]
    assert L["tarifa_pct"] is None
    assert L["total"] is None
    assert L["tarifa_motivo"] == "progresiva_sobre_renta_global_no_declarada"
    assert L["total_motivo"] == "naturalezas_y_momentos_distintos_no_se_suman"
    # Y ninguna clave del objeto contiene una cifra que se lea como «lo que debes».
    assert not any(k.startswith("impuesto_") or k == "debes" for k in L)


def test_f4_no_suma_dividendos_con_ganancias(monkeypatch):
    """REGLA 2 — naturalezas y momentos distintos. Ninguna cifra del objeto puede ser la
    suma de la base de dividendos con la de ganancias realizadas."""
    d = _datos_f4("ib_synth_1", monkeypatch)
    L = d["impuesto_local"]
    tr = L["realizado_por_tramo"]
    prohibido = round(L["dividendos"]["bruto"] + sum(v["monto"] for v in tr.values()), 2)
    planas = [v for v in L.values() if isinstance(v, (int, float))]
    planas += [v2 for v in L.values() if isinstance(v, dict)
               for v2 in v.values() if isinstance(v2, (int, float))]
    assert all(abs(v - prohibido) > 0.01 for v in planas if v not in (0, 0.0)), \
        "hay una cifra que suma dividendos con ganancias de capital"


def test_f4_el_no_realizado_se_nombra_pero_queda_fuera(monkeypatch):
    """Lo latente se declara al vender, no ahora. Se publica APARTE y rotulado como excluido
    — callarlo invitaría a sumarlo a la base."""
    d = _datos_f4("ib_synth_1", monkeypatch)
    L, gc = d["impuesto_local"], d["ganancias_capital"]
    if gc and gc.get("no_realizado"):
        assert L["no_realizado_excluido"] == gc["no_realizado"]["monto"]
        tr = L["realizado_por_tramo"]
        assert all(v["monto"] != L["no_realizado_excluido"] for v in tr.values())


def test_f4_no_depende_del_pais_declarado(monkeypatch):
    """La base declarable y el crédito son los mismos con o sin residencia declarada: no
    dependen del tratado con EE.UU. Declarar el país no puede moverlos."""
    sin = _datos_f4("schwab_synth_2", monkeypatch)["impuesto_local"]
    con = _datos_f4("schwab_synth_2", monkeypatch, pais="México")["impuesto_local"]
    assert sin["dividendos"] == con["dividendos"]
    assert sin["credito_eeuu"] == con["credito_eeuu"]
    assert sin["realizado_por_tramo"] == con["realizado_por_tramo"]


def test_f4_ya_no_queda_slot_proximamente(monkeypatch):
    """La Fase 4 llena el último slot reservado: la lista queda vacía, no con el peldaño
    rotulado «pendiente» debajo del que ya publica la cifra."""
    d = _datos_f4("schwab_synth_2", monkeypatch)
    assert d["slots_pendientes"] == []
    assert d["impuesto_local"] is not None


def test_f4_pinea_el_reparto_por_tramo_no_solo_la_suma(monkeypatch):
    """LA TRAMPA. Los dos tests de reconciliación de arriba comparan la SUMA de los tramos,
    así que pasarían enteros con las ventas clasificadas en el tramo equivocado. Este pinea
    en qué tramo cae: `ib_synth_1` tiene una única venta, y es de menos de 2 años."""
    d = _datos_f4("ib_synth_1", monkeypatch)
    tr = d["impuesto_local"]["realizado_por_tramo"]
    assert tr["lt_2y"]["n_ventas"] == 1
    assert tr["lt_2y"]["monto"] == pytest.approx(-20.0, abs=0.01)
    assert tr["ge_2y"]["n_ventas"] == 0 and tr["ge_2y"]["monto"] == 0.0
    assert tr["sin_tramo"]["n_ventas"] == 0


def test_f4_separa_las_dos_antiguedades_cuando_existen_las_dos():
    """La rama `ge_2y` NO la alcanza ninguna fixture del repo (medido: schwab_synth_2 no
    tiene ventas, ib_synth_1 tiene una sola y es `lt_2y`), así que sin este caso el tramo
    largo viviría sin ejercitar y su verde no diría nada. Se arma a mano, sin tocar los CSV."""
    res = {
        "AAA": {
            "dividends_gross_total": 0.0, "withheld_tax_total": 0.0,
            "history": pd.DataFrame({"Date": [], "Action": [], "Amount": []}),
            "capital_gains": {
                "estado": "ok", "realized_total": 300.0,
                "realized": [
                    {"gain": 500.0, "tramo": "ge_2y", "shares": 10},
                    {"gain": -200.0, "tramo": "lt_2y", "shares": 5},
                ],
                "unrealized": {},
            },
        },
    }
    from ui import adapters
    tr = adapters._impuesto_local_cartera(
        {"bruto": {"monto": 0.0}, "gravable": {"monto": 0.0}, "retenido": {"monto": 0.0}},
        None, res)["realizado_por_tramo"]
    assert tr["ge_2y"] == {"monto": 500.0, "n_ventas": 1}
    assert tr["lt_2y"] == {"monto": -200.0, "n_ventas": 1}
    # Y no se compensan en una sola cifra: +500 y −200 NO se publican como +300.
    assert tr["ge_2y"]["monto"] != 300.0 and tr["lt_2y"]["monto"] != 300.0


# ── 7. El crédito por impuesto pagado a EE.UU. tiene DOS momentos ─────────────────────
# Lo retenido al cobro no es todo acreditable: la parte que vuelve al reclasificar el ROC
# nunca llegó a ser impuesto, y lo que no se pagó no se descuenta en el país de residencia.
# Publicar el total como «crédito» lo infla — medido: $41.29 de $60.75 (68%) en schwab_synth_1.

@pytest.mark.parametrize("fixture", ["schwab_synth_1", "ib_synth_1"])
def test_credito_definitivo_mas_lo_que_vuelve_es_lo_retenido(monkeypatch, fixture):
    """La partición cierra exactamente contra el peldaño 4: nada se pierde ni se duplica."""
    d = _datos_f4(fixture, monkeypatch)
    c = d["impuesto_local"]["credito_eeuu"]
    assert c["monto"] == d["peldanos"]["retenido"]["monto"]
    if c["definitivo"] is not None:
        assert round(c["definitivo"] + c["vuelve_por_roc"], 2) == pytest.approx(
            c["monto"], abs=0.01)


def test_credito_no_cuenta_lo_que_el_broker_devuelve(monkeypatch):
    """GROUND TRUTH de `schwab_synth_1` (el CSV que se subió a producción el 2026-09-02):
    retenido $60.75, de los que la casilla 9 devuelve $41.29 ⇒ crédito real **$19.46**.

    Antes de este arreglo la vista presentaba los $60.75 enteros como «ya pagado a EE.UU.»,
    inflando 3.1× la cifra que el cliente llevaría a su contador."""
    d = _datos_f4("schwab_synth_1", monkeypatch)
    c = d["impuesto_local"]["credito_eeuu"]
    assert c["monto"] == pytest.approx(60.75, abs=0.01)
    assert c["vuelve_por_roc"] == pytest.approx(41.29, abs=0.01)
    assert c["definitivo"] == pytest.approx(19.46, abs=0.01)
    assert c["definitivo"] < c["monto"], "el crédito no puede ser todo lo retenido"


def test_credito_lee_la_casilla9_no_la_recalcula(monkeypatch):
    """REGLA 3 — objeto único. `vuelve_por_roc` es EXACTAMENTE `ruta_a.casilla9_esperada`,
    el objeto que el #102 ya publica (y que funciona sin país declarado)."""
    d = _datos_f4("schwab_synth_1", monkeypatch)
    assert (d["impuesto_local"]["credito_eeuu"]["vuelve_por_roc"]
            == d["ruta_a"]["casilla9_esperada"])


def test_credito_definitivo_es_none_cuando_no_hay_con_que_medirlo():
    """«Medí cero» y «no pude medirlo» no son lo mismo delante de una cifra de dinero. Sin
    `ruta_a`, el definitivo NO se publica como igual al retenido — se declara el motivo."""
    from ui import adapters
    L = adapters._impuesto_local_cartera(
        {"bruto": {"monto": 100.0}, "gravable": {"monto": 100.0}, "retenido": {"monto": 30.0}},
        None, {}, ruta_a=None)
    c = L["credito_eeuu"]
    assert c["monto"] == 30.0
    assert c["definitivo"] is None
    assert c["definitivo_motivo"] == "sin_dato_de_roc_recuperable"


def test_credito_definitivo_no_depende_del_pais(monkeypatch):
    """Lo que el bróker devuelve por ROC no depende del tratado: declarar país no puede
    mover el crédito definitivo (misma lógica que el #101/#102)."""
    sin = _datos_f4("schwab_synth_1", monkeypatch)["impuesto_local"]["credito_eeuu"]
    con = _datos_f4("schwab_synth_1", monkeypatch, pais="México")["impuesto_local"]["credito_eeuu"]
    assert sin["definitivo"] == con["definitivo"]
    assert sin["vuelve_por_roc"] == con["vuelve_por_roc"]


def test_casilla9_converge_con_y_sin_captura():
    """LA PRUEBA DEL ARREGLO, y vale más que el número pineado de arriba.

    Hasta 2026-09-02 la misma cartera daba DOS casillas 9 según el cliente hubiera subido o no
    la captura de posiciones: $1340.21 sin ella, $1314.14 con ella. Los $26.07 de diferencia
    eran PLTY, cuyo costo de bróker ($535.32) superaba lo aportado ($534.60) por **72 centavos**
    — 0.13%, ruido de comisiones. Ese ruido lo mandaba a la ruta 'broker', su ROC salía negativo
    y el fondo quedaba fuera de la cobertura fiscal pese a publicar avisos 19a con un ROC del
    66.48%.

    Subir una foto no puede cambiar cuánto impuesto te devuelven. Este test falla si vuelven a
    divergir, sin depender de que el número siga siendo 1340.21.
    """
    import demo_mode
    if not demo_mode.demo_available():
        pytest.skip("real_examples/ no montado")
    bundle = demo_mode.load_demo_case("ib")          # CON captura: inyecta cost_basis
    con = impuestos_data(bundle["_results"], logic.build_fiscal_profile("Colombia"), [])

    import glob
    import os as _os
    ruta = sorted(glob.glob(_os.path.join(
        "real_examples", "interactive_brokers_data", "*", "*.csv")))
    if not ruta:
        pytest.skip("CSV real de IB no disponible")
    with open(ruta[0], "rb") as fh:
        df, _ = logic.load_and_detect_csv(_FakeFile(fh.read(), "ib.csv"))
    sin = impuestos_data(logic.analyze_portfolio(df, version="TEST_CONV"),
                         logic.build_fiscal_profile("Colombia"), [])

    assert con["ruta_a"]["casilla9_esperada"] == pytest.approx(
        sin["ruta_a"]["casilla9_esperada"], abs=0.05), (
        "la casilla 9 no puede depender de si el cliente subió la captura del bróker")


def test_el_ruido_de_redondeo_no_saca_un_fondo_con_19a_de_la_cobertura():
    """PLTY publica avisos 19a, así que su ROC es medible: no puede quedar «sin dato» porque el
    costo del bróker difiera del aportado en menos que el ruido. El gate `in load_roc_19a()`
    sigue mandando — SCHB, SMH y XLK salen negativos por la misma resta y SIGUEN fuera, porque
    no publican avisos."""
    import demo_mode
    if not demo_mode.demo_available():
        pytest.skip("real_examples/ no montado")
    res = demo_mode.load_demo_case("ib")["_results"]
    plty = res.get("PLTY") or {}
    assert plty.get("roc_source") == "19a"
    assert plty.get("roc_percent", 0) > 0, "PLTY tiene ROC oficial; no puede salir negativo"

    datos = impuestos_data(res, logic.build_fiscal_profile(), [])
    sin_roc = datos["peldanos"]["gravable"]["sin_roc"]
    assert "PLTY" not in sin_roc
    for etf in ("SCHB", "SMH", "XLK"):                 # sin 19a: el gate los deja fuera igual
        if etf in res:
            assert etf in sin_roc, f"{etf} no publica 19a y no debe entrar por la tolerancia"


# ── Los DOS límites de la tolerancia del umbral del ROC ───────────────────────────────
# Añadidos tras ver que los mutantes «tolerancia infinita» y «sin gate de 19a» NO mordían:
# los tests de arriba pasaban por una razón distinta de la que afirmaban (ningún fondo del
# demo tiene el costo del bróker MUY por encima, así que ampliar la tolerancia no se notaba).
# Estos dos construyen justo ese caso.

def _analiza_con_captura(ticker, costo_broker, precio=20.0, monkeypatch=None):
    """Una compra y un dividendo de `ticker`, más una captura que declara `costo_broker`."""
    csv = ("Date,Action,Symbol,Description,Quantity,Price,Fees & Comm,Amount\n"
           f'"01/15/2025","Buy","{ticker}","X","40","$25.00","","-$1000.00"\n'
           f'"03/15/2025","Dividend","{ticker}","X","","","","$100.00"\n')
    df, _ = logic.load_and_detect_csv(_FakeFile(csv.encode(), "c.csv"))
    if monkeypatch is not None:
        monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    return logic.analyze_portfolio(
        logic.normalize_csv(df), version="TEST_TOL",
        position_overrides={ticker: {"shares": 40.0, "cost_basis": costo_broker}})


def test_tolerancia_no_tapa_una_diferencia_grande_de_costo(monkeypatch):
    """LÍMITE SUPERIOR. Si el bróker declara MUCHO más costo del que dice el CSV (aquí +50%),
    eso no es ruido: es una discrepancia real que debe RECONCILIARSE por la rama de al lado,
    no tomar el atajo del 19a. Con una tolerancia desbocada este test cae."""
    res = _analiza_con_captura("MSTY", 1500.0, monkeypatch=monkeypatch)   # CSV dice 1000
    st = res.get("MSTY") or {}
    assert "cost_basis" in (st.get("reconciled_fields") or []), (
        "una diferencia del 50% tiene que reconciliarse, no absorberse como ruido")


def test_el_gate_de_19a_manda_sobre_la_tolerancia(monkeypatch):
    """LÍMITE LATERAL. La tolerancia solo alcanza a fondos que PUBLICAN avisos 19a. Un ETF
    amplio sin avisos (SCHB) no puede tomar la ruta 19a por muy cerca que quede del umbral —
    no hay dato oficial que preferir. Quitar el gate hace caer este test."""
    assert "SCHB" not in logic.load_roc_19a(), "premisa: SCHB no publica 19a"
    res = _analiza_con_captura("SCHB", 999.50, monkeypatch=monkeypatch)   # a 50 centavos
    st = res.get("SCHB") or {}
    assert st.get("roc_source") != "19a", "SCHB no publica avisos: no puede resolver por 19a"


def test_los_etf_sin_19a_conservan_su_roc_medido():
    """El gate `in load_roc_19a()` no es decorativo, aunque la cobertura no lo note.

    Sin él, los ETFs amplios (SCHB, SMH, XLK) toman la ruta 19a, no encuentran aviso que
    aplicar y su `roc_percent` MEDIDO —negativo, por la resta del método bróker— se pierde en
    `None`. Los dos estados acaban «sin dato» en la cobertura, así que ningún test de cobertura
    lo ve; pero el #101 decidió CONSERVAR el valor medido y solo rotularlo en el carril fiscal
    (Regla 4). Perderlo es una regresión silenciosa de esa decisión.
    """
    import demo_mode
    if not demo_mode.demo_available():
        pytest.skip("real_examples/ no montado")
    res = demo_mode.load_demo_case("ib")["_results"]
    for etf in ("SCHB", "SMH", "XLK"):
        st = res.get(etf)
        if not isinstance(st, dict):
            continue
        assert st.get("roc_percent") is not None, (
            f"{etf} perdió su ROC medido: el gate de 19a dejó de proteger la ruta del bróker")
        assert st.get("roc_source") == "broker"
