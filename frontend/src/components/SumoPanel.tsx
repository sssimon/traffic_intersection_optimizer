import { useState } from "react";
import { Button, Card, Input } from "neobrutalistcomponents";
import { sumoExport } from "../api";
import type { IntersectionConfig, SumoExportResult } from "../types";

const downloadFile = (name: string, content: string) => {
  const blob = new Blob([content], { type: "application/xml" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
};

export function SumoPanel({ config }: { config: IntersectionConfig }) {
  const [method, setMethod] = useState<"delay_min" | "webster">("delay_min");
  const [replications, setReplications] = useState(5);
  const [durationS, setDurationS] = useState(600);
  const [warmupS, setWarmupS] = useState(120);
  const [result, setResult] = useState<SumoExportResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (runMicrosim: boolean) => {
    setLoading(true);
    setError(null);
    try {
      setResult(
        await sumoExport(config, {
          method,
          replications,
          durationS,
          warmupS,
          runMicrosim,
        }),
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const downloadAll = (files: SumoExportResult["files"]) =>
    files.forEach((f) => downloadFile(f.name, f.content));

  const m = result?.microsim;
  const delta = result?.delta_delay_s;

  return (
    <>
      <Card>
        <Card.Header>
          <Card.Title>Validación con SUMO — analítico vs microsimulado</Card.Title>
          <Card.Description>
            Exporta la intersección a un modelo SUMO completo y, si SUMO está
            instalado, corre réplicas headless para poner la demora del motor
            HCM al lado de la microsimulada. Dos métodos independientes que
            coinciden = el motor es creíble.
          </Card.Description>
        </Card.Header>
        <Card.Content>
          <div className="row" style={{ alignItems: "flex-end", flexWrap: "wrap", gap: 12 }}>
            <label className="field">
              Plan
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value as "delay_min" | "webster")}
              >
                <option value="delay_min">Mínima demora</option>
                <option value="webster">Webster</option>
              </select>
            </label>
            <Input
              label="Réplicas"
              size="sm"
              type="number"
              min={1}
              max={20}
              value={replications}
              onChange={(e) => setReplications(parseInt(e.target.value) || 5)}
              style={{ width: 90 }}
            />
            <Input
              label="Duración (s)"
              size="sm"
              type="number"
              min={120}
              max={3600}
              step={60}
              value={durationS}
              onChange={(e) => setDurationS(parseInt(e.target.value) || 600)}
              style={{ width: 110 }}
            />
            <Input
              label="Calentamiento (s)"
              size="sm"
              type="number"
              min={0}
              max={1800}
              step={30}
              value={warmupS}
              onChange={(e) => setWarmupS(parseInt(e.target.value) || 120)}
              style={{ width: 130 }}
            />
            <Button variant="primary" size="sm" loading={loading} onClick={() => run(true)}>
              Exportar y comparar
            </Button>
            <Button variant="secondary" size="sm" disabled={loading} onClick={() => run(false)}>
              Solo exportar
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
              <Card.Title>
                Comparación{" "}
                {result.sumo_available ? "" : "— SUMO no detectado"}
              </Card.Title>
              <Card.Description>
                {result.sumo_available
                  ? "timeLoss microsimulado ≈ demora de control; mismos umbrales LOS"
                  : "Se exportan los archivos; instala SUMO para la comparación automática"}
              </Card.Description>
            </Card.Header>
            <Card.Content>
              <div className="kpi-grid">
                <div className="kpi">
                  <span className="label">Analítico (HCM)</span>
                  <span className="value">{result.analytic.avg_delay_s.toFixed(1)}</span>
                  <span className="unit">
                    s/veh · LOS {result.analytic.overall_los} · v/c{" "}
                    {result.analytic.overall_v_c.toFixed(2)}
                  </span>
                </div>
                <div className="kpi">
                  <span className="label">Microsimulado (SUMO)</span>
                  <span className="value">
                    {m ? m.delay_mean_s.toFixed(1) : "—"}
                  </span>
                  <span className="unit">
                    {m
                      ? `s/veh · LOS ${m.overall_los} · ${m.replications} réplicas`
                      : "no disponible"}
                  </span>
                </div>
                <div className="kpi">
                  <span className="label">Diferencia</span>
                  <span className="value">
                    {delta != null ? `${delta >= 0 ? "+" : "−"}${Math.abs(delta).toFixed(1)}` : "—"}
                  </span>
                  <span className="unit">s/veh (micro − analítico)</span>
                </div>
                {m && (
                  <div className="kpi">
                    <span className="label">Banda microsim. (p05–p95)</span>
                    <span className="value">
                      {m.delay_p05_s.toFixed(0)}–{m.delay_p95_s.toFixed(0)}
                    </span>
                    <span className="unit">
                      s · {m.measured_vehicles.toFixed(0)} veh medidos
                    </span>
                  </div>
                )}
              </div>

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
              <Card.Title>Modelo SUMO ({result.files.length} archivos)</Card.Title>
              <Card.Description>
                Descárgalos para abrir el modelo en SUMO (sumo-gui interseccion.sumocfg)
              </Card.Description>
            </Card.Header>
            <Card.Content>
              <div className="row" style={{ marginBottom: 10 }}>
                <Button variant="secondary" size="sm" onClick={() => downloadAll(result.files)}>
                  Descargar todos
                </Button>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>Archivo</th>
                    <th className="right">Líneas</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {result.files.map((f) => (
                    <tr key={f.name}>
                      <td style={{ fontFamily: "JetBrains Mono, monospace" }}>{f.name}</td>
                      <td className="right">{f.content.split("\n").length}</td>
                      <td className="right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => downloadFile(f.name, f.content)}
                        >
                          Descargar
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card.Content>
          </Card>
        </>
      )}
    </>
  );
}
