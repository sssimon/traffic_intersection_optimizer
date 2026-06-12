"""API REST — Traffic Intersection Optimizer."""
from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .analysis import analyze
from .data import sample_intersection
from .alternatives import compare_controls
from .models import (
    CompareControlsRequest,
    CompareControlsResult,
    IntersectionAnalysis,
    IntersectionConfig,
    ScenarioComparison,
    ScenarioRequest,
    SignalPlan,
    SimulationRequest,
    SimulationResult,
    TWSCAnalysis,
    TWSCRequest,
)
from .optimizer import optimize
from .optimizer_delay import optimize_delay
from .scenarios import compare
from .simulator import simulate
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
) -> IntersectionAnalysis:
    """Optimiza (según método) + analiza con HCM (demora, cola, LOS)."""
    return analyze(cfg, _plan_for(cfg, method))


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
