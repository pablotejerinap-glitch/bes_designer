"""Request schemas — mirror the five input dataclasses in ``core/models.py``.

Field names match the dataclasses 1:1 so mapping is trivial. Enums are exposed
as lowercase strings (never the ``auto()`` integers). Validation of physical
ranges is left to the domain ``__post_init__`` (surfaced as HTTP 422); here we
only enforce types and JSON shape, plus a few obviously-cheap bounds that give
nicer OpenAPI docs.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class IPRMethodStr(str, Enum):
    linear = "linear"
    vogel = "vogel"
    fetkovich = "fetkovich"
    combined = "combined"


class DriveMechanismStr(str, Enum):
    solution_gas = "solution_gas"
    water_drive = "water_drive"
    gas_cap = "gas_cap"
    combination = "combination"


class ReservoirSchema(BaseModel):
    static_pressure: float = Field(..., gt=0, description="Presión estática [psia]")
    bubble_point: float = Field(..., ge=0, description="Presión de burbuja [psia]")
    productivity_index: float = Field(..., gt=0, description="PI [STB/d/psi]")
    ipr_method: IPRMethodStr
    reservoir_temp: float = Field(..., gt=0, description="Temp. de reservorio [°F]")
    drive_mechanism: DriveMechanismStr
    datum_depth: float = Field(..., gt=0, description="Profundidad de referencia [ft TVD]")


class FluidSchema(BaseModel):
    oil_api: float = Field(..., ge=5, le=70, description="Gravedad API [°API]")
    water_cut: float = Field(..., ge=0, le=1, description="Corte de agua [0-1]")
    gor: float = Field(..., ge=0, description="GOR [scf/STB]")
    gas_sg: float = Field(..., gt=0, description="SG del gas (aire=1)")
    water_sg: float = Field(..., gt=0, description="SG de la salmuera")
    oil_viscosity_dead: float = Field(..., gt=0, description="Viscosidad dead-oil [cp]")
    viscosity_temp_ref: float = Field(..., gt=0, description="Temp. de referencia de viscosidad [°F]")
    bubble_point_pressure: float = Field(..., ge=0, description="Pb del fluido [psia]")
    h2s_content: float = Field(..., ge=0, description="H2S [ppm]")
    co2_content: float = Field(..., ge=0, description="CO2 [ppm]")
    sand_production: bool


class WellSchema(BaseModel):
    total_depth: float = Field(..., gt=0, description="Profundidad total [ft MD]")
    casing_od: float = Field(..., gt=0, description="OD del casing [in]")
    casing_weight: float = Field(..., gt=0, description="Peso del casing [lb/ft]")
    casing_id: float = Field(..., gt=0, description="ID del casing [in]")
    tubing_od: float = Field(..., gt=0, description="OD del tubing [in]")
    tubing_id: float = Field(..., gt=0, description="ID del tubing [in]")
    perforations_top: float = Field(..., gt=0, description="Tope de perforaciones [ft MD]")
    perforations_bottom: float = Field(..., gt=0, description="Base de perforaciones [ft MD]")
    deviation_max: float = Field(..., ge=0, le=90, description="Desviación máxima [°]")
    wellhead_temp: float = Field(..., gt=0, description="Temp. en boca de pozo [°F]")
    bottom_hole_temp: float = Field(..., gt=0, description="Temp. de fondo [°F]")


class SurfaceSchema(BaseModel):
    wellhead_pressure_required: float = Field(..., ge=0, description="Presión requerida en cabeza [psi]")
    flowline_length: float = Field(..., ge=0, description="Longitud de flowline [ft]")
    flowline_id: float = Field(..., gt=0, description="ID del flowline [in]")
    flowline_elevation_change: float = Field(..., description="Cambio de elevación [ft]")
    separator_pressure: float = Field(..., ge=0, description="Presión del separador [psi]")
    power_supply_voltage: float = Field(..., gt=0, description="Voltaje de superficie [V]")
    frequency: float = Field(..., description="Frecuencia de red [Hz] (50 o 60)")


class ObjectivesSchema(BaseModel):
    target_flow_rate: float = Field(..., gt=0, description="Caudal objetivo [STB/d]")
    safety_margin_depth: float = Field(..., ge=0, description="Margen de profundidad [ft]")
    allow_gas_venting: bool
    max_gip: float = Field(..., ge=0, le=1, description="Fracción máxima de gas en bomba [0-1]")
    design_life_years: float = Field(..., gt=0, description="Vida de diseño [años]")
    use_vsd: bool
    preferred_manufacturer: str = Field("", description="Fabricante preferido (vacío = sin preferencia)")


class DesignRequest(BaseModel):
    """Full input bundle for a design run."""
    reservoir: ReservoirSchema
    fluid: FluidSchema
    well: WellSchema
    surface: SurfaceSchema
    objectives: ObjectivesSchema
    n: int = Field(3, ge=1, le=10, description="Número de recomendaciones a devolver")
