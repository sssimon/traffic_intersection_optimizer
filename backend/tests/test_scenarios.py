"""Pruebas de regresión — comparación de escenarios (app/scenarios.py).

Incluye los escenarios direccionales (M8): factor global, por acceso y por
movimiento, con prioridad movimiento > acceso > global.
"""
from app.models import DemandMultiplier, ScenarioRequest
from app.scenarios import _apply_spec, compare


def test_uniform_factor_scales_all(webster_config):
    scaled, label = _apply_spec(
        webster_config, DemandMultiplier(name="x2", factor=2.0)
    )
    for original, new in zip(webster_config.demand, scaled.demand):
        assert new.volume == original.volume * 2.0
    assert label == "global ×2.00"


def test_approach_factor_overrides_global(webster_config):
    # webster_config: accesos N (N-T) y E (E-T), 630 veh/h cada uno.
    spec = DemandMultiplier(
        name="desarrollo N", factor=1.0, approach_factors={"N": 1.5}
    )
    scaled, label = _apply_spec(webster_config, spec)
    vols = {d.lane_group_id: d.volume for d in scaled.demand}
    assert vols["N-T"] == 630.0 * 1.5
    assert vols["E-T"] == 630.0
    assert "acceso N ×1.50" in label


def test_movement_factor_overrides_approach(webster_config):
    spec = DemandMultiplier(
        name="mixto",
        factor=1.0,
        approach_factors={"N": 1.5},
        movement_factors={"N-T": 0.8},
    )
    scaled, _ = _apply_spec(webster_config, spec)
    vols = {d.lane_group_id: d.volume for d in scaled.demand}
    # El factor de movimiento manda sobre el de acceso.
    assert vols["N-T"] == 630.0 * 0.8


def test_unknown_ids_produce_warnings(webster_config):
    req = ScenarioRequest(
        config=webster_config,
        multipliers=[DemandMultiplier(
            name="typo",
            factor=1.0,
            approach_factors={"Z": 1.2},
            movement_factors={"X-T": 1.2},
        )],
    )
    comparison = compare(req)
    assert len(comparison.warnings) == 2


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


def test_directional_scenario_flags_and_worsens_delay(webster_config):
    req = ScenarioRequest(
        config=webster_config,
        multipliers=[
            DemandMultiplier(name="base", factor=1.0),
            DemandMultiplier(name="desarrollo E", approach_factors={"E": 1.6}),
        ],
    )
    comparison = compare(req)
    base, directional = comparison.scenarios
    assert directional.directional and not base.directional
    assert directional.analysis.avg_delay_s > base.analysis.avg_delay_s


def test_delay_min_method_uses_delay_optimizer(webster_config):
    req = ScenarioRequest(
        config=webster_config,
        multipliers=[DemandMultiplier(name="base", factor=1.0)],
        method="delay_min",
    )
    comparison = compare(req)
    notes = comparison.scenarios[0].analysis.signal_plan.notes
    assert any("minimización" in n for n in notes)


def test_worst_scenario_drives_strategy(make_two_phase):
    # Demanda baja en el único escenario -> peor LOS aceptable (A/B/C)
    # -> estrategia de "Operación normal".
    req = ScenarioRequest(
        config=make_two_phase(90.0),
        multipliers=[DemandMultiplier(name="base", factor=1.0)],
    )
    comparison = compare(req)
    assert comparison.recommended_strategy.startswith("Operación normal")
