import { useState } from "react";
import { Button, Card, Input } from "neobrutalistcomponents";
import { simulate } from "../api";
import type { IntersectionConfig, SimulationResult } from "../types";
import { QueueChart, colorFor } from "./QueueChart";

interface Props {
  config: IntersectionConfig;
}

export function SimulationPanel({ config }: Props) {
  const [duration, setDuration] = useState(900);
  const [seed, setSeed] = useState(42);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await simulate(config, { duration_s: duration, seed });
      setResult(r);
      const top = [...r.movements]
        .sort((a, b) => b.max_queue - a.max_queue)
        .slice(0, 6)
        .map((m) => m.lane_group_id);
      setSelected(new Set(top));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const decimated = (arr: number[], maxPoints = 400): number[] => {
    if (arr.length <= maxPoints) return arr;
    const step = Math.ceil(arr.length / maxPoints);
    const out: number[] = [];
    for (let i = 0; i < arr.length; i += step) out.push(arr[i]);
    return out;
  };

  const series = result
    ? result.movements
        .filter((m) => selected.has(m.lane_group_id))
        .map((m, i) => ({
          label: m.lane_group_id,
          color: colorFor(i),
          values: decimated(m.queue_over_time),
        }))
    : [];

  const timeAxis = result ? decimated(result.time_axis_s) : [];

  return (
    <Card>
      <Card.Header>
        <Card.Title>Simulación de colas</Card.Title>
        <Card.Description>
          Llegadas Poisson · descarga a flujo de saturación durante el verde
        </Card.Description>
      </Card.Header>
      <Card.Content>
        <div className="row" style={{ marginBottom: 16 }}>
          <Input
            label="Duración (s)"
            size="sm"
            type="number"
            min={60}
            max={3600}
            step={60}
            value={duration}
            onChange={(e) => setDuration(parseInt(e.target.value) || 900)}
            style={{ width: 110 }}
          />
          <Input
            label="Semilla"
            size="sm"
            type="number"
            value={seed}
            onChange={(e) => setSeed(parseInt(e.target.value) || 0)}
            style={{ width: 100 }}
          />
          <div style={{ alignSelf: "flex-end", marginLeft: "auto" }}>
            <Button variant="primary" size="sm" loading={loading} onClick={run}>
              Ejecutar simulación
            </Button>
          </div>
        </div>

        {error && <div className="error">{error}</div>}

        {result && (
          <>
            <div className="kpi-grid" style={{ marginBottom: 16 }}>
              <div className="kpi">
                <span className="label">Llegados</span>
                <span className="value">{result.total_arrived}</span>
                <span className="unit">vehículos</span>
              </div>
              <div className="kpi">
                <span className="label">Servidos</span>
                <span className="value">{result.total_served}</span>
                <span className="unit">
                  {result.total_arrived > 0
                    ? `${((result.total_served / result.total_arrived) * 100).toFixed(1)}%`
                    : ""}
                </span>
              </div>
              <div className="kpi">
                <span className="label">Espera media</span>
                <span className="value">{result.avg_wait_all_s.toFixed(1)}</span>
                <span className="unit">s / veh</span>
              </div>
              <div className="kpi">
                <span className="label">Cola máxima</span>
                <span className="value">{result.max_queue_all.toFixed(0)}</span>
                <span className="unit">veh</span>
              </div>
            </div>

            <div className="section-rule">
              Cola por movimiento en el tiempo
            </div>
            <QueueChart series={series} timeAxis={timeAxis} />

            <div className="section-rule">Movimientos a graficar</div>
            <div className="row" style={{ flexWrap: "wrap" }}>
              {result.movements.map((m) => (
                <label key={m.lane_group_id} className="inline">
                  <input
                    type="checkbox"
                    checked={selected.has(m.lane_group_id)}
                    onChange={() => {
                      const next = new Set(selected);
                      if (next.has(m.lane_group_id))
                        next.delete(m.lane_group_id);
                      else next.add(m.lane_group_id);
                      setSelected(next);
                    }}
                  />
                  <span className="code">{m.lane_group_id}</span>
                  <span style={{ color: "var(--muted)", fontSize: 11 }}>
                    máx {m.max_queue.toFixed(0)} · espera{" "}
                    {m.avg_wait_s.toFixed(0)}s
                  </span>
                </label>
              ))}
            </div>
          </>
        )}
      </Card.Content>
    </Card>
  );
}
