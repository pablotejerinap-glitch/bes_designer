"""Thin HTTP client so the Streamlit app consumes the FastAPI backend.

Design results are reconstructed into domain ``DesignResult`` objects so the
existing views (which access attributes like ``dr.pump_model``) keep working
unchanged. This makes Streamlit a real API client — the backend must be running
(``uvicorn api.main:app``); the base URL is configurable via ``BES_API_URL``.
"""
from __future__ import annotations

import os
from dataclasses import asdict

import httpx

from bes.core.models import (
    DesignObjectives, DesignResult, Fluid, Reservoir, SurfaceConditions, WellGeometry,
)

BASE_URL = os.environ.get("BES_API_URL", "http://localhost:8000").rstrip("/")
_TIMEOUT = 120.0


class ApiError(Exception):
    """Backend returned an error or was unreachable."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _reservoir_dict(r: Reservoir) -> dict:
    d = asdict(r)
    d["ipr_method"] = r.ipr_method.name.lower()
    d["drive_mechanism"] = r.drive_mechanism.name.lower()
    return d


def _payload(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    n: int = 3,
) -> dict:
    return {
        "reservoir":  _reservoir_dict(reservoir),
        "fluid":      asdict(fluid),
        "well":       asdict(well),
        "surface":    asdict(surface),
        "objectives": asdict(objectives),
        "n":          n,
    }


def _post(path: str, payload: dict) -> httpx.Response:
    try:
        resp = httpx.post(f"{BASE_URL}{path}", json=payload, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise ApiError(
            f"No se pudo conectar al backend en {BASE_URL}. "
            f"¿Está corriendo `uvicorn api.main:app`? ({exc})"
        ) from exc
    if resp.status_code != 200:
        detail = ""
        try:
            detail = resp.json().get("detail", "")
        except Exception:
            detail = resp.text
        raise ApiError(str(detail) or f"HTTP {resp.status_code}", status_code=resp.status_code)
    return resp


def design(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    n: int = 3,
) -> dict:
    """Call POST /api/design and reconstruct the domain-shaped result dict.

    The returned dict matches ``generate_recommendations``' shape, with each
    ``recommendation["design"]`` rebuilt as a ``DesignResult`` so the views are
    untouched.
    """
    data = _post("/api/design", _payload(reservoir, fluid, well, surface, objectives, n)).json()
    for rec in data["recommendations"]:
        rec["design"] = DesignResult(**rec["design"])
    return data


def report(
    fmt: str,
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    rank: int = 0,
) -> bytes:
    """Call POST /api/reports/{fmt} and return the file bytes (pdf | xlsx)."""
    payload = _payload(reservoir, fluid, well, surface, objectives)
    payload["rank"] = rank
    return _post(f"/api/reports/{fmt}", payload).content
