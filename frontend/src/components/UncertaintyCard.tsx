import { useState } from "react";
import { Button, Card } from "neobrutalistcomponents";
import { runUncertainty, type OptimizeMethod } from "../api";
import type { IntersectionConfig, UncertaintyResult } from "../types";

interface Props {
  config: IntersectionConfig;
  method: OptimizeMethod;
}

const CV_PRESETS = [
  { value: 0.15, label: "Aforo de 15 min expandido (CV 15 %)" },
  { value: 0.1, label: "Aforo de 1 hora (CV 10 %)" },
  { value: 0.05, label: "Aforo de varios días (CV 5 %)" },
];

const GRADES = ["A", "B", "C", "D", "E", "F"] as const;

export function UncertaintyCard({ config, method }: Props) {
  const [cv, setCv] = useState(0.1);
  const [result, setResult] = useState<UncertaintyResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      setResult(await runUncertainty(config, { volumeCv: cv, method }));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const mostLikely = result
    ? GRADES.reduce((best, g) =>
        (result.los_probability[g] ?? 0) > (result.los_probability[best] ?? 0)
          ? g
          : best,
      )
    : null;

  return (
    <Card>
      <Card.Header>
        <Card.Title>Incertidumbre del aforo (Monte Carlo)</Card.Title>
        <Card.Description>
          Un conteo corto no justifica una letra única — 1 000 muestras sobre
          los volúmenes
        </Card.Description>
      </Card.Header>
      <Card.Content>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <label className="field">
            Calidad del aforo
            <select
              value={cv}
              onChange={(e) => setCv(parseFloat(e.target.value))}
            >
              {CV_PRESETS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <Button variant="primary" size="sm" loading={loading} onClick={run}>
            Calcular P(LOS)
          </Button>
        </div>

        {error && (
          <div className="error" style={{ marginTop: 12 }}>
            {error}
          </div>
        )}

        {result && (
          <>
            <div className="kpi-grid" style={{ marginTop: 16 }}>
              <div className="kpi">
                <span className="label">Demora mediana</span>
                <span className="value">{result.delay_p50_s.toFixed(0)}</span>
                <span className="unit">
                  s/veh · p5–p95: {result.delay_p05_s.toFixed(0)}–
                  {result.delay_p95_s.toFixed(0)}
                </span>
              </div>
              <div className="kpi">
                <span className="label">LOS más probable</span>
                <span className="value">
                  {mostLikely && (
                    <span className={`los-badge los-${mostLikely}`}>
                      {mostLikely}
                    </span>
                  )}
                </span>
                <span className="unit">
                  P ={" "}
                  {mostLikely
                    ? `${((result.los_probability[mostLikely] ?? 0) * 100).toFixed(0)} %`
                    : "—"}
                </span>
              </div>
              <div className="kpi">
                <span className="label">P(LOS E o peor)</span>
                <span className="value">
                  {(
                    ((result.los_probability["E"] ?? 0) +
                      (result.los_probability["F"] ?? 0)) *
                    100
                  ).toFixed(0)}
                  %
                </span>
                <span className="unit">sobre {result.samples} muestras</span>
              </div>
              <div className="kpi">
                <span className="label">P(sobresaturación)</span>
                <span className="value">
                  {(result.prob_oversaturated * 100).toFixed(0)}%
                </span>
                <span className="unit">X máx &gt; 1</span>
              </div>
            </div>

            <div className="section-rule">Probabilidad de cada LOS</div>
            <div
              style={{
                display: "flex",
                width: "100%",
                height: 34,
                border: "2px solid #0a0a0a",
              }}
            >
              {GRADES.map((g) => {
                const p = result.los_probability[g] ?? 0;
                if (p <= 0) return null;
                return (
                  <div
                    key={g}
                    className={`los-${g}`}
                    title={`LOS ${g}: ${(p * 100).toFixed(1)} %`}
                    style={{
                      width: `${p * 100}%`,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 11,
                      fontWeight: 700,
                      overflow: "hidden",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {p >= 0.08 ? `${g} ${(p * 100).toFixed(0)}%` : ""}
                  </div>
                );
              })}
            </div>

            <div className="section-rule">
              Sensibilidad (¿qué volumen manda?)
            </div>
            {result.sensitivity.slice(0, 6).map((s) => (
              <div
                key={s.lane_group_id}
                className="row"
                style={{ alignItems: "center", gap: 8, marginTop: 4 }}
              >
                <span className="code" style={{ width: 60 }}>
                  {s.lane_group_id}
                </span>
                <div
                  style={{
                    height: 10,
                    width: `${Math.min(100, Math.abs(s.correlation) * 100)}%`,
                    maxWidth: "60%",
                    background:
                      s.correlation >= 0 ? "#8a0f1c" : "#444444",
                  }}
                />
                <span style={{ fontSize: 11, color: "var(--muted)" }}>
                  r = {s.correlation.toFixed(2)}
                </span>
              </div>
            ))}
            <p className="desc" style={{ marginTop: 8, marginBottom: 0 }}>
              Correlación entre el volumen muestreado del movimiento y la
              demora media de la intersección.
            </p>

            {result.notes.map((n, i) => (
              <div key={i} className="note" style={{ marginTop: 8 }}>
                {n}
              </div>
            ))}
          </>
        )}
      </Card.Content>
    </Card>
  );
}
