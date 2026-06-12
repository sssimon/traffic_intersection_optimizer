import type {
  IntersectionAnalysis,
  IntersectionConfig,
  ScenarioComparison,
  SignalPlan,
  SimulationResult,
  TWSCAnalysis,
} from "./types";

const BASE = "/api";

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function fetchSample(): Promise<IntersectionConfig> {
  const r = await fetch(`${BASE}/sample`);
  if (!r.ok) throw new Error(`sample: ${r.status}`);
  return r.json();
}

export type OptimizeMethod = "webster" | "delay_min";

export const optimize = (cfg: IntersectionConfig, method: OptimizeMethod = "webster") =>
  post<SignalPlan>(`/optimize?method=${method}`, cfg);

export const analyze = (cfg: IntersectionConfig, method: OptimizeMethod = "webster") =>
  post<IntersectionAnalysis>(`/analyze?method=${method}`, cfg);

export const simulate = (cfg: IntersectionConfig, opts: {
  signal_plan?: SignalPlan;
  duration_s?: number;
  seed?: number;
  replications?: number;
}) =>
  post<SimulationResult>("/simulate", {
    config: cfg,
    signal_plan: opts.signal_plan,
    duration_s: opts.duration_s ?? 900,
    seed: opts.seed ?? 42,
    time_step_s: 1.0,
    replications: opts.replications ?? 20,
  });

export const runScenarios = (
  cfg: IntersectionConfig,
  multipliers: { name: string; factor: number }[],
) =>
  post<ScenarioComparison>("/scenarios", {
    config: cfg,
    multipliers,
    use_optimized_timing: true,
  });

export const analyzeTwsc = (cfg: IntersectionConfig, majorApproachIds: string[]) =>
  post<TWSCAnalysis>("/analyze-twsc", {
    config: cfg,
    major_approach_ids: majorApproachIds,
  });
