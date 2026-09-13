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

## Acceso desde el sitio web

Esta app **no se embebe** en un iframe: se enlaza en pestaña nueva a
`https://dividend-analyzer-y32sicu2utt6xgcy3fhrvp.streamlit.app/`. El login (`st.login`) no
funciona dentro de un iframe y la subida de archivos requiere XSRF activo, que no funciona
dentro de un iframe de otro sitio.

## Puerta de acceso (Fase 2)

> El iframe de `invierteygana.net/calculadora/` se retiró el 2026-09-13 (la ruta redirige con
> 301 a la página de ventas). `[auth]` ya puede ir a los secrets de producción **cuando Daniel
> lo decida** — con `[auth]` presente, Streamlit enciende XSRF (`is_xsrf_enabled`, ver
> `streamlit/web/server/server_util.py:89-94`), y ya no hay iframe que lo rompa.

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
