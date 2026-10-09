"""Métricas de rendimiento que usa `analyze_portfolio`: drawdown, Sortino, CAGR, hold simulado.

Extraído de `logic.py` el 2026-10-09 (auditoría app-audit 2026-10-07, F4, segundo corte):
refactor puro, sin cambio de comportamiento. El código es byte-idéntico al que vivía en
`logic.py`; `logic` re-exporta estos nombres para los consumidores históricos (`logic.X`).
Dirección única: `logic` importa de aquí; este módulo no importa `logic`.
"""

import numpy as np
import pandas as pd


def _winsorize_returns(returns, lower=0.01, upper=0.99, min_len=20):
    """Acota una serie de retornos diarios a sus cuantiles [lower, upper] para que outliers
    espurios (transferencias de acciones sin efectivo, desfases de split, ticks malos de la API)
    no distorsionen vol/Sharpe/Sortino/beta. Series cortas (<min_len) se devuelven tal cual
    (los cuantiles no serían fiables). Defensiva ante entradas no-Series."""
    try:
        r = returns.dropna()
    except AttributeError:
        return returns
    if len(r) < min_len:
        return r
    lo, hi = r.quantile(lower), r.quantile(upper)
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return r
    return r.clip(lo, hi)


def _drawdown_twr(daily_returns_q):
    """Drawdown máximo sobre la riqueza unitizada (TWR) que arranca en 1.0: una venta o un aporte
    no mueven la riqueza por unidad, solo el precio y las distribuciones. Recibe los retornos
    diarios ya winsorizados (los mismos que usa Calmar). Devuelve (mínimo en %, serie en % con el
    índice de los retornos) o (None, serie vacía) con menos de 2 retornos."""
    r = pd.Series(daily_returns_q, dtype=float).dropna()
    if len(r) < 2:
        return None, pd.Series(dtype=float)
    riqueza = pd.concat([pd.Series([1.0]), (1.0 + r.reset_index(drop=True)).cumprod()], ignore_index=True)
    dd = (riqueza / riqueza.cummax() - 1.0) * 100.0
    return float(dd.min()), pd.Series(dd.iloc[1:].values, index=r.index)


def _sortino_ratio(daily_returns, rf_daily, periods: int = 252):
    """Sortino anualizado con downside deviation estándar (CFA/GIPS).

    Downside deviation = raíz de la media de (min(r - MAR, 0))^2 sobre TODOS los
    períodos (no solo los días negativos), con MAR = rf_daily. Esto difiere de usar
    `std` de los retornos negativos (que excluye los días positivos del denominador
    y subestima el riesgo a la baja). Devuelve None si no hay datos suficientes o no
    hay desviación a la baja.
    """
    r = daily_returns.dropna() if hasattr(daily_returns, 'dropna') else pd.Series(list(daily_returns))
    if len(r) < 2:
        return None
    downside = np.minimum(r - rf_daily, 0.0)
    dd = float(np.sqrt((downside ** 2).mean()))
    if dd <= 1e-9:
        return None
    excess = float(r.mean()) - rf_daily
    return float((excess / dd) * np.sqrt(periods))


def _snap_to_trading_days(daily, index):
    """Desplaza cada fecha de actividad al siguiente día de cotización disponible.

    Un `reindex(market_data.index)` a secas DESCARTA las fechas que no existen en el índice
    de precios —fin de semana, feriado, halt del ticker o hueco de datos de yfinance— y su
    importe desaparece del acumulado en vez de diferirse al siguiente día hábil. Con una
    compra fechada un sábado, la curva de capital invertido quedaba plana en cero durante
    toda la serie y el ticker salía marcado como "datos incompletos · no confiable", aunque
    su costo, ROI y valor de mercado (que se calculan por otra vía) fueran correctos.

    No es un caso de laboratorio: las transferencias de posiciones (ACATS/journaled, que
    `Cash_Flow_In` también recoge) pueden venir fechadas en fin de semana, y los extractos
    de IB con zona horaria no estadounidense pueden fechar un trade del viernes por la tarde
    ET en sábado.

    Las fechas que ya cotizan no se mueven, así que para cualquier CSV cuyas transacciones
    caigan todas en día hábil el resultado es idéntico al de antes. Las posteriores al
    último día con precio se descartan: no hay día de cotización al que llevarlas.
    """
    if daily is None or len(daily) == 0 or index is None or len(index) == 0:
        return daily
    daily = daily.sort_index()
    pos = index.searchsorted(daily.index)
    keep = pos < len(index)
    snapped = daily[keep].copy()
    snapped.index = index[pos[keep]]
    return snapped.groupby(level=0).sum()


def _annualized_cagr(close, days=None):
    """CAGR de precio anualizado (%) sobre una serie de cierres. `days`=None usa toda la
    serie; `days`=365 usa la ventana de los últimos 12 meses. Defensivo → None si no aplica."""
    try:
        c = close.dropna()
        if len(c) < 5:
            return None
        if days is not None:
            c = c[c.index >= c.index[-1] - pd.Timedelta(days=days)]
            if len(c) < 5:
                return None
        p0 = float(c.iloc[0]); p1 = float(c.iloc[-1])
        yrs = max((c.index[-1] - c.index[0]).days / 365.25, 0.05)
        return round(((p1 / p0) ** (1 / yrs) - 1) * 100, 2) if p0 > 0 else None
    except Exception:
        return None


def _simulate_hold_value(price_s, div_s, flow_s):
    """Simula invertir `flow_s` (flujo de capital diario) en un instrumento con precio `price_s`
    y dividendos `div_s` reinvertidos — el 'qué hubiera pasado si tenías el subyacente directo'.
    Mismo patrón que el benchmark VOO. Series alineadas al mismo índice. Devuelve el valor final."""
    shares = 0.0
    last_val = 0.0
    for date in price_s.index:
        vp = price_s.loc[date]
        vp = float(vp) if not pd.isna(vp) else 0.0
        if vp > 0:
            shares += float(flow_s.get(date, 0.0) or 0.0) / vp
            dv = float(div_s.get(date, 0.0) or 0.0) if div_s is not None else 0.0
            if dv > 0 and shares > 0:
                shares += (dv * shares) / vp
        shares = max(shares, 0.0)
        last_val = shares * vp
    return last_val
