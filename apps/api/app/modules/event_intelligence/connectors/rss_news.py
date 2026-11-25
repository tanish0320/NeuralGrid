from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse
import feedparser
import httpx
from apps.api.app.core.database import utc_now
from apps.api.app.modules.event_intelligence.connectors.base import EventSourceConnector, RawSourceItem
from apps.api.app.modules.event_intelligence.relevance import score_crowd_relevance
from apps.api.app.schemas.events import SourceHealthResult

logger = logging.getLogger("neuralgrid.eventsense.connector.rss")

# Curated feeds for Bengaluru public events, protests, concerts, matches
CURATED_BENGALURU_FEEDS = {
    "src_deccanherald_rss": "https://www.deccanherald.com/rss/bengaluru.rss",
    "src_thehindu_rss": "https://www.thehindu.com/news/cities/bangalore/feeder/default.rss",
    "src_timesofindia_rss": "https://timesofindia.indiatimes.com/rssfeeds/-2128833038.cms",
    "src_indianexpress_rss": "https://indianexpress.com/section/cities/bangalore/feed/",
    "src_bangaloremirror_rss": "https://bangaloremirror.indiatimes.com/rssfeeds/20970472.cms",
}


class RSSNewsConnector(EventSourceConnector):
    """Feedparser & Trafilatura News/RSS Connector for Bengaluru News Feeds."""

    def __init__(
        self,
        source_id: str = "src_deccanherald_rss",
        display_name: str = "Deccan Herald Bengaluru",
        feed_url: str | None = None,
        settings: object = None,
    ) -> None:
        super().__init__(settings)
        self.source_id = source_id
        self.platform = "NEWS"
        self.display_name = display_name
        self.base_url = feed_url or CURATED_BENGALURU_FEEDS.get(
            source_id, "https://www.deccanherald.com/rss/bengaluru.rss"
        )
        self.access_method = "RSS_FEED"
        self.default_reliability = 0.90

    async def fetch(
        self, city: str, query_terms: list[str], max_records: int
    ) -> list[RawSourceItem]:
        items: list[RawSourceItem] = []
        clean_terms = [t.lower().strip() for t in query_terms if t.strip()]

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }

        content_text = ""
        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
                resp = await client.get(self.base_url, headers=headers)
                if resp.status_code == 200:
                    content_text = resp.text
        except Exception as exc:
            logger.debug(f"Direct HTTP fetch failed for {self.base_url}: {exc}")

        if not content_text:
            return []

        # Feedparser parse bounded to fetched XML text (never block on un-timeouted URL fetch)
        feed = feedparser.parse(content_text)
        entries = feed.entries or []

        scored_candidates: list[tuple[int, RawSourceItem]] = []
        for entry in entries:
            link = getattr(entry, "link", None)
            title = getattr(entry, "title", None)
            if not link or not title:
                continue

            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            domain = urlparse(link).netloc
            rel = score_crowd_relevance(
                title=title,
                text=summary,
                domain=domain,
                source_type="news_article",
            )
            if not rel.is_relevant:
                continue

            # Parse date
            pub_dt = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    import time
                    pub_dt = datetime.fromtimestamp(time.mktime(entry.published_parsed), tz=timezone.utc)
                except Exception:
                    pub_dt = None

            scored_candidates.append(
                (
                    rel.score,
                    RawSourceItem(
                        url=link,
                        title=title,
                        snippet=summary[:400] if summary else None,
                        source_type="news_article",
                        published_at=pub_dt,
                        raw_metadata={
                            "feed_url": self.base_url,
                            "crowd_relevance_score": rel.score,
                            "crowd_category": rel.category,
                        },
                    ),
                )
            )

        scored_candidates.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored_candidates[:max_records]]

    async def check_health(self) -> SourceHealthResult:
        try:
            async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
                r = await client.head(self.base_url)
                status = "HEALTHY" if r.status_code < 400 else "DEGRADED"
                msg = f"Feed reachable with status {r.status_code}."
        except Exception as exc:
            status = "DEGRADED"
            msg = f"Feed unreachable: {exc}"

        return SourceHealthResult(
            source_id=self.source_id,
            connector_type=self.__class__.__name__,
            health_status=status,
            message=msg,
            last_check_at=utc_now(),
        )
