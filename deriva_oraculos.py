"""Plugin anti-deriva: detecta rojos que cambian de valor sin cambiar de color.

Lección C·15/C·13 (sep-2026): un rojo estable en color puede estar diciendo algo nuevo.
Este plugin guarda la huella numérica de cada fallo en un baseline versionado y en la
siguiente corrida distingue «sigue igual» de «SE MOVIÓ».

Limitación conocida: solo cuenta fallos de la fase ``call`` (report.when == "call" y
report.failed). Skips y errores de setup/teardown quedan fuera.
Un test flaky entra y sale del baseline: el informe lo cantará como 🆕 NUEVO ROJO una
corrida y ✅ SANADO la siguiente. El mecanismo no distingue flaky de deriva real.

El baseline está SEPARADO POR ENTORNO (v2). Motivo, medido el 2026-09-24 en la primera
corrida local tras el merge: el rojo `test_s1_demo_no_hereda_capturas_de_la_sesion_previa`
solo existe SIN `real_examples/` (datos privados de bróker, no versionados). El baseline se
generó en un árbol sin ellos, así que en la máquina de Daniel —donde sí están— el plugin
cantaba ✅ SANADO en cada corrida, por un test que nadie arregló. Peor: su propio consejo
(`--deriva-actualizar`) habría borrado esa entrada, y entonces CI —que corre sin datos
privados, donde ese test SÍ falla— lo habría cantado como 🆕 NUEVO ROJO todos los sábados.

Por eso cada entrada lleva su `entorno` y solo se compara contra las del entorno actual, y
`--deriva-actualizar` reescribe ÚNICAMENTE las entradas del entorno en que corres,
conservando intactas las de los demás. Esto es distinto del flaky de arriba: aquello es ruido
aleatorio, esto era sistemático y direccional — dependía de dónde corrieras.
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
VERSION_BASELINE = 2                       # v2 = rojos separados por entorno
# Línea de cursores de PEP 657: canalón de pytest opcional, y a partir de ahí solo ~ ^ y
# espacios, con al menos un cursor. `[\sE>|]*` no puede tragarse código porque el resto de
# la línea tiene que ser cursores hasta el final.
_ES_CURSOR = re.compile(r'^[\sE>|]*[~^][~^\s]*$')
DIR_DATOS_PRIVADOS = "real_examples"       # symlink a datos de bróker, no versionado


def entorno_actual(rootdir: str) -> str:
    """Identifica el entorno de corrida por lo único que cambia el SET de rojos de esta
    suite: si `real_examples/` está disponible o no.

    Sin esos datos privados hay tests que fallan y con ellos pasan (y ~70 que se saltan),
    así que un rojo del baseline solo es comparable contra una corrida del mismo lado.
    `os.path.isdir` sigue el symlink a propósito: lo que importa es si el destino existe,
    no si el enlace está puesto."""
    return ("con-datos-privados"
            if os.path.isdir(os.path.join(rootdir, DIR_DATOS_PRIVADOS))
            else "sin-datos-privados")


def normalizar(texto: str) -> str:
    """Prepara el texto del fallo para que la huella sea comparable entre máquinas y
    versiones de pytest. En este orden:
    1. quita códigos de color ANSI (`\\x1b\\[[0-9;]*m`);
    2. quita direcciones de memoria (`0x[0-9a-fA-F]+` → `<addr>`);
    3. quita rutas absolutas: de cualquier token con `/` conserva solo el basename
       (`/Users/x/repo/test_a.py` → `test_a.py`; `/home/runner/...` igual);
    4. quita números de línea de referencias `archivo.py:123` → `archivo.py`;
    5. quita las líneas de cursores de PEP 657 (`~~^~~`), que Python >= 3.11 añade bajo la
       expresión que falló y 3.9/3.10 no emiten.
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
    # 5. cursores de PEP 657. Medido el 2026-09-24 con dos intérpretes reales: un fallo con
    #    traceback da huellas DISTINTAS en 3.9 y 3.11 solo por estas líneas, y un `assert`
    #    plano da la misma. Importa porque el baseline se midió en 3.9 y CI corre 3.11: sin
    #    esto, el primer rojo con traceback se cantaría 🔴 MOVIDO sin que nada se moviera.
    #    Solo cae la línea cuyo contenido, quitado el canalón de pytest (`E`, `>`, `|`), son
    #    únicamente cursores — nunca una línea con código que además lleve `^` o `~`.
    texto = '\n'.join(l for l in texto.split('\n') if not _ES_CURSOR.match(l))
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
    """Lee el JSON del baseline. Si no existe o está corrupto, devuelve
    `{"version": VERSION_BASELINE, "rojos": {}}` — NUNCA lanza (un plugin roto no puede
    enrojecer la suite).

    Un baseline de un esquema anterior se devuelve VACÍO y marcado con `esquema_viejo`: sus
    entradas no dicen en qué entorno se midieron, así que compararlas sería justo el falso
    positivo que la v2 viene a cerrar. Se pierde una corrida de detección y el informe lo
    dice en voz alta; es preferible a un ✅ SANADO o un 🆕 NUEVO ROJO inventados."""
    try:
        with open(ruta, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict) or 'rojos' not in data:
            return {"version": VERSION_BASELINE, "rojos": {}}
        if data.get("version") != VERSION_BASELINE:
            return {"version": VERSION_BASELINE, "rojos": {},
                    "esquema_viejo": data.get("version")}
        return data
    except (OSError, json.JSONDecodeError, ValueError):
        return {"version": VERSION_BASELINE, "rojos": {}}


def rojos_del_entorno(baseline: dict, entorno: str) -> dict:
    """Las entradas del baseline medidas en `entorno`. Una entrada sin `entorno` no se
    compara contra nada: no sabemos de qué lado salió."""
    return {nodeid: previo
            for nodeid, previo in baseline.get("rojos", {}).items()
            if isinstance(previo, dict) and previo.get("entorno") == entorno}


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
        parser.addoption(
            "--deriva-entorno",
            default=None,
            help="Fuerza el identificador de entorno en vez de detectarlo.",
        )
    except Exception as ex:
        print(f"deriva_oraculos: aviso interno ({ex})")


class DerivaCollector:
    """Recoge fallos de la fase call y los clasifica contra el baseline."""

    def __init__(self, baseline_path, rootdir, entorno):
        self.baseline_path = baseline_path
        self.rootdir = rootdir
        self.entorno = entorno
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
        entorno = config.getoption("--deriva-entorno") or entorno_actual(rootdir)
        collector = DerivaCollector(baseline_path, rootdir, entorno)
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
        rojos_previos = rojos_del_entorno(baseline, collector.entorno)

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
            "entorno": collector.entorno,
            "fallos": collector.fallos,
            "resultados": resultados,
        }
        with open(os.path.join(local_dir, "ultimo.json"), 'w', encoding='utf-8') as f:
            json.dump(ultimo, f, indent=2, ensure_ascii=False)

        # --deriva-actualizar: reescribir el baseline versionado
        if config.getoption("--deriva-actualizar"):
            entorno = collector.entorno
            nuevo_baseline = {
                "version": VERSION_BASELINE,
                "generado": datetime.now().isoformat(timespec='seconds'),
                "commit": _get_commit_short(rootdir),
                "rojos": {},
            }
            # Las entradas de OTROS entornos se conservan tal cual: esta corrida no vio
            # esos tests en las condiciones en que se midieron, así que no tiene nada que
            # decir sobre ellas. Borrarlas es lo que convertía un refresco local en una
            # alarma perpetua en CI.
            for nodeid, previo in baseline.get("rojos", {}).items():
                if isinstance(previo, dict) and previo.get("entorno") != entorno:
                    nuevo_baseline["rojos"][nodeid] = previo
            # Conservar los que siguen fallando
            for nodeid, fallo in collector.fallos.items():
                previo = rojos_previos.get(nodeid)
                if previo:
                    nuevo_baseline["rojos"][nodeid] = {
                        "entorno": entorno,
                        "huella": fallo["huella"],
                        "valores": fallo["valores"],
                        "primera_vez": previo.get("primera_vez", hoy),
                        "ultima_vez": hoy,
                        "corridas": previo.get("corridas", 0) + 1,
                    }
                else:
                    nuevo_baseline["rojos"][nodeid] = {
                        "entorno": entorno,
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
        esquema_viejo = collector.baseline.get("esquema_viejo")
        if not resultados and esquema_viejo is None:
            return

        rojos_previos = rojos_del_entorno(collector.baseline, collector.entorno)
        lineas = []

        if esquema_viejo is not None:
            lineas.append(f"⚠️  BASELINE DE ESQUEMA v{esquema_viejo}: no se comparó nada esta corrida.")
            lineas.append(f"   La v{VERSION_BASELINE} separa los rojos por entorno y el viejo no dice en cuál se midió.")
            lineas.append(f"   Regenéralo con: pytest --deriva-actualizar   (entorno actual: {collector.entorno})")

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
                lineas.append(f"✅ SANADO: {nodeid}")
                lineas.append(f"   (estaba rojo en el baseline del MISMO entorno, {collector.entorno}; si el arreglo")
                lineas.append("    fue deliberado, corre pytest --deriva-actualizar y commitea el baseline)")

        if lineas:
            # La cabecera NO lleva el entorno: `test_deriva_oraculos.py` la matchea literal
            # y los workflows la usan para recortar el tramo del log (`sed -n '/Deriva de
            # oráculos/,/fin deriva/p'`). El entorno va en su propia línea.
            terminalreporter.write_line("======== Deriva de oráculos ========")
            terminalreporter.write_line(f"   entorno: {collector.entorno}")
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
