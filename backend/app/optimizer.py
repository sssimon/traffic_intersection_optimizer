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
    clamped: List[str] = []

    n_phases = len(cfg.phases)
    for i, ph in enumerate(cfg.phases):
        if Y > 0:
            target = effective_green_total * (y_per_phase[i] / Y)
        else:
            target = effective_green_total / n_phases
        # El verde se acota a [min_green, max_green]: los límites de la fase
        # (seguridad, diseño del semáforo) mandan sobre el reparto proporcional.
        # No se reescala después: escalar un verde ya acotado fue el origen
        # del bug que podía devolver verdes fuera de rango.
        g = max(ph.min_green, min(ph.max_green, target))
        if abs(g - target) > 0.1:
            clamped.append(ph.id)
        green_per_phase[ph.id] = round(g, 1)
        yellow[ph.id] = ph.yellow
        all_red[ph.id] = ph.all_red

    if Y <= 0:
        notes.append("No hay demanda registrada; verde distribuido equitativamente.")
    if clamped:
        notes.append(
            "El verde de la(s) fase(s) " + ", ".join(clamped)
            + " se acotó a [min_green, max_green]; con demanda muy "
            "desbalanceada la suma de tiempos puede no igualar el ciclo. "
            "Revise el número de fases o la geometría de la intersección."
        )

    return SignalPlan(
        cycle_length=round(cycle, 1),
        phase_green=green_per_phase,
        phase_yellow=yellow,
        phase_all_red=all_red,
        total_lost_time=round(L, 1),
        notes=notes,
    )
