from __future__ import annotations

import logging
from apps.api.app.modules.event_intelligence.connectors.base import EventSourceConnector, RawSourceItem
from apps.api.app.modules.event_intelligence.providers.gdelt_doc_provider import query_gdelt_doc
from apps.api.app.schemas.events import ProviderCandidateResult, SourceHealthResult
from apps.api.app.core.database import utc_now

logger = logging.getLogger("neuralgrid.eventsense.connector.gdelt")


class GDELTConnector(EventSourceConnector):
    """GDELT DOC 2.0 Global News Event Connector."""

    source_id = "src_gdelt_global"
    platform = "GDELT"
    display_name = "GDELT DOC 2.0 Global News (Bengaluru)"
    base_url = "https://api.gdeltproject.org/api/v2/doc/doc"
    access_method = "PUBLIC_API"
    default_reliability = 0.85

    async def fetch(
        self, city: str, query_terms: list[str], max_records: int
    ) -> list[RawSourceItem]:
        # GDELT returns SourceCandidate objects directly from query_gdelt_doc
        res = await query_gdelt_doc(
            city=city,
            query_terms=query_terms,
            max_records=max_records,
            timeout_seconds=4.0,
        )
        items: list[RawSourceItem] = []
        for cand in res.items:
            items.append(
                RawSourceItem(
                    url=str(cand.url),
                    title=cand.title or "GDELT Discovered News Article",
                    snippet=cand.snippet,
                    source_type="news_article",
                    published_at=cand.published_at,
                    raw_metadata={"domain": cand.domain},
                )
            )
        return items

    async def check_health(self) -> SourceHealthResult:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.head("https://api.gdeltproject.org/api/v2/doc/doc")
                status = "HEALTHY" if r.status_code < 500 else "DEGRADED"
                msg = f"GDELT DOC endpoint responded with HTTP {r.status_code}."
        except Exception as exc:
            status = "DEGRADED"
            msg = f"GDELT DOC health check probe warning: {exc}"

        return SourceHealthResult(
            source_id=self.source_id,
            connector_type=self.__class__.__name__,
            health_status=status,
            message=msg,
            last_check_at=utc_now(),
        )
