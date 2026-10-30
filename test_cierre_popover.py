"""Cierre del menú: HTML distinto en cada cierre y `pointerdown` antes del clic (30-oct-2026).

`_consumir_cierre_popover` emite un `st.html` con un script que simula un clic fuera del
popover. Medido en el navegador, hacen falta dos cosas y ninguna basta sola:
- HTML distinto en cada cierre: un rerun cortado por `st.rerun()` deja montado el elemento
  del cierre anterior y, si el nuevo llega idéntico, el script no se vuelve a ejecutar
  (solo con `pointerdown`: 2 de 10 cierres).
- `pointerdown` antes del clic: el popover de Streamlit 1.66 decide si el clic es de fuera
  con el último `pointerdown`, que era el del usuario dentro del menú (solo con el contador
  el script corría siempre, pero el menú se quedaba abierto casi siempre).
Con las dos: 20 de 20. Sin ninguna (como estaba): 11 de 48."""

from ui import chrome


def _cierres(monkeypatch, veces):
    emitidos = []
    monkeypatch.setattr(chrome.st, "session_state", {})
    monkeypatch.setattr(chrome.st, "html", lambda cuerpo, **kw: emitidos.append((cuerpo, kw)))
    for _ in range(veces):
        chrome._pedir_cierre_popover()
        chrome._consumir_cierre_popover()
    return emitidos


def test_cada_cierre_emite_un_script_distinto(monkeypatch):
    emitidos = _cierres(monkeypatch, 3)
    assert len(emitidos) == 3
    assert len({cuerpo for cuerpo, _ in emitidos}) == 3, "dos cierres con el mismo HTML"
    assert all(kw == {"unsafe_allow_javascript": True} for _, kw in emitidos)
    assert all("document.body.dispatchEvent" in cuerpo for cuerpo, _ in emitidos)
    assert all(cuerpo.index('"pointerdown"') < cuerpo.index('"click"') for cuerpo, _ in emitidos)


def test_sin_peticion_no_emite_nada(monkeypatch):
    emitidos = _cierres(monkeypatch, 0)
    chrome._consumir_cierre_popover()
    assert emitidos == []
