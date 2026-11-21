from __future__ import annotations

import asyncio
import hmac
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException

from agents.twinnode.node_agent.host_metrics import get_hostname, get_local_ipv4, read_host_telemetry
from agents.twinnode.node_agent.worker import NodeWorker
from apps.api.app.core.database import utc_iso, utc_now
from apps.api.app.schemas.twinnode import TaskRecord


def create_agent_app(
    *,
    node_id: str,
    node_token: str,
    controller_url: str,
    agent_port: int = 8101,
    agent_url: str | None = None,
    heartbeat_interval_seconds: float = 2.0,
) -> FastAPI:
    """Create the TwinNode physical Node Agent FastAPI server (Node A or Node B)."""
    resolved_agent_url = agent_url or f"http://{get_local_ipv4()}:{agent_port}"
    worker = NodeWorker(
        node_id=node_id,
        node_token=node_token,
        controller_url=controller_url,
        agent_url=resolved_agent_url,
    )

    def _require_token(x_node_token: str | None = Header(default=None)) -> None:
        if not x_node_token or not hmac.compare_digest(
            x_node_token.encode("utf-8"), node_token.encode("utf-8")
        ):
            raise HTTPException(status_code=401, detail="Invalid or missing X-Node-Token")

    async def _heartbeat_loop() -> None:
        registered = False
        while True:
            try:
                if not registered:
                    await worker.register()
                    registered = True
                await worker.send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception:
                registered = False
            await asyncio.sleep(heartbeat_interval_seconds)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        bg_task = asyncio.create_task(_heartbeat_loop())
        try:
            yield
        finally:
            bg_task.cancel()
            await worker.shutdown()

    agent_app = FastAPI(
        title=f"NeuralGrid TwinNode Agent ({node_id})",
        version="1.5.0",
        lifespan=lifespan,
    )
    agent_app.state.worker = worker

    @agent_app.get("/health")
    async def agent_health() -> dict[str, Any]:
        cpu, mem = read_host_telemetry()
        return {
            "status": "ok",
            "node_id": node_id,
            "hostname": get_hostname(),
            "ip_address": get_local_ipv4(),
            "worker_active": worker.worker_active,
            "draining": worker.draining,
            "cpu_pct": cpu,
            "memory_pct": mem,
            "timestamp": utc_iso(utc_now()),
        }

    @agent_app.post("/control/activate", dependencies=[Depends(_require_token)])
    async def activate() -> dict[str, Any]:
        return worker.activate_worker()

    @agent_app.post("/control/standby", dependencies=[Depends(_require_token)])
    async def standby() -> dict[str, Any]:
        return worker.standby_worker()

    @agent_app.post("/control/drain", dependencies=[Depends(_require_token)])
    async def drain() -> dict[str, Any]:
        return worker.drain_worker()

    @agent_app.post("/tasks/execute", dependencies=[Depends(_require_token)])
    async def accept_task(task: TaskRecord) -> dict[str, Any]:
        if task.assigned_node_id != node_id:
            raise HTTPException(status_code=403, detail="Task assigned to a different node")
        if not worker.worker_active:
            raise HTTPException(status_code=409, detail="Worker is currently in STANDBY")
        scheduled = worker.schedule_task(task)
        return {"accepted": scheduled, "task_id": str(task.task_id)}

    return agent_app
