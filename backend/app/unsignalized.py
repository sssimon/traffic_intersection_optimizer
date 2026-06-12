"""Análisis de intersecciones NO semaforizadas.

TWSC (HCM 2010, cap. 19; cap. 20 desde la 6.ª edición) — calle secundaria
con PARE; la principal circula libre. Se basa en teoría de aceptación de
brechas (gap-acceptance). El nivel de servicio no semaforizado usa umbrales
distintos a los del semáforo:

    A ≤ 10   B ≤ 15   C ≤ 25   D ≤ 35   E ≤ 50   F > 50   (s/veh)

Edición (tarea 1.3): los valores base de brecha crítica (tc) y tiempo de
seguimiento (tf) para calle principal de 2 carriles son idénticos en
HCM 2000 (Exhibit 17-5), HCM 2010 (Exhibits 19-10/11) y HCM 6.ª/7.ª ed.
(Exhibits 20-16/17) — verificado contra el capítulo 17 del HCM 2000.

Impedancia entre rangos (ec. 17-5 a 17-9 ≡ 19-43 a 19-49 del HCM 2010):
- Rango 3 (directo menor): impedido SOLO por los giros izquierda de la
  principal — no por los giros derecha menores.
- Rango 4 (izquierda menor, 4 ramas): p″ = p0(izq. mayores)·p0(directo menor
  opuesto); el ajuste p′ = 0.65p″ − p″/(p″+3) + 0.6√p″ corrige la
  dependencia estadística entre colas; luego f = p′·p0(derecha menor
  opuesta). En 3 ramas la izquierda menor opera como rango 3 (HCM).

Supuestos del módulo (declarados para que sean auditables):
- Calle principal de 2 carriles, una etapa de cruce (sin almacenamiento en
  mediana). Sin ajustes de tc/tf por pesados o pendiente (valores base);
  los pesados se modelan vía PCU en la demanda. En 3 ramas se aplica el
  ajuste geométrico t3,LT = −0.7 s a la brecha de la izquierda menor
  (ec. 17-1), verificado con el Ejemplo 1 del HCM 2000.
- Flujos conflictivos: aproximación de ambos sentidos para el giro derecha
  menor; las izquierdas de la principal cuentan DOBLE en el conflictivo de
  la izquierda menor (Exhibit 17-4: cruzan y luego convergen — verificado
  con la descomposición 870 = 2·150 + 250 + 20 + 300 del Ejemplo 1).
- Validación contra valores publicados: ver docs/validacion.md.
"""
from __future__ import annotations

import math
from typing import Dict, List

from .models import (
    IntersectionConfig,
    LOSGrade,
    MovementType,
    TWSCAnalysis,
    UnsignalizedMovement,
)

T_HOURS = 0.25  # periodo de análisis

# Brechas críticas (tc) y tiempos de seguimiento (tf) base para calle
# principal de DOS carriles — HCM 2000 Ex. 17-5 ≡ HCM 2010 Ex. 19-10/11.
# (Con principal de 4 carriles serían: derecha menor 6.9 e izquierda
# menor 7.5; el 7.5 que se usaba antes era el valor de 4 carriles.)
GAP = {
    "major_left": (4.1, 2.2),
    "minor_right": (6.2, 3.3),
    "minor_through": (6.5, 4.0),
    "minor_left": (7.1, 3.5),
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

    # Ajuste geométrico de 3 ramas (HCM 2000 ec. 17-1): t3,LT = 0.7 s se
    # RESTA de la brecha crítica de la izquierda menor en intersecciones T.
    is_three_leg = len(cfg.approaches) == 3

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
                # Las izquierdas de la principal cuentan doble (Exhibit 17-4).
                vc = VT_maj + 0.5 * VR_maj + 2.0 * VL_maj + vT_opp + vR_opp
                tc, tf = GAP["minor_left"]
                if is_three_leg:
                    tc -= 0.7
                rank = 4
            plan[lg.id] = dict(rank=rank, vc=vc, tc=tc, tf=tf, volume=v,
                               approach=a.id, movement=lg.movement, role="menor")

    # --- Capacidad de movimiento con impedancia por rango ---
    for d in plan.values():
        if d["rank"] == 1:
            continue
        d["cp"] = _potential_capacity(d["vc"], d["tc"], d["tf"])

    # Rango 2: cm = cp (sin impedancia).
    for d in plan.values():
        if d["rank"] == 2:
            d["cm"] = d["cp"]

    def p0(d: dict) -> float:
        cm = d.get("cm", 0.0)
        if cm <= 0:
            return 0.0
        return max(0.0, 1.0 - d["volume"] / cm)

    # Rango 3 (directo menor): impedido SOLO por los giros izquierda de la
    # principal (HCM 2000 ec. 17-6, j = movimientos 1 y 4).
    p_major_left = 1.0
    for d in plan.values():
        if d["rank"] == 2 and d["role"] == "mayor-giro-izq":
            p_major_left *= p0(d)

    for d in plan.values():
        if d["rank"] == 3:
            d["cm"] = d["cp"] * p_major_left

    # Rango 4 (izquierda menor): p″ = p0(izq. mayores)·p0(directo menor
    # opuesto); p′ = 0.65p″ − p″/(p″+3) + 0.6√p″ (ec. 17-8) corrige la
    # dependencia entre colas; f = p′·p0(derecha menor opuesta) (ec. 17-9).
    # Sin directo menor opuesto (3 ramas) opera como rango 3.
    for d in plan.values():
        if d["rank"] != 4:
            continue
        a = d["approach"]
        opp_through = [
            e for e in plan.values()
            if e["rank"] == 3 and e["approach"] != a
        ]
        opp_right = [
            e for e in plan.values()
            if e["rank"] == 2 and e["role"] == "menor"
            and e["movement"] == MovementType.RIGHT and e["approach"] != a
        ]
        p0_opp_right = 1.0
        for e in opp_right:
            p0_opp_right *= p0(e)

        if opp_through:
            p2 = p_major_left
            for e in opp_through:
                p2 *= p0(e)
            p_prime = 0.65 * p2 - p2 / (p2 + 3.0) + 0.6 * math.sqrt(p2)
            f = p_prime * p0_opp_right
        else:
            f = p_major_left * p0_opp_right
        d["cm"] = d["cp"] * max(0.0, f)

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
