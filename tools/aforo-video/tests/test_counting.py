"""Pruebas de la lógica de conteo OD (sin YOLO ni video)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from counting import (  # noqa: E402
    OdCounter,
    apply_to_config,
    point_in_polygon,
    stitch_tracks,
)

SQ = lambda x0, y0: [(x0, y0), (x0 + 100, y0), (x0 + 100, y0 + 100), (x0, y0 + 100)]
ZONES = {"W": SQ(0, 200), "E": SQ(400, 200), "N": SQ(200, 0), "S": SQ(200, 400)}


def _line(p0, p1, n=20):
    return [
        (p0[0] + (p1[0] - p0[0]) * i / (n - 1), p0[1] + (p1[1] - p0[1]) * i / (n - 1))
        for i in range(n)
    ]


def test_point_in_polygon():
    assert point_in_polygon((50, 250), ZONES["W"])
    assert not point_in_polygon((150, 250), ZONES["W"])


def test_od_counting_by_class():
    c = OdCounter(ZONES)
    assert c.add_track("auto", _line((10, 250), (490, 250))) == "W>E"
    assert c.add_track("auto", _line((10, 250), (490, 250))) == "W>E"
    assert c.add_track("moto", _line((250, 10), (250, 490))) == "N>S"
    assert c.add_track("camion", _line((490, 250), (250, 480))) == "E>S"

    res = c.result(duration_s=60.0)
    by_od = {f"{m['from']}>{m['to']}": m for m in res["movements"]}
    assert by_od["W>E"]["auto"] == 2 and by_od["W>E"]["total"] == 2
    assert by_od["N>S"]["moto"] == 1
    assert by_od["E>S"]["camion"] == 1
    assert res["total_counted"] == 4
    # Expansión ×60 (60 s observados): 2 autos -> 120 veh/h.
    assert res["expansion_factor"] == pytest.approx(60.0)
    assert by_od["W>E"]["veh_h"] == pytest.approx(120.0)
    # PCU del movimiento de camión: 2.0 / 1 vehículo.
    assert by_od["E>S"]["pcu_factor"] == pytest.approx(2.0)
    assert by_od["N>S"]["pcu_factor"] == pytest.approx(0.5)


def test_discards():
    c = OdCounter(ZONES, min_points=8, min_displacement_px=40)
    assert c.add_track("auto", _line((10, 250), (490, 250), n=3)) is None  # corto
    assert c.add_track("auto", [(50, 250)] * 30) is None                  # inmóvil
    assert c.add_track("auto", _line((150, 250), (350, 250))) is None     # sin OD
    assert c.discarded == {"cortos": 1, "inmoviles": 1, "sin_od": 1}


def test_stitch_bridges_fragmented_journey():
    # Vehículo W→E a 10 px/frame, con el ID perdido entre los frames 20 y 50
    # (hueco de 30 frames = 1 s a 30 fps; recorre 300 px durante el hueco).
    seg_a = {"cls_votes": {"auto": 20},
             "points": [(f, 10.0 + 10.0 * f, 250.0) for f in range(0, 21)]}
    seg_b = {"cls_votes": {"camion": 5},  # la clase parpadea de noche
             "points": [(f, 10.0 + 10.0 * f, 250.0) for f in range(50, 70)]}
    chains = stitch_tracks([seg_a, seg_b], fps=30.0, max_gap_s=2.0)
    assert len(chains) == 1
    assert chains[0]["cls_votes"] == {"auto": 20, "camion": 5}
    assert len(chains[0]["points"]) == 41


def test_stitch_rejects_far_or_late_segments():
    seg_a = {"cls_votes": {"auto": 10},
             "points": [(f, 10.0 * f, 250.0) for f in range(0, 11)]}
    # Mismo instante de arranque pero a 400 px de la posición extrapolada.
    far = {"cls_votes": {"auto": 10},
           "points": [(f, 10.0 * f, 650.0) for f in range(13, 24)]}
    # Posición correcta pero 5 s después (fuera del hueco máximo).
    late = {"cls_votes": {"auto": 10},
            "points": [(f, 10.0 * f, 250.0) for f in range(160, 171)]}
    chains = stitch_tracks([seg_a, far, late], fps=30.0, max_gap_s=2.0)
    assert len(chains) == 3


def test_stitched_fragments_count_in_od():
    # Sin costura: ninguno de los dos fragmentos toca dos zonas.
    # Cosidos: el viaje completo cuenta W>E.
    seg_a = {"cls_votes": {"auto": 10},
             "points": [(f, 10.0 + 12.0 * f, 250.0) for f in range(0, 11)]}
    seg_b = {"cls_votes": {"auto": 10},
             "points": [(f, 10.0 + 12.0 * f, 250.0) for f in range(25, 41)]}
    chains = stitch_tracks([seg_a, seg_b], fps=30.0)
    c = OdCounter(ZONES)
    for ch in chains:
        cls_name = max(ch["cls_votes"].items(), key=lambda kv: kv[1])[0]
        c.add_track(cls_name, [(x, y) for _, x, y in ch["points"]])
    res = c.result(60.0)
    assert res["total_counted"] == 1
    assert res["movements"][0]["from"] == "W"
    assert res["movements"][0]["to"] == "E"


def test_apply_to_config_maps_and_warns():
    c = OdCounter(ZONES)
    c.add_track("auto", _line((10, 250), (490, 250)))
    c.add_track("auto", _line((490, 250), (10, 250)))
    tmc = c.result(duration_s=900.0)  # 15 min -> ×4

    config = {
        "approaches": [
            {"id": "W", "lane_groups": [{"id": "W-T"}]},
            {"id": "E", "lane_groups": [{"id": "E-T"}]},
        ],
        "demand": [{"lane_group_id": "W-T", "volume": 0, "pcu_factor": 1.0}],
    }
    updated, warnings = apply_to_config(
        config, tmc, {"W>E": "W-T", "E>W": "E-T", "N>S": "X-T"}
    )
    demand = {d["lane_group_id"]: d for d in updated["demand"]}
    assert demand["W-T"]["volume"] == pytest.approx(4.0)
    assert demand["E-T"]["volume"] == pytest.approx(4.0)
    assert any("N>S" in w for w in warnings)  # mapeo sin conteos
