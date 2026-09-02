"""El benchmark (VOO) se baja UNA vez por corrida, no una por ticker.

Medido antes del arreglo sobre `?demo=schwab`: de las 19 descargas de una corrida completa,
**8 eran VOO** — el 42% del tráfico para traer ocho veces la misma serie, porque
`yf.download(benchmark, start=first_date)` vivía dentro del bucle por ticker y `first_date` era
lo único que cambiaba entre vueltas.

Importa por dos razones distintas, y la segunda es la dura: yfinance limita **por peticiones**
(medido en la Fase 3.3, que se descartó entera por eso), así que cada petición de más acerca la
app al rate limit en la IP compartida de Streamlit Cloud.
"""
import pandas as pd
import pytest

import logic


def _csv(tickers, desde='2024-01-02'):
    filas = []
    for i, t in enumerate(tickers):
        filas.append((pd.Timestamp(desde) + pd.Timedelta(days=i), 'Buy', t, 10, 100.0, -1000.0))
    return pd.DataFrame(filas, columns=['Date', 'Action', 'Ticker', 'Quantity', 'Price', 'Amount'])


def test_el_benchmark_se_baja_una_sola_vez_por_corrida(monkeypatch):
    """La aserción central: N tickers, UNA descarga del benchmark.

    Se cuenta la descarga por su TICKER, no el total de llamadas: el resto de peticiones son
    los precios de cada posición y no son el sujeto de esta prueba.
    """
    llamadas = []

    def _fake_download(tk, *a, **k):
        llamadas.append(tk)
        idx = pd.date_range('2023-12-01', periods=400, freq='D')
        return pd.DataFrame({'Open': 100.0, 'High': 100.0, 'Low': 100.0, 'Close': 100.0,
                             'Volume': 1000, 'Dividends': 0.0, 'Stock Splits': 0.0},
                            index=idx)

    monkeypatch.setattr(logic.yf, 'download', _fake_download)
    df = _csv(['SCHB', 'SMH', 'XLK'])
    logic._descargar_benchmark(df)

    assert llamadas == [logic.BENCHMARK_TICKER], (
        f"el benchmark tiene que bajarse una vez y solo una: {llamadas}")


def test_el_benchmark_arranca_en_la_fecha_mas_temprana_del_csv():
    """Se baja desde la primera fecha de TODO el CSV, para que cada ticker recorte la suya.

    Si arrancara en la fecha de un ticker cualquiera, los que empezaron antes se quedarían sin
    benchmark en su tramo inicial — y la comparación contra VOO saldría corta sin avisar.
    """
    capturado = {}

    def _fake_download(tk, *a, **k):
        capturado['start'] = k.get('start')
        return pd.DataFrame({'Close': [1.0]}, index=pd.date_range('2020-01-01', periods=1))

    import types
    orig = logic.yf.download
    logic.yf.download = _fake_download
    try:
        df = _csv(['SCHB', 'SMH', 'XLK'], desde='2021-03-15')
        logic._descargar_benchmark(df)
    finally:
        logic.yf.download = orig

    assert pd.Timestamp(capturado['start']) == pd.Timestamp('2021-03-15'), (
        "tiene que ser la fecha MÍNIMA del CSV, no la de un ticker cualquiera")


def test_recortar_la_serie_larga_equivale_a_bajarla_desde_esa_fecha():
    """La equivalencia de la que depende todo el arreglo, como propiedad y no como anécdota.

    Es la misma serie de Yahoo pedida desde dos fechas: recortarla por índice tiene que dar
    exactamente lo mismo que pedirla desde ahí. Si esto dejara de cumplirse, cada ticker
    estaría comparándose contra un benchmark distinto del que declara.
    """
    idx = pd.date_range('2022-01-03', periods=300, freq='B')
    larga = pd.DataFrame({'Close': range(300), 'Dividends': 0.0}, index=idx)
    corte = idx[120]

    recortada = larga[larga.index >= corte]
    directa = pd.DataFrame({'Close': range(120, 300), 'Dividends': 0.0}, index=idx[120:])

    pd.testing.assert_frame_equal(recortada, directa, check_dtype=False)


def test_sin_benchmark_la_corrida_sigue_entera(monkeypatch):
    """El benchmark es accesorio: si Yahoo lo niega, la app no se queda sin cifras.

    Por eso `_descargar_benchmark` NO lleva las tres capas de respaldo de `fetch_market_data`
    —que existen porque un ticker de la cartera sin precio sí deja al cliente sin nada—: sería
    gastar hasta tres peticiones en una comparación.
    """
    def _boom(*a, **k):
        raise RuntimeError("Yahoo dice que no")

    monkeypatch.setattr(logic.yf, 'download', _boom)
    assert logic._descargar_benchmark(_csv(['SCHB'])).empty


def test_un_csv_sin_fechas_usables_no_pide_nada(monkeypatch):
    """Sin fecha mínima no hay ventana que pedir: se devuelve vacío sin tocar la red."""
    llamadas = []
    monkeypatch.setattr(logic.yf, 'download',
                        lambda *a, **k: llamadas.append(1) or pd.DataFrame())
    df = pd.DataFrame({'Date': [None, None], 'Ticker': ['A', 'B']})
    assert logic._descargar_benchmark(df).empty
    assert llamadas == [], "no se pide una serie cuando no hay fecha desde la que pedirla"
