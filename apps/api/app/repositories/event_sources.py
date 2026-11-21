from __future__ import annotations

import json
import uuid
from typing import Any
from uuid import UUID

from apps.api.app.core.database import Database, parse_utc, utc_iso, utc_now
from apps.api.app.schemas.events import (
    DiscoveryRunDetailResponse,
    DiscoveryRunStatus,
    EventDiscoveryRequest,
    EventSourceRecord,
    ExtractionStatus,
    FetchProvider,
    FetchStatus,
    ProviderRunSummary,
)


class EventSourceRepository:
    """SQLite persistence for EventSense discovery runs and source evidence records."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create_discovery_run(self, run_id: UUID, request: EventDiscoveryRequest) -> None:
        now_iso = utc_iso(utc_now())
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO event_discovery_runs (
                    run_id, city, query_terms_json, provider_config_json,
                    status, providers_json, warnings_json, started_at, completed_at
                ) VALUES (?, ?, ?, ?, 'RUNNING', '[]', '[]', ?, NULL)
                """,
                (
                    str(run_id),
                    request.city,
                    json.dumps(request.query_terms),
                    request.model_dump_json(),
                    now_iso,
                ),
            )

    def complete_discovery_run(
        self,
        run_id: UUID,
        status: DiscoveryRunStatus,
        providers: list[ProviderRunSummary],
        warnings: list[str],
    ) -> None:
        now_iso = utc_iso(utc_now())
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE event_discovery_runs SET
                    status = ?, providers_json = ?, warnings_json = ?, completed_at = ?
                WHERE run_id = ?
                """,
                (
                    status,
                    json.dumps([p.model_dump(mode="json") for p in providers]),
                    json.dumps(warnings),
                    now_iso,
                    str(run_id),
                ),
            )

    def get_discovery_run(self, run_id: UUID | str) -> DiscoveryRunDetailResponse | None:
        row = self.db.fetchone(
            "SELECT * FROM event_discovery_runs WHERE run_id = ?", (str(run_id),)
        )
        if not row:
            return None
        source_rows = self.db.fetchall(
            "SELECT source_id FROM event_sources WHERE discovery_run_id = ? ORDER BY discovered_at ASC",
            (str(run_id),),
        )
        providers = [ProviderRunSummary(**p) for p in json.loads(row["providers_json"])]
        return DiscoveryRunDetailResponse(
            run_id=UUID(row["run_id"]),
            city=row["city"],
            query_terms=json.loads(row["query_terms_json"]),
            status=row["status"],
            providers=providers,
            source_ids=[UUID(s["source_id"]) for s in source_rows],
            warnings=json.loads(row["warnings_json"]),
            started_at=parse_utc(row["started_at"]),
            completed_at=parse_utc(row["completed_at"]) if row["completed_at"] else None,
        )

    def upsert_candidate_source(
        self,
        *,
        run_id: UUID,
        discovery_provider: str,
        source_type: str,
        url: str,
        canonical_url: str,
        domain: str,
        title: str | None,
        snippet: str | None,
        published_at: Any,
        discovered_at: Any,
        fetch_status: FetchStatus,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> tuple[UUID, bool]:
        """Insert candidate source or return existing ID if (run_id, canonical_url) exists."""
        existing = self.db.fetchone(
            "SELECT source_id FROM event_sources WHERE discovery_run_id = ? AND canonical_url = ?",
            (str(run_id), canonical_url),
        )
        if existing:
            return UUID(existing["source_id"]), False

        source_id = uuid.uuid4()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO event_sources (
                    source_id, discovery_run_id, event_id, discovery_provider, fetch_provider,
                    source_type, canonical_url, url, domain, title, snippet, published_at,
                    discovered_at, collected_at, fetch_status, extraction_status,
                    content_hash, evidence_summary, extracted_fields_json, field_provenance_json,
                    crawl_attempts, error_code, error_message
                ) VALUES (?, ?, NULL, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 'NOT_RUN', NULL, NULL, '{}', '{}', 0, ?, ?)
                """,
                (
                    str(source_id),
                    str(run_id),
                    discovery_provider,
                    source_type,
                    canonical_url,
                    url,
                    domain,
                    title,
                    snippet,
                    utc_iso(published_at) if published_at else None,
                    utc_iso(discovered_at),
                    fetch_status,
                    error_code,
                    error_message,
                ),
            )
        return source_id, True

    def _row_to_source(self, row: Any) -> EventSourceRecord:
        fetch_status: FetchStatus = row["fetch_status"]
        return EventSourceRecord(
            source_id=UUID(row["source_id"]),
            discovery_run_id=UUID(row["discovery_run_id"]),
            event_id=UUID(row["event_id"]) if row["event_id"] else None,
            discovery_provider=row["discovery_provider"],
            fetch_provider=row["fetch_provider"],
            source_type=row["source_type"],
            url=row["url"],
            canonical_url=row["canonical_url"],
            domain=row["domain"],
            title=row["title"],
            snippet=row["snippet"],
            published_at=parse_utc(row["published_at"]) if row["published_at"] else None,
            discovered_at=parse_utc(row["discovered_at"]),
            collected_at=parse_utc(row["collected_at"]) if row["collected_at"] else None,
            fetch_status=fetch_status,
            extraction_status=row["extraction_status"],
            content_hash=row["content_hash"],
            evidence_summary=row["evidence_summary"],
            extracted_fields=json.loads(row["extracted_fields_json"]),
            field_provenance=json.loads(row["field_provenance_json"]),
            crawl_attempts=int(row["crawl_attempts"]),
            eligible_for_crawl=(fetch_status not in ("BLOCKED_POLICY", "BLOCKED_ROBOTS")),
            error_code=row["error_code"],
            error_message=row["error_message"],
        )

    def get_source(self, source_id: UUID | str) -> EventSourceRecord | None:
        row = self.db.fetchone(
            "SELECT * FROM event_sources WHERE source_id = ?", (str(source_id),)
        )
        return self._row_to_source(row) if row else None

    def list_sources(
        self, run_id: UUID | str | None = None, event_id: UUID | str | None = None
    ) -> list[EventSourceRecord]:
        if run_id is not None:
            rows = self.db.fetchall(
                "SELECT * FROM event_sources WHERE discovery_run_id = ? ORDER BY discovered_at ASC",
                (str(run_id),),
            )
        elif event_id is not None:
            rows = self.db.fetchall(
                "SELECT * FROM event_sources WHERE event_id = ? ORDER BY discovered_at ASC",
                (str(event_id),),
            )
        else:
            rows = self.db.fetchall("SELECT * FROM event_sources ORDER BY discovered_at DESC LIMIT 100")
        return [self._row_to_source(r) for r in rows]

    def update_source_crawl_result(
        self,
        *,
        source_id: UUID | str,
        fetch_provider: FetchProvider | None,
        fetch_status: FetchStatus,
        extraction_status: ExtractionStatus,
        collected_at: Any,
        title: str | None = None,
        content_hash: str | None = None,
        evidence_summary: str | None = None,
        extracted_fields: dict[str, Any] | None = None,
        field_provenance: dict[str, Any] | None = None,
        event_id: UUID | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        increment_attempt: bool = True,
    ) -> EventSourceRecord:
        existing = self.get_source(source_id)
        if existing is None:
            raise KeyError(f"Source {source_id} not found")

        attempts = existing.crawl_attempts + (1 if increment_attempt else 0)
        new_title = title if title else existing.title
        new_event_id = str(event_id) if event_id is not None else (str(existing.event_id) if existing.event_id else None)
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE event_sources SET
                    fetch_provider = COALESCE(?, fetch_provider),
                    fetch_status = ?,
                    extraction_status = ?,
                    collected_at = ?,
                    title = ?,
                    content_hash = COALESCE(?, content_hash),
                    evidence_summary = COALESCE(?, evidence_summary),
                    extracted_fields_json = ?,
                    field_provenance_json = ?,
                    event_id = ?,
                    crawl_attempts = ?,
                    error_code = ?,
                    error_message = ?
                WHERE source_id = ?
                """,
                (
                    fetch_provider,
                    fetch_status,
                    extraction_status,
                    utc_iso(collected_at) if collected_at else utc_iso(utc_now()),
                    new_title,
                    content_hash,
                    evidence_summary,
                    json.dumps(extracted_fields if extracted_fields is not None else existing.extracted_fields, default=str),
                    json.dumps(field_provenance if field_provenance is not None else existing.field_provenance, default=str),
                    new_event_id,
                    attempts,
                    error_code,
                    error_message,
                    str(source_id),
                ),
            )
        return self.get_source(source_id)  # type: ignore[return-value]
