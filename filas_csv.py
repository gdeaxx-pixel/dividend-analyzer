"""Primitivas de fila CSV: el año de una fecha y el monto del bróker como float.

Extraído de `logic.py` el 2026-10-09 (auditoría app-audit 2026-10-07, F4, tercer corte):
refactor puro, sin cambio de comportamiento. El código es byte-idéntico al que vivía en
`logic.py`; `logic` re-exporta estos nombres para los consumidores históricos (`logic.X`).
Dirección única: `logic` importa de aquí; este módulo no importa `logic`.
"""

import pandas as pd


def _row_year(dt):
    """Año calendario de la fecha de una fila de transacción, o None si no es una fecha
    válida (ausente/NaT). Usado para agrupar dividendos y retención por año fiscal."""
    if dt is None:
        return None
    try:
        if pd.isna(dt):
            return None
        return pd.Timestamp(dt).year
    except (TypeError, ValueError):
        return None


def _clean_money(raw) -> float:
    """Convierte un monto del broker ('$1,234.56', '6.57', '') a float; nan si no se puede."""
    try:
        if pd.isna(raw):
            return float('nan')
    except (TypeError, ValueError):
        pass
    s = str(raw).replace('$', '').replace(',', '').strip()
    if s in ('', '-', 'nan', 'N/A', 'None'):
        return float('nan')
    try:
        return float(s)
    except (ValueError, TypeError):
        return float('nan')
