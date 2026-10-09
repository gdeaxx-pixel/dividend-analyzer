"""Splits, pares de transferencia y tenencia mínima: el camino de las acciones en `analyze_portfolio`.

Extraído de `logic.py` el 2026-10-09 (auditoría app-audit 2026-10-07, F4, segundo corte):
refactor puro, sin cambio de comportamiento. El código es byte-idéntico al que vivía en
`logic.py`; `logic` re-exporta estos nombres para los consumidores históricos (`logic.X`).
Dirección única: `logic` importa de aquí; este módulo no importa `logic`.
"""

import numpy as np
import pandas as pd


def _cumul_split_factor(tx_date, splits_series: pd.Series) -> float:
    """Return the cumulative split factor that applies to a share purchased on tx_date.

    Multiplies all split ratios that occurred AFTER tx_date so that historical
    share quantities from the CSV (which are in pre-split units) are correctly
    scaled to today's share count.

    Example: XLK 2:1 split on 2025-12-05.
    A share bought on 2024-08-26 → factor = 2.0 → counts as 2 shares today.
    A share bought on 2026-01-29 (post-split) → factor = 1.0 → no adjustment.
    """
    if splits_series is None or splits_series.empty:
        return 1.0
    try:
        tx_ts = pd.Timestamp(tx_date).normalize()
        if tx_ts.tzinfo is not None:
            tx_ts = tx_ts.tz_localize(None)
        idx = splits_series.index
        if idx.tzinfo is not None:
            idx = idx.tz_localize(None)
        future = splits_series[idx.normalize() > tx_ts]
        factor = 1.0
        for r in future:
            factor *= float(r)
        return factor
    except Exception:
        return 1.0


def _net_transfer_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """Neutraliza pares de migración entre brokers (p. ej. TD Ameritrade -> Schwab).

    Una transferencia de cuenta aparece como DOS filas el mismo día y mismo ticker:
    una 'Journaled Shares' de salida (Quantity < 0, descripción "...TRANSFER...OUT")
    y una 'Internal Transfer' de entrada (Quantity > 0). Son las dos patas del mismo
    movimiento. Se elimina la salida y la entrada gemela queda marcada en `_migracion_q` con
    las acciones traspasadas: tras la migración la posición tiene EXACTAMENTE esas acciones,
    y el bucle de `analyze_portfolio` suma solo lo que falta para llegar a ellas (las
    compradas antes de que empiece el CSV). Sumar la entrada entera contaba dos veces lo que
    el historial TDA ya traía: SVOL (CSV real `1`) compró 22 + 3.46 de DRIP en TDA, migró
    25.464 y vendió 28.2475 — con la entrada entera quedaban 25.464 acciones fantasma.
    Las 'Journaled Shares' sin gemela (salidas reales) se conservan.
    """
    if df is None or df.empty or 'Action' not in df.columns or 'Quantity' not in df.columns:
        return df
    if 'Ticker' not in df.columns or 'Date' not in df.columns:
        return df
    out = df.copy()
    act = out['Action'].astype(str).str.lower()
    qty = pd.to_numeric(out['Quantity'], errors='coerce').fillna(0)
    journal_out = act.str.contains('journal', na=False) & (qty < 0)
    transfer_in = act.str.contains('transfer', na=False) & (qty > 0)
    if not journal_out.any() or not transfer_in.any():
        return df
    drop_idx = []
    emparejadas = []
    in_idx = list(out.index[transfer_in])
    for i in out.index[journal_out]:
        t, d, q = out.at[i, 'Ticker'], out.at[i, 'Date'], abs(qty[i])
        for j in in_idx:
            if (out.at[j, 'Ticker'] == t and out.at[j, 'Date'] == d
                    and abs(abs(qty[j]) - q) < 1e-6 and j not in drop_idx):
                drop_idx.append(i)
                emparejadas.append(j)
                in_idx.remove(j)  # cada entrada empareja con una sola salida
                break
    if not drop_idx:
        return df
    out['_migracion_q'] = np.nan
    for j in emparejadas:
        out.at[j, '_migracion_q'] = abs(qty[j])
    return out.drop(index=drop_idx)


def is_held_too_briefly(ticker_df: pd.DataFrame, threshold_days: int = 14) -> tuple:
    """
    Returns (True, holding_days) if the position was fully closed in < threshold_days.
    Returns (False, None) if position is still open OR was held long enough.
    Only triggers when ALL shares have been sold (net_shares ≈ 0).
    """
    # Excluye 'transfer'/'journal': una salida por transferencia trae Quantity negativa y, con
    # abs(), inflaba total_bought — una posición realmente cerrada podía no detectarse.
    buys = ticker_df[ticker_df['Action'].str.lower().str.contains(
        'buy|bought|compra|deposit|contribution', na=False)]
    sells = ticker_df[ticker_df['Action'].str.lower().str.contains(
        'sell|sold|venta', na=False)]

    if buys.empty or sells.empty:
        return False, None  # Sin ventas → posición abierta → no filtrar

    # abs() en ambos: IB exporta ventas con Quantity negativa; sin abs el neto
    # se inflaría (bought - (-sold)) y una posición cerrada nunca se detectaría.
    total_bought = pd.to_numeric(buys['Quantity'], errors='coerce').fillna(0).abs().sum()
    total_sold = pd.to_numeric(sells['Quantity'], errors='coerce').fillna(0).abs().sum()
    net_shares = total_bought - total_sold

    if net_shares > 0.01:
        return False, None  # Todavía tiene shares → no filtrar

    # Posición completamente cerrada — calcular período
    first_buy = buys['Date'].min()
    last_sell = sells['Date'].max()
    holding_days = (last_sell - first_buy).days

    if holding_days < threshold_days:
        return True, holding_days

    return False, None
