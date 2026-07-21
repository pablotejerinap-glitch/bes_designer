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
