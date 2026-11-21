from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

CriticalityLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
CellOperationalState = Literal["ACTIVE", "STANDBY", "FAILED"]
EdgeType = Literal["handover_support", "shared_backhaul", "coverage_overlap"]


class NetworkSeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int = Field(default=42, ge=0, le=1_000_000)
    cell_count: int = Field(default=100, ge=100, le=100)
    regions: list[str] = Field(
        default_factory=lambda: [
            "Central Business District",
            "Outer Ring Road",
            "Whitefield",
            "Electronic City",
        ],
        min_length=1,
        max_length=8,
    )


class NetworkMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    network_id: UUID
    seed: int
    cell_count: int
    regions: list[str]
    state_version: int
    label: str = "SIMULATED NETWORK — SYNTHETIC COORDINATES"
    created_at: datetime


class CellRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell_id: str
    network_id: UUID
    region: str
    lat: float
    lon: float
    capacity_mbps: float
    backhaul_capacity_mbps: float
    base_load_mbps: float
    criticality: CriticalityLevel
    is_emergency: bool
    initial_state: CellOperationalState
    current_state: CellOperationalState


class CellEdgeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_id: str
    network_id: UUID
    source_cell_id: str
    target_cell_id: str
    edge_type: EdgeType
    weight: float
    max_transfer_mbps: float
    enabled: bool = True


class NetworkCellsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    network: NetworkMetadata
    cells: list[CellRecord]


class NetworkGraphResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    network: NetworkMetadata
    nodes: list[CellRecord]
    edges: list[CellEdgeRecord]
    average_degree: float
