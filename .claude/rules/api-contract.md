# Reglas del contrato de API (FastAPI + Pydantic) — Semana 2+

## Esquemas: separados, no convertir el dominio

- Se **mantienen** las dataclasses de `bes/core/models.py`. Se crean **esquemas
  Pydantic separados** (`bes/api/schemas/`) que las espejan, más mappers
  (`bes/api/mappers.py`).
- **NO** convertir las dataclasses a Pydantic: rompería los 545 tests (que
  esperan `ValueError` con mensajes específicos) y el `warnings.warn` "soft" de
  `Reservoir` (bubble_point > static_pressure es válido en reservorios depletados).
- Los nombres de campo ya coinciden → mapeo trivial:
  - Response: `DesignResultSchema(**dataclasses.asdict(dr))`
  - Request:  `Reservoir(**schema.model_dump())`

## Enums

- `IPRMethod` y `DriveMechanism` usan `auto()` (valores **enteros**). **Nunca**
  exponer los enteros por la API.
- La API habla enums **string** (`"vogel"`, `"linear"`, `"solution_gas"`, ...).
  El mapper hace el lookup explícito string↔enum. Testear ida y vuelta.

## Contrato de errores (central, en `bes/api/main.py`)

- `ValueError` del dominio (diseño inviable / validación) → **HTTP 422** con el
  mensaje del error.
- Capturar `UserWarning` y devolverlo en la respuesta (reusar el patrón del campo
  `DesignResult.warnings`, que ya existe).
- Configurar **CORS** para la SPA.

## Gráficos

- Los endpoints devuelven los gráficos como **Plotly figure JSON** llamando a los
  builders de `bes.plotting` (`fig.to_json()`). El front los renderiza con
  `react-plotly.js`. No reimplementar gráficos en JS.

## Endpoints previstos

`POST /api/design` · `GET /api/catalogs` · `POST /api/nodal` ·
`POST /api/reports/{pdf,xlsx}` ·
`POST/GET/GET{id} /api/designs` (SQLite, Semana 4).
