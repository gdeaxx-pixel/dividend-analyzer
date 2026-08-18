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
import os
import subprocess
import sys

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
