from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException

from apps.api.app.api.websocket import ConnectionManager
from apps.api.app.core.database import utc_now
from apps.api.app.core.events import AuditLogger
from apps.api.app.modules.scenario_engine.event_impact import (
    EventMissingCoordinatesError,
    EventNotConfirmedError,
    calculate_event_impact,
)
from apps.api.app.repositories.events import EventRepository
from apps.api.app.repositories.networks import NetworkRepository
from apps.api.app.repositories.plans import PlanRepository
from apps.api.app.repositories.simulations import SimulationRepository, SimulationRunRow
from apps.api.app.schemas.events import EventImpactRequest, EventImpactResponse
from apps.api.app.schemas.networks import CellOperationalState
from apps.api.app.schemas.simulations import (
    CellTelemetryRecord,
    FaultInjectRequest,
    SimulationCreateRequest,
    SimulationEventInjectRequest,
    SimulationStateResponse,
    SimulationSummary,
)
from simulation.tick_engine import advance_sim_clock, compute_tick_telemetry


class SimulationManager:
    """Authoritative digital twin manager coordinating simulation runs, ticks, and faults."""

    def __init__(
        self,
        *,
        network_repo: NetworkRepository,
        sim_repo: SimulationRepository,
        event_repo: EventRepository,
        plan_repo: PlanRepository,
        audit: AuditLogger,
        ws_manager: ConnectionManager,
    ) -> None:
        self.network_repo = network_repo
        self.sim_repo = sim_repo
        self.event_repo = event_repo
        self.plan_repo = plan_repo
        self.audit = audit
        self.ws = ws_manager
        self._runner_tasks: dict[UUID, asyncio.Task[None]] = {}

    def _get_run_or_404(self, simulation_id: UUID) -> SimulationRunRow:
        run = self.sim_repo.get_run(simulation_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Simulation {simulation_id} not found")
        return run

    def _build_uplift_map(self, run: SimulationRunRow) -> dict[str, float]:
        if run.active_event_id is None:
            return {}
        impact = self.event_repo.get_impact(run.active_event_id, run.id)
        if impact is None:
            return {}
        # Base uplift before simulation run intensity override
        event = self.event_repo.get_event(run.active_event_id)
        base_int = event.intensity if event else 1.0
        scale = run.event_intensity / max(0.1, base_int)
        return {
            item.cell_id: round(item.estimated_additional_demand_mbps * scale, 4)
            for item in impact.affected_cells
        }

    def _compute_and_persist_tick(
        self,
        run: SimulationRunRow,
        *,
        tick: int,
        state_version: int,
        sim_time_utc: datetime,
    ) -> tuple[list[CellTelemetryRecord], SimulationSummary]:
        cells = self.network_repo.get_cells(run.network_id)
        edges = self.network_repo.get_edges(run.network_id)
        uplift_map = self._build_uplift_map(run)
        telemetry, summary = compute_tick_telemetry(
            run_id=run.id,
            seed=run.seed,
            tick=tick,
            state_version=state_version,
            sim_time_utc=sim_time_utc,
            cells=cells,
            edges=edges,
            event_uplift_by_cell=uplift_map,
            event_intensity=1.0,  # Already scaled inside _build_uplift_map
            applied_transfers=run.applied_transfers,
            faults=run.faults,
        )
        self.sim_repo.save_telemetry(telemetry)
        return telemetry, summary

    def _summarize_telemetry(self, telemetry: list[CellTelemetryRecord]) -> SimulationSummary:
        active_lat = [t.simulated_latency_ms for t in telemetry if t.cell_state == "ACTIVE"]
        return SimulationSummary(
            total_cells=len(telemetry),
            active_cells=sum(1 for t in telemetry if t.cell_state == "ACTIVE"),
            standby_cells=sum(1 for t in telemetry if t.cell_state == "STANDBY"),
            failed_cells=sum(1 for t in telemetry if t.cell_state == "FAILED"),
            congested_cells=sum(
                1
                for t in telemetry
                if t.cell_state == "FAILED"
                or t.utilisation_pct >= 85.0
                or t.queued_mbps > 0.0
                or t.unserved_mbps > 0.0
            ),
            total_demand_mbps=round(sum(t.demand_mbps for t in telemetry), 2),
            total_served_mbps=round(sum(t.served_mbps for t in telemetry), 2),
            total_queued_mbps=round(sum(t.queued_mbps for t in telemetry), 2),
            total_unserved_mbps=round(sum(t.unserved_mbps for t in telemetry), 2),
            peak_utilisation_pct=round(max((t.utilisation_pct for t in telemetry), default=0.0), 2),
            mean_simulated_latency_ms=round(sum(active_lat) / max(1, len(active_lat)), 2),
        )

    def create_simulation(self, request: SimulationCreateRequest) -> SimulationStateResponse:
        network = self.network_repo.get_current_network()
        if network is None:
            raise HTTPException(status_code=409, detail="No network seeded yet. Call POST /api/v1/networks/seed first.")

        # Restore network cell states to initial_state for clean run
        self.network_repo.reset_cell_states(network.network_id)
        run_id = uuid4()
        start_time = request.start_time_utc
        if start_time is None:
            now = utc_now()
            start_time = datetime(now.year, now.month, now.day, 13, 0, tzinfo=timezone.utc)

        run = self.sim_repo.create_run(
            run_id=run_id,
            network_id=network.network_id,
            seed=request.seed,
            config={
                "step_minutes": request.step_minutes,
                "tick_interval_seconds": request.tick_interval_seconds,
            },
            sim_time_utc=start_time,
        )
        telemetry, summary = self._compute_and_persist_tick(
            run, tick=0, state_version=run.state_version, sim_time_utc=run.sim_time_utc
        )
        self.audit.log(
            actor="operator",
            action="simulation.created",
            entity_type="simulation_run",
            entity_id=str(run.id),
            state_version=run.state_version,
            details={"seed": run.seed, "network_id": str(run.network_id)},
        )
        return self._to_state_response(run, telemetry, summary)

    def get_state(self, simulation_id: UUID) -> SimulationStateResponse:
        run = self._get_run_or_404(simulation_id)
        telemetry = self.sim_repo.get_tick_telemetry(run.id, run.tick)
        if not telemetry:
            telemetry, summary = self._compute_and_persist_tick(
                run, tick=run.tick, state_version=run.state_version, sim_time_utc=run.sim_time_utc
            )
        else:
            summary = self._summarize_telemetry(telemetry)
        return self._to_state_response(run, telemetry, summary)

    async def step_simulation(self, simulation_id: UUID) -> SimulationStateResponse:
        run = self._get_run_or_404(simulation_id)
        step_min = int(run.config.get("step_minutes", 5))
        new_tick = run.tick + 1
        new_sv = run.state_version + 1
        new_time = advance_sim_clock(run.sim_time_utc, step_minutes=step_min)

        updated = self.sim_repo.update_run_fields(
            run.id,
            tick=new_tick,
            state_version=new_sv,
            sim_time_utc=new_time,
        )
        telemetry, summary = self._compute_and_persist_tick(
            updated, tick=new_tick, state_version=new_sv, sim_time_utc=new_time
        )
        self.audit.log(
            actor="system:twin",
            action="simulation.step",
            entity_type="simulation_run",
            entity_id=str(updated.id),
            state_version=new_sv,
            details={"tick": new_tick, "congested_cells": summary.congested_cells},
        )
        await self.ws.broadcast(
            "tick.updated",
            {
                "simulation_id": str(updated.id),
                "tick": new_tick,
                "state_version": new_sv,
                "summary": summary.model_dump(mode="json"),
            },
        )
        return self._to_state_response(updated, telemetry, summary)

    async def start_simulation(self, simulation_id: UUID) -> SimulationStateResponse:
        run = self._get_run_or_404(simulation_id)
        updated = self.sim_repo.update_run_fields(run.id, status="RUNNING")
        existing_task = self._runner_tasks.get(simulation_id)
        if existing_task is None or existing_task.done():
            self._runner_tasks[simulation_id] = asyncio.create_task(
                self._run_loop(simulation_id)
            )
        return self.get_state(updated.id)

    async def _run_loop(self, simulation_id: UUID) -> None:
        try:
            while True:
                run = self.sim_repo.get_run(simulation_id)
                if run is None or run.status != "RUNNING":
                    break
                interval = float(run.config.get("tick_interval_seconds", 1.5))
                await asyncio.sleep(interval)
                run_after = self.sim_repo.get_run(simulation_id)
                if run_after is None or run_after.status != "RUNNING":
                    break
                await self.step_simulation(simulation_id)
        except asyncio.CancelledError:
            pass

    async def pause_simulation(self, simulation_id: UUID) -> SimulationStateResponse:
        run = self._get_run_or_404(simulation_id)
        task = self._runner_tasks.pop(simulation_id, None)
        if task is not None and not task.done():
            task.cancel()
        updated = self.sim_repo.update_run_fields(run.id, status="PAUSED")
        self.audit.log(
            actor="operator",
            action="simulation.paused",
            entity_type="simulation_run",
            entity_id=str(updated.id),
            state_version=updated.state_version,
        )
        return self.get_state(updated.id)

    async def reset_simulation(self, simulation_id: UUID) -> SimulationStateResponse:
        run = self._get_run_or_404(simulation_id)
        task = self._runner_tasks.pop(simulation_id, None)
        if task is not None and not task.done():
            task.cancel()

        # Restore initial seeded cell states, clear telemetry & active injections, mark open plans STALE
        self.network_repo.reset_cell_states(run.network_id)
        self.sim_repo.clear_telemetry(run.id)
        self.plan_repo.mark_open_plans_stale(run.id)

        now = utc_now()
        reset_time = datetime(now.year, now.month, now.day, 13, 0, tzinfo=timezone.utc)
        new_sv = run.state_version + 1
        updated = self.sim_repo.update_run_fields(
            run.id,
            tick=0,
            state_version=new_sv,
            status="PAUSED",
            active_event_id=None,
            event_intensity=1.0,
            attendance_scenario="EXPECTED",
            faults={},
            applied_transfers=[],
            sim_time_utc=reset_time,
        )
        telemetry, summary = self._compute_and_persist_tick(
            updated, tick=0, state_version=new_sv, sim_time_utc=reset_time
        )
        self.audit.log(
            actor="operator",
            action="simulation.reset",
            entity_type="simulation_run",
            entity_id=str(updated.id),
            state_version=new_sv,
            details={"seed": updated.seed},
        )
        await self.ws.broadcast(
            "tick.updated",
            {
                "simulation_id": str(updated.id),
                "tick": 0,
                "state_version": new_sv,
                "reset": True,
                "summary": summary.model_dump(mode="json"),
            },
        )
        return self._to_state_response(updated, telemetry, summary)

    async def inject_event(
        self, simulation_id: UUID, request: SimulationEventInjectRequest
    ) -> tuple[SimulationStateResponse, EventImpactResponse]:
        run = self._get_run_or_404(simulation_id)
        event = self.event_repo.get_event(request.event_id)
        if event is None:
            raise HTTPException(status_code=404, detail=f"Event {request.event_id} not found")

        cells = self.network_repo.get_cells(run.network_id)
        try:
            impact = calculate_event_impact(
                event=event,
                cells=cells,
                request=EventImpactRequest(
                    simulation_id=simulation_id,
                    influence_radius_km=request.influence_radius_km,
                    attendance_scenario=request.attendance_scenario,
                ),
            )
        except EventNotConfirmedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except EventMissingCoordinatesError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        self.event_repo.save_impact(impact)
        new_sv = run.state_version + 1
        updated = self.sim_repo.update_run_fields(
            run.id,
            state_version=new_sv,
            active_event_id=event.event_id,
            event_intensity=request.intensity,
            attendance_scenario=request.attendance_scenario,
        )
        telemetry, summary = self._compute_and_persist_tick(
            updated, tick=updated.tick, state_version=new_sv, sim_time_utc=updated.sim_time_utc
        )
        self.audit.log(
            actor="operator",
            action="simulation.event_injected",
            entity_type="simulation_run",
            entity_id=str(updated.id),
            state_version=new_sv,
            details={
                "event_id": str(event.event_id),
                "intensity": request.intensity,
                "affected_cells": len(impact.affected_cells),
            },
        )
        await self.ws.broadcast(
            "event.mapped",
            {
                "simulation_id": str(updated.id),
                "event_id": str(event.event_id),
                "affected_cell_ids": [c.cell_id for c in impact.affected_cells],
                "state_version": new_sv,
            },
        )
        return self._to_state_response(updated, telemetry, summary), impact

    async def inject_fault(
        self, simulation_id: UUID, request: FaultInjectRequest
    ) -> SimulationStateResponse:
        run = self._get_run_or_404(simulation_id)
        cells = self.network_repo.get_cells(run.network_id)
        cell_map = {c.cell_id: c for c in cells}
        if request.cell_id not in cell_map:
            raise HTTPException(status_code=404, detail=f"Cell {request.cell_id} not found")

        faults = dict(run.faults)
        if request.active:
            faults[request.cell_id] = {
                "fault_type": request.fault_type,
                "severity": request.severity,
                "active": True,
            }
            if request.fault_type == "CELL_FAILURE":
                self.network_repo.update_cell_states(run.network_id, {request.cell_id: "FAILED"})
        else:
            faults.pop(request.cell_id, None)
            if request.fault_type == "CELL_FAILURE":
                orig_state = cell_map[request.cell_id].initial_state
                self.network_repo.update_cell_states(run.network_id, {request.cell_id: orig_state})

        new_sv = run.state_version + 1
        updated = self.sim_repo.update_run_fields(
            run.id, state_version=new_sv, faults=faults
        )
        telemetry, summary = self._compute_and_persist_tick(
            updated, tick=updated.tick, state_version=new_sv, sim_time_utc=updated.sim_time_utc
        )
        self.audit.log(
            actor="operator",
            action="simulation.fault_updated",
            entity_type="simulation_run",
            entity_id=str(updated.id),
            state_version=new_sv,
            details=request.model_dump(mode="json"),
        )
        await self.ws.broadcast(
            "tick.updated",
            {
                "simulation_id": str(updated.id),
                "tick": updated.tick,
                "state_version": new_sv,
                "summary": summary.model_dump(mode="json"),
            },
        )
        return self._to_state_response(updated, telemetry, summary)

    async def apply_plan_actions(
        self,
        simulation_id: UUID,
        *,
        cell_activations: list[str],
        transfers: list[dict[str, Any]],
    ) -> SimulationStateResponse:
        run = self._get_run_or_404(simulation_id)
        if cell_activations:
            updates: dict[str, CellOperationalState] = {cid: "ACTIVE" for cid in cell_activations}
            self.network_repo.update_cell_states(run.network_id, {k: str(v) for k, v in updates.items()})

        merged_transfers = list(run.applied_transfers) + transfers
        new_sv = run.state_version + 1
        updated = self.sim_repo.update_run_fields(
            run.id,
            state_version=new_sv,
            applied_transfers=merged_transfers,
        )
        telemetry, summary = self._compute_and_persist_tick(
            updated, tick=updated.tick, state_version=new_sv, sim_time_utc=updated.sim_time_utc
        )
        await self.ws.broadcast(
            "tick.updated",
            {
                "simulation_id": str(updated.id),
                "tick": updated.tick,
                "state_version": new_sv,
                "summary": summary.model_dump(mode="json"),
            },
        )
        return self._to_state_response(updated, telemetry, summary)

    async def shutdown(self) -> None:
        for task in list(self._runner_tasks.values()):
            if not task.done():
                task.cancel()
        self._runner_tasks.clear()

    def _to_state_response(
        self,
        run: SimulationRunRow,
        telemetry: list[CellTelemetryRecord],
        summary: SimulationSummary,
    ) -> SimulationStateResponse:
        return SimulationStateResponse(
            simulation_id=run.id,
            network_id=run.network_id,
            seed=run.seed,
            tick=run.tick,
            state_version=run.state_version,
            status=run.status,
            active_event_id=run.active_event_id,
            event_intensity=run.event_intensity,
            attendance_scenario=run.attendance_scenario,
            faults=run.faults,
            applied_transfers=run.applied_transfers,
            sim_time_utc=run.sim_time_utc,
            summary=summary,
            telemetry=telemetry,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
