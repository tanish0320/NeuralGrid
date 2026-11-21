from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from apps.api.app.schemas.events import ExtractionStatus

logger = logging.getLogger("neuralgrid.eventsense.normalizer")


def parse_datetime_to_utc(val: Any) -> datetime | None:
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)
    if isinstance(val, str):
        val_clean = val.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(val_clean)
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except Exception:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
                try:
                    dt = datetime.strptime(val.strip(), fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
    return None


def determine_extraction_status(fields: dict[str, Any]) -> ExtractionStatus:
    if not fields or not (fields.get("event_name") or fields.get("name")):
        return "NO_EVENT_FIELDS"
    
    has_venue = bool(fields.get("venue_name") or fields.get("venue"))
    has_date = bool(fields.get("start_at"))
    has_geo = fields.get("latitude") is not None and fields.get("longitude") is not None

    if (has_venue or has_geo) and has_date:
        return "SUCCEEDED"
    return "PARTIAL"
