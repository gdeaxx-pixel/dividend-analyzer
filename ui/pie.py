"""Pie de resultados (Fase 5a) — fila 26 de `specs/port-artifact/paridad.md`.

Decisión de Daniel (traspaso § Fase 5): estas secciones globales van en un pie único al
final de resultados, siempre visible, en vez de repetirse por vista. Regla de método de
esta fase: se copia la lógica y el texto literal de `app_old.py`, re-vestido con
`ui/tokens.py` — no se redactan de nuevo los textos ni se reinterpretan las cifras.

Las filas 22-24 (calidad de datos, notas técnicas, excluidos) y el banner 1042-S, antes
aquí y en `ui.vistas` respectivamente, se movieron a `ui.validacion` (2026-08-10):
Daniel pidió consolidar toda señal de confiabilidad en un solo panel «Validación datos»
detrás del menú de 3 puntos de la ruta, en vez de tenerlas sueltas por la página. La
descarga del reporte PDF (antes fila 37 aquí) se movió al mismo menú, en `ui.chrome`.
«Otras calculadoras» (antes fila 25, un expander aquí) se movió al mismo menú por el
mismo pedido — `render_calculadoras` sigue viviendo en este módulo (es su dueño
histórico) pero ahora la llama `ui.vistas` como panel de pantalla completa, no
`render_pie`.

Fuentes en `app_old.py`:
- Fila 25 — `app_old.py:6396-6412`, texto literal.
- Fila 26 — `app_old.py:6417-6432`, texto literal.
"""

from __future__ import annotations

import streamlit as st


def render_calculadoras() -> None:
    """Panel «Otras calculadoras» (antes fila 25, expander fijo del pie). Texto literal
    de `app_old.py:6396-6412`; el título del menú lo puso Daniel («Otras calculadoras»,
    2026-08-11) — el badge de arriba lo repite, sin la coletilla larga original."""
    st.markdown('<span class="vd-badge">Otras calculadoras</span>', unsafe_allow_html=True)
    st.markdown(
        "Esta herramienta se construyó estudiando las mejores calculadoras públicas de "
        "dividendos y tomando lo útil de cada una, pero con un principio propio: "
        "**realismo**, sobre todo en los ETF de alto rendimiento (YieldMax), donde el "
        "*yield* de portada engaña.\n\n"
        "- **[TipRanks](https://www.tipranks.com/tools/dividend-calculator)** y "
        "**[DividendCalculator.io](https://dividendcalculator.io/)** — proyección con "
        "DRIP, *yield on cost* y *forward yield*. → de aquí tomamos el **motor de "
        "proyección a futuro** y el *forward yield* vs realizado.\n"
        "- **[MiniWebtool](https://miniwebtool.com/dividend-reinvestment-calculator/)** y "
        "**[MarketBeat](https://www.marketbeat.com/dividends/calculator/)** — tabla año "
        "por año y efecto *bola de nieve* de la reinversión. → la **visualización del "
        "interés compuesto**.\n"
        "- **[DRIPCalc](https://www.dripcalc.com/yieldmax-etfs/)** — retorno con y sin "
        "DRIP para fondos YieldMax. → la **comparación reinvertir vs cobrar en "
        "efectivo**.\n"
        "- **[NAV Erosion Calculator](https://dividend-wealth.com/tools/nav-erosion-calculator)** "
        "— la carrera *ingreso acumulado* vs *pérdida de capital* con punto de "
        "*breakeven*. → nuestro **modo realista YieldMax**.\n\n"
        "**Lo que ninguna hace y aquí sí:** descomponer cuánto de cada distribución es "
        "**Retorno de Capital** (datos oficiales 19a) y proyectar con la **erosión real "
        "observada** del fondo, en vez de asumir que el precio sube. Por eso un YieldMax "
        "nunca se proyecta como si fuera un ETF de crecimiento.")


HTML_REGLA = '<hr class="vd-pie-regla">'

HTML_DISCLAIMER = (
    '<div class="vd-pie-legal">'
    '<span class="vd-pie-legal-badge">Versión Beta</span>'
    '<p class="vd-pie-legal-titulo">Esta herramienta es de carácter informativo y '
    'estimativo — no constituye asesoría financiera.</p>'
    '<p class="vd-pie-legal-cuerpo1">Los datos, cálculos y proyecciones pueden '
    'presentar errores o inexactitudes. Siempre verifica con tus propios registros o '
    'los estados de cuenta de tu casa de bolsa.</p>'
    '<p class="vd-pie-legal-cuerpo2">El uso de esta aplicación es bajo tu propio '
    'riesgo. Reporta cualquier fallo o inconsistencia para ayudarnos a seguir '
    'mejorando.</p>'
    "</div>"
)


def _render_disclaimer() -> None:
    """Fila 26 — texto literal de `app_old.py:6417-6432`, re-vestido con tokens (fuera los
    hex de `#f0eeec`/`#e0ddd9`/`#555`/`#888`/`#aaa` de la versión de `app_old.py`).

    El HTML vive en `HTML_DISCLAIMER` (constante del módulo) para que
    `design/previews/build_pie_preview.py` lo reuse tal cual, sin duplicarlo."""
    st.markdown(HTML_DISCLAIMER, unsafe_allow_html=True)


def render_pie(resultados: dict) -> None:
    """Punto único de entrada: el pie, siempre visible al final de resultados."""
    if not resultados:
        return
    st.markdown(HTML_REGLA, unsafe_allow_html=True)
    _render_disclaimer()


ESTILOS_PIE = """
        .vd-pie-regla { border: none; border-top: 1px dashed var(--hair); margin: 16px 0 10px; }
        .vd-pie-legal {
          background: var(--panel-tint); font-family: var(--font-mono);
          padding: 8px 12px; margin-top: 0;
        }
        .vd-pie-legal-badge {
          display: inline-block; font-size: 8px !important;
          font-weight: 700; letter-spacing: .1em; text-transform: uppercase;
          color: var(--ink-mut); border: 1px solid var(--hair); padding: 1px 4px;
          margin-bottom: 4px;
        }
        .vd-pie-legal-titulo {
          font-size: 9.5px !important; font-weight: 700; letter-spacing: .01em;
          color: var(--ink-2); margin: 0 0 2px !important; line-height: 1.3 !important;
        }
        .vd-pie-legal-cuerpo1 {
          font-size: 8.5px !important; color: var(--ink-mut); line-height: 1.35 !important;
          margin: 0 0 1px !important;
        }
        .vd-pie-legal-cuerpo2 {
          font-size: 8.5px !important; color: var(--ink-mut); line-height: 1.35 !important;
          margin: 0 !important; opacity: .8;
        }
"""
