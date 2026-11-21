from __future__ import annotations

import socket
from typing import Any

from apps.api.app.core.database import utc_now
from apps.api.app.modules.data_generator.network_generator import generate_synthetic_network
from simulation.tick_engine import compute_tick_telemetry


def run_scenario_evaluation(seed: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a deterministic intensity sweep over synthetic Palace Grounds cells."""
    intensities = payload.get("intensities", [0.8, 1.0, 1.4, 1.8])
    if not isinstance(intensities, list) or not intensities:
        intensities = [1.0, 1.4]
    intensities = [float(x) for x in intensities[:6]]

    net, cells, edges, _ = generate_synthetic_network(seed=seed, cell_count=100)
    cbd_cells = [c.cell_id for c in cells if c.region == "Central Business District"][:16]
    base_uplift = {cid: 185.0 for cid in cbd_cells}
    sim_time = utc_now()

    scenarios: list[dict[str, Any]] = []
    for intensity in intensities:
        telemetry, summary = compute_tick_telemetry(
            run_id=net.network_id,
            seed=seed,
            tick=4,
            state_version=1,
            sim_time_utc=sim_time,
            cells=cells,
            edges=edges,
            event_uplift_by_cell=base_uplift,
            event_intensity=intensity,
        )
        scenarios.append(
            {
                "intensity": intensity,
                "congested_cells": summary.congested_cells,
                "peak_utilisation_pct": summary.peak_utilisation_pct,
                "total_queued_mbps": summary.total_queued_mbps,
                "total_unserved_mbps": summary.total_unserved_mbps,
                "mean_simulated_latency_ms": summary.mean_simulated_latency_ms,
                "sample_cell_count": len(telemetry),
            }
        )

    return {
        "task_type": "scenario_evaluation",
        "seed": seed,
        "scenarios": scenarios,
        "executed_on_hostname": socket.gethostname(),
        "label": "SYNTHETIC SCENARIO SWEEP RESULT",
    }
