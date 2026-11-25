from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.api.app.schemas.events import EventRecord

# Hard-exclusion patterns for non-crowd crime, accident, legal, and fluff articles.
# NOTE: Do NOT block bare "police" so traffic/crowd advisories for rallies or concerts pass.
_TITLE_EXCLUSION_PATTERNS: list[tuple[str, str]] = [
    ("murder", r"\bmurder(?:ed|s)?\b"),
    ("killed", r"\bkilled\b"),
    ("beaten_to_death", r"\bbeats?\b.{0,30}\bto death\b"),
    ("stabbed", r"\bstabbed\b"),
    ("arrest", r"\barrest(?:ed|s)?\b"),
    ("police_booked", r"\bpolice book(?:ed|s)?\b"),
    ("booked", r"\bbooked\b"),
    ("fir", r"\bfir\b"),
    ("scam", r"\bscam(?:s|med)?\b"),
    ("fraud", r"\bfraud(?:s|ulent)?\b"),
    ("theft", r"\btheft(?:s)?\b"),
    ("steal", r"\bsteal(?:s|ing)?\b"),
    ("stolen", r"\bstolen\b"),
    ("robbery", r"\brobber(?:y|ies)\b"),
    ("burglary", r"\bburglar(?:y|ies)\b"),
    ("lures", r"\blures?\b"),
    ("rape", r"\brape(?:d)?\b"),
    ("sexual_assault", r"\bsexual assault\b"),
    ("suicide", r"\bsuicide\b"),
    ("fatal", r"\bfatal\b"),
    ("matrimonial", r"\bmatrimonial\b"),
    ("accused", r"\baccused\b"),
    ("custody", r"\bcustody\b"),
    ("bail", r"\bbail\b"),
    ("bomb_threat", r"\bbomb threat\b"),
    ("hoax", r"\bhoax\b"),
    ("snatching", r"\bsnatching\b"),
    ("cheating", r"\bcheating\b"),
    ("dead_body", r"\bdead body\b"),
    ("corpse", r"\bcorpse\b"),
    ("hit_and_run", r"\bhit-and-run\b"),
    ("rash_driving", r"\brash driving\b"),
    ("sari_boutique", r"\bsari boutique\b"),
    ("boutique", r"\bboutique\b"),
    ("pays_homage", r"\bpays? homage\b"),
    ("obituary", r"\bobituary\b"),
    ("fake_bills", r"\bfake bills\b"),
    ("forged_entries", r"\bforged entries\b"),
    ("autorickshaw_driver", r"\bautorickshaw driver\b"),
    ("trial_run", r"\btrial run(?:s)?\b"),
]

_TEXT_SEVERE_EXCLUSION_PATTERNS: list[tuple[str, str]] = [
    ("bomb_threat", r"\bbomb threat\b"),
    ("fir", r"\bfir\b"),
    ("murder", r"\bmurder(?:ed|s)?\b"),
    ("killed", r"\bkilled\b"),
    ("scam", r"\bscam(?:s|med)?\b"),
    ("steal", r"\bsteal(?:s|ing)?\b"),
    ("lures", r"\blures?\b"),
]

_COMPILED_TITLE_EXCLUSIONS = [
    (label, re.compile(pattern, re.IGNORECASE))
    for label, pattern in _TITLE_EXCLUSION_PATTERNS
]
_COMPILED_TEXT_EXCLUSIONS = [
    (label, re.compile(pattern, re.IGNORECASE))
    for label, pattern in _TEXT_SEVERE_EXCLUSION_PATTERNS
]

# Positive mass-gathering category terms (strict word boundaries, never substring matches)
_CATEGORY_SIGNALS: dict[str, tuple[int, list[str]]] = {
    "sports_stadium": (
        50,
        [
            r"\bipl\b",
            r"\brcb\b",
            r"\bcricket match\b",
            r"\bfootball match\b",
            r"\bstadium\b",
            r"\bmarathon\b",
            r"\bhalf marathon\b",
            r"\b10k run\b",
            r"\bcyclothon\b",
            r"\btournament\b",
            r"\bchampionship\b",
            r"\bpro kabaddi\b",
            r"\bbengaluru fc\b",
            r"\bisl match\b",
            r"\bathletic conclave\b",
            r"\bsports conclave\b",
            r"\bmatch day\b",
        ],
    ),
    "concert_festival": (
        45,
        [
            r"\bconcert(?:s)?\b",
            r"\bmusic festival\b",
            r"\bechoes of earth\b",
            r"\bsunburn\b",
            r"\blollapalooza\b",
            r"\bjatre\b",
            r"\bcarnival\b",
            r"\bfood festival\b",
            r"\bcultural festival\b",
            r"\bcomedy festival\b",
            r"\blive concert\b",
            r"\blive performance\b",
            r"\bdj night\b",
            r"\brock night\b",
            r"\bmusic fest\b",
            r"\bart festival\b",
            r"\bliterature festival\b",
            r"\bliterary festival\b",
            r"\bspring gala\b",
            r"\bgala\b",
            r"\bfolklore festival\b",
            r"\bsunidhi chauhan\b",
            r"\bdiljit dosanjh\b",
            r"\bfestival(?:s)?\b",
        ],
    ),
    "expo_summit": (
        45,
        [
            r"\baero india\b",
            r"\bairshow\b",
            r"\bair show\b",
            r"\bexpo\b",
            r"\bexhibition\b",
            r"\btrade fair\b",
            r"\btech summit\b",
            r"\bai summit\b",
            r"\bsummit\b",
            r"\bconclave\b",
            r"\bconference\b",
            r"\bhackathon\b",
            r"\bindusfood\b",
            r"\bcomic con\b",
            r"\bauto expo\b",
            r"\bbook fair\b",
            r"\bflower show\b",
            r"\bscience festival\b",
        ],
    ),
    "rally_protest": (
        35,
        [
            r"\bprotest(?:s|ers)?\b",
            r"\bmass rally\b",
            r"\brally\b",
            r"(?<!\bin\s)\bmarch(?!\s+\d{1,4})\b",
            r"\bbandh\b",
            r"\bstrike\b",
            r"\bprocession\b",
            r"\bparade\b",
            r"\bkaraga\b",
            r"\bdasara\b",
            r"\bnew year(?:'s)? eve\b",
        ],
    ),
}

_COMPILED_CATEGORY_SIGNALS: dict[str, tuple[int, list[re.Pattern[str]]]] = {
    cat: (weight, [re.compile(p, re.IGNORECASE) for p in patterns])
    for cat, (weight, patterns) in _CATEGORY_SIGNALS.items()
}

_HIGH_CAPACITY_VENUE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (term, re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE))
    for term in [
        "palace grounds",
        "jayamahal",
        "chinnaswamy",
        "kanteerava",
        "biec",
        "bengaluru international exhibition",
        "ktpo",
        "manpho",
        "manyata",
        "phoenix marketcity",
        "freedom park",
        "national college grounds",
        "lalbagh",
        "cubbon park",
        "yelahanka air force",
    ]
]

_TICKETING_DOMAINS = (
    "allevents.in",
    "bookmyshow.com",
    "district.in",
    "insider.in",
    "eventbrite",
)


@dataclass(slots=True)
class CrowdRelevanceResult:
    is_relevant: bool
    score: int
    category: str
    estimated_attendance: int
    matched_signals: list[str] = field(default_factory=list)
    rejection_reason: str | None = None


def _estimate_attendance_for_category(category: str, combined_lower: str) -> int:
    if "aero india" in combined_lower or "chinnaswamy" in combined_lower:
        return 38000
    if category == "concert_festival":
        return 28000 if "palace grounds" in combined_lower else 18000
    if category == "sports_stadium":
        return 26000
    if category == "expo_summit":
        if "biec" in combined_lower or "bengaluru international exhibition" in combined_lower or "ktpo" in combined_lower:
            return 20000
        return 12000
    if category == "rally_protest":
        return 12000
    return 10000


def score_crowd_relevance(
    title: str | None,
    text: str | None = None,
    domain: str | None = None,
    source_type: str | None = None,
) -> CrowdRelevanceResult:
    """Classify and score whether a scraped item describes a real crowd gathering capable of cellular surge."""
    title_str = (title or "").strip()
    text_str = (text or "").strip()

    for label, pattern in _COMPILED_TITLE_EXCLUSIONS:
        if pattern.search(title_str):
            return CrowdRelevanceResult(
                is_relevant=False,
                score=0,
                category="irrelevant",
                estimated_attendance=0,
                matched_signals=[],
                rejection_reason=f"title_excluded:{label}",
            )

    text_head = text_str[:300]
    for label, pattern in _COMPILED_TEXT_EXCLUSIONS:
        if pattern.search(text_head):
            return CrowdRelevanceResult(
                is_relevant=False,
                score=0,
                category="irrelevant",
                estimated_attendance=0,
                matched_signals=[],
                rejection_reason=f"text_excluded:{label}",
            )

    combined = f"{title_str} {text_str}".strip()
    combined_lower = combined.lower()

    score = 0
    matched_signals: list[str] = []
    category_scores: dict[str, int] = {}

    for cat, (weight, patterns) in _COMPILED_CATEGORY_SIGNALS.items():
        hits: list[str] = []
        for pat in patterns:
            m = pat.search(combined)
            if m:
                hits.append(m.group(0).lower())
        if hits:
            category_scores[cat] = weight + min(10, (len(hits) - 1) * 5)
            score += weight
            for h in hits:
                sig = f"{cat}:{h}"
                if sig not in matched_signals:
                    matched_signals.append(sig)

    venue_matched = False
    for venue_term, pat in _HIGH_CAPACITY_VENUE_PATTERNS:
        if pat.search(combined):
            if not venue_matched:
                score += 25
                venue_matched = True
            matched_signals.append(f"venue:{venue_term}")

    domain_lower = (domain or "").lower()
    is_ticketing = (source_type == "ticketing_page") or any(td in domain_lower for td in _TICKETING_DOMAINS)
    if is_ticketing:
        score += 30
        matched_signals.append("source:ticketing")

    score = min(100, score)
    is_relevant = score >= 30

    if not is_relevant:
        return CrowdRelevanceResult(
            is_relevant=False,
            score=score,
            category="irrelevant",
            estimated_attendance=0,
            matched_signals=matched_signals,
            rejection_reason="below_crowd_threshold",
        )

    if category_scores:
        best_category = max(category_scores.items(), key=lambda kv: kv[1])[0]
    else:
        best_category = "public_gathering"

    estimated_attendance = _estimate_attendance_for_category(best_category, combined_lower)
    return CrowdRelevanceResult(
        is_relevant=True,
        score=score,
        category=best_category,
        estimated_attendance=estimated_attendance,
        matched_signals=matched_signals,
        rejection_reason=None,
    )


def estimate_crowd_attendance(event: EventRecord) -> int:
    """Return explicit event attendance_high if present, otherwise a category/venue-grounded estimate."""
    if event.attendance_high is not None and event.attendance_high > 0:
        return int(event.attendance_high)
    rel = score_crowd_relevance(event.name, event.venue_name, None, None)
    if rel.is_relevant and rel.estimated_attendance > 0:
        return rel.estimated_attendance
    return 10000
