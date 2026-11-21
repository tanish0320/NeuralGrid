from __future__ import annotations

import math
from uuid import UUID, uuid4

from fastapi import HTTPException

from apps.api.app.api.websocket import ConnectionManager
from apps.api.app.core.database import utc_now
from apps.api.app.core.events import AuditLogger
from apps.api.app.modules.data_generator.network_generator import generate_synthetic_network
from apps.api.app.repositories.events import EventRepository
from apps.api.app.repositories.networks import NetworkRepository
from apps.api.app.repositories.plans import PlanRepository
from apps.api.app.repositories.simulations import SimulationRepository
from apps.api.app.repositories.twinnode import TwinNodeRepository
from apps.api.app.repositories.verification import VerificationRepository
from apps.api.app.schemas.networks import CellOperationalState
from apps.api.app.schemas.verification import (
    SimulationBranchMetrics,
    TwinNodeExecutionMetrics,
    VerificationResultResponse,
    VerificationRunRequest,
)
from simulation.tick_engine import advance_sim_clock, compute_tick_telemetry


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return round(ordered[int(k)], 2)
    return round(ordered[f] + (ordered[c] - ordered[f]) * (k - f), 2)


class CounterfactualVerifier:
    """Runs matched baseline/no-action vs intervention simulation branches from identical seed & initial state."""

    def __init__(
        self,
        *,
        network_repo: NetworkRepository,
        sim_repo: SimulationRepository,
        event_repo: EventRepository,
        plan_repo: PlanRepository,
        twinnode_repo: TwinNodeRepository,
        verification_repo: VerificationRepository,
        audit: AuditLogger,
        ws_manager: ConnectionManager,
    ) -> None:
        self.network_repo = network_repo
        self.sim_repo = sim_repo
        self.event_repo = event_repo
        self.plan_repo = plan_repo
        self.twinnode_repo = twinnode_repo
        self.verification_repo = verification_repo
        self.audit = audit
        self.ws = ws_manager

    async def verify(self, request: VerificationRunRequest) -> VerificationResultResponse:
        sim_run = self.sim_repo.get_run(request.simulation_id)
        if sim_run is None:
            raise HTTPException(status_code=404, detail=f"Simulation {request.simulation_id} not found")
        plan = self.plan_repo.get_plan(request.plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail=f"Plan {request.plan_id} not found")
        if plan.simulation_id != sim_run.id:
            raise HTTPException(
                status_code=409,
                detail=f"Plan {plan.plan_id} does not belong to simulation {sim_run.id}",
            )

        # Regenerate identical clean initial network cells/edges from matched seed
        _, initial_cells, edges, _ = generate_synthetic_network(
            seed=sim_run.seed, cell_count=100
        )

        uplift_map: dict[str, float] = {}
        effective_event_id = sim_run.active_event_id or plan.event_id
        if effective_event_id is not None:
            impact = self.event_repo.get_impact(effective_event_id, sim_run.id)
            if impact is not None:
                event = self.event_repo.get_event(effective_event_id)
                base_int = event.intensity if event else 1.0
                scale = sim_run.event_intensity / max(0.1, base_int)
                uplift_map = {
                    c.cell_id: round(c.estimated_additional_demand_mbps * scale, 4)
                    for c in impact.affected_cells
                }

        # Extract intervention actions from plan
        activations: dict[str, CellOperationalState] = {}
        transfers: list[dict[str, object]] = []
        for action in plan.actions:
            if action.action_type == "activate_standby_cell":
                activations[action.target_id] = "ACTIVE"
            elif action.action_type == "reallocate_load":
                transfers.append(
                    {
                        "source_id": action.source_id,
                        "target_id": action.target_id,
                        "amount": action.amount,
                    }
                )

        baseline_run_id = f"{sim_run.id}-baseline"
        intervention_run_id = f"{sim_run.id}-intervention"

        def run_branch(
            branch_uuid: UUID,
            overrides: dict[str, CellOperationalState],
            branch_transfers: list[dict[str, object]],
            action_count: int,
        ) -> SimulationBranchMetrics:
            congested_ticks = 0
            peak_util = 0.0
            latencies: list[float] = []
            total_queued = 0.0
            total_unserved = 0.0
            total_energy = 0.0
            clock = sim_run.sim_time_utc

            for step_idx in range(request.horizon_ticks):
                tick_num = sim_run.tick + step_idx
                telemetry, summary = compute_tick_telemetry(
                    run_id=branch_uuid,
                    seed=sim_run.seed,
                    tick=tick_num,
                    state_version=plan.state_version,
                    sim_time_utc=clock,
                    cells=initial_cells,
                    edges=edges,
                    cell_states_override=overrides,
                    event_uplift_by_cell=uplift_map,
                    event_intensity=1.0,
                    applied_transfers=branch_transfers,
                    faults=sim_run.faults,
                )
                congested_ticks += summary.congested_cells
                peak_util = max(peak_util, summary.peak_utilisation_pct)
                total_queued += summary.total_queued_mbps
                total_unserved += summary.total_unserved_mbps
                for rec in telemetry:
                    total_energy += rec.energy_units
                    if rec.cell_state == "ACTIVE":
                        latencies.append(rec.simulated_latency_ms)
                clock = advance_sim_clock(clock, step_minutes=int(sim_run.config.get("step_minutes", 5)))

            return SimulationBranchMetrics(
                congested_cell_minutes=round(congested_ticks * 5.0, 2),
                peak_utilisation_pct=round(peak_util, 2),
                simulated_latency_p50_ms=_percentile(latencies, 50.0),
                simulated_latency_p95_ms=_percentile(latencies, 95.0),
                simulated_latency_max_ms=round(max(latencies, default=0.0), 2),
                total_queued_mbps=round(total_queued, 2),
                total_unserved_mbps=round(total_unserved, 2),
                total_energy_units=round(total_energy, 2),
                action_count=action_count,
            )

        baseline_metrics = run_branch(uuid4(), {}, [], 0)
        intervention_metrics = run_branch(
            uuid4(), activations, transfers, len(plan.actions)
        )

        # Physical TwinNode task execution metrics (strictly separate from RAN metrics)
        plan_tasks = self.twinnode_repo.list_tasks(plan_id=plan.plan_id)
        completed_tasks = [t for t in plan_tasks if t.status == "COMPLETED"]
        durations = [
            float((t.result or {}).get("duration_ms", 0.0)) for t in completed_tasks
        ]
        twinnode_metrics = TwinNodeExecutionMetrics(
            tasks_total=len(plan_tasks),
            tasks_completed=len(completed_tasks),
            tasks_failed_or_pending=len(plan_tasks) - len(completed_tasks),
            avg_duration_ms=round(sum(durations) / max(1, len(durations)), 2) if durations else 0.0,
            total_retries=sum(t.retry_count for t in plan_tasks),
            executed_nodes=sorted({t.assigned_node_id for t in completed_tasks}),
        )

        deltas = {
            "congested_cell_minutes_delta": round(
                intervention_metrics.congested_cell_minutes - baseline_metrics.congested_cell_minutes, 2
            ),
            "peak_utilisation_pct_delta": round(
                intervention_metrics.peak_utilisation_pct - baseline_metrics.peak_utilisation_pct, 2
            ),
            "simulated_latency_p95_ms_delta": round(
                intervention_metrics.simulated_latency_p95_ms - baseline_metrics.simulated_latency_p95_ms, 2
            ),
            "total_queued_mbps_delta": round(
                intervention_metrics.total_queued_mbps - baseline_metrics.total_queued_mbps, 2
            ),
            "total_unserved_mbps_delta": round(
                intervention_metrics.total_unserved_mbps - baseline_metrics.total_unserved_mbps, 2
            ),
            "total_energy_units_delta": round(
                intervention_metrics.total_energy_units - baseline_metrics.total_energy_units, 2
            ),
        }

        result = VerificationResultResponse(
            verification_id=uuid4(),
            baseline_run_id=baseline_run_id,
            intervention_run_id=intervention_run_id,
            plan_id=plan.plan_id,
            event_id=effective_event_id,
            seed=sim_run.seed,
            initial_state_version=plan.state_version,
            horizon_ticks=request.horizon_ticks,
            config_match=True,
            baseline=baseline_metrics,
            intervention=intervention_metrics,
            deltas=deltas,
            twinnode_metrics=twinnode_metrics,
            created_at=utc_now(),
        )
        self.verification_repo.save_verification(result)
        self.audit.log(
            actor="system:verifier",
            action="verification.completed",
            entity_type="verification",
            entity_id=str(result.verification_id),
            state_version=plan.state_version,
            details={
                "plan_id": str(plan.plan_id),
                "seed": sim_run.seed,
                "deltas": deltas,
                "twinnode_tasks_completed": twinnode_metrics.tasks_completed,
            },
        )
        await self.ws.broadcast(
            "verification.completed",
            {
                "verification_id": str(result.verification_id),
                "plan_id": str(plan.plan_id),
                "seed": sim_run.seed,
                "deltas": deltas,
            },
        )
        return result
