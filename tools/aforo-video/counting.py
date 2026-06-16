"""Lógica de conteo OD del aforo por video (tarea 3.2) — pura y testeable.

Separación deliberada: este módulo no conoce YOLO ni OpenCV. Recibe
trayectorias (track_id, clase, lista de centros (x, y)) y zonas con
polígonos, y produce la matriz origen-destino por clase vehicular:

- la zona de ORIGEN es la primera que toca la trayectoria y la de DESTINO
  la última; los tracks que no tocan dos zonas distintas, demasiado cortos
  o casi inmóviles (ruido, vehículos estacionados) se descartan y se
  reportan aparte;
- la expansión a veh/h es ×(3600 / duración observada) — con clips cortos
  es solo una MUESTRA, no un aforo (el criterio formal pide ≥ 15 min);
- el PCU por movimiento usa las mismas equivalencias declaradas del módulo
  de aforo manual del backend (auto 1.0, moto 0.5, bus 2.0, camión 2.0).
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

Point = Tuple[float, float]

CLASSES = ("auto", "moto", "bus", "camion")
PCU_EQ = {"auto": 1.0, "moto": 0.5, "bus": 2.0, "camion": 2.0}


def stitch_tracks(
    segments: List[dict],
    fps: float,
    max_gap_s: float = 3.0,
    max_dist_px: float = 100.0,
) -> List[dict]:
    """Cose fragmentos de track (el seguimiento pierde el ID a mitad del
    cruce, sobre todo de noche): el viaje completo queda partido en
    segmentos que nunca tocan dos zonas.

    Cada segmento: {"cls_votes": {clase: n}, "points": [(frame, x, y), …]}.
    Regla: el segmento B continúa al A si empieza hasta `max_gap_s` después
    de que A termina y su primer punto cae a ≤ `max_dist_px` de la posición
    de A EXTRAPOLADA por su velocidad final (los vehículos siguen moviéndose
    durante el hueco). Se permite coser clases distintas (la clasificación
    parpadea de noche); la clase final es la mayoritaria.
    """
    max_gap_frames = max_gap_s * fps
    chains: List[dict] = []
    for seg in sorted(segments, key=lambda s: s["points"][0][0]):
        f0, x0, y0 = seg["points"][0]
        best = None
        best_dist = max_dist_px
        for chain in chains:
            fe, xe, ye = chain["points"][-1]
            gap = f0 - fe
            if gap <= 0 or gap > max_gap_frames:
                continue
            # Velocidad final del chain (últimos ≤5 puntos) para extrapolar.
            tail = chain["points"][-5:]
            df = tail[-1][0] - tail[0][0]
            if df > 0:
                vx = (tail[-1][1] - tail[0][1]) / df
                vy = (tail[-1][2] - tail[0][2]) / df
            else:
                vx = vy = 0.0
            px = xe + vx * gap
            py = ye + vy * gap
            dist = ((px - x0) ** 2 + (py - y0) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best = chain
        if best is not None:
            best["points"].extend(seg["points"])
            for cls_name, votes in seg["cls_votes"].items():
                best["cls_votes"][cls_name] = (
                    best["cls_votes"].get(cls_name, 0) + votes
                )
        else:
            chains.append({
                "cls_votes": dict(seg["cls_votes"]),
                "points": list(seg["points"]),
            })
    return chains


def point_in_polygon(pt: Point, polygon: Sequence[Point]) -> bool:
    """Ray casting clásico (frontera no garantizada — irrelevante aquí)."""
    x, y = pt
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


class OdCounter:
    """Acumula trayectorias y produce la matriz OD por clase."""

    def __init__(
        self,
        zones: Dict[str, Sequence[Point]],
        min_points: int = 6,
        min_displacement_px: float = 40.0,
    ) -> None:
        self.zones = zones
        self.min_points = min_points
        self.min_displacement_px = min_displacement_px
        self.od: Dict[Tuple[str, str], Dict[str, int]] = {}
        self.discarded = {"cortos": 0, "inmoviles": 0, "sin_od": 0}

    def _zone_at(self, pt: Point) -> str | None:
        for name, poly in self.zones.items():
            if point_in_polygon(pt, poly):
                return name
        return None

    def add_track(self, cls_name: str, points: List[Point]) -> str | None:
        """Procesa una trayectoria; devuelve 'O>D' si contó, None si no."""
        if cls_name not in CLASSES:
            cls_name = "auto"
        if len(points) < self.min_points:
            self.discarded["cortos"] += 1
            return None
        dx = points[-1][0] - points[0][0]
        dy = points[-1][1] - points[0][1]
        if (dx * dx + dy * dy) ** 0.5 < self.min_displacement_px:
            self.discarded["inmoviles"] += 1
            return None

        origin = None
        dest = None
        for pt in points:
            z = self._zone_at(pt)
            if z is None:
                continue
            if origin is None:
                origin = z
            dest = z
        if origin is None or dest is None or origin == dest:
            self.discarded["sin_od"] += 1
            return None

        key = (origin, dest)
        if key not in self.od:
            self.od[key] = {c: 0 for c in CLASSES}
        self.od[key][cls_name] += 1
        return f"{origin}>{dest}"

    def result(self, duration_s: float) -> dict:
        factor = 3600.0 / duration_s if duration_s > 0 else 0.0
        movements = []
        for (origin, dest), counts in sorted(self.od.items()):
            total = sum(counts.values())
            weighted = sum(counts[c] * PCU_EQ[c] for c in CLASSES)
            movements.append({
                "from": origin,
                "to": dest,
                **counts,
                "total": total,
                "veh_h": round(total * factor, 1),
                "pcu_factor": round(weighted / total, 2) if total else 1.0,
            })
        return {
            "duration_s": round(duration_s, 1),
            "expansion_factor": round(factor, 2),
            "movements": movements,
            "total_counted": sum(m["total"] for m in movements),
            "discarded": dict(self.discarded),
            "warnings": [
                "Expansión simple a veh/h: con clips cortos esto es una "
                "MUESTRA, no un aforo (el criterio formal pide ≥ 15 min). "
                "Úsese con CV alto en el análisis de incertidumbre.",
            ],
        }


def apply_to_config(
    config: dict, tmc: dict, od_to_group: Dict[str, str]
) -> Tuple[dict, List[str]]:
    """Vuelca el TMC en un IntersectionConfig (dict JSON) importable.

    od_to_group: {"W>E": "W-T", ...}. Devuelve (config actualizado, avisos).
    """
    warnings: List[str] = []
    by_od = {f"{m['from']}>{m['to']}": m for m in tmc["movements"]}
    group_ids = {
        lg["id"] for ap in config.get("approaches", [])
        for lg in ap.get("lane_groups", [])
    }
    demand = {d["lane_group_id"]: d for d in config.get("demand", [])}

    for od, gid in od_to_group.items():
        if od not in by_od:
            warnings.append(f"Movimiento {od}: sin conteos en el video.")
            continue
        if gid not in group_ids:
            warnings.append(f"Grupo '{gid}' no existe en la configuración.")
            continue
        m = by_od[od]
        demand[gid] = {
            "lane_group_id": gid,
            "volume": m["veh_h"],
            "pcu_factor": m["pcu_factor"],
        }
    for od in by_od:
        if od not in od_to_group:
            warnings.append(
                f"Movimiento {od} contado en el video pero sin mapeo a grupo."
            )

    config = dict(config)
    config["demand"] = list(demand.values())
    return config, warnings
