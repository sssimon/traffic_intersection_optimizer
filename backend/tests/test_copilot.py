"""Pruebas — copiloto LLM (tarea 5.2, F5).

Todo se prueba SIN red: disponibilidad por env var, construcción de prompts y
parseo/validación de la respuesta. La llamada HTTP (`_call_anthropic`) no se
ejercita; los orquestadores se detienen antes si no hay clave.
"""
import json

import pytest

from app.analysis import analyze
from app.copilot import (
    _extract_json,
    build_edit_prompt,
    build_explain_prompt,
    copilot_status,
    edit_config,
    explain_analysis,
    is_copilot_available,
    parse_edit_response,
)
from app.data import sample_intersection
from app.models import CopilotEditRequest, CopilotExplainRequest
from app.optimizer_delay import optimize_delay

KEY = "ANTHROPIC_API_KEY"


def test_availability_follows_env(monkeypatch):
    monkeypatch.delenv(KEY, raising=False)
    assert is_copilot_available() is False
    assert copilot_status().available is False
    assert "ANTHROPIC_API_KEY" in copilot_status().note

    monkeypatch.setenv(KEY, "sk-test")
    assert is_copilot_available() is True
    st = copilot_status()
    assert st.available is True and st.model


def test_explain_prompt_grounds_in_numbers():
    cfg = sample_intersection()
    an = analyze(cfg, optimize_delay(cfg))
    system, user = build_explain_prompt(cfg, an, optimize_delay(cfg), "¿Por qué hay demora?")
    assert "ingeniero de tránsito" in system
    assert "no inventes" in system.lower()
    assert "¿Por qué hay demora?" in user
    assert cfg.name in user
    # Lleva los números reales del motor (LOS global y algún grupo).
    assert f"LOS {an.overall_los.value}" in user
    assert "N-T" in user


def test_edit_prompt_carries_config_and_rules():
    cfg = sample_intersection()
    system, user = build_edit_prompt(cfg, "agrega una fase peatonal exclusiva")
    assert "JSON" in system and "movement" in system
    assert "agrega una fase peatonal exclusiva" in user
    assert cfg.name in user
    assert '"summary"' in user


def test_extract_json_variants():
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('```json\n{"a": 2}\n```') == {"a": 2}
    assert _extract_json('Claro:\n{"a": 3}\nlisto') == {"a": 3}
    with pytest.raises(RuntimeError):
        _extract_json("sin json aquí")


def _edit_response(cfg, summary="Cambié algo."):
    return json.dumps({"config": cfg.model_dump(mode="json"), "summary": summary})


def test_parse_edit_response_valid():
    cfg = sample_intersection()
    new, summary, warnings = parse_edit_response(_edit_response(cfg, "Subí la demanda."))
    assert new.name == cfg.name
    assert summary == "Subí la demanda."
    assert warnings == []


def test_parse_edit_response_fenced():
    cfg = sample_intersection()
    raw = "Aquí tienes:\n```json\n" + _edit_response(cfg) + "\n```"
    new, _, _ = parse_edit_response(raw)
    assert len(new.approaches) == len(cfg.approaches)


def test_parse_edit_response_missing_config_raises():
    with pytest.raises(RuntimeError):
        parse_edit_response('{"summary": "no hay config"}')


def test_parse_edit_response_invalid_config_raises():
    cfg = sample_intersection()
    d = cfg.model_dump(mode="json")
    d["approaches"][0]["lane_groups"][0]["movement"] = "diagonal"  # inválido
    raw = json.dumps({"config": d, "summary": "x"})
    with pytest.raises(RuntimeError):
        parse_edit_response(raw)


def test_sanity_warns_phase_referencing_missing_group():
    cfg = sample_intersection()
    d = cfg.model_dump(mode="json")
    d["phases"].append({"id": "PX", "name": "fantasma", "lane_group_ids": ["ZZZ"]})
    _, _, warnings = parse_edit_response(json.dumps({"config": d, "summary": "x"}))
    assert any("ZZZ" in w for w in warnings)


def test_sanity_allows_pedestrian_phase_id():
    cfg = sample_intersection()
    d = cfg.model_dump(mode="json")
    d["phases"].append({"id": "PP", "name": "peatonal", "lane_group_ids": ["PED"]})
    _, _, warnings = parse_edit_response(json.dumps({"config": d, "summary": "x"}))
    assert not any("PED" in w for w in warnings)


def test_orchestrators_require_key(monkeypatch):
    monkeypatch.delenv(KEY, raising=False)
    cfg = sample_intersection()
    with pytest.raises(RuntimeError):
        explain_analysis(CopilotExplainRequest(config=cfg, question="hola"))
    with pytest.raises(RuntimeError):
        edit_config(CopilotEditRequest(config=cfg, instruction="cambia algo"))
