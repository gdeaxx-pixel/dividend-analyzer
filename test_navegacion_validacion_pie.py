import re
from types import SimpleNamespace

import pytest

import logic
from ui import chrome, pie, validacion


class _FakeSt:
    def __init__(self):
        self.out = []
        self.session_state = {}

    def markdown(self, h, **k):
        self.out.append(h)

    def caption(self, t, **k):
        self.out.append(t)

    def texto(self):
        return " ".join(re.sub(r"<[^>]+>", " ", x) for x in self.out)


@pytest.fixture
def fake(monkeypatch):
    f = _FakeSt()
    monkeypatch.setattr(validacion, "st", f)
    monkeypatch.setattr(pie, "st", f)
    return f


def _ruta(cat, vista):
    return chrome.Ruta(categoria=cat, vista=vista, etf=None, tema="Claro")


def test_siguiente_desde_dividendos_igual_que_desde_largo():
    hab = {"largo": ["SCHB"], "dividendos": ["MSTY"]}
    assert chrome.paso_siguiente(_ruta("largo", "viaje"), hab) == ("comparacion", "simulacion")
    assert chrome.paso_siguiente(_ruta("dividendos", "viaje"), hab) == ("comparacion", "simulacion")


def test_numero_de_paradas_no_cambia():
    hab = {"largo": ["SCHB"], "dividendos": ["MSTY"]}
    cats = [c for c, _ in chrome._recorrido(hab)]
    assert ("largo" in cats) != ("dividendos" in cats)


def _patch_calidad(monkeypatch, dq):
    monkeypatch.setattr(logic, "classify_tickers", lambda t: {})
    monkeypatch.setattr(logic, "assess_data_quality", lambda r, c: dq)


def _res_mixto():
    res = {"MSTY": {}, "NVDY": {"error": "No market data found: x"}}
    res.update({f"ZZ{i}": {"skipped": True} for i in range(300)})
    return res


def test_verificadas_cuenta_solo_lo_evaluado(fake, monkeypatch):
    _patch_calidad(monkeypatch, {"MSTY": {"level": "ok"}})
    validacion._render_calidad_datos(_res_mixto())
    assert "Datos incompletos · 1 posición verificada · 1 sin precios" in fake.texto()
    assert "Datos completos" not in fake.texto()
    assert "--warn" in " ".join(fake.out)


def test_solo_un_fondo_con_error(fake, monkeypatch):
    _patch_calidad(monkeypatch, {})
    validacion._render_calidad_datos({"NVDY": {"error": "x"}})
    assert "Datos incompletos · 0 posiciones verificadas · 1 sin precios" in fake.texto()


def test_todo_bien_cuenta_bien(fake, monkeypatch):
    _patch_calidad(monkeypatch, {"MSTY": {"level": "ok"}, "SCHB": {"level": "ok"}})
    res = {"MSTY": {}, "SCHB": {}, **{f"ZZ{i}": {"skipped": True} for i in range(5)}}
    validacion._render_calidad_datos(res)
    assert "Datos completos · 2 posiciones verificadas" in fake.texto()


@pytest.mark.parametrize("ratio,esperado", [(0.1, "1:10"), (0.5, "1:2"), (1.5, "3:2"),
                                            (2, "2:1"), (10, "10:1"), (0.3333, "1:3")])
def test_razon_de_split_como_fraccion(fake, monkeypatch, ratio, esperado):
    monkeypatch.setattr(logic, "assess_ticker_quality", lambda r, t: {"level": "ok"})
    res = {"MSTY": {"splits_detected": [{"date": "2025-01-01", "ratio": ratio}]}}
    eventos = validacion._tech_events(res)
    assert eventos[0]["desc"].startswith(f"{esperado} — ")


def test_pie_sin_resultados_dibuja_el_aviso_legal(fake):
    pie.render_pie({})
    assert "Versión Beta" in fake.texto()
    assert "no constituye asesoría financiera" in fake.texto()


def test_validacion_sin_datos_no_queda_en_blanco(fake):
    validacion.render_validacion_datos({})
    assert "Todavía no hay datos que validar. Sube tu archivo para ver esta revisión." in fake.texto()
