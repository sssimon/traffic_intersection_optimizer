"""Pruebas de regresión — análisis no semaforizado TWSC, HCM cap. 19
(app/unsignalized.py).

Valores esperados derivados a mano de las fórmulas de aceptación de brechas.
Si se alteran las fórmulas de capacidad/demora, estas pruebas lo detectan.
"""
import pytest

from app.models import LOSGrade, MovementType
from app.unsignalized import (
    _gap_delay,
    _potential_capacity,
    analyze_twsc,
    los_unsignalized,
)


def test_los_unsignalized_thresholds():
    # Umbrales HCM no semaforizado: A<=10  B<=15  C<=25  D<=35  E<=50  F>50
    assert los_unsignalized(10.0) == LOSGrade.A
    assert los_unsignalized(15.0) == LOSGrade.B
    assert los_unsignalized(25.0) == LOSGrade.C
    assert los_unsignalized(35.0) == LOSGrade.D
    assert los_unsignalized(50.0) == LOSGrade.E
    assert los_unsignalized(50.1) == LOSGrade.F


def test_potential_capacity_formula():
    # cp = vc*exp(-vc*tc/3600) / (1 - exp(-vc*tf/3600))
    # vc=600, tc=6.2, tf=3.3 (giro derecha menor)  ->  cp ~= 504.6 veh/h
    cp = _potential_capacity(600.0, 6.2, 3.3)
    assert cp == pytest.approx(504.6, abs=1.0)


def test_gap_delay_formula():
    # vol=100, cap=500  ->  d = 3600/c + 900T[...] + 5 ~= 14.0 s
    d = _gap_delay(100.0, 500.0)
    assert d == pytest.approx(14.0, abs=0.5)


def test_gap_delay_zero_capacity_is_capped():
    # Capacidad nula -> demora topada en DELAY_CAP (999 s)
    assert _gap_delay(100.0, 0.0) == 999.0


def test_twsc_major_through_is_free(twsc_config):
    # El movimiento directo de la calle principal es de rango 1: circula
    # libre, sin demora de control y en LOS A.
    result = analyze_twsc(twsc_config, ["E", "W"])

    free = [m for m in result.movements if m.role == "mayor-libre"]
    assert len(free) == 2
    for m in free:
        assert m.movement == MovementType.THROUGH
        assert m.avg_delay_s == 0.0
        assert m.los == LOSGrade.A
        assert m.capacity is None


def test_twsc_minor_movement_is_impeded(twsc_config):
    # El movimiento de la calle secundaria sí tiene capacidad finita y
    # demora de control positiva.
    result = analyze_twsc(twsc_config, ["E", "W"])

    minor = [m for m in result.movements if m.role == "menor"]
    assert minor
    for m in minor:
        assert m.capacity is not None
        assert m.avg_delay_s > 0.0
