"""Fase 4 del plan de remediación — Clase D (sesgo de pérdida cableado) + la cita
congelada de `ui/componentes/metodologia.html` § 9.

Parte 1 — `ui/componentes/hoja.html` y `ui/componentes/cashflow.html` asumían que el
usuario siempre iba perdiendo: `Math.abs()` sin signo, clases de color
`"he-loss"`/`"dn"`/`"s-loss"` hardcodeadas y verbos ("perdiste", "se destruyeron", "la
caída del precio", "eso es lo que el mercado se llevó") que no seguían el dato. Con una
posición ganadora, la UI mentía. Estos tests son ESTRUCTURALES — mismo patrón que
`test_metodo_data.py`/`test_comparacion_data.py`: no hay motor JS en el harness de
Python, así que lo que se protege es que la condicional exista en el código fuente, no
su ejecución. La ejecución (ambos signos, luz verde y roja, claro y oscuro) se verificó
en vivo en el navegador — con datos reales (`?demo=ib`, NVDY: `MERCADO` negativo pero
`RESULTADO` positivo, un caso mixto) y con un fixture sintético para el caso 100%
perdedor, que no existe en los datos reales disponibles (los 4 tickers de
`real_examples/` terminan todos en ganancia total, aunque con un impacto de mercado
negativo — ver PR).

Parte 2 — `ui/componentes/metodologia.html` § 9 («Anualizar bien») citaba a mano
+50.2%/16.7%/+14.5%/29.9×/34×, copiados de la sección «Método tradicional» de
`metodo.html` ANTES de que la Fase 3.3b la cableara a datos reales. El literal quedó
mudo: en cuanto el mercado se movió, dejó de coincidir con su propia fuente — el mismo
defecto que originó toda esta remediación (`ROC_19A` congelado). Ahora las tres primeras
cifras se recalculan en cada carga desde `ui.adapters.metodo_data()["tot"]` (el mismo
`TOT.val`/`TOT.inv` que ya usa `metodo.html` para `mCmpCorrectPct`) vía
`render_metodologia(..., datos=...)`; el «anuncio original» (1499%/499%) es una cita
textual de la clase grabada y se queda fijo a propósito.
"""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import ui.componentes as componentes  # noqa: E402

_HOJA = os.path.join(os.path.dirname(__file__), "ui", "componentes", "hoja.html")
_CASHFLOW = os.path.join(os.path.dirname(__file__), "ui", "componentes", "cashflow.html")
_METODOLOGIA = os.path.join(os.path.dirname(__file__), "ui", "componentes", "metodologia.html")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ── Parte 1a — hoja.html: retornoCell y las dos conclusiones siguen el signo ────────────

def test_hoja_retorno_cell_sigue_el_signo():
    html = _read(_HOJA)
    # El bug: `setHtml(id, '<span class="he-loss">' + signed(val) + ...` — la clase
    # estaba hardcodeada, sin mirar el signo de `val`.
    assert '<span class="he-loss">' not in html, (
        "retornoCell vuelve a pintar de rojo cualquier valor — no mira el signo")
    assert re.search(r'val\s*>=\s*0\s*\?\s*"he-cash"\s*:\s*"he-loss"', html), (
        "retornoCell ya no elige la clase según el signo de `val`")


def test_hoja_he_c_he_loss_tiene_selector_descendiente():
    """`.he-c.he-loss` (compuesto, sin espacio) nunca puede coincidir con el <span> que
    arma `retornoCell` — vive DENTRO de un `div.he-c`, no ES un `div.he-c`. Sin el
    selector descendiente `.he-c .he-loss` la celda no se pinta con NINGÚN signo (bug
    real encontrado en la Fase 4: el rojo llevaba roto para ganador Y perdedor)."""
    html = _read(_HOJA)
    assert re.search(r'\.he-c\.he-loss\s*,\s*\.he-c \.he-loss\s*\{', html), (
        "falta el selector descendiente — retornoCell dejaría de colorear la celda "
        "sin importar el signo")
    assert re.search(r'\.he-c\.he-cash\s*,\s*\.he-c \.he-cash\s*\{', html)


def test_hoja_compare_naive_sigue_el_signo():
    html = _read(_HOJA)
    assert "Tu hoja dice que perdiste <b>" not in html, (
        "heCompareNaive vuelve a decir «perdiste» sin mirar el signo de APARENTE")
    assert re.search(r'APARENTE\s*>=\s*0\s*\?\s*"ganaste"\s*:\s*"perdiste"', html)


def test_hoja_compare_honest_sigue_el_signo():
    html = _read(_HOJA)
    assert '\'<b class="dn">\' + signed(RESULTADO)' not in html, (
        "heCompareHonest vuelve a pintar RESULTADO de rojo sin mirar el signo")
    assert "la pérdida real es '" not in html, (
        "heCompareHonest vuelve a decir «la pérdida real es» sin mirar el signo "
        "de RESULTADO")
    assert re.search(
        r'RESULTADO\s*>=\s*0\s*\?\s*"la ganancia real es"\s*:\s*"la pérdida real es"',
        html)


def test_hoja_lede_sigue_el_signo():
    """La lede estática decía "por qué la pérdida que muestra no es la real" sin
    importar si la hoja mostraba una ganancia o una pérdida (Clase D)."""
    html = _read(_HOJA)
    assert "la pérdida que muestra <b>" not in html, (
        "la lede de Hoja Excel volvió a asumir una pérdida en texto estático")
    assert re.search(
        r'APARENTE\s*>=\s*0\s*\?\s*"la ganancia"\s*:\s*"la pérdida"', html)


# ── Parte 1b — cashflow.html: MERCADO, gap-band y "se destruyeron" ──────────────────────

def test_cashflow_mercado_sigue_el_signo():
    html = _read(_CASHFLOW)
    assert 'amt:"−$" + Math.abs(MERCADO).toFixed(2), cap:"dn"' not in html, (
        "la columna «Impacto del mercado» vuelve a asumir pérdida — signo, color y "
        "clase del segmento hardcodeados")
    assert re.search(r'mercadoCap\s*=\s*MERCADO\s*>=\s*0\s*\?\s*"up"\s*:\s*"dn"', html)
    assert re.search(
        r'mercadoSegCls\s*=\s*MERCADO\s*>=\s*0\s*\?\s*"s-gain"\s*:\s*"s-loss"', html)
    assert re.search(
        r'mercadoVerbo\s*=\s*MERCADO\s*>=\s*0\s*\?\s*"La subida"\s*:\s*"La caída"', html)
    # El segmento del waterfall usa la variable, no el literal "s-loss" cableado.
    assert re.search(r'cls\s*:\s*mercadoSegCls', html)
    assert '.seg.s-gain' in html, "falta el color del segmento ganador"


def test_cashflow_gap_band_sigue_el_signo():
    """Antes: alto = `(POCKET - CAPITAL_ACTUAL) * sc` — negativo (CSS inválido, la
    franja no se dibujaba) en cuanto `CAPITAL_ACTUAL > POCKET`, y el rótulo llevaba
    "−$" cableado. Con una posición ganadora la franja debe existir Y decir "+$"."""
    html = _read(_CASHFLOW)
    assert 'gap.innerHTML = "<span>−$" + Math.abs(RESULTADO)' not in html, (
        "el rótulo de la franja vuelve a llevar el signo negativo cableado")
    assert re.search(r'gapGain\s*=\s*RESULTADO\s*>=\s*0', html)
    assert re.search(r'Math\.min\(POCKET,\s*CAPITAL_ACTUAL\)', html), (
        "la franja ya no recalcula lo/hi con Math.min/max — con RESULTADO positivo "
        "el alto vuelve a poder salir negativo")
    assert ".gap-band.gap-gain" in html, "falta la variante de color ganadora"


def test_cashflow_se_destruyeron_es_condicional():
    html = _read(_CASHFLOW)
    # El patrón viejo: una sola plantilla de texto que siempre dice "se destruyeron",
    # incluso cuando `pctDead` es 0.
    assert re.search(r'pctDead\s*>\s*0\s*\n?\s*\?', html), (
        "el mosaico final volvió a decir «se destruyeron» sin comprobar si de "
        "verdad hubo algo destruido")
    assert "ninguno se destruyó" in html


def test_cashflow_resultado_real_td_sigue_el_signo():
    html = _read(_CASHFLOW)
    assert '"La diferencia es lo que el mercado se llevó."' not in html
    assert re.search(r'RESULTADO\s*>=\s*0\s*\?\s*"sumó"\s*:\s*"se llevó"', html)


def test_cashflow_stepnote_final_sigue_el_signo():
    html = _read(_CASHFLOW)
    assert re.search(r'RESULTADO\s*>=\s*0\s*\n?\s*\?', html.split("function render(step)")[1][:4000]), (
        "el texto del paso 8 (stepNote) no distingue ganador/perdedor")
    assert "el mercado sumó" in html


# ── Parte 2 — metodologia.html § 9: ya no cita literales congelados ─────────────────────

def test_metodologia_no_tiene_los_literales_congelados():
    """Los cinco literales (`+50.2%`, `16.7%`, `+14.5%`, `29.9×`, `34×`) copiados a mano
    de la sección «Escalera» de `metodo.html` (que en la Fase 4 SIGUE congelada a la
    hoja del 5/1/2026 — solo «La matriz», Bloque 1/2, se cableó en la Fase 3.3b) no
    pueden reaparecer como texto fijo: divergen de su propia fuente en cuanto el
    mercado se mueve, el mismo defecto que originó el ROC 19(a) congelado."""
    html = _read(_METODOLOGIA)
    for literal in ("+50.2%", "16.7%", "+14.5%", "29.9×", "34×"):
        assert literal not in html, (
            f"el literal congelado {literal!r} volvió a aparecer en metodologia.html")


def test_metodologia_tiene_el_punto_de_inyeccion_y_los_ids():
    html = _read(_METODOLOGIA)
    assert "{{DATA_JSON}}" in html, "falta el punto de inyección {{DATA_JSON}}"
    for el_id in ("mtAnTotal", "mtAnNaive", "mtAnCagr", "mtAnMultTot", "mtAnMultAnual"):
        assert f'id="{el_id}"' in html, f"falta <b id=\"{el_id}\"> en la § 9"
    # El "anuncio original" (1499%/499%) es una cita textual de la clase grabada — SÍ
    # se queda fijo, a propósito. No confundir con las cifras derivadas de arriba.
    assert "1499%" in html and "499%/año" in html


def test_metodologia_calcula_desde_tot_con_la_misma_formula_que_metodo_html():
    """`correctPct` en `metodo.html` (Bloque 1/2, ya cableado en la Fase 3.3b) es
    `(TOT.val - TOT.inv) / TOT.inv * 100` — la misma fórmula tiene que vivir en
    metodologia.html § 9 para que ambas páginas no puedan divergir por lógica distinta,
    solo por redondeo de presentación."""
    html = _read(_METODOLOGIA)
    assert re.search(
        r'real\s*=\s*\(TOT\.val\s*-\s*TOT\.inv\)\s*/\s*TOT\.inv\s*\*\s*100', html), (
        "la § 9 no deriva el retorno real de TOT.val/TOT.inv — ¿volvió a hardcodearlo?")
    assert re.search(r'var\s+N\s*=\s*3', html), "la convención N=3 años debe ser explícita"
    assert re.search(r'Math\.pow\(1\s*\+\s*real\s*/\s*100,\s*1\s*/\s*N\)', html), (
        "el CAGR debe componer (Math.pow), no dividir (real/N) — esa es justo la "
        "confusión que denuncia esta sección")


def test_metodologia_degrada_con_gracia_sin_datos():
    """Si `metodo_data()` no pudo bajar historia (`None`), la sección no puede dejar
    los números viejos mudos en pantalla sin avisar — debe mostrar un aviso explícito."""
    html = _read(_METODOLOGIA)
    assert "!D || !D.tot" in html or "!D.tot" in html
    assert "No se pudo recalcular" in html


# ── Parte 2 — wiring Python (render_metodologia / vistas.py) ────────────────────────────

def test_render_metodologia_inyecta_datos_reales(monkeypatch):
    capturado = {}

    def _fake_html(html, height=None, scrolling=None):
        capturado["html"] = html

    monkeypatch.setattr(componentes.components, "html", _fake_html)

    datos = {"tot": {"inv": 48286.22, "val": 77194.64, "div": 165780.09, "ult": 703.75}}
    componentes.render_metodologia("Claro", datos=datos)

    assert "html" in capturado, "render_metodologia no llamó a components.html"
    assert json.dumps(datos, ensure_ascii=False) in capturado["html"], (
        "el DATA_JSON inyectado no es el `datos` que se pasó")
    assert "{{DATA_JSON}}" not in capturado["html"], "quedó el placeholder sin reemplazar"


def test_render_metodologia_sin_datos_inyecta_null(monkeypatch):
    capturado = {}

    def _fake_html(html, height=None, scrolling=None):
        capturado["html"] = html

    monkeypatch.setattr(componentes.components, "html", _fake_html)

    componentes.render_metodologia("Claro", datos=None)

    assert "var D = null;" in capturado["html"], (
        "sin `datos`, el componente debe recibir `null` explícito — nunca el "
        "placeholder sin reemplazar ni un valor inventado")


def test_vistas_metodologia_reusa_el_cache_de_metodo_data():
    """`render_metodo_tradicional` y la rama `metodologia` de `render_vista` deben usar
    la MISMA llave de sesión (`_vd_metodo_data`) — dos descargas de historia para el
    mismo caso de estudio fijo sería trabajo duplicado."""
    with open(os.path.join(os.path.dirname(__file__), "ui", "vistas.py"), encoding="utf-8") as f:
        src = f.read()
    ocurrencias = src.count('st.session_state.get("_vd_metodo_data")')
    assert ocurrencias >= 2, (
        "la rama de metodología ya no reusa `_vd_metodo_data` — volvería a bajar "
        "la historia del caso de estudio por separado")
    assert "render_metodologia(ruta.tema" in src and "datos=" in src
