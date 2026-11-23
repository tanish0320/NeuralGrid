from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
import httpx
from apps.api.app.core.database import utc_now
from apps.api.app.modules.event_intelligence.connectors.base import EventSourceConnector, RawSourceItem
from apps.api.app.schemas.events import SourceHealthResult

logger = logging.getLogger("neuralgrid.eventsense.connector.youtube")

YOUTUBE_SEARCH_ENDPOINT = "https://www.googleapis.com/youtube/v3/search"


class YouTubeConnector(EventSourceConnector):
    """YouTube Data API v3 Public Video & Livestream Announcement Adapter."""

    source_id = "src_youtube_events"
    platform = "YOUTUBE"
    display_name = "YouTube Data API v3 Venue Promos"
    base_url = "https://www.googleapis.com/youtube/v3/search"
    access_method = "API_TOKEN"
    default_reliability = 0.80

    def _get_api_key(self) -> str | None:
        key = getattr(self.settings, "youtube_api_key", None) if self.settings else None
        return key or os.getenv("YOUTUBE_API_KEY")

    async def fetch(
        self, city: str, query_terms: list[str], max_records: int
    ) -> list[RawSourceItem]:
        key = self._get_api_key()
        if not key:
            logger.info("YouTube API: No API key configured; operating in awaiting-credentials state.")
            return []

        clean_terms = " ".join(t.strip() for t in query_terms[:3] if t.strip())
        query = f"{city} {clean_terms} concert festival"

        params = {
            "part": "snippet",
            "q": query,
            "maxResults": str(max_records),
            "type": "video",
            "order": "date",
            "key": key,
        }

        items: list[RawSourceItem] = []
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(YOUTUBE_SEARCH_ENDPOINT, params=params)
                if r.status_code == 200:
                    for v in r.json().get("items", []):
                        vid = v.get("id", {}).get("videoId")
                        snippet = v.get("snippet", {})
                        if vid and snippet:
                            items.append(
                                RawSourceItem(
                                    url=f"https://www.youtube.com/watch?v={vid}",
                                    title=snippet.get("title", ""),
                                    snippet=snippet.get("description", "")[:300],
                                    source_type="social_post",
                                    published_at=datetime.fromisoformat(snippet.get("publishedAt").replace("Z", "+00:00")),
                                    raw_metadata={"channelTitle": snippet.get("channelTitle")},
                                )
                            )
        except Exception as exc:
            logger.warning(f"YouTube search error: {exc}")

        return items

    async def check_health(self) -> SourceHealthResult:
        key = self._get_api_key()
        if not key:
            return SourceHealthResult(
                source_id=self.source_id,
                connector_type=self.__class__.__name__,
                health_status="AWAITING_CREDENTIALS",
                message="YouTube Data API v3 key not configured in YOUTUBE_API_KEY environment variable.",
                last_check_at=utc_now(),
            )

        return SourceHealthResult(
            source_id=self.source_id,
            connector_type=self.__class__.__name__,
            health_status="HEALTHY",
            message="YouTube Data API key configured.",
            last_check_at=utc_now(),
        )
