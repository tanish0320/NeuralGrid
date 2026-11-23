from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

RiskBand = Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]


class PredictionGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulation_id: UUID
    horizons: list[int] = Field(default_factory=lambda: [5, 15, 30, 60, 120], min_length=1, max_length=10)
    cell_ids: list[str] | None = None
    method: str | None = None


class ForecastRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    event_id: UUID | None = None
    state_version: int
    seed: int
    cell_id: str
    horizon_min: int
    metric: Literal["traffic_mbps", "simulated_end_to_end_latency_ms"]
    unit: Literal["Mbps", "ms"]
    predicted_value: float
    p10: float | None = None
    p50: float | None = None
    p90: float | None = None
    method: str
    model_version: str
    data_provenance: str
    generated_at: datetime
    target_at: datetime


class RiskDriver(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature: str
    value: float | str
    threshold: float | str | None = None
    description: str


class CellRiskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    event_id: UUID | None = None
    state_version: int
    cell_id: str
    risk_band: RiskBand
    risk_method: str = "rule_based_threshold_v1"
    probability: float | None = None
    current_utilisation_pct: float
    forecast_utilisation_pct: float
    current_latency_ms: float
    forecast_latency_ms: float
    drivers: list[RiskDriver]
    generated_at: datetime


class PredictionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulation_id: UUID
    event_id: UUID | None = None
    state_version: int
    seed: int
    method: str
    model_version: str
    data_provenance: str
    forecasts: list[ForecastRecord]
    risk_assessments: list[CellRiskRecord]


class HorizonMetricDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    horizon_min: int
    target_at: datetime
    traffic_mbps: float
    traffic_p10: float
    traffic_p50: float
    traffic_p90: float
    latency_ms: float
    latency_p10: float
    latency_p50: float
    latency_p90: float
    projected_utilisation_pct: float
    risk_band: RiskBand


class CellForecastDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell_id: str
    region: str
    capacity_mbps: float
    backhaul_capacity_mbps: float
    current_demand_mbps: float
    current_utilisation_pct: float
    current_latency_ms: float
    risk_band: RiskBand
    horizons: list[HorizonMetricDetail]
    contributing_events: list[dict[str, Any]] = Field(default_factory=list)
    forecast_reasoning: str
    model_version: str
    generated_at: datetime


class NetworkForecastSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulation_id: UUID | None
    state_version: int
    total_cells: int
    horizons: list[int]
    congested_cells_by_horizon: dict[int, int]
    max_demand_by_horizon: dict[int, float]
    avg_demand_by_horizon: dict[int, float]
    critical_cells: list[str]
    high_risk_cells: list[str]
    generated_at: datetime

