"""Coordinación de corredor — offsets, onda verde y PF real (tarea 4.1, M5).

Cierra la brecha más visible frente a Synchro: hasta ahora cada intersección
se trataba como aislada (PF = 1 fijo, hallazgo F7 de la auditoría). Este
módulo coordina una arteria:

1. Todas las intersecciones comparten el ciclo del corredor; la fase
   arterial (verde g_i, offset o_i) sirve ambos sentidos.
2. **Banda verde**: la ventana de paso sin parar es la intersección cíclica
   de los verdes desplazados por los tiempos de viaje. La banda de cada
   sentido se calcula exacta (el inicio óptimo coincide con el borde de
   algún verde); los offsets se optimizan por descenso coordinado con paso
   de 1 s maximizando w_ida·B_ida + w_vuelta·B_vuelta, con pesos por
   volumen (MAXBAND simplificado).
3. **PF real (HCM 2000 cap. 16, ec. 16-4)**: PF = (1 − P)·fPA / (1 − g/C),
   con fPA = 1.0 (supuesto declarado). P es la fracción del pelotón aguas
   arriba que llega en verde, con pelotón uniforme durante el verde y sin
   dispersión (el modelo de Robertson queda para una versión futura). La
   primera intersección de cada sentido recibe llegadas aleatorias (PF = 1;
   con P = g/C la fórmula devuelve exactamente 1).
4. La demora arterial usa el mismo núcleo HCM del resto del motor
   (`movement_performance_full` con el PF calculado) y se compara contra el
   caso aislado (PF = 1): la mejora por coordinación queda cuantificada.
"""
from __future__ import annotations

from typing import List, Tuple

from .analysis import movement_performance_full
from .models import (
    CorridorIntersectionResult,
    CorridorRequest,
    CorridorResult,
)

F_PA = 1.0          # factor de ajuste por llegadas (supuesto declarado)
OFFSET_STEP_S = 1.0
MAX_SWEEPS = 25


def _cyclic_overlap(a0: float, a_len: float, b0: float, b_len: float, C: float) -> float:
    """Solapamiento de [a0, a0+a_len) y [b0, b0+b_len) en módulo C."""
    if a_len <= 0 or b_len <= 0:
        return 0.0
    if a_len >= C:
        return b_len
    if b_len >= C:
        return a_len
    a0 %= C
    b0 %= C
    total = 0.0
    for shift in (-C, 0.0, C):
        start = max(a0, b0 + shift)
        end = min(a0 + a_len, b0 + shift + b_len)
        total += max(0.0, end - start)
    return min(total, a_len, b_len)


def _bandwidth(starts: List[float], greens: List[float], C: float) -> Tuple[float, float]:
    """(banda, inicio) de la intersección cíclica de las ventanas verdes.

    El inicio óptimo de la banda coincide con el inicio de alguna ventana:
    se evalúan esos candidatos y se toma el mejor.
    """
    best = 0.0
    best_start = 0.0
    for i in range(len(starts)):
        cand = starts[i] % C
        width = float("inf")
        for j in range(len(starts)):
            off = (cand - starts[j]) % C
            rem = greens[j] - off if off < greens[j] else 0.0
            width = min(width, rem)
            if width <= 0.0:
                break
        if width > best:
            best = width
            best_start = cand
    return best, best_start


def _progression_factor(p: float, g_over_c: float) -> float:
    """PF = (1 − P)·fPA / (1 − g/C); con P = g/C (aleatorio) da 1.0."""
    denom = max(1e-6, 1.0 - g_over_c)
    return max(0.0, (1.0 - p) * F_PA / denom)


def process_corridor(req: CorridorRequest) -> CorridorResult:
    C = req.cycle_s
    n = len(req.intersections)
    warnings: List[str] = []
    notes = [
        "Pelotón uniforme durante el verde aguas arriba, sin dispersión "
        "(Robertson pendiente); fPA = 1.0.",
        "La fase arterial sirve ambos sentidos con el mismo verde y offset.",
        "PF (HCM 2000 cap. 16, ec. 16-4) aplicado a d1 del propio modelo "
        "de demora del motor; PF = 1 en la primera intersección de cada "
        "sentido (llegadas aleatorias).",
    ]

    for it in req.intersections:
        if it.green_s >= C:
            raise ValueError(
                f"'{it.name}': el verde arterial ({it.green_s:.0f} s) debe "
                f"ser menor que el ciclo ({C:.0f} s)."
            )
        if it.green_s >= C - 10:
            warnings.append(
                f"'{it.name}': la transversal queda con menos de 10 s de "
                "verde — revisa el reparto."
            )
    if req.offsets_s and len(req.offsets_s) != n:
        raise ValueError(
            f"Se recibieron {len(req.offsets_s)} offsets para {n} "
            "intersecciones."
        )

    # Posiciones y tiempos de viaje acumulados desde la primera intersección.
    positions = [0.0]
    travel = [0.0]
    for it in req.intersections[:-1]:
        positions.append(positions[-1] + it.distance_to_next_m)
        travel.append(travel[-1] + it.distance_to_next_m / (it.speed_to_next_kmh / 3.6))

    greens = [it.green_s for it in req.intersections]
    w_out_total = sum(it.vol_out for it in req.intersections)
    w_in_total = sum(it.vol_in for it in req.intersections)
    if w_out_total + w_in_total <= 0:
        w_out, w_in = 0.5, 0.5
    else:
        w_out = w_out_total / (w_out_total + w_in_total)
        w_in = 1.0 - w_out

    def _bands(offsets: List[float]) -> Tuple[float, float, float, float]:
        starts_out = [offsets[i] - travel[i] for i in range(n)]
        b_out, s_out = _bandwidth(starts_out, greens, C)
        starts_in = [offsets[i] - (travel[-1] - travel[i]) for i in range(n)]
        b_in, s_in = _bandwidth(starts_in, greens, C)
        return b_out, s_out, b_in, s_in

    def _objective(offsets: List[float]) -> float:
        b_out, _, b_in, _ = _bands(offsets)
        return w_out * b_out + w_in * b_in

    if req.offsets_s and not req.optimize_offsets:
        offsets = [o % C for o in req.offsets_s]
        optimized = False
    else:
        # Arranque ideal de ida (offsets = tiempos de viaje) y descenso
        # coordinado: probar cada offset en pasos de 1 s manteniendo el resto.
        offsets = [travel[i] % C for i in range(n)]
        best_obj = _objective(offsets)
        for _ in range(MAX_SWEEPS):
            improved = False
            for i in range(1, n):
                original = offsets[i]
                best_o = original
                steps = int(C / OFFSET_STEP_S)
                for k in range(steps):
                    offsets[i] = k * OFFSET_STEP_S
                    obj = _objective(offsets)
                    if obj > best_obj + 1e-9:
                        best_obj = obj
                        best_o = offsets[i]
                offsets[i] = best_o
                if best_o != original:
                    improved = True
            if not improved:
                break
        optimized = True

    # Los inicios de banda ya vienen en el reloj de su punto de entrada:
    # ida = primera intersección; vuelta = última (así se construyeron las
    # ventanas desplazadas).
    band_out, band_out_start, band_in, band_in_start = _bands(offsets)

    results: List[CorridorIntersectionResult] = []
    num_coord = den = num_iso = 0.0

    for i, it in enumerate(req.intersections):
        g_over_c = it.green_s / C

        # P de ida: pelotón del verde de la intersección anterior, desplazado
        # por el tiempo de viaje del tramo, contra el verde local.
        if i == 0:
            p_out = None
            pf_out = 1.0
        else:
            tau = travel[i] - travel[i - 1]
            g_up = greens[i - 1]
            overlap = _cyclic_overlap(
                offsets[i - 1] + tau, g_up, offsets[i], it.green_s, C
            )
            p_out = overlap / g_up if g_up > 0 else 0.0
            pf_out = _progression_factor(p_out, g_over_c)

        if i == n - 1:
            p_in = None
            pf_in = 1.0
        else:
            tau = travel[i + 1] - travel[i]
            g_up = greens[i + 1]
            overlap = _cyclic_overlap(
                offsets[i + 1] + tau, g_up, offsets[i], it.green_s, C
            )
            p_in = overlap / g_up if g_up > 0 else 0.0
            pf_in = _progression_factor(p_in, g_over_c)

        d_out = movement_performance_full(it.vol_out, it.sat_out, it.green_s, C, pf=pf_out).delay
        d_in = movement_performance_full(it.vol_in, it.sat_in, it.green_s, C, pf=pf_in).delay
        d_out_iso = movement_performance_full(it.vol_out, it.sat_out, it.green_s, C).delay
        d_in_iso = movement_performance_full(it.vol_in, it.sat_in, it.green_s, C).delay

        results.append(CorridorIntersectionResult(
            name=it.name,
            position_m=round(positions[i], 1),
            offset_s=round(offsets[i] % C, 1),
            green_s=it.green_s,
            p_green_out=round(p_out, 3) if p_out is not None else None,
            p_green_in=round(p_in, 3) if p_in is not None else None,
            pf_out=round(pf_out, 3),
            pf_in=round(pf_in, 3),
            delay_out_s=round(d_out, 1),
            delay_in_s=round(d_in, 1),
            delay_isolated_out_s=round(d_out_iso, 1),
            delay_isolated_in_s=round(d_in_iso, 1),
        ))

        num_coord += d_out * it.vol_out + d_in * it.vol_in
        num_iso += d_out_iso * it.vol_out + d_in_iso * it.vol_in
        den += it.vol_out + it.vol_in

    return CorridorResult(
        cycle_s=C,
        offsets_optimized=optimized,
        band_out_s=round(band_out, 1),
        band_in_s=round(band_in, 1),
        efficiency_out=round(band_out / C, 3),
        efficiency_in=round(band_in / C, 3),
        band_out_start_s=round(band_out_start, 1),
        band_in_start_s=round(band_in_start, 1),
        travel_times_s=[round(t, 1) for t in travel],
        intersections=results,
        avg_artery_delay_s=round(num_coord / den, 1) if den > 0 else 0.0,
        avg_artery_delay_isolated_s=round(num_iso / den, 1) if den > 0 else 0.0,
        warnings=warnings,
        notes=notes,
    )
