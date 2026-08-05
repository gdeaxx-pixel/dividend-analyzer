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
| 1 | Bloque 1 · Transacciones CSV/Excel (`app.py:1356`) | | |
| 2 | Bloque 1 contraído + botón «editar» (`app.py:1424`) | | |
| 3 | Bloque 2 · Posiciones del portafolio (`app.py:1439`) | | |
| 4 | Bloque 2 · lectura de fotos con Gemini (`app.py:1455`) | | |
| 5 | Bloque 3 · Ingresos / income CSV (`app.py:1585`) | | |
| 6 | Paso a Resultados (`app.py:1724`) | | |
| 7 | Detección de bróker y errores de formato (`app.py:1380-1420`) | | |

## Secciones de resultados

| # | Función en `app.py` | Ubicación en `app_v2.py` / `ui/` | Comprobación |
|---|---|---|---|
| 8 | Tus dos portafolios (`app.py:3839`) | | |
| 9 | Portafolio dividendos (`app.py:3927`) | | |
| 10 | Hoja de Excel: te venden vs realidad (`app.py:3946`) | | |
| 11 | Ingreso y comparación con el broker (`app.py:4205`) | | |
| 12 | Detalle consolidado Schwab vs cálculo · ROC (`app.py:4207`) | | |
| 13 | Explicación visual del ROC — infografía (`app.py:4519`) | | |
| 14 | Las 3 cuadrículas · inversión, dividendos y ROC (`app.py:4618`) | | |
| 15 | Detalle por portafolio (`app.py:4902`) | | |
| 16 | Resumen consolidado — fondos de dividendos (`app.py:5171`) | | |
| 17 | Proyección a futuro y escenarios (`app.py:5244`) | | |
| 18 | Proyección a futuro (escenario) — expander (`app.py:5299`) | | |
| 19 | El yield anunciado vs lo que de verdad ganas (`app.py:5658`) | | |
| 20 | Comparativa de estrategias (`app.py:5666`) | | |
| 21 | Total Return Graph — YieldMax vs Crecimiento (`app.py:5922`) | | |

## Pie y utilidades

| # | Función en `app.py` | Ubicación en `app_v2.py` / `ui/` | Comprobación |
|---|---|---|---|
| 22 | Calidad de datos y validación cruzada de ingresos (`app.py:6074`) | | |
| 23 | Notas técnicas y eventos corporativos (`app.py:6094`) | | |
| 24 | Tickers excluidos del análisis (`app.py:6289`) | | |
| 25 | Calculadoras de referencia (`app.py:6301`) | | |
| 26 | Disclaimer y pie legal | | |

## Modo alterno

| # | Función en `app.py` | Ubicación en `app_v2.py` / `ui/` | Comprobación |
|---|---|---|---|
| 27 | Simulación Teórica — modo completo (`app.py:6115`) | | |
| 28 | Evolución de Patrimonio (`app.py:6156`) | | |
| 29 | Evolución por mezcla de asignación (`app.py:6262`) | | |

## Comportamiento transversal

| # | Función en `app.py` | Ubicación en `app_v2.py` / `ui/` | Comprobación |
|---|---|---|---|
| 30 | Modo demo `?demo=ib\|schwab\|schwab2` (`app.py:68-80`) | | |
| 31 | `?clear` — limpia caché (`app.py:61`) | | |
| 32 | Flag `SHOW_ROC_INFOGRAPHIC` (`app.py:59`) | | |
| 33 | Toasts de progreso entre bloques (`app.py:1345`) | | |
| 34 | Animación de revelación progresiva (`app.py:1300-1320`) | | |
| 35 | Interpretación educativa por ticker (`build_interpretation`) | | |
| 36 | Exposición al subyacente (`build_underlying_exposure`) | | |
| 37 | Generación de reporte PDF (`report.py`) | | |

---

## Cómo se audita

1. Ninguna celda vacía en las 37 filas.
2. Cada ubicación se abre y contiene efectivamente la función.
3. Cada comprobación nombra el fixture usado (`schwab_synth_1` o `ib_synth_1`) y qué se
   observó — no «revisado» ni «funciona».
4. Se recorre a mano una muestra aleatoria de 5 filas para confirmar que la tabla no miente.
