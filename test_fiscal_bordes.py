"""Bordes del carril fiscal (auditoría del 2026-11-20, s12 H1, H2, H4, H5 y H6). Historiales
mínimos armados a mano; cada esperado es aritmética de la regla, no salida del motor."""
import pandas as pd
import pytest

import logic


@pytest.fixture
def sin_avisos(monkeypatch):
    """Sin avisos 19a ni cierres fiscales: el %ROC de cada año es el del holder."""
    for cache in (logic._ROC19A_CACHE, logic._ROCICI_CACHE):
        monkeypatch.setitem(cache, "_loaded", True)
        monkeypatch.setitem(cache, "data", {})


def _hist(filas):
    return pd.DataFrame(filas, columns=["Date", "Action", "Ticker", "Amount"])


def _stats(h, roc, bruto):
    return {
        "withheld_tax_total": logic.withheld_tax_total(h), "roc_percent": roc, "roc_source": "19a",
        "total_dividends": bruto, "dividends_gross_total": float(bruto),
        "dividends_gross_by_year": logic._csv_dividends_by_year(h),
        "withheld_by_year": logic.withheld_tax_total_by_year(h),
        "tax_refund_observed_by_year": logic.observed_tax_refund_by_year(h),
        "withheld_at_payment_by_year": logic.withheld_at_payment_by_year(h), "history": h,
    }


def _resumen(h, roc, bruto):
    return logic.build_tax_summary(_stats(h, roc, bruto), "ZZZY", base_rate_pct=30.0, country="Colombia")


# ── H1: la retención de un año no se mide contra el bruto de todos ─────────────────────

def test_retencion_de_un_solo_ano_se_mide_contra_el_bruto_de_ese_ano(sin_avisos):
    """$1.000 en 2024 sin retención y $1.000 en 2025 con $300 retenidos, ROC 50 %. La
    retención justa de 2025 es 30 % × 1.000 × 0,5 = 150 y vuelven 150. Con el bruto de los
    dos años salía justa 300 y devolución 0."""
    ts = _resumen(_hist([("2024-06-10", "Cash Dividend", "ZZZY", 1000),
                         ("2025-06-10", "Cash Dividend", "ZZZY", 1000),
                         ("2025-06-10", "NRA Tax Adj", "ZZZY", -300)]), 50.0, 2000)
    assert ts["fair_withholding"] == pytest.approx(150.0)
    assert ts["refund_total_estimated"] == pytest.approx(150.0)
    assert ts["refund_estimated"] == pytest.approx(150.0)
    assert ts["net_estimated"] == pytest.approx(150.0)
    assert ts["by_year"] is True


def test_un_solo_ano_de_bruto_sigue_por_el_agregado(sin_avisos):
    """Sin bruto fuera del año retenido no hay nada que separar: misma cifra, rama agregada."""
    ts = _resumen(_hist([("2025-06-10", "Cash Dividend", "ZZZY", 1000),
                         ("2025-06-10", "NRA Tax Adj", "ZZZY", -300)]), 50.0, 1000)
    assert ts["fair_withholding"] == pytest.approx(150.0)
    assert ts["refund_total_estimated"] == pytest.approx(150.0)
    assert ts["by_year"] is False


# ── H2: retención devuelta por completo ────────────────────────────────────────────────

def test_retencion_ya_devuelta_no_se_borra_del_resumen(sin_avisos):
    """Se retuvieron $300 y el bróker devolvió los $300 en febrero. El saldo es cero, pero
    el resumen decía «No hay retención NRA registrada» y publicaba lo devuelto como 0."""
    ts = _resumen(_hist([("2025-06-10", "Cash Dividend", "ZZZY", 1000),
                         ("2025-06-10", "NRA Tax Adj", "ZZZY", -300),
                         ("2026-02-15", "NRA Tax Adj", "ZZZY", 300)]), 100.0, 1000)
    assert ts["withheld_real"] == 0.0
    assert ts["withheld_at_payment"] == pytest.approx(300.0)
    assert ts["refund_observed"] == pytest.approx(300.0)
    assert ts["refund_estimated"] == 0.0 and ts["net_estimated"] == 0.0
    assert "ya fue devuelta" in ts["label_long"]


def test_sin_ninguna_retencion_sigue_diciendo_que_no_hay(sin_avisos):
    ts = _resumen(_hist([("2025-06-10", "Cash Dividend", "ZZZY", 1000)]), 50.0, 1000)
    assert ts["withheld_at_payment"] is None
    assert ts["label_long"] == "No hay retención NRA registrada para este fondo."


# ── H4: la retención por año cuadra con el total ───────────────────────────────────────

def test_retencion_por_ano_suma_el_total_y_cumple_la_identidad_del_contrato():
    """2025: −300. 2026: −30 y un reembolso de +75 (del año anterior). Total 255. Por año,
    300 y −45; al cobro 300 y 30; devuelto 0 y 75: `al cobro == neteado + devuelto`."""
    h = _hist([("2025-06-10", "Cash Dividend", "ZZZY", 1000), ("2025-06-10", "NRA Tax Adj", "ZZZY", -300),
               ("2026-01-10", "Cash Dividend", "ZZZY", 100), ("2026-01-10", "NRA Tax Adj", "ZZZY", -30),
               ("2026-02-15", "NRA Tax Adj", "ZZZY", 75)])
    por_ano = logic.withheld_tax_total_by_year(h)
    assert por_ano == {2025: 300.0, 2026: -45.0}
    assert sum(por_ano.values()) == pytest.approx(logic.withheld_tax_total(h)) == pytest.approx(255.0)
    al_cobro, devuelto = logic.withheld_at_payment_by_year(h), logic.observed_tax_refund_by_year(h)
    for ano in (2025, 2026):
        assert al_cobro.get(ano, 0.0) == pytest.approx(por_ano[ano] + devuelto.get(ano, 0.0))
    t = logic.build_dividend_tax_totals(h)
    assert t["net"] == pytest.approx(845.0)
    assert t["net_by_year"] == {2025: pytest.approx(700.0), 2026: pytest.approx(145.0)}


# ── H5: el ROC publicado no pasa del 100 % ─────────────────────────────────────────────

def test_roc_mayor_que_el_bruto_se_publica_como_cien(sin_avisos):
    h = _hist([("2025-06-10", "Cash Dividend", "ZZZY", 1000), ("2025-06-10", "NRA Tax Adj", "ZZZY", -300)])
    ts = _resumen(h, 111.11, 1000)
    assert ts["roc_pct_used"] == 100.0
    assert ts["refund_total_estimated"] == pytest.approx(300.0)
    sin_pais = logic.build_tax_summary(_stats(h, 111.11, 1000), "ZZZY", base_rate_pct=logic.RATE_UNDECLARED)
    assert sin_pais["roc_pct_used"] == 100.0


def test_cierre_fiscal_fuera_de_rango_no_se_publica_tal_cual(sin_avisos, monkeypatch):
    monkeypatch.setitem(logic._ROCICI_CACHE, "data", {"ZZZY": {2025: {"roc_pct": 150.0}}})
    ano = logic.estimate_roc_refund_by_year({2025: 1000.0}, {2025: 300.0}, "ZZZY")[2025]
    assert ano["roc_pct_usado"] == 100.0 and ano["roc_fuente"] == "cierre"
    assert ano["refund"] == pytest.approx(300.0)


# ── H6: una reversa no es el último pago ───────────────────────────────────────────────

def _seis_pagos(extra):
    return _hist([(f"2026-0{m}-10", "Cash Dividend", "ZZZY", 100.0) for m in range(1, 7)] + extra)


def test_rendimiento_a_futuro_ignora_un_ultimo_dia_de_reversa():
    """Seis pagos de $100 y una reversa de −$60 al final, sobre $5.000: el último pago es
    100 y a 12 al año da 24 %. Anualizar la reversa daba −14,4 %. Lo cobrado en el año sí
    la descuenta: 540 / 5.000 = 10,8 %."""
    r = logic.forward_realized_yield(_seis_pagos([("2026-07-10", "Cash Dividend", "ZZZY", -60.0)]),
                                     5000.0, today="2026-07-20")
    assert r["last_payment"] == pytest.approx(100.0)
    assert r["forward_yield"] == pytest.approx(24.0)
    assert r["payments_per_year"] == 12
    assert r["realized_yield"] == pytest.approx(10.8)
    assert r["stale"] is False


def test_reversa_vieja_no_tapa_que_la_posicion_dejo_de_pagar():
    """La antigüedad se mide desde el último PAGO (10-jun), no desde la reversa (10-sep)."""
    r = logic.forward_realized_yield(_seis_pagos([("2026-09-10", "Cash Dividend", "ZZZY", -60.0)]),
                                     5000.0, today="2026-09-20")
    assert r["stale"] is True and r["forward_yield"] is None


def test_solo_reversas_no_da_rendimiento_a_futuro():
    r = logic.forward_realized_yield(_hist([("2026-07-10", "Cash Dividend", "ZZZY", -60.0)]),
                                     5000.0, today="2026-07-20")
    assert r["last_payment"] is None and r["forward_yield"] is None


def test_las_reversas_no_cuentan_para_el_ritmo_de_pagos():
    """Tres pagos mensuales de $100 y, diez días después de cada uno, una reversa de −$10.
    Entre pagos hay 31 y 28 días: 12 al año, 100 × 12 / 5.000 = 24 %. Contando las reversas
    como pagos el intervalo típico bajaba a 10 días y salían 36 al año."""
    filas = []
    for dia in ("2026-01-10", "2026-02-10", "2026-03-10"):
        filas.append((dia, "Cash Dividend", "ZZZY", 100.0))
        filas.append((dia[:8] + "20", "Cash Dividend", "ZZZY", -10.0))
    r = logic.forward_realized_yield(_hist(filas), 5000.0, today="2026-03-25")
    assert r["payments_per_year"] == 12
    assert r["forward_yield"] == pytest.approx(24.0)
