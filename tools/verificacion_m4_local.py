"""Verificación LOCAL de la auditoría M4: lo que la nube no puede medir.

Corre en la máquina donde está montado `real_examples/` (datos privados de bróker). Hace tres
cosas y al final imprime un bloque para pegar de vuelta en la conversación:

  1. Mide la línea base de la suite completa, la que `CLAUDE.md` pide volver a medir en local.
  2. Aplica, uno a la vez, los mutantes de `MUTANTES` que en la nube sobrevivieron o no se
     pudieron medir. Ronda 1: G1-d (el predicado de filas de impuesto, ciego a la retención
     de IB) y G5-b (una venta SUMA al capital aportado). Ronda 2: H-3 (el aviso de bloqueo
     culpa al export de un fallo nuestro) y CG-1/CG-4/CG-6 (antigüedad y ROC fechado de las
     ganancias de capital). Para cada uno comprueba que sus tests sobre datos REALES estaban
     verdes antes, corre esos tests y la suite completa, y clasifica cada fallo en
     «aserción» o «excepción» leyendo el junitxml.
  3. Restaura cada archivo mutado byte a byte (compara el hash) pase lo que pase.

Uso:
    ./.venv/bin/python tools/verificacion_m4_local.py

Exige `logic.py` y `ui/adapters.py` sin cambios en git, así que si lo interrumpes a la fuerza
a mitad de un mutante, `git checkout -- logic.py ui/adapters.py` los deja como estaban. Tarda
una corrida de la suite por mutante, más la línea base.
Contexto: docs/auditorias/2026-09-24-m4-298ae66.md y docs/auditorias/2026-09-25-m4-ronda2-e53bd97.md.
"""

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
def _ruta(m):
    """Archivo que muta cada entrada: `logic.py` salvo que declare otro en `archivo`."""
    return os.path.join(REPO, m.get("archivo", "logic.py"))

_VENTA = ("                pocket_investment -= abs(amount)\n"
          "                shares_owned -= _adj_qty\n")

MUTANTES = [
    {
        "id": "G1-d",
        "que": "el predicado de filas de impuesto no ve la retención de IB",
        "viejo": ("return ('nra tax' in a or 'tax adj' in a or 'withholding' in a\n"
                  "            or 'foreign tax' in a or"),
        "nuevo": ("return ('nra tax' in a or 'tax adj' in a or False\n"
                  "            or False or"),
        # H3: la variante IB REAL de la familia cruza cuatro fuentes que comparten ese mismo
        # predicado. En la nube solo se pudo medir la sintética.
        "objetivo": ["test_logic.py::test_familia_dividend_declara_bruto_ib_por_ticker",
                     "test_tasa_aplicada.py::test_ib_real_ground_truth_los_cuatro_tickers"],
    },
    {
        "id": "G5-b",
        "que": "una venta SUMA al capital aportado en vez de restar",
        "viejo": _VENTA,
        "nuevo": _VENTA.replace("-= abs(amount)", "+= abs(amount)"),
        # H1: el único cruce que podía cazarlo con datos reales se saltaba en la nube.
        "objetivo": ["test_ganancias_capital.py::"
                     "test_cruce_contra_analyze_portfolio_sobre_los_casos_reales"],
    },
    # ── Ronda 2 (docs/auditorias/2026-09-25-m4-ronda2-e53bd97.md) ──────────────────────────
    {
        "id": "H-3",
        "archivo": "ui/adapters.py",
        "que": "un fallo del guard independiente (CSV releído) se atribuye al export",
        "viejo": '    if "CSV releído" in texto:\n',
        "nuevo": "    if False:\n",
        # El único test que lo cubría con el predicado saboteado sobre el CSV REAL de IB. En
        # la nube se salta; la ronda 2 añadió una versión sintética que sí corre allí.
        "objetivo": ["test_adapters.py::"
                     "test_el_aviso_no_culpa_al_export_cuando_la_culpa_es_del_motor"],
    },
    {
        "id": "CG-1",
        "que": "la fila de split del CSV no reescala la antigüedad de las acciones",
        "viejo": ("            if shares > 0:\n"
                  "                dias_wsum *= qty / shares\n"
                  "            shares = qty\n"),
        "nuevo": "            shares = qty\n",
        # Sobrevivía a toda la suite en la nube. ¿La ve el cruce sobre los demos reales?
        "objetivo": ["test_ganancias_capital.py::"
                     "test_cruce_contra_analyze_portfolio_sobre_los_casos_reales"],
    },
    {
        "id": "CG-4",
        "que": "la venta no se lleva su parte de la antigüedad ponderada",
        "viejo": ("            basis_roc -= base_roc_vendida\n"
                  "            dias_wsum -= dias_wsum * prop\n"),
        "nuevo": "            basis_roc -= base_roc_vendida\n",
        "objetivo": ["test_ganancias_capital.py::"
                     "test_cruce_contra_analyze_portfolio_sobre_los_casos_reales"],
    },
    {
        "id": "CG-6",
        "que": "el ROC del mismo día que la venta no le toca a lo vendido",
        "viejo": "_roc_pend[_roc_i][0] <= dia_limite",
        "nuevo": "_roc_pend[_roc_i][0] < dia_limite",
        "objetivo": ["test_ganancias_capital.py::"
                     "test_el_roc_aplicado_cuadra_con_el_acumulado_del_motor"],
    },
]


def sh(args, timeout=3600):
    return subprocess.run(args, cwd=REPO, capture_output=True, text=True, timeout=timeout)


def git(*args):
    return sh(["git", *args]).stdout.strip()


def estado_arbol():
    """Lo que cambiaría otra sesión trabajando en esta misma carpeta: los archivos VERSIONADOS
    modificados y el HEAD (una rama cambiada lo mueve). Los no versionados quedan fuera a
    propósito: la suite puede dejar archivos propios y eso no es una intrusión."""
    return git("status", "--porcelain", "--untracked-files=no"), git("rev-parse", "HEAD")


def exigir_arbol_intacto(inicial, momento):
    """Medido el 2026-09-25: con tres sesiones en la misma carpeta, otra sesión cambió de rama y
    recuperó un stash a mitad de la corrida, y los mutantes se aplicaron sobre código mezclado.
    En sentido contrario, esa sesión corrió su suite con un mutante de ESTE script aplicado y
    anotó como «flake» el rojo que el mutante provocaba. Si la carpeta cambió, nada de lo medido
    vale: se aborta en vez de entregar cifras mezcladas."""
    if estado_arbol() != inicial:
        sys.exit(f"La carpeta cambió {momento}: otra sesión o programa está trabajando aquí "
                 "(cambió de rama o tocó archivos versionados). Los resultados no valen. "
                 "Córrelo con la carpeta para ti sola, o en un git worktree aparte.")


def resumen(salida):
    lineas = [l for l in salida.strip().splitlines() if l.strip()]
    return lineas[-1] if lineas else "(sin salida)"


def suite_completa():
    r = sh([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no", "-rfE"])
    rojos = set(re.findall(r"^(?:FAILED|ERROR) (\S+)", r.stdout, re.M))
    return resumen(r.stdout), rojos


def por_test(objetivo):
    """nodeid -> 'PASA' | 'SKIP' | 'ASERCION | …' | 'EXCEPCION | …', leído del junitxml."""
    with tempfile.TemporaryDirectory() as tmp:
        xml = os.path.join(tmp, "junit.xml")
        sh([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=short",
            f"--junitxml={xml}", *objetivo])
        if not os.path.exists(xml):
            return {"(colección)": "EXCEPCION | pytest no produjo junitxml"}
        res = {}
        for tc in ET.parse(xml).getroot().iter("testcase"):
            nodo = f"{tc.get('classname')}::{tc.get('name')}"
            fallo, error, salto = tc.find("failure"), tc.find("error"), tc.find("skipped")
            if fallo is None and error is None:
                res[nodo] = "SKIP" if salto is not None else "PASA"
                continue
            el = fallo if fallo is not None else error
            msg = ((el.get("message") or "").strip().splitlines() or [""])[0][:110]
            es_asercion = fallo is not None and (msg.startswith("AssertionError")
                                                 or msg.startswith("assert "))
            res[nodo] = f"{'ASERCION' if es_asercion else 'EXCEPCION'} | {msg}"
        # «No aparece» es una alarma, no un resultado: un nodeid renombrado no puede leerse
        # como «el mutante sobrevivió».
        return res or {"(objetivo)": f"EXCEPCION | no se recolectó ningún test de {objetivo}"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sin-real-examples", action="store_true",
                    help="Corre aunque falte real_examples/ (solo para probar el script: "
                         "sin los datos, los tests objetivo se saltan y no se mide nada).")
    opts = ap.parse_args()

    montado = os.path.isdir(os.path.join(REPO, "real_examples"))
    if not montado and not opts.sin_real_examples:
        sys.exit("real_examples/ no está montado: este script existe justo para lo que sin esos "
                 "datos no se puede medir. Móntalo y vuelve a correrlo.")
    archivos = sorted({m.get("archivo", "logic.py") for m in MUTANTES})
    if git("status", "--porcelain", "--", *archivos):
        sys.exit(f"{', '.join(archivos)}: hay cambios sin commitear y no muto encima de "
                 "trabajo tuyo.")

    print(f"Durante unas {len(MUTANTES) + 1} corridas de la suite {', '.join(archivos)} van a "
          "estar MUTADOS a ratos: ninguna otra sesión debe correr tests ni editar en esta "
          "carpeta mientras tanto.", flush=True)
    inicial = estado_arbol()
    informe = [
        f"HEAD: {git('rev-parse', 'HEAD')} ({git('rev-parse', '--abbrev-ref', 'HEAD')})",
        f"real_examples/: {'montado' if montado else 'NO montado (prueba del script)'}",
    ]
    if inicial[0]:
        informe.append("OJO, cambios versionados al empezar (la línea base NO es main puro): "
                       + "; ".join(inicial[0].splitlines()[:10]))
    print("Midiendo la línea base (suite completa)…", flush=True)
    linea_base, rojos_base = suite_completa()
    informe += [f"Línea base: {linea_base}",
                f"Rojos de la línea base: {sorted(rojos_base) or 'ninguno'}"]

    for m in MUTANTES:
        exigir_arbol_intacto(inicial, f"antes del mutante {m['id']}")
        print(f"Mutante {m['id']}: {m['que']}…", flush=True)
        informe.append(f"\n{m['id']} — {m['que']}")
        # En binario: la restauración tiene que ser byte a byte, sin normalizar saltos de línea.
        ruta = _ruta(m)
        with open(ruta, "rb") as f:
            original = f.read()
        firma = hashlib.sha256(original).hexdigest()
        texto = original.decode("utf-8")
        n = texto.count(m["viejo"])
        if n != 1:
            informe.append(f"   NO APLICA: el trozo a mutar aparece {n} veces "
                           "(¿cambió el archivo desde la auditoría?)")
            continue
        antes = por_test(m["objetivo"])
        informe.append("   antes del mutante: " + ", ".join(
            f"{nodo.split('::')[-1]}={estado.split(' |')[0]}" for nodo, estado in antes.items()))
        try:
            with open(ruta, "wb") as f:
                f.write(texto.replace(m["viejo"], m["nuevo"]).encode("utf-8"))
            if sh([PY, "-m", "py_compile", ruta]).returncode != 0:
                informe.append("   el mutante NO compila: no mide nada")
                continue
            for nodo, estado in por_test(m["objetivo"]).items():
                informe.append(f"   {estado[:120]:120s} <- {nodo.split('::')[-1]}")
            linea, rojos = suite_completa()
            nuevos = sorted(rojos - rojos_base)
            informe.append(f"   suite completa: {linea}")
            informe.append(f"   rojos nuevos ({len(nuevos)}): {nuevos}")
        finally:
            with open(ruta, "wb") as f:
                f.write(original)
            with open(ruta, "rb") as f:
                restaurado = hashlib.sha256(f.read())
            if restaurado.hexdigest() != firma:
                rel = os.path.relpath(ruta, REPO)
                sys.exit(f"¡{rel} NO quedó como estaba! Corre: git checkout -- {rel}")

    exigir_arbol_intacto(inicial, "durante el último mutante")
    informe.append(f"\n{', '.join(archivos)} restaurados: "
                   f"{'sí' if not git('status', '--porcelain', '--', *archivos) else 'NO'}")
    print("\n===== VERIFICACIÓN LOCAL M4 — pega esto en la conversación =====")
    print("\n".join(informe))
    print("=================================================================")


if __name__ == "__main__":
    main()
