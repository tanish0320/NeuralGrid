from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.app.core.state import AppContainer, get_container
from apps.api.app.schemas.events import (
    CrawlRequest,
    CrawlResponse,
    DiscoveryRunDetailResponse,
    EventDiscoveryRequest,
    EventDiscoveryResponse,
    EventSourceRecord,
)

router = APIRouter(prefix="/event-intelligence", tags=["event-intelligence"])


@router.post("/discover", response_model=EventDiscoveryResponse)
async def discover_events(
    request: EventDiscoveryRequest,
    container: AppContainer = Depends(get_container),
) -> EventDiscoveryResponse:
    return await container.event_orchestrator.run_discovery(request)


@router.post("/crawl", response_model=CrawlResponse)
async def crawl_sources(
    request: CrawlRequest,
    container: AppContainer = Depends(get_container),
) -> CrawlResponse:
    return await container.event_orchestrator.run_crawl(request)


@router.get("/runs/{run_id}", response_model=DiscoveryRunDetailResponse)
async def get_discovery_run(
    run_id: UUID,
    container: AppContainer = Depends(get_container),
) -> DiscoveryRunDetailResponse:
    run = container.source_repo.get_discovery_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Discovery run {run_id} not found")
    return run


@router.get("/sources", response_model=list[EventSourceRecord])
async def list_event_sources(
    run_id: UUID | None = Query(default=None),
    event_id: UUID | None = Query(default=None),
    container: AppContainer = Depends(get_container),
) -> list[EventSourceRecord]:
    return container.source_repo.list_sources(run_id=run_id, event_id=event_id)
