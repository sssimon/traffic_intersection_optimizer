"""API REST — Traffic Intersection Optimizer."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .analysis import analyze
from .data import sample_intersection
from .models import (
    IntersectionAnalysis,
    IntersectionConfig,
    RoundaboutAnalysis,
    RoundaboutRequest,
    ScenarioComparison,
    ScenarioRequest,
    SignalPlan,
    SimulationRequest,
    SimulationResult,
    TWSCAnalysis,
    TWSCRequest,
)
from .optimizer import optimize
from .scenarios import compare
from .simulator import simulate
from .unsignalized import analyze_roundabout, analyze_twsc

app = FastAPI(
    title="Traffic Intersection Optimizer",
    description=(
        "Optimización de tiempos de semáforo (Webster), análisis de capacidad "
        "(HCM 2010), microsimulación y comparación de escenarios."
    ),
    version="0.1.0",
)

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
def post_optimize(cfg: IntersectionConfig) -> SignalPlan:
    """Calcula ciclo y verdes óptimos (Webster) para la configuración dada."""
    try:
        return optimize(cfg)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/analyze", response_model=IntersectionAnalysis)
def post_analyze(cfg: IntersectionConfig) -> IntersectionAnalysis:
    """Optimiza + analiza con HCM (demora, cola, LOS)."""
    plan = optimize(cfg)
    return analyze(cfg, plan)


@app.post("/api/simulate", response_model=SimulationResult)
def post_simulate(req: SimulationRequest) -> SimulationResult:
    """Microsimulación discreta con el plan dado (o el optimizado)."""
    return simulate(req)


@app.post("/api/scenarios", response_model=ScenarioComparison)
def post_scenarios(req: ScenarioRequest) -> ScenarioComparison:
    """Compara escenarios de demanda y recomienda estrategia de gestión."""
    return compare(req)


@app.post("/api/analyze-twsc", response_model=TWSCAnalysis)
def post_analyze_twsc(req: TWSCRequest) -> TWSCAnalysis:
    """Análisis no semaforizado con PARE en la calle secundaria (HCM cap. 19)."""
    return analyze_twsc(req.config, req.major_approach_ids)


@app.post("/api/analyze-roundabout", response_model=RoundaboutAnalysis)
def post_analyze_roundabout(req: RoundaboutRequest) -> RoundaboutAnalysis:
    """Análisis de glorieta / rotonda (HCM 2010 cap. 21)."""
    return analyze_roundabout(
        req.config, req.approach_order, req.circulating_lanes, req.entry_lanes
    )
