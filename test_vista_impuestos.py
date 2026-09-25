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
from ui.adapters import (  # noqa: E402
    _bruto_independiente_del_csv, cashflow_data, hoja_data, impuestos_data)

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
        # Ancla EXTERNA (auditoría M4, H2). Las tres vistas leen el mismo
        # `dividends_gross_total`: cuadrar entre ellas no ve un error del objeto compartido
        # —con el bug histórico de Schwab reintroducido (bruto = neto + retenido) este test
        # seguía verde—. `_bruto_independiente_del_csv` relee las filas sin pasar por el
        # predicado ni por la convención que se auditan.
        independiente = _bruto_independiente_del_csv(dfc[dfc["Ticker"] == tk])
        assert fondo["bruto"] == pytest.approx(independiente, abs=0.01), (
            f"{tk}: peldaño 1 ({fondo['bruto']}) ≠ CSV releído independiente ({independiente})")
        assert fondo["bruto"] == pytest.approx(cf["BRUTO"], abs=0.01), (
            f"{tk}: peldaño 1 ({fondo['bruto']}) ≠ cashflow BRUTO ({cf['BRUTO']})")
        # Hoy por construcción: `hoja_data` envuelve `cashflow_data`. Se queda por si alguien
        # la reescribe con su propia cuenta, pero NO cuenta como fuente independiente.
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


def test_impuesto_de_cashflow_es_lo_retenido_al_cobro_menos_lo_devuelto(monkeypatch):
    """Regla 3b con momentos distintos (auditoría M4, H4). La retención aparece en Cash flow
    y Hoja Excel (`IMPUESTO`, NETEADO tras el reembolso) y en Impuestos (`retenido` AL COBRO,
    y `ya_devuelto` aparte). Ningún test las cruzaba con un reembolso presente: los fixtures
    de los otros cruces no traen ninguno.

    Cada cifra se ancla a las filas del CSV. La relación sola
    (`IMPUESTO == retenido − ya_devuelto`) sale casi por construcción —`impuestos_data` ya
    reconcilia `withheld_at_payment` contra el mismo neteado que lee `cashflow_data`—, así
    que lo que muerde son los anclajes.

    Filas: dos cobros de $1,000 con −$300 al cobro cada uno, y +$240 devueltos en feb-2026 al
    reclasificar. Al cobro $600, devuelto $240, neteado $360."""
    df = pd.DataFrame([
        {"Date": pd.Timestamp(d), "Action": a, "Ticker": "MSTY", "Quantity": q, "Amount": amt}
        for d, a, q, amt in [
            ("2025-01-02", "Buy", 100, -2000.0),
            ("2025-03-03", "Cash Dividend", 0, 1000.0),
            ("2025-03-03", "NRA Tax Adj", 0, -300.0),
            ("2025-06-02", "Cash Dividend", 0, 1000.0),
            ("2025-06-02", "NRA Tax Adj", 0, -300.0),
            ("2026-02-16", "NRA Tax Adj", 0, 240.0),    # reembolso de la reclasificación
        ]])
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    # Sin esto, el 19(a) y el cierre fiscal REALES de MSTY entrarían al fixture sintético.
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {})
    monkeypatch.setattr(logic, "load_roc_ici", lambda: {})
    res = logic.analyze_portfolio(df, version="IMP_IMPUESTO_XVIEW_REEMBOLSO")

    datos = impuestos_data(res, logic.build_fiscal_profile("México"), [])
    assert [x["ticker"] for x in datos["fondos"]] == ["MSTY"]
    f = datos["fondos"][0]
    cf = cashflow_data(res["MSTY"], "MSTY")

    assert f["retenido"] == pytest.approx(600.0, abs=0.01), (
        f"Impuestos: retenido AL COBRO {f['retenido']} ≠ 600.00 de las filas")
    assert f["ya_devuelto"] == pytest.approx(240.0, abs=0.01), (
        f"Impuestos: ya devuelto {f['ya_devuelto']} ≠ 240.00 de las filas")
    assert cf["IMPUESTO"] == pytest.approx(360.0, abs=0.01), (
        f"Cash flow: IMPUESTO NETEADO {cf['IMPUESTO']} ≠ 360.00 de las filas")
    assert cf["IMPUESTO"] == pytest.approx(f["retenido"] - f["ya_devuelto"], abs=0.02)
    # Hoy por construcción (`hoja_data` envuelve `cashflow_data`), igual que en el peldaño 1.
    assert hoja_data(res["MSTY"], "MSTY", df)["IMPUESTO"] == pytest.approx(cf["IMPUESTO"], abs=0.01)


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

    NOTA: hasta el 2026-09-18 el pipeline estimaba MSTY sobre el CSV real
    (`real_examples/charles_schwab_data/daniel_zambrano`) con el 19(a) —72.9 %— y no con el
    100 % del cierre fiscal. Desde R1 la base del ROC usa el cierre en años cerrados
    (`logic._roc_events_from_19a` vía `logic.roc_pct_by_year`) y el ROC del holder queda en
    ~90 % (2025 al 100 %, 2026 aún estimado). Este test fija la aritmética de los buckets,
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


def test_i3_sin_retencion_no_se_afirma_con_7a_ilegible():
    """C·6/I3: un 7a que no se pudo leer no es 'sin retención' (0.01 de retenido no es
    lo mismo que 'no se sabe'). Con `withholding_credit`/`federal_tax_withheld` en None,
    `retenido_completo` sale False y `sin_retencion` debe ser False."""
    res = {"MSTY": _stats_sinteticos("MSTY", 1000.0, 100.0, 60.0, "19a")}
    forms = [{"income_code": "37", "gross_income": 276.0,
              "federal_tax_withheld": None, "withholding_credit": 30.0}]
    datos = impuestos_data(res, logic.build_fiscal_profile("Colombia"), forms)
    assert datos["ruta_a"]["sin_retencion"] is False


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
    """`?demo=schwab2`: MSTY (19a) + SCHB/XLK sin dato. Determinista.

    El monto gravable se mueve unos centavos con cada refresh de knowledge/roc_19a.yaml: las
    distribuciones de MSTY sin aviso 19a a ±7 días caen al `weighted_pct` del fondo, que el
    refresh recalcula cada sábado (71.94 → 72.31 el 2026-09-05). El valor de abajo corresponde
    al YAML `asof: 2026-09-05`; si vuelve a fallar por centavos, mirá primero ese asof —
    ver el comentario largo sobre `test_casilla9_no_regresion_con_pais` y
    dividend-analyzer-app/CLAUDE.md, incidente #95."""
    datos = _impuestos_demo("schwab2")
    g = datos["peldanos"]["gravable"]
    assert datos["peldanos"]["bruto"]["monto"] == pytest.approx(385.78, abs=0.02)
    # ACTUALIZADO 2026-09-21 (R1+F6): 125.81 -> 63.80. NO es deriva del refresh 19a: el
    # objeto fiscal pasa a consumir el CIERRE (ICI, casilla 3 del 1099) en los años cerrados
    # en vez de la ESTIMACIÓN 19(a). El bruto (385.78) no se mueve — sólo el bucket gravable.
    assert g["monto"] == pytest.approx(63.80, abs=0.05)
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


# ── Por qué estos 4 números se mueven solos (medido 2026-09-08) ──────────────────────────
# Salen de `logic._roc_events_from_19a`, que empareja cada distribución con su aviso 19a a
# ±7 días y, para las que no encuentran aviso en esa ventana, cae al `weighted_pct` del fondo
# (logic.py:3509). Ese weighted_pct lo RECALCULA el refresh automático de los sábados para
# TODOS los tickers (MSTY 71.94 → 72.31 el 2026-09-05), así que las cifras derivan unos
# centavos sin que haya ningún bug. Aislado en los dos sentidos: con el YAML fresco pero el
# weighted_pct viejo los valores anteriores seguían pasando; con el weighted_pct fresco y sin
# el aviso nuevo del 2026-09-02, fallaban. El driver es el weighted_pct, no el aviso nuevo.
# El juego actual corresponde al YAML `asof: 2026-09-05`.
#
# Se mantienen HARDCODEADOS a propósito: recalcularlos aquí desde el mismo pipeline que
# auditan los volvería auto-referenciales (pasarían aunque impuestos_data se rompiera entera).
# Sí muerden lo que dicen vigilar — mutante `pct = weighted + 5` en el respaldo de
# logic.py:3509 ⇒ 5 de 6 en rojo. Lo que NO vigilan: `_ticker_roc_fraction` (el promedio de
# los 12 avisos recientes) puede anularse a 0 y los 6 siguen verdes — ese guard vive en
# test_logic.py::test_ticker_roc_fraction_*, no aquí.
# Si fallan por centavos tras un `chore: refresh` → actualizar número y asof; CLAUDE.md, #95.
@pytest.mark.parametrize("alias,casilla9_esp", [
    ("schwab_1", 0.00),
    # ACTUALIZADO 2026-09-22 (Sprint 2, fix F1: el objeto fiscal real pasó a leer el
    # cierre ICI con precedencia sobre el 19a, Regla 4b; + refresh 19a asof 2026-09-19):
    # 78.01 -> 95.53. No es drift de centavos: los años cerrados ahora usan el %ROC del
    # cierre fiscal (p. ej. MSTY 2025 = 100% ICI vs ~72% de la estimación 19a), así que
    # la casilla 9 esperada SUBE — más ROC ⇒ más retención que el bróker devuelve.
    ("schwab_2", 95.53),
    # ACTUALIZADO 2026-09-22 (mismo fix F1 + refresh): 81.29 -> 99.27.
    ("schwab_daniel", 99.27),
    # ACTUALIZADO 2026-09-22 (mismo fix F1 + refresh): 1339.96 -> 780.92. Este BAJA:
    # el 1339.96 venía de mezclar tasas de 2025 y 2026; 780.92 es el valor año por año,
    # el MISMO que pinea `test_r2_casilla9_igual_al_objeto_fiscal_ib_real` (actualizado
    # por Sprint 2 el 2026-09-21) — las dos vistas del mismo número convergen (Regla 3b).
    # ACTUALIZADO 2026-09-08 (refresh 19a asof 2026-09-05): 1340.21 -> 1339.96.
    # ACTUALIZADO 2026-09-02 (tolerancia del umbral del ROC): 1314.14 -> 1340.21. La
    # diferencia son los $26.07 de PLTY, que con captura caía a la ruta 'broker' por 72
    # centavos y quedaba «sin dato». Ese 1314.14 NO era la cifra buena: era la del cliente
    # que subía la foto del bróker, mientras el que no la subía veía 1340.21. El nuevo
    # valor es el de AMBAS rutas — ver `test_casilla9_converge_con_y_sin_captura`.
    ("ib_1", 780.92),
])
def test_casilla9_no_regresion_con_pais(alias, casilla9_esp):
    """No-regresión: los 4 casos reales con Colombia declarada pinean su casilla 9.
    Valores re-medidos 2026-09-22 tras el fix F1 de Sprint 2 (precedencia ICI sobre 19a
    en el objeto fiscal real, Regla 4b) + el refresh del 19-sep; el de ib_1 converge con
    `test_r2_casilla9_igual_al_objeto_fiscal_ib_real` (Regla 3b: dos vistas del mismo
    número, ambas a 780.92)."""
    import demo_mode
    if not demo_mode.demo_available():
        pytest.skip("real_examples/ no montado")
    bundle = demo_mode.load_demo_case(alias)
    assert bundle is not None, alias
    datos = impuestos_data(bundle["_results"], logic.build_fiscal_profile("Colombia"), [])
    assert datos["ruta_a"]["casilla9_esperada"] == pytest.approx(casilla9_esp, abs=0.05)


def test_r2_casilla9_igual_al_objeto_fiscal_ib_real():
    """R2 sobre el caso real IB (9 fondos, retención al cobro mezclando 2025 con escudo
    aplicado y 2026 sin escudo): por fondo, `build_withholding_diagnosis(..., None)`
    (sin país) coincide EXACTO con `build_tax_summary(..., base_rate_pct=30.0)` — mismo
    helper único (Regla 3) — y la casilla 9 agregada del peldaño 4 da 801.69, la que mide
    año por año, no los 1466.19 que mezclaba las tasas de 2025 y 2026."""
    import demo_mode
    if not demo_mode.demo_available():
        pytest.skip("real_examples/ no montado")
    bundle = demo_mode.load_demo_case("ib_1")
    assert bundle is not None
    res = bundle["_results"]

    comparados = 0
    for t, s in sorted(res.items()):
        if not isinstance(s, dict) or s.get("skipped") or "error" in s:
            continue
        dg = logic.applied_withholding_rate(s)
        wap = float(dg.get("withheld_at_payment") or 0)
        if dg.get("applied_pct") is None or wap <= 0.01 or dg.get("implausible"):
            continue
        if not (dg.get("gross") or 0) > 0:
            continue
        ts = logic.build_tax_summary(s, t, base_rate_pct=30.0)
        netted = float(ts.get("withheld_real") if ts.get("withheld_real") is not None
                       else s.get("withheld_tax_total") or 0)
        ya = sum(float(v or 0) for v in (s.get("tax_refund_observed_by_year") or {}).values())
        if abs(wap - round(netted + ya, 2)) > max(0.02, 0.01 * wap):
            continue  # no reconcilia: mismo filtro que el oráculo (r2_casilla9_casos.py)

        diag = logic.build_withholding_diagnosis(s, t, None)
        assert diag["refund_roc"] == pytest.approx(ts["refund_total_estimated"], abs=0.05), t
        comparados += 1

    assert comparados >= 8, "muy pocos fondos reconciliaron: revisa el fixture ib_1"

    datos = impuestos_data(res, logic.build_fiscal_profile(), [])
    # ACTUALIZADO 2026-09-21: 801.69 -> 780.92. El oráculo se midió antes de `dccad80`
    # (refresh automático de knowledge/roc_19a.yaml del 19-sep), que movió la base.
    assert datos["ruta_a"]["casilla9_esperada"] == pytest.approx(780.92, abs=0.05)


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
    retenido $60.75, de los que la casilla 9 devuelve $56.65 ⇒ crédito real **$4.10**.

    **Estas cifras NO se mueven con el refresco semanal de 19a** (corregido 2026-09-23; la
    versión anterior de este docstring decía lo contrario y ya no era cierta). Las 20 filas
    del fixture son de **2025**, año cerrado: `roc_pct_by_year` da precedencia al cierre ICI
    y para 2025 las dos fuentes salen de `knowledge/roc_ici.yaml` — MSTY 100.0 y TSLY 72.97,
    ambas marcadas `cierre`, ninguna `estimacion`. Medido: con `weighted_pct` +0.5 pp y
    `roc_pct` +2 pp en TODO `roc_19a.yaml`, este test pasa igual.
    Si algún día el fixture incorpora distribuciones de un año todavía abierto, vuelve a ser
    sensible al 19a y esta nota deja de valer.

    ACTUALIZADO 2026-09-22 (Sprint 2, fix F1 — Regla 4b): 41.27 -> 56.65 y 19.48 -> 4.10.
    No es drift de centavos: el objeto fiscal real pasó a leer el cierre ICI con
    precedencia sobre la estimación 19a. MSTY es 100% ROC según el ICI (verificado contra el
    1042-S real — auditoría R1): fair = 30% × bruto × (1 − 1.00) = $0, así que toda su
    retención vuelve ($46.80); TSLY usa su cierre ICI de 2025 (72.97%).
    Sonda por ticker: MSTY 33.58 -> 46.80, TSLY 7.41 -> 9.85, SCHB 0 (sin ROC).
    El viejo 41.27 usaba la estimación 19a (~72%) sobre un año ya cerrado: subdevolvía.

    Antes de este arreglo la vista presentaba los $60.75 enteros como «ya pagado a EE.UU.»,
    inflando 14.8× la cifra que el cliente llevaría a su contador."""
    d = _datos_f4("schwab_synth_1", monkeypatch)
    c = d["impuesto_local"]["credito_eeuu"]
    assert c["monto"] == pytest.approx(60.75, abs=0.01)
    assert c["vuelve_por_roc"] == pytest.approx(56.65, abs=0.01)
    assert c["definitivo"] == pytest.approx(4.10, abs=0.01)
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


def test_credito_un_cero_medido_se_publica_como_cero_no_como_sin_dato():
    """La otra mitad de «medí cero ≠ no pude medirlo». Una casilla 9 esperada de $0.00 es un
    dato: no vuelve nada, así que todo lo retenido es crédito. Publicarlo como `None` borraría
    un crédito real de la vista y mandaría al cliente a buscar un dato que ya tiene.

    Auditoría M4, ronda 2 (mutante CR-4, `_vuelve_medido = _c9 is not None and _c9 > 0`):
    sobrevivía a la suite completa — el único test de esta rama es el de `ruta_a=None`, y en
    las fixtures la casilla 9 nunca es cero."""
    from ui import adapters
    L = adapters._impuesto_local_cartera(
        {"bruto": {"monto": 100.0}, "gravable": {"monto": 100.0}, "retenido": {"monto": 30.0}},
        None, {}, ruta_a={"casilla9_esperada": 0.0})
    c = L["credito_eeuu"]
    assert c["vuelve_por_roc"] == 0.0
    assert c["definitivo"] == 30.0
    assert c["definitivo_motivo"] is None


def test_casilla9_no_suma_el_roc_de_un_fondo_que_no_reconcilia(monkeypatch):
    """La casilla 9 se gatea por `reconcilia` —la retención al cobro cuadra con neteado +
    devuelto—, igual que el desglose del peldaño 4: si la cifra al cobro no es fiable, el ROC
    medido sobre ella tampoco lo es, y no se promete como devolución.

    Auditoría M4, ronda 2 (mutante CR-6, `if reconcilia:` → `if True:`): sobrevivía a la suite
    completa. Ninguna fixture tiene un fondo que no reconcilie, y el guard hermano
    (`implausible`) ya tiene su propio test. Aquí se fuerza: la retención al cobro de MSTY se
    infla $20 sobre lo que el CSV netea (la patología de reversos que el guard existe para
    contener). Solo queda TSLY: $9.85, la misma cifra de la sonda por ticker del docstring de
    `test_credito_no_cuenta_lo_que_el_broker_devuelve`."""
    real = logic.build_withholding_diagnosis

    def _msty_no_reconcilia(stats, ticker, *a, **k):
        d = real(stats, ticker, *a, **k)
        if ticker == "MSTY":
            d = dict(d, withheld_at_payment=round(float(d["withheld_at_payment"]) + 20.0, 2))
        return d

    monkeypatch.setattr(logic, "build_withholding_diagnosis", _msty_no_reconcilia)
    d = _datos_f4("schwab_synth_1", monkeypatch)
    assert d["ruta_a"]["casilla9_esperada"] == pytest.approx(9.85, abs=0.01)
    assert d["impuesto_local"]["credito_eeuu"]["vuelve_por_roc"] == pytest.approx(9.85, abs=0.01)


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


def test_la_captura_da_base_de_costo_pero_no_cobertura_de_roc():
    """Las dos mitades de la decisión de `ui/vistas.py::_resultados`, medidas juntas.

    La captura de posiciones (`position_overrides`) SÍ entra: es la única fuente de la base
    de costo cuando el CSV no llega a la compra original. El costo del bróker como fuente de
    ROC (`ib_cost_basis_map`) NO entra: alimenta la resta que el contrato descarta (M1 §4,
    «ROC = casilla 3 del 19a, no la resta») y metería a SMH —un ETF amplio sin avisos 19a—
    en la cobertura del peldaño 2 con un ROC del 0% que es ruido de comisiones.

    Sin este test las dos mitades se pueden separar sin que nada muerda: pasar los dos mapas
    «porque van juntos» deja la suite en verde y la escalera diciendo «cubre 4 de 8 fondos»
    con el monto gravable inmóvil.
    """
    import demo_mode
    if not demo_mode.demo_available():
        pytest.skip("real_examples/ no montado")
    b = demo_mode.load_demo_case("schwab")
    df, ov = b["_wizard_df_clean"], b["_wizard_overrides"]
    perfil = logic.build_fiscal_profile("Colombia")

    sin = impuestos_data(logic.analyze_portfolio(df, version="T_SIN"), perfil, [])
    con = impuestos_data(
        logic.analyze_portfolio(df, version="T_CON", position_overrides=ov), perfil, [])

    # 1. La captura da base de costo: fondos que sin ella no se pueden medir.
    assert con["ganancias_capital"]["tickers_base_captura"] == ["SCHB", "XLK"]
    assert (con["ganancias_capital"]["no_realizado"]["n_fondos"]
            > sin["ganancias_capital"]["no_realizado"]["n_fondos"])

    # 2. Y NO da cobertura de ROC: el peldaño 2 no se mueve ni en alcance ni en monto.
    g_con, g_sin = con["peldanos"]["gravable"], sin["peldanos"]["gravable"]
    assert g_con["cubiertos"] == g_sin["cubiertos"], (
        "la captura no puede ampliar la cobertura del ROC: eso sale de los avisos 19a")
    assert sorted(g_con["sin_roc"]) == sorted(g_sin["sin_roc"])
    assert g_con["monto"] == pytest.approx(g_sin["monto"], abs=0.01)

    # 3. El invariante protegido sigue en pie: subir la foto no cambia lo que te devuelven.
    assert con["ruta_a"]["casilla9_esperada"] == pytest.approx(
        sin["ruta_a"]["casilla9_esperada"], abs=0.05)


def test_editar_el_csv_invalida_el_cache_de_resultados():
    """Sin esto, subir un CSV nuevo muestra las cifras del anterior.

    `ui/vistas.py::_resultados` solo recalcula cuando `_vd_resultados` es `None`, así que el
    handler que borra `_wizard_df_clean` tiene que borrarlo también. Con la captura dentro del
    cálculo el síntoma empeora: arrastraría las posiciones de un portafolio al siguiente.
    """
    # C·10/S1: la lista literal en el handler se reemplazó por la constante única
    # `CLAVES_CONTEXTO_CARTERA` (una sola fuente para «editar» CSV, `demo_mode` y este
    # test — dos copias es como este defecto entró la primera vez).
    from ui.carga import CLAVES_CONTEXTO_CARTERA
    assert "_vd_resultados" in CLAVES_CONTEXTO_CARTERA, (
        "el handler de editar-CSV tiene que invalidar el caché de analyze_portfolio")
    fuente = open("ui/carga.py", encoding="utf-8").read()
    assert "for clave in CLAVES_CONTEXTO_CARTERA:" in fuente, (
        "no se encontró el handler que limpia la carga usando la lista única")
    # Y el de confirmar posiciones, que cambia la captura que alimenta ese mismo cálculo.
    assert 'pop("_vd_resultados", None)' in fuente, (
        "confirmar posiciones tiene que invalidar el caché: la captura entra al cálculo")
