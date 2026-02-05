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
