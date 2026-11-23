from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class EventCategoryProfile:
    category: str
    radius_km: float
    default_attendance: int
    mbps_per_1000_attendees: float
    arrival_hours: float
    default_duration_hours: float
    departure_hours: float
    arrival_ramp_factor: float
    event_peak_factor: float
    departure_exit_factor: float


CATEGORY_PROFILES: dict[str, EventCategoryProfile] = {
    "CONCERT": EventCategoryProfile(
        category="CONCERT",
        radius_km=3.5,
        default_attendance=15000,
        mbps_per_1000_attendees=8.5,
        arrival_hours=2.0,
        default_duration_hours=3.5,
        departure_hours=1.5,
        arrival_ramp_factor=0.65,
        event_peak_factor=1.15,
        departure_exit_factor=0.85,
    ),
    "SPORTS": EventCategoryProfile(
        category="SPORTS",
        radius_km=4.0,
        default_attendance=25000,
        mbps_per_1000_attendees=7.0,
        arrival_hours=1.5,
        default_duration_hours=3.5,
        departure_hours=1.5,
        arrival_ramp_factor=0.55,
        event_peak_factor=1.20,
        departure_exit_factor=0.90,
    ),
    "TECH_CONFERENCE": EventCategoryProfile(
        category="TECH_CONFERENCE",
        radius_km=2.5,
        default_attendance=5000,
        mbps_per_1000_attendees=12.0,
        arrival_hours=1.0,
        default_duration_hours=7.0,
        departure_hours=1.0,
        arrival_ramp_factor=0.50,
        event_peak_factor=0.80,
        departure_exit_factor=0.45,
    ),
    "EXHIBITION": EventCategoryProfile(
        category="EXHIBITION",
        radius_km=3.0,
        default_attendance=8000,
        mbps_per_1000_attendees=6.5,
        arrival_hours=1.0,
        default_duration_hours=6.0,
        departure_hours=1.0,
        arrival_ramp_factor=0.35,
        event_peak_factor=0.65,
        departure_exit_factor=0.35,
    ),
    "FESTIVAL": EventCategoryProfile(
        category="FESTIVAL",
        radius_km=3.5,
        default_attendance=12000,
        mbps_per_1000_attendees=7.5,
        arrival_hours=1.5,
        default_duration_hours=5.0,
        departure_hours=1.5,
        arrival_ramp_factor=0.45,
        event_peak_factor=0.90,
        departure_exit_factor=0.60,
    ),
    "MEETUP": EventCategoryProfile(
        category="MEETUP",
        radius_km=1.2,
        default_attendance=300,
        mbps_per_1000_attendees=10.0,
        arrival_hours=0.5,
        default_duration_hours=2.0,
        departure_hours=0.5,
        arrival_ramp_factor=0.30,
        event_peak_factor=0.50,
        departure_exit_factor=0.25,
    ),
    "OTHER": EventCategoryProfile(
        category="OTHER",
        radius_km=2.0,
        default_attendance=1000,
        mbps_per_1000_attendees=5.0,
        arrival_hours=1.0,
        default_duration_hours=3.0,
        departure_hours=1.0,
        arrival_ramp_factor=0.30,
        event_peak_factor=0.50,
        departure_exit_factor=0.25,
    ),
}


def get_category_profile(category: str | None) -> EventCategoryProfile:
    if not category:
        return CATEGORY_PROFILES["OTHER"]
    normalized = category.strip().upper()
    if normalized in CATEGORY_PROFILES:
        return CATEGORY_PROFILES[normalized]
    # Check partial mappings
    if "CONCERT" in normalized or "MUSIC" in normalized or "GIG" in normalized:
        return CATEGORY_PROFILES["CONCERT"]
    if "SPORT" in normalized or "MATCH" in normalized or "CRICKET" in normalized or "FOOTBALL" in normalized:
        return CATEGORY_PROFILES["SPORTS"]
    if "CONF" in normalized or "TECH" in normalized or "HACKATHON" in normalized or "SUMMIT" in normalized:
        return CATEGORY_PROFILES["TECH_CONFERENCE"]
    if "EXPO" in normalized or "EXHIBIT" in normalized or "FAIR" in normalized:
        return CATEGORY_PROFILES["EXHIBITION"]
    if "FEST" in normalized or "CARNIVAL" in normalized:
        return CATEGORY_PROFILES["FESTIVAL"]
    if "MEET" in normalized or "COMMUNITY" in normalized:
        return CATEGORY_PROFILES["MEETUP"]
    return CATEGORY_PROFILES["OTHER"]


def compute_event_window(
    profile: EventCategoryProfile,
    start_at: datetime | None,
    end_at: datetime | None,
) -> tuple[datetime, datetime, datetime, datetime]:
    """
    Returns (window_start, event_start, event_end, window_end) as UTC datetimes.
    """
    now = datetime.now(timezone.utc)
    ev_start = start_at if start_at is not None else now
    if ev_start.tzinfo is None:
        ev_start = ev_start.replace(tzinfo=timezone.utc)
    else:
        ev_start = ev_start.astimezone(timezone.utc)

    if end_at is not None:
        ev_end = end_at if end_at.tzinfo is not None else end_at.replace(tzinfo=timezone.utc)
        ev_end = ev_end.astimezone(timezone.utc)
        if ev_end <= ev_start:
            ev_end = ev_start + timedelta(hours=profile.default_duration_hours)
    else:
        ev_end = ev_start + timedelta(hours=profile.default_duration_hours)

    window_start = ev_start - timedelta(hours=profile.arrival_hours)
    window_end = ev_end + timedelta(hours=profile.departure_hours)
    return window_start, ev_start, ev_end, window_end


def evaluate_temporal_surge_factor(
    profile: EventCategoryProfile,
    window_start: datetime,
    event_start: datetime,
    event_end: datetime,
    window_end: datetime,
    eval_time: datetime,
) -> float:
    """
    Calculates surge multiplier factor [0.0 - peak] at a specific instant in time.
    """
    if eval_time.tzinfo is None:
        eval_time = eval_time.replace(tzinfo=timezone.utc)
    else:
        eval_time = eval_time.astimezone(timezone.utc)

    if eval_time < window_start or eval_time > window_end:
        return 0.0

    # Arrival phase (window_start -> event_start)
    if eval_time < event_start:
        total_arrival_sec = max(1.0, (event_start - window_start).total_seconds())
        elapsed_sec = (eval_time - window_start).total_seconds()
        progress = elapsed_sec / total_arrival_sec
        # Non-linear build-up
        return float(progress ** 1.5 * profile.arrival_ramp_factor)

    # In-event phase (event_start -> event_end)
    if eval_time <= event_end:
        total_event_sec = max(1.0, (event_end - event_start).total_seconds())
        elapsed_sec = (eval_time - event_start).total_seconds()
        progress = elapsed_sec / total_event_sec
        # Peak curve: elevated throughout, highest around 50%-75% of the event
        midpoint_boost = 1.0 + 0.15 * math.sin(progress * math.pi)
        return float(profile.event_peak_factor * midpoint_boost)

    # Departure phase (event_end -> window_end)
    total_departure_sec = max(1.0, (window_end - event_end).total_seconds())
    elapsed_sec = (eval_time - event_end).total_seconds()
    progress = elapsed_sec / total_departure_sec
    # Rapid falloff
    decay = (1.0 - progress) ** 1.3
    return float(profile.departure_exit_factor * decay)


import math


def generate_profile_sample_points(
    profile: EventCategoryProfile,
    window_start: datetime,
    event_start: datetime,
    event_end: datetime,
    window_end: datetime,
    peak_demand_mbps: float,
    sample_step_minutes: int = 15,
) -> list[dict[str, Any]]:
    """
    Generates discrete time series sample points for visualization / tick interpolation.
    """
    total_minutes = int((window_end - window_start).total_seconds() / 60)
    samples: list[dict[str, Any]] = []

    curr_time = window_start
    while curr_time <= window_end:
        factor = evaluate_temporal_surge_factor(
            profile, window_start, event_start, event_end, window_end, curr_time
        )
        offset_mins = int((curr_time - window_start).total_seconds() / 60)
        samples.append(
            {
                "timestamp": curr_time.isoformat(),
                "offset_minutes": offset_mins,
                "surge_factor": round(factor, 4),
                "demand_mbps": round(peak_demand_mbps * factor, 2),
            }
        )
        curr_time += timedelta(minutes=sample_step_minutes)

    return samples
