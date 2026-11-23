"""
Queueing Network Delay Model for Telecom Cellular & Backhaul Latency Prediction.

Mathematical formulation:
Latency = Propagation Delay + Processing Delay + Transmission Delay + Queueing Delay + Backhaul Bottleneck Delay

Queueing Delay follows Kleinrock / M/M/1 approximation with a soft-saturation barrier:
- Light traffic (util < 0.70): linear/quadratic delay curve
- Medium traffic (0.70 <= util < 0.95): exponential queue growth
- Heavy/Saturated traffic (util >= 0.95): buffer limit drop barrier capped at 250 ms
"""
from __future__ import annotations

import math


def calculate_queueing_latency(
    *,
    demand_mbps: float,
    capacity_mbps: float,
    backhaul_capacity_mbps: float | None = None,
    base_propagation_ms: float = 10.0,
    processing_ms: float = 2.0,
) -> float:
    """
    Computes deterministic end-to-end simulated latency in milliseconds based on
    packet transmission, M/M/1 buffer queueing, and backhaul contention.
    """
    if demand_mbps <= 0.0:
        return base_propagation_ms

    cap = max(1.0, capacity_mbps)
    # Transmission serialization delay for standard 1500-byte MTU: (1500 * 8 / (C * 1e6)) * 1000 ms
    tx_delay = round(12.0 / cap, 3)

    rho = demand_mbps / cap

    # Kleinrock / M/M/1 queueing delay with soft-saturation barrier
    if rho < 0.70:
        # D_queue = (1.5 * rho) / (1 - rho)
        queue_delay = (1.5 * rho) / max(0.01, 1.0 - rho)
    elif rho < 0.95:
        # Medium saturation: accelerated queue build-up
        excess = rho - 0.70
        queue_delay = 3.5 + (25.0 * (excess ** 2)) / max(0.01, 1.0 - rho)
    else:
        # Severe saturation: buffer filling to packet discard threshold
        overflow = rho - 0.95
        queue_delay = min(220.0, 75.0 + overflow * 350.0)

    # Backhaul contention delay if backhaul is throttled or exceeded
    backhaul_delay = 0.0
    if backhaul_capacity_mbps and backhaul_capacity_mbps > 0:
        if demand_mbps > backhaul_capacity_mbps:
            bh_ratio = (demand_mbps - backhaul_capacity_mbps) / backhaul_capacity_mbps
            backhaul_delay = min(100.0, bh_ratio * 120.0)

    total_lat = base_propagation_ms + processing_ms + tx_delay + queue_delay + backhaul_delay
    return round(min(350.0, max(base_propagation_ms, total_lat)), 2)


def calculate_latency_uncertainty_bounds(
    central_latency_ms: float,
    horizon_min: int,
) -> tuple[float, float, float]:
    """
    Computes (P10, P50, P90) latency uncertainty bounds accounting for horizon scale.
    """
    sigma = (1.8 + 0.10 * central_latency_ms) * math.sqrt(1.0 + (horizon_min / 30.0))
    p50 = round(central_latency_ms, 2)
    p10 = round(max(10.0, p50 - 1.282 * sigma), 2)
    p90 = round(min(350.0, p50 + 1.282 * sigma), 2)
    return p10, p50, p90
