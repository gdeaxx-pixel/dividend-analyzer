"""`ui.adapters.metodo_serie_data` — la 3ª matriz de «Método tradicional · La matriz».

Seis curvas de cartera en el tiempo (3 escenarios fiscales x reinvertir/cobrar). Mismo
criterio que `test_metodo_data.py`: se protegen FORMA e INVARIANTES, nunca un número
puntual — la función corre hasta hoy y sus cifras se mueven cada semana por diseño.

Los dos tests que de verdad muerden son el de reconciliación (`bruto`/con DRIP tiene que
dar exactamente el mismo dólar que `metodo_data()["tot"]["val"]`, porque es la misma
corrida del mismo motor) y el de metodología (`plano` tiene que quedar por DEBAJO de lo
que predice la reescala de un paso que usan las tablas — si alguien cambia la simulación
por ese atajo, ese test cae).
"""
import json
import os
import re

import pytest

import backtest
import logic
import price_cache
from ui.adapters import (MET_CASO, MET_SERIE_DRIP, TRG_MODOS, metodo_data,
                         metodo_serie_data)

BASE = os.path.dirname(__file__)


@pytest.fixture(scope="module")
def serie():
    d = metodo_serie_data()
    if d is None:
        pytest.skip("sin historia de precios para el caso de estudio (ni caché ni red)")
    return d


@pytest.fixture(scope="module")
def datos():
    d = metodo_data()
    if d is None:
        pytest.skip("sin historia de precios para el caso de estudio (ni caché ni red)")
    return d


@pytest.fixture(scope="module")
def ultimo(serie):
    return str(serie["last"])


# ── forma ───────────────────────────────────────────────────────────────────────────────

def test_estan_las_seis_combinaciones(serie):
    assert set(serie["serie"]) == set(TRG_MODOS)
    for modo in TRG_MODOS:
        assert set(serie["serie"][modo]) == set(MET_SERIE_DRIP)
    combos = [(m, d) for m in TRG_MODOS for d in MET_SERIE_DRIP]
    assert len(combos) == 6, "la gráfica se llama «los seis escenarios» por algo"


def test_los_meses_son_contiguos_desde_cero(serie):
    """Un hueco en el medio dibujaría una cartera que desaparece un mes. `_cartera`
    arrastra el último cierre conocido justamente para que no pueda pasar."""
    esperados = [str(m) for m in range(0, serie["last"] + 1)]
    for modo in TRG_MODOS:
        for drip in MET_SERIE_DRIP:
            assert sorted(serie["serie"][modo][drip], key=int) == esperados, f"{modo}/{drip}"


def test_todas_las_curvas_son_positivas(serie):
    for modo in TRG_MODOS:
        for drip in MET_SERIE_DRIP:
            for m, v in serie["serie"][modo][drip].items():
                assert v > 0, f"{modo}/{drip} mes {m} = {v}"


def test_el_origen_es_la_apertura_mas_temprana_del_caso_de_estudio(serie):
    """No la más tardía: aquí el eje son dólares de UNA cartera, y arrancar en la ventana
    común (como sí hace `comparacion_data`, que compara porcentajes) borraría los 14
    meses que TSLY, NVDY y CONY ya llevaban corriendo antes de que entrara MSTY."""
    import pandas as pd
    primero = min(pd.Timestamp(c["start"]) for c in MET_CASO)
    assert serie["origen"] == [primero.year, primero.month - 1]
    assert min(serie["incep"].values()) == 0


def test_incep_cubre_los_cinco_tickers_del_caso(serie):
    assert set(serie["incep"]) == {c["t"] for c in MET_CASO}


# ── Regla 1 del contrato fiscal: el capital aportado es invariante ───────────────────────

def test_el_capital_es_una_sola_serie_no_una_por_escenario(serie):
    """Si algún día `capital` aparece anidado por modo o por DRIP, es un bug por
    definición: la retención mueve el bucket impuesto y la base fiscal, jamás lo que
    salió del bolsillo (Regla 1, `specs/roc-nra-invariants.md`)."""
    cap = serie["capital"]
    assert isinstance(cap, dict)
    for k, v in cap.items():
        assert isinstance(k, str) and isinstance(v, (int, float)), (
            f"capital[{k!r}] = {v!r}: dejó de ser mes → dólares planos")
    assert not (set(cap) & set(TRG_MODOS)), "capital se anidó por escenario fiscal"
    assert not (set(cap) & set(MET_SERIE_DRIP)), "capital se anidó por DRIP"


def test_el_capital_final_es_la_suma_exacta_de_los_aportes(serie, ultimo):
    aportado = round(sum(c["inv"] for c in MET_CASO), 2)
    assert serie["invTotal"] == aportado
    assert serie["capital"][ultimo] == aportado


def test_el_capital_solo_sube_y_solo_cuando_entra_una_posicion(serie):
    """Escalonado, no plano — las 5 posiciones se abrieron con 14 meses de diferencia.
    Cada escalón tiene que valer exactamente el aporte de la posición que entró ese mes;
    un escalón que no calce contra `MET_CASO` sería capital saliendo de la nada."""
    por_mes = {}
    for c in MET_CASO:
        por_mes[serie["incep"][c["t"]]] = por_mes.get(serie["incep"][c["t"]], 0.0) + c["inv"]
    previo = 0.0
    for m in range(0, serie["last"] + 1):
        v = serie["capital"].get(str(m))
        if v is None:
            continue
        assert v >= previo, f"el capital aportado bajó en el mes {m}"
        if previo:
            assert round(v - previo, 2) == round(por_mes.get(m, 0.0), 2), (
                f"escalón del mes {m} no calza contra ningún aporte de MET_CASO")
        previo = v


def test_el_capital_no_depende_del_escenario_fiscal(serie):
    """La contracara del test de forma: aunque `capital` fuera plano, la prueba real es
    que ninguna combinación fiscal produzca una serie de capital distinta. Hoy solo
    existe una — este test fija que siga siendo así."""
    assert "capital" not in serie["serie"]
    for modo in TRG_MODOS:
        assert "capital" not in serie["serie"][modo]


# ── Regla 3: objeto fiscal único — reconciliación contra el mismo motor ──────────────────

def test_bruto_con_drip_reconcilia_al_centavo_contra_la_matriz(serie, datos, ultimo):
    """EL gate de este archivo. `serie["bruto"]["con"]` y `metodo_data()["tot"]["val"]`
    son la MISMA corrida (`nra_rate=0`, `drip=True`, mismo capital, mismas fechas): tienen
    que dar el mismo dólar. Si divergen, alguien introdujo una segunda metodología para el
    escenario base — que es exactamente lo que este trabajo se comprometió a no hacer.
    """
    assert serie["serie"]["bruto"]["con"][ultimo] == pytest.approx(
        datos["tot"]["val"], abs=0.05)


def test_bruto_sin_drip_reconcilia_contra_una_corrida_independiente(serie, ultimo):
    """Guard no tautológico: se vuelve a correr el motor aquí, ticker por ticker, en vez
    de releer la cifra que produjo la función bajo prueba."""
    total = 0.0
    for caso in MET_CASO:
        hr = price_cache.load_history(caso["t"])
        r = backtest.run_backtest(caso["t"], start_date=caso["start"],
                                  initial_capital=caso["inv"], drip=False, nra_rate=0.0,
                                  history=hr.history.sort_index())
        total += float(r.daily["total_value"].iloc[-1])
    assert serie["serie"]["bruto"]["sin"][ultimo] == pytest.approx(total, abs=0.05)


def test_la_tasa_roc_sale_del_yaml_vivo_no_de_una_copia(serie):
    """Reconcilia contra `logic.load_roc_19a()` directamente — la fuente, no la fórmula
    que la consumió."""
    roc = logic.load_roc_19a()
    for caso in MET_CASO:
        tk = caso["t"]
        weighted = (roc.get(tk) or {}).get("weighted_pct")
        assert weighted is not None, f"{tk} perdió sus avisos 19(a) en el yaml"
        esperada = 30.0 * (1 - float(weighted) / 100.0)
        assert serie["tasaEfectivaPct"]["roc"][tk] == pytest.approx(esperada, abs=0.01)


def test_las_tasas_de_los_extremos_son_las_declaradas(serie):
    for caso in MET_CASO:
        tk = caso["t"]
        assert serie["tasaEfectivaPct"]["bruto"][tk] == 0.0
        assert serie["tasaEfectivaPct"]["plano"][tk] == 30.0
        assert 0.0 < serie["tasaEfectivaPct"]["roc"][tk] < 30.0, (
            f"{tk}: el escudo del ROC dejó de quedar entre 'no retienen' y '30% liso'")
    assert serie["tasaPlanaPct"] == 30


# ── Regla 2: más impuesto nunca puede dejar más dinero ───────────────────────────────────

def test_mas_retencion_nunca_deja_mas_dinero_en_ningun_mes(serie):
    """Invariante fiscal, mes a mes y en las dos vistas de reinversión. Cazaría un mapeo
    de tasas cruzado (roc y plano intercambiados) o un signo invertido en `nra_rate`.

    OJO con lo que este test NO afirma: nada sobre `con` vs `sin`. Que el efectivo le gane
    al DRIP depende de la TRAYECTORIA del precio, no de si el NAV cae — la premisa «NAV
    cayendo ⇒ el efectivo gana» es falsa y no debe volver a entrar al repo como aserción.
    """
    for drip in MET_SERIE_DRIP:
        for m in range(0, serie["last"] + 1):
            bruto = serie["serie"]["bruto"][drip].get(str(m))
            roc = serie["serie"]["roc"][drip].get(str(m))
            plano = serie["serie"]["plano"][drip].get(str(m))
            if bruto is None or roc is None or plano is None:
                continue
            assert bruto >= roc - 1e-6, f"{drip}, mes {m}: bruto {bruto} < roc {roc}"
            assert roc >= plano - 1e-6, f"{drip}, mes {m}: roc {roc} < plano {plano}"


def test_la_retencion_compone_no_es_un_descuento_al_final(serie, datos, ultimo):
    """El test de METODOLOGÍA, y el que muerde si alguien «simplifica» esta función.

    Las tablas Con/Sin DRIP reescalan en JS el total bruto por `(1 - 0.30)` una sola vez,
    al final (`baseVal` en `metodo.html`). La gráfica simula la retención al cobrar cada
    distribución, así que un escenario retenido reinvierte menos, compra menos acciones y
    COMPONE menos — tiene que terminar estrictamente por debajo de lo que predice el
    atajo. Si algún día coincidieran, sería porque alguien reemplazó la simulación por la
    reescala, y las seis curvas dejarían de significar lo que dice el copy.

    Se reproduce aquí la aritmética exacta del atajo (no se importa: vive en JS) para que
    la comparación sea contra el número que el lector ve en la tabla de al lado.
    """
    atajo = 0.0
    for fila in datos["matriz"]:
        atajo += fila["max"] + round((round(fila["val"]) - fila["max"]) * (1 - 0.30))
    medido = serie["serie"]["plano"]["con"][ultimo]
    assert medido < atajo - 1000, (
        f"«Con NRA · 30%» con DRIP dio {medido:,.2f}, y el atajo de un solo paso predice "
        f"{atajo:,.2f}. Coincidir significa que se perdió el efecto compuesto del impuesto")


# ── procedencia ─────────────────────────────────────────────────────────────────────────

def test_la_fuente_es_el_cache_no_una_descarga_en_runtime(serie):
    assert set(serie["fuente"]) == {c["t"] for c in MET_CASO}
    for tk, src in serie["fuente"].items():
        assert src in ("cache", "live", "cache_stale_fallback"), f"{tk}: {src}"
    assert serie["degradado"] == sorted(
        tk for tk, s in serie["fuente"].items() if s != "cache")


def test_es_serializable_a_json_y_no_pesa_de_mas(serie):
    """Viaja embebido en el `srcdoc` del iframe: si un día crece a cientos de KB es que
    alguien metió la serie DIARIA en vez de la mensual."""
    crudo = json.dumps(serie, ensure_ascii=False)
    assert len(crudo) < 60_000, f"{len(crudo)} bytes — ¿se coló la serie diaria?"


# ── contrato con el componente ──────────────────────────────────────────────────────────

def _leer(*partes):
    with open(os.path.join(BASE, *partes), encoding="utf-8") as f:
        return f.read()


def test_metodo_html_tiene_el_hueco_de_la_serie_y_su_bloque():
    html = _leer("ui", "componentes", "metodo.html")
    assert "var SER = {{SERIE_JSON}}" in html, "falta el punto de inyección {{SERIE_JSON}}"
    assert 'id="tmSerieSvg"' in html and 'id="tmSerieBlock"' in html
    assert 'id="tip"' in html, "el tooltip de la gráfica necesita su elemento montado"


def test_la_grafica_vive_dentro_del_panel_de_la_matriz():
    """Daniel la pidió como tercer bloque de «La matriz», después de las dos tablas — no
    como una sexta sub-vista del menú."""
    html = _leer("ui", "componentes", "metodo.html")
    inicio = html.index('id="met-panel-matriz"')
    fin = html.index("</main>", inicio)
    panel = html[inicio:fin]
    assert 'id="tmSerieBlock"' in panel
    assert panel.index('id="tmSinDripBlock"') < panel.index('id="tmSerieBlock"'), (
        "la gráfica tiene que ir DESPUÉS de las dos tablas")


def test_la_grafica_no_la_esconde_el_toggle_con_sin_drip():
    """Compara los dos mundos entre sí: si quedara ANIDADA dentro de `tmConDripBlock` o
    de `tmSinDripBlock`, el toggle «Cómo se reinvirtió» le escondería la mitad de su
    respuesta. Se comprueba por dos vías independientes:

      1. La sangría: los tres bloques son hermanos, así que abren en la misma columna.
         (Comparar indentación al portar código es justo lo que caza un anidado
         accidental que a ojo se ve idéntico.)
      2. `aplicarVistaDrip`, la función que enciende y apaga esos dos bloques, no puede
         siquiera nombrar al de la gráfica.
    """
    html = _leer("ui", "componentes", "metodo.html")
    sangrias = {}
    for bloque in ("tmConDripBlock", "tmSinDripBlock", "tmSerieBlock"):
        linea = html[html.rindex("\n", 0, html.index(f'id="{bloque}"')) + 1:]
        sangrias[bloque] = len(linea) - len(linea.lstrip(" "))
    assert sangrias["tmSerieBlock"] == sangrias["tmConDripBlock"] == sangrias["tmSinDripBlock"], (
        f"tmSerieBlock dejó de ser hermano de las dos tablas: {sangrias}")

    ini = html.index("function aplicarVistaDrip()")
    cuerpo = html[ini:html.index("\n    }", ini)]
    assert "tmSerieBlock" not in cuerpo, "el toggle Con/Sin DRIP empezó a esconder la gráfica"


def test_render_metodo_inyecta_la_serie_aparte_de_datos():
    src = _leer("ui", "componentes", "__init__.py")
    m = re.search(r"def render_metodo\(([^)]*)\)", src)
    assert m is not None and "serie" in m.group(1)
    cuerpo = src[src.index("def render_metodo("):src.index("\ndef ", src.index("def render_metodo(") + 1)]
    assert '"{{SERIE_JSON}}"' in cuerpo and "json.dumps(serie" in cuerpo
    assert '"null"' in cuerpo, "sin serie el componente tiene que recibir null, no romper"


def test_el_componente_no_recalcula_ninguna_tasa_fiscal_en_js():
    """Regla 3 del contrato: la gráfica RENDERIZA el objeto que armó Python. Si el JS del
    bloque vuelve a escribir un 0.30 o a multiplicar por `TASA_NRA`, volvieron a existir
    dos fuentes para el mismo dólar."""
    html = _leer("ui", "componentes", "metodo.html")
    ini = html.index("function renderSerie()")
    fin = html.index("</script>", ini)
    bloque = html[ini:fin]
    assert "TASA_NRA" not in bloque and "ROC_19A" not in bloque, (
        "el bloque de la serie usó las tasas que gobiernan las tablas")
    assert "baseVal" not in bloque and "devueltoRound" not in bloque, (
        "el bloque de la serie llamó a la aritmética de reescala de las tablas")
    # `(1 - tasa)` es la firma de la reescala; `0.30`/`0.70` escritos así son la firma de
    # una tasa copiada a mano. Ninguna de las dos tiene por qué aparecer: las cifras
    # llegan ya calculadas en `SER`. No se prohíben los decimales en general a propósito
    # —el bloque está lleno de opacidades y grosores de trazo legítimos— sino justo los
    # dos que sólo pueden significar «aquí alguien volvió a hacer la cuenta fiscal».
    assert "(1 -" not in bloque, "apareció una reescala fiscal en el JS de la gráfica"
    assert not re.search(r"\b0\.(30|70)\b", bloque), (
        "apareció la tasa NRA como literal en el JS de la gráfica")
