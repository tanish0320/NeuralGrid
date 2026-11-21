from __future__ import annotations

import hashlib
import logging
from typing import Any
import httpx
from bs4 import BeautifulSoup
from pydantic import HttpUrl

from apps.api.app.schemas.events import CrawlPageResult, CrawlTarget, FetchProvider, FetchStatus

logger = logging.getLogger("neuralgrid.eventsense.crawler")

# Attempt Crawl4AI import
HAS_CRAWL4AI = False
try:
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig  # type: ignore
    HAS_CRAWL4AI = True
except Exception:
    HAS_CRAWL4AI = False


def _compute_hash(text: str | None) -> str | None:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _crawl_with_crawl4ai(target: CrawlTarget, timeout_seconds: int) -> CrawlPageResult:
    """Execute page fetch using Crawl4AI AsyncWebCrawler."""
    try:
        run_config = CrawlerRunConfig(
            check_robots_txt=True,
            page_timeout=timeout_seconds * 1000,
            verbose=False,
        )
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=str(target.url), config=run_config)

        if not result.success:
            status: FetchStatus = "BLOCKED_ROBOTS" if "robots" in (result.error_message or "").lower() else "FAILED"
            return CrawlPageResult(
                source_id=target.source_id,
                fetch_provider="crawl4ai",
                fetch_status=status,
                error_code="CRAWL_FAILED",
                error_message=(result.error_message or "Crawl4AI returned failure")[:450],
            )

        html = result.html or ""
        markdown = result.markdown or ""
        title = None
        if html:
            soup = BeautifulSoup(html, "html.parser")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()

        content_hash = _compute_hash(markdown or html)
        return CrawlPageResult(
            source_id=target.source_id,
            fetch_provider="crawl4ai",
            fetch_status="SUCCEEDED",
            final_url=str(result.url or target.url),
            title=title,
            markdown_text=markdown[:180_000] if markdown else None,
            html_for_extraction=html[:450_000] if html else None,
            content_hash=content_hash,
        )
    except Exception as exc:
        logger.warning("Crawl4AI execution failed for %s, will try fallback: %s", target.url, exc)
        return await _crawl_with_httpx_fallback(target, timeout_seconds)


async def _crawl_with_httpx_fallback(target: CrawlTarget, timeout_seconds: int) -> CrawlPageResult:
    """Documented static HTTPX + BeautifulSoup fallback (Integration Guide §7 & §12)."""
    headers = {
        "User-Agent": "NeuralGridEventSense/1.5 (Mozilla/5.0 compatible; Proactive Network NOC; +https://neuralgrid.local)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=float(timeout_seconds), follow_redirects=True) as client:
            resp = await client.get(str(target.url), headers=headers)

        if resp.status_code == 429:
            return CrawlPageResult(
                source_id=target.source_id,
                fetch_provider="static_html_fallback",
                fetch_status="RATE_LIMITED",
                error_code="RATE_LIMITED",
                error_message="HTTP 429 Too Many Requests",
            )
        if resp.status_code != 200:
            return CrawlPageResult(
                source_id=target.source_id,
                fetch_provider="static_html_fallback",
                fetch_status="HTTP_ERROR",
                error_code=f"HTTP_{resp.status_code}",
                error_message=f"Server returned HTTP {resp.status_code}",
            )

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else None

        # Clean script/style for markdown text approximation
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            if tag.name != "script" or tag.get("type") != "application/ld+json":
                tag.decompose()

        text_content = soup.get_text(separator="\n", strip=True)
        content_hash = _compute_hash(text_content or html)

        return CrawlPageResult(
            source_id=target.source_id,
            fetch_provider="static_html_fallback",
            fetch_status="SUCCEEDED",
            final_url=str(resp.url),
            title=title,
            markdown_text=text_content[:180_000] if text_content else None,
            html_for_extraction=html[:450_000] if html else None,
            content_hash=content_hash,
        )

    except httpx.TimeoutException:
        return CrawlPageResult(
            source_id=target.source_id,
            fetch_provider="static_html_fallback",
            fetch_status="TIMEOUT",
            error_code="TIMEOUT",
            error_message="Page request timed out",
        )
    except Exception as exc:
        return CrawlPageResult(
            source_id=target.source_id,
            fetch_provider="static_html_fallback",
            fetch_status="FAILED",
            error_code="FETCH_ERROR",
            error_message=str(exc)[:450],
        )


async def crawl_targets(targets: list[CrawlTarget], timeout_seconds: int = 30) -> list[CrawlPageResult]:
    """Crawl a list of approved CrawlTargets sequentially (1 concurrent page, max 5)."""
    results: list[CrawlPageResult] = []
    # Cap to max 5 targets per run per spec
    bounded_targets = targets[:5]

    for target in bounded_targets:
        if HAS_CRAWL4AI:
            res = await _crawl_with_crawl4ai(target, timeout_seconds)
        else:
            res = await _crawl_with_httpx_fallback(target, timeout_seconds)
        results.append(res)

    return results
