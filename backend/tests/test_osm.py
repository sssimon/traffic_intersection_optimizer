"""Pruebas — importación de geometría desde OSM (tarea 3.1).

Usan elementos Overpass sintéticos (sin red): la lógica pura
`build_config_from_elements` es la que se valida.
"""
import pytest

from app.osm import build_config_from_elements

LAT, LON = 10.0, -70.0
D = 0.0009  # ~100 m en latitud


def _way(wid, name, nodes, coords, **tags):
    return {
        "type": "way",
        "id": wid,
        "nodes": nodes,
        "geometry": [{"lat": la, "lon": lo} for la, lo in coords],
        "tags": {"highway": "secondary", "name": name, **tags},
    }


def _crossroads():
    """Av. Bolívar N-S (doble sentido, 4 carriles) × Calle 5 W→E
    (sentido único, 2 carriles), cruzando en el nodo 2 = (LAT, LON)."""
    return [
        _way(101, "Avenida Bolívar",
             [1, 2, 3],
             [(LAT + D, LON), (LAT, LON), (LAT - D, LON)],
             lanes="4"),
        _way(102, "Calle 5",
             [4, 2, 5],
             [(LAT, LON - D), (LAT, LON), (LAT, LON + D)],
             lanes="2", oneway="yes"),
    ]


def test_crossroads_builds_three_approaches():
    cfg, warnings = build_config_from_elements(_crossroads(), LAT, LON)

    ids = {ap.id for ap in cfg.approaches}
    # N y S de la avenida; W de la calle (entra hacia el este).
    # El brazo E es solo salida y queda excluido con aviso.
    assert ids == {"N", "S", "W"}
    assert any("solo salida" in w for w in warnings)

    by_id = {ap.id: ap for ap in cfg.approaches}
    assert by_id["N"].lane_groups[0].lanes == 2   # 4 totales / 2 sentidos
    assert by_id["S"].lane_groups[0].lanes == 2
    assert by_id["W"].lane_groups[0].lanes == 2   # sentido único: todos
    assert "Avenida Bolívar" in by_id["N"].name
    assert "Calle 5" in by_id["W"].name

    assert cfg.name == "Avenida Bolívar × Calle 5"
    assert cfg.latitude == pytest.approx(LAT)
    assert cfg.longitude == pytest.approx(LON)
    # Demanda en cero para cada grupo.
    assert {d.lane_group_id for d in cfg.demand} == {"N-T", "S-T", "W-T"}
    assert all(d.volume == 0.0 for d in cfg.demand)


def test_opposite_arms_share_a_phase():
    cfg, _ = build_config_from_elements(_crossroads(), LAT, LON)
    partitions = {frozenset(ph.lane_group_ids) for ph in cfg.phases}
    assert frozenset({"N-T", "S-T"}) in partitions
    assert frozenset({"W-T"}) in partitions
    assert len(cfg.phases) == 2


def test_lanes_forward_overrides_halving():
    elements = [
        _way(101, "Av. Asimétrica",
             [1, 2, 3],
             [(LAT + D, LON), (LAT, LON), (LAT - D, LON)],
             lanes="5", **{"lanes:forward": "3", "lanes:backward": "2"}),
        _way(102, "Calle 5",
             [4, 2, 5],
             [(LAT, LON - D), (LAT, LON), (LAT, LON + D)],
             lanes="2"),
    ]
    cfg, _ = build_config_from_elements(elements, LAT, LON)
    by_id = {ap.id: ap for ap in cfg.approaches}
    # Brazo N: el tránsito entrante (N→S) va en el sentido directo de la vía
    # (nodos 1→2): lanes:forward = 3. Brazo S entra contra el sentido: 2.
    assert by_id["N"].lane_groups[0].lanes == 3
    assert by_id["S"].lane_groups[0].lanes == 2


def test_dual_carriageway_merges_same_street():
    # Dos calzadas de sentido único de la misma avenida entrando desde el
    # norte con rumbos casi iguales: se fusionan sumando carriles.
    elements = [
        _way(101, "Av. Dual",
             [1, 2],
             [(LAT + D, LON - 0.00004), (LAT, LON)],
             lanes="2", oneway="yes"),
        _way(102, "Av. Dual",
             [6, 2],
             [(LAT + D, LON + 0.00004), (LAT, LON)],
             lanes="2", oneway="yes"),
        _way(103, "Calle 5",
             [4, 2, 5],
             [(LAT, LON - D), (LAT, LON), (LAT, LON + D)],
             lanes="2"),
    ]
    cfg, warnings = build_config_from_elements(elements, LAT, LON)
    by_id = {ap.id: ap for ap in cfg.approaches}
    assert by_id["N"].lane_groups[0].lanes == 4
    assert sum(1 for ap in cfg.approaches if "Av. Dual" in ap.name) == 1
    assert any("fusionadas" in w for w in warnings)


def test_t_intersection_endpoint_node_is_detected():
    # La calle menor TERMINA en un nodo intermedio de la avenida (T).
    elements = [
        _way(101, "Avenida Bolívar",
             [1, 2, 3],
             [(LAT + D, LON), (LAT, LON), (LAT - D, LON)],
             lanes="2"),
        _way(102, "Calle Ciega",
             [4, 2],
             [(LAT, LON - D), (LAT, LON)],
             lanes="1"),
    ]
    cfg, _ = build_config_from_elements(elements, LAT, LON)
    assert {ap.id for ap in cfg.approaches} == {"N", "S", "W"}


def test_missing_lanes_assumes_one_with_warning():
    elements = [
        _way(101, "Sin Etiqueta",
             [1, 2, 3],
             [(LAT + D, LON), (LAT, LON), (LAT - D, LON)]),
        _way(102, "Calle 5",
             [4, 2],
             [(LAT, LON - D), (LAT, LON)],
             lanes="2"),
    ]
    cfg, warnings = build_config_from_elements(elements, LAT, LON)
    by_id = {ap.id: ap for ap in cfg.approaches}
    assert by_id["N"].lane_groups[0].lanes == 1
    assert any("se asumió 1" in w for w in warnings)


def test_no_shared_node_raises():
    elements = [
        _way(101, "Solitaria",
             [1, 2, 3],
             [(LAT + D, LON), (LAT, LON), (LAT - D, LON)],
             lanes="2"),
    ]
    with pytest.raises(ValueError):
        build_config_from_elements(elements, LAT, LON)


def test_picks_shared_node_closest_to_pin():
    # Dos cruces sobre la misma avenida; el pin está junto al nodo 2.
    far = 3 * D
    elements = [
        _way(101, "Avenida",
             [1, 2, 7, 9],
             [(LAT + D, LON), (LAT, LON), (LAT - far, LON), (LAT - 2 * far, LON)],
             lanes="2"),
        _way(102, "Calle A",
             [4, 2],
             [(LAT, LON - D), (LAT, LON)],
             lanes="1"),
        _way(103, "Calle B",
             [8, 7],
             [(LAT - far, LON - D), (LAT - far, LON)],
             lanes="1"),
    ]
    cfg, _ = build_config_from_elements(elements, LAT, LON)
    assert cfg.latitude == pytest.approx(LAT)
    assert "Calle A" in cfg.name or any("Calle A" in ap.name for ap in cfg.approaches)
    assert not any("Calle B" in ap.name for ap in cfg.approaches)
