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
