# Matriz de paridad — `app.py` → `app_v2.py`

> **Gate de la Fase 5.** «Funcionalidad absoluta» no se declara leyendo código: se demuestra
> con esta tabla. Una fila sin ubicación o sin comprobación **es un fallo de fase**, no una
> nota pendiente.
>
> El inventario de filas está fijado: lo generó la auditoría desde `app.py`, no el ejecutor.
> **No se borran filas.** Si una función se decide no portar, se marca `NO PORTADA` con el
> motivo, y eso lo aprueba Daniel — no el ejecutor.

Columnas a llenar por el ejecutor:
- **Ubicación** — archivo y línea en `app_v2.py` / `ui/` donde vive ahora.
- **Comprobación** — cómo se verificó (fixture usado + qué se observó). No vale «revisado».

---

## Hoja de carga (wizard)

| # | Función en `app.py` | Ubicación en `app_v2.py` / `ui/` | Comprobación |
|---|---|---|---|
| 1 | Bloque 1 · Transacciones CSV/Excel (`app.py:1356`) | `ui/carga.py:143` `render_bloque_transacciones` | Fase 2, cerrada 2026-08-05: carga y valida con `fixtures/schwab_synth_1` e `ib_synth_1` (broker, columnas requeridas, error de formato). |
| 2 | Bloque 1 contraído + botón «editar» (`app.py:1424`) | `ui/carga.py:143` (rama `bloque_resumen` + botón `_vd_edit_csv`) | Fase 2: con `schwab_synth_1` cargado se contrae a resumen `"CSV cargado · N tickers"`; «editar» limpia el estado y vuelve al uploader. |
| 3 | Bloque 2 · Posiciones del portafolio (`app.py:1439`) | `ui/carga.py:200` `render_bloque_posiciones` | Fase 2: con `schwab_synth_1`, acciones/costo por ticker prellenados desde la vista previa del CSV (MSTY 40/$1000, TSLY 50/$600, SCHB 10/$200), editables y confirmables. |
| 4 | Bloque 2 · lectura de fotos con Gemini (`app.py:1455`) | `ui/carga.py:200` (bloque `_clave_gemini`/`extract_positions_from_images`) | Fase 2: sin `GEMINI_API_KEY` en el entorno el uploader de fotos no aparece y el resto del bloque sigue funcionando a mano — verificado en este worktree (sin clave). |
| 5 | Bloque 3 · Ingresos / income CSV (`app.py:1585`) | `ui/carga.py` `_render_income_uploader`/`_render_income_resumen`, llamadas desde `render_bloque_1042s` junto al 1042-S (conviven, ninguna sustituye a la otra) | Fase 5b, 2026-08-08: `AppTest` sobre `app_v2.py` — con broker `schwab` y ninguna fuente cargada aparecen el uploader del 1042-S y el expander «¿Tienes también el Investment Income?»; con `_wizard_1042s` y `_wizard_income_summary` ambos en sesión aparecen las dos tarjetas resumen («1042-S leído» y «Ingresos validados»); con broker `ibkr` aparecen los dos mensajes «No hace falta» (misma asimetría de `669731c`), sin uploader. `logic.parse_schwab_income_csv`/`summarize_income` verificados con `fixtures/schwab_synth_1/synthetic_investment_income.csv` (4 filas). |
| 6 | Paso a Resultados (`app.py:1724`) | `ui/carga.py:381` `render_carga` (botón «Ver resultados →», flag `_wizard_listo`) · `app_v2.py:64` | Pulido post Fase 3b (2026-08-07, commit `55e4431`): único punto de entrada a resultados; probado con `schwab_synth_1` hasta llegar a Cash flow. |
| 7 | Detección de bróker y errores de formato (`app.py:1380-1420`) | `ui/carga.py:101` `_leer_transacciones` + `ui/carga.py:143` (manejo de `faltan`/excepciones) | Fase 2: `schwab_synth_1` → detecta `schwab`; `ib_synth_1` → detecta `ibkr`; columnas faltantes muestran el error con la lista de columnas encontradas. |

## Secciones de resultados

| # | Función en `app.py` | Ubicación en `app_v2.py` / `ui/` | Comprobación |
|---|---|---|---|
| 8 | Tus dos portafolios (`app.py:3839`) | `ui/heredadas.py` `_tus_dos_portafolios` + `_dona_asignacion`, vista «Portafolios» | Fase 5b, 2026-08-08: `AppTest` con `fixtures/schwab_synth_1` — tarjeta «Portafolio de crecimiento» (SCHB) y «Portafolio de dividendos» (MSTY, TSLY) con invertido/vale hoy/dividendos/retorno total; dona de asignación por valor de mercado sin excepción. |
| 9 | Portafolio dividendos (`app.py:3927`) | `ui/heredadas.py` `_portafolio_dividendos`, vista «Portafolios» — reusa `ui.adapters.salud_nav_data` (mismo objeto que Salud NAV) en vez de recalcular `classify_roc_health` | Fase 5b: con `schwab_synth_1`, MSTY muestra «🔴 Tu capital se está encogiendo» (headline/plain idénticos a `classify_roc_health`), expander «Ver detalle técnico» y «¿Por qué pasa esto en MSTY?» con el texto de `logic.load_instruments()`; cierra con el callout «El trato completo, en una línea» literal. La «Hoja de Excel» que `app.py` embebía aquí como expander **no se duplica**: ya es su propia vista completa en la ruta (Dividendos/Largo Plazo › [ETF] › Hoja Excel, fila 10) — decisión de diseño, no omisión. |
| 10 | Hoja de Excel: te venden vs realidad (`app.py:3946`) | `ui/vistas.py:127` `render_hoja_excel` + `ui/componentes/hoja.html` (extraído por `tools/extract_hoja.py`) | Fase 4, cerrada 2026-08-07 (commit `6c0038f`): render medido en navegador con `schwab_synth_1`, `ALTO_HOJA=700`, sin `hidden` heredado ni `ReferenceError`. |
| 11 | Ingreso y comparación con el broker (`app.py:4205`) | `ui/heredadas.py` `render_ingresos` (gate `_wizard_income_df`, idéntico a `app.py`: la sección completa vive detrás de `if _income_df_s3 is not None and len(_income_df_s3) > 0:` — verificado por indentación del original) | Fase 5b, 2026-08-08: con `schwab_synth_1`, `logic.project_income`/`filter_income_assets` no producen filas (el fixture no trae filas `Estimated`, solo `Received` — limitación del fixture, no del port: `app.py` con los mismos datos también dejaría `_proj` vacío) → se muestra el mensaje «Tu Investment Income no tiene dividendos que coincidan con los tickers analizados», sin excepción. Camino con datos verificado por lectura de código (mismas fórmulas de `app.py:4295-4385`, gráfica acumulado Schwab-vs-cálculo y `_tabla_income_comparacion`); pendiente de un fixture con filas `Estimated` para ver la rama con contenido en vivo. |
| 12 | Detalle consolidado Schwab vs cálculo · ROC (`app.py:4207`) | `ui/heredadas.py` `_cuadricula_roc_consolidada`, vista «Ingresos» (Regla 3 no aplica: no es `tax_summary`, es la cuadrícula de dividendos/ROC por transacciones) | Fase 5b: misma gate que la fila 11 (mismo fixture, mismo resultado — mensaje de datos insuficientes); tabla condensada a `st.dataframe` nativo (Ticker/Div. pagados/ROC/Reinvertidos/En efectivo/Invertido/Costo bróker/Valor actual + fila TOTAL), sin las ~12 tooltips por columna de `app.py` (movidas a un párrafo explicativo debajo de la tabla) — decisión de re-vestido, no de datos. |
| 13 | Explicación visual del ROC — infografía (`app.py:4519`) | **Pendiente — Fase 5c** (`roc_infographic.py` ya existe, falta cablear como expander por ETF) | — |
| 14 | Las 3 cuadrículas · inversión, dividendos y ROC (`app.py:4618`) | `ui/heredadas.py` `_tabla_income_comparacion` + `_cuadricula_roc_consolidada`, vista «Ingresos» | Fase 5b: consolidadas en dos tablas nativas (recibido 12m/proyectado/histórico Schwab-vs-calc, y la cuadrícula ROC) en vez de las 3 cuadrículas HTML separadas (A: rendimiento, B: dividendos bruto→neto, C: ROC) de `app.py` — mismos números, misma fuente (`project_income`/`results`), presentación condensada. |
| 15 | Detalle por portafolio (`app.py:4902`) | `ui/heredadas.py` `_detalle_por_portafolio` + `_tarjeta_ticker` (solo `mode_a`: `app.py` tampoco despliega este detalle denso para tickers de crecimiento), vista «Portafolios» | Fase 5b: con `schwab_synth_1`, tarjetas MSTY y TSLY con KPIs (acciones, tu inversión, base broker/ROC, valor de mercado, próx. mes est.), callout ROC (`ib_cost_basis`/`roc_accumulated`), retorno total con desglose capital/income, interpretación educativa, y checkbox «Ver números crudos» con la tabla de 10 indicadores — sin excepción vía `AppTest`, cifras verificadas 1:1 contra el `results` crudo (MSTY ROI -73.68%, ROC $140.26/71.6% — coincide exacto). |
| 16 | Resumen consolidado — fondos de dividendos (`app.py:5171`) | `ui/heredadas.py` `_resumen_consolidado`, vista «Portafolios» (dentro de `_detalle_por_portafolio`) | Fase 5b: con `schwab_synth_1` (MSTY+TSLY, ≥2 fondos), tabla nativa con fila TOTAL — verificado vía `AppTest.dataframe`: Tu inversión $1,600.00, Dividendos $201.00, Valor mercado $322.72, ROI total -67.27% (coincide con la agregación `(mv+div-inv)/inv` de `app.py:5271-5272`). |
| 17 | Proyección a futuro y escenarios (`app.py:5244`) | **Pendiente — Fase 5c**, `ui/heredadas.py` vista «Proyección» | — |
| 18 | Proyección a futuro (escenario) — expander (`app.py:5299`) | **Pendiente — Fase 5c**, `ui/heredadas.py` vista «Proyección» | — |
| 19 | El yield anunciado vs lo que de verdad ganas (`app.py:5658`) | **Pendiente — Fase 5c**, `ui/heredadas.py` vista «Estrategias» | — |
| 20 | Comparativa de estrategias (`app.py:5666`) | **Pendiente — Fase 5c**, `ui/heredadas.py` vista «Estrategias» | — |
| 21 | Total Return Graph — YieldMax vs Crecimiento (`app.py:5922`) | `ui/vistas.py:279` (ruta Comparación · Simulación) → `ui/componentes/render_comparacion` + `comparacion.html` (extraído por `tools/extract_comparacion.py`) | Fase 4: render medido con `ALTO_COMPARACION=920`, `initComparacion()` corre tal cual, sin adapter (no depende del CSV del usuario). |

## Pie y utilidades

| # | Función en `app.py` | Ubicación en `app_v2.py` / `ui/` | Comprobación |
|---|---|---|---|
| 22 | Calidad de datos y validación cruzada de ingresos (`app.py:6074`, `_render_data_quality_panel` en `app.py:4031`) | `ui/pie.py:71` `_render_calidad_datos`, llamada desde `render_pie` (`ui/pie.py:220`) | Fase 5a: con `schwab_synth_1` (todo `mode_a`/`mode_b`, sin capturas) el expander muestra la tarjeta "Datos completos · 3 posiciones verificadas" (`assess_data_quality` sin niveles `unreliable`/`reconciled`/`partial`); verificado sin excepción vía `AppTest` en Cash flow, Salud NAV y Hoja Excel. La validación cruzada del 1042-S (tercera fuente) que este panel también dibujaba en `app.py` ya vive en el banner persistente `ui.vistas.render_1042s_card` desde la Fase 3 — no se duplica aquí. |
| 23 | Notas técnicas y eventos corporativos (`app.py:6094`, recolección en `app.py:5106-5158`) | `ui/pie.py:127` `_tech_events` + `_render_notas_tecnicas` | Fase 5a: con `schwab_synth_1` el expander «… · 14 evento(s)» aparece (splits/reconciliaciones/dividendos especiales de `stats`), verificado vía `AppTest` (`expander_labels` incluye la etiqueta con la cuenta). |
| 24 | Tickers excluidos del análisis (`app.py:6382`) | `ui/pie.py:167` `_render_excluidos` (lee `skipped` de `analyze_portfolio`, no confundir con `mode_skip` de `classify_tickers` ya mostrado en el Bloque 2 de la carga) | Fase 5a: con `schwab_synth_1` el expander «2 ticker(s) excluidos del análisis» aparece — verificado vía `AppTest`. |
| 25 | Calculadoras de referencia (`app.py:6396-6412`) | `ui/pie.py:184` `_render_calculadoras` (texto literal) | Fase 5a: expander presente en resultados con `schwab_synth_1`, texto idéntico al de `app.py` — verificado vía `AppTest` (`expander_labels`). |
| 26 | Disclaimer y pie legal (`app.py:6417-6432`) | `ui/pie.py:203` `_render_disclaimer` (texto literal, re-vestido con tokens — fuera los hex de `app.py`) | Fase 5a: con `schwab_synth_1`, `"vd-pie-legal"` y `"Versión Beta"` presentes en el HTML renderizado — verificado vía `AppTest`. |

## Modo alterno

| # | Función en `app.py` | Ubicación en `app_v2.py` / `ui/` | Comprobación |
|---|---|---|---|
| 27 | Simulación Teórica — modo completo (`app.py:6115`) | **NO PORTADA** — aprobado por Daniel, 2026-08-07 | Motivo: modo de entrada paralelo (`input_method`, `app.py:1170`) que la ruta del artifact no contempla; reintroducirlo obligaría a bifurcar la navegación. |
| 28 | Evolución de Patrimonio (`app.py:6156`) | **NO PORTADA** — aprobado por Daniel, 2026-08-07 | Mismo motivo que la fila 27: submódulo de Simulación Teórica, no portada como bloque. |
| 29 | Evolución por mezcla de asignación (`app.py:6262`) | **NO PORTADA** — aprobado por Daniel, 2026-08-07 | Mismo motivo que la fila 27: submódulo de Simulación Teórica, no portada como bloque. |

## Comportamiento transversal

| # | Función en `app.py` | Ubicación en `app_v2.py` / `ui/` | Comprobación |
|---|---|---|---|
| 30 | Modo demo `?demo=ib\|schwab\|schwab2` (`app.py:68-80`) | `app_v2.py:36-46` (copiado literal; usa `demo_mode.py`, ya presente en el worktree) | Fase 5a: probado con `?demo=schwab` en `localhost:8620` — sin `real_examples/` en este worktree queda inerte por diseño (no crashea, no navega), igual que en producción sin ese directorio. `st.session_state["_wizard_listo"]` se fija al cargar el bundle para saltar directo a resultados (puente necesario: el bundle trae las claves de sesión de `app.py`, que este port no lee). |
| 31 | `?clear` — limpia caché (`app.py:61`) | `app_v2.py:23-26` (copiado literal) | Fase 5a: probado con `?clear=1` en `localhost:8620` — limpia `query_params` y recarga a la hoja de carga sin error, verificado con captura de pantalla y consola sin errores. |
| 32 | Flag `SHOW_ROC_INFOGRAPHIC` (`app.py:59`) | **Pendiente — Fase 5c** (junto con la infografía ROC, fila 13) | — |
| 33 | Toasts de progreso entre bloques (`app.py:1345-1362`) | `ui/carga.py:83` `notificar_progreso`, llamada desde `app_v2.py:53` | Fase 5a: verificado con `AppTest` (instancia fresca por transición, ver nota de método abajo) — pill 1→2 dispara `st.toast("Configura tus costos")`; pill 2→3 (con `schwab_synth_1`) dispara `st.toast("Paso 3 de 3 · Resultados")`. |
| 34 | Animación de revelación progresiva (`app.py:1310-1324`) | `ui/carga.py` clase `.vd-reveal` + `@keyframes vd-rev` en `ESTILOS_CARGA`, aplicada en `bloque_header`/`bloque_resumen` | Fase 5a: mismo timing/easing que `.da-reveal` de `app.py` (`.42s cubic-bezier(.16,1,.3,1)`, `translateY(10px)→none`), con `prefers-reduced-motion` respetado; clase presente en el HTML de los tres bloques de la carga, verificado en `localhost:8620` claro y oscuro. |
| 35 | Interpretación educativa por ticker (`build_interpretation`) | `ui/heredadas.py` `_render_interpretation`, llamada por `_tarjeta_ticker` (vista «Portafolios», literal de `app.py:1869-1884`) | Fase 5b: con `schwab_synth_1`, callout «Qué significa para ti» presente en las tarjetas MSTY/TSLY con las líneas de `build_interpretation`, sin excepción vía `AppTest`. |
| 36 | Exposición al subyacente (`build_underlying_exposure`) | `ui/heredadas.py` `_render_interpretation`, llamada por `_tarjeta_ticker` (vista «Portafolios», literal de `app.py:1885-1895`) | Fase 5b: con `schwab_synth_1`, callout «Exposición al subyacente — riesgo asimétrico» presente para MSTY («MSTY sigue a MSTR (MicroStrategy)…») — texto literal de `build_underlying_exposure`, verificado en el markdown renderizado. |
| 37 | Generación de reporte PDF (`report.py`) | **Pendiente — Fase 5c** (`report.py`/`test_report.py` ya existen, falta cablear el botón en el pie) | — |

---

## Nota de método — Fase 5a (verificación)

El file uploader del navegador (Claude Browser / claude-in-chrome) reprodujo el mismo
bug de validación de esquema ya documentado en el traspaso — no pudo alcanzar ningún
archivo bajo este workspace ni bajo el scratchpad de la sesión, reproducido de forma
consistente en 4 intentos (por encima del tope de 2 reintentos). Se verificó en su lugar
con `streamlit.testing.v1.AppTest`, preseedeando `st.session_state` como si el wizard ya
hubiera pasado los Bloques 1-3 (mismo patrón que usa `demo_mode.py`), sobre
`fixtures/schwab_synth_1`. Esto cubre toda la plomería Python (categorías/vistas de
Detalle, dispatch, contenido del pie, toasts) pero no reemplaza la inspección visual del
DOM — por eso `?clear`, `?demo=schwab`, el tema claro/oscuro y la ausencia de errores de
consola SÍ se verificaron en el navegador real contra `localhost:8620`.

Un hallazgo de método, no del port: `AppTest.run()` dos veces sobre la misma instancia
revienta con `ValueError: content: "C" is not in list` — reproducido también contra el
commit base `6c0038f`, **antes** de cualquier cambio de esta fase. No es una regresión;
cada chequeo de este traspaso usa una instancia fresca de `AppTest` con un solo `.run()`.

---

## Cómo se audita

1. Ninguna celda vacía en las 37 filas.
2. Cada ubicación se abre y contiene efectivamente la función.
3. Cada comprobación nombra el fixture usado (`schwab_synth_1` o `ib_synth_1`) y qué se
   observó — no «revisado» ni «funciona».
4. Se recorre a mano una muestra aleatoria de 5 filas para confirmar que la tabla no miente.
