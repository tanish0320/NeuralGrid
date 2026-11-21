from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException

from apps.api.app.api.websocket import ConnectionManager
from apps.api.app.config import Settings
from apps.api.app.core.database import utc_now
from apps.api.app.core.events import AuditLogger
from apps.api.app.modules.digital_twin.engine import SimulationManager
from apps.api.app.modules.planner.optimizer import ConstrainedPlanner
from apps.api.app.repositories.networks import NetworkRepository
from apps.api.app.repositories.plans import PlanRepository
from apps.api.app.repositories.twinnode import TwinNodeRepository
from apps.api.app.schemas.plans import (
    PlanApproveRequest,
    PlanExecuteRequest,
    PlanExecutionResponse,
    PlanGenerateRequest,
    PlanRecord,
    PlanRejectRequest,
)
from apps.api.app.schemas.twinnode import TaskCreateRequest

if TYPE_CHECKING:
    from agents.twinnode.controller.node_manager import TwinNodeController


class GovernanceService:
    """Enforces plan approval lifecycle, expiry, rejection, and state_version checks (FR-009)."""

    def __init__(
        self,
        *,
        settings: Settings,
        sim_manager: SimulationManager,
        network_repo: NetworkRepository,
        plan_repo: PlanRepository,
        twinnode_repo: TwinNodeRepository,
        twinnode_controller: "TwinNodeController",
        audit: AuditLogger,
        ws_manager: ConnectionManager,
    ) -> None:
        self.settings = settings
        self.sim_manager = sim_manager
        self.network_repo = network_repo
        self.plan_repo = plan_repo
        self.twinnode_repo = twinnode_repo
        self.twinnode_controller = twinnode_controller
        self.audit = audit
        self.ws = ws_manager
        self.planner = ConstrainedPlanner(settings)

    async def generate_plan(self, request: PlanGenerateRequest) -> PlanRecord:
        sim_state = self.sim_manager.get_state(request.simulation_id)
        if request.state_version != sim_state.state_version:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"State version mismatch: requested state_version={request.state_version}, "
                    f"current simulation state_version={sim_state.state_version}. Refresh state first."
                ),
            )

        cells = self.network_repo.get_cells(sim_state.network_id)
        edges = self.network_repo.get_edges(sim_state.network_id)
        nodes = self.twinnode_repo.list_nodes()
        existing = self.plan_repo.list_plans(sim_state.simulation_id)
        next_version = (max((p.version for p in existing), default=0) + 1)

        plan = self.planner.generate_plan(
            sim_state=sim_state,
            cells=cells,
            edges=edges,
            nodes=nodes,
            request=request,
            plan_version=next_version,
        )
        if not all(c.passed for c in plan.constraints_checked):
            failed = [c.name for c in plan.constraints_checked if not c.passed]
            raise HTTPException(
                status_code=422,
                detail=f"Planner hard constraints failed: {failed}",
            )

        saved = self.plan_repo.save_plan(plan)
        self.audit.log(
            actor="system:planner",
            action="plan.generated",
            entity_type="plan",
            entity_id=str(saved.plan_id),
            state_version=saved.state_version,
            details={
                "simulation_id": str(saved.simulation_id),
                "event_id": str(saved.event_id) if saved.event_id else None,
                "action_count": len(saved.actions),
                "solver_method": saved.solver_method,
            },
        )
        await self.ws.broadcast(
            "plan.pending_approval",
            {
                "plan_id": str(saved.plan_id),
                "simulation_id": str(saved.simulation_id),
                "state_version": saved.state_version,
                "action_count": len(saved.actions),
            },
        )
        return saved

    def get_plan(self, plan_id: UUID) -> PlanRecord:
        plan = self.plan_repo.get_plan(plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
        return plan

    def list_plans(self, simulation_id: UUID | None = None) -> list[PlanRecord]:
        return self.plan_repo.list_plans(simulation_id)

    async def approve_plan(self, plan_id: UUID, request: PlanApproveRequest) -> PlanRecord:
        plan = self.get_plan(plan_id)
        if plan.status == "REJECTED":
            raise HTTPException(status_code=409, detail="Rejected plans cannot be approved.")
        if plan.status in ("COMPLETED", "EXECUTING", "FAILED"):
            raise HTTPException(status_code=409, detail=f"Plan in terminal/active state '{plan.status}' cannot be approved.")
        if utc_now() > plan.expires_at:
            self.plan_repo.update_plan_status(plan.plan_id, "EXPIRED")
            raise HTTPException(status_code=409, detail="Plan has expired; regenerate a fresh plan.")
        if request.plan_version != plan.version:
            raise HTTPException(
                status_code=409,
                detail=f"Plan version mismatch: expected {plan.version}, got {request.plan_version}.",
            )

        sim_state = self.sim_manager.get_state(plan.simulation_id)
        if request.state_version != plan.state_version or sim_state.state_version != plan.state_version:
            self.plan_repo.update_plan_status(plan.plan_id, "STALE")
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Plan is STALE: plan state_version={plan.state_version}, "
                    f"requested={request.state_version}, current simulation={sim_state.state_version}."
                ),
            )

        self.plan_repo.record_approval(
            plan_id=plan.plan_id,
            operator_id=request.operator_id,
            decision="APPROVED",
            reason=request.notes,
            state_version=plan.state_version,
        )
        approved = self.plan_repo.update_plan_status(plan.plan_id, "APPROVED")
        self.audit.log(
            actor=request.operator_id,
            action="plan.approved",
            entity_type="plan",
            entity_id=str(approved.plan_id),
            state_version=approved.state_version,
            details={"notes": request.notes},
        )
        await self.ws.broadcast(
            "plan.approved",
            {
                "plan_id": str(approved.plan_id),
                "operator_id": request.operator_id,
                "state_version": approved.state_version,
            },
        )
        return approved

    async def reject_plan(self, plan_id: UUID, request: PlanRejectRequest) -> PlanRecord:
        plan = self.get_plan(plan_id)
        if plan.status in ("COMPLETED", "EXECUTING"):
            raise HTTPException(status_code=409, detail=f"Plan in state '{plan.status}' cannot be rejected.")

        self.plan_repo.record_approval(
            plan_id=plan.plan_id,
            operator_id=request.operator_id,
            decision="REJECTED",
            reason=request.reason,
            state_version=plan.state_version,
        )
        rejected = self.plan_repo.update_plan_status(plan.plan_id, "REJECTED")
        self.audit.log(
            actor=request.operator_id,
            action="plan.rejected",
            entity_type="plan",
            entity_id=str(rejected.plan_id),
            state_version=rejected.state_version,
            details={"reason": request.reason},
        )
        return rejected

    async def execute_plan(self, plan_id: UUID, request: PlanExecuteRequest) -> PlanExecutionResponse:
        plan = self.get_plan(plan_id)

        if plan.status == "REJECTED":
            raise HTTPException(status_code=409, detail="Rejected plan can never execute.")
        if plan.status == "STALE":
            raise HTTPException(status_code=409, detail="Stale plan cannot execute; regenerate plan.")
        if plan.status == "EXPIRED" or utc_now() > plan.expires_at:
            self.plan_repo.update_plan_status(plan.plan_id, "EXPIRED")
            raise HTTPException(status_code=409, detail="Expired plan cannot execute; regenerate plan.")
        if plan.status != "APPROVED":
            raise HTTPException(
                status_code=409,
                detail=f"Plan status is '{plan.status}'; explicit human approval is required before execution.",
            )

        sim_state = self.sim_manager.get_state(plan.simulation_id)
        if sim_state.state_version != plan.state_version:
            self.plan_repo.update_plan_status(plan.plan_id, "STALE")
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Plan state_version={plan.state_version} is stale against current "
                    f"simulation state_version={sim_state.state_version}."
                ),
            )
        if request.expected_state_version is not None and request.expected_state_version != sim_state.state_version:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Expected state_version={request.expected_state_version} does not match "
                    f"current simulation state_version={sim_state.state_version}."
                ),
            )

        self.plan_repo.update_plan_status(plan.plan_id, "EXECUTING")
        activations: list[str] = []
        transfers: list[dict[str, object]] = []
        compute_actions = []

        for action in plan.actions:
            if action.action_type == "activate_standby_cell":
                activations.append(action.target_id)
            elif action.action_type == "reallocate_load":
                transfers.append(
                    {
                        "source_id": action.source_id,
                        "target_id": action.target_id,
                        "amount": action.amount,
                        "plan_id": str(plan.plan_id),
                    }
                )
            elif action.action_type == "dispatch_compute_task":
                compute_actions.append(action)

        dispatched_task_ids: list[UUID] = []
        try:
            new_sim_state = await self.sim_manager.apply_plan_actions(
                plan.simulation_id,
                cell_activations=activations,
                transfers=transfers,
            )

            for action in compute_actions:
                task_type = str(action.params.get("task_type", "counterfactual_batch"))
                task = await self.twinnode_controller.create_and_dispatch_task(
                    TaskCreateRequest(
                        idempotency_key=f"plan-{plan.plan_id}-action-{action.action_id}",
                        task_type=task_type,  # type: ignore[arg-type]
                        origin_node_id=action.source_id,
                        assigned_node_id=action.target_id,
                        plan_id=plan.plan_id,
                        simulation_id=plan.simulation_id,
                        event_id=plan.event_id,
                        seed=plan.seed,
                        payload={
                            "plan_id": str(plan.plan_id),
                            "simulation_id": str(plan.simulation_id),
                            "horizon_ticks": 6,
                            "transfers": transfers,
                            "cell_activations": activations,
                        },
                    )
                )
                dispatched_task_ids.append(task.task_id)

            completed = self.plan_repo.update_plan_status(plan.plan_id, "COMPLETED")
        except HTTPException:
            self.plan_repo.update_plan_status(plan.plan_id, "FAILED")
            raise
        except Exception as exc:
            self.plan_repo.update_plan_status(plan.plan_id, "FAILED")
            raise HTTPException(status_code=500, detail=f"Plan execution failed: {exc}") from exc

        self.audit.log(
            actor=request.operator_id,
            action="plan.executed",
            entity_type="plan",
            entity_id=str(completed.plan_id),
            state_version=new_sim_state.state_version,
            details={
                "dispatched_task_ids": [str(tid) for tid in dispatched_task_ids],
                "activations": activations,
                "transfer_count": len(transfers),
            },
        )
        await self.ws.broadcast(
            "plan.executed",
            {
                "plan_id": str(completed.plan_id),
                "simulation_id": str(completed.simulation_id),
                "new_state_version": new_sim_state.state_version,
                "dispatched_task_ids": [str(tid) for tid in dispatched_task_ids],
            },
        )
        return PlanExecutionResponse(
            plan=completed,
            new_simulation_state_version=new_sim_state.state_version,
            dispatched_task_ids=dispatched_task_ids,
            message="Approved plan executed in simulator; eligible remote TwinNode compute tasks dispatched.",
        )
