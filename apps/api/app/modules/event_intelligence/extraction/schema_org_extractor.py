from __future__ import annotations

import json
import logging
import re
from typing import Any
from bs4 import BeautifulSoup

logger = logging.getLogger("neuralgrid.eventsense.extractor.schema_org")

EVENT_TYPES = {
    "event",
    "musicevent",
    "festivalevent",
    "festival",
    "sportsevent",
    "socialevent",
    "businessevent",
    "exhibitionevent",
    "theaterevent",
    "danceevent",
    "saleevent",
}


def _extract_text_field(val: Any) -> str | None:
    if isinstance(val, str):
        cleaned = val.strip()
        return cleaned if cleaned else None
    if isinstance(val, dict):
        return _extract_text_field(val.get("name") or val.get("text"))
    return None


def _find_event_object(data: Any) -> dict[str, Any] | None:
    """Recursively search for a Schema.org Event dict in JSON-LD structure."""
    if isinstance(data, list):
        for item in data:
            found = _find_event_object(item)
            if found:
                return found
    elif isinstance(data, dict):
        raw_type = data.get("@type")
        if raw_type:
            types = [raw_type] if isinstance(raw_type, str) else raw_type
            for t in types:
                if str(t).lower() in EVENT_TYPES:
                    return data
        if "@graph" in data:
            return _find_event_object(data["@graph"])
    return None


def extract_schema_org_event(html: str | None) -> tuple[dict[str, Any], dict[str, Any], str] | None:
    """Extract Schema.org Event metadata from HTML.
    
    Returns (fields, field_provenance, evidence_summary) or None if no Event JSON-LD found.
    """
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            if not script.string:
                continue
            try:
                parsed = json.loads(script.string.strip())
            except Exception:
                continue

            event_data = _find_event_object(parsed)
            if not event_data:
                continue

            fields: dict[str, Any] = {}
            provenance: dict[str, Any] = {}
            evidence_parts: list[str] = []

            # Name
            name = _extract_text_field(event_data.get("name"))
            if name:
                fields["event_name"] = name
                provenance["event_name"] = "schema_org.name"
                evidence_parts.append(f"Name: {name}")

            # Description
            desc = _extract_text_field(event_data.get("description"))
            if desc:
                fields["description"] = desc[:1500]
                provenance["description"] = "schema_org.description"

            # Start and End Dates
            start_date = _extract_text_field(event_data.get("startDate"))
            if start_date:
                fields["start_at"] = start_date
                provenance["start_at"] = "schema_org.startDate"
                evidence_parts.append(f"Start: {start_date}")

            end_date = _extract_text_field(event_data.get("endDate"))
            if end_date:
                fields["end_at"] = end_date
                provenance["end_at"] = "schema_org.endDate"
                evidence_parts.append(f"End: {end_date}")

            # Location / Venue
            loc = event_data.get("location")
            if isinstance(loc, dict):
                venue = _extract_text_field(loc.get("name"))
                if venue:
                    fields["venue_name"] = venue
                    provenance["venue_name"] = "schema_org.location.name"
                    evidence_parts.append(f"Venue: {venue}")

                addr = loc.get("address")
                if isinstance(addr, dict):
                    street = addr.get("streetAddress")
                    locality = addr.get("addressLocality")
                    region = addr.get("addressRegion")
                    parts = [str(p).strip() for p in (street, locality, region) if p]
                    if parts:
                        fields["address"] = ", ".join(parts)
                        provenance["address"] = "schema_org.location.address"
                    if locality:
                        fields["city"] = str(locality).strip()
                        provenance["city"] = "schema_org.location.address.addressLocality"
                elif isinstance(addr, str) and addr.strip():
                    fields["address"] = addr.strip()
                    provenance["address"] = "schema_org.location.address"

                # Geo coordinates
                geo = loc.get("geo")
                if isinstance(geo, dict):
                    lat = geo.get("latitude")
                    lon = geo.get("longitude")
                    if lat is not None and lon is not None:
                        try:
                            fields["latitude"] = float(lat)
                            fields["longitude"] = float(lon)
                            provenance["latitude"] = "schema_org.location.geo.latitude"
                            provenance["longitude"] = "schema_org.location.geo.longitude"
                        except (ValueError, TypeError):
                            pass

            elif isinstance(loc, str) and loc.strip():
                fields["venue_name"] = loc.strip()
                provenance["venue_name"] = "schema_org.location"
                evidence_parts.append(f"Venue: {loc.strip()}")

            # Capacity / Attendance (only if explicit Schema.org property present)
            capacity = event_data.get("maximumAttendeeCapacity")
            if capacity is not None:
                try:
                    cap_int = int(capacity)
                    if cap_int > 0:
                        fields["attendance_high"] = cap_int
                        fields["attendance_low"] = int(cap_int * 0.7)
                        provenance["attendance_high"] = "schema_org.maximumAttendeeCapacity"
                        provenance["attendance_low"] = "derived:schema_org.maximumAttendeeCapacity*0.7"
                except (ValueError, TypeError):
                    pass

            if fields.get("event_name"):
                evidence_summary = (
                    f"Schema.org Event JSON-LD found. " + "; ".join(evidence_parts)
                )[:1900]
                return fields, provenance, evidence_summary

    except Exception as exc:
        logger.debug("Failed parsing Schema.org from HTML: %s", exc)

    return None
