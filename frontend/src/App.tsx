import { useEffect, useState } from "react";
import { Button } from "neobrutalistcomponents";
import { analyze, fetchSample } from "./api";
import { DemandTable } from "./components/DemandTable";
import { IntersectionForm, PhaseEditor } from "./components/IntersectionForm";
import { LocationMap } from "./components/LocationMap";
import { AlternativesPanel } from "./components/AlternativesPanel";
import { CorridorPanel } from "./components/CorridorPanel";
import { FieldCountPanel } from "./components/FieldCountPanel";
import { RunsPanel } from "./components/RunsPanel";
import { ScenarioComparison } from "./components/ScenarioComparison";
import { SimulationPanel } from "./components/SimulationPanel";
import { SumoPanel } from "./components/SumoPanel";
import { TimingResults } from "./components/TimingResults";
import type { IntersectionAnalysis, IntersectionConfig } from "./types";

type Tab =
  | "config"
  | "timing"
  | "simulation"
  | "scenarios"
  | "alternatives"
  | "corridor"
  | "sumo";

const TABS: { id: Tab; label: string }[] = [
  { id: "config", label: "01 · Configuración" },
  { id: "timing", label: "02 · Tiempos & análisis" },
  { id: "simulation", label: "03 · Simulación" },
  { id: "scenarios", label: "04 · Escenarios" },
  { id: "alternatives", label: "05 · Alternativas" },
  { id: "corridor", label: "06 · Corredor" },
  { id: "sumo", label: "07 · Validación SUMO" },
];

const EMPTY: IntersectionConfig = {
  name: "Nueva intersección",
  approaches: [],
  phases: [],
  demand: [],
  peak_hour_factor: 0.92,
};

interface Analyses {
  webster: IntersectionAnalysis;
  delayMin: IntersectionAnalysis;
}

export default function App() {
  const [tab, setTab] = useState<Tab>("config");
  const [config, setConfig] = useState<IntersectionConfig>(EMPTY);
  const [analyses, setAnalyses] = useState<Analyses | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSample = async () => {
    try {
      const s = await fetchSample();
      setConfig(s);
      setAnalyses(null);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    loadSample().catch(() => {});
  }, []);

  const runAnalysis = async () => {
    setLoading(true);
    setError(null);
    try {
      const [webster, delayMin] = await Promise.all([
        analyze(config, "webster"),
        analyze(config, "delay_min"),
      ]);
      setAnalyses({ webster, delayMin });
      setTab("timing");
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(config, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${config.name.replace(/\s+/g, "_")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const importJson = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result));
        setConfig(parsed);
        setAnalyses(null);
      } catch {
        setError("JSON inválido");
      }
    };
    reader.readAsText(file);
  };

  return (
    <div className="app">
      <div className="topbar">
        <div>
          <h1>Traffic Intersection Optimizer</h1>
          <span className="sub">Webster · HCM 2010 · Simulación de colas</span>
        </div>
        <div className="topbar-actions">
          <Button variant="ghost" size="sm" onClick={loadSample}>
            Cargar ejemplo
          </Button>
          <Button variant="secondary" size="sm" onClick={exportJson}>
            Exportar JSON
          </Button>
          <label className="inline" style={{ cursor: "pointer" }}>
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                (document.getElementById("import-json") as HTMLInputElement)?.click()
              }
            >
              Importar JSON
            </Button>
            <input
              id="import-json"
              type="file"
              accept=".json"
              onChange={(e) =>
                e.target.files?.[0] && importJson(e.target.files[0])
              }
            />
          </label>
          <Button
            variant="primary"
            size="sm"
            loading={loading}
            onClick={runAnalysis}
          >
            Optimizar y analizar
          </Button>
        </div>
      </div>

      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? "active" : ""}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="content">
        {error && <div className="error">{error}</div>}

        {tab === "config" && (
          <>
            <LocationMap config={config} onChange={setConfig} />
            <IntersectionForm config={config} onChange={setConfig} />
            <PhaseEditor config={config} onChange={setConfig} />
            <DemandTable config={config} onChange={setConfig} />
            <FieldCountPanel config={config} onChange={setConfig} />
            <RunsPanel config={config} onChange={setConfig} />
          </>
        )}

        {tab === "timing" &&
          (analyses ? (
            <TimingResults
              webster={analyses.webster}
              delayMin={analyses.delayMin}
              config={config}
            />
          ) : (
            <div className="loading">
              Sin análisis aún — haz clic en "Optimizar y analizar" en la barra
              superior.
            </div>
          ))}

        {tab === "simulation" && <SimulationPanel config={config} />}

        {tab === "scenarios" && <ScenarioComparison config={config} />}

        {tab === "alternatives" && <AlternativesPanel config={config} />}

        {tab === "corridor" && <CorridorPanel />}

        {tab === "sumo" && <SumoPanel config={config} />}
      </div>
    </div>
  );
}
