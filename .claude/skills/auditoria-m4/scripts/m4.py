"""Arnés M4 — sabotaje de tests. Aplica mutantes de a uno y mide cuántos tests los cazan.

Uso (desde la raíz del repo, con la carpeta para ti solo o en un `git worktree` aparte):

    ./.venv/bin/python .claude/skills/auditoria-m4/scripts/m4.py base
    ./.venv/bin/python .claude/skills/auditoria-m4/scripts/m4.py run mutantes.py [ID ...]

`base` corre la suite completa y guarda el estado de cada test en `<out>/base.json`.
`run` lee `MUTANTES` de `mutantes.py`, una lista de dicts:

    dict(id='CG-1', file='logic.py', que='qué bug imita',
         old='texto exacto (1 sola ocurrencia)', new='texto mutado',
         target=['test_x.py::test_y'])       # nodeids concretos, NO archivos enteros

Protocolo, por mutante (el de las rondas 1 y 2, no negociable):
  1. El objetivo tiene que estar VERDE y NO saltado antes del mutante; si no, se aborta.
  2. El texto a mutar aparece exactamente 1 vez; se aplica y se pasa `py_compile` si es .py.
  3. Se corren el objetivo y la suite COMPLETA, las dos con junitxml.
  4. Cada fallo se clasifica desde el XML: ASSERT si es <failure> con mensaje `assert`/
     `AssertionError`; EXC en cualquier otro caso. Solo cuentan como «nuevos» los tests que
     estaban PASS en la base (por nodeid, no por cuenta).
  5. Se restaura EN BINARIO desde el contenido guardado y se verifica el sha256. Nunca
     `git checkout` sobre un archivo con trabajo sin commitear.
  6. Si la carpeta cambió (HEAD u otro archivo versionado) entre mutantes, se aborta: otra
     sesión está trabajando aquí y lo medido no vale.

Variables de entorno: M4_REPO (raíz; por defecto el cwd), M4_OUT (dónde guardar base.json y
res_<ID>.json; por defecto `<repo>/.m4_out`, que conviene tener en .gitignore o fuera del repo).
"""
import hashlib
import json
import os
import py_compile
import runpy
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

REPO = os.path.abspath(os.environ.get("M4_REPO", os.getcwd()))
OUT = os.path.abspath(os.environ.get("M4_OUT", os.path.join(REPO, ".m4_out")))
PY = os.path.join(REPO, ".venv", "bin", "python")
if not os.path.exists(PY):
    PY = sys.executable


def _git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


def _estado_arbol(excluir):
    """HEAD + archivos versionados modificados, sin contar los que este arnés muta a propósito."""
    lineas = [l for l in _git("status", "--porcelain", "--untracked-files=no").splitlines()
              if l[3:].strip() not in excluir]
    return _git("rev-parse", "HEAD"), tuple(lineas)


def junit(args, xml):
    """nodeid -> 'PASS' | 'SKIP' | 'ASSERT | msg' | 'EXC | msg'."""
    subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=short",
                    f"--junitxml={xml}", *args], cwd=REPO, capture_output=True, text=True,
                   timeout=3600)
    if not os.path.exists(xml):
        return {"(coleccion)": "EXC | pytest no produjo junitxml"}
    res = {}
    for tc in ET.parse(xml).getroot().iter("testcase"):
        n = f"{tc.get('classname')}::{tc.get('name')}"
        f, e, s = tc.find("failure"), tc.find("error"), tc.find("skipped")
        if f is None and e is None:
            res[n] = "SKIP" if s is not None else "PASS"
            continue
        el = f if f is not None else e
        msg = ((el.get("message") or "").strip().splitlines() or [""])[0][:200]
        es_assert = f is not None and (msg.startswith("AssertionError") or msg.startswith("assert "))
        res[n] = ("ASSERT | " if es_assert else "EXC | ") + msg
    # «No aparece» es una alarma, no un resultado: un nodeid mal escrito no es «sobrevivió».
    return res or {"(objetivo)": f"EXC | no se recolectó ningún test de {args}"}


class _Aborta(Exception):
    """El mutante no se mide: se registra el motivo y se sigue con el siguiente."""


def cmd_base():
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        res = junit([], os.path.join(t, "base.xml"))
    json.dump(res, open(os.path.join(OUT, "base.json"), "w"), indent=0)
    cuenta = {k: sum(v.split(" ")[0] == k for v in res.values()) for k in ("PASS", "SKIP", "ASSERT", "EXC")}
    print("base:", cuenta, "(un SKIP no es un PASS: dilo en el informe)")
    if cuenta["ASSERT"] or cuenta["EXC"]:
        print("OJO: la base tiene rojos. Investígalos ANTES de medir mutantes.")


def cmd_run(ruta_mutantes, ids):
    base_p = os.path.join(OUT, "base.json")
    if not os.path.exists(base_p):
        sys.exit("Falta base.json: corre primero `m4.py base` sobre el árbol limpio.")
    base = json.load(open(base_p))
    muts = runpy.run_path(ruta_mutantes)["MUTANTES"]
    archivos = {m["file"] for m in muts}
    inicial = _estado_arbol(archivos)
    for m in muts:
        if ids and m["id"] not in ids:
            continue
        if _estado_arbol(archivos) != inicial:
            sys.exit(f"La carpeta cambió antes de {m['id']}: otra sesión trabaja aquí. Aborto.")
        path = os.path.join(REPO, m["file"])
        orig = open(path, "rb").read()
        h0 = hashlib.sha256(orig).hexdigest()
        rep = {"id": m["id"], "file": m["file"], "que": m.get("que", "")}
        try:
            with tempfile.TemporaryDirectory() as t:
                rep["pre"] = junit(m["target"], os.path.join(t, "pre.xml"))
            if any(v != "PASS" for v in rep["pre"].values()):
                rep["abort"] = "objetivo no verde (o saltado) antes del mutante"
                raise _Aborta
            txt = orig.decode("utf-8")
            n = txt.count(m["old"])
            if n != 1:
                rep["abort"] = f"el texto a mutar aparece {n} veces (debe ser 1)"
                raise _Aborta
            open(path, "wb").write(txt.replace(m["old"], m["new"]).encode("utf-8"))
            if path.endswith(".py"):
                py_compile.compile(path, doraise=True)
            with tempfile.TemporaryDirectory() as t:
                rep["obj"] = junit(m["target"], os.path.join(t, "obj.xml"))
                full = junit([], os.path.join(t, "full.xml"))
            rep["nuevos"] = {k: v for k, v in full.items()
                             if not v.startswith(("PASS", "SKIP")) and base.get(k) == "PASS"}
            rep["n_assert"] = sum(v.startswith("ASSERT") for v in rep["nuevos"].values())
            rep["n_exc"] = sum(v.startswith("EXC") for v in rep["nuevos"].values())
        except _Aborta:
            pass
        finally:
            open(path, "wb").write(orig)
            rep["restaurado"] = hashlib.sha256(open(path, "rb").read()).hexdigest() == h0
            os.makedirs(OUT, exist_ok=True)
            json.dump(rep, open(os.path.join(OUT, f"res_{m['id']}.json"), "w"),
                      indent=1, ensure_ascii=False)
        obj = rep.get("obj", {})
        estado_obj = ("aborta: " + rep["abort"]) if rep.get("abort") else (
            "ASSERT" if any(v.startswith("ASSERT") for v in obj.values()) else
            "EXC" if any(v.startswith("EXC") for v in obj.values()) else "VIVE")
        n = len(rep.get("nuevos", {}))
        alerta = "  <- SOBREVIVE A LA SUITE" if n == 0 and not rep.get("abort") else (
                 "  <- frágil: 1 solo test" if n == 1 else "")
        print(f"{m['id']:8s} objetivo={estado_obj:10s} suite={n} (assert {rep.get('n_assert')}, "
              f"exc {rep.get('n_exc')}) restaurado={rep['restaurado']}{alerta}", flush=True)
        if not rep["restaurado"]:
            sys.exit(f"¡{m['file']} NO quedó como estaba! Revisa antes de seguir.")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "base":
        cmd_base()
    elif len(sys.argv) >= 3 and sys.argv[1] == "run":
        cmd_run(sys.argv[2], sys.argv[3:])
    else:
        sys.exit(__doc__)
