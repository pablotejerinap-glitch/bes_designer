# Reglas de arquitectura — BES Designer

Migramos de un monolito Streamlit a una arquitectura de tres capas
(frontend React / backend FastAPI / DB SQLite). Ver el plan en
`C:\Users\maria\.claude\plans\quiet-stargazing-scott.md`.

## Capas y dependencias permitidas

```
frontend/ (React) ──HTTP/JSON──▶ bes.api (FastAPI) ──▶ bes.services ──▶ bes.core (dominio)
                                                                       bes.catalogs · bes.recommender
                                                                       bes.reports · bes.plotting
                                            bes.services ──▶ bes.db (SQLAlchemy, Semana 4)
```

## Layout del repositorio

```
backend/            todo el Python — unidad de despliegue autocontenida
  src/bes/          paquete único distribuible (pip install -e backend/)
    core/           dominio puro — sin frameworks
    catalogs/       catálogos JSON + queries (los .json viajan con el paquete)
    recommender/    scoring y selección
    reports/        PDF / Excel
    services/       orquestación agnóstica de framework
    plotting/       builders Plotly — agnósticos, los consume la API
    api/            capa de entrega HTTP (FastAPI)
  tests/ data/ scripts/
  pyproject.toml  requirements*.txt  Dockerfile
frontend/           SPA React (Vite + TS + Mantine)
docker-compose.yml · docs/ · README.md · CLAUDE.md   ← nivel proyecto
```

`frontend/` y `bes.api` son **adaptadores de entrega**: ninguno es "el
backend". El dominio vive debajo y no depende de ninguno. Por eso `core/` y
`services/` **no** viven dentro de `api/` — si lo hicieran, cualquier otra UI
(o un job batch, o un script) tendría que importar el paquete de FastAPI sólo
para poder calcular.

Hubo una tercera UI (`streamlit_app/`), retirada cuando React alcanzó paridad.
`streamlit` sigue prohibido en el dominio: ver `tests/test_architecture.py`.

**Regla de dirección de dependencias (no negociable):**

1. `bes.core` (dominio) **NUNCA** importa un framework: ni `streamlit`, ni
   `fastapi`, ni `sqlalchemy`. Solo funciones puras sobre las dataclasses de
   `bes/core/models.py`.
2. `bes.services` orquesta el dominio. Es **agnóstico de framework**: no importa
   `streamlit` ni `fastapi`. Devuelve **números crudos**, nunca strings
   formateados ni objetos de UI. Para progreso usa un callback, no la UI.
3. `bes.api` y la UI (React) **dependen** de `bes.services`,
   nunca al revés. La UI solo formatea y renderiza.
4. `bes.plotting` construye figuras Plotly y **no importa streamlit** — es
   reusable por la API (`fig.to_json()`). Mantenerlo así: es la razón por la
   que vive en el paquete y no en la carpeta de la UI.

## Fuente única de verdad

- La lógica de negocio vive en `bes.core` (cálculo) o `bes.services`
  (orquestación), **nunca inline en una vista**. Si aparece lógica en
  la UI, extraerla.
- Toda UI llama a la **misma** capa de servicios vía la API → no duplicar lógica.

## Packaging

- El proyecto es un paquete instalable con layout `src/` (`pyproject.toml`,
  `pip install -e .`). El único paquete distribuible es `bes`.
- **Prohibido** `sys.path.insert`. Los imports son absolutos
  (`from bes.core.models import ...`).
- Los datos del paquete (catálogos JSON) se resuelven con
  `Path(__file__).parent`, nunca desde la raíz del repo ni desde el CWD:
  `CatalogManager()` **sin argumento** ya los encuentra.

## Contrato de datos

- `core/models.py` (dataclasses) es el vocabulario compartido. `DesignResult` es
  `dataclasses.asdict`-serializable → contrato natural para JSON/API.
- La capa API usa **esquemas Pydantic separados** + mappers; NO se convierten las
  dataclasses del dominio (protege los 545 tests y la validación `__post_init__`).
  Detalle en `api-contract.md`.
