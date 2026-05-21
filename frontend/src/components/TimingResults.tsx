import { Card } from "neobrutalistcomponents";
import type { IntersectionAnalysis, IntersectionConfig } from "../types";

interface Props {
  analysis: IntersectionAnalysis;
  config: IntersectionConfig;
}

// Swiss palette: ink + oxblood + three neutrals
const PHASE_COLORS = ["#0a0a0a", "#8a0f1c", "#444444", "#888888", "#2a2a2a", "#6b6b6b"];

export function TimingResults({ analysis, config }: Props) {
  const plan = analysis.signal_plan;
  const phases = config.phases;
  const cycle = plan.cycle_length;

  return (
    <>
      <Card>
        <Card.Header>
          <Card.Title>Plan de tiempos (Webster)</Card.Title>
          <Card.Description>
            Ciclo óptimo y distribución por fase
          </Card.Description>
        </Card.Header>
        <Card.Content>
          <div className="kpi-grid">
            <div className="kpi">
              <span className="label">Ciclo</span>
              <span className="value">{plan.cycle_length.toFixed(0)}</span>
              <span className="unit">segundos</span>
            </div>
            <div className="kpi">
              <span className="label">Tiempo perdido</span>
              <span className="value">{plan.total_lost_time.toFixed(0)}</span>
              <span className="unit">s / ciclo</span>
            </div>
            <div className="kpi">
              <span className="label">Demora media</span>
              <span className="value">{analysis.avg_delay_s.toFixed(0)}</span>
              <span className="unit">s / veh</span>
            </div>
            <div className="kpi">
              <span className="label">LOS general</span>
              <span className="value">
                <span className={`los-badge los-${analysis.overall_los}`}>
                  {analysis.overall_los}
                </span>
              </span>
              <span className="unit">
                v/c máx: {analysis.overall_v_c.toFixed(2)}
              </span>
            </div>
          </div>

          <div className="section-rule">Distribución temporal del ciclo</div>
          <div className="bar">
            {phases.map((ph, idx) => {
              const color = PHASE_COLORS[idx % PHASE_COLORS.length];
              const g = plan.phase_green[ph.id] ?? 0;
              const y = plan.phase_yellow[ph.id] ?? 0;
              const ar = plan.phase_all_red[ph.id] ?? 0;
              return (
                <div key={`g-${ph.id}`} style={{ display: "contents" }}>
                  <div
                    style={{
                      background: color,
                      width: `${(g / cycle) * 100}%`,
                    }}
                  >
                    {g >= 3 ? `${ph.id} · ${g.toFixed(0)}S` : ""}
                  </div>
                  <div
                    style={{
                      background: "#f9a825",
                      width: `${(y / cycle) * 100}%`,
                      color: "#0a0a0a",
                    }}
                  />
                  <div
                    style={{
                      background: "#c4c4c4",
                      width: `${(ar / cycle) * 100}%`,
                    }}
                  />
                </div>
              );
            })}
          </div>
          <div className="legend">
            <span><span className="swatch" style={{ background: "#0a0a0a" }} />verde por fase</span>
            <span><span className="swatch" style={{ background: "#f9a825" }} />amarillo</span>
            <span><span className="swatch" style={{ background: "#c4c4c4" }} />todo-rojo</span>
          </div>

          {plan.notes.length > 0 && (
            <div style={{ marginTop: 16 }}>
              {plan.notes.map((n, i) => (
                <div key={i} className="note">
                  {n}
                </div>
              ))}
            </div>
          )}
        </Card.Content>
      </Card>

      <Card>
        <Card.Header>
          <Card.Title>Análisis HCM por movimiento</Card.Title>
          <Card.Description>
            Demora · capacidad · cola 95-percentil · LOS
          </Card.Description>
        </Card.Header>
        <Card.Content>
          <table>
            <thead>
              <tr>
                <th>Grupo</th>
                <th>Fase</th>
                <th className="right">Demanda</th>
                <th className="right">Capacidad</th>
                <th className="right">v/c</th>
                <th className="right">Demora (s)</th>
                <th className="right">Cola 95% (veh)</th>
                <th>LOS</th>
              </tr>
            </thead>
            <tbody>
              {analysis.movements.map((m) => (
                <tr key={m.lane_group_id}>
                  <td>
                    <span className="code">{m.lane_group_id}</span>
                  </td>
                  <td>{m.phase_id}</td>
                  <td className="right">{m.demand.toFixed(0)}</td>
                  <td className="right">{m.capacity.toFixed(0)}</td>
                  <td
                    className="right"
                    style={{
                      color: m.v_c_ratio > 0.9 ? "var(--oxblood)" : undefined,
                      fontWeight: m.v_c_ratio > 0.9 ? 600 : undefined,
                    }}
                  >
                    {m.v_c_ratio.toFixed(2)}
                  </td>
                  <td className="right">{m.avg_delay_s.toFixed(0)}</td>
                  <td className="right">{m.queue_95th_veh.toFixed(1)}</td>
                  <td>
                    <span className={`los-badge los-${m.los}`}>{m.los}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {analysis.warnings.length > 0 && (
            <div style={{ marginTop: 16 }}>
              {analysis.warnings.map((w, i) => (
                <div key={i} className="warning">
                  {w}
                </div>
              ))}
            </div>
          )}
        </Card.Content>
      </Card>
    </>
  );
}
