from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from apps.api.app.core.state import AppContainer, get_container
from apps.api.app.schemas.simulations import (
    FaultInjectRequest,
    SimulationCreateRequest,
    SimulationEventInjectRequest,
    SimulationStateResponse,
)

router = APIRouter(prefix="/simulations", tags=["simulations"])


@router.post("", response_model=SimulationStateResponse)
async def create_simulation(
    request: SimulationCreateRequest,
    container: AppContainer = Depends(get_container),
) -> SimulationStateResponse:
    return container.sim_manager.create_simulation(request)


@router.get("", response_model=list[dict[str, Any]])
async def list_simulations(
    container: AppContainer = Depends(get_container),
) -> list[dict[str, Any]]:
    runs = container.sim_repo.list_runs()
    return [
        {
            "simulation_id": str(r.id),
            "seed": r.seed,
            "tick": r.tick,
            "state_version": r.state_version,
            "status": r.status,
            "active_event_id": str(r.active_event_id) if r.active_event_id else None,
        }
        for r in runs
    ]


@router.get("/{simulation_id}/state", response_model=SimulationStateResponse)
async def get_simulation_state(
    simulation_id: UUID,
    container: AppContainer = Depends(get_container),
) -> SimulationStateResponse:
    return container.sim_manager.get_state(simulation_id)


@router.post("/{simulation_id}/step", response_model=SimulationStateResponse)
async def step_simulation(
    simulation_id: UUID,
    container: AppContainer = Depends(get_container),
) -> SimulationStateResponse:
    return await container.sim_manager.step_simulation(simulation_id)


@router.post("/{simulation_id}/start", response_model=SimulationStateResponse)
async def start_simulation(
    simulation_id: UUID,
    container: AppContainer = Depends(get_container),
) -> SimulationStateResponse:
    return await container.sim_manager.start_simulation(simulation_id)


@router.post("/{simulation_id}/pause", response_model=SimulationStateResponse)
async def pause_simulation(
    simulation_id: UUID,
    container: AppContainer = Depends(get_container),
) -> SimulationStateResponse:
    return await container.sim_manager.pause_simulation(simulation_id)


@router.post("/{simulation_id}/reset", response_model=SimulationStateResponse)
async def reset_simulation(
    simulation_id: UUID,
    container: AppContainer = Depends(get_container),
) -> SimulationStateResponse:
    return await container.sim_manager.reset_simulation(simulation_id)


@router.post("/{simulation_id}/events", response_model=dict[str, Any])
async def inject_simulation_event(
    simulation_id: UUID,
    request: SimulationEventInjectRequest,
    container: AppContainer = Depends(get_container),
) -> dict[str, Any]:
    state, impact = await container.sim_manager.inject_event(simulation_id, request)
    return {
        "state": state.model_dump(mode="json"),
        "impact": impact.model_dump(mode="json"),
    }


@router.post("/{simulation_id}/faults", response_model=SimulationStateResponse)
async def inject_simulation_fault(
    simulation_id: UUID,
    request: FaultInjectRequest,
    container: AppContainer = Depends(get_container),
) -> SimulationStateResponse:
    return await container.sim_manager.inject_fault(simulation_id, request)
