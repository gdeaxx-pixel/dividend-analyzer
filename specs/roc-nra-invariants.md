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

---

## Regla 3 — Reconciliación entre vistas mediante un objeto fiscal único

**Requirement:** Debe existir en `logic.py` UN único objeto `tax_summary` por ticker con los campos `{retenido_real, retención_justa, devolución_estimada, por_año}`. Todas las vistas que muestren cifras fiscales (cuadritos del viaje del dinero, Hoja Excel, paso "Impuesto NRA", y cualquier vista futura) deben **renderizar** ese objeto — nunca recalcular el concepto con su propia lógica. "Misma función" no es suficiente si cada vista la invoca con parámetros o alcance distintos; tiene que ser el mismo objeto consumido, no la misma fórmula reimplementada.

> **Implementado (2026-07-28).** `logic.build_tax_summary(stats, ticker, base_rate_pct=None)` calcula el objeto por ticker (capa 1, dentro de `analyze_portfolio`, tasa `NRA_DEFAULT_RATE`); `logic.build_tax_summaries(results, base_rate_pct=None)` lo re-deriva barato por país (capa 2, en `app.py`), reusando por IDENTIDAD el objeto cacheado cuando la tasa coincide. Reusa `estimate_roc_refund`/`estimate_roc_refund_by_year` tal cual — no reimplementa su matemática. Las 4 vistas (migas, cuadritos, tabla "② vista honesta", Cuadrícula B) y `build_hoja_excel` leen ese mismo objeto vía `_tax_sum(_vj_tk)` / `tax_summaries` en `app.py`; el paso "Impuesto NRA" (antes el único cálculo inline) fue refactorizado para leerlo también. Gate de reconciliación: `test_tax_summary_is_single_source_across_views` en `test_logic.py` (verifica identidad del objeto entre `analyze_portfolio`, `build_tax_summaries` y `build_hoja_excel`, y que coincide con invocar `estimate_roc_refund_by_year` directamente, tolerancia $0.01).

**Scenario:** Tres vistas, un solo cálculo
- **WHEN** el usuario abre los cuadritos del viaje del dinero, la Hoja Excel y el paso "Impuesto NRA" para el mismo ticker en la misma sesión
- **THEN** las tres vistas leen el mismo `tax_summary` del ticker y muestran valores de `retenido_real`, `retención_justa` y `devolución_estimada` idénticos entre sí (no solo "consistentes", sino la misma fuente)

**Scenario:** Test de reconciliación como gate de deploy
- **WHEN** se agrega o modifica cualquier cifra fiscal en una vista
- **THEN** un test de harness suma el impuesto neto mostrado por cada vista para el mismo ticker y falla si difieren en más de $0.05 — la divergencia la debe cazar pytest antes del deploy, no una revisión manual

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

Fuente: memoria del agente `feedback_dividend-invariante-roc-nra.md` (2026-07-14). Este archivo es el contrato vigente en el repo; la memoria conserva el porqué se aprendió.
