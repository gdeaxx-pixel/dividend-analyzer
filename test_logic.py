import io
import os
import re
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(__file__))
import logic


# ── Fixtures ──────────────────────────────────────────────────────────────────

class FakeFile:
    def __init__(self, content: bytes, name: str = "test.csv"):
        self._buf = io.BytesIO(content)
        self.name = name

    def read(self):
        return self._buf.read()

    def seek(self, n):
        self._buf.seek(n)


SCHWAB_CSV = (
    b'"Transactions for account XXXX-1234","","","","","","",""\n'
    b'"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"\n'
    b'"05/08/2026","Cash Dividend","SCHD","SCHWAB US DIVIDEND ETF","","","","75.00"\n'
    b'"05/01/2026","Buy","SCHD","SCHWAB US DIVIDEND ETF","10","27.50","","-275.00"\n'
    b'"Transactions Total","","","","","","","$-200.00"\n'
)

IB_TH_CSV = (
    b"Statement,Header,Field Name,Field Value\n"
    b"Statement,Data,Title,Transaction History\n"
    b"Transaction History,Header,Date,Account,Description,Transaction Type,Symbol,"
    b"Quantity,Price,Price Currency,Gross Amount,Commission,Net Amount\n"
    b'Transaction History,Data,2026-05-14,U123,"AAPL(US123) Cash Dividend USD 0.27",Dividend,AAPL,-,-,-,3.31,-,3.31\n'
    b'Transaction History,Data,2026-05-01,U123,"MSFT Regular Purchase",Buy,MSFT,5,420.00,USD,-2100.00,-1.0,-2101.00\n'
    b'Transaction History,Data,2026-04-15,U123,"TSLA Sale",Sell,TSLA,2,180.00,USD,360.00,-1.0,359.00\n'
    b'Transaction History,Data,2026-04-10,U123,Deposit,Deposit,,,,,5000.00,,5000.00\n'
)

IB_TH_COMMA_DESC = (
    b"Transaction History,Header,Date,Account,Description,Transaction Type,Symbol,"
    b"Quantity,Price,Price Currency,Gross Amount,Commission,Net Amount\n"
    b'Transaction History,Data,2026-01-15,U123,"MSFT, INC Cash Dividend USD 0.75",Dividend,MSFT,-,-,-,75.00,-,75.00\n'
    b'Transaction History,Data,2026-01-10,U123,"AAPL Buy, Regular",Buy,AAPL,10,150.00,USD,-1500.00,-1.0,-1501.00\n'
)

IB_TH_BOM = (
    b"\xef\xbb\xbf"
    b"Transaction History,Header,Date,Account,Description,Transaction Type,Symbol,"
    b"Quantity,Price,Price Currency,Gross Amount,Commission,Net Amount\n"
    b"Transaction History,Data,2026-01-15,U123,AAPL Dividend,Dividend,AAPL,-,-,-,3.00,-,3.00\n"
)

IB_ACTIVITY_STATEMENT = (
    b"Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,"
    b"Quantity,T. Price,Proceeds,Comm/Fee\n"
    b'Trades,Data,Order,Stocks,USD,MSFT,"2024-01-15, 09:30:00",10,420.00,4200.00,-1.0\n'
    b"Dividends,Header,Currency,Date,Description,Amount\n"
    b"Dividends,Data,USD,2024-01-20,MSFT(US123) Cash Dividend USD 0.75 per Share,75.00\n"
)


# ── detect_broker ──────────────────────────────────────────────────────────────

def test_detect_schwab():
    text = SCHWAB_CSV[:3000].decode("utf-8", errors="replace")
    assert logic.detect_broker(text) == "schwab"


def test_detect_ibkr_transaction_history():
    text = IB_TH_CSV[:3000].decode("utf-8", errors="replace")
    assert logic.detect_broker(text) == "ibkr"


def test_detect_ibkr_activity_statement():
    text = IB_ACTIVITY_STATEMENT[:3000].decode("utf-8", errors="replace")
    assert logic.detect_broker(text) == "ibkr"


def test_schwab_not_misdetected_when_body_contains_transaction_history():
    """Schwab file mentioning 'transaction history' in a description must still be 'schwab'."""
    csv = (
        b'"Transactions for account XXXX-9999","",""\n'
        b'"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"\n'
        b'"05/08/2026","Cash Dividend","VTI","See transaction history for details","","","","50.00"\n'
        b'"Transactions Total","","","","","","",""\n'
    )
    text = csv[:3000].decode("utf-8", errors="replace")
    assert logic.detect_broker(text) == "schwab"


# ── parse_ibkr_csv — Transaction History ──────────────────────────────────────

def test_ib_th_row_count():
    df, broker = logic.load_and_detect_csv(FakeFile(IB_TH_CSV))
    assert broker == "ibkr"
    assert len(df) == 3  # Deposit debe descartarse


def test_ib_th_actions():
    df, _ = logic.load_and_detect_csv(FakeFile(IB_TH_CSV))
    assert set(df["Action"].unique()) == {"Dividend", "Buy", "Sell"}


def test_ib_th_dividend_amount():
    df, _ = logic.load_and_detect_csv(FakeFile(IB_TH_CSV))
    div = df[df["Action"] == "Dividend"].iloc[0]
    assert div["Ticker"] == "AAPL"
    assert float(div["Amount"]) == pytest.approx(3.31)


def test_ib_th_buy_amount_negative():
    df, _ = logic.load_and_detect_csv(FakeFile(IB_TH_CSV))
    buy = df[df["Action"] == "Buy"].iloc[0]
    assert float(buy["Amount"]) < 0  # Dinero saliente


def test_ib_th_comma_in_description():
    """csv.reader debe manejar comas dentro de campos Description entrecomillados."""
    df, broker = logic.load_and_detect_csv(FakeFile(IB_TH_COMMA_DESC))
    assert broker == "ibkr"
    assert len(df) == 2
    assert "MSFT" in df["Ticker"].values
    assert "AAPL" in df["Ticker"].values


def test_ib_th_bom():
    """BOM UTF-8 al inicio no debe romper el match del header."""
    df, broker = logic.load_and_detect_csv(FakeFile(IB_TH_BOM))
    assert broker == "ibkr"
    assert len(df) == 1
    assert df.iloc[0]["Ticker"] == "AAPL"


# ── parse_ibkr_csv — Activity Statement ───────────────────────────────────────

def test_ib_activity_statement_parsed():
    df, broker = logic.load_and_detect_csv(FakeFile(IB_ACTIVITY_STATEMENT))
    assert broker == "ibkr"
    assert len(df) >= 1


def test_ib_activity_statement_dividend_present():
    df, _ = logic.load_and_detect_csv(FakeFile(IB_ACTIVITY_STATEMENT))
    if "Action" in df.columns:
        assert "Dividend" in df["Action"].values or len(df) > 0


# ── parse_schwab_csv ───────────────────────────────────────────────────────────

def test_schwab_parsed():
    df, broker = logic.load_and_detect_csv(FakeFile(SCHWAB_CSV))
    assert broker == "schwab"
    assert len(df) == 2


def test_schwab_columns_present():
    df, _ = logic.load_and_detect_csv(FakeFile(SCHWAB_CSV))
    assert "Symbol" in df.columns or "Ticker" in df.columns


# ── normalize_csv ─────────────────────────────────────────────────────────────

def test_normalize_ibkr_output():
    df, _ = logic.load_and_detect_csv(FakeFile(IB_TH_CSV))
    df_clean = logic.normalize_csv(df)
    assert len(df_clean) > 0
    for col in ["Date", "Action", "Ticker", "Amount"]:
        assert col in df_clean.columns, f"Columna '{col}' ausente después de normalize_csv"


def test_normalize_schwab_output():
    df, _ = logic.load_and_detect_csv(FakeFile(SCHWAB_CSV))
    df_clean = logic.normalize_csv(df)
    assert len(df_clean) > 0


def test_ib_sell_negative_qty_shares_counted_correctly():
    """
    IB Transaction History guarda sells con Quantity negativa (ej. -35).
    analyze_portfolio debe usar abs(qty) al restar → resultado correcto.
    Regresión: MSTY mostraba 1200 shares cuando el correcto era 1250
    (1285 compradas - 35 vendidas).
    """
    csv = (
        b"Transaction History,Header,Date,Account,Description,Transaction Type,"
        b"Symbol,Quantity,Price,Price Currency,Gross Amount,Commission,Net Amount\n"
        b"Transaction History,Data,2025-01-10,U123,Buy DEMO,Buy,DEMO,50,10.00,USD,-500.00,-1.0,-501.00\n"
        b"Transaction History,Data,2025-02-01,U123,Buy DEMO,Buy,DEMO,50,10.00,USD,-500.00,-1.0,-501.00\n"
        b"Transaction History,Data,2025-03-01,U123,Sell DEMO,Sell,DEMO,-20,12.00,USD,240.00,-1.0,239.00\n"
    )
    df, _ = logic.load_and_detect_csv(FakeFile(csv))
    df_clean = logic.normalize_csv(df)
    df_clean["Quantity"] = pd.to_numeric(df_clean["Quantity"], errors="coerce").fillna(0)

    buys  = df_clean[df_clean["Action"] == "Buy"]["Quantity"].sum()
    sells = df_clean[df_clean["Action"] == "Sell"]["Quantity"].sum()

    assert buys == pytest.approx(100.0), "Total comprado debe ser 100"
    assert sells == pytest.approx(-20.0), "IB guarda sells como negativos"

    # La cuenta correcta de shares: 100 - abs(-20) = 80
    net_shares = buys + sells  # 100 + (-20) = 80  (no restar, ya es negativo)
    assert net_shares == pytest.approx(80.0), "Shares netas deben ser 80 (100 - 20)"


def test_normalize_real_ib_file():
    """Valida el archivo IB real con FTW y Payment in Lieu incluidos (922 filas)."""
    base = os.path.dirname(__file__)
    real_path = os.path.join(base, "interactive_brokers_data",
                             "U15179613.TRANSACTIONS.20240820.20260514.csv")
    if not os.path.exists(real_path):
        pytest.skip("Archivo IB real no disponible")
    with open(real_path, "rb") as f:
        df, broker = logic.load_and_detect_csv(FakeFile(f.read(), "real_ib.csv"))
    assert broker == "ibkr"
    assert len(df) == 922
    # Foreign Tax Withholding deben estar presentes como Dividend con monto negativo
    ftw_rows = df[(df["Action"] == "Dividend") & (df["Amount"] < 0)]
    assert len(ftw_rows) > 0, "Foreign Tax Withholding debe generar filas con monto negativo"
    # Normalización TSLY.OLD → TSLY
    assert "TSLY.OLD" not in df["Ticker"].values, "TSLY.OLD debe normalizarse a TSLY"
    # 745 Dividend = dividendos ordinarios + FTW (negativo) + Payment in Lieu
    assert len(df[df["Action"] == "Dividend"]) == 745
    assert len(df[df["Action"] == "Buy"]) == 153
    df_clean = logic.normalize_csv(df)
    assert len(df_clean) > 0


# ── Regresión: correcciones negativas de dividendo IB ────────────────────────

def test_ib_negative_dividend_corrections_reduce_total(monkeypatch):
    """
    IB emite entradas de dividendo con Amount negativo para corregir pagos duplicados.
    analyze_portfolio debe RESTAR esas correcciones, no sumarlas.
    Regresión: abs(amount) inflaba MSTY en $1,863.76 (correcciones de ago-2025 y ene-2026).
    """
    csv = (
        b"Transaction History,Header,Date,Account,Description,Transaction Type,"
        b"Symbol,Quantity,Price,Price Currency,Gross Amount,Commission,Net Amount\n"
        # Dividendo real pagado
        b"Transaction History,Data,2025-08-01,U123,MSTY Dividend,Dividend,MSTY,-,-,-,414.23,-,414.23\n"
        # IB revierte el pago (error) → negativo
        b"Transaction History,Data,2025-08-01,U123,MSTY Dividend Correction,Dividend,MSTY,-,-,-,-414.23,-,-414.23\n"
        # Nuevo pago correcto
        b"Transaction History,Data,2025-08-02,U123,MSTY Dividend Corrected,Dividend,MSTY,-,-,-,410.00,-,410.00\n"
        # Compra para tener posición
        b"Transaction History,Data,2025-07-01,U123,Buy MSTY,Buy,MSTY,100,20.00,USD,-2000.00,-1.0,-2001.00\n"
    )
    df, _ = logic.load_and_detect_csv(FakeFile(csv))
    df_clean = logic.normalize_csv(df)

    def mock_fetch(ticker, start_date):
        data = pd.DataFrame(
            {"Close": [20.0], "Dividends": [0.0], "Stock Splits": [0.0], "VOO Price": [500.0]},
            index=[pd.Timestamp("2025-08-15")],
        )
        return data, None

    monkeypatch.setattr(logic, "fetch_market_data", mock_fetch)
    results = logic.analyze_portfolio(df_clean, version="TEST_DIV_NEG")

    assert "MSTY" in results
    div_cash = results["MSTY"]["dividends_collected_cash"]

    # Correcto: 414.23 - 414.23 + 410.00 = 410.00
    # Incorrecto (bug abs): 414.23 + 414.23 + 410.00 = 1238.46
    assert div_cash == pytest.approx(410.00, abs=0.01), (
        f"Dividendos deben ser $410.00 (corrección restada), no ${div_cash:.2f}"
    )


# ── Lógica de negocio existente (CONY ground truth) ───────────────────────────

def test_cony_portfolio_analysis(monkeypatch):
    csv_path = os.path.join(os.path.dirname(__file__), "CONY_test.csv")
    if not os.path.exists(csv_path):
        pytest.skip("CONY_test.csv no disponible")

    df = pd.read_csv(csv_path)
    df_clean = logic.normalize_csv(df)

    def mock_fetch(ticker, start_date):
        data = pd.DataFrame(
            {"Close": [31.434], "Dividends": [0.0], "Stock Splits": [0.0], "VOO Price": [450.0]},
            index=[pd.Timestamp("2026-03-15")],
        )
        return data, None

    monkeypatch.setattr(logic, "fetch_market_data", mock_fetch)
    results = logic.analyze_portfolio(df_clean, version="TEST_RUN")

    assert results, "analyze_portfolio devolvió vacío"
    stats = next(iter(results.values()))
    assert round(stats["pocket_investment"], 2) == 311.46


def test_roc_calculation_with_ib_cost_basis(monkeypatch):
    """ROC = (invertido + reinvertido) - ib_cost_basis; roc_percent = ROC / distribuciones * 100."""
    csv = (
        b"Transaction History,Header,Date,Account,Description,Transaction Type,Symbol,"
        b"Quantity,Price,Price Currency,Gross Amount,Commission,Net Amount\n"
        b"Transaction History,Data,2024-09-01,U123,MSTY Buy,Buy,MSTY,250,23.00,USD,-5750.00,-1.0,-5751.00\n"
        b"Transaction History,Data,2024-10-01,U123,MSTY Dividend,Dividend,MSTY,-,-,-,500.00,-,500.00\n"
    )
    df, _ = logic.load_and_detect_csv(FakeFile(csv))
    df_clean = logic.normalize_csv(df)

    def mock_fetch(ticker, start_date):
        data = pd.DataFrame(
            {"Close": [20.0], "Dividends": [0.0], "Stock Splits": [0.0]},
            index=[pd.Timestamp("2024-10-15")],
        )
        return data, None

    monkeypatch.setattr(logic, "fetch_market_data", mock_fetch)

    ib_basis = {"MSTY": "4298.17"}
    results = logic.analyze_portfolio(df_clean, version="TEST_ROC", ib_cost_basis_map=ib_basis)

    assert "MSTY" in results
    s = results["MSTY"]
    basis_in = s["pocket_investment"] + s["dividends_collected_drip"]   # sin DRIP aquí => == pocket
    assert s["ib_cost_basis"] == pytest.approx(4298.17, abs=0.01)
    assert s["roc_source"] == "broker"
    assert s["roc_accumulated"] == pytest.approx(basis_in - 4298.17, abs=0.01)
    assert s["roc_percent"] == pytest.approx((basis_in - 4298.17) / s["total_dividends"] * 100, abs=0.1)


def _roc_norm_df(rows):
    """DataFrame ya normalizado (Date/Action/Ticker/Quantity/Amount) para probar analyze_portfolio."""
    return pd.DataFrame([{"Date": pd.Timestamp(d), "Action": a, "Ticker": t, "Quantity": q, "Amount": amt}
                         for d, a, t, q, amt in rows])


_MKT_MOCK = lambda t, d: (pd.DataFrame({"Close": [20.0], "Dividends": [0.0], "Stock Splits": [0.0]},
                                       index=[pd.Timestamp("2024-10-15")]), None)


def test_roc_includes_reinvested_drip(monkeypatch):
    """El arreglo: el ROC suma lo reinvertido (DRIP). Con costo base = lo invertido en cash,
    la fórmula vieja daba ~0; la nueva da ROC = reinvertido."""
    df = _roc_norm_df([
        ("2024-09-01", "Buy", "MSTY", 100, -2000.0),
        ("2024-10-01", "Reinvest Shares", "MSTY", 10, -200.0),
    ])
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    results = logic.analyze_portfolio(df, version="TEST_ROC_DRIP",
                                      ib_cost_basis_map={"MSTY": "2000.00"})
    s = results["MSTY"]
    assert s["pocket_investment"] == pytest.approx(2000.0, abs=0.01)
    assert s["dividends_collected_drip"] == pytest.approx(200.0, abs=0.01)
    # (2000 + 200) - 2000 = 200  (la fórmula vieja pocket-base habría dado 0)
    assert s["roc_accumulated"] == pytest.approx(200.0, abs=0.01)
    assert s["roc_source"] == "broker"


def test_roc_estimated_from_19a_when_no_basis(monkeypatch):
    """Sin costo base del bróker, se estima el ROC con el % publicado por el fondo (19a),
    empatando por fecha. roc_source == '19a'."""
    df = _roc_norm_df([
        ("2024-09-01", "Buy", "MSTY", 100, -2000.0),
        ("2024-10-01", "Dividend", "MSTY", 0, 500.0),
    ])
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    # 19a controlado: el pago del 2024-10-01 fue 90% ROC
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {
        "MSTY": {"weighted_pct": 90.0, "per_distribution": [{"date": "2024-10-01", "roc_pct": 90.0}]}})
    results = logic.analyze_portfolio(df, version="TEST_ROC_19A")  # sin ib_cost_basis_map
    s = results["MSTY"]
    assert s.get("ib_cost_basis") is None
    assert s["roc_source"] == "19a"
    assert s["roc_accumulated"] == pytest.approx(450.0, abs=0.5)   # 500 * 90%
    assert s["roc_percent"] == pytest.approx(90.0, abs=0.5)


def test_deep_fix_keeps_real_cash_roc_via_19a(monkeypatch):
    """Arreglo profundo: en un fondo con ROC e historial completo, NO se pisa el costo real del CSV
    (Invertido/ROI usan tu efectivo) y el ROC se estima con el 19a, no con la resta (que el DRIP
    subestima cuando reinviertes)."""
    df = _roc_norm_df([
        ("2024-09-01", "Buy", "MSTY", 100, -2000.0),            # efectivo de tu bolsillo
        ("2024-10-01", "Reinvest Shares", "MSTY", 10, -200.0),  # DRIP (sube la base)
        ("2024-10-01", "Dividend", "MSTY", 0, 250.0),           # distribución (total_dividends>0)
    ])
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {
        "MSTY": {"weighted_pct": 75.0, "per_distribution": [{"date": "2024-10-01", "roc_pct": 75.0}]}})
    # El bróker reporta una base ya reducida por ROC ($1800), por debajo de pocket+drip=2200.
    res = logic.analyze_portfolio(
        df, version="TEST_DEEP_FIX",
        ib_cost_basis_map={"MSTY": "1800.00"},
        position_overrides={"MSTY": {"cost_basis": 1800.0}},
    )
    s = res["MSTY"]
    # Costo real conservado (NO reconciliado): Invertido = tu efectivo ($2000), no la base del bróker.
    assert s["pocket_investment"] == pytest.approx(2000.0, abs=0.01)
    assert "cost_basis" not in (s.get("reconciled_fields") or [])
    assert not s.get("reconciled_from_snapshot")
    assert s["ib_cost_basis"] == pytest.approx(1800.0, abs=0.01)
    # ROC vía 19a, NO por resta (la resta daría (2000+200)-1800 = 400).
    assert s["roc_source"] == "19a"
    assert s["roc_accumulated"] != pytest.approx(400.0, abs=1.0)


def test_roc_none_when_no_basis_provided(monkeypatch):
    """Sin ib_cost_basis_map los campos ROC son None."""
    csv = (
        b"Transaction History,Header,Date,Account,Description,Transaction Type,Symbol,"
        b"Quantity,Price,Price Currency,Gross Amount,Commission,Net Amount\n"
        b"Transaction History,Data,2024-09-01,U123,MSTY Buy,Buy,MSTY,250,23.00,USD,-5750.00,-1.0,-5751.00\n"
    )
    df, _ = logic.load_and_detect_csv(FakeFile(csv))
    df_clean = logic.normalize_csv(df)

    def mock_fetch(ticker, start_date):
        data = pd.DataFrame(
            {"Close": [20.0], "Dividends": [0.0], "Stock Splits": [0.0]},
            index=[pd.Timestamp("2024-10-15")],
        )
        return data, None

    monkeypatch.setattr(logic, "fetch_market_data", mock_fetch)
    results = logic.analyze_portfolio(df_clean, version="TEST_ROC_NONE")

    assert "MSTY" in results
    s = results["MSTY"]
    assert s.get("ib_cost_basis") is None
    assert s.get("roc_accumulated") is None
    assert s.get("roc_percent") is None


# ── Regresión: parsing numérico US vs Europeo (BUG clean_val) ───────────────

def _norm_amounts(values):
    df = pd.DataFrame({
        "Date": ["2025-01-01"] * len(values),
        "Action": ["Buy"] * len(values),
        "Ticker": ["X"] * len(values),
        "Quantity": ["1"] * len(values),
        "Price": ["1"] * len(values),
        "Amount": values,
    })
    return logic.normalize_csv(df.copy())["Amount"].tolist()


def test_clean_val_us_thousands_separator():
    """Formato US con coma de miles no debe dividirse por ~1000."""
    assert _norm_amounts(["12,500.00"]) == [12500.0]
    assert _norm_amounts(["1,234.56"]) == [1234.56]
    assert _norm_amounts(["1,000,000.00"]) == [1000000.0]


def test_clean_val_european_format_preserved():
    """El formato europeo (coma decimal, como el export de IB) sigue funcionando."""
    assert _norm_amounts(["12.500,00"]) == [12500.0]
    assert _norm_amounts(["0,155"]) == [0.155]
    assert _norm_amounts(["579,314"]) == [579.314]


def test_clean_val_plain_formats():
    assert _norm_amounts(["25.50"]) == [25.5]
    assert _norm_amounts(["300"]) == [300.0]


# ── Regresión: is_held_too_briefly con ventas negativas (IB) ────────────────

def test_held_too_briefly_ib_negative_sell():
    """IB exporta ventas con Quantity negativa; una posición cerrada en <14d
    debe detectarse como too_brief (antes net_shares se inflaba y nunca disparaba)."""
    ib = pd.DataFrame({
        "Date": pd.to_datetime(["2025-01-01", "2025-01-03"]),
        "Action": ["Buy", "Sell"],
        "Ticker": ["XYZ", "XYZ"],
        "Quantity": [100, -100],
    })
    brief, days = logic.is_held_too_briefly(ib)
    assert brief is True
    assert days == 2


def test_held_too_briefly_schwab_positive_sell_still_works():
    """Schwab (venta positiva) sigue funcionando igual."""
    sw = pd.DataFrame({
        "Date": pd.to_datetime(["2025-01-01", "2025-01-03"]),
        "Action": ["Buy", "Sell"],
        "Ticker": ["XYZ", "XYZ"],
        "Quantity": [100, 100],
    })
    brief, days = logic.is_held_too_briefly(sw)
    assert brief is True
    assert days == 2


def test_held_open_position_not_flagged():
    """Posición aún abierta (venta parcial) no debe marcarse como too_brief."""
    ib = pd.DataFrame({
        "Date": pd.to_datetime(["2025-01-01", "2025-01-03"]),
        "Action": ["Buy", "Sell"],
        "Ticker": ["XYZ", "XYZ"],
        "Quantity": [100, -40],
    })
    brief, days = logic.is_held_too_briefly(ib)
    assert brief is False


# ── build_portfolio_comparison_series ──────────────────────────────────────────

def _trend(dates, invested, value):
    return pd.DataFrame(
        {"Invested Capital": invested, "User Total Value": value},
        index=pd.to_datetime(dates),
    )


def test_portfolio_comparison_series_aggregates_two_blocks():
    """Agrega mode_a y mode_b en dos series; el último % cierra con el cálculo estático."""
    results = {
        # Dividendos (mode_a) — dos tickers con fechas distintas
        "TSLY": {"daily_trend": _trend(
            ["2025-01-01", "2025-01-02", "2025-01-03"], [1000, 1000, 1000], [900, 950, 1100])},
        "NVDY": {"daily_trend": _trend(
            ["2025-01-02", "2025-01-03"], [500, 500], [520, 600])},
        # Crecimiento (mode_b)
        "XLK": {"daily_trend": _trend(
            ["2025-01-01", "2025-01-02", "2025-01-03"], [2000, 2000, 2000], [2100, 2200, 2400])},
        "SCHB": {"daily_trend": _trend(
            ["2025-01-01", "2025-01-03"], [800, 800], [810, 850])},
    }
    classify_map = {"TSLY": "mode_a", "NVDY": "mode_a", "XLK": "mode_b", "SCHB": "mode_b"}

    df = logic.build_portfolio_comparison_series(results, classify_map)

    assert set(df["Portafolio"].unique()) == {"Dividendos", "Crecimiento"}

    for label in ("Dividendos", "Crecimiento"):
        sub = df[df["Portafolio"] == label]
        assert sub["Fecha"].is_monotonic_increasing, f"{label}: fechas desordenadas"

    # Último punto Dividendos: invested 1000+500=1500, value 1100+600=1700
    div_last = df[df["Portafolio"] == "Dividendos"].iloc[-1]
    assert div_last["Valor"] == pytest.approx(1700.0)
    assert div_last["Rendimiento"] == pytest.approx((1700 - 1500) / 1500 * 100)

    # Último punto Crecimiento: invested 2000+800=2800, value 2400+850=3250
    grw_last = df[df["Portafolio"] == "Crecimiento"].iloc[-1]
    assert grw_last["Valor"] == pytest.approx(3250.0)
    assert grw_last["Rendimiento"] == pytest.approx((3250 - 2800) / 2800 * 100)


def test_portfolio_comparison_series_handles_missing_block():
    """Si solo hay un bloque, devuelve solo esa serie (no rompe)."""
    results = {"TSLY": {"daily_trend": _trend(["2025-01-01"], [1000], [1100])}}
    df = logic.build_portfolio_comparison_series(results, {"TSLY": "mode_a"})
    assert set(df["Portafolio"].unique()) == {"Dividendos"}


def test_portfolio_comparison_series_skips_errored_tickers():
    """Tickers con error o sin daily_trend se ignoran sin romper."""
    results = {
        "TSLY": {"daily_trend": _trend(["2025-01-01"], [1000], [1100])},
        "BAD":  {"error": "no data"},
        "XLK":  {"daily_trend": _trend(["2025-01-01"], [2000], [2200])},
    }
    classify_map = {"TSLY": "mode_a", "BAD": "mode_a", "XLK": "mode_b"}
    df = logic.build_portfolio_comparison_series(results, classify_map)
    div_last = df[df["Portafolio"] == "Dividendos"].iloc[-1]
    assert div_last["Valor"] == pytest.approx(1100.0)


# ── Schwab: formato actual y migración TDA ──────────────────────────────────────

SCHWAB_NEW_CSV = (
    b'"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"\n'
    b'"05/13/2024","Journaled Shares","SCHB","TDA TRAN - TRANSFER OF SECURITY OR OPTION OUT (SCHB)","-18.933","","",""\n'
    b'"05/13/2024","Internal Transfer","SCHB","SCHWAB US BROAD MARKET ETF","18.933","","",""\n'
    b'"05/01/2024","Buy","SCHB","SCHWAB US BROAD MARKET ETF","10","27.50","","-275.00"\n'
)


def test_detect_schwab_new_format_no_metadata():
    """Export actual de Schwab: empieza con el header (sin 'Transactions for account').
    Se reconoce por 'Fees & Comm'. Regresión del bug detect_broker -> generic -> crash."""
    text = SCHWAB_NEW_CSV[:3000].decode("utf-8", errors="replace")
    assert logic.detect_broker(text) == "schwab"


def test_net_transfer_pairs_tda_migration():
    """Journaled OUT + Internal Transfer IN (mismo ticker/fecha/|qty|) son la misma
    migración TDA->Schwab; se elimina la pata OUT para no anular la entrada."""
    df = pd.DataFrame({
        "Date": pd.to_datetime(["2024-05-13", "2024-05-13", "2024-05-01"]),
        "Action": ["Journaled Shares", "Internal Transfer", "Buy"],
        "Ticker": ["SCHB", "SCHB", "SCHB"],
        "Quantity": [-18.933, 18.933, 10.0],
    })
    out = logic._net_transfer_pairs(df)
    assert len(out) == 2
    assert "Journaled Shares" not in out["Action"].values
    assert out[out["Action"] == "Internal Transfer"]["Quantity"].iloc[0] == pytest.approx(18.933)


def test_net_transfer_pairs_keeps_unpaired_journal_out():
    """Una 'Journaled Shares' OUT sin entrada gemela (salida real) se conserva."""
    df = pd.DataFrame({
        "Date": pd.to_datetime(["2024-05-13", "2024-05-01"]),
        "Action": ["Journaled Shares", "Buy"],
        "Ticker": ["SCHB", "SCHB"],
        "Quantity": [-5.0, 10.0],
    })
    out = logic._net_transfer_pairs(df)
    assert len(out) == 2
    assert (out["Action"] == "Journaled Shares").any()


# ── Sortino con downside deviation estándar ─────────────────────────────────────

def test_sortino_ratio_downside_deviation():
    """Sortino usa downside deviation sobre TODOS los períodos (no std de solo los
    negativos). Caso a mano: returns [0.01,-0.02,0.03,-0.01,0.005], rf=0:
    mean=0.003, downside=[0,-0.02,0,-0.01,0], dd=sqrt((0.0004+0.0001)/5)=0.01,
    sortino=(0.003/0.01)*sqrt(252)."""
    r = pd.Series([0.01, -0.02, 0.03, -0.01, 0.005])
    assert logic._sortino_ratio(r, 0.0) == pytest.approx(0.3 * (252 ** 0.5), rel=1e-4)


def test_sortino_ratio_guards():
    assert logic._sortino_ratio(pd.Series([0.01, 0.02, 0.03]), 0.0) is None  # sin caídas
    assert logic._sortino_ratio(pd.Series([0.01]), 0.0) is None              # <2 datos


# ── Reconciliación desde la captura del broker (límite de export ~3-4 años) ───

_RECON_CSV = (
    b"Transaction History,Header,Date,Account,Description,Transaction Type,"
    b"Symbol,Quantity,Price,Price Currency,Gross Amount,Commission,Net Amount\n"
    # Solo 1 compra en el CSV (el broker no exportó las acciones viejas)
    b"Transaction History,Data,2025-07-01,U123,Buy SCHB,Buy,SCHB,10,20.00,USD,-200.00,0.0,-200.00\n"
)


def _mock_price_30(ticker, start_date):
    data = pd.DataFrame(
        {"Close": [30.0], "Dividends": [0.0], "Stock Splits": [0.0], "VOO Price": [500.0]},
        index=[pd.Timestamp("2025-08-15")],
    )
    return data, None


def test_reconciliation_overrides_incomplete_position(monkeypatch):
    """El CSV solo trae 10 acciones / $200, pero la captura del broker dice 50 acciones / $1000
    (acciones previas a la ventana de export). El override debe reemplazar shares/cost y recalcular."""
    df, _ = logic.load_and_detect_csv(FakeFile(_RECON_CSV))
    df_clean = logic.normalize_csv(df)
    monkeypatch.setattr(logic, "fetch_market_data", _mock_price_30)

    overrides = {"SCHB": {"cost_basis": 1000.0, "shares": 50.0}}
    res = logic.analyze_portfolio(df_clean, version="TEST_RECON", position_overrides=overrides)
    assert "SCHB" in res
    s = res["SCHB"]
    assert s["reconciled_from_snapshot"] is True
    assert set(s["reconciled_fields"]) == {"shares", "cost_basis"}
    assert s["shares_owned"] == pytest.approx(50.0)
    assert s["pocket_investment"] == pytest.approx(1000.0)
    assert s["market_value"] == pytest.approx(1500.0)             # 50 × $30
    assert s["roi_percent"] == pytest.approx(50.0, abs=0.5)        # (1500-1000)/1000
    assert logic.assess_ticker_quality(res, "SCHB")["level"] == "reconciled"


def test_reconciliation_noop_when_matches_csv(monkeypatch):
    """Si la captura coincide con el CSV (dentro de tolerancia), NO se reconcilia (no-op)."""
    df, _ = logic.load_and_detect_csv(FakeFile(_RECON_CSV))
    df_clean = logic.normalize_csv(df)
    monkeypatch.setattr(logic, "fetch_market_data", _mock_price_30)

    overrides = {"SCHB": {"cost_basis": 200.0, "shares": 10.0}}  # = CSV
    res = logic.analyze_portfolio(df_clean, version="TEST_RECON_NOOP", position_overrides=overrides)
    s = res["SCHB"]
    assert s["reconciled_from_snapshot"] is False
    assert s["shares_owned"] == pytest.approx(10.0)
    assert s["pocket_investment"] == pytest.approx(200.0)


# ── Capa de conocimiento de instrumentos + interpretación (2026-06-08) ─────────

def test_load_instruments_merges_yaml_over_fallback():
    """Carga el YAML sobre el fallback embebido: tickers del fallback + los nuevos del YAML."""
    logic.load_instruments.clear()
    inst = logic.load_instruments()
    # del fallback embebido
    assert 'MSTY' in inst and inst['MSTY']['risk'] == 'HIGH'
    # nuevos que solo viven en el YAML (estaban como UNKNOWN antes)
    assert 'NFLY' in inst and 'PLTY' in inst
    # el YAML profundiza con campos que el fallback no tenía
    assert inst['MSTY'].get('income_mechanism')
    assert inst['MSTY'].get('sustainability')


def test_load_instruments_resilient_to_missing_file(monkeypatch):
    """Si el archivo de conocimiento no existe, cae al fallback embebido sin crashear."""
    logic.load_instruments.clear()
    monkeypatch.setattr(logic, '_INSTRUMENTS_PATH', '/no/existe/instruments.yaml')
    inst = logic.load_instruments()
    assert 'MSTY' in inst  # fallback intacto
    logic.load_instruments.clear()  # no contaminar otros tests


def test_get_yieldmax_risk_profile_shape_stable():
    """Back-compat: siempre devuelve las 4 claves que consume la sección de riesgo."""
    logic.load_instruments.clear()
    known = logic.get_yieldmax_risk_profile('NVDY')
    assert set(known) == {'underlying', 'name', 'risk', 'reason'}
    assert known['underlying'] == 'NVDA' and known['risk'] == 'HIGH'
    unknown = logic.get_yieldmax_risk_profile('ZZZZ')
    assert set(unknown) == {'underlying', 'name', 'risk', 'reason'}
    assert unknown['risk'] == 'UNKNOWN'


def test_build_interpretation_compensated_vs_deficit():
    """YieldMax: el bloque sintetiza COMPENSADO cuando el income supera la caída, y déficit si no."""
    comp = logic.build_interpretation(
        {'MSTY': {'pocket_investment': 10000, 'market_value': 6000, 'dividends_collected_cash': 5000}}, 'MSTY')
    txt = ' '.join(comp['lines'])
    assert comp['lines']                      # no vacío
    assert 'income' in txt and 'compensó' in txt
    assert 'retorno total +$1,000' in txt

    deficit = logic.build_interpretation(
        {'MSTY': {'pocket_investment': 10000, 'market_value': 6000, 'dividends_collected_cash': 1000}}, 'MSTY')
    assert 'todavía no cubre' in ' '.join(deficit['lines'])


def test_build_interpretation_unknown_no_fabrication():
    """Ticker fuera del YAML: solo sintetiza los números, NO inventa conocimiento."""
    out = logic.build_interpretation(
        {'ZZZZ': {'pocket_investment': 1000, 'market_value': 1200, 'dividends_collected_cash': 50}}, 'ZZZZ')
    assert len(out['lines']) == 1
    assert 'retorno total' in out['lines'][0].lower()


def test_knowledge_and_interpretation_have_no_buy_sell_language():
    """Principio de diseño: NUNCA recomendación personalizada de compra/venta —
    ni en el conocimiento curado ni en las líneas generadas."""
    forbidden = re.compile(r'\b(deber[ií]as|compra|compre|vende|venda|vender|comprar|recomiendo|recomendamos)\b',
                           re.IGNORECASE)
    # 1) Conocimiento curado (todos los campos de texto de cada instrumento)
    for tk, prof in logic.load_instruments().items():
        for field in ('reason', 'income_mechanism', 'nav_erosion', 'sustainability', 'note'):
            val = prof.get(field)
            if val:
                assert not forbidden.search(val), f"{tk}.{field} contiene lenguaje de compra/venta: {val!r}"
    # 2) Líneas generadas para varios escenarios
    scenarios = {
        'MSTY': {'pocket_investment': 10000, 'market_value': 6000, 'dividends_collected_cash': 5000},
        'XLK':  {'pocket_investment': 2000,  'market_value': 3500, 'dividends_collected_cash': 20},
        'NVDL': {'pocket_investment': 1000,  'market_value': 1100, 'dividends_collected_cash': 0},
    }
    for tk, s in scenarios.items():
        for ln in logic.build_interpretation({tk: s}, tk)['lines']:
            assert not forbidden.search(ln), f"línea de {tk} contiene compra/venta: {ln!r}"


def test_build_portfolio_verdict_concentration_and_income():
    """Veredicto: detecta concentración alta y peso en YieldMax; sin lenguaje de compra/venta."""
    results = {
        'MSTY': {'pocket_investment': 14000, 'market_value': 6000, 'dividends_collected_cash': 9000},
        'SCHB': {'pocket_investment': 1000,  'market_value': 1200,  'dividends_collected_cash': 20},
    }
    classify = {'MSTY': 'mode_a', 'SCHB': 'mode_b'}
    out = logic.build_portfolio_verdict(results, classify)
    txt = ' '.join(out['lines'])
    assert out['lines']
    assert 'MSTY' in txt and '%' in txt            # concentración nombrada
    assert 'YieldMax' in txt                        # peso en income
    forbidden = re.compile(r'\b(deber[ií]as|compra|compre|vende|venda|vender|comprar|recomiendo|recomendamos)\b',
                           re.IGNORECASE)
    for ln in out['lines']:
        assert not forbidden.search(ln), f"veredicto con compra/venta: {ln!r}"


def test_build_portfolio_verdict_empty_is_safe():
    """Sin posiciones válidas no crashea y devuelve vacío."""
    assert logic.build_portfolio_verdict({}, {}) == {'lines': []}
    assert logic.build_portfolio_verdict({'X': {'error': 'x'}}, {}) == {'lines': []}


# ── Investment Income (segunda fuente de validación) ───────────────────────────

INCOME_CSV = (
    b'"Investment Income Transactions as of 06/08/2026 08:43:32 ET"\n'
    b'Transaction Date,Account Number,Account Name,Account Type,Security Description,Symbol,Security Type,Transaction Type,Transaction Amount,Income Type,\n'
    b'"06/30/2027","...550","Individual","BROKERAGE","Schwab US Broad Market ETF","SCHB","ETFs & Closed End Funds","Dividend","3.74","Estimated",\n'
    b'"05/01/2026","...550","Individual","BROKERAGE","YIELDMAX MSTR OPT INCM STRTGY ETF","88634T493","ETFs & Closed End Funds","Reinvest Dividend","10.00","Received",\n'
    b'"04/01/2026","...550","Individual","BROKERAGE","TIDAL TR II YIELDMAX MSTR OPTION INCOME STRATEGY ETF NEW","MSTY","ETFs & Closed End Funds","Reinvest Dividend","5.00","Received",\n'
    b'"03/01/2026","...550","Individual","BROKERAGE","MICROSOFT CORP","MSFT","Equities","Qualified Dividend","1.82","Received",\n'
    b'"02/01/2026","...550","Individual","BROKERAGE","Cash & Money Market","NO NUMBER","Cash & Money Market","Credit Interest","0.09","Received",\n'
    b'"01/01/2026","...550","Individual","BROKERAGE","ORACLE CORP","ORCL","Equities","Qualified Dividend","","Received",\n'
)


def _hist(rows, ticker="X"):
    """Construye un history DataFrame mínimo [Date, Action, Amount, Ticker] para reconcile."""
    return pd.DataFrame([
        {"Date": pd.Timestamp(d), "Action": a, "Amount": amt, "Ticker": ticker}
        for d, a, amt in rows
    ])


def test_income_parse_and_summarize():
    df = logic.parse_schwab_income_csv(INCOME_CSV)
    assert df is not None and len(df) > 0
    summ = logic.summarize_income(df)
    assert summ["multi_account"] is False
    t = summ["tickers"]
    # MSTY plegado: 10 (CUSIP 88634T493) + 5 (ticker) = 15, folded
    assert t["MSTY"]["received_total"] == pytest.approx(15.0, abs=0.01)
    assert t["MSTY"]["folded"] is True
    assert "88634T493" not in t                       # el CUSIP no es un ticker propio
    assert t["MSFT"]["received_total"] == pytest.approx(1.82, abs=0.01)
    assert "received_total" not in t.get("SCHB", {})  # SCHB solo 'Estimated'
    assert t["SCHB"]["est_per_payment"] == pytest.approx(3.74, abs=0.01)
    assert "NO NUMBER" not in t                        # interés de cash excluido
    assert "ORCL" not in t                             # monto malformado -> fila descartada


def test_income_reject_non_income():
    assert logic.parse_schwab_income_csv(b"") is None
    assert logic.parse_schwab_income_csv(SCHWAB_CSV) is None     # es de transacciones, no income


def test_reconcile_none_is_noop_and_pure():
    results = {"MSTY": {"history": _hist([("2026-05-01", "Reinvest Dividend", 5.0)]),
                        "history_incomplete": False}}
    assert logic.reconcile_income(results, None) == {}
    assert logic.reconcile_income(results, {"tickers": {}}) == {}
    assert "income_recon" not in results["MSTY"]                 # no muta results


def test_reconcile_match_gross():
    results = {"MSTY": {"history": _hist([("2026-04-01", "Reinvest Dividend", 5.0),
                                          ("2026-05-01", "Reinvest Dividend", 10.0)]),
                        "history_incomplete": False}}
    income = {"tickers": {"MSTY": {"received_total": 15.0, "folded": False,
                                   "received_window": (pd.Timestamp("2026-04-01"), pd.Timestamp("2026-05-01"))}}}
    r = logic.reconcile_income(results, income)["MSTY"]
    assert r["status"] == "match" and r["badge"] == "ok"
    assert r["csv_total"] == pytest.approx(15.0, abs=0.01)


def test_reconcile_cusip_folded_badge():
    results = {"MSTY": {"history": _hist([("2026-05-01", "Reinvest Dividend", 15.0)]),
                        "history_incomplete": False}}
    income = {"tickers": {"MSTY": {"received_total": 15.0, "folded": True,
                                   "received_window": (pd.Timestamp("2026-05-01"), pd.Timestamp("2026-05-01"))}}}
    r = logic.reconcile_income(results, income)["MSTY"]
    assert r["status"] == "cusip_folded" and r["badge"] == "ok"


def test_reconcile_csv_window_longer():
    # El CSV tiene un dividendo de 2024 fuera de la ventana del income.
    results = {"SCHB": {"history": _hist([("2024-05-01", "Reinvest Dividend", 5.0),
                                          ("2026-05-01", "Reinvest Dividend", 10.0)]),
                        "history_incomplete": False}}
    income = {"tickers": {"SCHB": {"received_total": 10.0, "folded": False,
                                   "received_window": (pd.Timestamp("2026-01-01"), pd.Timestamp("2026-12-31"))}}}
    r = logic.reconcile_income(results, income)["SCHB"]
    assert r["status"] == "csv_window_longer" and r["badge"] == "ok"
    assert r["csv_total"] == pytest.approx(15.0, abs=0.01)
    assert r["csv_in_window"] == pytest.approx(10.0, abs=0.01)


def test_reconcile_income_higher_regression():
    """REGRESIÓN: income > CSV en la ventana común debe ser 'income_higher' (alarma real).
    Protege contra que una tolerancia más amplia enmascare dividendos faltantes."""
    results = {"MSTY": {"history": _hist([("2026-05-01", "Reinvest Dividend", 5.0)]),
                        "history_incomplete": False}}
    income = {"tickers": {"MSTY": {"received_total": 15.0, "folded": False,
                                   "received_window": (pd.Timestamp("2026-04-01"), pd.Timestamp("2026-06-01"))}}}
    r = logic.reconcile_income(results, income)["MSTY"]
    assert r["status"] == "income_higher" and r["badge"] == "warn"


def test_reconcile_csv_overcount_when_history_incomplete():
    results = {"SCHB": {"history": _hist([("2026-05-01", "Reinvest Dividend", 20.0)]),
                        "history_incomplete": True}}
    income = {"tickers": {"SCHB": {"received_total": 10.0, "folded": False,
                                   "received_window": (pd.Timestamp("2026-01-01"), pd.Timestamp("2026-12-31"))}}}
    r = logic.reconcile_income(results, income)["SCHB"]
    assert r["status"] == "csv_overcount_suspected" and r["badge"] == "warn"


def test_reconcile_missing_in_csv():
    income = {"tickers": {"ZIM": {"received_total": 8.0, "folded": False,
                                  "received_window": (pd.Timestamp("2025-01-01"), pd.Timestamp("2025-12-31"))}}}
    r = logic.reconcile_income({}, income)
    assert r["ZIM"]["status"] == "missing_in_csv"


def test_reconcile_missing_in_income():
    results = {"MSTY": {"history": _hist([("2026-05-01", "Reinvest Dividend", 5.0)]),
                        "history_incomplete": False}}
    income = {"tickers": {"MSTY": {"est_per_payment": 6.5}}}     # solo Estimated, sin received
    r = logic.reconcile_income(results, income)["MSTY"]
    assert r["status"] == "missing_in_income"


_FIX = os.path.join(os.path.dirname(__file__), "real_examples", "charles_schwab_data", "2")


@pytest.mark.skipif(not os.path.isdir(_FIX), reason="sin real_examples/ (data privada)")
def test_income_real_schwab2_reconciles():
    """Caso real schwab_2: el income del broker valida el dividendo del CSV. Sin red:
    se reconstruyen results desde las transacciones normalizadas (history por ticker)."""
    import glob as _glob
    import json as _json
    inc = _glob.glob(os.path.join(_FIX, "*InvestmentIncome*"))
    tx = _glob.glob(os.path.join(_FIX, "*Transactions*.csv"))
    if not inc or not tx:
        pytest.skip("fixtures incompletos")
    with open(inc[0], "rb") as f:
        summ = logic.summarize_income(logic.parse_schwab_income_csv(f.read()))
    with open(tx[0], "rb") as f:
        df = logic.normalize_csv(logic.parse_schwab_csv(f.read()))
    results = {}
    for tk in df["Ticker"].dropna().unique():
        results[tk] = {"history": df[df["Ticker"] == tk], "history_incomplete": (tk == "SCHB")}
    recon = logic.reconcile_income(results, summ)

    exp = _json.load(open(os.path.join(_FIX, "expected.json")))["income_expected"]
    # MSTY plegado del CUSIP y ~346 (tolerancia = constante de la app)
    assert summ["tickers"]["MSTY"]["folded"] is True
    assert summ["tickers"]["MSTY"]["received_total"] == pytest.approx(
        exp["received"]["MSTY"], abs=logic.INCOME_MATCH_TOL_ABS)
    assert recon["MSTY"]["status"] in ("match", "cusip_folded")
    assert recon["MSTY"]["badge"] == "ok"
    # Equities: income exacto y estado 'match'
    for eq in ("MSFT", "ORCL", "COP", "CHD", "CL"):
        assert summ["tickers"][eq]["received_total"] == pytest.approx(exp["received"][eq], abs=0.01)
        assert recon[eq]["status"] == "match"
    # SCHB/XLK: NUNCA 'income_higher' (es ventana más larga, no error)
    for w in ("SCHB", "XLK"):
        assert recon[w]["status"] != "income_higher", (w, recon[w])


# ── project_income (proyección broker vs run-rate reciente) ────────────────────

def _income_df(rows):
    """rows: lista de (date, ticker, income_type, amount) -> df estilo parse_schwab_income_csv."""
    return pd.DataFrame([
        {"Date": pd.Timestamp(d), "Ticker": t, "IncomeType": it, "Amount": a, "folded": False}
        for d, t, it, a in rows
    ])


def _build_proj_income():
    """MSTY: serie semanal decreciente ($6→$3) + Estimated plano alto ($6). SCHB: trimestral
    estable ($4) + Estimated estable. Fechas relativas a hoy para que el test no caduque."""
    today = pd.Timestamp.today().normalize()
    rows = []
    for i in range(20):  # 20 pagos semanales recibidos, de $6 a $3
        rows.append((today - pd.Timedelta(weeks=20 - i), "MSTY", "Received", 6.0 - 3.0 * i / 19))
    for i in range(1, 53):  # 52 estimados futuros, plano en $6 (ancla alta)
        rows.append((today + pd.Timedelta(weeks=i), "MSTY", "Estimated", 6.0))
    for i in range(5):   # SCHB trimestral estable
        rows.append((today - pd.Timedelta(days=90 * (5 - i)), "SCHB", "Received", 4.0))
    for i in range(1, 5):
        rows.append((today + pd.Timedelta(days=90 * i), "SCHB", "Estimated", 4.0))
    rows.append((today - pd.Timedelta(weeks=2), "AAA", "Received", 1.0))   # solo 2 received -> excluido
    rows.append((today - pd.Timedelta(weeks=1), "AAA", "Received", 1.0))
    rows.append((today + pd.Timedelta(weeks=1), "AAA", "Estimated", 1.0))
    return _income_df(rows)


def test_project_income_yieldmax_overstated():
    proj = logic.project_income(_build_proj_income())
    assert "AAA" not in proj                       # <4 pagos recibidos -> excluido
    m = proj["MSTY"]
    assert m["payments_per_year"] == 52
    assert m["anchor_per_payment"] == pytest.approx(6.0, abs=0.01)
    assert m["schwab_proj"] == pytest.approx(312.0, abs=1.0)        # 52 x $6
    assert m["our_proj"] < m["schwab_proj"]                          # run-rate reciente menor
    assert m["overstatement_pct"] > logic.INCOME_OVERSTATE_FLAG_PCT  # > 15%
    assert m["our_received_12m"] is None                             # sin results


def test_project_income_stable_etf_matches():
    proj = logic.project_income(_build_proj_income())
    s = proj["SCHB"]
    assert abs(s["overstatement_pct"]) <= 5         # ETF estable: proyecciones ~iguales


def test_project_income_empty_and_none():
    assert logic.project_income(None) == {}
    assert logic.project_income(_income_df([])) == {}


def test_project_income_uses_results_for_csv_12m():
    today = pd.Timestamp.today().normalize()
    hist = _hist([(str((today - pd.Timedelta(weeks=k)).date()), "Reinvest Dividend", 5.0) for k in range(1, 6)],
                 ticker="SCHB")
    proj = logic.project_income(_build_proj_income(), {"SCHB": {"history": hist}})
    assert proj["SCHB"]["our_received_12m"] == pytest.approx(25.0, abs=0.01)  # 5 x $5 en 12m


def test_project_income_total_historico_keys():
    """Total histórico: Schwab = todas las filas Received (no solo 12m); Calc = todo el CSV."""
    proj = logic.project_income(_build_proj_income())
    # MSTY: 20 pagos de $6→$3 todos dentro de 12 meses -> total == 12m == $90.
    assert proj["MSTY"]["schwab_received_total"] == pytest.approx(90.0, abs=0.5)
    assert proj["MSTY"]["schwab_received_total"] == pytest.approx(proj["MSTY"]["schwab_received_12m"], abs=0.01)
    # SCHB: 5 pagos de $4; el más viejo (~450d) cae fuera de 12m -> total ($20) > 12m ($16).
    assert proj["SCHB"]["schwab_received_total"] == pytest.approx(20.0, abs=0.01)
    assert proj["SCHB"]["schwab_received_total"] > proj["SCHB"]["schwab_received_12m"]
    # Sin results, el total del CSV no está disponible.
    assert proj["MSTY"]["our_received_total"] is None


def test_project_income_csv_total_exceeds_12m_window():
    """our_received_total incluye dividendos previos a 12m que our_received_12m excluye."""
    today = pd.Timestamp.today().normalize()
    rows = [(str((today - pd.Timedelta(weeks=k)).date()), "Reinvest Dividend", 5.0) for k in range(1, 6)]
    rows.append((str((today - pd.Timedelta(days=730)).date()), "Reinvest Dividend", 10.0))  # ~2 años atrás
    hist = _hist(rows, ticker="SCHB")
    proj = logic.project_income(_build_proj_income(), {"SCHB": {"history": hist}})
    assert proj["SCHB"]["our_received_12m"] == pytest.approx(25.0, abs=0.01)   # solo los 5 recientes
    assert proj["SCHB"]["our_received_total"] == pytest.approx(35.0, abs=0.01)  # + el viejo de $10


# ── filter_income_assets / is_income_strategy_asset (filtro del portafolio de ingresos) ─────

def test_filter_income_assets_excludes_index_etf():
    """MSTY (yieldmax) entra siempre; SCHB (etf) con yield <4% (dividendo marginal) se excluye."""
    proj = logic.project_income(_build_proj_income())     # SCHB recibido 12m = $16
    kept, dropped = logic.filter_income_assets(proj, {"SCHB": {"market_value": 1000.0}})  # $16/$1000 = 1.6%
    assert "MSTY" in kept
    assert "SCHB" not in kept
    assert any(t == "SCHB" for t, _ in dropped)


def test_filter_income_assets_keeps_yieldmax_without_results():
    """Sin market_value, el yieldmax se conserva por su type (degradación elegante)."""
    proj = logic.project_income(_build_proj_income())
    kept, _ = logic.filter_income_assets(proj, None)
    assert "MSTY" in kept


def test_filter_income_assets_high_yield_etf_kept():
    """Un etf con yield alto (caso SCHD-like) entra por el umbral de yield, no por su type."""
    proj = logic.project_income(_build_proj_income())     # SCHB recibido 12m = $16
    kept, _ = logic.filter_income_assets(proj, {"SCHB": {"market_value": 200.0}})  # $16/$200 = 8% >= 4%
    assert "SCHB" in kept
    assert kept["SCHB"]["_yield_pct"] == pytest.approx(8.0, abs=0.1)


def test_is_income_strategy_asset_leveraged_excluded():
    """type:leveraged (NVDL) nunca es activo de ingresos, aunque el yield calculado sea altísimo."""
    ok, meta = logic.is_income_strategy_asset(
        "NVDL", {"schwab_received_12m": 50.0, "our_received_12m": 50.0},
        {"NVDL": {"market_value": 100.0}})   # yield 50% pero es apalancado de crecimiento
    assert ok is False
    assert meta["reason"] == "type:leveraged"


# ── is_growth_asset / filter_growth_assets (portafolio de crecimiento) ──────────

def test_is_growth_asset_type_rules():
    """yieldmax nunca es crecimiento (aunque yield_on_cost sea 0); leveraged siempre lo es."""
    assert logic.is_growth_asset("MSTY", {"MSTY": {"yield_on_cost": 0.0}})[0] is False
    assert logic.is_growth_asset("NVDL", {"NVDL": {"yield_on_cost": 0.0}})[0] is True


def test_is_growth_asset_low_yield_etf_is_growth():
    """ETF de dividendo marginal (yield_on_cost < 4%) → crecimiento, vía fallback solo-CSV."""
    ok, meta = logic.is_growth_asset("SCHB", {"SCHB": {"market_value": 1000.0, "yield_on_cost": 1.5}})
    assert ok is True
    assert meta["yield_pct"] == pytest.approx(1.5, abs=0.1)


def test_is_growth_asset_high_yield_etf_is_income():
    """ETF de yield alto (>=4%) NO es crecimiento (es income), aunque no sea yieldmax."""
    ok, _ = logic.is_growth_asset("SCHB", {"SCHB": {"market_value": 200.0, "yield_on_cost": 8.0}})
    assert ok is False


def test_is_growth_asset_prefers_income_file_yield():
    """Si hay dato del income file, usa yield-on-market (16/1000=1.6%) sobre yield_on_cost."""
    ok, meta = logic.is_growth_asset(
        "SCHB", {"SCHB": {"market_value": 1000.0, "yield_on_cost": 99.0}},
        {"our_received_12m": 16.0})
    assert ok is True
    assert meta["yield_pct"] == pytest.approx(1.6, abs=0.1)


def test_filter_growth_assets_complement_of_income():
    """Crecimiento = posiciones válidas no-income; excluye yieldmax, skipped y error."""
    results = {
        "SCHB": {"market_value": 7000.0, "pocket_investment": 5000.0,
                 "dividends_collected_cash": 20.0, "roi_percent": 40.4,
                 "benchmark_value": 6000.0, "benchmark_roi": 20.0, "yield_on_cost": 0.5},
        "MSTY": {"market_value": 1000.0, "pocket_investment": 1200.0,
                 "dividends_collected_cash": 300.0, "roi_percent": 8.3,
                 "benchmark_value": 1300.0, "benchmark_roi": 8.3, "yield_on_cost": 60.0},
        "NVDL": {"skipped": True, "reason": "not_known_etf"},
        "BAD":  {"error": "no market data"},
    }
    growth = logic.filter_growth_assets(results)
    assert "SCHB" in growth          # etf bajo yield → crecimiento
    assert "MSTY" not in growth      # yieldmax → income
    assert "NVDL" not in growth      # skipped (sin métricas) → excluido
    assert "BAD" not in growth       # error → excluido
    assert growth["SCHB"]["roi_percent"] == 40.4
    assert growth["SCHB"]["benchmark_roi"] == 20.0


# ── v3.0: Proyección a futuro, doble yield, impuestos (Mejoras inspiradas en calculadoras web) ──

def _div_hist(rows):
    df = pd.DataFrame(rows)
    df['Date'] = pd.to_datetime(df['Date'])
    return df


def test_net_of_withholding_basic_and_defensive():
    assert logic.net_of_withholding(100, 30) == pytest.approx(70.0)
    assert logic.net_of_withholding(100, 0) == pytest.approx(100.0)
    assert logic.net_of_withholding(None, 30) is None
    assert logic.net_of_withholding(100, None) == pytest.approx(100.0)
    # tasas fuera de rango se acotan a [0, 100]
    assert logic.net_of_withholding(100, 150) == pytest.approx(0.0)


def test_dividend_events_excludes_reinvest_shares_and_tax():
    hist = _div_hist([
        {'Date': '2025-09-15', 'Action': 'Qualified Dividend', 'Amount': 10},
        {'Date': '2025-10-15', 'Action': 'Reinvest Dividend', 'Amount': 10},
        {'Date': '2025-10-15', 'Action': 'Reinvest Shares', 'Amount': -7},   # compra neta → omitir
        {'Date': '2025-11-15', 'Action': 'NRA Tax Adj', 'Amount': -3},        # impuesto → omitir
        {'Date': '2025-11-15', 'Action': 'Cash Dividend', 'Amount': 12},
    ])
    ev = logic._dividend_events(hist)
    assert len(ev) == 3
    assert ev.sum() == pytest.approx(32.0)


def test_withheld_tax_total_reads_nra_rows():
    hist = _div_hist([
        {'Date': '2025-11-15', 'Action': 'Cash Dividend', 'Amount': 12},
        {'Date': '2025-11-15', 'Action': 'NRA Tax Adj', 'Amount': -3.6},
    ])
    assert logic.withheld_tax_total(hist) == pytest.approx(3.6)
    # sin filas de impuesto → 0
    assert logic.withheld_tax_total(_div_hist(
        [{'Date': '2025-11-15', 'Action': 'Cash Dividend', 'Amount': 12}])) == 0.0


def test_forward_realized_yield_distinguishes_headline_from_collected():
    # Pagos mensuales decrecientes: último pago anualizado (forward) > lo cobrado en 12m (realizado).
    rows = [{'Date': f'2025-{m:02d}-15', 'Action': 'Cash Dividend', 'Amount': amt}
            for m, amt in zip(range(1, 13), [20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9])]
    hist = _div_hist(rows)
    fy = logic.forward_realized_yield(hist, market_value=1000, today='2026-01-01')
    assert fy['payments_per_year'] == 12
    assert fy['last_payment'] == pytest.approx(9.0)
    # forward = 9*12/1000 = 10.8%
    assert fy['forward_yield'] == pytest.approx(10.8, abs=0.1)
    # realized (suma de los 12 pagos) = 174/1000 = 17.4%
    assert fy['realized_yield'] == pytest.approx(17.4, abs=0.1)
    # sin valor de mercado → todo None
    assert logic.forward_realized_yield(hist, market_value=0)['forward_yield'] is None


def test_project_growth_etf_drip_beats_cash():
    results = {'SCHD': {'forward_yield': 4.0, 'realized_yield': 3.9, 'shares_owned': 100,
                        'current_price': 80.0, 'price_cagr': 8.0}}
    out = logic.project_portfolio_forward(
        results, {'horizon_years': 10, 'drip': True, 'price_appreciation_pct': 6,
                  'dividend_growth_pct': 5}, classify_map={'SCHD': 'mode_b'})
    e = out['per_ticker']['SCHD']
    assert e['is_yieldmax'] is False
    assert e['price_growth_pct'] == 6 and e['div_growth_pct'] == 5
    assert e['drip_advantage'] > 0          # reinvertir gana en un activo que aprecia
    assert e['end_value'] > e['start_value']


def test_project_yieldmax_never_assumes_appreciation_and_has_breakeven():
    results = {'MSTY': {'forward_yield': 60.0, 'realized_yield': 50.0, 'shares_owned': 100,
                        'current_price': 20.0, 'price_cagr': 12.0, 'roc_percent': 70.0}}
    # price_cagr positivo (12%): el guardarraíl debe capar a ≤0 para un YieldMax.
    out = logic.project_portfolio_forward(
        results, {'horizon_years': 5, 'drip': False, 'price_appreciation_pct': 10},
        classify_map={'MSTY': 'mode_a'})
    e = out['per_ticker']['MSTY']
    assert e['is_yieldmax'] is True
    assert e['price_growth_pct'] <= 0       # nunca apreciación positiva
    assert 'breakeven_month' in e and 'honest_total_return_pct' in e
    assert 'race' in e and len(e['race']) == 60


def test_project_yieldmax_decay_override_and_no_breakeven():
    results = {'TSLY': {'forward_yield': 20.0, 'realized_yield': 18.0, 'shares_owned': 100,
                        'current_price': 10.0, 'price_cagr': None}}
    # Decaimiento brutal (-50%/año) y yield modesto: el ingreso no cubre la pérdida → sin breakeven.
    out = logic.project_portfolio_forward(
        results, {'horizon_years': 3, 'drip': False, 'nav_decay_overrides': {'TSLY': -50.0}},
        classify_map={'TSLY': 'mode_a'})
    e = out['per_ticker']['TSLY']
    assert e['price_growth_pct'] == -50.0
    assert e['honest_total_return_pct'] < 0     # pierde dinero pese al yield alto


def test_project_tax_reduces_income():
    results = {'MSTY': {'forward_yield': 60.0, 'realized_yield': 50.0, 'shares_owned': 100,
                        'current_price': 20.0, 'price_cagr': -20.0}}
    base = logic.project_portfolio_forward(results, {'horizon_years': 3, 'drip': True, 'tax_rate_pct': 0},
                                           classify_map={'MSTY': 'mode_a'})
    taxed = logic.project_portfolio_forward(results, {'horizon_years': 3, 'drip': True, 'tax_rate_pct': 30},
                                            classify_map={'MSTY': 'mode_a'})
    assert (taxed['per_ticker']['MSTY']['cumulative_dividends_net']
            < base['per_ticker']['MSTY']['cumulative_dividends_net'])


def test_project_skips_ineligible_tickers():
    results = {
        'NODIV': {'forward_yield': 0, 'shares_owned': 50, 'current_price': 30.0},     # sin yield
        'SOLD':  {'forward_yield': 5.0, 'shares_owned': 0, 'current_price': 30.0},    # sin acciones
        'BAD':   {'error': 'no data'},
        'OK':    {'forward_yield': 4.0, 'realized_yield': 4.0, 'shares_owned': 10,
                  'current_price': 50.0, 'price_cagr': 5.0},
    }
    out = logic.project_portfolio_forward(results, {'horizon_years': 2}, classify_map={'OK': 'mode_b'})
    assert out['eligible'] == ['OK']


def test_project_income_goal_milestone():
    results = {'SCHD': {'forward_yield': 4.0, 'realized_yield': 4.0, 'shares_owned': 1000,
                        'current_price': 80.0, 'price_cagr': 7.0}}
    out = logic.project_portfolio_forward(
        results, {'horizon_years': 20, 'drip': True, 'dividend_growth_pct': 8,
                  'price_appreciation_pct': 7, 'income_goal_monthly': 500},
        classify_map={'SCHD': 'mode_b'})
    assert out['portfolio'].get('income_goal_year') is not None


# ── v3.1: detección de cambio de cadencia + decaimiento de ventana reciente ──

def _payment_hist(dates_amounts):
    df = pd.DataFrame([{'Date': d, 'Action': 'Cash Dividend', 'Amount': a} for d, a in dates_amounts])
    df['Date'] = pd.to_datetime(df['Date'])
    return df


def test_cadence_change_monthly_to_weekly():
    import datetime as dt
    rows = []
    d = dt.date(2025, 1, 15)
    for i in range(8):                       # 8 mensuales
        rows.append((d + dt.timedelta(days=30 * i), 200 - i * 5))
    start = rows[-1][0]
    for i in range(1, 9):                     # 8 semanales después
        rows.append((start + dt.timedelta(days=7 * i), 40 - i))
    cc = logic.detect_cadence_change(_payment_hist(rows))
    assert cc['changed'] is True
    assert cc['old_label'] == 'mensual' and cc['recent_label'] == 'semanal'


def test_cadence_stable_quarterly_not_flagged():
    import datetime as dt
    rows = [(dt.date(2024, 1, 15) + dt.timedelta(days=91 * i), 75) for i in range(8)]
    cc = logic.detect_cadence_change(_payment_hist(rows))
    assert cc['changed'] is False and cc['recent_label'] == 'trimestral'


def test_cadence_change_none_when_too_few_payments():
    import datetime as dt
    rows = [(dt.date(2025, 1, 15) + dt.timedelta(days=30 * i), 100) for i in range(4)]
    assert logic.detect_cadence_change(_payment_hist(rows)) is None


def test_cadence_label_maps_to_nearest_standard():
    assert logic._cadence_label(52) == 'semanal'
    assert logic._cadence_label(11) == 'mensual'      # 11 → mensual (12)
    assert logic._cadence_label(4) == 'trimestral'
    assert logic._cadence_label(None) == 'desconocida'


def test_projection_prefers_recent_decay_window():
    # Vida del fondo cayó -60%/año pero el último año solo -20%: la proyección debe usar -20%.
    results = {'NVDY': {'forward_yield': 40.0, 'realized_yield': 38.0, 'shares_owned': 100,
                        'current_price': 15.0, 'price_cagr': -60.0, 'price_cagr_recent': -20.0}}
    out = logic.project_portfolio_forward(results, {'horizon_years': 3, 'drip': False},
                                          classify_map={'NVDY': 'mode_a'})
    e = out['per_ticker']['NVDY']
    assert e['price_growth_pct'] == -20.0
    assert e['decay_window'] == '12m'


def test_projection_falls_back_to_life_cagr_when_no_recent():
    results = {'TSLY': {'forward_yield': 30.0, 'realized_yield': 28.0, 'shares_owned': 100,
                        'current_price': 10.0, 'price_cagr': -40.0, 'price_cagr_recent': None}}
    out = logic.project_portfolio_forward(results, {'horizon_years': 2, 'drip': False},
                                          classify_map={'TSLY': 'mode_a'})
    e = out['per_ticker']['TSLY']
    assert e['price_growth_pct'] == -40.0 and e['decay_window'] == 'vida'


# ── v3.2: subyacente (M1), módulo fiscal NRA (M2), Monte Carlo (M3) ──

def test_nra_tax_breakdown_treaty_and_default():
    co = logic.nra_tax_breakdown('Colombia', 0)
    assert co['base_rate'] == 30 and co['has_treaty'] is False
    mx = logic.nra_tax_breakdown('México', 0)
    assert mx['base_rate'] == 10 and mx['has_treaty'] is True
    cl = logic.nra_tax_breakdown('Chile', 0)
    assert cl['base_rate'] == 15 and cl['has_treaty'] is True
    other = logic.nra_tax_breakdown('Inventelandia', 0)   # país desconocido → 30%
    assert other['base_rate'] == 30 and other['has_treaty'] is False


def test_nra_nugget_equation_roc_shield():
    # 30% × (1 − 0.745) = 7.65%
    b = logic.nra_tax_breakdown('Colombia', 74.5, nominal_income=1000)
    assert b['effective_rate'] == pytest.approx(7.65, abs=0.05)
    assert any('Retorno de Capital' in l for l in b['lines'])     # educa el ROC
    assert any('costo de compra' in l for l in b['lines'])        # advierte costo base
    assert any('$300' in l and '$76' in l for l in b['lines'])    # contraste nominal vs efectivo
    assert b['audit_note'] and 'IRS' in b['audit_note']           # nota de auditoría


def test_nra_no_roc_keeps_base_rate():
    b = logic.nra_tax_breakdown('Colombia', 0)
    assert b['effective_rate'] == 30.0


def test_project_country_applies_effective_rate_per_ticker():
    # ZZZY es un YieldMax ficticio (no está en roc_19a.yaml) → usa el roc_percent de results.
    results = {
        'ZZZY': {'forward_yield': 60.0, 'realized_yield': 50.0, 'shares_owned': 100,
                 'current_price': 20.0, 'price_cagr_recent': -25.0, 'roc_percent': 70.0},
        'SCHD': {'forward_yield': 4.0, 'realized_yield': 4.0, 'shares_owned': 100,
                 'current_price': 80.0, 'price_cagr_recent': 6.0, 'roc_percent': None},
    }
    out = logic.project_portfolio_forward(results, {'horizon_years': 3, 'country': 'Colombia'},
                                          classify_map={'ZZZY': 'mode_a', 'SCHD': 'mode_b'})
    # ZZZY: 30 × (1 − 0.70) = 9% ; SCHD sin ROC → 30%
    assert out['per_ticker']['ZZZY']['tax_effective_rate'] == pytest.approx(9.0, abs=0.1)
    assert out['per_ticker']['SCHD']['tax_effective_rate'] == pytest.approx(30.0, abs=0.1)


def test_build_underlying_exposure_asymmetry():
    results = {'TSLY': {'underlying_ticker': 'TSLA', 'underlying_cagr_recent': 27.0,
                        'price_cagr_recent': -31.0, 'shares_owned': 10, 'current_price': 9.0,
                        'forward_yield': 70.0}}
    exp = logic.build_underlying_exposure(results, 'TSLY')
    txt = ' '.join(exp['lines'])
    assert 'TSLA' in txt and 'CAÍDA' in txt
    assert '+27%' in txt and '-31%' in txt          # contraste con datos reales
    # un ticker no-YieldMax no produce líneas
    assert logic.build_underlying_exposure({'SCHD': {'forward_yield': 4}}, 'SCHD')['lines'] == []


def test_monte_carlo_bands_ordered_and_bounded():
    results = {
        'MSTY': {'forward_yield': 60.0, 'shares_owned': 100, 'current_price': 20.0,
                 'price_cagr_recent': -25.0, 'volatilidad_anualizada': 80.0},
        'SCHD': {'forward_yield': 4.0, 'shares_owned': 100, 'current_price': 80.0,
                 'price_cagr_recent': 6.0, 'volatilidad_anualizada': 18.0},
    }
    cm = {'MSTY': 'mode_a', 'SCHD': 'mode_b'}
    mc = logic.monte_carlo_projection(results, {'horizon_years': 5, 'income_goal_monthly': 200},
                                      classify_map=cm, n_paths=400, seed=7)
    assert mc['final']['p10'] <= mc['final']['p50'] <= mc['final']['p90']
    assert mc['final']['p90'] < 1e8            # no explota
    assert 0 <= mc['prob_goal'] <= 100
    for b in mc['bands']:
        assert b['p10'] <= b['p50'] <= b['p90']


def test_monte_carlo_deterministic_with_seed():
    results = {'MSTY': {'forward_yield': 60.0, 'shares_owned': 100, 'current_price': 20.0,
                        'price_cagr_recent': -25.0, 'volatilidad_anualizada': 80.0}}
    cm = {'MSTY': 'mode_a'}
    a = logic.monte_carlo_projection(results, {'horizon_years': 4}, classify_map=cm, n_paths=200, seed=99)
    b = logic.monte_carlo_projection(results, {'horizon_years': 4}, classify_map=cm, n_paths=200, seed=99)
    assert a['final'] == b['final'] and a['bands'] == b['bands']


def test_monte_carlo_corrupt_vol_does_not_explode():
    # vol corrupta (miles de %) NO debe hacer explotar las bandas (cap + modelo yield-on-price)
    results = {'XLK': {'forward_yield': 0.4, 'shares_owned': 100, 'current_price': 250.0,
                       'price_cagr_recent': 30.0, 'volatilidad_anualizada': 3443.0}}
    cm = {'XLK': 'mode_b'}
    mc = logic.monte_carlo_projection(results, {'horizon_years': 5}, classify_map=cm, n_paths=300, seed=3)
    assert mc['final']['p90'] < 1e8


def test_monte_carlo_real_view_below_nominal():
    results = {'SCHD': {'forward_yield': 4.0, 'shares_owned': 100, 'current_price': 80.0,
                        'price_cagr_recent': 6.0, 'volatilidad_anualizada': 18.0}}
    cm = {'SCHD': 'mode_b'}
    real = logic.monte_carlo_projection(results, {'horizon_years': 10, 'price_appreciation_pct': 6,
                                                  'inflation_pct': 3, 'real_view': True},
                                        classify_map=cm, n_paths=300, seed=5)
    nom = logic.monte_carlo_projection(results, {'horizon_years': 10, 'price_appreciation_pct': 6,
                                                 'inflation_pct': 3, 'real_view': False},
                                       classify_map=cm, n_paths=300, seed=5)
    assert real['final']['p50'] < nom['final']['p50']


# ── v3.3: winsorización de retornos (fix de volatilidad corrupta por transferencias) ──

def test_winsorize_clips_spurious_spike():
    import numpy as np
    # 200 retornos normales (~1%) + 1 glitch de +6843% (transferencia de acciones a $0)
    normal = pd.Series(np.random.default_rng(0).normal(0, 0.01, 200))
    spiked = pd.concat([normal, pd.Series([68.43])], ignore_index=True)
    raw_vol = spiked.std()
    clean = logic._winsorize_returns(spiked)
    assert clean.max() < 1.0                      # el glitch quedó acotado
    assert clean.std() < raw_vol / 10             # la vol deja de estar inflada


def test_winsorize_preserves_short_series():
    s = pd.Series([0.01, -0.02, 0.03, 68.0])      # <min_len → se devuelve tal cual
    out = logic._winsorize_returns(s)
    assert out.max() == 68.0


def test_winsorize_handles_non_series():
    assert logic._winsorize_returns(None) is None


# ── v3.4: el benchmark VOO refleja transferencias de acciones (no se queda en $0) ──

_XFER_IDX = pd.date_range('2024-01-02', '2024-06-03', freq='D')


def _mock_flat50(monkeypatch):
    """Mockea el precio del ticker (fetch_market_data) Y el de VOO (yf.download) a $50 plano,
    sin dividendos, para que el benchmark sea determinista (yf.download trae VOO de la red real)."""
    def mock_fetch(ticker, start_date):
        return pd.DataFrame({'Close': [50.0] * len(_XFER_IDX), 'Dividends': [0.0] * len(_XFER_IDX),
                             'Stock Splits': [0.0] * len(_XFER_IDX)}, index=_XFER_IDX), None
    def mock_download(ticker, **kwargs):
        return pd.DataFrame({'Close': [50.0] * len(_XFER_IDX), 'Dividends': [0.0] * len(_XFER_IDX)},
                            index=_XFER_IDX)
    monkeypatch.setattr(logic, 'fetch_market_data', mock_fetch)
    monkeypatch.setattr(logic.yf, 'download', mock_download)


def test_benchmark_includes_share_transfer(monkeypatch):
    """Una Internal Transfer a $0 de efectivo debe contar como capital en el benchmark VOO
    (antes el benchmark ignoraba la transferencia y quedaba subestimado/en $0)."""
    df = pd.DataFrame([
        {'Date': '2024-01-02', 'Action': 'Buy', 'Ticker': 'SCHB', 'Quantity': 1, 'Price': 50.0, 'Amount': -50.0},
        {'Date': '2024-03-01', 'Action': 'Internal Transfer', 'Ticker': 'SCHB', 'Quantity': 20, 'Price': 0.0, 'Amount': 0.0},
    ])
    df['Date'] = pd.to_datetime(df['Date'])
    _mock_flat50(monkeypatch)
    s = logic.analyze_portfolio(df, version='TEST_XFER')['SCHB']
    # 1 acción comprada + 20 transferidas = 21 × $50 = $1050 de valor
    assert s['shares_owned'] == pytest.approx(21.0, abs=0.01)
    # Benchmark = efectivo ($50) + transferencia ($1000) en VOO @ $50 = 21 acc × $50 = ~$1050, no $50.
    assert s['benchmark_value'] == pytest.approx(1050.0, abs=5.0), s['benchmark_value']


def test_benchmark_no_transfer_unchanged(monkeypatch):
    """Sin filas de transferencia, el benchmark usa solo el efectivo (comportamiento idéntico)."""
    df = pd.DataFrame([
        {'Date': '2024-01-02', 'Action': 'Buy', 'Ticker': 'SCHB', 'Quantity': 10, 'Price': 50.0, 'Amount': -500.0},
    ])
    df['Date'] = pd.to_datetime(df['Date'])
    _mock_flat50(monkeypatch)
    s = logic.analyze_portfolio(df, version='TEST_NOXFER')['SCHB']
    # $500 invertidos → 10 acc VOO × $50 = $500 (sin inflar por transferencias inexistentes)
    assert s['benchmark_value'] == pytest.approx(500.0, abs=1.0)


# ── v3.5: modelo por subyacente (escenarios YieldMax) ──

def test_yieldmax_nav_from_underlying_calibration_and_asymmetry():
    f = logic._yieldmax_nav_from_underlying
    # El escenario base (= observado) reproduce el comportamiento real observado del fondo.
    assert f(-67, -67, -83) == pytest.approx(-83.0, abs=0.01)
    # Subida del subyacente: el fondo captura solo una fracción (upside 0.5) → NAV sube poco.
    # cap(R)=1.0·min(R,0)+0.5·max(R,0); drag=cap(-67)-(-83)=16 ; NAV(+30)=0.5·30-16=-1
    assert f(30, -67, -83) == pytest.approx(-1.0, abs=0.01)
    # Caída más fuerte: captura casi toda la baja → NAV peor.
    assert f(-90, -67, -83) == pytest.approx(-106.0, abs=0.01)
    # Sin punto de calibración → None
    assert f(30, None, -83) is None


def test_projection_underlying_scenario_allows_positive(monkeypatch):
    results = {'MSTY': {'forward_yield': 60.0, 'realized_yield': 50.0, 'shares_owned': 100,
                        'current_price': 20.0, 'price_cagr_recent': -83.0,
                        'underlying_cagr_recent': -67.0, 'roc_percent': 74.0}}
    # Escenario muy alcista del subyacente → NAV del fondo puede ser positivo (escenario lo permite).
    out = logic.project_portfolio_forward(
        results, {'horizon_years': 3, 'drip': False, 'underlying_scenarios': {'MSTY': 100.0}},
        classify_map={'MSTY': 'mode_a'})
    e = out['per_ticker']['MSTY']
    assert e['decay_window'] == 'escenario'
    assert e['price_growth_pct'] > 0          # +100% subyacente → NAV positivo (0.5·100−16=+34)
    # Escenario bajista → NAV negativo
    out2 = logic.project_portfolio_forward(
        results, {'horizon_years': 3, 'drip': False, 'underlying_scenarios': {'MSTY': -30.0}},
        classify_map={'MSTY': 'mode_a'})
    assert out2['per_ticker']['MSTY']['price_growth_pct'] < 0


def test_projection_scenario_ignored_without_underlying_data():
    # Sin underlying_cagr_recent no se puede calibrar → cae al decaimiento normal (capado ≤0).
    results = {'MSTY': {'forward_yield': 60.0, 'shares_owned': 100, 'current_price': 20.0,
                        'price_cagr_recent': -25.0, 'underlying_cagr_recent': None}}
    out = logic.project_portfolio_forward(
        results, {'horizon_years': 2, 'drip': False, 'underlying_scenarios': {'MSTY': 50.0}},
        classify_map={'MSTY': 'mode_a'})
    e = out['per_ticker']['MSTY']
    assert e['decay_window'] != 'escenario' and e['price_growth_pct'] <= 0


def test_monte_carlo_scenario_lifts_median():
    results = {'MSTY': {'forward_yield': 60.0, 'shares_owned': 100, 'current_price': 20.0,
                        'price_cagr_recent': -83.0, 'underlying_cagr_recent': -67.0,
                        'volatilidad_anualizada': 70.0}}
    cm = {'MSTY': 'mode_a'}
    base = logic.monte_carlo_projection(results, {'horizon_years': 3}, classify_map=cm, n_paths=400, seed=11)
    bull = logic.monte_carlo_projection(
        results, {'horizon_years': 3, 'underlying_scenarios': {'MSTY': 80.0}},
        classify_map=cm, n_paths=400, seed=11)
    assert bull['final']['p50'] > base['final']['p50']


# ── v3.6: concentración por factor (#2), comparación vs subyacente (#1) ──

def test_ticker_factor_mapping():
    assert logic._ticker_factor('MSTY') == 'Bitcoin'      # MSTR → Bitcoin
    assert logic._ticker_factor('CONY') == 'Bitcoin'      # COIN → Bitcoin
    assert logic._ticker_factor('TSLY') == 'TSLA'         # sin mapeo → el subyacente
    assert logic._ticker_factor('X', {'underlying': 'Mercado'}) is None
    assert logic._ticker_factor('X', {}) is None


def test_factor_concentration_hidden_bitcoin():
    # MSTY (MSTR→Bitcoin) + CONY (COIN→Bitcoin) → factor Bitcoin con 2 tickers = correlación oculta
    results = {
        'MSTY': {'forward_yield': 60.0, 'market_value': 5000.0},
        'CONY': {'forward_yield': 50.0, 'market_value': 3000.0},
        'NVDY': {'forward_yield': 40.0, 'market_value': 2000.0},
    }
    fc = logic.build_factor_concentration(results)
    assert fc['top_factor'] == 'Bitcoin'
    assert fc['hidden_correlation'] is True
    btc = next(f for f in fc['factors'] if f['factor'] == 'Bitcoin')
    assert set(btc['tickers']) == {'MSTY', 'CONY'}
    assert abs(sum(f['income_share_pct'] for f in fc['factors']) - 100) < 0.5


def test_factor_concentration_single_factor_not_hidden():
    # Un solo YieldMax → no es "correlación oculta" (necesita ≥2 tickers en el factor)
    results = {'NVDY': {'forward_yield': 40.0, 'market_value': 2000.0}}
    fc = logic.build_factor_concentration(results)
    assert fc['hidden_correlation'] is False and fc['top_factor'] == 'NVDA'


def test_simulate_hold_value_invests_flow_and_reinvests_divs():
    idx = pd.date_range('2024-01-01', periods=3, freq='D')
    price = pd.Series([10.0, 10.0, 20.0], index=idx)      # precio 2x al final
    div = pd.Series([0.0, 0.0, 0.0], index=idx)
    flow = pd.Series([100.0, 0.0, 0.0], index=idx)        # $100 día 1 → 10 acciones
    assert logic._simulate_hold_value(price, div, flow) == pytest.approx(200.0)   # 10 × $20
    # dividendo por-acción $1 el día 2 (precio $10): +1 acción (10×1/10) → 11 × $20 = $220
    div2 = pd.Series([0.0, 1.0, 0.0], index=idx)
    assert logic._simulate_hold_value(price, div2, flow) == pytest.approx(220.0)


def test_underlying_exposure_includes_hold_comparison():
    results = {'NVDY': {'underlying_ticker': 'NVDA', 'underlying_cagr_recent': 42.0,
                        'price_cagr_recent': -22.0, 'underlying_hold_value': 13000.0,
                        'market_value': 9000.0, 'dividends_collected_cash': 2000.0,
                        'forward_yield': 40.0}}
    txt = ' '.join(logic.build_underlying_exposure(results, 'NVDY')['lines'])
    assert 'NVDA directo' in txt and '$13,000' in txt and '$11,000' in txt   # fund total = 9000+2000


# ── v3.7: forward yield rancio (posición que dejó de pagar) → None, no inflado ──

def test_forward_yield_stale_when_payments_stopped():
    # Pagos mensuales que PARARON a mediados de 2024 (posición transferida/vendida).
    rows = [{'Date': f'2024-{m:02d}-15', 'Action': 'Cash Dividend', 'Amount': 20.0} for m in range(1, 7)]
    hist = pd.DataFrame(rows); hist['Date'] = pd.to_datetime(hist['Date'])
    fy = logic.forward_realized_yield(hist, market_value=1000, today='2026-06-01')  # ~700 días después
    assert fy['stale'] is True and fy['forward_yield'] is None
    assert fy['realized_yield'] == 0.0          # nada cobrado en los últimos 12m


def test_forward_yield_not_stale_when_recent():
    rows = [{'Date': f'2026-{m:02d}-15', 'Action': 'Cash Dividend', 'Amount': 20.0} for m in range(1, 6)]
    hist = pd.DataFrame(rows); hist['Date'] = pd.to_datetime(hist['Date'])
    fy = logic.forward_realized_yield(hist, market_value=1000, today='2026-06-01')
    assert fy['stale'] is False and fy['forward_yield'] is not None


# ── Veredicto de salud del NAV (ROC destructivo vs contable) ───────────────────

def test_roc_health_destructive_high_roc_nav_falling():
    v = logic.classify_roc_health(roc_pct=95, price_cagr=-40, total_return_pct=-25, history_days=400)
    assert v["verdict"] == "destructive"
    assert "DESTRUCTIVO" in v["label"]


def test_roc_health_destructive_low_roc_but_nav_collapses():
    # ROC bajo, pero el NAV cae fuerte y el total return es negativo -> sigue siendo destructivo.
    v = logic.classify_roc_health(roc_pct=10, price_cagr=-30, total_return_pct=-15, history_days=400)
    assert v["verdict"] == "destructive"


def test_roc_health_accounting_high_roc_nav_rising():
    # ROC alto pero el NAV sube y el total return es positivo -> contable (pass-through).
    v = logic.classify_roc_health(roc_pct=80, price_cagr=12, total_return_pct=20, history_days=400)
    assert v["verdict"] == "accounting"
    assert "CONTABLE" in v["label"]


def test_roc_health_accounting_positive_total_return_flat_nav():
    v = logic.classify_roc_health(roc_pct=60, price_cagr=0.5, total_return_pct=8, history_days=400)
    assert v["verdict"] == "accounting"


def test_roc_health_mixed_flat_nav_no_signal():
    v = logic.classify_roc_health(roc_pct=55, price_cagr=-0.5, total_return_pct=None, history_days=400)
    assert v["verdict"] == "mixed"


def test_roc_health_insufficient_missing_inputs():
    assert logic.classify_roc_health(roc_pct=None, price_cagr=-40)["verdict"] == "insufficient"
    assert logic.classify_roc_health(roc_pct=90, price_cagr=None)["verdict"] == "insufficient"


def test_roc_health_insufficient_short_history():
    # Fondo joven: aunque parezca destructivo, no hay historia para afirmarlo.
    v = logic.classify_roc_health(roc_pct=95, price_cagr=-50, total_return_pct=-30, history_days=60)
    assert v["verdict"] == "insufficient"
    assert "corta" in v["reason"].lower()


def test_roc_health_insufficient_stale_19a():
    v = logic.classify_roc_health(roc_pct=95, price_cagr=-40, total_return_pct=-25,
                                  history_days=400, roc_asof_days=120)
    assert v["verdict"] == "insufficient"
    assert "desactualizado" in v["reason"].lower()


def test_roc_health_always_has_color_and_label():
    for v in (
        logic.classify_roc_health(95, -40, -25, history_days=400),
        logic.classify_roc_health(80, 12, 20, history_days=400),
        logic.classify_roc_health(55, -0.5, None, history_days=400),
        logic.classify_roc_health(None, None),
    ):
        assert v["color"].startswith("#") and v["label"] and v["reason"]


def test_roc_health_simple_layer_fields_present():
    v = logic.classify_roc_health(95, -40, -25, history_days=400)
    assert v["headline"] and v["plain"]
    assert v["gauge_score"] is not None and 0 <= v["gauge_score"] <= 100
    assert "encogiendo" in v["headline"].lower()


def test_roc_health_gauge_none_when_insufficient():
    assert logic.classify_roc_health(95, -50, -30, history_days=60)["gauge_score"] is None
    assert logic.classify_roc_health(None, None)["gauge_score"] is None


def test_roc_health_gauge_monotonic_with_nav():
    # Mas caida del NAV -> score mayor (mas cerca de "destruyendose").
    worse = logic.classify_roc_health(80, -50, -30, history_days=400)["gauge_score"]
    mid   = logic.classify_roc_health(80, -20, -10, history_days=400)["gauge_score"]
    good  = logic.classify_roc_health(80,  15,  20, history_days=400)["gauge_score"]
    assert worse > mid > good
    assert good == 0.0


def test_roc_health_destructive_tr_positive_has_nuance():
    v = logic.classify_roc_health(58, -36, 64, history_days=400)
    assert v["verdict"] == "destructive"
    assert "compensan" in v["plain"].lower()


def test_roc_health_headline_per_verdict():
    assert "sano" in logic.classify_roc_health(80, 12, 20, history_days=400)["headline"].lower()
    assert "medir" in logic.classify_roc_health(None, None)["headline"].lower()


# ── Auditoría del yield titular vs realidad (audit_advertised_yield) ────────────

def test_audit_advertised_match_within_tolerance():
    # titular 66.67 vs mecanismo 64.0 → dentro de banda → 'match'
    r = logic.audit_advertised_yield(66.67, 64.0, 45.0)
    assert r["verdict"] == "match"
    assert round(r["gap_real"], 2) == 21.67  # titular − realizado = dato educativo


def test_audit_advertised_ahead_when_titular_exceeds_mechanism():
    # titular muy por encima de lo que su propia fórmula da hoy
    r = logic.audit_advertised_yield(80.0, 50.0, 40.0)
    assert r["verdict"] == "ahead"
    assert r["gap_fwd"] == 30.0


def test_audit_advertised_behind():
    r = logic.audit_advertised_yield(40.0, 60.0, 55.0)
    assert r["verdict"] == "behind"


def test_audit_advertised_unknown_without_data():
    assert logic.audit_advertised_yield(None, 50.0, 40.0)["verdict"] == "unknown"
    assert logic.audit_advertised_yield(70.0, None, 40.0)["verdict"] == "unknown"


def test_advertised_distribution_rate_reads_yaml():
    # los fondos sembrados existen y devuelven float; un ticker inventado devuelve None
    msty = logic.advertised_distribution_rate("MSTY")
    assert msty is None or isinstance(msty, float)
    assert logic.advertised_distribution_rate("ZZZZ_NOPE") is None


# ── Hoja Excel: método tradicional vs vista honesta (build_hoja_excel) ──────────

def test_build_hoja_excel_naive_vs_honest():
    results = {
        "MSTY": {
            "pocket_investment": 4197.2, "total_dividends": 2574.54,
            "withheld_tax_total": 120.0, "market_value": 1131.78,
            "dividends_collected_cash": 2574.54, "last_payment": 28.85,
            "price_cagr": -81.5, "roc_percent": 90.0, "price_history_days": 500,
            "advertised_yield": 66.67, "forward_yield": 132.6, "realized_yield": 227.5,
            "yield_on_cost": 61.0,
        },
        "VOO": {"error": "crecimiento"},  # ignorado: no es mode_a si se filtra
    }
    out = logic.build_hoja_excel(results, classify_map={"MSTY": "mode_a", "VOO": "mode_b"})
    assert len(out["rows"]) == 1
    r = out["rows"][0]
    # método tradicional: inversión + dividendos (la fórmula engañosa)
    assert round(r["total_inv_naive"], 2) == round(4197.2 + 2574.54, 2)
    # honesto: valor + cash − inversión  (queda negativo → el income no cubrió la erosión)
    assert round(r["total_return"], 2) == round(1131.78 + 2574.54 - 4197.2, 2)
    # bruto = neto + NRA
    assert round(r["dividends_gross"], 2) == round(2574.54 + 120.0, 2)
    assert r["nav_health"]["verdict"] in ("destructive", "mixed", "accounting", "insufficient")
    assert r["audit"]["advertised"] == 66.67


def test_build_hoja_excel_roc_dollars_trap():
    # Ticker ficticio sin avisos 19a → roc_pct cae al estimado del broker (roc_percent).
    results = {
        "ZZZZ": {
            "pocket_investment": 4197.2, "total_dividends": 2574.54,
            "withheld_tax_total": 120.0, "market_value": 1131.78,
            "dividends_collected_cash": 2574.54, "last_payment": 28.85,
            "price_cagr": -81.5, "roc_percent": 90.0, "price_history_days": 500,
            "advertised_yield": 66.67, "forward_yield": 132.6, "realized_yield": 227.5,
            "yield_on_cost": 61.0,
        },
    }
    out = logic.build_hoja_excel(results, classify_map={"ZZZZ": "mode_a"})
    r = out["rows"][0]
    gross = 2574.54 + 120.0
    assert r["roc_pct"] == 90.0
    # ROC en dólares = % ROC × distribución bruta (no es una resta de costos).
    assert round(r["roc_dollars"], 2) == round(0.90 * gross, 2)
    # «Capital real aportado» = total_inv_naive − ROC$, siempre menor que el inflado.
    cap_real = r["total_inv_naive"] - r["roc_dollars"]
    assert cap_real < r["total_inv_naive"]
    # el total agrega roc_dollars
    assert round(out["totals"]["roc_dollars"], 2) == round(r["roc_dollars"], 2)
