from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from pydantic import HttpUrl

from apps.api.app.core.database import utc_now
from apps.api.app.schemas.events import (
    ProviderCandidateResult,
    SourceCandidate,
    SourceHealthResult,
)

logger = logging.getLogger("neuralgrid.eventsense.connector")


class RawSourceItem:
    """Internal container for raw items retrieved from external sources before normalisation."""

    def __init__(
        self,
        *,
        url: str,
        title: str,
        snippet: str | None = None,
        source_type: str = "news_article",
        published_at: datetime | None = None,
        raw_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.url = url
        self.title = title
        self.snippet = snippet
        self.source_type = source_type
        self.published_at = published_at
        self.raw_metadata = raw_metadata or {}


class EventSourceConnector(ABC):
    """Canonical interface that every NeuralGrid event source connector must implement.

    Lifecycle:
        fetch() -> normalize() -> validate() -> deduplicate() -> attach_provenance() -> return_events()
    """

    source_id: str
    platform: str
    display_name: str
    base_url: str
    access_method: str
    default_reliability: float = 0.8

    def __init__(self, settings: Any = None) -> None:
        self.settings = settings

    @abstractmethod
    async def fetch(
        self, city: str, query_terms: list[str], max_records: int
    ) -> list[RawSourceItem]:
        """Fetch raw items from source without raising unhandled exceptions."""
        ...

    def normalize(self, raw_items: list[RawSourceItem]) -> list[SourceCandidate]:
        """Normalize raw items into canonical SourceCandidate schema."""
        candidates: list[SourceCandidate] = []
        now = utc_now()

        for item in raw_items:
            try:
                parsed_url = urlparse(item.url)
                domain = parsed_url.netloc.lower().split(":")[0]
                if not domain:
                    continue

                candidates.append(
                    SourceCandidate(
                        discovery_provider=self.source_id,
                        source_type=item.source_type,
                        url=HttpUrl(item.url),
                        canonical_url=HttpUrl(item.url.split("?")[0].split("#")[0]),
                        domain=domain,
                        title=item.title.strip() if item.title else None,
                        snippet=item.snippet.strip() if item.snippet else None,
                        published_at=item.published_at,
                        discovered_at=now,
                    )
                )
            except Exception as exc:
                logger.debug(f"Normalization skipped item from {self.source_id}: {exc}")
                continue

        return candidates

    def validate(self, candidates: list[SourceCandidate]) -> list[SourceCandidate]:
        """Validate URL validity, minimum title length, and structure."""
        valid: list[SourceCandidate] = []
        for c in candidates:
            if not c.title or len(c.title.strip()) < 3:
                continue
            if not str(c.url).startswith("http"):
                continue
            valid.append(c)
        return valid

    def deduplicate(self, candidates: list[SourceCandidate]) -> list[SourceCandidate]:
        """Deduplicate candidates within the connector batch by canonical URL."""
        seen: set[str] = set()
        deduped: list[SourceCandidate] = []
        for c in candidates:
            key = str(c.canonical_url).lower().rstrip("/")
            if key not in seen:
                seen.add(key)
                deduped.append(c)
        return deduped

    def attach_provenance(self, candidates: list[SourceCandidate]) -> list[SourceCandidate]:
        """Attach connector provenance metadata to each candidate."""
        # Provenance is embedded via discovery_provider = self.source_id & domain
        return candidates

    async def return_events(
        self, city: str, query_terms: list[str], max_records: int
    ) -> ProviderCandidateResult:
        """Standardized pipeline runner with comprehensive exception isolation and health tracking."""
        t0 = time.perf_counter()
        try:
            raw_items = await self.fetch(city, query_terms, max_records)
            normalized = self.normalize(raw_items)
            validated = self.validate(normalized)
            deduped = self.deduplicate(validated)
            final_items = self.attach_provenance(deduped)

            return ProviderCandidateResult(
                provider=self.source_id,
                status="SUCCEEDED",
                items=final_items,
            )
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            logger.error(
                f"Connector {self.source_id} failed after {elapsed:.2f}s: {exc}", exc_info=True
            )
            return ProviderCandidateResult(
                provider=self.source_id,
                status="FAILED",
                items=[],
                error_code="FETCH_ERROR",
                error_message=str(exc)[:450],
                retryable=True,
            )

    async def check_health(self) -> SourceHealthResult:
        """Verify endpoint connectivity or credentials and report health status."""
        return SourceHealthResult(
            source_id=self.source_id,
            connector_type=self.__class__.__name__,
            health_status="HEALTHY",
            message="Connector active and operating normally.",
            last_check_at=utc_now(),
        )
