"""conftest compartido del repo.

`frozen_price_cache`: redirige `price_cache` al snapshot congelado
(`knowledge/price_cache_frozen/`, versionado, que el cron NO toca) mientras dura el bloque.
Los tests que clavan cifras contra una entrada fija lo usan para que su entrada deje de moverse
con el refresh semanal del caché vivo — ver traspaso 2026-08-23 y Regla 6 del contrato.
"""
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
