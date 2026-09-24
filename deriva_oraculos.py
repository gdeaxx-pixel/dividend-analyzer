"""Plugin anti-deriva: detecta rojos que cambian de valor sin cambiar de color.

Lección C·15/C·13 (sep-2026): un rojo estable en color puede estar diciendo algo nuevo.
Este plugin guarda la huella numérica de cada fallo en un baseline versionado y en la
siguiente corrida distingue «sigue igual» de «SE MOVIÓ».

Limitación conocida: solo cuenta fallos de la fase ``call`` (report.when == "call" y
report.failed). Skips y errores de setup/teardown quedan fuera.
Un test flaky entra y sale del baseline: el informe lo cantará como 🆕 NUEVO ROJO una
corrida y ✅ SANADO la siguiente. El mecanismo no distingue flaky de deriva real.
"""

import hashlib
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

import pytest

NOMBRE_BASELINE = "deriva_baseline.json"   # en la raíz del repo (junto a conftest.py)
CARPETA_LOCAL = ".deriva"                  # estado local, gitignored


def normalizar(texto: str) -> str:
    """Prepara el texto del fallo para que la huella sea comparable entre máquinas y
    versiones de pytest. En este orden:
    1. quita códigos de color ANSI (`\\x1b\\[[0-9;]*m`);
    2. quita direcciones de memoria (`0x[0-9a-fA-F]+` → `<addr>`);
    3. quita rutas absolutas: de cualquier token con `/` conserva solo el basename
       (`/Users/x/repo/test_a.py` → `test_a.py`; `/home/runner/...` igual);
    4. quita números de línea de referencias `archivo.py:123` → `archivo.py`.
    Devuelve el texto en minúsculas."""
    # 1. ANSI
    texto = re.sub(r'\x1b\[[0-9;]*m', '', texto)
    # 2. direcciones de memoria
    texto = re.sub(r'0x[0-9a-fA-F]+', '<addr>', texto)
    # 3. rutas absolutas → basename
    def _basename_token(match):
        ruta = match.group(0)
        # conservar solo el basename
        return os.path.basename(ruta)
    texto = re.sub(r'/[^\s:]+', _basename_token, texto)
    # 4. números de línea: archivo.py:123 → archivo.py
    texto = re.sub(r'(\S+\.py):\d+', r'\1', texto)
    return texto.lower()


def tokens_numericos(texto_normalizado: str) -> list:
    """Extrae los números del texto normalizado: regex `\\d+\\.\\d+(?:e[+-]?\\d+)?`
    (SOLO flotantes — los enteros son ruido: conteos, referencias, fechas).
    Devuelve lista ordenada y sin duplicados, como strings."""
    matches = re.findall(r'\d+\.\d+(?:e[+-]?\d+)?', texto_normalizado)
    # sin duplicados, ordenados
    vistos = set()
    resultado = []
    for m in matches:
        if m not in vistos:
            vistos.add(m)
            resultado.append(m)
    resultado.sort()
    return resultado


def huella(nodeid: str, longrepr: str) -> str:
    """sha256 de (nodeid + '\\n' + tokens numéricos uno por línea) sobre el longrepr
    NORMALIZADO. Devuelve los primeros 16 hex. Misma entrada → misma huella, en
    cualquier máquina."""
    norm = normalizar(longrepr)
    toks = tokens_numericos(norm)
    payload = nodeid + '\n' + norm + '\n' + '\n'.join(toks)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


def leer_baseline(ruta: str) -> dict:
    """Lee el JSON del baseline. Si no existe o está corrupto, devuelve `{"version": 1,
    "rojos": {}}` — NUNCA lanza (un plugin roto no puede enrojecer la suite)."""
    try:
        with open(ruta, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict) or 'rojos' not in data:
            return {"version": 1, "rojos": {}}
        return data
    except (OSError, json.JSONDecodeError, ValueError):
        return {"version": 1, "rojos": {}}


def clasificar(previo, fallo_actual: bool, huella_actual) -> str:
    """previo = entrada del baseline para ese nodeid, o None.
    Devuelve exactamente uno de:
    - "movido"  : previo existe, sigue fallando, huella distinta
    - "igual"   : previo existe, sigue fallando, huella igual
    - "nuevo"   : no hay previo, falla
    - "sanado"  : previo existe, ya no falla
    - "verde"   : no hay previo y no falla (no se reporta)"""
    if previo is None:
        if fallo_actual:
            return "nuevo"
        return "verde"
    if not fallo_actual:
        return "sanado"
    if previo.get("huella") == huella_actual:
        return "igual"
    return "movido"


# ── pytest hooks ──────────────────────────────────────────────────────────────


def pytest_addoption(parser):
    try:
        parser.addoption(
            "--deriva-actualizar",
            action="store_true",
            default=False,
            help="Reescribe el baseline versionado al terminar la corrida.",
        )
        parser.addoption(
            "--deriva-off",
            action="store_true",
            default=False,
            help="Desactiva el plugin por completo (escape hatch).",
        )
        parser.addoption(
            "--deriva-baseline",
            default=None,
            help="Usa RUTA como baseline en vez del de la raíz.",
        )
    except Exception as ex:
        print(f"deriva_oraculos: aviso interno ({ex})")


class DerivaCollector:
    """Recoge fallos de la fase call y los clasifica contra el baseline."""

    def __init__(self, baseline_path, rootdir):
        self.baseline_path = baseline_path
        self.rootdir = rootdir
        self.baseline = leer_baseline(baseline_path)
        self.fallos = {}  # nodeid -> {huella, valores, longrepr_normalizado}
        self.resultados = {}  # nodeid -> clasificacion

    def add_failure(self, nodeid, longrepr):
        norm = normalizar(longrepr)
        toks = tokens_numericos(norm)[:20]
        h = huella(nodeid, longrepr)
        self.fallos[nodeid] = {
            "huella": h,
            "valores": toks,
        }


def pytest_configure(config):
    try:
        if config.getoption("--deriva-off"):
            return
    except Exception:
        return
    try:
        rootdir = str(config.rootdir)
        baseline_opt = config.getoption("--deriva-baseline")
        if baseline_opt:
            baseline_path = baseline_opt
        else:
            baseline_path = os.path.join(rootdir, NOMBRE_BASELINE)
        collector = DerivaCollector(baseline_path, rootdir)
        config._deriva_collector = collector
    except Exception as ex:
        print(f"deriva_oraculos: aviso interno ({ex})")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    try:
        report = outcome.get_result()
        config = item.config
        collector = getattr(config, '_deriva_collector', None)
        if collector is None:
            return
        if report.when == "call" and report.failed:
            longrepr = str(report.longrepr) if report.longrepr else ""
            collector.add_failure(item.nodeid, longrepr)
    except Exception as ex:
        print(f"deriva_oraculos: aviso interno ({ex})")


def pytest_sessionfinish(session, exitstatus):
    try:
        config = session.config
        collector = getattr(config, '_deriva_collector', None)
        if collector is None:
            return

        rootdir = collector.rootdir
        baseline = collector.baseline
        rojos_previos = baseline.get("rojos", {})

        # Clasificar cada rojo del baseline
        resultados = {}
        # Los que están en el baseline
        for nodeid, previo in rojos_previos.items():
            if nodeid in collector.fallos:
                h_actual = collector.fallos[nodeid]["huella"]
                cls = clasificar(previo, True, h_actual)
            else:
                cls = clasificar(previo, False, None)
            resultados[nodeid] = cls

        # Los nuevos (no en el baseline)
        for nodeid in collector.fallos:
            if nodeid not in rojos_previos:
                resultados[nodeid] = clasificar(None, True, None)

        config._deriva_resultados = resultados

        # Escribir estado local
        local_dir = os.path.join(rootdir, CARPETA_LOCAL)
        os.makedirs(local_dir, exist_ok=True)
        hoy = date.today().isoformat()
        ultimo = {
            "fecha": hoy,
            "fallos": collector.fallos,
            "resultados": resultados,
        }
        with open(os.path.join(local_dir, "ultimo.json"), 'w', encoding='utf-8') as f:
            json.dump(ultimo, f, indent=2, ensure_ascii=False)

        # --deriva-actualizar: reescribir el baseline versionado
        if config.getoption("--deriva-actualizar"):
            nuevo_baseline = {
                "version": 1,
                "generado": datetime.now().isoformat(timespec='seconds'),
                "commit": _get_commit_short(rootdir),
                "rojos": {},
            }
            # Conservar los que siguen fallando
            for nodeid, fallo in collector.fallos.items():
                previo = rojos_previos.get(nodeid)
                if previo:
                    nuevo_baseline["rojos"][nodeid] = {
                        "huella": fallo["huella"],
                        "valores": fallo["valores"],
                        "primera_vez": previo.get("primera_vez", hoy),
                        "ultima_vez": hoy,
                        "corridas": previo.get("corridas", 0) + 1,
                    }
                else:
                    nuevo_baseline["rojos"][nodeid] = {
                        "huella": fallo["huella"],
                        "valores": fallo["valores"],
                        "primera_vez": hoy,
                        "ultima_vez": hoy,
                        "corridas": 1,
                    }
            baseline_path = collector.baseline_path
            with open(baseline_path, 'w', encoding='utf-8') as f:
                json.dump(nuevo_baseline, f, indent=2, ensure_ascii=False)
    except Exception as ex:
        print(f"deriva_oraculos: aviso interno ({ex})")


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    try:
        collector = getattr(config, '_deriva_collector', None)
        if collector is None:
            return
        resultados = getattr(config, '_deriva_resultados', {})
        if not resultados:
            return

        rojos_previos = collector.baseline.get("rojos", {})
        lineas = []

        # MOVIDO
        for nodeid, cls in sorted(resultados.items()):
            if cls == "movido":
                previo = rojos_previos.get(nodeid, {})
                actual = collector.fallos.get(nodeid, {})
                antes = previo.get("valores", [])
                ahora = actual.get("valores", [])
                ultima = previo.get("ultima_vez", "?")
                lineas.append(f"🔴 MOVIDO: {nodeid}")
                lineas.append(f"   antes {antes} → ahora {ahora}  (baseline: {ultima})")
                lineas.append("   Este rojo cambió de valor: NO es «el rojo de siempre». Verifícalo antes de re-correr.")

        # IGUAL
        for nodeid, cls in sorted(resultados.items()):
            if cls == "igual":
                previo = rojos_previos.get(nodeid, {})
                corridas = previo.get("corridas", 0)
                lineas.append(f"⚪ IGUAL: {nodeid} (corrida #{corridas})")

        # NUEVO
        for nodeid, cls in sorted(resultados.items()):
            if cls == "nuevo":
                lineas.append(f"🆕 NUEVO ROJO: {nodeid}")

        # SANADO
        for nodeid, cls in sorted(resultados.items()):
            if cls == "sanado":
                lineas.append(f"✅ SANADO: {nodeid} (estaba rojo en el baseline; si el arreglo fue deliberado, corre")
                lineas.append("   pytest --deriva-actualizar y commitea el baseline)")

        if lineas:
            terminalreporter.write_line("======== Deriva de oráculos ========")
            for linea in lineas:
                terminalreporter.write_line(linea)
            terminalreporter.write_line("======== fin deriva ========")
    except Exception as ex:
        print(f"deriva_oraculos: aviso interno ({ex})")


def _get_commit_short(rootdir):
    """Obtiene el commit HEAD corto. Si no hay git, devuelve 'unknown'."""
    try:
        import subprocess
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True,
            cwd=rootdir, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"
