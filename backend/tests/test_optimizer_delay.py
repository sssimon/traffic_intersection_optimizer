"""Pruebas — optimizador por minimización directa de demora HCM (M4).

Criterio de aceptación (plan estratégico, tarea 1.5): en el caso de ejemplo
congestionado el plan de mínima demora produce ciclo <= Webster y demora
media <= Webster. Además: factibilidad (cotas de verde, consistencia del
ciclo) y sanidad (simetría con demanda balanceada, sin demanda no revienta).
"""
from app.analysis import analyze
from app.data import sample_intersection
from app.optimizer import optimize
from app.optimizer_delay import optimize_delay


def test_beats_webster_on_congested_sample():
    cfg = sample_intersection()
    plan_w = optimize(cfg)
    plan_d = optimize_delay(cfg)
    result_w = analyze(cfg, plan_w)
    result_d = analyze(cfg, plan_d)

    assert plan_d.cycle_length <= plan_w.cycle_length
    assert result_d.avg_delay_s <= result_w.avg_delay_s


def test_respects_bounds_and_cycle_consistency():
    cfg = sample_intersection()
    plan = optimize_delay(cfg)

    L = sum(ph.lost_time for ph in cfg.phases)
    assert 40.0 <= plan.cycle_length <= 120.0
    # Σ verdes efectivos = C - L (tolerancia por redondeo a 0.1 s por fase)
    assert abs(sum(plan.phase_green.values()) + L - plan.cycle_length) <= 0.5
    for ph in cfg.phases:
        g = plan.phase_green[ph.id]
        assert ph.min_green - 1e-6 <= g <= ph.max_green + 1e-6
        assert plan.phase_yellow[ph.id] == ph.yellow
        assert plan.phase_all_red[ph.id] == ph.all_red


def test_balanced_two_phase_split_is_symmetric(make_two_phase):
    # Demanda idéntica en ambas fases -> el reparto óptimo es simétrico.
    cfg = make_two_phase(630.0)
    plan = optimize_delay(cfg)
    greens = list(plan.phase_green.values())
    assert abs(greens[0] - greens[1]) <= 1.0


def test_not_worse_than_webster_on_balanced_case(make_two_phase):
    # También en régimen no saturado (Y = 0.70) el plan de mínima demora
    # no puede ser peor que Webster bajo el mismo modelo de evaluación.
    # Tolerancia 0.15 s por los redondeos a 0.1 de demora y verdes.
    cfg = make_two_phase(630.0)
    delay_w = analyze(cfg, optimize(cfg)).avg_delay_s
    delay_d = analyze(cfg, optimize_delay(cfg)).avg_delay_s
    assert delay_d <= delay_w + 0.15


def test_zero_demand_does_not_crash(make_two_phase):
    cfg = make_two_phase(0.0)
    plan = optimize_delay(cfg)
    assert plan.cycle_length >= 40.0
    assert any("demanda" in n.lower() for n in plan.notes)
