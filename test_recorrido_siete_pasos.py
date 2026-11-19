"""C5 — el recorrido de cada fondo pasa de ocho pasos a siete (19-nov, idea de Daniel).

«Efectivo cobrado» era «Efectivo apartado» otra vez: su propio texto lo decía — «el mismo
efectivo que apartaste en el paso 4 vuelve a sumar». No traía una cifra nueva, solo
deshacía la resta anterior, y el paso final ya dibujaba ese efectivo.

**Ninguna cifra cambia, y está medido**: `cashflow_data` sobre los cuatro fondos del caso
real da exactamente los mismos valores antes y después; la única diferencia es el número
de pasos (8 → 7). Las seis identidades de `verificar_identidades` siguen intactas.

Lo que sí había que mover: el paso que se va era el único sitio donde se explicaba `OTROS`
—el efectivo que no viene del dividendo—, y el único que decía que lo apartado vuelve.
"""
import re
from pathlib import Path

from ui.adapters import STEP_LABELS

COMPONENTE = Path(__file__).resolve().parent / "ui" / "componentes" / "cashflow.html"
FUENTE = COMPONENTE.read_text(encoding="utf-8")


def _paso(etiqueta: str) -> str:
    """El objeto de un paso de la cascada, desde su `lab` hacia atrás y adelante."""
    i = FUENTE.index(f'lab:"{etiqueta}"')
    ini = FUENTE.rindex("    { segs:", 0, i)
    return FUENTE[ini:FUENTE.index("\n    { segs:", i) if "\n    { segs:" in FUENTE[i:] else len(FUENTE)]


def test_el_recorrido_tiene_siete_pasos():
    assert len(STEP_LABELS) == 7, STEP_LABELS
    assert "Efectivo cobrado" not in STEP_LABELS
    assert STEP_LABELS[-1] == "Resultado real"


def test_el_componente_dice_los_mismos_siete():
    js = re.search(r"var STEP_LABELS = \[(.*?)\];", FUENTE, re.S).group(1)
    nombres = [x.strip().strip('"') for x in js.split(",")]
    assert nombres == list(STEP_LABELS), (nombres, list(STEP_LABELS))


def test_ya_no_queda_el_paso_repetido():
    assert "Efectivo cobrado" not in FUENTE
    assert 'lab:"Efectivo apartado"' in FUENTE, "el que sí aporta sigue"


def test_el_paso_final_sigue_dibujando_el_efectivo():
    """Si se quitara de sus segmentos, el efectivo desaparecería de la cascada y el
    resultado dejaría de cuadrar con la barra."""
    final = _paso("Resultado real")
    assert "segsEfectivo()" in final, final[:200]
    assert "s-anchor" in final


def test_el_que_aparta_dice_que_vuelve():
    """Lo decía el paso que se fue: sin esto, el cliente se queda con que ese dinero se
    restó y nunca vuelve."""
    apartado = _paso("Efectivo apartado")
    assert "vuelve a sumar" in apartado, apartado[:200]


def test_la_explicacion_del_efectivo_que_no_es_dividendo_no_se_perdio():
    """`OTROS` (Cash In Lieu y compañía) solo se explicaba en el paso que se quitó."""
    final = _paso("Resultado real")
    assert "HAY_OTROS" in final
    assert "no viene del dividendo" in final
    assert "franja, rayada" in final


def test_las_seis_identidades_siguen_vivas():
    """Quitar un paso es presentación: ninguna cuenta se toca. Estas comprobaciones son las
    que cazarían a quien aprovechara para recalcular algo.

    Se ROMPE cada identidad y se exige que avise. Mirar que su texto siga en el archivo no
    basta: medido, renombrar `check(` a otra cosa deja las frases intactas y el guard de
    texto pasa verde.
    """
    from ui.adapters import verificar_identidades

    base = {"BRUTO": 100.0, "IMPUESTO": 30.0, "NETO": 70.0, "DRIP": 50.0, "CASH": 20.0,
            "OTROS": 0.0, "POCKET": 1000.0, "TOTAL_TRABAJANDO": 1050.0, "MERCADO": -50.0,
            "VALOR_HOY": 1000.0, "CAPITAL_ACTUAL": 1020.0, "RESULTADO": 20.0}
    assert verificar_identidades(dict(base)) == [], "los datos de partida ya no cuadran"

    # Se exige que avise LA identidad rota, no que avise alguna: romper una cifra suele
    # romper dos identidades a la vez, así que «la lista no está vacía» deja pasar un
    # check desactivado — medido, ese mutante sobrevivía.
    rompe = {
        "bruto = neto + impuesto": {"BRUTO": 140.0},
        "neto = reinvertido + efectivo": {"CASH": 5.0},
        "capital trabajando = bolsillo + reinvertido": {"TOTAL_TRABAJANDO": 1200.0},
        "impacto de mercado = valor hoy − capital trabajando": {"MERCADO": 10.0},
        "capital actual = valor hoy + efectivo + otros": {"CAPITAL_ACTUAL": 1500.0},
        "resultado = capital actual − bolsillo": {"RESULTADO": 500.0},
    }
    for identidad, cambio in rompe.items():
        avisos = verificar_identidades(dict(base) | cambio)
        assert any(identidad in a for a in avisos), (
            f"romper «{identidad}» no la hizo avisar; avisos: {avisos}")


def test_el_rail_y_la_cascada_no_pueden_divergir():
    """El rail nativo se dibuja con `STEP_LABELS` del adaptador y las columnas con la lista
    del componente: son dos copias, y el guard de que coinciden vive en
    `test_arreglos_rapidos_ui.py`. Aquí se fija el número, que es lo que cambió."""
    cols = re.findall(r'\n    \{ segs:', FUENTE)
    assert len(cols) == len(STEP_LABELS), (
        f"{len(cols)} columnas en la cascada contra {len(STEP_LABELS)} pasos del rail")
