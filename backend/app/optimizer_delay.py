"""Optimización de tiempos por minimización directa de la demora HCM (M4).

Webster (1958) es una fórmula cerrada calibrada para operación no saturada:
la literatura documenta que sobrestima el ciclo óptimo conforme crece el
grado de saturación — justo el régimen congestionado. Este módulo no usa
fórmula: busca el plan (ciclo + reparto de verdes efectivos) que minimiza la
demora media ponderada por demanda del propio modelo HCM (d = d1·PF + d2,
las mismas fórmulas de `analysis.py` vía `movement_performance`), de modo
que "óptimo" significa óptimo del modelo con el que después se evalúa.

Método (el motor evalúa un plan en microsegundos; la búsqueda directa es
viable y exacta al paso elegido):

1. Barrido del ciclo C en el rango factible dentro de [CYCLE_MIN, CYCLE_MAX]:
   paso grueso de 2 s y refinamiento de 0.5 s alrededor del mejor.
2. Para cada C, con verde efectivo total G = C − L:
   - inicio por equisaturación (proporcional a los flujos críticos yi, como
     Webster), acotado a [min_green, max_green] y reparado para que Σgi = G;
   - descenso coordinado: transferir ±paso de verde entre pares de fases
     mientras la demora ponderada mejore (pasos 2 → 0.5 → 0.1 s).
3. Restricciones: gi ∈ [min_green, max_green], Σgi = C − L. Si ningún ciclo
   del rango es factible, se devuelve el plan de verdes mínimos (o máximos)
   con una advertencia.

En sobre-saturación no colapsa al ciclo máximo como Webster: entrega el plan
de mínima demora del modelo, que típicamente usa ciclos más cortos.
"""
from __future__ import annotations

import math
from typing import List, Tuple

from .analysis import movement_performance
from .models import IntersectionConfig, SignalPlan
from .optimizer import CYCLE_MAX, CYCLE_MIN, _phase_critical_ratio

COARSE_STEP = 2.0
FINE_STEP = 0.5
FINE_WINDOW = 2.0
MAX_SWEEPS = 200


def _movement_inputs(cfg: IntersectionConfig) -> List[Tuple[int, float, float]]:
    """(índice de fase, demanda v, saturación s) por movimiento con demanda.

    Los movimientos sin fase asignada o sin demanda no aportan al objetivo
    ponderado (igual que en `analyze`, donde pesan 0).
    """
    index_of = {ph.id: i for i, ph in enumerate(cfg.phases)}
    out: List[Tuple[int, float, float]] = []
    for ap in cfg.approaches:
        for lg in ap.lane_groups:
            phase_idx = next(
                (index_of[ph.id] for ph in cfg.phases if lg.id in ph.lane_group_ids),
                None,
            )
            if phase_idx is None:
                continue
            v = cfg.demand_for(lg.id)
            if v <= 0:
                continue
            out.append((phase_idx, v, lg.saturation_flow))
    return out


def _weighted_delay(
    movs: List[Tuple[int, float, float]], C: float, greens: List[float]
) -> float:
    """Demora media ponderada por demanda (s/veh) — el objetivo a minimizar."""
    num = 0.0
    den = 0.0
    for phase_idx, v, s in movs:
        d, _, _ = movement_performance(v, s, greens[phase_idx], C)
        num += d * v
        den += v
    return num / den if den > 0 else 0.0


def _fit_to_total(
    greens: List[float], mins: List[float], maxs: List[float], total: float
) -> List[float]:
    """Reparte el residuo para que Σ greens = total sin violar las cotas."""
    g = list(greens)
    for _ in range(60):
        residual = total - sum(g)
        if abs(residual) < 1e-9:
            break
        if residual > 0:
            slack = [maxs[i] - g[i] for i in range(len(g))]
        else:
            slack = [g[i] - mins[i] for i in range(len(g))]
        slack_total = sum(x for x in slack if x > 1e-12)
        if slack_total <= 1e-12:
            break
        for i in range(len(g)):
            if slack[i] > 1e-12:
                g[i] += residual * (slack[i] / slack_total)
        g = [min(maxs[i], max(mins[i], g[i])) for i in range(len(g))]
    return g


def _coordinate_descent(
    movs: List[Tuple[int, float, float]],
    C: float,
    greens: List[float],
    mins: List[float],
    maxs: List[float],
    steps: Tuple[float, ...],
) -> Tuple[List[float], float]:
    """Transfiere verde entre pares de fases mientras la demora mejore.

    Mantiene Σg constante (cada movimiento es una transferencia i→j), así
    que la factibilidad Σg = C − L del punto inicial se conserva.
    """
    g = list(greens)
    best = _weighted_delay(movs, C, g)
    n = len(g)
    for step in steps:
        for _ in range(MAX_SWEEPS):
            improved = False
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    if g[i] - step < mins[i] - 1e-9 or g[j] + step > maxs[j] + 1e-9:
                        continue
                    g[i] -= step
                    g[j] += step
                    d = _weighted_delay(movs, C, g)
                    if d < best - 1e-9:
                        best = d
                        improved = True
                    else:
                        g[i] += step
                        g[j] -= step
            if not improved:
                break
    return g, best


def optimize_delay(cfg: IntersectionConfig) -> SignalPlan:
    notes: List[str] = []
    phases = cfg.phases
    n = len(phases)
    L = sum(ph.lost_time for ph in phases)
    mins = [ph.min_green for ph in phases]
    maxs = [ph.max_green for ph in phases]
    yellow = {ph.id: ph.yellow for ph in phases}
    all_red = {ph.id: ph.all_red for ph in phases}

    def _plan(C: float, greens: List[float], delay: float | None) -> SignalPlan:
        if delay is not None:
            notes.append(
                f"Demora media ponderada estimada del plan: {delay:.1f} s/veh."
            )
        return SignalPlan(
            cycle_length=round(C, 1),
            phase_green={ph.id: round(greens[i], 1) for i, ph in enumerate(phases)},
            phase_yellow=yellow,
            phase_all_red=all_red,
            total_lost_time=round(L, 1),
            notes=notes,
        )

    notes.append(
        "Plan por minimización directa de la demora HCM: búsqueda de ciclo y "
        "reparto de verdes sobre el propio modelo d = d1·PF + d2."
    )

    movs = _movement_inputs(cfg)
    y_per_phase = [_phase_critical_ratio(cfg, ph) for ph in phases]
    Y = sum(y_per_phase)

    if not movs or Y <= 0:
        notes.append("No hay demanda registrada; verde distribuido equitativamente.")
        G = max(sum(mins), CYCLE_MIN - L)
        greens = _fit_to_total([G / n] * n, mins, maxs, G)
        return _plan(G + L, greens, None)

    # Rango de ciclos factible: Σmin ≤ C − L ≤ Σmax dentro de [Cmin, Cmax].
    c_lo = max(CYCLE_MIN, L + sum(mins))
    c_hi = min(CYCLE_MAX, L + sum(maxs))
    if c_lo > c_hi:
        if L + sum(mins) > CYCLE_MAX:
            notes.append(
                "Los verdes mínimos más el tiempo perdido exceden el ciclo "
                "máximo: se devuelve el plan de verdes mínimos. Revise el "
                "número de fases."
            )
            greens = list(mins)
            return _plan(L + sum(mins), greens, _weighted_delay(movs, L + sum(mins), greens))
        notes.append(
            "Los verdes máximos no alcanzan el ciclo mínimo: se devuelve el "
            "plan de verdes máximos."
        )
        greens = list(maxs)
        return _plan(L + sum(maxs), greens, _weighted_delay(movs, L + sum(maxs), greens))

    def _evaluate_cycle(C: float, steps: Tuple[float, ...]) -> Tuple[List[float], float]:
        G = C - L
        init = [G * (y_per_phase[i] / Y) for i in range(n)]
        init = [min(maxs[i], max(mins[i], init[i])) for i in range(n)]
        init = _fit_to_total(init, mins, maxs, G)
        return _coordinate_descent(movs, C, init, mins, maxs, steps)

    # Pasada gruesa.
    best_C, best_g, best_d = None, None, float("inf")
    C = c_lo
    while C <= c_hi + 1e-9:
        g, d = _evaluate_cycle(min(C, c_hi), (2.0, 0.5))
        if d < best_d:
            best_C, best_g, best_d = min(C, c_hi), g, d
        C += COARSE_STEP
    if abs(best_C - c_hi) > 1e-9 and (c_hi - c_lo) % COARSE_STEP != 0:
        g, d = _evaluate_cycle(c_hi, (2.0, 0.5))
        if d < best_d:
            best_C, best_g, best_d = c_hi, g, d

    # Refinamiento alrededor del mejor ciclo.
    C = max(c_lo, best_C - FINE_WINDOW)
    while C <= min(c_hi, best_C + FINE_WINDOW) + 1e-9:
        g, d = _evaluate_cycle(C, (2.0, 0.5, 0.1))
        if d < best_d - 1e-9:
            best_C, best_g, best_d = C, g, d
        C += FINE_STEP

    # Transparencia: el mínimo de demora puede admitir X > 1 en el movimiento
    # crítico (el ciclo corto baja la demora de todos aunque un movimiento
    # exceda su capacidad durante el periodo analizado).
    max_x = 0.0
    for phase_idx, v, s in movs:
        _, _, x = movement_performance(v, s, best_g[phase_idx], best_C)
        if math.isfinite(x):
            max_x = max(max_x, x)
    if max_x > 1.0:
        notes.append(
            f"El plan admite sobresaturación del movimiento crítico "
            f"(X máx = {max_x:.2f}): el ciclo corto reduce la demora total "
            f"del periodo aunque ese movimiento acumule cola residual. "
            f"Compare con el plan Webster si el pico se prolonga."
        )

    return _plan(best_C, best_g, best_d)
