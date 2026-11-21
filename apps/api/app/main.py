from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.app.api.v1 import (
    audit,
    event_intelligence,
    events,
    networks,
    nodes,
    plans,
    predictions,
    simulations,
    tasks,
    verification,
)
from apps.api.app.config import Settings, get_settings
from apps.api.app.core.database import utc_iso, utc_now
from apps.api.app.core.state import AppContainer
from apps.api.app.core.url_policy import DnsResolver
from apps.api.app.modules.event_intelligence.orchestrator import EventIntelligenceServiceProtocol
from simulation.seed_network import seed_network_if_needed


def create_app(
    *,
    settings: Settings | None = None,
    event_intelligence_service: EventIntelligenceServiceProtocol | None = None,
    dns_resolver: DnsResolver | None = None,
) -> FastAPI:
    """Create and configure the NeuralGrid FastAPI control plane."""
    cfg = settings or get_settings()
    container = AppContainer(
        settings=cfg,
        event_intelligence_service=event_intelligence_service,
        dns_resolver=dns_resolver,
    )

    async def _timeout_sweeper_loop() -> None:
        while True:
            try:
                await asyncio.sleep(3.0)
                await container.twinnode_controller.sweep_timeouts()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        seed_network_if_needed(
            container.network_repo,
            seed=cfg.neuralgrid_default_seed,
            cell_count=100,
            force=False,
        )
        container.event_repo.ensure_seeded_demo_event(cfg.demo_event_id)
        sweeper_task = asyncio.create_task(_timeout_sweeper_loop())
        try:
            yield
        finally:
            sweeper_task.cancel()
            await container.sim_manager.shutdown()
            container.db.close()

    app = FastAPI(
        title="NeuralGrid Control Plane API",
        version="1.5.0",
        description=(
            "Authoritative simulation control plane, 100-cell digital twin, EventSense API "
            "orchestration, constrained planner/governance, and TwinNode controller."
        ),
        lifespan=lifespan,
    )
    app.state.container = container

    cors_origins = cfg.cors_origins_list
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next: Any):
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
        request.state.correlation_id = correlation_id
        try:
            response = await call_next(request)
        except Exception:
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "correlation_id": correlation_id,
                },
                headers={"X-Correlation-ID": correlation_id},
            )
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, Any]:
        net = container.network_repo.get_current_network()
        registered_nodes = container.twinnode_repo.list_nodes()
        return {
            "status": "ok",
            "version": "1.5.0",
            "environment": cfg.neuralgrid_env,
            "db_journal_mode": container.db.journal_mode(),
            "network_cell_count": net.cell_count if net else 0,
            "registered_nodes": len(registered_nodes),
            "tanish_eventsense_service_loaded": container.event_orchestrator.get_service() is not None,
            "seeded_demo_fallback_enabled": cfg.eventsense_allow_seeded_fallback,
            "timestamp": utc_iso(utc_now()),
        }

    @app.websocket("/ws/live")
    async def websocket_live(websocket: WebSocket) -> None:
        await container.ws_manager.connect(websocket)
        try:
            await websocket.send_json(
                {
                    "event": "ws.connected",
                    "timestamp": utc_iso(utc_now()),
                    "data": {"message": "Connected to NeuralGrid live control-plane stream"},
                }
            )
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await container.ws_manager.disconnect(websocket)
        except Exception:
            await container.ws_manager.disconnect(websocket)

    api_prefix = "/api/v1"
    app.include_router(networks.router, prefix=api_prefix)
    app.include_router(simulations.router, prefix=api_prefix)
    app.include_router(event_intelligence.router, prefix=api_prefix)
    app.include_router(events.router, prefix=api_prefix)
    app.include_router(predictions.router, prefix=api_prefix)
    app.include_router(plans.router, prefix=api_prefix)
    app.include_router(nodes.router, prefix=api_prefix)
    app.include_router(tasks.router, prefix=api_prefix)
    app.include_router(verification.router, prefix=api_prefix)
    app.include_router(audit.router, prefix=api_prefix)

    return app


app = create_app()
