import { useState } from "react";
import { Button, Card, Input } from "neobrutalistcomponents";
import { runCorridor } from "../api";
import type {
  CorridorIntersectionInput,
  CorridorResult,
} from "../types";

const DEFAULT_ROWS: CorridorIntersectionInput[] = [
  { name: "Cruce 1", green_s: 42, distance_to_next_m: 320, speed_to_next_kmh: 45, vol_out: 700, vol_in: 650, sat_out: 3400, sat_in: 3400 },
  { name: "Cruce 2", green_s: 48, distance_to_next_m: 280, speed_to_next_kmh: 45, vol_out: 700, vol_in: 650, sat_out: 3400, sat_in: 3400 },
  { name: "Cruce 3", green_s: 42, distance_to_next_m: 0, speed_to_next_kmh: 45, vol_out: 700, vol_in: 650, sat_out: 3400, sat_in: 3400 },
];

function TimeSpaceDiagram({ result }: { result: CorridorResult }) {
  const C = result.cycle_s;
  const ints = result.intersections;
  const tau = result.travel_times_s;
  const tauEnd = tau[tau.length - 1];

  const width = 860;
  const height = 360;
  const padL = 110;
  const padR = 14;
  const padT = 16;
  const padB = 34;

  const tMax = 2 * C;
  const maxPos = Math.max(1, ...ints.map((i) => i.position_m));
  const px = (t: number) => padL + (t / tMax) * (width - padL - padR);
  const py = (pos: number) =>
    height - padB - (pos / maxPos) * (height - padT - padB);

  const bandPolygon = (
    startAt: (idx: number) => number,
    bandWidth: number,
    shift: number,
  ): string => {
    const lead = ints.map((it, i) => `${px(startAt(i) + shift)},${py(it.position_m)}`);
    const trail = [...ints]
      .map((it, i) => `${px(startAt(i) + shift + bandWidth)},${py(it.position_m)}`)
      .reverse();
    return [...lead, ...trail].join(" ");
  };

  const ticks = Array.from({ length: Math.floor(tMax / 30) + 1 }, (_, i) => i * 30);

  return (
    <svg
      className="chart"
      viewBox={`0 0 ${width} ${height}`}
      style={{ width: "100%", height }}
    >
      {/* ejes */}
      <line x1={padL} x2={width - padR} y1={height - padB} y2={height - padB} stroke="#0a0a0a" />
      {ticks.map((t) => (
        <g key={t}>
          <line x1={px(t)} x2={px(t)} y1={padT} y2={height - padB} stroke="#eee" />
          <text x={px(t)} y={height - 14} fontSize="10" textAnchor="middle"
            fontFamily="JetBrains Mono, monospace">{t}s</text>
        </g>
      ))}

      {/* bandas (ida oxblood, vuelta gris) — copias en ±C para cubrir 2C */}
      {result.band_out_s > 0 &&
        [-C, 0, C].map((shift) => (
          <polygon
            key={`out${shift}`}
            points={bandPolygon((i) => result.band_out_start_s + tau[i], result.band_out_s, shift)}
            fill="rgba(138,15,28,0.16)"
            stroke="rgba(138,15,28,0.45)"
            strokeWidth={1}
          />
        ))}
      {result.band_in_s > 0 &&
        [-C, 0, C].map((shift) => (
          <polygon
            key={`in${shift}`}
            points={bandPolygon((i) => result.band_in_start_s + (tauEnd - tau[i]), result.band_in_s, shift)}
            fill="rgba(60,60,60,0.14)"
            stroke="rgba(60,60,60,0.4)"
            strokeWidth={1}
          />
        ))}

      {/* líneas de cada intersección: rojo de fondo + verdes por ciclo */}
      {ints.map((it) => (
        <g key={it.name}>
          <line
            x1={padL}
            x2={width - padR}
            y1={py(it.position_m)}
            y2={py(it.position_m)}
            stroke="#d9b8bc"
            strokeWidth={5}
          />
          {[0, 1, 2].map((k) => {
            const start = (it.offset_s % C) + k * C - C;
            const t0 = Math.max(0, start);
            const t1 = Math.min(tMax, start + it.green_s);
            if (t1 <= t0) return null;
            return (
              <line
                key={k}
                x1={px(t0)}
                x2={px(t1)}
                y1={py(it.position_m)}
                y2={py(it.position_m)}
                stroke="#1d8a3a"
                strokeWidth={6}
              >
                <title>{`${it.name}: verde ${it.green_s}s, offset ${it.offset_s}s`}</title>
              </line>
            );
          })}
          <text
            x={6}
            y={py(it.position_m) + 4}
            fontSize="11"
            fontFamily="JetBrains Mono, monospace"
          >
            {it.name} · {it.position_m.toFixed(0)}m
          </text>
        </g>
      ))}
    </svg>
  );
}

export function CorridorPanel() {
  const [rows, setRows] = useState<CorridorIntersectionInput[]>(DEFAULT_ROWS);
  const [cycle, setCycle] = useState(90);
  const [optimize, setOptimize] = useState(true);
  const [offsets, setOffsets] = useState<string[]>(["0", "0", "0"]);
  const [result, setResult] = useState<CorridorResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateRow = (i: number, patch: Partial<CorridorIntersectionInput>) => {
    const copy = [...rows];
    copy[i] = { ...copy[i], ...patch };
    setRows(copy);
  };

  const addRow = () => {
    setRows([
      ...rows,
      { name: `Cruce ${rows.length + 1}`, green_s: 42, distance_to_next_m: 0,
        speed_to_next_kmh: 45, vol_out: 600, vol_in: 600, sat_out: 3400, sat_in: 3400 },
    ]);
    setOffsets([...offsets, "0"]);
  };

  const removeRow = (i: number) => {
    setRows(rows.filter((_, j) => j !== i));
    setOffsets(offsets.filter((_, j) => j !== i));
  };

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const manual = optimize
        ? undefined
        : rows.map((_, i) => parseFloat(offsets[i] ?? "0") || 0);
      setResult(
        await runCorridor(cycle, rows, { offsets: manual, optimize }),
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const improvement = result
    ? result.avg_artery_delay_isolated_s - result.avg_artery_delay_s
    : 0;

  return (
    <>
      <Card>
        <Card.Header>
          <Card.Title>Corredor — onda verde</Card.Title>
          <Card.Description>
            Ciclo común · offsets optimizados (MAXBAND simplificado) · PF de
            progresión real sobre el modelo de demora
          </Card.Description>
        </Card.Header>
        <Card.Content>
          <div className="row" style={{ alignItems: "flex-end", flexWrap: "wrap" }}>
            <Input
              label="Ciclo común (s)"
              size="sm"
              type="number"
              min={40}
              max={180}
              value={cycle}
              onChange={(e) => setCycle(parseFloat(e.target.value) || 90)}
              style={{ width: 120 }}
            />
            <label className="inline" style={{ alignSelf: "center" }}>
              <input
                type="checkbox"
                checked={optimize}
                onChange={(e) => setOptimize(e.target.checked)}
              />
              Optimizar offsets
            </label>
            <div style={{ marginLeft: "auto" }}>
              <Button variant="secondary" size="sm" onClick={addRow}>
                + Intersección
              </Button>
            </div>
          </div>

          <table style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>Nombre</th>
                <th className="right">Verde art. (s)</th>
                <th className="right">Dist. → sig. (m)</th>
                <th className="right">Vel. (km/h)</th>
                <th className="right">Vol. ida</th>
                <th className="right">Vol. vuelta</th>
                {!optimize && <th className="right">Offset (s)</th>}
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td>
                    <Input size="sm" value={r.name}
                      onChange={(e) => updateRow(i, { name: e.target.value })}
                      style={{ width: 110 }} />
                  </td>
                  <td>
                    <Input size="sm" type="number" min={5} value={r.green_s}
                      onChange={(e) => updateRow(i, { green_s: parseFloat(e.target.value) || 30 })}
                      style={{ width: 80 }} />
                  </td>
                  <td>
                    <Input size="sm" type="number" min={0} step={10}
                      value={r.distance_to_next_m}
                      disabled={i === rows.length - 1}
                      onChange={(e) => updateRow(i, { distance_to_next_m: parseFloat(e.target.value) || 0 })}
                      style={{ width: 95 }} />
                  </td>
                  <td>
                    <Input size="sm" type="number" min={5} max={120}
                      value={r.speed_to_next_kmh}
                      disabled={i === rows.length - 1}
                      onChange={(e) => updateRow(i, { speed_to_next_kmh: parseFloat(e.target.value) || 40 })}
                      style={{ width: 80 }} />
                  </td>
                  <td>
                    <Input size="sm" type="number" min={0} step={50} value={r.vol_out}
                      onChange={(e) => updateRow(i, { vol_out: parseFloat(e.target.value) || 0 })}
                      style={{ width: 85 }} />
                  </td>
                  <td>
                    <Input size="sm" type="number" min={0} step={50} value={r.vol_in}
                      onChange={(e) => updateRow(i, { vol_in: parseFloat(e.target.value) || 0 })}
                      style={{ width: 85 }} />
                  </td>
                  {!optimize && (
                    <td>
                      <Input size="sm" type="number" min={0} value={offsets[i] ?? "0"}
                        onChange={(e) => {
                          const copy = [...offsets];
                          copy[i] = e.target.value;
                          setOffsets(copy);
                        }}
                        style={{ width: 80 }} />
                    </td>
                  )}
                  <td>
                    <Button variant="ghost" size="sm" onClick={() => removeRow(i)}>
                      ✕
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="row" style={{ marginTop: 12 }}>
            <Button variant="primary" size="sm" loading={loading} onClick={run}>
              Calcular corredor
            </Button>
          </div>

          {error && (
            <div className="error" style={{ marginTop: 12 }}>
              {error}
            </div>
          )}
        </Card.Content>
      </Card>

      {result && (
        <>
          <Card variant="elevated">
            <Card.Header>
              <Card.Title>Onda verde</Card.Title>
              <Card.Description>
                Diagrama tiempo-espacio · banda ida (vino) y vuelta (gris)
              </Card.Description>
            </Card.Header>
            <Card.Content>
              <div className="kpi-grid" style={{ marginBottom: 12 }}>
                <div className="kpi">
                  <span className="label">Banda ida</span>
                  <span className="value">{result.band_out_s.toFixed(0)}</span>
                  <span className="unit">
                    s · eficiencia {(result.efficiency_out * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="kpi">
                  <span className="label">Banda vuelta</span>
                  <span className="value">{result.band_in_s.toFixed(0)}</span>
                  <span className="unit">
                    s · eficiencia {(result.efficiency_in * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="kpi">
                  <span className="label">Demora arteria</span>
                  <span className="value">{result.avg_artery_delay_s.toFixed(1)}</span>
                  <span className="unit">
                    s/veh coordinada · {result.avg_artery_delay_isolated_s.toFixed(1)} aislada
                  </span>
                </div>
                <div className="kpi">
                  <span className="label">Mejora por coordinación</span>
                  <span className="value">
                    {improvement >= 0 ? "−" : "+"}
                    {Math.abs(improvement).toFixed(1)}
                  </span>
                  <span className="unit">s/veh en la arteria</span>
                </div>
              </div>

              <TimeSpaceDiagram result={result} />

              {result.warnings.map((w, i) => (
                <div key={i} className="warning" style={{ marginTop: 8 }}>
                  {w}
                </div>
              ))}
              {result.notes.map((n, i) => (
                <div key={i} className="note" style={{ marginTop: 6 }}>
                  {n}
                </div>
              ))}
            </Card.Content>
          </Card>

          <Card>
            <Card.Header>
              <Card.Title>Detalle por intersección</Card.Title>
              <Card.Description>
                Offset · proporción del pelotón en verde (P) · PF · demora
                coordinada vs aislada
              </Card.Description>
            </Card.Header>
            <Card.Content>
              <table>
                <thead>
                  <tr>
                    <th>Intersección</th>
                    <th className="right">Pos. (m)</th>
                    <th className="right">Offset (s)</th>
                    <th className="right">P ida</th>
                    <th className="right">PF ida</th>
                    <th className="right">Demora ida (s)</th>
                    <th className="right">P vta</th>
                    <th className="right">PF vta</th>
                    <th className="right">Demora vta (s)</th>
                  </tr>
                </thead>
                <tbody>
                  {result.intersections.map((it) => (
                    <tr key={it.name}>
                      <td>{it.name}</td>
                      <td className="right">{it.position_m.toFixed(0)}</td>
                      <td className="right">{it.offset_s.toFixed(0)}</td>
                      <td className="right">
                        {it.p_green_out != null ? it.p_green_out.toFixed(2) : "—"}
                      </td>
                      <td className="right">{it.pf_out.toFixed(2)}</td>
                      <td className="right">
                        {it.delay_out_s.toFixed(1)}
                        <span style={{ color: "var(--muted)", fontSize: 11 }}>
                          {" "}({it.delay_isolated_out_s.toFixed(1)})
                        </span>
                      </td>
                      <td className="right">
                        {it.p_green_in != null ? it.p_green_in.toFixed(2) : "—"}
                      </td>
                      <td className="right">{it.pf_in.toFixed(2)}</td>
                      <td className="right">
                        {it.delay_in_s.toFixed(1)}
                        <span style={{ color: "var(--muted)", fontSize: 11 }}>
                          {" "}({it.delay_isolated_in_s.toFixed(1)})
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="desc" style={{ marginBottom: 0 }}>
                Entre paréntesis: demora con llegadas aleatorias (PF = 1,
                intersección aislada). PF &lt; 1 = la coordinación ayuda;
                PF &gt; 1 = el pelotón llega en rojo y castiga.
              </p>
            </Card.Content>
          </Card>
        </>
      )}
    </>
  );
}
