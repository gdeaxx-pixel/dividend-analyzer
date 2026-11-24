"""El texto que viene del archivo del cliente se pinta como texto, nunca como etiquetas.

Un símbolo o un concepto del CSV puede traer `<img …>`: la pantalla de validación lo
interpolaba en `st.markdown(unsafe_allow_html=True)` y el Cash flow en `innerHTML`. Aquí se
mete esa cadena por cada camino y se comprueba que llega escapada.
"""
import json
import re

import pytest

import logic
from test_cascada_eje import STATS_SCHB
from ui import componentes, validacion
from ui.adapters import cashflow_data

HOSTIL = '<img src=x onerror="window.__colado=1">'
ESCAPADO = "&lt;img src=x onerror=&quot;window.__colado=1&quot;&gt;"


class _FakeSt:
    def __init__(self):
        self.out = []
        self.session_state = {}

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


def _sin_etiqueta_colada(html: str, veces: int = 1):
    assert "<img" not in html, html
    assert html.count(ESCAPADO) >= veces, html


def test_el_simbolo_excluido_sale_como_texto(fake):
    validacion._render_lista_excluidos({HOSTIL: {"skipped": True, "reason": "not_known_etf"}})
    _sin_etiqueta_colada(fake.html())
    assert f"<b>{ESCAPADO}</b>" in fake.html()


def test_la_tarjeta_de_calidad_escapa_simbolo_razon_y_accion(fake, monkeypatch):
    monkeypatch.setattr(logic, "classify_tickers", lambda t: {})
    monkeypatch.setattr(logic, "assess_data_quality", lambda r, c: {HOSTIL: {
        "level": "unreliable", "reason": f"razón de {HOSTIL}", "action": f"Exporta {HOSTIL}"}})
    validacion._render_calidad_datos({HOSTIL: {}})
    html = fake.html()
    _sin_etiqueta_colada(html, veces=3)
    assert f"razón de {ESCAPADO}" in html
    assert f"→ Exporta {ESCAPADO}" in html
    assert html.count("<span style=") == 1


def test_la_validacion_cruzada_de_ingresos_escapa_simbolo_y_nota(fake, monkeypatch):
    monkeypatch.setattr(logic, "classify_tickers", lambda t: {})
    monkeypatch.setattr(logic, "assess_data_quality", lambda r, c: {})
    monkeypatch.setattr(logic, "reconcile_income", lambda r, i: {HOSTIL: {
        "status": HOSTIL, "badge": "warn", "csv_total": None, "income_total": 12.5,
        "csv_in_window": None, "note": f"nota de {HOSTIL}"}})
    fake.session_state["_wizard_income_summary"] = {"tickers": {HOSTIL: {}}}
    validacion._render_calidad_datos({})
    html = fake.html()
    _sin_etiqueta_colada(html, veces=3)
    assert f"nota de {ESCAPADO}" in html
    assert "Broker recibido: <b>$12.50</b>" in html


def test_la_tabla_de_eventos_escapa_el_simbolo(fake, monkeypatch):
    monkeypatch.setattr(logic, "assess_ticker_quality", lambda r, t: {"level": "ok"})
    validacion._render_notas_tecnicas({HOSTIL: {
        "splits_detected": [{"date": HOSTIL, "ratio": 0.1}]}})
    html = fake.html()
    _sin_etiqueta_colada(html, veces=2)
    assert f'vd-pie-celda-ticker">{ESCAPADO}</td>' in html
    assert f'vd-pie-celda-fecha">{ESCAPADO}</td>' in html


def test_el_texto_normal_no_cambia(fake):
    validacion._render_lista_excluidos({"SCHB": {"skipped": True, "reason": "not_known_etf"}})
    assert "— <b>SCHB</b> · " in fake.html()
    assert "No reconocido como ETF de largo plazo" in fake.html()


# --- Cash flow: la etiqueta de «otros movimientos» sale del concepto del CSV -------------

CONCEPTO = "Cash In Lieu " + HOSTIL
DATOS = cashflow_data(dict(STATS_SCHB, misc_cash_total=30.0,
                           misc_cash_breakdown={CONCEPTO: 30.0}), "SCHB")

_LEER = """() => {
  const sq = document.querySelector('#grid .sq.q-otros');
  if (sq) sq.dispatchEvent(new MouseEvent('mousemove', {bubbles: true, clientX: 50, clientY: 50}));
  if (sq) sq.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true, clientX: 50, clientY: 50}));
  const tip = document.querySelector('.tip, #tip');
  return {
    imgs: document.querySelectorAll('img').length,
    colado: window.__colado === 1,
    texto: document.body.textContent,
    hayOtros: !!sq,
    tip: tip ? tip.textContent : null,
  };
}"""


def test_el_adaptador_entrega_el_concepto_tal_cual():
    """Si el adaptador lo limpiara, la prueba del navegador no probaría el escape."""
    assert list(DATOS["OTROS_DETALLE"]) == [CONCEPTO]


@pytest.fixture(scope="module")
def pasos():
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        with sync_api.sync_playwright() as pw:
            nav = pw.chromium.launch()
            out = {}
            for paso in range(len(DATOS["STEP_LABELS"])):
                html = componentes._con_tema(componentes._plantilla("cashflow.html"), "Claro")
                html = (html.replace("{{DATA_JSON}}", json.dumps(DATOS, ensure_ascii=False))
                            .replace("{{PASO}}", str(paso)))
                pagina = nav.new_page(viewport={"width": 860, "height": 1400})
                pagina.set_content("<!doctype html>" + html)
                pagina.wait_for_timeout(300)
                out[paso] = pagina.evaluate(_LEER)
                pagina.close()
            nav.close()
            return out
    except Exception as error:
        pytest.skip(f"Chromium no disponible: {error}")


def test_el_concepto_del_csv_no_crea_etiquetas_en_ningun_paso(pasos):
    for paso, leido in pasos.items():
        assert leido["imgs"] == 0, paso
        assert not leido["colado"], paso


def test_el_concepto_se_lee_entero_como_texto(pasos):
    """Sin esto la prueba de arriba pasaría también si la etiqueta dejara de pintarse."""
    ultimo = pasos[max(pasos)]
    assert ultimo["hayOtros"]
    assert len(re.findall(re.escape(CONCEPTO), ultimo["texto"])) >= 3, ultimo["texto"][-900:]
    assert ultimo["tip"] is not None and CONCEPTO in ultimo["tip"], ultimo["tip"]
