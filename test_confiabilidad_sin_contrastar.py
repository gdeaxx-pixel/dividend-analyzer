"""«Alta» exige que algo se haya comparado; el 30 % sin país se rotula como supuesto.

Tres caminos daban «Confiabilidad alta» sin que ninguna fuente confirmara nada: un 1042-S
sin dividendos que cruzar, un reporte de ingresos que no toca ninguna posición y un fondo
sin precios. Ahora dicen «Sin contrastar». Y Comparación, sin país declarado, dice que el
30 % es la tasa máxima supuesta.
"""
import pandas as pd
import pytest

from ui import componentes, validacion
from ui.adapters import trg_real_data
from ui.validacion import (SIN_CONTRASTAR, _puntuacion_acertividad, clase_nivel,
                           hay_alertas, nivel_confiabilidad)

SIN_NADA = ["Sin discrepancias entre las fuentes disponibles."]
R_1042S = "El 1042-S no se pudo comparar con tu archivo."
R_INGRESOS = "El reporte de ingresos no coincide con ninguna posición analizada."


class _FakeSt:
    def __init__(self):
        self.out = []
        self.session_state = {"_wizard_pos_confirmed": True}

    def markdown(self, h, **k):
        self.out.append(h)

    def caption(self, t, **k):
        pass

    def expander(self, titulo, **k):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def html(self):
        return " ".join(self.out)


@pytest.fixture
def fake(monkeypatch):
    f = _FakeSt()
    monkeypatch.setattr(validacion, "st", f)
    return f


def _ok():
    return {"history_incomplete": False, "csv_coverage_pct": 100.0,
            "valuation_date": "2026-09-20", "current_price": 17.5}


def _cartera():
    return {"MSTY": _ok(), "SCHB": _ok()}


def _hist(filas, ticker="MSTY"):
    return pd.DataFrame([{"Date": pd.Timestamp(d), "Action": a, "Amount": m, "Ticker": ticker}
                         for d, a, m in filas])


def _form(bruto, anio=2025):
    return {"tax_year": anio, "forms": [
        {"unique_form_id": "1", "income_code": "06", "gross_income": bruto,
         "federal_tax_withheld": round(bruto * 0.3), "withholding_credit": 0.0}]}


def test_sin_fuentes_extra_la_cartera_sana_sigue_en_alta(fake):
    assert _puntuacion_acertividad(_cartera()) == ("Alta", SIN_NADA)
    assert hay_alertas(_cartera()) is False


# --- 1042-S ------------------------------------------------------------------------------

def test_un_1042s_sin_dividendos_que_cruzar_no_da_alta(fake):
    fake.session_state["_wizard_1042s"] = _form(1000.0)
    assert validacion.validacion_1042s(_cartera())["status"] == "no_overlap"
    assert _puntuacion_acertividad(_cartera()) == (SIN_CONTRASTAR, [R_1042S])


def test_un_1042s_sin_anio_no_da_alta_ni_escribe_none(fake):
    cartera = _cartera()
    cartera["MSTY"]["history"] = _hist([("2025-06-01", "Cash Dividend", 1000.0)])
    fake.session_state["_wizard_1042s"] = _form(1000.0, anio=None)
    assert _puntuacion_acertividad(cartera) == (SIN_CONTRASTAR, [R_1042S])
    validacion._render_1042s(cartera)
    assert "None" not in fake.html()
    assert "Dividendo bruto — Tu archivo" in fake.html()
    assert "Sin comparar" in fake.html() and "Sin año en común" not in fake.html()


def test_un_1042s_que_coincide_si_da_alta(fake):
    cartera = _cartera()
    cartera["MSTY"]["history"] = _hist([("2025-06-01", "Cash Dividend", 1000.0)])
    fake.session_state["_wizard_1042s"] = _form(1000.0)
    assert validacion.validacion_1042s(cartera)["status"] == "match"
    assert _puntuacion_acertividad(cartera) == ("Alta", SIN_NADA)
    validacion._render_1042s(cartera)
    assert "Dividendo bruto 2025 — Tu archivo" in fake.html()


# --- Reporte de ingresos -----------------------------------------------------------------

def test_un_reporte_de_ingresos_que_no_cruza_con_nada_no_da_alta(fake):
    fake.session_state["_wizard_income_summary"] = {
        "tickers": {"ZZZ": {"received_total": 50.0}}}
    assert _puntuacion_acertividad(_cartera()) == (SIN_CONTRASTAR, [R_INGRESOS])


def test_basta_una_posicion_validada_contra_ingresos_para_alta(fake):
    cartera = _cartera()
    cartera["MSTY"]["history"] = _hist([("2025-06-01", "Cash Dividend", 100.0)])
    fake.session_state["_wizard_income_summary"] = {
        "tickers": {"MSTY": {"received_total": 100.0}}}
    assert _puntuacion_acertividad(cartera) == ("Alta", SIN_NADA)


def test_una_alerta_de_ingresos_sigue_siendo_media(fake):
    cartera = _cartera()
    cartera["MSTY"]["history"] = _hist([("2025-06-01", "Cash Dividend", 100.0)])
    fake.session_state["_wizard_income_summary"] = {
        "tickers": {"MSTY": {"received_total": 5000.0}}}
    nivel, razones = _puntuacion_acertividad(cartera)
    assert nivel == "Media"
    assert R_INGRESOS not in razones


# --- Fondo sin precios -------------------------------------------------------------------

@pytest.mark.parametrize("rotos, razon", [
    (["CONY"], "1 posición sin precios: no se pudo revisar."),
    (["CONY", "NVDY"], "2 posiciones sin precios: no se pudieron revisar."),
])
def test_un_fondo_sin_precios_no_da_alta(fake, rotos, razon):
    cartera = dict(_cartera(), **{t: {"error": "sin precios"} for t in rotos})
    assert _puntuacion_acertividad(cartera) == (SIN_CONTRASTAR, [razon])


def test_un_excluido_no_cuenta_como_fondo_sin_precios(fake):
    cartera = dict(_cartera(), ZZZ={"skipped": True, "reason": "not_known_etf",
                                    "error": "x"})
    assert _puntuacion_acertividad(cartera)[0] == "Alta"


def test_las_tres_causas_se_listan_juntas(fake):
    cartera = dict(_cartera(), CONY={"error": "sin precios"})
    fake.session_state["_wizard_1042s"] = _form(1000.0)
    fake.session_state["_wizard_income_summary"] = {
        "tickers": {"ZZZ": {"received_total": 50.0}}}
    assert _puntuacion_acertividad(cartera) == (
        SIN_CONTRASTAR,
        [R_1042S, R_INGRESOS, "1 posición sin precios: no se pudo revisar."])


def test_una_discrepancia_real_manda_sobre_sin_contrastar(fake):
    cartera = dict(_cartera(), CONY={"error": "sin precios"})
    cartera["MSTY"]["history"] = _hist([("2025-06-01", "Cash Dividend", 100.0)])
    fake.session_state["_wizard_1042s"] = _form(1000.0)
    nivel, razones = _puntuacion_acertividad(cartera)
    assert nivel == "Media"
    assert not any("sin precios" in r for r in razones)


# --- Dónde se ve -------------------------------------------------------------------------

def test_la_cabecera_lo_trata_como_aviso(fake):
    cartera = dict(_cartera(), CONY={"error": "sin precios"})
    assert nivel_confiabilidad(cartera) == SIN_CONTRASTAR
    assert hay_alertas(cartera) is True


def test_el_panel_lo_escribe_con_su_clase(fake, monkeypatch):
    monkeypatch.setattr(validacion, "_render_calidad_datos", lambda r: None)
    monkeypatch.setattr(validacion, "_render_notas_tecnicas", lambda r: None)
    monkeypatch.setattr(validacion, "_render_excluidos", lambda r: None)
    validacion.render_validacion_datos(dict(_cartera(), CONY={"error": "sin precios"}))
    html = fake.html()
    assert '<div class="vd-val-score vd-val-score-sin-contrastar">' in html
    assert '<p class="vd-val-score-etiqueta">Confiabilidad sin contrastar</p>' in html
    assert "1 posición sin precios: no se pudo revisar." in html
    assert "Sin discrepancias" not in html


def test_cada_nivel_tiene_su_regla_de_estilo():
    for nivel in ("Alta", "Media", "Baja", SIN_CONTRASTAR):
        assert f".vd-val-score-{clase_nivel(nivel)} .vd-val-score-etiqueta" \
            in validacion.ESTILOS_VALIDACION, nivel
    assert " " not in clase_nivel(SIN_CONTRASTAR)


# --- Comparación: el 30 % sin país -------------------------------------------------------

_LEER_NOTAS = "() => document.getElementById('cmpNotes').textContent"


@pytest.fixture(scope="module")
def notas():
    sync_api = pytest.importorskip("playwright.sync_api")
    from test_logic import _trg_real_fake_frames, _trg_real_patch
    try:
        pw = sync_api.sync_playwright().start()
        nav = pw.chromium.launch()
    except Exception as error:
        pytest.skip(f"Chromium no disponible: {error}")
    parche = pytest.MonkeyPatch()
    try:
        _trg_real_patch(parche, _trg_real_fake_frames())
        montado = []
        parche.setattr(componentes, "_montar", lambda html, alto: montado.append(html))
        out = {}
        for clave, tasa, pais in (("sin_pais", 30.0, None), ("con_pais", 10.0, "México")):
            datos = trg_real_data({"MSTY": {"market_value": 500}}, tasa_pct=tasa, pais=pais)
            componentes.render_comparacion_real(datos, "Claro")
            pagina = nav.new_page(viewport={"width": 1100, "height": 1400})
            errores = []
            pagina.on("pageerror", lambda e: errores.append(str(e)))
            pagina.set_content("<!doctype html>" + montado[-1])
            pagina.wait_for_timeout(300)
            out[clave] = (pagina.evaluate(_LEER_NOTAS), errores)
            pagina.close()
        return out
    finally:
        parche.undo()
        nav.close()
        pw.stop()


def test_sin_pais_el_30_se_dice_que_es_supuesto(notas):
    texto, errores = notas["sin_pais"]
    assert errores == []
    assert "Tasa supuesta: no has declarado tu país de residencia" in texto
    assert "usan el 30%, la tasa máxima" in texto
    assert "Tu tasa:" not in texto


def test_con_pais_no_se_habla_de_tasa_supuesta(notas):
    texto, errores = notas["con_pais"]
    assert errores == []
    assert "Tasa supuesta" not in texto
    assert "Tu tasa: 10% por tu residencia declarada (México)" in texto
