"""API REST — Traffic Intersection Optimizer."""
from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .analysis import analyze
from .data import sample_intersection
from .alternatives import compare_controls
from .audit import build_audit
from .corridor import process_corridor
from .field_count import process_field_count
from .models import (
    CompareControlsRequest,
    CompareControlsResult,
    CorridorRequest,
    CorridorResult,
    FieldCountRequest,
    FieldCountResult,
    IntersectionAnalysis,
    IntersectionConfig,
    OsmImportRequest,
    OsmImportResult,
    ReportRequest,
    RunDetail,
    RunSummary,
    SaveRunRequest,
    ScenarioComparison,
    ScenarioRequest,
    SignalPlan,
    SimulationRequest,
    SimulationResult,
    SumoExportRequest,
    SumoExportResult,
    TWSCAnalysis,
    TWSCRequest,
    UncertaintyRequest,
    UncertaintyResult,
)
from .optimizer import optimize
from .optimizer_delay import optimize_delay
from .osm import build_config_from_elements, fetch_overpass
from .reports import build_report_html
from .scenarios import compare
from .simulator import simulate
from .storage import delete_run, get_run, list_runs, save_run
from .sumo_bridge import process_sumo_export
from .uncertainty import run_uncertainty
from .unsignalized import analyze_twsc

OptimizeMethod = Literal["webster", "delay_min"]

app = FastAPI(
    title="Traffic Intersection Optimizer",
    description=(
        "Optimización de tiempos de semáforo (Webster y minimización directa "
        "de demora HCM), análisis de capacidad (HCM 2010), simulación de "
        "colas y comparación de escenarios."
    ),
    version="0.1.0",
)


def _plan_for(cfg: IntersectionConfig, method: OptimizeMethod) -> SignalPlan:
    return optimize_delay(cfg) if method == "delay_min" else optimize(cfg)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/sample", response_model=IntersectionConfig)
def get_sample() -> IntersectionConfig:
    """Devuelve una configuración de ejemplo (intersección 4×4 congestionada)."""
    return sample_intersection()


@app.post("/api/optimize", response_model=SignalPlan)
def post_optimize(
    cfg: IntersectionConfig,
    method: OptimizeMethod = Query(
        "webster", description="Optimizador: 'webster' o 'delay_min'."
    ),
) -> SignalPlan:
    """Plan de tiempos: Webster (1958) o minimización directa de demora HCM."""
    try:
        return _plan_for(cfg, method)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/analyze", response_model=IntersectionAnalysis)
def post_analyze(
    cfg: IntersectionConfig,
    method: OptimizeMethod = Query(
        "webster", description="Optimizador: 'webster' o 'delay_min'."
    ),
    audit: bool = Query(
        False,
        description="Modo auditoría: incluye la traza de cálculo por movimiento.",
    ),
) -> IntersectionAnalysis:
    """Optimiza (según método) + analiza con HCM (demora, cola, LOS)."""
    plan = _plan_for(cfg, method)
    analysis = analyze(cfg, plan)
    if audit:
        analysis.audit = build_audit(cfg, plan)
    return analysis


@app.post("/api/simulate", response_model=SimulationResult)
def post_simulate(req: SimulationRequest) -> SimulationResult:
    """Simulación de colas (tiempo discreto) con el plan dado (o el optimizado)."""
    return simulate(req)


@app.post("/api/scenarios", response_model=ScenarioComparison)
def post_scenarios(req: ScenarioRequest) -> ScenarioComparison:
    """Compara escenarios de demanda y recomienda estrategia de gestión."""
    return compare(req)


@app.post("/api/analyze-twsc", response_model=TWSCAnalysis)
def post_analyze_twsc(req: TWSCRequest) -> TWSCAnalysis:
    """Análisis no semaforizado con PARE en la calle secundaria (HCM cap. 19)."""
    return analyze_twsc(req.config, req.major_approach_ids)


@app.post("/api/compare-controls", response_model=CompareControlsResult)
def post_compare_controls(req: CompareControlsRequest) -> CompareControlsResult:
    """Explorador de alternativas: rankea semáforo (fases configuradas y por
    acceso) vs PARE con la misma demanda."""
    return compare_controls(req)


@app.post("/api/uncertainty", response_model=UncertaintyResult)
def post_uncertainty(req: UncertaintyRequest) -> UncertaintyResult:
    """Monte Carlo de incertidumbre del aforo: P(LOS), banda de demora y
    tornado de sensibilidad."""
    return run_uncertainty(req)


@app.post("/api/corridor", response_model=CorridorResult)
def post_corridor(req: CorridorRequest) -> CorridorResult:
    """Coordinación de corredor: offsets, banda verde bidireccional y PF."""
    try:
        return process_corridor(req)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/field-count", response_model=FieldCountResult)
def post_field_count(req: FieldCountRequest) -> FieldCountResult:
    """Procesa el aforo de 15 min: hora pico, PHF y PCU por movimiento."""
    try:
        return process_field_count(req)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/sumo-export", response_model=SumoExportResult)
def post_sumo_export(req: SumoExportRequest) -> SumoExportResult:
    """Exporta el modelo a SUMO y, si está instalado, corre réplicas headless
    para comparar la demora analítica (HCM) con la microsimulada."""
    try:
        return process_sumo_export(req)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/report", response_class=HTMLResponse)
def post_report(req: ReportRequest) -> HTMLResponse:
    """Informe técnico profesional de 1 clic (HTML autocontenido, listo para
    imprimir a PDF): análisis HCM + P(LOS) + anexo de auditoría."""
    try:
        html = build_report_html(
            req.config,
            method=req.method,
            volume_cv=req.volume_cv,
            samples=req.samples,
            include_uncertainty=req.include_uncertainty,
            include_audit=req.include_audit,
            author=req.author,
            study_date=req.study_date,
        )
        return HTMLResponse(content=html)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/osm-import", response_model=OsmImportResult)
def post_osm_import(req: OsmImportRequest) -> OsmImportResult:
    """Importa la geometría del cruce más cercano al pin desde OpenStreetMap."""
    try:
        elements = fetch_overpass(req.latitude, req.longitude, req.radius_m)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "No se pudo consultar Overpass/OSM (red o límite de uso). "
                "Intenta de nuevo en unos segundos."
            ),
        ) from exc
    try:
        cfg, warnings = build_config_from_elements(
            elements, req.latitude, req.longitude
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OsmImportResult(config=cfg, warnings=warnings)


@app.post("/api/runs", response_model=RunSummary)
def post_run(req: SaveRunRequest) -> RunSummary:
    """Guarda la corrida: configuración + resumen del análisis."""
    return save_run(req)


@app.get("/api/runs", response_model=list[RunSummary])
def get_runs() -> list[RunSummary]:
    """Corridas guardadas (la más reciente primero) — comparables entre sí."""
    return list_runs()


@app.get("/api/runs/{run_id}", response_model=RunDetail)
def get_run_detail(run_id: int) -> RunDetail:
    """Corrida completa (incluye la configuración para recargarla)."""
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No existe la corrida {run_id}.")
    return run


@app.delete("/api/runs/{run_id}")
def remove_run(run_id: int) -> dict:
    """Elimina una corrida guardada."""
    if not delete_run(run_id):
        raise HTTPException(status_code=404, detail=f"No existe la corrida {run_id}.")
    return {"ok": True}
