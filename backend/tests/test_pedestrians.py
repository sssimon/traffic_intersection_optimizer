"""Pruebas — análisis peatonal (M10, tarea 5.3).

Valores derivados a mano de las fórmulas: FDW = L/Sp, mínimo MUTCD = Walk +
FDW, demora dp = 0.5·C·(1 − gp/C)², LOS por demora.
"""
import pytest

from app.analysis import analyze
from app.data import sample_intersection
from app.models import (
    Approach,
    Crossing,
    Demand,
    IntersectionConfig,
    LaneGroup,
    MovementType,
    Phase,
    SignalPlan,
)
from app.optimizer import optimize
from app.pedestrians import _ped_los, analyze_pedestrians


def _plan(cycle, greens):
    return SignalPlan(
        cycle_length=cycle, phase_green=greens,
        phase_yellow={k: 3.0 for k in greens}, phase_all_red={k: 1.0 for k in greens},
        total_lost_time=4.0 * len(greens),
    )


def _cfg_with_crossing(length=12.0, phase="P1", walk=7.0, speed=1.2):
    return IntersectionConfig(
        name="ped-test",
        approaches=[Approach(id="N", name="N", lane_groups=[
            LaneGroup(id="N-T", movement=MovementType.THROUGH, lanes=1)])],
        phases=[Phase(id="P1", name="P1", lane_group_ids=["N-T"])],
        demand=[Demand(lane_group_id="N-T", volume=400)],
        crossings=[Crossing(id="X", name="Cruce", length_m=length,
                            phase_id=phase, walk_speed_ms=speed, walk_interval_s=walk)],
        peak_hour_factor=1.0,
    )


def test_delay_and_clearance_formula():
    cfg = _cfg_with_crossing(length=12.0, walk=7.0, speed=1.2)
    # C=100, gp=40: FDW=12/1.2=10, min=7+10=17, dp=0.5*100*(1-0.4)^2=18.0
    res, warns = analyze_pedestrians(cfg, _plan(100.0, {"P1": 40.0}))
    assert len(res) == 1
    p = res[0]
    assert p.clearance_s == pytest.approx(10.0)
    assert p.min_required_s == pytest.approx(17.0)
    assert p.avg_delay_s == pytest.approx(18.0, abs=0.05)
    assert p.sufficient_green is True   # 40 >= 17
    assert p.los.value == "B"           # 18 s -> B (10<d<=20)
    assert warns == []


def test_insufficient_green_warns():
    # gp=12 < min=17 -> insuficiente, con aviso.
    cfg = _cfg_with_crossing(length=12.0, walk=7.0)
    res, warns = analyze_pedestrians(cfg, _plan(100.0, {"P1": 12.0}))
    assert res[0].sufficient_green is False
    assert any("mínimo seguro" in w for w in warns)


def test_ped_los_thresholds():
    assert _ped_los(10.0).value == "A"
    assert _ped_los(10.1).value == "B"
    assert _ped_los(30.0).value == "C"
    assert _ped_los(55.0).value == "E"
    assert _ped_los(60.1).value == "F"


def test_missing_phase_is_skipped_with_warning():
    cfg = _cfg_with_crossing(phase="NOPE")
    res, warns = analyze_pedestrians(cfg, _plan(100.0, {"P1": 40.0}))
    assert res == []
    assert any("no existe" in w for w in warns)


def test_no_crossings_means_empty():
    cfg = _cfg_with_crossing()
    cfg.crossings = []
    res, warns = analyze_pedestrians(cfg, _plan(100.0, {"P1": 40.0}))
    assert res == [] and warns == []


def test_analyze_includes_pedestrians_for_sample():
    sample = sample_intersection()
    an = analyze(sample, optimize(sample))
    assert len(an.pedestrians) == 2
    ids = {p.crossing_id for p in an.pedestrians}
    assert ids == {"X-N", "X-E"}
    # Ambos cruces del ejemplo tienen verde suficiente (avisos solo si falta).
    assert all(p.los.value in {"A", "B", "C", "D", "E", "F"} for p in an.pedestrians)


def test_pedestrians_do_not_change_vehicular_metrics():
    # El snapshot vehicular del ejemplo no cambia por agregar cruces.
    sample = sample_intersection()
    an = analyze(sample, optimize(sample))
    assert an.avg_delay_s == 56.0
    assert an.overall_los.value == "E"
    assert an.overall_v_c == 0.929
