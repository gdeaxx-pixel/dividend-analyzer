"""P4 y P5 de la propuesta de interfaz (2026-10-30): el paso 2 ofrece un camino a la vez y la
dona dice «sin revisar» antes de confirmar.

P4 — Al abrir el paso 2 se veían juntos el cargador del CSV de posiciones, el de capturas y la
tabla con − / +: tres caminos abiertos. Ahora el cliente elige «Captura · recomendada» (solo con
clave de Gemini), «Archivo de Schwab» (solo en Schwab) o «A mano». Solo se pide el cargador del
camino elegido, y con captura o archivo la tabla aparece al leer. Una vez dibujada no se
esconde al cambiar de camino: esconderla haría que Streamlit purgue lo tecleado.

P5 — Sin resultados la dona mostraba «0/5», que se leía como cinco fallos. El adapter dice
`evaluado: False` y el componente pinta «5 controles» y «Se revisan al confirmar tus
posiciones».

Todo sintético. Reusa el arnés de `test_carga_posiciones_csv.py`: los uploaders se sustituyen por
clave y `_test_llamados` guarda los que se pidieron en cada pase.
"""
import glob
import json
import os
import re

import pytest

import logic
from test_carga_posiciones_csv import (_POS_UI, _at, _campo, _confirmar, _proto, _subir_pos,
                                       _textos)
from ui import carga, componentes
from ui.adapters import cobertura_data

_FOTO = {"MSTY": {"shares": 1.0, "cost_basis": 2.0}, "SLV": {"shares": 3.0, "cost_basis": 4.0}}
_CARGADORES = ("_vd_fotos", "_vd_upload_pos_csv")


@pytest.fixture
def con_clave(monkeypatch):
    monkeypatch.setattr(carga, "_clave_gemini", lambda: "clave-de-prueba")
    monkeypatch.setattr(logic, "extract_positions_from_images",
                        lambda payload, analizables, clave: {t: dict(v) for t, v in
                                                             _FOTO.items()})


@pytest.fixture
def sin_clave(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(carga, "_clave_gemini", lambda: None)


def _hay_tabla(at):
    return any(w.proto.id.endswith("_vd_sh_MSTY") for w in at.number_input)


def _hay_confirmar(at):
    return any(b.proto.id.endswith("_vd_confirm_pos") for b in at.button)


def _selector(at):
    return [w for w in at.get("button_group") if w.proto.id.endswith("_vd_modo_pos")]


def _cargadores_pedidos(at):
    return {k for k in at.session_state["_test_llamados"] if k in _CARGADORES}


# ── P4 · qué caminos se ofrecen ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("clave, broker, esperado", [
    ("clave-de-prueba", "schwab", ["Captura · recomendada", "Archivo de Schwab", "A mano"]),
    ("clave-de-prueba", "ibkr", ["Captura · recomendada", "A mano"]),
    (None, "schwab", ["Archivo de Schwab", "A mano"]),
])
def test_los_caminos_dependen_del_broker_y_de_la_clave(monkeypatch, clave, broker, esperado):
    """La captura va primera («captura primero», 17-sep) y solo existe con clave: sin ella,
    un cargador que no lee nada solo confunde. El archivo de posiciones es de Schwab."""
    monkeypatch.setattr(carga, "_clave_gemini", lambda: clave)
    at = _at()
    at.session_state["_wizard_broker"] = broker
    at.run()
    assert not at.exception
    selector = _selector(at)
    assert selector, "no se dibujó la pregunta «¿Cómo nos das tus posiciones?»"
    assert selector[0].options == esperado
    assert selector[0].formatted_values == [esperado[0]], "el camino inicial no es el primero"


def test_con_un_solo_camino_no_hay_pregunta(sin_clave):
    """IBKR sin clave: solo queda «A mano», así que no se pregunta y la tabla sale ya."""
    at = _at()
    at.session_state["_wizard_broker"] = "ibkr"
    at.run()
    assert not at.exception
    assert not _selector(at)
    assert _hay_tabla(at)
    assert _cargadores_pedidos(at) == set()


@pytest.mark.parametrize("camino, cargador", [
    ("captura", "_vd_fotos"), ("archivo", "_vd_upload_pos_csv"), ("mano", None)])
def test_solo_se_pide_el_cargador_del_camino_elegido(con_clave, camino, cargador):
    at = _at()
    at.session_state["_vd_modo_pos"] = camino
    at.run()
    assert not at.exception
    assert _cargadores_pedidos(at) == ({cargador} if cargador else set())


# ── P4 · la tabla aparece al leer y luego no se esconde ──────────────────────────────────

def test_con_captura_la_tabla_aparece_al_leer(con_clave):
    at = _at()
    at.run()
    assert at.session_state["_vd_modo_pos"] == "captura"
    assert not _hay_tabla(at) and not _hay_confirmar(at)
    assert "Sube la captura y aquí aparece la tabla" in _textos(at)
    at.session_state["_test_foto_bytes"] = b"foto"
    at.run()
    assert not at.exception
    assert _campo(at, "_vd_sh_MSTY") == 1.0
    assert _hay_confirmar(at)
    texto = _textos(at)
    assert "Sube la captura" not in texto
    assert "No pudimos leer" not in texto
    assert "Los valores vienen de tu captura" in texto


def test_con_archivo_la_tabla_aparece_al_leer(sin_clave):
    at = _at()
    at.run()
    assert at.session_state["_vd_modo_pos"] == "archivo"
    assert not _hay_tabla(at) and not _hay_confirmar(at)
    assert "Sube el archivo y aquí aparece la tabla" in _textos(at)
    _subir_pos(at, _POS_UI)
    assert not at.exception
    assert _campo(at, "_vd_sh_MSTY") == 12.5
    assert _proto(at, "_vd_sh_MSTY").set_value
    assert _hay_confirmar(at)


def test_cambiar_de_camino_no_esconde_la_tabla_ni_borra_lo_tecleado(con_clave):
    """Con la tabla escondida, Streamlit purga los campos y lo tecleado se pierde."""
    at = _at()
    at.session_state["_vd_modo_pos"] = "mano"
    at.run()
    [w for w in at.number_input if w.proto.id.endswith("_vd_sh_MSTY")][0].set_value(7.0).run()
    for camino in ("captura", "archivo", "mano"):
        at.button_group(key="_vd_modo_pos").set_value(camino).run()
        assert not at.exception
        assert _campo(at, "_vd_sh_MSTY") == 7.0, camino


def test_cambiar_tras_confirmar_sale_con_lo_editado(sin_clave):
    """Confirmado, la tabla no se dibuja y Streamlit purga sus campos. Al volver con
    «Cambiar» deben salir como el cliente los dejó, no con la vista previa."""
    at = _at()
    at.session_state["_vd_modo_pos"] = "mano"
    at.run()
    [w for w in at.number_input if w.proto.id.endswith("_vd_sh_MSTY")][0].set_value(7.0).run()
    _confirmar(at)
    assert at.session_state["_wizard_positions"]["MSTY"]["shares"] == 7.0
    [b for b in at.button if b.proto.id.endswith("_vd_edit_pos")][0].click().run()
    assert not at.exception
    assert _campo(at, "_vd_sh_MSTY") == 7.0


def test_cambiar_sin_tabla_previa_sale_con_lo_confirmado(con_clave):
    """El demo llega con posiciones confirmadas sin haber dibujado la tabla. «Cambiar» debe
    enseñarlas aunque el camino inicial sea la captura y no haya nada leído."""
    at = _at()
    at.session_state["_wizard_positions"] = {"MSTY": {"shares": 9.0, "cost_basis": 90.0}}
    at.session_state["_wizard_pos_confirmed"] = True
    at.run()
    [b for b in at.button if b.proto.id.endswith("_vd_edit_pos")][0].click().run()
    assert not at.exception
    assert at.session_state["_vd_modo_pos"] == "captura"
    assert _campo(at, "_vd_sh_MSTY") == 9.0
    assert _campo(at, "_vd_cb_MSTY") == 90.0


def test_una_cartera_nueva_no_hereda_la_tabla(sin_clave):
    at = _at()
    at.session_state["_vd_modo_pos"] = "mano"
    at.run()
    [w for w in at.number_input if w.proto.id.endswith("_vd_sh_MSTY")][0].set_value(7.0).run()
    df, previa = at.session_state["_wizard_df_clean"], at.session_state["_wizard_csv_ticker_data"]
    [b for b in at.button if b.proto.id.endswith("_vd_edit_csv")][0].click().run()
    assert not at.exception
    at.session_state["_wizard_df_clean"] = df
    at.session_state["_wizard_csv_ticker_data"] = previa
    at.session_state["_wizard_broker"] = "schwab"
    at.session_state["_wizard_csv_name"] = "otra.csv"
    at.session_state["_vd_modo_pos"] = "mano"
    at.run()
    assert not at.exception
    assert _campo(at, "_vd_sh_MSTY") == 40.0
    assert "_vd_pos_tabla" in carga.CLAVES_CONTEXTO_CARTERA


# ── P4 · campos sin − / + y cifras a la derecha ──────────────────────────────────────────

_TESTIDS = ("stNumberInputStepDown", "stNumberInputStepUp")


def _reglas(css):
    """(selectores, cuerpo) de cada regla; las de dentro de un @media salen igual."""
    return [(sel.strip(), cuerpo) for sel, cuerpo in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


def test_los_campos_no_tienen_menos_mas_y_alinean_a_la_derecha():
    css = carga.ESTILOS_CARGA
    selectores = [f'[class*="st-key-{k}"] [data-testid="{t}"]'
                  for k in ("_vd_sh_", "_vd_cb_") for t in _TESTIDS]
    m = re.search(r"((?:\[class\*=\"st-key-_vd_(?:sh|cb)_\"\] \[data-testid=\"\w+\"\],?\s*)+)"
                  r"\{\s*display:\s*none;\s*\}", css)
    assert m, "no hay una regla `display: none` para los − / + de la tabla del paso 2"
    for sel in selectores:
        assert sel in m.group(1), f"la regla que esconde los − / + no cubre {sel}"
    alinea = re.search(r'\[class\*="st-key-_vd_sh_"\] input, \[class\*="st-key-_vd_cb_"\] input'
                       r"\s*\{[^}]*text-align:\s*right", css)
    assert alinea, "las cifras de la tabla del paso 2 no van a la derecha"


def test_la_tabla_del_paso_2_no_se_apila_en_el_telefono():
    """Streamlit apila las columnas bajo 640 px: «Acciones» y «Costo base» quedaban arriba,
    lejos de sus campos (medido a 375 y 320 px el 30-oct)."""
    reglas = _reglas(carga.ESTILOS_CARGA)
    filas = [c for s, c in reglas
             if ':has([class*="st-key-_vd_sh_"])' in s and "stColumn" not in s]
    assert any(re.search(r"flex-wrap:\s*nowrap", c) for c in filas), (
        "las filas de la tabla del paso 2 vuelven a apilarse en el teléfono")
    columnas = [c for s, c in reglas
                if ':has([class*="st-key-_vd_sh_"]) > [data-testid="stColumn"]' in s]
    assert any(re.search(r"min-width:\s*0", c) for c in columnas), (
        "las columnas conservan el ancho mínimo que las apila")


def test_el_campo_numerico_sigue_el_tema_y_no_tiene_esquinas():
    """En Streamlit 1.66 el campo numérico ya no lleva `data-baseweb`: salía claro y
    redondeado (8 px) también en el tema oscuro. Regla de marca: sin border-radius."""
    from ui.chrome import _ESTILOS
    reglas = _reglas(_ESTILOS)
    propias = [c for s, c in reglas
               if '[data-testid="stNumberInputContainer"]' in [x.strip() for x in s.split(",")]]
    assert any("background: var(--panel)" in c for c in propias), "el campo no usa la superficie del tema"
    assert any(re.search(r"border-radius:\s*0", c) for c in propias), "el campo vuelve a tener esquinas"
    assert any(":focus-within" in s and "var(--accent)" in c
               for s, c in reglas if "stNumberInputContainer" in s), (
        "el borde del tema pisa el foco de Streamlit y nada lo marca")


def test_los_testids_de_los_menos_mas_existen_en_este_streamlit():
    """Si una versión nueva de Streamlit los renombra, la regla deja de aplicar sin ruido y
    los − / + vuelven."""
    import streamlit
    js = glob.glob(os.path.join(os.path.dirname(streamlit.__file__), "static", "static", "js",
                                "NumberInput*.js"))
    assert js, "no encuentro el componente NumberInput en el Streamlit instalado"
    fuente = "".join(open(r, encoding="utf-8").read() for r in js)
    for t in _TESTIDS + ("stNumberInputContainer", "stNumberInputField"):
        assert t in fuente, f"{t} ya no existe en el NumberInput de este Streamlit"


# ── P5 · la dona antes de confirmar ──────────────────────────────────────────────────────

def test_sin_resultados_la_dona_sabe_que_no_se_reviso_nada():
    assert cobertura_data({})["evaluado"] is False
    assert cobertura_data(None)["evaluado"] is False


def test_el_componente_lee_evaluado():
    with open(os.path.join(os.path.dirname(carga.__file__), "componentes", "cobertura.html"),
              encoding="utf-8") as f:
        assert re.search(r"var sinRevisar\s*=\s*DATA\.evaluado\s*===\s*false;", f.read()), (
            "el componente no decide el estado «sin revisar» por `DATA.evaluado`")


_MEDIR_DONA = """() => ({
  cap: document.getElementById('dona-cap').textContent,
  centro: Array.from(document.querySelectorAll('#dona .dona-num, #dona .dona-sub'))
              .map(t => t.textContent),
  sinRevisar: document.getElementById('cov-root').classList.contains('sin-revisar'),
  aria: document.getElementById('dona').getAttribute('aria-label'),
})"""


@pytest.fixture(scope="module")
def donas():
    sync_api = pytest.importorskip("playwright.sync_api")
    sin = cobertura_data({})
    con = dict(sin, evaluado=True)
    out = {}
    try:
        with sync_api.sync_playwright() as pw:
            nav = pw.chromium.launch()
            pagina = nav.new_page()
            for nombre, datos in (("sin", sin), ("con", con)):
                html = componentes._con_tema(componentes._plantilla("cobertura.html"), "Claro")
                pagina.set_content(html.replace("{{DATA_JSON}}",
                                                json.dumps(datos, ensure_ascii=False)))
                out[nombre] = pagina.evaluate(_MEDIR_DONA)
            nav.close()
    except Exception as error:  # sin Chromium instalado (CI)
        pytest.skip(f"Chromium no disponible: {error}")
    return out


def test_la_dona_sin_revisar_no_dice_cero_de_cinco(donas):
    d = donas["sin"]
    assert d["sinRevisar"]
    assert d["cap"] == "Se revisan al confirmar tus posiciones"
    assert d["centro"] == ["5", "controles"]
    assert "0 de 5" not in d["aria"] and "sin revisar" in d["aria"]


def test_la_dona_revisada_sigue_contando(donas):
    """Mismos cinco pendientes, pero ya evaluados: ahí «0/5» sí es la respuesta."""
    d = donas["con"]
    assert not d["sinRevisar"]
    assert d["cap"] == "Verificación · toca un segmento"
    assert d["centro"] == ["0/5"]
    assert "0 de 5" in d["aria"]
