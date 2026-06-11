"""Simulación de colas en tiempo discreto (paso fijo).

No es una microsimulación espacial: cada grupo de carriles se modela como una
cola vertical, sin seguimiento vehicular ni cambio de carril.

Modelo:
- Llegadas: aleatorias. En cada paso se añade una llegada con probabilidad
  λ·dt  (λ = demanda / 3600 veh/s). Es una aproximación de Bernoulli, no un
  proceso de Poisson exacto (no genera más de una llegada por paso). Ver M2b.
- Cola: lista FIFO con tiempo de llegada de cada vehículo.
- Salidas: durante el verde del grupo, se libera al ritmo de saturación
  s/3600 (veh/s). Fuera del verde no hay salidas (amarillo + rojo).
- Estado del semáforo: se reproduce el plan ciclo a ciclo.

Métricas:
- Cola promedio y máxima por grupo a lo largo del tiempo.
- Tiempo de espera promedio por vehículo servido.
- Llegadas vs servidos (vehículos que quedan en cola al final).
"""
from __future__ import annotations

import random
from collections import deque
from typing import Dict, List

from .models import (
    IntersectionConfig,
    MovementTrace,
    SignalPlan,
    SimulationRequest,
    SimulationResult,
)
from .optimizer import optimize


def _phase_id_for(cfg: IntersectionConfig, lg_id: str) -> str | None:
    for ph in cfg.phases:
        if lg_id in ph.lane_group_ids:
            return ph.id
    return None


def _build_phase_schedule(cfg: IntersectionConfig, plan: SignalPlan) -> List[tuple[str, str, float]]:
    """Devuelve secuencia [(phase_id, state, dur_s)] para un ciclo.

    state ∈ {'green', 'yellow', 'all_red'}

    `plan.phase_green` es verde efectivo; bajo el supuesto del modelo
    (arranque perdido ≈ extensión del verde) se reproduce directamente como
    el intervalo de verde visualizado, sin conversión adicional.
    """
    sched: List[tuple[str, str, float]] = []
    for ph in cfg.phases:
        g = plan.phase_green.get(ph.id, 0.0)
        y = plan.phase_yellow.get(ph.id, ph.yellow)
        ar = plan.phase_all_red.get(ph.id, ph.all_red)
        if g > 0:
            sched.append((ph.id, "green", g))
        if y > 0:
            sched.append((ph.id, "yellow", y))
        if ar > 0:
            sched.append((ph.id, "all_red", ar))
    return sched


def _phase_state_at(t: float, schedule: List[tuple[str, str, float]]) -> tuple[str, str]:
    cycle = sum(d for _, _, d in schedule)
    if cycle <= 0:
        return ("", "all_red")
    tau = t % cycle
    acc = 0.0
    for phase_id, state, dur in schedule:
        if tau < acc + dur:
            return (phase_id, state)
        acc += dur
    return schedule[-1][0], schedule[-1][1]


def simulate(req: SimulationRequest) -> SimulationResult:
    rng = random.Random(req.seed)
    cfg = req.config
    plan = req.signal_plan or optimize(cfg)
    schedule = _build_phase_schedule(cfg, plan)

    dt = req.time_step_s
    n_steps = int(req.duration_s / dt)

    # Estado por grupo
    queues: Dict[str, deque[float]] = {}
    arrivals: Dict[str, int] = {}
    served: Dict[str, int] = {}
    wait_sum: Dict[str, float] = {}
    queue_history: Dict[str, List[float]] = {}
    departure_credit: Dict[str, float] = {}
    rates: Dict[str, tuple[float, float, str | None]] = {}  # (arr_rate, sat_rate, phase)

    for ap in cfg.approaches:
        for lg in ap.lane_groups:
            queues[lg.id] = deque()
            arrivals[lg.id] = 0
            served[lg.id] = 0
            wait_sum[lg.id] = 0.0
            queue_history[lg.id] = []
            departure_credit[lg.id] = 0.0
            arr_rate = cfg.demand_for(lg.id) / 3600.0  # veh/s
            sat_rate = lg.saturation_flow / 3600.0      # veh/s
            rates[lg.id] = (arr_rate, sat_rate, _phase_id_for(cfg, lg.id))

    time_axis: List[float] = []

    for step in range(n_steps):
        t = step * dt
        time_axis.append(t)
        active_phase, state = _phase_state_at(t, schedule)

        for lg_id, (arr_rate, sat_rate, phase_id) in rates.items():
            # Llegadas aleatorias en el intervalo dt
            mean = arr_rate * dt
            # Aproximación de Bernoulli: parte entera + bernoulli de la fracción.
            # NO es Poisson exacto (no produce más de una llegada por paso). Ver M2b.
            n_arr = int(mean)
            frac = mean - n_arr
            if rng.random() < frac:
                n_arr += 1
            for _ in range(n_arr):
                queues[lg_id].append(t)
                arrivals[lg_id] += 1

            # Salidas si la fase está en verde para este grupo
            if phase_id == active_phase and state == "green":
                departure_credit[lg_id] += sat_rate * dt
                while departure_credit[lg_id] >= 1.0 and queues[lg_id]:
                    arrival_time = queues[lg_id].popleft()
                    wait_sum[lg_id] += t - arrival_time
                    served[lg_id] += 1
                    departure_credit[lg_id] -= 1.0
            else:
                # se mantiene el crédito acumulado del verde anterior
                pass

            queue_history[lg_id].append(len(queues[lg_id]))

    traces: List[MovementTrace] = []
    total_served = 0
    total_arrived = 0
    max_q_all = 0.0
    wait_num = 0.0
    wait_den = 0

    for lg_id in queues:
        q_hist = queue_history[lg_id]
        max_q = max(q_hist) if q_hist else 0.0
        avg_wait = wait_sum[lg_id] / served[lg_id] if served[lg_id] > 0 else 0.0
        traces.append(
            MovementTrace(
                lane_group_id=lg_id,
                queue_over_time=q_hist,
                served_total=served[lg_id],
                arrived_total=arrivals[lg_id],
                avg_wait_s=round(avg_wait, 2),
                max_queue=max_q,
            )
        )
        total_served += served[lg_id]
        total_arrived += arrivals[lg_id]
        max_q_all = max(max_q_all, max_q)
        wait_num += wait_sum[lg_id]
        wait_den += served[lg_id]

    avg_wait_all = wait_num / wait_den if wait_den > 0 else 0.0

    return SimulationResult(
        duration_s=req.duration_s,
        time_axis_s=time_axis,
        movements=traces,
        avg_wait_all_s=round(avg_wait_all, 2),
        max_queue_all=max_q_all,
        total_served=total_served,
        total_arrived=total_arrived,
    )
