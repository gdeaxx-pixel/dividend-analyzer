"""Traduce lo que calcula `logic.py` al JSON que consumen los componentes HTML.

Esta capa **no calcula nada fiscal**: lee y reordena. Toda cifra de impuesto sale del
objeto `tax_summary` que ya construyó `analyze_portfolio` (Regla 3 del contrato
ROC/NRA: objeto fiscal único, se renderiza, no se recalcula).

El mapa cifra→campo está en `specs/port-artifact/mapa-datos.md` § 1, verificado corriendo
`analyze_portfolio` sobre los fixtures.
"""

from __future__ import annotations

import datetime

import backtest
import logic
import price_cache

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


def _bruto_independiente_del_csv(history_df) -> float:
    """Recalcula el dividendo BRUTO desde cero, releyendo el historial fila por fila —
    para el guard de `verificar_identidades`, que necesita una fuente que NO pase por
    `_dividend_tax_netted`/`dividend_base_convention`.

    Auditoría al PR B (objeto fiscal único): la versión anterior de este guard leía
    `stats['dividend_base_convention']` para decidir si comparar contra NETO o BRUTO. Esa
    convención la calcula la MISMA función que el guard debería estar auditando
    (`logic._dividend_tax_netted`) — si esa detección se rompe, `dividend_base_convention`
    se rompe con ella y el guard compara el lado equivocado, cuadrando por casualidad.
    Comprobado: forzando `_dividend_tax_netted` a devolver siempre `True`, `BRUTO` vuelve a
    mostrar $600.60 en vez de $462.00 (el bug que arregló el PR B) y el guard viejo no lo
    veía.

    Este helper no depende de la convención: suma toda fila 'dividend'/'dividendo' EXCLUYENDO
    las de impuesto (nra tax/tax adj/withholding/foreign tax/retención/retencion) y las de
    compra DRIP ('Reinvest Shares', monto neto post-impuesto, no un cobro). CON SIGNO — hay
    reversos/correcciones negativas en el CSV real, `abs()` los convertiría en más dividendo.
    Verificado contra ground truth: Schwab MSTY $462.00, IB MSTY $7,224.59 (el bruto real en
    ambas convenciones, sin pasar por la detección que se está auditando).
    """
    if history_df is None or len(history_df) == 0 or 'Action' not in history_df.columns:
        return 0.0
    total = 0.0
    for _, row in history_df.iterrows():
        action = str(row.get('Action', '')).lower()
        if 'dividend' not in action and 'dividendo' not in action:
            continue
        is_tax = ('nra tax' in action or 'tax adj' in action or 'withholding' in action
                  or 'foreign tax' in action or 'retención' in action or 'retencion' in action)
        if is_tax:
            continue
        is_drip = 'reinvest' in action or 'reinversión' in action or 'drip' in action
        if is_drip and ('share' in action or 'acciones' in action):
            continue
        amount = logic._clean_money(row.get('Amount', 0))
        if amount != amount:  # NaN
            continue
        total += float(amount)
    return round(total, 2)


def _f(valor, defecto: float = 0.0) -> float:
    """Convierte a float tolerando None — `analyze_portfolio` deja campos vacíos cuando
    yfinance no responde, y ahí es mejor un cero explícito que un TypeError."""
    if valor is None:
        return defecto
    try:
        return float(valor)
    except (TypeError, ValueError):
        return defecto


def _tiene_datos(stats) -> bool:
    """Un ticker es utilizable si `analyze_portfolio` lo analizó de verdad.

    `classify_tickers` clasifica por IDENTIDAD del instrumento (SMH es un ETF de
    crecimiento pase lo que pase) y `analyze_portfolio` por CALIDAD DE LOS DATOS
    (una posición de menos de 14 días se descarta y solo deja
    `{"skipped": True, "reason": …}`). Las dos son correctas por separado; lo que
    no puede pasar es armar la lista con la primera y leer los números de la
    segunda — de ahí el `KeyError: 'pocket_investment'` de esta vista.

    Vive aquí (no en `ui/heredadas.py`) porque `trg_real_data` también lo necesita
    y `ui.heredadas` ya importa de `ui.adapters` — el helper no puede vivir en
    heredadas sin crear un import circular.
    """
    return isinstance(stats, dict) and "error" not in stats and not stats.get("skipped")


def cashflow_data(stats: dict, ticker: str) -> dict:
    """Las 12 constantes del Cash flow, más lo que el componente necesita para rotular.

    Equivale al bloque `viaje-dinero-waterfall.html:2124-2127`, pero con datos del CSV.
    """
    if not stats or stats.get("skipped"):
        raise DatosIncompletos(f"{ticker}: sin datos analizables")

    pocket = _f(stats.get("pocket_investment"))
    drip = _f(stats.get("dividends_collected_drip"))
    valor_hoy = _f(stats.get("market_value"))

    # Regla 3: la retención sale del objeto fiscal único, no de una resta propia.
    # `withheld_tax_total` está en stats y coincide, pero la fuente canónica es
    # `tax_summary` — si algún día divergen, manda el objeto.
    tax = stats.get("tax_summary") or {}
    impuesto = _f(tax.get("withheld_real"), _f(stats.get("withheld_tax_total")))

    # Objeto fiscal único (`logic.build_dividend_tax_totals`, corrido dentro de
    # `analyze_portfolio`): bruto/neto NO se reconstruyen aquí sumando/restando el impuesto a
    # `total_dividends` — ese campo mezcla bases distintas según el broker (para Schwab sin
    # DRIP YA es el bruto; sumarle la retención de nuevo la duplica). `dividends_gross_total`/
    # `dividends_net_total` declaran su propia procedencia en `dividend_base_convention`.
    _gross_total = stats.get("dividends_gross_total")
    _net_total = stats.get("dividends_net_total")
    if _gross_total is None or _net_total is None:
        # Legado: stats sin el objeto fiscal único (fixture armado a mano, no vía
        # analyze_portfolio). Degrada al supuesto anterior — incorrecto para Schwab, pero
        # es la mejor aproximación disponible sin el CSV.
        neto = _f(stats.get("total_dividends"))
        bruto = neto + impuesto
        cash = _f(stats.get("dividends_collected_cash"))
    else:
        bruto = _f(_gross_total)
        neto = _f(_net_total)
        # `dividends_collected_cash` puede venir en base BRUTA (Schwab, retención en fila
        # aparte) — usarlo tal cual aquí inflaría CAPITAL_ACTUAL/RESULTADO con dinero que en
        # realidad se fue en impuesto. El efectivo que de verdad quedó líquido es el residuo
        # del neto ya declarado una vez descontado lo reinvertido (`drip`, que siempre es
        # neto: el DRIP se compra con el monto post-retención) — no se reconstruye sumando,
        # se deriva del objeto fiscal único que ya trae el neto correcto.
        cash = round(neto - drip, 2)

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


def verificar_identidades(datos: dict, stats: dict = None, tolerancia: float = 0.02) -> list:
    """Comprueba las identidades contables del recorrido. Devuelve la lista de fallos.

    No es decorativo: son las relaciones que el waterfall dibuja. Si no se cumplen, las
    barras mienten aunque cada cifra por separado sea correcta.

    `stats` (opcional, el dict crudo de `analyze_portfolio` para este ticker): si se pasa,
    además reconcilia BRUTO/NETO contra una RELECTURA INDEPENDIENTE del CSV
    (`logic._csv_dividends_in_window` sobre `stats['history']`) — no contra la fórmula que
    los generó. Los checks de arriba (`bruto = neto + impuesto`, `neto = reinvertido +
    efectivo`, …) son identidades DEFINITORIAS de `cashflow_data`/`hoja_data`: cada cifra de
    la derecha participa en construir la de la izquierda, así que nunca pueden fallar por
    construcción — sirven para cazar un error de tecleo, no un bug real en el objeto fiscal.
    Este check sí es real: vuelve a sumar el ledger desde cero, sin tocar ningún campo ya
    cacheado en `stats`/`datos`, así que si `build_dividend_tax_totals` (o su cableado en
    `analyze_portfolio`/`cashflow_data`) se rompe, esto lo detecta.
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

    history = (stats or {}).get("history")
    if history is not None and len(history):
        # Compara SIEMPRE contra BRUTO, sin mirar `dividend_base_convention` — ese campo es
        # el resultado de la misma detección (`_dividend_tax_netted`) que este guard debe
        # poder auditar. Leerlo para decidir qué lado comparar lo hacía tautológico: si la
        # detección se rompe, el campo se rompe con ella y el guard termina comparando
        # NETO (mal etiquetado) contra un ledger que por casualidad también da ese número.
        # `_bruto_independiente_del_csv` relee el CSV sin pasar por esa convención.
        bruto_independiente = _bruto_independiente_del_csv(history)
        if abs(bruto_independiente - datos["BRUTO"]) > tolerancia:
            fallos.append(
                f"BRUTO vs CSV releído independiente: {datos['BRUTO']:.2f} "
                f"≠ {bruto_independiente:.2f}")

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
    poseidos = [t for t, m in classify_map.items()
                if m == "mode_a" and t in TRG_YM and _tiene_datos(resultados.get(t))]
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


# Capital arbitrario para las corridas de `backtest.run_backtest`: como `comparacion_data`
# solo entrega RATIOS (cada serie se renormaliza en JS contra su propio valor de arranque,
# igual que `trg_real_data`), la escala no importa — 100 hace que el primer punto de cada
# serie (su propia incepcion) caiga en el mismo numero que un indice base-100 clasico, util
# para depurar el JSON a ojo.
_CMP_CAPITAL = 100.0

# Retencion NRA plana del modo "Peor caso" — literal del demo (`RATE = 0.30` que tenia
# `comparacion.html` antes de esta fase). Fijo, no depende del pais del usuario: a
# diferencia de "Comparacion Real" (`trg_real_data`, atada al portafolio cargado),
# "Simulacion" es un panel pedagogico independiente del CSV — no hay pais que leer.
_CMP_FLAT_RATE = 0.30


def _cmp_nra_rate(ticker: str, modo: str, roc19a: dict) -> float:
    """Retencion NRA efectiva por modo fiscal (mapa-datos § 3.3a del plan de remediacion):

      - 'bruto': 0.0 — sin retencion (residente EE.UU.).
      - 'plano': `_CMP_FLAT_RATE` sobre TODA la distribucion — peor caso, sin escudo ROC.
      - 'roc':   `_CMP_FLAT_RATE * (1 - weighted_pct/100)` — el escudo fiscal del ROC
        ponderado que publica YieldMax en sus avisos 19(a) (`knowledge/roc_19a.yaml`).
        Fondos sin avisos 19(a) (ETFs de crecimiento, o un YieldMax que aun no publico
        ninguno) no tienen escudo que aplicar: caen a la tasa plana, igual que hace
        `logic.build_roc_aware_withholding`/`build_drip_comparison_series` para el mismo
        caso.

    `weighted_pct` es un PROMEDIO PONDERADO sobre una ventana rodante (~52 avisos mas
    recientes, ver `logic.load_roc_19a`) — no la historia completa del fondo desde su
    incepcion. Aplicarlo aqui a TODO el horizonte del backtest (incluidos los tramos
    anteriores a esa ventana) es, por construccion, una EXTRAPOLACION: la mejor tasa
    disponible, pero no una medida directa de esos tramos viejos. `comparacion_data`
    declara esto en `roc19a` (rango de fechas de la ventana) para que la UI lo diga en
    vez de presentarlo como si fuera medido — ese es el punto entero de esta fase.
    """
    if modo == "bruto":
        return 0.0
    if modo == "plano":
        return _CMP_FLAT_RATE
    info = roc19a.get(ticker)
    weighted = info.get("weighted_pct") if info else None
    if weighted is None:
        return _CMP_FLAT_RATE
    try:
        weighted = float(weighted)
    except (TypeError, ValueError):
        return _CMP_FLAT_RATE
    return max(0.0, min(1.0, _CMP_FLAT_RATE * (1.0 - weighted / 100.0)))


def comparacion_data() -> dict | None:
    """JSON para `ui/componentes/comparacion.html` (Total Return Graph · Simulación).

    Mismo patrón de índice mensual (`origen`/`last`/`idx[modo][tk][m]`) que
    `trg_real_data`, pero con dos diferencias deliberadas (Fase 3.3a del plan de
    remediación — reemplaza las cifras inventadas `F`/`shapeOf`/`targetEnd` que tenía
    `comparacion.html`):

      1. **No depende del portafolio del usuario.** `comparacion.html` es el panel
         pedagógico "y si hubiera invertido en..." — vive fuera del wizard, sin CSV
         cargado (a diferencia de "Comparación · Real", que sí necesita `resultados`).
      2. **La fuente es `price_cache.load_history` + `backtest.run_backtest`**, no
         `logic.build_drip_comparison_series`. Ese motor ya reconcilió al 0.013% contra
         el extracto real de IB (Fase 3.1, `test_backtest.py`) y lee del caché en disco
         (Fase 3.2, `test_price_cache.py`) — cero llamadas a yfinance en este código;
         el único punto que puede tocar red es el fallback YA declarado dentro de
         `price_cache.load_history` (cache ausente/vencido), y ese fallback se
         propaga aquí vía `fuente`/`degradado`, nunca en silencio.

    Además del índice "Con DRIP" (`idx`, para los 8 tickers de `TRG_UNIVERSO`), calcula
    "Sin DRIP" (`idxSin`/`precioSin`, solo para `TRG_YM` — es la única familia que puede
    ser fondo base, y el toggle "Cómo se reinvirtió" solo aplica al fondo base) separando
    el retorno de precio puro del efectivo acumulado sin componer — la misma separación
    que `seriesSin` dibuja en JS, ahora con datos reales en vez de una rampa lineal
    fabricada sobre un `shapeOf` senoidal.

    Devuelve `None` solo si NINGÚN ticker del universo pudo cargar historia (ni caché ni
    yfinance en vivo) — la vista entera se degrada con un aviso explícito en vez de
    dibujar un gráfico vacío o a medias.
    """
    historias: dict[str, price_cache.HistoryResult] = {}
    for tk in TRG_UNIVERSO:
        try:
            hr = price_cache.load_history(tk)
        except Exception:
            continue
        if hr.history is None or hr.history.empty:
            continue
        historias[tk] = hr

    if not historias:
        return None

    ancla, ancla_start = None, None
    for tk in TRG_YM:
        if tk not in historias:
            continue
        start = historias[tk].history.sort_index().index.min()
        if ancla_start is None or start < ancla_start:
            ancla, ancla_start = tk, start
    if ancla is None:
        return None

    origen = [int(ancla_start.year), int(ancla_start.month) - 1]
    roc19a = logic.load_roc_19a()

    def _mensualizar(serie) -> dict:
        """Remuestreo mensual (último cierre de cada mes) con la misma excepción de
        primer-mes que `trg_real_data`: el primer bin suele ser parcial (la incepción
        real casi nunca cae el día 1), y `.resample().last()` ahí devolvería el cierre
        de FIN de ese mes en vez del valor real de arranque — que es justo el punto que
        cada serie usa como su propio 100% (ver `_CMP_CAPITAL`)."""
        serie = serie.sort_index()
        mensual = serie.resample("ME").last().dropna()
        if len(mensual):
            mensual.iloc[0] = serie.iloc[0]
        out = {}
        for fecha, valor in mensual.items():
            m = (int(fecha.year) - origen[0]) * 12 + (int(fecha.month) - 1 - origen[1])
            out[str(m)] = round(float(valor), 4)
        return out

    idx: dict = {modo: {} for modo in TRG_MODOS}
    idx_sin: dict = {modo: {} for modo in TRG_MODOS}
    precio_sin: dict = {}
    incep: dict = {}
    grp: dict = {}
    last = 0

    def _actualizar_last(valores: dict) -> None:
        nonlocal last
        if valores:
            last = max(last, max(int(k) for k in valores))

    for tk, hr in historias.items():
        history = hr.history.sort_index()
        start = history.index.min()
        incep[tk] = (int(start.year) - origen[0]) * 12 + (int(start.month) - 1 - origen[1])
        grp[tk] = "ym" if tk in TRG_YM else "growth"

        for modo in TRG_MODOS:
            rate = _cmp_nra_rate(tk, modo, roc19a)
            r_con = backtest.run_backtest(tk, start_date=start, initial_capital=_CMP_CAPITAL,
                                          drip=True, nra_rate=rate, history=history)
            valores_con = _mensualizar(r_con.daily["total_value"])
            idx[modo][tk] = valores_con
            _actualizar_last(valores_con)

            if tk in TRG_YM:
                r_sin = backtest.run_backtest(tk, start_date=start, initial_capital=_CMP_CAPITAL,
                                              drip=False, nra_rate=rate, history=history)
                valores_sin = _mensualizar(r_sin.daily["total_value"])
                idx_sin[modo][tk] = valores_sin
                _actualizar_last(valores_sin)
                if tk not in precio_sin:
                    # El componente de precio NO depende de la retencion (nra_rate solo
                    # afecta cuanto efectivo se acumula, nunca el precio de mercado) —
                    # basta una corrida por ticker, no una por modo.
                    precio_sin[tk] = _mensualizar(r_sin.daily["portfolio_value"])

    fuente = {tk: hr.source for tk, hr in historias.items()}
    degradado = sorted(tk for tk, s in fuente.items() if s != "cache")
    faltantes = sorted(t for t in TRG_UNIVERSO if t not in historias)

    roc_ventana: dict = {}
    for tk in TRG_YM:
        info = roc19a.get(tk)
        if not info:
            continue
        fechas = [str(r["date"]) for r in (info.get("per_distribution") or []) if r.get("date")]
        if not fechas:
            continue
        roc_ventana[tk] = {
            "min": min(fechas), "max": max(fechas),
            "weighted_pct": info.get("weighted_pct"), "asof": info.get("asof"),
        }

    asof_candidatos = [hr.cache_asof for hr in historias.values() if hr.cache_asof]
    asof = max(asof_candidatos) if asof_candidatos else datetime.date.today().isoformat()

    return {
        "origen": origen,
        "last": last,
        "base_defecto": "NVDY" if "NVDY" in historias else ancla,
        "tasa_pct": round(_CMP_FLAT_RATE * 100.0),
        "asof": asof,
        "incep": incep,
        "grp": grp,
        "col": {tk: TRG_COLORES[tk] for tk in historias if tk in TRG_COLORES},
        "idx": idx,
        "idxSin": idx_sin,
        "precioSin": precio_sin,
        "fuente": fuente,
        "degradado": degradado,
        "faltantes": faltantes,
        "roc19a": roc_ventana,
    }
