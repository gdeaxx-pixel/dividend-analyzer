"""Diagnóstico de un 1042-S que la calculadora no lee, sin imprimir nada del documento.

Para soporte: el cliente (o Daniel) lo corre sobre su PDF y pega la salida. La salida es
SOLO conteos y sí/no — ni texto, ni dígitos, ni nombres —, así que nunca hace falta pedirle
el PDF a nadie. Un 1042-S trae nombre, dirección, TIN y número de cuenta del titular.

Uso:
    ./.venv/bin/python tools/diagnostico_1042s.py ruta/al/1042-S.pdf
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logic  # noqa: E402

_ETIQUETA = "UNIQUE FORM IDENTIFIER"
_UFI_SOLO_ESPACIOS = re.compile(r"((?:\d\s){9}\d)\s*UNIQUE FORM IDENTIFIER")


def _texto(pdf_bytes, **kw):
    import pdfplumber
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return len(pdf.pages), "".join((p.extract_text(**kw) or "") + "\n" for p in pdf.pages)


def diagnosticar(pdf_bytes) -> list:
    """Líneas de diagnóstico: solo conteos y sí/no."""
    lineas = []
    try:
        paginas, por_defecto = _texto(pdf_bytes)
        _, ajustado = _texto(pdf_bytes, x_tolerance=1.5)
    except Exception as e:                                         # noqa: BLE001
        return [f"no se pudo abrir el PDF ({type(e).__name__})"]

    lineas.append(f"páginas: {paginas}")
    lineas.append(f"menciona «1042-S»: {'sí' if '1042-S' in por_defecto else 'no'}")
    for nombre, t in (("tolerancia por defecto", por_defecto), ("tolerancia 1.5", ajustado)):
        lineas.append(
            f"{nombre}: etiquetas de identificador {t.count(_ETIQUETA)}, "
            f"casadas con el patrón de Schwab {len(_UFI_SOLO_ESPACIOS.findall(t))}, "
            f"casadas con el patrón actual {len(logic._UFI_1042S.findall(t))}")
    anios = set(logic._ANIO_CABECERA_1042S.findall(ajustado))
    lineas.append(f"año en la cabecera: {'sí, uno' if len(anios) == 1 else f'{len(anios)} distintos'}")
    lineas.append(f"emitido por TD Ameritrade: {'sí' if 'AMERITRADE' in ajustado.upper() else 'no'}")

    r = logic.parse_1042s_pdf(pdf_bytes)
    if r is None:
        lineas.append("resultado: la calculadora NO lo lee")
    else:
        camino = "por defecto" if logic._parse_1042s_text(por_defecto) else "respaldo 1.5"
        codigos = ", ".join(sorted(f["income_code"] for f in r["forms"]))
        lineas.append(f"resultado: leído ({camino}); formularios {len(r['forms'])}; "
                      f"códigos {codigos}; año fiscal {'sí' if r['tax_year'] else 'no'}; "
                      f"conflictos entre copias {sum(f['conflict'] for f in r['forms'])}")
    return lineas


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    with open(sys.argv[1], "rb") as fh:
        print("\n".join(diagnosticar(fh.read())))
