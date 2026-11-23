from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

FEATURE_COLUMNS: list[str] = [
    "hour_of_day",
    "day_of_week",
    "horizon_min",
    "cell_capacity_mbps",
    "backhaul_capacity_mbps",
    "criticality",
    "current_demand_mbps",
    "lag_demand_1",
    "lag_demand_2",
    "lag_demand_3",
    "demand_trend_slope",
    "current_utilisation_pct",
    "current_latency_ms",
    "queued_mbps",
    "neighbour_mean_utilisation_pct",
    "event_demand_delta_mbps",
    "event_distance_km",
    "event_confidence",
    "overlapping_events_count",
    "active_fault",
]

TARGET_COLUMNS: list[str] = [
    "target_demand_mbps",
]


@dataclass
class FeatureVector:
    hour_of_day: float = 0.0
    day_of_week: float = 0.0
    horizon_min: float = 15.0
    cell_capacity_mbps: float = 1000.0
    backhaul_capacity_mbps: float = 2000.0
    criticality: float = 1.0
    current_demand_mbps: float = 0.0
    lag_demand_1: float = 0.0
    lag_demand_2: float = 0.0
    lag_demand_3: float = 0.0
    demand_trend_slope: float = 0.0
    current_utilisation_pct: float = 0.0
    current_latency_ms: float = 15.0
    queued_mbps: float = 0.0
    neighbour_mean_utilisation_pct: float = 0.0
    event_demand_delta_mbps: float = 0.0
    event_distance_km: float = 10.0
    event_confidence: float = 0.0
    overlapping_events_count: float = 0.0
    active_fault: float = 0.0
    # Backward compatibility fields for legacy adapter:
    event_intensity: float = 0.0
    event_impact_weight: float = 0.0

    def to_list(self) -> list[float]:
        return [
            self.hour_of_day,
            self.day_of_week,
            self.horizon_min,
            self.cell_capacity_mbps,
            self.backhaul_capacity_mbps,
            self.criticality,
            self.current_demand_mbps,
            self.lag_demand_1,
            self.lag_demand_2,
            self.lag_demand_3,
            self.demand_trend_slope,
            self.current_utilisation_pct,
            self.current_latency_ms,
            self.queued_mbps,
            self.neighbour_mean_utilisation_pct,
            self.event_demand_delta_mbps,
            self.event_distance_km,
            self.event_confidence,
            self.overlapping_events_count,
            self.active_fault,
        ]

    def to_legacy_list(self) -> list[float]:
        return [
            self.hour_of_day,
            self.day_of_week,
            self.cell_capacity_mbps,
            self.criticality,
            self.current_demand_mbps,
            self.lag_demand_1,
            self.lag_demand_2,
            self.lag_demand_3,
            self.demand_trend_slope,
            self.current_utilisation_pct,
            self.event_intensity,
            self.event_distance_km,
            self.event_impact_weight,
            self.active_fault,
        ]
