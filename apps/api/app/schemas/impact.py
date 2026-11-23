from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator

from apps.api.app.schemas.events import ContractModel


def _ensure_utc(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    if v.tzinfo is None:
        from datetime import timezone
        return v.replace(tzinfo=timezone.utc)
    from datetime import timezone
    return v.astimezone(timezone.utc)


ImpactCategory = Literal["PRIMARY_HOTSPOT", "SECONDARY_ADJACENT", "PERIPHERAL_TRANSIT"]
CongestionRiskBand = Literal["NORMAL", "ELEVATED", "HIGH", "CRITICAL"]


class TemporalProfilePoint(ContractModel):
    offset_minutes: int
    factor: float
    demand_mbps: float


class TemporalProfile(ContractModel):
    arrival_hours: float
    event_hours: float
    departure_hours: float
    peak_multiplier: float
    points: list[TemporalProfilePoint] = Field(default_factory=list)


class EventCellImpactRecord(ContractModel):
    impact_id: str
    event_id: UUID
    cell_id: str
    geographic_distance_km: float
    geographic_relevance_score: float = Field(ge=0.0, le=1.0)
    coverage_relevance_score: float = Field(ge=0.0, le=1.0)
    estimated_demand_delta_mbps: float = Field(ge=0.0)
    impact_confidence: float = Field(ge=0.0, le=1.0)
    impact_category: ImpactCategory
    impact_window_start: datetime
    impact_window_end: datetime
    temporal_profile: dict[str, Any] = Field(default_factory=dict)
    mapping_method: str = "haversine_attenuation_v1.5"
    scoring_model_version: str = "v1.5"
    input_evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("impact_window_start", "impact_window_end", "created_at", "updated_at")
    @classmethod
    def _validate_dates(cls, v: datetime) -> datetime:
        return _ensure_utc(v) or v


class EventImpactSummary(ContractModel):
    event_id: UUID
    event_title: str
    event_category: str
    venue_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    lifecycle_status: str
    verification_status: str
    attendance_estimate: int | None = None
    is_geographically_resolved: bool
    total_affected_cells: int
    total_demand_delta_mbps: float
    impact_window_start: datetime | None = None
    impact_window_end: datetime | None = None
    affected_cells: list[EventCellImpactRecord] = Field(default_factory=list)

    @field_validator("impact_window_start", "impact_window_end")
    @classmethod
    def _validate_dates(cls, v: datetime | None) -> datetime | None:
        return _ensure_utc(v)


class ContributingEventInfo(ContractModel):
    event_id: UUID
    event_title: str
    event_category: str
    venue_name: str | None = None
    distance_km: float
    demand_delta_mbps: float
    impact_category: str
    impact_confidence: float
    impact_window_start: datetime
    impact_window_end: datetime


class CellImpactAggregated(ContractModel):
    cell_id: str
    region: str
    capacity_mbps: float
    base_load_mbps: float
    current_load_mbps: float
    combined_demand_delta_mbps: float
    projected_total_demand_mbps: float
    projected_utilisation_pct: float
    congestion_risk_band: CongestionRiskBand
    contributing_event_count: int
    contributing_events: list[ContributingEventInfo] = Field(default_factory=list)
    max_impact_window_start: datetime | None = None
    max_impact_window_end: datetime | None = None

    @field_validator("max_impact_window_start", "max_impact_window_end")
    @classmethod
    def _validate_dates(cls, v: datetime | None) -> datetime | None:
        return _ensure_utc(v)


class CellOverlapSummary(ContractModel):
    cell_id: str
    region: str
    overlapping_event_count: int
    event_ids: list[UUID]
    event_titles: list[str]
    individual_demand_sum_mbps: float
    sublinear_aggregated_demand_mbps: float
    attenuation_discount_mbps: float
    peak_overlap_window_start: datetime | None = None
    peak_overlap_window_end: datetime | None = None
    risk_band: CongestionRiskBand

    @field_validator("peak_overlap_window_start", "peak_overlap_window_end")
    @classmethod
    def _validate_dates(cls, v: datetime | None) -> datetime | None:
        return _ensure_utc(v)


class ImpactRecalculateRequest(ContractModel):
    network_id: UUID | None = None
    force_all: bool = False


class ImpactRecalculateResponse(ContractModel):
    status: str
    network_id: UUID | None = None
    total_canonical_events: int
    mapped_events_count: int
    geographically_unresolved_count: int
    excluded_events_count: int
    total_impact_records: int
    affected_cells_count: int
    overlapping_cells_count: int
    max_cell_demand_delta_mbps: float
    avg_cell_demand_delta_mbps: float
    category_distribution: dict[str, int] = Field(default_factory=dict)
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def _validate_dates(cls, v: datetime) -> datetime:
        return _ensure_utc(v) or v
