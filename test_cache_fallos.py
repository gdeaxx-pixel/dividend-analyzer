"""Un fallo pasajero no se queda guardado; un archivo de datos que cambia se relee.

Todo sin red: el mercado y la sesión HTTP son dobles, y cada prueba cuenta las llamadas
para distinguir «volvió a pedir» de «sirvió lo guardado».
"""
import os

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import logic

BASE = os.path.dirname(os.path.abspath(__file__))


def _mercado(n=60, inicio='2024-01-02'):
    idx = pd.bdate_range(inicio, periods=n)
    return pd.DataFrame({'Close': [100.0] * n, 'Dividends': 0.0, 'Stock Splits': 0.0}, index=idx)


def _cartera(tickers=('VTI',)):
    filas = [dict(Date='2024-01-02', Action='Buy', Ticker=t, Quantity=10.0, Price=100.0,
                  Amount=-1000.0) for t in tickers]
    df = pd.DataFrame(filas)
    df['Date'] = pd.to_datetime(df['Date'])
    return df


class _Mercado:
    def __init__(self):
        self.caidos = set()
        self.llamadas = []

    def __call__(self, ticker, start_date):
        self.llamadas.append(ticker)
        if ticker in self.caidos or '*' in self.caidos:
            return pd.DataFrame(), "API Rate Limited & Scraper failed."
        return _mercado(), None


@pytest.fixture
def mercado(monkeypatch):
    m = _Mercado()
    monkeypatch.setattr(logic, 'fetch_market_data', m)
    monkeypatch.setattr(logic, '_descargar_benchmark', lambda d, ticker='VOO': _mercado())
    logic.analyze_portfolio.clear()
    yield m
    logic.analyze_portfolio.clear()


# ── analyze_portfolio ────────────────────────────────────────────────────────────────────

def test_sin_precios_no_se_guarda_y_la_siguiente_llamada_los_vuelve_a_pedir(mercado):
    df = _cartera()
    mercado.caidos = {'*'}
    r1 = logic.analyze_portfolio(df, version='T8_caido')
    assert r1['VTI']['error'].startswith('No market data found')
    assert logic.tiene_fallo_de_mercado(r1)

    mercado.caidos = set()
    r2 = logic.analyze_portfolio(df, version='T8_caido')
    assert 'error' not in r2['VTI']
    assert r2['VTI']['market_value'] == pytest.approx(1000.0)
    assert not logic.tiene_fallo_de_mercado(r2)


def test_el_resultado_bueno_si_se_guarda(mercado):
    df = _cartera()
    r1 = logic.analyze_portfolio(df, version='T8_bueno')
    pedidos = len(mercado.llamadas)
    assert pedidos >= 1
    mercado.caidos = {'*'}
    r2 = logic.analyze_portfolio(df, version='T8_bueno')
    assert len(mercado.llamadas) == pedidos
    assert r2['VTI']['market_value'] == r1['VTI']['market_value']


def test_un_solo_fondo_sin_precios_basta_para_no_guardar(mercado):
    df = _cartera(('VTI', 'VOO'))
    mercado.caidos = {'VOO'}
    r1 = logic.analyze_portfolio(df, version='T8_parcial')
    assert 'error' not in r1['VTI'] and 'error' in r1['VOO']
    mercado.caidos = set()
    r2 = logic.analyze_portfolio(df, version='T8_parcial')
    assert 'error' not in r2['VOO']


def test_serie_sin_cierres_tambien_cuenta_como_fallo_de_mercado(mercado, monkeypatch):
    hueco = _mercado()
    hueco['Close'] = float('nan')
    monkeypatch.setattr(logic, 'fetch_market_data', lambda t, s: (hueco.copy(), None))
    r = logic.analyze_portfolio(_cartera(), version='T8_nan')
    assert r['VTI']['error'].startswith('No usable close price')
    assert logic.tiene_fallo_de_mercado(r)


def test_un_descarte_de_la_cartera_no_es_fallo_de_mercado():
    assert not logic.tiene_fallo_de_mercado(
        {'AAA': {'skipped': True, 'reason': 'not_known_etf'}, 'BBB': {'market_value': 1.0},
         'CCC': {'error': 'otra cosa'}, 'DDD': None})
    assert not logic.tiene_fallo_de_mercado(None)
    assert logic.tiene_fallo_de_mercado({'AAA': {'error': 'No market data found: x'}})


def test_la_funcion_publica_conserva_clear_y_el_acceso_sin_cache(mercado):
    df = _cartera()
    logic.analyze_portfolio(df, version='T8_clear')
    pedidos = len(mercado.llamadas)
    logic.analyze_portfolio.clear()
    logic.analyze_portfolio(df, version='T8_clear')
    assert len(mercado.llamadas) > pedidos
    pedidos = len(mercado.llamadas)
    logic.analyze_portfolio.__wrapped__(df, version='T8_clear')
    assert len(mercado.llamadas) > pedidos
    pedidos = len(mercado.llamadas)
    logic.analyze_portfolio.__wrapped__(df, version='T8_clear')
    assert len(mercado.llamadas) > pedidos


# ── respaldo por scraping ────────────────────────────────────────────────────────────────

_FILA = "<tr><td>Nov 20, 2026</td><td>1</td><td>2</td><td>0.5</td><td>1.5</td><td>1.5</td><td>1,000</td></tr>"


class _Sesion:
    def __init__(self):
        self.respuestas = []
        self.pedidos = 0

    def get(self, url, timeout=None):
        self.pedidos += 1
        estado, texto = self.respuestas.pop(0)
        if estado is None:
            raise ConnectionError("sin red")
        return type("R", (), {"status_code": estado, "text": texto})()


@pytest.fixture
def sesion(monkeypatch):
    s = _Sesion()
    monkeypatch.setattr(logic, 'get_session', lambda: s)
    logic.fetch_data_from_html.clear()
    yield s
    logic.fetch_data_from_html.clear()


@pytest.mark.parametrize("fallo", [(503, ""), (200, "pagina sin tabla"), (None, "")])
def test_el_respaldo_vacio_no_se_guarda(sesion, fallo):
    sesion.respuestas = [fallo, (200, "Historical Data <table>" + _FILA + "</table>")]
    assert logic.fetch_data_from_html('ZZZT').empty
    df = logic.fetch_data_from_html('ZZZT')
    assert sesion.pedidos == 2
    assert len(df) == 1 and df['Close'].iloc[0] == 1.5 and df['Volume'].iloc[0] == 1000


def test_el_respaldo_con_filas_si_se_guarda(sesion):
    sesion.respuestas = [(200, "Historical Data <table>" + _FILA + "</table>")]
    assert len(logic.fetch_data_from_html('ZZZT')) == 1
    assert len(logic.fetch_data_from_html('ZZZT')) == 1
    assert sesion.pedidos == 1


# ── archivos de datos que cambian con el proceso vivo ────────────────────────────────────

_YAMLS = [
    ('load_roc_19a', '_ROC19A_PATH', '_ROC19A_CACHE', "AAA:\n  weighted_pct: {v}\n", lambda d: d['AAA']['weighted_pct']),
    ('load_roc_ici', '_ROCICI_PATH', '_ROCICI_CACHE', "AAA:\n  2025:\n    roc_pct: {v}\n", lambda d: d['AAA'][2025]['roc_pct']),
    ('load_distribution_rate', '_DISTRATE_PATH', '_DISTRATE_CACHE', "AAA:\n  rate_pct: {v}\n", lambda d: d['AAA']['rate_pct']),
    ('load_roc_health_history', '_ROCHEALTH_PATH', '_ROCHEALTH_CACHE', "AAA:\n  - roc_pct: {v}\n", lambda d: d['AAA'][0]['roc_pct']),
]


@pytest.fixture(params=_YAMLS, ids=[y[0] for y in _YAMLS])
def yaml_vivo(request, tmp_path, monkeypatch):
    cargar, ruta_attr, cache_attr, plantilla, leer = request.param
    ruta = tmp_path / "dato.yaml"
    monkeypatch.setattr(logic, ruta_attr, str(ruta))
    cache = getattr(logic, cache_attr)
    guardado = dict(cache)
    cache.clear()

    def escribir(v, mtime=None):
        ruta.write_text(plantilla.format(v=v), encoding='utf-8')
        if mtime is not None:
            os.utime(ruta, (mtime, mtime))

    yield escribir, lambda: leer(getattr(logic, cargar)()), cache, ruta, getattr(logic, cargar)
    cache.clear()
    cache.update(guardado)


def test_el_archivo_cambiado_se_relee(yaml_vivo):
    escribir, valor, cache, ruta, cargar = yaml_vivo
    escribir(40.0, mtime=1_700_000_000)
    assert valor() == 40.0
    escribir(77.5, mtime=1_700_000_500)
    assert valor() == 77.5


def test_mismo_tamano_y_otra_fecha_tambien_se_relee(yaml_vivo):
    escribir, valor, cache, ruta, cargar = yaml_vivo
    escribir(40.0, mtime=1_700_000_000)
    assert valor() == 40.0
    escribir(77.0, mtime=1_700_000_500)
    assert valor() == 77.0


def test_sin_cambio_en_disco_no_se_vuelve_a_abrir(yaml_vivo, monkeypatch):
    escribir, valor, cache, ruta, cargar = yaml_vivo
    escribir(40.0, mtime=1_700_000_000)
    assert valor() == 40.0
    antes = cargar()
    monkeypatch.setattr(logic._yaml, 'safe_load', lambda fh: pytest.fail("releyó sin cambio"))
    assert cargar() is antes


def test_el_archivo_que_desaparece_deja_de_servirse(yaml_vivo):
    escribir, valor, cache, ruta, cargar = yaml_vivo
    escribir(40.0, mtime=1_700_000_000)
    assert valor() == 40.0
    ruta.unlink()
    assert cargar() == {}


def test_el_archivo_que_aparece_despues_se_lee(yaml_vivo):
    escribir, valor, cache, ruta, cargar = yaml_vivo
    assert cargar() == {}
    escribir(40.0, mtime=1_700_000_000)
    assert valor() == 40.0


def test_un_cache_rellenado_a_mano_se_respeta(yaml_vivo):
    escribir, valor, cache, ruta, cargar = yaml_vivo
    escribir(40.0, mtime=1_700_000_000)
    cache.clear()
    cache.update({'_loaded': True, 'data': {'MANO': {}}})
    assert cargar() == {'MANO': {}}


# ── la sesión no se queda con el fallo ───────────────────────────────────────────────────

_SCRIPT = """
import sys
sys.path.insert(0, {path!r})
import streamlit as st
from ui import vistas

st.session_state["_salida"] = vistas.obtener_resultados()
""".format(path=BASE)


def test_la_pantalla_reintenta_pasada_la_espera_y_no_antes(mercado, monkeypatch):
    import ui.vistas as vistas
    reloj = [1000.0]
    monkeypatch.setattr(vistas, '_ahora', lambda: reloj[0])

    at = AppTest.from_string(_SCRIPT, default_timeout=40)
    at.session_state["_wizard_df_clean"] = _cartera()
    mercado.caidos = {'*'}
    at.run()
    assert at.exception == []
    assert 'error' in at.session_state["_salida"]['VTI']
    assert at.session_state[vistas._REINTENTO_PRECIOS] == 1000.0 + vistas._ESPERA_REINTENTO_S

    mercado.caidos = set()
    pedidos = len(mercado.llamadas)
    reloj[0] = 1000.0 + vistas._ESPERA_REINTENTO_S - 1
    at.run()
    assert len(mercado.llamadas) == pedidos
    assert 'error' in at.session_state["_salida"]['VTI']

    reloj[0] = 1000.0 + vistas._ESPERA_REINTENTO_S
    at.run()
    assert at.exception == []
    assert 'error' not in at.session_state["_salida"]['VTI']
    assert at.session_state[vistas._REINTENTO_PRECIOS] is None

    pedidos = len(mercado.llamadas)
    reloj[0] += 10_000
    at.run()
    assert len(mercado.llamadas) == pedidos
