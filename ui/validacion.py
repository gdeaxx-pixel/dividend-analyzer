"""Sección «Validación datos» — se abre desde el menú de 3 puntos de la ruta
(`ui/chrome.py`), igual que Metodología.

Decisión de Daniel (2026-08-10): antes cada aviso de confiabilidad vivía suelto en una
esquina distinta — el banner 1042-S ocupaba una franja fija bajo el encabezado en TODA
la app (`ui.vistas.render_1042s_card`, ahora `_render_1042s` aquí), y calidad de datos /
notas técnicas / excluidos eran tres expanders sueltos al pie (`ui.pie`, filas 22-24).
Se consolidan en un solo panel oculto por defecto, con una etiqueta de confiabilidad al
frente (`_puntuacion_acertividad`) — no es una métrica nueva, es la lectura conjunta de
las señales que ya se calculaban por separado. El menú marca un punto cuando
`hay_alertas` es cierto, para que la app no calle una discrepancia real solo por
haberla escondido detrás de un clic (mockup aprobado por Daniel en la misma sesión).
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

_V1042S_ESTILO = {
    "match":             ("--cash", "Coincide"),
    "portfolio_higher":  ("--warn", "Tu análisis reporta más"),
    "form_higher":       ("--warn", "El 1042-S reporta más"),
    "no_overlap":        ("--ink-mut", "Sin año en común"),
}


def _tarjeta(accent_var: str, titulo_html: str, cuerpo_html: str) -> str:
    return (f'<div class="vd-pie-card" style="border-left-color: var({accent_var});">'
            f'<p class="vd-pie-card-titulo">{titulo_html}</p>{cuerpo_html}</div>')


def _render_1042s(resultados: dict) -> dict | None:
    """Cruza el 1042-S leído en el Bloque 3 contra el bruto de dividendos que
    `analyze_portfolio` calculó. Antes vivía en `ui.vistas.render_1042s_card`, banner
    persistente bajo el encabezado en toda la app; ahora solo se dibuja dentro de este
    panel. Devuelve la validación (o `None`) para que `_puntuacion_acertividad` la
    reutilice sin recalcular."""
    wizard_1042s = st.session_state.get("_wizard_1042s")
    if not wizard_1042s:
        return None
    validacion = logic.build_1042s_validation(resultados, wizard_1042s)
    if not validacion:
        return None
    accent_var, etiqueta = _V1042S_ESTILO.get(validacion["status"], _V1042S_ESTILO["no_overlap"])
    st.markdown(
        f'<div class="vd-1042s-card" style="border-left-color: var({accent_var});">'
        f'<p class="vd-1042s-titulo">Validación 1042-S · <span style="color: var({accent_var});">'
        f'{etiqueta}</span></p>'
        f'<p class="vd-1042s-detalle">Dividendo bruto {validacion["tax_year"]} — Tu análisis: '
        f'<b>${validacion["bruto_portafolio"]:,.2f}</b> · 1042-S: <b>${validacion["bruto_1042s"]:,.2f}</b> · '
        f'Retenido: <b>${validacion["retenido_1042s"]:,.2f}</b> · ROC: '
        f'<b>${validacion["roc_1042s"]:,.2f}</b> ({validacion["roc_pct"]:.1f}%)</p>'
        f'<p class="vd-1042s-nota">{validacion["note"]}</p>'
        '</div>', unsafe_allow_html=True)
    return validacion


def _render_calidad_datos(resultados: dict) -> None:
    """Calidad de datos y validación cruzada de ingresos (antes fila 22 de `ui.pie`)."""
    classify_map = logic.classify_tickers(list(resultados.keys()))
    dq = logic.assess_data_quality(resultados, classify_map)
    no_ok = {t: q for t, q in dq.items() if q["level"] != "ok"}

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
    """Splits, reconciliaciones y dividendos especiales por ticker (antes en `ui.pie`)."""
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
    """Notas técnicas y eventos corporativos detectados (antes fila 23 de `ui.pie`)."""
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


def _separar_excluidos(resultados: dict) -> tuple[dict, dict]:
    """Separa los `skipped` de `analyze_portfolio` en dos grupos que comparten el mismo
    dict pero significan cosas muy distintas: `tuyos` (razón `held_less_than_14_days`) SÍ
    son posiciones del usuario, solo que sin datos suficientes; `ruido` (`not_known_etf` y
    cualquier otra razón) nunca fueron un ETF que la app cubra — normalmente cientos de
    acciones sueltas que no tienen nada que ver con el portafolio. Mezclados en una sola
    lista, los `tuyos` (los pocos que importan) se pierden entre el `ruido`."""
    excluidos = {t: s for t, s in resultados.items() if isinstance(s, dict) and s.get("skipped")}
    tuyos = {t: s for t, s in excluidos.items() if s.get("reason") == "held_less_than_14_days"}
    ruido = {t: s for t, s in excluidos.items() if t not in tuyos}
    return tuyos, ruido


def _etiqueta_excluido(s: dict) -> str:
    razon = s.get("reason", "")
    if razon == "held_less_than_14_days":
        return _SKIP_REASON[razon].format(days=s.get("holding_days", "?"))
    return _SKIP_REASON.get(razon, "Excluido")


def _render_lista_excluidos(grupo: dict) -> None:
    for ticker, s in grupo.items():
        st.markdown(f'<p class="vd-pie-excluido">— <b>{ticker}</b> · '
                    f'<span class="vd-pie-excluido-razon">{_etiqueta_excluido(s)}</span></p>',
                    unsafe_allow_html=True)


def _render_excluidos(resultados: dict) -> None:
    """Tickers excluidos del análisis (antes fila 24 de `ui.pie`; no confundir con los
    `mode_skip` de `classify_tickers` que se muestran en el Bloque 2 de la carga — son
    dos exclusiones distintas). Título y orden priorizan `tuyos` sobre `ruido` (ver
    `_separar_excluidos`): con un portafolio real, el ruido puede ser cientos de tickers
    y no debe enterrar los pocos que sí son del usuario."""
    tuyos, ruido = _separar_excluidos(resultados)
    if not tuyos and not ruido:
        return
    if tuyos and ruido:
        titulo = (f"{len(tuyos)} posición(es) tuya(s) excluida(s) · "
                  f"+ {len(ruido)} ticker(s) no reconocido(s) como ETF")
    elif tuyos:
        titulo = f"{len(tuyos)} posición(es) tuya(s) excluida(s) del análisis"
    else:
        titulo = f"{len(ruido)} ticker(s) excluidos del análisis"

    with st.expander(titulo):
        if tuyos:
            if ruido:
                st.markdown('<p class="vd-pie-subtitulo">Tus posiciones, sin datos suficientes</p>',
                            unsafe_allow_html=True)
            _render_lista_excluidos(tuyos)
        if ruido:
            if tuyos:
                st.markdown('<p class="vd-pie-subtitulo">No reconocidos como ETF de largo plazo</p>',
                            unsafe_allow_html=True)
            _render_lista_excluidos(ruido)


def _puntuacion_acertividad(resultados: dict) -> tuple[str, list[str]]:
    """Etiqueta de confiabilidad (Alta/Media/Baja) — lectura conjunta de las señales que
    ya se calculaban por separado (1042-S, calidad de datos, validación cruzada de
    ingresos, posiciones propias excluidas). No es una métrica nueva ni un número que
    nadie pueda auditar a ojo (decisión de Daniel: etiqueta cualitativa, no 0-100): cada
    bajón de nivel trae debajo la razón concreta que lo causó."""
    nivel = "Alta"
    razones: list[str] = []

    wizard_1042s = st.session_state.get("_wizard_1042s")
    if wizard_1042s:
        v1042s = logic.build_1042s_validation(resultados, wizard_1042s)
        if v1042s and v1042s["status"] in ("portfolio_higher", "form_higher"):
            nivel = "Media"
            razones.append(v1042s["note"])

    classify_map = logic.classify_tickers(list(resultados.keys()))
    dq = logic.assess_data_quality(resultados, classify_map)
    unreliable = {t: q for t, q in dq.items() if q["level"] == "unreliable"}
    parcial = {t: q for t, q in dq.items() if q["level"] not in ("ok", "unreliable")}
    if unreliable:
        nivel = "Baja"
        razones.append(f"{len(unreliable)} posición(es) con datos no confiables.")
    elif parcial:
        if nivel == "Alta":
            nivel = "Media"
        razones.append(f"{len(parcial)} posición(es) reconciliadas desde tu captura, no "
                       "directas del CSV.")

    ingreso = st.session_state.get("_wizard_income_summary")
    if ingreso and ingreso.get("tickers"):
        recon = logic.reconcile_income(resultados, ingreso)
        warns = [t for t, r in recon.items() if r["badge"] == "warn"]
        if warns:
            if nivel == "Alta":
                nivel = "Media"
            razones.append(f"{len(warns)} posición(es) con alerta en la validación de ingresos.")

    tuyos, _ruido = _separar_excluidos(resultados)
    if tuyos:
        if nivel == "Alta":
            nivel = "Media"
        razones.append(f"{len(tuyos)} posición(es) tuya(s) excluida(s) por datos insuficientes.")

    if not razones:
        razones.append("Sin discrepancias entre las fuentes disponibles.")
    return nivel, razones


def hay_alertas(resultados: dict) -> bool:
    """Si el menú de 3 puntos (`ui/chrome.py`) debe marcar el punto de aviso — cierto en
    cuanto la confiabilidad baja de Alta."""
    if not resultados:
        return False
    nivel, _razones = _puntuacion_acertividad(resultados)
    return nivel != "Alta"


def preparar_pdf(resultados: dict) -> tuple[bytes | None, str]:
    """Genera los bytes del reporte PDF por adelantado: el botón de descarga vive dentro
    del popover de la ruta (`ui/chrome.py`), que es solo presentación y no calcula nada,
    así que se prepara aquí antes. Literal de la fila 37 heredada de `ui.pie`/
    `app_old.py:5271-5282`: `report.py` y `test_report.py` no se tocan. `try/except`
    porque el original también lo protege — un reporte que falla no debe romper el menú."""
    try:
        from datetime import date as _date

        from report import generate_report_pdf

        broker = st.session_state.get("_wizard_broker") or "schwab"
        pdf_bytes = generate_report_pdf(resultados, broker, version="2.0")
        filename = f"auditoria-portafolio-{_date.today().isoformat()}.pdf"
        return pdf_bytes, filename
    except Exception:
        return None, ""


def render_validacion_datos(resultados: dict) -> None:
    """Punto único de entrada: el panel «Validación datos» completo."""
    if not resultados:
        return
    st.markdown('<span class="vd-badge">Validación datos</span>', unsafe_allow_html=True)

    nivel, razones = _puntuacion_acertividad(resultados)
    st.markdown(
        f'<div class="vd-val-score vd-val-score-{nivel.lower()}">'
        f'<p class="vd-val-score-etiqueta">Confiabilidad {nivel.lower()}</p>'
        f'<p class="vd-val-score-razon">{" · ".join(razones)}</p>'
        '</div>', unsafe_allow_html=True)

    _render_1042s(resultados)

    st.markdown('<p class="vd-pie-subtitulo">Calidad de datos</p>', unsafe_allow_html=True)
    st.caption("Detalle técnico: cómo se reconciliaron tus posiciones y la "
              "verificación del dividendo bruto contra el reporte de ingresos del "
              "broker.")
    _render_calidad_datos(resultados)
    _render_notas_tecnicas(resultados)
    _render_excluidos(resultados)


ESTILOS_VALIDACION = """
        .vd-1042s-card {
          background: var(--panel-tint); border-left: 3px solid var(--hair);
          padding: 10px 14px; margin: 0 0 18px;
        }
        .vd-1042s-titulo {
          font-family: var(--font-mono); font-size: 11.5px; font-weight: 700;
          letter-spacing: .05em; text-transform: uppercase; color: var(--ink);
          margin: 0;
        }
        .vd-1042s-detalle { font-size: 12px; color: var(--ink-2); margin: 4px 0 0; }
        .vd-1042s-nota { font-size: 12px; color: var(--ink-mut); margin: 3px 0 0; }

        .vd-val-score {
          border-left: 3px solid var(--hair); background: var(--panel-tint);
          padding: 10px 14px; margin: 0 0 20px;
        }
        .vd-val-score-etiqueta {
          font-family: var(--font-mono); font-size: 12px; font-weight: 700;
          letter-spacing: .05em; text-transform: uppercase; margin: 0; color: var(--ink);
        }
        .vd-val-score-razon { font-size: 12px; color: var(--ink-mut); margin: 4px 0 0; }
        .vd-val-score-alta { border-left-color: var(--cash); }
        .vd-val-score-alta .vd-val-score-etiqueta { color: var(--cash); }
        .vd-val-score-media { border-left-color: var(--warn); }
        .vd-val-score-media .vd-val-score-etiqueta { color: var(--warn); }
        .vd-val-score-baja { border-left-color: var(--loss); }
        .vd-val-score-baja .vd-val-score-etiqueta { color: var(--loss); }

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
"""
