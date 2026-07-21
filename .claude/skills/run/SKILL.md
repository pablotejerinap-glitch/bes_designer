---
name: run
description: Levantar la app BES Designer localmente (backend FastAPI + frontend React). Usar cuando el usuario pida correr, arrancar o probar la app.
---

# Correr BES Designer

El proyecto usa un venv en `.venv` con Python 3.14. El intérprete es
`.venv\Scripts\python.exe`. El paquete está instalado en editable
(`pip install -e backend`), así que los imports funcionan desde cualquier CWD,
sin `sys.path`. El venv vive en la raíz; los comandos de Python se corren
desde `backend/`, que es donde están `pyproject.toml` y `tests/`.

## Setup (una vez)

```powershell
# Crear venv (si no existe) e instalar dependencias
& "C:\Users\maria\AppData\Local\Python\bin\python.exe" -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
& ".\.venv\Scripts\python.exe" -m pip install -e backend
```

## Backend FastAPI (requerido por el frontend)

```powershell
cd backend; & "..\.venv\Scripts\python.exe" -m uvicorn bes.api.main:app --reload --port 8000
```
Docs OpenAPI en http://localhost:8000/docs. Salud: `Invoke-WebRequest http://localhost:8000/api/health`.

## Tests (correr SIEMPRE antes de dar por terminado un cambio)

```powershell
cd backend; & "..\.venv\Scripts\python.exe" -m pytest -q
```
Deben pasar los 584 tests (545 dominio + 17 API + 15 arquitectura + 7 scripts). Ver `.claude/rules/domain.md`.

## Frontend React (Semana 3+)

```powershell
cd frontend; npm install; npm run dev
```

## Todo junto (Docker)

```powershell
docker compose up --build
```
frontend http://localhost:8080 · api http://localhost:8000

## Notas
- En PowerShell, para pasar scripts multilínea a Python, escribí el script a un
  archivo y ejecutalo — pasar código con comillas por `python -c` rompe el quoting.
- No uses `python`/`pip` pelados: no están en PATH. Usá siempre la ruta del venv.
