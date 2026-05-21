"""Fixtures compartidas para la batería de pruebas de regresión.

Las configuraciones de prueba usan números deliberadamente sencillos
(saturación 1800, PHF 1.0) para que el resultado esperado pueda derivarse
a mano de las fórmulas y verificarse en los comentarios de cada prueba.
"""
from __future__ import annotations

import pytest

from app.models import (
    Approach,
    Demand,
    IntersectionConfig,
    LaneGroup,
    MovementType,
    Phase,
)


@pytest.fixture
def make_two_phase():
    """Fábrica: intersección de 2 fases, 1 carril por acceso.

    Con PHF=1.0 y `saturation` por carril, cada fase tiene flujo crítico
    y = volume / saturation. Devolver una fábrica permite variar la demanda
    para probar los regímenes de Webster (normal, sobre-saturado, mínimo).
    """

    def _make(volume: float, volume2: float | None = None,
              saturation: float = 1800.0) -> IntersectionConfig:
        # volume2 permite demanda distinta por fase (escenarios desbalanceados).
        v2 = volume if volume2 is None else volume2
        return IntersectionConfig(
            name="test-2fases",
            approaches=[
                Approach(id="N", name="Norte", lane_groups=[
                    LaneGroup(id="N-T", movement=MovementType.THROUGH, lanes=1,
                              saturation_flow_per_lane=saturation)]),
                Approach(id="E", name="Este", lane_groups=[
                    LaneGroup(id="E-T", movement=MovementType.THROUGH, lanes=1,
                              saturation_flow_per_lane=saturation)]),
            ],
            phases=[
                Phase(id="P1", name="Norte", lane_group_ids=["N-T"]),
                Phase(id="P2", name="Este", lane_group_ids=["E-T"]),
            ],
            demand=[
                Demand(lane_group_id="N-T", volume=volume),
                Demand(lane_group_id="E-T", volume=v2),
            ],
            peak_hour_factor=1.0,
        )

    return _make


@pytest.fixture
def webster_config(make_two_phase):
    """Caso base: demanda 630 veh/h -> Y = 2*(630/1800) = 0.70."""
    return make_two_phase(630.0)


@pytest.fixture
def single_movement_config():
    """Un solo movimiento, para verificar el modelo de demora HCM aislado."""
    return IntersectionConfig(
        name="test-1movimiento",
        approaches=[
            Approach(id="N", name="Norte", lane_groups=[
                LaneGroup(id="N-T", movement=MovementType.THROUGH, lanes=1,
                          saturation_flow_per_lane=1800.0)]),
        ],
        phases=[Phase(id="P1", name="Norte", lane_group_ids=["N-T"])],
        demand=[Demand(lane_group_id="N-T", volume=600.0)],
        peak_hour_factor=1.0,
    )


@pytest.fixture
def right_turn_roundabout():
    """Glorieta de 4 ramas con solo giros a la derecha.

    Los giros a la derecha no aportan al flujo circulante, así que el flujo
    circulante de cada acceso es 0 y la capacidad de entrada queda en el
    intercepto puro: c = A * exp(0) * 1 = A.
    """
    quad = [("N", "Norte"), ("E", "Este"), ("S", "Sur"), ("W", "Oeste")]
    return IntersectionConfig(
        name="test-glorieta",
        approaches=[
            Approach(id=i, name=n, lane_groups=[
                LaneGroup(id=f"{i}-R", movement=MovementType.RIGHT, lanes=1,
                          saturation_flow_per_lane=1800.0)])
            for i, n in quad
        ],
        phases=[],
        demand=[Demand(lane_group_id=f"{i}-R", volume=300.0) for i, _ in quad],
        peak_hour_factor=1.0,
    )


@pytest.fixture
def twsc_config():
    """Intersección con PARE: E y W son la calle principal; N y S la secundaria."""
    return IntersectionConfig(
        name="test-twsc",
        approaches=[
            Approach(id="E", name="Este", lane_groups=[
                LaneGroup(id="E-T", movement=MovementType.THROUGH, lanes=1)]),
            Approach(id="W", name="Oeste", lane_groups=[
                LaneGroup(id="W-T", movement=MovementType.THROUGH, lanes=1)]),
            Approach(id="N", name="Norte", lane_groups=[
                LaneGroup(id="N-T", movement=MovementType.THROUGH, lanes=1)]),
            Approach(id="S", name="Sur", lane_groups=[
                LaneGroup(id="S-T", movement=MovementType.THROUGH, lanes=1)]),
        ],
        phases=[],
        demand=[
            Demand(lane_group_id="E-T", volume=500.0),
            Demand(lane_group_id="W-T", volume=500.0),
            Demand(lane_group_id="N-T", volume=120.0),
            Demand(lane_group_id="S-T", volume=120.0),
        ],
        peak_hour_factor=1.0,
    )
