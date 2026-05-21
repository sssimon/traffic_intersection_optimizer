"""Pruebas de regresión — comparación de escenarios (app/scenarios.py)."""
from app.models import DemandMultiplier, ScenarioRequest
from app.scenarios import _scale_demand, compare


def test_scale_demand_doubles_volume(webster_config):
    scaled = _scale_demand(webster_config, 2.0)
    for original, new in zip(webster_config.demand, scaled.demand):
        assert new.volume == original.volume * 2.0


def test_compare_returns_one_result_per_multiplier(webster_config):
    req = ScenarioRequest(
        config=webster_config,
        multipliers=[
            DemandMultiplier(name="bajo", factor=0.5),
            DemandMultiplier(name="alto", factor=1.5),
        ],
    )
    comparison = compare(req)
    assert len(comparison.scenarios) == 2
    assert [s.name for s in comparison.scenarios] == ["bajo", "alto"]


def test_worst_scenario_drives_strategy(make_two_phase):
    # Demanda baja en el único escenario -> peor LOS aceptable (A/B/C)
    # -> estrategia de "Operación normal".
    req = ScenarioRequest(
        config=make_two_phase(90.0),
        multipliers=[DemandMultiplier(name="base", factor=1.0)],
    )
    comparison = compare(req)
    assert comparison.recommended_strategy.startswith("Operación normal")
