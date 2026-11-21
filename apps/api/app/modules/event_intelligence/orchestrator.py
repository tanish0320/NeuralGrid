from __future__ import annotations

import hashlib
import importlib
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from fastapi import HTTPException

from apps.api.app.api.websocket import ConnectionManager
from apps.api.app.config import Settings
from apps.api.app.core.database import parse_utc, utc_now
from apps.api.app.core.events import AuditLogger
from apps.api.app.core.url_policy import (
    DnsResolver,
    UrlPolicyError,
    canonicalize_url,
    validate_public_https_url,
    validate_redirect_url,
)
from apps.api.app.repositories.event_sources import EventSourceRepository
from apps.api.app.repositories.events import EventRepository
from apps.api.app.schemas.events import (
    CrawlPageResult,
    CrawlRequest,
    CrawlResponse,
    CrawlTarget,
    DiscoveryRunStatus,
    EventDiscoveryRequest,
    EventDiscoveryResponse,
    EventDiscoveryServiceResult,
    EventExtractionResult,
    EventRecord,
    EventSourceRecord,
    ProviderRunSummary,
)


class EventIntelligenceServiceProtocol(Protocol):
    """Contract implemented by Tanish under apps.api.app.modules.event_intelligence.service."""

    async def discover_candidates(
        self, request: EventDiscoveryRequest
    ) -> EventDiscoveryServiceResult: ...

    async def crawl_public_sources(
        self, sources: list[CrawlTarget]
    ) -> list[CrawlPageResult]: ...

    def extract_event_fields(
        self, page: CrawlPageResult
    ) -> EventExtractionResult: ...


def load_tanish_service() -> EventIntelligenceServiceProtocol | None:
    """Load Tanish's in-process service module if present; return None cleanly if absent."""
    try:
        mod = importlib.import_module("apps.api.app.modules.event_intelligence.service")
    except ModuleNotFoundError:
        return None
    required = ("discover_candidates", "crawl_public_sources", "extract_event_fields")
    if all(callable(getattr(mod, fn, None)) for fn in required):
        return mod  # type: ignore[return-value]
    return None


def _bounded_hash(text: str | None) -> str | None:
    if not text:
        return None
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _parse_optional_dt(val: Any) -> datetime | None:
    if val is None or val == "":
        return None
    try:
        return parse_utc(val)
    except Exception:
        return None


def _parse_optional_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_optional_int(val: Any) -> int | None:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


class EventIntelligenceOrchestrator:
    """Junaid-owned orchestration, URL safety enforcement, persistence, and twin hand-off."""

    def __init__(
        self,
        *,
        settings: Settings,
        source_repo: EventSourceRepository,
        event_repo: EventRepository,
        audit: AuditLogger,
        ws_manager: ConnectionManager,
        service: EventIntelligenceServiceProtocol | None = None,
        dns_resolver: DnsResolver | None = None,
    ) -> None:
        self.settings = settings
        self.source_repo = source_repo
        self.event_repo = event_repo
        self.audit = audit
        self.ws = ws_manager
        self._injected_service = service
        self._dns_resolver = dns_resolver

    def get_service(self) -> EventIntelligenceServiceProtocol | None:
        if self._injected_service is not None:
            return self._injected_service
        return load_tanish_service()

    def set_service(self, service: EventIntelligenceServiceProtocol | None) -> None:
        self._injected_service = service

    async def run_discovery(self, request: EventDiscoveryRequest) -> EventDiscoveryResponse:
        run_id = uuid4()
        started_at = utc_now()
        self.source_repo.create_discovery_run(run_id, request)
        await self.ws.broadcast(
            "event_discovery.started",
            {"run_id": str(run_id), "city": request.city, "providers": request.enabled_providers},
        )

        service = self.get_service()
        provider_summaries: list[ProviderRunSummary] = []
        persisted_source_ids: list[UUID] = []
        seen_source_ids: set[UUID] = set()
        warnings: list[str] = []

        if service is None:
            warnings.append(
                "Tanish EventSense collector service is not installed; seeded Palace Grounds demo remains available."
            )
            for prov in request.enabled_providers:
                summary = ProviderRunSummary(
                    provider=prov,
                    status="FAILED",
                    candidate_count=0,
                    error_code="PROVIDER_NOT_INSTALLED",
                    error_message="Collector module apps.api.app.modules.event_intelligence.service is not present.",
                    retryable=False,
                )
                provider_summaries.append(summary)
                await self.ws.broadcast(
                    "event_discovery.provider_status",
                    {"run_id": str(run_id), **summary.model_dump(mode="json")},
                )
        else:
            try:
                service_result = await service.discover_candidates(request)
                warnings.extend(service_result.warnings)
                by_provider = {p.provider: p for p in service_result.providers}
            except Exception as exc:
                by_provider = {}
                warnings.append(f"Collector service raised an unexpected error: {type(exc).__name__}")
                for prov in request.enabled_providers:
                    provider_summaries.append(
                        ProviderRunSummary(
                            provider=prov,
                            status="FAILED",
                            candidate_count=0,
                            error_code="COLLECTOR_ERROR",
                            error_message=str(exc)[:300],
                            retryable=True,
                        )
                    )

            if by_provider or not provider_summaries:
                allowed = self.settings.allowed_domains_set
                for prov in request.enabled_providers:
                    p_res = by_provider.get(prov)
                    if p_res is None:
                        summary = ProviderRunSummary(
                            provider=prov,
                            status="SKIPPED",
                            candidate_count=0,
                            error_code="PROVIDER_SKIPPED",
                            error_message="Enabled provider returned no result summary.",
                            retryable=False,
                        )
                        provider_summaries.append(summary)
                        await self.ws.broadcast(
                            "event_discovery.provider_status",
                            {"run_id": str(run_id), **summary.model_dump(mode="json")},
                        )
                        continue

                    persisted_for_provider = 0
                    for candidate in p_res.items[: request.max_candidates]:
                        raw_url = str(candidate.url)
                        try:
                            canon = canonicalize_url(raw_url)
                        except UrlPolicyError:
                            canon = str(candidate.canonical_url)

                        try:
                            validated_url = validate_public_https_url(
                                raw_url,
                                allowed,
                                resolver=self._dns_resolver,
                            )
                            canon = validated_url
                            fetch_status = "NOT_FETCHED"
                            err_code = None
                            err_msg = None
                        except UrlPolicyError as exc:
                            fetch_status = "BLOCKED_POLICY"
                            err_code = exc.error_code
                            err_msg = str(exc)[:450]

                        source_id, inserted = self.source_repo.upsert_candidate_source(
                            run_id=run_id,
                            discovery_provider=candidate.discovery_provider,
                            source_type=candidate.source_type,
                            url=raw_url,
                            canonical_url=canon,
                            domain=candidate.domain.lower(),
                            title=candidate.title,
                            snippet=candidate.snippet,
                            published_at=candidate.published_at,
                            discovered_at=candidate.discovered_at,
                            fetch_status=fetch_status,
                            error_code=err_code,
                            error_message=err_msg,
                        )
                        if source_id not in seen_source_ids:
                            seen_source_ids.add(source_id)
                            persisted_source_ids.append(source_id)
                        if inserted:
                            persisted_for_provider += 1

                    summary = ProviderRunSummary(
                        provider=p_res.provider,
                        status=p_res.status,
                        candidate_count=persisted_for_provider,
                        error_code=p_res.error_code,
                        error_message=p_res.error_message,
                        retryable=p_res.retryable,
                    )
                    provider_summaries.append(summary)
                    await self.ws.broadcast(
                        "event_discovery.provider_status",
                        {"run_id": str(run_id), **summary.model_dump(mode="json")},
                    )

        statuses = [p.status for p in provider_summaries]
        if all(s == "SUCCEEDED" for s in statuses):
            final_status: DiscoveryRunStatus = "SUCCEEDED"
        elif any(s in ("SUCCEEDED", "PARTIAL") for s in statuses):
            final_status = "PARTIAL"
        elif all(s == "SKIPPED" for s in statuses):
            final_status = "SKIPPED"
        else:
            final_status = "FAILED"

        self.source_repo.complete_discovery_run(run_id, final_status, provider_summaries, warnings)
        completed_at = utc_now()
        self.audit.log(
            actor="system:orchestrator",
            action="event_discovery.completed",
            entity_type="event_discovery_run",
            entity_id=str(run_id),
            details={
                "status": final_status,
                "source_count": len(persisted_source_ids),
                "providers": [p.model_dump(mode="json") for p in provider_summaries],
            },
        )
        await self.ws.broadcast(
            "event_discovery.completed",
            {
                "run_id": str(run_id),
                "status": final_status,
                "source_ids": [str(s) for s in persisted_source_ids],
            },
        )

        return EventDiscoveryResponse(
            run_id=run_id,
            status=final_status,
            providers=provider_summaries,
            source_ids=persisted_source_ids,
            warnings=warnings,
            started_at=started_at,
            completed_at=completed_at,
        )

    async def run_crawl(self, request: CrawlRequest) -> CrawlResponse:
        run = self.source_repo.get_discovery_run(request.run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Discovery run {request.run_id} not found")

        cap = min(request.max_pages, self.settings.eventsense_max_crawl_pages, 5)
        loaded_sources: list[EventSourceRecord] = []
        for sid in request.source_ids[:cap]:
            src = self.source_repo.get_source(sid)
            if src is None:
                raise HTTPException(status_code=404, detail=f"Source {sid} not found")
            if src.discovery_run_id != request.run_id:
                raise HTTPException(
                    status_code=409,
                    detail=f"Source {sid} belongs to run {src.discovery_run_id}, not {request.run_id}",
                )
            loaded_sources.append(src)

        allowed = self.settings.allowed_domains_set
        approved_targets: list[CrawlTarget] = []
        updated_sources: dict[UUID, EventSourceRecord] = {}

        for src in loaded_sources:
            try:
                validated_url = validate_public_https_url(
                    src.url,
                    allowed,
                    resolver=self._dns_resolver,
                )
                approved_targets.append(
                    CrawlTarget(
                        source_id=src.source_id,
                        run_id=request.run_id,
                        url=validated_url,  # type: ignore[arg-type]
                        discovery_provider=src.discovery_provider,
                        domain=src.domain,
                    )
                )
            except UrlPolicyError as exc:
                rejected = self.source_repo.update_source_crawl_result(
                    source_id=src.source_id,
                    fetch_provider=None,
                    fetch_status="BLOCKED_POLICY",
                    extraction_status="NOT_RUN",
                    collected_at=utc_now(),
                    error_code=exc.error_code,
                    error_message=str(exc)[:450],
                )
                updated_sources[src.source_id] = rejected
                await self.ws.broadcast(
                    "event_source.crawl_failed",
                    {
                        "run_id": str(request.run_id),
                        "source_id": str(src.source_id),
                        "error_code": exc.error_code,
                    },
                )

        linked_event_ids: list[UUID] = []
        service = self.get_service()

        if approved_targets:
            for tgt in approved_targets:
                await self.ws.broadcast(
                    "event_source.crawl_started",
                    {"run_id": str(request.run_id), "source_id": str(tgt.source_id)},
                )

            if service is None:
                for tgt in approved_targets:
                    failed = self.source_repo.update_source_crawl_result(
                        source_id=tgt.source_id,
                        fetch_provider=None,
                        fetch_status="FAILED",
                        extraction_status="NOT_RUN",
                        collected_at=utc_now(),
                        error_code="PROVIDER_NOT_INSTALLED",
                        error_message="Tanish crawl service is not installed; seeded demo fallback remains available.",
                    )
                    updated_sources[tgt.source_id] = failed
                    await self.ws.broadcast(
                        "event_source.crawl_failed",
                        {
                            "run_id": str(request.run_id),
                            "source_id": str(tgt.source_id),
                            "error_code": "PROVIDER_NOT_INSTALLED",
                        },
                    )
            else:
                crawl_results = await service.crawl_public_sources(approved_targets)
                by_sid = {res.source_id: res for res in crawl_results}
                for tgt in approved_targets:
                    page = by_sid.get(tgt.source_id)
                    if page is None:
                        failed = self.source_repo.update_source_crawl_result(
                            source_id=tgt.source_id,
                            fetch_provider=None,
                            fetch_status="FAILED",
                            extraction_status="NOT_RUN",
                            collected_at=utc_now(),
                            error_code="MISSING_CRAWL_RESULT",
                            error_message="Crawler did not return a result for target source.",
                        )
                        updated_sources[tgt.source_id] = failed
                        continue

                    # Revalidate final URL after redirects (Integration Guide §5.5)
                    if page.final_url is not None:
                        try:
                            validate_redirect_url(
                                str(page.final_url),
                                allowed,
                                resolver=self._dns_resolver,
                            )
                        except UrlPolicyError as exc:
                            blocked = self.source_repo.update_source_crawl_result(
                                source_id=tgt.source_id,
                                fetch_provider=page.fetch_provider,
                                fetch_status="BLOCKED_POLICY",
                                extraction_status="NOT_RUN",
                                collected_at=utc_now(),
                                error_code=exc.error_code,
                                error_message=str(exc)[:450],
                            )
                            updated_sources[tgt.source_id] = blocked
                            await self.ws.broadcast(
                                "event_source.crawl_failed",
                                {
                                    "run_id": str(request.run_id),
                                    "source_id": str(tgt.source_id),
                                    "error_code": exc.error_code,
                                },
                            )
                            continue

                    if page.fetch_status != "SUCCEEDED":
                        failed = self.source_repo.update_source_crawl_result(
                            source_id=tgt.source_id,
                            fetch_provider=page.fetch_provider,
                            fetch_status=page.fetch_status,
                            extraction_status="NOT_RUN",
                            collected_at=utc_now(),
                            title=page.title,
                            content_hash=page.content_hash,
                            error_code=page.error_code,
                            error_message=page.error_message,
                        )
                        updated_sources[tgt.source_id] = failed
                        await self.ws.broadcast(
                            "event_source.crawl_failed",
                            {
                                "run_id": str(request.run_id),
                                "source_id": str(tgt.source_id),
                                "error_code": page.error_code or page.fetch_status,
                            },
                        )
                        continue

                    # Truncate bounded text cleanly before extraction/hashing
                    bounded_md = (
                        page.markdown_text[: self.settings.eventsense_max_text_bytes]
                        if page.markdown_text
                        else None
                    )
                    content_hash = page.content_hash or _bounded_hash(bounded_md)
                    extraction = service.extract_event_fields(
                        page.model_copy(update={"markdown_text": bounded_md})
                    )

                    saved_src = self.source_repo.update_source_crawl_result(
                        source_id=tgt.source_id,
                        fetch_provider=page.fetch_provider,
                        fetch_status=page.fetch_status,
                        extraction_status=extraction.extraction_status,
                        collected_at=utc_now(),
                        title=page.title,
                        content_hash=content_hash,
                        evidence_summary=extraction.evidence_summary,
                        extracted_fields=extraction.fields,
                        field_provenance=extraction.field_provenance,
                        error_code=page.error_code,
                        error_message=page.error_message,
                    )

                    event_rec = self._upsert_normalised_event_from_extraction(
                        source=saved_src,
                        extraction=extraction,
                        city_hint=run.city,
                    )
                    if event_rec is not None:
                        saved_src = self.source_repo.update_source_crawl_result(
                            source_id=saved_src.source_id,
                            fetch_provider=saved_src.fetch_provider,
                            fetch_status=saved_src.fetch_status,
                            extraction_status=saved_src.extraction_status,
                            collected_at=saved_src.collected_at,
                            event_id=event_rec.event_id,
                            increment_attempt=False,
                        )
                        if event_rec.event_id not in linked_event_ids:
                            linked_event_ids.append(event_rec.event_id)
                        await self.ws.broadcast(
                            "event.normalised",
                            {
                                "event_id": str(event_rec.event_id),
                                "verification_status": event_rec.verification_status,
                                "source_id": str(saved_src.source_id),
                            },
                        )

                    updated_sources[tgt.source_id] = saved_src
                    await self.ws.broadcast(
                        "event_source.crawl_completed",
                        {
                            "run_id": str(request.run_id),
                            "source_id": str(tgt.source_id),
                            "extraction_status": saved_src.extraction_status,
                        },
                    )

        ordered_results = [updated_sources[src.source_id] for src in loaded_sources]
        self.audit.log(
            actor="system:orchestrator",
            action="event_source.crawl_batch",
            entity_type="event_discovery_run",
            entity_id=str(request.run_id),
            details={
                "processed": len(ordered_results),
                "event_ids": [str(eid) for eid in linked_event_ids],
            },
        )
        return CrawlResponse(
            run_id=request.run_id,
            processed_count=len(ordered_results),
            sources=ordered_results,
            event_ids=linked_event_ids,
        )

    def _upsert_normalised_event_from_extraction(
        self,
        *,
        source: EventSourceRecord,
        extraction: EventExtractionResult,
        city_hint: str,
    ) -> EventRecord | None:
        fields = extraction.fields or {}
        name = (fields.get("event_name") or fields.get("name") or source.title or "").strip()
        if not name:
            return None

        event_type = str(fields.get("event_type") or "public_event").strip()
        venue_name = fields.get("venue_name") or fields.get("venue")
        venue_name = str(venue_name).strip() if venue_name else None
        city = str(fields.get("city") or city_hint).strip()
        address = str(fields["address"]).strip() if fields.get("address") else None
        lat = _parse_optional_float(fields.get("latitude"))
        lon = _parse_optional_float(fields.get("longitude"))
        start_at = _parse_optional_dt(fields.get("start_at"))
        end_at = _parse_optional_dt(fields.get("end_at"))
        att_low = _parse_optional_int(fields.get("attendance_low"))
        att_high = _parse_optional_int(fields.get("attendance_high"))
        att_basis = "SOURCE_EVIDENCE" if (att_low is not None or att_high is not None) else "UNKNOWN"

        # Conservative matching: only match existing SOURCE_DISCOVERED event when name + venue + start date ALL match
        matched_event: EventRecord | None = None
        if venue_name and start_at:
            target_date = start_at.date()
            for candidate_ev in self.event_repo.list_events():
                if candidate_ev.event_origin != "SOURCE_DISCOVERED":
                    continue
                if (
                    candidate_ev.name.strip().lower() == name.lower()
                    and (candidate_ev.venue_name or "").strip().lower() == venue_name.lower()
                    and candidate_ev.start_at is not None
                    and candidate_ev.start_at.date() == target_date
                ):
                    matched_event = candidate_ev
                    break

        now = utc_now()
        if matched_event is not None:
            new_source_ids = list(matched_event.source_ids)
            if source.source_id not in new_source_ids:
                new_source_ids.append(source.source_id)

            provenance = dict(matched_event.field_provenance)
            conflicts = list(provenance.get("conflicts", []))

            for field_name, incoming_val in (
                ("venue_name", venue_name),
                ("latitude", lat),
                ("longitude", lon),
                ("start_at", start_at),
                ("end_at", end_at),
                ("attendance_low", att_low),
                ("attendance_high", att_high),
            ):
                existing_val = getattr(matched_event, field_name)
                if existing_val is not None and incoming_val is not None and existing_val != incoming_val:
                    conflicts.append(
                        {
                            "field": field_name,
                            "existing": str(existing_val),
                            "incoming": str(incoming_val),
                            "source_id": str(source.source_id),
                        }
                    )

            if conflicts:
                provenance["conflicts"] = conflicts

            # Corroborated only when >= 2 independent sources (distinct domains + distinct hashes) agree without conflict
            all_sources = [self.source_repo.get_source(sid) for sid in new_source_ids]
            distinct_domains = {s.domain for s in all_sources if s is not None}
            distinct_hashes = {s.content_hash for s in all_sources if s is not None and s.content_hash}
            if len(distinct_domains) >= 2 and len(distinct_hashes) >= 2:
                verification = "CORROBORATED"
            else:
                verification = "SINGLE_SOURCE"

            updated = matched_event.model_copy(
                update={
                    "source_ids": new_source_ids,
                    "field_provenance": provenance,
                    "verification_status": verification,
                    "updated_at": now,
                }
            )
            return self.event_repo.update_event(updated)

        verification_status = (
            "SINGLE_SOURCE" if extraction.extraction_status in ("SUCCEEDED", "PARTIAL") else "UNVERIFIED"
        )
        new_event = EventRecord(
            event_id=uuid4(),
            event_key=None,
            event_origin="SOURCE_DISCOVERED",
            name=name,
            event_type=event_type,
            venue_name=venue_name,
            city=city,
            address=address,
            latitude=lat,
            longitude=lon,
            start_at=start_at,
            end_at=end_at,
            attendance_low=att_low,
            attendance_high=att_high,
            attendance_basis=att_basis,
            intensity=1.0,
            verification_status=verification_status,
            status="CANDIDATE",
            source_ids=[source.source_id],
            field_provenance={
                "source_id": str(source.source_id),
                "fields": extraction.field_provenance,
            },
            created_at=now,
            updated_at=now,
        )
        return self.event_repo.create_event(new_event)
