from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from apps.api.app.core.database import Database, parse_utc, utc_iso, utc_now
from apps.api.app.schemas.events import (
    AffectedCellImpact,
    EventImpactResponse,
    EventRecord,
)

PALACE_GROUNDS_EVENT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "neuralgrid.palace-grounds-demo")


class EventRepository:
    """SQLite persistence for normalised events and operator-confirmed impacts."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def _row_to_event(self, row: Any) -> EventRecord:
        return EventRecord(
            event_id=UUID(row["event_id"]),
            event_key=row["event_key"],
            event_origin=row["event_origin"],
            name=row["name"],
            event_type=row["event_type"],
            venue_name=row["venue_name"],
            city=row["city"],
            address=row["address"],
            latitude=float(row["latitude"]) if row["latitude"] is not None else None,
            longitude=float(row["longitude"]) if row["longitude"] is not None else None,
            start_at=parse_utc(row["start_at"]) if row["start_at"] else None,
            end_at=parse_utc(row["end_at"]) if row["end_at"] else None,
            attendance_low=int(row["attendance_low"]) if row["attendance_low"] is not None else None,
            attendance_high=int(row["attendance_high"]) if row["attendance_high"] is not None else None,
            attendance_basis=row["attendance_basis"],
            intensity=float(row["intensity"]),
            verification_status=row["verification_status"],
            status=row["status"],
            source_ids=[UUID(sid) for sid in json.loads(row["source_ids_json"])],
            field_provenance=json.loads(row["field_provenance_json"]),
            confirmed_by=row["confirmed_by"],
            confirmed_at=parse_utc(row["confirmed_at"]) if row["confirmed_at"] else None,
            confirmation_notes=row["confirmation_notes"],
            created_at=parse_utc(row["created_at"]),
            updated_at=parse_utc(row["updated_at"]),
        )

    def create_event(self, event: EventRecord) -> EventRecord:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO events (
                    event_id, event_key, event_origin, name, event_type, venue_name, city,
                    address, latitude, longitude, start_at, end_at, attendance_low,
                    attendance_high, attendance_basis, intensity, verification_status,
                    status, source_ids_json, field_provenance_json, confirmed_by,
                    confirmed_at, confirmation_notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.event_id),
                    event.event_key,
                    event.event_origin,
                    event.name,
                    event.event_type,
                    event.venue_name,
                    event.city,
                    event.address,
                    event.latitude,
                    event.longitude,
                    utc_iso(event.start_at) if event.start_at else None,
                    utc_iso(event.end_at) if event.end_at else None,
                    event.attendance_low,
                    event.attendance_high,
                    event.attendance_basis,
                    event.intensity,
                    event.verification_status,
                    event.status,
                    json.dumps([str(s) for s in event.source_ids]),
                    json.dumps(event.field_provenance, default=str),
                    event.confirmed_by,
                    utc_iso(event.confirmed_at) if event.confirmed_at else None,
                    event.confirmation_notes,
                    utc_iso(event.created_at),
                    utc_iso(event.updated_at),
                ),
            )
        return self.get_event(event.event_id)  # type: ignore[return-value]

    def update_event(self, event: EventRecord) -> EventRecord:
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE events SET
                    event_key = ?, event_origin = ?, name = ?, event_type = ?,
                    venue_name = ?, city = ?, address = ?, latitude = ?, longitude = ?,
                    start_at = ?, end_at = ?, attendance_low = ?, attendance_high = ?,
                    attendance_basis = ?, intensity = ?, verification_status = ?,
                    status = ?, source_ids_json = ?, field_provenance_json = ?,
                    confirmed_by = ?, confirmed_at = ?, confirmation_notes = ?, updated_at = ?
                WHERE event_id = ?
                """,
                (
                    event.event_key,
                    event.event_origin,
                    event.name,
                    event.event_type,
                    event.venue_name,
                    event.city,
                    event.address,
                    event.latitude,
                    event.longitude,
                    utc_iso(event.start_at) if event.start_at else None,
                    utc_iso(event.end_at) if event.end_at else None,
                    event.attendance_low,
                    event.attendance_high,
                    event.attendance_basis,
                    event.intensity,
                    event.verification_status,
                    event.status,
                    json.dumps([str(s) for s in event.source_ids]),
                    json.dumps(event.field_provenance, default=str),
                    event.confirmed_by,
                    utc_iso(event.confirmed_at) if event.confirmed_at else None,
                    event.confirmation_notes,
                    utc_iso(utc_now()),
                    str(event.event_id),
                ),
            )
        return self.get_event(event.event_id)  # type: ignore[return-value]

    def get_event(self, event_id: UUID | str) -> EventRecord | None:
        row = self.db.fetchone("SELECT * FROM events WHERE event_id = ?", (str(event_id),))
        return self._row_to_event(row) if row else None

    def get_event_by_key(self, event_key: str) -> EventRecord | None:
        row = self.db.fetchone("SELECT * FROM events WHERE event_key = ?", (event_key,))
        return self._row_to_event(row) if row else None

    def list_events(self) -> list[EventRecord]:
        rows = self.db.fetchall("SELECT * FROM events ORDER BY created_at DESC")
        return [self._row_to_event(r) for r in rows]

    def ensure_seeded_demo_event(self, event_key: str = "palace-grounds-demo") -> EventRecord:
        existing = self.get_event_by_key(event_key)
        if existing is not None:
            return existing

        now = utc_now()
        start = datetime(now.year, now.month, now.day, 13, 30, tzinfo=timezone.utc) + timedelta(days=1)
        end = start + timedelta(hours=4)
        seeded = EventRecord(
            event_id=PALACE_GROUNDS_EVENT_ID,
            event_key=event_key,
            event_origin="SEEDED_DEMO",
            name="Palace Grounds Concert — DEMO SCENARIO",
            event_type="concert",
            venue_name="Palace Grounds",
            city="Bengaluru",
            address="Jayamahal Main Rd, Bengaluru (Synthetic Demo Placement)",
            latitude=12.9988,
            longitude=77.5921,
            start_at=start,
            end_at=end,
            attendance_low=18000,
            attendance_high=26000,
            attendance_basis="OPERATOR_ASSUMPTION",
            intensity=1.4,
            verification_status="DEMO_SCENARIO",
            status="CANDIDATE",
            source_ids=[],
            field_provenance={
                "venue_name": {"origin": "SEEDED_DEMO", "note": "Preconfigured offline scenario"},
                "attendance": {
                    "origin": "SEEDED_DEMO",
                    "note": "Synthetic attendance interval (18,000-26,000) requiring explicit operator acceptance",
                },
            },
            confirmed_by=None,
            confirmed_at=None,
            confirmation_notes=None,
            created_at=now,
            updated_at=now,
        )
        return self.create_event(seeded)

    def save_impact(self, impact: EventImpactResponse) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO event_impacts (
                    event_id, simulation_id, influence_radius_km, attendance_scenario,
                    affected_cells_json, assumptions_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(impact.event_id),
                    str(impact.simulation_id),
                    impact.influence_radius_km,
                    impact.attendance_scenario,
                    json.dumps([c.model_dump(mode="json") for c in impact.affected_cells]),
                    json.dumps(impact.assumptions, default=str),
                    utc_iso(impact.created_at),
                ),
            )

    def get_impact(self, event_id: UUID | str, simulation_id: UUID | str) -> EventImpactResponse | None:
        row = self.db.fetchone(
            "SELECT * FROM event_impacts WHERE event_id = ? AND simulation_id = ?",
            (str(event_id), str(simulation_id)),
        )
        if not row:
            return None
        affected = [AffectedCellImpact(**item) for item in json.loads(row["affected_cells_json"])]
        return EventImpactResponse(
            event_id=UUID(row["event_id"]),
            simulation_id=UUID(row["simulation_id"]),
            influence_radius_km=float(row["influence_radius_km"]),
            attendance_scenario=row["attendance_scenario"],
            affected_cells=affected,
            total_estimated_uplift_mbps=round(
                sum(c.estimated_additional_demand_mbps for c in affected), 3
            ),
            assumptions=json.loads(row["assumptions_json"]),
            created_at=parse_utc(row["created_at"]),
        )
