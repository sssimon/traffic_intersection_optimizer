"""Pruebas — explorador de alternativas de control (tarea 2.1).

Criterio de aceptación: para el caso de ejemplo, ranking completo en < 2 s.
"""
import time

from app.alternatives import compare_controls
from app.data import sample_intersection
from app.models import (
    Approach,
    CompareControlsRequest,
    Demand,
    IntersectionConfig,
    LaneGroup,
    MovementType,
    Phase,
)


def _four_leg(volume_major: float, volume_minor: float,
              split_phases: bool = False) -> IntersectionConfig:
    """4 ramas solo-directo; fases N-S / E-W (o partidas por acceso)."""
    quad = [("N", volume_minor), ("S", volume_minor),
            ("E", volume_major), ("W", volume_major)]
    approaches = [
        Approach(id=i, name=i, lane_groups=[
            LaneGroup(id=f"{i}-T", movement=MovementType.THROUGH, lanes=1)])
        for i, _ in quad
    ]
    if split_phases:
        phases = [Phase(id=f"P{i}", name=i, lane_group_ids=[f"{i}-T"])
                  for i, _ in quad]
    else:
        phases = [
            Phase(id="P1", name="N-S", lane_group_ids=["N-T", "S-T"]),
            Phase(id="P2", name="E-W", lane_group_ids=["E-T", "W-T"]),
        ]
    return IntersectionConfig(
        name="test-4ramas",
        approaches=approaches,
        phases=phases,
        demand=[Demand(lane_group_id=f"{i}-T", volume=v) for i, v in quad],
        peak_hour_factor=1.0,
    )


def test_sample_ranking_complete_and_fast():
    t0 = time.perf_counter()
    res = compare_controls(CompareControlsRequest(config=sample_intersection()))
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0  # criterio de aceptación 2.1
    assert {a.id for a in res.alternatives} == {
        "signal_current", "signal_split", "twsc"
    }
    delays = [a.avg_delay_s for a in res.alternatives]
    assert delays == sorted(delays)
    assert res.recommended_id == res.alternatives[0].id


def test_sample_twsc_majors_auto_selected_and_collapsed():
    res = compare_controls(CompareControlsRequest(config=sample_intersection()))
    twsc = next(a for a in res.alternatives if a.kind == "twsc")
    # E y W son los accesos de mayor demanda del ejemplo.
    assert "E" in twsc.name and "W" in twsc.name
    # Con la demanda del ejemplo el PARE colapsa: gana un semáforo.
    assert any("No viable" in n for n in twsc.notes)
    assert res.alternatives[0].kind == "signal"


def test_split_scheme_assigns_every_group():
    res = compare_controls(CompareControlsRequest(config=sample_intersection()))
    split = next(a for a in res.alternatives if a.id == "signal_split")
    assert split.signal is not None
    # Los 10 grupos del ejemplo quedan asignados a fases por acceso (S-*).
    assert len(split.signal.movements) == 10
    assert all(m.phase_id.startswith("S-") for m in split.signal.movements)
    assert len(split.signal.signal_plan.phase_green) == 4


def test_low_demand_recommends_stop():
    # Principal 250 veh/h por sentido, secundaria 60: el PARE opera en
    # LOS A-C y con menor demora media que cualquier semáforo.
    res = compare_controls(CompareControlsRequest(
        config=_four_leg(volume_major=250.0, volume_minor=60.0)))
    assert res.recommended_id == "twsc"
    assert any("podría no estar justificado" in r for r in res.rationale)


def test_duplicate_split_scheme_suppressed():
    # Si el esquema configurado YA es por acceso, no se duplica.
    res = compare_controls(CompareControlsRequest(
        config=_four_leg(250.0, 60.0, split_phases=True)))
    assert {a.id for a in res.alternatives} == {"signal_current", "twsc"}


def test_no_phases_still_ranks_with_warning():
    cfg = _four_leg(250.0, 60.0)
    cfg.phases = []
    res = compare_controls(CompareControlsRequest(config=cfg))
    assert {a.id for a in res.alternatives} == {"signal_split", "twsc"}
    assert any("no tiene fases" in w for w in res.warnings)


def test_explicit_majors_respected_and_bad_ids_warn():
    res = compare_controls(CompareControlsRequest(
        config=_four_leg(250.0, 60.0),
        major_approach_ids=["N", "S", "Z"],
    ))
    twsc = next(a for a in res.alternatives if a.kind == "twsc")
    assert "N" in twsc.name and "S" in twsc.name
    assert any("'Z' no existe" in w for w in res.warnings)
