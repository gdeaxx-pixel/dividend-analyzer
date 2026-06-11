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
