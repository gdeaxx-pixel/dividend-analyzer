"""El bloque del 1042-S salió de `logic.py` a `fiscal_1042s.py` (auditoría F4, 2026-10-09).

`test_1042s.py::test_ningun_pdf_viaja_a_gemini` lee `inspect.getsource(logic)`: tras el
movimiento ya no ve el código que lee el 1042-S, que es justo el documento con nombre, TIN y
número de cuenta. Medido: una llamada con `mime_type="application/pdf"` añadida en
`fiscal_1042s.py` dejaba ese test verde.
"""

import inspect

import fiscal_1042s


def test_ningun_pdf_del_1042s_viaja_a_gemini():
    assert 'mime_type="application/pdf"' not in inspect.getsource(fiscal_1042s)
