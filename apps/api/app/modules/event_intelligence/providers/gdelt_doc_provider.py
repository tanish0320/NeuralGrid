from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse
import httpx
from pydantic import HttpUrl

from apps.api.app.core.database import utc_now
from apps.api.app.schemas.events import ProviderCandidateResult, SourceCandidate

logger = logging.getLogger("neuralgrid.eventsense.gdelt")

GDELT_DOC_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"


def _parse_gdelt_seendate(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    cleaned = date_str.strip().replace("Z", "")
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(cleaned, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


async def query_gdelt_doc(
    city: str,
    query_terms: list[str],
    max_records: int = 5,
    timeout_seconds: float = 3.5,
) -> ProviderCandidateResult:
    """Bounded GDELT DOC 2.0 article search adapter."""
    cleaned_city = city.strip()
    cleaned_terms = " OR ".join(f'"{t.strip()}"' for t in query_terms if t.strip())
    query = f'({cleaned_terms}) "{cleaned_city}"' if cleaned_terms else f'"{cleaned_city}"'

    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": str(max(1, min(max_records, 15))),
        "format": "json",
        "timespan": "7d",
    }

    headers = {
        "User-Agent": "NeuralGridEventSense/1.5 (Proactive Network Intelligence NOC)",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            response = await client.get(GDELT_DOC_ENDPOINT, params=params, headers=headers)

        if response.status_code == 429:
            return ProviderCandidateResult(
                provider="gdelt",
                status="FAILED",
                items=[],
                error_code="RATE_LIMITED",
                error_message="GDELT DOC API rate limited (HTTP 429). Respecting backoff.",
                retryable=True,
            )

        if response.status_code != 200:
            return ProviderCandidateResult(
                provider="gdelt",
                status="FAILED",
                items=[],
                error_code="HTTP_ERROR",
                error_message=f"GDELT DOC returned HTTP {response.status_code}",
                retryable=response.status_code >= 500,
            )

        content_type = response.headers.get("content-type", "")
        if "json" not in content_type and not response.text.strip().startswith("{"):
            return ProviderCandidateResult(
                provider="gdelt",
                status="FAILED",
                items=[],
                error_code="INVALID_RESPONSE_FORMAT",
                error_message="GDELT DOC returned non-JSON content",
                retryable=False,
            )

        data = response.json()
        articles = data.get("articles") or []
        now = utc_now()
        candidates: list[SourceCandidate] = []

        for art in articles:
            raw_url = art.get("url")
            if not raw_url:
                continue

            parsed_url = urlparse(raw_url)
            domain = (parsed_url.netloc or art.get("domain") or "").lower()
            if not domain:
                continue

            published_at = _parse_gdelt_seendate(art.get("seendate"))
            title = (art.get("title") or "").strip() or None

            try:
                cand = SourceCandidate(
                    discovery_provider="gdelt",
                    source_type="news_article",
                    url=raw_url,
                    canonical_url=raw_url,
                    domain=domain,
                    title=title,
                    snippet=None,
                    published_at=published_at,
                    discovered_at=now,
                )
                candidates.append(cand)
            except Exception as exc:
                logger.debug("Skipping invalid GDELT candidate URL %s: %s", raw_url, exc)
                continue

            if len(candidates) >= max_records:
                break

        return ProviderCandidateResult(
            provider="gdelt",
            status="SUCCEEDED" if candidates else "PARTIAL",
            items=candidates,
        )

    except httpx.TimeoutException:
        return ProviderCandidateResult(
            provider="gdelt",
            status="FAILED",
            items=[],
            error_code="TIMEOUT",
            error_message="GDELT DOC query timed out",
            retryable=True,
        )
    except Exception as exc:
        return ProviderCandidateResult(
            provider="gdelt",
            status="FAILED",
            items=[],
            error_code="GDELT_ERROR",
            error_message=str(exc)[:450],
            retryable=False,
        )
