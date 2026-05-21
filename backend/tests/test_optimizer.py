"""Pruebas de regresión — optimizador Webster (app/optimizer.py).

Los valores esperados se derivan a mano de la fórmula de Webster (1958):

    Co = (1.5 * L + 5) / (1 - Y)

Si alguien altera una constante de la fórmula (el 1.5 o el 5), o el tiempo
perdido por fase, estas pruebas fallan: esa es la red de seguridad.
"""
from app.optimizer import optimize


def test_webster_cycle_length(make_two_phase):
    # Y = 2 * (630 / 1800) = 0.70
    # L = 2 fases * (yellow 3 + all_red 1) = 8 s
    # Co = (1.5 * 8 + 5) / (1 - 0.70) = 17 / 0.30 = 56.67 s
    plan = optimize(make_two_phase(630.0))
    assert plan.total_lost_time == 8.0
    assert plan.cycle_length == 56.7


def test_webster_green_split(make_two_phase):
    # Verde efectivo total = Co - L = 56.67 - 8 = 48.67 s
    # Cada fase recibe yi/Y = 0.35/0.70 = 0.5 -> 24.33 s
    plan = optimize(make_two_phase(630.0))
    assert plan.phase_green["P1"] == 24.3
    assert plan.phase_green["P2"] == 24.3


def test_oversaturation_uses_max_cycle(make_two_phase):
    # Y = 2 * (900 / 1800) = 1.0 >= 0.95 -> sobre-saturada -> ciclo maximo
    plan = optimize(make_two_phase(900.0))
    assert plan.cycle_length == 120.0
    assert any("sobre-saturada" in note for note in plan.notes)


def test_cycle_clamped_to_minimum(make_two_phase):
    # Y = 2 * (90 / 1800) = 0.10 -> Co = 17 / 0.90 = 18.9 s -> acotado a 40 s
    plan = optimize(make_two_phase(90.0))
    assert plan.cycle_length == 40.0
