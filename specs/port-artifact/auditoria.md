# Checklist de auditoría — port del artifact

> Se entrega al ejecutor a propósito: debe saber contra qué se le mide antes de escribir
> la primera línea. La auditoría la corre Claude en el repo canónico (con acceso a los
> casos reales), no en el worktree.
>
> **Si eres el ejecutor: los comandos de abajo dicen `.venv/bin/python` porque son del
> repo canónico.** En tu worktree ese venv no existe — fue eliminado del control de
> versiones en el commit de saneamiento `e7fd033`. Traduce siempre a `.venv-port/bin/python`,
> y no intentes crear un `.venv/`. Los pasos 3 y 4 no puedes correrlos: necesitan los casos
> reales, que están fuera de tu árbol a propósito. Tu receta de verificación es la del
> traspaso, § Verificación.

Cada fase cierra con un veredicto escrito en el traspaso:
**pasa** · **pasa con correcciones** (lista exacta) · **se devuelve**.

---

## 1 · Los cálculos no se tocaron

```bash
git diff --stat logic.py
```

Debe salir **vacío**. Cualquier línea cambiada se revisa una a una y, salvo justificación
aprobada por Daniel, se revierte. `logic.py` son 5,281 líneas de lógica fiscal validada con
meses de tests; el port es de presentación.

## 2 · La suite sigue verde

```bash
.venv/bin/python -m pytest test_logic.py test_report.py -q
```

Y con los casos reales, que el ejecutor nunca vio:

```bash
DIVIDEND_REAL_EXAMPLES_DIR="$HOME/.local/share/dividend-analyzer/real_examples" \
  .venv/bin/python -m pytest test_real_examples.py -q
```

**Baseline medido el 2026-08-05, antes de que el ejecutor tocara nada.**
Son **dos** líneas base distintas — compararlas entre sí produce falsos positivos:

| Comando | Repo canónico | Worktree del ejecutor |
|---|---|---|
| `pytest test_logic.py test_report.py -q` | **197 passed, 2 skipped** | **196 passed, 3 skipped** |
| `pytest test_real_examples.py -q` **con** `DIVIDEND_REAL_EXAMPLES_DIR` | **21 passed** | n/a |
| `pytest test_real_examples.py -q` **sin** la variable | 6 skipped | **6 skipped** (limpio) |

**El skip de diferencia está explicado y es correcto:** `test_logic.py:284` («CONY_test.csv
no disponible»). Ese archivo está sin rastrear en el canónico —lo bloquea el `*.csv` de
`.gitignore:37`— así que no existe en el worktree. Los otros dos skips son idénticos en
ambos: `test_logic.py:219` (archivo IB real) y `test_logic.py:916` (sin `real_examples/`).

Cualquier cifra por debajo de la línea base **de su propio entorno** es una regresión hasta
que se demuestre lo contrario.

**Si el ejecutor modificó un test:** no basta con que pase. Se saboteaba la función que el
test cubre y se confirma que el test **falla**. Un test que pasa con la función rota no es
un test.

## 3 · Los casos reales siguen cuadrando

```bash
DIVIDEND_REAL_EXAMPLES_DIR="$HOME/.local/share/dividend-analyzer/real_examples" \
  .venv/bin/python validate_real_cases.py
```

Aquí es donde salen los fantasmas que los fixtures sintéticos no ven.

## 4 · El invariante fiscal aguanta

```bash
.venv/bin/python -m pytest test_logic.py -k tax_summary_is_single_source -q
```

Más revisión manual: **ninguna vista nueva recalcula el impuesto**. Se busca aritmética de
retención fuera de `tax_summary`:

```bash
grep -rn "withheld_tax_total\|estimate_roc_refund\|0.30\|NRA_DEFAULT_RATE" ui/ app_v2.py
```

Todo acierto debe ser una lectura de `tax_summary`, no un cálculo propio. Y se comprueba
que los dos `roc_pct` siguen separados (Regla 4): `roc_pct_used` de `build_tax_summary` vs
el 19a ponderado de `build_hoja_excel`. **Unificarlos es un fallo grave.**

## 5 · Los fixtures siguen cuadrando

```bash
.venv/bin/python fixtures/verify_fixtures.py
```

Exit 0. Verificado que detecta sabotaje (se le cambió un valor esperado y falló).

## 6 · Consola limpia, con evidencia

Se capturan los **dos** flujos y se recorre la navegación completa:

- stdout/stderr del proceso Streamlit
- `read_console_messages` del navegador

Falla ante `Traceback`, `Uncaught`, `TypeError`, `ReferenceError` o cualquier
`console.error`. **Los logs se adjuntan al veredicto**; «no vi errores» no es evidencia.

## 7 · Fidelidad visual

Capturas del demo y de `app_v2.py` lado a lado con Chrome headless: mismo ancho, tema claro
y oscuro. El desborde se mide **en el contenedor, no en el documento** — con `overflow-x:
auto` el chequeo a nivel documento siempre da 0 y no prueba nada. Se mide la caja y la
celda, en varios anchos.

Nota: las capturas por elemento recortan gráficos con scroll. Un recorte **no** se reporta
como bug de render sin que Daniel lo mire.

## 8 · A/B contra la fase anterior

Antes de cada fase se guarda una copia intacta y se sirven ambas por HTTP. Sin esto se
reportan regresiones que nunca ocurrieron.

## 9 · Nada omitido

```bash
grep -rn "TODO: IMPLEMENT\|TODO: placeholder\|NotImplementedError\|pass  # pendiente\|# resto del código\|# aquí va\|# \.\.\." ui/ app_v2.py
```

Un `TODO` normal es una nota legítima y **no** falla la fase. Lo que falla es código
declarado como entregado que en realidad está vacío.

## 10 · Paridad (solo Fase 5)

`specs/port-artifact/paridad.md` sin celdas vacías en las 37 filas. Se abren 5 filas al
azar y se confirma que la ubicación citada contiene de verdad la función.

---

## Orden de ejecución

1 → 2 → 5 → 4 → 3 → 6 → 7 → 8 → 9 → (10 en Fase 5)

Los baratos y deterministas primero: si `logic.py` está tocado o la suite está roja, no
tiene sentido gastar tiempo en capturas.
