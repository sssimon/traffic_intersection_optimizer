"""Comparación de escenarios y recomendación de gestión de congestión.

Cada escenario aplica un multiplicador uniforme a la demanda. Se evalúa con
optimización Webster + análisis HCM y se recomienda una estrategia según el
peor LOS y la saturación.
"""
from __future__ import annotations

from copy import deepcopy
from typing import List

from .analysis import analyze
from .models import (
    Demand,
    IntersectionAnalysis,
    IntersectionConfig,
    LOSGrade,
    ScenarioComparison,
    ScenarioRequest,
    ScenarioResult,
)
from .optimizer import optimize


def _scale_demand(cfg: IntersectionConfig, factor: float) -> IntersectionConfig:
    new_cfg = cfg.model_copy(deep=True)
    new_cfg.demand = [
        Demand(lane_group_id=d.lane_group_id, volume=d.volume * factor, pcu_factor=d.pcu_factor)
        for d in cfg.demand
    ]
    return new_cfg


def _strategy(worst: ScenarioResult) -> tuple[str, List[str]]:
    los = worst.analysis.overall_los
    vc = worst.analysis.overall_v_c
    cycle = worst.analysis.signal_plan.cycle_length
    rationale: List[str] = []

    if los in (LOSGrade.A, LOSGrade.B, LOSGrade.C):
        rationale.append(f"Peor escenario alcanza LOS {los.value} con X={vc:.2f}: operación aceptable.")
        rationale.append("Mantener el plan optimizado y reevaluar trimestralmente.")
        return ("Operación normal — plan pretimed optimizado por Webster.", rationale)

    if los == LOSGrade.D:
        rationale.append(f"LOS D, X={vc:.2f}: cercano a saturación.")
        rationale.append("Implementar control adaptativo (actuated) para responder a fluctuaciones.")
        rationale.append("Revisar coordinación con intersecciones vecinas (onda verde).")
        return ("Control semáforo actuado + coordinación", rationale)

    if los == LOSGrade.E:
        rationale.append(f"LOS E, X={vc:.2f}: capacidad excedida en hora pico.")
        rationale.append(f"Ciclo en {cycle:.0f}s; considerar fases por demanda específica (left-lead/lag).")
        rationale.append("Habilitar carril de giro exclusivo en accesos críticos si la geometría lo permite.")
        rationale.append("Estudio de redistribución de flujos por señalización en la red.")
        return ("Re-diseño de fases + ampliación de capacidad geométrica", rationale)

    # LOS F
    rationale.append(f"LOS F, X={vc:.2f}: intersección colapsada — Webster no resuelve por sí solo.")
    rationale.append("Gestión activa de demanda: desvíos, peaje urbano, restricción horaria.")
    rationale.append("Control adaptativo en red (SCOOT/SCATS-like) con prioridad de descarga.")
    rationale.append("Evaluar paso a desnivel o rediseño geométrico mayor (rotonda turbo, glorieta semaforizada).")
    return ("Gestión de demanda + control adaptativo en red", rationale)


def compare(req: ScenarioRequest) -> ScenarioComparison:
    results: List[ScenarioResult] = []
    base_plan = optimize(req.config) if req.use_optimized_timing else None

    for m in req.multipliers:
        scaled = _scale_demand(req.config, m.factor)
        plan = optimize(scaled) if req.use_optimized_timing else (base_plan or optimize(req.config))
        analysis = analyze(scaled, plan)
        results.append(ScenarioResult(name=m.name, factor=m.factor, analysis=analysis))

    worst = max(results, key=lambda r: r.analysis.avg_delay_s) if results else None
    if worst is None:
        return ScenarioComparison(
            scenarios=[],
            recommended_strategy="Sin escenarios para comparar.",
            rationale=[],
        )

    strategy, rationale = _strategy(worst)
    return ScenarioComparison(
        scenarios=results,
        recommended_strategy=strategy,
        rationale=rationale,
    )
