"""Pruebas de regresión — análisis no semaforizado TWSC, HCM cap. 19
(app/unsignalized.py).

Valores esperados derivados a mano de las fórmulas de aceptación de brechas.
Si se alteran las fórmulas de capacidad/demora, estas pruebas lo detectan.
"""
import pytest

from app.models import (
    Approach,
    Demand,
    IntersectionConfig,
    LaneGroup,
    LOSGrade,
    MovementType,
)
from app.unsignalized import (
    GAP,
    _gap_delay,
    _potential_capacity,
    analyze_twsc,
    los_unsignalized,
)


def _twsc_with_minor_left(include_opposing: bool) -> IntersectionConfig:
    """E/W principal directa (500 c/u); N con izquierda menor (100);
    S opcional con directo menor (120). PHF = 1.0."""
    approaches = [
        Approach(id="E", name="Este", lane_groups=[
            LaneGroup(id="E-T", movement=MovementType.THROUGH, lanes=1)]),
        Approach(id="W", name="Oeste", lane_groups=[
            LaneGroup(id="W-T", movement=MovementType.THROUGH, lanes=1)]),
        Approach(id="N", name="Norte", lane_groups=[
            LaneGroup(id="N-L", movement=MovementType.LEFT, lanes=1)]),
    ]
    demand = [
        Demand(lane_group_id="E-T", volume=500.0),
        Demand(lane_group_id="W-T", volume=500.0),
        Demand(lane_group_id="N-L", volume=100.0),
    ]
    if include_opposing:
        approaches.append(Approach(id="S", name="Sur", lane_groups=[
            LaneGroup(id="S-T", movement=MovementType.THROUGH, lanes=1)]))
        demand.append(Demand(lane_group_id="S-T", volume=120.0))
    return IntersectionConfig(
        name="twsc-izq-menor",
        approaches=approaches,
        phases=[],
        demand=demand,
        peak_hour_factor=1.0,
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


def test_minor_left_uses_two_lane_base_gap():
    # 1.3: principal de 2 carriles -> tc = 7.1 (7.5 era el valor de 4
    # carriles, inconsistente con el supuesto declarado del módulo).
    assert GAP["minor_left"] == (7.1, 3.5)


def test_rank4_impedance_with_p_prime_adjustment():
    # Cálculo a mano (HCM 2000 ec. 17-1, 17-8, 17-9; PHF=1):
    #   S-T (rango 3): vc = 1000 -> cp = 245.1 ; p0 = 1 - 120/245.1 = 0.5103
    #   N-L (rango 4): vc = 1000 + 120 = 1120, tc=7.1, tf=3.5 -> cp = 185.4
    #   p″ = 1·0.5103 ; p′ = 0.65p″ − p″/(p″+3) + 0.6√p″ = 0.6149
    #   cm = 185.4 · 0.6149 = 114.0 veh/h
    # (El producto directo de p0 —comportamiento anterior— daría 94.6:
    #  el ajuste p′ corrige esa sobre-impedancia.)
    result = analyze_twsc(_twsc_with_minor_left(include_opposing=True),
                          ["E", "W"])
    nl = next(m for m in result.movements if m.lane_group_id == "N-L")
    assert nl.capacity == pytest.approx(114.0, abs=1.0)
    assert nl.capacity > 95.0  # > producto directo (94.6)


def test_rank4_without_opposing_minor_behaves_as_rank3():
    # 3 ramas: sin directo menor opuesto, la izquierda menor opera como
    # rango 3 (HCM) y la brecha lleva el ajuste t3,LT = -0.7 (ec. 17-1).
    # Sin izquierdas mayores: cm = cp.
    #   vc = 1000, tc = 7.1 - 0.7 = 6.4, tf = 3.5 -> cp = 271.8 veh/h
    result = analyze_twsc(_twsc_with_minor_left(include_opposing=False),
                          ["E", "W"])
    nl = next(m for m in result.movements if m.lane_group_id == "N-L")
    assert nl.capacity == pytest.approx(271.8, abs=1.0)
