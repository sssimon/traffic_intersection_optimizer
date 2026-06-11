"""Pruebas de regresión — simulación de colas (app/simulator.py).

La simulación es determinista con la semilla por defecto (42), así que
estas pruebas verifican invariantes estructurales y de comportamiento.
"""
from app.models import SimulationRequest
from app.simulator import simulate


def test_served_never_exceeds_arrived(webster_config):
    result = simulate(SimulationRequest(config=webster_config, duration_s=600))
    assert result.total_arrived > 0
    assert result.total_served <= result.total_arrived


def test_queue_history_non_negative(webster_config):
    result = simulate(SimulationRequest(config=webster_config, duration_s=300))
    for trace in result.movements:
        assert all(q >= 0 for q in trace.queue_over_time)


def test_time_axis_length(webster_config):
    # duration 600 s con paso de 1 s -> 600 muestras
    result = simulate(SimulationRequest(config=webster_config, duration_s=600,
                                        time_step_s=1.0))
    assert len(result.time_axis_s) == 600


def test_high_capacity_clears_queue(make_two_phase):
    # Saturación muy alta (2200) frente a demanda baja (120): la cola se
    # disipa cada ciclo y casi todos los vehículos quedan servidos.
    cfg = make_two_phase(120.0, saturation=2200.0)
    result = simulate(SimulationRequest(config=cfg, duration_s=600))
    assert result.max_queue_all <= 10
    assert result.total_served >= result.total_arrived * 0.9


def test_poisson_arrival_dispersion(single_movement_config):
    # M2b: el total de llegadas en T segundos debe distribuirse Poisson(λ·T),
    # cuyo índice de dispersión (varianza/media) es 1. La antigua aproximación
    # de Bernoulli era sub-dispersa (índice << 1). Con 400 semillas fijas el
    # estimador tiene desviación ≈ 0.07: los límites [0.75, 1.30] están a más
    # de 3.5 desviaciones y la prueba es determinista.
    totals = []
    for seed in range(400):
        r = simulate(SimulationRequest(config=single_movement_config,
                                       duration_s=300, seed=seed))
        totals.append(r.total_arrived)
    mean = sum(totals) / len(totals)
    var = sum((x - mean) ** 2 for x in totals) / (len(totals) - 1)
    assert mean > 0
    assert 0.75 <= var / mean <= 1.30


def test_poisson_allows_bursts_per_step(make_two_phase):
    # Con λ·dt = 0.5 un Poisson real produce pasos con 2+ llegadas
    # (P ≈ 9 % por paso); la aproximación de Bernoulli nunca podía.
    # Un salto de cola ≥ 2 entre muestras consecutivas implica 2+ llegadas
    # en ese paso (las salidas solo pueden reducir la diferencia).
    cfg = make_two_phase(1800.0)
    r = simulate(SimulationRequest(config=cfg, duration_s=600, seed=7))
    max_jump = 0
    for tr in r.movements:
        q = tr.queue_over_time
        for i in range(1, len(q)):
            max_jump = max(max_jump, q[i] - q[i - 1])
    assert max_jump >= 2
