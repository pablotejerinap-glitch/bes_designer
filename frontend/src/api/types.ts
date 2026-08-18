// Tipos que espejan el contrato de la API (ver backend api/schemas/*).
// Se pueden regenerar desde openapi.json con `npm run gen:api` (openapi-typescript),
// pero estos escritos a mano mantienen el código legible.

export type IPRMethod = "linear" | "vogel" | "fetkovich";
export type DriveMechanism =
  | "solution_gas"
  | "water_drive"
  | "gas_cap"
  | "combination";
export type SensitivityParam =
  | "water_cut"
  | "gor"
  | "static_pressure"
  | "target_flow_rate";

export interface ReservoirInput {
  static_pressure: number;
  bubble_point: number;
  /** Ensayo — Pwf medida [psia]. Debe ser < static_pressure. */
  test_pwf: number;
  /** Ensayo — caudal bruto medido [STB/d]. */
  test_rate: number;
  ipr_method: IPRMethod;
  reservoir_temp: number;
  drive_mechanism: DriveMechanism;
  /** Exponente n [-], rango físico [0.5, 1.0]. Obligatorio con "fetkovich":
   *  un ensayo de un solo punto no permite ajustar C y n a la vez. */
  fetkovich_n?: number | null;
}

/** Entregabilidad derivada del ensayo (POST /api/ipr/from-test). */
export interface IPRFromTestResponse {
  productivity_index: number;
  drawdown_psi: number;
  aof: number;
  qmax_vogel: number | null;
  fetkovich_c: number | null;
  fetkovich_n: number | null;
}

export interface FluidInput {
  oil_api: number;
  water_cut: number;
  gor: number;
  gas_sg: number;
  water_sg: number;
  oil_viscosity_dead: number;
  viscosity_temp_ref: number;
  bubble_point_pressure: number;
  h2s_content: number;
  co2_content: number;
  sand_production: boolean;
}

export interface WellInput {
  total_depth: number;
  casing_od: number;
  casing_weight: number;
  casing_id: number;
  tubing_od: number;
  tubing_id: number;
  perforations_top: number;
  perforations_bottom: number;
  deviation_max: number;
  wellhead_temp: number;
  /**
   * Profundidad de succión [ft MD]. Opcional: `null` deja que el backend la
   * calcule como tope de punzados menos el margen de seguridad.
   */
  pump_setting_depth?: number | null;
}

/** Una fila de la tabla dimensional Tenaris (API 5CT): un OD + peso nominal con
 *  su ID y drift resueltos. Espeja `TubularDim` del backend. */
export interface TubularDim {
  od_in: number;
  od_label: string;
  od_mm?: number | null;
  weight_lbft: number;
  wall_in?: number | null;
  id_in: number;
  drift_in?: number | null;
}

/** Tablas dimensionales de casing y tubing (`GET /api/catalogs/tubulars`). */
export interface TubularCatalog {
  casing: TubularDim[];
  tubing: TubularDim[];
}

export interface SurfaceInput {
  wellhead_pressure_required: number;
  flowline_length: number;
  flowline_id: number;
  flowline_elevation_change: number;
  separator_pressure: number;
  power_supply_voltage: number;
  frequency: number;
}

export interface ObjectivesInput {
  target_flow_rate: number;
  safety_margin_depth: number;
  allow_gas_venting: boolean;
  max_gip: number;
  design_life_years: number;
  use_vsd: boolean;
  /** Fracción de gas libre en la admisión por encima de la cual la pérdida de
   *  carga en el tubing se calcula con Poettmann-Carpenter en vez de
   *  Hazen-Williams [0-1]. Default 0.10. */
  /** Frecuencia de operación [Hz]. Vacío = frecuencia de red. Sólo con use_vsd. */
  design_frequency_hz?: number | null;
}

export interface DesignInputs {
  reservoir: ReservoirInput;
  fluid: FluidInput;
  well: WellInput;
  surface: SurfaceInput;
  objectives: ObjectivesInput;
}

export interface DesignRequest extends DesignInputs {
  n: number;
  /** Modelo de bomba a forzar manualmente; si se especifica, bypassa el
   *  motor de recomendación y devuelve una única opción para esa bomba. */
  pump_model?: string | null;
}

/** Un punto de la curva reescalado por las leyes de afinidad. */
export interface AffinityPoint {
  flow_bpd: number;
  head_ft_per_stage: number;
  hp_per_stage: number;
  /** Invariante bajo las leyes de afinidad. */
  efficiency: number;
}

/** La curva de la bomba a una frecuencia dada. */
export interface AffinityCurve {
  frequency_hz: number;
  from_frequency_hz: number;
  /** N₂/N₁ = f₂/f₁ */
  speed_ratio: number;
  diameter_ratio: number;
  sg_ratio: number;
  synchronous_rpm: number;
  motor_rpm: number;
  min_flow: number;
  max_flow: number;
  bep_flow: number;
  bep_head_per_stage: number;
  bep_hp_per_stage: number;
  bep_efficiency: number;
  points: AffinityPoint[];
}

export interface AffinityResponse {
  pump_manufacturer: string;
  pump_series: string;
  pump_model: string;
  catalog_frequency_hz: number;
  curves: AffinityCurve[];
  target_flow: number | null;
  /** f₂ = f₁·Q₂/Q₁ que lleva el BEP al caudal objetivo [Hz]. */
  frequency_for_target_flow: number | null;
}

/** Potencia sobre el eje contra los límites de la serie. */
export interface ShaftCheck {
  /** false = el catálogo no tiene ficha mecánica de esta serie. */
  verified: boolean;
  /** HP_eje = P_etapa × #Etapas × Pem */
  hp_shaft: number;
  limit_std: number;
  limit_high_strength: number;
  shaft_type: "standard" | "high_strength" | "";
  ok: boolean;
  note: string;
}

/** Etapas contra la capacidad del cojinete de empuje, con su tope de temperatura. */
export interface BearingCheck {
  verified: boolean;
  stages: number;
  limit_stages: number;
  bearing_type: "standard" | "high_load" | "";
  bht_max_f: number;
  ok: boolean;
  note: string;
}

/** Los tres topes de etapas del fabricante. 0 = sin dato para esa vía. */
export interface StagingCeiling {
  by_housing_pressure: number;
  by_shaft: number;
  by_bearing: number;
  governing: number;
  governing_by: string;
}

/** Una carcasa del arreglo, con su verificación de presión. */
export interface HousingDetail {
  /** 1 = carcasa de admisión; crece hacia la descarga. */
  position: number;
  stages: number;
  /** Vacío si el catálogo no lo publica. */
  code: string;
  material: string;
  /** 0 = sin dato. */
  od_in: number;
  length_ft: number;
  weight_lbs: number;
  active_stages_below: number;
  pressure_psi: number;
  /** 0 = sin dato. */
  limit_psi: number;
  limit_known: boolean;
  pressure_ok: boolean;
}

/**
 * Una cuenta del diseño, con la fórmula que se aplicó y los números puestos.
 *
 * La arma el backend desde el mismo código que calcula, así que lo que se
 * muestra es necesariamente lo que se ejecutó: no puede desincronizarse.
 */
export interface Formula {
  /** Clave única en el catálogo ("tdh", "pwf_vogel_bifasico"…). */
  key: string;
  /**
   * Paso conceptual. Varias fórmulas lo comparten cuando son el mismo cálculo
   * por métodos distintos (la Pwf sale por Darcy, Vogel o Fetkovich); en una
   * corrida se ejecuta exactamente una.
   */
  step: string;
  /** Tema del catálogo: "ipr", "tdh", "diseno", "viscosidad", "gas"… */
  topic: string;
  /** Qué se calcula, en castellano. */
  label: string;
  /** La fórmula en símbolos, como está en el libro. */
  expression: string;
  /** La misma fórmula con los valores reemplazados. */
  substitution: string;
  /** Los valores que entraron, por símbolo. */
  inputs: Record<string, number>;
  /** Qué significa cada símbolo, con su unidad. */
  symbols: Record<string, string>;
  result: number;
  units: string;
  /** Cita bibliográfica. */
  reference: string;
  /** Condición de validez que vale siempre. Viene del catálogo. */
  note: string;
  /** Por qué esta variante y con qué datos, en este caso concreto. */
  context: string;
  /**
   * Sólo en métodos partidos en tramos, como el Vogel generalizado:
   * `true`  = es el tramo que gobierna este pozo,
   * `false` = se muestra para poder revisar el método completo, pero el punto
   *           de diseño no cae en este tramo,
   * `null`  = no es un método partido y la pregunta no corresponde.
   */
  applies: boolean | null;
}

/**
 * Una fórmula tal como está DECLARADA en el catálogo del motor.
 *
 * No trae números: es la declaración. Los números llegan por `Formula`, que
 * sale de esta misma fuente cuando se corre un diseño.
 */
export interface FormulaSpec {
  key: string;
  topic: string;
  step: string;
  label: string;
  expression: string;
  units: string;
  symbols: Record<string, string>;
  reference: string;
  note: string;
  /** Dónde se ejecuta, para quien sí quiera leer el código. */
  module: string;
}

/** Un capítulo del motor, con sus fórmulas. */
export interface FormulaTopic {
  key: string;
  label: string;
  /** Qué resuelve, en una línea. */
  blurb: string;
  /** false mientras el tema no emita traza. Se publica igual, no se esconde. */
  instrumented: boolean;
  formulas: FormulaSpec[];
}

export interface FormulaCatalog {
  topics: FormulaTopic[];
  total: number;
  pending_topics: string[];
}

export interface DesignResult {
  pump_manufacturer: string;
  pump_series: string;
  pump_model: string;
  pump_od: number;
  num_stages: number;
  pump_setting_depth: number;
  intake_pressure: number;
  total_head_required: number;
  head_per_stage: number;
  hp_per_stage: number;
  pump_efficiency: number;
  total_pump_hp: number;
  motor_manufacturer: string;
  motor_model: string;
  motor_hp: number;
  motor_voltage: number;
  motor_amperage: number;
  motor_od: number;
  motor_length: number;
  cable_type: string;
  cable_awg: number;
  cable_voltage_drop: number;
  surface_voltage_required: number;
  transformer_kva: number;
  system_efficiency: number;
  flow_rate_achieved: number;
  operating_frequency: number;
  gip_fraction: number;
  /** Correlación usada para la pérdida de carga en el tubing. */
  friction_method: "hazen_williams" | "poettmann_carpenter";
  /** Umbral de gas libre que decidió esa elección [0-1]. */
  gas_fraction_threshold: number;
  warnings: string[];
  alternatives: string[];
  /** Traza de las cuentas del diseño, en orden de ejecución. */
  formulas: Formula[];
  housing_size_stages: number;
  dummy_stages: number;
  n_housings: number;
  max_housing_pressure_psi: number;
  housing_pressure_limit_psi: number;
  housing_pressure_ok: boolean;
  /** Ficha por carcasa, de la admisión (posición 1) a la descarga. */
  housing_detail: HousingDetail[];
  /** Justificación técnica de la combinación elegida. */
  housing_rationale: string;
  /** false = el catálogo no publica la presión admisible de la carcasa. */
  housing_pressure_verified: boolean;
  /** Verificación del eje; null si el catálogo no tiene la serie. */
  shaft_check: ShaftCheck | null;
  /** Verificación del cojinete; null si el catálogo no tiene la serie. */
  bearing_check: BearingCheck | null;
  /** Carga TL = Ho × Pem × A_eje [lbs]. */
  bearing_load_lbs: number;
  /** Tope de etapas por carcasa, eje y cojinete. */
  staging_ceiling: StagingCeiling | null;
  fluid_velocity_ft_s: number;
  cooling_ok: boolean;
  motor_hp_max: number;
  controller_manufacturer: string;
  controller_model: string;
  controller_type: string;
  seal_manufacturer: string;
  seal_model: string;
  seal_type: string;
  seal_thrust_capacity_lbs: number;
  axial_thrust_lbs: number;
  gas_handler_manufacturer: string;
  gas_handler_model: string;
  gas_handler_type: string;
  gas_handler_efficiency: number;
  sensor_manufacturer: string;
  sensor_model: string;
}

/** Clasificación de la distancia al BEP. Solo para mostrar: nunca ordena. */
export type BepClassification = "optimo" | "aceptable" | "alejado";

/**
 * Criterios de ingeniería crudos detrás del ordenamiento — sin puntajes ni
 * pesos. `bep_distance_frac` es el criterio 1, `efficiency` el 2 y
 * `total_pump_hp` el 3; el resto es contexto para la UI.
 */
export interface Criteria {
  bep_flow_bpd: number;
  bep_distance_frac: number;
  flow_vs_bep_pct: number;
  efficiency: number;
  total_pump_hp: number;
  classification: BepClassification;
}

export interface Recommendation {
  rank: number;
  criteria: Criteria;
  design: DesignResult;
  rationale: string;
  warnings: string[];
}

export interface DesignResponse {
  recommendations: Recommendation[];
  design_basis: Record<string, number>;
  /** Criterios aplicados, en orden de prioridad. Documentan el método. */
  ordering_criteria: string[];
  n_candidates_evaluated: number;
  warnings: string[];
}

export interface PumpSummary {
  manufacturer: string;
  series: string;
  model: string;
  od: number;
  min_flow: number;
  max_flow: number;
  bep_flow: number;
}

export interface CatalogSummary {
  pumps: PumpSummary[];
  manufacturers: string[];
  counts: Record<string, number>;
}

// Figura Plotly serializada por el backend (fig.to_json()). Se tipa flexible
// para no atarse al namespace global de plotly; se castea al pasar a <Plot>.
export interface PlotlyFigure {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  layout: Record<string, any>;
}

export interface NodalRequest {
  reservoir: ReservoirInput;
  fluid: FluidInput;
  well: WellInput;
  surface: SurfaceInput;
  pr_decline_pct?: number;
  pump_model?: string | null;
  stages?: number | null;
  pump_depth?: number | null;
}

export interface NodalResponse {
  /** Siempre "poettmann_carpenter": es la única correlación del simulador. */
  method: string;
  pr_decline_pct: number;
  static_pressure_eff: number;
  has_pump: boolean;
  metrics: Record<string, number>;
  figure: PlotlyFigure;
}

export interface SensitivityRequest extends DesignInputs {
  param: SensitivityParam;
  pct_range_pct?: number;
  n_points?: number;
}

export interface SensitivityResponse {
  param: string;
  param_label: string;
  param_values: number[];
  metrics: Record<string, number[]>;
  figure: PlotlyFigure;
}

// ---------------------------------------------------------------------------
// Método de incrementos de presión (pozos con gas) — Brown Vol. 2b §4.53103
// ---------------------------------------------------------------------------

/** Una fila de un análisis PVT de laboratorio. Todo salvo la presión es opcional. */
export interface PVTPointInput {
  pressure: number;
  rs?: number | null;
  bo?: number | null;
  bg?: number | null;
  bw?: number | null;
  z?: number | null;
  mu_oil?: number | null;
}

export interface PVTTableInput {
  points: PVTPointInput[];
  source?: string;
  temperature_f?: number | null;
}

export interface GasIncrementRequest extends DesignInputs {
  /** Tamaño del escalón de presión [psi]. Más chico = más fiel al fluido real. */
  increment_psi?: number;
  pump_depth?: number | null;
  /** Vacío = el backend la calcula con el recorrido multifásico. */
  p_intake?: number | null;
  p_discharge?: number | null;
  vent_gas_pct?: number;
  apply_deterioration?: boolean;
  apply_viscosity?: boolean;
  fixed_pump_model?: string | null;
  pvt_table?: PVTTableInput | null;
}

/**
 * Fila de la tabla por intervalo. Lleva los valores en los DOS extremos y el
 * promedio con que se calculó: sin los extremos la cuenta no se puede auditar.
 */
export interface GasIncrementRow {
  p_lo: number;
  p_hi: number;
  delta_p: number;
  // Promedios del intervalo
  rs: number;
  bo: number;
  bg: number;
  bw: number;
  free_gas_scf: number;
  v_total: number;
  rho_mix: number;
  gradient: number;
  sg_mix: number;
  fg_ratio: number;
  q_avg_bpd: number;
  // Extremos
  q_lo_bpd: number;
  q_hi_bpd: number;
  q_oil_lo: number;
  q_oil_hi: number;
  q_water_lo: number;
  q_water_hi: number;
  q_gas_lo: number;
  q_gas_hi: number;
  rs_lo: number;
  rs_hi: number;
  bo_lo: number;
  bo_hi: number;
  bg_lo: number;
  bg_hi: number;
  rho_lo: number;
  rho_hi: number;
  gradient_lo: number;
  gradient_hi: number;
  // Bomba
  pump_model: string;
  head_per_stage: number;
  efficiency: number;
  det_factor: number;
  head_effective: number;
  hp_per_stage_w: number;
  psi_per_stage: number;
  stages_exact: number;
  stages: number;
  hp: number;
  // Viscosidad (Riling)
  is_viscous: boolean;
  capacity_factor: number;
  head_factor: number;
  hp_factor: number;
  /** Origen de cada propiedad PVT: "pvt" | "correlacion" | "supuesto". */
  pvt_sources: Record<string, string>;
}

export interface GasIncrementSummary {
  p_intake: number;
  p_discharge: number;
  delta_p: number;
  increment_psi: number;
  n_increments: number;
  target_oil_rate: number;
  target_liquid_rate: number;
  q_mix_intake_bpd: number;
  q_mix_discharge_bpd: number;
  q_mix_max_bpd: number;
  q_mix_min_bpd: number;
  /** Invariante de control: la masa no cambia aunque el volumen sí. */
  mass_rate_lbm_d: number;
  total_stages: number;
  total_stages_exact: number;
  /** Suma de redondear cada incremento: la convención del cálculo a mano. */
  total_stages_longhand: number;
  total_hp: number;
  pump_model: string;
  pump_manufacturer: string;
  pump_series: string;
  pump_setting_depth: number;
  pump_intake_temp_f: number;
  pvt_source: string;
  gip: number;
}

export interface GasIncrementResponse {
  summary: GasIncrementSummary;
  increments: GasIncrementRow[];
  free_gas_fraction_at_intake: number;
  gas_risk: Record<string, unknown>;
  separator: Record<string, unknown>;
  warnings: string[];
  /** Escalera de incrementos (Brown Fig. 4.56B). Vacío si no se pudo armar. */
  ladder_figure: PlotlyFigure | Record<string, never>;
  /** Qué cuenta hizo el método y con qué números — un tramo entero y los totales. */
  formulas: Formula[];
}

/** Por qué se usó (o no) el método por incrementos. */
export interface GasMethodDecision {
  applies: boolean;
  free_gas_fraction: number;
  threshold: number;
  negligible_reference: number;
  reason: string;
}

export interface GasCompleteDesignRequest extends DesignInputs {
  increment_psi?: number;
  pump_depth?: number | null;
  vent_gas_pct?: number;
  apply_deterioration?: boolean;
  apply_viscosity?: boolean;
  fixed_pump_model?: string | null;
  pvt_table?: PVTTableInput | null;
}

/**
 * Diseño BES completo por incrementos. `design` es el MISMO esquema que
 * devuelve el camino convencional, así que la vista de resultados se reutiliza.
 */
/**
 * Cuánto gas llega realmente a la bomba y si eso la deja funcionar.
 * Las reducciones se aplican sobre la relación gas/líquido, no sobre la
 * fracción: el separador saca gas y deja el líquido.
 */
export interface GasFeasibility {
  viable: boolean;
  /** Gas libre en la admisión, antes de separar. */
  f_intake: number;
  f_after_vent: number;
  /** El que efectivamente entra a la bomba. */
  f_pump: number;
  max_gip: number;
  vent_fraction: number;
  separator_efficiency: number | null;
  separator_model: string | null;
  /** Eficiencia que haría falta; null si ya cumple. */
  required_efficiency: number | null;
  verdict: string;
}

export interface GasCompleteDesignResponse {
  design: DesignResult;
  method: GasMethodDecision;
  feasibility: GasFeasibility;
  increments: GasIncrementRow[];
  summary: GasIncrementSummary;
  /** Σ ΔPᵢ/gradienteᵢ — con este se dimensionó el aparejo. */
  tdh_increment_ft: number;
  /** TDH de tres términos, para auditar la discrepancia entre rutas. */
  tdh_conventional_ft: number;
  /** Bombas descartadas y por qué, en orden de intento. */
  rejected: string[];
  warnings: string[];
  /** Escalera de incrementos (Brown Fig. 4.56B). Vacío si no se pudo armar. */
  ladder_figure: PlotlyFigure | Record<string, never>;
}
