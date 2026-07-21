"""Case-bundle serializer.

Bundles a complete design case (inputs + result) into a plain dict / JSON bytes.
Extracted from the "Guardar Caso JSON" download in ``app.py`` so the same
format can back the future save/open feature and the SQLite ``designs`` table.
"""
from __future__ import annotations

import json
from dataclasses import asdict

from bes.core.models import (
    DesignObjectives, DesignResult, Fluid, Reservoir, SurfaceConditions, WellGeometry,
)


def build_case_bundle(
    design_result: DesignResult,
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    *,
    generated: str | None = None,
) -> dict:
    """Assemble a serializable dict holding the full design case.

    Args:
        design_result: The chosen DesignResult.
        reservoir, fluid, well, surface, objectives: The five input models.
        generated: Optional generation timestamp/date string for provenance.

    Returns:
        A plain dict (dataclasses expanded via ``asdict``). Enums remain as enum
        objects here; use ``case_bundle_json`` (``default=str``) to serialize.
    """
    return {
        "generated":     generated,
        "design_result": asdict(design_result),
        "reservoir":     asdict(reservoir),
        "fluid":         asdict(fluid),
        "well":          asdict(well),
        "surface":       asdict(surface),
        "objectives":    asdict(objectives),
    }


def case_bundle_json(
    design_result: DesignResult,
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    *,
    generated: str | None = None,
    indent: int = 2,
) -> bytes:
    """Serialize a case bundle to pretty-printed UTF-8 JSON bytes.

    ``default=str`` stringifies non-JSON-native values (e.g. enum members),
    matching the original download behavior.
    """
    bundle = build_case_bundle(
        design_result, reservoir, fluid, well, surface, objectives, generated=generated,
    )
    return json.dumps(bundle, default=str, indent=indent).encode("utf-8")
