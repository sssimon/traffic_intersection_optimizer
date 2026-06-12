"""Simulación de colas en tiempo discreto (paso fijo) con réplicas.

No es una microsimulación espacial: cada grupo de carriles se modela como una
cola vertical, sin seguimiento vehicular ni cambio de carril.

Modelo:
- Llegadas: proceso de Poisson. El número de llegadas de cada paso se muestrea
  de una distribución Poisson de media λ·dt (λ = demanda / 3600 veh/s), que es
  la discretización exacta del proceso: reproduce la varianza real de las
  llegadas, incluidas las ráfagas de 2+ vehículos por paso que forman las
  colas largas.
- Cola: lista FIFO con tiempo de llegada de cada vehículo.
- Salidas: durante el verde del grupo, se libera al ritmo de saturación
  s/3600 (veh/s). Fuera del verde no hay salidas (amarillo + rojo).
- Estado del semáforo: se reproduce el plan ciclo a ciclo.

Réplicas (M6): una corrida estocástica es una muestra, no una estimación. Se
corren `replications` réplicas con semillas consecutivas (seed, seed+1, …) y
se reporta la banda de percentiles 5/50/95 de la cola punto a punto, además
de percentiles de las métricas agregadas. Con replications=1 el resultado es
la corrida única de esa semilla (los tres percentiles coinciden).

Limitación declarada: sin periodo de calentamiento — cada réplica parte con
colas vacías (inicio del periodo pico), lo que subestima la cola de los
primeros minutos.
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Tuple

import numpy as np

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


def _run_once(
    group_ids: List[str],
    rates: Dict[str, Tuple[float, float, str | None]],
    states: List[Tuple[str, str]],
    dt: float,
    seed: int,
) -> dict:
    """Una réplica: historial de cola, llegadas, servidos y esperas por grupo."""
    rng = np.random.default_rng(seed)
    n_steps = len(states)

    queues: Dict[str, deque[float]] = {g: deque() for g in group_ids}
    arrivals: Dict[str, int] = {g: 0 for g in group_ids}
    served: Dict[str, int] = {g: 0 for g in group_ids}
    wait_sum: Dict[str, float] = {g: 0.0 for g in group_ids}
    credit: Dict[str, float] = {g: 0.0 for g in group_ids}
    hist: Dict[str, np.ndarray] = {
        g: np.zeros(n_steps, dtype=np.float32) for g in group_ids
    }

    # Pre-muestreo: llegadas por paso ~ Poisson(λ·dt), en el orden de los
    # grupos (mismo orden de consumo del RNG que la corrida única original).
    draws = {g: rng.poisson(rates[g][0] * dt, n_steps) for g in group_ids}

    for step in range(n_steps):
        t = step * dt
        active_phase, state = states[step]

        for g in group_ids:
            arr_rate, sat_rate, phase_id = rates[g]
            n_arr = int(draws[g][step])
            for _ in range(n_arr):
                queues[g].append(t)
            arrivals[g] += n_arr

            # Salidas si la fase está en verde para este grupo; el crédito
            # acumulado se conserva fuera del verde.
            if phase_id == active_phase and state == "green":
                credit[g] += sat_rate * dt
                while credit[g] >= 1.0 and queues[g]:
                    arrival_time = queues[g].popleft()
                    wait_sum[g] += t - arrival_time
                    served[g] += 1
                    credit[g] -= 1.0

            hist[g][step] = len(queues[g])

    return {"hist": hist, "arrivals": arrivals, "served": served, "wait_sum": wait_sum}


def simulate(req: SimulationRequest) -> SimulationResult:
    cfg = req.config
    plan = req.signal_plan or optimize(cfg)
    schedule = _build_phase_schedule(cfg, plan)

    dt = req.time_step_s
    n_steps = int(req.duration_s / dt)
    time_axis = [i * dt for i in range(n_steps)]
    # El plan es fijo: el estado semafórico por paso se calcula una sola vez
    # y se comparte entre réplicas.
    states = [_phase_state_at(i * dt, schedule) for i in range(n_steps)]

    group_ids: List[str] = []
    rates: Dict[str, Tuple[float, float, str | None]] = {}
    for ap in cfg.approaches:
        for lg in ap.lane_groups:
            group_ids.append(lg.id)
            rates[lg.id] = (
                cfg.demand_for(lg.id) / 3600.0,   # veh/s
                lg.saturation_flow / 3600.0,       # veh/s
                _phase_id_for(cfg, lg.id),
            )

    reps = [
        _run_once(group_ids, rates, states, dt, req.seed + r)
        for r in range(req.replications)
    ]
    n_reps = len(reps)

    traces: List[MovementTrace] = []
    rep_arrived = np.zeros(n_reps)
    rep_served = np.zeros(n_reps)
    rep_wait_num = np.zeros(n_reps)
    rep_max_queue = np.zeros(n_reps)

    for g in group_ids:
        qstack = np.stack([rep["hist"][g] for rep in reps])  # (réplicas, pasos)
        if n_steps > 0:
            p05, p50, p95 = np.percentile(qstack, [5.0, 50.0, 95.0], axis=0)
            maxqs = qstack.max(axis=1)
        else:
            p05 = p50 = p95 = np.zeros(0)
            maxqs = np.zeros(n_reps)

        waits = np.array([
            rep["wait_sum"][g] / rep["served"][g] if rep["served"][g] > 0 else 0.0
            for rep in reps
        ])
        arr = np.array([rep["arrivals"][g] for rep in reps], dtype=float)
        srv = np.array([rep["served"][g] for rep in reps], dtype=float)

        traces.append(MovementTrace(
            lane_group_id=g,
            queue_p05=[round(float(x), 2) for x in p05],
            queue_p50=[round(float(x), 2) for x in p50],
            queue_p95=[round(float(x), 2) for x in p95],
            arrived_total=round(float(arr.mean()), 1),
            served_total=round(float(srv.mean()), 1),
            avg_wait_s=round(float(waits.mean()), 2),
            wait_p05=round(float(np.percentile(waits, 5.0)), 2),
            wait_p95=round(float(np.percentile(waits, 95.0)), 2),
            max_queue=round(float(maxqs.mean()), 1),
            max_queue_p95=round(float(np.percentile(maxqs, 95.0)), 1),
        ))

        rep_arrived += arr
        rep_served += srv
        rep_wait_num += np.array([rep["wait_sum"][g] for rep in reps])
        rep_max_queue = np.maximum(rep_max_queue, maxqs)

    rep_avg_wait = np.where(rep_served > 0, rep_wait_num / np.maximum(rep_served, 1.0), 0.0)

    return SimulationResult(
        duration_s=req.duration_s,
        replications=n_reps,
        time_axis_s=time_axis,
        movements=traces,
        avg_wait_all_s=round(float(rep_avg_wait.mean()), 2),
        avg_wait_all_p05=round(float(np.percentile(rep_avg_wait, 5.0)), 2),
        avg_wait_all_p95=round(float(np.percentile(rep_avg_wait, 95.0)), 2),
        max_queue_all=round(float(rep_max_queue.mean()), 1),
        max_queue_all_p95=round(float(np.percentile(rep_max_queue, 95.0)), 1),
        total_served=round(float(rep_served.mean()), 1),
        total_arrived=round(float(rep_arrived.mean()), 1),
    )
