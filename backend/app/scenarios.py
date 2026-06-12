"""Comparación de escenarios y recomendación de gestión de congestión.

Cada escenario aplica un factor global de demanda más ajustes direccionales
opcionales por acceso o por movimiento (M8): el crecimiento real rara vez es
uniforme — un desarrollo nuevo carga un solo acceso. Cada escenario se evalúa
con el optimizador elegido (Webster o minimización directa de demora HCM) +
análisis HCM, y se recomienda una estrategia según el peor escenario.
"""
from __future__ import annotations

from typing import List, Tuple

from .analysis import analyze
from .models import (
    Demand,
    DemandMultiplier,
    IntersectionConfig,
    LOSGrade,
    ScenarioComparison,
    ScenarioRequest,
    ScenarioResult,
)
from .optimizer import optimize
from .optimizer_delay import optimize_delay


def _effective_factor(
    spec: DemandMultiplier, approach_id: str, lane_group_id: str
) -> float:
    """Prioridad: movimiento > acceso > global."""
    if lane_group_id in spec.movement_factors:
        return spec.movement_factors[lane_group_id]
    if approach_id in spec.approach_factors:
        return spec.approach_factors[approach_id]
    return spec.factor


def _apply_spec(
    cfg: IntersectionConfig, spec: DemandMultiplier
) -> Tuple[IntersectionConfig, str]:
    """Config con la demanda escalada + etiqueta legible del escenario."""
    approach_of = {
        lg.id: ap.id for ap in cfg.approaches for lg in ap.lane_groups
    }
    new_cfg = cfg.model_copy(deep=True)
    new_cfg.demand = [
        Demand(
            lane_group_id=d.lane_group_id,
            volume=d.volume * _effective_factor(
                spec, approach_of.get(d.lane_group_id, ""), d.lane_group_id
            ),
            pcu_factor=d.pcu_factor,
        )
        for d in cfg.demand
    ]
    parts = [f"global ×{spec.factor:.2f}"]
    parts += [f"acceso {a} ×{f:.2f}" for a, f in spec.approach_factors.items()]
    parts += [f"{m} ×{f:.2f}" for m, f in spec.movement_factors.items()]
    return new_cfg, " · ".join(parts)


def _validate_spec_ids(cfg: IntersectionConfig, spec: DemandMultiplier) -> List[str]:
    """Advierte ids inexistentes (typos): el factor se ignora sin reventar."""
    warnings: List[str] = []
    approach_ids = {ap.id for ap in cfg.approaches}
    group_ids = {lg.id for ap in cfg.approaches for lg in ap.lane_groups}
    for a in spec.approach_factors:
        if a not in approach_ids:
            warnings.append(
                f"Escenario '{spec.name}': el acceso '{a}' no existe; "
                "se ignora su factor."
            )
    for m in spec.movement_factors:
        if m not in group_ids:
            warnings.append(
                f"Escenario '{spec.name}': el grupo '{m}' no existe; "
                "se ignora su factor."
            )
    return warnings


def _strategy(worst: ScenarioResult) -> tuple[str, List[str]]:
    los = worst.analysis.overall_los
    vc = worst.analysis.overall_v_c
    cycle = worst.analysis.signal_plan.cycle_length
    rationale: List[str] = []

    if los in (LOSGrade.A, LOSGrade.B, LOSGrade.C):
        rationale.append(f"Peor escenario alcanza LOS {los.value} con X={vc:.2f}: operación aceptable.")
        rationale.append("Mantener el plan optimizado y reevaluar trimestralmente.")
        return ("Operación normal — plan pretimed optimizado.", rationale)

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
    rationale.append(f"LOS F, X={vc:.2f}: intersección colapsada — la optimización de tiempos no resuelve por sí sola.")
    rationale.append("Gestión activa de demanda: desvíos, peaje urbano, restricción horaria.")
    rationale.append("Control adaptativo en red (SCOOT/SCATS-like) con prioridad de descarga.")
    rationale.append("Evaluar paso a desnivel o rediseño geométrico mayor (rotonda turbo, glorieta semaforizada).")
    return ("Gestión de demanda + control adaptativo en red", rationale)


def compare(req: ScenarioRequest) -> ScenarioComparison:
    optimizer = optimize_delay if req.method == "delay_min" else optimize
    results: List[ScenarioResult] = []
    warnings: List[str] = []

    # Con use_optimized_timing=False se evalúa la robustez del plan de la
    # demanda base (fijo) frente a los escenarios.
    base_plan = None if req.use_optimized_timing else optimizer(req.config)

    for spec in req.multipliers:
        warnings += _validate_spec_ids(req.config, spec)
        scaled, label = _apply_spec(req.config, spec)
        plan = optimizer(scaled) if req.use_optimized_timing else base_plan
        analysis = analyze(scaled, plan)
        results.append(ScenarioResult(
            name=spec.name,
            factor=spec.factor,
            directional=bool(spec.approach_factors or spec.movement_factors),
            label=label,
            analysis=analysis,
        ))

    worst = max(results, key=lambda r: r.analysis.avg_delay_s) if results else None
    if worst is None:
        return ScenarioComparison(
            scenarios=[],
            recommended_strategy="Sin escenarios para comparar.",
            rationale=[],
            warnings=warnings,
        )

    strategy, rationale = _strategy(worst)
    return ScenarioComparison(
        scenarios=results,
        recommended_strategy=strategy,
        rationale=rationale,
        warnings=warnings,
    )
