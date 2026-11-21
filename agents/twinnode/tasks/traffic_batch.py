from __future__ import annotations

import socket
from typing import Any

from apps.api.app.modules.data_generator.network_generator import generate_synthetic_network
from simulation.tick_engine import compute_tick_telemetry
from apps.api.app.core.database import utc_now


def run_traffic_batch(seed: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Deterministically compute synthetic traffic & latency across requested ticks and cells."""
    ticks = max(1, min(12, int(payload.get("ticks", 3))))
    cell_count = int(payload.get("cell_count", 100))
    net, cells, edges, _ = generate_synthetic_network(seed=seed, cell_count=cell_count)
    target_ids = payload.get("cell_ids")
    target_set = set(target_ids) if isinstance(target_ids, list) and target_ids else None

    sim_time = utc_now()
    peak_demand = 0.0
    latencies: list[float] = []
    congested_total = 0

    for t in range(ticks):
        telemetry, _ = compute_tick_telemetry(
            run_id=net.network_id,
            seed=seed,
            tick=t,
            state_version=t + 1,
            sim_time_utc=sim_time,
            cells=cells,
            edges=edges,
        )
        subset = [rec for rec in telemetry if target_set is None or rec.cell_id in target_set]
        for rec in subset:
            peak_demand = max(peak_demand, rec.demand_mbps)
            if rec.cell_state == "ACTIVE":
                latencies.append(rec.simulated_latency_ms)
            if rec.utilisation_pct >= 85.0:
                congested_total += 1

    return {
        "task_type": "traffic_batch",
        "seed": seed,
        "ticks_evaluated": ticks,
        "cells_evaluated": len(target_set) if target_set else len(cells),
        "peak_demand_mbps": round(peak_demand, 2),
        "mean_simulated_latency_ms": round(sum(latencies) / max(1, len(latencies)), 2),
        "congested_cell_ticks": congested_total,
        "executed_on_hostname": socket.gethostname(),
        "label": "SYNTHETIC COMPUTE BATCH RESULT",
    }
