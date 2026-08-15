"""price_cache.py — loader del cache de historia de precio/dividendo/split
(`knowledge/price_cache/`), con fallback EXPLICITO a yfinance en vivo cuando el cache falta o
esta vencido.

Fase 3.2 del plan de remediacion (`vivid-popping-clover.md`). El cache lo escribe
`fetch_price_cache.py` (corrido semanalmente por `.github/workflows/refresh-price-cache.yml`,
mismo patron que `fetch_roc_19a.py` / `refresh-roc-19a.yml`). Este modulo SOLO lee el cache en
disco — la unica llamada a yfinance que hace es el fallback declarado de abajo.

Punto de inyeccion: `load_history(...).history` tiene EXACTAMENTE la forma que espera
`backtest.run_backtest(..., history=...)` — columnas ['Close', 'Dividends'], index=fecha
tz-naive normalizada — porque el cache se escribio con `backtest.fetch_history` (ya auditado
en la Fase 3.1). `ui/` NO importa este modulo todavia (eso es la Fase 3.3).

Cada resultado declara `source` ("cache" | "live" | "cache_stale_fallback") — nunca en
silencio, por diseno (ver plan: "declarar cual de las dos fuentes uso, nunca en silencio").
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import os
from typing import Optional

import pandas as pd
import yaml

import backtest as bt

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "knowledge", "price_cache")
META_PATH = os.path.join(CACHE_DIR, "_meta.yaml")
SPLITS_PATH = os.path.join(CACHE_DIR, "_splits.yaml")

# Daniel confirmo que un desfase de hasta un mes es aceptable (no hace falta tiempo real, ver
# plan). 35 dias da margen sobre el refresco semanal (deberia refrescar cada 7 dias) sin ser
# tan laxo que un cache que dejo de correr durante semanas pase inadvertido como "fresco".
DEFAULT_MAX_STALENESS_DAYS = 35


def _parquet_path(ticker: str) -> str:
    return os.path.join(CACHE_DIR, f"{ticker.upper()}.parquet")


def _load_yaml(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def _cache_age_days(asof_iso: Optional[str]) -> Optional[int]:
    if not asof_iso:
        return None
    try:
        asof = dt.date.fromisoformat(str(asof_iso))
    except (TypeError, ValueError):
        return None
    return (dt.date.today() - asof).days


def _slice_by_date(df: pd.DataFrame, start, end) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    start_ts, end_ts = bt._to_ts(start), bt._to_ts(end)
    mask = pd.Series(True, index=df.index)
    if start_ts is not None:
        mask &= df.index >= start_ts
    if end_ts is not None:
        mask &= df.index <= end_ts
    return df[mask]


def _slice_series_by_date(s: pd.Series, start, end) -> pd.Series:
    if s is None or len(s) == 0:
        return s
    start_ts, end_ts = bt._to_ts(start), bt._to_ts(end)
    mask = pd.Series(True, index=s.index)
    if start_ts is not None:
        mask &= s.index >= start_ts
    if end_ts is not None:
        mask &= s.index <= end_ts
    return s[mask]


def _read_cached_history(ticker: str) -> Optional[pd.DataFrame]:
    path = _parquet_path(ticker)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_parquet(path)
    except Exception:
        return None
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    df.index = df.index.normalize()
    return df


def _read_cached_splits(ticker: str) -> Optional[pd.Series]:
    all_splits = _load_yaml(SPLITS_PATH)
    if ticker not in all_splits:
        return None
    rows = all_splits.get(ticker) or []
    if not rows:
        return pd.Series(dtype=float)
    idx = pd.to_datetime([r["date"] for r in rows]).normalize()
    vals = [float(r["ratio"]) for r in rows]
    return pd.Series(vals, index=idx).sort_index()


@dataclasses.dataclass
class HistoryResult:
    history: pd.DataFrame
    source: str                        # "cache" | "live" | "cache_stale_fallback"
    ticker: str
    cache_asof: Optional[str] = None   # fecha ISO de generacion del cache usado (si aplica)
    stale: bool = False


@dataclasses.dataclass
class SplitsResult:
    splits: pd.Series
    source: str
    ticker: str
    cache_asof: Optional[str] = None
    stale: bool = False


def load_history(ticker: str, start=None, end=None,
                  max_staleness_days: int = DEFAULT_MAX_STALENESS_DAYS) -> HistoryResult:
    """Historia ['Close', 'Dividends'] para `ticker`, lista para pasar tal cual a
    `backtest.run_backtest(..., history=...)`.

    Orden de resolucion:
      1. Cache fresco (existe y `generated_at` <= `max_staleness_days`) -> source="cache".
      2. Cache ausente o vencido -> intenta yfinance en vivo -> source="live".
      3. yfinance en vivo falla (red caida) pero SI hay cache (aunque vencido) -> lo usa como
         ultimo recurso, declarado como source="cache_stale_fallback" y `stale=True` (mejor
         una cifra vieja y declarada que ninguna — nunca datos inventados).
      4. Sin cache y sin red: propaga la excepcion tal cual (mismo contrato que
         `backtest.fetch_history` — no hay fallback silencioso a datos falsos).
    """
    ticker = ticker.upper()
    meta = _load_yaml(META_PATH).get(ticker)
    cached = _read_cached_history(ticker) if meta else None
    age_days = _cache_age_days(meta.get("generated_at")) if meta else None
    asof = meta.get("generated_at") if meta else None

    if cached is not None and age_days is not None and age_days <= max_staleness_days:
        return HistoryResult(history=_slice_by_date(cached, start, end), source="cache",
                              ticker=ticker, cache_asof=asof, stale=False)

    try:
        live = bt.fetch_history(ticker, start=start, end=end)
        return HistoryResult(history=live, source="live", ticker=ticker,
                              cache_asof=asof, stale=False)
    except Exception:
        if cached is not None:
            return HistoryResult(history=_slice_by_date(cached, start, end),
                                  source="cache_stale_fallback", ticker=ticker,
                                  cache_asof=asof, stale=True)
        raise


def load_splits(ticker: str,
                 max_staleness_days: int = DEFAULT_MAX_STALENESS_DAYS) -> SplitsResult:
    """Serie de splits para `ticker` (misma forma que `backtest.fetch_splits`), con el mismo
    orden de resolucion cache-fresco -> vivo -> cache-vencido-como-ultimo-recurso que
    `load_history` (ver docstring de arriba)."""
    ticker = ticker.upper()
    meta = _load_yaml(META_PATH).get(ticker)
    cached = _read_cached_splits(ticker) if meta else None
    age_days = _cache_age_days(meta.get("generated_at")) if meta else None
    asof = meta.get("generated_at") if meta else None

    if cached is not None and age_days is not None and age_days <= max_staleness_days:
        return SplitsResult(splits=cached, source="cache", ticker=ticker,
                             cache_asof=asof, stale=False)

    try:
        live = bt.fetch_splits(ticker)
        return SplitsResult(splits=live, source="live", ticker=ticker,
                             cache_asof=asof, stale=False)
    except Exception:
        if cached is not None:
            return SplitsResult(splits=cached, source="cache_stale_fallback",
                                 ticker=ticker, cache_asof=asof, stale=True)
        raise


def cache_coverage() -> dict:
    """`{ticker: {generated_at, start, end, rows}}` tal cual esta en `_meta.yaml` — para que
    la UI de la Fase 3.3 pueda mostrar 'datos al DD/MM' sin tener que leer el yaml a mano."""
    return _load_yaml(META_PATH)
