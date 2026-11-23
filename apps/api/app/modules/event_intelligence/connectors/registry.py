from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING
from apps.api.app.core.database import utc_now
from apps.api.app.modules.event_intelligence.connectors.base import EventSourceConnector
from apps.api.app.modules.event_intelligence.connectors.crawl4ai_web import Crawl4AIConnector
from apps.api.app.modules.event_intelligence.connectors.gdelt import GDELTConnector
from apps.api.app.modules.event_intelligence.connectors.rss_news import RSSNewsConnector
from apps.api.app.modules.event_intelligence.connectors.social_instagram import InstagramConnector
from apps.api.app.modules.event_intelligence.connectors.social_reddit import RedditConnector
from apps.api.app.modules.event_intelligence.connectors.social_telegram import TelegramConnector
from apps.api.app.modules.event_intelligence.connectors.social_twitter import TwitterXConnector
from apps.api.app.modules.event_intelligence.connectors.social_youtube import YouTubeConnector
from apps.api.app.modules.event_intelligence.connectors.ticketing import (
    AllEventsConnector,
    BookMyShowConnector,
    DistrictConnector,
)
from apps.api.app.schemas.events import ProviderCandidateResult, SourceHealthResult

if TYPE_CHECKING:
    from apps.api.app.repositories.source_registry import SourceRegistryRepository

logger = logging.getLogger("neuralgrid.eventsense.connectors.registry")


class ConnectorRegistry:
    """Central registry and dispatch coordinator for all NeuralGrid event source connectors."""

    def __init__(self, settings: object = None) -> None:
        self.settings = settings
        self._connectors: dict[str, EventSourceConnector] = {}
        self._register_default_connectors()

    def _register_default_connectors(self) -> None:
        # News & RSS
        self.register(GDELTConnector(self.settings))
        self.register(RSSNewsConnector("src_deccanherald_rss", "Deccan Herald Bengaluru", settings=self.settings))
        self.register(RSSNewsConnector("src_thehindu_rss", "The Hindu Bengaluru", settings=self.settings))
        self.register(RSSNewsConnector("src_timesofindia_rss", "Times of India Bengaluru", settings=self.settings))
        self.register(RSSNewsConnector("src_indianexpress_rss", "The Indian Express Bengaluru", settings=self.settings))
        self.register(RSSNewsConnector("src_bangaloremirror_rss", "Bangalore Mirror City Pulse", settings=self.settings))
        self.register(Crawl4AIConnector(self.settings))

        # Ticketing
        self.register(BookMyShowConnector(self.settings))
        self.register(DistrictConnector(self.settings))
        self.register(AllEventsConnector(self.settings))

        # Social Media
        self.register(TwitterXConnector(self.settings))
        self.register(InstagramConnector(self.settings))
        self.register(RedditConnector(self.settings))
        self.register(YouTubeConnector(self.settings))
        self.register(TelegramConnector(self.settings))

    def register(self, connector: EventSourceConnector) -> None:
        self._connectors[connector.source_id] = connector

    def get(self, source_id: str) -> EventSourceConnector | None:
        return self._connectors.get(source_id)

    def list_all(self) -> list[EventSourceConnector]:
        return list(self._connectors.values())

    async def run_discovery(
        self,
        city: str,
        query_terms: list[str],
        max_records: int = 5,
        target_source_ids: list[str] | None = None,
        registry_repo: SourceRegistryRepository | None = None,
    ) -> list[ProviderCandidateResult]:
        """Runs concurrent discovery across all targeted connectors with total error isolation."""
        # 1. Determine active connectors based on registry repo and target list
        active_connectors: list[EventSourceConnector] = []
        enabled_map: dict[str, bool] = {}

        if registry_repo:
            try:
                db_sources = registry_repo.list_sources()
                enabled_map = {s.source_id: s.enabled for s in db_sources}
            except Exception as e:
                logger.warning(f"Failed to query source registry DB: {e}")

        for cid, conn in self._connectors.items():
            # If target list specified, must match
            if target_source_ids is not None:
                # Also allow matching by provider name prefix (e.g. 'gdelt', 'rss')
                matches = any(
                    target == cid or cid.startswith(f"src_{target}") or (target in cid)
                    for target in target_source_ids
                )
                if not matches:
                    continue

            # Check DB enabled state
            if enabled_map and not enabled_map.get(cid, True):
                continue

            active_connectors.append(conn)

        if not active_connectors:
            logger.info("No active connectors matched the discovery filter.")
            return []

        # 2. Execute concurrently with exception protection
        async def _run_single(connector: EventSourceConnector) -> ProviderCandidateResult:
            t0 = time.perf_counter()
            try:
                res = await connector.return_events(city, query_terms, max_records)
                elapsed = time.perf_counter() - t0

                if registry_repo:
                    if res.status == "SUCCEEDED":
                        registry_repo.record_run_result(
                            connector.source_id,
                            health_status="HEALTHY",
                            collected_at=utc_now(),
                        )
                    else:
                        registry_repo.record_run_result(
                            connector.source_id,
                            health_status="DEGRADED",
                            error_message=res.error_message,
                        )
                return res
            except Exception as exc:
                elapsed = time.perf_counter() - t0
                err_msg = f"Unhandled connector error in {connector.source_id}: {exc}"
                logger.error(err_msg, exc_info=True)
                if registry_repo:
                    registry_repo.record_run_result(
                        connector.source_id,
                        health_status="DEGRADED",
                        error_message=err_msg[:400],
                    )
                return ProviderCandidateResult(
                    provider=connector.source_id,
                    status="FAILED",
                    items=[],
                    error_code="UNHANDLED_EXCEPTION",
                    error_message=err_msg[:450],
                    retryable=False,
                )

        tasks = [_run_single(c) for c in active_connectors]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return results

    async def check_all_health(
        self, registry_repo: SourceRegistryRepository | None = None
    ) -> list[SourceHealthResult]:
        """Probes all registered connectors and returns operational health records."""
        async def _probe(c: EventSourceConnector) -> SourceHealthResult:
            try:
                res = await c.check_health()
                if registry_repo:
                    registry_repo.record_run_result(
                        c.source_id,
                        health_status=res.health_status,
                        error_message=res.message if res.health_status != "HEALTHY" else None,
                    )
                return res
            except Exception as exc:
                res = SourceHealthResult(
                    source_id=c.source_id,
                    connector_type=c.__class__.__name__,
                    health_status="DEGRADED",
                    message=f"Health probe check exception: {exc}",
                    last_check_at=utc_now(),
                )
                if registry_repo:
                    registry_repo.record_run_result(
                        c.source_id, health_status="DEGRADED", error_message=str(exc)
                    )
                return res

        tasks = [_probe(c) for c in self._connectors.values()]
        return await asyncio.gather(*tasks)
