from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from apps.api.app.core.database import utc_now
from apps.api.app.core.state import AppContainer, get_container
from apps.api.app.modules.scenario_engine.event_impact import (
    EventMissingCoordinatesError,
    EventNotConfirmedError,
    calculate_event_impact,
)
from apps.api.app.schemas.events import (
    EventConfirmRequest,
    EventCreateRequest,
    EventImpactRequest,
    EventImpactResponse,
    EventRecord,
)

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=EventRecord)
async def create_event(
    request: EventCreateRequest,
    container: AppContainer = Depends(get_container),
) -> EventRecord:
    if request.event_key:
        existing = container.event_repo.get_event_by_key(request.event_key)
        if existing is not None:
            return existing

    now = utc_now()
    is_demo = request.event_origin == "SEEDED_DEMO"
    event = EventRecord(
        event_id=uuid4(),
        event_key=request.event_key,
        event_origin=request.event_origin,
        name=request.name,
        event_type=request.event_type,
        venue_name=request.venue_name,
        city=request.city,
        address=request.address,
        latitude=request.latitude,
        longitude=request.longitude,
        start_at=request.start_at,
        end_at=request.end_at,
        attendance_low=request.attendance_low,
        attendance_high=request.attendance_high,
        attendance_basis=request.attendance_basis,
        intensity=request.intensity,
        verification_status="DEMO_SCENARIO" if is_demo else "UNVERIFIED",
        status="CANDIDATE",
        source_ids=[],
        field_provenance={
            "origin": request.event_origin,
            "source_url": request.source_url,
            "source_summary": request.source_summary,
        },
        created_at=now,
        updated_at=now,
    )
    saved = container.event_repo.create_event(event)
    container.audit.log(
        actor="operator",
        action="event.created",
        entity_type="event",
        entity_id=str(saved.event_id),
        details={"event_origin": saved.event_origin, "name": saved.name},
    )
    await container.ws_manager.broadcast(
        "event.created",
        {
            "event_id": str(saved.event_id),
            "name": saved.name,
            "event_origin": saved.event_origin,
            "verification_status": saved.verification_status,
        },
    )
    return saved


@router.get("", response_model=list[EventRecord])
async def list_events(
    container: AppContainer = Depends(get_container),
) -> list[EventRecord]:
    return container.event_repo.list_events()


@router.get("/{event_id}", response_model=EventRecord)
async def get_event(
    event_id: UUID,
    container: AppContainer = Depends(get_container),
) -> EventRecord:
    ev = container.event_repo.get_event(event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    return ev


@router.post("/{event_id}/confirm", response_model=EventRecord)
async def confirm_event(
    event_id: UUID,
    request: EventConfirmRequest,
    container: AppContainer = Depends(get_container),
) -> EventRecord:
    ev = container.event_repo.get_event(event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    if ev.event_origin == "SEEDED_DEMO" and not request.accept_demo_assumptions:
        raise HTTPException(
            status_code=422,
            detail="Demo scenario confirmation requires accept_demo_assumptions=true.",
        )

    now = utc_now()
    new_verification = ev.verification_status
    if ev.event_origin == "SEEDED_DEMO":
        new_verification = "DEMO_SCENARIO"
    elif ev.event_origin == "MANUAL_INPUT":
        new_verification = "MANUALLY_VERIFIED"

    att_low = request.attendance_low if request.attendance_low is not None else ev.attendance_low
    att_high = request.attendance_high if request.attendance_high is not None else ev.attendance_high
    att_basis = request.attendance_basis or (
        "OPERATOR_ASSUMPTION"
        if (request.attendance_low is not None or request.attendance_high is not None or request.accept_demo_assumptions)
        and ev.attendance_basis == "UNKNOWN"
        else ev.attendance_basis
    )

    updated = ev.model_copy(
        update={
            "venue_name": request.venue_name if request.venue_name is not None else ev.venue_name,
            "latitude": request.latitude if request.latitude is not None else ev.latitude,
            "longitude": request.longitude if request.longitude is not None else ev.longitude,
            "start_at": request.start_at if request.start_at is not None else ev.start_at,
            "end_at": request.end_at if request.end_at is not None else ev.end_at,
            "attendance_low": att_low,
            "attendance_high": att_high,
            "attendance_basis": att_basis,
            "intensity": request.intensity if request.intensity is not None else ev.intensity,
            "verification_status": new_verification,
            "status": "CONFIRMED",
            "confirmed_by": request.operator_id,
            "confirmed_at": now,
            "confirmation_notes": request.notes,
            "updated_at": now,
        }
    )
    saved = container.event_repo.update_event(updated)
    container.audit.log(
        actor=request.operator_id,
        action="event.confirmed",
        entity_type="event",
        entity_id=str(saved.event_id),
        details={
            "accept_demo_assumptions": request.accept_demo_assumptions,
            "verification_status": saved.verification_status,
            "attendance_basis": saved.attendance_basis,
        },
    )
    await container.ws_manager.broadcast(
        "event.operator_confirmed",
        {
            "event_id": str(saved.event_id),
            "confirmed_by": request.operator_id,
            "verification_status": saved.verification_status,
        },
    )
    return saved


@router.post("/{event_id}/impact", response_model=EventImpactResponse)
async def map_event_impact(
    event_id: UUID,
    request: EventImpactRequest,
    container: AppContainer = Depends(get_container),
) -> EventImpactResponse:
    ev = container.event_repo.get_event(event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    sim_run = container.sim_repo.get_run(request.simulation_id)
    if sim_run is None:
        raise HTTPException(status_code=404, detail=f"Simulation {request.simulation_id} not found")

    cells = container.network_repo.get_cells(sim_run.network_id)
    try:
        impact = calculate_event_impact(event=ev, cells=cells, request=request)
    except EventNotConfirmedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EventMissingCoordinatesError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    container.event_repo.save_impact(impact)
    container.audit.log(
        actor="operator",
        action="event.impact_mapped",
        entity_type="event",
        entity_id=str(ev.event_id),
        state_version=sim_run.state_version,
        details={
            "simulation_id": str(sim_run.id),
            "affected_cell_count": len(impact.affected_cells),
            "total_estimated_uplift_mbps": impact.total_estimated_uplift_mbps,
        },
    )
    await container.ws_manager.broadcast(
        "event.mapped",
        {
            "event_id": str(ev.event_id),
            "simulation_id": str(sim_run.id),
            "affected_cell_ids": [c.cell_id for c in impact.affected_cells],
        },
    )
    return impact
