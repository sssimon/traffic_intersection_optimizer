"""Puente SUMO opcional — analítico vs microsimulado (tarea 4.2, F4).

Convierte la debilidad declarada del proyecto (no escribimos un
microsimulador propio, §2 del plan) en validación gratuita: exporta la
intersección a un modelo SUMO completo y, si SUMO está instalado, corre N
réplicas headless y pone la demora **microsimulada** al lado de la
**analítica** (HCM). Que dos métodos tan distintos coincidan a grandes
rasgos es la mejor evidencia de que el motor analítico es creíble; que
difieran (p. ej. en sobresaturación), una señal honesta de los límites de
cada uno.

Modelo (todo declarado):

1. **Geometría sintética en estrella**: un nodo central semaforizado y un
   brazo por acceso a `RADIUS_M` sobre su rumbo. El rumbo sale del prefijo
   cardinal del id del acceso (N, S, E, W, NE…); si no son cardinales o
   chocan, se reparten en círculo. La geometría exacta no afecta la demora
   (el `timeLoss` se mide contra el tiempo a flujo libre).
2. **Giros por rumbo**: directo → acceso más opuesto; izquierda/derecha →
   accesos a ±90° (según la mano de circulación, derecha por defecto).
3. **Carriles y conexiones**: el acceso aporta tantos carriles como suman
   sus grupos; se ordenan derecha→izquierda (derecha, directo, izquierda).
4. **Semáforo**: una fase verde + amarillo (+ todo-rojo) por cada fase del
   plan, con las duraciones del plan; la suma reproduce el ciclo. El orden
   de los enlaces de la cadena de estados lo fija `netconvert` (no respeta
   un `linkIndex` impuesto); por eso, cuando SUMO está, el `.tll.xml` se
   construye LEYENDO el orden real del `.net.xml` generado (doble pasada de
   netconvert) y ese mismo archivo se exporta.
5. **Demanda**: se inyecta `demanda ajustada por PCU / PHF` (la MISMA carga
   que analiza el motor) como flujo por movimiento.
6. **Saturación**: NO se impone el `s` analítico; emerge del modelo de
   auto-seguimiento de Krauss de SUMO. Por eso ambos métodos deben coincidir
   solo aproximadamente — ese es justamente el valor de la comparación.

La generación de XML es pura y se prueba sin SUMO; la ejecución
(`netconvert` + `sumo` por subproceso, lectura de `tripinfo`) está aislada y
solo corre si las herramientas están disponibles — degradación elegante.
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from typing import Dict, List, NamedTuple, Optional, Tuple

from .analysis import _los_from_delay, analyze
from .models import (
    IntersectionConfig,
    MovementType,
    SignalPlan,
    SumoAnalyticSummary,
    SumoExportRequest,
    SumoExportResult,
    SumoFile,
    SumoMicrosimResult,
)
from .optimizer import optimize
from .optimizer_delay import optimize_delay

RADIUS_M = 400.0          # largo de cada brazo (m): holgado para colas
SPEED_MS = 13.9           # ~50 km/h
NET_FILE = "net.net.xml"
TELEPORT_S = 300          # umbral de teletransporte (gridlock visible como aviso)

CARDINAL_BEARING = {
    "N": 0.0, "NE": 45.0, "E": 90.0, "SE": 135.0,
    "S": 180.0, "SW": 225.0, "W": 270.0, "NW": 315.0,
}

# Orden físico de los carriles, de la derecha (índice 0) a la izquierda.
_LANE_ORDER = {MovementType.RIGHT: 0, MovementType.THROUGH: 1, MovementType.LEFT: 2}


class _Conn(NamedTuple):
    from_edge: str
    to_edge: str
    from_lane: int
    to_lane: int
    link_index: int
    lane_group_id: str


class SumoModel(NamedTuple):
    approaches: List[str]
    bearings: Dict[str, float]
    in_lanes: Dict[str, int]
    out_lanes: Dict[str, int]
    conns: List[_Conn]
    dests: Dict[str, Optional[str]]
    unresolved: List[str]


# --------------------------------------------------------------------------
# Geometría y topología (puro)
# --------------------------------------------------------------------------

def _cardinal_prefix(approach_id: str) -> Optional[str]:
    s = approach_id.upper().rstrip("0123456789")
    return s if s in CARDINAL_BEARING else None


def _assign_bearings(approach_ids: List[str]) -> Dict[str, float]:
    """Rumbo (grados, 0 = N, 90 = E) por acceso: cardinal si todos lo son y
    no chocan; si no, reparto uniforme en círculo."""
    prefixes = [_cardinal_prefix(a) for a in approach_ids]
    if all(p is not None for p in prefixes):
        vals = {a: CARDINAL_BEARING[p] for a, p in zip(approach_ids, prefixes)}
        if len(set(vals.values())) == len(vals):
            return vals
    n = max(1, len(approach_ids))
    return {a: (360.0 * i / n) for i, a in enumerate(approach_ids)}


def _nearest_approach(
    target: float, bearings: Dict[str, float], exclude: str
) -> Optional[str]:
    best, best_d = None, 999.0
    for a, b in bearings.items():
        if a == exclude:
            continue
        d = abs(((b - target + 180.0) % 360.0) - 180.0)
        if d < best_d:
            best_d, best = d, a
    return best


def _destination(
    approach_id: str, movement: MovementType,
    bearings: Dict[str, float], driving_side: str,
) -> Optional[str]:
    """Acceso destino de un movimiento, inferido por rumbo."""
    b = bearings[approach_id]
    if movement == MovementType.THROUGH:
        target = (b + 180.0) % 360.0
    else:
        left, right = (b + 90.0) % 360.0, (b - 90.0) % 360.0
        if driving_side == "left":
            left, right = right, left
        target = left if movement == MovementType.LEFT else right
    return _nearest_approach(target, bearings, exclude=approach_id)


def prepare_model(
    cfg: IntersectionConfig, driving_side: str = "right"
) -> SumoModel:
    """Topología SUMO de la intersección: rumbos, carriles, destinos de giro
    y conexiones (puro, sin tocar disco).

    Las conexiones se ordenan por (rumbo del acceso, carril) — el mismo orden
    determinista con que `netconvert` numera los enlaces del semáforo — y se
    les asigna `link_index` en ese orden, de modo que la cadena de estados
    case sin depender de leer el `.net.xml`. Aun así, la corrida real vuelve
    a leer el orden del net para ser a prueba de balas.
    """
    ids = [ap.id for ap in cfg.approaches]
    bearings = _assign_bearings(ids)
    in_lanes = {ap.id: sum(lg.lanes for lg in ap.lane_groups) for ap in cfg.approaches}
    out_lanes = dict(in_lanes)

    dests: Dict[str, Optional[str]] = {}
    unresolved: List[str] = []
    raw: List[_Conn] = []
    for ap in cfg.approaches:
        groups = sorted(ap.lane_groups, key=lambda g: _LANE_ORDER.get(g.movement, 1))
        cursor = 0
        for lg in groups:
            dest = _destination(ap.id, lg.movement, bearings, driving_side)
            dests[lg.id] = dest
            if dest is None:
                unresolved.append(lg.id)
                cursor += lg.lanes
                continue
            for k in range(lg.lanes):
                raw.append(_Conn(
                    from_edge=f"in_{ap.id}",
                    to_edge=f"out_{dest}",
                    from_lane=cursor + k,
                    to_lane=min(k, out_lanes[dest] - 1),
                    link_index=-1,
                    lane_group_id=lg.id,
                ))
            cursor += lg.lanes

    raw.sort(key=lambda c: (bearings[c.from_edge[3:]], c.from_lane))
    conns = [c._replace(link_index=i) for i, c in enumerate(raw)]
    return SumoModel(ids, bearings, in_lanes, out_lanes, conns, dests, unresolved)


# --------------------------------------------------------------------------
# Generación de XML (puro)
# --------------------------------------------------------------------------

_HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n'


def build_nod_xml(model: SumoModel) -> str:
    lines = [_HEAD + "<nodes>",
             '  <node id="C" x="0.00" y="0.00" type="traffic_light"/>']
    for a in model.approaches:
        rad = math.radians(model.bearings[a])
        x, y = RADIUS_M * math.sin(rad), RADIUS_M * math.cos(rad)
        lines.append(f'  <node id="{a}" x="{x:.2f}" y="{y:.2f}" type="priority"/>')
    lines.append("</nodes>\n")
    return "\n".join(lines)


def build_edg_xml(model: SumoModel) -> str:
    lines = [_HEAD + "<edges>"]
    for a in model.approaches:
        lines.append(
            f'  <edge id="in_{a}" from="{a}" to="C" '
            f'numLanes="{model.in_lanes[a]}" speed="{SPEED_MS:.2f}" priority="3"/>'
        )
        lines.append(
            f'  <edge id="out_{a}" from="C" to="{a}" '
            f'numLanes="{model.out_lanes[a]}" speed="{SPEED_MS:.2f}" priority="3"/>'
        )
    lines.append("</edges>\n")
    return "\n".join(lines)


def build_con_xml(model: SumoModel) -> str:
    lines = [_HEAD + "<connections>"]
    for c in model.conns:
        lines.append(
            f'  <connection from="{c.from_edge}" to="{c.to_edge}" '
            f'fromLane="{c.from_lane}" toLane="{c.to_lane}" '
            f'linkIndex="{c.link_index}"/>'
        )
    lines.append("</connections>\n")
    return "\n".join(lines)


def build_tll_from_order(
    cfg: IntersectionConfig, plan: SignalPlan, link_groups: List[Optional[str]]
) -> str:
    """Programa estático del semáforo dado el orden REAL de los enlaces.

    `link_groups[i]` = id del grupo de carriles que controla el enlace `i`
    (None si el enlace no corresponde a ningún grupo). Por cada fase del plan
    se emite verde + amarillo (+ todo-rojo); la suma reproduce el ciclo.
    """
    k = len(link_groups)
    body: List[str] = []
    for ph in cfg.phases:
        g = plan.phase_green.get(ph.id, 0.0)
        y = plan.phase_yellow.get(ph.id, ph.yellow)
        ar = plan.phase_all_red.get(ph.id, ph.all_red)
        active = set(ph.lane_group_ids)
        green = "".join("G" if link_groups[i] in active else "r" for i in range(k))
        yellow = "".join("y" if link_groups[i] in active else "r" for i in range(k))
        if g > 0:
            body.append(f'    <phase duration="{g:.1f}" state="{green}"/>')
        if y > 0:
            body.append(f'    <phase duration="{y:.1f}" state="{yellow}"/>')
        if ar > 0:
            body.append(f'    <phase duration="{ar:.1f}" state="{"r" * k}"/>')

    inner = "\n".join(body)
    return (
        _HEAD + "<tlLogics>\n"
        '  <tlLogic id="C" type="static" programID="0" offset="0">\n'
        f"{inner}\n"
        "  </tlLogic>\n"
        "</tlLogics>\n"
    )


def build_tll_xml(cfg: IntersectionConfig, plan: SignalPlan, model: SumoModel) -> str:
    """Cadena de estados con el orden heurístico del modelo (rumbo, carril) —
    coincide con netconvert para geometrías estándar; la corrida lo confirma
    leyendo el net real."""
    ordered = sorted(model.conns, key=lambda c: c.link_index)
    return build_tll_from_order(cfg, plan, [c.lane_group_id for c in ordered])


def build_rou_xml(cfg: IntersectionConfig, model: SumoModel, end_s: int) -> str:
    routes: List[str] = []
    flows: List[str] = []
    for ap in cfg.approaches:
        for lg in ap.lane_groups:
            dest = model.dests.get(lg.id)
            v = cfg.demand_for(lg.id)
            if not dest or v <= 0:
                continue
            rid = f"r_{lg.id}"
            routes.append(f'  <route id="{rid}" edges="in_{ap.id} out_{dest}"/>')
            flows.append(
                f'  <flow id="f_{lg.id}" type="car" route="{rid}" '
                f'begin="0" end="{end_s}" vehsPerHour="{v:.1f}" '
                f'departLane="best" departSpeed="max"/>'
            )
    vtype = (
        '  <vType id="car" vClass="passenger" length="5.00" minGap="2.50" '
        f'accel="2.60" decel="4.50" sigma="0.50" maxSpeed="{SPEED_MS:.2f}"/>'
    )
    inner = "\n".join([vtype, *routes, *flows])
    return _HEAD + "<routes>\n" + inner + "\n</routes>\n"


def build_sumocfg(end_s: int) -> str:
    return (
        _HEAD + "<configuration>\n"
        "  <input>\n"
        f'    <net-file value="{NET_FILE}"/>\n'
        '    <route-files value="routes.rou.xml"/>\n'
        "  </input>\n"
        "  <time>\n"
        '    <begin value="0"/>\n'
        f'    <end value="{end_s}"/>\n'
        "  </time>\n"
        "</configuration>\n"
    )


def build_all(
    cfg: IntersectionConfig, plan: SignalPlan, model: SumoModel, end_s: int
) -> Dict[str, str]:
    return {
        "nodes.nod.xml": build_nod_xml(model),
        "edges.edg.xml": build_edg_xml(model),
        "connections.con.xml": build_con_xml(model),
        "tls.tll.xml": build_tll_xml(cfg, plan, model),
        "routes.rou.xml": build_rou_xml(cfg, model, end_s),
        "interseccion.sumocfg": build_sumocfg(end_s),
    }


# --------------------------------------------------------------------------
# Lectura de resultados de SUMO (puro)
# --------------------------------------------------------------------------

def parse_tripinfo(xml_text: str, warmup_s: float) -> Tuple[int, float, float]:
    """(n, demora media, espera media) sobre los vehículos que parten tras el
    calentamiento. La demora es `timeLoss` (≈ demora de control HCM)."""
    root = ET.fromstring(xml_text)
    losses: List[float] = []
    waits: List[float] = []
    for t in root.findall("tripinfo"):
        if float(t.get("depart", "0")) < warmup_s:
            continue
        losses.append(float(t.get("timeLoss", "0")))
        waits.append(float(t.get("waitingTime", "0")))
    n = len(losses)
    if n == 0:
        return 0, 0.0, 0.0
    return n, sum(losses) / n, sum(waits) / n


def parse_teleports(xml_text: str) -> int:
    try:
        root = ET.fromstring(xml_text)
        tp = root.find("teleports")
        if tp is not None:
            return int(tp.get("total", "0"))
    except ET.ParseError:
        pass
    return 0


def link_groups_from_net(net_text: str, model: SumoModel) -> List[Optional[str]]:
    """Orden REAL de los enlaces del semáforo según el `.net.xml` generado.

    Devuelve `link_groups[linkIndex] = lane_group_id`. netconvert reordena los
    enlaces (no respeta el `linkIndex` del archivo de conexiones), así que el
    `.tll.xml` debe construirse contra este orden o las fases se desalinean.
    """
    root = ET.fromstring(net_text)
    lookup = {
        (c.from_edge, c.to_edge, c.from_lane): c.lane_group_id for c in model.conns
    }
    indexed: List[Tuple[int, Optional[str]]] = []
    for cn in root.findall("connection"):
        li = cn.get("linkIndex")
        frm = cn.get("from")
        if li is None or frm is None or frm.startswith(":"):
            continue
        key = (frm, cn.get("to"), int(cn.get("fromLane", "0")))
        indexed.append((int(li), lookup.get(key)))
    indexed.sort()
    return [lg for _, lg in indexed]


# --------------------------------------------------------------------------
# Disponibilidad y ejecución de SUMO (I/O, aislado)
# --------------------------------------------------------------------------

def _tool_path(name: str) -> Optional[str]:
    found = shutil.which(name)
    if found:
        return found
    home = os.environ.get("SUMO_HOME")
    if home:
        exe = name + (".exe" if os.name == "nt" else "")
        cand = os.path.join(home, "bin", exe)
        if os.path.exists(cand):
            return cand
    return None


def is_sumo_available() -> bool:
    return _tool_path("netconvert") is not None and _tool_path("sumo") is not None


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _run_netconvert(netconvert: str, work: str, with_tll: bool, timeout_s: int) -> None:
    net_out = os.path.join(work, NET_FILE)
    cmd = [
        netconvert,
        "--node-files", os.path.join(work, "nodes.nod.xml"),
        "--edge-files", os.path.join(work, "edges.edg.xml"),
        "--connection-files", os.path.join(work, "connections.con.xml"),
        "--output-file", net_out,
        "--no-turnarounds", "true",
        "--no-warnings", "true",
        "--xml-validation", "never",
    ]
    if with_tll:
        cmd[1:1] = ["--tllogic-files", os.path.join(work, "tls.tll.xml")]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    if r.returncode != 0 or not os.path.exists(net_out):
        raise RuntimeError(
            "netconvert falló: " + (r.stderr.strip()[-300:] or "sin detalle")
        )


def run_microsim(
    cfg: IntersectionConfig, plan: SignalPlan, model: SumoModel, *,
    replications: int, seed: int, warmup_s: float, duration_s: int,
    timeout_s: int = 180,
) -> Tuple[SumoMicrosimResult, str]:
    """Compila la red y corre N réplicas de sumo headless. Devuelve el
    resultado y el `.tll.xml` realmente usado (alineado al net), para que los
    archivos exportados coincidan exactamente con lo que se corrió.

    Lanza RuntimeError si SUMO no está o si netconvert/sumo fallan (lo captura
    `process_sumo_export` para degradar con elegancia)."""
    import numpy as np

    netconvert = _tool_path("netconvert")
    sumo = _tool_path("sumo")
    if not netconvert or not sumo:
        raise RuntimeError("SUMO no disponible (netconvert/sumo no encontrados).")

    work = tempfile.mkdtemp(prefix="sumo_tio_")
    try:
        end_s = int(warmup_s + duration_s)
        base = {
            "nodes.nod.xml": build_nod_xml(model),
            "edges.edg.xml": build_edg_xml(model),
            "connections.con.xml": build_con_xml(model),
            "routes.rou.xml": build_rou_xml(cfg, model, end_s),
            "interseccion.sumocfg": build_sumocfg(end_s),
        }
        for name, content in base.items():
            with open(os.path.join(work, name), "w", encoding="utf-8") as f:
                f.write(content)

        # Pasada 1: red SIN semáforo propio, para leer el orden real de enlaces.
        _run_netconvert(netconvert, work, with_tll=False, timeout_s=timeout_s)
        link_groups = link_groups_from_net(_read(os.path.join(work, NET_FILE)), model)
        tll = build_tll_from_order(cfg, plan, link_groups)
        with open(os.path.join(work, "tls.tll.xml"), "w", encoding="utf-8") as f:
            f.write(tll)
        # Pasada 2: red con el semáforo ya alineado al orden de netconvert.
        _run_netconvert(netconvert, work, with_tll=True, timeout_s=timeout_s)

        cfg_path = os.path.join(work, "interseccion.sumocfg")
        delays: List[float] = []
        counts: List[int] = []
        waits: List[float] = []
        teleports: List[int] = []
        for i in range(replications):
            tri = os.path.join(work, f"tripinfo_{i}.xml")
            stat = os.path.join(work, f"stat_{i}.xml")
            cmd = [
                sumo, "-c", cfg_path,
                "--seed", str(seed + i),
                "--tripinfo-output", tri,
                "--statistic-output", stat,
                "--no-step-log", "true",
                "--no-warnings", "true",
                "--xml-validation", "never",
                "--duration-log.disable", "true",
                "--time-to-teleport", str(TELEPORT_S),
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
            if r.returncode != 0 or not os.path.exists(tri):
                raise RuntimeError(
                    "sumo falló: " + (r.stderr.strip()[-300:] or "sin detalle")
                )
            n, delay, wait = parse_tripinfo(_read(tri), warmup_s)
            tp = parse_teleports(_read(stat)) if os.path.exists(stat) else 0
            delays.append(delay)
            counts.append(n)
            waits.append(wait)
            teleports.append(tp)

        arr = np.array(delays, dtype=float)
        mean = float(arr.mean())
        result = SumoMicrosimResult(
            replications=replications,
            measured_vehicles=round(float(np.mean(counts)), 1),
            delay_mean_s=round(mean, 1),
            delay_p05_s=round(float(np.percentile(arr, 5)), 1),
            delay_p50_s=round(float(np.percentile(arr, 50)), 1),
            delay_p95_s=round(float(np.percentile(arr, 95)), 1),
            mean_waiting_s=round(float(np.mean(waits)), 1),
            overall_los=_los_from_delay(mean),
            teleports=round(float(np.mean(teleports)), 1),
        )
        return result, tll
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --------------------------------------------------------------------------
# Orquestación
# --------------------------------------------------------------------------

def _plan_for(cfg: IntersectionConfig, method: str) -> SignalPlan:
    return optimize_delay(cfg) if method == "delay_min" else optimize(cfg)


def process_sumo_export(req: SumoExportRequest) -> SumoExportResult:
    cfg = req.config
    if not cfg.phases:
        raise ValueError(
            "El puente SUMO requiere una intersección semaforizada con al "
            "menos una fase."
        )
    plan = req.signal_plan or _plan_for(cfg, req.method)
    analysis = analyze(cfg, plan)
    model = prepare_model(cfg, req.driving_side)
    end_s = req.warmup_s + req.duration_s
    files_dict = build_all(cfg, plan, model, end_s)

    warnings: List[str] = []
    for lg_id in model.unresolved:
        warnings.append(
            f"Movimiento '{lg_id}': sin acceso destino geométrico; su flujo "
            "no se exporta."
        )
    assigned = {lg for ph in cfg.phases for lg in ph.lane_group_ids}
    for ap in cfg.approaches:
        for lg in ap.lane_groups:
            if lg.id not in assigned and cfg.demand_for(lg.id) > 0:
                warnings.append(
                    f"Movimiento '{lg.id}' tiene demanda pero no está en "
                    "ninguna fase: en SUMO no recibe verde."
                )

    notes = [
        "Geometría sintética en estrella (radio 400 m); destinos de giro "
        "inferidos por rumbo (mano derecha).",
        "La saturación microsimulada emerge del auto-seguimiento de Krauss "
        "(no se impone el s analítico): los dos métodos deben coincidir solo "
        "aproximadamente — ese es el valor de la comparación.",
        "Demanda inyectada = demanda ajustada por PCU / PHF (la misma carga "
        "que analiza el motor).",
        "timeLoss de SUMO ≈ demora de control; LOS con los mismos umbrales HCM.",
        "Los giros permitidos en conflicto no se modelan aparte; cada fase "
        "recibe verde 'G' según el plan.",
    ]

    available = is_sumo_available()
    micro: Optional[SumoMicrosimResult] = None
    delta: Optional[float] = None

    if not available:
        notes.append(
            "SUMO no detectado (ni en PATH ni en SUMO_HOME): se exportan los "
            "archivos para correrlo a mano. Instala SUMO para la comparación "
            "automática."
        )
    elif req.run_microsim:
        try:
            micro, tll = run_microsim(
                cfg, plan, model,
                replications=req.replications,
                seed=req.seed,
                warmup_s=req.warmup_s,
                duration_s=req.duration_s,
            )
            files_dict["tls.tll.xml"] = tll  # el .tll.xml exacto que se corrió
            delta = round(micro.delay_mean_s - analysis.avg_delay_s, 1)
            if micro.measured_vehicles <= 0:
                warnings.append(
                    "SUMO no midió vehículos tras el calentamiento: reduce el "
                    "calentamiento o aumenta la duración."
                )
            if micro.teleports > 0:
                warnings.append(
                    f"SUMO teletransportó ~{micro.teleports:.0f} vehículos por "
                    "congestión (gridlock): la demora microsimulada queda "
                    "subestimada."
                )
        except Exception as exc:  # noqa: BLE001 — degradación elegante
            warnings.append(
                f"No se pudo correr SUMO ({exc}); se devuelven los archivos "
                "para correrlo a mano."
            )

    files = [SumoFile(name=k, content=v) for k, v in files_dict.items()]
    return SumoExportResult(
        sumo_available=available,
        files=files,
        analytic=SumoAnalyticSummary(
            avg_delay_s=analysis.avg_delay_s,
            overall_los=analysis.overall_los,
            overall_v_c=analysis.overall_v_c,
        ),
        microsim=micro,
        delta_delay_s=delta,
        warnings=warnings,
        notes=notes,
    )
