"""Pruebas — persistencia de corridas en SQLite (tarea 2.5).

Criterio de aceptación: guardar / cargar / comparar funciona. La base se
redirige a un archivo temporal por prueba (no toca data/runs/).
"""
import pytest

from app import storage
from app.analysis import analyze
from app.data import sample_intersection
from app.models import SaveRunRequest
from app.optimizer_delay import optimize_delay


@pytest.fixture(autouse=True)
def _tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "runs.db")


def test_save_and_list_with_consistent_summary():
    cfg = sample_intersection()
    saved = storage.save_run(SaveRunRequest(name="corrida base", config=cfg))

    expected = analyze(cfg, optimize_delay(cfg))
    assert saved.method == "delay_min"
    assert saved.avg_delay_s == pytest.approx(expected.avg_delay_s)
    assert saved.overall_los == expected.overall_los
    assert saved.intersection_name == cfg.name
    assert saved.created_at  # ISO UTC

    runs = storage.list_runs()
    assert len(runs) == 1
    assert runs[0].id == saved.id
    assert runs[0].name == "corrida base"


def test_load_round_trips_the_config():
    cfg = sample_intersection()
    saved = storage.save_run(SaveRunRequest(name="x", config=cfg))
    detail = storage.get_run(saved.id)
    assert detail is not None
    assert detail.config.name == cfg.name
    assert len(detail.config.approaches) == len(cfg.approaches)
    assert detail.config.demand == cfg.demand
    assert detail.config.phases == cfg.phases


def test_delete_removes_run():
    saved = storage.save_run(
        SaveRunRequest(name="efimera", config=sample_intersection())
    )
    assert storage.delete_run(saved.id) is True
    assert storage.get_run(saved.id) is None
    assert storage.delete_run(saved.id) is False


def test_runs_are_comparable_across_methods():
    # Misma intersección con dos métodos: la lista permite comparar
    # (Webster ciclo 120 vs mínima demora 92.5 en el caso de ejemplo).
    cfg = sample_intersection()
    storage.save_run(SaveRunRequest(name="webster", config=cfg, method="webster"))
    storage.save_run(SaveRunRequest(name="min-demora", config=cfg, method="delay_min"))

    runs = storage.list_runs()
    assert [r.name for r in runs] == ["min-demora", "webster"]  # reciente primero
    by_name = {r.name: r for r in runs}
    assert by_name["webster"].cycle_length == pytest.approx(120.0)
    assert by_name["min-demora"].cycle_length < by_name["webster"].cycle_length
    assert by_name["min-demora"].avg_delay_s < by_name["webster"].avg_delay_s


def test_get_missing_run_returns_none():
    assert storage.get_run(9999) is None
