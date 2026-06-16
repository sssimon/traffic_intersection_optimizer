"""Copiloto LLM opcional (tarea 5.2, F5).

**Feature-flag**: solo se activa si hay `ANTHROPIC_API_KEY` en el entorno; el
core no la requiere ni la importa. La llamada a la API de Claude se hace por
`urllib` de la librería estándar — sin SDK ni dependencias nuevas, igual que
`osm.py` con Overpass. Si no hay clave, los endpoints lo dicen con claridad y
el resto de la aplicación funciona idéntico.

Dos capacidades:

- **Explicar**: responde preguntas sobre el análisis en lenguaje natural,
  anclado en los números REALES del motor (se le pasan los resultados ya
  calculados; el prompt le prohíbe inventar cifras).
- **Editar**: traduce una instrucción ("agrega una fase peatonal exclusiva",
  "sube 20 % la demanda del Este") a un `IntersectionConfig` nuevo, que se
  **valida con Pydantic** antes de devolverlo. El modelo propone; el sistema
  valida y avisa de inconsistencias. La edición nunca se aplica sola: el
  frontend muestra el resumen y el usuario decide.

La construcción de prompts y el parseo/validación de la respuesta son puros y
se prueban sin red; la llamada HTTP está aislada en `_call_anthropic`.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import List, Tuple

from .analysis import analyze
from .models import (
    CopilotEditRequest,
    CopilotEditResult,
    CopilotExplainRequest,
    CopilotExplainResult,
    CopilotStatus,
    IntersectionAnalysis,
    IntersectionConfig,
    SignalPlan,
)
from .optimizer import optimize
from .optimizer_delay import optimize_delay

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
ENV_KEY = "ANTHROPIC_API_KEY"
ENV_MODEL = "COPILOT_MODEL"
DEFAULT_MODEL = "claude-sonnet-4-6"


def is_copilot_available() -> bool:
    return bool(os.environ.get(ENV_KEY))


def _model() -> str:
    return os.environ.get(ENV_MODEL) or DEFAULT_MODEL


def copilot_status() -> CopilotStatus:
    avail = is_copilot_available()
    return CopilotStatus(
        available=avail,
        model=_model() if avail else None,
        note=(
            "Copiloto listo."
            if avail
            else "Define ANTHROPIC_API_KEY en el entorno del backend para "
            "activar el copiloto (es opcional; el resto funciona sin él)."
        ),
    )


def _plan_for(cfg: IntersectionConfig, method: str) -> SignalPlan:
    return optimize_delay(cfg) if method == "delay_min" else optimize(cfg)


# --------------------------------------------------------------------------
# Construcción de prompts (puro)
# --------------------------------------------------------------------------

_EXPLAIN_SYSTEM = (
    "Eres un ingeniero de tránsito experto que asiste con el análisis de una "
    "intersección. Respondes en español, claro y conciso, en formato markdown. "
    "Te basas EXCLUSIVAMENTE en los datos numéricos provistos: no inventes "
    "cifras ni supongas valores que no estén en los datos. Si propones mejoras, "
    "márcalas explícitamente como sugerencias. Usa la terminología del HCM "
    "(LOS, v/c, demora, ciclo, verde)."
)


def _analysis_brief(cfg: IntersectionConfig, an: IntersectionAnalysis,
                    plan: SignalPlan, method: str) -> str:
    lines = [
        f"Intersección: {cfg.name}",
        f"Accesos: {len(cfg.approaches)} · Fases: {len(cfg.phases)} · PHF: {cfg.peak_hour_factor}",
        f"Plan ({method}): ciclo {plan.cycle_length:.0f} s, tiempo perdido "
        f"{plan.total_lost_time:.0f} s",
        f"Verde por fase: " + ", ".join(
            f"{pid}={g:.1f}s" for pid, g in plan.phase_green.items()
        ),
        f"RESULTADO GLOBAL: demora media {an.avg_delay_s:.1f} s/veh · "
        f"LOS {an.overall_los.value} · v/c máx {an.overall_v_c:.2f}",
        "Movimientos (grupo | fase | demanda veh/h | capacidad | v/c | "
        "demora s | cola95 veh | LOS):",
    ]
    for m in an.movements:
        lines.append(
            f"  {m.lane_group_id} | {m.phase_id} | {m.demand:.0f} | "
            f"{m.capacity:.0f} | {m.v_c_ratio:.2f} | {m.avg_delay_s:.1f} | "
            f"{m.queue_95th_veh:.1f} | {m.los.value}"
        )
    if an.warnings:
        lines.append("Avisos del motor: " + " | ".join(an.warnings))
    return "\n".join(lines)


def build_explain_prompt(cfg: IntersectionConfig, an: IntersectionAnalysis,
                         plan: SignalPlan, question: str) -> Tuple[str, str]:
    user = (
        "Datos del análisis (calculados por el motor HCM, son la única fuente "
        "de cifras válida):\n\n"
        f"{_analysis_brief(cfg, an, plan, '')}\n\n"
        f"Pregunta del usuario: {question}"
    )
    return _EXPLAIN_SYSTEM, user


_EDIT_SYSTEM = (
    "Eres un asistente que edita la configuración JSON de una intersección "
    "semaforizada. Recibes la configuración actual y una instrucción en "
    "español. Devuelves EXCLUSIVAMENTE un objeto JSON válido, sin texto "
    "adicional, con esta forma exacta:\n"
    '{"config": <IntersectionConfig completo>, "summary": "<qué cambiaste, '
    'en español, 1-3 frases>"}\n\n'
    "Reglas del esquema IntersectionConfig:\n"
    "- approaches[].lane_groups[].movement debe ser 'left', 'through' o 'right'.\n"
    "- phases[].lane_group_ids deben referenciar ids de lane_groups existentes.\n"
    "- demand[].lane_group_id debe referenciar un lane_group existente; "
    "volume en veh/h; pcu_factor entre 0.3 y 3.0.\n"
    "- Una fase peatonal exclusiva se modela como una fase con su propia "
    "duración donde NINGÚN grupo vehicular tiene verde: usa una lista "
    "lane_group_ids con un único id ficticio de peatones (p. ej. 'PED') y NO "
    "agregues ese id a ningún acceso, o bien añade una fase con los grupos "
    "indicados — sigue la intención del usuario.\n"
    "- Conserva intactos TODOS los campos que la instrucción no menciona "
    "(devuelve el config COMPLETO, no un parche).\n"
    "- No cambies ids existentes salvo que se pida. Mantén unidades y rangos."
)


def build_edit_prompt(cfg: IntersectionConfig, instruction: str) -> Tuple[str, str]:
    user = (
        "Configuración actual:\n```json\n"
        f"{cfg.model_dump_json(indent=2, exclude_none=True)}\n```\n\n"
        f"Instrucción: {instruction}\n\n"
        "Devuelve solo el JSON {\"config\": ..., \"summary\": ...}."
    )
    return _EDIT_SYSTEM, user


# --------------------------------------------------------------------------
# Parseo y validación de la respuesta (puro)
# --------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """Extrae el primer objeto JSON de la respuesta (tolera vallas ```)."""
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    i, j = t.find("{"), t.rfind("}")
    if 0 <= i < j:
        try:
            return json.loads(t[i:j + 1])
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "El copiloto no devolvió un JSON válido."
            ) from exc
    raise RuntimeError("El copiloto no devolvió un JSON válido.")


def _sanity_warnings(cfg: IntersectionConfig) -> List[str]:
    """Inconsistencias no fatales del config propuesto."""
    warnings: List[str] = []
    group_ids = {
        lg.id for ap in cfg.approaches for lg in ap.lane_groups
    }
    for ph in cfg.phases:
        missing = [g for g in ph.lane_group_ids if g not in group_ids]
        # Permitimos ids "peatonales" que no son grupos vehiculares.
        real_missing = [g for g in missing if not g.upper().startswith(("PED", "PEA"))]
        if real_missing:
            warnings.append(
                f"La fase '{ph.id}' referencia grupos inexistentes: "
                f"{', '.join(real_missing)}."
            )
    for d in cfg.demand:
        if d.lane_group_id not in group_ids:
            warnings.append(
                f"La demanda referencia un grupo inexistente: '{d.lane_group_id}'."
            )
    return warnings


def parse_edit_response(raw: str) -> Tuple[IntersectionConfig, str, List[str]]:
    """(config validado, resumen, avisos) a partir de la respuesta cruda."""
    data = _extract_json(raw)
    cfg_dict = data.get("config")
    if cfg_dict is None:
        raise RuntimeError("La respuesta del copiloto no contiene 'config'.")
    summary = str(data.get("summary") or "(el copiloto no resumió el cambio)")
    try:
        cfg = IntersectionConfig(**cfg_dict)
    except Exception as exc:  # noqa: BLE001 — validación Pydantic u otros
        raise RuntimeError(
            f"El copiloto devolvió una configuración inválida: {exc}"
        ) from exc
    return cfg, summary, _sanity_warnings(cfg)


# --------------------------------------------------------------------------
# Llamada a la API (I/O, aislado)
# --------------------------------------------------------------------------

def _call_anthropic(system: str, user: str, *, max_tokens: int = 1500,
                    temperature: float = 0.2, timeout: int = 60) -> str:
    key = os.environ.get(ENV_KEY)
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY no configurada.")
    body = json.dumps({
        "model": _model(),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "x-api-key": key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(
            f"La API de Claude respondió {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"No se pudo contactar la API de Claude: {exc.reason}") from exc

    parts = [
        b.get("text", "")
        for b in payload.get("content", [])
        if b.get("type") == "text"
    ]
    text = "".join(parts).strip()
    if not text:
        raise RuntimeError("La API de Claude devolvió una respuesta vacía.")
    return text


# --------------------------------------------------------------------------
# Orquestación
# --------------------------------------------------------------------------

def _require_available() -> None:
    if not is_copilot_available():
        raise RuntimeError(
            "Copiloto no disponible: define ANTHROPIC_API_KEY en el entorno "
            "del backend."
        )


def explain_analysis(req: CopilotExplainRequest) -> CopilotExplainResult:
    _require_available()
    plan = _plan_for(req.config, req.method)
    an = analyze(req.config, plan)
    system, user = build_explain_prompt(req.config, an, plan, req.question)
    answer = _call_anthropic(system, user, max_tokens=1500)
    return CopilotExplainResult(answer=answer, model=_model())


def edit_config(req: CopilotEditRequest) -> CopilotEditResult:
    _require_available()
    system, user = build_edit_prompt(req.config, req.instruction)
    raw = _call_anthropic(system, user, max_tokens=4000, temperature=0.0)
    cfg, summary, warnings = parse_edit_response(raw)
    return CopilotEditResult(config=cfg, summary=summary, model=_model(), warnings=warnings)
