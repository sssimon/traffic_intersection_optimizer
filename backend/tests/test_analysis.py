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
    # Back of queue por carril (HCM 2000 ap. G, 1 carril, T=0.25, I=1):
    #   Q1 = (600/3600)·(60-30) / (1 - (2/3)·0.5) = 5/0.6667 = 7.5 veh
    #   kB = 0.12·(1800·30/3600)^0.7 = 0.12·15^0.7 = 0.7988
    #   Q2 = 0.25·900·0.25·[(X-1) + √((X-1)² + 8·kB·X/225)]
    #      = 56.25·(-0.3333 + √(0.1111 + 0.01893)) = 1.53 veh
    #   Q  = 7.5 + 1.53 = 9.03  -> 9.0
    #   Q95 = (1.6 + e^(-9.03/5))·9.03 = 1.7642·9.03 = 15.9 veh
    assert mv.back_of_queue_avg_veh == 9.0
    assert mv.queue_95th_veh == 15.9

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


def test_back_of_queue_oversaturated(single_movement_config):
    # Con X > 1 el término incremental Q2 domina y la cola del periodo es
    # finita y mayor que la del caso no saturado. A mano (v=1200, X=1.333):
    #   Q1 = (1200/3600)·30 / (1 - 1·0.5) = 20
    #   Q2 = 56.25·(0.3333 + √(0.1111 + 8·0.7988·1.3333/225)) = 40.5
    #   Q ≈ 60.5 ; fB95 ≈ 1.6 (e^(-12) ≈ 0)  ->  Q95 ≈ 96.7
    plan = SignalPlan(
        cycle_length=60.0,
        phase_green={"P1": 30.0},
        phase_yellow={"P1": 3.0},
        phase_all_red={"P1": 1.0},
        total_lost_time=4.0,
    )
    base = analyze(single_movement_config, plan).movements[0]

    over_cfg = single_movement_config.model_copy(deep=True)
    over_cfg.demand[0].volume = 1200.0
    over = analyze(over_cfg, plan).movements[0]

    assert over.v_c_ratio == 1.333
    assert over.back_of_queue_avg_veh == 60.5
    assert over.queue_95th_veh > over.back_of_queue_avg_veh
    assert over.queue_95th_veh > base.queue_95th_veh


def test_zero_capacity_movement_is_los_f(single_movement_config):
    # Una fase sin verde -> capacidad 0 -> demora de referencia
    # (ZERO_CAPACITY_DELAY) -> el movimiento cae en LOS F.
    plan = SignalPlan(
        cycle_length=60.0,
        phase_green={"P1": 0.0},
        phase_yellow={"P1": 3.0},
        phase_all_red={"P1": 1.0},
        total_lost_time=4.0,
    )
    result = analyze(single_movement_config, plan)
    mv = result.movements[0]
    assert mv.capacity == 0.0
    assert mv.los == LOSGrade.F
