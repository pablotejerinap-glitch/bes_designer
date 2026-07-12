// Tipos que espejan el contrato de la API (ver backend api/schemas/*).
// Se pueden regenerar desde openapi.json con `npm run gen:api` (openapi-typescript),
// pero estos escritos a mano mantienen el código legible.

export type IPRMethod = "linear" | "vogel" | "fetkovich" | "combined";
export type DriveMechanism =
  | "solution_gas"
  | "water_drive"
  | "gas_cap"
  | "combination";
export type NodalMethod =
  | "hagedorn_brown"
  | "beggs_brill"
  | "duns_ros"
  | "poettmann_carpenter";
export type SensitivityParam =
  | "water_cut"
  | "gor"
  | "static_pressure"
  | "target_flow_rate";

export interface ReservoirInput {
  static_pressure: number;
  bubble_point: number;
  productivity_index: number;
  ipr_method: IPRMethod;
  reservoir_temp: number;
  drive_mechanism: DriveMechanism;
  datum_depth: number;
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
  bottom_hole_temp: number;
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
  preferred_manufacturer: string;
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
  warnings: string[];
  alternatives: string[];
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

export interface Recommendation {
  rank: number;
  score: number;
  metrics: Record<string, number>;
  design: DesignResult;
  rationale: string;
  warnings: string[];
}

export interface DesignResponse {
  recommendations: Recommendation[];
  design_basis: Record<string, number>;
  weights: Record<string, number>;
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
  method?: NodalMethod;
  pr_decline_pct?: number;
  compare_all?: boolean;
  pump_model?: string | null;
  stages?: number | null;
  pump_depth?: number | null;
}

export interface NodalComparisonRow {
  method_key: string;
  method_label: string;
  q_natural: number;
  q_pump: number;
  incremental: number;
  pwf_operating: number;
  pump_efficiency: number;
}

export interface NodalResponse {
  mode: "single" | "compare";
  method: string;
  pr_decline_pct: number;
  static_pressure_eff: number;
  has_pump: boolean;
  metrics: Record<string, number> | null;
  comparison: NodalComparisonRow[] | null;
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
