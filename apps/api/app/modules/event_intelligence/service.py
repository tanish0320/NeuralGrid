from __future__ import annotations

import logging
from typing import Any

from apps.api.app.config import Settings
from apps.api.app.modules.event_intelligence.connectors.registry import ConnectorRegistry
from apps.api.app.modules.event_intelligence.extraction.page_text_extractor import extract_page_text_fallback
from apps.api.app.modules.event_intelligence.extraction.schema_org_extractor import extract_schema_org_event
from apps.api.app.modules.event_intelligence.normalization.deduplication import deduplicate_source_candidates
from apps.api.app.modules.event_intelligence.normalization.event_normalizer import (
    determine_extraction_status,
    parse_datetime_to_utc,
)
from apps.api.app.modules.event_intelligence.providers.crawl4ai_provider import crawl_targets
from apps.api.app.modules.event_intelligence.providers.gdelt_doc_provider import query_gdelt_doc
from apps.api.app.modules.event_intelligence.providers.rss_provider import parse_rss_feeds
from apps.api.app.schemas.events import (
    CrawlPageResult,
    CrawlTarget,
    EventDiscoveryRequest,
    EventDiscoveryServiceResult,
    EventExtractionResult,
    ExtractionStatus,
    ProviderCandidateResult,
)

logger = logging.getLogger("neuralgrid.eventsense.service")


class EventIntelligenceService:
    """Canonical Tanish in-process EventSense service implementing EventIntelligenceServiceProtocol."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.registry = ConnectorRegistry(self.settings)

    async def discover_candidates(
        self, request: EventDiscoveryRequest
    ) -> EventDiscoveryServiceResult:
        """Runs multi-source discovery across configured connectors (GDELT, RSS, Ticketing, Social)."""
        provider_results: list[ProviderCandidateResult] = []
        warnings: list[str] = []

        # Run discovery through the central connector registry
        registry_results = await self.registry.run_discovery(
            city=request.city,
            query_terms=request.query_terms,
            max_records=request.max_candidates,
            target_source_ids=request.enabled_providers,
        )

        for res in registry_results:
            if res.items:
                res.items = deduplicate_source_candidates(res.items)
            provider_results.append(res)

        # Fallback GDELT / RSS if request specifically requested legacy providers and registry had none
        if not provider_results and ("gdelt" in request.enabled_providers or "rss" in request.enabled_providers):
            if "gdelt" in request.enabled_providers and self.settings.eventsense_enable_gdelt:
                gdelt_res = await query_gdelt_doc(
                    city=request.city,
                    query_terms=request.query_terms,
                    max_records=request.max_candidates,
                    timeout_seconds=3.5,
                )
                if gdelt_res.items:
                    gdelt_res.items = deduplicate_source_candidates(gdelt_res.items)
                provider_results.append(gdelt_res)

        return EventDiscoveryServiceResult(
            providers=provider_results,
            warnings=warnings,
        )

    async def crawl_public_sources(
        self, sources: list[CrawlTarget]
    ) -> list[CrawlPageResult]:
        """Fetch orchestrator-validated CrawlTarget records (robots check on, serial, max 5)."""
        timeout = self.settings.eventsense_crawl_timeout_seconds
        return await crawl_targets(sources, timeout_seconds=timeout)

    def extract_event_fields(
        self, page: CrawlPageResult
    ) -> EventExtractionResult:
        """Extract Schema.org Event JSON-LD first, then bounded Markdown fallback.
        
        Leaves unknown fields null. Never fabricates attendance, coordinates or dates.
        """
        if page.fetch_status != "SUCCEEDED":
            return EventExtractionResult(
                source_id=page.source_id,
                extraction_status="NOT_RUN",
                fields={},
                field_provenance={},
                evidence_summary=f"Fetch did not succeed (status: {page.fetch_status})",
            )

        # 1. Try Schema.org JSON-LD first
        schema_result = extract_schema_org_event(page.html_for_extraction)
        if schema_result is not None:
            fields, prov, evidence_summary = schema_result
            # Normalize dates in fields if present
            if fields.get("start_at"):
                dt = parse_datetime_to_utc(fields["start_at"])
                if dt:
                    fields["start_at"] = dt
            if fields.get("end_at"):
                dt = parse_datetime_to_utc(fields["end_at"])
                if dt:
                    fields["end_at"] = dt

            status = determine_extraction_status(fields)
            return EventExtractionResult(
                source_id=page.source_id,
                extraction_status=status,
                fields=fields,
                field_provenance=prov,
                evidence_summary=evidence_summary,
            )

        # 2. Text / Markdown Fallback
        text_fields, text_prov, text_evidence = extract_page_text_fallback(
            title=page.title,
            markdown_text=page.markdown_text,
            html=page.html_for_extraction,
        )

        status = determine_extraction_status(text_fields)
        return EventExtractionResult(
            source_id=page.source_id,
            extraction_status=status,
            fields=text_fields,
            field_provenance=text_prov,
            evidence_summary=text_evidence,
        )


# Global default instance and top-level module functions for backward/forward compatibility
_default_service = EventIntelligenceService()
registry = _default_service.registry


async def discover_candidates(request: EventDiscoveryRequest) -> EventDiscoveryServiceResult:
    return await _default_service.discover_candidates(request)


async def crawl_public_sources(sources: list[CrawlTarget]) -> list[CrawlPageResult]:
    return await _default_service.crawl_public_sources(sources)


def extract_event_fields(page: CrawlPageResult) -> EventExtractionResult:
    return _default_service.extract_event_fields(page)
