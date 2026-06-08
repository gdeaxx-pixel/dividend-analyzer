# Aviso de privacidad — captura de casos de estudio

La calculadora puede guardar, **solo si das tu consentimiento explícito** (casilla
desmarcada por defecto), una versión **anónima** de tu análisis para mejorar la
precisión de la herramienta. Si no marcas la casilla, no se guarda absolutamente nada:
todo el procesamiento ocurre en memoria y se descarta al cerrar la sesión.

## Qué se guarda (cuando consientes)
- Fechas, tickers, cantidades y montos de tus transacciones (las columnas que el
  análisis necesita: `Date, Action, Ticker, Quantity, Price, Amount`).
- Las posiciones que tú confirmaste (acciones y costo por ticker).
- Indicadores de calidad de datos calculados por la app (p. ej. "historial completo").

## Qué NUNCA se guarda
- **Tu nombre, número de cuenta, dirección o cualquier dato de identidad.** Se eliminan
  por construcción: solo se conservan las columnas de transacción anteriores; cualquier
  otra columna del archivo del broker se descarta antes de guardar.
- **Las fotos/capturas de tu portafolio.** Se usan en memoria para leer los valores y se
  descartan; jamás se almacenan.
- Tu dirección IP, ubicación geográfica, correo ni identificador de sesión.

## Cómo se guarda
- En almacenamiento privado y cifrado, con acceso restringido.
- Cada caso recibe un identificador aleatorio (`case_id`) sin relación con tu identidad.
- Retención limitada (por defecto 90 días en el almacén de captura).

## Tus derechos
- Puedes pedir el **borrado** de tu caso en cualquier momento indicando tu `case_id`.
- Como los datos guardados son anónimos (sin elementos que te identifiquen), no es
  posible vincularlos de vuelta a tu persona una vez almacenados.

## Para el operador (notas técnicas)
- La anonimización ocurre en `logic.anonymize_to_min_rows` (whitelist de columnas) y el
  empaquetado en `logic.build_capture_bundle` (solo números/enums/texto genérico).
- La subida ocurre en `storage.upload_case`; un fallo de almacenamiento nunca interrumpe
  el análisis del usuario.
- La promoción al set de regresión es **manual** (`promote_case.py`): ningún dato entra al
  repositorio sin tu revisión.
- Borrado por caso: `python promote_case.py --delete <broker> <case_id>`.
