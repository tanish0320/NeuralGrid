from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from apps.api.app.schemas.events import SourceCandidate


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "mc_eid",
    "ref",
}


def canonicalize_url_str(raw_url: str) -> str:
    """Strip common query tracking parameters and fragment for stable deduplication."""
    parsed = urlparse(raw_url.strip())
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # Filter query parameters
    query_tuples = parse_qsl(parsed.query, keep_blank_values=False)
    filtered = [(k, v) for k, v in query_tuples if k.lower() not in TRACKING_PARAMS]
    filtered.sort(key=lambda x: x[0])
    new_query = urlencode(filtered)

    path = parsed.path
    if path.endswith("/") and len(path) > 1:
        path = path[:-1]

    return urlunparse((parsed.scheme.lower(), netloc, path, "", new_query, ""))


def deduplicate_source_candidates(candidates: list[SourceCandidate]) -> list[SourceCandidate]:
    """Deduplicate candidates by canonical URL."""
    seen_urls: set[str] = set()
    unique: list[SourceCandidate] = []

    for cand in candidates:
        canon = canonicalize_url_str(str(cand.canonical_url or cand.url))
        if canon in seen_urls:
            continue
        seen_urls.add(canon)
        unique.append(cand)

    return unique
