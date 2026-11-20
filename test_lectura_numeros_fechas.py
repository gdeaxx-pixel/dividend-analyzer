import glob
import io
import math

import pandas as pd
import pytest

import logic

NAN = float("nan")


@pytest.mark.parametrize("texto, coma, esperado", [
    ("1,000", False, 1000.0), ("1,000", True, 1.0),
    ("$1,234", False, 1234.0), ("$1,234", True, 1.234),
    ("-$12,000.00", False, -12000.0),
    ("1,234.56", False, 1234.56), ("1,234.56", True, 1234.56),
    ("1.234,56", False, 1234.56), ("1.234,56", True, 1234.56),
    ("12,50", False, 12.5), ("12,50", True, 12.5),
    ("1,5", False, 1.5), ("1,5", True, 1.5),
    ("-185,18", False, -185.18), ("-185,18", True, -185.18),
    ("($12.34)", False, -12.34), ("($12.34)", True, -12.34),
    ("(80.00)", False, -80.0), ("(80.00)", True, -80.0),
    ("-27,500", False, -27500.0), ("-27,500", True, -27.5),
    ("27.50", False, 27.5), ("27.50", True, 27.5),
    ("", False, None), ("--", False, None), ("N/A", False, None),
    (None, False, None), (NAN, False, None),
    ("", True, None), ("--", True, None), ("N/A", True, None),
    (None, True, None), (NAN, True, None),
    (1234.5, False, 1234.5), (1234.5, True, 1234.5),
])
def test_leer_numero_tabla(texto, coma, esperado):
    got = logic.leer_numero(texto, coma)
    if esperado is None:
        assert got is None
    else:
        assert got == pytest.approx(esperado, abs=1e-9)


def _cadena(contenido: bytes):
    raw, broker = logic.load_and_detect_csv(io.BytesIO(contenido))
    return broker, logic.normalize_csv(raw)


_ENC = ('"Transactions for account X as of 11/20/2025"\n'
        '"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"\n')


def test_schwab_compra_de_mil_acciones_y_montos_sin_decimales():
    contenido = (_ENC +
                 '"01/15/2025","Buy","SCHD","SCHWAB US DIV","1,000","$27.50","","-$27,500.00"\n'
                 '"01/16/2025","Qualified Dividend","SCHD","SCHWAB US DIV","","","","$1,234"\n'
                 '"01/17/2025","NRA Tax Adj","SCHD","SCHWAB US DIV","","","","($12.34)"\n').encode()
    broker, n = _cadena(contenido)
    assert broker == "schwab"
    assert n["Quantity"].tolist() == [1000.0, 0.0, 0.0]
    assert n["Amount"].tolist() == pytest.approx([-27500.0, 1234.0, -12.34])
    assert n["Price"].iloc[0] == 27.5


_IB_TRADES = (
    b'Statement,Header,Field Name,Field Value\nStatement,Data,BrokerName,Interactive Brokers LLC\n'
    b'Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,T. Price,C. Price,Proceeds,Comm/Fee,Basis,Realized P/L,Code\n'
    b'Trades,Data,Order,Stocks,USD,SCHD,"2025-01-16, 09:30:00","1,000",27.5,27.5,"-27,500",-1,27501,0,O\n'
    b'Dividends,Header,Currency,Date,Description,Amount\n'
    b'Dividends,Data,USD,2025-02-02,SCHD(US8085247976) Cash Dividend USD 0.25 per Share (Ordinary Dividend),250\n')


def test_ibkr_activity_proceeds_con_coma_de_miles():
    broker, n = _cadena(_IB_TRADES)
    assert broker == "ibkr"
    compra = n[n["Action"] == "Buy"].iloc[0]
    assert compra["Quantity"] == 1000.0
    assert compra["Amount"] == -27500.0
    assert compra["Price"] == 27.5


_IB_TH = (
    b'Transaction History,Header,Date,Account,Description,Transaction Type,Symbol,Quantity,Price,Gross Amount,Commission,Net Amount\n'
    b'Transaction History,Data,2025-01-15,U1,Buy,Buy,AAA,10,"12,50","-125,00",-1,"-126,00"\n'
    b'Transaction History,Data,2025-02-01,U1,Div,Dividend,AAA,-,-,"1.234,56",-,"1.234,56"\n'
    b'Transaction History,Data,2025-02-01,U1,Tax,Foreign Tax Withholding,AAA,-,-,-,-,"-185,18"\n')


def test_ibkr_transaction_history_con_coma_decimal():
    broker, n = _cadena(_IB_TH)
    assert broker == "ibkr"
    compra = n[n["Action"] == "Buy"].iloc[0]
    assert compra["Price"] == 12.5
    assert compra["Quantity"] == 10.0
    div = n[n["Action"] == "Dividend"].iloc[0]
    assert div["Amount"] == pytest.approx(1234.56)
    ret = n[n["Action"] == "Dividend - Foreign Tax Withholding"].iloc[0]
    assert ret["Amount"] == pytest.approx(-185.18)


def test_ingreso_schwab_parentesis_y_coma_decimal():
    inc = (b'"Investment Income Transactions as of 06/30/2025"\n'
           b'Transaction Date,Account Number,Account Name,Account Type,Security Description,Symbol,Security Type,Transaction Type,Transaction Amount,Income Type,\n'
           b'02/28/2025,...111,Ind,BROKERAGE,Fund A,TSLY,ETFs,Dividend,"1.234,50",Received,\n'
           b'03/28/2025,...111,Ind,BROKERAGE,Fund A,TSLY,ETFs,Dividend,(80.00),Received,\n'
           b'03/29/2025,...111,Ind,BROKERAGE,Fund A,TSLY,ETFs,Dividend,"1,5",Received,\n'
           b'04/28/2025,...111,Ind,BROKERAGE,Fund A,TSLY,ETFs,Dividend,40.00,Received,\n')
    d = logic.parse_schwab_income_csv(inc)
    assert d["Amount"].tolist() == pytest.approx([1234.5, -80.0, 1.5, 40.0])


def test_posiciones_con_parentesis_y_miles():
    pos = (b'"Positions for account X as of 11/20/2025"\n\n'
           b'Symbol,Description,Qty (Quantity),Price,Mkt Val (Market Value),Cost Basis,Asset Type\n'
           b'SCHD,x,"1,000",$27.5,"$27,500.00","$25,000.00",ETFs & Closed End Funds\n'
           b'JEPI,x,10,$55,($550.00),"($500.00)",ETFs\n')
    out = logic.parse_schwab_positions_csv(pos)
    assert out["SCHD"] == {"shares": 1000.0, "cost_basis": 25000.0, "market_value": 27500.0}
    assert out["JEPI"]["market_value"] == -550.0
    assert out["JEPI"]["cost_basis"] == -500.0


def test_safe_float_parentesis_y_coma():
    assert logic.safe_float("(12.34)") == -12.34
    assert logic.safe_float("1.234,5") == 1234.5
    assert logic.safe_float("12,5") == 12.5
    assert logic.safe_float("$1,000.5") == 1000.5
    assert logic.safe_float("--") == 0.0


_SUMAS_FIXTURES = {
    "fixtures/ib_synth_1/synthetic_transactions.csv":
        (11, 134.0, 288.0, -2483.4),
    "fixtures/schwab_synth_1/synthetic_transactions.csv":
        (21, 108.8515, 475.0, -1707.86),
    "fixtures/schwab_synth_2/synthetic_transactions.csv":
        (20, 120.0, 57.92, -3372.37),
    "fixtures/schwab_tda_synth/synthetic_transactions.csv":
        (22, 18.145, 1006.0, -1312.2),
}


@pytest.mark.parametrize("ruta", sorted(_SUMAS_FIXTURES))
def test_las_fixtures_se_leen_igual_que_antes(ruta):
    filas, qty, price, amount = _SUMAS_FIXTURES[ruta]
    with open(ruta, "rb") as f:
        _, n = _cadena(f.read())
    assert len(n) == filas
    assert n["Quantity"].sum() == pytest.approx(qty, abs=1e-6)
    assert n["Price"].sum() == pytest.approx(price, abs=1e-6)
    assert n["Amount"].sum() == pytest.approx(amount, abs=1e-6)


def test_la_columna_con_coma_decimal_lee_1_000_como_uno():
    contenido = (b'Date,Action,Ticker,Quantity,Price,Amount\n'
                 b'2025-01-15,Buy,AAA,10,"12,50","-125,00"\n'
                 b'2025-01-16,Buy,AAA,10,"1,000","-27,500"\n')
    _, n = _cadena(contenido)
    assert n["Price"].tolist() == [12.5, 1.0]
    assert n["Amount"].tolist() == pytest.approx([-125.0, -27.5])


def test_la_columna_con_miles_en_coma_no_se_vuelve_decimal():
    contenido = (b'Date,Action,Ticker,Quantity,Price,Amount\n'
                 b'2025-01-15,Buy,AAA,"1,000",5,"-27,500"\n'
                 b'2025-01-16,Buy,AAA,10,5,"-1,234.56"\n')
    _, n = _cadena(contenido)
    assert n["Quantity"].tolist() == [1000.0, 10.0]
    assert n["Amount"].tolist() == pytest.approx([-27500.0, -1234.56])
