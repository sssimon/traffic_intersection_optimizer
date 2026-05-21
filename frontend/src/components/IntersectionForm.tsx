import { useState } from "react";
import { Button, Card, Input } from "neobrutalistcomponents";
import type {
  Approach,
  IntersectionConfig,
  LaneGroup,
  MovementType,
  Phase,
} from "../types";

interface Props {
  config: IntersectionConfig;
  onChange: (c: IntersectionConfig) => void;
}

const movementOptions: MovementType[] = ["left", "through", "right"];

export function IntersectionForm({ config, onChange }: Props) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const updateApproach = (idx: number, ap: Approach) => {
    const copy = { ...config, approaches: [...config.approaches] };
    copy.approaches[idx] = ap;
    onChange(copy);
  };

  const addApproach = () => {
    const id = `A${config.approaches.length + 1}`;
    onChange({
      ...config,
      approaches: [
        ...config.approaches,
        {
          id,
          name: `Acceso ${id}`,
          lane_groups: [defaultLaneGroup(`${id}-T`, "through")],
        },
      ],
    });
  };

  const removeApproach = (idx: number) => {
    const removed = config.approaches[idx];
    const removedIds = new Set(removed.lane_groups.map((lg) => lg.id));
    onChange({
      ...config,
      approaches: config.approaches.filter((_, i) => i !== idx),
      demand: config.demand.filter((d) => !removedIds.has(d.lane_group_id)),
      phases: config.phases.map((ph) => ({
        ...ph,
        lane_group_ids: ph.lane_group_ids.filter((id) => !removedIds.has(id)),
      })),
    });
  };

  const addLaneGroup = (apIdx: number) => {
    const ap = config.approaches[apIdx];
    const newLg = defaultLaneGroup(
      `${ap.id}-LG${ap.lane_groups.length + 1}`,
      "through",
    );
    updateApproach(apIdx, { ...ap, lane_groups: [...ap.lane_groups, newLg] });
  };

  const updateLaneGroup = (apIdx: number, lgIdx: number, lg: LaneGroup) => {
    const ap = config.approaches[apIdx];
    const groups = [...ap.lane_groups];
    groups[lgIdx] = lg;
    updateApproach(apIdx, { ...ap, lane_groups: groups });
  };

  const removeLaneGroup = (apIdx: number, lgIdx: number) => {
    const ap = config.approaches[apIdx];
    const removed = ap.lane_groups[lgIdx];
    onChange({
      ...config,
      approaches: config.approaches.map((a, i) =>
        i === apIdx
          ? { ...a, lane_groups: a.lane_groups.filter((_, j) => j !== lgIdx) }
          : a,
      ),
      demand: config.demand.filter((d) => d.lane_group_id !== removed.id),
      phases: config.phases.map((ph) => ({
        ...ph,
        lane_group_ids: ph.lane_group_ids.filter((id) => id !== removed.id),
      })),
    });
  };

  return (
    <Card>
      <Card.Header>
        <Card.Title>Geometría de la intersección</Card.Title>
        <Card.Description>
          Cualquier número de accesos · cada uno con sus grupos de carriles
        </Card.Description>
      </Card.Header>
      <Card.Content>
        <div className="row" style={{ marginBottom: 16 }}>
          <Input
            label="Nombre"
            size="sm"
            value={config.name}
            style={{ minWidth: 260 }}
            onChange={(e) => onChange({ ...config, name: e.target.value })}
          />
          <Input
            label="PHF"
            size="sm"
            type="number"
            step={0.01}
            min={0.7}
            max={1.0}
            value={config.peak_hour_factor}
            onChange={(e) =>
              onChange({
                ...config,
                peak_hour_factor: parseFloat(e.target.value) || 0.92,
              })
            }
            style={{ width: 90 }}
          />
          <div style={{ marginLeft: "auto" }}>
            <Button variant="primary" size="sm" onClick={addApproach}>
              + Acceso
            </Button>
          </div>
        </div>

        {config.approaches.map((ap, apIdx) => {
          const isCollapsed = collapsed[ap.id];
          return (
            <div key={ap.id} style={{ marginTop: 16 }}>
              <div className="section-rule">
                Acceso {ap.id} · {ap.name}
              </div>
              <div className="row" style={{ marginBottom: 8 }}>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    setCollapsed({ ...collapsed, [ap.id]: !isCollapsed })
                  }
                >
                  {isCollapsed ? "▸" : "▾"}
                </Button>
                <Input
                  size="sm"
                  value={ap.id}
                  onChange={(e) =>
                    updateApproach(apIdx, { ...ap, id: e.target.value })
                  }
                  style={{ width: 80 }}
                />
                <Input
                  size="sm"
                  value={ap.name}
                  onChange={(e) =>
                    updateApproach(apIdx, { ...ap, name: e.target.value })
                  }
                  style={{ width: 200 }}
                />
                <span style={{ color: "var(--muted)", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.15em" }}>
                  {ap.lane_groups.length} grupo(s)
                </span>
                <div style={{ marginLeft: "auto" }}>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => removeApproach(apIdx)}
                  >
                    Eliminar acceso
                  </Button>
                </div>
              </div>

              {!isCollapsed && (
                <>
                  <table>
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Movimiento</th>
                        <th>Carriles</th>
                        <th>Sat. (veh/h/c)</th>
                        <th>Compartido</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {ap.lane_groups.map((lg, lgIdx) => (
                        <tr key={lg.id}>
                          <td>
                            <Input
                              size="sm"
                              value={lg.id}
                              onChange={(e) =>
                                updateLaneGroup(apIdx, lgIdx, {
                                  ...lg,
                                  id: e.target.value,
                                })
                              }
                              style={{ width: 100 }}
                            />
                          </td>
                          <td>
                            <select
                              value={lg.movement}
                              onChange={(e) =>
                                updateLaneGroup(apIdx, lgIdx, {
                                  ...lg,
                                  movement: e.target.value as MovementType,
                                })
                              }
                            >
                              {movementOptions.map((m) => (
                                <option key={m} value={m}>
                                  {m}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td>
                            <Input
                              size="sm"
                              type="number"
                              min={1}
                              max={8}
                              value={lg.lanes}
                              onChange={(e) =>
                                updateLaneGroup(apIdx, lgIdx, {
                                  ...lg,
                                  lanes: parseInt(e.target.value) || 1,
                                })
                              }
                              style={{ width: 80 }}
                            />
                          </td>
                          <td>
                            <Input
                              size="sm"
                              type="number"
                              step={50}
                              value={lg.saturation_flow_per_lane}
                              onChange={(e) =>
                                updateLaneGroup(apIdx, lgIdx, {
                                  ...lg,
                                  saturation_flow_per_lane:
                                    parseFloat(e.target.value) || 1900,
                                })
                              }
                              style={{ width: 110 }}
                            />
                          </td>
                          <td>
                            <input
                              type="checkbox"
                              checked={lg.shared_with_through}
                              onChange={(e) =>
                                updateLaneGroup(apIdx, lgIdx, {
                                  ...lg,
                                  shared_with_through: e.target.checked,
                                })
                              }
                            />
                          </td>
                          <td>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => removeLaneGroup(apIdx, lgIdx)}
                            >
                              ✕
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div style={{ marginTop: 12 }}>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => addLaneGroup(apIdx)}
                    >
                      + Grupo de carriles
                    </Button>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </Card.Content>
    </Card>
  );
}

function defaultLaneGroup(id: string, mv: MovementType): LaneGroup {
  return {
    id,
    movement: mv,
    lanes: 1,
    saturation_flow_per_lane: 1900,
    shared_with_through: false,
  };
}

export function PhaseEditor({
  config,
  onChange,
}: {
  config: IntersectionConfig;
  onChange: (c: IntersectionConfig) => void;
}) {
  const allLgIds = config.approaches.flatMap((a) =>
    a.lane_groups.map((lg) => lg.id),
  );

  const updatePhase = (idx: number, ph: Phase) => {
    const copy = [...config.phases];
    copy[idx] = ph;
    onChange({ ...config, phases: copy });
  };

  const addPhase = () => {
    onChange({
      ...config,
      phases: [
        ...config.phases,
        {
          id: `P${config.phases.length + 1}`,
          name: `Fase ${config.phases.length + 1}`,
          lane_group_ids: [],
          min_green: 7,
          max_green: 60,
          yellow: 3,
          all_red: 1,
        },
      ],
    });
  };

  const removePhase = (idx: number) => {
    onChange({ ...config, phases: config.phases.filter((_, i) => i !== idx) });
  };

  const toggleLg = (phaseIdx: number, lgId: string) => {
    const ph = config.phases[phaseIdx];
    const has = ph.lane_group_ids.includes(lgId);
    updatePhase(phaseIdx, {
      ...ph,
      lane_group_ids: has
        ? ph.lane_group_ids.filter((x) => x !== lgId)
        : [...ph.lane_group_ids, lgId],
    });
  };

  return (
    <Card>
      <Card.Header>
        <Card.Title>Fases del semáforo</Card.Title>
        <Card.Description>
          Cada fase = combinación de grupos con verde simultáneo
        </Card.Description>
      </Card.Header>
      <Card.Content>
        <Button variant="primary" size="sm" onClick={addPhase}>
          + Fase
        </Button>

        {config.phases.map((ph, idx) => (
          <div key={ph.id} style={{ marginTop: 20 }}>
            <div className="section-rule">{ph.id} · {ph.name}</div>
            <div className="row">
              <Input
                label="ID"
                size="sm"
                value={ph.id}
                onChange={(e) =>
                  updatePhase(idx, { ...ph, id: e.target.value })
                }
                style={{ width: 80 }}
              />
              <Input
                label="Nombre"
                size="sm"
                value={ph.name}
                onChange={(e) =>
                  updatePhase(idx, { ...ph, name: e.target.value })
                }
                style={{ width: 200 }}
              />
              <Input
                label="Min g"
                size="sm"
                type="number"
                value={ph.min_green}
                onChange={(e) =>
                  updatePhase(idx, {
                    ...ph,
                    min_green: parseFloat(e.target.value) || 7,
                  })
                }
                style={{ width: 80 }}
              />
              <Input
                label="Max g"
                size="sm"
                type="number"
                value={ph.max_green}
                onChange={(e) =>
                  updatePhase(idx, {
                    ...ph,
                    max_green: parseFloat(e.target.value) || 60,
                  })
                }
                style={{ width: 80 }}
              />
              <Input
                label="Y"
                size="sm"
                type="number"
                step={0.5}
                value={ph.yellow}
                onChange={(e) =>
                  updatePhase(idx, {
                    ...ph,
                    yellow: parseFloat(e.target.value) || 3,
                  })
                }
                style={{ width: 70 }}
              />
              <Input
                label="AR"
                size="sm"
                type="number"
                step={0.5}
                value={ph.all_red}
                onChange={(e) =>
                  updatePhase(idx, {
                    ...ph,
                    all_red: parseFloat(e.target.value) || 1,
                  })
                }
                style={{ width: 70 }}
              />
              <div style={{ marginLeft: "auto", alignSelf: "flex-end" }}>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => removePhase(idx)}
                >
                  Eliminar
                </Button>
              </div>
            </div>
            <div className="row" style={{ marginTop: 12, flexWrap: "wrap" }}>
              {allLgIds.map((id) => (
                <label key={id} className="inline">
                  <input
                    type="checkbox"
                    checked={ph.lane_group_ids.includes(id)}
                    onChange={() => toggleLg(idx, id)}
                  />
                  <span className="code">{id}</span>
                </label>
              ))}
            </div>
          </div>
        ))}
      </Card.Content>
    </Card>
  );
}
