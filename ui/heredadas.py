"""Categoría «Detalle» — secciones de `app_old.py` que el artifact nunca cubrió.

Fase 5 (traspaso § Fase 5 — Arquitectura): estas 4 vistas agrupan las secciones
heredadas que Daniel decidió que vivan en su propia categoría de la ruta, en vez de
resucitar el scroll infinito de `app_old.py`. A diferencia de `ui/nav.py`, este módulo
**no se genera** — el demo del artifact no tiene una quinta categoría, así que
inventarla ahí rompería el `--check` de `tools/extract_design_system.py` y dejaría
que el port divergiera de su fuente sin que nadie lo note. Aquí sí se escribe a mano,
porque no hay nada que extraer: nunca existió en el artifact.

Regla de método de esta fase (no la de las fases 1-4): se copia la lógica y el texto
literal de `app_old.py`, re-vestido con `ui/tokens.py`. No se redactan de nuevo los
textos ni se reinterpretan las cifras.

Fase 5b — Portafolios e Ingresos:
- Portafolios (filas 8, 9, 15, 16, 35, 36) — `app_old.py:3901-3945` (Tus dos portafolios),
  `app_old.py:3989-4029` (Portafolio dividendos), `app_old.py:4997-5337` (Detalle por
  portafolio + Resumen consolidado), `app_old.py:1869-1895` (`_render_interpretation`,
  filas 35/36).
- Ingresos (filas 11, 12, 14) — `app_old.py:4153-4995`, todo detrás de la misma guarda
  `_wizard_income_df is not None` que en `app_old.py` (verificado por indentación: el
  bloque completo — gráfica, cuadrícula ROC y las 3 cuadrículas Schwab-vs-cálculo —
  vive dentro de `if _income_df_s3 is not None and len(_income_df_s3) > 0:`). La
  dona de concentración de ingreso es la excepción: usa `results` directo, sin CSV
  de ingresos, y por eso se muestra siempre que haya ≥2 tickers con ingreso.

Reusa `ui/adapters.py::salud_nav_data` para las tarjetas de salud del NAV (fila 9):
mismo objeto que ya consume la vista Salud NAV — no se recalcula `classify_roc_health`
por segunda vez (espíritu de la Regla 3 del contrato ROC/NRA, aunque esta fila no sea
fiscal).
"""

from __future__ import annotations

import streamlit as st

import logic
from ui import estado

CAT_CLAVE = "detalle"
CAT_LABEL = "Portafolios"

VIEWS = {
    "portafolios": "Portafolios",
}

VIEW_ORDER = ("portafolios",)


# ── Helpers de formato y presentación ───────────────────────────────────────────

def _money(v, decimales: int = 2, defecto: str = "n/d") -> str:
    if v is None or v != v:  # None o NaN
        return defecto
    return f"${v:,.{decimales}f}"


def _pct1(v, defecto: str = "—") -> str:
    if v is None or v != v:
        return defecto
    return f"{v:+.1f}%"


def _color_signo(v) -> str:
    return "--cash" if (v or 0) >= 0 else "--loss"


def _seccion(titulo: str, lede: str = "") -> None:
    st.markdown(f'<p class="vd-her-seccion">{titulo}</p>', unsafe_allow_html=True)
    if lede:
        st.markdown(f'<p class="vd-her-lede">{lede}</p>', unsafe_allow_html=True)


def _tarjeta(accent_var: str, titulo_html: str, cuerpo_html: str) -> str:
    return (f'<div class="vd-her-card" style="border-left-color: var({accent_var});">'
            f'<p class="vd-her-card-titulo">{titulo_html}</p>{cuerpo_html}</div>')


# ── Fila 8 — Tus dos portafolios ────────────────────────────────────────────────

def _fondos(tickers: list[str]) -> str:
    """«3 fondos» / «1 fondo». Antes del filtro de `_tiene_datos` estos chips casi nunca
    llegaban a uno solo y el plural fijo pasaba desapercibido; al excluir los tickers sin
    datos, «1 fondos» se volvió visible (auditoría 2026-08-10)."""
    n = len(tickers)
    return f"{n} fondo" if n == 1 else f"{n} fondos"


def _agregados(resultados: dict, tickers: list[str]) -> tuple:
    from ui.adapters import _tiene_datos

    filas = [(t, resultados[t]) for t in tickers if _tiene_datos(resultados.get(t))]
    inv = sum(s["pocket_investment"] for _, s in filas)
    mv = sum(s["market_value"] for _, s in filas)
    # `dividends_collected_cash` no se puede sumar entre tickers: viene BRUTO en Schwab
    # y NETO en IB (misma mezcla de bases que ya resolvió el PR C en `_cuadricula_roc_
    # consolidada` de este archivo y en `report._dividendos_netos`). `dividends_net_total`
    # es el objeto fiscal único (`logic.build_dividend_tax_totals`, corrido dentro de
    # `analyze_portfolio`) y ya resuelve la convención por ticker — sumarlo hace que el
    # "Retorno total" reste la retención NRA también para Schwab. Si no está presente
    # (stats legado sin pasar por `analyze_portfolio`) degrada al campo crudo.
    div = sum(s.get("dividends_net_total") if s.get("dividends_net_total") is not None
              else s.get("dividends_collected_cash", 0)
              for _, s in filas)
    tr = mv + div - inv
    pct = tr / inv * 100 if inv > 0 else 0
    return inv, mv, div, tr, pct


def _tus_dos_portafolios(resultados: dict, classify_map: dict) -> tuple[list, list]:
    """Fila 8 — tarjetas A/B + dona de asignación por valor. Literal de
    `app_old.py:3901-3987` (cascada de agregados, tarjetas, pie chart dividendos/crecimiento)."""
    from ui.adapters import _tiene_datos

    mode_a = sorted(t for t, m in classify_map.items()
                     if m == "mode_a" and _tiene_datos(resultados.get(t)))
    mode_b = sorted(t for t, m in classify_map.items()
                     if m == "mode_b" and _tiene_datos(resultados.get(t)))
    if not (mode_a or mode_b):
        return mode_a, mode_b

    _seccion("Tus dos portafolios",
             "Tu dinero está jugando dos juegos distintos al mismo tiempo. Cada uno gana "
             "(y pierde) de una forma diferente — por eso los separamos.")

    def mini(inv, mv, div, tr, pct):
        color = _color_signo(tr)
        return (
            '<div class="vd-her-port-mini">'
            f'<span><span class="lbl">Invertido</span><span class="val">{_money(inv, 0)}</span></span>'
            f'<span><span class="lbl">Vale hoy</span><span class="val">{_money(mv, 0)}</span></span>'
            f'<span><span class="lbl">Dividendos</span><span class="val">{_money(div, 0)}</span></span>'
            f'<span><span class="lbl">Retorno total</span>'
            f'<span class="val" style="color:var({color});">{_money(tr, 0)} ({pct:+.1f}%)</span></span>'
            "</div>")

    tarjetas = []
    if mode_b:
        inv, mv, div, tr, pct = _agregados(resultados, mode_b)
        tarjetas.append(
            '<div class="vd-her-port-card">'
            '<p class="vd-her-port-titulo">Portafolio de crecimiento</p>'
            f'<span class="vd-her-port-chip">{_fondos(mode_b)}: {", ".join(mode_b)}</span>'
            + mini(inv, mv, div, tr, pct) + "</div>")
    if mode_a:
        inv, mv, div, tr, pct = _agregados(resultados, mode_a)
        tarjetas.append(
            '<div class="vd-her-port-card vd-her-port-card-navy">'
            '<p class="vd-her-port-titulo">Portafolio de dividendos</p>'
            f'<span class="vd-her-port-chip">{_fondos(mode_a)}: {", ".join(mode_a)}</span>'
            + mini(inv, mv, div, tr, pct) + "</div>")
    estilo = ' style="grid-template-columns:1fr;"' if len(tarjetas) == 1 else ""
    st.markdown(f'<div class="vd-her-port-cards"{estilo}>' + "".join(tarjetas) + "</div>",
                unsafe_allow_html=True)

    if mode_a and mode_b:
        _dona_asignacion(resultados, mode_a, mode_b)

    return mode_a, mode_b


def _dona_asignacion(resultados: dict, mode_a: list[str], mode_b: list[str]) -> None:
    """Pie chart de asignación por valor de mercado. Literal de `app_old.py:3946-3985`."""
    import altair as alt
    import pandas as pd

    filas = ([{"ETF": t, "Grupo": "Dividendos",
               "Capital": (resultados[t].get("market_value") or 0)} for t in mode_a]
             + [{"ETF": t, "Grupo": "Crecimiento",
                 "Capital": (resultados[t].get("market_value") or 0)} for t in mode_b])
    df = pd.DataFrame([f for f in filas if f["Capital"] > 0])
    if df.empty:
        return
    total = df["Capital"].sum()
    df["Pct"] = df["Capital"] / total * 100 if total else 0
    df["Etiqueta"] = df["ETF"] + "  " + df["Pct"].round(0).astype(int).astype(str) + "%"

    base = alt.Chart(df).encode(
        theta=alt.Theta("Capital:Q", stack=True),
        order=alt.Order("Grupo:N"),
        color=alt.Color("Grupo:N",
                        scale=alt.Scale(domain=["Dividendos", "Crecimiento"],
                                        range=["#3ea0d6", "#8f76d4"]),
                        legend=alt.Legend(title=None, orient="top", labelFontSize=12)),
        tooltip=[alt.Tooltip("ETF:N", title="ETF"),
                 alt.Tooltip("Grupo:N", title="Portafolio"),
                 alt.Tooltip("Capital:Q", format="$,.0f", title="Valor de mercado"),
                 alt.Tooltip("Pct:Q", format=".1f", title="% del portafolio")])
    arco = base.mark_arc(innerRadius=68, outerRadius=130, strokeWidth=2)
    texto = base.mark_text(radius=155, fontSize=11, fontWeight="bold").encode(
        text=alt.Text("Etiqueta:N"))
    chart = (arco + texto).properties(height=360)
    st.altair_chart(chart, use_container_width=True)

    div_mv = sum((resultados[t].get("market_value") or 0) for t in mode_a)
    crec_mv = sum((resultados[t].get("market_value") or 0) for t in mode_b)
    comb = div_mv + crec_mv
    a_share = div_mv / comb * 100 if comb else 0
    b_share = crec_mv / comb * 100 if comb else 0
    st.markdown(
        '<div class="vd-her-leyenda">'
        f'<span><span class="vd-her-dot" style="background:#3ea0d6;"></span>'
        f'Dividendos <b>{a_share:.0f}%</b> · {_money(div_mv, 0)}</span>'
        f'<span><span class="vd-her-dot" style="background:#8f76d4;"></span>'
        f'Crecimiento <b>{b_share:.0f}%</b> · {_money(crec_mv, 0)}</span>'
        "</div>", unsafe_allow_html=True)


# ── Fila 9 — Portafolio dividendos (erosión del NAV, fondo por fondo) ──────────

def _portafolio_dividendos(resultados: dict, mode_a: list[str]) -> None:
    """Fila 9 — semáforo de salud del NAV por fondo + cierre honesto. Literal de
    `app_old.py:3989-4029`. Reusa `ui.adapters.salud_nav_data` (mismo objeto que Salud
    NAV) en vez de volver a invocar `classify_roc_health` por su cuenta.

    La «Hoja de Excel que te venden vs la realidad» que `app_old.py` embebía aquí como
    expander **no se duplica**: ya es su propia vista completa en la ruta
    (Dividendos/Largo Plazo › [ETF] › Hoja Excel) — la función sigue accesible,
    solo cambió de puerta de entrada."""
    if not mode_a:
        return
    from ui.adapters import salud_nav_data

    _seccion("Portafolio dividendos", "")
    st.markdown(
        '<p class="vd-her-subtitulo">La erosión del precio (NAV), fondo por fondo</p>'
        '<p class="vd-her-nota">El precio de estos ETFs tiende a bajar con el tiempo — se '
        'llama <b>erosión del NAV</b>. Aquí el diagnóstico de cada fondo tuyo, con su '
        "tendencia real de precio:</p>", unsafe_allow_html=True)

    for ticker in mode_a:
        stats = resultados.get(ticker)
        if not isinstance(stats, dict) or "error" in stats:
            continue
        datos = salud_nav_data(ticker, stats)
        st.markdown(
            f'<p class="vd-her-nav-headline" style="color:{datos["color"]};">'
            f'{ticker} — {datos["headline"]}</p>'
            f'<p class="vd-her-nav-plain">{datos["plain"]}</p>', unsafe_allow_html=True)
        with st.expander("Ver detalle técnico", expanded=False):
            nums = []
            if datos["nav_cagr"] is not None:
                nums.append(f"NAV {datos['nav_cagr']:+.0f}%/año")
            if datos["roc_pct"] is not None:
                nums.append(f"ROC {datos['roc_pct']:.0f}%")
            if datos["total_return_pct"] is not None:
                nums.append(f"retorno total {datos['total_return_pct']:+.0f}%")
            if nums:
                st.caption(" · ".join(nums))
            st.write(datos["reason"])
        info = logic.load_instruments().get(str(ticker).upper(), {}) or {}
        why = []
        if info.get("nav_erosion"):
            why.append(f"**Erosión del NAV:** {info['nav_erosion']}")
        if info.get("sustainability"):
            why.append(f"**Sostenibilidad de la distribución:** {info['sustainability']}")
        if why:
            with st.expander(f"¿Por qué pasa esto en {ticker}?", expanded=False):
                for parrafo in why:
                    st.markdown(parrafo)

    # La tasa se lee del perfil: este callout va pegado a las cifras reales del bróker, así
    # que fijar "~30%" le mentiría a un mexicano (10% por tratado) o a un residente US (0%).
    _perfil = estado.perfil_fiscal()
    _imp = (f'menos ~{_perfil["rate_pct"]:.0f}% de impuesto' if _perfil["rate_declared"]
            else 'menos la retención de impuestos que te corresponda')
    st.markdown(
        '<div class="vd-her-callout" style="border-left-color: var(--warn);">'
        '<p class="vd-her-callout-eyebrow">El trato completo, en una línea</p>'
        '<p class="vd-her-callout-cuerpo">'
        '<b>Cuándo sí:</b> quieres ingreso mensual real hoy y lo entiendes como renta, no '
        'crecimiento. &nbsp;·&nbsp; <b>El precio:</b> renuncias a la subida de la acción, '
        "el NAV tiende a erosionarse, y parte del 'pago' es tu dinero de vuelta (ROC) "
        f'{_imp}. &nbsp;·&nbsp; <b>Regla de bolsillo:</b> yield alto ≠ ganancia '
        'alta — la cifra que manda es el retorno total de la portada.</p></div>',
        unsafe_allow_html=True)


# ── Filas 35, 36 — interpretación educativa + exposición al subyacente ─────────

def _render_interpretation(resultados: dict, ticker: str) -> None:
    """Filas 35 y 36. Literal de `app_old.py:1869-1895` (`_render_interpretation`)."""
    interp = logic.build_interpretation(resultados, ticker)
    exp_lines = logic.build_underlying_exposure(resultados, ticker).get("lines", [])
    if not interp.get("lines") and not exp_lines:
        return
    if interp.get("lines"):
        items = "".join(f"<li>{ln}</li>" for ln in interp["lines"])
        st.markdown(
            '<div class="vd-her-callout" style="border-left-color: var(--accent);">'
            '<p class="vd-her-callout-eyebrow">Qué significa para ti</p>'
            f'<ul class="vd-her-callout-lista">{items}</ul></div>', unsafe_allow_html=True)
    if exp_lines:
        eitems = "".join(f"<li>{ln}</li>" for ln in exp_lines)
        st.markdown(
            '<div class="vd-her-callout" style="border-left-color: var(--ink);">'
            '<p class="vd-her-callout-eyebrow">Exposición al subyacente — riesgo asimétrico</p>'
            f'<ul class="vd-her-callout-lista">{eitems}</ul></div>', unsafe_allow_html=True)


# ── Fila 15 — Detalle por portafolio (tarjeta por ticker, mode_a) ──────────────

def _tarjeta_roc(stats: dict) -> None:
    """ROC callout — literal de `app_old.py:5117-5139` (solo si hay costo base del bróker)."""
    if stats.get("ib_cost_basis") is None or stats.get("roc_accumulated") is None:
        return
    roc_acc = stats["roc_accumulated"]
    roc_pct = stats["roc_percent"]
    ib_b = stats["ib_cost_basis"]
    pocket = stats["pocket_investment"]
    st.markdown(
        '<div class="vd-her-roc-callout">'
        '<p class="vd-her-roc-titulo">Return of Capital detectado</p>'
        '<div class="vd-her-roc-valores">'
        f'<div><span class="vd-her-roc-num">{_money(roc_acc, 2)}</span>'
        '<span class="vd-her-roc-sub">ROC acumulado</span></div>'
        f'<div><span class="vd-her-roc-num">{roc_pct:.1f}%</span>'
        '<span class="vd-her-roc-sub">del costo real</span></div>'
        f'<div><span class="vd-her-roc-num">{_money(ib_b, 2)}</span>'
        '<span class="vd-her-roc-sub">base actual del broker</span></div>'
        "</div>"
        f'<p class="vd-her-roc-explica">Tu broker redujo tu base de {_money(pocket, 2)} a '
        f'{_money(ib_b, 2)} porque {roc_pct:.1f}% de las distribuciones fue clasificado '
        "como Return of Capital. Esto reduce tu ganancia de capital imponible al vender.</p>"
        "</div>", unsafe_allow_html=True)


def _tarjeta_retorno_total(stats: dict) -> None:
    """Literal de `app_old.py:5160-5219` (retorno total + erosión de NAV si aplica).

    Alineada (2026-08-23) con `_agregados` de este archivo y `cashflow_data`: el «Income»
    era `dividends_collected_cash`, que es BRUTO al cobro en Schwab (retención en fila
    aparte) mientras el ROI que calcula `analyze_portfolio` (`logic.py:1574`,
    `_cash_collected_net`) deriva del NETO — hasta ~$105 de diferencia por posición bajo la
    misma etiqueta «Retorno Total». Mismo fallback que `_agregados`.
    """
    inc = (stats.get("dividends_net_total") if stats.get("dividends_net_total") is not None
           else stats.get("dividends_collected_cash", 0))
    total_ret = stats["market_value"] + inc - stats["pocket_investment"]
    total_ret_pct = (total_ret / stats["pocket_investment"] * 100) if stats["pocket_investment"] > 0 else 0
    cap_comp = stats["market_value"] - stats["pocket_investment"]
    inc_comp = inc
    color_tr = _color_signo(total_ret)
    color_cap = _color_signo(cap_comp)
    st.markdown(
        f'<div class="vd-her-retorno" style="border-left-color:var({color_tr});">'
        '<p class="vd-her-retorno-label">Retorno Total</p>'
        f'<p class="vd-her-retorno-num" style="color:var({color_tr});">'
        f'{_money(total_ret, 2)} <span class="vd-her-retorno-pct">({total_ret_pct:+.2f}%)</span></p>'
        f'<p class="vd-her-retorno-desglose">Capital: <b style="color:var({color_cap});">'
        f'{_money(cap_comp, 2)}</b> &nbsp;·&nbsp; Income: <b style="color:var(--cash);">'
        f'{_money(inc_comp, 2)}</b></p></div>', unsafe_allow_html=True)

    if cap_comp < 0:
        erosion_amt = abs(cap_comp)
        offset = inc_comp - erosion_amt
        m_income = stats.get("monthly_income")
        avg_monthly = (m_income.mean() if (m_income is not None and not m_income.empty
                                            and m_income.mean() > 0) else None)
        if offset >= 0:
            label, color = "COMPENSADO", "--cash"
            verdict = (f"Los dividendos superaron la caída de precio en "
                       f"<b style='color:var(--cash);'>{_money(offset, 2)}</b>. "
                       "Tu capital está cubierto por el income.")
        else:
            deficit = abs(offset)
            label, color = "DÉFICIT NETO", "--loss"
            if avg_monthly:
                meses = deficit / avg_monthly
                verdict = (f"Faltan <b style='color:var(--loss);'>{_money(deficit, 2)}</b> en "
                           f"dividendos para cubrir la caída — a tasa actual "
                           f"(~{_money(avg_monthly, 0)}/mes): <b>~{meses:.0f} meses más</b>")
            else:
                verdict = (f"Faltan <b style='color:var(--loss);'>{_money(deficit, 2)}</b> en "
                           "dividendos para cubrir la caída de precio")
        st.markdown(
            f'<div class="vd-her-erosion" style="border-left-color:var({color});">'
            f'<p class="vd-her-erosion-eyebrow" style="color:var({color});">NAV EROSION · {label}</p>'
            '<div class="vd-her-erosion-valores">'
            f'<div><span class="vd-her-erosion-sub">Caída de precio</span>'
            f'<span class="vd-her-erosion-num" style="color:var(--loss);">{_money(erosion_amt, 2)}</span></div>'
            '<span class="vd-her-erosion-vs">vs</span>'
            f'<div><span class="vd-her-erosion-sub">Income cobrado</span>'
            f'<span class="vd-her-erosion-num" style="color:var(--cash);">{_money(inc_comp, 2)}</span></div>'
            "</div>"
            f'<p class="vd-her-erosion-verdict">{verdict}</p></div>', unsafe_allow_html=True)


def _tarjeta_ticker(resultados: dict, ticker: str, stats: dict) -> None:
    """Una tarjeta del acordeón «Detalle por portafolio» — literal de `app_old.py:5051-5259`."""
    roi = stats.get("roi_percent", 0)
    color_roi = _color_signo(roi)
    st.markdown(
        f'<div class="vd-her-tk-header"><span class="vd-her-tk-nombre">{ticker}</span>'
        '<span class="vd-her-tk-badge">Income</span>'
        f'<span class="vd-her-tk-precio">{_money(stats.get("current_price"))} &nbsp;·&nbsp; '
        f'<span style="color:var({color_roi});font-weight:700;">{roi:+.2f}% ROI</span></span>'
        "</div>", unsafe_allow_html=True)

    buys = stats.get("shares_bought", 0)
    sells = stats.get("shares_sold", 0)
    proj_m = stats.get("monthly_income")
    proj_recent = proj_m[proj_m > 0].tail(3) if (proj_m is not None and not proj_m.empty) else None
    proj_val = proj_recent.mean() if (proj_recent is not None and len(proj_recent) > 0) else None
    proj_cell = (f'<p class="vd-her-tkpi-value" style="color:var(--cash);">{_money(proj_val)}</p>'
                 '<p class="vd-her-tkpi-sub">prom. últ. 3 meses</p>') if proj_val else (
        '<p class="vd-her-tkpi-value" style="color:var(--ink-mut);">—</p>'
        '<p class="vd-her-tkpi-sub">sin historial</p>')

    if stats.get("ib_cost_basis") is not None:
        base_cell = f'<p class="vd-her-tkpi-value">{_money(stats["ib_cost_basis"])}</p>'
        ra = stats.get("roc_accumulated")
        if ra is not None:
            rp = stats.get("roc_percent")
            rp_txt = f" ({rp:.1f}%)" if rp is not None else ""
            base_cell += f'<p class="vd-her-tkpi-sub" style="color:var(--warn);">ROC: {_money(ra)}{rp_txt}</p>'
    elif stats.get("roc_accumulated") is not None:
        base_cell = (f'<p class="vd-her-tkpi-value" style="color:var(--warn);">ROC ~{_money(stats["roc_accumulated"], 0)}</p>'
                     f'<p class="vd-her-tkpi-sub">est. 19a ({(stats.get("roc_percent") or 0):.0f}% de distrib.)</p>')
    else:
        base_cell = ('<p class="vd-her-tkpi-value" style="color:var(--ink-mut);">—</p>'
                     '<p class="vd-her-tkpi-sub">Edítala al cargar (Paso 1)</p>')

    st.markdown(f"""
    <div class="vd-her-tkpi">
        <div class="vd-her-tkpi-cell">
            <p class="vd-her-tkpi-label">Acciones</p>
            <p class="vd-her-tkpi-value">{stats['shares_owned']:.4f}</p>
            <p class="vd-her-tkpi-sub">Compradas {buys:.2f} · Vendidas {sells:.2f}</p>
        </div>
        <div class="vd-her-tkpi-cell">
            <p class="vd-her-tkpi-label">Tu inversión</p>
            <p class="vd-her-tkpi-value">{_money(stats['pocket_investment'])}</p>
            <p class="vd-her-tkpi-sub">lo que pusiste de tu bolsillo</p>
        </div>
        <div class="vd-her-tkpi-cell">
            <p class="vd-her-tkpi-label">Base broker (con ROC)</p>
            {base_cell}
        </div>
        <div class="vd-her-tkpi-cell">
            <p class="vd-her-tkpi-label">Valor de Mercado</p>
            <p class="vd-her-tkpi-value">{_money(stats['market_value'])}</p>
            <p class="vd-her-tkpi-sub">@ {_money(stats['current_price'])} por acción</p>
        </div>
        <div class="vd-her-tkpi-cell">
            <p class="vd-her-tkpi-label" style="color:var(--cash);">Próx. mes (est.)</p>
            {proj_cell}
        </div>
    </div>
    """, unsafe_allow_html=True)

    quality = logic.assess_ticker_quality(resultados, ticker)
    if quality["level"] == "unreliable":
        st.warning(f"{ticker} · datos incompletos: {quality['reason']} {quality['action']}")

    cov = stats.get("csv_coverage_pct")
    if cov is not None:
        inc_yf = stats.get("csv_inception_yf")
        color_cov = "--accent" if cov >= 80 else ("--warn" if cov >= 60 else "--loss")
        inc_txt = f" (ticker cotiza desde {inc_yf})" if inc_yf else ""
        st.markdown(f'<p class="vd-her-cobertura" style="color:var({color_cov});">CSV cubre el '
                    f'<b>{cov:.0f}%</b> del historial disponible{inc_txt}</p>', unsafe_allow_html=True)
        if cov < 80:
            st.caption("Se recomienda ≥80% de cobertura para métricas de riesgo confiables")

    for disc in stats.get("price_discrepancies", []):
        st.warning(f"Posible evento corporativo no registrado en {ticker} el {disc['date']}: "
                   f"precio CSV ${disc['csv_price']:.2f} vs yfinance ${disc['yf_price']:.2f} "
                   f"(ratio {disc['ratio']:.2f}x). Verifica si hubo un split adicional.")

    _tarjeta_roc(stats)
    _tarjeta_retorno_total(stats)
    _render_interpretation(resultados, ticker)

    if st.checkbox("Ver números crudos", key=f"vd_her_raw_{ticker}"):
        import pandas as pd

        tabla = pd.DataFrame({
            "Indicador": [
                "Inversión (el dinero que tu pusiste)",
                "Valor de Mercado (valor de tu inversión hoy)",
                "Div. Efectivo (dividendos pagados a tu balance)",
                "Valor de Div. Reinvertidos",
                "Total generado en dividendos (Cash + Reinversión)",
                "Acciones Compradas", "Acciones por DRIP", "Acciones Totales",
                "Ganancia en $", "Ganancia en %",
            ],
            "Valor": [
                _money(stats["pocket_investment"]), _money(stats["market_value"]),
                _money(stats["dividends_collected_cash"]), _money(stats["dividends_collected_drip"]),
                _money(stats["total_dividends"]),
                f"{stats.get('shares_owned_pocket', 0):.4f}", f"{stats.get('shares_owned_drip', 0):.4f}",
                f"{stats['shares_owned']:.4f}", _money(stats["net_profit"]), f"{stats['roi_percent']:.2f}%",
            ],
        })
        st.dataframe(tabla, hide_index=True, use_container_width=True)

    st.divider()


def _resumen_consolidado(rows: list[tuple[str, dict]]) -> None:
    """Fila 16 — Resumen consolidado, fondos de dividendos. Literal de `app_old.py:5261-5334`."""
    if len(rows) < 2:
        return
    import pandas as pd

    total_inv = sum(s["pocket_investment"] for _, s in rows)
    total_mv = sum(s["market_value"] for _, s in rows)
    # Mismo defecto de base mixta que ya resolvió `_agregados` (:105) en este archivo:
    # `dividends_collected_cash` viene BRUTO en Schwab (retención en fila aparte) y NETO en
    # IB, así que el TOTAL y el ROI consolidados sumaban bases distintas en un portafolio
    # mixto. `dividends_net_total` es el objeto fiscal único (`build_dividend_tax_totals`,
    # corrido dentro de `analyze_portfolio`) — mismo fallback que `_agregados`.
    total_div = sum((s.get("dividends_net_total") if s.get("dividends_net_total") is not None
                     else s.get("dividends_collected_cash", 0))
                    for _, s in rows)
    total_tr = total_mv + total_div - total_inv
    total_tr_pct = (total_tr / total_inv * 100) if total_inv > 0 else 0
    has_roc = any(s.get("ib_cost_basis") is not None for _, s in rows)
    total_ib = sum(s["ib_cost_basis"] for _, s in rows if s.get("ib_cost_basis") is not None)
    total_roc = sum(s["roc_accumulated"] for _, s in rows if s.get("roc_accumulated") is not None)
    total_roc_pct = round(total_roc / total_inv * 100, 1) if (has_roc and total_inv > 0) else None

    st.markdown('<p class="vd-her-seccion">Resumen consolidado — fondos de dividendos</p>',
                unsafe_allow_html=True)
    tabla = pd.DataFrame([{
        "Ticker": t,
        "Acciones": f"{s['shares_owned']:.4f}",
        "Tu inversión": _money(s["pocket_investment"]),
        "Dividendos cobrados": _money(s.get("dividends_net_total")
                                      if s.get("dividends_net_total") is not None
                                      else s.get("dividends_collected_cash", 0)),
        "Valor mercado": _money(s["market_value"]),
        "Base de coste (ROC)": _money(s.get("ib_cost_basis"), defecto="—"),
        "ROC acumulado": (f"{_money(s.get('roc_accumulated'))} "
                          f"({s.get('roc_percent'):.1f}%)" if s.get("roc_accumulated") is not None else "—"),
        "ROI total": f"{s['roi_percent']:+.2f}%",
    } for t, s in rows] + [{
        "Ticker": "TOTAL", "Acciones": "",
        "Tu inversión": _money(total_inv), "Dividendos cobrados": _money(total_div),
        "Valor mercado": _money(total_mv),
        "Base de coste (ROC)": _money(total_ib) if has_roc else "Ver broker",
        "ROC acumulado": (f"{_money(total_roc)} ({total_roc_pct:.1f}%)" if has_roc else "—"),
        "ROI total": f"{total_tr_pct:+.2f}%",
    }])
    st.dataframe(tabla, hide_index=True, use_container_width=True)
    st.caption('Base de Coste (ROC): el broker reduce el costo base por distribuciones '
              'clasificadas como Return of Capital. En Interactive Brokers: Portafolio → '
              'Posiciones → columna "Base de coste". En Charles Schwab: Cuentas → '
              'Posiciones → columna "Cost Basis".')


def _detalle_por_portafolio(resultados: dict, mode_a: list[str]) -> None:
    """Fila 15 + 16 — acordeón de tarjetas por ticker + resumen. Literal de
    `app_old.py:4997-5337` (solo `mode_a`: `app_old.py` no despliega este detalle denso para
    los tickers de crecimiento, solo la tarjeta agregada de la fila 8)."""
    if not mode_a:
        return
    _seccion("Detalle por portafolio",
             "Abre cada portafolio para ver sus posiciones y métricas de riesgo")
    with st.expander(f"PORTAFOLIO DE DIVIDENDOS · income mensual · {_fondos(mode_a)}",
                     expanded=True):
        mostrados = []
        for ticker in mode_a:
            stats = resultados.get(ticker)
            if not isinstance(stats, dict) or "error" in stats:
                continue
            mostrados.append((ticker, stats))
            _tarjeta_ticker(resultados, ticker, stats)
        if mostrados:
            _resumen_consolidado(mostrados)
        else:
            st.info("No hay posiciones YieldMax activas en este portafolio.")


def render_portafolios(resultados: dict) -> None:
    if not resultados:
        st.markdown('<span class="vd-badge">Portafolios</span>', unsafe_allow_html=True)
        st.markdown('<h2 class="vd-title">Portafolios</h2>', unsafe_allow_html=True)
        st.markdown('<p class="vd-lede">Carga tu CSV de transacciones para ver esta vista.</p>',
                    unsafe_allow_html=True)
        return
    classify_map = logic.classify_tickers(list(resultados.keys()))
    mode_a, _mode_b = _tus_dos_portafolios(resultados, classify_map)
    _portafolio_dividendos(resultados, mode_a)
    _detalle_por_portafolio(resultados, mode_a)


# ── Despacho ─────────────────────────────────────────────────────────────────

def render_vista(vista: str, ruta) -> None:
    """Despacho de Detalle — solo Portafolios (poda de Ingresos, Proyección y
    Estrategias, decisión de Daniel 2026-08-25)."""
    from ui.vistas import obtener_resultados

    render_portafolios(obtener_resultados())


ESTILOS_HEREDADAS = """
        .vd-her-seccion {
          font-family: var(--font-mono); font-size: 13px; font-weight: 700;
          letter-spacing: .04em; text-transform: uppercase; color: var(--ink);
          margin: 22px 0 4px;
        }
        .vd-her-subtitulo {
          font-family: var(--font-mono); font-size: 11px; font-weight: 700;
          letter-spacing: .05em; text-transform: uppercase; color: var(--ink);
          margin: 18px 0 6px;
        }
        .vd-her-lede { font-size: 13px; color: var(--ink-2); line-height: 1.6; margin: 0 0 12px; }
        .vd-her-nota { font-size: 12px; color: var(--ink-mut); line-height: 1.6; margin: 0 0 10px; }

        .vd-her-port-cards {
          display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin: 6px 0 14px;
        }
        .vd-her-port-card {
          border: 1px dashed var(--hair); background: var(--panel); padding: 16px 18px;
        }
        .vd-her-port-card-navy { background: var(--panel-tint); }
        .vd-her-port-titulo {
          font-family: var(--font-mono); font-size: 12px; font-weight: 700;
          text-transform: uppercase; letter-spacing: .04em; color: var(--ink); margin: 0;
        }
        .vd-her-port-chip {
          display: inline-block; font-size: 11px; color: var(--ink-mut); margin: 4px 0 10px;
        }
        .vd-her-port-mini { display: flex; flex-wrap: wrap; gap: 14px 22px; }
        .vd-her-port-mini .lbl {
          display: block; font-size: 9.5px; color: var(--ink-mut); text-transform: uppercase;
          letter-spacing: .06em; margin-bottom: 2px;
        }
        .vd-her-port-mini .val {
          font-family: var(--font-mono); font-size: 14px; font-weight: 700; color: var(--ink);
        }

        .vd-her-leyenda { display: flex; justify-content: center; gap: 24px; margin: -4px 0 8px; font-size: 12px; color: var(--ink); }
        .vd-her-dot { display: inline-block; width: 9px; height: 9px; margin-right: 6px; vertical-align: middle; }

        .vd-her-card {
          border-left: 3px solid var(--hair); background: var(--panel-tint);
          padding: 8px 14px; margin: 8px 0;
        }
        .vd-her-card-titulo { font-family: var(--font-mono); font-size: 12px; font-weight: 700; color: var(--ink); margin: 0; }

        .vd-her-callout {
          border-left: 4px solid var(--hair); background: var(--panel-tint);
          padding: 12px 16px; margin: 8px 0 14px;
        }
        .vd-her-callout-eyebrow {
          font-family: var(--font-mono); font-size: 9.5px; font-weight: 700;
          letter-spacing: .1em; text-transform: uppercase; color: var(--ink-mut); margin: 0 0 8px;
        }
        .vd-her-callout-cuerpo { font-size: 12px; color: var(--ink-2); line-height: 1.65; margin: 0; }
        .vd-her-callout-lista { font-size: 12px; color: var(--ink-2); line-height: 1.6; margin: 0; padding-left: 18px; }
        .vd-her-callout-lista li { margin: 0 0 6px; }

        .vd-her-nav-headline { font-weight: 700; font-size: 15px; margin: 10px 0 2px; }
        .vd-her-nav-plain { font-size: 12.5px; color: var(--ink-2); line-height: 1.5; margin: 0 0 4px; }

        .vd-her-tk-header {
          display: flex; align-items: baseline; gap: 10px; margin: 20px 0 10px;
          padding-top: 14px; border-top: 1px dashed var(--hair);
        }
        .vd-her-tk-nombre { font-family: var(--font-mono); font-size: 16px; font-weight: 700; color: var(--ink); }
        .vd-her-tk-badge {
          font-family: var(--font-mono); font-size: 9px; font-weight: 700; letter-spacing: .08em;
          text-transform: uppercase; color: var(--accent); border: 1px solid var(--accent);
          padding: 1px 6px;
        }
        .vd-her-tk-precio { font-size: 12px; color: var(--ink-mut); margin-left: auto; }

        .vd-her-tkpi { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin: 8px 0 10px; }
        .vd-her-tkpi-cell { border: 1px dashed var(--hair); padding: 8px 10px; }
        .vd-her-tkpi-label {
          font-size: 9px; color: var(--ink-mut); text-transform: uppercase; letter-spacing: .06em; margin: 0 0 3px;
        }
        .vd-her-tkpi-value { font-family: var(--font-mono); font-size: 15px; font-weight: 700; color: var(--ink); margin: 0; }
        .vd-her-tkpi-sub { font-size: 10px; color: var(--ink-mut); margin: 2px 0 0; }

        .vd-her-cobertura { font-size: 11px; margin: 0 0 2px; }

        .vd-her-roc-callout { border-left: 3px solid var(--warn); background: var(--panel-tint); padding: 12px 16px; margin: 8px 0; }
        .vd-her-roc-titulo { font-family: var(--font-mono); font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--warn); margin: 0 0 8px; }
        .vd-her-roc-valores { display: flex; gap: 24px; margin-bottom: 8px; }
        .vd-her-roc-num { display: block; font-family: var(--font-mono); font-size: 16px; font-weight: 700; color: var(--ink); }
        .vd-her-roc-sub { display: block; font-size: 10px; color: var(--ink-mut); }
        .vd-her-roc-explica { font-size: 11.5px; color: var(--ink-2); line-height: 1.55; margin: 0; }

        .vd-her-retorno { border-left: 3px solid var(--hair); background: var(--panel-tint); padding: 13px 18px; margin: 8px 0 12px; }
        .vd-her-retorno-label { font-size: 10px; color: var(--ink-mut); font-weight: 400; margin: 0 0 4px; letter-spacing: .08em; text-transform: uppercase; }
        .vd-her-retorno-num { font-family: var(--font-mono); font-size: 24px; font-weight: 700; margin: 0 0 6px; }
        .vd-her-retorno-pct { font-size: 14px; font-weight: 600; }
        .vd-her-retorno-desglose { font-size: 11.5px; color: var(--ink-2); margin: 0; }

        .vd-her-erosion { border-left: 3px solid var(--hair); padding: 12px 16px; margin: 0 0 12px; background: var(--panel-tint); }
        .vd-her-erosion-eyebrow { font-family: var(--font-mono); font-size: 9px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; margin: 0 0 8px; }
        .vd-her-erosion-valores { display: flex; gap: 18px; align-items: flex-end; margin-bottom: 8px; }
        .vd-her-erosion-sub { display: block; font-size: 9px; color: var(--ink-mut); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 2px; }
        .vd-her-erosion-num { display: block; font-family: var(--font-mono); font-size: 18px; font-weight: 800; }
        .vd-her-erosion-vs { font-size: 14px; color: var(--ink-mut); margin-bottom: 4px; }
        .vd-her-erosion-verdict { font-size: 11px; color: var(--ink-2); margin: 0; }
"""
