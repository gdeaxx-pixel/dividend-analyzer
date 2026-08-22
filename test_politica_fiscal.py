"""`ui.adapters._roc_pct_by_year` y `_politica_fiscal` — el mapeo ROC → año fiscal.

Estos tests nacen al **jubilar** `logic.build_roc_aware_withholding` (y con ella
`build_drip_comparison_series` / `build_total_return_series`), el motor que modelaba el
escudo ROC como tasa efectiva al cobro. Esas funciones tenían 8 tests de casos borde del
mapeo; la función que las reemplazó no tenía **ninguno** — solo se ejercía de refilón, a
través de la reconciliación de las vistas.

Borrar los tests viejos sin escribir estos habría sido una pérdida neta de protección
disfrazada de limpieza: el concepto sigue vivo, solo cambió de dueño.

**Qué cubre cada carril, para no volver a dejar un hueco así:**
  - la aritmética del mapeo (este archivo);
  - que la política llegue al motor sin diluirse (`test_un_solo_motor_fiscal.py`,
    `test_comparacion_data.py` — espías sobre `run_backtest`);
  - que las dos vistas que la consumen no diverjan (`test_un_solo_motor_fiscal.py`).
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(__file__))
import logic  # noqa: E402
from ui.adapters import _CMP_FLAT_RATE, _politica_fiscal, _roc_pct_by_year  # noqa: E402


def _yaml(**tickers):
    """Un `roc_19a` sintético, con la misma forma que `logic.load_roc_19a()`."""
    return dict(tickers)


def _avisos(*pares):
    return [{"date": f, "roc_pct": p} for f, p in pares]


# ── El mapeo por año ─────────────────────────────────────────────────────────────────────

class TestRocPorAnio:
    """La reclasificación del bróker opera por AÑO FISCAL: cada año reclama el promedio de
    los avisos 19(a) publicados ESE año. Misma convención que
    `logic.estimate_roc_refund_by_year`, que es quien la fijó."""

    def test_cada_anio_usa_el_promedio_de_sus_propios_avisos(self):
        roc19a = _yaml(MSTY={"weighted_pct": 50.0,
                             "per_distribution": _avisos(("2025-01-05", 90.0),
                                                         ("2025-07-05", 70.0),
                                                         ("2026-02-05", 20.0))})
        assert _roc_pct_by_year("MSTY", roc19a) == {2025: 80.0, 2026: 20.0}

    def test_un_hueco_dentro_de_la_ventana_hereda_el_ponderado(self):
        """Un año sin avisos ENTRE dos que sí los tienen es un hueco de publicación, no un
        año sin ROC. Leerlo como 0% diría que ese año no hubo retorno de capital, que es una
        afirmación sobre el fondo y no sobre nuestros datos."""
        roc19a = _yaml(MSTY={"weighted_pct": 55.0,
                             "per_distribution": _avisos(("2024-01-05", 90.0),
                                                         ("2026-02-05", 20.0))})
        assert _roc_pct_by_year("MSTY", roc19a) == {2024: 90.0, 2025: 55.0, 2026: 20.0}

    def test_los_anios_anteriores_a_la_ventana_no_reclaman_nada(self):
        """**El piso conservador, y la decisión de producto más cara de este objeto.** Un
        año ANTERIOR al primer aviso no aparece en el dict, así que el motor le aplica 0% de
        ROC: retiene completo y no devuelve nada.

        No es simetría con el hueco de arriba, y es deliberado: dentro de la ventana sabemos
        que el fondo publicaba y falta un dato; antes de ella no sabemos ni eso. Extrapolar
        hacia atrás sería inventar el pasado; el piso solo se equivoca en contra del
        inversor, nunca a favor.

        Medido sobre datos reales (2026-08-21): vale **20.4 pp** en TSLY (avisos desde
        may-2025, incepción nov-2022) y **17.0 pp** en CONY. Si alguien decide extrapolar,
        que sea cambiando esta línea a propósito y no por accidente."""
        roc19a = _yaml(TSLY={"weighted_pct": 54.0,
                             "per_distribution": _avisos(("2025-05-14", 60.0))})
        por_anio = _roc_pct_by_year("TSLY", roc19a)
        assert por_anio == {2025: 60.0}
        for anio in (2022, 2023, 2024):
            assert anio not in por_anio, (
                f"{anio} es anterior al primer aviso: no puede reclamar escudo")

    def test_sin_avisos_no_hay_escudo_aunque_haya_ponderado(self):
        """Un fondo con `weighted_pct` pero sin `per_distribution` devuelve `{}`: sin fechas
        no hay año al que imputar la reclasificación. Es un cambio real frente al motor
        jubilado, que en ese caso aplicaba el ponderado a todas las distribuciones — se pina
        aquí para que se vea si alguien lo revierte."""
        assert _roc_pct_by_year("MSTY", _yaml(MSTY={"weighted_pct": 72.0})) == {}

    def test_ticker_desconocido_devuelve_vacio(self):
        assert _roc_pct_by_year("SCHB", _yaml(MSTY={"weighted_pct": 72.0})) == {}
        assert _roc_pct_by_year("SCHB", {}) == {}

    def test_un_aviso_corrupto_no_tumba_el_resto(self):
        """El yaml lo escribe un scraper semanal contra una página de terceros: una fila
        malformada tiene que perder solo esa fila."""
        roc19a = _yaml(MSTY={"weighted_pct": 50.0,
                             "per_distribution": [{"date": "2025-01-05", "roc_pct": 90.0},
                                                  {"date": "no-es-fecha", "roc_pct": 10.0},
                                                  {"date": "2025-02-05"},
                                                  {"date": "2025-03-05", "roc_pct": "x"},
                                                  {"date": "2025-04-05", "roc_pct": 70.0}]})
        assert _roc_pct_by_year("MSTY", roc19a) == {2025: 80.0}


# ── Contra el yaml vivo ──────────────────────────────────────────────────────────────────

def test_el_promedio_por_anio_cuadra_con_los_avisos_del_yaml():
    """Reconciliación contra la fuente viva, no contra la fórmula. Hereda la intención de
    `test_build_roc_aware_withholding_matches_most_msty_distributions`, que verificaba el
    empate por fecha del motor jubilado: aquí el lado independiente es el promedio calculado
    a mano desde `knowledge/roc_19a.yaml`.

    Se afirma sobre el fondo con más historia publicada; si mañana el yaml se queda sin
    avisos de MSTY, el test lo dice en vez de pasar por vacío."""
    roc19a = logic.load_roc_19a()
    info = roc19a.get("MSTY") or {}
    avisos = info.get("per_distribution") or []
    assert len(avisos) >= 20, (
        f"solo {len(avisos)} avisos 19(a) de MSTY en el yaml — o el scraper se rompió, o "
        "este test dejó de tener material sobre el que afirmar algo")

    a_mano: dict[int, list[float]] = {}
    for aviso in avisos:
        a_mano.setdefault(pd.Timestamp(aviso["date"]).year, []).append(float(aviso["roc_pct"]))

    por_anio = _roc_pct_by_year("MSTY", roc19a)
    for anio, valores in a_mano.items():
        assert por_anio[anio] == pytest.approx(sum(valores) / len(valores), abs=1e-9), anio
    assert set(a_mano) <= set(por_anio)
    assert all(0.0 <= pct <= 100.0 for pct in por_anio.values()), por_anio


# ── La política que se arma con ese mapeo ────────────────────────────────────────────────

class TestPoliticaFiscal:
    _ROC19A = _yaml(MSTY={"weighted_pct": 60.0,
                          "per_distribution": _avisos(("2025-01-05", 60.0))})

    def test_bruto_no_retiene_ni_reclama(self):
        pol = _politica_fiscal("MSTY", "bruto", self._ROC19A, base_rate=0.30)
        assert pol.rate == 0.0 and pol.roc_pct_by_year == {}

    def test_plano_retiene_todo_y_no_devuelve(self):
        pol = _politica_fiscal("MSTY", "plano", self._ROC19A, base_rate=0.30)
        assert pol.rate == 0.30 and pol.roc_pct_by_year == {}

    def test_roc_retiene_completo_y_reclama_aparte(self):
        """El corazón del modelo: la tasa al cobro es la MISMA que en «plano» — el escudo no
        la rebaja, viaja aparte y vuelve con el 1042-S."""
        pol = _politica_fiscal("MSTY", "roc", self._ROC19A, base_rate=0.30)
        assert pol.rate == 0.30, "el escudo volvió a meterse dentro de la tasa"
        assert pol.roc_pct_by_year == {2025: 60.0}

    def test_sin_avisos_roc_es_identico_a_plano(self):
        """Lo que la UI declara en el copy: un fondo sin avisos 19(a) no tiene nada que
        reclasificar, así que «Neto ROC 19a» y «Peor caso» dan la misma línea."""
        assert _politica_fiscal("SCHB", "roc", self._ROC19A, base_rate=0.30) == \
               _politica_fiscal("SCHB", "plano", self._ROC19A, base_rate=0.30)

    @pytest.mark.parametrize("base_rate", [0.10, 0.15, 0.30])
    def test_la_tasa_del_pais_se_respeta_en_los_dos_modos_con_retencion(self, base_rate):
        """«Comparación · Real» pasa la tasa del país declarado (10% México con tratado);
        los paneles pedagógicos usan el 30% por defecto. El %ROC no depende de la tasa: es
        una propiedad de la distribución, no del inversor."""
        for modo in ("plano", "roc"):
            assert _politica_fiscal("MSTY", modo, self._ROC19A, base_rate=base_rate).rate == base_rate
        assert _politica_fiscal("MSTY", "roc", self._ROC19A, base_rate=base_rate).roc_pct_by_year \
               == _politica_fiscal("MSTY", "roc", self._ROC19A, base_rate=0.30).roc_pct_by_year

    def test_el_default_es_la_tasa_plana_de_los_paneles(self):
        assert _politica_fiscal("MSTY", "plano", self._ROC19A).rate == _CMP_FLAT_RATE
