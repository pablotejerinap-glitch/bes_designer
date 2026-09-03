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

    **Los campos tienen que seguir a los de** :class:`bes.core.formulas.Formula`.
    El mapper hace ``FormulaSchema(**asdict(f))`` y Pydantic descarta en
    silencio lo que no esté declarado acá: si se agrega un campo al dominio y
    no a este esquema, el dato nunca llega a la pantalla y no falla nada.
    ``tests/test_api.py::TestElContratoSigueAlDominio`` lo verifica.
    """
    key: str = Field(..., description="Clave única en el catálogo de fórmulas")
    step: str = Field(
        "", description="Paso conceptual. Varias fórmulas lo comparten cuando "
                        "son el mismo cálculo por métodos distintos.",
    )
    topic: str = Field("", description="Tema del catálogo al que pertenece")
    label: str = Field(..., description="Qué se calcula, en castellano")
    expression: str = Field(..., description="La fórmula en símbolos")
    substitution: str = Field(..., description="La fórmula con los números puestos")
    inputs: dict[str, float] = Field(default_factory=dict)
    symbols: dict[str, str] = Field(
        default_factory=dict,
        description="Qué significa cada símbolo, con su unidad",
    )
    result: float
    units: str
    reference: str = Field("", description="Cita bibliográfica")
    note: str = Field("", description="Condición de validez que vale siempre")
    context: str = Field(
        "", description="Por qué esta variante y con qué datos, en este caso",
    )
    applies: bool | None = Field(
        None,
        description="Sólo en métodos partidos en tramos (Vogel generalizado): "
                    "True = es el tramo que gobierna este pozo, False = se "
                    "muestra para poder revisar el método completo pero el "
                    "punto de diseño no cae acá, None = no corresponde.",
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
    # --- Escalera de manejo de gas (bes.core.gas_handling) -----------------
    # Estos campos vienen del dominio y Pydantic los DESCARTA EN SILENCIO si no
    # están declarados acá: sin ellos la pantalla no puede decir en qué escalón
    # quedó el pozo. Ver DesignResultSchema y test_api::TestElContratoSigueAlDominio.
    strategy: str = Field(
        "", description="'ninguno' | 'simple' | 'tandem' | 'agh' | 'no_viable'",
    )
    n_separators: int = Field(0, description="Separadores en serie")
    switch_lift_method: bool = Field(
        False, description="True = ni el techo de la tecnología BES alcanza",
    )
    uses_agh: bool = Field(
        False,
        description="El aparejo lleva manejador avanzado de gas. NO retira gas: "
                    "acondiciona la mezcla y sube la tolerancia de max_gip al "
                    "GVF que publica el equipo.",
    )
    agh_model: str | None = None
    agh_max_gvf: float | None = Field(
        None, description="Fracción de vacío máxima del manejador [0-1]",
    )
    tolerance: float = Field(
        0.0,
        description="Contra qué se comparó el gas en la bomba: max_gip en los "
                    "tres primeros escalones, el GVF del manejador en el cuarto",
    )
    # --- Las dos condiciones de cada escalón --------------------------------
    # Cada escalón responde dos preguntas medidas en puntos distintos, y las
    # dos tienen que dar bien:
    #   1. ¿la configuración soporta este pozo?  gas en la ADMISIÓN vs capacidad
    #   2. ¿el gas que entra a la bomba cumple?  gas DESPUÉS de separar vs max_gip
    # Publicarlas por separado es lo que permite decir cuál falló, y el remedio
    # de cada una es distinto.
    capacity: float = Field(
        0.0,
        description="Fracción de vacío en la admisión que admite la "
                    "configuración elegida (Takács, Fig. 4.25, pág. 195): "
                    "0.20 sin separador, 0.80 con uno, 0.95 en tándem",
    )
    tandem_arrangement: str | None = Field(
        None,
        description="Cómo se armó el tándem: 'tipos distintos' es lo que "
                    "documenta la bibliografía; cualquier otro valor es una "
                    "extrapolación y viaja además como advertencia",
    )


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
    gas_handler_hp: float = 0.0
    gas_q_representative_bpd: float = 0.0
    gas_q_intake_bpd: float = 0.0
    gas_q_discharge_bpd: float = 0.0
    # Escalera de manejo de gas (Takács §4.4.5). 2 separadores = TÁNDEM.
    gas_handler_count: int = 0
    gas_strategy: str = ""
    gas_fraction_at_pump: float = 0.0
    switch_lift_method: bool = False
    gas_verdict: str = ""
    # La escalera entera. Los cuatro campos de arriba son su resumen y se
    # conservan (los lee la vista de resultados y los reportes); esto es lo que
    # falta para poder explicar el veredicto —contra qué se comparó, cuánto se
    # separó y con qué equipo— también por el camino convencional.
    # ``None`` cuando el diseño no corrió la escalera.
    gas_feasibility: GasFeasibility | None = None
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
