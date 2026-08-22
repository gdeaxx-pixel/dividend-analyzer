"""Traduce lo que calcula `logic.py` al JSON que consumen los componentes HTML.

Esta capa **no calcula nada fiscal**: lee y reordena. Toda cifra de impuesto sale del
objeto `tax_summary` que ya construyó `analyze_portfolio` (Regla 3 del contrato
ROC/NRA: objeto fiscal único, se renderiza, no se recalcula).

El mapa cifra→campo está en `specs/port-artifact/mapa-datos.md` § 1, verificado corriendo
`analyze_portfolio` sobre los fixtures.
"""

from __future__ import annotations

import datetime
import math
import typing

import pandas as pd

import backtest
import logic
import price_cache

# Universo del Total Return Graph — 5 fondos YieldMax + 3 ETFs de crecimiento + 4 acciones
# subyacentes. Paleta y agrupación literales del demo (`viaje-dinero-waterfall.html:2781`).
# Viven aquí (no en `ui/vistas.py`, que las tenía antes bajo `_TRG_*`) porque las consume
# `trg_real_data`; `ui.vistas` ya importa de `ui.adapters`, así que dejarlas en vistas.py
# habría creado un import circular en cuanto el adapter necesitara leerlas.
TRG_YM = ("NVDY", "TSLY", "CONY", "MSTY", "CHPY")
TRG_GROWTH = ("SCHB", "XLK", "SMH")
TRG_SUB = ("NVDA", "TSLA", "COIN", "MSTR")
TRG_UNIVERSO = TRG_YM + TRG_GROWTH + TRG_SUB
# La vista «Real» (trg_real_data) tiene sus chips hardcodeados aparte y nunca dibujaría los
# subyacentes: si compartiera TRG_UNIVERSO bajaría 4 tickers x 3 modos para tirarlos, y los
# listaría en su aviso «Sin datos». Se queda con el universo de 8.
TRG_UNIVERSO_REAL = TRG_YM + TRG_GROWTH
# Subyacente de cada YieldMax de un solo nombre. CHPY no tiene: no aparece en instruments.yaml
# ni en YIELDMAX_RISK_PROFILES.
TRG_PARES = {"NVDY": "NVDA", "TSLY": "TSLA", "CONY": "COIN", "MSTY": "MSTR"}
TRG_COLORES = {"NVDY": "#1f86c4", "TSLY": "#d1662f", "CONY": "#b95cae", "MSTY": "#a8b020",
               "CHPY": "#17a89a", "SCHB": "#b06a3d", "XLK": "#8f76d4", "SMH": "#c99a26",
               # Cada subyacente toma la variante oscura del color de su YieldMax (paleta
               # CVD-safe ya validada con la skill dataviz, ver app_old.py:6018-6020): el par
               # comparte familia de color y el ojo lo agrupa solo.
               "NVDA": "#006497", "TSLA": "#C05621", "COIN": "#A84C9E", "MSTR": "#98A000"}
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


def cashflow_data(stats: dict, ticker: str, tax_summary: dict = None) -> dict:
    """Las 12 constantes del Cash flow, más lo que el componente necesita para rotular.

    Equivale al bloque `viaje-dinero-waterfall.html:2124-2127`, pero con datos del CSV.

    `tax_summary` permite inyectar el objeto fiscal ya re-derivado por el país declarado
    (capa 2, `logic.build_tax_summaries`). Sin él se usa el cacheado en `stats` — que es la
    capa 1, SIN DECLARAR, y por tanto no trae devolución estimada. Nunca se recalcula el
    concepto aquí (Regla 3): o llega el objeto, o se lee el de `stats`.
    """
    if not stats or stats.get("skipped"):
        raise DatosIncompletos(f"{ticker}: sin datos analizables")

    pocket = _f(stats.get("pocket_investment"))
    drip = _f(stats.get("dividends_collected_drip"))
    valor_hoy = _f(stats.get("market_value"))

    # Regla 3: la retención sale del objeto fiscal único, no de una resta propia.
    # `withheld_tax_total` está en stats y coincide, pero la fuente canónica es
    # `tax_summary` — si algún día divergen, manda el objeto.
    tax = tax_summary if tax_summary is not None else (stats.get("tax_summary") or {})
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
        # Sin residencia declarada la devolución no se estima (Regla 2: una cifra sin base
        # declarada no se publica). El componente debe ocultarla, no pintar $0 — que se
        # leería como "no te vuelve nada" en vez de "no lo sabemos todavía".
        "tasa_declarada": bool(tax.get("rate_declared", False)),
        "tasa_pais": tax.get("country"),
        "tasa_pct": tax.get("base_rate_pct"),
    }


def hoja_data(stats: dict, ticker: str, df, tax_summary: dict = None) -> dict:
    """Las 12 constantes del Cash flow más `INICIO`/`TICKER`, para la Hoja Excel.

    Equivale al bloque `viaje-dinero-waterfall.html:3000-3006` (`initHoja`), que no
    introduce datos nuevos: deriva `TOTALINV`/`APARENTE` de las mismas 12 constantes
    del Cash flow (mapa-datos.md § 2). `INICIO` es la fecha de la primera transacción
    del ticker en el CSV — el mismo criterio que usa `logic.py:687`
    (`ticker_df['Date'].min()`), no persistido en `stats`, así que se recalcula aquí
    leyendo el mismo `df` que ya validó la carga.
    """
    datos = cashflow_data(stats, ticker, tax_summary=tax_summary)
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


# Las cifras que este guard compara. Todas tienen que ser números reales antes de
# entrar a cualquier resta: ver la nota sobre NaN en `verificar_identidades`.
_CLAVES_FINITAS = (
    "BRUTO", "NETO", "IMPUESTO", "DRIP", "CASH", "POCKET",
    "TOTAL_TRABAJANDO", "MERCADO", "VALOR_HOY", "CAPITAL_ACTUAL", "RESULTADO",
)


def verificar_identidades(datos: dict, stats: dict = None, tolerancia: float = 0.02) -> list:
    """Comprueba las identidades contables del recorrido. Devuelve la lista de fallos.

    No es decorativo: son las relaciones que el waterfall dibuja. Si no se cumplen, las
    barras mienten aunque cada cifra por separado sea correcta.

    Antes de comparar nada, exige que las cifras sean **finitas**. Un NaN no falla una
    identidad: la desactiva (toda comparación con NaN es falsa), y el guard pasaría en
    silencio justo cuando los datos están rotos. Ver la nota extensa en el cuerpo.

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
    # Un NaN no FALLA los checks de abajo: los DESACTIVA. Toda comparación con NaN es
    # falsa, así que `abs(nan - x) > tolerancia` da False y la identidad «pasa» — el guard
    # que existe precisamente para no dibujar algo que miente se queda ciego justo en el
    # caso donde más falta hace. Y el silencio es total: la posición tampoco aparecería
    # como ganadora ni como perdedora, porque esas comparaciones también son falsas.
    #
    # No es hipotético: yfinance devolvió cierres NaN el 2026-08-18, `market_value` salió
    # NaN y las cifras llegaron rotas a pantalla sin que nada lo reportara.
    # `metodo_real_data` ya se defendía por su cuenta con `math.isfinite`; el guard común
    # no, así que cada vista tenía que acordarse de hacerlo. Ahora lo hace el guard.
    #
    # Se comprueba ANTES de restar, y con `math.isfinite`, que también caza ±inf (un
    # infinito sí dispararía los checks, pero imprimiría «inf ≠ inf» en vez de decir qué
    # pasó). Se devuelve de inmediato: con una cifra no numérica en el objeto, cualquier
    # identidad que la toque es indecidible, y las que no la tocan no salvan la vista.
    no_finitos = [c for c in _CLAVES_FINITAS
                  if c in datos and not math.isfinite(_f(datos[c], float("nan")))]
    if no_finitos:
        return [f"cifra no numérica en {', '.join(no_finitos)} — sin precio de mercado "
                f"utilizable hoy la posición no se puede valorar"]

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


def _trg_ancla(historias: dict):
    """El YM de `TRG_YM` con la incepción más antigua entre las historias YA cargadas —
    decisión 4 del traspaso 2026-08-10: el ancla NO se hardcodea (hoy es TSLY; mañana
    puede entrar otro fondo). Devuelve (ticker, Timestamp) o (None, None) si ninguno de
    los 5 cargó.

    Recibe las historias en vez de descargarlas: antes hacía su propia ronda de
    `logic.fetch_market_data` —a la red, en runtime— y después `trg_real_data` volvía a
    bajar los mismos 8 tickers. Hoy ambos leen el mismo dict del caché de precio.
    """
    mejor_tk, mejor_start = None, None
    for tk in TRG_YM:
        history = historias.get(tk)
        if history is None or history.empty:
            continue
        start = history.index.min()
        if mejor_start is None or start < mejor_start:
            mejor_tk, mejor_start = tk, start
    return mejor_tk, mejor_start


def trg_real_data(resultados: dict, tasa_pct: float, pais: str | None = None) -> dict | None:
    """JSON para `ui/componentes/comparacion_real.html` (Total Return Graph · datos
    reales): el índice TRI crudo de los 8 tickers de `TRG_UNIVERSO_REAL` × 3 modos
    fiscales sobre la ventana completa (mapa-datos.md § 5). No incluye los 4 subyacentes
    (`TRG_SUB`) — este componente nunca dibuja esos chips, se aísla a propósito.

    El componente no calcula nada — Python entrega el índice base 100 (normalizado en
    la incepción de cada ticker, o en la del ancla si es posterior) y JS renormaliza
    al fondo base que el usuario elija dentro del iframe, sin rerun (decisión 3 del
    traspaso 2026-08-10: arquitectura Exhibit 2 del paper Morningstar TRI). Por eso las
    series se calculan UNA vez por (ticker, modo), siempre ancladas al YM más antiguo —
    no una por cada posible selección de fondo base.

    **Motor y política fiscal (migración 2026-08-21).** Corre `price_cache.load_history`
    + `backtest.run_backtest` con `_politica_fiscal`, exactamente igual que
    `comparacion_data`. Hasta esa fecha usaba `logic.build_drip_comparison_series`, que
    (a) bajaba de yfinance EN RUNTIME por cada ticker y modo —`fetch_market_data`, la
    última ruta de la UI que tocaba la red— y (b) modelaba el escudo ROC como tasa
    efectiva `tasa × (1 − ROC)` aplicada al cobro, o sea asumiendo que el dinero nunca
    sale del fondo. Hoy retiene la tasa COMPLETA al cobro y el reembolso llega con el
    1042-S, meses después. El modo `bruto` no se movió ni un decimal (ahí no hay nada
    que retener y los dos motores ya coincidían: NVDY 365.54 en ambos); `roc` y `plano`
    sí, y bastante — ver el PR de la migración.

    A diferencia de «Simulación», la tasa NO es el 30% fijo: sale del país declarado por
    el cliente (`ui.estado.perfil_fiscal()` → `tasa_pct`), y por eso viaja como
    `base_rate` hasta `_politica_fiscal`. Sin país declarado, quien llama sustituye por
    `NRA_DEFAULT_RATE` (30%) — el peor caso, nunca 0%.

    Devuelve `None` si el ancla (el YM de incepción más antigua) no está en el caché; para
    cualquier otro ticker, si falla simplemente no aparece en `idx`/`incep`/`col` — el
    componente omite su chip, no inventa una serie. `fuente`/`degradado`/`faltantes`
    declaran de dónde salió cada serie, igual que en `comparacion_data`: un caché vencido
    que se rellenó de la red se dice, no se calla.

    **Límite conocido del eje mensual (auditoría 2026-08-10).** Dentro del mes en que
    arranca el fondo base, el base y sus comparadores NO se anclan en el mismo
    instante: el base entra por su primer dato real (la excepción de primer-mes de
    `_mensualizar_desde`) y los comparadores, que ya existían, por el cierre de fin de
    ese mes.
    Son hasta ~3 semanas de desfase en un solo punto, el de normalización. Medido con
    base MSTY (incepción 22-feb-2024): el componente da SMH +173% donde el cálculo
    diario da +176%; MSTY +23% contra +24%. Es la contrapartida declarada de portar el
    eje mensual del demo (decisión 5 del traspaso) y afecta solo a la comparación
    visual, nunca a una cifra fiscal. Si algún día hace falta paridad exacta con el
    cálculo diario, la vía es interpolar el valor de cada comparador en la fecha real
    de incepción del base, no volver a serie diaria (multiplicaría el JSON por ~20).
    """
    if tasa_pct is None:
        raise ValueError("trg_real_data requiere una tasa: sin país declarado, quien "
                         "llama debe sustituir por NRA_DEFAULT_RATE, nunca por 0")
    historias: dict[str, pd.DataFrame] = {}
    fuente: dict[str, str] = {}
    asof_candidatos: list[str] = []
    for tk in TRG_UNIVERSO_REAL:
        try:
            hr = price_cache.load_history(tk)
        except Exception:
            continue
        if hr.history is None or hr.history.empty:
            continue
        historias[tk] = hr.history.sort_index()
        fuente[tk] = hr.source
        if hr.cache_asof:
            asof_candidatos.append(hr.cache_asof)

    ancla, ancla_start = _trg_ancla(historias)
    if ancla is None:
        return None

    origen = [int(ancla_start.year), int(ancla_start.month) - 1]
    roc19a = logic.load_roc_19a()
    base_rate = tasa_pct / 100.0

    idx: dict = {modo: {} for modo in TRG_MODOS}
    incep: dict = {}
    grp: dict = {}
    last = 0

    for tk, history in historias.items():
        # La ventana arranca en el ancla: un comparador que ya existía antes no puede
        # aportar retorno de meses en que la lección todavía no había empezado.
        start = max(history.index.min(), ancla_start)
        incep[tk] = (int(start.year) - origen[0]) * 12 + (int(start.month) - 1 - origen[1])
        grp[tk] = "ym" if tk in TRG_YM else "growth"
        for modo in TRG_MODOS:
            pol = _politica_fiscal(tk, modo, roc19a, base_rate=base_rate)
            r = backtest.run_backtest(tk, start_date=start, initial_capital=_INDICE_CAPITAL,
                                      drip=True, nra_rate=pol.rate, history=history,
                                      roc_pct_by_year=pol.roc_pct_by_year)
            if r.daily.empty:
                continue
            valores = _mensualizar_desde(r.daily["total_value"], origen)
            idx[modo][tk] = valores
            if valores:
                last = max(last, max(int(m) for m in valores))

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
        # La fecha que se muestra es la del CACHÉ que se usó, no la de hoy: el copy dice
        # «precios y dividendos de mercado hasta el X», y con el motor viejo —que bajaba
        # en vivo— hoy y el dato coincidían. Leyendo del caché ya no: anunciar la fecha de
        # hoy sobre datos del viernes es exactamente la clase de cifra sin procedencia que
        # el repo persigue. Mismo criterio que `comparacion_data`.
        "asof": max(asof_candidatos) if asof_candidatos else datetime.date.today().isoformat(),
        "incep": incep,
        "grp": grp,
        "col": {tk: TRG_COLORES[tk] for tk in historias if tk in TRG_COLORES},
        "fuente": fuente,
        "degradado": sorted(tk for tk, s in fuente.items() if s != "cache"),
        "faltantes": sorted(t for t in TRG_UNIVERSO_REAL if t not in historias),
        "idx": idx,
    }


# Capital arbitrario para las corridas de `backtest.run_backtest` de las dos vistas de
# «Comparacion»: como ambas entregan RATIOS (cada serie se renormaliza en JS contra su
# propio valor de arranque), la escala no importa — 100 hace que el primer punto de cada
# serie caiga en el mismo numero que un indice base-100 clasico, util para depurar el JSON
# a ojo. Se llamaba `_CMP_CAPITAL` cuando solo lo usaba «Simulacion».
_INDICE_CAPITAL = 100.0

# Retencion NRA plana del modo "Peor caso" — literal del demo (`RATE = 0.30` que tenia
# `comparacion.html` antes de esta fase). Fijo, no depende del pais del usuario: a
# diferencia de "Comparacion Real" (`trg_real_data`, atada al portafolio cargado),
# "Simulacion" es un panel pedagogico independiente del CSV — no hay pais que leer.
_CMP_FLAT_RATE = 0.30


def _tasa_efectiva_neta(ticker: str, modo: str, roc19a: dict) -> float:
    """Tasa NRA **efectiva neta de reembolso** por modo fiscal: lo que el inversor acaba
    pagando una vez cerrado el ciclo fiscal. Es una cifra que la UI **reporta** — no la
    tasa que se aplica en ninguna simulación.

      - 'bruto': 0.0 — sin retención (residente EE. UU.).
      - 'plano': `_CMP_FLAT_RATE` sobre TODA la distribución — peor caso, sin escudo ROC.
      - 'roc':   `_CMP_FLAT_RATE * (1 - weighted_pct/100)` — el 30% retenido menos la
        porción que el aviso 19(a) reclasifica como retorno de capital y devuelve
        (`knowledge/roc_19a.yaml`). Fondos sin avisos 19(a) (ETFs de crecimiento, o un
        YieldMax que aún no publicó ninguno) no tienen nada que reclasificar: caen a la
        tasa plana.

    **Ya no gobierna ninguna corrida del motor** (migración 2026-08-21). Hasta esa fecha
    `comparacion_data` se la pasaba como `nra_rate` y era el último punto del repo donde el
    escudo ROC vivía DENTRO de la tasa. Meterlo ahí asume que el escudo aplica AL COBRO —que
    el dinero nunca sale del fondo y compone todo el tiempo—, y no es lo que ocurre: se
    retiene el 30% completo y el reembolso llega meses después, con el 1042-S. Quien simula
    es `_politica_fiscal`, que separa las dos cosas (tasa al cobro + %ROC por año). Los dos
    modelos no son equivalentes: medido sobre el universo de esta vista, la diferencia va de
    −18.7 pp (TSLY) a +28.0 pp (MSTY) en el retorno total Con DRIP. Ver el docstring de
    `backtest.run_backtest` y `specs/roc-nra-invariants.md` (Regla 2: base Y momento).

    Como cifra **reportada** sigue siendo correcta —el total pagado al final del ciclo es el
    mismo— y es la que la nota al pie de la 3ª gráfica de «La matriz» usa para decir
    «8.7%–17.6% según el fondo». Lo que una tasa no puede expresar es el MOMENTO, que es
    justo lo que mueve el resultado.

    `weighted_pct` es un PROMEDIO PONDERADO sobre una ventana rodante (~52 avisos más
    recientes, ver `logic.load_roc_19a`) — no la historia completa del fondo desde su
    incepción. Como tasa única para todo el horizonte es, por construcción, una
    EXTRAPOLACIÓN. `_roc_pct_by_year` no extrapola: usa el promedio de cada año y deja los
    años anteriores a la ventana sin escudo. Por eso esta tasa y la simulación pueden
    discrepar incluso ignorando el momento, y por eso `comparacion_data` publica la ventana
    en `roc19a` para que la UI declare el alcance en vez de presentarlo como medido.
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


def _mensualizar_desde(serie, origen, decimales: int = 4) -> dict:
    """Remuestreo mensual (último cierre de cada mes) con la misma excepción de
    primer-mes que `trg_real_data`: el primer bin suele ser parcial (la incepción real
    casi nunca cae el día 1), y `.resample().last()` ahí devolvería el cierre de FIN de
    ese mes en vez del valor real de arranque — que es justo el punto que cada serie usa
    como su propio 100% (ver `_INDICE_CAPITAL`) o, en `metodo_serie_data`, como el dólar
    exacto que salió del bolsillo el día que se abrió la posición.

    Las claves son índices de mes relativos a `origen` (`[año, mes0]`), en texto, porque
    el destino es JSON y ahí toda clave es texto de todos modos.

    Estaba definida dentro de `comparacion_data` como closure sobre su `origen`. Subió a
    nivel de módulo cuando `metodo_serie_data` necesitó exactamente el mismo remuestreo:
    dos copias de la excepción de primer-mes es justo el tipo de duplicado que después
    diverge en una sola de las dos y nadie lo nota.
    """
    serie = serie.sort_index()
    mensual = serie.resample("ME").last().dropna()
    if len(mensual):
        mensual.iloc[0] = serie.iloc[0]
    out = {}
    for fecha, valor in mensual.items():
        m = (int(fecha.year) - origen[0]) * 12 + (int(fecha.month) - 1 - origen[1])
        out[str(m)] = round(float(valor), decimales)
    return out


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
         `logic.build_drip_comparison_series` (retirada el 2026-08-21; en su momento era el
         otro camino posible). Ese motor ya reconcilió al 0.013% contra
         el extracto real de IB (Fase 3.1, `test_backtest.py`) y lee del caché en disco
         (Fase 3.2, `test_price_cache.py`) — cero llamadas a yfinance en este código;
         el único punto que puede tocar red es el fallback YA declarado dentro de
         `price_cache.load_history` (cache ausente/vencido), y ese fallback se
         propaga aquí vía `fuente`/`degradado`, nunca en silencio.

    **Política fiscal: la del objeto único** (`_politica_fiscal`, migración 2026-08-21).
    Los 3 modos de `TRG_MODOS` no son tres tasas: son tres políticas. «bruto» no retiene;
    «plano» retiene el 30% y no devuelve nada; «roc» retiene el 30% COMPLETO al cobro y la
    porción que el aviso 19(a) reclasifica vuelve en efectivo meses después, con el 1042-S
    (`roc_pct_by_year` + `refund_month` de `run_backtest`). Hasta esta migración el modo
    «roc» se simulaba con la tasa efectiva `0.30 × (1 − ROC)` —el escudo dentro de la
    tasa—, que asume que el dinero nunca sale del fondo: la misma app decía «Con NRA · ROC
    19a» en dos secciones con dos modelos distintos. La diferencia no es cosmética: de
    −18.7 pp (TSLY) a +28.0 pp (MSTY) en el retorno total Con DRIP.

    Consecuencia en el JSON: en modo «roc», `idx`/`idxSin` incluyen la cuenta por cobrar al
    fisco (`roc_receivable`, un activo real) además del valor de mercado y el efectivo.
    `precioSin` no — es solo precio, y por eso el área que el componente pinta como
    «efectivo» en modo «roc» contiene también el reembolso pendiente. El copy lo declara.

    Además del índice "Con DRIP" (`idx`, para los 12 tickers de `TRG_UNIVERSO`), calcula
    "Sin DRIP" (`idxSin`/`precioSin`, para TODO el universo — cualquier ticker puede ser
    fondo base, y el toggle "Cómo se reinvirtió" solo aplica al fondo base) separando
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
        return _mensualizar_desde(serie, origen)

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
        grp[tk] = "ym" if tk in TRG_YM else ("sub" if tk in TRG_SUB else "growth")

        for modo in TRG_MODOS:
            pol = _politica_fiscal(tk, modo, roc19a)
            r_con = backtest.run_backtest(tk, start_date=start, initial_capital=_INDICE_CAPITAL,
                                          drip=True, nra_rate=pol.rate, history=history,
                                          roc_pct_by_year=pol.roc_pct_by_year)
            valores_con = _mensualizar(r_con.daily["total_value"])
            idx[modo][tk] = valores_con
            _actualizar_last(valores_con)

            # Sin DRIP para TODO el universo: desde que cualquier ticker puede ser
            # fondo base, el toggle «Reinversión» tiene que tener datos para los 12.
            r_sin = backtest.run_backtest(tk, start_date=start, initial_capital=_INDICE_CAPITAL,
                                          drip=False, nra_rate=pol.rate, history=history,
                                          roc_pct_by_year=pol.roc_pct_by_year)
            valores_sin = _mensualizar(r_sin.daily["total_value"])
            idx_sin[modo][tk] = valores_sin
            _actualizar_last(valores_sin)
            if tk not in precio_sin:
                # El componente de precio NO depende de la politica fiscal: sin DRIP las
                # acciones nunca cambian de numero, asi que `portfolio_value` es el mismo
                # en los tres modos (la retencion y el reembolso del 1042-S solo mueven
                # `cash_accum`/`roc_receivable`, nunca el precio de mercado ni las
                # acciones). Basta una corrida por ticker, no una por modo.
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

    sin_dividendos = sorted(
        tk for tk, hr in historias.items()
        if float(hr.history.get("Dividends", pd.Series(dtype=float)).fillna(0).sum()) == 0.0)

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
        "par": TRG_PARES,
        "sin_dividendos": sin_dividendos,
    }


# Caso de estudio de «Método tradicional · La matriz» (Fase 3.3b) — el portafolio de la
# clase de Greco. Decisión de producto de Daniel: la LECCIÓN queda fija (mismos 5
# tickers, misma fecha de apertura, mismo aporte inicial — la cifra que literalmente
# salió del bolsillo de Greco, con centavos); lo que deja de estar hardcodeado es todo
# lo que un mercado real puede recalcular por su cuenta — dividendos cobrados, valor de
# mercado, último pago. `dr` (RENDI) también queda literal a propósito: el propio
# modal (`modal-tmrend`) explica que es "copiada a mano el día que se armó, y nunca se
# refrescó" — es un dato histórico sobre lo que decía la hoja ese día, no una medición
# en vivo, así que no hay nada que derivar.
MET_CASO = (
    {"t": "CONY", "ini": "9/6/2023", "start": "2023-09-06", "dr": 74.05, "inv": 9004.87},
    {"t": "NVDY", "ini": "6/23/2023", "start": "2023-06-23", "dr": 47.18, "inv": 7670.26},
    {"t": "MSTY", "ini": "7/2/2024", "start": "2024-07-02", "dr": 77.28, "inv": 13599.57},
    {"t": "TSLY", "ini": "5/5/2023", "start": "2023-05-05", "dr": 44.84, "inv": 10020.32},
    {"t": "NFLY", "ini": "12/8/2023", "start": "2023-12-08", "dr": 69.73, "inv": 7991.20},
)


def _payback_contraejemplo(ratios: list[dict]) -> str | None:
    """Elige el ticker que ilustra «cobró y perdió» en el panel Payback ≠ ganancia: el
    de mayor payback bruto (`pb`) entre los que tienen retorno real negativo (`ret`).

    Antes estaba cableado a mano a CONY, literal desde la hoja fechada 5/1/2026. Con
    datos vivos CONY dejó de perder (traspaso 2026-08-17: retorno pasó de -8.6% a
    +18.4%), así que el contraejemplo tiene que salir del dato en cada corrida, no
    quedarse fijo al ticker que lo ilustraba el día que se armó la hoja.

    Devuelve `None` si en la corrida actual ningún ticker perdió capital — el panel no
    puede inventar un contraejemplo que no existe esa semana (Duda 2 del traspaso).
    """
    negativos = [r for r in ratios if r["ret"] < 0]
    if not negativos:
        return None
    return max(negativos, key=lambda r: r["pb"])["t"]


def _tmtot_ejemplo(ratios: list[dict]) -> str | None:
    """Elige el ticker que ilustra la paradoja de `modal-tmtot`: ganó dinero de verdad y
    a la vez arrastra pérdida de capital contra su Total inv. — el de mayor `ret` entre
    los que tienen `perdidaCapital > 0`.

    Estaba cableado a NVDY con dos cifras literales (+244.1% y $11,673.52) copiadas el
    día que se armó la hoja; medidas hoy dan +282.9% y $12,281.41. Peor que desfasadas:
    convivían en el mismo modal con el párrafo de arriba, que sí se alimenta en vivo de
    `TOT` — dos cifras de momentos distintos a dos párrafos de distancia.

    `None` si en esta corrida ningún ticker tiene las dos preguntas apuntando en
    direcciones opuestas. El modal lo declara en vez de inventar un protagonista, mismo
    patrón que `_payback_contraejemplo`.
    """
    candidatos = [r for r in ratios if r["perdidaCapital"] > 0]
    if not candidatos:
        return None
    return max(candidatos, key=lambda r: r["ret"])["t"]


def metodo_data() -> dict | None:
    """JSON para `ui/componentes/metodo.html` (Método tradicional · La matriz, Fase
    3.3b). Reemplaza los `var MATRIZ`/`var ROC_19A` congelados que tenía el componente
    (copiados a mano de la hoja fechada 5/1/2026, ya desfasados del yaml vivo) por
    cifras derivadas de `price_cache.load_history` + `backtest.run_backtest` — el mismo
    motor reconciliado al 0.013% contra el extracto real de IB (Fase 3.1) que ya usa
    `comparacion_data`.

    Por fila de `MET_CASO` (ticker/fecha de apertura/aporte — el caso de estudio fijo,
    ver docstring de `MET_CASO`), con capital inicial = `inv` y DRIP bruto (`nra_rate=0`,
    igual que Greco: reside en EE. UU. y no sufre retención NRA):

      - `div`: total de distribuciones brutas cobradas hasta hoy (`gross_dividends_total`
        de la corrida CON DRIP — el dinero que de verdad entró, incluidas las
        distribuciones que generaron las acciones que el propio DRIP fue comprando).
      - `val`: valor de mercado de la posición hoy (`final_total_value` de la misma
        corrida) — las acciones originales más las que compró el DRIP.
      - `ult`: el último pago individual (`gross_dividend` del evento ex-dividendo más
        reciente), no un promedio.
      - `tot`: `inv + div` — la suma que hace la hoja de la clase y que esta sección
        entera existe para desmentir como "lo que ganaste" (double-counting: esos
        dividendos ya viven dentro de `val`).
      - `max`: techo teórico sin reinversión — acciones originales, ni una más,
        valoradas al precio de hoy (`portfolio_value` final de una segunda corrida SIN
        DRIP). Alimenta las matrices "Con DRIP"/"Sin DRIP" del componente (columna
        «Inversión Hoy»).
      - `divSin`: las distribuciones del contrafáctico — `gross_dividends_total` de la
        corrida SIN DRIP. **Es la única que puede aparecer en la fila «Sin DRIP»**: ahí
        las acciones extra nunca se compraron y por tanto nunca pagaron. Mezclar `div`
        (mundo con DRIP) con `max` (mundo sin DRIP) en la misma fila infló el total
        2.25x e invirtió el veredicto DRIP-vs-efectivo en NVDY y TSLY (auditoría
        2026-08-21). Regla: **una fila contrafáctica saca TODAS sus columnas de la misma
        corrida.**
      - `sinTotReal`: `final_total_value` de esa misma corrida sin DRIP — el total del
        contrafáctico según el motor. Existe para reconciliar contra la suma de columnas
        que hace el JS, que es una fuente independiente.

    `ROC_19A` sale de `logic.load_roc_19a()` (yaml vivo, refrescado semanalmente) en vez
    de la copia congelada — ya no hay drift entre lo que muestra el componente y
    `knowledge/roc_19a.yaml`.

    Devuelve `None` si algún ticker del caso de estudio no cargó historia (ni caché ni
    yfinance en vivo): con solo 5 filas fijas, una faltante deja la lección incompleta —
    a diferencia de `comparacion_data` (8 tickers, degrada individualmente), aquí no hay
    "universo parcial" que tenga sentido mostrar.

    Fase 3.3c (traspaso 2026-08-17) agrega los Bloques 3-5 del componente (Escalera,
    Payback, Tasa), que hasta ahora citaban la hoja congelada fechada 5/1/2026 aparte de
    `matriz`/`tot` — la desincronización entre ambos es justo lo que este traspaso cierra:

      - `escalera`: la anualización EXACTA (XIRR) de los aportes de `MET_CASO` contra
        `tot.val`, más la ventana media ponderada por capital que alimenta el ÷N ingenuo
        que el panel denuncia. `metodologia.html` § 9 «Anualizar bien» LEE estas claves;
        no calcula una segunda vez ni en otra convención.
      - `ratios`/`ratiosTot`: payback bruto/neto y retorno real por fila, derivados de
        `matriz` (nunca de un neto reusado — Regla 2 del contrato).
      - `nra`: los tres números de la frase "bruto → neto (retenido)" del panel Payback,
        todos derivados de `tot.div` y `tasaNra` — no pueden volver a desincronizarse.
      - `tasaNra`: 0.30, única fuente de la retención NRA simulada (cota superior, no el
        perfil fiscal de nadie — Decisión 4 del traspaso).
      - `tmtotEjemplo`: el ticker que ilustra la paradoja de `modal-tmtot` (ganó y a la
        vez perdió capital contra su Total inv.), o `None` si esta semana ninguno la
        ilustra. Ver `_tmtot_ejemplo`.
      - `paybackContraejemplo`: el ticker que ilustra "cobró y perdió" (mayor payback
        bruto entre los que tienen retorno negativo), o `None` si ninguno perdió esta
        semana — antes era CONY cableado a mano; con datos vivos dejó de ser válido en
        cuanto CONY dejó de perder. Ver `_payback_contraejemplo`.
      - `ymMedido`: lo que la app puede medir por ticker (yield realizado = dividendos
        cobrados sobre lo aportado; retorno de precio) — lo que publicó el emisor
        (`dr`/`sec`/`x`/`trc`/`tra` del panel Tasa) se queda literal y fechado en el
        componente, porque no hay fuente viva de 30-Day SEC Yield en el repo.
    """
    filas = []
    fuente: dict[str, str] = {}
    asof_candidatos = []
    ym_medido: dict[str, dict] = {}
    flujos_efectivo: list[tuple] = []
    # Escenarios fiscales SIMULADOS por el motor, uno por modo (Frente B, 2026-08-21).
    # Sustituyen a la reescala post-hoc que hacía el JS: `baseVal(bruto) = bruto*(1-tasa)`
    # aplicado una sola vez sobre el total de hoy. Esa aproximación no cobraba el interés
    # compuesto que el impuesto se lleva por el camino, y en el modo «roc» llegaba a dar
    # un total MAYOR que el escenario sin retención alguna.
    roc19a_yaml = logic.load_roc_19a()
    escenarios: dict[str, dict] = {m: {} for m in TRG_MODOS}

    for caso in MET_CASO:
        tk = caso["t"]
        try:
            hr = price_cache.load_history(tk)
        except Exception:
            return None
        if hr.history is None or hr.history.empty:
            return None

        r_con = backtest.run_backtest(tk, start_date=caso["start"], initial_capital=caso["inv"],
                                      drip=True, nra_rate=0.0, history=hr.history)
        r_sin = backtest.run_backtest(tk, start_date=caso["start"], initial_capital=caso["inv"],
                                      drip=False, nra_rate=0.0, history=hr.history)
        if r_con.daily.empty or r_sin.daily.empty:
            return None

        div = r_con.gross_dividends_total
        val = r_con.final_total_value
        pagos = r_con.daily[r_con.daily["gross_dividend"] > 0]
        ult = float(pagos["gross_dividend"].iloc[-1]) if len(pagos) else 0.0
        max_sin_drip = float(r_sin.daily["portfolio_value"].iloc[-1])
        # `div` es del mundo CON DRIP y la fila «Sin DRIP» NO puede usarlo: ahí las
        # acciones extra nunca se compraron, así que nunca pagaron esas distribuciones.
        # Medido: $165,780 (con DRIP) contra $67,307 (sin) — 2.46x. El nombre lleva el
        # mundo encima a propósito; el docstring ya declaraba el de `div` y aun así se
        # consumió en la fila equivocada.
        div_sin = r_sin.gross_dividends_total
        # Ancla de reconciliación: el total del contrafáctico según el propio motor, no
        # una suma de columnas rehecha en JS. Con `nra_rate=0` cierra la identidad
        # `portfolio_value + cash_accum`, y `cash_accum == gross_dividends_total`.
        sin_tot_real = r_sin.final_total_value

        # Flujos del contrafáctico «si los dividendos fueran efectivo», para su XIRR. Se
        # toman de `r_sin` (sin DRIP) porque ahí cada distribución SÍ salió del
        # instrumento y entró al bolsillo en su fecha — que es exactamente lo que la
        # fila describe. Fecha a fecha, sin promediar: el momento en que llegó cada peso
        # es la mitad de la respuesta, y un total anual lo borraría.
        pagos_sin = r_sin.daily[r_sin.daily["gross_dividend"] > 0]
        flujos_efectivo.append((caso["start"], -caso["inv"]))
        flujos_efectivo.extend(
            (fecha, float(monto)) for fecha, monto in pagos_sin["gross_dividend"].items()
        )

        filas.append({
            "t": tk, "ini": caso["ini"], "dr": caso["dr"], "inv": caso["inv"],
            "div": round(div, 2), "tot": round(caso["inv"] + div, 2),
            "val": round(val, 2), "ult": round(ult, 2), "max": round(max_sin_drip, 2),
            "divSin": round(div_sin, 2), "sinTotReal": round(sin_tot_real, 2),
        })
        fuente[tk] = hr.source
        if hr.cache_asof:
            asof_candidatos.append(hr.cache_asof)

        # Los 3 escenarios, simulados evento a evento con la MISMA política que usa la 3ª
        # gráfica (`_politica_fiscal`). «bruto» reutiliza las corridas de arriba en vez de
        # repetirlas: es literalmente el mismo caso (`nra_rate=0`, sin reembolso).
        for modo in TRG_MODOS:
            pol = _politica_fiscal(tk, modo, roc19a_yaml)
            if modo == "bruto":
                rc, rs = r_con, r_sin
            else:
                rc = backtest.run_backtest(tk, start_date=caso["start"],
                                           initial_capital=caso["inv"], drip=True,
                                           nra_rate=pol.rate, history=hr.history,
                                           roc_pct_by_year=pol.roc_pct_by_year)
                rs = backtest.run_backtest(tk, start_date=caso["start"],
                                           initial_capital=caso["inv"], drip=False,
                                           nra_rate=pol.rate, history=hr.history,
                                           roc_pct_by_year=pol.roc_pct_by_year)
            pv_con = float(rc.daily["portfolio_value"].iloc[-1])
            pv_sin = float(rs.daily["portfolio_value"].iloc[-1])
            escenarios[modo][tk] = {
                # «Inversión Hoy»: las acciones originales, ni una más, al precio de hoy.
                # Idéntica en los 3 modos —sin reinversión las acciones no se mueven— y
                # por eso es el ancla de la Regla 1: el impuesto no toca el capital.
                "max": round(pv_sin, 2),
                # Con DRIP: lo que volvió al fondo (distribuciones netas + reembolsos ya
                # cobrados, que también compraron acciones) y lo que vale hoy.
                "drip": round(rc.net_dividends_total + rc.roc_refund_total, 2),
                "dripHoy": round(pv_con - pv_sin, 2),
                # «Devuelto» con DRIP es SOLO lo aún por cobrar: lo ya reembolsado compró
                # acciones y vive dentro de «DRIP Hoy». Sumar ambos sería doble conteo.
                "devueltoCon": round(rc.roc_receivable_final, 2),
                "conTot": round(rc.final_total_value, 2),
                # Sin DRIP: el efectivo no compró nada, así que el reembolso cobrado sigue
                # siendo efectivo y se suma junto a lo pendiente.
                "divSin": round(rs.net_dividends_total, 2),
                "devueltoSin": round(rs.roc_refund_total + rs.roc_receivable_final, 2),
                "sinTot": round(rs.final_total_value, 2),
                # Impuesto NETO que acaba pagando el escenario, en el mundo con DRIP:
                # retenido menos lo que el ROC devuelve (cobrado o por cobrar). Única
                # fuente del contraste «ROC paga X en vez de Y» del copy — antes el JS lo
                # recalculaba con su propia aritmética post-hoc.
                "impuestoCon": round(rc.nra_withheld_total - rc.roc_refund_total
                                     - rc.roc_receivable_final, 2),
            }

        # Panel 5 (Tasa) parte en dos: `dr`/`sec`/`x`/`trc`/`tra` (YM en el componente)
        # siguen citando lo que publicó el emisor, literal y fechado — no hay fuente viva
        # de 30-Day SEC Yield en el repo. Pero lo que la app SÍ puede medir con su propio
        # motor (yield realizado = dividendos cobrados sobre lo aportado, y el retorno de
        # precio que lo explica) se deriva aquí, reusando `r_con`/`r_sin` de este mismo
        # bucle — no se corre el motor una tercera vez. `priceRetPct` es negativo cuando
        # el precio cayó (mismo signo que `backtest.price_return_pct`, sin invertir).
        ym_medido[tk] = {
            "realYieldPct": round(div / caso["inv"] * 100.0, 2),
            "priceRetPct": round(r_sin.price_return_pct, 2),
        }

    tot = {
        "inv": round(sum(f["inv"] for f in filas), 2),
        "div": round(sum(f["div"] for f in filas), 2),
        "val": round(sum(f["val"] for f in filas), 2),
        "ult": round(sum(f["ult"] for f in filas), 2),
        "divSin": round(sum(f["divSin"] for f in filas), 2),
        "sinTotReal": round(sum(f["sinTotReal"] for f in filas), 2),
    }
    tot["tot"] = round(tot["inv"] + tot["div"], 2)
    tot["totHoja"] = round(tot["tot"])

    # Panel 5 → renombrado a "quien retiene": única fuente de verdad de la retención
    # NRA simulada (Decisión 3 del traspaso 2026-08-17). El valor no cambia (0.30, la
    # cota superior de siempre) — solo deja de estar escrito una segunda vez en el JS.
    tasa_nra = 0.30

    # ---- Bloque 3 · la escalera del rendimiento ----
    # Anualización EXACTA por XIRR (decisión de Daniel, 2026-08-17: «prefiero que sea
    # exacto»). No hay N que elegir: `logic.xirr` resuelve la tasa que descuenta cada
    # aporte desde su propia fecha. El N=3 que vivía aquí no era medido sino redondeado a
    # mano, y sobre este mismo caso se desviaba 1.39 pp del exacto (+16.93%/año contra
    # +18.32%) — suficiente para mover el múltiplo con el que se contrasta el anuncio.
    #
    # Pero el N no desaparece de la pantalla, porque la lección del panel es justamente
    # «÷N no es anualizar»: para que el error sea concreto hace falta un N visible. El que
    # se muestra —y el que alimenta el ÷N ingenuo— es la ventana media ponderada por
    # capital aportado, medida, no inventada.
    asof = max(asof_candidatos) if asof_candidatos else datetime.date.today().isoformat()
    asof_ts = pd.Timestamp(asof)
    max_tot = round(sum(f["max"] for f in filas), 2)
    real_pct = (tot["val"] - tot["inv"]) / tot["inv"] * 100.0
    real_d = tot["val"] - tot["inv"]

    ventana_por_caso = [
        (caso["inv"], (asof_ts - pd.Timestamp(caso["start"])).days / 365.25)
        for caso in MET_CASO
    ]
    peso_total = sum(inv for inv, _ in ventana_por_caso)
    # Se redondea ANTES de dividir, no después: la ventana es un número que el panel
    # imprime («÷ 2.77 años») y el ÷N que muestra al lado tiene que ser esa división
    # exacta. Redondear al final dejaría en pantalla una cuenta que no cierra si el
    # lector la rehace a mano — el mismo tipo de descuadre que este panel denuncia.
    ventana_pond = round(sum(inv * anios for inv, anios in ventana_por_caso) / peso_total, 2)

    # El XIRR del portafolio con DRIP: cada aporte sale en su fecha, y el valor de mercado
    # de hoy entra como único flujo positivo. Los dividendos NO son flujo aquí — se
    # reinvirtieron, nunca tocaron el bolsillo, y su efecto ya vive dentro de `tot["val"]`.
    xirr_dec = logic.xirr(
        [(caso["start"], -caso["inv"]) for caso in MET_CASO] + [(asof, tot["val"])]
    )
    xirr_pct = None if xirr_dec is None else xirr_dec * 100.0

    naive_pct = real_pct / ventana_pond

    # El contrafáctico del efectivo se mide con SUS propias distribuciones (`divSin`),
    # no con las del mundo que reinvirtió. Usar `tot["div"]` aquí daba +267.2% donde el
    # real es +63.2% — y dejaba este total ($177,290) peleado con el que suman los flujos
    # del `efectivo_xirr` de tres líneas abajo ($78,817), que siempre salió de `r_sin`.
    efectivo_d = max_tot + tot["divSin"] - tot["inv"]
    efectivo_pct = efectivo_d / tot["inv"] * 100.0
    # El contrafáctico sí tiene flujos intermedios: cada distribución entró al bolsillo el
    # día que se pagó (`flujos_efectivo`, recolectado arriba de `r_sin`), y el valor final
    # es el de la posición que nunca reinvirtió.
    efectivo_xirr_dec = logic.xirr(flujos_efectivo + [(asof, max_tot)])
    efectivo_xirr_pct = None if efectivo_xirr_dec is None else efectivo_xirr_dec * 100.0

    anuncio_total, anuncio_anual = 1499.0, 499.0

    escalera = {
        "anuncioTotal": anuncio_total, "anuncioAnual": anuncio_anual,
        "realPct": round(real_pct, 2), "realD": round(real_d, 2),
        "xirrPct": round(xirr_pct, 2) if xirr_pct is not None else None,
        "ventanaPondAnos": ventana_pond,
        "naivePct": round(naive_pct, 2),
        "efectivoPct": round(efectivo_pct, 2), "efectivoD": round(efectivo_d, 2),
        "efectivoXirrPct": round(efectivo_xirr_pct, 2) if efectivo_xirr_pct is not None else None,
        "maxTot": max_tot,
        "multTot": round(anuncio_total / real_pct, 1) if real_pct > 0 else None,
        "multAnual": round(anuncio_anual / xirr_pct, 1) if xirr_pct and xirr_pct > 0 else None,
    }

    # ---- Bloque 4 · payback ≠ ganancia ----
    # `pbn` es cota superior sintética al 30% plano (Decisión 4): NO se conecta al
    # perfil fiscal del usuario, es la simulación de un NRA sobre la cartera de un
    # residente de EE. UU. Deriva de los BRUTOS de cada fila, nunca de un neto reusado
    # (Regla 2 del contrato: no mezclar bases).
    ratios = []
    for f in filas:
        pb = f["div"] / f["inv"]
        ret = (f["val"] - f["inv"]) / f["inv"] * 100.0
        ratios.append({
            "t": f["t"],
            "pb": round(pb, 4),
            "pbn": round(pb * (1 - tasa_nra), 4),
            "ret": round(ret, 2),
            "retD": round(f["val"] - f["inv"], 2),
            # Versión por fila del agregado que ya usa `modal-tmtot` arriba
            # (`mTmtotPerdida`): Total inv. − Valor mer. La base es **Total inv.**
            # (aportado + dividendos reinvertidos ≈ base de costo ajustada), NUNCA el
            # aportado a secas — mezclar las dos bases en la misma frase es la Regla 2
            # del contrato, y es lo que hace que esta cifra signifique algo fiscal.
            # Positiva = pérdida de capital no realizada; negativa = está por encima.
            "perdidaCapital": round((f["inv"] + f["div"]) - f["val"], 2),
        })

    pb_tot = tot["div"] / tot["inv"]
    ret_tot = (tot["val"] - tot["inv"]) / tot["inv"] * 100.0
    ratios_tot = {
        "pb": round(pb_tot, 4),
        "pbn": round(pb_tot * (1 - tasa_nra), 4),
        "ret": round(ret_tot, 2),
        "retD": round(tot["val"] - tot["inv"], 2),
    }

    # Los tres números de `tmPaybackNra` salen todos de aquí — nunca vuelven a poder
    # desincronizarse (el bug del traspaso: un TOT.div vivo concatenado con dos mitades
    # de la hoja congelada, en la misma oración).
    nra = {
        "divBruto": tot["div"],
        "divNeto": round(tot["div"] * (1 - tasa_nra), 2),
        "retenido": round(tot["div"] * tasa_nra, 2),
    }
    payback_contraejemplo = _payback_contraejemplo(ratios)
    tmtot_ejemplo = _tmtot_ejemplo(ratios)

    roc19a_raw = logic.load_roc_19a()
    roc19a = {}
    roc19a_asof = []
    for caso in MET_CASO:
        tk = caso["t"]
        info = roc19a_raw.get(tk)
        weighted = info.get("weighted_pct") if info else None
        try:
            roc19a[tk] = max(0.0, min(1.0, float(weighted) / 100.0)) if weighted is not None else 0.0
        except (TypeError, ValueError):
            roc19a[tk] = 0.0
        if info and info.get("asof"):
            roc19a_asof.append(str(info["asof"]))

    degradado = sorted(tk for tk, s in fuente.items() if s != "cache")

    # Totales de cartera por escenario: la suma de las 5 filas YA redondeadas, nunca un
    # agregado aparte (hallazgo L1 del traspaso 2026-08-03 — si no, la columna no cuadra
    # cuando el lector la suma a mano).
    escenarios_tot = {
        modo: {
            k: round(sum(v[k] for v in filas_modo.values()), 2)
            for k in ("max", "drip", "dripHoy", "devueltoCon", "conTot",
                      "divSin", "devueltoSin", "sinTot", "impuestoCon")
        }
        for modo, filas_modo in escenarios.items()
    }

    return {
        "matriz": filas,
        "tot": tot,
        "escenarios": escenarios,
        "escenariosTot": escenarios_tot,
        "roc19a": roc19a,
        "roc19aAsof": max(roc19a_asof) if roc19a_asof else None,
        "asof": asof,
        "fuente": fuente,
        "degradado": degradado,
        "tasaNra": tasa_nra,
        "escalera": escalera,
        "ratios": ratios,
        "ratiosTot": ratios_tot,
        "nra": nra,
        "paybackContraejemplo": payback_contraejemplo,
        "tmtotEjemplo": tmtot_ejemplo,
        "ymMedido": ym_medido,
    }


# Combinaciones de la gráfica de escenarios: los 3 modos fiscales de `TRG_MODOS` cruzados
# con reinvertir o no. Seis series, no seis fórmulas — ver `metodo_serie_data`.
MET_SERIE_DRIP = ("con", "sin")


def _roc_pct_by_year(ticker: str, roc19a: dict) -> dict[int, float]:
    """%ROC (0-100) por año calendario para el reembolso 1042-S de `backtest.run_backtest`.

    La reclasificación del bróker opera por AÑO FISCAL, así que cada año usa el promedio
    de los avisos 19(a) publicados ESE año — misma convención que
    `logic.estimate_roc_refund_by_year`, que es quien ya la fijó. Los años sin avisos en la
    ventana caen al ponderado del fondo (`weighted_pct`), y un ticker sin avisos ningunos
    devuelve `{}`: sin escudo que reclamar, la retención plana se queda como está.

    **Los años ANTERIORES a la ventana no se extrapolan** (y eso mueve cifras). El relleno
    con el ponderado cubre solo los huecos DENTRO del rango de avisos publicados; un año
    previo al primer aviso no aparece en el dict, así que el motor le aplica 0% de ROC:
    retiene el 30% completo y no devuelve nada. Es un piso conservador, no una medida — y
    difiere de lo que hacía `_tasa_efectiva_neta`, que aplicaba el ponderado a TODO el
    horizonte. Material hoy en dos fondos del universo, cuyos avisos empiezan mucho después
    de su incepción: TSLY (incep. nov-2022, avisos desde may-2025) y CONY (incep. ago-2023,
    avisos desde feb-2025). NVDY y MSTY tienen la ventana cubierta desde su primer año.

    Que el alcance sea el mismo en todas las vistas es lo que exige la Regla 3; que ese
    alcance se DECLARE en el copy es lo que exige la Regla 2. Ampliarlo (extrapolar hacia
    atrás) es una decisión de producto abierta, no un arreglo: movería también las cifras
    ya desplegadas de «La matriz».
    """
    info = roc19a.get(ticker) or {}
    por_anio: dict[int, list[float]] = {}
    for p in (info.get("per_distribution") or []):
        try:
            por_anio.setdefault(pd.Timestamp(p["date"]).year, []).append(float(p["roc_pct"]))
        except (KeyError, TypeError, ValueError):
            continue
    try:
        ponderado = float(info.get("weighted_pct"))
    except (TypeError, ValueError):
        ponderado = 0.0
    if not por_anio and ponderado <= 0:
        return {}
    anios = list(por_anio) or []
    promedios = {a: sum(v) / len(v) for a, v in por_anio.items()}
    # Los años del histórico que no tienen avisos propios heredan el ponderado, para que
    # un hueco en la publicación no se lea como «ese año no hubo ROC».
    if anios and ponderado > 0:
        for a in range(min(anios), max(anios) + 1):
            promedios.setdefault(a, ponderado)
    return promedios


class _PoliticaFiscal(typing.NamedTuple):
    """Cómo se grava un escenario. `rate` es la retención AL COBRO; `roc_pct_by_year` es
    el escudo que vuelve DESPUÉS, vía 1042-S. Los dos juntos definen base Y momento
    (Regla 2 del contrato) — por eso viajan como una sola cosa y no como dos parámetros
    sueltos que alguien pueda combinar mal."""
    rate: float
    roc_pct_by_year: dict


def _politica_fiscal(ticker: str, modo: str, roc19a: dict,
                     base_rate: float = _CMP_FLAT_RATE) -> _PoliticaFiscal:
    """Política fiscal de un escenario simulado, por modo. **Fuente única de los 3
    escenarios en las CUATRO vistas que los dibujan**: las tablas de «La matriz»
    (`metodo_data`), su 3ª gráfica (`metodo_serie_data`), «Comparación · Simulación»
    (`comparacion_data`) y «Comparación · Real» (`trg_real_data`). Una sola política, un
    solo modelo — Regla 3 del contrato (objeto fiscal único) aplicada al escudo ROC.

    `base_rate` es la retención al cobro antes del escudo. Por defecto el 30% de los
    paneles pedagógicos; «Comparación · Real» pasa la del país declarado por el cliente
    (`ui.estado.perfil_fiscal()`), que con tratado puede ser 10%. El ROC no depende de la
    tasa —es una propiedad de la distribución, no del inversor—, así que solo entra
    `rate`: por eso el parámetro se agregó aquí y no en `_roc_pct_by_year`.

    Se llamaba `_met_politica` mientras solo servía a «La matriz»; el prefijo se cayó al
    migrar «Comparación · Simulación», y «Comparación · Real» entró el mismo día
    (2026-08-21). Con eso ya no queda en el repo ninguna vista que meta el escudo DENTRO
    de la tasa (`_tasa_efectiva_neta`, hoy solo cifra reportada).
    Meter el escudo en la tasa asume que aplica al cobro —el dinero nunca sale del fondo—;
    aquí «roc» retiene el 30% completo al cobro y devuelve el ROC más tarde, que es lo que
    de verdad ocurre. No son equivalentes: +6.3% en la cartera del caso de estudio con DRIP
    y con el signo cambiando por fondo (MSTY +28.9%, NFLY −1.8%); en el universo de
    «Comparación», de −18.7 pp (TSLY) a +28.0 pp (MSTY). Ver `backtest.run_backtest`.

    **Alcance: completo.** Las cuatro vistas que dibujan escenarios fiscales pasan por
    aquí. El otro motor —`logic.build_drip_comparison_series` /
    `build_roc_aware_withholding` / `build_total_return_series`, que metía el escudo dentro
    de la tasa— se quedó sin consumidor vivo el 2026-08-21 y se borró el mismo día. El guard
    que impide reintroducirlo sigue puesto (`test_un_solo_motor_fiscal.py`).
    """
    if modo == "bruto":
        return _PoliticaFiscal(0.0, {})
    if modo == "plano":
        return _PoliticaFiscal(base_rate, {})
    return _PoliticaFiscal(base_rate, _roc_pct_by_year(ticker, roc19a))


def metodo_serie_data() -> dict | None:
    """JSON para la tercera matriz de «Método tradicional · La matriz»: las 6 curvas de
    la cartera del caso de estudio en el tiempo (eje X = mes, eje Y = dólares).

    Seis = los 3 escenarios fiscales de `TRG_MODOS` («Sin NRA» / «Con NRA · ROC 19a» /
    «Con NRA · 30%») cruzados con reinvertir las distribuciones o cobrarlas en efectivo.
    Cada curva es la SUMA de las 5 posiciones de `MET_CASO` valoradas al cierre de cada
    mes; cada posición sale de `backtest.run_backtest(..., history=...)` sobre el caché
    de precio — ninguna llamada a yfinance en runtime, mismo motor reconciliado al 0.013%
    contra el extracto real de IB que ya alimentan `metodo_data` y `comparacion_data`.

    **Decisión metodológica.** Los 3 escenarios se SIMULAN evento a evento con
    `_politica_fiscal` —el objeto fiscal único, compartido con las tablas y con
    «Comparación · Simulación»— y el motor la aplica al cobrar cada distribución. Con DRIP
    eso significa que un escenario retenido reinvierte MENOS dinero, compra MENOS acciones
    y por lo tanto COMPONE distinto: el efecto fiscal es multiplicativo en el tiempo, no un
    descuento al final.

    Las tablas de la Matriz 2 leen esa MISMA simulación desde el PR #59. Hasta entonces
    reescalaban en JS el total bruto por `(1 - tasaNra)` una sola vez, al final (`baseVal`),
    y la misma pantalla llegó a mostrar $177,289 y $78,816 para la misma cifra. Hoy las seis
    celdas cuadran con las seis curvas, y hay un test cruzado que lo exige
    (`test_contrafactico_sin_drip.py::TestReconciliacionVistas`) — no una nota al pie que
    declare la divergencia.

    **Base y momento de cada serie** (Regla 2, otra vez): «Sin NRA» es BRUTA (nadie
    retiene); «Con NRA · ROC 19a» y «Con NRA · 30%» son NETAS con el 30% completo tomado
    AL COBRO de cada distribución. En «ROC 19a» la porción que el aviso 19(a) reclasifica
    vuelve DESPUÉS, en efectivo, cuando llega el 1042-S (`roc_pct_by_year` +
    `refund_month` en `run_backtest`): se devenga como cuenta por cobrar en el momento del
    cobro y se paga en marzo del año siguiente. Por eso las curvas «ROC 19a» no son las de
    «30%» desplazadas por un factor — el dinero estuvo fuera del mercado meses, y en un
    fondo que cae, estar fuera a veces protege.

    **Capital aportado** (Regla 1): `capital` es UNA sola serie, idéntica en los 6
    escenarios — la retención mueve el bucket impuesto, jamás lo que salió del bolsillo.
    Es escalonada, no plana, porque las 5 posiciones del caso de estudio se abrieron en
    fechas distintas (14 meses entre la primera y la última): cada escalón es un aporte
    nuevo entrando, no rendimiento. Sin esa referencia, el salto de $13,599 del día que
    entra MSTY se leería como una ganancia.

    Devuelve `None` con el mismo criterio que `metodo_data`: si alguno de los 5 tickers
    no cargó historia, la lección queda coja y no hay «cartera parcial» que dibujar.
    """
    historias: dict[str, pd.DataFrame] = {}
    fuente: dict[str, str] = {}
    asof_candidatos: list[str] = []
    for caso in MET_CASO:
        tk = caso["t"]
        try:
            hr = price_cache.load_history(tk)
        except Exception:
            return None
        if hr.history is None or hr.history.empty:
            return None
        historias[tk] = hr.history.sort_index()
        fuente[tk] = hr.source
        if hr.cache_asof:
            asof_candidatos.append(hr.cache_asof)

    # El origen del eje X es la apertura MÁS TEMPRANA del caso de estudio, no la más
    # tardía: a diferencia de `comparacion_data` —que renormaliza cada serie contra su
    # propia incepción y necesita una ventana común para que los porcentajes sean
    # comparables— aquí el eje son dólares de UNA cartera, y recortar el arranque
    # borraría 14 meses de historia que sí ocurrieron.
    inicios = {c["t"]: pd.Timestamp(c["start"]) for c in MET_CASO}
    primero = min(inicios.values())
    origen = [int(primero.year), int(primero.month) - 1]

    def _mes_de(ts) -> int:
        return (int(ts.year) - origen[0]) * 12 + (int(ts.month) - 1 - origen[1])

    incep = {tk: _mes_de(ts) for tk, ts in inicios.items()}
    roc19a = logic.load_roc_19a()

    # Una corrida por (ticker, modo, drip) = 5 x 3 x 2 = 30. Se guardan por ticker y
    # después se suman: sumar carteras exige alinear en el MISMO mes, y cada ticker
    # arranca en el suyo.
    porticker: dict = {modo: {d: {} for d in MET_SERIE_DRIP} for modo in TRG_MODOS}
    tasa_efectiva: dict = {modo: {} for modo in TRG_MODOS}
    last = 0
    for caso in MET_CASO:
        tk, history = caso["t"], historias[caso["t"]]
        for modo in TRG_MODOS:
            pol = _politica_fiscal(tk, modo, roc19a)
            # La tasa que se REPORTA es la neta de reembolso —lo que el inversor acaba
            # pagando— aunque el motor retenga el 30% y devuelva después. Es la cifra que
            # la nota al pie usa para decir «8.7%–17.6% según el fondo».
            tasa_efectiva[modo][tk] = round(_tasa_efectiva_neta(tk, modo, roc19a) * 100.0, 2)
            for drip in MET_SERIE_DRIP:
                r = backtest.run_backtest(tk, start_date=caso["start"],
                                          initial_capital=caso["inv"], drip=(drip == "con"),
                                          nra_rate=pol.rate, history=history,
                                          roc_pct_by_year=pol.roc_pct_by_year)
                if r.daily.empty:
                    return None
                # `total_value` = valor de mercado de las acciones + efectivo acumulado.
                # Es la única columna que se puede sumar entre escenarios sin doble
                # conteo: con DRIP el dividendo reinvertido YA vive dentro de las
                # acciones, y sin DRIP vive en el efectivo — nunca en las dos a la vez.
                valores = _mensualizar_desde(r.daily["total_value"], origen, decimales=2)
                porticker[modo][drip][tk] = valores
                if valores:
                    last = max(last, max(int(m) for m in valores))

    def _cartera(por_tk: dict) -> dict:
        """Suma las 5 posiciones mes a mes. Antes de su apertura una posición aporta 0
        (todavía no existe); después, si a un mes le falta cierre, arrastra el último
        conocido en vez de desaparecer y hundir el total de la cartera un mes."""
        out, previo = {}, {tk: None for tk in por_tk}
        for m in range(0, last + 1):
            total, vivos = 0.0, 0
            for tk, valores in por_tk.items():
                if m < incep[tk]:
                    continue
                v = valores.get(str(m))
                if v is None:
                    v = previo[tk]
                if v is None:
                    continue
                previo[tk] = v
                total += v
                vivos += 1
            if vivos:
                out[str(m)] = round(total, 2)
        return out

    serie = {modo: {d: _cartera(porticker[modo][d]) for d in MET_SERIE_DRIP}
             for modo in TRG_MODOS}

    # Regla 1 del contrato fiscal: el capital aportado es invariante. UNA serie para los
    # 6 escenarios, sin `modo` ni `drip` de por medio — si algún día aparece un `capital`
    # por escenario, es un bug por definición.
    capital = {}
    for m in range(0, last + 1):
        acum = sum(c["inv"] for c in MET_CASO if incep[c["t"]] <= m)
        if acum:
            capital[str(m)] = round(acum, 2)

    asof = max(asof_candidatos) if asof_candidatos else datetime.date.today().isoformat()
    return {
        "origen": origen,
        "last": last,
        "incep": incep,
        "serie": serie,
        "capital": capital,
        "invTotal": round(sum(c["inv"] for c in MET_CASO), 2),
        "tasaPlanaPct": round(_CMP_FLAT_RATE * 100.0),
        "tasaEfectivaPct": tasa_efectiva,
        "asof": asof,
        "fuente": fuente,
        "degradado": sorted(tk for tk, s in fuente.items() if s != "cache"),
    }


def _xirr_cartera(resultados: dict, tickers: list) -> float | None:
    """Retorno anual EXACTO de las posiciones incluidas, como una sola cartera.

    Decisión de Daniel (2026-08-17): «prefiero que sea exacto». No hay un N que elegir —
    `logic.xirr` resuelve la tasa que descuenta los flujos reales en sus fechas reales.
    Sobre el caso de estudio, elegir N movía la respuesta 1.39 pp (N=3 daba +16.93%/año
    contra el exacto +18.32%), y con un CSV real —compras repartidas en decenas de
    fechas— la arbitrariedad solo crece.

    Los flujos salen de `stats["cash_flows_dated"]`, que `analyze_portfolio` construye
    fila por fila. **No se reclasifican aquí**: separar aporte propio de compra por DRIP
    mirando `Action` es imposible sin decidir por bróker (IB rotula las dos `Buy`,
    Schwab usa `Reinvest Shares`), y decidir por bróker es lo que ya duplicó una
    retención antes. Se suma el valor de mercado de hoy como flujo final positivo, igual
    que hace `analyze_portfolio` para `irr_anual`.

    `None` si ninguna posición aporta flujos utilizables — la escalera se dibuja sin el
    peldaño anualizado antes que con un número inventado.
    """
    flujos = []
    hoy = pd.Timestamp(datetime.date.today())
    for tk in tickers:
        stats = (resultados or {}).get(tk) or {}
        flujos.extend(stats.get("cash_flows_dated") or [])
        valor = _f(stats.get("market_value"))
        # `if valor:` no basta: NaN es truthy. Colar un NaN aquí sería peor que omitirlo
        # —`logic.xirr` lo descarta al limpiar, y el resultado sería la TIR de los aportes
        # SIN valor final, o sea un −99% que parece medido.
        if math.isfinite(valor) and valor:
            flujos.append((hoy, valor))
    tasa = logic.xirr(flujos)
    return None if tasa is None else tasa * 100.0


def metodo_real_data(resultados: dict, df, tasa_pct, pais: str | None = None) -> dict | None:
    """JSON para `ui/componentes/metodo_real.html` («Matriz 2» · las cuatro lecciones de
    «La matriz» aplicadas al portafolio REAL del CSV cargado — traspaso 2026-08-17).

    No calcula nada fiscal ni de mercado por su cuenta (Regla 3, `specs/
    roc-nra-invariants.md`): cada fila reusa por IDENTIDAD `cashflow_data`/
    `verificar_identidades`, exactamente lo que ya usan Cash flow y Hoja Excel para el
    ticker de la ruta — aquí solo se itera sobre TODOS los tickers del portafolio.

    **La trampa del traspaso.** En «La matriz» el DRIP fue TOTAL, así que
    `Valor mer. − Inversión` ya es el retorno real. Aquí el DRIP es PARCIAL — parte de
    las distribuciones se cobró en efectivo y nunca volvió a comprar acciones —, así que
    la única fórmula válida es `Retorno total real = Valor de mercado + efectivo cobrado
    − Capital aportado`. `cashflow_data` ya la implementa así en su campo `RESULTADO`
    (`CAPITAL_ACTUAL − POCKET`, con `CAPITAL_ACTUAL = VALOR_HOY + CASH`, y `CASH` derivado
    de `NETO − DRIP` — nunca de `dividends_collected_cash` crudo, que no está en la misma
    base en los dos brokers, logic.py:1490-1500). Reusarlo aquí es lo que impide que el
    atajo de «La matriz» se cuele.

    `tasa_pct`/`pais` llegan de `ui.estado.tasa_y_pais()` — `tasa_pct ==
    logic.RATE_UNDECLARED` cuando el cliente no declaró residencia (Decisión 4 del
    traspaso: «sin declarar» no es 0%, no se estima devolución ni se muestra payback
    neto). `tax_summaries` se re-deriva con esa tasa vía `logic.build_tax_summaries` —
    mismo patrón que `ui.vistas._tax_summary`, sin recalcular el concepto.

    Un ticker se EXCLUYE de la matriz (no se calla en silencio: va a `excluidos`) si
    `verificar_identidades` no reconcilia — las mismas cifras que Cash flow/Hoja Excel ya
    rechazan mostrar por ticker individual, aquí no pueden colarse solo porque la vista
    agrega varios a la vez.

    Devuelve `None` si ningún ticker del portafolio tiene datos analizables
    (`_tiene_datos`) — sin al menos una fila la sección no tiene qué mostrar.
    """
    tax_summaries = logic.build_tax_summaries(resultados, base_rate_pct=tasa_pct, country=pais)
    pais_declarado = tasa_pct != logic.RATE_UNDECLARED
    instrumentos = logic.load_instruments()

    filas, ratios, excluidos = [], [], []
    con_ficha, sin_ficha = [], []
    ym_medido: dict[str, dict] = {}
    tot_inv = tot_div = tot_val = tot_retD = tot_impuesto = tot_neto_decl = 0.0

    for tk, stats in sorted((resultados or {}).items()):
        if not _tiene_datos(stats):
            continue
        tax = tax_summaries.get(tk) or {}
        try:
            cf = cashflow_data(stats, tk, tax_summary=tax)
        except DatosIncompletos:
            continue
        fallos = verificar_identidades(cf, stats)
        if fallos:
            excluidos.append({"t": tk, "motivo": fallos[0]})
            continue

        pocket, bruto, valor_hoy = cf["POCKET"], cf["BRUTO"], cf["VALOR_HOY"]
        ret_d = cf["RESULTADO"]

        # Una cifra no finita NO puede llegar a un total. Si el precio de hoy no se pudo
        # obtener (yfinance degradado devuelve filas con `Close` = NaN, visto el
        # 2026-08-18), `market_value` sale NaN y contamina por aritmética TODOS los
        # agregados: NaN + x = NaN, y como toda comparación con NaN es falsa, la posición
        # tampoco aparecería como perdedora ni ganadora — se volvería invisible sin que
        # nadie lo note. Se excluye declarándolo, que es la misma regla que aplica
        # `verificar_identidades`: antes de mostrar algo que miente, no mostrarlo.
        if not all(math.isfinite(_f(v)) for v in (pocket, bruto, valor_hoy, ret_d)):
            excluidos.append({
                "t": tk,
                "motivo": "sin precio de mercado utilizable hoy — no se puede valorar la posición",
            })
            continue

        primera = None
        if df is not None and "Ticker" in df.columns:
            serie = df.loc[df["Ticker"] == tk, "Date"]
            primera = serie.min() if len(serie) else None
        inicio = "" if primera is None or primera != primera else primera.strftime("%Y-%m-%d")

        filas.append({
            "t": tk, "ini": inicio,
            "inv": pocket, "div": bruto, "tot": round(pocket + bruto, 2), "val": valor_hoy,
            "convencion": stats.get("dividend_base_convention"),
        })
        tot_inv += pocket; tot_div += bruto; tot_val += valor_hoy; tot_retD += ret_d
        tot_impuesto += cf["IMPUESTO"]

        pb = (bruto / pocket) if pocket > 0 else 0.0
        ret_pct = (ret_d / pocket * 100.0) if pocket > 0 else 0.0
        fila_ratio = {"t": tk, "pb": round(pb, 4), "ret": round(ret_pct, 2), "retD": round(ret_d, 2)}
        if pais_declarado and pocket > 0:
            # `net_estimated` = lo que en definitiva se queda el fisco tras la
            # reclasificación ROC, YA calculado a la tasa del perfil del usuario
            # (`logic.build_tax_summary`, Regla 4: usa el ROC% como palanca fiscal, no
            # como medida de daño al NAV) — nunca el 30% plano de «La matriz».
            neto_decl = bruto - _f(tax.get("net_estimated"), cf["IMPUESTO"])
            fila_ratio["pbn"] = round(neto_decl / pocket, 4)
            tot_neto_decl += neto_decl
        ratios.append(fila_ratio)

        info = instrumentos.get(str(tk).upper())
        (con_ficha if info else sin_ficha).append(tk)
        # `price_cagr_recent` (ventana reciente) sobre `price_cagr` (histórico completo)
        # cuando ambos existen — mismo criterio que `salud_nav_data`. `None` explícito
        # (no 0) cuando `analyze_portfolio` no pudo calcular ninguno de los dos.
        cagr_recent = stats.get("price_cagr_recent")
        precio_cagr = cagr_recent if cagr_recent is not None else stats.get("price_cagr")
        ym_medido[tk] = {
            "yieldRealizadoPct": round(pb * 100.0, 2),
            "precioCagrPct": round(precio_cagr, 2) if precio_cagr is not None else None,
            "conFicha": bool(info),
        }

    if not filas:
        return None

    tot = {"inv": round(tot_inv, 2), "div": round(tot_div, 2),
           "tot": round(tot_inv + tot_div, 2), "val": round(tot_val, 2)}
    ret_tot_pct = (tot_retD / tot_inv * 100.0) if tot_inv > 0 else 0.0
    ratios_tot = {"pb": round(tot_div / tot_inv, 4) if tot_inv > 0 else 0.0,
                  "ret": round(ret_tot_pct, 2), "retD": round(tot_retD, 2)}
    if pais_declarado and tot_inv > 0:
        ratios_tot["pbn"] = round(tot_neto_decl / tot_inv, 4)

    payback_contraejemplo = _payback_contraejemplo(ratios)

    xirr_pct = _xirr_cartera(resultados, [f["t"] for f in filas])
    escalera = None
    if tot_inv > 0:
        hoja_pct = tot_div / tot_inv * 100.0
        escalera = {
            "hojaPct": round(hoja_pct, 2),
            "realPct": round(ret_tot_pct, 2), "realD": round(tot_retD, 2),
            # El número correcto, sin plazo inventado. `None` cuando no se pudo
            # resolver: la vista omite el peldaño anualizado en vez de rellenarlo.
            "xirrPct": round(xirr_pct, 2) if xirr_pct is not None else None,
            # Peldaño 3 de la lección («si los dividendos fueran efectivo» — el
            # contrafáctico sin reinvertir) necesita el valor de mercado de SOLO las
            # acciones compradas con capital propio, valoradas hoy. En «La matriz» sale
            # de una segunda corrida de `backtest.run_backtest(drip=False)` porque el
            # caso de estudio es una compra única en una fecha única; el CSV real tiene
            # compras fraccionadas en N fechas por ticker y ni `analyze_portfolio` ni
            # `cashflow_data` guardan «valor hoy de las acciones NO-DRIP» por separado —
            # aislarlo exigiría un motor de simulación nuevo por posición, que el
            # traspaso prohíbe explícitamente («Ni un cálculo nuevo»). Se deja declarado
            # como no disponible en vez de inventarlo o aproximarlo — ver «Traspaso de
            # vuelta».
            "efectivoDisponible": False,
        }

    nra = {
        "divBruto": round(tot_div, 2),
        "retenidoReal": round(tot_impuesto, 2),
        "paisDeclarado": pais_declarado,
        "pais": pais,
        "tasaPct": tasa_pct if pais_declarado else None,
        "netoDeclarado": round(tot_neto_decl, 2) if pais_declarado else None,
    }

    return {
        "matriz": filas,
        "tot": tot,
        "ratios": ratios,
        "ratiosTot": ratios_tot,
        "paybackContraejemplo": payback_contraejemplo,
        "escalera": escalera,
        "nra": nra,
        "ymMedido": ym_medido,
        "conFicha": con_ficha,
        "sinFicha": sin_ficha,
        "excluidos": excluidos,
        "paisDeclarado": pais_declarado,
        "asof": datetime.date.today().isoformat(),
    }
