"""Catalog summary schema for ``GET /api/catalogs`` — light overview for the
frontend (pump list, manufacturers for the preferred-manufacturer dropdown,
and item counts). Full performance curves are not exposed here.
"""
from __future__ import annotations

from pydantic import BaseModel


class PumpSummary(BaseModel):
    manufacturer: str
    series: str
    model: str
    od: float
    min_flow: float
    max_flow: float
    bep_flow: float


class CatalogSummary(BaseModel):
    pumps: list[PumpSummary]
    manufacturers: list[str]
    counts: dict[str, int]


class TubularDim(BaseModel):
    """Una fila de la tabla dimensional Tenaris (API 5CT): un OD + peso nominal
    con su ID y drift resueltos."""
    od_in: float
    od_label: str
    od_mm: float | None = None
    weight_lbft: float
    wall_in: float | None = None
    id_in: float
    drift_in: float | None = None


class TubularCatalog(BaseModel):
    """Tablas dimensionales de casing y tubing para ``GET /api/catalogs/tubulars``.

    El frontend arma con esto los desplegables OD -> peso y autocompleta el ID
    (y el drift) que el usuario casi nunca tiene a mano.
    """
    casing: list[TubularDim]
    tubing: list[TubularDim]
