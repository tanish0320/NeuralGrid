from __future__ import annotations

import json
import uuid
from typing import Any

from apps.api.app.core.database import Database, utc_iso, utc_now


class AuditLogger:
    """Persists immutable UTC audit trail entries for provenance (FR-014)."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def log(
        self,
        *,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str,
        state_version: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> str:
        audit_id = str(uuid.uuid4())
        ts = utc_iso(utc_now())
        payload = json.dumps(details or {}, default=str)
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO audit_events (id, timestamp, actor, action, entity_type, entity_id, state_version, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (audit_id, ts, actor, action, entity_type, entity_id, state_version, payload),
            )
        return audit_id
