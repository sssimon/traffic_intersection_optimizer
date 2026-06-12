"""Validación cruzada contra el Ejemplo 1 publicado del HCM (tarea 1.8).

Fuente: HCM 2000, cap. 17, Example Problem 1 — intersección en T con PARE
en la calle menor (NB), izquierda exclusiva WB, 10 % de pesados, terreno
plano, sin peatones. Valores publicados en los worksheets del manual:

    tc/tf con ajuste por pesados:  izq. mayor 4.200/2.290 ·
    der. menor 6.300/3.390 · izq. menor (T) 6.500/3.590
    vc,9 = 270  -> cp,9 = 750     vc,4 = 290 -> cp,4 = 1227
    vc,7 = 870  -> cp,7 = 312 ;  cm,7 = 312·0.878 = 274
    Carril compartido NB (40+120 veh/h, cSH = 523): d = 14.9 s, LOS B

Bloque A — nivel fórmula: con las ENTRADAS del manual (sus tc/tf ya
ajustados), nuestras ecuaciones reproducen los valores publicados (<1 %).

Bloque B — motor completo sobre los volúmenes del ejemplo (v2=250, v3=40,
v4=150, v5=300, v7=40, v9=120; PHF=1, PCU=1): las desviaciones provienen de
las simplificaciones declaradas (pesados vía PCU y no en tc/tf; carriles
menores separados, no compartidos). Demoras por movimiento dentro de ±5 %
de las equivalentes publicadas por carril separado. Ver docs/validacion.md.
"""
import pytest

from app.models import (
    Approach,
    Demand,
    IntersectionConfig,
    LaneGroup,
    MovementType,
)
from app.unsignalized import _gap_delay, _potential_capacity, analyze_twsc


# ---------- Bloque A: fórmulas con entradas publicadas ----------

def test_potential_capacity_minor_right_published():
    # cp,9 = 750 veh/h (vc=270, tc=6.300, tf=3.390)
    assert _potential_capacity(270.0, 6.300, 3.390) == pytest.approx(750.0, abs=2.0)


def test_potential_capacity_major_left_published():
    # cp,4 = 1227 veh/h (vc=290, tc=4.200, tf=2.290)
    assert _potential_capacity(290.0, 4.200, 2.290) == pytest.approx(1227.0, abs=3.0)


def test_potential_capacity_minor_left_T_published():
    # cp,7 = 312 veh/h (vc=870, tc=6.500, tf=3.590)
    assert _potential_capacity(870.0, 6.500, 3.590) == pytest.approx(312.0, abs=2.0)


def test_control_delay_published():
    # Carril compartido NB: v=160, cSH=523 -> d = 14.9 s (LOS B)
    assert _gap_delay(160.0, 523.0) == pytest.approx(14.9, abs=0.15)


# ---------- Bloque B: motor completo sobre el Ejemplo 1 ----------

def _example1_config() -> IntersectionConfig:
    """Volúmenes del Ejemplo 1; PHF=1 y PCU=1 para aislar las diferencias
    estructurales (los pesados del ejemplo van en tc/tf, no en demanda)."""
    return IntersectionConfig(
        name="HCM2000-ej1",
        approaches=[
            Approach(id="E", name="EB", lane_groups=[
                LaneGroup(id="E-T", movement=MovementType.THROUGH, lanes=1),
                LaneGroup(id="E-R", movement=MovementType.RIGHT, lanes=1),
            ]),
            Approach(id="W", name="WB", lane_groups=[
                LaneGroup(id="W-T", movement=MovementType.THROUGH, lanes=1),
                LaneGroup(id="W-L", movement=MovementType.LEFT, lanes=1),
            ]),
            Approach(id="N", name="NB (PARE)", lane_groups=[
                LaneGroup(id="N-L", movement=MovementType.LEFT, lanes=1),
                LaneGroup(id="N-R", movement=MovementType.RIGHT, lanes=1),
            ]),
        ],
        phases=[],
        demand=[
            Demand(lane_group_id="E-T", volume=250.0),
            Demand(lane_group_id="E-R", volume=40.0),
            Demand(lane_group_id="W-T", volume=300.0),
            Demand(lane_group_id="W-L", volume=150.0),
            Demand(lane_group_id="N-L", volume=40.0),
            Demand(lane_group_id="N-R", volume=120.0),
        ],
        peak_hour_factor=1.0,
    )


def test_example1_conflicting_flows():
    result = analyze_twsc(_example1_config(), ["E", "W"])
    by_id = {m.lane_group_id: m for m in result.movements}
    # Izquierda mayor WB: vc = v2 + v3 = 290 — idéntico al manual.
    assert by_id["W-L"].conflicting_flow == pytest.approx(290.0)
    # Izquierda menor (T): vc = VT + 0.5·VR + 2·VL = 550 + 20 + 300 = 870
    # — idéntico al manual (descomposición 2·150 + 250 + 20 + 300).
    assert by_id["N-L"].conflicting_flow == pytest.approx(870.0)
    # Derecha menor: aproximación de ambos sentidos: 0.5·550 + 0.25·40 = 285
    # (manual: 270 con un solo sentido; +5.6 % en vc, +1 % en capacidad).
    assert by_id["N-R"].conflicting_flow == pytest.approx(285.0)


def test_example1_capacities_within_documented_deviation():
    result = analyze_twsc(_example1_config(), ["E", "W"])
    by_id = {m.lane_group_id: m for m in result.movements}
    # Con brechas BASE (pesados vía PCU, aquí PCU=1):
    #   W-L: cp(290, 4.1, 2.2) = 1283 (publicado con ajuste HV: 1227, +4.6 %)
    #   N-R: cp(285, 6.2, 3.3) = 759  (publicado 750, +1.2 %)
    #   N-L: cp(870, 6.4, 3.5)·p0(W-L) = 324.6·0.8831 = 287 (publicado 274,
    #        +4.6 %)
    assert by_id["W-L"].capacity == pytest.approx(1283.0, abs=3.0)
    assert by_id["N-R"].capacity == pytest.approx(759.0, abs=3.0)
    assert by_id["N-L"].capacity == pytest.approx(287.0, abs=3.0)
    # Desviación frente a lo publicado < 5 %:
    assert abs(by_id["W-L"].capacity - 1227.0) / 1227.0 < 0.05
    assert abs(by_id["N-R"].capacity - 750.0) / 750.0 < 0.05
    assert abs(by_id["N-L"].capacity - 274.0) / 274.0 < 0.05


def test_example1_delays_within_5pct_of_published_equivalents():
    # El manual publica la demora del carril COMPARTIDO NB (14.9 s); nuestro
    # modelo usa carriles separados. Comparamos cada movimiento contra la
    # demora publicada-equivalente por carril separado con las capacidades
    # del manual: d(150, 1227) = 8.3 ; d(120, 750) = 10.7 ; d(40, 274) = 20.4.
    result = analyze_twsc(_example1_config(), ["E", "W"])
    by_id = {m.lane_group_id: m for m in result.movements}
    published = {"W-L": 8.3, "N-R": 10.7, "N-L": 20.4}
    for lg_id, d_pub in published.items():
        d_ours = by_id[lg_id].avg_delay_s
        assert abs(d_ours - d_pub) / d_pub < 0.05, (lg_id, d_ours, d_pub)
