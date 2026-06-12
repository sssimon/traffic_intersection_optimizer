"""Persistencia de corridas (tarea 2.5, M13/F24 de la auditoría).

Guarda en SQLite (stdlib, sin dependencias) cada corrida: la configuración
completa de la intersección más el resumen del análisis (método, ciclo,
demora, LOS, v/c) calculado en el momento de guardar. Eso permite:

- recuperar una configuración tal cual se analizó (cargar),
- comparar corridas entre fechas (la tabla de resúmenes ES la comparación),
- darle uso real al directorio data/runs/ reservado desde el inicio.

La base vive en data/runs/runs.db (ignorada por git). El esquema se crea
on-demand en cada conexión (CREATE TABLE IF NOT EXISTS): sin migraciones ni
hooks de arranque para un esquema de una tabla.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .analysis import analyze
from .models import (
    IntersectionConfig,
    RunDetail,
    RunSummary,
    SaveRunRequest,
)
from .optimizer import optimize
from .optimizer_delay import optimize_delay

# Raíz del repo: backend/app/storage.py -> parents[2]
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "runs" / "runs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    intersection_name TEXT NOT NULL,
    method TEXT NOT NULL,
    cycle_length REAL NOT NULL,
    avg_delay_s REAL NOT NULL,
    overall_los TEXT NOT NULL,
    overall_v_c REAL NOT NULL,
    config_json TEXT NOT NULL
)
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def _summary(row: sqlite3.Row) -> RunSummary:
    return RunSummary(
        id=row["id"],
        name=row["name"],
        created_at=row["created_at"],
        intersection_name=row["intersection_name"],
        method=row["method"],
        cycle_length=row["cycle_length"],
        avg_delay_s=row["avg_delay_s"],
        overall_los=row["overall_los"],
        overall_v_c=row["overall_v_c"],
    )


def save_run(req: SaveRunRequest) -> RunSummary:
    """Analiza la configuración con el método pedido y guarda el resumen."""
    optimizer = optimize_delay if req.method == "delay_min" else optimize
    plan = optimizer(req.config)
    analysis = analyze(req.config, plan)

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO runs (name, created_at, intersection_name, method, "
            "cycle_length, avg_delay_s, overall_los, overall_v_c, config_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                req.name.strip(),
                created_at,
                req.config.name,
                req.method,
                plan.cycle_length,
                analysis.avg_delay_s,
                analysis.overall_los.value,
                analysis.overall_v_c,
                req.config.model_dump_json(),
            ),
        )
        run_id = cur.lastrowid
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return _summary(row)


def list_runs() -> List[RunSummary]:
    """Resúmenes de todas las corridas, la más reciente primero."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
    return [_summary(r) for r in rows]


def get_run(run_id: int) -> Optional[RunDetail]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    return RunDetail(
        **_summary(row).model_dump(),
        config=IntersectionConfig.model_validate_json(row["config_json"]),
    )


def delete_run(run_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
    return cur.rowcount > 0
