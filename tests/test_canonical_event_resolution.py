from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest

from apps.api.app.core.database import Database
from apps.api.app.modules.event_intelligence.resolution.resolver import CanonicalEventResolver
from apps.api.app.repositories.events import EventRepository
from apps.api.app.repositories.source_registry import SourceRegistryRepository


@pytest.fixture
def test_resolver(tmp_path):
    db_file = str(tmp_path / "test_canonical_events.db")
    db = Database(db_file)
    db.init_schema()

    event_repo = EventRepository(db)
    registry_repo = SourceRegistryRepository(db)
    return CanonicalEventResolver(event_repo=event_repo, registry_repo=registry_repo)


def test_case_1_same_event_six_different_sources(test_resolver):
    """1. Same event reported by six different sources must resolve to one canonical event with 6 evidence records."""
    sources = [
        ("src_bookmyshow_blr", "TICKETING", "https://in.bookmyshow.com/events/arijit-singh-live/ET001", "bookmyshow.com", "hash_bms_1"),
        ("src_deccanherald_rss", "NEWS", "https://deccanherald.com/bengaluru/arijit-singh-concert-palace-grounds", "deccanherald.com", "hash_dh_2"),
        ("src_thehindu_rss", "NEWS", "https://thehindu.com/entertainment/music/arijit-singh-bengaluru-live", "thehindu.com", "hash_th_3"),
        ("src_allevents_blr", "TICKETING", "https://allevents.in/bangalore/arijit-singh-india-tour", "allevents.in", "hash_ae_4"),
        ("src_crawl4ai_web", "PUBLIC_SCRAPER", "https://timesofindia.indiatimes.com/city/bangalore/arijit-live", "timesofindia.indiatimes.com", "hash_toi_5"),
        ("src_reddit_blr", "REDDIT", "https://reddit.com/r/bangalore/comments/arijit_concert", "reddit.com", "hash_rd_6"),
    ]

    event_date = datetime(2026, 12, 15, 18, 30, tzinfo=timezone.utc)
    canonical_event = None

    for idx, (sid, platform, url, domain, chash) in enumerate(sources):
        ev, is_new, match_info = test_resolver.resolve_candidate(
            title="Arijit Singh Live in Concert Bengaluru",
            source_id=sid,
            source_platform=platform,
            source_url=url,
            domain=domain,
            content_hash=chash,
            extracted_fields={
                "name": "Arijit Singh Live",
                "venue_name": "Palace Grounds",
                "start_at": event_date,
                "attendance_high": 35000,
            },
        )
        if idx == 0:
            assert is_new is True
            canonical_event = ev
        else:
            assert is_new is False
            assert ev.event_id == canonical_event.event_id

    # Verify canonical event properties
    detail = test_resolver.get_canonical_event_detail(canonical_event.event_id)
    assert detail is not None
    assert len(detail.event.source_ids) == 6
    assert len(detail.evidence) == 6
    assert detail.event.verification_status in ("VERIFIED", "CORROBORATED")
    assert detail.event.venue_name == "Palace Grounds"


def test_case_2_same_event_slightly_different_titles(test_resolver):
    """2. Same event with slightly different titles must match and merge."""
    start_time = datetime(2026, 11, 28, 19, 0, tzinfo=timezone.utc)

    # First source
    ev1, is_new1, _ = test_resolver.resolve_candidate(
        title="Coldplay Music of the Spheres World Tour - Bengaluru",
        source_id="src_bookmyshow_blr",
        source_platform="TICKETING",
        source_url="https://in.bookmyshow.com/events/coldplay-live/ET999",
        domain="bookmyshow.com",
        extracted_fields={
            "name": "Coldplay Music of the Spheres World Tour - Bengaluru",
            "venue_name": "M. Chinnaswamy Stadium",
            "start_at": start_time,
        },
    )
    assert is_new1 is True

    # Second source with colloquial title
    ev2, is_new2, match_info = test_resolver.resolve_candidate(
        title="Coldplay Live in Bangalore Concert Tickets Booking Open",
        source_id="src_deccanherald_rss",
        source_platform="NEWS",
        source_url="https://deccanherald.com/city/bangalore/coldplay-live-tickets",
        domain="deccanherald.com",
        extracted_fields={
            "name": "Coldplay Live in Bangalore Concert",
            "venue_name": "Chinnaswamy Stadium",
            "start_at": start_time,
        },
    )
    assert is_new2 is False
    assert ev2.event_id == ev1.event_id
    assert match_info is not None
    assert match_info.is_match is True
    assert match_info.confidence >= 0.70


def test_case_3_same_venue_two_different_events(test_resolver):
    """3. Same venue hosting two different events on the same day must NOT be merged."""
    date = datetime(2026, 12, 10, 10, 0, tzinfo=timezone.utc)

    # Event 1: Tech Summit
    ev1, is_new1, _ = test_resolver.resolve_candidate(
        title="Bangalore Tech Summit 2026 Innovation Conclave",
        source_id="src_thehindu_rss",
        source_platform="NEWS",
        source_url="https://thehindu.com/tech/bts-2026",
        domain="thehindu.com",
        extracted_fields={
            "name": "Bangalore Tech Summit 2026",
            "venue_name": "Palace Grounds",
            "start_at": date,
        },
    )
    assert is_new1 is True

    # Event 2: Sunburn EDM Night (same venue, same date, completely different event)
    ev2, is_new2, match_info = test_resolver.resolve_candidate(
        title="Sunburn Arena EDM Electronic Night Bangalore",
        source_id="src_bookmyshow_blr",
        source_platform="TICKETING",
        source_url="https://bookmyshow.com/sunburn-arena",
        domain="bookmyshow.com",
        extracted_fields={
            "name": "Sunburn Arena EDM Night",
            "venue_name": "Palace Grounds",
            "start_at": date,
        },
    )
    assert is_new2 is True
    assert ev2.event_id != ev1.event_id


def test_case_4_different_dates_for_otherwise_similar_events(test_resolver):
    """4. Different dates for otherwise similar events must NOT be merged."""
    # Match 1 in April
    ev1, is_new1, _ = test_resolver.resolve_candidate(
        title="RCB vs CSK IPL 2026 League Match Chinnaswamy",
        source_id="src_thehindu_rss",
        source_platform="NEWS",
        source_url="https://thehindu.com/sports/rcb-csk-match-1",
        domain="thehindu.com",
        extracted_fields={
            "name": "RCB vs CSK IPL Match",
            "venue_name": "Chinnaswamy Stadium",
            "start_at": datetime(2026, 4, 10, 19, 30, tzinfo=timezone.utc),
        },
    )
    assert is_new1 is True

    # Match 2 in May (different match in same tournament)
    ev2, is_new2, _ = test_resolver.resolve_candidate(
        title="RCB vs CSK IPL 2026 Playoffs Qualifier Chinnaswamy",
        source_id="src_timesofindia_rss",
        source_platform="NEWS",
        source_url="https://timesofindia.indiatimes.com/sports/rcb-csk-match-2",
        domain="timesofindia.indiatimes.com",
        extracted_fields={
            "name": "RCB vs CSK IPL Match",
            "venue_name": "Chinnaswamy Stadium",
            "start_at": datetime(2026, 5, 20, 19, 30, tzinfo=timezone.utc),
        },
    )
    assert is_new2 is True
    assert ev2.event_id != ev1.event_id


def test_case_5_conflicting_event_start_times(test_resolver):
    """5. Conflicting event start times must be flagged and tracked in conflicts without crashing."""
    ev1, _, _ = test_resolver.resolve_candidate(
        title="Rock Festival India Bengaluru",
        source_id="src_thehindu_rss",
        source_platform="NEWS",
        source_url="https://thehindu.com/events/rock-fest",
        domain="thehindu.com",
        extracted_fields={
            "name": "Rock Festival India",
            "venue_name": "Kanteerava Stadium",
            "start_at": datetime(2026, 12, 1, 14, 0, tzinfo=timezone.utc),
        },
    )

    # Second source claims it starts at 20:00 UTC (6 hours later)
    ev2, is_new, match_info = test_resolver.resolve_candidate(
        title="Rock Festival India Official Timings",
        source_id="src_district_blr",
        source_platform="TICKETING",
        source_url="https://district.in/rock-fest-timing",
        domain="district.in",
        extracted_fields={
            "name": "Rock Festival India",
            "venue_name": "Kanteerava Stadium",
            "start_at": datetime(2026, 12, 1, 20, 0, tzinfo=timezone.utc),
        },
    )
    assert is_new is False
    assert ev2.event_id == ev1.event_id

    detail = test_resolver.get_canonical_event_detail(ev1.event_id)
    assert len(detail.conflicts) >= 1
    start_conflict = next((c for c in detail.conflicts if c.get("field") == "start_at"), None)
    assert start_conflict is not None
    assert detail.event.verification_status == "CONFLICTED"


def test_case_6_missing_coordinates(test_resolver):
    """6. Missing coordinates should remain None and never be fabricated."""
    ev, is_new, _ = test_resolver.resolve_candidate(
        title="Independent Film Screening at Unregistered Private Gallery",
        source_id="src_reddit_blr",
        source_platform="REDDIT",
        source_url="https://reddit.com/r/bangalore/comments/gallery_indie",
        domain="reddit.com",
        extracted_fields={
            "name": "Independent Film Screening",
            "venue_name": "Private Basement Gallery XYZ",  # Non-canonical venue
            "start_at": datetime(2026, 12, 5, 18, 0, tzinfo=timezone.utc),
            # No latitude or longitude provided
        },
    )
    assert is_new is True
    assert ev.latitude is None
    assert ev.longitude is None


def test_case_7_missing_attendance(test_resolver):
    """7. Missing attendance should remain None / UNKNOWN and never be fabricated."""
    ev, is_new, _ = test_resolver.resolve_candidate(
        title="Open Source Developers Meetup Bengaluru",
        source_id="src_thehindu_rss",
        source_platform="NEWS",
        source_url="https://thehindu.com/tech/open-source-meet",
        domain="thehindu.com",
        extracted_fields={
            "name": "Open Source Developers Meetup",
            "venue_name": "KTPO Whitefield",
            "start_at": datetime(2026, 12, 2, 10, 0, tzinfo=timezone.utc),
            # No attendance numbers
        },
    )
    assert is_new is True
    assert ev.attendance_high is None
    assert ev.attendance_low is None
    assert ev.attendance_basis == "UNKNOWN"


def test_case_8_cancelled_event(test_resolver):
    """8. Cancelled event updates status to CANCELLED and preserves evidence and history."""
    ev, _, _ = test_resolver.resolve_candidate(
        title="Maroon 5 India Tour Bengaluru",
        source_id="src_bookmyshow_blr",
        source_platform="TICKETING",
        source_url="https://bookmyshow.com/maroon-5",
        domain="bookmyshow.com",
        extracted_fields={
            "name": "Maroon 5 India Tour",
            "venue_name": "Palace Grounds",
            "start_at": datetime(2026, 12, 20, 19, 0, tzinfo=timezone.utc),
        },
    )
    assert ev.status == "UPCOMING"

    # Cancellation announcement arrives
    ev_updated, is_new, _ = test_resolver.resolve_candidate(
        title="Maroon 5 India Tour Cancelled Due to Unforeseen Circumstances",
        source_id="src_deccanherald_rss",
        source_platform="NEWS",
        source_url="https://deccanherald.com/city/maroon-5-cancelled",
        domain="deccanherald.com",
        extracted_fields={
            "name": "Maroon 5 India Tour",
            "venue_name": "Palace Grounds",
            "start_at": datetime(2026, 12, 20, 19, 0, tzinfo=timezone.utc),
            "raw_text": "The Maroon 5 concert has been officially cancelled due to security advisories.",
        },
    )
    assert is_new is False
    assert ev_updated.status == "CANCELLED"
    assert ev_updated.verification_status == "CANCELLED"

    detail = test_resolver.get_canonical_event_detail(ev.event_id)
    assert len(detail.evidence) == 2
    assert len(detail.history) >= 2


def test_case_9_postponed_event(test_resolver):
    """9. Postponed event updates status to POSTPONED and preserves provenance."""
    ev, _, _ = test_resolver.resolve_candidate(
        title="Bengaluru Jazz Festival Annual Edition",
        source_id="src_thehindu_rss",
        source_platform="NEWS",
        source_url="https://thehindu.com/entertainment/jazz-fest",
        domain="thehindu.com",
        extracted_fields={
            "name": "Bengaluru Jazz Festival",
            "venue_name": "Indiranagar Club Grounds",
            "start_at": datetime(2026, 12, 5, 17, 0, tzinfo=timezone.utc),
        },
    )

    # Postponement notice
    ev_updated, is_new, _ = test_resolver.resolve_candidate(
        title="Bengaluru Jazz Festival Postponed to January Next Year",
        source_id="src_bangaloremirror_rss",
        source_platform="NEWS",
        source_url="https://bangaloremirror.indiatimes.com/jazz-postponed",
        domain="bangaloremirror.indiatimes.com",
        extracted_fields={
            "name": "Bengaluru Jazz Festival",
            "venue_name": "Indiranagar Club Grounds",
            "start_at": datetime(2026, 12, 5, 17, 0, tzinfo=timezone.utc),
            "raw_text": "Organisers confirmed the festival is postponed to early next year.",
        },
    )
    assert is_new is False
    assert ev_updated.status == "POSTPONED"


def test_case_10_duplicate_social_media_announcements(test_resolver):
    """10. Duplicate social-media announcements do not elevate verification to CORROBORATED."""
    ev1, is_new1, _ = test_resolver.resolve_candidate(
        title="Crowd Gathering Flash Mob at Koramangala 80ft Road",
        source_id="src_twitter_x_v2",
        source_platform="TWITTER",
        source_url="https://twitter.com/user1/status/10001",
        domain="twitter.com",
        content_hash="tweet_hash_repeat",
        extracted_fields={
            "name": "Flash Mob Koramangala",
            "venue_name": "Koramangala Indoor Stadium",
            "start_at": datetime(2026, 11, 30, 16, 0, tzinfo=timezone.utc),
        },
    )
    assert is_new1 is True
    assert ev1.verification_status in ("DISCOVERED", "PARTIALLY_VERIFIED")

    # Duplicate tweet from same domain / duplicate text
    ev2, is_new2, _ = test_resolver.resolve_candidate(
        title="Crowd Gathering Flash Mob at Koramangala 80ft Road",
        source_id="src_twitter_x_v2",
        source_platform="TWITTER",
        source_url="https://twitter.com/user2/status/10002",
        domain="twitter.com",
        content_hash="tweet_hash_repeat",
        extracted_fields={
            "name": "Flash Mob Koramangala",
            "venue_name": "Koramangala Indoor Stadium",
            "start_at": datetime(2026, 11, 30, 16, 0, tzinfo=timezone.utc),
        },
    )
    assert is_new2 is False
    assert ev2.verification_status != "CORROBORATED"


def test_case_11_two_independent_sources_corroborating(test_resolver):
    """11. Two independent news sources with distinct content hashes corroborate an event."""
    start = datetime(2026, 12, 22, 18, 0, tzinfo=timezone.utc)

    # Source 1: Deccan Herald
    ev1, is_new1, _ = test_resolver.resolve_candidate(
        title="Classical Carnatic Music Sangeethotsava Bengaluru",
        source_id="src_deccanherald_rss",
        source_platform="NEWS",
        source_url="https://deccanherald.com/city/carnatic-fest",
        domain="deccanherald.com",
        content_hash="dh_original_article_771",
        extracted_fields={
            "name": "Carnatic Music Sangeethotsava",
            "venue_name": "National College Grounds Basavanagudi",
            "start_at": start,
        },
    )
    assert is_new1 is True
    assert ev1.verification_status == "PARTIALLY_VERIFIED"

    # Source 2: The Hindu (independent news organization, distinct domain and content hash)
    ev2, is_new2, _ = test_resolver.resolve_candidate(
        title="Carnatic Music Sangeethotsava Basavanagudi Schedule",
        source_id="src_thehindu_rss",
        source_platform="NEWS",
        source_url="https://thehindu.com/entertainment/carnatic-sangeethotsava",
        domain="thehindu.com",
        content_hash="th_independent_report_882",
        extracted_fields={
            "name": "Carnatic Music Sangeethotsava",
            "venue_name": "National College Grounds Basavanagudi",
            "start_at": start,
        },
    )
    assert is_new2 is False
    assert ev2.verification_status == "CORROBORATED"


def test_case_12_several_sources_repeating_same_original_announcement(test_resolver):
    """12. Several sources repeating identical syndicated press release (same hash) do NOT count as independent corroboration."""
    start = datetime(2026, 12, 25, 11, 0, tzinfo=timezone.utc)
    syndicated_hash = "pti_wire_feed_sha256_identical"

    sources = [
        ("src_deccanherald_rss", "deccanherald.com", "https://deccanherald.com/pti-story-1"),
        ("src_timesofindia_rss", "timesofindia.indiatimes.com", "https://timesofindia.com/pti-story-2"),
        ("src_indianexpress_rss", "indianexpress.com", "https://indianexpress.com/pti-story-3"),
    ]

    canonical_ev = None
    for idx, (sid, domain, url) in enumerate(sources):
        ev, is_new, _ = test_resolver.resolve_candidate(
            title="Karnataka State Handloom Expo Bengaluru Inauguration",
            source_id=sid,
            source_platform="NEWS",
            source_url=url,
            domain=domain,
            content_hash=syndicated_hash,  # Identical syndicated wire hash
            extracted_fields={
                "name": "Karnataka Handloom Expo",
                "venue_name": "Palace Grounds",
                "start_at": start,
            },
        )
        if idx == 0:
            canonical_ev = ev

    # All 3 attached to canonical_ev, but because content hash was identical across syndicated portals,
    # it does not satisfy the independent non-syndicated corroboration standard!
    detail = test_resolver.get_canonical_event_detail(canonical_ev.event_id)
    assert len(detail.evidence) == 3
    assert detail.event.verification_status != "CORROBORATED"
