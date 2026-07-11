# Reglas de arquitectura — BES Designer

Estamos migrando de un monolito Streamlit a una arquitectura de tres capas
(frontend React / backend FastAPI / DB SQLite). Ver el plan en
`C:\Users\maria\.claude\plans\quiet-stargazing-scott.md`.

## Capas y dependencias permitidas

```
frontend (React)  ──HTTP/JSON──▶  backend (FastAPI)  ──▶  services/  ──▶  core/ (dominio)
streamlit_app     ──HTTP/JSON──▶  backend                              catalogs/ · recommender/ · reports/
                                                          services/ ──▶  db/ (SQLAlchemy, Semana 4)
```

**Regla de dirección de dependencias (no negociable):**

1. `core/` (dominio) **NUNCA** importa un framework: ni `streamlit`, ni `fastapi`,
   ni `sqlalchemy`. Solo funciones puras sobre las dataclasses de `core/models.py`.
2. `services/` orquesta el dominio. Es **agnóstico de framework**: no importa
   `streamlit` ni `fastapi`. Devuelve **números crudos**, nunca strings
   formateados ni objetos de UI. Para progreso usa un callback, no la UI.
3. El backend (FastAPI) y las vistas (Streamlit/React) **dependen** de `services/`,
   nunca al revés. La UI solo formatea y renderiza.
4. `ui/plots.py` construye figuras Plotly y **no importa streamlit** — es reusable
   por la API (`fig.to_json()`). Mantenerlo así.

## Fuente única de verdad

- La lógica de negocio vive en `core/` (cálculo) o `services/` (orquestación),
  **nunca inline en una vista**. Si aparece lógica en `app.py`/`ui/`, extraerla.
- Streamlit y React llaman a la **misma** capa de servicios → no duplicar lógica.

## Packaging

- El proyecto es un paquete instalable (`pyproject.toml`, `pip install -e .`).
- **Prohibido** `sys.path.insert`. Los imports son absolutos (`from core.models import ...`).

## Contrato de datos

- `core/models.py` (dataclasses) es el vocabulario compartido. `DesignResult` es
  `dataclasses.asdict`-serializable → contrato natural para JSON/API.
- La capa API usa **esquemas Pydantic separados** + mappers; NO se convierten las
  dataclasses del dominio (protege los 545 tests y la validación `__post_init__`).
  Detalle en `api-contract.md`.
