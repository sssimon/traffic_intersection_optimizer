import { useEffect, useState } from "react";
import { Button, Card, Input } from "neobrutalistcomponents";
import { deleteRun, getRun, listRuns, saveRun } from "../api";
import type { IntersectionConfig, RunSummary } from "../types";

interface Props {
  config: IntersectionConfig;
  onChange: (c: IntersectionConfig) => void;
}

export function RunsPanel({ config, onChange }: Props) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      setRuns(await listRuns());
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    refresh().catch(() => {});
  }, []);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await saveRun(name.trim() || config.name, config);
      setName("");
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const load = async (id: number) => {
    setBusy(true);
    setError(null);
    try {
      const detail = await getRun(id);
      onChange(detail.config);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: number) => {
    setBusy(true);
    setError(null);
    try {
      await deleteRun(id);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <Card.Header>
        <Card.Title>Corridas guardadas</Card.Title>
        <Card.Description>
          Historial en el servidor · la tabla compara resultados entre fechas
        </Card.Description>
      </Card.Header>
      <Card.Content>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <Input
            label="Nombre de la corrida"
            size="sm"
            placeholder={config.name}
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ minWidth: 260 }}
          />
          <Button variant="primary" size="sm" loading={busy} onClick={save}>
            Guardar corrida actual
          </Button>
        </div>
        <p className="desc" style={{ marginBottom: 0 }}>
          Se guarda la configuración completa más el resumen del análisis
          (plan de mínima demora) al momento de guardar.
        </p>

        {error && (
          <div className="error" style={{ marginTop: 12 }}>
            {error}
          </div>
        )}

        {runs.length > 0 && (
          <table style={{ marginTop: 16 }}>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Fecha</th>
                <th>Intersección</th>
                <th>Método</th>
                <th className="right">Ciclo (s)</th>
                <th className="right">Demora (s/veh)</th>
                <th>LOS</th>
                <th className="right">v/c</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>{r.name}</td>
                  <td style={{ fontSize: 11 }}>
                    {new Date(r.created_at).toLocaleString("es", {
                      dateStyle: "short",
                      timeStyle: "short",
                    })}
                  </td>
                  <td style={{ fontSize: 11 }}>{r.intersection_name}</td>
                  <td style={{ fontSize: 11 }}>
                    {r.method === "delay_min" ? "mín. demora" : "Webster"}
                  </td>
                  <td className="right">{r.cycle_length.toFixed(0)}</td>
                  <td className="right">{r.avg_delay_s.toFixed(1)}</td>
                  <td>
                    <span className={`los-badge los-${r.overall_los}`}>
                      {r.overall_los}
                    </span>
                  </td>
                  <td className="right">{r.overall_v_c.toFixed(2)}</td>
                  <td>
                    <div className="row" style={{ gap: 4 }}>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => load(r.id)}
                      >
                        Cargar
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => remove(r.id)}
                      >
                        ✕
                      </Button>
                    </div>
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
