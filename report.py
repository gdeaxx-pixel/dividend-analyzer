from fpdf import FPDF
from datetime import date


BROKER_LABELS = {
    "schwab": "Charles Schwab",
    "ibkr": "Interactive Brokers",
    "generic": "Formato Genérico",
}

_BLUE  = (0,   68, 151)
_RED   = (200, 16,  46)
_DARK  = (2,   28,  54)
_LIGHT = (245, 245, 245)
_WHITE = (255, 255, 255)


def _fmt_usd(v: float) -> str:
    return f"${v:,.2f}"


def _fmt_pct(v: float) -> str:
    return f"{v:.2f}%"


class _PDF(FPDF):
    def __init__(self, broker: str, version: str):
        super().__init__()
        self._broker = BROKER_LABELS.get(broker, broker.upper())
        self._version = version
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(15, 15, 15)

    def header(self):
        self.set_fill_color(*_DARK)
        self.rect(0, 0, 210, 18, "F")
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*_WHITE)
        self.set_xy(0, 4)
        self.cell(0, 10, "DIVIDEND  //  ANALYZER", align="C")
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 5,
                  "Este documento es informativo y no constituye asesoría financiera.  "
                  f"Generado el {date.today().isoformat()}  |  Pág. {self.page_no()}",
                  align="C")
        self.set_text_color(0, 0, 0)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _section_title(self, text: str):
        self.ln(4)
        self.set_fill_color(*_DARK)
        self.set_text_color(*_WHITE)
        self.set_font("Helvetica", "B", 9)
        self.cell(0, 7, f"  {text}", fill=True, ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def _row(self, label: str, value: str, shade: bool = False):
        if shade:
            self.set_fill_color(*_LIGHT)
        else:
            self.set_fill_color(*_WHITE)
        self.set_font("Helvetica", "", 8)
        self.cell(90, 6, f"  {label}", fill=True)
        self.set_font("Helvetica", "B", 8)
        self.cell(0, 6, value, fill=True, ln=True)

    def _two_col_row(self, l1: str, v1: str, l2: str, v2: str, shade: bool = False):
        fill = _LIGHT if shade else _WHITE
        self.set_fill_color(*fill)
        self.set_font("Helvetica", "", 8)
        self.cell(45, 6, f"  {l1}", fill=True)
        self.set_font("Helvetica", "B", 8)
        self.cell(50, 6, v1, fill=True)
        self.set_font("Helvetica", "", 8)
        self.cell(45, 6, f"  {l2}", fill=True)
        self.set_font("Helvetica", "B", 8)
        self.cell(0, 6, v2, fill=True, ln=True)

    def _metric_strip(self, items: list[tuple[str, str]]):
        """Row of N equally-spaced metrics."""
        n = len(items)
        w = 180 / n
        self.set_fill_color(*_LIGHT)
        for label, value in items:
            x = self.get_x()
            y = self.get_y()
            self.set_font("Helvetica", "", 7)
            self.set_fill_color(*_LIGHT)
            self.cell(w, 5, f"  {label}", fill=True)
            self.set_xy(x, y + 5)
            self.set_font("Helvetica", "B", 9)
            self.cell(w, 6, f"  {value}", fill=True)
            self.set_xy(x + w, y)
        self.ln(12)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_report_pdf(results: dict, broker: str, version: str = "2.0") -> bytes:
    valid = {
        t: s for t, s in results.items()
        if not s.get("skipped") and not s.get("error")
    }

    total_inv  = sum(s.get("pocket_investment", 0)        for s in valid.values())
    total_mv   = sum(s.get("market_value", 0)             for s in valid.values())
    total_div  = sum(s.get("dividends_collected_cash", 0) for s in valid.values())
    total_gain = (total_mv + total_div) - total_inv
    total_roi  = (total_gain / total_inv * 100) if total_inv else 0

    mode_a = sorted(t for t, s in valid.items() if s.get("ticker_mode") == "mode_a")
    mode_b = sorted(t for t, s in valid.items() if s.get("ticker_mode") == "mode_b")

    pdf = _PDF(broker, version)

    # ── Cover / summary page ────────────────────────────────────────────────
    pdf.add_page()

    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Reporte de Auditoría de Portafolio", align="C", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6,
             f"Broker: {BROKER_LABELS.get(broker, broker.upper())}   |   "
             f"Fecha: {date.today().isoformat()}   |   "
             f"Versión: {version}   |   "
             f"Posiciones: {len(valid)}",
             align="C", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(6)

    pdf._section_title("RESUMEN GLOBAL DEL PORTAFOLIO")
    pdf._row("Total Invertido",       _fmt_usd(total_inv),  shade=False)
    pdf._row("Valor de Mercado",      _fmt_usd(total_mv),   shade=True)
    pdf._row("Ganancia / Pérdida $",  _fmt_usd(total_gain), shade=False)
    pdf._row("ROI Global",            _fmt_pct(total_roi),  shade=True)
    pdf._row("Dividendos Totales",    _fmt_usd(total_div),  shade=False)
    pdf.ln(4)

    if mode_a:
        pdf._section_title("MODO A - YieldMax / Income ETFs")
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(0, 5, "  " + "   ".join(mode_a), ln=True)
        pdf.ln(2)

    if mode_b:
        pdf._section_title("MODO B - ETFs de Crecimiento")
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(0, 5, "  " + "   ".join(mode_b), ln=True)
        pdf.ln(2)

    # ── Per-ticker pages ─────────────────────────────────────────────────────
    for ticker in mode_a + mode_b:
        s = valid[ticker]
        mode_label = "YieldMax" if s.get("ticker_mode") == "mode_a" else "ETF Crecimiento"

        pdf.add_page()

        # Ticker header bar
        color = _RED if s.get("ticker_mode") == "mode_a" else _BLUE
        pdf.set_fill_color(*color)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, f"  {ticker}   -   {mode_label}", fill=True, ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

        # Investment metrics
        pdf._section_title("MÉTRICAS DE INVERSIÓN")
        shade = False
        rows_inv = [
            ("Inversión (dinero propio)",          _fmt_usd(s.get("pocket_investment", 0))),
            ("Valor de Mercado",                    _fmt_usd(s.get("market_value", 0))),
            ("Ganancia / Pérdida $",               _fmt_usd(s.get("net_profit", 0))),
            ("ROI %",                               _fmt_pct(s.get("roi_percent", 0))),
            ("CAGR",                                _fmt_pct(s.get("cagr", 0))),
            ("Dividendos Efectivo",                 _fmt_usd(s.get("dividends_collected_cash", 0))),
            ("Dividendos DRIP",                     _fmt_usd(s.get("dividends_collected_drip", 0))),
            ("Total Dividendos",                    _fmt_usd(s.get("total_dividends", 0))),
            ("Yield on Cost",                       _fmt_pct(s.get("yield_on_cost", 0))),
        ]
        for label, value in rows_inv:
            pdf._row(label, value, shade=shade)
            shade = not shade

        # Shares
        pdf._section_title("POSICIÓN EN ACCIONES")
        pdf._row("Acciones Compradas",  f"{s.get('shares_bought', 0):,.4f}",  shade=False)
        pdf._row("Acciones Vendidas",   f"{s.get('shares_sold', 0):,.4f}",    shade=True)
        pdf._row("Acciones Netas",      f"{s.get('shares_owned', 0):,.4f}",   shade=False)
        pdf._row("Precio Actual",       _fmt_usd(s.get("current_price", 0)),  shade=True)

        # Risk metrics — show N/A when value is None (insufficient data)
        def _risk_fmt(key: str, pct: bool = False) -> str:
            v = s.get(key)
            if v is None:
                return "N/A"
            return _fmt_pct(float(v)) if pct else f"{float(v):.2f}"

        pdf._section_title("MÉTRICAS DE RIESGO AJUSTADO")
        pdf._two_col_row(
            "Sharpe Ratio",    _risk_fmt("sharpe_ratio"),
            "Sortino Ratio",   _risk_fmt("sortino_ratio"),
            shade=False,
        )
        pdf._two_col_row(
            "Max Drawdown",    _risk_fmt("max_drawdown", pct=True),
            "Volatilidad Anual", _risk_fmt("volatilidad_anualizada", pct=True),
            shade=True,
        )
        pdf._two_col_row(
            "Beta vs VOO",     _risk_fmt("beta_vs_voo"),
            "Alpha Anualizado", _risk_fmt("alpha_anualizado", pct=True),
            shade=False,
        )

        # Monthly income (last 12 months)
        monthly = s.get("monthly_income")
        if monthly is not None and len(monthly) > 0:
            pdf._section_title("INGRESOS MENSUALES (últimos 12 meses)")
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_fill_color(*_DARK)
            pdf.set_text_color(*_WHITE)
            pdf.cell(30, 5, "  Mes", fill=True)
            pdf.cell(40, 5, "Dividendo", fill=True)
            pdf.ln()
            pdf.set_text_color(0, 0, 0)

            import pandas as _pd
            try:
                series = _pd.Series(monthly).sort_index().tail(12)
            except Exception:
                series = monthly.tail(12) if hasattr(monthly, "tail") else monthly

            shade = False
            for period, amount in series.items():
                try:
                    label = str(period)[:7]
                except Exception:
                    label = str(period)
                fill = _LIGHT if shade else _WHITE
                pdf.set_fill_color(*fill)
                pdf.set_font("Helvetica", "", 7)
                pdf.cell(30, 5, f"  {label}", fill=True)
                pdf.set_font("Helvetica", "B", 7)
                pdf.cell(40, 5, _fmt_usd(float(amount)), fill=True)
                pdf.ln()
                shade = not shade

    return bytes(pdf.output())
