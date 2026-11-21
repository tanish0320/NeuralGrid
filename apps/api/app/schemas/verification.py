from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class VerificationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulation_id: UUID
    plan_id: UUID
    horizon_ticks: int = Field(default=12, ge=1, le=48)


class SimulationBranchMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    congested_cell_minutes: float
    peak_utilisation_pct: float
    simulated_latency_p50_ms: float
    simulated_latency_p95_ms: float
    simulated_latency_max_ms: float
    total_queued_mbps: float
    total_unserved_mbps: float
    total_energy_units: float
    action_count: int


class TwinNodeExecutionMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks_total: int
    tasks_completed: int
    tasks_failed_or_pending: int
    avg_duration_ms: float
    total_retries: int
    executed_nodes: list[str]
    label: str = "PHYSICAL COMPUTE EXECUTION METRICS — SEPARATE FROM RAN KPIS"


class VerificationResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verification_id: UUID
    baseline_run_id: str
    intervention_run_id: str
    plan_id: UUID
    event_id: UUID | None = None
    seed: int
    initial_state_version: int
    horizon_ticks: int
    config_match: bool
    label: str = "SIMULATION COUNTERFACTUAL — NOT LIVE NETWORK OUTCOME"
    baseline: SimulationBranchMetrics
    intervention: SimulationBranchMetrics
    deltas: dict[str, float]
    twinnode_metrics: TwinNodeExecutionMetrics
    created_at: datetime


class AuditEventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    timestamp: datetime
    actor: str
    action: str
    entity_type: str
    entity_id: str
    state_version: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)
