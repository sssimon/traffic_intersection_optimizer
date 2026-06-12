"""Pruebas — coordinación de corredor (tarea 4.1, M5).

Casos derivados a mano: banda cíclica, offset ideal de ida, PF de progresión
(perfecta → 0, aleatoria → 1, pésima → 1/(1−g/C)).
"""
import pytest

from app.corridor import _bandwidth, _cyclic_overlap, process_corridor
from app.models import CorridorIntersectionInput, CorridorRequest


def _pair(distance=250.0, speed=45.0, vol_in=0.0, green=30.0):
    """Dos intersecciones; a 45 km/h, 250 m → τ = 20 s."""
    return [
        CorridorIntersectionInput(
            name="A", green_s=green, distance_to_next_m=distance,
            speed_to_next_kmh=speed, vol_out=600.0, vol_in=vol_in,
        ),
        CorridorIntersectionInput(
            name="B", green_s=green, vol_out=600.0, vol_in=vol_in,
        ),
    ]


def test_cyclic_overlap_cases():
    assert _cyclic_overlap(0, 30, 10, 30, 80) == pytest.approx(20.0)
    assert _cyclic_overlap(0, 30, 40, 30, 80) == pytest.approx(0.0)
    # Ventana que cruza el fin del ciclo: [70, 100) ≡ [70,80)+[0,20).
    assert _cyclic_overlap(70, 30, 0, 30, 80) == pytest.approx(20.0)
    assert _cyclic_overlap(0, 80, 10, 30, 80) == pytest.approx(30.0)


def test_bandwidth_full_and_disjoint():
    # Ventanas idénticas -> banda = verde completo, inicia en el borde.
    band, start = _bandwidth([10.0, 10.0], [30.0, 30.0], 80.0)
    assert band == pytest.approx(30.0)
    assert start == pytest.approx(10.0)
    # Disjuntas -> banda 0.
    band, _ = _bandwidth([0.0, 40.0], [30.0, 30.0], 80.0)
    assert band == pytest.approx(0.0)
    # Solape parcial 20 s.
    band, start = _bandwidth([0.0, 10.0], [30.0, 30.0], 80.0)
    assert band == pytest.approx(20.0)
    assert start == pytest.approx(10.0)


def test_one_way_optimization_finds_ideal_offset():
    # Solo ida: el offset óptimo de B es el tiempo de viaje (20 s) y la
    # banda es el verde completo (30 s). Progresión perfecta: P = 1, PF = 0.
    res = process_corridor(CorridorRequest(cycle_s=80.0, intersections=_pair()))
    assert res.band_out_s == pytest.approx(30.0)
    assert res.efficiency_out == pytest.approx(0.375)
    b = res.intersections[1]
    assert b.offset_s == pytest.approx(20.0, abs=1.0)
    assert b.p_green_out == pytest.approx(1.0)
    assert b.pf_out == pytest.approx(0.0, abs=0.01)
    # Coordinada elimina d1 en B: demora menor que aislada.
    assert b.delay_out_s < b.delay_isolated_out_s
    assert res.avg_artery_delay_s < res.avg_artery_delay_isolated_s


def test_bad_manual_offset_penalizes_with_pf_above_one():
    # Offset 60: el pelotón de A (llega 20–50) cae fuera del verde de B
    # (60–90): P = 0 -> PF = 1/(1 − 30/80) = 1.6 y la demora empeora.
    res = process_corridor(CorridorRequest(
        cycle_s=80.0,
        intersections=_pair(),
        offsets_s=[0.0, 60.0],
        optimize_offsets=False,
    ))
    b = res.intersections[1]
    assert b.p_green_out == pytest.approx(0.0)
    assert b.pf_out == pytest.approx(1.6)
    assert b.delay_out_s > b.delay_isolated_out_s
    assert res.offsets_optimized is False


def test_first_intersection_has_random_arrivals():
    res = process_corridor(CorridorRequest(cycle_s=80.0, intersections=_pair()))
    a = res.intersections[0]
    assert a.p_green_out is None
    assert a.pf_out == pytest.approx(1.0)
    assert a.delay_out_s == pytest.approx(a.delay_isolated_out_s)
    # Vuelta: la última intersección es la primera de ese sentido.
    assert res.intersections[-1].p_green_in is None
    assert res.intersections[-1].pf_in == pytest.approx(1.0)


def test_two_way_bands_bounded_and_consistent():
    ints = [
        CorridorIntersectionInput(name="A", green_s=40.0, distance_to_next_m=300.0,
                                  speed_to_next_kmh=40.0, vol_out=500, vol_in=500),
        CorridorIntersectionInput(name="B", green_s=45.0, distance_to_next_m=350.0,
                                  speed_to_next_kmh=50.0, vol_out=500, vol_in=500),
        CorridorIntersectionInput(name="C", green_s=40.0, vol_out=500, vol_in=500),
    ]
    res = process_corridor(CorridorRequest(cycle_s=90.0, intersections=ints))
    min_green = 40.0
    assert 0.0 <= res.band_out_s <= min_green
    assert 0.0 <= res.band_in_s <= min_green
    assert res.band_out_s + res.band_in_s > 0.0
    assert len(res.travel_times_s) == 3
    assert res.travel_times_s[0] == 0.0
    for it in res.intersections:
        for p in (it.p_green_out, it.p_green_in):
            if p is not None:
                assert 0.0 <= p <= 1.0


def test_validation_errors():
    with pytest.raises(ValueError):
        process_corridor(CorridorRequest(
            cycle_s=80.0,
            intersections=_pair(green=85.0),  # verde >= ciclo
        ))
    with pytest.raises(ValueError):
        process_corridor(CorridorRequest(
            cycle_s=80.0,
            intersections=_pair(),
            offsets_s=[0.0],  # longitud incorrecta
            optimize_offsets=False,
        ))
