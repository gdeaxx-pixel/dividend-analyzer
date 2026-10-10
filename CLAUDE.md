# Dividend Analyzer — instrucciones de agente

Adaptador delgado. Las reglas de auditoría no viven aquí: viven en el contrato del repo y en la
skill. Este archivo sólo dice dónde están y qué no romper.

## Antes de tocar cualquier cifra en dólares

Impuesto, retención NRA, ROC, capital aportado o neto → **leer primero
[`specs/roc-nra-invariants.md`](specs/roc-nra-invariants.md)**. Es el contrato fiscal vigente. Si
algo lo contradice, manda el contrato.

Las reglas duras, en una línea cada una:

1. El capital aportado es **invariante** — el ROC nunca lo mueve; sólo mueve el bucket impuesto y la
   base fiscal.
2. Toda cifra declara su **base** (bruto / neto / base-fiscal) y su **momento** (al cobro / tras
   reclasificación anual). Nunca sumar ni restar cifras que difieran en cualquiera de los dos.
   **2b — y su MUNDO**: una fila contrafáctica («si no se hubiera reinvertido») toma TODAS sus
   columnas de la misma corrida. Base y momento no cazan este error; el mundo sí.
3. **Objeto fiscal único** por eje: `logic.build_tax_summary` (impuesto/ROC del CSV),
   `logic.build_dividend_tax_totals` (base bruto/neto por bróker), `ui.adapters._politica_fiscal`
   (escenarios simulados: «La matriz» y las dos vistas de «Comparación»). Las vistas los
   **renderizan**, nunca recalculan. `logic.build_drip_comparison_series` /
   `build_roc_aware_withholding` / `build_total_return_series` **se borraron** el
   2026-08-21: metían el escudo ROC dentro de la tasa y se quedaron sin consumidor. Hay un
   guard que impide reintroducirlas.
   **3b**: todo eje con más de una vista necesita un test que compare **dos vistas del mismo
   número entre sí** — una suite de tests que verifican cada vista contra sí misma puede estar
   verde con dos pantallas contradiciéndose por $98K. Ya pasó.
4. **Dos carriles del ROC que no se cruzan**: destructividad = tendencia del NAV
   (`classify_roc_health`); ROC% = palanca fiscal (`estimate_roc_refund*`).
   **4b — y dos FUENTES del ROC%, con precedencia**: el **cierre fiscal** (`load_roc_ici`,
   casilla 3 del 1099) manda sobre la **estimación** del gestor (`load_roc_19a`, avisos 19(a)),
   año por año. El 19(a) solo gobierna el año todavía abierto. Probado contra un 1042-S real:
   MSTY 2025 fue 100% ROC ($275.97 bajo el código 37); el cierre decía 100.00%, la estimación
   78.40%.
5. **Un invariante estructural no es un hecho de mercado.** Antes de assertar una propiedad:
   ¿se cumple por construcción o porque los precios salieron así? «Más impuesto ⇒ peor resultado»
   es FALSO con reinversión (MSTY: el escenario con ROC supera al de cero impuestos).

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

**La suite completa, nunca un subconjunto.** Los archivos cubren clases de regresión distintas.

**Un verde en CI no sustituye una corrida local.** Los tests que dependen de `real_examples/` (datos privados) se saltan en CI.

**Los refrescos automáticos commitean a `main` sin PR ni review.** Si algo sale en cero o por centavos tras un `chore: refresh`, el primer sitio donde mirar es la última fila de los parquets o el `asof` / `weighted_pct` de `knowledge/roc_19a.yaml`. Qué hacer con cada aviso de Telegram: [`docs/runbook-refrescos.md`](docs/runbook-refrescos.md).

Línea base: **1481 passed, 2 skipped, 3 deselected, 0 xfailed** (medido 2026-10-09 sobre
`main` = `81b40c9` + los 4 tests de huecos R3/C6/PD de `analyze_portfolio`, con `real_examples/` y `CONY_test.csv`. Antes: 1477 sobre `81b40c9`. Antes: 1470 sobre `a71aa7f`,
tras los PRs de la auditoría app-audit 2026-10-07 (#202 +3, #203 +2, #204 +0, #205 +1, #206 +0).
Después: #208 y #210 +0 (F4, `metricas.py` y `movimientos.py`), #211 +3 (huecos de mutante CA-1,
TP-3 y HB-1b), #213 +0 (`filas_csv.py`), +3 (huecos FC-1, FC-2, RY-1 de `filas_csv.py`). Desde #203 la suite corre también en CI en cada PR: allí, sin datos privados, da
~1362 passed / 87 skipped — el gate es exit 0, no la cuenta.)

Línea base en la **nube** (sin `real_examples/` y sin red hacia Yahoo): **1342 passed, 91 skipped, 1 deselected** (última corrida del workflow «Suite en PR», 2026-10-09, rama `test/huecos-fc1-fc2-ry1`). En CI el gate es exit 0, no la cuenta. No sustituye a la línea local. Para volver a medir la local, con `real_examples/` montado y la carpeta para ti sola: `./.venv/bin/python tools/verificacion_m4_local.py`.

**Una sesión por working tree** (`git worktree`): una mutación temporal en una carpeta compartida se ve desde otra sesión como un rojo «flaky», y nunca se atribuye un rojo de `test_capital_aportado_resta_lo_que_devuelve_una_venta` a «un servidor compitiendo». Un worktree no hereda lo ignorado por git: sin `real_examples/` y `CONY_test.csv` la cuenta baja (≈1291/87).

Si tu PR cambia la cuenta de tests, actualiza la línea base en el mismo PR: ya se ha desfasado varias veces.

**`yf.download(lista)` no reduce peticiones** (una por ticker; solo latencia). Si hace falta latencia, se paraleliza `fetch_market_data` con hilos conservando su fallback de 3 capas.

Historial de líneas base e incidentes: `docs/historial-linea-base.md`.


**Cero `xfailed`, y así debe quedarse.** Hubo uno deliberado con `strict=True` mientras el modo
«roc» superaba a «bruto» en la fila Con DRIP; la unificación cerró el defecto y el xfail se
retiró, que es exactamente para lo que servía `strict`. Un `xfailed` nuevo en la cuenta significa
que alguien documentó un defecto en vez de arreglarlo: revísalo, no lo normalices.

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
- Un corte **estructural** (borrar una vista, una función, una rama) necesita un guard que
  **PARSEE**, no que compare texto. Un test de texto no puede ver un `SyntaxError`, y un
  `SyntaxError` mata el script **entero**: pantalla en blanco, consola limpia, cero tests rojos.
  Ya pasó (#83 → #84: el corte se comió el `})();` de `initMetodo`). Tras quitar un trozo de
  código la pregunta no es «¿sigue diciendo lo que quiero?» sino **«¿sigue parseando?»**.
  Guard vigente: `test_contrato_componentes.py`, `node --check` sobre los 14 scripts de los 7
  componentes (con balance de delimitadores como piso, para cuando no hay node).
- Para decidir si un guard **basta**, escribir 2-3 **mutantes** con la forma del bug real y medir
  cuántos caza. Convierte «¿será suficiente?» en un número. Medido así: ante un corte balanceado
  pero roto —cortar la rama `if` dejando un `else {` huérfano, que es la forma exacta del #84—
  el balance de delimitadores pasa **verde** y sólo `node --check` lo caza.

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
  en el tag `archivo/app_old-2026-10` (`app_old.py` se borró en oct-2026, #204).
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
