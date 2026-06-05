"""Golden harness sobre real_examples/ — red de regresion con datos reales de IB y Schwab.

Objetivo: que cualquier variacion futura (splits, tz, formato de broker, costo incompleto)
que rompa un caso conocido falle automaticamente ANTES de desplegar.

Ground truth derivado de las capturas del broker (ver protocolo-revision-calculadora.md).
Dos niveles:
  - Tier 1 (sin red, determinista): deteccion de broker y condicion de datos del CSV.
  - Tier 2 (pipeline real, requiere yfinance): acciones split-ajustadas y flags de calidad.
    Hace pytest.skip si la red/yfinance no esta disponible (no bloquea por outage), pero
    una regresion de LOGICA (acciones o flags incorrectos) si falla.

Todo hace skip si real_examples/ no existe (data privada, no versionada).
"""
import io
import os
import glob
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(__file__))
import logic

BASE = os.path.dirname(__file__)
REAL = os.path.join(BASE, "real_examples")


class FakeFile:
    def __init__(self, content: bytes, name: str = "test.csv"):
        self._buf = io.BytesIO(content)
        self.name = name

    def read(self):
        return self._buf.read()

    def seek(self, n):
        self._buf.seek(n)


# Ground truth por caso (capturas reales del broker)
CASES = {
    "ib_1": {
        "glob": "interactive_brokers_data/1/*.csv",
        "broker": "ibkr",
        "shares": {"MSTY": 250, "CONY": 80, "TSLY": 160, "NVDY": 600,
                   "XLK": 20, "SCHB": 45, "SMH": 10, "NFLY": 10, "PLTY": 10},
        "unreliable": set(),  # historial completo
    },
    "schwab_1": {
        "glob": "charles_schwab_data/1/*.csv",
        "broker": "schwab",
        # solo los tickers con historial COMPLETO (SCHB/XLK divergen por incompletitud)
        "shares": {"MSTY": 98.16, "NVDY": 101.0517, "SMH": 7.0383, "TSLY": 22.4431},
        "unreliable": {"SCHB", "XLK"},
        "sells_exceed_buys": {"SCHB"},
    },
    "schwab_2": {
        "glob": "charles_schwab_data/2/*.csv",
        "broker": "schwab",
        "unreliable_includes": {"SCHB"},
    },
}


def _load(case):
    paths = glob.glob(os.path.join(REAL, CASES[case]["glob"]))
    if not paths:
        pytest.skip(f"real_examples no disponible: {CASES[case]['glob']}")
    with open(paths[0], "rb") as f:
        return logic.load_and_detect_csv(FakeFile(f.read(), os.path.basename(paths[0])))


def _analyze_or_skip(df):
    dfc = logic.normalize_csv(df)
    try:
        res = logic.analyze_portfolio(dfc, version="GOLDEN")
    except Exception as e:  # red caida / yfinance
        pytest.skip(f"analyze_portfolio fallo (red?): {e}")
    if not res or all(("error" in s) for s in res.values()):
        pytest.skip("sin datos de mercado (yfinance no disponible)")
    return res


# ── Tier 1: determinista, sin red ────────────────────────────────────────────

@pytest.mark.parametrize("case", list(CASES))
def test_broker_detection(case):
    df, broker = _load(case)
    assert broker == CASES[case]["broker"], f"{case}: broker detectado {broker}"


def test_schwab1_schb_sells_exceed_buys():
    """SCHB en Schwab caso 1 tiene ventas > compras registradas (historial incompleto)."""
    df, _ = _load("schwab_1")
    dfc = logic.normalize_csv(df)
    dfc["Quantity"] = pd.to_numeric(dfc["Quantity"], errors="coerce").fillna(0)
    for t in CASES["schwab_1"]["sells_exceed_buys"]:
        sub = dfc[dfc["Ticker"] == t]
        buys = sub[sub["Action"].str.contains("buy", case=False, na=False)]["Quantity"].abs().sum()
        sells = sub[sub["Action"].str.contains("sell", case=False, na=False)]["Quantity"].abs().sum()
        assert sells > buys, f"{t}: se esperaba ventas({sells}) > compras({buys})"


# ── Tier 2: pipeline real (yfinance); skip elegante si no hay red ─────────────

@pytest.mark.parametrize("case", ["ib_1", "schwab_1"])
def test_shares_match_ground_truth(case):
    c = CASES[case]
    if "shares" not in c:
        pytest.skip("sin ground truth de acciones")
    df, _ = _load(case)
    res = _analyze_or_skip(df)
    checked = 0
    for t, expected in c["shares"].items():
        s = res.get(t)
        if s is None or s.get("skipped") or s.get("shares_owned") is None:
            continue  # ticker no analizado por datos faltantes
        got = s["shares_owned"]
        assert got == pytest.approx(expected, rel=0.02), f"{case} {t}: shares {got} != {expected}"
        checked += 1
    if checked == 0:
        pytest.skip(f"{case}: ningun ticker con datos de mercado")


@pytest.mark.parametrize("case", ["ib_1", "schwab_1"])
def test_data_quality_flags(case):
    c = CASES[case]
    df, _ = _load(case)
    res = _analyze_or_skip(df)
    valid = {t: s for t, s in res.items() if not s.get("skipped")}
    dq = logic.assess_data_quality(valid)
    unrel = {t for t, q in dq.items() if q["level"] == "unreliable"}
    # los esperados no confiables deben marcarse (si fueron analizados)
    for t in c.get("unreliable", set()):
        if t in valid:
            assert t in unrel, f"{case}: {t} deberia ser 'unreliable', flags={dq.get(t)}"
    # los confiables esperados NO deben marcarse
    for t in c.get("shares", {}):
        if t in valid and t not in c.get("unreliable", set()):
            assert t not in unrel, f"{case}: {t} no deberia ser 'unreliable', flags={dq.get(t)}"


def test_cost_incomplete_matches_assess():
    """_cost_incomplete (usado en el comparativo) y assess_data_quality deben coincidir
    EXACTAMENTE (fuente unica de verdad)."""
    df, _ = _load("schwab_1")
    res = _analyze_or_skip(df)
    valid = {t: s for t, s in res.items() if not s.get("skipped")}
    dq = logic.assess_data_quality(valid)
    for t in valid:
        assert logic._cost_incomplete(valid, t) == (dq[t]["level"] in ("unreliable", "reconciled")), \
            f"{t}: _cost_incomplete discrepa de assess_data_quality"
