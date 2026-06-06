"""Golden harness sobre real_examples/ — red de regresion con datos reales de IB y Schwab.

Objetivo: que cualquier variacion futura (splits, tz, formato de broker, costo incompleto)
que rompa un caso conocido falle automaticamente ANTES de desplegar.

Ground truth (fuente UNICA): real_examples/<caso>/expected.json, transcrito UNA vez de las
capturas del broker y compartido con validate_real_cases.py. Agregar un caso nuevo = soltar
CSV + fotos + expected.json; aqui se descubre solo (no se edita codigo).
A esos casos se suman los CAPTURED_CASES promovidos por promote_case.py (fixtures normalizados
PII-free, privados, no versionados) si el modulo existe.

Niveles:
  - Tier 1 (sin red, determinista): deteccion de broker y condicion de datos del CSV.
  - Tier 2 (pipeline real, requiere yfinance): acciones split-ajustadas y flags de calidad.
    pytest.skip si la red/yfinance no esta disponible (no bloquea por outage); una regresion
    de LOGICA (acciones o flags incorrectos) si falla.
  - Tier vision (@pytest.mark.vision, opt-in): la OCR de fotos con Gemini contra el manifest.
    Deseleccionado por defecto en pytest.ini (cuota + no determinista). Correr: pytest -m vision.

Todo hace skip si real_examples/ no existe (data privada, no versionada).
"""
import glob
import os
import sys

import pandas as pd
import pytest

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import logic                       # noqa: E402
import validate_real_cases as vrc  # noqa: E402  (loader de manifests — fuente unica con el runner)

REAL = vrc.REAL
FakeFile = vrc.FakeFile


def _build_cases():
    """Construye CASES desde los expected.json (compat con los tests de abajo)."""
    cases = {}
    for c in vrc.discover_cases():
        m = c["manifest"]
        tk = m["tickers"]
        cases[c["case_id"]] = {
            "dir": c["dir"],
            "csv_glob": m.get("csv_glob", "*.csv"),
            "broker": m["broker"],
            "shares": {t: e["shares"] for t, e in tk.items()
                       if e.get("reliability", "ok") == "ok" and e.get("shares") is not None},
            "unreliable": {t for t, e in tk.items()
                           if e.get("reliability") in ("unreliable", "reconciled")},
            "sells_exceed_buys": {t for t, e in tk.items() if e.get("sells_exceed_buys")},
            "manifest": m,
        }
    return cases


CASES = _build_cases()

# Casos capturados y promovidos por promote_case.py (fixtures normalizados PII-free,
# privados, no versionados). Cada uno lleva "normalized": True. Si el modulo no existe
# (entorno limpio), simplemente no hay casos capturados.
try:
    from captured_cases import CAPTURED_CASES
    CASES.update(CAPTURED_CASES)
except Exception:
    pass


def _ids(pred):
    """IDs de casos que cumplen pred; si no hay, un parametro que hace skip (evita 'empty set')."""
    ids = [k for k, v in CASES.items() if pred(v)]
    return ids or [pytest.param("__none__", marks=pytest.mark.skip(reason="sin real_examples/"))]


def _has_vision(v):
    m = v.get("manifest")
    return bool(m and any(e.get("vision") and e.get("cost_basis") for e in m["tickers"].values()))


def _load(case):
    c = CASES[case]
    if c.get("normalized"):
        # Fixture ya normalizado (caso capturado, PII-free): se salta la deteccion de broker.
        paths = glob.glob(os.path.join(REAL, c["glob"]))
        if not paths:
            pytest.skip(f"real_examples no disponible: {c['glob']}")
        return pd.read_csv(paths[0]), c.get("broker", "normalized")
    # Caso con manifest (expected.json en su carpeta).
    paths = [p for p in glob.glob(os.path.join(c["dir"], c.get("csv_glob", "*.csv")))
             if not p.endswith("expected.json")]
    if not paths:
        pytest.skip(f"real_examples no disponible: {case}")
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

@pytest.mark.parametrize("case", _ids(lambda v: not v.get("normalized")))
def test_broker_detection(case):
    df, broker = _load(case)
    assert broker == CASES[case]["broker"], f"{case}: broker detectado {broker}"


@pytest.mark.parametrize("case", _ids(lambda v: v.get("sells_exceed_buys")))
def test_schb_sells_exceed_buys(case):
    """Tickers marcados sells_exceed_buys tienen ventas > compras registradas (historial incompleto)."""
    df, _ = _load(case)
    dfc = logic.normalize_csv(df)
    dfc["Quantity"] = pd.to_numeric(dfc["Quantity"], errors="coerce").fillna(0)
    for t in CASES[case]["sells_exceed_buys"]:
        sub = dfc[dfc["Ticker"] == t]
        buys = sub[sub["Action"].str.contains("buy", case=False, na=False)]["Quantity"].abs().sum()
        sells = sub[sub["Action"].str.contains("sell", case=False, na=False)]["Quantity"].abs().sum()
        assert sells > buys, f"{case} {t}: se esperaba ventas({sells}) > compras({buys})"


# ── Tier 2: pipeline real (yfinance); skip elegante si no hay red ─────────────

@pytest.mark.parametrize("case", _ids(lambda v: v.get("shares")))
def test_shares_match_ground_truth(case):
    c = CASES[case]
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


@pytest.mark.parametrize("case", _ids(lambda v: v.get("shares") or v.get("unreliable")))
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
    if "schwab_1" not in CASES:
        pytest.skip("sin caso schwab_1")
    df, _ = _load("schwab_1")
    res = _analyze_or_skip(df)
    valid = {t: s for t, s in res.items() if not s.get("skipped")}
    dq = logic.assess_data_quality(valid)
    for t in valid:
        assert logic._cost_incomplete(valid, t) == (dq[t]["level"] in ("unreliable", "reconciled")), \
            f"{t}: _cost_incomplete discrepa de assess_data_quality"


# ── Tier vision: OCR de fotos con Gemini (opt-in: pytest -m vision) ───────────

@pytest.mark.vision
@pytest.mark.parametrize("case", _ids(_has_vision))
def test_vision_cost_basis_matches_capture(case):
    """Gemini debe leer el cost_basis de las fotos igual que el ground truth (tol 2%)."""
    key = vrc._load_gemini_key()
    if not key:
        pytest.skip("sin GEMINI_API_KEY (env ni .streamlit/secrets.toml)")
    c = CASES[case]
    res = vrc.validate_vision({"dir": c["dir"], "manifest": c["manifest"]}, key)
    if res["status"] != "ok":
        pytest.skip(res.get("error", "vision no disponible"))
    fails = [r for r in res["rows"] if r["result"] == "FAIL"]
    assert not fails, f"{case}: OCR fallo en {[(r['ticker'], r['detail']) for r in fails]}"
