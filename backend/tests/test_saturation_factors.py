"""Pruebas — cadena de factores de saturación HCM (M9, tarea 1.4).

Caso del manual calculado a mano (HCM 2010 cap. 18):
2 carriles directos, W = 3.05 m (10 ft), pendiente +2 %, 20 maniobras/h de
estacionamiento adyacente, 10 buses/h, CBD, fLU = 0.952:

    fw  = 1 + (3.05 − 3.66)/9.14        = 0.9333
    fg  = 1 − 2/200                     = 0.99
    fp  = (2 − 0.1 − 18·20/3600)/2      = 0.90
    fbb = (2 − 14.4·10/3600)/2          = 0.98
    fa  = 0.90 ;  fLU = 0.952
    producto = 0.6982  →  s = 1900·2·0.6982 = 2653.2 veh/h
"""
import pytest

from app.models import LaneGroup, MovementType, SaturationFactors


def _lg(**kw):
    base = dict(id="T", movement=MovementType.THROUGH, lanes=1)
    base.update(kw)
    return LaneGroup(**base)


def test_no_factors_keeps_legacy_behavior():
    assert _lg(lanes=2).saturation_flow == 1900.0 * 2


def test_empty_factors_are_neutral_for_through():
    lg = _lg(lanes=2, factors=SaturationFactors())
    assert lg.saturation_flow == pytest.approx(3800.0)


def test_manual_chain_example():
    lg = _lg(
        lanes=2,
        factors=SaturationFactors(
            lane_width_m=3.05,
            grade_pct=2.0,
            parking_maneuvers_per_h=20.0,
            bus_stops_per_h=10.0,
            cbd=True,
            lane_utilization=0.952,
        ),
    )
    assert lg.saturation_flow == pytest.approx(2653.2, abs=1.0)


def test_protected_turn_factors_apply_with_chain_active():
    left = _lg(movement=MovementType.LEFT, factors=SaturationFactors())
    right = _lg(movement=MovementType.RIGHT, factors=SaturationFactors())
    assert left.saturation_flow == pytest.approx(1900 * 0.95)
    assert right.saturation_flow == pytest.approx(1900 * 0.85)


def test_shared_lane_skips_turn_factor():
    # Compartido: solo la simplificación 0.85 del grupo, sin fRT adicional.
    shared = _lg(
        movement=MovementType.RIGHT,
        shared_with_through=True,
        factors=SaturationFactors(),
    )
    assert shared.saturation_flow == pytest.approx(1900 * 0.85)


def test_downhill_grade_increases_saturation():
    lg = _lg(factors=SaturationFactors(grade_pct=-4.0))
    assert lg.saturation_flow == pytest.approx(1900 * 1.02)


def test_parking_floor_at_005():
    # Nm máximo (180) en 1 carril: (1 − 0.1 − 0.9)/1 = 0 → piso 0.05.
    lg = _lg(factors=SaturationFactors(parking_maneuvers_per_h=180.0))
    assert lg.saturation_flow == pytest.approx(1900 * 0.05)
