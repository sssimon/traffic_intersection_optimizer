"""Análisis de capacidad y demora — HCM 2010 (Capítulo 18).

Para cada movimiento (grupo de carriles) calcula:

    c  = s · g/C                            capacidad (veh/h)
    X  = v/c                                grado de saturación
    d1 = 0.5·C·(1 - g/C)² / (1 - min(1,X)·g/C)    demora uniforme
    d2 = 900·T·[(X-1) + √((X-1)² + 8·k·I·X/(c·T))]  demora incremental
    d  = d1·PF + d2                         demora promedio por vehículo

LOS (HCM):  A ≤10 < B ≤20 < C ≤35 < D ≤55 < E ≤80 < F

Cola (back of queue) por carril — HCM 2000 cap. 16 ap. G (Akçelik 1988);
el HCM 2010 cap. 31 conserva la misma estructura Q1 + Q2 · factor percentil:

    Q1  = vL·(C-g) / (1 - min(1,X)·g/C)        término uniforme (vL en veh/s)
    Q2  = 0.25·cL·T·[(X-1) + √((X-1)² + 8·kB·X/(cL·T))]   término incremental
    kB  = 0.12·I·(sL·g/3600)^0.7               controlador pretimed
    Q95 = (1.6 + 1.0·e^(-Q/5)) · Q             factor percentil 95 (pretimed)

Sin cola inicial (QbL = 0). Supuestos coherentes con la demora: llegadas
aleatorias (PF2 = 1), intersección aislada (I = 1), T = 0.25 h.
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

# Demora de referencia para un movimiento sin capacidad (g=0 o C=0): no puede
# servir demanda, su demora real no está acotada. Se usa un valor finito grande
# que cae claramente en LOS F (>80 s) sin propagar infinitos al promedio.
ZERO_CAPACITY_DELAY = 300.0

# Factor percentil 95 del back of queue, controlador pretimed (HCM 2000
# ap. G, tabla de factores):  fB95 = p1 + p2·e^(-Q/p3).
QUEUE_FB95_P1 = 1.6
QUEUE_FB95_P2 = 1.0
QUEUE_FB95_P3 = 5.0


def _back_of_queue_per_lane(
    v: float, capacity: float, s: float, lanes: int, g: float, C: float
) -> tuple[float, float]:
    """Cola media y percentil 95 (back of queue) por carril, en vehículos.

    `v`, `capacity` y `s` son totales del grupo de carriles (veh/h); se
    promedian por carril según el método del HCM (utilización igual).
    Sin capacidad (g=0 o C=0) la cola crece sin servicio: Q1 equivale a las
    llegadas de un ciclo y Q2 al promedio del crecimiento lineal del
    periodo (v·T/2), que es el límite de la fórmula incremental cuando
    cL → 0.
    """
    n = max(1, lanes)
    v_lane = v / n          # veh/h
    c_lane = capacity / n   # veh/h
    s_lane = s / n          # veh/h

    u = (g / C) if C > 0 else 0.0
    r = max(0.0, C - g)
    x = (v_lane / c_lane) if c_lane > 0 else (math.inf if v_lane > 0 else 0.0)

    # Q1 — término uniforme (vehículos en cola al disiparse el rojo)
    if r > 0:
        denom = 1.0 - min(1.0, x) * u
        q1 = (v_lane / 3600.0) * r / max(denom, 1e-6)
    else:
        q1 = 0.0

    # Q2 — término incremental (aleatoriedad + sobresaturación)
    if c_lane <= 0:
        q2 = 0.5 * v_lane * T_HOURS
    else:
        k_b = 0.12 * I_FACTOR * (s_lane * g / 3600.0) ** 0.7
        z = x - 1.0
        inside = z * z + 8.0 * k_b * x / (c_lane * T_HOURS)
        q2 = 0.25 * c_lane * T_HOURS * (z + math.sqrt(max(0.0, inside)))

    q_avg = q1 + q2
    f_b95 = QUEUE_FB95_P1 + QUEUE_FB95_P2 * math.exp(-q_avg / QUEUE_FB95_P3)
    return q_avg, f_b95 * q_avg


def movement_performance(v: float, s: float, g: float, C: float) -> tuple[float, float, float]:
    """Demora de control HCM, capacidad y grado de saturación de un movimiento.

    Devuelve (d, capacidad, X) con d = d1·PF + d2. Es el núcleo compartido
    entre el análisis (`analyze`) y el optimizador por minimización de demora
    (`optimizer_delay`): una sola transcripción de las fórmulas.
    """
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
        d2 = ZERO_CAPACITY_DELAY

    return d1 * PF_FACTOR + d2, capacity, X


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

            d, capacity, X = movement_performance(v, s, g, C)

            # Cola: back of queue por carril (HCM 2000 ap. G; ver helper)
            q_avg, q_95 = _back_of_queue_per_lane(
                v=v, capacity=capacity, s=s, lanes=lg.lanes, g=g, C=C
            )

            los = _los_from_delay(d)
            movements.append(
                MovementAnalysis(
                    lane_group_id=lg.id,
                    phase_id=phase_id,
                    demand=round(v, 1),
                    capacity=round(capacity, 1),
                    v_c_ratio=round(X if math.isfinite(X) else 99.0, 3),
                    avg_delay_s=round(d, 1),
                    back_of_queue_avg_veh=round(q_avg, 1),
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
