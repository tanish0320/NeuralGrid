from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
import feedparser

from apps.api.app.core.database import utc_now
from apps.api.app.schemas.events import ProviderCandidateResult, SourceCandidate

logger = logging.getLogger("neuralgrid.eventsense.rss")


def _struct_time_to_utc(st: time.struct_time | None) -> datetime | None:
    if st is None:
        return None
    try:
        ts = time.mktime(st)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return None


def parse_rss_feeds(
    feed_urls: list[str],
    query_terms: list[str] | None = None,
    max_records: int = 5,
) -> ProviderCandidateResult:
    """Parses configured RSS/Atom feeds using feedparser."""
    now = utc_now()
    all_candidates: list[SourceCandidate] = []
    errors: list[str] = []

    clean_terms = [t.lower().strip() for t in (query_terms or []) if t.strip()]

    for feed_url in feed_urls:
        url_str = feed_url.strip()
        if not url_str:
            continue
        try:
            feed = feedparser.parse(url_str)
            if feed.bozo and not feed.entries:
                bozo_msg = str(getattr(feed, "bozo_exception", "Unknown parse failure"))
                errors.append(f"{url_str}: {bozo_msg}")
                continue

            for entry in feed.entries:
                link = getattr(entry, "link", None)
                if not link:
                    continue

                parsed = urlparse(link)
                domain = (parsed.netloc or "").lower()
                if not domain:
                    continue

                title = (getattr(entry, "title", "") or "").strip() or None
                summary = (getattr(entry, "summary", "") or "").strip() or None

                # Optional keyword filter if query_terms provided
                if clean_terms:
                    text_blob = f"{title or ''} {summary or ''}".lower()
                    if not any(qt in text_blob for qt in clean_terms):
                        continue

                published_at = _struct_time_to_utc(
                    getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
                )

                try:
                    cand = SourceCandidate(
                        discovery_provider="rss",
                        source_type="rss_item",
                        url=link,
                        canonical_url=link,
                        domain=domain,
                        title=title,
                        snippet=summary[:1800] if summary else None,
                        published_at=published_at,
                        discovered_at=now,
                    )
                    all_candidates.append(cand)
                except Exception as exc:
                    logger.debug("Skipping invalid RSS candidate link %s: %s", link, exc)
                    continue

                if len(all_candidates) >= max_records:
                    break

        except Exception as exc:
            errors.append(f"{url_str}: {str(exc)[:120]}")

        if len(all_candidates) >= max_records:
            break

    status = "SUCCEEDED" if all_candidates else ("FAILED" if errors else "PARTIAL")
    err_msg = "; ".join(errors) if errors else None

    return ProviderCandidateResult(
        provider="rss",
        status=status,
        items=all_candidates,
        error_code="RSS_PARSE_WARNING" if errors and all_candidates else ("RSS_ERROR" if errors else None),
        error_message=err_msg[:450] if err_msg else None,
    )
