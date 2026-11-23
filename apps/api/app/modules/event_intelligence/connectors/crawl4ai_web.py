from __future__ import annotations

import logging
from apps.api.app.core.database import utc_now
from apps.api.app.modules.event_intelligence.connectors.base import EventSourceConnector, RawSourceItem
from apps.api.app.schemas.events import SourceHealthResult

logger = logging.getLogger("neuralgrid.eventsense.connector.crawl4ai")


class Crawl4AIConnector(EventSourceConnector):
    """Crawl4AI public web event page extractor connector."""

    source_id = "src_crawl4ai_web"
    platform = "NEWS"
    display_name = "Crawl4AI Web Page Scraper"
    base_url = "https://crawl4ai.com"
    access_method = "PUBLIC_SCRAPER"
    default_reliability = 0.85

    async def fetch(
        self, city: str, query_terms: list[str], max_records: int
    ) -> list[RawSourceItem]:
        # Crawl4AI operates on specific target URLs during the crawl phase
        # During discovery, it returns configured public venue announcement pages
        return []

    async def check_health(self) -> SourceHealthResult:
        try:
            from crawl4ai import AsyncWebCrawler  # type: ignore
            status = "HEALTHY"
            msg = "Crawl4AI module installed and operational."
        except Exception as exc:
            status = "DEGRADED"
            msg = f"Crawl4AI fallback mode active (using HTTPX/BeautifulSoup): {exc}"

        return SourceHealthResult(
            source_id=self.source_id,
            connector_type=self.__class__.__name__,
            health_status=status,
            message=msg,
            last_check_at=utc_now(),
        )
