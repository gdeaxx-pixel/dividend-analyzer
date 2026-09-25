import io
import os
import re
import sys

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, os.path.dirname(__file__))
import backtest
import logic
import price_cache
from ui.adapters import _tiene_datos, trg_real_data
from ui.heredadas import _agregados
from ui.validacion import _separar_excluidos


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

# Los mismos eventos por las dos rutas de IB. Las filas "Total" van a propósito: si llegaran
# a normalize_csv como datos, duplicarían el bruto y la retención.
IB_AS_CON_RETENCION = (
    b"Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,"
    b"Quantity,T. Price,Proceeds,Comm/Fee\n"
    b'Trades,Data,Order,Stocks,USD,SCHD,"2024-01-02, 09:30:00",10,100.00,-1000.00,-1.0\n'
    b"Dividends,Header,Currency,Date,Description,Amount\n"
    b"Dividends,Data,USD,2024-12-11,SCHD(US8085247976) Cash Dividend USD 0.61 per Share (Ordinary Dividend),6.10\n"
    b"Dividends,Data,USD,2025-03-26,SCHD(US8085247976) Cash Dividend USD 0.25 per Share (Ordinary Dividend),2.50\n"
    b"Dividends,Data,Total,,,8.60\n"
    b"Withholding Tax,Header,Currency,Date,Description,Amount,Code\n"
    b"Withholding Tax,Data,USD,2024-12-11,SCHD(US8085247976) Cash Dividend USD 0.61 per Share - US Tax,-1.83,\n"
    b"Withholding Tax,Data,USD,2025-03-26,SCHD(US8085247976) Cash Dividend USD 0.25 per Share - US Tax,-0.75,\n"
    b"Withholding Tax,Data,Total,,,-2.58,\n"
)

IB_TH_MISMOS_EVENTOS = (
    b"Transaction History,Header,Date,Account,Description,Transaction Type,Symbol,"
    b"Quantity,Price,Price Currency,Gross Amount,Commission,Net Amount\n"
    b"Transaction History,Data,2024-01-02,U123,SCHD Buy,Buy,SCHD,10,100.00,USD,-1000.00,-1.0,-1001.00\n"
    b"Transaction History,Data,2024-12-11,U123,SCHD Cash Dividend,Dividend,SCHD,-,-,-,6.10,-,6.10\n"
    b"Transaction History,Data,2024-12-11,U123,SCHD US Tax,Foreign Tax Withholding,SCHD,-,-,-,-1.83,-,-1.83\n"
    b"Transaction History,Data,2025-03-26,U123,SCHD Cash Dividend,Dividend,SCHD,-,-,-,2.50,-,2.50\n"
    b"Transaction History,Data,2025-03-26,U123,SCHD US Tax,Foreign Tax Withholding,SCHD,-,-,-,-0.75,-,-0.75\n"
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
    assert "Dividend" in df["Action"].values


def test_ib_activity_statement_normalizado_conserva_el_dividendo():
    """I1 (auditoría 2026-09-17). Trades trae «fecha, hora» y Dividends solo la fecha. Con las
    dos formas en la misma columna, normalize_csv infería el formato de la primera fila y
    descartaba el dividendo como NaT: los $75 desaparecían del bruto sin error ni aviso.
    El test de arriba no lo veía porque mira el df crudo, antes de normalizar."""
    raw, _ = logic.load_and_detect_csv(FakeFile(IB_ACTIVITY_STATEMENT))
    df = logic.normalize_csv(raw.copy())
    assert len(df) == len(raw) == 2
    fechas = {a: d.strftime("%Y-%m-%d") for a, d in zip(df["Action"], df["Date"])}
    assert fechas == {"Buy": "2024-01-15", "Dividend": "2024-01-20"}
    assert logic.build_dividend_tax_totals(df)["gross"] == pytest.approx(75.0)


def test_ib_activity_statement_lee_la_retencion_como_transaction_history():
    """I2 (auditoría 2026-09-17). parse_ibkr_csv leía solo Trades y Dividends: la sección
    Withholding Tax del Activity Statement se ignoraba y la retención salía en $0, con el neto
    igual al bruto. Los mismos eventos entrando por Transaction History (ruta validada contra el
    CSV real de IB) tienen que dar el mismo objeto fiscal, por ticker como lo lee
    analyze_portfolio. La cifra absoluta va aparte: la igualdad sola pasaría si las dos rutas se
    rompieran igual."""
    def _fiscal_schd(csv):
        raw, _ = logic.load_and_detect_csv(FakeFile(csv))
        df = logic.normalize_csv(raw.copy())
        schd = df[df["Ticker"] == "SCHD"]
        return logic.build_dividend_tax_totals(schd), logic.withheld_tax_total(schd), len(df)

    as_tot, as_ret, as_filas = _fiscal_schd(IB_AS_CON_RETENCION)
    th_tot, th_ret, th_filas = _fiscal_schd(IB_TH_MISMOS_EVENTOS)

    assert as_filas == th_filas == 5

    for k in ("gross", "withheld", "net"):
        assert as_tot[k] == pytest.approx(th_tot[k]), k
    for k in ("gross_by_year", "withheld_by_year", "net_by_year"):
        assert as_tot[k] == pytest.approx(th_tot[k]), k
    assert as_ret == pytest.approx(th_ret)

    assert as_tot["gross"] == pytest.approx(8.60)
    assert as_tot["withheld"] == pytest.approx(2.58)
    assert as_tot["net"] == pytest.approx(6.02)
    assert as_tot["withheld_by_year"] == pytest.approx({2024: 1.83, 2025: 0.75})
    assert as_ret == pytest.approx(2.58)


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
    """Valida el archivo IB real con FTW y Payment in Lieu incluidos (922 filas).

    Desde el fix de ingesta IB (rama fix/ingesta-ib-old-reversos), las filas
    'Foreign Tax Withholding' ya NO se funden en Action=='Dividend' puro: quedan
    como 'Dividend - Foreign Tax Withholding' (sigue conteniendo 'dividend', así
    que analyze_portfolio las sigue neteando en dividends_collected_cash igual que
    antes) para que withheld_tax_total() pueda detectarlas por separado — antes
    reportaba $0 de retención para todos los tickers IB.
    """
    base = os.path.dirname(__file__)
    real_path = os.path.join(base, "interactive_brokers_data",
                             "U15179613.TRANSACTIONS.20240820.20260514.csv")
    if not os.path.exists(real_path):
        pytest.skip("Archivo IB real no disponible")
    with open(real_path, "rb") as f:
        df, broker = logic.load_and_detect_csv(FakeFile(f.read(), "real_ib.csv"))
    assert broker == "ibkr"
    assert len(df) == 922
    # Foreign Tax Withholding: rastro explícito propio, con monto negativo (cargos) y
    # positivo (reversos de los splits inversos .OLD, ya fusionados en el ticker base).
    ftw_rows = df[df["Action"] == "Dividend - Foreign Tax Withholding"]
    assert len(ftw_rows) == 462, "Deben sobrevivir las 462 filas de retención del CSV crudo"
    assert (ftw_rows["Amount"] < 0).sum() > 0, "Debe haber cargos (monto negativo)"
    assert (ftw_rows["Amount"] > 0).sum() > 0, "Debe haber reversos .OLD (monto positivo)"
    # Normalización TSLY.OLD → TSLY (y MSTY.OLD, CONY.OLD)
    assert "TSLY.OLD" not in df["Ticker"].values, "TSLY.OLD debe normalizarse a TSLY"
    assert "MSTY.OLD" not in df["Ticker"].values, "MSTY.OLD debe normalizarse a MSTY"
    assert "CONY.OLD" not in df["Ticker"].values, "CONY.OLD debe normalizarse a CONY"
    # 283 Dividend puro + 462 FTW = 745 filas etiquetadas como dividendo en sentido amplio
    # (dividendos ordinarios + Payment in Lieu, sin contar FTW aparte)
    assert len(df[df["Action"] == "Dividend"]) == 283
    assert len(df[df["Action"] == "Buy"]) == 153
    df_clean = logic.normalize_csv(df)
    assert len(df_clean) > 0


# ── withheld_tax_total — IB: .OLD fusionado + reversos neteados ───────────────
# (fix/ingesta-ib-old-reversos). Cifras verificadas por Opus contra
# real_examples/interactive_brokers_data/1 (462 filas 'Foreign Tax Withholding' crudas).
# ESCALA declarada en cada aserción — por ticker vs portafolio no son comparables entre sí
# (ver Obsidian feedback_dividend-invariante-roc-nra: un audit previo mezcló ambas escalas).

def _load_real_ib_1():
    """DataFrame normalizado del caso real ib_1 (real_examples/), o skip si no está disponible
    (dato privado, no versionado — igual que el resto de real_examples/)."""
    base = os.path.dirname(__file__)
    real_dir = os.environ.get(
        "DIVIDEND_REAL_EXAMPLES_DIR", os.path.join(base, "real_examples"))
    csv_path = os.path.join(
        real_dir, "interactive_brokers_data", "1",
        "U15179613.TRANSACTIONS.20240820.20260514.csv")
    if not os.path.exists(csv_path):
        pytest.skip("real_examples/interactive_brokers_data/1 no disponible")
    with open(csv_path, "rb") as f:
        df, broker = logic.load_and_detect_csv(FakeFile(f.read(), "ib_1.csv"))
    assert broker == "ibkr"
    return logic.normalize_csv(df)


@pytest.mark.parametrize("ticker,expected_net", [
    ("MSTY", -545.52),   # cargos -2056.12 + reversos .OLD +1510.60
    ("TSLY", -495.01),   # cargos -975.52  + reversos .OLD +480.51
    ("CONY", -202.98),   # cargos -890.02  + reversos .OLD +687.04
])
def test_ib_withheld_tax_neto_por_ticker(ticker, expected_net):
    """ESCALA: por ticker (NO el portafolio). Retención neta = cargos + reversos .OLD,
    con el ticker .OLD ya fusionado al base por normalize_csv."""
    dfc = _load_real_ib_1()
    sub = dfc[dfc["Ticker"] == ticker]
    assert len(sub) > 0, f"{ticker}: sin filas tras normalizar"
    neto = logic.withheld_tax_total(sub)
    assert neto == pytest.approx(-expected_net, abs=0.01), (
        f"{ticker}: retención neta {neto} != {-expected_net} esperado (escala: por ticker)")


def test_ib_withheld_tax_neto_portafolio_completo():
    """ESCALA: portafolio completo (los 38 tickers de las 462 filas 'Foreign Tax
    Withholding' del CSV crudo, no solo los 9 reconocidos por analyze_portfolio).
    NO comparar este número contra el de un ticker individual — son escalas distintas."""
    dfc = _load_real_ib_1()
    neto_total = logic.withheld_tax_total(dfc)
    assert neto_total == pytest.approx(2121.43, abs=0.01), (
        f"retención neta del portafolio completo {neto_total} != 2121.43 (escala: portafolio)")


def test_ib_withheld_tax_no_rompe_schwab():
    """No-regresión (fixtures/schwab_synth_2, versionado): el fix de IB no debe tocar el
    resultado ya correcto de Schwab. MSTY: withheld=138.6 (30% de 462 bruto), cash=462.0."""
    raw = open(os.path.join(os.path.dirname(__file__),
                             "fixtures", "schwab_synth_2",
                             "synthetic_transactions.csv"), "rb").read()
    df, broker = logic.load_and_detect_csv(FakeFile(raw, "schwab_synth_2.csv"))
    assert broker == "schwab"
    dfc = logic.normalize_csv(df)
    sub = dfc[dfc["Ticker"] == "MSTY"]
    assert logic.withheld_tax_total(sub) == pytest.approx(138.6, abs=0.01)
    res = logic.analyze_portfolio(dfc, version="TEST_SCHWAB_SYNTH_2")
    r = res.get("MSTY", {})
    assert r.get("withheld_tax_total") == pytest.approx(138.6, abs=0.01)
    assert r.get("dividends_collected_cash") == pytest.approx(462.0, abs=0.01)


@pytest.mark.parametrize("ticker", ["SMCY", "NKE"])
def test_ib_smcy_nke_no_se_pierden_en_ingesta_solo_en_clasificacion(ticker):
    """SMCY y NKE tienen filas de retención en el CSV crudo y NO aparecen en la salida de
    analyze_portfolio — pero la causa NO es la ingesta (fuera del alcance de este PR, que es
    SOLO la capa de ingesta): withheld_tax_total() sí calcula su retención correctamente sobre
    el df normalizado (la fusión .OLD y el neteo de reversos aplican igual a cualquier ticker).

    La pérdida ocurre después, en analyze_portfolio (logic.py ~1052): classify_tickers()
    los marca 'mode_skip' → 'reason': 'not_known_etf' y el ticker nunca entra al loop que
    llama a withheld_tax_total() por ticker. Es el filtro v2.1 "descartar tickers no
    reconocidos como ETF de largo plazo" (NKE es una acción de crecimiento normal, no un
    fondo de dividendos — correcto excluirla; SMCY sí es un fondo YieldMax pero falta en
    knowledge/instruments.yaml — tarea de /aprende-portafolio, no de este PR).
    """
    dfc = _load_real_ib_1()
    sub = dfc[dfc["Ticker"] == ticker]
    assert len(sub) > 0, f"{ticker}: debe sobrevivir la ingesta con filas propias"
    assert logic.withheld_tax_total(sub) > 0, (
        f"{ticker}: la ingesta SÍ calcula su retención; no se pierde ahí")
    res = logic.analyze_portfolio(dfc)
    assert res.get(ticker, {}).get("skipped") is True
    assert res.get(ticker, {}).get("reason") == "not_known_etf", (
        f"{ticker}: se esperaba que se filtrara por clasificación de instrumento "
        "(not_known_etf), no por otra causa — si esto cambia, la Fase 0 debe revisarse")


@pytest.mark.parametrize("ticker,esperado", [
    ("MSTY", {2026: 23.25}),   # positiva huérfana 2026-01-26 = reembolso ROC genuino
    ("TSLY", {2026: 7.31}),    # ídem
    ("CONY", {}),              # todas sus positivas emparejan con una negativa gemela
])
def test_ib_observed_refund_separa_reverso_de_split_de_reembolso_genuino(ticker, esperado):
    """Resuelto 2026-08-29 (antes: exclusión de IB en bloque). El clasificador único
    `_classify_tax_rows` empareja los reversos de split .OLD 1:1 con su negativa gemela
    (mismo día, |importe|, ticker) y los deja fuera; las positivas HUÉRFANAS —el crédito de
    reclasificación ROC que IB acredita en ene–mar— sí se cuentan. Antes esta función
    excluía IB entero y tiraba a la basura reembolsos reales."""
    dfc = _load_real_ib_1()
    sub = dfc[dfc["Ticker"] == ticker]
    assert len(sub) > 0
    assert logic.withheld_tax_total(sub) > 0, "la retención neta SÍ debe calcularse"
    obs = logic.observed_tax_refund_by_year(sub)
    assert {y: round(v, 2) for y, v in obs.items()} == esperado, (
        f"{ticker}: los reversos .OLD no cuentan; las huérfanas ROC sí")
    # Invariante que lo ata: al cobro == neteado + ya devuelto, exacto.
    al_cobro = round(sum(logic.withheld_at_payment_by_year(sub).values()), 2)
    devuelto = round(sum(obs.values()), 2)
    assert al_cobro == pytest.approx(logic.withheld_tax_total(sub) + devuelto, abs=0.01)


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


# ── F5 — una sola fecha de valoración (auditoría 2026-09-18) ───────────────────────
#
# `unrealized.market_value` usaba el último cierre CON DATO (`_closes.index[-1]`), pero
# `holding_days_ponderado` se anclaba al reloj de HOY (`ultimo_dia`/`pd.Timestamp.today()`
# vía `today=None`) o a la última fila del CSV — dos fechas distintas para el mismo
# tramo/tenencia. El fix pasa `today` explícito = la fecha del cierre que ya se usa para
# `market_value`, así que tenencia y valor de mercado miden contra la MISMA fecha.

def test_f5_tenencia_cuenta_hasta_la_fecha_de_valoracion():
    """Unitario sobre `build_capital_gains` (misma forma de `ticker_df` que
    `test_ganancias_capital.py::test_corte_de_dos_anios_por_un_dia_a_cada_lado`:
    Date/Action/Symbol/Quantity/Price/Amount). Compra el 2024-01-01; con
    `today=2026-01-10` (740 días desde la compra) el tramo cruza a `ge_2y`. Sin
    `today` (None), el motor cae a la última fila del CSV (2025-12-01, 700 días) y
    sigue en `lt_2y` — confirma que `today` es lo que decide, no un reloj interno
    distinto."""
    df = pd.DataFrame([
        ('2024-01-01', 'Buy', 'AAA', 100, 10.00, -1000.00),
        ('2025-12-01', 'Dividend', 'AAA', 0, 0.0, 1.00),   # última fila del CSV
    ], columns=['Date', 'Action', 'Symbol', 'Quantity', 'Price', 'Amount'])

    con_fecha = logic.build_capital_gains(df, 'AAA', market_price=20.00, today='2026-01-10')
    u = con_fecha['unrealized']
    assert u['holding_days_ponderado'] == 740
    assert u['tramo'] == 'ge_2y'

    sin_fecha = logic.build_capital_gains(df, 'AAA', market_price=20.00, today=None)
    u2 = sin_fecha['unrealized']
    assert u2['holding_days_ponderado'] == 700
    assert u2['tramo'] == 'lt_2y'


def test_f5_analyze_portfolio_pasa_la_fecha_del_ultimo_cierre(monkeypatch):
    """`fetch_market_data` trae cierres hasta 2026-01-09 y una barra MÁS RECIENTE
    (2026-01-12) sin dato (`Close=NaN`, fin de semana / feed incompleto). `_closes.dropna()`
    descarta esa barra, así que la fecha de VALORACIÓN real es 2026-01-09 — la misma que ya
    fija `current_price`/`market_value`. `build_capital_gains` debe recibir exactamente esa
    fecha por `today`, y el dict del ticker debe publicarla en `valuation_date`."""
    df = _roc_norm_df([("2024-01-01", "Buy", "MSTY", 100, -1000.0)])

    def mock_fetch(ticker, start_date):
        idx = pd.DatetimeIndex(["2026-01-09", "2026-01-12"])
        data = pd.DataFrame(
            {"Close": [50.0, float("nan")], "Dividends": [0.0, 0.0],
             "Stock Splits": [0.0, 0.0]}, index=idx)
        return data, None

    monkeypatch.setattr(logic, "fetch_market_data", mock_fetch)

    capturado = {}
    original_bcg = logic.build_capital_gains

    def _spy(*args, **kwargs):
        capturado["today"] = kwargs.get("today")
        return original_bcg(*args, **kwargs)

    monkeypatch.setattr(logic, "build_capital_gains", _spy)

    results = logic.analyze_portfolio(df, version="TEST_F5")
    s = results["MSTY"]
    assert s["valuation_date"] == "2026-01-09"
    assert capturado["today"] == pd.Timestamp("2026-01-09")


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
    # 19a sintético: sin esto el cierre fiscal REAL de MSTY 2024 (0%, roc_ici.yaml) pisa el año.
    monkeypatch.setattr(logic, "load_roc_ici", lambda: {})
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


_ROC_80 = lambda: {"MSTY": {"weighted_pct": 80.0,
                            "per_distribution": [{"date": "2024-10-01", "roc_pct": 80.0}]}}


def test_roc_19a_no_cambia_por_reinvertir(monkeypatch):
    """F1 (auditoría 2026-09-17). El % del 19a es de la distribución BRUTA, y reinvertirla no
    la cambia. La rama DRIP tomaba la compra de acciones (el neto tras la retención) como si
    fuera la distribución: con bruto $100, retención $30 y 80% de ROC daba $56 en vez de $80,
    y la base ajustada $1,014 en vez de $990 ($1,070 aportados − $80)."""
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    monkeypatch.setattr(logic, "load_roc_19a", _ROC_80)
    # 19a sintético: sin esto el cierre fiscal REAL de MSTY 2024 (0%, roc_ici.yaml) pisa el año.
    monkeypatch.setattr(logic, "load_roc_ici", lambda: {})
    compra = ("2024-09-01", "Buy", "MSTY", 50, -1000.0)
    efectivo = _roc_norm_df([
        compra,
        ("2024-10-01", "Cash Dividend", "MSTY", 0, 100.0),
        ("2024-10-01", "NRA Tax Adj", "MSTY", 0, -30.0),
    ])
    drip = _roc_norm_df([
        compra,
        ("2024-10-01", "Reinvest Dividend", "MSTY", 0, 100.0),
        ("2024-10-01", "NRA Tax Adj", "MSTY", 0, -30.0),
        ("2024-10-01", "Reinvest Shares", "MSTY", 3.5, -70.0),
    ])
    s_ef = logic.analyze_portfolio(efectivo)["MSTY"]
    s_dr = logic.analyze_portfolio(drip)["MSTY"]

    assert s_ef["roc_source"] == s_dr["roc_source"] == "19a"
    assert s_dr["roc_accumulated"] == pytest.approx(s_ef["roc_accumulated"])
    assert s_dr["roc_accumulated"] == pytest.approx(80.0)
    u = s_dr["capital_gains"]["unrealized"]
    assert u["basis"] == pytest.approx(1070.0)
    assert u["basis_roc_adjusted"] == pytest.approx(990.0)


def test_roc_19a_se_aplica_al_bruto_del_objeto_fiscal_ib(monkeypatch):
    """F1, convención IB. La base del ROC se reconstruía aparte del objeto fiscal: contaba como
    distribución todo monto positivo con «dividend» en el Action —también el reverso de una
    retención— e ignoraba las reversas de dividendo. En el CSV real de IB eso llevó la base de
    MSTY a $9,778.33 contra $7,224.59 de bruto reconciliado, y el ROC ($7,773.87) por encima
    del bruto entero. Aquí: un pago que IB revierte un día y re-emite al siguiente (el día de
    la reversa queda en negativo y tiene que restar), y una retención revertida."""
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    monkeypatch.setattr(logic, "load_roc_19a", _ROC_80)
    # 19a sintético: sin esto el cierre fiscal REAL de MSTY 2024 (0%, roc_ici.yaml) pisa el año.
    monkeypatch.setattr(logic, "load_roc_ici", lambda: {})
    df = _roc_norm_df([
        ("2024-09-01", "Buy", "MSTY", 50, -1000.0),
        ("2024-10-01", "Dividend", "MSTY", 0, 100.0),
        ("2024-10-01", "Dividend - Foreign Tax Withholding", "MSTY", 0, -30.0),
        ("2024-10-08", "Dividend", "MSTY", 0, -100.0),
        ("2024-10-08", "Dividend - Foreign Tax Withholding", "MSTY", 0, 30.0),
        ("2024-10-08", "Dividend - Foreign Tax Withholding", "MSTY", 0, -30.0),
        ("2024-10-09", "Dividend", "MSTY", 0, 100.0),
    ])
    s = logic.analyze_portfolio(df)["MSTY"]

    assert s["roc_source"] == "19a"
    assert s["dividends_gross_total"] == pytest.approx(100.0)
    assert s["roc_accumulated"] == pytest.approx(80.0)


def test_roc_19a_nunca_supera_el_bruto_en_el_caso_real_ib():
    """Ancla externa de F1: el bruto de `ib_1` está reconciliado contra el extracto de IB. El ROC
    es una parte de la distribución, así que no puede superarlo, y con la ruta 19a es
    exactamente su % aplicado a ese bruto."""
    from conftest import frozen_price_cache
    df = _load_real_ib_1()
    with frozen_price_cache():
        res = logic.analyze_portfolio(df)
    fondos_19a = {t: s for t, s in res.items() if s.get("roc_source") == "19a"}
    assert {"MSTY", "CONY", "TSLY", "NVDY"} <= set(fondos_19a)
    for t, s in fondos_19a.items():
        bruto = s["dividends_gross_total"]
        assert s["roc_accumulated"] <= bruto + 0.01, t
        # roc_percent se publica redondeado a 2 decimales: ±0.005 pp sobre el bruto.
        redondeo = bruto * 0.005 / 100 + 0.01
        assert s["roc_accumulated"] == pytest.approx(bruto * s["roc_percent"] / 100, abs=redondeo), t


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


def _schwab_np(monkeypatch, filas):
    from ui.adapters import cashflow_data
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    s = logic.analyze_portfolio(_roc_norm_df(filas))["MSTY"]
    return s, cashflow_data(s, "MSTY")["RESULTADO"]


def test_net_profit_no_resta_la_retencion_de_lo_reinvertido(monkeypatch):
    """F2 (auditoría 2026-09-17). La compra DRIP ya es neta de retención: sus acciones están en
    `market_value`. Restar esa retención del efectivo (que es $0) la descontaba otra vez:
    bruto $100, retención $30, DRIP $70 -> net_profit $40 en lugar de $70, mientras cashflow
    mostraba $70 para la misma posición."""
    s, resultado_cashflow = _schwab_np(monkeypatch, [
        ("2024-09-01", "Buy", "MSTY", 50, -1000.0),
        ("2024-10-01", "Reinvest Dividend", "MSTY", 0, 100.0),
        ("2024-10-01", "NRA Tax Adj", "MSTY", 0, -30.0),
        ("2024-10-01", "Reinvest Shares", "MSTY", 3.5, -70.0),
    ])
    assert s["market_value"] == pytest.approx(1070.0)
    assert s["net_profit"] == pytest.approx(70.0)
    assert s["net_profit"] == pytest.approx(resultado_cashflow)


def test_net_profit_resta_solo_la_retencion_de_lo_cobrado_en_efectivo(monkeypatch):
    """F2, caso mixto: una distribución cobrada en efectivo y otra reinvertida, cada una con su
    retención. Solo la del efectivo sale del efectivo: 1070 + (100 − 30) − 1000 = 140. Restar
    las dos da 110; no restar ninguna, 170."""
    s, resultado_cashflow = _schwab_np(monkeypatch, [
        ("2024-09-01", "Buy", "MSTY", 50, -1000.0),
        ("2024-10-01", "Cash Dividend", "MSTY", 0, 100.0),
        ("2024-10-01", "NRA Tax Adj", "MSTY", 0, -30.0),
        ("2024-11-01", "Reinvest Dividend", "MSTY", 0, 100.0),
        ("2024-11-01", "NRA Tax Adj", "MSTY", 0, -30.0),
        ("2024-11-01", "Reinvest Shares", "MSTY", 3.5, -70.0),
    ])
    assert s["withheld_tax_total"] == pytest.approx(60.0)
    assert s["net_profit"] == pytest.approx(140.0)
    assert s["net_profit"] == pytest.approx(resultado_cashflow)


_COMPRA_MSTY = ("2024-09-01", "Buy", "MSTY", 50, -1000.0)


@pytest.mark.parametrize("filas", [
    [_COMPRA_MSTY,
     ("2024-10-01", "Cash Dividend", "MSTY", 0, 100.0),
     ("2024-10-01", "NRA Tax Adj", "MSTY", 0, -30.0)],
    [_COMPRA_MSTY,
     ("2024-10-01", "Reinvest Dividend", "MSTY", 0, 100.0),
     ("2024-10-01", "NRA Tax Adj", "MSTY", 0, -30.0),
     ("2024-10-01", "Reinvest Shares", "MSTY", 3.5, -70.0)],
], ids=["efectivo", "drip"])
def test_salud_nav_publica_el_mismo_retorno_que_roi_y_cashflow(monkeypatch, filas):
    """F3 (auditoría 2026-09-17). Salud NAV recalculaba el retorno con
    `dividends_collected_cash`, que en Schwab es BRUTO: bruto $100 y retención $30 daban 10%
    mientras ROI y cashflow decían 7%. Las tres vistas del mismo retorno tienen que coincidir,
    cobrado en efectivo o reinvertido."""
    from ui.adapters import salud_nav_data
    s, resultado_cashflow = _schwab_np(monkeypatch, filas)
    tr = salud_nav_data("MSTY", s)["total_return_pct"]
    assert tr == pytest.approx(7.0)
    assert tr == pytest.approx(s["roi_percent"])
    assert tr == pytest.approx(resultado_cashflow / s["pocket_investment"] * 100)


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


# ── Drawdown sobre riqueza unitizada (TWR) — C·5/F4 ─────────────────────────────

def test_f4_drawdown_parte_de_la_riqueza_inicial():
    """Riqueza 1.0 -> 0.5 (-50%) -> 0.55 (+10%): el mínimo de la serie de drawdown
    debe ser -50.0, medido desde la riqueza inicial de 1.0 (el primer pico)."""
    mn, serie = logic._drawdown_twr([-0.5, 0.1])
    assert mn == pytest.approx(-50.0)
    assert len(serie) == 2


def test_f4_drawdown_es_desde_el_pico_corriente():
    """Riqueza 1 -> 0.5 -> 2.0 -> 1.5: el pico corriente en el último tramo es 2.0
    (no el pico global inicial de 1.0), así que la caída final es -25%, pero el
    MÍNIMO de toda la serie sigue siendo -50% (el primer tramo). Con pico global fijo
    en 1.0 el resultado sería -75% en el último punto (1.5 vs 1.0*2.0 mal referenciado)."""
    mn, serie = logic._drawdown_twr([-0.5, 3.0, -0.25])
    assert mn == pytest.approx(-50.0)
    assert serie.iloc[-1] == pytest.approx(-25.0)


def test_f4_venta_a_precio_constante_no_es_caida(monkeypatch):
    """Vender a precio constante no debe leerse como una caída de riqueza: antes del fix,
    el drawdown se medía sobre 'User Total Value' (valor absoluto de la cartera), así que
    una venta que reduce el valor de mercado (sin que el precio se mueva) contaba como
    drawdown falso. Sobre la riqueza unitizada (TWR) el resultado debe ser 0.0."""
    csv = (
        b"Transaction History,Header,Date,Account,Description,Transaction Type,"
        b"Symbol,Quantity,Price,Price Currency,Gross Amount,Commission,Net Amount\n"
        b"Transaction History,Data,2025-01-01,U123,Buy SCHB,Buy,SCHB,10,10.00,USD,-100.00,-1.0,-101.00\n"
        b"Transaction History,Data,2025-01-20,U123,Sell SCHB,Sell,SCHB,-5,10.00,USD,50.00,-1.0,49.00\n"
    )
    df, _ = logic.load_and_detect_csv(FakeFile(csv))
    df_clean = logic.normalize_csv(df)

    idx = pd.date_range("2025-01-01", "2025-02-15", freq="D")  # 46 días, precio constante
    def mock_fetch(ticker, start_date):
        data = pd.DataFrame(
            {"Close": [10.0] * len(idx), "Dividends": [0.0] * len(idx),
             "Stock Splits": [0.0] * len(idx)},
            index=idx,
        )
        return data, None

    monkeypatch.setattr(logic, "fetch_market_data", mock_fetch)
    results = logic.analyze_portfolio(df_clean, version="TEST_DD_VENTA")

    assert "SCHB" in results
    max_dd = results["SCHB"]["max_drawdown"]
    assert max_dd is not None, "la base debe producir una serie de drawdown (con precio constante todo el tramo, si no hay serie el test no discrimina)"
    assert max_dd == pytest.approx(0.0, abs=1e-6)


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
        {'MSTY': {'pocket_investment': 10000, 'market_value': 6000, 'dividends_collected_cash': 5000,
                  'net_profit': 1000}}, 'MSTY')
    txt = ' '.join(comp['lines'])
    assert comp['lines']                      # no vacío
    assert 'income' in txt and 'compensó' in txt
    assert 'retorno total +$1,000' in txt

    deficit = logic.build_interpretation(
        {'MSTY': {'pocket_investment': 10000, 'market_value': 6000, 'dividends_collected_cash': 1000,
                  'net_profit': -3000}}, 'MSTY')
    assert 'todavía no cubre' in ' '.join(deficit['lines'])


def test_build_interpretation_unknown_no_fabrication():
    """Ticker fuera del YAML: solo sintetiza los números, NO inventa conocimiento."""
    out = logic.build_interpretation(
        {'ZZZZ': {'pocket_investment': 1000, 'market_value': 1200, 'dividends_collected_cash': 50,
                  'net_profit': 250}}, 'ZZZZ')
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
        'MSTY': {'pocket_investment': 10000, 'market_value': 6000, 'dividends_collected_cash': 5000,
                 'net_profit': 1000},
        'XLK':  {'pocket_investment': 2000,  'market_value': 3500, 'dividends_collected_cash': 20,
                 'net_profit': 1520},
        'NVDL': {'pocket_investment': 1000,  'market_value': 1100, 'dividends_collected_cash': 0,
                 'net_profit': 100},
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


# ── project_income con el reloj congelado (fixtures/schwab_synth_2) ───────────
# La fixture es un export CONGELADO de Schwab ('as of 08/08/2026') con 12 filas 'Estimated' de
# fecha ABSOLUTA. Evaluada con el reloj de hoy caduca sola: cada mes cae una fila fuera de la
# ventana de 365 días y `schwab_proj` baja ($900 -> $825 en sep-2026 -> $750 en oct...). Por eso
# se pinea contra `as_of`, no contra hoy. Si esto falla, se congela el reloj — no se re-pinea.

def _income_schwab_synth_2():
    """El income CSV real de fixtures/schwab_synth_2, parseado por el mismo camino de la app."""
    raw = open(os.path.join(os.path.dirname(__file__), "fixtures", "schwab_synth_2",
                            "synthetic_investment_income.csv"), "rb").read()
    inc = logic.parse_schwab_income_csv(raw)
    return inc[0] if isinstance(inc, tuple) else inc


def test_project_income_fixture_congelada_en_as_of():
    """Ground truth de la fixture evaluada en la fecha de su propia cabecera: 12 x $75 = $900."""
    m = logic.project_income(_income_schwab_synth_2(), None, today="2026-08-08")["MSTY"]
    assert m["schwab_proj"] == pytest.approx(900.0, abs=0.01)
    assert m["our_proj"] == pytest.approx(600.0, abs=0.01)       # (58+50+42)/3 = $50 x 12
    assert m["overstatement_pct"] == pytest.approx(50.0, abs=0.01)
    assert m["payments_per_year"] == 12


def test_project_income_ventana_cuenta_solo_las_estimated_futuras():
    """LA TRAMPA. Un mes después del 'as of', la fila del 08/31/2026 ya es pasado: quedan 11 x $75.

    Este test es el que distingue "$900 porque contó las 12 filas futuras" de "$900 porque no
    contó ninguna": cuando NINGUNA 'Estimated' cae en la ventana, `project_income` no da $0, cae
    al fallback (último Estimated x ppy = 75 x 12) que devuelve $900 por coincidencia aritmética.
    Un test que solo asertara 900 pasaría con el filtro `est_future` completamente roto. Este no.
    """
    m = logic.project_income(_income_schwab_synth_2(), None, today="2026-09-01")["MSTY"]
    assert m["schwab_proj"] == pytest.approx(825.0, abs=0.01)     # 11 x $75, no 12
    assert m["overstatement_pct"] == pytest.approx(37.5, abs=0.01)
    assert m["our_proj"] == pytest.approx(600.0, abs=0.01)        # el run-rate NO depende del reloj


def test_project_income_today_none_sigue_siendo_hoy():
    """El default de producción no cambia: `today=None` == omitir el argumento == hoy."""
    inc = _income_schwab_synth_2()
    hoy = logic.project_income(inc)["MSTY"]
    explicito = logic.project_income(inc, None, today=None)["MSTY"]
    assert hoy == explicito
    congelado = logic.project_income(inc, None, today=pd.Timestamp.today().normalize())["MSTY"]
    assert hoy["schwab_proj"] == pytest.approx(congelado["schwab_proj"], abs=0.01)


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


def test_dividend_events_excludes_reinvest_shares_and_tax():
    """Fixture con LAS DOS convenciones y una REVERSA de cada tipo (IB emite filas de
    reversa con el mismo Action y signo contrario: 'Dividend' negativa y 'Withholding'
    positiva — reclasificaciones que se anulan entre sí). Antes este test solo usaba la
    convención Schwab ('NRA Tax Adj', sin 'dividend' en el Action) y estaba VERDE mientras
    `_dividend_events` inflaba el bruto IB en +55–78% medido (abs() por fila convertía cada
    reversa en una suma, y las filas 'Dividend - Foreign Tax Withholding' entraban como
    dividendo). Economía idéntica en ambas convenciones: bruto 22.

    Schwab: 10+10+12 = 32 (la fila 'NRA Tax Adj' nunca tuvo 'dividend').
    IB:     10 −2 (reversa Dividend) +12 = 20; las filas de impuesto (y su reversa) se
            EXCLUYEN por el predicado único (`_is_tax_row_action`), no se abs()ean.
    """
    # Convención Schwab (retención en fila aparte).
    hist_schwab = _div_hist([
        {'Date': '2025-09-15', 'Action': 'Qualified Dividend', 'Amount': 10},
        {'Date': '2025-10-15', 'Action': 'Reinvest Dividend', 'Amount': 10},
        {'Date': '2025-10-15', 'Action': 'Reinvest Shares', 'Amount': -7},   # compra neta → omitir
        {'Date': '2025-11-15', 'Action': 'NRA Tax Adj', 'Amount': -3},        # impuesto → omitir
        {'Date': '2025-11-15', 'Action': 'Cash Dividend', 'Amount': 12},
    ])
    ev = logic._dividend_events(hist_schwab)
    assert len(ev) == 3
    assert ev.sum() == pytest.approx(32.0)

    # Convención IB (retención PLEGADA en la fila, que comparte 'dividend') + reversas.
    hist_ib = _div_hist([
        {'Date': '2025-09-15', 'Action': 'Dividend', 'Amount': 10},
        {'Date': '2025-09-15', 'Action': 'Dividend', 'Amount': -2},           # reversa → resta
        {'Date': '2025-10-15', 'Action': 'Dividend', 'Amount': 12},
        {'Date': '2025-10-15', 'Action': 'Reinvest Shares', 'Amount': -7},   # compra neta → omitir
        {'Date': '2025-11-15', 'Action': 'Dividend - Foreign Tax Withholding', 'Amount': -3},   # impuesto
        {'Date': '2025-11-15', 'Action': 'Dividend - Foreign Tax Withholding', 'Amount': 3},    # reversa de impuesto
    ])
    ev_ib = logic._dividend_events(hist_ib)
    assert ev_ib.sum() == pytest.approx(20.0), (
        "las reversas deben RESTAR y las filas de impuesto EXCLUIRSE — nunca abs()")
    # Misma economía declarada en bruto que la lectura del ledger:
    assert ev_ib.sum() == pytest.approx(logic._csv_dividends_in_window(hist_ib), abs=0.01)


# ── Invariante cruzado de la familia `_dividend_*` (Regla 3b del contrato ROC/NRA) ──────────
# Cruza las tres hermanas que recorren filas del CSV (`_dividend_events`,
# `_csv_dividends_in_window`, `_csv_dividends_by_year`) contra el objeto fiscal
# (`build_dividend_tax_totals`). Antes del fix, IB MSTY daba 12,877.59 vs 7,224.59 — con la
# suite en verde, porque ningún test cruzaba las fuentes con la convención IB.
#
# NO son fuentes independientes (auditoría M4, H3): `gross` ES
# `round(_csv_dividends_in_window(...), 2)`, y las tres hermanas excluyen las filas de
# impuesto con el MISMO predicado (`_is_tax_row_action`). El cruce caza que UNA se despegue;
# un fallo del predicado las mueve a las cuatro juntas y cuadra por construcción. Ese caso lo
# muerde el ANCLA externa —el literal $462.00 de Schwab y los de `ib_synth_1`, derivados a
# mano de las filas del CSV—, no el cruce. Medido con el predicado ciego a la retención de
# IB: la variante `ib_synth_1` cae y la de Schwab no (no tiene filas IB).

def _assert_familia_cuadra_con_bruto(df_sub, etiqueta):
    esperado = logic.build_dividend_tax_totals(df_sub)['gross']
    eventos = logic._dividend_events(df_sub).sum()
    ventana = logic._csv_dividends_in_window(df_sub)
    por_anio = sum(logic._csv_dividends_by_year(df_sub).values())
    assert eventos == pytest.approx(esperado, abs=0.01), (
        f"{etiqueta}: _dividend_events {eventos} ≠ bruto {esperado}")
    assert ventana == pytest.approx(esperado, abs=0.01), (
        f"{etiqueta}: _csv_dividends_in_window {ventana} ≠ bruto {esperado}")
    assert por_anio == pytest.approx(esperado, abs=0.01), (
        f"{etiqueta}: suma de _csv_dividends_by_year {por_anio} ≠ bruto {esperado}")


@pytest.mark.parametrize("ticker", ["MSTY", "NVDY", "CONY", "TSLY"])
def test_familia_dividend_declara_bruto_ib_por_ticker(ticker):
    """Invariante cruzado, convención IB real: las tres hermanas devuelven BRUTO y coinciden
    con `build_dividend_tax_totals['gross']` para cada whitelist ticker."""
    dfc = _load_real_ib_1()
    sub = dfc[dfc["Ticker"] == ticker]
    assert len(sub) > 0
    _assert_familia_cuadra_con_bruto(sub, f"IB {ticker}")


def test_familia_dividend_declara_bruto_schwab():
    """Mismo invariante cruzado, convención Schwab (fixtures/schwab_synth_2 MSTY,
    ground truth $462.00) — la ruta Schwab no debía moverse."""
    raw = open(os.path.join(os.path.dirname(__file__), "fixtures", "schwab_synth_2",
                             "synthetic_transactions.csv"), "rb").read()
    df, broker = logic.load_and_detect_csv(FakeFile(raw, "schwab_synth_2.csv"))
    dfc = logic.normalize_csv(df)
    sub = dfc[dfc["Ticker"] == "MSTY"]
    tt = logic.build_dividend_tax_totals(sub)
    assert tt["gross"] == pytest.approx(462.00, abs=0.01)
    _assert_familia_cuadra_con_bruto(sub, "Schwab MSTY")


_IB_SYNTH_1 = os.path.join(os.path.dirname(__file__), "fixtures", "ib_synth_1",
                           "synthetic_transactions.csv")


def _ib_synth_1_normalizado():
    with open(_IB_SYNTH_1, "rb") as f:
        df, broker = logic.load_and_detect_csv(FakeFile(f.read(), "ib_synth_1.csv"))
    assert broker == "ibkr"
    return logic.normalize_csv(df)


@pytest.mark.parametrize("ticker,bruto", [
    ("NVDY", 61.20),   # Dividend $60.00 + Payment in Lieu $1.20
    ("CONY", 60.00),
    ("SMH", 2.00),
])
def test_familia_dividend_declara_bruto_ib_sintetico(ticker, bruto):
    """El ancla que le falta a la variante IB real, sobre un fixture que corre sin
    `real_examples/`: el bruto por ticker, derivado A MANO de las filas del CSV.

    NVDY incluye el pago sustitutivo de $1.20: `parse_ibkr_csv` mapea 'Payment in Lieu' a
    'Dividend' y el bruto fiscal lo cuenta. `income_expected.received` del fixture lo EXCLUYE
    a propósito —es otra definición de «bruto», ver la nota en `fixtures/verify_fixtures.py`—,
    así que no sirve de ancla aquí. Si algún día se decide que el pago sustitutivo no es
    dividendo, este literal cambia con esa decisión."""
    dfc = _ib_synth_1_normalizado()
    sub = dfc[dfc["Ticker"] == ticker]
    tt = logic.build_dividend_tax_totals(sub)
    assert tt["gross"] == pytest.approx(bruto, abs=0.01), (
        f"IB sintético {ticker}: bruto {tt['gross']} ≠ {bruto} de las filas del CSV")
    assert tt["netted"] is True, "el fixture debe ejercer la convención IB (retención plegada)"
    _assert_familia_cuadra_con_bruto(sub, f"IB sintético {ticker}")


def test_withheld_tax_total_reads_nra_rows():
    hist = _div_hist([
        {'Date': '2025-11-15', 'Action': 'Cash Dividend', 'Amount': 12},
        {'Date': '2025-11-15', 'Action': 'NRA Tax Adj', 'Amount': -3.6},
    ])
    assert logic.withheld_tax_total(hist) == pytest.approx(3.6)
    # sin filas de impuesto → 0
    assert logic.withheld_tax_total(_div_hist(
        [{'Date': '2025-11-15', 'Action': 'Cash Dividend', 'Amount': 12}])) == 0.0


def test_withheld_tax_total_nets_refunds_not_abs():
    # Regresión: un reembolso (monto POSITIVO en fila de impuesto, p.ej. la devolución de la
    # porción ROC tras la reclasificación) debe NETEAR la retención, no sumarse como más
    # retención. Antes, con abs(): -100 y +30 → 130 (bug). Ahora → 70.
    hist = _div_hist([
        {'Date': '2025-05-15', 'Action': 'NRA Tax Adj', 'Amount': -100},
        {'Date': '2026-03-01', 'Action': 'NRA Tax Adj', 'Amount': 30},   # reembolso/reclasif.
    ])
    assert logic.withheld_tax_total(hist) == pytest.approx(70.0)
    # reembolso que excede la retención → retención neta acotada a 0 (nunca negativa)
    hist2 = _div_hist([
        {'Date': '2025-05-15', 'Action': 'NRA Tax Adj', 'Amount': -20},
        {'Date': '2026-03-01', 'Action': 'NRA Tax Adj', 'Amount': 50},
    ])
    assert logic.withheld_tax_total(hist2) == 0.0
    # by_year netea por año: 2025 retiene 100, 2026 recibe reembolso → 0 (no negativo)
    wby = logic.withheld_tax_total_by_year(hist)
    assert wby.get(2025) == pytest.approx(100.0)
    assert wby.get(2026) == 0.0


def test_observed_tax_refund_by_year_detects_positive_rows():
    # El reembolso real (fila de impuesto POSITIVA, p.ej. la devolución del ROC) se detecta por
    # año; la retención (negativa) y las filas que no son de impuesto no cuentan.
    hist = _div_hist([
        {'Date': '2025-05-15', 'Action': 'NRA Tax Adj', 'Amount': -100},  # retención
        {'Date': '2026-06-20', 'Action': 'NRA Tax Adj', 'Amount': 83},    # reembolso del ROC
        {'Date': '2026-07-01', 'Action': 'Cash Dividend', 'Amount': 40},  # no es impuesto
    ])
    obs = logic.observed_tax_refund_by_year(hist)
    assert obs.get(2026) == pytest.approx(83.0)
    assert 2025 not in obs               # ese año solo hubo retención, sin reembolso
    assert logic.observed_tax_refund_by_year(_div_hist(
        [{'Date': '2025-11-15', 'Action': 'Cash Dividend', 'Amount': 12}])) == {}


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


# ── Ronda 2: devolución estimada de retención NRA (escudo del ROC) ──

def test_estimate_roc_refund_no_roc_exact_base_rate_zero_refund():
    r = logic.estimate_roc_refund(gross=1000.0, withheld=300.0, roc_pct=0, base_rate=0.30)
    assert r['fair_withholding'] == pytest.approx(300.0, abs=0.01)
    assert r['refund'] == pytest.approx(0.0, abs=0.01)
    assert r['refund_pct'] == pytest.approx(0.0, abs=0.1)


def test_estimate_roc_refund_never_negative_or_above_withheld():
    # retención justa mayor que lo retenido (roc bajo, base alta) → devolución 0, no negativa
    r = logic.estimate_roc_refund(gross=100.0, withheld=5.0, roc_pct=0, base_rate=0.30)
    assert r['refund'] >= 0.0
    assert r['refund'] <= 5.0
    # roc muy alto, retención alta → devolución acotada a lo retenido
    r2 = logic.estimate_roc_refund(gross=100.0, withheld=1000.0, roc_pct=90, base_rate=0.30)
    assert 0.0 <= r2['refund'] <= 1000.0


def test_estimate_roc_refund_acceptance_case():
    # Caso de aceptación del traspaso: gross=361.05, withheld=105.08, roc=67%, base 30%
    r = logic.estimate_roc_refund(gross=361.05, withheld=105.08, roc_pct=67, base_rate=0.30)
    assert r['fair_withholding'] == pytest.approx(35.7, abs=0.5)
    assert r['refund'] == pytest.approx(69.3, abs=0.5)


def test_estimate_roc_refund_full_roc_refunds_everything():
    r = logic.estimate_roc_refund(gross=500.0, withheld=150.0, roc_pct=100, base_rate=0.30)
    assert r['fair_withholding'] == pytest.approx(0.0, abs=0.01)
    assert r['refund'] == pytest.approx(150.0, abs=0.01)
    assert r['refund_pct'] == pytest.approx(100.0, abs=0.1)


def test_estimate_roc_refund_zero_withheld_returns_zeroes():
    r = logic.estimate_roc_refund(gross=500.0, withheld=0.0, roc_pct=50, base_rate=0.30)
    assert r == {'fair_withholding': 0.0, 'refund': 0.0, 'refund_pct': 0.0}


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


def test_roc_health_destructive_plain_clarifies_engine_not_investor_result():
    # El veredicto destructivo mide el motor de los cheques (de donde sale el pago), no el
    # resultado real del inversionista -> debe remitir a la pestaña "Resultado real".
    v1 = logic.classify_roc_health(roc_pct=95, price_cagr=-40, total_return_pct=-25, history_days=400)
    v2 = logic.classify_roc_health(roc_pct=10, price_cagr=-30, total_return_pct=-15, history_days=400)
    for v in (v1, v2):
        assert v["verdict"] == "destructive"
        assert "Resultado real" in v["plain"]
        assert "motor de los cheques" in v["plain"]


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


# ── Histéresis del umbral de ROC alto (anti-parpadeo de alertas) ────────────────

def test_roc_health_hysteresis_regression_prev_none_threshold_50():
    # Sin veredicto previo, el umbral sigue siendo 50 (comportamiento clásico).
    assert logic.classify_roc_health(49.9, -40, None, history_days=400)["verdict"] == "mixed"
    assert logic.classify_roc_health(50.0, -40, None, history_days=400)["verdict"] == "destructive"
    assert logic.classify_roc_health(50.1, -40, None, history_days=400)["verdict"] == "destructive"


def test_roc_health_hysteresis_exit_requires_roc_below_45():
    # Viniendo de destructivo, un ROC de 47 (bajo 50 pero sobre 45) NO saca al fondo.
    v = logic.classify_roc_health(47, -40, None, history_days=400, prev_verdict="destructive")
    assert v["verdict"] == "destructive"
    # Con ROC 44 (bajo el umbral de salida) ya puede salir.
    v = logic.classify_roc_health(44, -40, None, history_days=400, prev_verdict="destructive")
    assert v["verdict"] != "destructive"


def test_roc_health_hysteresis_enter_requires_roc_above_55():
    # Viniendo de mixed, un ROC de 52 (sobre 50 pero bajo 55) NO entra a destructivo.
    v = logic.classify_roc_health(52, -40, None, history_days=400, prev_verdict="mixed")
    assert v["verdict"] != "destructive"
    # Con ROC 56 sí entra.
    v = logic.classify_roc_health(56, -40, None, history_days=400, prev_verdict="mixed")
    assert v["verdict"] == "destructive"


def test_roc_health_hysteresis_prev_insufficient_behaves_like_none():
    v_ins = logic.classify_roc_health(52, -40, None, history_days=400, prev_verdict="insufficient")
    v_none = logic.classify_roc_health(52, -40, None, history_days=400, prev_verdict=None)
    assert v_ins["verdict"] == v_none["verdict"] == "destructive"
    v_ins = logic.classify_roc_health(47, -40, None, history_days=400, prev_verdict="insufficient")
    v_none = logic.classify_roc_health(47, -40, None, history_days=400, prev_verdict=None)
    assert v_ins["verdict"] == v_none["verdict"] == "mixed"


# ── Filtro de justicia de mercado: NAV vs subyacente (underlying_cagr) ──────────

def test_roc_health_market_justified_when_fund_falls_with_underlying():
    # MSTR -60% / MSTY -62% / ROC 80% -> gap -2 pts, dentro de tolerancia -> NO destructivo
    v = logic.classify_roc_health(80, -62, None, history_days=400, underlying_cagr=-60)
    assert v["verdict"] == "mixed"
    assert "mercado" in v["headline"].lower()


def test_roc_health_overcapture_still_destructive():
    # MSTR -60% / MSTY -85% / ROC 80% -> gap -25 pts, fuera de tolerancia -> destructivo
    v = logic.classify_roc_health(80, -85, None, history_days=400, underlying_cagr=-60)
    assert v["verdict"] == "destructive"


def test_roc_health_confirmed_destructive_when_underlying_recovers():
    # MSTR +5% / MSTY -20% / ROC 80% -> subyacente sube, fondo cae -> destructivo confirmado
    v = logic.classify_roc_health(80, -20, None, history_days=400, underlying_cagr=5)
    assert v["verdict"] == "destructive"


def test_roc_health_underlying_cagr_none_is_regression_safe():
    # underlying_cagr=None -> comportamiento absoluto clasico, identico al actual
    with_none = logic.classify_roc_health(95, -40, -25, history_days=400, underlying_cagr=None)
    without_param = logic.classify_roc_health(95, -40, -25, history_days=400)
    assert with_none["verdict"] == without_param["verdict"] == "destructive"


def test_latest_health_verdict_reads_last_entry(monkeypatch):
    monkeypatch.setattr(logic, "load_roc_health_history", lambda: {
        "MSTY": [{"date": "2026-06-01", "verdict": "mixed", "roc_pct": 40, "price_cagr": -20},
                 {"date": "2026-06-28", "verdict": "destructive", "roc_pct": 60, "price_cagr": -35}],
    })
    assert logic.latest_health_verdict("msty") == "destructive"
    assert logic.latest_health_verdict("NOEXISTE") is None


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


# ── ui.adapters.trg_real_data — JSON del Total Return Graph · datos reales
# (traspaso 2026-08-10) ─────────────────────────────────────────────────────────

def _trg_real_fake_frames():
    """Universo completo (5 YM + 3 crecimiento), diario, TSLY como ancla más antigua
    (arranca 2026-01-01). CHPY arranca el 5 de marzo — tardío, > 7 días tras el ancla,
    y a medio mes a propósito (no en el día 1) para ejercer el fix de remuestreo del
    primer mes parcial (ver `trg_real_data`) también en un ticker tardío, no solo en
    el ancla. La ventana cruza tres meses (ene/feb/mar) para probar el remuestreo
    mensual."""
    idx_full = pd.date_range("2026-01-01", "2026-03-20", freq="D")
    idx_tardio = pd.date_range("2026-03-05", "2026-03-20", freq="D")

    def _frame(idx, close0, drift, dia_div=None):
        close = pd.Series([close0 + drift * i for i in range(len(idx))], index=idx)
        divs = pd.Series(0.0, index=idx)
        if dia_div is not None and dia_div in divs.index:
            divs.loc[dia_div] = 1.0
        return pd.DataFrame({"Close": close, "Dividends": divs})

    return {
        "TSLY": _frame(idx_full, 10.0, 0.02, dia_div=idx_full[10]),
        "NVDY": _frame(idx_full, 20.0, 0.01, dia_div=idx_full[15]),
        "CONY": _frame(idx_full, 15.0, 0.01),
        "MSTY": _frame(idx_full, 12.0, 0.015, dia_div=idx_full[20]),
        "CHPY": _frame(idx_tardio, 5.0, 0.03),
        "SCHB": _frame(idx_full, 100.0, 0.05),
        "XLK": _frame(idx_full, 200.0, 0.08),
        "SMH": _frame(idx_full, 150.0, 0.10),
    }


def _trg_real_patch(monkeypatch, frames):
    """Doble de `price_cache.load_history`. Antes doblaba `logic.fetch_market_data`, que
    era la ruta que `build_drip_comparison_series` usaba para bajar de yfinance en
    runtime; desde la migración del 2026-08-21 la vista lee del caché de precio y corre
    `backtest.run_backtest`, así que el doble tiene que estar un nivel más abajo.

    Un ticker sin frame devuelve un `HistoryResult` vacío, que es como el caché reporta
    «este símbolo no está» — no una excepción."""
    def _fake_load_history(tk, *args, **kwargs):
        df = frames.get(tk)
        return price_cache.HistoryResult(
            history=df if df is not None else pd.DataFrame(),
            source="cache", ticker=tk, cache_asof="2026-03-20")
    monkeypatch.setattr(price_cache, "load_history", _fake_load_history)


def test_trg_real_data_shape_has_3_modos_y_8_tickers(monkeypatch):
    _trg_real_patch(monkeypatch, _trg_real_fake_frames())
    datos = trg_real_data({"MSTY": {"market_value": 500}}, tasa_pct=30.0, pais="México")
    assert datos is not None
    assert set(datos["idx"].keys()) == {"bruto", "roc", "plano"}
    for modo in ("bruto", "roc", "plano"):
        assert set(datos["idx"][modo].keys()) == {
            "NVDY", "TSLY", "CONY", "MSTY", "CHPY", "SCHB", "XLK", "SMH"}
    assert datos["origen"] == [2026, 0]  # enero 2026, 0-indexado


def test_trg_real_data_incepcion_tardia_no_arranca_en_0(monkeypatch):
    _trg_real_patch(monkeypatch, _trg_real_fake_frames())
    datos = trg_real_data({"MSTY": {"market_value": 500}}, tasa_pct=30.0)
    assert "0" not in datos["idx"]["bruto"]["CHPY"]
    primer_mes_chpy = min(int(k) for k in datos["idx"]["bruto"]["CHPY"].keys())
    assert datos["incep"]["CHPY"] == primer_mes_chpy
    # CHPY arranca en marzo (mes 2, 0-indexado desde enero) — tardío frente al ancla.
    assert datos["incep"]["CHPY"] == 2
    assert datos["incep"]["TSLY"] == 0


def test_trg_real_data_incep_coincide_con_el_arranque_real_de_cada_serie(monkeypatch):
    """`incep` tiene que ser el mes en que la serie de verdad empieza: su propia incepción,
    o la del ancla si el ticker ya existía antes (la ventana no puede abrirse antes de que
    la lección empiece).

    El lado esperado se deriva de las FRAMES, no de la fórmula del adaptador — si se
    calculara con la misma expresión que produce el dato, el test no podría fallar. Antes
    el lado independiente era el `meta` de `build_drip_comparison_series`, el motor que
    esta vista dejó de usar el 2026-08-21."""
    frames = _trg_real_fake_frames()
    _trg_real_patch(monkeypatch, frames)
    datos = trg_real_data({"MSTY": {"market_value": 500}}, tasa_pct=30.0)
    ancla_start = min(f.index.min() for f in frames.values())
    for tk, frame in frames.items():
        start = max(frame.index.min(), ancla_start)
        esperado = (start.year - 2026) * 12 + (start.month - 1)
        assert datos["incep"][tk] == esperado, tk


def test_trg_real_data_remuestreo_mensual_ultimo_valor_y_ultimo_dato_real(monkeypatch):
    frames = _trg_real_fake_frames()
    _trg_real_patch(monkeypatch, frames)
    datos = trg_real_data({"MSTY": {"market_value": 500}}, tasa_pct=30.0)
    tsly_bruto = datos["idx"]["bruto"]["TSLY"]

    # Lado independiente: la corrida diaria del motor, sin mensualizar. El remuestreo es
    # justo lo que este test verifica, así que no puede salir de la misma función.
    serie = backtest.run_backtest(
        "TSLY", start_date=frames["TSLY"].index.min(), initial_capital=100.0, drip=True,
        nra_rate=0.0, history=frames["TSLY"]).daily["total_value"].sort_index()

    # Un mes intermedio COMPLETO (febrero, mes 1) sí usa el último cierre del mes.
    ultimo_feb = serie[serie.index.month == 2].iloc[-1]
    assert tsly_bruto["1"] == pytest.approx(round(float(ultimo_feb), 4))
    # El último punto (mes 2, marzo — parcial, hasta el 20) es el último dato real de
    # la serie completa, no el cierre "de mes" inexistente (marzo no terminó).
    assert tsly_bruto[str(datos["last"])] == pytest.approx(round(float(serie.iloc[-1]), 4))
    assert datos["last"] == 2


def test_trg_real_data_primer_mes_usa_valor_real_de_arranque_no_cierre_de_mes(monkeypatch):
    """El primer mes de CADA ticker (su propia incepción) casi nunca cae el día 1, así
    que `.resample().last()` ahí tomaría el cierre de FIN de ese mes, no el valor real
    de arranque — cada serie se normaliza a exactamente 100 en su primer dato. Si ese ancla se corre, la renormalización de JS a "0% en la
    incepción" queda sesgada por lo que el precio ya se movió mientras tanto (medido
    en vivo con datos reales: MSTY, incep 22-feb, daba +5% en vez de +24% con este
    bug). Se prueba con el ancla (TSLY, incep día 1 — caso trivial) Y con un ticker
    tardío que arranca a medio mes (CHPY, 5 de marzo — el caso que de verdad ejerce
    el fix)."""
    _trg_real_patch(monkeypatch, _trg_real_fake_frames())
    datos = trg_real_data({"MSTY": {"market_value": 500}}, tasa_pct=30.0)
    assert datos["idx"]["bruto"]["TSLY"]["0"] == pytest.approx(100.0)
    primer_mes_chpy = str(min(int(k) for k in datos["idx"]["bruto"]["CHPY"].keys()))
    assert datos["idx"]["bruto"]["CHPY"][primer_mes_chpy] == pytest.approx(100.0)


def test_trg_real_data_plano_nunca_supera_a_roc(monkeypatch):
    """**Estructural.** El escudo ROC solo puede sumar: en «plano» se retiene la tasa y no
    vuelve nada; en «roc» se retiene lo mismo y una parte se devenga como cuenta por
    cobrar. `plano <= roc` no depende de ningún precio.

    Ojo con la mitad que NO está aquí: `roc <= bruto` era parte de esta aserción y se
    separó al test de abajo, porque con reinversión ESO SÍ depende del mercado (Regla 5
    del contrato fiscal)."""
    _trg_real_patch(monkeypatch, _trg_real_fake_frames())
    datos = trg_real_data({"MSTY": {"market_value": 500}}, tasa_pct=30.0)
    last = str(datos["last"])
    for tk in ("TSLY", "NVDY", "MSTY"):
        assert datos["idx"]["plano"][tk][last] <= datos["idx"]["roc"][tk][last] + 1e-9, tk


def test_trg_real_data_roc_bajo_precios_al_alza_queda_bajo_bruto(monkeypatch):
    """**Hecho de la fixture, no invariante.** Aquí `roc <= bruto` se cumple porque los
    precios sintéticos SUBEN de principio a fin: lo que «bruto» reinvirtió de más siguió
    apreciándose, mientras el reembolso del ROC quedó congelado como cuenta por cobrar.

    Con precios a la baja se invierte, y no es un bug: es la misma lección que el repo ya
    protege en `test_comparacion_data.py` y `test_contrafactico_sin_drip.py`. Si este test
    falla, revisa PRIMERO si alguien tocó la fixture para que baje — no «arregles» el
    motor."""
    frames = _trg_real_fake_frames()
    _trg_real_patch(monkeypatch, frames)
    for tk in ("TSLY", "NVDY", "MSTY"):
        cierres = frames[tk]["Close"]
        assert cierres.iloc[-1] > cierres.iloc[0], (
            f"la fixture de {tk} dejó de subir: esta prueba ya no mide lo que dice medir")
    datos = trg_real_data({"MSTY": {"market_value": 500}}, tasa_pct=30.0)
    last = str(datos["last"])
    for tk in ("TSLY", "NVDY", "MSTY"):
        assert datos["idx"]["roc"][tk][last] <= datos["idx"]["bruto"][tk][last] + 1e-9, tk


def test_trg_real_data_ancla_caida_devuelve_none(monkeypatch):
    _trg_real_patch(monkeypatch, {})
    assert trg_real_data({"MSTY": {"market_value": 500}}, tasa_pct=30.0) is None


def test_trg_real_data_ticker_caido_se_omite_de_todas_las_claves(monkeypatch):
    """Un comparador que no descarga desaparece del JSON entero — no entra con ceros
    ni interpolado.

    Es el contrato que consume el componente: sus chips se dibujan filtrando
    `["NVDY",…].filter(_presente)` contra `DATA.incep`
    (`tools/extract_comparacion_real.py`). Si `incep`/`idx`/`col` dejaran de estar de
    acuerdo, volvería el fallo que encontró la auditoría del 2026-08-10: el chip se
    dibuja igual y al pulsarlo `F[tk]` es undefined → `TypeError` en `F[tk].incep`.
    """
    frames = _trg_real_fake_frames()
    del frames["CHPY"]          # yfinance sin datos para ese símbolo
    _trg_real_patch(monkeypatch, frames)

    datos = trg_real_data({"MSTY": {"market_value": 500}}, tasa_pct=30.0)
    assert datos is not None            # cae un comparador, no el ancla
    assert "CHPY" not in datos["incep"]
    assert "CHPY" not in datos["grp"]
    assert "CHPY" not in datos["col"]
    for modo in ("bruto", "roc", "plano"):
        assert "CHPY" not in datos["idx"][modo]
    # Las cuatro claves siguen describiendo exactamente el mismo conjunto de tickers.
    assert set(datos["incep"]) == set(datos["grp"]) == set(datos["col"])
    assert set(datos["incep"]) == set(datos["idx"]["bruto"])


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
    """`dividends_gross_total` viene DECLARADO en stats (como lo deja
    `build_dividend_tax_totals` dentro de `analyze_portfolio`), igual a `total_dividends`:
    escenario Schwab sin DRIP, donde el CSV ya entrega el bruto directo y NO hay que sumarle
    la retención de nuevo (antes del fix, `build_hoja_excel` sí lo hacía y duplicaba el
    impuesto — ver `test_ib_withheld_tax_no_rompe_schwab` y el caso real MSTY $600.60 vs
    $462)."""
    results = {
        "MSTY": {
            "pocket_investment": 4197.2, "total_dividends": 2574.54,
            "withheld_tax_total": 120.0, "dividends_gross_total": 2574.54,
            "market_value": 1131.78,
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
    # bruto = declarado (leído del CSV), NO neto + NRA — sumarlo de nuevo duplicaría la
    # retención cuando el broker (Schwab) ya reporta `total_dividends` en base bruta.
    assert round(r["dividends_gross"], 2) == 2574.54


def test_build_hoja_excel_roc_dollars_trap():
    # Ticker ficticio sin avisos 19a → roc_pct cae al estimado del broker (roc_percent).
    # `dividends_gross_total` declarado igual a `total_dividends` (mismo escenario Schwab
    # sin DRIP de test_build_hoja_excel_naive_vs_honest).
    results = {
        "ZZZZ": {
            "pocket_investment": 4197.2, "total_dividends": 2574.54,
            "withheld_tax_total": 120.0, "dividends_gross_total": 2574.54,
            "market_value": 1131.78,
            "dividends_collected_cash": 2574.54, "last_payment": 28.85,
            "price_cagr": -81.5, "roc_percent": 90.0, "price_history_days": 500,
            "advertised_yield": 66.67, "forward_yield": 132.6, "realized_yield": 227.5,
            "yield_on_cost": 61.0,
        },
    }
    out = logic.build_hoja_excel(results, classify_map={"ZZZZ": "mode_a"})
    r = out["rows"][0]
    gross = 2574.54          # declarado, no net_div + withheld_tax_total (ver test naive_vs_honest)
    assert r["roc_pct"] == 90.0
    # ROC en dólares = % ROC × distribución bruta (no es una resta de costos).
    assert round(r["roc_dollars"], 2) == round(0.90 * gross, 2)
    # «Capital real aportado» = total_inv_naive − ROC$, siempre menor que el inflado.
    cap_real = r["total_inv_naive"] - r["roc_dollars"]
    assert cap_real < r["total_inv_naive"]
    # el total agrega roc_dollars
    assert round(out["totals"]["roc_dollars"], 2) == round(r["roc_dollars"], 2)


# ── Regresión fixes 2026-07-01 (revision-logica) ────────────────────────────────

def test_monthly_income_drip_schwab_no_netea(monkeypatch):
    """Fix 2: monthly_income (mode_a) usa _dividend_events, no el filtro que neteaba el DRIP.
    Repro del informe: Reinvest Dividend +10, Reinvest Shares -7, Qualified Dividend +5
    → el mes debe mostrar 15 (bruto cobrado), no 8 (neteado con la compra del DRIP)."""
    df = _roc_norm_df([
        ("2024-09-01", "Buy",              "MSTY", 100, -2000.0),
        ("2024-10-01", "Reinvest Dividend", "MSTY", 0,    10.0),
        ("2024-10-01", "Reinvest Shares",   "MSTY", 7,    -7.0),
        ("2024-10-15", "Qualified Dividend", "MSTY", 0,    5.0),
    ])
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    s = logic.analyze_portfolio(df, version="TEST_MONTHLY_DRIP")["MSTY"]
    mi = s["monthly_income"]
    assert float(mi.loc["2024-10"]) == pytest.approx(15.0, abs=0.01)


def test_irr_incluye_deposito_con_costo(monkeypatch):
    """Fix 3: la rama deposit registra el flujo en el IRR. Una posición fondeada por una
    contribución externa con costo produce un IRR finito; antes quedaba en None porque el
    único flujo negativo (el capital que entró) no se registraba."""
    df = _roc_norm_df([
        ("2024-09-01", "Contribution", "MSTY", 100, -2000.0),
    ])
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    s = logic.analyze_portfolio(df, version="TEST_IRR_DEPOSIT")["MSTY"]
    assert s["pocket_investment"] == pytest.approx(2000.0, abs=0.01)
    assert s["irr_anual"] is not None
    # market_value ≈ pocket → IRR cercano a 0, pero finito (sin el fix: None).
    assert abs(s["irr_anual"]) < 20


def test_triple_comparison_reinvierte_dividendos(monkeypatch):
    """Fix 1: simulate_triple_comparison reinvierte los dividendos (total return).
    Con 1 dividendo de 10 sobre 10 acciones a $100, el valor final sube de 1000 a 1100
    (antes ignoraba las distribuciones y daba 1000 / 0%)."""
    import json

    def _mkt(ticker, start):
        idx = pd.to_datetime(["2024-09-02", "2024-09-03"])
        df = pd.DataFrame({"Close": [100.0, 100.0], "Dividends": [0.0, 10.0]}, index=idx)
        return df, None

    monkeypatch.setattr(logic, "fetch_market_data", _mkt)
    flows = json.dumps([["2024-09-01", 1000.0]])
    res = logic.simulate_triple_comparison(flows)
    assert res, "simulate_triple_comparison devolvió vacío"
    for key in ("all_vti", "all_ymax", "all_spy"):
        assert res[key]["final_value"] == pytest.approx(1100.0, abs=0.5)
        assert res[key]["return_pct"] == pytest.approx(10.0, abs=0.1)


# ── Regresión fixes 6-9 (revision-logica, 2026-07-02) ───────────────────────────
# Nota: los fixes 4 (coma de miles) y 5 (MC div growth) se descartaron por conflicto con
# comportamiento correcto existente (IB '579,314'=579.314 y el guardarraíl anti-explosión
# del Monte Carlo). Ver log 2026-07-02.

def test_coverage_baja_sola_no_marca_partial():
    """Fix 6: un fondo viejo con la posición documentada al 100% marca coverage bajo (vida del
    FONDO, no de la posición) → no debe degradarse a 'partial' sin una señal real de historial
    truncado. Antes: badge 'partial' falso."""
    results = {"SMH": {"csv_coverage_pct": 7.0}}   # sin history_incomplete ni cost issues
    q = logic.assess_ticker_quality(results, "SMH")
    assert q["level"] == "ok"
    assert "low_coverage" in q["flags"]            # el flag informativo se conserva


def test_held_too_briefly_ignora_transfers():
    """Fix 9: una transferencia (qty con abs) no debe contar como compra. Una posición
    realmente cerrada en pocos días se detecta aunque haya una fila de transferencia."""
    tdf = pd.DataFrame({
        "Date": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-03"),
                 pd.Timestamp("2024-01-05")],
        "Action": ["Buy", "Transfer", "Sell"],
        "Quantity": [100, -30, -100],
    })
    too_brief, days = logic.is_held_too_briefly(tdf, threshold_days=14)
    assert too_brief is True
    assert days == 4


# ── Ronda 3 (2026-07-13): desglose por año de la devolución ROC + ROC forward reciente ──

def test_dividends_gross_and_withheld_by_year_match_totals(monkeypatch):
    """dividends_gross_by_year / withheld_by_year — retención en 2 años calendario distintos
    (real_examples/ hoy no trae un caso Schwab con NRA Tax Adj multi-año).

    Convención Schwab: 'NRA Tax Adj' NO comparte 'dividend' con la fila del pago -> el CSV
    YA entrega el bruto directo ('Dividend' 300/400). ANTES del fix, `dividends_gross_by_year`
    asumía ciegamente `gross = net + withheld` (correcto solo para IB, donde la retención
    viene plegada en la propia fila de dividendo) y duplicaba la retención aquí: 390/460 en
    vez de 300/400. Ese comportamiento viejo era el bug, no el contrato — por eso este test
    cambia de expectativa (no es un test tocado para pasar el deploy: sigue pudiendo fallar
    si `build_dividend_tax_totals` deja de detectar la convención por fila).
    """
    df = _roc_norm_df([
        ("2024-01-01", "Buy", "MSTY", 100, -2000.0),
        ("2024-06-01", "Dividend", "MSTY", 0, 300.0),
        ("2024-06-01", "NRA Tax Adj", "MSTY", 0, -90.0),
        ("2025-06-01", "Dividend", "MSTY", 0, 400.0),
        ("2025-06-01", "NRA Tax Adj", "MSTY", 0, -60.0),
    ])
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    s = logic.analyze_portfolio(df, version="TEST_YEAR_SPLIT")["MSTY"]
    assert s["total_dividends"] == pytest.approx(700.0, abs=0.01)
    assert s["withheld_tax_total"] == pytest.approx(150.0, abs=0.01)
    gby, wby = s["dividends_gross_by_year"], s["withheld_by_year"]
    nby = s["dividends_net_by_year"]
    assert sum(wby.values()) == pytest.approx(s["withheld_tax_total"], abs=0.05)
    # El CSV ya entrega el bruto (convención Schwab, detectada por fila): la suma por año
    # cuadra con `total_dividends` tal cual, SIN sumarle la retención de nuevo.
    assert sum(gby.values()) == pytest.approx(s["total_dividends"], abs=0.05)
    assert wby[2024] == pytest.approx(90.0, abs=0.01)
    assert wby[2025] == pytest.approx(60.0, abs=0.01)
    assert gby[2024] == pytest.approx(300.0, abs=0.01)
    assert gby[2025] == pytest.approx(400.0, abs=0.01)
    assert nby[2024] == pytest.approx(210.0, abs=0.01)
    assert nby[2025] == pytest.approx(340.0, abs=0.01)
    # Objeto fiscal único (totales del ticker completo): bruto = leído del CSV, neto = derivado.
    assert s["dividend_base_convention"] == "retencion_aparte"
    assert s["dividends_gross_total"] == pytest.approx(700.0, abs=0.01)
    assert s["dividends_net_total"] == pytest.approx(550.0, abs=0.01)


def test_estimate_roc_refund_by_year_sums_match_total_when_roc_uniform(monkeypatch):
    """(a) Con el mismo %ROC en ambos años (aquí, sin avisos 19a -> fallback uniforme), la
    suma de los refunds por año debe coincidir con llamar estimate_roc_refund directo sobre
    los totales agregados."""
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {})
    gross_by_year = {2024: 1000.0, 2025: 2000.0}
    withheld_by_year = {2024: 300.0, 2025: 600.0}
    result = logic.estimate_roc_refund_by_year(
        gross_by_year, withheld_by_year, "ZZZY", base_rate=0.30, roc_fallback_pct=50.0)
    sum_refund = result[2024]["refund"] + result[2025]["refund"]
    assert result["total"]["refund"] == pytest.approx(sum_refund, abs=0.02)
    direct = logic.estimate_roc_refund(3000.0, 900.0, 50.0, base_rate=0.30)
    assert result["total"]["refund"] == pytest.approx(direct["refund"], abs=0.05)
    assert result["total"]["fair_withholding"] == pytest.approx(direct["fair_withholding"], abs=0.05)


def test_estimate_roc_refund_by_year_uses_fallback_for_year_without_19a(monkeypatch):
    """(b) Un año sin avisos 19a en la ventana cae al roc_fallback_pct (roc_percent del
    holder); el año con aviso usa el promedio de ESE año."""
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {
        "MSTY": {"per_distribution": [{"date": "2025-03-01", "roc_pct": 80.0}]}})
    # 19a sintético: sin esto el cierre fiscal REAL de MSTY (roc_ici.yaml) pisa sus años.
    monkeypatch.setattr(logic, "load_roc_ici", lambda: {})
    gross_by_year = {2024: 500.0, 2025: 500.0}
    withheld_by_year = {2024: 150.0, 2025: 150.0}
    result = logic.estimate_roc_refund_by_year(
        gross_by_year, withheld_by_year, "MSTY", base_rate=0.30, roc_fallback_pct=10.0)
    assert result[2024]["roc_pct_usado"] == pytest.approx(10.0)
    assert result[2025]["roc_pct_usado"] == pytest.approx(80.0)


def test_estimate_roc_refund_by_year_different_roc_different_refund(monkeypatch):
    """(c) Años con %ROC distinto (2 avisos 19a sintéticos) producen devoluciones distintas
    sobre el mismo gross/withheld."""
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {
        "MSTY": {"per_distribution": [
            {"date": "2024-06-01", "roc_pct": 10.0},
            {"date": "2025-06-01", "roc_pct": 90.0},
        ]}})
    # 19a sintético: sin esto el cierre fiscal REAL de MSTY (roc_ici.yaml) pisa sus años.
    monkeypatch.setattr(logic, "load_roc_ici", lambda: {})
    gross_by_year = {2024: 1000.0, 2025: 1000.0}
    withheld_by_year = {2024: 300.0, 2025: 300.0}
    result = logic.estimate_roc_refund_by_year(gross_by_year, withheld_by_year, "MSTY", base_rate=0.30)
    assert result[2024]["refund"] < result[2025]["refund"]


# ── R1 + F6 (auditoría 2026-09-17/18): cierre fiscal por año y una sola resta de lo devuelto ──

def test_refund_por_anio_el_cierre_ici_manda_sobre_el_19a(monkeypatch):
    """R1: en un año con cierre fiscal (ICI) manda el cierre, no el promedio 19(a); en el año
    abierto, el 19(a). Un 0% del ICI es un cero MEDIDO y también pisa. Cada año declara su
    fuente. Forma del caso real: MSTY 2025 con 19(a) 78.4% y cierre 100% (1042-S de Daniel)."""
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {"MSTY": {"per_distribution": [
        {"date": "2024-11-01", "roc_pct": 95.9},
        {"date": "2025-03-01", "roc_pct": 70.0}, {"date": "2025-09-01", "roc_pct": 86.8},
        {"date": "2026-03-01", "roc_pct": 60.0}]}})
    monkeypatch.setattr(logic, "load_roc_ici", lambda: {"MSTY": {
        2024: {"roc_pct": 0.0}, 2025: {"roc_pct": 100.0}}})
    r = logic.estimate_roc_refund_by_year(
        {2024: 100.0, 2025: 1000.0, 2026: 1000.0}, {2024: 30.0, 2025: 300.0, 2026: 300.0},
        "MSTY", base_rate=0.30, roc_fallback_pct=50.0)
    assert (r[2025]["roc_pct_usado"], r[2025]["roc_fuente"]) == (100.0, "cierre")
    assert r[2025]["refund"] == pytest.approx(300.0, abs=0.01)          # todo vuelve
    assert (r[2024]["roc_pct_usado"], r[2024]["roc_fuente"]) == (0.0, "cierre")
    assert r[2024]["refund"] == pytest.approx(0.0, abs=0.01)            # nada vuelve
    assert (r[2026]["roc_pct_usado"], r[2026]["roc_fuente"]) == (60.0, "estimacion")
    assert r[2026]["refund"] == pytest.approx(300.0 - 0.30 * 1000.0 * 0.40, abs=0.01)
    assert r["total"]["refund"] == pytest.approx(300.0 + 0.0 + 180.0, abs=0.01)


def test_refund_por_anio_sin_cierre_ni_19a_cae_al_respaldo_declarado(monkeypatch):
    """Un año sin cierre ni avisos usa el %ROC del holder y lo DECLARA como respaldo; sin
    respaldo, 0% declarado como sin dato — nunca una fuente inventada."""
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {})
    monkeypatch.setattr(logic, "load_roc_ici", lambda: {})
    r = logic.estimate_roc_refund_by_year({2025: 100.0}, {2025: 30.0}, "ZZZY",
                                          roc_fallback_pct=40.0)
    assert (r[2025]["roc_pct_usado"], r[2025]["roc_fuente"]) == (40.0, "respaldo")
    r0 = logic.estimate_roc_refund_by_year({2025: 100.0}, {2025: 30.0}, "ZZZY")
    assert (r0[2025]["roc_pct_usado"], r0[2025]["roc_fuente"]) == (0.0, "sin_dato")


def _f6_summary(monkeypatch, filas, roc19a, roc_ici):
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    monkeypatch.setattr(logic, "load_roc_19a", lambda: roc19a)
    monkeypatch.setattr(logic, "load_roc_ici", lambda: roc_ici)
    results = logic.analyze_portfolio(_roc_norm_df(filas), version="TEST_F6")
    return logic.build_tax_summaries(
        results, base_rate_pct=logic.NRA_DEFAULT_RATE, country="Colombia")["MSTY"]


def test_tax_summary_no_resta_dos_veces_lo_ya_devuelto(monkeypatch):
    """F6, caso del informe: bruto $100, retenido al cobro $30, ya devuelto $10, ROC 80%,
    tasa 30%. Justa $6 ⇒ devolución TOTAL $24, ADICIONAL $14 (la que falta), saldo $20 y lo
    que se queda el fisco $6. Antes: `refund_pending` = $4 (restaba los $10 dos veces)."""
    ts = _f6_summary(monkeypatch, [
        ("2025-01-02", "Buy", "MSTY", 100, -2000.0),
        ("2025-06-01", "Dividend", "MSTY", 0, 100.0),
        ("2025-06-01", "NRA Tax Adj", "MSTY", 0, -30.0),
        ("2025-09-01", "NRA Tax Adj", "MSTY", 0, 10.0),
    ], {"MSTY": {"weighted_pct": 80.0,
                 "per_distribution": [{"date": "2025-06-01", "roc_pct": 80.0}]}}, {})
    assert ts["withheld_at_payment"] == pytest.approx(30.0, abs=0.01)   # inicial
    assert ts["refund_observed"] == pytest.approx(10.0, abs=0.01)       # ya devuelto
    assert ts["withheld_real"] == pytest.approx(20.0, abs=0.01)         # saldo
    assert ts["refund_total_estimated"] == pytest.approx(24.0, abs=0.01)
    assert ts["refund_estimated"] == pytest.approx(14.0, abs=0.01)      # adicional
    assert ts["refund_pending"] == pytest.approx(14.0, abs=0.01)
    assert ts["net_estimated"] == pytest.approx(6.0, abs=0.01)          # = justa
    assert ts["net_estimated"] == pytest.approx(ts["fair_withholding"], abs=0.01)


def test_tax_summary_el_reembolso_de_un_anio_llega_al_siguiente(monkeypatch):
    """F6 + R1 con la forma real (IB MSTY): la retención de 2025 se devuelve entera en
    febrero de 2026 (cierre 100%). Medida contra el SALDO, esa devolución le quitaba a 2026
    una retención que sí se cobró: 2026 salía sin nada que devolver y el fisco se quedaba en
    $0. Medida al cobro: total $30 + $15, ya devuelto $30, falta $15, y el fisco se queda la
    justa de 2026 ($15)."""
    ts = _f6_summary(monkeypatch, [
        ("2025-01-02", "Buy", "MSTY", 100, -2000.0),
        ("2025-06-01", "Dividend", "MSTY", 0, 100.0),
        ("2025-06-01", "NRA Tax Adj", "MSTY", 0, -30.0),
        ("2026-02-15", "NRA Tax Adj", "MSTY", 0, 30.0),
        ("2026-06-01", "Dividend", "MSTY", 0, 100.0),
        ("2026-06-01", "NRA Tax Adj", "MSTY", 0, -30.0),
    ], {"MSTY": {"weighted_pct": 50.0,
                 "per_distribution": [{"date": "2026-06-01", "roc_pct": 50.0}]}},
       {"MSTY": {2025: {"roc_pct": 100.0}}})
    assert ts["withheld_at_payment_by_year"] == {2025: 30.0, 2026: 30.0}
    assert ts["refund_by_year"][2025]["roc_fuente"] == "cierre"
    assert ts["refund_by_year"][2025]["refund"] == pytest.approx(30.0, abs=0.01)
    assert ts["refund_by_year"][2026]["roc_fuente"] == "estimacion"
    assert ts["refund_by_year"][2026]["refund"] == pytest.approx(15.0, abs=0.01)
    assert ts["refund_total_estimated"] == pytest.approx(45.0, abs=0.01)
    assert ts["refund_estimated"] == pytest.approx(15.0, abs=0.01)
    assert ts["withheld_real"] == pytest.approx(30.0, abs=0.01)
    assert ts["net_estimated"] == pytest.approx(15.0, abs=0.01)


def test_tax_summary_devuelto_de_mas_no_da_devolucion_negativa(monkeypatch):
    """Si el bróker ya devolvió MÁS de lo que estimamos, no falta nada por volver (cero, no
    negativo) y el fisco se queda el saldo — no una cifra por debajo de él."""
    ts = _f6_summary(monkeypatch, [
        ("2025-01-02", "Buy", "MSTY", 100, -2000.0),
        ("2025-06-01", "Dividend", "MSTY", 0, 100.0),
        ("2025-06-01", "NRA Tax Adj", "MSTY", 0, -30.0),
        ("2025-09-01", "NRA Tax Adj", "MSTY", 0, 28.0),
    ], {"MSTY": {"weighted_pct": 80.0,
                 "per_distribution": [{"date": "2025-06-01", "roc_pct": 80.0}]}}, {})
    assert ts["refund_total_estimated"] == pytest.approx(24.0, abs=0.01)
    assert ts["refund_estimated"] == 0.0
    assert ts["net_estimated"] == pytest.approx(ts["withheld_real"], abs=0.01)
    assert ts["withheld_real"] == pytest.approx(2.0, abs=0.01)


def test_roc_de_la_base_usa_el_cierre_en_años_cerrados(monkeypatch):
    """R1, base fiscal: el ROC en dólares de una distribución de año cerrado sale del cierre
    (ICI), no del 19(a) del día; en el año abierto, del 19(a). Un 0% de cierre anula el ROC
    del año aunque el 19(a) dijera 95%. Y la base ajustada baja por lo que dice el cierre."""
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {"MSTY": {"weighted_pct": 75.0,
        "per_distribution": [{"date": "2024-10-01", "roc_pct": 95.0},
                             {"date": "2025-06-01", "roc_pct": 70.0},
                             {"date": "2026-06-01", "roc_pct": 60.0}]}})
    monkeypatch.setattr(logic, "load_roc_ici", lambda: {"MSTY": {
        2024: {"roc_pct": 0.0}, 2025: {"roc_pct": 100.0}}})
    s = logic.analyze_portfolio(_roc_norm_df([
        ("2024-09-01", "Buy", "MSTY", 50, -1000.0),
        ("2024-10-01", "Dividend", "MSTY", 0, 100.0),
        ("2025-06-01", "Dividend", "MSTY", 0, 100.0),
        ("2026-06-01", "Dividend", "MSTY", 0, 100.0),
    ]), version="TEST_R1_BASE")["MSTY"]
    assert s["roc_source"] == "19a"
    assert s["roc_accumulated"] == pytest.approx(0.0 + 100.0 + 60.0, abs=0.01)
    assert s["roc_percent"] == pytest.approx(160.0 / 300.0 * 100.0, abs=0.01)
    u = s["capital_gains"]["unrealized"]
    assert u["basis_roc_adjusted"] == pytest.approx(u["basis"] - 160.0, abs=0.01)


def test_roc_fondo_solo_con_cierre_es_todo_o_nada(monkeypatch):
    """Un fondo sin avisos 19(a) pero con cierre fiscal: si todas sus distribuciones caen en
    años cerrados, su ROC sale del cierre; si una cae en un año abierto (sin % que la
    catalogue), no hay ROC — un ROC a medias no es una base fiscal (Regla 2)."""
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {})
    monkeypatch.setattr(logic, "load_roc_ici", lambda: {"CHPY": {2025: {"roc_pct": 24.47}}})
    ev = logic._roc_events_from_19a("CHPY", [(pd.Timestamp("2025-05-01"), 100.0),
                                             (pd.Timestamp("2025-11-01"), 50.0)])
    assert [r for _, r in ev] == pytest.approx([100.0 * 0.2447, 50.0 * 0.2447])
    assert logic._roc_events_from_19a("CHPY", [(pd.Timestamp("2025-05-01"), 100.0),
                                               (pd.Timestamp("2026-02-01"), 50.0)]) is None


def _schwab_daniel_df():
    import glob
    rutas = glob.glob(os.path.join(os.path.dirname(__file__), "real_examples",
                                   "charles_schwab_data", "daniel_zambrano", "*.csv"))
    if not rutas:
        pytest.skip("real_examples no montado (data privada)")
    with open(rutas[0], "rb") as f:
        df, _b = logic.load_and_detect_csv(FakeFile(f.read(), os.path.basename(rutas[0])))
    return logic.normalize_csv(df)


def test_refund_real_schwab_msty_2025_vuelve_entero_como_dice_el_1042s():
    """Ground truth externo: el 1042-S 2025 de Daniel reporta las 21 distribuciones de MSTY
    ($275.97) bajo el código 37 (ROC, tasa 0%), o sea que TODA la retención de 2025 ($82.81)
    se devuelve. Con el 19(a) (78.4%) la app devolvía $66.70 de ese año."""
    df = _schwab_daniel_df()
    res = logic.analyze_portfolio(df[df["Ticker"] == "MSTY"].copy(), version="TEST_R1_SCHWAB")
    ts = logic.build_tax_summary(res["MSTY"], "MSTY", base_rate_pct=30.0)
    y25 = ts["refund_by_year"][2025]
    assert y25["roc_fuente"] == "cierre"
    assert y25["roc_pct_usado"] == pytest.approx(100.0)
    assert y25["refund"] == pytest.approx(82.81, abs=0.01)
    assert ts["withheld_at_payment_by_year"][2025] == pytest.approx(82.81, abs=0.01)


def test_roc_real_schwab_msty_2025_baja_la_base_por_todo_el_bruto():
    """Ground truth del 1042-S 2025 de Daniel: todo MSTY 2025 fue ROC (código 37), así que
    los $275.97 de ese año bajan la base enteros; con el 19(a) bajaban $210.23. El ROC de
    MSTY 2024 fue 0% al cierre (el 19(a) decía ~73%): no baja nada."""
    df = _schwab_daniel_df()
    res = logic.analyze_portfolio(df[df["Ticker"] == "MSTY"].copy(), version="TEST_R1_BASE_R")
    s = res["MSTY"]
    ev = logic._roc_events_from_19a(
        "MSTY", [(d, float(a)) for d, a in logic._dividend_events(s["history"]).items()])
    por_anio = {}
    for d, r in ev:
        por_anio[pd.Timestamp(d).year] = por_anio.get(pd.Timestamp(d).year, 0.0) + r
    assert por_anio[2025] == pytest.approx(s["dividends_gross_by_year"][2025], abs=0.01)
    assert por_anio[2025] == pytest.approx(275.97, abs=0.01)
    assert por_anio[2024] == pytest.approx(0.0, abs=0.01)
    assert s["roc_accumulated"] == pytest.approx(sum(r for _, r in ev), abs=0.01)


def test_refund_real_ib_msty_lo_devuelto_se_resta_una_sola_vez():
    """IB MSTY real: los $23.25 retenidos en 2025 (cierre 100%) se acreditaron en 2026. Lo
    que falta por volver es el total menos esos $23.25 UNA vez, y lo que se queda el fisco es
    exactamente la retención justa (ningún año topa en cero ni en lo retenido)."""
    df = _load_real_ib_1()
    res = logic.analyze_portfolio(df[df["Ticker"] == "MSTY"].copy(), version="TEST_R1_IB")
    ts = logic.build_tax_summary(res["MSTY"], "MSTY", base_rate_pct=30.0)
    assert ts["refund_observed"] == pytest.approx(23.25, abs=0.01)
    assert ts["refund_by_year"][2025]["roc_fuente"] == "cierre"
    assert ts["refund_by_year"][2025]["refund"] == pytest.approx(23.25, abs=0.01)
    assert ts["withheld_at_payment"] == pytest.approx(ts["withheld_real"] + 23.25, abs=0.01)
    assert ts["refund_estimated"] == pytest.approx(ts["refund_total_estimated"] - 23.25,
                                                   abs=0.01)
    assert ts["net_estimated"] == pytest.approx(ts["fair_withholding"], abs=0.02)


# ── Objeto fiscal único `tax_summary` (Regla 3, specs/roc-nra-invariants.md) ────────────────
# Tolerancia $0.01 en todas las comparaciones (más estricta que el ±$0.05 de la spec, la
# satisface).

def _tax_summary_multi_year_setup(monkeypatch):
    """CSV sintético MSTY con retención NRA en 2 años calendario y %ROC distinto cada año
    (avisos 19a mockeados) — mismo fixture base de
    test_dividends_gross_and_withheld_by_year_match_totals, reusado aquí para el objeto
    fiscal único. Sin ib_cost_basis_map: roc_percent se estima vía los 19a (empate por fecha),
    igual que test_roc_estimated_from_19a_when_no_basis."""
    df = _roc_norm_df([
        ("2024-01-01", "Buy", "MSTY", 100, -2000.0),
        ("2024-06-01", "Dividend", "MSTY", 0, 300.0),
        ("2024-06-01", "NRA Tax Adj", "MSTY", 0, -90.0),
        ("2025-06-01", "Dividend", "MSTY", 0, 400.0),
        ("2025-06-01", "NRA Tax Adj", "MSTY", 0, -60.0),
    ])
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {
        "MSTY": {"per_distribution": [
            {"date": "2024-06-01", "roc_pct": 40.0},
            {"date": "2025-06-01", "roc_pct": 80.0},
        ]}})
    # 19a sintético: sin esto el cierre fiscal REAL de MSTY (roc_ici.yaml) pisa sus años.
    monkeypatch.setattr(logic, "load_roc_ici", lambda: {})
    return logic.analyze_portfolio(df, version="TEST_TAX_SUMMARY")


def test_tax_summary_is_single_source_across_views(monkeypatch):
    """Regla 3: tax_summary reusa estimate_roc_refund_by_year tal cual (no reimplementa su
    matemática), declara base/momento como estimado (Regla 2), y build_tax_summaries /
    build_hoja_excel lo consumen por IDENTIDAD — no una copia recalculada.

    Se parte de un summary DECLARADO (capa 2, país sin tratado) porque la capa 1 ya no
    declara tasa: sin residencia no hay devolución que estimar, y este test es sobre la
    aritmética de la devolución. La rama sin declarar la cubre `test_capa_1_no_declara_tasa`."""
    results = _tax_summary_multi_year_setup(monkeypatch)
    s = results["MSTY"]
    ts = logic.build_tax_summaries(
        results, base_rate_pct=logic.NRA_DEFAULT_RATE, country="Colombia")["MSTY"]
    assert ts is not None
    assert ts["rate_declared"] is True

    # (a) devolución estimada + neto estimado deben sumar exactamente el retenido real.
    assert ts["refund_estimated"] + ts["net_estimated"] == pytest.approx(
        ts["withheld_real"], abs=0.01)
    assert ts["withheld_real"] == pytest.approx(s["withheld_tax_total"], abs=0.01)

    # (b) coincide con llamar estimate_roc_refund_by_year directamente — misma tasa declarada
    # y mismo roc_fallback_pct (roc_percent del holder) que usa build_tax_summary.
    direct = logic.estimate_roc_refund_by_year(
        s["dividends_gross_by_year"], s["withheld_by_year"], "MSTY",
        base_rate=logic.NRA_DEFAULT_RATE / 100.0, roc_fallback_pct=s["roc_percent"])
    assert ts["refund_estimated"] == pytest.approx(direct["total"]["refund"], abs=0.01)
    assert ts["fair_withholding"] == pytest.approx(direct["total"]["fair_withholding"], abs=0.01)
    assert ts["by_year"] is True

    # (c) toda cifra declara base y momento (Regla 2): es una proyección, no efectivo recibido.
    assert ts["is_estimate"] is True
    assert ts["moment"] == "annual_reclass_estimate"
    assert ts["basis"] == "gross_withheld"

    # (d) build_hoja_excel propaga por IDENTIDAD el mismo objeto que recibe — no lo recalcula
    # ni lo copia. Es lo que impide que dos vistas muestren dos verdades del mismo dólar.
    sums = logic.build_tax_summaries(
        results, base_rate_pct=logic.NRA_DEFAULT_RATE, country="Colombia")
    he = logic.build_hoja_excel(results, classify_map={"MSTY": "mode_a"}, tax_summaries=sums)
    assert he["rows"][0]["tax_summary"] is sums["MSTY"]

    # Y la reutilización por identidad sigue viva para el caso sin declarar: pedir dos veces
    # lo mismo devuelve el objeto cacheado de capa 1, no una copia nueva.
    assert logic.build_tax_summaries(results)["MSTY"] is s["tax_summary"]


def test_tax_summary_no_toca_capital_ni_roc_dollars(monkeypatch):
    """Regla 1 (capital invariante) + Regla 4 (carriles del ROC que no se cruzan): agregar
    tax_summary no mueve pocket_investment/market_value/total_dividends, y roc_dollars de
    build_hoja_excel sigue viniendo de _roc_pct_for (19a ponderado histórico del fondo) —
    NUNCA de tax_summary['roc_pct_used'] (roc_percent, ROC realizado del holder). Son 2 de
    las 3 fuentes de %ROC que divergen a propósito; no se deben unificar."""
    df = _roc_norm_df([
        ("2024-01-01", "Buy", "MSTY", 100, -2000.0),
        ("2024-06-01", "Dividend", "MSTY", 0, 300.0),
        ("2024-06-01", "NRA Tax Adj", "MSTY", 0, -90.0),
        ("2025-06-01", "Dividend", "MSTY", 0, 400.0),
        ("2025-06-01", "NRA Tax Adj", "MSTY", 0, -60.0),
    ])
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {
        "MSTY": {"weighted_pct": 65.0, "per_distribution": [
            {"date": "2024-06-01", "roc_pct": 40.0},
            {"date": "2025-06-01", "roc_pct": 80.0},
        ]}})
    # 19a sintético: sin esto el cierre fiscal REAL de MSTY (roc_ici.yaml) pisa sus años.
    monkeypatch.setattr(logic, "load_roc_ici", lambda: {})
    results = logic.analyze_portfolio(df, version="TEST_TAX_SUMMARY_CAPITAL")
    s = results["MSTY"]

    assert s["pocket_investment"] == pytest.approx(2000.0, abs=0.01)
    assert s["total_dividends"] == pytest.approx(700.0, abs=0.01)
    assert s["market_value"] == pytest.approx(2000.0, abs=1.0)  # 100 acciones × $20 (mock plano)

    he = logic.build_hoja_excel(results, classify_map={"MSTY": "mode_a"})
    r = he["rows"][0]
    # Objeto fiscal único: bruto = declarado (`dividends_gross_total`), NO `total_dividends +
    # withheld_tax_total` — este fixture es convención Schwab (retención en fila aparte, el
    # CSV ya trae el bruto directo), así que sumarle la retención de nuevo la duplicaría.
    assert s["dividend_base_convention"] == "retencion_aparte"
    gross = s["dividends_gross_total"]
    # roc_dollars sigue viniendo de _roc_pct_for (weighted_pct 19a) — no del tax_summary.
    assert r["roc_pct"] == pytest.approx(65.0, abs=0.01)
    assert round(r["roc_dollars"], 2) == round(0.65 * gross, 2)
    # Regla 4: el summary trae `roc_pct_used` = `roc_percent` (ROC realizado del holder),
    # SIEMPRE distinto de `_roc_pct_for` (19a ponderado) que alimenta `roc_dollars`. El % de
    # ROC no depende de la tasa ni de la retención, así que lo publican también las rutas
    # nulas (sin país / sin retención) — ver `test_roc_sin_pais_ni_retencion.py`.
    ts_dec = logic.build_tax_summaries(
        results, base_rate_pct=logic.NRA_DEFAULT_RATE, country="Colombia")["MSTY"]
    ts_sin = logic.build_tax_summaries(results)["MSTY"]   # capa 1, sin declarar
    for ts in (ts_dec, ts_sin):
        assert ts["roc_pct_used"] == pytest.approx(s["roc_percent"], abs=0.01)
        assert ts["roc_pct_used"] != pytest.approx(r["roc_pct"], abs=0.01)  # carriles distintos
    # ...pero sin país NO corre la aritmética fiscal: nada de devolución.
    assert ts_sin["refund_estimated"] == 0.0
    assert ts_sin["method"] is None


@pytest.mark.parametrize("ticker,capital", [
    ("NVDY", 770.00),    # compra 60 × $15.00 = $900.00, venta 10 × $13.00 = $130.00
    ("CONY", 800.00),    # compra 80 × $10.00, sin venta
    ("SMH", 1000.00),    # compra 4 × $250.00, sin venta
])
def test_capital_aportado_resta_lo_que_devuelve_una_venta(monkeypatch, ticker, capital):
    """Regla 1 con ventas: el capital aportado es flujo de caja neto del bolsillo, así que
    una venta RESTA su importe. Anclado a las filas del CSV (`Gross Amount`; las comisiones
    de $1 no entran), no al motor.

    Auditoría M4 (H1): invertir el signo de la venta (`pocket_investment += abs(amount)`)
    sobrevivía a la suite completa aunque 18 tests ejecutaban esa línea — los que la
    recorren comparan vistas que derivan del MISMO `pocket_investment` y cuadran entre sí
    con el capital mal. Medido en NVDY: capital $770 → $1,030."""
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    res = logic.analyze_portfolio(_ib_synth_1_normalizado(), version="TEST_CAPITAL_TRAS_VENTA")
    assert res[ticker]["pocket_investment"] == pytest.approx(capital, abs=0.01), (
        f"{ticker}: capital aportado {res[ticker]['pocket_investment']} ≠ {capital} "
        f"(compras − importe de las ventas, leído de las filas del CSV)")


def test_build_tax_summaries_respeta_tasa_de_tratado(monkeypatch):
    """Capa 2: build_tax_summaries re-deriva con la tasa de tratado del país (México, 10%) en
    vez del 30% estatutario — la retención justa baja, la devolución estimada sube, y el
    objeto declara la tasa usada.

    La referencia contra la que se compara cambió a propósito: la capa 1 ya no rellena 30%
    "provisionalmente" (ver `test_capa_1_no_declara_tasa`), así que el contraste se hace
    contra el 30% pedido EXPLÍCITAMENTE, que es el caso real de un residente sin tratado."""
    results = _tax_summary_multi_year_setup(monkeypatch)
    sin_tratado = logic.build_tax_summaries(
        results, base_rate_pct=logic.NRA_DEFAULT_RATE, country="Colombia")["MSTY"]
    assert sin_tratado["base_rate_pct"] == pytest.approx(logic.NRA_DEFAULT_RATE)
    assert sin_tratado["rate_declared"] is True

    treaty_rate = logic.NRA_COUNTRY_RATES["México"][0]  # 10.0, con tratado
    treaty_ts = logic.build_tax_summaries(
        results, base_rate_pct=treaty_rate, country="México")["MSTY"]

    assert treaty_ts is not sin_tratado   # tasa distinta → no reusa por identidad, re-deriva
    assert treaty_ts["base_rate_pct"] == pytest.approx(treaty_rate)
    assert treaty_ts["fair_withholding"] < sin_tratado["fair_withholding"]
    assert treaty_ts["refund_estimated"] > sin_tratado["refund_estimated"]
    assert treaty_ts["net_estimated"] < sin_tratado["net_estimated"]


def test_capa_1_no_declara_tasa(monkeypatch):
    """`analyze_portfolio` (capa 1) corre bajo `@st.cache_data` y no puede ver el país del
    cliente, así que construye el objeto fiscal SIN DECLARAR — no con el 30% estatutario.

    Antes lo rellenaba con `NRA_DEFAULT_RATE` "provisionalmente" y la capa 2 nunca llegó a
    cablearse desde la UI: el provisional acabó siendo el número que veía todo el mundo,
    incluidos los residentes de México (10% por tratado). Sin país no se estima devolución;
    la retención REAL del CSV sí se sigue mostrando."""
    results = _tax_summary_multi_year_setup(monkeypatch)
    ts = results["MSTY"]["tax_summary"]

    assert ts["rate_declared"] is False
    assert ts["base_rate_pct"] is None
    assert ts["country"] is None
    assert ts["refund_estimated"] == 0.0
    assert ts["fair_withholding"] == 0.0
    # Lo que SÍ es un dato —lo que el bróker retuvo— no desaparece por no saber el país.
    assert ts["withheld_real"] == pytest.approx(results["MSTY"]["withheld_tax_total"], abs=0.01)
    assert ts["net_estimated"] == pytest.approx(ts["withheld_real"], abs=0.01)


def test_sin_declarar_no_es_cero_por_ciento(monkeypatch):
    """El centinela y la tasa 0% son cosas distintas, y confundirlas es la trampa de todo esto.

    Con 0% declarado (residente fiscal en EE.UU.) la retención justa es $0 y por tanto TODO
    lo retenido se estima como devolución. Esa lectura es correcta para quien declara 0% —
    y catastróficamente optimista como default para quien no declaró nada."""
    results = _tax_summary_multi_year_setup(monkeypatch)
    retenido = results["MSTY"]["withheld_tax_total"]

    cero = logic.build_tax_summaries(
        results, base_rate_pct=0.0, country="Estados Unidos")["MSTY"]
    assert cero["rate_declared"] is True
    assert cero["refund_estimated"] == pytest.approx(retenido, abs=0.01)   # todo vuelve

    sin_declarar = logic.build_tax_summaries(results)["MSTY"]
    assert sin_declarar["rate_declared"] is False
    assert sin_declarar["refund_estimated"] == 0.0        # no se estima, no es que sea cero
    assert sin_declarar["withheld_real"] == pytest.approx(retenido, abs=0.01)


def _stats_roc(withheld, roc_percent, roc_source="19a", gross=1000.0):
    """`stats` mínimo para `build_tax_summary` — un solo año, retención plegada estilo IB."""
    return {
        "withheld_tax_total": withheld,
        "total_dividends": round(gross - withheld, 2),
        "dividends_gross_total": gross,
        "dividends_gross_by_year": {2025: gross},
        "withheld_by_year": {2025: withheld} if withheld > 0.01 else {},
        "tax_refund_observed_by_year": {},
        "roc_percent": roc_percent, "roc_source": roc_source,
    }


def test_roc_sin_pais_ni_retencion_igual_publica_el_roc():
    """El % de ROC no depende de la tasa de residencia ni de que haya habido retención NRA.
    Las dos rutas nulas de `build_tax_summary` (`_undeclared`, `withheld <= 0.01`) publican
    ahora `roc_pct_used`/`roc_source` — antes cableaban `None` (daño colateral). Lo que sí
    sigue nulo es todo lo que depende de la tasa/retención: devolución y método."""
    # Ruta «sin país declarado» (RATE_UNDECLARED), con retención real.
    ts_und = logic.build_tax_summary(_stats_roc(50.0, 61.24, "19a"), "CONY",
                                     base_rate_pct=logic.RATE_UNDECLARED)
    assert ts_und["roc_pct_used"] == pytest.approx(61.24, abs=0.01)
    assert ts_und["roc_source"] == "19a"
    assert ts_und["rate_declared"] is False
    assert ts_und["refund_estimated"] == 0.0
    assert ts_und["method"] is None
    assert ts_und["withheld_real"] == pytest.approx(50.0, abs=0.01)

    # Ruta «sin retención NRA registrada» ($0), con país declarado.
    ts_wh0 = logic.build_tax_summary(_stats_roc(0.0, 72.59, "19a"), "MSTY",
                                     base_rate_pct=30.0, country="Colombia")
    assert ts_wh0["roc_pct_used"] == pytest.approx(72.59, abs=0.01)
    assert ts_wh0["roc_source"] == "19a"
    assert ts_wh0["refund_estimated"] == 0.0
    assert ts_wh0["method"] is None


def test_roc_negativo_es_sin_dato():
    """Un `roc_percent` negativo (resta del método 'broker' que no cuadra — traspasos con
    costo base sin importe) NO es un hecho fiscal: `roc_pct_used`/`roc_source` salen `None`
    y la fila tributa sobre el bruto completo. El saneado vive en el carril fiscal, no en
    `stats['roc_percent']` (Regla 4)."""
    for roc_neg in (-0.78, -65.29):
        # con país declarado + retención: el negativo cae a la ruta nula por «sin % ROC».
        ts = logic.build_tax_summary(_stats_roc(40.0, roc_neg, "broker"), "PLTY",
                                     base_rate_pct=30.0, country="Colombia")
        assert ts["roc_pct_used"] is None, roc_neg
        assert ts["roc_source"] is None, roc_neg
        assert ts["refund_estimated"] == 0.0
        # sin país tampoco lo resucita
        ts_und = logic.build_tax_summary(_stats_roc(40.0, roc_neg, "broker"), "PLTY",
                                         base_rate_pct=logic.RATE_UNDECLARED)
        assert ts_und["roc_pct_used"] is None, roc_neg


def test_roc_cero_medido_sigue_siendo_dato():
    """`roc_percent == 0.0` es un CERO MEDIDO (SMH del demo de Schwab: `roc 0.0 / broker`),
    no «sin dato»: se conserva `roc_pct_used == 0.0` y `roc_source` intacto. Es el caso que
    separa un guard bien escrito (`< 0`) de uno con `if not roc_pct`."""
    ts = logic.build_tax_summary(_stats_roc(20.0, 0.0, "broker"), "SMH",
                                 base_rate_pct=30.0, country="Colombia")
    assert ts["roc_pct_used"] == 0.0
    assert ts["roc_source"] == "broker"
    # ROC 0% ⇒ no reduce la retención, pero eso es un resultado, no ausencia de dato.
    ts_und = logic.build_tax_summary(_stats_roc(0.0, 0.0, "broker"), "SMH",
                                     base_rate_pct=logic.RATE_UNDECLARED)
    assert ts_und["roc_pct_used"] == 0.0
    assert ts_und["roc_source"] == "broker"


def test_ninguna_ruta_null_publica_devolucion():
    """Invariante que el fix NO puede romper: ninguna de las rutas nulas —tocadas o no—
    publica una devolución estimada ni un método."""
    casos = [
        # (stats, kwargs)
        (_stats_roc(50.0, 60.0), dict(base_rate_pct=logic.RATE_UNDECLARED)),         # _undeclared
        (_stats_roc(0.0, 60.0), dict(base_rate_pct=30.0, country="Colombia")),       # withheld<=0.01
        (_stats_roc(50.0, None), dict(base_rate_pct=30.0, country="Colombia")),      # roc None
        (_stats_roc(50.0, -12.0), dict(base_rate_pct=30.0, country="Colombia")),     # roc negativo
    ]
    for stats, kw in casos:
        ts = logic.build_tax_summary(stats, "X", **kw)
        assert ts["refund_estimated"] == 0.0, kw
        assert ts["method"] is None, kw
        assert ts["fair_withholding"] == 0.0, kw
        assert ts["by_year"] is False, kw


# ── R2 — la casilla 9 mezcla años con tasas distintas (auditoría 2026-09-18) ────────────
#
# `_roc_refund_recuperable` usaba UNA tasa (la aplicada agregada) y UN escudo (el ROC del
# holder) para todos los años: en un fondo con un año sin escudo (retención plana) y otro
# con el escudo YA aplicado al cobro (IB reclasificó antes de emitir el CSV), esa mezcla
# cuenta el escudo dos veces en el año que ya lo tenía. El fix mide la tasa del bróker
# (`broker_withholding_rate_pct`, la tasa LEGAL más cercana a la máxima aplicada por año) y
# corre `_refund_total_al_cobro` año por año — la misma función que ya usaba `build_tax_summary`.

def test_r2_casilla9_por_anio_no_mezcla_tasas(monkeypatch):
    """Caso sintético: 2 años, bruto 1000/1000. 2024 retuvo 4.30 (0.43%, escudo YA aplicado —
    cierre ICI 100%); 2025 retuvo 300.00 (30%, sin escudo — cierre ICI 40%). ROC del holder
    60% (no se usa: ambos años tienen cierre ICI). La fórmula vieja (una tasa/escudo para
    todo) daba 182.62; la correcta, año por año, da 124.30 — exactamente el objeto fiscal
    al 30%."""
    hist = _roc_norm_df([
        ("2024-06-14", "Cash Dividend", "ZZZZ", 0, 1000.0),
        ("2024-06-14", "NRA Tax Adj", "ZZZZ", 0, -4.30),
        ("2025-06-13", "Cash Dividend", "ZZZZ", 0, 1000.0),
        ("2025-06-13", "NRA Tax Adj", "ZZZZ", 0, -300.00),
    ])
    s = {
        "history": hist,
        "dividends_gross_by_year": {2024: 1000.0, 2025: 1000.0},
        "dividends_gross_total": 2000.0,
        "withheld_tax_total": 304.30,
        "total_dividends": round(2000.0 - 304.30, 2),
        "withheld_by_year": {2024: 4.30, 2025: 300.00},
        "tax_refund_observed_by_year": {},
        "roc_percent": 60.0, "roc_source": "broker",
    }
    monkeypatch.setattr(logic, "load_roc_ici", lambda: {
        "ZZZZ": {2024: {"roc_pct": 100.0}, 2025: {"roc_pct": 40.0}}})
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {})

    diag = logic.build_withholding_diagnosis(s, "ZZZZ", entitled_pct=None)
    assert diag["refund_roc"] == pytest.approx(124.30, abs=0.01)
    ts = logic.build_tax_summary(s, "ZZZZ", base_rate_pct=30.0)
    assert ts["refund_total_estimated"] == pytest.approx(124.30, abs=0.01)
    assert diag["refund_roc"] == pytest.approx(ts["refund_total_estimated"], abs=0.01)


def test_r2_tasa_del_broker_redondea_a_la_legal():
    """Caso sintético: 1 año, bruto 1000, retenido 302.20 (30.22% aparente por redondeo de
    centavos), ROC 50%. `broker_withholding_rate_pct` redondea la tasa observada a la legal
    más cercana (30.0, no 30.22) y la devolución sale 152.20 (= 302.20 − 0.30·1000·0.50)."""
    hist = _roc_norm_df([
        ("2025-06-01", "Cash Dividend", "YYYY", 0, 1000.0),
        ("2025-06-01", "NRA Tax Adj", "YYYY", 0, -302.20),
    ])
    s = {
        "history": hist,
        "dividends_gross_by_year": {2025: 1000.0},
        "dividends_gross_total": 1000.0,
        "withheld_tax_total": 302.20,
        "total_dividends": round(1000.0 - 302.20, 2),
        "withheld_by_year": {2025: 302.20},
        "tax_refund_observed_by_year": {},
        "roc_percent": 50.0, "roc_source": "broker",
    }
    diag = logic.applied_withholding_rate(s)
    assert logic.broker_withholding_rate_pct(diag) == pytest.approx(30.0)

    out = logic.build_withholding_diagnosis(s, "YYYY", entitled_pct=None)
    assert out["refund_roc"] == pytest.approx(152.20, abs=0.01)


def test_build_tax_summaries_etiqueta_el_pais(monkeypatch):
    """El campo `country` debe traer la etiqueta del país cuyo tratado se aplicó (antes quedaba
    siempre en None). Y la reutilización por identidad tiene que mirar el país, no solo la
    tasa: si no, un objeto de capa 1 (country=None) se reusaría para un país con tratado y la
    vista mostraría la etiqueta equivocada."""
    results = _tax_summary_multi_year_setup(monkeypatch)
    capa1_ts = results["MSTY"]["tax_summary"]
    assert capa1_ts["country"] is None             # capa 1: sin declarar, sin país

    treaty_rate = logic.NRA_COUNTRY_RATES["México"][0]
    sums = logic.build_tax_summaries(results, base_rate_pct=treaty_rate, country="México")
    assert sums["MSTY"]["country"] == "México"
    assert sums["MSTY"]["base_rate_pct"] == pytest.approx(treaty_rate)

    # Sin argumentos = sin declarar, igual que capa 1 → sí reusa por identidad.
    assert logic.build_tax_summaries(results)["MSTY"] is capa1_ts

    # Dos países SIN tratado comparten tasa (30%) pero no etiqueta: la reutilización por
    # identidad debe mirar ambas, o una vista pintaría el país equivocado.
    colombia = logic.build_tax_summaries(
        results, base_rate_pct=logic.NRA_DEFAULT_RATE, country="Colombia")["MSTY"]
    peru = logic.build_tax_summaries(
        results, base_rate_pct=logic.NRA_DEFAULT_RATE, country="Perú")["MSTY"]
    assert colombia is not capa1_ts                 # capa 1 no declara tasa: no puede reusarse
    assert colombia is not peru
    assert colombia["country"] == "Colombia" and peru["country"] == "Perú"
    assert colombia["refund_estimated"] == pytest.approx(
        peru["refund_estimated"], abs=0.01)         # la etiqueta no altera la aritmética


# ── Objeto fiscal único: bruto/retención/neto (PR B, build_dividend_tax_totals) ─────────────
# Escala declarada en cada aserción — por ticker vs portafolio no son comparables entre sí
# (ver Obsidian feedback_dividend-invariante-roc-nra). Ground truth verificado por Opus.

def test_build_dividend_tax_totals_schwab_style_no_duplica_retencion():
    """Convención Schwab (retención en fila 'NRA Tax Adj' aparte, sin 'dividend' en el
    Action): el CSV ya entrega el bruto directo -> el neto se DERIVA restando, nunca al
    revés. `fixtures/schwab_synth_2` MSTY: 90+82+74+66+58+50+42 = $462 bruto (suma de los
    'Cash Dividend'), retención = 30% exacto = $138.60, neto = $323.40 (ESCALA: por ticker)."""
    raw = open(os.path.join(os.path.dirname(__file__), "fixtures", "schwab_synth_2",
                             "synthetic_transactions.csv"), "rb").read()
    df, broker = logic.load_and_detect_csv(FakeFile(raw, "schwab_synth_2.csv"))
    assert broker == "schwab"
    dfc = logic.normalize_csv(df)
    sub = dfc[dfc["Ticker"] == "MSTY"]
    tt = logic.build_dividend_tax_totals(sub)
    assert tt["netted"] is False
    assert tt["gross_source"] == "leido"
    assert tt["net_source"] == "derivado"
    assert tt["gross"] == pytest.approx(462.00, abs=0.01)
    assert tt["withheld"] == pytest.approx(138.60, abs=0.01)
    assert tt["net"] == pytest.approx(323.40, abs=0.01)
    # Identidad de reconciliación: bruto − retención = neto, contra el CSV como fuente.
    assert round(tt["gross"] - tt["withheld"], 2) == pytest.approx(tt["net"], abs=0.01)


def test_build_dividend_tax_totals_ib_style_neteada_en_la_fila():
    """Convención IB (retención plegada como fila negativa 'Dividend - Foreign Tax
    Withholding', SÍ comparte 'dividend' con el Action): el CSV ya entrega el neto directo ->
    el bruto se DERIVA sumando. `real_examples/interactive_brokers_data/1` MSTY: bruto
    $7,224.59, retención $545.52, neto $6,679.07 (ESCALA: por ticker) — mismas cifras que
    `test_ib_withheld_tax_neto_por_ticker`, ahora también verificadas del lado del bruto/neto,
    no solo de la retención."""
    dfc = _load_real_ib_1()
    sub = dfc[dfc["Ticker"] == "MSTY"]
    tt = logic.build_dividend_tax_totals(sub)
    assert tt["netted"] is True
    # Desde el fix de la familia `_dividend_*` el ledger excluye las filas de impuesto en
    # ambas convenciones: el BRUTO es LEÍDO en las dos y el neto se DERIVA restando.
    assert tt["gross_source"] == "leido"
    assert tt["net_source"] == "derivado"
    assert tt["gross"] == pytest.approx(7224.59, abs=0.01)
    assert tt["withheld"] == pytest.approx(545.52, abs=0.01)
    assert tt["net"] == pytest.approx(6679.07, abs=0.01)
    assert round(tt["gross"] - tt["withheld"], 2) == pytest.approx(tt["net"], abs=0.01)


@pytest.mark.parametrize("ticker,expected_withheld", [
    ("TSLY", 495.01),
    ("CONY", 202.98),
])
def test_build_dividend_tax_totals_ib_no_rompe_pr_a(ticker, expected_withheld):
    """No-regresión del PR A (fix/ingesta-ib-old-reversos): TSLY/CONY deben seguir dando la
    misma retención neta que ya tenían verificada — el objeto fiscal único reusa
    `withheld_tax_total` por identidad, no la reimplementa."""
    dfc = _load_real_ib_1()
    sub = dfc[dfc["Ticker"] == ticker]
    tt = logic.build_dividend_tax_totals(sub)
    assert tt["netted"] is True
    assert tt["withheld"] == pytest.approx(expected_withheld, abs=0.01)
    assert round(tt["gross"] - tt["withheld"], 2) == pytest.approx(tt["net"], abs=0.01)


def test_analyze_portfolio_ib_msty_dividend_base_convention(monkeypatch):
    """`analyze_portfolio` propaga el objeto fiscal único al dict de resultados: convención
    detectada, bruto/neto agregados, y `observed_tax_refund_by_year` con el reembolso ROC
    genuino de IB ($23.25 en 2026, positiva huérfana) — ya NO se excluye IB en bloque, ver
    `test_ib_observed_refund_separa_reverso_de_split_de_reembolso_genuino`."""
    dfc = _load_real_ib_1()
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    res = logic.analyze_portfolio(dfc, version="TEST_TAX_TOTALS_IB")
    s = res["MSTY"]
    assert s["dividend_base_convention"] == "retencion_en_fila"
    assert s["dividends_gross_total"] == pytest.approx(7224.59, abs=0.01)
    assert s["dividends_net_total"] == pytest.approx(6679.07, abs=0.01)
    assert s["withheld_tax_total"] == pytest.approx(545.52, abs=0.01)
    assert {y: round(v, 2) for y, v in s["tax_refund_observed_by_year"].items()} == {2026: 23.25}
    # IB no tiene ninguna fila 'Foreign Tax Paid' → el campo nuevo queda en cero y la
    # retención NRA no se movió por el fix del impuesto extranjero.
    assert s["foreign_tax_paid_total"] == pytest.approx(0.0)
    assert s["foreign_tax_paid_by_year"] == {}


def test_analyze_portfolio_schwab_msty_dividend_base_convention(monkeypatch):
    """Mismo contrato que el test IB de arriba, del lado Schwab: convención 'retencion_aparte' y
    bruto/neto agregados coinciden con el ground truth ($462/$138.60/$323.40)."""
    raw = open(os.path.join(os.path.dirname(__file__), "fixtures", "schwab_synth_2",
                             "synthetic_transactions.csv"), "rb").read()
    df, broker = logic.load_and_detect_csv(FakeFile(raw, "schwab_synth_2.csv"))
    dfc = logic.normalize_csv(df)
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    res = logic.analyze_portfolio(dfc, version="TEST_TAX_TOTALS_SCHWAB")
    s = res["MSTY"]
    assert s["dividend_base_convention"] == "retencion_aparte"
    assert s["dividends_gross_total"] == pytest.approx(462.00, abs=0.01)
    assert s["dividends_net_total"] == pytest.approx(323.40, abs=0.01)
    assert s["withheld_tax_total"] == pytest.approx(138.60, abs=0.01)


def test_analyze_portfolio_propaga_foreign_tax_paid(monkeypatch):
    """`schwab_synth_1` SCHB: NRA -$0.45 + `Foreign Tax Paid` -$0.08. `analyze_portfolio`
    saca el FTP del eje NRA (`withheld_tax_total` = 0.45, no 0.53) y lo expone en su propio
    campo. `dividends_net_total` sube el mismo importe que salió de la retención."""
    raw = open(os.path.join(os.path.dirname(__file__), "fixtures", "schwab_synth_1",
                             "synthetic_transactions.csv"), "rb").read()
    df, _ = logic.load_and_detect_csv(FakeFile(raw, "schwab_synth_1.csv"))
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    res = logic.analyze_portfolio(logic.normalize_csv(df), version="TEST_FTP")
    s = res["SCHB"]
    assert s["withheld_tax_total"] == pytest.approx(0.45, abs=0.01)
    assert s["foreign_tax_paid_total"] == pytest.approx(0.08, abs=0.01)
    assert s["foreign_tax_paid_by_year"] == {2025: pytest.approx(0.08, abs=0.01)}


def test_analyze_portfolio_roi_neto_schwab_no_ignora_la_retencion(monkeypatch):
    """Auditoría de Opus al PR B (PR C, Parte 1): `gross_value = market_value +
    dividends_collected_cash` sumaba BRUTO para Schwab (la retención vive en 'NRA Tax Adj',
    fila que ningún branch del loop de clasificación tocaba) -> ROI/Retorno Total/IRR salían
    sobreestimados. Medido con `fixtures/schwab_synth_2` MSTY (mismo mock de mercado $20/share
    que usa todo este archivo): net_profit baja exactamente $138.60 (la retención) y ROI baja
    +4.36 pp al arreglar el fix — cifras verificadas por Opus antes del fix.
    `dividends_collected_cash` NO cambia (sigue $462, el crudo bruto) — el fix vive en
    gross_value/net_profit/roi/IRR, no en el campo crudo (otros consumidores lo siguen
    leyendo tal cual; ver test_analyze_portfolio_schwab_msty_dividend_base_convention)."""
    raw = open(os.path.join(os.path.dirname(__file__), "fixtures", "schwab_synth_2",
                             "synthetic_transactions.csv"), "rb").read()
    df, broker = logic.load_and_detect_csv(FakeFile(raw, "schwab_synth_2.csv"))
    dfc = logic.normalize_csv(df)
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    res = logic.analyze_portfolio(dfc, version="TEST_ROI_NETO_SCHWAB")
    s = res["MSTY"]
    assert s["dividends_collected_cash"] == pytest.approx(462.0, abs=0.01)   # crudo, sin tocar
    assert s["pocket_investment"] == pytest.approx(3176.0, abs=0.01)
    old_net_profit = s["market_value"] + 462.0 - s["pocket_investment"]      # fórmula pre-fix
    old_roi = old_net_profit / s["pocket_investment"] * 100
    expected_net_profit = s["market_value"] + 323.40 - s["pocket_investment"]  # 462 − 138.60
    assert s["net_profit"] == pytest.approx(expected_net_profit, abs=0.01)
    assert s["net_profit"] == pytest.approx(old_net_profit - 138.60, abs=0.01)
    assert s["roi_percent"] == pytest.approx(
        expected_net_profit / s["pocket_investment"] * 100, abs=0.01)
    assert s["roi_percent"] == pytest.approx(old_roi - 4.36, abs=0.02)


def test_analyze_portfolio_roi_neto_ib_no_resta_la_retencion_dos_veces(monkeypatch):
    """Convención IB: `dividends_collected_cash` ya viene neto (retención plegada en la
    propia fila de dividendo). El fix debe usarlo TAL CUAL para gross_value/net_profit/roi —
    restarle `withheld_tax_total` otra vez encima duplicaría la retención. Es la misma
    asimetría bruto/neto que ya resolvió el PR B, ahora también cubierta del lado de
    ROI/Retorno Total."""
    dfc = _load_real_ib_1()
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    res = logic.analyze_portfolio(dfc, version="TEST_ROI_NETO_IB")
    s = res["MSTY"]
    expected_net_profit = s["market_value"] + s["dividends_collected_cash"] - s["pocket_investment"]
    assert s["net_profit"] == pytest.approx(expected_net_profit, abs=0.01)
    assert s["roi_percent"] == pytest.approx(
        expected_net_profit / s["pocket_investment"] * 100, abs=0.01)


def test_build_hoja_excel_sin_tax_summary_no_rompe():
    """Fixture legado (dict a mano sin tax_summary, igual que usan los tests preexistentes de
    build_hoja_excel — test_build_hoja_excel_roc_dollars_trap y vecino) no debe lanzar
    KeyError: nra_refund_est/nra_net_est siempre tienen default seguro."""
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
    assert r["tax_summary"] is None
    assert r["nra_refund_est"] == 0.0
    assert r["nra_net_est"] == r["nra_tax"]
    assert out["totals"]["nra_refund_est"] == 0.0
    assert out["totals"]["nra_net_est"] == out["totals"]["nra_tax"]


def test_ticker_roc_fraction_uses_average_of_last_12_notices(monkeypatch):
    """(a) Con 15 avisos disponibles, toma el promedio de los 12 MÁS RECIENTES (no el
    histórico completo ni weighted_pct)."""
    # 15 avisos mensuales sintéticos: los 3 más viejos en 30%, los 12 más recientes en 60%.
    old = [{"date": f"2023-0{i}-01", "roc_pct": 30.0} for i in range(1, 4)]
    recent = [{"date": f"2024-{i:02d}-01", "roc_pct": 60.0} for i in range(1, 13)]
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {
        "MSTY": {"weighted_pct": 30.0, "per_distribution": old + recent}})
    frac = logic._ticker_roc_fraction("MSTY")
    assert frac == pytest.approx(60.0, abs=0.01)


def test_ticker_roc_fraction_falls_back_to_weighted_pct_with_few_notices(monkeypatch):
    """(b) Con solo 2 avisos (< mínimo de 3), cae a weighted_pct en vez del promedio."""
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {
        "MSTY": {"weighted_pct": 72.0, "per_distribution": [
            {"date": "2026-01-01", "roc_pct": 10.0},
            {"date": "2026-02-01", "roc_pct": 20.0}]}})
    frac = logic._ticker_roc_fraction("MSTY")
    assert frac == pytest.approx(72.0, abs=0.01)


def test_ticker_roc_fraction_falls_back_to_holder_roc_percent_without_19a(monkeypatch):
    """(c) Sin datos 19a para el ticker, cae al roc_percent ya calculado en results."""
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {})
    frac = logic._ticker_roc_fraction("ZZZY", results={"ZZZY": {"roc_percent": 45.0}})
    assert frac == pytest.approx(45.0, abs=0.01)
    # Sin 19a y sin results tampoco -> 0
    assert logic._ticker_roc_fraction("ZZZY") == 0.0


def test_ticker_roc_fraction_bounded_0_100(monkeypatch):
    """(d) Acotado a [0, 100] incluso si el YAML trae valores fuera de rango."""
    monkeypatch.setattr(logic, "load_roc_19a", lambda: {
        "MSTY": {"weighted_pct": 150.0, "per_distribution": [
            {"date": "2026-01-01", "roc_pct": 200.0},
            {"date": "2026-02-01", "roc_pct": -50.0}]}})
    frac = logic._ticker_roc_fraction("MSTY")
    assert 0.0 <= frac <= 100.0


def test_ticker_roc_fraction_msty_recent_average_not_weighted():
    """MSTY reporta 19a semanal con ROC% muy volátil semana a semana (0% a 99%), así que el
    promedio de los últimos 12 avisos se MUEVE con cada refresh automático de
    knowledge/roc_19a.yaml — NO se fija un valor exacto aquí (eso rompía cada 1-2 semanas sin
    que hubiera ningún bug real, ver historial del commit que introdujo este comentario).

    En vez de un número fijo se recalcula aquí el promedio esperado desde el MISMO YAML que lee
    la función: eso sobrevive a cualquier refresh de datos y aun así falla si la función deja de
    promediar bien (una aserción de rango tipo `frac < weighted` no sirve: pasaría igual con
    0% o 5%, que serían valores rotos).

    ── 2026-09-08: se retiró el segundo invariante de este test ──────────────────────────────
    Hasta hoy había aquí una segunda aserción, `frac < weighted_pct - 10`: el weighted_pct
    histórico de MSTY (ROC acumulado desde su lanzamiento) venía siendo consistentemente MAYOR
    que el promedio reciente, y se usaba como canario de que la función mira el dato reciente
    (forward) y no lo diluye con todo el histórico. Su propio docstring decía que si la brecha
    desaparecía había que revisar el perfil del fondo, no relajar el test. **La brecha
    desapareció y el perfil del fondo cambió de verdad**, medido sobre el YAML del 2026-09-05:

        weighted_pct .................. 72.31
        promedio 12 recientes ......... 68.09   (era el que debía quedar por debajo de 62.31)
        promedio de los 56 avisos ..... 69.67   (histórico completo: ya converge con el reciente)
        promedio 4 recientes .......... 74.05   (ya POR ENCIMA del weighted_pct)

    Y no es ruido: moviendo la ventana de 12 semana a semana, el promedio reciente va
    40.3 → 48.0 → 53.2 → 59.9 → 68.1 en las últimas 10 semanas. MSTY imprimió ~97-99% de ROC en
    8 de los 12 avisos más recientes (0% solo el 19-ago, 1-jul y 10-jun). La brecha no se cerró:
    se está invirtiendo, así que ampliar el margen a -5 compraba una o dos semanas y volvía a
    romper. Ojo: `knowledge/roc_health_history.yaml` NO vio este cambio (MSTY lleva
    'destructive' sin interrupción desde junio) porque sigue el weighted_pct, que apenas se
    movió — el giro está en la ventana reciente.

    El mutante que esa aserción pretendía cazar («la función devuelve weighted_pct o el promedio
    del histórico completo en vez de los 12 recientes») ya lo caza con datos sintéticos
    `test_ticker_roc_fraction_uses_average_of_last_12_notices` (3 avisos viejos al 30%, 12
    recientes al 60%, weighted_pct 30) — ese sí muerde sin depender de qué haga YieldMax."""
    info = logic.load_roc_19a().get("MSTY")
    if not info or not info.get("per_distribution") or len(info["per_distribution"]) < 3:
        pytest.skip("sin knowledge/roc_19a.yaml con per_distribution para MSTY")

    dated = []
    for rowp in info["per_distribution"]:
        try:
            dated.append((pd.Timestamp(rowp["date"]), float(rowp["roc_pct"])))
        except Exception:
            continue
    dated.sort(key=lambda dp: dp[0], reverse=True)
    recent = dated[:12]
    expected = sum(v for _, v in recent) / len(recent)

    frac = logic._ticker_roc_fraction("MSTY")
    assert frac == pytest.approx(expected, abs=0.01), (
        f"debe ser el promedio de los {len(recent)} avisos 19a más recientes "
        f"({expected:.2f}%), obtenido {frac:.2f}%")


# ── 1042-S: extracción del crédito ROC (casilla 10, income code 37) ───────────

def test_sum_roc_credit_from_forms_only_code_37():
    per_form = [
        {"income_code": "01", "gross_income": 1, "federal_tax_withheld": 0, "withholding_credit": 0},
        {"income_code": "06", "gross_income": 28, "federal_tax_withheld": 8, "withholding_credit": 8},
        {"income_code": "37", "gross_income": 276, "federal_tax_withheld": 83, "withholding_credit": 83},
    ]
    result = logic._sum_roc_credit_from_forms(per_form)
    assert result["credit"] == pytest.approx(83.0)
    assert result["roc_gross"] == pytest.approx(276.0)
    assert len(result["per_form"]) == 1


def test_sum_roc_credit_from_forms_sums_multiple_code_37():
    per_form = [
        {"income_code": "37", "gross_income": 100, "withholding_credit": 30},
        {"income_code": "37", "gross_income": 200, "withholding_credit": 60},
    ]
    result = logic._sum_roc_credit_from_forms(per_form)
    assert result["credit"] == pytest.approx(90.0)
    assert result["roc_gross"] == pytest.approx(300.0)
    assert len(result["per_form"]) == 2


def test_sum_roc_credit_from_forms_no_code_37():
    per_form = [
        {"income_code": "01", "gross_income": 1, "withholding_credit": 0},
        {"income_code": "06", "gross_income": 28, "withholding_credit": 8},
    ]
    result = logic._sum_roc_credit_from_forms(per_form)
    assert result == {"credit": 0.0, "roc_gross": 0.0, "per_form": []}


def test_sum_roc_credit_from_forms_falls_back_to_7a():
    per_form = [
        {"income_code": "37", "gross_income": 276, "federal_tax_withheld": 83, "withholding_credit": None},
    ]
    result = logic._sum_roc_credit_from_forms(per_form)
    assert result["credit"] == pytest.approx(83.0)


def test_sum_roc_credit_from_forms_int_and_str_code():
    per_form = [
        {"income_code": 37, "gross_income": 100, "withholding_credit": 30},
        {"income_code": "37", "gross_income": 50, "withholding_credit": 10},
    ]
    result = logic._sum_roc_credit_from_forms(per_form)
    assert result["credit"] == pytest.approx(40.0)
    assert len(result["per_form"]) == 2


def test_analyze_portfolio_cache_caduca():
    """N2 (auditoría de privacidad 2026-09-17): sin ttl ni max_entries, el resultado de cada
    análisis quedaba en la memoria del proceso hasta reiniciarlo. PRIVACY.md promete que se
    descarta en 1 hora; dentro de la sesión el resultado vive en `_vd_resultados`."""
    info = logic.analyze_portfolio._info
    assert info.ttl is not None, "el resultado del análisis nunca caduca"
    assert info.ttl <= 3600
    assert info.max_entries is not None, "el caché del análisis crece sin tope"


def test_extract_roc_credit_from_pdf_retirada():
    """Retirada el 2026-09-18 (auditoría de privacidad, S1): mandaba el 1042-S completo a
    Gemini y no tenía consumidor vivo."""
    assert not hasattr(logic, "extract_roc_credit_from_pdf")


# ── Alineación de transacciones al calendario bursátil ────────────────────────

def test_snap_to_trading_days_defers_instead_of_dropping():
    """`_snap_to_trading_days` mueve una fecha sin cotización al siguiente día hábil.

    El `reindex` a secas que había antes DESCARTABA esas fechas y su importe desaparecía
    del acumulado. Aquí se comprueba lo contrario: nada se pierde, y lo que ya cotiza no
    se mueve.
    """
    index = pd.DatetimeIndex(["2025-12-12", "2025-12-15", "2025-12-16"])  # vie, lun, mar

    # Sábado y domingo caen al lunes; ambos importes se conservan y se suman.
    fin_de_semana = pd.Series([100.0, 5.0], index=pd.DatetimeIndex(["2025-12-13", "2025-12-14"]))
    snapped = logic._snap_to_trading_days(fin_de_semana, index)
    assert snapped.sum() == pytest.approx(105.0), "no se puede perder ningún importe"
    assert snapped.loc[pd.Timestamp("2025-12-15")] == pytest.approx(105.0)

    # Una fecha que YA cotiza no se mueve: el resultado es idéntico al de antes del fix.
    habil = pd.Series([42.0], index=pd.DatetimeIndex(["2025-12-16"]))
    assert logic._snap_to_trading_days(habil, index).loc[pd.Timestamp("2025-12-16")] == 42.0

    # Posterior al último día con precio: no hay dónde ponerla, se descarta.
    futuro = pd.Series([7.0], index=pd.DatetimeIndex(["2026-01-05"]))
    assert len(logic._snap_to_trading_days(futuro, index)) == 0


def test_weekend_purchase_keeps_cost_curve(monkeypatch):
    """Una compra fechada en sábado debe seguir contando en la curva de capital invertido.

    Regresión (2026-08-08): `daily_activity.reindex(market_data.index)` descartaba toda
    transacción cuya fecha no fuera día de cotización — fin de semana, feriado, halt o
    hueco de yfinance — y el importe se perdía del `cumsum`. La curva de 'Invested Capital'
    quedaba plana en CERO durante toda la serie y `assess_ticker_quality` marcaba el ticker
    como 'unreliable' (`no_cost_recorded`), aunque el costo, el ROI y el valor de mercado
    fueran correctos: se calculan por otra vía. Alcanzable de verdad con transferencias
    ACATS fechadas en fin de semana y con extractos de IB en zona horaria no estadounidense.
    """
    # 2025-12-13 es SÁBADO: el mercado no abre.
    csv = (
        b"Transaction History,Header,Date,Account,Description,Transaction Type,"
        b"Symbol,Quantity,Price,Price Currency,Gross Amount,Commission,Net Amount\n"
        b"Transaction History,Data,2025-12-13,U123,Buy MSTY,Buy,MSTY,100,20.00,USD,-2000.00,-1.0,-2001.00\n"
    )
    df, _ = logic.load_and_detect_csv(FakeFile(csv))
    df_clean = logic.normalize_csv(df)

    def mock_fetch(ticker, start_date):
        # Solo días hábiles: viernes 12, lunes 15, martes 16. El sábado NO existe.
        idx = pd.DatetimeIndex(["2025-12-12", "2025-12-15", "2025-12-16"])
        data = pd.DataFrame(
            {"Close": [20.0, 20.0, 20.0], "Dividends": [0.0, 0.0, 0.0],
             "Stock Splits": [0.0, 0.0, 0.0], "VOO Price": [500.0, 500.0, 500.0]},
            index=idx,
        )
        return data, None

    monkeypatch.setattr(logic, "fetch_market_data", mock_fetch)
    results = logic.analyze_portfolio(df_clean, version="TEST_WEEKEND_BUY")

    trend = results["MSTY"]["daily_trend"]
    invertido = trend["Invested Capital"].max()
    assert invertido == pytest.approx(2000.00, abs=0.01), (
        f"la compra del sábado debe entrar el lunes, no perderse: curva = ${invertido:.2f}")

    # Y el ticker no debe salir marcado como no confiable por una fecha de fin de semana.
    calidad = logic.assess_ticker_quality(results, "MSTY")
    assert "no_cost_recorded" not in calidad["flags"], calidad


# ── KeyError en «Tus dos portafolios» con tickers `skipped` (2026-08-10) ────────
#
# `logic.classify_tickers` clasifica por IDENTIDAD del instrumento (SMH es mode_b pase lo
# que pase) y `logic.analyze_portfolio` por CALIDAD DE LOS DATOS (una posición <14 días
# queda `{"skipped": True, "reason": "held_less_than_14_days"}`, casi vacío).
# `ui/heredadas.py::_tus_dos_portafolios` armaba mode_a/mode_b con el primero y leía los
# números del segundo → `KeyError: 'pocket_investment'` (`?demo=schwab2` en producción,
# vía SLV/XLB/SMH). El fix va en la construcción de las listas, no en cada consumidor.

def _resultados_con_skipped(monkeypatch):
    """Portafolio con un ticker válido y uno `skipped` (<14 días) en cada modo:
    MSTY/TSLY en mode_a, SCHB/SMH en mode_b."""
    rows = [
        ("2024-01-01", "Buy", "MSTY", 100, -2000.0),
        ("2024-06-01", "Dividend", "MSTY", 0, 500.0),
        ("2025-01-01", "Buy", "TSLY", 100, -1000.0),
        ("2025-01-03", "Sell", "TSLY", 100, 1010.0),
        ("2024-01-01", "Buy", "SCHB", 50, -3000.0),
        ("2025-01-01", "Buy", "SMH", 100, -1000.0),
        ("2025-01-03", "Sell", "SMH", 100, 1010.0),
    ]
    df = _roc_norm_df(rows)
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    return logic.analyze_portfolio(df, version="TEST_SKIPPED_MIX")


def test_resultados_con_skipped_tiene_ambas_ramas(monkeypatch):
    """Confirma la fixture antes de usarla: 2 válidos + 2 `skipped` (uno por modo)."""
    results = _resultados_con_skipped(monkeypatch)
    assert results["TSLY"].get("skipped") is True
    assert results["TSLY"]["reason"] == "held_less_than_14_days"
    assert results["SMH"].get("skipped") is True
    assert results["SMH"]["reason"] == "held_less_than_14_days"
    assert "pocket_investment" in results["MSTY"]
    assert "pocket_investment" in results["SCHB"]


def test_tiene_datos_helper(monkeypatch):
    results = _resultados_con_skipped(monkeypatch)
    assert _tiene_datos(results["MSTY"]) is True
    assert _tiene_datos(results["SCHB"]) is True
    assert _tiene_datos(results["TSLY"]) is False        # skipped
    assert _tiene_datos(results["SMH"]) is False         # skipped
    assert _tiene_datos({"error": "No market data"}) is False
    assert _tiene_datos("not a dict") is False
    assert _tiene_datos(None) is False


def test_agregados_excluye_skipped_sin_crash(monkeypatch):
    """`_agregados` no debe reventar con un `skipped` en la lista, y el total debe
    corresponder solo al ticker con datos (no una suma parcial silenciosa con el otro)."""
    results = _resultados_con_skipped(monkeypatch)
    solo_valido = _agregados(results, ["MSTY"])
    con_skipped = _agregados(results, ["MSTY", "TSLY"])
    assert con_skipped == solo_valido


def test_agregados_schwab_resta_retencion_nra_en_retorno_total(monkeypatch):
    """Cuarta instancia de la Clase B (PR D, anotada durante el PR C): `_agregados`
    (`ui/heredadas.py`, alimenta las tarjetas de "Tus dos portafolios") sumaba
    `dividends_collected_cash` entre tickers — BRUTO en Schwab, NETO en IB — así que el
    "Retorno total" mostrado no restaba la retención NRA para Schwab. `fixtures/schwab_synth_2`
    completo (MSTY + SCHB): retención total $138.60 + $1.47 = $140.07. Como `inv` y `mv` no
    cambian con el fix, el retorno correcto (con `dividends_net_total`) debe ser exactamente
    $140.07 más negativo que el que arrojaba la suma bruta — ni más ni menos."""
    raw = open(os.path.join(os.path.dirname(__file__), "fixtures", "schwab_synth_2",
                             "synthetic_transactions.csv"), "rb").read()
    df, broker = logic.load_and_detect_csv(FakeFile(raw, "schwab_synth_2.csv"))
    dfc = logic.normalize_csv(df)
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    results = logic.analyze_portfolio(dfc, version="TEST_AGREGADOS_SCHWAB_NETO")

    tickers = ["MSTY", "SCHB"]
    inv, mv, div, tr, pct = _agregados(results, tickers)

    div_bruto_buggy = sum(results[t]["dividends_collected_cash"] for t in tickers)
    tr_buggy = mv + div_bruto_buggy - inv
    retencion_total = sum(
        results[t]["dividends_gross_total"] - results[t]["dividends_net_total"]
        for t in tickers)

    assert retencion_total == pytest.approx(140.07, abs=0.01)
    assert div == pytest.approx(326.83, abs=0.01)          # neto: 323.40 + 3.43
    assert div != pytest.approx(466.90, abs=0.01)           # el bruto que sumaba el bug
    assert round(tr_buggy - tr, 2) == pytest.approx(140.07, abs=0.01)


def test_agregados_ib_no_cambia_dividendos_ya_netos(monkeypatch):
    """No-regresión del fix anterior: en IB `dividends_collected_cash` YA es neto
    (`build_dividend_tax_totals` detecta la convención 'netted' y no deriva nada), así que
    `_agregados` sobre un portafolio IB debe dar el MISMO retorno que antes del fix — si
    cambia, el fix está restando la retención dos veces. `fixtures/ib_synth_1`."""
    raw = open(os.path.join(os.path.dirname(__file__), "fixtures", "ib_synth_1",
                             "synthetic_transactions.csv"), "rb").read()
    df, broker = logic.load_and_detect_csv(FakeFile(raw, "ib_synth_1.csv"))
    dfc = logic.normalize_csv(df)
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)
    results = logic.analyze_portfolio(dfc, version="TEST_AGREGADOS_IB_NETO")

    from ui.adapters import _tiene_datos
    tickers = [t for t in results if _tiene_datos(results.get(t))]
    assert tickers  # confirma la fixture antes de usarla

    inv, mv, div, tr, pct = _agregados(results, tickers)
    div_bruto_style = sum(results[t]["dividends_collected_cash"] for t in tickers)
    tr_bruto_style = mv + div_bruto_style - inv

    for t in tickers:
        assert results[t]["dividends_net_total"] == pytest.approx(
            results[t]["dividends_collected_cash"], abs=0.01)
    assert div == pytest.approx(div_bruto_style, abs=0.01)
    assert tr == pytest.approx(tr_bruto_style, abs=0.01)


def test_cuadricula_roc_div_pagados_neto_es_realmente_neto(monkeypatch):
    """Jubilado con la poda de Detalle (2026-08-25): `_cuadricula_roc_consolidada` se
    borró de `ui/heredadas.py` con las vistas Ingresos/Proyección/Estrategias. La
    columna "Div. pagados (neto)" ya no existe en UI; el invariante que este test
    vigilaba (que lo mostrado como neto es `dividends_net_total`, no la mezcla
    bruto/neto de `total_dividends`) vive ahora en el objeto fiscal único, verificado
    por test_analyze_portfolio_schwab_msty_dividend_base_convention y por la identidad
    neto = drip + efectivo de test_heredadas_base_mixta."""
    assert not hasattr(heredadas_mod := __import__("ui.heredadas", fromlist=["x"]),
                       "_cuadricula_roc_consolidada"), (
        "la vista podada no debe reintroducirse")


def test_detalle_portafolios_no_crashea_con_skipped(monkeypatch):
    """Regresión de raíz: las 4 vistas de Detalle vía `AppTest` (patrón de
    `test_carga_1042s.py`) con un `skipped` en mode_a (TSLY) y otro en mode_b (SMH). El
    criterio principal es `at.exception == []`; además, los tickers `skipped` deben
    quedar excluidos en vez de sumarse con ceros.

    Adaptado (sep-2026, Portafolios v3): las tarjetas A/B que este test leía en
    `at.markdown` («1 fondo: SCHB») fueron sustituidas por el componente
    `ui/componentes/portafolios.html`, que viaja en un iframe (`components.html`). El
    invariante es el mismo y ahora se verifica en el `srcdoc` del iframe — el JSON de
    `portafolios_data` debe traer solo los tickers con datos — y en el markdown de las
    secciones que siguen nativas."""
    results = _resultados_con_skipped(monkeypatch)

    script = """
import sys
sys.path.insert(0, {path!r})
from ui.heredadas import render_portafolios
from ui.vistas import obtener_resultados

resultados = obtener_resultados()
render_portafolios(resultados)
""".format(path=os.path.dirname(os.path.abspath(__file__)))

    at = AppTest.from_string(script)
    at.session_state["_vd_resultados"] = results
    at.run()
    assert at.exception == [], [e.value for e in at.exception]

    iframes = at.get("iframe")
    assert len(iframes) == 1, "el componente Portafolios v3 debe dibujarse en un iframe"
    srcdoc = iframes[0].proto.srcdoc
    assert '"SCHB"' in srcdoc, "el grupo de crecimiento debe incluir a SCHB"
    assert '"MSTY"' in srcdoc, "el grupo de dividendos debe incluir a MSTY"
    assert "SMH" not in srcdoc, "SMH está skipped: no debe llegar al componente"
    assert "TSLY" not in srcdoc, "TSLY está skipped: no debe llegar al componente"

    texto = "\n".join(m.value for m in at.markdown)
    assert "SMH" not in texto, "SMH está skipped: no debe aparecer en ninguna vista de Detalle"
    assert "TSLY" not in texto, "TSLY está skipped: no debe aparecer en ninguna vista de Detalle"


def test_separar_excluidos_tuyos_vs_ruido():
    """`_separar_excluidos` no debe mezclar posiciones reales del usuario (`skipped` por
    `held_less_than_14_days`) con acciones que nunca fueron un ETF (`not_known_etf`) — son
    los "603 excluidos" que enterraban a SLV/XLB/SMH en producción."""
    resultados = {
        "MSTY": {"pocket_investment": 100},  # analizado, no excluido
        "SMH": {"skipped": True, "reason": "held_less_than_14_days", "holding_days": 3},
        "XLB": {"skipped": True, "reason": "held_less_than_14_days", "holding_days": 9},
        "ACME": {"skipped": True, "reason": "not_known_etf"},
        "FOOBAR": {"skipped": True, "reason": "not_known_etf"},
    }
    tuyos, ruido = _separar_excluidos(resultados)
    assert set(tuyos) == {"SMH", "XLB"}
    assert set(ruido) == {"ACME", "FOOBAR"}
    assert "MSTY" not in tuyos and "MSTY" not in ruido


def test_separar_excluidos_vacio_sin_skipped():
    tuyos, ruido = _separar_excluidos({"MSTY": {"pocket_investment": 100}})
    assert tuyos == {} and ruido == {}


def test_pie_excluidos_titulo_no_entierra_las_posiciones_del_usuario(monkeypatch):
    """Con posiciones reales (SMH) Y ruido (un ticker no reconocido) presentes a la vez, el
    título del expander debe nombrar explícitamente las posiciones del usuario en vez de
    solo el conteo total — y ambas debe aparecer en el cuerpo."""
    results = _resultados_con_skipped(monkeypatch)
    results["ACME"] = {"skipped": True, "reason": "not_known_etf", "ticker": "ACME"}

    script = """
import sys
sys.path.insert(0, {path!r})
from ui.validacion import _render_excluidos
from ui.vistas import obtener_resultados

_render_excluidos(obtener_resultados())
""".format(path=os.path.dirname(os.path.abspath(__file__)))

    at = AppTest.from_string(script)
    at.session_state["_vd_resultados"] = results
    at.run()
    assert at.exception == [], [e.value for e in at.exception]

    assert len(at.expander) == 1
    titulo = at.expander[0].label
    assert titulo.startswith("2 posición(es) tuya(s) excluida(s)"), titulo
    assert "+ 1 ticker(s) no reconocido(s) como ETF" in titulo, titulo

    texto = "\n".join(m.value for m in at.markdown)
    assert "SMH" in texto and "TSLY" in texto and "ACME" in texto


# ── C·4/E4 · el efectivo líquido publicado por el motor, no reconstruido ────────────────

_REAL_EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "real_examples")


def _e4_casos_reales():
    """(res, ticker) de las posiciones reales de real_examples/, vía el mismo patrón que
    `o2c_e4_oraculo.py` (validate_real_cases.discover_cases + conftest.frozen_price_cache)."""
    import conftest
    from validate_real_cases import FakeFile, discover_cases

    out = []
    for case in discover_cases():
        d, m = case["dir"], case["manifest"]
        csvp = None
        import glob as _glob
        candidatos = _glob.glob(os.path.join(d, m.get("csv_glob", "*.csv")))
        inc = _glob.glob(os.path.join(d, m["income_glob"])) if m.get("income_glob") else []
        candidatos = [c for c in candidatos if os.path.basename(c) not in
                     {os.path.basename(i) for i in inc}]
        if not candidatos:
            continue
        csvp = candidatos[0]
        raw, _b = logic.load_and_detect_csv(FakeFile(open(csvp, "rb").read(),
                                                       os.path.basename(csvp)))
        df = logic.normalize_csv(raw)
        with conftest.frozen_price_cache():
            res = logic.analyze_portfolio(df.copy(), version="TEST_E4")
        for t, s in sorted(res.items()):
            if s.get("skipped"):
                continue
            out.append((res, t, s))
    return out


@pytest.mark.skipif(not os.path.isdir(_REAL_EXAMPLES_DIR), reason="sin real_examples/ (data privada)")
def test_e4_cashflow_igual_a_net_profit_en_los_casos_reales():
    """Las 24 posiciones reales: net_profit == cashflow RESULTADO (abs <= 0.02). Un verde de
    CI (con skip) no sustituye la corrida local — la corrida local la escribe O3 al auditar."""
    from ui.adapters import cashflow_data

    casos = _e4_casos_reales()
    assert casos, "no se encontraron posiciones reales analizables"
    for _res, t, s in casos:
        cf = cashflow_data(s, t)
        assert abs(s["net_profit"] - cf["RESULTADO"]) <= 0.02, (
            f"{t}: net_profit={s['net_profit']} != RESULTADO={cf['RESULTADO']}")


@pytest.mark.skipif(not os.path.isdir(_REAL_EXAMPLES_DIR), reason="sin real_examples/ (data privada)")
def test_e4_el_efectivo_publicado_nunca_es_negativo():
    """`dividends_cash_net >= -0.005` en las 24 posiciones reales."""
    casos = _e4_casos_reales()
    assert casos, "no se encontraron posiciones reales analizables"
    for _res, t, s in casos:
        assert s.get("dividends_cash_net") is not None, f"{t}: falta dividends_cash_net"
        assert s["dividends_cash_net"] >= -0.005, (
            f"{t}: dividends_cash_net={s['dividends_cash_net']} es negativo")


def test_e4_marca_calidad_cuando_faltan_filas_fuente_del_drip(monkeypatch):
    """Sintético: 2 `Reinvest Shares` y 1 `Reinvest Dividend` -> drip_sin_fuente True; con
    2 y 2, False."""
    monkeypatch.setattr(logic, "fetch_market_data", _MKT_MOCK)

    con_gap = logic.analyze_portfolio(_roc_norm_df([
        ("2024-09-01", "Buy", "MSTY", 50, -1000.0),
        ("2024-10-01", "Reinvest Dividend", "MSTY", 0, 100.0),
        ("2024-10-01", "Reinvest Shares", "MSTY", 1.0, -50.0),
        ("2024-11-01", "Reinvest Shares", "MSTY", 1.0, -50.0),   # sin su Reinvest Dividend
    ]))["MSTY"]
    assert con_gap["drip_sin_fuente"] is True

    sin_gap = logic.analyze_portfolio(_roc_norm_df([
        ("2024-09-01", "Buy", "MSTY", 50, -1000.0),
        ("2024-10-01", "Reinvest Dividend", "MSTY", 0, 100.0),
        ("2024-10-01", "Reinvest Shares", "MSTY", 1.0, -50.0),
        ("2024-11-01", "Reinvest Dividend", "MSTY", 0, 100.0),
        ("2024-11-01", "Reinvest Shares", "MSTY", 1.0, -50.0),
    ]))["MSTY"]
    assert sin_gap["drip_sin_fuente"] is False
def test_e1_el_texto_usa_el_mismo_retorno_que_la_tarjeta():
    """C·1/E1: `build_interpretation` publica el mismo `net_profit` que
    `_tarjeta_retorno_total` (regla 3b) — ya no usa el bruto (`mv + inc - pk`)."""
    stats = {"pocket_investment": 10000, "market_value": 6000,
             "dividends_collected_cash": 5000, "net_profit": 1234}
    # el bruto (mv + inc - pk) da 1000, deliberadamente distinto de net_profit (1234)
    # para que el test muerda si el texto sigue leyendo la fórmula vieja
    out = logic.build_interpretation({"MSTY": stats}, "MSTY")
    txt = " ".join(out["lines"])
    assert "$1,234" in txt, f"el texto no usa net_profit (1234): {txt!r}"
    assert "$1,000" not in txt, f"el texto todavía publica el bruto (1000): {txt!r}"


def test_e1_el_texto_usa_dividends_net_total_no_el_bruto():
    """C·1/E1: el «Income» del texto sale de `dividends_net_total` (neto), no de
    `dividends_collected_cash` (bruto en Schwab). Fixture con AMBOS presentes y
    distintos — si el texto lee el bruto, este test muerde (el anterior no podía:
    su fixture no traía `dividends_net_total`, así que el fallback daba el mismo
    valor con o sin el bug)."""
    stats = {"pocket_investment": 10000, "market_value": 6000,
             "dividends_net_total": 800, "dividends_collected_cash": 5000,
             "net_profit": 1234}
    out = logic.build_interpretation({"MSTY": stats}, "MSTY")
    txt = " ".join(out["lines"])
    assert "$800" in txt, f"el texto no usa dividends_net_total (800): {txt!r}"
    assert "$5,000" not in txt, f"el texto publica el bruto (5000) en vez del neto: {txt!r}"

# ── C·3/E3 + I5 — filas "as of" descartadas en silencio ────────────────────────

_ASOF_CSV = (
    b'"Transactions for account XXXX-1234","","","","","","",""\n'
    b'"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"\n'
    b'"01/13/2026 as of 12/31/2025","Pr Yr Div Reinvest","MSTY","YIELDMAX MSTY","2","20.00","","-40.00"\n'
    b'"06/02/2025","Cash Dividend","MSTY","YIELDMAX MSTY","","","","30.00"\n'
    b'"12/05/2025 as of 12/04/2025","Stock Split","XLK","TECH SELECT SPDR","11","","",""\n'
    b'"Transactions Total","","","","","","","$-10.00"\n'
)


def test_e3_cuenta_las_filas_as_of_descartadas():
    """`ultimo_descarte` cuenta las filas «as of» y las desglosa por acción — sintético
    con 3 filas «as of» (2 recuperables + 1 Stock Split que se sigue descartando)."""
    df, _ = logic.load_and_detect_csv(FakeFile(_ASOF_CSV))
    logic.normalize_csv(df)
    descarte = logic.normalize_csv.ultimo_descarte
    assert descarte["total"] == 2
    assert descarte["por_accion"] == {"Pr Yr Div Reinvest": 1, "Stock Split": 1}


def test_e3_manda_la_fecha_efectiva_no_la_de_registro():
    """«01/13/2026 as of 12/31/2025» (Pr Yr Div Reinvest) entra fechada el 2025-12-31,
    no el 2026-01-13 — el año fiscal cambia, que es el motivo de la decisión de Daniel."""
    df, _ = logic.load_and_detect_csv(FakeFile(_ASOF_CSV))
    df_clean = logic.normalize_csv(df)
    fila = df_clean[df_clean["Action"] == "Pr Yr Div Reinvest"]
    assert len(fila) == 1
    assert fila["Date"].iloc[0] == pd.Timestamp("2025-12-31")


def test_e3_los_stock_split_siguen_descartados():
    """Una fila `Stock Split ... as of ...` con `Quantity` no entra — ni su fecha se
    restaura ni `shares_owned` se mueve con ella."""
    df, _ = logic.load_and_detect_csv(FakeFile(_ASOF_CSV))
    df_clean = logic.normalize_csv(df)
    assert "XLK" not in set(df_clean["Ticker"]), (
        "el Stock Split «as of» debe seguir descartado (NaT), no restaurado")
    assert logic.normalize_csv.ultimo_descarte["por_accion"].get("Stock Split") == 1


def test_e3_paso1_no_mueve_ninguna_cifra():
    """A/B del commit 1: sobre un fixture sintético con filas «as of» (`_ASOF_CSV`), el
    número de filas limpias y sus valores no dependen de si el paso 2 (fecha efectiva)
    está o no — la única fila recuperable (Cash Dividend MSTY normal) no es «as of», y
    la única fila «as of» no-split queda con la misma cuenta total de descarte que
    antes de que existiera el paso 2 (ver test_e3_cuenta_las_filas_as_of_descartadas)."""
    df, _ = logic.load_and_detect_csv(FakeFile(_ASOF_CSV))
    df_clean = logic.normalize_csv(df)
    # la fila normal (no "as of") sigue intacta y es la única "MSTY" viva salvo la
    # recuperada — el conteo de descarte es el oráculo de "cuántas seguían siendo NaT
    # antes del paso 2": aquí 2 (coincide con lo medido arriba).
    assert logic.normalize_csv.ultimo_descarte["total"] == 2
    assert len(df_clean[df_clean["Action"] == "Cash Dividend"]) == 1


_I5_CSV = (
    b'"Transactions for account XXXX-1234","","","","","","",""\n'
    b'"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"\n'
    b'"03/01/2025","Buy","MSTY","YIELDMAX MSTY","100","20.00","","-2000.00"\n'
    b'"04/01/2025","Cash In Lieu","MSTY","YIELDMAX MSTY","","","","5.00"\n'
    b'"04/02/2025","Special Qual Div","MSTY","YIELDMAX MSTY","","","","2.52"\n'
    b'"04/03/2025","ADR Mgmt Fee","MSTY","YIELDMAX MSTY","","","","-0.06"\n'
    b'"04/04/2025","Wire Received","MSTY","YIELDMAX MSTY","","","","3.00"\n'
    b'"04/05/2025","Bond Interest","","","","","","5.89"\n'
    b'"Transactions Total","","","","","","","$-1988.65"\n'
)


def test_i5_cash_in_lieu_y_companeros_entran_por_su_rama():
    """Cash In Lieu, Special Qual Div, ADR Mgmt Fee y Wire Received quedan
    clasificados (suman a `dividends_collected_cash`) en vez de caer SIN RAMA —
    control: Bond Interest sigue entrando por `is_div_payout` ('interest'), sin
    cambiar de rama."""
    df, _ = logic.load_and_detect_csv(FakeFile(_I5_CSV))
    df_clean = logic.normalize_csv(df)
    import conftest
    with conftest.frozen_price_cache():
        res = logic.analyze_portfolio(df_clean.copy(), version="TEST_I5")
    s = res["MSTY"]
    # 5.00 + 2.52 - 0.06 + 3.00 = 10.46 de las 4 acciones I5; Bond Interest (5.89) es
    # `Ticker` vacío -> no ticker MSTY, así que no debe sumar aquí (control de rama).
    assert s["dividends_collected_cash"] == pytest.approx(10.46, abs=0.01), (
        f"dividends_collected_cash = {s['dividends_collected_cash']}, esperaba 10.46 "
        "(5.00 Cash In Lieu + 2.52 Special Qual Div - 0.06 ADR Mgmt Fee + 3.00 Wire Received)")
