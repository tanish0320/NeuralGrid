from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import create_app
from apps.api.app.config import Settings
from apps.api.app.core.database import Database
from apps.api.app.repositories.source_registry import SourceRegistryRepository
from apps.api.app.modules.event_intelligence.connectors.base import (
    EventSourceConnector,
    RawSourceItem,
)
from apps.api.app.modules.event_intelligence.connectors.registry import ConnectorRegistry
from apps.api.app.modules.event_intelligence.connectors.social_twitter import TwitterXConnector
from apps.api.app.modules.event_intelligence.connectors.social_instagram import InstagramConnector
from apps.api.app.modules.event_intelligence.connectors.social_youtube import YouTubeConnector
from apps.api.app.modules.event_intelligence.connectors.social_telegram import TelegramConnector
from apps.api.app.schemas.events import SourceCandidate, SourceRegistryUpdate


class MockWorkingConnector(EventSourceConnector):
    source_id = "src_mock_working"
    platform = "mock"
    display_name = "Mock Working Source"
    base_url = "https://mock.example.com"
    access_method = "http_get"

    async def fetch(
        self, city: str, query_terms: list[str], max_records: int
    ) -> list[RawSourceItem]:
        return [
            RawSourceItem(
                url="https://mock.example.com/events/concert?ref=rss&session=1",
                title="Mock Live Concert in Whitefield",
                snippet="Massive gathering in Whitefield campus",
                source_type="ticketing_page",
            ),
            # Duplicate canonical URL
            RawSourceItem(
                url="https://mock.example.com/events/concert?ref=twitter#section",
                title="Mock Live Concert in Whitefield (Duplicate Link)",
                snippet="Duplicate link for same concert",
                source_type="ticketing_page",
            ),
            # Invalid item with empty title
            RawSourceItem(
                url="https://mock.example.com/events/invalid",
                title="",
                snippet="No title",
            ),
        ]


class MockFaultyConnector(EventSourceConnector):
    source_id = "src_mock_faulty"
    platform = "mock_faulty"
    display_name = "Mock Faulty Source"
    base_url = "https://faulty.example.com"
    access_method = "http_get"

    async def fetch(
        self, city: str, query_terms: list[str], max_records: int
    ) -> list[RawSourceItem]:
        raise RuntimeError("External network connection timeout / TLS handshake failed")


@pytest.mark.asyncio
async def test_connector_pipeline_normalization_validation_and_deduplication():
    """Verify standard connector pipeline steps: fetch -> normalize -> validate -> deduplicate -> return_events."""
    conn = MockWorkingConnector()
    result = await conn.return_events(city="Bengaluru", query_terms=["concert"], max_records=10)

    assert result.status == "SUCCEEDED"
    assert result.provider == "src_mock_working"
    # Should deduplicate from 2 valid candidates down to 1 distinct canonical URL, and drop the empty-title one
    assert len(result.items) == 1

    candidate = result.items[0]
    assert candidate.title == "Mock Live Concert in Whitefield"
    assert str(candidate.canonical_url) == "https://mock.example.com/events/concert"
    assert candidate.domain == "mock.example.com"
    assert candidate.discovery_provider == "src_mock_working"


@pytest.mark.asyncio
async def test_connector_isolation_on_catastrophic_failure():
    """Verify that if one connector crashes or raises an exception, other connectors still succeed."""
    registry = ConnectorRegistry()
    # Clear defaults for unit isolation
    registry._connectors.clear()

    working = MockWorkingConnector()
    faulty = MockFaultyConnector()
    registry.register(working)
    registry.register(faulty)

    results = await registry.run_discovery(city="Bengaluru", query_terms=["event"])
    assert len(results) == 2

    res_by_id = {r.provider: r for r in results}
    assert "src_mock_working" in res_by_id
    assert "src_mock_faulty" in res_by_id

    # The working connector returned items
    assert res_by_id["src_mock_working"].status == "SUCCEEDED"
    assert len(res_by_id["src_mock_working"].items) == 1

    # The faulty connector safely caught exception, marked as FAILED with error message
    assert res_by_id["src_mock_faulty"].status == "FAILED"
    assert len(res_by_id["src_mock_faulty"].items) == 0
    assert "External network connection timeout" in res_by_id["src_mock_faulty"].error_message


def test_social_connectors_report_awaiting_credentials_cleanly():
    """Verify that unauthenticated social connectors do not crash and report AWAITING_CREDENTIALS."""
    twitter = TwitterXConnector()
    instagram = InstagramConnector()
    youtube = YouTubeConnector()
    telegram = TelegramConnector()

    for connector in [twitter, instagram, youtube, telegram]:
        health = asyncio.run(connector.check_health())
        assert health.health_status in ("AWAITING_CREDENTIALS", "DISABLED", "DEGRADED")
        assert (
            "Awaiting" in health.message
            or "disabled" in health.message
            or "not configured" in health.message
            or "key" in health.message.lower()
            or "token" in health.message.lower()
        )

        # Calling return_events without credentials should return safely without crashing
        res = asyncio.run(connector.return_events(city="Bengaluru", query_terms=["test"], max_records=5))
        assert res.status in ("SUCCEEDED", "FAILED", "SKIPPED")
        assert len(res.items) == 0


def test_source_registry_repository_and_evidence(tmp_path):
    """Verify SourceRegistryRepository persistence, seeding, health updates, and evidence storage."""
    db_file = str(tmp_path / "test_sources.db")
    db = Database(db_file)
    db.init_schema()

    repo = SourceRegistryRepository(db)
    sources = repo.list_sources()

    # Pre-seeded default sources should exist
    assert len(sources) >= 12
    source_ids = [s.source_id for s in sources]
    assert "src_gdelt_global" in source_ids
    assert "src_deccanherald_rss" in source_ids
    assert "src_bookmyshow_blr" in source_ids

    # Update source enabled/disabled
    repo.update_source("src_bookmyshow_blr", SourceRegistryUpdate(enabled=False, refresh_interval_sec=1800))
    bms = repo.get_source("src_bookmyshow_blr")
    assert bms is not None
    assert bms.enabled is False
    assert bms.refresh_interval_sec == 1800

    # Record run result
    repo.record_run_result("src_gdelt_global", health_status="HEALTHY", collected_at=datetime.now(timezone.utc))
    gdelt = repo.get_source("src_gdelt_global")
    assert gdelt is not None
    assert gdelt.health_status == "HEALTHY"
    assert gdelt.last_collected_at is not None

    # Test evidence recording and retrieval
    from apps.api.app.repositories.events import EventRepository
    event_repo = EventRepository(db)
    demo_event = event_repo.ensure_seeded_demo_event()
    test_event_id = demo_event.event_id

    from apps.api.app.schemas.events import EventEvidenceRecord
    ev_record = EventEvidenceRecord(
        evidence_id=f"evid_{uuid4().hex[:12]}",
        event_id=test_event_id,
        source_platform="bms",
        source_url="https://in.bookmyshow.com/bengaluru/events/rock-night",
        extracted_text="Rock Night at Palace Grounds with 15000 expected fans",
        source_reliability=0.9,
        evidence_confidence=0.85,
        evidence_type="TICKETING_LISTING",
        created_at=datetime.now(timezone.utc),
    )
    repo.add_evidence(ev_record)

    evidence_records = repo.list_evidence_for_event(test_event_id)
    assert len(evidence_records) == 1
    assert evidence_records[0].source_platform == "bms"
    assert evidence_records[0].source_reliability == 0.9
    assert evidence_records[0].evidence_confidence == 0.85


def test_source_registry_api_endpoints():
    """Verify REST API endpoints for source registry list, toggle, probe, and event evidence."""
    app = create_app()
    client = TestClient(app)

    # 1. GET /api/v1/event-intelligence/sources/registry
    resp = client.get("/api/v1/event-intelligence/sources/registry")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 10

    # 2. PATCH /api/v1/event-intelligence/sources/registry/{source_id}
    patch_resp = client.patch(
        "/api/v1/event-intelligence/sources/registry/src_district_blr",
        json={"enabled": False, "refresh_interval_sec": 7200},
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["enabled"] is False
    assert patched["refresh_interval_sec"] == 7200

    # Re-enable
    client.patch("/api/v1/event-intelligence/sources/registry/src_district_blr", json={"enabled": True})

    # 3. POST /api/v1/event-intelligence/sources/registry/{source_id}/test
    test_resp = client.post("/api/v1/event-intelligence/sources/registry/src_district_blr/test")
    assert test_resp.status_code == 200
    test_data = test_resp.json()
    assert "health_status" in test_data
    assert "source_id" in test_data
    assert test_data["source_id"] == "src_district_blr"

    # 4. GET /api/v1/event-intelligence/events/{event_id}/evidence
    random_event_id = uuid4()
    ev_resp = client.get(f"/api/v1/event-intelligence/events/{random_event_id}/evidence")
    assert ev_resp.status_code == 200
    assert isinstance(ev_resp.json(), list)
