from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

FEATURE_COLUMNS: list[str] = [
    "hour_of_day",
    "day_of_week",
    "cell_capacity_mbps",
    "criticality",
    "current_demand_mbps",
    "lag_demand_1",
    "lag_demand_2",
    "lag_demand_3",
    "demand_trend_slope",
    "current_utilisation_pct",
    "event_intensity",
    "event_distance_km",
    "event_impact_weight",
    "active_fault",
]

TARGET_COLUMNS: list[str] = [
    "target_demand_15m_mbps",
    "target_demand_30m_mbps",
]


@dataclass(frozen=True)
class FeatureVector:
    hour_of_day: float
    day_of_week: float
    cell_capacity_mbps: float
    criticality: float
    current_demand_mbps: float
    lag_demand_1: float
    lag_demand_2: float
    lag_demand_3: float
    demand_trend_slope: float
    current_utilisation_pct: float
    event_intensity: float
    event_distance_km: float
    event_impact_weight: float
    active_fault: float

    def to_list(self) -> list[float]:
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
