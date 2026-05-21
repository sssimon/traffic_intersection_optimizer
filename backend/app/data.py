"""Configuración de ejemplo: intersección de 4 accesos con fase doble.

Sirve como punto de partida para el frontend ("Cargar ejemplo") y como
caso de prueba. Refleja una intersección urbana con congestión: dos accesos
N-S y dos E-W, con giros a izquierda permitidos en fase exclusiva.
"""
from __future__ import annotations

from .models import (
    Approach,
    Demand,
    IntersectionConfig,
    LaneGroup,
    MovementType,
    Phase,
)


def sample_intersection() -> IntersectionConfig:
    approaches = [
        Approach(
            id="N",
            name="Norte",
            lane_groups=[
                LaneGroup(id="N-T", movement=MovementType.THROUGH, lanes=2),
                LaneGroup(id="N-L", movement=MovementType.LEFT, lanes=1),
                LaneGroup(id="N-R", movement=MovementType.RIGHT, lanes=1, shared_with_through=True),
            ],
        ),
        Approach(
            id="S",
            name="Sur",
            lane_groups=[
                LaneGroup(id="S-T", movement=MovementType.THROUGH, lanes=2),
                LaneGroup(id="S-L", movement=MovementType.LEFT, lanes=1),
                LaneGroup(id="S-R", movement=MovementType.RIGHT, lanes=1, shared_with_through=True),
            ],
        ),
        Approach(
            id="E",
            name="Este",
            lane_groups=[
                LaneGroup(id="E-T", movement=MovementType.THROUGH, lanes=2),
                LaneGroup(id="E-L", movement=MovementType.LEFT, lanes=1),
            ],
        ),
        Approach(
            id="W",
            name="Oeste",
            lane_groups=[
                LaneGroup(id="W-T", movement=MovementType.THROUGH, lanes=2),
                LaneGroup(id="W-L", movement=MovementType.LEFT, lanes=1),
            ],
        ),
    ]

    phases = [
        Phase(id="P1", name="N-S directo", lane_group_ids=["N-T", "N-R", "S-T", "S-R"]),
        Phase(id="P2", name="N-S izquierda", lane_group_ids=["N-L", "S-L"], max_green=25.0),
        Phase(id="P3", name="E-W directo", lane_group_ids=["E-T", "W-T"]),
        Phase(id="P4", name="E-W izquierda", lane_group_ids=["E-L", "W-L"], max_green=25.0),
    ]

    # Demanda en hora pico — refleja congestión (E-W más cargado)
    demand = [
        Demand(lane_group_id="N-T", volume=820),
        Demand(lane_group_id="N-L", volume=180),
        Demand(lane_group_id="N-R", volume=160),
        Demand(lane_group_id="S-T", volume=780),
        Demand(lane_group_id="S-L", volume=160),
        Demand(lane_group_id="S-R", volume=140),
        Demand(lane_group_id="E-T", volume=1150),
        Demand(lane_group_id="E-L", volume=240),
        Demand(lane_group_id="W-T", volume=1080),
        Demand(lane_group_id="W-L", volume=210),
    ]

    return IntersectionConfig(
        name="Intersección ejemplo (4×4 con giros izquierda)",
        approaches=approaches,
        phases=phases,
        demand=demand,
        peak_hour_factor=0.92,
    )
