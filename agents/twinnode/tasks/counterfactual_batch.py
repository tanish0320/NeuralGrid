from __future__ import annotations

import socket
from typing import Any

from apps.api.app.core.database import utc_now
from apps.api.app.modules.data_generator.network_generator import generate_synthetic_network
from simulation.tick_engine import compute_tick_telemetry


def run_counterfactual_batch(seed: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Run matched no-action baseline vs intervention simulation trajectories deterministically."""
    horizon_ticks = max(1, min(24, int(payload.get("horizon_ticks", 6))))
    transfers = payload.get("transfers", [])
    activations = payload.get("cell_activations", [])

    net, cells, edges, _ = generate_synthetic_network(seed=seed, cell_count=100)
    cbd_cells = [c.cell_id for c in cells if c.region == "Central Business District" and c.initial_state == "ACTIVE"][:14]
    uplift_map = {cid: 240.0 for cid in cbd_cells}
    sim_time = utc_now()

    base_congested = 0
    base_peak_util = 0.0
    base_queued = 0.0

    int_congested = 0
    int_peak_util = 0.0
    int_queued = 0.0

    activation_overrides = {str(cid): "ACTIVE" for cid in activations}

    for t in range(horizon_ticks):
        _, b_sum = compute_tick_telemetry(
            run_id=net.network_id,
            seed=seed,
            tick=t,
            state_version=t + 1,
            sim_time_utc=sim_time,
            cells=cells,
            edges=edges,
            event_uplift_by_cell=uplift_map,
            event_intensity=1.2,
        )
        base_congested += b_sum.congested_cells
        base_peak_util = max(base_peak_util, b_sum.peak_utilisation_pct)
        base_queued += b_sum.total_queued_mbps

        _, i_sum = compute_tick_telemetry(
            run_id=net.network_id,
            seed=seed,
            tick=t,
            state_version=t + 1,
            sim_time_utc=sim_time,
            cells=cells,
            edges=edges,
            cell_states_override=activation_overrides,  # type: ignore[arg-type]
            event_uplift_by_cell=uplift_map,
            event_intensity=1.2,
            applied_transfers=transfers if isinstance(transfers, list) else [],
        )
        int_congested += i_sum.congested_cells
        int_peak_util = max(int_peak_util, i_sum.peak_utilisation_pct)
        int_queued += i_sum.total_queued_mbps

    return {
        "task_type": "counterfactual_batch",
        "seed": seed,
        "horizon_ticks": horizon_ticks,
        "baseline_congested_cell_minutes": round(base_congested * 5.0, 2),
        "intervention_congested_cell_minutes": round(int_congested * 5.0, 2),
        "baseline_peak_utilisation_pct": round(base_peak_util, 2),
        "intervention_peak_utilisation_pct": round(int_peak_util, 2),
        "baseline_total_queued_mbps": round(base_queued, 2),
        "intervention_total_queued_mbps": round(int_queued, 2),
        "executed_on_hostname": socket.gethostname(),
        "label": "SYNTHETIC COUNTERFACTUAL COMPUTE BATCH",
    }
