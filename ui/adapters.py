"""Traduce lo que calcula `logic.py` al JSON que consumen los componentes HTML.

Esta capa **no calcula nada fiscal**: lee y reordena. Toda cifra de impuesto sale del
objeto `tax_summary` que ya construyó `analyze_portfolio` (Regla 3 del contrato
ROC/NRA: objeto fiscal único, se renderiza, no se recalcula).

El mapa cifra→campo está en `specs/port-artifact/mapa-datos.md` § 1, verificado corriendo
`analyze_portfolio` sobre los fixtures.
"""

from __future__ import annotations

import datetime

import logic

# Universo del Total Return Graph — 5 fondos YieldMax + 3 ETFs de crecimiento. Paleta y
# agrupación literales del demo (`viaje-dinero-waterfall.html:2781`). Viven aquí (no en
# `ui/vistas.py`, que las tenía antes bajo `_TRG_*`) porque las consume `trg_real_data`;
# `ui.vistas` ya importa de `ui.adapters`, así que dejarlas en vistas.py habría creado
# un import circular en cuanto el adapter necesitara leerlas.
TRG_YM = ("NVDY", "TSLY", "CONY", "MSTY", "CHPY")
TRG_GROWTH = ("SCHB", "XLK", "SMH")
TRG_UNIVERSO = TRG_YM + TRG_GROWTH
TRG_COLORES = {"NVDY": "#1f86c4", "TSLY": "#d1662f", "CONY": "#b95cae", "MSTY": "#a8b020",
              "CHPY": "#17a89a", "SCHB": "#b06a3d", "XLK": "#8f76d4", "SMH": "#c99a26"}
TRG_MODOS = ("bruto", "roc", "plano")


# Etiquetas del rail — literales del demo (`viaje-dinero-waterfall.html:2131`).
STEP_LABELS = (
    "Bolsillo", "Div. bruto", "Imp. NRA", "Reinv + Efvo",
    "Bols + DRIP", "Mercado", "Cap. actual", "Resultado",
)


class DatosIncompletos(ValueError):
    """El ticker no tiene lo mínimo para dibujar el recorrido."""


def _f(valor, defecto: float = 0.0) -> float:
    """Convierte a float tolerando None — `analyze_portfolio` deja campos vacíos cuando
    yfinance no responde, y ahí es mejor un cero explícito que un TypeError."""
    if valor is None:
        return defecto
    try:
        return float(valor)
    except (TypeError, ValueError):
        return defecto


def cashflow_data(stats: dict, ticker: str) -> dict:
    """Las 12 constantes del Cash flow, más lo que el componente necesita para rotular.

    Equivale al bloque `viaje-dinero-waterfall.html:2124-2127`, pero con datos del CSV.
    """
    if not stats or stats.get("skipped"):
        raise DatosIncompletos(f"{ticker}: sin datos analizables")

    pocket = _f(stats.get("pocket_investment"))
    neto = _f(stats.get("total_dividends"))
    drip = _f(stats.get("dividends_collected_drip"))
    cash = _f(stats.get("dividends_collected_cash"))
    valor_hoy = _f(stats.get("market_value"))

    # Regla 3: la retención sale del objeto fiscal único, no de una resta propia.
    # `withheld_tax_total` está en stats y coincide, pero la fuente canónica es
    # `tax_summary` — si algún día divergen, manda el objeto.
    tax = stats.get("tax_summary") or {}
    impuesto = _f(tax.get("withheld_real"), _f(stats.get("withheld_tax_total")))

    # No existe `dividends_gross` en stats (sí en el dict de fila de build_hoja_excel,
    # otro namespace). El bruto se reconstruye: lo que llegó + lo que se retuvo.
    bruto = neto + impuesto

    total_trabajando = pocket + drip
    mercado = valor_hoy - total_trabajando
    capital_actual = valor_hoy + cash
    resultado = capital_actual - pocket

    # El pico escala el mosaico: la mayor suma de categorías que se llega a mostrar en
    # cualquier paso. Sin esto, un paso con varias categorías desborda el "100%" de otro.
    pico = max(pocket, bruto, total_trabajando, capital_actual, valor_hoy + cash)

    return {
        "ticker": ticker,
        "POCKET": round(pocket, 2),
        "BRUTO": round(bruto, 2),
        "IMPUESTO": round(impuesto, 2),
        "NETO": round(neto, 2),
        "DRIP": round(drip, 2),
        "CASH": round(cash, 2),
        "TOTAL_TRABAJANDO": round(total_trabajando, 2),
        "MERCADO": round(mercado, 2),
        "VALOR_HOY": round(valor_hoy, 2),
        "CAPITAL_ACTUAL": round(capital_actual, 2),
        "RESULTADO": round(resultado, 2),
        "PICO": round(pico, 2),
        "STEP_LABELS": list(STEP_LABELS),
        # Regla 2: cada cifra fiscal declara su base y su momento. El componente los
        # rotula; sin esto no puede distinguir la retención al cobro de la devolución
        # estimada tras la reclasificación anual.
        "impuesto_base": tax.get("basis", "gross_withheld"),
        "impuesto_momento": "al cobro",
        "devolucion_estimada": round(_f(tax.get("refund_estimated")), 2),
        "devolucion_es_estimacion": bool(tax.get("is_estimate", True)),
        "devolucion_momento": tax.get("moment", "annual_reclass_estimate"),
    }


def hoja_data(stats: dict, ticker: str, df) -> dict:
    """Las 12 constantes del Cash flow más `INICIO`/`TICKER`, para la Hoja Excel.

    Equivale al bloque `viaje-dinero-waterfall.html:3000-3006` (`initHoja`), que no
    introduce datos nuevos: deriva `TOTALINV`/`APARENTE` de las mismas 12 constantes
    del Cash flow (mapa-datos.md § 2). `INICIO` es la fecha de la primera transacción
    del ticker en el CSV — el mismo criterio que usa `logic.py:687`
    (`ticker_df['Date'].min()`), no persistido en `stats`, así que se recalcula aquí
    leyendo el mismo `df` que ya validó la carga.
    """
    datos = cashflow_data(stats, ticker)
    primera = df.loc[df["Ticker"] == ticker, "Date"].min()
    datos["INICIO"] = "" if primera is None or primera != primera else primera.strftime("%Y-%m-%d")
    datos["TICKER"] = ticker
    return datos


def salud_nav_data(ticker: str, stats: dict) -> dict:
    """El veredicto de `logic.classify_roc_health` más el contexto numérico que lo
    explica — no hay diseño que extraer del demo (`panel-salud` es un placeholder,
    mapa-datos.md § 3), así que esta vista es nueva en el port.

    Regla 4: la destructividad se mide con la TENDENCIA del NAV, nunca con el ROC% —
    `classify_roc_health` ya respeta esto internamente; esta función solo junta sus
    parámetros, con la misma fórmula que `app_old.py:3590-3611` (verificada, en producción).
    """
    roc_pct = logic._roc_pct_for(ticker, stats)
    nav_cagr = stats.get("price_cagr_recent")
    if nav_cagr is None:
        nav_cagr = stats.get("price_cagr")
    pocket = stats.get("pocket_investment")
    tr_pct = None
    if pocket:
        valor_hoy = stats.get("market_value") or 0
        cash = stats.get("dividends_collected_cash") or 0
        tr_pct = (valor_hoy + cash - pocket) / pocket * 100

    asof_days = None
    r19a = logic.load_roc_19a().get(str(ticker).upper())
    if r19a and r19a.get("asof"):
        try:
            asof_days = (datetime.date.today()
                        - datetime.date.fromisoformat(r19a["asof"])).days
        except (ValueError, TypeError):
            asof_days = None

    prev_verdict = logic.latest_health_verdict(ticker)
    veredicto = logic.classify_roc_health(
        roc_pct=roc_pct, price_cagr=nav_cagr, total_return_pct=tr_pct,
        history_days=stats.get("price_history_days"), roc_asof_days=asof_days,
        prev_verdict=prev_verdict, underlying_cagr=stats.get("underlying_cagr_recent"))

    return {
        "ticker": ticker,
        "verdict": veredicto["verdict"],
        "label": veredicto["label"],
        "color": veredicto["color"],
        "reason": veredicto["reason"],
        "headline": veredicto["headline"],
        "plain": veredicto["plain"],
        "gauge_score": veredicto["gauge_score"],
        "nav_cagr": nav_cagr,
        "roc_pct": roc_pct,
        "total_return_pct": tr_pct,
    }


def verificar_identidades(datos: dict, tolerancia: float = 0.02) -> list:
    """Comprueba las identidades contables del recorrido. Devuelve la lista de fallos.

    No es decorativo: son las relaciones que el waterfall dibuja. Si no se cumplen, las
    barras mienten aunque cada cifra por separado sea correcta.
    """
    fallos = []

    def check(nombre, izquierda, derecha):
        if abs(izquierda - derecha) > tolerancia:
            fallos.append(f"{nombre}: {izquierda:.2f} ≠ {derecha:.2f}")

    check("bruto = neto + impuesto",
          datos["BRUTO"], datos["NETO"] + datos["IMPUESTO"])
    check("neto = reinvertido + efectivo",
          datos["NETO"], datos["DRIP"] + datos["CASH"])
    check("capital trabajando = bolsillo + reinvertido",
          datos["TOTAL_TRABAJANDO"], datos["POCKET"] + datos["DRIP"])
    check("impacto de mercado = valor hoy − capital trabajando",
          datos["MERCADO"], datos["VALOR_HOY"] - datos["TOTAL_TRABAJANDO"])
    check("capital actual = valor hoy + efectivo",
          datos["CAPITAL_ACTUAL"], datos["VALOR_HOY"] + datos["CASH"])
    check("resultado = capital actual − bolsillo",
          datos["RESULTADO"], datos["CAPITAL_ACTUAL"] - datos["POCKET"])

    # Regla 1: el capital aportado es invariante. No puede depender de ninguna cifra
    # fiscal — si el bolsillo se moviera al aplicar ROC, esta comprobación no lo vería,
    # pero sí detecta el caso burdo de haberlo mezclado con el impuesto.
    if datos["POCKET"] < 0:
        fallos.append(f"bolsillo negativo: {datos['POCKET']:.2f}")

    return fallos


def _trg_ancla():
    """El YM de `TRG_YM` con la incepción más antigua — decisión 4 del traspaso
    2026-08-10: el ancla NO se hardcodea (hoy es TSLY; mañana puede entrar otro
    fondo). Ignora los que fallen. Devuelve (ticker, Timestamp) o (None, None) si
    ninguno de los 5 respondió.
    """
    mejor_tk, mejor_start = None, None
    for tk in TRG_YM:
        try:
            data, _ = logic.fetch_market_data(tk, "2000-01-01")
        except Exception:
            continue
        if data is None or data.empty or "Close" not in data.columns:
            continue
        start = data.sort_index().index.min()
        if mejor_start is None or start < mejor_start:
            mejor_tk, mejor_start = tk, start
    return mejor_tk, mejor_start


def trg_real_data(resultados: dict, tasa_pct: float, pais: str | None = None) -> dict | None:
    """JSON para `ui/componentes/comparacion_real.html` (Total Return Graph · datos
    reales): el índice TRI crudo de los 8 tickers del universo × 3 modos fiscales
    sobre la ventana completa (mapa-datos.md § 5).

    El componente no calcula nada — Python entrega el índice base 100 (normalizado en
    la incepción de cada ticker, o en la del ancla si es posterior) y JS renormaliza
    al fondo base que el usuario elija dentro del iframe, sin rerun (decisión 3 del
    traspaso 2026-08-10: arquitectura Exhibit 2 del paper Morningstar TRI). Por eso
    basta con UNA llamada a `build_drip_comparison_series` por modo, siempre anclada
    al YM más antiguo — no una por cada posible selección de fondo base.

    Devuelve `None` si el ancla (el YM de incepción más antigua) no descarga; para
    cualquier otro ticker, si falla simplemente no aparece en `idx`/`incep`/`col` — el
    componente omite su chip, no inventa una serie.

    **Límite conocido del eje mensual (auditoría 2026-08-10).** Dentro del mes en que
    arranca el fondo base, el base y sus comparadores NO se anclan en el mismo
    instante: el base entra por su primer dato real (la excepción de `mensual.iloc[0]`
    de abajo) y los comparadores, que ya existían, por el cierre de fin de ese mes.
    Son hasta ~3 semanas de desfase en un solo punto, el de normalización. Medido con
    base MSTY (incepción 22-feb-2024): el componente da SMH +173% donde el cálculo
    diario da +176%; MSTY +23% contra +24%. Es la contrapartida declarada de portar el
    eje mensual del demo (decisión 5 del traspaso) y afecta solo a la comparación
    visual, nunca a una cifra fiscal. Si algún día hace falta paridad exacta con el
    cálculo diario, la vía es interpolar el valor de cada comparador en la fecha real
    de incepción del base, no volver a serie diaria (multiplicaría el JSON por ~20).
    """
    ancla, ancla_start = _trg_ancla()
    if ancla is None:
        return None

    origen = [int(ancla_start.year), int(ancla_start.month) - 1]
    comparar = tuple(t for t in TRG_UNIVERSO if t != ancla)

    idx: dict = {}
    meta_por_ticker: dict = {}
    last = 0

    for modo in TRG_MODOS:
        df, meta = logic.build_drip_comparison_series(
            ancla, comparar, mode=modo, base_rate=tasa_pct / 100.0)
        if df.empty or ancla not in meta:
            return None
        idx[modo] = {}
        for tk, grupo in df.groupby("Ticker"):
            # Remuestreo mensual (decisión 5): el último cierre de cada mes; el punto
            # final es el último dato real aunque el mes esté a medias — `.last()`
            # sobre un bin parcial ya toma el último punto observado, sin rellenar.
            serie = grupo.set_index("Fecha")["Valor"].sort_index()
            mensual = serie.resample("ME").last().dropna()
            # Excepción al "último del mes": el PRIMER mes de cada ticker también es
            # casi siempre parcial (la incepción real rara vez cae el día 1), y
            # `.resample().last()` ahí devolvería el cierre de FIN de ese mes — no el
            # valor real de arranque. `build_total_return_series` normaliza cada
            # serie a exactamente 100 en su primer dato (`serie.iloc[0]`); si ese
            # ancla se corre unas semanas, la renormalización de JS a "0% en la
            # incepción" queda sesgada por lo que el precio ya se movió mientras
            # tanto — medido en vivo: MSTY (incep 22-feb, fondo volátil en sus
            # primeras semanas) daba +5% de retorno final en vez de +24% con este
            # bug. El resto de los meses SÍ debe ser el cierre de fin de mes. Si el
            # ticker vive entero dentro de un solo mes (ventana muy corta desde su
            # incepción), esto pisa también el "último dato real" de ese único bin —
            # inocuo: `series()` en JS divide ese valor entre sí mismo cuando ese
            # ticker es el fondo base (siempre 0%), y con la ventana real de 46 meses
            # ningún ticker vive en un solo mes.
            mensual.iloc[0] = serie.iloc[0]
            valores = {}
            for fecha, valor in mensual.items():
                m = (int(fecha.year) - origen[0]) * 12 + (int(fecha.month) - 1 - origen[1])
                valores[str(m)] = round(float(valor), 4)
                if m > last:
                    last = m
            idx[modo][tk] = valores
        meta_por_ticker.update(meta)

    incep = {}
    grp = {}
    for tk, m in meta_por_ticker.items():
        start = m["start"]
        incep[tk] = ((int(start.year) - origen[0]) * 12
                     + (int(start.month) - 1 - origen[1]))
        grp[tk] = "ym" if tk in TRG_YM else "growth"

    classify_map = logic.classify_tickers(list(resultados.keys()))
    poseidos = [t for t, m in classify_map.items() if m == "mode_a" and t in TRG_YM]
    base_defecto = (max(poseidos, key=lambda t: (resultados.get(t) or {}).get("market_value") or 0)
                    if poseidos else ancla)

    return {
        "origen": origen,
        "last": last,
        "base_defecto": base_defecto,
        "tasa_pct": tasa_pct,
        "pais": pais,
        "asof": datetime.date.today().isoformat(),
        "incep": incep,
        "grp": grp,
        "col": {tk: TRG_COLORES[tk] for tk in meta_por_ticker if tk in TRG_COLORES},
        "idx": idx,
    }
