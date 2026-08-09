"""Pie único de resultados (Fase 5a) — filas 22-26 de `specs/port-artifact/paridad.md`.

Decisión de Daniel (traspaso § Fase 5): estas cinco secciones globales van en un pie
único al final de resultados, siempre visible, en vez de repetirse por vista. Regla de
método de esta fase: se copia la lógica y el texto literal de `app_old.py`, re-vestido con
`ui/tokens.py` — no se redactan de nuevo los textos ni se reinterpretan las cifras.

Fuentes en `app_old.py`:
- Fila 22 — `_render_data_quality_panel` (`app_old.py:4031`), dentro del expander de
  `app_old.py:6074`. La validación cruzada del 1042-S (tercera fuente) que ese panel también
  dibuja ya vive en el banner persistente `ui.vistas.render_1042s_card` desde la Fase 3 —
  no se duplica aquí.
- Fila 23 — recolección de `_tech_events` (splits, reconciliaciones, dividendos
  especiales) a lo largo de `app_old.py:5106-5158`, tabla en `app_old.py:6094`.
- Fila 24 — `app_old.py:6382-6395` (tickers con `skipped=True` de `analyze_portfolio`, no
  confundir con los `mode_skip` de `classify_tickers` que ya se muestran en el Bloque 2
  de la carga — son dos exclusiones distintas, mapa-datos.md § no aplica, ver logic.py).
- Fila 25 — `app_old.py:6396-6412`, texto literal.
- Fila 26 — `app_old.py:6417-6432`, texto literal.
"""

from __future__ import annotations

import streamlit as st

import logic

_QUALITY_STYLE = {
    "unreliable": ("--warn", "No confiable"),
    "reconciled": ("--accent", "Reconciliado desde tu captura"),
    "partial": ("--ink-mut", "Parcial"),
}

_RECON_STYLE = {
    "ok": "--cash",
    "warn": "--warn",
    "info": "--ink-mut",
}

_RECON_LABEL = {
    "match": "Validado",
    "cusip_folded": "Validado (identidad CUSIP plegada)",
    "csv_window_longer": "Validado en ventana común",
    "income_higher": "Faltan dividendos en el CSV",
    "csv_overcount_suspected": "Posible sobre-conteo del CSV",
    "csv_higher": "El CSV reporta de más",
    "missing_in_income": "Sin cobertura en el income",
    "missing_in_csv": "Solo en el income (vendido)",
}

_SKIP_REASON = {
    "not_known_etf": "No reconocido como ETF de largo plazo (acción individual, ETF inverso o apalancado)",
    "held_less_than_14_days": "Posición cerrada en {days} días (< 2 semanas)",
}


def _tarjeta(accent_var: str, titulo_html: str, cuerpo_html: str) -> str:
    return (f'<div class="vd-pie-card" style="border-left-color: var({accent_var});">'
            f'<p class="vd-pie-card-titulo">{titulo_html}</p>{cuerpo_html}</div>')


def _render_calidad_datos(resultados: dict) -> None:
    """Fila 22 — calidad de datos y validación cruzada de ingresos."""
    classify_map = logic.classify_tickers(list(resultados.keys()))
    dq = logic.assess_data_quality(resultados, classify_map)
    no_ok = {t: q for t, q in dq.items() if q["level"] != "ok"}

    st.markdown('<p class="vd-pie-subtitulo">Calidad de datos</p>', unsafe_allow_html=True)
    if no_ok:
        st.markdown(
            '<p class="vd-pie-nota">Cuando el CSV no trae el historial completo, usamos tu '
            'captura del broker (acciones y costo) para reconciliar la posición; los tickers '
            'no reconciliados se marcan y se excluyen del % en el tiempo.</p>',
            unsafe_allow_html=True)
        for ticker, q in no_ok.items():
            accent_var, etiqueta = _QUALITY_STYLE.get(q["level"], _QUALITY_STYLE["partial"])
            accion = (f'<p class="vd-pie-card-accion">→ {q["action"]}</p>' if q.get("action") else "")
            st.markdown(
                _tarjeta(accent_var,
                        f'{ticker} · <span style="color: var({accent_var});">{etiqueta}</span>',
                        f'<p class="vd-pie-card-cuerpo">{q["reason"]}</p>{accion}'),
                unsafe_allow_html=True)
    else:
        st.markdown(
            _tarjeta("--cash", f"Datos completos · {len(resultados)} posiciones verificadas", ""),
            unsafe_allow_html=True)

    ingreso = st.session_state.get("_wizard_income_summary")
    if ingreso and ingreso.get("tickers"):
        recon = logic.reconcile_income(resultados, ingreso)
        if recon:
            n_ok = sum(1 for r in recon.values() if r["badge"] == "ok")
            n_warn = sum(1 for r in recon.values() if r["badge"] == "warn")
            orden = {"warn": 0, "ok": 1, "info": 2}
            st.markdown('<p class="vd-pie-subtitulo">Validación cruzada de ingresos</p>',
                        unsafe_allow_html=True)
            st.markdown(
                '<p class="vd-pie-nota">Comparamos el dividendo bruto del CSV contra tu '
                f'reporte de ingresos del broker (segunda fuente). {n_ok} validado(s), '
                f'{n_warn} con alerta. Las proyecciones "Estimated" del broker no se usan.</p>',
                unsafe_allow_html=True)
            for ticker, r in sorted(recon.items(), key=lambda kv: (orden.get(kv[1]["badge"], 3), kv[0])):
                accent_var = _RECON_STYLE.get(r["badge"], _RECON_STYLE["info"])
                etiqueta = _RECON_LABEL.get(r["status"], r["status"])
                csv_v = f"${r['csv_total']:,.2f}" if r.get("csv_total") is not None else "—"
                inc_v = f"${r['income_total']:,.2f}" if r.get("income_total") is not None else "—"
                ventana = ""
                if (r.get("csv_in_window") is not None and r.get("csv_total") is not None
                        and abs(r["csv_in_window"] - r["csv_total"]) > 0.01):
                    ventana = f' (en ventana común: ${r["csv_in_window"]:,.2f})'
                st.markdown(
                    _tarjeta(accent_var,
                            f'{ticker} · <span style="color: var({accent_var});">{etiqueta}</span>',
                            f'<p class="vd-pie-card-cuerpo">Dividendo bruto — CSV: <b>{csv_v}</b>'
                            f'{ventana} · Broker recibido: <b>{inc_v}</b></p>'
                            f'<p class="vd-pie-card-accion">{r["note"]}</p>'),
                    unsafe_allow_html=True)


def _tech_events(resultados: dict) -> list[dict]:
    """Replica la recolección de `_tech_events` de `app_old.py:5106-5158`, sin depender de
    dibujarse mientras se recorre cada ticker: aquí no hay ese recorrido de UI, así que
    se reconstruye desde `stats` directamente."""
    eventos = []
    for ticker, stats in resultados.items():
        if not isinstance(stats, dict) or stats.get("skipped"):
            continue
        for split in stats.get("splits_detected", []):
            ratio = split["ratio"]
            tipo = "Split" if ratio > 1 else "Reverse Split"
            eventos.append({"date": split["date"], "ticker": ticker, "tipo": tipo,
                            "desc": f"{ratio:.0f}:1 — las cantidades de acciones se ajustaron automáticamente."})

        calidad = logic.assess_ticker_quality(resultados, ticker)
        if calidad["level"] == "reconciled":
            eventos.append({"date": "", "ticker": ticker, "tipo": "Reconciliación",
                            "desc": f"Reconciliado desde tu captura: {calidad['reason']}"})

        for accion in stats.get("corporate_actions", []):
            if accion["type"] == "Dividendo especial":
                eventos.append({"date": accion["date"], "ticker": ticker, "tipo": "Dividendo especial",
                                "desc": f"${accion.get('amount', 0):.4f} por acción"})
    return eventos


def _render_notas_tecnicas(resultados: dict) -> None:
    """Fila 23 — notas técnicas y eventos corporativos detectados."""
    eventos = sorted(_tech_events(resultados),
                     key=lambda e: (e.get("date") or "9999-99", e.get("ticker", "")))
    if not eventos:
        return
    with st.expander(f"Notas técnicas y eventos corporativos detectados · {len(eventos)} evento(s)"):
        filas = "".join(
            '<tr class="vd-pie-fila">'
            f'<td class="vd-pie-celda vd-pie-celda-fecha">{e["date"] or "—"}</td>'
            f'<td class="vd-pie-celda vd-pie-celda-ticker">{e["ticker"]}</td>'
            f'<td class="vd-pie-celda vd-pie-celda-tipo">{e["tipo"]}</td>'
            f'<td class="vd-pie-celda">{e["desc"]}</td>'
            "</tr>"
            for e in eventos)
        st.markdown(
            '<table class="vd-pie-tabla"><thead><tr>'
            '<th class="vd-pie-th">Fecha</th><th class="vd-pie-th">Ticker</th>'
            '<th class="vd-pie-th">Evento</th><th class="vd-pie-th">Detalle</th>'
            f"</tr></thead><tbody>{filas}</tbody></table>",
            unsafe_allow_html=True)
        st.caption("Eventos detectados automáticamente al procesar tu archivo (splits, "
                  "reconciliaciones desde captura y dividendos especiales). Las cantidades "
                  "y métricas ya están ajustadas.")


def _render_excluidos(resultados: dict) -> None:
    """Fila 24 — tickers excluidos del análisis (`skipped` de `analyze_portfolio`; no
    confundir con los `mode_skip` de `classify_tickers` que se muestran en el Bloque 2
    de la carga — son dos exclusiones distintas)."""
    excluidos = {t: s for t, s in resultados.items() if isinstance(s, dict) and s.get("skipped")}
    if not excluidos:
        return
    with st.expander(f"{len(excluidos)} ticker(s) excluidos del análisis"):
        for ticker, s in excluidos.items():
            razon = s.get("reason", "")
            if razon == "held_less_than_14_days":
                etiqueta = _SKIP_REASON[razon].format(days=s.get("holding_days", "?"))
            else:
                etiqueta = _SKIP_REASON.get(razon, "Excluido")
            st.markdown(f'<p class="vd-pie-excluido">— <b>{ticker}</b> · '
                        f'<span class="vd-pie-excluido-razon">{etiqueta}</span></p>',
                        unsafe_allow_html=True)


def _render_calculadoras() -> None:
    """Fila 25 — texto literal de `app_old.py:6396-6412`."""
    with st.expander("Calculadoras de referencia — en qué nos inspiramos y en qué nos diferenciamos"):
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


def _render_disclaimer() -> None:
    """Fila 26 — texto literal de `app_old.py:6417-6432`, re-vestido con tokens (fuera los
    hex de `#f0eeec`/`#e0ddd9`/`#555`/`#888`/`#aaa` de la versión de `app_old.py`)."""
    st.markdown(
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
        "</div>", unsafe_allow_html=True)


def _render_reporte_pdf(resultados: dict) -> None:
    """Fila 37 — descarga del reporte PDF. Literal de `app_old.py:5271-5282`: `report.py`
    y `test_report.py` no se tocan, solo se cablea el botón. `try/except` porque el
    original también lo protege (un reporte que falla no debe romper el pie)."""
    try:
        from datetime import date as _date

        from report import generate_report_pdf

        broker = st.session_state.get("_wizard_broker") or "schwab"
        pdf_bytes = generate_report_pdf(resultados, broker, version="2.0")
        st.download_button(
            label="Descargar Reporte PDF",
            data=pdf_bytes,
            file_name=f"auditoria-portafolio-{_date.today().isoformat()}.pdf",
            mime="application/pdf",
        )
    except Exception:
        pass


def render_pie(resultados: dict) -> None:
    """Punto único de entrada: el pie completo, siempre visible al final de resultados."""
    if not resultados:
        return
    st.markdown('<hr class="vd-pie-regla">', unsafe_allow_html=True)
    with st.expander("Calidad de datos y validación cruzada de ingresos"):
        st.caption("Detalle técnico: cómo se reconciliaron tus posiciones y la "
                  "verificación del dividendo bruto contra el reporte de ingresos del "
                  "broker.")
        _render_calidad_datos(resultados)
    _render_notas_tecnicas(resultados)
    _render_excluidos(resultados)
    _render_calculadoras()
    _render_reporte_pdf(resultados)
    _render_disclaimer()


ESTILOS_PIE = """
        .vd-pie-regla { border: none; border-top: 1px dashed var(--hair); margin: 40px 0 24px; }
        .vd-pie-subtitulo {
          font-family: var(--font-mono); font-size: 12px; font-weight: 700;
          letter-spacing: .05em; text-transform: uppercase; color: var(--ink);
          margin: 14px 0 4px;
        }
        .vd-pie-nota { font-size: 12px; color: var(--ink-mut); margin: 0 0 8px; }
        .vd-pie-card {
          border-left: 3px solid var(--hair); background: var(--panel-tint);
          padding: 8px 14px; margin: 8px 0;
        }
        .vd-pie-card-titulo {
          font-family: var(--font-mono); font-size: 12px; font-weight: 700;
          color: var(--ink); margin: 0;
        }
        .vd-pie-card-cuerpo { font-size: 12px; color: var(--ink-2); margin: 3px 0 0; }
        .vd-pie-card-accion { font-size: 12px; color: var(--accent); margin: 3px 0 0; }
        .vd-pie-tabla { width: 100%; border-collapse: collapse; margin-top: 2px; }
        .vd-pie-th {
          padding: 7px 14px; text-align: left; font-family: var(--font-mono);
          font-size: 9px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
          color: var(--ink-mut); border-bottom: 2px solid var(--ink);
        }
        .vd-pie-fila { border-bottom: 1px solid var(--hair-soft); }
        .vd-pie-celda { padding: 7px 14px; font-size: 11.5px; color: var(--ink-2); }
        .vd-pie-celda-fecha {
          font-family: var(--font-mono); font-size: 11px; color: var(--ink-mut);
          white-space: nowrap;
        }
        .vd-pie-celda-ticker { font-weight: 700; color: var(--ink); }
        .vd-pie-celda-tipo { font-weight: 600; color: var(--accent); white-space: nowrap; }
        .vd-pie-excluido { font-size: 12px; color: var(--ink-2); margin: 2px 0; }
        .vd-pie-excluido-razon { color: var(--ink-mut); }
        .vd-pie-legal {
          background: var(--panel-tint); border-top: 1px solid var(--hair);
          padding: 24px 28px; margin-top: 32px;
        }
        .vd-pie-legal-badge {
          display: inline-block; font-family: var(--font-mono); font-size: 9px;
          font-weight: 700; letter-spacing: .12em; text-transform: uppercase;
          color: var(--ink-mut); border: 1px solid var(--hair); padding: 2px 6px;
          margin-bottom: 10px;
        }
        .vd-pie-legal-titulo {
          font-size: 12px; font-weight: 600; letter-spacing: -.01em; color: var(--ink-2);
          margin: 0 0 8px; max-width: 720px; line-height: 1.5;
        }
        .vd-pie-legal-cuerpo1 {
          font-size: 11px; color: var(--ink-mut); line-height: 1.7; margin: 0 0 4px;
          max-width: 720px;
        }
        .vd-pie-legal-cuerpo2 {
          font-size: 11px; color: var(--ink-mut); line-height: 1.7; margin: 0;
          max-width: 720px; opacity: .8;
        }
"""
