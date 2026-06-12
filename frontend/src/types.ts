// Tipos espejo de los modelos Pydantic del backend.

export type MovementType = "left" | "through" | "right";

export interface SaturationFactors {
  lane_width_m?: number | null;
  grade_pct?: number;
  parking_maneuvers_per_h?: number | null;
  bus_stops_per_h?: number;
  cbd?: boolean;
  lane_utilization?: number;
}

export interface LaneGroup {
  id: string;
  movement: MovementType;
  lanes: number;
  saturation_flow_per_lane: number;
  shared_with_through: boolean;
  factors?: SaturationFactors | null;
}

export interface Approach {
  id: string;
  name: string;
  lane_groups: LaneGroup[];
}

export interface Phase {
  id: string;
  name: string;
  lane_group_ids: string[];
  min_green: number;
  max_green: number;
  yellow: number;
  all_red: number;
}

export interface Demand {
  lane_group_id: string;
  volume: number;
  pcu_factor: number;
}

export interface IntersectionConfig {
  name: string;
  approaches: Approach[];
  phases: Phase[];
  demand: Demand[];
  peak_hour_factor: number;
  latitude?: number | null;
  longitude?: number | null;
}

export interface SignalPlan {
  cycle_length: number;
  phase_green: Record<string, number>;
  phase_yellow: Record<string, number>;
  phase_all_red: Record<string, number>;
  total_lost_time: number;
  notes: string[];
}

export type LOS = "A" | "B" | "C" | "D" | "E" | "F";

export interface MovementAnalysis {
  lane_group_id: string;
  phase_id: string;
  demand: number;
  capacity: number;
  v_c_ratio: number;
  avg_delay_s: number;
  back_of_queue_avg_veh: number;
  queue_95th_veh: number;
  los: LOS;
}

export interface AuditStep {
  concept: string;
  formula: string;
  substitution: string;
  value: number;
  units: string;
  source: string;
}

export interface MovementAudit {
  lane_group_id: string;
  phase_id: string;
  steps: AuditStep[];
}

export interface IntersectionAnalysis {
  config_name: string;
  signal_plan: SignalPlan;
  movements: MovementAnalysis[];
  avg_delay_s: number;
  overall_los: LOS;
  overall_v_c: number;
  warnings: string[];
  audit?: MovementAudit[] | null;
}

export interface MovementTrace {
  lane_group_id: string;
  queue_p05: number[];
  queue_p50: number[];
  queue_p95: number[];
  served_total: number;
  arrived_total: number;
  avg_wait_s: number;
  wait_p05: number;
  wait_p95: number;
  max_queue: number;
  max_queue_p95: number;
}

export interface SimulationResult {
  duration_s: number;
  replications: number;
  time_axis_s: number[];
  movements: MovementTrace[];
  avg_wait_all_s: number;
  avg_wait_all_p05: number;
  avg_wait_all_p95: number;
  max_queue_all: number;
  max_queue_all_p95: number;
  total_served: number;
  total_arrived: number;
}

export interface DemandMultiplier {
  name: string;
  factor: number;
  approach_factors?: Record<string, number>;
  movement_factors?: Record<string, number>;
}

export interface ScenarioResult {
  name: string;
  factor: number;
  directional: boolean;
  label: string;
  analysis: IntersectionAnalysis;
}

export interface ScenarioComparison {
  scenarios: ScenarioResult[];
  recommended_strategy: string;
  rationale: string[];
  warnings: string[];
}

// ---- Análisis no semaforizado ----

export interface UnsignalizedMovement {
  lane_group_id: string;
  approach_id: string;
  role: string;
  movement: MovementType;
  demand: number;
  conflicting_flow: number | null;
  capacity: number | null;
  v_c_ratio: number | null;
  avg_delay_s: number;
  los: LOS;
}

export interface TWSCAnalysis {
  config_name: string;
  major_approach_ids: string[];
  movements: UnsignalizedMovement[];
  avg_delay_s: number;
  overall_los: LOS;
  worst_movement: string | null;
  warnings: string[];
}

// ---- Explorador de alternativas de control ----

export interface ControlAlternative {
  id: string;
  kind: "signal" | "twsc";
  name: string;
  avg_delay_s: number;
  overall_los: LOS;
  overall_v_c: number;
  cycle_length: number | null;
  worst_queue_95th_veh: number | null;
  notes: string[];
  signal: IntersectionAnalysis | null;
  twsc: TWSCAnalysis | null;
}

export interface CompareControlsResult {
  alternatives: ControlAlternative[];
  recommended_id: string;
  rationale: string[];
  warnings: string[];
}

// ---- Corredor ----

export interface CorridorIntersectionInput {
  name: string;
  green_s: number;
  distance_to_next_m: number;
  speed_to_next_kmh: number;
  vol_out: number;
  vol_in: number;
  sat_out: number;
  sat_in: number;
}

export interface CorridorIntersectionResult {
  name: string;
  position_m: number;
  offset_s: number;
  green_s: number;
  p_green_out: number | null;
  p_green_in: number | null;
  pf_out: number;
  pf_in: number;
  delay_out_s: number;
  delay_in_s: number;
  delay_isolated_out_s: number;
  delay_isolated_in_s: number;
}

export interface CorridorResult {
  cycle_s: number;
  offsets_optimized: boolean;
  band_out_s: number;
  band_in_s: number;
  efficiency_out: number;
  efficiency_in: number;
  band_out_start_s: number;
  band_in_start_s: number;
  travel_times_s: number[];
  intersections: CorridorIntersectionResult[];
  avg_artery_delay_s: number;
  avg_artery_delay_isolated_s: number;
  warnings: string[];
  notes: string[];
}

// ---- Aforo de campo (15 min) ----

export interface MovementCounts {
  auto?: number[];
  moto?: number[];
  bus?: number[];
  camion?: number[];
}

export interface FieldCountResult {
  peak_hour_label: string;
  expanded: boolean;
  phf: number | null;
  volumes: Record<string, number>;
  pcu_factors: Record<string, number>;
  totals_per_interval: number[];
  warnings: string[];
}

// ---- Importación OSM ----

export interface OsmImportResult {
  config: IntersectionConfig;
  warnings: string[];
}

// ---- Corridas guardadas ----

export interface RunSummary {
  id: number;
  name: string;
  created_at: string;
  intersection_name: string;
  method: string;
  cycle_length: number;
  avg_delay_s: number;
  overall_los: LOS;
  overall_v_c: number;
}

export interface RunDetail extends RunSummary {
  config: IntersectionConfig;
}

// ---- Incertidumbre Monte Carlo ----

export interface MovementSensitivity {
  lane_group_id: string;
  correlation: number;
  cv: number;
}

export interface UncertaintyResult {
  samples: number;
  volume_cv: number;
  method: string;
  signal_plan: SignalPlan;
  base_delay_s: number;
  delay_mean_s: number;
  delay_p05_s: number;
  delay_p50_s: number;
  delay_p95_s: number;
  los_probability: Record<string, number>;
  prob_oversaturated: number;
  sensitivity: MovementSensitivity[];
  notes: string[];
}
