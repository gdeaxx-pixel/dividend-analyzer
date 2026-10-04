"""1042-S de TD Ameritrade, varios 1042-S del mismo año y avisos del Bloque 3.

Medido el 2026-10-04 sobre documentos reales (solo conteos): en el 1042-S de TDA las
palabras salen pegadas con la tolerancia por defecto de pdfplumber, el identificador va en
la línea ANTERIOR a su etiqueta seguido de otro texto, el año no sale del identificador y los
códigos son 06 y 57 (57 = venta de una participación en PTP, sección 1446(f): no es dividendo).
Las cuentas que venían de TDA tienen en 2024 dos 1042-S, y solo sumados cuadran con el CSV.

Todo sintético: identificadores, importes y nombres inventados.
"""
import datetime
import io
import os
import sys

import pandas as pd
import pytest
from fpdf import FPDF
from streamlit.testing.v1 import AppTest

sys.path.insert(0, os.path.dirname(__file__))
import logic
from test_1042s import _build_synthetic_1042s_pdf
from tools import diagnostico_1042s
from ui import carga

BASE = os.path.dirname(os.path.abspath(__file__))

# (identificador, código, bruto, 7a, casilla 10, tasa 3b)
_TDA_2024 = [
    ("7319502846", "06", 2.00, 1.00, 1.00, "30.00"),
    ("7319502853", "57", 40.00, 4.00, 4.00, "10.00"),
]


def _linea(pdf, y, texto, gap=0.75):
    """Escribe palabra por palabra con un hueco de ~2 pt: menor que la tolerancia por defecto
    de pdfplumber (3) y mayor que 1.5, como en el documento de TDA."""
    x = 10
    for palabra in texto.split(" "):
        pdf.text(x, y, palabra)
        x += pdf.get_string_width(palabra) + gap


def _pdf_tda(forms=_TDA_2024, anio=2024, copias=2):
    pdf = FPDF()
    pdf.set_font("Helvetica", size=9)
    for ufi, code, gross, fed, cred, tasa in forms:
        for _ in range(copias):
            pdf.add_page()
            lineas = [
                f"Form 1042-S ({anio}) Foreign Person's U.S. Source Income Subject to Withholding",
                f"{' '.join(ufi)} AMENDED AMENDMENT NO.",
                "Copy B for Recipient UNIQUE FORM IDENTIFIER",
                "1 Income 2 Gross income 3 Chapter indicator",
                f"{code} {gross:.2f} 3b Tax rate {tasa} 4b Tax rate 00.00",
                f"7a Federal tax withheld {fed:.2f}",
                "10 Total withholding credit (combine boxes 7a, 8, and 9)",
                f"{cred:.2f}",
                "12a Withholding agent's name TD AMERITRADE CLEARING INC",
                "13a Recipient's name NOMBRE INVENTADO",
            ]
            for i, texto in enumerate(lineas):
                _linea(pdf, 20 + 6 * i, texto)
    return bytes(pdf.output())


_SCHWAB_2024 = [("2024000101", "06", 18.0, 5.0, 5.0)]


@pytest.fixture(scope="module")
def tda():
    return logic.parse_1042s_pdf(_pdf_tda())


# ── Lector ────────────────────────────────────────────────────────────────────

def test_el_fixture_reproduce_las_palabras_pegadas():
    """Sin esto, los tests del respaldo de tolerancia no probarían nada."""
    import pdfplumber
    with pdfplumber.open(io.BytesIO(_pdf_tda())) as pdf:
        defecto = "".join(p.extract_text() or "" for p in pdf.pages)
        ajustado = "".join(p.extract_text(x_tolerance=1.5) or "" for p in pdf.pages)
    assert "UNIQUE FORM IDENTIFIER" not in defecto
    assert ajustado.count("UNIQUE FORM IDENTIFIER") == 4


def test_lee_el_1042s_de_tda(tda):
    assert tda is not None
    assert sorted(f["income_code"] for f in tda["forms"]) == ["06", "57"]
    f06 = next(f for f in tda["forms"] if f["income_code"] == "06")
    assert (f06["gross_income"], f06["federal_tax_withheld"], f06["withholding_credit"]) == (2.0, 1.0, 1.0)
    assert f06["tax_rate"] == pytest.approx(30.0)
    assert not any(f["conflict"] for f in tda["forms"])
    assert tda["td_ameritrade"] is True
    assert tda["recipient_country_code"] is None


def test_el_anio_sale_de_la_cabecera_no_del_identificador(tda):
    assert tda["tax_year"] == 2024                      # el identificador empieza por 7319


def test_la_cabecera_manda_sobre_el_identificador():
    texto = ("Form 1042-S (2023)\n"
             "2 0 2 5 0 0 0 1 0 1 UNIQUE FORM IDENTIFIER\n"
             "06 10.00 3b Tax rate 30.00 4b Tax rate 00.00\n"
             "7a Federal tax withheld 3.00\n")
    assert logic._parse_1042s_text(texto)["tax_year"] == 2023


def test_schwab_sin_cabecera_sigue_tomando_el_anio_del_identificador():
    r = logic.parse_1042s_pdf(_build_synthetic_1042s_pdf())
    assert r["tax_year"] == 2025
    assert r["td_ameritrade"] is False
    assert sorted(f["income_code"] for f in r["forms"]) == ["01", "06", "37"]


def test_identificador_sin_anio_y_sin_cabecera_da_anio_nulo():
    texto = ("1042-S\n7 3 1 9 5 0 2 8 4 6 UNIQUE FORM IDENTIFIER\n"
             "06 10.00 3b Tax rate 30.00 4b Tax rate 00.00\n")
    assert logic._parse_1042s_text(texto)["tax_year"] is None


# ── Combinar varios documentos ────────────────────────────────────────────────

def _schwab_2024():
    return logic.parse_1042s_pdf(_build_synthetic_1042s_pdf(_SCHWAB_2024, copies=3))


def test_combinar_suma_los_dos_documentos_del_mismo_anio(tda):
    c = logic.combinar_1042s([_schwab_2024(), tda])
    assert c["tax_year"] == 2024
    assert c["documentos"] == 2
    assert c["td_ameritrade"] and c["schwab"]
    assert sum(f["gross_income"] for f in c["forms"] if f["income_code"] == "06") == 20.0
    assert c["recipient_country_code"] == "CO"           # el de TDA no lo trae
    assert c["anios_descartados"] == []


def test_combinar_no_duplica_el_mismo_pdf_subido_dos_veces():
    s = _schwab_2024()
    c = logic.combinar_1042s([s, s])
    assert len(c["forms"]) == len(s["forms"])
    assert sum(f["gross_income"] for f in c["forms"]) == sum(f["gross_income"] for f in s["forms"])


def test_combinar_nunca_suma_anios_distintos(tda):
    s2025 = logic.parse_1042s_pdf(_build_synthetic_1042s_pdf())
    c = logic.combinar_1042s([tda, s2025])
    assert c["tax_year"] == 2025
    assert c["anios_descartados"] == [2024]
    assert {f["unique_form_id"] for f in c["forms"]} == {f["unique_form_id"] for f in s2025["forms"]}
    assert c["td_ameritrade"] is False


def test_combinar_sin_nada_legible():
    assert logic.combinar_1042s([None, None]) is None
    assert logic.combinar_1042s([]) is None


def _df(filas):
    return pd.DataFrame(filas, columns=["Date", "Action", "Ticker", "Description", "Amount"])


_CSV_MIGRADO = _df([
    ("2024-03-15", "Cash Dividend", "AAA", "TDA TRAN - ORDINARY DIVIDEND (AAA)", 2.00),
    ("2024-05-15", "Cash Dividend", "AAA", "TDA TRAN - ORDINARY DIVIDEND (AAA)", 0.00),
    ("2024-06-03", "Journal", "", "TDA TRAN - TRANSFER", 0.00),
    ("2024-09-15", "Cash Dividend", "AAA", "AAA ETF", 18.00),
    ("2025-03-15", "Cash Dividend", "AAA", "AAA ETF", 30.00),
])


def test_el_codigo_57_no_entra_al_bruto(tda):
    v = logic.build_1042s_validation({}, logic.combinar_1042s([tda]), df_cuenta=_CSV_MIGRADO)
    assert v["bruto_1042s"] == 2.0


def test_los_dos_documentos_cuadran_y_uno_solo_no(tda):
    solo = logic.build_1042s_validation({}, logic.combinar_1042s([_schwab_2024()]),
                                        df_cuenta=_CSV_MIGRADO)
    ambos = logic.build_1042s_validation({}, logic.combinar_1042s([_schwab_2024(), tda]),
                                         df_cuenta=_CSV_MIGRADO)
    assert solo["status"] == "portfolio_higher"
    assert ambos["status"] == "match"


# ── Aviso del 1042-S que falta ────────────────────────────────────────────────

def test_tda_en_anio():
    a = logic.tda_en_anio(_CSV_MIGRADO, 2024)
    assert (a["tda"], a["schwab"], a["ultimo_mes_tda"]) == (2, 1, 6)
    assert logic.tda_en_anio(_CSV_MIGRADO, 2025)["tda"] == 0


def test_falta_el_de_tda(tda):
    f = logic.falta_1042s_tda(_CSV_MIGRADO, logic.combinar_1042s([_schwab_2024()]), "schwab")
    assert f == {"anio": 2024, "ultimo_mes_tda": 6, "falta": ["tda"]}


def test_falta_el_de_schwab(tda):
    f = logic.falta_1042s_tda(_CSV_MIGRADO, logic.combinar_1042s([tda]), "schwab")
    assert f["falta"] == ["schwab"]


def test_con_los_dos_no_falta_nada(tda):
    assert logic.falta_1042s_tda(
        _CSV_MIGRADO, logic.combinar_1042s([_schwab_2024(), tda]), "schwab") is None


def test_el_aviso_caduca_solo_por_el_anio_del_formulario():
    s2025 = logic.combinar_1042s([logic.parse_1042s_pdf(_build_synthetic_1042s_pdf())])
    assert logic.falta_1042s_tda(_CSV_MIGRADO, s2025, "schwab") is None


def test_el_aviso_solo_es_para_schwab():
    lectura = logic.combinar_1042s([_schwab_2024()])
    assert logic.falta_1042s_tda(_CSV_MIGRADO, lectura, "ibkr") is None
    assert logic.falta_1042s_tda(_CSV_MIGRADO, lectura, "generic") is None


def test_sin_historial_tda_no_hay_aviso():
    sin_tda = _df([("2024-09-15", "Cash Dividend", "AAA", "AAA ETF", 18.00)])
    assert logic.falta_1042s_tda(sin_tda, logic.combinar_1042s([_schwab_2024()]), "schwab") is None


def test_anio_solo_tda_no_pide_el_de_schwab():
    solo_tda = _df([("2023-05-15", "Cash Dividend", "AAA", "TDA TRAN - ORDINARY DIVIDEND", 5.0)])
    lectura = logic.combinar_1042s([logic.parse_1042s_pdf(_pdf_tda(anio=2023))])
    assert logic.falta_1042s_tda(solo_tda, lectura, "schwab") is None


def test_la_marca_tda_sale_del_contenido_no_del_nombre_del_archivo(tda):
    """El lector no recibe nombre de archivo: el emisor sale del texto del formulario."""
    assert tda["td_ameritrade"] is True
    assert logic.parse_1042s_pdf(_build_synthetic_1042s_pdf())["td_ameritrade"] is False


# ── Aviso de 1042-S viejo ─────────────────────────────────────────────────────

@pytest.mark.parametrize("hoy,esperado", [
    (datetime.date(2026, 2, 10), 2024),
    (datetime.date(2026, 3, 15), 2024),
    (datetime.date(2026, 3, 16), 2025),
    (datetime.date(2026, 12, 31), 2025),
])
def test_tax_year_esperado(hoy, esperado):
    assert logic.tax_year_esperado(hoy) == esperado


# ── UI ────────────────────────────────────────────────────────────────────────

_SCRIPT = """
import sys
sys.path.insert(0, {path!r})
import streamlit as st
from ui.carga import render_carga


class _Pdf:
    type = "application/pdf"

    def __init__(self, i):
        self._i = i

    def getvalue(self):
        return st.session_state["_test_pdfs"][self._i]


_real = st.file_uploader


def _uploader(*args, **kwargs):
    if kwargs.get("key") == "_vd_upload_1042s":
        return [_Pdf(i) for i in range(len(st.session_state.get("_test_pdfs") or []))]
    return _real(*args, **kwargs)


st.file_uploader = _uploader
try:
    render_carga()
finally:
    st.file_uploader = _real
""".format(path=BASE)


def _at(df=_CSV_MIGRADO, broker="schwab"):
    at = AppTest.from_string(_SCRIPT, default_timeout=40)
    at.session_state["_wizard_df_clean"] = df
    at.session_state["_wizard_csv_ticker_data"] = {}
    at.session_state["_wizard_broker"] = broker
    at.session_state["_wizard_csv_name"] = "sintetico.csv"
    at.session_state["_wizard_positions"] = {"AAA": {"shares": 1.0, "cost_basis": 10.0}}
    at.session_state["_wizard_pos_confirmed"] = True
    return at


def _textos(at):
    return " ".join(str(getattr(e, "value", "")) for e in
                    list(at.markdown) + list(at.warning) + list(at.info) + list(at.caption)
                    + list(at.error))


@pytest.fixture
def hoy_2026_oct(monkeypatch):
    monkeypatch.setattr(carga, "_hoy", lambda: datetime.date(2026, 10, 4))


def test_ui_sube_los_dos_y_no_avisa(hoy_2026_oct):
    at = _at()
    at.session_state["_test_pdfs"] = [_build_synthetic_1042s_pdf(_SCHWAB_2024), _pdf_tda()]
    at.run()
    assert not at.exception
    lectura = at.session_state["_wizard_1042s"]
    assert lectura["documentos"] == 2 and lectura["tax_year"] == 2024
    texto = _textos(at)
    assert "3 formularios · 2 documentos" in texto
    assert "Te falta" not in texto


def test_ui_solo_el_de_schwab_avisa_del_de_tda(hoy_2026_oct):
    at = _at()
    at.session_state["_test_pdfs"] = [_build_synthetic_1042s_pdf(_SCHWAB_2024)]
    at.run()
    assert not at.exception
    texto = _textos(at)
    assert "TD Ameritrade hasta junio de 2024" in texto
    assert "Te falta: «TDA - 1042S - 2024»" in texto


def test_ui_sin_historial_tda_no_avisa(hoy_2026_oct):
    at = _at(df=_df([("2024-09-15", "Cash Dividend", "AAA", "AAA ETF", 18.00)]))
    at.session_state["_test_pdfs"] = [_build_synthetic_1042s_pdf(_SCHWAB_2024)]
    at.run()
    assert "Te falta" not in _textos(at)


def test_ui_anios_distintos_usa_el_mas_reciente(hoy_2026_oct):
    at = _at()
    at.session_state["_test_pdfs"] = [_pdf_tda(), _build_synthetic_1042s_pdf()]
    at.run()
    assert not at.exception
    assert at.session_state["_wizard_1042s"]["tax_year"] == 2025
    assert "usamos el de 2025 y dejamos fuera 2024" in _textos(at)


def test_ui_un_archivo_ilegible_entre_varios(hoy_2026_oct):
    basura = FPDF()
    basura.add_page()
    basura.set_font("Helvetica", size=10)
    basura.cell(0, 10, "Documento cualquiera")
    at = _at()
    at.session_state["_test_pdfs"] = [bytes(basura.output()), _build_synthetic_1042s_pdf()]
    at.run()
    assert not at.exception
    assert "No pudimos leer el 1.º archivo; usamos los demás." in _textos(at)


def test_ui_aviso_de_1042s_viejo(monkeypatch):
    lectura = logic.combinar_1042s([logic.parse_1042s_pdf(_build_synthetic_1042s_pdf(_SCHWAB_2024))])
    for hoy, avisa in ((datetime.date(2026, 2, 10), False), (datetime.date(2026, 3, 20), True)):
        monkeypatch.setattr(carga, "_hoy", lambda hoy=hoy: hoy)
        at = _at(df=_df([("2024-09-15", "Cash Dividend", "AAA", "AAA ETF", 18.00)]))
        at.session_state["_wizard_1042s"] = lectura
        at.run()
        assert not at.exception
        assert ("Este 1042-S es de 2024. Ya debería estar disponible el de 2025" in _textos(at)) is avisa
        # Informativo: lo que va DESPUÉS del aviso (el botón «editar») se sigue dibujando.
        assert [x for x in at.button if x.proto.id.endswith("_vd_edit_1042s")]


def test_ui_editar_borra_tambien_los_ilegibles(hoy_2026_oct):
    assert "_wizard_1042s_ilegibles" in carga.CLAVES_CONTEXTO_CARTERA
    at = _at()
    at.session_state["_wizard_1042s"] = logic.combinar_1042s([_schwab_2024()])
    at.session_state["_wizard_1042s_ilegibles"] = [1]
    at.run()
    [b for b in at.button if b.proto.id.endswith("_vd_edit_1042s")][0].click().run()
    assert "_wizard_1042s_ilegibles" not in at.session_state.filtered_state


# ── Herramienta de soporte ────────────────────────────────────────────────────

def test_el_diagnostico_no_imprime_nada_del_documento():
    salida = "\n".join(diagnostico_1042s.diagnosticar(_pdf_tda()))
    assert "leído (respaldo 1.5); formularios 2; códigos 06, 57" in salida
    assert "emitido por TD Ameritrade: sí" in salida
    for secreto in ("NOMBRE", "INVENTADO", "7319502846", "7 3 1 9", "2.00", "40.00", "CLEARING"):
        assert secreto not in salida, secreto
