---
title: Dividend Analyzer
emoji: 📈
colorFrom: green
colorTo: blue
sdk: docker
pinned: false
---

# Dividend Analyzer App

Esta aplicación te permite analizar tu portafolio de dividendos (forense) o simular estrategias de inversión (DRIP vs No-DRIP).

## Requisitos

Asegúrate de tener instaladas las dependencias:

```bash
python3 -m pip install -r requirements.txt
```

## Cómo ejecutar la aplicación

Para iniciar la aplicación, abre una terminal en esta carpeta y ejecuta:

```bash
python3 -m streamlit run app.py
```

O si estás en otra carpeta, usa la ruta completa:

```bash
cd "/Users/danielzambrano/Desktop/Habilidades de agentes/dividend-analyzer-app" && python3 -m streamlit run app.py
```

## Integración en Sitio Web

Para embeber esta aplicación en tu sitio web, usa el siguiente código.

**Nota importante**: Se ha incluido el parámetro `?embed=true` en la URL para ocultar la barra de herramientas de Streamlit y mejorar la visualización.

```html
<!-- Dividend Analyzer App Embed -->
<iframe
  src="https://dividend-analyzer-y32sicu2utt6xgcy3fhrvp.streamlit.app/?embed=true"
  height="1000"
  style="width:100%;border:none;border-radius:10px;box-shadow:0 4px 6px rgba(0,0,0,0.1);"
  title="Dividend Analyzer"
></iframe>
```

## Puerta de acceso (Fase 2)

> **⚠️ No añadir `[auth]` a los secrets de producción hasta retirar el iframe (Fase 3).**
> Con `[auth]` presente, Streamlit enciende XSRF (`is_xsrf_enabled`, ver
> `streamlit/web/server/server_util.py:89-94`) y con XSRF la subida de archivos se rompe
> dentro del iframe de `invierteygana.net/calculadora/`, que sigue vivo hasta la Fase 3.
> El modo `apagado` no evita esto: el disparador es la sola presencia de `[auth]`, no el
> modo configurado.

Secrets necesarios (`.streamlit/secrets.toml`), con valores vacíos:

```toml
[auth]
redirect_uri = "http://localhost:8765/oauth2callback"
cookie_secret = "..."

[auth.auth0]
client_id = "..."
client_secret = "..."
server_metadata_url = "https://invierteygana.us.auth0.com/.well-known/openid-configuration"

[acceso]
modo = "observar"          # aplicar | observar | apagado
allowlist_pat = "..."
hmac_key = "..."
telegram_token = "..."
telegram_chat_id = "..."
```

Sin la sección `[auth]`, la puerta queda en modo `apagado` (la app funciona como hoy, sin
login). El login se lanza con `st.login("auth0")`.

### Probar el login real en local

En la red de Daniel, IPv6 hacia Auth0 no responde y `requests` lo intenta primero: el login
se cuelga sin timeout y parece roto. Usa `tools/run_ipv4.py` (fuerza IPv4, solo local, no es
código de producción):

```bash
.venv/bin/python tools/run_ipv4.py
```
