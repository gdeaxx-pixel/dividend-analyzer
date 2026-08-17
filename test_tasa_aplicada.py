"""Validación de la tasa que el bróker APLICÓ de verdad (PR C).

El país da la tasa a la que el cliente tiene DERECHO; los números dicen cuál le aplicaron.
No tienen por qué coincidir: el 10% de México solo corre si el W-8BEN está presentado y
vigente (caduca a los 3 años). Sin él retienen 30% igual.

Y la sobre-retención resultante tiene DOS causas que no se pueden sumar en una cifra:
  · ROC      → vuelve sola (IB ene–mar, Schwab jun–sep).
  · W-8BEN   → no vuelve sola: hay que presentar el formulario y reclamar con 1040-NR.
Meterlas en el mismo número sería repetir el bug de las dos verdades del mismo dólar que
originó `specs/roc-nra-invariants.md`.
"""
import os
import sys

import pandas as pd
import pytest

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import logic  # noqa: E402


def _hist(filas):
    """history_df mínimo: [(fecha, action, monto), ...]."""
    return pd.DataFrame({
        "Date": [pd.Timestamp(f) for f, _, _ in filas],
        "Action": [a for _, a, _ in filas],
        "Amount": [m for _, _, m in filas],
        "Ticker": ["MSTY"] * len(filas),
        "Quantity": [0] * len(filas),
    })


def _stats(bruto, filas, roc=None, por_año=None):
    return {
        "history": _hist(filas),
        "dividends_gross_total": bruto,
        "dividends_gross_by_year": por_año or {2025: bruto},
        "roc_percent": roc,
    }


# ── C1 · medir la tasa aplicada ─────────────────────────────────────────────────


def test_mide_la_tasa_aplicada_sobre_el_bruto():
    s = _stats(1000.0, [("2025-06-01", "Cash Dividend", 1000.0),
                        ("2025-06-01", "NRA Tax Adj", -300.0)])
    d = logic.applied_withholding_rate(s)
    assert d["withheld_at_payment"] == pytest.approx(300.0)
    assert d["applied_pct"] == pytest.approx(30.0)


def test_la_tasa_aplicada_ignora_los_reembolsos():
    """**El punto de la Regla 2 (momento).** `withheld_tax_total` netea reembolsos; usarla
    aquí mezclaría el cobro con la devolución del ROC y daría una tasa efectiva que ningún
    tratado explica. Un cliente de IB con devolución automática mostraría ~7.5% y parecería
    tener un tratado que no tiene."""
    # El reembolso va en el MISMO año que la retención — que es el caso de Schwab, que
    # acredita entre junio y septiembre. Con el reembolso en otro año el tope «≥0» que
    # `withheld_tax_total_by_year` aplica por año absorbe la diferencia y las dos
    # implementaciones coinciden: el fixture no discriminaría nada.
    filas = [("2025-06-01", "Cash Dividend", 1000.0),
             ("2025-06-01", "NRA Tax Adj", -300.0),
             ("2025-09-01", "NRA Tax Adj", 225.0)]        # reclasificación ROC, positiva
    s = _stats(1000.0, filas)

    assert logic.withheld_tax_total(s["history"]) == pytest.approx(75.0)          # neteado
    assert logic.withheld_tax_total_by_year(s["history"])[2025] == pytest.approx(75.0)

    d = logic.applied_withholding_rate(s)
    assert d["withheld_at_payment"] == pytest.approx(300.0), "al cobro, sin netear"
    assert d["applied_pct"] == pytest.approx(30.0), (
        "si se netea, la tasa cae a 7.5% y el diagnóstico de W-8BEN se vuelve ciego")

    # Y el diagnóstico completo también tiene que verlo: a 7.5% un cliente de México
    # parecería estar por DEBAJO de su tratado en vez de por encima.
    diag = logic.build_withholding_diagnosis(s, "MSTY", entitled_pct=10.0, country="México")
    assert diag["verdict"] == "tratado_no_aplicado"


def test_el_reembolso_de_otro_año_tampoco_baja_la_tasa():
    """Variante IB: el crédito llega en enero–marzo del año siguiente."""
    s = _stats(1000.0, [("2025-06-01", "Cash Dividend", 1000.0),
                        ("2025-06-01", "NRA Tax Adj", -300.0),
                        ("2026-02-01", "NRA Tax Adj", 225.0)])
    d = logic.applied_withholding_rate(s)
    assert d["withheld_at_payment"] == pytest.approx(300.0)
    assert d["applied_pct"] == pytest.approx(30.0)


def test_tasa_aplicada_sin_bruto_no_inventa():
    d = logic.applied_withholding_rate(_stats(0.0, [("2025-06-01", "NRA Tax Adj", -30.0)]))
    assert d["applied_pct"] is None


# ── C2 · reconciliar con derecho vs aplicada ────────────────────────────────────


def test_sin_pais_declarado_no_diagnostica():
    s = _stats(1000.0, [("2025-06-01", "Cash Dividend", 1000.0),
                        ("2025-06-01", "NRA Tax Adj", -300.0)])
    d = logic.build_withholding_diagnosis(s, "MSTY", entitled_pct=logic.RATE_UNDECLARED)
    assert d["verdict"] == "sin_declarar"
    assert d["gap_w8ben"] == 0.0 and d["refund_roc"] == 0.0


def test_colombia_al_30_coincide():
    s = _stats(1000.0, [("2025-06-01", "Cash Dividend", 1000.0),
                        ("2025-06-01", "NRA Tax Adj", -300.0)], roc=0.0)
    d = logic.build_withholding_diagnosis(s, "MSTY", entitled_pct=30.0, country="Colombia")
    assert d["verdict"] == "coincide"
    assert d["gap_w8ben"] == pytest.approx(0.0, abs=0.01)


def test_mexico_con_retencion_del_30_delata_el_w8ben():
    """El caso que motivó todo esto: tratado del 10%, pero le retienen 30%."""
    s = _stats(1000.0, [("2025-06-01", "Cash Dividend", 1000.0),
                        ("2025-06-01", "NRA Tax Adj", -300.0)], roc=0.0)
    d = logic.build_withholding_diagnosis(s, "MSTY", entitled_pct=10.0, country="México")
    assert d["verdict"] == "tratado_no_aplicado"
    assert d["gap_w8ben"] == pytest.approx(200.0, abs=0.01)   # 30% − 10% sobre $1000
    assert "W-8BEN" in d["label"] and "1040-NR" in d["label"]


def test_la_tolerancia_absorbe_el_ruido_pero_no_un_tratado():
    """Redondeos al centavo y dividendos a caballo entre años mueven la tasa unas décimas.
    2 pp absorben eso sin dejar de distinguir 10 de 30."""
    casi = _stats(1000.0, [("2025-06-01", "Cash Dividend", 1000.0),
                           ("2025-06-01", "NRA Tax Adj", -301.5)], roc=0.0)
    assert logic.build_withholding_diagnosis(
        casi, "MSTY", entitled_pct=30.0, country="Colombia")["verdict"] == "coincide"

    lejos = _stats(1000.0, [("2025-06-01", "Cash Dividend", 1000.0),
                            ("2025-06-01", "NRA Tax Adj", -330.0)], roc=0.0)
    assert logic.build_withholding_diagnosis(
        lejos, "MSTY", entitled_pct=30.0, country="Colombia")["verdict"] == "tratado_no_aplicado"


# ── C3 · los dos buckets, separados y exactos ───────────────────────────────────


@pytest.mark.parametrize("roc", [0.0, 40.0, 73.0, 90.0])
def test_la_descomposicion_es_exacta(roc):
    """`refund_roc + gap_w8ben` tiene que dar EXACTAMENTE la sobre-retención total.

    Si no cuadra, la app estaría mostrando dos mitades que no suman el todo — que es
    peor que mostrar el todo sin desglosar."""
    bruto, retenido = 1000.0, 300.0
    s = _stats(bruto, [("2025-06-01", "Cash Dividend", bruto),
                       ("2025-06-01", "NRA Tax Adj", -retenido)], roc=roc)
    d = logic.build_withholding_diagnosis(s, "MSTY", entitled_pct=10.0, country="México")

    escudo = 1.0 - roc / 100.0
    exceso_total = retenido - bruto * 0.10 * escudo
    assert d["refund_roc"] + d["gap_w8ben"] == pytest.approx(exceso_total, abs=0.02)


def test_los_dos_buckets_no_se_confunden():
    """Con tratado aplicado correctamente todo el exceso es ROC; sin ROC todo es W-8BEN.
    Los carriles no se cruzan (Regla 4)."""
    solo_roc = _stats(1000.0, [("2025-06-01", "Cash Dividend", 1000.0),
                               ("2025-06-01", "NRA Tax Adj", -300.0)], roc=80.0)
    d1 = logic.build_withholding_diagnosis(solo_roc, "MSTY", entitled_pct=30.0,
                                           country="Colombia")
    assert d1["refund_roc"] > 0 and d1["gap_w8ben"] == pytest.approx(0.0, abs=0.01)

    solo_w8 = _stats(1000.0, [("2025-06-01", "Cash Dividend", 1000.0),
                              ("2025-06-01", "NRA Tax Adj", -300.0)], roc=0.0)
    d2 = logic.build_withholding_diagnosis(solo_w8, "MSTY", entitled_pct=10.0,
                                           country="México")
    assert d2["gap_w8ben"] > 0 and d2["refund_roc"] == pytest.approx(0.0, abs=0.01)


def test_sin_roc_el_exceso_no_desaparece():
    """Un ETF de crecimiento no tiene avisos 19a: `roc_percent` es None. El escudo es CERO,
    no «desconocido» — si no, los dos buckets salían en $0 y un exceso real se esfumaba."""
    s = _stats(500.0, [("2025-06-01", "Cash Dividend", 500.0),
                       ("2025-06-01", "NRA Tax Adj", -150.0)], roc=None)
    d = logic.build_withholding_diagnosis(s, "SCHB", entitled_pct=10.0, country="México")
    assert d["verdict"] == "tratado_no_aplicado"
    assert d["gap_w8ben"] == pytest.approx(100.0, abs=0.01)   # (30%−10%) × $500
    assert d["refund_roc"] == pytest.approx(0.0, abs=0.01)


def test_la_tasa_observada_no_alimenta_el_objeto_fiscal():
    """La tasa APLICADA diagnostica; la que manda la aritmética de `fair_withholding` es la
    tasa CON DERECHO. Confundirlas haría que a un mexicano al que le retienen 30% la app le
    dijera que 30% es lo justo — justo el error que este PR existe para evitar."""
    s = _stats(1000.0, [("2025-06-01", "Cash Dividend", 1000.0),
                        ("2025-06-01", "NRA Tax Adj", -300.0)], roc=0.0)
    s["withheld_tax_total"] = 300.0
    s["total_dividends"] = 700.0
    s["withheld_by_year"] = {2025: 300.0}

    ts = logic.build_tax_summary(s, "MSTY", base_rate_pct=10.0, country="México")
    assert ts["fair_withholding"] == pytest.approx(100.0, abs=0.01), (
        "la retención justa sale del 10% del tratado, no del 30% observado")


# ── Contra el CSV real ──────────────────────────────────────────────────────────


def test_contra_el_csv_real_de_schwab():
    """Ground truth: el 1042-S del mismo cliente declara 30% en la casilla 3b para el
    código 06, y el CSV tiene que dar lo mismo medido sobre los movimientos."""
    import glob
    import io

    rutas = glob.glob(os.path.join(BASE, "real_examples", "charles_schwab_data",
                                   "daniel_zambrano", "*.csv"))
    if not rutas:
        pytest.skip("real_examples no montado (data privada)")

    class _FF:
        def __init__(self, b):
            self._b = io.BytesIO(b)
            self.name = "t.csv"

        def read(self):
            return self._b.read()

        def seek(self, n):
            self._b.seek(n)

    with open(rutas[0], "rb") as fh:
        df, broker = logic.load_and_detect_csv(_FF(fh.read()))
    assert broker == "schwab"
    res = logic.analyze_portfolio(logic.normalize_csv(df), version="TEST_TASA_APLICADA")

    medidas = {}
    for tk, s in res.items():
        if "error" in s or s.get("skipped"):
            continue
        d = logic.applied_withholding_rate(s)
        if d["applied_pct"] is not None:
            medidas[tk] = d["applied_pct"]

    assert medidas, "ningún ticker con retención medible"
    for tk, pct in medidas.items():
        assert pct == pytest.approx(30.0, abs=1.0), (
            f"{tk}: {pct}% — el 1042-S del mismo cliente declara 30% en la casilla 3b")
