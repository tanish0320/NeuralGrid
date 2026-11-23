from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

DiscoveryProvider = str
FetchProvider = Literal["crawl4ai", "static_html_fallback"]
DiscoveryRunStatus = Literal["PENDING", "RUNNING", "SUCCEEDED", "PARTIAL", "FAILED", "SKIPPED"]
ProviderStatus = Literal["SUCCEEDED", "PARTIAL", "FAILED", "SKIPPED"]
FetchStatus = Literal[
    "NOT_FETCHED",
    "RUNNING",
    "SUCCEEDED",
    "BLOCKED_ROBOTS",
    "BLOCKED_POLICY",
    "HTTP_ERROR",
    "TIMEOUT",
    "RATE_LIMITED",
    "FAILED",
]
ExtractionStatus = Literal["NOT_RUN", "SUCCEEDED", "PARTIAL", "NO_EVENT_FIELDS", "FAILED"]
EventOrigin = Literal["SOURCE_DISCOVERED", "MANUAL_INPUT", "SEEDED_DEMO"]
VerificationStatus = Literal[
    "DISCOVERED",
    "PARTIALLY_VERIFIED",
    "CORROBORATED",
    "VERIFIED",
    "CONFLICTED",
    "CANCELLED",
    "EXPIRED",
    "UNVERIFIED",
    "SINGLE_SOURCE",
    "MANUALLY_VERIFIED",
    "DEMO_SCENARIO",
]
AttendanceBasis = Literal["SOURCE_EVIDENCE", "OPERATOR_ASSUMPTION", "UNKNOWN"]
SourceType = Literal[
    "news_article",
    "rss_item",
    "event_page",
    "organiser_page",
    "ticketing_page",
    "social_post",
    "manual_reference",
]
EventLifecycleStatus = Literal[
    "UPCOMING",
    "ONGOING",
    "COMPLETED",
    "CANCELLED",
    "POSTPONED",
    "RECURRING",
    "CANDIDATE",
    "CONFIRMED",
    "REJECTED",
]
AttendanceScenario = Literal["LOW", "EXPECTED", "HIGH"]
RegistryHealthStatus = Literal["HEALTHY", "DEGRADED", "UNAVAILABLE", "AWAITING_CREDENTIALS", "DISABLED"]


def _ensure_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("Datetime values crossing the API boundary must include timezone/UTC offset")
    return value.astimezone(timezone.utc)


class ContractModel(BaseModel):
    """Canonical strict Pydantic v2 base model for EventSense contracts."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EventDiscoveryRequest(ContractModel):
    city: str = Field(min_length=2, max_length=80)
    query_terms: list[str] = Field(min_length=1, max_length=8)
    time_window_hours: int = Field(default=168, ge=1, le=168)
    max_candidates: int = Field(default=5, ge=1, le=10)
    enabled_providers: list[str] = Field(
        default_factory=lambda: ["gdelt", "rss"],
        min_length=1,
        max_length=20,
    )

    @field_validator("query_terms")
    @classmethod
    def _validate_query_terms(cls, terms: list[str]) -> list[str]:
        cleaned = [term.strip() for term in terms if term and term.strip()]
        if not cleaned:
            raise ValueError("query_terms must contain at least one non-empty term")
        return cleaned


class SourceCandidate(ContractModel):
    discovery_provider: str
    source_type: str = Field(min_length=1, max_length=64)
    url: HttpUrl
    canonical_url: HttpUrl
    domain: str = Field(min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=500)
    snippet: str | None = Field(default=None, max_length=2000)
    published_at: datetime | None = None
    discovered_at: datetime

    @field_validator("published_at", "discovered_at")
    @classmethod
    def _normalize_utc(cls, v: datetime | None) -> datetime | None:
        return _ensure_utc_datetime(v)


class ProviderCandidateResult(ContractModel):
    """Internal output from Tanish's provider adapters; items are not the public API response."""

    provider: str
    status: ProviderStatus
    items: list[SourceCandidate] = Field(default_factory=list)
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, max_length=500)
    retryable: bool = False


class EventDiscoveryServiceResult(ContractModel):
    providers: list[ProviderCandidateResult]
    warnings: list[str] = Field(default_factory=list)


class ProviderRunSummary(ContractModel):
    """Public provider summary returned by FastAPI after Junaid persists candidates."""

    provider: str
    status: ProviderStatus
    candidate_count: int = Field(default=0, ge=0)
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, max_length=500)
    retryable: bool = False


class EventDiscoveryResponse(ContractModel):
    run_id: UUID
    status: DiscoveryRunStatus
    providers: list[ProviderRunSummary]
    source_ids: list[UUID] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime | None = None


class CrawlRequest(ContractModel):
    run_id: UUID
    source_ids: list[UUID] = Field(min_length=1, max_length=5)
    max_pages: int = Field(default=5, ge=1, le=5)


class CrawlTarget(ContractModel):
    source_id: UUID
    run_id: UUID
    url: HttpUrl
    discovery_provider: DiscoveryProvider
    domain: str


class CrawlPageResult(ContractModel):
    source_id: UUID
    fetch_provider: FetchProvider
    fetch_status: FetchStatus
    final_url: HttpUrl | None = None
    title: str | None = Field(default=None, max_length=500)
    markdown_text: str | None = Field(default=None, max_length=200_000)
    html_for_extraction: str | None = Field(default=None, max_length=500_000)
    content_hash: str | None = Field(default=None, max_length=80)
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, max_length=500)


class EventExtractionResult(ContractModel):
    source_id: UUID
    extraction_status: ExtractionStatus
    fields: dict[str, Any] = Field(default_factory=dict)
    field_provenance: dict[str, Any] = Field(default_factory=dict)
    evidence_summary: str | None = Field(default=None, max_length=2000)


class EventSourceRecord(ContractModel):
    source_id: UUID
    discovery_run_id: UUID
    event_id: UUID | None = None
    discovery_provider: DiscoveryProvider
    fetch_provider: FetchProvider | None = None
    source_type: str
    url: str
    canonical_url: str
    domain: str
    title: str | None = None
    snippet: str | None = None
    published_at: datetime | None = None
    discovered_at: datetime
    collected_at: datetime | None = None
    fetch_status: FetchStatus
    extraction_status: ExtractionStatus
    content_hash: str | None = None
    evidence_summary: str | None = None
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    field_provenance: dict[str, Any] = Field(default_factory=dict)
    crawl_attempts: int = 0
    eligible_for_crawl: bool = False
    error_code: str | None = None
    error_message: str | None = None


class DiscoveryRunDetailResponse(ContractModel):
    run_id: UUID
    city: str
    query_terms: list[str]
    status: DiscoveryRunStatus
    providers: list[ProviderRunSummary]
    source_ids: list[UUID] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime | None = None


class CrawlResponse(ContractModel):
    run_id: UUID
    processed_count: int
    sources: list[EventSourceRecord]
    event_ids: list[UUID] = Field(default_factory=list)


class EventCreateRequest(ContractModel):
    event_key: str | None = Field(default=None, max_length=120)
    event_origin: Literal["MANUAL_INPUT", "SEEDED_DEMO"] = "MANUAL_INPUT"
    name: str = Field(min_length=2, max_length=240)
    event_type: str = Field(default="concert", min_length=2, max_length=64)
    venue_name: str | None = Field(default=None, max_length=240)
    city: str = Field(default="Bengaluru", min_length=2, max_length=80)
    address: str | None = Field(default=None, max_length=400)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    start_at: datetime | None = None
    end_at: datetime | None = None
    attendance_low: int | None = Field(default=None, ge=0)
    attendance_high: int | None = Field(default=None, ge=0)
    attendance_basis: AttendanceBasis = "OPERATOR_ASSUMPTION"
    intensity: float = Field(default=1.0, ge=0.1, le=5.0)
    source_url: str | None = Field(default=None, max_length=500)
    source_summary: str | None = Field(default=None, max_length=1000)

    @field_validator("start_at", "end_at")
    @classmethod
    def _normalize_utc(cls, v: datetime | None) -> datetime | None:
        return _ensure_utc_datetime(v)

    @model_validator(mode="after")
    def _check_ranges(self) -> "EventCreateRequest":
        if self.attendance_low is not None and self.attendance_high is not None:
            if self.attendance_high < self.attendance_low:
                raise ValueError("attendance_high must be >= attendance_low")
        if self.start_at is not None and self.end_at is not None:
            if self.end_at < self.start_at:
                raise ValueError("end_at must be >= start_at")
        return self


class EventConfirmRequest(ContractModel):
    operator_id: str = Field(default="operator-1", min_length=1, max_length=120)
    accept_demo_assumptions: bool = False
    venue_name: str | None = Field(default=None, max_length=240)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    start_at: datetime | None = None
    end_at: datetime | None = None
    attendance_low: int | None = Field(default=None, ge=0)
    attendance_high: int | None = Field(default=None, ge=0)
    attendance_basis: AttendanceBasis | None = None
    intensity: float | None = Field(default=None, ge=0.1, le=5.0)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("start_at", "end_at")
    @classmethod
    def _normalize_utc(cls, v: datetime | None) -> datetime | None:
        return _ensure_utc_datetime(v)


class EventRecord(ContractModel):
    event_id: UUID
    event_key: str | None = None
    event_origin: EventOrigin
    name: str
    event_type: str
    venue_name: str | None = None
    city: str
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    attendance_low: int | None = None
    attendance_high: int | None = None
    attendance_basis: AttendanceBasis
    intensity: float
    verification_status: VerificationStatus
    status: EventLifecycleStatus
    source_ids: list[UUID] = Field(default_factory=list)
    field_provenance: dict[str, Any] = Field(default_factory=dict)
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    confirmation_notes: str | None = None
    created_at: datetime
    updated_at: datetime


class EventImpactRequest(ContractModel):
    simulation_id: UUID
    influence_radius_km: float = Field(default=3.0, gt=0.1, le=25.0)
    attendance_scenario: AttendanceScenario = "EXPECTED"


class AffectedCellImpact(ContractModel):
    cell_id: str
    distance_km: float
    impact_weight: float
    estimated_additional_demand_mbps: float
    reason: str


class EventImpactResponse(ContractModel):
    event_id: UUID
    simulation_id: UUID
    influence_radius_km: float
    attendance_scenario: AttendanceScenario
    affected_cells: list[AffectedCellImpact]
    total_estimated_uplift_mbps: float
    assumptions: dict[str, Any]
    created_at: datetime


class RealtimeScanRequest(ContractModel):
    city: str = Field(default="Bengaluru")
    query_terms: list[str] = Field(default_factory=lambda: ["concert", "festival", "stadium", "match", "Bengaluru"])
    auto_confirm: bool = Field(default=True)
    simulation_id: UUID | None = Field(default=None)


class RealtimeScanResponse(ContractModel):
    status: str
    discovered_sources_count: int
    events: list[EventRecord]
    selected_event: EventRecord | None = None
    surge_tower: dict[str, Any] | None = None
    mitigating_towers: list[dict[str, Any]] = Field(default_factory=list)
    load_distribution: list[dict[str, Any]] = Field(default_factory=list)
    justification: dict[str, Any] = Field(default_factory=dict)


class SourceRegistryItem(ContractModel):
    source_id: str
    platform: str
    display_name: str
    base_url: str
    connector_type: str
    enabled: bool
    access_method: str
    refresh_interval_sec: int
    geographic_scope: str = "Bengaluru"
    supported_categories: list[str] = Field(default_factory=list)
    last_collected_at: datetime | None = None
    last_error: str | None = None
    health_status: RegistryHealthStatus = "HEALTHY"
    created_at: datetime
    updated_at: datetime


class SourceRegistryUpdate(ContractModel):
    enabled: bool | None = None
    refresh_interval_sec: int | None = Field(default=None, ge=60, le=86400)


class SourceHealthResult(ContractModel):
    source_id: str
    connector_type: str
    health_status: RegistryHealthStatus
    message: str
    last_check_at: datetime
    latency_ms: float | None = None


class EventEvidenceRecord(ContractModel):
    evidence_id: str
    event_id: UUID
    source_platform: str
    source_url: str
    source_timestamp: datetime | None = None
    evidence_type: str
    extracted_text: str
    source_reliability: float = 0.8
    evidence_confidence: float = 0.8
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class EventHistoryRecord(ContractModel):
    history_id: str
    event_id: UUID
    change_type: str
    previous_state: dict[str, Any] = Field(default_factory=dict)
    new_state: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    recorded_at: datetime


class FieldAttributionItem(ContractModel):
    field_name: str
    chosen_value: Any
    source_platform: str
    source_reliability: float
    confidence: float
    basis: str  # CONFIRMED, INFERRED, ESTIMATED
    attribution_reason: str


class FieldConflictItem(ContractModel):
    field_name: str
    preferred_value: Any
    conflicting_value: Any
    preferred_source: str
    conflicting_source: str
    severity: str = "WARNING"  # CRITICAL, WARNING, INFO
    detected_at: datetime


class CanonicalEventDetailResponse(ContractModel):
    event: EventRecord
    evidence: list[EventEvidenceRecord] = Field(default_factory=list)
    field_attribution: dict[str, Any] = Field(default_factory=dict)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    resolution_metadata: dict[str, Any] = Field(default_factory=dict)
    history: list[EventHistoryRecord] = Field(default_factory=list)

