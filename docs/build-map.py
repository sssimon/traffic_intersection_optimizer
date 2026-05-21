#!/usr/bin/env python3
"""build-map.py — Regenera figura-4-ubicacion.png (mapa de ubicación).

Renderiza un mapa Leaflet (tiles CartoDB / OpenStreetMap) centrado en las
coordenadas de la intersección, con un marcador, y guarda una captura PNG
que el informe (`informe-caso-ejemplo.html`) incluye en su sección 2.

Uso:
  python build-map.py                      # coordenadas desde el JSON del caso
  python build-map.py 7.780639 -72.221870  # coordenadas explícitas
  python build-map.py 7.780639 -72.221870 17   # ... con nivel de zoom (def. 16)

Requisitos:
  - Python 3 con el paquete 'websocket-client'
        pip install --user websocket-client
  - Microsoft Edge o Google Chrome instalado
  - Conexión a internet (para descargar los tiles del mapa)
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

DOCS = Path(__file__).resolve().parent
JSON_CASE = DOCS / "ejemplo-aforo-cruce-av-principal.json"
OUT_PNG = DOCS / "figura-4-ubicacion.png"
WIN_W, WIN_H = 960, 560

HTML_TEMPLATE = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html,body,#map{{margin:0;height:100%;width:100%}}
  .leaflet-control-zoom a{{border-radius:0!important;color:#0a0a0a}}
  .leaflet-bar{{border:1px solid #0a0a0a;box-shadow:none}}
  .leaflet-control-attribution{{font-size:10px}}
</style></head><body><div id="map"></div><script>
  var lat={lat}, lng={lng}, zoom={zoom};
  var map=L.map('map',{{zoomControl:true,attributionControl:true}}).setView([lat,lng],zoom);
  L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png',
    {{subdomains:'abcd',maxZoom:19,attribution:'&copy; OpenStreetMap &copy; CARTO'}}).addTo(map);
  L.circleMarker([lat,lng],{{radius:12,color:'#8a0f1c',weight:3,
    fillColor:'#8a0f1c',fillOpacity:0.35}}).addTo(map);
</script></body></html>
"""


def find_browser() -> str | None:
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    for name in ("msedge", "chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def read_case_coords() -> tuple[float, float]:
    if not JSON_CASE.exists():
        sys.exit(f"ERROR: no se encuentra {JSON_CASE.name} y no se dieron coordenadas.")
    cfg = json.loads(JSON_CASE.read_text(encoding="utf-8"))
    lat, lng = cfg.get("latitude"), cfg.get("longitude")
    if lat is None or lng is None:
        sys.exit(
            f"ERROR: {JSON_CASE.name} no tiene latitude/longitude. "
            "Pásalas como argumentos: python build-map.py LAT LNG"
        )
    return float(lat), float(lng)


def render(lat: float, lng: float, zoom: int) -> bool:
    try:
        import websocket  # noqa: F401  (websocket-client)
    except ImportError:
        print("  ERROR: falta el paquete 'websocket-client'.")
        print("         Instálalo con:  pip install --user websocket-client")
        return False
    import websocket

    browser = find_browser()
    if not browser:
        print("  ERROR: no se encontró Microsoft Edge ni Google Chrome.")
        return False

    tmp_html = DOCS / "_map_tmp.html"
    tmp_html.write_text(HTML_TEMPLATE.format(lat=lat, lng=lng, zoom=zoom), encoding="utf-8")
    profile = tempfile.mkdtemp(prefix="edge-map-")
    port = free_port()

    proc = subprocess.Popen(
        [
            browser, "--headless", "--disable-gpu", "--hide-scrollbars",
            f"--remote-debugging-port={port}", "--remote-allow-origins=*",
            f"--user-data-dir={profile}", f"--window-size={WIN_W},{WIN_H}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        # Esperar a que el endpoint CDP responda.
        base = f"http://127.0.0.1:{port}"
        for _ in range(40):
            try:
                urllib.request.urlopen(base + "/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            print("  ERROR: el navegador no abrió el puerto de depuración.")
            return False

        targets = json.load(urllib.request.urlopen(base + "/json"))
        page = next(t for t in targets if t.get("type") == "page")
        ws = websocket.create_connection(
            page["webSocketDebuggerUrl"], timeout=40,
            header=["Origin: http://localhost"],
        )
        _id = 0

        def cmd(method, params=None):
            nonlocal _id
            _id += 1
            ws.send(json.dumps({"id": _id, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == _id:
                    return msg

        cmd("Page.enable")
        url = "file:///" + str(tmp_html).replace("\\", "/")
        cmd("Page.navigate", {"url": url})

        # Esperar a que carguen los tiles del mapa.
        loaded = 0
        for _ in range(24):
            time.sleep(0.6)
            r = cmd("Runtime.evaluate", {
                "expression": "document.querySelectorAll('.leaflet-tile-loaded').length",
                "returnByValue": True,
            })
            loaded = r.get("result", {}).get("result", {}).get("value", 0) or 0
            if loaded >= 8:
                break
        time.sleep(1.0)  # asentar el render

        shot = cmd("Page.captureScreenshot", {"format": "png"})
        OUT_PNG.write_bytes(base64.b64decode(shot["result"]["data"]))
        ws.close()
        print(f"  tiles cargados: {loaded}")
        return OUT_PNG.exists() and OUT_PNG.stat().st_size > 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        tmp_html.unlink(missing_ok=True)
        shutil.rmtree(profile, ignore_errors=True)


def main() -> int:
    args = sys.argv[1:]
    zoom = 16
    if len(args) >= 2:
        try:
            lat, lng = float(args[0]), float(args[1])
        except ValueError:
            print("ERROR: latitud y longitud deben ser números.")
            return 2
        if len(args) >= 3:
            try:
                zoom = int(args[2])
            except ValueError:
                print("ERROR: el zoom debe ser un entero.")
                return 2
    elif len(args) == 0:
        lat, lng = read_case_coords()
    else:
        print("Uso: python build-map.py [LAT LNG [ZOOM]]")
        return 2

    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        print("ERROR: coordenadas fuera de rango.")
        return 2

    print(f"Generando figura-4-ubicacion.png  (lat {lat}, lng {lng}, zoom {zoom}) ...")
    ok = render(lat, lng, zoom)
    if ok:
        print(f"  OK  ({OUT_PNG.stat().st_size / 1024:.0f} KB)  ->  {OUT_PNG}")
        print("\nRecuerda regenerar el informe:  python build-pdf.py informe")
        return 0
    print("  FALLO al generar el mapa.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
