"""A2 — «Para entenderlo a fondo» pasa a cuatro preguntas con su cifra (18-nov).

El bloque era un índice de destinos con una frase de qué había en cada uno. Ahora cada
línea responde —te pagaron tanto, el impuesto se quedó tanto, tanto era tu propio dinero
de vuelta, tanto quedó sin reinvertir— y el enlace solo está por si se quiere el detalle.

Las cuatro cifras ya existían en las stats por ticker. Lo que hay que vigilar es su
**momento** (Regla 2 del contrato): tres son al cobro y el ROC es de la reclasificación
anual, así que se muestran en líneas separadas y nunca se restan entre sí.

Contrastado contra una fuente independiente: en el caso de ejemplo la línea dice que el
impuesto se quedó $0, y la vista de Impuestos del mismo caso dice «no hubo retención al
cobro sobre tus dividendos en la ventana analizada».
"""
import re
from pathlib import Path

from ui.adapters import PREGUNTAS_CLAVE, preguntas_clave_data

VISTA = (Path(__file__).resolve().parent / "ui" / "heredadas.py").read_text(encoding="utf-8")


def _stats(bruto=100.0, retenido=30.0, roc=40.0, cash=10.0):
    return {
        "pocket_investment": 1000.0, "market_value": 1000.0, "net_profit": 0.0,
        "dividends_gross_total": bruto, "withheld_tax_total": retenido,
        "roc_accumulated": roc, "dividends_cash_net": cash,
        "dividends_net_total": bruto - retenido,
    }


def _bloque(nombre: str) -> str:
    i = VISTA.index(f"def {nombre}(")
    return VISTA[i:VISTA.index("\ndef ", i + 1)]


def test_sin_dividendos_no_hay_bloque():
    """Una cartera solo de crecimiento tendría cuatro ceros: el bloque sobra."""
    assert preguntas_clave_data({}) is None
    assert preguntas_clave_data({"A": _stats(bruto=0, retenido=0, roc=0, cash=0)}) is None
    assert preguntas_clave_data({"A": {"skipped": True}}) is None


def test_las_cuatro_preguntas_en_orden():
    d = preguntas_clave_data({"A": _stats()})
    assert [p["clave"] for p in d["preguntas"]] == ["pagado", "retenido", "roc", "efectivo"]
    assert all(p["pregunta"].startswith("¿") for p in d["preguntas"])


def test_cada_cifra_suma_su_campo_sobre_los_fondos_con_datos():
    d = preguntas_clave_data({"A": _stats(), "B": _stats(bruto=50.0, retenido=5.0, roc=7.0, cash=3.0),
                              "C": {"skipped": True}})
    valores = {p["clave"]: p["valor"] for p in d["preguntas"]}
    assert valores == {"pagado": 150.0, "retenido": 35.0, "roc": 47.0, "efectivo": 13.0}


def test_el_roc_declara_que_es_de_otro_momento():
    """Es la cifra que no comparte momento con las demás; si se declarara «al cobro»,
    alguien la restaría de lo pagado."""
    d = preguntas_clave_data({"A": _stats()})
    momentos = {p["clave"]: p["momento"] for p in d["preguntas"]}
    assert momentos["roc"] == "tras_reclasificacion_anual"
    assert momentos["pagado"] == momentos["retenido"] == momentos["efectivo"] == "al_cobro"


def test_el_adaptador_no_resta_cifras_entre_si():
    """Regla 2: nada de operaciones entre cifras de momentos distintos. Aquí cada línea es
    una suma de su propio campo y nada más."""
    i = __import__("ui.adapters", fromlist=["x"]).__file__
    fuente = Path(i).read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("def preguntas_clave_data("):]
    cuerpo = cuerpo[:cuerpo.index("\ndef ")]
    cuerpo = cuerpo[cuerpo.index('"""', cuerpo.index('"""') + 3) + 3:]   # fuera el docstring
    assert "cifras[" not in cuerpo.split("return")[0].replace('cifras[clave]', ''), cuerpo
    assert not re.search(r"cifras\[[^\]]+\]\s*[-+]\s*cifras\[", cuerpo), "está restando dos cifras"


def test_lo_pagado_menos_lo_retenido_es_el_neto_del_objeto_fiscal():
    """La identidad que sí vale, contra `dividends_net_total`, que llega por otra ruta.
    Medido en el caso real de Daniel: $422 − $127 = $295."""
    d = preguntas_clave_data({"A": _stats(), "B": _stats(bruto=422.0, retenido=127.0)})
    v = {p["clave"]: p["valor"] for p in d["preguntas"]}
    assert abs((v["pagado"] - v["retenido"]) - d["neto"]) < 1e-9


def test_cada_pregunta_lleva_a_una_vista_que_existe():
    from ui import chrome

    d = preguntas_clave_data({"A": _stats()})
    for p in d["preguntas"]:
        assert p["cat"] in chrome.CAT_ORDER_TOTAL, p
        assert p["vista"] in chrome._orden(p["cat"]), p


def test_las_tres_columnas_son_iguales_en_las_cuatro_filas():
    """El pedido de Daniel (18-nov): «que no se sienta que se mueven de un lado para
    otro». Con un reparto por fila, una etiqueta más larga corre la cifra de esa fila.

    Se mira el ÁRBOL, no el texto: un reparto escrito como `[6, 2, 3] if … else [5, 2, 4]`
    deja el primer literal intacto y un `findall` lo da por bueno — medido, ese mutante
    sobrevivía.
    """
    import ast

    arbol = ast.parse(VISTA)
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "_botones_ruta")
    llamadas = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == "columns"]
    assert len(llamadas) == 1, f"{len(llamadas)} llamadas a columns: pueden divergir"
    reparto = llamadas[0].args[0]
    assert isinstance(reparto, ast.List), (
        f"el reparto no es una lista fija sino {type(reparto).__name__}: cada fila podría "
        "repartir distinto")
    assert all(isinstance(e, ast.Constant) for e in reparto.elts), ast.dump(reparto)


def test_sin_retencion_no_sale_menos_cero():
    """Medido en el caso de ejemplo: no hubo retención y la línea mostraba «−$0»."""
    cuerpo = _bloque("_botones_ruta")
    assert 'round(p["valor"]) != 0' in cuerpo


def test_la_vista_no_calcula_las_cifras():
    cuerpo = _bloque("_botones_ruta")
    assert "preguntas_clave_data(resultados)" in cuerpo
    assert not re.search(r"(dividends_|withheld_|roc_accumulated|sum\()", cuerpo), cuerpo


def test_la_nota_dice_por_que_el_roc_no_se_resta():
    cuerpo = _bloque("_botones_ruta")
    assert "no " in cuerpo and "resta" in cuerpo and "momentos distintos" in cuerpo


def test_el_catalogo_y_lo_que_se_publica_no_divergen():
    """`PREGUNTAS_CLAVE` es la lista única: si alguien añade una pregunta al catálogo, sale
    publicada, y si la quita, desaparece."""
    d = preguntas_clave_data({"A": _stats()})
    assert [p["clave"] for p in d["preguntas"]] == [c for c, *_ in PREGUNTAS_CLAVE]
