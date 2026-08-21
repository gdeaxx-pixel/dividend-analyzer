# Dividend Analyzer — instrucciones de agente

Adaptador delgado. Las reglas de auditoría no viven aquí: viven en el contrato del repo y en la
skill. Este archivo sólo dice dónde están y qué no romper.

## Antes de tocar cualquier cifra en dólares

Impuesto, retención NRA, ROC, capital aportado o neto → **leer primero
[`specs/roc-nra-invariants.md`](specs/roc-nra-invariants.md)**. Es el contrato fiscal vigente. Si
algo lo contradice, manda el contrato.

Las cuatro reglas duras, en una línea cada una:

1. El capital aportado es **invariante** — el ROC nunca lo mueve; sólo mueve el bucket impuesto y la
   base fiscal.
2. Toda cifra declara su **base** (bruto / neto / base-fiscal) y su **momento** (al cobro / tras
   reclasificación anual). Nunca sumar ni restar cifras que difieran en cualquiera de los dos.
3. **Objeto fiscal único**: `logic.build_tax_summary` y `logic.build_dividend_tax_totals`. Las vistas
   los **renderizan**, nunca recalculan. "Misma función" no basta; tiene que ser el mismo objeto.
4. **Dos carriles del ROC que no se cruzan**: destructividad = tendencia del NAV
   (`classify_roc_health`); ROC% = palanca fiscal (`estimate_roc_refund*`).

## La convención bruto/neto es por FILA, no por bróker

Schwab declara bruto con la retención en fila aparte; IB declara neto con la retención plegada. Pero
**la regla no es esa**: `_dividend_tax_netted` detecta la convención fila por fila. Asumir
`bruto = neto + retenido` porque "es IB" ya duplicó la retención en Schwab (MSTY $600.60 vs $462.00
reales). Cada cifra trae su procedencia: `gross_source` / `net_source` ∈ `{'leido', 'derivado'}`.

## Cómo correr

```bash
./.venv/bin/python -m streamlit run app.py     # nunca `python` a secas
```

Casos de ejemplo sin subir CSV: `localhost:8501/?demo=ib`, `?demo=schwab`, `?demo=schwab2`.

## Cómo validar

```bash
./.venv/bin/python -m pytest -q          # suite completa — ver línea base abajo
./.venv/bin/python validate_real_cases.py
```

**La suite completa, nunca un subconjunto.** Los 23 archivos cubren clases de regresión distintas.
Línea base: **589 passed, 2 skipped, 3 deselected, 1 xfailed** (medido 2026-08-21 tras el arreglo
del contrafáctico Sin DRIP). Este número envejece en cuanto alguien añade tests: si tu PR cambia
la cuenta, **actualízalo aquí en el mismo PR**. Ya estuvo desfasado en 74 tests sin que nadie lo
notara, y volvió a desfasarse en 2 entre `a2dd335` (538, lo que decía esta línea) y `95c0932`
(540, que es lo que `main` corría de verdad): el #57 añadió dos tests sin tocar este número.

El `xfailed` es **uno solo y deliberado**, con `strict=True`
(`test_contrafactico_sin_drip.py::test_con_drip_respeta_monotonicidad`): documenta que en la fila
Con DRIP el modo «roc» supera a «bruto» —retener y devolver enriquece— porque el método post-hoc
penaliza el *valor* y reembolsa sobre los *dividendos*. No es una tolerancia ampliada para pasar:
cuando se unifique la metodología con la de la 3ª gráfica, pytest lo reportará como XPASS fallido
y obligará a retirar el xfail. Si aparece un segundo xfail, sospecha.

Los tests de visión están deseleccionados por `pytest.ini`; correrlos aparte sólo si se tocó la
lectura por foto (`-m vision`, gasta cuota de Gemini).

`real_examples/` es un symlink a data privada (`~/.local/share/dividend-analyzer/real_examples`). Si
no está montado, los tests hacen **skip** — y un skip no es un pass: hay que decirlo.

## Datos: nada inventado, todo con procedencia

- **Nunca** una constante en código presentada como cifra "real / medida / observada". Ningún test la
  detecta (un test compara el código contra sí mismo); sólo la caza contrastarla contra la fuente
  viva. Ya pasó: `F`/`shapeOf` fabricaban series con senos y gaussianas, y `MATRIZ`/`ROC_19A`
  estaban congelados bajo el copy "Todas las cifras son observadas".
- Fuentes vivas: `knowledge/roc_19a.yaml`, `knowledge/price_cache/`, `knowledge/instruments.yaml`,
  `real_examples/<caso>/expected.json`.
- El motor (`backtest.py`) es **event-driven** sobre ex-date y pay-date reales. Corre sobre
  `price_cache.load_history` con `history=` inyectado — **no** llamar a yfinance desde la UI.
- Validar **siempre** contra las capturas del bróker en `real_examples/`, nunca contra una tabla en
  frío. Una tabla vieja ya provocó el diagnóstico de un bug inexistente.

## Tests: si no muerde, no vale

- Un guard sólo vale si reconcilia contra una **fuente independiente**. Patrón vigente:
  `ui/adapters.py::verificar_identidades` relee el CSV (`logic._csv_dividends_in_window`), no la
  fórmula que generó el dato. Antes era tautológico y no podía fallar nunca.
- Tras tocar cualquier aserción, la pregunta no es "¿pasa?" sino **"¿seguiría detectando el bug?"** —
  se responde reintroduciendo el bug y confirmando que la suite falla.
- **Nunca** ampliar una tolerancia para que algo pase. Una entrega declaró "PASSED" con 4.80% de
  desviación bajo una tolerancia inventada del 8%.

## Deploy

- Rama + PR. **Nunca commit directo a `main`** — `main` auto-despliega a Streamlit Cloud.
- Daniel mergea. Siempre. Nunca auto-merge. **Mergear no es desplegar.**
- **Módulo nuevo propio** → añadirlo a `stale_guard._ORDEN`, **antes** de quienes lo importan.
  Streamlit Cloud reescribe los archivos al desplegar sin reiniciar el proceso, y
  `asegurar_frescura()` recarga por fecha de modificación: lo que no esté en `_ORDEN` se recarga
  al final, que es seguro salvo si otros módulos importan nombres sueltos de él. Hay un test que
  avisa (`test_stale_guard.py`) — cazó `ui.estado` el 2026-08-17.
- **No hace falta registrar funciones nuevas en ninguna lista.** El guard por símbolos
  (`_LOGIC_SENTINELS`) se retiró: solo veía símbolos nuevos, había que alimentarlo a mano en cada
  PR y no detectaba el caso más común —un arreglo dentro de una función existente—. Hoy solo vive
  en `app_old.py`, que no se ejecuta; editarlo ahí no hace nada.
- `git pull --rebase` antes de push: el workflow de refresco del caché commitea solo.

## Skills

| Para | Skill |
|---|---|
| Auditar los cálculos a fondo | `/auditoria-financiera` |
| Validar antes de desplegar | `/validar-app` |
| Bug visual o de comportamiento | `/corregir-dividendos` |
| Enseñarle un instrumento nuevo | `/aprende-portafolio` |
| Desplegar | `/actualizar-app` |

Protocolo completo y bitácora histórica:
`../Obsidian/APPs/Dividend-Analyzer/protocolo-revision-calculadora.md`.
