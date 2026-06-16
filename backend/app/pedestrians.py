"""Análisis peatonal en intersección semaforizada (M10, tarea 5.3).

Cierra la última brecha del plan: hasta ahora solo se reportaba el LOS
vehicular. Por cada cruce peatonal definido se calcula, sobre el plan de
tiempos ya optimizado:

- **Despeje peatonal** (flashing don't walk): FDW = L / Sp, con L la longitud
  del cruce y Sp la velocidad de cruce (HCM: 1.2 m/s).
- **Mínimo seguro** (MUTCD): Walk + FDW. Si el verde de la fase no lo cubre,
  se avisa: la fase es demasiado corta para que un peatón cruce con seguridad.
- **Demora peatonal** (HCM, llegadas aleatorias): dp = 0.5·C·(1 − gp/C)², con
  gp el verde disponible para cruzar (el verde de la fase asociada).
- **LOS peatonal** por demora (umbrales del HCM para cruces semaforizados).

Supuestos declarados: gp = verde efectivo de la fase (Walk + parte del FDW se
aproxima por el verde vehicular concurrente); no se modela el efecto del
volumen peatonal sobre el tiempo de despeje (plataforma 4.0 m) ni el LOS
peatonal perceptual (puntaje multifactor del HCM 2010), solo el basado en
demora — el más usado y verificable.
"""
from __future__ import annotations

from typing import List, Tuple

from .models import (
    Crossing,
    IntersectionConfig,
    LOSGrade,
    PedestrianAnalysis,
    SignalPlan,
)

# Umbrales de LOS peatonal por demora (s) — HCM, cruce semaforizado.
_PED_LOS = [(10.0, LOSGrade.A), (20.0, LOSGrade.B), (30.0, LOSGrade.C),
            (40.0, LOSGrade.D), (60.0, LOSGrade.E)]


def _ped_los(delay: float) -> LOSGrade:
    for limit, grade in _PED_LOS:
        if delay <= limit:
            return grade
    return LOSGrade.F


def _crossing_result(cx: Crossing, g: float, C: float) -> PedestrianAnalysis:
    clearance = cx.length_m / cx.walk_speed_ms
    min_required = cx.walk_interval_s + clearance
    gp = max(0.0, min(g, C))
    delay = 0.5 * C * (1.0 - gp / C) ** 2 if C > 0 else 0.0
    return PedestrianAnalysis(
        crossing_id=cx.id,
        name=cx.name,
        phase_id=cx.phase_id,
        length_m=cx.length_m,
        effective_walk_s=round(gp, 1),
        clearance_s=round(clearance, 1),
        min_required_s=round(min_required, 1),
        avg_delay_s=round(delay, 1),
        los=_ped_los(delay),
        sufficient_green=gp >= min_required,
    )


def analyze_pedestrians(
    cfg: IntersectionConfig, plan: SignalPlan
) -> Tuple[List[PedestrianAnalysis], List[str]]:
    """(resultados por cruce, avisos). Vacío si no hay cruces definidos."""
    results: List[PedestrianAnalysis] = []
    warnings: List[str] = []
    C = plan.cycle_length
    for cx in cfg.crossings:
        if cx.phase_id not in plan.phase_green:
            warnings.append(
                f"Cruce '{cx.id}': la fase '{cx.phase_id}' no existe en el "
                "plan; se omite del análisis peatonal."
            )
            continue
        res = _crossing_result(cx, plan.phase_green[cx.phase_id], C)
        results.append(res)
        if not res.sufficient_green:
            warnings.append(
                f"Cruce '{cx.id}': el verde de la fase '{cx.phase_id}' "
                f"({res.effective_walk_s:.0f} s) es menor que el mínimo seguro "
                f"MUTCD ({res.min_required_s:.0f} s = Walk {cx.walk_interval_s:.0f} + "
                f"despeje {res.clearance_s:.0f}). Amplía el verde o usa fase "
                "peatonal exclusiva."
            )
    return results, warnings
