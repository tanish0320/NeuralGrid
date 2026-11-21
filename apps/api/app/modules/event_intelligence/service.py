from __future__ import annotations

import logging
from typing import Any

from apps.api.app.config import Settings
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

    async def discover_candidates(
        self, request: EventDiscoveryRequest
    ) -> EventDiscoveryServiceResult:
        """Call enabled GDELT DOC / RSS adapters and return structured ProviderCandidateResult for each."""
        provider_results: list[ProviderCandidateResult] = []
        warnings: list[str] = []

        # 1. GDELT DOC 2.0 Discovery
        if "gdelt" in request.enabled_providers:
            if self.settings.eventsense_enable_gdelt and self.settings.gdelt_enabled:
                gdelt_res = await query_gdelt_doc(
                    city=request.city,
                    query_terms=request.query_terms,
                    max_records=request.max_candidates,
                    timeout_seconds=8.0,
                )
                if gdelt_res.items:
                    gdelt_res.items = deduplicate_source_candidates(gdelt_res.items)
                provider_results.append(gdelt_res)
            else:
                provider_results.append(
                    ProviderCandidateResult(
                        provider="gdelt",
                        status="SKIPPED",
                        items=[],
                        error_code="PROVIDER_DISABLED",
                        error_message="GDELT discovery is disabled in settings.",
                    )
                )

        # 2. RSS/Atom Feeds Discovery
        if "rss" in request.enabled_providers:
            if self.settings.eventsense_enable_rss:
                feed_urls_str = self.settings.eventsense_rss_feeds.strip()
                feed_urls = [u.strip() for u in feed_urls_str.split(",") if u.strip()]
                if not feed_urls:
                    # If no feeds configured in env, return clean SKIPPED or empty
                    provider_results.append(
                        ProviderCandidateResult(
                            provider="rss",
                            status="SKIPPED",
                            items=[],
                            error_code="NO_FEEDS_CONFIGURED",
                            error_message="No RSS feed URLs configured in EVENTSENSE_RSS_FEEDS.",
                        )
                    )
                else:
                    rss_res = parse_rss_feeds(
                        feed_urls=feed_urls,
                        query_terms=request.query_terms,
                        max_records=request.max_candidates,
                    )
                    if rss_res.items:
                        rss_res.items = deduplicate_source_candidates(rss_res.items)
                    provider_results.append(rss_res)
            else:
                provider_results.append(
                    ProviderCandidateResult(
                        provider="rss",
                        status="SKIPPED",
                        items=[],
                        error_code="PROVIDER_DISABLED",
                        error_message="RSS discovery is disabled in settings.",
                    )
                )

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


async def discover_candidates(request: EventDiscoveryRequest) -> EventDiscoveryServiceResult:
    return await _default_service.discover_candidates(request)


async def crawl_public_sources(sources: list[CrawlTarget]) -> list[CrawlPageResult]:
    return await _default_service.crawl_public_sources(sources)


def extract_event_fields(page: CrawlPageResult) -> EventExtractionResult:
    return _default_service.extract_event_fields(page)
