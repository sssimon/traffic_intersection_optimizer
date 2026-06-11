import { useEffect, useMemo, useState } from "react";
import { Button, Card } from "neobrutalistcomponents";
import { analyze, analyzeTwsc } from "../api";
import type {
  IntersectionAnalysis,
  IntersectionConfig,
  LOS,
  TWSCAnalysis,
} from "../types";

interface Props {
  config: IntersectionConfig;
}

interface Results {
  signal: IntersectionAnalysis;
  twsc: TWSCAnalysis;
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
  const [result, setResult] = useState<Results | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sincroniza con la configuración: por defecto, las dos vías de mayor
  // demanda como calle principal.
  useEffect(() => {
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

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const [signal, twsc] = await Promise.all([
        analyze(config),
        analyzeTwsc(config, majorIds),
      ]);
      setResult({ signal, twsc });
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

  return (
    <>
      <Card>
        <Card.Header>
          <Card.Title>Análisis sin semáforo</Card.Title>
          <Card.Description>
            Comparación: semáforo vs PARE — HCM cap. 19
          </Card.Description>
        </Card.Header>
        <Card.Content>
          <p className="desc" style={{ marginTop: 0 }}>
            Evalúa la intersección con control no semaforizado mediante teoría
            de aceptación de brechas, y la compara con el plan semafórico
            optimizado. Útil para decidir si conviene instalar un semáforo o
            mantener señales de PARE.
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
                Misma demanda · dos formas de operar la intersección
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
        </>
      )}
    </>
  );
}
