import { useEffect, useMemo, useState } from "react";
import { Button, Card } from "neobrutalistcomponents";
import { compareControls } from "../api";
import type {
  CompareControlsResult,
  IntersectionConfig,
} from "../types";

interface Props {
  config: IntersectionConfig;
}

export function AlternativesPanel({ config }: Props) {
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
  const [result, setResult] = useState<CompareControlsResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Por defecto: las dos vías de mayor demanda como calle principal.
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
      setResult(await compareControls(config, majorIds));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const twscDetail = result
    ? result.alternatives.find((a) => a.kind === "twsc")?.twsc ?? null
    : null;

  return (
    <>
      <Card>
        <Card.Header>
          <Card.Title>Alternativas de control</Card.Title>
          <Card.Description>
            ¿Qué control merece esta intersección? Semáforo (fases
            configuradas y por acceso) vs PARE — misma demanda
          </Card.Description>
        </Card.Header>
        <Card.Content>
          <p className="desc" style={{ marginTop: 0 }}>
            El explorador optimiza y evalúa cada alternativa con el mismo
            aforo y las rankea por demora media. Para la alternativa PARE,
            marca qué accesos forman la calle principal (flujo libre).
          </p>

          <div className="section-rule">Calle principal (sin PARE)</div>
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
            <Button variant="primary" size="sm" loading={loading} onClick={run}>
              Comparar alternativas
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
              <Card.Title>Ranking de alternativas</Card.Title>
              <Card.Description>
                Ordenadas por demora media · ★ recomendada
              </Card.Description>
            </Card.Header>
            <Card.Content>
              <table>
                <thead>
                  <tr>
                    <th>Alternativa</th>
                    <th className="right">Demora media (s/veh)</th>
                    <th className="right">v/c repr.</th>
                    <th>LOS</th>
                    <th className="right">Ciclo (s)</th>
                    <th className="right">Cola 95 % máx</th>
                  </tr>
                </thead>
                <tbody>
                  {result.alternatives.map((a) => (
                    <tr
                      key={a.id}
                      style={
                        a.id === result.recommended_id
                          ? { fontWeight: 600 }
                          : undefined
                      }
                    >
                      <td>
                        {a.id === result.recommended_id ? "★ " : ""}
                        {a.name}
                      </td>
                      <td className="right">{a.avg_delay_s.toFixed(1)}</td>
                      <td
                        className="right"
                        style={{
                          color:
                            a.overall_v_c > 0.9 ? "var(--oxblood)" : undefined,
                        }}
                      >
                        {a.overall_v_c.toFixed(2)}
                      </td>
                      <td>
                        <span className={`los-badge los-${a.overall_los}`}>
                          {a.overall_los}
                        </span>
                      </td>
                      <td className="right">
                        {a.cycle_length != null
                          ? a.cycle_length.toFixed(0)
                          : "—"}
                      </td>
                      <td className="right">
                        {a.worst_queue_95th_veh != null
                          ? a.worst_queue_95th_veh.toFixed(1)
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {result.alternatives.some((a) => a.notes.length > 0) && (
                <div style={{ marginTop: 12 }}>
                  {result.alternatives.flatMap((a) =>
                    a.notes.map((n, i) => (
                      <div
                        key={`${a.id}-${i}`}
                        className="note"
                        style={{ marginTop: 4 }}
                      >
                        <strong>{a.name}:</strong> {n}
                      </div>
                    )),
                  )}
                </div>
              )}

              {result.warnings.map((w, i) => (
                <div key={i} className="warning" style={{ marginTop: 8 }}>
                  {w}
                </div>
              ))}
            </Card.Content>
          </Card>

          <Card>
            <Card.Header>
              <Card.Title>Por qué</Card.Title>
              <Card.Description>Criterios del ranking</Card.Description>
            </Card.Header>
            <Card.Content>
              <ul className="compact">
                {result.rationale.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
              <p className="desc" style={{ marginBottom: 0 }}>
                El detalle del semáforo con fases configuradas está en la
                pestaña 02 · Tiempos &amp; análisis.
              </p>
            </Card.Content>
          </Card>

          {twscDetail && (
            <Card>
              <Card.Header>
                <Card.Title>Detalle — PARE en calle secundaria</Card.Title>
                <Card.Description>
                  Calle principal: {twscDetail.major_approach_ids.join(", ")}
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
                    {twscDetail.movements.map((m) => (
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
                          <span className={`los-badge los-${m.los}`}>
                            {m.los}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {twscDetail.warnings.map((w, i) => (
                  <div key={i} className="warning">
                    {w}
                  </div>
                ))}
              </Card.Content>
            </Card>
          )}
        </>
      )}
    </>
  );
}
