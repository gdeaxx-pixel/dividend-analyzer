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

> ✅ **CERRADO (2026-08-30).** Hubo un incidente: el commit automático `127e2f6` («refresh
> price/dividend/split cache») guardó una fila final `2026-08-28` con `Close = NaN` en los 14
> parquets — la sesión del día en curso, que yfinance devuelve sin publicar. El NaN se propagó
> por el motor de backtest, dejó **12 tests en rojo** y puso producción a mostrar
> «VALOR MER. $0.00» en todos los fondos, con el veredicto del DRIP invertido ($67,535 «a favor
> del efectivo»). **Verificado en la app desplegada, no inferido.** Mitigado con
> `git revert 127e2f6` (`20d2ca7`) y cerrado en el **#95**: `fetch_price_cache.py` descarta las
> filas finales con `Close` nulo, trata un nulo a media serie como fallo (conserva el cache
> previo, workflow en rojo) y hay un guard sobre los parquets versionados. La discriminación es
> segura porque yfinance **no emite fila** para festivos ni días sin sesión: una fila que existe
> con `Close` nulo solo puede ser una barra pendiente.
>
> Lección: el refresco automático es un commit a `main` como cualquier otro, y **no pasa por
> PR ni por review**. Si vuelve a romper algo, el síntoma será el mismo — series en cero — y el
> primer sitio donde mirar es la última fila de los parquets.

Línea base: **828 passed, 2 skipped, 3 deselected** (medido 2026-09-02 sobre la rama
`fiscal/base-desde-captura`, base `main` = `19b775a`. La captura de posiciones que el cliente
confirma en el paso 2 **nunca llegaba al motor**: `ui/vistas.py::_resultados` corría
`analyze_portfolio(df)` a secas, y `_wizard_positions` solo lo leía `ui/carga.py` para pintar
su propia tabla. Efecto medido en `?demo=schwab`: SCHB mostraba capital invertido de
**−$100.46** y ROI **−1,834.60%** a un cliente que ya había dado el costo correcto; ahora
$946.04 y 84.20%. Y el peldaño 5 pasa de cubrir 3 de 8 fondos a 5, con **+$2,918.94** de
ganancia latente que antes se declaraba no medible.
Entra `position_overrides` y **NO** `ib_cost_basis_map`: el segundo alimenta la ruta 'broker'
del ROC —la resta que M1 §4 descarta— y metía a SMH, un ETF amplio sin avisos 19a, en la
cobertura del peldaño 2 con un ROC del 0% que es ruido de comisiones. Medido: con él,
`cubiertos` 3→4 con el gravable inmóvil; sin él, 3.
La casilla 9 **no se mueve**: la convergencia del bloque de abajo se conserva.
8 mutantes M4 cazados, cada uno en su propio test.)

Antes: **815 passed, 2 skipped, 3 deselected** (medido 2026-09-02 sobre la rama
`fiscal/umbral-roc-tolerancia`, base `main` = `691cfdc`. El umbral que decide la ruta del ROC
(`_prefer_19a_roc`) comparaba con `<` ESTRICTO mientras la rama `elif` de al lado, sobre las
MISMAS dos cifras, ya usaba `max(2%, $0.50)`. Por esa asimetría PLTY quedaba fuera de la
cobertura fiscal por **72 centavos** (costo de bróker $535.32 contra $534.60 aportados,
0.13% — comisiones): caía a la ruta 'broker', su ROC salía −$0.72, el #101 lo rotulaba «sin
dato» y el fondo tributaba sobre el 100% del bruto teniendo un ROC oficial 19a del 66.48%.
Efecto medido: PLTY −0.78→66.48, cobertura 5/9→6/9, gravable $6,200.66→$6,113.61; SCHB, SMH
y XLK **no se mueven** porque no publican 19a y el gate los sigue frenando.
**Y hace converger las dos rutas de carga**: la casilla 9 de `ib_1` daba $1,340.21 sin
captura y $1,314.14 con captura — los $26.07 eran PLTY. Ahora las dos dan $1,340.21: subir
una foto ya no cambia cuánto impuesto te devuelven.
3 mutantes M4 cazados, dos de ellos SOLO tras añadir los tests de límite —«tolerancia
infinita» y «sin gate de 19a» sobrevivían a la primera tanda.)

Antes: **810 passed, 2 skipped, 3 deselected** (medido 2026-09-02 sobre la rama
`fiscal/credito-eeuu-momento`, base `main` = `cc7bd8a`, tras partir el CRÉDITO del peldaño 6
en sus dos momentos: lo retenido al cobro NO es todo acreditable, porque la parte que vuelve
al reclasificar el ROC nunca llegó a ser impuesto. Medido en `schwab_synth_1`: de $60.75
retenidos vuelven $41.29, así que el crédito real es **$19.46** — la vista mostraba los
$60.75 enteros, 3.1× inflado. `vuelve_por_roc` LEE `ruta_a.casilla9_esperada` (#102), no la
recalcula; `definitivo` es `None` —con motivo— cuando no hay con qué medir la devolución,
porque «medí cero» y «no pude medirlo» no son lo mismo. 3 mutantes M4 cazados.)

Antes: **804 passed, 2 skipped, 3 deselected** (medido 2026-09-02 sobre `main` = `40abad7`
FUSIONADO, no sobre la rama, tras la **Fase 4** — el peldaño 6 «¿Y en tu país?». Publica la BASE
declarable (dividendos en bruto, y aparte la parte que EE.UU. trató como renta y el ROC) y el
CRÉDITO por impuesto ya pagado a EE.UU., más las ganancias REALIZADAS separadas por el corte de
2 años y lo no realizado rotulado EXCLUIDO. **No publica tarifa ni total, a propósito**: la
tarifa del país de residencia es progresiva sobre la renta GLOBAL del contribuyente, que la app
no ve — publicarla sería inventar la base (Regla 2), y sumar dividendos con ganancias mezcla
naturalezas, casillas y momentos. El objeto lo declara en `tarifa_motivo` / `total_motivo`, no lo
omite. `logic.py` sin tocar: la capa solo LEE los peldaños 1, 2 y 4 (Regla 3). Los 4 mutantes M4
—recalcular el bruto, publicar tarifa, sumar en un total, mandar todas las ventas a `ge_2y`—
cayeron donde debían; el último solo lo caza un test que pinea el REPARTO por tramo, porque los
de reconciliación comparan la SUMA y ninguna fixture tiene una venta ≥2 años.
Ya no queda ningún peldaño «PRÓXIMAMENTE» en la escalera.

Antes: **785 passed, 2 skipped, 3 deselected** (medido 2026-09-01 sobre la rama
`fiscal/casilla9-sin-pais`, base `main` = `1389cfc`, tras sumar 7 tests — la Ruta A publica el
ROC recuperable (`ruta_a.casilla9_esperada`) aunque falte el país: `build_withholding_diagnosis`
antes cortaba en `sin_declarar` y devolvía `refund_roc: 0.0` sin calcularlo. Helper único
`logic._roc_refund_recuperable` (misma fórmula, sin duplicar) llamado también en la rama
`sin_declarar`; en `ui/adapters.py` un acumulador propio `refund_roc_casilla9_total` gateado solo
por `reconcilia` (no por `declarado`). El peldaño 4 NO amplía su alcance. Los 4 sabotajes de M4
—revertir la llamada en `sin_declarar`, quitar el guard `implausible`, gatear por `desglose_ok`,
forzar `retenido_estado='ok'`— fallaron donde debían.

Antes: **778 passed, 2 skipped, 3 deselected** (medido 2026-08-31 sobre la rama
`fiscal/peldano2-roc-sin-pais`, base `main` = `54381ae`, tras sumar 11 tests — el peldaño 2
de la vista de Impuestos publica el % de ROC aunque falte el país o la retención NRA
(`build_tax_summary._null` lo propaga por las dos rutas nulas), y un `roc_percent` NEGATIVO
—resta del método 'broker' que no cuadra— se rotula «sin dato» en el carril fiscal sin tocar
`stats['roc_percent']` (Regla 4). El cero MEDIDO se conserva. La vista declara la cobertura
(`gravable.sin_roc`/`cubiertos`/`total`) antes de la cifra. Los 3 sabotajes de M4 (guard del
negativo, guard del cero, `_null` deja de publicar) fallaron donde debían.

Antes: **767 passed, 2 skipped, 3 deselected** (medido 2026-08-30 sobre la rama
`fiscal/roc-base-costo`, base `main` = `c998feb`, tras sumar 11 tests en
`test_ganancias_capital.py` — **el ROC ya ajusta la base fiscal**, en una cifra APARTE
(`basis_roc_adjusted` / `gain_roc_adjusted`) que nunca pisa `basis`/`gain`: son dos momentos
distintos y la Regla 2 prohíbe mezclarlos. El ROC entra **fechado**
(`logic._roc_events_from_19a`) y se aplica dentro del mismo recorrido cronológico, porque a las
acciones vendidas solo les toca el ROC devengado ANTES de la venta — restar el acumulado al
final, o repartirlo a prorrata, da cifras distintas y medibles (MSTY del demo de IB: −$178.78
contra −$85.13 contra +$32.81). Solo se acepta la serie de los **19a**: el método `'broker'` no
tiene fecha que repartir y subestima el ROC al reinvertir (M1 §4). Los 4 sabotajes del protocolo
M4 fallaron donde debían y se restauraron.

> **Borde conocido, medido y NO cerrado.** La ruta del ROC (`_prefer_19a_roc`, `logic.py:1591`)
> se decide por si el costo del bróker quedó por DEBAJO de (aportado + reinvertido). PLTY del
> demo de IB cae a **$0.72** de ese umbral: dos centavos al otro lado mueven su ROC de −$0.01 a
> **$96.26** y cambian si su base se ajusta o no. El defecto de fondo es más ancho que el borde
> —cuando el snapshot del bróker es anterior a la reclasificación anual, la app concluye ROC ≈ 0
> para un fondo que publica 46% en sus 19a—. No se tocó: mueve `roc_percent` en toda la app y
> merece su propia auditoría. La vista sí lo declara: `fiscal_roc.tickers_19a_sin_ajuste` nombra
> esos fondos para que el alcance no se lea como «los demás no tienen ROC».

Antes: **756 passed, 2 skipped, 3 deselected** (medido 2026-08-30 sobre la rama
`fiscal/ganancias-capital`, base `main` = `4366f20`, tras sumar 31 tests en
`test_ganancias_capital.py` — el motor de ganancia de capital por **costo promedio ponderado**
(`logic.build_capital_gains`) y el quinto peldaño de la vista de Impuestos. Eje NUEVO: ni
`pocket_investment` (flujo de caja neto) ni `net_profit` sirven de base fiscal. **El gate que
vale es el cruzado sobre los demos** (`test_cruce_contra_analyze_portfolio_sobre_los_casos_reales`),
que cazó dos defectos que los fixtures sintéticos no vieron: acciones llegadas por traspaso con
`Amount $0.00` diluyendo la base (XLK de `?demo=schwab`, $1,087.00 de ganancia fantasma) y el
doble ajuste por split cuando la fila viene DENTRO del CSV (MSTY de `?demo=schwab2`, 5.39% en
las acciones). En aquel momento el ROC **todavía no ajustaba esta base** (lo declaraba en
`roc_basis_adjustment_applied: False`); entró después, en `fiscal/roc-base-costo`. Antes: **725 passed, 2 skipped, 3 deselected** (medido
2026-08-30 sobre la rama `fiscal/fixtures-fuente-unica`, base `main` = `e8c1924`, tras sumar 2 guards en
`test_contrato_componentes.py`: `fixtures/generate_fixtures.py` queda **desarmado** —decía ser la
fuente de los fixtures y dejó de serlo hace ~5 commits; correrlo revertía 4 correcciones
auditadas (MLK Day, shares split-ajustadas, clasificaciones `unreliable`, `Received`→`Reported`)—
y `schwab_synth_1` se contradecía a sí mismo sobre el bruto de MSTY: $156 en el income CSV y en
`expected.json`, $116 en las transacciones, por una fila `Reinvest Dividend` escrita en negativo.
`verify_fixtures.py` cruza ahora las transacciones contra `income_expected` y lo habría cazado.
Antes: **723 passed, 2 skipped, 3 deselected**
(medido 2026-08-30, `main` = `c650d4f`, tras los #95 y #96). Los #95 (guard de la barra pendiente, +6 tests) y #96 (el veredicto de
W-8BEN compara en dólares, +9 tests) entraron sobre los 708 de `20d2ca7`. Del #96:
el VEREDICTO de W-8BEN compara EN DÓLARES (`exceso` vs `holgura = bruto·TASA_TOLERANCIA_PP/100 +
N·0.01`), reusando el `n_tax_rows` que ya expone `applied_withholding_rate` — mismo principio que
el guard `implausible` del #94, una capa más abajo. En producción MU (cliente colombiano) daba
«Revisa tu W-8BEN» por un exceso real de $0.0040. Antes: **708 passed, 2 skipped, 3 deselected**
(medido 2026-08-29 sobre la rama
`fiscal/guard-falsos-positivos`, base `main` = `21384da` = #93, tras sumar 8 tests: el guard de
la tasa imposible compara EN DÓLARES con un término absoluto `N·0.01` (N = nº de filas de
impuesto) en vez de en puntos porcentuales — el redondeo de centavos del bróker es absoluto y
se acumula por pago (perfil YieldMax semanal). El techo del 30% y `TASA_TOLERANCIA_PP` no se
tocan. Antes: **700 passed, 2 skipped, 3 deselected** (medido 2026-08-29 sobre la rama
`fiscal/foreign-tax-paid`, base `main` = `e4fb6c5` = #92, tras sumar 10 tests: separar
`Foreign Tax Paid` (impuesto extranjero, ZIM/Israel) del eje de retención NRA vía
`_is_nra_withholding_action` — coherente en `withheld_tax_total`, `_classify_tax_rows` y familia
—, el campo `foreign_tax_paid_total` en `stats` y su línea propia en la vista de Impuestos.
Antes: **690 passed, 2 skipped, 3 deselected** (medido 2026-08-29 sobre la rama
`fiscal/ib-reversos-split`, base `main` = `0ba86c9`, tras sumar 7 tests: el clasificador único
de reversos de split de IB —`_classify_tax_rows`— con su invariante `al cobro == neteado +
devuelto` contra el CSV real, la guarda de la tasa aplicada imposible, y la reescritura de los
3 tests que codificaban la vieja exclusión de IB en bloque). Antes: **683 passed, 2 skipped, 3
deselected** (medido 2026-08-28 sobre la rama
`fiscal/vista-impuestos`, base `main` = `319a5d0`, tras sumar 9 tests en
`test_vista_impuestos.py` — la escalera fiscal de cartera Fase 2 + el fix del bucket gris
negativo: reconciliación cruzada del peldaño 1 contra `cashflow_data`/`hoja_data`; el residuo
al cobro contra `withheld_at_payment` con reembolso positivo (repro de auditoría); el guard
'parcial' cuando `withheld_at_payment` no reconcilia (reversos de split inverso en IB); «sin
país ⇒ peldaño 3 None»; la regresión ROC 100 %). OJO: `main` corría **674** de verdad al
ramificar, no los 668 que esta línea seguía afirmando — desfasado otra vez (nadie actualizó
tras el #90). Antes: **668 passed, 2 skipped, 3 deselected** (medido 2026-08-25 sobre la rama de la
tercera línea de «Sin DRIP» — cosechar el efectivo hacia `CMP_COSECHA_DESTINO`/SCHB en vez
de dejarlo quieto, base `main` = `0fbaa73` —, tras sumar 21 tests en
`test_comparacion_data.py`: 12 en `TestCosechaHaciaDestino` —ground truth congelado,
ausencia para el propio destino y para tickers sin dividendo, arranque común con
`idxSin`/`precioSin`—, 7 en `TestIdentidadCosechaAlPropioTicker` —gate de identidad: cosechar
al propio ticker reproduce «Con DRIP» exacto en `bruto`/`plano`, y por qué NO en `roc`
(más acciones ⇒ más `roc_receivable`, divergencia esperada, no un bug)—, y 2 en
`TestDobleConteoDeEfectivo` —TRI constante debe reproducir `idxSin` sin sumar `cash_accum`
de más, y un destino que no cubre la ventana devuelve `None` en vez de interpolar). Antes:
**647 passed, 2 skipped, 3 deselected** (medido 2026-08-25 sobre `main` =
`9d95dbf`, tras podar el menú Detalle a solo Portafolios: `ui/heredadas.py` pierde las
vistas Ingresos, Proyección y Estrategias —1136 líneas—, y `test_estrategias_datos.py`
se jubila completo porque su sujeto ya no existe; se van 7 tests netos). Antes: **654
passed, 2 skipped, 3 deselected** (medido 2026-08-25 sobre `main` =
`e17a639`, tras podar 4 claves de `metodo_data()` sin consumidor —`ratiosTot`, `nra`,
`paybackContraejemplo`, `ymMedido`— y `pbn` de `ratios[]`: se van 9 tests, no 4 —
`test_ymmedido_real_yield_reconcilia_contra_matriz` estaba parametrizado ×5 tickers, la
cuenta a ojo lo pasó por alto la primera vez—. 663 en `main` antes de esta poda (661 más
los 2 del guard de sintaxis, PR #86). Antes: **660**, medido 2026-08-23 sobre `main` =
`b72f4ae` — y quedó desfasado enseguida, porque el #84 añadió su guard de balance sin tocar
esta línea; `main` corría 661 de verdad. Con el #71 —vistas heredadas con base mixta, A2/A3— y el #72 —las 3 copias inline
del predicado de fila-de-impuesto al predicado único, más cobertura IB de la tasa aplicada—
dentro. **Ninguno de los dos PRs actualizó este número, y menos mal**: cada uno medía sobre su
propia rama (658 y 657), habrían chocado al mergear y los dos habrían quedado mal — el real
post-merge sólo se sabe midiendo el árbol fusionado. Antes: 655 tras el #68 —enrutar la familia
`_dividend_*` al predicado único— y el #69 —congelar la entrada del caché en los tests de
cifras—. Antes: 651 passed, 2 skipped, 3
deselected, medido 2026-08-21 tras poner el cierre
fiscal por delante de la estimación 19(a): 644 antes; 636 tras jubilar el motor fiscal viejo —la poda quitó 15 tests del motor retirado y añadió 15 sobre el objeto vivo
`_politica_fiscal`, la cuenta no se movió pero la cobertura sí cambió de dueño—, más 8 de
`test_roc_ici.py` — el parser del ICI histórico, ver
`Obsidian/IA/traspaso-2026-08-21-roc-historico-ici.md`). Este número envejece en cuanto alguien añade tests: si tu PR
cambia la cuenta, **actualízalo aquí en el mismo PR**. Ya estuvo desfasado en 74 tests sin que
nadie lo notara, y volvió a desfasarse en 2 entre `a2dd335` (538, lo que decía esta línea) y
`95c0932` (540, que es lo que `main` corría de verdad): el #57 añadió dos tests sin tocar este
número.

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
