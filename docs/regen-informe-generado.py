#!/usr/bin/env python3
"""regen-informe-generado.py — Regenera el informe de 1 clic del caso ejemplo.

Llama al motor (`backend/app/reports.py`, tarea 5.1) sobre el aforo de
ejemplo y escribe `informe-generado-ejemplo.html`. Es el mismo informe que
produce el botón «Generar informe» de la aplicación; este script solo lo
materializa como artefacto del repositorio. Para el PDF:

    python regen-informe-generado.py
    python build-pdf.py informe-generado
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent
sys.path.insert(0, str(DOCS.parent / "backend"))

from app.models import IntersectionConfig          # noqa: E402
from app.reports import build_report_html           # noqa: E402

SRC = DOCS / "ejemplo-aforo-cruce-av-principal.json"
OUT = DOCS / "informe-generado-ejemplo.html"


def main() -> int:
    cfg = IntersectionConfig(**json.loads(SRC.read_text(encoding="utf-8")))
    html = build_report_html(
        cfg, method="delay_min", volume_cv=0.10, samples=3000,
        study_date="Jueves 30 de abril de 2026, 07:00-09:00",
    )
    OUT.write_text(html, encoding="utf-8")
    print(f"OK  {OUT.name}  ({len(html) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
