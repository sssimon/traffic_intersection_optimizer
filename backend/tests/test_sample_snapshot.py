"""Prueba de regresión 'snapshot' del caso de ejemplo (app/data.py).

Congela las métricas del caso de ejemplo con su configuración por defecto.
Si un cambio en cualquier módulo de cálculo altera estos resultados, estas
pruebas lo detectan de inmediato.

IMPORTANTE: actualizar estos valores SOLO con una justificación documentada
(p. ej. al implementar M2b — muestreo Poisson real — o M3 — HCM 7).
"""
import pytest

from app.analysis import analyze
from app.data import sample_intersection
from app.models import LOSGrade, SimulationRequest
from app.optimizer import optimize
from app.simulator import simulate


def test_sample_optimization_snapshot():
    plan = optimize(sample_intersection())
    assert plan.cycle_length == 120.0
    assert plan.total_lost_time == 16.0
    assert plan.phase_green == pytest.approx(
        {"P1": 30.3, "P2": 13.3, "P3": 42.6, "P4": 17.8}
    )


def test_sample_analysis_snapshot():
    sample = sample_intersection()
    analysis = analyze(sample, optimize(sample))
    assert analysis.avg_delay_s == 56.0
    assert analysis.overall_los == LOSGrade.E
    assert analysis.overall_v_c == 0.929


def test_sample_simulation_snapshot():
    # Determinista con la semilla por defecto (42) y UNA réplica: ancla la
    # corrida única para detectar cambios en el muestreo o en la descarga.
    # Actualizado al implementar M2b (muestreo Poisson real con numpy):
    # el valor 1320 correspondía a la aproximación de Bernoulli. La media
    # teórica es Σv/PHF × 900/3600 ≈ 1337; 1328 está dentro de ±1σ (≈37).
    result = simulate(SimulationRequest(config=sample_intersection(),
                                        replications=1))
    assert result.total_arrived == 1328
    assert result.total_served <= result.total_arrived


def test_sample_simulation_replicated_mean_near_theory():
    # Con 20 réplicas, la media de llegadas debe acercarse a la teórica
    # (Σv/PHF × T = 1337 veh en 900 s; error estándar de la media ≈ 8).
    result = simulate(SimulationRequest(config=sample_intersection(),
                                        replications=20))
    assert abs(result.total_arrived - 1337.0) <= 30.0
    assert result.replications == 20
