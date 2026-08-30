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
                            ("2025-06-01", "NRA Tax Adj", -300.0)], roc=0.0)
    assert logic.build_withholding_diagnosis(
        lejos, "MSTY", entitled_pct=10.0, country="México")["verdict"] == "tratado_no_aplicado"


def test_tasa_aplicada_imposible_no_acusa_del_w8ben():
    """Una tasa aplicada por encima del techo NRA del 30% no es posible: la cifra de
    retención al cobro está inflada (típicamente reversos mal contados). El diagnóstico
    NO debe emitir 'tratado_no_aplicado' con base en un número que el código sabe irreal."""
    s = _stats(1000.0, [("2025-06-01", "Cash Dividend", 1000.0),
                        ("2025-06-01", "NRA Tax Adj", -360.0)], roc=0.0)
    d = logic.build_withholding_diagnosis(s, "TSLY", entitled_pct=30.0, country="Colombia")
    assert d["implausible"] is True
    assert d["verdict"] == "indeterminado"
    assert d["verdict"] != "tratado_no_aplicado"


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


def test_convencion_ib_plegada_tambien_mide_la_tasa():
    """Cobertura de la convención IB (check 12): la retención va PLEGADA en una fila
    'Dividend - Foreign Tax Withholding' (con la palabra dividend), no en un 'NRA Tax Adj'
    aparte como Schwab. `withheld_at_payment_by_year` —que alimenta `applied_withholding_rate`
    vía la copia de logic.py:4941, hoy enrutada al predicado único `_is_tax_row_action`—
    tiene que verla igual: al cobro, sin netear reembolsos."""
    # mismo escenario numérico que test_la_tasa_aplicada_ignora_los_reembolsos,
    # pero con la fila de impuesto en formato IB
    filas = [("2025-02-28", "Dividend", 1000.0),
             ("2025-02-28", "Dividend - Foreign Tax Withholding", -300.0),
             ("2026-02-01", "Dividend - Foreign Tax Withholding", 225.0)]  # reverso IB
    s = _stats(1000.0, filas)

    assert logic.withheld_at_payment_by_year(s["history"])[2025] == pytest.approx(300.0), (
        "la fila IB plegada cuenta como retención al cobro")
    d = logic.applied_withholding_rate(s)
    assert d["withheld_at_payment"] == pytest.approx(300.0)
    assert d["applied_pct"] == pytest.approx(30.0), (
        "si la convención plegada de IB no se viera, la tasa saldría 0% y el "
        "diagnóstico de W-8BEN sería ciego para clientes IB")


def test_convencion_ib_contra_el_fixture_sintetico(monkeypatch):
    """Ground truth sintético de la convención IB (`fixtures/ib_synth_1`, retención plegada
    30% plano): CONY bruto $60.00, retención $18.00 → tasa aplicada exactamente 30%,
    medida con el objeto fiscal completo de `analyze_portfolio` (no a mano). NVDY se mide
    aparte con su valor esperado real: su bruto incluye $1.20 de 'Payment in Lieu'
    (mapeado a 'Dividend' por action_map) sobre el que NO hubo retención, así que su tasa
    es 18.0/61.2 = 29.41%, no 30% — el test lo pinea para cazar deriva del denominador."""
    import io

    class _FF:
        def __init__(self, b):
            self._b = io.BytesIO(b)
            self.name = "ib_synth_1.csv"

        def read(self):
            return self._b.read()

        def seek(self, n):
            self._b.seek(n)

    raw = open(os.path.join(BASE, "fixtures", "ib_synth_1",
                            "synthetic_transactions.csv"), "rb").read()
    df, broker = logic.load_and_detect_csv(_FF(raw))
    assert broker == "ibkr"
    monkeypatch.setattr(logic, "fetch_market_data", lambda t, d: (
        pd.DataFrame({"Close": [20.0], "Dividends": [0.0], "Stock Splits": [0.0]},
                     index=[pd.Timestamp("2024-10-15")]), None))
    res = logic.analyze_portfolio(logic.normalize_csv(df), version="TEST_TASA_APLICADA_IB")

    d_cony = logic.applied_withholding_rate(res["CONY"])
    assert d_cony["withheld_at_payment"] == pytest.approx(18.0), (
        "la retención plegada IB debe verse como retención al cobro")
    assert d_cony["applied_pct"] == pytest.approx(30.0, abs=0.1), (
        f"CONY: {d_cony['applied_pct']}% — el fixture IB declara 30% plano plegado en fila")

    # NVDY: mismo numerador ($18), denominador inflado por Payment in Lieu sin retención
    d_nvdy = logic.applied_withholding_rate(res["NVDY"])
    assert res["NVDY"]["dividends_gross_total"] == pytest.approx(61.20, abs=0.01)
    assert d_nvdy["applied_pct"] == pytest.approx(18.0 / 61.2 * 100, abs=0.01), (
        "NVDY: la tasa debe salir del bruto REAL (incluido el in-lieu), no de un redondeo")


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


# ── C4 · reversos de split inverso de IB (fix 2026-08-29) ───────────────────────


def test_par_de_reverso_no_cuenta_como_cobro():
    """−$38.30 y +$38.30 el mismo día/ticker (reverso de split .OLD): al cobro $0."""
    h = _hist([("2025-12-29", "Dividend - Foreign Tax Withholding", -38.30),
               ("2025-12-29", "Dividend - Foreign Tax Withholding", 38.30)])
    cls = logic._classify_tax_rows(h)
    assert cls["withheld_at_payment_by_year"].get(2025, 0.0) == pytest.approx(0.0)
    assert cls["genuine_refund_by_year"].get(2025, 0.0) == pytest.approx(0.0)
    assert logic.withheld_at_payment_by_year(h) == {} or \
        logic.withheld_at_payment_by_year(h).get(2025, 0.0) == pytest.approx(0.0)


def test_emparejamiento_uno_a_uno_voraz():
    """Tres negativas de −$10 y una positiva de +$10 el mismo día → al cobro $20, no $0 ni $30."""
    h = _hist([("2025-12-19", "Dividend - Foreign Tax Withholding", -10.0),
               ("2025-12-19", "Dividend - Foreign Tax Withholding", -10.0),
               ("2025-12-19", "Dividend - Foreign Tax Withholding", -10.0),
               ("2025-12-19", "Dividend - Foreign Tax Withholding", 10.0)])
    cls = logic._classify_tax_rows(h)
    assert cls["withheld_at_payment_by_year"][2025] == pytest.approx(20.0)
    assert cls["genuine_refund_by_year"].get(2025, 0.0) == pytest.approx(0.0)


def test_positiva_huerfana_es_reembolso_genuino_incluso_en_ib():
    """Positiva sin negativa gemela → entra en `observed_tax_refund_by_year`, y para IB
    (Action con 'dividend') TAMBIÉN — lo que antes no pasaba (exclusión en bloque)."""
    h = _hist([("2025-12-29", "Dividend - Foreign Tax Withholding", -38.30),
               ("2025-12-29", "Dividend - Foreign Tax Withholding", 38.30),
               ("2026-01-26", "Dividend - Foreign Tax Withholding", 7.31)])   # huérfana = ROC real
    ref = logic.observed_tax_refund_by_year(h)
    assert ref.get(2026, 0.0) == pytest.approx(7.31)
    assert ref.get(2025, 0.0) == pytest.approx(0.0)   # el par no cuenta


def test_invariante_al_cobro_igual_neteado_mas_devuelto():
    """al_cobro == neteado + ya_devuelto, exacto, sobre un fixture con pares y una huérfana."""
    filas = [
        ("2025-12-29", "Dividend - Foreign Tax Withholding", -38.30),
        ("2025-12-29", "Dividend - Foreign Tax Withholding", 38.30),   # reverso
        ("2025-12-19", "Dividend - Foreign Tax Withholding", -29.02),
        ("2025-12-19", "Dividend - Foreign Tax Withholding", 29.02),   # reverso
        ("2025-11-15", "Dividend - Foreign Tax Withholding", -50.00),  # retención real
        ("2026-01-26", "Dividend - Foreign Tax Withholding", 7.31),    # reembolso genuino
    ]
    h = _hist(filas)
    al_cobro = round(sum(logic.withheld_at_payment_by_year(h).values()), 2)
    devuelto = round(sum(logic.observed_tax_refund_by_year(h).values()), 2)
    neteado = logic.withheld_tax_total(h)
    assert al_cobro == pytest.approx(50.0)
    assert devuelto == pytest.approx(7.31)
    assert neteado == pytest.approx(42.69)   # −(−38.30+38.30−29.02+29.02−50.00+7.31) = 42.69
    assert al_cobro == pytest.approx(neteado + devuelto)


def test_withheld_tax_total_no_se_mueve_con_el_fix():
    """La propiedad de seguridad: `withheld_tax_total` ya neteaba bien y su cifra no cambia."""
    casos = [
        [("2025-06-01", "NRA Tax Adj", -300.0)],
        [("2025-06-01", "NRA Tax Adj", -300.0), ("2025-09-01", "NRA Tax Adj", 225.0)],
        [("2025-12-29", "Dividend - Foreign Tax Withholding", -38.30),
         ("2025-12-29", "Dividend - Foreign Tax Withholding", 38.30),
         ("2025-11-15", "Dividend - Foreign Tax Withholding", -50.0)],
    ]
    esperado = [300.0, 75.0, 50.0]
    for filas, exp in zip(casos, esperado):
        assert logic.withheld_tax_total(_hist(filas)) == pytest.approx(exp)


def test_ib_real_ground_truth_los_cuatro_tickers():
    """Ground truth medido en la auditoría, sobre el CSV real de IB."""
    import glob
    rutas = [p for p in glob.glob(os.path.join(
        BASE, "real_examples", "interactive_brokers_data", "1", "*.csv"))
        if not p.endswith("expected.json")]
    if not rutas:
        pytest.skip("real_examples no montado (data privada)")

    class _FF:
        def __init__(self, b, n):
            self._b = b
            self.name = n

        def read(self):
            return self._b

        def seek(self, *a):
            pass

    with open(rutas[0], "rb") as fh:
        out = logic.load_and_detect_csv(_FF(fh.read(), os.path.basename(rutas[0])))
    df = logic.normalize_csv(out[0] if isinstance(out, tuple) else out)

    esperado = {   # ticker: (al_cobro, neteado, ya_devuelto)
        "CONY": (202.98, 202.98, 0.00),
        "MSTY": (568.77, 545.52, 23.25),
        "TSLY": (502.32, 495.01, 7.31),
        "NVDY": (798.30, 798.30, 0.00),
    }
    for tk, (al_cobro, neteado, devuelto) in esperado.items():
        g = df[df["Ticker"] == tk]
        wap = round(sum(logic.withheld_at_payment_by_year(g).values()), 2)
        ref = round(sum(logic.observed_tax_refund_by_year(g).values()), 2)
        net = logic.withheld_tax_total(g)
        assert wap == pytest.approx(al_cobro, abs=0.01), f"{tk} al cobro"
        assert net == pytest.approx(neteado, abs=0.01), f"{tk} neteado"
        assert ref == pytest.approx(devuelto, abs=0.01), f"{tk} ya devuelto"
        assert wap == pytest.approx(net + ref, abs=0.01), f"{tk} invariante"


# ── C5 · «Foreign Tax Paid» separado de la retención NRA (fix 2026-08-29) ────────


def test_predicado_nra_no_toca_ib():
    """La trampa principal: en IB la retención NRA SE LLAMA `Dividend - Foreign Tax
    Withholding`. El discriminante es `'foreign tax paid'` EXACTO, nunca `'foreign tax'`."""
    assert logic._is_nra_withholding_action("Dividend - Foreign Tax Withholding") is True
    assert logic._is_nra_withholding_action("NRA Tax Adj") is True
    assert logic._is_nra_withholding_action("Foreign Tax Paid") is False
    assert logic._is_foreign_tax_credit_action("Foreign Tax Paid") is True
    assert logic._is_foreign_tax_credit_action("Dividend - Foreign Tax Withholding") is False


def test_predicado_nra_sobre_las_465_filas_reales_de_ib():
    """Ninguna fila de retención de IB puede quedar fuera del eje NRA."""
    import glob
    rutas = [p for p in glob.glob(os.path.join(
        BASE, "real_examples", "interactive_brokers_data", "1", "*.csv"))
        if not p.endswith("expected.json")]
    if not rutas:
        pytest.skip("real_examples no montado")

    class _FF:
        def __init__(self, b, n):
            self._b, self.name = b, n

        def read(self):
            return self._b

        def seek(self, *a):
            pass

    with open(rutas[0], "rb") as fh:
        out = logic.load_and_detect_csv(_FF(fh.read(), os.path.basename(rutas[0])))
    df = logic.normalize_csv(out[0] if isinstance(out, tuple) else out)
    tax = df[df["Action"].apply(logic._is_tax_row_action)]
    nra = df[df["Action"].apply(logic._is_nra_withholding_action)]
    assert len(tax) == len(nra) > 0, "IB no tiene ninguna fila 'Foreign Tax Paid'; nada debe caer"


def test_foreign_tax_paid_sale_de_la_tasa_aplicada():
    """NRA $300 + FTP $35 sobre bruto $1000 → aplicada 30.0% (no 33.5%), implausible=False,
    y para un colombiano el veredicto es 'coincide'."""
    s = _stats(1000.0, [("2025-06-01", "Cash Dividend", 1000.0),
                        ("2025-06-01", "NRA Tax Adj", -300.0),
                        ("2025-06-01", "Foreign Tax Paid", -35.0)], roc=0.0)
    d = logic.applied_withholding_rate(s)
    assert d["withheld_at_payment"] == pytest.approx(300.0)
    assert d["applied_pct"] == pytest.approx(30.0)
    assert d["implausible"] is False
    diag = logic.build_withholding_diagnosis(s, "MSTY", entitled_pct=30.0, country="Colombia")
    assert diag["verdict"] == "coincide"


def test_foreign_tax_paid_no_mueve_withheld_tax_total_de_ib():
    """Coherencia del eje: `withheld_tax_total` cae exactamente el FTP y ni un centavo más."""
    con_ftp = _hist([("2025-06-01", "Cash Dividend", 1000.0),
                     ("2025-06-01", "NRA Tax Adj", -300.0),
                     ("2025-06-01", "Foreign Tax Paid", -35.0)])
    sin_ftp = _hist([("2025-06-01", "Cash Dividend", 1000.0),
                     ("2025-06-01", "NRA Tax Adj", -300.0)])
    assert logic.withheld_tax_total(con_ftp) == pytest.approx(300.0)
    assert logic.withheld_tax_total(sin_ftp) == pytest.approx(300.0)
    assert logic.foreign_tax_paid_total(con_ftp) == pytest.approx(35.0)
    assert logic.foreign_tax_paid_total(sin_ftp) == pytest.approx(0.0)
    # invariante: al cobro == neteado + devuelto, con y sin FTP
    for h in (con_ftp, sin_ftp):
        alc = round(sum(logic.withheld_at_payment_by_year(h).values()), 2)
        dev = round(sum(logic.observed_tax_refund_by_year(h).values()), 2)
        assert alc == pytest.approx(logic.withheld_tax_total(h) + dev)


def test_schwab_fixture_invariante_con_ftp_estrechado():
    """SCHB de `schwab_synth_1`: NRA -$0.45 + FTP -$0.08. Coherente → al cobro 0.45,
    neteado 0.45, invariante 0.00 (a medias daría -0.08 y 'parcial')."""
    df = logic.normalize_csv(
        pd.read_csv(os.path.join(BASE, "fixtures", "schwab_synth_1",
                                 "synthetic_transactions.csv")))
    g = df[df["Ticker"] == "SCHB"]
    alc = round(sum(logic.withheld_at_payment_by_year(g).values()), 2)
    dev = round(sum(logic.observed_tax_refund_by_year(g).values()), 2)
    net = logic.withheld_tax_total(g)
    assert alc == pytest.approx(0.45)
    assert net == pytest.approx(0.45)
    assert alc == pytest.approx(net + dev)
    assert logic.foreign_tax_paid_total(g) == pytest.approx(0.08)


def test_ib_ground_truth_no_se_mueve_con_este_fix():
    """Los 4 tickers de IB no tienen ni una fila `Foreign Tax Paid`: sus cifras de retención
    NO deben moverse respecto al PR anterior."""
    import glob
    rutas = [p for p in glob.glob(os.path.join(
        BASE, "real_examples", "interactive_brokers_data", "1", "*.csv"))
        if not p.endswith("expected.json")]
    if not rutas:
        pytest.skip("real_examples no montado")

    class _FF:
        def __init__(self, b, n):
            self._b, self.name = b, n

        def read(self):
            return self._b

        def seek(self, *a):
            pass

    with open(rutas[0], "rb") as fh:
        out = logic.load_and_detect_csv(_FF(fh.read(), os.path.basename(rutas[0])))
    df = logic.normalize_csv(out[0] if isinstance(out, tuple) else out)
    esperado = {"CONY": 202.98, "MSTY": 545.52, "TSLY": 495.01, "NVDY": 798.30}
    for tk, neteado in esperado.items():
        g = df[df["Ticker"] == tk]
        assert logic.withheld_tax_total(g) == pytest.approx(neteado, abs=0.01), tk
        assert logic.foreign_tax_paid_total(g) == pytest.approx(0.0), f"{tk} sin FTP"


def test_regresion_zim_impuesto_israeli():
    """El caso real: ZIM $0.63 + $2.11 en dic-2024 queda FUERA de la retención NRA y DENTRO
    de `foreign_tax_paid`."""
    ruta = os.path.join(BASE, "real_examples", "charles_schwab_data", "2",
                        "indiv_transactions.csv")
    if not os.path.exists(ruta):
        pytest.skip("real_examples no montado")
    df = logic.normalize_csv(pd.read_csv(ruta))
    z = df[df["Ticker"] == "ZIM"]
    assert logic.foreign_tax_paid_total(z) == pytest.approx(2.74, abs=0.01)
    assert logic.foreign_tax_paid_by_year(z) == {2024: pytest.approx(2.74, abs=0.01)}
    assert logic.withheld_tax_total(z) == pytest.approx(0.0), "el impuesto israelí no es NRA"


# ── C6 · el redondeo de centavos no dispara el guard (fix 2026-08-29) ───────────
#
# El guard de la tasa imposible compara EN DÓLARES, no en pp: el error a absorber es el
# redondeo de centavos del bróker, que es absoluto y ocurre POR PAGO. `techo = bruto ·
# (30+TOL)/100 + N·0.01`, con N = número de filas de impuesto.


def test_mu_redondeo_de_centavos_no_es_implausible():
    """MU real: $0.12 de dividendo, $0.04 de retención (30% = $0.036, Schwab redondea a
    $0.04). 33.3% aparente sobre 4 centavos — NO es sobre-retención."""
    s = _stats(0.12, [("2025-03-01", "Cash Dividend", 0.12),
                      ("2025-03-01", "NRA Tax Adj", -0.04)], roc=0.0)
    d = logic.applied_withholding_rate(s)
    assert d["implausible"] is False
    diag = logic.build_withholding_diagnosis(s, "MU", entitled_pct=30.0, country="Colombia")
    assert diag["verdict"] != "indeterminado"


def test_acumulacion_de_pagos_diminutos_no_es_implausible():
    """El caso que DESCARTA la fórmula porcentual: 20 pagos semanales de $0.15 con
    retención 30% real redondeada a $0.05 cada uno → bruto $3.00, retenido $1.00, 33.3%
    aparente. El redondeo se acumula con el nº de pagos (perfil YieldMax semanal); una
    tolerancia en pp contra el bruto total lo dejaría pasar como implausible."""
    filas = []
    for i in range(20):
        d = f"2025-{(i % 12) + 1:02d}-0{(i % 3) + 1}"
        filas.append((d, "Cash Dividend", 0.15))
        filas.append((d, "NRA Tax Adj", -0.05))
    s = _stats(3.00, filas, roc=0.0)
    d = logic.applied_withholding_rate(s)
    assert d["withheld_at_payment"] == pytest.approx(1.00)
    assert d["applied_pct"] == pytest.approx(33.33)
    assert d["implausible"] is False


@pytest.mark.parametrize("retenido,esperado", [
    (300.0, False),   # 30% exacto
    (320.0, False),   # 32%, en el borde de la tolerancia
    (330.0, True),    # 33%, apenas pasado el borde
    (360.0, True),    # 36%, sobre-retención real
])
def test_el_termino_absoluto_no_relaja_lo_material(retenido, esperado):
    """Con bruto de $1,000 el término `N·0.01` es despreciable: los cuatro casos mantienen
    exactamente el veredicto que tenían antes del fix. Propiedad de seguridad."""
    s = _stats(1000.0, [("2025-06-01", "Cash Dividend", 1000.0),
                        ("2025-06-01", "NRA Tax Adj", -retenido)], roc=0.0)
    assert logic.applied_withholding_rate(s)["implausible"] is esperado


def test_el_caso_ib_pre_fix_de_reversos_sigue_cazandose():
    """El bug que motivó el guard: NVDY IB pre-clasificador, $4,117.61 de bruto, $1,628.35
    contados al cobro (reversos incluidos), 40 filas de impuesto. Debe seguir marcándose
    implausible — el término absoluto ($0.40) no lo rescata."""
    filas = [("2025-01-15", "Cash Dividend", 4117.61)]
    resto, acum = 1628.35, 0.0
    for i in range(40):
        v = round(1628.35 / 40, 2) if i < 39 else round(1628.35 - acum, 2)
        acum += v
        filas.append((f"2025-{(i % 12) + 1:02d}-15",
                      "Dividend - Foreign Tax Withholding", -v))
    s = _stats(4117.61, filas, roc=0.0)
    assert logic.applied_withholding_rate(s)["implausible"] is True


def test_ib_ground_truth_intacto_bajo_el_guard_en_dolares():
    """Los 4 tickers de IB: al cobro exacto, invariante en cero, y NINGUNO implausible."""
    import glob
    rutas = [p for p in glob.glob(os.path.join(
        BASE, "real_examples", "interactive_brokers_data", "1", "*.csv"))
        if not p.endswith("expected.json")]
    if not rutas:
        pytest.skip("real_examples no montado")

    class _FF:
        def __init__(self, b, n):
            self._b, self.name = b, n

        def read(self):
            return self._b

        def seek(self, *a):
            pass

    with open(rutas[0], "rb") as fh:
        out = logic.load_and_detect_csv(_FF(fh.read(), os.path.basename(rutas[0])))
    df = logic.normalize_csv(out[0] if isinstance(out, tuple) else out)
    esperado = {"CONY": 202.98, "MSTY": 568.77, "TSLY": 502.32, "NVDY": 798.30}
    for tk, al_cobro in esperado.items():
        g = df[df["Ticker"] == tk]
        tot = logic.build_dividend_tax_totals(g)
        s = {"history": g, "dividends_gross_total": tot["gross"],
             "dividends_gross_by_year": tot["gross_by_year"], "roc_percent": 0.0}
        d = logic.applied_withholding_rate(s)
        assert d["withheld_at_payment"] == pytest.approx(al_cobro, abs=0.01), tk
        assert d["implausible"] is False, f"{tk} no debe caer en el guard"
        dev = round(sum(logic.observed_tax_refund_by_year(g).values()), 2)
        assert d["withheld_at_payment"] == pytest.approx(
            logic.withheld_tax_total(g) + dev, abs=0.01), f"{tk} invariante"


# ── C7 · el VEREDICTO también compara en dólares (fix 2026-08-30) ───────────────
#
# `build_withholding_diagnosis` decidía en puntos porcentuales — mismo problema de redondeo
# que el guard `implausible` del #94, una capa más abajo. En producción MU (cliente
# colombiano, 30% con derecho) daba 'tratado_no_aplicado' por un exceso real de $0.0040.


@pytest.mark.parametrize("nombre,bruto,retenido,derecho,n,esperado", [
    ("MU real (redondeo)",            0.12,  0.04, 30.0,  1, "coincide"),
    ("20 pagos de $0.15 redondeados", 3.00,  1.00, 30.0, 20, "coincide"),
    ("gap de tratado real (Mexico)",  1000.0, 300.0, 10.0, 1, "tratado_no_aplicado"),
    ("W-8BEN vencido (derecho 15%)",  1000.0, 300.0, 15.0, 1, "tratado_no_aplicado"),
    ("30% exacto con derecho 30%",    1000.0, 300.0, 30.0, 1, "coincide"),
    ("retienen de menos (ROC)",       1000.0, 100.0, 30.0, 1, "menor_de_lo_esperado"),
])
def test_veredicto_en_dolares_los_casos_del_traspaso(nombre, bruto, retenido, derecho, n, esperado):
    """Los casos de la tabla del traspaso. El caso «12c / 6c → tratado_no_aplicado» NO se
    incluye: el guard `implausible` del #94 lo intercepta antes (6c sobre 12c = 50% aplicada,
    por encima del techo), y ese guard queda fuera de alcance. Cae en 'indeterminado', que
    tampoco acusa — ver el traspaso de vuelta."""
    if n == 1:
        filas = [("2025-03-01", "Cash Dividend", bruto),
                 ("2025-03-01", "NRA Tax Adj", -retenido)]
    else:
        filas = []
        for i in range(n):
            d = f"2025-{(i % 12) + 1:02d}-0{(i % 3) + 1}"
            filas.append((d, "Cash Dividend", round(bruto / n, 2)))
            filas.append((d, "NRA Tax Adj", -round(retenido / n, 2)))
    s = _stats(bruto, filas, roc=0.0)
    d = logic.build_withholding_diagnosis(s, "X", entitled_pct=derecho, country="Colombia")
    assert d["verdict"] == esperado, f"{nombre}: {d['verdict']}"


def test_mu_exceso_contra_holgura():
    """MU: exceso $0.0040 contra holgura $0.0124 (bruto·2% + 1·$0.01) → coincide."""
    s = _stats(0.12, [("2025-03-01", "Cash Dividend", 0.12),
                      ("2025-03-01", "NRA Tax Adj", -0.04)], roc=0.0)
    d = logic.build_withholding_diagnosis(s, "MU", entitled_pct=30.0, country="Colombia")
    assert d["verdict"] == "coincide"
    # la descomposición no cambia: no hay exceso material que repartir
    assert d["refund_roc"] == pytest.approx(0.0, abs=0.01)
    assert d["gap_w8ben"] == pytest.approx(0.0, abs=0.01)


def test_n_tax_rows_se_reusa_del_mismo_dict():
    """Regla 3: el veredicto usa el MISMO `n_tax_rows` que el guard `implausible`, no una
    copia. `applied_withholding_rate` lo expone."""
    s = _stats(1000.0, [("2025-01-01", "Cash Dividend", 500.0),
                        ("2025-01-01", "NRA Tax Adj", -150.0),
                        ("2025-07-01", "Cash Dividend", 500.0),
                        ("2025-07-01", "NRA Tax Adj", -150.0)], roc=0.0)
    assert logic.applied_withholding_rate(s)["n_tax_rows"] == 2


def test_gap_de_tratado_real_no_se_relaja_con_el_termino_absoluto():
    """El término `N·0.01` no puede tapar un gap real ni con muchas filas: México 10%,
    retienen 30% sobre $1,000 en 12 pagos → sigue siendo tratado_no_aplicado."""
    filas = []
    for i in range(12):
        filas.append((f"2025-{i + 1:02d}-01", "Cash Dividend", round(1000.0 / 12, 2)))
        filas.append((f"2025-{i + 1:02d}-01", "NRA Tax Adj", -round(300.0 / 12, 2)))
    s = _stats(1000.0, filas, roc=0.0)
    d = logic.build_withholding_diagnosis(s, "X", entitled_pct=10.0, country="México")
    assert d["verdict"] == "tratado_no_aplicado"
