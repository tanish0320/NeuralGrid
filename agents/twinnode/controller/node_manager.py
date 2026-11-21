from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException

from apps.api.app.api.websocket import ConnectionManager
from apps.api.app.config import Settings
from apps.api.app.core.database import utc_now
from apps.api.app.core.events import AuditLogger
from apps.api.app.core.security import ALLOWED_TASK_TYPES, compute_canonical_checksum
from apps.api.app.repositories.twinnode import TwinNodeRepository
from apps.api.app.schemas.twinnode import (
    HeartbeatCommandResponse,
    NodeCommandRequest,
    NodeHeartbeatRequest,
    NodeRecord,
    NodeRegisterRequest,
    NodeStatus,
    TaskAckRequest,
    TaskCreateRequest,
    TaskRecord,
    TaskResultSubmitRequest,
)


class TwinNodeController:
    """Authoritative TwinNode lifecycle, heartbeat monitor, and allowlisted task dispatcher."""

    def __init__(
        self,
        *,
        settings: Settings,
        repo: TwinNodeRepository,
        audit: AuditLogger,
        ws_manager: ConnectionManager,
    ) -> None:
        self.settings = settings
        self.repo = repo
        self.audit = audit
        self.ws = ws_manager

    def _get_node_or_404(self, node_id: str) -> NodeRecord:
        node = self.repo.get_node(node_id)
        if node is None:
            raise HTTPException(status_code=404, detail=f"Node '{node_id}' is not registered")
        return node

    def _get_task_or_404(self, task_id: UUID) -> TaskRecord:
        task = self.repo.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return task

    async def register_node(
        self, request: NodeRegisterRequest, *, client_ip: str = "127.0.0.1"
    ) -> NodeRecord:
        node = self.repo.upsert_node(
            node_id=request.node_id,
            hostname=request.hostname,
            ip_last_seen=client_ip,
            agent_url=request.agent_url,
            status="STANDBY",
            agent_version=request.agent_version,
            capabilities=list(request.capabilities),
            worker_slots=request.worker_slots,
            capacity_estimate_score=request.capacity_estimate_score,
        )
        self.audit.log(
            actor=request.node_id,
            action="node.registered",
            entity_type="physical_node",
            entity_id=request.node_id,
            details={
                "hostname": request.hostname,
                "ip": client_ip,
                "status": node.status,
                "agent_url": request.agent_url,
            },
        )
        await self.ws.broadcast(
            "node.online",
            {
                "node_id": node.node_id,
                "hostname": node.hostname,
                "status": node.status,
                "ip_last_seen": node.ip_last_seen,
            },
        )
        return node

    async def process_heartbeat(
        self,
        node_id: str,
        request: NodeHeartbeatRequest,
        *,
        client_ip: str | None = None,
    ) -> HeartbeatCommandResponse:
        existing = self._get_node_or_404(node_id)
        prev_status = existing.status
        clear_cmd = False
        new_status: NodeStatus = existing.status

        if existing.status == "ACTIVATING":
            if request.worker_active:
                new_status = "ACTIVE"
                clear_cmd = True
        elif existing.status == "DRAINING":
            if request.active_tasks == 0 and not request.worker_active:
                new_status = "STANDBY"
                clear_cmd = True
        elif existing.status == "OFFLINE":
            new_status = "ACTIVE" if request.worker_active else "STANDBY"
            clear_cmd = True
        elif existing.status == "STANDBY" and existing.desired_command == "ACTIVATE" and request.worker_active:
            new_status = "ACTIVE"
            clear_cmd = True
        elif existing.status == "ACTIVE" and not request.worker_active and existing.desired_command == "STANDBY":
            new_status = "STANDBY"
            clear_cmd = True

        updated = self.repo.record_heartbeat(
            node_id=node_id,
            cpu_pct=request.cpu_pct,
            memory_pct=request.memory_pct,
            worker_active=request.worker_active,
            worker_slots=request.worker_slots,
            active_tasks=request.active_tasks,
            local_rtt_ms=request.local_rtt_ms,
            new_status=new_status,
            ip_last_seen=request.ip_address or client_ip,
            agent_url=request.agent_url,
            clear_desired_command=clear_cmd,
        )

        if new_status != prev_status:
            await self.ws.broadcast(
                "node.state_changed",
                {"node_id": node_id, "previous": prev_status, "status": new_status},
            )
            self.audit.log(
                actor=node_id,
                action="node.state_changed",
                entity_type="physical_node",
                entity_id=node_id,
                details={"previous": prev_status, "status": new_status},
            )

        await self.ws.broadcast(
            "node.heartbeat",
            {
                "node_id": node_id,
                "status": updated.status,
                "cpu_pct": request.cpu_pct,
                "memory_pct": request.memory_pct,
                "local_rtt_ms": request.local_rtt_ms,
                "worker_active": request.worker_active,
            },
        )

        desired = updated.desired_command or "NONE"
        if desired not in ("NONE", "ACTIVATE", "STANDBY", "DRAIN"):
            desired = "NONE"

        # Deliver ASSIGNED tasks on heartbeat ONLY when node is genuinely ACTIVE
        pending_tasks = (
            self.repo.list_assigned_tasks_for_node(node_id)
            if updated.status == "ACTIVE" and updated.worker_active
            else []
        )
        return HeartbeatCommandResponse(
            node=updated,
            desired_command=desired,  # type: ignore[arg-type]
            pending_tasks=pending_tasks,
        )

    async def _push_agent_control(
        self, node: NodeRecord, command_path: str
    ) -> dict[str, Any] | None:
        if not node.agent_url:
            return None
        token = self.settings.node_tokens_map.get(node.node_id, "")
        url = f"{node.agent_url.rstrip('/')}{command_path}"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.post(url, headers={"X-Node-Token": token})
                if resp.status_code == 200:
                    return resp.json()
        except httpx.HTTPError:
            return None
        return None

    async def activate_node(self, node_id: str, request: NodeCommandRequest) -> NodeRecord:
        node = self._get_node_or_404(node_id)
        if node.status == "OFFLINE":
            raise HTTPException(
                status_code=409,
                detail=f"Node '{node_id}' is OFFLINE; wait for live heartbeat before activation.",
            )

        # Enter ACTIVATING first; do not mark ACTIVE until worker readiness is confirmed
        activating = self.repo.update_node_status(
            node_id, "ACTIVATING", desired_command="ACTIVATE"
        )
        await self.ws.broadcast(
            "node.state_changed",
            {"node_id": node_id, "previous": node.status, "status": "ACTIVATING"},
        )

        push_resp = await self._push_agent_control(activating, "/control/activate")
        if push_resp and push_resp.get("worker_active") is True:
            activating = self.repo.update_node_status(
                node_id, "ACTIVE", desired_command="NONE", worker_active=True
            )
            await self.ws.broadcast(
                "node.state_changed",
                {"node_id": node_id, "previous": "ACTIVATING", "status": "ACTIVE"},
            )

        self.audit.log(
            actor=request.operator_id,
            action="node.activate_requested",
            entity_type="physical_node",
            entity_id=node_id,
            details={"resulting_status": activating.status},
        )
        return activating

    async def standby_node(self, node_id: str, request: NodeCommandRequest) -> NodeRecord:
        node = self._get_node_or_404(node_id)
        updated = self.repo.update_node_status(
            node_id, "STANDBY", desired_command="STANDBY", worker_active=False
        )
        await self._push_agent_control(updated, "/control/standby")
        self.audit.log(
            actor=request.operator_id,
            action="node.standby",
            entity_type="physical_node",
            entity_id=node_id,
            details={"previous": node.status},
        )
        await self.ws.broadcast(
            "node.state_changed",
            {"node_id": node_id, "previous": node.status, "status": "STANDBY"},
        )
        return updated

    async def drain_node(self, node_id: str, request: NodeCommandRequest) -> NodeRecord:
        node = self._get_node_or_404(node_id)
        updated = self.repo.update_node_status(
            node_id, "DRAINING", desired_command="DRAIN"
        )
        await self._push_agent_control(updated, "/control/drain")
        self.audit.log(
            actor=request.operator_id,
            action="node.drain",
            entity_type="physical_node",
            entity_id=node_id,
            details={"previous": node.status},
        )
        await self.ws.broadcast(
            "node.state_changed",
            {"node_id": node_id, "previous": node.status, "status": "DRAINING"},
        )
        return updated

    async def create_and_dispatch_task(self, request: TaskCreateRequest) -> TaskRecord:
        if request.task_type not in ALLOWED_TASK_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Task type '{request.task_type}' is not in allowlist {sorted(ALLOWED_TASK_TYPES)}",
            )

        # Idempotency check: duplicate key must not execute task twice
        existing = self.repo.get_task_by_idempotency_key(request.idempotency_key)
        if existing is not None:
            return existing

        node = self._get_node_or_404(request.assigned_node_id)
        if node.status != "ACTIVE" or not node.worker_active:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Node '{node.node_id}' is in status '{node.status}' (worker_active={node.worker_active}); "
                    "cannot dispatch task until node is ACTIVE."
                ),
            )
        if node.heartbeat_age_seconds > self.settings.twinnode_heartbeat_timeout_seconds:
            raise HTTPException(
                status_code=409,
                detail=f"Node '{node.node_id}' heartbeat is stale ({node.heartbeat_age_seconds:.1f}s).",
            )

        inflight = self.repo.count_active_tasks_for_node(node.node_id)
        if inflight >= node.worker_slots:
            raise HTTPException(
                status_code=409,
                detail=f"Node '{node.node_id}' has no free worker slots ({inflight}/{node.worker_slots}).",
            )

        now = utc_now()
        lease_until = now + timedelta(seconds=self.settings.twinnode_task_lease_seconds)
        task = TaskRecord(
            task_id=uuid4(),
            idempotency_key=request.idempotency_key,
            task_type=request.task_type,
            schema_version=request.schema_version,
            status="ASSIGNED",
            origin_node_id=request.origin_node_id,
            assigned_node_id=node.node_id,
            plan_id=request.plan_id,
            simulation_id=request.simulation_id,
            event_id=request.event_id,
            seed=request.seed,
            payload=request.payload,
            result=None,
            checksum=None,
            retry_count=0,
            lease_until=lease_until,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        saved = self.repo.create_task(task)
        self.audit.log(
            actor=request.origin_node_id,
            action="task.assigned",
            entity_type="task",
            entity_id=str(saved.task_id),
            details={
                "task_type": saved.task_type,
                "assigned_node_id": saved.assigned_node_id,
                "idempotency_key": saved.idempotency_key,
            },
        )
        await self.ws.broadcast(
            "task.assigned",
            {
                "task_id": str(saved.task_id),
                "task_type": saved.task_type,
                "assigned_node_id": saved.assigned_node_id,
                "status": saved.status,
            },
        )

        # Best-effort authenticated push to remote agent HTTP server; heartbeat pull acts as guaranteed backup
        if node.agent_url:
            token = self.settings.node_tokens_map.get(node.node_id, "")
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    await client.post(
                        f"{node.agent_url.rstrip('/')}/tasks/execute",
                        json=saved.model_dump(mode="json"),
                        headers={"X-Node-Token": token},
                    )
            except httpx.HTTPError:
                pass

        return saved

    async def ack_task(self, task_id: UUID, request: TaskAckRequest) -> TaskRecord:
        task = self._get_task_or_404(task_id)
        if task.assigned_node_id != request.node_id:
            raise HTTPException(
                status_code=403,
                detail=f"Task {task_id} is assigned to {task.assigned_node_id}, not {request.node_id}",
            )
        if task.status in ("COMPLETED", "CANCELLED"):
            return task

        new_lease = utc_now() + timedelta(seconds=self.settings.twinnode_task_lease_seconds)
        updated = self.repo.update_task(
            task_id,
            status=request.status,
            lease_until=new_lease,
            error_message=request.message if request.status == "REJECTED" else None,
        )
        if request.status == "RUNNING":
            await self.ws.broadcast(
                "task.started",
                {"task_id": str(task_id), "node_id": request.node_id, "status": "RUNNING"},
            )
        return updated

    async def submit_task_result(
        self, task_id: UUID, request: TaskResultSubmitRequest
    ) -> TaskRecord:
        task = self._get_task_or_404(task_id)
        if task.assigned_node_id != request.node_id:
            raise HTTPException(
                status_code=403,
                detail=f"Task {task_id} is assigned to {task.assigned_node_id}, not {request.node_id}",
            )
        if task.status == "COMPLETED":
            return task

        if request.status == "FAILED":
            failed = self.repo.update_task(
                task_id,
                status="FAILED",
                error_message=request.error_message or "Remote node reported task failure",
            )
            self.audit.log(
                actor=request.node_id,
                action="task.failed",
                entity_type="task",
                entity_id=str(task_id),
                details={"error": failed.error_message},
            )
            return failed

        if not isinstance(request.result, dict) or not request.result:
            raise HTTPException(status_code=400, detail="Task completion requires a non-empty result object")

        expected_checksum = compute_canonical_checksum(request.result)
        if expected_checksum != request.checksum:
            raise HTTPException(
                status_code=400,
                detail=f"Result checksum mismatch: expected {expected_checksum}, got {request.checksum}",
            )

        completed = self.repo.update_task(
            task_id,
            status="COMPLETED",
            result={**request.result, "duration_ms": request.duration_ms},
            checksum=request.checksum,
            lease_until=None,
            error_message=None,
        )
        self.audit.log(
            actor=request.node_id,
            action="task.completed",
            entity_type="task",
            entity_id=str(task_id),
            details={
                "checksum": request.checksum,
                "duration_ms": request.duration_ms,
                "executed_on_hostname": request.result.get("executed_on_hostname"),
            },
        )
        await self.ws.broadcast(
            "task.completed",
            {
                "task_id": str(task_id),
                "node_id": request.node_id,
                "checksum": request.checksum,
                "status": "COMPLETED",
            },
        )
        return completed

    async def sweep_timeouts(self, now_override: datetime | None = None) -> dict[str, int]:
        """Mark stale nodes OFFLINE and transition expired in-flight tasks to RETRY_PENDING/FAILED."""
        now = now_override or utc_now()
        nodes_marked_offline = 0
        tasks_recovered = 0

        offline_node_ids: set[str] = set()
        for node in self.repo.list_nodes():
            age = (now - node.last_heartbeat).total_seconds()
            if node.status in ("OFFLINE", "DISCONNECTED"):
                offline_node_ids.add(node.node_id)
                continue
            if age > self.settings.twinnode_heartbeat_timeout_seconds:
                prev = node.status
                self.repo.update_node_status(
                    node.node_id, "OFFLINE", worker_active=False
                )
                offline_node_ids.add(node.node_id)
                nodes_marked_offline += 1
                self.audit.log(
                    actor="system:heartbeat_monitor",
                    action="node.offline",
                    entity_type="physical_node",
                    entity_id=node.node_id,
                    details={"previous_status": prev, "age_seconds": round(age, 2)},
                )
                await self.ws.broadcast(
                    "node.offline",
                    {"node_id": node.node_id, "previous_status": prev, "age_seconds": round(age, 2)},
                )

        for task in self.repo.list_inflight_tasks():
            lease_expired = task.lease_until is not None and now > task.lease_until
            node_down = task.assigned_node_id in offline_node_ids
            if lease_expired or node_down:
                if task.retry_count < self.settings.twinnode_max_retries:
                    self.repo.update_task(
                        task.task_id,
                        status="RETRY_PENDING",
                        retry_count=task.retry_count + 1,
                        error_message=(
                            "Assigned node went OFFLINE before task completion; queued for retry."
                            if node_down
                            else "Task lease expired; queued for retry."
                        ),
                    )
                else:
                    self.repo.update_task(
                        task.task_id,
                        status="FAILED",
                        error_message="Maximum retry limit reached after node disconnect/lease timeout.",
                    )
                tasks_recovered += 1

        return {
            "nodes_marked_offline": nodes_marked_offline,
            "tasks_moved_to_recovery": tasks_recovered,
        }
