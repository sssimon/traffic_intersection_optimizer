"""Pruebas de regresión — simulación de colas con réplicas (app/simulator.py).

Con `replications=1` la simulación es la corrida única de la semilla dada
(los percentiles coinciden con la traza); con N réplicas se verifica la
coherencia de las bandas (p05 ≤ p50 ≤ p95) y de los agregados.
"""
from app.models import SimulationRequest
from app.simulator import simulate


def test_served_never_exceeds_arrived(webster_config):
    result = simulate(SimulationRequest(config=webster_config, duration_s=600,
                                        replications=5))
    assert result.total_arrived > 0
    assert result.total_served <= result.total_arrived


def test_queue_bands_ordered_and_non_negative(webster_config):
    result = simulate(SimulationRequest(config=webster_config, duration_s=300,
                                        replications=10))
    for trace in result.movements:
        assert len(trace.queue_p05) == len(trace.queue_p50) == len(trace.queue_p95)
        for lo, mid, hi in zip(trace.queue_p05, trace.queue_p50, trace.queue_p95):
            assert 0 <= lo <= mid <= hi


def test_band_collapses_with_one_replication(webster_config):
    # Una sola réplica: los tres percentiles son la misma traza.
    result = simulate(SimulationRequest(config=webster_config, duration_s=300,
                                        replications=1))
    for trace in result.movements:
        assert trace.queue_p05 == trace.queue_p50 == trace.queue_p95
    assert result.avg_wait_all_p05 == result.avg_wait_all_s == result.avg_wait_all_p95


def test_band_is_visible_with_replications(make_two_phase):
    # Cerca de saturación la variabilidad entre réplicas es grande: la banda
    # p05–p95 debe abrirse en algún punto (criterio 1.6: banda visible).
    cfg = make_two_phase(900.0)
    result = simulate(SimulationRequest(config=cfg, duration_s=600,
                                        replications=20))
    widest = max(
        (hi - lo)
        for tr in result.movements
        for lo, hi in zip(tr.queue_p05, tr.queue_p95)
    )
    assert widest >= 2.0
    assert result.replications == 20


def test_time_axis_length(webster_config):
    # duration 600 s con paso de 1 s -> 600 muestras
    result = simulate(SimulationRequest(config=webster_config, duration_s=600,
                                        time_step_s=1.0, replications=2))
    assert len(result.time_axis_s) == 600


def test_high_capacity_clears_queue(make_two_phase):
    # Saturación muy alta (2200) frente a demanda baja (120): la cola se
    # disipa cada ciclo y casi todos los vehículos quedan servidos.
    cfg = make_two_phase(120.0, saturation=2200.0)
    result = simulate(SimulationRequest(config=cfg, duration_s=600,
                                        replications=5))
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
                                       duration_s=300, seed=seed,
                                       replications=1))
        totals.append(r.total_arrived)
    mean = sum(totals) / len(totals)
    var = sum((x - mean) ** 2 for x in totals) / (len(totals) - 1)
    assert mean > 0
    assert 0.75 <= var / mean <= 1.30


def test_poisson_allows_bursts_per_step(make_two_phase):
    # Con λ·dt = 0.5 un Poisson real produce pasos con 2+ llegadas
    # (P ≈ 9 % por paso); la aproximación de Bernoulli nunca podía.
    # Un salto de cola ≥ 2 entre muestras consecutivas implica 2+ llegadas
    # en ese paso (las salidas solo pueden reducir la diferencia). Con una
    # réplica, queue_p50 es la traza de esa corrida.
    cfg = make_two_phase(1800.0)
    r = simulate(SimulationRequest(config=cfg, duration_s=600, seed=7,
                                   replications=1))
    max_jump = 0.0
    for tr in r.movements:
        q = tr.queue_p50
        for i in range(1, len(q)):
            max_jump = max(max_jump, q[i] - q[i - 1])
    assert max_jump >= 2
