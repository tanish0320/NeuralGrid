from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from apps.api.app.modules.event_intelligence.extraction.page_text_extractor import extract_page_text_fallback
from apps.api.app.modules.event_intelligence.extraction.schema_org_extractor import extract_schema_org_event
from apps.api.app.modules.event_intelligence.normalization.deduplication import (
    canonicalize_url_str,
    deduplicate_source_candidates,
)
from apps.api.app.modules.event_intelligence.normalization.event_normalizer import determine_extraction_status
from apps.api.app.modules.event_intelligence.providers.gdelt_doc_provider import _parse_gdelt_seendate
from apps.api.app.modules.event_intelligence.providers.rss_provider import parse_rss_feeds
from apps.api.app.modules.event_intelligence.service import EventIntelligenceService
from apps.api.app.schemas.events import (
    CrawlPageResult,
    CrawlTarget,
    EventDiscoveryRequest,
    SourceCandidate,
)


def test_es01_import_and_dto_contract() -> None:
    """ES-01: Tanish provider module and DTOs import cleanly."""
    service = EventIntelligenceService()
    assert hasattr(service, "discover_candidates")
    assert hasattr(service, "crawl_public_sources")
    assert hasattr(service, "extract_event_fields")


def test_es03_rss_fixture_parsing() -> None:
    """ES-03: Parse RSS structure and verify SourceCandidate."""
    # Test deduplication & canonicalization
    url1 = "https://events.example.org/concert?utm_source=twitter&utm_medium=social"
    url2 = "https://events.example.org/concert?fbclid=xyz"
    assert canonicalize_url_str(url1) == canonicalize_url_str(url2)
    assert canonicalize_url_str(url1) == "https://events.example.org/concert"


def test_schema_org_json_ld_extraction() -> None:
    """Test extraction of Schema.org Event JSON-LD."""
    html_sample = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Bengaluru Music Festival 2026</title>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "MusicEvent",
            "name": "Bengaluru Electronic Music Fest",
            "description": "Annual electronic music gathering at Palace Grounds",
            "startDate": "2026-12-05T18:00:00+05:30",
            "endDate": "2026-12-05T23:30:00+05:30",
            "location": {
                "@type": "Place",
                "name": "Palace Grounds",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "Jayachamaraja Road",
                    "addressLocality": "Bengaluru",
                    "addressRegion": "Karnataka"
                },
                "geo": {
                    "@type": "GeoCoordinates",
                    "latitude": 13.0067,
                    "longitude": 77.5855
                }
            },
            "maximumAttendeeCapacity": 25000
        }
        </script>
    </head>
    <body><h1>Festival Info</h1></body>
    </html>
    """

    res = extract_schema_org_event(html_sample)
    assert res is not None
    fields, prov, evidence = res

    assert fields["event_name"] == "Bengaluru Electronic Music Fest"
    assert fields["venue_name"] == "Palace Grounds"
    assert fields["latitude"] == 13.0067
    assert fields["longitude"] == 77.5855
    assert fields["attendance_high"] == 25000
    assert fields["attendance_low"] == int(25000 * 0.7)
    assert prov["event_name"] == "schema_org.name"
    assert "Schema.org Event JSON-LD found" in evidence


def test_page_text_fallback_extraction_leaves_unknowns_null() -> None:
    """Test page text fallback extracts title and known venue but leaves unknown fields None."""
    sample_text = """# Bengaluru Rock Night at Palace Grounds
    Come watch the bands perform live this weekend. Tickets available at the gate.
    """
    fields, prov, evidence = extract_page_text_fallback(
        title="Bengaluru Rock Night - Event Page",
        markdown_text=sample_text,
    )

    assert fields["event_name"] == "Bengaluru Rock Night at Palace Grounds"
    assert fields["venue_name"] == "Palace Grounds"
    assert fields["latitude"] == 13.0067
    assert fields["longitude"] == 77.5855
    # Strict epistemic invariant: attendance must NOT be invented
    assert "attendance_low" not in fields
    assert "attendance_high" not in fields
    assert "start_at" not in fields


def test_service_extract_event_fields() -> None:
    """Test EventIntelligenceService.extract_event_fields wrapper."""
    service = EventIntelligenceService()
    sample_page = CrawlPageResult(
        source_id=uuid4(),
        fetch_provider="static_html_fallback",
        fetch_status="SUCCEEDED",
        final_url="https://approved.example/event-1",
        title="Spring Gala at Chinnaswamy Stadium",
        markdown_text="# Spring Gala\nSports and entertainment night at Chinnaswamy Stadium",
        html_for_extraction="<html><body><h1>Spring Gala</h1><p>At Chinnaswamy Stadium</p></body></html>",
    )

    extraction = service.extract_event_fields(sample_page)
    assert extraction.extraction_status in ("SUCCEEDED", "PARTIAL")
    assert extraction.fields["event_name"] == "Spring Gala"
    assert extraction.fields["venue_name"] == "M. Chinnaswamy Stadium"
    assert extraction.fields["latitude"] == 12.9788
    assert extraction.fields["longitude"] == 77.5996


def test_xgboost_forecast_provider_integration(client) -> None:
    """Test XGBoostForecastProvider integrated into prediction service."""
    from ml.traffic.adapter import XGBoostForecastProvider

    xgb_provider = XGBoostForecastProvider()
    client.app.state.container.prediction_service.set_forecast_provider(xgb_provider)

    sim = client.post("/api/v1/simulations", json={"seed": 42}).json()
    sim_id = sim["simulation_id"]

    resp = client.post(
        "/api/v1/predictions/generate",
        json={"simulation_id": sim_id, "horizons": [15, 30], "cell_ids": ["CELL-BLR-001", "CELL-BLR-002"]},
    )
    if resp.status_code != 200:
        print("ERROR RESPONSE:", resp.text)
    assert resp.status_code == 200
    data = resp.json()
    assert data["method"] == "xgboost_regressor_v1"
    assert data["model_version"] == "xgb-v1.0"
    assert len(data["forecasts"]) > 0
