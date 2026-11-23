from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from apps.api.app.core.database import utc_now
from apps.api.app.modules.event_intelligence.resolution.venues import normalize_venue_name
from apps.api.app.schemas.events import EventRecord

logger = logging.getLogger("neuralgrid.eventsense.reconciler")

SOURCE_RELIABILITY_WEIGHTS: dict[str, float] = {
    "TICKETING": 0.95,
    "BookMyShowConnector": 0.95,
    "DistrictConnector": 0.92,
    "AllEventsConnector": 0.88,
    "NEWS": 0.85,
    "RSSNewsConnector": 0.85,
    "GDELTConnector": 0.80,
    "Crawl4AIConnector": 0.82,
    "PUBLIC_SCRAPER": 0.80,
    "RedditConnector": 0.70,
    "TwitterXConnector": 0.65,
    "InstagramConnector": 0.65,
    "YouTubeConnector": 0.65,
    "TelegramConnector": 0.60,
}


def get_source_reliability(source_type_or_connector: str | None) -> float:
    """Return numeric reliability multiplier for a source."""
    if not source_type_or_connector:
        return 0.75
    for key, weight in SOURCE_RELIABILITY_WEIGHTS.items():
        if key.lower() in source_type_or_connector.lower():
            return weight
    return 0.75


class EventFieldReconciler:
    """Field-level event reconciliation with source reliability weighting, conflict detection,
    and granular provenance tracking."""

    @staticmethod
    def reconcile_fields(
        existing_event: EventRecord,
        incoming_fields: dict[str, Any],
        incoming_source_id: str,
        incoming_source_platform: str,
        incoming_confidence: float = 0.8,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        """Reconcile existing canonical event fields with newly extracted fields from an incoming source.
        
        Returns:
            - reconciled_fields: dict of updated field values
            - new_conflicts: list of newly detected conflict objects
            - updated_provenance: updated field_provenance dictionary
        """
        reconciled = {
            "name": existing_event.name,
            "event_type": existing_event.event_type,
            "venue_name": existing_event.venue_name,
            "city": existing_event.city,
            "address": existing_event.address,
            "latitude": existing_event.latitude,
            "longitude": existing_event.longitude,
            "start_at": existing_event.start_at,
            "end_at": existing_event.end_at,
            "attendance_low": existing_event.attendance_low,
            "attendance_high": existing_event.attendance_high,
            "attendance_basis": existing_event.attendance_basis,
            "status": existing_event.status,
        }

        provenance = dict(existing_event.field_provenance or {})
        field_attr = dict(provenance.get("field_attribution") or {})
        existing_conflicts = list(provenance.get("conflicts") or [])
        new_conflicts: list[dict[str, Any]] = []

        inc_rel = get_source_reliability(incoming_source_platform)
        inc_score = round(inc_rel * incoming_confidence, 3)
        now = utc_now()

        # 1. Event Name / Title
        inc_name = incoming_fields.get("name") or incoming_fields.get("event_name") or incoming_fields.get("title")
        if inc_name and inc_name.strip():
            inc_name = inc_name.strip()
            curr_score = field_attr.get("name", {}).get("score", 0.7)
            if inc_score > curr_score:
                # If incoming source has strictly higher authority (e.g. ticketing vs social snippet), prefer clean title
                reconciled["name"] = inc_name
                field_attr["name"] = {
                    "source": incoming_source_id,
                    "platform": incoming_source_platform,
                    "score": inc_score,
                    "basis": "CONFIRMED" if inc_rel >= 0.85 else "INFERRED",
                    "updated_at": now.isoformat(),
                }

        # 2. Venue & Coordinates
        inc_venue = incoming_fields.get("venue_name") or incoming_fields.get("venue")
        inc_lat = incoming_fields.get("latitude")
        inc_lon = incoming_fields.get("longitude")

        if inc_venue and str(inc_venue).strip():
            inc_venue_str = str(inc_venue).strip()
            canon_venue, canon_lat, canon_lon = normalize_venue_name(inc_venue_str)
            eff_venue = canon_venue or inc_venue_str

            curr_venue = existing_event.venue_name
            if curr_venue and curr_venue.lower() != eff_venue.lower():
                # Flag venue discrepancy
                conflict_entry = {
                    "field": "venue_name",
                    "preferred": curr_venue,
                    "conflicting": eff_venue,
                    "preferred_source": field_attr.get("venue_name", {}).get("source", "existing"),
                    "conflicting_source": incoming_source_id,
                    "severity": "WARNING",
                    "detected_at": now.isoformat(),
                }
                new_conflicts.append(conflict_entry)
                existing_conflicts.append(conflict_entry)

            curr_v_score = field_attr.get("venue_name", {}).get("score", 0.0)
            if not curr_venue or inc_score > curr_v_score:
                reconciled["venue_name"] = eff_venue
                field_attr["venue_name"] = {
                    "source": incoming_source_id,
                    "platform": incoming_source_platform,
                    "score": inc_score,
                    "basis": "CONFIRMED" if canon_venue else "INFERRED",
                    "updated_at": now.isoformat(),
                }

            # Coordinates: Prefer canonical geocoded coordinates, otherwise explicit source coordinates
            best_lat = canon_lat or inc_lat
            best_lon = canon_lon or inc_lon
            if best_lat is not None and best_lon is not None:
                reconciled["latitude"] = float(best_lat)
                reconciled["longitude"] = float(best_lon)
                field_attr["coordinates"] = {
                    "source": "bengaluru_venue_registry" if canon_lat else incoming_source_id,
                    "basis": "CONFIRMED",
                    "updated_at": now.isoformat(),
                }

        # 3. Start Date & End Date
        inc_start = incoming_fields.get("start_at")
        inc_end = incoming_fields.get("end_at")

        if inc_start is not None:
            if isinstance(inc_start, str):
                try:
                    inc_start = datetime.fromisoformat(inc_start.replace("Z", "+00:00"))
                except Exception:
                    inc_start = None

        if inc_end is not None:
            if isinstance(inc_end, str):
                try:
                    inc_end = datetime.fromisoformat(inc_end.replace("Z", "+00:00"))
                except Exception:
                    inc_end = None

        if inc_start is not None:
            if inc_start.tzinfo is None:
                inc_start = inc_start.replace(tzinfo=timezone.utc)

            curr_start = existing_event.start_at
            if curr_start is not None:
                if curr_start.tzinfo is None:
                    curr_start = curr_start.replace(tzinfo=timezone.utc)

                diff_seconds = abs((curr_start - inc_start).total_seconds())
                if diff_seconds > 1800:  # > 30 minutes difference
                    conflict_entry = {
                        "field": "start_at",
                        "preferred": curr_start.isoformat(),
                        "conflicting": inc_start.isoformat(),
                        "preferred_source": field_attr.get("start_at", {}).get("source", "existing"),
                        "conflicting_source": incoming_source_id,
                        "time_discrepancy_minutes": round(diff_seconds / 60.0, 1),
                        "severity": "CRITICAL" if diff_seconds > 7200 else "WARNING",
                        "detected_at": now.isoformat(),
                    }
                    new_conflicts.append(conflict_entry)
                    existing_conflicts.append(conflict_entry)

            curr_date_score = field_attr.get("start_at", {}).get("score", 0.0)
            if not curr_start or inc_score > curr_date_score:
                reconciled["start_at"] = inc_start
                if inc_end:
                    reconciled["end_at"] = inc_end
                field_attr["start_at"] = {
                    "source": incoming_source_id,
                    "platform": incoming_source_platform,
                    "score": inc_score,
                    "basis": "CONFIRMED",
                    "updated_at": now.isoformat(),
                }

        # 4. Attendance
        inc_att_low = incoming_fields.get("attendance_low")
        inc_att_high = incoming_fields.get("attendance_high")
        inc_att_basis = incoming_fields.get("attendance_basis")

        if inc_att_high is not None or inc_att_low is not None:
            # Source explicitly reports attendance: always prefer over unstated/default
            curr_att_score = field_attr.get("attendance", {}).get("score", 0.0)
            if inc_score > curr_att_score or existing_event.attendance_basis != "SOURCE_EVIDENCE":
                reconciled["attendance_low"] = int(inc_att_low) if inc_att_low else None
                reconciled["attendance_high"] = int(inc_att_high) if inc_att_high else None
                reconciled["attendance_basis"] = "SOURCE_EVIDENCE"
                field_attr["attendance"] = {
                    "source": incoming_source_id,
                    "platform": incoming_source_platform,
                    "score": inc_score,
                    "basis": "SOURCE_EVIDENCE",
                    "updated_at": now.isoformat(),
                }

        # 5. Cancellation / Postponement keywords
        text_context = (str(incoming_fields.get("raw_text") or "") + " " + str(incoming_fields.get("title") or "")).lower()
        if any(term in text_context for term in ["cancelled", "called off", "canceled", "scrapped"]):
            reconciled["status"] = "CANCELLED"
            field_attr["status"] = {
                "source": incoming_source_id,
                "reason": "Cancellation detected in incoming source text",
                "updated_at": now.isoformat(),
            }
        elif any(term in text_context for term in ["postponed", "rescheduled", "deferred", "pushed to"]):
            reconciled["status"] = "POSTPONED"
            field_attr["status"] = {
                "source": incoming_source_id,
                "reason": "Postponement detected in incoming source text",
                "updated_at": now.isoformat(),
            }

        # Pack provenance
        provenance["field_attribution"] = field_attr
        provenance["conflicts"] = existing_conflicts

        return reconciled, new_conflicts, provenance
