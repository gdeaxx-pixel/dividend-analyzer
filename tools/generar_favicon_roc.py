#!/usr/bin/env python3
"""Genera `ui/assets/roc_favicon.png` (64x64, RGBA) desde la reja del sprite de ROC.

La reja sale de `ui/componentes/roc_sprite.js` (`rocGrid({})`, estado por defecto) vía node, así
que el favicon y el búho del encabezado no pueden divergir. Paleta del tema claro. Sin flags:
escribe siempre ese archivo.
"""
import json
import os
import subprocess

from PIL import Image

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPRITE = os.path.join(_RAIZ, "ui", "componentes", "roc_sprite.js")
_SALIDA = os.path.join(_RAIZ, "ui", "assets", "roc_favicon.png")

_PALETA = {
    "B": (0x02, 0x1C, 0x36, 255),
    "T": (0x02, 0x1C, 0x36, 255),
    "W": (0x33, 0x47, 0x5A, 255),
    "L": (0x33, 0x47, 0x5A, 255),
    "E": (0xFF, 0xFF, 0xFF, 255),
    "P": (0x00, 0x64, 0x97, 255),
    "K": (0xA0, 0x6A, 0x1A, 255),
    "F": (0xA0, 0x6A, 0x1A, 255),
    "C": (0xD5, 0xE0, 0xEA, 255),
}


def _reja() -> list:
    js = ("var m = require(%s); console.log(JSON.stringify(m.rocGrid({}).map(function (r) "
          "{ return r.join(''); })));" % json.dumps(_SPRITE))
    salida = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
    return json.loads(salida.stdout)


def main() -> None:
    filas = _reja()
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    for y, fila in enumerate(filas):
        for x, letra in enumerate(fila):
            if letra in _PALETA:
                img.putpixel((x, y), _PALETA[letra])
    img = img.resize((64, 64), Image.NEAREST)
    img.save(_SALIDA)


if __name__ == "__main__":
    main()
