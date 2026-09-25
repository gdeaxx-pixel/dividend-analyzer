"""U4 · Carga + cobertura integrada — tests del adapter `cobertura_data`, de la dona de
5 segmentos y de los tres retoques del flujo de 3 pasos. U4bis añade las correcciones
H1 (Regla 3b sobre tres segmentos, parametrizada por residencia) y los guards H2/H3
del componente.

Cuatro capas (mismo patrón que `test_portafolios_data.py` / `test_vista_impuestos_render.py`):

1. ADAPTER — los 5 segmentos salen de SUS señales (tabla §4.1 de la spec), sobre fixtures
   sintéticos. Cifras/estados esperados escritos A MANO, nunca con la expresión auditada
   (trampa 3 de la spec §7).
2. REGLA 3b (§4.2, corregida por U4bis H1) — la dona y la etiqueta Alta/Media/Baja de
   `_puntuacion_acertividad` leen las mismas señales de datos y no pueden contradecirse.
   El invariante es sobre TRES segmentos (movimientos/posiciones/excluidos); `fiscal` y
   `valoracion` quedan fuera porque la etiqueta no lee `rate_declared` ni
   `valuation_date`. Parametrizado por residencia (con país / sin país): «Sin declarar»
   es el default de la app y tiene que estar vigilado.
3. RENDER — datos, tema, decisiones cerradas (§5.2) y los guards U4bis H2/H3: el tono
   de cada segmento depende de su `estado` y el centro N/5 lee `DATA.verificados` en
   vez de recalcularlo en JS.
4. FLUJO (`AppTest`) — dona arriba del flujo, los 5 pendientes antes de confirmar (y
   `analyze_portfolio` NO llamado), residencia en el paso 3 antes de los dos retornos,
   y «Editar» del paso 2 que vuelve conservando el CSV.

Ninguna cifra se calcula en JS: el componente (`ui/componentes/cobertura.html`) dibuja lo
que recibe en `DATA` (Regla 3). Los tests de render lo verifican sobre el `srcdoc` real.
"""
import os
import re
import sys

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

sys.path.insert(0, os.path.dirname(__file__))
import logic
from ui import estado
from ui.adapters import cobertura_data
from ui.validacion import _puntuacion_acertividad

BASE = os.path.dirname(os.path.abspath(__file__))


# ── Helpers de fixtures sintéticas ───────────────────────────────────────────────────

def _hist(rows, ticker="MSTY"):
    """history DataFrame mínimo [Date, Action, Amount, Ticker] (patrón `test_logic.py`)."""
    return pd.DataFrame([
        {"Date": pd.Timestamp(d), "Action": a, "Amount": amt, "Ticker": ticker}
        for d, a, amt in rows
    ])


def _stats_ok(vdate="2026-09-20", precio=17.5):
    """Un ticker ANALIZADO y sano: sin `history_incomplete`, cobertura alta, con
    `valuation_date` y `current_price`. Es lo que `assess_ticker_quality` puntúa `ok`."""
    return {"history_incomplete": False, "csv_coverage_pct": 100.0,
            "valuation_date": vdate, "current_price": precio}


def _cartera_limpia():
    """Dos tickers sanos, fechas de valoración iguales — la cartera que da 5/5 con
    posiciones confirmadas y residencia declarada."""
    return {"MSTY": _stats_ok(precio=17.5), "SCHB": _stats_ok(precio=29.0)}


@pytest.fixture
def sesion(monkeypatch):
    """Reemplaza `st.session_state` (proxy, no settable) por un dict real y declara una
    residencia + posiciones confirmadas: el estado en el que la dona debe leer las MISMAS
    señales que la etiqueta de confiabilidad (Regla 3b)."""
    monkeypatch.setattr(st, "session_state",
                        {"_wizard_pos_confirmed": True})
    monkeypatch.setattr(estado, "perfil_fiscal",
                        lambda: {"rate_declared": True, "country": "Colombia",
                                 "rate_pct": 30.0, "has_treaty": False})
    return st.session_state


def _seg(datos, clave):
    for s in datos["segmentos"]:
        if s["clave"] == clave:
            return s
    raise AssertionError(f"segmento {clave!r} ausente")


# ── Capa 1 · ADAPTER — cada segmento por SU señal (§4.1) ────────────────────────────

def test_cartera_limpia_da_cinco_de_cinco(sesion):
    """Baseline escrito a mano: con posiciones confirmadas, residencia declarada, dos
    tickers `ok`, sin 1042-S ni income y fechas de valoración iguales → 5/5."""
    d = cobertura_data(_cartera_limpia())
    assert d["verificados"] == 5
    assert [s["estado"] for s in d["segmentos"]] == ["ok"] * 5
    # El orden de los 5 segmentos es el cerrado en §4.1 (Periodo → Excluidos).
    assert [s["clave"] for s in d["segmentos"]] == [
        "movimientos", "posiciones", "fiscal", "valoracion", "excluidos"]


def test_segmento_movimientos_pendiente_por_unreliable(sesion):
    """Seg 1 — verde cuando ningún ticker está en `unreliable`. Se pone pendiente con
    `history_incomplete` (cost_broken → unreliable) y vuelve a verde al quitarlo."""
    cartera = _cartera_limpia()
    assert _seg(cobertura_data(cartera), "movimientos")["estado"] == "ok"

    cartera["MSTY"]["history_incomplete"] = True
    assert _seg(cobertura_data(cartera), "movimientos")["estado"] == "pendiente"
    # El resto no se contamina por ESTA señal.
    assert _seg(cobertura_data(cartera), "excluidos")["estado"] == "ok"


def test_segmento_posiciones_pendiente_sin_confirmar(sesion):
    """Seg 2 — verde solo si `_wizard_pos_confirmed` es True Y ningún ticker en
    `partial`/`reconciled`. Dos caminos a pendiente, uno por señal."""
    cartera = _cartera_limpia()
    assert _seg(cobertura_data(cartera), "posiciones")["estado"] == "ok"

    # (a) sin confirmar
    sesion["_wizard_pos_confirmed"] = False
    assert _seg(cobertura_data(cartera), "posiciones")["estado"] == "pendiente"
    sesion["_wizard_pos_confirmed"] = True

    # (b) un ticker reconciliado desde la captura (level ∉ ok/unreliable)
    cartera["SCHB"]["reconciled_from_snapshot"] = True
    cartera["SCHB"]["reconciled_fields"] = ["shares"]
    assert _seg(cobertura_data(cartera), "posiciones")["estado"] == "pendiente"
    # ...pero Movimientos NO se pone rojo: `reconciled` no es `unreliable`.
    assert _seg(cobertura_data(cartera), "movimientos")["estado"] == "ok"


def test_posiciones_pendiente_dice_la_causa_correcta(sesion):
    """Las DOS causas del pendiente de Posiciones no se leen igual.

    Sin confirmar, el pop-out pide confirmar. Ya confirmado y con un ticker
    `reconciled`/`partial`, lo que falta es el HISTORIAL: el texto de «confirma las
    cantidades» pediría algo que el cliente acaba de hacer, y el título «Posiciones»
    contradice al chip «✓ POSICIONES CONFIRMADAS» del propio flujo. La `clave` no cambia
    en ningún caso — es la identidad del segmento.
    """
    cartera = _cartera_limpia()

    # (a) sin confirmar: el texto original, y el nombre del catálogo.
    sesion["_wizard_pos_confirmed"] = False
    seg = _seg(cobertura_data(cartera), "posiciones")
    assert seg["estado"] == "pendiente"
    assert seg["nombre"] == "Posiciones"
    assert "confirmaci" in seg["falta"]

    # (b) confirmado Y reconciliado: variante de historial.
    sesion["_wizard_pos_confirmed"] = True
    cartera["SCHB"]["reconciled_from_snapshot"] = True
    cartera["SCHB"]["reconciled_fields"] = ["shares"]
    seg = _seg(cobertura_data(cartera), "posiciones")
    assert seg["estado"] == "pendiente"
    assert seg["clave"] == "posiciones"
    assert seg["nombre"] == "Historial de posiciones"
    # No puede seguir pidiendo confirmar lo ya confirmado.
    assert "requieren confirmaci" not in seg["falta"]
    assert "no cubre toda la vida" in seg["falta"]

    # (c) sin confirmar Y reconciliado: manda la falta de confirmación, que es el paso
    #     que el cliente tiene delante.
    sesion["_wizard_pos_confirmed"] = False
    seg = _seg(cobertura_data(cartera), "posiciones")
    assert seg["nombre"] == "Posiciones"
    assert "confirmaci" in seg["falta"]


def test_segmento_fiscal_pendiente_sin_residencia(sesion, monkeypatch):
    """Seg 3 — necesita residencia declarada (`rate_declared`)."""
    cartera = _cartera_limpia()
    assert _seg(cobertura_data(cartera), "fiscal")["estado"] == "ok"

    monkeypatch.setattr(estado, "perfil_fiscal",
                        lambda: {"rate_declared": False, "country": None})
    assert _seg(cobertura_data(cartera), "fiscal")["estado"] == "pendiente"


def test_segmento_fiscal_pendiente_por_1042s_que_no_cuadra(sesion):
    """Seg 3 — con residencia declarada, un 1042-S cuyo bruto no cuadra
    (`portfolio_higher`) lo pone pendiente; al quitarlo vuelve a verde."""
    cartera = _cartera_limpia()
    cartera["MSTY"]["history"] = _hist([("2025-06-01", "Cash Dividend", 1000.0)])

    sesion["_wizard_1042s"] = {
        "tax_year": 2025,
        "forms": [{"unique_form_id": "1", "income_code": "06", "gross_income": 100.0,
                   "federal_tax_withheld": 30.0, "withholding_credit": 0.0}],
    }
    assert _seg(cobertura_data(cartera), "fiscal")["estado"] == "pendiente"

    sesion.pop("_wizard_1042s", None)
    assert _seg(cobertura_data(cartera), "fiscal")["estado"] == "ok"


def test_segmento_fiscal_pendiente_por_income_en_alerta(sesion):
    """Seg 3 — con residencia declarada, un income cuyo `reconcile` da `badge == warn`
    lo pone pendiente; al quitarlo vuelve a verde."""
    cartera = _cartera_limpia()
    cartera["MSTY"]["history"] = _hist([("2025-06-01", "Cash Dividend", 100.0)])

    sesion["_wizard_income_summary"] = {"tickers": {"MSTY": {"received_total": 5000.0}}}
    assert _seg(cobertura_data(cartera), "fiscal")["estado"] == "pendiente"

    sesion.pop("_wizard_income_summary", None)
    assert _seg(cobertura_data(cartera), "fiscal")["estado"] == "ok"


def test_segmento_valoracion_exige_fecha_no_nula_igual_y_precio(sesion):
    """Seg 4 — verde solo si TODOS los analizados publican `valuation_date` no nulo Y
    todos la misma, y ninguno trae `current_price` nulo (logic.py:2250, F5)."""
    # (a) fechas distintas entre tickers
    a = {"MSTY": _stats_ok(vdate="2026-09-20"), "SCHB": _stats_ok(vdate="2026-09-19")}
    assert _seg(cobertura_data(a), "valoracion")["estado"] == "pendiente"

    # (b) valuation_date presente pero None (trampa 4 de la spec: distinto de «falta»)
    b = {"MSTY": _stats_ok(vdate="2026-09-20")}
    b["SCHB"] = _stats_ok()
    b["SCHB"]["valuation_date"] = None
    assert _seg(cobertura_data(b), "valoracion")["estado"] == "pendiente"

    # (c) valuation_date AUSENTE (la clave no está) — caso distinto de (b)
    c = {"MSTY": _stats_ok()}
    c["SCHB"] = _stats_ok()
    del c["SCHB"]["valuation_date"]
    assert _seg(cobertura_data(c), "valoracion")["estado"] == "pendiente"

    # (d) current_price nulo
    e = {"MSTY": _stats_ok(), "SCHB": _stats_ok()}
    e["SCHB"]["current_price"] = None
    assert _seg(cobertura_data(e), "valoracion")["estado"] == "pendiente"

    # (e) todos sanos y con la misma fecha → verde
    assert _seg(cobertura_data(_cartera_limpia()), "valoracion")["estado"] == "ok"


def test_segmento_excluidos_mira_tuyos_no_el_ruido(sesion):
    """Seg 5 — verde cuando `_separar_excluidos(resultados)[0]` (`tuyos`) está vacío. El
    `ruido` (not_known_etf, cientos de tickers que nunca fueron del portafolio) NO lo pone
    en rojo: confundirlos pintaría 4/5 en carteras sanas."""
    cartera = _cartera_limpia()

    # Solo ruido → sigue verde.
    cartera["AAA"] = {"skipped": True, "reason": "not_known_etf"}
    assert _seg(cobertura_data(cartera), "excluidos")["estado"] == "ok"

    # Una posición TUYA excluida por datos insuficientes → pendiente.
    cartera["ZZZ"] = {"skipped": True, "reason": "held_less_than_14_days", "holding_days": 5}
    assert _seg(cobertura_data(cartera), "excluidos")["estado"] == "pendiente"


def test_sin_resultados_todo_pendiente(sesion):
    """§4.3 — sin resultados (`analyze_portfolio` no ha corrido), los 5 van pendientes.
    Decisión de Daniel del 18-sep."""
    d = cobertura_data({})
    assert d["verificados"] == 0
    assert all(s["estado"] == "pendiente" for s in d["segmentos"])
    # Cada segmento conserva su texto «qué falta» / «cómo resolverlo».
    assert all(s["falta"] and s["como"] for s in d["segmentos"])


def test_contrato_del_adapter_sin_cifras(sesion):
    """§5.1.2 — el adapter devuelve, por segmento, SOLO clave/nombre/estado/falta/como,
    más `verificados` (0-5). Nada de porcentajes ni cifras del portafolio."""
    d = cobertura_data(_cartera_limpia())
    assert set(d.keys()) == {"segmentos", "verificados"}
    for s in d["segmentos"]:
        assert set(s.keys()) == {"clave", "nombre", "estado", "falta", "como"}
        assert s["estado"] in ("ok", "pendiente")


# ── Capa 2 · REGLA 3b (§4.2, corregida por U4bis H1) — dona y etiqueta no se contradicen ──
#
# `_puntuacion_acertividad` (ui/validacion.py) y `cobertura_data` leen las mismas
# señales de datos: unreliable/parcial y posiciones propias excluidas.
#
# U4bis H1 — el invariante queda sobre TRES segmentos: movimientos, posiciones y
# excluidos. Dos quedan FUERA, los dos porque la etiqueta no los lee:
#
# 1. VALORACIÓN: la etiqueta no lee `valuation_date` (hueco documentado desde U4
#    §4.2; PENDIENTE PARA DANIEL: decidir si la etiqueta debe leer la valoración).
# 2. FISCAL: la etiqueta no lee la RESIDENCIA (`rate_declared`), y «Sin declarar» es
#    el default deliberado de la app (`ui/carga.py:236-238`). Con la Regla 3b original
#    (4 segmentos) el estado por defecto de un cliente nuevo pintaba 4/5 con
#    «Confiabilidad alta» — medido por Opus el 22-sep sobre casos reales (IB · 39
#    tickers sin declarar: fiscal pendiente, etiqueta Alta). Por eso este test se
#    PARAMETRIZA POR RESIDENCIA: cada caso corre con país y sin país, porque un 3b
#    que solo existe en la rama «con país» no vigila el estado por defecto (H1.2).
#
# Las dos señales que la etiqueta SÍ lee pero que en la dona aterrizan solo en
# `fiscal` (1042-S que no cuadra, income en alerta) tienen su propio test abajo
# (`test_senal_fiscal_...`): su reflejo en la dona queda fuera del invariante de tres
# y se pinea por separado, medido — no se predice.
#
# La PUERTA DE SESIÓN `_wizard_pos_confirmed` se mantiene FIJA y satisfecha en estas
# fixtures: la etiqueta no la lee y sin ella `posiciones` va pendiente por diseño
# (§4.1/§4.3), no por contradicción. Lo que varía son las señales que AMBAS partes leen.

_CARTERAS_3B = {
    # nombre: (cartera, claves de sesión extra, nivel esperado escrito A MANO)
    # Las 4 que mueven señales que la etiqueta Y los tres segmentos del invariante
    # leen. Los casos cuya señal aterriza solo en `fiscal` están en _CASOS_SENAL_FISCAL.
    "limpia": ({}, {}, "Alta"),
    "unreliable": ({"MSTY_mod": "history_incomplete"}, {}, "Baja"),
    "reconciliada": ({"SCHB_mod": "reconciled"}, {}, "Media"),
    "posicion_propia_excluida": ({"ZZZ_extra": True}, {}, "Media"),
}

_CASOS_SENAL_FISCAL = {
    # Señales que la etiqueta lee (bajan a «Media») pero que en la dona SOLO aterrizan
    # en `fiscal` — segmento fuera del invariante (H1). Medido: etiqueta Media con los
    # tres invariantes verdes y fiscal pendiente, con país y sin país.
    "income_en_alerta": ({"MSTY_hist": [("2025-06-01", "Cash Dividend", 100.0)]},
                         {"_wizard_income_summary": {"tickers": {"MSTY": {"received_total": 5000.0}}}},
                         "Media"),
    "1042s_que_no_cuadra": ({"MSTY_hist": [("2025-06-01", "Cash Dividend", 1000.0)]},
                            {"_wizard_1042s": {"tax_year": 2025, "forms": [
                                {"unique_form_id": "1", "income_code": "06",
                                 "gross_income": 100.0, "federal_tax_withheld": 30.0,
                                 "withholding_credit": 0.0}]}},
                            "Media"),
}


def _cartera_3b(mods):
    cartera = _cartera_limpia()
    if "MSTY_mod" in mods:
        cartera["MSTY"][mods["MSTY_mod"]] = True
    if "SCHB_mod" in mods:
        cartera["SCHB"]["reconciled_from_snapshot"] = True
        cartera["SCHB"]["reconciled_fields"] = ["shares"]
    if "MSTY_hist" in mods:
        cartera["MSTY"]["history"] = _hist(mods["MSTY_hist"])
    if "ZZZ_extra" in mods:
        cartera["ZZZ"] = {"skipped": True, "reason": "held_less_than_14_days",
                          "holding_days": 5}
    return cartera


@pytest.mark.parametrize("nombre", sorted(_CARTERAS_3B))
@pytest.mark.parametrize("residencia", ("con_pais", "sin_pais"))
def test_regla_3b_dona_y_etiqueta_no_se_contradicen(sesion, monkeypatch, nombre, residencia):
    """Regla 3b de U4 (§4.2, corregida por U4bis H1), en las dos direcciones, sobre
    fixtures sintéticos y SOBRE LAS DOS RESIDENCIAS (H1.2: «Sin declarar» es el default
    de la app — un 3b que solo corre con país no vigila el estado por defecto):

    - etiqueta «Alta»  → movimientos, posiciones y excluidos todos verdes;
    - etiqueta «Media»/«Baja» → al menos uno de esos tres pendiente.

    FUERA del invariante, los dos porque la etiqueta no los lee:
    - `valoracion`: `_puntuacion_acertividad` no lee `valuation_date`;
    - `fiscal`: `_puntuacion_acertividad` no lee `rate_declared` (la residencia).
    """
    if residencia == "sin_pais":
        monkeypatch.setattr(estado, "perfil_fiscal",
                            lambda: {"rate_declared": False, "country": None})

    mods, extra_sesion, nivel_esperado = _CARTERAS_3B[nombre]
    cartera = _cartera_3b(mods)
    sesion.update(extra_sesion)

    nivel, _razones = _puntuacion_acertividad(cartera)
    assert nivel == nivel_esperado, (
        f"la fixture {nombre!r} ya no produce el nivel escrito a mano: la señal cambió")

    d = cobertura_data(cartera)
    invariantes = [_seg(d, c)["estado"] for c in
                   ("movimientos", "posiciones", "excluidos")]

    if nivel == "Alta":
        assert invariantes == ["ok"] * 3, (
            f"Regla 3b rota ({residencia}): etiqueta Alta con segmentos pendientes "
            f"{invariantes}")
    else:
        assert "pendiente" in invariantes, (
            f"Regla 3b rota ({residencia}): etiqueta {nivel} con los 3 segmentos verdes")


@pytest.mark.parametrize("nombre", sorted(_CASOS_SENAL_FISCAL))
@pytest.mark.parametrize("residencia", ("con_pais", "sin_pais"))
def test_senal_fiscal_baja_la_etiqueta_y_pinta_solo_el_segmento_fiscal(
        sesion, monkeypatch, nombre, residencia):
    """Los dos casos cuya señal (1042-S que no cuadra, income en alerta) la etiqueta SÍ
    lee —baja a «Media»— pero en la dona aterriza SOLO en `fiscal`, que está fuera del
    invariante de tres (H1). Se pinea el comportamiento MEDIDO (no deducido): etiqueta
    «Media», los tres invariantes verdes, `fiscal` pendiente con país Y sin país.

    Si mañana la etiqueta dejara de leer el 1042-S/income, o la dona moviera esa señal
    a otro segmento, este test lo dice — el 3b de tres segmentos, solo, no se enteraría.
    """
    if residencia == "sin_pais":
        monkeypatch.setattr(estado, "perfil_fiscal",
                            lambda: {"rate_declared": False, "country": None})

    mods, extra_sesion, nivel_esperado = _CASOS_SENAL_FISCAL[nombre]
    cartera = _cartera_3b(mods)
    sesion.update(extra_sesion)

    nivel, _razones = _puntuacion_acertividad(cartera)
    assert nivel == nivel_esperado == "Media", (
        f"la fixture {nombre!r} ya no produce Media: la etiqueta cambió")

    d = cobertura_data(cartera)
    assert [_seg(d, c)["estado"] for c in
            ("movimientos", "posiciones", "excluidos")] == ["ok"] * 3, (
        f"la señal de {nombre!r} se filtró a un segmento del invariante")
    assert _seg(d, "fiscal")["estado"] == "pendiente"


# ── Capa 3 · RENDER — datos, tema y decisiones cerradas (§5.2) ──────────────────────

def _captura_html(monkeypatch):
    from ui import componentes

    caja = {}

    def _fake_html(html, height=None, scrolling=None):
        caja["html"] = html
        caja["height"] = height
        caja["scrolling"] = scrolling

    monkeypatch.setattr(componentes.components, "html", _fake_html)
    return componentes, caja


_DONUT_MIN = {"segmentos": [{"clave": "movimientos", "nombre": "Movimientos",
                             "estado": "pendiente", "falta": "F.", "como": "C."}],
              "verificados": 0}


def test_render_cobertura_inyecta_datos_y_tema_oscuro(monkeypatch):
    componentes, caja = _captura_html(monkeypatch)
    componentes.render_cobertura(_DONUT_MIN, "Oscuro")
    html = caja["html"]
    assert "{{DATA_JSON}}" not in html and "{{" not in html
    assert 'data-theme", "dark"' in html, "el tema no llegó al iframe (lo pone _con_tema)"
    assert '"verificados": 0' in html.replace(" ", "")  or '"verificados":0' in html.replace(" ", "")
    assert caja["height"] == componentes.ALTO_COBERTURA
    assert caja["scrolling"] is False


def test_render_cobertura_inyecta_tema_claro(monkeypatch):
    """§5.2 — el claro/oscuro no llega solo al iframe: se prueba en los dos."""
    componentes, caja = _captura_html(monkeypatch)
    componentes.render_cobertura(_DONUT_MIN, "Claro")
    assert 'data-theme", "light"' in caja["html"]


def test_tokens_de_cobertura_en_los_cuatro_bloques():
    """Mismo guard que impuestos/portafolios: cualquier `var(--x)` usado tiene que estar
    declarado en los 4 bloques (`:root`, `@media dark`, `[data-theme=light]`,
    `[data-theme=dark]`) o cae al color del navegador."""
    ruta = os.path.join(BASE, "ui", "componentes", "cobertura.html")
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    style = src[src.index("<style>"):src.index("</style>")]
    usados = set(re.findall(r"var\((--[\w-]+)\)", src))
    bloques = re.findall(
        r"(?::root(?:\[data-theme=\"\w+\"\])?|@media[^{]+\{\s*:root)\s*\{([^}]*)\}", style)
    assert len(bloques) >= 4, f"esperaba ≥4 bloques de tokens, encontré {len(bloques)}"
    ignora = {"--font-mono", "--font-sans"}
    for tok in sorted(usados - ignora):
        faltan = [i for i, b in enumerate(bloques) if (tok + ":") not in b.replace(" ", "")]
        assert not faltan, f"{tok} usado pero ausente en los bloques de tokens #{faltan}"


def test_componente_sin_superficie_del_prototipo():
    """§5.2 / §4 «Qué NO portar»: sin selector «Cobertura simulada», sin barra de
    laboratorio, sin la palabra «COBERTURA» repetida ni «controles sin alertas» (§3B.7),
    y sin los botones de acción del pop-out (pérdida deliberada — §3B.4: solo qué falta
    y cómo resolverlo).

    Se quitan los comentarios HTML antes de buscar (patrón
    `_sin_cadenas_ni_comentarios` de `test_contrato_componentes.py`): la cabecera del
    componente DOCUMENTA lo que no se portó y nombra esas superficies a propósito; lo
    que el guard vigila es el markup y el script, no la documentación."""
    ruta = os.path.join(BASE, "ui", "componentes", "cobertura.html")
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    cuerpo = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    for prohibido in ("Cobertura simulada", "coverage-demo", "controles sin alertas",
                      "pop-action", "Revisar transacciones", "Revisar posiciones",
                      "Añadir documentos →", "data-preview", "COBERTURA"):
        assert prohibido not in cuerpo, f"superficie del prototipo portada: {prohibido!r}"


def test_movimiento_apagado_con_prefers_reduced_motion():
    """§5.2 — el vaivén de los pendientes se apaga con prefers-reduced-motion."""
    ruta = os.path.join(BASE, "ui", "componentes", "cobertura.html")
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    assert "@media (prefers-reduced-motion: reduce)" in src
    bloque = src.split("@media (prefers-reduced-motion: reduce)")[1][:200]
    assert "animation: none" in bloque


# ── Guards U4bis H2/H3 — el dibujo DEPENDE de los datos (mutantes de Opus, 22-sep) ──

_SCRIPT_RE = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S)


def _script_principal_de_cobertura():
    """El script que dibuja la dona (el primero; el segundo es el auto-alto del iframe).
    Patrón de extracción de `test_contrato_componentes.py`."""
    ruta = os.path.join(BASE, "ui", "componentes", "cobertura.html")
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    cuerpos = _SCRIPT_RE.findall(src)
    assert len(cuerpos) == src.count("<script"), (
        "el regex no extrajo todos los <script>: el guard estaría mirando de menos")
    principal = next((js for js in cuerpos if "function tono" in js), None)
    assert principal is not None, "no encuentro el script que define `tono`"
    return principal


def test_el_tono_de_cada_segmento_depende_de_su_estado():
    """U4bis H2 — el mutante que corrió Opus (`function tono(seg) { return "ok"; }`)
    pintaba los 5 segmentos verdes pase lo que pase y la suite entera seguía en
    `2 failed, 973 passed`: ningún test miraba que el dibujo dependiera de `estado`.

    Guard sobre la fuente: la función que decide el tono (a) LEE `estado`, y (b) no
    tiene ningún camino que devuelva un tono constante (todo `return` de su cuerpo
    referencia el estado del segmento, no un literal suelto).
    """
    js = _script_principal_de_cobertura()
    # Sin cadenas ni comentarios: el cuerpo estructural, no lo que dice la prosa.
    limpio = re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|//[^\n]*|/\*.*?\*/",
                    "", js, flags=re.S)
    m = re.search(r"function\s+tono\s*\([^)]*\)\s*\{([^}]*)\}", limpio)
    assert m, "no encuentro la definición de `tono` en el script"
    cuerpo = m.group(1)
    assert "estado" in cuerpo, (
        "H2: `tono` no lee el `estado` del segmento — la dona pintaría lo mismo con "
        "datos sanos que rotos (mutante `return \"ok\"`)")
    returns = re.findall(r"return\s*([^;]+);", cuerpo)
    assert returns, "H2: `tono` no devuelve nada"
    for expr in returns:
        assert "estado" in expr, (
            f"H2: camino de `tono` con tono constante: `return {expr.strip()}` no "
            "referencia el estado — pinta igual pase lo que pase")


def test_el_centro_de_la_dona_no_recalcula_el_contador():
    """U4bis H3 — `verificados` era un campo muerto: el centro N/5 se recalculaba en JS
    contando tonos, contradiciendo la regla «nada se calcula en JS» (U4 §4) y dejando
    cinco tests que parecían vigilar la cifra del centro sin vigilarla.

    Guard: el contador del centro se LEE de `DATA.verificados` y no existe ningún
    camino que lo derive de los segmentos (nada de `count++`/`count +=`).
    """
    js = _script_principal_de_cobertura()
    assert "DATA.verificados" in js, (
        "H3: el componente no lee `DATA.verificados` — el centro volvió a derivarse "
        "en JS")
    m = re.search(r"var count\s*=\s*([^;]+);", js)
    assert m, "no encuentro la asignación del contador del centro (`var count = …`)"
    assert m.group(1).strip() == "DATA.verificados", (
        f"H3: el centro deriva el contador de los segmentos (`var count = "
        f"{m.group(1).strip()}`) en vez de leer `DATA.verificados`")
    for patron in ("count++", "count += 1", "count+=1", "count = count +"):
        assert patron not in js, f"H3: el contador vuelve a incrementarse en JS ({patron!r})"


# ── Capa 4 · FLUJO (AppTest) — dona arriba, pendientes, residencia, editar ────────────

_SCRIPT = """
import sys
sys.path.insert(0, {path!r})
from ui.carga import render_carga

render_carga()
""".format(path=BASE)


def _df_schwab():
    ruta = os.path.join(BASE, "fixtures", "schwab_synth_1", "synthetic_transactions.csv")
    return logic.normalize_csv(pd.read_csv(ruta))


def _at(timeout=25):
    return AppTest.from_string(_SCRIPT, default_timeout=timeout)


def _ss(at, k):
    """Lectura segura de session_state (patrón `test_privacidad_ui.py::_ss`):
    `SafeSessionState.get` interpreta la clave como widget y lanza KeyError."""
    try:
        return at.session_state[k]
    except Exception:
        return None


def _datos_dona(at):
    """El DATA JSON que la dona recibió, leído del srcdoc del iframe (Regla 3: lo que
    se dibuja es exactamente lo que Python le pasó)."""
    import json

    iframes = at.get("iframe")
    assert len(iframes) == 1, f"esperaba 1 iframe (la dona), vi {len(iframes)}"
    m = re.search(r"var DATA = (\{.*?\});", iframes[0].proto.srcdoc, re.S)
    assert m, "la dona no trae su DATA JSON"
    return json.loads(m.group(1))


def test_dona_va_arriba_del_flujo_de_carga():
    """§5.1.4 — la dona va debajo del wordmark y ARRIBA de los tres bloques (el cambio
    de la integrada v2 respecto de la cobertura al final)."""
    at = _at()
    at.run()
    assert at.exception == []

    orden = list(at.main.children.values())
    tipos = [type(el).__name__ for el in orden]
    # 0 wordmark · 1 lede · 2 iframe (dona) · 3 expander privacidad · 4+ bloques
    assert "UnknownElement" in tipos, "el iframe de la dona no se dibujó"
    idx_dona = tipos.index("UnknownElement")
    assert idx_dona == 2, f"la dona no va justo tras wordmark+lede: {tipos}"
    assert isinstance(orden[0].value, str) and "vd-wordmark" in orden[0].value
    # Todo lo que viene después (expander + bloques) va detrás de la dona.
    assert idx_dona < tipos.index("Expander")


def test_antes_de_confirmar_todo_pendiente_y_analyze_no_corre(monkeypatch):
    """§4.3 + criterio 5 — antes de confirmar posiciones los 5 segmentos van pendientes
    y `analyze_portfolio` NO se llamó (espía sobre `logic.analyze_portfolio`): sería una
    llamada de red de varios segundos en mitad de un formulario (decisión de Daniel,
    18-sep)."""
    llamadas = []
    real = logic.analyze_portfolio

    def espia(*args, **kwargs):
        llamadas.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(logic, "analyze_portfolio", espia)

    at = _at()
    at.session_state["_wizard_df_clean"] = _df_schwab()
    at.session_state["_wizard_csv_ticker_data"] = {}
    at.session_state["_wizard_broker"] = "schwab"
    at.session_state["_wizard_csv_name"] = "synthetic_transactions.csv"
    at.run()
    assert at.exception == []

    d = _datos_dona(at)
    assert d["verificados"] == 0
    assert [s["estado"] for s in d["segmentos"]] == ["pendiente"] * 5
    assert llamadas == [], "la dona disparó analyze_portfolio antes de confirmar"


def test_tras_confirmar_la_dona_lee_el_cache(monkeypatch, request):
    """§4.3 — después de confirmar, la dona SÍ lee los resultados vía
    `ui.vistas.obtener_resultados` (importación diferida). Estados medidos A MANO sobre
    el fixture `schwab_synth_1` con la captura del wizard (`position_overrides`):
    MSTY queda `reconciled` (la captura reconcilia la posición), así que Posiciones va
    PENDIENTE por diseño (§4.1: level ∉ ok/unreliable) y Movimientos verde (reconciled
    no es unreliable). Sin residencia declarada, Fiscal pendiente. Valoración verde
    (todos los tickers publican la misma `valuation_date`) y Excluidos verde (cero
    posiciones propias excluidas; el ruido de AAPL/nan no cuenta)."""
    # Mercado desde el snapshot CONGELADO (historia real: dividendos y splits), no desde
    # Yahoo. Sin esto el test dependía de la red: sin ella MSTY se quedaba sin datos, no
    # llegaba a `reconciled` y Valoración salía pendiente (auditoría M4, H6). Un precio plano
    # tampoco sirve: medido, con él Movimientos sale pendiente — los estados de este fixture
    # dependen de los dividendos y splits reales, no de un precio cualquiera.
    # Mismo patrón que el espía de `analyze_portfolio` del test de arriba.
    import conftest
    monkeypatch.setattr(logic, "fetch_market_data", conftest.mercado_congelado)
    # `analyze_portfolio` va cacheada (`st.cache_data`) y la app la llama con sus propios
    # argumentos: si otro test de la sesión ya la corrió con estos mismos datos, la dona lee
    # ESE resultado y el mock nunca se ejecuta. Medido: solo, el test pasaba; dentro de la
    # suite completa, no. Se limpia al entrar y al salir, como `load_instruments` en
    # test_logic.py.
    logic.analyze_portfolio.clear()
    request.addfinalizer(logic.analyze_portfolio.clear)
    at = _at(timeout=40)
    at.session_state["_wizard_df_clean"] = _df_schwab()
    at.session_state["_wizard_csv_ticker_data"] = {}
    at.session_state["_wizard_broker"] = "schwab"
    at.session_state["_wizard_csv_name"] = "synthetic_transactions.csv"
    at.session_state["_wizard_positions"] = {"MSTY": {"shares": 40.0, "cost_basis": 1000.0}}
    at.session_state["_wizard_pos_confirmed"] = True
    at.run()
    assert at.exception == []

    d = _datos_dona(at)
    assert d["verificados"] == 3
    assert {s["clave"]: s["estado"] for s in d["segmentos"]} == {
        "movimientos": "ok",
        "posiciones": "pendiente",   # MSTY reconciliado desde la captura
        "fiscal": "pendiente",       # nadie declaró residencia en este recorrido
        "valoracion": "ok",
        "excluidos": "ok",
    }


def test_residencia_visible_con_1042s_ya_cargado():
    """Criterio 6 — la residencia va ANTES del retorno temprano de «documentos ya
    cargados»: con el 1042-S leído, el selector sigue visible."""
    at = _at(timeout=40)
    at.session_state["_wizard_df_clean"] = _df_schwab()
    at.session_state["_wizard_csv_ticker_data"] = {}
    at.session_state["_wizard_broker"] = "schwab"
    at.session_state["_wizard_csv_name"] = "synthetic_transactions.csv"
    at.session_state["_wizard_positions"] = {"MSTY": {"shares": 40.0, "cost_basis": 1000.0}}
    at.session_state["_wizard_pos_confirmed"] = True
    at.session_state["_wizard_1042s"] = {
        "tax_year": 2025, "source": "pdfplumber",
        "forms": [{"unique_form_id": "1", "income_code": "06", "gross_income": 28.0,
                   "federal_tax_withheld": 8.0, "withholding_credit": 0.0,
                   "conflict": False}],
    }
    at.run()
    assert at.exception == []
    etiquetas = [s.label for s in at.selectbox]
    assert any("residencia fiscal" in (l or "").lower() for l in etiquetas), (
        f"la residencia desapareció con el 1042-S cargado: {etiquetas}")
    # El resumen del 1042-S convive con el selector.
    assert "1042-S leído" in "\n".join(m.value for m in at.markdown)


def test_residencia_visible_con_broker_ibkr():
    """Criterio 6 — y ANTES del retorno de IBKR: si quedara después, un cliente de IBKR
    nunca podría declarar su país y todas sus cifras fiscales correrían al 30%."""
    at = _at(timeout=40)
    at.session_state["_wizard_df_clean"] = _df_schwab()
    at.session_state["_wizard_csv_ticker_data"] = {}
    at.session_state["_wizard_broker"] = "ibkr"
    at.session_state["_wizard_csv_name"] = "synthetic_transactions.csv"
    at.session_state["_wizard_positions"] = {"MSTY": {"shares": 40.0, "cost_basis": 1000.0}}
    at.session_state["_wizard_pos_confirmed"] = True
    at.run()
    assert at.exception == []
    etiquetas = [s.label for s in at.selectbox]
    assert any("residencia fiscal" in (l or "").lower() for l in etiquetas), (
        f"la residencia desapareció con IBKR: {etiquetas}")
    # El bloque de IBKR («no hace falta») sigue pintado.
    texto = "\n".join(m.value for m in at.markdown)
    assert "Interactive Brokers ya incluye el detalle fiscal" in texto


def test_residencia_declara_pais_desde_el_paso_3():
    """§5.3.2 — persiste por `ui/estado.py::declarar_pais`, no por la clave del widget:
    elegir un país en el paso 3 deja el perfil declarado (mismo patrón que el test de
    `test_perfil_fiscal.py`, pero a través de `render_carga` completa)."""
    at = _at(timeout=40)
    at.session_state["_wizard_df_clean"] = _df_schwab()
    at.session_state["_wizard_csv_ticker_data"] = {}
    at.session_state["_wizard_broker"] = "schwab"
    at.session_state["_wizard_csv_name"] = "synthetic_transactions.csv"
    at.session_state["_wizard_positions"] = {"MSTY": {"shares": 40.0, "cost_basis": 1000.0}}
    at.session_state["_wizard_pos_confirmed"] = True
    at.run()
    assert at.exception == []
    sel = next(s for s in at.selectbox if "residencia fiscal" in (s.label or "").lower())
    sel.select("México").run()
    assert at.exception == []
    assert at.session_state["_perfil_fiscal_pais"] == "México"


def test_paso3_documentos_bajo_un_unico_desplegable():
    """§5.3.3 (§3A.5) — 1042-S + Investment Income quedan bajo un único desplegable
    «Añadir documentos»; los uploaders no cambian (sus claves siguen vivas dentro)."""
    at = _at(timeout=40)
    at.session_state["_wizard_df_clean"] = _df_schwab()
    at.session_state["_wizard_csv_ticker_data"] = {}
    at.session_state["_wizard_broker"] = "schwab"
    at.session_state["_wizard_csv_name"] = "synthetic_transactions.csv"
    at.session_state["_wizard_positions"] = {"MSTY": {"shares": 40.0, "cost_basis": 1000.0}}
    at.session_state["_wizard_pos_confirmed"] = True
    at.run()
    assert at.exception == []
    etiquetas = [e.label for e in at.get("expander")]
    docs = [e for e in etiquetas if "Añadir documentos" in e]
    assert docs, f"no hay desplegable «Añadir documentos»: {etiquetas}"
    # El expander viejo del income ya no existe aparte.
    assert not any("¿Tienes también el Investment Income?" in e for e in etiquetas)
    # Los dos uploaders siguen dentro (mismas claves, sin cambiar su lógica).
    # OJO: en AppTest el `.key` de file_uploader sale None; la clave de usuario vive
    # al final del `proto.id` (`$$ID-<hash>-_vd_upload_1042s`).
    ids = "\n".join(w.proto.id for w in at.get("file_uploader"))
    assert "_vd_upload_1042s" in ids and "_vd_upload_inc" in ids


def test_editar_paso2_vuelve_al_formulario_conservando_el_csv():
    """Criterio 7 — el «editar» del paso 2 confirmado vuelve al formulario CONSERVANDO
    `_wizard_df_clean` (no borra CLAVES_CONTEXTO_CARTERA: eso tiraría el CSV del paso 1)
    y borra solo `_wizard_pos_confirmed`, `_wizard_listo` y `_vd_resultados`."""
    df = _df_schwab()
    at = _at(timeout=40)
    at.session_state["_wizard_df_clean"] = df
    at.session_state["_wizard_csv_ticker_data"] = {}
    at.session_state["_wizard_broker"] = "schwab"
    at.session_state["_wizard_csv_name"] = "synthetic_transactions.csv"
    at.session_state["_wizard_positions"] = {"MSTY": {"shares": 40.0, "cost_basis": 1000.0}}
    at.session_state["_wizard_pos_confirmed"] = True
    at.session_state["_vd_resultados"] = {"MSTY": _stats_ok()}
    at.session_state["_wizard_listo"] = False
    at.run()
    assert at.exception == []

    boton = next((b for b in at.button if b.proto.id.endswith("_vd_edit_pos")), None)
    assert boton is not None, "el paso 2 confirmado no ofrece «editar»"
    boton.click().run()
    assert at.exception == []

    # Volvió al formulario: los number_input de acciones/costo están otra vez.
    assert any(n.proto.id.endswith("_vd_sh_MSTY") for n in at.number_input)
    # Conserva el CSV del paso 1.
    assert at.session_state["_wizard_df_clean"] is not None
    assert at.session_state["_wizard_csv_name"] == "synthetic_transactions.csv"
    # Borra solo lo suyo. (`_ss`, no `.get`: SafeSessionState interpreta `.get` como
    # una clave de widget y lanza KeyError — mismo helper que `test_privacidad_ui.py`.)
    assert _ss(at, "_wizard_pos_confirmed") is False
    assert _ss(at, "_wizard_listo") is False
    assert "_vd_resultados" not in at.session_state.filtered_state


def test_editar_paso2_no_borra_el_contexto_de_captura():
    """El «editar» del paso 2 NO toca `_wizard_ocr_positions` ni `_wizard_photo_sig`:
    la captura leída sigue rellenando la tabla al volver al formulario (a diferencia del
    editar del paso 1, que sí las borra — ahí el CSV cambia y la captura es de otro
    portafolio)."""
    ocr = {"MSTY": {"shares": 999.0, "cost_basis": 12345.0}}
    at = _at(timeout=40)
    at.session_state["_wizard_df_clean"] = _df_schwab()
    at.session_state["_wizard_csv_ticker_data"] = {}
    at.session_state["_wizard_broker"] = "schwab"
    at.session_state["_wizard_csv_name"] = "synthetic_transactions.csv"
    at.session_state["_wizard_positions"] = {"MSTY": {"shares": 40.0, "cost_basis": 1000.0}}
    at.session_state["_wizard_pos_confirmed"] = True
    at.session_state["_wizard_ocr_positions"] = ocr
    at.session_state["_wizard_photo_sig"] = (("captura_A.png", 100),)
    at.run()
    assert at.exception == []

    boton = next((b for b in at.button if b.proto.id.endswith("_vd_edit_pos")), None)
    assert boton is not None
    boton.click().run()
    assert at.exception == []
    assert at.session_state["_wizard_ocr_positions"] == ocr
    assert at.session_state["_wizard_photo_sig"] == (("captura_A.png", 100),)
