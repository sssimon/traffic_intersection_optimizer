"""Pruebas — modo auditoría (tarea 2.4).

Garantía central: la traza usa los MISMOS núcleos que el análisis, así que
cada valor de la auditoría coincide con el del análisis (por construcción,
y verificado aquí). Criterio de aceptación: un revisor puede verificar
cualquier número contra el manual sin leer código — cada paso lleva
fórmula, sustitución numérica, valor, unidades y fuente.
"""
import pytest

from app.analysis import analyze
from app.audit import build_audit
from app.data import sample_intersection
from app.models import SaturationFactors, SignalPlan
from app.optimizer_delay import optimize_delay


def _step(audit_mov, concept_prefix):
    return next(s for s in audit_mov.steps if s.concept.startswith(concept_prefix))


def test_audit_values_match_analysis_exactly():
    cfg = sample_intersection()
    plan = optimize_delay(cfg)
    analysis = analyze(cfg, plan)
    audit = build_audit(cfg, plan)

    assert len(audit) == len(analysis.movements)
    by_id = {m.lane_group_id: m for m in analysis.movements}
    for mov in audit:
        ref = by_id[mov.lane_group_id]
        assert mov.phase_id == ref.phase_id
        assert _step(mov, "Demanda").value == pytest.approx(ref.demand, abs=0.05)
        assert _step(mov, "Capacidad").value == pytest.approx(ref.capacity, abs=0.05)
        assert _step(mov, "Grado de saturación").value == pytest.approx(
            ref.v_c_ratio, abs=0.001
        )
        assert _step(mov, "Demora de control").value == pytest.approx(
            ref.avg_delay_s, abs=0.05
        )
        assert _step(mov, "Cola percentil 95").value == pytest.approx(
            ref.queue_95th_veh, abs=0.05
        )
        # d = d1·PF + d2 cierra con sus componentes
        d1 = _step(mov, "Demora uniforme").value
        d2 = _step(mov, "Demora incremental").value
        assert d1 + d2 == pytest.approx(ref.avg_delay_s, abs=0.05)


def test_every_step_is_verifiable():
    cfg = sample_intersection()
    plan = optimize_delay(cfg)
    for mov in build_audit(cfg, plan):
        assert len(mov.steps) >= 10
        for step in mov.steps:
            assert step.formula.strip()
            assert step.substitution.strip()
            assert step.units.strip()
            assert step.source.strip()
        # Las fuentes citan el manual.
        assert any("HCM" in s.source for s in mov.steps)


def test_factor_chain_appears_in_trace():
    cfg = sample_intersection()
    lg = cfg.approaches[0].lane_groups[0]  # N-T, through 2 carriles
    lg.factors = SaturationFactors(grade_pct=4.0, cbd=True)
    plan = optimize_delay(cfg)
    audit = build_audit(cfg, plan)
    sat = _step(next(m for m in audit if m.lane_group_id == lg.id),
                "Flujo de saturación")
    assert "fg" in sat.substitution and "fa" in sat.substitution
    assert sat.value == pytest.approx(lg.saturation_flow, abs=0.05)
    # 1900·2·0.98·0.90 = 3351.6
    assert sat.value == pytest.approx(3351.6, abs=0.1)


def test_zero_capacity_movement_declares_fallback():
    cfg = sample_intersection()
    plan = optimize_delay(cfg)
    no_green = SignalPlan(
        cycle_length=plan.cycle_length,
        phase_green={**plan.phase_green, "P2": 0.0},
        phase_yellow=plan.phase_yellow,
        phase_all_red=plan.phase_all_red,
        total_lost_time=plan.total_lost_time,
    )
    audit = build_audit(cfg, no_green)
    nl = next(m for m in audit if m.lane_group_id == "N-L")  # fase P2
    d2 = _step(nl, "Demora incremental")
    assert "sin capacidad" in d2.concept
    assert "declarado" in d2.source
    q2 = _step(nl, "Cola incremental")
    assert "sin capacidad" in q2.concept
