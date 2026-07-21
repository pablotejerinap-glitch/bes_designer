"""GET /api/examples — book example wells in API input shape (for form prefill)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from bes.api.schemas.inputs import (
    DesignInputs, FluidSchema, ObjectivesSchema, ReservoirSchema,
    SurfaceSchema, WellSchema,
)

_DATA_REL = Path("data") / "example_wells.json"


@lru_cache(maxsize=1)
def _data_path() -> Path:
    """Ubica ``data/example_wells.json``, que vive en la raíz del repo y no
    dentro del paquete instalable.

    Subimos por los padres hasta encontrarlo en vez de contar niveles: un
    ``parents[N]`` fijo se rompe en silencio cuando el módulo cambia de
    profundidad (que es justo lo que pasó al migrar a ``src/``).
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _DATA_REL
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"No se encontró {_DATA_REL} subiendo desde {__file__}")

router = APIRouter(prefix="/api", tags=["examples"])


class ExampleWell(BaseModel):
    key: str
    label: str
    inputs: DesignInputs


@router.get("/examples", response_model=list[ExampleWell])
def get_examples() -> list[ExampleWell]:
    """Return the Brown book examples already normalized to the API shape
    (enums lowercased)."""
    data = json.loads(_data_path().read_text(encoding="utf-8"))
    out: list[ExampleWell] = []
    for key, ex in data.items():
        if not key.startswith("example_"):
            continue
        res = dict(ex["reservoir"])
        res["ipr_method"] = res["ipr_method"].lower()
        res["drive_mechanism"] = res["drive_mechanism"].lower()
        obj = dict(ex["objectives"])
        inputs = DesignInputs(
            reservoir=ReservoirSchema(**res),
            fluid=FluidSchema(**ex["fluid"]),
            well=WellSchema(**ex["well"]),
            surface=SurfaceSchema(**ex["surface"]),
            objectives=ObjectivesSchema(**obj),
        )
        out.append(ExampleWell(key=key, label=ex.get("description", key), inputs=inputs))
    return out
