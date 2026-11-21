from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from apps.api.app.core.database import utc_now
from apps.api.app.schemas.networks import CellEdgeRecord, CellOperationalState, CellRecord
from apps.api.app.schemas.simulations import (
    CellTelemetryRecord,
    LatencyComponents,
    SimulationSummary,
)


def temporal_profile_multiplier(tick: int) -> float:
    """Three-phase synthetic event profile: arrival ramp, event peak, departure decay."""
    if tick <= 0:
        return 0.55
    if tick == 1:
        return 0.78
    if tick == 2:
        return 0.92
    if 3 <= tick <= 10:
        return 1.0
    if 11 <= tick <= 15:
        return round(max(0.35, 1.0 - (tick - 10) * 0.13), 4)
    return 0.25


def compute_tick_telemetry(
    *,
    run_id: UUID,
    seed: int,
    tick: int,
    state_version: int,
    sim_time_utc: datetime,
    cells: list[CellRecord],
    edges: list[CellEdgeRecord],
    cell_states_override: dict[str, CellOperationalState] | None = None,
    event_uplift_by_cell: dict[str, float] | None = None,
    event_intensity: float = 1.0,
    applied_transfers: list[dict[str, Any]] | None = None,
    faults: dict[str, Any] | None = None,
    recorded_at: datetime | None = None,
) -> tuple[list[CellTelemetryRecord], SimulationSummary]:
    """Deterministically advance and account for all demand across 100 cells for one tick."""
    rng = random.Random(f"{seed}:tick:{tick}")
    rec_ts = recorded_at or utc_now()
    uplift_map = event_uplift_by_cell or {}
    fault_map = faults or {}
    transfers = applied_transfers or []
    state_overrides = cell_states_override or {}

    effective_states: dict[str, CellOperationalState] = {}
    cell_by_id: dict[str, CellRecord] = {}
    for c in cells:
        cell_by_id[c.cell_id] = c
        st = state_overrides.get(c.cell_id, c.current_state)
        if fault_map.get(c.cell_id, {}).get("fault_type") == "CELL_FAILURE" and fault_map[c.cell_id].get("active", True):
            st = "FAILED"
        effective_states[c.cell_id] = st

    # Time-of-day smooth diurnal multiplier based on simulated UTC hour
    hour_float = sim_time_utc.hour + sim_time_utc.minute / 60.0
    diurnal = 0.85 + 0.25 * math.sin(((hour_float - 7.0) / 24.0) * 2.0 * math.pi)
    t_mult = temporal_profile_multiplier(tick)

    bg_demand: dict[str, float] = {}
    ev_demand: dict[str, float] = {}
    eff_cap: dict[str, float] = {}

    for c in cells:
        st = effective_states[c.cell_id]
        jitter = rng.uniform(0.94, 1.06)
        if st == "STANDBY":
            bg = 0.0
            ev = 0.0
        else:
            bg = round(c.base_load_mbps * diurnal * jitter, 4)
            base_uplift = uplift_map.get(c.cell_id, 0.0)
            ev = round(base_uplift * event_intensity * t_mult, 4) if base_uplift > 0.0 else 0.0
        bg_demand[c.cell_id] = bg
        ev_demand[c.cell_id] = ev

        if st == "ACTIVE":
            cap = c.capacity_mbps
            f_info = fault_map.get(c.cell_id, {})
            if f_info.get("fault_type") == "BACKHAUL_CONGESTION" and f_info.get("active", True):
                sev = float(f_info.get("severity", 0.6))
                cap = cap * max(0.25, 1.0 - 0.55 * sev)
            eff_cap[c.cell_id] = round(cap, 4)
        else:
            eff_cap[c.cell_id] = 0.0

    # Compute raw total demands before transfers/failover
    raw_demand: dict[str, float] = {
        cid: round(bg_demand[cid] + ev_demand[cid], 4) for cid in cell_by_id
    }

    # Apply planned/approved transfers deterministically without losing demand
    transfer_delta: dict[str, float] = {cid: 0.0 for cid in cell_by_id}
    for tr in transfers:
        src = str(tr.get("source_id", ""))
        tgt = str(tr.get("target_id", ""))
        amt = float(tr.get("amount", 0.0))
        if src in cell_by_id and tgt in cell_by_id and amt > 0.0:
            if effective_states.get(tgt) == "ACTIVE":
                available_src = max(0.0, raw_demand[src] + transfer_delta[src])
                actual_amt = min(amt, available_src)
                transfer_delta[src] -= actual_amt
                transfer_delta[tgt] += actual_amt

    # Redistribute eligible load away from FAILED cells across enabled handover_support edges
    failover_delta: dict[str, float] = {cid: 0.0 for cid in cell_by_id}
    adj_edges: dict[str, list[tuple[str, float]]] = {cid: [] for cid in cell_by_id}
    for e in edges:
        if not e.enabled or e.edge_type != "handover_support":
            continue
        adj_edges[e.source_cell_id].append((e.target_cell_id, e.max_transfer_mbps))
        adj_edges[e.target_cell_id].append((e.source_cell_id, e.max_transfer_mbps))

    for cid in sorted(cell_by_id):
        if effective_states[cid] != "FAILED":
            continue
        remaining_to_shed = max(0.0, raw_demand[cid] + transfer_delta[cid] + failover_delta[cid])
        if remaining_to_shed <= 0.0:
            continue
        for nbr_id, max_edge_mbps in sorted(adj_edges[cid], key=lambda item: item[0]):
            if remaining_to_shed <= 0.0:
                break
            if effective_states.get(nbr_id) != "ACTIVE":
                continue
            nbr_load = raw_demand[nbr_id] + transfer_delta[nbr_id] + failover_delta[nbr_id]
            nbr_spare = max(0.0, eff_cap[nbr_id] - nbr_load)
            moved = min(remaining_to_shed, max_edge_mbps, nbr_spare)
            if moved > 0.0:
                failover_delta[cid] -= moved
                failover_delta[nbr_id] += moved
                remaining_to_shed -= moved

    telemetry_records: list[CellTelemetryRecord] = []
    active_count = 0
    standby_count = 0
    failed_count = 0
    congested_count = 0

    for cid in sorted(cell_by_id):
        st = effective_states[cid]
        cap = eff_cap[cid]
        bg = bg_demand[cid]
        ev = ev_demand[cid]
        net_shift = transfer_delta[cid] + failover_delta[cid]

        # Keep background + event non-negative; represent net shift inside total demand cleanly
        demand = round(max(0.0, bg + ev + net_shift), 4)
        # Re-anchor bg+ev proportionally if negative transfer reduced total below bg+ev so audit stays transparent
        if demand < bg + ev and (bg + ev) > 0:
            ratio = demand / (bg + ev)
            bg_adj = round(bg * ratio, 4)
            ev_adj = round(max(0.0, demand - bg_adj), 4)
        else:
            bg_adj = round(bg + max(0.0, net_shift), 4) if ev == 0.0 else round(bg, 4)
            ev_adj = round(max(0.0, demand - bg_adj), 4)

        if st == "ACTIVE" and cap > 0.0:
            active_count += 1
            served = round(min(demand, cap), 4)
            excess = max(0.0, demand - served)
            queue_cap = cap * 0.25
            queued = round(min(excess, queue_cap), 4)
            unserved = round(max(0.0, demand - served - queued), 4)
            # Re-align demand to exact sum to prevent IEEE-754 4-decimal rounding drift
            demand = round(served + queued + unserved, 4)

            util = round(min(100.0, (served / cap) * 100.0), 2)
            load_ratio = demand / cap

            f_info = fault_map.get(cid, {})
            bh_penalty = (
                28.0 * float(f_info.get("severity", 0.6))
                if f_info.get("fault_type") == "BACKHAUL_CONGESTION" and f_info.get("active", True)
                else 0.0
            )
            radio_ms = round(8.0 + 18.0 * (min(load_ratio, 1.8) ** 2) + (queued / cap) * 40.0, 2)
            transport_ms = round(4.0 + 10.0 * min(load_ratio, 1.5) + bh_penalty, 2)
            core_ms = round(3.5 + (2.5 if unserved > 0.0 else 0.0), 2)
            processing_ms = round(2.5 + 5.0 * (util / 100.0), 2)
            total_lat = round(radio_ms + transport_ms + core_ms + processing_ms, 2)
            pkt_loss = round(min(25.0, (unserved / demand) * 100.0), 2) if demand > 0 and unserved > 0 else 0.0
            energy = round(12.0 + 28.0 * (util / 100.0), 2)

            if util >= 85.0 or queued > 0.0 or unserved > 0.0:
                congested_count += 1
        elif st == "STANDBY":
            standby_count += 1
            served = 0.0
            queued = round(min(demand, 25.0), 4)
            unserved = round(max(0.0, demand - queued), 4)
            demand = round(served + queued + unserved, 4)
            util = 0.0
            radio_ms = transport_ms = core_ms = processing_ms = 0.0
            total_lat = 0.0
            pkt_loss = 100.0 if unserved > 0 else 0.0
            energy = 2.0
        else:
            failed_count += 1
            congested_count += 1
            served = 0.0
            queued = round(min(demand, 40.0), 4)
            unserved = round(max(0.0, demand - queued), 4)
            demand = round(served + queued + unserved, 4)
            util = 0.0
            radio_ms = 180.0
            transport_ms = 40.0
            core_ms = 15.0
            processing_ms = 15.0
            total_lat = 250.0
            pkt_loss = 100.0 if demand > 0 else 0.0
            energy = 0.5

        telemetry_records.append(
            CellTelemetryRecord(
                run_id=run_id,
                tick=tick,
                state_version=state_version,
                cell_id=cid,
                background_demand_mbps=bg_adj,
                event_demand_mbps=ev_adj,
                demand_mbps=demand,
                served_mbps=served,
                queued_mbps=queued,
                unserved_mbps=unserved,
                utilisation_pct=util,
                simulated_latency_ms=total_lat,
                latency_components=LatencyComponents(
                    radio_ms=radio_ms,
                    transport_ms=transport_ms,
                    core_ms=core_ms,
                    processing_ms=processing_ms,
                ),
                packet_loss_pct=pkt_loss,
                energy_units=energy,
                cell_state=st,
                sim_time_utc=sim_time_utc,
                recorded_at=rec_ts,
            )
        )

    active_latencies = [t.simulated_latency_ms for t in telemetry_records if t.cell_state == "ACTIVE"]
    summary = SimulationSummary(
        total_cells=len(telemetry_records),
        active_cells=active_count,
        standby_cells=standby_count,
        failed_cells=failed_count,
        congested_cells=congested_count,
        total_demand_mbps=round(sum(t.demand_mbps for t in telemetry_records), 2),
        total_served_mbps=round(sum(t.served_mbps for t in telemetry_records), 2),
        total_queued_mbps=round(sum(t.queued_mbps for t in telemetry_records), 2),
        total_unserved_mbps=round(sum(t.unserved_mbps for t in telemetry_records), 2),
        peak_utilisation_pct=round(max((t.utilisation_pct for t in telemetry_records), default=0.0), 2),
        mean_simulated_latency_ms=round(
            sum(active_latencies) / max(1, len(active_latencies)), 2
        ),
    )
    return telemetry_records, summary


def advance_sim_clock(sim_time_utc: datetime, step_minutes: int = 5) -> datetime:
    return sim_time_utc + timedelta(minutes=step_minutes)
