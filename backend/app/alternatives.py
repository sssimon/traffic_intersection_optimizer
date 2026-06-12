"""Explorador de alternativas de control (tarea 2.1) — pilar prescriptivo.

Responde la pregunta que ningún software clásico contesta de forma
integrada: ¿qué tipo de control merece esta intersección? Con la MISMA
demanda evalúa y rankea:

1. Semáforo con las fases configuradas (plan de mínima demora HCM).
2. Semáforo con fases por acceso (esquema partido auto-generado: cada
   acceso recibe su propia fase, todo protegido). Es el único esquema
   alternativo evaluable con honestidad: el motor no modela giros
   permitidos, así que esquemas de 2 fases con izquierdas compartidas
   quedan fuera (ver tarea 2.2).
3. PARE en la calle secundaria (TWSC), con la principal elegida por el
   usuario o, por defecto, los dos accesos de mayor demanda.

El ranking es por demora media ponderada sobre TODOS los vehículos (en
PARE la calle principal no se detiene y pondera con demora 0 — eso es
físicamente correcto, no un sesgo). Los umbrales de LOS difieren entre
control semaforizado (F > 80 s) y no semaforizado (F > 50 s): comparar
por demora, no por letra.

Las advertencias de aplicabilidad son criterios orientativos derivados
del propio análisis de capacidad (v/c y LOS), no un estudio formal de
warrants MUTCD.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from .analysis import analyze
from .models import (
    CompareControlsRequest,
    CompareControlsResult,
    ControlAlternative,
    IntersectionConfig,
    LOSGrade,
    Phase,
)
from .optimizer_delay import optimize_delay
from .unsignalized import analyze_twsc

# v/c a partir del cual un movimiento con PARE se considera al límite.
TWSC_VC_LIMIT = 0.85


def _approach_demand(cfg: IntersectionConfig, approach_id: str) -> float:
    ap = next(a for a in cfg.approaches if a.id == approach_id)
    return sum(cfg.demand_for(lg.id) for lg in ap.lane_groups)


def _default_majors(cfg: IntersectionConfig) -> List[str]:
    """Los dos accesos de mayor demanda como calle principal."""
    ranked = sorted(
        (a.id for a in cfg.approaches),
        key=lambda aid: _approach_demand(cfg, aid),
        reverse=True,
    )
    return ranked[:2]


def _phase_partition(phases: List[Phase]) -> set[frozenset[str]]:
    return {frozenset(ph.lane_group_ids) for ph in phases}


def _split_phasing_config(cfg: IntersectionConfig) -> Optional[IntersectionConfig]:
    """Config con fases por acceso (todo protegido); None si no aplica."""
    if len(cfg.approaches) < 2:
        return None
    new_cfg = cfg.model_copy(deep=True)
    new_cfg.phases = [
        Phase(
            id=f"S-{ap.id}",
            name=f"Acceso {ap.id}",
            lane_group_ids=[lg.id for lg in ap.lane_groups],
        )
        for ap in cfg.approaches
        if ap.lane_groups
    ]
    if len(new_cfg.phases) < 2:
        return None
    # Si el esquema del usuario YA es el partido, no duplicar.
    if _phase_partition(new_cfg.phases) == _phase_partition(cfg.phases):
        return None
    return new_cfg


def _signal_alternative(
    alt_id: str, name: str, cfg: IntersectionConfig, extra_notes: List[str]
) -> ControlAlternative:
    plan = optimize_delay(cfg)
    analysis = analyze(cfg, plan)
    worst_q = max(
        (m.queue_95th_veh for m in analysis.movements), default=0.0
    )
    notes = list(extra_notes)
    if analysis.overall_los == LOSGrade.F:
        notes.append("Opera en LOS F con esta demanda: revisar gestión de demanda o geometría.")
    return ControlAlternative(
        id=alt_id,
        kind="signal",
        name=name,
        avg_delay_s=analysis.avg_delay_s,
        overall_los=analysis.overall_los,
        overall_v_c=analysis.overall_v_c,
        cycle_length=plan.cycle_length,
        worst_queue_95th_veh=worst_q,
        notes=notes,
        signal=analysis,
    )


def _twsc_alternative(
    cfg: IntersectionConfig, majors: List[str]
) -> Tuple[ControlAlternative, List[str]]:
    twsc = analyze_twsc(cfg, majors)
    vcs = [m.v_c_ratio for m in twsc.movements if m.v_c_ratio is not None]
    max_vc = max(vcs) if vcs else 0.0
    notes: List[str] = []
    minor_f = [m for m in twsc.movements if m.los == LOSGrade.F]
    if minor_f:
        ids = ", ".join(m.lane_group_id for m in minor_f)
        notes.append(f"No viable con esta demanda: {ids} en LOS F bajo PARE.")
    elif max_vc >= TWSC_VC_LIMIT:
        notes.append(
            f"Movimiento menor al límite (v/c = {max_vc:.2f} ≥ {TWSC_VC_LIMIT}): "
            "poca reserva ante crecimiento."
        )
    alt = ControlAlternative(
        id="twsc",
        kind="twsc",
        name=f"PARE en secundaria (principal: {', '.join(majors)})",
        avg_delay_s=twsc.avg_delay_s,
        overall_los=twsc.overall_los,
        overall_v_c=round(min(max_vc, 99.0), 3),
        notes=notes,
        twsc=twsc,
    )
    return alt, twsc.warnings


def compare_controls(req: CompareControlsRequest) -> CompareControlsResult:
    cfg = req.config
    alternatives: List[ControlAlternative] = []
    warnings: List[str] = []

    # 1) Semáforo — fases configuradas.
    if cfg.phases:
        alternatives.append(
            _signal_alternative(
                "signal_current",
                "Semáforo — fases configuradas (mín. demora)",
                cfg,
                [],
            )
        )
    else:
        warnings.append(
            "La configuración no tiene fases: no se evaluó el semáforo con "
            "el esquema configurado."
        )

    # 2) Semáforo — fases por acceso (esquema partido auto-generado).
    split_cfg = _split_phasing_config(cfg)
    if split_cfg is not None:
        composition = " | ".join(
            f"{ph.id.removeprefix('S-')}: " + ", ".join(ph.lane_group_ids)
            for ph in split_cfg.phases
        )
        alternatives.append(
            _signal_alternative(
                "signal_split",
                "Semáforo — fases por acceso (auto-generado)",
                split_cfg,
                [
                    "Esquema generado automáticamente: cada acceso en su "
                    "propia fase, todos los movimientos protegidos. "
                    f"Fases: {composition}.",
                ],
            )
        )

    # 3) PARE en la calle secundaria.
    majors = [a for a in req.major_approach_ids if any(ap.id == a for ap in cfg.approaches)]
    for bad in req.major_approach_ids:
        if bad not in majors:
            warnings.append(f"El acceso '{bad}' no existe; se ignora para la calle principal.")
    if not majors:
        majors = _default_majors(cfg)
    if 0 < len(majors) < len(cfg.approaches):
        twsc_alt, twsc_warnings = _twsc_alternative(cfg, majors)
        alternatives.append(twsc_alt)
        warnings += twsc_warnings
    else:
        warnings.append(
            "No se evaluó PARE: se requiere al menos un acceso principal y "
            "uno secundario."
        )

    if not alternatives:
        return CompareControlsResult(
            alternatives=[],
            recommended_id="",
            rationale=["No hay alternativas evaluables con esta configuración."],
            warnings=warnings,
        )

    alternatives.sort(key=lambda a: a.avg_delay_s)
    winner = alternatives[0]

    rationale: List[str] = []
    if len(alternatives) > 1:
        runner = alternatives[1]
        rationale.append(
            f"Menor demora media: {winner.name} ({winner.avg_delay_s:.1f} s/veh "
            f"frente a {runner.avg_delay_s:.1f} de la siguiente alternativa)."
        )
    rationale.append(
        "La demora media pondera todos los vehículos de la intersección; "
        "con PARE la calle principal circula libre (demora 0)."
    )
    rationale.append(
        "Los umbrales de LOS difieren entre semáforo (F > 80 s) y PARE "
        "(F > 50 s): compare por demora, no por letra."
    )

    twsc_alt = next((a for a in alternatives if a.kind == "twsc"), None)
    if twsc_alt is not None:
        if twsc_alt.overall_los in (LOSGrade.A, LOSGrade.B, LOSGrade.C) and winner.kind == "twsc":
            rationale.append(
                "Criterio orientativo: con el PARE operando en LOS "
                f"{twsc_alt.overall_los.value}, un semáforo podría no estar "
                "justificado con esta demanda."
            )
        if any("No viable" in n for n in twsc_alt.notes):
            rationale.append(
                "El PARE no absorbe la demanda de la calle secundaria: un "
                "control semaforizado (u otra mejora) está justificado."
            )
    if winner.kind == "signal" and winner.overall_los == LOSGrade.F:
        rationale.append(
            "Ninguna alternativa opera aceptablemente: se recomienda la de "
            "menor demora y un estudio de gestión de demanda o rediseño "
            "geométrico."
        )

    return CompareControlsResult(
        alternatives=alternatives,
        recommended_id=winner.id,
        rationale=rationale,
        warnings=warnings,
    )
