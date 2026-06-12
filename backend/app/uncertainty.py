"""Monte Carlo de incertidumbre del aforo (tarea 2.3) — pilar insignia.

Un aforo de 15 minutos no justifica un LOS de letra única. Este módulo
propaga la incertidumbre de los volúmenes por el motor analítico y entrega
probabilidades en lugar de falsas precisiones:

- Muestreo: v ~ Normal(media, CV·media) truncada en 0, independiente por
  movimiento. Supuesto declarado: la correlación día-a-día entre
  movimientos (un día cargado lo es en toda la intersección) no se modela
  aún, lo que tiende a subestimar la varianza del total.
- El plan semafórico se diseña UNA vez con el aforo medio (Webster o
  mínima demora) y se evalúa fijo bajo demanda incierta — replica la
  práctica real: el plan se programa con el conteo disponible y la
  demanda luego varía.
- Salida: distribución de la demora media (p5/p50/p95), P(LOS A..F),
  probabilidad de sobresaturación del movimiento crítico y tornado de
  sensibilidad (correlación de Pearson volumen → demora por movimiento).

Las 1 000 muestras corren en decenas de milisegundos: cada evaluación usa
el núcleo `movement_performance` sin construir objetos intermedios — la
ventaja estructural del motor analítico que un microsimulador no tiene.
"""
from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np

from .analysis import movement_performance
from .models import (
    IntersectionConfig,
    MovementSensitivity,
    UncertaintyRequest,
    UncertaintyResult,
)
from .optimizer import optimize
from .optimizer_delay import optimize_delay

LOS_BINS = np.array([10.0, 20.0, 35.0, 55.0, 80.0])
LOS_LETTERS = "ABCDEF"


def _sampleable_movements(
    cfg: IntersectionConfig, phase_green: dict[str, float]
) -> List[Tuple[str, float, float, float, float]]:
    """(lg_id, volumen crudo medio, pcu, saturación, verde) por movimiento
    con fase asignada y demanda positiva."""
    out: List[Tuple[str, float, float, float, float]] = []
    for ap in cfg.approaches:
        for lg in ap.lane_groups:
            phase_id = next(
                (ph.id for ph in cfg.phases if lg.id in ph.lane_group_ids), None
            )
            if phase_id is None:
                continue
            entry = next(
                (d for d in cfg.demand if d.lane_group_id == lg.id), None
            )
            if entry is None or entry.volume <= 0:
                continue
            out.append((
                lg.id,
                entry.volume,
                entry.pcu_factor,
                lg.saturation_flow,
                phase_green.get(phase_id, 0.0),
            ))
    return out


def run_uncertainty(req: UncertaintyRequest) -> UncertaintyResult:
    cfg = req.config
    optimizer = optimize_delay if req.method == "delay_min" else optimize
    plan = optimizer(cfg)
    C = plan.cycle_length

    notes = [
        "Volúmenes ~ Normal(media, CV·media) truncada en 0, independientes "
        "por movimiento (la correlación día-a-día no se modela: la varianza "
        "del total tiende a subestimarse).",
        "El plan se diseñó una vez con el aforo medio y se evalúa fijo bajo "
        "demanda incierta (práctica real de programación de semáforos).",
    ]

    movs = _sampleable_movements(cfg, plan.phase_green)
    if not movs:
        return UncertaintyResult(
            samples=0,
            volume_cv=req.volume_cv,
            method=req.method,
            signal_plan=plan,
            base_delay_s=0.0,
            delay_mean_s=0.0,
            delay_p05_s=0.0,
            delay_p50_s=0.0,
            delay_p95_s=0.0,
            los_probability={letter: 0.0 for letter in LOS_LETTERS},
            prob_oversaturated=0.0,
            sensitivity=[],
            notes=notes + ["Sin movimientos con demanda y fase: nada que muestrear."],
        )

    n = req.samples
    m = len(movs)
    means = np.array([mv[1] for mv in movs])
    pcus = np.array([mv[2] for mv in movs])
    cvs = np.array([req.movement_cv.get(mv[0], req.volume_cv) for mv in movs])

    rng = np.random.default_rng(req.seed)
    raw = rng.normal(means, means * cvs, size=(n, m))
    np.maximum(raw, 0.0, out=raw)
    adjusted = raw * pcus / cfg.peak_hour_factor

    def _weighted_delay_and_xmax(volumes: np.ndarray) -> Tuple[float, float]:
        num = 0.0
        den = 0.0
        x_max = 0.0
        for j, (_, _, _, s, g) in enumerate(movs):
            v = float(volumes[j])
            d, _, x = movement_performance(v, s, g, C)
            num += d * v
            den += v
            if math.isfinite(x):
                x_max = max(x_max, x)
        return (num / den if den > 0 else 0.0), x_max

    delays = np.empty(n)
    xmax = np.empty(n)
    for i in range(n):
        delays[i], xmax[i] = _weighted_delay_and_xmax(adjusted[i])

    base_delay, _ = _weighted_delay_and_xmax(means * pcus / cfg.peak_hour_factor)

    p05, p50, p95 = np.percentile(delays, [5.0, 50.0, 95.0])

    los_idx = np.searchsorted(LOS_BINS, delays, side="left")
    los_probability = {
        letter: round(float(np.mean(los_idx == k)), 4)
        for k, letter in enumerate(LOS_LETTERS)
    }

    sensitivity: List[MovementSensitivity] = []
    delay_std = float(delays.std())
    for j, mv in enumerate(movs):
        col = raw[:, j]
        if col.std() <= 1e-12 or delay_std <= 1e-12:
            r = 0.0
        else:
            r = float(np.corrcoef(col, delays)[0, 1])
        sensitivity.append(MovementSensitivity(
            lane_group_id=mv[0],
            correlation=round(r, 3),
            cv=round(float(cvs[j]), 3),
        ))
    sensitivity.sort(key=lambda s: abs(s.correlation), reverse=True)

    return UncertaintyResult(
        samples=n,
        volume_cv=req.volume_cv,
        method=req.method,
        signal_plan=plan,
        base_delay_s=round(base_delay, 1),
        delay_mean_s=round(float(delays.mean()), 1),
        delay_p05_s=round(float(p05), 1),
        delay_p50_s=round(float(p50), 1),
        delay_p95_s=round(float(p95), 1),
        los_probability=los_probability,
        prob_oversaturated=round(float(np.mean(xmax > 1.0)), 4),
        sensitivity=sensitivity,
        notes=notes,
    )
