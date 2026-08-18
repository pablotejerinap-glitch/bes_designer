"""Esquemas Pydantic de pedido y respuesta de la API.

Están **separados a propósito** de las dataclasses del dominio
(``core/models.py``) — ver ``.claude/rules/api-contract.md``.

Los enums se exponen como cadenas en minúscula (``"vogel"``, ``"linear"``),
nunca como los enteros de ``auto()``.
"""
from bes.api.schemas.inputs import (
    DesignRequest,
    DriveMechanismStr,
    FluidSchema,
    IPRMethodStr,
    ObjectivesSchema,
    ReservoirSchema,
    SurfaceSchema,
    WellSchema,
)
from bes.api.schemas.outputs import (
    CriteriaSchema,
    DesignResponse,
    DesignResultSchema,
    RecommendationSchema,
)
from bes.api.schemas.catalog import (
    CatalogSummary,
    PumpSummary,
    TubularCatalog,
    TubularDim,
)

__all__ = [
    "CatalogSummary",
    "PumpSummary",
    "TubularCatalog",
    "TubularDim",
    "DesignRequest",
    "DriveMechanismStr",
    "FluidSchema",
    "IPRMethodStr",
    "ObjectivesSchema",
    "ReservoirSchema",
    "SurfaceSchema",
    "WellSchema",
    "CriteriaSchema",
    "DesignResponse",
    "DesignResultSchema",
    "RecommendationSchema",
]
