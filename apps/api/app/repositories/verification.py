from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from apps.api.app.core.database import Database, parse_utc, utc_iso
from apps.api.app.schemas.verification import AuditEventRecord, VerificationResultResponse


class VerificationRepository:
    """SQLite persistence for counterfactual verification runs and audit queries."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def save_verification(self, record: VerificationResultResponse) -> VerificationResultResponse:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO verification_runs (
                    id, baseline_run_id, intervention_run_id, plan_id, event_id,
                    seed, metrics_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record.verification_id),
                    record.baseline_run_id,
                    record.intervention_run_id,
                    str(record.plan_id),
                    str(record.event_id) if record.event_id else None,
                    record.seed,
                    record.model_dump_json(),
                    utc_iso(record.created_at),
                ),
            )
        return record

    def get_verification(self, verification_id: UUID | str) -> VerificationResultResponse | None:
        row = self.db.fetchone(
            "SELECT * FROM verification_runs WHERE id = ?", (str(verification_id),)
        )
        if not row:
            return None
        return VerificationResultResponse(**json.loads(row["metrics_json"]))

    def list_verifications(self, plan_id: UUID | str | None = None) -> list[VerificationResultResponse]:
        if plan_id:
            rows = self.db.fetchall(
                "SELECT * FROM verification_runs WHERE plan_id = ? ORDER BY created_at DESC",
                (str(plan_id),),
            )
        else:
            rows = self.db.fetchall(
                "SELECT * FROM verification_runs ORDER BY created_at DESC LIMIT 50"
            )
        return [VerificationResultResponse(**json.loads(r["metrics_json"])) for r in rows]

    def list_audit_events(
        self, entity_id: str | None = None, limit: int = 200
    ) -> list[AuditEventRecord]:
        if entity_id:
            rows = self.db.fetchall(
                "SELECT * FROM audit_events WHERE entity_id = ? ORDER BY timestamp DESC LIMIT ?",
                (entity_id, limit),
            )
        else:
            rows = self.db.fetchall(
                "SELECT * FROM audit_events ORDER BY timestamp DESC LIMIT ?", (limit,)
            )
        return [
            AuditEventRecord(
                id=UUID(r["id"]),
                timestamp=parse_utc(r["timestamp"]),
                actor=r["actor"],
                action=r["action"],
                entity_type=r["entity_type"],
                entity_id=r["entity_id"],
                state_version=int(r["state_version"]) if r["state_version"] is not None else None,
                details=json.loads(r["details_json"]),
            )
            for r in rows
        ]
