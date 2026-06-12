"""Pruebas — Monte Carlo de incertidumbre del aforo (tarea 2.3).

Criterio de aceptación: 1 000 muestras en < 2 s y salida con P(LOS) y banda.
"""
import time

import pytest

from app.analysis import analyze
from app.data import sample_intersection
from app.models import UncertaintyRequest
from app.optimizer_delay import optimize_delay
from app.uncertainty import run_uncertainty


def test_thousand_samples_under_two_seconds():
    t0 = time.perf_counter()
    res = run_uncertainty(UncertaintyRequest(config=sample_intersection(),
                                             samples=1000))
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0  # criterio de aceptación 2.3
    assert res.samples == 1000


def test_los_probabilities_sum_to_one():
    res = run_uncertainty(UncertaintyRequest(config=sample_intersection()))
    assert sum(res.los_probability.values()) == pytest.approx(1.0, abs=1e-6)
    assert set(res.los_probability) == set("ABCDEF")
    assert 0.0 <= res.prob_oversaturated <= 1.0


def test_zero_cv_collapses_to_base():
    # Sin incertidumbre, la distribución degenera en la estimación puntual.
    res = run_uncertainty(UncertaintyRequest(config=sample_intersection(),
                                             volume_cv=0.0, samples=200))
    assert res.delay_p05_s == res.delay_p50_s == res.delay_p95_s
    assert res.delay_p50_s == pytest.approx(res.base_delay_s, abs=0.1)
    assert max(res.los_probability.values()) == pytest.approx(1.0)


def test_base_delay_matches_deterministic_analysis():
    cfg = sample_intersection()
    res = run_uncertainty(UncertaintyRequest(config=cfg, samples=200))
    deterministic = analyze(cfg, optimize_delay(cfg))
    assert res.base_delay_s == pytest.approx(deterministic.avg_delay_s, abs=0.2)


def test_wider_cv_widens_the_band():
    cfg = sample_intersection()
    narrow = run_uncertainty(UncertaintyRequest(config=cfg, volume_cv=0.05))
    wide = run_uncertainty(UncertaintyRequest(config=cfg, volume_cv=0.15))
    assert (wide.delay_p95_s - wide.delay_p05_s) > (
        narrow.delay_p95_s - narrow.delay_p05_s
    )


def test_sample_case_shows_meaningful_uncertainty():
    # El caso de ejemplo opera al borde D/E con X≈1.04: la incertidumbre
    # del aforo debe traducirse en probabilidad repartida (no una letra
    # única) y sobresaturación probable.
    res = run_uncertainty(UncertaintyRequest(config=sample_intersection(),
                                             volume_cv=0.10))
    assert max(res.los_probability.values()) < 1.0
    assert res.prob_oversaturated > 0.3
    # P(LOS E o peor) es relevante en este caso.
    p_e_or_worse = res.los_probability["E"] + res.los_probability["F"]
    assert p_e_or_worse > 0.05


def test_tornado_sorted_and_heavy_movements_dominate():
    res = run_uncertainty(UncertaintyRequest(config=sample_intersection()))
    corrs = [abs(s.correlation) for s in res.sensitivity]
    assert corrs == sorted(corrs, reverse=True)
    assert corrs[0] > 0.1
    # Los movimientos pesados del eje E-W dominan la sensibilidad.
    top3 = {s.lane_group_id for s in res.sensitivity[:3]}
    assert top3 & {"E-T", "W-T"}


def test_reproducible_with_same_seed():
    cfg = sample_intersection()
    a = run_uncertainty(UncertaintyRequest(config=cfg, seed=7))
    b = run_uncertainty(UncertaintyRequest(config=cfg, seed=7))
    assert a.delay_p50_s == b.delay_p50_s
    assert a.los_probability == b.los_probability


def test_movement_cv_override():
    cfg = sample_intersection()
    res = run_uncertainty(UncertaintyRequest(
        config=cfg, volume_cv=0.05, movement_cv={"E-T": 0.3}))
    et = next(s for s in res.sensitivity if s.lane_group_id == "E-T")
    assert et.cv == 0.3
    # Con 6× más incertidumbre, E-T encabeza el tornado.
    assert res.sensitivity[0].lane_group_id == "E-T"
