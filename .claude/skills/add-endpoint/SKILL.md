---
name: add-endpoint
description: Checklist para agregar un endpoint nuevo al backend FastAPI de BES Designer, respetando el contrato de API (esquemas Pydantic separados, enums string, errores 422). Usar al crear o modificar rutas de la API.
---

# Agregar un endpoint (FastAPI)

Leé primero `.claude/rules/api-contract.md` y `.claude/rules/architecture.md`.

## Pasos

1. **Schema** (`api/schemas/`): definir el/los modelo(s) Pydantic de
   request y response que espejan las dataclasses relevantes de `core/models.py`.
   Enums como **string** (nunca los enteros de `auto()`).
2. **Mapper** (`api/mappers.py`): mapear schema↔dataclass.
   - Request: `Reservoir(**schema.model_dump())` (+ lookup de enums string→enum).
   - Response: `Schema(**dataclasses.asdict(dr))` (+ enum→string).
3. **Servicio**: la lógica va en `services/` (o ya existe: `nodal_service`,
   `sensitivity_service`, `recommendation_engine`). **No** poner lógica en el router.
4. **Router** (`api/routers/`): endpoint delgado — valida entrada (Pydantic),
   llama al servicio, mapea la salida. `ValueError`→422 lo maneja el handler central.
5. **Gráficos**: si el endpoint devuelve un gráfico, llamá al builder de
   `ui/plots.py` y devolvé `fig.to_json()`. No reimplementar en el router.
6. **Test** (`tests/`): test de API con httpx/TestClient. Reusá los fixtures
   existentes. Si es un endpoint de cálculo, validá contra un ejemplo del libro.
7. **Correr** `pytest -q` — los 545 + los nuevos deben pasar.

## Regla
El router no contiene lógica de negocio ni formateo de dominio. Solo I/O + mapeo.
