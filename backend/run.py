"""Entrypoint local.

Elige automáticamente el primer puerto libre del rango configurable y lo
escribe en `../.dev-port` para que el frontend (Vite) lo lea como destino
del proxy. Evita colisiones con otros servicios locales.
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import uvicorn

HOST = "127.0.0.1"
PORT_START = 8765
PORT_END = 8800
PORT_FILE = Path(__file__).resolve().parent.parent / ".dev-port"


def find_free_port(host: str, start: int, end: int) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            try:
                s.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(
        f"No hay puertos libres en el rango {start}-{end}."
    )


if __name__ == "__main__":
    # Permite forzar un puerto con la env var BACKEND_PORT
    forced = os.environ.get("BACKEND_PORT")
    if forced:
        port = int(forced)
    else:
        port = find_free_port(HOST, PORT_START, PORT_END)

    PORT_FILE.write_text(str(port), encoding="utf-8")
    print(f"[run.py] Puerto elegido: {port}  (escrito en {PORT_FILE})", flush=True)
    sys.stdout.flush()

    uvicorn.run("app.main:app", host=HOST, port=port, reload=True)
