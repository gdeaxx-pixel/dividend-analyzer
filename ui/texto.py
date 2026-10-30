"""Frases con número: singular o plural según la cantidad.

Sustituye las formas «posición(es)» y «1 instrumentos» de la carga y de Validación
(propuesta de interfaz del 2026-10-30, A7). Sin estado y sin Streamlit: lo importan
`ui.carga` y `ui.validacion`.
"""


def plural(n: int, uno: str, varios: str) -> str:
    """«1 posición», «3 posiciones». `uno` y `varios` son la frase entera sin el número,
    para que el resto de la frase (adjetivos, verbos) concuerde también."""
    return f"{n} {uno if n == 1 else varios}"
