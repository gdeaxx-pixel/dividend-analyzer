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
| 5 | Bloque 3 · Ingresos / income CSV (`app.py:1585`) | `ui/carga.py` `_render_income_uploader`/`_render_income_resumen`, llamadas desde `render_bloque_1042s` junto al 1042-S (conviven, ninguna sustituye a la otra) | Fase 5b, 2026-08-08: `AppTest` sobre `app_v2.py` — con broker `schwab` y ninguna fuente cargada aparecen el uploader del 1042-S y el expander «¿Tienes también el Investment Income?»; con `_wizard_1042s` y `_wizard_income_summary` ambos en sesión aparecen las dos tarjetas resumen («1042-S leído» y «Ingresos validados»); con broker `ibkr` aparecen los dos mensajes «No hace falta» (misma asimetría de `669731c`), sin uploader. `logic.parse_schwab_income_csv`/`summarize_income` verificados con `fixtures/schwab_synth_1/synthetic_investment_income.csv` (4 filas). **Corregido en la revisión final 5c:** esa comprobación era hueca — el income CSV del fixture traía `Reported` donde el export real de Schwab dice `Received` (literal de `test_logic.py:799-803`), así que `summarize_income` devolvía `{}` y no verificaba nada. Corregida la palabra en el fixture, ahora sí cuadra con su propio `expected.json` (MSTY $156.00 · TSLY $45.00 · SCHB $1.50) y `verify_fixtures.py` lo asserta. |
| 6 | Paso a Resultados (`app.py:1724`) | `ui/carga.py:381` `render_carga` (botón «Ver resultados →», flag `_wizard_listo`) · `app_v2.py:64` | Pulido post Fase 3b (2026-08-07, commit `55e4431`): único punto de entrada a resultados; probado con `schwab_synth_1` hasta llegar a Cash flow. |
| 7 | Detección de bróker y errores de formato (`app.py:1380-1420`) | `ui/carga.py:101` `_leer_transacciones` + `ui/carga.py:143` (manejo de `faltan`/excepciones) | Fase 2: `schwab_synth_1` → detecta `schwab`; `ib_synth_1` → detecta `ibkr`; columnas faltantes muestran el error con la lista de columnas encontradas. |

## Secciones de resultados

| # | Función en `app.py` | Ubicación en `app_v2.py` / `ui/` | Comprobación |
|---|---|---|---|
| 8 | Tus dos portafolios (`app.py:3839`) | `ui/heredadas.py` `_tus_dos_portafolios` + `_dona_asignacion`, vista «Portafolios» | Fase 5b, 2026-08-08: `AppTest` con `fixtures/schwab_synth_1` — tarjeta «Portafolio de crecimiento» (SCHB) y «Portafolio de dividendos» (MSTY, TSLY) con invertido/vale hoy/dividendos/retorno total; dona de asignación por valor de mercado sin excepción. |
| 9 | Portafolio dividendos (`app.py:3927`) | `ui/heredadas.py` `_portafolio_dividendos`, vista «Portafolios» — reusa `ui.adapters.salud_nav_data` (mismo objeto que Salud NAV) en vez de recalcular `classify_roc_health` | Fase 5b: con `schwab_synth_1`, MSTY muestra «🔴 Tu capital se está encogiendo» (headline/plain idénticos a `classify_roc_health`), expander «Ver detalle técnico» y «¿Por qué pasa esto en MSTY?» con el texto de `logic.load_instruments()`; cierra con el callout «El trato completo, en una línea» literal. La «Hoja de Excel» que `app.py` embebía aquí como expander **no se duplica**: ya es su propia vista completa en la ruta (Dividendos/Largo Plazo › [ETF] › Hoja Excel, fila 10) — decisión de diseño, no omisión. |
| 10 | Hoja de Excel: te venden vs realidad (`app.py:3946`) | `ui/vistas.py:127` `render_hoja_excel` + `ui/componentes/hoja.html` (extraído por `tools/extract_hoja.py`) | Fase 4, cerrada 2026-08-07 (commit `6c0038f`): render medido en navegador con `schwab_synth_1`, `ALTO_HOJA=700`, sin `hidden` heredado ni `ReferenceError`. |
| 11 | Ingreso y comparación con el broker (`app.py:4205`) | `ui/heredadas.py` `render_ingresos` (gate `_wizard_income_df`, idéntico a `app.py`: la sección completa vive detrás de `if _income_df_s3 is not None and len(_income_df_s3) > 0:` — verificado por indentación del original) | Fase 5b, 2026-08-08: con `schwab_synth_1`, `logic.project_income`/`filter_income_assets` no producen filas (el fixture no trae filas `Estimated`, solo `Received` — limitación del fixture, no del port: `app.py` con los mismos datos también dejaría `_proj` vacío) → se muestra el mensaje «Tu Investment Income no tiene dividendos que coincidan con los tickers analizados», sin excepción. Camino con datos verificado por lectura de código (mismas fórmulas de `app.py:4295-4385`, gráfica acumulado Schwab-vs-cálculo y `_tabla_income_comparacion`); pendiente de un fixture con filas `Estimated` para ver la rama con contenido en vivo. **Actualizado en la revisión final de la Fase 5c (2026-08-08):** la rama con contenido ya no depende de leer código — se ejerce con el fixture nuevo `schwab_synth_2` (11 pagos `Received` + 12 `Estimated`): `AppTest` muestra la sección «Ingreso y comparación con el broker», el expander de detalle, la gráfica acumulada y la justificación de sobreestimación (66.7% > `INCOME_OVERSTATE_FLAG_PCT`), sin excepción y sin falsear nada. `schwab_synth_1` se conserva como el caso de la rama vacía. |
| 12 | Detalle consolidado Schwab vs cálculo · ROC (`app.py:4207`) | `ui/heredadas.py` `_cuadricula_roc_consolidada`, vista «Ingresos» (Regla 3 no aplica: no es `tax_summary`, es la cuadrícula de dividendos/ROC por transacciones) | Fase 5b: misma gate que la fila 11 (mismo fixture, mismo resultado — mensaje de datos insuficientes); tabla condensada a `st.dataframe` nativo (Ticker/Div. pagados/ROC/Reinvertidos/En efectivo/Invertido/Costo bróker/Valor actual + fila TOTAL), sin las ~12 tooltips por columna de `app.py` (movidas a un párrafo explicativo debajo de la tabla) — decisión de re-vestido, no de datos. **Revisión final 5c:** verificada con contenido real vía `schwab_synth_2` (`st.dataframe` con MSTY y fila TOTAL), no solo con el mensaje de datos insuficientes. |
| 13 | Explicación visual del ROC — infografía (`app.py:4519`) | `ui/heredadas.py` `_infografia_roc`, llamada al final de `render_ingresos` como **hermana** de `if proj:` y **fuera** de todo `st.expander` — calca la jerarquía de `app.py`, donde `if SHOW_ROC_INFOGRAPHIC:` (`app.py:4504`) está al mismo indent que `if _proj:` (`app.py:4064`), ambos colgando del gate del income CSV (`app.py:4059`) | Fase 5c, 2026-08-08: con `schwab_synth_1` + su income CSV, `AppTest` muestra los dos expanders «📊 Explicación visual del ROC — MSTY» y «— TSLY», sin excepción, y a la vez el mensaje de «no coincide» de la rama `proj` vacía — las dos ramas conviven, igual que en `app.py`. Condición de elegibilidad literal de `app.py:4501-4520` (ROC 25-100%, ROC ≤ distribuciones, valor de mercado < bolsillo): MSTY y TSLY **sí** la cumplen con este fixture. Verificado por A/B contra el commit `6faabbe`: con la infografía dentro del expander de «Ver detalle» y detrás del `return` temprano de `proj` vacío, la vista Ingresos completa reventaba con `StreamlitAPIException: Expanders may not be nested` en cuanto el income CSV cruzaba con algún ticker — ver «Nota de método — Fase 5c». |
| 14 | Las 3 cuadrículas · inversión, dividendos y ROC (`app.py:4618`) | `ui/heredadas.py` `_tabla_income_comparacion` + `_cuadricula_roc_consolidada`, vista «Ingresos» | Fase 5b: consolidadas en dos tablas nativas (recibido 12m/proyectado/histórico Schwab-vs-calc, y la cuadrícula ROC) en vez de las 3 cuadrículas HTML separadas (A: rendimiento, B: dividendos bruto→neto, C: ROC) de `app.py` — mismos números, misma fuente (`project_income`/`results`), presentación condensada. **Revisión final 5c:** las dos tablas se verifican ya con datos, vía `schwab_synth_2` (2 `st.dataframe` en la vista Ingresos). |
| 15 | Detalle por portafolio (`app.py:4902`) | `ui/heredadas.py` `_detalle_por_portafolio` + `_tarjeta_ticker` (solo `mode_a`: `app.py` tampoco despliega este detalle denso para tickers de crecimiento), vista «Portafolios» | Fase 5b: con `schwab_synth_1`, tarjetas MSTY y TSLY con KPIs (acciones, tu inversión, base broker/ROC, valor de mercado, próx. mes est.), callout ROC (`ib_cost_basis`/`roc_accumulated`), retorno total con desglose capital/income, interpretación educativa, y checkbox «Ver números crudos» con la tabla de 10 indicadores — sin excepción vía `AppTest`, cifras verificadas 1:1 contra el `results` crudo (MSTY ROI -73.68%, ROC $140.26/71.6% — coincide exacto). |
| 16 | Resumen consolidado — fondos de dividendos (`app.py:5171`) | `ui/heredadas.py` `_resumen_consolidado`, vista «Portafolios» (dentro de `_detalle_por_portafolio`) | Fase 5b: con `schwab_synth_1` (MSTY+TSLY, ≥2 fondos), tabla nativa con fila TOTAL — verificado vía `AppTest.dataframe`: Tu inversión $1,600.00, Dividendos $201.00, Valor mercado $322.72, ROI total -67.27% (coincide con la agregación `(mv+div-inv)/inv` de `app.py:5271-5272`). |
| 17 | Proyección a futuro y escenarios (`app.py:5244`) | `ui/heredadas.py` `_concentracion_por_factor` (correlación oculta por factor) + `render_proyeccion`, vista «Proyección» | Fase 5c, 2026-08-08: `AppTest` con `schwab_synth_1`/`ib_synth_1` — sin excepción, `logic.build_factor_concentration` leído tal cual (sin recalcular). |
| 18 | Proyección a futuro (escenario) — expander (`app.py:5299`) | `ui/heredadas.py` `_proyeccion_escenario` + `_carrera_yieldmax` + `_modulo_fiscal_nra` + `_monte_carlo`, vista «Proyección» | Fase 5c: sliders (horizonte/aporte/país/DRIP/crecimiento/apreciación/meta) y escenario de subyacente en widgets nativos; `logic.project_portfolio_forward`/`logic.monte_carlo_projection`/`logic.classify_roc_health`/`logic.nra_tax_breakdown` leídos sin recalcular su matemática — verificado con `AppTest` sobre ambos fixtures, sin excepción. Desviación: el detalle técnico de la carrera YieldMax usa `<details>` HTML (no `st.expander`) porque ya vive dentro del expander «Proyección a futuro (escenario)» y Streamlit no permite expanders anidados — mismo motivo documentado en `app.py:5518-5520`; detectado por el propio `AppTest` (`StreamlitAPIException`) y corregido antes de cerrar la fase. |
| 19 | El yield anunciado vs lo que de verdad ganas (`app.py:5658`) | `ui/heredadas.py` `_yield_audit`, vista «Estrategias» | Fase 5c: 3 pasos auditados (titular → mecanismo hoy → realizado) con `st.pills`, reusando `logic.build_hoja_excel`+`logic.build_tax_summaries` (Regla 3: un solo objeto fiscal, llamado una vez). Desviación de re-vestido: las barras de comparación del demo se condensan en `st.progress` por columna (sin equivalente nativo barato a la barra HTML animada) y la tabla «todos los fondos» usa `st.dataframe` en vez de `<table>` HTML — mismas cifras, mismo texto. Verificado con `AppTest` sobre `schwab_synth_1`/`ib_synth_1`, sin excepción. **Bug encontrado y corregido en Fase 6 (2026-08-08, navegador real):** el texto del paso 1 («por cada $100 en MSTY hoy, te pagaría ~$86 al año») se renderizaba como LaTeX roto — `app.py:3767` lo embebe dentro de un bloque HTML completo (`unsafe_allow_html=True`, empieza con `<div>`), por lo que Streamlit nunca aplica su parser de markdown/LaTeX a ese texto; el port usaba `st.markdown(txt)` en texto plano con `**negritas**`, y los dos `$` literales del mismo párrafo se interpretaban como delimitadores de fórmula. Fix: escapar los `$` literales (`\$`) en `ui/heredadas.py:1326-1327`. `AppTest` no lo detecta (no renderiza HTML/LaTeX) — solo apareció al mirarlo en el navegador, ver nota de método de la Fase 6. |
| 20 | Comparativa de estrategias (`app.py:5666`) | `ui/heredadas.py` `_comparativa_estrategias` + `_serie_temporal_estrategias`, vista «Estrategias» | Fase 5c: reconstrucción de flujos de compra desde `daily_trend`/`Invested Capital` (con los mismos 2 respaldos que `app.py`) + descarga de precios de SCHB/XLK/YMAX/SMH vía `yfinance`, cacheada en sesión por `_file_id` — verificado con `AppTest` sobre ambos fixtures, sin excepción (con o sin red, gracias al `try/except` por ETF ya presente en `app.py`). Dos desviaciones: (1) el gate original `_strat_results` (salida de `logic.simulate_triple_comparison`) solo se usaba como booleano en esta sección — nunca se leía su contenido — así que se sustituye por «hay resultados con inversión > 0», evitando recalcular una comparación que esta vista no consume; (2) la tabla de rendimiento se muestra con `st.dataframe` en vez del bloque HTML monoespaciado, y las etiquetas finales de la gráfica (de-colisión vertical) se omiten — el tooltip de Altair sigue mostrando cada valor al pasar el cursor. |
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
| 32 | Flag `SHOW_ROC_INFOGRAPHIC` (`app.py:59`) | `ui/heredadas.py` `SHOW_ROC_INFOGRAPHIC = True` (junto a `_infografia_roc`, fila 13) | Fase 5c: mismo valor y mismo rol que en `app.py` — módulo-nivel, gate del bloque completo antes de intentar `import roc_infographic`. |
| 33 | Toasts de progreso entre bloques (`app.py:1345-1362`) | `ui/carga.py:83` `notificar_progreso`, llamada desde `app_v2.py:53` | Fase 5a: verificado con `AppTest` (instancia fresca por transición, ver nota de método abajo) — pill 1→2 dispara `st.toast("Configura tus costos")`; pill 2→3 (con `schwab_synth_1`) dispara `st.toast("Paso 3 de 3 · Resultados")`. |
| 34 | Animación de revelación progresiva (`app.py:1310-1324`) | `ui/carga.py` clase `.vd-reveal` + `@keyframes vd-rev` en `ESTILOS_CARGA`, aplicada en `bloque_header`/`bloque_resumen` | Fase 5a: mismo timing/easing que `.da-reveal` de `app.py` (`.42s cubic-bezier(.16,1,.3,1)`, `translateY(10px)→none`), con `prefers-reduced-motion` respetado; clase presente en el HTML de los tres bloques de la carga, verificado en `localhost:8620` claro y oscuro. |
| 35 | Interpretación educativa por ticker (`build_interpretation`) | `ui/heredadas.py` `_render_interpretation`, llamada por `_tarjeta_ticker` (vista «Portafolios», literal de `app.py:1869-1884`) | Fase 5b: con `schwab_synth_1`, callout «Qué significa para ti» presente en las tarjetas MSTY/TSLY con las líneas de `build_interpretation`, sin excepción vía `AppTest`. |
| 36 | Exposición al subyacente (`build_underlying_exposure`) | `ui/heredadas.py` `_render_interpretation`, llamada por `_tarjeta_ticker` (vista «Portafolios», literal de `app.py:1885-1895`) | Fase 5b: con `schwab_synth_1`, callout «Exposición al subyacente — riesgo asimétrico» presente para MSTY («MSTY sigue a MSTR (MicroStrategy)…») — texto literal de `build_underlying_exposure`, verificado en el markdown renderizado. |
| 37 | Generación de reporte PDF (`report.py`) | `ui/pie.py` `_render_reporte_pdf`, llamada desde `render_pie` (última sección antes del disclaimer) | Fase 5c, 2026-08-08: `report.py`/`test_report.py` sin tocar (196 passed incluye `test_report.py`). `logic.generate_report_pdf` invocado con el `results` real de `AppTest` sobre `schwab_synth_1` → 6947 bytes sin excepción, y con `st.session_state["_wizard_broker"]` (fila cableada, no hardcodeada). El `try/except` de `app.py:5271-5282` se conserva literal. |

---

## Nota de método — Fase 5c (el punto ciego de «sin excepción»)

`AppTest` sin excepción sobre los fixtures **no prueba que una vista funcione**: prueba
que funciona *el camino que los fixtures ejercitan*. En esta fase eso dejó pasar un fallo
de severidad de producción hasta la revisión final.

`_infografia_roc` abre un `st.expander` por ETF elegible. Se colocó dentro del expander
«Ver detalle», y además detrás del `return` temprano que `render_ingresos` hacía cuando
`proj` venía vacío. Con `schwab_synth_1` el `proj` **siempre** sale vacío (su income CSV
no trae filas `Estimated`, limitación conocida del fixture desde la Fase 5b), así que el
código nunca se alcanzaba y `AppTest` reportaba verde en las 8 combinaciones
vista × fixture. Para un usuario real de Schwab —income CSV que sí cruza con sus tickers,
más un YieldMax en pérdida— la vista Ingresos entera reventaba con
`StreamlitAPIException: Expanders may not be nested inside other expanders`.

Se cazó comparando la jerarquía de indentación contra `app.py` en vez de leer solo el
contenido de cada bloque: allí `if SHOW_ROC_INFOGRAPHIC:` (4504) es **hermana** de
`if _proj:` (4064), no su hija — la infografía se muestra aunque el income no cruce con
nada, y no está anidada en ningún expander. Confirmado por A/B contra el commit `6faabbe`
falseando `logic.project_income` para devolver proyección no vacía (sin tocar `logic.py`
ni los fixtures en disco): versión previa → excepción; versión corregida → los dos
expanders de MSTY y TSLY, sin excepción.

**Reglas que deja la fase**, para las que vengan:

1. Cuando una vista tenga ramas que el fixture no alcanza, **forzar la rama** (falsear la
   función de `logic` en memoria, o doctorar el dict de `results`) antes de declararla
   verificada. «Sin excepción con los fixtures» se escribe declarando qué rama se ejerció.
2. Antes de reubicar un bloque de `app.py`, **comparar su indentación**, no solo su
   contenido: de qué gate cuelga y quién es su hermano es parte del comportamiento.
3. Todo `st.expander` que se mueva a una función auxiliar hereda el contexto de su
   llamador: verificar que ningún camino lo anide (`app.py` ya documenta este mismo
   choque en `app.py:5518-5520`, y esta fase lo repitió dos veces —
   `_carrera_yieldmax` y `_infografia_roc`).

### El fixture que faltaba — `schwab_synth_2`

Cerrar el hueco anterior exigía un fixture capaz de alcanzar la rama, y al construirlo
salieron dos defectos más de los fixtures existentes:

- **`schwab_synth_1` traía `Reported` donde Schwab escribe `Received`.** Tanto
  `summarize_income` como `project_income` filtran por `'received'`, así que ese income
  CSV no ejercía **nada** de la capa de ingresos: `summarize_income` devolvía `{}`. La
  palabra correcta está verificada contra datos reales en `test_logic.py:799-803`.
  Corregida en el fixture; ahora cuadra con su propio `expected.json`.
- **Los bloques `income_expected`/`tax_expected` de los `expected.json` eran
  decorativos**: `verify_fixtures.py` solo comprobaba bróker, columnas, clasificación y
  vista previa. Por eso nadie notó lo anterior — el `expected.json` afirmaba
  `received: {MSTY: 156.0, …}` mientras el código devolvía `{}`. Se añadieron las
  comprobaciones de `received`, `n_payments`, `est_per_payment` y `projection_expected`.

`schwab_synth_2` es el caso complementario: 11 pagos `Received` mensuales decrecientes
(90 → 40) en MSTY + 12 filas `Estimated` futuras ancladas en $75 (el broker repite el pago
alto). Con eso `project_income` devuelve `schwab_proj` $900 vs `our_proj` $540 —
sobreestimación del 66.7%, por encima de `INCOME_OVERSTATE_FLAG_PCT` — y MSTY queda
elegible para la infografía ROC. Los dos fixtures se reparten las ramas: `synth_1` la
proyección vacía, `synth_2` la proyección con contenido.

**El fixture caza el bug por sí solo**, que es la prueba de que valía la pena: corriendo
`AppTest` sobre la vista Ingresos con `schwab_synth_2` contra el commit `6faabbe` (sin
falsear nada) sale `StreamlitAPIException`; contra el código corregido, renderiza.

### La convención de `csv_glob` — y los tres fixtures que nunca se ejecutaron

Los `expected.json` sintéticos escribían `csv_glob`/`income_glob` relativos a `fixtures/`,
que es como los resolvía `verify_fixtures.py`. Pero los otros **tres** consumidores del
mismo manifest (`test_real_examples.py:90`, `validate_real_cases.py:104`,
`demo_mode.py:55`) los unen al **directorio del caso** — y los casos reales de
`real_examples/` usan esa convención. Resultado: esos tres construían una ruta duplicada
(`fixtures/schwab_synth_1/schwab_synth_1/…`) y **saltaban los tres casos en silencio**. La
explicación del traspaso («el Tier 2 necesita datos de mercado que los fixtures no
cubren») nunca fue la causa.

Unificado a la convención mayoritaria: globs relativos al caso, `verify_fixtures.py`
resolviendo contra `case_dir`, y `generate_fixtures.py` corregido para no reintroducirlo.
**El Tier 2 pasa de 12 skipped / 0 passed a 13 passed.** Lo que esos 13 tests destaparon
en cuanto empezaron a correr:

- **Cuatro tickers con `shares` desfasados en los tres fixtures**, todos por reverse splits
  REALES de diciembre 2025 (MSTY y TSLY 1:5 el 08 y 01/12; CONY 1:10 el 02/12). Los
  fixtures se escribieron con fechas de principios de 2025 y el mercado se movió debajo de
  ellos. Estaban ocultos tras `reliability: "high"` — un valor que el loader no reconoce
  (`test_real_examples.py:47` solo asserta `"ok"`), así que el bloque `tickers[].shares`
  era decorativo igual que `income_expected`. Corregidos a la verdad ajustada por split, con
  nota de que un split futuro los cambia y debe actualizarse el número, no borrarse.
- **`schwab_synth_2` se reconstruyó con compras posteriores al split** (2025-12-15) para que
  su `shares` no dependa de una acción corporativa que ese caso no pretende probar, y **con
  los precios de compra reales sin ajustar** de esa fecha (MSTY $31.76, SCHB $26.16). Con
  precios inventados muy por debajo del real, `assess_data_quality` marcaba
  `value_without_cost` **con razón**: valoraba las 100 acciones a $3,176 contra un costo
  registrado de $2,000 (ratio 1.59 > `VALUE_WITHOUT_COST_RATIO`). El flag era correcto y el
  fixture el equivocado.

### Auditoría de la sospecha de IB — veredicto

La sospecha era: «`assess_ticker_quality` marca NVDY y SMH como `unreliable` pese a tener
compra con costo; parece deficiencia con el formato de IB». **Esa hipótesis era falsa en su
atribución**, y la auditoría encontró debajo una fragilidad real y agnóstica del bróker.

**Causa raíz — `logic.py:1426`:**

```python
daily_history['Daily Invested'] = daily_activity['Cash_Flow_In'].reindex(market_data.index).fillna(0)
daily_history['Invested Capital'] = daily_history['Daily Invested'].cumsum()
```

`market_data.index` solo contiene días de cotización. Una transacción fechada en un día que
no cotiza **no se reindexa: se cae, se rellena con 0 y su importe se pierde para siempre**
del `cumsum` — no se difiere al siguiente día hábil. La curva de costo queda plana en cero
durante toda la serie.

**Reproducción (A/B cambiando solo la fecha, nada más):**

| Fecha de la compra | Curva `Invested Capital` | Veredicto |
|---|---|---|
| lunes hábil 2025-12-15 | $3,176 | `ok` |
| sábado 2025-12-13 | **$0** | `unreliable` |
| domingo 2025-12-14 | **$0** | `unreliable` |
| Navidad 2025-12-25 | **$0** | `unreliable` |

**No es de IB.** Reproducido idéntico con `schwab_synth_2` (tabla de arriba) y con
`ib_synth_1`: mover la compra de NVDY/SMH del 2025-01-20 al 2025-01-21 devuelve la curva de
$0 a $900/$1,000 y SMH pasa a `ok`. El bróker es irrelevante; lo que manda es si la fecha
existe en el histórico de precios.

**Defecto del fixture, corregido:** `ib_synth_1` fechaba sus compras el **2025-01-20, que
fue MLK Day — el mercado estaba cerrado**. Era una transacción imposible, y por eso el
`no_cost_recorded` original: mi sospecha nació de datos inventados mal. Movidas al
2025-01-21 (martes hábil). Con eso SMH queda `ok`; NVDY y CONY siguen `unreliable` pero por
otra razón —y correcta— `value_without_cost`: sus precios sintéticos están muy por debajo
del precio real de la fecha, justo lo que ese flag existe para detectar (mismo problema que
ya se corrigió en `schwab_synth_2` usando cierres reales).

**Exposición real.** No es alarmista pero tampoco teórica: una compra no se ejecuta en
feriado, pero sí pueden caer en día no bursátil las **transferencias de posiciones**
(ACATS/journaled, que `Cash_Flow_In` también recoge, ver `logic.py` § 5b), los extractos de
**IB con zona horaria no estadounidense** (un trade del viernes por la tarde ET puede
fecharse el sábado) y cualquier **hueco de datos de yfinance** o halt del ticker.

**Impacto acotado, pero visible al usuario.** `pocket_investment`, ROI y valor de mercado
salen **correctos** en todos los casos — se calculan por otra vía. Lo que se rompe es (1) la
línea de capital invertido del gráfico y (2) el veredicto de calidad, que le muestra al
usuario un «datos incompletos · no confiable» **falso** sobre una posición cuyas cifras
están bien.

**ARREGLADO — en `main`, no aquí.** Daniel lo autorizó el 2026-08-08 y se corrigió en el
repo canónico (commit `227eb3c`), **no en esta rama**: es un bug de producción que afecta a
`app.py` hoy, y llevarlo aquí rompería el invariante de la Fase 5 (`git diff --stat
logic.py` vacío). El port lo hereda cuando se rebase.

El arreglo introduce `logic._snap_to_trading_days`, aplicado en los **tres** puntos donde
estaba el patrón (la actividad completa —que arrastra también la cantidad de acciones—, el
`Cash_Flow_In` y los dividendos en efectivo): desplaza cada fecha al siguiente día de
cotización con `index.searchsorted` en vez de descartarla. Las fechas que ya cotizan no se
mueven, así que el resultado es idéntico para cualquier CSV cuyas transacciones caigan todas
en día hábil.

**Impacto medido sobre datos reales: ninguno.** Los 21 tickers de `real_examples/` dan
cifras idénticas antes y después — ninguno tiene transacciones en día no bursátil. Es red de
seguridad, sin riesgo de mover números de producción hoy.

Dos tests nuevos en `test_logic.py`, ambos verificados **saboteando el fix** (con el helper
devolviendo su entrada sin alinear, los dos fallan):
`test_snap_to_trading_days_defers_instead_of_dropping` y
`test_weekend_purchase_keeps_cost_curve`. Suite en `main`: 197 → 199 passed, cero
regresiones; `test_real_examples` 25 passed con datos reales de bróker.

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

## Nota de método — Fase 6 (verificación humana, 2026-08-08)

Rebase del port sobre `main` (hereda `227eb3c`, el arreglo del calendario bursátil) sin
conflictos de fondo (solo `.gitignore`, ambas líneas se conservaron). Gate tras el rebase:
236 passed/11 skipped · `fixtures/verify_fixtures.py` exit 0 · `git diff main -- logic.py`
vacío.

**El bug de `file_upload` del entorno (documentado en `feedback_preview-tool-sandbox-bug`)
se sorteó, no se evitó**: se construyó un `File`/`DataTransfer` en JS dentro del navegador
real (`atob` + `Uint8Array` + `input.files = dt.files` + evento `change`) y se disparó sobre
el `input[type=file]` real del uploader de Streamlit — mismo endpoint, mismo camino de
código que un drag-and-drop real, a diferencia de sembrar `session_state` a mano. Usado con
el fixture `schwab_synth_2` (no datos reales de Daniel, para no exponerlos): resultado
idéntico al de `verify_fixtures.py` (MSTY 100 acc. @ $3,176, SCHB 20 acc. @ $523.20,
ingresos $462.00/$4.90 validados contra el income CSV).

Recorridas las 17 vistas con datos reales renderizados (no solo `AppTest`): las 3 de
Dividendos/MSTY, las 3 de Largo Plazo/SCHB (confirma que el waterfall no solo funciona en
rojo/negativo — SCHB con retorno positivo renderiza con la paleta azul, sin regresión),
Comparación (Simulación y Real), las 5 de Método tradicional (spot-check), y las 4 de
Detalle — incluida Ingresos con el income CSV cruzando (ejercita la rama que 5c tuvo que
forzar) y la infografía ROC expandida sin el `StreamlitAPIException` de expanders anidados
que rompió 5c. Modo oscuro verificado en 2 vistas (Cash flow y Estrategias) sin regresión de
contraste. Consola: un único error `POCKET is not defined` (`about:srcdoc`), no reproducible
al repetir la acción — mount transitorio de un iframe anterior, no un fallo del port.

**Un bug real encontrado y corregido** — fila 19 de esta tabla: el texto «por cada $100 en
MSTY hoy…» se renderizaba como LaTeX roto (Streamlit interpreta `$…$` como fórmula cuando el
bloque no empieza con una etiqueta HTML). `AppTest` no lo detecta porque no renderiza
HTML/CSS/LaTeX — es exactamente la clase de defecto que este checklist existe para cazar.
Gate re-verificado después del fix: 236 passed/11 skipped, sin cambios de conteo.

**Dos bugs del mismo patrón, encontrados pero NO tocados** por estar **idénticos en
`app.py` línea por línea** (`logic.py:4215-4217`, el módulo fiscal NRA — «Diferencia a tu
favor: $X»; y `app.py:5153`/`ui/heredadas.py:434`, el aviso de discrepancia de precio CSV vs
yfinance): ambos son bugs preexistentes de producción, no regresiones del port. Tocarlos
aquí rompería el invariante `git diff main -- logic.py` vacío (el primero) o divergiría del
comportamiento de `app.py` sin autorización (el segundo). Quedan anotados para que Daniel
decida si los arregla en `main` cuando le convenga — no bloquean el port.

Con esto, el punto 4 de «Cómo se audita» queda cerrado: la muestra recorrida a mano cubrió
bastante más de 5 filas (8-21 completas con datos reales, no solo `AppTest`).

---

## Cómo se audita

1. Ninguna celda vacía en las 37 filas.
2. Cada ubicación se abre y contiene efectivamente la función.
3. Cada comprobación nombra el fixture usado (`schwab_synth_1` o `ib_synth_1`) y qué se
   observó — no «revisado» ni «funciona».
4. Se recorre a mano una muestra aleatoria de 5 filas para confirmar que la tabla no miente.
