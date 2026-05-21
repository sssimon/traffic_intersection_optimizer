"""Pruebas de regresión — análisis de capacidad HCM 2010 cap. 18 (app/analysis.py).

Valores esperados derivados a mano del modelo de demora del HCM:

    d1 = 0.5 * C * (1 - g/C)^2 / (1 - min(1,X) * g/C)
    d2 = 900 * T * [(X-1) + sqrt((X-1)^2 + 8*k*I*X / (c*T))]
    d  = d1 * PF + d2
"""
from app.analysis import _los_from_delay, analyze
from app.models import LOSGrade, SignalPlan


def test_hcm_single_movement_delay(single_movement_config):
    # C = 60, g = 30  ->  c = 1800 * (30/60) = 900 veh/h
    # v = 600  ->  X = 600 / 900 = 0.667
    # d1 = 0.5*60*(0.5)^2 / (1 - 0.667*0.5) = 7.5 / 0.667 = 11.25 s
    # d2 = 900*0.25*[(X-1) + sqrt(0.12296)] = 3.90 s
    # d  = 11.25 + 3.90 = 15.1 s  ->  LOS B  (d <= 20)
    plan = SignalPlan(
        cycle_length=60.0,
        phase_green={"P1": 30.0},
        phase_yellow={"P1": 3.0},
        phase_all_red={"P1": 1.0},
        total_lost_time=4.0,
    )
    result = analyze(single_movement_config, plan)
    assert len(result.movements) == 1

    mv = result.movements[0]
    assert mv.capacity == 900.0
    assert mv.v_c_ratio == 0.667
    assert mv.avg_delay_s == 15.1
    assert mv.los == LOSGrade.B
    # Cola estimada: q_avg = (v/3600)*r / (1 - X*g/C) = 7.5 ; q_95 = 2*q_avg = 15.0
    assert mv.queue_95th_veh == 15.0

    assert result.avg_delay_s == 15.1
    assert result.overall_los == LOSGrade.B
    assert result.overall_v_c == 0.667


def test_los_thresholds():
    # Umbrales HCM semaforizado: A<=10  B<=20  C<=35  D<=55  E<=80  F>80
    assert _los_from_delay(10.0) == LOSGrade.A
    assert _los_from_delay(10.1) == LOSGrade.B
    assert _los_from_delay(20.0) == LOSGrade.B
    assert _los_from_delay(35.0) == LOSGrade.C
    assert _los_from_delay(55.0) == LOSGrade.D
    assert _los_from_delay(80.0) == LOSGrade.E
    assert _los_from_delay(80.1) == LOSGrade.F
