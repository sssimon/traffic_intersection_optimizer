"""Informe profesional de 1 clic (tarea 5.1, F5).

Productiza el pipeline HTML→PDF que antes era semi-manual (`docs/build-pdf.py`
sobre un HTML escrito a mano): genera un informe técnico completo en español,
**autocontenido** (CSS y figuras SVG embebidas, sin archivos externos) y listo
para imprimir a PDF desde el navegador, a partir de cualquier
`IntersectionConfig`.

El informe no solo reporta el análisis HCM: incluye los dos pilares
diferenciadores del proyecto que ningún software del mercado integra —
**incertidumbre P(LOS)** (Monte Carlo) y **anexo de auditoría** (cada número
con su fórmula, sustitución y edición citada). El motor calcula todo
(optimización + análisis + incertidumbre + traza); este módulo solo arma la
presentación.

El resultado es un único string HTML. El frontend lo abre en una pestaña con
una barra (solo en pantalla) para «Imprimir / Guardar como PDF».
"""
from __future__ import annotations

import html
from datetime import date
from typing import List, Optional

from .analysis import _los_from_delay, analyze
from .audit import build_audit
from .models import (
    IntersectionConfig,
    IntersectionAnalysis,
    MovementType,
    SignalPlan,
    UncertaintyRequest,
)
from .optimizer import optimize
from .optimizer_delay import optimize_delay
from .uncertainty import run_uncertainty

LOS_COLOR = {
    "A": "#2e7d32", "B": "#689f38", "C": "#f9a825",
    "D": "#ef6c00", "E": "#c62828", "F": "#4a0000",
}
LOS_TEXT = {
    "A": "excelente", "B": "muy bueno", "C": "aceptable",
    "D": "límite", "E": "deficiente", "F": "colapso",
}
_MOV_ES = {
    MovementType.LEFT: "Giro izquierda",
    MovementType.THROUGH: "Directo",
    MovementType.RIGHT: "Giro derecha",
}
_MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _es(x: float, dec: int = 1) -> str:
    """Número en formato español: coma decimal y separador de millares U+00A0
    (espacio de no separación, para que el número no se parta de línea)."""
    s = f"{x:,.{dec}f}"
    return s.replace(",", " ").replace(".", ",")


def _esc(s: str) -> str:
    return html.escape(str(s))


def _badge(los: str) -> str:
    return f'<span class="badge {los}">{los}</span>'


def _today_es() -> str:
    t = date.today()
    return f"{t.day} de {_MESES[t.month - 1]} de {t.year}"


def _plan_for(cfg: IntersectionConfig, method: str) -> SignalPlan:
    return optimize_delay(cfg) if method == "delay_min" else optimize(cfg)


# --------------------------------------------------------------------------
# Figuras SVG embebidas
# --------------------------------------------------------------------------

def _svg_hbars(
    rows: List[tuple], unit: str, *, dec: int = 0, width: int = 660,
    row_h: int = 24, pad_l: int = 96,
) -> str:
    """Barras horizontales: rows = [(etiqueta, valor, color), …]."""
    if not rows:
        return ""
    pad_r, pad_t, pad_b = 86, 8, 8
    n = len(rows)
    h = pad_t + pad_b + n * row_h
    plot_w = width - pad_l - pad_r
    maxv = max((v for _, v, *_ in rows), default=1) or 1
    parts = [
        f'<svg viewBox="0 0 {width} {h}" style="width:100%;height:auto" '
        'xmlns="http://www.w3.org/2000/svg" font-family="Inter Tight,Segoe UI,Arial,sans-serif">'
    ]
    for i, (label, value, *rest) in enumerate(rows):
        color = rest[0] if rest else "#8a0f1c"
        y = pad_t + i * row_h
        bw = max(1.0, (value / maxv) * plot_w)
        cy = y + row_h / 2 + 3
        parts.append(
            f'<text x="{pad_l - 6}" y="{cy:.0f}" text-anchor="end" font-size="9.5" '
            f'font-family="JetBrains Mono,monospace">{_esc(label)}</text>'
        )
        parts.append(
            f'<rect x="{pad_l}" y="{y + 4}" width="{bw:.1f}" height="{row_h - 9}" '
            f'fill="{color}"/>'
        )
        parts.append(
            f'<text x="{pad_l + bw + 5:.1f}" y="{cy:.0f}" font-size="9" '
            f'fill="#444" font-family="JetBrains Mono,monospace">{_es(value, dec)} {unit}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _svg_plos(los_prob: dict) -> str:
    """Distribución P(LOS): barras verticales A–F."""
    letters = "ABCDEF"
    width, height = 460, 200
    pad_l, pad_r, pad_t, pad_b = 30, 12, 14, 28
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    bw = plot_w / len(letters)
    maxp = max((los_prob.get(c, 0.0) for c in letters), default=1.0) or 1.0
    parts = [
        f'<svg viewBox="0 0 {width} {height}" style="width:100%;max-width:460px;height:auto" '
        'xmlns="http://www.w3.org/2000/svg" font-family="Inter Tight,Segoe UI,Arial,sans-serif">'
    ]
    parts.append(
        f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{width - pad_r}" '
        f'y2="{pad_t + plot_h}" stroke="#0a0a0a" stroke-width="1"/>'
    )
    for i, c in enumerate(letters):
        p = los_prob.get(c, 0.0)
        bh = (p / maxp) * plot_h
        x = pad_l + i * bw + bw * 0.18
        w = bw * 0.64
        y = pad_t + plot_h - bh
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{bh:.1f}" fill="{LOS_COLOR[c]}"/>')
        parts.append(
            f'<text x="{x + w / 2:.1f}" y="{pad_t + plot_h + 14:.0f}" text-anchor="middle" '
            f'font-size="10" font-weight="600">{c}</text>'
        )
        if p > 0.005:
            parts.append(
                f'<text x="{x + w / 2:.1f}" y="{y - 4:.1f}" text-anchor="middle" '
                f'font-size="8.5" fill="#444" font-family="JetBrains Mono,monospace">{p * 100:.0f}%</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------
# Secciones
# --------------------------------------------------------------------------

def _cover(cfg: IntersectionConfig, plan: SignalPlan, method: str,
           author: Optional[str], study_date: Optional[str]) -> str:
    coords = (
        f"{_es(cfg.latitude, 6)}, {_es(cfg.longitude, 6)}"
        if cfg.latitude is not None and cfg.longitude is not None
        else "No especificadas"
    )
    method_txt = (
        "Minimización directa de demora HCM"
        if method == "delay_min" else "Webster (1958)"
    )
    rows = [
        ("Intersección", f"{_esc(cfg.name)} ({len(cfg.approaches)} accesos)"),
        ("Coordenadas", coords),
        ("Optimizador", method_txt),
        ("Métodos aplicados", "HCM 2010 cap. 18 · Monte Carlo P(LOS) · auditoría trazable"),
        ("Herramienta", "Traffic Intersection Optimizer"),
    ]
    if study_date:
        rows.insert(2, ("Fecha del estudio", _esc(study_date)))
    if author:
        rows.append(("Responsable", _esc(author)))
    rows.append(("Fecha del informe", _today_es()))
    meta = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return (
        '<div class="cover">'
        '<div class="kicker">Vialidad y Transporte · Informe técnico</div>'
        '<h1 class="title">Análisis y optimización<br>semafórica de intersección</h1>'
        f'<p class="sub">{_esc(cfg.name)}</p>'
        '<div class="rule"></div>'
        f'<table class="meta">{meta}</table>'
        '<div class="foot">Informe generado automáticamente por el motor de '
        'análisis. Todas las cifras son reproducibles cargando la misma '
        'configuración y ejecutando «Optimizar y analizar».</div>'
        "</div>"
    )


def _exec_summary(cfg: IntersectionConfig, an: IntersectionAnalysis,
                  plan: SignalPlan) -> str:
    worst = sorted(an.movements, key=lambda m: m.avg_delay_s, reverse=True)
    los_f = [m.lane_group_id for m in an.movements if m.los.value == "F"]
    crit = worst[0] if worst else None
    los = an.overall_los.value

    narr = (
        f"La intersección <strong>{_esc(cfg.name)}</strong> opera con un "
        f"<strong>nivel de servicio global {los}</strong> "
        f"({LOS_TEXT[los]}), una demora media de "
        f"<strong>{_es(an.avg_delay_s)} s/veh</strong> y una saturación "
        f"máxima de <strong>v/c = {_es(an.overall_v_c, 2)}</strong>."
    )
    if crit:
        narr += (
            f" El movimiento crítico es <code>{_esc(crit.lane_group_id)}</code> "
            f"con {_es(crit.avg_delay_s)} s/veh (LOS {crit.los.value})."
        )
    if los_f:
        grupos = ", ".join(f"<code>{_esc(g)}</code>" for g in los_f)
        narr += (
            f" <strong>{len(los_f)} movimiento(s) en nivel de servicio F</strong> "
            f"({grupos}) constituyen el cuello de botella operativo."
        )

    kpis = (
        '<div class="kpis">'
        f'<div class="kpi"><div class="l">Demora media</div><div class="v">{_es(an.avg_delay_s)}</div><div class="u">s / veh</div></div>'
        f'<div class="kpi"><div class="l">LOS global</div><div class="v">{_badge(los)}</div><div class="u">{LOS_TEXT[los]}</div></div>'
        f'<div class="kpi"><div class="l">Saturación v/c</div><div class="v">{_es(an.overall_v_c, 2)}</div><div class="u">máximo</div></div>'
        f'<div class="kpi"><div class="l">Ciclo óptimo</div><div class="v">{_es(plan.cycle_length, 0)}</div><div class="u">segundos</div></div>'
        "</div>"
    )
    return f"<h1>1. Resumen ejecutivo</h1>{kpis}<p>{narr}</p>"


def _description(cfg: IntersectionConfig) -> str:
    rows = []
    for ap in cfg.approaches:
        for lg in ap.lane_groups:
            rows.append(
                f"<tr><td>{_esc(ap.name)}</td><td><code>{_esc(lg.id)}</code></td>"
                f"<td>{_MOV_ES.get(lg.movement, lg.movement.value)}</td>"
                f'<td class="r">{lg.lanes}</td>'
                f'<td class="r">{_es(lg.saturation_flow_per_lane, 0)}</td></tr>'
            )
    groups = (
        '<table><thead><tr><th>Acceso</th><th>Grupo</th><th>Movimiento</th>'
        '<th class="r">Carriles</th><th class="r">Sat. base (veh/h/carril)</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )

    ph_rows = []
    for ph in cfg.phases:
        ids = ", ".join(f"<code>{_esc(g)}</code>" for g in ph.lane_group_ids)
        ph_rows.append(
            f"<tr><td><code>{_esc(ph.id)}</code></td><td>{_esc(ph.name)}</td>"
            f'<td>{ids}</td><td class="r">{_es(ph.min_green, 0)} s</td>'
            f'<td class="r">{_es(ph.max_green, 0)} s</td>'
            f'<td class="r">{_es(ph.yellow, 0)} s</td>'
            f'<td class="r">{_es(ph.all_red, 0)} s</td></tr>'
        )
    phases = (
        '<h2>Esquema de fases</h2><table><thead><tr><th>Fase</th><th>Nombre</th>'
        '<th>Grupos con verde</th><th class="r">V. mín.</th><th class="r">V. máx.</th>'
        '<th class="r">Amarillo</th><th class="r">Todo-rojo</th></tr></thead>'
        f"<tbody>{''.join(ph_rows)}</tbody></table>"
    )
    intro = (
        f"<h1>2. Descripción de la intersección</h1><p>Intersección de "
        f"{len(cfg.approaches)} accesos semaforizados con "
        f"{sum(len(a.lane_groups) for a in cfg.approaches)} grupos de carriles. "
        f"El factor de hora pico (PHF) aplicado es {_es(cfg.peak_hour_factor, 2)}.</p>"
    )
    return intro + groups + phases


def _methodology() -> str:
    return (
        "<h1>3. Metodología</h1><ul>"
        "<li><strong>Optimización de tiempos.</strong> Ciclo y reparto de verde "
        "por minimización directa de la demora HCM (o Webster), sobre los flujos "
        "críticos de cada fase.</li>"
        "<li><strong>Análisis HCM 2010 (cap. 18).</strong> Demora media por "
        "movimiento <code>d = d1·PF + d2</code>, capacidad, grado de saturación "
        "v/c, cola (back of queue, percentil 95) y nivel de servicio (LOS A–F).</li>"
        "<li><strong>Incertidumbre (Monte Carlo).</strong> Propagación de la "
        "variabilidad del aforo sobre los volúmenes para obtener la probabilidad "
        "de cada LOS, no una sola letra determinista.</li>"
        "<li><strong>Auditoría trazable.</strong> Cada número del análisis se "
        "acompaña de su fórmula, sustitución numérica y la edición del manual "
        "citada (anexo).</li>"
        "</ul>"
        '<div class="box">La demanda de diseño que utiliza el modelo es '
        "<code>demanda = conteo × PCU ÷ PHF</code>. Los vehículos pesados se "
        "modelan vía el factor PCU en la demanda (equivalente al fHV del HCM).</div>"
    )


def _signal_plan(cfg: IntersectionConfig, plan: SignalPlan, method: str) -> str:
    method_txt = "minimización de demora HCM" if method == "delay_min" else "Webster"
    rows = []
    for ph in cfg.phases:
        g = plan.phase_green.get(ph.id, 0.0)
        y = plan.phase_yellow.get(ph.id, ph.yellow)
        ar = plan.phase_all_red.get(ph.id, ph.all_red)
        rows.append(
            f"<tr><td><code>{_esc(ph.id)}</code> {_esc(ph.name)}</td>"
            f'<td class="r">{_es(g)} s</td><td class="r">{_es(y, 0)} s</td>'
            f'<td class="r">{_es(ar, 0)} s</td></tr>'
        )
    notes = "".join(f"<li>{_esc(n)}</li>" for n in plan.notes)
    notes_html = f"<ul>{notes}</ul>" if notes else ""
    return (
        f"<h1>4. Plan semafórico óptimo ({method_txt})</h1>"
        f"<p>Ciclo óptimo de <strong>{_es(plan.cycle_length, 0)} segundos</strong> "
        f"con un tiempo perdido total de {_es(plan.total_lost_time, 0)} s por ciclo.</p>"
        '<table><thead><tr><th>Fase</th><th class="r">Verde efectivo</th>'
        '<th class="r">Amarillo</th><th class="r">Todo-rojo</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>{notes_html}"
    )


def _demand(cfg: IntersectionConfig) -> str:
    items = []
    for ap in cfg.approaches:
        for lg in ap.lane_groups:
            v = cfg.demand_for(lg.id)
            if v > 0:
                items.append((lg.id, v))
    items.sort(key=lambda t: t[1], reverse=True)
    rows = [(lid, round(v), "#8a0f1c") for lid, v in items]
    fig = _svg_hbars(rows, "veh/h")
    total = sum(v for _, v in items)
    return (
        "<h1>5. Flujos de demanda de diseño</h1>"
        f"<p>Demanda total entrante: <strong>{_es(total, 0)} veh/h</strong> "
        "(conteo × PCU ÷ PHF). Por grupo de carriles, ordenada de mayor a menor:</p>"
        f'<div class="fig">{fig}</div>'
        '<p class="caption">Figura 1 — Demanda de diseño por movimiento (veh/h)</p>'
    )


def _hcm_analysis(an: IntersectionAnalysis) -> str:
    rows = []
    for m in an.movements:
        rows.append(
            f"<tr><td><code>{_esc(m.lane_group_id)}</code></td><td>{_esc(m.phase_id)}</td>"
            f'<td class="r">{_es(m.demand, 0)}</td><td class="r">{_es(m.capacity, 0)}</td>'
            f'<td class="r">{_es(m.v_c_ratio, 2)}</td><td class="r">{_es(m.avg_delay_s)}</td>'
            f'<td class="r">{_es(m.queue_95th_veh)}</td>'
            f'<td class="c">{_badge(m.los.value)}</td></tr>'
        )
    table = (
        '<table><thead><tr><th>Grupo</th><th>Fase</th><th class="r">Demanda</th>'
        '<th class="r">Capacidad</th><th class="r">v/c</th><th class="r">Demora (s)</th>'
        '<th class="r">Cola 95% (veh)</th><th class="c">LOS</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    fig_rows = [
        (m.lane_group_id, round(m.avg_delay_s, 1), LOS_COLOR[m.los.value])
        for m in sorted(an.movements, key=lambda x: x.avg_delay_s, reverse=True)
    ]
    fig = _svg_hbars(fig_rows, "s/veh", dec=1)
    warn = "".join(f'<div class="box">{_esc(w)}</div>' for w in an.warnings)
    return (
        "<h1>6. Análisis de capacidad y nivel de servicio (HCM 2010)</h1>"
        f"{table}"
        f"<p><strong>Resultado global:</strong> demora media "
        f"{_es(an.avg_delay_s)} s/veh, nivel de servicio {_badge(an.overall_los.value)} "
        f"y saturación máxima v/c = {_es(an.overall_v_c, 2)}.</p>"
        f"{warn}"
        f'<div class="fig">{fig}</div>'
        '<p class="caption">Figura 2 — Demora por movimiento (color = nivel de servicio)</p>'
    )


def _uncertainty(cfg: IntersectionConfig, an: IntersectionAnalysis,
                 method: str, volume_cv: float, samples: int) -> str:
    res = run_uncertainty(UncertaintyRequest(
        config=cfg, volume_cv=volume_cv, samples=samples, method=method,
    ))
    fig = _svg_plos(res.los_probability)
    det = an.overall_los.value
    p_det = res.los_probability.get(det, 0.0)
    ranked = sorted(res.los_probability.items(), key=lambda t: t[1], reverse=True)
    likely = ranked[0][0] if ranked else det

    rows = "".join(
        f'<tr><td class="c">{_badge(c)}</td><td class="r">{p * 100:.0f}%</td></tr>'
        for c, p in res.los_probability.items() if p > 0.0
    )
    narr = (
        f"Con un coeficiente de variación del aforo de "
        f"<strong>{volume_cv * 100:.0f}%</strong> y {_es(res.samples, 0)} "
        f"muestras Monte Carlo, el LOS determinista <strong>{det}</strong> tiene "
        f"una probabilidad de <strong>{p_det * 100:.0f}%</strong>; el más "
        f"probable es <strong>{likely}</strong>. La probabilidad de "
        f"sobresaturación (v/c &gt; 1) del movimiento crítico es "
        f"<strong>{res.prob_oversaturated * 100:.0f}%</strong>. La banda de "
        f"demora va de {_es(res.delay_p05_s)} a {_es(res.delay_p95_s)} s/veh "
        f"(p05–p95, mediana {_es(res.delay_p50_s)})."
    )
    return (
        "<h1>7. Incertidumbre — probabilidad de nivel de servicio</h1>"
        "<p>Un aforo corto no justifica una letra de LOS única. Propagando la "
        "incertidumbre de los volúmenes se obtiene la <strong>probabilidad de "
        "cada LOS</strong>, un resultado que ningún software comercial ofrece.</p>"
        f"<p>{narr}</p>"
        f'<div class="cols"><div class="fig">{fig}</div>'
        f'<table class="tight"><thead><tr><th class="c">LOS</th>'
        f'<th class="r">Probabilidad</th></tr></thead><tbody>{rows}</tbody></table></div>'
        '<p class="caption">Figura 3 — Distribución de probabilidad del nivel de servicio</p>'
    )


def _audit_annex(cfg: IntersectionConfig, plan: SignalPlan) -> str:
    audits = build_audit(cfg, plan)
    blocks = []
    for ma in audits:
        steps = "".join(
            f"<tr><td>{_esc(s.concept)}</td><td><code>{_esc(s.formula)}</code></td>"
            f"<td><code>{_esc(s.substitution)}</code></td>"
            f'<td class="r">{_es(s.value, 2)}</td><td>{_esc(s.units)}</td>'
            f'<td><small>{_esc(s.source)}</small></td></tr>'
            for s in ma.steps
        )
        blocks.append(
            f"<h2>Movimiento <code>{_esc(ma.lane_group_id)}</code> "
            f"(fase <code>{_esc(ma.phase_id)}</code>)</h2>"
            '<table class="audit"><thead><tr><th>Concepto</th><th>Fórmula</th>'
            '<th>Sustitución</th><th class="r">Valor</th><th>Unidades</th>'
            f"<th>Fuente</th></tr></thead><tbody>{steps}</tbody></table>"
        )
    return (
        '<h1 class="annex">Anexo A — Traza de auditoría del cálculo</h1>'
        "<p>Cada número del análisis con su fórmula, sustitución numérica y la "
        "edición del manual citada, para verificación independiente con una "
        "calculadora.</p>" + "".join(blocks)
    )


def _conclusions(cfg: IntersectionConfig, an: IntersectionAnalysis) -> str:
    los = an.overall_los.value
    los_f = [m.lane_group_id for m in an.movements if m.los.value == "F"]
    items = [
        f"La intersección opera en nivel de servicio global <strong>{los}</strong> "
        f"({LOS_TEXT[los]}) con demora media de {_es(an.avg_delay_s)} s/veh."
    ]
    if an.overall_v_c >= 0.95:
        items.append(
            f"La saturación máxima (v/c = {_es(an.overall_v_c, 2)}) deja "
            "<strong>muy poco margen</strong>: un incremento moderado de demanda "
            "sobresaturaría la intersección."
        )
    elif an.overall_v_c >= 0.85:
        items.append(
            f"La saturación máxima (v/c = {_es(an.overall_v_c, 2)}) indica una "
            "operación cercana a la capacidad."
        )
    if los_f:
        grupos = ", ".join(f"<code>{_esc(g)}</code>" for g in los_f)
        items.append(
            f"Los movimientos {grupos} operan en nivel de servicio F y son el "
            "componente crítico a intervenir."
        )
    lis = "".join(f"<li>{i}</li>" for i in items)

    recs = [
        "Revisar el reparto de verde y el esquema de fases (lead/lag en los "
        "giros a la izquierda) según los movimientos críticos identificados.",
        "Si la saturación es alta, evaluar control actuado y, donde el espacio "
        "lo permita, ampliación de capacidad geométrica en los accesos críticos.",
        "Coordinar con las intersecciones contiguas (onda verde) si forman "
        "parte de un corredor.",
    ]
    rlis = "".join(f"<li>{r}</li>" for r in recs)
    return (
        "<h1>8. Conclusiones y recomendaciones</h1>"
        f"<h2>Conclusiones</h2><ul>{lis}</ul>"
        f"<h2>Recomendaciones</h2><ol>{rlis}</ol>"
    )


_CSS = """
@page { size: A4; margin: 16mm 16mm 16mm 16mm; }
* { box-sizing: border-box; }
body { font-family:'Inter Tight','Helvetica Neue','Segoe UI',Arial,sans-serif;
       font-size:10.5pt; line-height:1.5; color:#0a0a0a; margin:0; background:#fff; }
h1 { font-size:15.5pt; font-weight:700; margin:22px 0 8px;
     border-bottom:1px solid #0a0a0a; padding-bottom:3px; page-break-after:avoid; }
h1.annex { page-break-before:always; }
h2 { font-size:11.5pt; font-weight:600; color:#8a0f1c; margin:14px 0 6px;
     page-break-after:avoid; }
p { margin:6px 0; text-align:justify; }
strong { font-weight:700; } small { color:#7a7a7a; }
table { border-collapse:collapse; width:100%; margin:8px 0; font-size:9pt;
        page-break-inside:avoid; }
th { background:#0a0a0a; color:#fff; text-align:left; padding:5px 7px;
     font-size:8pt; text-transform:uppercase; letter-spacing:0.4px; }
td { border:1px solid #d0d0d0; padding:4px 7px; }
td.r, th.r { text-align:right; } td.c, th.c { text-align:center; }
tbody tr:nth-child(even) td { background:#f6f6f6; }
table.audit { font-size:8pt; } table.audit td { padding:3px 6px; }
table.tight { width:auto; min-width:200px; }
code { font-family:'JetBrains Mono',Consolas,monospace; font-size:9pt;
       background:#f0f0f0; padding:1px 4px; }
ul,ol { margin:6px 0; padding-left:22px; } li { margin:3px 0; }
.fig { margin:10px 0 4px; page-break-inside:avoid; }
.cols { display:flex; gap:18px; align-items:flex-start; flex-wrap:wrap; }
.cols .fig { flex:1; min-width:280px; }
.caption { text-align:center; font-size:8.5pt; color:#7a7a7a; margin:0 0 12px;
           text-transform:uppercase; letter-spacing:1px; }
.cover { page-break-after:always; padding-top:46mm; }
.cover .kicker { font-size:10pt; letter-spacing:3px; text-transform:uppercase;
                 color:#8a0f1c; font-weight:600; }
.cover h1.title { font-size:30pt; font-weight:700; border:none; margin:8px 0 4px;
                  letter-spacing:-1px; line-height:1.1; }
.cover .sub { font-size:14pt; font-weight:400; margin:0 0 22px; }
.cover .rule { height:4px; background:#8a0f1c; width:120px; margin:18px 0 26px; }
.meta { width:100%; font-size:10pt; }
.meta td { border:none; border-bottom:1px solid #e0e0e0; padding:7px 4px; }
.meta td:first-child { color:#7a7a7a; text-transform:uppercase; font-size:8.5pt;
                       letter-spacing:1px; width:42%; }
.meta td:last-child { font-weight:600; }
.badge { display:inline-block; min-width:22px; padding:1px 6px; text-align:center;
         color:#fff; font-weight:700; font-size:9pt; }
.A{background:#2e7d32}.B{background:#689f38}.C{background:#f9a825}
.D{background:#ef6c00}.E{background:#c62828}.F{background:#4a0000}
.kpis { display:flex; gap:10px; margin:12px 0; }
.kpi { flex:1; border:1px solid #0a0a0a; padding:9px 11px; }
.kpi .l { font-size:7.5pt; text-transform:uppercase; letter-spacing:1px; color:#7a7a7a; }
.kpi .v { font-size:19pt; font-weight:700; line-height:1.1; }
.kpi .u { font-size:8pt; color:#7a7a7a; }
.box { border-left:3px solid #8a0f1c; background:#faf2f2; padding:8px 12px;
       margin:10px 0; font-size:10pt; page-break-inside:avoid; }
.foot { margin-top:26px; padding-top:8px; border-top:1px solid #d0d0d0;
        font-size:8pt; color:#9a9a9a; }
.toolbar { position:sticky; top:0; background:#0a0a0a; color:#fff; padding:10px 16px;
           display:flex; align-items:center; gap:14px; font-size:11pt; z-index:10; }
.toolbar button { background:#8a0f1c; color:#fff; border:none; padding:8px 16px;
                  font-size:11pt; font-weight:600; cursor:pointer; font-family:inherit; }
.toolbar span { color:#bbb; font-size:9.5pt; }
.page { max-width:200mm; margin:0 auto; padding:0 10mm 20mm; }
@media print { .toolbar { display:none; } .page { max-width:none; margin:0; padding:0; } }
"""

_TOOLBAR = (
    '<div class="toolbar">'
    '<button onclick="window.print()">Imprimir / Guardar como PDF</button>'
    "<span>Usa «Guardar como PDF» en el destino de impresión. Esta barra no "
    "aparece en el documento.</span></div>"
)


def build_report_html(
    cfg: IntersectionConfig, *, method: str = "delay_min", volume_cv: float = 0.10,
    samples: int = 2000, include_uncertainty: bool = True,
    include_audit: bool = True, author: Optional[str] = None,
    study_date: Optional[str] = None,
) -> str:
    """Construye el informe técnico completo como un único HTML autocontenido."""
    if not cfg.approaches:
        raise ValueError("El informe requiere una intersección con accesos.")
    if not cfg.phases:
        raise ValueError(
            "El informe requiere una intersección semaforizada con fases."
        )

    plan = _plan_for(cfg, method)
    an = analyze(cfg, plan)

    sections = [
        _cover(cfg, plan, method, author, study_date),
        _exec_summary(cfg, an, plan),
        _description(cfg),
        _methodology(),
        _signal_plan(cfg, plan, method),
        _demand(cfg),
        _hcm_analysis(an),
    ]
    if include_uncertainty:
        try:
            sections.append(_uncertainty(cfg, an, method, volume_cv, samples))
        except Exception:  # noqa: BLE001 — el informe no debe caerse por el MC
            pass
    sections.append(_conclusions(cfg, an))
    if include_audit:
        sections.append(_audit_annex(cfg, plan))

    footer = (
        '<div class="foot">Traffic Intersection Optimizer — HCM 2010 cap. 18 · '
        "Monte Carlo P(LOS) · auditoría trazable. Informe generado "
        f"automáticamente el {_today_es()}. Cifras reproducibles desde la "
        "configuración cargada.</div>"
    )
    body = _TOOLBAR + '<div class="page">' + "".join(sections) + footer + "</div>"
    return (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        f"<title>Informe — {_esc(cfg.name)}</title><style>{_CSS}</style></head>"
        f"<body>{body}</body></html>"
    )
