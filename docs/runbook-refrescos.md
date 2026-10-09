# Runbook — avisos de Telegram de los refrescos automáticos

Los dos workflows de refresco (`refresh-roc-19a.yml`, sábados 12:17 UTC, y
`refresh-price-cache.yml`, sábados 12:47 UTC) commitean **directo a `main`, sin PR**
(deliberado, #95/#117), y Streamlit Cloud despliega solo. Cuando algo sale mal, lo único que
se entera es Telegram. Este es qué hacer con cada aviso.

Por qué existe: el 2026-09-26 el parser de YieldMax devolvió 0 filas en 13 tickers (run
`36255272004`). El workflow conservó el dato previo —degradación segura— y el 2026-10-03 la
página volvió sola. Entre medias, producción sirvió ROC 19a de hace 14 días sin que nadie
decidiera nada.

## 1. «⚠️ el scraper de ROC 19a falló (¿cambió la página de YieldMax?)»

El fondo que perdió datos **conserva los anteriores**; los demás se actualizaron igual.

1. Abrir el run (enlace del aviso) → paso «Refrescar ROC 19a»: la línea
   `::error::Regresión en: …` lista los tickers afectados.
2. Abrir a mano `https://yieldmaxetfs.com/our-etfs/<ticker>/` de uno de ellos.
   - **La página cargó pero cambió el layout** → fix de `fetch_roc_19a.py` en rama + PR.
     Probar con `env -u PYTHONPATH ./.venv/bin/python fetch_roc_19a.py <TICKER>` (reescribe
     `knowledge/roc_19a.yaml` y `distribution_rate.yaml` en tu copia, fusionando con lo que
     había: revisar `git diff knowledge/` antes de commitear).
   - **La página está caída o vacía** → no hacer nada: el cron reintenta el sábado siguiente.
     Anotar la fecha del aviso para saber cuántos días de dato rancio lleva producción.
3. Cuánto lleva rancio (el `asof` es por fondo; esto muestra el primero):
   ```bash
   git fetch origin main && git show origin/main:knowledge/roc_19a.yaml | grep -m1 asof
   ```
   La app ya lo sabe: `roc_asof_days` (`ui/adapters.py`) entra en `classify_roc_health`.

## 2. «⚠️ el refresco del cache de precios falló para un ticker que ya tenía datos»

Mismo patrón: el ticker conserva su cache previo. Abrir el run → `::error::Regresion en: …`.
Si yfinance devuelve vacío para todos, suele ser transitorio (reintenta el sábado). Si falla
uno solo de forma repetida, revisar `fetch_price_cache.py` contra ese ticker.

## 3. «🔴 el refresco automático dejó la suite en rojo sobre main»

`main` ya está desplegado con el dato fresco. Casi siempre es una **expectativa hardcodeada**
que el dato movió unos centavos, no un bug (el aviso trae los `FAILED` y la deriva de oráculos).

1. Triaje: ¿el test pinea contra un dato móvil? Mirar el `asof` / `weighted_pct` de
   `knowledge/roc_19a.yaml` o la última fila de los parquets de `knowledge/price_cache/`.
2. Si la última fila de un parquet tiene `Close` nulo → es el incidente #95: no re-pinear,
   revisar `fetch_price_cache.py`.
3. Regla de merge: **el siguiente PR lleva la reconciliación antes de mergearse**. Re-pinear
   SOLO con una derivación independiente del motor, nunca copiando la salida del motor.

## 4. «📊 cambio de salud del NAV»

Un fondo cambió de veredicto (destructivo ↔ contable). Revisar el diff del commit automático
en `knowledge/roc_health_history.yaml` y decidir si es dato fresco legítimo o efecto de un
`asof` viejo (ver aviso 1).
