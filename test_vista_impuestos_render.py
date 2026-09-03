"""PR 1 «la mudanza» — la vista «Impuestos» se parte en 5 pantallas
(`ui.impuestos.VIEW_ORDER`) sin cambiar contenido: cada una RENDERIZA un trozo distinto
del mismo objeto fiscal.

Estos tests son del DESPACHO, no de la fiscalidad: que `render_impuestos` inyecte la
vista pedida, que cada clave tenga su propio alto, y que el cinturón de
`impuestos.render_vista` caiga a la primera vista ante una clave desconocida. La
aritmética la siguen pineando `test_vista_impuestos.py` (por datos, no por marcado).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import ui.componentes as componentes  # noqa: E402
from ui import impuestos  # noqa: E402

_DATOS = {"fondos": [{"ticker": "MSTY"}], "peldanos": {}, "declarado": False}


def _captura(monkeypatch):
    caja = {}

    def _fake_html(html, height=None, scrolling=None):
        caja["html"] = html
        caja["height"] = height

    monkeypatch.setattr(componentes.components, "html", _fake_html)
    return caja


def test_viewset_tiene_las_cinco_vistas_en_orden():
    assert tuple(impuestos.VIEWS) == impuestos.VIEW_ORDER
    assert impuestos.VIEW_ORDER == ("corte", "fondos", "venta", "pais", "recuperar")


@pytest.mark.parametrize("vista", impuestos.VIEW_ORDER)
def test_render_impuestos_inyecta_solo_la_vista_pedida(monkeypatch, vista):
    caja = _captura(monkeypatch)
    componentes.render_impuestos(_DATOS, "Claro", vista=vista)

    assert "{{VISTA_ACTIVA}}" not in caja["html"], "quedó el placeholder sin sustituir"
    assert f'var VISTA_ACTIVA = "{vista}";' in caja["html"]
    for otra in impuestos.VIEW_ORDER:
        if otra != vista:
            assert f'var VISTA_ACTIVA = "{otra}";' not in caja["html"]


@pytest.mark.parametrize("vista", impuestos.VIEW_ORDER)
def test_cada_vista_trae_su_propio_alto(monkeypatch, vista):
    caja = _captura(monkeypatch)
    componentes.render_impuestos(_DATOS, "Claro", vista=vista)
    assert caja["height"] == componentes.ALTO_IMPUESTOS[vista]
    assert set(componentes.ALTO_IMPUESTOS) == set(impuestos.VIEW_ORDER)


def test_render_vista_cae_a_la_primera_vista_ante_una_clave_desconocida(monkeypatch):
    caja = _captura(monkeypatch)

    class _Ruta:
        tema = "Claro"

    monkeypatch.setattr(impuestos, "obtener_resultados", lambda: None, raising=False)
    # con `obtener_resultados` devolviendo None se corta antes del render (estado vacío);
    # el cinturón se prueba llamando a componentes.render_impuestos por la ruta real:
    componentes.render_impuestos(_DATOS, "Claro", vista="no-existe")
    # alto de respaldo = el mayor, nunca un KeyError
    assert caja["height"] == max(componentes.ALTO_IMPUESTOS.values())


def test_impuestos_render_vista_normaliza_la_clave(monkeypatch):
    """`impuestos.render_vista` debe pasar SIEMPRE una clave de `VIEWS` a
    `render_impuestos`, aunque el llamador pase basura."""
    import ui.adapters as adapters
    from ui import estado

    caja = _captura(monkeypatch)
    monkeypatch.setattr("ui.vistas.obtener_resultados", lambda: {"MSTY": object()})
    monkeypatch.setattr(estado, "perfil_fiscal", lambda: None)
    monkeypatch.setattr(adapters, "impuestos_data",
                        lambda *a, **k: {"fondos": [{"ticker": "MSTY"}]})

    class _Ruta:
        tema = "Claro"

    impuestos.render_vista("basura-total", _Ruta())
    assert 'var VISTA_ACTIVA = "corte";' in caja["html"]
