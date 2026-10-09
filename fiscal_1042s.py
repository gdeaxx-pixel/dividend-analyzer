"""Lectura del 1042-S y diagnósticos sobre sus formularios.

Extraído de `logic.py` el 2026-10-09 (auditoría app-audit 2026-10-07, F4, primer corte):
refactor puro, sin cambio de comportamiento. El código es byte-idéntico al que vivía en
`logic.py`; `logic` re-exporta estos nombres para los consumidores históricos (`logic.X`).
Dirección única: `logic` importa de aquí; este módulo no importa `logic`.
"""

import datetime
import io
import re

import pandas as pd


def income_code_str(value):
    """Normaliza el income code de un 1042-S a dos digitos ('37', '06', '01').

    El camino determinista siempre entrega la cadena de dos digitos, pero Gemini puede
    devolver el entero 37, '037' o '37 '. Comparar crudo contra '37' hace que un ROC
    valido cuente como cero. Toda la app compara codigos a traves de esta funcion.
    Devuelve '' si no hay ningun digito.
    """
    m = re.search(r"\d+", str(value if value is not None else ""))
    return f"{int(m.group()):02d}" if m else ""


# Codigos de pais del 1042-S (casilla 13b) -> nombre en NRA_COUNTRY_RATES.
#
# El IRS usa su propia tabla de country codes; coincide con ISO 3166-1 alfa-2 en casi todo,
# pero no siempre (Chile aparece como 'CI' en las tablas del IRS y como 'CL' en ISO). Se
# aceptan ambas variantes donde difieren. Un codigo que no este aqui NO se adivina: se
# devuelve tal cual y la UI pide que el cliente lo confirme a mano.
#
# Esta tabla nunca aplica sola: el flujo es detectar -> proponer -> el cliente confirma. Un
# mapeo equivocado lo caza el humano antes de que mueva una sola cifra.
_1042S_COUNTRY_CODES = {
    'MX': 'México',
    'CI': 'Chile', 'CL': 'Chile',
    'VE': 'Venezuela',
    'SP': 'España', 'ES': 'España',
    'CO': 'Colombia',
    'PE': 'Perú',
    'AR': 'Argentina',
    'BR': 'Brasil',
    'US': 'Estados Unidos',
}


def pais_desde_codigo_1042s(code):
    """Nombre de país de `NRA_COUNTRY_RATES` a partir del código de la casilla 13b.

    Devuelve None si el código no está mapeado — que es distinto de "no hay código". El
    llamador debe pedir confirmación en ambos casos; aquí solo se traduce.
    """
    if not code:
        return None
    return _1042S_COUNTRY_CODES.get(str(code).strip().upper())


def _tasa_3b(fragmento):
    """Tasa de la casilla 3b a partir del texto que la sigue.

    El PDF real la imprime con los puntos decorativos del formulario y el layout no es
    estable: `30..00`, `00..00` y `00.0.0` aparecen en el MISMO documento (copias B/C/D del
    1042-S de `real_examples`). Se toman los 4 primeros dígitos y se leen como NN.NN, que es
    como está impreso el campo.

    Medido: para esas tres variantes un parseo decimal ingenuo (`(\\d+)\\.+(\\d+)`) da el
    mismo resultado — no se gana robustez ahí. Lo que sí aporta este enfoque es un contrato
    más simple y tolerar la ausencia de puntos. El caller DEBE recortar el fragmento antes
    de "4b" (la línea trae las dos casillas): si la 3b viniera con menos de 4 dígitos, los
    de la 4b se colarían en el número.
    """
    digitos = re.sub(r"\D", "", fragmento or "")[:4]
    if len(digitos) < 4:
        return None
    try:
        return float(f"{digitos[:2]}.{digitos[2:]}")
    except ValueError:
        return None


# El identificador va delante de su etiqueta: en la misma línea (Schwab) o en la línea
# anterior seguido de otro texto (TD Ameritrade). Medido el 2026-10-04: 9/9 en un 1042-S
# de Schwab y 4/4 en uno de TDA; con el patrón de solo espacios, TDA daba 0.
_UFI_1042S = re.compile(r"((?:\d\s){9}\d)(?:\s*|[^\n]*\n[^\n]*?)UNIQUE FORM IDENTIFIER")
_ANIO_CABECERA_1042S = re.compile(r"1042-S\s*\(\s*(20\d\d)\s*\)")


def _anio_1042s(text, unique_form_id):
    """Año fiscal del 1042-S: el de la cabecera `Form 1042-S (AAAA)`, único en todo el
    documento. Respaldo: los 4 primeros dígitos del identificador, que en Schwab son el año
    y en TDA no (medido: el de TDA no empieza por ningún año 2015-2030)."""
    anios = set(_ANIO_CABECERA_1042S.findall(text))
    if len(anios) == 1:
        return int(anios.pop())
    pref = unique_form_id[:4]
    if pref.isdigit() and 2015 <= int(pref) <= datetime.date.today().year + 1:
        return int(pref)
    return None


def _parse_1042s_text(text):
    """Todo lo que `parse_1042s_pdf` hace después de extraer el texto. Ver su docstring."""
    if "1042-S" not in text:
        return None

    matches = list(_UFI_1042S.finditer(text))
    if not matches:
        return None

    forms = []
    seen = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        unique_form_id = re.sub(r"\s+", "", m.group(1))

        # "3b Tax rate" ya se usaba como ancla para localizar income_code + bruto; la
        # tasa que venía justo detrás se tiraba. Ahora se captura: es el dato oficial de
        # qué retención aplicaron.
        code_m = re.search(r"\n(\d{2})\s+([\d,]+\.\d{2})\s+3b Tax rate([^\n]*)", block)
        if not code_m:
            continue
        income_code = code_m.group(1)
        gross_income = float(code_m.group(2).replace(",", ""))
        # El resto de la línea trae también "4b Tax rate ..."; solo interesa lo anterior.
        tax_rate = _tasa_3b(code_m.group(3).split("4b")[0])

        fed_m = re.search(r"7a Federal tax withheld\s+([\d,]+\.\d{2})", block)
        federal_tax_withheld = float(fed_m.group(1).replace(",", "")) if fed_m else None

        cred_m = re.search(r"10 Total withholding credit[^\n]*\n\s*([\d,]+\.\d{2})", block)
        withholding_credit = float(cred_m.group(1).replace(",", "")) if cred_m else None

        row = {
            "unique_form_id": unique_form_id,
            "income_code": income_code,
            "gross_income": gross_income,
            "federal_tax_withheld": federal_tax_withheld,
            "withholding_credit": withholding_credit,
            "tax_rate": tax_rate,
            "conflict": False,
        }

        if unique_form_id in seen:
            prev = seen[unique_form_id]
            prev_key = (prev["income_code"], prev["gross_income"],
                        prev["federal_tax_withheld"], prev["withholding_credit"])
            row_key = (row["income_code"], row["gross_income"],
                       row["federal_tax_withheld"], row["withholding_credit"])
            if prev_key != row_key:
                prev["conflict"] = True
            continue

        seen[unique_form_id] = row
        forms.append(row)

    if not forms:
        return None

    tax_year = _anio_1042s(text, forms[0]["unique_form_id"])
    # Casilla 13b — el país del receptor va al FINAL de la línea siguiente a la etiqueta,
    # detrás del nombre (verificado contra el 1042-S real de `real_examples`). Es dato
    # del documento, no del formulario: un 1042-S trae varios códigos de ingreso pero un
    # solo receptor. En el de TDA no aparece con esta forma: queda None.
    pais_m = re.search(r"13b [^\n]*country code\s*\n[^\n]*?\b([A-Z]{2})\s*$",
                       text, re.MULTILINE)
    return {"tax_year": tax_year, "forms": forms, "source": "pdfplumber",
            "recipient_country_code": pais_m.group(1) if pais_m else None,
            # El agente de retención de los 1042-S de TD Ameritrade se nombra en el propio
            # formulario; el de Schwab, no (medido: 5 y 0 apariciones). No lee nada del titular.
            "td_ameritrade": "AMERITRADE" in text.upper()}


def parse_1042s_pdf(pdf_bytes):
    """Extraccion determinista (sin LLM) de un Formulario 1042-S en PDF via pdfplumber.

    Deduplica por UNIQUE FORM IDENTIFIER: cada formulario trae 3 copias (B/C/D) con
    los mismos numeros, y un parser ingenuo los sumaria 3 veces. Devuelve:
    {'tax_year': int|None, 'recipient_country_code': str|None, 'td_ameritrade': bool,
     'forms': [{'unique_form_id', 'income_code', 'gross_income', 'federal_tax_withheld',
     'withholding_credit', 'tax_rate', 'conflict'}, ...], 'source': 'pdfplumber'}
    o None si el documento no parece un 1042-S o ante cualquier excepcion.

    `tax_rate` (casilla 3b) es la tasa que el agente de retencion APLICO de verdad —
    distinta de la tasa a la que el cliente tiene DERECHO por su pais. La diferencia entre
    ambas es el diagnostico de W-8BEN: el tratado de Mexico (10%) solo corre si el
    formulario esta presentado y vigente; sin el retienen 30% igual. Verificado contra el
    1042-S real de `real_examples`: codigo 06 (dividendo) 30%, codigo 37 (ROC) 0%.

    Primero se extrae con la tolerancia por defecto de pdfplumber (la que siempre leyó los
    de Schwab). Si así no sale un 1042-S, se reintenta con `x_tolerance=1.5`: en los de TD
    Ameritrade las palabras están tan juntas que salen pegadas («UNIQUEFORMIDENTIFIER»).
    """
    try:
        import pdfplumber

        def _texto(**kw):
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                return "".join((page.extract_text(**kw) or "") + "\n" for page in pdf.pages)

        text = _texto()
        r = _parse_1042s_text(text)
        if r is None and "1042-S" in text:
            r = _parse_1042s_text(_texto(x_tolerance=1.5))
        return r
    except Exception:
        return None


def combinar_1042s(lecturas):
    """Une varios 1042-S ya leídos en uno solo, como si fueran un documento.

    Un mismo año puede traer DOS documentos: las cuentas que Schwab absorbió de TD
    Ameritrade recibieron en 2024 el «1042S - 2024» (lo cobrado ya en Schwab) y el
    «TDA - 1042S - 2024» (lo cobrado en TDA). Por separado, ninguno cuadra con el CSV del
    año completo; sumados, sí (medido el 2026-10-04 con un caso real: 18+2 = 20 frente a
    20.33 del CSV).

    - Formularios deduplicados por identificador ENTRE archivos: subir dos veces el mismo
      PDF no duplica nada.
    - Años distintos: se queda con el más reciente; los demás van a `anios_descartados`.
      Nunca se suman formularios de años distintos.
    - País: el primero no nulo. `documentos`: cuántos archivos se usaron.
    - `td_ameritrade` / `schwab`: si entre los usados hay uno de cada emisor.

    Devuelve None si ninguna lectura sirve."""
    validas = [l for l in (lecturas or []) if l and l.get("forms")]
    if not validas:
        return None
    anios = {l.get("tax_year") for l in validas}
    anio = max((a for a in anios if a is not None), default=None)
    usadas = [l for l in validas if l.get("tax_year") == anio]
    forms, ids = [], set()
    for l in usadas:
        for f in l["forms"]:
            fid = f.get("unique_form_id")
            if fid and fid in ids:
                continue
            if fid:
                ids.add(fid)
            forms.append(f)
    return {
        "tax_year": anio,
        "forms": forms,
        "source": "pdfplumber",
        "recipient_country_code": next(
            (l.get("recipient_country_code") for l in usadas if l.get("recipient_country_code")),
            None),
        "documentos": len(usadas),
        "td_ameritrade": any(l.get("td_ameritrade") for l in usadas),
        "schwab": any(not l.get("td_ameritrade") for l in usadas),
        "anios_descartados": sorted(a for a in anios if a != anio and a is not None),
    }


def tax_year_esperado(hoy):
    """Año del 1042-S más reciente que ya debería existir en `hoy`. El IRS fija el 15 de
    marzo para emitirlo (Schwab lo emitió el 7-12 de marzo en 2025 y 2026): desde el 16 de
    marzo es el del año anterior; antes, el de hace dos años."""
    return hoy.year - 1 if (hoy.month, hoy.day) >= (3, 16) else hoy.year - 2


def tda_en_anio(df, anio):
    """Actividad de dividendos de la época TD Ameritrade en `anio`, leída del CSV de Schwab.

    Las cuentas absorbidas exportan su historial previo como filas `TDA TRAN - ...` en la
    descripción (medido: 2022 a junio de 2024). Cuenta solo filas de dividendo (`Action`
    con «div»), porque un 1042-S solo existe si hubo renta. Devuelve
    {'tda': n, 'schwab': n, 'ultimo_mes_tda': int|None}."""
    vacio = {"tda": 0, "schwab": 0, "ultimo_mes_tda": None}
    if df is None or len(df) == 0 or anio is None or "Description" not in df.columns:
        return vacio
    fechas = pd.to_datetime(df["Date"], errors="coerce")
    del_anio = df[fechas.dt.year == int(anio)]
    if del_anio.empty:
        return vacio
    es_tda = del_anio["Description"].astype(str).str.strip().str.upper().str.startswith("TDA TRAN")
    es_div = del_anio["Action"].astype(str).str.lower().str.contains("div", na=False)
    meses_tda = fechas[del_anio.index][es_tda].dt.month
    return {"tda": int((es_tda & es_div).sum()),
            "schwab": int((~es_tda & es_div).sum()),
            "ultimo_mes_tda": int(meses_tda.max()) if not meses_tda.empty else None}


def falta_1042s_tda(df, lectura, broker):
    """¿Le falta al cliente uno de los dos 1042-S de un año partido entre TDA y Schwab?

    Solo para Schwab, y solo si el CSV tiene dividendos de la época TDA en el año del 1042-S
    subido: desde 2025 ya no hay, así que el aviso deja de salir solo. Devuelve None o
    {'anio', 'ultimo_mes_tda', 'falta': ['schwab'|'tda', ...]}."""
    if broker != "schwab" or not lectura or not lectura.get("tax_year"):
        return None
    anio = lectura["tax_year"]
    act = tda_en_anio(df, anio)
    if not act["tda"]:
        return None
    tiene_tda = bool(lectura.get("td_ameritrade"))
    tiene_schwab = bool(lectura.get("schwab", not tiene_tda))
    falta = []
    if act["schwab"] and not tiene_schwab:
        falta.append("schwab")
    if not tiene_tda:
        falta.append("tda")
    if not falta:
        return None
    return {"anio": anio, "ultimo_mes_tda": act["ultimo_mes_tda"], "falta": falta}


def _sum_roc_credit_from_forms(per_form):
    """Suma el credito de retencion (casilla 10) de los formularios 1042-S con
    income code 37 (Return of Capital). Los codigos 01 (interes) y 06 (dividendo)
    nunca se suman. Si falta withholding_credit usa federal_tax_withheld (7a) de respaldo.
    Deduplica antes de sumar: por 'unique_form_id' si las filas lo traen, o si no por la
    tupla (income_code, gross_income, federal_tax_withheld, withholding_credit) — evita
    sumar 2x/3x cuando el mismo formulario aparece repetido (copias B/C/D).
    Devuelve {'credit': float, 'roc_gross': float, 'per_form': [...]} (vacio si no hay code 37).
    """
    def _code37(v):
        m = re.search(r"\d+", str(v or ""))
        return m is not None and int(m.group()) == 37

    def _num(v):
        try:
            f = float(v)
            return f
        except (TypeError, ValueError):
            return 0.0

    matched = []
    credit_total = 0.0
    gross_total = 0.0
    seen_keys = set()
    for row in per_form or []:
        if not isinstance(row, dict) or not _code37(row.get("income_code")):
            continue
        credit = _num(row.get("withholding_credit"))
        if not credit:
            credit = _num(row.get("federal_tax_withheld"))
        gross = _num(row.get("gross_income"))

        form_id = row.get("unique_form_id")
        if form_id:
            dedupe_key = ("id", str(form_id))
        else:
            dedupe_key = ("tuple", row.get("income_code"), gross,
                          _num(row.get("federal_tax_withheld")), credit)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        credit_total += credit
        gross_total += gross
        matched.append(row)

    if not matched:
        return {"credit": 0.0, "roc_gross": 0.0, "per_form": []}
    return {"credit": credit_total, "roc_gross": gross_total, "per_form": matched}


def diagnose_broker_refund_from_forms(per_form):
    """¿El bróker ya devolvió la retención en exceso, o el dinero sigue en el IRS?

    En el 1042-S la **casilla 10** ("Total withholding credit") es por definición
    `7a + 8 + 9`, donde:
      - 7a = "Federal tax withheld" (lo que retuvo este agente),
      - 8  = "Tax withheld by other withholding agents",
      - 9  = "Overwithheld tax repaid to recipient" (lo que el bróker YA devolvió).

    Si asumimos casilla 8 = 0 (un solo agente), entonces:
        devuelto_por_broker = 7a − casilla_10

    Ejemplos reales (formularios de Daniel):
      - 2022, code 36: 7a=$1.00, casilla_10=$0.00 → devuelto $1.00 → 'devuelto'.
      - 2025, code 37: 7a=$83.00, casilla_10=$83.00 → devuelto $0.00 → 'pendiente'
        (el dinero está en el IRS: toca ITIN + 1040-NR).

    ⚠️ NO se usa el fallback de `_sum_roc_credit_from_forms` (si falta
    `withholding_credit`, usar 7a). Ese respaldo aquí daría `7a − 7a = 0` y afirmaría
    "no te devolvieron nada" cuando la verdad es que **no se sabe**. Un cero falso en
    una cifra de dólares de impuesto está prohibido (specs/roc-nra-invariants.md).
    Regla: sin `withholding_credit` numérico → veredicto 'indeterminado', nunca 0.0.
    Igual si `devuelto` sale negativo: la casilla 8 no es cero y la fórmula de dos
    términos no aplica → 'indeterminado', no un número truncado.

    No filtra por income code: sirve para cualquiera (el caso de 2022 es code 36).

    Devuelve {'devuelto': float|None, 'retenido': float, 'pendiente': float|None,
              'veredicto': str, 'per_form': [...]}.
    """
    def _num_or_none(v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    filas = []
    seen_keys = set()
    for row in per_form or []:
        if not isinstance(row, dict):
            continue
        fed_7a = _num_or_none(row.get("federal_tax_withheld"))
        wc = _num_or_none(row.get("withholding_credit"))

        form_id = row.get("unique_form_id")
        if form_id:
            dedupe_key = ("id", str(form_id))
        else:
            dedupe_key = ("tuple", row.get("income_code"), _num_or_none(row.get("gross_income")),
                          fed_7a, wc)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        if wc is None or fed_7a is None:
            veredicto = "indeterminado"
            devuelto = None
        else:
            devuelto = fed_7a - wc
            if devuelto < -0.01:
                veredicto = "indeterminado"
                devuelto = None
            elif abs(devuelto) <= 0.01 and fed_7a > 0.01:
                veredicto = "pendiente"
            elif abs(devuelto - fed_7a) <= 0.01:
                veredicto = "devuelto"
            elif 0.0 < devuelto < fed_7a:
                veredicto = "parcial"
            else:
                veredicto = "indeterminado"
                devuelto = None

        filas.append({
            "income_code": row.get("income_code"),
            "federal_tax_withheld": fed_7a,
            "withholding_credit": wc,
            "devuelto": devuelto,
            "veredicto": veredicto,
        })

    retenido = sum(f["federal_tax_withheld"] or 0.0 for f in filas)

    if not filas:
        return {"devuelto": None, "retenido": 0.0, "pendiente": None,
                "veredicto": "indeterminado", "per_form": [], "retenido_completo": True}

    retenido_completo = all(f["federal_tax_withheld"] is not None for f in filas)

    if any(f["veredicto"] == "indeterminado" for f in filas):
        return {"devuelto": None, "retenido": retenido, "pendiente": None,
                "veredicto": "indeterminado", "per_form": filas,
                "retenido_completo": retenido_completo}

    devuelto_total = sum(f["devuelto"] for f in filas)
    pendiente = retenido - devuelto_total

    if all(f["veredicto"] == "devuelto" for f in filas):
        veredicto = "devuelto"
    elif all(f["veredicto"] == "pendiente" for f in filas):
        veredicto = "pendiente"
    else:
        veredicto = "parcial"

    return {"devuelto": devuelto_total, "retenido": retenido, "pendiente": pendiente,
            "veredicto": veredicto, "per_form": filas, "retenido_completo": retenido_completo}


def extract_1042s(pdf_bytes):
    """Punto de entrada unico del Bloque 3: lee el 1042-S con el parser determinista
    (pdfplumber, sin red). Devuelve el dict de parse_1042s_pdf (source='pdfplumber') o None.

    Sin Gemini desde el 2026-09-18 (auditoria de privacidad, S1): el 1042-S trae nombre, TIN,
    direccion, fecha de nacimiento y numero de cuenta, y el fallback mandaba el PDF completo a
    Google. El parametro `api_key`, que ya se ignoraba, se retiro con `app_old.py` (2026-10).
    """
    return parse_1042s_pdf(pdf_bytes)
