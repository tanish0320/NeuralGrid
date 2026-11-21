from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.app.config import Settings
from apps.api.app.main import create_app
from apps.api.app.schemas.events import (
    CrawlPageResult,
    CrawlTarget,
    EventDiscoveryRequest,
    EventDiscoveryServiceResult,
    EventExtractionResult,
    ProviderCandidateResult,
    SourceCandidate,
)
from tests.conftest import make_mock_dns_resolver


class StubTanishEventService:
    """Test double implementing Tanish's exact EventIntelligenceServiceProtocol."""

    def __init__(self, *, gdelt_fail: bool = False) -> None:
        self.gdelt_fail = gdelt_fail
        self.crawl_calls: list[list[CrawlTarget]] = []

    async def discover_candidates(
        self, request: EventDiscoveryRequest
    ) -> EventDiscoveryServiceResult:
        now = datetime.now(timezone.utc)
        providers: list[ProviderCandidateResult] = []
        if "gdelt" in request.enabled_providers:
            if self.gdelt_fail:
                providers.append(
                    ProviderCandidateResult(
                        provider="gdelt",
                        status="FAILED",
                        items=[],
                        error_code="TIMEOUT",
                        error_message="GDELT DOC API timed out",
                        retryable=True,
                    )
                )
            else:
                providers.append(
                    ProviderCandidateResult(
                        provider="gdelt",
                        status="SUCCEEDED",
                        items=[
                            SourceCandidate(
                                discovery_provider="gdelt",
                                source_type="news_article",
                                url="https://approved.example/events/blr-live?utm_source=gdelt",
                                canonical_url="https://approved.example/events/blr-live",
                                domain="approved.example",
                                title="Bengaluru Live Concert Announcement",
                                snippet="Evening music festival at Palace Grounds",
                                published_at=now,
                                discovered_at=now,
                            ),
                            # Duplicate canonical URL in same run should dedupe cleanly
                            SourceCandidate(
                                discovery_provider="gdelt",
                                source_type="news_article",
                                url="https://approved.example/events/blr-live?fbclid=dup123",
                                canonical_url="https://approved.example/events/blr-live",
                                domain="approved.example",
                                title="Bengaluru Live Concert Announcement",
                                snippet="Duplicate link",
                                published_at=now,
                                discovered_at=now,
                            ),
                            # Disallowed domain must be persisted BLOCKED_POLICY and never crawled
                            SourceCandidate(
                                discovery_provider="gdelt",
                                source_type="news_article",
                                url="https://evil.example/unapproved-page",
                                canonical_url="https://evil.example/unapproved-page",
                                domain="evil.example",
                                title="Unapproved Domain Candidate",
                                published_at=None,
                                discovered_at=now,
                            ),
                        ],
                    )
                )

        if "rss" in request.enabled_providers:
            providers.append(
                ProviderCandidateResult(
                    provider="rss",
                    status="SUCCEEDED",
                    items=[
                        SourceCandidate(
                            discovery_provider="rss",
                            source_type="rss_item",
                            url="https://events.example.org/blr-festival",
                            canonical_url="https://events.example.org/blr-festival",
                            domain="events.example.org",
                            title="Bengaluru Live Concert",
                            snippet="RSS listing",
                            published_at=None,
                            discovered_at=now,
                        ),
                    ],
                )
            )
        return EventDiscoveryServiceResult(
            providers=providers,
            warnings=["GDELT timed out"] if self.gdelt_fail else [],
        )

    async def crawl_public_sources(
        self, sources: list[CrawlTarget]
    ) -> list[CrawlPageResult]:
        self.crawl_calls.append(sources)
        results: list[CrawlPageResult] = []
        for target in sources:
            results.append(
                CrawlPageResult(
                    source_id=target.source_id,
                    fetch_provider="crawl4ai",
                    fetch_status="SUCCEEDED",
                    final_url=target.url,
                    title="Bengaluru Live Concert",
                    markdown_text="# Bengaluru Live Concert\nVenue: Palace Grounds\n",
                    html_for_extraction="<html><script type='application/ld+json'>{}</script></html>",
                    content_hash=f"sha256:hash-{target.domain}",
                )
            )
        return results

    def extract_event_fields(self, page: CrawlPageResult) -> EventExtractionResult:
        # Unknown attendance and coordinates stay missing/null rather than fabricated
        return EventExtractionResult(
            source_id=page.source_id,
            extraction_status="PARTIAL",
            fields={
                "event_name": "Bengaluru Live Concert",
                "event_type": "concert",
                "venue_name": "Palace Grounds",
                "city": "Bengaluru",
                "start_at": "2026-11-22T13:30:00Z",
                "attendance_low": None,
                "attendance_high": None,
                "latitude": None,
                "longitude": None,
            },
            field_provenance={"venue_name": "markdown_text"},
            evidence_summary="Extracted event title, venue, and date; attendance unknown.",
        )


def test_discovery_crawl_policy_dedup_corroboration_and_guards(test_settings: Settings) -> None:
    stub = StubTanishEventService(gdelt_fail=False)
    app = create_app(
        settings=test_settings,
        event_intelligence_service=stub,
        dns_resolver=make_mock_dns_resolver(),
    )
    with TestClient(app) as tc:
        # ES-05: Discover persists run and unique source IDs
        disc = tc.post(
            "/api/v1/event-intelligence/discover",
            json={
                "city": "Bengaluru",
                "query_terms": ["concert", "Palace Grounds"],
                "time_window_hours": 168,
                "max_candidates": 5,
                "enabled_providers": ["gdelt", "rss"],
            },
        )
        assert disc.status_code == 200
        d_data = disc.json()
        run_id = d_data["run_id"]
        assert d_data["status"] == "SUCCEEDED"
        # 2 unique GDELT (1 approved deduped + 1 blocked) + 1 RSS = 3 source IDs
        assert len(d_data["source_ids"]) == 3

        sources = tc.get(f"/api/v1/event-intelligence/sources?run_id={run_id}").json()
        assert len(sources) == 3
        blocked_src = next(s for s in sources if s["domain"] == "evil.example")
        assert blocked_src["fetch_status"] == "BLOCKED_POLICY"
        assert blocked_src["eligible_for_crawl"] is False

        allowed_sources = [s for s in sources if s["eligible_for_crawl"]]
        assert len(allowed_sources) == 2

        # ES-06: Unknown source ID -> 404; mismatched run_id -> 409
        r404 = tc.post(
            "/api/v1/event-intelligence/crawl",
            json={"run_id": run_id, "source_ids": [str(uuid4())], "max_pages": 1},
        )
        assert r404.status_code == 404

        other_disc = tc.post(
            "/api/v1/event-intelligence/discover",
            json={"city": "Bengaluru", "query_terms": ["festival"], "enabled_providers": ["rss"]},
        ).json()
        r409 = tc.post(
            "/api/v1/event-intelligence/crawl",
            json={
                "run_id": other_disc["run_id"],
                "source_ids": [allowed_sources[0]["source_id"]],
                "max_pages": 1,
            },
        )
        assert r409.status_code == 409

        # ES-07: Attempting to crawl policy-blocked source never calls crawler
        prev_calls = len(stub.crawl_calls)
        blocked_crawl = tc.post(
            "/api/v1/event-intelligence/crawl",
            json={"run_id": run_id, "source_ids": [blocked_src["source_id"]], "max_pages": 1},
        )
        assert blocked_crawl.status_code == 200
        assert blocked_crawl.json()["sources"][0]["fetch_status"] == "BLOCKED_POLICY"
        assert len(stub.crawl_calls) == prev_calls

        # Crawl both allowed independent sources -> corroborated event, null unknown fields, separate providers preserved
        crawl_ok = tc.post(
            "/api/v1/event-intelligence/crawl",
            json={
                "run_id": run_id,
                "source_ids": [s["source_id"] for s in allowed_sources],
                "max_pages": 5,
            },
        )
        assert crawl_ok.status_code == 200
        c_data = crawl_ok.json()
        assert len(c_data["event_ids"]) == 1
        for src in c_data["sources"]:
            assert src["discovery_provider"] in ("gdelt", "rss")
            assert src["fetch_provider"] == "crawl4ai"

        event_id = c_data["event_ids"][0]
        ev = tc.get(f"/api/v1/events/{event_id}").json()
        assert ev["event_origin"] == "SOURCE_DISCOVERED"
        assert ev["verification_status"] == "CORROBORATED"
        assert len(ev["source_ids"]) == 2
        assert ev["attendance_low"] is None
        assert ev["attendance_high"] is None
        assert ev["attendance_basis"] == "UNKNOWN"

        # Impact mapping blocked until operator confirms
        sim_id = tc.post("/api/v1/simulations", json={"seed": 42}).json()["simulation_id"]
        unconfirmed_imp = tc.post(
            f"/api/v1/events/{event_id}/impact",
            json={"simulation_id": sim_id, "influence_radius_km": 3.0},
        )
        assert unconfirmed_imp.status_code == 409

        # Confirm with venue coordinates -> impact succeeds
        tc.post(
            f"/api/v1/events/{event_id}/confirm",
            json={"operator_id": "op1", "latitude": 12.9988, "longitude": 77.5921},
        )
        confirmed_imp = tc.post(
            f"/api/v1/events/{event_id}/impact",
            json={"simulation_id": sim_id, "influence_radius_km": 3.0, "attendance_scenario": "EXPECTED"},
        )
        assert confirmed_imp.status_code == 200
        assert len(confirmed_imp.json()["affected_cells"]) > 0


def test_partial_provider_failure_and_offline_seeded_fallback(test_settings: Settings) -> None:
    # ES-08: Partial failure when GDELT fails and RSS succeeds
    partial_stub = StubTanishEventService(gdelt_fail=True)
    app_partial = create_app(
        settings=test_settings,
        event_intelligence_service=partial_stub,
        dns_resolver=make_mock_dns_resolver(),
    )
    with TestClient(app_partial) as tc:
        disc = tc.post(
            "/api/v1/event-intelligence/discover",
            json={
                "city": "Bengaluru",
                "query_terms": ["concert"],
                "enabled_providers": ["gdelt", "rss"],
            },
        ).json()
        assert disc["status"] == "PARTIAL"
        assert len(disc["source_ids"]) == 1
        by_p = {p["provider"]: p for p in disc["providers"]}
        assert by_p["gdelt"]["status"] == "FAILED"
        assert by_p["gdelt"]["error_code"] == "TIMEOUT"
        assert by_p["rss"]["status"] == "SUCCEEDED"

    # ES-12: No Tanish collector installed -> structured PROVIDER_NOT_INSTALLED + seeded demo still works
    app_offline = create_app(
        settings=test_settings,
        event_intelligence_service=None,
        dns_resolver=make_mock_dns_resolver(),
    )
    with TestClient(app_offline) as tc:
        disc_off = tc.post(
            "/api/v1/event-intelligence/discover",
            json={"city": "Bengaluru", "query_terms": ["concert"]},
        ).json()
        assert disc_off["status"] == "FAILED"
        assert disc_off["providers"][0]["error_code"] == "PROVIDER_NOT_INSTALLED"

        events = tc.get("/api/v1/events").json()
        demo = next(e for e in events if e["event_key"] == "palace-grounds-demo")
        assert demo["verification_status"] == "DEMO_SCENARIO"
        assert demo["event_origin"] == "SEEDED_DEMO"

        sim_id = tc.post("/api/v1/simulations", json={"seed": 42}).json()["simulation_id"]
        assert tc.post(
            f"/api/v1/events/{demo['event_id']}/confirm",
            json={"operator_id": "op1", "accept_demo_assumptions": True},
        ).status_code == 200
        imp = tc.post(
            f"/api/v1/events/{demo['event_id']}/impact",
            json={"simulation_id": sim_id, "influence_radius_km": 3.0},
        )
        assert imp.status_code == 200
        assert len(imp.json()["affected_cells"]) > 5


class _RedirectingCrawlService(StubTanishEventService):
    async def crawl_public_sources(
        self, sources: list[CrawlTarget]
    ) -> list[CrawlPageResult]:
        return [
            CrawlPageResult(
                source_id=target.source_id,
                fetch_provider="crawl4ai",
                fetch_status="SUCCEEDED",
                final_url="https://evil.example/hijacked-redirect",
                title="Redirected",
                markdown_text="Should never be extracted",
            )
            for target in sources
        ]


def test_redirect_to_disallowed_domain_blocked_before_extraction(test_settings: Settings) -> None:
    app = create_app(
        settings=test_settings,
        event_intelligence_service=_RedirectingCrawlService(),
        dns_resolver=make_mock_dns_resolver(),
    )
    with TestClient(app) as tc:
        disc = tc.post(
            "/api/v1/event-intelligence/discover",
            json={"city": "Bengaluru", "query_terms": ["concert"], "enabled_providers": ["rss"]},
        ).json()
        run_id = disc["run_id"]
        src_id = disc["source_ids"][0]

        crawl = tc.post(
            "/api/v1/event-intelligence/crawl",
            json={"run_id": run_id, "source_ids": [src_id], "max_pages": 1},
        )
        assert crawl.status_code == 200
        c_data = crawl.json()
        assert c_data["event_ids"] == []
        src = c_data["sources"][0]
        assert src["fetch_status"] == "BLOCKED_POLICY"
        assert src["extraction_status"] == "NOT_RUN"
        assert src["error_code"] == "REDIRECT_NOT_ALLOWED"
