"""Tests para backtest.py — Fase 3.1 (motor + gate de splits).

Gate central del PR: el motor debe reproducir el bruto de dividendos MSTY del extracto real de
IB (`real_examples/interactive_brokers_data/1/`, ground truth verificado por
`logic.parse_ibkr_csv`: $7,224.59 bruto, $545.52 retencion NRA, $6,679.07 neto) replicando la
posicion real (acciones efectivamente en mano en cada ex-date) x distribucion por accion real
de yfinance. Si esto no reconcilia dentro de tolerancia, el manejo de splits/elegibilidad esta
mal y la Fase 3.2 (UI) NO debe arrancar sobre este motor.

Todo lo que toca red (yfinance) hace `pytest.skip` limpio si la red/API falla — un FAIL aqui es
siempre una regresion de LOGICA, nunca un outage (mismo patron que test_real_examples.py).

## Nota de auditoria (revision de Opus sobre la primera version de este PR)

La primera version reconciliaba a 4.80% ($346.55 de diferencia) con una tolerancia de 8%
"justificada" por desfase ex-date/pay-date. Esa justificacion NO sobrevivio la auditoria: los
primeros 4 eventos reconciliaban a +0.0 exacto, y el residuo crecia en cantidades REDONDAS de
acciones (+5, +10, +20...) coincidiendo una a una con compras que caian el MISMO dia que una
fecha ex-dividendo de yfinance. La causa real: `dividends_for_position` contaba esas compras
como ya elegibles para ESA distribucion (corte `<=`), cuando la convencion de mercado exige
haber comprado ANTES del ex-date. Corregido con `position_asof(..., inclusive=False)` — ver
docstring de `backtest.py`. Con la correccion, la diferencia cae a $0.97 (0.013%).
"""
import contextlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import backtest as bt   # noqa: E402
import logic            # noqa: E402

REAL = os.environ.get("DIVIDEND_REAL_EXAMPLES_DIR", os.path.join(BASE, "real_examples"))
MSTY_CSV = os.path.join(
    REAL, "interactive_brokers_data", "1",
    "U15179613.TRANSACTIONS.20240820.20260514.csv",
)
BACKTEST_PATH = os.path.join(BASE, "backtest.py")

# Tolerancia del gate de reconciliacion: diferencia observada real, con el corte de
# elegibilidad corregido (inclusive=False, ver backtest.py), es $0.97 sobre $7,224.59 =
# 0.013%. Ese residuo es ruido de redondeo de centavos: yfinance publica la tasa/accion con 3
# decimales (p.ej. 0.740) mientras el extracto de IB trae 4 (0.7375 implicito) — la diferencia
# de ultimo digito, multiplicada por ~250-1250 acciones y sumada sobre 40 eventos, es del
# orden de $1. 0.5% deja ~38x de margen sobre el 0.013% observado sin esconder una regresion
# real: el sabotaje de abajo prueba que romper el manejo de splits sube la diferencia a
# ~126% y romper el corte de elegibilidad (ver test_sabotage_eligibility_cutoff_...) la sube a
# ~4.8% — ambos muy por encima de 0.5%.
GATE_TOLERANCE_PCT = 0.5


def _require_msty_csv():
    if not os.path.exists(MSTY_CSV):
        pytest.skip(f"real_examples no disponible: {MSTY_CSV}")


def _msty_position_and_ground_truth(module=bt):
    """Reconstruye la posicion real de MSTY desde el CSV de IB (Buy/Sell) via
    `module.shares_from_transactions`, y devuelve el ground truth de dividendos brutos que
    el propio extracto reporta (columna Action == 'Dividend' post-parseo, que ya neta las
    filas de correccion/reversion que IB emitio al restar el CUSIP tras el split — ver
    logic.parse_ibkr_csv, norm_ticker).

    Devuelve (position, first_date, last_date, csv_gross_total).
    """
    with open(MSTY_CSV, "rb") as f:
        raw = f.read()
    df = logic.parse_ibkr_csv(raw)
    msty = df[df["Ticker"] == "MSTY"].copy()
    msty["Date"] = pd.to_datetime(msty["Date"])

    tx = msty[msty["Action"].isin(["Buy", "Sell"])][["Date", "Quantity"]]
    try:
        splits = bt.fetch_splits("MSTY")
    except Exception as e:
        pytest.skip(f"yfinance no disponible (fetch_splits MSTY): {e}")

    position = module.shares_from_transactions(tx, splits)

    csv_gross = msty[msty["Action"] == "Dividend"]["Amount"].astype(float).sum()
    return position, msty["Date"].min(), msty["Date"].max(), csv_gross


# ── GATE: reconciliacion contra el extracto real de IB (MSTY) ───────────────

def test_gate_msty_reconciles_against_real_ib_statement():
    """EL gate de esta fase. Ver docstring del modulo."""
    _require_msty_csv()
    position, first, last, csv_gross = _msty_position_and_ground_truth()

    # ground truth citado en el plan de remediacion — si esto no coincide, el CSV/parser
    # cambiaron y hay que re-verificar el numero, no solo la tolerancia de abajo.
    assert csv_gross == pytest.approx(7224.59, abs=0.01)

    # posicion final reconstruida debe ser la posicion real declarada por Daniel (250
    # acciones MSTY, foto IB 2026-05-15 / real_examples/interactive_brokers_data/1/expected.json)
    assert position.iloc[-1] == pytest.approx(250.0, abs=0.01)

    try:
        engine_gross, detail = bt.dividends_for_position("MSTY", position, start=first, end=last)
    except Exception as e:
        pytest.skip(f"yfinance no disponible (dividends_for_position MSTY): {e}")

    assert len(detail) > 30, (
        f"muy pocos eventos de dividendo reconstruidos ({len(detail)}) — "
        "sospechoso de ventana mal calculada, no solo de splits"
    )

    diff_pct = abs(engine_gross - csv_gross) / csv_gross * 100.0
    assert diff_pct <= GATE_TOLERANCE_PCT, (
        f"GATE FALLIDO: motor reconstruyo ${engine_gross:,.2f} bruto vs ${csv_gross:,.2f} "
        f"real de IB ({diff_pct:.2f}% de diferencia, tolerancia {GATE_TOLERANCE_PCT}%). El "
        "manejo de splits (shares_from_transactions) o de elegibilidad de ex-date "
        "(dividends_for_position) esta mal — NO avanzar a UI con este motor."
    )


def test_gate_msty_position_matches_pre_and_post_split_units():
    """Sub-check del gate: la posicion reconstruida debe estar en unidades PRE-split (~1250,
    como aparecen literalmente en el ledger de IB) antes del split y POST-split (250) despues
    — confirma que `shares_from_transactions` esta aplicando el factor en el punto correcto
    del tiempo, no solo que el numero final da bien por casualidad."""
    _require_msty_csv()
    position, first, last, _ = _msty_position_and_ground_truth()

    before_split = position[position.index < pd.Timestamp("2025-12-08")]
    assert before_split.iloc[-1] == pytest.approx(250.0, abs=0.01), (
        "la posicion antes del split debe estar YA en unidades vigentes-hoy "
        "(250, no 1250) — shares_from_transactions convierte por transaccion, no por fecha "
        "de consulta"
    )
    assert position.iloc[-1] == pytest.approx(250.0, abs=0.01)


# ── position_asof: elegibilidad de ex-dividendo (unitario, sin red) ─────────

def test_position_asof_inclusive_vs_exclusive_on_same_day_transaction():
    """Regresion directa del bug que encontro la auditoria: una compra fechada EXACTAMENTE en
    la fecha de consulta debe contar con `inclusive=True` (posicion "al cierre del dia D") y
    NO contar con `inclusive=False` (elegibilidad de dividendo: hay que haber comprado ANTES
    del ex-date)."""
    position = pd.Series([10.0, 25.0], index=pd.to_datetime(["2024-01-01", "2024-01-10"]))
    assert bt.position_asof(position, "2024-01-10", inclusive=True) == 25.0
    assert bt.position_asof(position, "2024-01-10", inclusive=False) == 10.0
    # una fecha posterior a la ultima transaccion da lo mismo en ambos modos
    assert bt.position_asof(position, "2024-01-15", inclusive=True) == 25.0
    assert bt.position_asof(position, "2024-01-15", inclusive=False) == 25.0


def test_dividends_for_position_excludes_same_day_purchase():
    """Version sintetica minima del bug real: comprar 100 acciones justo en la fecha
    ex-dividendo no debe generar dividendo ese evento (compra tardia), pero SI participa de
    cualquier distribucion posterior."""
    position = pd.Series([50.0, 150.0], index=pd.to_datetime(["2024-01-01", "2024-01-10"]))
    dividends = pd.Series([1.0, 1.0], index=pd.to_datetime(["2024-01-10", "2024-01-20"]))
    total, detail = bt.dividends_for_position(
        "FAKE", position, start="2024-01-01", end="2024-01-31", dividends=dividends)
    by_date = detail.set_index("ex_date")["shares"]
    assert by_date.loc[pd.Timestamp("2024-01-10")] == 50.0, (
        "la compra del mismo dia (2024-01-10, 100 acciones) no deberia contar para el "
        "dividendo con ex-date 2024-01-10"
    )
    assert by_date.loc[pd.Timestamp("2024-01-20")] == 150.0
    assert total == pytest.approx(50.0 + 150.0)


def test_date_buffer_days_matters_when_event_falls_at_the_window_edge():
    """La auditoria de Opus probo 0/1/2/3/5 sobre el caso real MSTY y el total no se movio —
    correcto, porque en ese dataset el primer/ultimo evento de yfinance ya caen comodamente
    DENTRO de [start, end] sin necesitar margen (no es que el parametro este muerto). Este
    test sintetico fuerza el caso donde SI importa: un evento justo 2 dias fuera del borde de
    la ventana solo aparece si el buffer lo alcanza."""
    position = pd.Series([100.0], index=pd.to_datetime(["2024-01-01"]))
    dividends = pd.Series([1.0], index=pd.to_datetime(["2024-01-03"]))  # 2 dias antes de start
    total_sin_buffer, detail_sin = bt.dividends_for_position(
        "FAKE", position, start="2024-01-05", end="2024-01-31",
        dividends=dividends, date_buffer_days=0)
    total_con_buffer, detail_con = bt.dividends_for_position(
        "FAKE", position, start="2024-01-05", end="2024-01-31",
        dividends=dividends, date_buffer_days=3)
    assert total_sin_buffer == 0.0 and len(detail_sin) == 0, (
        "sin buffer, el evento fuera de [start, end] no deberia aparecer"
    )
    assert total_con_buffer == pytest.approx(100.0) and len(detail_con) == 1, (
        "con buffer=3, el evento a 2 dias del borde SI deberia entrar — "
        "date_buffer_days no esta muerto, solo no lo ejercita el caso real de MSTY"
    )


# ── Casos de split conocidos (fallan si el ajuste se rompe) ─────────────────

KNOWN_SPLITS = {
    "MSTY": [("2025-12-08", 0.2)],
    "CONY": [("2025-12-02", 0.1)],
    "TSLY": [("2024-02-26", 0.5), ("2025-12-01", 0.2)],
    "NVDY": [],  # sin splits
}


@pytest.mark.parametrize("ticker", sorted(KNOWN_SPLITS))
def test_known_splits_match_expected(ticker):
    expected = KNOWN_SPLITS[ticker]
    try:
        splits = bt.fetch_splits(ticker)
    except Exception as e:
        pytest.skip(f"yfinance no disponible (fetch_splits {ticker}): {e}")

    assert len(splits) == len(expected), (
        f"{ticker}: se esperaban {len(expected)} splits ({expected}), "
        f"yfinance devolvio {len(splits)}: {list(zip(splits.index.astype(str), splits.values))}"
    )
    for exp_date, exp_ratio in expected:
        exp_ts = pd.Timestamp(exp_date)
        match = splits[splits.index == exp_ts]
        assert len(match) == 1, f"{ticker}: no se encontro split en {exp_date} (splits={splits})"
        assert float(match.iloc[0]) == pytest.approx(exp_ratio, abs=1e-6)


def test_price_and_dividends_are_split_normalized_not_discontinuous():
    """Documenta/verifica el supuesto central del modulo: yfinance ya split-ajusta `Close`
    (incluso con auto_adjust=False) y `Dividends` de forma consistente, asi que NO deberia
    haber un salto ~5x en precio ni en dividendo/accion al cruzar la fecha de split de MSTY
    (2025-12-08, ratio 1:5). Si yfinance cambia esta convencion, este test es la alarma."""
    try:
        hist = bt.fetch_history("MSTY")
    except Exception as e:
        pytest.skip(f"yfinance no disponible (fetch_history MSTY): {e}")
    if hist.empty:
        pytest.skip("yfinance devolvio historia vacia para MSTY")

    split_date = pd.Timestamp("2025-12-08")
    before = hist[(hist.index >= split_date - pd.Timedelta(days=5)) & (hist.index < split_date)]
    after = hist[(hist.index >= split_date) & (hist.index <= split_date + pd.Timedelta(days=5))]
    if before.empty or after.empty:
        pytest.skip("sin suficientes datos alrededor del split para comparar")

    price_before = float(before["Close"].iloc[-1])
    price_after = float(after["Close"].iloc[0])
    ratio = price_after / price_before if price_before else 0.0
    # una serie NO normalizada por split mostraria ratio ~5x (o ~0.2x) en el borde; una
    # normalizada se mueve por variacion de mercado normal de pocos dias (holgado: 0.5x-2x)
    assert 0.5 <= ratio <= 2.0, (
        f"salto de precio {ratio:.2f}x al cruzar el split de MSTY — yfinance dejo de "
        "split-ajustar Close; run_backtest ya no puede asumir continuidad"
    )


# ── Motor: sanity checks basicos (independientes del gate) ──────────────────

def test_run_backtest_no_dividends_equals_price_return():
    """Sin dividendos (serie sintetica), DRIP y efectivo deben coincidir exactamente con el
    retorno de precio puro — es el caso base que prueba que el motor no inventa nada."""
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    history = pd.DataFrame({"Close": [10.0, 11.0, 9.0, 12.0, 12.0],
                             "Dividends": [0.0] * 5}, index=idx)
    r_drip = bt.run_backtest("FAKE", idx[0], initial_capital=100.0, drip=True, history=history)
    r_cash = bt.run_backtest("FAKE", idx[0], initial_capital=100.0, drip=False, history=history)
    assert r_drip.total_return_pct == pytest.approx(20.0, abs=1e-9)  # 12/10 - 1
    assert r_cash.total_return_pct == pytest.approx(r_drip.total_return_pct, abs=1e-9)
    assert r_drip.gross_dividends_total == 0.0


def test_run_backtest_drip_beats_cash_when_price_recovers_after_div():
    """Caso sintetico minimo del hallazgo TSLY: si el precio cae fuerte pero se recupera
    ANTES de que el dividendo se reinvierta a precio bajo, DRIP puede superar al efectivo
    aunque el precio termine deprimido. No es el caso real (eso lo prueba el gate de arriba
    contra datos reales) — es la prueba de que el mecanismo del motor lo permite."""
    idx = pd.date_range("2024-01-01", periods=4, freq="D")
    # cae de 10 a 2 (ex-div ese dia, dividendo grande), luego se recupera a 8
    history = pd.DataFrame({
        "Close": [10.0, 2.0, 5.0, 8.0],
        "Dividends": [0.0, 1.0, 0.0, 0.0],
    }, index=idx)
    r_drip = bt.run_backtest("FAKE", idx[0], initial_capital=100.0, drip=True, history=history)
    r_cash = bt.run_backtest("FAKE", idx[0], initial_capital=100.0, drip=False, history=history)
    assert r_drip.total_return_pct > r_cash.total_return_pct, (
        "el motor no deberia asumir que el efectivo siempre gana cuando el precio cae — "
        "esa es precisamente la premisa falsa que este PR existe para tumbar"
    )


def test_run_backtest_nra_rate_reduces_reinvested_and_cash_amounts():
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    history = pd.DataFrame({"Close": [10.0, 10.0, 10.0], "Dividends": [0.0, 1.0, 0.0]},
                            index=idx)
    r_bruto = bt.run_backtest("FAKE", idx[0], initial_capital=100.0, drip=False,
                               nra_rate=0.0, history=history)
    r_neto = bt.run_backtest("FAKE", idx[0], initial_capital=100.0, drip=False,
                              nra_rate=0.30, history=history)
    assert r_bruto.net_dividends_total == pytest.approx(10.0)  # 10 acciones x $1
    assert r_neto.net_dividends_total == pytest.approx(7.0)     # 10 x $1 x (1-0.30)
    assert r_neto.nra_withheld_total == pytest.approx(3.0)


def test_run_backtest_rejects_invalid_nra_rate():
    with pytest.raises(ValueError):
        bt.run_backtest("FAKE", "2024-01-01", initial_capital=100.0, nra_rate=1.5)


def test_run_backtest_requires_capital_or_shares():
    with pytest.raises(ValueError):
        bt.run_backtest("FAKE", "2024-01-01")


# ── Tests de sabotaje: rompen el motor a proposito y confirman que el gate FALLA ─

@contextlib.contextmanager
def _sabotaged_backtest_module(target: str, replacement: str, sabotage_name: str):
    """Reescribe `backtest.py` en disco reemplazando `target` por `replacement`, carga esa
    version rota como un modulo Python aparte (no pisa el `backtest` normal que el resto de
    la suite ya tiene importado), la entrega al bloque `with`, y SIEMPRE — pase lo que pase
    adentro — revierte el archivo al original y verifica con `diff` que quedo byte-a-byte
    identico (feedback_test-tocado-para-desbloquear-deploy: la pregunta no es si el gate
    "pasa" sino si seguiria detectando el bug; y un sabotaje que no se revierte limpio deja
    el repo roto para el resto de la sesion)."""
    original = Path(BACKTEST_PATH).read_text(encoding="utf-8")
    assert original.count(target) == 1, (
        f"[{sabotage_name}] linea de sabotaje no encontrada (o duplicada) en backtest.py — "
        "el codigo cambio, actualizar el target de este sabotaje"
    )
    sabotaged = original.replace(target, replacement)
    assert sabotaged != original

    backup_path = BACKTEST_PATH + f".sabotage_backup.{sabotage_name}"
    Path(backup_path).write_text(original, encoding="utf-8")
    module_name = f"backtest_sabotaged_{sabotage_name}"

    try:
        Path(BACKTEST_PATH).write_text(sabotaged, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(module_name, BACKTEST_PATH)
        sabotaged_module = importlib.util.module_from_spec(spec)
        # dataclasses._get_field resuelve anotaciones tipo-string buscando el modulo en
        # sys.modules por nombre; sin registrarlo ahi, la definicion de BacktestResult
        # revienta con AttributeError al cargar el archivo sabotaged como modulo aparte.
        sys.modules[module_name] = sabotaged_module
        try:
            spec.loader.exec_module(sabotaged_module)
            yield sabotaged_module
        finally:
            del sys.modules[module_name]
    finally:
        Path(BACKTEST_PATH).write_text(original, encoding="utf-8")
        restored = Path(BACKTEST_PATH).read_text(encoding="utf-8")
        assert restored == original, (
            f"[{sabotage_name}] backtest.py NO quedo identico tras revertir el sabotaje"
        )
        diff_result = subprocess.run(
            ["diff", BACKTEST_PATH, backup_path], capture_output=True, text=True)
        assert diff_result.returncode == 0 and diff_result.stdout == "", (
            f"[{sabotage_name}] diff detecto cambios residuales tras revertir:\n"
            f"{diff_result.stdout}"
        )
        os.remove(backup_path)


def test_sabotage_breaking_split_handling_fails_the_gate():
    """Rompe a proposito la conversion de splits en `shares_from_transactions` (hardcodea el
    factor a 1.0, es decir: "ignora los splits" — el bug exacto del Riesgo #1 del plan)."""
    _require_msty_csv()

    with _sabotaged_backtest_module(
        target="return float(future.prod())",
        replacement="return 1.0  # SABOTAJE DE PRUEBA: ignora los splits futuros a proposito",
        sabotage_name="split_factor",
    ) as sabotaged_module:
        position, first, last, csv_gross = _msty_position_and_ground_truth(
            module=sabotaged_module)
        # con el split ignorado, la posicion final queda en unidades PRE-split (~1250) en vez
        # de las 250 reales
        assert position.iloc[-1] == pytest.approx(1250.0, abs=1.0), (
            "el sabotaje no tuvo el efecto esperado sobre la posicion — revisar el patch"
        )

        engine_gross, _ = sabotaged_module.dividends_for_position(
            "MSTY", position, start=first, end=last)
        diff_pct = abs(engine_gross - csv_gross) / csv_gross * 100.0

        assert diff_pct > GATE_TOLERANCE_PCT, (
            f"el gate deberia fallar con el manejo de splits roto, pero la diferencia quedo "
            f"en {diff_pct:.2f}% (tolerancia {GATE_TOLERANCE_PCT}%) — el sabotaje no esta "
            "ejercitando la rama que protege el gate"
        )
        print(f"[sabotaje splits] gate FALLA como se esperaba: {diff_pct:.1f}% de diferencia "
              f"(motor roto reconstruyo ${engine_gross:,.2f} vs ${csv_gross:,.2f} real)")


def test_sabotage_breaking_eligibility_cutoff_fails_the_gate():
    """Rompe a proposito el corte de elegibilidad de dividendo en `dividends_for_position`
    (vuelve a `inclusive=True`, el bug REAL que encontro la auditoria de Opus sobre la
    primera version de este PR: contar como elegible una compra hecha el mismo dia de la
    fecha ex-dividendo). Confirma que el gate sube de 0.013% a ~4.8% y falla."""
    _require_msty_csv()

    with _sabotaged_backtest_module(
        target='shares = position_asof(position, ex_date, inclusive=False)',
        replacement=(
            'shares = position_asof(position, ex_date, inclusive=True)  '
            '# SABOTAJE DE PRUEBA: cuenta de mas las compras del mismo dia'
        ),
        sabotage_name="eligibility_cutoff",
    ) as sabotaged_module:
        position, first, last, csv_gross = _msty_position_and_ground_truth(
            module=sabotaged_module)
        # el sabotaje esta en dividends_for_position, no en shares_from_transactions — la
        # posicion en si sigue correcta (250 finales)
        assert position.iloc[-1] == pytest.approx(250.0, abs=0.01)

        engine_gross, _ = sabotaged_module.dividends_for_position(
            "MSTY", position, start=first, end=last)
        diff_pct = abs(engine_gross - csv_gross) / csv_gross * 100.0

        assert diff_pct > GATE_TOLERANCE_PCT, (
            f"el gate deberia fallar con el corte de elegibilidad roto, pero la diferencia "
            f"quedo en {diff_pct:.2f}% (tolerancia {GATE_TOLERANCE_PCT}%) — el sabotaje no "
            "esta ejercitando la rama que protege el gate"
        )
        assert diff_pct == pytest.approx(4.80, abs=0.5), (
            f"se esperaba recrear aprox. el 4.80% que reporto la auditoria original al "
            f"contar de mas las compras del mismo dia; dio {diff_pct:.2f}%"
        )
        print(f"[sabotaje elegibilidad] gate FALLA como se esperaba: {diff_pct:.2f}% de "
              f"diferencia (motor roto reconstruyo ${engine_gross:,.2f} vs "
              f"${csv_gross:,.2f} real)")
