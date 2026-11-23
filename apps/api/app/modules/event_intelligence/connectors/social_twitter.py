from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
import httpx
from apps.api.app.core.database import utc_now
from apps.api.app.modules.event_intelligence.connectors.base import EventSourceConnector, RawSourceItem
from apps.api.app.schemas.events import SourceHealthResult

logger = logging.getLogger("neuralgrid.eventsense.connector.twitter")

TWITTER_SEARCH_ENDPOINT = "https://api.twitter.com/2/tweets/search/recent"


class TwitterXConnector(EventSourceConnector):
    """Official X (Twitter) API v2 Recent Search Connector."""

    source_id = "src_twitter_x_v2"
    platform = "TWITTER"
    display_name = "X (Twitter) API v2 Bengaluru Search"
    base_url = "https://api.twitter.com/2/tweets/search/recent"
    access_method = "OFFICIAL_OAUTH"
    default_reliability = 0.85

    def _get_bearer_token(self) -> str | None:
        token = getattr(self.settings, "twitter_bearer_token", None) if self.settings else None
        return token or os.getenv("TWITTER_BEARER_TOKEN") or os.getenv("X_BEARER_TOKEN")

    async def fetch(
        self, city: str, query_terms: list[str], max_records: int
    ) -> list[RawSourceItem]:
        token = self._get_bearer_token()
        if not token:
            logger.info("X API v2: No Bearer Token configured; operating in awaiting-credentials state.")
            return []

        clean_terms = " OR ".join(f'"{t.strip()}"' for t in query_terms if t.strip())
        query = f'({clean_terms}) "{city}" -is:retweet lang:en' if clean_terms else f'"{city}" event -is:retweet lang:en'

        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "NeuralGridNOC/1.5",
        }
        params = {
            "query": query[:500],
            "max_results": str(max(10, min(max_records, 25))),
            "tweet.fields": "created_at,author_id,public_metrics,entities",
        }

        items: list[RawSourceItem] = []
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(TWITTER_SEARCH_ENDPOINT, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    now = utc_now()
                    for t in data[:max_records]:
                        tid = t.get("id")
                        text = t.get("text", "")
                        created_at_str = t.get("created_at")
                        pub_dt = None
                        if created_at_str:
                            try:
                                pub_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                            except Exception:
                                pub_dt = now

                        items.append(
                            RawSourceItem(
                                url=f"https://x.com/i/web/status/{tid}",
                                title=text[:80].replace("\n", " "),
                                snippet=text,
                                source_type="social_post",
                                published_at=pub_dt,
                                raw_metadata={"author_id": t.get("author_id"), "metrics": t.get("public_metrics")},
                            )
                        )
                elif resp.status_code == 429:
                    logger.warning("X API v2 rate limit encountered.")
                elif resp.status_code == 401:
                    logger.warning("X API v2: Invalid bearer token or unauthorized tier.")
        except Exception as exc:
            logger.warning(f"X API v2 query error: {exc}")

        return items

    async def check_health(self) -> SourceHealthResult:
        token = self._get_bearer_token()
        if not token:
            return SourceHealthResult(
                source_id=self.source_id,
                connector_type=self.__class__.__name__,
                health_status="AWAITING_CREDENTIALS",
                message="X API v2 Bearer Token not configured in TWITTER_BEARER_TOKEN environment variable.",
                last_check_at=utc_now(),
            )

        try:
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(
                    TWITTER_SEARCH_ENDPOINT,
                    params={"query": "Bengaluru", "max_results": "10"},
                    headers=headers,
                )
                if r.status_code == 200:
                    status = "HEALTHY"
                    msg = "X API v2 authenticated and operational."
                else:
                    status = "DEGRADED"
                    msg = f"X API v2 returned HTTP {r.status_code} ({r.text[:100]})."
        except Exception as exc:
            status = "DEGRADED"
            msg = f"X API probe warning: {exc}"

        return SourceHealthResult(
            source_id=self.source_id,
            connector_type=self.__class__.__name__,
            health_status=status,
            message=msg,
            last_check_at=utc_now(),
        )
