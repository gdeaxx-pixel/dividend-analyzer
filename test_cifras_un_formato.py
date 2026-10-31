"""D1 de la propuesta de interfaz (2026-10-30): un solo formato de cifras en dólares.

La misma cifra salía distinta según la sección: Cash flow, Impuestos, las dos Comparaciones y
la Hoja escribían «−$8412.30» y «$1847.06»; Portafolios, Vigilar y Método tradicional, «$8,412.30».
Ahora todas llevan separador de miles y dos decimales. Solo cambia el formato: el número es el
mismo que daba `toFixed(2)`.

Se ejecutan en Node las funciones REALES de cada componente, extraídas de su <script>; sin node
estos tests se saltan, y un skip no es un pass. `ui/componentes/impuestos.html` (v1) no se toca:
ya no se dibuja y es la referencia congelada del guard de frases.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "componentes")
_PIDE_NODE = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node no está en el PATH: el formato de las cifras NO se comprobó. Un skip no es un pass.")


def _fuente(archivo):
    with open(os.path.join(_DIR, archivo), encoding="utf-8") as f:
        return f.read()


def _funcion(src, nombre):
    """El texto de `function nombre(...) { ... }`, contando llaves desde la primera."""
    m = re.search(r"function " + nombre + r"\s*\([^)]*\)\s*\{", src)
    assert m, f"no encuentro la función {nombre}"
    nivel, i = 0, m.end() - 1
    while True:
        nivel += {"{": 1, "}": -1}.get(src[i], 0)
        if nivel == 0:
            return src[m.start():i + 1]
        i += 1


def _node(js):
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


_CASOS = [
    ("cashflow.html", ("miles",), "miles",
     [(1234.5, "1,234.50"), (120978, "120,978.00"), (946.82, "946.82"), (0, "0.00")]),
    ("impuestos_v2.html", ("money",), "money",
     [(1847.06, "$1,847.06"), (-1234.5, "−$1,234.50"), (0.4, "$0.40"), (None, "$0.00")]),
    ("comparacion.html", ("cvUsd",), "cvUsd", [(12345.678, "$12,345.68"), (-5, "−$5.00")]),
    ("comparacion_real.html", ("cvUsd",), "cvUsd", [(12345.678, "$12,345.68"), (-5, "−$5.00")]),
    ("hoja.html", ("miles", "money", "signed"), "signed",
     [(1234.5, "+$1,234.50"), (-98765.4, "−$98,765.40")]),
]


@_PIDE_NODE
@pytest.mark.parametrize("archivo, funciones, llamada, casos", _CASOS,
                         ids=[c[0] for c in _CASOS])
def test_las_cifras_en_dolares_llevan_separador_de_miles(archivo, funciones, llamada, casos):
    src = _fuente(archivo)
    js = "\n".join(_funcion(src, f) for f in funciones)
    js += f"\nconsole.log(JSON.stringify({json.dumps([c[0] for c in casos])}.map({llamada})));"
    assert _node(js) == [c[1] for c in casos]


@_PIDE_NODE
@pytest.mark.parametrize("archivo, funciones, llamada, casos", _CASOS,
                         ids=[c[0] for c in _CASOS])
def test_el_separador_no_cambia_el_numero(archivo, funciones, llamada, casos):
    """Sin comas, signo ni «$», cada cifra es exactamente `Math.abs(x).toFixed(2)` en 20,000
    importes: positivos y negativos, de 0 a diez millones, y los medios centavos donde
    `toLocaleString` redondea distinto (2.675 → «2.68» contra «2.67»: medido el 30-oct)."""
    js = "\n".join(_funcion(_fuente(archivo), f) for f in funciones) + r"""
var malos = [], xs = [0, 0.005, 0.015, 0.125, 2.675, 999.995, 1000, 1234.565, 9999999.99];
for (var i = 0; i < 20000; i++) {
  var x = Math.round((Math.random() * 1e7) * 100) / 100 + (i % 7 === 0 ? 0.005 : 0);
  xs.push(i % 2 ? x : -x);
}
xs.forEach(function (x) {
  if (String(LLAMADA(x)).replace(/[$,+\u2212-]/g, "") !== Math.abs(x).toFixed(2)) malos.push(x);
});
console.log(JSON.stringify(malos.slice(0, 5)));
""".replace("LLAMADA", llamada)
    assert _node(js) == []


_DOLAR_SIN_MILES = re.compile(r"\$['\"]\s*\+\s*(?:Math\.abs\()?[\w.]+\)?\.toFixed\(")


@pytest.mark.parametrize("archivo", sorted(f for f in os.listdir(_DIR)
                                           if f.endswith(".html") and f != "impuestos.html"))
def test_ningun_componente_escribe_dolares_con_tofixed(archivo):
    """Un «$» pegado a un `toFixed` vuelve a escribir «$8412.30» sin coma."""
    malos = [m.group(0) for m in _DOLAR_SIN_MILES.finditer(_fuente(archivo))]
    assert not malos, f"{archivo}: cifras en dólares sin separador de miles: {malos[:3]}"
