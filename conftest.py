"""conftest compartido del repo.

`frozen_price_cache`: redirige `price_cache` al snapshot congelado
(`knowledge/price_cache_frozen/`, versionado, que el cron NO toca) mientras dura el bloque.
Los tests que clavan cifras contra una entrada fija lo usan para que su entrada deje de moverse
con el refresh semanal del caché vivo — ver traspaso 2026-08-23 y Regla 6 del contrato.
"""
pytest_plugins = ["deriva_oraculos", "pytester"]

import contextlib
import os

import price_cache as pc

FROZEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "knowledge", "price_cache_frozen")


@contextlib.contextmanager
def frozen_price_cache():
    """Apunta CACHE_DIR/META_PATH/SPLITS_PATH al snapshot congelado y restaura al salir.
    Dentro del bloque, `_is_frozen()` hace que el cache nunca cuente como vencido."""
    saved = (pc.CACHE_DIR, pc.META_PATH, pc.SPLITS_PATH)
    pc.CACHE_DIR = FROZEN_DIR
    pc.META_PATH = os.path.join(FROZEN_DIR, "_meta.yaml")
    pc.SPLITS_PATH = os.path.join(FROZEN_DIR, "_splits.yaml")
    try:
        yield
    finally:
        pc.CACHE_DIR, pc.META_PATH, pc.SPLITS_PATH = saved


def mercado_congelado(ticker, start_date):
    """Sustituto de `logic.fetch_market_data` SIN red: la historia REAL del snapshot
    congelado (precio, dividendos y splits), con la forma que devuelve `yf.download(...,
    actions=True)` — incluida la columna 'Stock Splits'. Para los tests cuyo resultado
    depende de los dividendos o splits reales y no de un precio cualquiera: un mock plano
    los borra y cambia lo que se mide (medido en la dona de cobertura, auditoría M4, H6).

    Un ticker que no está en el snapshot devuelve vacío con motivo, igual que
    `fetch_market_data` cuando no encuentra datos: nunca sale a la red."""
    import pandas as pd
    t = str(ticker).upper()
    if not os.path.exists(os.path.join(FROZEN_DIR, f"{t}.parquet")):
        return pd.DataFrame(), f"{t} no está en el snapshot congelado"
    with frozen_price_cache():
        hist = pc.load_history(t).history.copy()
        splits = pc.load_splits(t).splits
    hist["Stock Splits"] = 0.0
    for fecha, razon in splits.items():
        if fecha in hist.index:
            hist.loc[fecha, "Stock Splits"] = float(razon)
    desde = pd.to_datetime(start_date) - pd.Timedelta(days=10)   # mismo margen que el real
    return hist[hist.index >= desde], None
