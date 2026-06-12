"""Modelos de configuración para una intersección semaforizada genérica.

El sistema acepta cualquier número de accesos (approaches), cada uno con uno o
más grupos de carril (lane groups). Los movimientos se asignan a fases del
semáforo. Todas las cantidades están en unidades coherentes:

- Flujo / demanda: vehículos por hora (veh/h)
- Saturación: vehículos por hora de verde por carril (veh/h/carril)
- Tiempos: segundos
"""
from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class MovementType(str, Enum):
    LEFT = "left"
    THROUGH = "through"
    RIGHT = "right"


class LaneGroup(BaseModel):
    """Grupo de carriles que comparten línea de detención y movimiento."""
    id: str = Field(..., description="Identificador único, ej: 'N-through'")
    movement: MovementType
    lanes: int = Field(..., ge=1, le=8)
    saturation_flow_per_lane: float = Field(
        1900.0,
        description="Flujo de saturación base (veh/h/carril). Valor HCM típico: 1900.",
        ge=500.0,
        le=2200.0,
    )
    shared_with_through: bool = Field(
        False,
        description="True si el carril de giro comparte con el directo (afecta capacidad).",
    )

    @property
    def saturation_flow(self) -> float:
        """Flujo de saturación total del grupo (veh/h)."""
        factor = 0.85 if self.shared_with_through else 1.0
        return self.saturation_flow_per_lane * self.lanes * factor


class Approach(BaseModel):
    """Acceso a la intersección (ej: Norte, Sur, etc.)."""
    id: str
    name: str
    lane_groups: List[LaneGroup]

    @field_validator("lane_groups")
    @classmethod
    def at_least_one_group(cls, v: List[LaneGroup]) -> List[LaneGroup]:
        if not v:
            raise ValueError("Cada acceso debe tener al menos un grupo de carriles.")
        return v


class Phase(BaseModel):
    """Una fase del semáforo: combinación de movimientos que reciben verde."""
    id: str
    name: str
    lane_group_ids: List[str] = Field(
        ...,
        description="IDs de LaneGroup que tienen verde durante esta fase.",
        min_length=1,
    )
    min_green: float = Field(7.0, ge=4.0, description="Verde mínimo (s).")
    max_green: float = Field(60.0, ge=10.0, description="Verde máximo (s).")
    yellow: float = Field(3.0, ge=2.0, le=6.0)
    all_red: float = Field(1.0, ge=0.0, le=4.0)

    @property
    def lost_time(self) -> float:
        """Tiempo perdido por fase (s): amarillo + todo-rojo.

        El arranque perdido al inicio del verde se asume compensado por la
        extensión del verde efectivo sobre el amarillo (supuesto estándar
        l1 ≈ extensión). Para un modelo más fino habría que separar el
        arranque perdido como un parámetro propio de la fase.
        """
        return self.yellow + self.all_red


class Demand(BaseModel):
    """Volumen vehicular en un grupo de carriles (veh/h)."""
    lane_group_id: str
    volume: float = Field(..., ge=0.0, description="Demanda en veh/h.")
    pcu_factor: float = Field(
        1.0,
        ge=1.0,
        le=3.0,
        description="Factor de equivalencia vehículo ligero (pesados >1.0).",
    )

    @property
    def adjusted_volume(self) -> float:
        return self.volume * self.pcu_factor


class IntersectionConfig(BaseModel):
    """Configuración completa de una intersección."""
    name: str
    approaches: List[Approach]
    phases: List[Phase]
    demand: List[Demand]
    peak_hour_factor: float = Field(
        0.92,
        ge=0.7,
        le=1.0,
        description="PHF: factor de hora pico (HCM, 0.85–0.95 típico).",
    )
    latitude: Optional[float] = Field(
        None, ge=-90.0, le=90.0, description="Latitud de la intersección (grados)."
    )
    longitude: Optional[float] = Field(
        None, ge=-180.0, le=180.0, description="Longitud de la intersección (grados)."
    )

    def lane_group(self, lg_id: str) -> Optional[LaneGroup]:
        for ap in self.approaches:
            for lg in ap.lane_groups:
                if lg.id == lg_id:
                    return lg
        return None

    def demand_for(self, lg_id: str) -> float:
        """Demanda ajustada (PCU) para un grupo de carriles."""
        for d in self.demand:
            if d.lane_group_id == lg_id:
                return d.adjusted_volume / self.peak_hour_factor
        return 0.0


class SignalPlan(BaseModel):
    """Plan de tiempos resultante de la optimización."""
    cycle_length: float = Field(..., description="Duración del ciclo (s).")
    phase_green: dict[str, float] = Field(
        ...,
        description=(
            "Verde por fase (s). Es verde efectivo; bajo el supuesto del "
            "modelo (arranque perdido ≈ extensión del verde) se usa también "
            "como el verde visualizado en la simulación."
        ),
    )
    phase_yellow: dict[str, float]
    phase_all_red: dict[str, float]
    total_lost_time: float
    notes: List[str] = Field(default_factory=list)


# ---------- Resultados de análisis ----------

class LOSGrade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"


class MovementAnalysis(BaseModel):
    lane_group_id: str
    phase_id: str
    demand: float
    capacity: float
    v_c_ratio: float = Field(..., description="Grado de saturación X = v/c.")
    avg_delay_s: float
    back_of_queue_avg_veh: float = Field(
        ...,
        description=(
            "Cola media (back of queue) por carril, veh: Q1 + Q2 según "
            "HCM 2000 cap. 16 ap. G (estructura conservada en HCM 2010 "
            "cap. 31). Supone utilización igual entre carriles del grupo."
        ),
    )
    queue_95th_veh: float = Field(
        ...,
        description=(
            "Cola al percentil 95 (back of queue) por carril, veh: "
            "(Q1+Q2)·fB95 con fB95 = 1.6 + e^(-Q/5), controlador pretimed."
        ),
    )
    los: LOSGrade


class IntersectionAnalysis(BaseModel):
    config_name: str
    signal_plan: SignalPlan
    movements: List[MovementAnalysis]
    avg_delay_s: float
    overall_los: LOSGrade
    overall_v_c: float
    warnings: List[str] = Field(default_factory=list)


# ---------- Simulación ----------

class SimulationRequest(BaseModel):
    config: IntersectionConfig
    signal_plan: Optional[SignalPlan] = None
    duration_s: int = Field(900, ge=60, le=7200, description="Duración (s).")
    seed: int = Field(42, description="Semilla base; la réplica i usa seed + i.")
    time_step_s: float = Field(1.0, ge=0.25, le=2.0)
    replications: int = Field(
        20,
        ge=1,
        le=100,
        description="Número de réplicas con semillas consecutivas (M6).",
    )


class MovementTrace(BaseModel):
    """Métricas de un grupo de carriles agregadas entre réplicas."""
    lane_group_id: str
    queue_p05: List[float] = Field(..., description="Cola por paso, percentil 5 entre réplicas.")
    queue_p50: List[float] = Field(..., description="Cola por paso, mediana entre réplicas.")
    queue_p95: List[float] = Field(..., description="Cola por paso, percentil 95 entre réplicas.")
    arrived_total: float = Field(..., description="Llegadas totales (media entre réplicas).")
    served_total: float = Field(..., description="Vehículos servidos (media entre réplicas).")
    avg_wait_s: float = Field(..., description="Espera media por vehículo (media entre réplicas).")
    wait_p05: float = Field(..., description="Espera media, percentil 5 entre réplicas.")
    wait_p95: float = Field(..., description="Espera media, percentil 95 entre réplicas.")
    max_queue: float = Field(..., description="Cola máxima (media entre réplicas).")
    max_queue_p95: float = Field(..., description="Cola máxima, percentil 95 entre réplicas.")


class SimulationResult(BaseModel):
    duration_s: int
    replications: int
    time_axis_s: List[float]
    movements: List[MovementTrace]
    avg_wait_all_s: float = Field(..., description="Espera media global (media entre réplicas).")
    avg_wait_all_p05: float
    avg_wait_all_p95: float
    max_queue_all: float = Field(..., description="Cola máxima global (media entre réplicas).")
    max_queue_all_p95: float
    total_served: float = Field(..., description="Media entre réplicas.")
    total_arrived: float = Field(..., description="Media entre réplicas.")


# ---------- Escenarios ----------

class DemandMultiplier(BaseModel):
    """Escenario de demanda: factor global + ajustes direccionales (M8).

    El factor efectivo de cada grupo de carriles es el más específico que lo
    cubra: movement_factors[grupo] > approach_factors[acceso] > factor.
    """
    name: str
    factor: float = Field(1.0, ge=0.1, le=3.0, description="Factor global.")
    approach_factors: dict[str, float] = Field(
        default_factory=dict,
        description="Factor por acceso (approach_id → factor); prevalece sobre el global.",
    )
    movement_factors: dict[str, float] = Field(
        default_factory=dict,
        description="Factor por grupo de carriles (lane_group_id → factor); prevalece sobre todos.",
    )

    @field_validator("approach_factors", "movement_factors")
    @classmethod
    def factors_in_range(cls, v: dict[str, float]) -> dict[str, float]:
        for key, f in v.items():
            if not 0.1 <= f <= 3.0:
                raise ValueError(
                    f"Factor fuera de rango [0.1, 3.0] para '{key}': {f}"
                )
        return v


class ScenarioRequest(BaseModel):
    config: IntersectionConfig
    multipliers: List[DemandMultiplier]
    use_optimized_timing: bool = True
    method: Literal["webster", "delay_min"] = Field(
        "webster",
        description="Optimizador usado para el plan de cada escenario.",
    )


class ScenarioResult(BaseModel):
    name: str
    factor: float = Field(..., description="Factor global del escenario.")
    directional: bool = Field(
        False, description="True si el escenario tiene ajustes por acceso/movimiento."
    )
    label: str = Field("", description="Resumen legible de los factores aplicados.")
    analysis: IntersectionAnalysis


class ScenarioComparison(BaseModel):
    scenarios: List[ScenarioResult]
    recommended_strategy: str
    rationale: List[str]
    warnings: List[str] = Field(default_factory=list)


# ---------- Análisis no semaforizado (HCM cap. 19) ----------

class TWSCRequest(BaseModel):
    """Intersección con PARE en la calle secundaria (Two-Way Stop Control)."""
    config: IntersectionConfig
    major_approach_ids: List[str] = Field(
        ...,
        description="IDs de los accesos de la calle principal (sin PARE, flujo libre).",
        min_length=1,
    )


class UnsignalizedMovement(BaseModel):
    lane_group_id: str
    approach_id: str
    role: str  # "mayor-libre" | "mayor-giro-izq" | "menor"
    movement: MovementType
    demand: float
    conflicting_flow: Optional[float] = None
    capacity: Optional[float] = None
    v_c_ratio: Optional[float] = None
    avg_delay_s: float
    los: LOSGrade


class TWSCAnalysis(BaseModel):
    config_name: str
    major_approach_ids: List[str]
    movements: List[UnsignalizedMovement]
    avg_delay_s: float
    overall_los: LOSGrade
    worst_movement: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


