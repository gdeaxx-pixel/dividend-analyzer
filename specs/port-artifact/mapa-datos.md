# Mapa de datos — de dónde sale cada cifra de cada vista

> Fuente del port: `Obsidian/APPs/Dividend-Analyzer/demos/viaje-dinero-waterfall.html`
> (3,990 líneas; byte a byte idéntico al artifact publicado `4f5b3f19`).
>
> Este documento existe porque el demo **no tiene un objeto de datos único**. Sin este
> mapa, un ejecutor inventa nombres de campo y el port sale roto por dentro aunque se
> vea idéntico.

## La regla que gobierna todo

El propio demo lo declara en su pie (línea 1531) y en su nota de cifras (línea 1527):

> «Esta página mezcla **dos juegos de datos, y ninguno es inventado**. El recorrido de un
> ETF («Cash flow», «Salud NAV», «Hoja Excel») usa el caso real de Schwab… La sección
> **«Método tradicional»** usa cifras **tal cual**: la matriz sale de la hoja de la clase,
> los precios de Yahoo Finance y los datos de fondo de las fichas de YieldMax.»

De ahí sale la división que hay que respetar sin excepción:

| Vista | Origen | ¿Se conecta al CSV? |
|---|---|---|
| Cash flow | Caso Schwab · MSTY | **SÍ** |
| Hoja Excel | Derivada del Cash flow | **SÍ** |
| Salud NAV | A construir | **SÍ** |
| Comparación · Real | A construir | **SÍ** |
| Comparación · Simulación | Modelo paramétrico | **NO** |
| Método tradicional (5 vistas) | Hoja de la clase + Yahoo + fichas YieldMax | **NO** |
| Metodología (11 entradas) | Bibliografía y fórmulas | **NO** |

**Conectar al CSV una cifra de la columna «NO» es un fallo de fase.** No son datos de
relleno esperando una fuente: son observaciones reales de terceros, citadas, que pierden
su sentido si se recalculan con el portafolio del usuario.

---

## 1 · Cash flow — `viaje-dinero-waterfall.html:2124-2127`

Único bloque de constantes limpio de todo el demo. Doce números:

```js
var POCKET = 605.43, BRUTO = 361.05, IMPUESTO = 105.08, NETO = 255.97,
    DRIP = 219.73, CASH = 36.24, TOTAL_TRABAJANDO = 825.16,
    MERCADO = -703.27, VALOR_HOY = 121.89, CAPITAL_ACTUAL = 158.13,
    RESULTADO = -447.30, PICO = 966.48;
```

Claves **verificadas** corriendo `analyze_portfolio` sobre `fixtures/schwab_synth_1`
(no son suposiciones — se listaron del dict real):

| Constante | Significado | Clave exacta en `stats` |
|---|---|---|
| `POCKET` | Capital aportado del bolsillo | `pocket_investment` |
| `BRUTO` | Dividendo bruto acumulado | `total_dividends + withheld_tax_total` ¹ |
| `IMPUESTO` | Retención NRA al cobro | `tax_summary['withheld_real']` ² |
| `NETO` | Dividendo neto percibido | `total_dividends` |
| `DRIP` | Porción reinvertida | `dividends_collected_drip` |
| `CASH` | Porción en efectivo | `dividends_collected_cash` |
| `TOTAL_TRABAJANDO` | Capital expuesto al mercado | `pocket_investment + dividends_collected_drip` |
| `VALOR_HOY` | Valor de mercado actual | `market_value` |
| `MERCADO` | Impacto del mercado | `market_value − TOTAL_TRABAJANDO` |
| `CAPITAL_ACTUAL` | Capital actual total | `market_value + dividends_collected_cash` ³ |
| `RESULTADO` | Resultado real | `CAPITAL_ACTUAL − pocket_investment` |
| `PICO` | Mayor suma de categorías del recorrido | máximo por paso; escala del mosaico |

¹ **No existe** una clave `dividends_gross` en `stats`. (Sí existe una con ese nombre dentro
del dict de fila de `build_hoja_excel`, `logic.py:3697` — otro namespace, no confundir.)
El bruto se reconstruye sumando el neto y lo retenido.

² `withheld_tax_total` está en `stats` y es la misma cifra, pero **la fuente canónica es
`tax_summary`** (Regla 3: objeto fiscal único, se renderiza, no se recalcula). Usar
`stats['tax_summary']['withheld_real']`.

³ Esta identidad ya está en el código, con su razón: `logic.py:989` hace
`gross_value = market_value + dividends_collected_cash`, y el comentario de `logic.py:987`
explica que el DRIP **no** se suma aparte porque ese dinero ya está dentro de
`market_value`. Ese es exactamente el doble conteo que denuncia la vista «Hoja Excel».

Otras claves útiles para vistas posteriores: `roc_percent`, `roc_source`, `price_cagr`,
`shares_owned`, `shares_owned_drip`, `shares_owned_pocket`, `tax_summary` (dict anidado),
`withheld_by_year`, `tax_refund_observed_by_year`.

**Regla dura:** `IMPUESTO` es `withheld_real` (base `gross_withheld`, momento *al cobro*).
NO es `net_estimated` ni `refund_estimated`. La devolución estimada es otro momento y va
rotulada aparte — Reglas 2 y 3 de `specs/roc-nra-invariants.md`.

Además:
- `STEP_LABELS` (línea 2131) — 8 etiquetas fijas de UI, no son datos.
- `pasoActual = 7` (línea 2135) — el demo arranca en el paso final. En el port, el paso
  vive en `st.session_state`.

---

## 2 · Hoja Excel — `initHoja()`, línea 3000

**No introduce datos nuevos.** Deriva todo del bloque anterior:

```js
var TOTALINV  = POCKET + NETO;                 // el «total invertido» de la hoja vieja
var APARENTE  = VALOR_HOY + NETO - POCKET;     // el retorno aparente (con doble conteo)
var INICIO    = "2024-12-05", TICKER = "MSTY"; // contexto de la posición
```

Solo hacen falta dos entradas adicionales: **fecha de la primera compra** y **ticker**.

El punto de la vista es que `APARENTE` vuelve a sumar el DRIP que ya está dentro del valor
de mercado; la brecha contra el retorno real **es exactamente el reinvertido**. Esa
identidad debe seguir cumpliéndose con datos reales — es el chequeo natural de la vista.

Ojo (Regla 4): el `roc_pct` que usa `build_hoja_excel` es el **19a ponderado histórico**,
deliberadamente distinto del `roc_pct_used` de `build_tax_summary` (ROC realizado del
holder). **No unificarlos.**

---

## 3 · Salud NAV — placeholder, línea 1097

Hoy es un `soon` con badge «En diseño». Se construye sobre `logic.classify_roc_health`
(`logic.py:2790`), que ya corre en producción.

**Regla 4, carril de destructividad:** el veredicto se mide con la **tendencia del NAV en
el tiempo**, nunca con el `%` de ROC. Un ROC alto puede ser eficiencia fiscal o capital
consumiéndose; solo la trayectoria lo distingue. Una vista que coloree el veredicto por
`roc_pct` está rota aunque compile.

---

## 4 · Comparación · Simulación — `series()`, línea 2825

**Modelo paramétrico, NO datos de mercado.** Construye el índice desde una tabla de fondos
`F` con `price`, `div`, `roc` e `incep`, y tres modos:

```js
w = mode === "bruto" ? 0 : mode === "plano" ? RATE : RATE * (1 - f.roc);
```

`bruto` (sin retención) · `plano` (peor caso 30%) · `roc` (ROC-aware, 19a).

Se porta **tal cual**, con sus cifras. Es una simulación etiquetada como tal, y el demo la
declara explícitamente como uno de los dos escenarios simulados de toda la página.

## 5 · Comparación · Real — placeholder, línea 1239

Se construye sobre `logic.build_drip_comparison_series` (`logic.py:5210`), que ya existe y
tiene 6 tests. Reinversión **por evento** (no potencia), base 100, incepción tardía arranca
en su propia base, y degrada a serie vacía si falla la descarga.

---

## 6 · Método tradicional — `initMetodo()`, línea 3204 · **NO TOCAR**

Cinco vistas sobre una cartera ajena, de una hoja fechada **5/1/2026**:

```js
var MATRIZ = [
  { t:"CONY", ini:"9/6/2023",  dr:74.05, inv: 9004.87, div:22873.37, … },
  { t:"NVDY", … }, { t:"MSTY", … }, { t:"TSLY", … }, { t:"NFLY", … }
];
var TOT = { inv:48286.22, div:111689.71, totHoja:159980, val:72509.21, ult:4409.09 };
var PRUEBA_DRIP = [ … ];   // techo teórico vs valor real, 5 fondos
var ESCALERA   = [ … ];    // 4 filas: lo anunciado → la cifra honesta
```

Estas cifras **no son del usuario y no deben conectarse a su CSV**. Vienen de la grabación
de la clase, de precios de Yahoo Finance y de las fichas de YieldMax, y están citadas por
minuto en la sección de Metodología. Sustituirlas por datos del portafolio destruye el
argumento de la sección, que es precisamente auditar *esa* hoja.

La única excepción declarada: los modos **«Con NRA · ROC 19a»** y **«Con NRA · peor caso
30%»** de las matrices son escenarios simulados, y ya vienen rotulados como tales. Se
portan con su rótulo intacto.

> Contexto de auditoría previa: los netos de estas matrices son sintéticos (30% plano sobre
> cifras brutas observadas). El «4 de 5, excepción NVDY» que aparece en el texto es
> artefacto de esa mezcla, no un hallazgo del portafolio de nadie. No re-derivar.

---

## 7 · Metodología — 11 entradas, líneas 1409-1530 · **NO TOCAR**

Contenido educativo con bibliografía y fórmulas. Se porta como HTML estático completo.
Incluye las fuentes citadas (grabación de clase, Yahoo Finance, fichas de YieldMax) y los
anclajes `mt-*` que el breadcrumb usa para el enlace «¿Cómo funciona? →».

---

## Cifras que NO pueden ser ground truth fijo

- **Valor de mercado** — depende del precio del día (yfinance). En los fixtures va como
  `null` a propósito.
- **Cualquier cosa derivada del valor de mercado** — `MERCADO`, `VALOR_HOY`,
  `CAPITAL_ACTUAL`, `RESULTADO`, `PICO`.

Lo que sí es determinista y por tanto verificable sin red: aportado, dividendos brutos y
netos, retención, reinvertido y efectivo.
