#!/usr/bin/env python3
"""Generador de fixtures sintéticos — Dividend Analyzer.

Produce casos de prueba con la ESTRUCTURA exacta de los exports de Charles Schwab e
Interactive Brokers, pero con cifras inventadas. Sirven para que un ejecutor externo
desarrolle y valide la UI sin acceso a `real_examples/` (datos reales, privados, que
viven fuera del repo).

Los fixtures NO sustituyen la validación contra casos reales: esa la corre la auditoría
con `DIVIDEND_REAL_EXAMPLES_DIR` apuntando a la ruta privada.

Uso:
    python3 fixtures/generate_fixtures.py

Vocabulario replicado de los exports reales:
  Schwab  Action:           Buy · Sell · Cash Dividend · Qualified Dividend ·
                            Reinvest Shares · Reinvest Dividend · Qual Div Reinvest ·
                            NRA Tax Adj · Foreign Tax Paid · Cash In Lieu ·
                            Credit Interest · MoneyLink Transfer · Stock Split
  IBKR    Transaction Type: Buy · Sell · Dividend · Foreign Tax Withholding ·
                            Payment in Lieu · Deposit · Credit Interest
"""
import csv
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))

# Tickers elegidos para cubrir los tres modos de `logic.classify_tickers`:
#   mode_a  (YieldMax)      MSTY, TSLY, CONY
#   mode_b  (largo plazo)   SCHB, XLK
#   mode_skip (acción)      AAPL — debe quedar excluido del análisis
NRA_RATE = 0.30


# ── Charles Schwab ────────────────────────────────────────────────────────────

SCHWAB_HEADER = ["Date", "Action", "Symbol", "Description",
                 "Quantity", "Price", "Fees & Comm", "Amount"]

SCHWAB_ROWS = [
    # (fecha, acción, símbolo, descripción, cantidad, precio, fees, monto)
    ("01/15/2025", "Buy", "MSTY", "YIELDMAX MSTR OPTION INCOME ETF", "40", "$25.00", "", "-$1000.00"),
    ("01/15/2025", "Buy", "SCHB", "SCHWAB US BROAD MARKET ETF", "10", "$20.00", "", "-$200.00"),
    ("02/03/2025", "Buy", "TSLY", "YIELDMAX TSLA OPTION INCOME ETF", "50", "$12.00", "", "-$600.00"),
    ("02/10/2025", "Buy", "AAPL", "APPLE INC", "5", "$180.00", "", "-$900.00"),

    # Dividendo bruto → retención NRA → reinversión parcial
    ("02/28/2025", "Cash Dividend", "MSTY", "YIELDMAX MSTR OPTION INCOME ETF", "", "", "", "$80.00"),
    ("02/28/2025", "NRA Tax Adj", "MSTY", "YIELDMAX MSTR OPTION INCOME ETF", "", "", "", "-$24.00"),
    ("03/01/2025", "Reinvest Dividend", "MSTY", "YIELDMAX MSTR OPTION INCOME ETF", "", "", "", "-$40.00"),
    ("03/01/2025", "Reinvest Shares", "MSTY", "YIELDMAX MSTR OPTION INCOME ETF", "1.8182", "$22.00", "", ""),

    ("03/31/2025", "Cash Dividend", "MSTY", "YIELDMAX MSTR OPTION INCOME ETF", "", "", "", "$76.00"),
    ("03/31/2025", "NRA Tax Adj", "MSTY", "YIELDMAX MSTR OPTION INCOME ETF", "", "", "", "-$22.80"),

    ("03/31/2025", "Cash Dividend", "TSLY", "YIELDMAX TSLA OPTION INCOME ETF", "", "", "", "$45.00"),
    ("03/31/2025", "NRA Tax Adj", "TSLY", "YIELDMAX TSLA OPTION INCOME ETF", "", "", "", "-$13.50"),

    ("03/31/2025", "Qualified Dividend", "SCHB", "SCHWAB US BROAD MARKET ETF", "", "", "", "$1.50"),
    ("03/31/2025", "NRA Tax Adj", "SCHB", "SCHWAB US BROAD MARKET ETF", "", "", "", "-$0.45"),

    ("04/15/2025", "Qual Div Reinvest", "SCHB", "SCHWAB US BROAD MARKET ETF", "", "", "", "-$1.05"),
    ("04/15/2025", "Reinvest Shares", "SCHB", "SCHWAB US BROAD MARKET ETF", "0.0500", "$21.00", "", ""),

    # Ruido que el parser debe ignorar sin romperse
    ("04/20/2025", "Credit Interest", "", "SCHWAB BANK INTEREST", "", "", "", "$0.12"),
    ("04/22/2025", "MoneyLink Transfer", "", "TRANSFER FROM BANK", "", "", "", "$500.00"),
    ("05/02/2025", "Cash In Lieu", "TSLY", "YIELDMAX TSLA OPTION INCOME ETF", "", "", "", "$0.37"),
    ("05/10/2025", "Sell", "AAPL", "APPLE INC", "2", "$195.00", "$0.02", "$389.98"),
    ("06/01/2025", "Foreign Tax Paid", "SCHB", "SCHWAB US BROAD MARKET ETF", "", "", "", "-$0.08"),
]

SCHWAB_INCOME_PREAMBLE = '"Investment Income Transactions as of 06/30/2025 09:00:00 ET"'
SCHWAB_INCOME_HEADER = ["Transaction Date", "Account Number", "Account Name", "Account Type",
                        "Security Description", "Symbol", "Security Type",
                        "Transaction Type", "Transaction Amount", "Income Type", ""]

SCHWAB_INCOME_ROWS = [
    ("02/28/2025", "...111", "Individual", "BROKERAGE", "YieldMax MSTR Option Income ETF",
     "MSTY", "ETFs & Closed End Funds", "Dividend", "80.0000000000", "Reported", ""),
    ("03/31/2025", "...111", "Individual", "BROKERAGE", "YieldMax MSTR Option Income ETF",
     "MSTY", "ETFs & Closed End Funds", "Dividend", "76.0000000000", "Reported", ""),
    ("03/31/2025", "...111", "Individual", "BROKERAGE", "YieldMax TSLA Option Income ETF",
     "TSLY", "ETFs & Closed End Funds", "Dividend", "45.0000000000", "Reported", ""),
    ("03/31/2025", "...111", "Individual", "BROKERAGE", "Schwab US Broad Market ETF",
     "SCHB", "ETFs & Closed End Funds", "Dividend", "1.5000000000", "Reported", ""),
]


def write_schwab(outdir):
    os.makedirs(outdir, exist_ok=True)

    path = os.path.join(outdir, "synthetic_transactions.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(SCHWAB_HEADER)
        for row in SCHWAB_ROWS:
            w.writerow(row)

    path_inc = os.path.join(outdir, "synthetic_investment_income.csv")
    with open(path_inc, "w", newline="", encoding="utf-8") as f:
        f.write(SCHWAB_INCOME_PREAMBLE + "\n")
        w = csv.writer(f)
        w.writerow(SCHWAB_INCOME_HEADER)
        for row in SCHWAB_INCOME_ROWS:
            w.writerow(row)

    return path, path_inc


# ── Interactive Brokers ───────────────────────────────────────────────────────

IB_TXN_HEADER = ["Transaction History", "Header", "Date", "Account", "Description",
                 "Transaction Type", "Symbol", "Quantity", "Price", "Price Currency",
                 "Gross Amount ", "Commission", "Net Amount"]

IB_PREAMBLE = [
    ["Statement", "Header", "Nombre del campo", "Valor del campo"],
    ["Statement", "Data", "Title", "Transaction History"],
    ["Statement", "Data", "Period", "Enero 2, 2025 - Junio 30, 2025"],
    ["Statement", "Data", "WhenGenerated", "2025-06-30, 12:00:00 EDT"],
    ["Summary", "Header", "Nombre del campo", "Valor del campo"],
    ["Summary", "Data", "Divisa base", "USD"],
    ["Summary", "Data", "Efectivo inicial", "0.0"],
]

# (fecha, descripción, tipo, símbolo, cantidad, precio, bruto, comisión, neto)
IB_ROWS = [
    ("2025-01-20", "YIELDMAX NVDA OPTION INC ETF", "Buy", "NVDY", "60", "15.00", "-900.00", "-1.00", "-901.00"),
    ("2025-01-20", "VANECK SEMICONDUCTOR ETF", "Buy", "SMH", "4", "250.00", "-1000.00", "-1.00", "-1001.00"),
    ("2025-02-05", "YIELDMAX COIN OPTION IS ETF", "Buy", "CONY", "80", "10.00", "-800.00", "-1.00", "-801.00"),

    ("2025-02-28", "NVDY(US88634T7827) Dividendo en efectivo USD 1.00 por accion (Dividendo ordinario)",
     "Dividend", "NVDY", "", "", "60.00", "", "60.00"),
    ("2025-02-28", "NVDY(US88634T7827) Dividendo en efectivo USD 1.00 por accion - US Impuestos",
     "Foreign Tax Withholding", "NVDY", "", "", "-18.00", "", "-18.00"),

    ("2025-03-31", "CONY(US88634T8801) Dividendo en efectivo USD 0.75 por accion (Dividendo ordinario)",
     "Dividend", "CONY", "", "", "60.00", "", "60.00"),
    ("2025-03-31", "CONY(US88634T8801) Dividendo en efectivo USD 0.75 por accion - US Impuestos",
     "Foreign Tax Withholding", "CONY", "", "", "-18.00", "", "-18.00"),

    ("2025-04-30", "SMH(US92189F6768) Dividendo en efectivo USD 0.50 por accion (Dividendo ordinario)",
     "Dividend", "SMH", "", "", "2.00", "", "2.00"),
    ("2025-04-30", "SMH(US92189F6768) Dividendo en efectivo USD 0.50 por accion - US Impuestos",
     "Foreign Tax Withholding", "SMH", "", "", "-0.60", "", "-0.60"),

    # Ruido que el parser debe tolerar
    ("2025-05-01", "Transferencia de Fondos Electronica", "Deposit", "-", "", "", "1000.00", "", "1000.00"),
    ("2025-05-15", "Interes de credito USD", "Credit Interest", "-", "", "", "0.45", "", "0.45"),
    ("2025-06-02", "NVDY(US88634T7827) Pago en Lugar de Dividendo (in Lieu)",
     "Payment in Lieu", "NVDY", "", "", "1.20", "", "1.20"),
    ("2025-06-10", "YIELDMAX NVDA OPTION INC ETF", "Sell", "NVDY", "-10", "13.00", "130.00", "-1.00", "129.00"),
]


def write_ibkr(outdir):
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "synthetic_transactions.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for row in IB_PREAMBLE:
            w.writerow(row)
        w.writerow(IB_TXN_HEADER)
        for (date, desc, ttype, sym, qty, price, gross, comm, net) in IB_ROWS:
            w.writerow(["Transaction History", "Data", date, "U0000000", desc, ttype,
                        sym, qty, price, "USD", gross, comm, net])
    return path


# ── Ground truth ──────────────────────────────────────────────────────────────
#
# Los valores se derivan de las filas de arriba con aritmética simple y explícita.
# `market_value` queda en null a propósito: depende del precio de mercado del día
# (yfinance), así que no puede ser ground truth fijo en un fixture.
#
# ATENCIÓN — dos cifras distintas que es fácil confundir (verificado contra el código):
#
#   `tickers[].shares` / `cost_basis`  = la POSICIÓN REAL. Cuenta compras + reinversiones
#       y resta ventas. Es lo que el usuario confirma en el Bloque 2 del wizard y lo que
#       consume `analyze_portfolio`.
#
#   `csv_preview_expected`             = lo que produce la agregación rápida de
#       `app.py:1400-1412` (`_csv_ticker_data`) al cargar el archivo en el Bloque 1.
#       Esa agregación filtra por `Action.str.contains('buy')`, así que NO suma las
#       filas `Reinvest Shares` y NO resta las ventas. Es una vista previa, no la
#       posición. Una UI que muestre este número como "tus acciones" está mintiendo.

SCHWAB_EXPECTED = {
    "case_id": "schwab_synth_1",
    "broker": "schwab",
    "csv_glob": "schwab_synth_1/synthetic_transactions.csv",
    "income_glob": "schwab_synth_1/synthetic_investment_income.csv",
    "source": "SINTETICO — cifras inventadas, estructura real del export de Charles Schwab.",
    "notes": ("No es un caso real. Sirve para desarrollo y validacion de UI sin acceso a "
              "real_examples/. La validacion contra datos reales corre aparte, con "
              "DIVIDEND_REAL_EXAMPLES_DIR."),
    "tickers": {
        "MSTY": {
            "shares": 41.8182,
            "cost_basis": 1040.00,
            "market_value": None,
            "reliability": "high",
            "note": "40 compradas @ $25.00 + 1.8182 reinvertidas @ $22.00.",
        },
        "TSLY": {
            "shares": 50.0,
            "cost_basis": 600.00,
            "market_value": None,
            "reliability": "high",
            "note": "50 compradas @ $12.00, sin reinversion.",
        },
        "SCHB": {
            "shares": 10.05,
            "cost_basis": 201.05,
            "market_value": None,
            "reliability": "high",
            "note": "10 compradas @ $20.00 + 0.05 reinvertidas @ $21.00.",
        },
    },
    "csv_preview_expected": {
        "source": "app.py:1400-1412 (_csv_ticker_data) — filtro Action.contains('buy')",
        "shares": {"MSTY": 40.0, "TSLY": 50.0, "SCHB": 10.0, "AAPL": 5.0},
        "invested": {"MSTY": 1000.00, "TSLY": 600.00, "SCHB": 200.00, "AAPL": 900.00},
        "note": ("Vista previa del Bloque 1, NO la posicion. Ignora 'Reinvest Shares' "
                 "(MSTY +1.8182, SCHB +0.05) y no resta la venta de AAPL (-2). "
                 "Verificado contra el codigo, no estimado."),
    },
    "income_expected": {
        "source": "synthetic_investment_income.csv",
        "cusip_folds": {},
        "received": {"MSTY": 156.00, "TSLY": 45.00, "SCHB": 1.50},
        "expected_status": {"MSTY": "match", "TSLY": "match", "SCHB": "match"},
        "note": "Dividendos BRUTOS. La retencion NRA va aparte, en las filas 'NRA Tax Adj'.",
    },
    "tax_expected": {
        "basis": "gross_withheld",
        "moment": "al cobro",
        "withheld_real": {"MSTY": 46.80, "TSLY": 13.50, "SCHB": 0.45},
        "note": ("Retencion al cobro, tasa plana del 30%. NO confundir con "
                 "`refund_estimated` de build_tax_summary, que es una estimacion "
                 "post-reclasificacion anual (momento distinto — Regla 2)."),
    },
    "excluded_tickers": {
        "AAPL": "mode_skip — accion individual, fuera del analisis.",
    },
}

IB_EXPECTED = {
    "case_id": "ib_synth_1",
    "broker": "ibkr",
    "csv_glob": "ib_synth_1/synthetic_transactions.csv",
    "income_glob": None,
    "source": "SINTETICO — cifras inventadas, estructura real del export de Interactive Brokers.",
    "notes": ("No es un caso real. El export de IB trae la retencion como filas "
              "'Foreign Tax Withholding' separadas de las filas 'Dividend'."),
    "tickers": {
        "NVDY": {
            "shares": 50.0,
            "cost_basis": 750.00,
            "market_value": None,
            "reliability": "high",
            "note": "60 compradas @ $15.00, 10 vendidas. Costo base proporcional a las 50 vivas.",
        },
        "CONY": {
            "shares": 80.0,
            "cost_basis": 800.00,
            "market_value": None,
            "reliability": "high",
            "note": "80 compradas @ $10.00.",
        },
        "SMH": {
            "shares": 4.0,
            "cost_basis": 1000.00,
            "market_value": None,
            "reliability": "high",
            "note": "4 compradas @ $250.00.",
        },
    },
    "csv_preview_expected": {
        "source": "app.py:1400-1412 (_csv_ticker_data) — filtro Action.contains('buy')",
        "shares": {"NVDY": 60.0, "CONY": 80.0, "SMH": 4.0},
        "invested": {"NVDY": 900.00, "CONY": 800.00, "SMH": 1000.00},
        "note": ("Vista previa del Bloque 1, NO la posicion: no resta la venta de 10 NVDY. "
                 "Verificado contra el codigo, no estimado."),
    },
    "income_expected": {
        "source": "filas Dividend del propio archivo de transacciones",
        "cusip_folds": {},
        "received": {"NVDY": 60.00, "CONY": 60.00, "SMH": 2.00},
        "expected_status": {"NVDY": "match", "CONY": "match", "SMH": "match"},
        "note": "Dividendos BRUTOS, sin el 'Payment in Lieu' de $1.20 de NVDY.",
    },
    "tax_expected": {
        "basis": "gross_withheld",
        "moment": "al cobro",
        "withheld_real": {"NVDY": 18.00, "CONY": 18.00, "SMH": 0.60},
        "note": "Filas 'Foreign Tax Withholding'. Tasa plana del 30% sobre el bruto.",
    },
    "excluded_tickers": {},
}


def main():
    schwab_dir = os.path.join(BASE, "schwab_synth_1")
    ib_dir = os.path.join(BASE, "ib_synth_1")

    txn, inc = write_schwab(schwab_dir)
    with open(os.path.join(schwab_dir, "expected.json"), "w", encoding="utf-8") as f:
        json.dump(SCHWAB_EXPECTED, f, indent=2, ensure_ascii=False)

    ib_txn = write_ibkr(ib_dir)
    with open(os.path.join(ib_dir, "expected.json"), "w", encoding="utf-8") as f:
        json.dump(IB_EXPECTED, f, indent=2, ensure_ascii=False)

    for p in (txn, inc, ib_txn):
        print("escrito:", os.path.relpath(p, BASE))
    print("escrito: schwab_synth_1/expected.json")
    print("escrito: ib_synth_1/expected.json")


if __name__ == "__main__":
    main()
