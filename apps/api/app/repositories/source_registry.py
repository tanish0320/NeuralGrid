from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID, uuid4
from apps.api.app.core.database import Database, parse_utc, utc_iso, utc_now
from apps.api.app.schemas.events import EventEvidenceRecord, SourceRegistryItem, SourceRegistryUpdate

DEFAULT_BENGALURU_SOURCES = [
    {
        "source_id": "src_gdelt_global",
        "platform": "GDELT",
        "display_name": "GDELT DOC 2.0 Global News (Bengaluru)",
        "base_url": "https://api.gdeltproject.org/api/v2/doc/doc",
        "connector_type": "GDELTConnector",
        "enabled": 1,
        "access_method": "PUBLIC_API",
        "refresh_interval_sec": 1800,
        "geographic_scope": "Bengaluru",
        "supported_categories": ["CONCERT", "SPORTS", "FESTIVAL", "EXHIBITION", "TECH_CONFERENCE"],
        "health_status": "HEALTHY",
    },
    {
        "source_id": "src_deccanherald_rss",
        "platform": "NEWS",
        "display_name": "Deccan Herald Bengaluru & Karnataka",
        "base_url": "https://www.deccanherald.com/rss/bengaluru.rss",
        "connector_type": "RSSNewsConnector",
        "enabled": 1,
        "access_method": "RSS_FEED",
        "refresh_interval_sec": 1800,
        "geographic_scope": "Bengaluru",
        "supported_categories": ["CONCERT", "FESTIVAL", "PROTEST", "PUBLIC_EVENT"],
        "health_status": "HEALTHY",
    },
    {
        "source_id": "src_thehindu_rss",
        "platform": "NEWS",
        "display_name": "The Hindu Bengaluru",
        "base_url": "https://www.thehindu.com/news/cities/bangalore/feeder/default.rss",
        "connector_type": "RSSNewsConnector",
        "enabled": 1,
        "access_method": "RSS_FEED",
        "refresh_interval_sec": 3600,
        "geographic_scope": "Bengaluru",
        "supported_categories": ["CONCERT", "SPORTS", "FESTIVAL", "POLITICAL"],
        "health_status": "HEALTHY",
    },
    {
        "source_id": "src_timesofindia_rss",
        "platform": "NEWS",
        "display_name": "Times of India Bengaluru News",
        "base_url": "https://timesofindia.indiatimes.com/rssfeeds/-2128833038.cms",
        "connector_type": "RSSNewsConnector",
        "enabled": 1,
        "access_method": "RSS_FEED",
        "refresh_interval_sec": 3600,
        "geographic_scope": "Bengaluru",
        "supported_categories": ["CONCERT", "SPORTS", "FESTIVAL", "TRAFFIC"],
        "health_status": "HEALTHY",
    },
    {
        "source_id": "src_indianexpress_rss",
        "platform": "NEWS",
        "display_name": "The Indian Express Bengaluru",
        "base_url": "https://indianexpress.com/section/cities/bangalore/feed/",
        "connector_type": "RSSNewsConnector",
        "enabled": 1,
        "access_method": "RSS_FEED",
        "refresh_interval_sec": 3600,
        "geographic_scope": "Bengaluru",
        "supported_categories": ["CONCERT", "FESTIVAL", "TECH_CONFERENCE"],
        "health_status": "HEALTHY",
    },
    {
        "source_id": "src_bangaloremirror_rss",
        "platform": "NEWS",
        "display_name": "Bangalore Mirror City Pulse",
        "base_url": "https://bangaloremirror.indiatimes.com/rssfeeds/20970472.cms",
        "connector_type": "RSSNewsConnector",
        "enabled": 1,
        "access_method": "RSS_FEED",
        "refresh_interval_sec": 3600,
        "geographic_scope": "Bengaluru",
        "supported_categories": ["NIGHTLIFE", "FESTIVAL", "CONCERT"],
        "health_status": "HEALTHY",
    },
    {
        "source_id": "src_bookmyshow_blr",
        "platform": "TICKETING",
        "display_name": "BookMyShow Bengaluru Live Events",
        "base_url": "https://in.bookmyshow.com/explore/events-bengaluru",
        "connector_type": "BookMyShowConnector",
        "enabled": 1,
        "access_method": "PUBLIC_SCRAPER",
        "refresh_interval_sec": 3600,
        "geographic_scope": "Bengaluru",
        "supported_categories": ["CONCERT", "COMEDY", "SPORTS", "THEATRE"],
        "health_status": "HEALTHY",
    },
    {
        "source_id": "src_district_blr",
        "platform": "TICKETING",
        "display_name": "District by Zomato (Bengaluru)",
        "base_url": "https://www.district.in/bengaluru/events",
        "connector_type": "DistrictConnector",
        "enabled": 1,
        "access_method": "PUBLIC_SCRAPER",
        "refresh_interval_sec": 3600,
        "geographic_scope": "Bengaluru",
        "supported_categories": ["CONCERT", "FOOD_FESTIVAL", "NIGHTLIFE"],
        "health_status": "HEALTHY",
    },
    {
        "source_id": "src_allevents_blr",
        "platform": "TICKETING",
        "display_name": "AllEvents.in Bengaluru",
        "base_url": "https://allevents.in/bangalore",
        "connector_type": "AllEventsConnector",
        "enabled": 1,
        "access_method": "PUBLIC_SCRAPER",
        "refresh_interval_sec": 7200,
        "geographic_scope": "Bengaluru",
        "supported_categories": ["CONCERT", "WORKSHOP", "EXHIBITION", "FESTIVAL"],
        "health_status": "HEALTHY",
    },
    {
        "source_id": "src_twitter_x_v2",
        "platform": "TWITTER",
        "display_name": "X (Twitter) API v2 Bengaluru Search",
        "base_url": "https://api.twitter.com/2/tweets/search/recent",
        "connector_type": "TwitterXConnector",
        "enabled": 1,
        "access_method": "OFFICIAL_OAUTH",
        "refresh_interval_sec": 900,
        "geographic_scope": "Bengaluru",
        "supported_categories": ["BREAKING_CROWD", "TRAFFIC", "CONCERT", "CONFERENCE"],
        "health_status": "AWAITING_CREDENTIALS",
    },
    {
        "source_id": "src_instagram_graph",
        "platform": "INSTAGRAM",
        "display_name": "Instagram Public Creator & Venue Posts",
        "base_url": "https://graph.facebook.com/v19.0",
        "connector_type": "InstagramConnector",
        "enabled": 1,
        "access_method": "OFFICIAL_OAUTH",
        "refresh_interval_sec": 1800,
        "geographic_scope": "Bengaluru",
        "supported_categories": ["CONCERT", "COLLEGE_FEST", "NIGHTLIFE", "FESTIVAL"],
        "health_status": "AWAITING_CREDENTIALS",
    },
    {
        "source_id": "src_reddit_bangalore",
        "platform": "REDDIT",
        "display_name": "Reddit /r/bangalore Events & Gatherings",
        "base_url": "https://oauth.reddit.com/r/bangalore",
        "connector_type": "RedditConnector",
        "enabled": 1,
        "access_method": "OFFICIAL_OAUTH",
        "refresh_interval_sec": 1800,
        "geographic_scope": "Bengaluru",
        "supported_categories": ["COMMUNITY_EVENT", "TECH_MEETUP", "TRAFFIC", "FESTIVAL"],
        "health_status": "AWAITING_CREDENTIALS",
    },
    {
        "source_id": "src_youtube_events",
        "platform": "YOUTUBE",
        "display_name": "YouTube Data API v3 Venue Promos",
        "base_url": "https://www.googleapis.com/youtube/v3/search",
        "connector_type": "YouTubeConnector",
        "enabled": 1,
        "access_method": "API_TOKEN",
        "refresh_interval_sec": 7200,
        "geographic_scope": "Bengaluru",
        "supported_categories": ["CONCERT", "FESTIVAL", "LIVESTREAM"],
        "health_status": "AWAITING_CREDENTIALS",
    },
    {
        "source_id": "src_telegram_events",
        "platform": "TELEGRAM",
        "display_name": "Telegram Public Bengaluru Event Announcements",
        "base_url": "https://api.telegram.org",
        "connector_type": "TelegramConnector",
        "enabled": 1,
        "access_method": "API_TOKEN",
        "refresh_interval_sec": 3600,
        "geographic_scope": "Bengaluru",
        "supported_categories": ["COMMUNITY_EVENT", "TECH_MEETUP", "NIGHTLIFE"],
        "health_status": "AWAITING_CREDENTIALS",
    },
]


class SourceRegistryRepository:
    """SQLite repository for central source registry and multi-source evidence tracking."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.seed_default_registry()

    def seed_default_registry(self) -> None:
        now_str = utc_iso(utc_now())
        with self.db.transaction() as conn:
            for item in DEFAULT_BENGALURU_SOURCES:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO event_source_registry (
                        source_id, platform, display_name, base_url, connector_type,
                        enabled, access_method, refresh_interval_sec, geographic_scope,
                        supported_categories_json, last_collected_at, last_error,
                        health_status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)
                    """,
                    (
                        item["source_id"],
                        item["platform"],
                        item["display_name"],
                        item["base_url"],
                        item["connector_type"],
                        item["enabled"],
                        item["access_method"],
                        item["refresh_interval_sec"],
                        item["geographic_scope"],
                        json.dumps(item["supported_categories"]),
                        item["health_status"],
                        now_str,
                        now_str,
                    ),
                )

    def list_sources(
        self, platform: str | None = None, enabled_only: bool = False
    ) -> list[SourceRegistryItem]:
        query = "SELECT * FROM event_source_registry WHERE 1=1"
        params: list[object] = []
        if platform:
            query += " AND platform = ?"
            params.append(platform)
        if enabled_only:
            query += " AND enabled = 1"
        query += " ORDER BY platform, display_name"

        with self.db.transaction() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        items: list[SourceRegistryItem] = []
        for row in rows:
            cats = json.loads(row["supported_categories_json"]) if row["supported_categories_json"] else []
            items.append(
                SourceRegistryItem(
                    source_id=row["source_id"],
                    platform=row["platform"],
                    display_name=row["display_name"],
                    base_url=row["base_url"],
                    connector_type=row["connector_type"],
                    enabled=bool(row["enabled"]),
                    access_method=row["access_method"],
                    refresh_interval_sec=row["refresh_interval_sec"],
                    geographic_scope=row["geographic_scope"],
                    supported_categories=cats,
                    last_collected_at=parse_utc(row["last_collected_at"]) if row["last_collected_at"] else None,
                    last_error=row["last_error"],
                    health_status=row["health_status"],
                    created_at=parse_utc(row["created_at"]),
                    updated_at=parse_utc(row["updated_at"]),
                )
            )
        return items

    def get_source(self, source_id: str) -> SourceRegistryItem | None:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "SELECT * FROM event_source_registry WHERE source_id = ?", (source_id,)
            )
            row = cursor.fetchone()
        if not row:
            return None
        cats = json.loads(row["supported_categories_json"]) if row["supported_categories_json"] else []
        return SourceRegistryItem(
            source_id=row["source_id"],
            platform=row["platform"],
            display_name=row["display_name"],
            base_url=row["base_url"],
            connector_type=row["connector_type"],
            enabled=bool(row["enabled"]),
            access_method=row["access_method"],
            refresh_interval_sec=row["refresh_interval_sec"],
            geographic_scope=row["geographic_scope"],
            supported_categories=cats,
            last_collected_at=parse_utc(row["last_collected_at"]) if row["last_collected_at"] else None,
            last_error=row["last_error"],
            health_status=row["health_status"],
            created_at=parse_utc(row["created_at"]),
            updated_at=parse_utc(row["updated_at"]),
        )

    def update_source(
        self, source_id: str, update: SourceRegistryUpdate
    ) -> SourceRegistryItem | None:
        now_str = utc_iso(utc_now())
        updates: list[str] = ["updated_at = ?"]
        params: list[object] = [now_str]

        if update.enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if update.enabled else 0)
        if update.refresh_interval_sec is not None:
            updates.append("refresh_interval_sec = ?")
            params.append(update.refresh_interval_sec)

        params.append(source_id)
        with self.db.transaction() as conn:
            conn.execute(
                f"UPDATE event_source_registry SET {', '.join(updates)} WHERE source_id = ?",
                params,
            )
        return self.get_source(source_id)

    def record_run_result(
        self,
        source_id: str,
        health_status: str,
        error_message: str | None = None,
        collected_at: datetime | None = None,
    ) -> None:
        now = utc_now()
        now_str = utc_iso(now)
        col_str = utc_iso(collected_at or now) if health_status == "HEALTHY" else None

        with self.db.transaction() as conn:
            if col_str:
                conn.execute(
                    """
                    UPDATE event_source_registry
                    SET health_status = ?, last_error = ?, last_collected_at = ?, updated_at = ?
                    WHERE source_id = ?
                    """,
                    (health_status, error_message, col_str, now_str, source_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE event_source_registry
                    SET health_status = ?, last_error = ?, updated_at = ?
                    WHERE source_id = ?
                    """,
                    (health_status, error_message, now_str, source_id),
                )

    def add_evidence(self, evidence: EventEvidenceRecord) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO event_evidence (
                    evidence_id, event_id, source_platform, source_url,
                    source_timestamp, evidence_type, extracted_text,
                    source_reliability, evidence_confidence, raw_metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.evidence_id,
                    str(evidence.event_id),
                    evidence.source_platform,
                    evidence.source_url,
                    utc_iso(evidence.source_timestamp) if evidence.source_timestamp else None,
                    evidence.evidence_type,
                    evidence.extracted_text,
                    evidence.source_reliability,
                    evidence.evidence_confidence,
                    json.dumps(evidence.raw_metadata),
                    utc_iso(evidence.created_at),
                ),
            )

    def list_evidence_for_event(self, event_id: UUID) -> list[EventEvidenceRecord]:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "SELECT * FROM event_evidence WHERE event_id = ? ORDER BY created_at DESC",
                (str(event_id),),
            )
            rows = cursor.fetchall()

        records: list[EventEvidenceRecord] = []
        for r in rows:
            records.append(
                EventEvidenceRecord(
                    evidence_id=r["evidence_id"],
                    event_id=UUID(r["event_id"]),
                    source_platform=r["source_platform"],
                    source_url=r["source_url"],
                    source_timestamp=parse_utc(r["source_timestamp"]) if r["source_timestamp"] else None,
                    evidence_type=r["evidence_type"],
                    extracted_text=r["extracted_text"],
                    source_reliability=r["source_reliability"],
                    evidence_confidence=r["evidence_confidence"],
                    raw_metadata=json.loads(r["raw_metadata_json"]) if r["raw_metadata_json"] else {},
                    created_at=parse_utc(r["created_at"]),
                )
            )
        return records
