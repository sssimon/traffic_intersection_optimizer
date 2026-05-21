import { Card, Input } from "neobrutalistcomponents";
import type { Demand, IntersectionConfig } from "../types";

interface Props {
  config: IntersectionConfig;
  onChange: (c: IntersectionConfig) => void;
}

export function DemandTable({ config, onChange }: Props) {
  const allLgs = config.approaches.flatMap((a) =>
    a.lane_groups.map((lg) => ({ approach: a.name, lg })),
  );

  const demandFor = (lgId: string): Demand | undefined =>
    config.demand.find((d) => d.lane_group_id === lgId);

  const upsert = (lgId: string, patch: Partial<Demand>) => {
    const existing = demandFor(lgId);
    const next: Demand = {
      lane_group_id: lgId,
      volume: existing?.volume ?? 0,
      pcu_factor: existing?.pcu_factor ?? 1.0,
      ...patch,
    };
    const others = config.demand.filter((d) => d.lane_group_id !== lgId);
    onChange({ ...config, demand: [...others, next] });
  };

  return (
    <Card>
      <Card.Header>
        <Card.Title>Demanda</Card.Title>
        <Card.Description>
          Volumen horario por grupo en hora pico (veh/h)
        </Card.Description>
      </Card.Header>
      <Card.Content>
        <table>
          <thead>
            <tr>
              <th>Acceso</th>
              <th>Grupo</th>
              <th>Mov.</th>
              <th className="right">Carriles</th>
              <th className="right">Demanda (veh/h)</th>
              <th className="right">PCU</th>
            </tr>
          </thead>
          <tbody>
            {allLgs.map(({ approach, lg }) => {
              const d = demandFor(lg.id);
              return (
                <tr key={lg.id}>
                  <td>{approach}</td>
                  <td>
                    <span className="code">{lg.id}</span>
                  </td>
                  <td>{lg.movement}</td>
                  <td className="right">{lg.lanes}</td>
                  <td className="right">
                    <Input
                      size="sm"
                      type="number"
                      min={0}
                      step={10}
                      value={d?.volume ?? 0}
                      onChange={(e) =>
                        upsert(lg.id, { volume: parseFloat(e.target.value) || 0 })
                      }
                      style={{ width: 110 }}
                    />
                  </td>
                  <td className="right">
                    <Input
                      size="sm"
                      type="number"
                      min={1}
                      max={3}
                      step={0.05}
                      value={d?.pcu_factor ?? 1.0}
                      onChange={(e) =>
                        upsert(lg.id, {
                          pcu_factor: parseFloat(e.target.value) || 1.0,
                        })
                      }
                      style={{ width: 90 }}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card.Content>
    </Card>
  );
}
