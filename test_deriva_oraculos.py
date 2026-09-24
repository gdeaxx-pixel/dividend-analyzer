"""Tests del plugin anti-deriva (deriva_oraculos).

Todos usan pytester con ``-p deriva_oraculos --deriva-baseline=<tmp>`` para no
tocar el baseline real del repo. Se usa ``runpytest_subprocess`` para que cada
corrida sea un proceso independiente.
"""

import json
import os
import shutil
import textwrap
import time

import pytest

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def _setup_testdir(testdir, monkeypatch):
    """Configura testdir para que el subproceso encuentre deriva_oraculos."""
    # Copiar el plugin al tmpdir
    src = os.path.join(REPO_ROOT, "deriva_oraculos.py")
    dst = str(testdir.tmpdir.join("deriva_oraculos.py"))
    shutil.copy2(src, dst)
    # PYTHONPATH apunta al tmpdir para que el subprocess encuentre la copia
    monkeypatch.setenv('PYTHONPATH', str(testdir.tmpdir))


def _reescribir(testdir, **ficheros):
    """`makepyfile` + invalidar el bytecode cacheado. Úsalo siempre que un test escriba
    DOS versiones del mismo fichero.

    Trampa medida el 2026-09-24: Python invalida un `.pyc` por (mtime en SEGUNDOS, tamaño
    en bytes) del fuente. Las dos versiones de `test_sample.py` de
    `test_nuevo_rojo_y_sanado` pesan 67 bytes las dos, y las de
    `test_detecta_movimiento_de_valor` también coinciden; si las dos escrituras caen en el
    mismo segundo de reloj —lo normal cuando la primera corrida es rápida— la segunda
    corrida REUTILIZA el bytecode de la primera. El síntoma es desconcertante porque
    pytest muestra el fuente NUEVO y ejecuta el VIEJO:

        def test_a():
        >       assert True
        E       assert 1.0 == 2.0

    Reproducido a voluntad forzando `os.utime` al mismo mtime (falla 100%) y descartado con
    mtime natural. Adelantar el mtime rompe el empate de forma determinista.
    """
    ruta = testdir.makepyfile(**ficheros)
    futuro = time.time() + 2
    for f in ([ruta] if not isinstance(ruta, (list, tuple)) else ruta):
        os.utime(str(f), (futuro, futuro))
    cache = testdir.tmpdir.join("__pycache__")
    if cache.check():
        cache.remove(rec=1)
    return ruta


def test_detecta_movimiento_de_valor(testdir, monkeypatch):
    """Reproduce C·15 en miniatura: falla con 41.60, se actualiza baseline,
    se cambia a 56.65 → segunda corrida dice MOVIDO."""
    _setup_testdir(testdir, monkeypatch)
    ruta_baseline = str(testdir.tmpdir.join("bl.json"))

    # Primera corrida: assert falla con un valor
    _reescribir(testdir, test_sample=textwrap.dedent("""\
        def test_oraculo():
            obtenido = 99.99
            assert 41.60 == obtenido
    """))
    ret = testdir.runpytest_subprocess(
        "-p", "deriva_oraculos",
        "--deriva-baseline", ruta_baseline,
        "--deriva-actualizar", "-q")
    ret.stdout.fnmatch_lines(["======== Deriva de oráculos ========"])
    ret.stdout.fnmatch_lines(["*NUEVO ROJO*"])
    assert ret.ret != 0
    assert os.path.exists(ruta_baseline)

    # Segunda corrida: el valor esperado cambió (simula drift del refresco)
    _reescribir(testdir, test_sample=textwrap.dedent("""\
        def test_oraculo():
            obtenido = 99.99
            assert 56.65 == obtenido
    """))
    ret2 = testdir.runpytest_subprocess(
        "-p", "deriva_oraculos",
        "--deriva-baseline", ruta_baseline, "-q")
    ret2.stdout.fnmatch_lines(["======== Deriva de oráculos ========"])
    ret2.stdout.fnmatch_lines(["*MOVIDO*"])
    ret2.stdout.fnmatch_lines(["*fin deriva*"])
    assert ret2.ret != 0


def test_rojo_estable_no_se_reporta_como_movido(testdir, monkeypatch):
    """El mismo fallo dos veces → IGUAL, nunca MOVIDO."""
    _setup_testdir(testdir, monkeypatch)
    ruta_baseline = str(testdir.tmpdir.join("bl.json"))

    body = textwrap.dedent("""\
        def test_oraculo():
            assert 1.50 == 2.50
    """)
    testdir.makepyfile(test_sample=body)
    ret = testdir.runpytest_subprocess(
        "-p", "deriva_oraculos",
        "--deriva-baseline", ruta_baseline,
        "--deriva-actualizar", "-q")
    ret.stdout.fnmatch_lines(["======== Deriva de oráculos ========"])
    assert ret.ret != 0

    # Segunda corrida con el mismo código
    ret2 = testdir.runpytest_subprocess(
        "-p", "deriva_oraculos",
        "--deriva-baseline", ruta_baseline, "-q")
    ret2.stdout.fnmatch_lines(["======== Deriva de oráculos ========"])
    ret2.stdout.fnmatch_lines(["*IGUAL*"])
    out = "\n".join(ret2.stdout.lines)
    assert "MOVIDO" not in out


def test_direcciones_de_memoria_no_generan_falso_movimiento(testdir, monkeypatch):
    """Un fallo con object at 0x… distinto en cada corrida → NO movido."""
    _setup_testdir(testdir, monkeypatch)
    ruta_baseline = str(testdir.tmpdir.join("bl.json"))

    body = textwrap.dedent("""\
        def test_oraculo():
            obj = object()
            msg = "fallo en " + repr(obj) + " con valor 3.14"
            assert False, msg
    """)
    testdir.makepyfile(test_sample=body)
    ret = testdir.runpytest_subprocess(
        "-p", "deriva_oraculos",
        "--deriva-baseline", ruta_baseline,
        "--deriva-actualizar", "-q")
    ret.stdout.fnmatch_lines(["======== Deriva de oráculos ========"])
    assert ret.ret != 0

    # Segunda corrida: mismo código, la dirección de memoria será distinta
    ret2 = testdir.runpytest_subprocess(
        "-p", "deriva_oraculos",
        "--deriva-baseline", ruta_baseline, "-q")
    ret2.stdout.fnmatch_lines(["======== Deriva de oráculos ========"])
    out = "\n".join(ret2.stdout.lines)
    assert "MOVIDO" not in out
    ret2.stdout.fnmatch_lines(["*IGUAL*"])


def test_nuevo_rojo_y_sanado(testdir, monkeypatch):
    """Rojo ausente del baseline → NUEVO; rojo del baseline que pasa a verde → SANADO."""
    _setup_testdir(testdir, monkeypatch)
    ruta_baseline = str(testdir.tmpdir.join("bl.json"))

    # Primera corrida: test_a falla, test_b pasa
    _reescribir(testdir, test_sample=textwrap.dedent("""\
        def test_a():
            assert 1.0 == 2.0

        def test_b():
            assert True
    """))
    ret = testdir.runpytest_subprocess(
        "-p", "deriva_oraculos",
        "--deriva-baseline", ruta_baseline,
        "--deriva-actualizar", "-q")
    ret.stdout.fnmatch_lines(["======== Deriva de oráculos ========"])
    ret.stdout.fnmatch_lines(["*NUEVO ROJO*"])

    # Segunda corrida: test_a pasa, test_b falla
    _reescribir(testdir, test_sample=textwrap.dedent("""\
        def test_a():
            assert True

        def test_b():
            assert 1.0 == 9.9
    """))
    ret2 = testdir.runpytest_subprocess(
        "-p", "deriva_oraculos",
        "--deriva-baseline", ruta_baseline, "-q")
    ret2.stdout.fnmatch_lines(["======== Deriva de oráculos ========"])
    ret2.stdout.fnmatch_lines(["*SANADO*"])
    ret2.stdout.fnmatch_lines(["*NUEVO ROJO*"])


def test_flag_actualizar_reescribe_el_baseline(testdir, monkeypatch):
    """Tras --deriva-actualizar, el JSON existe, trae huella, valores y corridas."""
    _setup_testdir(testdir, monkeypatch)
    ruta_baseline = str(testdir.tmpdir.join("bl.json"))

    testdir.makepyfile(test_sample=textwrap.dedent("""\
        def test_oraculo():
            assert 1.5 == 2.5
    """))
    ret = testdir.runpytest_subprocess(
        "-p", "deriva_oraculos",
        "--deriva-baseline", ruta_baseline,
        "--deriva-actualizar", "-q")
    assert ret.ret != 0

    assert os.path.exists(ruta_baseline)
    with open(ruta_baseline) as f:
        data = json.load(f)
    assert "rojos" in data
    assert len(data["rojos"]) >= 1
    for nodeid, entry in data["rojos"].items():
        assert "huella" in entry
        assert "valores" in entry
        assert "corridas" in entry


def test_baseline_corrupto_no_rompe_la_suite(testdir, monkeypatch):
    """Baseline con JSON inválido → la corrida termina, el informe avisa sin excepciones."""
    _setup_testdir(testdir, monkeypatch)
    ruta_baseline = str(testdir.tmpdir.join("bl.json"))

    # Escribir JSON corrupto
    with open(ruta_baseline, 'w') as f:
        f.write("{rojos: INVALIDO !!!")

    testdir.makepyfile(test_sample=textwrap.dedent("""\
        def test_oraculo():
            assert 1.5 == 2.5
    """))
    ret = testdir.runpytest_subprocess(
        "-p", "deriva_oraculos",
        "--deriva-baseline", ruta_baseline, "-q")
    # La suite termina (no crashea el plugin)
    ret.stdout.fnmatch_lines(["======== Deriva de oráculos ========"])
    ret.stdout.fnmatch_lines(["*fin deriva*"])
    # El test de muestra falla normalmente
    assert ret.ret != 0


# ── v2 · el baseline está separado por entorno ────────────────────────────────
#
# Reproduce el falso positivo medido el 2026-09-24: el baseline se generó en un árbol
# SIN `real_examples/`, y en la máquina de Daniel —donde sí están— el mismo test pasa.
# Antes de la v2 eso salía como ✅ SANADO en cada corrida, y seguir el consejo del aviso
# (`--deriva-actualizar`) borraba la entrada, convirtiendo el falso positivo local en una
# alarma perpetua en CI.

def _escribir_baseline(ruta, rojos, version=2):
    contenido = {"version": version, "generado": "2026-09-24T00:00:00",
                 "commit": "abc1234", "rojos": rojos}
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(contenido, f)


_ENTRADA_A = {
    "entorno": "entorno-A",
    "huella": "0123456789abcdef",
    "valores": [],
    "primera_vez": "2026-09-23",
    "ultima_vez": "2026-09-23",
    "corridas": 4,
}

_TEST_QUE_PASA = "def test_oraculo():\n    assert True\n"
_TEST_QUE_FALLA = "def test_oraculo():\n    assert 1.5 == 2.5\n"


def test_un_rojo_de_otro_entorno_no_se_canta_como_sanado(testdir, monkeypatch):
    """El caso real: entrada medida en A, corrida en B donde el test pasa.

    Sin la v2 esto imprimía ✅ SANADO por un test que nadie arregló."""
    _setup_testdir(testdir, monkeypatch)
    ruta_baseline = str(testdir.tmpdir.join("bl.json"))
    _escribir_baseline(ruta_baseline, {"test_sample.py::test_oraculo": dict(_ENTRADA_A)})
    testdir.makepyfile(test_sample=_TEST_QUE_PASA)

    ret = testdir.runpytest_subprocess(
        "-p", "deriva_oraculos", "--deriva-baseline", ruta_baseline,
        "--deriva-entorno", "entorno-B", "-q")
    assert ret.ret == 0
    assert "SANADO" not in ret.stdout.str()


def test_control_en_el_mismo_entorno_si_canta_sanado(testdir, monkeypatch):
    """Control del test de arriba. Sin esto, «no dice SANADO» pasaría también si el
    plugin se hubiera quedado mudo del todo: aquí el ÚNICO cambio es el entorno."""
    _setup_testdir(testdir, monkeypatch)
    ruta_baseline = str(testdir.tmpdir.join("bl.json"))
    _escribir_baseline(ruta_baseline, {"test_sample.py::test_oraculo": dict(_ENTRADA_A)})
    testdir.makepyfile(test_sample=_TEST_QUE_PASA)

    ret = testdir.runpytest_subprocess(
        "-p", "deriva_oraculos", "--deriva-baseline", ruta_baseline,
        "--deriva-entorno", "entorno-A", "-q")
    assert ret.ret == 0
    ret.stdout.fnmatch_lines(["*SANADO*"])


def test_actualizar_conserva_las_entradas_de_otros_entornos(testdir, monkeypatch):
    """La trampa gorda: refrescar el baseline desde un entorno NO puede borrar lo medido
    en otro. Si se borra, CI canta 🆕 NUEVO ROJO para siempre por un test que nunca se
    rompió."""
    _setup_testdir(testdir, monkeypatch)
    ruta_baseline = str(testdir.tmpdir.join("bl.json"))
    _escribir_baseline(ruta_baseline, {"test_sample.py::test_oraculo": dict(_ENTRADA_A)})
    testdir.makepyfile(test_otro=_TEST_QUE_FALLA)

    ret = testdir.runpytest_subprocess(
        "-p", "deriva_oraculos", "--deriva-baseline", ruta_baseline,
        "--deriva-entorno", "entorno-B", "--deriva-actualizar", "-q")
    assert ret.ret != 0

    with open(ruta_baseline, encoding='utf-8') as f:
        nuevo = json.load(f)
    assert nuevo["version"] == 2
    # la entrada ajena sobrevive intacta
    assert nuevo["rojos"]["test_sample.py::test_oraculo"] == _ENTRADA_A
    # y el rojo de esta corrida entra sellado con SU entorno
    assert nuevo["rojos"]["test_otro.py::test_oraculo"]["entorno"] == "entorno-B"


def test_baseline_de_esquema_viejo_no_se_compara_y_lo_dice(testdir, monkeypatch):
    """Un baseline v1 no dice en qué entorno se midió: compararlo es justo el falso
    positivo que la v2 cierra. Se avisa y no se clasifica nada."""
    _setup_testdir(testdir, monkeypatch)
    ruta_baseline = str(testdir.tmpdir.join("bl.json"))
    viejo = {k: v for k, v in _ENTRADA_A.items() if k != "entorno"}
    _escribir_baseline(ruta_baseline, {"test_sample.py::test_oraculo": viejo}, version=1)
    testdir.makepyfile(test_sample=_TEST_QUE_PASA)

    ret = testdir.runpytest_subprocess(
        "-p", "deriva_oraculos", "--deriva-baseline", ruta_baseline, "-q")
    assert ret.ret == 0
    ret.stdout.fnmatch_lines(["*BASELINE DE ESQUEMA v1*"])
    assert "SANADO" not in ret.stdout.str()


def test_entorno_actual_distingue_por_los_datos_privados(tmp_path):
    """La detección en sí: los tests de arriba fuerzan el entorno con `--deriva-entorno`,
    así que sin este `entorno_actual` podría devolver una constante y nadie se enteraría.

    Se comprueba también a través de un SYMLINK, que es como `real_examples/` existe de
    verdad en la máquina de Daniel (apunta a ~/.local/share/dividend-analyzer)."""
    import deriva_oraculos

    assert deriva_oraculos.entorno_actual(str(tmp_path)) == "sin-datos-privados"

    real = tmp_path / "destino"
    real.mkdir()
    (tmp_path / "real_examples").symlink_to(real, target_is_directory=True)
    assert deriva_oraculos.entorno_actual(str(tmp_path)) == "con-datos-privados"

    # symlink roto = los datos NO están: cuenta como sin datos privados
    (tmp_path / "real_examples").unlink()
    (tmp_path / "real_examples").symlink_to(tmp_path / "no-existe", target_is_directory=True)
    assert deriva_oraculos.entorno_actual(str(tmp_path)) == "sin-datos-privados"


# ── la huella no depende de la versión de Python ──────────────────────────────

_LONGREPR_39 = """    def test_con_traceback():
>       assert _nivel1(3.5) == 1.0

test_muestras.py:14:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
    def _nivel2(x):
>       return x / 0
E       ZeroDivisionError: float division by zero

test_muestras.py:6: ZeroDivisionError
"""

# lo mismo en 3.11: idéntico salvo las líneas de cursores que añade PEP 657
_LONGREPR_311 = """    def test_con_traceback():
>       assert _nivel1(3.5) == 1.0
               ~~~~~~~^^^^^

test_muestras.py:14:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
    def _nivel2(x):
>       return x / 0
           ~~^~~
E       ZeroDivisionError: float division by zero

test_muestras.py:6: ZeroDivisionError
"""


def test_la_huella_no_cambia_entre_python_39_y_311():
    """Mismo fallo, distinto intérprete → MISMA huella.

    Medido el 2026-09-24 con dos intérpretes reales (3.9.6 y 3.11.15) corriendo el plugin
    sobre el mismo test: un fallo con traceback daba huellas distintas y un `assert` plano
    la misma. La única diferencia del texto son los cursores de PEP 657.

    Importa porque el baseline se midió en 3.9 y CI corre 3.11 (y producción 3.11.16): sin
    esto, el primer rojo con traceback se canta 🔴 MOVIDO sin que nada se haya movido.
    """
    import deriva_oraculos

    nodeid = "test_muestras.py::test_con_traceback"
    assert deriva_oraculos.huella(nodeid, _LONGREPR_39) == \
           deriva_oraculos.huella(nodeid, _LONGREPR_311)


def test_no_se_come_lineas_de_codigo_que_contienen_cursores():
    """Control de sobre-borrado: la regla solo puede tragarse líneas que SEAN cursores.

    Sin este control, un filtro demasiado goloso («quita todo lo que tenga ^ o ~») pasaría
    el test de arriba y a la vez borraría código real, haciendo que dos fallos DISTINTOS
    compartieran huella — un 🔴 MOVIDO que nunca se reportaría.
    """
    import deriva_oraculos

    con_xor = "E       assert 6 ^ 3 == 5\n"
    con_tilde = "E       assert ~x == y\n"
    # y el ancla del final: una línea que EMPIEZA por cursores pero sigue con texto no es
    # un cursor. Sin el `$` de la regex, esta se borraría (mutante M3).
    empieza_con_cursor = "E       ^^^ este texto importa\n"
    for texto in (con_xor, con_tilde, empieza_con_cursor):
        assert "importa" in deriva_oraculos.normalizar(texto) or \
               "assert" in deriva_oraculos.normalizar(texto), texto

    # y dos fallos que solo se diferencian en esa línea NO pueden compartir huella
    assert deriva_oraculos.huella("t::x", con_xor) != deriva_oraculos.huella("t::x", con_tilde)
