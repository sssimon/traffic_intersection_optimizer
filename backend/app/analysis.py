"""Análisis de capacidad y demora — HCM 2010 (Capítulo 18).

Para cada movimiento (grupo de carriles) calcula:

    c  = s · g/C                            capacidad (veh/h)
    X  = v/c                                grado de saturación
    d1 = 0.5·C·(1 - g/C)² / (1 - min(1,X)·g/C)    demora uniforme
    d2 = 900·T·[(X-1) + √((X-1)² + 8·k·I·X/(c·T))]  demora incremental
    d  = d1·PF + d2                         demora promedio por vehículo

LOS (HCM):  A ≤10 < B ≤20 < C ≤35 < D ≤55 < E ≤80 < F
Cola 95-percentil aproximada: Q95 = 2 · Q_promedio  con Q_promedio ≈ v·r·(1-(g/C))
"""
from __future__ import annotations

import math
from typing import List

from .models import (
    IntersectionAnalysis,
    IntersectionConfig,
    LOSGrade,
    MovementAnalysis,
    SignalPlan,
)


T_HOURS = 0.25   # periodo de análisis (15 min, HCM)
K_FACTOR = 0.5   # k: controlador pretimed
I_FACTOR = 1.0   # I: intersección aislada
PF_FACTOR = 1.0  # PF: factor por progresión (1.0 = llegadas aleatorias)


def _los_from_delay(d: float) -> LOSGrade:
    if d <= 10:
        return LOSGrade.A
    if d <= 20:
        return LOSGrade.B
    if d <= 35:
        return LOSGrade.C
    if d <= 55:
        return LOSGrade.D
    if d <= 80:
        return LOSGrade.E
    return LOSGrade.F


def _phase_id_for(cfg: IntersectionConfig, lg_id: str) -> str | None:
    for ph in cfg.phases:
        if lg_id in ph.lane_group_ids:
            return ph.id
    return None


def analyze(cfg: IntersectionConfig, plan: SignalPlan) -> IntersectionAnalysis:
    movements: List[MovementAnalysis] = []
    warnings: List[str] = []
    weighted_delay_num = 0.0
    weighted_delay_den = 0.0
    max_vc = 0.0

    C = plan.cycle_length

    for ap in cfg.approaches:
        for lg in ap.lane_groups:
            phase_id = _phase_id_for(cfg, lg.id)
            if phase_id is None:
                warnings.append(f"Grupo '{lg.id}' no está asignado a ninguna fase.")
                continue
            g = plan.phase_green.get(phase_id, 0.0)
            s = lg.saturation_flow
            v = cfg.demand_for(lg.id)

            if C <= 0 or g <= 0:
                capacity = 0.0
                X = float("inf") if v > 0 else 0.0
            else:
                capacity = s * (g / C)
                X = v / capacity if capacity > 0 else float("inf")

            g_over_C = (g / C) if C > 0 else 0.0
            X_capped = min(1.0, X) if math.isfinite(X) else 1.0

            denom = 1.0 - X_capped * g_over_C
            if denom <= 1e-6:
                d1 = 0.5 * C * (1.0 - g_over_C) ** 2 / 1e-6
            else:
                d1 = 0.5 * C * (1.0 - g_over_C) ** 2 / denom

            if capacity > 0 and math.isfinite(X):
                inside = (X - 1.0) ** 2 + (8.0 * K_FACTOR * I_FACTOR * X) / (capacity * T_HOURS)
                d2 = 900.0 * T_HOURS * ((X - 1.0) + math.sqrt(max(0.0, inside)))
            else:
                d2 = 300.0  # demora oversaturada de referencia

            d = d1 * PF_FACTOR + d2

            # Cola: vehículos atrapados al final del rojo, ajustada por X
            r = C - g
            q_avg = (v / 3600.0) * r * (1.0 / max(1e-6, 1.0 - min(0.95, X) * g_over_C))
            q_95 = 2.0 * q_avg

            los = _los_from_delay(d)
            movements.append(
                MovementAnalysis(
                    lane_group_id=lg.id,
                    phase_id=phase_id,
                    demand=round(v, 1),
                    capacity=round(capacity, 1),
                    v_c_ratio=round(X if math.isfinite(X) else 99.0, 3),
                    avg_delay_s=round(d, 1),
                    queue_95th_veh=round(q_95, 1),
                    los=los,
                )
            )

            weighted_delay_num += d * v
            weighted_delay_den += v
            if math.isfinite(X):
                max_vc = max(max_vc, X)

    avg_delay = weighted_delay_num / weighted_delay_den if weighted_delay_den > 0 else 0.0
    overall_los = _los_from_delay(avg_delay)

    if max_vc > 1.0:
        warnings.append(
            f"Algún movimiento supera capacidad (X máx = {max_vc:.2f}). "
            "Se forman colas residuales que no se disipan en un ciclo."
        )
    if avg_delay > 80:
        warnings.append("Demora promedio en LOS F — la intersección está colapsada.")

    return IntersectionAnalysis(
        config_name=cfg.name,
        signal_plan=plan,
        movements=movements,
        avg_delay_s=round(avg_delay, 1),
        overall_los=overall_los,
        overall_v_c=round(max_vc, 3),
        warnings=warnings,
    )
