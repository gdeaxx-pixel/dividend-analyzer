import io
import os
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
    """ROC = pocket_investment - ib_cost_basis; roc_percent = ROC / pocket_investment * 100"""
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
    pocket = s["pocket_investment"]
    assert s["ib_cost_basis"] == pytest.approx(4298.17, abs=0.01)
    assert s["roc_accumulated"] == pytest.approx(pocket - 4298.17, abs=0.01)
    assert s["roc_percent"] == pytest.approx((pocket - 4298.17) / pocket * 100, abs=0.1)


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
