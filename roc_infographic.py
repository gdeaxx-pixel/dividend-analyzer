"""Infografía ROC dinámica (IYG "Architectural Authority") para incrustar en la app.

`roc_infographic_html(stats, ticker)` toma el dict de resultados de UN ticker
(de `analyze_portfolio`) y devuelve el HTML del póster lleno con sus cifras reales
+ el "waffle" pintado según su % de ROC. Se muestra solo para fondos con ROC
(YieldMax-tipo) en pérdida — el gate vive en app.py.

100% aditivo: NO toca la lógica de cálculo, solo LEE resultados y los presenta.
Reversible: borrar este archivo + la plantilla + el bloque en app.py (o el flag).
"""
import os

_TPL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roc_infographic_template.html")
try:
    with open(_TPL_PATH, encoding="utf-8") as _f:
        _TEMPLATE = _f.read()
except Exception:
    _TEMPLATE = ""


def roc_infographic_html(stats: dict, ticker: str) -> str:
    """Devuelve el HTML de la infografía para `ticker` con los datos de `stats`.
    Devuelve "" si faltan datos o la plantilla no cargó (el caller hace fallback)."""
    if not _TEMPLATE or not isinstance(stats, dict):
        return ""
    try:
        pocket = float(stats["pocket_investment"])
        dist = float(stats["total_dividends"])
        roc = float(stats["roc_accumulated"])
        roc_pct = float(stats["roc_percent"])
        mv = float(stats["market_value"])
    except (KeyError, TypeError, ValueError):
        return ""
    if pocket <= 0 or dist <= 0:
        return ""
    drip = float(stats.get("dividends_collected_drip") or 0)
    cash = float(stats.get("dividends_collected_cash") or 0)

    roc = max(0.0, min(roc, dist))           # blindaje gross/net: el ROC no excede las distribuciones
    roc_pct = max(0.0, min(roc_pct, 100.0))
    inc = dist - roc
    inc_pct = 100.0 - roc_pct
    teq = mv + cash
    res = (teq - pocket) / pocket * 100.0
    n_blue = max(0, min(100, round(inc_pct)))

    def D(v):
        return f"${round(v):,}"

    res_s = f"{'−' if res < 0 else '+'}{abs(round(res))}%"

    # Pass 1: tokens crudos del template -> sentinelas (evita colisiones de substring)
    pass1 = [
        ("Retorno de Capital &middot; Ejemplo real: MSTY", "@KICK@"),
        ("Pero 3 de cada 4 dólares ya eran tuyos.", "@LEDE@"),
        ("$256", "@DIST@"), ("$191", "@ROC@"), ("$605", "@POCKET@"), ("$180", "@TEQ@"),
        ("$220", "@DRIP@"), ("$65", "@INC@"), ("$36", "@CASH@"),
        ("75%", "@RP@"), ("25%", "@IP@"), ("−70%", "@RES@"), ("i >= 75", "i >= @WAFFLE@"),
    ]
    h = _TEMPLATE
    for a, b in pass1:
        h = h.replace(a, b)
    # Pass 2: sentinelas -> valores reales
    pass2 = {
        "@KICK@": f"Retorno de Capital &middot; Tu posición: {ticker}",
        "@LEDE@": f"Pero ~{round(roc_pct)}% ya era tu propio dinero.",
        "@DIST@": D(dist), "@ROC@": D(roc), "@POCKET@": D(pocket), "@TEQ@": D(teq),
        "@DRIP@": D(drip), "@INC@": D(inc), "@CASH@": D(cash),
        "@RP@": f"{round(roc_pct)}%", "@IP@": f"{round(inc_pct)}%",
        "@RES@": res_s, "@WAFFLE@": str(100 - n_blue),
    }
    for a, b in pass2.items():
        h = h.replace(a, b)
    return h
