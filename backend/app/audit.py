"""Modo auditoría (tarea 2.4): traza de cálculo verificable por movimiento.

Cada número del análisis se presenta con su fórmula, la sustitución
numérica y la fuente citada, para que un revisor pueda verificarlo contra
el manual con una calculadora — sin leer código.

Integridad: este módulo NO re-transcribe fórmulas. Los valores provienen de
los mismos núcleos que usa el análisis (`movement_performance_full`,
`back_of_queue_detail`, `SaturationFactors.breakdown`); aquí solo se
construyen las cadenas de presentación. La igualdad traza ↔ análisis está
garantizada por construcción y cubierta por tests.
"""
from __future__ import annotations

import math
from typing import List

from .analysis import (
    I_FACTOR,
    K_FACTOR,
    PF_FACTOR,
    QUEUE_FB95_P1,
    QUEUE_FB95_P2,
    QUEUE_FB95_P3,
    T_HOURS,
    ZERO_CAPACITY_DELAY,
    back_of_queue_detail,
    movement_performance_full,
)
from .models import (
    AuditStep,
    IntersectionConfig,
    LaneGroup,
    MovementAudit,
    SignalPlan,
)

_LOS_RANGES = [
    (10.0, "A"), (20.0, "B"), (35.0, "C"), (55.0, "D"), (80.0, "E"),
]

SRC_HCM18 = "HCM 2010, cap. 18 (intersecciones semaforizadas)"
SRC_QUEUE = "HCM 2000, cap. 16 ap. G (≡ HCM 2010, cap. 31)"


def _f(x: float) -> str:
    """Número compacto para las sustituciones."""
    if not math.isfinite(x):
        return "∞"
    return f"{x:.4g}"


def _los_text(d: float) -> str:
    prev = 0.0
    for limit, letter in _LOS_RANGES:
        if d <= limit:
            lo = f"{prev:.0f} < " if prev > 0 else ""
            return f"{lo}d ≤ {limit:.0f} → LOS {letter}"
        prev = limit
    return f"d > 80 → LOS F"


def _movement_audit(
    cfg: IntersectionConfig, plan: SignalPlan, lg: LaneGroup, phase_id: str
) -> MovementAudit:
    C = plan.cycle_length
    g = plan.phase_green.get(phase_id, 0.0)
    entry = next((d for d in cfg.demand if d.lane_group_id == lg.id), None)
    raw = entry.volume if entry else 0.0
    pcu = entry.pcu_factor if entry else 1.0
    phf = cfg.peak_hour_factor

    v = cfg.demand_for(lg.id)
    s = lg.saturation_flow
    perf = movement_performance_full(v, s, g, C)
    q = back_of_queue_detail(v, perf.capacity, s, lg.lanes, g, C)

    steps: List[AuditStep] = []

    steps.append(AuditStep(
        concept="Demanda de diseño",
        formula="v = V·PCU / PHF",
        substitution=f"{_f(raw)}·{_f(pcu)} / {_f(phf)}",
        value=round(v, 1),
        units="veh/h",
        source="HCM: PCU ≡ ajuste fHV (en la demanda) y factor de hora pico",
    ))

    if lg.factors is not None:
        parts = lg.factors.breakdown(lg.lanes, lg.movement, lg.shared_with_through)
        names = "·".join(name.split()[0] for name, _ in parts) if parts else "1"
        chain_sub = "·".join(
            f"{_f(val)} ({name})" for name, val in parts
        ) if parts else "1"
        sub = f"{_f(lg.saturation_flow_per_lane)}·{lg.lanes}·{chain_sub}"
        formula = f"s = s₀·N·{names}"
    else:
        sub = f"{_f(lg.saturation_flow_per_lane)}·{lg.lanes}"
        formula = "s = s₀·N"
    if lg.shared_with_through:
        sub += "·0.85 (compartido)"
        formula += "·0.85"
    steps.append(AuditStep(
        concept="Flujo de saturación",
        formula=formula,
        substitution=sub,
        value=round(s, 1),
        units="veh/h",
        source=SRC_HCM18 + ", ec. 18-5 y factores de ajuste",
    ))

    steps.append(AuditStep(
        concept="Capacidad",
        formula="c = s·g/C",
        substitution=f"{_f(s)}·{_f(g)}/{_f(C)}",
        value=round(perf.capacity, 1),
        units="veh/h",
        source=SRC_HCM18,
    ))

    steps.append(AuditStep(
        concept="Grado de saturación",
        formula="X = v/c",
        substitution=(
            f"{_f(v)}/{_f(perf.capacity)}" if perf.capacity > 0
            else "capacidad nula (g = 0)"
        ),
        value=round(perf.x_ratio, 3) if math.isfinite(perf.x_ratio) else 99.0,
        units="—",
        source=SRC_HCM18,
    ))

    steps.append(AuditStep(
        concept="Demora uniforme d1",
        formula="d1 = 0.5·C·(1−g/C)² / (1−min(1,X)·g/C)",
        substitution=(
            f"0.5·{_f(C)}·(1−{_f(perf.g_over_c)})² / "
            f"(1−{_f(perf.x_capped)}·{_f(perf.g_over_c)})"
        ),
        value=round(perf.d1, 2),
        units="s/veh",
        source=SRC_HCM18,
    ))

    if perf.capacity > 0 and math.isfinite(perf.x_ratio):
        steps.append(AuditStep(
            concept="Demora incremental d2",
            formula="d2 = 900·T·[(X−1) + √((X−1)² + 8·k·I·X/(c·T))]",
            substitution=(
                f"900·{_f(T_HOURS)}·[({_f(perf.x_ratio)}−1) + √(…+ "
                f"8·{_f(K_FACTOR)}·{_f(I_FACTOR)}·{_f(perf.x_ratio)}/"
                f"({_f(perf.capacity)}·{_f(T_HOURS)}))]"
            ),
            value=round(perf.d2, 2),
            units="s/veh",
            source=SRC_HCM18 + f" — k={K_FACTOR} pretimed, I={I_FACTOR} aislada, T={T_HOURS} h",
        ))
    else:
        steps.append(AuditStep(
            concept="Demora incremental d2 (sin capacidad)",
            formula=f"d2 = {ZERO_CAPACITY_DELAY:.0f} (valor de referencia declarado)",
            substitution="movimiento sin verde: demora no acotada por el modelo",
            value=round(perf.d2, 2),
            units="s/veh",
            source="Supuesto declarado del motor (cae en LOS F sin propagar infinitos)",
        ))

    steps.append(AuditStep(
        concept="Demora de control",
        formula="d = d1·PF + d2",
        substitution=f"{_f(perf.d1)}·{_f(PF_FACTOR)} + {_f(perf.d2)}",
        value=round(perf.delay, 1),
        units="s/veh",
        source=SRC_HCM18 + " — PF=1.0: llegadas aleatorias (aislada)",
    ))

    steps.append(AuditStep(
        concept="Nivel de servicio",
        formula="umbrales HCM semaforizado: 10/20/35/55/80",
        substitution=_los_text(perf.delay),
        value=round(perf.delay, 1),
        units="s/veh",
        source=SRC_HCM18,
    ))

    steps.append(AuditStep(
        concept="Cola uniforme Q1 (por carril)",
        formula="Q1 = vL·(C−g) / (1−min(1,X)·g/C), vL en veh/s",
        substitution=(
            f"({_f(q.v_lane)}/3600)·{_f(q.r)} / "
            f"(1−{_f(min(1.0, q.x) if math.isfinite(q.x) else 1.0)}·{_f(q.u)})"
        ),
        value=round(q.q1, 2),
        units="veh",
        source=SRC_QUEUE,
    ))

    if q.c_lane > 0:
        steps.append(AuditStep(
            concept="Cola incremental Q2 (por carril)",
            formula=(
                "Q2 = 0.25·cL·T·[(X−1) + √((X−1)² + 8·kB·X/(cL·T))], "
                "kB = 0.12·I·(sL·g/3600)^0.7"
            ),
            substitution=(
                f"kB={_f(q.k_b)}; 0.25·{_f(q.c_lane)}·{_f(T_HOURS)}·"
                f"[({_f(q.x)}−1) + √(…)]"
            ),
            value=round(q.q2, 2),
            units="veh",
            source=SRC_QUEUE + " — kB pretimed",
        ))
    else:
        steps.append(AuditStep(
            concept="Cola incremental Q2 (sin capacidad)",
            formula="Q2 = vL·T/2 (crecimiento lineal; límite de la fórmula con cL→0)",
            substitution=f"{_f(q.v_lane)}·{_f(T_HOURS)}/2",
            value=round(q.q2, 2),
            units="veh",
            source=SRC_QUEUE + " — caso declarado del motor",
        ))

    steps.append(AuditStep(
        concept="Cola percentil 95 (por carril)",
        formula=(
            f"Q95 = ({QUEUE_FB95_P1} + {QUEUE_FB95_P2}·e^(−Q/{QUEUE_FB95_P3:.0f}))·Q, "
            "Q = Q1 + Q2"
        ),
        substitution=f"{_f(q.f_b95)}·{_f(q.q_avg)}",
        value=round(q.q95, 1),
        units="veh/carril",
        source=SRC_QUEUE + " — factor percentil pretimed",
    ))

    return MovementAudit(lane_group_id=lg.id, phase_id=phase_id, steps=steps)


def build_audit(cfg: IntersectionConfig, plan: SignalPlan) -> List[MovementAudit]:
    """Traza de cálculo de todos los movimientos asignados a fase."""
    out: List[MovementAudit] = []
    for ap in cfg.approaches:
        for lg in ap.lane_groups:
            phase_id = next(
                (ph.id for ph in cfg.phases if lg.id in ph.lane_group_ids), None
            )
            if phase_id is None:
                continue
            out.append(_movement_audit(cfg, plan, lg, phase_id))
    return out
