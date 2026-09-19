# Aviso de privacidad — Calculadora de Dividendos
*Actualizado: 2026-09-18*

**Tus archivos.** El archivo de transacciones, las capturas y el 1042-S se procesan en la
memoria del servidor mientras dura tu sesión. La app no los escribe a disco ni los guarda en
ninguna base de datos. El resultado del análisis se conserva en memoria hasta 1 hora para no
recalcularlo y luego se descarta.

**Servicios externos que intervienen**

| Servicio | Qué recibe | Cuándo |
|---|---|---|
| Google Gemini | Tus capturas del bróker y la lista de tus ETFs | Solo si subes capturas en el paso 2 |
| Yahoo Finance | Los símbolos de tus ETFs y la fecha de tu primera compra, enviados desde el servidor (sin tu nombre ni tu correo) | En cada análisis |
| Auth0 | Tu correo, para enviarte el código de acceso | Al entrar |
| Telegram (aviso interno al administrador) | Tu correo, si no figura en la lista de miembros | Mientras la verificación de acceso esté en modo de prueba |
| Streamlit Community Cloud | Aloja la app | Siempre |

**Tu 1042-S no sale del servidor:** se lee con un lector propio y no se envía a ningún servicio externo.

**Captura de casos de estudio:** desactivada desde 2026-08-09. Si se reactiva, este aviso se
actualizará antes y pedirá tu consentimiento explícito.

## Anexo — notas técnicas del operador (inactivo)

Esta sección describe el mecanismo de captura de casos de estudio, **desactivado desde
2026-08-09** (ver arriba). Se conserva como referencia técnica, no como descripción del
comportamiento actual de la app.

- La anonimización ocurriría en `logic.anonymize_to_min_rows` (whitelist de columnas) y el
  empaquetado en `logic.build_capture_bundle` (solo números/enums/texto genérico).
- La subida ocurriría en `storage.upload_case`; un fallo de almacenamiento nunca interrumpiría
  el análisis del usuario.
- La promoción al set de regresión sería **manual** (`promote_case.py`): ningún dato entraría al
  repositorio sin revisión.
- Borrado por caso (si se reactivara): `python promote_case.py --delete <broker> <case_id>`.
