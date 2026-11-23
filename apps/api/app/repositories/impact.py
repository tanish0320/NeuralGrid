from __future__ import annotations

import json
from uuid import UUID

from apps.api.app.core.database import Database, parse_utc, utc_iso
from apps.api.app.schemas.impact import EventCellImpactRecord


class ImpactRepository:
    """SQLite persistence for event-to-cell impact assessments."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def save_impacts(self, impacts: list[EventCellImpactRecord]) -> None:
        if not impacts:
            return
        with self.db.transaction() as conn:
            for item in impacts:
                conn.execute(
                    """
                    INSERT INTO event_cell_impacts (
                        impact_id, event_id, cell_id, geographic_distance_km,
                        geographic_relevance_score, coverage_relevance_score,
                        estimated_demand_delta_mbps, impact_confidence,
                        impact_category, impact_window_start, impact_window_end,
                        temporal_profile_json, mapping_method, scoring_model_version,
                        input_evidence_ids_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(event_id, cell_id) DO UPDATE SET
                        geographic_distance_km = excluded.geographic_distance_km,
                        geographic_relevance_score = excluded.geographic_relevance_score,
                        coverage_relevance_score = excluded.coverage_relevance_score,
                        estimated_demand_delta_mbps = excluded.estimated_demand_delta_mbps,
                        impact_confidence = excluded.impact_confidence,
                        impact_category = excluded.impact_category,
                        impact_window_start = excluded.impact_window_start,
                        impact_window_end = excluded.impact_window_end,
                        temporal_profile_json = excluded.temporal_profile_json,
                        mapping_method = excluded.mapping_method,
                        scoring_model_version = excluded.scoring_model_version,
                        input_evidence_ids_json = excluded.input_evidence_ids_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        item.impact_id,
                        str(item.event_id),
                        item.cell_id,
                        item.geographic_distance_km,
                        item.geographic_relevance_score,
                        item.coverage_relevance_score,
                        item.estimated_demand_delta_mbps,
                        item.impact_confidence,
                        item.impact_category,
                        utc_iso(item.impact_window_start),
                        utc_iso(item.impact_window_end),
                        json.dumps(item.temporal_profile),
                        item.mapping_method,
                        item.scoring_model_version,
                        json.dumps(item.input_evidence_ids),
                        utc_iso(item.created_at),
                        utc_iso(item.updated_at),
                    ),
                )

    def delete_impacts_for_event(self, event_id: UUID | str) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM event_cell_impacts WHERE event_id = ?",
                (str(event_id),),
            )
            return cursor.rowcount

    def delete_all_impacts(self) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM event_cell_impacts")
            return cursor.rowcount

    def _row_to_impact(self, row: object) -> EventCellImpactRecord:
        return EventCellImpactRecord(
            impact_id=row["impact_id"],
            event_id=UUID(row["event_id"]),
            cell_id=row["cell_id"],
            geographic_distance_km=float(row["geographic_distance_km"]),
            geographic_relevance_score=float(row["geographic_relevance_score"]),
            coverage_relevance_score=float(row["coverage_relevance_score"]),
            estimated_demand_delta_mbps=float(row["estimated_demand_delta_mbps"]),
            impact_confidence=float(row["impact_confidence"]),
            impact_category=row["impact_category"],
            impact_window_start=parse_utc(row["impact_window_start"]),
            impact_window_end=parse_utc(row["impact_window_end"]),
            temporal_profile=json.loads(row["temporal_profile_json"] or "{}"),
            mapping_method=row["mapping_method"],
            scoring_model_version=row["scoring_model_version"],
            input_evidence_ids=json.loads(row["input_evidence_ids_json"] or "[]"),
            created_at=parse_utc(row["created_at"]),
            updated_at=parse_utc(row["updated_at"]),
        )

    def get_impacts_for_event(self, event_id: UUID | str) -> list[EventCellImpactRecord]:
        rows = self.db.fetchall(
            """
            SELECT * FROM event_cell_impacts
            WHERE event_id = ?
            ORDER BY geographic_distance_km ASC, cell_id ASC
            """,
            (str(event_id),),
        )
        return [self._row_to_impact(r) for r in rows]

    def get_impacts_for_cell(self, cell_id: str) -> list[EventCellImpactRecord]:
        rows = self.db.fetchall(
            """
            SELECT * FROM event_cell_impacts
            WHERE cell_id = ?
            ORDER BY estimated_demand_delta_mbps DESC
            """,
            (cell_id,),
        )
        return [self._row_to_impact(r) for r in rows]

    def list_all_impacts(self) -> list[EventCellImpactRecord]:
        rows = self.db.fetchall(
            "SELECT * FROM event_cell_impacts ORDER BY created_at DESC"
        )
        return [self._row_to_impact(r) for r in rows]

    def list_distinct_affected_cells(self) -> list[str]:
        rows = self.db.fetchall(
            "SELECT DISTINCT cell_id FROM event_cell_impacts ORDER BY cell_id ASC"
        )
        return [r["cell_id"] for r in rows]

    def get_overlapping_cells(self) -> list[tuple[str, int]]:
        """Return cell_ids that have > 1 contributing event."""
        rows = self.db.fetchall(
            """
            SELECT cell_id, COUNT(event_id) as event_count
            FROM event_cell_impacts
            GROUP BY cell_id
            HAVING COUNT(event_id) > 1
            ORDER BY event_count DESC, cell_id ASC
            """
        )
        return [(r["cell_id"], int(r["event_count"])) for r in rows]

    def get_stats(self) -> dict[str, float | int]:
        row = self.db.fetchone(
            """
            SELECT
                COUNT(*) as total_records,
                COUNT(DISTINCT event_id) as mapped_events,
                COUNT(DISTINCT cell_id) as affected_cells,
                COALESCE(MAX(estimated_demand_delta_mbps), 0.0) as max_demand_delta,
                COALESCE(AVG(estimated_demand_delta_mbps), 0.0) as avg_demand_delta
            FROM event_cell_impacts
            """
        )
        if not row:
            return {
                "total_records": 0,
                "mapped_events": 0,
                "affected_cells": 0,
                "max_demand_delta": 0.0,
                "avg_demand_delta": 0.0,
            }
        return {
            "total_records": int(row["total_records"]),
            "mapped_events": int(row["mapped_events"]),
            "affected_cells": int(row["affected_cells"]),
            "max_demand_delta": round(float(row["max_demand_delta"]), 2),
            "avg_demand_delta": round(float(row["avg_demand_delta"]), 2),
        }
