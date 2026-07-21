"""Schemas for the nodal and sensitivity analysis endpoints."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from bes.api.schemas.inputs import (
    FluidSchema, ObjectivesSchema, ReservoirSchema, SurfaceSchema, WellSchema,
)


class NodalMethodStr(str, Enum):
    hagedorn_brown = "hagedorn_brown"
    beggs_brill = "beggs_brill"
    duns_ros = "duns_ros"
    poettmann_carpenter = "poettmann_carpenter"


class SensitivityParamStr(str, Enum):
    water_cut = "water_cut"
    gor = "gor"
    static_pressure = "static_pressure"
    target_flow_rate = "target_flow_rate"


# --------------------------------------------------------------------------- #
# Nodal
# --------------------------------------------------------------------------- #
class NodalRequest(BaseModel):
    reservoir: ReservoirSchema
    fluid: FluidSchema
    well: WellSchema
    surface: SurfaceSchema
    method: NodalMethodStr = NodalMethodStr.hagedorn_brown
    pr_decline_pct: float = Field(0.0, ge=0, le=90, description="Declinación de Pr [%]")
    compare_all: bool = False
    # Contexto de bomba (opcional; normalmente del top design).
    pump_model: str | None = Field(None, description="Modelo de bomba para el flujo con BES")
    stages: int | None = Field(None, gt=0)
    pump_depth: float | None = Field(None, gt=0)


class NodalComparisonRow(BaseModel):
    method_key: str
    method_label: str
    q_natural: float
    q_pump: float
    incremental: float
    pwf_operating: float
    pump_efficiency: float


class NodalResponse(BaseModel):
    mode: str                          # "single" | "compare"
    method: str
    pr_decline_pct: float
    static_pressure_eff: float
    has_pump: bool
    metrics: dict[str, float] | None = None
    comparison: list[NodalComparisonRow] | None = None
    figure: dict                       # Plotly figure JSON (data + layout)


# --------------------------------------------------------------------------- #
# Sensitivity
# --------------------------------------------------------------------------- #
class SensitivityRequest(BaseModel):
    reservoir: ReservoirSchema
    fluid: FluidSchema
    well: WellSchema
    surface: SurfaceSchema
    objectives: ObjectivesSchema
    param: SensitivityParamStr
    pct_range_pct: float = Field(40.0, gt=0, le=90, description="Semiancho del barrido [%]")
    n_points: int = Field(7, ge=2, le=25)


class SensitivityResponse(BaseModel):
    param: str
    param_label: str
    param_values: list[float]
    metrics: dict[str, list[float]]
    figure: dict                       # Plotly figure JSON


# --------------------------------------------------------------------------- #
# Gráficos sueltos
# --------------------------------------------------------------------------- #
class FigureResponse(BaseModel):
    """Un gráfico solo, sin métricas. El front lo pasa tal cual a <Plot>."""
    figure: dict                       # Plotly figure JSON (data + layout)
