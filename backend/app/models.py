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


class SaturationFactors(BaseModel):
    """Factores de ajuste del flujo de saturación — HCM 2010, cap. 18 (M9).

        s = s_base · N · fw · fg · fp · fbb · fa · fLU · f_giro

    Declarar este objeto activa la cadena. Todos los campos tienen valores
    neutros (factor 1.0) salvo el ajuste por giro: en un grupo de giro
    EXCLUSIVO se aplica el factor de giro protegido del HCM (fLT = 0.95
    izquierda, fRT = 0.85 derecha). En carriles compartidos se mantiene la
    simplificación 0.85 del grupo y NO se aplica f_giro (evita el doble
    castigo). Sin este objeto el cálculo es el histórico.

    Vehículos pesados: NO van aquí — se modelan con `pcu_factor` en la
    demanda, matemáticamente equivalente al fHV del HCM (incluirlos en
    ambos lados los contaría dos veces). Bloqueo de giros por peatones y
    ciclistas (fLpb/fRpb): no modelado aún (ver M10).
    """
    lane_width_m: Optional[float] = Field(
        None,
        ge=2.4,
        le=5.5,
        description=(
            "Ancho promedio de carril (m). fw = 1 + (W − 3.66)/9.14 "
            "(HCM 2010; 12 y 30 pies). None = sin ajuste."
        ),
    )
    grade_pct: float = Field(
        0.0,
        ge=-6.0,
        le=10.0,
        description="Pendiente del acceso (%), subida positiva. fg = 1 − G/200.",
    )
    parking_maneuvers_per_h: Optional[float] = Field(
        None,
        ge=0.0,
        le=180.0,
        description=(
            "Maniobras de estacionamiento adyacente por hora (Nm). "
            "fp = (N − 0.1 − 18·Nm/3600)/N ≥ 0.05. None = sin estacionamiento."
        ),
    )
    bus_stops_per_h: float = Field(
        0.0,
        ge=0.0,
        le=250.0,
        description=(
            "Buses que paran por hora en el acceso (NB). "
            "fbb = (N − 14.4·NB/3600)/N ≥ 0.05."
        ),
    )
    cbd: bool = Field(False, description="Zona céntrica de negocios: fa = 0.90.")
    lane_utilization: float = Field(
        1.0,
        ge=0.5,
        le=1.0,
        description=(
            "fLU. Valores HCM típicos: 0.952 (2 carriles), 0.908 (3). "
            "1.0 = reparto parejo o medido."
        ),
    )

    def breakdown(
        self, lanes: int, movement: MovementType, shared: bool
    ) -> list[tuple[str, float]]:
        """Factores individuales (nombre, valor) — los neutros se omiten.

        Es la única transcripción de las fórmulas: `chain` y el modo
        auditoría se construyen sobre este desglose.
        """
        n = max(1, lanes)
        out: list[tuple[str, float]] = []
        if self.lane_width_m is not None:
            out.append(("fw ancho", 1.0 + (self.lane_width_m - 3.66) / 9.14))
        if self.grade_pct != 0.0:
            out.append(("fg pendiente", 1.0 - self.grade_pct / 200.0))
        if self.parking_maneuvers_per_h is not None:
            out.append((
                "fp estacionamiento",
                max(0.050, (n - 0.1 - 18.0 * self.parking_maneuvers_per_h / 3600.0) / n),
            ))
        if self.bus_stops_per_h > 0:
            out.append((
                "fbb buses",
                max(0.050, (n - 14.4 * self.bus_stops_per_h / 3600.0) / n),
            ))
        if self.cbd:
            out.append(("fa CBD", 0.90))
        if self.lane_utilization != 1.0:
            out.append(("fLU utilización", self.lane_utilization))
        if not shared:
            if movement == MovementType.LEFT:
                out.append(("fLT izq. protegida", 0.95))
            elif movement == MovementType.RIGHT:
                out.append(("fRT der. exclusiva", 0.85))
        return out

    def chain(self, lanes: int, movement: MovementType, shared: bool) -> float:
        """Producto de los factores para un grupo de `lanes` carriles."""
        f = 1.0
        for _, value in self.breakdown(lanes, movement, shared):
            f *= value
        return f


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
    factors: Optional[SaturationFactors] = Field(
        None,
        description=(
            "Cadena de factores de saturación HCM; None = sin cadena "
            "(comportamiento histórico)."
        ),
    )

    @property
    def saturation_flow(self) -> float:
        """Flujo de saturación total del grupo (veh/h)."""
        s = self.saturation_flow_per_lane * self.lanes
        if self.factors is not None:
            s *= self.factors.chain(self.lanes, self.movement, self.shared_with_through)
        if self.shared_with_through:
            s *= 0.85
        return s


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
        ge=0.3,
        le=3.0,
        description=(
            "Factor de equivalencia a vehículo ligero: pesados > 1.0, "
            "motos < 1.0 (composición con muchas motos baja el factor)."
        ),
    )

    @property
    def adjusted_volume(self) -> float:
        return self.volume * self.pcu_factor


class Crossing(BaseModel):
    """Cruce peatonal asociado a una fase del semáforo (M10, tarea 5.3).

    Los peatones reciben el intervalo Walk durante una fase (normalmente la
    paralela al sentido que cruzan, o una fase peatonal exclusiva). El tiempo
    mínimo seguro es el Walk de MUTCD más el despeje peatonal L/Sp; la demora
    peatonal sale del modelo HCM de llegadas aleatorias.
    """
    id: str = Field(..., description="Identificador único del cruce, ej: 'X-N'.")
    name: str
    length_m: float = Field(
        ..., gt=0.0, le=60.0, description="Longitud del cruce (m): ancho de la calzada que se cruza."
    )
    phase_id: str = Field(
        ..., description="Fase durante la cual los peatones reciben Walk."
    )
    walk_speed_ms: float = Field(
        1.2, ge=0.8, le=1.8, description="Velocidad peatonal de cruce (HCM: 1.2 m/s)."
    )
    walk_interval_s: float = Field(
        7.0, ge=4.0, le=15.0, description="Intervalo Walk mínimo (MUTCD: 7 s)."
    )
    ped_volume_per_h: float = Field(
        0.0, ge=0.0, description="Volumen peatonal por hora (informativo)."
    )


class IntersectionConfig(BaseModel):
    """Configuración completa de una intersección."""
    name: str
    approaches: List[Approach]
    phases: List[Phase]
    demand: List[Demand]
    crossings: List[Crossing] = Field(
        default_factory=list,
        description="Cruces peatonales (opcional, M10). Vacío = sin análisis peatonal.",
    )
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


class AuditStep(BaseModel):
    """Un paso verificable: fórmula, sustitución numérica, valor y fuente."""
    concept: str
    formula: str
    substitution: str
    value: float
    units: str
    source: str


class MovementAudit(BaseModel):
    lane_group_id: str
    phase_id: str
    steps: List[AuditStep]


class PedestrianAnalysis(BaseModel):
    """Resultado peatonal por cruce (M10): demora y LOS junto al vehicular."""
    crossing_id: str
    name: str
    phase_id: str
    length_m: float
    effective_walk_s: float = Field(
        ..., description="Tiempo disponible para cruzar (verde de la fase, gp)."
    )
    clearance_s: float = Field(..., description="Despeje peatonal L/Sp (FDW).")
    min_required_s: float = Field(
        ..., description="Mínimo seguro: Walk + L/Sp (MUTCD)."
    )
    avg_delay_s: float = Field(..., description="Demora peatonal media: 0.5·C·(1 − gp/C)².")
    los: LOSGrade
    sufficient_green: bool = Field(
        ..., description="True si el verde de la fase cubre el mínimo MUTCD."
    )


class IntersectionAnalysis(BaseModel):
    config_name: str
    signal_plan: SignalPlan
    movements: List[MovementAnalysis]
    avg_delay_s: float
    overall_los: LOSGrade
    overall_v_c: float
    pedestrians: List[PedestrianAnalysis] = Field(
        default_factory=list,
        description="Análisis peatonal por cruce (vacío si no hay cruces definidos).",
    )
    warnings: List[str] = Field(default_factory=list)
    audit: Optional[List[MovementAudit]] = Field(
        None,
        description=(
            "Traza de cálculo por movimiento (modo auditoría): cada número "
            "con su fórmula, sustitución y edición citada."
        ),
    )


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


# ---------- Explorador de alternativas de control (tarea 2.1) ----------

class CompareControlsRequest(BaseModel):
    config: IntersectionConfig
    major_approach_ids: List[str] = Field(
        default_factory=list,
        description=(
            "Accesos de la calle principal para la alternativa PARE. "
            "Vacío = los dos de mayor demanda."
        ),
    )


class ControlAlternative(BaseModel):
    """Una alternativa de control evaluada con la misma demanda."""
    id: str
    kind: Literal["signal", "twsc"]
    name: str
    avg_delay_s: float = Field(..., description="Demora media ponderada (s/veh) sobre TODOS los vehículos.")
    overall_los: LOSGrade = Field(..., description="OJO: umbrales distintos entre semáforo (F>80) y PARE (F>50).")
    overall_v_c: float = Field(..., description="v/c representativo (máximo entre movimientos).")
    cycle_length: Optional[float] = Field(None, description="Solo semáforo (s).")
    worst_queue_95th_veh: Optional[float] = Field(
        None, description="Solo semáforo: peor cola 95 % por carril (veh)."
    )
    notes: List[str] = Field(default_factory=list)
    signal: Optional[IntersectionAnalysis] = None
    twsc: Optional[TWSCAnalysis] = None


class CompareControlsResult(BaseModel):
    alternatives: List[ControlAlternative] = Field(
        ..., description="Ordenadas por demora media ascendente (ranking)."
    )
    recommended_id: str
    rationale: List[str]
    warnings: List[str] = Field(default_factory=list)


# ---------- Coordinación de corredor (tarea 4.1) ----------

class CorridorIntersectionInput(BaseModel):
    """Una intersección del corredor, vista desde la arteria coordinada."""
    name: str
    green_s: float = Field(..., ge=5.0, description="Verde efectivo de la fase arterial (s).")
    distance_to_next_m: float = Field(
        0.0, ge=0.0, description="Distancia a la siguiente intersección (m); 0 en la última."
    )
    speed_to_next_kmh: float = Field(40.0, ge=5.0, le=120.0)
    vol_out: float = Field(0.0, ge=0.0, description="Volumen arterial de ida (veh/h).")
    vol_in: float = Field(0.0, ge=0.0, description="Volumen arterial de vuelta (veh/h).")
    sat_out: float = Field(3400.0, ge=500.0, description="Saturación de ida (veh/h, ≈1700·carriles).")
    sat_in: float = Field(3400.0, ge=500.0, description="Saturación de vuelta (veh/h).")


class CorridorRequest(BaseModel):
    cycle_s: float = Field(..., ge=40.0, le=180.0, description="Ciclo común del corredor (s).")
    intersections: List[CorridorIntersectionInput] = Field(..., min_length=2, max_length=8)
    offsets_s: List[float] = Field(
        default_factory=list,
        description="Offsets manuales (s, uno por intersección); vacío = optimizar.",
    )
    optimize_offsets: bool = Field(
        True, description="Optimizar offsets maximizando la banda ponderada por volumen."
    )


class CorridorIntersectionResult(BaseModel):
    name: str
    position_m: float
    offset_s: float
    green_s: float
    p_green_out: Optional[float] = Field(None, description="Fracción del pelotón de ida que llega en verde (None = primera, llegadas aleatorias).")
    p_green_in: Optional[float] = None
    pf_out: float = Field(..., description="Factor de progresión HCM aplicado a d1 (ida).")
    pf_in: float
    delay_out_s: float
    delay_in_s: float
    delay_isolated_out_s: float = Field(..., description="Demora con PF = 1 (aislada), para comparar.")
    delay_isolated_in_s: float


class CorridorResult(BaseModel):
    cycle_s: float
    offsets_optimized: bool
    band_out_s: float = Field(..., description="Banda verde de ida (s).")
    band_in_s: float
    efficiency_out: float = Field(..., description="Banda/ciclo (ida).")
    efficiency_in: float
    band_out_start_s: float = Field(..., description="Inicio de la banda de ida, reloj absoluto en la 1.ª intersección.")
    band_in_start_s: float = Field(..., description="Inicio de la banda de vuelta, reloj absoluto en la última intersección.")
    travel_times_s: List[float] = Field(..., description="Tiempo de viaje acumulado desde la 1.ª intersección.")
    intersections: List[CorridorIntersectionResult]
    avg_artery_delay_s: float = Field(..., description="Demora arterial media ponderada, coordinada (con PF).")
    avg_artery_delay_isolated_s: float = Field(..., description="Ídem con PF = 1 (aisladas).")
    warnings: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


# ---------- Aforo de campo de 15 minutos (tarea 3.3) ----------

class MovementCounts(BaseModel):
    """Conteos de un grupo por intervalo de 15 min y clase vehicular.

    Cada lista trae un valor por intervalo (o va vacía = ceros)."""
    auto: List[float] = Field(default_factory=list)
    moto: List[float] = Field(default_factory=list)
    bus: List[float] = Field(default_factory=list)
    camion: List[float] = Field(default_factory=list)


class PcuEquivalences(BaseModel):
    """Equivalencias PCU por clase — declaradas y editables."""
    auto: float = Field(1.0, ge=0.1, le=5.0)
    moto: float = Field(0.5, ge=0.1, le=5.0)
    bus: float = Field(2.0, ge=0.1, le=5.0)
    camion: float = Field(2.0, ge=0.1, le=5.0)


class FieldCountRequest(BaseModel):
    interval_labels: List[str] = Field(
        ...,
        min_length=1,
        max_length=16,
        description="Etiquetas de los intervalos de 15 min (ej. hora de inicio).",
    )
    counts: dict[str, MovementCounts] = Field(
        ..., description="Conteos por lane_group_id."
    )
    pcu: PcuEquivalences = Field(default_factory=PcuEquivalences)


class FieldCountResult(BaseModel):
    peak_hour_label: str
    expanded: bool = Field(
        ..., description="True si hubo menos de 4 intervalos (expansión ×4/n)."
    )
    phf: Optional[float] = Field(
        None,
        description="PHF = V_hora/(4·V15máx) sobre el total; None si no es calculable.",
    )
    volumes: dict[str, float] = Field(
        ..., description="Volumen horario mixto (veh/h) por grupo en la hora pico."
    )
    pcu_factors: dict[str, float] = Field(
        ..., description="PCU por grupo desde la composición de la hora pico."
    )
    totals_per_interval: List[float]
    warnings: List[str] = Field(default_factory=list)


# ---------- Importación desde OpenStreetMap (tarea 3.1) ----------

class OsmImportRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    radius_m: int = Field(
        60, ge=20, le=150,
        description="Radio de búsqueda del cruce alrededor del pin (m).",
    )


class OsmImportResult(BaseModel):
    config: IntersectionConfig = Field(
        ..., description="Configuración inicial: accesos, carriles, fases; demanda en 0."
    )
    warnings: List[str] = Field(default_factory=list)


# ---------- Persistencia de corridas (tarea 2.5) ----------

class SaveRunRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Nombre de la corrida.")
    config: IntersectionConfig
    method: Literal["webster", "delay_min"] = Field(
        "delay_min", description="Optimizador con el que se calcula el resumen."
    )


class RunSummary(BaseModel):
    """Resumen guardado de una corrida — la tabla de resúmenes permite
    comparar corridas entre fechas."""
    id: int
    name: str
    created_at: str = Field(..., description="Fecha-hora ISO (UTC).")
    intersection_name: str
    method: str
    cycle_length: float
    avg_delay_s: float
    overall_los: LOSGrade
    overall_v_c: float


class RunDetail(RunSummary):
    config: IntersectionConfig


# ---------- Incertidumbre Monte Carlo (tarea 2.3) ----------

class UncertaintyRequest(BaseModel):
    config: IntersectionConfig
    volume_cv: float = Field(
        0.10,
        ge=0.0,
        le=0.5,
        description=(
            "Coeficiente de variación de los volúmenes. Guía según la "
            "calidad del aforo: ≈0.15 conteo de 15 min expandido, ≈0.10 "
            "conteo de 1 h, ≈0.05 aforo de varios días."
        ),
    )
    movement_cv: dict[str, float] = Field(
        default_factory=dict,
        description="CV por grupo de carriles (prevalece sobre el global).",
    )
    samples: int = Field(1000, ge=100, le=20000)
    seed: int = 42
    method: Literal["webster", "delay_min"] = Field(
        "delay_min", description="Optimizador del plan (diseñado con el aforo medio)."
    )

    @field_validator("movement_cv")
    @classmethod
    def cv_in_range(cls, v: dict[str, float]) -> dict[str, float]:
        for key, cv in v.items():
            if not 0.0 <= cv <= 0.5:
                raise ValueError(f"CV fuera de rango [0, 0.5] para '{key}': {cv}")
        return v


class MovementSensitivity(BaseModel):
    lane_group_id: str
    correlation: float = Field(
        ..., description="Correlación de Pearson entre el volumen muestreado y la demora media."
    )
    cv: float


class UncertaintyResult(BaseModel):
    samples: int
    volume_cv: float
    method: str
    signal_plan: SignalPlan = Field(..., description="Plan fijo diseñado con el aforo medio.")
    base_delay_s: float = Field(..., description="Demora con el aforo medio (la estimación puntual clásica).")
    delay_mean_s: float
    delay_p05_s: float
    delay_p50_s: float
    delay_p95_s: float
    los_probability: dict[str, float] = Field(
        ..., description="P(LOS) de la intersección sobre las muestras (A..F, suma 1)."
    )
    prob_oversaturated: float = Field(
        ..., description="P(X máx > 1): probabilidad de sobresaturación del movimiento crítico."
    )
    sensitivity: List[MovementSensitivity] = Field(
        ..., description="Tornado: movimientos ordenados por |correlación| descendente."
    )
    notes: List[str] = Field(default_factory=list)


# ---------- Puente SUMO opcional (tarea 4.2) ----------

class SumoExportRequest(BaseModel):
    config: IntersectionConfig
    signal_plan: Optional[SignalPlan] = Field(
        None, description="Plan a exportar; None = se optimiza con `method`."
    )
    method: Literal["webster", "delay_min"] = Field(
        "delay_min", description="Optimizador si no se entrega un signal_plan."
    )
    duration_s: int = Field(
        600, ge=120, le=3600, description="Periodo medido por réplica (s)."
    )
    warmup_s: int = Field(
        120, ge=0, le=1800, description="Calentamiento descartado antes de medir (s)."
    )
    replications: int = Field(
        5, ge=1, le=20, description="Réplicas SUMO con semillas consecutivas."
    )
    seed: int = 42
    run_microsim: bool = Field(
        True, description="Correr SUMO si está disponible; False = solo exportar archivos."
    )
    driving_side: Literal["right", "left"] = Field(
        "right", description="Mano de circulación para inferir giros (Venezuela: derecha)."
    )


class SumoFile(BaseModel):
    """Un archivo del modelo SUMO, devuelto como texto para descargar."""
    name: str
    content: str


class SumoMicrosimResult(BaseModel):
    replications: int
    measured_vehicles: float = Field(
        ..., description="Vehículos medidos tras el calentamiento (media entre réplicas)."
    )
    delay_mean_s: float = Field(
        ..., description="timeLoss medio (s/veh): demora microsimulada."
    )
    delay_p05_s: float
    delay_p50_s: float
    delay_p95_s: float
    mean_waiting_s: float = Field(
        ..., description="Tiempo detenido medio (s/veh)."
    )
    overall_los: LOSGrade
    teleports: float = Field(
        ...,
        description=(
            "Teletransportes medios por réplica; >0 indica gridlock y demora "
            "microsimulada subestimada."
        ),
    )


class SumoAnalyticSummary(BaseModel):
    avg_delay_s: float
    overall_los: LOSGrade
    overall_v_c: float


class SumoExportResult(BaseModel):
    sumo_available: bool = Field(
        ..., description="True si netconvert y sumo se encontraron (PATH o SUMO_HOME)."
    )
    files: List[SumoFile] = Field(
        ..., description="Archivos del modelo SUMO (descargables aunque SUMO no esté)."
    )
    analytic: SumoAnalyticSummary
    microsim: Optional[SumoMicrosimResult] = None
    delta_delay_s: Optional[float] = Field(
        None, description="Demora microsimulada − analítica (s/veh)."
    )
    warnings: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


# ---------- Informe profesional de 1 clic (tarea 5.1) ----------

class ReportRequest(BaseModel):
    config: IntersectionConfig
    method: Literal["webster", "delay_min"] = Field(
        "delay_min", description="Optimizador con el que se diseña el plan del informe."
    )
    volume_cv: float = Field(
        0.10, ge=0.0, le=0.5,
        description="CV de los volúmenes para el análisis de incertidumbre P(LOS).",
    )
    samples: int = Field(2000, ge=100, le=20000)
    include_uncertainty: bool = Field(
        True, description="Incluir la sección de incertidumbre P(LOS)."
    )
    include_audit: bool = Field(
        True, description="Incluir el anexo de auditoría (traza de cálculo)."
    )
    author: Optional[str] = Field(
        None, description="Quién firma el informe (opcional, para la portada)."
    )
    study_date: Optional[str] = Field(
        None, description="Fecha del estudio/aforo (texto libre, opcional)."
    )


# ---------- Copiloto LLM opcional (tarea 5.2) ----------

class CopilotStatus(BaseModel):
    available: bool = Field(
        ..., description="True si hay ANTHROPIC_API_KEY en el entorno del backend."
    )
    model: Optional[str] = Field(None, description="Modelo que usará el copiloto.")
    note: str


class CopilotExplainRequest(BaseModel):
    config: IntersectionConfig
    question: str = Field(..., min_length=1, max_length=2000)
    method: Literal["webster", "delay_min"] = "delay_min"


class CopilotExplainResult(BaseModel):
    answer: str = Field(..., description="Respuesta en español (markdown).")
    model: str
    warnings: List[str] = Field(default_factory=list)


class CopilotEditRequest(BaseModel):
    config: IntersectionConfig
    instruction: str = Field(
        ..., min_length=1, max_length=2000,
        description="Instrucción en lenguaje natural (p. ej. 'sube 20% la demanda del Este').",
    )


class CopilotEditResult(BaseModel):
    config: IntersectionConfig = Field(
        ..., description="Configuración propuesta, ya validada con el esquema."
    )
    summary: str = Field(..., description="Resumen en español de lo que cambió.")
    model: str
    warnings: List[str] = Field(default_factory=list)


