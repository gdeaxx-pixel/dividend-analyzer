"""Tests para price_cache.py — Fase 3.2 (cache de historia con refresco automatico).

Dos cosas se verifican aqui, no solo que el loader "funcione":

1. El gate de reconciliacion de la Fase 3.1 (MSTY vs extracto real de IB, `test_backtest.py`)
   debe reproducirse leyendo splits/dividendos DESDE EL CACHE, no solo desde yfinance en vivo
   — ese es el criterio de aceptacion principal de la 3.2 (ver plan). Si el cache rompe la
   reconciliacion, el cache esta mal aunque el loader "no truene".
2. Sabotaje: corromper el cache a proposito (desalinear el split de MSTY en `_splits.yaml`) y
   confirmar que el gate FALLA con esos datos corrompidos — un verde no prueba que el test
   ejercite la ruta correcta (`feedback_test-tocado-para-desbloquear-deploy`). El archivo se
   revierte SIEMPRE (incluso si el `with` explota) y se verifica con `diff` que quedo
   byte-a-byte identico, mismo patron que `test_backtest.py::_sabotaged_backtest_module`.

Todo lo que toca red (yfinance, cuando el cache esta ausente/vencido) hace `pytest.skip` limpio
si la red/API falla — un FAIL aqui es siempre una regresion de LOGICA, nunca un outage.
"""
import contextlib
import os
import subprocess
import sys

import pandas as pd
import pytest
import yaml

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import backtest as bt        # noqa: E402
import logic                 # noqa: E402
import price_cache as pc     # noqa: E402

REAL = os.environ.get("DIVIDEND_REAL_EXAMPLES_DIR", os.path.join(BASE, "real_examples"))
MSTY_CSV = os.path.join(
    REAL, "interactive_brokers_data", "1",
    "U15179613.TRANSACTIONS.20240820.20260514.csv",
)
SPLITS_PATH = pc.SPLITS_PATH
META_PATH = pc.META_PATH

# Misma tolerancia y misma justificacion que test_backtest.py::GATE_TOLERANCE_PCT: el residuo
# real observado (cache o vivo, es la MISMA serie de yfinance en el momento de generar el
# cache) es 0.013% ($0.97 sobre $7,224.59) — ruido de redondeo de centavos en la tasa/accion
# publicada. 0.5% deja ~38x de margen sin esconder una regresion real.
GATE_TOLERANCE_PCT = 0.5

# Cifras "que no pueden moverse", MEDIDAS contra el snapshot congelado
# `knowledge/price_cache_frozen/` (2026-08-23, capital inicial $10,000):
# (ticker, inception, price_return_pct, ConDRIP, SinDRIP). La ENTRADA esta congelada y
# versionada — el cron no la toca — asi que estas salidas son deterministas para siempre.
# Tolerancia 0.2pp: con la entrada fija cualquier desviacion es una regresion del motor o del
# snapshot, no deriva de mercado. Antes se comparaban contra el caché vivo y el refresh
# semanal las rompia sin que nadie rompiera nada (Regla 6).
FROZEN_FIGURES = [
    ("NVDY", "2023-05-11", -37.4, 347.7, 166.9),
    ("TSLY", "2022-11-23", -88.7, 37.1, 8.2),
    ("CONY", "2023-08-15", -89.2, 44.7, 81.8),
    ("MSTY", "2024-02-22", -86.4, 45.8, 136.0),
]
FROZEN_TOLERANCE_PCT = 0.2


def _require_msty_csv():
    if not os.path.exists(MSTY_CSV):
        pytest.skip(f"real_examples no disponible: {MSTY_CSV}")


def _require_cache(ticker):
    if ticker not in pc.cache_coverage():
        pytest.skip(f"knowledge/price_cache no tiene entrada para {ticker} — correr "
                     f"fetch_price_cache.py {ticker} primero")


def _msty_position_and_ground_truth_from_cache():
    """Igual que `test_backtest.py::_msty_position_and_ground_truth`, pero los splits salen
    de `price_cache.load_splits` (cache en disco) en vez de `bt.fetch_splits` (vivo)."""
    with open(MSTY_CSV, "rb") as f:
        raw = f.read()
    df = logic.parse_ibkr_csv(raw)
    msty = df[df["Ticker"] == "MSTY"].copy()
    msty["Date"] = pd.to_datetime(msty["Date"])

    tx = msty[msty["Action"].isin(["Buy", "Sell"])][["Date", "Quantity"]]
    splits_result = pc.load_splits("MSTY")
    if splits_result.source not in ("cache", "cache_stale_fallback"):
        pytest.skip(f"price_cache.load_splits('MSTY') no uso el cache (source="
                     f"{splits_result.source!r}) — el fixture de cache no esta poblado")

    position = bt.shares_from_transactions(tx, splits_result.splits)
    csv_gross = msty[msty["Action"] == "Dividend"]["Amount"].astype(float).sum()
    return position, msty["Date"].min(), msty["Date"].max(), csv_gross, splits_result


# ── GATE: reconciliacion contra el extracto real de IB, leyendo desde el cache ──────────────

def test_gate_msty_reconciles_against_real_ib_statement_using_cache():
    """El gate central de la Fase 3.2. Ver docstring del modulo — debe reproducir el mismo
    resultado que `test_backtest.py::test_gate_msty_reconciles_against_real_ib_statement`
    (motor vivo), pero leyendo splits Y dividendos desde `knowledge/price_cache/`."""
    _require_msty_csv()
    _require_cache("MSTY")
    position, first, last, csv_gross, splits_result = (
        _msty_position_and_ground_truth_from_cache())

    assert csv_gross == pytest.approx(7224.59, abs=0.01)
    assert position.iloc[-1] == pytest.approx(250.0, abs=0.01), (
        "posicion final reconstruida con splits del CACHE deberia ser 250 (igual que con "
        "splits en vivo) — si esto falla, el split de MSTY en _splits.yaml esta mal"
    )

    hist_result = pc.load_history("MSTY", start=None, end=last)
    if hist_result.source not in ("cache", "cache_stale_fallback"):
        pytest.skip(f"price_cache.load_history('MSTY') no uso el cache (source="
                     f"{hist_result.source!r})")
    dividends = hist_result.history["Dividends"]

    engine_gross, detail = bt.dividends_for_position(
        "MSTY", position, start=first, end=last, dividends=dividends)

    assert len(detail) > 30, (
        f"muy pocos eventos de dividendo reconstruidos desde el cache ({len(detail)}) — "
        "sospechoso de que el parquet no cubre el rango completo"
    )

    diff_pct = abs(engine_gross - csv_gross) / csv_gross * 100.0
    assert diff_pct <= GATE_TOLERANCE_PCT, (
        f"GATE FALLIDO (cache): motor reconstruyo ${engine_gross:,.2f} bruto vs "
        f"${csv_gross:,.2f} real de IB ({diff_pct:.3f}% de diferencia, tolerancia "
        f"{GATE_TOLERANCE_PCT}%) leyendo desde knowledge/price_cache/ — el cache esta mal, "
        "NO avanzar a UI (Fase 3.3) sobre estos datos."
    )
    print(f"[gate cache] MSTY reconcilia a {diff_pct:.3f}% (${engine_gross:,.2f} vs "
          f"${csv_gross:,.2f}) leyendo splits+dividendos de knowledge/price_cache/ "
          f"(cache_asof={splits_result.cache_asof}, history_asof={hist_result.cache_asof})")


# ── Cifras que no pueden moverse (verificadas por Opus, ver docstring del modulo) ───────────

@pytest.mark.parametrize("ticker,inception,price_pct,condrip_pct,sindrip_pct", FROZEN_FIGURES)
def test_frozen_figures_reproduce_from_cache(ticker, inception, price_pct, condrip_pct,
                                              sindrip_pct):
    from conftest import frozen_price_cache
    with frozen_price_cache():
        _require_cache(ticker)
        hist_result = pc.load_history(ticker, start=inception)
        if hist_result.source not in ("cache", "cache_stale_fallback"):
            pytest.skip(f"price_cache.load_history({ticker!r}) no uso el cache (source="
                         f"{hist_result.source!r})")

        r_drip = bt.run_backtest(ticker, inception, initial_capital=10000.0, drip=True,
                                  history=hist_result.history)
        r_cash = bt.run_backtest(ticker, inception, initial_capital=10000.0, drip=False,
                                  history=hist_result.history)

    assert r_drip.price_return_pct == pytest.approx(price_pct, abs=FROZEN_TOLERANCE_PCT), (
        f"{ticker}: retorno de precio desde cache {r_drip.price_return_pct:.1f}% se alejo de "
        f"la cifra congelada {price_pct}% mas de {FROZEN_TOLERANCE_PCT}pp"
    )
    assert r_drip.total_return_pct == pytest.approx(condrip_pct, abs=FROZEN_TOLERANCE_PCT), (
        f"{ticker}: ConDRIP desde cache {r_drip.total_return_pct:.1f}% se alejo de la cifra "
        f"congelada {condrip_pct}% mas de {FROZEN_TOLERANCE_PCT}pp"
    )
    assert r_cash.total_return_pct == pytest.approx(sindrip_pct, abs=FROZEN_TOLERANCE_PCT), (
        f"{ticker}: SinDRIP desde cache {r_cash.total_return_pct:.1f}% se alejo de la cifra "
        f"congelada {sindrip_pct}% mas de {FROZEN_TOLERANCE_PCT}pp"
    )


# ── Loader: fuente declarada, nunca en silencio ──────────────────────────────────────────────

def test_load_history_reports_cache_source_when_fresh():
    _require_cache("MSTY")
    result = pc.load_history("MSTY", start="2024-02-22")
    assert result.source == "cache"
    assert result.stale is False
    assert result.cache_asof is not None
    assert not result.history.empty
    assert list(result.history.columns[:2]) == ["Close", "Dividends"] or (
        "Close" in result.history.columns and "Dividends" in result.history.columns)


def test_load_history_falls_back_to_live_when_ticker_not_cached():
    """Un ticker sin entrada en el cache (nunca corrido `fetch_price_cache.py` para el) debe
    caer a yfinance en vivo y DECLARARLO como source='live', nunca fabricar datos ni fallar en
    silencio."""
    assert "AAPL" not in pc.cache_coverage(), (
        "este test asume que AAPL no esta en el cache de precios (solo YieldMax + "
        "SCHB/XLK/SMH/CHPY) — si se agrego, cambiar el ticker de prueba"
    )
    try:
        result = pc.load_history("AAPL", start="2024-01-01", end="2024-02-01")
    except Exception as e:
        pytest.skip(f"yfinance no disponible: {e}")
    assert result.source == "live"
    assert result.stale is False


def test_load_history_treats_ancient_cache_as_stale():
    """`max_staleness_days=0` fuerza a que CUALQUIER cache (por fresco que sea el de hoy)
    cuente como vencido, ejercitando la rama de fallback a vivo sin tener que esperar 35 dias
    reales ni editar `_meta.yaml`."""
    _require_cache("MSTY")
    try:
        result = pc.load_history("MSTY", start="2024-02-22", max_staleness_days=-1)
    except Exception as e:
        pytest.skip(f"yfinance no disponible: {e}")
    assert result.source in ("live", "cache_stale_fallback"), (
        f"con max_staleness_days=-1 el cache de hoy deberia contar como vencido, pero el "
        f"loader devolvio source={result.source!r}"
    )
    if result.source == "cache_stale_fallback":
        assert result.stale is True


def test_load_history_falls_back_to_stale_cache_when_live_fails(monkeypatch):
    """Cache vencido (max_staleness_days=-1) + yfinance en vivo caido (simulado) debe caer al
    cache vencido como ULTIMO recurso, declarado `source='cache_stale_fallback'` y
    `stale=True` — nunca fabricar datos ni dejar caer la excepcion cuando SI hay algo (viejo)
    que mostrar. Sin este test, la rama de `price_cache.load_history` que atrapa el fallo de
    `bt.fetch_history` nunca se ejercita (verde no prueba cobertura)."""
    _require_cache("MSTY")

    def _boom(*args, **kwargs):
        raise RuntimeError("red caida (simulado)")

    monkeypatch.setattr(pc.bt, "fetch_history", _boom)
    result = pc.load_history("MSTY", start="2024-02-22", max_staleness_days=-1)
    assert result.source == "cache_stale_fallback"
    assert result.stale is True
    assert not result.history.empty, (
        "el fallback a cache vencido debe devolver los datos viejos, no un DataFrame vacio"
    )


def test_load_history_raises_when_no_cache_and_live_fails(monkeypatch):
    """Sin cache y sin red: debe propagar la excepcion tal cual (mismo contrato que
    `backtest.fetch_history`) — nunca inventar una serie vacia o fabricada que se vería como
    dato real corriente abajo."""

    def _boom(*args, **kwargs):
        raise RuntimeError("red caida (simulado)")

    monkeypatch.setattr(pc.bt, "fetch_history", _boom)
    with pytest.raises(RuntimeError, match="red caida"):
        pc.load_history("ZZZNOTCACHED", start="2024-01-01")


# ── Sabotaje: corromper el cache en disco y confirmar que el gate FALLA ─────────────────────

@contextlib.contextmanager
def _sabotaged_splits_yaml(ticker: str, sabotage_ratio: float, sabotage_name: str):
    """Reescribe `knowledge/price_cache/_splits.yaml` en disco, reemplazando TODOS los splits
    de `ticker` por uno solo con `sabotage_ratio` (p.ej. 1.0 = 'el fondo nunca tuvo split' —
    desalinea el cache exactamente como advierte el plan: 'si tu cache guarda una [serie] y no
    la otra, o las guarda de epocas distintas, se corrompe en silencio'). SIEMPRE revierte el
    archivo al salir del bloque `with` y verifica con `diff` que quedo byte-a-byte identico
    (mismo patron que `test_backtest.py::_sabotaged_backtest_module`)."""
    original = open(SPLITS_PATH, "r", encoding="utf-8").read()
    backup_path = SPLITS_PATH + f".sabotage_backup.{sabotage_name}"
    with open(backup_path, "w", encoding="utf-8") as fh:
        fh.write(original)

    try:
        data = yaml.safe_load(original) or {}
        assert ticker in data and data[ticker], (
            f"[{sabotage_name}] {ticker} no tiene splits en _splits.yaml para sabotear — "
            "correr fetch_price_cache.py o actualizar el sabotaje"
        )
        data[ticker] = [{"date": data[ticker][0]["date"], "ratio": sabotage_ratio}]
        sabotaged = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        assert sabotaged != original
        with open(SPLITS_PATH, "w", encoding="utf-8") as fh:
            fh.write(sabotaged)
        yield
    finally:
        with open(SPLITS_PATH, "w", encoding="utf-8") as fh:
            fh.write(original)
        restored = open(SPLITS_PATH, "r", encoding="utf-8").read()
        assert restored == original, (
            f"[{sabotage_name}] _splits.yaml NO quedo identico tras revertir el sabotaje"
        )
        diff_result = subprocess.run(
            ["diff", SPLITS_PATH, backup_path], capture_output=True, text=True)
        assert diff_result.returncode == 0 and diff_result.stdout == "", (
            f"[{sabotage_name}] diff detecto cambios residuales tras revertir:\n"
            f"{diff_result.stdout}"
        )
        os.remove(backup_path)


def test_sabotage_desaligning_cached_split_fails_the_gate():
    """Corrompe a proposito el split de MSTY en el cache (lo reemplaza por ratio=1.0, es
    decir: 'el cache dice que MSTY nunca tuvo split inverso') y confirma que el gate de
    reconciliacion (esta vez leyendo TODO desde el cache) FALLA con una diferencia grande —
    la misma firma que `test_backtest.py::test_sabotage_breaking_split_handling_fails_the_gate`
    pero corrompiendo el dato cacheado en vez de la logica del motor."""
    _require_msty_csv()
    _require_cache("MSTY")

    with _sabotaged_splits_yaml("MSTY", sabotage_ratio=1.0, sabotage_name="msty_split"):
        # price_cache.load_splits cachea nada en memoria (lee el yaml en cada llamada), asi
        # que no hace falta recargar ningun modulo — solo releer.
        splits_result = pc.load_splits("MSTY")
        assert splits_result.source == "cache"
        assert len(splits_result.splits) == 1
        assert float(splits_result.splits.iloc[0]) == pytest.approx(1.0), (
            "el sabotaje no tuvo el efecto esperado sobre el yaml — revisar el patch"
        )

        with open(MSTY_CSV, "rb") as f:
            raw = f.read()
        df = logic.parse_ibkr_csv(raw)
        msty = df[df["Ticker"] == "MSTY"].copy()
        msty["Date"] = pd.to_datetime(msty["Date"])
        tx = msty[msty["Action"].isin(["Buy", "Sell"])][["Date", "Quantity"]]
        csv_gross = msty[msty["Action"] == "Dividend"]["Amount"].astype(float).sum()
        first, last = msty["Date"].min(), msty["Date"].max()

        position = bt.shares_from_transactions(tx, splits_result.splits)
        # con el split "borrado" del cache, la posicion final queda en unidades PRE-split
        # (~1250) en vez de las 250 reales — mismo sintoma que el sabotaje de backtest.py
        assert position.iloc[-1] == pytest.approx(1250.0, abs=1.0), (
            "el sabotaje del cache no tuvo el efecto esperado sobre la posicion reconstruida"
        )

        hist_result = pc.load_history("MSTY", start=None, end=last)
        engine_gross, _ = bt.dividends_for_position(
            "MSTY", position, start=first, end=last,
            dividends=hist_result.history["Dividends"])
        diff_pct = abs(engine_gross - csv_gross) / csv_gross * 100.0

        assert diff_pct > GATE_TOLERANCE_PCT, (
            f"el gate deberia fallar con el split del CACHE corrompido, pero la diferencia "
            f"quedo en {diff_pct:.2f}% (tolerancia {GATE_TOLERANCE_PCT}%) — el sabotaje no "
            "esta ejercitando la rama que protege el gate"
        )
        print(f"[sabotaje cache splits] gate FALLA como se esperaba: {diff_pct:.1f}% de "
              f"diferencia (cache corrompido reconstruyo ${engine_gross:,.2f} vs "
              f"${csv_gross:,.2f} real)")
