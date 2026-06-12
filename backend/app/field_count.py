"""Aforo de campo de 15 minutos (tarea 3.3) — del conteo al análisis sin Excel.

Procesa conteos de campo por intervalo de 15 min y clase vehicular
(auto / moto / bus / camión) y entrega lo que la tabla de demanda necesita:

- Hora pico: la ventana móvil de 4 intervalos que maximiza el total de la
  intersección (práctica HCM). Con menos de 4 intervalos el volumen horario
  se obtiene por expansión simple ×(4/n), con aviso de mayor incertidumbre
  (úsese un CV alto en el análisis Monte Carlo).
- PHF = V_hora / (4·V15máx), calculado sobre el total de la intersección;
  se acota al rango del modelo [0.70, 1.00] con aviso si se recorta.
- PCU por movimiento desde la composición de la hora pico:
  Σ(conteo_clase · equivalencia) / Σ(conteo_clase). Equivalencias por
  defecto declaradas y editables: auto 1.0, moto 0.5, bus 2.0, camión 2.0.
  Una composición con muchas motos produce PCU < 1.0 — efecto real y
  relevante en el tránsito de LatAm.
"""
from __future__ import annotations

import re
from typing import Dict, List

from .models import FieldCountRequest, FieldCountResult, MovementCounts

CLASSES = ("auto", "moto", "bus", "camion")
PHF_MIN, PHF_MAX = 0.70, 1.00
PCU_MIN, PCU_MAX = 0.3, 3.0


def _series(
    mc: MovementCounts, n: int, group_id: str, cls_name: str
) -> List[float]:
    raw: List[float] = getattr(mc, cls_name)
    if not raw:
        return [0.0] * n
    if len(raw) != n:
        raise ValueError(
            f"Grupo '{group_id}', clase {cls_name}: {len(raw)} valores "
            f"para {n} intervalos."
        )
    return [max(0.0, float(x)) for x in raw]


def _end_label(labels: List[str], k: int) -> str:
    """Fin de la hora pico: inicio del último intervalo + 15 min."""
    last = labels[k + 3].strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", last)
    if m:
        h, mi = int(m.group(1)), int(m.group(2)) + 15
        h = (h + mi // 60) % 24
        mi %= 60
        return f"{h:02d}:{mi:02d}"
    return f"{last} +15 min"


def process_field_count(req: FieldCountRequest) -> FieldCountResult:
    n = len(req.interval_labels)
    warnings: List[str] = []
    eq = {c: getattr(req.pcu, c) for c in CLASSES}

    mixed: Dict[str, List[float]] = {}
    weighted: Dict[str, List[float]] = {}
    for gid, mc in req.counts.items():
        per_class = {c: _series(mc, n, gid, c) for c in CLASSES}
        mixed[gid] = [
            sum(per_class[c][i] for c in CLASSES) for i in range(n)
        ]
        weighted[gid] = [
            sum(per_class[c][i] * eq[c] for c in CLASSES) for i in range(n)
        ]

    if not mixed:
        raise ValueError("Sin conteos: agrega al menos un grupo de carriles.")

    totals = [sum(mixed[g][i] for g in mixed) for i in range(n)]

    if n >= 4:
        k = max(range(n - 3), key=lambda i: sum(totals[i:i + 4]))
        window = list(range(k, k + 4))
        expansion = 1.0
        expanded = False
        peak_label = f"{req.interval_labels[k]}–{_end_label(req.interval_labels, k)}"

        v_hour_total = sum(totals[i] for i in window)
        v15_max = max(totals[i] for i in window)
        phf = round(v_hour_total / (4.0 * v15_max), 2) if v15_max > 0 else None
        if phf is not None and phf < PHF_MIN:
            warnings.append(
                f"PHF calculado = {phf:.2f} (pico muy concentrado); se acota "
                f"a {PHF_MIN:.2f}, el mínimo del modelo."
            )
            phf = PHF_MIN
    else:
        window = list(range(n))
        expansion = 4.0 / n
        expanded = True
        phf = None
        peak_label = f"expansión de {n} intervalo(s) de 15 min"
        warnings.append(
            f"Solo {n} intervalo(s): volumen horario por expansión simple "
            f"×{expansion:.2f}. Mayor incertidumbre — usa un CV alto en el "
            "análisis Monte Carlo. El PHF no se puede calcular: se conserva "
            "el configurado."
        )

    volumes: Dict[str, float] = {}
    pcu_factors: Dict[str, float] = {}
    for gid in mixed:
        v_mixed = sum(mixed[gid][i] for i in window) * expansion
        v_weighted = sum(weighted[gid][i] for i in window) * expansion
        volumes[gid] = round(v_mixed, 1)
        if v_mixed > 0:
            pcu = v_weighted / v_mixed
            if pcu < PCU_MIN or pcu > PCU_MAX:
                warnings.append(
                    f"Grupo '{gid}': PCU calculado {pcu:.2f} fuera del rango "
                    f"del modelo [{PCU_MIN}, {PCU_MAX}]; se acota."
                )
                pcu = min(PCU_MAX, max(PCU_MIN, pcu))
            pcu_factors[gid] = round(pcu, 2)
        else:
            pcu_factors[gid] = 1.0

    return FieldCountResult(
        peak_hour_label=peak_label,
        expanded=expanded,
        phf=phf,
        volumes=volumes,
        pcu_factors=pcu_factors,
        totals_per_interval=[round(t, 1) for t in totals],
        warnings=warnings,
    )
