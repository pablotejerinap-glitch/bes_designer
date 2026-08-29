"""Esquemas de pedido — espejan las cinco dataclasses de entrada del dominio.

Los nombres de campo coinciden 1:1 con las dataclasses de ``core/models.py``,
así el mapeo es trivial. Los enums se exponen como cadenas en minúscula,
nunca como los enteros de ``auto()``.

**La validación de rangos físicos queda en el ``__post_init__`` del
dominio** (y sale como HTTP 422). Acá sólo se exigen los tipos y la forma del
JSON, más unos pocos límites obvios y baratos que hacen más legible la
documentación OpenAPI.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

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
    # Opcionales a propósito: sin ensayo de laboratorio la viscosidad se lee de
    # la Fig. 4L(2) del libro con la °API y la temperatura de admisión. `null`
    # dice «no hay dato»; 0 sería un dato falso y se rechaza.
    oil_viscosity_dead: float | None = Field(
        None, gt=0,
        description="Viscosidad dead-oil medida [cp]. Omitir o null si no hay "
                    "ensayo: se lee la Fig. 4L(2) del libro.",
    )
    viscosity_temp_ref: float | None = Field(
        None, gt=0,
        description="Temp. a la que se midió esa viscosidad [°F]. Obligatoria "
                    "sólo si se manda oil_viscosity_dead.",
    )
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
    pressure_loss_method: Literal["poettmann_carpenter", "hazen_williams"] | None = Field(
        None,
        description="Correlación con la que se calcula la pérdida de carga por "
                    "fricción en el tubing. Vacío = la decide la fracción de gas "
                    "libre en la admisión. 'poettmann_carpenter' sólo es "
                    "aplicable a tubing de 2, 2½ y 3 pulg (OD 2 3/8, 2 7/8 y "
                    "3 1/2 in): con otra cañería el diseño falla. Los otros "
                    "tres límites del método —menos de 5 cp, RGL menor a "
                    "1500 scf/bbl y más de 400 bbl/d— avisan sin frenar.",
    )
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
