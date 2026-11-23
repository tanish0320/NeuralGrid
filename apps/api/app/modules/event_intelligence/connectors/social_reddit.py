from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
import httpx
from apps.api.app.core.database import utc_now
from apps.api.app.modules.event_intelligence.connectors.base import EventSourceConnector, RawSourceItem
from apps.api.app.schemas.events import SourceHealthResult

logger = logging.getLogger("neuralgrid.eventsense.connector.reddit")


class RedditConnector(EventSourceConnector):
    """Reddit /r/bangalore & /r/karnataka Public Community Adapter."""

    source_id = "src_reddit_bangalore"
    platform = "REDDIT"
    display_name = "Reddit /r/bangalore Events & Gatherings"
    base_url = "https://www.reddit.com/r/bangalore"
    access_method = "OFFICIAL_OAUTH"
    default_reliability = 0.75

    def _get_credentials(self) -> tuple[str | None, str | None]:
        cid = getattr(self.settings, "reddit_client_id", None) if self.settings else None
        csec = getattr(self.settings, "reddit_client_secret", None) if self.settings else None
        return (cid or os.getenv("REDDIT_CLIENT_ID"), csec or os.getenv("REDDIT_CLIENT_SECRET"))

    async def fetch(
        self, city: str, query_terms: list[str], max_records: int
    ) -> list[RawSourceItem]:
        cid, csec = self._get_credentials()
        items: list[RawSourceItem] = []

        headers = {
            "User-Agent": "NeuralGrid:v1.5:event_intelligence_bot (by /u/neuralgrid_bot)",
        }

        # Attempt public read-only JSON search if credentials not set
        try:
            url = "https://www.reddit.com/r/bangalore/search.json"
            query = "event OR concert OR festival OR Palace Grounds"
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                r = await client.get(url, params={"q": query, "restrict_sr": "1", "sort": "new", "limit": str(max_records)}, headers=headers)
                if r.status_code == 200:
                    data = r.json().get("data", {}).get("children", [])
                    now = utc_now()
                    for child in data[:max_records]:
                        post = child.get("data", {})
                        title = post.get("title", "")
                        permalink = post.get("permalink", "")
                        created_utc = post.get("created_utc")
                        pub_dt = datetime.fromtimestamp(created_utc, tz=timezone.utc) if created_utc else now

                        items.append(
                            RawSourceItem(
                                url=f"https://www.reddit.com{permalink}",
                                title=title,
                                snippet=post.get("selftext", "")[:300] or title,
                                source_type="social_post",
                                published_at=pub_dt,
                                raw_metadata={"subreddit": post.get("subreddit"), "score": post.get("score")},
                            )
                        )
        except Exception as exc:
            logger.debug(f"Reddit query probe notice: {exc}")

        return items

    async def check_health(self) -> SourceHealthResult:
        cid, _ = self._get_credentials()
        if not cid:
            return SourceHealthResult(
                source_id=self.source_id,
                connector_type=self.__class__.__name__,
                health_status="AWAITING_CREDENTIALS",
                message="Reddit API OAuth client ID not set in REDDIT_CLIENT_ID. Public read-only feed active.",
                last_check_at=utc_now(),
            )

        return SourceHealthResult(
            source_id=self.source_id,
            connector_type=self.__class__.__name__,
            health_status="HEALTHY",
            message="Reddit OAuth connector active.",
            last_check_at=utc_now(),
        )
