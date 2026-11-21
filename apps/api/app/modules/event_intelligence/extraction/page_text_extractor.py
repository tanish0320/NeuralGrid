from __future__ import annotations

import re
from typing import Any
from bs4 import BeautifulSoup


def extract_page_text_fallback(
    title: str | None,
    markdown_text: str | None,
    html: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Fallback text and heading extractor for un-structured web pages.
    
    Leaves date, venue, coordinates, and attendance as None unless unambiguous.
    Never invents attendance or coordinates.
    """
    fields: dict[str, Any] = {}
    provenance: dict[str, Any] = {}
    evidence_parts: list[str] = []

    # 1. Event Name from H1 or Title
    event_name: str | None = None
    if markdown_text:
        h1_match = re.search(r"^#\s+(.+)$", markdown_text, re.MULTILINE)
        if h1_match:
            candidate = h1_match.group(1).strip()
            if len(candidate) >= 3 and len(candidate) <= 240:
                event_name = candidate
                provenance["event_name"] = "markdown_h1"

    if not event_name and title:
        # Clean generic site suffixes like ' - BookMyShow' or ' | Eventbrite'
        cleaned_title = re.split(r"\s+[-|—]\s+", title)[0].strip()
        if len(cleaned_title) >= 3:
            event_name = cleaned_title
            provenance["event_name"] = "page_title"

    if event_name:
        fields["event_name"] = event_name
        evidence_parts.append(f"Name from title/header: {event_name}")

    # 2. Known Bengaluru venue pattern detection
    KNOWN_VENUES = [
        ("Palace Grounds", "Palace Grounds", 13.0067, 77.5855),
        ("Chinnaswamy Stadium", "M. Chinnaswamy Stadium", 12.9788, 77.5996),
        ("Kanteerava Stadium", "Sri Kanteerava Outdoor Stadium", 12.9698, 77.5926),
        ("Manpho Convention Centre", "Manpho Convention Centre", 13.0450, 77.6160),
        ("BIEC", "Bengaluru International Exhibition Centre", 13.0610, 77.4760),
        ("Phoenix Marketcity", "Phoenix Marketcity Whitefield", 12.9958, 77.6964),
    ]

    full_text = f"{title or ''}\n{markdown_text or ''}"
    for venue_key, venue_official, vlat, vlon in KNOWN_VENUES:
        if re.search(rf"\b{re.escape(venue_key)}\b", full_text, re.IGNORECASE):
            fields["venue_name"] = venue_official
            fields["latitude"] = vlat
            fields["longitude"] = vlon
            fields["city"] = "Bengaluru"
            provenance["venue_name"] = f"text_pattern:{venue_key}"
            provenance["latitude"] = f"venue_lookup:{venue_key}"
            provenance["longitude"] = f"venue_lookup:{venue_key}"
            evidence_parts.append(f"Known venue detected: {venue_official}")
            break

    evidence_summary = (
        "Text fallback extraction. " + "; ".join(evidence_parts) if evidence_parts else "No clear event structure found in page text."
    )[:1900]

    return fields, provenance, evidence_summary
