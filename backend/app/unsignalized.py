"""Análisis de intersecciones NO semaforizadas.

Dos métodos del Highway Capacity Manual 2010:

- TWSC (cap. 19) — calle secundaria con PARE; la principal circula libre.
- Glorieta / rotonda (cap. 22) — capacidad de entrada por aceptación de brechas.

Ambos se basan en teoría de aceptación de brechas (gap-acceptance). El nivel de
servicio para intersecciones no semaforizadas usa umbrales distintos a los del
semáforo (HCM Exhibit 19-1 / 22-3):

    A ≤ 10   B ≤ 15   C ≤ 25   D ≤ 35   E ≤ 50   F > 50   (s/veh)

Supuestos del módulo (declarados para que sean auditables):
- Calle principal de 2 carriles, una etapa de cruce (sin almacenamiento en
  mediana). Brechas críticas y tiempos de seguimiento: valores base HCM.
- El flujo conflictivo del giro a la derecha desde la calle secundaria se
  aproxima como el promedio de ambos sentidos de la principal.
- Glorieta validada para 4 ramas; capacidad de entrada multiplicada por el
  número de carriles de entrada (simplificación).
"""
from __future__ import annotations

import math
from typing import Dict, List

from .models import (
    IntersectionConfig,
    LOSGrade,
    MovementType,
    RoundaboutAnalysis,
    RoundaboutApproachResult,
    TWSCAnalysis,
    UnsignalizedMovement,
)

T_HOURS = 0.25  # periodo de análisis

# Brechas críticas (tc) y tiempos de seguimiento (tf) base — HCM cap. 19.
GAP = {
    "major_left": (4.1, 2.2),
    "minor_right": (6.2, 3.3),
    "minor_through": (6.5, 4.0),
    "minor_left": (7.5, 3.5),
}


def los_unsignalized(delay: float) -> LOSGrade:
    if delay <= 10:
        return LOSGrade.A
    if delay <= 15:
        return LOSGrade.B
    if delay <= 25:
        return LOSGrade.C
    if delay <= 35:
        return LOSGrade.D
    if delay <= 50:
        return LOSGrade.E
    return LOSGrade.F


DELAY_CAP = 999.0  # tope de demora mostrada; por encima la operación es inviable


def _gap_delay(volume: float, capacity: float) -> float:
    """Demora de control por aceptación de brechas (HCM eq. 19-x / 22-x)."""
    if capacity <= 0:
        return DELAY_CAP
    x = volume / capacity
    inside = (x - 1.0) ** 2 + (3600.0 / capacity) * x / (450.0 * T_HOURS)
    d = 3600.0 / capacity + 900.0 * T_HOURS * ((x - 1.0) + math.sqrt(max(0.0, inside))) + 5.0
    return min(DELAY_CAP, d)


def _potential_capacity(vc: float, tc: float, tf: float) -> float:
    """Capacidad potencial cp,x (veh/h) — fórmula de Siegloch / HCM."""
    if vc <= 0:
        return 3600.0 / tf
    num = vc * math.exp(-vc * tc / 3600.0)
    den = 1.0 - math.exp(-vc * tf / 3600.0)
    if den <= 1e-9:
        return 3600.0 / tf
    return num / den


def _mvt_volume(cfg: IntersectionConfig, approach, mvt: MovementType) -> float:
    """Demanda ajustada (PCU/PHF) de un acceso para un tipo de movimiento."""
    total = 0.0
    for lg in approach.lane_groups:
        if lg.movement == mvt:
            total += cfg.demand_for(lg.id)
    return total


def analyze_twsc(cfg: IntersectionConfig, major_ids: List[str]) -> TWSCAnalysis:
    """Análisis TWSC — PARE en la calle secundaria."""
    warnings: List[str] = []
    major_set = set(major_ids)
    majors = [a for a in cfg.approaches if a.id in major_set]
    minors = [a for a in cfg.approaches if a.id not in major_set]

    if not majors or not minors:
        warnings.append(
            "Se requiere al menos un acceso mayor y uno menor. "
            "Revise la asignación de la calle principal."
        )

    # Volúmenes agregados de la calle principal.
    VT_maj = sum(_mvt_volume(cfg, a, MovementType.THROUGH) for a in majors)
    VR_maj = sum(_mvt_volume(cfg, a, MovementType.RIGHT) for a in majors)
    VL_maj = sum(_mvt_volume(cfg, a, MovementType.LEFT) for a in majors)

    # --- Flujos conflictivos y brechas por movimiento controlado ---
    # Estructura interna por lane_group: dict con vc, tc, tf, rank, volume.
    plan: Dict[str, dict] = {}

    for a in majors:
        for lg in a.lane_groups:
            v = cfg.demand_for(lg.id)
            if lg.movement == MovementType.LEFT:
                # Giro izquierda mayor: conflicta con el sentido opuesto.
                other = [m for m in majors if m.id != a.id]
                vc = sum(_mvt_volume(cfg, m, MovementType.THROUGH) +
                         _mvt_volume(cfg, m, MovementType.RIGHT) for m in other)
                tc, tf = GAP["major_left"]
                plan[lg.id] = dict(rank=2, vc=vc, tc=tc, tf=tf, volume=v,
                                   approach=a.id, movement=lg.movement,
                                   role="mayor-giro-izq")
            else:
                # Directo / derecha mayor: flujo libre (rango 1).
                plan[lg.id] = dict(rank=1, vc=None, volume=v,
                                   approach=a.id, movement=lg.movement,
                                   role="mayor-libre")

    for a in minors:
        other_minor = [m for m in minors if m.id != a.id]
        vT_opp = sum(_mvt_volume(cfg, m, MovementType.THROUGH) for m in other_minor)
        vR_opp = sum(_mvt_volume(cfg, m, MovementType.RIGHT) for m in other_minor)
        for lg in a.lane_groups:
            v = cfg.demand_for(lg.id)
            if lg.movement == MovementType.RIGHT:
                vc = 0.5 * VT_maj + 0.25 * VR_maj
                tc, tf = GAP["minor_right"]
                rank = 2
            elif lg.movement == MovementType.THROUGH:
                vc = VT_maj + 0.5 * VR_maj + VL_maj
                tc, tf = GAP["minor_through"]
                rank = 3
            else:  # LEFT
                vc = VT_maj + 0.5 * VR_maj + VL_maj + vT_opp + vR_opp
                tc, tf = GAP["minor_left"]
                rank = 4
            plan[lg.id] = dict(rank=rank, vc=vc, tc=tc, tf=tf, volume=v,
                               approach=a.id, movement=lg.movement, role="menor")

    # --- Capacidad de movimiento con impedancia por rango ---
    for d in plan.values():
        if d["rank"] == 1:
            continue
        d["cp"] = _potential_capacity(d["vc"], d["tc"], d["tf"])

    # Rango 2: cm = cp.
    for d in plan.values():
        if d["rank"] == 2:
            d["cm"] = d["cp"]

    def p0(d: dict) -> float:
        cm = d.get("cm", 0.0)
        if cm <= 0:
            return 0.0
        return max(0.0, 1.0 - d["volume"] / cm)

    rank2 = [d for d in plan.values() if d["rank"] == 2]
    imp_r2 = 1.0
    for d in rank2:
        imp_r2 *= p0(d)

    # Rango 3: impedido por rango 2.
    for d in plan.values():
        if d["rank"] == 3:
            d["cm"] = d["cp"] * imp_r2

    rank3 = [d for d in plan.values() if d["rank"] == 3]
    imp_r3 = 1.0
    for d in rank3:
        imp_r3 *= p0(d)

    # Rango 4: impedido por rango 2 y 3.
    for d in plan.values():
        if d["rank"] == 4:
            d["cm"] = d["cp"] * imp_r2 * imp_r3

    # --- Resultados por movimiento ---
    movements: List[UnsignalizedMovement] = []
    num = 0.0
    den = 0.0
    worst_delay = -1.0
    worst_id = None

    for lg_id, d in plan.items():
        if d["rank"] == 1:
            movements.append(UnsignalizedMovement(
                lane_group_id=lg_id, approach_id=d["approach"], role=d["role"],
                movement=d["movement"], demand=round(d["volume"], 1),
                conflicting_flow=None, capacity=None, v_c_ratio=None,
                avg_delay_s=0.0, los=LOSGrade.A))
            den += d["volume"]
            continue
        cm = d.get("cm", 0.0)
        delay = _gap_delay(d["volume"], cm)
        x = d["volume"] / cm if cm > 0 else 99.0
        los = los_unsignalized(delay)
        movements.append(UnsignalizedMovement(
            lane_group_id=lg_id, approach_id=d["approach"], role=d["role"],
            movement=d["movement"], demand=round(d["volume"], 1),
            conflicting_flow=round(d["vc"], 1), capacity=round(cm, 1),
            v_c_ratio=round(min(x, 99.0), 3), avg_delay_s=round(delay, 1),
            los=los))
        num += delay * d["volume"]
        den += d["volume"]
        if delay > worst_delay:
            worst_delay = delay
            worst_id = lg_id

    avg = num / den if den > 0 else 0.0
    overall = los_unsignalized(avg)

    for m in movements:
        if m.los == LOSGrade.F:
            warnings.append(
                f"Movimiento '{m.lane_group_id}' en LOS F "
                f"(demora {m.avg_delay_s:.0f} s): supera la capacidad con PARE."
            )

    return TWSCAnalysis(
        config_name=cfg.name,
        major_approach_ids=list(major_ids),
        movements=movements,
        avg_delay_s=round(avg, 1),
        overall_los=overall,
        worst_movement=worst_id,
        warnings=warnings,
    )


def analyze_roundabout(
    cfg: IntersectionConfig,
    approach_order: List[str],
    circulating_lanes: int,
    entry_lanes: Dict[str, int],
) -> RoundaboutAnalysis:
    """Análisis de glorieta — capacidad de entrada (HCM cap. 22)."""
    warnings: List[str] = []
    order = approach_order or [a.id for a in cfg.approaches]
    n = len(order)
    by_id = {a.id: a for a in cfg.approaches}

    if n < 3:
        warnings.append("Una glorieta requiere al menos 3 ramas.")
    if n != 4:
        warnings.append(
            "Modelo validado para glorietas de 4 ramas; "
            "el flujo circulante en otras geometrías es aproximado."
        )

    # Flujo circulante: cada movimiento aporta a las entradas que atraviesa.
    # Regla (4 ramas, circulación estándar): un movimiento directo pasa frente
    # a 1 entrada; un giro a la izquierda, frente a 2; el giro a la derecha, 0.
    circulating: Dict[str, float] = {aid: 0.0 for aid in order}
    for i, aid in enumerate(order):
        ap = by_id.get(aid)
        if ap is None:
            continue
        vT = _mvt_volume(cfg, ap, MovementType.THROUGH)
        vL = _mvt_volume(cfg, ap, MovementType.LEFT)
        if n >= 2:
            circulating[order[(i + 1) % n]] += vT
        if n >= 3:
            circulating[order[(i + 1) % n]] += vL
            circulating[order[(i + 2) % n]] += vL

    # Capacidad de entrada: c = A * exp(-B * vc)  (HCM 2010).
    A = 1130.0
    B = 1.0e-3 if circulating_lanes == 1 else 0.7e-3

    results: List[RoundaboutApproachResult] = []
    num = 0.0
    den = 0.0

    for aid in order:
        ap = by_id.get(aid)
        if ap is None:
            warnings.append(f"Acceso '{aid}' no existe en la configuración.")
            continue
        entry_demand = sum(cfg.demand_for(lg.id) for lg in ap.lane_groups)
        vc = circulating[aid]
        n_entry = max(1, entry_lanes.get(aid, 1))
        capacity = A * math.exp(-B * vc) * n_entry
        x = entry_demand / capacity if capacity > 0 else 99.0
        # Demora de glorieta: como gap-delay con término +5*min(x,1).
        if capacity <= 0:
            delay = DELAY_CAP
        else:
            inside = (x - 1.0) ** 2 + (3600.0 / capacity) * x / (450.0 * T_HOURS)
            delay = min(DELAY_CAP, 3600.0 / capacity
                        + 900.0 * T_HOURS * ((x - 1.0) + math.sqrt(max(0.0, inside)))
                        + 5.0 * min(x, 1.0))
        los = los_unsignalized(delay)
        results.append(RoundaboutApproachResult(
            approach_id=aid, approach_name=ap.name,
            entry_demand=round(entry_demand, 1),
            circulating_flow=round(vc, 1),
            capacity=round(capacity, 1),
            v_c_ratio=round(min(x, 99.0), 3),
            avg_delay_s=round(delay, 1),
            los=los))
        num += delay * entry_demand
        den += entry_demand
        if los == LOSGrade.F:
            warnings.append(
                f"Acceso '{ap.name}' en LOS F (demora {delay:.0f} s): "
                "la glorieta no absorbe esta demanda."
            )

    avg = num / den if den > 0 else 0.0
    return RoundaboutAnalysis(
        config_name=cfg.name,
        circulating_lanes=circulating_lanes,
        approaches=results,
        avg_delay_s=round(avg, 1),
        overall_los=los_unsignalized(avg),
        warnings=warnings,
    )
