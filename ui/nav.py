"""Taxonomía de navegación del artifact: categorías, ETFs y vistas.

GENERADO POR `tools/extract_design_system.py` — NO EDITAR A MANO.
Los valores salen del bloque `las constantes JS de navegación` del demo del artifact. Si hay que cambiarlos,
se cambia el demo y se regenera; así el port no puede divergir de su fuente.
"""

CAT_LABELS = {
    'dividendos': 'Dividendos',
    'largo': 'Largo Plazo',
    'comparacion': 'Comparación',
    'metodo': 'Método tradicional',
}

CAT_ORDER = ('dividendos', 'largo', 'comparacion', 'metodo')

CATS = {
    'dividendos': ('MSTY', 'TSLY', 'NVDY', 'CONY'),
    'largo': ('SCHB', 'XLK', 'SMH'),
}

SECTIONS = {
    'viaje': 'Cash flow',
    'salud': 'Salud NAV',
    'hoja': 'Hoja Excel',
}

SECTION_ORDER = ('viaje', 'salud', 'hoja')

CMP_VIEWS = {
    'simulacion': 'Simulación',
    'real': 'Real',
}

CMP_ORDER = ('simulacion', 'real')

MET_VIEWS = {
    'matriz': 'La matriz',
    'matriz2': 'Matriz 2',
}

MET_ORDER = ('matriz', 'matriz2')


# «Metodología» NO es una categoría: el demo la oculta al volver a la jerarquía
# (`showCat()`), y se llega a ella por el enlace «¿Cómo funciona? →» y por el pie.
METODOLOGIA_ES_CATEGORIA = False

# El tercer segmento (ETF) solo existe en «Cash flow»; en Salud NAV y Hoja Excel el
# demo lo oculta (`showTab`: `var conEtf = (name === "viaje")`).
VISTA_CON_ETF = "viaje"
