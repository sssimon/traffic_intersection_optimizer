import { useState } from "react";
import { Button, Card, Input } from "neobrutalistcomponents";
import { runScenarios } from "../api";
import type {
  IntersectionConfig,
  ScenarioComparison as Comparison,
} from "../types";

interface Props {
  config: IntersectionConfig;
}

interface Row {
  name: string;
  factor: number;
}

const DEFAULTS: Row[] = [
  { name: "Valle (60%)", factor: 0.6 },
  { name: "Actual", factor: 1.0 },
  { name: "+15% (crecimiento)", factor: 1.15 },
  { name: "Hora pico extrema", factor: 1.3 },
];

export function ScenarioComparison({ config }: Props) {
  const [rows, setRows] = useState<Row[]>(DEFAULTS);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateRow = (i: number, r: Row) => {
    const copy = [...rows];
    copy[i] = r;
    setRows(copy);
  };

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await runScenarios(config, rows);
      setComparison(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Card>
        <Card.Header>
          <Card.Title>Comparación de escenarios</Card.Title>
          <Card.Description>
            Multiplicadores de demanda · reoptimización por escenario
          </Card.Description>
        </Card.Header>
        <Card.Content>
          <table>
            <thead>
              <tr>
                <th>Escenario</th>
                <th>Factor</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td>
                    <Input
                      size="sm"
                      value={r.name}
                      onChange={(e) =>
                        updateRow(i, { ...r, name: e.target.value })
                      }
                      style={{ width: 240 }}
                    />
                  </td>
                  <td>
                    <Input
                      size="sm"
                      type="number"
                      step={0.05}
                      min={0.1}
                      max={3}
                      value={r.factor}
                      onChange={(e) =>
                        updateRow(i, {
                          ...r,
                          factor: parseFloat(e.target.value) || 1,
                        })
                      }
                      style={{ width: 100 }}
                    />
                  </td>
                  <td>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setRows(rows.filter((_, j) => j !== i))}
                    >
                      ✕
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="row" style={{ marginTop: 16 }}>
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                setRows([
                  ...rows,
                  {
                    name: `Escenario ${rows.length + 1}`,
                    factor: 1.0,
                  },
                ])
              }
            >
              + Escenario
            </Button>
            <Button
              variant="primary"
              size="sm"
              loading={loading}
              onClick={run}
            >
              Comparar escenarios
            </Button>
          </div>

          {error && (
            <div className="error" style={{ marginTop: 16 }}>
              {error}
            </div>
          )}
        </Card.Content>
      </Card>

      {comparison && (
        <>
          <Card>
            <Card.Header>
              <Card.Title>Resultados</Card.Title>
              <Card.Description>
                Demora · saturación · LOS por escenario
              </Card.Description>
            </Card.Header>
            <Card.Content>
              <table>
                <thead>
                  <tr>
                    <th>Escenario</th>
                    <th className="right">Factor</th>
                    <th className="right">Ciclo (s)</th>
                    <th className="right">Demora media</th>
                    <th className="right">v/c máx</th>
                    <th>LOS</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.scenarios.map((s) => (
                    <tr key={s.name}>
                      <td>{s.name}</td>
                      <td className="right">{s.factor.toFixed(2)}×</td>
                      <td className="right">
                        {s.analysis.signal_plan.cycle_length.toFixed(0)}
                      </td>
                      <td className="right">
                        {s.analysis.avg_delay_s.toFixed(0)} s
                      </td>
                      <td
                        className="right"
                        style={{
                          color:
                            s.analysis.overall_v_c > 0.9
                              ? "var(--oxblood)"
                              : undefined,
                          fontWeight:
                            s.analysis.overall_v_c > 0.9 ? 600 : undefined,
                        }}
                      >
                        {s.analysis.overall_v_c.toFixed(2)}
                      </td>
                      <td>
                        <span
                          className={`los-badge los-${s.analysis.overall_los}`}
                        >
                          {s.analysis.overall_los}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card.Content>
          </Card>

          <Card variant="elevated">
            <Card.Header>
              <Card.Title>Estrategia recomendada</Card.Title>
              <Card.Description>
                Basada en el peor escenario evaluado
              </Card.Description>
            </Card.Header>
            <Card.Content>
              <div
                style={{
                  fontSize: 16,
                  fontWeight: 600,
                  borderLeft: "4px solid var(--oxblood)",
                  paddingLeft: 12,
                  marginBottom: 12,
                }}
              >
                {comparison.recommended_strategy}
              </div>
              <ul className="compact">
                {comparison.rationale.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </Card.Content>
          </Card>
        </>
      )}
    </>
  );
}
