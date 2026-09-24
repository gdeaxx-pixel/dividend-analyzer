"""Tests del plugin anti-deriva (deriva_oraculos).

Todos usan pytester con ``-p deriva_oraculos --deriva-baseline=<tmp>`` para no
tocar el baseline real del repo. Se usa ``runpytest_subprocess`` para que cada
corrida sea un proceso independiente.
"""

import json
import os
import shutil
import textwrap

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


def test_detecta_movimiento_de_valor(testdir, monkeypatch):
    """Reproduce C·15 en miniatura: falla con 41.60, se actualiza baseline,
    se cambia a 56.65 → segunda corrida dice MOVIDO."""
    _setup_testdir(testdir, monkeypatch)
    ruta_baseline = str(testdir.tmpdir.join("bl.json"))

    # Primera corrida: assert falla con un valor
    testdir.makepyfile(test_sample=textwrap.dedent("""\
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
    testdir.makepyfile(test_sample=textwrap.dedent("""\
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
    testdir.makepyfile(test_sample=textwrap.dedent("""\
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
    testdir.makepyfile(test_sample=textwrap.dedent("""\
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
