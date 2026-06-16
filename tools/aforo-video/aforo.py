"""Aforo por video (tarea 3.2) — YOLO + ByteTrack → matriz OD importable.

Uso:
  python aforo.py VIDEO ZONAS.json [--out tmc.json] [--modelo yolov8s.pt]
                  [--conf 0.15] [--imgsz 1280] [--stride 3] [--max-s N]
                  [--anotado salida.mp4] [--frames-debug carpeta]
                  [--config interseccion.json --map "W>E=W-T,E>W=E-T"]

ZONAS.json: {"zonas": [{"nombre": "W", "poligono": [[x, y], ...]}, ...]}
  Una zona por boca de acceso (entrada/salida). El origen del track es la
  primera zona tocada y el destino la última.

Clases COCO → clases del aforo: car→auto, motorcycle→moto, bus→bus,
truck→camion.

Salida: TMC JSON (conteos por clase, veh/h expandidos y PCU por
movimiento) y, con --config y --map, una copia de la configuración con la
demanda volcada lista para Importar JSON en la app.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict

import cv2
from ultralytics import YOLO

from counting import OdCounter, apply_to_config, stitch_tracks

COCO_TO_CLASS = {2: "auto", 3: "moto", 5: "bus", 7: "camion"}


def main() -> None:
    ap = argparse.ArgumentParser(description="Aforo por video — OD por clase")
    ap.add_argument("video")
    ap.add_argument("zonas")
    ap.add_argument("--out", default="tmc.json")
    ap.add_argument("--modelo", default="yolov8s.pt")
    ap.add_argument("--conf", type=float, default=0.15)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--stride", type=int, default=3,
                    help="Procesar 1 de cada N cuadros.")
    ap.add_argument("--max-s", type=float, default=0,
                    help="Limitar a los primeros N segundos (0 = todo).")
    ap.add_argument("--anotado", default="",
                    help="Escribir video anotado (verificación manual).")
    ap.add_argument("--frames-debug", default="",
                    help="Carpeta para volcar cuadros anotados de muestra.")
    ap.add_argument("--dump-tracks", default="",
                    help="Volcar trayectorias crudas a JSON (diagnóstico; "
                         "permite iterar zonas/costura sin re-detectar).")
    ap.add_argument("--config", default="",
                    help="IntersectionConfig JSON al que volcar la demanda.")
    ap.add_argument("--map", default="",
                    help='Mapeo OD→grupo: "W>E=W-T,E>W=E-T,..."')
    args = ap.parse_args()

    with open(args.zonas, encoding="utf-8") as f:
        zonas_doc = json.load(f)
    zones = {z["nombre"]: [tuple(p) for p in z["poligono"]]
             for z in zonas_doc["zonas"]}

    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    limit = int(min(n_frames, args.max_s * fps)) if args.max_s > 0 else n_frames

    model = YOLO(args.modelo)

    writer = None
    if args.anotado:
        writer = cv2.VideoWriter(
            args.anotado, cv2.VideoWriter_fourcc(*"mp4v"),
            fps / args.stride, (width, height),
        )
    if args.frames_debug:
        os.makedirs(args.frames_debug, exist_ok=True)

    # Trayectorias: track_id -> (clase más votada, lista de centros)
    tracks: dict[int, list[tuple[float, float]]] = defaultdict(list)
    track_cls: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    poly_np = {name: [(int(x), int(y)) for x, y in poly]
               for name, poly in zones.items()}

    processed = 0
    frame_idx = 0
    while frame_idx < limit:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % args.stride != 0:
            frame_idx += 1
            continue

        results = model.track(
            frame, persist=True, conf=args.conf, imgsz=args.imgsz,
            classes=list(COCO_TO_CLASS), tracker="bytetrack.yaml",
            verbose=False,
        )
        r = results[0]
        if r.boxes is not None and r.boxes.id is not None:
            ids = r.boxes.id.int().tolist()
            clss = r.boxes.cls.int().tolist()
            xyxy = r.boxes.xyxy.tolist()
            for tid, ci, box in zip(ids, clss, xyxy):
                cx = (box[0] + box[2]) / 2.0
                cy = (box[1] + box[3]) / 2.0
                tracks[tid].append((frame_idx, cx, cy))
                track_cls[tid][COCO_TO_CLASS.get(ci, "auto")] += 1

        if writer is not None or args.frames_debug:
            annotated = r.plot(line_width=1, font_size=0.4)
            for name, pts in poly_np.items():
                for i in range(len(pts)):
                    cv2.line(annotated, pts[i], pts[(i + 1) % len(pts)],
                             (0, 255, 255), 2)
                cv2.putText(annotated, name, pts[0],
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            if writer is not None:
                writer.write(annotated)
            if args.frames_debug and processed % 60 == 0:
                cv2.imwrite(
                    os.path.join(args.frames_debug, f"a{frame_idx:05d}.png"),
                    annotated,
                )

        processed += 1
        frame_idx += 1

    cap.release()
    if writer is not None:
        writer.release()

    duration_s = min(limit, frame_idx) / fps

    if args.dump_tracks:
        with open(args.dump_tracks, "w", encoding="utf-8") as f:
            json.dump({
                "fps": fps,
                "duration_s": duration_s,
                "tracks": [
                    {"id": tid, "cls_votes": dict(track_cls[tid]),
                     "points": pts}
                    for tid, pts in tracks.items()
                ],
            }, f)

    # Costura de fragmentos: el tracking pierde IDs a mitad del cruce
    # (sobre todo de noche) y sin coser casi ningún viaje toca dos zonas.
    segments = [
        {"cls_votes": dict(track_cls[tid]), "points": pts}
        for tid, pts in tracks.items()
    ]
    chains = stitch_tracks(segments, fps=fps)

    counter = OdCounter(zones)
    for chain in chains:
        cls_name = max(chain["cls_votes"].items(), key=lambda kv: kv[1])[0]
        counter.add_track(cls_name, [(x, y) for _, x, y in chain["points"]])

    tmc = counter.result(duration_s)
    tmc["video"] = os.path.basename(args.video)
    tmc["fps"] = round(fps, 2)
    tmc["stride"] = args.stride
    tmc["tracks_detectados"] = len(tracks)
    tmc["tracks_cosidos"] = len(chains)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(tmc, f, ensure_ascii=False, indent=2)

    print(f"video: {tmc['video']}  dur={duration_s:.1f}s  "
          f"tracks={len(tracks)} -> cosidos={len(chains)}  "
          f"contados={tmc['total_counted']}  "
          f"descartados={tmc['discarded']}")
    for m in tmc["movements"]:
        print(f"  {m['from']}>{m['to']}: total={m['total']} "
              f"(auto {m['auto']}, moto {m['moto']}, bus {m['bus']}, "
              f"camión {m['camion']})  ≈{m['veh_h']} veh/h  PCU {m['pcu_factor']}")

    if args.config and args.map:
        with open(args.config, encoding="utf-8") as f:
            config = json.load(f)
        od_map = dict(pair.split("=") for pair in args.map.split(","))
        updated, warnings = apply_to_config(config, tmc, od_map)
        out_cfg = os.path.splitext(args.config)[0] + "-aforado.json"
        with open(out_cfg, "w", encoding="utf-8") as f:
            json.dump(updated, f, ensure_ascii=False, indent=2)
        print(f"configuración con demanda volcada: {out_cfg}")
        for w in warnings:
            print(f"  aviso: {w}")


if __name__ == "__main__":
    main()
