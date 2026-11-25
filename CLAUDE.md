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

Línea base: **2392 passed, 2 skipped, 3 deselected, 0 xfailed** (medido 2026-11-25 en Python 3.14 sobre la rama `fix/ibkr-pagos-en-otra-moneda`, que sale de `main` = `5270a6e`: +20 de `test_ibkr_otra_moneda.py` —una fila del Activity Statement de IBKR en una moneda distinta del dólar queda fuera, se cuenta y se avisa en el paso 1—; avisos 2179). Antes: **2372 passed, 2 skipped, 3 deselected, 0 xfailed** (medido 2026-11-25 en Python 3.14 sobre la rama `fix/confiabilidad-sin-contrastar-y-tasa-supuesta`, que sale de `main` = `63fa3fa`: +18 de `test_confiabilidad_sin_contrastar.py` —el nivel «Sin contrastar» cuando ninguna fuente confirma y el rótulo de tasa máxima supuesta sin país declarado—; avisos 2179). Antes: **2354 passed, 2 skipped, 3 deselected, 0 xfailed** (medido 2026-11-24 en Python 3.14 sobre la rama `fix/ganancias-mismo-dia-y-refrescos`, que sale de `main` = `d1e2b0b`: +40 de `test_ganancias_mismo_dia_y_tramo.py` —compras antes que ventas con la misma marca de fecha y la marca de tramo aproximado— y +19 de `test_refrescos_no_recortan.py` —un refresco recortado no reemplaza lo guardado—; con la referencia local de `tools/referencia_analyze.py` vuelta a congelar, porque `tramo_aproximado` es un campo nuevo de la salida). Antes: **2295 passed, 2 skipped, 3 deselected, 0 xfailed** (medido 2026-11-24 en Python 3.14 sobre la rama `fix/pantallas-textos-y-rotulos`, que sale de `main` = `6b4e532`: +12 de `test_1042s_no_legible.py` —casilla ilegible y formularios sin leer del 1042-S—, +17 de `test_vista_impuestos_render.py` —años del archivo, 1042-S devuelto a medias y el aviso de retención de menos con su margen—, +1 de `test_preguntas_con_su_cifra.py` y +1 neto de `test_metodo_serie.py` —la tasa del Método sale de la simulación—). Antes: **2264 passed, 2 skipped, 3 deselected, 0 xfailed** (medido 2026-11-24 en Python 3.14 sobre la rama `fix/escapar-texto-del-csv`, que sale de `main` = `8addb69`: +10 de `test_texto_del_csv_no_es_html.py` —el símbolo y el concepto del archivo se pintan como texto y el JSON incrustado no puede cerrar el `<script>`—, +8 de `test_fondo_sin_precios.py` —un fondo sin precios no se ofrece ni se dibuja con ceros—, +3 de `test_backtest.py` —un día sin cierre usa el último válido—, +1 de `test_logic.py` y +1 de `test_metodo_real.py` —la rentabilidad anual no cuenta la reinversión como aporte ni el valor de hoy dos veces—; avisos 2179). Antes: **2241 passed** (medido 2026-11-21 sobre la rama `fix/chpy-en-el-motor`, que sale de `main` = `622f66e`: +2 de `test_logic.py` —todo fondo que Comparación ofrece como YieldMax está en la lista blanca del motor, y CHPY entra como fondo de cartera—; avisos 2179). Antes: **2239 passed** (sobre la rama `fix/mercado-caches`, que sale de `main` = `9bff022`: +43 de `test_cache_fallos.py` —un resultado con algún fondo sin precios dura un minuto en caché y no la hora, el respaldo por scraping vacío no se guarda, los cuatro YAML de ROC se releen si cambian en disco y la pantalla reintenta a los 2, 8 y 30 minutos— y +20 de `test_market_context.py` —ventanas de calendario, niveles sin ajustar, nota que no se pisa—; avisos 2179: los 30 de más son de `test_carga_1042s.py`, que recalcula una vez porque `test_cache_fallos.py` vacía el caché compartido justo antes, medido quitando y poniendo ese archivo). Antes: **2176 passed** (sobre la rama `fix/fiscal-roc`, que sale de `main` = `80d4783`: +16 de `test_fiscal_bordes.py` —la retención de un solo año se mide contra el bruto de ese año, la retención ya devuelta no se borra del resumen, la retención por año va con signo y suma el total, el ROC publicado no pasa del 100 % y una reversa no cuenta como último pago ni para el ritmo—; avisos 2149). Antes: **2160 passed** sobre la rama `fix/rentabilidad-anual`, que sale de `main` = `522aaa3` (+6 de `test_metodo_real.py` —`xirr` ya no revienta con una fecha con zona horaria, mide una pérdida de más del 99,99 % anual en vez de dejarla sin dato, conserva a propósito el tope de arriba y no elige entre dos soluciones— y +4 de `test_logic.py` —`irr_anual` sale de `xirr` sobre las fechas reales y ya no de agrupar los flujos por mes calendario—; avisos 2149). Antes: **2150 passed** sobre la rama `fix/recorrido-menores`, que sale de `main` = `b63f231` (+11 de `test_serie_diaria_coherencia.py` —la transferencia de acciones anterior a un split entra a la comparación con el índice por su valor de ese día, la reinversión en una sola fila cuenta su importe con cualquier signo y la venta mayor que lo comprado se lleva lo reinvertido—. Antes: **2139 passed** sobre `fix/recorrido-operaciones` (`main` = `c3f736f`): +9 de `test_serie_diaria_coherencia.py` y +2 de `test_ganancias_capital.py` —la fracción de acción que el bróker paga en efectivo por un split sin fila en el CSV sale de las acciones, de la gráfica diaria y de las ganancias de capital—. Antes: **2128 passed** sobre `fix/serie-split-inverso` (`main` = `1266162`): +9 de `test_serie_diaria_coherencia.py` —la serie diaria reinicia las acciones en la fila de split con cantidad, como la cifra principal, y suma el día que se paga la caja que no es distribución—. Antes: **2119 passed** el mismo día sobre la rama `fix/serie-diaria-coherente`, que sale de `main` = `012e87e`: +19 de `test_serie_diaria_coherencia.py` —la serie diaria cuenta el dividendo neto de retención y con signo como la cifra principal, un día sin precio se valora al último cierre válido y la fila fuente de una reinversión no suma acciones—; la referencia local de `analyze_portfolio` se regrabó porque la serie cambia a propósito. Avisos: 2149. Antes: **2100 passed** (medido 2026-11-21 en Python 3.14 sobre la rama `fix/puerta-acceso-caducidades`, que sale de `main` = `134cfe2`: +35 de `test_acceso.py` —el permiso temporal caduca por su fecha, la lista deja de valer a los 7 días, el modo ausente o mal escrito aplica la lista, los avisos dicen si la puerta quedó cerrada o abierta y las pruebas no salen a la red—. Avisos: 2149. Antes: **2065 passed** (medido 2026-11-20 en Python 3.14 sobre la rama `fix/lectura-numeros-y-fechas`, que sale de `main` = `693e5fd`: +66 de `test_lectura_numeros_fechas.py` y +4 de `test_carga_asistente.py` —un solo lector de números para los archivos del bróker, la coma decimal la decide el archivo entero, los paréntesis son negativos, cada fecha se lee por sí misma y las filas que no se pueden leer se cuentan y se avisan en pantalla—. Avisos: 2149. Antes: **1995 passed** (medido 2026-11-20 en Python 3.14 sobre la rama `fix/pantallas-navegacion-y-carga`, que sale de `main` = `1d1a100`: +14 de `test_navegacion_validacion_pie.py` y +9 de `test_carga_asistente.py` —«Siguiente» se queda en el mismo fondo, el panel de validación cuenta lo que de verdad verificó y avisa si faltan precios, el aviso legal del pie sale también sin resultados, y el asistente de carga escapa el nombre del archivo y el símbolo—. Avisos: 2149. Antes: **1972 passed** (medido 2026-11-20 en Python 3.14 sobre la rama `fix/privacidad-copia-de-casos`, que sale de `main` = `e98a5c2`: +23 de `test_privacidad_captura.py` —la copia de casos solo lleva tipos de movimiento y símbolos de vocabulario conocido, el Action propio de Schwab e IBKR no se reescribe, y `promote_case.py` valida sus identificadores—. Avisos: 2103. Antes: **1949 passed** (medido 2026-11-19 en Python 3.14 sobre la rama `feat/pais-sugerido`, que sale de `main` = `7e8b38f`: +22 de `test_pais_sugerido.py` —el país que sugiere la zona horaria del navegador, y que sugerir no es declarar—. Avisos: 2103. Antes: **1927 passed** (medido 2026-11-19 en Python 3.14 sobre la rama `feat/recorrido-siete-pasos`, que sale de `main` = `eff6b38`: +8 de `test_recorrido_siete_pasos.py` —el recorrido pasa de 8 pasos a 7 y las seis identidades se comprueban rompiéndolas, no leyendo su texto—. Avisos: 2103. Antes: **1919 passed** (medido 2026-11-18 en Python 3.14 sobre la rama `feat/textos-al-popup`, que sale de `main` = `01e7d0c`: +10 de `test_textos_al_popup.py` —el texto largo de «La matriz» pasa a un popup, con un guard por frase y otro por tamaño del bloque movido—. Avisos: 2107. Antes: **1909 passed** (medido 2026-11-18 en Python 3.14 sobre la rama `feat/preguntas-con-su-cifra`, que sale de `main` = `d8168f5`: +12 de `test_preguntas_con_su_cifra.py` —las cuatro preguntas de abajo, con el momento de cada cifra y el reparto de columnas vigilado por AST— y +1 en `test_vigilar_data.py`. Avisos: 2094. Antes: **1896 passed** (medido 2026-11-18 en Python 3.14 sobre la rama `feat/total-de-la-cuenta`, que sale de `main` = `d1f53d2`: +11 de `test_total_de_la_cuenta.py` —la línea «pusiste · tienes hoy · tu resultado» de arriba de los resultados, con el guard de que la caja NO use el objeto fiscal, que duplicaría el DRIP—. Avisos: 2107, cuatro más que vienen de importar la vista en los tests nuevos. Antes: **1885 passed** (medido 2026-11-18 en Python 3.14 sobre la rama `feat/reparto-en-barras`, que sale de `main` = `24c8a08`: +10 de `test_reparto_en_barras.py` —el reparto deja de ser una dona y pasa a dos barras a la misma escala, una por portafolio, con un tramo por fondo que se sigue pudiendo aislar—. Avisos: 2103, los mismos. Antes: **1875 passed** (medido 2026-11-16 en Python 3.14 sobre la rama `feat/fondo-por-fondo`, que sale de `main` = `3d0b8c8`; ya en `main` = `9f493e1`. Los seis PR de la propuesta de interfaz v2 suman 91 desde 1784: [#271](https://github.com/gdeaxx-pixel/dividend-analyzer/pull/271) +15 (`test_ficha_portafolios.py`, cada fila de «Por portafolio» abre su ficha), [#272](https://github.com/gdeaxx-pixel/dividend-analyzer/pull/272) +14 (`test_paso_siguiente.py`, el pie del recorrido y la etiqueta de origen), [#273](https://github.com/gdeaxx-pixel/dividend-analyzer/pull/273) +28 (`test_titulos_compactos.py`, un tope por componente), [#274](https://github.com/gdeaxx-pixel/dividend-analyzer/pull/274) +7 (`test_controles_comparacion.py`), [#275](https://github.com/gdeaxx-pixel/dividend-analyzer/pull/275) +16 (`test_narracion_metodo_comparacion.py`) y [#276](https://github.com/gdeaxx-pixel/dividend-analyzer/pull/276) +9 (`test_fondo_por_fondo.py` y un caso más en `test_ruta_botones_etf.py`). Avisos: 2103, los mismos. Antes: **1784 passed** (medido 2026-11-14 en Python 3.14 sobre la rama `feat/narracion-portafolios`, que sale de `main` = `6db4e69`: +9 de `test_narracion_portafolios.py` —las tres filas de «Por portafolio» se revelan en orden, la barra negativa crece desde el cero y solo se anima una vez por cifras— y +1 en `test_carga_medidor_al_pie.py`. Antes: 1774 sobre la rama `feat/guia-pdf-descarga`, que sale de `main` = `a599e17`: +8 de `test_guia_pdf.py` —la guía viaja con la app, el paso 1 la ofrece, sin el archivo no revienta, y cuatro guards de que el PDF no publique datos de ninguna cuenta—. Antes: 1766 sobre la rama `feat/carga-notas-y-avisos` = `6247746`, que sale de `main` = `720d840`: +9 de `test_contraste_notas.py` —el gris de las notas llega a 4.5:1 sobre los tres fondos, con dos anclas que validan la propia fórmula— y +7 de `test_aviso_archivo_equivocado.py` —el paso 2 reconoce el historial del paso 1 y no confunde el CSV de posiciones—, más +1 en `test_carga_posiciones_csv.py`. Antes: 1749 sobre la rama `feat/carga-mas-simple`, que sale de `main` = `5a10b87`: +10 tests de `test_carga_medidor_al_pie.py` —el medidor baja al pie y no vuelve arriba, la frase concuerda, el titular conserva su regla de tamaño— y +1 neto en `test_carga_un_camino.py`, que pasa a exigir qué camino se abre según el bróker. Avisos: 2103, los mismos. Antes: 1739 sobre la rama `fix/lector-capturas-sdk-pin`, en `3d08303` y repetido igual en su punta `0870779`, que sale de `main` = `cae1645`: +7 tests de `test_vision_wire_format.py` —el cuerpo que el SDK manda a Gemini lleva `mimeType`, sin red ni cuota— y +3 de `test_carga_aviso_lector.py` —el paso 2 distingue «tu captura no sirve» de «nuestro lector está caído»—. Avisos: 2103; los nuevos son `DeprecationWarning` de `_UnionGenericAlias` que trae `google-genai==2.20.0` en Python 3.14, no de nuestro código. Antes: 1729 sobre la rama `fix/metodologia-telefono` = `a96f0ab`, que sale de `main` = `2d47c0d`: +4 tests de `test_metodologia_telefono.py`, Metodología cabe en el ancho del teléfono. Antes: 1725 sobre la rama `feat/letra-y-titulos` = `8e92e7a`, que sale de `main` = `cf39c60`: +45 tests de `test_letra_y_titulos.py`, letra de 11 px como mínimo y títulos en letra normal. Antes: 1680 sobre la rama `feat/cifras-un-formato` = `2227f7c`, que sale de `main` = `710e89e`: +23 tests de `test_cifras_un_formato.py`, un solo formato de cifras en dólares, y +2 de `test_cashflow_desborde.py` por el ancho nuevo de 900 px. Con `real_examples/` y `CONY_test.csv`). Avisos: unos 2100, todos de yfinance (`inplace=`, obsoleto en pandas 3 desde #248); ninguno de nuestro código. Antes: 1655 sobre `d33774b` (+7 de `test_todos_los_fondos.py`, #260). Antes: 1648 sobre `a91742a` (+11 de `test_vigilar_compacto.py`, #259). Antes: 1637 sobre `72ea174` (+21 de `test_carga_un_camino.py`, #258). Antes: 1616 sobre `fix/cache-dividendos-oficiales` fusionada con `245c11e` (+22 de `test_dividendos_oficiales.py`, #256: los dividendos YieldMax del cache contra la tabla oficial, todos sin red). Antes: 1594 sobre `4e848b6` (+13 de `test_navegacion_visible.py`, #257). Antes: 1581 sobre `f32391a` (+16 de los arreglos rápidos de interfaz, #255: 15 en `test_arreglos_rapidos_ui.py` y 1 en `test_vista_impuestos_render.py`). Antes: 1565 sobre `07cf19c` + los 22 tests de `test_cashflow_desborde.py` (la tarjeta del Cash flow no se sale del iframe a 10 anchos × 8 pasos y el alto de respaldo cubre el peor caso; sin Playwright se saltan). Antes: 1543 sobre `f84cba3` (+3 de #252, los tests del cierre del menú; uno arranca un Streamlit real y se salta sin Chromium). Antes: 1540, sin avisos, sobre
`main` = `85cedfd` + los 3 tests de `test_subyacente_ticker.py` (el Módulo 1 ya no pide «Multi» ni «Mag-7» a Yahoo), con `real_examples/` y `CONY_test.csv`). Antes: 1537 sobre `cf04c54` + el test de que todo YieldMax de la lista blanca tiene ficha en `knowledge/instruments.yaml` (#244); 1536 sobre `489e9a6` + los 2 tests del snapshot de 2022 de `test_estres_2022.py` (#243: nada en vivo; todo fondo que la app reconoce, congelado); 1534 sobre `0c5b812` + el test de huecos del TWR inválido a mitad de serie (#242); 1533 sobre `b131dc2` + los 5 tests G4 de `test_estres_2022.py` (cada fondo simulado en 2022, al dólar), igual en 3.11 y en 3.14; 1528 sobre `b131dc2` (#236, +15 de la prueba de estrés 2022); 1513 sobre `d48e4ed`; 1481 sobre `81b40c9` + los 4 tests de huecos R3/C6/PD de `analyze_portfolio` (2026-10-09). Antes: 1477 sobre `81b40c9`. Antes: 1470 sobre `a71aa7f`,
tras los PRs de la auditoría app-audit 2026-10-07 (#202 +3, #203 +2, #204 +0, #205 +1, #206 +0).
Después: #208 y #210 +0 (F4, `metricas.py` y `movimientos.py`), #211 +3 (huecos de mutante CA-1,
TP-3 y HB-1b), #213 +0 (`filas_csv.py`), +3 (huecos FC-1, FC-2, RY-1 de `filas_csv.py`). Desde #203 la suite corre también en CI en cada PR: allí, sin datos privados, da
~1362 passed / 87 skipped — el gate es exit 0, no la cuenta.)

Línea base en la **nube** (sin `real_examples/` y sin red hacia Yahoo): **1458 passed, 94 skipped, 1 deselected** (corrida del workflow «Suite en PR» del #256 sobre `main` = `245c11e`, 2026-10-30, Python 3.14: los 22 tests del contraste oficial no necesitan red; antes 1436/94/1 en el #257, 1423/94/1 en el #255 y 1407/94/1 en el #254, donde `test_cashflow_desborde.py` se salta sin Playwright; 1407/93/1 en el #252, 1405/92/1 en el #245, 1402/92/1 en el #244, 1401/92/1 en el #243, 1399/92/1 en el #242, 1398/92/1 en el #241 y 1342/91/1 el 2026-10-09). En CI el gate es exit 0, no la cuenta. No sustituye a la línea local. Para volver a medir la local, con `real_examples/` montado y la carpeta para ti sola: `./.venv/bin/python tools/verificacion_m4_local.py`.

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
- Mergea el agente (desde 2026-10-29), `gh pr merge --squash`, nunca `--auto`. Solo si: base `main`,
  `gh pr checks --watch` todo en verde, rama al día con `main` (si no, `gh pr update-branch` y
  esperar el verde otra vez) y la verificación local hecha. **Mergear no es desplegar**: después,
  health de Streamlit Cloud (skill `actualizar-app`) y reportar a Daniel enlace + SHA de `main`.
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
