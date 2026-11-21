from __future__ import annotations

import csv
import math
import random
from pathlib import Path

from ml.traffic.feature_contract import FEATURE_COLUMNS


def generate_synthetic_dataset(
    num_samples: int = 5000,
    seed: int = 42,
    output_path: Path | str = "ml/traffic/synthetic_traffic_dataset.csv",
) -> Path:
    """Generates synthetic time-series telemetry rows for ML training.
    
    Chronological progression: tick-by-tick simulation dynamics across cells.
    """
    rng = random.Random(seed)
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    header = FEATURE_COLUMNS + ["target_demand_15m_mbps", "target_demand_30m_mbps"]

    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)

        # Base capacities: 300 to 1200 Mbps
        cell_capacities = [300.0, 500.0, 800.0, 1000.0, 1200.0]

        for i in range(num_samples):
            # Time progression
            sim_minute = (i * 5) % (24 * 60)
            hour_of_day = sim_minute / 60.0
            day_of_week = ((i * 5) // (24 * 60)) % 7

            cap = rng.choice(cell_capacities)
            crit = rng.choice([1.0, 2.0, 3.0])

            # Diurnal baseline
            diurnal = 0.5 + 0.4 * math.sin(math.pi * (hour_of_day - 6) / 12) if 6 <= hour_of_day <= 22 else 0.25
            base_demand = cap * diurnal * (0.85 + 0.3 * rng.random())

            # Event parameters
            has_event = rng.random() < 0.25
            event_intensity = rng.uniform(1.2, 3.0) if has_event else 1.0
            event_dist = rng.uniform(0.2, 5.0) if has_event else 15.0
            event_weight = max(0.0, 1.0 - (event_dist / 4.0)) * (event_intensity - 1.0) if has_event else 0.0

            active_fault = 1.0 if rng.random() < 0.05 else 0.0

            lag_3 = base_demand * 0.95
            lag_2 = base_demand * 0.98
            lag_1 = base_demand
            current_demand = base_demand * (1.0 + event_weight * 0.5)

            trend_slope = (current_demand - lag_3) / 3.0
            util_pct = min(100.0, (current_demand / cap) * 100.0)

            # Targets (+15m is 3 ticks ahead, +30m is 6 ticks ahead)
            event_future_multiplier_15 = (1.0 + event_weight * 0.8)
            event_future_multiplier_30 = (1.0 + event_weight * 0.95)

            noise_15 = rng.gauss(0.0, cap * 0.02)
            noise_30 = rng.gauss(0.0, cap * 0.04)

            target_15 = max(10.0, (current_demand + trend_slope * 2.0) * event_future_multiplier_15 + noise_15)
            target_30 = max(10.0, (current_demand + trend_slope * 4.0) * event_future_multiplier_30 + noise_30)

            row = [
                round(hour_of_day, 2),
                day_of_week,
                round(cap, 1),
                crit,
                round(current_demand, 2),
                round(lag_1, 2),
                round(lag_2, 2),
                round(lag_3, 2),
                round(trend_slope, 2),
                round(util_pct, 1),
                round(event_intensity, 2),
                round(event_dist, 2),
                round(event_weight, 3),
                active_fault,
                round(target_15, 2),
                round(target_30, 2),
            ]
            writer.writerow(row)

    return out_file


if __name__ == "__main__":
    generate_synthetic_dataset()
