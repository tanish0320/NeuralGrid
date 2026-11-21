from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import UUID

import httpx

from agents.twinnode.node_agent.host_metrics import get_hostname, get_local_ipv4, read_host_telemetry
from agents.twinnode.tasks.registry import DisallowedTaskError, execute_allowlisted_task
from apps.api.app.schemas.twinnode import TaskRecord


class NodeWorker:
    """Software worker running on Tanish (Agent A) or Junaid (Agent B) laptop."""

    def __init__(
        self,
        *,
        node_id: str,
        node_token: str,
        controller_url: str,
        agent_url: str | None = None,
        worker_slots: int = 2,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.node_id = node_id
        self.node_token = node_token
        self.controller_url = controller_url.rstrip("/")
        self.agent_url = agent_url
        self.worker_slots = worker_slots
        self._external_client = http_client

        self.worker_active: bool = False
        self.draining: bool = False
        self._active_tasks: set[UUID] = set()
        self._completed_cache: dict[str, tuple[dict[str, Any], str]] = {}
        self._background_jobs: set[asyncio.Task[None]] = set()
        self.last_rtt_ms: float = 0.0

    def _headers(self) -> dict[str, str]:
        return {"X-Node-Token": self.node_token}

    def _get_client(self) -> tuple[httpx.AsyncClient, bool]:
        if self._external_client is not None:
            return self._external_client, False
        return httpx.AsyncClient(base_url=self.controller_url, timeout=8.0), True

    async def register(self) -> dict[str, Any]:
        client, should_close = self._get_client()
        try:
            payload = {
                "node_id": self.node_id,
                "hostname": get_hostname(),
                "token": self.node_token,
                "agent_version": "1.5.0",
                "agent_url": self.agent_url,
                "capabilities": ["traffic_batch", "scenario_evaluation", "counterfactual_batch"],
                "worker_slots": self.worker_slots,
                "capacity_estimate_score": 1.0,
            }
            resp = await client.post("/api/v1/nodes/register", json=payload, headers=self._headers())
            resp.raise_for_status()
            return resp.json()
        finally:
            if should_close:
                await client.aclose()

    def activate_worker(self) -> dict[str, Any]:
        self.draining = False
        self.worker_active = True
        return {"node_id": self.node_id, "worker_active": True, "status": "ACTIVE"}

    def standby_worker(self) -> dict[str, Any]:
        self.draining = False
        self.worker_active = False
        return {"node_id": self.node_id, "worker_active": False, "status": "STANDBY"}

    def drain_worker(self) -> dict[str, Any]:
        self.draining = True
        if not self._active_tasks:
            self.worker_active = False
        return {
            "node_id": self.node_id,
            "worker_active": self.worker_active,
            "draining": True,
            "active_tasks": len(self._active_tasks),
        }

    async def send_heartbeat(self) -> dict[str, Any]:
        cpu_pct, mem_pct = read_host_telemetry()
        client, should_close = self._get_client()
        try:
            t0 = time.perf_counter()
            payload = {
                "cpu_pct": cpu_pct,
                "memory_pct": mem_pct,
                "worker_active": self.worker_active,
                "worker_slots": self.worker_slots,
                "active_tasks": len(self._active_tasks),
                "local_rtt_ms": round(self.last_rtt_ms, 2),
                "ip_address": get_local_ipv4(),
                "agent_url": self.agent_url,
            }
            resp = await client.post(
                f"/api/v1/nodes/{self.node_id}/heartbeat",
                json=payload,
                headers=self._headers(),
            )
            self.last_rtt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            resp.raise_for_status()
            data = resp.json()
        finally:
            if should_close:
                await client.aclose()

        # Act on controller desired command delivered via heartbeat response
        cmd = data.get("desired_command", "NONE")
        if cmd == "ACTIVATE":
            self.activate_worker()
        elif cmd == "STANDBY":
            self.standby_worker()
        elif cmd == "DRAIN":
            self.drain_worker()

        # Pull-dispatch any ASSIGNED tasks when worker is active
        for raw_task in data.get("pending_tasks", []):
            task = TaskRecord.model_validate(raw_task)
            self.schedule_task(task)

        return data

    def schedule_task(self, task: TaskRecord) -> bool:
        if not self.worker_active or self.draining:
            return False
        if task.task_id in self._active_tasks:
            return False
        job = asyncio.create_task(self.execute_task(task))
        self._background_jobs.add(job)
        job.add_done_callback(self._background_jobs.discard)
        return True

    async def execute_task(self, task: TaskRecord) -> dict[str, Any]:
        # Local idempotency cache prevents re-execution on duplicate delivery
        if task.idempotency_key in self._completed_cache:
            cached_res, cached_sum = self._completed_cache[task.idempotency_key]
            await self._post_result(task.task_id, "COMPLETED", cached_res, cached_sum, 0.0)
            return cached_res

        self._active_tasks.add(task.task_id)
        try:
            await self._post_ack(task.task_id, "ACCEPTED")
            await self._post_ack(task.task_id, "RUNNING")
            t0 = time.perf_counter()
            result, checksum = await asyncio.to_thread(
                execute_allowlisted_task, task.task_type, task.seed, task.payload
            )
            duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            self._completed_cache[task.idempotency_key] = (result, checksum)
            await self._post_result(task.task_id, "COMPLETED", result, checksum, duration_ms)
            return result
        except DisallowedTaskError as exc:
            await self._post_ack(task.task_id, "REJECTED", message=str(exc))
            raise
        except Exception as exc:
            await self._post_result(
                task.task_id,
                "FAILED",
                {"error": str(exc)},
                "sha256:" + ("0" * 64),
                0.0,
                error_message=str(exc),
            )
            raise
        finally:
            self._active_tasks.discard(task.task_id)
            if self.draining and not self._active_tasks:
                self.worker_active = False

    async def _post_ack(
        self, task_id: UUID, status: str, message: str | None = None
    ) -> None:
        client, should_close = self._get_client()
        try:
            resp = await client.post(
                f"/api/v1/tasks/{task_id}/ack",
                json={"node_id": self.node_id, "status": status, "message": message},
                headers=self._headers(),
            )
            resp.raise_for_status()
        finally:
            if should_close:
                await client.aclose()

    async def _post_result(
        self,
        task_id: UUID,
        status: str,
        result: dict[str, Any],
        checksum: str,
        duration_ms: float,
        error_message: str | None = None,
    ) -> None:
        client, should_close = self._get_client()
        try:
            resp = await client.post(
                f"/api/v1/tasks/{task_id}/result",
                json={
                    "node_id": self.node_id,
                    "status": status,
                    "checksum": checksum,
                    "result": result,
                    "duration_ms": duration_ms,
                    "error_message": error_message,
                },
                headers=self._headers(),
            )
            resp.raise_for_status()
        finally:
            if should_close:
                await client.aclose()

    async def shutdown(self) -> None:
        for job in list(self._background_jobs):
            if not job.done():
                job.cancel()
        self._background_jobs.clear()
