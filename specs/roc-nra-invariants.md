# Invariantes ROC / NRA — contrato fiscal de la Dividend Analyzer

> Contrato vigente para cualquier cifra en dólares de impuesto, retención NRA o ROC (Return of Capital) que la app calcule o muestre — cuadritos del viaje del dinero, Hoja Excel, paso "Impuesto NRA", o cualquier vista futura.

## Caso origen

**2026-07-14.** La sección "Hoja Excel" y los cuadritos del viaje del dinero mostraban la retención NRA real del CSV ($105) como pérdida permanente. Al mismo tiempo, el paso "Impuesto NRA" — que sí corre `estimate_roc_refund_by_year` — reportaba que ~$75 de esos $105 vuelven en la reclasificación anual del broker como ROC. Dos verdades distintas para el mismo dólar, mostradas en la misma sesión de la app.

Causa raíz: no existe una fuente única del "impuesto neto real de esta posición". Cada vista recalcula el concepto por su cuenta —`withheld_tax_total` crudo en cuadritos, `roc_dollars` en Hoja Excel, `estimate_roc_refund_by_year` en el paso NRA— así que la divergencia es estructural, no un bug puntual. Este caso es el ejemplo real de violación de las Reglas 2 y 3 de abajo.

---

## Regla 1 — El capital aportado es invariante

**Requirement:** El capital aportado (`pocket_investment` / costo real desplegado) NO puede cambiar como efecto de una reclasificación fiscal del ROC. La reclasificación solo mueve dos cosas: el bucket IMPUESTO (cuánto de lo retenido es retención real vs. devolución esperada) y la base fiscal de la posición (relevante para la ganancia de capital futura, no para el capital ya aportado).

**Scenario:** Reclasificación anual de una distribución ya cobrada
- **WHEN** el broker reclasifica al cierre del año una distribución que antes se trató como dividendo ordinario, marcándola ahora como ROC (19a)
- **THEN** el capital aportado mostrado en cualquier vista de la app permanece exactamente igual al que había antes de la reclasificación; solo cambian el bucket de impuesto y la base fiscal registrada para esa posición

**Scenario:** Señal de alarma — cifra sospechosa por definición
- **WHEN** una vista muestra un "capital real" o "capital ajustado" que sube o baja después de aplicar un porcentaje de ROC
- **THEN** esa cifra se considera sospechosa por definición y debe rechazarse o corregirse antes de desplegar — el ROC nunca es motivo válido para mover el capital aportado

---

## Regla 2 — Toda cifra declara su base y su momento

**Requirement:** Cualquier cifra en dólares de impuesto/ROC/NRA que se muestre en la UI debe declarar explícitamente dos atributos: **base** (bruto / neto / base-fiscal) y **momento** (al cobro / tras reclasificación anual). Ninguna operación (suma o resta) puede combinar dos cifras que difieran en base o en momento dentro de la misma fila o el mismo total.

**Scenario:** Retención al cobro vs. reclasificación anual (el bug del caso origen)
- **WHEN** se muestra la retención NRA de $105 tomada al momento del cobro (retención real del CSV, momento = "al cobro", base = "bruto retenido")
- **THEN** esa cifra NO puede presentarse en la misma fila o total que la devolución estimada de $75 calculada por `estimate_roc_refund_by_year` (momento = "tras reclasificación anual") sin declarar ambos momentos por separado; combinarlas sin distinguir el momento es el bug documentado

**Scenario:** Fila con base mixta
- **WHEN** una vista arma una fila de "Neto real" restando una cifra en base-fiscal de una cifra en base bruta
- **THEN** la fila se rechaza en revisión — antes de publicar, cada operando debe rotularse con su base (bruto/neto/base-fiscal) y verificar que coincidan entre sí

### Regla 2b — El mundo es la tercera dimensión (añadida 2026-08-21)

**Requirement:** Cuando una cifra describe un escenario **contrafáctico** —«si no se hubiera reinvertido», «si hubiera retención», «si se hubiera vendido»— además de base y momento declara su **mundo**: la corrida de simulación de la que sale. **Una fila contrafáctica toma TODAS sus columnas de la misma corrida.** Nunca se combina una columna del mundo que ocurrió con otra del mundo que no ocurrió.

Base y momento no bastan para detectar este error: en el bug del caso origen las dos cifras eran brutas y las dos estaban tomadas al cobro. Lo que difería era **qué simulación las produjo**.

**Scenario:** La fila «Sin DRIP» con dividendos del mundo que sí reinvirtió (bug real, 2026-08-21)
- **WHEN** la fila «Sin DRIP» muestra «Inversión Hoy» tomada de `run_backtest(drip=False)` y en la misma fila muestra «Dividendos» tomados de `run_backtest(drip=True)`
- **THEN** la fila se rechaza: en el mundo sin reinversión las acciones extra nunca se compraron, así que nunca pagaron esas distribuciones. Medido: $165,780 contra $67,307 reales (2.46×), total inflado 2.25×, y el veredicto DRIP-vs-efectivo invertido en 2 de 5 fondos

**Scenario:** El nombre lleva el mundo encima
- **WHEN** un adaptador expone los dividendos de dos corridas distintas
- **THEN** los campos se llaman de forma que el mundo sea evidente en el punto de USO (`div` / `divSin`), no solo en el docstring de origen — en el bug real el docstring declaraba correctamente que `div` venía de la corrida con DRIP, y aun así se consumió en la fila equivocada

---

## Regla 3 — Reconciliación entre vistas mediante un objeto fiscal único

**Requirement:** Debe existir en `logic.py` UN único objeto `tax_summary` por ticker con los campos `{retenido_real, retención_justa, devolución_estimada, por_año}`. Todas las vistas que muestren cifras fiscales (cuadritos del viaje del dinero, Hoja Excel, paso "Impuesto NRA", y cualquier vista futura) deben **renderizar** ese objeto — nunca recalcular el concepto con su propia lógica. "Misma función" no es suficiente si cada vista la invoca con parámetros o alcance distintos; tiene que ser el mismo objeto consumido, no la misma fórmula reimplementada.

> **Implementado (2026-07-28).** `logic.build_tax_summary(stats, ticker, base_rate_pct=None)` calcula el objeto por ticker (capa 1, dentro de `analyze_portfolio`, tasa `NRA_DEFAULT_RATE`); `logic.build_tax_summaries(results, base_rate_pct=None)` lo re-deriva barato por país (capa 2, en `app.py`), reusando por IDENTIDAD el objeto cacheado cuando la tasa coincide. Reusa `estimate_roc_refund`/`estimate_roc_refund_by_year` tal cual — no reimplementa su matemática. Las 4 vistas (migas, cuadritos, tabla "② vista honesta", Cuadrícula B) y `build_hoja_excel` leen ese mismo objeto vía `_tax_sum(_vj_tk)` / `tax_summaries` en `app.py`; el paso "Impuesto NRA" (antes el único cálculo inline) fue refactorizado para leerlo también. Gate de reconciliación: `test_tax_summary_is_single_source_across_views` en `test_logic.py` (verifica identidad del objeto entre `analyze_portfolio`, `build_tax_summaries` y `build_hoja_excel`, y que coincide con invocar `estimate_roc_refund_by_year` directamente, tolerancia $0.01).

> **Ampliado (PR B, objeto fiscal bruto/retención/neto).** `build_tax_summary` cubre retenido/retención-justa/devolución (el eje de la *reclasificación* ROC). Faltaba un objeto para un eje distinto: cada broker declara `dividendos cobrados` en una BASE distinta (Schwab: bruto, retención en fila `NRA Tax Adj` aparte; IB: neto, la retención va plegada dentro de la propia fila `Dividend - Foreign Tax Withholding`) — asumir ciegamente `bruto = neto + retenido` (correcto solo para IB) duplicaba la retención en Schwab (bug real: MSTY reportaba $600.60 de bruto en vez de $462). `logic.build_dividend_tax_totals(history_df)` es el objeto único para ese eje: detecta la convención POR FILA (`_dividend_tax_netted`, no asume el broker) y devuelve `{gross, withheld, net, gross_source, net_source, netted, gross_by_year, net_by_year, withheld_by_year}`, cada cifra con su procedencia declarada (`'leido'` del CSV vs `'derivado'` aritméticamente desde la otra + la retención — nunca reconstruye el bruto sumando hacia atrás si el CSV ya lo entrega). `analyze_portfolio` lo cachea por ticker (`dividends_gross_total`, `dividends_net_total`, `dividend_base_convention`, `dividends_gross_by_year`/`dividends_net_by_year`); `build_hoja_excel`, `build_tax_summary` y `ui.adapters.cashflow_data` lo leen por identidad — ninguno debe volver a calcular `net + withheld` por su cuenta. Gate de reconciliación: `test_build_dividend_tax_totals_schwab_style_no_duplica_retencion` / `..._ib_style_neteada_en_la_fila` en `test_logic.py` (contra `fixtures/schwab_synth_2` y `real_examples/interactive_brokers_data/1`, ground truth verificado), más `ui.adapters.verificar_identidades(datos, stats)` — que además de las identidades definitorias de `cashflow_data`, reconcilia BRUTO/NETO contra una relectura independiente del CSV (`logic._csv_dividends_in_window`), no contra la fórmula que los generó.

> **Actualizado (2026-08-23, familia `_dividend_*` al predicado único).** El ledger que alimenta
> `build_dividend_tax_totals` (`_csv_dividends_in_window` / `_csv_dividends_by_year` /
> `_dividend_events`) excluye AHORA las filas de impuesto en AMBAS convenciones vía el predicado
> único `logic._is_tax_row_action` y suma CON SIGNO (las reversas de IB restan — nunca `abs()`:
> medido, convertía cada reversa en suma e inflaba el bruto IB +55–78%). Consecuencias: el ledger
> es BRUTO en los dos brokers (antes, en IB era el NETO sin declararlo — violación silenciosa de
> esta Regla 2), `build_dividend_tax_totals` devuelve `{gross: 'leido', net: 'derivado'}` en ambas
> convenciones (`netted` queda como procedencia declarada, ya no cambia la aritmética), y
> `dividend_base_convention` pasó de `'neto_leido'/'bruto_leido'` a `'retencion_en_fila'/
> 'retencion_aparte'`. Invariante cruzado probado en `test_logic.py`
> (`test_familia_dividend_declara_bruto_ib_por_ticker` / `..._schwab`): las tres hermanas ==
> `gross` para cada ticker. El guard independiente `ui.adapters._bruto_independiente_del_csv`
> conserva su copia deliberada del criterio para no depender del predicado que audita.

> **Actualizado (2026-08-29, clasificador único de filas de impuesto).** Los reversos de split
> inverso de IB aparecen en el CSV como un par exacto (retención negativa + su reverso positivo,
> mismo día / |importe| / ticker). `logic._classify_tax_rows` es el primitivo único que los
> empareja 1:1 y voraz (`Counter`) y separa: **retención al cobro real** (negativas − revertidas)
> y **reembolsos genuinos** (positivas huérfanas = crédito de reclasificación ROC). Lo consumen
> `withheld_at_payment_by_year` (antes contaba TODAS las negativas → tasa aplicada imposible
> >30% para IB → falsa alarma «Revisa tu W-8BEN») y `observed_tax_refund_by_year` (antes excluía
> IB en bloque → tiraba reembolsos ROC reales, "pendiente" de dinero ya recibido). `withheld_tax_total`
> NO cambió: ya neteaba por signo y su cifra sigue siendo la buena. Invariante que lo ata:
> `al_cobro == neteado + ya_devuelto`, exacto, medido sobre el CSV real de IB en CONY/MSTY/TSLY/NVDY
> (`test_tasa_aplicada.py::test_ib_real_ground_truth_los_cuatro_tickers`,
> `test_logic.py::test_ib_observed_refund_separa_reverso_de_split_de_reembolso_genuino`). Guarda
> blanda en `applied_withholding_rate` (`'implausible'`): una tasa aplicada > techo NRA hace que
> `build_withholding_diagnosis` caiga a `'indeterminado'` en vez de acusar de W-8BEN vencido.

> **Actualizado (2026-08-29, «Foreign Tax Paid» ≠ retención NRA).** El eje de retención NRA es
> ahora `_is_nra_withholding_action` = `_is_tax_row_action` MENOS la frase exacta
> `'foreign tax paid'`. `Foreign Tax Paid` es impuesto de otra jurisdicción retenido por un
> emisor extranjero (ZIM/Israel: $0.63 + $2.11 en dic-2024); no tiene techo del 30%, no se
> relaciona con el W-8BEN y su remedio es crédito fiscal en el país de residencia. Sumarlo con
> la NRA producía tasas aplicadas > 30% (imposibles). **La trampa:** en IB la retención NRA se
> llama `Dividend - Foreign Tax Withholding` — el discriminante es `'foreign tax paid'` EXACTO,
> nunca `'foreign tax'`. El **bruto** sigue excluyendo las tres clases (`_is_tax_row_action`, sin
> tocar); solo se estrecha el eje de retención: `_classify_tax_rows`, `withheld_at_payment_by_year`,
> `observed_tax_refund_by_year`, `withheld_tax_total` y `withheld_tax_total_by_year` — todos
> coherentes, o se rompe el invariante `al_cobro == neteado + devuelto`. Campo nuevo
> `foreign_tax_paid_total` / `_by_year` en `stats`; en la vista de Impuestos es una **línea
> aparte**, nunca un cuarto bucket. Los 4 tickers de IB (sin ninguna fila `Foreign Tax Paid`) no
> se movieron ni un centavo; SCHB del fixture pasó de al-cobro $0.53 a $0.45 con el FTP en su
> propio campo.

> **Actualizado (2026-08-29, el guard de la tasa imposible compara en DÓLARES).** La holgura de
> `applied_withholding_rate['implausible']` es absoluta, no en pp: el error que absorbe es el
> redondeo de centavos del bróker (el 30% de $0.12 son $0.036 → Schwab redondea a $0.04 → 33.3%
> aparente), que es absoluto y ocurre POR PAGO. `techo = bruto·(30 + TASA_TOLERANCIA_PP)/100 +
> N·0.01`, con `N` = nº de filas de retención NRA. Una tolerancia en pp contra el bruto total no
> contempla la acumulación (20 pagos de $0.15 al 30% real dan 33.3%: perfil YieldMax semanal). El
> techo del 30% y `TASA_TOLERANCIA_PP` **no se tocan**; para importes materiales (bruto > $100) el
> veredicto es idéntico al de antes. El caso IB pre-clasificador ($4,117.61 / $1,628.35 / 40
> filas) se sigue cazando.

> **Actualizado (2026-08-30, el VEREDICTO de W-8BEN también compara en DÓLARES).** El guard de
> `implausible` (arriba) tapaba, una capa más abajo, el mismo defecto en la decisión del veredicto
> de `build_withholding_diagnosis`, que se tomaba en pp (`abs(applied − entitled) ≤
> TASA_TOLERANCIA_PP`). Al arreglarse el guard (#94), MU (cliente colombiano, 30% con derecho)
> quedó dando `'tratado_no_aplicado'` por un exceso REAL sobre el 30% de **$0.0040** — el 30% de
> $0.12 son $0.036 y el bróker redondea a $0.04. Ahora:
> `exceso = retención_al_cobro − bruto·derecho/100`;
> `holgura = bruto·TASA_TOLERANCIA_PP/100 + N·0.01` (N = filas de impuesto NRA, **reusado** del
> dict de `applied_withholding_rate`, no recalculado — Regla 3). `abs(exceso) ≤ holgura` →
> `'coincide'`; `exceso > holgura` → `'tratado_no_aplicado'`; `exceso < −holgura` →
> `'menor_de_lo_esperado'`. `TASA_TOLERANCIA_PP` y `NRA_TECHO_ESTATUTARIO` no se tocan;
> `applied_pct` se sigue publicando (es lo que se muestra, deja de ser lo que decide). La
> descomposición `refund_roc`/`gap_w8ben` no cambia. Los 4 fondos de IB y sus veredictos quedan
> igual.

**Scenario:** Tres vistas, un solo cálculo
- **WHEN** el usuario abre los cuadritos del viaje del dinero, la Hoja Excel y el paso "Impuesto NRA" para el mismo ticker en la misma sesión
- **THEN** las tres vistas leen el mismo `tax_summary` del ticker y muestran valores de `retenido_real`, `retención_justa` y `devolución_estimada` idénticos entre sí (no solo "consistentes", sino la misma fuente)

**Scenario:** Test de reconciliación como gate de deploy
- **WHEN** se agrega o modifica cualquier cifra fiscal en una vista
- **THEN** un test de harness suma el impuesto neto mostrado por cada vista para el mismo ticker y falla si difieren en más de $0.05 — la divergencia la debe cazar pytest antes del deploy, no una revisión manual

### Regla 3b — El alcance se declara, y hay más de un eje (añadida 2026-08-21)

**Requirement:** La Regla 3 no se cumple nombrando un objeto: se cumple nombrando **todos los ejes de cifras financieras del repo** y asignándole a cada uno su objeto único. Un eje sin objeto nombrado no está cubierto aunque la regla exista.

Ejes vigentes y su objeto único:

| Eje | Objeto único | Vistas que lo renderizan |
|---|---|---|
| Impuesto/ROC de la cartera del CSV | `logic.build_tax_summary` | cuadritos, Hoja Excel, paso NRA |
| Base bruto/neto por convención de bróker | `logic.build_dividend_tax_totals` | Hoja Excel, cashflow, tax_summary |
| **Escenarios fiscales simulados** | **`ui.adapters._politica_fiscal`** → `escenarios` | **tablas Con/Sin DRIP y 3ª gráfica de «La matriz»; «Comparación · Simulación»; «Comparación · Real»** |
| **%ROC por año fiscal** | **`ui.adapters._roc_pct_by_year`** — cierre fiscal (`logic.load_roc_ici`) por delante de la estimación (`logic.load_roc_19a`), año por año | alimenta a `_politica_fiscal`, o sea las 4 vistas |

> **Por qué se añadió.** Hasta el 2026-08-21 el tercer eje no existía en este contrato, y por eso pudo crecer con **dos metodologías simultáneas**: las tablas reescalaban en JS (`bruto × (1 − tasa)`, un solo paso al final) mientras la gráfica simulaba evento a evento. La misma pantalla mostraba $177,289 y $78,816 para la misma cifra, con **562 tests en verde**. La regla estaba escrita y era correcta; lo que faltaba era que este eje estuviera dentro de su alcance.

> **Migración de «Comparación · Simulación» (2026-08-21).** Ese panel era el último punto del repo donde el escudo ROC vivía **dentro de la tasa** (`_cmp_nra_rate`, hoy `_tasa_efectiva_neta`): `0.30 × (1 − ROC)` aplicado al cobro, o sea asumiendo que el dinero nunca sale del fondo. La app decía «Con NRA · ROC 19a» en dos secciones con dos modelos distintos. Hoy corre `_politica_fiscal` como «La matriz» —30% completo al cobro y reembolso con el 1042-S en su fecha—, y la brecha entre los dos modelos, medida en su propio universo, va de **−18.7 pp (TSLY) a +28.0 pp (MSTY)** en el retorno total Con DRIP. Guardas: `test_comparacion_data.py::TestUnSoloModeloRoc` (espía lo que el motor RECIBE — ninguna corrida puede llegar con una tasa entre 0 y 30%) y `::TestReconciliacionConElMotor`.
>
> **`_tasa_efectiva_neta` no se borró y no es un modelo huérfano:** sigue siendo la tasa efectiva **reportada** («8.7%–17.6% según el fondo» en la nota al pie de la 3ª gráfica). Como cifra de cierre de ciclo es correcta; lo que una tasa no puede expresar es el momento. Que exista una función así es lícito — lo que el contrato prohíbe es que gobierne una simulación.

> **Alcance cerrado el mismo día.** «Comparación · Real» (`trg_real_data`) también migró: corría `logic.build_drip_comparison_series` con el escudo dentro de la tasa, y la app llegó a mostrar **NVDY +250.85% en «Real» y +232.0% en «Simulación»** bajo la misma etiqueta «Con NRA · ROC 19a», a dos submenús de distancia. Hoy las cuatro vistas pasan por `_politica_fiscal`, y hay un test que **cruza las dos vistas de «Comparación» entre sí** (`test_un_solo_motor_fiscal.py::TestReconciliacionEntreLasDosVistas`), que es el guard que la Regla 3b exige y que no existía.
>
> Evidencia de que se cambió el modelo y no el motor de precios: al migrar, `bruto` y `plano` no se movieron **ni un decimal** en los 8 tickers —los dos motores ya coincidían donde no hay escudo que modelar— y `roc` se movió solo en los 4 fondos con avisos 19(a). `build_drip_comparison_series` / `build_roc_aware_withholding` / `build_total_return_series` quedaron sin consumidor vivo y se **borraron** de `logic.py` el mismo día, junto con sus 15 tests; la cobertura de los casos borde del mapeo ROC→año se trasladó al objeto vivo (`test_politica_fiscal.py`), que hasta entonces no tenía ninguna. Queda un guard que impide reintroducirlas (`test_un_solo_motor_fiscal.py::TestElMotorViejoNoVuelve`).

**Requirement (gate):** Todo eje con más de una vista necesita un test que compare **dos vistas del mismo número entre sí**, no cada vista contra sí misma. La fuente de cada lado debe ser genuinamente independiente (p. ej. una suma columnas redondeadas en el componente, la otra mensualiza la serie diaria del motor).

**Scenario:** Dos vistas del mismo número
- **WHEN** una cifra financiera aparece en dos vistas (una tabla y una gráfica, un modal y una fila)
- **THEN** existe un test que las reconcilia dentro de la tolerancia de redondeo declarada, y falla si divergen. Referencia viva: `test_contrafactico_sin_drip.py::TestReconciliacionVistas`

**Scenario:** Suite verde no es evidencia de coherencia
- **WHEN** se propone que un cambio es seguro porque «la suite pasa»
- **THEN** eso solo vale si existe al menos un test cruzado sobre las cifras tocadas; una suite compuesta únicamente de tests que verifican cada vista contra sí misma puede estar verde con dos pantallas contradiciéndose

---

## Regla 4 — Dos carriles del ROC que no se cruzan

**Requirement:** El ROC tiene dos usos que son independientes y nunca deben mezclarse en el mismo cálculo o mensaje:
1. **Destructividad del NAV** — se mide SIEMPRE con la tendencia del NAV a lo largo del tiempo, NUNCA con el ROC%. Esta es responsabilidad de `classify_roc_health`.
2. **Palanca fiscal** — el ROC% es el mecanismo que determina el escudo fiscal / devolución NRA (`estimate_roc_refund*`). Esto es responsabilidad de las funciones de estimación de devolución.

Un número que usa el ROC% para medir daño al NAV está mal. Un número que ignora el ROC% al calcular la carga fiscal está incompleto.

**Scenario:** ROC% alto no implica NAV destructivo
- **WHEN** un fondo reporta un ROC% de 80% en su distribución más reciente
- **THEN** la app NO usa ese 80% para calificar la salud del NAV; `classify_roc_health` evalúa exclusivamente la tendencia histórica del NAV para determinar si la distribución es destructiva

**Scenario:** Cálculo fiscal que ignora el ROC
- **WHEN** se calcula la retención NRA neta de una posición con distribuciones clasificadas parcialmente como ROC
- **THEN** el cálculo debe incorporar el ROC% vía `estimate_roc_refund*`; una cifra de "impuesto neto" que trata toda la distribución como dividendo ordinario (ignorando el ROC) se considera incompleta y no debe presentarse como final

**Nota al pie:** el ROC difiere la base fiscal para TODOS los inversionistas, tanto US como NRA. El ROC en sí mismo no es destructividad del NAV ni es retención de impuesto — es un mecanismo de diferimiento de base. Confundir "hay ROC" con "hay daño" o con "hay retención" es el error que las Reglas 1 y 4 buscan prevenir.

---

## Regla 5 — Un invariante estructural no es un hecho de mercado (añadida 2026-08-21)

**Requirement:** Antes de escribir una aserción sobre una propiedad financiera hay que responder: **¿esto se cumple por construcción, o se cumple porque los precios de hoy salieron así?** Solo lo primero se assertá como invariante. Lo segundo, si vale la pena fijarlo, se assertá como *existencia de un ejemplo* y con un mensaje que diga que fallar puede significar «cambió el mercado», no «hay un bug».

Un test que codifica una coincidencia de mercado se rompe sin que nadie haya roto nada, y entrena al equipo a ignorar fallos rojos.

**Scenario:** «Más impuesto ⇒ peor resultado» es FALSO con reinversión (caso real, 2026-08-21)
- **WHEN** se propone assertar que el escenario con más retención siempre termina por debajo del escenario sin retención
- **THEN** se rechaza para el mundo CON DRIP: el impuesto cambia el CAMINO (se reinvierte menos, y parte del dinero vuelve más tarde a otro precio). Medido: MSTY cayó −91.4% y el escenario «roc» termina en $10,235 contra $9,462 del escenario sin impuesto alguno — la retención actuó como retiro forzoso de un activo en colapso
- **Y THEN** sí se assertá en el mundo SIN DRIP, donde es estructural: sin reinversión el impuesto solo resta efectivo y no hay camino que alterar

**Scenario:** Qué sí es estructural en el eje fiscal
- **WHEN** hace falta una guarda de propiedad sobre los escenarios
- **THEN** se assertá que el **impuesto neto** crece con la severidad del régimen (`bruto = 0 ≤ roc < plano`) y que el **capital aportado** no se mueve entre escenarios — dos cosas que no dependen de ningún precio

**Nota:** esta regla es la hermana fiscal de la lección que ya protege `test_comparacion_data.py` («NAV cayendo ⇒ el efectivo gana» es falso). El patrón se repite: en un fondo con trayectoria violenta, la intuición monótona falla. Manda la trayectoria, no el destino.

---

Fuente: memoria del agente `feedback_dividend-invariante-roc-nra.md` (2026-07-14). Este archivo es el contrato vigente en el repo; la memoria conserva el porqué se aprendió.

Reglas 2b, 3b y 5 añadidas el 2026-08-21 tras el bug del contrafáctico «Sin DRIP» y la unificación de la metodología fiscal de «La matriz» (PR #59). Auditoría completa: `../Obsidian/APPs/Dividend-Analyzer/auditoria-2026-08-21-contrafactico-sin-drip.md`.
