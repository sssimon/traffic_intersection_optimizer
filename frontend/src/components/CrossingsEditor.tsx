import { Button, Card, Input } from "neobrutalistcomponents";
import type { Crossing, IntersectionConfig } from "../types";

interface Props {
  config: IntersectionConfig;
  onChange: (cfg: IntersectionConfig) => void;
}

const newCrossing = (n: number, phaseId: string): Crossing => ({
  id: `X${n}`,
  name: `Cruce ${n}`,
  length_m: 12,
  phase_id: phaseId,
  walk_speed_ms: 1.2,
  walk_interval_s: 7,
  ped_volume_per_h: 0,
});

export function CrossingsEditor({ config, onChange }: Props) {
  const crossings = config.crossings ?? [];
  const phases = config.phases;

  const update = (i: number, patch: Partial<Crossing>) => {
    const copy = [...crossings];
    copy[i] = { ...copy[i], ...patch };
    onChange({ ...config, crossings: copy });
  };

  const add = () => {
    const phaseId = phases[0]?.id ?? "";
    onChange({
      ...config,
      crossings: [...crossings, newCrossing(crossings.length + 1, phaseId)],
    });
  };

  const remove = (i: number) =>
    onChange({ ...config, crossings: crossings.filter((_, j) => j !== i) });

  return (
    <Card>
      <Card.Header>
        <Card.Title>Cruces peatonales (M10)</Card.Title>
        <Card.Description>
          Opcional. Cada cruce recibe Walk durante una fase; la app calcula la
          demora peatonal y verifica el verde mínimo seguro (MUTCD).
        </Card.Description>
      </Card.Header>
      <Card.Content>
        <div className="row" style={{ marginBottom: 10 }}>
          <Button
            variant="secondary"
            size="sm"
            onClick={add}
            disabled={phases.length === 0}
          >
            + Cruce
          </Button>
          {phases.length === 0 && (
            <span className="desc" style={{ marginLeft: 8 }}>
              Define al menos una fase primero.
            </span>
          )}
        </div>

        {crossings.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Nombre</th>
                <th className="right">Long. (m)</th>
                <th>Fase (Walk)</th>
                <th className="right">Vel. (m/s)</th>
                <th className="right">Walk (s)</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {crossings.map((c, i) => (
                <tr key={i}>
                  <td>
                    <Input size="sm" value={c.id}
                      onChange={(e) => update(i, { id: e.target.value })}
                      style={{ width: 70 }} />
                  </td>
                  <td>
                    <Input size="sm" value={c.name}
                      onChange={(e) => update(i, { name: e.target.value })}
                      style={{ width: 130 }} />
                  </td>
                  <td>
                    <Input size="sm" type="number" min={1} max={60} value={c.length_m}
                      onChange={(e) => update(i, { length_m: parseFloat(e.target.value) || 0 })}
                      style={{ width: 75 }} />
                  </td>
                  <td>
                    <select
                      value={c.phase_id}
                      onChange={(e) => update(i, { phase_id: e.target.value })}
                    >
                      {phases.map((ph) => (
                        <option key={ph.id} value={ph.id}>
                          {ph.id} · {ph.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <Input size="sm" type="number" min={0.8} max={1.8} step={0.1}
                      value={c.walk_speed_ms}
                      onChange={(e) => update(i, { walk_speed_ms: parseFloat(e.target.value) || 1.2 })}
                      style={{ width: 70 }} />
                  </td>
                  <td>
                    <Input size="sm" type="number" min={4} max={15} value={c.walk_interval_s}
                      onChange={(e) => update(i, { walk_interval_s: parseFloat(e.target.value) || 7 })}
                      style={{ width: 70 }} />
                  </td>
                  <td>
                    <Button variant="ghost" size="sm" onClick={() => remove(i)}>
                      ✕
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card.Content>
    </Card>
  );
}
