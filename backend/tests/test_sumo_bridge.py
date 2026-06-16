"""Pruebas — puente SUMO (tarea 4.2, F4).

La generación de XML y la topología son puras y se prueban sin SUMO. La
prueba end-to-end se salta si SUMO no está instalado (degradación elegante);
donde sí está, valida el criterio de aceptación: comparación automática
analítico-vs-microsimulado en el caso de ejemplo.
"""
import time

import pytest

from app.data import sample_intersection
from app.models import SumoExportRequest
from app.optimizer_delay import optimize_delay
from app.sumo_bridge import (
    build_all,
    build_tll_xml,
    is_sumo_available,
    parse_teleports,
    parse_tripinfo,
    prepare_model,
    process_sumo_export,
)


def test_bearings_and_destinations_from_cardinals():
    cfg = sample_intersection()
    model = prepare_model(cfg, driving_side="right")
    assert model.bearings == {"N": 0.0, "S": 180.0, "E": 90.0, "W": 270.0}
    # Sur que circula hacia el centro: directo→S, izquierda→E, derecha→W.
    assert model.dests["N-T"] == "S"
    assert model.dests["N-L"] == "E"
    assert model.dests["N-R"] == "W"
    # Desde el Este (circula hacia el oeste): directo→W, izquierda→S.
    assert model.dests["E-T"] == "W"
    assert model.dests["E-L"] == "S"


def test_left_hand_driving_swaps_turns():
    cfg = sample_intersection()
    right = prepare_model(cfg, "right")
    left = prepare_model(cfg, "left")
    assert right.dests["N-L"] == "E" and left.dests["N-L"] == "W"
    assert right.dests["N-R"] == "W" and left.dests["N-R"] == "E"


def test_connections_contiguous_and_cover_all_lanes():
    cfg = sample_intersection()
    model = prepare_model(cfg)
    # link_index 0..K-1 sin huecos.
    assert [c.link_index for c in model.conns] == list(range(len(model.conns)))
    # Una conexión por carril de cada grupo con destino resuelto.
    expected = sum(
        lg.lanes
        for ap in cfg.approaches
        for lg in ap.lane_groups
        if model.dests[lg.id] is not None
    )
    assert len(model.conns) == expected
    # in_N tiene 4 carriles (T2 + L1 + R1); fromLane en rango válido.
    assert model.in_lanes["N"] == 4
    assert all(0 <= c.from_lane < model.in_lanes[c.from_edge[3:]] for c in model.conns)


def test_tll_state_length_matches_links_and_cycle():
    cfg = sample_intersection()
    plan = optimize_delay(cfg)
    model = prepare_model(cfg)
    tll = build_tll_xml(cfg, plan, model)
    import xml.etree.ElementTree as ET
    root = ET.fromstring(tll)
    phases = root.find("tlLogic").findall("phase")
    k = len(model.conns)
    assert phases, "debe haber fases"
    for ph in phases:
        assert len(ph.get("state")) == k  # un carácter por linkIndex
    total = sum(float(ph.get("duration")) for ph in phases)
    assert total == pytest.approx(plan.cycle_length, abs=0.5)
    # Hay verde (G) y amarillo (y) en el programa.
    states = "".join(ph.get("state") for ph in phases)
    assert "G" in states and "y" in states


def test_build_all_emits_six_files():
    cfg = sample_intersection()
    plan = optimize_delay(cfg)
    model = prepare_model(cfg)
    files = build_all(cfg, plan, model, end_s=720)
    assert set(files) == {
        "nodes.nod.xml", "edges.edg.xml", "connections.con.xml",
        "tls.tll.xml", "routes.rou.xml", "interseccion.sumocfg",
    }
    assert 'net-file value="net.net.xml"' in files["interseccion.sumocfg"]
    # Un flujo por movimiento con demanda; vehsPerHour presente.
    assert files["routes.rou.xml"].count("<flow ") == 10
    assert 'vehsPerHour=' in files["routes.rou.xml"]


def test_parse_tripinfo_filters_warmup():
    xml = (
        '<tripinfos>'
        '<tripinfo id="a" depart="10.0" timeLoss="5.0" waitingTime="2.0"/>'
        '<tripinfo id="b" depart="200.0" timeLoss="20.0" waitingTime="8.0"/>'
        '<tripinfo id="c" depart="300.0" timeLoss="40.0" waitingTime="12.0"/>'
        '</tripinfos>'
    )
    n, delay, wait = parse_tripinfo(xml, warmup_s=120.0)
    assert n == 2                       # 'a' descartado por calentamiento
    assert delay == pytest.approx(30.0)  # (20 + 40) / 2
    assert wait == pytest.approx(10.0)


def test_parse_teleports():
    xml = '<statistics><teleports total="7" jam="7"/></statistics>'
    assert parse_teleports(xml) == 7
    assert parse_teleports("<statistics/>") == 0


def test_no_phases_raises():
    cfg = sample_intersection()
    cfg.phases = []
    with pytest.raises(ValueError):
        process_sumo_export(SumoExportRequest(config=cfg))


def test_export_without_running_returns_files():
    cfg = sample_intersection()
    res = process_sumo_export(SumoExportRequest(config=cfg, run_microsim=False))
    assert len(res.files) == 6
    assert res.analytic.avg_delay_s > 0
    assert res.microsim is None  # no se corrió


@pytest.mark.skipif(not is_sumo_available(), reason="SUMO no instalado")
def test_end_to_end_compares_analytic_vs_microsim():
    """Criterio de aceptación: comparación automática en el caso de ejemplo.

    Además valida el motor: dos métodos independientes (HCM analítico y
    microsimulación SUMO) deben coincidir a grandes rasgos. Una divergencia
    enorme delataría un modelo mal armado (p. ej. enlaces del semáforo
    desalineados, el bug que motivó la doble pasada de netconvert)."""
    cfg = sample_intersection()
    t0 = time.perf_counter()
    res = process_sumo_export(SumoExportRequest(
        config=cfg, replications=3, warmup_s=60, duration_s=300,
    ))
    elapsed = time.perf_counter() - t0
    assert res.sumo_available is True
    assert res.microsim is not None, f"microsim None; avisos={res.warnings}"
    assert res.microsim.measured_vehicles > 0
    assert res.microsim.delay_mean_s > 0
    assert res.microsim.overall_los in {"A", "B", "C", "D", "E", "F"}
    assert res.delta_delay_s is not None
    assert res.analytic.avg_delay_s > 20  # el ejemplo es congestionado
    # Concordancia: ambos métodos dentro de ~30 s (el bug de enlaces daba +200).
    assert abs(res.delta_delay_s) < 30, (
        f"analítico {res.analytic.avg_delay_s}s vs microsim "
        f"{res.microsim.delay_mean_s}s divergen demasiado"
    )
    # El .tll.xml exportado es el que realmente se corrió (alineado al net).
    tll = next(f for f in res.files if f.name == "tls.tll.xml")
    assert "<tlLogic" in tll.content
    assert elapsed < 90.0
