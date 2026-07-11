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

## Streamlit (estado actual / demo de respaldo)

```powershell
& ".\.venv\Scripts\python.exe" -m streamlit run app.py --server.headless true --server.port 8501
```
Abre en http://localhost:8501. Verificar salud: `Invoke-WebRequest http://localhost:8501/healthz`.

## Tests (correr SIEMPRE antes de dar por terminado un cambio)

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q
```
Deben pasar los 545 tests. Ver `.claude/rules/domain.md`.

## Backend FastAPI (Semana 2+)

```powershell
& ".\.venv\Scripts\python.exe" -m uvicorn backend.app.main:app --reload --port 8000
```
Docs OpenAPI en http://localhost:8000/docs.

## Frontend React (Semana 3+)

```powershell
cd frontend; npm install; npm run dev
```

## Todo junto (Semana 4)

```powershell
docker compose up
```

## Notas
- En PowerShell, para pasar scripts multilínea a Python, escribí el script a un
  archivo y ejecutalo — pasar código con comillas por `python -c` rompe el quoting.
- No uses `python`/`pip` pelados: no están en PATH. Usá siempre la ruta del venv.
