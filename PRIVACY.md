# Aviso de privacidad — Calculadora de Dividendos
*Actualizado: 2026-09-25*

**Tus archivos.** El archivo de transacciones, las capturas y el 1042-S se procesan en la
memoria del servidor mientras dura tu sesión. La app no los escribe a disco. El resultado del
análisis se conserva en memoria hasta 1 hora para no recalcularlo y luego se descarta. La única
excepción es la copia reducida que se describe abajo, y solo si tú la autorizas.

**Servicios externos que intervienen**

| Servicio | Qué recibe | Cuándo |
|---|---|---|
| Google Gemini | Tus capturas del bróker y la lista de tus ETFs | Solo si subes capturas en el paso 2 |
| Yahoo Finance | Los símbolos de tus ETFs y la fecha de tu primera compra, enviados desde el servidor (sin tu nombre ni tu correo) | En cada análisis |
| Auth0 | Tu correo, para enviarte el código de acceso | Al entrar |
| Backblaze B2 | La copia reducida de tu caso (ver abajo), sin tu correo | Solo si marcas la casilla del paso 2 |
| Streamlit Community Cloud | Aloja la app | Siempre |

**Tu 1042-S.** Se lee con un lector propio y el PDF no se envía a ningún servicio externo. Si
marcas la casilla del paso 2, se guardan solo los números leídos (año, país, código de renta,
bruto, retención, crédito y tasa), nunca el documento.

**Copia de tu caso para mejorar la calculadora (opcional).**

En el paso 2 hay una casilla, desmarcada, que dice «Ayúdanos a mejorar la calculadora con tu
caso». Si no la marcas, no se guarda nada y la app funciona igual.

Si la marcas, al pulsar «Ver resultados» guardamos una copia reducida de tu caso para comprobar
que la calculadora sigue acertando con casos reales. **No se usa para entrenar ningún modelo de
inteligencia artificial.**

- **Qué guardamos:** de cada movimiento, la fecha, el tipo (compra, dividendo, retención,
  depósito…), el ticker, la cantidad, el precio y el importe; las acciones y el costo que
  confirmas; lo que se leyó de tus capturas (acciones, costo, valor, precio); los números del
  1042-S; el país que declaraste; qué ETFs tuvieron avisos en el análisis; y el día (sin hora)
  en que se guardó.
- **Qué no guardamos:** el archivo original, su nombre, tus capturas, el PDF del 1042-S, tu
  nombre, tu correo, tu número de cuenta, tu número de identificación fiscal ni tu IP. La copia
  no queda asociada a tu correo.
- **Dónde:** en un almacenamiento privado y cifrado de Backblaze B2, en Estados Unidos. La app
  solo puede escribir en él; no puede leer ni listar lo que hay.
- **Quién lo ve:** solo el responsable de la calculadora, que lo revisa con sus herramientas de
  desarrollo, incluidas herramientas de inteligencia artificial, para verificar los cálculos.
  No se publica ni se comparte con terceros.
- **Cuánto tiempo:** se borra automáticamente a los 90 días. Si tu caso sirve para detectar un
  error, se conserva una copia de esa misma información reducida como caso de prueba en el
  equipo del responsable, sin fecha de borrado, hasta que pidas eliminarla.
- **Borrarlo antes:** al terminar el análisis verás un código de caso. Escríbelo a
  soporte@invierteygana.net y lo borramos, de Backblaze y de cualquier copia de prueba.
- **Una aclaración honesta:** la copia no incluye datos que te identifiquen directamente, pero
  un historial completo de movimientos es muy particular; quien tuviera tus registros del bróker
  podría reconocerlo. Por eso se guarda en privado, no se comparte y se borra a los 90 días.

## Anexo — notas técnicas del operador

Describe el mecanismo de la copia opcional del caso. No es parte del aviso que ve el cliente.

- **Consentimiento:** casilla `_consent_capture` del paso 2 (`ui/carga.py`), desmarcada por
  defecto. La captura ocurre al pulsar «Ver resultados», una sola vez por caso; editar el
  paso 2 y volver reutiliza el mismo código de caso.
- **Anonimización y empaquetado:** `logic.anonymize_to_min_rows` (whitelist de columnas) y
  `logic.build_capture_bundle` (solo números, enums y texto genérico; no recibe el nombre del
  archivo ni el correo).
- **Subida:** `storage.upload_case` → Backblaze B2, bucket privado y cifrado, ruta
  `captured/<broker>/<case_id>/`. La clave de la app es solo de escritura (`put_object`): no
  puede leer ni listar. Un fallo de almacenamiento nunca interrumpe el análisis del usuario.
- **Retención:** regla de lifecycle del bucket: 90 días ocultar + 1 día borrar
  (`ui.carga.CAPTURA_RETENCION_DIAS`).
- **Revisión y promoción (manual, solo en local):** `tools/promote_b2.sh --list | --show |
  --promote | --delete`, con la clave de lectura y borrado leída del Llavero de macOS. Un caso
  promovido pasa a `real_examples/captured/` (fuera del repositorio público); ningún dato
  entra al repositorio sin revisión.
- **Borrado a petición:** `tools/promote_b2.sh --delete <broker> <case_id>` borra **todas las
  versiones y marcadores** del caso en B2 (`storage.delete_case`); si fue promovido, borrar
  también su carpeta en `real_examples/captured/` y su entrada en `captured_cases.py`.
