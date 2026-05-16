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
_GREEN = (44, 160, 100)
_LIGHT = (245, 245, 245)
_WHITE = (255, 255, 255)
_GRAY  = (150, 150, 150)


def _fmt_usd(v) -> str:
    try:
        return f"${float(v):+,.2f}" if float(v) < 0 else f"${float(v):,.2f}"
    except Exception:
        return "N/A"


def _fmt_usd_plain(v) -> str:
    try:
        return f"${float(v):,.2f}"
    except Exception:
        return "N/A"


def _fmt_pct(v, signed: bool = False) -> str:
    try:
        return f"{float(v):+.2f}%" if signed else f"{float(v):.2f}%"
    except Exception:
        return "N/A"


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
        self.set_text_color(*_GRAY)
        self.cell(0, 5,
                  "Este documento es informativo y no constituye asesoría financiera.  "
                  f"Generado el {date.today().isoformat()}  |  Pág. {self.page_no()}",
                  align="C")
        self.set_text_color(0, 0, 0)

    def _section_title(self, text: str):
        self.ln(4)
        self.set_fill_color(*_DARK)
        self.set_text_color(*_WHITE)
        self.set_font("Helvetica", "B", 9)
        self.cell(0, 7, f"  {text}", fill=True, ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def _row(self, label: str, value: str, shade: bool = False, value_color=None):
        if shade:
            self.set_fill_color(*_LIGHT)
        else:
            self.set_fill_color(*_WHITE)
        self.set_font("Helvetica", "", 8)
        self.cell(90, 6, f"  {label}", fill=True)
        self.set_font("Helvetica", "B", 8)
        if value_color:
            self.set_text_color(*value_color)
        self.cell(0, 6, value, fill=True, ln=True)
        if value_color:
            self.set_text_color(0, 0, 0)

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

    def _total_return_box(self, total_ret: float, total_ret_pct: float,
                          capital: float, income: float):
        """Bloque oscuro con Retorno Total destacado — Fase 9."""
        self.ln(3)
        self.set_fill_color(*_DARK)
        x0 = self.get_x()
        y0 = self.get_y()
        self.rect(x0, y0, 180, 20, "F")
        # Etiqueta
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_GRAY)
        self.set_xy(x0 + 3, y0 + 2)
        self.cell(80, 4, "RETORNO TOTAL (Capital + Income)", ln=False)
        # Número grande
        color = _GREEN if total_ret >= 0 else (220, 80, 80)
        self.set_text_color(*color)
        self.set_font("Helvetica", "B", 14)
        self.set_xy(x0 + 3, y0 + 7)
        self.cell(100, 7, f"{_fmt_usd(total_ret)}  ({_fmt_pct(total_ret_pct, signed=True)})", ln=False)
        # Desglose Capital / Income
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_GRAY)
        self.set_xy(x0 + 3, y0 + 15)
        cap_color = "+" if capital >= 0 else ""
        self.cell(180, 4,
                  f"Capital: {cap_color}{_fmt_usd(capital)}     Income: {_fmt_usd_plain(income)}",
                  ln=False)
        self.set_text_color(0, 0, 0)
        self.set_xy(x0, y0 + 22)
        self.ln(2)


def generate_report_pdf(results: dict, broker: str, version: str = "2.0") -> bytes:
    valid = {
        t: s for t, s in results.items()
        if not s.get("skipped") and not s.get("error")
    }

    total_inv  = sum(s.get("pocket_investment", 0)        for s in valid.values())
    total_mv   = sum(s.get("market_value", 0)             for s in valid.values())
    total_div  = sum(s.get("dividends_collected_cash", 0) for s in valid.values())
    total_ret  = (total_mv + total_div) - total_inv
    total_roi  = (total_ret / total_inv * 100) if total_inv else 0

    mode_a = sorted(t for t, s in valid.items() if s.get("ticker_mode") == "mode_a")
    mode_b = sorted(t for t, s in valid.items() if s.get("ticker_mode") == "mode_b")

    pdf = _PDF(broker, version)

    # ── Portada / Resumen Global ─────────────────────────────────────────────
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
    pdf.ln(4)

    # Bloque de retorno total global
    pdf._total_return_box(
        total_ret=total_ret,
        total_ret_pct=total_roi,
        capital=total_mv - total_inv,
        income=total_div,
    )

    pdf._section_title("RESUMEN GLOBAL DEL PORTAFOLIO")
    pdf._row("Total Invertido",                     _fmt_usd_plain(total_inv), shade=False)
    pdf._row("Valor de Mercado",                    _fmt_usd_plain(total_mv),  shade=True)
    pdf._row("Dividendos Cobrados (neto impuestos)", _fmt_usd_plain(total_div), shade=False)
    ret_color = _GREEN if total_ret >= 0 else (200, 50, 50)
    pdf._row("Retorno Total (incl. dividendos)",    _fmt_usd(total_ret),       shade=True,  value_color=ret_color)
    pdf._row("ROI Global (incl. dividendos)",       _fmt_pct(total_roi, signed=True), shade=False, value_color=ret_color)
    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(*_GRAY)
    pdf.multi_cell(0, 4,
        "Nota: 'Inversión' refleja el capital real desplegado (precios pagados en el CSV del broker). "
        "Puede diferir del 'Base de Coste' de IB porque IB reduce el costo base por distribuciones "
        "clasificadas como Return of Capital (ROC) — una distinción fiscal, no una diferencia económica.")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    if mode_a:
        pdf._section_title("MODO A — YieldMax / Income ETFs")
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(0, 5, "  " + "   ".join(mode_a), ln=True)
        pdf.ln(2)

    if mode_b:
        pdf._section_title("MODO B — ETFs de Crecimiento")
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(0, 5, "  " + "   ".join(mode_b), ln=True)
        pdf.ln(2)

    # ── Páginas por ticker ───────────────────────────────────────────────────
    def _risk_fmt(key: str, pct: bool = False) -> str:
        v = s.get(key)
        if v is None:
            return "N/A"
        return _fmt_pct(float(v), signed=pct) if pct else f"{float(v):.2f}"

    for ticker in mode_a + mode_b:
        s = valid[ticker]
        mode_label = "YieldMax" if s.get("ticker_mode") == "mode_a" else "ETF Crecimiento"

        pdf.add_page()
        pdf.set_x(pdf.l_margin)

        color = _RED if s.get("ticker_mode") == "mode_a" else _BLUE
        pdf.set_fill_color(*color)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, f"  {ticker}   -   {mode_label}", fill=True, ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(1)

        # Bloque Retorno Total por ticker
        inv  = s.get("pocket_investment", 0)
        mv   = s.get("market_value", 0)
        divs = s.get("dividends_collected_cash", 0)
        t_ret     = mv + divs - inv
        t_ret_pct = (t_ret / inv * 100) if inv else 0
        pdf._total_return_box(
            total_ret=t_ret,
            total_ret_pct=t_ret_pct,
            capital=mv - inv,
            income=divs,
        )

        # Métricas de inversión
        pdf._section_title("MÉTRICAS DE INVERSIÓN")
        irr_val  = s.get("irr_anual")
        irr_str  = _fmt_pct(irr_val, signed=True) if irr_val is not None else "N/A"
        cagr_val = s.get("cagr")
        cagr_str = _fmt_pct(cagr_val) if cagr_val is not None else "N/A"

        rows_inv = [
            ("Inversión (capital real desplegado)",  _fmt_usd_plain(inv)),
            ("Valor de Mercado",                      _fmt_usd_plain(mv)),
            ("Dividendos Efectivo (neto impuestos)",  _fmt_usd_plain(divs)),
            ("Dividendos DRIP",                       _fmt_usd_plain(s.get("dividends_collected_drip", 0))),
            ("Total Dividendos",                      _fmt_usd_plain(s.get("total_dividends", 0))),
            ("Retorno Total $",                       _fmt_usd(t_ret)),
            ("Retorno Total %",                       _fmt_pct(t_ret_pct, signed=True)),
            ("IRR Anualizado",                        irr_str),
            ("CAGR",                                  cagr_str),
            ("Yield on Cost",                         _fmt_pct(s.get("yield_on_cost", 0))),
        ]
        shade = False
        for label, value in rows_inv:
            r_color = None
            if label in ("Retorno Total $", "Retorno Total %", "IRR Anualizado"):
                try:
                    num = float(value.replace("$", "").replace("%", "").replace("+", "").replace(",", ""))
                    r_color = _GREEN if num >= 0 else (200, 50, 50)
                except Exception:
                    pass
            pdf._row(label, value, shade=shade, value_color=r_color)
            shade = not shade

        # Benchmark (solo mode_b)
        if s.get("ticker_mode") == "mode_b":
            bench_roi = s.get("benchmark_roi")
            if bench_roi is not None:
                diff = t_ret_pct - bench_roi
                b_color = _GREEN if diff >= 0 else (200, 50, 50)
                pdf._row("Benchmark VOO (timing real)", _fmt_pct(bench_roi, signed=True), shade=shade)
                shade = not shade
                pdf._row("Tu ventaja vs VOO",           _fmt_pct(diff, signed=True), shade=shade, value_color=b_color)
                shade = not shade

        # Posición en acciones
        pdf._section_title("POSICIÓN EN ACCIONES")
        pdf._row("Acciones Compradas", f"{s.get('shares_bought', 0):,.4f}", shade=False)
        pdf._row("Acciones Vendidas",  f"{s.get('shares_sold',   0):,.4f}", shade=True)
        pdf._row("Acciones Netas",     f"{s.get('shares_owned',  0):,.4f}", shade=False)
        pdf._row("Precio Actual",      _fmt_usd_plain(s.get("current_price", 0)), shade=True)

        # Alertas — splits, discrepancias
        splits = s.get("splits_detected", [])
        discs  = s.get("price_discrepancies", [])
        if splits or discs:
            pdf._section_title("ALERTAS")
            for sp in splits:
                kind = "Split" if sp["ratio"] > 1 else "Reverse Split"
                pdf._row(f"{kind} detectado", f"{sp['ratio']:.0f}:1 el {sp['date']}", shade=False)
            for d in discs:
                pdf._row(f"Discrepancia precio {d['date']}",
                         f"CSV ${d['csv_price']:.2f} vs yfinance ${d['yf_price']:.2f} (ratio {d['ratio']:.2f}x)",
                         shade=True)

        # Métricas de riesgo
        pdf._section_title("MÉTRICAS DE RIESGO AJUSTADO")
        pdf._two_col_row("Sharpe Ratio",    _risk_fmt("sharpe_ratio"),
                         "Sortino Ratio",   _risk_fmt("sortino_ratio"), shade=False)
        pdf._two_col_row("Max Drawdown",    _risk_fmt("max_drawdown", pct=True),
                         "Volatilidad Anual", _risk_fmt("volatilidad_anualizada", pct=True), shade=True)
        pdf._two_col_row("Beta vs VOO",     _risk_fmt("beta_vs_voo"),
                         "Alpha Anualizado", _risk_fmt("alpha_anualizado", pct=True), shade=False)

        # Ingresos mensuales
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
                label = str(period)[:7]
                fill = _LIGHT if shade else _WHITE
                pdf.set_fill_color(*fill)
                pdf.set_font("Helvetica", "", 7)
                pdf.cell(30, 5, f"  {label}", fill=True)
                pdf.set_font("Helvetica", "B", 7)
                pdf.cell(40, 5, _fmt_usd_plain(float(amount)), fill=True)
                pdf.ln()
                shade = not shade

    return bytes(pdf.output())
