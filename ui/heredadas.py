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
CAT_LABEL = "Detalle"

VIEWS = {
    "portafolios": "Portafolios",
    "ingresos": "Ingresos",
    "proyeccion": "Proyección",
    "estrategias": "Estrategias",
}

VIEW_ORDER = ("portafolios", "ingresos", "proyeccion", "estrategias")


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
    """Literal de `app_old.py:5160-5219` (retorno total + erosión de NAV si aplica)."""
    total_ret = stats["market_value"] + stats["dividends_collected_cash"] - stats["pocket_investment"]
    total_ret_pct = (total_ret / stats["pocket_investment"] * 100) if stats["pocket_investment"] > 0 else 0
    cap_comp = stats["market_value"] - stats["pocket_investment"]
    inc_comp = stats["dividends_collected_cash"]
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
    total_div = sum(s.get("dividends_collected_cash", 0) for _, s in rows)
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
        "Dividendos cobrados": _money(s.get("dividends_collected_cash", 0)),
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
        st.markdown('<span class="vd-badge">Detalle</span>', unsafe_allow_html=True)
        st.markdown('<h2 class="vd-title">Portafolios</h2>', unsafe_allow_html=True)
        st.markdown('<p class="vd-lede">Carga tu CSV de transacciones para ver esta vista.</p>',
                    unsafe_allow_html=True)
        return
    classify_map = logic.classify_tickers(list(resultados.keys()))
    mode_a, _mode_b = _tus_dos_portafolios(resultados, classify_map)
    _portafolio_dividendos(resultados, mode_a)
    _detalle_por_portafolio(resultados, mode_a)


# ── Ingresos (filas 11, 12, 14) ─────────────────────────────────────────────────

def _annual_income_for(resultados: dict, ticker: str) -> float:
    """Literal de `app_old.py:1909-1925`."""
    s = resultados.get(ticker) or {}
    if not isinstance(s, dict) or "error" in s:
        return 0.0
    mv = s.get("market_value") or 0
    ry = s.get("realized_yield")
    if ry is not None and mv:
        return ry / 100.0 * mv
    ttm = s.get("ttm_income")
    if ttm:
        return float(ttm)
    fy = s.get("forward_yield")
    if fy is not None and mv:
        return fy / 100.0 * mv
    return 0.0


def _dona_concentracion(resultados: dict) -> None:
    """«¿De dónde viene tu ingreso?» — literal de `app_old.py:4956-4995`. No depende del
    income CSV: usa `results` directo, igual que en producción."""
    growth_fn = getattr(logic, "filter_growth_assets", None)
    growth_set = set((growth_fn(resultados) or {}).keys()) if growth_fn else set()
    contrib = {t: v for t in resultados if t not in growth_set
              for v in [_annual_income_for(resultados, t)] if v > 0}
    if len(contrib) < 2:
        return

    import altair as alt
    import pandas as pd

    items = sorted(contrib.items(), key=lambda kv: -kv[1])
    if len(items) > 6:
        items = items[:6] + [("Otros", sum(v for _, v in items[6:]))]
    df = pd.DataFrame([{"Ticker": t, "Ingreso": v} for t, v in items])
    total = df["Ingreso"].sum()
    df["Pct"] = df["Ingreso"] / total * 100 if total else 0
    paleta = ["#3ea0d6", "#8f76d4", "#4caf82", "#c9821f", "#60a5fa", "#86efac", "#8899aa"]
    top_tk, top_v = items[0]
    top_pct = (top_v / total * 100) if total else 0

    _seccion("¿De dónde viene tu ingreso? (concentración)")
    arco = (alt.Chart(df).mark_arc(innerRadius=70, strokeWidth=2)
            .encode(theta=alt.Theta("Ingreso:Q", stack=True),
                    order=alt.Order("Ingreso:Q", sort="descending"),
                    color=alt.Color("Ticker:N",
                                    scale=alt.Scale(domain=list(df["Ticker"]), range=paleta),
                                    legend=alt.Legend(title=None, orient="right", labelFontSize=11)),
                    tooltip=[alt.Tooltip("Ticker:N", title="Activo"),
                             alt.Tooltip("Ingreso:Q", format="$,.0f", title="Ingreso anual"),
                             alt.Tooltip("Pct:Q", format=".1f", title="% del total")])
            .properties(height=280))
    st.altair_chart(arco, use_container_width=True)
    top3 = df["Pct"].iloc[:3].sum()
    conc_txt = f", y el <b>{top3:.0f}%</b> de tus 3 mayores." if len(items) >= 3 else "."
    st.markdown(f'<p class="vd-her-nota">El <b>{top_pct:.0f}%</b> de tu ingreso viene de '
                f'<b>{top_tk}</b>{conc_txt} Una concentración alta significa que tu ingreso '
                "depende mucho de ese activo.</p>", unsafe_allow_html=True)


def _tabla_income_comparacion(items, proj: dict) -> None:
    """Fila 11 — tabla Schwab vs cálculo (recibido 12m, proyectado anual, histórico).
    Condensa `app_old.py:4295-4300` (`_rows_ann`/`_rows_hist`) en una sola tabla nativa."""
    import pandas as pd

    def fila(t, d):
        return {
            "ETF": t,
            "Recibido 12m (Schwab)": _money(d.get("schwab_received_12m"), 0),
            "Recibido 12m (calc.)": _money(d.get("our_received_total"), 0),
            "Proy. anual (Schwab)": _money(d.get("schwab_proj"), 0),
            "Proy. anual (calc.)": _money(d.get("our_proj"), 0),
            "Histórico (Schwab)": _money(d.get("schwab_received_total"), 0),
            "Histórico (calc.)": _money(d.get("our_received_total"), 0),
        }

    df = pd.DataFrame([fila(t, d) for t, d in items])
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.caption("«Δ%» implícito entre Schwab y calc.: cerca de 0% tu CSV está completo; si "
              "Schwab reporta bastante más, revisa que el archivo cubra todo el año. En "
              "«Proyectado anual», Schwab repite tu último pago (optimista); la calculadora "
              "promedia los últimos ~3 meses (realista) — en YieldMax el pago suele bajar con "
              "el tiempo, así que en caso de duda guíate por la cifra de la calculadora.")


def _grafica_ingreso_acumulado(sum_sproj: float, sum_oproj: float) -> None:
    """Literal de `app_old.py:4308-4385` — acumulado Schwab vs cálculo, 12 meses."""
    import datetime as _dt

    import altair as alt
    import pandas as pd

    meses_abbr = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    meses = [meses_abbr[(_dt.date.today().month - 1 + i) % 12] for i in range(12)]
    m_sch, m_cal = sum_sproj / 12.0, sum_oproj / 12.0
    filas = []
    for i, mes in enumerate(meses, start=1):
        filas.append({"Mes": mes, "Serie": "Schwab (acumulado)", "Monto": m_sch * i})
        filas.append({"Mes": mes, "Serie": "Tu cálculo (acumulado)", "Monto": m_cal * i})
    df = pd.DataFrame(filas)
    series = ["Schwab (acumulado)", "Tu cálculo (acumulado)"]
    colores = ["#3ea0d6", "#8f76d4"]

    st.markdown(
        '<p class="vd-her-subtitulo">Ingreso acumulado en el año: Schwab vs tu cálculo</p>'
        '<p class="vd-her-nota">Cada punto suma todo lo que llevarías cobrado desde hoy '
        "hasta ese mes. La línea Schwab repite tu último pago como si nunca bajara; tu "
        "cálculo usa el ritmo real reciente — por eso la separación se ensancha con el "
        "tiempo.</p>", unsafe_allow_html=True)
    linea = alt.Chart(df).mark_line(point=True, strokeWidth=2.5).encode(
        x=alt.X("Mes:O", sort=meses, title=None),
        y=alt.Y("Monto:Q", title="USD acumulado", axis=alt.Axis(format="$,.0f")),
        color=alt.Color("Serie:N", sort=series, scale=alt.Scale(domain=series, range=colores),
                        legend=alt.Legend(title=None, orient="top")),
        tooltip=[alt.Tooltip("Mes:O", title="Mes"), alt.Tooltip("Serie:N", title="Serie"),
                 alt.Tooltip("Monto:Q", format="$,.0f", title="USD acumulado")])
    st.altair_chart(linea.properties(height=300), use_container_width=True)
    gap_pct = ((sum_sproj / sum_oproj - 1) * 100) if sum_oproj > 0 else None
    if gap_pct is not None:
        st.caption(f"Δ {gap_pct:+.0f}% · {_money(sum_sproj - sum_oproj, 0)}/año de diferencia "
                  "entre lo que proyecta Schwab y tu cálculo, acumulado a fin de año.")


def _justificacion_sobreestimacion(proj: dict) -> None:
    """Literal de `app_old.py:4387-4422`."""
    flagged = sorted(
        [(t, d) for t, d in proj.items()
         if (d.get("overstatement_pct") or 0) > logic.INCOME_OVERSTATE_FLAG_PCT],
        key=lambda x: -(x[1]["overstatement_pct"] or 0))
    stable = [t for t, d in proj.items() if abs(d.get("overstatement_pct") or 0) <= 5]
    if not flagged:
        return

    def pct_below(d):
        a = d.get("anchor_per_payment") or 0
        r = d.get("recent_per_payment") or 0
        return (1 - r / a) * 100 if a else 0

    items_html = "".join(
        f"<li><b>{t}</b>: Schwab supone que vas a seguir cobrando "
        f'<b>{_money(d.get("anchor_per_payment"))}</b> por acción en cada pago (tu último '
        f'pago alto) y por eso proyecta <b>{_money(d.get("schwab_proj"), 0)}</b> al año. Pero '
        f'tus pagos recientes ya bajaron a <b>{_money(d.get("recent_per_payment"))}</b> en '
        f'promedio — <b style="color:var(--warn);">un {pct_below(d):.0f}% más bajo</b>. Con '
        f'ese ritmo real cobrarías unos <b style="color:var(--accent);">'
        f'{_money(d.get("our_proj"), 0)}</b> al año. (En los últimos 12 meses recibiste '
        f'{_money(d.get("schwab_received_12m"), 0)}.)</li>'
        for t, d in flagged)
    stable_html = ""
    if stable:
        stable_html = (f'<p class="vd-her-nota">En cambio, en los fondos de dividendo estable '
                       f'({", ".join(stable)}) las dos proyecciones casi coinciden. La '
                       "diferencia solo aparece en los fondos tipo YieldMax: lo que pagan por "
                       "acción va bajando mes a mes, pero Schwab da por hecho que seguirás "
                       "cobrando igual que en tu mejor pago.</p>")
    st.markdown(
        '<div class="vd-her-callout" style="border-left-color: var(--warn);">'
        '<p class="vd-her-callout-eyebrow">Por qué la proyección de Schwab está inflada</p>'
        f'<ul class="vd-her-callout-lista">{items_html}</ul>{stable_html}</div>',
        unsafe_allow_html=True)


def _cuadricula_roc_consolidada(items, resultados: dict, roc19a_asof: dict) -> None:
    """Fila 12 — «Detalle consolidado Schwab vs cálculo · ROC». Condensa
    `app_old.py:4424-4595` en una tabla nativa; Regla 3 no aplica aquí (esto no es
    `tax_summary`, es la cuadrícula de ROC/dividendos por transacciones)."""
    import pandas as pd

    filas = []
    total = {"pagado": 0.0, "drip": 0.0, "cash": 0.0, "pkt": 0.0, "mv": 0.0,
             "basis": 0.0, "roc": 0.0, "basis_has": False, "roc_has": False}
    for t, _d in items:
        rs = resultados.get(t, {})
        roc_a = rs.get("roc_accumulated")
        roc_p = rs.get("roc_percent")
        roc_src = rs.get("roc_source")
        basis = rs.get("ib_cost_basis")
        # "Div. pagados (neto)" — antes leía `total_dividends`, que mezcla bases (bruto para
        # el cash de Schwab, neto para IB/DRIP): la columna decía "neto" y mostraba una
        # mezcla. `dividends_net_total` es el objeto fiscal único (`build_dividend_tax_totals`,
        # corrido dentro de `analyze_portfolio`), ya resuelto por ticker; si no está (stats
        # legado sin pasar por `analyze_portfolio`) degrada al campo anterior.
        pagado_neto = rs.get("dividends_net_total")
        if pagado_neto is None:
            pagado_neto = rs.get("total_dividends") or 0
        filas.append({
            "ETF": t,
            "Div. pagados (neto)": _money(pagado_neto, 0),
            "ROC": (f"{_money(roc_a, 0)} ({roc_p:.0f}%)" if roc_a is not None else "n/d")
                   + (" est.19a" if roc_src == "19a" else ""),
            "Reinvertidos": _money(rs.get("dividends_collected_drip"), 0),
            "En efectivo": _money(rs.get("dividends_collected_cash"), 0),
            "Invertido": _money(rs.get("pocket_investment"), 0),
            "Costo bróker": _money(basis, 0),
            "Valor actual": _money(rs.get("market_value"), 0),
        })
        total["pagado"] += pagado_neto
        total["drip"] += rs.get("dividends_collected_drip") or 0
        total["cash"] += rs.get("dividends_collected_cash") or 0
        total["pkt"] += rs.get("pocket_investment") or 0
        total["mv"] += rs.get("market_value") or 0
        if basis is not None:
            total["basis"] += basis
            total["basis_has"] = True
        if roc_a is not None:
            total["roc"] += roc_a
            total["roc_has"] = True

    filas.append({
        "ETF": "TOTAL",
        "Div. pagados (neto)": _money(total["pagado"], 0),
        "ROC": _money(total["roc"], 0) if total["roc_has"] else "—",
        "Reinvertidos": _money(total["drip"], 0),
        "En efectivo": _money(total["cash"], 0),
        "Invertido": _money(total["pkt"], 0),
        "Costo bróker": _money(total["basis"], 0) if total["basis_has"] else "—",
        "Valor actual": _money(total["mv"], 0),
    })
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
    st.markdown(
        "**ROC (Retorno de Capital)** es la parte de tus distribuciones que el fondo declara "
        "como devolución de tu propio capital, no rendimiento. La fuente oficial es el aviso "
        "**19a-1** del fondo (= tu 1099-DIV casilla 3, marcado *est.19a*). La app también "
        "puede estimar el ROC como (Invertido + Reinvertido) − Costo bróker cuando tiene tu "
        "costo base, pero con reinversión esa resta **subestima** el ROC — por eso manda el "
        "% oficial del fondo cuando está disponible.")
    if not total["basis_has"] and not any(resultados.get(t, {}).get("roc_source") == "19a" for t, _ in items):
        st.caption("Sube el costo base de tu bróker en el paso de captura para calcular el ROC.")


# ── Filas 13, 32 — infografía visual del ROC ────────────────────────────────

SHOW_ROC_INFOGRAPHIC = True  # literal de `app_old.py:59` (fila 32) — alterna la fila 13.


def _infografia_roc(resultados: dict) -> None:
    """Fila 13 — panel de infografía ROC por ETF elegible. Literal de
    `app_old.py:4500-4521`: solo fondos con ROC en pérdida (25-100% de ROC, ROC ≤
    distribuciones totales, valor de mercado < bolsillo). Aditivo: solo lee
    `resultados`, con `try/except` — si algo falla no muestra nada ni rompe la vista."""
    if not SHOW_ROC_INFOGRAPHIC:
        return
    try:
        import streamlit.components.v1 as components

        from roc_infographic import roc_infographic_html
    except Exception:
        return
    for ticker, stats in resultados.items():
        if not isinstance(stats, dict):
            continue
        roc_acc = stats.get("roc_accumulated")
        roc_pct = stats.get("roc_percent")
        pocket = stats.get("pocket_investment")
        mv = stats.get("market_value")
        total_div = stats.get("total_dividends") or 0
        elegible = (roc_acc and roc_pct and 25 <= roc_pct <= 100 and roc_acc <= total_div
                   and pocket and mv is not None and mv < pocket)
        if not elegible:
            continue
        try:
            html = roc_infographic_html(stats, ticker)
        except Exception:
            continue
        if not html:
            continue
        with st.expander(f"📊 Explicación visual del ROC — {ticker}"):
            components.html(html, height=2480, scrolling=True)


def render_ingresos(resultados: dict) -> None:
    st.markdown('<span class="vd-badge">Detalle</span>', unsafe_allow_html=True)
    st.markdown('<h2 class="vd-title">Ingresos</h2>', unsafe_allow_html=True)

    if not resultados:
        st.markdown('<p class="vd-lede">Carga tu CSV de transacciones para ver esta vista.</p>',
                    unsafe_allow_html=True)
        return

    _dona_concentracion(resultados)

    income_df = st.session_state.get("_wizard_income_df")
    if income_df is None or len(income_df) == 0:
        st.markdown(
            '<p class="vd-lede">Sube tu <b>Investment Income</b> de Schwab en el Bloque 3 de '
            "la carga para ver la comparación línea por línea contra tu cálculo (recibido, "
            "proyectado y Retorno de Capital por fondo).</p>", unsafe_allow_html=True)
        return

    proj_all = logic.project_income(income_df, resultados)
    proj, dropped = logic.filter_income_assets(proj_all, resultados)

    if proj:
        _seccion("Ingreso y comparación con el broker",
                 "El número fino: lo recibido vs lo proyectado, tu Retorno de Capital por "
                 "activo y por qué la proyección del broker suele estar inflada.")

        items = sorted(proj.items(), key=lambda kv: (kv[1].get("schwab_received_12m") or 0),
                       reverse=True)
        sum_sproj = sum((d.get("schwab_proj") or 0) for d in proj.values())
        sum_oproj = sum((d.get("our_proj") or 0) for d in proj.values())

        with st.expander("Ver detalle · tabla consolidada (Schwab vs tu cálculo · ROC) · "
                         "gráfica de ingresos", expanded=False):
            _grafica_ingreso_acumulado(sum_sproj, sum_oproj)
            if dropped:
                st.caption("No se grafican " + ", ".join(t for t, _ in dropped)
                          + ": su dividendo es marginal y quedan fuera del portafolio de ingresos.")
            _justificacion_sobreestimacion(proj)
            st.markdown('<p class="vd-her-subtitulo">Ingreso, ROC y comparación con Schwab · '
                        "consolidado</p>", unsafe_allow_html=True)
            _cuadricula_roc_consolidada(items, resultados, {})
            _tabla_income_comparacion(items, proj)
    else:
        st.markdown('<p class="vd-lede">Tu Investment Income no tiene dividendos que '
                    "coincidan con los tickers analizados.</p>", unsafe_allow_html=True)

    # HERMANA de `if proj:`, no hija — y fuera de todo expander. Las dos cosas son
    # deliberadas y calcan `app_old.py`: allí `if SHOW_ROC_INFOGRAPHIC:` (`app_old.py:4504`) está
    # al mismo indent que `if _proj:` (`app_old.py:4064`), ambos colgando del gate del income
    # CSV (`app_old.py:4059`). O sea: la infografía se muestra aunque el income no cruce con
    # ningún ticker, y no puede anidarse porque abre un `st.expander` por ETF elegible.
    _infografia_roc(resultados)


# ── Filas 17, 18 — Proyección a futuro y escenarios ─────────────────────────

def _concentracion_por_factor(resultados: dict, classify_map: dict) -> None:
    """Literal de `app_old.py:5247-5269` — correlación oculta por factor/subyacente."""
    fc = logic.build_factor_concentration(resultados, classify_map)
    if not fc.get("factors") or len(fc["factors"]) < 1:
        return
    accent = "--warn" if fc.get("hidden_correlation") else "--accent"
    frows = "".join(
        f'<li><b>{f["factor"]}</b> — {f["income_share_pct"]:.0f}% de tu ingreso '
        f'({", ".join(f["tickers"])})</li>'
        for f in fc["factors"][:5])
    if fc.get("hidden_correlation"):
        top = fc["factors"][0]
        titulo = "Correlación oculta detectada"
        intro = (f'<p class="vd-her-nota">Se ve diversificado, pero el <b>'
                 f'{top["income_share_pct"]:.0f}% de tu ingreso depende de un solo factor '
                 f'({top["factor"]})</b> vía {", ".join(top["tickers"])}. Si ese factor cae, '
                 "varias de tus posiciones caen juntas.</p>")
    else:
        titulo = "De dónde viene tu ingreso (por factor)"
        intro = ""
    st.markdown(
        f'<div class="vd-her-callout" style="border-left-color: var({accent});">'
        f'<p class="vd-her-callout-eyebrow" style="color: var({accent});">{titulo}</p>'
        + intro +
        f'<ul class="vd-her-callout-lista">{frows}</ul>'
        '<p class="vd-her-nota">Ingreso forward anual agrupado por el subyacente de cada '
        "fondo (MSTR y COIN cuentan como Bitcoin). Educativo — no es recomendación.</p></div>",
        unsafe_allow_html=True)


def _carrera_yieldmax(resultados: dict, fwd: dict, p_hz: int) -> None:
    """YieldMax — ingreso vs erosión de capital + veredicto de salud del NAV.
    Literal de `app_old.py:5446-5567`."""
    import datetime as _dt

    import altair as alt
    import pandas as pd

    pt = fwd["per_ticker"]
    ym = [(tk, pt[tk]) for tk in fwd["eligible"] if pt[tk]["is_yieldmax"]]
    if not ym:
        return
    st.markdown("**YieldMax — ingreso vs erosión de capital (comprar y cobrar, sin DRIP)**")
    wlbl = {"12m": "últimos 12 meses", "vida": "toda la vida del fondo",
            "manual": "tu valor manual", "default": "estimación por defecto"}
    ventana = wlbl.get(next((pt[t].get("decay_window") for t, _ in ym), "12m"), "últimos 12 meses")
    st.caption(
        "La línea verde es el dinero que cobras; la roja, cuánto cayó tu capital. El "
        "cruce es el punto en que el ingreso ya cubrió la pérdida del precio. El total "
        "return honesto incluye ambos efectos — no solo el yield de portada. La erosión "
        f"se estima con el decaimiento de los {ventana} (puedes ajustar el supuesto arriba).")

    for tk, e in ym:
        bm = e.get("breakeven_month")
        be_txt = f"breakeven al mes {bm}" if bm else "no alcanza breakeven en el horizonte"
        roc = e.get("roc_fraction_pct")
        roc_txt = (f" · ~{roc:.0f}% de las distribuciones es retorno de capital (no es "
                   "rendimiento)" if roc is not None else "")
        htr = e.get("honest_total_return_pct")
        st.markdown(
            f"**{tk}** — yield portada {e['forward_yield']:.0f}% · total return honesto "
            f"{('%+.0f%%' % htr) if htr is not None else 'n/d'} a {p_hz} año(s) · "
            f"{be_txt}{roc_txt}")

        rs = resultados.get(tk, {}) or {}
        asof_days = None
        r19 = logic.load_roc_19a().get(str(tk).upper())
        if r19 and r19.get("asof"):
            try:
                asof_days = (_dt.date.today() - _dt.date.fromisoformat(r19["asof"])).days
            except Exception:
                asof_days = None
        prev_v = logic.latest_health_verdict(tk)
        verdict = logic.classify_roc_health(
            roc_pct=roc,
            price_cagr=(rs.get("price_cagr_recent") if rs.get("price_cagr_recent") is not None
                       else rs.get("price_cagr")),
            total_return_pct=htr, history_days=rs.get("price_history_days"),
            roc_asof_days=asof_days, prev_verdict=prev_v,
            underlying_cagr=rs.get("underlying_cagr_recent"))
        vreason = verdict["reason"]
        if verdict["verdict"] == "destructive":
            u, f, und = rs.get("underlying_cagr_recent"), rs.get("price_cagr_recent"), rs.get("underlying_ticker")
            if u is not None and f is not None and und:
                vreason += f" En 12m el NAV de {tk} hizo {f:+.0f}% mientras {str(und).upper()} hizo {u:+.0f}%."

        score = verdict.get("gauge_score")
        if score is None:
            gauge_html = ('<div style="height:14px;background:var(--panel-tint);color:var(--ink-mut);'
                         'font-size:10px;text-align:center;line-height:14px;">no medible aún</div>')
        else:
            gauge_html = (
                '<div style="position:relative;height:14px;margin:6px 0 2px 0;'
                "background:linear-gradient(90deg,#4caf82 0%,#e0a23c 50%,#e05c5c 100%);\">"
                f'<div style="position:absolute;top:-3px;left:{score:.0f}%;width:3px;'
                'height:20px;background:var(--ink);transform:translateX(-50%);"></div></div>'
                '<div style="display:flex;justify-content:space-between;font-size:10px;'
                'color:var(--ink-mut);"><span>Sano</span><span>Destruyéndose</span></div>')
        st.markdown(
            f'<div style="margin:6px 0 2px 0;font-weight:700;font-size:15px;'
            f'color:{verdict["color"]};">{verdict["headline"]}</div>{gauge_html}'
            f'<div style="font-size:12.5px;color:var(--ink-2);margin:6px 0 2px 0;'
            f'line-height:1.5;">{verdict["plain"]}</div>', unsafe_allow_html=True)

        navc = rs.get("price_cagr_recent")
        if navc is None:
            navc = rs.get("price_cagr")
        nums = []
        if navc is not None:
            nums.append(f"NAV {navc:+.0f}%/año")
        if roc is not None:
            nums.append(f"ROC {roc:.0f}%")
        if htr is not None:
            nums.append(f"total return honesto {htr:+.0f}%")
        # `<details>` HTML, no `st.expander`: esta sección ya vive dentro del expander
        # «Proyección a futuro (escenario)» y Streamlit no permite expanders anidados
        # (mismo motivo documentado en `app_old.py:5518-5520`).
        st.markdown(
            "<details style='margin:2px 0 8px 0;'>"
            "<summary style='cursor:pointer;font-size:12px;color:var(--accent);'>"
            "Ver detalle técnico</summary>"
            + (f'<div style="font-size:12px;color:var(--ink-mut);margin:4px 0;">'
               f'{" · ".join(nums)}</div>' if nums else "")
            + f'<div style="font-size:12.5px;color:var(--ink-2);line-height:1.5;">'
              f"{vreason}</div></details>", unsafe_allow_html=True)

        vh = logic.load_roc_health_history().get(str(tk).upper()) or []
        if len(vh) >= 2:
            vhdf = pd.DataFrame(vh)
            vhdf["date"] = pd.to_datetime(vhdf["date"])
            vlabels = {"destructive": "Destructivo", "accounting": "Contable",
                      "mixed": "Vigilar", "insufficient": "Sin datos"}
            vhdf["Veredicto"] = vhdf["verdict"].map(vlabels).fillna(vhdf["verdict"])
            vchart = alt.Chart(vhdf).mark_line(point=True, color="#8a8f98").encode(
                x=alt.X("date:T", title="Fecha"), y=alt.Y("price_cagr:Q", title="NAV %/año"),
                color=alt.Color("Veredicto:N", scale=alt.Scale(
                    domain=["Destructivo", "Contable", "Vigilar", "Sin datos"],
                    range=["#e05c5c", "#4caf82", "#e0a23c", "#8a8f98"])),
                tooltip=["date:T", "Veredicto:N", "roc_pct:Q", "price_cagr:Q"],
            ).properties(height=130)
            st.altair_chart(vchart, use_container_width=True)

        exp = logic.build_underlying_exposure(resultados, tk)
        if exp["lines"]:
            st.markdown(
                '<div class="vd-her-callout" style="border-left-color: var(--ink);">'
                '<p class="vd-her-callout-eyebrow">Exposición al subyacente (riesgo asimétrico)</p>'
                f'<ul class="vd-her-callout-lista">{"".join(f"<li>{l}</li>" for l in exp["lines"])}'
                "</ul></div>", unsafe_allow_html=True)

        rr = e.get("race") or []
        if rr:
            rdf = pd.DataFrame(
                [{"Mes": r["month"], "Serie": "Ingreso acum. (neto)", "Valor": r["cum_income_net"]} for r in rr]
                + [{"Mes": r["month"], "Serie": "Pérdida de capital", "Valor": r["capital_loss"]} for r in rr])
            rchart = alt.Chart(rdf).mark_line().encode(
                x=alt.X("Mes:Q", title="Mes"), y=alt.Y("Valor:Q", title="USD", axis=alt.Axis(format="$,.0f")),
                color=alt.Color("Serie:N", scale=alt.Scale(
                    domain=["Ingreso acum. (neto)", "Pérdida de capital"], range=["#4caf82", "#e05c5c"]),
                    legend=alt.Legend(title=None, orient="top")),
                tooltip=["Mes", "Serie", alt.Tooltip("Valor:Q", format="$,.0f")],
            ).properties(height=220)
            st.altair_chart(rchart, use_container_width=True)


def _modulo_fiscal_nra(resultados: dict, fwd: dict, p_country: str) -> None:
    """Literal de `app_old.py:5569-5590`."""
    import pandas as pd

    with st.container(border=True):
        st.markdown(f"**Módulo fiscal — tu retención real en {p_country}**")
        tax_rows = []
        for tk in fwd["eligible"]:
            bd = logic.nra_tax_breakdown(p_country, logic._ticker_roc_fraction(tk, resultados))
            tax_rows.append({"Activo": tk, "ROC": f"{bd['roc_fraction']:.0f}%",
                             "Nominal (creías)": f"{bd['base_rate']:.0f}%",
                             "Efectiva (real)": f"{bd['effective_rate']:.1f}%"})
        st.dataframe(pd.DataFrame(tax_rows), use_container_width=True, hide_index=True)
        st.caption("ROC reciente (últimos ~12 avisos 19a) — no el histórico completo del "
                  "fondo, para reflejar mejor el escudo fiscal vigente.")
        best = max(fwd["eligible"], default=None,
                  key=lambda t: logic._ticker_roc_fraction(t, resultados))
        if best is not None:
            eb = fwd["per_ticker"][best]
            gross = eb["forward_yield"] / 100.0 * eb["start_value"]
            bd = logic.nra_tax_breakdown(p_country, logic._ticker_roc_fraction(best, resultados),
                                        nominal_income=gross)
            st.markdown(f"**Ejemplo con {best}** (ingreso anual estimado {_money(gross, 0)}):")
            for l in bd["lines"]:
                st.markdown(f"- {l}")
            st.caption(bd["audit_note"])


def _monte_carlo(resultados: dict, classify_map: dict, proj_params: dict) -> None:
    """Literal de `app_old.py:5592-5607` — rango de resultados posibles."""
    import altair as alt
    import pandas as pd

    with st.container(border=True):
        st.markdown("**Escenarios (Monte Carlo) — el rango de lo que puede pasar**")
        c1, c2 = st.columns(2)
        with c1:
            mc_infl = st.number_input("Inflación anual % (para la vista real)", min_value=0.0,
                                      max_value=20.0, value=3.0, step=0.5, key="vd_her_mc_infl")
        with c2:
            mc_real = st.checkbox("Mostrar en poder de compra de hoy (descontar inflación)",
                                  value=False, key="vd_her_mc_real")
        mc = logic.monte_carlo_projection(
            resultados, {**proj_params, "inflation_pct": mc_infl, "real_view": mc_real},
            classify_map, n_paths=500, seed=123)
        if not mc["bands"]:
            return
        f = mc["final"]
        k1, k2 = st.columns(2)
        k1.metric("Valor final — rango probable (p10–p90)",
                  f"{_money(f['p10'], 0)} – {_money(f['p90'], 0)}", f"mediana {_money(f['p50'], 0)}")
        if mc["prob_goal"] is not None:
            k2.metric("Prob. de cumplir tu meta de ingreso", f"{mc['prob_goal']:.0f}%")
        brows = []
        for b in mc["bands"]:
            brows += [{"Año": b["year"], "Banda": "Pesimista (p10)", "Valor": b["p10"]},
                     {"Año": b["year"], "Banda": "Mediana (p50)", "Valor": b["p50"]},
                     {"Año": b["year"], "Banda": "Optimista (p90)", "Valor": b["p90"]}]
        bchart = alt.Chart(pd.DataFrame(brows)).mark_line(point=True).encode(
            x=alt.X("Año:O", title="Año"), y=alt.Y("Valor:Q", title="USD", axis=alt.Axis(format="$,.0f")),
            color=alt.Color("Banda:N", scale=alt.Scale(
                domain=["Pesimista (p10)", "Mediana (p50)", "Optimista (p90)"],
                range=["#e05c5c", "#021C36", "#4caf82"]), legend=alt.Legend(title=None, orient="top")),
            tooltip=["Año", "Banda", alt.Tooltip("Valor:Q", format="$,.0f")],
        ).properties(height=280)
        st.altair_chart(bchart, use_container_width=True)
        st.caption(f"{mc['n_paths']} escenarios aleatorios usando la volatilidad observada "
                  "de cada activo, con un retorno distinto cada año (riesgo de secuencia). "
                  + ("Valores en poder de compra de hoy (inflación descontada)."
                     if mc["real_view"] else "Valores nominales."))


def _proyeccion_escenario(resultados: dict, classify_map: dict) -> None:
    """Filas 17/18 — expander «Proyección a futuro (escenario)». Literal de
    `app_old.py:5286-5608`: sliders de horizonte/aporte/país/DRIP/crecimiento,
    `logic.project_portfolio_forward`, tabla por activo, carrera YieldMax, módulo
    fiscal NRA y Monte Carlo."""
    proj_elig = [t for t, s in resultados.items()
                if isinstance(s, dict) and "error" not in s
                and (s.get("forward_yield") or 0) > 0
                and (s.get("shares_owned") or 0) > 0 and (s.get("current_price") or 0) > 0]
    if not proj_elig:
        return
    import altair as alt
    import pandas as pd

    with st.expander("Proyección a futuro (escenario)", expanded=False):
        st.caption(
            "Es un escenario, no una promesa: parte de tu yield actual y de supuestos que "
            "tú controlas. Los YieldMax se proyectan con su erosión de NAV observada — "
            "nunca se asume que su precio sube; los ETF de crecimiento usan los supuestos "
            "de abajo.")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            p_hz = st.slider("Horizonte (años)", 1, 30, 5, key="vd_her_proj_hz")
        with c2:
            p_contrib = st.number_input("Aporte mensual ($)", min_value=0.0, value=0.0,
                                        step=50.0, key="vd_her_proj_contrib")
        with c3:
            # El selector de país ya no vive aquí: se declara una vez en el Paso 2 y esta
            # vista LEE el perfil, como todas las demás. Estar enterrado en un expander
            # colapsado de una sub-vista fue justo lo que permitió que su valor no llegara
            # a ninguna otra cifra fiscal de la app durante todo el port.
            _perfil = estado.perfil_fiscal()
            p_country = _perfil["country"]
            if _perfil["rate_declared"]:
                st.metric("Retención NRA", f'{_perfil["rate_pct"]:.0f}%',
                          help=f'Residencia declarada: {p_country}. Se cambia en el Paso 2.')
            else:
                st.metric("Retención NRA", "sin declarar",
                          help="Declara tu residencia fiscal en el Paso 2 para proyectar "
                               "los ingresos netos de retención.")
        with c4:
            p_drip = st.checkbox("Reinvertir (DRIP)", value=True, key="vd_her_proj_drip")
        c5, c6, c7 = st.columns(3)
        with c5:
            p_divg = st.number_input("Crecim. dividendo % (solo ETFs)", min_value=-20.0,
                                     max_value=30.0, value=0.0, step=1.0, key="vd_her_proj_divg",
                                     help="Aplica a ETF de dividendo/crecimiento. Los "
                                         "YieldMax usan su erosión observada, no este valor.")
        with c6:
            p_priceg = st.number_input("Apreciación precio % (solo ETFs)", min_value=-20.0,
                                       max_value=30.0, value=0.0, step=1.0, key="vd_her_proj_priceg",
                                       help="Aplica a ETF de crecimiento. En YieldMax se ignora.")
        with c7:
            p_goal = st.number_input("Meta ingreso mensual ($)", min_value=0.0, value=0.0,
                                     step=100.0, key="vd_her_proj_goal")

        ym_elig = [t for t in proj_elig if classify_map.get(t) == "mode_a"
                  and (resultados.get(t) or {}).get("underlying_cagr_recent") is not None]
        scenarios = {}
        if ym_elig:
            with st.container(border=True):
                st.markdown("**Escenario del subyacente (YieldMax) — ¿y si la acción base "
                           "se recupera?**")
                st.caption(
                    "Pon el retorno anual que esperas del SUBYACENTE (MSTR para MSTY, etc.) "
                    "y el fondo lo refleja con captura asimétrica: toma casi toda la caída "
                    "pero poca de la subida, menos su erosión estructural. El valor por "
                    "defecto es el ritmo observado del subyacente en los últimos 12 meses.")
                for ymt in ym_elig:
                    u = resultados[ymt].get("underlying_ticker") or "?"
                    uobs = resultados[ymt].get("underlying_cagr_recent") or 0.0
                    scenarios[ymt] = st.number_input(
                        f"{ymt} — retorno anual de {u} (%)", min_value=-90.0, max_value=300.0,
                        value=float(round(uobs, 1)), step=5.0, key=f"vd_her_scen_{ymt}")

        proj_params = {"horizon_years": p_hz, "monthly_contribution": p_contrib,
                       "drip": p_drip, "country": p_country,
                       "dividend_growth_pct": p_divg, "price_appreciation_pct": p_priceg,
                       "income_goal_monthly": (p_goal or None),
                       "underlying_scenarios": (scenarios or None)}
        fwd = logic.project_portfolio_forward(resultados, proj_params, classify_map)
        pf, pt = fwd["portfolio"], fwd["per_ticker"]

        proj_unrel = [t for t in fwd["eligible"]
                     if logic.assess_ticker_quality(resultados, t)["level"] in ("unreliable", "reconciled")]
        if proj_unrel:
            st.caption("Aviso — " + ", ".join(proj_unrel) + ": costo de origen incompleto "
                      "(acciones por transferencia); su punto de partida y la proyección "
                      "son aproximados.")

        if not pf.get("yearly"):
            return
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Valor proyectado", _money(pf["end_value"], 0),
                 f"{(pf['end_value']/pf['start_value']-1)*100:+.0f}% vs hoy"
                 if pf["start_value"] > 0 else None)
        last = pf["yearly"][-1]
        m2.metric("Ingreso anual (último año)", _money(last["annual_income"], 0),
                 f"{_money(last['annual_income']/12, 0)}/mes")
        m3.metric("Dividendos netos acumulados", _money(pf["cumulative_dividends_net"], 0))
        m4.metric("Ventaja del DRIP", _money(pf["drip_advantage"], 0),
                 help="Cuánto más vale el portafolio reinvirtiendo vs tomando los "
                     "dividendos en efectivo, al final del horizonte.")
        if p_country:
            st.caption(f"Ingresos netos de la retención NRA de {p_country} (efectiva por "
                      "activo, ya descontado el escudo del ROC). El histórico de arriba "
                      "sigue en bruto.")
        if pf.get("income_goal_monthly"):
            gy = pf.get("income_goal_year")
            st.caption(f"Meta de {_money(pf['income_goal_monthly'], 0)}/mes: "
                      + (f"se alcanza alrededor del año {gy}." if gy
                         else "no se alcanza dentro del horizonte proyectado."))

        crows = []
        for r in pf["yearly"]:
            crows.append({"Año": r["year"], "Serie": "Valor del portafolio", "Valor": r["portfolio_value"]})
            crows.append({"Año": r["year"], "Serie": "Dividendos acum. (neto)", "Valor": r["cumulative_dividends"]})
        cdf = pd.DataFrame(crows)
        chart = alt.Chart(cdf).mark_line(point=True).encode(
            x=alt.X("Año:O", title="Año"), y=alt.Y("Valor:Q", title="USD", axis=alt.Axis(format="$,.0f")),
            color=alt.Color("Serie:N", scale=alt.Scale(
                domain=["Valor del portafolio", "Dividendos acum. (neto)"], range=["#006497", "#4caf82"]),
                legend=alt.Legend(title=None, orient="top")),
            tooltip=["Año", "Serie", alt.Tooltip("Valor:Q", format="$,.0f")],
        ).properties(height=280)
        st.altair_chart(chart, use_container_width=True)

        trows = []
        for tk in fwd["eligible"]:
            e = pt[tk]
            yl = e["yearly"][-1]["annual_income"] if e["yearly"] else None
            row = {"Activo": tk, "Tipo": "YieldMax" if e["is_yieldmax"] else "ETF",
                  "Yield forward": f"{e['forward_yield']:.1f}%",
                  "Yield realizado": (f"{e['realized_yield']:.1f}%"
                                      if e.get("realized_yield") is not None else "—"),
                  "Valor hoy": _money(e["start_value"], 0), "Valor proyectado": _money(e["end_value"], 0),
                  "Ingreso anual final": _money(yl, 0) if yl is not None else "—",
                  "Dividendos netos acum.": _money(e["cumulative_dividends_net"], 0)}
            if p_country:
                row["Retención efectiva"] = f"{e.get('tax_effective_rate', 0):.1f}%"
            trows.append(row)
        st.dataframe(pd.DataFrame(trows), use_container_width=True, hide_index=True)
        st.caption("Yield forward = último pago anualizado (lo que anuncian). Yield "
                  "realizado = lo que de verdad cobraste en los últimos 12 meses. Cuando "
                  "el forward es mucho mayor, la cifra de marketing es optimista.")

        cad_changes = []
        for tk in fwd["eligible"]:
            cc = (resultados.get(tk) or {}).get("cadence_change")
            if isinstance(cc, dict) and cc.get("changed"):
                cad_changes.append(f"**{tk}**: {cc['old_label']} → {cc['recent_label']}")
        if cad_changes:
            st.caption("Cambio de frecuencia de pago detectado — " + " · ".join(cad_changes)
                      + ". El forward usa la frecuencia actual; el realizado (lo cobrado) no se afecta.")

        _carrera_yieldmax(resultados, fwd, p_hz)
        if p_country:
            _modulo_fiscal_nra(resultados, fwd, p_country)
        _monte_carlo(resultados, classify_map, proj_params)
        st.caption("Proyección educativa con supuestos tuyos — no es recomendación de compra o venta.")


def render_proyeccion(resultados: dict) -> None:
    st.markdown('<span class="vd-badge">Detalle</span>', unsafe_allow_html=True)
    st.markdown('<h2 class="vd-title">Proyección</h2>', unsafe_allow_html=True)
    if not resultados:
        st.markdown('<p class="vd-lede">Carga tu CSV de transacciones para ver esta vista.</p>',
                    unsafe_allow_html=True)
        return
    st.markdown(
        '<p class="vd-lede">Escenarios que tú controlas: cómo podría evolucionar tu '
        "portafolio y el rango de resultados posibles.</p>", unsafe_allow_html=True)
    classify_map = logic.classify_tickers(list(resultados.keys()))
    _concentracion_por_factor(resultados, classify_map)
    _proyeccion_escenario(resultados, classify_map)


# ── Fila 19 — El yield anunciado vs lo que de verdad ganas ──────────────────

def _yield_audit(resultados: dict, classify_map: dict) -> None:
    """Fila 19. Literal de `app_old.py:3652-3782` (`_render_yield_audit`): 3 pasos
    auditados (titular → mecanismo hoy → realizado) por fondo, con `st.pills` cuando
    está disponible. Reusa `logic.build_tax_summaries` una sola vez (Regla 3: mismo
    objeto fiscal por ticker, no se recalcula por segunda vez)."""
    # Antes se llamaba sin argumentos → 30% plano para todos. La residencia declarada por el
    # cliente tiene que llegar hasta aquí como a cualquier otra vista fiscal.
    _tasa, _pais = estado.tasa_y_pais()
    tax_summaries = logic.build_tax_summaries(resultados, base_rate_pct=_tasa, country=_pais)
    hoja = logic.build_hoja_excel(resultados, classify_map, tax_summaries=tax_summaries)
    rows = hoja.get("rows") or []
    if not rows:
        return
    aud_rows = {r["ticker"]: r for r in rows}

    def pct(x, d=1):
        return "—" if x is None else f"{x:.{d}f}%"

    st.markdown(
        '<p class="vd-her-subtitulo">🔍 ¿YieldMax paga lo que anuncia?</p>'
        '<p class="vd-her-nota">Tres formas de medir el mismo yield — recórrelas: cada '
        "paso es la misma pregunta, medida más honestamente. Reconstruido de tus pagos "
        "reales.</p>", unsafe_allow_html=True)

    tickers = list(aud_rows.keys())
    if hasattr(st, "pills") and len(tickers) > 1:
        au_tk = st.pills("Fondo a auditar", options=tickers, default=tickers[0],
                         selection_mode="single", key="vd_her_au_fondo")
    else:
        au_tk = tickers[0]
    au_tk = au_tk or tickers[0]
    ar = aud_rows[au_tk]
    a = ar["audit"]
    yoc = ar["yield_on_cost"]

    steps = ["1. Lo que anuncian", "2. Lo que su fórmula paga hoy", "3. Lo que de verdad rindió"]
    if hasattr(st, "pills"):
        sel = st.pills("Paso auditoría", options=steps, default=steps[0],
                       selection_mode="single", key=f"vd_her_au_paso_{au_tk}",
                       label_visibility="collapsed")
        i = steps.index(sel) if sel in steps else 0
    else:
        i = 2

    adv, fwd, rzd = a["advertised"], a["forward"], a["realized"]
    vcolor = {"match": "--cash", "ahead": "--warn", "behind": "--accent",
             "unknown": "--ink-mut"}.get(a["verdict"], "--ink-mut")

    if i == 0:
        big = pct(adv)
        if adv is not None:
            txt = (f"{au_tk} publica un yield **titular** de {pct(adv)}: «por cada \\$100 en "
                  f"{au_tk} hoy, te pagaría ~\\${adv:.0f} al año». Pero ese número anualiza "
                  "**un solo pago** — es marketing, no una promesa.")
        else:
            txt = (f"No tenemos la tasa titular publicada de {au_tk} — sigue a los pasos 2 "
                  "y 3, que salen de tus pagos reales.")
    elif i == 1:
        big = pct(fwd)
        txt = (f"Si el **último pago real** se repitiera 12 meses, el mecanismo estaría "
              f"pagando {pct(fwd)} sobre el valor actual.")
        if fwd is not None and adv is not None:
            if fwd > adv * 1.1:
                txt += (" Va **por encima** del titular: hoy pagan más de lo que anuncian. "
                       "Suena bien… sigue al paso 3.")
            elif fwd < adv * 0.9:
                txt += " Va **por debajo** del titular: hoy su fórmula paga menos de lo que anuncian."
            else:
                txt += " Coincide con el titular: anuncian lo que su fórmula paga hoy."
    else:
        big = pct(rzd)
        txt = (f"En los últimos 12 meses {au_tk} pagó el equivalente a {pct(rzd)} de su "
              "valor actual. **Ojo: un número disparado aquí NO es buena señal** — se "
              "infla porque divides entre un NAV desplomado; es la erosión hablando. Sobre "
              f"**tu costo real** el rendimiento fue **{pct(yoc)}**.")
        ret = ar.get("total_return_pct")
        if ret is not None:
            txt += (f" Y aun así tu retorno total es **{pct(ret)}** — la cifra honesta "
                   "siempre es el retorno total de la tabla de arriba, no el yield.")

    st.markdown(f'<p style="font-family:var(--font-mono);font-size:30px;font-weight:800;'
               f'color:var(--ink);margin:4px 0;">{big}</p>', unsafe_allow_html=True)
    st.markdown(txt)

    vals = [(adv, "Titular"), (fwd, "Mecanismo hoy"), (rzd, "Realizado s/ valor")]
    cols = st.columns(3)
    for idx, (v, label) in enumerate(vals):
        with cols[idx]:
            on = idx <= i and v is not None
            nums = [x for x, _ in vals if x is not None]
            vmax = max(nums) if nums else 1
            st.progress(min(1.0, max(0.0, (v or 0) / vmax)) if on else 0.0)
            st.caption(f"{label} · {pct(v)}" if on else f"{label} · —")
    if i == 2:
        st.markdown(f'<span style="display:inline-block;border:1px solid var({vcolor});'
                   f'color:var({vcolor});font-size:10px;font-weight:600;letter-spacing:'
                   f'0.05em;padding:2px 8px;margin-top:6px;text-transform:uppercase;">'
                   f'{a["label"]}</span>', unsafe_allow_html=True)

    if len(tickers) > 1:
        import pandas as pd

        with st.expander("Ver la tabla completa (todos los fondos)"):
            tabla = pd.DataFrame([{
                "Fondo": r["ticker"], "Titular": pct(r["audit"]["advertised"]),
                "Mecanismo hoy": pct(r["audit"]["forward"]), "Realizado (s/ valor)": pct(r["audit"]["realized"]),
                "Rend. s/ tu costo": pct(r["yield_on_cost"]), "Veredicto": r["audit"]["label"],
            } for r in aud_rows.values()])
            st.dataframe(tabla, hide_index=True, use_container_width=True)
            st.caption('Cómo leerlo: si «titular ≈ mecanismo», anuncian lo que su fórmula '
                      'paga. Fíjate en «Rend. s/ tu costo»: si se acerca al titular, el '
                      "fondo sí paga ~lo prometido respecto a tu principal — lo que te "
                      "empobrece es la caída del NAV, no que paguen poco.")


# ── Fila 20 — Comparativa de estrategias ────────────────────────────────────

_ESTR_ETF_MAP = {"SCHB": "Todo en SCHB", "XLK": "Todo en XLK", "YMAX": "Todo en YMAX", "SMH": "Todo en SMH"}
_ESTR_MONO = "'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace"


def _estr_nra_rate() -> float:
    """Retención aplicada a las distribuciones del ETF alternativo al reinvertirlas.

    Sale de la residencia declarada por el cliente. Antes era `0.0` fijo, lo que hacía la
    comparación asimétrica: el portafolio real cargaba la retención observada de su CSV
    mientras el benchmark reinvertía dividendos íntegros — una ventaja que el cliente no
    tendría en la vida real, justo en la vista que existe para responder "¿me habría ido
    mejor en un solo ETF?".

    Sin residencia declarada sigue en 0.0 (bruto) y la vista lo ROTULA como tal: es el único
    sitio donde «sin declarar» colapsa a cero, porque el motor necesita un número para
    simular. Ver `ui.estado.tasa_para_motor`.
    """
    return estado.tasa_para_motor()


def _serie_temporal_estrategias(resultados: dict, sr_invested: float) -> dict:
    """Reconstruye la serie temporal Portafolio Real vs «todo en un solo ETF».
    Cacheada en sesión por `_file_id` (evita repetir el trabajo en cada rerun del rail).

    Portado de `app_old.py:5682-5794`, con un cambio de FUENTE y de MOTOR: antes llamaba
    `yf.download(..., auto_adjust=True)` en cada render —la única vista de la app que seguía
    bajando de la red en runtime— y derivaba el valor como `acciones × precio ajustado`.
    Ahora lee de `price_cache.load_history` (caché primero, vivo sólo si falta o venció) y
    delega la simulación a `backtest.run_backtest`, el motor event-driven ya reconciliado
    contra el extracto real de IB.

    **Por qué no basta cambiar la fuente.** `auto_adjust=True` mete el dividendo dentro del
    precio, así que la serie vieja medía RETORNO TOTAL. El caché guarda `auto_adjust=False`
    a propósito (`Close` crudo + `Dividends` aparte) para que el DRIP no se cuente dos veces.
    Sustituir una serie por la otra sin reinvertir las distribuciones convierte el benchmark
    en sólo-precio: medido sobre 3 tranches de $5k, YMAX caía de $16,741 a $7,102 (−58%) y
    los ETF amplios ~1-2%. Vía motor la equivalencia se mantiene dentro del 0.5%."""
    import pandas as pd

    import backtest
    import price_cache

    # La tasa entra en la clave: si no, cambiar de residencia dejaría la serie cacheada de
    # la tasa anterior y la gráfica contradiría al resto de la app en silencio.
    ts_key = (f"vd_her_strat_ts_{st.session_state.get('_file_id', 'x')}"
              f"_{_estr_nra_rate():.4f}")
    if ts_key in st.session_state:
        return st.session_state[ts_key]

    flow_by_date: dict = {}
    for _t, s in resultados.items():
        if "error" in s or "daily_trend" not in s:
            continue
        ic = s["daily_trend"].get("Invested Capital")
        if ic is None or len(ic) == 0:
            continue
        inc = ic.diff()
        if len(inc) > 0:
            inc.iloc[0] = ic.iloc[0]
        for d, amt in inc[inc > 0].items():
            key = pd.Timestamp(d).normalize()
            flow_by_date[key] = flow_by_date.get(key, 0.0) + float(amt)
    buy_flows = sorted(flow_by_date.items(), key=lambda x: x[0])

    if not buy_flows:
        for _t, s in resultados.items():
            if "error" not in s and "history" in s:
                h = s["history"]
                buys = h[h["Action"].str.lower().str.contains("buy", na=False)]
                for _, row in buys.iterrows():
                    try:
                        buy_flows.append((pd.to_datetime(row["Date"]).normalize(), abs(float(row["Amount"]))))
                    except Exception:
                        pass
        buy_flows.sort(key=lambda x: x[0])

    if not buy_flows and sr_invested > 0:
        earliest = None
        for _t, s in resultados.items():
            if "error" not in s and "daily_trend" in s and len(s["daily_trend"]) > 0:
                d0 = pd.Timestamp(s["daily_trend"].index[0]).normalize()
                earliest = d0 if earliest is None else min(earliest, d0)
        if earliest is not None:
            buy_flows = [(earliest, sr_invested)]

    flow_total = sum(a for _, a in buy_flows)
    if flow_total > 0 and sr_invested > 0:
        scale = sr_invested / flow_total
        buy_flows = [(d, a * scale) for d, a in buy_flows]

    frames_ts = []
    etf_final_vals: dict = {}

    real_ts = None
    for _t, s in resultados.items():
        if "error" not in s and "daily_trend" in s:
            col = s["daily_trend"]["User Total Value"]
            real_ts = col.copy() if real_ts is None else real_ts.add(col, fill_value=0)
    if real_ts is not None:
        r_df = real_ts.reset_index()
        r_df.columns = ["Fecha", "Valor"]
        r_df["Estrategia"] = "Tu Portafolio Real"
        frames_ts.append(r_df)

    nra_rate = _estr_nra_rate()

    if buy_flows:
        ts_start = buy_flows[0][0] - pd.Timedelta(days=10)
        ts_end = pd.Timestamp.today()
        for etf_tk, etf_lbl in _ESTR_ETF_MAP.items():
            try:
                hr = price_cache.load_history(etf_tk, start=ts_start, end=ts_end)
                hist = hr.history
                if hist is None or hist.empty:
                    continue
                # Un tranche por compra: cada uno es independiente y el valor total es su
                # suma (linealidad), igual que el calculo anterior. `run_backtest` recorre el
                # calendario real y reinvierte cada distribucion NETA de `nra_rate` al cierre
                # del propio dia ex-div.
                port_val = None
                for bd, amt in buy_flows:
                    if float(amt) <= 0:
                        continue
                    bd_norm = pd.Timestamp(bd).normalize()
                    if bd_norm > hist.index.max():
                        continue
                    r = backtest.run_backtest(
                        etf_tk, start_date=bd_norm, initial_capital=float(amt),
                        drip=True, nra_rate=nra_rate, end_date=ts_end, history=hist)
                    serie = r.daily["total_value"]
                    port_val = serie if port_val is None else port_val.add(serie, fill_value=0.0)
                if port_val is None:
                    continue
                vals = port_val[port_val > 0]
                if vals.empty:
                    continue
                etf_final_vals[etf_lbl] = float(vals.iloc[-1])
                e_df = vals.reset_index()
                e_df.columns = ["Fecha", "Valor"]
                e_df["Estrategia"] = etf_lbl
                frames_ts.append(e_df)
            except Exception:
                pass

    resultado = {"df": pd.concat(frames_ts, ignore_index=True) if frames_ts else pd.DataFrame(),
                "etf_final": etf_final_vals}
    st.session_state[ts_key] = resultado
    return resultado


def _comparativa_estrategias(resultados: dict) -> None:
    """Fila 20 — «Tu portafolio real vs. poner ese mismo dinero, mismas fechas, en un
    solo ETF». Literal de `app_old.py:5665-5908`. El gate original (`_strat_results`,
    salida de `logic.simulate_triple_comparison`) solo se usaba como booleano — nunca
    se consumía su contenido en esta sección — así que aquí se reemplaza por «hay
    resultados válidos»: evita recalcular una comparación triple que esta vista no lee."""
    if not resultados:
        return
    sr_invested = sum(s.get("pocket_investment", 0) for s in resultados.values() if "error" not in s)
    sr_value = sum(s.get("market_value", 0) for s in resultados.values() if "error" not in s)
    if sr_invested <= 0:
        return
    sr_ret_pct = (sr_value - sr_invested) / sr_invested * 100

    _seccion("Comparativa de estrategias",
             "Tu portafolio completo vs. poner ese mismo dinero, en las mismas fechas, "
             "todo en un solo ETF")
    st.markdown(
        f'<p class="vd-her-nota">Tomamos el <b>mismo dinero</b> que aportaste '
        f"(<b>{_money(sr_invested, 0)}</b> en total) en las <b>mismas fechas</b>, y lo "
        "invertimos 100% en cada ETF. La línea oscura es <b>tu portafolio real "
        "completo</b> — dividendos + crecimiento juntos; las demás responden: “¿y si ese "
        "mismo dinero hubiera ido todo a un solo fondo?”. Mismo capital, mismo timing: "
        "solo cambia el destino.</p>", unsafe_allow_html=True)

    import altair as alt
    import pandas as pd

    with st.spinner("Descargando precios históricos (yfinance)…"):
        ts_cache = _serie_temporal_estrategias(resultados, sr_invested)
    line_data = ts_cache["df"]
    etf_finals = ts_cache.get("etf_final", {})

    all_strats = {"real": {"label": "Tu Portafolio Real", "total_invested": sr_invested,
                           "final_value": sr_value, "return_pct": sr_ret_pct, "ok": True}}
    for etf_lbl in _ESTR_ETF_MAP.values():
        if etf_lbl in etf_finals:
            fv = etf_finals[etf_lbl]
            rp = (fv - sr_invested) / sr_invested * 100 if sr_invested > 0 else 0
            all_strats[etf_lbl] = {"label": etf_lbl, "total_invested": sr_invested,
                                   "final_value": fv, "return_pct": rp, "ok": True}
        else:
            all_strats[etf_lbl] = {"label": etf_lbl, "total_invested": sr_invested,
                                   "final_value": None, "return_pct": None, "ok": False}
    sorted_strats = sorted(all_strats.items(),
                           key=lambda x: (0, -x[1]["return_pct"]) if x[1]["ok"] else (1, 0.0))
    color_domain = ["Tu Portafolio Real", "Todo en SCHB", "Todo en XLK", "Todo en YMAX", "Todo en SMH"]
    color_range = ["#021C36", "#006497", "#2e7d5d", "#c8102e", "#e67e22"]
    short = {"Tu Portafolio Real": "TU PORTAFOLIO", "Todo en SCHB": "SCHB", "Todo en XLK": "XLK",
            "Todo en YMAX": "YMAX", "Todo en SMH": "SMH"}
    cmap = dict(zip(color_domain, color_range))

    tabla = pd.DataFrame([{
        "Estrategia": short.get(v["label"], v["label"]),
        "Valor hoy": _money(v["final_value"], 0) if v["ok"] else "—",
        "Retorno": f"{v['return_pct']:+.2f}%" if v["ok"] else "sin datos",
    } for _, v in sorted_strats])
    st.dataframe(tabla, hide_index=True, use_container_width=True)

    missing_etfs = [v["label"].replace("Todo en ", "") for _, v in sorted_strats if not v["ok"]]
    if missing_etfs:
        st.caption(f"No se pudieron descargar precios de: {', '.join(missing_etfs)} "
                  "(yfinance). Vuelve a intentar en unos segundos.")

    if not line_data.empty:
        line_data = line_data.copy()
        line_data["Fecha"] = pd.to_datetime(line_data["Fecha"])
        color = alt.Color("Estrategia:N", scale=alt.Scale(domain=color_domain, range=color_range), legend=None)
        tip = [alt.Tooltip("Fecha:T", title="Fecha", format="%d %b %Y"),
              alt.Tooltip("Estrategia:N", title="Estrategia"),
              alt.Tooltip("Valor:Q", title="Valor", format="$,.0f")]
        bench = line_data[line_data["Estrategia"] != "Tu Portafolio Real"]
        real = line_data[line_data["Estrategia"] == "Tu Portafolio Real"]
        l_bench = alt.Chart(bench).mark_line(strokeWidth=1.5, opacity=0.6).encode(
            x="Fecha:T", y=alt.Y("Valor:Q", axis=alt.Axis(format="$,.0f")), color=color, tooltip=tip)
        l_real = alt.Chart(real).mark_line(strokeWidth=3, opacity=1.0).encode(
            x="Fecha:T", y=alt.Y("Valor:Q", axis=alt.Axis(format="$,.0f")), color=color, tooltip=tip)
        chart = (l_bench + l_real).properties(height=440)
        st.altair_chart(chart, use_container_width=True)


def render_estrategias(resultados: dict) -> None:
    st.markdown('<span class="vd-badge">Detalle</span>', unsafe_allow_html=True)
    st.markdown('<h2 class="vd-title">Estrategias</h2>', unsafe_allow_html=True)
    if not resultados:
        st.markdown('<p class="vd-lede">Carga tu CSV de transacciones para ver esta vista.</p>',
                    unsafe_allow_html=True)
        return
    from ui.adapters import _tiene_datos

    classify_map = logic.classify_tickers(list(resultados.keys()))
    mode_a = sorted(t for t, m in classify_map.items()
                     if m == "mode_a" and _tiene_datos(resultados.get(t)))
    if mode_a:
        _seccion("El yield anunciado vs lo que de verdad ganas",
                 "Un fondo puede anunciar '80% de yield' y aun así hacerte perder "
                 "dinero. El truco: el yield anualiza un solo pago de un flujo que "
                 "salta cada semana, y no descuenta la caída del precio.")
        _yield_audit(resultados, classify_map)
    _comparativa_estrategias(resultados)


# ── Despacho ─────────────────────────────────────────────────────────────────

def render_vista(vista: str, ruta) -> None:
    """Despacho de las 4 vistas de Detalle — las 4 con datos reales desde la Fase 5c."""
    from ui.chrome import render_placeholder
    from ui.vistas import obtener_resultados

    resultados = obtener_resultados()
    if vista == "portafolios":
        render_portafolios(resultados)
    elif vista == "ingresos":
        render_ingresos(resultados)
    elif vista == "proyeccion":
        render_proyeccion(resultados)
    elif vista == "estrategias":
        render_estrategias(resultados)
    else:
        render_placeholder(ruta)


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
