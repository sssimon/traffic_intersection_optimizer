import { useEffect, useState } from "react";
import { Button, Card } from "neobrutalistcomponents";
import { copilotEdit, copilotExplain, copilotStatus } from "../api";
import type {
  CopilotEditResult,
  CopilotStatus,
  IntersectionConfig,
} from "../types";

interface Props {
  config: IntersectionConfig;
  onChange: (cfg: IntersectionConfig) => void;
}

export function CopilotPanel({ config, onChange }: Props) {
  const [status, setStatus] = useState<CopilotStatus | null>(null);

  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [explLoading, setExplLoading] = useState(false);

  const [instruction, setInstruction] = useState("");
  const [proposal, setProposal] = useState<CopilotEditResult | null>(null);
  const [editLoading, setEditLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    copilotStatus().then(setStatus).catch((e) => setError(String(e)));
  }, []);

  const ask = async () => {
    if (!question.trim()) return;
    setExplLoading(true);
    setError(null);
    setAnswer(null);
    try {
      const r = await copilotExplain(config, question);
      setAnswer(r.answer);
    } catch (e) {
      setError(String(e));
    } finally {
      setExplLoading(false);
    }
  };

  const propose = async () => {
    if (!instruction.trim()) return;
    setEditLoading(true);
    setError(null);
    setProposal(null);
    try {
      setProposal(await copilotEdit(config, instruction));
    } catch (e) {
      setError(String(e));
    } finally {
      setEditLoading(false);
    }
  };

  const applyProposal = () => {
    if (proposal) {
      onChange(proposal.config);
      setProposal(null);
      setInstruction("");
    }
  };

  const available = status?.available ?? false;

  return (
    <>
      <Card>
        <Card.Header>
          <Card.Title>Copiloto (IA) — opcional</Card.Title>
          <Card.Description>
            Explica resultados y edita la configuración por lenguaje natural.
            Usa la API de Claude; el resto de la aplicación funciona sin él.
          </Card.Description>
        </Card.Header>
        <Card.Content>
          {status && (
            <div className={available ? "note" : "warning"}>
              {available
                ? `Copiloto activo · modelo ${status.model}`
                : status.note}
            </div>
          )}
          {error && (
            <div className="error" style={{ marginTop: 8 }}>
              {error}
            </div>
          )}
        </Card.Content>
      </Card>

      <Card>
        <Card.Header>
          <Card.Title>Explicar el análisis</Card.Title>
          <Card.Description>
            Pregunta en español; la respuesta se ancla en los números reales del
            motor (no inventa cifras).
          </Card.Description>
        </Card.Header>
        <Card.Content>
          <textarea
            rows={3}
            value={question}
            disabled={!available}
            placeholder="Ej.: ¿Por qué los giros a la izquierda están en LOS F y qué haría para mejorarlos?"
            onChange={(e) => setQuestion(e.target.value)}
            style={{ width: "100%", fontFamily: "inherit", fontSize: 13, padding: 8 }}
          />
          <div className="row" style={{ marginTop: 8 }}>
            <Button
              variant="primary"
              size="sm"
              loading={explLoading}
              disabled={!available || !question.trim()}
              onClick={ask}
            >
              Preguntar
            </Button>
          </div>
          {answer && (
            <div
              className="note"
              style={{ marginTop: 12, whiteSpace: "pre-wrap", lineHeight: 1.5 }}
            >
              {answer}
            </div>
          )}
        </Card.Content>
      </Card>

      <Card>
        <Card.Header>
          <Card.Title>Editar por instrucción</Card.Title>
          <Card.Description>
            Describe el cambio; el copiloto propone una configuración que se
            valida con el esquema. Tú decides si aplicarla.
          </Card.Description>
        </Card.Header>
        <Card.Content>
          <textarea
            rows={2}
            value={instruction}
            disabled={!available}
            placeholder="Ej.: sube 20% la demanda del acceso Este · agrega una fase peatonal exclusiva de 15 s"
            onChange={(e) => setInstruction(e.target.value)}
            style={{ width: "100%", fontFamily: "inherit", fontSize: 13, padding: 8 }}
          />
          <div className="row" style={{ marginTop: 8 }}>
            <Button
              variant="primary"
              size="sm"
              loading={editLoading}
              disabled={!available || !instruction.trim()}
              onClick={propose}
            >
              Proponer cambio
            </Button>
          </div>

          {proposal && (
            <div style={{ marginTop: 12 }}>
              <div className="note">{proposal.summary}</div>
              {proposal.warnings.map((w, i) => (
                <div key={i} className="warning" style={{ marginTop: 6 }}>
                  {w}
                </div>
              ))}
              <div className="row" style={{ marginTop: 10, gap: 8 }}>
                <Button variant="primary" size="sm" onClick={applyProposal}>
                  Aplicar a la configuración
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setProposal(null)}>
                  Descartar
                </Button>
              </div>
              <details style={{ marginTop: 10 }}>
                <summary style={{ cursor: "pointer", fontSize: 12 }}>
                  Ver JSON propuesto
                </summary>
                <pre style={{ fontSize: 11, maxHeight: 280, overflow: "auto" }}>
                  {JSON.stringify(proposal.config, null, 2)}
                </pre>
              </details>
            </div>
          )}
        </Card.Content>
      </Card>
    </>
  );
}
