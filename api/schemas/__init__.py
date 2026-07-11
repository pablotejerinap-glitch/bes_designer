"""Pydantic request/response schemas for the API.

Separate from the domain dataclasses (`core/models.py`) on purpose — see
`.claude/rules/api-contract.md`. Enums are exposed as lowercase strings.
"""
from api.schemas.inputs import (
    DesignRequest,
    DriveMechanismStr,
    FluidSchema,
    IPRMethodStr,
    ObjectivesSchema,
    ReservoirSchema,
    SurfaceSchema,
    WellSchema,
)
from api.schemas.outputs import (
    DesignResponse,
    DesignResultSchema,
    RecommendationSchema,
)
from api.schemas.catalog import CatalogSummary, PumpSummary

__all__ = [
    "CatalogSummary",
    "PumpSummary",
    "DesignRequest",
    "DriveMechanismStr",
    "FluidSchema",
    "IPRMethodStr",
    "ObjectivesSchema",
    "ReservoirSchema",
    "SurfaceSchema",
    "WellSchema",
    "DesignResponse",
    "DesignResultSchema",
    "RecommendationSchema",
]
