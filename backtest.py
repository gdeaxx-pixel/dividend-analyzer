"""backtest.py — motor de backtest event-driven sobre historia real de yfinance.

Fase 3.1 del plan de remediacion (`vivid-popping-clover.md`). Puro: sin Streamlit, sin cache,
sin estado global. Solo pandas + yfinance. `ui/` NO importa este modulo todavia (eso es 3.2).

## Convencion de splits (LEER ANTES DE TOCAR ESTE ARCHIVO)

yfinance normaliza retroactivamente TODA su historia — precio (`Close`, incluso con
`auto_adjust=False`, que solo evita el ajuste por dividendos) y dividendo-por-accion
(`Ticker.dividends`) — a la unidad de accion VIGENTE HOY. Verificado empiricamente contra
MSTY (split inverso 1:5 el 2025-12-08): el dividendo que yfinance reporta para 2025-11-20 es
0.740 USD/accion; el que realmente pago el fondo ese ciclo (segun el extracto real de IB) fue
0.1475 USD/accion — exactamente 1/5. yfinance ya escalo el historico hacia arriba para que sea
consistente con el numero de acciones post-split.

Consecuencia practica: `run_backtest()` (parte de abajo) que solo consume `Close` +
`Dividends` de yfinance de punta a punta NO necesita ningun ajuste manual por split — las dos
series ya son mutuamente consistentes en todo momento, igual que un grafico de precio
"split-adjusted" de cualquier bróker. Esto ya era sabido en el código existente
(`logic.py:5791`, "Precios y dividendos de yfinance ya vienen ajustados por splits").

Donde SI hace falta aritmetica de split explicita es al reconciliar contra cantidades de
acciones que vienen de un broker real (`shares_from_transactions`, `dividends_for_position`):
esas cantidades quedan grabadas en la unidad vigente AL MOMENTO de la transaccion, no en la
unidad de hoy. Ejemplo verificado: Daniel compro MSTY en lotes que suman 1250 "acciones" segun
el extracto de IB (todas las compras fueron *antes* del split 2025-12-08); su posicion real hoy
es 250 acciones (1250 / 5) — que es exactamente lo que declara el broker. Sin convertir esas
1250 acciones-vintage a su equivalente actual (x0.2), cualquier reconciliacion contra dividendos
de yfinance queda ~5x fuera para todo el tramo anterior al split.

`shares_from_transactions` hace esa conversion: por cada transaccion, multiplica la cantidad
transada por el producto de las razones de todos los splits *posteriores* a la fecha de esa
transaccion (`Stock Splits` de yfinance: ratio < 1 = split inverso, p.ej. 0.2 = 1:5). El
resultado es una serie de posicion en "unidades vigentes hoy", compatible con `Close`/
`Dividends` de yfinance sin mas conversiones.

## Elegibilidad de dividendo: estrictamente ANTES de la fecha ex-dividendo

Bug real encontrado en la auditoria de este PR (no era de splits, aunque el sintoma —numeros
inflados alrededor de las fechas de compra— parecia serlo): comprar el MISMO dia de la fecha
ex-dividendo NO da derecho a esa distribucion (convencion estandar de mercado — hay que ser
tenedor de registro desde ANTES del ex-date; vender el mismo dia SI conserva el derecho, ya
que la tenencia relevante es la del cierre del dia anterior). `dividends_for_position` usa
`position_asof(position, ex_date, inclusive=False)` — corte estrictamente `< ex_date` — para
no contar de mas una compra que cae justo el dia del evento.

Verificado contra MSTY/IB: con corte inclusivo (`<=`, el bug), cada compra que caia el mismo
dia que un ex-date de yfinance se sumaba de mas a esa distribucion (p.ej. la compra de 100
acciones-vintage del 2025-09-25 se contaba en el dividendo CON ex-date 2025-09-25, inflando
esa distribucion en 100 x 0.2 = 20 acciones equivalentes); el efecto se acumulaba en cada
compra sucesiva y llegaba a $346.55 (4.80%) de diferencia total contra el extracto real. Con
el corte exclusivo la diferencia cae a $0.97 (0.013%) — ver `test_backtest.py` para el gate
completo y el detalle evento-por-evento.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Mapping, Optional, Union

import pandas as pd
import yfinance as yf

DateLike = Union[str, dt.date, dt.datetime, pd.Timestamp]


def _to_ts(d: Optional[DateLike]) -> Optional[pd.Timestamp]:
    if d is None:
        return None
    ts = pd.Timestamp(d)
    if ts.tz is not None:
        ts = ts.tz_localize(None)
    return ts.normalize()


def _tz_naive(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    if getattr(index, "tz", None) is not None:
        return index.tz_localize(None)
    return index


# ── Descarga de datos reales ──────────────────────────────────────────────

def fetch_history(ticker: str, start: Optional[DateLike] = None,
                   end: Optional[DateLike] = None) -> pd.DataFrame:
    """Historia diaria real de `ticker`: precio crudo (`Close`, sin ajuste por dividendo) +
    dividendo por accion (`Dividends`), ambos ya split-adjusted por yfinance (ver docstring
    del modulo). `auto_adjust=False` es deliberado: con `auto_adjust=True` yfinance retro-
    ajusta `Close` restando cada dividendo del precio, y el DRIP quedaria contado dos veces
    (una vez via el precio deprimido, otra via la reinversion explicita del motor).

    Devuelve DataFrame indexado por fecha (tz-naive, normalizada a medianoche), columnas
    ['Close', 'Dividends'] como minimo. Vacio si el ticker no tiene historia. Deja que
    cualquier error de red/yfinance suba tal cual — el caller decide si reintentar o hacer
    skip (no hay fallback silencioso a datos falsos).
    """
    t = yf.Ticker(ticker)
    start_ts = _to_ts(start)
    if start_ts is None:
        # Sin `start`, yfinance NO asume "desde incepcion": si se pasa `end` sin `period` ni
        # `start`, cae a una ventana reciente corta (~1 mes). `period="max"` es la forma
        # correcta de pedir "toda la historia disponible" cuando no hay fecha de arranque.
        hist = t.history(period="max", end=_to_ts(end), auto_adjust=False, actions=True)
    else:
        hist = t.history(start=start_ts, end=_to_ts(end), auto_adjust=False, actions=True)
    if hist is None or hist.empty:
        return pd.DataFrame(columns=["Close", "Dividends"])
    hist = hist.copy()
    hist.index = _tz_naive(hist.index).normalize()
    if "Dividends" not in hist.columns:
        hist["Dividends"] = 0.0
    hist["Dividends"] = hist["Dividends"].fillna(0.0)
    return hist


def fetch_splits(ticker: str) -> pd.Series:
    """Serie de splits real de `ticker` (indice = fecha efectiva, valor = razon
    nuevas-acciones-por-accion-vieja; <1.0 = split inverso). Vacia si no hubo splits."""
    s = yf.Ticker(ticker).splits
    if s is None or len(s) == 0:
        return pd.Series(dtype=float)
    s = s.copy()
    s.index = _tz_naive(s.index).normalize()
    return s


# ── Reconstruccion de posicion real a partir de transacciones de un broker ──

def shares_from_transactions(transactions: pd.DataFrame, splits: pd.Series) -> pd.Series:
    """Convierte transacciones de un broker (cantidades en la unidad VIGENTE AL MOMENTO de
    cada transaccion) en una serie de posicion acumulada en unidades VIGENTES HOY — la misma
    convencion que usa yfinance para `Close`/`Dividends` (ver docstring del modulo).

    Args:
        transactions: DataFrame con columnas 'Date' (fecha de la transaccion) y 'Quantity'
            (con signo: compra positiva, venta negativa — la convencion de
            `logic.parse_ibkr_csv`/`parse_schwab_csv`). Cualquier otra columna se ignora.
        splits: serie de `fetch_splits(ticker)` — indice = fecha efectiva, valor = razon.

    Devuelve pd.Series indexada por fecha de transaccion (ascendente), valor = posicion
    acumulada en unidades vigentes hoy (step function: usar `position_asof` para consultar
    cualquier fecha intermedia).
    """
    if transactions is None or len(transactions) == 0:
        return pd.Series(dtype=float)

    tx = transactions.copy()
    tx["Date"] = pd.to_datetime(tx["Date"])
    if isinstance(tx["Date"].dtype, pd.DatetimeTZDtype):
        tx["Date"] = tx["Date"].dt.tz_localize(None)
    tx["Date"] = tx["Date"].dt.normalize()
    tx["Quantity"] = tx["Quantity"].astype(float)
    tx = tx.sort_values("Date")

    def _factor_after(d: pd.Timestamp) -> float:
        """Producto de razones de splits cuya fecha efectiva es POSTERIOR a `d` — convierte
        una cantidad transada en `d` (unidad vintage de ese momento) a unidad vigente hoy."""
        if splits is None or len(splits) == 0:
            return 1.0
        future = splits[splits.index > d]
        if len(future) == 0:
            return 1.0
        return float(future.prod())

    tx["adj_qty"] = [q * _factor_after(d) for q, d in zip(tx["Quantity"], tx["Date"])]
    position = tx.groupby("Date")["adj_qty"].sum().cumsum()
    position.name = "shares"
    return position


def position_asof(position: pd.Series, date: DateLike, inclusive: bool = True) -> float:
    """Posicion vigente en `date` (step function: ultimo valor con indice <= date si
    `inclusive=True`, o < date si `inclusive=False`; 0 si `date` es anterior a la primera
    transaccion).

    `inclusive=False` es la convencion correcta para elegibilidad de dividendo: para cobrar
    la distribucion de una fecha ex-dividendo D hay que haber comprado ANTES de D (comprar el
    mismo dia D no da derecho a esa distribucion — ver `dividends_for_position`, que es quien
    debe usar `inclusive=False`). `inclusive=True` (default) es la lectura general de
    "posicion al cierre del dia D", correcta para cualquier otro uso de la posicion."""
    if position is None or len(position) == 0:
        return 0.0
    ts = _to_ts(date)
    eligible = position[position.index <= ts] if inclusive else position[position.index < ts]
    return float(eligible.iloc[-1]) if len(eligible) else 0.0


def dividends_for_position(
    ticker: str,
    position: pd.Series,
    start: Optional[DateLike] = None,
    end: Optional[DateLike] = None,
    dividends: Optional[pd.Series] = None,
    date_buffer_days: int = 3,
) -> tuple:
    """Recorre cada fecha ex-dividendo real de `ticker` dentro de [start, end] y calcula el
    dividendo bruto que habria cobrado una posicion que siguio exactamente `position`
    (tipicamente el resultado de `shares_from_transactions`) en cada una de esas fechas.

    `date_buffer_days` amplia la ventana de busqueda de dividendos mas alla de [start, end]
    porque la fecha ex-dividendo de yfinance y la fecha de "pago"/asiento que reporta un
    broker suelen diferir por 1-2 dias habiles — sin margen se pueden perder eventos en los
    bordes de la ventana real de tenencia.

    Devuelve (total_bruto: float, detalle: pd.DataFrame con columnas
    ['ex_date', 'shares', 'rate_per_share', 'amount']).
    """
    if dividends is None:
        hist = fetch_history(ticker, start=None, end=end)
        dividends = hist["Dividends"] if "Dividends" in hist.columns else pd.Series(dtype=float)
    divs = dividends[dividends > 0]

    start_ts = _to_ts(start)
    end_ts = _to_ts(end)
    if start_ts is not None:
        divs = divs[divs.index >= start_ts - pd.Timedelta(days=date_buffer_days)]
    if end_ts is not None:
        divs = divs[divs.index <= end_ts + pd.Timedelta(days=date_buffer_days)]

    rows = []
    total = 0.0
    for ex_date, rate in divs.items():
        # inclusive=False: comprar EL MISMO dia de la fecha ex-dividendo no da derecho a esa
        # distribucion (convencion estandar de mercado). Verificado contra el extracto real
        # de IB (ver test_backtest.py): sin esto, cada compra que cae el mismo dia que un
        # ex-date queda contada de mas — el error no es de splits, es de elegibilidad.
        shares = position_asof(position, ex_date, inclusive=False)
        amount = shares * float(rate)
        total += amount
        rows.append({"ex_date": ex_date, "shares": shares, "rate_per_share": float(rate),
                      "amount": amount})

    detail = pd.DataFrame(rows, columns=["ex_date", "shares", "rate_per_share", "amount"])
    return total, detail


# ── Motor principal: simulacion DRIP / efectivo desde capital inicial ───────

@dataclasses.dataclass
class BacktestResult:
    ticker: str
    drip: bool
    nra_rate: float
    initial_shares: float
    initial_capital: float
    daily: pd.DataFrame  # columnas: price, dividend_per_share, shares, gross_dividend,
                          # nra_withheld, net_dividend, cash_accum, portfolio_value,
                          # roc_refund, roc_receivable, total_value

    @property
    def gross_dividends_total(self) -> float:
        return float(self.daily["gross_dividend"].sum())

    @property
    def roc_refund_total(self) -> float:
        """Reembolso ROC efectivamente COBRADO (excluye lo devengado y aun por cobrar)."""
        if "roc_refund" not in self.daily:
            return 0.0
        return float(self.daily["roc_refund"].sum())

    @property
    def roc_receivable_final(self) -> float:
        """Reembolso ya devengado que el 1042-S aun no ha pagado a la fecha de corte."""
        if "roc_receivable" not in self.daily or self.daily.empty:
            return 0.0
        return float(self.daily["roc_receivable"].iloc[-1])

    @property
    def nra_withheld_total(self) -> float:
        return float(self.daily["nra_withheld"].sum())

    @property
    def net_dividends_total(self) -> float:
        return float(self.daily["net_dividend"].sum())

    @property
    def final_shares(self) -> float:
        return float(self.daily["shares"].iloc[-1]) if len(self.daily) else self.initial_shares

    @property
    def final_price(self) -> float:
        return float(self.daily["price"].iloc[-1]) if len(self.daily) else 0.0

    @property
    def final_total_value(self) -> float:
        return float(self.daily["total_value"].iloc[-1]) if len(self.daily) else self.initial_capital

    @property
    def price_return_pct(self) -> float:
        if len(self.daily) < 2:
            return 0.0
        p0 = float(self.daily["price"].iloc[0])
        p1 = float(self.daily["price"].iloc[-1])
        return (p1 / p0 - 1.0) * 100.0 if p0 > 0 else 0.0

    @property
    def total_return_pct(self) -> float:
        if self.initial_capital <= 0:
            return 0.0
        return (self.final_total_value / self.initial_capital - 1.0) * 100.0


def run_backtest(
    ticker: str,
    start_date: DateLike,
    initial_capital: Optional[float] = None,
    initial_shares: Optional[float] = None,
    drip: bool = True,
    nra_rate: float = 0.0,
    end_date: Optional[DateLike] = None,
    history: Optional[pd.DataFrame] = None,
    roc_pct_by_year: Optional[Mapping[int, float]] = None,
    refund_month: int = 3,
) -> BacktestResult:
    """Motor event-driven: recorre el calendario real de `ticker` dia a dia desde
    `start_date` (precio + distribucion, ambos reales de yfinance) y simula una posicion que
    arranca en `initial_shares` (o `initial_capital / precio_inicial` si no se da) y que:

      - con `drip=True`: reinvierte cada distribucion NETA de `nra_rate` al `Close` del
        propio dia ex-dividendo (misma convencion que `logic.build_total_return_series` /
        Morningstar TRI-por-evento: reinvertir en la fecha ex-div, no en la de pago).
      - con `drip=False`: mantiene las acciones fijas y acumula la distribucion neta como
        efectivo sin invertir (no gana ni pierde con el precio).

    `nra_rate` es un PARAMETRO de politica fiscal (0.0-1.0), no un dato historico — la
    retencion real depende del pais/tratado del inversor y no viene en la serie de yfinance
    (ver plan: "retencion NRA (parametro, no dato historico)").

    **Reembolso ROC (`roc_pct_by_year`)** — modela el escudo fiscal del ROC como lo que es
    en la realidad: se retiene `nra_rate` sobre TODA la distribucion al cobrarla, y la
    porcion que el aviso 19(a) reclasifica como retorno de capital vuelve MAS TARDE, en
    efectivo, cuando llega el 1042-S (`refund_month`, marzo por defecto, del año siguiente
    al fiscal). Formato: `{año: roc_pct}` con `roc_pct` en 0-100.

    Es distinto —y no equivalente— a bajar `nra_rate` a la tasa efectiva
    `nra_rate*(1-roc_pct)`, que es lo que hacia `ui.adapters._cmp_nra_rate`. Esa version
    asume que el escudo aplica AL COBRO, o sea que el dinero nunca sale del fondo y compone
    todo el tiempo. Medido sobre el caso de estudio: la diferencia es **+6.3%** en la
    cartera con DRIP, y cambia de SIGNO segun el fondo (MSTY +28.9%, NFLY -1.8%), porque
    tener ese dinero fuera del mercado durante un año protege en las caidas y cuesta en las
    subidas. Mezclar los dos modelos viola la Regla 2 del contrato fiscal (declarar base Y
    momento) — ver `specs/roc-nra-invariants.md`.

    El reembolso se DEVENGA con cada distribucion (columna `roc_receivable`, que suma a
    `total_value` porque es un activo real: una cuenta por cobrar al fisco) y se COBRA en
    `refund_month` (columna `roc_refund`); al cobrarse compra acciones si `drip=True`, o
    entra a `cash_accum` si no. Sin `roc_pct_by_year` ambas columnas son 0 y el motor se
    comporta exactamente como antes.

    No hace ningun ajuste manual por split: `Close`/`Dividends` de yfinance ya vienen
    normalizados de forma mutuamente consistente (ver docstring del modulo) — sumar acciones
    via DRIP con esas dos series es correcto en todo momento, incluso atravesando una fecha
    de split.

    Devuelve un `BacktestResult` con la serie temporal COMPLETA (no solo el punto final).
    """
    if initial_capital is None and initial_shares is None:
        raise ValueError("run_backtest requiere initial_capital o initial_shares")
    if not (0.0 <= nra_rate <= 1.0):
        raise ValueError(f"nra_rate fuera de rango [0,1]: {nra_rate}")

    if history is None:
        history = fetch_history(ticker, start=start_date, end=end_date)
    else:
        start_ts, end_ts = _to_ts(start_date), _to_ts(end_date)
        mask = history.index >= start_ts
        if end_ts is not None:
            mask &= history.index <= end_ts
        history = history[mask]

    if history is None or history.empty:
        empty = pd.DataFrame(columns=["price", "dividend_per_share", "shares",
                                       "gross_dividend", "nra_withheld", "net_dividend",
                                       "cash_accum", "portfolio_value", "roc_refund",
                                       "roc_receivable", "total_value"])
        cap = initial_capital if initial_capital is not None else 0.0
        return BacktestResult(ticker=ticker, drip=drip, nra_rate=nra_rate,
                               initial_shares=initial_shares or 0.0,
                               initial_capital=cap, daily=empty)

    history = history.sort_index()
    first_price = float(history["Close"].iloc[0])
    if initial_shares is None:
        initial_shares = initial_capital / first_price if first_price > 0 else 0.0
    if initial_capital is None:
        initial_capital = initial_shares * first_price

    shares = float(initial_shares)
    cash_accum = 0.0
    # Reembolso ROC devengado por año fiscal y aun no cobrado. Se devenga con cada
    # distribucion (no de golpe al cerrar el año) para que la serie no tenga un escalon
    # artificial: el caracter de ROC existe desde que se paga el dividendo; lo que llega
    # tarde es la CONFIRMACION —y el dinero— via 1042-S.
    receivable_by_year: dict[int, float] = {}
    rows = []
    for date, row in history.iterrows():
        price = float(row["Close"]) if pd.notna(row["Close"]) else 0.0
        div_rate = float(row["Dividends"]) if pd.notna(row.get("Dividends", 0.0)) else 0.0

        # 1) ¿llego hoy el 1042-S de algun año ya cerrado? Se cobra ANTES de procesar la
        #    distribucion del dia: el reembolso es dinero disponible desde su fecha.
        roc_refund_hoy = 0.0
        for year in sorted(receivable_by_year):
            if date >= pd.Timestamp(year=year + 1, month=refund_month, day=1):
                roc_refund_hoy += receivable_by_year.pop(year)
        if roc_refund_hoy > 0:
            if drip and price > 0:
                shares += roc_refund_hoy / price
            else:
                cash_accum += roc_refund_hoy

        gross_div = shares * div_rate if div_rate > 0 else 0.0
        nra_withheld = gross_div * nra_rate
        net_div = gross_div - nra_withheld

        if net_div > 0:
            if drip and price > 0:
                shares += net_div / price
            else:
                cash_accum += net_div

        # 2) devengar el reembolso de esta distribucion. `refund = retenido - retencion
        #    justa = nra_rate*bruto - nra_rate*bruto*(1-roc) = nra_rate*bruto*roc`, la
        #    misma identidad que `logic.estimate_roc_refund`.
        if gross_div > 0 and roc_pct_by_year:
            roc_pct = float(roc_pct_by_year.get(date.year) or 0.0)
            if roc_pct > 0:
                devengado = nra_withheld * max(0.0, min(100.0, roc_pct)) / 100.0
                receivable_by_year[date.year] = (
                    receivable_by_year.get(date.year, 0.0) + devengado)

        roc_receivable = sum(receivable_by_year.values())
        portfolio_value = shares * price
        # La cuenta por cobrar suma: es un activo real del inversor, no una promesa. Si no
        # sumara, la serie mostraria un hueco entre el cobro del dividendo y el 1042-S y
        # luego un salto — dinero que aparece de la nada.
        total_value = portfolio_value + (0.0 if drip else cash_accum) + roc_receivable

        rows.append({
            "date": date, "price": price, "dividend_per_share": div_rate, "shares": shares,
            "gross_dividend": gross_div, "nra_withheld": nra_withheld, "net_dividend": net_div,
            "cash_accum": cash_accum, "portfolio_value": portfolio_value,
            "roc_refund": roc_refund_hoy, "roc_receivable": roc_receivable,
            "total_value": total_value,
        })

    daily = pd.DataFrame(rows).set_index("date")
    return BacktestResult(ticker=ticker, drip=drip, nra_rate=nra_rate,
                           initial_shares=initial_shares, initial_capital=initial_capital,
                           daily=daily)
