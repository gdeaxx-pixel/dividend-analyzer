"""Tarjeta de resultado del Cash flow: nada se sale del iframe a ningún ancho (2026-10-30).

A 375 px de viewport (iframe de 343) la tarjeta seguía a dos columnas y la pista de los
importes medía 9 px: «PUSISTE $946.» y «TIENES HOY …726» salían cortados por el borde,
porque `html{overflow:hidden}` (`_SIN_SCROLL`) recorta sin barras. A 320, 2 px; y ahí la
línea se cortaba entre «−» y «$10434.24», así que la cifra suelta se leía positiva. Aparte,
el iframe quedaba 14 px corto a cualquier ancho: el margen del cockpit atravesaba el body y
el auto-alto (`body.scrollHeight`) no lo contaba.

Se monta como en la app: lo que `render_cashflow` le pasa a `st.iframe`, en el `srcdoc` de
un iframe dentro de un `.block-container` con los estilos de `ui/chrome.py`, así que el
ancho del iframe sale del viewport igual que en Streamlit y el auto-alto corre. El
documento no basta (`feedback_medicion-dom`): se mide cada línea de texto contra el borde
del iframe y contra su ancestro con `overflow`, y cada importe contra su pista y el borde de
su relleno.
"""
import html

import pytest

from test_cascada_eje import STATS_MSTY, STATS_SCHB, _stats
from ui import componentes
from ui.adapters import cashflow_data
from ui.chrome import _ESTILOS

sync_api = pytest.importorskip("playwright.sync_api")

# 740: teléfono apaisado, iframe de 681 — el último ancho que apila la tarjeta.
ANCHOS = (320, 360, 375, 390, 412, 430, 460, 740, 768, 1280)
# Techo $220,000 (bolsillo + bruto). Bolsillo $120,978 = 0.5499 del techo y capital
# trabajando $121,022 = 0.5501: importes de 10 caracteres a cada lado del corte de 0.55 de
# `placeGhostAt`, el peor caso de la pista — después de un relleno que ya ocupa el 55%, o
# dentro de uno que apenas lo pasa.
BORDE = cashflow_data(_stats(120978.0, 99022.0, 29706.6, 69315.4, 44.0, 69271.4, 100000.0),
                      "ZZZB")
CASOS = {"SCHB": cashflow_data(STATS_SCHB, "SCHB"), "MSTY": cashflow_data(STATS_MSTY, "MSTY"),
         "BORDE": BORDE}
PASOS = range(len(BORDE["STEP_LABELS"]))

_PAGINA = """<!doctype html><html><head><style>body { margin: 0; } %s</style></head>
<body><div class="block-container">%s</div></body></html>"""

_MEDIR = """() => {
  const d = document, de = d.documentElement, W = de.clientWidth;
  const oculto = el => { for (let a = el; a && a !== de; a = a.parentElement) {
    const cs = getComputedStyle(a);
    if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return true; }
    return false; };
  const nombre = el => el.id ? '#' + el.id
    : el.tagName.toLowerCase() + [...el.classList].map(c => '.' + c).join('');
  const caja = el => { for (let a = el.parentElement; a && a !== d.body; a = a.parentElement) {
    const ox = getComputedStyle(a).overflowX; if (ox !== 'visible') return [a, ox]; }
    return [null, null]; };
  const fallos = [];
  for (const el of d.body.querySelectorAll('*')) {
    if (el.closest('#tip, script, style') || oculto(el) || caja(el)[0]) continue;
    const r = el.getBoundingClientRect();
    if (r.width && (r.left < -0.5 || r.right > W + 0.5))
      fallos.push(nombre(el) + ' sale del iframe ' + Math.round(Math.max(-r.left, r.right - W)) + ' px');
  }
  const tw = d.createTreeWalker(d.body, NodeFilter.SHOW_TEXT);
  for (let n = tw.nextNode(); n; n = tw.nextNode()) {
    const p = n.parentElement, t = n.textContent.trim().slice(0, 30);
    if (!t || p.closest('#tip, script, style') || oculto(p)) continue;
    const [c, ox] = caja(p), rg = d.createRange();
    rg.selectNodeContents(n);
    for (const r of rg.getClientRects()) {
      if (r.width < 0.5) continue;
      if (!c && (r.left < -0.5 || r.right > W + 0.5)) fallos.push('«' + t + '» sale del iframe');
      if (c && (ox === 'hidden' || ox === 'clip')) {
        const b = c.getBoundingClientRect();
        if (r.left < b.left - 0.5 || r.right > b.right + 0.5)
          fallos.push('«' + t + '» cortado por ' + nombre(c));
      }
    }
  }
  for (const id of ['ioInGhost', 'ioOutGhost']) {
    const g = d.getElementById(id), fila = g.closest('.io-row'), r = g.getBoundingClientRect();
    const pista = fila.querySelector('.io-track').getBoundingClientRect();
    const borde = fila.querySelector('.io-fill').getBoundingClientRect().right;
    if (r.left < pista.left - 0.5 || r.right > pista.right + 0.5)
      fallos.push('«' + g.textContent + '» sale de su pista ' + Math.round(r.right - pista.right) + ' px');
    if (r.left < borde - 0.5 && r.right > borde + 0.5)
      fallos.push('«' + g.textContent + '» queda a caballo del borde del relleno');
  }
  for (const el of d.querySelectorAll('.v-big, .v-pct .num')) {
    const rg = d.createRange();
    rg.selectNodeContents(el);
    const lineas = new Set([...rg.getClientRects()].filter(r => r.width > 0.5).map(r => Math.round(r.top)));
    if (lineas.size > 1) fallos.push('«' + el.textContent + '» partida en ' + lineas.size + ' líneas');
  }
  return {fallos, ancho: W, dx: de.scrollWidth - de.clientWidth, dy: de.scrollHeight - de.clientHeight,
          contenido: de.scrollHeight};
}"""


def _srcdoc(datos, paso):
    """El HTML exacto que la app le da a `st.iframe`, `_SIN_SCROLL` incluido."""
    llamadas = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(componentes.st, "iframe", lambda doc, height: llamadas.append((doc, height)))
        componentes.render_cashflow(datos, paso, "Claro")
    (doc, alto), = llamadas
    return doc, alto


@pytest.fixture(scope="module")
def medidas():
    iframes = {}
    for caso, datos in CASOS.items():
        bloques = []
        for paso in PASOS:
            doc, alto = _srcdoc(datos, paso)
            bloques.append(f'<iframe name="p{paso}" srcdoc="{html.escape(doc)}" height="{alto}" '
                           'style="width:100%;border:0;display:block"></iframe>')
        iframes[caso] = "".join(bloques)
    try:
        with sync_api.sync_playwright() as pw:
            nav = pw.chromium.launch()
            out = {}
            for ancho in ANCHOS:
                pagina = nav.new_page(viewport={"width": ancho, "height": 900})
                for caso, bloques in iframes.items():
                    pagina.set_content(_PAGINA % (_ESTILOS, bloques))
                    pagina.wait_for_timeout(300)
                    for paso in PASOS:
                        marco = pagina.frame(name=f"p{paso}")
                        marco.evaluate("() => window.__vdAjustarAlto()")
                        out[caso, ancho, paso] = marco.evaluate(_MEDIR)
                pagina.close()
            nav.close()
            return out
    except Exception as error:  # sin Chromium instalado (CI)
        pytest.skip(f"Chromium no disponible: {error}")


def _de(medidas, ancho, clave):
    return [(caso, paso + 1, m[clave]) for (caso, a, paso), m in sorted(medidas.items())
            if a == ancho and m[clave]]


@pytest.mark.parametrize("ancho", ANCHOS)
def test_ningun_texto_ni_importe_se_sale(medidas, ancho):
    fallos = [(caso, paso, fallo) for caso, paso, lista in _de(medidas, ancho, "fallos")
              for fallo in lista]
    assert not fallos, fallos[:6]


@pytest.mark.parametrize("ancho", ANCHOS)
def test_el_documento_cabe_en_el_iframe(medidas, ancho):
    assert not _de(medidas, ancho, "dx"), "más ancho que el iframe"
    assert not _de(medidas, ancho, "dy"), "más alto que el iframe: el auto-alto se quedó corto"


def test_el_alto_de_respaldo_cubre_el_peor_caso(medidas):
    """Si el auto-alto no corre (iframe servido cross-origin), el iframe se queda con el alto
    que la app le pasa a `st.iframe`, y sin scroll lo que no cabe es inalcanzable. Ya se
    había quedado corto sin que nadie lo viera: 1536 px de documento contra 1520 a 320."""
    reservado = _srcdoc(CASOS["SCHB"], 0)[1]
    peor = max(medidas.items(), key=lambda kv: kv[1]["contenido"])
    assert peor[1]["contenido"] <= reservado, (peor[0], peor[1]["contenido"], reservado)


def test_el_iframe_toma_el_ancho_del_contenedor(medidas):
    """Si el montaje dejara el iframe en sus 300 px por defecto, los anchos de arriba
    medirían todos lo mismo y el test pasaría sin probar nada."""
    anchos = {a: medidas["SCHB", a, 0]["ancho"] for a in ANCHOS}
    assert anchos[320] < anchos[375] < anchos[430] < anchos[768] < anchos[1280], anchos
