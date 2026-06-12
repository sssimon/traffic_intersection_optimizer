import { useState } from "react";
import { Button, Card, Input } from "neobrutalistcomponents";
import { processFieldCount } from "../api";
import type {
  FieldCountResult,
  IntersectionConfig,
  MovementCounts,
} from "../types";

interface Props {
  config: IntersectionConfig;
  onChange: (c: IntersectionConfig) => void;
}

const CLASSES = [
  { key: "auto", label: "Autos" },
  { key: "moto", label: "Motos" },
  { key: "bus", label: "Buses" },
  { key: "camion", label: "Camiones" },
] as const;
type ClassKey = (typeof CLASSES)[number]["key"];

function genLabels(start: string, n: number): string[] {
  const m = /^(\d{1,2}):(\d{2})$/.exec(start.trim());
  if (!m) return Array.from({ length: n }, (_, i) => `I${i + 1}`);
  let h = parseInt(m[1], 10);
  let mi = parseInt(m[2], 10);
  const out: string[] = [];
  for (let i = 0; i < n; i++) {
    out.push(`${String(h).padStart(2, "0")}:${String(mi).padStart(2, "0")}`);
    mi += 15;
    h = (h + Math.floor(mi / 60)) % 24;
    mi %= 60;
  }
  return out;
}

export function FieldCountPanel({ config, onChange }: Props) {
  const [start, setStart] = useState("07:00");
  const [nIntervals, setNIntervals] = useState(4);
  const [enabled, setEnabled] = useState<Record<ClassKey, boolean>>({
    auto: true,
    moto: true,
    bus: false,
    camion: true,
  });
  const [cells, setCells] = useState<Record<string, string[]>>({});
  const [result, setResult] = useState<FieldCountResult | null>(null);
  const [applied, setApplied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const labels = genLabels(start, nIntervals);
  const groups = config.approaches.flatMap((a) =>
    a.lane_groups.map((lg) => lg.id),
  );
  const enabledClasses = CLASSES.filter((c) => enabled[c.key]);

  const cellValue = (gid: string, cls: ClassKey, i: number): string =>
    cells[`${gid}|${cls}`]?.[i] ?? "";

  const setCell = (gid: string, cls: ClassKey, i: number, value: string) => {
    const key = `${gid}|${cls}`;
    const arr = [...(cells[key] ?? [])];
    while (arr.length < nIntervals) arr.push("");
    arr[i] = value;
    setCells({ ...cells, [key]: arr });
    setResult(null);
    setApplied(false);
  };

  const buildCounts = (): Record<string, MovementCounts> => {
    const out: Record<string, MovementCounts> = {};
    for (const gid of groups) {
      const mc: MovementCounts = {};
      let any = false;
      for (const cls of CLASSES) {
        const values = Array.from({ length: nIntervals }, (_, i) => {
          const v = parseFloat(cellValue(gid, cls.key, i));
          return Number.isNaN(v) ? 0 : Math.max(0, v);
        });
        if (values.some((v) => v > 0)) {
          mc[cls.key] = values;
          any = true;
        }
      }
      if (any) out[gid] = mc;
    }
    return out;
  };

  const compute = async () => {
    const counts = buildCounts();
    if (Object.keys(counts).length === 0) {
      setError("Captura al menos un conteo mayor que cero.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setResult(await processFieldCount(labels, counts));
      setApplied(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const apply = () => {
    if (!result) return;
    const others = config.demand.filter(
      (d) => !(d.lane_group_id in result.volumes),
    );
    const updated = Object.keys(result.volumes).map((gid) => ({
      lane_group_id: gid,
      volume: result.volumes[gid],
      pcu_factor: result.pcu_factors[gid] ?? 1.0,
    }));
    onChange({
      ...config,
      demand: [...others, ...updated],
      peak_hour_factor: result.phf ?? config.peak_hour_factor,
    });
    setApplied(true);
  };

  const printSheet = () => {
    const w = window.open("", "_blank");
    if (!w) return;
    const head = labels.map((l) => `<th>${l}</th>`).join("");
    const body = groups
      .map((gid) =>
        CLASSES.map(
          (cls, i) =>
            `<tr>${i === 0 ? `<td rowspan="4" class="g">${gid}</td>` : ""}` +
            `<td>${cls.label}</td>${labels.map(() => "<td></td>").join("")}</tr>`,
        ).join(""),
      )
      .join("");
    w.document.write(`<!doctype html><html><head><meta charset="utf-8">
<title>Hoja de aforo — ${config.name}</title>
<style>
body{font-family:Arial,sans-serif;font-size:11pt;margin:14mm}
h1{font-size:15pt;border-bottom:3px solid #8a0f1c;padding-bottom:6px}
p{font-size:10pt}
table{border-collapse:collapse;width:100%;margin-top:8px}
th,td{border:1px solid #333;padding:7px 6px;font-size:9pt;text-align:center}
td.g{font-weight:bold;font-family:monospace}
th{background:#eee}
</style></head><body>
<h1>Hoja de aforo — ${config.name}</h1>
<p>Fecha: ________  Aforador: ________  Clima: ________  Inicio: ${labels[0]}
 · Intervalos de 15 min · Anota VEHÍCULOS POR CLASE que cruzan la línea de
 detención en cada intervalo.</p>
<table><thead><tr><th>Grupo</th><th>Clase</th>${head}</tr></thead>
<tbody>${body}</tbody></table>
</body></html>`);
    w.document.close();
    w.focus();
    w.print();
  };

  return (
    <Card>
      <Card.Header>
        <Card.Title>Aforo de campo (15 min)</Card.Title>
        <Card.Description>
          Conteos por intervalo y clase → hora pico, PHF y PCU calculados —
          sin Excel
        </Card.Description>
      </Card.Header>
      <Card.Content>
        <div className="row" style={{ alignItems: "flex-end", flexWrap: "wrap" }}>
          <Input
            label="Inicio (HH:MM)"
            size="sm"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            style={{ width: 110 }}
          />
          <Input
            label="Intervalos"
            size="sm"
            type="number"
            min={1}
            max={8}
            value={nIntervals}
            onChange={(e) =>
              setNIntervals(
                Math.max(1, Math.min(8, parseInt(e.target.value) || 4)),
              )
            }
            style={{ width: 90 }}
          />
          {CLASSES.map((cls) => (
            <label key={cls.key} className="inline" style={{ alignSelf: "center" }}>
              <input
                type="checkbox"
                checked={enabled[cls.key]}
                onChange={(e) =>
                  setEnabled({ ...enabled, [cls.key]: e.target.checked })
                }
              />
              {cls.label}
            </label>
          ))}
          <div style={{ marginLeft: "auto" }}>
            <Button variant="ghost" size="sm" onClick={printSheet}>
              🖨 Hoja de campo imprimible
            </Button>
          </div>
        </div>

        {groups.length === 0 ? (
          <p className="desc">Define primero los accesos y grupos de carriles.</p>
        ) : (
          <table style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>Grupo</th>
                <th>Clase</th>
                {labels.map((l) => (
                  <th key={l} className="right">
                    {l}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groups.flatMap((gid) =>
                enabledClasses.map((cls, ci) => (
                  <tr key={`${gid}|${cls.key}`}>
                    {ci === 0 && (
                      <td rowSpan={enabledClasses.length}>
                        <span className="code">{gid}</span>
                      </td>
                    )}
                    <td style={{ fontSize: 11 }}>{cls.label}</td>
                    {labels.map((_, i) => (
                      <td key={i} className="right">
                        <Input
                          size="sm"
                          type="number"
                          min={0}
                          placeholder="0"
                          value={cellValue(gid, cls.key, i)}
                          onChange={(e) =>
                            setCell(gid, cls.key, i, e.target.value)
                          }
                          style={{ width: 70 }}
                        />
                      </td>
                    ))}
                  </tr>
                )),
              )}
            </tbody>
          </table>
        )}

        <div className="row" style={{ marginTop: 12 }}>
          <Button variant="primary" size="sm" loading={loading} onClick={compute}>
            Calcular hora pico
          </Button>
        </div>

        {error && (
          <div className="error" style={{ marginTop: 12 }}>
            {error}
          </div>
        )}

        {result && (
          <>
            <div className="section-rule">Resultado del aforo</div>
            <div className="kpi-grid">
              <div className="kpi">
                <span className="label">Hora pico</span>
                <span className="value" style={{ fontSize: 18 }}>
                  {result.peak_hour_label}
                </span>
                <span className="unit">
                  {result.expanded ? "expansión simple" : "ventana móvil de 4×15 min"}
                </span>
              </div>
              <div className="kpi">
                <span className="label">PHF calculado</span>
                <span className="value">
                  {result.phf != null ? result.phf.toFixed(2) : "—"}
                </span>
                <span className="unit">V / (4·V15máx)</span>
              </div>
              <div className="kpi">
                <span className="label">Totales por intervalo</span>
                <span className="value" style={{ fontSize: 14 }}>
                  {result.totals_per_interval.map((t) => t.toFixed(0)).join(" · ")}
                </span>
                <span className="unit">veh mixtos / 15 min</span>
              </div>
            </div>

            <table style={{ marginTop: 12 }}>
              <thead>
                <tr>
                  <th>Grupo</th>
                  <th className="right">Volumen hora pico (veh/h)</th>
                  <th className="right">PCU calculado</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys(result.volumes).map((gid) => (
                  <tr key={gid}>
                    <td>
                      <span className="code">{gid}</span>
                    </td>
                    <td className="right">{result.volumes[gid].toFixed(0)}</td>
                    <td className="right">
                      {(result.pcu_factors[gid] ?? 1).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {result.warnings.map((w, i) => (
              <div key={i} className="warning" style={{ marginTop: 8 }}>
                {w}
              </div>
            ))}

            <div className="row" style={{ marginTop: 12 }}>
              <Button variant="primary" size="sm" onClick={apply}>
                Aplicar a la demanda y PHF
              </Button>
              {applied && (
                <span style={{ fontSize: 12, color: "var(--muted)", alignSelf: "center" }}>
                  ✓ Aplicado a la tabla de demanda
                  {result.phf != null ? ` y PHF = ${result.phf.toFixed(2)}` : ""}.
                </span>
              )}
            </div>
          </>
        )}
      </Card.Content>
    </Card>
  );
}
