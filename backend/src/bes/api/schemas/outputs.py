"""Response schemas — mirror ``DesignResult`` and the ``generate_recommendations``
return shape. ``DesignResult`` has no enums, so mapping is
``DesignResultSchema(**dataclasses.asdict(dr))``.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class HousingDetail(BaseModel):
    """Una carcasa del arreglo, con su verificación de presión.

    ``position`` va de la admisión (1) hacia la descarga, que es el orden en
    que se arma el tándem y el orden en que crece la presión.
    """
    position: int = Field(..., description="1 = carcasa de admisión")
    stages: int = Field(..., description="Capacidad de la carcasa [etapas]")
    code: str = Field("", description="Código de fábrica; vacío si el catálogo no lo trae")
    material: str = Field("", description="Material; vacío si el catálogo no lo trae")
    od_in: float = Field(0.0, description="Diámetro exterior [in]; 0 = sin dato")
    length_ft: float = Field(0.0, description="Longitud [ft]; 0 = sin dato")
    weight_lbs: float = Field(0.0, description="Peso [lbs]; 0 = sin dato")
    active_stages_below: int = Field(
        ..., description="Etapas activas en esta carcasa y por debajo",
    )
    pressure_psi: float = Field(..., description="Presión de operación a caudal cero [psi]")
    limit_psi: float = Field(..., description="Presión máxima admisible [psi]; 0 = sin dato")
    limit_known: bool = Field(..., description="False = el catálogo no publica el límite")
    pressure_ok: bool = Field(..., description="Resultado de la verificación")


class ShaftCheck(BaseModel):
    """Potencia sobre el eje contra los límites de la serie."""
    verified: bool = Field(..., description="False = el catálogo no tiene la serie")
    hp_shaft: float = Field(..., description="HP_eje = P_etapa × #Etapas × Pem [hp]")
    limit_std: float = Field(..., description="Límite del eje estándar [hp], a la frecuencia de diseño")
    limit_high_strength: float = Field(..., description="Límite del eje de alta resistencia [hp]")
    shaft_type: str = Field(..., description="'standard' | 'high_strength' | '' si no verifica")
    ok: bool
    note: str


class BearingCheck(BaseModel):
    """Etapas contra la capacidad del cojinete de empuje, con su tope de temperatura."""
    verified: bool = Field(..., description="False = el catálogo no tiene la serie")
    stages: int
    limit_stages: int = Field(..., description="Máximo de etapas del cojinete aplicable")
    bearing_type: str = Field(..., description="'standard' | 'high_load' | '' si no verifica")
    bht_max_f: float = Field(..., description="Temperatura de fondo máxima de ese cojinete [°F]")
    ok: bool
    note: str


class StagingCeiling(BaseModel):
    """Los tres topes de etapas del fabricante. 0 = sin dato para esa vía."""
    by_housing_pressure: int
    by_shaft: int
    by_bearing: int
    governing: int = Field(..., description="El menor de los conocidos; 0 si ninguno")
    governing_by: str = Field(..., description="Cuál manda; '' si no hay datos")


class FormulaSchema(BaseModel):
    """Una cuenta del diseño, lista para mostrar y auditar.

    La arma el mismo código que calcula (``bes/core/formulas.py``), de modo que
    la fórmula que se muestra en pantalla es necesariamente la que se aplicó.
    """
    key: str = Field(..., description="Identificador estable del paso")
    label: str = Field(..., description="Qué se calcula, en castellano")
    expression: str = Field(..., description="La fórmula en símbolos")
    substitution: str = Field(..., description="La fórmula con los números puestos")
    inputs: dict[str, float] = Field(default_factory=dict)
    result: float
    units: str
    reference: str = Field("", description="Cita bibliográfica")
    note: str = Field("", description="Condición de validez o supuesto")


class DesignResultSchema(BaseModel):
    # Pump
    pump_manufacturer: str
    pump_series: str
    pump_model: str
    pump_od: float
    num_stages: int
    pump_setting_depth: float
    intake_pressure: float
    total_head_required: float
    head_per_stage: float
    hp_per_stage: float
    pump_efficiency: float
    total_pump_hp: float
    # Motor
    motor_manufacturer: str
    motor_model: str
    motor_hp: float
    motor_voltage: float
    motor_amperage: float
    motor_od: float
    motor_length: float
    # Cable / power
    cable_type: str
    cable_awg: int
    cable_voltage_drop: float
    surface_voltage_required: float
    transformer_kva: float
    # System
    system_efficiency: float
    flow_rate_achieved: float
    operating_frequency: float
    gip_fraction: float
    warnings: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    formulas: list[FormulaSchema] = Field(
        default_factory=list,
        description="Cada cuenta del diseño con su fórmula, los números "
                    "reemplazados, el resultado y la cita bibliográfica.",
    )
    # Correlación usada para la pérdida de carga en el tubing, según la
    # fracción de gas libre en la admisión frente al umbral de objetivos.
    friction_method: str = Field(
        "hazen_williams",
        description="'hazen_williams' (monofásica) o 'poettmann_carpenter' (multifásica)",
    )
    gas_fraction_threshold: float = Field(
        0.10, description="Umbral de gas libre que disparó la elección [0-1]",
    )
    # Housing / carcasas — optimización automática (bes.core.housing)
    housing_size_stages: int = 0
    dummy_stages: int = 0
    n_housings: int = 1
    max_housing_pressure_psi: float = 0.0
    housing_pressure_limit_psi: float = 0.0
    housing_pressure_ok: bool = True
    housing_detail: list[HousingDetail] = Field(
        default_factory=list,
        description="Ficha por carcasa, de la admisión a la descarga",
    )
    housing_rationale: str = Field(
        "", description="Justificación técnica de la combinación elegida",
    )
    housing_pressure_verified: bool = Field(
        False,
        description="False = el catálogo no publica la presión admisible y la "
                    "verificación no pudo realizarse",
    )
    # Verificación mecánica de la serie (eje / cojinete). Vacías si el catálogo
    # no tiene ficha de la serie.
    shaft_check: ShaftCheck | None = Field(
        None, description="HP sobre el eje vs. límite estándar / alta resistencia",
    )
    bearing_check: BearingCheck | None = Field(
        None, description="Etapas vs. capacidad del cojinete a la temperatura de fondo",
    )
    bearing_load_lbs: float = Field(
        0.0, description="Carga axial sobre el cojinete del sello: Ho × Pem × A_eje [lbs]",
    )
    staging_ceiling: StagingCeiling | None = Field(
        None, description="Tope de etapas por carcasa, eje y cojinete; manda el menor",
    )
    fluid_velocity_ft_s: float = 0.0
    cooling_ok: bool = True
    motor_hp_max: float = 0.0
    controller_manufacturer: str = ""
    controller_model: str = ""
    controller_type: str = ""
    # Seal / protector (optional)
    seal_manufacturer: str = ""
    seal_model: str = ""
    seal_type: str = ""
    seal_thrust_capacity_lbs: float = 0.0
    axial_thrust_lbs: float = 0.0
    # Gas handler / separator (optional)
    gas_handler_manufacturer: str = ""
    gas_handler_model: str = ""
    gas_handler_type: str = ""
    gas_handler_efficiency: float = 0.0
    # Downhole sensor (optional)
    sensor_manufacturer: str = ""
    sensor_model: str = ""


class CriteriaSchema(BaseModel):
    """Los valores crudos de ingeniería detrás del orden — sin puntajes ni pesos.

    ``bep_distance_frac`` es el criterio 1, ``efficiency`` el 2 y
    ``total_pump_hp`` el 3; el resto es contexto para la pantalla.
    ``classification`` etiqueta la distancia al BEP **sólo para mostrar** y nunca
    interviene en el orden.
    """
    bep_flow_bpd: float
    bep_distance_frac: float
    flow_vs_bep_pct: float
    efficiency: float
    total_pump_hp: float
    classification: str


class RecommendationSchema(BaseModel):
    rank: int
    criteria: CriteriaSchema
    design: DesignResultSchema
    rationale: str
    warnings: list[str] = Field(default_factory=list)


class DesignResponse(BaseModel):
    recommendations: list[RecommendationSchema]
    design_basis: dict[str, float]
    ordering_criteria: list[str] = Field(
        description="Criterios aplicados, en orden de prioridad. Documentan el "
                    "método: no son pesos configurables.",
    )
    n_candidates_evaluated: int
    warnings: list[str] = Field(default_factory=list, description="Warnings del run (p.ej. reservorio depletado)")
