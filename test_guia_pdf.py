"""La guía paso a paso se descarga desde el propio paso 1 (14-nov).

Daniel: «dale con el botón de descarga». Va dentro de la app y no como enlace a la web: así no
depende de que esa página siga viva ni de que el cliente pase un login justo cuando está
atascado subiendo un archivo, y no se lo lleva a otra pestaña a mitad del proceso.

El PDF se publica a todo el que abra la app, así que estos guards vigilan también que no lleve
datos de ninguna cuenta. Se comprobó antes de subirlo: los ejemplos son inventados (AAAA,
BBBB…) y las ilustraciones están dibujadas, no son capturas de una pantalla real.
"""
import re

import pytest

from ui import carga


def test_la_guia_viaja_con_la_app():
    assert carga.GUIA_PDF.exists(), f"falta el PDF en {carga.GUIA_PDF}"
    assert carga.GUIA_PDF.suffix == ".pdf"
    assert carga.GUIA_PDF.stat().st_size > 50_000, "el PDF parece truncado"


def test_el_paso_1_ofrece_descargarla():
    fuente = (carga.GUIA_PDF.parent.parent.parent / "ui" / "carga.py").read_text(encoding="utf-8")
    bloque = fuente[fuente.index("def render_bloque_transacciones"):]
    assert "_boton_guia()" in bloque, "el botón no se dibuja en el paso 1"


def test_sin_el_pdf_el_paso_1_sigue_funcionando(monkeypatch, tmp_path):
    """Un deploy que se deje el archivo no puede tumbar la carga entera."""
    llamadas = []
    monkeypatch.setattr(carga, "GUIA_PDF", tmp_path / "no-esta.pdf")
    monkeypatch.setattr(carga.st, "download_button", lambda *a, **k: llamadas.append(a))
    carga._boton_guia()
    assert not llamadas, "intentó dibujar el botón sin tener el archivo"


def test_el_boton_entrega_el_pdf_entero(monkeypatch):
    entregado = {}

    def falso(label, data, **k):
        entregado["label"], entregado["data"], entregado["kw"] = label, data, k

    monkeypatch.setattr(carga.st, "download_button", falso)
    carga._guia_bytes.clear()
    carga._boton_guia()
    assert entregado["data"][:5] == b"%PDF-", "lo que se descarga no es un PDF"
    assert len(entregado["data"]) == carga.GUIA_PDF.stat().st_size
    assert entregado["kw"]["file_name"].endswith(".pdf")
    assert entregado["kw"]["mime"] == "application/pdf"


_PII = {
    "número de cuenta": r"\b\d{8,}\b",
    "cuenta con guiones": r"\b\d{3,4}-\d{4,}\b",
    "correo": r"[\w.+-]+@[\w-]+\.\w+",
    "nombre del titular": r"(?i)\b(zambrano|gdeaxx)\b",
}


@pytest.mark.parametrize("nombre, patron", list(_PII.items()))
def test_la_guia_no_publica_datos_de_ninguna_cuenta(nombre, patron):
    """Se sirve a cualquiera que abra la app: si alguien reemplaza el PDF por uno con capturas
    reales, esto lo caza antes del deploy."""
    pdfplumber = pytest.importorskip("pdfplumber")
    import logging
    logging.disable(logging.ERROR)
    try:
        with pdfplumber.open(carga.GUIA_PDF) as pdf:
            texto = "\n".join(p.extract_text() or "" for p in pdf.pages)
    finally:
        logging.disable(logging.NOTSET)
    hallados = re.findall(patron, texto)
    assert not hallados, f"la guía trae {nombre}: {hallados[:3]}"
