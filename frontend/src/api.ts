import type {
  CompareControlsResult,
  DemandMultiplier,
  FieldCountResult,
  IntersectionAnalysis,
  IntersectionConfig,
  MovementCounts,
  OsmImportResult,
  RunDetail,
  RunSummary,
  ScenarioComparison,
  SignalPlan,
  SimulationResult,
  TWSCAnalysis,
  UncertaintyResult,
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

export const analyze = (
  cfg: IntersectionConfig,
  method: OptimizeMethod = "webster",
  audit = false,
) =>
  post<IntersectionAnalysis>(
    `/analyze?method=${method}${audit ? "&audit=true" : ""}`,
    cfg,
  );

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
  multipliers: DemandMultiplier[],
  method: OptimizeMethod = "delay_min",
) =>
  post<ScenarioComparison>("/scenarios", {
    config: cfg,
    multipliers,
    use_optimized_timing: true,
    method,
  });

export const analyzeTwsc = (cfg: IntersectionConfig, majorApproachIds: string[]) =>
  post<TWSCAnalysis>("/analyze-twsc", {
    config: cfg,
    major_approach_ids: majorApproachIds,
  });

export const compareControls = (
  cfg: IntersectionConfig,
  majorApproachIds: string[],
) =>
  post<CompareControlsResult>("/compare-controls", {
    config: cfg,
    major_approach_ids: majorApproachIds,
  });

export const runUncertainty = (
  cfg: IntersectionConfig,
  opts: { volumeCv: number; samples?: number; method?: OptimizeMethod },
) =>
  post<UncertaintyResult>("/uncertainty", {
    config: cfg,
    volume_cv: opts.volumeCv,
    samples: opts.samples ?? 1000,
    method: opts.method ?? "delay_min",
  });

export const processFieldCount = (
  intervalLabels: string[],
  counts: Record<string, MovementCounts>,
) =>
  post<FieldCountResult>("/field-count", {
    interval_labels: intervalLabels,
    counts,
  });

export const importOsm = (latitude: number, longitude: number, radiusM = 60) =>
  post<OsmImportResult>("/osm-import", {
    latitude,
    longitude,
    radius_m: radiusM,
  });

export const saveRun = (
  name: string,
  cfg: IntersectionConfig,
  method: OptimizeMethod = "delay_min",
) => post<RunSummary>("/runs", { name, config: cfg, method });

export async function listRuns(): Promise<RunSummary[]> {
  const r = await fetch(`${BASE}/runs`);
  if (!r.ok) throw new Error(`runs: ${r.status}`);
  return r.json();
}

export async function getRun(id: number): Promise<RunDetail> {
  const r = await fetch(`${BASE}/runs/${id}`);
  if (!r.ok) throw new Error(`run ${id}: ${r.status}`);
  return r.json();
}

export async function deleteRun(id: number): Promise<void> {
  const r = await fetch(`${BASE}/runs/${id}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`delete run ${id}: ${r.status}`);
}
