# Auditoría M1/M2/M4 — el efectivo que no es dividendo dentro del balde del dividendo

- **SHA auditado:** `333bcc2` (`main` al empezar), árbol limpio. El fix se midió también sobre el
  árbol **fusionado** con `origin/main` = `5714469` (#141 y #142 entraron durante la sesión).
- **Fecha:** 2026-09-24. **Entorno:** Mac de Daniel, `.venv/` del repo, `real_examples/` montado,
  con red.
- **Contrato leído primero:** `specs/roc-nra-invariants.md`.
- **Disparo:** en producción, Cash flow y Hoja Excel de MSTY mostraban «Las cifras de este
  recorrido no cuadran entre sí — no se dibuja para no mostrar un gráfico que miente ·
  neto = reinvertido + efectivo: 269.35 ≠ 287.67».

---

## Paso 0 — estado

```
barrido.sh   PASS=8 WARN=5 FAIL=1      (línea base documentada: PASS=9 WARN=5 FAIL=0)
pytest -q    1103 passed, 2 skipped, 3 deselected, 0 xfailed   (CLAUDE.md declaraba 906)
```

Dos desvíos de la línea base, **ninguno causado por este trabajo** — ver §Hallazgos 4 y 5.

---

## Hallazgo 1 — el efectivo no distributivo vivía en el balde del dividendo

**MÓDULO** · M1 (base de una cifra en dólares) · M2 (clasificación de filas del CSV)

**HALLAZGO** · La rama `is_misc_cash` de `logic.py` sumaba `Cash In Lieu`, `Special Qual Div`,
`ADR Mgmt Fee` y `Wire Received` a `dividends_collected_cash`, que es de donde el recorrido del
dinero saca el efectivo **del dividendo** — un total con dos bases, prohibido por la Regla 2.

**EVIDENCIA** (MEDIDA) · `logic.py:1407` (antes del fix). Agregado por `Action` del MSTY real de
`real_examples/charles_schwab_data/daniel_zambrano`:

```
Cash Dividend        4 filas     36.24
Cash In Lieu         1 fila      18.32     ← no es una distribución
NRA Tax Adj         54 filas   -111.10
Reinvest Dividend   50 filas    334.01
Reinvest Shares     50 filas   -233.79
```

`dividends_collected_cash` = 36.24 + 18.32 = 54.56. El NETO del objeto fiscal
(`build_dividend_tax_totals`) es 370.25 − 111.10 = 259.15, y no contiene el Cash In Lieu —
correctamente, su `Action` no dice `dividend`. Resultado: `DRIP + CASH` supera al NETO en
**exactamente** $18.32 y `verificar_identidades` bloquea la vista.

**BASE/MOMENTO** · CASH: neto de dividendos, al cobro. Cash In Lieu: efectivo no distributivo,
al cobro. Bases distintas, mismo total.

**ALCANCE** (MEDIDO, 3 CSV reales de Schwab · 9 posiciones):

| Caso | Ticker | Importe |
|---|---|---|
| daniel_zambrano · 2 | MSTY | $18.32 |
| daniel_zambrano · 2 | XLK | $8.47 |
| daniel_zambrano · 2 | SCHB | $3.55 |
| 1 | XLK | $44.76 |
| 1 | TSLY | $15.56 |
| 1 | MSTY | $5.17 |
| 1 | SCHB | $2.41 |

Los 4 casos de IB no tienen ninguna fila de esta familia: **cero** movimiento.

**VEREDICTO** · CORREGIDO en este PR. `misc_cash_total` + `misc_cash_breakdown` en `logic.py`;
`OTROS` como sumando propio del capital actual en `ui/adapters.py`; franja y leyenda propias en
`cashflow.html`; término propio en la ecuación de `hoja.html`.

**A/B (MEDIDO)** · 24 posiciones de los 4 casos: **Δ ROI = 0.0000 y Δ net_profit = 0.00 en todas**
— `gross_value` suma `misc_cash_total` por su cuenta. Lo que sí se mueve, y es el propósito:
`dividends_collected_cash` y `total_dividends` dejan de contener dinero que no es dividendo.

---

## Hallazgo 2 — el test que mentía (severidad mayor que el defecto)

**MÓDULO** · M4 (regla del test que miente)

**HALLAZGO** · `test_logic.py::test_i5_cash_in_lieu_y_companeros_entran_por_su_rama` afirmaba
`dividends_collected_cash == 10.46`: **codificaba el destino equivocado**. Verde con el defecto
puesto desde el #122.

**EVIDENCIA** · El fixture `_I5_CSV` no tiene DRIP ni retención, así que la identidad que el
defecto rompe no puede fallar ahí. Y los dos tests que sí ejercitan el guard
(`test_verificar_identidades_pasa_con_datos_reales_schwab` / `_ib`) corren sobre
`fixtures/schwab_synth_2` y el CSV de IB, **ambos con `DRIP = 0.0`**: el guard nunca se había
ejercitado con reinversión.

**VEREDICTO** · CORREGIDO. Test reescrito (afirma el balde correcto, que el dividendo queda en
cero y que la caja no se pierde) + 4 tests nuevos en `test_adapters.py` sobre un CSV con la forma
real (DRIP + retención + Cash In Lieu), incluido el mutante que devuelve el importe al efectivo.

**Sabotajes M4 (los 4 aplicados, medidos, restaurados):**

| Sabotaje | Cae |
|---|---|
| el misc vuelve a `dividends_collected_cash` | `test_el_efectivo_del_split_no_entra_en_el_balde_del_dividendo` + I5 |
| `gross_value` pierde `misc_cash_total` | `test_el_efectivo_del_split_sigue_contando_en_el_capital_actual` + I5 |
| `capital_actual` ignora `otros` | los dos tests del efectivo del split |
| el check de identidad deja de mirar `OTROS` | `test_el_efectivo_del_split_no_entra_en_el_balde_del_dividendo` |

---

## Hallazgo 3 — ABIERTO: `drip_sin_fuente` bloquea 6 posiciones por otra causa

**MÓDULO** · M2

**HALLAZGO** · Tras el fix, XLK ($3.52), SCHB ($2.76) y TSLY siguen rompiendo
`neto = reinvertido + efectivo`, y SVOL/QYLD además dan bolsillo negativo. La causa es distinta:
el export trae más filas `Reinvest Shares` que `Reinvest Dividend`, así que el bruto del CSV no
cubre lo reinvertido (`drip_sin_fuente = True`, ya declarado en `stats` desde E4).

**EVIDENCIA** (MEDIDA) · desglose del delta por causa en `daniel_zambrano`:

```
TK        delta     misc    resto  dripSF
MSTY      18.32    18.32     0.00   False
SCHB       6.31     3.55     2.76   True
XLK       11.99     8.47     3.52   True
```

**VEREDICTO** · ACEPTABLE CON NOTA, fuera de alcance. El guard bloquea con razón (los datos están
incompletos de verdad), pero el usuario solo lee «no cuadran»: merece un mensaje que nombre lo que
le falta al export. Requiere su propio PR.

---

## Hallazgo 4 — ABIERTO: el check 1 del barrido en FAIL es un falso positivo

**EVIDENCIA** · `ui/componentes/cobertura.html:143-152`, función `arco(i)`: calcula el path SVG de
un segmento de dona (5 × 72°) con `cos`/`sin`. Es geometría de dibujo, no una serie financiera
fabricada. Entró con el #125 y nadie actualizó la línea base del barrido.

**VEREDICTO** · CORREGIR el check (o su línea base), no la app. No se tocó aquí: cambiar un guard
en el mismo PR que arregla lo que ese guard vigila es mala práctica.

---

## Hallazgo 5 — la línea base de `CLAUDE.md` llevaba 201 tests de desfase

**EVIDENCIA** · Declaraba **906** (2026-09-04); `main` = `333bcc2` corría **1103**. Es el tercer
episodio del mismo descuido documentado en ese archivo.

**VEREDICTO** · CORREGIDO en este PR, y con la cifra de la nube de `main` conservada al lado.

---

## Cierre

```
pytest -q            1118 passed, 2 skipped, 3 deselected, 0 xfailed
                     (árbol fusionado con origin/main = 5714469; 1107 en la rama sola)
validate_real_cases  21 PASS · 0 FAIL · 15 SKIP
barrido.sh           PASS=8 WARN=5 FAIL=1  (el FAIL = Hallazgo 4, preexistente)
```

**Un skip no es un pass:** los 2 skips de la suite y los 15 del validador son los de siempre
(tickers sin datos en las capturas).

## Supuestos y materialidad

- **El Cash In Lieu es efectivo real de la cuenta** = sí, la fracción liquidada ya no está en
  `market_value` → si fuera al revés (que el bróker lo hubiera reinvertido), sacarlo de
  `gross_value` sería obligatorio y el ROI **sí** se movería. Se verificó por la vía contraria:
  el A/B exige Δ = 0, así que un error en este supuesto aparecería como una diferencia de ROI.
- **`Wire Received` se trata como el resto de la familia I5** = herencia del #122, no re-litigada
  aquí → si resultara ser una aportación de capital (bolsillo) y no un ingreso, su lugar sería
  `pocket_investment`, no `misc_cash_total`. No hay ninguna fila `Wire Received` con ticker en los
  4 casos reales (solo con `Ticker` vacío), así que hoy no mueve ninguna cifra de posición.
- **La frase «posición hoy + dividendos cobrados» (`logic.py:3780`) pierde el misc** = sí, baja
  hasta $18.32 en las posiciones afectadas → no cambia ningún veredicto (es una comparación contra
  el subyacente, con holgura de cientos de dólares). Esa línea arrastra además un defecto
  preexistente de base mixta: usa `dividends_collected_cash` BRUTO contra un `market_value` neto.
