from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

PlanStatus = Literal[
    "DRAFT",
    "PENDING_APPROVAL",
    "APPROVED",
    "EXECUTING",
    "COMPLETED",
    "REJECTED",
    "EXPIRED",
    "FAILED",
    "STALE",
]
ActionType = Literal[
    "activate_standby_cell",
    "reallocate_load",
    "dispatch_compute_task",
]


class OperatorIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(
        default="Reduce event-area congestion while preserving critical coverage and limiting action churn",
        min_length=4,
        max_length=300,
    )
    target_utilisation_pct: float = Field(default=80.0, ge=40.0, le=99.0)
    preserve_emergency_coverage: bool = True
    prefer_energy_efficiency: bool = False
    include_compute_offload: bool = True
    max_actions: int = Field(default=8, ge=1, le=25)


class PlanConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_transfer_per_action_mbps: float = Field(default=200.0, gt=1.0, le=1000.0)
    max_actions: int = Field(default=8, ge=1, le=25)
    protect_emergency_cells: bool = True


class PlanGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulation_id: UUID
    state_version: int = Field(ge=1)
    intent: OperatorIntent = Field(default_factory=OperatorIntent)
    constraints: PlanConstraints = Field(default_factory=PlanConstraints)


class PlanActionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: UUID
    action_order: int
    action_type: ActionType
    source_id: str
    target_id: str
    amount: float
    params: dict[str, Any] = Field(default_factory=dict)


class ObjectiveTermBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overload_penalty: float
    latency_penalty: float
    energy_penalty: float
    action_churn_penalty: float
    total_score: float


class ObjectiveBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weights: dict[str, float]
    before: ObjectiveTermBreakdown
    after_projected: ObjectiveTermBreakdown
    improvement: float
    formula: str = "J = w1*overload_penalty + w2*latency_penalty + w3*energy_penalty + w4*action_churn_penalty"


class ConstraintCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    detail: str


class PlanRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    simulation_id: UUID
    event_id: UUID | None = None
    seed: int
    version: int
    state_version: int
    status: PlanStatus
    solver_method: str
    label: str = "SIMULATED RECOMMENDATION — REQUIRES OPERATOR APPROVAL"
    intent: OperatorIntent
    objective: ObjectiveBreakdown
    constraints_checked: list[ConstraintCheckResult]
    actions: list[PlanActionRecord]
    explanation: list[str]
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class PlanApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_id: str = Field(default="operator-1", min_length=1, max_length=120)
    plan_version: int = Field(ge=1)
    state_version: int = Field(ge=1)
    notes: str | None = Field(default=None, max_length=500)


class PlanRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_id: str = Field(default="operator-1", min_length=1, max_length=120)
    reason: str = Field(min_length=2, max_length=500)


class PlanExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_id: str = Field(default="operator-1", min_length=1, max_length=120)
    expected_state_version: int | None = Field(default=None, ge=1)


class PlanExecutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: PlanRecord
    new_simulation_state_version: int
    dispatched_task_ids: list[UUID] = Field(default_factory=list)
    message: str
