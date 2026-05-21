import { useEffect, useMemo, useState } from "react";
import { Button, Card } from "neobrutalistcomponents";
import { analyze, analyzeRoundabout, analyzeTwsc } from "../api";
import type {
  IntersectionAnalysis,
  IntersectionConfig,
  LOS,
  RoundaboutAnalysis,
  TWSCAnalysis,
} from "../types";

interface Props {
  config: IntersectionConfig;
}

interface Results {
  signal: IntersectionAnalysis;
  twsc: TWSCAnalysis;
  roundabout: RoundaboutAnalysis;
}

function verdict(los: LOS): string {
  if (los === "A" || los === "B" || los === "C") return "Aceptable";
  if (los === "D" || los === "E") return "Saturado";
  return "No viable";
}

export function UnsignalizedPanel({ config }: Props) {
  const approachIds = useMemo(
    () => config.approaches.map((a) => a.id),
    [config.approaches],
  );

  const demandByApproach = useMemo(() => {
    const m: Record<string, number> = {};
    for (const a of config.approaches) {
      m[a.id] = a.lane_groups.reduce(
        (s, lg) =>
          s + (config.demand.find((d) => d.lane_group_id === lg.id)?.volume ?? 0),
        0,
      );
    }
    return m;
  }, [config]);

  const [majorIds, setMajorIds] = useState<string[]>([]);
  const [order, setOrder] = useState<string[]>([]);
  const [circLanes, setCircLanes] = useState(1);
  const [entryLanes, setEntryLanes] = useState(1);
  const [result, setResult] = useState<Results | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sincroniza con la configuración: orden y, por defecto, las dos vías de
  // mayor demanda como calle principal.
  useEffect(() => {
    setOrder(approachIds);
    setMajorIds((prev) => {
      const valid = prev.filter((id) => approachIds.includes(id));
      if (valid.length >= 1) return valid;
      return [...approachIds]
        .sort((a, b) => (demandByApproach[b] ?? 0) - (demandByApproach[a] ?? 0))
        .slice(0, 2);
    });
    setResult(null);
  }, [approachIds, demandByApproach]);

  const toggleMajor = (id: string) => {
    setMajorIds((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  };

  const moveOrder = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= order.length) return;
    const copy = [...order];
    [copy[i], copy[j]] = [copy[j], copy[i]];
    setOrder(copy);
  };

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const entry: Record<string, number> = {};
      for (const id of approachIds) entry[id] = entryLanes;
      const [signal, twsc, roundabout] = await Promise.all([
        analyze(config),
        analyzeTwsc(config, majorIds),
        analyzeRoundabout(config, {
          order,
          circulatingLanes: circLanes,
          entryLanes: entry,
        }),
      ]);
      setResult({ signal, twsc, roundabout });
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const twscMaxVC = result
    ? Math.max(
        0,
        ...result.twsc.movements
          .map((m) => m.v_c_ratio)
          .filter((v): v is number => v != null),
      )
    : 0;
  const rbMaxVC = result
    ? Math.max(0, ...result.roundabout.approaches.map((a) => a.v_c_ratio))
    : 0;

  return (
    <>
      <Card>
        <Card.Header>
          <Card.Title>Análisis sin semáforo</Card.Title>
          <Card.Description>
            Comparación: semáforo vs PARE vs glorieta — HCM cap. 19 / 22
          </Card.Description>
        </Card.Header>
        <Card.Content>
          <p className="desc" style={{ marginTop: 0 }}>
            Evalúa la intersección con control no semaforizado mediante teoría
            de aceptación de brechas, y la compara con el plan semafórico
            optimizado. Útil para decidir si conviene instalar un semáforo,
            mantener señales de PARE o construir una glorieta.
          </p>

          <div className="section-rule">Calle principal (sin PARE)</div>
          <p className="desc" style={{ marginTop: 0 }}>
            Marca los accesos de la vía mayor (flujo libre). El resto llevan
            PARE.
          </p>
          <div className="row" style={{ flexWrap: "wrap" }}>
            {config.approaches.map((a) => (
              <label key={a.id} className="inline">
                <input
                  type="checkbox"
                  checked={majorIds.includes(a.id)}
                  onChange={() => toggleMajor(a.id)}
                />
                <span className="code">{a.id}</span>
                <span style={{ color: "var(--muted)", fontSize: 11 }}>
                  {a.name}
                </span>
              </label>
            ))}
          </div>

          <div className="section-rule">Glorieta</div>
          <div className="row">
            <label className="field">
              Carriles de circulación
              <select
                value={circLanes}
                onChange={(e) => setCircLanes(parseInt(e.target.value))}
              >
                <option value={1}>1 carril</option>
                <option value={2}>2 carriles</option>
              </select>
            </label>
            <label className="field">
              Carriles de entrada
              <select
                value={entryLanes}
                onChange={(e) => setEntryLanes(parseInt(e.target.value))}
              >
                <option value={1}>1 carril</option>
                <option value={2}>2 carriles</option>
              </select>
            </label>
          </div>
          <p className="desc" style={{ marginBottom: 4 }}>
            Orden de circulación de los accesos (afecta el flujo circulante):
          </p>
          <div className="row" style={{ flexWrap: "wrap" }}>
            {order.map((id, i) => (
              <span key={id} className="inline" style={{ gap: 2 }}>
                <span className="code">{i + 1}. {id}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => moveOrder(i, -1)}
                >
                  ◂
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => moveOrder(i, 1)}
                >
                  ▸
                </Button>
              </span>
            ))}
          </div>

          <div className="row" style={{ marginTop: 16 }}>
            <Button
              variant="primary"
              size="sm"
              loading={loading}
              onClick={run}
            >
              Analizar y comparar
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
              <Card.Title>Comparación de tipos de control</Card.Title>
              <Card.Description>
                Misma demanda · tres formas de operar la intersección
              </Card.Description>
            </Card.Header>
            <Card.Content>
              <table>
                <thead>
                  <tr>
                    <th>Tipo de control</th>
                    <th className="right">Demora media</th>
                    <th className="right">v/c repr.</th>
                    <th>LOS</th>
                    <th>Veredicto</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Semáforo (plan optimizado)</td>
                    <td className="right">
                      {result.signal.avg_delay_s.toFixed(0)} s
                    </td>
                    <td className="right">
                      {result.signal.overall_v_c.toFixed(2)}
                    </td>
                    <td>
                      <span className={`los-badge los-${result.signal.overall_los}`}>
                        {result.signal.overall_los}
                      </span>
                    </td>
                    <td>{verdict(result.signal.overall_los)}</td>
                  </tr>
                  <tr>
                    <td>PARE en calle secundaria (TWSC)</td>
                    <td className="right">
                      {result.twsc.avg_delay_s.toFixed(0)} s
                    </td>
                    <td className="right">{twscMaxVC.toFixed(2)}</td>
                    <td>
                      <span className={`los-badge los-${result.twsc.overall_los}`}>
                        {result.twsc.overall_los}
                      </span>
                    </td>
                    <td>{verdict(result.twsc.overall_los)}</td>
                  </tr>
                  <tr>
                    <td>
                      Glorieta ({result.roundabout.circulating_lanes} carril
                      {result.roundabout.circulating_lanes > 1 ? "es" : ""} circ.)
                    </td>
                    <td className="right">
                      {result.roundabout.avg_delay_s.toFixed(0)} s
                    </td>
                    <td className="right">{rbMaxVC.toFixed(2)}</td>
                    <td>
                      <span
                        className={`los-badge los-${result.roundabout.overall_los}`}
                      >
                        {result.roundabout.overall_los}
                      </span>
                    </td>
                    <td>{verdict(result.roundabout.overall_los)}</td>
                  </tr>
                </tbody>
              </table>
              <p className="desc" style={{ marginBottom: 0, marginTop: 8 }}>
                Nota: el LOS no semaforizado usa umbrales distintos al
                semaforizado (F &gt; 50 s en vez de &gt; 80 s). Demoras
                mostradas hasta 999 s; por encima la operación es inviable.
              </p>
            </Card.Content>
          </Card>

          <Card>
            <Card.Header>
              <Card.Title>Detalle — PARE en calle secundaria</Card.Title>
              <Card.Description>
                Calle principal: {result.twsc.major_approach_ids.join(", ")}
              </Card.Description>
            </Card.Header>
            <Card.Content>
              <table>
                <thead>
                  <tr>
                    <th>Grupo</th>
                    <th>Rol</th>
                    <th className="right">Demanda</th>
                    <th className="right">Flujo confl.</th>
                    <th className="right">Capacidad</th>
                    <th className="right">v/c</th>
                    <th className="right">Demora (s)</th>
                    <th>LOS</th>
                  </tr>
                </thead>
                <tbody>
                  {result.twsc.movements.map((m) => (
                    <tr key={m.lane_group_id}>
                      <td>
                        <span className="code">{m.lane_group_id}</span>
                      </td>
                      <td>{m.role}</td>
                      <td className="right">{m.demand.toFixed(0)}</td>
                      <td className="right">
                        {m.conflicting_flow != null
                          ? m.conflicting_flow.toFixed(0)
                          : "—"}
                      </td>
                      <td className="right">
                        {m.capacity != null ? m.capacity.toFixed(0) : "libre"}
                      </td>
                      <td className="right">
                        {m.v_c_ratio != null ? m.v_c_ratio.toFixed(2) : "—"}
                      </td>
                      <td className="right">{m.avg_delay_s.toFixed(0)}</td>
                      <td>
                        <span className={`los-badge los-${m.los}`}>{m.los}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.twsc.warnings.map((w, i) => (
                <div key={i} className="warning">
                  {w}
                </div>
              ))}
            </Card.Content>
          </Card>

          <Card>
            <Card.Header>
              <Card.Title>Detalle — Glorieta</Card.Title>
              <Card.Description>
                Capacidad de entrada por aceptación de brechas
              </Card.Description>
            </Card.Header>
            <Card.Content>
              <table>
                <thead>
                  <tr>
                    <th>Acceso</th>
                    <th className="right">Demanda entrada</th>
                    <th className="right">Flujo circulante</th>
                    <th className="right">Capacidad</th>
                    <th className="right">v/c</th>
                    <th className="right">Demora (s)</th>
                    <th>LOS</th>
                  </tr>
                </thead>
                <tbody>
                  {result.roundabout.approaches.map((a) => (
                    <tr key={a.approach_id}>
                      <td>
                        <span className="code">{a.approach_id}</span>{" "}
                        {a.approach_name}
                      </td>
                      <td className="right">{a.entry_demand.toFixed(0)}</td>
                      <td className="right">
                        {a.circulating_flow.toFixed(0)}
                      </td>
                      <td className="right">{a.capacity.toFixed(0)}</td>
                      <td className="right">{a.v_c_ratio.toFixed(2)}</td>
                      <td className="right">{a.avg_delay_s.toFixed(0)}</td>
                      <td>
                        <span className={`los-badge los-${a.los}`}>{a.los}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.roundabout.warnings.map((w, i) => (
                <div key={i} className="warning">
                  {w}
                </div>
              ))}
            </Card.Content>
          </Card>
        </>
      )}
    </>
  );
}
