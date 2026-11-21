from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from apps.api.app.schemas.networks import CellOperationalState

SimulationStatus = Literal["CREATED", "RUNNING", "PAUSED", "COMPLETED"]
FaultType = Literal["CELL_FAILURE", "BACKHAUL_CONGESTION"]


class SimulationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int = Field(default=42, ge=0, le=1_000_000)
    step_minutes: int = Field(default=5, ge=1, le=30)
    tick_interval_seconds: float = Field(default=1.5, ge=0.1, le=30.0)
    start_time_utc: datetime | None = None


class LatencyComponents(BaseModel):
    model_config = ConfigDict(extra="forbid")

    radio_ms: float
    transport_ms: float
    core_ms: float
    processing_ms: float
    label: str = "SYNTHETIC_COMPONENT_LATENCY"


class CellTelemetryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    tick: int
    state_version: int
    cell_id: str
    background_demand_mbps: float
    event_demand_mbps: float
    demand_mbps: float
    served_mbps: float
    queued_mbps: float
    unserved_mbps: float
    utilisation_pct: float
    simulated_latency_ms: float
    latency_components: LatencyComponents
    packet_loss_pct: float
    energy_units: float
    cell_state: CellOperationalState
    sim_time_utc: datetime
    recorded_at: datetime


class FaultInjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fault_type: FaultType
    cell_id: str = Field(min_length=3, max_length=64)
    severity: float = Field(default=0.6, ge=0.1, le=1.0)
    active: bool = True


class SimulationEventInjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    influence_radius_km: float = Field(default=3.0, gt=0.1, le=25.0)
    attendance_scenario: Literal["LOW", "EXPECTED", "HIGH"] = "EXPECTED"
    intensity: float = Field(default=1.0, ge=0.1, le=5.0)


class SimulationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_cells: int
    active_cells: int
    standby_cells: int
    failed_cells: int
    congested_cells: int
    total_demand_mbps: float
    total_served_mbps: float
    total_queued_mbps: float
    total_unserved_mbps: float
    peak_utilisation_pct: float
    mean_simulated_latency_ms: float


class SimulationStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulation_id: UUID
    network_id: UUID
    seed: int
    tick: int
    state_version: int
    status: SimulationStatus
    active_event_id: UUID | None = None
    event_intensity: float
    attendance_scenario: str
    faults: dict[str, Any] = Field(default_factory=dict)
    applied_transfers: list[dict[str, Any]] = Field(default_factory=list)
    sim_time_utc: datetime
    label: str = "SIMULATED NETWORK TELEMETRY"
    summary: SimulationSummary
    telemetry: list[CellTelemetryRecord]
    created_at: datetime
    updated_at: datetime
