"""El contrato «el demo genera el componente»: dónde sigue vivo y dónde ya no.

Seis componentes (`cashflow`, `comparacion`, `comparacion_real`, `hoja`, `metodo`,
`metodologia`) nacieron generados desde el demo del artifact y abrían con un banner que
decía «GENERADO POR … NO EDITAR A MANO. Fuente: el demo del artifact». Dejó de ser cierto
cuando las fases 3.3a/3.3b los cablearon a `{{DATA_JSON}}`: desde entonces se mantienen a
mano, el demo ya no es su fuente, y regenerarlos borraría el cableado a datos reales.

Un banner que miente es peor que no tener banner: invita justo al accidente que dice
prevenir. Estos tests fijan las dos mitades de la reparación —el texto retirado y el
gatillo desarmado— y, sobre todo, protegen el contrato que SÍ sigue vivo, para que
«retirar banners» no se lea algún día como «aquí ya nada se genera».
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

BASE = os.path.dirname(__file__)
COMPONENTES = os.path.join(BASE, "ui", "componentes")
TOOLS = os.path.join(BASE, "tools")

# Los seis cuyo contrato murió al cablearlos a datos vivos.
DESARMADOS = ["cashflow", "comparacion", "comparacion_real", "hoja", "metodo", "metodologia"]
# Los dos que siguen generándose de verdad. `metodo_real` lo genera su propio extractor
# (el panel y el script son del extractor, no del demo) y `design_system` deriva taxonomía
# y tokens del demo. Los dos pasan `--check`, y ese es justo el punto.
VIVOS = ["metodo_real", "design_system"]


def _leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def test_ningun_componente_desarmado_conserva_el_banner_falso():
    for nombre in DESARMADOS:
        html = _leer(os.path.join(COMPONENTES, f"{nombre}.html"))
        assert "NO EDITAR A MANO" not in html, (
            f"{nombre}.html volvió a abrir con «NO EDITAR A MANO»: es falso desde que el "
            "componente se cableó a datos reales, y el banner invita a regenerarlo — que "
            "es exactamente el accidente que borraría el cableado")


def test_el_banner_nuevo_dice_de_donde_viene_y_que_sigue_vivo():
    """Retirar la mentira no puede dejar el hueco: quien abra el archivo tiene que
    entender por qué se mantiene a mano y qué contrato sí sigue generándose."""
    for nombre in DESARMADOS:
        html = _leer(os.path.join(COMPONENTES, f"{nombre}.html"))
        cabecera = html[:1200]
        assert "extract_design_system.py" in cabecera, (
            f"{nombre}.html no menciona el contrato que sí sigue vivo")
        assert "{{DATA_JSON}}" in cabecera, (
            f"{nombre}.html no explica que se cableó a datos reales")


def test_los_seis_extractores_no_escriben():
    """El banner y el gatillo son la misma reparación: retirar el texto y dejar el script
    capaz de sobrescribir deja media mentira en pie."""
    for nombre in DESARMADOS:
        r = subprocess.run([sys.executable, os.path.join(TOOLS, f"extract_{nombre}.py")],
                           capture_output=True, text=True)
        assert r.returncode != 0, (
            f"extract_{nombre}.py volvió a salir con 0 — ¿volvió a escribir el componente?")
        assert "ya NO escribe" in r.stdout or "ya NO escribe" in r.stderr, (
            f"extract_{nombre}.py no explica por qué no corre")


def test_el_extractor_desarmado_no_reintroduce_el_banner_falso():
    """Aunque no escriba: si alguien lo re-arma, no puede volver a estampar el banner que
    este trabajo retiró."""
    for nombre in DESARMADOS:
        src = _leer(os.path.join(TOOLS, f"extract_{nombre}.py"))
        assert "NO EDITAR A MANO" not in src, (
            f"extract_{nombre}.py todavía genera el banner falso")


def test_los_contratos_vivos_siguen_pasando_su_check():
    """La contracara del test anterior, y la que importa más: `metodo_real` y la taxonomía
    SÍ se generan. Si alguien «termina el trabajo» desarmándolos también, esto cae."""
    for nombre in VIVOS:
        r = subprocess.run(
            [sys.executable, os.path.join(TOOLS, f"extract_{nombre}.py"), "--check"],
            capture_output=True, text=True)
        assert r.returncode == 0, (
            f"extract_{nombre}.py --check dejó de pasar: ese contrato SÍ está vivo\n"
            f"{r.stdout}{r.stderr}")
        assert "OK" in r.stdout


# ── Guard de sintaxis: el JS de los componentes tiene que PARSEAR ────────────────────
#
# Nace del #84. Al retirar 4 sub-vistas de `metodo.html` (#83), el corte se comió también
# el `})();` que cerraba `initMetodo()` — en el original venían dos cierres seguidos. El
# `SyntaxError: Unexpected end of input` mató el script ENTERO al parsear: tablas y gráfica
# en blanco, consola limpia, cero tests rojos. Los tests de este repo comparan substrings
# del HTML y por construcción no pueden ver eso.
#
# El #84 respondió con un balance de llaves sobre `metodo.html`
# (`test_metodo_serie.py::test_el_script_principal_del_componente_es_javascript_valido`).
# Ese test se queda —es el piso que no depende de nada externo— pero no basta, y está
# medido: sobre tres mutantes con la forma del bug real, el balance caza 1 de 3 y
# `node --check` caza 3 de 3. El mutante que el balance no ve —cortar la rama `if` de un
# `if/else` dejando un `else {` huérfano— es la forma EXACTA del #84; aquella vez lo cazó
# sólo porque ese corte además desbalanceaba.
#
# Los componentes se descubren por glob, no por lista: uno nuevo queda cubierto solo.

_PLACEHOLDER = re.compile(r"\{\{\w+\}\}")
_SCRIPT = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S)


def _scripts_de(ruta):
    """Los `<script>` de un componente, listos para parsear.

    Los placeholders de plantilla (`{{DATA_JSON}}`, `{{SERIE_JSON}}`, `{{VISTA_ACTIVA}}`…)
    se sustituyen por `null`: en crudo `var DATA = {{DATA_JSON}};` NO es JavaScript, y un
    guard que fallara por eso estaría reportando la plantilla, no el código. `null` sirve
    igual dentro de una cadena (`"{{TEMA}}"` → `"null"`) que suelto.
    """
    html = _PLACEHOLDER.sub("null", _leer(ruta))
    cuerpos = _SCRIPT.findall(html)
    # Un guard que se salta scripts en silencio no muerde. Si alguien abre un `<script>`
    # que el regex no casa (sin cerrar, anidado en un comentario), la cuenta no cuadra y
    # esto lo dice en vez de dar por revisado lo que nunca miró.
    assert len(cuerpos) == html.count("<script"), (
        f"{os.path.basename(ruta)}: hay {html.count('<script')} etiquetas <script> pero "
        f"sólo pude extraer {len(cuerpos)} — el guard estaría dando por buenas las que no ve")
    return cuerpos


def _componentes():
    return sorted(glob.glob(os.path.join(COMPONENTES, "*.html")))


def _sin_cadenas_ni_comentarios(js):
    """Quita cadenas ANTES que comentarios, en un solo alternate.

    El orden importa y es el que separa este stripper del que usan los tests de ausencia
    (`re.sub(r"//[^\\n]*", "", html)` a secas): ése se come todo lo que siga a un `//`
    dentro de una cadena. Hoy ningún componente tiene un `https://` en un string, así que
    aquel es seguro por suerte y no por construcción.
    """
    return re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|//[^\n]*|/\*.*?\*/",
                  "", js, flags=re.S)


def test_todos_los_componentes_balancean_sus_delimitadores():
    """El piso, siempre activo: no depende de node, así que no puede saltarse.

    Cubre los 7 componentes, no sólo `metodo.html`. El modo de fallo del #84 es genérico
    —cualquier corte estructural puede comerse un cierre— y hasta ahora el guard miraba
    1 script de 14.
    """
    for ruta in _componentes():
        for i, js in enumerate(_scripts_de(ruta)):
            limpio = _sin_cadenas_ni_comentarios(js)
            for abre, cierra in (("{", "}"), ("(", ")"), ("[", "]")):
                assert limpio.count(abre) == limpio.count(cierra), (
                    f"{os.path.basename(ruta)} script #{i}: desbalance de {abre}{cierra} "
                    f"({limpio.count(abre)} vs {limpio.count(cierra)}) — el JS no parsea y "
                    "TODO el panel muere en blanco, sin error en consola")


@pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node no está en el PATH: el guard de sintaxis NO corrió. Un skip no es un "
           "pass — el balance de delimitadores queda como único piso, y ése sólo caza "
           "1 de cada 3 cortes rotos (ver el comentario de cabecera de este bloque).")
def test_todos_los_componentes_parsean_como_javascript():
    """El techo: `node --check` de verdad, sobre los 14 scripts de los 7 componentes.

    Esto es lo único de la suite que puede ver un `SyntaxError`, que es el único fallo de
    esta familia que el usuario percibe (pantalla en blanco) y el único que no deja rastro
    en ninguna parte.
    """
    rotos = []
    for ruta in _componentes():
        for i, js in enumerate(_scripts_de(ruta)):
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                             encoding="utf-8") as tmp:
                tmp.write(js)
                destino = tmp.name
            try:
                r = subprocess.run(["node", "--check", destino],
                                   capture_output=True, text=True)
            finally:
                os.unlink(destino)
            if r.returncode != 0:
                # El mensaje de node cita la línea del temporal; se recorta a lo útil.
                detalle = "\n".join(r.stderr.strip().split("\n")[:4])
                rotos.append(f"{os.path.basename(ruta)} script #{i}:\n{detalle}")
    assert not rotos, (
        "hay JavaScript que no parsea — el script entero muere al cargar y el panel queda "
        "en blanco sin error visible:\n\n" + "\n\n".join(rotos))


# ── `metodo.html`: superficie retirada (4 sub-vistas, #83) que no puede reaparecer ──────
#
# Reubicados aquí el 2026-08-25 (antes vivían en `test_metodo_data.py`, mezclados con los
# tests del adaptador). Dos de los cinco usaban `re.sub(r"//[^\n]*", "", html)` para
# quitar comentarios antes de buscar texto prohibido — ese stripper se come todo lo que
# siga a un `//` dentro de una cadena. Hoy es seguro porque `metodo.html` no tiene ningún
# `esquema://`, pero es seguro por suerte, no por construcción. Los cinco usan ahora
# `_sin_cadenas_ni_comentarios`, que ya vive en este archivo (guard de sintaxis, arriba) y
# quita cadenas ANTES que comentarios.

_METODO_HTML = os.path.join(COMPONENTES, "metodo.html")


def test_metodo_html_escalera_ratios_ya_no_son_arrays_literales():
    """`ratios`/`ratiosTot` en minúscula a propósito (a diferencia de `MATRIZ`/`TOT`):
    el barrido de `/auditoria-financiera` (bloque 5) sigue rastreando `var
    RATIOS`/`var RATIOS_TOT` en MAYÚSCULA como pendiente-de-portar; ya se portó, así
    que el nombre en minúscula deja de generar ese WARN fantasma sin tener que tocar
    el script del skill (fuera de este repo)."""
    html = _leer(_METODO_HTML)

    # Las vistas 3-5 se retiraron el 2026-08-24: solo sobrevive `ratios`, que el
    # modal de la paradoja sigue leyendo. `ratiosTot`/`var ESC` murieron con ellas.
    assert "var ratios = DATA.ratios" in html
    assert "var ratiosTot" not in html and "var ESC " not in html

    # El patrón viejo: `var RATIOS = [{ t:"CONY", pb:2.54, ... }, ...]` — la copia
    # congelada de la hoja, en MAYÚSCULA. No puede reaparecer, en ningún nombre.
    assert not re.search(r"var (RATIOS|ratios)\s*=\s*\[", html), (
        "`RATIOS`/`ratios` volvió a declararse como array-literal")
    assert not re.search(r't\s*:\s*"CONY"\s*,\s*pb\s*:\s*[\d.]+', html), (
        "encontré un literal tipo `{ t:\"CONY\", pb:N.NN, ... }` — parece RATIOS viejo")


def test_metodo_html_tasa_nra_lee_de_data_no_esta_hardcodeada():
    html = _leer(_METODO_HTML)
    assert "var TASA_NRA = DATA.tasaNra" in html
    assert not re.search(r"var TASA_NRA\s*=\s*0\.3\d*\s*;", html), (
        "`var TASA_NRA` volvió a ser un literal (0.30) en vez de leer DATA.tasaNra")


def test_metodo_html_ym_ya_no_tiene_el_campo_real_congelado():
    """El literal `YM` (fichas del emisor para la vista «Rendimiento vs tasa») se
    retiró con su vista el 2026-08-24. Que vuelva a declararse indicaría que la
    vista regresó sin pasar por la decisión de Daniel."""
    cuerpo = _sin_cadenas_ni_comentarios(_leer(_METODO_HTML))
    assert not re.search(r"var YM\s*=\s*\[", cuerpo), (
        "`var YM` (literal del emisor) volvió al componente — ¿regresó la vista?")
    assert "YM_MEDIDO" not in cuerpo and "ymMedido" not in cuerpo


def test_metodo_html_contraejemplo_ya_no_esta_cableado_a_mano_a_cony():
    """La vista «Payback ≠ ganancia» (donde vivía `renderPayback` y su flag
    «cobró y perdió») se retiró el 2026-08-24. Que vuelva a existir la función
    indicaría que la vista regresó sin pasar por la decisión de Daniel."""
    cuerpo = _sin_cadenas_ni_comentarios(_leer(_METODO_HTML))
    assert "renderPayback" not in cuerpo


def test_metodo_html_tmpaybacknra_ya_no_concatena_un_vivo_con_dos_congelados():
    """El bug aritméticamente roto del traspaso: `fmtMoney(TOT.div)` (vivo, se
    refresca semanal) concatenado con `~$78,182.80`/`~$33,506.91` (mitades de la hoja
    fechada 5/1/2026) en la misma oración — nunca cuadraba. El párrafo vivía en la
    vista «Payback», retirada el 2026-08-24: los literales no pueden volver."""
    html = _leer(_METODO_HTML)
    assert "~$78,182.80" not in html
    assert "~$33,506.91" not in html
