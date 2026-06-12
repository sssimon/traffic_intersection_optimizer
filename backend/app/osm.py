"""Importación de geometría desde OpenStreetMap (tarea 3.1).

Desde el pin del mapa se consulta Overpass y se construye una configuración
inicial de la intersección: accesos con rumbo cardinal, nombre de calle,
número de carriles aproximado y sentidos; fases emparejando brazos opuestos;
demanda en cero lista para cargar el aforo.

Método:
1. Se piden las vías vehiculares en un radio alrededor del pin (Overpass,
   `out geom`: ids de nodos + coordenadas).
2. El cruce es el nodo compartido por 2+ vías más cercano al pin (las
   intersecciones en T también comparten el nodo del extremo).
3. Cada vía incidente aporta brazos. Un brazo es ACCESO si el tránsito puede
   entrar al cruce por él: las calles de doble sentido siempre; las de
   sentido único solo si apuntan hacia el cruce (los brazos de solo salida
   se excluyen con aviso).
4. Carriles por acceso: `lanes:forward`/`lanes:backward` si existen; si no,
   `lanes` (entero) en sentido único o `lanes`÷2 en doble sentido; sin
   etiqueta se asume 1 con aviso.
5. Calzadas separadas (dual carriageway): brazos entrantes con el mismo
   nombre y rumbo similar (<30°) se fusionan sumando carriles.

Lo que NO hace (declarado): no interpreta `turn:lanes` ni genera grupos de
giro — produce un grupo directo por acceso; los giros, la demanda y el
refinamiento de fases son del usuario.

La lógica es pura (`build_config_from_elements`) y se prueba sin red; el
fetch (`fetch_overpass`) usa urllib de la librería estándar.
"""
from __future__ import annotations

import json
import math
import urllib.request
from typing import List, Tuple

from .models import (
    Approach,
    Demand,
    IntersectionConfig,
    LaneGroup,
    MovementType,
    Phase,
)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "Traffic-Intersection-Optimizer/0.1 (herramienta academica)"

_HIGHWAYS = (
    "motorway|trunk|primary|secondary|tertiary|unclassified|residential|"
    "living_street|motorway_link|trunk_link|primary_link|secondary_link|"
    "tertiary_link"
)

_CARDINALS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
_CARDINAL_NAMES = {
    "N": "Norte", "NE": "Noreste", "E": "Este", "SE": "Sureste",
    "S": "Sur", "SW": "Suroeste", "W": "Oeste", "NW": "Noroeste",
}
MERGE_BEARING_DEG = 30.0


def fetch_overpass(lat: float, lon: float, radius_m: int) -> list[dict]:
    """Vías vehiculares alrededor del punto (puede lanzar URLError/timeout)."""
    query = (
        f"[out:json][timeout:10];"
        f'way(around:{radius_m},{lat},{lon})["highway"~"^({_HIGHWAYS})$"];'
        f"out geom;"
    )
    req = urllib.request.Request(
        OVERPASS_URL,
        data=query.encode("utf-8"),
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("elements", [])


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dy = (lat2 - lat1) * 110_540.0
    dx = (lon2 - lon1) * 111_320.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _cardinal(bearing: float) -> str:
    return _CARDINALS[int(((bearing + 22.5) % 360.0) // 45.0)]


def _parse_lanes(tags: dict, key: str) -> int | None:
    raw = tags.get(key)
    if raw is None:
        return None
    try:
        return max(1, int(float(str(raw).split(";")[0])))
    except ValueError:
        return None


def _way_label(tags: dict) -> str:
    return tags.get("name") or tags.get("ref") or f"vía {tags.get('highway', '?')}"


def build_config_from_elements(
    elements: list[dict], lat: float, lon: float
) -> Tuple[IntersectionConfig, List[str]]:
    """Construye la configuración inicial; lanza ValueError si no hay cruce."""
    warnings: List[str] = []
    ways = [
        e for e in elements
        if e.get("type") == "way" and e.get("nodes") and e.get("geometry")
    ]
    if not ways:
        raise ValueError(
            "No se encontraron vías vehiculares cerca del punto. "
            "Acerca el pin a la intersección."
        )

    # Nodo del cruce: compartido por 2+ vías, el más cercano al pin.
    node_ways: dict[int, set[int]] = {}
    node_coord: dict[int, tuple[float, float]] = {}
    for w in ways:
        for nid, geo in zip(w["nodes"], w["geometry"]):
            node_ways.setdefault(nid, set()).add(w["id"])
            node_coord[nid] = (geo["lat"], geo["lon"])

    shared = [nid for nid, ws in node_ways.items() if len(ws) >= 2]
    if not shared:
        raise ValueError(
            "No se encontró un cruce (nodo compartido entre vías) en el radio. "
            "Acerca el pin al centro de la intersección."
        )
    center = min(
        shared, key=lambda nid: _distance_m(lat, lon, *node_coord[nid])
    )
    c_lat, c_lon = node_coord[center]
    dist = _distance_m(lat, lon, c_lat, c_lon)
    if dist > 40.0:
        warnings.append(
            f"El cruce detectado está a {dist:.0f} m del pin: verifica que "
            "sea el correcto."
        )

    # Brazos incidentes al nodo del cruce.
    arms: List[dict] = []  # {bearing, name, lanes, lanes_assumed}
    for w in ways:
        tags = w.get("tags", {})
        nodes = w["nodes"]
        geometry = w["geometry"]
        oneway_tag = str(tags.get("oneway", "no")).lower()
        if tags.get("junction") == "roundabout":
            oneway_tag = "yes"
        oneway_fwd = oneway_tag in ("yes", "true", "1")
        oneway_rev = oneway_tag == "-1"

        for i, nid in enumerate(nodes):
            if nid != center:
                continue
            for j in (i - 1, i + 1):
                if j < 0 or j >= len(nodes):
                    continue
                # Tránsito entrante: vecino -> cruce. En el orden de la vía,
                # j < i fluye en sentido directo; j > i, en sentido inverso.
                incoming_forward = j < i
                if oneway_fwd and not incoming_forward:
                    warnings.append(
                        f"Brazo de «{_way_label(tags)}»: solo salida "
                        "(sentido único); no es un acceso."
                    )
                    continue
                if oneway_rev and incoming_forward:
                    warnings.append(
                        f"Brazo de «{_way_label(tags)}»: solo salida "
                        "(sentido único); no es un acceso."
                    )
                    continue

                lanes_total = _parse_lanes(tags, "lanes")
                directional = _parse_lanes(
                    tags, "lanes:forward" if incoming_forward else "lanes:backward"
                )
                if oneway_fwd or oneway_rev:
                    lanes = lanes_total or 1
                    assumed = lanes_total is None
                elif directional is not None:
                    lanes = directional
                    assumed = False
                elif lanes_total is not None:
                    lanes = max(1, lanes_total // 2)
                    assumed = False
                else:
                    lanes = 1
                    assumed = True

                geo = geometry[j]
                arms.append({
                    "bearing": _bearing_deg(c_lat, c_lon, geo["lat"], geo["lon"]),
                    "name": _way_label(tags),
                    "lanes": min(8, lanes),
                    "lanes_assumed": assumed,
                })

    if not arms:
        raise ValueError(
            "El cruce detectado no tiene brazos de entrada (¿todas las vías "
            "son de salida?)."
        )

    # Fusión de calzadas separadas: mismo nombre y rumbo similar.
    merged: List[dict] = []
    for arm in sorted(arms, key=lambda a: a["bearing"]):
        target = next(
            (
                m for m in merged
                if m["name"] == arm["name"]
                and min(
                    abs(m["bearing"] - arm["bearing"]),
                    360 - abs(m["bearing"] - arm["bearing"]),
                ) < MERGE_BEARING_DEG
            ),
            None,
        )
        if target is not None:
            target["lanes"] = min(8, target["lanes"] + arm["lanes"])
            target["lanes_assumed"] = target["lanes_assumed"] and arm["lanes_assumed"]
            warnings.append(
                f"Calzadas separadas de «{arm['name']}» fusionadas en un "
                "acceso (carriles sumados)."
            )
        else:
            merged.append(dict(arm))

    # Accesos con id cardinal único.
    used_ids: set[str] = set()
    approaches: List[Approach] = []
    demand: List[Demand] = []
    for arm in merged:
        base = _cardinal(arm["bearing"])
        ap_id = base
        k = 2
        while ap_id in used_ids:
            ap_id = f"{base}{k}"
            k += 1
        used_ids.add(ap_id)
        if arm["lanes_assumed"]:
            warnings.append(
                f"Acceso {ap_id} («{arm['name']}»): sin etiqueta de carriles "
                "en OSM; se asumió 1. Verifícalo."
            )
        approaches.append(Approach(
            id=ap_id,
            name=f"{_CARDINAL_NAMES.get(base, base)} — {arm['name']}",
            lane_groups=[LaneGroup(
                id=f"{ap_id}-T",
                movement=MovementType.THROUGH,
                lanes=arm["lanes"],
            )],
        ))
        demand.append(Demand(lane_group_id=f"{ap_id}-T", volume=0.0))
    arm_bearing = {ap.id: arm["bearing"] for ap, arm in zip(approaches, merged)}

    # Fases: brazos opuestos (Δ rumbo ≈ 180° ± 45°) comparten fase.
    phases: List[Phase] = []
    unpaired = [ap.id for ap in approaches]
    while unpaired:
        a = unpaired.pop(0)
        partner = None
        for b in unpaired:
            diff = abs(arm_bearing[a] - arm_bearing[b]) % 360.0
            diff = min(diff, 360.0 - diff)
            if abs(diff - 180.0) <= 45.0:
                partner = b
                break
        ids = [f"{a}-T"]
        name = f"{a} directo"
        if partner is not None:
            unpaired.remove(partner)
            ids.append(f"{partner}-T")
            name = f"{a}-{partner} directo"
        phases.append(Phase(
            id=f"P{len(phases) + 1}",
            name=name,
            lane_group_ids=ids,
        ))

    street_names = list(dict.fromkeys(arm["name"] for arm in merged))
    if len(street_names) >= 2:
        cfg_name = f"{street_names[0]} × {street_names[1]}"
    elif street_names:
        cfg_name = f"Cruce de {street_names[0]}"
    else:
        cfg_name = "Intersección OSM"

    warnings.append(
        "Importado de OSM: un grupo directo por acceso. Agrega grupos de "
        "giro, revisa fases/carriles y carga la demanda del aforo."
    )

    cfg = IntersectionConfig(
        name=cfg_name,
        approaches=approaches,
        phases=phases,
        demand=demand,
        peak_hour_factor=0.92,
        latitude=c_lat,
        longitude=c_lon,
    )
    return cfg, warnings
