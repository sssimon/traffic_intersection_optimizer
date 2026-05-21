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
from typing import List, Optional

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
        """Tiempo perdido por fase: arranque + despeje. Asumimos 2s + (Y+AR) - 2s útiles."""
        # Tiempo perdido típico = 2s arranque + (amarillo + todo-rojo) - extensión efectiva
        # HCM usa L = arranque + despeje - extensión ≈ 4s por fase
        return 2.0 + self.yellow + self.all_red - 2.0


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
        ..., description="Verde efectivo por fase (s)."
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
    queue_95th_veh: float
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
    seed: int = 42
    time_step_s: float = Field(1.0, ge=0.25, le=2.0)


class MovementTrace(BaseModel):
    lane_group_id: str
    queue_over_time: List[float]
    served_total: int
    arrived_total: int
    avg_wait_s: float
    max_queue: float


class SimulationResult(BaseModel):
    duration_s: int
    time_axis_s: List[float]
    movements: List[MovementTrace]
    avg_wait_all_s: float
    max_queue_all: float
    total_served: int
    total_arrived: int


# ---------- Escenarios ----------

class DemandMultiplier(BaseModel):
    name: str
    factor: float = Field(..., ge=0.1, le=3.0)


class ScenarioRequest(BaseModel):
    config: IntersectionConfig
    multipliers: List[DemandMultiplier]
    use_optimized_timing: bool = True


class ScenarioResult(BaseModel):
    name: str
    factor: float
    analysis: IntersectionAnalysis


class ScenarioComparison(BaseModel):
    scenarios: List[ScenarioResult]
    recommended_strategy: str
    rationale: List[str]


# ---------- Análisis no semaforizado (HCM cap. 19 y 22) ----------

class TWSCRequest(BaseModel):
    """Intersección con PARE en la calle secundaria (Two-Way Stop Control)."""
    config: IntersectionConfig
    major_approach_ids: List[str] = Field(
        ...,
        description="IDs de los accesos de la calle principal (sin PARE, flujo libre).",
        min_length=1,
    )


class RoundaboutRequest(BaseModel):
    """Glorieta / rotonda (HCM cap. 22)."""
    config: IntersectionConfig
    approach_order: List[str] = Field(
        default_factory=list,
        description="IDs de accesos en orden de circulación. Vacío = orden del config.",
    )
    circulating_lanes: int = Field(1, ge=1, le=2)
    entry_lanes: dict[str, int] = Field(
        default_factory=dict,
        description="Carriles de entrada por acceso (id -> nº). Por defecto 1.",
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


class RoundaboutApproachResult(BaseModel):
    approach_id: str
    approach_name: str
    entry_demand: float
    circulating_flow: float
    capacity: float
    v_c_ratio: float
    avg_delay_s: float
    los: LOSGrade


class RoundaboutAnalysis(BaseModel):
    config_name: str
    circulating_lanes: int
    approaches: List[RoundaboutApproachResult]
    avg_delay_s: float
    overall_los: LOSGrade
    warnings: List[str] = Field(default_factory=list)
