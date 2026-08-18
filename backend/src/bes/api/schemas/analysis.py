"""Esquemas de los endpoints de análisis: nodal, sensibilidad, gas y fórmulas."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from bes.api.schemas.inputs import (
    FluidSchema, ObjectivesSchema, ReservoirSchema, SurfaceSchema, WellSchema,
)
from bes.api.schemas.outputs import DesignResultSchema, FormulaSchema


class SensitivityParamStr(str, Enum):
    water_cut = "water_cut"
    gor = "gor"
    static_pressure = "static_pressure"
    target_flow_rate = "target_flow_rate"


# --------------------------------------------------------------------------- #
# Leyes de afinidad
# --------------------------------------------------------------------------- #
class AffinityPoint(BaseModel):
    """Un punto de la curva ya reescalado."""
    flow_bpd: float
    head_ft_per_stage: float
    hp_per_stage: float
    efficiency: float = Field(..., description="Invariante bajo las leyes")


class AffinityCurve(BaseModel):
    """La curva de la bomba a una frecuencia dada."""
    frequency_hz: float
    from_frequency_hz: float = Field(..., description="Frecuencia del catálogo")
    speed_ratio: float = Field(..., description="N₂/N₁ = f₂/f₁")
    diameter_ratio: float
    sg_ratio: float
    synchronous_rpm: float = Field(..., description="120·f/polos")
    motor_rpm: float = Field(..., description="Con el deslizamiento típico del motor")
    min_flow: float
    max_flow: float
    bep_flow: float
    bep_head_per_stage: float
    bep_hp_per_stage: float
    bep_efficiency: float
    points: list[AffinityPoint]


class AffinityResponse(BaseModel):
    pump_manufacturer: str
    pump_series: str
    pump_model: str
    catalog_frequency_hz: float
    curves: list[AffinityCurve]
    target_flow: float | None = None
    frequency_for_target_flow: float | None = Field(
        None, description="f₂ = f₁·Q₂/Q₁ que lleva el BEP al caudal objetivo [Hz]",
    )


# --------------------------------------------------------------------------- #
# IPR desde ensayo
# --------------------------------------------------------------------------- #
class IPRFromTestResponse(BaseModel):
    """Entregabilidad derivada de un ensayo de producción."""

    productivity_index: float = Field(
        ..., description="Índice de productividad [STB/d/psi]. Para Fetkovich es "
                         "la secante en el punto de ensayo (informativo).",
    )
    drawdown_psi: float = Field(..., description="Pr − Pwf del ensayo [psi]")
    aof: float = Field(..., description="Caudal a Pwf = 0 según el ajuste [STB/d]")
    qmax_vogel: float | None = Field(
        None, description="qmax de Vogel [STB/d]; null salvo método 'vogel'",
    )
    fetkovich_c: float | None = Field(
        None, description="C de Fetkovich [STB/d/psia^(2n)]; null salvo 'fetkovich'",
    )
    fetkovich_n: float | None = Field(
        None, description="n de Fetkovich [-]; null salvo 'fetkovich'",
    )


# --------------------------------------------------------------------------- #
# Nodal
# --------------------------------------------------------------------------- #
class NodalRequest(BaseModel):
    reservoir: ReservoirSchema
    fluid: FluidSchema
    well: WellSchema
    surface: SurfaceSchema
    pr_decline_pct: float = Field(0.0, ge=0, le=90, description="Declinación de Pr [%]")
    # Contexto de bomba (opcional; normalmente del top design).
    pump_model: str | None = Field(None, description="Modelo de bomba para el flujo con BES")
    stages: int | None = Field(None, gt=0)
    pump_depth: float | None = Field(None, gt=0)


class NodalResponse(BaseModel):
    method: str = Field(..., description="Siempre 'poettmann_carpenter'")
    pr_decline_pct: float
    static_pressure_eff: float
    has_pump: bool
    metrics: dict[str, float]
    figure: dict                       # Plotly figure JSON (data + layout)


# --------------------------------------------------------------------------- #
# Método de incrementos de presión (pozos con gas) — Brown §4.53103
# --------------------------------------------------------------------------- #
class PVTPointSchema(BaseModel):
    """Una fila de un análisis PVT de laboratorio.

    Las propiedades son opcionales: un informe rara vez publica las seis
    columnas, y lo que falte se completa con correlación quedando marcado como
    tal en la respuesta.
    """
    pressure: float = Field(..., gt=0, description="Presión de la fila [psia]")
    rs: float | None = Field(None, ge=0, description="Gas en solución [scf/STB]")
    bo: float | None = Field(None, gt=0, description="Factor volumétrico del petróleo [rb/STB]")
    bg: float | None = Field(None, gt=0, description="Factor volumétrico del gas [bbl/scf]")
    bw: float | None = Field(None, gt=0, description="Factor volumétrico del agua [bbl/STB]")
    z: float | None = Field(None, gt=0, description="Compresibilidad del gas [-]")
    mu_oil: float | None = Field(None, gt=0, description="Viscosidad del petróleo vivo [cp]")


class PVTTableSchema(BaseModel):
    """Análisis PVT medido. Gana sobre las correlaciones, propiedad por propiedad."""
    points: list[PVTPointSchema] = Field(..., min_length=2)
    source: str = Field("PVT experimental", description="Origen del dato, textual")
    temperature_f: float | None = Field(None, description="Temperatura del ensayo [°F]")


class GasIncrementRequest(BaseModel):
    reservoir: ReservoirSchema
    fluid: FluidSchema
    well: WellSchema
    surface: SurfaceSchema
    objectives: ObjectivesSchema
    increment_psi: float = Field(
        200.0, gt=0, le=1000,
        description="Tamaño del escalón de presión [psi]. Más chico = mejor "
                    "representa el cambio del fluido dentro del intervalo.",
    )
    pump_depth: float | None = Field(None, gt=0, description="Profundidad de admisión [ft]")
    p_intake: float | None = Field(
        None, gt=0,
        description="Presión de admisión [psia]. Vacío = calcularla con el "
                    "recorrido multifásico.",
    )
    p_discharge: float | None = Field(
        None, gt=0, description="Presión de descarga [psia]. Vacío = calcularla.",
    )
    vent_gas_pct: float = Field(0.0, ge=0, le=1, description="Gas libre venteado [0-1]")
    apply_deterioration: bool = Field(
        False, description="Degrada la altura por gas libre (Brown §4.53102)",
    )
    apply_viscosity: bool = Field(
        True, description="Corrección de Riling por intervalo (Brown §4.53112)",
    )
    fixed_pump_model: str | None = Field(
        None, description="Fija el modelo en vez de seleccionarlo del catálogo",
    )
    pvt_table: PVTTableSchema | None = Field(
        None, description="PVT de laboratorio; sin esto se usan correlaciones",
    )


class GasIncrementRow(BaseModel):
    """Una fila de la tabla por intervalo (§23 del procedimiento).

    Lleva los valores en **los dos extremos** del intervalo y el **promedio**
    que se usó para calcular, porque el promedio solo no deja auditar la cuenta.
    """
    p_lo: float
    p_hi: float
    delta_p: float
    # Promedios del intervalo — son los que entran al cálculo
    rs: float
    bo: float
    bg: float
    bw: float
    free_gas_scf: float
    v_total: float
    rho_mix: float
    gradient: float
    sg_mix: float
    fg_ratio: float
    q_avg_bpd: float
    # Extremos
    q_lo_bpd: float
    q_hi_bpd: float
    q_oil_lo: float
    q_oil_hi: float
    q_water_lo: float
    q_water_hi: float
    q_gas_lo: float
    q_gas_hi: float
    rs_lo: float
    rs_hi: float
    bo_lo: float
    bo_hi: float
    bg_lo: float
    bg_hi: float
    rho_lo: float
    rho_hi: float
    gradient_lo: float
    gradient_hi: float
    # Bomba
    pump_model: str
    head_per_stage: float
    efficiency: float
    det_factor: float
    head_effective: float
    hp_per_stage_w: float
    psi_per_stage: float
    stages_exact: float
    stages: int
    hp: float
    # Viscosidad (Riling)
    is_viscous: bool
    capacity_factor: float
    head_factor: float
    hp_factor: float
    # Trazabilidad del dato (§25)
    pvt_sources: dict[str, str]


class GasIncrementSummary(BaseModel):
    p_intake: float
    p_discharge: float
    delta_p: float
    increment_psi: float
    n_increments: int
    target_oil_rate: float
    target_liquid_rate: float
    q_mix_intake_bpd: float
    q_mix_discharge_bpd: float
    q_mix_max_bpd: float
    q_mix_min_bpd: float
    mass_rate_lbm_d: float
    total_stages: int
    total_stages_exact: float
    total_stages_longhand: int
    total_hp: float
    pump_model: str
    pump_manufacturer: str
    pump_series: str
    pump_setting_depth: float
    pump_intake_temp_f: float
    pvt_source: str
    gip: float


class GasIncrementResponse(BaseModel):
    summary: GasIncrementSummary
    increments: list[GasIncrementRow]
    free_gas_fraction_at_intake: float
    gas_risk: dict
    separator: dict
    warnings: list[str]
    ladder_figure: dict = Field(
        default_factory=dict,
        description="Escalera de incrementos (Brown Fig. 4.56B) como Plotly "
                    "figure JSON. Acompaña al cálculo, igual que el nodal.",
    )
    formulas: list[FormulaSchema] = Field(
        default_factory=list,
        description="Qué cuenta hizo el método y con qué números. La arma el "
                    "mismo código que calcula (bes.core.formulas): un tramo "
                    "entero más los totales.",
    )


class GasMethodDecision(BaseModel):
    """Por qué se usó (o no) el método por incrementos.

    El criterio no es nuevo: es el mismo umbral de gas libre despreciable que
    el proyecto ya usaba para elegir la correlación de fricción.
    """
    applies: bool
    free_gas_fraction: float
    threshold: float
    negligible_reference: float
    reason: str


class GasCompleteDesignRequest(BaseModel):
    reservoir: ReservoirSchema
    fluid: FluidSchema
    well: WellSchema
    surface: SurfaceSchema
    objectives: ObjectivesSchema
    increment_psi: float = Field(200.0, gt=0, le=1000)
    pump_depth: float | None = Field(None, gt=0)
    vent_gas_pct: float = Field(0.0, ge=0, le=1)
    apply_deterioration: bool = False
    apply_viscosity: bool = True
    fixed_pump_model: str | None = None
    pvt_table: PVTTableSchema | None = None


class GasFeasibility(BaseModel):
    """Cuánto gas llega realmente a la bomba, y si eso la deja funcionar.

    Las reducciones se aplican sobre la **relación** gas/líquido, no sobre la
    fracción: el separador saca gas y deja el líquido, así que la fracción no
    escala linealmente.
    """
    viable: bool
    f_intake: float = Field(..., description="Gas libre en la admisión [0-1]")
    f_after_vent: float = Field(..., description="Tras ventear por el anular")
    f_pump: float = Field(..., description="El que efectivamente entra a la bomba")
    max_gip: float = Field(..., description="Máximo admisible (objectives.max_gip)")
    vent_fraction: float
    separator_efficiency: float | None
    separator_model: str | None
    required_efficiency: float | None = Field(
        None, description="Eficiencia que haría falta; None si ya cumple",
    )
    verdict: str


class GasCompleteDesignResponse(BaseModel):
    """Diseño BES completo por el método de incrementos.

    ``design`` es el **mismo** esquema que devuelve el camino convencional, así
    que la vista de resultados se reutiliza sin cambios. Lo específico del
    método viaja aparte.
    """
    design: DesignResultSchema
    method: GasMethodDecision
    feasibility: GasFeasibility
    increments: list[GasIncrementRow]
    summary: GasIncrementSummary
    tdh_increment_ft: float = Field(
        ..., description="Σ ΔPᵢ/gradienteᵢ — con este se dimensionó el aparejo",
    )
    tdh_conventional_ft: float = Field(
        ..., description="TDH de tres términos, para auditar la discrepancia",
    )
    rejected: list[str] = Field(
        default_factory=list,
        description="Bombas descartadas y por qué, en orden de intento",
    )
    warnings: list[str] = Field(default_factory=list)
    ladder_figure: dict = Field(
        default_factory=dict,
        description="Escalera de incrementos (Brown Fig. 4.56B) como Plotly "
                    "figure JSON. Acompaña al cálculo, igual que el nodal.",
    )


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


# --------------------------------------------------------------------------- #
# Catálogo de fórmulas
# --------------------------------------------------------------------------- #
class FormulaSpecSchema(BaseModel):
    """Una fórmula del motor, tal como está declarada en el catálogo.

    Es la DECLARACIÓN, no una corrida: no trae números. Los números llegan por
    la traza del diseño (``FormulaSchema``), que sale de esta misma fuente.
    """
    key: str = Field(..., description="Clave única en todo el catálogo")
    topic: str = Field(..., description="Tema al que pertenece")
    step: str = Field(
        ..., description="Paso conceptual. Varias fórmulas lo comparten cuando "
                         "son el mismo cálculo por métodos distintos; en una "
                         "corrida se ejecuta exactamente una.",
    )
    label: str = Field(..., description="Qué se calcula, en castellano")
    expression: str = Field(..., description="La fórmula en símbolos")
    units: str = Field(..., description="Unidad del resultado")
    symbols: dict[str, str] = Field(
        default_factory=dict,
        description="Cada símbolo de la expresión con su significado y unidad",
    )
    reference: str = Field("", description="Cita bibliográfica")
    note: str = Field("", description="Condición de validez que vale siempre")
    module: str = Field("", description="Dónde se ejecuta, para quien lea el código")


class FormulaTopicSchema(BaseModel):
    """Un capítulo del motor, con sus fórmulas."""
    key: str
    label: str
    blurb: str = Field(..., description="Qué resuelve, en una línea")
    instrumented: bool = Field(
        ..., description="False mientras el tema no emita traza. Se publica "
                         "igual para mostrar la cobertura real.",
    )
    formulas: list[FormulaSpecSchema] = Field(default_factory=list)


class FormulaCatalogResponse(BaseModel):
    """Todas las fórmulas del motor, sin correr ningún diseño."""
    topics: list[FormulaTopicSchema]
    total: int = Field(..., description="Fórmulas instrumentadas hoy")
    pending_topics: list[str] = Field(
        default_factory=list, description="Temas que todavía no emiten traza",
    )
