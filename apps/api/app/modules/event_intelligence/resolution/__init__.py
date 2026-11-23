from __future__ import annotations

from apps.api.app.modules.event_intelligence.resolution.field_reconciler import (
    EventFieldReconciler,
    get_source_reliability,
)
from apps.api.app.modules.event_intelligence.resolution.lifecycle import EventLifecycleManager
from apps.api.app.modules.event_intelligence.resolution.resolver import CanonicalEventResolver
from apps.api.app.modules.event_intelligence.resolution.similarity import (
    MatchScoreResult,
    calculate_title_similarity,
    check_date_compatibility,
    clean_event_title,
    compute_event_match_score,
)
from apps.api.app.modules.event_intelligence.resolution.venues import (
    BENGALURU_VENUES,
    are_venues_compatible,
    haversine_km,
    normalize_venue_name,
)

__all__ = [
    "CanonicalEventResolver",
    "EventFieldReconciler",
    "EventLifecycleManager",
    "MatchScoreResult",
    "calculate_title_similarity",
    "check_date_compatibility",
    "clean_event_title",
    "compute_event_match_score",
    "normalize_venue_name",
    "are_venues_compatible",
    "haversine_km",
    "get_source_reliability",
    "BENGALURU_VENUES",
]
