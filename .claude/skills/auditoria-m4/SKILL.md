---
name: auditoria-m4
description: Auditoría M4 de la calculadora de dividendos — sabotaje de tests con mutantes. Úsala cuando pidan medir si los tests de verdad detectan errores («¿muerden los tests?», «auditoría M4», «sabotaje», «mutantes», «¿sirve este guard?»), antes de fiarse de una suite verde en cifras en dólares, o para cerrar un hallazgo con un test verificado. Aplica mutantes con la forma del bug real, mide cuántos tests los cazan en la suite completa, clasifica aserción/excepción desde el junitxml y restaura en binario. Incluye el arnés `scripts/m4.py` y las correcciones de las rondas 1 y 2 (2026-09-24/25).
---

# Auditoría M4 — ¿los tests muerden?

Una suite verde no prueba nada si ningún test cae cuando el código se rompe. M4 lo mide: se
introduce a propósito un error con la forma de un bug real («mutante») y se cuenta cuántos tests
lo cazan. Un mutante que sobrevive a la suite completa es un hueco. Si lo caza **un solo test**,
el guard es frágil.

Antes de empezar, lee **completo** `specs/roc-nra-invariants.md` (el contrato fiscal manda sobre
todo) y `CLAUDE.md` (reglas duras, líneas base, «Tests: si no muerde, no vale»). Lee también
los informes previos en `docs/auditorias/*-m4-*.md`: su tabla de mutantes es el punto de partida
y no hay que repetir lo ya medido.

## 0. Entorno — una sesión por carpeta

**Nunca** apliques mutantes en una carpeta donde trabaja otra sesión. Otra sesión que corra tests
verá tu mutante como un rojo «flaky», y un cambio de rama suyo mezcla el código que mides. Ya
pasó (cierre de la ronda 1): se anotó como «flake» un rojo que era el mutante G5-b funcionando.

- Mediciones auxiliares (efecto en dólares, verificar un test nuevo): `git worktree add` aparte,
  con su propia rama. El arnés acepta `M4_REPO=<worktree>`.
- Nube: `python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt pytest`.
- Si esperas un proceso en segundo plano, usa `pgrep -f "[m]4.py"` (con corchetes). Sin ellos,
  el bucle de espera se encuentra a sí mismo y nunca termina. Le pasó a la ronda 2.

## 1. Línea base — antes de tocar nada

```bash
./.venv/bin/python -m pytest -q                                  # la suite completa, nunca un subconjunto
./.venv/bin/python .claude/skills/auditoria-m4/scripts/m4.py base
```

- Tiene que coincidir con la línea base de `CLAUDE.md` para tu entorno (nube o local). Si no
  coincide, o hay algún rojo, **investígalo antes de medir mutantes**.
- **Un skip no es un pass**: di cuántos se saltan y por qué. En la nube se saltan ~80 tests
  (`real_examples/` y Yahoo).

## 2. Elegir guards y escribir mutantes

- 2-3 mutantes por guard, **con la forma del bug real**. Los mejores reintroducen un bug
  documentado (ronda 2: W-2 = bug de MU, W-3 = #94, W-6 = #115, O-1 = #143, PF-4 = origen de la
  Regla 4b). Después, la forma más plausible de un error de mantenimiento: signo, `>=`→`>`, una
  línea de bookkeeping borrada, un gate quitado, un argumento olvidado en la llamada.
- Busca en particular:
  - **Lógica duplicada**: la ronda 2 encontró dos copias del corte de 2 años (realizado y no
    realizado) y solo una tenía test.
  - **Bordes**: el mismo día, exactamente $0.01, exactamente 730 días.
  - **Bookkeeping que no mueve dólares pero sí casillas**: antigüedad y tramo. CG-1 y CG-4
    cambiaban ≥2 años por 0 días.
  - **El sitio de la llamada, no solo la función**: PF-4 no tocaba `_roc_pct_by_year`, sino la
    llamada que olvidaba pasarle el cierre.
  - **Ramas hermanas**: cuando se arregla un umbral, ¿la rama de al lado tiene el mismo borde?
    (R2-H4: el #115 arregló el gap y el ROC seguía con `> 0.01`).
- Formato, en un archivo fuera del repo (scratchpad):

```python
MUTANTES = [
  dict(id='CG-1', file='logic.py', que='la fila de split no reescala la antigüedad',
       old="            if shares > 0:\n                dias_wsum *= qty / shares\n            shares = qty\n",
       new="            shares = qty\n",
       target=['test_ganancias_capital.py::test_split_declarado_en_el_csv_reinicia_el_balance']),
]
```

- `old` tiene que aparecer **exactamente 1 vez**. Ojo con la indentación: un texto más corto
  puede estar contenido en otro más indentado. Añade contexto hasta que sea único.
- `target` son **nodeids concretos**, nunca un archivo entero: si el archivo tiene algún skip, el
  arnés aborta porque el objetivo no está «verde».

## 3. Medir

```bash
./.venv/bin/python .claude/skills/auditoria-m4/scripts/m4.py run /ruta/mutantes.py [ID ...]
```

Cada mutante tarda una suite completa (~70 s en la nube, ~3 min en local). El arnés imprime
`objetivo=ASSERT|EXC|VIVE`, los rojos nuevos en la suite y las alertas `SOBREVIVE A LA SUITE` /
`frágil: 1 solo test`. El detalle queda en `res_<ID>.json`.

- **Muerte por excepción ≠ muerte por aserción.** Repórtala aparte: el test cae, pero no por la
  cifra (G2-b en la ronda 1, PF-1 en la ronda 2).
- **Cuenta los tests que cazan cada mutante en toda la suite.** 0 es un hueco. 1 es un
  hallazgo, aunque sea aceptable si ese test está dedicado a eso.
- **Mide el efecto en dólares** de cada superviviente, en el worktree aparte: qué cifra cambia y
  de cuánto a cuánto. Sin eso no hay materialidad.

## 4. Tests tautológicos — mídelos, no los afirmes

Hay dos formas típicas:
- una vista que envuelve a otra (`hoja_data` llama a `cashflow_data`);
- un test que saca su esperado de la **misma función que audita** (los 36 tests de
  «Comparación» leían `_politica_fiscal` para calcular el esperado de `_politica_fiscal`).

Se demuestra con un mutante: si el mutante mueve los dos lados y el test sigue verde, es
tautológico. Anótalo así: «medido: el mutante X no lo pone rojo».

## 5. Datos reales

Si el único test que vigila un guard depende de `real_examples/`, en la nube no se puede medir:
- escribe una versión **sintética** que sí corra allí (ronda 2: H-3);
- añade el mutante a `MUTANTES` en `tools/verificacion_m4_local.py` (campo `archivo` si no es
  `logic.py`) para que Daniel lo corra en su Mac:

```bash
git checkout main && git pull && ./.venv/bin/python tools/verificacion_m4_local.py
```

Antes, comprueba que su copia esté al día. Si el bloque final solo trae G1-d y G5-b y dice
`logic.py restaurado` (no `logic.py, ui/adapters.py restaurados`), la copia está vieja y esa
corrida no vale.

## 6. Cerrar cada hueco con un test que muerda

- Un test nuevo solo vale cuando el mutante que antes sobrevivía lo pone **rojo por aserción**,
  leído del junitxml. Verifícalo con el arnés, con `M4_REPO` apuntando al worktree del test.
- Ancla el esperado a una **fuente independiente**:
  - un literal medido;
  - una relectura del CSV (`_bruto_independiente_del_csv`);
  - un yaml leído aparte (`knowledge/roc_ici.yaml`);
  - nunca la función auditada.
- Prefiere tests de **Regla 3b**: dos superficies del mismo número comparadas entre sí, sin
  conocer el umbral. Ejemplos: titular contra tarjeta renderizada, peldaño 6 contra peldaño 2
  `sin_roc`.
- Invariantes **estructurales**, nunca hechos de mercado (Regla 5). Por ejemplo,
  `basis_roc_adjusted ≤ basis` se cumple por construcción.
- **Nunca** amplíes una tolerancia ni metas un `xfail`: `CLAUDE.md` exige cero `xfailed`. Un test
  que se sabe rojo va con su arreglo, no antes.

## 7. Bugs de producción

- Un defecto real va en un **PR aparte**, y **antes de tocar producción se pide aprobación a
  Daniel**. Documéntalo con el efecto medido y una propuesta concreta.
- Si el arreglo solo cambia rótulos, dilo y demuéstralo: «ninguna cifra cambia», con las cifras
  antes y después en las fixtures.
- Verifica el arreglo con mutantes, incluido el que reintroduce el bug.

## 8. Entregables

1. **Informe** `docs/auditorias/<fecha>-m4-<ronda>-<sha>.md`, en su propio PR, con el formato de
   los anteriores:
   - por hallazgo: `MÓDULO / HALLAZGO / EVIDENCIA / BASE/MOM./MUNDO / VEREDICTO`;
   - la tabla de mutantes (guard, mutante, objetivo, rojos en la suite);
   - supuestos y materialidad;
   - apéndice con el diff exacto de cada mutante;
   - cada cifra marcada **MEDIDA** (con el comando que la reproduce) o **ESTIMADA**.
2. **Un PR de tests** con los huecos cerrados, cada test verificado con su mutante.
3. **La línea base de `CLAUDE.md` actualizada en el mismo PR** que cambia la cuenta. La local se
   marca ESTIMADA hasta que se mida en el Mac.
4. **Nota 1-10**, comparable con las anteriores. Ronda 1: 8/10 (1 de 15 sobrevivía). Ronda 2:
   6/10 al empezar, 7.5/10 al cerrar (12 de 41 sobrevivían). Explica qué la mueve.

Reglas del repo: rama + PR, **nunca** commit a `main`, Daniel mergea siempre. Si varios PRs tocan
la línea base de `CLAUDE.md`, habrá conflicto al fusionar el primero: se resuelve con merge de
`main` (nunca rebase de una rama ya publicada), volviendo a **medir** la suite sobre el árbol
fusionado.

## Comunicación

Daniel sigue la sesión desde el móvil y no es programador: mensajes cortos, en español, en
lenguaje llano (un mutante es «un error de prueba metido a propósito»). Nunca lenguaje de
compra/venta de activos.
