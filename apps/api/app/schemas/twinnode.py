from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

NodeStatus = Literal[
    "DISCONNECTED",
    "REGISTERING",
    "STANDBY",
    "ACTIVATING",
    "ACTIVE",
    "DRAINING",
    "DEGRADED",
    "OFFLINE",
    "ERROR",
]
TaskStatus = Literal[
    "PENDING",
    "ASSIGNED",
    "ACCEPTED",
    "RUNNING",
    "COMPLETED",
    "REJECTED",
    "FAILED",
    "CANCELLED",
    "RETRY_PENDING",
]
AllowedTaskType = Literal[
    "traffic_batch",
    "scenario_evaluation",
    "counterfactual_batch",
]


class NodeRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=2, max_length=64)
    hostname: str = Field(min_length=1, max_length=255)
    token: str | None = Field(default=None, max_length=255)
    agent_version: str = Field(default="1.5.0", min_length=1, max_length=32)
    agent_url: str | None = Field(default=None, max_length=255)
    capabilities: list[AllowedTaskType] = Field(
        default_factory=lambda: ["traffic_batch", "scenario_evaluation", "counterfactual_batch"]
    )
    worker_slots: int = Field(default=2, ge=1, le=16)
    capacity_estimate_score: float = Field(default=1.0, gt=0.0, le=100.0)


class NodeHeartbeatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu_pct: float = Field(ge=0.0, le=100.0)
    memory_pct: float = Field(ge=0.0, le=100.0)
    worker_active: bool
    worker_slots: int = Field(ge=1, le=16)
    active_tasks: int = Field(default=0, ge=0, le=64)
    local_rtt_ms: float = Field(default=0.0, ge=0.0, le=60_000.0)
    ip_address: str | None = Field(default=None, max_length=64)
    agent_url: str | None = Field(default=None, max_length=255)


class HostTelemetryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    timestamp: datetime
    cpu_pct: float
    memory_pct: float
    worker_active: bool
    worker_slots: int
    active_tasks: int
    local_rtt_ms: float
    label: str = "PHYSICAL HOST TELEMETRY — NOT CELLULAR KPI"


class NodeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    hostname: str
    ip_last_seen: str
    agent_url: str | None = None
    status: NodeStatus
    agent_version: str
    capabilities: list[str]
    worker_slots: int
    worker_active: bool
    desired_command: str | None = None
    capacity_estimate_score: float
    last_heartbeat: datetime
    heartbeat_age_seconds: float
    registered_at: datetime
    latest_host_telemetry: HostTelemetryRecord | None = None


class NodeCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_id: str = Field(default="operator-1", min_length=1, max_length=120)
    drain_existing: bool = True


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=4, max_length=128)
    task_type: AllowedTaskType
    schema_version: str = Field(default="1.5", max_length=16)
    origin_node_id: str = Field(default="NODE-TANISH", min_length=2, max_length=64)
    assigned_node_id: str = Field(min_length=2, max_length=64)
    plan_id: UUID | None = None
    simulation_id: UUID | None = None
    event_id: UUID | None = None
    seed: int = Field(default=42, ge=0, le=1_000_000)
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskAckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=2, max_length=64)
    status: Literal["ACCEPTED", "RUNNING", "REJECTED"]
    message: str | None = Field(default=None, max_length=500)


class TaskResultSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=2, max_length=64)
    status: Literal["COMPLETED", "FAILED"] = "COMPLETED"
    checksum: str = Field(min_length=10, max_length=128)
    result: dict[str, Any]
    duration_ms: float = Field(default=0.0, ge=0.0)
    error_message: str | None = Field(default=None, max_length=500)


class TaskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    idempotency_key: str
    task_type: str
    schema_version: str
    status: TaskStatus
    origin_node_id: str
    assigned_node_id: str
    plan_id: UUID | None = None
    simulation_id: UUID | None = None
    event_id: UUID | None = None
    seed: int
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    checksum: str | None = None
    retry_count: int
    lease_until: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class HeartbeatCommandResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node: NodeRecord
    desired_command: Literal["NONE", "ACTIVATE", "STANDBY", "DRAIN"]
    pending_tasks: list[TaskRecord] = Field(default_factory=list)
