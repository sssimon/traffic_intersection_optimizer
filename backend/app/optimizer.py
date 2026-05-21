"""Optimización de tiempos de semáforo (Webster 1958).

Fórmulas:

    yi = max(v/s)  para los grupos de carril en la fase i (flujo crítico)
    Y  = Σ yi      sobre todas las fases
    L  = Σ Li      tiempo perdido total por ciclo
    Co = (1.5·L + 5) / (1 - Y)      ciclo óptimo
    gi = (Co - L) · (yi / Y)        verde efectivo por fase

Restricciones:
- Ciclo en [Cmin, Cmax] — típicamente [40, 120] s.
- Cada fase recibe al menos su `min_green` y a lo más `max_green`.
- Si Y ≥ 0.95 la intersección está sobre-saturada: se devuelve ciclo máximo.
"""
from __future__ import annotations

from typing import List

from .models import IntersectionConfig, Phase, SignalPlan


CYCLE_MIN = 40.0
CYCLE_MAX = 120.0
Y_OVERSATURATED = 0.95


def _phase_critical_ratio(cfg: IntersectionConfig, phase: Phase) -> float:
    """yi = max sobre los grupos de la fase de (demanda / saturación)."""
    ratios: List[float] = []
    for lg_id in phase.lane_group_ids:
        lg = cfg.lane_group(lg_id)
        if lg is None:
            continue
        s = lg.saturation_flow
        if s <= 0:
            continue
        v = cfg.demand_for(lg_id)
        ratios.append(v / s)
    return max(ratios) if ratios else 0.0


def optimize(cfg: IntersectionConfig) -> SignalPlan:
    notes: List[str] = []

    y_per_phase = [_phase_critical_ratio(cfg, ph) for ph in cfg.phases]
    Y = sum(y_per_phase)

    L = sum(ph.lost_time for ph in cfg.phases)

    if Y >= Y_OVERSATURATED:
        cycle = CYCLE_MAX
        notes.append(
            f"Intersección sobre-saturada (Y={Y:.2f} ≥ {Y_OVERSATURATED}). "
            "Se aplica ciclo máximo; se requieren medidas de gestión de demanda."
        )
    else:
        cycle = (1.5 * L + 5.0) / (1.0 - Y)

    cycle = max(CYCLE_MIN, min(CYCLE_MAX, cycle))

    effective_green_total = cycle - L
    if effective_green_total <= 0:
        effective_green_total = max(10.0, cycle * 0.5)
        notes.append("Tiempo perdido excede el ciclo; se ajustó verde total.")

    green_per_phase: dict[str, float] = {}
    yellow: dict[str, float] = {}
    all_red: dict[str, float] = {}

    if Y > 0:
        for ph, yi in zip(cfg.phases, y_per_phase):
            g = effective_green_total * (yi / Y) if Y > 0 else effective_green_total / len(cfg.phases)
            g = max(ph.min_green, min(ph.max_green, g))
            green_per_phase[ph.id] = round(g, 1)
            yellow[ph.id] = ph.yellow
            all_red[ph.id] = ph.all_red
    else:
        equal = effective_green_total / max(1, len(cfg.phases))
        for ph in cfg.phases:
            green_per_phase[ph.id] = round(max(ph.min_green, equal), 1)
            yellow[ph.id] = ph.yellow
            all_red[ph.id] = ph.all_red
        notes.append("No hay demanda registrada; verde distribuido equitativamente.")

    # Reescalar para que la suma de tiempos coincida con el ciclo.
    total = sum(green_per_phase.values()) + sum(yellow.values()) + sum(all_red.values())
    if abs(total - cycle) > 0.5 and total > 0:
        scale = (cycle - sum(yellow.values()) - sum(all_red.values())) / sum(green_per_phase.values())
        if scale > 0:
            for k in green_per_phase:
                green_per_phase[k] = round(green_per_phase[k] * scale, 1)

    return SignalPlan(
        cycle_length=round(cycle, 1),
        phase_green=green_per_phase,
        phase_yellow=yellow,
        phase_all_red=all_red,
        total_lost_time=round(L, 1),
        notes=notes,
    )
