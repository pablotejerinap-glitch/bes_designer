# Reglas de arquitectura — BES Designer

Estamos migrando de un monolito Streamlit a una arquitectura de tres capas
(frontend React / backend FastAPI / DB SQLite). Ver el plan en
`C:\Users\maria\.claude\plans\quiet-stargazing-scott.md`.

## Capas y dependencias permitidas

```
frontend/        ──HTTP/JSON──▶  bes.api (FastAPI) ──▶ bes.services ──▶ bes.core (dominio)
streamlit_app/   ──HTTP/JSON──▶  bes.api                              bes.catalogs · bes.recommender
                                                                      bes.reports · bes.plotting
                                            bes.services ──▶ bes.db (SQLAlchemy, Semana 4)
```

## Layout del repositorio

```
src/bes/            paquete único distribuible (pip install -e .)
  core/             dominio puro — sin frameworks
  catalogs/         catálogos JSON + queries (los .json viajan con el paquete)
  recommender/      scoring y selección
  reports/          PDF / Excel
  services/         orquestación agnóstica de framework
  plotting/         builders Plotly — agnósticos, los consume la API
  api/              capa de entrega HTTP (FastAPI)
streamlit_app/      app Streamlit (red de seguridad) — NO es parte del paquete
frontend/           SPA React
tests/ data/ docs/ scripts/
```

`streamlit_app/` y `frontend/` son **adaptadores de entrega**, igual que
`bes.api`. Ninguno de los tres es "el backend": el dominio vive debajo de los
tres y no depende de ninguno. Por eso `core/` y `services/` **no** viven dentro
de `api/` — si lo hicieran, Streamlit tendría que importar del paquete de
FastAPI para poder calcular.

Los módulos de `streamlit_app/` se importan entre sí como hermanos
(`from forms import ...`) porque `streamlit run` pone el directorio del script
en `sys.path[0]`. No es un `sys.path.insert`: sigue siendo import absoluto.

**Regla de dirección de dependencias (no negociable):**

1. `bes.core` (dominio) **NUNCA** importa un framework: ni `streamlit`, ni
   `fastapi`, ni `sqlalchemy`. Solo funciones puras sobre las dataclasses de
   `bes/core/models.py`.
2. `bes.services` orquesta el dominio. Es **agnóstico de framework**: no importa
   `streamlit` ni `fastapi`. Devuelve **números crudos**, nunca strings
   formateados ni objetos de UI. Para progreso usa un callback, no la UI.
3. `bes.api` y las vistas (Streamlit/React) **dependen** de `bes.services`,
   nunca al revés. La UI solo formatea y renderiza.
4. `bes.plotting` construye figuras Plotly y **no importa streamlit** — es
   reusable por la API (`fig.to_json()`). Mantenerlo así: es la razón por la
   que vive en el paquete y no en `streamlit_app/`.

## Fuente única de verdad

- La lógica de negocio vive en `bes.core` (cálculo) o `bes.services`
  (orquestación), **nunca inline en una vista**. Si aparece lógica en
  `streamlit_app/`, extraerla.
- Streamlit y React llaman a la **misma** capa de servicios → no duplicar lógica.

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
