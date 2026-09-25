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
    assert b["ground_truth"]["MSTY"] == {"cost_basis": 23500.5, "shares": 250.0,
                                         "origen_shares": None, "origen_cost_basis": None}
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


# ── Fase 1 (2026-09-25): fidelidad del fixture, procedencia y fecha ─────────────

_REAL_CASES = [
    ("interactive_brokers_data/1/*.csv", "ibkr"),
    ("charles_schwab_data/1/*.csv", "schwab"),
    ("charles_schwab_data/2/indiv_transactions.csv", "schwab"),
    ("charles_schwab_data/daniel_zambrano/*.csv", "schwab"),
]


def _con_filas(df, filas):
    extra = pd.DataFrame(filas, columns=df.columns).astype(object)
    return pd.concat([df.astype(object), extra], ignore_index=True)


def _load_real(glob_pat):
    paths = glob.glob(os.path.join(REAL, glob_pat))
    if not paths:
        pytest.skip(f"real_examples no disponible: {glob_pat}")
    with open(paths[0], "rb") as f:
        df, _ = logic.load_and_detect_csv(_Fake(f.read(), os.path.basename(paths[0])))
    return logic.normalize_csv(df), os.path.basename(paths[0])


def _ida_y_vuelta(dfc):
    csv = logic.anonymize_to_min_rows(dfc).to_csv(index=False)
    return logic.normalize_csv(logic.load_capture_fixture(io.StringIO(csv)))


def test_filas_sin_ticker_se_conservan_vacias():
    df = _con_filas(_df_with_pii(), [
        ["2026-03-01", "NRA Tax Adj", None, None, None, -3.3, "U15179613", "Daniel Zambrano", "x", "y"],
        ["2026-03-02", "Cash Dividend", "", None, None, 12.0, "U15179613", "Daniel Zambrano", "x", "y"]])
    mn = logic.anonymize_to_min_rows(df)
    assert len(mn) == 4
    assert list(mn["Ticker"]) == ["MSTY", "MSTY", "", ""]
    back = logic.load_capture_fixture(io.StringIO(mn.to_csv(index=False)))
    assert list(back["Ticker"]) == ["MSTY", "MSTY", "", ""]
    assert back["Amount"].tolist() == [-200.0, 110.0, -3.3, 12.0]


def test_loader_no_convierte_ticker_na_en_nan():
    back = logic.load_capture_fixture(io.StringIO(
        "Date,Action,Ticker,Quantity,Price,Amount\n2026-01-02,Buy,NA,1,2,-2\n"))
    assert back["Ticker"].tolist() == ["NA"]


@pytest.mark.parametrize("glob_pat,broker", _REAL_CASES)
def test_fixture_reproduce_los_totales_fiscales(glob_pat, broker):
    """El fixture anonimizado tiene que dar los MISMOS totales fiscales que el CSV
    completo. Con las filas sin ticker descartadas, schwab1 daba bruto $5,835.50 en vez
    de $6,646.08 (medido 2026-09-25): el caso capturado habría probado otra cosa."""
    dfc, _ = _load_real(glob_pat)
    mn2 = _ida_y_vuelta(dfc)
    a, b = logic.build_dividend_tax_totals(dfc), logic.build_dividend_tax_totals(mn2)
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str), \
        "build_dividend_tax_totals difiere entre CSV completo y fixture"
    assert logic.drip_huerfanas(dfc) == logic.drip_huerfanas(mn2)


@pytest.mark.parametrize("glob_pat,broker", _REAL_CASES)
def test_fixture_conserva_todas_las_filas_con_fecha(glob_pat, broker):
    dfc, _ = _load_real(glob_pat)
    con_fecha = int(pd.to_datetime(dfc["Date"], errors="coerce").notna().sum())
    assert len(_ida_y_vuelta(dfc)) == con_fecha


@pytest.mark.parametrize("glob_pat,broker", _REAL_CASES)
def test_bundle_real_sin_numero_de_cuenta(glob_pat, broker):
    """Ni el nombre del archivo ni un número de cuenta llegan al bundle. El archivo de IB
    se llama como la cuenta (U + 7-8 dígitos) y el de Schwab lleva XXX + 3 dígitos."""
    import re
    dfc, nombre = _load_real(glob_pat)
    b = logic.build_capture_bundle(dfc, broker, {}, {})
    blob = json.dumps(b, default=str)
    assert nombre not in blob
    assert os.path.splitext(nombre)[0] not in blob
    assert not re.search(r"\bU\d{7,8}\b", blob), "patrón de cuenta IB en el bundle"
    assert not re.search(r"XXX\d{3}", blob), "patrón de cuenta Schwab en el bundle"


def test_bundle_no_acepta_nombre_de_archivo():
    import inspect
    params = set(inspect.signature(logic.build_capture_bundle).parameters)
    prohibidos = {p for p in params if any(k in p.lower() for k in ("file", "archivo", "nombre", "name", "path"))}
    assert not prohibidos, f"build_capture_bundle no debe recibir el nombre del archivo: {prohibidos}"


def test_captured_at_solo_dia():
    import re
    b = logic.build_capture_bundle(_df_with_pii(), "ibkr", {}, {})
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", b["meta"]["captured_at"])


def test_origen_posiciones_replica_los_defectos_de_la_ui():
    ocr = {"MSTY": {"shares": 250.0, "cost_basis": 23500.5}, "NVDY": {"shares": 600.0, "cost_basis": 0}}
    previa = {"MSTY": {"shares": 240.0, "invested": 20000.0},
              "NVDY": {"shares": 590.0, "invested": 11000.0},
              "SCHB": {"shares": 10.0, "invested": 300.0},
              "XLK": {"shares": 5.0, "invested": 900.0}}
    confirmadas = {"MSTY": {"shares": 250.0, "cost_basis": 23500.5},
                   "NVDY": {"shares": 600.0, "cost_basis": 11000.0},
                   "SCHB": {"shares": 10.0, "cost_basis": 300.0},
                   "XLK": {"shares": 5.5, "cost_basis": 950.0}}
    o = logic.origen_posiciones(confirmadas, ocr, previa)
    assert o["MSTY"] == {"shares": "captura", "cost_basis": "captura"}
    assert o["NVDY"] == {"shares": "captura", "cost_basis": "vista_previa"}
    assert o["SCHB"] == {"shares": "vista_previa", "cost_basis": "vista_previa"}
    assert o["XLK"] == {"shares": "editado", "cost_basis": "editado"}


def test_bundle_guarda_origen_senales_y_1042s_sin_identificadores():
    df = _con_filas(_df_with_pii(),
                    [["2026-03-01", "Stock Split", "MSTY", 10, None, None, "U15179613", "D", "x", "y"]])
    ov = {"MSTY": {"shares": 250.0, "cost_basis": 100.0}}
    origen = logic.origen_posiciones(ov, {"MSTY": {"shares": 250.0}}, {})
    parsed = {"tax_year": 2025, "recipient_country_code": "CO", "source": "pdfplumber",
              "recipient_tin": "123456789", "recipient_name": "Daniel Zambrano",
              "forms": [{"unique_form_id": "0000123456", "income_code": "06",
                         "gross_income": 300.0, "federal_tax_withheld": 90.0,
                         "withholding_credit": 90.0, "tax_rate": 30.0, "conflict": False}]}
    b = logic.build_capture_bundle(df, "ibkr", ov, {"MSTY": {"level": "unreliable"}},
                                   origen=origen, form_1042s=parsed, pais="Colombia",
                                   bloqueos=["MSTY", "<script>"], indeterminados=["NVDY"])
    gt = b["ground_truth"]["MSTY"]
    assert gt["origen_shares"] == "captura" and gt["origen_cost_basis"] == "editado"
    sen = b["meta"]["senales"]
    assert sen["bloqueos_identidades"] == ["MSTY"]
    assert sen["indeterminados"] == ["NVDY"] and sen["unreliable"] == ["MSTY"]
    assert sen["n_splits"] == 1
    f = b["meta"]["form_1042s"]
    assert f["tax_year"] == 2025 and f["recipient_country_code"] == "CO"
    assert f["forms"] == [{"income_code": "06", "gross_income": 300.0, "federal_tax_withheld": 90.0,
                           "withholding_credit": 90.0, "tax_rate": 30.0}]
    assert b["meta"]["pais"] == "Colombia"
    blob = json.dumps(b, default=str)
    for pii in ("0000123456", "123456789", "Daniel", "U15179613"):
        assert pii not in blob, f"fuga en bundle: {pii}"


def test_promocion_excluye_la_vista_previa():
    import promote_case
    gt = {"A": {"shares": 10.0, "origen_shares": "captura"},
          "B": {"shares": 20.0, "origen_shares": "editado"},
          "C": {"shares": 30.0, "origen_shares": "vista_previa"},
          "D": {"shares": 40.0, "origen_shares": None},
          "E": {"shares": 50.0}}
    q = {t: {"level": "ok"} for t in gt}
    assert promote_case.promotable_shares(gt, q) == {"A": 10.0, "B": 20.0}


def test_harness_lee_los_fixtures_con_el_lector_unico(tmp_path, monkeypatch):
    """El harness tiene que leer el fixture igual que el test de fidelidad: con
    `pd.read_csv` a secas el ticker vacío vuelve a NaN y un ticker «NA» desaparece."""
    import test_real_examples as tre
    p = tmp_path / "transactions_min.csv"
    p.write_text("Date,Action,Ticker,Quantity,Price,Amount\n"
                 "2026-01-02,Buy,NA,1,2,-2\n2026-01-03,NRA Tax Adj,,,,-1\n")
    monkeypatch.setitem(tre.CASES, "cap_tmp", {"glob": str(p), "normalized": True, "broker": "schwab"})
    df, _ = tre._load("cap_tmp")
    assert df["Ticker"].tolist() == ["NA", ""]
