"""Tests de la captura de casos de estudio — Tier 1, deterministas, sin red.

El foco es la garantía de privacidad: que anonymize_to_min_rows NUNCA deje pasar
columnas de identidad, y que el bundle sea PII-free por construcción.
"""
import io
import os
import glob
import json
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(__file__))
import logic

BASE = os.path.dirname(__file__)
REAL = os.path.join(BASE, "real_examples")


class _Fake:
    def __init__(self, content: bytes, name: str = "t.csv"):
        self._buf = io.BytesIO(content)
        self.name = name

    def read(self):
        return self._buf.read()

    def seek(self, n):
        self._buf.seek(n)


def _df_with_pii():
    return pd.DataFrame({
        "Date": ["2026-01-02", "2026-02-03"],
        "Action": ["Buy", "Sell"],
        "Ticker": ["msty", " MSTY "],
        "Quantity": [10, -5],
        "Price": [20.0, 22.0],
        "Amount": [-200.0, 110.0],
        "Account Number": ["U15179613", "U15179613"],
        "Holder Name": ["Daniel Zambrano", "Daniel Zambrano"],
        "Description": ["DIV PAGADO A JOHN DOE", "VENTA"],
        "Address": ["Calle 123, Bogota", "Calle 123, Bogota"],
    })


def test_anonymize_whitelist_only():
    mn = logic.anonymize_to_min_rows(_df_with_pii())
    assert set(mn.columns) <= set(logic.CAPTURE_MIN_COLUMNS)
    for leaked in ("Account Number", "Holder Name", "Description", "Address"):
        assert leaked not in mn.columns


def test_anonymize_no_pii_in_serialized_csv():
    csv = logic.anonymize_to_min_rows(_df_with_pii()).to_csv(index=False)
    for pii in ("U15179613", "Daniel", "Zambrano", "JOHN DOE", "Bogota", "Calle 123"):
        assert pii not in csv, f"fuga de PII: {pii}"


def test_anonymize_normalizes_ticker_and_date():
    mn = logic.anonymize_to_min_rows(_df_with_pii())
    assert list(mn["Ticker"]) == ["MSTY", "MSTY"]
    assert list(mn["Date"]) == ["2026-01-02", "2026-02-03"]


def test_build_bundle_is_pii_free():
    df = _df_with_pii()
    overrides = {"MSTY": {"cost_basis": 23500.5, "shares": 250.0},
                 "NVDY": {"cost_basis": 12000, "shares": 600}}
    quality = {"MSTY": {"level": "ok", "flags": [], "coverage_pct": 100.0},
               "NVDY": {"level": "ok", "flags": [], "coverage_pct": 95.0}}
    gemini = {"MSTY": {"cost_basis": 23500.5, "shares": 250, "market_value": 28750}}
    b = logic.build_capture_bundle(df, "ibkr", overrides, quality, gemini, app_version="2.8")

    assert set(b) >= {"case_id", "broker", "transactions_min_csv", "ground_truth",
                      "quality", "gemini_raw", "meta"}
    assert b["broker"] == "ibkr"
    assert b["meta"]["broker"] == "ibkr" and b["meta"]["case_id"] == b["case_id"]
    assert b["ground_truth"]["MSTY"] == {"cost_basis": 23500.5, "shares": 250.0}
    header = b["transactions_min_csv"].splitlines()[0].split(",")
    assert set(header) <= set(logic.CAPTURE_MIN_COLUMNS)
    blob = json.dumps(b, default=str)
    for pii in ("Daniel", "Zambrano", "U15179613", "JOHN DOE", "Bogota"):
        assert pii not in blob, f"fuga de PII en bundle: {pii}"


def test_capture_worthy_gate():
    q_ok = {"A": {"level": "ok"}, "B": {"level": "ok"}}
    ov = {"A": {"cost_basis": 100, "shares": 5}}
    assert logic.is_capture_worthy(q_ok, ov)[0] is True
    # sin overrides -> no
    assert logic.is_capture_worthy(q_ok, {})[0] is False
    # solo 1 'ok' -> no
    assert logic.is_capture_worthy({"A": {"level": "ok"}, "B": {"level": "unreliable"}}, ov)[0] is False
    # overrides sin costo/acciones -> no
    assert logic.is_capture_worthy(q_ok, {"A": {"cost_basis": 0, "shares": 0}})[0] is False


@pytest.mark.parametrize("glob_pat,broker", [
    ("interactive_brokers_data/1/*.csv", "ibkr"),
    ("charles_schwab_data/1/*.csv", "schwab"),
])
def test_real_examples_no_leak(glob_pat, broker):
    """Sobre CSVs reales: tras normalizar + anonimizar, solo quedan columnas whitelist."""
    paths = glob.glob(os.path.join(REAL, glob_pat))
    if not paths:
        pytest.skip(f"real_examples no disponible: {glob_pat}")
    with open(paths[0], "rb") as f:
        df, _ = logic.load_and_detect_csv(_Fake(f.read(), os.path.basename(paths[0])))
    dfc = logic.normalize_csv(df)
    mn = logic.anonymize_to_min_rows(dfc)
    assert set(mn.columns) <= set(logic.CAPTURE_MIN_COLUMNS)
    assert len(mn) > 0
