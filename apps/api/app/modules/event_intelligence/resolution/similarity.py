from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from apps.api.app.modules.event_intelligence.resolution.venues import are_venues_compatible

NOISE_WORDS = {
    "in", "at", "the", "and", "a", "an", "of", "to", "for", "with",
    "bengaluru", "bangalore", "live", "tickets", "ticket", "book", "now",
    "concert", "fest", "festival", "tour", "2024", "2025", "2026",
    "india", "karnataka", "edition", "night", "day", "annual",
    "booking", "open", "online", "official", "announcement", "presale", "sale",
    "schedule", "dates", "timing", "timings", "details", "pass", "passes",
    "registrations", "register", "pushed", "venue", "city",
}


def clean_event_title(title: str | None) -> tuple[str, set[str]]:
    """Normalize event title by stripping punctuation, dates, noise words, returning clean string and keyword set."""
    if not title:
        return "", set()

    # Convert to lowercase and strip special characters
    lower = title.lower()
    cleaned = re.sub(r"[^\w\s]", " ", lower)
    tokens = [t.strip() for t in cleaned.split() if t.strip()]

    meaningful = [t for t in tokens if t not in NOISE_WORDS and len(t) > 1]
    if not meaningful:
        meaningful = [t for t in tokens if len(t) > 1]
    keyword_set = set(meaningful)
    normalized_str = " ".join(meaningful)

    return normalized_str, keyword_set


def calculate_title_similarity(title_a: str | None, title_b: str | None) -> float:
    """Calculate combined token Jaccard and Levenshtein similarity between two titles (0.0 to 1.0)."""
    norm_a, set_a = clean_event_title(title_a)
    norm_b, set_b = clean_event_title(title_b)

    if not norm_a or not norm_b:
        return 0.0

    if norm_a == norm_b:
        return 1.0

    # Token Jaccard similarity
    union = set_a | set_b
    intersection = set_a & set_b
    jaccard = len(intersection) / len(union) if union else 0.0

    # Token Overlap coefficient (containment)
    min_size = min(len(set_a), len(set_b)) if (set_a and set_b) else 1
    overlap = len(intersection) / min_size if min_size else 0.0

    # Sequence matcher / Levenshtein ratio
    ratio = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()

    # If key distinctive artist/entity token (>= 5 chars) is shared, boost containment
    shared_key_tokens = [t for t in intersection if len(t) >= 4]
    distinctive_bonus = 0.25 if shared_key_tokens else 0.0

    # Blend token Jaccard, overlap containment, and edit ratio
    token_score = max(jaccard, overlap * 0.75 + distinctive_bonus)
    score = min(1.0, (token_score * 0.6) + (ratio * 0.4))
    return round(score, 3)


def check_date_compatibility(
    start_a: datetime | None,
    start_b: datetime | None,
    end_a: datetime | None = None,
    end_b: datetime | None = None,
) -> tuple[bool, float, str]:
    """Check if dates are compatible, returning (compatible, score, reason)."""
    if start_a is None or start_b is None:
        # Date unknown in one source: allow match with neutral score
        return True, 0.5, "One or both start times unspecified"

    # Ensure both are UTC
    if start_a.tzinfo is None:
        start_a = start_a.replace(tzinfo=timezone.utc)
    if start_b.tzinfo is None:
        start_b = start_b.replace(tzinfo=timezone.utc)

    # Exact calendar date match
    if start_a.date() == start_b.date():
        # Check hour difference
        diff_hours = abs((start_a - start_b).total_seconds()) / 3600.0
        if diff_hours <= 1.0:
            return True, 1.0, "Identical date and start time"
        elif diff_hours <= 4.0:
            return True, 0.85, f"Same date with {round(diff_hours, 1)}h time shift"
        else:
            return True, 0.65, f"Same date with significant time discrepancy ({round(diff_hours, 1)}h)"

    # Difference in days
    day_diff = abs((start_a.date() - start_b.date()).days)
    if day_diff == 1:
        # Midnight overlap or multi-day festival
        return True, 0.60, "Adjacent date / multi-day festival overlap"

    # Dates are different by 2+ days
    return False, 0.0, f"Incompatible event dates ({start_a.date()} vs {start_b.date()})"


@dataclass
class MatchScoreResult:
    is_match: bool
    confidence: float
    title_score: float
    venue_score: float
    date_score: float
    reasons: list[str] = field(default_factory=list)
    duplicate_type: str = "DISTINCT"  # EXACT, HIGH_CONFIDENCE, MODERATE_CONFIDENCE, SYNDICATED_REPEAT, DISTINCT


def compute_event_match_score(
    name_a: str | None,
    name_b: str | None,
    venue_a: str | None,
    venue_b: str | None,
    start_a: datetime | None,
    start_b: datetime | None,
    lat_a: float | None = None,
    lon_a: float | None = None,
    lat_b: float | None = None,
    lon_b: float | None = None,
    content_hash_a: str | None = None,
    content_hash_b: str | None = None,
    canonical_url_a: str | None = None,
    canonical_url_b: str | None = None,
) -> MatchScoreResult:
    """Compute holistic multi-factor match score between two event candidate records.
    
    Prevents false merges of different events at the same venue or different dates.
    """
    reasons: list[str] = []

    # 1. Exact URL or content hash check
    if canonical_url_a and canonical_url_b and canonical_url_a.lower() == canonical_url_b.lower():
        return MatchScoreResult(
            is_match=True,
            confidence=1.0,
            title_score=1.0,
            venue_score=1.0,
            date_score=1.0,
            reasons=["Identical canonical source URL"],
            duplicate_type="EXACT",
        )

    if content_hash_a and content_hash_b and content_hash_a == content_hash_b:
        return MatchScoreResult(
            is_match=True,
            confidence=0.98,
            title_score=1.0,
            venue_score=1.0,
            date_score=1.0,
            reasons=["Identical content hash (syndicated repetition)"],
            duplicate_type="SYNDICATED_REPEAT",
        )

    # 2. Title similarity
    title_score = calculate_title_similarity(name_a, name_b)
    if title_score >= 0.85:
        reasons.append(f"High title similarity ({title_score})")
    elif title_score >= 0.50:
        reasons.append(f"Moderate title keyword overlap ({title_score})")
    else:
        reasons.append(f"Low title similarity ({title_score})")

    # Hard barrier: If title similarity is very low, do not merge even if venue and date match!
    # (e.g. Comic Con vs Auto Expo at same venue on same date)
    if title_score < 0.35:
        return MatchScoreResult(
            is_match=False,
            confidence=round(title_score * 0.3, 3),
            title_score=title_score,
            venue_score=0.0,
            date_score=0.0,
            reasons=["Titles are completely different; distinct events at potentially shared venue"],
            duplicate_type="DISTINCT",
        )

    # 3. Date compatibility
    date_compat, date_score, date_reason = check_date_compatibility(start_a, start_b)
    reasons.append(date_reason)

    if not date_compat:
        # Different dates: Do NOT merge
        return MatchScoreResult(
            is_match=False,
            confidence=0.1,
            title_score=title_score,
            venue_score=0.0,
            date_score=0.0,
            reasons=[date_reason, "Dates are incompatible; cannot be same event instance"],
            duplicate_type="DISTINCT",
        )

    # 4. Venue compatibility
    venue_compat, venue_score = are_venues_compatible(
        venue_a, venue_b, lat_a, lon_a, lat_b, lon_b
    )
    if venue_score >= 0.85:
        reasons.append("Matching or canonicalized venue identity")
    elif not venue_compat:
        reasons.append("Geographically incompatible venues")

    if not venue_compat and venue_score == 0.0:
        # Geographically incompatible venues (> 8km apart)
        return MatchScoreResult(
            is_match=False,
            confidence=0.15,
            title_score=title_score,
            venue_score=0.0,
            date_score=date_score,
            reasons=["Venues located in contradictory parts of the city"],
            duplicate_type="DISTINCT",
        )

    # 5. Weighted composite confidence score
    confidence = (title_score * 0.45) + (venue_score * 0.30) + (date_score * 0.25)
    confidence = round(confidence, 3)

    is_match = confidence >= 0.68
    if is_match:
        dup_type = "HIGH_CONFIDENCE" if confidence >= 0.85 else "MODERATE_CONFIDENCE"
    else:
        dup_type = "DISTINCT"

    return MatchScoreResult(
        is_match=is_match,
        confidence=confidence,
        title_score=title_score,
        venue_score=venue_score,
        date_score=date_score,
        reasons=reasons,
        duplicate_type=dup_type,
    )
