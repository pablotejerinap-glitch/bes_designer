---
name: run
description: Levantar la app BES Designer localmente (Streamlit hoy; backend FastAPI + frontend React a medida que avanza la migración). Usar cuando el usuario pida correr, arrancar o probar la app.
---

# Correr BES Designer

El proyecto usa un venv en `.venv` con Python 3.14. El intérprete es
`.venv\Scripts\python.exe`. El proyecto está instalado en editable (`pip install -e .`),
así que los imports funcionan desde cualquier CWD, sin `sys.path`.

## Setup (una vez)

```powershell
# Crear venv (si no existe) e instalar dependencias
& "C:\Users\maria\AppData\Local\Python\bin\python.exe" -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\.venv\Scripts\python.exe" -m pip install -e .
```

## Backend FastAPI (requerido por Streamlit desde Semana 2)

```powershell
& ".\.venv\Scripts\python.exe" -m uvicorn bes.api.main:app --reload --port 8000
```
Docs OpenAPI en http://localhost:8000/docs. Salud: `Invoke-WebRequest http://localhost:8000/api/health`.

## Streamlit (respaldo, consume la API)

**Requiere el backend corriendo** (Streamlit repunta `/api/design` y las descargas
PDF/Excel por HTTP vía `streamlit_app/api_client.py`). Levantá primero uvicorn, después:

```powershell
& ".\.venv\Scripts\python.exe" -m streamlit run streamlit_app/app.py --server.headless true --server.port 8501
```
Abre en http://localhost:8501. Salud: `Invoke-WebRequest http://localhost:8501/healthz`.
URL del backend configurable con `$env:BES_API_URL` (default http://localhost:8000).
Las secciones Nodal y Sensibilidad siguen calculando in-process (no requieren la API).

## Tests (correr SIEMPRE antes de dar por terminado un cambio)

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q
```
Deben pasar los 562 tests (545 dominio + 17 API). Ver `.claude/rules/domain.md`.

## Frontend React (Semana 3+)

```powershell
cd frontend; npm install; npm run dev
```

## Todo junto (Docker)

```powershell
docker compose up --build
```
frontend http://localhost:8080 · api http://localhost:8000 · streamlit http://localhost:8501

## Notas
- En PowerShell, para pasar scripts multilínea a Python, escribí el script a un
  archivo y ejecutalo — pasar código con comillas por `python -c` rompe el quoting.
- No uses `python`/`pip` pelados: no están en PATH. Usá siempre la ruta del venv.
