---
name: dividend-analyzer-app
description: Interfaz Web para analizar portafolios de dividendos (CSV) o simular estrategias DRIP con datos de Yahoo Finance.
---

# Web App: Dividend Analyzer

Esta habilidad lanza una aplicación visual (Streamlit) para análisis financiero.

## Instrucciones para el Agente

Cuando el usuario pida "abrir el analizador de dividendos" o "lanzar la app de dividendos", ejecuta el siguiente comando:

```bash
cd "/Users/danielzambrano/Desktop/Habilidades de agentes/dividend-analyzer-app" && env -u PYTHONPATH ./.venv/bin/python -m streamlit run app.py
```

Si pytest o streamlit mueren con `No module named 'numpy._core._multiarray_umath'`, es el PYTHONPATH heredado de la sesión: `env -u PYTHONPATH` lo arregla sin tocar el venv.

## Funcionalidades
1.  **Carga de CSV**: Análisis forense de historial real.
2.  **Simulación**: Proyección teórica de TSLY/NVDY con reinversión.
