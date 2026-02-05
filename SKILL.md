---
name: dividend-analyzer-app
description: Interfaz Web para analizar portafolios de dividendos (CSV) o simular estrategias DRIP con datos de Yahoo Finance.
---

# Web App: Dividend Analyzer

Esta habilidad lanza una aplicación visual (Streamlit) para análisis financiero.

## Instrucciones para el Agente

Cuando el usuario pida "abrir el analizador de dividendos" o "lanzar la app de dividendos", ejecuta el siguiente comando:

```bash
cd "/Users/danielzambrano/Desktop/Habilidades de agentes/dividend-analyzer-app" && python3 -m streamlit run app.py
```

## Funcionalidades
1.  **Carga de CSV**: Análisis forense de historial real.
2.  **Simulación**: Proyección teórica de TSLY/NVDY con reinversión.
