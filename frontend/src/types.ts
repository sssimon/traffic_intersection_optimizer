// Tipos espejo de los modelos Pydantic del backend.

export type MovementType = "left" | "through" | "right";

export interface LaneGroup {
  id: string;
  movement: MovementType;
  lanes: number;
  saturation_flow_per_lane: number;
  shared_with_through: boolean;
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

export interface IntersectionAnalysis {
  config_name: string;
  signal_plan: SignalPlan;
  movements: MovementAnalysis[];
  avg_delay_s: number;
  overall_los: LOS;
  overall_v_c: number;
  warnings: string[];
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
