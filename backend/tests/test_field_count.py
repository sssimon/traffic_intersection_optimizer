"""Pruebas — aforo de campo de 15 minutos (tarea 3.3).

Valores derivados a mano: hora pico por ventana móvil, PHF = V/(4·V15máx),
PCU desde la composición vehicular.
"""
import pytest

from app.field_count import process_field_count
from app.models import FieldCountRequest, MovementCounts, PcuEquivalences

LABELS_6 = ["07:00", "07:15", "07:30", "07:45", "08:00", "08:15"]
LABELS_4 = ["07:00", "07:15", "07:30", "07:45"]


def test_peak_hour_window_and_phf():
    # Totales por intervalo: 100,120,150,130,110,90.
    # Ventanas de 4: 500 / 510 / 480 -> pico = 07:15–08:15.
    # PHF = 510 / (4·150) = 0.85.
    req = FieldCountRequest(
        interval_labels=LABELS_6,
        counts={"N-T": MovementCounts(auto=[100, 120, 150, 130, 110, 90])},
    )
    res = process_field_count(req)
    assert res.peak_hour_label == "07:15–08:15"
    assert res.expanded is False
    assert res.phf == pytest.approx(0.85)
    assert res.volumes["N-T"] == pytest.approx(510.0)
    assert res.pcu_factors["N-T"] == pytest.approx(1.0)
    assert res.totals_per_interval == [100, 120, 150, 130, 110, 90]


def test_pcu_from_vehicle_composition():
    # N-T moto-dominante: 10 autos + 30 motos por intervalo
    #   mixto 40, ponderado 10·1 + 30·0.5 = 25 -> PCU = 0.62 (motos bajan).
    # E-T con pesados: 40 autos + 10 camiones
    #   mixto 50, ponderado 40 + 20 = 60 -> PCU = 1.2.
    req = FieldCountRequest(
        interval_labels=LABELS_4,
        counts={
            "N-T": MovementCounts(auto=[10] * 4, moto=[30] * 4),
            "E-T": MovementCounts(auto=[40] * 4, camion=[10] * 4),
        },
    )
    res = process_field_count(req)
    assert res.volumes["N-T"] == pytest.approx(160.0)
    assert res.pcu_factors["N-T"] == pytest.approx(0.62, abs=0.01)
    assert res.volumes["E-T"] == pytest.approx(200.0)
    assert res.pcu_factors["E-T"] == pytest.approx(1.2, abs=0.01)


def test_custom_equivalences():
    req = FieldCountRequest(
        interval_labels=LABELS_4,
        counts={"N-T": MovementCounts(auto=[10] * 4, camion=[10] * 4)},
        pcu=PcuEquivalences(camion=3.0),
    )
    res = process_field_count(req)
    # (10·1 + 10·3) / 20 = 2.0
    assert res.pcu_factors["N-T"] == pytest.approx(2.0)


def test_short_count_expands_with_warning():
    req = FieldCountRequest(
        interval_labels=["07:30", "07:45"],
        counts={"N-T": MovementCounts(auto=[30, 50])},
    )
    res = process_field_count(req)
    assert res.expanded is True
    assert res.phf is None
    assert res.volumes["N-T"] == pytest.approx(160.0)  # (30+50)·4/2
    assert any("expansión" in w for w in res.warnings)


def test_extreme_peaking_clamps_phf():
    # Totales 10,100,10,10 -> PHF = 130/(4·100) = 0.33 -> acotado a 0.70.
    req = FieldCountRequest(
        interval_labels=LABELS_4,
        counts={"N-T": MovementCounts(auto=[10, 100, 10, 10])},
    )
    res = process_field_count(req)
    assert res.phf == pytest.approx(0.70)
    assert any("se acota" in w for w in res.warnings)


def test_mismatched_interval_length_raises():
    req = FieldCountRequest(
        interval_labels=LABELS_4,
        counts={"N-T": MovementCounts(auto=[10, 20])},
    )
    with pytest.raises(ValueError):
        process_field_count(req)


def test_empty_counts_raise():
    with pytest.raises(ValueError):
        process_field_count(
            FieldCountRequest(interval_labels=LABELS_4, counts={})
        )


def test_generic_labels_get_textual_end():
    req = FieldCountRequest(
        interval_labels=["I1", "I2", "I3", "I4"],
        counts={"N-T": MovementCounts(auto=[10, 10, 10, 10])},
    )
    res = process_field_count(req)
    assert res.peak_hour_label == "I1–I4 +15 min"
