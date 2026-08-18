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


class DriveMechanismStr(str, Enum):
    solution_gas = "solution_gas"
    water_drive = "water_drive"
    gas_cap = "gas_cap"
    combination = "combination"


class ReservoirSchema(BaseModel):
    """Reservorio. La entregabilidad se carga como **ensayo de producción**
    (``test_pwf`` + ``test_rate``), que es el dato que se mide en el pozo; el
    índice de productividad se deriva de ahí con el método IPR elegido."""

    static_pressure: float = Field(..., gt=0, description="Presión estática [psia]")
    bubble_point: float = Field(..., ge=0, description="Presión de burbuja [psia]")
    test_pwf: float = Field(
        ..., ge=0,
        description="Ensayo — presión de fondo fluyente medida [psia]. "
                    "Debe ser menor que la presión estática.",
    )
    test_rate: float = Field(
        ..., gt=0,
        description="Ensayo — caudal bruto de líquido medido [STB/d].",
    )
    ipr_method: IPRMethodStr
    reservoir_temp: float = Field(..., gt=0, description="Temp. de reservorio [°F]")
    drive_mechanism: DriveMechanismStr
    fetkovich_n: float | None = Field(
        None, ge=0.5, le=1.0,
        description="Exponente n de Fetkovich [-]. 1.0 = laminar, 0.5 = turbulento "
                    "pleno. Obligatorio si ipr_method es 'fetkovich': un ensayo de "
                    "un solo punto no permite ajustar C y n a la vez.",
    )


class IPRFromTestRequest(BaseModel):
    """Entrada mínima para derivar la entregabilidad de un ensayo."""

    static_pressure: float = Field(..., gt=0, description="Presión estática [psia]")
    test_pwf: float = Field(..., ge=0, description="Pwf del ensayo [psia]")
    test_rate: float = Field(..., gt=0, description="Caudal del ensayo [STB/d]")
    ipr_method: IPRMethodStr
    bubble_point: float = Field(
        ..., ge=0,
        description="Presión de burbuja [psia]. La usa VOGEL para separar el "
                    "tramo recto de la IPR (arriba de Pb) del curvo (abajo).",
    )
    fetkovich_n: float | None = Field(
        None, ge=0.5, le=1.0, description="Exponente n de Fetkovich [-]",
    )


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
    pump_setting_depth: float | None = Field(
        None, gt=0,
        description="Profundidad de succión [ft MD]. Opcional: si se omite se "
                    "calcula como tope de punzados menos margen de seguridad.",
    )


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
    max_gip: float = Field(
        0.10, ge=0, le=1,
        description="FRACCIÓN máxima de gas libre admisible a la entrada de la "
                    "bomba [0-1], ya descontados el venteo y el separador. Por "
                    "encima, el diseño BES no converge y hay que evaluar otro "
                    "método de levantamiento. Es fracción V_gas/(V_gas+V_líq), "
                    "no relación V_gas/V_líq.",
    )
    design_life_years: float = Field(..., gt=0, description="Vida de diseño [años]")
    use_vsd: bool
    design_frequency_hz: float | None = Field(
        None, ge=20, le=90,
        description="Frecuencia de operación de la bomba [Hz]. Vacío = la frecuencia "
                    "de red. Sólo válido con use_vsd: sin variador la bomba gira a la "
                    "frecuencia de línea. La curva se reescala a esta frecuencia con "
                    "las leyes de afinidad antes de seleccionar.",
    )


class DesignInputs(BaseModel):
    """The five input models bundled (without run options)."""
    reservoir: ReservoirSchema
    fluid: FluidSchema
    well: WellSchema
    surface: SurfaceSchema
    objectives: ObjectivesSchema


class DesignRequest(DesignInputs):
    """Full input bundle for a design run."""
    n: int = Field(3, ge=1, le=10, description="Número de recomendaciones a devolver")
    pump_model: str | None = Field(
        None,
        description="Modelo de bomba del catálogo a forzar manualmente. Si se "
                    "especifica, se omite el motor de recomendación y se devuelve "
                    "el diseño completo para esa única bomba (bypassa 'n').",
    )
